# `document(operation)` to Generate Snippets with MockMvc

## 1. From HTTP Operation to Verifiable Documentation

**Spring REST Docs** generates REST API documentation from requests and responses recorded during HTTP tests. It provides integrations for **MockMvc**, WebTestClient, and REST Assured; in the **MockMvc** chapter, we use the results of `mockMvc.perform(...)` to generate **snippets** for requests, responses, payloads, parameters, headers, and other parts of the API contract.

A snippet is a documentation fragment that can be included into Asciidoctor or Markdown. Unlike handwritten HTTP examples, snippets originate from actual test execution data and can be regenerated during builds and CI. If descriptors do not match the request or response, the documentation test typically fails, helping catch outdated documentation early.

When referring to "**`document(operation)` to generate snippets**", we need to distinguish two layers:

- **At the MockMvc test layer:** developers call `.andDo(document("books-get", ...))`. Here, `document(...)` is a method on `MockMvcRestDocumentation` that accepts an **identifier** and optional `Snippet` instances, returning a `ResultHandler`.
- **At the internal processing layer:** Spring REST Docs converts the HTTP result into an **`Operation`**, containing the request, response, and required metadata. `Snippet` implementations use this `Operation` to write snippet contents to files. In the SPI, `Snippet.document(Operation)` is how each snippet generates its own content.

Therefore, **do not write `.andDo(document(operation))` with an `Operation` variable in a regular MockMvc test**. The actual usage in tests is:

```java
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                pathParameters(
                        parameterWithName("id").description("Book ID")),
                responseFields(
                        fieldWithPath("id").description("Book ID"),
                        fieldWithPath("title").description("Book title"),
                        fieldWithPath("price").description("List price"))));
```

The goal of this lesson is to understand **how an operation is created**, where `document(...)` is called, which snippets are generated, and how to integrate them into documentation and the build pipeline.

## 2. Snippet Generation Mechanism: From Request to File

```text
JUnit Jupiter + RestDocumentationExtension
                |
                v
    RestDocumentationContextProvider
                |
                v
 MockMvcBuilders.standaloneSetup(...)
     .apply(documentationConfiguration(...))
     .build()
                |
                v
       mockMvc.perform(...)
                |
                v
    HTTP request + HTTP response
                |
      andExpect(...) verifies
                |
                v
  andDo(document("books-get", Snippet...))
                |
                v
       Spring REST Docs Operation
                |
      +---------+-----------+-------------+
      |         |           |             |
      v         v           v             v
  HTTP text  Parameters  JSON fields   Headers
      |         |           |             |
      +---------+-----------+-------------+
                |
                v
    build/generated-snippets/books-get/
                |
                v
    Asciidoctor / Markdown -> CI / publish
```

| Component | Responsibility | Automatically generates files? |
| --- | --- | --- |
| `MockMvcRequestBuilders.get/post/...` | Builds the request to test | No. |
| `MockMvc.perform(...)` | Executes the request in simulated Spring MVC infrastructure | Does not automatically create per-identifier snippets. |
| `andExpect(...)` | Checks status, headers, payload; fails test on mismatch | No. |
| `documentationConfiguration(restDocumentation)` | Connects Spring REST Docs to MockMvc configuration | Prepares the recording mechanism; by itself does not decide which operations to record. |
| `document("identifier", snippets...)` | Requests recording the executed operation as snippets under the specified identifier | Yes, when called in a properly configured test. |
| `Snippet` | Describes/writes an aspect of the operation, e.g., `responseFields` or `pathParameters` | Executed by Spring REST Docs while recording the operation. |

`document(...)` does not replace assertions. Documentation tests should place `andExpect(...)` **before** `andDo(document(...))` so an out-of-contract response is never recorded as a passing example. Additionally, Spring REST Docs field and parameter descriptors can detect undocumented data and fail the test.

## 3. Setting Up the MockMvc + Spring REST Docs Environment

The examples use **Java 17+, Spring Boot 3.x, Spring MVC, and JUnit Jupiter (JUnit 5)**. With Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

When a project uses Spring Boot dependency management, let the BOM select the compatible Spring REST Docs version. Without the BOM, declare versions compatible with your Spring Framework, Spring Test, and Java versions.

To create a MockMvc instance that generates snippets with JUnit Jupiter:

```java
@ExtendWith(RestDocumentationExtension.class)
class BookDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

In this condensed example, classes are imported from `org.junit.jupiter.api`, `org.springframework.restdocs`, and `org.springframework.test.web.servlet`, plus the static import `MockMvcRestDocumentation.documentationConfiguration`. `RestDocumentationExtension` supplies the context so Spring REST Docs can name and write snippets per test execution. On `MockMvcBuilder`, `.apply(documentationConfiguration(...))` must appear before `.build()`.

The examples use `standaloneSetup` to keep the focus on `document(...)`. In a real application, you can substitute `webAppContextSetup(webApplicationContext)` or use Spring Boot's auto-configured MockMvc with Spring REST Docs integration. Regardless of the setup, the `perform → assert → document` flow remains identical.

## 4. Complete Example: Recording GET and POST Operations

We create a small book API to demonstrate two types of operations:

1. `GET /api/books/{id}` returns `200 OK`, JSON containing `id`, `title`, `price`, and the `X-Trace-Id` header.
2. `POST /api/books` accepts JSON containing `title` and `price`, returning `201 Created`, a `Location` header, and the created resource JSON.

The JUnit class below places a sample controller inside the test for deterministic data. In a real product, the controller resides in application code and tests should verify cases aligned with the API contract.

```java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .setMessageConverters(new MappingJackson2HttpMessageConverter())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", "bk-101")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string("X-Trace-Id", "trace-doc-01"))
                .andExpect(jsonPath("$.id").value("bk-101"))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andExpect(jsonPath("$.price").value(199000))
                .andDo(document("books-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Book identifier")),
                        requestHeaders(
                                headerWithName(HttpHeaders.ACCEPT)
                                        .description("Desired response format")),
                        responseHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Response trace ID")),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Book ID"),
                                fieldWithPath("title")
                                        .description("Book title"),
                                fieldWithPath("price")
                                        .description("List price"))));
    }

    @Test
    void documentCreateBook() throws Exception {
        mockMvc.perform(post("/api/books")
                        .accept(MediaType.APPLICATION_JSON)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"MockMvc Guide","price":165000}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/books/bk-102"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("bk-102"))
                .andExpect(jsonPath("$.title").value("MockMvc Guide"))
                .andExpect(jsonPath("$.price").value(165000))
                .andDo(document("books-create",
                        requestFields(
                                fieldWithPath("title")
                                        .description("Title of the book to create"),
                                fieldWithPath("price")
                                        .description("Book price")),
                        responseHeaders(
                                headerWithName(HttpHeaders.LOCATION)
                                        .description("URL of the newly created book")),
                        responseFields(
                                fieldWithPath("id")
                                        .description("New book ID"),
                                fieldWithPath("title")
                                        .description("Book title"),
                                fieldWithPath("price")
                                        .description("List price"))));
    }

    @RestController
    public static class BookController {

        @GetMapping(
                value = "/api/books/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> find(
                @PathVariable("id") String id) {
            Map<String, Object> book = Map.of(
                    "id", id,
                    "title", "Spring REST Docs",
                    "price", 199000);
            return ResponseEntity.ok()
                    .header("X-Trace-Id", "trace-doc-01")
                    .body(book);
        }

        @PostMapping(
                value = "/api/books",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> create(
                @RequestBody Map<String, Object> request) {
            Map<String, Object> created = Map.of(
                    "id", "bk-102",
                    "title", request.get("title"),
                    "price", request.get("price"));
            return ResponseEntity.created(
                    URI.create("/api/books/bk-102")).body(created);
        }
    }
}
```

### Analyzing the Two `document(...)` Calls

**GET `books-get`**:

- `get("/api/books/{id}", "bk-101")` preserves the URI template so Spring REST Docs knows `id` is a path parameter.
- The `andExpect(...)` calls verify status `200`, media type, `X-Trace-Id` header, and JSON contents.
- `document("books-get", ...)` records the HTTP operation under identifier `books-get` and generates `path-parameters`, `request-headers`, `response-headers`, and `response-fields` alongside the default snippets.

**POST `books-create`**:

- `post("/api/books")` sends `Content-Type: application/json` and a JSON body with two fields.
- Assertions safeguard `201 Created`, `Location`, and the JSON response before writing documentation.
- `requestFields(...)` describes the input body; `responseHeaders(...)` describes the `Location` header; `responseFields(...)` describes the output body.

Identifiers **must reflect distinct operations**. Reusing the same identifier across multiple tests recording different responses can overwrite snippet files or produce unstable output during parallel execution. It is best to use a unique, readable name per endpoint/scenario, such as `books-get`, `books-create`, and `books-get-not-found`.

## 5. Ways to Use `document(...)`

### 5.1. Default Snippets Only

```java
mockMvc.perform(get("/api/health"))
        .andExpect(status().isOk())
        .andDo(document("health-get"));
