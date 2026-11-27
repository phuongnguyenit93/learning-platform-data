# ManualRestDocumentation When Not Using JUnit

## 1. Context: Generating REST API Documentation Without Depending on JUnit

Spring REST Docs generates documentation from **HTTP operations verified by tests**. A test typically sends a request using **MockMvc**, **WebTestClient**, or **REST Assured**, verifies the response, and generates snippets describing the request, response, payload, parameters, and headers. The snippets are fed into Asciidoctor or a Markdown pipeline to build documentation in build and CI.

In the **SPRING_REST_DOCS** module, the **JUnit and Lifecycle** chapter introduces mechanisms for tying documentation generation to the test lifecycle. With JUnit Jupiter, we have `RestDocumentationExtension`; with JUnit 4, we have `JUnitRestDocumentation`. However, not every project uses JUnit. Some projects use **TestNG**, internal test runners, or invoke HTTP operations from a standalone verification program.

Those cases require **`ManualRestDocumentation`**: a component that lets test code **manually signal when each test starts and ends** so Spring REST Docs has the context needed to generate snippets.

After this lesson, you will be able to:

- Understand the exact role of `ManualRestDocumentation` and how it differs from JUnit extensions/rules.
- Explicitly invoke `beforeTest(Class<?>, String)` and `afterTest()` at the right lifecycle points.
- Integrate `ManualRestDocumentation` with MockMvc in a complete **TestNG** test.
- Apply the same concept to WebTestClient, REST Assured, and custom test harnesses.
- Choose an output directory, generate snippets, compile Asciidoctor/Markdown, and troubleshoot errors in build/CI.

## 2. What is ManualRestDocumentation?

The `org.springframework.restdocs.ManualRestDocumentation` class manages **`RestDocumentationContext`** manually. It implements the `RestDocumentationContextProvider` interface, allowing it to be passed directly into the REST Docs configuration API for HTTP clients.

Key APIs:

~~~java
import org.springframework.restdocs.ManualRestDocumentation;

ManualRestDocumentation docs = new ManualRestDocumentation();
ManualRestDocumentation customDocs =
        new ManualRestDocumentation("build/generated-snippets");

docs.beforeTest(MyApiTest.class, "shouldDocumentGetBook");

// Execute HTTP request, assertions, and document(...).

docs.afterTest();
~~~

| Component | Purpose |
| --- | --- |
| `new ManualRestDocumentation()` | Creates a context manager using the default snippet directory suitable for supported build environments. |
| `new ManualRestDocumentation("...")` | Specifies the root directory for snippets. |
| `beforeTest(Class<?> testClass, String testMethodName)` | Marks the start of **one test execution**, creating the corresponding documentation context. |
| `afterTest()` | Marks the end of the test and releases the created context. |
| `RestDocumentationContextProvider` | Interface that MockMvc, WebTestClient, or REST Assured can accept when configuring REST Docs. |
| `document("identifier", ...)` | Instructs REST Docs to generate snippets from the HTTP operation being verified. |

**Lifecycle constraint:** every successful call to `beforeTest(...)` must be paired with **one call to `afterTest()` when the test finishes**, even if an assertion fails. Do not call `beforeTest(...)` again on the same context before closing it: the API may throw `IllegalStateException` if a context already exists.

`ManualRestDocumentation` does not execute requests or write complete documentation by itself. It only supplies the context. The HTTP client and the `document(...)` call are still separate parts that must be configured.

## 3. Comparison with JUnit 4 and JUnit Jupiter

| Aspect | JUnit 4 | JUnit Jupiter | Without JUnit |
| --- | --- | --- | --- |
| REST Docs component | `JUnitRestDocumentation` | `RestDocumentationExtension` | `ManualRestDocumentation` |
| Activation mechanism | `@Rule` | `@ExtendWith` or `@RegisterExtension` | Manually instantiated |
| Who opens and closes the test context? | JUnit rule | JUnit extension | Test code calls `beforeTest` and `afterTest` |
| Common setup hook | `@Before` | `@BeforeEach` | TestNG `@BeforeMethod` or equivalent hook |
| Depends on JUnit runner? | Yes | Yes | No |
| Must configure MockMvc/WebTestClient/REST Assured? | Yes | Yes | Yes |

