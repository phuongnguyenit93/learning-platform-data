# REST Resources, Requests, and Responses in an Operation

In **Spring REST Docs**, API documentation is built from tested HTTP interactions. To read a piece of documentation accurately, you first need to distinguish three concepts: a **REST resource** is the business object exposed by the API; a **request** is the client's demand on the resource; and a **response** is the result returned by the server. One request paired with its corresponding response forms an **operation** that Spring REST Docs can record and document.

This lesson belongs to the **Documentation Model** chapter and focuses on viewing an operation as the unit of documentation. The examples use Spring REST Docs with MockMvc; the same mindset applies to WebTestClient or REST Assured. From an operation, we generate snippets for paths, parameters, headers, and payloads, and include them in Asciidoctor/Markdown documentation in the build and CI pipeline.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish between resource, URI, JSON representation, request, response, and operation.
- Identify the HTTP components that must be documented so consumers can call an endpoint correctly.
- Design separate test operations for success and error cases.
- Attach documentation to MockMvc tests to generate snippets from actual requests and responses.
- Assemble snippets into reproducible documentation during the build and verify them in CI.

## 2. A REST Resource Is Not Synonymous with a Request

Suppose a book management service has a **book** resource. The URI `/api/books/42` identifies the book with ID `42`; clients can interact with this resource using different HTTP methods.

| Method and URI | Business meaning | Common response |
| --- | --- | --- |
| `GET /api/books/42` | Read the representation of book 42 | `200 OK` with JSON; `404 Not Found` if the book does not exist |
| `GET /api/books?author=An` | Search for a list of books using a filter | `200 OK` with list and metadata |
| `POST /api/books` | Request to create a new book resource | `201 Created`, often with a `Location` header |
| `PUT /api/books/42` | Replace the resource state according to the API contract | `200 OK` or `204 No Content` |
| `PATCH /api/books/42` | Partially update the resource state | `200 OK` or `204 No Content` |
| `DELETE /api/books/42` | Delete book 42 | `204 No Content` or an appropriate error code |

**Resource** is a business concept; **URI** is the identifier or address used to access it; **representation** is the data that the client and server exchange about the resource, such as a JSON object. Multiple URIs can relate to the same resource type, and a single URI can support multiple methods. Therefore, a single line of documentation for the “book resource” is not enough to replace documentation for each interaction.

For example, two requests both use `/api/books/42`, yet `GET` and `DELETE` carry different meanings, input preconditions, and outcomes. Documentation needs to clearly specify **method + path + handling scenario**, rather than just listing URIs.

## 3. Operation: The Unit That Is Observed and Recorded

An HTTP operation is a single exchange with a corresponding request and response during testing:

```text
Client
  │  GET /api/books/42?locale=vi
  │  Accept: application/json
  ├──────────────────────────────────────► Server
  │
  │  HTTP/1.1 200 OK
  │  Content-Type: application/json
  │  {"id":42,"title":"Spring REST Docs","locale":"vi"}
  ◄──────────────────────────────────────┤
```

In the Spring REST Docs model:

1. A test sends a request using MockMvc, WebTestClient, or REST Assured.
2. The application (or controller under test) produces a response.
3. The test verifies behavior using assertions, such as the HTTP status and JSON fields.
4. Spring REST Docs captures the request/response of that execution and generates snippets according to the `document(...)` configuration.
5. Asciidoctor/Markdown references the snippets to present the API contract to readers.

An operation has **observed data** (method, URI, headers, body, status) and **author-declared descriptions** (meaning of parameters, JSON fields, examples). Recording requests and responses keeps examples aligned with tested behavior. However, a test still only proves the specific case it actually runs through; it does not automatically cover every error branch, every role, or every API variant.

### 3.1. Breaking Down Request Components

Example request to read a book:

```http
GET /api/books/42?locale=vi HTTP/1.1
Host: api.example.test
Accept: application/json
```

| Component | Value in example | Question the documentation must answer |
| --- | --- | --- |
| HTTP method | `GET` | What action does the client need to perform? |
| Path | `/api/books/42` | What is the access path and which variables are in the path? |
| Path parameter | `id = 42` | Which object does `id` identify, and what constraints apply? |
| Query parameter | `locale = vi` | Is this filter or option required? |
| Request header | `Accept: application/json` | Which response format does the client expect? |
| Request body | None in this example | Must a payload be sent? If so, which fields does it contain? |

`Accept` indicates the representation format the client wants to receive; `Content-Type` indicates the data type of the body **being sent**. These two headers serve different roles. The `GET` request above has no body, so there is no need to document request fields. For a `POST` with a JSON body, both `Content-Type` and the payload structure must be documented.

