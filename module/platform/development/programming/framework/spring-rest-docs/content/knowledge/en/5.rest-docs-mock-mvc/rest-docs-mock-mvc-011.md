# Troubleshooting Missing Snippets or Failing Requests

## 1. Tracing the Pipeline to Find the Root Cause

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. With MockMvc, tests send requests through Spring MVC, verify responses, and write snippets for requests, responses, payloads, parameters, and headers. Snippets are compiled into Asciidoctor/Markdown and integrated into builds and CI. This lesson focuses on diagnosing failures in the MockMvc pipeline.

When a snippet directory is missing or a request fails, the issue can occur at several stages:

~~~text
Test discovery
     |
     v
MockMvc setup + REST Docs configuration
     |
     v
mockMvc.perform(request)
     |
     v
HTTP response
     |
     v
andExpect(status / header / body)
     |
     v
andDo(document(identifier, snippets...))
     |
     v
generated-snippets/<identifier>/
     |
     v
Asciidoctor / Markdown include
~~~

If the test never ran, there is no operation to record. If an assertion before documentation fails, the subsequent `document(...)` call is not executed. If `document` runs with invalid descriptors, Spring REST Docs may throw an error and fail to write all snippets. If snippets exist but documentation fails to compile, the cause may lie in include paths.

Therefore, never assume REST Docs is broken just because files are missing. This lesson helps categorize errors by pipeline stage, inspect logs and responses, fix descriptors, verify identifiers/output paths, and avoid stale snippets in CI.

## 2. Confirming the Test Actually Ran

First, check that the test is discovered and executed:

~~~bash
./gradlew test
~~~

You can filter by class or method:

~~~bash
./gradlew test --tests "com.example.docs.BookDocumentationTest"
./gradlew test --tests "com.example.docs.BookDocumentationTest.getBook"
~~~

With Maven Surefire, projects can typically run a single class via:

~~~bash
mvn -Dtest=BookDocumentationTest test
~~~

Inspect the test report to answer:

- Was the test discovered or excluded by a filter?
- Did the test pass, fail, or get skipped?
- Was an exception thrown in `@BeforeEach` before `mockMvc.perform(...)` ran?
- Did the test reach `andDo(document(...))`?

If a test is skipped or not discovered, Spring REST Docs has no operation to record. Running the wrong task or filter can leave the output directory empty even when dependencies and MockMvc configuration are completely valid.

## 3. Missing Snippets: Checking the Base Configuration

A MockMvc test integrated with Spring REST Docs typically has three parts: JUnit extension, context provider, and builder configuration.

~~~java
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
~~~

Points to verify:

1. The test class registers JUnit Jupiter's `RestDocumentationExtension`, or the integration mechanism appropriate for your test framework.
2. The setup method accepts `RestDocumentationContextProvider` properly.
3. The builder calls `apply(documentationConfiguration(restDocumentation))` before `build()`.
4. The request calls `andDo(document(...))`, or a handler is configured via `alwaysDo(...)`.
5. The `spring-restdocs-mockmvc` dependency is on the test classpath and compatible with Spring Framework/Spring Boot.

When the REST Docs context or builder configuration is missing, errors usually surface during setup or when recording an operation. Read the first exception and root cause in the stack trace rather than only looking at the last line of the error output.

| MockMvc Setup Style | What to Check |
| --- | --- |
| `standaloneSetup(controller)` | Controller was passed in; needed services, advice, converters, validators, or filters are explicitly registered. |
| `webAppContextSetup(context)` | Context is loaded and injected by Spring Test; controller and needed MVC beans exist in the context. |
| Spring Boot auto-configured MockMvc | Annotations/auto-configuration are enabled; test invokes the right MockMvc instance. |

If setup fails, no request is ever sent. Do not investigate `pathParameters(...)` or include files until MockMvc builds successfully.

## 4. Failing Requests: Inspecting the Sent Request and Received Response

When `andExpect(...)` fails, determine whether the request reached the right handler and what the actual response was. You can print the result:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andDo(print())
        .andExpect(status().isOk());
~~~

`print()` displays the request, handler, status, headers, and body in test output. Use dummy data only; logs may contain tokens, cookies, or personal data.

When manual inspection is needed, capture `MvcResult`:

~~~java
MvcResult result = mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andReturn();

int statusCode = result.getResponse().getStatus();
String body = result.getResponse().getContentAsString();
String contentType = result.getResponse().getContentType();
~~~

