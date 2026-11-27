# URI, Query String, and Headers in Requests

## 1. Objectives and Context

In Spring REST Docs **HTTP operations**, a request does not just contain a `GET`/`POST` method and a body—it also includes a **URI**, **query string**, and **HTTP request headers**. These three sources of information determine the resource being accessed, filtering/pagination parameters, and how the client communicates with the API.

This lesson belongs to the `SPRING_REST_DOCS` module, aiming to produce **verifiable REST API documentation from HTTP tests** using MockMvc, WebTestClient, or REST Assured. From tested requests and responses, Spring REST Docs generates snippets describing payloads, parameters, and headers, which are then incorporated into Asciidoctor documentation or Markdown, build, and CI workflows.

After this lesson, you will be able to:

- Break down a URI into scheme, host, port, path, and query; explain why **fragments are not sent to the server**.
- Distinguish path variables, query parameters, HTTP headers, and form parameters.
- Generate `path-parameters.adoc`, `query-parameters.adoc`, and `request-headers.adoc` snippets in a MockMvc test.
- Understand when required, `optional()`, `ignored()`, or `relaxed...` descriptors are appropriate.
- Replay requests with `curl`/HTTPie and recognize differences caused by URL encoding, default headers, and test environments.
- Build documentation reproducible from tests and catch drift in CI.

## 2. Analyzing a Request URI

Consider a call to read book reviews:

~~~http
GET /api/books/42/reviews?page=0&size=10&sort=createdAt%2Cdesc HTTP/1.1
Host: api.example.com
Accept: application/json
X-Request-Id: docs-001
~~~

With a full URL, one breakdown is:

~~~text
https://api.example.com:443/api/books/42/reviews?page=0&size=10&sort=createdAt%2Cdesc
|___|   |_____________| |__| |___________________| |_________________________________|
scheme         host       port          path                        query
~~~

| Component | Example | Meaning |
| --- | --- | --- |
| Scheme | `https` | Protocol used to access the resource; HTTPS combines HTTP with TLS. |
| Host | `api.example.com` | Server or domain name receiving the request. |
| Port | `443` | Typical port for HTTPS; if it is the default port, the displayed URL may omit it. |
| Path | `/api/books/42/reviews` | Path to the collection of reviews for book `42`. |
| Path variable | `42` in `/api/books/{bookId}/reviews` | Concrete value substituted into the route template. |
| Query string | `page=0&size=10&sort=createdAt%2Cdesc` | Query parameters following `?`. |
| Fragment | E.g. `#example` | Handled by the client; **not** part of the request target sent to the HTTP server. |

**A URI can have multiple representations**: test code typically uses a relative path (`/api/books/...`); HTTP request snippets display the request target and headers; `curl-request`/`httpie-request` snippets may use an absolute URL. All three representations can describe **the same operation**.

### 2.1. URL, URI, and URI Template

In API guides, distinguish among:

- **Actual URI:** `/api/books/42/reviews` is the concrete path sent by the client.
- **URI template:** `/api/books/{bookId}/reviews` describes an endpoint accepting a path parameter.
- **URL with query:** `/api/books/42/reviews?page=0&size=10` states concrete query conditions.
- **Route/controller mapping:** e.g. `@GetMapping("/api/books/{bookId}/reviews")` defines the endpoint accepted by the application.

Spring REST Docs generates snippets from **the request executed in the test**, rather than inferring the entire URI contract from controller annotations. When generating a path parameter table, the request builder must preserve **variable names from the URI template**.

### 2.2. How Paths Differ from Queries

A common REST API convention:

| Purpose | Example | Where to place it |
| --- | --- | --- |
| Access a specific resource | `/api/books/42` | Path variable `bookId` |
| Access a sub-resource collection | `/api/books/42/reviews` | Path |
| Paginate results | `?page=0&size=10` | Query |
| Sort results | `?sort=createdAt,desc` | Query |
| Filter by attribute | `?rating=5` | Query |
| Send creation/update data | JSON in request body | Body, rather than stuffing into query |
| Specify representation format | `Accept: application/json` | Request header |
| Send authentication credentials | `Authorization: Bearer ...` | Request header, per the API auth scheme |

