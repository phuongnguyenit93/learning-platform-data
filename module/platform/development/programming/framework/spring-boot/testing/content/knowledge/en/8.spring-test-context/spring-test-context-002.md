# Spring TestContext: ApplicationContext Initialization, Dependency Injection, and Test Execution

## 1. Objectives

In plain Java, a unit test can instantiate objects with `new`, pass fakes/mocks, and check the result. However, when you need to verify whether Spring reads configuration, creates beans, injects dependencies, selects profiles, and wires components properly, the test must run with the **Spring TestContext Framework**.

This lesson explains the full path from **JUnit Jupiter discovering and running a test**, to **Spring building or reusing an `ApplicationContext`**, **injecting dependencies into the test instance**, invoking callbacks, and closing transactions or cleaning up data at the right boundaries.

After this lesson, you should be able to:

- Distinguish between `JUnit Jupiter`, `SpringExtension`, `TestContextManager`, `TestContext`, `TestExecutionListener`, `ContextLoader`, and `ApplicationContext`.
- Choose the right `@SpringJUnitConfig`, `@ContextConfiguration` + `@ExtendWith(SpringExtension.class)`, `@SpringBootTest`, or test slice when needed.
- Explain when the context is created, how the cache key is formed, and why two test classes can share singleton beans.
- Use `@Autowired` on fields, constructors, or method parameters and debug injection errors.
- Understand the relative order of `@BeforeEach`, `@Test`, Spring callbacks, transactions, and cleanup.
- Write runnable Java 17+ tests and know the scope of evidence provided by each test type.

## 2. Two Different Lifecycles: Test Instance and Spring Context

A test instance and a Spring bean **are not the same thing**.

JUnit Jupiter is responsible for creating and running the test object, typically creating a new instance per test method under the default `PER_METHOD` mode. Spring manages beans inside an `ApplicationContext`, usually holding shared singletons. Spring TestContext connects the two sides so that the JUnit test instance receives Spring beans.

```text
Gradle / Maven / IDE
        |
        v
JUnit Platform -> Jupiter TestEngine
        |
        v
JUnit test instance + @Test methods
        |
        | SpringExtension (JUnit extension)
        v
TestContextManager
        |
        +--> TestContext / context configuration
        |        |
        |        +--> ContextCache (cache hit?)
        |                  |
        |                if not cached
        |                  v
        |           ContextLoader
        |                  |
        |                  v
        |           ApplicationContext
        |             |     |     |
        |          @Bean  @Service  repository...
        |
        +--> TestExecutionListeners
                 |
                 +--> Dependency injection
                 +--> Transaction (if any)
                 +--> SQL scripts (if any)
                 +--> DirtiesContext (if marked)
        |
        v
@BeforeEach -> @Test -> @AfterEach
        |
        v
Assertions + result reporting to JUnit
```

| Component | Role | What Not to Confuse It With |
| --- | --- | --- |
| **JUnit Platform/Jupiter** | Discovers and runs `@Test`, lifecycle, and assertions | Does not instantiate Spring beans on its own |
| **`SpringExtension`** | Bridges JUnit Jupiter with Spring TestContext, providing callbacks and parameters | Not an IoC container |
| **`TestContextManager`** | Manages test state and dispatches events at lifecycle milestones | Not a business service |
| **`TestContext`** | Holds the class, method, instance, configuration context, and access to the context | Does not mean every method gets its own context |
| **`TestExecutionListener`** | Performs dependency injection, transactions, SQL, and other tasks | Not an HTTP filter or application event listener |
| **`ContextLoader` / `SmartContextLoader`** | Creates the context based on the chosen configuration | Does not automatically guarantee Spring Boot features |
| **`ApplicationContext`** | Container that creates and supplies beans along with configuration | Not the test object created by JUnit |
| **`ContextCache`** | Reuses contexts by cache key | Does not reset mutable state inside singletons |

**Example:** JUnit creates two separate instances of `AccountServiceTest` to run two `@Test` methods; both can still be injected with the same singleton `AccountService` bean from a cached Spring context. Therefore, you cannot infer "a new test instance means fresh bean data."

## 3. Choosing the Right Level of Context Loading

