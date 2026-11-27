# Initializing MockMvc from `WebApplicationContext`

## 1. Why Use `WebApplicationContext`?

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests. Instead of writing request and response examples manually—which easily become outdated—we run the endpoint, verify the result, and let the tool generate **snippets** describing the HTTP exchange, payload, path/query parameters, headers, and other parts to be published. Snippets are included into Asciidoctor/Markdown and can be updated automatically during builds and CI.

Spring REST Docs can integrate with MockMvc, WebTestClient, or REST Assured. In the **MockMvc** chapter, this lesson focuses on building a `MockMvc` instance **from Spring's `WebApplicationContext`** to test and document Spring MVC endpoints.

`WebApplicationContext` is the web application context loaded by Spring Test, containing the relevant beans and MVC configuration, such as:

- `RequestMappingHandlerMapping` and URL mappings to controllers.
- `HandlerAdapter` and `HttpMessageConverter` to invoke handlers and convert JSON.
- `@ControllerAdvice`, exception handlers, validators, and registered MVC components.
- Services, repositories, or other beans created by the application within the scope of the context under test.

When calling:

```java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .build();
```

MockMvc uses the MVC configuration from `context` to process requests **in-process within the JVM**, without opening a port or making HTTP connections to a real server. With Spring REST Docs, we add `documentationConfiguration(...)` before `build()` to generate snippets from selected requests.

Expected outcome after this lesson: you can create and configure MockMvc from a valid `WebApplicationContext`, write HTTP tests that generate documentation, distinguish this approach from `standaloneSetup(...)`, and handle common initialization errors.

## 2. Initialization Flow and Required Components

```text
JUnit Jupiter
  |
  +-- Spring Test / Spring Boot Test
  |      |
  |      +-- Create WebApplicationContext
  |             |-- Controller / Service
  |             |-- MVC mapping / converter / advice
  |
  +-- RestDocumentationExtension
         |
         +-- RestDocumentationContextProvider
                   |
                   v
MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .apply(documentationConfiguration(restDocumentation))
    .build()
                   |
                   v
mockMvc.perform(request)
    .andExpect(...)       <- verify HTTP contract
    .andDo(document(...)) <- generate snippets
```

| Component | Role | Key Takeaway |
| --- | --- | --- |
| `WebApplicationContext` | Provides the Spring MVC configuration for the test | Must be loaded from a servlet web environment; cannot be arbitrarily replaced by a plain `ApplicationContext`. |
| `MockMvcBuilders.webAppContextSetup(context)` | Creates a builder based on the MVC infrastructure in the context | Works in Spring MVC tests without needing a real web server. |
| `RestDocumentationExtension` | Integrates Spring REST Docs into the JUnit Jupiter lifecycle | Supplies `RestDocumentationContextProvider` to the setup method. |
| `documentationConfiguration(restDocumentation)` | Adds documentation generation configuration to the builder | Must be applied via `.apply` before calling `build()`. |
| `MockMvc.perform(...)` | Executes a request through the MVC infrastructure | Can assert status, body, and headers just like regular MockMvc tests. |
| `document("identifier", ...)` | Records an HTTP operation as snippets | Attached to a specific request via `andDo(...)`. |

**Key distinction:** `webAppContextSetup` answers the question "Which MVC configuration does MockMvc use?", while `documentationConfiguration` answers "How does MockMvc integrate the documentation recording mechanism?". Configuring the builder alone does not produce snippets unless `document(...)` or an explicit default documentation mechanism is used.

## 3. Project Setup

The examples below use **Java 17+, Spring Boot 3.x, Spring MVC, JUnit Jupiter 5**, and Gradle. Spring Boot manages compatible dependency versions; for projects not using the Boot BOM, compatible versions must be specified explicitly.

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` provides Spring MVC and JSON message converters; `spring-boot-starter-test` provides Spring Test, MockMvc, JUnit Jupiter, and common testing libraries; `spring-restdocs-mockmvc` provides the Spring REST Docs integration with MockMvc.

In a typical Spring Boot application, you can use:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ExtendWith(RestDocumentationExtension.class)
class ApiDocumentationTest {
    @Autowired
    WebApplicationContext context;

    // Initialize MockMvc with webAppContextSetup(context) in @BeforeEach.
}
```

