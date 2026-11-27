# @RegisterExtension and Custom Output Directories

## 1. When Do You Need to Register RestDocumentationExtension Manually?

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests first verify the request and response; Spring REST Docs then generates snippets for the HTTP request, HTTP response, payload, parameters, headers, and related API elements. Snippets are fed into Asciidoctor or a Markdown compilation pipeline, and then packaged in build and CI.

In the **JUnit and Lifecycle** chapter, we learned that Spring REST Docs can be enabled for JUnit Jupiter using the annotation:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class BookApiTest {
    // ...
}
~~~

This approach is concise when using the default configuration. However, some projects need a **specific output path**, for example:

- A Gradle project wants snippets placed under `build/generated-snippets`.
- A Maven project wants snippets placed in `target/generated-snippets`.
- A CI pipeline needs to read from a specific directory to package or publish documentation.
- A module wants to use a separate directory to avoid mixing snippets from multiple test groups.

With JUnit 5, you can use **`@RegisterExtension`** to directly instantiate `RestDocumentationExtension` and pass the output path to its constructor:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");
~~~

**Distinction:** `@RegisterExtension` is a **JUnit Jupiter** annotation used to register a pre-constructed extension instance; `RestDocumentationExtension` is the **Spring REST Docs** extension. The constructor accepting a path configures the extension's output directory. This annotation does not execute HTTP requests or compile complete documentation by itself.

After this lesson, you will be able to use `@RegisterExtension` properly, inspect the actual snippet directory, and synchronize paths across tests, Asciidoctor, and CI.

## 2. How Does @ExtendWith Differ from @RegisterExtension?

Both mechanisms register an extension with JUnit Jupiter, but they differ in how the extension is instantiated.

| Criterion | `@ExtendWith(RestDocumentationExtension.class)` | `@RegisterExtension` |
| --- | --- | --- |
| Registration method | Declares the extension **class** | Declares a **field** holding the extension instance |
| Who instantiates it? | JUnit | The test code |
| Passing custom constructor arguments | Not directly via the annotation | Yes, when creating the instance |
| Configuring output directory | Uses the default or another configuration mechanism | Passes the path via `new RestDocumentationExtension("...")` |
| Registration scope | On a class, method, or composed annotation per JUnit rules | On a field of the test class |
| Common use case | Standard REST Docs setup | Need control over extension creation/configuration |

Comparison example:

~~~java
// Approach A: JUnit creates the extension from the declared type.
@ExtendWith(RestDocumentationExtension.class)
class DefaultOutputDocumentationTest {
    // ...
}

// Approach B: The test creates the extension with a specific output path.
class CustomOutputDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/generated-snippets");
}
~~~

In Approach B, there is no need to also declare `@ExtendWith(RestDocumentationExtension.class)` on the same class just to activate that extension. Duplicate registration can make configuration harder to follow. When a Spring context is needed, you can register **`SpringExtension` separately** (via `@ExtendWith` or a Spring Boot annotation) while using `@RegisterExtension` for REST Docs.

### Instance Fields vs. Static Fields in JUnit Jupiter

JUnit Jupiter allows registering extensions via either a `static` field or an instance field:

~~~java
// Instance field: used per test instance.
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");
~~~

~~~java
// Static field: extension instance created at class scope.
@RegisterExtension
static final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");
~~~

This choice affects **when the extension is registered** in the JUnit lifecycle. A `static` field is registered earlier so it can participate in class-level callbacks supported by an extension; an instance field is registered after the test instance is created. For documenting individual HTTP requests in `@BeforeEach` and `@Test`, using an **instance field** keeps the code readable and ties configuration to the test object.

Do not assume that using a `static` field merges snippets into a single test. REST Docs still binds documentation writing to the context of the current test execution; file collisions mainly come from the **identifier** in `document(...)` and the chosen output location.

## 3. How Does RestDocumentationExtension Use the Output Path?

The constructor takes the form:

~~~java
new RestDocumentationExtension("build/generated-snippets")
~~~

The string passed in is the **root directory for snippets**. When a test calls:

~~~java
document("books-get")
~~~

REST Docs writes the generated files into a subdirectory matching the identifier, for example:

~~~text
build/
└── generated-snippets/
    └── books-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── httpie-request.adoc
        └── ... (additional snippets requested by the test)
~~~

The exact filenames and count depend on the REST Docs version, default snippet configuration, and descriptors used. If the test includes `pathParameters(...)` or `responseFields(...)`, those generate their corresponding descriptor snippets.

