# RestDocumentationExtension in JUnit 5

## 1. Purpose and Role in Spring REST Docs

**`RestDocumentationExtension`** is an extension for **JUnit Jupiter (JUnit 5)** that enables Spring REST Docs to create and manage the documentation context for each test execution. When combining the extension with **MockMvc**, **WebTestClient**, or **REST Assured**, we can generate REST API documentation from actual HTTP requests and responses under test.

This is a link in the **SPRING_REST_DOCS** workflow: write HTTP tests, verify API behavior, generate snippets describing the request/response/payload/parameters/headers, and then use Asciidoctor or a suitable publishing pipeline to build the documentation. The extension is only responsible for the **documentation context and lifecycle**; sending requests, asserting responses, and deciding which snippets to generate are the responsibilities of other components.

After this lesson, you will be able to:

- Register `RestDocumentationExtension` using `@ExtendWith` in JUnit 5 tests.
- Inject `RestDocumentationContextProvider` in `@BeforeEach` and configure MockMvc to generate documentation.
- Understand what happens before, during, and after each test.
- Generate and inspect REST Docs snippets from an HTTP test case.
- Identify errors caused by a missing extension, missing documentation configuration, or using the wrong request builder.

## 2. What Does the Extension Solve?

If you only run a standard MockMvc test, you can verify that an endpoint returns `200 OK` and the expected JSON content. However, MockMvc **does not automatically** turn those results into documentation. Spring REST Docs also needs to know the context of the test case to determine where to store snippets and associate the HTTP operation with the current test execution.

JUnit 5 provides an **extension** mechanism so libraries can participate in the test lifecycle. With REST Docs, the typical integration point is:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class ApiDocumentationTest {
    // Tests and REST Docs configuration go here.
}
~~~

| Component | Role |
| --- | --- |
| `@ExtendWith(RestDocumentationExtension.class)` | Registers REST Docs into the JUnit Jupiter lifecycle. |
| `RestDocumentationContextProvider` | Provides the current documentation context to configure the HTTP test client. |
| `documentationConfiguration(restDocumentation)` | Connects the REST Docs context to MockMvc; other clients have corresponding configuration APIs. |
| `MockMvc` / `WebTestClient` / `REST Assured` | Executes HTTP requests in tests. |
| `document("identifier", ...)` | Instructs REST Docs to write snippets for the HTTP operation under an identifier. |
| Asciidoctor/Markdown and build | Compiles the generated snippets into readable or publishable documentation. |

**Important distinction:** having `@ExtendWith` does not mean every request generates snippets. For the MockMvc example below, you still need to apply `documentationConfiguration(...)` and call `.andDo(document(...))` (or configure an appropriate default documentation handler).

## 3. JUnit 5 Lifecycle and the REST Docs Context

The following diagram illustrates the conceptual flow of a test case; JUnit Jupiter manages the callback order, while the extension supplies the context required by REST Docs.

~~~mermaid
sequenceDiagram
    participant JUnit as JUnit Jupiter
    participant Ext as RestDocumentationExtension
    participant Setup as @BeforeEach
    participant MVC as MockMvc
    participant Docs as Spring REST Docs

    JUnit->>Ext: Start a test
    Ext-->>JUnit: Set up documentation context
    JUnit->>Setup: Call setUp(RestDocumentationContextProvider)
    Setup->>MVC: apply(documentationConfiguration(provider))
    JUnit->>MVC: perform(request)
    MVC-->>JUnit: HTTP response
    JUnit->>JUnit: Verify assertions
    JUnit->>Docs: andDo(document("books-get", ...))
    Docs-->>JUnit: Generate snippets for the tested operation
    JUnit->>Ext: End test
    Ext-->>JUnit: Complete context lifecycle
~~~

Key milestones to understand:

1. **Before the test:** JUnit detects `@ExtendWith` and lets the extension participate in the test execution lifecycle.
2. **Setup:** JUnit can pass `RestDocumentationContextProvider` into a `@BeforeEach` method. We use this provider to configure MockMvc.
3. **Execution:** The test sends a request, asserts status/headers/body, and calls `document(...)` with the appropriate descriptors.
4. **Teardown:** The REST Docs context for the run is completed. The next test receives its own documentation lifecycle.

This context is bound to the **test execution**, so you should not store it in a `static` field or manually create a shared provider across multiple tests. For tests running in parallel, you should also use **distinct snippet identifiers** for different scenarios to avoid writing into the same output directory simultaneously.

`@BeforeEach` is commonly chosen because it sets up a fresh MockMvc instance for each test. For tests using `@TestInstance(PER_CLASS)`, the test instance may be reused, yet you should still prepare the context per test run.

## 4. Preparing Dependencies and the Test Runner

The main example uses JUnit 5, Spring MVC Test, and the `spring-restdocs-mockmvc` module. In a Spring Boot project, test dependencies can typically be declared as follows:

**Maven (Spring Boot manages dependency versions):**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Gradle Kotlin DSL (when using Spring Boot dependency management):**

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.restdocs:spring-restdocs-mockmvc")
}