These values let you compare the actual response against the contract. In day-to-day tests, prefer explicit matchers like `status()`, `header()`, `content()`, and `jsonPath()`.

### Common Status Diagnosis Table

| Result | Common Cause | What to Check |
| --- | --- | --- |
| `404 Not Found` | URL/method does not match mapping or controller not registered | Check URI, mapping, context, or builder. |
| `400 Bad Request` | Missing request parameter, invalid body, binding/validation failure | Check parameters, JSON, data types, validator, and exception handler. |
| `401 Unauthorized` | Missing credentials or security filter rejects request | Check authentication setup and filter chain in MockMvc. |
| `403 Forbidden` | Insufficient permissions or missing CSRF token when required | Check roles, `spring-security-test`, CSRF, and security config. |
| `405 Method Not Allowed` | Wrong HTTP method used for URL | Compare method with controller mapping. |
| `406 Not Acceptable` | `Accept` incompatible with response formats endpoint can produce | Check `accept(...)`, `produces`, and message converters. |
| `415 Unsupported Media Type` | `Content-Type` or body incompatible with `consumes` | Check `contentType(...)`, request body, and converters. |
| `500 Internal Server Error` | Unhandled exception in controller/service | Find root exception, check fake/mock dependencies and advice. |

Not every 4xx status is a test bug. For example, a GET test for a missing ID may **expect 404**. In that case, use `status().isNotFound()` and document the error response under a separate identifier. Treat it as a failure only when the actual status differs from the scenario's expected status.

## 5. Assertions Fail Before `document`: Why Aren't Snippets Generated?

Common chain:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("Spring REST Docs"))
        .andDo(document("books-get"));
~~~

If the status or JSONPath assertion throws an error, execution never reaches `andDo(document(...))`. The `books-get` directory may not exist or may not be updated during this run.

### Checking the Exact Status

If the API specifies POST returns `201 Created`, the matcher must assert that exact status:

~~~java
mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"REST Docs\"}"))
        .andExpect(status().isCreated())
        .andDo(document("books-create"));
~~~

Do not relax the matcher to `is2xxSuccessful()` just to make the test pass when the contract requires 201. Overly broad matchers hide API bugs.

### Checking Headers and Content Type

~~~java
mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"REST Docs\"}"))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andDo(document("books-create"));
~~~

`Accept` is a request header specifying the desired format; the response `Content-Type` tells what the server actually returned. Setting `accept(APPLICATION_JSON)` does not by itself prove the response is JSON.

### Checking the Body

~~~java
.andExpect(jsonPath("$.id").value("bk-102"))
.andExpect(jsonPath("$.title").value("REST Docs"))
~~~

These are matchers chained after `perform(...)`. If the body has a wrong or missing field, fix the endpoint/test data logic or update expected values when the contract genuinely changes. Never delete meaningful assertions just to let snippets be written.

## 6. `document` Ran, Yet Snippets Still Fail

If both the request and assertions pass but the test fails inside `andDo(document(...))`, inspect the Spring REST Docs exception. The most common category is descriptors not matching the operation.

### 6.1. Missing Field in `responseFields`

Actual response:

~~~json
{
  "id": "bk-101",
  "title": "Spring REST Docs",
  "price": 199000
}
~~~

Descriptor missing `price`:

~~~java
responseFields(
        fieldWithPath("id").description("Book ID"),
        fieldWithPath("title").description("Book title"))
~~~

With default strict descriptors, Spring REST Docs reports undocumented fields remaining. If `price` belongs to the public contract, add its descriptor:

~~~java
responseFields(
        fieldWithPath("id").description("Book ID"),
        fieldWithPath("title").description("Book title"),
        fieldWithPath("price").description("List price"))
~~~

Nested fields require exact paths, such as `author.name` or `items[].id`. Compare against the actual JSON received before writing descriptors.

### 6.2. Descriptor Pointing to a Non-Existent Field

If you declare `fieldWithPath("description")` when the response lacks that field, REST Docs also throws an error. Check:

- Is the JSON field name spelled accurately with exact casing?
- Is the field nested inside another object?
- Is the field actually returned in this test scenario?
- Were request fields confused with response fields?

`optional()` is appropriate only when the field may validly be absent. `ignored()` or relaxed snippets can help in intentional cases, but they reduce enforcement against undocumented fields. Do not use them as a blanket workaround for errors.

### 6.3. Path/Query Parameter Descriptor Mismatch

