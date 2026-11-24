# The TestContext Framework and the Role of SpringExtension

Spring Boot can be tested at many levels: from a plain Java function to services, controllers, repositories, transactions, and a fully configured application. When a test needs dependency injection, bean configuration, profiles, transactions, or other Spring features, instantiating every object manually with `new` is no longer enough. The **Spring TestContext Framework** provides the foundation for creating, managing, and reusing an `ApplicationContext` for tests. **`SpringExtension`** is the bridge that brings that capability into the **JUnit Jupiter (JUnit 5)** lifecycle.

This lesson explains the relationship between JUnit, SpringExtension, and the TestContext Framework; the components behind the annotations; how the context is bootstrapped, injected, and cached; how listeners work across each test phase; the difference between `@SpringJUnitConfig` and `@SpringBootTest`; and important limitations regarding transactions, test isolation, and execution cost.

**After this lesson, you will be able to:**

- Distinguish between `TestContext`, `ApplicationContext`, `TestContextManager`, `TestExecutionListener`, and `SpringExtension`.
- Choose plain JUnit, plain Spring TestContext, test slices, or Spring Boot integration tests based on the contract to be verified.
- Configure `@ExtendWith(SpringExtension.class)`, `@ContextConfiguration`, and `@SpringJUnitConfig` for their proper roles.
- Inject Spring beans into fields, constructors, test methods, and lifecycle callbacks when needed.
- Understand the phases of the JUnit Jupiter lifecycle that SpringExtension forwards to TestContext.
- Use `@ActiveProfiles`, `@TestPropertySource`, `@Transactional`, and `@DirtiesContext` for their intended purposes.
- Understand context caching, why new contexts are created, and common errors when running Spring Boot tests.

## 1. Starting from the Need: When Does a Test Need Spring?

Consider a class with no Spring dependencies:

```java
public final class PricePolicy {
    public boolean hasFreeShipping(int total) {
        if (total < 0) {
            throw new IllegalArgumentException("total must be >= 0");
        }
        return total >= 200;
    }
}
```

This is **illustrative code**: if placed in a separate Java file, a package declaration matching the project is required. For pure calculations, a JUnit test can use `new PricePolicy()` and assert the result; Spring is not needed. However, if you want to verify that a service has been created by Spring, configuration properties have been injected properly, a transaction interceptor works, or a repository connects to a real database, you need Spring-managed components.

| What Needs to Be Verified | Appropriate Test Level | Is Spring TestContext Required? |
|---|---|---|
| Standalone calculation rules | JUnit unit test | No |
| A service receiving dependencies via constructor and its business logic | Unit test with mock/fake collaborators | No, if Spring wiring is not the target |
| Whether beans are created and injected correctly according to configuration | Spring context/integration test | Yes |
| REST routing, binding, JSON, and MVC security | Spring MVC slice with `@WebMvcTest` | Yes, via Spring Test integration |
| JPA mapping/queries and DB constraints | Persistence slice with `@DataJpaTest` | Yes |
| Transactions, auto-configuration, and multi-bean integration | `@SpringBootTest` or an appropriate context test | Yes |
| Real HTTP over a network port and multiple components | Integration/end-to-end test | Usually yes, along with environment and data control |

**Important rule:** Do not start Spring just because a test involves a `@Service` class. A Spring bean is still a Java object. Only load a context when **Spring's capabilities are part of what needs to be verified** or real dependencies require it.

## 2. Core Components of the Spring TestContext Framework

The name `TestContext` is easily confused with `ApplicationContext`. They have different roles.

| Component | Role | Key Point to Remember |
|---|---|---|
| **`ApplicationContext`** | Container holding beans, dependencies, properties, resources, events, and Spring configuration components | The runtime environment for beans that the test wants to use |
| **`TestContext`** | Context of the **test execution**: test class, instance, method, exception, attributes, and access to the application context | Not another name for `ApplicationContext` |
| **`TestContextManager`** | Coordinates a `TestContext` and dispatches lifecycle callbacks to listeners | The integration point between the test framework and TestContext |
| **`TestExecutionListener`** | Hooks running before/after test execution phases to inject dependencies, handle transactions, SQL, dirty contexts, etc. | Includes default listeners and supports custom listeners |
| **`TestContextBootstrapper`** | Reads test configuration, selects loaders/listeners, and builds the metadata to initialize TestContext | Boot has its own bootstrapper to handle Boot-specific features |
| **`ContextLoader` / `SmartContextLoader`** | Loads an `ApplicationContext` from classes, locations, and configuration sources | JUnit does not create beans directly |
| **`SpringExtension`** | JUnit Jupiter extension that forwards JUnit callbacks to `TestContextManager` and resolves parameters from the Spring context | The **JUnit Jupiter integration** layer, not the container itself |

Relationship diagram:

```text
JUnit Platform / JUnit Jupiter
         |
         | runs @Test, @BeforeEach, @AfterEach...
         v
  SpringExtension   (@ExtendWith)
         |
         | forwards lifecycle callbacks + resolves parameters
         v
  TestContextManager
         |
         +--> TestContext (test class / method / instance / attributes)
         |
         +--> TestExecutionListener (DI, transaction, SQL, cache...)
         |
         +--> TestContextBootstrapper / ContextLoader
                         |
                         v
               ApplicationContext
                (beans, profiles, data source...)
                         |
                         +--> Context cache reused when configurations match
```

