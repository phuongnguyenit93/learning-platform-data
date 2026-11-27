# `RestDocumentationResultHandler` and Reusing Handlers

## 1. Why Reuse a Result Handler?

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests. With the **MockMvc** integration, each `mockMvc.perform(...)` call produces an HTTP result that can be verified with assertions and recorded as snippets for the request, response, payload, parameters, or headers. Snippets are then compiled into Asciidoctor/Markdown and integrated into builds and CI. Spring REST Docs also supports WebTestClient and REST Assured; this lesson focuses on organizing handlers in MockMvc.

In previous lessons, we usually wrote directly:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andDo(document("books-get"));
~~~

When multiple tests need the same request/response formatting, default snippet set, or preprocessing configuration, repeating `document(...)` in every test makes test code verbose and inconsistent. Spring REST Docs provides **`RestDocumentationResultHandler`** to store documentation recording configuration in an object and reuse it:

~~~java
private RestDocumentationResultHandler documentationHandler;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    documentationHandler = document("{method-name}");
    mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

Then, each request that needs snippets simply writes:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andDo(documentationHandler);
~~~

`RestDocumentationResultHandler` is a MockMvc `ResultHandler`. It receives the request execution result and delegates operation and snippet recording to Spring REST Docs. **Handlers are reusable; their identifier and snippet set must be designed to suit each test group.**

## 2. What Object Does `document(...)` Return?

The static method `MockMvcRestDocumentation.document(...)` has overloads accepting an identifier and `Snippet` instances, returning a `RestDocumentationResultHandler`. This object can be passed to `andDo(...)` like any other `ResultHandler`:

~~~java
import org.springframework.restdocs.mockmvc.RestDocumentationResultHandler;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

RestDocumentationResultHandler handler = document("books-get");
~~~

Distinguish three roles:

| Component | Role |
| --- | --- |
| `document("books-get", snippets...)` | Creates a handler bound with an identifier and the list of snippets to record. |
| `RestDocumentationResultHandler` | Result handler object that can be passed to `andDo(...)` or configured on the builder. |
| `andDo(handler)` | Executes the handler with the just-executed request/response result. |

Execution flow:

~~~text
document("identifier", snippets...)
              |
              v
RestDocumentationResultHandler
              |
              +---------------------------+
                                          |
mockMvc.perform(request)                  |
       |                                  |
       v                                  |
andExpect(status/header/body)             |
       |                                  |
       v                                  |
andDo(handler) <--------------------------+
       |
       v
HTTP Operation -> Snippet writers
       |
       v
generated-snippets/<identifier>/
~~~

Importantly, creating a handler **does not write files on its own**. Snippets are only written when the handler runs against a request result, such as via `andDo(handler)` or automatically via `alwaysDo(handler)` on the MockMvc builder.

## 3. Creating a Handler in `@BeforeEach` and Reusing It Across Tests