To document path parameters, preserve the URI template:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andDo(document("books-get",
                pathParameters(
                        parameterWithName("id").description("Book ID"))));
~~~

If you write a pre-substituted URL such as `get("/api/books/bk-101")`, Spring REST Docs no longer has the original `id` variable name to associate via the URI template. Similarly, query descriptors must match the actual query parameter name:

~~~java
mockMvc.perform(get("/api/books")
                .queryParam("category", "java"))
        .andDo(document("books-search",
                queryParameters(
                        parameterWithName("category")
                                .description("Category to filter by"))));
~~~

Do not use `param(...)` and assume the query string is represented as intended; use `queryParam(...)` when documenting URL query parameters.

### 6.4. Header Descriptor Mismatch

Before declaring `responseHeaders(...)`, verify the header actually exists:

~~~java
.andExpect(header().string(HttpHeaders.LOCATION, "/api/books/bk-102"))
.andDo(document("books-create",
        responseHeaders(
                headerWithName(HttpHeaders.LOCATION)
                        .description("URI of the newly created resource"))))
~~~

If a header is added by a filter or interceptor not registered in standalone setup, the standalone test will not see the header. Register the required component or switch to `webAppContextSetup(...)` if the goal is testing full application configuration.

## 7. Checking Identifiers, Output Directory, and Stale Files

The identifier in `document("books-get")` determines the root snippet directory. Verify this exact string against include paths:

~~~java
.andDo(document("books-get"));
~~~

~~~adoc
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/http-response.adoc[]
~~~

Common causes of broken paths:

- Test uses `books-get`, while Asciidoctor includes `book-get`.
- Identifier uses `{method-name}` placeholder, while include assumes a fixed directory name.
- Test writes to a custom output directory, while Asciidoctor points to `build/generated-snippets`.
- Test did not run or call the handler, yet an old directory from a previous build remains.
- Included snippet filename is not among the generated or declared snippets.

With Gradle, default output is typically `build/generated-snippets/`; with Maven, `target/generated-snippets/`. Project configuration may override this location.

To eliminate stale files, run clean together with test per your project's build workflow:

~~~bash
./gradlew clean test
~~~

Cleaning removes leftover artifacts from previous runs. Never treat an existing folder as proof that the current test wrote snippets successfully; check the test report, file modification timestamps, and files generated by the current run.

## 8. Special Note on `alwaysDo`

You can configure:

~~~java
mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
        .apply(documentationConfiguration(restDocumentation))
        .alwaysDo(document("{method-name}"))
        .build();
~~~

`alwaysDo(...)` invokes the handler automatically while MockMvc processes `perform(...)`, before the `ResultActions` chain runs `andExpect(...)` matchers. Therefore, snippets may still be written even if a subsequent assertion fails.

If your team wants documentation generated only after status/headers/body are verified, use:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value("bk-101"))
        .andDo(documentationHandler);
~~~

Never configure the same handler via `alwaysDo(...)` and also call `andDo(handler)` on the same request; that can cause duplicate writes. When diagnosing a failing test's snippets, check which mechanism attaches the handler.

## 9. Distinguishing Test Failures from Documentation Build Failures

| State | Symptom | Action |
| --- | --- | --- |
| Test fails before `document` | Status/header/body assertion failure or request exception | Fix request/endpoint/expected result per contract; subsequent `document` likely never ran. |
| Test fails during `document` | Spring REST Docs exception such as descriptor mismatch or preprocessor error | Check identifier, snippets, field paths, parameters, headers, and preprocessors. |
| Test generates snippets successfully but docs fail | Asciidoctor cannot find include or Markdown has not converted snippets | Check output path, `{snippets}`, identifier, filenames, and task dependencies. |

A missing include file is not necessarily a controller bug. Conversely, a passing Asciidoctor build does not prove the API is right if documentation tests lack proper assertions.

## 10. Example: Query Descriptor Mismatching Request

Suppose a test sends a query parameter named `lang`, while the descriptor specifies `language`:

~~~java
// Wrong: request sends "lang", but descriptor documents "language".
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .queryParam("lang", "vi"))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                queryParameters(
                        parameterWithName("language")
                                .description("Language"))));
~~~

If the controller ignores unknown query parameters, the request may still return 200. However, REST Docs cannot treat `language` as a parameter that actually appeared. Fix it to match the real contract:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .queryParam("language", "vi"))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                pathParameters(
                        parameterWithName("id").description("Book ID")),
                queryParameters(
                        parameterWithName("language")
                                .description("Response language"))));