These are useful design conventions, not rigid laws forcing every API to place parameters identically. Whichever design you choose, documentation must describe **the endpoint's actual contract**.

## 3. Query Strings: Syntax, Encoding, and Repeated Parameters

The query string follows `?` and typically consists of `name=value` pairs separated by `&`:

~~~text
/api/books?page=0&size=10&tag=java&tag=spring
~~~

Here:

- `page` has value `0`.
- `size` has value `10`.
- `tag` appears twice, which the API may interpret as a list `["java", "spring"]` per its contract.
- Parameter order in a query string is generally not treated as having business meaning, unless an endpoint specifies otherwise.

### 3.1. Cases to Document Clearly

| Case | Example | What to clarify in the contract |
| --- | --- | --- |
| Required parameter | `size=10` | What happens if `size` is omitted? |
| Optional parameter | `sort=createdAt,desc` | What is the default sort order if omitted? |
| Repeated parameter | `tag=java&tag=spring` | Combined into multiple values or only one accepted? |
| Valueless parameter | `debug` or `debug=` | Does the API distinguish "absent", "empty", and "present without value"? |
| Type and range | `page=0`, `size=10` | Is indexing 0-based or 1-based? What is the max limit for `size`? |
| Case sensitivity | `sort` vs. `Sort` | Is parameter matching case-sensitive? |
| Special characters | `q=Spring%20REST%20Docs` | How do URL encoding and server decoding behave? |

Parameter names and values should be URL-encoded according to URI rules, especially when containing spaces, `&`, `=`, or Unicode characters. `%20` encodes a space in URIs; under `application/x-www-form-urlencoded` form rules, `+` is typically interpreted as a space. Do not assume every API treats `+` and `%20` identically in every context.

**Distinguish actual values from displayed examples:** in tests, `queryParam("sort", "createdAt,desc")` expresses the value processed by the API client; the URL representation may be `createdAt,desc` or an equivalent percent-encoded form. Inspect the generated `http-request.adoc` when you need an exact comparison.

### 3.2. Avoid Putting Secrets in Query Strings

Query strings easily appear in browser history, access logs, reverse proxies, monitoring tools, and caching layers. Therefore, never put passwords, access tokens, or sensitive personal data in query strings. Use proper authentication and authorization mechanisms; in documentation tests, use only dummy data.

## 4. What Are Request Headers?

Headers are metadata fields accompanying an HTTP request. Illustrative syntax:

~~~http
GET /api/books/42/reviews?page=0 HTTP/1.1
Host: api.example.com
Accept: application/json
Authorization: Bearer <example-token>
X-Request-Id: docs-001
If-None-Match: "v1"
~~~

| Header | Common meaning | When documenting |
| --- | --- | --- |
| `Host` | Authority targeted by an HTTP/1.1 request | Usually set by the HTTP client; do not confuse with path variables. |
| `Accept` | Response media type preferred by the client | E.g., `application/json`. |
| `Content-Type` | Media type of the **request body** | E.g., `application/json` when sending JSON; not normally needed on a bodyless GET. |
| `Authorization` | Credentials per the authentication scheme | Explain usage only; never include real tokens. |
| `X-Request-Id` | Example custom/observability header for correlating logs | May be a custom header; not automatically part of standard HTTP. |
| `If-None-Match` | ETag-based condition for conditional requests | If the contract supports conditional caching, test the `304` branch. |
| `If-Match` | ETag-based precondition for updates | Can pair with `PUT`/`PATCH` for optimistic concurrency control. |
| `Idempotency-Key` | Defined by some APIs to guard against re-executing side-effecting calls | Use only if the endpoint actually supports it; document key scope and TTL. |

