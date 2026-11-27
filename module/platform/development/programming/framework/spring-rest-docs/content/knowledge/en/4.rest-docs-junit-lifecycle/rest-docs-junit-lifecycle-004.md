# JUnitRestDocumentation in JUnit 4

## 1. Where Does JUnit 4 Fit in the Spring REST Docs Workflow?

**Spring REST Docs** generates REST API documentation from HTTP tests. Instead of writing request and response descriptions completely by hand, we send requests via **MockMvc**, **WebTestClient**, or **REST Assured**, verify results with assertions, and ask the library to generate **snippets** for the HTTP request, HTTP response, payload, parameters, headers, and other elements. Snippets are then compiled into Asciidoctor/Markdown documentation in the build and CI pipeline.

In the **SPRING_REST_DOCS** module, the **JUnit and Lifecycle** chapter focuses on how to attach Spring REST Docs to a test suite. When using **JUnit Jupiter (JUnit 5)**, the familiar mechanism is `RestDocumentationExtension` with `@ExtendWith` or `@RegisterExtension`. In a project still running **JUnit 4**, the corresponding component is **`JUnitRestDocumentation`**, which works with JUnit 4's **`@Rule`**.

This lesson helps you:

- Properly declare `JUnitRestDocumentation` using `@Rule` and understand why the rule must be executed by JUnit 4.
- Combine the rule with `MockMvcRestDocumentation.documentationConfiguration(...)` to generate snippets from tested requests.
- Specify an output directory, assign identifiers per scenario, and compile documentation with Asciidoctor.
- Distinguish `JUnitRestDocumentation` from `SpringRunner` and `RestDocumentationExtension`.
- Handle common errors in JUnit 4 projects, including cases where the build uses JUnit Platform.

**Scope:** this lesson focuses on the JUnit 4 API for maintaining existing projects. For new projects already using JUnit Jupiter, REST Docs' extension mechanism is usually the more natural choice.

## 2. What is JUnitRestDocumentation?

The `org.springframework.restdocs.JUnitRestDocumentation` class is Spring REST Docs' **JUnit 4 rule**. It provides the documentation context around each test execution, and can optionally accept the snippet directory path upon instantiation.

Common declaration:

~~~java
import org.junit.Rule;
import org.springframework.restdocs.JUnitRestDocumentation;

public class ApiDocumentationTest {

    @Rule
    public final JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation();
}
~~~

If you need to specify the output directory:

~~~java
@Rule
public final JUnitRestDocumentation restDocumentation =
        new JUnitRestDocumentation("build/generated-snippets");
~~~

Here:

- `@Rule` is a **JUnit 4** annotation telling JUnit to apply the rule to each test method.
- `JUnitRestDocumentation` handles the REST Docs context for the test lifecycle.
- The constructor taking `"build/generated-snippets"` selects the **root directory** for writing snippets; the subdirectory name will be determined by `document(identifier, ...)`.
- A standard `@Rule` field must be **`public` and non-`static`** so JUnit 4 recognizes and executes it properly. It can be `final` as shown in the example.

Do not confuse it with `@ClassRule`: that is a **class-scoped** mechanism in JUnit 4. The `JUnitRestDocumentation` configuration in this lesson uses `@Rule` at **test-method scope**, which is suitable when generating documentation for each verified request.

### The Rule Does Not Automatically Record Every HTTP Response

Simply declaring `@Rule` does not mean JUnit will save all requests. With MockMvc, you must also:

1. Use `restDocumentation` to configure MockMvc.
2. Send an HTTP request using MockMvc.
3. Verify the HTTP result with assertions.
4. Call `document("identifier", descriptors...)` to generate snippets.

As a result, documentation stays anchored to **tested API behavior** instead of being produced from unverified descriptions.

## 3. JUnit 4 Lifecycle and the REST Docs Context

JUnit 4 uses a **rule** to wrap the execution of a test. With `JUnitRestDocumentation`, the flow can be visualized as follows:

~~~mermaid
sequenceDiagram
    participant JUnit as JUnit 4
    participant Rule as JUnitRestDocumentation
    participant Setup as @Before
    participant MVC as MockMvc
    participant Docs as Spring REST Docs

    JUnit->>Rule: Apply rule to test method
    Rule-->>JUnit: Prepare documentation context
    JUnit->>Setup: Run setUp()
    Setup->>MVC: apply(documentationConfiguration(rule))
    JUnit->>MVC: perform(request)
    MVC-->>JUnit: HTTP response
    JUnit->>JUnit: andExpect(...) verifies response
    JUnit->>Docs: andDo(document("identifier", ...))
    Docs-->>JUnit: Write snippets to output directory
    JUnit->>JUnit: Run @After if present
    JUnit->>Rule: Complete test execution scope
~~~

The diagram illustrates the responsibility of each step without diving into every internal JUnit callback. The key takeaway is that **the REST Docs context is prepared before `@Before` configures MockMvc**, and the rule finishes the scope of a test after test execution concludes.

| JUnit 4 Component | Role During Documentation |
| --- | --- |
| `@Rule JUnitRestDocumentation` | Prepares and completes the REST Docs context for each test execution. |
| `@Before` | Initializes the HTTP client such as `MockMvc`, applying REST Docs configuration. |
| `@Test` | Executes the HTTP request, assertions, and `document(...)`. |
| `@After` | Cleans up test resources if needed; not a required place for snippet generation. |
| `@RunWith(SpringRunner.class)` | Integrates JUnit 4 with Spring TestContext when the test needs a Spring ApplicationContext. |

**Two different lifecycles:** Spring TestContext may cache `ApplicationContext` across multiple tests; `JUnitRestDocumentation` manages the documentation-writing context of the currently running test. Therefore, you should not assume that Spring context caching allows two tests to share an identifier while keeping independent outputs.

## 4. Dependencies and Running JUnit 4

The example uses Spring MVC Test, Spring REST Docs MockMvc, and JUnit 4. If your project has a BOM or Spring Boot dependency management, choose versions of Spring/Spring REST Docs compatible with the Spring line in use.

### Maven (Illustrating Dependencies in a Version-Managed Project)

~~~xml
<dependencies>
    <dependency>
        <groupId>junit</groupId>
        <artifactId>junit</artifactId>
        <version>4.13.2</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Besides the dependencies above, the project must have Spring MVC and the JSON processor matching the tested controller (such as Jackson). If you do not use a BOM or dependency management, declare explicit compatible versions for `spring-test` and `spring-restdocs-mockmvc`.

### Gradle Groovy DSL (Illustrative)