| What Needs to Be Verified | Test Level to Choose | Spring Context |
| --- | --- | --- |
| Pricing rules, data transformations | JUnit, `new` object | No |
| Service calling a gateway with the right inputs | JUnit + Mockito/fake | No |
| A few `@Configuration`/`@Bean` beans | `@SpringJUnitConfig` | Small context |
| Spring Boot auto-configuration, profiles, bean wiring | `@SpringBootTest` | Boot context |
| HTTP mappings/JSON alone | `@WebMvcTest` | MVC slice |
| JPA mappings/repositories | `@DataJpaTest` | Persistence slice |
| Controller → service → DB | `@SpringBootTest` + HTTP/DB tooling | Integration context |
| Real HTTP server on a random port | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Boot + server |

A larger context has more points of failure: datasources, external beans, secrets, migrations, or HTTP ports. **Only use a context when Spring's behavior is the subject under verification.**

## 4. Three Ways to Declare Spring TestContext

### 4.1. Explicit Form: `@ExtendWith` and `@ContextConfiguration`

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class ExampleContextTest {
    @Autowired
    GreetingService service;

    @Test
    void testGreeting() {
        // assert the result from the bean in the context.
    }
}
```

This is an **illustrative snippet**, requiring `TestConfig` and `GreetingService` to exist. `@ExtendWith(SpringExtension.class)` registers Spring with JUnit Jupiter. `@ContextConfiguration` specifies context configuration sources such as Java `@Configuration` classes, XML/resource locations, and other attributes.

**Having `@ContextConfiguration` alone without SpringExtension or a corresponding composed annotation does not integrate Spring DI with JUnit Jupiter.** `@Autowired` test fields may remain null.

### 4.2. Shorter Form: `@SpringJUnitConfig`

```java
@SpringJUnitConfig(classes = TestConfig.class)
class ExampleContextTest {
    @Autowired
    GreetingService service;
}
```

`@SpringJUnitConfig` combines the functionality of `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`, convenient when you need a **small, explicitly configured Spring context**. It does not automatically enable Spring Boot auto-configuration like `@SpringBootTest`.

### 4.3. Loading Spring Boot: `@SpringBootTest`

```java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ExampleBootTest {
    @Autowired
    GreetingService service;
}
```

`@SpringBootTest` uses Spring Boot's bootstrap mechanism, creating the context via `SpringApplication` to integrate Boot configuration, auto-configuration, properties, and matching profiles. This annotation already registers SpringExtension for JUnit Jupiter; there is no need to add `@ExtendWith(SpringExtension.class)` again.

`webEnvironment`:

- `MOCK` (default): builds a mock web environment if a web stack is on the classpath; **does not open a real HTTP server**.
- `RANDOM_PORT`: starts an HTTP server on a random port, suitable for real HTTP testing.
- `DEFINED_PORT`: starts a server on the configured or default port when a web environment is present.
- `NONE`: loads the context without creating a web environment.

If you need MockMvc for an MVC integration test, you can combine `@SpringBootTest` with `@AutoConfigureMockMvc`; do not assume `@SpringBootTest` automatically starts a server.

### 4.4. Which Annotation Should You Put on a Test?

| Annotation | Registers SpringExtension? | Chooses How Context Is Loaded |
| --- | --- | --- |
| `@Test` | No | JUnit only |
| `@ContextConfiguration` | Does not register extension by itself | Specified Spring config |
| `@SpringJUnitConfig` | Yes | Specified Spring config |
| `@SpringBootTest` | Yes | Spring Boot application context |
| `@WebMvcTest` | Yes in Boot test slice | Relevant MVC beans |
| `@DataJpaTest` | Yes in Boot test slice | Relevant persistence/JPA beans |

Do not treat an annotation as a "magic spell" to turn tests green. For example, `@WebMvcTest` intentionally does not load all real services, so a dependency needs mocking or test configuration fitting the slice boundary.

## 5. What Exactly Happens When Creating an `ApplicationContext`?

Test annotations describe configuration; **they do not guarantee that every bean already exists the moment JUnit discovers the class**. The context is loaded when the test infrastructure actually needs to access it. Constructor injection may trigger it earlier than field injection; a listener can also request the context before `@Test` starts.

Functional workflow:

1. **Discovery:** JUnit Jupiter inspects the test class, `@Test` methods, and extensions/annotations.
2. **TestContext Bootstrap:** `SpringExtension` coordinates with `TestContextManager`; Spring merges configurations such as classes, profiles, properties, loaders, context customizers, and parent contexts.
3. **Cache Lookup:** Spring uses the merged configuration as a cache key. If a valid context is cached, it can be reused.
4. **Load Context on Miss:** The context loader creates an `ApplicationContext`; with `@SpringBootTest`, Boot's bootstrap uses `SpringApplication`.
5. **Prepare Bean Definitions:** `@Configuration`/`@Bean`, component scanning, imports, conditional configuration, profiles, and properties are processed according to active configuration.
6. **Refresh Context:** Spring runs post-processors, instantiates non-lazy singletons, resolves dependencies, performs constructor/field injection for beans, and runs appropriate init callbacks.
7. **Inject Test Fixture:** The DI listener injects fields/setters on the test instance; `SpringExtension` resolves constructor/test-method/lifecycle parameters via JUnit `ParameterResolver`.
8. **Execute Test:** JUnit and Spring listeners invoke before/after test method hooks, keeping the context in cache while still valid.

This is a **responsibility model**, not a strict log of every internal call. Detailed ordering can vary by injection mode, listeners, and Framework version.

### Difference Between "Bean Created" and "Bean Injected into Test"

A bean may already be created by Spring because it is a singleton in the context, yet the test does not receive it if `@Autowired` was forgotten on the field or the extension/DI listener is inactive. Conversely, a mock created with `Mockito.mock` and passed via `new Service(mock)` can make a unit test pass **without proving at all** that Spring knows how to create or inject that service.

A `contextLoads()` test is valuable for catching bootstrap failures; it does not replace business assertions.

## 6. Runnable Example with Java 17, Spring Boot 3.3.0, and JUnit Jupiter

The example pins **Spring Boot 3.3.0** so imports and configuration align to the same version. This is a mechanics lesson, not a recommendation to pin an old version in production apps. When applying this to real projects, use your project's supported BOM, wrapper, and releases.

A small app has a service that greets users. A formatter bean reads `lesson.prefix` from application properties. The `test` profile changes "Hello" to "Hi". Four tests demonstrate plain JUnit, a small Spring context, a Boot context, and constructor injection.

### 6.1. Structure

```text
testcontext-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── DemoApplication.java
    │   │   ├── GreetingFormatter.java
    │   │   ├── GreetingService.java
    │   │   └── GreetingConfiguration.java
    │   └── resources/application.properties
    └── test/
        ├── java/example/
        │   ├── GreetingServiceUnitTest.java
        │   ├── GreetingSmallContextTest.java
        │   ├── GreetingBootContextTest.java
        │   └── GreetingConstructorTest.java
        └── resources/application-test.properties