HTTP header field names are generally **case-insensitive** per protocol semantics—for instance, `Accept` and `accept` are the same header name—though each header's value must follow its own syntax and rules. Some headers permit multiple values or multiple equivalent header lines, though not all headers can be safely comma-joined (e.g., `Set-Cookie`).

### 4.1. `Accept` vs. `Content-Type`

- `Accept: application/json`: the client wants to **receive the response** in JSON format.
- `Content-Type: application/json`: the **request body being sent** is JSON.

A `GET` request without a body normally only needs `Accept` if content negotiation is needed. A JSON `POST` request may need both. Do not add `Content-Type` to every GET just to make commands in docs look "complete".

### 4.2. Headers Set by Tests vs. Headers Added by HTTP Clients

MockMvc runs in a mocked Servlet environment, WebTestClient can bind to an application or server, and REST Assured can call a real server over the network. As a result, default headers like `Host`, `User-Agent`, `Content-Length`, and encoding headers can differ. Headers appearing in snippets should be viewed as **observed output of a specific client and test configuration**, not a promise that every client sends the exact same headers.

## 5. Distinguishing Path, Query, Header, and Form/Body

Choosing the right descriptor matters because Spring REST Docs provides distinct APIs:

| Information location | Example request | Descriptor | Generated snippet |
| --- | --- | --- | --- |
| Path variable | `/api/books/42` with `/api/books/{bookId}` | `pathParameters(parameterWithName("bookId")...)` | `path-parameters.adoc` |
| Query parameter | `?page=0&size=10` | `queryParameters(parameterWithName("page")...)` | `query-parameters.adoc` |
| Request header | `Accept: application/json` | `requestHeaders(headerWithName("Accept")...)` | `request-headers.adoc` |
| Form field | Body `application/x-www-form-urlencoded` | `formParameters(parameterWithName("name")...)` | `form-parameters.adoc` |
| JSON body field | Body `{"name":"Lan"}` | `requestFields(fieldWithPath("name")...)` | `request-fields.adoc` |

**Do not use `queryParameters` for a JSON body**, and do not use `requestFields` for `?page=0`. A parameter appearing in the query string is distinct from a JSON field, even if both share the name `page`.

### Query Parameters vs. Form Parameters

Example request creating/searching via a form:

~~~http
POST /api/books/search HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=Spring
~~~

`title` is a **form parameter in the request body**, not a query parameter on the URL. In MockMvc, `param(...)` can be used to supply form parameters; to record query parameters explicitly, use `queryParam(...)` or put parameters directly in the URI. Spring REST Docs documentation recommends avoiding `param(...)` for query parameters because parameter placement becomes ambiguous.

## 6. MockMvc Test: URI, Query, and Headers in One Operation

### 6.1. Assumptions and Dependencies

This example uses **Spring Boot 3.x, Spring MVC, JUnit 5, and Java 17+**. The project needs the test starter and the Spring REST Docs MockMvc module:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Assume the application already implements:

~~~text
GET /api/books/{bookId}/reviews
~~~

Illustrative contract: book `42` has test data, the endpoint accepts three query parameters (`page`, `size`, `sort`) and header `X-Request-Id`, and returns `200 OK` with a JSON-compatible `Content-Type`. The values and status are **assumed for this lesson**; Spring REST Docs does not create endpoints or fixtures on its own.

### 6.2. A Self-Contained Test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
class BookReviewDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentListBookReviews() throws Exception {
        mockMvc.perform(get("/api/books/{bookId}/reviews", 42)
                .queryParam("page", "0")
                .queryParam("size", "10")
                .queryParam("sort", "createdAt,desc")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "docs-001"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andDo(document("book-reviews-list",
                pathParameters(
                    parameterWithName("bookId")
                        .description("ID of the book whose reviews to fetch")
                ),
                queryParameters(
                    parameterWithName("page")
                        .description("Page to retrieve, starting from 0"),
                    parameterWithName("size")
                        .description("Maximum number of reviews per page"),
                    parameterWithName("sort")
                        .description("Sort order, e.g., createdAt,desc")
                ),
                requestHeaders(
                    headerWithName(HttpHeaders.ACCEPT)
                        .description("Desired media type of the response"),
                    headerWithName("X-Request-Id")
                        .description("Client request tracking ID")
                )
            ));
    }
}
~~~

