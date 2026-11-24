# Extension Model, MockitoExtension, and SpringExtension in JUnit Jupiter

## 1. Why does JUnit Jupiter need extensions?

A method annotated with `@Test` usually only needs to verify outputs. However, real tests also need surrounding tasks: creating mocks, preparing data, injecting dependencies, loading a Spring `ApplicationContext`, measuring execution time, checking run conditions, or cleaning up resources after the test finishes.

JUnit Jupiter addresses these needs through its **Extension Model**. An extension is a component registered by JUnit into the execution lifecycle that receives `ExtensionContext` and implements corresponding *callback interfaces*. As a result, test infrastructure logic can be reused while the `@Test` body stays focused on the behavior to prove.

Two extensions very commonly seen in Spring Boot applications:

- **`MockitoExtension`** from Mockito: initializes and manages Mockito mocks, supports `@Mock`/`@InjectMocks` and `@Mock` parameters, and validates stubbing when the test ends.
- **`SpringExtension`** from Spring Test: connects JUnit Jupiter with the Spring TestContext Framework to initialize or reuse an `ApplicationContext`, inject Spring beans, and apply Spring's test listeners and mechanisms.

JUnit is the **test execution engine**; Mockito creates **test doubles** for collaborators; Spring provides the **real container and wiring** per test configuration. Extensions let those capabilities participate at the exact right moments in the JUnit lifecycle.

| Question | JUnit Jupiter Extension Model | MockitoExtension | SpringExtension |
| --- | --- | --- | --- |
| Which library does it belong to? | `org.junit.jupiter.api.extension` | `org.mockito.junit.jupiter` | `org.springframework.test.context.junit.jupiter` |
| Responsibility | Standard API for callbacks, parameters, conditions, and state | Initializes/controls Mockito sessions and mocks | Integrates JUnit with Spring TestContext |
| Does it create a Spring context? | No | No | Yes, if Spring Test configuration requires it |
| Does it automatically create Mockito mocks? | No | Yes, for matching `@Mock` | Not merely from using SpringExtension |
| Can they be combined? | Serves as the shared foundation | Used alone for unit tests; consider carefully when combined with Spring | Used with Spring Test, Spring Boot Test, and test slices |
| What is being tested? | Depends on the written extension | Java logic with isolated collaborators | Bean wiring, configuration, Spring integration |

**Learning goals:** understand extension contracts, registration mechanisms, callback invocation order, and how parameters are resolved; write a small custom extension; use MockitoExtension and SpringExtension in the right context; distinguish `@Mock` from Spring mock beans; and avoid conflicts when combining multiple extensions.

## 2. JUnit 4 vs JUnit Jupiter

JUnit 4 had mechanisms such as `@RunWith`, `TestRule`, and `MethodRule`. A test class could only have a single runner, making combining runners difficult. JUnit Jupiter (the API/test engine portion of JUnit 5) unifies these needs into a consistent **`Extension`** model and allows registering multiple extensions at various scopes.

```text
JUnit Platform
└── Jupiter TestEngine
    └── Test class / test method
        ├── Extension A: callbacks around the test
        ├── Extension B: parameter resolution
        └── Extension C: Spring TestContext control
            └── @Test + assertions
```

`Extension` is a **marker interface**: on its own it defines no required methods. An extension must implement one or more specific interfaces such as `BeforeEachCallback`, `ParameterResolver`, or `TestExecutionExceptionHandler` to provide behavior.

Do not confuse:

- `@BeforeEach` is a **method written by the test author**.
- `BeforeEachCallback` is an **extension hook**, invoked by JUnit **before** `@BeforeEach` methods.
- `@ExtendWith(...)` is a way to **register** extensions, not a test method.
- `@Autowired` is a Spring directive; plain JUnit Jupiter does not process it automatically without SpringExtension/TestContext participating.
- `@Mock` is only a Mockito annotation; without Mockito's corresponding initialization mechanism, the field may remain `null`.

## 3. Core extension points

| Extension API | When is it used? | Example |
| --- | --- | --- |
| `BeforeAllCallback` / `AfterAllCallback` | Before/after the set of tests in a test container | Preparing and cleaning up shared resources |
| `BeforeEachCallback` / `AfterEachCallback` | Wrapping setup and teardown of each individual test | Initializing sessions, logging, managing contexts |
| `BeforeTestExecutionCallback` / `AfterTestExecutionCallback` | Immediately before/after the `@Test` body, inside the `@BeforeEach`/`@AfterEach` cycle | Timing the test body alone |
| `TestInstancePostProcessor` | After JUnit creates the test instance | Injecting fields or configuring the test object |
| `ParameterResolver` | Supplying arguments to constructors/methods invoked by JUnit | Injecting `Clock`, `TestInfo`, Mockito mocks, Spring beans |
| `ExecutionCondition` | Deciding whether to enable a test/container | Skipping tests based on environment |
| `TestExecutionExceptionHandler` | Handling exceptions thrown by a test method | Logging error context; may rethrow depending on design |
| `TestWatcher` | Observing finalized test outcomes | Recording PASS/FAIL/ABORTED/DISABLED tests |
| `InvocationInterceptor` | Intercepting or wrapping supported test/lifecycle calls | Measuring or controlling invocation execution |
| `ExtensionContext.Store` | Storing scoped state tied to a test/container | Storing start timestamps, resource handles |