This is the standard pattern when each test method typically performs one documented operation. Use `{method-name}` so the identifier resolves to the test method name:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.mockmvc.RestDocumentationResultHandler;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class CatalogDocumentationTest {

    private MockMvc mockMvc;
    private RestDocumentationResultHandler documentationHandler;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        documentationHandler = document("{method-name}");

        mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void getCatalog() throws Exception {
        mockMvc.perform(get("/api/catalog")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(documentationHandler);
    }

    @Test
    void getBook() throws Exception {
        mockMvc.perform(get("/api/catalog/{id}", "bk-101")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(documentationHandler);
    }

    @Test
    void createBook() throws Exception {
        mockMvc.perform(post("/api/catalog")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"REST Docs\"}"))
                .andExpect(status().isCreated())
                .andDo(documentationHandler);
    }
}
~~~

In the example, `document("{method-name}")` is recreated in each `@BeforeEach`, so the identifier resolves to the running method, such as `getCatalog`, `getBook`, or `createBook`. These tests share the same snippet recording configuration without repeating `document(...)` calls with hardcoded names.

Illustrative classes like `CatalogController` must be defined in the test or replaced with your project's actual controller. The goal of the example is to demonstrate handler lifecycle, not to construct a full application configuration.

## 4. Reusing Handlers with Custom Snippet Sets

A handler can be created together with snippet descriptors, request/response preprocessors, and an identifier. When a group of tests shares a uniform response structure, this configuration helps standardize documentation:

~~~java
import org.springframework.restdocs.mockmvc.RestDocumentationResultHandler;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

private RestDocumentationResultHandler documentationHandler;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    documentationHandler = document(
            "{method-name}",
            preprocessRequest(prettyPrint()),
            preprocessResponse(prettyPrint()),
            responseFields(
                    fieldWithPath("id").description("Resource ID"),
                    fieldWithPath("title").description("Resource title")));

    mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

This is an **abbreviated configuration template**; only share these descriptors across responses that genuinely contain both `id` and `title`. If endpoint responses have different structures, do not force them onto a shared `responseFields(...)`. Instead, create specialized handlers or pass distinct descriptors in the respective tests.

For example:

~~~java
private RestDocumentationResultHandler bookHandler;
private RestDocumentationResultHandler categoryHandler;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    bookHandler = document(
            "books/{method-name}",
            responseFields(
                    fieldWithPath("id").description("Book ID"),
                    fieldWithPath("title").description("Book title")));

    categoryHandler = document(
            "categories/{method-name}",
            responseFields(
                    fieldWithPath("id").description("Category ID"),
                    fieldWithPath("name").description("Category name")));

    mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

Identifiers in this example are partitioned by resource group. When using dynamic placeholders, verify the actual snippet paths generated by Spring REST Docs during test runs; do not guess directory names solely from handler variable names.

## 5. Using `alwaysDo(handler)` When Recording Every Request

The MockMvc builder provides `alwaysDo(...)` to automatically run a `ResultHandler` after every request executed through that MockMvc instance. It can be used to avoid calling `andDo(documentationHandler)` in every test:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class AutomaticallyDocumentedApiTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        RestDocumentationResultHandler documentationHandler =
                document("{method-name}");

        mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
                .apply(documentationConfiguration(restDocumentation))
                .alwaysDo(documentationHandler)
                .build();
    }

    @Test
    void getBook() throws Exception {
        mockMvc.perform(get("/api/catalog/{id}", "bk-101"))
                .andExpect(status().isOk());
    }
}
~~~

With this configuration, the handler is applied to all requests passing through `mockMvc`, even in tests without `.andDo(...)`. That is convenient for test suites where **every request needs snippets**.

`alwaysDo(...)` also has consequences: helper requests, state-setup requests, or requests intentionally producing error responses are also recorded. If you do not want to document every request, use `andDo(...)` selectively. Specifically, never combine `alwaysDo(documentationHandler)` with `.andDo(documentationHandler)` on the same request, as the handler may run twice and record duplicate operations.

**Important difference in verification order:** a handler registered via `alwaysDo(...)` is invoked automatically by MockMvc during `perform(...)`, before `ResultActions` returns to the test to execute `andExpect(...)`. Thus, snippets may already be written even if assertions written after `perform(...)` fail. If your team requires documentation to be generated only after status/headers/body are verified, use `andDo(handler)` placed after `andExpect(...)` instead of `alwaysDo(handler)`.

## 6. Choosing `andDo(handler)` or `alwaysDo(handler)`?

| Criterion | `andDo(documentationHandler)` | `alwaysDo(documentationHandler)` |
| --- | --- | --- |
| Scope | Only requests where the handler is attached | Every request executed via the configured MockMvc |
| Control | Explicit in each test | Centralized at the builder |
| Best suited for | Tests with setup requests, multi-scenario tests, or selective endpoint documentation | Documentation test suites where nearly every request needs snippets |
| Risk | Might forget to attach the handler in a test | Might unintentionally generate snippets for helper requests |
| Test readability | Documentation point is clearly visible | Shorter tests, though readers must know the shared setup |

A practical rule of thumb:

- Choose **`andDo(handler)`** when you want explicit control over which requests are published.
- Choose **`alwaysDo(handler)`** when every request is documented and identifiers avoid collisions.
- If a single test executes multiple distinct requests, consider separate handlers and explicit `andDo(...)` calls for each request.

## 7. Identifiers: Avoiding Snippet Overwrites

The identifier determines the directory holding the operation's snippets. When reusing a handler, ensure calls write to **distinct paths** if they represent different operations.

Bad example:

~~~java
RestDocumentationResultHandler handler = document("api-operation");
~~~

If this handler is reused for multiple requests with different responses, they all target the `api-operation` directory. Files with the same names can overwrite each other, making build results depend on test execution order.

Placeholders can be used:

~~~java
document("{method-name}");
document("{class-name}/{method-name}");
document("catalog/{method-name}");
~~~

