# `parameterWithName` and documenting query parameters in Spring REST Docs

## 1. Lesson objectives

In a REST API that supports search queries, parameter names such as `q`, `page`, `size`, or `tag` are part of the contract between the client and the server. If you only include an example URL in the documentation, readers still will not know which parameters are required, what the default values are, or whether multiple values can be passed.

**Spring REST Docs** generates API documentation from HTTP tests executed with MockMvc, WebTestClient, or REST Assured. In the **Query parameters** topic, `parameterWithName(...)` is the mechanism for declaring each parameter to document; `queryParameters(...)` collects those declarations into a snippet that can be included in Asciidoctor/Markdown documentation. This approach ensures that the documentation is verified against real requests during builds and CI.

After this lesson, you will be able to:

- Create a `ParameterDescriptor` using `parameterWithName("...")` and write a `description(...)` that provides sufficient information for API consumers.
- Understand when to use `optional()`, `ignored()`, and `attributes(...)`, and how they relate to the HTTP contract.
- Distinguish between verifying **parameter presence/names** and verifying **values and business rules**.
- Generate, inspect, and integrate `query-parameters.adoc` using a complete MockMvc test.

## 2. What does `parameterWithName` do?

Consider this request:

```http
GET /api/articles?q=rest%20docs&page=1&tag=java&tag=spring HTTP/1.1
Host: api.example.test
```

The query string contains three **parameter names**: `q`, `page`, and `tag`. `tag` appears twice, yet it is still a single parameter name. To generate documentation for this request:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q")
        .description("Article search keyword; required, must not be empty"),
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0")
        .optional(),
    parameterWithName("tag")
        .description("Filter tag; repeat the parameter to select multiple tags, e.g. tag=java&tag=spring")
        .optional()
)
```

Each component has a distinct role:

| API | Role |
| --- | --- |
| `parameterWithName("q")` | Creates a descriptor for the query parameter name `q` |
| `description("...")` | Provides the explanatory text shown in the documentation table |
| `optional()` | Allows the request under test to **omit** that parameter |
| `ignored()` | Declares a known parameter while excluding it from the snippet table |
| `attributes(...)` | Attaches extra metadata, which can be used in custom snippet templates |
| `queryParameters(...)` | Groups the descriptors and generates a snippet for the request's **query string** |

`parameterWithName(...)` is a static factory method on `org.springframework.restdocs.request.RequestDocumentation` and returns a `ParameterDescriptor`. On its own, it **does not generate any documentation file**. A file is generated only when the descriptor is passed into `queryParameters(...)` and attached to a `document(...)` step in a test configured with Spring REST Docs.

> Since Spring REST Docs 3.0, the API dedicated to the query string is `queryParameters(...)`. `formParameters(...)` is intended for form parameters in the request body. In older REST Docs 2.x documentation, you may see `requestParameters(...)`; when using newer versions, clearly separate the two data sources.

## 3. Writing `description(...)` from an API consumer's perspective

A parameter name only tells you **what it is called**. A good description answers practical questions:

1. What is the parameter used for, and which results does it affect?
2. What type or format is expected for its value: string, integer, ISO code, enum, etc.?
3. Is it required? If omitted, how does the server handle it?
4. What are the bounds or valid values?
5. Can the parameter be repeated? If repeated, how are the results combined?

Example:

| Name | Description too short | Description sufficient for use |
| --- | --- | --- |
| `q` | Keyword | Keyword searched in title and body; required, must not be blank |
| `page` | Page | Zero-based page index; defaults to 0 when omitted |
| `size` | Size | Results per page, from 1 to 100; defaults to 20 |
| `sort` | Sort | `createdAt` or `title`; defaults to `createdAt` |
| `tag` | Tag | Repeatable: `tag=java&tag=spring`; filters articles matching the selected tags |

The constraints above are **only examples of an API contract**. Document only what your project's controller and tests actually enforce. For instance, REST Docs does not automatically validate the range `size=1..100` just because we wrote that range in `description(...)`.

### 3.1. Name and value are two distinct concepts

- `parameterWithName("page")` documents the **name** `page`, not the specific value `1`.
- `?tag=java&tag=spring` typically needs **one** descriptor `parameterWithName("tag")`; the semantics of multiple values must be explained in text.
- `?tag[]=java` has the actual parameter name `tag[]` after URL decoding. Do not change it to `tag` in the descriptor if the application uses bracketed names.
- `?q=` has the parameter `q` with an empty value; REST Docs' presence check does not replace controller validation.
- `Page` and `page` are two different names; use the exact name sent in the HTTP request and expected by the controller.

### 3.2. Documenting formats and default values

For example, `cursor` is a pagination token, `fromDate` is an ISO date, and `limit` is an integer:

```java
queryParameters(
    parameterWithName("cursor")
        .description("Token to fetch the next page; omit to start from the first page")
        .optional(),
    parameterWithName("fromDate")
        .description("Start date in ISO 8601 format (yyyy-MM-dd), e.g. 2026-11-01")
        .optional(),
    parameterWithName("limit")
        .description("Maximum number of results, from 1 to 100; defaults to 20")
        .optional()
)
```

If the documentation needs to specify timezone handling, multiple-value semantics, or sorting rules, state them explicitly in `description(...)` or the endpoint explanation. Avoid documenting unverified claims as actual API behavior.

## 4. Complete example with MockMvc, JUnit 5, and REST Docs

The sample controller accepts a required keyword, a page index with a default value, and an optional list of tags:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ArticleController {

    @GetMapping("/api/articles")
    public String findArticles(
            @RequestParam("q") String query,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "tag", required = false) List<String> tags) {
        String joinedTags = tags == null ? "" : String.join(",", tags);
        return "q=" + query + "; page=" + page + "; tags=" + joinedTags;
    }
}
```