These hooks differ **in timing**. For example, if you only want to measure the duration of the `@Test` method itself, using `BeforeTestExecutionCallback` and `AfterTestExecutionCallback` fits better than `BeforeEachCallback` and `AfterEachCallback`, because the latter pair also wraps the test's setup step.

### Sequence of a simple test

With an extension implementing all four callbacks around a test method:

```text
BeforeEachCallback       [extension]
    @BeforeEach          [test class]
BeforeTestExecutionCallback [extension]
        @Test            [test class]
AfterTestExecutionCallback  [extension]
    @AfterEach           [test class]
AfterEachCallback        [extension]
```

`BeforeAllCallback` runs before the container's `@BeforeAll`; `AfterAllCallback` runs after `@AfterAll`. When multiple extensions exist, JUnit guarantees **wrapping behavior** for corresponding "before/after" callbacks: an extension registered earlier runs its "before" callback earlier and its "after" callback later than an extension registered after it.

This is the **typical ordering model** for understanding the API, not a guarantee that every callback still runs if a test is disabled or an earlier initialization step fails. Do not treat printed logs or cross-test execution order as a business contract.

## 4. Registering extensions: three common ways

### 4.1. `@ExtendWith` — declarative registration

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CalculatorServiceTest {
    @Test
    void calculationWorks() {
        // Test body.
    }
}
```

`@ExtendWith` can be applied at the class or method level to adjust registration scope; multiple extensions can be declared, including as an array:

```java
@ExtendWith({FirstExtension.class, SecondExtension.class})
class MultipleExtensionsTest {
    // Assumes FirstExtension and SecondExtension are already defined.
}
```

This is a **syntax illustration snippet**, not a standalone runnable class when the referenced extensions are missing. When registering declaratively, declaration order matters for callbacks; do not reorder arbitrarily if extensions have lifecycle dependencies.

You can also create **composed annotations** containing `@ExtendWith` to reuse the same configuration across many tests. `@SpringJUnitConfig` is a real-world example of this approach.

### 4.2. `@RegisterExtension` — programmatic registration

```java
import org.junit.jupiter.api.extension.RegisterExtension;

class WithConfiguredExtensionTest {
    @RegisterExtension
    static final SomeConfiguredExtension extension =
            new SomeConfiguredExtension("test-env");
}
```

This snippet only illustrates the registration form; `SomeConfiguredExtension` is a hypothetical class that must be implemented in the project. This approach is helpful when an extension needs constructor arguments or a builder. A `static` extension field can participate in class-level callbacks. With an instance field, some class-level callbacks cannot work the same way because the instance has not been created yet when `@BeforeAll` runs. When combining multiple extension fields, review `@Order` rules to avoid relying on non-obvious default ordering.

### 4.3. Automatic detection

JUnit Jupiter also supports discovering extensions via `ServiceLoader` when auto-detection is explicitly enabled. Because this is not the default mechanism, prefer `@ExtendWith`/`@RegisterExtension` in normal tests so registration sources stay visible and easy to debug.

**Registration scope:** class-level extensions normally apply to tests in that class; method-level extensions apply only to invocations of that method. Nested tests, inherited annotations, and test interfaces follow specific inheritance/scoping rules in JUnit Jupiter. When writing a stateful extension, use `ExtensionContext` with the appropriate scope instead of a shared global variable.

## 5. Setting up a Java 17+ sample project for practice

Let's create a small Gradle project requiring no server or database. It uses the dependency set managed by Spring Boot 3.3.x **for tests only**, sufficient to run the JUnit Jupiter, MockitoExtension, and SpringExtension examples in the following sections.

`settings.gradle`:

```groovy
rootProject.name = 'jupiter-extension-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Prerequisites: JDK 17 or newer and a compatible Gradle version (you may use the repository's Gradle Wrapper). The test classes below go under `src/test/java/com/example/testing/`, package `com.example.testing`. Each example is a standalone class with its own imports.

In an **existing Spring Boot 3.3.x application** with the Boot BOM or plugin, the test dependency typically only needs:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

