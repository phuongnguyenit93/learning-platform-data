# Default values and conditional applicability of query parameters in Spring REST Docs

## 1. The problem: parameters can be absent while the API still has processing rules

Consider an order search endpoint:

```http
GET /api/orders?page=2&status=PAID HTTP/1.1
Host: api.example.test
```

The client only sends `page` and `status`. The server may automatically apply `size=20` because the client did not send `size`. Similarly, an API may allow omitting `fromDate` and `toDate` when not filtering by date, yet **require both** when the user enables date-range filtering.

These are two separate concerns:

- **Default value:** When the client does not supply a parameter, what value does the server choose?
- **Conditional applicability:** When is a parameter allowed, required, ignored, or required to appear alongside another parameter?

In the **SPRING_REST_DOCS** module, Spring REST Docs generates verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. In the **Query parameters** chapter, we document these two concerns using `parameterWithName(...).description(...)`, apply `optional()` when a parameter name may be absent, and write additional behavioral tests to verify the default and conditional rules.

After this lesson, you will be able to:

1. Distinguish Spring MVC default values from how REST Docs verifies the query string.
2. Accurately document defaults, scope of applicability, valid values, and inter-parameter relationships.
3. Write an endpoint along with HTTP tests covering absent values, empty values, explicit values, and dependent parameters.
4. Generate `query-parameters.adoc`, include it in Asciidoctor/Markdown documentation, and run it in build/CI.

## 2. Default values belong to the server's processing contract

In Spring MVC, `@RequestParam` has a `defaultValue` attribute:

```java
@GetMapping("/api/orders")
public String list(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size,
        @RequestParam(name = "status", defaultValue = "ALL") String status) {
    return "page=" + page + ";size=" + size + ";status=" + status;
}
```

In this example, the values `0`, `20`, and `ALL` are server-side decisions. Using `defaultValue` also makes the corresponding parameter optional at the Spring MVC binding layer.

### 2.1. Absent, empty, and explicit values

| Incoming request | Value of `page` in controller | Explanation |
| --- | --- | --- |
| `/api/orders` | `0` | `page` omitted; default is used |
| `/api/orders?page=` | `0` | `page` name is present with an empty value; `@RequestParam(defaultValue = "0")` applies the default |
| `/api/orders?page=3` | `3` | Explicit value overrides the default |
| `/api/orders?page=abc` | Type conversion error, typically HTTP 400 response | Non-empty value that is not an integer |
| `/api/orders?page=-1` | `-1` after binding | Conversion succeeds; rejected only if the application validates `page >= 0` |

Do not equate an **empty value** with a **whitespace-only value**: `page=%20` may go through conversion differently depending on configuration. If the contract needs to specify whitespace handling, test that exact request.

Common point of confusion: A default value chosen by the server **is not injected back into the HTTP request's query string**. For example, `GET /api/orders?page=2` still does not contain `size` even though the controller received `size=20`. REST Docs documents the actual request, without automatically adding `size=20` into the request snippet.

### 2.2. When `defaultValue` is not used

```java
@RequestParam(name = "status", required = false) String status
```

With a reference type like `String`, when `status` is omitted, the controller typically receives `null`. If the application determines a default inside the service layer, `description(...)` must still describe the actual effective value the consumer receives; do not guess defaults solely from annotations. For primitive, enum, or custom-typed parameters, verify binding behavior when the value is absent.

## 3. Documenting defaults with `parameterWithName` and `optional()`

Suppose the team's API contract specifies:

| Parameter | Can be omitted? | Default/condition |
| --- | --- | --- |
| `page` | Yes | Zero-based page index; defaults to `0` |
| `size` | Yes | From 1 to 100; defaults to `20` |
| `status` | Yes | `ALL`, `PAID`, or `CANCELLED`; defaults to `ALL` |
| `fromDate` | Conditionally | Start date as `yyyy-MM-dd`; **must appear with** `toDate` |
| `toDate` | Conditionally | End date as `yyyy-MM-dd`; **must appear with** `fromDate` and must not be before `fromDate` |