A **path parameter** is a named part of the path in a route template, such as `{id}`. A **query parameter** appears after `?` and typically adjusts searching, filtering, or presentation. Never treat `id` in `/api/books/{id}` as a query parameter.

### 3.2. Breaking Down Response Components

Example successful response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "title": "Spring REST Docs",
  "locale": "vi"
}
```

| Component | Meaning | What needs to be documented |
| --- | --- | --- |
| Status | `200 OK` | Under what scenario does the request succeed? |
| Response header | `Content-Type` | Returned representation type; include other headers if part of the contract |
| Response body | JSON object | Structure, type, and meaning of each field |
| `id` | Integer | Book identifier |
| `title` | String | Book title |
| `locale` | String | Language used by the example data |

A response does not always have a JSON body. `204 No Content` normally has no body; `404 Not Found` may have an error JSON or an empty body depending on the design; `201 Created` commonly uses `Location` to point to the URI of the newly created resource. **Each case must be based on the actual contract and response**, rather than inferring a body from the status and writing documentation from assumptions.

### 3.3. One Resource Can Have Multiple Documented Operations

For `GET /api/books/{id}`, at least two scenarios should be considered:

| Test operation | Request | Response | Content to document |
| --- | --- | --- | --- |
| `books-get` | `GET /api/books/42` | `200` and book information | Path parameter, response fields, relevant headers |
| `books-get-not-found` | `GET /api/books/999` | `404` and error format (if any) | Not-found condition, status, error structure |

These are **two separate interactions** even though they share the same route. Assigning distinct snippet identifiers keeps success and error examples from overwriting each other. When the API also has `400`, `401`, `403`, `409`, or pagination, add operations for behaviors that matter to integrators. You do not necessarily have to generate documentation for every input combination; select the scenarios that shape the public contract of the API.

## 4. Creating an Actual Operation with MockMvc and Spring REST Docs

The example below uses a minimal controller to focus on the boundary between resource and operation. The controller returns the same sample book or `404`. In a real project, data may come from a repository/service, and test fixtures should be prepared reproducibly.

```java
@RestController
class BookController {

    @GetMapping(
        value = "/api/books/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<BookDto> getBook(
            @PathVariable long id,
            @RequestParam(defaultValue = "vi") String locale) {

        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(
            new BookDto(42L, "Spring REST Docs", locale)
        );
    }

    record BookDto(long id, String title, String locale) {}
}
```

A JUnit 5 test with MockMvc can be set up as follows. Java imports are omitted for readability; use `RestDocumentationExtension`, `MockMvcBuilders.standaloneSetup`, `MockMvcRestDocumentation.documentationConfiguration`, and the corresponding documentation methods from Spring REST Docs. The example uses the Spring REST Docs 3.x `queryParameters` API.

```java
@ExtendWith(RestDocumentationExtension.class)
class BookApiDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new BookController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void getBook_documentation() throws Exception {
        mockMvc.perform(
                get("/api/books/{id}", 42L)
                    .queryParam("locale", "vi")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Spring REST Docs"))
            .andDo(document("books-get",
                pathParameters(
                    parameterWithName("id")
                        .description("Identifier of the book to read")
                ),
                queryParameters(
                    parameterWithName("locale")
                        .description("Language code for the result")
                        .optional()
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Data format the client wants to receive")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Book identifier"),
                    fieldWithPath("title")
                        .type(JsonFieldType.STRING)
                        .description("Book title"),
                    fieldWithPath("locale")
                        .type(JsonFieldType.STRING)
                        .description("Language code in the response")
                )
            ));
    }
}
```

In this test snippet, `get` must be imported from Spring REST Docs' `RestDocumentationRequestBuilders.get`. That builder preserves the URI template `/api/books/{id}` so `pathParameters(...)` recognizes the `id` variable. The standard `MockMvcRequestBuilders.get` does not automatically supply the necessary template information in the same way.

An important set of static imports:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

`JsonFieldType`, `RestDocumentationExtension`, `RestDocumentationContextProvider`, `MockMvc`, `MockMvcBuilders`, `MediaType`, and the JUnit/Spring annotations must be imported as usual. The project also needs a Spring REST Docs dependency compatible with the Spring Framework/Boot version in use.

### 4.1. Why Do Assertions and Documentation Live in the Same Test?

`andExpect(status().isOk())` and `jsonPath(...)` verify the actual execution result. `andDo(document(...))` takes the exact request and response from that run to generate documentation. When application behavior changes, assertions can fail; when JSON contains an undocumented field or is missing a documented required field, the `responseFields(...)` snippet can fail under the default strict checking mode.

Therefore, a documentation test plays two complementary roles:

- **Proof of behavior:** the operation went through the endpoint and satisfied the assertions.
- **Description verification:** the components declared in snippets match the observed payload and parameters.

Do not assume that “having generated snippets” means the entire API has been thoroughly tested. The example above has not yet verified the `404` contract, locale restrictions, or unauthorized access cases; those need appropriate tests if they are part of the API scope.

### 4.2. Reading the Generated Snippets

After the test succeeds, Spring REST Docs typically writes snippets under the build directory, such as `target/generated-snippets/books-get/` with Maven or `build/generated-snippets/books-get/` with Gradle (depending on project configuration).

| Snippet | Which part of the operation does it show? |
| --- | --- |
| `http-request.adoc` | Observed request line, headers, and body |
| `http-response.adoc` | Observed response status line, headers, and body |
| `curl-request.adoc` | Equivalent cURL command example |
| `httpie-request.adoc` | Equivalent HTTPie command example |
| `request-body.adoc` / `response-body.adoc` | Isolated body for convenient inclusion in documentation |
| `path-parameters.adoc` | Path parameter table from `pathParameters(...)` |
| `query-parameters.adoc` | Query parameter table from `queryParameters(...)` |
| `request-headers.adoc` | Request header table from `requestHeaders(...)` |
| `response-fields.adoc` | Response field table from `responseFields(...)` |

Descriptive snippets such as `path-parameters.adoc` and `response-fields.adoc` only appear when the test requests their generation. For an operation without a body, the corresponding body snippets may be empty; do not mechanically insert a “Request body” section into the documentation.

## 5. Resource Creation Operation: Request Body and Response Headers

To see the difference clearly, consider another operation, `POST /api/books`:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "title": "HTTP API Design"
}
```

