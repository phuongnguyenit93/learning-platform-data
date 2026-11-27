# Documenting Search with Query Parameters and Pagination

## 1. Practice Objectives

In this capstone, you will document a product search API with filtering, sorting, and pagination using Spring REST Docs and MockMvc. Documentation tests send requests with realistic query parameters, verify the status and response payload, and then generate snippets describing the parameters and result fields.

The end result is Asciidoctor/Markdown documentation that is reproducible in the build and CI. When the API changes parameter names, pagination limits, or response structure, tests and descriptors detect that the documentation no longer matches.

Sample API:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/products | Search products |

Query parameters:

| Parameter | Meaning | Example | Default |
| --- | --- | --- | --- |
| q | Keyword to search in name/description | keyboard | None |
| category | Filter by category | accessories | None |
| minPrice | Minimum price | 100000 | None |
| maxPrice | Maximum price | 2000000 | None |
| page | Page number, zero-based | 0 | 0 |
| size | Number of items per page | 20 | 20 |
| sort | Field and sort direction | price,asc | createdAt,desc |

These values represent a sample contract. When applying this to an application, you must use the endpoint's real parameter names, defaults, and limits.

## 2. Designing Requests and Responses

A search request might look like:

~~~http
GET /api/products?q=keyboard&category=accessories&minPrice=100000&maxPrice=2000000&page=0&size=20&sort=price,asc
Accept: application/json
~~~

The response uses a pagination envelope:

~~~json
{
  "content": [
    {
      "id": "p-42",
      "name": "Mechanical Keyboard",
      "category": "accessories",
      "price": 1299000,
      "currency": "VND",
      "active": true
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1,
  "first": true,
  "last": true
}
~~~

Separate query parameters from response fields when writing descriptors. Query parameters describe data sent by the client in the URL; response fields describe data returned by the server.

## 3. DTOs and Response Model

Search results can be represented with DTOs:

~~~java
import java.math.BigDecimal;
import java.util.List;

record ProductSummary(
        String id,
        String name,
        String category,
        BigDecimal price,
        String currency,
        boolean active) {}

record ProductSearchResponse(
        List<ProductSummary> content,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean first,
        boolean last) {}
~~~

Data types and field paths in descriptors must be based on the JSON after Jackson serialization. If the application uses Spring Data `Page` directly, the JSON envelope may differ; prefer using a stable response DTO for publishing the API rather than relying on internal structures not intended to be public.

## 4. Controller and Query Contract

Illustrative controller:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductSearchController {

    @GetMapping
    ProductSearchResponse search(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String category,
            @RequestParam(required = false) BigDecimal minPrice,
            @RequestParam(required = false) BigDecimal maxPrice,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "createdAt,desc") String sort) {
        // Validate filter range, normalize sort and delegate to service.
        return productSearchService.search(
                q, category, minPrice, maxPrice, page, size, sort);
    }
}
~~~

This is an illustrative skeleton. In a real application, add constructor injection for the service and validate `page`/`size` limits, `sort` fields, and `minPrice`/`maxPrice`. The documentation must publish the limits that the endpoint actually enforces.

## 5. Configuring MockMvc and REST Docs

With Spring Boot tests:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductSearchDocumentationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

MockMvc sends requests directly through the Spring MVC test infrastructure. REST Docs writes snippets when the operation calls `document(...)`. Use a stable output directory so Asciidoctor can include the snippets after tests finish.

## 6. Documenting Query Parameters with Descriptors

Declare each parameter with `parameterWithName(...)`. For parameters that may be omitted, use `optional()`; if the API has a default, state it clearly in the description or metadata:

~~~java
queryParameters(
        parameterWithName("q")
                .optional()
                .description("Keyword to search in product name and description"),
        parameterWithName("category")
                .optional()
                .description("Category code to filter by"),
        parameterWithName("minPrice")
                .optional()
                .description("Minimum price, in the product's currency"),
        parameterWithName("maxPrice")
                .optional()
                .description("Maximum price"),
        parameterWithName("page")
                .description("Page number, zero-based; defaults to 0"),
        parameterWithName("size")
                .description("Number of items per page; defaults to 20"),
        parameterWithName("sort")
                .description("Field and sort direction; defaults to createdAt,desc"))
~~~

`page`, `size`, and `sort` can still be sent explicitly in the request so the test verifies behavior. If the API allows omitting them, mark them `optional()` and explain the default. Descriptors only document the contract; a separate test must verify that the server actually applies those defaults.

## 7. Documenting Response Fields of the Pagination Envelope

Response fields need to cover both the pagination metadata and the items inside `content`:

~~~java
responseFields(
        fieldWithPath("content")
                .description("List of products on the current page"),
        fieldWithPath("content[].id")
                .description("Product ID"),
        fieldWithPath("content[].name")
                .description("Product name"),
        fieldWithPath("content[].category")
                .description("Category code"),
        fieldWithPath("content[].price")
                .description("Product price"),
        fieldWithPath("content[].currency")
                .description("Currency code"),
        fieldWithPath("content[].active")
                .description("Whether the product is active"),
        fieldWithPath("page").description("Current page number"),
        fieldWithPath("size").description("Page size"),
        fieldWithPath("totalElements").description("Total number of results"),
        fieldWithPath("totalPages").description("Total number of pages"),
        fieldWithPath("first").description("Whether this is the first page"),
        fieldWithPath("last").description("Whether this is the last page"))
~~~

If the actual response does not contain a field, do not add a fake descriptor. If there is additional metadata such as `numberOfElements` or `empty`, document it according to the actual JSON.

## 8. Documentation Test for Search with Filters and Pagination

Example test combining `queryParameters` and `responseFields`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductSearchDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void searchProductsWithFiltersAndPagination() throws Exception {
        mockMvc.perform(get("/api/products")
                        .queryParam("q", "keyboard")
                        .queryParam("category", "accessories")
                        .queryParam("minPrice", "100000")
                        .queryParam("maxPrice", "2000000")
                        .queryParam("page", "0")
                        .queryParam("size", "20")
                        .queryParam("sort", "price,asc")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(0))
                .andExpect(jsonPath("$.size").value(20))
                .andExpect(jsonPath("$.content").isArray())
                .andDo(document("products-search",
                        queryParameters(
                                parameterWithName("q").description(
                                        "Keyword to search in name and description").optional(),
                                parameterWithName("category").description(
                                        "Category code to filter by").optional(),
                                parameterWithName("minPrice").description(
                                        "Minimum price").optional(),
                                parameterWithName("maxPrice").description(
                                        "Maximum price").optional(),
                                parameterWithName("page").description(
                                        "Page number, zero-based; defaults to 0"),
                                parameterWithName("size").description(
                                        "Number of items per page; defaults to 20"),
                                parameterWithName("sort").description(
                                        "Field and sort direction; defaults to createdAt,desc")),
                        responseFields(
                                fieldWithPath("content").description("List of products"),
                                fieldWithPath("content[].id").description("Product ID"),
                                fieldWithPath("content[].name").description("Product name"),
                                fieldWithPath("content[].category").description("Category code"),
                                fieldWithPath("content[].price").description("Product price"),
                                fieldWithPath("content[].currency").description("Currency code"),
                                fieldWithPath("content[].active").description("Active status"),
                                fieldWithPath("page").description("Current page number"),
                                fieldWithPath("size").description("Page size"),
                                fieldWithPath("totalElements").description("Total number of results"),
                                fieldWithPath("totalPages").description("Total number of pages"),
                                fieldWithPath("first").description("Whether this is the first page"),
                                fieldWithPath("last").description("Whether this is the last page"))));
    }
}
~~~