~~~groovy
dependencies {
    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Artifacts without versions above assume the build already has a BOM/dependency management. If the project uses `spring-boot-starter-test`, verify whether **JUnit 4** and (when needed) **JUnit Vintage** are actually present on the test runtime classpath.

### Distinguishing JUnit 4 Runner and JUnit Platform

- To run JUnit 4 directly, the build must use JUnit 4's test discovery and execution mechanism.
- If Gradle/Maven runs tests through **JUnit Platform**, tests written with `org.junit.Test` and `@Rule` will only run when a compatible **JUnit Vintage TestEngine** is present.
- Enabling `useJUnitPlatform()` in Gradle without Vintage can cause JUnit 4 tests to **not be discovered**; in that case tests will not generate snippets even if the source code looks valid.
- Tests written with `org.junit.jupiter.api.Test` belong to **JUnit Jupiter** and use the REST Docs extension (`RestDocumentationExtension`), not JUnit 4's `@Rule`.

Example Gradle configuration when the project **runs JUnit 4 directly**:

~~~groovy
tasks.named('test') {
    useJUnit()
}
~~~

If the whole project runs on JUnit Platform, configure the Vintage engine and a compatible version instead of blindly copying the `useJUnit()` snippet above.

## 5. Complete Example: JUnit 4 + MockMvc + JSON Response

The following example is a standalone test case: the controller is instantiated directly without starting a Spring ApplicationContext. Consequently, **`SpringRunner` is not needed** in this test.

Assuming an environment with JUnit 4, Spring MVC Test, Spring REST Docs MockMvc, and Jackson supporting JSON responses, place this test class in `src/test/java`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.springframework.http.MediaType;
import org.springframework.restdocs.JUnitRestDocumentation;
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

public class GreetingApiDocumentationTest {

    @Rule
    public final JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;

    @Before
    public void setUp() {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .apply(documentationConfiguration(this.restDocumentation))
                .build();
    }

    @Test
    public void getGreetingProducesDocumentation() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.message").value("Hello, Lan"))
                .andDo(document("greetings-get-success",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Name of the person being greeted")
                        ),
                        responseFields(
                                fieldWithPath("name")
                                        .description("Name from the path parameter"),
                                fieldWithPath("message")
                                        .description("Greeting message content")
                        )
                ));
    }

    @RestController
    static class GreetingController {

        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> greet(@PathVariable("name") String name) {
            Map<String, String> response = new LinkedHashMap<>();
            response.put("name", name);
            response.put("message", "Hello, " + name);
            return response;
        }
    }
}
~~~

### Why Does This Example Generate Snippets?

**1. `@Rule` registers the right lifecycle.** JUnit 4 applies `JUnitRestDocumentation` around the test execution. The constructor selects the root directory `build/generated-snippets`.

**2. `@Before` builds MockMvc with REST Docs.** `standaloneSetup(new GreetingController())` creates an MVC environment for the sample controller. `documentationConfiguration(this.restDocumentation)` connects the rule's context to MockMvc.

**3. The request builder retains path template metadata.** In the `import static` section, `get(...)` is imported from **`RestDocumentationRequestBuilders`**, allowing `pathParameters(...)` to recognize the `{name}` placeholder in the URL.

**4. Assertions verify the API contract.** The test expects `200 OK`, JSON field `name = "Lan"`, and `message = "Hello, Lan"`. If the application changes the response, the assertions or field descriptors can detect the mismatch.

**5. `document(...)` generates snippets.** Identifier `greetings-get-success` is the subdirectory name. The `pathParameters(...)` and `responseFields(...)` descriptors create additional snippets describing the corresponding parts. Spring REST Docs can strictly validate field descriptions so documentation reflects the payload structure under test.

Expected example response:

~~~json
{
  "name": "Lan",
  "message": "Hello, Lan"
}
~~~

After the test passes, the expected files include:

~~~text
build/generated-snippets/
└── greetings-get-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
~~~

The exact filenames also depend on the default snippets and actual configuration of your REST Docs version. The root directory is chosen by the rule; the subdirectory is chosen by `document("greetings-get-success", ...)`.

## 6. Combining JUnitRestDocumentation with SpringRunner

The example in Section 5 tests a standalone controller. If the controller depends on Spring-managed beans or you want to use your actual Spring MVC configuration, combine **`SpringRunner`** with **`JUnitRestDocumentation`**.

In JUnit 4:

- **`@RunWith(SpringRunner.class)`** integrates the test with the **Spring TestContext Framework**, including loading the context and `@Autowired` injection.
- **`@Rule JUnitRestDocumentation`** manages the documentation context for each test.
- **`MockMvcBuilders.webAppContextSetup(...)`** builds MockMvc from the web application context.

Configuration skeleton example:

~~~java
import org.junit.Before;
import org.junit.Rule;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.JUnitRestDocumentation;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit4.SpringRunner;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@RunWith(SpringRunner.class)
@WebAppConfiguration
@ContextConfiguration(classes = TestWebConfiguration.class)
public class SpringMvcApiDocumentationTest {

