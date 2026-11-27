# Pagination, sorting, and filtering parameters in Spring REST Docs

## 1. Real-world problem and objectives

A product listing endpoint typically accepts query parameters to limit results, specify ordering, and filter data:

```http
GET /api/products?page=1&size=10&sort=price,asc&sort=id,asc&status=ACTIVE&status=PREORDER&q=gaming%20phone&minPrice=100&maxPrice=500 HTTP/1.1
Host: api.example.test
Accept: application/json
```

In this request:

- `page=1` selects the second page if the system uses a **zero-based** page index.
- `size=10` requests at most 10 results per page.
- Two occurrences of `sort` describe two sort criteria in priority order.
- Two occurrences of `status` select two statuses; how they are combined must be defined.
- `q` is a search keyword; `minPrice` and `maxPrice` bound the price range.

The **SPRING_REST_DOCS** module uses **Spring REST Docs** to generate verifiable API documentation directly from HTTP tests using MockMvc, WebTestClient, or REST Assured. In the **Query parameters** chapter, we use `queryParameters(...)` and `parameterWithName(...)` to document pagination, sorting, and filtering contracts; include snippets into Asciidoctor/Markdown; and integrate testing and documentation generation into build/CI.

Objectives after this lesson:

1. Design and clearly document `page`, `size`, `sort`, and filters.
2. Distinguish required parameters, optional parameters, default values, and business rules.
3. Test both **accurate parameter name documentation** and **accurate value processing**.
4. Generate `query-parameters.adoc` and integrate the snippet into the endpoint documentation page.

## 2. Designing a query contract for a list endpoint

Before writing documentation tests, the team must agree on HTTP conventions. The table below is an **illustrative contract** for `GET /api/products`; it is not automatic behavior of every Spring MVC controller:

| Parameter | Syntax | Default | Conditions and meaning |
| --- | --- | --- | --- |
| `page` | Integer from 0 | `0` | Zero-based page index; single value only |
| `size` | Integer from 1 to 100 | `20` | Maximum items per page |
| `sort` | `field,direction`; repeatable | `createdAt,desc` plus `id,asc` for stable ordering | `field` must be `price`, `createdAt`, or `id`; `direction` is `asc` or `desc` |
| `status` | Repeatable: `status=ACTIVE&status=PREORDER` | No status filter | Each status belongs to `ACTIVE`, `PREORDER`, `ARCHIVED` |
| `q` | URL-encoded text string | No keyword filter | Searches according to application-defined rules |
| `minPrice` | Non-negative decimal | No lower bound | May be sent independently |
| `maxPrice` | Non-negative decimal | No upper bound | If sent with `minPrice`, then `maxPrice >= minPrice` |

Suppose the endpoint filters results using **AND across condition groups** (`status`, `q`, and price range), while using **OR across multiple `status` values**. When querying real data, the service/repository layer must implement this exact rule and have tests verifying it.

Details that must be published include: whether pages are 0-based or 1-based, `size` limits, allowed sort fields, priority order of multiple `sort` entries, how filters combine, number/date formats, behavior when parameters are missing or invalid, and tie-breaking rules for stable ordering when values match.

## 3. Pagination: `page`, `size`, and limits

### 3.1. Offset-based pagination by page number

If pages start at 0, the number of items to skip is typically:

```text
offset = page * size
```

For example, with `page=2&size=10`, a stably sorted dataset skips the first 20 results and returns up to the next 10 results. In public APIs, explicitly state that **`page=0` is the first page**. Do not assume consumers will guess whether `page=1` is the first page.

| Query | Result under the illustrative contract |
| --- | --- |
| No `page` and `size` | Page 0, up to 20 results |
| `?page=0&size=10` | Up to the first 10 results |
| `?page=2&size=10` | Up to 10 results after the first 20 |
| `?page=-1` | HTTP 400 because page is negative |
| `?size=0` or `?size=101` | HTTP 400 because it is outside the 1–100 range |
| `?page=abc` | Typically HTTP 400 due to `int` type conversion error |