**Note on relative paths:** `"build/generated-snippets"` is typically resolved relative to the working directory of the test runner process. In multi-module builds or when the IDE and CI configure different working directories, the exact same path string can point to different physical directories. Verify the path in the official build environment, especially when running from an IDE.

Guidelines for choosing the output directory:

1. Place the directory under the **build output area** (such as `build/` or `target/`) when appropriate for the project's tooling.
2. Use the exact same directory across the **extension, test task, and documentation compilation tool**.
3. Use stable, readable identifiers for each scenario, such as `books-get-success` or `books-get-not-found`.
4. Do not reuse the same identifier for tests with different snippet contents running in parallel.
5. If test types need separation, you can specify different output directories for **separately configured test suites** while updating the build to collect from all of them properly.

## 4. Complete Example: JUnit 5, MockMvc, and Custom Output

This example uses a minimal controller, standalone `MockMvc`, and `@RegisterExtension` to output snippets into `build/generated-snippets`.

To run this in a Spring Boot project with Spring MVC, you need compatible test dependencies such as `spring-boot-starter-test` and `spring-restdocs-mockmvc`, along with Jackson infrastructure for JSON. Plain Spring Framework applications must also declare the corresponding MVC/Test/Jackson/JUnit dependencies.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
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

class BookDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/generated-snippets");

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new BookController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentGetBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 7L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get-success",
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
        @GetMapping(value = "/api/books/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        BookResponse getBook(@PathVariable("id") Long id) {
            return new BookResponse(id, "Spring REST Docs");
        }
    }

    record BookResponse(Long id, String title) {}
}
~~~

### Analyzing Key Lines

**`@RegisterExtension`** registers the instantiated `RestDocumentationExtension` object. Thanks to the constructor, the test explicitly chooses the output directory.

**`@BeforeEach setUp(RestDocumentationContextProvider documentation)`** receives a parameter resolved by the REST Docs extension for the current test execution. You do not manually instantiate `RestDocumentationContextProvider`.

**`.apply(documentationConfiguration(documentation))`** configures the REST Docs processor on the exact `MockMvc` instance that will execute requests. Forgetting this step leaves `document(...)` calls without proper snippet-writing infrastructure.

**`RestDocumentationRequestBuilders.get`** is a crucial import. `pathParameters(...)` requires URL template information; using the REST Docs builder records `"/api/books/{id}"` instead of only a substituted path.

**`.andExpect(...)`** verifies the HTTP response. **`.andDo(document("books-get-success", ...))`** creates documentation tied to the verified response. The `pathParameters` and `responseFields` descriptors define the endpoint's contract.

If the test succeeds and the output dir is configured properly, look for:

~~~text
build/generated-snippets/books-get-success/http-request.adoc
build/generated-snippets/books-get-success/http-response.adoc
build/generated-snippets/books-get-success/path-parameters.adoc
build/generated-snippets/books-get-success/response-fields.adoc
~~~

`@RegisterExtension` **does not determine the subdirectory name** `books-get-success`; that name comes from the identifier argument passed to `document(...)`.

## 5. Distinguishing Output Configuration from Client Configuration

A common misconception is thinking that initializing the extension with an output directory automatically documents every MockMvc request. In reality, there are three independent configuration points:

| Configuration Point | Example | What Does It Control? |
| --- | --- | --- |
| Extension registration | `@RegisterExtension` + `new RestDocumentationExtension("build/generated-snippets")` | REST Docs lifecycle and the root output directory |
| Client configuration | `.apply(documentationConfiguration(documentation))` | Which HTTP client is tracked by REST Docs |
| Recording documentation | `.andDo(document("books-get-success", ...))` | Which HTTP operation is recorded, snippet name, and descriptors |

A test can pass its assertions without producing snippets if the documentation recording step is missing. Conversely, a valid identifier cannot rescue a test that lacks REST Docs configuration on the client.

Relationship diagram:

~~~mermaid
flowchart TD
    A["JUnit Jupiter"] --> B["@RegisterExtension"]
    B --> C["RestDocumentationExtension(outputDir)"]
    C --> D["RestDocumentationContextProvider"]
    D --> E["documentationConfiguration(provider)"]
    E --> F["MockMvc/WebTestClient/REST Assured"]
    F --> G["HTTP test + assertions"]
    G --> H["document(identifier, descriptors)"]
    H --> I["outputDir / identifier / *.adoc"]
    I --> J["Asciidoctor/Markdown build"]
    J --> K["REST API documentation page"]
~~~

Here the diagram describes the **flow of responsibilities**, not the detailed internal calls for each client. For WebTestClient or REST Assured, attaching `RestDocumentationContextProvider` to the client uses different syntax than MockMvc, yet follows the same principle: the extension manages the context, the client performs HTTP calls, and `document(...)` generates snippets.