```

### 6.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'testcontext-demo'
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

This is a build for a standalone example, requiring a valid Gradle wrapper and repository access to download dependencies. There is no Spring Web or database; therefore `@SpringBootTest(webEnvironment=NONE)` suffices for the goal.

### 6.3. Production Code

**`src/main/java/example/DemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**`src/main/java/example/GreetingFormatter.java`:**

```java
package example;

public record GreetingFormatter(String prefix) {
    public String format(String name) {
        return prefix + ", " + name + "!";
    }
}
```

**`src/main/java/example/GreetingService.java`:**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return formatter.format(name);
    }
}
```

**`src/main/java/example/GreetingConfiguration.java`:**

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {
    @Bean
    GreetingFormatter greetingFormatter(
            @Value("${lesson.prefix:Hello}") String prefix) {
        return new GreetingFormatter(prefix);
    }
}
```

**`src/main/resources/application.properties`:**

```properties
lesson.prefix=Hello
```

**`src/test/resources/application-test.properties`:**

```properties
lesson.prefix=Hi
```

Mechanism: `@SpringBootApplication` in the `example` package sets up Boot configuration and scans `GreetingService`/`GreetingConfiguration`. `@Bean` creates the formatter, `@Value` reads `lesson.prefix`, and the service receives the formatter via constructor injection. Under the `test` profile, Boot reads that profile's properties and replies `"Hi, ..."`.

### 6.4. Test A — Plain JUnit, No Spring

**`src/test/java/example/GreetingServiceUnitTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceUnitTest {
    @Test
    void verifiesJavaLogicWithoutContext() {
        var service =
                new GreetingService(new GreetingFormatter("Hello"));

        assertEquals("Hello, Mai!", service.greet("Mai"));
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(" "));
    }
}
```

JUnit creates the test instance itself. The test explicitly creates the service and formatter using `new`. It proves Java logic, **not** that Spring created the beans or read properties.

### 6.5. Test B — Small Spring Context, Only Two Beans