This test needs fixture/service test data that guarantees a stable response. Status and JSONPath assertions verify behavior; descriptors verify that the query contract and response structure are documented.

## 9. Verifying Default Pagination

A separate test should omit `page` and `size` to confirm defaults:

~~~java
@Test
void searchUsesDefaultPageAndSize() throws Exception {
    mockMvc.perform(get("/api/products")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(0))
            .andExpect(jsonPath("$.size").value(20));
}
~~~

This test does not necessarily have to generate new snippets if the goal is solely checking defaults. If you want to include a request example without passing `page`/`size` in the documentation, create a separate operation identifier and document the query parameters with their proper optional status.

## 10. Checking Limits and Edge Cases

A pagination API should clearly specify:

- Whether `page` starts at 0 or 1.
- Minimum and maximum `size`.
- Whether `page` exceeding total pages returns an empty page or an error.
- Which fields `sort` accepts.
- Whether valid sort directions are `asc`, `desc`, or both.
- Whether `minPrice` is allowed to be greater than `maxPrice`.
- How empty `content` and `totalElements` equal to 0 behave when there are no results.

Suggested test table:

| Case | Request | Expectation to verify |
| --- | --- | --- |
| Default | Omit `page`/`size` | `page=0`, `size=20` |
| Next page | `page=1`, `size=10` | Returns elements of page 1 |
| Maximum size | `size=100` | Accepted if the limit is 100 |
| Size exceeds limit | `size=5000` | Clamped or returns an error per contract |
| Negative page | `page=-1` | Returns validation error per contract |
| No results | `q=unknown-value` | Empty `content`, consistent metadata |
| Invalid price range | `minPrice` greater than `maxPrice` | Returns validation error if defined by the API |
| Unsupported sort | `sort=secretField,asc` | Rejected or uses published fallback |

Do not document assumed behavior. Every rule needs to be verified by tests and actual responses before describing it.

## 11. Documenting Error Responses

If a query is invalid, the API may return `400 Bad Request` with an error payload. Example:

~~~json
{
  "code": "INVALID_PAGE_SIZE",
  "message": "size must be between 1 and 100",
  "field": "size"
}
~~~