`@SpringBootTest` uses `WebEnvironment.MOCK` by default, loading a servlet-capable web `ApplicationContext` when Spring MVC and the servlet API are present in the project. It already integrates Spring Test with JUnit Jupiter; you only need to add `RestDocumentationExtension` to receive the Spring REST Docs context.

## 4. Complete Example: Documenting a Book Endpoint

Suppose the endpoint `GET /api/books/{id}` returns:

```json
{
  "id": "b-100",
  "title": "Spring REST Docs"
}
```

To make the example self-contained and runnable in `src/test/java`, the test class below declares a minimal Spring Boot configuration and a sample controller directly inside the test. In a real application, replace `TestApplication` with the project's main configuration class and use controllers from your application source.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = BookApiDocumentationTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ExtendWith(RestDocumentationExtension.class)
class BookApiDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", "b-100")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("b-100"))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Book identifier")),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Book identifier"),
                                fieldWithPath("title")
                                        .description("Book title"))));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(BookController.class)
    static class TestApplication {
    }

    @RestController
    static class BookController {

        @GetMapping(
                value = "/api/books/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> getBook(@PathVariable("id") String id) {
            return Map.of("id", id, "title", "Spring REST Docs");
        }
    }
}
```

### Step-by-Step Analysis

1. **Load the web context:** `@SpringBootTest` loads the `TestApplication` configuration, enables the required auto-configuration, and registers `BookController` via `@Import`. Because Spring MVC is on the classpath, Spring Test injects `WebApplicationContext` into the `context` field.
2. **Prepare Spring REST Docs:** `RestDocumentationExtension` supplies `RestDocumentationContextProvider` to `@BeforeEach`. Do not instantiate this object manually.
3. **Build MockMvc:** `webAppContextSetup(context)` retrieves the configured MVC beans. `.apply(documentationConfiguration(restDocumentation))` attaches the documentation mechanism to the builder, and `.build()` creates MockMvc.
4. **Execute a request with a URI template:** `get("/api/books/{id}", "b-100")` retains the path variable name `id` so that `pathParameters(...)` can accurately document the parameter.
5. **Verify and record documentation:** `andExpect(...)` checks the actual result. `andDo(document("books-get", ...))` generates snippets for the request, response, path parameter, and documented JSON fields.

Upon a successful test run, Spring REST Docs creates the `books-get` directory inside the build's snippet output directory. By default, this is typically `build/generated-snippets/books-get/` with Gradle or `target/generated-snippets/books-get/` with Maven.

## 5. Can `@WebMvcTest` Be Used Instead of `@SpringBootTest`?

Yes, if the goal is to test a Spring MVC slice. `@WebMvcTest` also provides a web context suitable for `webAppContextSetup(...)`, but loads a smaller scope of beans. It is typically appropriate when you only need controllers, MVC validation, message conversion, and related MVC components.

```java
@WebMvcTest(BookController.class)
@ExtendWith(RestDocumentationExtension.class)
class BookControllerDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // @Test: mockMvc.perform(...).andExpect(...).andDo(document(...))
}
```

The snippet above assumes `BookController` is already defined in the project code; import the corresponding annotations, classes, and static methods as in the main example. If the controller depends on services outside the MVC slice, you must provide mock beans or appropriate test configuration. The test will not automatically have all application beans as with `@SpringBootTest`.

| Criterion | `@WebMvcTest` | `@SpringBootTest` + `WebEnvironment.MOCK` |
| --- | --- | --- |
| Context | Focused on the MVC slice | Loads more configuration and beans, following the application |
| Suitable target | Documentation tests for standalone controllers | Documenting endpoint behavior with integrated configurations |
| Dependencies outside MVC | Usually must be mocked or additionally imported | Can use real beans depending on test configuration |
| Execution cost | Usually lower | Usually slower startup |
| Creating MockMvc from context | `webAppContextSetup(context)` | `webAppContextSetup(context)` |

Both approaches **differ from `standaloneSetup(controller)`**: in standalone setup, you pass the controller directly and declare required MVC components yourself; in web context setup, the builder leverages the MVC infrastructure from the loaded context. This helps documentation more accurately reflect the MVC configuration of the test scope.

## 6. Manual Configuration vs. Spring Boot Auto-Configured MockMvc

Spring Boot also supports directly injecting an auto-configured `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class AutoConfiguredDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    // @Test: mockMvc.perform(...).andDo(document(...))
}
```

The example above represents **Spring Boot's auto-configuration approach**: `@AutoConfigureMockMvc` creates and provides `MockMvc`; `@AutoConfigureRestDocs` integrates Spring REST Docs into that MockMvc. To compile, import `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` and `org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs` in Spring Boot 3.x.

When learning `webAppContextSetup(...)`, use the manual setup as shown in section 4 to clearly see the initialization process and where `documentationConfiguration(...)` is applied. If a project already uses `@AutoConfigureMockMvc` to inject MockMvc, there is no need to create another instance just to document the same endpoint: consistently choose one mechanism and configure Spring REST Docs accordingly.

## 7. Filters, Spring Security, and Easy-to-Miss Differences

`webAppContextSetup(context)` picks up **Spring MVC configuration** from the context, but **this does not mean every servlet filter in the application is automatically added** to a manually built MockMvc. If the documentation needs to reflect authentication, authorization, sessions, or custom filters, you must add the appropriate filters/configurers when constructing the builder.

For example, with `spring-security-test` and Spring Security in the application context:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .apply(documentationConfiguration(restDocumentation))
        .build();
```