In a real system, the endpoint usually calls a service and returns JSON. Returning a string lets learners directly observe binding results while focusing on parameter documentation.

Test:

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ArticleQueryParameterDocsTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ArticleController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsQueryParameters() throws Exception {
        mockMvc.perform(get("/api/articles")
                        .queryParam("q", "Spring REST Docs")
                        .queryParam("page", "1")
                        .queryParam("tag", "java", "spring"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "q=Spring REST Docs; page=1; tags=java,spring"))
                .andDo(document("articles-search",
                        queryParameters(
                                parameterWithName("q")
                                        .description("Article search keyword; required"),
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0")
                                        .optional(),
                                parameterWithName("tag")
                                        .description("Filter tag; repeat to select multiple tags")
                                        .optional()
                        )));
    }
}
```

In this example:

1. `RestDocumentationExtension` together with `documentationConfiguration(...)` enables Spring REST Docs for MockMvc.
2. `get("/api/articles").queryParam(...)` constructs the query string, including two values for `tag`. With REST Docs 3+, use `queryParam(...)` or place parameters directly in the URL when documenting **query parameters**. In MockMvc, `param(...)` represents generic Servlet request parameters and can be confused with form parameters.
3. The two assertions `status()` and `content()` verify the controller's HTTP behavior; REST Docs descriptors do not verify response bodies.
4. `document("articles-search", queryParameters(...))` triggers documentation generation. With the default Asciidoctor template, the corresponding file is located at `build/generated-snippets/articles-search/query-parameters.adoc` when Gradle is configured with that directory (Maven typically uses `target/generated-snippets/`).

The generated snippet has a table-like structure containing the names `q`, `page`, `tag` and their `description` text; exact formatting depends on the template, version, and project configuration. There is no need to manually maintain this table in the documentation.

### Including the table in an Asciidoctor document

```asciidoc
= Articles API

== Search articles

GET /api/articles

=== Query parameters

