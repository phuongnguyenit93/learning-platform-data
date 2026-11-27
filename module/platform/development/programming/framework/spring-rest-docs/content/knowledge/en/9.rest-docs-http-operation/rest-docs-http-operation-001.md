# The `http-request` Snippet and HTTP Method Information

## 1. Objectives and Context

In Spring REST Docs, an **HTTP operation** is an HTTP exchange recorded when a test sends a request to an API and receives a response. From that operation, Spring REST Docs generates **snippets**: documentation fragments that can be included in an API guide using Asciidoctor or a separately configured Markdown workflow.

This lesson focuses on the `http-request.adoc` snippet: it presents the actual request executed by the test, specifically the **HTTP method** (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, etc.), path, query string, headers, and body. This is a core part of `SPRING_REST_DOCS`: generating verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, then incorporating those snippets into documentation and build/CI pipelines.

After this lesson, you will be able to:

- Read the first line of an HTTP request and explain the meaning of the HTTP method.
- Generate `http-request.adoc` using a MockMvc test with assertions.
- Distinguish `http-request` from snippets that describe individual fields, headers, or parameters.
- Include snippets in Asciidoctor documentation and detect when documentation no longer matches the API through test runs.

## 2. What Does `http-request` Show?

Consider a request represented in HTTP/1.1 format:

~~~http
POST /api/users HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-001

{"name":"Lan","email":"lan@example.com"}
~~~

This is an illustrative example; header order, `Host`, `Content-Length`, charset, and line endings may vary depending on the client, configuration, and preprocessors.

| Component | Example | Meaning |
| --- | --- | --- |
| HTTP method | `POST` | The action the client requests to perform on the resource. |
| Request target | `/api/users` | The path and, if present, query string to the resource. |
| HTTP version | `HTTP/1.1` | How the snippet represents the HTTP request; not a business field. |
| Request header | `Content-Type: application/json` | The format of the body being sent. |
| Request header | `Accept: application/json` | The response format desired by the client. |
| Request body | JSON containing `name`, `email` | The data sent to the endpoint. |

**Key takeaway:** the HTTP method in the snippet is taken from the **request sent by the test**, such as `post("/api/users")` or `get("/api/users")`. Spring REST Docs does not infer the method from the documentation section title, test method name, or `@PostMapping`. If the wrong method is used, the test typically receives an unexpected status (such as `405 Method Not Allowed`) and the assertion will fail.

The `http-request.adoc` snippet lets readers see the **complete request**. It does not automatically explain the business meaning of individual fields, enums, or validation rules; those should be written as prose and dedicated snippets.

> **Protocol note:** the `METHOD /path HTTP/1.1` line is a convenient text representation for reading documentation. HTTP/2 and HTTP/3 transmit methods/paths differently on the wire; do not treat the snippet format as proof that the production server only supports HTTP/1.1.

## 3. Understanding HTTP Methods Correctly

The same path can support multiple different operations; **method + path** together determine the type of request the API must handle.

| Method | Common meaning in REST APIs | Request body | HTTP characteristics to note |
| --- | --- | --- | --- |
| `GET` | Read one or more resources | Typically not used | Safe, idempotent |
| `HEAD` | Retrieve metadata/headers corresponding to a resource without a response body | Typically not used | Safe, idempotent |
| `POST` | Create a resource or perform an action | Typically present for create operations | Not idempotent by default |
| `PUT` | Create/replace the state of a resource at a specified URI | Typically present | Idempotent per HTTP semantics |
| `PATCH` | Apply a partial modification | Typically present | Not guaranteed idempotent; depends on design |
| `DELETE` | Request deletion of a resource | Typically not used | Idempotent per HTTP semantics |
| `OPTIONS` | Query communication options supported by the endpoint | Typically not used | Safe, idempotent |

*Safe* means the method is defined with read-only semantics from the client's perspective; *idempotent* means sending the same request multiple times has the same intended effect on server state as sending it once. Idempotent does **not** mean every response has the same status: for example, the first `DELETE` may return `204`, while subsequent ones return `404` depending on the API contract.