```

This short example is valid only when `/api/health` is registered in the test environment. Passing no descriptors tells Spring REST Docs to write the configured default snippets, such as `http-request`, `http-response`, `curl-request`, `httpie-request`, `request-body`, and `response-body`. The exact files and count depend on the version, snippet configuration, and actual data.

### 5.2. Adding Descriptors per API Contract

```java
.andDo(document("books-get",
        pathParameters(
                parameterWithName("id").description("Book ID")),
        responseFields(
                fieldWithPath("id").description("ID"),
                fieldWithPath("title").description("Book title"),
                fieldWithPath("price").description("Price"))));
```

This snippet is a continuation of `mockMvc.perform(...).andExpect(...)`; the corresponding classes and static imports appear in the complete example in section 4. Adding `Snippet` arguments instructs Spring REST Docs to create additional files for each descriptor type. You do not need to write `.adoc` files manually.

### 5.3. Preprocessing Requests and Responses Before Generating Snippets

`OperationRequestPreprocessor` and `OperationResponsePreprocessor` adjust **how an operation is presented in documentation**, commonly to pretty-print JSON or mask data that should not be published.

Example formatting JSON for readability:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

// Chained after mockMvc.perform(...).andExpect(...).
.andDo(document("books-create",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint()),
        requestFields(
                fieldWithPath("title").description("Book title"),
                fieldWithPath("price").description("Book price")),
        responseFields(
                fieldWithPath("id").description("Book ID"),
                fieldWithPath("title").description("Book title"),
                fieldWithPath("price").description("Book price"))));
```

`prettyPrint()` only formats the output written to snippets; it does not alter the actual response returned by the controller during `andExpect(...)`. For sensitive data or dynamic values, consider preprocessors that modify headers, URIs, or content while ensuring the snippets remain faithful to the published API contract.

### 5.4. Public URI Differing from MockMvc URI

MockMvc runs inside the JVM and does not send real requests to a server. To make URIs displayed in snippets match the public API:

```java
mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
        .apply(documentationConfiguration(restDocumentation)
                .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
        .build();
```

The host/scheme/port here only affect how URIs are displayed in documentation; requests are still processed locally by MockMvc. If you already have the builder setup from section 4, update that same builder instead of creating an unrelated MockMvc instance.

## 6. Snippet Groups and the Data Used to Generate Them

Each `Snippet` requires the right kind of data in the HTTP operation:

| Item to Document | Common Descriptor API | Resulting Snippet |
| --- | --- | --- |
| HTTP request/response | Default snippets | `http-request.adoc`, `http-response.adoc` |
| Command-line call examples | Corresponding default snippets | `curl-request.adoc`, optionally `httpie-request.adoc` |
| JSON request | `requestFields(fieldWithPath(...))` | `request-fields.adoc` |
| JSON response | `responseFields(fieldWithPath(...))` | `response-fields.adoc` |
| Path parameter | `pathParameters(parameterWithName(...))` | `path-parameters.adoc` |
| Query parameter | `queryParameters(parameterWithName(...))` | `query-parameters.adoc` |
| Form parameter | `formParameters(parameterWithName(...))` | `form-parameters.adoc` |
| Request/response headers | `requestHeaders(...)`, `responseHeaders(...)` | `request-headers.adoc`, `response-headers.adoc` |
| Multipart part | `requestParts(partWithName(...))` | `request-parts.adoc` |
| Entire body | Default snippets or chosen body snippets | `request-body.adoc`, `response-body.adoc` |

Spring REST Docs also supports other descriptors such as cookies, multipart part payloads, subsections, and constraints. Do not declare descriptors just to generate extra files: **snippets must match the executed operation**.