The diagram expresses **responsibilities**, not a fixed call stack for every callback. The context may be loaded lazily when a listener or callback actually needs it; using the extension does not mean each test method creates a new container.

## 3. Where Does `SpringExtension` Sit in JUnit Jupiter?

JUnit Jupiter supports an extension model via `@ExtendWith`. An extension can participate in the lifecycle, post-process test instances, and supply method parameters. `SpringExtension` implements the appropriate extension points so that Spring TestContext participates in the JUnit lifecycle.

When you write:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class ExampleTest {
    // ...
}
```

you are instructing:

1. **JUnit Jupiter** to use `SpringExtension` to integrate Spring into the test.
2. **Spring TestContext** to use `@ContextConfiguration` to know which configuration class `TestConfig` needs to be loaded.
3. The test can receive beans from `ApplicationContext`; Spring listeners can prepare the instance and handle transactions, SQL, or cleanup according to annotations.

The example above is **illustrative syntax**; to compile, it needs annotation imports, an actual `TestConfig` class, and `@Test` methods. Section 7 provides a complete example.

### 3.1. Why Are Both Annotations Needed?

`@ExtendWith(SpringExtension.class)` only **registers the bridge with JUnit**; it does not specify where all the beans or configurations come from.

`@ContextConfiguration` describes the **context configuration sources** (such as `classes`, `locations`, `initializers`, custom loaders, etc.). It does not automatically replace registering the extension in a JUnit Jupiter test unless another composed annotation is present.

Spring provides `@SpringJUnitConfig` to combine both. Therefore, the following two forms are equivalent for typical configuration purposes:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class FirstTest {
}
```

```java
@SpringJUnitConfig(TestConfig.class)
class SecondTest {
}
```

These two classes only illustrate configuration and do not yet contain actual `@Test` methods. **Do not add `@ExtendWith(SpringExtension.class)` again when already using `@SpringJUnitConfig`**; the composed annotation already includes the extension.

### 3.2. What JUnit Does vs. What Spring Does

- JUnit Jupiter discovers tests, runs `@Test`, `@ParameterizedTest`, checks assertions, and manages the JUnit lifecycle.
- SpringExtension plugs the TestContext Framework into lifecycle points and provides parameter resolvers so tests can receive beans, properties, or the `ApplicationContext`.
- Spring TestContext is responsible for bootstrapping, retrieving the `ApplicationContext`, invoking listeners, and managing the context cache.
- Spring Boot extends the bootstrapping process to load the application via `SpringApplication`, supporting auto-configuration and specialized test mechanisms.

If a simple test only uses JUnit `@Test` + `assertEquals`, it does not automatically need SpringExtension.

## 4. Lifecycle: How Do JUnit and TestContext Coordinate?

A JUnit Jupiter class has milestones: `@BeforeAll`, test instance creation, `@BeforeEach`, `@Test`, `@AfterEach`, `@AfterAll`. SpringExtension translates these milestones into callbacks managed by TestContextManager.

| Meaningful Phase | JUnit/SpringExtension Callback | TestContextManager / TestExecutionListener Callback |
|---|---|---|
| Before all tests in the class | Before-all extension callback | `beforeTestClass` |
| After JUnit creates the instance | Test-instance post-processing | `prepareTestInstance` (e.g., injects `@Autowired` fields) |
| Before the test's `@BeforeEach` | Before-each extension callback | `beforeTestMethod` |
| After `@BeforeEach`, right before `@Test` | Before-test-execution callback | `beforeTestExecution` |
| Right after `@Test`, before `@AfterEach` | After-test-execution callback | `afterTestExecution` |
| After `@AfterEach` | After-each extension callback | `afterTestMethod` |
| After all tests in the class | After-all extension callback | `afterTestClass` |

**Two distinct "before" milestones**: `beforeTestMethod` is called before `@BeforeEach` setup, whereas `beforeTestExecution` is called right before the `@Test` body. Similarly, `afterTestExecution` runs right after the test body, while `afterTestMethod` runs after `@AfterEach` teardown. This matters if you write a custom listener to time a test method, prepare fixtures, or perform cleanup.

Some common `TestExecutionListener` implementations in Spring TestContext handle tasks such as:

- `DependencyInjectionTestExecutionListener`: injects dependencies into the test instance.
- `DirtiesContextBeforeModesTestExecutionListener` and `DirtiesContextTestExecutionListener`: handle `@DirtiesContext` modes.
- `TransactionalTestExecutionListener`: starts/ends test-managed transactions and handles `@BeforeTransaction`, `@AfterTransaction`.
- `SqlScriptsTestExecutionListener`: processes `@Sql` to prepare and clean up SQL data.
- `EventPublishingTestExecutionListener`: publishes test execution events when appropriate conditions are met.

**Do not think of listeners as direct JUnit callbacks:** `TestExecutionListener` is a Spring abstraction shared across multiple test frameworks; SpringExtension is the dedicated adapter for JUnit Jupiter.

## 5. How Does `TestContext` Differ from `ApplicationContext`?

`ApplicationContext` is the Spring container where beans are created and injected. `TestContext` holds information related to **the test run**, including the test class, test instance, test method, exception, and attributes for listeners.

For example, in a custom listener, you can read the name of the method being tested:

```java
// Illustrative snippet: not a standalone file.
// Inside a TestExecutionListener implementation:
@Override
public void beforeTestExecution(TestContext context) {
    String name = context.getTestMethod().getName();
    System.out.println("Running: " + name);
}
```

Here `context` is `org.springframework.test.context.TestContext`, **not** `org.springframework.context.ApplicationContext`. In real code, tests/beans usually only need `@Autowired` or to receive an `ApplicationContext` via argument injection; they do not manipulate `TestContextManager` directly.

Normally you **do not need to instantiate `TestContextManager` with `new`** in a JUnit Jupiter test using SpringExtension. The framework handles the orchestration. These APIs are mainly useful for debugging/testing custom integrations or writing extensions/listeners.

## 6. Annotations to Distinguish

| Annotation | Layer | Primary Effect |
|---|---|---|
| `@ExtendWith(SpringExtension.class)` | JUnit Jupiter | Registers Spring TestContext integration |
| `@ContextConfiguration` | Spring TestContext | Specifies classes/resources/loaders/initializers to build the context |
| `@SpringJUnitConfig` | Spring TestContext + Jupiter | Combines extension and context configuration for standard tests |
| `@SpringJUnitWebConfig` | Spring TestContext + Jupiter | Combines extension, context config, and web application context |
| `@SpringBootTest` | Spring Boot Test | Uses SpringApplication/Boot context; already integrates SpringExtension |
| `@WebMvcTest`, `@DataJpaTest` | Spring Boot Test slices | Loads appropriate parts of the application to test a specific boundary |
| `@ActiveProfiles` | Spring TestContext | Selects profiles for the context in tests |
| `@TestPropertySource` | Spring TestContext | Adds/overrides properties for building the context in tests |
| `@Autowired` | Spring DI | Injects beans into supported fields/constructors/parameters |
| `@Transactional` on a test | Spring TestContext transaction | Runs the test in a test-managed transaction when appropriate infrastructure exists |
| `@Sql` | Spring TestContext SQL | Executes SQL scripts/statements before/after tests as configured |
| `@DirtiesContext` | Spring TestContext cache | Marks the context as no longer eligible for reuse |
| `@TestExecutionListeners` | Spring TestContext | Registers/modifies listeners participating in the lifecycle |

**Version note:** Examples use **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+ / JUnit Jupiter 5**. If your project uses Spring Framework 7 or Spring Boot 4, check the dependencies and documentation for your exact version because many testing APIs and dependencies have evolved. The principles of bridging via extensions and context management remain the focus of this lesson.

## 7. Complete Example: `@SpringJUnitConfig` with Plain Spring TestContext

We create a small service that takes a prefix from a Spring property. Goal: verify that TestContext loads a `@Configuration`, resolves `Environment`, creates the bean, and injects it into the test. There is no need to boot all of Spring Boot.

**`src/main/java/com/example/testcontext/plain/GreetingService.java`**

```java
package com.example.testcontext.plain;

import java.util.Objects;

public final class GreetingService {
    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return prefix + ", " + name.strip() + "!";
    }
}
```

**`src/test/java/com/example/testcontext/plain/GreetingTestConfig.java`**

```java
package com.example.testcontext.plain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class GreetingTestConfig {

    @Bean
    GreetingService greetingService(Environment environment) {
        String prefix = environment.getRequiredProperty("greeting.prefix");
        return new GreetingService(prefix);
    }
}
```

**`src/test/java/com/example/testcontext/plain/GreetingSpringTest.java`**

```java
package com.example.testcontext.plain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(GreetingTestConfig.class)
@TestPropertySource(properties = "greeting.prefix=Xin chào")
class GreetingSpringTest {

    @Autowired
    GreetingService greetingService;

    @Test
    void createsBeanFromConfigurationAndProperties() {
        String result = greetingService.greet("  Mai  ");

        assertEquals("Xin chào, Mai!", result);
    }

    @Test
    void injectsTheSameSingletonBeanFromContext(
            @Autowired ApplicationContext applicationContext) {

        assertSame(greetingService,
                applicationContext.getBean(GreetingService.class));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> greetingService.greet("  "));
    }
}
```

### 7.1. Explaining via the Execution Flow

1. JUnit discovers `GreetingSpringTest`.
2. `@SpringJUnitConfig` registers `SpringExtension` and points to `GreetingTestConfig`.
3. `@TestPropertySource` adds the property `greeting.prefix=Xin chào` to the test context.
4. When the context needs to be loaded, Spring creates the `GreetingService` bean via the `@Bean` method. `Environment` is resolved by Spring; `getRequiredProperty` fails clearly if the property is missing.
5. `DependencyInjectionTestExecutionListener` injects the bean into the `greetingService` field on the test instance.
6. The test method invokes the real service and asserts the return value; the second method receives `ApplicationContext` directly via an `@Autowired` parameter resolved by SpringExtension.
7. There is no database, web server, transaction, or external I/O in this example.

**Why is `assertSame` true in the second test?** In the configuration above, `@Bean` has the default singleton scope, and both the field and `applicationContext.getBean(...)` point to the same bean in the same context. If a bean intentionally has prototype scope, do not use this assertion.

**Why not use `@SpringBootTest`?** This lesson tests Spring Java configuration and small dependency injection. A small context from `@SpringJUnitConfig` is enough to prove the goal; `@SpringBootTest` would add unnecessary auto-configuration overhead.