include::{snippets}/articles-search/query-parameters.adoc[]
```

In a Gradle or Maven build, `{snippets}` must point to the directory containing the snippets, and the Asciidoctor task needs to run after the tests that generate snippets. CI should run both the tests and the documentation rendering step to catch changes to the contract or snippet paths.

## 5. `optional()`: permitted to be absent in the test request

The snippet below documents `q` as required and `page` as optional:

```java
queryParameters(
    parameterWithName("q").description("Required keyword"),
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0")
        .optional()
)
```

| Request under test | Evaluation against the description above |
| --- | --- |
| `/api/articles?q=spring&page=2` | Both documented parameters are present |
| `/api/articles?q=spring` | Valid for REST Docs because `page` is optional |
| `/api/articles?page=2` | Missing the required descriptor `q`; the controller may also return 400 |
| `/api/articles?q=spring&sort=title` | Contains undocumented parameter `sort` in strict mode |

**Distinguishing the two constraint layers:**

```java
// In Spring MVC: the server allows omitting page, defaulting to 0.
@RequestParam(name = "page", defaultValue = "0") int page

// In Spring REST Docs: the test may omit sending page.
parameterWithName("page")
    .description("Zero-based page index; defaults to 0")
    .optional()
```

`.optional()` does not make `@RequestParam` optional, does not set a default value, and does not allow invalid types. Conversely, `required = false` or `defaultValue` in the controller does not automatically add `.optional()` to the descriptor. Without `.optional()`, if the documented request lacks a declared parameter, REST Docs reports an error for the missing parameter.

## 6. `ignored()`: acknowledging a parameter while hiding it from the snippet

Sometimes a request includes an extra query parameter for internal instrumentation, such as `debugTrace`, that public API documentation does not need to explain.

```java
queryParameters(
    parameterWithName("q")
        .description("Article search keyword"),
    parameterWithName("debugTrace").ignored()
)
```

If the actual request has `?q=spring&debugTrace=abc123`, the `debugTrace` descriptor tells REST Docs that this parameter name has been accounted for in the snippet specification, while excluding it from the generated table. Do not use `ignored()` to hide public parameters that clients need to know about.

Differences:

- **`optional()`:** still renders a description row in the documentation; the request may omit that name.
- **`ignored()`:** omits the description row from the documentation; typically used for known technical parameters.
- **`relaxedQueryParameters(...)`:** allows query parameter names in the request without descriptors, useful when intentionally documenting only part of a contract.

When producing official documentation for an endpoint, prefer strict `queryParameters(...)` and document every parameter a client may send.

## 7. `attributes(...)` and custom templates

`description(...)` is usually enough for the default documentation table. If a team wants to add an **Example** or **Constraints** column, custom attributes can be attached to the descriptor:

```java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

parameterWithName("size")
    .description("Number of results per page; defaults to 20")
    .attributes(
        key("example").value("20"),
        key("constraints").value("Integer from 1 to 100")
    )
    .optional();