**`src/test/java/example/GreetingSmallContextTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(classes = GreetingSmallContextTest.TestConfig.class)
class GreetingSmallContextTest {
    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        GreetingFormatter formatter() {
            return new GreetingFormatter("Bonjour");
        }

        @Bean
        GreetingService greetingService(GreetingFormatter formatter) {
            return new GreetingService(formatter);
        }
    }

    @Autowired
    GreetingService service;

    @Test
    void injectsBeanFromExplicitConfiguration() {
        assertNotNull(service);
        assertEquals("Bonjour, Mai!", service.greet("Mai"));
    }
}
```

Here TestContext creates a small `ApplicationContext` from `TestConfig`; two beans are declared explicitly. There is no component scan of `DemoApplication` and no Spring Boot `SpringApplication`. The `Bonjour` prefix proves the test uses the formatter from the small context.

### 6.6. Test C — Boot Context + Field Injection + Method Injection

**`src/test/java/example/GreetingBootContextTest.java`:**

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
class GreetingBootContextTest {
    @Autowired
    GreetingService service;

    @Autowired
    ApplicationContext context;

    @BeforeEach
    void injectedBeforeSetupRuns() {
        assertNotNull(service);
        assertNotNull(context);
    }

    @Test
    void resolvesBeanAndProfileProperty() {
        assertEquals("Hi, Mai!", service.greet("Mai"));
        assertSame(context.getBean(GreetingService.class), service);
    }

    @Test
    void injectsTestMethodParameter(
            @Autowired GreetingService parameterService) {
        assertSame(service, parameterService);
        assertEquals("Hi, An!", parameterService.greet("An"));
    }
}
```

Meaning:

- `@SpringBootTest` uses Boot bootstrapping and `@ActiveProfiles("test")` selects the `Hi` prefix.
- `DependencyInjectionTestExecutionListener` injects fields into the test instance before JUnit invokes `@BeforeEach`.
- `SpringExtension` acts as a `ParameterResolver`, supplying the `@Autowired GreetingService` method parameter.
- `assertSame` is appropriate because `GreetingService` is a singleton by default; for scoped/proxied beans, identity checks must reflect the bean's contract.
- The context loaded successfully and returned the expected greeting; however, since there is no HTTP or database, the test does not prove those.

### 6.7. Test D — Constructor Injection for a JUnit Test Instance

**`src/test/java/example/GreetingConstructorTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestConstructor;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class GreetingConstructorTest {
    private final GreetingService service;

    GreetingConstructorTest(GreetingService service) {
        this.service = service;
    }

    @Test
    void receivesBeanThroughConstructor() {
        assertEquals("Hi, Linh!", service.greet("Linh"));
    }
}
```

`@TestConstructor(autowireMode=ALL)` instructs Spring to supply the constructor parameters of the test instance. Alternatively, you can annotate the constructor directly with `@Autowired` when you want the entire constructor autowired. Without any annotation, JUnit does not know how to resolve `GreetingService` by default unless the global autowire mode has been changed.

### 6.8. Running with the Wrapper

```bash
./gradlew test
./gradlew test --tests example.GreetingServiceUnitTest
./gradlew test --tests example.GreetingSmallContextTest
./gradlew test --tests example.GreetingBootContextTest
./gradlew test --tests example.GreetingConstructorTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.GreetingBootContextTest
```

The expected result is **5 passing test executions**: A = 1, B = 1, C = 2, D = 1. There is no fixed business stdout; the build tool prints `BUILD SUCCESSFUL` when all tests pass and no other task errors occur. Do not invoke `javac` directly for tests without providing the full JUnit/Spring test classpath; Gradle is the more reliable approach in this example.

Boot test classes C and D have equivalent configurations, so they **can reuse the same context** when run in the same JVM while the cache remains valid. Class B's small context has a different configuration, so it gets its own context.

## 7. How Do Field, Constructor, and Parameter Injection Differ?

### 7.1. Field Injection into the Test Object

```java
@Autowired
GreetingService service;
```

JUnit instantiates the test instance, Spring TestContext prepares the instance via the default DI listener, and injects the field before the test needs it. Suitable for short tests. If SpringExtension is missing or a bean is absent, the field may be null or the context fails before the test runs.

### 7.2. Constructor Injection

```java
@Autowired
MyTest(GreetingService service) {
    this.service = service;
}
```

This is a **syntax fragment**, requiring an actual field and context. With a constructor marked `@Autowired`, SpringExtension resolves all constructor parameters. `@TestConstructor(autowireMode=ALL)` is another option. Injection occurs when JUnit creates the test instance, so it can trigger context loading early.

**Specifically:** if you combine JUnit `@TestInstance(PER_CLASS)` with `@DirtiesContext` closing the context before/after each method, constructor-injected bean references may still point to beans from the closed context. Avoid this combination or use appropriate field/setter injection so Spring can reinject.

### 7.3. Injecting into `@Test` or `@BeforeEach`

```java
@Test
void checksService(@Autowired GreetingService service) {
    assertEquals("Hi, Mai!", service.greet("Mai"));
}