### 7.2. Writing the Annotations Explicitly Has the Same Meaning

You can replace the two annotations above the test with:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTestConfig.class)
@TestPropertySource(properties = "greeting.prefix=Xin chào")
class GreetingSpringTest {
    // Keep the @Test methods from the example above.
}
```

This is only a **header syntax variant**, not an additional class to compile with the same name. You need to import `org.junit.jupiter.api.extension.ExtendWith`, `org.springframework.test.context.junit.jupiter.SpringExtension`, and `org.springframework.test.context.ContextConfiguration` if using the explicit form.

## 8. Injection in Tests: Field, Constructor, Parameter, and Lifecycle

SpringExtension integrates with JUnit Jupiter's `ParameterResolver`. In addition to `@Autowired` fields handled by the listener, you can ask Spring to supply beans directly as parameters to a constructor, `@Test`, or `@BeforeEach`.

An alternative example **for syntax illustration only**, using the configuration and service from Section 7:

```java
@SpringJUnitConfig(GreetingTestConfig.class)
@TestPropertySource(properties = "greeting.prefix=Xin chào")
class ParameterInjectionTest {

    @Test
    void receivesBeanAsMethodArgument(
            @Autowired GreetingService service) {
        assertEquals("Xin chào, An!", service.greet("An"));
    }

    @BeforeEach
    void prepare(@Autowired ApplicationContext context) {
        assertNotNull(context.getBean(GreetingService.class));
    }
}
```

This snippet requires importing the corresponding JUnit/Spring assertions and annotations; it is an **illustrative example**, not a standalone file in the runnable list in Section 18.

When using constructor injection in a JUnit test, a parameter annotated with `@Autowired` or a suitably marked constructor is resolved by Spring. However, you must understand **test instance lifecycle**. If you use `@TestInstance(PER_CLASS)`, the constructor runs only once; if you also use `@DirtiesContext` between methods, beans injected from the old context may already be closed. In this specific situation, **field/setter injection** allows Spring to re-inject the test instance appropriately; do not hold references to beans belonging to a closed context.

JUnit may have multiple extensions resolving parameters; if two resolvers claim the same parameter conflictingly, the test may fail with an error. Use `@Autowired` explicitly for Spring beans and JUnit-provided parameters according to the framework semantics.

**Do not confuse this with constructor injection in production beans:** In production, constructor injection is great design. The note above only concerns **test class constructors with PER_CLASS lifecycle combined with context replacement**, not a reason to avoid constructor injection for services.

## 9. Complete Example: `@SpringBootTest` Already Includes SpringExtension

`@SpringBootTest` uses Spring Boot to build the `ApplicationContext` via `SpringApplication`, bringing Boot's configuration and auto-configuration capabilities. In JUnit Jupiter, this annotation **is already meta-annotated with `@ExtendWith(SpringExtension.class)`**, so there is no need to register SpringExtension a second time.

**`src/main/java/com/example/testcontext/boot/TestContextDemoApplication.java`**

```java
package com.example.testcontext.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestContextDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/testcontext/boot/ShippingPolicy.java`**

```java
package com.example.testcontext.boot;

import org.springframework.stereotype.Service;

@Service
public class ShippingPolicy {

