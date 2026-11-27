# Multi-value query parameters and how to represent them in Spring REST Docs

## 1. Why can a query parameter have multiple values?

In a search API, a filter often needs to accept multiple selections: a list of tags, multiple product codes, multiple statuses, or multiple sort criteria. Consider this request:

```http
GET /api/articles?tag=java&tag=spring&sort=createdAt:desc&sort=title:asc&page=0 HTTP/1.1
Host: api.example.test
```

Here:

- The name `tag` has **two values**: `java` and `spring`.
- The name `sort` has **two values**: `createdAt:desc` and `title:asc`.
- The name `page` has only **one value**: `0`.

Each `name=value` pair is one occurrence in the query string. When a name is repeated, the application must define how the values are processed: take all, take the first, take the last, deduplicate, or reject with an error. Do not infer the processing behavior from URL syntax alone.

**Spring REST Docs** in the `SPRING_REST_DOCS` module generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. The topic of this lesson is **Query parameters**, specifically how to represent and document **multi-value parameters** with `queryParameters(...)` and `parameterWithName(...)`, so the descriptions can be included in Asciidoctor/Markdown and run alongside build/CI.

After this lesson, you will be able to:

1. Distinguish between multiple query pairs sharing the same name and a single value containing a delimiter.
2. Specify the API contract regarding value count, ordering, duplicate values, and empty values.
3. Test multi-value requests using MockMvc, WebTestClient, or REST Assured.
4. Generate a query parameters documentation snippet and add the necessary assertions to verify semantics.

## 2. Common representation patterns

There is no single convention that forces every REST API to interpret value strings the same way. The representations below are **not automatically equivalent**:

| Query string | Meaning at the HTTP name/value level | What the API must specify |
| --- | --- | --- |
| `?tag=java&tag=spring` | The name `tag` appears twice, once per value | Are both values accepted? Combined with OR or AND? |
| `?tag=java,spring` | The name `tag` appears once, with the string value `java,spring` | Is the comma a literal character or a delimiter? |
| `?tag[]=java&tag[]=spring` | The transmitted name is `tag[]`, appearing twice | Does the framework understand bracket syntax or require custom handling? |
| `?tag[0]=java&tag[1]=spring` | Two distinct names, `tag[0]` and `tag[1]` | Are indexed names supported, and how are missing/duplicate indices handled? |
| `?sort=createdAt,desc&sort=title,asc` | Two values for `sort`, each containing a comma | Each value has `field,direction`; does the order of occurrences matter? |
| `?tag=java&tag=java` | One name appearing twice with duplicate values | Are duplicates kept, deduplicated, or rejected? |

### 2.1. Repeating the same name: `tag=java&tag=spring`

This is the most direct way to represent multiple values in a query string:

```http
GET /api/articles?tag=java&tag=spring HTTP/1.1
```

Its advantage is that no custom delimiter is needed. The client sends each element as a separate occurrence of the name `tag`. In Spring MVC, `@RequestParam List<String>` or `@RequestParam MultiValueMap<String, String>` can handle this format.

Example contract chosen by an API team:

> `tag` can be repeated multiple times. The API finds articles that carry **at least one** tag in the list (OR logic). If duplicate tags are sent, the server evaluates each tag only once.

REST Docs records that explanation in `description(...)`. The OR filtering and deduplication logic must be implemented and tested at the application layer.

### 2.2. Delimited within a single value: `tag=java,spring`

```http
GET /api/articles?tag=java,spring HTTP/1.1
```

At the query string level, this is **one** name/value pair. Splitting it into two elements occurs only if the binding mechanism or application logic defines the comma as a separator. Some Spring MVC collection binding behaviors can split a comma-separated string into a list; exact behavior should be tested with the endpoint's parameter type, converters, and configuration.

Do not document both styles (`tag=a&tag=b` and `tag=a,b`) as supported just because one test currently accepts both. If valid values themselves may contain commas, this representation also requires explicit escaping/quoting rules.

### 2.3. Using square brackets or indices in the name

Some client libraries may send:

```http
GET /api/articles?tag%5B%5D=java&tag%5B%5D=spring HTTP/1.1
```

`%5B` and `%5D` are the URL encodings of `[` and `]`, respectively. After URL decoding, the parameter name is `tag[]`. This is not always equivalent to the name `tag`; verify exact server binding behavior. If the API expects `tag[]`, the REST Docs descriptor must document the matching name:

```java
queryParameters(
    parameterWithName("tag[]")
        .description("List of tags; the parameter name includes square brackets and can be repeated")
)
```