In this test class:

1. `RestDocumentationRequestBuilders.get("/api/books/{bookId}/reviews", 42)` records the URI template with variable `bookId`. Choosing this builder also works on projects using Spring Framework 6.1 or earlier, where `MockMvcRequestBuilders` does not supply sufficient path parameter metadata to REST Docs.
2. `queryParam(...)` builds an explicit query string. Parameters declared in `queryParameters(...)` can be verified against the actual query.
3. `accept(...)` and `header(...)` set request headers received by the API.
4. `andExpect(...)` verifies results before reaching `document(...)`.
5. `document("book-reviews-list", ...)` generates both default snippets and **three description tables for path, query, and headers** from the descriptors.
6. `@AutoConfigureRestDocs` chooses the URI displayed in documentation. Host `api.example.com` is illustrative, not a server started by MockMvc.

**Test note:** the example only asserts status and Content-Type; in real projects, add assertions for response body structure, sorting, and pagination matching the contract. Request descriptors verify **metadata presence** per REST Docs rules, not the application's pagination/sorting algorithm itself.

## 7. Generated Snippets and How to Read Them

After the test passes, you may see:

~~~text
build/generated-snippets/
└── book-reviews-list/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── path-parameters.adoc
    ├── query-parameters.adoc
    └── request-headers.adoc
~~~

The first six files are common default snippets. The last three come from declaring `pathParameters`, `queryParameters`, and `requestHeaders`. The exact file list can vary when a project customizes default snippets or templates.

### 7.1. `http-request.adoc`: The Actual Request

An **illustrative** output might be:

~~~http
GET /api/books/42/reviews?page=0&size=10&sort=createdAt%2Cdesc HTTP/1.1
Accept: application/json
X-Request-Id: docs-001
Host: api.example.com
~~~

Comma percent-encoding, header ordering, and the appearance of `Host` depend on how the client builds the request and the template. Do not rely on this example to assert byte-for-byte equality of the generated file. Open `http-request.adoc` itself after running tests.

### 7.2. `path-parameters.adoc`

The tabular snippet may have content equivalent to:

| Parameter | Description |
| --- | --- |
| `bookId` | ID of the book whose reviews to fetch. |

This table **documents variable names** from the URI template. It does not replace `bookId` with `42` in the name column; `42` is the concrete value used in the sample request.

### 7.3. `query-parameters.adoc`

| Parameter | Description |
| --- | --- |
| `page` | Page to retrieve, starting from 0. |
| `size` | Maximum number of reviews per page. |
| `sort` | Sort order, e.g., `createdAt,desc`. |

To make documentation complete and usable, also state defaults, upper/lower bounds, allowed values, repeated-parameter handling, and error statuses for invalid parameters. REST Docs only checks descriptors against the test request; it does not infer those business constraints automatically.

### 7.4. `request-headers.adoc`

| Header | Description |
| --- | --- |
| `Accept` | Desired media type of the response. |
| `X-Request-Id` | Client request tracking ID. |

`requestHeaders(...)` checks that **declared, non-optional headers** are present in the request. It **does not require every other header to be listed as well**. This differs from default validation on `queryParameters(...)` and `pathParameters(...)`, which can fail when encountering an undocumented parameter.

## 8. Descriptor Validation: Strict, Optional, Ignored, Relaxed

This is a common point of confusion when bringing REST Docs into CI.

### 8.1. Path and Query Parameters: Bidirectional Validation

