# Configuring Spring REST Docs to Use Markdown

## 1. Lesson Objectives

Spring REST Docs generates snippets in Asciidoctor format by default. If your project uses Markdown as its primary documentation format, you can configure Spring REST Docs to generate **Markdown snippets directly** using the built-in template format. HTTP tests still produce requests/responses; descriptors still describe and verify payloads; only the snippet file format changes.

This lesson belongs to the **Markdown** chapter of the **SPRING_REST_DOCS** module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; and then assembles the documentation and integrates it into the build/CI pipeline.

After this lesson, you will be able to select the Markdown format, configure each HTTP client, understand output files and custom templates, assemble snippets into final pages, and verify the pipeline.

> Markdown snippets do not create a complete API website on their own. You still need narrative documentation, a snippet assembly tool, a Markdown renderer, and a publish step.

## 2. Markdown Template Format

Spring REST Docs provides two built-in template formats:

| Format | ID | Extension |
| --- | --- | --- |
| Asciidoctor | `asciidoctor` | `.adoc` |
| Markdown | `markdown` | `.md` |

Configure the Markdown format via:

~~~java
.snippets().withTemplateFormat(TemplateFormats.markdown())
~~~

This is a setting on `RestDocumentationConfigurer`. It changes how snippets are rendered, without changing how tests send requests, receive responses, or declare descriptors.

The six default snippets in modern versions include `curl-request`, `http-request`, `http-response`, `httpie-request`, `request-body`, and `response-body`. The `request-fields`, `response-fields`, `path-parameters`, `query-parameters`, and headers tables are only generated when tests declare the appropriate descriptors.

## 3. Configuring with MockMvc

Illustrative dependencies for Spring Boot 3.x, JUnit 5, Java 17+:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Use the JUnit 5 extension and select the Markdown format when creating MockMvc:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.templates.TemplateFormats;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class MarkdownDocumentationTest {
    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
            .build();
    }
}
~~~

Test that generates snippets:

~~~java
@Test
void documentGetOrder() throws Exception {
    this.mockMvc.perform(get("/api/orders/101")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(101))
        .andDo(document("orders-get",
            responseFields(
                fieldWithPath("id").description("Order ID"),
                fieldWithPath("status").description("Order status"),
                fieldWithPath("total").description("Total amount in VND")
            )
        ));
}
~~~

The example assumes the endpoint and fixture return JSON containing the exact described fields. Appropriate imports and test context are required. If using `@AutoConfigureRestDocs`, you can configure this via the corresponding customizer for your Spring Boot version; ensure that the exact MockMvc instance used by the test has the Markdown configurer attached.

Example output:

~~~text
build/
└── generated-snippets/
    └── orders-get/
        ├── curl-request.md
        ├── httpie-request.md
        ├── http-request.md
        ├── http-response.md
        ├── request-body.md
        ├── response-body.md
        └── response-fields.md
~~~

The output directory depends on the context/configuration. Body snippets may be empty if the operation has no body; `response-fields` is only generated when `responseFields(...)` is declared.

## 4. Configuring with WebTestClient

With Spring WebFlux, attach the Markdown format to the documentation filter:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.templates.TemplateFormats;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class WebFluxMarkdownDocumentationTest {
    @Autowired
    private ApplicationContext context;

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
            .configureClient()
            .filter(documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.markdown()))
            .build();
    }
}
~~~

Test:

~~~java
webTestClient.get()
    .uri("/api/orders/101")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(101)
    .consumeWith(document("orders-get-webflux",
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Status"),
            fieldWithPath("total").description("Total amount")
        )
    ));
~~~

Use the `spring-restdocs-webtestclient` dependency. The example binds to `ApplicationContext`; if your project binds to a server or another client, place the filter on the exact client used by the test.

## 5. Configuring with REST Assured

REST Assured uses a REST Docs filter. Select the Markdown format in `RequestSpecification`:

~~~java
RequestSpecification specification =
    new RequestSpecBuilder()
        .addFilter(documentationConfiguration(restDocumentation)
            .snippets()
            .withTemplateFormat(TemplateFormats.markdown()))
        .build();
~~~

Test:

~~~java
given(specification)
    .filter(document("orders-get-restassured"))
    .accept("application/json")
.when()
    .get("/api/orders/101")
.then()
    .statusCode(200);
~~~