If using the BOM from an existing Boot project, avoid forcing an incompatible newer JUnit or Spring Framework version. This example explicitly picks Spring Boot 3.3.5 to speak accurately about annotations in the Boot 3.3 line, without claiming it is the latest release.

Run all tests:

```bash
./gradlew test
```

On Windows, use `gradlew.bat test`. If the project does not yet have a Gradle Wrapper, use `gradle test` with an installed Gradle. Run a single class:

```bash
./gradlew test --tests 'com.example.testing.MockitoOrderServiceTest'
```

`--tests` filters **which tests run**, while extensions govern the infrastructure/lifecycle inside the selected tests.

## 6. Writing your own extension to see callbacks in action

The following example records callback order and asserts it right at the end of the cycle. It uses **one test method**, making the verification deterministic and independent of actual execution time.

`src/test/java/com/example/testing/ExtensionLifecycleTest.java`:

```java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.AfterEachCallback;
import org.junit.jupiter.api.extension.AfterTestExecutionCallback;
import org.junit.jupiter.api.extension.BeforeEachCallback;
import org.junit.jupiter.api.extension.BeforeTestExecutionCallback;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.extension.ExtensionContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(ExtensionLifecycleTest.TraceExtension.class)
class ExtensionLifecycleTest {
    private final List<String> trace = new ArrayList<>();

    static final class TraceExtension implements
            BeforeEachCallback,
            BeforeTestExecutionCallback,
            AfterTestExecutionCallback,
            AfterEachCallback {

        private static ExtensionLifecycleTest test(ExtensionContext ctx) {
            return (ExtensionLifecycleTest) ctx.getRequiredTestInstance();
        }

        @Override
        public void beforeEach(ExtensionContext ctx) {
            test(ctx).trace.add("extension.beforeEach");
        }

        @Override
        public void beforeTestExecution(ExtensionContext ctx) {
            test(ctx).trace.add("extension.beforeTestExecution");
        }

        @Override
        public void afterTestExecution(ExtensionContext ctx) {
            test(ctx).trace.add("extension.afterTestExecution");
        }

        @Override
        public void afterEach(ExtensionContext ctx) {
            ExtensionLifecycleTest instance = test(ctx);
            instance.trace.add("extension.afterEach");

            assertEquals(List.of(
                    "extension.beforeEach",
                    "test.@BeforeEach",
                    "extension.beforeTestExecution",
                    "test.@Test",
                    "extension.afterTestExecution",
                    "test.@AfterEach",
                    "extension.afterEach"
            ), instance.trace);
        }
    }

    @BeforeEach
    void setUp() {
        trace.add("test.@BeforeEach");
    }

    @Test
    void verifiesCallbackOrder() {
        trace.add("test.@Test");
    }

    @AfterEach
    void tearDown() {
        trace.add("test.@AfterEach");
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.testing.ExtensionLifecycleTest'
```

**Expectation:** 1 test PASSES; the assertion in `TraceExtension.afterEach` verifies all 7 events in exact order. If you change the expected order, the test FAILS; it needs no stdout output. This is an example of **callback lifecycles**, creating no Spring `ApplicationContext` and using no Mockito.

Key takeaway: callbacks and `@BeforeEach`/`@AfterEach` methods belong to two distinct layers of behavior. Extensions receive `ExtensionContext`; when a test instance exists, `getRequiredTestInstance()` returns the current instance. Never use a shared `static List` across tests because parallel execution can interleave state.

### Storing state via `ExtensionContext.Store`

Extensions that measure time or open resources may need to pass data from a "before" callback to an "after" callback. Instead of a static mutable map, use a namespaced store:

`src/test/java/com/example/testing/TimingExtension.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.extension.AfterTestExecutionCallback;
import org.junit.jupiter.api.extension.BeforeTestExecutionCallback;
import org.junit.jupiter.api.extension.ExtensionContext;

public final class TimingExtension
        implements BeforeTestExecutionCallback, AfterTestExecutionCallback {

    private static final ExtensionContext.Namespace NAMESPACE =
            ExtensionContext.Namespace.create(TimingExtension.class);

    @Override
    public void beforeTestExecution(ExtensionContext context) {
        context.getStore(NAMESPACE).put("startNanos", System.nanoTime());
    }

    @Override
    public void afterTestExecution(ExtensionContext context) {
        Long start = context.getStore(NAMESPACE)
                .remove("startNanos", Long.class);
        if (start != null) {
            long elapsed = System.nanoTime() - start;
            System.out.println("Elapsed nanos: " + elapsed);
        }
    }
}
```

Registration:

```java
@ExtendWith(TimingExtension.class)
class AnyTimedTest {
    @Test
    void sample() {
        assertEquals(4, 2 + 2);
    }
}
```

