# JUnit 5 Is Recommended and Other Frameworks

## 1. How Does JUnit 5 Fit the Spring REST Docs Lifecycle?

The **SPRING_REST_DOCS** module teaches how to generate verifiable REST API documentation from HTTP tests. Tests using MockMvc, WebTestClient, or REST Assured execute requests, verify status/headers/body, and generate snippets to compile into Asciidoctor or Markdown documentation running in build/CI.

Spring REST Docs does not require the entire project to use a single test framework. However, **JUnit Jupiter (JUnit 5)** is a convenient choice when starting a new project because Spring REST Docs provides an extension that integrates directly with Jupiter's lifecycle. The extension automatically manages the documentation context for each test and allows injecting `RestDocumentationContextProvider` into test callbacks.

Common options:

| Framework | Lifecycle Integration Approach | Convenience Level |
| --- | --- | --- |
| JUnit Jupiter (JUnit 5) | `RestDocumentationExtension` and parameter injection | Recommended for new projects |
| JUnit 4 | `JUnitRestDocumentation` via `@Rule` | Clear integration for legacy projects |
| TestNG | Manually drive lifecycle with `ManualRestDocumentation` in `@BeforeMethod`/`@AfterMethod` | Requires explicit setup/cleanup management |
| Spock | Can use REST Docs APIs in specification setup/cleanup, typically via `ManualRestDocumentation` | Suitable when the project already chose Spock |
| Custom framework | Manually coordinate `ManualRestDocumentation` or context provider | Flexible, though the author is responsible for lifecycle |

"Recommended" here refers to integration convenience and the modern ecosystem, not that REST Docs only works with JUnit 5. What all options share is that REST Docs needs to know **which test is running**, **where snippets are written**, and **when the test's context ends**.

## 2. Basic JUnit Jupiter Lifecycle

A Jupiter test class typically has the following callbacks:

- `@BeforeAll` runs once before all tests in the class.
- `@BeforeEach` runs before each test method.
- `@Test` marks a test method.
- `@AfterEach` runs after each test method.
- `@AfterAll` runs once after all tests in the class.

With the default `@TestInstance(Lifecycle.PER_METHOD)` configuration, JUnit creates a new instance of the test class for each test method. `@BeforeAll` and `@AfterAll` typically must be static. You can choose `PER_CLASS` to use instance callbacks, though shared state must be controlled.

Spring REST Docs provides an extension:

```java
@ExtendWith(RestDocumentationExtension.class)
class AccountDocumentationTest {
    // Test methods
}
```

`RestDocumentationExtension` integrates into the Jupiter extension model to create and manage the documentation context. The extension provides `RestDocumentationContextProvider` via parameter resolution. During setup, pass the provider to `documentationConfiguration(...)` when creating the appropriate MockMvc/WebTestClient/REST Assured filter.

### 2.1. Configuring MockMvc with @BeforeEach

Example using an existing Spring MVC context:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})
class AccountDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void getAccount() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk());
    }
}
```

If the project uses Spring Boot/JUnit Jupiter test integration and corresponding auto-configuration, `@SpringBootTest` typically already registers `SpringExtension` via meta-annotation; for example, it can be shortened to `@ExtendWith(RestDocumentationExtension.class)`. To make responsibilities clear, the snippet above explicitly shows both extensions.

Flow per test:

1. Jupiter instantiates the test class and injects Spring dependencies.
2. `RestDocumentationExtension` sets up the context for the test.
3. `@BeforeEach` receives `RestDocumentationContextProvider` and configures MockMvc.
4. The test sends the request and verifies the HTTP response.
5. `document(...)` generates snippets within the test's context.
6. Jupiter runs cleanup callbacks and the extension closes the documentation context.

There is no need to manually create a new output directory in each test method when using the extension and project-wide output directory configuration.

### 2.2. Manual Setup for Standalone MockMvc

For a controller that does not need a Spring application context:

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderControllerDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void getOrder() throws Exception {
        mockMvc.perform(get("/api/orders/100"))
                .andExpect(status().isOk())
                .andDo(document("orders-get"));
    }
}
```

Standalone setup is fast and isolated, but does not automatically load all production configuration components. If the controller depends on converters, advice, validators, filters, or security config, register those components explicitly or use an integration test with an application context.

## 3. What Does the Extension Provide and What Does It Not Do?

The extension helps manage the documentation context and integrates with the Jupiter lifecycle. It does not replace HTTP assertions, write field descriptors for you, or decide snippet content.