With `pathParameters(...)` or `queryParameters(...)` in normal mode:

- A parameter **appears in the request** without a matching descriptor → snippet generation can fail.
- A **required** parameter descriptor exists, but the parameter is absent → snippet generation fails.
- A descriptor with `.optional()` is allowed to be absent from the request.
- A descriptor with `.ignored()` is omitted from the snippet, yet REST Docs still knows that parameter was accounted for/allowed to be excluded from the table.
- `relaxedPathParameters(...)` or `relaxedQueryParameters(...)` ignores undocumented parameters; required declared descriptors must still be satisfied.

Example of an optional `language` query parameter:

~~~java
queryParameters(
    parameterWithName("page")
        .description("Page starting from 0"),
    parameterWithName("language")
        .description("Language code to filter reviews, e.g., vi")
        .optional()
)
~~~

If the test only sends `page`, the `language` descriptor remains valid because it is marked optional. When documenting a specific branch and wanting to omit a system parameter like `trace`, you can use `ignored()`; consider whether hiding that parameter deprives readers of needed knowledge.

### 8.2. Request Headers: Checking Declared Descriptors

With `requestHeaders(...)`:

- A non-optional header descriptor **missing from the request** → snippet generation error.
- An optional header may be absent.
- Extra undocumented headers **do not fail the test by default**; therefore, never assume a request contains only the headers listed.

Example documenting an optional header:

~~~java
requestHeaders(
    headerWithName(HttpHeaders.ACCEPT)
        .description("Response media type"),
    headerWithName("X-Request-Id")
        .description("Request tracking ID")
        .optional()
)
~~~

This is useful for APIs where clients may omit `X-Request-Id`. Clearly state who generates a default correlation ID and when the header is used for log lookup.

### 8.3. Descriptors Do Not Validate Business Values

A descriptor like:

~~~java
parameterWithName("size").description("Number of items from 1 to 100")
~~~

does not prove the server rejects `size=1000`. To verify the contract, **add separate HTTP tests** for valid and invalid boundaries and assert the corresponding status/body/error code. The same applies to headers: documenting `Accept` as `application/json` does not replace a test returning `406 Not Acceptable` when a client requests an unsupported media type.

Diagram:

~~~mermaid
flowchart TD
    A["Test builds request URI/query/headers"] --> B["Application returns response"]
    B --> C{"Status/body assertions pass?"}
    C -->|No| D["Test fails"]
    C -->|Yes| E["Spring REST Docs processes descriptors"]
    E --> F{"Descriptors valid?"}
    F -->|No| D
    F -->|Yes| G["Generate snippets"]
    G --> H["Asciidoctor/CI builds docs"]
~~~

This is the sequence in the MockMvc example when `andExpect(...)` precedes `andDo(document(...))`. With REST Assured, the recording filter can run before the final assertion; only publish when **the entire test suite passes**.

## 9. Practical Pitfalls with `queryParam`, `param`, and Form Bodies

### 9.1. Clear Ways to Build Queries in MockMvc

Use one of these two approaches.

**Option A: write the query directly in the URI**:

~~~java
mockMvc.perform(get("/api/books/42/reviews?page=0&size=10"));
~~~

**Option B: use the request builder**:

~~~java
mockMvc.perform(get("/api/books/42/reviews")
    .queryParam("page", "0")
    .queryParam("size", "10"));
~~~

In modern code, `queryParam` or `queryParams` lets Spring REST Docs identify the source as the **query string**. Avoid using `param("page", "0")` for queries when it is ambiguous whether a parameter is a query or form parameter; doing so can prevent docs from matching the expected request line.

### 9.2. Form Data Lives in the Body