Hypothetical response following a successful creation contract:

```http
HTTP/1.1 201 Created
Location: /api/books/43
Content-Type: application/json

{
  "id": 43,
  "title": "HTTP API Design"
}
```

In this operation, the documentation must describe:

- The request body contains a `title` field (string type, required per the contract example).
- The request `Content-Type` specifies the JSON format being sent.
- Status `201 Created` indicates the resource was created successfully.
- `Location` points to the new resource and may be a relative or absolute URI depending on the service contract.
- The response body provides the server-generated `id` and the resource's `title`.

In an actual `POST` test, after sending JSON with `.contentType(MediaType.APPLICATION_JSON).content(...)`, the snippet configuration might look like:

```java
.andDo(document("books-create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("JSON format of the request")
    ),
    requestFields(
        fieldWithPath("title")
            .type(JsonFieldType.STRING)
            .description("Title of the book to create")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI of the newly created book")
    ),
    responseFields(
        fieldWithPath("id")
            .type(JsonFieldType.NUMBER)
            .description("Server-assigned book ID"),
        fieldWithPath("title")
            .type(JsonFieldType.STRING)
            .description("Saved book title")
    )
));
```

This snippet illustrates **the `document(...)` part** of the book creation test; to run it, the controller must actually support `POST /api/books`, and the test must assert status `201`, the response body, and the headers according to the contract. Do not mix `books-create` snippets with the response of a `GET` test: they are two different operations.

If a request has nested fields, you can describe them using JSON paths, such as `author.name` or `items[].id`. If a header or field is genuinely optional, use `optional()` intentionally. Do not mark every field as optional just to make the test pass, because the documentation will lose the API's required-field contract.

## 6. Relationship Between Resource Documentation and Operation Documentation

Documentation typically has two layers:

- **Resource layer:** business purpose, how resources are identified, general rules, access permissions, states, and links to actions.
- **Operation layer:** method, path template, parameters, headers, body, status, response fields, and examples for each scenario.

Example documentation structure:

```text
Books (/api/books)
├── Read book: GET /api/books/{id}
│   ├── Success: 200 → books-get
│   └── Not found: 404 → books-get-not-found
├── Create book: POST /api/books
│   ├── Success: 201 → books-create
│   └── Invalid data: 400 → books-create-invalid
└── Delete book: DELETE /api/books/{id}
    └── Success: 204 → books-delete
```

For an endpoint with multiple response codes, explicitly state **the condition that leads to each code**. Simply placing two HTTP response blocks back-to-back without explaining when each occurs leaves readers unable to determine the expected behavior.