Description in Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0 if omitted or empty")
        .optional(),
    parameterWithName("size")
        .description("Results per page (1-100); defaults to 20")
        .optional(),
    parameterWithName("status")
        .description("ALL, PAID, or CANCELLED; defaults to ALL")
        .optional(),
    parameterWithName("fromDate")
        .description("Start date yyyy-MM-dd; if provided, toDate is required")
        .optional(),
    parameterWithName("toDate")
        .description("End date yyyy-MM-dd; requires fromDate and must not be earlier than fromDate")
        .optional()
)
```

`queryParameters(...)` is a factory method on `org.springframework.restdocs.request.RequestDocumentation`. Each `parameterWithName("...")` creates a descriptor for a parameter **name**. `description(...)` supplies the explanatory text in the documentation; `optional()` tells REST Docs that the name **is permitted to be absent from the test request**.

### What `optional()` does not do

- Does not set a default value on the controller.
- Does not verify that `size` is within 1–100.
- Does not check that `status` belongs to an allowed set.
- Does not know that `fromDate` is only valid when `toDate` is also present.
- Does not automatically infer default values from `@RequestParam`, `@PageableDefault`, or service configuration.

**Therefore, accurate descriptions are only the first step.** For documented conditions to be meaningfully verified, you need validation and HTTP tests covering both allowed and rejected branches.

## 4. Conditional applicability: from "may be absent" to "required when..."

A parameter can be **optional in a normal request** yet **conditionally required**. For the two date-range filter parameters:

| `fromDate` | `toDate` | Result under the sample contract |
| --- | --- | --- |
| Not sent | Not sent | Valid, no date filtering |
| Present | Present | Valid if both match the format and `fromDate <= toDate` |
| Present | Not sent | Invalid: missing end date |
| Not sent | Present | Invalid: missing start date |
| Present but empty | Present | Invalid: start date is not a valid ISO date |

REST Docs has no `conditionallyRequired()` modifier that automatically checks these relationships inside `queryParameters(...)`. Marking both `.optional()` is appropriate because each parameter may be absent when **the entire pair is absent**. The rule "if A is present, B must be present" is described via `description(...)` and enforced in the controller/service/validation layer.

Examples of other relationships:

| Relationship | Example | What must be written in documentation |
| --- | --- | --- |
| **Applies only in a specific mode** | `cursor` is only used when `mode=cursor` | Which `mode` value activates `cursor`, and whether `cursor` is required in that mode |
| **Mutually exclusive** | `cursor` cannot be used with `page` | Whether the server rejects or ignores when the client sends both |
| **Required as a pair** | `fromDate` and `toDate` | Both can be omitted; if used, both must be provided |
| **Default depends on another parameter** | Default `sort` depends on `status` | List each default case, precedence rules, and outcome when `sort` is omitted |
| **Conditionally bounded** | `size` max 100 when `mode=search` | Valid range in each mode and error code when exceeded |

These rules are **API design choices of each application**, not capabilities automatically enforced by Spring REST Docs.

## 5. Building a sample controller with defaults and conditional validation

The following controller implements the exact contract from sections 3 and 4. It returns a string for easy data verification in tests, rather than querying a database or serializing JSON:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class OrderController {

    private static final Set<String> STATUSES =
            Set.of("ALL", "PAID", "CANCELLED");

    @GetMapping("/api/orders")
    public String search(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size,
            @RequestParam(name = "status", defaultValue = "ALL") String status,
            @RequestParam(name = "fromDate", required = false) String fromDate,
            @RequestParam(name = "toDate", required = false) String toDate) {

        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page/size out of range");
        }
        if (!STATUSES.contains(status)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "status is unsupported");
        }

        // The date pair is valid only when both are absent or both are present.
        if ((fromDate == null) != (toDate == null)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "fromDate and toDate must appear together");
        }

        String range = "none";
        if (fromDate != null) {
            try {
                LocalDate from = LocalDate.parse(fromDate);
                LocalDate to = LocalDate.parse(toDate);

                if (from.isAfter(to)) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST, "fromDate is after toDate");
                }
                range = from + ".." + to;
            } catch (DateTimeParseException exception) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "invalid ISO date", exception);
            }
        }

        return "page=" + page
                + ";size=" + size
                + ";status=" + status
                + ";range=" + range;
    }
}
```

Notes:

- `defaultValue` handles absent or empty `page`, `size`, and `status` parameters.
- Range checks, status allowlist checks, and date checks live **in the controller**, making the documented conditions genuinely enforced.
- `LocalDate.parse(...)` follows the standard ISO date format `yyyy-MM-dd`; invalid date values result in HTTP 400.
- The `fromDate`/`toDate` pair rule applies whenever either parameter name is supplied. An empty value like `fromDate=` is not treated as a valid date.
- This is an instructional endpoint for learning documentation; production projects should place business rules in appropriate service/validation layers.

## 6. MockMvc testing and generating REST Docs snippets

