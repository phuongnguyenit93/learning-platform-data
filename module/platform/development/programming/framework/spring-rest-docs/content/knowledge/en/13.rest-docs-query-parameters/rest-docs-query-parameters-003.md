# Required, optional, and absent parameters in Spring REST Docs

## 1. Why distinguish these three states?

Suppose a product search API supports:

```http
GET /api/products?q=laptop&page=2&sort=price HTTP/1.1
Host: api.example.test
```

According to the hypothetical API contract:

- `q` is a **required** keyword.
- `page` is an **optional** page index, defaulting to `0` if omitted.
- `sort` is an **optional** sort mode, defaulting to `relevance`.

A client can certainly send `GET /api/products?q=laptop`. In that case `page` and `sort` are **absent**: their parameter names do not appear in the query string. This differs from `?page=`, where the name `page` is present with an empty value.

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. In the **Query parameters** chapter, Spring REST Docs uses `queryParameters(...)` and `parameterWithName(...)` descriptors to record which parameters must appear in the *request under test*, which parameters may be omitted, and which parameter names have been documented. This verification catches mismatches between the documentation and example requests during build/CI runs.

After this lesson, you will be able to distinguish:

1. **Required**: a descriptor declared **without marking it optional**; REST Docs requires the parameter to appear in the documented request.
2. **Optional**: a descriptor using `.optional()`; the parameter may be absent in the documented request.
3. **Absent**: the actual state of a request when **a parameter name is missing**; it is not a separate REST Docs modifier.
4. **Empty / blank / repeated**: the parameter name is present, while the value may be empty, contain only whitespace, or appear multiple times; these require separate value tests.

## 2. Distinguishing absent, empty, blank, and present

| Request | State of `q` | Notes |
| --- | --- | --- |
| `/api/products?page=1` | **Absent** | No `q` key in the query string |
| `/api/products?q=` | **Present, empty** | The `q` key is present, but its value is an empty string |
| `/api/products?q=%20%20` | **Present, blank** | After decoding, the value consists of two spaces |
| `/api/products?q=laptop` | **Present, non-empty** | Has a text value |
| `/api/products?q=laptop&q=mouse` | **Present, repeated** | The same name `q` is sent multiple times |

`/api/products?q` (without `=`) is commonly interpreted by servers as a parameter with an empty value, though the exact query-string parsing behavior depends on the HTTP stack. Do not rely on this form to represent "absent".

**Key point:** `queryParameters(...)` primarily checks the **names and presence** of query parameters; it does not check whether `q` is empty, contains only spaces, matches a format, or belongs to a valid set of values. Use application validation and HTTP assertions to verify those constraints.

## 3. Required and optional at the Spring REST Docs documentation layer

### 3.1. Required descriptor

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q")
        .description("Product search keyword; required, must not be empty")
)
```

The `q` descriptor **does not call** `optional()`, so it is required under REST Docs' verification mechanism. If a test tries to document `GET /api/products?page=1`, the snippet processor does not find `q` and reports an error for a documented parameter missing from the request.

There is no `required()` method to call in this example: **the default state is required**.

### 3.2. Optional descriptor

```java
queryParameters(
    parameterWithName("q")
        .description("Required keyword"),
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0")
        .optional(),
    parameterWithName("sort")
        .description("Sort order; defaults to relevance")
        .optional()
)
```

With this set of descriptors, both of the following requests can pass the **parameter presence** check:

```http
GET /api/products?q=laptop&page=2&sort=price HTTP/1.1
```

```http
GET /api/products?q=laptop HTTP/1.1
```

In the second request, `page` and `sort` are absent, yet they do not cause a documentation error because `optional()` was called. The descriptors remain part of the snippet model, so they can still be listed in the documentation table. However, **do not assume the documentation template automatically renders a "Required/Optional" column**: how it is displayed depends on the template. State optionality rules and default values in `description(...)` or configure a custom column.

### 3.3. Expected verification results table

Suppose descriptors exist for `q` (required), `page` (optional), and `sort` (optional), using `queryParameters(...)` in its default mode:

| Query string | Name/presence check | Explanation |
| --- | --- | --- |
| `?q=laptop` | Pass | Both optional parameters are allowed to be absent |
| `?q=laptop&page=2` | Pass | `sort` is allowed to be absent |
| `?q=laptop&page=2&sort=price` | Pass | All present names are documented |
| `?page=2` | Fail | Missing required `q` |
| `?q=laptop&brand=acme` | Fail | `brand` is present without a descriptor |
| `?q=` | **May pass name check** | `q` is present; empty values must be checked separately by the application |

These evaluations apply only to the query parameter documentation mechanism and do not cover HTTP status codes determined by controllers, security, or validation.

## 4. How required in a controller differs from required in documentation

In Spring MVC, `@RequestParam` handles parameter receiving and binding:

```java
@RequestParam("q") String q