Suppose an illustrative endpoint accepts `application/x-www-form-urlencoded`:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// Place this method inside a class already configured with MockMvc and REST Docs:
@Test
void documentFormSearch() throws Exception {
    mockMvc.perform(post("/api/books/search")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("title", "Spring"))
        .andExpect(status().isOk())
        .andDo(document("books-form-search",
            formParameters(
                parameterWithName("title")
                    .description("Book title to search for")
            )
        ));
}
~~~

The resulting `form-parameters.adoc` describes the `title` field in the form body. `query-parameters.adoc` would not be the right snippet here. Note that the illustrative endpoint naming may not reflect ideal REST design; the goal here is to show **the difference in data placement**.

### 9.3. A JSON Body Is a Different Category

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Spring in Action"}
~~~

For this request, use `requestFields(fieldWithPath("title")...)` to document the JSON field, not `formParameters(...)` or `queryParameters(...)`.

## 10. Headers and Content Negotiation: Dedicated Examples

Suppose the API supports JSON responses. A test explicitly indicates the client wants JSON:

~~~java
mockMvc.perform(get("/api/books/42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andDo(document("books-get-json",
        requestHeaders(
            headerWithName(HttpHeaders.ACCEPT)
                .description("Response media type accepted by the client")
        )
    ));
~~~

Place this inside a class already configured with REST Docs. `Accept` is only a request header; the actual JSON content belongs to the response and must be asserted separately, e.g., via `jsonPath` or `responseFields`.

Similarly, when sending a `POST` with a JSON body, verify:

~~~java
mockMvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Spring in Action\"}"))
    .andExpect(status().isCreated())
    .andDo(document("books-create-json",
        requestHeaders(
            headerWithName(HttpHeaders.CONTENT_TYPE)
                .description("Media type of the request body"),
            headerWithName(HttpHeaders.ACCEPT)
                .description("Desired response media type")
        )
    ));
~~~

This is an example for **a hypothetical endpoint returning `201`**; a complete test requires preparing fixtures/controllers and adding necessary assertions for `Location` or response body per your project's contract.

## 11. Sanitizing URIs and Headers Before Putting Them in Docs

Snippets can inadvertently expose internal hostnames, cookies, tokens, or personal identifiers. Tests and documentation should intentionally use dummy data.

### 11.1. Standardizing Hostname and Port

When using MockMvc with Spring Boot 3.x, you can configure:

~~~java
@AutoConfigureRestDocs(
    outputDir = "build/generated-snippets",
    uriScheme = "https",
    uriHost = "api.example.com",
    uriPort = 443
)
~~~

This host and port only affect how Spring REST Docs **renders URIs** in snippets; it does not create a live HTTP server at `api.example.com`. To replay with `curl` or HTTPie, substitute an accessible real environment URL.

With WebTestClient bound to an application, you can configure the base URL on the builder used for documentation. With clients calling a real server, REST Docs also offers the `modifyUris()` request preprocessor to standardize host, scheme, and port in the recorded snippet output.

### 11.2. Replacing Secret Values with Placeholders

If an `Authorization` header is genuinely sent by the test and needs to remain in documentation, you can **replace its value in snippets only**:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

// Replace the .andDo(document(...)) call in a test that sends Authorization:
.andDo(document("secured-books-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <redacted>")
    ),
    requestHeaders(
        headerWithName(HttpHeaders.AUTHORIZATION)
            .description("Access token of the authenticated user")
    )
));
~~~

When running the test, the actual request still uses credentials/fixtures per test configuration; the preprocessor only cleans **the record used to generate documentation**. This snippet assumes the test sends `Authorization`, and the identifier is illustrative. It is a **replacement call**, not appended to a test that already has `document("secured-books-get", ...)`.

If you want to omit the header completely, use `modifyHeaders().remove("Authorization")`, though in that case do not declare `headerWithName("Authorization")` as required in `requestHeaders(...)` because it has been removed from the snippet record. Clearly explain authentication requirements outside the sample command so readers understand why replaying as-is may return `401`.

### 11.3. What URI/Header Preprocessing Should Not Be Used For