Clearly separate two pieces of information when writing documentation:

1. **Actual method**: appears right on the first line of `http-request` and must be executed by the test.
2. **Business rules**: for example, "`POST /api/users` creates a user and returns `201 Created` with `Location`", which should be written in prose and verified with appropriate assertions.

## 4. Generating Snippets with MockMvc

### 4.1. Preparing the Test

The example below follows a configuration style familiar to **Spring Boot 3.x, JUnit 5, Java 17+**. The project needs Spring MVC, Spring Boot Test, and the `spring-restdocs-mockmvc` test dependency. If using Spring Boot's BOM/dependency management, let the BOM manage compatible library versions.

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Assume the application already has a `POST /api/users` endpoint that accepts JSON and returns `201 Created` on successful creation. The `@AutoConfigureRestDocs` annotation integrates REST Docs with the auto-configured MockMvc in Spring Boot and specifies where snippets are written.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class UserApiDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentCreateUser() throws Exception {
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "req-001")
                .content("""
                    {"name":"Lan","email":"lan@example.com"}
                    """))
            .andExpect(status().isCreated())
            .andDo(document("users-create"));
    }
}
~~~

Execution flow:

~~~mermaid
flowchart LR
    A["MockMvc: POST /api/users"] --> B["Application processes request"]
    B --> C["Verify status 201"]
    C --> D["document('users-create')"]
    D --> E["generated-snippets/users-create/http-request.adoc"]
~~~

- `post("/api/users")` determines the HTTP method and request target recorded.
- `contentType(...)`, `accept(...)`, `header(...)`, and `content(...)` provide the actual request data.
- `andExpect(status().isCreated())` verifies behavior before documentation is generated in this chain.
- `document("users-create")` specifies the **identifier** used to group the operation's snippets. The identifier should be stable and have business meaning.

After running the test successfully, the configured output location may contain:

~~~text
build/generated-snippets/
└── users-create/
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    └── response-body.adoc
~~~

These are the **six default snippets** in a typical Spring REST Docs configuration. If you change the default snippet list, template format, or output directory, the actual files may differ.

### 4.2. Reading the Resulting `http-request.adoc`

For the test above, the HTTP request content **may** look like:

~~~http
POST /api/users HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-001
Host: localhost:8080

{"name":"Lan","email":"lan@example.com"}
~~~

The `POST` method is the most important piece of information in this example: it describes the user creation operation. The `Host` header and environment-dependent values are purely illustrative. When you need to know the exact current configuration output, **open the snippet just generated by the test**.

Quick comparison of related snippets:

| Snippet | What question does it answer? |
| --- | --- |
| `http-request.adoc` | What complete HTTP request did the client send? |
| `http-response.adoc` | What status, headers, and response body did the server return? |
| `curl-request.adoc` | What `curl` command can replay the operation? |
| `httpie-request.adoc` | What HTTPie command can replay the operation? |
| `request-body.adoc` | What is the request body, separate from the method and headers? |
| `response-body.adoc` | What is the response body? |

## 5. Changing the HTTP Method and Recording Query Parameters

Suppose the API also has `GET /api/users?page=0&size=10` that returns a list. We write a separate test using a different identifier:

~~~java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void documentListUsers() throws Exception {
    mockMvc.perform(get("/api/users")
            .queryParam("page", "0")
            .queryParam("size", "10")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("users-list",
            queryParameters(
                parameterWithName("page").description("Page index, starting from 0"),
                parameterWithName("size").description("Number of items per page")
            )));
}
~~~

This snippet is placed inside the same test class configured in the previous section; the imports only illustrate the additions needed.

The `users-list/http-request.adoc` snippet will show the corresponding request line, for example:

~~~http
GET /api/users?page=0&size=10 HTTP/1.1
Accept: application/json
Host: localhost:8080
~~~