| Responsibility | Responsible Component |
| --- | --- |
| Create/close context for each test | `RestDocumentationExtension` |
| Supply context for client configuration | `RestDocumentationContextProvider` |
| Send HTTP requests in tests | MockMvc, WebTestClient, or REST Assured |
| Verify status/headers/body | HTTP test framework assertions |
| Choose snippets and field descriptions | `document(...)`, `requestFields(...)`, `responseFields(...)` |
| Assemble snippets into documentation | Asciidoctor or the project's documentation pipeline |

For example, if a test does not call `andDo(document(...))` with MockMvc, the extension can still run normally, yet that test does not request any REST Docs snippet generation. Conversely, if a test uses `document(...)` when MockMvc has not been configured with the documentation configurer from the corresponding context, snippet generation will not be wired properly into the lifecycle.

## 4. Configuring Snippet Output

The snippet output path is usually configured centrally rather than hard-coded in every test:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
            .apply(documentationConfiguration(documentation)
                    .snippets().withDefaults(
                            CliDocumentation.curlRequest(),
                            HttpDocumentation.httpRequest(),
                            HttpDocumentation.httpResponse()
                    ))
            .build();
}
```

The snippet above illustrates configuring additional default snippets; in a real project, import the corresponding helpers or keep the default configuration of your Spring REST Docs version. If configuring the output directory in the build, make sure the test task and Asciidoctor reference the exact same directory.

Commonly with Gradle:

```text
build/generated-snippets/
```

Commonly with Maven:

```text
target/generated-snippets/
```

These are common conventions; projects can customize them. Keep test setup, the Asciidoctor plugin, and CI consistent.

## 5. JUnit 4: Integration via @Rule

Projects using JUnit 4 can integrate Spring REST Docs using `JUnitRestDocumentation`:

```java
import org.junit.Rule;
import org.junit.Test;
import org.junit.Before;
import org.springframework.restdocs.JUnitRestDocumentation;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class LegacyAccountDocumentationTest {

    @Rule
    public JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("target/generated-snippets");

    private MockMvc mockMvc;

    @Before
    public void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .apply(documentationConfiguration(this.restDocumentation))
                .build();
    }

    @Test
    public void getAccount() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk())
                .andDo(document("accounts-get"));
    }
}
```

`JUnitRestDocumentation` is a JUnit 4 Rule managing the documentation context per test. The example specifies the output directory as `target/generated-snippets`; you can replace it with your project's build path. The test method uses JUnit 4's `@Test`, not the Jupiter annotation.

Do not arbitrarily mix the two models in the same class: `@Rule` belongs to JUnit 4, while `@ExtendWith`/`@BeforeEach` belong to JUnit Jupiter. When migrating from JUnit 4 to Jupiter, replace both the lifecycle integration and dependencies/imports, not merely the annotation names.

## 6. TestNG or Frameworks Without Built-In Extension Integration

For frameworks without a directly integrated extension/rule, you can manage the lifecycle using `ManualRestDocumentation`. The idea is:

1. Create a `ManualRestDocumentation` instance for the test fixture.
2. Call `beforeTest(testClass, testMethodName)` before the test.
3. Configure MockMvc or the client with that documentation provider.
4. Call `afterTest()` after the test, even when assertions fail.

Example TestNG structure:

```java
import org.springframework.restdocs.ManualRestDocumentation;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;

class TestNgAccountDocumentationTest {

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation();

    private MockMvc mockMvc;

    @BeforeMethod
    public void setUp(java.lang.reflect.Method testMethod) {
        restDocumentation.beforeTest(
                getClass(), testMethod.getName());

        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    public void getAccount() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk())
                .andDo(document("accounts-get"));
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        restDocumentation.afterTest();
    }
}
```

This is an illustrative skeleton: you need imports for MockMvc, MockMvcBuilders, and the static request/assertion/documentation methods just like the MockMvc example above. Using `alwaysRun = true` in TestNG ensures cleanup runs even if setup/test fails, following TestNG's lifecycle rules.

Do not call `beforeTest` once for the whole class if the snippet context needs to be isolated per method. Each test needs a context corresponding to its class/method name and must be closed exactly once. If a framework uses differently named before/after test hooks, map the same lifecycle responsibility to the equivalent hooks.

## 7. Spock and Groovy Specifications

Spock uses `setup()`, `cleanup()`, `setupSpec()`, and `cleanupSpec()` blocks instead of JUnit-style annotations. With Spring REST Docs, you can manage the context manually via `ManualRestDocumentation` if not using a dedicated integration bridge.

Example structure:

```groovy
import org.springframework.restdocs.ManualRestDocumentation
import spock.lang.Specification