@RequestParam(name = "page", defaultValue = "0") int page

@RequestParam(name = "sort", required = false) String sort
```

| Controller configuration | When parameter name is absent | Relationship to REST Docs |
| --- | --- | --- |
| `@RequestParam("q") String q` | By default, Spring MVC returns HTTP 400 because `q` is missing | Declare `parameterWithName("q")` without calling `optional()` |
| `@RequestParam(name = "page", defaultValue = "0") int page` | Spring MVC uses `0`; `defaultValue` is also used for empty values | Declare `page` with `.optional()` and state the default clearly |
| `@RequestParam(name = "sort", required = false) String sort` | Typically binds to `null` for `String` | Declare `sort` with `.optional()` if clients may omit it |
| `@RequestParam("sort") Optional<String> sort` | Binds to `Optional.empty()` when absent | Declare with `.optional()` accordingly |

The two mechanisms operate at **two independent layers**:

- **Controller/Spring MVC** determines whether a request is valid, how values are converted to Java types, and what HTTP response is returned.
- **Spring REST Docs** determines whether the snippet matches the parameter names in the test request.

`.optional()` on `ParameterDescriptor` does not turn a required `@RequestParam` into an optional one. Conversely, `required = false` or `defaultValue` on the controller does not automatically add `.optional()` for Spring REST Docs.

If the two sides are declared inconsistently, you can end up with documentation claiming a parameter is "optional" while the server returns HTTP 400 when it is omitted. Therefore, you must write tests for both server behavior and snippet generation.

## 5. Complete example: optional truly absent in MockMvc

Sample controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/api/products")
    public String search(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "sort", required = false) String sort) {
        String effectiveSort = sort == null ? "relevance" : sort;
        return "q=" + q + ";page=" + page + ";sort=" + effectiveSort;
    }
}
```

Here `q` is required. If `page` is not sent, the server uses `0`; if `sort` is not sent, the controller explicitly selects `relevance`. The example uses a plain-text response to focus on binding and documentation; a real API can return JSON and add payload tests.

