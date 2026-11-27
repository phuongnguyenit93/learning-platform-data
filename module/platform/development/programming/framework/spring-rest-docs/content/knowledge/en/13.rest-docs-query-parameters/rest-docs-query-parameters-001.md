# Documenting query parameters with `queryParameters` in Spring REST Docs

## 1. Objectives and context

A search REST API typically accepts parameters after the `?` in the URL:

```http
GET /api/books?keyword=spring&page=1&tag=java&tag=api HTTP/1.1
Host: example.com
```

`keyword`, `page`, and `tag` are **query parameters**. They consist of names and values in the *query string*, which differ from:

| Component | Example | Corresponding descriptor method in Spring REST Docs |
| --- | --- | --- |
| Query parameter | `?page=1` | `queryParameters(...)` |
| Path parameter | `/books/42` with `{id}` | `pathParameters(...)` |
| Form parameter | `email` field in an `application/x-www-form-urlencoded` body | `formParameters(...)` |
| Request header | `Accept-Language: vi` | `requestHeaders(...)` |
| JSON body | `{"page":1}` | `requestFields(...)` |

**Spring REST Docs** generates documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. When you attach `queryParameters(...)` to the documentation step, the test both generates the query string description and detects parameter names that were sent without being documented or required parameters that were documented but missing from the request. As a result, the documentation and actual HTTP behavior are verified together.

> **Version scope:** `queryParameters(...)` has been available since **Spring REST Docs 3.0**. Versions 3.x and 4.x use this API. If you are upgrading from 2.x, replace the legacy `requestParameters(...)` approach with `queryParameters(...)` and `formParameters(...)` according to the actual data source.

After this lesson, you will be able to:

1. Document the names, meanings, presence requirements, and repetition behavior of query parameters.
2. Generate the `query-parameters.adoc` snippet file through HTTP tests.
3. Distinguish between strict verification, `optional()`, `ignored()`, and `relaxedQueryParameters(...)`.
4. Include the snippet in Asciidoctor documentation and run the tests in a build/CI pipeline.

## 2. Core syntax

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("keyword").description("Search keyword; required"),
    parameterWithName("page").description("Page index, starting from 0; defaults to 0").optional(),
    parameterWithName("tag").description("Can be repeated to filter by multiple tags").optional()
)
```

- `queryParameters(...)` is a static factory method on `org.springframework.restdocs.request.RequestDocumentation` that accepts `ParameterDescriptor` instances.
- `parameterWithName("...")` documents the **exact name** of the parameter in the query string; `description(...)` explains its meaning to API consumers.
- `optional()` tells REST Docs that the parameter may be absent from the **test request**. It does not change the controller's constraints on its own.
- A parameter can appear multiple times, such as `tag=java&tag=api`. Usually only **one** descriptor is needed for the name `tag`; explain repetition and handling rules in the description.

In Spring MVC, `@RequestParam(required = false)` or `@RequestParam(defaultValue = "...")` determines server-side binding. In Spring REST Docs, `.optional()` determines presence verification when generating documentation. These two configurations must reflect the same API contract, though they are **not automatically synchronized**.

## 3. Complete example with MockMvc and JUnit 5

Suppose an endpoint returns a list of books by keyword and supports pagination and tag filtering. To focus on snippet generation, the sample controller returns a simple string:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class BookController {

    @GetMapping("/api/books")
    public String findBooks(
            @RequestParam("keyword") String keyword,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "tag", required = false) List<String> tags) {
        return "keyword=" + keyword + ", page=" + page + ", tags=" + tags;
    }
}
```