Spring MVC has some support for binding names with a `[]` suffix, though the level of support depends on the parameter type and how the request is sent. Do not blindly apply a JavaScript library's convention to every REST API.

## 3. URL encoding, ordering, and empty values

### 3.1. Encode each component properly

Query values can contain spaces, `+`, `&`, commas, or Unicode characters. When constructing URLs manually, syntactically significant characters must be properly percent-encoded:

```http
GET /api/articles?tag=C%2B%2B&tag=spring%20web HTTP/1.1
```

When decoded, the two expected values are `C++` and `spring web`. If written directly as `tag=C++`, the `+` sign may be interpreted as a space by query parsers following form-encoding rules. Avoid concatenating URLs from unencoded strings.

Example with MockMvc:

```java
mockMvc.perform(get("/api/articles")
        .queryParam("tag", "C++", "spring web"));
```

When using a URI builder or HTTP client, let the tool construct and encode the query components according to its API. Inspect the actual outgoing request when handling values with special characters.

### 3.2. Does order matter?

The following two requests contain the same set of `tag` values:

```http
GET /api/articles?tag=java&tag=spring HTTP/1.1
GET /api/articles?tag=spring&tag=java HTTP/1.1
```

For set-style filters, order usually does not matter. For a `sort` parameter, order may be used to determine sort precedence. If order is meaningful, the documentation must state it clearly, and tests must verify order preservation across supported client/server layers. Do not rely on query parameter ordering without a contract and tests.

### 3.3. Empty values differ from absent parameters

| Request | Represented data | Business question |
| --- | --- | --- |
| `/api/articles` | No `tag` parameter | Is a default filter applied? |
| `/api/articles?tag=` | Parameter `tag` is present with an empty value | Accept, ignore, or return a 400 error? |
| `/api/articles?tag=java&tag=` | One non-empty value and one empty value | Discard empty values or reject the entire request? |
| `/api/articles?tag=java&tag=java` | Two duplicate values | Are duplicates removed? |

`queryParameters(...)` primarily verifies **parameter names and whether those names are present**; it does not automatically distinguish the business rules in the table above. Separate assertions/validation are needed for empty values, occurrence counts, and duplicates.

## 4. Binding multi-value parameters in Spring MVC

For an API accepting multiple tags, a common declaration style is:

```java
@GetMapping("/api/articles")
public List<Article> findArticles(
        @RequestParam(name = "tag", required = false) List<String> tags) {
    // Process the list of tag values.
    return articleService.findByTags(tags);
}
```

When you need to read **every value by name exactly as sent** without tying logic to a fixed parameter name, you can use `MultiValueMap`:

```java
import java.util.List;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/filter-preview")
public List<String> preview(@RequestParam MultiValueMap<String, String> parameters) {
    return parameters.getOrDefault("tag", List.of());
}
```

`MultiValueMap` maps one key to multiple values. This type lets you observe repeated occurrences, though allowed parameter names, empty data, and maximum counts must still be enforced by the API.

With `@RequestParam List<String>`, converting a single value like `"java,spring"` into a list may behave differently from receiving multiple `tag` pairs. Write tests for the exact representation your API publishes, especially when custom converters are configured.

## 5. Documenting with `parameterWithName` and `queryParameters`

Suppose an endpoint accepts repeatable `tag`, repeatable `sort`, and single-valued `page`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("tag")
        .description("Tag to filter by; pass multiple times: tag=java&tag=spring"),
    parameterWithName("sort")
        .description("Repeatable: sort=field:direction; order of appearance defines priority")
        .optional(),
    parameterWithName("page")
        .description("Zero-based page number, defaults to 0; accepts a single value")
        .optional()
)
```

**One name is documented by one descriptor**, even when the request sends that name multiple times. Do not create two `parameterWithName("tag")` entries to document `tag=java&tag=spring`.

| Aspect | What REST Docs can check | What the application must check itself |
| --- | --- | --- |
| Whether `tag` is present | Yes, via a required descriptor or `optional()` | Whether empty/blank values are valid |
| Undocumented name such as `color` | Strict `queryParameters(...)` mode can detect it | Whether the server should accept `color` |
| `tag` appears twice | Recognizes the name `tag`, generates one row | Maximum repetitions, duplicates, AND/OR |
| `sort` repeated in order | Documented in prose | Parser, malformed cases, and precedence order |
| `page` contains `abc` | Does not validate numeric types from `description` | Conversion, validation, HTTP status |

### Distinguishing descriptor mechanisms

- `.optional()`: permits the parameter name to be absent in the test request; does not mean any value is accepted.
- `.ignored()`: acknowledges the parameter name while omitting that row from the documentation table.
- `relaxedQueryParameters(...)`: allows requests to include query parameter names without descriptors; still verifies presence of required descriptors.

For official APIs, prefer `queryParameters(...)` in default mode to catch when a new parameter name appears in a request without being documented.

## 6. Complete example: MockMvc + JUnit 5 + snippet

The sample controller returns a string that is quick to assert, instead of a JSON list as in a production application:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ArticleController {

    @GetMapping("/api/articles")
    public String findArticles(
            @RequestParam("tag") List<String> tags,
            @RequestParam(name = "sort", required = false) List<String> sorts,
            @RequestParam(name = "page", defaultValue = "0") int page) {

        List<String> safeSorts = sorts == null ? List.of() : sorts;
        return "tags=" + String.join("|", tags)
                + ";sorts=" + String.join("|", safeSorts)
                + ";page=" + page;
    }
}
```