    @Rule
    public final JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("build/generated-snippets");

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @Before
    public void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // @Test: mockMvc.perform(...).andExpect(...).andDo(document(...))
}
~~~

This is an **integration skeleton**: `TestWebConfiguration` must exist and declare sufficient MVC/controller configuration for the test; add test methods, appropriate imports, and application-specific dependencies before running.

**Separating responsibilities:** `SpringRunner` manages Spring TestContext integration; `JUnitRestDocumentation` supports creating the documentation context. They can coexist because runners and rules are two distinct integration mechanisms in JUnit 4. Registering the rule does not automatically initialize a Spring context; conversely, using SpringRunner does not automatically generate REST Docs documentation.

### With Spring Boot Projects

In Spring Boot versions supporting REST Docs auto-configuration, a controller test can use:

~~~java
@RunWith(SpringRunner.class)
@WebMvcTest(GreetingController.class)
@AutoConfigureRestDocs
public class GreetingBootDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    // @Test: perform(...).andExpect(...).andDo(document(...))
}
~~~

The snippet above is a **conceptual skeleton**, assuming `GreetingController` resides in application code and the dependencies required by `@WebMvcTest` are provided. `@AutoConfigureRestDocs` configures REST Docs on the Spring Boot-managed MockMvc. When using this auto-configuration approach, you typically **do not need to add `@Rule JUnitRestDocumentation`** for that same client.

For modern Boot projects, check the support policy for JUnit 4, the Vintage library, and the annotations belonging to your current version. Legacy integration APIs should not be copied verbatim into a project that has completely migrated to JUnit Jupiter.

## 7. Output Path, Identifiers, and Parallel Testing

`JUnitRestDocumentation` accepts a root directory via its constructor:

~~~java
new JUnitRestDocumentation("target/generated-snippets")
~~~

This configuration typically suits Maven. For Gradle, a common example is:

~~~java
new JUnitRestDocumentation("build/generated-snippets")
~~~

If no path is passed, the library has default conventions for supported build environments. However, in multi-module projects, multi-task builds, or custom CI setups, **passing an explicit path** makes inspection easier.

Suppose you call:

~~~java
document("greetings-get-success")
~~~

Logically, the target directory written to will be:

~~~text
<output-directory>/greetings-get-success/
~~~

**Relative paths** are resolved against the working directory of the test runner process. Therefore, the exact same string `"build/generated-snippets"` can resolve to different locations if the IDE, Maven, Gradle, and CI use different working directories.

Guidelines to follow:

| Decision | Reason |
| --- | --- |
| Choose a root directory consistent with the build | Asciidoctor/CI can locate the right snippets after tests finish. |
| Use a distinct identifier per scenario | Avoids overwrites across success, validation error, and not-found responses. |
| Choose names reflecting API behavior | For example `greetings-get-success`, `greetings-get-not-found`, `greetings-post-invalid`. |
| Never reuse the same identifier for parallel tests with different output | Two threads could write to the same file and produce unstable documentation. |
| Keep generated artifacts under the build directory | Convenient for clean, caching, and packaging mechanisms. |

`@Rule` itself **has no built-in mechanism to guarantee** that two tests sharing an identifier are safe when writing concurrently. Separating directories/identifiers must be part of your test suite design and build tasks.

## 8. Compiling Snippets into Asciidoctor and Markdown Documentation

The test example in Section 5 generates the `greetings-get-success` snippet. An Asciidoctor page can include the files like this:

~~~asciidoc
= Greeting API

== Greet by Name

=== HTTP request
include::{snippets}/greetings-get-success/http-request.adoc[]

=== Path parameters
include::{snippets}/greetings-get-success/path-parameters.adoc[]

=== HTTP response
include::{snippets}/greetings-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/greetings-get-success/response-fields.adoc[]
~~~

The **`{snippets}`** attribute must be set by the compilation task to the **root directory** used by the JUnit rule. Having `.adoc` files in `build/generated-snippets` alone does not produce publishable documentation.