To use this snippet, the test classpath needs `org.springframework.security:spring-security-test` and the application context must have an appropriate Spring Security configuration. Then you can use test utilities like `@WithMockUser` to simulate a user or `csrf()` for operations requiring a CSRF token. Never assume a public API allows anonymous access just because a manually constructed MockMvc test did not attach the security filter.

When verifying the correctness of requests and responses for documentation:

- Verify `status()` and `contentType` rather than only looking at the generated snippets.
- For POST/PUT/PATCH, send `contentType(MediaType.APPLICATION_JSON)` and the corresponding body via `content(...)`; document `requestFields(...)` when needed.
- If an endpoint requires headers, use `header(...)` or `accept(...)` to send real headers and document them with `requestHeaders(...)`.
- When a test relies on cookies, sessions, authentication, or filters, ensure the builder has the required components and assertions accurately reflect the application's behavior.

## 8. Customizing URIs and Generating Documentation from Snippets

Because MockMvc runs inside the JVM, the host, scheme, and port appearing in snippets may differ from the public URL. You can configure the displayed values when building MockMvc:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(restDocumentation)
                .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
        .build();
```

This change affects **the URL shown in documentation** and does not cause MockMvc to send HTTP requests to an external host.

After a `document("books-get", ...)` test succeeds, a typical set of snippets may appear:

```text
build/generated-snippets/
└── books-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

The exact list depends on the Spring REST Docs version, default snippets, and declared descriptors; for example, `httpie-request.adoc` may also be included. Snippets that are not described or not in the default set will not appear automatically.

Asciidoctor documentation can include the output directly:

```adoc
= Books API

== Get Book Information

include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/http-response.adoc[]
include::{snippets}/books-get/response-fields.adoc[]
```

`{snippets}` must be configured in the build to point to the snippet output directory. When authoring Markdown, convert or embed snippet contents according to the project's setup. The execution chain in build/CI should be **run tests → generate snippets → compile documentation → publish**, with the documentation compilation task depending on the test task to avoid using stale snippets.

## 9. Common Initialization Errors