Complete test with JUnit 5 and REST Docs:

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
class ProductQueryParametersTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setup(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsAbsentOptionalParameters() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", "laptop"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "q=laptop;page=0;sort=relevance"))
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("q")
                                        .description("Search keyword; required"),
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0")
                                        .optional(),
                                parameterWithName("sort")
                                        .description("Sort order; defaults to relevance")
                                        .optional()
                        )));
    }

    @Test
    void rejectsAbsentRequiredParameter() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("page", "2"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsEmptyQAtBindingLayerWithoutValidation() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "q=;page=0;sort=relevance"));
    }
}
```

**Analysis of the three tests:**

1. `documentsAbsentOptionalParameters` sends only `q`. Spring REST Docs still generates the table describing `q`, `page`, and `sort` because the latter two have `.optional()`. The assertion proves the server actually applies the defaults.
2. `rejectsAbsentRequiredParameter` omits `q`. Spring MVC detects the missing required `@RequestParam` and returns HTTP 400. This is an error-behavior test; do not attach the required descriptor set to generate a query parameters snippet for a request intentionally missing `q`.
3. `acceptsEmptyQAtBindingLayerWithoutValidation` sends `q` with an empty string value. A plain `String` `@RequestParam("q")` is not equivalent to `@NotBlank`. If the contract requires a non-empty keyword, add validation or business checks, then update the test to expect HTTP 400.

Using MockMvc's `queryParam(...)` instead of `param(...)` is intentional. `queryParam(...)` places the parameter in the **query string** so Spring REST Docs can document it via `queryParameters(...)`; `param(...)` only adds generic Servlet request parameters, which may not appear in the query string.

## 6. Testing absent, empty, and invalid values serves different purposes

When designing a test suite, separate these cases:

| Case | Example | What the test must verify |
| --- | --- | --- |
| Required present | `?q=java` | Controller handles it properly, snippet is generated successfully |
| Optional absent | `?q=java`, without `page` | Default value or filter-skipping behavior works; snippet does not report missing `page` |
| Required absent | `?page=2`, without `q` | HTTP 400 or defined contract error |
| Required present but empty | `?q=` | Server validation handles empty value per the contract |
| Required present but blank | `?q=%20%20` | Validation checks whitespace if disallowed |
| Optional present with wrong type | `?q=java&page=abc` | Binding/validation error tested separately |
| Optional present out of range | `?q=java&page=-5` | Business constraint or Bean Validation tested separately |
| Undocumented name | `?q=java&lang=vi` | Strict `queryParameters(...)` detects `lang` has no descriptor |

Note: HTTP 400 for empty, blank, or out-of-range values **does not happen automatically in every application**. Corresponding binding/validation rules must exist; error codes and response bodies must be tested according to the specific contract.

### Repeated parameters

```http
GET /api/products?q=phone&tag=android&tag=5g HTTP/1.1
```

Multiple occurrences of `tag` do not change how required/optional is marked on the descriptor:

```java
parameterWithName("tag")
    .description("Repeatable, e.g. tag=android&tag=5g; omit to skip tag filtering")
    .optional()
```

`.optional()` allows the **name `tag` to be absent**. It does not enforce a limit on the number of repetitions when `tag` is present; count and value limits must be enforced by application validation.

## 7. What `optional()` does not do

| Misconception | Reality |
| --- | --- |
| Calling `.optional()` automatically makes the controller accept an optional parameter | `.optional()` only affects snippet verification |
| Required means the value cannot be empty | Required in REST Docs mainly requires the **name** to appear |
| An absent parameter is equivalent to `?name=` | Absent means **no name**; `?name=` has a name with an empty value |
| `.optional()` automatically generates an "Optional" column in every document | Columns and rendering depend on the template; state the meaning in text |
| Using `relaxedQueryParameters(...)` makes all parameters optional | Relaxed ignores **undocumented names**, whereas declared descriptors must still be present unless marked optional |
| `.ignored()` is the same as `.optional()` | Ignored excludes a known parameter from the documentation table; optional allows absence while still documenting it |

Example of relaxed mode:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedQueryParameters;

relaxedQueryParameters(
    parameterWithName("q").description("Keyword; required"),
    parameterWithName("page").description("Page").optional()
)
```

A request with an additional `debug=true` is not flagged as undocumented in relaxed mode. However, if the request omits `q`, it still fails the required descriptor check. For official API documentation to catch unrecorded parameter additions, use strict `queryParameters(...)`.

## 8. Separately documenting error responses when required is absent

For HTTP 400 caused by omitting `q`, you can generate a separate **request/response** snippet to show clients how to fix it. For instance, in a test configured with REST Docs:

```java
mockMvc.perform(get("/api/products")
                .queryParam("page", "2"))
        .andExpect(status().isBadRequest())
        .andDo(document("products-search-missing-q"));
```

Calling `document("products-search-missing-q")` generates the default HTTP request/response snippets. This call **does not pass `queryParameters(...)` containing a required `q` descriptor**, because the test's purpose is to intentionally send a request without `q`. The main endpoint documentation still pulls the query parameters table from the successful `products-search` test.