Certain decisions should be finalized at the contract level: which fields may be omitted, which fields may be `null`, date/time formats, error code standards, authentication requirements, and pagination conventions. Spring REST Docs can describe and verify many of those parts, but the author still needs to define the business rules upfront.

## 7. Including Operation Snippets in Asciidoctor or Markdown Documentation

Spring REST Docs produces documentation fragments; those fragments must be compiled into a complete page. For example, an AsciiDoc file for the read-book operation:

```asciidoc
=== Read book details

Retrieve information about a book by its identifier. When found, the API returns 200.

==== Example request
include::{snippets}/books-get/http-request.adoc[]

==== Path parameter
include::{snippets}/books-get/path-parameters.adoc[]

==== Query parameter
include::{snippets}/books-get/query-parameters.adoc[]

==== Example response
include::{snippets}/books-get/http-response.adoc[]

==== Response fields
include::{snippets}/books-get/response-fields.adoc[]
```

The build must point the `{snippets}` attribute to the test's snippet directory and enforce the task order:

```text
Run HTTP tests
       │
       ▼
Generate generated-snippets/
       │
       ▼
Convert AsciiDoc to HTML/PDF (or compile Markdown)
       │
       ▼
Verify and publish documentation
```

For Markdown, you can use a build step to inject snippet contents or generate the corresponding Markdown sections; do not assume the `include::{snippets}/...[]` directive is Markdown syntax supported by every compiler. Tying `test` and `asciidoctor`/compilation steps into the CI pipeline helps prevent documentation from being published with snippets that were not regenerated in that build.

If you want more readable request examples, you can use preprocessors such as `preprocessResponse(prettyPrint())` in `document(...)`. When documentation contains tokens or sensitive data, remove or mask them in published examples while ensuring assertions still check appropriate data in tests. You can also normalize hostnames, ports, and URIs so examples do not depend on the CI runner machine.

## 8. Common Mistakes When Modeling Operations

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `path-parameters` table is not generated | Test uses a request builder that does not preserve the URI template | Use `RestDocumentationRequestBuilders.get/post/...` with `{id}` |
| Response field test fails even though status is right | Payload adds an undocumented field, a documented field is missing, or types do not match | Update the contract or test to match intended behavior; only use `relaxedResponseFields` when partial documentation is truly needed |
| `POST` documentation has no body | Included snippet from a `GET` operation or the test did not send a payload | Create a dedicated test and snippet for `POST` with `requestFields(...)` |
| Success and error cases appear under the same example | Reused the same snippet name across scenarios | Use distinct identifiers, e.g., `books-get` and `books-get-not-found` |
| Documentation shows internal host or real token | Test request contains environment data or sensitive headers | Normalize host/URI, filter or mask sensitive info before outputting snippets |
| Built page is missing an `include` file | Tests have not run, wrong snippets path, or build task lacks the required dependency | Configure snippet generation before the compilation step and inspect output in CI |
| Sample responses shown without describing conditions | Missing operation behavior analysis | Clearly state when `200`, `201`, `400`, `404`, etc. occur |

Distinguish between **documenting** a field in a table and **testing the business logic** of that field. `responseFields(...)` checks structural documentation, but it does not replace value assertions like `jsonPath("$.id").value(42)` or checks for authorization, business state, and errors.

## 9. Self-Check Exercise

Suppose your team is adding the endpoints `GET /api/books/{id}?locale=vi` and `POST /api/books`.

1. Identify the shared resource, path parameter, and query parameter of the read-book operation.
2. Create two read-book tests for `200` and `404`, each with its own `document(...)` identifier.
3. In the `200` test, assert the status, one key business field, and document all returned fields; verify that the `response-fields.adoc` snippet is generated.
4. In the create-book test, send a JSON request body, assert `201` along with `Location`, and document `requestFields`, `responseHeaders`, and `responseFields`.
5. Include the snippets into a documentation page and rerun the build from a clean state without old snippets. The documentation must be generated completely from only the tests in the current build.

**Completion criteria:** every HTTP example in the documentation page traces back to a specific test operation; every field and parameter has a clear meaning; success and error scenarios do not share snippets; CI can regenerate the documentation when running tests and builds.

## 10. Takeaways

- A **resource** is a business object; a **request** expresses what the client wants to do; a **response** represents the server's result; an **operation** binds a request to its actual response in a single execution.
- One route can produce multiple operations to document, depending on the method and success/error scenarios.
- Spring REST Docs tests both verify HTTP behavior via assertions and generate snippets from requests/responses, headers, parameters, and JSON fields.
- A complete documentation page combines snippets with contract explanations, and is regenerated and verified in build/CI.