class AccountDocumentationSpec extends Specification {

    ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation()

    def setup() {
        restDocumentation.beforeTest(
                getClass(), specificationContext.currentFeature.name)
        // Build MockMvc/WebTestClient with
        // documentationConfiguration(restDocumentation)
    }

    def cleanup() {
        restDocumentation.afterTest()
    }

    def "GET account documents the response"() {
        expect:
        // Send request, assert response, and call document(...)
        true
    }
}
```

The snippet above demonstrates lifecycle mapping, not a complete endpoint test. In a real specification, you must configure the client, request, assertions, and snippets. Ensure `cleanup()` executes even when a feature fails, and never share a mutable documentation context across parallel features.

If a Spock project already uses Spring Test/Spock integration, keep using that model while maintaining the rules: context starts before the test, snippets are bound to the right test, and cleanup always finishes.

## 8. Using WebTestClient or REST Assured Keeps the Same Lifecycle Idea

The Jupiter extension is not exclusively for MockMvc. It can also supply the documentation context to configure WebTestClient or REST Assured.

### 8.1. WebTestClient

Example configuration:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    webTestClient = WebTestClient.bindToController(new AccountController())
            .configureClient()
            .filter(documentationConfiguration(documentation))
            .build();
}
```

Then send the request and record snippets using the WebTestClient REST Docs API:

```java
webTestClient.get()
        .uri("/api/accounts/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("accounts-get"));
```

In an application with a real WebFlux server, you can bind to the application context or server depending on the test type. Choose the right setup so tests reflect actual converters/filters/security and routing.

### 8.2. REST Assured

With REST Assured, the documentation context is used to create a filter:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    this.spec = new RequestSpecBuilder()
            .addFilter(documentationConfiguration(documentation))
            .build();
}
```

In the test:

```java
given(this.spec)
    .filter(document("accounts-get"))
    .when()
    .get("/api/accounts/42")
    .then()
    .statusCode(200);