With TestNG, **do not use `@Rule` or `@ExtendWith`**: both annotations belong to the JUnit ecosystem. Use `@BeforeMethod` and `@AfterMethod` to control the lifecycle of `ManualRestDocumentation`.

If your project already uses JUnit Jupiter or JUnit 4 and has the corresponding REST Docs API, prefer the built-in automatic integration of that test framework. `ManualRestDocumentation` is specifically suited when the current framework does not provide a JUnit rule/extension mechanism.

## 4. The Right Lifecycle: beforeTest → HTTP → afterTest

Example execution flow with TestNG and MockMvc:

~~~mermaid
sequenceDiagram
    participant NG as TestNG
    participant Setup as @BeforeMethod
    participant Manual as ManualRestDocumentation
    participant MVC as MockMvc
    participant Docs as REST Docs
    participant Cleanup as @AfterMethod

    NG->>Setup: setUp(Method)
    Setup->>MVC: Create and configure MockMvc
    Setup->>Manual: beforeTest(testClass, methodName)
    NG->>MVC: perform(request)
    MVC-->>NG: HTTP response
    NG->>NG: Assert status, headers, body
    NG->>Docs: document("identifier", descriptors)
    Docs-->>NG: Generate snippets in outputDir
    NG->>Cleanup: tearDown() even if test fails
    Cleanup->>Manual: afterTest()
~~~

Key points to keep in mind:

1. **Before the first request to be documented**, call `beforeTest(...)` to establish the context.
2. `testClass` and `testMethodName` tell REST Docs which test is currently running. In TestNG, you can accept a `java.lang.reflect.Method` parameter in `@BeforeMethod` and retrieve `method.getName()`.
3. When configuring MockMvc, pass the `ManualRestDocumentation` instance itself into `documentationConfiguration(...)`.
4. The test must still assert the HTTP response and then call `document(...)` to generate snippets.
5. **After each test**, even when an assertion throws an exception, call `afterTest()` to release the context before the next test runs.

**Cleanup hook caveat:** `@AfterMethod(alwaysRun = true)` is a good way to reduce the risk of skipping cleanup when a test fails. If setup fails before `beforeTest(...)` is called, cleanup logic needs to know whether the context was already opened; this specialized handling is covered in Section 7.

## 5. Preparing Dependencies and the Test Runner

The main example uses **TestNG + Spring MVC Test + Spring REST Docs MockMvc**. The project needs compatible libraries, including Spring MVC, `spring-test`, `spring-restdocs-mockmvc`, TestNG, and a JSON converter such as Jackson (if the example returns JSON).

With Gradle Groovy DSL and Spring/Spring REST Docs versions managed via a BOM or existing dependency configuration:

~~~groovy
dependencies {
    testImplementation 'org.testng:testng:7.10.2'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useTestNG()
}
~~~

`spring-test` and `spring-restdocs-mockmvc` in the example above require versions managed by the build. Add `spring-webmvc` and Jackson in project setups that do not already include them.

If using Maven, ensure a compatible version of the test runner plugin can **discover and execute TestNG**, and that the `org.testng:testng` dependency is present in test scope. Do not confuse `useJUnitPlatform()` in Gradle with running TestNG: configuring JUnit Platform alone does not mean `org.testng.annotations.Test` methods will execute.

A typical TestNG test imports:

~~~java
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.Test;
~~~

These annotations differ from `org.junit.Test` and `org.junit.jupiter.api.Test`. When tests do not execute, no new snippets are created even if the REST Docs configuration code is completely valid.

## 6. Complete Example: TestNG + MockMvc + ManualRestDocumentation

The following example has a sample controller, JSON response, status/payload verification, and generates snippets for the path, request header, and response fields. Because it uses `MockMvcBuilders.standaloneSetup(...)`, the test **does not require** a Spring ApplicationContext.

Assuming the project already has Spring MVC Test, REST Docs MockMvc, Jackson, and TestNG, place the class in `src/test/java` and run with TestNG:

~~~java
import java.lang.reflect.Method;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.restdocs.ManualRestDocumentation;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.headerWithName;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.requestHeaders;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class GreetingApiTestNgDocumentationTest {

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;

    @BeforeMethod
    public void setUp(Method method) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .apply(documentationConfiguration(restDocumentation))
                .build();

        restDocumentation.beforeTest(getClass(), method.getName());
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        restDocumentation.afterTest();
    }

    @Test
    public void getGreetingIsDocumented() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan")
                        .accept(MediaType.APPLICATION_JSON)
                        .header("X-Trace-Id", "trace-demo-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.message").value("Hello, Lan"))
                .andDo(document("greetings-get-success",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Name used to build the greeting")
                        ),
                        requestHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Request tracking ID used in the example")
                        ),
                        responseFields(
                                fieldWithPath("name")
                                        .description("Name from the URL"),
                                fieldWithPath("message")
                                        .description("Response message content")
                        )
                ));
    }

    @RestController
    static class GreetingController {

        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> greet(@PathVariable("name") String name) {
            Map<String, String> body = new LinkedHashMap<>();
            body.put("name", name);
            body.put("message", "Hello, " + name);
            return body;
        }
    }
}
~~~

### Analyzing Key Connection Points

**`new ManualRestDocumentation("build/generated-snippets")`:** selects the root snippet directory. This object is reused sequentially across test methods of the TestNG instance; each run gets its own context lifecycle via `beforeTest` and `afterTest`.

**`@BeforeMethod setUp(Method method)`:** TestNG supplies the test method about to execute. `method.getName()` is the name passed into the documentation context. In TestNG, when using a data provider, multiple invocations of the same test method share the same method name; snippet identifiers should be chosen so different inputs do not overwrite one another.

**`documentationConfiguration(restDocumentation)`:** configures MockMvc to use the context provided by `ManualRestDocumentation`. Creating `ManualRestDocumentation` alone is not enough; the client executing requests itself must be configured with REST Docs.

**`beforeTest(getClass(), method.getName())`:** must be called before MockMvc performs the request. Without this line, REST Docs will not have an active open context to process the HTTP operation.

**`RestDocumentationRequestBuilders.get(...)`:** imported from REST Docs to preserve the URL template metadata `/api/greetings/{name}`, which is needed to generate the `pathParameters` snippet.

**`.andExpect(...)`:** verifies status and JSON fields; this ensures documentation is based on a verified response.

**`.andDo(document(...))`:** chooses identifier `greetings-get-success` and documents the path parameter, request header, and response fields. The additional snippets are typically named `path-parameters.adoc`, `request-headers.adoc`, and `response-fields.adoc`.

**`@AfterMethod(alwaysRun = true)`:** is responsible for calling `afterTest()` so the context from the previous test run is not left behind. This is the part JUnit rules/extensions normally manage automatically.

### Expected Output

With an appropriate working directory and default snippets, the output directory might look like:

~~~text
build/
└── generated-snippets/
    └── greetings-get-success/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── path-parameters.adoc
        ├── request-headers.adoc
        └── response-fields.adoc
~~~

The exact file list depends on the REST Docs configuration and version in use. The sign to verify is that the identifier subdirectory contains the requested files and their content matches the request/response verified by the test.

## 7. Ensuring Cleanup When Tests or Setup Fail

In long-running test environments, a later test must never inherit the documentation context of a prior test. In particular, `beforeTest(...)` can throw `IllegalStateException` if the instance already holds an unclosed context.

For **standalone manual verification programs**, the safest way to guarantee cleanup is `try/finally`:

~~~java
ManualRestDocumentation docs =
        new ManualRestDocumentation("build/generated-snippets");

docs.beforeTest(MyHttpChecks.class, "verifyGetGreeting");
try {
    MockMvc mvc = MockMvcBuilders
            .standaloneSetup(new GreetingController())
            .apply(documentationConfiguration(docs))
            .build();

    mvc.perform(get("/api/greetings/{name}", "Lan"))
            .andExpect(status().isOk())
            .andDo(document("greetings-manual-check"));
} finally {
    docs.afterTest();
}
~~~

This is a **usage skeleton**: assuming `MyHttpChecks`, `GreetingController`, imports, and MockMvc infrastructure are present. If `pathParameters(...)` is needed in snippets, keep the REST Docs request builder import as in the main example.

In **TestNG**, `@AfterMethod(alwaysRun = true)` is the appropriate hook. If `@BeforeMethod` might fail before `beforeTest(...)` runs, add a local state flag so cleanup only runs when a context was actually opened:

~~~java
private boolean documentationStarted;

@BeforeMethod
public void setUp(Method method) {
    // Prepare MockMvc or HTTP client first.
    mockMvc = createConfiguredMockMvc();

    restDocumentation.beforeTest(getClass(), method.getName());
    documentationStarted = true;
}

@AfterMethod(alwaysRun = true)
public void tearDown() {
    if (documentationStarted) {
        try {
            restDocumentation.afterTest();
        } finally {
            documentationStarted = false;
        }
    }
}
~~~

This is a **lifecycle-handling pattern** requiring the current test's `createConfiguredMockMvc()` method. When running multiple TestNG threads concurrently, a single boolean instance field is not enough to guarantee isolation. You must design **each test execution to have its own context and cleanup state**, as well as distinct identifiers/output locations to prevent file collisions.

If setup succeeds but an assertion fails, `afterTest()` must still be called; that is why cleanup should never be placed at the end of a test body after the assertions.

## 8. Integrating with Spring TestContext in TestNG

The test in Section 6 uses a simple controller. In a real application, a controller may depend on services, bean validation, message converters, or Spring MVC configuration. In that case, you can use the **Spring TestContext Framework for TestNG** with `AbstractTestNGSpringContextTests` and `@ContextConfiguration`.

Skeleton example:

~~~java
@ContextConfiguration(classes = DocumentationWebConfig.class)
@WebAppConfiguration
public class WebContextDocumentationTest
        extends AbstractTestNGSpringContextTests {

    @Autowired
    private WebApplicationContext context;

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;

    @BeforeMethod
    public void setUp(Method method) {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();

        restDocumentation.beforeTest(getClass(), method.getName());
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        restDocumentation.afterTest();
    }

    // @Test: mockMvc.perform(...).andExpect(...).andDo(document(...))
}
~~~

This is an **integration skeleton**, requiring imports, `DocumentationWebConfig`, and appropriate beans/controllers; it is not a complete runnable program as-is.

Separating responsibilities:

- `AbstractTestNGSpringContextTests` and Spring TestContext help prepare the ApplicationContext and inject beans when using TestNG.
- `ManualRestDocumentation` manages the lifecycle of the **REST Docs documentation generation context**.
- `MockMvc` uses `WebApplicationContext` to execute requests against the application's MVC configuration.
- `document(...)` requests snippet generation from the verified HTTP operation.

Using Spring TestContext with TestNG **does not automatically replace** `ManualRestDocumentation`'s `beforeTest`/`afterTest`. When a project uses Spring Boot, you must also distinguish Boot's auto-configured client from manually created clients; avoid assuming every MockMvc instance already has REST Docs integrated.

## 9. Applying to WebTestClient and REST Assured

`ManualRestDocumentation` implements `RestDocumentationContextProvider`, so the same lifecycle concept applies to other HTTP clients. What changes is the **client configuration syntax**, not the meaning of `beforeTest` and `afterTest`.

### WebTestClient

For an application with a suitable `ApplicationContext`:

~~~java
private final ManualRestDocumentation restDocumentation =
        new ManualRestDocumentation("build/generated-snippets");

private WebTestClient webTestClient;

@BeforeMethod
public void setUp(Method method) {
    webTestClient = WebTestClient.bindToApplicationContext(applicationContext)
            .configureClient()
            .filter(WebTestClientRestDocumentation
                    .documentationConfiguration(restDocumentation))
            .build();

    restDocumentation.beforeTest(getClass(), method.getName());
}

@AfterMethod(alwaysRun = true)
public void tearDown() {
    restDocumentation.afterTest();
}
~~~

This skeleton requires an initialized `applicationContext`, imports, and a compatible `spring-restdocs-webtestclient` dependency. When invoking requests, use `WebTestClientRestDocumentation.document(...)` or the integration API matching your REST Docs version.

### REST Assured

For an HTTP service ready to be tested:

~~~java
private final ManualRestDocumentation restDocumentation =
        new ManualRestDocumentation("build/generated-snippets");

private RequestSpecification specification;