The `AnyTimedTest` snippet is **abbreviated**: placing it in a standalone file requires JUnit imports for `@ExtendWith`, `@Test`, and `assertEquals`; `TimingExtension` is complete as shown above. The number after `Elapsed nanos:` is **not fixed** and is not a PASS/FAIL criterion; execution duration varies by machine and run. The store is accessed through the invocation's own context/namespace, avoiding JVM-wide shared variables.

## 7. `ParameterResolver`: JUnit can supply parameters to tests

JUnit Jupiter lets test methods, lifecycle methods, or constructors declare parameters when a supporting `ParameterResolver` is available. JUnit includes built-in resolvers, such as for `TestInfo`. Custom extensions can also supply `Clock`, a test configuration, or other objects.

Two main methods:

- `supportsParameter(ParameterContext, ExtensionContext)`: returns `true` if the extension takes responsibility for that parameter.
- `resolveParameter(ParameterContext, ExtensionContext)`: returns the corresponding object at runtime.

Example providing a fixed clock so tests do not depend on the current date.

`src/test/java/com/example/testing/FixedClockTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.ParameterContext;
import org.junit.jupiter.api.extension.ParameterResolver;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(FixedClockTest.FixedClockExtension.class)
class FixedClockTest {
    static final class FixedClockExtension implements ParameterResolver {
        @Override
        public boolean supportsParameter(
                ParameterContext parameter,
                ExtensionContext context) {
            return parameter.getParameter().getType() == Clock.class;
        }

        @Override
        public Object resolveParameter(
                ParameterContext parameter,
                ExtensionContext context) {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Test
    void receivesFixedClock(Clock clock) {
        assertEquals("2024-01-01T00:00:00Z",
                clock.instant().toString());
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.testing.FixedClockTest'
```

**Expectation:** 1 test PASSES; JUnit invokes the resolver to pass `Clock` into `receivesFixedClock`. No `new Clock(...)` is needed inside the test method or as a Spring bean. The main reason to use this kind of injection is supplying repeated fixtures consistently across many tests.

**Pitfall:** if two `ParameterResolver`s both claim support for the same parameter, JUnit can throw `ParameterResolutionException` due to competing resolvers. A custom resolver should narrow `supportsParameter` to specific types and/or annotations rather than returning `true` broadly.

## 8. MockitoExtension: initializing mocks and verifying usage

### 8.1. What does MockitoExtension handle?

`MockitoExtension` lives in the `mockito-junit-jupiter` artifact (included in `spring-boot-starter-test` in Boot 3.3.x). It typically:

1. Initializes `@Mock`, `@Spy`, `@Captor`, and processes `@InjectMocks` on the test instance according to Mockito rules.
2. Manages the **Mockito session** alongside the JUnit lifecycle.
3. Allows declaring mocks directly on test/lifecycle method parameters via `@Mock`.
4. Enforces **strict stubbing** to catch unused stubs or suspicious setups; configurable with `@MockitoSettings`.

It **does not** create an `ApplicationContext`, run real repositories, or inject dependencies into Spring beans. The word "injection" in `@InjectMocks` means Mockito tries to construct/wire collaborators into the plain Java class under test; this differs from Spring Dependency Injection.

### 8.2. Runnable unit test: `@Mock` + `@InjectMocks`

`src/test/java/com/example/testing/MockitoOrderServiceTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MockitoOrderServiceTest {
    interface TaxClient {
        int taxPercent();
    }

    static final class OrderService {
        private final TaxClient taxClient;

        OrderService(TaxClient taxClient) {
            this.taxClient = taxClient;
        }

        int totalWithTax(int netPrice) {
            if (netPrice < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return netPrice
                    + netPrice * taxClient.taxPercent() / 100;
        }
    }

    @Mock
    TaxClient taxClient;

    @InjectMocks
    OrderService service;

    @Test
    void addsTaxToNetPrice() {
        when(taxClient.taxPercent()).thenReturn(10);

        assertEquals(110, service.totalWithTax(100));
        verify(taxClient).taxPercent();
    }

    @Test
    void rejectsNegativePriceWithoutCallingCollaborator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.totalWithTax(-1)
        );
        verifyNoInteractions(taxClient);
    }

    @Test
    void canInjectMethodScopedMock(@Mock TaxClient temporaryClient) {
        when(temporaryClient.taxPercent()).thenReturn(5);

        OrderService temporaryService = new OrderService(temporaryClient);

        assertEquals(105, temporaryService.totalWithTax(100));
        verify(temporaryClient).taxPercent();
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.testing.MockitoOrderServiceTest'
```

**Expectation: 3 tests PASS.** The first verifies `100 + 10% = 110`; the second verifies the exception happens before calling the collaborator; the third receives a mock solely via a method parameter. No database, Spring context, or HTTP server is needed.

What happens step by step:

- Before the test, MockitoExtension creates a `TaxClient` mock for the `@Mock` field and constructs `OrderService` with that mock via `@InjectMocks`.
- Inside `addsTaxToNetPrice`, `when(...).thenReturn(10)` defines the return value, and `verify` checks the interaction actually occurred.
- At the end of the test, MockitoExtension closes the session and runs strictness checks. An unused stub can be flagged as an error instead of being silently ignored.

With MockitoExtension, you can write tests without `@InjectMocks` and construct `new OrderService(taxClient)` manually in `@BeforeEach` or inside the test. That often makes dependencies clearer and avoids relying on Mockito's injection heuristics.

### 8.3. Strict stubbing: why can a test FAIL even when assertions PASS?

MockitoExtension defaults to strict stubbing behavior in modern Mockito releases. Example:

```java
@Test
void unusedStubExample() {
    when(taxClient.taxPercent()).thenReturn(10);
    assertEquals(2, 1 + 1);
}
```

This is an **anti-example**: `taxClient.taxPercent()` was never called, so such a stub can be flagged by Mockito as **unnecessary stubbing** when the session ends. Do not copy this test into a suite expecting it to PASS.

The proper fix is usually **removing the unnecessary stub**. Only when there is a concrete reason should you use `lenient()` for a stub or configure class-level strictness via:

```java
@MockitoSettings(strictness = Strictness.LENIENT)
```

This configuration snippet requires importing `org.mockito.junit.jupiter.MockitoSettings` and `org.mockito.quality.Strictness`, applied to a class using MockitoExtension. Avoid turning on lenient mode suite-wide just to mask poorly designed tests.

### 8.4. `@Mock` is not `@MockBean`

`@Mock` creates a Mockito object scoped to a standard test. Inside a booted Spring `ApplicationContext`, a mock field on the test **does not automatically replace beans** used by controllers/services in the context.

In Spring Boot **3.3.x**, `org.springframework.boot.test.mock.mockito.MockBean` creates or replaces a bean inside the test context; Spring Boot also automatically resets mock beans after tests according to configuration. In Spring Framework 6.2 / Spring Boot 3.4+, there is the newer `@MockitoBean` API. When following this lesson on Boot 3.3.x, use **Boot's `@MockBean`**; do not copy the newer annotation by mistake if your classpath does not yet support it.

Do not conclude `@MockBean` is merely "MockitoExtension in Spring form" — it is a context customizer/test listener mechanism integrated with Spring Boot Test's bean registry.

## 9. SpringExtension: connecting JUnit Jupiter to Spring TestContext

### 9.1. Role of SpringExtension

`SpringExtension` lives in `spring-test`, acting as the adapter between JUnit Jupiter and the **Spring TestContext Framework**.

Key responsibilities:

- Connects the test lifecycle with Spring's `TestContextManager` and `TestExecutionListener`s.
- Loads `ApplicationContext` per `@ContextConfiguration` or matching settings; leverages the **context cache** across tests with equivalent configurations.
- Injects beans into fields, constructors, or test/lifecycle methods per Spring Test contracts and autowiring rules.
- Supports test transactions, SQL fixtures, profiles, properties, and other TestContext features when declared.
- Integrates with Spring Boot test configurations when using `@SpringBootTest` or test slices.

SpringExtension is not a clone of MockitoExtension: SpringExtension actually uses the Spring container to satisfy DI and manage contexts. Never boot a Spring context just to test a plain Java function.

### 9.2. `@SpringJUnitConfig` is a composed annotation

The following two forms are equivalent in terms of registering the extension and configuring the context:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class FirstSpringTest {
}
```

```java
@SpringJUnitConfig(TestConfig.class)
class SecondSpringTest {
}
```

The snippets above are **illustrative syntax**, assuming `TestConfig` exists and matching annotations are imported. `@SpringJUnitConfig` combines `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`; adding `@ExtendWith(SpringExtension.class)` again therefore brings no benefit.

In Spring Boot 3.3.x, `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, and Boot's other test slice annotations already integrate `SpringExtension`. Test authors do not need to declare `@ExtendWith(SpringExtension.class)` again.

### 9.3. Small, standalone Spring context test

`src/test/java/com/example/testing/SpringClockWiringTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(SpringClockWiringTest.Config.class)
class SpringClockWiringTest {
    @Configuration
    static class Config {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }

        @Bean
        DateService dateService(Clock clock) {
            return new DateService(clock);
        }
    }

    static final class DateService {
        private final Clock clock;

        DateService(Clock clock) {
            this.clock = clock;
        }

        String today() {
            return LocalDate.now(clock).toString();
        }
    }

    @Autowired
    DateService dateService;

    @Test
    void injectsBeanDefinedInSpringContext() {
        assertEquals("2024-01-01", dateService.today());
    }
}
```

