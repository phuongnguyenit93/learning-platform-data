# beforeTest and afterTest for Manual Lifecycle

## 1. Goal: Managing the Spring REST Docs Lifecycle Manually

**Spring REST Docs** generates REST API documentation from actual HTTP operations under test. A test can use **MockMvc**, **WebTestClient**, or **REST Assured** to send requests, verify status, headers, and payload, and then generate snippets describing the request, response, parameters, payload, or headers. These snippets are compiled with **Asciidoctor/Markdown** and integrated into the build and CI pipeline.

In the **SPRING_REST_DOCS** module, the **JUnit and Lifecycle** chapter focuses on the question: *Who is responsible for initializing and terminating the documentation context of each test run?*

- With JUnit Jupiter, `RestDocumentationExtension` handles this via the extension mechanism.
- With JUnit 4, `JUnitRestDocumentation` handles this via a rule.
- With **TestNG**, custom test runners, or HTTP verification programs that do not use JUnit, we can directly control **`ManualRestDocumentation`** via **`beforeTest(...)`** and **`afterTest()`**.

This lesson dives deep into this **pair of lifecycle methods**: when to call them, how to pair them, ensuring cleanup when a test fails, handling setup errors, and considerations when running multiple tests or running in parallel.

By the end of this lesson, you will be able to:

1. Explain the roles of `beforeTest(Class<?>, String)` and `afterTest()`.
2. Write an HTTP test suite with a proper manual lifecycle.
3. Integrate the lifecycle with TestNG or with `try/finally` in a standalone program.
4. Distinguish the test context, HTTP client configuration, and the `document(...)` operation.
5. Inspect generated snippets and ensure build/CI only consumes output from tests that have executed successfully.

## 2. ManualRestDocumentation and Its Two Core Methods

`ManualRestDocumentation` belongs to package:

~~~java
org.springframework.restdocs.ManualRestDocumentation
~~~

This object implements `RestDocumentationContextProvider` and manages the REST Docs context that a test must establish when there is no JUnit rule/extension doing it automatically.

The shortest example of the usage cycle:

~~~java
ManualRestDocumentation restDocs =
        new ManualRestDocumentation("build/generated-snippets");

restDocs.beforeTest(BookDocumentationTest.class, "getBook");
try {
    // Perform HTTP request, assert response, and document(...).
} finally {
    restDocs.afterTest();
}
~~~

Meaning of the two methods:

| Method | When to Call | Role |
| --- | --- | --- |
| `beforeTest(Class<?> testClass, String testMethodName)` | Before starting the HTTP operation to document | Opens the REST Docs context for the test execution identified by class and method name. |
| `afterTest()` | After the test finishes, even if an error occurred | Ends and releases the context of the test run. |

`beforeTest(...)` does **not** send requests, start a server, or automatically generate snippets. `afterTest()` does **not** render an Asciidoctor page or verify assertions. Both methods are solely responsible for the **context** used during documentation generation.

An instance can use either a no-arg constructor or one accepting an output directory:

~~~java
ManualRestDocumentation defaultOutput = new ManualRestDocumentation();

ManualRestDocumentation customOutput =
        new ManualRestDocumentation("build/generated-snippets");
~~~

When using the constructor with a path, REST Docs writes snippets under the specified directory when `document(...)` is called. Relative paths are typically resolved against the test process's working directory.

### What Are the Class and Method Name Passed For?

For example:

~~~java
restDocs.beforeTest(BookDocumentationTest.class, "shouldGetBookById");
~~~

- `BookDocumentationTest.class` is the test class identity.
- `"shouldGetBookById"` describes the test method or scenario.
- These two arguments supply context identity metadata to REST Docs; they do **not** replace the identifier in `document("books-get", ...)`.

The identifier `books-get` still determines the snippet subdirectory. Passing the method name `shouldGetBookById` does not cause REST Docs to write into a `shouldGetBookById` folder if the test calls `document("books-get", ...)`.

## 3. Three Layers of Responsibility to Distinguish

In a REST API documentation test, there are **three independent steps**:

| Step | Illustrative API | Effect |
| --- | --- | --- |
| Lifecycle management | `beforeTest(...)` / `afterTest()` | Opens and closes the REST Docs context. |
| HTTP client configuration | `documentationConfiguration(restDocs)` | Connects the context to MockMvc or the integrated client. |
| Snippet generation | `document("books-get", descriptors...)` | Writes documentation for a specific HTTP operation. |

Overall diagram:

~~~mermaid
flowchart TD
    A["Test runner: TestNG or custom"] --> B["beforeTest(testClass, methodName)"]
    B --> C["REST Docs context is opened"]
    C --> D["Client with documentationConfiguration applied"]
    D --> E["HTTP request"]
    E --> F["Verify status / headers / body"]
    F --> G["document(identifier, descriptors)"]
    G --> H["generated-snippets/identifier/*.adoc"]
    H --> I["afterTest(): close context"]
    I --> J["Asciidoctor / Markdown in build, CI"]
~~~

The diagram depicts responsibilities and logical ordering. The client configuration itself (`MockMvcBuilders...apply(...)`) can be constructed in setup right after opening the context; what is mandatory is that **the context must be ready before documenting a request**.

**Do not conflate the methods:** calling `beforeTest` while forgetting `document` simply means you opened a context without requesting snippets for any HTTP operation. Conversely, calling `document` without a proper active context can fail. Proper cleanup does not substitute for necessary HTTP assertions.

## 4. Pairing Rule: Open Once, Close Once

Treat each test execution's lifecycle as a resource that must be managed:

~~~text
NOT OPEN
   |
   | beforeTest(...)
   v
OPEN
   |
   | request + assertions + document(...)
   |
   | afterTest()
   v
CLOSED
~~~

Key checkpoints:

1. **Open once:** call `beforeTest(...)` exactly once per test execution before the documented request runs.
2. **Do not stack opens:** never call `beforeTest(...)` a second time while a previous context is still open. Re-opening an unclosed context can throw `IllegalStateException`.
3. **Close even when the test fails:** cleanup must live in `finally` or a teardown hook guaranteed to run when assertions throw errors.
4. **Do not reuse a closed context:** the next test needs a fresh `beforeTest(...)` before continuing snippet generation.
5. **Do not share arbitrarily:** if tests run in parallel, you need a dedicated strategy for lifecycle state and output locations to prevent requests from hitting the wrong context or writing to the same files.

### Why Does finally Matter?

Here is error-prone code:

~~~java
restDocs.beforeTest(MyCheck.class, "checkBook");

mockMvc.perform(get("/books/{id}", 42L))
        .andExpect(status().isOk());

restDocs.afterTest(); // Never runs if the assertion above throws an exception.
~~~

A safer structure:

~~~java
restDocs.beforeTest(MyCheck.class, "checkBook");
try {
    mockMvc.perform(get("/books/{id}", 42L))
            .andExpect(status().isOk());
} finally {
    restDocs.afterTest();
}
~~~

The `try/finally` structure guarantees a **cleanup attempt** whether the test body completes normally or throws an exception/error. When a program is terminated abruptly at the process level, there is no guarantee `finally` will execute; therefore, the build also needs reliable output cleaning and regeneration mechanisms.

## 5. Complete Example: TestNG + MockMvc + JSON Snippets

This example uses **TestNG** to demonstrate a JUnit-independent lifecycle. The test suite builds MockMvc for a simple controller; each test opens the context in `@BeforeMethod` and closes it in `@AfterMethod`.

Prerequisites: the project has **Java 17+**, Spring MVC Test, Spring REST Docs MockMvc, **TestNG**, and a Jackson JSON converter. With Gradle, configure `useTestNG()` instead of only running JUnit Platform.

~~~java
import java.lang.reflect.Method;

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

public class BookDocumentationTestNgTest {

    private final ManualRestDocumentation restDocs =
            new ManualRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;
    private boolean documentationOpen;

    @BeforeMethod
    public void setUp(Method method) {
        restDocs.beforeTest(getClass(), method.getName());
        documentationOpen = true;

        try {
            mockMvc = MockMvcBuilders
                    .standaloneSetup(new BookController())
                    .apply(documentationConfiguration(restDocs))
                    .build();
        } catch (RuntimeException | Error setupError) {
            try {
                closeDocumentation();
            } catch (RuntimeException | Error cleanupError) {
                setupError.addSuppressed(cleanupError);
            }
            throw setupError;
        }
    }