When switching from `POST` to `GET`, the method and request target change directly in `http-request`. At the same time, calling `queryParameters(...)` generates an additional `query-parameters.adoc` snippet describing the meaning and constraints of the parameters. Prefer `queryParam(...)` in MockMvc when you want the query string to appear explicitly on the URI, rather than assuming every parameter passed to `param(...)` will be rendered on the request line.

For path variables, distinguish between:

- `GET /api/users/42`: the actual request target containing the value `42`.
- `GET /api/users/{id}`: the endpoint template in documentation, used to explain the meaning of `id`.

When generating `path-parameters.adoc` with MockMvc, use Spring REST Docs' URI-template-aware request builders (for example `RestDocumentationRequestBuilders.get("/api/users/{id}", 42)`) and `pathParameters(...)` to bind the variable names properly.

## 6. Adding Descriptions While Keeping `http-request` as the Example Source

A raw HTTP request alone is not enough for API consumers to know which fields are required, what valid data looks like, or what a header is used for. You can add specialized snippets right inside the `document(...)` call.

For example, extend the create-user test with the code below, along with the static imports:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

// Replace .andDo(document("users-create")) in the create-user test with:
.andDo(document("users-create",
    requestHeaders(
        headerWithName("X-Request-Id")
            .description("Client request tracking ID")
    ),
    requestFields(
        fieldWithPath("name").description("Display name"),
        fieldWithPath("email").description("Valid email address")
    )
));
~~~

Spring REST Docs then keeps the default snippets while adding `request-headers.adoc` and `request-fields.adoc`. Descriptors also act as **contract verification**: if the payload has an undocumented field or a documented field does not exist according to the corresponding validation rules, snippet generation can cause the test to fail. This keeps documentation aligned with the tested request.

Keep the scopes clearly separated:

- `http-request`: illustrates **one concrete request**, including method, URI, headers, and body.
- `requestHeaders`: table explaining relevant request headers.
- `requestFields`: field table for the JSON/XML request body.
- `queryParameters` and `pathParameters`: tables of URI parameters.
- `responseFields`: field table for the response body, independent of the request method.

These snippets only record behavior **executed by tests**. A single example for `POST` does not replace writing tests and documentation for `GET`, `PUT`, or `DELETE` if the API supports those operations.

## 7. Applying the Same Principles with WebTestClient and REST Assured

The HTTP method still comes from the request under test, regardless of which client is used:

| Test tool | How the HTTP method is chosen | Where documentation generation is attached |
| --- | --- | --- |
| **MockMvc** | `perform(post(...))`, `perform(get(...))` | `.andDo(document("identifier"))` |
| **WebTestClient** | `webTestClient.get().uri(...)`, `post()`... | `.expectBody().consumeWith(document("identifier"))` after exchange/assertions |
| **REST Assured** | `given()...when().post(...)`, `get(...)`... | REST Docs filter `document("identifier")` configured on the request specification |

Brief example with a **WebTestClient configured with Spring REST Docs**:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
    .uri("/api/users?page=0&size=10")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("users-list-webtestclient"));
~~~

With REST Assured, use the `spring-restdocs-restassured` module and configure the REST Docs filter on the request specification before sending the request. Both tools still generate `http-request` from the recorded operation. Setting up the extension/filter, output directory, and request specification depends on the test framework and Spring REST Docs version chosen by the project.

## 8. Controlling the Data Shown in Sample Requests

Requests created by tests sometimes contain internal hosts, tokens, cookies, random IDs, or hard-to-read bodies. These elements affect documentation even when the API processes them properly.

**Preprocessing** lets you adjust how data is presented in snippets—for example, formatting JSON or hiding sensitive headers. It does not alter the request that the application processed.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

// Keep the test request unchanged; only clean up the request when generating documentation:
.andDo(document("users-create",
    preprocessRequest(
        removeHeaders("Authorization"),
        prettyPrint()
    )
));
~~~

This block is an **alternative** to the `.andDo(...)` call; do not append a second call with the same identifier. If the documentation needs to describe the `Authorization` header, document authentication requirements separately and use a safe replacement/masking approach, because removing a header from the recorded request can conflict with a required `requestHeaders(...)` descriptor.