- Do not make a query string containing a real password "safe" merely by masking part of it on the doc page; **keep secrets out of fixtures from the start**.
- Do not claim a tested URL is reachable from the Internet simply because snippets display a public host.
- Do not edit a header value in a snippet and treat it as proof that the system processed the edited value.
- Do not use preprocessors to hide behavioral bugs; rely on test assertions before generating documentation.

## 12. WebTestClient and REST Assured

The same path/query/header contract can be tested with other clients. The difference lies in how requests are built and how the snippet-generating filter or consumer is attached.

### 12.1. WebTestClient

Assuming `webTestClient` is configured with Spring REST Docs integration and the GET endpoint returns `200`:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/books/{bookId}/reviews?page=0&size=10", 42)
    .accept(MediaType.APPLICATION_JSON)
    .header("X-Request-Id", "docs-001")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("book-reviews-webtestclient",
        pathParameters(
            parameterWithName("bookId").description("Book ID")
        ),
        queryParameters(
            parameterWithName("page").description("Page index"),
            parameterWithName("size").description("Items per page")
        ),
        requestHeaders(
            headerWithName("X-Request-Id")
                .description("Request tracking ID")
        )
    ));
~~~

The URI template is retained by WebTestClient so `pathParameters(...)` can describe `bookId`. Use the `spring-restdocs-webtestclient` module and configure REST Docs for your Spring version.

### 12.2. REST Assured

With REST Assured, requests are typically sent to a real HTTP server. An illustrative example using a `RequestSpecification` configured with REST Docs:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

// spec: RequestSpecification configured with the test server and REST Docs.
given(spec)
    .filter(document("book-reviews-restassured",
        queryParameters(
            parameterWithName("page").description("Page index")
        ),
        requestHeaders(
            headerWithName("X-Request-Id")
                .description("Request tracking ID")
        )
    ))
    .queryParam("page", "0")
    .header("X-Request-Id", "docs-001")
.when()
    .get("/api/books/42/reviews")
.then()
    .statusCode(200);
~~~

The integration module is `spring-restdocs-restassured`, and the filter/documentation context must be configured per your project version. In this example, the URI already contains the **concrete value `42`**, so only query/header descriptors are declared; do not assume the filter automatically knows the `bookId` URI template name as in the two URI-template-aware clients above.

The filter may record the operation when the request executes, before the `statusCode(200)` assertion runs. Therefore, CI must require **tests to PASS** before publishing snippets.

### 12.3. Comparison

| Tool | Building URI and query | Building headers | Generating snippets |
| --- | --- | --- | --- |
| MockMvc | `get("/path/{id}", id).queryParam(...)` | `accept(...)`, `header(...)` | `.andDo(document(...))` |
| WebTestClient | `.uri("/path/{id}?page=0", id)` | `.accept(...)`, `.header(...)` | `.expectBody().consumeWith(document(...))` |
| REST Assured | `.get("/path")` combined with `.queryParam(...)` | `.header(...)`, `.accept(...)` | Filter `document(...)` |

## 13. Authoring Documentation from Snippets

In an Asciidoctor file, you can combine raw requests, URI/query/header tables, and responses:

~~~asciidoc
= Books API

== List Reviews of a Book

=== HTTP request
include::{snippets}/book-reviews-list/http-request.adoc[]

=== Path parameters
include::{snippets}/book-reviews-list/path-parameters.adoc[]

=== Query parameters
include::{snippets}/book-reviews-list/query-parameters.adoc[]

=== Request headers
include::{snippets}/book-reviews-list/request-headers.adoc[]

=== HTTP response
include::{snippets}/book-reviews-list/http-response.adoc[]

=== Try with curl
include::{snippets}/book-reviews-list/curl-request.adoc[]
~~~

The `snippets` attribute must be configured to point to the snippet output directory such as `build/generated-snippets`. This is an Asciidoctor example; if a project outputs Markdown docs, configure an appropriate template/conversion step because standard Markdown renderers do not natively understand `include::{snippets}/...[]`.