```

The two attributes `example` and `constraints` are simply metadata with project-chosen keys; they **do not automatically add columns to the default snippet** and **do not enable validation**. To display them, the team must customize the Mustache template for `query-parameters`, then inspect the rendered output. For a short documentation page, placing this information directly inside `description(...)` is easier to maintain.

REST Docs does not automatically infer parameter descriptions from `@RequestParam`, `@Min`, or `@Max` annotations in these examples. If value rules must be enforced, use application-layer validation and separate assertions in tests.

## 8. What causes a documentation test to fail?

In default mode, `queryParameters(...)` verifies consistency between the **set of parameter names in the request** and the **set of descriptors**:

| Symptom | Why | How to fix |
| --- | --- | --- |
| Request sends `page` while only `q` has a descriptor | The name `page` is undocumented | Add `parameterWithName("page").description(...)` |
| `sort` is documented, but the request does not send `sort` | A required descriptor is missing from the request | Send `sort` in the test or add `.optional()` if the contract allows it |
| Descriptor specifies `"tags"`, but the request sends `tag` | The two names do not match | Align the name with the HTTP request and controller |
| Test uses `.param("q", "spring")` and documents with `queryParameters(...)` | Servlet request parameters are not necessarily in the URL | Use `.queryParam("q", "spring")` or include the query string in the URL |
| Test passes, but `query-parameters.adoc` is missing | `queryParameters(...)` was not attached to `document(...)`, or checking the wrong identifier/directory | Check REST Docs configuration, identifier, and snippet output directory |
| `?size=abc` passes the REST Docs documentation step | Descriptors do not validate integers, bounds, or enums | Add HTTP/Bean Validation and write tests for invalid data |
| `?q=` includes the name `q` but violates a non-empty requirement | Name checking differs from content checking | Test that the application returns the appropriate error, e.g. HTTP 400 |

**Value rules are part of the business contract, not a built-in feature of `parameterWithName`.** A good documentation test verifies both the response/status and the descriptors; to verify validation, write additional tests for invalid cases.

## 9. Using with WebTestClient and REST Assured

The `parameterWithName(...)` and `queryParameters(...)` descriptions stay the same when switching testing tools. The differences lie in how HTTP calls are made and how `document(...)` is attached:

- **MockMvc:** `mockMvc.perform(...).andDo(document("id", queryParameters(...)))`; pass the query string via `queryParam(...)` or the URL.
- **WebTestClient:** build a URI with a query string and use `expectBody().consumeWith(document("id", queryParameters(...)))` after configuring Spring REST Docs for the client.
- **REST Assured:** use `queryParam(...)` on the request and the documentation filter from the `spring-restdocs-restassured` module.

Conceptual example with WebTestClient already configured for REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/articles?q=spring&page=1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("articles-search",
        queryParameters(
            parameterWithName("q").description("Article search keyword"),
            parameterWithName("page").description("Zero-based page index").optional()
        )
    ));
```

This snippet illustrates the API call; `webTestClient` must be initialized and configured with Spring REST Docs beforehand. When moving to REST Assured, there is no need to rewrite the semantics of `description` and `optional`.

## 10. Hands-on exercise

Suppose your team is building this API:

```http
GET /api/orders?status=PAID&page=0&size=25&sort=createdAt&sort=id HTTP/1.1
```

Intended contract:

- `status`: optional; accepts only `PENDING`, `PAID`, or `CANCELLED`.
- `page`: optional; integer starting from 0, defaults to 0.
- `size`: optional; integer from 1 to 100, defaults to 25.
- `sort`: optional; repeatable to define multi-field sort priority.

**Tasks:**

1. Write four `parameterWithName(...)` descriptors, using `.optional()` where appropriate and `.description(...)` to state formats, defaults, and repetition rules.
2. Write a MockMvc test that sends the sample request and generates `query-parameters.adoc`.
3. Try adding `currency=VND` to the request without documenting it; observe the error when using strict `queryParameters(...)`, then add a descriptor if it is a valid parameter.
4. Try `size=-5` and `status=UNKNOWN`. Confirm that server-side validation tests catch the invalid data; do not rely on `description(...)` to detect errors.
5. Include the snippet in Asciidoctor, make the documentation task depend on the test task, and run that workflow in CI.

**Completion criteria:** Descriptors reflect the actual names and semantics of the query string; valid requests generate snippets; changing a name or omitting a required parameter causes the documentation test to catch the mismatch; value validation is tested independently.

## 11. Project implementation notes

`parameterWithName(...)` brings knowledge about the name and meaning of each query parameter into HTTP tests; `description(...)` is what API consumers read directly. When combining descriptors with `queryParameters(...)` and `document(...)`, documentation is regenerated from tests in build/CI. Prefer documenting defaults, bounds, repeatable parameters, and optionality clearly, while verifying value constraints with dedicated application tests.

### References

- [Spring REST Docs Reference — Documenting your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring REST Docs Reference — Query parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Javadoc — `RequestDocumentation`](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html)
- [Javadoc — `ParameterDescriptor`](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/ParameterDescriptor.html)