Run:

```bash
./gradlew test --tests 'com.example.testing.SpringClockWiringTest'
```

**Expectation:** 1 test PASSES. `@SpringJUnitConfig` makes SpringExtension load the context from `Config`, Spring creates the `Clock` and `DateService` beans, and then injects `DateService` into the test field. This tests **real Spring wiring** in a minimal context; it still does not start full Boot auto-configuration or an HTTP server.

Easy-to-confuse detail: `@Bean DateService dateService(Clock clock)` receives `Clock` from the Spring container per `@Bean` DI rules; whereas `@Test void receivesFixedClock(Clock clock)` earlier received `Clock` from a **custom JUnit ParameterResolver**. The parameter syntax looks similar, but the underlying engine responsible differs.

## 10. Using SpringExtension in Spring Boot applications

### 10.1. `@SpringBootTest` pulls SpringExtension into the test automatically

In an application that already has `@SpringBootApplication`, the test below checks whether Boot's context can assemble:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
        // JUnit PASSES if the application context loads successfully.
    }
}
```

This is a **test integrated into an existing Boot application**, not runnable inside the minimal Gradle Java project from section 5 without application configuration. There is no need to add `@ExtendWith(SpringExtension.class)` because `@SpringBootTest` is already meta-annotated accordingly.

By default `@SpringBootTest` does not open a real HTTP port; the `MOCK` web environment suits simulating web requests in tests. When a real server is needed, use `webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT` and test via a suitable HTTP client.

### 10.2. Mocking a collaborator in a Spring context with Boot 3.3.x

Suppose the real application has an `OrderService` bean and a `PaymentGateway` bean, with contracts `OrderService.placeOrder(String orderId)` and `PaymentGateway.charge(String orderId)`. To test the service's logic **obtained from the Spring context** while avoiding calls to a real payment gateway, Boot 3.3.x uses:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@SpringBootTest
class OrderServiceSpringTest {
    @Autowired
    OrderService orderService;

    @MockBean
    PaymentGateway paymentGateway;

    @Test
    void placesOrderWithMockedPaymentGateway() {
        when(paymentGateway.charge("order-1")).thenReturn(true);

        assertTrue(orderService.placeOrder("order-1"));
    }
}
```

**This is an example attached to an existing application**: it requires real definitions of `OrderService`, `PaymentGateway`, Spring configuration, and the described method contracts. It is not a standalone file snippet. `@MockBean` replaces/registers the mock in the Spring context so the autowired `OrderService` sees the mock, while SpringExtension manages TestContext. There is no default reason to add MockitoExtension to this test class.

The difference from the Mockito unit test in section 8 is crucial: Mockito unit tests instantiate `OrderService` directly, whereas Boot tests verify which `OrderService` Spring resolves, which dependencies it injects, and how the context is configured. The latter is heavier, but it protects different boundaries.

## 11. When should you combine MockitoExtension and SpringExtension?

JUnit allows registering multiple extensions. However, **being allowed to register both** does not mean you **need both** for every test.

| Need | Best starting point | Reason |
| --- | --- | --- |
| Testing Java business logic with fake collaborators | `@ExtendWith(MockitoExtension.class)`, `@Mock` | Lightweight; creates no Spring context |
| Testing bean wiring in a small config | `@SpringJUnitConfig` | SpringExtension + TestContext suffice |
| Testing Boot wiring or multi-bean flows | `@SpringBootTest` | SpringExtension is already registered |
| Testing an MVC slice needing mocked service dependencies | `@WebMvcTest` + `@MockBean` (Boot 3.3.x) | Creates MVC context with Boot-managed mock beans |
| Test receives mock parameters without needing Spring | MockitoExtension + `@Mock` parameter | Mockito resolves the parameter |
| Test wants Spring to inject beans into parameters | SpringExtension + `@Autowired` parameter or constructor setup | Spring's resolver fetches from ApplicationContext |

There are situations requiring both: for instance, SpringExtension manages the context while MockitoExtension supplies a mock **used only inside the test method**, not registered as a Spring bean. In that case, actively verify resolvers, lifecycles, and ownership. That is an intentional exception; the normal starting point remains using the minimal extension required.

### ParameterResolver conflicts

If both extensions claim responsibility for the same constructor/method parameter, JUnit can throw an error like:

```text
org.junit.jupiter.api.extension.ParameterResolutionException:
Discovered multiple competing ParameterResolvers for parameter ...
```

For example, a constructor configured to **autowire all parameters from Spring** while also using MockitoExtension to resolve `@Mock` parameters can cause overlap. The fix is clarifying "who supplies this parameter": Spring beans come from the context, Mockito mocks use `@Mock` in unit tests or mock beans declared via the compatible Boot/Spring Test mechanism.