For example, for `GET /api/books/{id}`:

```java
pathParameters(
        parameterWithName("id")
                .description("ID of the book to find"))
```

If the test only calls `get("/api/books/bk-101")`, the tool may lack the URI template needed to associate `id` with the actual path. Use a templated request builder `get("/api/books/{id}", "bk-101")` when generating a path parameter snippet.

For JSON payloads, `responseFields(...)` normally requires documenting every field present in the response. If `price` is omitted while the payload still contains `price`, the documentation test will fail under the default strict checking mode. Do not work around this by marking every field `optional()` or overusing relaxed descriptors.

## 7. Strict Documentation, Optional Fields, and Partial Descriptions

To ensure documentation does not omit API data, Spring REST Docs checks consistency between the operation and descriptors. Given JSON:

```json
{
  "id": "bk-101",
  "title": "Spring REST Docs",
  "price": 199000,
  "currency": "VND"
}
```

If you write:

```java
responseFields(
        fieldWithPath("id").description("ID"),
        fieldWithPath("title").description("Title"),
        fieldWithPath("price").description("Price"))
```

then `currency` is undocumented and the strict snippet check will fail the test. The preferred fix is adding `fieldWithPath("currency").description("Currency unit")` if the field belongs to the API contract.

Options to understand accurately:

- `fieldWithPath("description").optional()`: the field may validly be **absent**; it does not mean other fields in the response can be skipped.
- `fieldWithPath("internalId").ignored()`: the field is recognized and intentionally excluded from the documentation table; use only when the API genuinely permits omitting it.
- `relaxedResponseFields(...)` or `relaxedRequestFields(...)`: ignores undocumented fields. Useful when documenting only part of a large payload, though it reduces the ability to detect unexpected fields added to the API.

In a system treating documentation as part of the contract, prefer strict descriptors for public endpoints. If fields vary dynamically with time or data, choose field names and verification strictness based on API specifications, not simply to make tests pass.

**Important:** strict snippet checking mainly covers **field structure and presence according to descriptors**. It does not replace `andExpect(jsonPath("$.price").value(199000))` for protecting business values, or `andExpect(status().isOk())` for verifying the status code.

## 8. File Locations and Including Snippets in Asciidoctor/Markdown

Run:

```bash
./gradlew test
```

With Gradle, the default snippet output location is usually `build/generated-snippets/`; with Maven, it is `target/generated-snippets/`. The actual location depends on build configuration and the REST Docs context. For the two tests in the example, a typical file tree looks like:

```text
build/generated-snippets/
├── books-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   ├── path-parameters.adoc
│   ├── request-headers.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── books-create/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── request-fields.adoc
    ├── response-headers.adoc
    └── response-fields.adoc
```

This is a **condensed illustrative structure**; other default snippets such as `httpie-request.adoc`, `request-body.adoc`, and `response-body.adoc` may also appear. Do not conclude a test is wrong solely because the file count differs from the example tree; check the snippets actually configured and requested.

An Asciidoctor page can reference the files:

```adoc
= Books REST API

== Get Book Information

include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/request-headers.adoc[]
include::{snippets}/books-get/http-response.adoc[]
include::{snippets}/books-get/response-fields.adoc[]

== Create Book

include::{snippets}/books-create/http-request.adoc[]
include::{snippets}/books-create/request-fields.adoc[]
include::{snippets}/books-create/http-response.adoc[]
include::{snippets}/books-create/response-headers.adoc[]
include::{snippets}/books-create/response-fields.adoc[]
```

`{snippets}` is an Asciidoctor attribute that must be configured to point to the output directory. If the documentation product uses Markdown, an appropriate embedding or snippet-conversion step is needed, as default Spring REST Docs snippets are typically AsciiDoc.

A build/CI pipeline should ensure:

1. **HTTP tests** run in a deterministic environment and with deterministic data; assertions must pass.
2. **Spring REST Docs** writes snippets from the operations in the tests.
3. The Asciidoctor/Markdown **compilation task** depends on the snippet generation step, preventing stale files from being used.
4. **Publishing** happens only after both tests and the compilation task succeed.

Do not treat a leftover `generated-snippets` directory from a previous build as proof that the current tests passed; check the results of the current run.