```

Imports and filter composition may vary depending on the REST Docs/REST Assured version. Use the integration artifact corresponding to your chosen client and verify snippets are generated from real HTTP exchanges.

Regardless of the client used, the general lifecycle still consists of setting up the documentation context, attaching the configurer/filter, running the HTTP test, calling `document`, and cleaning up.

## 9. Parameterized Tests, Dynamic Tests, and Snippet Identifiers

JUnit Jupiter supports `@ParameterizedTest`, `@MethodSource`, `@CsvSource`, and `@TestFactory`. When multiple inputs generate snippets, choose unique, meaningful, and stable identifiers.

Example:

```java
@ParameterizedTest
@ValueSource(strings = {"42", "43"})
void getAccount(String accountId) throws Exception {
    mockMvc.perform(get("/api/accounts/{id}", accountId))
            .andExpect(status().isOk())
            .andDo(document("accounts-" + accountId));
}
```

The two test runs will generate snippets:

```text
accounts-42/
accounts-43/
```

Do not reuse the same identifier for multiple different responses if tests may run in parallel or produce different content. If the same endpoint has multiple scenarios like success/not-found, clearly distinguish `accounts-get-success` and `accounts-get-not-found`.

Dynamic tests also need distinct identifiers:

```java
@TestFactory
Stream<DynamicTest> accountScenarios() {
    return Stream.of("42", "43")
            .map(id -> dynamicTest("account " + id, () -> {
                // Request, assertions, and document("accounts-" + id)
            }));
}
```

Note: `@BeforeEach` lifecycle applies to the test factory method itself, and does not re-run individually for each dynamic test node the way it does for standard test methods. If each dynamic test needs its own documentation context, manage the lifecycle manually inside the executable or prefer parameterized tests to leverage per-invocation lifecycle hooks.

## 10. Parallel Execution and Context Management

JUnit Jupiter can run tests in parallel when enabled in configuration. When REST Docs generates snippet files, ensure:

- Each test has its own documentation context.
- Snippet identifiers do not collide when outputs differ.
- A single mutable `MockMvc`/WebTestClient is not shared if test setups differ.
- `ManualRestDocumentation` is not shared across concurrent tests.
- Two tests never write to the same snippet file simultaneously.
- Fixtures and test data do not depend on execution order.

If two tests both write `accounts-get`, output can be overwritten or hit race conditions. Use distinct identifiers per scenario; avoid merely appending random method names if you want long-term stable snippets. When stronger output isolation is desired, configure per-test/task directories or disable parallelism for documentation-generating tests until identifiers and contexts are designed safely.

## 11. Choosing a Framework by Project

| Context | Reasonable Choice | Reason |
| --- | --- | --- |
| New Spring project without legacy test framework | JUnit Jupiter | Direct extension, parameterized tests, and modern ecosystem |
| Project steadily using JUnit 4 | Keep JUnit 4 integration | No need to migrate just to generate REST Docs |
| Project using TestNG | TestNG + ManualRestDocumentation | Maps cleanly to before/after method lifecycle |
| Team already using Spock/Groovy | Spock + manual lifecycle or suitable integration | Preserves the existing testing language |
| Multiple different test clients | Choose per HTTP stack | REST Docs provides integrations for MockMvc, WebTestClient, and REST Assured |

Do not switch test frameworks just to use Spring REST Docs. Migration costs, build plugins, other extensions, reporting, and team conventions must be weighed. When starting a new project, Jupiter usually requires less configuration; if a project already uses JUnit 4/Spock/TestNG, you can integrate via the corresponding lifecycle.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot inject `RestDocumentationContextProvider` | Missing `@ExtendWith(RestDocumentationExtension.class)` or method signature is not on a supported lifecycle callback/test | Register the extension and place the parameter on the proper callback |
| `documentationConfiguration` does not receive expected context | Built configurer from another provider or wrong test scope | Pass the context provided for the currently running test |
| JUnit 4 Rule is not triggered | Running Jupiter engine while only having a JUnit 4 `@Rule` | Use the Vintage engine for legacy tests or migrate to the Jupiter extension |
| TestNG does not generate snippets | Forgot `beforeTest`/`afterTest` or wrong provider configuration | Use `ManualRestDocumentation` and guarantee cleanup |
| Snippets get overwritten | Multiple tests share the same identifier | Create stable, scenario-specific identifiers |
| Context is not cleaned up on test failure | Cleanup placed in code that only runs when the test passes | Use `@AfterEach`/`@AfterMethod(alwaysRun = true)` or an equivalent cleanup hook |
| Flaky results during parallel execution | Shared context, client, or snippet path | Separate contexts/identifiers and control concurrency |
| Jupiter test runs without generating snippets | Forgot `document(...)` or REST Docs not configured on client | Attach the configurer/filter and call `document` inside the HTTP test |
| Using dynamic tests but setup does not run per node | Misunderstanding `@TestFactory` lifecycle | Use parameterized tests or manage context inside the executable |
| Switching frameworks solely for REST Docs | Overlooking migration cost | Keep the current framework if it already meets needs |

## 13. Practice

Practice on endpoint `GET /api/accounts/{id}`:

1. Create a Jupiter test class with `@ExtendWith(RestDocumentationExtension.class)`; inject `RestDocumentationContextProvider` into `@BeforeEach`.
2. Configure MockMvc, send a request, and verify status/body before calling `document("accounts-get")`.
3. Run two test methods and observe that each test gets its own documentation context.
4. Create a `@ParameterizedTest` for multiple account IDs; generate distinct identifiers and verify snippets do not overwrite one another.
5. Port the test to JUnit 4 using the `JUnitRestDocumentation` Rule and compare its lifecycle with Jupiter.
6. Write a TestNG test using `ManualRestDocumentation`; ensure `afterTest()` runs even when an assertion fails.
7. Try configuring WebTestClient or REST Assured using the same documentation context and verify HTTP snippets are generated.
8. Enable parallel execution on a group of tests with distinct identifiers; verify output does not contend.
9. Create a dynamic test and confirm `@BeforeEach` is not invoked separately for each dynamic node.
10. Run the test task before the Asciidoctor task and verify the final documentation references the latest snippets.

**Completion criteria:** you can explain JUnit Jupiter's integrated lifecycle, configure `RestDocumentationExtension` with MockMvc, know that JUnit 4 uses a Rule and other frameworks can use `ManualRestDocumentation`, and safely manage identifiers/contexts for parameterized, dynamic, and parallel tests.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/index.html): test framework setup and Spring REST Docs integration.
- [Spring REST Docs — API Documentation](https://docs.spring.io/spring-restdocs/reference/index.html): MockMvc, WebTestClient, and REST Assured integrations.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): lifecycle, extension model, parameterized tests, and dynamic tests.
- [Spring REST Docs API — ManualRestDocumentation](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/ManualRestDocumentation.html): manual lifecycle for other test frameworks.
- [Spring REST Docs API — RestDocumentationExtension](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationExtension.html): extension for JUnit Jupiter.