An error documentation test can use its own identifier:

~~~java
@Test
void searchRejectsInvalidPageSize() throws Exception {
    mockMvc.perform(get("/api/products")
                    .queryParam("size", "5000")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isBadRequest())
            .andDo(document("products-search-invalid-size",
                    queryParameters(
                            parameterWithName("size")
                                    .description("Number of items per page")),
                    responseFields(
                            fieldWithPath("code").description("Error code"),
                            fieldWithPath("message").description("Error message"),
                            fieldWithPath("field").description("Invalid parameter"))));
}
~~~

The error payload and status must match the application's exception handler. If errors return Problem Details per RFC 9457 or another structure, document that exact structure instead of using the example JSON above.

## 12. Assembling Snippets into AsciiDoc

Create the search section in `api-guide.adoc`:

~~~adoc
== Search Products

=== Request

include::{snippets}/products-search/http-request.adoc[]
include::{snippets}/products-search/query-parameters.adoc[]

=== Response

include::{snippets}/products-search/http-response.adoc[]
include::{snippets}/products-search/response-fields.adoc[]

=== Error: Invalid Page Size

include::{snippets}/products-search-invalid-size/http-request.adoc[]
include::{snippets}/products-search-invalid-size/query-parameters.adoc[]
include::{snippets}/products-search-invalid-size/http-response.adoc[]
include::{snippets}/products-search-invalid-size/response-fields.adoc[]
~~~

The identifier in `include` must match `document(...)` exactly. Only include files that are actually generated; if an operation does not produce `request-fields` or `response-fields`, do not add an include for that snippet.

## 13. Running the Build and Checking Snippets

Workflow:

~~~text
Clean generated snippets
          |
          v
Run MockMvc documentation tests
          |
          v
Verify query parameter assertions
          |
          v
Generate query and response snippets
          |
          v
Run Asciidoctor
          |
          v
Inspect HTML and includes
~~~

With Gradle:

~~~bash
./gradlew clean test
./gradlew asciidoctor
~~~

Or run `clean asciidoctor` if the task already declares `dependsOn test`:

~~~bash
./gradlew clean asciidoctor
~~~

Check that `build/generated-snippets/products-search` contains `query-parameters.adoc` and `response-fields.adoc`. Read their contents to verify parameter names, descriptions, column order, and field paths match the current response. Check that the final HTML has no missing includes.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Query parameter does not appear | Test did not send the parameter or descriptor has the wrong name | Compare the actual URL with `parameterWithName` |
| Optional parameter reported as missing | Not marked `optional` per the contract | Use `optional()` when the API allows omission |
| Response field path mismatch | API returns an array or different envelope than assumed | Inspect the actual JSON after serialization |
| Documented default is wrong | Only described in text without testing default behavior | Add a test without passing the parameter |
| Inconsistent pagination metadata | Test data or service returns unstable totals | Use fixed fixtures and assert metadata |
| Arbitrary sort field poses a risk | API does not whitelist sort properties | Validate and publish the list of supported fields |
| Empty results cause descriptor failure | Empty `content` was not tested | Add an operation or assertion for empty results |
| Asciidoctor missing snippet | Task runs before documentation tests or wrong identifier | Declare task dependency and synchronize includes |

## 15. Capstone Exercise

Complete the Product search documentation:

1. Document query parameters `q`, `category`, `minPrice`, and `maxPrice`.
2. Document `page`, `size`, and `sort`, including defaults and limits.
3. Document the response envelope with `content`, `page`, `size`, `totalElements`, and `totalPages`.
4. Write a test verifying default pagination when `page`/`size` are omitted.
5. Write tests for the next page and the empty-results case.
6. Write error tests for `size` exceeding the limit and invalid `sort`.
7. Include request, query parameter, response, and error snippets in AsciiDoc.
8. Run a clean build and verify the HTML.

**Completion criteria:** query descriptors reflect the actual URL; optional/default behavior is accurately documented; response fields cover the envelope and items; pagination/sort limits are tested; snippets and HTML are generated from the current run.

## 16. Checklist Before Adding to CI

- [ ] Query parameter names match the controller and actual requests.
- [ ] Parameters are marked `optional` only when the API allows omitting them.
- [ ] Default `page`/`size`/`sort` are verified by tests.
- [ ] `page`/`size` limits and `sort` rules are published.
- [ ] Response fields fully describe the envelope and items.
- [ ] Empty results and invalid queries have appropriate tests.
- [ ] Test data is stable and does not depend on external services.
- [ ] Documentation tests run before Asciidoctor.
- [ ] Includes point to the exact operation identifiers and existing snippets.
- [ ] CI archives the HTML artifact built from fresh snippets.

**Remember:** Search API documentation must describe both the query contract and the pagination response. Combining MockMvc assertions, query parameter descriptors, and response field descriptors helps consumers understand filtering, sorting, and pagination while helping CI detect when defaults or result structures change.