## 6. Combining @RegisterExtension with SpringExtension

If a test uses a Spring `WebApplicationContext` to pull the controller and dependencies from the application, you can combine them:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestWebConfig.class)
@WebAppConfiguration
class SpringMvcDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/generated-snippets");

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(documentation))
                .build();
    }

    // Tests call mockMvc.perform(...).andDo(document(...)).
}
~~~

This is an **integration skeleton**, requiring the appropriate imports and a `TestWebConfig` class containing the MVC/controller configuration. `SpringExtension` handles integrating JUnit Jupiter with Spring TestContext and dependency injection. `RestDocumentationExtension` is still registered via `@RegisterExtension` to configure the output dir. Neither replaces the other.

### Spring Boot and @AutoConfigureRestDocs

In a Spring Boot project supporting REST Docs auto-configuration, an alternative approach is available:

~~~java
@WebMvcTest(BookController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookBootDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    // Tests execute requests, assertions, and document(...).
}
~~~

This is a **configuration skeleton**: the controller and dependencies used in the slice must be available, and the corresponding imports must be added. With this approach, Spring Boot automatically integrates REST Docs into the Boot-managed MockMvc. When using `@AutoConfigureRestDocs`, you usually **do not need to manually instantiate `RestDocumentationExtension`** just to specify an output dir. Choose one consistent configuration strategy for the test's actual client.

**Do not accidentally mix two output paths:** for example, a test manually creating `RestDocumentationExtension("build/docs")` while the build reads `build/generated-snippets`. In that case, snippets may have been generated, yet the documentation page still reports missing files.

## 7. Integrating Custom Paths into Gradle, Maven, and CI

Choosing the output dir in JUnit only completes the **snippet generation step**. The final documentation needs to know where to read snippets and must be built after the corresponding tests finish.

### Gradle: Sharing One Path

Suppose tests specify:

~~~java
new RestDocumentationExtension("build/generated-snippets")
~~~

With Gradle Groovy DSL and the Asciidoctor JVM plugin, an illustrative configuration might look like:

~~~groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    useJUnitPlatform()
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
    dependsOn(tasks.named("test"))
    attributes "snippets": snippetsDir
}
~~~

Task names/syntax may need adjustment depending on the plugin version and task types in the project. The core idea is that `test` writes to `snippetsDir`, Asciidoctor uses the same directory, and the documentation build task depends on running tests.

If this is a **Gradle multi-project build**, determine relative paths against the working directory of the test task in the appropriate module. For instance, if snippets are written to `module-a/build/generated-snippets`, an Asciidoctor task in another module must point to that exact physical directory.

### Maven: Aligning with the target Directory

In a Maven project, you can choose:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("target/generated-snippets");
~~~

Then configure the documentation compilation and resource packaging steps to read from `target/generated-snippets`. If you need a different custom directory, update both the extension initialization and the plugin/task configuration that reads snippets. The compilation step must run after the test phase that generates snippets.

### Asciidoctor: Including from the Right Location

Assuming `books-get-success` has been generated, the Asciidoctor section can be written as:

~~~asciidoc
= Books API

== Get Book Details

=== Request
include::{snippets}/books-get-success/http-request.adoc[]

=== Path parameters
include::{snippets}/books-get-success/path-parameters.adoc[]

=== Response
include::{snippets}/books-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/books-get-success/response-fields.adoc[]
~~~

The **`snippets`** attribute must be declared in the Asciidoctor task so it points to the directory used by the extension. `include::{snippets}/...[]` does not automatically infer the path from Java tests.

For Markdown pipelines, Spring REST Docs' default snippets are typically Asciidoctor `.adoc` files, so a suitable conversion or embedding step is required before outputting Markdown or HTML pages. Changing the output dir does not automatically change the snippet format.

### Minimal CI Workflow