    public int shippingFee(int subtotal, boolean express) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        if (express) {
            return 30;
        }
        return subtotal >= 200 ? 0 : 15;
    }
}
```

**`src/test/java/com/example/testcontext/boot/ShippingPolicyContextTest.java`**

```java
package com.example.testcontext.boot;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = TestContextDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ShippingPolicyContextTest {

    @Autowired
    ShippingPolicy policy;

    @Test
    void autowiresServiceAndAppliesShippingRules() {
        assertAll("shipping rules",
                () -> assertEquals(15, policy.shippingFee(199, false)),
                () -> assertEquals(0, policy.shippingFee(200, false)),
                () -> assertEquals(30, policy.shippingFee(200, true)));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.shippingFee(-1, false));
    }
}
```

The test verifies that **the Boot context is built and the `ShippingPolicy` bean is injected by Spring**, then verifies behavior. `webEnvironment=NONE` avoids creating a web environment; `SpringApplication` is still used to build the context.

**Practical test design:** if you only want to check that `shippingFee` computes correctly, a direct unit test with `new ShippingPolicy()` is lighter. `@SpringBootTest` is valuable when protecting bootstrapping, bean wiring, auto-configuration, properties, or multi-bean real interactions. The example uses a simple service to observe the TestContext mechanism itself.

### 9.1. Is `@ExtendWith(SpringExtension.class)` Still Needed?

No. With Spring Boot 3.3 and JUnit Jupiter, `@SpringBootTest` as well as slice tests like `@WebMvcTest` already integrate SpringExtension. Adding `@ExtendWith(SpringExtension.class)` only adds noise for readers and does not make the application inject "more."

### 9.2. Does `@SpringBootTest` Start an HTTP Server?

It depends on `webEnvironment`:

| Mode | Meaning |
|---|---|
| `MOCK` (default when a suitable web environment is present) | Creates a mock web environment; does not open an embedded HTTP server automatically |
| `RANDOM_PORT` | Starts an embedded server on a random port; HTTP clients can make real calls |
| `DEFINED_PORT` | Starts a server on the configured/default port; prone to resource collisions when tests run in parallel |
| `NONE` | Creates a non-web `ApplicationContext` with SpringApplication |

With `MOCK`, if you want to test MVC using `MockMvc`, it is typically combined with `@AutoConfigureMockMvc`. Do not assume `@SpringBootTest` alone automatically injects `MockMvc` into every test.

## 10. Bootstrap: How Is Configuration Found?

Spring TestContext reads annotations on the test class, determines the `TestContextBootstrapper`, and selects the appropriate `ContextLoader`, listeners, context initializers, and parameters to load the context.

With `@SpringJUnitConfig(GreetingTestConfig.class)`, the configuration is declared explicitly. With `@SpringBootTest` without specifying `classes`, Spring Boot typically searches for `@SpringBootConfiguration` or `@SpringBootApplication` by walking up from the test's package to parent packages. If none is found, the test may report that no configuration class could be located.

**To avoid ambiguity:** in the Boot example, we wrote `classes = TestContextDemoApplication.class` explicitly. In real projects, this attribute can be omitted if the package/class structure is correct and default discovery is appropriate.

Do not confuse two configuration annotations:

- `@Configuration` is standard Spring configuration; when declared as a nested class in a Boot test, it may be treated as the test's primary configuration.
- Boot's `@TestConfiguration` is used to add/override beans for the test context while still using the main application configuration under Boot's mechanism.

Adding a custom `@ComponentScan` at the application root can alter the exclude filters of slice tests. When `@WebMvcTest` unexpectedly loads too many beans or misses beans, check component scanning and imported configurations.

## 11. `@ActiveProfiles` and `@TestPropertySource` Affect Both Context and Cache

A test may need its own profile to avoid connecting to production services or to use test configuration:

```java
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "feature.registration.enabled=true",
        "external.mail.enabled=false"
})
@SpringJUnitConfig(TestConfig.class)
class FeatureTest {
    // ...
}
```

This is an **annotation pattern**; `TestConfig` and the test body are not defined here. Both annotations supply information when Spring creates the context, but by themselves they **do not guarantee** that production infrastructure will be disabled: the application's beans and configurations must actually honor those properties/profiles.

Key points:

1. `@ActiveProfiles` changes the set of beans/configs activated by profile.
2. `@TestPropertySource` adds properties for testing with appropriate precedence in TestContext property sources.
3. If two tests have different context configurations, different profiles, or different test properties, they may receive **two cache entries** and two separate contexts.
4. Avoid creating unnecessary per-test profiles/properties for small tests, which fragments the cache and slows down the suite.
5. For Spring Boot, `@SpringBootTest(properties = ...)` is also a way to supply properties; use it consistently and only add properties when the contract truly requires them.

**Limitation:** Do not assume a property has taken effect just because the annotation is present. The test should verify the relevant behavior/bean, just as `GreetingSpringTest` verified the bean's prefix.

## 12. Context Cache: Why Don't Multiple Tests Reload Spring from Scratch?

A major benefit of the TestContext Framework is **caching `ApplicationContext` instances by configuration**. If multiple tests use equivalent context configurations within the same JVM and the cache has not been invalidated, Spring can reuse an already-created context, reducing startup cost.

Factors in the cache key may include configuration classes/resources, initializers, loaders, profiles, property sources, parent contexts, web configuration, and `context customizers` (such as customizers provided by framework mock beans). Therefore, **you cannot look at two tests that both use `@SpringBootTest` and conclude they will definitely share a context**.

Important details for Spring Framework 6.x:

- The context cache defaults to a maximum of **32** entries; when exceeded, an LRU (least recently used) eviction policy applies.
- The cache is typically kept in **static JVM memory**. Two tests running in two separate JVMs/forks do not directly share this cache.
- `@DirtiesContext` marks a context as modified to the point it should not be reused; that context is removed from the cache and closed according to the specified mode.
- DEBUG-level logging for the `org.springframework.test.context.cache` category can reveal cache hit/miss statistics and cache size.
- Unnecessarily changing `@ActiveProfiles`, property sources, or mock bean configurations can increase the number of distinct contexts.

Example:

```text
Test A: @SpringJUnitConfig(GreetingTestConfig.class)
        property greeting.prefix = Xin chào
Test B: same config + same property
        -> usually reuses the context within the same JVM

Test C: same config but greeting.prefix = Hello
        -> different configuration, usually a different cache entry
```

This is a conceptual model; the actual cache key also considers other metadata and customizers. Do not turn class names or suite execution order into hard assumptions about context identity.

### 12.1. When Is `@DirtiesContext` Needed?

Use it when a test has dirtied the context—such as modifying bean definitions or mutating singleton state in a way other tests cannot cleanly recover from. **Do not apply `@DirtiesContext` by default to every test to "guarantee independence"**: doing so forces contexts to be rebuilt repeatedly and significantly increases runtime.

If only database data or a request-scoped object changes, consider transaction rollbacks, fixture cleanup, mock resets, or independent test data. `@DirtiesContext` is no substitute for an intentional isolation strategy for databases or external resources.

## 13. TestExecutionListener: Why Do DI and Transactions Work?

SpringExtension does not reimplement field injection, transactions, or SQL script execution itself. It calls TestContextManager, and the appropriate **`TestExecutionListener`** does the work at lifecycle callbacks.

Examples of bean integration:

- When preparing a test instance, `DependencyInjectionTestExecutionListener` can inject `@Autowired` fields.
- When a test has `@Transactional` and an appropriate transaction manager exists, `TransactionalTestExecutionListener` can open and end a test-managed transaction.
- With `@Sql`, `SqlScriptsTestExecutionListener` handles executing SQL as configured.
- With `@DirtiesContext`, the corresponding listeners know when to mark, close, or evict the context from the cache.

### 13.1. Custom Listeners

In specialized cases, you can write a listener to time tests, prepare resources, or record events:

```java
package com.example.testcontext.plain;