Page size limits protect memory, query latency, and bandwidth. The API also needs to handle cases where `page * size` overflows integer limits or database query limits when converted into an offset. These rules live in the application and database, **not automatically checked by Spring REST Docs**.

### 3.2. Stable pagination when data changes

If `sort=price,asc` and multiple products share the same price, their ordering can become non-deterministic. In the illustrative contract, the API automatically appends `id,asc` as the final tie-breaker if the client has not provided `id`. As a result, within a data snapshot, rows with the same `price` maintain a deterministic order.

Even with stable ordering, when rows are inserted or deleted between requests, offset pagination can still cause clients to observe duplicated or skipped records. If traversing a continuously mutating dataset is required, consider **cursor pagination** with `cursor` and `limit`; that is a separate contract requiring dedicated documentation for tokens, expiration, ordering, and consistency.

### 3.3. Response metadata

Documenting request `page`/`size` alone is not enough for a list API: clients also need to know how the response represents the current page and how to navigate pages. Sample response body:

```json
{
  "content": [
    {"id": 24, "name": "Gaming phone", "price": 250}
  ],
  "page": 1,
  "size": 10,
  "totalElements": 57,
  "totalPages": 6,
  "hasNext": true
}
```

This is an example structure defined by the application; Spring REST Docs does not require responses to include these fields. In a real project, use `responseFields(...)`/`responseBody(...)` to document the payload and write assertions for metadata if the API exposes it.

## 4. Sorting: repeated `sort`, precedence order, and allowlist

Common query:

```http
GET /api/products?sort=price,asc&sort=id,asc HTTP/1.1
```

The illustrative contract defines each value in the form `field,direction`. Because `sort` appears twice, the client requests sorting by ascending `price` first, then by ascending `id` on price ties.

| Case | Meaning or recommended handling |
| --- | --- |
| No `sort` sent | Defaults to `createdAt,desc`; appends `id,asc` as the final key |
| `sort=price,asc` | Sort by ascending price, then ascending `id` |
| `sort=price,desc&sort=id,asc` | Descending price, then ascending ID |
| `sort=unknown,asc` | HTTP 400 because the field is not in the allowlist |
| `sort=price,up` | HTTP 400 because sort direction is invalid |
| `sort=price` | HTTP 400 under a contract requiring full `field,direction` |

**Security and performance note:** Never concatenate client-supplied column names directly into SQL statements. Validate against an allowlist of fields and use parameterized query APIs or safe query builders. Public sort fields do not have to match physical database column names.

In Spring Data, `Pageable` and `Sort` can assist with pagination/sorting binding, though exact defaults and syntax depend on the application's resolver configuration. Whether `@RequestParam` splits multiple values or a comma-containing string must also be verified against the actual parameter type and converters; HTTP tests serve as proof of the contract.

## 5. Filtering data: filter names, repeated values, and ranges

### 5.1. Multiple values for one filter

```http
GET /api/products?status=ACTIVE&status=PREORDER HTTP/1.1
```

At the query string level, `status` appears twice. Under the contract being designed, the list means **ACTIVE or PREORDER**. In documentation, only **one** `parameterWithName("status")` descriptor is needed, clearly stating repeatability, valid enum names, and the OR rule.

When combined with `q=phone`, results must satisfy the status condition **and** the keyword. Do not infer AND/OR combination semantics solely from `@RequestParam List<String>`.

### 5.2. Range filters

```http
GET /api/products?minPrice=100&maxPrice=500 HTTP/1.1
```

Under the example contract, `minPrice` and `maxPrice` can be sent individually for a one-sided bound. If both are sent, the upper value must be greater than or equal to the lower value. When handling monetary amounts, clearly define currency units, rounding rules, and precision; `BigDecimal` avoids binary floating-point inaccuracies of `double` when comparing decimals.

### 5.3. Keywords and URL encoding

```http
GET /api/products?q=gaming%20phone HTTP/1.1
```

After URL decoding, `q` has the value `gaming phone`. If it contains `+` or `&`, clients must encode them properly rather than concatenating query strings manually. The contract should also clarify whitespace trimming, case sensitivity, which fields are searched, and special character escaping; these rules must be implemented in the search layer.