With MockMvc, if you want snippets to show a public host, scheme, and port, configure the URI in REST Docs (such as `uriHost`, `uriScheme`, `uriPort` attributes on `@AutoConfigureRestDocs` in the corresponding Spring Boot version). With clients running against a real server, REST Docs also supports preprocessors to modify the URI for documentation. Use a placeholder hostname like `api.example.com`; do not put real access tokens or cookies into source code or test fixtures.

## 9. Including Snippets in Documentation and CI

By default, Spring REST Docs generates **Asciidoctor** (`*.adoc`) snippets. In an Asciidoctor file, you can include the content generated by tests:

~~~asciidoc
= Users API

== Create User

Send POST /api/users with a valid name and email.

=== HTTP request
include::{snippets}/users-create/http-request.adoc[]

=== HTTP response
include::{snippets}/users-create/http-response.adoc[]

== List Users

=== HTTP request
include::{snippets}/users-list/http-request.adoc[]

=== Query parameters
include::{snippets}/users-list/query-parameters.adoc[]
~~~

The Asciidoctor `snippets` attribute must be configured in the build to point to the snippet output directory (in the example, `build/generated-snippets`). Do not hardcode one fixed relative path for all projects: the actual location depends on where the `.adoc` file resides and how the build plugin invokes Asciidoctor.

Typical build/CI flow:

~~~mermaid
flowchart LR
    A["Run HTTP tests"] --> B["Generate snippets"]
    B --> C["Asciidoctor includes snippets"]
    C --> D["Export HTML/PDF documentation"]
    D --> E["Package or publish"]
~~~

Configure the documentation generation task to **depend on** the test task so includes do not read stale snippets. If you want to author documentation in Markdown, configure the corresponding format/template and processing workflow; do not assume you can include `*.adoc` directly into Markdown and expect every renderer to understand Asciidoctor syntax.

## 10. Common Pitfalls

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `http-request.adoc` is missing | REST Docs not configured, `document(...)` not called, test failed before the document step, or looking in the wrong output directory | Verify configuration, run the right test, and check the folder matching the identifier. |
| Snippet shows `GET` even though docs say `POST` | Test code actually calls `get(...)` or includes the wrong identifier | Open the test and request line, fix the method/identifier to match the endpoint. |
| Wrong method causes test to receive `405` | Request method is not allowed by the endpoint | Check the API mapping and assertion; do not edit docs to hide a test error. |
| Missing query string | Test passes data to `param(...)` without producing a query string on the URL as expected | Use `queryParam(...)` or a URI with an explicit query string. |
| No field/header table | `http-request` does not auto-generate description tables | Declare `requestFields(...)`, `requestHeaders(...)`, or `queryParameters(...)`. |
| Sample request contains tokens or sensitive data | Test fixture uses real data or is not preprocessed | Use dummy data, mask/replace headers and body before generating documentation. |
| Documentation page missing snippets at build time | Asciidoctor runs before tests, `snippets` points to the wrong directory, or identifier differs | Check build task ordering and include paths. |

## 11. Hands-on Exercise

For a sample book management API, write three independent HTTP tests:

1. `POST /api/books` sending JSON, expecting `201 Created`, written to `books-create/http-request.adoc`.
2. `GET /api/books?page=0&size=5`, expecting `200 OK`, documenting both parameters and written to `books-list/http-request.adoc`.
3. `DELETE /api/books/42`, expecting the status per the API contract (e.g., `204 No Content`), written to `books-delete/http-request.adoc`.

Then open each `http-request.adoc` and verify that the first three request lines start with `POST`, `GET`, and `DELETE`, respectively. Add them to an Asciidoctor document, re-run the tests, then intentionally change the method in one test to see the assertion catch the mismatch.

**Completion criteria:** each operation has a distinct identifier, an appropriate assertion, snippets accurately reflect the HTTP method and URI invoked, the documentation includes the right files, and CI only publishes documentation after the relevant tests pass.

## Official References

- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Customizing requests and responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