To make documentation verifiable, combine behavioral assertions with `document(...)`. Example using JUnit 5, MockMvc, and Spring REST Docs:

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
class OrderQueryDefaultsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsOptionalParametersAndTheirDefaults() throws Exception {
        // Client sends only page; size/status use defaults,
        // and fromDate/toDate are both absent so no date filtering is applied.
        mockMvc.perform(get("/api/orders").queryParam("page", "2"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=2;size=20;status=ALL;range=none"))
                .andDo(document("orders-search-defaults",
                        queryParameters(
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Results per page (1-100); defaults to 20")
                                        .optional(),
                                parameterWithName("status")
                                        .description("ALL, PAID, CANCELLED; defaults to ALL")
                                        .optional(),
                                parameterWithName("fromDate")
                                        .description("Start date yyyy-MM-dd; must appear with toDate")
                                        .optional(),
                                parameterWithName("toDate")
                                        .description("End date yyyy-MM-dd; must appear with fromDate")
                                        .optional()
                        )));
    }

    @Test
    void appliesDefaultsWhenValuesAreMissing() throws Exception {
        mockMvc.perform(get("/api/orders"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=0;size=20;status=ALL;range=none"));
    }

    @Test
    void appliesDefaultsWhenValuesAreEmpty() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .queryParam("page", "")
                        .queryParam("size", "")
                        .queryParam("status", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=0;size=20;status=ALL;range=none"));
    }

    @Test
    void acceptsBothDateParameters() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .queryParam("fromDate", "2026-11-01")
                        .queryParam("toDate", "2026-11-30"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=0;size=20;status=ALL;range=2026-11-01..2026-11-30"));
    }

    @Test
    void rejectsPartialDateRange() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .queryParam("fromDate", "2026-11-01"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders")
                        .queryParam("toDate", "2026-11-30"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidValues() throws Exception {
        mockMvc.perform(get("/api/orders").queryParam("size", "101"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders").queryParam("page", "oops"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders").queryParam("status", "UNKNOWN"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders")
                        .queryParam("fromDate", "2026-11-30")
                        .queryParam("toDate", "2026-11-01"))
                .andExpect(status().isBadRequest());
    }
}
```

In the documentation test, only `page=2` actually appears in the URL. The other descriptors are marked `.optional()`, so REST Docs does not require their names to appear in that request. However, **the documentation table still includes a description row** for each descriptor; defaults and conditions are clearly stated by `description(...)`.

The remaining tests verify behavior that REST Docs **does not check automatically**: defaults apply when absent/empty, the date pair is valid only when complete, and invalid values are rejected.

### 6.1. Why is `queryParam(...)` needed?

With MockMvc and REST Docs versions that provide `queryParameters(...)`, use `.queryParam("page", "2")` or the URL `get("/api/orders?page=2")` to document the query string. `.param("page", "2")` only sets a generic Servlet request parameter, which can originate from either the query string or a form body; the controller may receive the value while REST Docs does not see an actual query parameter.

### 6.2. What happens if you forget `optional()`?

The following example fails when the test request omits `size`:

```java
// Request GET /api/orders?page=2 has no size.
queryParameters(
    parameterWithName("page").description("Page index"),
    parameterWithName("size").description("Defaults to 20")
)
```

`description("Defaults to 20")` is descriptive text; **it does not make the descriptor optional**. When `size` is absent, Spring REST Docs reports an error by default because that descriptor is treated as required. The proper fix is to add `.optional()` if the API contract actually permits omitting `size`.

## 7. Reading snippets and including them in Asciidoctor/Markdown documentation

After running a test with `document("orders-search-defaults", ...)`, with Gradle configured to write snippets to `build/generated-snippets`, you will find:

```text
build/
  generated-snippets/
    orders-search-defaults/
      query-parameters.adoc
      http-request.adoc
      http-response.adoc
      curl-request.adoc
      ...
```

The directory name corresponds to the `orders-search-defaults` identifier; in Maven, the default directory is typically `target/generated-snippets`. `query-parameters.adoc` displays parameter names and their descriptions; REST Docs does not automatically insert default numbers from the controller if the descriptor omits them.

The documentation page `src/docs/asciidoc/orders.adoc` can include the snippet:

```asciidoc
= Orders API

== Search orders

GET /api/orders

=== Query parameters

include::{snippets}/orders-search-defaults/query-parameters.adoc[]

=== Date filter rules

If fromDate and toDate are omitted, the API does not filter by date.
When filtering by date, both parameters must be passed in yyyy-MM-dd format
and fromDate must not be after toDate.
```

When building with Asciidoctor, configure `{snippets}` to point where tests write snippets and make the documentation rendering task depend on the `test` task.

Spring REST Docs also supports the Markdown snippet format via `TemplateFormats.markdown()`. If using Markdown, choose an appropriate tool to assemble snippets into the final output page since plain Markdown has no standard `include` syntax like Asciidoctor.

## 8. Same approach with WebTestClient and REST Assured

`parameterWithName(...).description(...).optional()` descriptors stay the same across testing tools. What changes is primarily how requests are sent and where `document(...)` is attached.

### WebTestClient

Example with a client already configured for Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(uriBuilder -> uriBuilder.path("/api/orders")
                .queryParam("page", 2)
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("orders-search-defaults",
                queryParameters(
                        parameterWithName("page")
                                .description("Zero-based page index; defaults to 0")
                                .optional(),
                        parameterWithName("size")
                                .description("Results per page; defaults to 20")
                                .optional()
                )));
```

This example documents the two names `page` and `size` of a simplified contract; for a real endpoint with additional parameters, document all parameters according to the request scope and official documentation.

### REST Assured

With the `spring-restdocs-restassured` integration, send requests with a query string using `queryParam(...)`; configure `queryParameters(...)` inside the documentation filter:

```java
given()
    .filter(documentationFilter)
    .queryParam("page", 2)
    .when()
    .get("/api/orders")
    .then()
    .statusCode(200);
```

Here `documentationFilter` represents a filter created with REST Docs configuration and `document(..., queryParameters(...))`; the request call alone is not enough to generate a snippet.

## 9. Build and CI workflow

A practical workflow for documentation tests:

1. Declare the Spring REST Docs dependency matching your tool: `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient`, or `spring-restdocs-restassured`; choose a version compatible with Spring Framework/Spring Boot.
2. Configure the test task's output as the snippets directory, such as `build/generated-snippets`.
3. Make the Asciidoctor task or Markdown assembly step depend on the test task, supplying the snippets path to the renderer.
4. In CI, run both tests and the documentation build task; the pipeline fails if tests fail or snippets are missing/mispathed.

To avoid documentation stating incorrect defaults or conditional rules, maintain **behavioral tests** alongside snippet-generating tests. When changing a default from `20` to `50`, updating only the annotation or logic is not enough: update `description(...)` and assertions for the absent case as well.

## 10. Common mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Docs say "defaults to 20" while server returns 50 | `description(...)` was updated manually and does not read values from the controller | Check annotations/service logic and assertions when `size` is omitted |
| REST Docs test reports missing `size` even though controller uses `defaultValue` | `size` descriptor lacks `.optional()` | Mark it optional in docs if clients are allowed to omit the parameter |
| `fromDate` appears alone, yet docs still build successfully | REST Docs checks names and knows nothing about its relationship with `toDate` | Add validation and HTTP 400 tests |
| `page=abc` errors despite having default 0 | `defaultValue` does not override an explicit invalid value | Test conversion and appropriate error responses |
| `size=-1` passes the binding layer | Valid integer type, but invalid business value | Enforce range limits with validation |
| Query string has no `size` even though response shows size 20 | Default is applied during server binding | Document the default in the snippet; do not expect REST Docs to inject queries into the request |
| Docs build succeeds, but table is missing | Wrong `{snippets}` path, wrong identifier, or missing `queryParameters(...)` | Check snippet output and task dependencies |
| Using `relaxedQueryParameters(...)` hides a new parameter | Relaxed mode allows undocumented names | Prefer strict `queryParameters(...)` when publishing official documentation |

## 11. Hands-on exercise

Design a hypothetical API:

```http
GET /api/reports?format=CSV&month=2026-11&includeDetails=true HTTP/1.1
```

Contract:

- `format`: optional, defaults to `JSON`, accepts only `JSON` or `CSV`.
- `month`: permitted only when `format=CSV`; in CSV mode, `month` is required and formatted as `yyyy-MM`.
- `includeDetails`: optional, defaults to `false`; takes effect only in CSV mode.

Tasks:

1. Create an endpoint implementing the defaults and conditions above. Decide explicitly whether the server **rejects or ignores** `includeDetails` when `format=JSON`, and reflect that consistently in both code and documentation.
2. Write `queryParameters(...)` documenting each parameter with appropriate `.optional()` calls. For `month`, state the `format`-dependent requirement in `description(...)`.
3. Write tests for a request with no query string, `?format=CSV&month=2026-11`, `?format=CSV`, and `?format=JSON&month=2026-11`.
4. Add tests for malformed `month` or non-boolean `includeDetails`, checking HTTP error codes.
5. Include the snippet in your project's Asciidoctor or Markdown workflow; run tests together with documentation generation in CI.

**Completion criteria:** Accurate default descriptions exist for each parameter; tests prove defaults and conditional rules; snippets are generated from real requests and documentation pages pull in the right snippet.

## 12. Key takeaways

In Spring REST Docs, `parameterWithName(...)` documents the query parameter name, `description(...)` publishes **defaults and usage conditions**, and `optional()` only allows the parameter to be absent in the documented request. Real defaults belong to application binding/logic; inter-parameter dependencies must be enforced and verified with dedicated tests. When both are combined, Asciidoctor/Markdown documentation generated from tests reflects a clear HTTP contract ready for build/CI integration.

### References

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Documenting your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring Framework — Method Arguments: `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework Javadoc — `RequestParam.defaultValue`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestParam.html)