    @Test
    public void getBookCreatesSnippets() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON)
                        .header("X-Trace-Id", "trace-example-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get-success",
                        pathParameters(
                                parameterWithName("id")
                                        .description("The identifier of the book")
                        ),
                        requestHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Sample request tracking ID")
                        ),
                        responseFields(
                                fieldWithPath("id")
                                        .description("The identifier of the book"),
                                fieldWithPath("title")
                                        .description("The title of the book")
                        )
                ));
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        closeDocumentation();
    }

    private void closeDocumentation() {
        if (documentationOpen) {
            try {
                restDocs.afterTest();
            } finally {
                documentationOpen = false;
            }
        }
    }

    @RestController
    static class BookController {
        @GetMapping(value = "/api/books/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public BookResponse getBook(@PathVariable("id") Long id) {
            return new BookResponse(id, "Spring REST Docs");
        }
    }

    record BookResponse(Long id, String title) {}
}
~~~

### Why Open the Context at the Beginning of @BeforeMethod?

The `setUp` step calls `beforeTest(...)` **before** building MockMvc and applying `documentationConfiguration(restDocs)`. This layout is clear: every REST Docs component is configured within an already opened test scope. Afterwards, the `@Test` method sends the request and calls `document(...)`.

### Why Is There a documentationOpen Flag?

The `documentationOpen` flag distinguishes two cases:

- `beforeTest(...)` did not succeed yet: cleanup will not be called mistakenly on an unopened context.
- `beforeTest(...)` succeeded: teardown or the setup catch branch calls `afterTest()` exactly once.

`@AfterMethod(alwaysRun = true)` supports cleanup even when an assertion in the test fails. The `catch` branch in `setUp` adds handling for cases where **MockMvc setup fails after the context was opened**, because you should not rely solely on whether the framework executes teardown after a failed setup configuration.

In this example, `documentationOpen` is a simple field because **test methods on the same instance are assumed to run sequentially**. When enabling TestNG parallel mode, this design must change so state belongs to each test execution; never share a boolean or `ManualRestDocumentation` instance without proper coordination.

### How Are Assertions and Snippets Connected?

In the test:

- `RestDocumentationRequestBuilders.get(...)` preserves the `/api/books/{id}` URL template needed for the path parameter snippet.
- `.andExpect(...)` verifies the response has status `200`, `id = 42`, and `title = "Spring REST Docs"`.
- `.andDo(document("books-get-success", ...))` writes the HTTP snippets and documents path parameters, request headers, and JSON response fields.

Typical output:

~~~text
build/generated-snippets/books-get-success/
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    path-parameters.adoc
    request-headers.adoc
    response-fields.adoc
~~~

The exact files and count also depend on default snippet configuration. The identifier `books-get-success` determines the subdirectory name; `beforeTest(..., "getBookCreatesSnippets")` only provides the test identity for the context.

## 6. Using try/finally Without a Test Framework

For an application-driven HTTP verification suite (without TestNG/JUnit), you can encapsulate the lifecycle in a helper function:

~~~java
static void runDocumentedCheck(
        ManualRestDocumentation docs,
        String methodName,
        ThrowingCheck check) throws Exception {

    docs.beforeTest(CustomHttpChecks.class, methodName);
    try {
        check.run();
    } finally {
        docs.afterTest();
    }
}

@FunctionalInterface
interface ThrowingCheck {
    void run() throws Exception;
}
~~~

Usage in verification code:

~~~java
ManualRestDocumentation docs =
        new ManualRestDocumentation("build/generated-snippets");

runDocumentedCheck(docs, "verifyBookResponse", () -> {
    MockMvc mvc = MockMvcBuilders
            .standaloneSetup(new BookController())
            .apply(documentationConfiguration(docs))
            .build();

    mvc.perform(get("/api/books/{id}", 42L))
            .andExpect(status().isOk())
            .andDo(document("books-manual-check"));
});
~~~