An illustrative Gradle Groovy DSL configuration, assuming the project has already applied the corresponding Asciidoctor plugin and the task is named `asciidoctor`:

~~~groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    // Choose useJUnit() or JUnit Platform + Vintage depending on test runtime.
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir
}
~~~

Attribute syntax may require adjustment depending on the version of the Asciidoctor Gradle plugin used by your project. Whether using Maven, Gradle, or another build system, three pieces must stay aligned:

1. JUnit 4 tests write to the designated **output directory**.
2. Asciidoctor or the Markdown pipeline reads from **that exact output directory**.
3. The documentation build step runs **after** the tests responsible for generating snippets and fails when required inputs are missing.

Spring REST Docs defaults to generating Asciidoctor `.adoc` snippets. If the publishing target is Markdown, you need a conversion pipeline or compatible custom snippet mechanism. Choosing JUnit 4 vs. JUnit 5 does not automatically change the snippet format.

Overall flow:

~~~mermaid
flowchart TD
    A["JUnit 4 Test + @Rule"] --> B["MockMvc / WebTestClient / REST Assured"]
    B --> C["Verify HTTP response"]
    C --> D["document(identifier, descriptors)"]
    D --> E["generated-snippets/identifier/*.adoc"]
    E --> F["Asciidoctor or Markdown pipeline"]
    F --> G["Documentation artifact in build / CI"]
~~~

If the CI pipeline fails to build documentation, check whether **tests are actually being discovered and executed** before modifying the Asciidoctor step. This is often overlooked when a build moves to JUnit Platform without Vintage support for JUnit 4.

## 9. Common Errors with JUnitRestDocumentation

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| JUnit reports invalid `@Rule` field | Field is missing `public` or declared `static` for a regular `@Rule` | Use `@Rule public final JUnitRestDocumentation ...`. |
| JUnit 4 tests are not executed | Build is running Jupiter/JUnit Platform without Vintage | Check test engine, Gradle/Maven config, and executed test count. |
| No snippets appear despite passing assertions | `document(...)` was not called or client is not configured with REST Docs | Check `.andDo(document(...))` and `documentationConfiguration(restDocumentation)`. |
| Calling `document(...)` throws a context error | No active rule or MockMvc has not applied documentation configuration | Check `@Rule` declaration, JUnit 4 lifecycle, and how MockMvc is initialized. |
| `pathParameters(...)` fails to recognize path variables | Using a request builder that does not retain the URL template | Import `RestDocumentationRequestBuilders.get` and request `"/api/greetings/{name}"`. |
| Response fields descriptor mismatch | JSON changed without updating documentation | Compare JSON response with `fieldWithPath(...)` and assertions. |
| `@Autowired WebApplicationContext` is `null` | Test uses Spring context without `SpringRunner` or context setup is incomplete | Check `@RunWith(SpringRunner.class)`, `@ContextConfiguration`, and `@WebAppConfiguration`. |
| Snippets exist, yet Asciidoctor cannot find them | Wrong `snippets` attribute, wrong identifier, or wrong build order | Check physical directory, include paths, and task dependencies. |
| Flaky tests when running in parallel | Tests concurrently write files under the same identifier | Use distinct identifiers and define an output isolation strategy. |
| After upgrading to JUnit 5, `@Rule` stops working | Tests run on Jupiter while the rule belongs to JUnit 4 | Migrate to `RestDocumentationExtension` with `@ExtendWith`/`@RegisterExtension` and configure the provider accordingly. |

You can troubleshoot along this diagnostic chain: **JUnit 4 test actually runs → `@Rule` is valid → MockMvc is configured with REST Docs → request/assertions pass → `document(...)` is called → snippets are written to the right place → Asciidoctor/Markdown reads from the right place**.

## 10. From JUnit 4 to JUnit Jupiter: What Needs to Change

The two JUnit versions use different lifecycle mechanisms. When upgrading, you cannot simply change `import org.junit.Test` to `org.junit.jupiter.api.Test` and keep `@Rule`.