If you need a parameter table for an error request, design descriptors appropriate for that specific request or use a separate documentation test for valid requests. Do not mark `q` as optional just to make an error test pass if the real contract requires `q`.

## 9. From snippets to Asciidoctor, Markdown, and CI

After running the `documentsAbsentOptionalParameters` test, the default snippet path typically corresponds to:

```text
build/generated-snippets/products-search/query-parameters.adoc
```

The actual path depends on your project's output directory configuration; Maven typically uses `target/generated-snippets/`.

To embed the parameter table in `src/docs/asciidoc/products.adoc`:

```asciidoc
= Products API

== Search products

GET /api/products

=== Query parameters

include::{snippets}/products-search/query-parameters.adoc[]

=== Example request missing q

include::{snippets}/products-search-missing-q/http-request.adoc[]
```

The `{snippets}` attribute must point to the directory containing the snippets. With Gradle or Maven, the workflow should:

1. Declare the `spring-restdocs-mockmvc` test dependency (or `spring-restdocs-webtestclient`, `spring-restdocs-restassured`) matching your project version.
2. Configure the snippet output directory and make the documentation task depend on the tests that generate the snippets.
3. Run the tests to generate snippets; then render Asciidoctor to HTML, or use `TemplateFormats.markdown()` if the project intentionally outputs Markdown snippets.
4. Execute the entire pipeline in CI; if snippets are missing, names change, or contract tests fail, the documentation build must not be considered successful.

Markdown has no standard `include` directive like Asciidoctor; if using Markdown, you need a content assembly step or publishing tool that supports linking the corresponding snippets.

### Do WebTestClient and REST Assured follow different rules?

No. `parameterWithName("q")`, `.optional()`, and `queryParameters(...)` share the same semantics across all three integrations. The differences lie mainly in how requests are sent and how `document(...)` is attached:

- **MockMvc:** `.queryParam(...)` on the request builder, then `.andDo(document(...))`.
- **WebTestClient:** URI containing the query string, then `.expectBody().consumeWith(document(...))`.
- **REST Assured:** `.queryParam(...)` and the REST Docs documentation filter.

In all three cases, absent must be tested with an actual request that **does not send the parameter name**; do not simulate absent using an empty string.

## 10. Practice exercise

Given the endpoint:

```http
GET /api/orders?customerId=42&page=0&size=20&status=PAID HTTP/1.1
```

Intended contract:

- `customerId`: required, positive integer ID.
- `page`: optional, non-negative integer, defaults to 0.
- `size`: optional, from 1 to 100, defaults to 20.
- `status`: optional, accepts only `PENDING`, `PAID`, or `CANCELLED`; when absent, returns orders in all statuses.

Proceed step by step:

1. Write four `parameterWithName(...)` descriptors; keep `customerId` required and call `.optional()` on the remaining three parameters.
2. Write a passing test with a request containing only `customerId=42`, verify the server defaults, and generate `query-parameters.adoc`.
3. Write a test missing `customerId` and verify the HTTP error according to the contract. Do not invoke the valid endpoint's `queryParameters(...)` in this test.
4. Write tests with `customerId=` and `customerId=abc`; distinguish **name present with invalid value** from absent.
5. Add `currency=VND` to the passing request without a descriptor; observe the documentation error in strict mode, then align the documentation or API for consistency.
6. Include the snippet in Asciidoctor and verify that the build/CI step produces a page with the parameter table.

**Pass criteria:** Tests verify the effect of absent parameters on controller behavior; the snippet does not fail on absent optional descriptors; required parameters are still enforced; separate tests cover empty/invalid values; documentation and HTTP requests follow a single contract.

## 11. Summary

In Spring REST Docs, required/optional are **descriptor verification rules**, while absent is a **request state**. `parameterWithName("...")` is required by default; add `.optional()` when that name is allowed to be omitted. Check `@RequestParam` and server validation so the documentation reflects actual behavior, then integrate snippets into Asciidoctor/Markdown and CI pipelines to keep the API contract continuously verified.

### References

- [Spring REST Docs Reference — Query parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