import org.springframework.test.context.TestContext;
import org.springframework.test.context.TestExecutionListener;

public class TestNameListener implements TestExecutionListener {

    @Override
    public void beforeTestExecution(TestContext testContext) {
        String testName = testContext.getTestMethod().getName();
        System.out.println("Starting test method: " + testName);
    }
}
```

If you actually need to register this listener, add the following annotation to the **test class**:

```java
@TestExecutionListeners(
        listeners = TestNameListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
```

This is an **annotation snippet**, not a standalone Java class. `MERGE_WITH_DEFAULTS` preserves default listeners such as dependency injection and transactions when adding a custom listener. If you replace the entire default listener set inadvertently, you may accidentally disable behaviors the test relies on.

Do not write listeners just to increase log volume. Tests may run in parallel or in a different order, and listener stdout is not proof of business correctness. When useful, a listener needs a clear purpose, no hidden side effects, and no reliance on execution order.

### 13.2. Listeners vs. Application Event Listeners

A `TestExecutionListener` is not necessarily a Spring bean in the `ApplicationContext`. Spring TestContext also supports `EventPublishingTestExecutionListener`, which publishes **test execution events** to bean listeners, though event publication depends on the context already being loaded and the lifecycle. Do not assume `BeforeTestClassEvent` is always published on the first context startup. That is an advanced API; most tests do not need to customize these events.

## 14. Transactions and Rollback in Spring TestContext

One advantage of Spring integration tests is the ability to run a test in a **test-managed transaction**. If a method or class has `@Transactional`, a suitable `PlatformTransactionManager` exists, and the corresponding TestContext listener is active, the framework typically starts a transaction and **rolls back after the test** by default.

The following snippet **only illustrates the annotation** and requires a real configured repository, transaction manager, and database:

```java
@SpringBootTest
@Transactional
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrderInTransactionalTest() {
        repository.save(new OrderEntity("ORDER-1"));
        assertEquals(1, repository.count());
    }
}
```

This snippet is not a standalone compilable file because `OrderRepository` and `OrderEntity` are not declared; it is not included in the runnable examples in Section 18. It illustrates the meaning of `@Transactional` in tests.

Limitations to remember:

1. **Default rollback** applies only to transactions properly managed by TestContext. Not every side effect lives inside the same transaction: HTTP servers, message brokers, files, and remote APIs do not roll back automatically.
2. With `@SpringBootTest(webEnvironment=RANDOM_PORT)` or `DEFINED_PORT`, the HTTP client and server typically run on **different threads/transactions**. Rolling back the test client's transaction does not automatically roll back transactions created by server-side requests.
3. `@BeforeEach` and `@AfterEach` typically run inside the test-managed transaction of a `@Transactional` method, whereas `@BeforeAll`/`@AfterAll` lifecycle methods do not run inside that transaction.
4. `@BeforeTransaction` and `@AfterTransaction` are available to run verification before the test transaction opens or after it ends.
5. Transactions are bound to a thread. A **preemptive timeout** such as `assertTimeoutPreemptively` can run code on another thread, causing that code not to participate in the test-managed transaction and not roll back as expected.
6. Rollback keeps test data clean, but a **rollback-only** test does not prove that production business transactions commit/roll back properly at every boundary. If you need to verify actual commit behavior, design a dedicated integration test with proper data cleanup.

**Do not overuse `@Transactional` to patch unisolated data bugs.** Understand transaction boundaries, auto-increment sequences/IDs, async workers, caches, and external resources; those can persist outside a rollback.

## 15. Different Test Types Still Share TestContext

An important point: `SpringExtension` does not force every test to use a full application context. **The type of context and which beans are loaded depend on annotations and configuration.**

| Test Type | Typical Configuration | What Is Verified |
|---|---|---|
| Plain Spring | `@SpringJUnitConfig(TestConfig.class)` | Focused beans/configuration, dependency injection |
| Full Spring Boot | `@SpringBootTest` | SpringApplication, auto-configuration, wiring/integration |
| MVC slice | `@WebMvcTest(Controller.class)` | Controllers, mappings, binding, JSON, MVC/security in the slice |
| JPA slice | `@DataJpaTest` | Repositories, JPA mappings, queries/constraints on a suitable test DB |
| Real HTTP runtime | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Requests to an embedded server and real components |
| Non-Boot Spring web context | `@SpringJUnitWebConfig(WebConfig.class)` | `WebApplicationContext` via Spring TestContext |

For example, `@WebMvcTest` and `@DataJpaTest` typically have their own bootstrap/auto-configuration setup. They still benefit from SpringExtension and context management, but do not automatically include every bean in the application. When a bean dependency is missing in a slice, consider mocking the collaborator, importing the needed configuration, or raising the integration level if the test goal truly requires it.

**Do not stack multiple slice annotations on the same test** just to "combine" MVC and JPA; choose either a single slice or a full integration test according to the behavior being verified.

## 16. Common Pitfalls When Using SpringExtension and TestContext

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| `@Autowired` field remains `null` in a JUnit test | SpringExtension is not registered or the test instance was created manually with `new` outside the JUnit lifecycle | Use `@SpringJUnitConfig`, `@ExtendWith(SpringExtension.class)`, or an appropriate Boot annotation; let JUnit manage the test |
| `NoSuchBeanDefinitionException` | Bean is not in the test context, profile does not match, or the slice excludes that bean | Check `@ContextConfiguration`, `@Import`, component scan, profiles, and slice type |
| `Unable to find a @SpringBootConfiguration` | Boot cannot locate the application root from the test's package | Place the test under an appropriate package or declare `classes=...` explicitly |
| Test loads real DB/remote services when only unit logic is needed | `@SpringBootTest` is too broad or production beans are not isolated | Use plain JUnit, a small Spring config, or an appropriate slice |
| Spring suite runs very slowly | Too many distinct context keys, JVM forks, or overly frequent `@DirtiesContext` | Inspect cache statistics, consolidate equivalent configs, reduce unnecessary context loads |
| Test does not roll back after real HTTP calls | Request and test method run on different threads/transactions | Design server-side cleanup/test data isolation; do not rely on client rollback |
| Test transaction does not roll back when using a timeout | Preemptive timeout moves code to another thread | Avoid preemptive timeouts with test-managed transactions |
| Test fails after replacing `@TestExecutionListeners` | Overwrote default listeners and lost DI/transaction hooks | Use `MERGE_WITH_DEFAULTS` when adding listeners |
| Injected Spring bean differs from expectations | Duplicate beans, `@Primary`, `@Qualifier`, or wrong active profile/test property | Check bean type/name, qualifiers, and active configuration |
| Test passes in isolation but fails in suite | Shared singleton/static/DB/cache state or order dependency | Isolate fixtures, reset state, avoid side effects, and use `@DirtiesContext` only when necessary |
| Mockito `@Mock` does not automatically replace a bean in the context | Mockito mock fields and Spring beans are in two separate scopes | Use the bean override/mocking mechanism appropriate for your Boot/Spring version when truly needed |
| Added `@ExtendWith` to `@SpringBootTest` and still getting errors | The extension was already integrated; the error lies in context/bean/configuration or test logic | Read the `ApplicationContext` root cause, dependencies/auto-configuration, and stack trace |

**When the context fails to start:** look for the **first root cause** in the `Caused by` chain. Top-level exceptions like `Failed to load ApplicationContext` only describe the outcome, not the offending bean or property. If the test has `@ActiveProfiles("test")`, inspect the profile itself and conditional beans activated by it.

## 17. Workflow for Choosing and Evaluating Tests

A practical workflow when adding a Spring Boot test:

1. **State the behavior to protect.** For example: "API returns 400 on invalid input", "bean receives configuration from test profile", "order rolls back when processing fails".
2. **Identify the observation boundary.** If it is just a calculation, write a unit test; if HTTP mapping is needed, use an MVC slice; if JPA/transactions are needed, use an integration test with the required infrastructure.
3. **Choose the smallest annotation that meets the goal.** `@SpringJUnitConfig` for small beans/configs; `@WebMvcTest` or `@DataJpaTest` for slices; `@SpringBootTest` when a broad Boot context is needed.
4. **Configure only what the test truly needs.** Use `classes`, `@Import`, and properties/profiles when justified; avoid turning every test into a unique context that cannot be cached.
5. **Keep tests independent.** Data, mutable singletons, DBs, and messages should not depend on earlier tests.
6. **Assert the contract, not just that the context loads.** A context startup smoke test has its own purpose, but features must have clear assertions on outputs, errors, or side effects.
7. **Read failure signals at the right layer.** Context errors, DI errors, transaction errors, and assertion errors have different causes.
8. **Monitor execution time and cache behavior.** A heavy context can be worth keeping if it protects a critical flow; for simple calculations, do not pay that cost.

**Analysis exercise:** A team has 50 `@SpringBootTest` tests, each testing only a pricing calculation method on a `@Service` with no I/O; CI is slow. A sensible improvement is to rewrite most cases as plain Java unit tests while keeping a few targeted integration tests to protect Spring wiring and configuration. Deleting every context-startup test without preserving coverage for important bean/config wiring could introduce a new blind spot.

## 18. Running the Two Example Sets and Reading the Results

The examples above target **Java 17+**, Spring Boot **3.3.x**, and JUnit Jupiter **5**. If the project already manages dependencies via the Spring Boot plugin/BOM, you can declare in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` pulls in the required test libraries, including `spring-test` and JUnit Jupiter in the Boot 3.3 ecosystem. Do not add duplicate dependencies if the current module already declares them.