@BeforeEach
void hasContext(@Autowired ApplicationContext context) {
    assertNotNull(context);
}
```

This snippet must be placed in a test class integrated with SpringExtension and the `test` profile as in the example. `SpringExtension` implements Jupiter's `ParameterResolver`; parameters like `ApplicationContext` can be recognized by type, while application beans should use `@Autowired`/`@Qualifier` to be explicit.

Properties can also be injected:

```java
@Test
void readsProperty(@Value("${lesson.prefix}") String prefix) {
    assertEquals("Hi", prefix);
}
```

You must import `org.springframework.beans.factory.annotation.Value` and have a context with the corresponding property. `@Value` on a parameter is a way to pass configuration into a test method, not a replacement for assertions.

### 7.4. When Multiple Beans Share the Same Type

If the context has two `PaymentGateway` beans, `@Autowired PaymentGateway gateway` can lead to `NoUniqueBeanDefinitionException`. Use `@Qualifier("gatewayName")`, a sensibly `@Primary` bean, or load a context containing only the exact implementation the test needs. Do not alter production configuration arbitrarily just to make a single test pass.

## 8. Execution Order of JUnit and Spring Listeners

There are at least three types of milestones: JUnit lifecycle methods (`@BeforeAll`, `@BeforeEach`…), Jupiter extension callbacks (`beforeEach`, `beforeTestExecution`…), and `TestContextManager` events for Spring listeners.

Diagram of the **general order**:

```text
JUnit discovery / register SpringExtension
  |
  +--> SpringExtension.beforeAll
  |      -> TestContextManager.beforeTestClass
  +--> JUnit @BeforeAll
  |
  +--> Create test instance
  |      -> constructor injection if declared
  +--> SpringExtension.postProcessTestInstance
  |      -> TestContextManager.prepareTestInstance
  |      -> DependencyInjectionTestExecutionListener
  |
  +--> SpringExtension.beforeEach
  |      -> TestContextManager.beforeTestMethod
  |      -> listener may open transaction
  +--> JUnit @BeforeEach
  +--> SpringExtension.beforeTestExecution
  |      -> TestContextManager.beforeTestExecution
  +--> JUnit @Test
  +--> SpringExtension.afterTestExecution
  |      -> TestContextManager.afterTestExecution
  +--> JUnit @AfterEach
  +--> SpringExtension.afterEach
  |      -> TestContextManager.afterTestMethod
  |      -> listener may roll back transaction
  |
  +--> JUnit @AfterAll
  +--> SpringExtension.afterAll
         -> TestContextManager.afterTestClass
```

This is a lifecycle map, not a guarantee of absolute ordering across **all listeners/extensions** when a test has multiple extensions. Listeners have their own ordering; the context may be created at an earlier milestone when the framework requires it. Key takeaways for writing tests:

- Field injection into the test instance usually completes before `@BeforeEach`.
- `@BeforeEach` prepares per-method fixtures; `@AfterEach` cleans up appropriate fixtures.
- `beforeTestMethod` differs from `beforeTestExecution`: the second callback sits right before `@Test` code executes.
- Context creation errors can surface **before the Act step or assertions inside `@Test` execute**.

### 8.1. Common Default Listeners

`DependencyInjectionTestExecutionListener` handles field/setter injection; `TransactionalTestExecutionListener` handles test transactions; `SqlScriptsTestExecutionListener` supports `@Sql`; listeners related to `@DirtiesContext` mark, evict, or close contexts across the lifecycle.

When adding a custom listener via `@TestExecutionListeners`, understand **how merging with default listeners works**. Accidentally overwriting all default listeners can make working DI, transactions, or SQL support disappear.

## 9. Context Caching and Singleton Sharing

Spring TestContext maintains a **static** context cache **within the test JVM**. From the merged configuration, Spring computes a cache key; two tests with compatible configurations can share a single `ApplicationContext` instead of reloading it.

The cache key is affected by components such as:

- `classes` and `locations` of the context configuration.
- Active profiles from `@ActiveProfiles`.
- Property sources or inline properties.
- Initializers, context loader, parent context.
- Context customizers, such as mock/bean overrides or dynamic properties.
- Web resource base path when a web context is used.

```text
BootContextTest:
    classes=DemoApplication, profile=test, web=NONE
                          |
                          +--> context A

