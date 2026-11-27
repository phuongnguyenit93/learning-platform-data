# Custom Output Directory for an Extension or Rule

## 1. When Should You Specify an Output Directory?

Spring REST Docs writes snippets into an output directory. By default, this directory is inferred from the build tool: Maven typically uses **target/generated-snippets** and Gradle typically uses **build/generated-snippets**. If you want to group snippets into a separate directory, store them according to your project structure, use a temporary directory for a test suite, or isolate outputs across documentation groups, you can pass a custom path when creating the extension or rule that manages the documentation lifecycle.

The configuration point resides in the test framework:

| Test framework | Context management component | How to set the output directory |
| --- | --- | --- |
| JUnit Jupiter (JUnit 5/6) | RestDocumentationExtension | Constructor `RestDocumentationExtension(String outputDirectory)` |
| JUnit 4 | JUnitRestDocumentation rule | Constructor `JUnitRestDocumentation(String outputDirectory)` |
| TestNG or self-managed framework | ManualRestDocumentation | Constructor `ManualRestDocumentation(String outputDirectory)` |

The output directory is the **root** that REST Docs uses to write snippets. The document identifier in the `document(...)` call continues to create subdirectories beneath this root. For example, if the output directory is `build/docs-snippets` and the identifier is `orders/create`, the snippets are written under `build/docs-snippets/orders/create/`.

In the **SPRING_REST_DOCS** module, snippets are generated from HTTP tests with MockMvc, WebTestClient, or REST Assured and then fed into Asciidoctor/Markdown documentation and build/CI pipelines. When changing the output directory, you must update the input path of the documentation rendering step at the same time; otherwise, tests may generate snippets successfully while Asciidoctor still looks in the old directory.

## 2. JUnit Jupiter: Customizing with RestDocumentationExtension

### 2.1. Registering the Extension as a Field

With JUnit Jupiter, you can declare the extension as a field using `@RegisterExtension`:

~~~java
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.restdocs.RestDocumentationExtension;

class OrderDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/custom-snippets");

    // Test methods
}
~~~

The constructor accepts the output directory path string. The extension manages `RestDocumentationContext` for each test and provides the context to configure MockMvc, WebTestClient, or REST Assured.

If you do not need a separate path, you can use the class-level extension:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {
}
~~~

By default, the extension chooses the directory based on the build tool. Use the parameterized constructor when you need explicit control over the output location.

### 2.2. Configuring MockMvc with a Registered Extension

Full example:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/custom-snippets");

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(documentation))
            .build();
    }

    @Test
    void documentsOrder() throws Exception {
        this.mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get-one"));
    }
}
~~~

In `BeforeEach`, the extension is activated by JUnit and injects `RestDocumentationContextProvider`. `documentationConfiguration(documentation)` connects the provider to MockMvc; the provider carries the output directory specified in the constructor. The `document("orders/get-one")` call creates subdirectories based on the identifier.

The example assumes the controller and required dependencies are already present in the test context. Mock setup details depend on the application; the focus here is the extension and output path.

### 2.3. Configuring WebTestClient

With WebFlux, use the same provider to configure `WebTestClient`:

~~~java
@BeforeEach
void setUp(
        ApplicationContext applicationContext,
        RestDocumentationContextProvider documentation) {
    this.webTestClient = WebTestClient.bindToApplicationContext(applicationContext)
        .configureClient()
        .filter(documentationConfiguration(documentation))
        .build();
}
~~~

When the test executes a request and calls `consumeWith(document("orders/get-one"))`, Spring REST Docs writes snippets to the output directory managed by the extension. If `WebTestClient` is bound to a controller, router function, or live server, keep the same principle: attach the REST Docs filter using the same `RestDocumentationContextProvider`.

## 3. JUnit 4: Customizing with the JUnitRestDocumentation Rule

JUnit 4 uses `@Rule` with `JUnitRestDocumentation`. Pass your custom directory to the constructor:

~~~java
import org.junit.Rule;
import org.springframework.restdocs.JUnitRestDocumentation;