The test below configures Spring REST Docs on MockMvc, sends actual query parameters, and requests snippet output:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookQueryParametersDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsSearchQueryParameters() throws Exception {
        mockMvc.perform(get("/api/books")
                        .queryParam("keyword", "spring docs")
                        .queryParam("page", "1")
                        .queryParam("tag", "java", "api"))
                .andExpect(status().isOk())
                .andDo(document("books-search",
                        queryParameters(
                                parameterWithName("keyword")
                                        .description("Book search keyword, required"),
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0")
                                        .optional(),
                                parameterWithName("tag")
                                        .description("Filter tag; may be repeated multiple times")
                                        .optional()
                        )));
    }
}
```

**Step-by-step walkthrough:**

1. `RestDocumentationExtension` manages the documentation context for JUnit 5; `documentationConfiguration(...)` attaches it to MockMvc. The example uses `standaloneSetup`; in Spring Boot you can use a MockMvc instance configured via `@AutoConfigureRestDocs`.
2. `get("/api/books").queryParam(...)` builds the query string of the HTTP request. The value `spring docs` is URL-encoded by the request builder; there is no need to concatenate an already-encoded string manually.
3. `.andExpect(status().isOk())` verifies that the endpoint returns 200; additional assertions for the payload or filtering rules can be added independently.
4. `document("books-search", queryParameters(...))` creates a snippet set identified as `books-search`, including the description of the query parameters.

With Gradle, the default output is typically located at:

```text
build/
  generated-snippets/
    books-search/
      query-parameters.adoc
      curl-request.adoc
      http-request.adoc
      http-response.adoc
      ...
```

In Maven, the usual location is `target/generated-snippets/`. The other files are generated according to the default snippet configuration; the documentation file name for query parameters is `query-parameters.adoc` when using the Asciidoctor template. The snippet content is a table describing parameter names and their declared `description` values.

**Note on MockMvc:** With `queryParameters(...)`, supply data in the URL (`get("/api/books?keyword=spring")`) or use `queryParam(...)` / `queryParams(...)`. Avoid `.param(...)` / `.params(...)` for this use case because they only add Servlet request parameters without clarifying whether the data comes from the query string or a form body. A controller using `@RequestParam` might still receive values via `.param(...)` while REST Docs sees no query parameter to document.

## 4. Strict verification and descriptor variants

By default, `queryParameters(...)` verifies the contract for the **names and presence** of query parameters in the request under test:

| Scenario | Result with `queryParameters(...)` | How to handle |
| --- | --- | --- |
| Request sends `sort=title` without a `sort` descriptor | Test fails due to undocumented parameter | Add `parameterWithName("sort")` or remove it from the request if not part of the contract |
| Descriptor documents `page` but request omits `page` | Test fails unless marked optional | Use `.optional()` if the endpoint allows omitting `page` |
| Request includes an internal `trace` parameter that should not appear in the table | Still treated as undocumented by default | Use `parameterWithName("trace").ignored()` when the parameter is known to be in the request |
| You only want to document a subset of the parameters present in the request | Fails by default because the remaining names are undocumented | Consider `relaxedQueryParameters(...)` for intentional cases |

### 4.1. Optional parameters

```java
queryParameters(
    parameterWithName("keyword").description("Required keyword"),
    parameterWithName("page").description("Page index, defaults to 0").optional()
)
```

With this description, a request to `/api/books?keyword=spring` still generates the snippet successfully even without `page`. Conversely, if the request omits `keyword`, the documentation test fails. You should write separate tests for default values, data types, and invalid inputs if those are important parts of the API.

### 4.2. Intentionally ignored parameters

```java
queryParameters(
    parameterWithName("keyword").description("Search keyword"),
    parameterWithName("trace").ignored()
)
```

For example, if the request has `?keyword=spring&trace=abc`, `trace` does not appear in the generated table and is not flagged as an undocumented parameter. This is suitable when a technical parameter is known in advance but should not appear in public documentation. If an ignored parameter may also be absent, consider combining `.optional().ignored()` according to the test contract.

### 4.3. Relaxed mode

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedQueryParameters;

relaxedQueryParameters(
    parameterWithName("keyword").description("Search keyword")
)
```

`relaxedQueryParameters(...)` **does not report errors for query parameters that are present without a descriptor**. It still checks that documented parameters are present unless marked `optional()`. Use this when you need to document a slice of a request; for official API documentation, prefer strict mode to catch contract changes.

## 5. How do WebTestClient and REST Assured differ?

`queryParameters(...)` and `parameterWithName(...)` belong to the shared descriptor API layer. What changes across testing tools is mainly **how requests are sent and where `document(...)` is attached**.