ConstructorTest:
    classes=DemoApplication, profile=test, web=NONE
                          |
                          +--> can reuse context A

StagingProfileTest:
    classes=DemoApplication, profile=staging, web=NONE
                          |
                          +--> context B (different key)
```

Do not deduce "one context per test class" or "one context for the entire suite." Different `@SpringBootTest(properties=...)`, different mock sets, `@DirtiesContext`, or different Gradle forks/processes can cause tests to load multiple contexts.

### 9.1. Caching Does Not Clear State Inside Singletons

If a singleton bean holds a mutable `Map`, one test may modify it and a subsequent test sees the same data when the context is cached. You must reset state via proper fixtures, design stateless beans, or isolate databases/transactions. `@DirtiesContext` is only an option when you genuinely need to evict/recreate the context, not a default data-cleanup mechanism.

### 9.2. `@DirtiesContext`

```java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutatingIT {
    // Test with a genuine reason to close the context after the class.
}
```

This is an **illustrative pattern**, requiring Spring test annotations/imports and a real test context. `@DirtiesContext` makes Spring remove the context from the cache at the specified milestone; subsequent tests may have to bootstrap again. Overusing it slows down the suite and sometimes masks real state leakage issues.

### 9.3. Context Failure Threshold

Since Spring Framework 6.1, TestContext has a **context failure threshold** defaulting to 1 per cache key. If loading a context has already failed, repeated attempts with the same key can be skipped early with a threshold message. When reading suite logs, look for the **first root context-load error**, not just "preemptively skipped" messages.

You can configure `spring.test.context.failure.threshold` per the framework documentation, though raising the threshold does not fix broken beans, profiles, or dependencies.

## 10. Profiles, Properties, and Test Configuration

### 10.1. `@ActiveProfiles`

`@ActiveProfiles("test")` activates the `test` profile; with Spring Boot, it allows the example's `application-test.properties` to be used. Profiles only select configuration—**they do not automatically guarantee** every external service or database is isolated from production.

### 10.2. `@TestPropertySource`

Example adding a separate test class for overrides:

```java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@TestPropertySource(properties = "lesson.prefix=Salut")
class OverridePropertyTest {
    @Autowired GreetingService service;

    @Test
    void usesCustomProperty() {
        assertEquals("Salut, Mai!", service.greet("Mai"));
    }
}
```

This is an **abbreviated example** needing JUnit and Spring imports and is not among the four runnable tests in Section 6. Besides `@TestPropertySource`, `@SpringBootTest(properties=...)` also supports inline test properties. These values can alter the cache key; do not change properties per test arbitrarily unless needed.

### 10.3. `@TestConfiguration`, `@Import`, Test Doubles

Spring Boot provides `@TestConfiguration` to declare test-supporting beans. It can be imported with `@Import` or nested inside a test class per Boot conventions. Do not assume declaring the same bean name automatically replaces a production bean: depending on configuration, bean overriding may be rejected.

When you need to replace a collaborator with a mock inside a Spring context, use the bean override mechanism matching your version: Spring Boot 3.3 commonly has `@MockBean`; Spring Framework 6.2 introduced `@MockitoBean`, and moving to Boot 4 requires updating the corresponding test packages/modules. Mockito mocks for unit tests can use `mock(...)` directly without Spring TestContext.

## 11. Test Transactions and Rollback

**`@SpringBootTest` does not automatically roll back every test.** Spring TestContext supports test-managed transactions for tests marked `@Transactional` when an appropriate transaction manager exists; by default, that transaction rolls back after the test.

```java
@SpringBootTest
@Transactional
class AccountRepositoryIT {
    @Autowired
    AccountRepository repository;