**List of main runnable files:**

```text
src/main/java/com/example/testcontext/plain/GreetingService.java
src/test/java/com/example/testcontext/plain/GreetingTestConfig.java
src/test/java/com/example/testcontext/plain/GreetingSpringTest.java

src/main/java/com/example/testcontext/boot/TestContextDemoApplication.java
src/main/java/com/example/testcontext/boot/ShippingPolicy.java
src/test/java/com/example/testcontext/boot/ShippingPolicyContextTest.java
```

`TestNameListener.java` in Section 13 is an optional listener example and is not required to run the two test sets. Snippets marked **illustrative/not standalone** should not be copied as separate runnable Java files.

Run from the directory containing the Gradle wrapper and `test` project:

```bash
./gradlew test --tests com.example.testcontext.plain.GreetingSpringTest --tests com.example.testcontext.boot.ShippingPolicyContextTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.testcontext.plain.GreetingSpringTest --tests com.example.testcontext.boot.ShippingPolicyContextTest
```

In a multi-project build, replace `test` with `:module-name:test` matching the module containing the files; do not use an example module name if the real project does not have one.

**Designed outcomes:**

- `GreetingSpringTest.createsBeanFromConfigurationAndProperties` returns `"Xin chào, Mai!"`.
- `GreetingSpringTest.injectsTheSameSingletonBeanFromContext` confirms the field and `ApplicationContext` reference the same bean.
- `GreetingSpringTest.rejectsBlankName` catches `IllegalArgumentException`.
- `ShippingPolicyContextTest` receives an injected `ShippingPolicy`; for 199 standard shipping the fee is 15, 200 standard is 0, 200 express is 30; negative values throw `IllegalArgumentException`.
- When the project and dependencies are configured correctly, Gradle is expected to print `BUILD SUCCESSFUL`. This is **expected from the example code**, not a claim that the tests have been executed on a specific workspace.