~~~

If the API does not support that query parameter, remove both the query parameter and the descriptor. Never add fake parameters just to generate snippets.

## 11. Systematic Diagnostic Workflow

When an error occurs, go step by step:

1. **Check the test report:** was the test discovered and executed?
2. **Check setup:** was MockMvc built; are the extension and `documentationConfiguration(...)` active?
3. **Print request/response:** use `andDo(print())` or `MvcResult` to inspect the sent request, selected handler, and received response.
4. **Read the first failing assertion:** status, header, or body? Fix according to the API contract instead of unnecessarily loosening matchers.
5. **Check `document`:** did the handler run? Does the exception mention a field, parameter, header, operation, or preprocessor?
6. **Check output files:** were the identifier, output directory, and specific snippets created in this run?
7. **Check compilation:** do `{snippets}` and include paths match the actual files?
8. **Run a clean build when needed:** clear stale artifacts and regenerate snippets and documentation via proper task dependencies.

| Question | If No | If Yes |
| --- | --- | --- |
| Did the test run? | Fix test discovery/filter/task | Check setup |
| Did MockMvc setup succeed? | Check context, extension, builder | Check request |
| Did the response pass assertions? | Print response and fix HTTP cause | Check `document` |
| Did `document` run without exceptions? | Check descriptors and preprocessors | Check output files |
| Do new snippet folders/files exist? | Check identifier and output directory | Check Asciidoctor/Markdown |
| Do includes point to the right files? | Fix `{snippets}` or include names | Check build/publish |

## 12. Integrating Verification into Build and CI

A reliable CI pipeline must generate fresh snippets before compiling documentation:

~~~text
checkout source
     |
     v
clean generated output
     |
     v
run MockMvc documentation tests
     |
     +-- failed -> stop pipeline
     |
     v
verify expected snippets / assemble docs
     |
     +-- missing include -> stop pipeline
     |
     v
publish documentation artifact
~~~

Key principles to maintain:

- Documentation compilation depends on the snippet-generating test step.
- Test failures or snippet descriptor failures must halt the pipeline.
- Stale output must never be mistaken for fresh output from the current run.
- You can add a check for required snippet files or let Asciidoctor fail on missing includes.
- Never publish snippets containing tokens, cookies, customer data, or environment secrets.

Default Spring REST Docs snippets are usually in AsciiDoc format. If your product uses Markdown, a proper conversion or embedding step is required; do not assume `.adoc` files can be included as-is into a Markdown renderer.

## 13. Practice Exercises

1. Remove `.apply(documentationConfiguration(restDocumentation))`, run the test, and determine whether the error occurs at setup or when writing snippets.
2. Change the expected status from `isCreated()` to `isOk()` in a POST test, then examine why the test fails against the 201 contract.
3. Add a `currency` JSON field without adding its descriptor; observe the strict `responseFields(...)` failure and then update the description.
4. Change the identifier from `books-get` to `book-get` while leaving the include unchanged; identify the step reporting the missing file and align both.
5. Create a test that intentionally fails in `andExpect(...)` before `andDo(document(...))`; check whether the handler is called. Then try `alwaysDo(...)` and compare.
6. Run a clean test and compile documentation; verify snippets come from the fresh run rather than leftover artifacts.

**Completion criteria:** accurately pinpoint the failing layer, read logs/responses to find root causes, fix matchers or descriptors per the real contract, verify identifiers/outputs/includes, and ensure CI halts when tests or documentation compilation fail.

## 14. Troubleshooting Checklist

- [ ] Test is actually discovered and executed under the current task/filter.
- [ ] MockMvc has REST Docs configured properly and setup completed.
- [ ] Actual sent request, matched handler, status, headers, and body were inspected.
- [ ] Assertion failures are distinguished from errors inside `document(...)`.
- [ ] Field/parameter/header descriptors match the actual operation.
- [ ] Identifiers and output directory match Asciidoctor/Markdown paths.
- [ ] Stale snippet artifacts have been eliminated when needed.
- [ ] `alwaysDo(...)` does not write unintended documentation; prefer `andDo(...)` after assertions when that condition is required.
- [ ] Build/CI generates snippets before compiling, and stops when tests or includes fail.

**Remember:** When snippets are missing, trace the pipeline from test discovery through request execution, assertions, `document(...)`, output files, and includes. Pinpointing the exact failing stage lets you fix the true cause, keep meaningful assertions intact, and ensure REST API documentation reflects verified requests and responses.