    @Test
    void changesAreRolledBackByTestTransaction() {
        // Call repository, assert data inside the test transaction.
        // Rolls back by default after the test method.
    }
}
```

This is a **skeleton**, requiring an application with JPA/database/repository/transaction manager and imports. It will not run in the Greeting project from Section 6 because that example has no database.

Boundaries to remember:

- In a transactional test, `@BeforeEach` and `@AfterEach` normally run inside the test-managed transaction.
- `@BeforeAll` and `@AfterAll` do not run inside each method's transaction.
- `@BeforeTransaction` and `@AfterTransaction` are Spring hooks that run outside the test transaction when applied.
- `@Commit` or `@Rollback(false)` intentionally alters the default rollback behavior.
- With `@SpringBootTest(webEnvironment=RANDOM_PORT)`, the HTTP server executes on a different thread/transaction; rolling back the test thread **does not roll back** transactions committed by the server.
- JUnit's `assertTimeoutPreemptively(...)` can run code on another thread, breaking thread-bound transaction boundaries; do not use it casually when relying on rollback.

**Context lifecycle differs from transaction lifecycle:** a context can be shared across many tests, whereas a test transaction typically opens and closes per method. Closing the context is not a substitute for rollback.

## 12. Debugging Context Loading or Dependency Injection Errors

### 12.1. `@Autowired` Is Still Null

Common causes are using plain JUnit without integrating SpringExtension, or instantiating the test object manually with `new` outside JUnit. Check the test class annotations and DI listener. If the test only needs service logic, constructing the service with `new` and dropping field injection makes sense; if real beans are needed, use a proper context test.

### 12.2. `Unable to find a @SpringBootConfiguration`

Boot could not locate a `@SpringBootApplication` class from the test's package location using configuration search. Place the test in an appropriate package or specify `@SpringBootTest(classes=DemoApplication.class)`; do not broaden component scanning recklessly.

### 12.3. `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`

Possible causes include a missing bean dependency, wrong profile, missing `@Bean`, component scan not covering the package, unmet conditional config, or a test slice excluding that bean. Find the first bean that could not be created and compare it with the loaded context scope. A `@SpringJUnitConfig` containing only a formatter will not create the service unless the service is registered via `@Bean` or component scan.

### 12.4. `NoUniqueBeanDefinitionException`

There are multiple beans of the same type and Spring cannot choose one. Use `@Qualifier`, `@Primary`, or an appropriately scoped small test configuration. Do not alter production wiring arbitrarily when the test simply needs an explicit choice.

### 12.5. `No ParameterResolver registered for parameter ...`

JUnit does not know how to supply a constructor or method parameter. Check whether `SpringExtension` is registered, whether `@Autowired` or `@TestConstructor(ALL)` is present, and whether Spring can resolve that parameter type from the context. For test class constructors, the annotation/autowiring strategy matters just as much as the bean existing.

### 12.6. Datasource/Secret/Client Errors During Context Creation

A bean may require a DB URL, credentials, or a network call during initialization. The failure occurs **before `@Test`**, not at an assertion. Check active profiles/test properties, external dependencies, and how mocks or test configurations are supplied. Never let tests point to a production database as a "quick fix."

### 12.7. Mapping Symptoms to the Right Layer

| Symptom | Where to Investigate |
| --- | --- |
| `No tests found` | JUnit Platform/engine, `@Test` import, filter/build task |
| `Failed to load ApplicationContext` | Bean graph, profiles, properties, context loader, external resources |
| `No ParameterResolver` | SpringExtension, constructor injection mode, parameter annotation |
| `@Autowired` field is null | Test instance was not prepared by Spring TestContext |
| Multiple beans of same type | `@Qualifier`, `@Primary`, test configuration |
| Test fails with "ApplicationContext failure threshold exceeded" | First context-load failure sharing the same cache key |
| Context loads green but behavior is wrong | Missing assertions or buggy business code |
| Suite reloads contexts repeatedly | Different cache keys, `@DirtiesContext`, separate JVM forks/processes |
| DB does not roll back | Missing test transaction or request executing outside that thread/transaction |

## 13. Observing and Verifying That a Test Loaded the Right Bean

In the Boot test from Section 6:

```java
@Autowired
ApplicationContext context;

@Autowired
GreetingService service;