This is an **illustrative skeleton**: `CustomHttpChecks`, `BookController`, imports, and exceptions need to be placed in the same real test program. `get(...)` here should be the request builder from Spring REST Docs if you plan to document path parameters.

Using a callback guarantees **no caller forgets `afterTest()`** in the main execution path. However, a single `ManualRestDocumentation` instance should still only be used according to your chosen lifecycle policy; do not share it arbitrarily across threads.

### What If Cleanup Also Throws an Error?

In Java, an exception thrown from `finally` can mask the original test exception. When full diagnostics are needed, a wrapper can attach the cleanup error as a **suppressed exception** instead of losing the initial stack trace. The TestNG example in Section 5 already uses this pattern when **setup** fails. In a complete test helper library, the same principle should apply to test execution as well.

At the level of this lesson, the foundational rule is: **failing tests must still perform cleanup**, while preserving the primary failure cause for investigation.

## 7. Error-Prone State Transitions

### 7.1. Calling beforeTest Twice Without afterTest

~~~java
restDocs.beforeTest(MyChecks.class, "caseA");

// Missing afterTest()
restDocs.beforeTest(MyChecks.class, "caseB"); // Invalid lifecycle.
~~~

The instance already has an open context; the subsequent `beforeTest` call can throw `IllegalStateException`. Finish case A first:

~~~java
restDocs.beforeTest(MyChecks.class, "caseA");
try {
    // Test A.
} finally {
    restDocs.afterTest();
}

restDocs.beforeTest(MyChecks.class, "caseB");
try {
    // Test B.
} finally {
    restDocs.afterTest();
}
~~~

### 7.2. Placing afterTest After Assertions Without finally

If the request or assertion throws an exception, the trailing cleanup line is skipped. Move cleanup into `finally` or `@AfterMethod(alwaysRun = true)` and guard against failed setup as shown in the previous example.

### 7.3. Closing the Context Too Early

~~~java
restDocs.beforeTest(MyChecks.class, "caseA");
restDocs.afterTest();

// Running the request and document(...) only now: wrong timing.
~~~

The context must remain active while the HTTP client performs the operation to be documented.

### 7.4. Calling document Without Configuring the Client

For MockMvc, the following step is mandatory:

~~~java
mockMvc = MockMvcBuilders
        .standaloneSetup(new BookController())
        .apply(documentationConfiguration(restDocs))
        .build();
~~~

If you build another MockMvc **without applying** REST Docs configuration and call `document(...)` on it, the test may fail to write snippets properly. Simply calling `beforeTest(...)` does not automatically configure every MockMvc instance.

### 7.5. Configuring Output While the Build Reads the Wrong Place

~~~java
new ManualRestDocumentation("build/api-snippets");
~~~

In this case, Asciidoctor cannot guess that snippets live in `build/api-snippets` if the build still points to `build/generated-snippets`. The root directory in the constructor, the identifier in `document(...)`, and the input path of the documentation build step must all match.

## 8. Multi-Run Tests, Data Providers, and Parallel Execution

A TestNG test method may be invoked multiple times by `@DataProvider`, or multiple methods may run in parallel. Calling `method.getName()` in `beforeTest(...)` can produce **the same method name** for multiple executions. That does not replace choosing a unique identifier when generating snippets.

For example:

~~~java
// Run 1: GET /books/42 -> 200
document("books-get-42-success");

// Run 2: GET /books/404 -> 404
document("books-get-404-not-found");
~~~

Key principles:

| Risk | Mitigation |
| --- | --- |
| Two data runs share `document("books-get")` with different bodies | Assign identifiers by **stable scenario** or split tests; avoid overwrites. |
| Tests in the same class run concurrently sharing `documentationOpen` | Use dedicated objects/lifecycle state per execution; never share unsynchronized mutable state. |
| Two CI processes write to the same directory and identifier | Separate output by job/module or coordinate write ordering. |
| Responses depend on random data | Fix test fixtures and mask dynamic data with appropriate preprocessors before publishing. |
| Multi-run test only asserts on one run | Verify each HTTP branch that needs to be documented. |