Placeholders like `{method-name}` and `{class-name}` let you construct identifiers from test context. A structured identifier helps group snippets and clarifies the relationship between documentation files and test methods.

When a single method runs multiple operations:

~~~java
@Test
void updateThenReadBook() throws Exception {
    mockMvc.perform(put("/api/books/{id}", "bk-101")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New title\"}"))
            .andExpect(status().isNoContent())
            .andDo(document("books-update"));

    mockMvc.perform(get("/api/books/{id}", "bk-101"))
            .andExpect(status().isOk())
            .andDo(document("books-get-after-update"));
}
~~~

Here each operation needs its own identifier. Using only `{method-name}` for both handlers in the same method would cause both to write into the same directory. Supply specific operation names such as `books-update` and `books-get-after-update`, or adopt an identifier convention combining the method and operation role.

## 8. Reusing Handlers with Data Preprocessing

Handlers are frequently used to standardize how requests/responses are displayed. For instance, formatting all JSON snippets across a test group:

~~~java
RestDocumentationResultHandler jsonDocumentation =
        document(
                "{method-name}",
                preprocessRequest(prettyPrint()),
                preprocessResponse(prettyPrint()));
~~~

Then:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(jsonDocumentation);
~~~

Preprocessing runs on the operation data used to write snippets. It improves file readability without changing what `andExpect(...)` verifies. If sensitive headers or values must be masked in documentation, configure appropriate preprocessors and inspect the generated snippets; never put real credentials into tests or published files.

When multiple endpoints share the same preprocessor but need different descriptors, create separate handlers sharing the same preprocessing rules:

~~~java
RestDocumentationResultHandler bookDocumentation =
        document("{method-name}",
                preprocessResponse(prettyPrint()),
                responseFields(
                        fieldWithPath("id").description("Book ID"),
                        fieldWithPath("title").description("Book title")));

RestDocumentationResultHandler categoryDocumentation =
        document("{method-name}",
                preprocessResponse(prettyPrint()),
                responseFields(
                        fieldWithPath("id").description("Category ID"),
                        fieldWithPath("name").description("Category name")));
~~~

To prevent directory collisions if both handler groups are used in the same test class, partition identifiers by resource, such as `books/{method-name}` and `categories/{method-name}`.

## 9. Organizing Tests and Handlers by API Group

In a large project, standardize conventions at the test-class level:

| Test Group | Recommended Handler | Reason |
| --- | --- | --- |
| One endpoint/operation per test method | One handler using `{method-name}` | Easy to reuse; identifiers automatically stay distinct per method. |
| Multiple endpoints sharing response structure | One shared handler with compatible descriptors | Avoids repeating snippet and preprocessing configuration. |
| Multiple endpoints with differing payloads | Dedicated handler per schema group | Avoids forcing one endpoint's descriptors onto another. |
| Test containing multiple requests | Dedicated handlers attached via `andDo(...)` | Prevents writing different operations to the same identifier. |
| Suite containing only documented requests | `alwaysDo(...)` | Reduces boilerplate and ensures every in-scope request is recorded. |
| Tests with helper requests or undocumented error checks | Selective `andDo(...)` | Records only selected operations. |

Do not create a single module-wide shared handler merely because all tests use MockMvc. Handlers should reflect descriptor scopes and identifier conventions. When response structures change, test groups sharing descriptors may fail together; this signals a need to review the contract and split handlers if actual schemas diverge.

## 10. Where Are Snippets Generated and How Are They Included?

With Gradle:

~~~bash
./gradlew test
~~~

The default directory is usually `build/generated-snippets/`; with Maven, it is usually `target/generated-snippets/`. The actual path also depends on Spring REST Docs and build output settings.

For example, tests with identifiers `getBook` and `createBook` can produce the file tree:

~~~text
build/generated-snippets/
├── getBook/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   └── response-body.adoc
└── createBook/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
~~~

This is an abbreviated example. The exact snippets depend on default snippets, the `Snippet` list passed to `document(...)`, and operation data.

An Asciidoctor page can include the snippets:

~~~adoc
= Catalog API

== Get Book

include::{snippets}/getBook/http-request.adoc[]
include::{snippets}/getBook/http-response.adoc[]

== Create Book

include::{snippets}/createBook/http-request.adoc[]
include::{snippets}/createBook/request-fields.adoc[]
include::{snippets}/createBook/http-response.adoc[]
include::{snippets}/createBook/response-fields.adoc[]
~~~