CI flow:

~~~mermaid
flowchart LR
    A["HTTP tests + assertions"] --> B["Generate snippets from operations"]
    B --> C["Asciidoctor includes snippets"]
    C --> D["Build HTML/PDF or doc artifact"]
    D --> E["Publish when pipeline PASSES"]
~~~

Configure the documentation build task to depend on the test task that generates snippets, and manage the output directory and include paths. If stale snippets remain even though their corresponding test was removed or skipped, the build could pull outdated content into documentation; ensure artifacts reflect **the current test run**.

## 14. Common Issues and How to Handle Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `path-parameters.adoc` is not generated | Missing `pathParameters(...)` or URI template metadata not preserved | Use an appropriate request builder and declare descriptors. |
| `pathParameters` reports missing `bookId` | Request built from hardcoded path instead of URI template | Use `RestDocumentationRequestBuilders.get("/.../{bookId}", 42)` in MockMvc. |
| `query-parameters.adoc` is empty or test fails | Used `param(...)`, leaving parameter placement ambiguous; query not actually in URI | Use `queryParam(...)` or a query string directly in the URI. |
| REST Docs reports an undocumented query parameter | Parameter present in request without descriptor in strict mode | Add accurate descriptor; use `relaxedQueryParameters` only intentionally. |
| Missing query descriptor still passes | Marked `optional()` or using relaxed mode | Check documentation intent; do not mark truly required parameters optional. |
| `request-headers.adoc` omits auto-generated headers | Only headers declared in descriptors get table rows | Add descriptors for headers important to the contract. |
| Header descriptor exists but header is absent | Test client did not send header or preprocessing removed it | Fix request builder/descriptor or preserve header when masking. |
| `Accept` is right but response is not JSON | Test only verified request header | Add response `Content-Type` and payload assertions. |
| URL with spaces/`&` produces wrong request | Missing percent-encoding or shell misinterprets special chars | Use URI builder/`queryParam`, or properly encode and quote URLs for the shell. |
| `curl-request` calls wrong host | Displayed URI uses sample host from MockMvc config | Use a real test server and explain how to substitute the URL. |
| Headers/tokens leaked in docs | Fixture contains secrets without masking | Use dummy data and proper preprocessing before generating snippets. |
| CI still publishes when tests fail | Pipeline uses stale snippets or lacks test dependency | Make docs build depend on tests and manage build artifacts. |

## 15. Hands-on Exercise

Document a hypothetical endpoint:

~~~text
GET /api/orders/{orderId}/events?type=PAYMENT&page=0&size=20
~~~

The client sends headers:

~~~http
Accept: application/json
X-Request-Id: exercise-001
~~~

Exercise requirements:

1. Write an HTTP test with URI template `{orderId}`, pass value `101`, queries `type`/`page`/`size`, and both headers above.
2. Assert status `200 OK`, JSON `Content-Type`, and at least one key response field per the hypothetical contract.
3. Generate `path-parameters.adoc` describing `orderId`, `query-parameters.adoc` describing the three query params, and `request-headers.adoc` describing `Accept` and `X-Request-Id`.
4. Add an optional query parameter `sort` using `.optional()`; run the test without sending `sort` and verify snippets still generate.
5. Intentionally send an undeclared query parameter, such as `debug=true`, to observe strict validation; then either add its descriptor or evaluate ignoring it.
6. Compare `http-request.adoc` and `curl-request.adoc` to see how the request target, host, and headers are presented.
7. Include snippets in Asciidoctor and confirm the pipeline publishes only after tests pass.

**Completion criteria:** accurately distinguish path/query/header/form/JSON, generate all three description tables, understand strict/optional/ignored rules, use URI templates properly, and maintain a documentation workflow backed by passing tests.

## Official References

- [Spring REST Docs — Path Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/path-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