**Do not try to fix it merely by reordering `@ExtendWith`** when two resolvers both claim one parameter; that does not eliminate ownership ambiguity. If parameter mocks are unnecessary, drop MockitoExtension; if a Spring bean needs mocking, use Spring's test-context bean override mechanism.

### Distinguishing easily confused annotations

| Annotation | Who processes it? | Effect |
| --- | --- | --- |
| `@Test` | JUnit Jupiter | Defines a test method |
| `@ExtendWith(MockitoExtension.class)` | JUnit Jupiter + MockitoExtension | Registers Mockito session, initializes mocks |
| `@Mock` | MockitoExtension or another Mockito initializer | Creates a Mockito mock for the test |
| `@InjectMocks` | Mockito | Attempts to build/inject mocks into the class under test |
| `@ExtendWith(SpringExtension.class)` | JUnit Jupiter + SpringExtension | Integrates Spring TestContext |
| `@SpringJUnitConfig` | Spring Test + JUnit | Combines SpringExtension and context config |
| `@Autowired` | Spring Test/Spring container | Injects matching Spring beans |
| `@SpringBootTest` | Spring Boot Test + SpringExtension | Boots the Boot application context for testing |
| `@MockBean` (Boot 3.3.x) | Spring Boot Test | Creates/replaces a bean in context with a Mockito mock |
| `@MockitoBean` (Spring Framework 6.2+) | Spring Test | Bean override API in newer Framework versions |

## 12. Lifecycle and state pitfalls

### 12.1. Assuming `MockitoExtension` initializes Spring beans

`@Mock` and `@InjectMocks` can make unit tests PASS even when Spring configuration is broken. That is normal: unit tests verify the **logic** of the class constructed in the test, not the ApplicationContext. Add a Spring Test when real wiring needs verification.

### 12.2. Using `@Autowired` in plain JUnit Jupiter

```java
class WrongSpringTest {
    @Autowired
    SomeService service;

    @Test
    void testIt() {
        service.run();
    }
}
```

This is an **anti-example** (and `SomeService` is undefined): plain JUnit Jupiter does not inject Spring fields merely because the annotation is present. Without SpringExtension/TestContext, the field may remain `null`. Once SpringExtension is used, you must also supply configuration containing the matching bean.

### 12.3. Forgetting to register MockitoExtension

```java
class MissingMockitoSetupTest {
    @Mock
    Collaborator collaborator;
}
```

This is also an **anti-example**. The annotation alone does not make JUnit initialize mocks. Use MockitoExtension, or manually manage `MockitoAnnotations.openMocks(this)` and close resources at the right time; in most Jupiter tests, MockitoExtension is cleaner and less error-prone.

### 12.4. Sharing state across tests

JUnit Jupiter creates a new test instance per test method by default, though a project can configure `@TestInstance(PER_CLASS)`. Spring TestContext can share its context cache across classes. Never infer from "fresh test instance" that **all Spring singleton beans** or DB data are reset.

Do not store extension state in unsynchronized mutable static fields if tests run in parallel. Use `ExtensionContext.Store` with proper namespaces, scope, and resource cleanup. If the store holds long-lived resources, pay attention to resource-closing mechanisms and compatibility with your JUnit version.

### 12.5. Depending on the wrong "before/after" hook order

`BeforeEachCallback` runs before `@BeforeEach`, whereas `BeforeTestExecutionCallback` runs after setup and right before the test body. A common mistake is an extension reading data created by `@BeforeEach` inside `BeforeEachCallback`: at that moment, setup has not happened yet. Pick the callback matching the right phase.

### 12.6. Adding `@SpringBootTest` to fix every test error

A full Boot context may need a database, security, or external config; it boots slowly and widens the failure surface. If testing one Java class, MockitoExtension is enough. For a small DI configuration, `@SpringJUnitConfig` can fit. For MVC/JPA, prefer corresponding test slices; reserve full context when multi-layer integration truly needs to be proved.

### 12.7. Assuming `@Transactional` rolls back every request

In Spring Test, a test method's transaction can roll back at the end of the method. Yet when `@SpringBootTest(webEnvironment = RANDOM_PORT)` makes real HTTP calls, the server handles them on a different thread and transaction, so server-side commits **do not automatically roll back** from the test method's annotation. Manage fixtures and cleanup at the right boundary. SpringExtension does not fold every request into one shared transaction.

### 12.8. Hitting `UnnecessaryStubbingException` or parameter mock errors

Only stub calls needed by the behavior under test; Mockito strictness catches unused stubbing. With method-parameter mocks, note that a parameter mock is a distinct object from a similarly typed field mock; if the method under test uses the field mock while you stub the parameter mock, the stubbing has no effect. Trace which collaborator is **actually used** before adjusting assertions.