@BeforeMethod
public void setUp(Method method) {
    specification = new RequestSpecBuilder()
            .addFilter(RestAssuredRestDocumentation
                    .documentationConfiguration(restDocumentation))
            .build();

    restDocumentation.beforeTest(getClass(), method.getName());
}

@AfterMethod(alwaysRun = true)
public void tearDown() {
    restDocumentation.afterTest();
}
~~~

This skeleton uses REST Assured's `RequestSpecification`, `RequestSpecBuilder`, and APIs from `spring-restdocs-restassured`. Tests must still specify the URL/base URI, execute the request, run assertions, and apply the appropriate `document(...)` filter.

| Tool | How to Attach REST Docs to Client | Context |
| --- | --- | --- |
| MockMvc | `MockMvcBuilders...apply(documentationConfiguration(docs))` | In-process Spring MVC testing |
| WebTestClient | `configureClient().filter(documentationConfiguration(docs))` | WebFlux or client-configured HTTP testing |
| REST Assured | `RequestSpecBuilder().addFilter(documentationConfiguration(docs))` | HTTP API testing with REST Assured |

Do not swap package names/imports mechanically across the three tools: each integration module has its own corresponding `documentationConfiguration`/`document` class.

## 10. From Snippets to Asciidoctor, Markdown, and CI

`ManualRestDocumentation` has a constructor taking an output directory:

~~~java
new ManualRestDocumentation("build/generated-snippets")
~~~

When a test calls `document("greetings-get-success", ...)`, output typically resides at:

~~~text
build/generated-snippets/greetings-get-success/
~~~

**Distinguish the two path levels:** the constructor selects the **root directory**, while `document(identifier)` determines the **subdirectory**. Relative paths can depend on the test process's working directory, so inspect IDE, multi-module build, and CI configurations.

An Asciidoctor page can embed snippets as follows:

~~~asciidoc
= Greeting API

== Get Greeting

=== HTTP request
include::{snippets}/greetings-get-success/http-request.adoc[]

=== Request header
include::{snippets}/greetings-get-success/request-headers.adoc[]

=== Path parameter
include::{snippets}/greetings-get-success/path-parameters.adoc[]

=== HTTP response
include::{snippets}/greetings-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/greetings-get-success/response-fields.adoc[]
~~~

Here the `{snippets}` attribute must be set in the Asciidoctor configuration to point to the root directory where tests write snippets. To ensure proper ordering, the documentation generation task must depend on the corresponding **TestNG** test suite.

Illustrative Gradle Groovy DSL example:

~~~groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    useTestNG()
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir
}
~~~