## 6. Documenting parameters with Spring REST Docs

Place the descriptors inside `queryParameters(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("page")
        .description("Zero-based page index; defaults to 0")
        .optional(),
    parameterWithName("size")
        .description("Items per page, 1-100; defaults to 20")
        .optional(),
    parameterWithName("sort")
        .description("Repeatable: sort=field,direction; field is price, createdAt, or id; "
            + "direction is asc or desc; defaults to createdAt,desc then id,asc")
        .optional(),
    parameterWithName("status")
        .description("Repeatable: ACTIVE, PREORDER, or ARCHIVED; "
            + "values combine with OR; omit for no filter")
        .optional(),
    parameterWithName("q")
        .description("Search keyword, URL-encoded; omit for no filter")
        .optional(),
    parameterWithName("minPrice")
        .description("Non-negative minimum price; optional")
        .optional(),
    parameterWithName("maxPrice")
        .description("Non-negative maximum price, not less than minPrice when both are present")
        .optional()
)
```

**`parameterWithName(...)` documents the name, not each individual value.** Therefore, `status=ACTIVE&status=PREORDER` has one descriptor for `status`, and `sort=price,asc&sort=id,asc` has one descriptor for `sort`. The `description(...)` text appears in the snippet table.

All descriptors in the example use `.optional()` because the endpoint allows requests without a query string. That only says a parameter name may **be absent** in the test request; it does not mean any value is valid. Nor does `.optional()` automatically configure defaults in the controller.

### 6.1. Strict, relaxed, and ignored

| Declaration | Meaning during documentation generation |
| --- | --- |
| `queryParameters(...)` | Default mode: fails if the request contains an undocumented query parameter name, or misses a required descriptor |
| `parameterWithName("page").optional()` | `page` is documented, yet may be absent from the request |
| `parameterWithName("trace").ignored()` | Acknowledges `trace` without including it in the snippet table |
| `relaxedQueryParameters(...)` | Allows the request to contain undocumented query parameter names; still enforces required descriptors |

When documenting official APIs, use strict `queryParameters(...)` to detect when new parameter names are added to requests without documentation. Use `ignored()` for intentional technical parameters and `relaxedQueryParameters(...)` when you genuinely want to document only part of a request.

### 6.2. Checking names differs from checking content

REST Docs can confirm that the query string contains the documented parameter `size`, but it does not infer from `description("1-100")` that `size=500` should return an error. Similarly, `sort=unknown,asc` still has a valid `sort` name as far as the descriptor is concerned. Value, order, and cross-parameter validation must reside in application code and be tested separately.

## 7. Complete example with MockMvc + JUnit 5

To make query-passing rules clear, the following controller simply **normalizes and echoes parameters back**. It does not query a database; in a real API, the service/repository must use the validated values to execute pagination, sorting, and filtering.