@Test
void verifiesManagedBean() {
    assertNotNull(context);
    assertSame(context.getBean(GreetingService.class), service);
    assertEquals("Hi, Mai!", service.greet("Mai"));
}
```

This snippet must reside in a class configured with `@SpringBootTest` and the `test` profile, with JUnit imports. The test verifies that the bean is present, is the same singleton instance, and behaves as expected. `assertNotNull(context)` alone is insufficient, because a context can load successfully while still missing the target bean or logic.

When a test is slow or fails, run the single test via the wrapper:

```bash
./gradlew test --tests example.GreetingBootContextTest
./gradlew test --info
```

Inspect task/test reports and the **root error stack trace**. If you need context cache logs, enable DEBUG level for Spring TestContext's cache component in test logging config; do not print the entire `Environment`, as it may contain secrets.

## 14. Sequential Hands-On Exercises

**Exercise 1 — JUnit without Spring.** Run `GreetingServiceUnitTest`, then temporarily break `GreetingFormatter.format` (remove the exclamation mark). The assertion must fail. Restore the code. Explain why this proves logic but not wiring.

**Exercise 2 — Small Spring context.** Run `GreetingSmallContextTest`. Change the formatter from `Bonjour` to `Salut` and update the assertion. List the two beans declared by `TestConfig`. Why doesn't `application-test.properties` affect this test?

**Exercise 3 — Profiles and Boot properties.** Run `GreetingBootContextTest`, change `lesson.prefix=Hi` to `Hello-Test` in `application-test.properties`. The test passes once the expected value is updated to match the contract. Try removing `@ActiveProfiles("test")` on a test branch: the value will follow another configuration. Restore it.

**Exercise 4 — Injection timing.** Run `GreetingConstructorTest`, try removing `@TestConstructor(autowireMode=ALL)` to observe the constructor resolution failure (under default settings). Re-add it; describe when JUnit instantiates the test instance and when field injection completes.

**Exercise 5 — Cache vs. test state.** Create a singleton in-memory counter for a practice exercise. Have two test methods share the same context and mutate the counter. Point out why state can leak across tests; find a fixture-reset solution instead of defaulting to `@DirtiesContext`.

**Exercise 6 — Error diagnosis.** Given a failing test, before fixing it, classify it: runner did not find the test, missing resolver, Boot config not found, missing bean, external dependency error, or wrong business assertion. Record evidence from the root error and make the smallest required change.

## 15. Checklist Before Marking Complete

- [ ] The test has a clear goal: Java logic, bean wiring, Boot auto-configuration, adapter, or full flow.
- [ ] I chose the smallest context scope that still proves the behavior.
- [ ] I know which annotation registers SpringExtension for Jupiter.
- [ ] I distinguish a JUnit test instance from a Spring singleton bean.
- [ ] I know the actual test configuration classes, profiles, and properties.
- [ ] I know how field injection, constructor injection, and method parameter injection occur.
- [ ] Test fixtures are injected before `@BeforeEach`/`@Test` uses them.
- [ ] I do not assume every method gets a brand-new context.
- [ ] Mutable singleton state is properly isolated/reset; `@DirtiesContext` is used only when needed.
- [ ] When using `@Transactional`, I know where the transaction starts/ends and whether an HTTP server shares that transaction.
- [ ] The test has meaningful behavioral assertions, not just `contextLoads`.
- [ ] I check Java/build tool/JUnit/Spring Boot versions and the first context initialization failure.
- [ ] Tests do not depend on secrets, production databases, execution order, or uncleaned mutable state.

## 16. Decision Map

```text
Only need to check logic?
    └─ Plain JUnit; instantiate with new, mock/fake dependencies.

Need Spring to manage a few beans?
    └─ @SpringJUnitConfig / @ContextConfiguration + SpringExtension.

Need Spring Boot bootstrap, profiles, or auto-config?
    └─ @SpringBootTest, with an appropriate webEnvironment.

Only need a framework slice?
    ├─ @WebMvcTest for HTTP MVC.
    └─ @DataJpaTest for JPA.

When TestContext is active:
 JUnit -> SpringExtension -> TestContextManager
       -> cache / context loader -> ApplicationContext
       -> inject test fixture -> lifecycle callbacks
       -> @Test assertions -> cleanup/transaction.
```

**Core message:** Spring TestContext is the bridge between the test runner's lifecycle and the Spring IoC container's lifecycle. Understanding how contexts are built or reused, how dependencies enter the test instance, and how listeners participate before/after `@Test` helps you verify real wiring while avoiding unnecessarily heavy integration tests.

## 17. Official Documentation

- Spring Framework — TestContext Framework: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html
- Spring Framework — Key Abstractions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/key-abstractions.html
- Spring Framework — `SpringExtension` / parameter injection: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html
- Spring Framework — Dependency Injection of Test Fixtures: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/fixture-di.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- JUnit User Guide: https://docs.junit.org/current/user-guide/