public class OrderDocumentationTest {

    @Rule
    public JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("target/custom-snippets");

    // MockMvc tests
}
~~~

The rule manages `RestDocumentationContext` for each test method. When configuring MockMvc, pass the rule as the context provider:

~~~java
private MockMvc mockMvc;

@Before
public void setUp() {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(this.restDocumentation))
        .build();
}
~~~

The test can write snippets:

~~~java
mockMvc.perform(get("/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get-one"));
~~~

With the constructor `new JUnitRestDocumentation("target/custom-snippets")`, the output will be at:

~~~text
target/custom-snippets/
└── orders/
    └── get-one/
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
~~~

This mechanism is specifically for JUnit 4. Do not place `JUnitRestDocumentation` in JUnit Jupiter tests as a rule; JUnit Jupiter uses `RestDocumentationExtension`.

## 4. Frameworks Without JUnit Extensions/Rules: ManualRestDocumentation

Spring REST Docs provides `ManualRestDocumentation` for cases where the test framework does not support automatic extensions or rules, typically TestNG or a self-managed test lifecycle.

~~~java
import org.springframework.restdocs.ManualRestDocumentation;

public class OrderTest {

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation("build/custom-snippets");

    @BeforeMethod
    public void beforeMethod(Method method) {
        this.restDocumentation.beforeTest(
                OrderTest.class, method.getName());
    }

    @AfterMethod
    public void afterMethod() {
        this.restDocumentation.afterTest();
    }
}
~~~

When configuring MockMvc, pass `restDocumentation` into `documentationConfiguration(...)` as a `RestDocumentationContextProvider`:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation))
    .build();
~~~

Then, inside the test:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("orders/get-one"));
~~~

Unlike the JUnit extension/rule, `ManualRestDocumentation` must be notified when a test starts and finishes via `beforeTest(...)` and `afterTest()`. Ensure the teardown hook is called even when a test fails; use `try`/`finally` or the framework's teardown mechanism.

## 5. Combining Output Directory and Document Identifier

There are two separate path levels:

1. **Output directory** selects the root directory.
2. **Document identifier** selects the subdirectory for an HTTP operation.

For example:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/api-reference");

mockMvc.perform(get("/orders/42"))
    .andDo(document("orders/get-one"));

mockMvc.perform(post("/orders"))
    .andDo(document("orders/create"));
~~~

Output structure:

~~~text
build/api-reference/
└── orders/
    ├── get-one/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── create/
        ├── http-request.adoc
        └── http-response.adoc
~~~

Do not embed the identifier into the output directory a second time. For example, setting the extension to `build/api-reference/orders` and then using the identifier `orders/get-one` creates a duplicated path `orders/orders/get-one`. Choose a stable root and structure identifiers by resource/action.

## 6. Using Parameterized Identifiers to Separate Snippets by Test

Spring REST Docs supports placeholders in the document identifier:

| Placeholder | Value |
| --- | --- |
| `{methodName}` | Test method name as-is |
| `{method-name}` | Test method name in kebab-case |
| `{method_name}` | Test method name in snake_case |
| `{ClassName}` | Test class name as-is |
| `{class-name}` | Test class name in kebab-case |
| `{class_name}` | Test class name in snake_case |
| `{step}` | Sequence number of the service call in the current test |

For example:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("{class-name}/{method-name}"));
~~~

With class `OrderDocumentationTest` and method `getOrderDetails`, the identifier directory is generated with normalized names:

~~~text
order-documentation-test/get-order-details/
~~~

Placeholders are useful when multiple test methods share documentation configuration and need separate outputs. If a fixed identifier is reused by different tests, snippets with the same name can be written into the same directory, causing overwrites or making them hard to trace.

The `{step}` placeholder is useful when there are multiple service calls within a single test and you want to separate snippets for each call. Use it only when each call has independent documentation value.

## 7. Synchronizing a Custom Output Directory with Asciidoctor