Directory names in the example must match the identifiers actually generated by the handlers. With placeholders like `{method-name}`, check the actual output to write the correct include paths. If publishing Markdown, a conversion or snippet-embedding step is needed because default snippets are usually in AsciiDoc format.

Build/CI should follow the order **run tests → write snippets → compile documentation → publish**. The compilation task must depend on the test task so stale snippets are never reused.

## 11. Common Errors When Reusing Handlers

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No snippets generated | Handler was created but never attached via `andDo(...)`/`alwaysDo(...)` | Verify whether the request actually invoked the handler. |
| Missing REST Docs context error | `RestDocumentationExtension` not registered or `documentationConfiguration(...)` missing | Provide `RestDocumentationContextProvider`; apply configuration before `build()`. |
| Snippets overwritten | Multiple operations use the same identifier | Use a unique identifier for each operation. |
| Descriptor fails on one endpoint | Shared handler contains fields/headers absent from that endpoint | Split handlers by schema or create separate descriptors. |
| All helper requests get recorded | Handler configured with `alwaysDo(...)` | Switch to selective `andDo(...)` or separate MockMvc/test scopes. |
| Same request generates snippets twice | Both `alwaysDo(handler)` and `andDo(handler)` used | Attach the handler via only one mechanism for that request. |
| Multiple requests in one method write to same folder | Identifier only contains `{method-name}` | Assign operation-specific identifiers within that method. |
| Asciidoctor include cannot find file | Assumed path does not match resolved identifier | Open the output directory and use the actual filenames. |
| Snippet content formatted inconsistently | Missing preprocessor or using handler with different config | Standardize handlers and inspect snippet output. |
| Test fails to document certain fields | Shared descriptor used across responses with different schemas | Split handlers; do not relax descriptors if the API needs strict docs. |

### Lifecycle and Object Sharing Notes

Creating a handler in `@BeforeEach` is easy to understand because each test receives a handler configured with a method-based identifier. You can also store handlers in fields and reuse them when configuration does not depend on per-test data. Either way:

- Do not mutate the identifier or snippet list while tests are running.
- Avoid letting multiple tests write concurrently to the same identifier/directory.
- Do not share a single handler with incompatible descriptors across endpoints with different schemas.
- When using `alwaysDo(...)`, be fully aware that every request through that MockMvc instance passes through the handler.

## 12. Practice Exercises

1. Create a `RestDocumentationResultHandler` in `@BeforeEach` with the `{method-name}` identifier; reuse it across two different GET tests and inspect both snippet directories.
2. Move the handler to `alwaysDo(...)`; run a test containing two requests and observe both operations being recorded. Set appropriate identifiers so they do not collide.
3. Write a test that updates and then reads a resource back; use two handlers or two separate identifiers for the two requests.
4. Reuse the `prettyPrint()` preprocessor across multiple handlers while defining separate descriptors for Book and Category schemas.
5. Intentionally share an identifier across two operations and observe the output issue; fix the naming convention so each operation has its own directory.
6. Include snippets in Asciidoctor, run tests before compiling, and verify the documentation task dependency in CI.

**Completion criteria:** know how to create and use `RestDocumentationResultHandler`; distinguish `andDo(handler)` from `alwaysDo(handler)`; properly reuse descriptors/preprocessors; avoid identifier collisions; compile documentation from output of the current test run.

## 13. Checklist for Using Handlers in a Project

- [ ] MockMvc is integrated via `documentationConfiguration(...)` or the appropriate auto-configuration mechanism.
- [ ] `RestDocumentationResultHandler` is created via `document(identifier, snippets...)`.
- [ ] Handler is attached via `andDo(...)` or `alwaysDo(...)`, without accidentally using both for the same request.
- [ ] Identifiers are distinct per operation, even when a single test method performs multiple requests.
- [ ] Shared descriptors are compatible with every request/response recorded by the handler.
- [ ] Preprocessors are configured consistently and do not expose sensitive data in public snippets.
- [ ] Actual output paths and includes in Asciidoctor/Markdown have been verified.
- [ ] Build/CI generates fresh snippets after tests succeed before compiling/publishing documentation.

**Remember:** `RestDocumentationResultHandler` packages an identifier, snippets, and documentation recording settings into a reusable object. `andDo(handler)` gives per-request control; `alwaysDo(handler)` applies the handler to every MockMvc request. Choosing the right scope, descriptors, and identifiers reduces duplication while still producing clear, collision-free, verifiable REST API documentation.