## 9. Common Errors Around `document(...)`

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| No snippet directory for a test | `andDo(document(...))` not called or a preceding assertion failed | Verify the test ran, matcher results, and documentation call. |
| Missing REST Docs context error | `RestDocumentationExtension` not registered or MockMvc setup incomplete | Supply `RestDocumentationContextProvider` and `.apply(documentationConfiguration(...))` before `.build()`. |
| Snippet files in the wrong directory | Different identifier than expected or different output directory | Check `document("...")` name, REST Docs configuration, and build settings. |
| Files from two tests collide | Reused identifier across different operations | Assign unique identifiers per endpoint/scenario, especially under parallel execution. |
| `pathParameters(...)` reports error | URI did not preserve template or descriptor has wrong variable name | Use `get("/api/books/{id}", id)` and `parameterWithName("id")`. |
| `responseFields(...)` fails | Payload has undocumented field, declared field does not exist, or invalid JSON | Compare with actual body, fix descriptors, and check content type. |
| `requestFields(...)` fails | JSON body differs from documented fields | Check `Content-Type`, `content(...)`, and fields against the data actually sent. |
| `responseHeaders(...)` cannot find header | Expected header did not appear in the operation | Verify with `header().exists(...)` and inspect controller/filters. |
| Snippets show `localhost` URL | Display URI not customized | Configure `.uris().withScheme(...).withHost(...).withPort(...)`. |
| Asciidoctor reports missing include | Wrong file/snippet name, test has not generated snippets, or `{snippets}` points to wrong folder | Check actual generated snippets and compilation task dependencies. |
| Test passes but example has wrong business status | Only `document(...)` used without proper assertions | Add `andExpect(status/header/body)` before documenting. |

### When You Need to Inspect the Actual Operation

During debugging, you can use:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andDo(print())
        .andExpect(status().isOk());
```

`print()` displays the request, handler, status, headers, and body for the test, without writing REST Docs documentation. Do not print real sensitive data into logs. Once inspected, combine `andExpect(...)` with `document(...)` to generate assertion-backed snippets.

## 10. Practice Exercises

1. **Default snippets:** create a test for `GET /api/health`, assert `200 OK`, then call `document("health-get")`. Verify the actual directory and files generated.
2. **Path parameters:** add `GET /api/books/{id}` and document `id` with `pathParameters(...)`. Try renaming the descriptor to `bookId` and observe the test failing; fix the name back.
3. **JSON fields:** add a `currency` field to the response without updating `responseFields(...)` and observe the strict failure. Add the descriptor and re-run the test.
4. **POST and headers:** document `requestFields(...)`, `responseHeaders("Location")`, and `responseFields(...)`. Remove the `Location` header in the controller to see assertions and documentation both catch the contract change.
5. **Preprocessors:** apply `preprocessRequest(prettyPrint())` and `preprocessResponse(prettyPrint())` to a JSON operation; compare snippets before and after formatting.
6. **Build/CI:** create an Asciidoctor page referencing the `books-get` and `books-create` snippets; configure the compilation task to depend on tests so data is always fresh.

**Completion criteria:** each operation has a unique identifier, assertions protect status/headers/body, descriptors match actual data, snippets are written to the expected path, and the final documentation compiles from the current test results.

## 11. Pre-Completion Checklist

- [ ] MockMvc has Spring REST Docs integrated via `documentationConfiguration(...)` or the equivalent Spring Boot mechanism.
- [ ] Requests use the endpoint's exact method, URI template, query/headers/body.
- [ ] `andExpect(...)` assertions cover status, headers, and important payload values **before** `andDo(document(...))`.
- [ ] `document("identifier", snippets...)` uses a unique, stable name for each HTTP scenario.
- [ ] `pathParameters`, `requestFields`, `responseFields`, and other descriptors reflect the actual operation.
- [ ] Secrets or volatile data are handled appropriately in tests and published snippets.
- [ ] Generated snippets path has been verified and all `include` directives compile cleanly.
- [ ] Build/CI generates fresh snippets after tests pass before compiling/publishing documentation.

**Remember:** In MockMvc, `document("identifier", snippets...)` connects **a tested HTTP operation** with its snippets. `Operation` holds the request/response data passed internally by Spring REST Docs to each `Snippet`. Combining HTTP verification, descriptors, and the build pipeline makes REST API documentation testable right alongside the source code.