### 7.1. Sample controller

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class ProductSearchController {

    private static final Set<String> SORT_FIELDS =
            Set.of("price", "createdAt", "id");
    private static final Set<String> STATUSES =
            Set.of("ACTIVE", "PREORDER", "ARCHIVED");

    @GetMapping("/api/products")
    public String search(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size,
            @RequestParam(name = "sort", required = false) List<String> requestedSort,
            @RequestParam(name = "status", required = false) List<String> statuses,
            @RequestParam(name = "q", required = false) String q,
            @RequestParam(name = "minPrice", required = false) BigDecimal minPrice,
            @RequestParam(name = "maxPrice", required = false) BigDecimal maxPrice) {

        if (page < 0 || size < 1 || size > 100) {
            throw badRequest("page/size is out of range");
        }

        if ((minPrice != null && minPrice.signum() < 0)
                || (maxPrice != null && maxPrice.signum() < 0)
                || (minPrice != null && maxPrice != null
                    && minPrice.compareTo(maxPrice) > 0)) {
            throw badRequest("invalid price range");
        }

        List<String> selectedStatuses =
                statuses == null ? List.of() : statuses;
        for (String status : selectedStatuses) {
            if (!STATUSES.contains(status)) {
                throw badRequest("unsupported status");
            }
        }

        List<String> sortInput =
                requestedSort == null || requestedSort.isEmpty()
                    ? List.of("createdAt,desc")
                    : requestedSort;
        List<String> normalizedSort = new ArrayList<>();

        for (String spec : sortInput) {
            String[] parts = spec.split(",", -1);
            if (parts.length != 2
                    || !SORT_FIELDS.contains(parts[0])
                    || (!parts[1].equals("asc") && !parts[1].equals("desc"))) {
                throw badRequest("invalid sort: " + spec);
            }
            normalizedSort.add(parts[0] + ":" + parts[1]);
        }

        // Add a unique key as the final tie-breaker if the client did not send one.
        if (normalizedSort.stream().noneMatch(s -> s.startsWith("id:"))) {
            normalizedSort.add("id:asc");
        }

        String keyword = q == null ? "" : q.trim();
        String statusesText = selectedStatuses.isEmpty()
                ? "ALL"
                : String.join("|", selectedStatuses);
        String priceRange = (minPrice == null ? "*" : minPrice.toPlainString())
                + ".."
                + (maxPrice == null ? "*" : maxPrice.toPlainString());

        return "page=" + page
                + ";size=" + size
                + ";sort=" + String.join("|", normalizedSort)
                + ";status=" + statusesText
                + ";q=" + keyword
                + ";price=" + priceRange;
    }

    private static ResponseStatusException badRequest(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
```

Key points to note:

- `defaultValue` for `page`/`size` is a **Spring MVC** configuration, not a Spring REST Docs configuration.
- `List<String> requestedSort` and `List<String> statuses` receive lists of values for the same query name. Test them using the exact way clients send repeated values.
- Sort normalization validates both field name and direction to avoid accepting arbitrary input. `id:asc` is appended at the end if `id` is not already present.
- Non-negative prices and `minPrice <= maxPrice` are validated independently of `queryParameters(...)`.
- The returned string serves the lesson on HTTP binding and documentation. It is **not yet** actual search/pagination output from a repository.

### 7.2. Documentation test covering all parameter groups

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
class ProductQueryDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductSearchController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsPaginationSortingAndFiltering() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("page", "1")
                        .queryParam("size", "10")
                        .queryParam("sort", "price,asc", "id,asc")
                        .queryParam("status", "ACTIVE", "PREORDER")
                        .queryParam("q", "gaming phone")
                        .queryParam("minPrice", "100")
                        .queryParam("maxPrice", "500"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=1;size=10;sort=price:asc|id:asc;"
                        + "status=ACTIVE|PREORDER;q=gaming phone;price=100..500"))
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("page")
                                        .description("Zero-based page index; defaults to 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Page size, 1-100; defaults to 20")
                                        .optional(),
                                parameterWithName("sort")
                                        .description("Repeatable: field,direction; "
                                                + "field=price|createdAt|id, direction=asc|desc; "
                                                + "defaults to createdAt,desc then id,asc")
                                        .optional(),
                                parameterWithName("status")
                                        .description("Repeatable: ACTIVE, PREORDER, ARCHIVED; "
                                                + "combined with OR; omit for no filter")
                                        .optional(),
                                parameterWithName("q")
                                        .description("Search keyword; omit for no filter")
                                        .optional(),
                                parameterWithName("minPrice")
                                        .description("Minimum price, non-negative")
                                        .optional(),
                                parameterWithName("maxPrice")
                                        .description("Maximum price, non-negative; not less than minPrice")
                                        .optional()
                        )));
    }
}
```

The test performs two kinds of verification:

1. `status().isOk()` and `content().string(...)` verify how the server receives, validates, and normalizes values.
2. `document("products-search", queryParameters(...))` verifies query parameter names, generates snippets, and records descriptions matching the intended contract.

**Important note for MockMvc:** Use `.queryParam(...)` or put parameters directly in the URI when documenting with `queryParameters(...)`. `.param(...)` only adds generic Servlet request parameters, which can allow the controller to receive data while REST Docs does not recognize it as part of the query string.

### 7.3. Tests for defaults and invalid data

Because all parameters are declared `.optional()`, a request with no query string can still be valid. The tests below verify the controller's **actual defaults**:

```java
@Test
void usesDefaultsWhenQueryIsAbsent() throws Exception {
    mockMvc.perform(get("/api/products"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "page=0;size=20;sort=createdAt:desc|id:asc;"
                    + "status=ALL;q=;price=*..*"));
}

@Test
void rejectsInvalidPageSizeSortAndFilters() throws Exception {
    mockMvc.perform(get("/api/products").queryParam("page", "-1"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products").queryParam("size", "101"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products").queryParam("sort", "password,asc"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products").queryParam("status", "UNKNOWN"))
            .andExpect(status().isBadRequest());

    mockMvc.perform(get("/api/products")
            .queryParam("minPrice", "500")
            .queryParam("maxPrice", "100"))
            .andExpect(status().isBadRequest());
}
```

These two methods are added to the **same test class** from section 7.2. They catch regressions if someone changes `defaultValue`, removes range checks, or permits sorting by an unlisted field. To guarantee actual data filtering and pagination, add integration tests with a sample dataset checking returned items, `totalElements`, and ordering.

## 8. Snippets and Asciidoctor/Markdown

With Gradle configured to write snippets to `build/generated-snippets`, the test in section 7.2 produces the following directory layout:

```text
build/
  generated-snippets/
    products-search/
      query-parameters.adoc
      http-request.adoc
      http-response.adoc
      curl-request.adoc
      ...
```

Actual paths depend on your build configuration; Maven typically uses `target/generated-snippets`. With the Asciidoctor template, `query-parameters.adoc` contains a table of parameter names and their corresponding `description` text.

In `src/docs/asciidoc/products.adoc`:

```asciidoc
= Products API

== Search products

GET /api/products

=== Query parameters

include::{snippets}/products-search/query-parameters.adoc[]

=== Example query

include::{snippets}/products-search/http-request.adoc[]

=== Response

include::{snippets}/products-search/http-response.adoc[]
```

The `{snippets}` attribute must be configured to point to Spring REST Docs' output directory. If you need to document a JSON response and pagination metadata, add `responseFields(...)` to the real endpoint's test to generate the corresponding response fields table.

Spring REST Docs also supports selecting `TemplateFormats.markdown()` to generate Markdown-formatted snippets. Markdown has no standard `include` syntax like Asciidoctor; use a snippet-merging workflow compatible with your project's publishing tool.

### 8.1. Integrating documentation into build and CI

General workflow:

1. Declare the Spring REST Docs test dependency suited to your environment: `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient`, or `spring-restdocs-restassured`, together with JUnit/Spring Test.
2. Declare the `generated-snippets` directory as an output of the `test` task.
3. Configure the Asciidoctor/documentation packaging task to read snippets and **depend on the `test` task**.
4. Run tests, render HTML, and verify artifacts in CI; the pipeline must fail if either tests or documentation compilation fails.

Illustrative Gradle command once the project declares the corresponding plugins and tasks:

```bash
./gradlew test asciidoctor
```

Contract changes such as lowering maximum `size` from 100 to 50, renaming a `status`, or adding a new `sort` field require updating **both** validation and `description(...)`/documentation tests. REST Docs does not automatically infer business rules from description text alone.

## 9. Applying with WebTestClient and REST Assured

The `parameterWithName(...)` and `queryParameters(...)` descriptors are shared across integrations. How you send the query string and attach `document(...)` changes per tool.

### WebTestClient

Example with `webTestClient` already configured for REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder.path("/api/products")
                .queryParam("page", 1)
                .queryParam("sort", "price,asc", "id,asc")
                .queryParam("status", "ACTIVE", "PREORDER")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("products-search-webclient",
                queryParameters(
                        parameterWithName("page")
                                .description("Zero-based page index").optional(),
                        parameterWithName("sort")
                                .description("Repeatable field,direction").optional(),
                        parameterWithName("status")
                                .description("Repeatable; select multiple statuses").optional()
                )));
```

This example documents only the parameter names actually present in this request. For an endpoint with more parameters, official documentation should cover the full contract using appropriate descriptors; Spring REST Docs does not automatically extract descriptions from controller annotations.

### REST Assured

REST Assured lets you send query values with `queryParam(...)`:

```java
given()
    .filter(documentationFilter)
    .queryParam("page", 1)
    .queryParam("sort", "price,asc", "id,asc")
    .queryParam("status", "ACTIVE", "PREORDER")
    .when()
    .get("/api/products")
    .then()
    .statusCode(200);
```

`documentationFilter` represents a filter configured through the `spring-restdocs-restassured` module containing `document(..., queryParameters(...))`. The HTTP call alone will not generate snippets unless the filter is configured.

## 10. Common errors and how to resolve them

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| REST Docs test reports missing `sort` even though controller receives `sort` | Using `.param(...)` instead of a real query string | Send via `.queryParam(...)` or a URL with `?sort=...` |
| `page=1` is treated as the first page | Client and server disagree on 0-based vs. 1-based indexing | Finalize the convention and state it explicitly in `description(...)` |
| `size=500` still generates a snippet | REST Docs checks parameter names, not value bounds | Add validation and HTTP 400 tests for `size` |
| Two `sort` values sent, yet docs have two descriptors with the same name | Confusing multiple values with multiple parameter names | Use only one `parameterWithName("sort")` and document repetition |
| Page order changes between two calls on the same data | Sort lacks a tie-breaker key when values match | Apply a deterministic key such as `id` and test it |
| `status` filter accepts unpublished values | Missing enum/allowlist check | Validate against an allowlist and write negative tests |
| `minPrice > maxPrice` passes the documentation step | Price constraints are outside descriptor verification | Validate the range and assert a 400 response |
| Response reports an incorrect total count after filtering | Metadata counts over a different dataset than the returned set | Write integration tests with sample data checking filtered totals |
| HTML lacks the query parameters table | Wrong identifier, missing snippet, or docs task runs before tests | Check `document(...)`, snippets directory, and task ordering |

## 11. Hands-on exercise

Build documentation for the endpoint:

```http
GET /api/orders?page=0&size=25&sort=createdAt,desc&sort=id,asc&status=PAID&status=SHIPPED&fromDate=2026-11-01&toDate=2026-11-30 HTTP/1.1
```

Intended contract:

- `page` defaults to 0, non-negative; `size` defaults to 25, from 1 to 200.
- `sort` is repeatable, allowing only `createdAt`, `totalAmount`, `id` with `asc`/`desc`; append `id` for stability.
- `status` is repeatable; multiple values combine with OR, accepting only `PENDING`, `PAID`, `SHIPPED`, `CANCELLED`.
- `fromDate` and `toDate` must be both absent or both present, using `yyyy-MM-dd` format; the date range must be valid.
- Status and date-range condition groups combine with AND.

Tasks:

1. Write a controller/service receiving and validating the parameters; define responses when values are invalid or conflicting.
2. Write a MockMvc test sending multiple `sort`/`status` values via `queryParam(...)` and generating `query-parameters.adoc`; keep only one descriptor per parameter name.
3. Write tests verifying defaults when the request has no query string and errors when `size=201`, `sort=secret,asc`, or `toDate` is missing.
4. Use a mock dataset to verify item ordering, pagination, and **post-filter** total count, rather than checking only snippet descriptions.
5. Embed the snippet in Asciidoctor or Markdown and add both tests and documentation rendering to CI.

**Completion criteria:** Documentation clearly states defaults, value ranges, ordering, and filter rules; HTTP tests verify inputs and outputs; snippets are generated from tests; build/CI fails whenever the contract diverges.

## 12. Knowledge summary

`page` and `size` determine pagination; `sort` determines ordering; filters such as `status`, `q`, and price ranges narrow the result set. Spring REST Docs keeps query parameter name documentation tied to tested HTTP requests, while pagination, filtering, validation, and metadata behavior still must be verified with appropriate assertions. By combining `queryParameters(...)`, business-logic tests, and the build pipeline, documentation updates stay controlled alongside REST API changes.

### References

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring Framework — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