When changing the output directory, Asciidoctor must read from the new directory. For example, if the extension writes to `build/api-reference`:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/api-reference");
~~~

Gradle Groovy DSL:

~~~groovy
def snippetsDir = file('build/api-reference')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
~~~

Asciidoctor:

~~~adoc
= Orders API

== Get Order Details

include::{snippets}/orders/get-one/http-request.adoc[]
include::{snippets}/orders/get-one/http-response.adoc[]
~~~

With Maven, configure the test output and documentation plugin using a shared property, such as the `target/api-reference` directory. Regardless of the build tool, the custom output directory must be consistent in three places: the extension/rule, the build's output/input declarations, and Asciidoctor's `snippets` attribute.

If tests use an extension outputting to `build/api-reference` while Asciidoctor still points to `build/generated-snippets`, includes will report missing files. Check the absolute path or inspect the directory tree after running tests to determine where snippets are actually written.

## 8. Relative Paths vs. Absolute Paths

The extension/rule constructor accepts an output directory string:

~~~java
new RestDocumentationExtension("build/api-reference");
new JUnitRestDocumentation("target/api-reference");
~~~

Relative paths are convenient because the project can run on developer machines and in CI without modifying source code. Use an absolute path only when the build environment has a clearly configured fixed location; avoid hardcoding personal machine paths.

In multi-module projects, verify which module the tests run in and which working directory/project context of the test process resolves relative output directories. If you want to centralize snippets at the repository root, pass a path computed from the project configuration instead of assuming every module shares the same working directory.

## 9. Common Errors

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Extension still writes to default `generated-snippets` | Used class-level extension instead of an instance with constructor path | Register a field with `@RegisterExtension` and pass the output directory |
| JUnit 4 fails to compile with `RestDocumentationExtension` | Used JUnit Jupiter API in JUnit 4 tests | Use `JUnitRestDocumentation` with `@Rule` |
| JUnit Jupiter ignores the rule | Used JUnit 4-style `@Rule` | Use `@RegisterExtension` |
| Tests generate snippets in the right place, but Asciidoctor reports missing files | `snippets` attribute still points to the old directory | Synchronize the attribute and input directory |
| Snippets get mixed up across tests | Multiple tests use the same identifier | Use distinct identifiers, optionally combining `{class-name}` and `{method-name}` |
| Repeated resource segment in path | Output root already contains the resource while identifier repeats it | Keep a shared output root and let identifiers create subdirectories |
| Test framework does not call before/after automatically | Used `ManualRestDocumentation` without lifecycle hooks | Call `beforeTest` and `afterTest` in the framework hooks |
| CI build writes to a developer's local path | Absolute path was hardcoded | Use relative paths or environment-based properties |

## 10. Practice Exercise

Create a test documenting the `GET /orders/{id}` endpoint and configure a custom output directory of `build/team-api-snippets`.

Steps:

1. For JUnit Jupiter, register `RestDocumentationExtension` using `@RegisterExtension` with a constructor accepting `build/team-api-snippets`.
2. Configure MockMvc using `documentationConfiguration(RestDocumentationContextProvider)`.
3. Generate snippets with the identifier `orders/get-one`.
4. Add another test method using the `{class-name}/{method-name}` identifier to observe how outputs are separated.
5. If the project still has JUnit 4 tests, configure them separately using `JUnitRestDocumentation("build/team-api-snippets")` and `@Rule`.
6. Configure Gradle to declare the output/input directories and pass the same path to Asciidoctor's `snippets` attribute.
7. Render the AsciiDoc page and verify that includes read from `build/team-api-snippets/orders/get-one/`.

**Completion criteria:** The extension or rule writes snippets to the custom output directory; document identifiers create the right subdirectories; Asciidoctor reads from the same root; tests do not overwrite each other's snippets.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — RestDocumentationExtension API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationExtension.html)
- [Spring REST Docs — JUnitRestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/JUnitRestDocumentation.html)
- [Spring REST Docs — ManualRestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/ManualRestDocumentation.html)
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/index.html)