### 12.9. Mixing annotation APIs across versions

Some newer docs use `@MockitoBean`; Boot 3.3.x still uses Boot's `@MockBean` for test contexts. JUnit Jupiter 5.x and JUnit Jupiter 6.x have different platform requirements. For projects with locked versions, prioritize the BOM and docs for that version instead of copying annotations from newer releases assuming they exist.

## 13. Workflow for choosing and verifying extensions in a project

When starting a test, walk through these questions:

1. **Only calling a plain Java class?** Use `@Test` and assertions; if the class has collaborators needing isolation, add MockitoExtension.
2. **Need Spring to create/inject beans?** Use SpringExtension via `@SpringJUnitConfig`, or a Boot test annotation that already includes SpringExtension.
3. **Need to replace a Spring bean with a mock?** Use the bean-mocking mechanism for your Boot/Spring version; `@Mock` alone does not replace beans.
4. **Need repeated fixtures/hooks across many tests?** Consider a custom extension using `BeforeEachCallback`, `ParameterResolver`, or `ExtensionContext.Store` as appropriate.
5. **Registering multiple extensions?** Check callback order, scope, `ParameterResolver` collisions, and shared resources.
6. **Test FAILS?** Identify which phase failed: discovery, constructor parameters, extension setup, Spring context refresh, Mockito session, test body, or cleanup callbacks.

### Commands to verify the example suite

In the Gradle project from section 5, the corresponding complete classes are:

```bash
./gradlew test --tests 'com.example.testing.ExtensionLifecycleTest'
./gradlew test --tests 'com.example.testing.FixedClockTest'
./gradlew test --tests 'com.example.testing.MockitoOrderServiceTest'
./gradlew test --tests 'com.example.testing.SpringClockWiringTest'
```

There are **6 test methods** in total across the four complete classes: 1 lifecycle + 1 parameter resolver + 3 Mockito + 1 Spring. With dependencies and code matching the examples above, all assertions PASS. `ApplicationContextTest`/`OrderServiceSpringTest` in section 10 **are not counted** among these six tests because they are integration examples requiring a real Boot application.

For detailed inspection, open the Gradle report at `build/reports/tests/test/index.html` or XML files in `build/test-results/test/`. Do not interpret `BUILD SUCCESSFUL` as "verified the entire Boot application" when only a few unit/component tests ran.

## 14. Self-check questions

**1.** Does `MockitoExtension` initialize a Spring `ApplicationContext`?  
No. It manages Mockito mocks and sessions; SpringExtension/TestContext handles the Spring context.

**2.** Why does `@SpringBootTest` not need an extra `@ExtendWith(SpringExtension.class)`?  
Because Boot's test annotation already includes SpringExtension.

**3.** Which runs first: `BeforeEachCallback` or `@BeforeEach`?  
The extension's `BeforeEachCallback`.

**4.** In `ParameterResolver`, what is the purpose of `supportsParameter`?  
It determines whether the resolver claims responsibility for the requested parameter; `resolveParameter` supplies the actual value.

**5.** Why might `@Mock` have no effect on a Spring-injected service?  
Because a mock field on the test class does not automatically modify the bean registry inside the Spring context.

**6.** What should you do when two extensions both resolve the same parameter?  
Clarify ownership or narrow the resolver's condition to avoid parameter resolution conflicts.

**7.** When no Spring context is needed, why prefer MockitoExtension?  
Tests stay simple, run fast, and focus on the logic and interactions of the class under test.

## 15. Summary

The JUnit Jupiter **Extension Model** provides a unified contract for extending lifecycles, resolving parameters, evaluating conditions, and managing test state. **MockitoExtension** gives Java tests explicit mocks, controlled sessions, and strict stubbing. **SpringExtension** links JUnit with Spring TestContext to verify dependency injection, bean configuration, and Spring/Boot integration.

Choose an extension based on **what is under test**: plain Java logic, a single Spring component, or multiple beans in a Boot context. Paying close attention to where dependencies are created and who owns them prevents most `null` mock, missing bean, wrong lifecycle, and competing resolver bugs.

### Primary reference sources

- [JUnit Jupiter 5.10.2 User Guide — Extension Model](https://docs.junit.org/5.10.2/user-guide/) (registration, callback ordering, parameter resolution, store).
- [Mockito — MockitoExtension source/Javadoc](https://github.com/mockito/mockito/blob/main/mockito-extensions/mockito-junit-jupiter/src/main/java/org/mockito/junit/jupiter/MockitoExtension.java) (mock initialization, strictness, method parameters).
- [Spring Framework 6.1 — SpringJUnitConfig](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/test/context/junit/jupiter/SpringJUnitConfig.html) (composed annotation).
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) (`@SpringBootTest`, test slices, `@MockBean`, and transactions).