| JUnit 4 | JUnit Jupiter (JUnit 5) |
| --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `org.junit.Before` | `org.junit.jupiter.api.BeforeEach` |
| `org.junit.After` | `org.junit.jupiter.api.AfterEach` |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)`, unless already registered by a Spring meta-annotation |
| `@Rule JUnitRestDocumentation` | `@ExtendWith(RestDocumentationExtension.class)` or `@RegisterExtension` |
| `documentationConfiguration(restDocumentation)` takes the rule object | `documentationConfiguration(provider)` takes the `RestDocumentationContextProvider` of the current test run |
| `JUnitRestDocumentation("build/generated-snippets")` | Can use `@RegisterExtension` with `new RestDocumentationExtension("build/generated-snippets")` |

Example migrating part of a configuration:

**Before — JUnit 4:**

~~~java
@Rule
public final JUnitRestDocumentation restDocumentation =
        new JUnitRestDocumentation("build/generated-snippets");

@Before
public void setUp() {
    mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

**After — JUnit Jupiter:**

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");

@BeforeEach
void setUp(RestDocumentationContextProvider provider) {
    mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
            .apply(documentationConfiguration(provider))
            .build();
}
~~~

The Jupiter example needs the corresponding imports, where `@RegisterExtension` belongs to `org.junit.jupiter.api.extension`. When using `@ExtendWith(RestDocumentationExtension.class)` instead of `@RegisterExtension`, JUnit creates the extension declaratively by class; check how to configure the output dir accordingly.

**Note:** switching test engines can affect lifecycle ordering, parameter validation, Spring context integration, and other testing libraries. Migrate one test suite at a time, verifying executed test counts, assertions, and generated snippets in CI.

## 11. Practice: Maintaining JUnit 4 Documentation in CI

Starting from `GreetingApiDocumentationTest` in Section 5:

1. Run the test with JUnit 4 and verify `greetings-get-success/http-request.adoc`, `http-response.adoc`, `path-parameters.adoc`, and `response-fields.adoc` are present.
2. Temporarily remove `.andDo(document(...))`, re-run from a cleaned output directory, and verify no new snippets are generated for that case. Restore the call.
3. Temporarily remove `.apply(documentationConfiguration(this.restDocumentation))` and observe the error or absence of documentation data when `document(...)` runs; then restore it.
4. Change the constructor path to `"build/api-snippets"`. Re-run the test, then update the Asciidoctor configuration to read from this directory.
5. Add an API error scenario returning `404` with appropriate assertions, using a distinct identifier such as `greetings-get-not-found`.
6. If the project uses JUnit Platform, verify JUnit 4 tests run via Vintage. Compare with what happens when Vintage is missing to understand why tests might go undiscovered.
7. Create a JUnit Jupiter version using `RestDocumentationExtension` and compare snippet locations, response fields content, and documentation build results.

**Completion criteria:** know why `@Rule` and `JUnitRestDocumentation` are needed, and identify where the HTTP client is created, where snippets are written, where output is stored, and the path from tests to published documentation.

## 12. Takeaways

- **`JUnitRestDocumentation` is a JUnit 4 rule** used to provide the REST Docs context across the test lifecycle; declare it with `@Rule` on a valid instance field.
- **`SpringRunner` has a different responsibility**: integrating Spring TestContext with JUnit 4. You only need SpringRunner when tests depend on Spring context infrastructure.
- **MockMvc must still be configured** with `documentationConfiguration(restDocumentation)`; `document(identifier, ...)` selects the HTTP operation and descriptors to generate snippets.
- **The output directory** from the constructor and the **identifier** from `document(...)` must align with the paths used by Asciidoctor/Markdown and CI.
- When migrating to **JUnit Jupiter**, replace the rule mechanism with **`RestDocumentationExtension`**, update lifecycle callbacks, and verify the test engine actually executes the tests.