Documentation test:

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
class ArticleMultiValueQueryDocsTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ArticleController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsRepeatedQueryParameters() throws Exception {
        mockMvc.perform(get("/api/articles")
                        .queryParam("tag", "java", "spring")
                        .queryParam("sort", "createdAt:desc", "title:asc")
                        .queryParam("page", "0"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "tags=java|spring;sorts=createdAt:desc|title:asc;page=0"))
                .andDo(document("articles-multi-value-query",
                        queryParameters(
                                parameterWithName("tag")
                                        .description("Filter tag; repeat tag to select multiple tags"),
                                parameterWithName("sort")
                                        .description("Repeat sort=field:direction to prioritize multiple criteria")
                                        .optional(),
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0; single value")
                                        .optional()
                        )));
    }
}
```

**Meaning of each part:**

1. `get(...).queryParam("tag", "java", "spring")` creates a query string with two values for the same `tag` name. To document query parameters with REST Docs, use `queryParam(...)` or put the query string in the URL; MockMvc's `param(...)` only adds generic Servlet request parameters and may leave the query-string source ambiguous.
2. The `content().string(...)` assertion verifies the binding and value order expected by the example. This checks **actual behavior**, which is outside the scope of `queryParameters(...)`.
3. `parameterWithName("tag")` appears only once even though two values are sent. `.description(...)` publishes the repetition rules for clients.
4. `sort` and `page` use `.optional()` because the server allows omitting them from the request. This matches `required = false` and `defaultValue` on the controller, though REST Docs does not automatically infer those annotations.
5. `document("articles-multi-value-query", ...)` generates the snippets once the test passes and Spring REST Docs is configured.

In Gradle using `build/generated-snippets`, the query parameters snippet will be at:

```text
build/generated-snippets/
└── articles-multi-value-query/
    ├── query-parameters.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    └── ...
```

The actual path depends on your output configuration; with Maven it is typically `target/generated-snippets`. The generated table has **one row per name** (`tag`, `sort`, and `page`) along with its `description(...)`; it does not generate separate rows for `tag=java` and `tag=spring`.

### 6.1. Adding tests for value cardinality

REST Docs does not automatically verify that `tag` can be repeated at most three times or that `page` may appear only once. If those are API requirements, check the element count in your controller/service and write tests for both valid and invalid cases.

Example testing a single occurrence and multiple occurrences:

```java
// Case 1: one tag, sort omitted.
mockMvc.perform(get("/api/articles")
        .queryParam("tag", "java"))
    .andExpect(status().isOk())
    .andExpect(content().string("tags=java;sorts=;page=0"));

// Case 2: two tags, sort omitted.
mockMvc.perform(get("/api/articles")
        .queryParam("tag", "java", "spring"))
    .andExpect(status().isOk())
    .andExpect(content().string("tags=java|spring;sorts=;page=0"));
```

These tests verify binding values in the sample controller. If the contract requires rejecting empty elements, exceeding maximum counts, or unlisted values, add validation and HTTP 4xx assertions for those cases.

## 7. Sending multi-value parameters with WebTestClient and REST Assured

`parameterWithName(...)` and `queryParameters(...)` belong to the shared descriptor API across Spring REST Docs integrations. The difference is in the client sending the request:

### 7.1. WebTestClient

Include the query string in the URI or use a URI builder, then attach the snippet in `consumeWith(document(...))`. Example when `webTestClient` is already configured with REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/articles")
                .queryParam("tag", "java", "spring")
                .queryParam("sort", "createdAt:desc", "title:asc")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("articles-multi-value-query",
                queryParameters(
                        parameterWithName("tag").description("Filter tag, repeatable"),
                        parameterWithName("sort").description("Sort criterion, repeatable")
                                .optional()
                )));
```