The specification must be configured with the server/base URI, port, and REST Docs context. The filter may write the operation after receiving the response but before final assertions complete; CI should only publish when the entire test suite passes.

## 6. Snippet Content Formatting

Example Markdown content of an HTTP request snippet:

~~~http
GET /api/orders/101 HTTP/1.1
Accept: application/json
~~~

Example response fields table:

~~~markdown
|Path|Type|Description|
|---|---|---|
|id|Number|Order ID|
|status|String|Order status|
|total|Number|Total amount in VND|
~~~

Default Markdown tables use **Markdown Extra** syntax. Not every minimal Markdown parser supports tables; verify your actual renderer/site generator.

REST Docs generates the verifiable parts. Hand-written content is still needed to explain endpoint purpose, authentication, business rules, operation sequences, limitations, and common errors.

## 7. Organizing Output and Identifiers

Identifiers should be stable, describe the resource and scenario, and distinguish success/error cases. For example, `orders-get-success` and `orders-get-not-found`. Do not reuse the same identifier for two different operations within the same output set.

The directory structure can look like:

~~~text
build/generated-snippets/
├── orders-get-success/
├── orders-get-not-found/
├── orders-create/
└── orders-search/
~~~

With multiple test modules, standardize the output directory or use clear merge rules to prevent tasks from overwriting each other's snippets.

## 8. Custom Markdown Templates

Spring REST Docs uses Mustache templates. When Markdown is selected, templates are loaded by format ID `markdown` from the package:

~~~text
org/springframework/restdocs/templates/markdown/
~~~

Example template files:

~~~text
src/test/resources/org/springframework/restdocs/templates/markdown/
├── http-response.snippet
└── response-fields.snippet
~~~

To override a snippet:

1. Obtain the original template for the exact Spring REST Docs version in use.
2. Place the template with the same name in the Markdown package under test resources.
3. Change only what is necessary, keeping important variables/snippet attributes intact.
4. Run tests to verify the overridden template is loaded.
5. Compare before/after output to detect missing fields or incorrect escaping.

Do not copy Asciidoctor templates into the Markdown package because table syntax, code fences, and escaping differ.

You can attach metadata to field descriptors and customize the template to add custom columns, such as a Constraint column. Project-defined attributes will not automatically appear in default templates unless the template reads them.

## 9. Assembling Markdown Snippets into Final Documentation

Markdown does not define a standard syntax to include one Markdown file inside another. Generating Markdown snippets and assembling them into final pages are two separate steps.

You can use:

- Slate or a static site generator that supports includes/partials.
- An include plugin for the Markdown system in use.
- A custom build task that reads snippets and assembles them into pages according to a template.
- A preprocessing step that creates complete Markdown pages before the renderer runs.

Conceptual example of a final page:

~~~markdown
# Orders API

## Get Order

Endpoint returns order information by ID.

### HTTP request
Content assembled from snippet orders-get-success/http-request.md.

### HTTP response
Content assembled from snippet orders-get-success/http-response.md.

### Response fields
Content assembled from snippet orders-get-success/response-fields.md.
~~~

The lines above only describe where snippets should be assembled, not Markdown include directives. The build tool must replace them with actual file contents or use that tool's own syntax.

### 9.1. Choosing a Markdown Dialect

Verify that the renderer supports:

- Markdown Extra tables.
- Fenced code blocks and inline code.
- Relative links/images.
- Includes/partials.
- Syntax highlighting if needed.

If descriptor tables render incorrectly, configure the appropriate extension or customize the template for the target dialect. Do not manually edit raw snippets generated from tests.

## 10. Markdown or Asciidoctor?

| Criterion | Markdown | Asciidoctor |
| --- | --- | --- |
| Configuration | `TemplateFormats.markdown()` | Default format. |
| Extension | `.md` | `.adoc` |
| Tables | Markdown Extra | Asciidoc table. |
| Including snippets | Requires additional tooling | Has an include directive. |
| Ecosystem | Git hosting and popular static sites | Long-form technical documentation. |
| Custom templates | Package under Markdown format ID | Package under Asciidoctor format ID. |

Markdown is a good fit when your team's docs platform already uses Markdown, the renderer/dialect is clear, and a snippet assembly mechanism is in place. Asciidoctor is convenient when direct includes are needed. Choose based on your project's documentation system.

## 11. Encoding and Multilingual Content