| Symptom | Possible Cause | How to Check/Resolve |
| --- | --- | --- |
| `@Autowired WebApplicationContext` fails to inject | Test did not load a servlet web context, Spring MVC is missing, or Spring Test configuration is incorrect | Check `@SpringBootTest`/`@WebMvcTest`, MVC dependencies, and the web application type in use. |
| Exception thrown on `webAppContextSetup(context)` | `context` is null or not a valid `WebApplicationContext` | Do not instantiate context with `new`; let Spring Test initialize and inject it. |
| `404` response even though endpoint exists in code | Controller was not scanned or `@Import`ed into the test context, or wrong URL | Check the controller bean, `@RequestMapping`, scan/import configuration, and request path. |
| `401`/`403` response differs from real app | Security filter is missing or applied differently than expected; missing token or mock user | Check `springSecurity()`, test dependencies, filter configuration, and authentication data. |
| `406`/`415` response | Wrong `Accept`, `Content-Type`, or message converter | Send proper headers, check converters in the context, and endpoint `produces`/`consumes`. |
| No snippets generated | `andDo(document(...))` not called, test did not run, or failed before recording | Verify the test passed and check the exact output directory. |
| Path parameter error during documentation | URI template was lost or descriptor name mismatches | Use `get("/api/books/{id}", value)` and `parameterWithName("id")`. |
| `responseFields` fails the test | Actual JSON field is undocumented or path is wrong | Compare with actual response, document all fields; use `optional()` or `ignored()` only when matching the API contract. |
| Documentation shows `localhost` URL | Snippet URI not configured | Use `documentationConfiguration(...).uris()` to set the published host/scheme/port. |

Do not disable field verification just to make tests pass. One of the greatest benefits of Spring REST Docs is that changes to the HTTP contract cause documentation tests to fail and force the documentation to be updated.

## 10. Applied Practice Exercises

Starting from the `BookApiDocumentationTest` example:

1. Add a `GET /api/books` endpoint accepting a `title` query parameter and returning a list of books. Send the request with `param("title", "...")`, verify the result, and generate `queryParameters(...)`.
2. Add a `POST /api/books` endpoint accepting JSON containing `title`. Verify status, `Content-Type`, and response, then document using `requestFields(...)` and `responseFields(...)`.
3. Use `@ControllerAdvice` to return a consistent JSON error when a book is not found. Document both success and error cases, verifying that `webAppContextSetup` uses the advice from the context.
4. If the application uses Spring Security, add `springSecurity()` and document responses for authorized and unauthorized requests. Verify which filters the test actually applied.
5. Run the tests and include the new snippets in Asciidoctor or Markdown documentation; configure CI to verify and build the documentation after tests.

**Completion criteria:** Tests run through the `WebApplicationContext` MVC configuration, assertions verify the responses, snippets reflect actual requests/responses, and the documentation task uses the latest output from the tests.

## 11. Pre-Project Checklist

- [ ] Compatible Spring MVC, Spring Test/JUnit Jupiter, and `spring-restdocs-mockmvc` dependencies are present.
- [ ] `WebApplicationContext` is loaded by Spring Test, injected successfully, and contains the controllers intended for documentation.
- [ ] `RestDocumentationExtension` is registered and `RestDocumentationContextProvider` is supplied to `@BeforeEach`.
- [ ] `MockMvcBuilders.webAppContextSetup(context).apply(documentationConfiguration(restDocumentation)).build()` is used.
- [ ] Necessary filters/security are integrated according to the test scope.
- [ ] Requests use proper URI templates, headers, and bodies; responses have clear assertions.
- [ ] `document(...)` generates all required snippets; the snippet path is used by build/CI and Asciidoctor/Markdown.

**Remember:** `webAppContextSetup(context)` lets MockMvc use **the MVC infrastructure of the loaded Spring context**; `documentationConfiguration(...)` attaches Spring REST Docs to the builder; `document(...)` turns the result of **a tested request** into snippets. Combining these three steps keeps REST API documentation aligned with the application's actual behavior within the test scope.