The example assumes the project already applies an Asciidoctor plugin with an `asciidoctor` task; attribute syntax may vary by plugin version. With Maven, configure the test phase with TestNG, then point the Asciidoctor plugin to read from the corresponding snippet directory (typically `target/generated-snippets` when using Maven's output dir).

If using a Markdown pipeline, remember that REST Docs' default snippets are usually Asciidoctor `.adoc` files. Configure compatible conversion/embedding rather than assuming changing the output directory changes the format automatically.

Overall workflow:

~~~text
TestNG or custom test runner
        |
        v
ManualRestDocumentation.beforeTest(...)
        |
        v
MockMvc / WebTestClient / REST Assured
        |
        v
HTTP assertions + document(...)
        |
        v
ManualRestDocumentation.afterTest()
        |
        v
generated-snippets/{identifier}/
        |
        v
Asciidoctor / Markdown pipeline
        |
        v
REST API documentation in build and CI
~~~

The build step should verify the existence of essential snippets and avoid leaking sensitive data from real requests/responses into published documentation pages. When changing the output dir or identifier names, update both the producer and consumer sides.

## 11. Common Errors and How to Diagnose Them

| Symptom | Typical Cause | Resolution |
| --- | --- | --- |
| `IllegalStateException` when calling `beforeTest(...)` | Previous test context was not released or `beforeTest` was called twice. | Check pairing between `beforeTest` and `afterTest`, and avoid duplicate calls in setup. |
| Request is processed without generating snippets | Forgot `document(...)` or REST Docs configured on the wrong client. | Verify `documentationConfiguration(docs)` is applied to the active client and `document` is called. |
| Error due to missing REST Docs context | Forgot to call `beforeTest(...)` before the request or `afterTest()` was called too early. | Fix setup/test/teardown order using per-test hooks. |
| One test failure breaks subsequent tests | Missing `afterTest()` when an exception occurs. | Use `@AfterMethod(alwaysRun = true)` or `try/finally`. |
| No snippet files despite build reporting success | TestNG tests were not discovered or executed. | Check test engine, Gradle `useTestNG()`, Maven config, and test counts. |
| `pathParameters(...)` fails to match URL | Used a builder that does not preserve the path template. | Use `RestDocumentationRequestBuilders.get` with URL `/api/greetings/{name}`. |
| Response fields check fails | JSON response does not match descriptors, or a field is missing. | Compare actual body, assertions, and `fieldWithPath(...)`. |
| Snippets appear in a different directory | Different working directory between IDE/build/CI. | Verify physical paths and synchronize the output directory. |
| Data-driven TestNG tests overwrite each other | Multiple test runs share the same identifier. | Generate predictable snippet identifiers per scenario or test data. |
| Flaky parallel tests | Context/filenames/mutable objects shared without control. | Isolate per-execution state and output names; review parallel execution strategy. |
| Asciidoctor cannot find include | Tests have not run, snippet is missing, or `snippets` attribute is wrong. | Verify task dependencies and `{snippets}` path after tests generate files. |

A systematic diagnostic checklist:

1. **Is the TestNG runner actually executing tests?**
2. **Is `beforeTest(...)` called exactly once before the HTTP operation?**
3. **Is the client used to send requests configured with REST Docs?**
4. **Do status/body assertions pass?**
5. **Is `document(...)` called with the right identifier?**
6. **Is `afterTest()` called even when a test fails?**
7. **Which directory are snippets written to, and where is Asciidoctor/Markdown reading from?**

## 12. Practice: Verifying Lifecycle Outside JUnit

Starting from `GreetingApiTestNgDocumentationTest` in Section 6:

1. Run TestNG and verify expected status/body; locate `greetings-get-success/http-request.adoc`, `request-headers.adoc`, and `response-fields.adoc`.
2. Temporarily remove `restDocumentation.beforeTest(...)` from `@BeforeMethod`, run the test, and observe the failure in the documentation step. Restore the call.
3. Temporarily remove `@AfterMethod` or `afterTest()` and run multiple tests sequentially on the same instance (in an isolated test environment). Observe the impact of an uncleaned context, then restore cleanup.
4. Move `afterTest()` into a `finally` block in a standalone HTTP verification program, deliberately throw an exception, and confirm the cleanup branch still executes.
5. Change the output directory to `build/api-snippets`, re-run the test, and update Asciidoctor to include the right files.
6. Add an error response test such as `404 Not Found` with assertions and identifier `greetings-get-not-found`. Compare the actual response against the snippet.
7. If using TestNG `@DataProvider` or parallel execution, design distinct identifiers per scenario and verify files are generated without overwriting one another.
8. Add the TestNG test suite and documentation build step to CI; fail the build if tests do not run or required snippets are missing.

**Completion criteria:** you can distinguish the test context from the HTTP operation, pinpoint when to open/close the context, select the client configured with REST Docs, verify snippets, and trace the link to the built documentation.

## 13. Takeaways

- **`ManualRestDocumentation`** manually manages the Spring REST Docs context when **not using JUnit**, especially suited for TestNG or custom test runners.
- You must pair **`beforeTest(testClass, testMethodName)`** with **`afterTest()`** for each test execution; cleanup must run even when assertions fail.
- **`documentationConfiguration(docs)`** connects the context to MockMvc/WebTestClient/REST Assured; **`document(identifier, ...)`** triggers snippet generation.
- The constructor can specify the **root output directory**, while the identifier determines the subdirectory; both must match the build, Asciidoctor/Markdown, and CI configuration.
- Reliable API documentation requires the complete chain: **actually run tests → verify responses → generate snippets → compile and publish documentation**.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): setting up tests when not using JUnit.
- [ManualRestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/ManualRestDocumentation.html): constructors, `beforeTest`, `afterTest`, and `RestDocumentationContextProvider`.

Select documentation and library versions matching the Spring REST Docs version used in your project, as integration details with Spring Boot, TestNG, or compilation tools may differ across release lines.