Keep snippets and hand-written content in UTF-8. Check output files after tests, ensure response bodies have no garbled characters, verify the renderer uses UTF-8, and ensure locale does not accidentally depend on a developer's machine. Normalize line endings/whitespace in a unified build step rather than manually editing individual snippets.

Spring REST Docs allows configuring snippet encoding via the configurer. Only change encoding when compatibility requires it; UTF-8 is usually appropriate for web documentation.

## 12. Build and CI

~~~mermaid
flowchart TD
    A["Compile test sources"] --> B["Run HTTP tests"]
    B --> C{"Assertions pass?"}
    C -->|No| D["Fail CI"]
    C -->|Yes| E["Generate Markdown snippets"]
    E --> F["Assemble Markdown pages"]
    F --> G["Run Markdown renderer"]
    G --> H{"Includes and render pass?"}
    H -->|No| D
    H -->|Yes| I["Package / Publish"]
~~~

The build must ensure snippet-generating tests run before the page assembly task; the output directory contains no stale artifacts; the assemble task only reads snippets from the current build; the renderer supports the chosen Markdown dialect; and CI only publishes when testing, assembling, and rendering all pass.

Gradle skeleton illustrating task relationships:

~~~groovy
tasks.register('assembleApiMarkdown') {
    dependsOn tasks.named('test')
    inputs.dir(layout.buildDirectory.dir('generated-snippets'))
    inputs.dir(layout.projectDirectory.dir('src/docs'))
    outputs.dir(layout.buildDirectory.dir('api-markdown'))

    doLast {
        // Invoke the project's Markdown include/preprocess tool.
        // Fail if required snippets are missing or source pages are invalid.
    }
}
~~~

This is a skeleton, not an implementation of a Markdown include engine. If snippets are generated by a separate integration test task, `assemble` must depend on that specific task rather than defaulting to the general `test` task.

## 13. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Still generating .adoc | The configurer used by the test has not selected Markdown | Check the exact client instance. |
| Missing http-response.md | Test did not run, wrong identifier, or different output dir | Check test/configurer. |
| Fields table renders as plain text | Renderer does not support Markdown Extra | Enable the extension or choose another renderer. |
| Final page missing snippet content | Missing include/preprocess step | Configure a snippet assembly tool. |
| Template override has no effect | Wrong templates/markdown package or filename | Check classpath, format ID, and template name. |
| Snippet missing fields after customization | Template has wrong version/format | Obtain the original template for the exact version. |
| Old snippets remain | Output directory is not managed | Manage output per build. |
| Vietnamese encoding errors | Charset/renderer does not use UTF-8 | Check encoding across the entire pipeline. |
| CI renders before generating snippets | Incorrect task dependency | Make assemble depend on the appropriate test task. |
| REST Assured writes snippet before final assertion | Filter records operation as soon as response arrives | Only publish after the entire test suite passes. |

## 14. Practice Exercise

Set up Markdown for the following endpoints:

- `GET /api/orders/101` returns `200` and a JSON body.
- `POST /api/orders` accepts JSON, returns `201`, `Location`, and response JSON.
- `GET /api/orders/999` returns `404` according to the application's error contract.

Steps to perform:

1. Configure MockMvc to use `TemplateFormats.markdown()`.
2. Write tests for the three operations with distinct identifiers.
3. Open `http-request.md`, `http-response.md`, `request-body.md`, `response-body.md`, `response-fields.md`, and related descriptor snippets.
4. Confirm that the snippets have the `.md` extension.
5. Create a custom template in the `org/springframework/restdocs/templates/markdown` package and verify the output.
6. Choose an include/partials mechanism; assemble snippets into final Markdown pages.
7. Render using a Markdown dialect supporting tables; check links, encoding, and code blocks.
8. Configure CI to run tests before assemble/render and avoid publishing when required snippets are missing.

**Completion criteria:** Spring REST Docs generates Markdown snippets directly; the learner can explain the role of template formats, the location of custom templates, and how snippets are assembled; final pages pull data from tests; CI only publishes when both tests and rendering pass.

## Official References

- [Spring REST Docs — Snippet Template Format](https://docs.spring.io/spring-restdocs/reference/configuration/snippet-template-format.html)
- [Spring REST Docs — Working with Markdown](https://docs.spring.io/spring-restdocs/reference/working-with-markdown.html)
- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