tasks.test {
    useJUnitPlatform()
}
~~~

If you do not use version management from Spring Boot/BOM, declare compatible versions for your dependencies. JUnit Jupiter must be run via the **JUnit Platform**; having the dependencies on the classpath while running the wrong test engine will prevent the extension from working as expected.

## 5. Complete Example: Documenting a GET Endpoint

The following example includes a self-contained controller to clearly show the relationship between the extension, request, assertions, and snippets. With Java 17+ and the dependencies above, you can place this test class in `src/test/java` of a Spring MVC/Spring Boot project.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookApiDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void shouldDocumentGetBook() throws Exception {
        mockMvc.perform(get("/books/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("The identifier of the book")
                        ),
                        responseFields(
                                fieldWithPath("id")
                                        .description("The identifier of the book"),
                                fieldWithPath("title")
                                        .description("The title of the book")
                        )
                ));
    }

    @RestController
    static class BookController {
        @GetMapping("/books/{id}")
        public BookResponse getBook(@PathVariable("id") Long id) {
            return new BookResponse(id, "Spring REST Docs");
        }
    }

    record BookResponse(Long id, String title) {}
}
~~~

This example uses `standaloneSetup` so there is no need to start the full Spring ApplicationContext. This is suitable for learning the REST Docs mechanism in isolation; in a real project, you can replace the sample controller with your application's controller.

### Explaining Each Connection Point

**`@ExtendWith(RestDocumentationExtension.class)`:** registers the extension with JUnit 5. JUnit uses the extension to prepare the context and resolve the `RestDocumentationContextProvider` parameter in `setUp`.

**`@BeforeEach void setUp(RestDocumentationContextProvider restDocumentation)`:** the method does not create the provider itself. JUnit and the extension collaborate to supply the proper object for the current test execution.

**`.apply(documentationConfiguration(restDocumentation))`:** attaches REST Docs to the MockMvc configuration. Without this call, `.andDo(document(...))` may fail to find the context or lack the necessary REST Docs configuration.

**`RestDocumentationRequestBuilders.get("/books/{id}", 42L)`:** uses `get` imported from **REST Docs**, rather than `MockMvcRequestBuilders.get`, to retain the URL template metadata needed for the `pathParameters` snippet. When only reading the `get(...)` line, it is easy to overlook this difference in the `import static` statement.

**`.andExpect(...)`:** verifies the HTTP response before generating documentation. The documentation is tied to API behavior that has already been verified by assertions.

**`.andDo(document("books-get", ...))`:** the `books-get` identifier determines the snippet directory. `pathParameters(...)` documents the `id` path variable; `responseFields(...)` documents the JSON fields. By default, REST Docs strictly validates the documented response fields, so changing the response structure can cause documentation tests to fail if the descriptors are not updated.

## 6. Generated Output and How to Use It

After the test passes, Spring REST Docs typically writes Asciidoctor snippet files to an output location determined by the build configuration. With standard setups, the directory is:

- Maven: `target/generated-snippets/books-get/`.
- Gradle: `build/generated-snippets/books-get/`.

Inside the `books-get` directory, common snippets include:

| Snippet Name | Content |
| --- | --- |
| `http-request.adoc` | The executed HTTP request. |
| `http-response.adoc` | The received HTTP response. |
| `curl-request.adoc` | A sample curl command reproducing the request. |
| `path-parameters.adoc` | A table of path parameters from `pathParameters(...)`. |
| `response-fields.adoc` | A table of JSON fields from `responseFields(...)`. |

The actual path and list of snippets also depend on your REST Docs configuration. Check the build directory after running the tests rather than assuming the extension will automatically generate a complete documentation page.

If you use **Asciidoctor**, an API page can assemble the files above like this:

~~~asciidoc
= Books API

== Get Book Details

=== HTTP Request
include::{snippets}/books-get/http-request.adoc[]

=== Path Parameters
include::{snippets}/books-get/path-parameters.adoc[]

=== HTTP Response
include::{snippets}/books-get/http-response.adoc[]

=== Response Fields
include::{snippets}/books-get/response-fields.adoc[]
~~~

The Asciidoctor `{snippets}` attribute must be **configured in the documentation build task** to point to the directory containing the snippets, and that task must run **after the tests**. If you write documentation in Markdown, you still need to set up a compatible way to convert or include the snippets in your documentation output; the extension does not perform this compilation step on its own.

The typical pipeline is:

~~~text
JUnit 5 test
   -> MockMvc/WebTestClient/REST Assured
   -> REST Docs document(...)
   -> generated-snippets/
   -> Asciidoctor or Markdown compilation step
   -> published REST API documentation in build/CI
~~~

## 7. Using the Extension with Spring ApplicationContext

`standaloneSetup` is the minimal option. When you need to test realistic Spring MVC configuration (message converters, validation, exception handlers, security, or dependency injection), use `webAppContextSetup` with `WebApplicationContext`.

An example setup skeleton in a Spring Boot project:

~~~java
@WebMvcTest(BookController.class)
@ExtendWith(RestDocumentationExtension.class)
class BookApiWebMvcDocumentationTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // @Test methods continue calling perform(...).andDo(document(...)).
}
~~~

The snippet above is an **integration skeleton**: it requires the corresponding `import` statements, controller, mock dependencies, and application configuration. `@WebMvcTest` already includes `SpringExtension` via Spring Boot's annotations; `RestDocumentationExtension` is added to manage the REST Docs context. If you use JUnit 5 with plain Spring Test, you must register `SpringExtension` alongside the REST Docs extension when tests depend on a Spring context.

Some Spring Boot projects use `@AutoConfigureRestDocs` to automatically integrate REST Docs with the Boot-configured test client. When using that approach, choose **one clear configuration strategy** and verify which client is actually being used, avoiding the assumption that a manually created MockMvc in the test has the same configuration as the MockMvc injected by Boot.

### When Switching HTTP Testing Tools

`RestDocumentationExtension` still handles the JUnit 5 lifecycle, while the API connecting it to the testing tool changes:

| Tool | Documentation Integration |
| --- | --- |
| MockMvc | `MockMvcRestDocumentation.documentationConfiguration(provider)` applied via `MockMvcBuilders`. |
| WebTestClient | `WebTestClientRestDocumentation.documentationConfiguration(provider)` attached to the client via a filter mechanism. |
| REST Assured | `RestAssuredRestDocumentation.documentationConfiguration(provider)` integrated into the request specification/filter. |

Therefore, **the extension does not replace MockMvc/WebTestClient/REST Assured**. It provides the shared context piece for the same documentation-driven testing approach.

## 8. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Check or Fix |
| --- | --- | --- |
| JUnit cannot inject `RestDocumentationContextProvider` into `@BeforeEach`. | Missing `@ExtendWith(RestDocumentationExtension.class)`, or tests are not running on JUnit Jupiter. | Check annotations, JUnit 5 dependencies, and JUnit Platform configuration. |
| `document(...)` reports missing REST Docs context/configuration. | MockMvc has not applied `documentationConfiguration(restDocumentation)`. | Review how MockMvc is initialized in `@BeforeEach`. |
| Test passes, but expected snippet files are missing. | `document(...)` was not called, looking in the wrong output directory, or configuring the wrong client instance. | Check `.andDo(...)`, the identifier, and the actual output path. |
| `pathParameters(...)` cannot find URL parameters. | Mistakenly using `MockMvcRequestBuilders.get` when URL template info is needed. | Use `RestDocumentationRequestBuilders.get` and a URL like `/books/{id}`. |
| Documentation test fails when JSON fields are added/removed in the response. | `responseFields(...)` descriptors do not match the response. | Update assertions and descriptors according to the intended API contract; do not disable validation just to make the test pass. |
| Two tests overwrite or mix up each other's snippets. | Both use `document("books-get")` for non-equivalent scenarios. | Assign distinct identifiers, such as `books-get-success` and `books-get-not-found`. |
| Asciidoctor reports that snippets cannot be found. | Tests have not run before building documentation, or the `snippets` attribute is not configured. | Configure build task dependencies and the snippet path. |

Note: a passing assertion **does not guarantee** complete documentation. For endpoints returning multiple status branches, you should test and document meaningful responses separately, such as `200`, `400`, and `404`. Conversely, a successfully generated snippet does not replace business logic testing and security testing.

## 9. Mini Practice: Verifying Documentation Against API Changes

Starting from the `BookApiDocumentationTest` example:

1. Run the test, open `books-get/http-response.adoc` and `books-get/response-fields.adoc`, and compare them with the actual response.
2. Add an `author` field to `BookResponse` and the returned value in `BookController`, **without** updating `responseFields(...)` yet. Observe how the documentation test catches that the response no longer matches the description.
3. Add an assertion for `author`, then add `fieldWithPath("author").description("Author")` to `responseFields(...)`. Re-run the test and inspect the updated snippet.
4. Create a separate `404 Not Found` case with a different identifier, such as `books-get-not-found`, and document only the response specific to that case.
5. Configure the Asciidoctor step to use the generated snippet directory, ensuring the documentation is built **after** tests pass in CI.

**Completion criteria:** JUnit 5 tests run on the JUnit Platform; the provider is injected in `@BeforeEach`; requests have clear assertions; snippets have distinct identifiers and descriptions matching the HTTP responses; the documentation build step locates the generated files properly.

## 10. Takeaways

- `RestDocumentationExtension` is the bridge between **JUnit Jupiter ↔ Spring REST Docs context**.
- `@ExtendWith` registers the extension; `RestDocumentationContextProvider` is obtained during the test lifecycle, most commonly in `@BeforeEach`.
- `documentationConfiguration(provider)` connects the context to the HTTP client; `document(...)` triggers snippet generation.
- Tests should assert the response **before** using that response as documentation; descriptors help detect contract changes.
- The build/CI pipeline needs to run tests, collect snippets, and compile documentation. Publishing the documentation pages is a separate step from the extension lifecycle.