`UriBuilder.queryParam(...)` supports passing multiple values for the same name. When using the builder, verify the encoding of special values.

### 7.2. REST Assured

With the `spring-restdocs-restassured` module and an initialized documentation filter, you can use REST Assured's `queryParam(...)` to pass a list or multiple values (depending on the library overloads). Sketch:

```java
given()
    .filter(documentationFilter)
    .queryParam("tag", "java", "spring")
    .when()
    .get("/api/articles")
    .then()
    .statusCode(200);
```

This snippet only illustrates how to send the request and cannot generate `query-parameters.adoc` by itself: you must configure the documentation filter with `document(..., queryParameters(...))` or the equivalent mechanism in a full REST Assured test.

## 8. Including snippets in Asciidoctor/Markdown and build/CI

If using Asciidoctor, insert the parameter table from the test into the endpoint documentation:

```asciidoc
= Articles API

== Search articles by multiple tags

GET /api/articles

Example: /api/articles?tag=java&tag=spring

=== Query parameters

include::{snippets}/articles-multi-value-query/query-parameters.adoc[]
```

For `include` to work, configure the `{snippets}` attribute to point to the Spring REST Docs output directory. If you prefer Markdown, Spring REST Docs lets you select the Markdown template format via `TemplateFormats.markdown()`; you will then need a suitable Markdown authoring/assembly tool to include the snippet in the final page.

Recommended workflow:

1. Declare the `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient`, or `spring-restdocs-restassured` dependency matching your test tool.
2. Have the `test` task output to the snippets directory (such as `build/generated-snippets`).
3. Make the Asciidoctor/documentation packaging task **depend on** the `test` task so snippets are generated before pages are rendered.
4. Run tests and documentation build in CI. When a test or the documentation build step fails, the pipeline should fail so the team fixes either the API contract or the snippet path.

REST Docs verifies the descriptions of *query parameter names* in the request under test. To make multi-value documentation trustworthy, tests should also assert cardinality, ordering, AND/OR rules, deduplication, and validation if the API commits to those behaviors.

## 9. Common errors

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `tag=java&tag=spring` is documented with two `tag` descriptors | Confusing occurrence count with parameter name count | Document `parameterWithName("tag")` only once |
| `tag` is documented, but the test sends `tag[]` | Name after URL decoding does not match the descriptor | Standardize the parameter name contract and update the request/descriptor |
| API accepts `tag=java,spring`, but sometimes fails to split the list | Relying on an unspecified converter or delimiter format | Pick one format, test parser behavior, and document it clearly |
| Values containing `+`, `&`, or spaces get altered | Concatenating URLs without proper encoding | Use a URI builder/`queryParam` and inspect the outgoing request |
| `queryParameters(...)` succeeds, but the app handles `sort` order incorrectly | REST Docs checks names, not value ordering | Add result assertions and tests for sort priority |
| `tag` is absent from the request while its descriptor is required | Parameter name is declared but missing from the test | Send at least one value or add `optional()` if the API allows omitting it |
| `tag` data is sent, yet the snippet does not appear | Wrong identifier, missing `queryParameters(...)`, or misconfigured output | Check `document(...)`, the snippets directory, and the `include` directive |

## 10. Hands-on exercise

Given this hypothetical API:

```http
GET /api/products?category=laptop&category=monitor&brand=acme&brand=example&sort=price:asc&page=1 HTTP/1.1
```

Contract:

- `category` can be repeated; results match at least one selected category.
- `brand` can be repeated; the brand filter combines with the category filter using AND, while values within the brand group combine using OR.
- `sort` can be repeated, with syntax `field:direction`; prioritized by order of appearance; defaults to `createdAt:desc`.
- `page` accepts a single non-negative integer; defaults to 0.
- For `category` and `brand`, the server rejects empty values and limits each name to at most 10 values.

**Tasks:**

1. Write a controller or sample endpoint accepting `List<String>` for `category`, `brand`, and `sort`.
2. Write a MockMvc test using `.queryParam("category", "laptop", "monitor")` and similarly for `brand`; verify both values with assertions.
3. Create `queryParameters(...)` with only one `parameterWithName(...)` per name; write `description(...)` stating structure, defaults, and combination rules.
4. Try `brand=acme&brand=` and 11 `category` values. Add server-side validation and tests verifying the appropriate errors, since `queryParameters(...)` does not check these constraints on its own.
5. Generate `query-parameters.adoc`, include it in an Asciidoctor document, and verify again via build/CI.

**Completion criteria:** Documentation describes how to send multiple values and how the server combines them; the snippet has one row per query parameter name; HTTP tests demonstrate binding and handling of count/order/values per the contract.

## References

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