**Do not assume `ManualRestDocumentation` solves multi-threading for the entire test suite.** Clearly design lifecycle ownership per execution, snippet identifiers, and output directories. A simple starting option while learning is **sequential execution** with separate tests and identifiers; only expand to controlled concurrency afterwards.

## 9. Applying with Spring TestContext, WebTestClient, and REST Assured

`beforeTest` and `afterTest` are the shared lifecycle of **`ManualRestDocumentation`**, independent of any specific client. Because it is a `RestDocumentationContextProvider`, the integration modules can use the same context object:

| Client | Documentation Hook | Usage Hint |
| --- | --- | --- |
| MockMvc | `MockMvcRestDocumentation.documentationConfiguration(docs)` via `MockMvcBuilders.apply(...)` | In-process MVC testing with standalone controllers or Spring `WebApplicationContext`. |
| WebTestClient | `WebTestClientRestDocumentation.documentationConfiguration(docs)` via `filter(...)` | Testing WebFlux or configured WebTestClient instances. |
| REST Assured | `RestAssuredRestDocumentation.documentationConfiguration(docs)` via a filter on the request specification | Testing live HTTP endpoints. |

With TestNG requiring a Spring ApplicationContext, Spring Test supports integration via `AbstractTestNGSpringContextTests` along with `@ContextConfiguration`, `@WebAppConfiguration`, or project-appropriate configuration. Spring TestContext prepares the beans; `ManualRestDocumentation` must still be opened/closed in manual hooks.

Condensed example for WebTestClient:

~~~java
docs.beforeTest(MyReactiveApiTest.class, "getBook");
try {
    WebTestClient client = WebTestClient.bindToController(controller)
            .configureClient()
            .filter(WebTestClientRestDocumentation
                    .documentationConfiguration(docs))
            .build();

    // client.get() ... exchange() ... expectStatus()
    // ... consumeWith(document("books-webtestclient-get")).
} finally {
    docs.afterTest();
}
~~~

This is a **conceptual skeleton**, requiring a `controller` instance, imports, and a compatible `spring-restdocs-webtestclient` dependency; calling `document(...)` in WebTestClient differs from MockMvc. With REST Assured, configure the `RestAssuredRestDocumentation.documentationConfiguration(docs)` filter in the request specification, then use the REST Assured `document(...)` filter.

Across all three tools, the timing rule is identical: **open context → execute documented request → close context**.

## 10. Snippet Output and Build/CI Integration

Suppose you construct `ManualRestDocumentation` with:

~~~java
new ManualRestDocumentation("build/generated-snippets")
~~~

and inside the test call:

~~~java
document("books-get-success", ...)
~~~

then the expected output directory is:

~~~text
build/generated-snippets/books-get-success/
~~~

This follows the **root directory** (`build/generated-snippets`) and **identifier subdirectory** (`books-get-success`) model. Relative paths are affected by the test task's working directory, especially in multi-module builds.

Example Asciidoctor page:

~~~asciidoc
= Books API

== Get Book by ID

=== HTTP request
include::{snippets}/books-get-success/http-request.adoc[]

=== Path parameter
include::{snippets}/books-get-success/path-parameters.adoc[]

=== Request headers
include::{snippets}/books-get-success/request-headers.adoc[]

=== HTTP response
include::{snippets}/books-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/books-get-success/response-fields.adoc[]
~~~

The `{snippets}` attribute must be configured in the Asciidoctor task to point to the **root directory**. Default snippets are usually generated as `.adoc`; outputting Markdown requires a compatible compilation/conversion step.

Example Gradle Groovy DSL when using TestNG and an Asciidoctor plugin with an `asciidoctor` task:

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

`attributes` syntax may vary by plugin version. What must be verified is that **the test task runs successfully first**, **snippets exist**, and **the compilation step reads the right output**.

For Maven, the common directory is `target/generated-snippets`. If tests use this path, configure the documentation build plugin to read snippets from the same location. Avoid writing test output to `build/generated-snippets` while the plugin defaults to reading `target/generated-snippets`.

A CI pipeline can execute:

~~~text
1. Build dependencies, select the right TestNG/custom test runner
2. Run documentation-generating tests
3. Check report: tests were actually discovered and executed
4. Verify generated-snippets/{identifier}/*.adoc
5. Run Asciidoctor or Markdown pipeline
6. Package or publish documentation from the generated artifact
~~~

Before publishing, sanitize sample data so tokens, sensitive cookies, personal information, or real production response payloads do not leak into snippets.

## 11. Troubleshooting by Lifecycle

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `IllegalStateException` when opening a new test | Previous test did not call `afterTest()`, or nested contexts opened | Check `beforeTest`/`afterTest` pairing, including setup error paths. |
| `document(...)` reports missing context | Forgot `beforeTest(...)`, or `afterTest()` was called before the request ran | Put `beforeTest` in setup before the request, and move cleanup to teardown/finally. |
| Failing test causes subsequent tests to omit snippets | Cleanup did not run when an assertion failed | Use `finally` or `@AfterMethod(alwaysRun = true)`, and handle setup failures. |
| Test passes but no snippets exist | Missing `document(...)` or wrong MockMvc instance | Verify the exact executing client and identifier. |
| `pathParameters(...)` does not recognize URL variables | Using a request builder that drops the URL template | Use `RestDocumentationRequestBuilders.get` with path `/api/books/{id}`. |
| Response field descriptors do not match body | JSON contract changed without updating descriptions | Compare assertions, actual JSON, and descriptors. |
| Snippets exist but Asciidoctor cannot find them | Wrong `snippets` attribute, identifier, or task dependency | Check physical paths, includes, and build order. |
| TestNG creates no files | Test suite did not run or only the JUnit engine ran | Check `useTestNG()`, test runtime config, and test count reports. |
| Two parallel tests overwrite files | Shared identifier/output or mutable lifecycle state | Isolate executions, use independent names, and separate outputs if needed. |
| Teardown callback throws a different error than the assertion | Cleanup itself threw an exception, hiding the root cause | Preserve the original exception and attach cleanup errors as suppressed in shared helpers. |

An effective investigation order is: **test runner → `beforeTest` → client configuration → request/assertions → `document` → `afterTest` → snippet files → Asciidoctor/Markdown build**.

## 12. Lifecycle Verification Practice

Using `BookDocumentationTestNgTest` from Section 5:

1. Run the test with TestNG, verify HTTP `200`, and locate `http-request.adoc`, `request-headers.adoc`, and `response-fields.adoc`.
2. Temporarily remove `beforeTest(...)` in setup. Note the error or missing context when REST Docs is invoked. Restore the call.
3. Add a second test to the same class. Ensure each test opens and closes its own context with no overlapping-open errors.
4. Temporarily alter an `assertion` so the test fails. Verify teardown still invokes cleanup; restore the assertion to the expected value.
5. Add an intentional failure branch in `setUp` **after** `beforeTest`. Verify the catch branch closes the context and preserves the original setup error.
6. Change the identifier to `books-get-by-id-success`; verify the subdirectory changes while the root output dir remains unchanged.
7. Change the output dir to `build/api-snippets`, update Asciidoctor configuration, and rebuild the documentation page.
8. If trying parallel TestNG, first redesign state and lifecycle instances per execution; choose unique identifiers and confirm files do not overwrite each other.
9. Hook tests and the compilation task into CI, verifying the build fails when assertions fail or required snippets are missing.

**Completion criteria:** you can point out where the **context is opened**, where the **context is closed**, why `finally`/teardown is needed, which client is configured with REST Docs, which call generates snippets, and which build step consumes them.

## 13. Summary

- `ManualRestDocumentation` is suitable when managing the REST Docs lifecycle manually outside JUnit, such as with TestNG or custom runners.
- `beforeTest(Class<?>, String)` **opens the context per test run**; `afterTest()` **ends the context**. Both calls must be paired and cleanup must run even when tests fail.
- Lifecycle context, HTTP client configuration, and `document(identifier, ...)` are **three distinct responsibilities**; missing any one means documentation may not be generated properly.
- When running repeated or parallel tests, isolate state and identifier names to avoid overlapping contexts or overwriting snippets.
- Snippets from MockMvc/WebTestClient/REST Assured must be compiled with Asciidoctor/Markdown and wired into build/CI with consistent paths and task ordering.