Example when `WebTestClient` is already configured with Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri("/api/books?keyword=spring&page=1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("books-search",
                queryParameters(
                        parameterWithName("keyword").description("Book search keyword"),
                        parameterWithName("page").description("Zero-based page index").optional()
                )));
```

With REST Assured, you can attach `document(..., queryParameters(...))` through the filter provided by `spring-restdocs-restassured`, and pass values using REST Assured's `queryParam(...)`. In all three approaches, REST Docs must be configured before requesting snippet generation; simply calling `queryParameters(...)` without attaching it to a documentation action will not generate files.

## 6. Including snippets in documentation and CI

With Asciidoctor, create a handwritten documentation page (for example, `src/docs/asciidoc/books.adoc`) and include the snippet:

```asciidoc
= Books API

== Search books

GET /api/books

=== Query parameters

include::{snippets}/books-search/query-parameters.adoc[]
```

The `{snippets}` attribute is configured to point to the build's snippet directory; when `spring-restdocs-asciidoctor` is integrated properly, the build can provide this attribute. With Gradle, the basic flow consists of:

1. Declare `testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'` (or the corresponding dependency for WebTestClient/REST Assured) along with JUnit/Spring Test dependencies. Choose a Spring REST Docs version compatible with the project's Spring Framework and Spring Boot versions.
2. Configure the snippet directory, such as `build/generated-snippets`, as an **output of the `test` task**.
3. Configure the Asciidoctor plugin and `spring-restdocs-asciidoctor` so the documentation task reads from the snippet directory; make this task depend on `test`.
4. Run `./gradlew test asciidoctor` (or the equivalent Maven lifecycle) in CI to verify the HTTP contract before generating HTML. If the documentation tests fail, CI must fail as well.

By default, Spring REST Docs generates Asciidoctor snippets. If a project chooses **Markdown** as the snippet template format, configure `TemplateFormats.markdown()` on `RestDocumentationConfigurer`; generated files will use Markdown format. Markdown has no standard `include` mechanism like Asciidoctor, so an appropriate document assembly tool is needed when publishing.

## 7. Common errors and diagnostics

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Test reports missing `keyword` even though the controller reads it | Using `.param("keyword", ...)` instead of a real query string | Use `.queryParam("keyword", ...)` or inspect the outgoing URL |
| Test fails after adding `sort` to the endpoint | `queryParameters(...)` requires documenting every sent query parameter by default | Add a `sort` descriptor and update the contract description |
| Test fails when omitting `page` | The `page` descriptor does not call `optional()` | Cross-check with `@RequestParam`/default values and update the descriptor |
| Request/response snippets exist, but `query-parameters.adoc` is missing | `queryParameters(...)` was not passed into that test's `document(...)` call | Check the identifier and snippet list in the `document` call |
| HTML documentation is missing the parameter table | Asciidoctor file points to the wrong `books-search` identifier, wrong `{snippets}`, or the docs task runs before tests | Check output paths and task dependencies |
| Table lists parameter names but does not reflect value constraints | REST Docs primarily checks **names/presence**, not business value validation | Document units, default values, and repetition rules; write separate assertions/tests for data constraints |

## 8. Practice exercises

1. Create an endpoint `GET /api/books?keyword=java&page=0&size=20&tag=backend&tag=testing`. In the documentation table, describe `keyword` as required, `page` and `size` as optional with default values, and `tag` as accepting multiple values.
2. Run the test, then additionally send `sort=title` without declaring a descriptor. Observe the test failure; add the `sort` descriptor and re-verify.
3. Omit `page` from the request. Compare the result when the descriptor has and does not have `.optional()`.
4. Open `query-parameters.adoc`, include it in `books.adoc`, and inspect the HTML documentation generated by the build.

**Completion criteria:** The HTTP test passes, a snippet exists documenting all parameter names in the request, optional fields are clearly described, and the documentation page displays the query parameters table sourced from the test snippet.

## References

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started and including snippets in Asciidoctor](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs 3.0 — release notes and upgrade changes](https://github.com/spring-projects/spring-restdocs/wiki/Spring-REST-Docs-3.0-Release-Notes)