~~~text
1. Checkout and prepare the Java runtime
2. Run JUnit Jupiter tests to generate REST Docs snippets
3. Verify outputDir/identifier/*.adoc files exist
4. Build Asciidoctor or Markdown pipeline from the same outputDir
5. Package or publish the generated documentation
~~~

CI should fail if documentation-generating tests fail, or if an include directive requests a missing snippet. Sample data, credentials, tokens, and private information must be sanitized in test requests/responses before publishing to documentation.

## 8. Custom Output Directories and Parallel Testing

Every call to `document("identifier", ...)` uses a subdirectory named after the identifier beneath the output dir. When multiple tests share an output dir, pay attention to:

- **Distinct identifiers per scenario:** `books-get-success`, `books-get-not-found`, `books-create-invalid`.
- **Never share a single identifier** between two concurrent tests writing different responses; output can be overwritten or become flaky.
- **Do not write snippets into source directories** if they are build artifacts meant to be regenerated. Build directories are usually much cleaner for clean/rebuild cycles.
- **Do not assume the Spring context and REST Docs context share the same lifecycle.** Spring can cache `ApplicationContext` across tests; REST Docs binds snippets to the HTTP operation of the currently running execution.
- **Do not vary `outputDir` arbitrarily across IDE, local build, and CI.** If it must change, configure a single source of truth or update all consumers together.

If strict parallel execution is required, look into task isolation, naming, and output placement per test suite. Simply adding `@RegisterExtension` does not guarantee thread/process safety when multiple processes write to the same file.

## 9. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| JUnit cannot provide the `RestDocumentationContextProvider` parameter | Extension not registered, `@RegisterExtension` field not initialized properly, or test not running on JUnit Jupiter | Check annotations, constructor, `useJUnitPlatform()`, and dependency versions |
| Test passes but no snippets exist | Missing `document(...)`, or test is using a different client than the one configured with REST Docs | Verify `perform(...)`, `documentationConfiguration(...)`, and identifier |
| Snippets exist, but in an unexpected directory | Relative path resolved from a different working directory | Check the actual working directory of the test process and physical file paths |
| Asciidoctor reports `http-request.adoc` not found | `snippets` attribute points to wrong path, wrong identifier, or tests have not run | Compare actual directory, `document(...)`, and task dependencies |
| Stale documentation still appears after changing the path | Build is reading a different output dir or reusing stale output | Align output dir in test/build and run a controlled clean/rebuild |
| Two tests overwrite each other's snippets | Duplicate identifier with different content | Use distinct identifiers; consider separating tasks when running in parallel |
| `pathParameters(...)` fails | Using a request builder that does not record the URL template | Use `RestDocumentationRequestBuilders` with a path like `/books/{id}` |
| Boot test has REST Docs configured multiple times | Mixing `@AutoConfigureRestDocs` inconsistently with manual setup | Choose one strategy for the `MockMvc` actually in use |
| Response fields documentation does not match JSON | API contract changed without updating descriptors | Update assertions/descriptors to match the contract to be published |

When diagnosing, follow the sequence: **Is JUnit running the test? → Is the extension registered? → Is REST Docs attached to the HTTP client? → Do assertions pass? → Is `document(...)` called? → Where are snippets written? → Where is Asciidoctor/CI reading from?**

## 10. Practice: Switching Output Dirs and Proving the Build Reads Correctly

Starting from `BookDocumentationTest` in Section 4:

1. Run the test and verify `build/generated-snippets/books-get-success/` contains the corresponding request/response/path parameter/response fields files.
2. Change the constructor to `new RestDocumentationExtension("build/api-reference-snippets")`. Re-run the test and verify new files appear at `build/api-reference-snippets/books-get-success/`.
3. Update the Asciidoctor configuration so `{snippets}` points to `build/api-reference-snippets`. Rebuild the documentation page and verify includes succeed without errors.
4. Set a new identifier `books-get-by-id-success`, re-run the test, and verify the subdirectory changes to match the identifier while the root output dir stays the same.
5. Add a test for an error response (e.g., `404`) using a distinct identifier. Write assertions matching the actual response before calling `document(...)`.
6. Run the pipeline from a clean directory in CI or a reproducible build environment, verifying that documentation is only built **after** snippets are generated.

**Completion criteria:** learners can distinguish the **root directory** in the constructor, the **subdirectory** from `document(identifier)`, and the **input path** of Asciidoctor/Markdown. When changing any one of the three, they know how to adjust the rest so the build does not reference stale or missing snippets.

## 11. Takeaways

- `@RegisterExtension` lets JUnit Jupiter use a **pre-constructed extension instance**, suitable when constructor arguments are needed.
- `new RestDocumentationExtension("...")` sets the **root output directory** for snippets; `document("identifier", ...)` sets the **subdirectory** and generated documentation content.
- Registering the extension alone is not enough: you must properly configure the MockMvc/WebTestClient/REST Assured client and invoke `document(...)` after HTTP assertions.
- With Spring TestContext, you can combine `SpringExtension` and `@RegisterExtension`; with Spring Boot, `@AutoConfigureRestDocs(outputDir = "...")` is another option when using auto-configuration.
- Build and CI must use the **same output path**, execute tests first, and then compile the snippets into Asciidoctor/Markdown documentation.