Because the examples use JUnit tests and contain no `System.out.println` in the main test classes, there is **no fixed business stdout** to compare against. You can view the Gradle report at `build/reports/tests/test/index.html` or XML test results at `build/test-results/test/` in the module.

## 19. Self-Check and Review Questions

### Question 1: Why doesn't `@Autowired` work in a regular JUnit test?

If a test only has `@Test` without SpringExtension or a Boot test annotation, Spring TestContext does not participate to prepare the instance and inject fields. You need to register the appropriate extension and configure the context; or skip Spring and pass dependencies directly via constructor if you only need a unit test.

### Question 2: Is `SpringExtension` a Spring container?

No. SpringExtension is a **JUnit Jupiter extension**. The Spring container is `ApplicationContext`; `TestContextManager` and listeners orchestrate the lifecycle and context for tests.

### Question 3: How do `@SpringJUnitConfig` and `@SpringBootTest` differ?

`@SpringJUnitConfig` is a composed annotation of `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration`, useful for building a narrowly scoped Spring context. `@SpringBootTest` uses Spring Boot's bootstrap mechanism (`SpringApplication`, auto-configuration, app configuration, `webEnvironment` when requested) and already integrates SpringExtension.

### Question 4: Why can two tests that both use `@SpringBootTest` still pay for loading two contexts?

Because the cache key also depends on profiles, properties, configuration classes, context customizers, and other factors. If they differ, they may get two separate contexts; if `@DirtiesContext` or separate JVM forks are used, the context will not be shared as expected either.

### Question 5: When is a custom `TestExecutionListener` needed?

When there is a clear requirement at lifecycle points that standard annotations or fixtures do not cover. Understand and preserve the default listeners, use `MERGE_WITH_DEFAULTS` when adding one, and avoid using a listener to implicitly mutate business data.

### Question 6: Can you trust that all DB changes in `@SpringBootTest(RANDOM_PORT)` roll back thanks to `@Transactional` on the test client?

No. The test client and the HTTP server run on different threads and transactions. You need an appropriate server-side data and cleanup strategy.

### Question 7: Does `@DirtiesContext` make every test completely independent?

No. It controls the **context cache** lifecycle; it does not automatically revert external databases, files, sockets, messages, or static state outside the context. Use it when the context itself is genuinely dirtied, while managing other resources separately.

## 20. Practical Checklist

- [ ] I know clearly **which behavior** needs a Spring context to be verified.
- [ ] I distinguish `TestContext` (metadata/lifecycle) from `ApplicationContext` (bean container).
- [ ] I know that `SpringExtension` registers with JUnit Jupiter and forwards callbacks to TestContextManager.
- [ ] For plain Spring, I use `@SpringJUnitConfig` or `@ExtendWith` + `@ContextConfiguration` explicitly.
- [ ] With Spring Boot test annotations that already integrate the extension, I do not add redundant annotations.
- [ ] I declare context/profile/property settings and beans properly so test injection succeeds.
- [ ] I understand which listener hooks correspond to `@BeforeEach`, `@Test`, and `@AfterEach`.
- [ ] I do not lose default listeners when adding a custom listener.
- [ ] I know when `@Transactional` can roll back and when HTTP/async/threads create a different boundary.
- [ ] I keep the cache effective, avoid unnecessary distinct contexts, and only use `@DirtiesContext` with good reason.
- [ ] I choose the right test level—unit, Spring config, slice, or full Boot—instead of always starting the entire application.
- [ ] I read the root cause of context/bean errors and verify contracts with concrete assertions.

**Key takeaway:** The Spring TestContext Framework is the foundation for managing Spring test contexts and lifecycles; `SpringExtension` is the adapter that lets **JUnit Jupiter** use that foundation. Understanding the boundaries between the extension, TestContextManager, listeners, and ApplicationContext helps you write Spring Boot tests that are accurate, well-isolated, and free of unnecessary startup overhead.

### References

- Spring Framework 6.2 — TestContext Framework Support Classes: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/support-classes.html
- Spring Framework — Key Abstractions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/key-abstractions.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Test-managed Transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
