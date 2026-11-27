# Performing Requests with MockMvc

## 1. Lesson Objectives

In Spring MVC, **MockMvc** lets you send simulated HTTP requests to `DispatcherServlet` and inspect responses without starting a real HTTP server. This is an essential way to test controllers, URL mappings, content types, headers, parameters, bodies, and status codes.

With **Spring REST Docs**, requests executed in tests also serve as the data source for generating verifiable **snippets**: HTTP requests/responses, `curl` examples, JSON payloads, path/query parameters, form parameters, request parts, and request/response headers. Those snippets are then included in Asciidoctor/Markdown documentation and the build/CI pipeline. The same mechanism can also be applied via WebTestClient or REST Assured; this lesson focuses on **MockMvc**.

After completing this lesson, you will be able to:

- Build HTTP GET, POST, PUT, PATCH, and DELETE requests using `MockMvcRequestBuilders`.
- Supply URI templates, query/form parameters, headers, cookies, sessions, JSON bodies, and multipart payloads.
- Distinguish between request builders, `mockMvc.perform(...)`, `andExpect(...)`, `andDo(...)`, and `andReturn()`.
- Generate Spring REST Docs snippets from executed and verified requests.
- Identify common errors when tests use incorrect URLs, `Content-Type`, `Accept`, payloads, or descriptors.

## 2. Execution Flow: From Request Builder to Snippet

A MockMvc request typically has the following structure:

```java
mockMvc.perform(get("/api/tasks/{id}", "task-100")
                .queryParam("includeDetails", "true")
                .header("X-Correlation-Id", "req-001")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value("task-100"))
        .andDo(document("tasks-get-basic"));
```

| Component | Purpose |
| --- | --- |
| `get(...)`, `post(...)`, `put(...)`, `patch(...)`, `delete(...)` | Creates a `MockHttpServletRequestBuilder` representing the HTTP method, URI, and request data to send. |
| `mockMvc.perform(builder)` | Executes the request through the configured Spring MVC pipeline and returns `ResultActions`. |
| `andExpect(resultMatcher)` | Verifies response properties such as status, headers, content type, and JSON fields; a failing assertion fails the test. |
| `andDo(resultHandler)` | Performs an action after the request, such as `print()` or Spring REST Docs `document(...)`. |
| `andReturn()` | Retrieves the `MvcResult` for additional inspection of the processed request/response; usually unnecessary when matchers suffice. |

```text
MockMvcRequestBuilders.get/post/put/...
         |
         +-- URI template, query/form params, headers, cookies, body
         |
         v
    mockMvc.perform(...)
         |
         v
  DispatcherServlet (in test)
         |
         v
    Simulated HTTP response
         |
         +-- andExpect(...): verify behavior
         |
         +-- andDo(document(...)): write snippets to generated-snippets
         |
         +-- andReturn(): obtain MvcResult (if needed)
```

**Note:** `MockMvc` does not use the network when processing normal requests. It runs requests through simulated servlet/MVC infrastructure within the same test process. Results are valid within the scope of the controllers, beans, filters, and components configured for that specific test.

## 3. Setting Up MockMvc with Spring REST Docs

The examples use **Java 17+, Spring MVC, Spring Boot 3.x, JUnit Jupiter**, and Gradle. If you use Spring Boot dependency management, compatible dependency versions should be managed through the project's BOM.

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

For an independent controller, configuration can be done in `@BeforeEach`:

```java
@ExtendWith(RestDocumentationExtension.class)
class TaskRequestDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new TaskController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

The types and methods are imported from `org.junit.jupiter.api`, `org.springframework.restdocs`, `org.springframework.test.web.servlet`, and the static import `MockMvcRestDocumentation.documentationConfiguration`. `RestDocumentationExtension` provides the test context for Spring REST Docs. If the controller requires specific services, converters, advice, or filters, add them to the builder according to the test scope or use `webAppContextSetup(context)` to pull MVC configuration from the web application context.

`documentationConfiguration(restDocumentation)` **configures the documentation recorder**; it does not automatically record every request. To record a specific request into snippets, use `.andDo(document(...))`, and verify the response before recording.

## 4. Complete Example: Documented GET, POST, and DELETE

Suppose a task management API has three endpoints:

- `GET /api/tasks/{id}?includeDetails=true`: retrieves a task, reading path/query parameters and a correlation header.
- `POST /api/tasks`: accepts JSON containing `title`, creates a task, and returns `201 Created`.
- `DELETE /api/tasks/{id}`: deletes a task and returns `204 No Content`.

The test class below defines a sample controller right inside the test to clearly demonstrate request construction and snippet generation. In a real project, use your application's controller and appropriate test data.

```java
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
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
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class TaskRequestDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new TaskController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetTask() throws Exception {
        mockMvc.perform(get("/api/tasks/{id}", "task-100")
                        .queryParam("includeDetails", "true")
                        .accept(MediaType.APPLICATION_JSON)
                        .header("X-Correlation-Id", "req-001"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string("X-Correlation-Id", "req-001"))
                .andExpect(jsonPath("$.id").value("task-100"))
                .andExpect(jsonPath("$.details").value("Additional details included"))
                .andDo(document("tasks-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Task ID")),
                        queryParameters(
                                parameterWithName("includeDetails")
                                        .description("Whether to include details")),
                        requestHeaders(
                                headerWithName("Accept")
                                        .description("Desired response format"),
                                headerWithName("X-Correlation-Id")
                                        .description("Request trace ID")),
                        responseHeaders(
                                headerWithName("X-Correlation-Id")
                                        .description("Response trace ID")),
                        responseFields(
                                fieldWithPath("id").description("Task ID"),
                                fieldWithPath("title").description("Task title"),
                                fieldWithPath("state").description("Task state"),
                                fieldWithPath("details")
                                        .description("Additional information"))));
    }

    @Test
    void documentCreateTask() throws Exception {
        mockMvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Write API documentation"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/tasks/task-101"))
                .andExpect(jsonPath("$.id").value("task-101"))
                .andExpect(jsonPath("$.title").value("Write API documentation"))
                .andDo(document("tasks-create",
                        requestFields(
                                fieldWithPath("title")
                                        .description("Title of the task to create")),
                        responseHeaders(
                                headerWithName("Location")
                                        .description("URL of the newly created resource")),
                        responseFields(
                                fieldWithPath("id").description("New task ID"),
                                fieldWithPath("title").description("Task title"),
                                fieldWithPath("state").description("Task state"))));
    }

    @Test
    void documentDeleteTask() throws Exception {
        mockMvc.perform(delete("/api/tasks/{id}", "task-101"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andDo(document("tasks-delete",
                        pathParameters(
                                parameterWithName("id")
                                        .description("ID of the task to delete"))));
    }

    @RestController
    public static class TaskController {

        @GetMapping(value = "/api/tasks/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> find(
                @PathVariable("id") String id,
                @RequestParam("includeDetails") boolean includeDetails,
                @RequestHeader("X-Correlation-Id") String correlationId) {

            Map<String, Object> task = new LinkedHashMap<>();
            task.put("id", id);
            task.put("title", "Learn MockMvc");
            task.put("state", "OPEN");
            if (includeDetails) {
                task.put("details", "Additional details included");
            }
            return ResponseEntity.ok()
                    .header("X-Correlation-Id", correlationId)
                    .body(task);
        }

        @PostMapping(value = "/api/tasks",
                     consumes = MediaType.APPLICATION_JSON_VALUE,
                     produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, String>> create(
                @RequestBody Map<String, String> request) {
            return ResponseEntity.created(URI.create("/api/tasks/task-101"))
                    .body(Map.of(
                            "id", "task-101",
                            "title", request.get("title"),
                            "state", "OPEN"));
        }

        @DeleteMapping("/api/tasks/{id}")
        public ResponseEntity<Void> deleteById(@PathVariable("id") String id) {
            return ResponseEntity.noContent().build();
        }
    }
}
```

### Result Analysis

1. **GET Request:** `get("/api/tasks/{id}", "task-100")` places the `id` name into the URI template and substitutes the actual value. `queryParam("includeDetails", "true")` appends the query parameter to the URL, `accept(...)` sets the `Accept` header, and `header(...)` sets the trace header. The corresponding descriptors extract the exact information from the request.
2. **POST Request:** `contentType(...)` informs the controller how to parse the body; `content(...)` passes the actual JSON string. `requestFields(...)` describes the `title` field, while `responseFields(...)` describes the returned JSON. The `Location` header is verified and documented.
3. **DELETE Request:** because the `204` response has no payload, the test verifies an empty body and documents only the path parameter; it does not declare `responseFields(...)` for a non-existent JSON body.
4. **Verified results:** `andExpect(...)` runs after `perform(...)` and before `andDo(document(...))`. If an assertion fails, the call chain normally stops at that assertion and the test fails.
5. **Snippets separated by operation:** `tasks-get`, `tasks-create`, and `tasks-delete` are independent identifiers. Each documentation call creates or updates the snippets for its corresponding request.

The controller in this example always returns deterministic data so we can focus on building requests. Separate tests must verify real services, databases, validation, or security if those are critical parts of the API's behavior.

## 5. Mastering URI Templates, Query Parameters, and Form Parameters

### URI Templates and Path Parameters

Prefer passing **the template along with replacement values** when documenting path variables:

```java
get("/api/tasks/{id}", "task-100")
get("/api/teams/{teamId}/tasks/{taskId}", "team-01", "task-100")
```

This retains the variable names so Spring REST Docs generates `path-parameters.adoc` accurately:

```java
pathParameters(
        parameterWithName("teamId").description("Team ID"),
        parameterWithName("taskId").description("Task ID"))
```

If you only pass an already-expanded URL string like `get("/api/tasks/task-100")`, the path parameter recorder may not know the original variable was named `id`. Do not pass arbitrary values and then describe a variable name that is no longer in the template.

### Query Parameters

For GET/DELETE or requests with URL query parameters, use:

```java
mockMvc.perform(get("/api/tasks")
        .queryParam("state", "OPEN")
        .queryParam("page", "0")
        .queryParam("tag", "spring", "rest-docs"));
```

`queryParam(...)` reflects values in the **query string** and is ideal when using Spring REST Docs' `queryParameters(...)`:

```java
queryParameters(
        parameterWithName("state").description("Filter by state"),
        parameterWithName("page").description("Zero-based page index"),
        parameterWithName("tag").description("Tags, repeatable"))
```

`param(...)` also sets request parameters in MockMvc and is commonly used to simulate form data or bind to `@RequestParam`. However, when the goal is **documenting the query string**, use `queryParam(...)` so the query appears clearly in the snippet URL. This is important because query parameters and form parameters are categorized differently in modern Spring REST Docs.

### URL-Encoded Forms

Standard HTML forms send name/value pairs with `application/x-www-form-urlencoded`:

```java
mockMvc.perform(post("/api/subscriptions")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "reader@example.com")
        .param("topic", "java", "spring"));
```

The controller can receive `@RequestParam("email")` and `@RequestParam("topic")`. When writing form documentation, use `formParameters(...)` with appropriate descriptors instead of declaring JSON fields with `requestFields(...)`. To ensure the body representation matches a real client, you can also send an explicitly URL-encoded body, such as `email=reader%40example.com&topic=java`.

## 6. Headers, Content Types, Cookies, Sessions, and Authentication Data

### Headers and Content Negotiation

```java
mockMvc.perform(post("/api/tasks")
        .header("X-Correlation-Id", "req-002")
        .accept(MediaType.APPLICATION_JSON)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Read documentation\"}"));
```

- `Accept` specifies **the response format the client expects**. The server may return `406 Not Acceptable` if it cannot satisfy it.
- `Content-Type` specifies **the format of the request body sent**. A controller with an incompatible `consumes` attribute may return `415 Unsupported Media Type`.
- `header(name, values...)` adds standard headers such as `Authorization`, `If-Match`, or trace IDs; document meaningful headers using `requestHeaders(...)`.
- `characterEncoding("UTF-8")` sets the request encoding when explicit control over character decoding is needed. For UTF-8 JSON, use a consistent encoding and content type.

A request with an `Authorization` header in MockMvc does not mean security has been tested. If the endpoint uses Spring Security, integrate the proper filter chain or security test configuration; a dummy token with an arbitrary value might simply be an unverified header.

### Cookies and Sessions

```java
import jakarta.servlet.http.Cookie;

mockMvc.perform(get("/api/profile")
        .cookie(new Cookie("theme", "dark"))
        .sessionAttr("selectedTab", "overview"));
```

`cookie(...)` sends a cookie; `sessionAttr(...)` provides a session attribute for the request in the test. These values only have an effect if the controller, interceptor, or filter actually reads them. When documenting cookies, use the corresponding Spring REST Docs snippet descriptors; do not confuse request cookies with headers or JSON bodies.

### Multi-Value Parameters

```java
get("/api/tasks")
    .queryParam("tag", "spring", "mockmvc")
    .queryParam("state", "OPEN")
```

A single query parameter name can appear multiple times. Controllers typically bind this to `List<String>`, an array, or a compatible type depending on binding configuration. Tests should include assertions for multi-value handling, especially when endpoints perform filtering and pagination.

## 7. PUT, PATCH, Multipart, and Request Bodies

Beyond GET, POST, and DELETE, other methods can be built using the same principles:

```java
mockMvc.perform(put("/api/tasks/{id}", "task-100")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Rename task\",\"state\":\"DONE\"}"));

mockMvc.perform(patch("/api/tasks/{id}", "task-100")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"state\":\"DONE\"}"));
```

These two snippets are request-sending examples without assertions or `document(...)`. `PUT` is typically used by APIs to replace resource state; `PATCH` is used for partial updates. The exact semantics depend on the API contract. If `PATCH` accepts a specialized patch format such as `application/merge-patch+json`, set `Content-Type` to the designed media type.

### Multipart Requests

Upload files using `MockMultipartFile`:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

MockMultipartFile file = new MockMultipartFile(
        "file",
        "guide.txt",
        "text/plain",
        "Sample content".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/attachments")
        .file(file)
        .param("category", "docs"));
```

`multipart(...)` builds a `multipart/form-data` POST request by default, where `file` is the part name. The corresponding controller can use `@RequestPart("file") MultipartFile file` or `@RequestParam("file") MultipartFile file` depending on the contract. With Spring REST Docs, document the file using `requestParts(partWithName("file").description(...))`; if a part carries JSON, you can document the part's payload using the snippets supporting request part payloads.

Do not use `requestFields(...)` to describe raw file bytes as if they were a regular JSON property. For multipart requests that also include text fields like `category`, distinguish between form parameters and multipart parts according to how the API actually receives the data.

## 8. Verifying Responses for Meaningful Documentation

Common assertions:

```java
.andExpect(status().isOk())
.andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
.andExpect(jsonPath("$.id").value("task-100"))
.andExpect(jsonPath("$.state").value("OPEN"))
.andExpect(header().string("X-Correlation-Id", "req-001"))
```

These are **chained methods** in the `perform(...)` call, not standalone Java statements. When the response is JSON whose field order may vary, verify important values with `jsonPath(...)` instead of comparing the entire JSON string verbatim.

When you need to inspect the request/response for troubleshooting:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/tasks/{id}", "task-100")
        .queryParam("includeDetails", "true")
        .header("X-Correlation-Id", "req-001"))
    .andDo(print())
    .andExpect(status().isOk());
```

`print()` is useful when debugging, but it can output sensitive bodies and headers to test logs; use it appropriately with test data. When you want to read the result directly:

```java
MvcResult result = mockMvc.perform(get("/api/tasks/{id}", "task-100")
                .queryParam("includeDetails", "true")
                .header("X-Correlation-Id", "req-001"))
        .andExpect(status().isOk())
        .andReturn();

String responseBody = result.getResponse().getContentAsString();
int httpStatus = result.getResponse().getStatus();
```

`MvcResult` is in `org.springframework.test.web.servlet.MvcResult`. Retrieving the result this way is useful for specialized checks; for ordinary cases, built-in matchers are clearer and easier to maintain.

## 9. Generating Spring REST Docs Snippets from Actual Requests

`document(...)` attaches to `ResultActions` just like `print()`, except its purpose is to record the operation under an identifier:

```java
mockMvc.perform(get("/api/tasks/{id}", "task-100")
                .queryParam("includeDetails", "true")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Correlation-Id", "req-001"))
        .andExpect(status().isOk())
        .andDo(document("tasks-get",
                pathParameters(
                        parameterWithName("id").description("Task ID")),
                queryParameters(
                        parameterWithName("includeDetails")
                                .description("Request additional details")),
                requestHeaders(
                        headerWithName("Accept").description("Response format"),
                        headerWithName("X-Correlation-Id")
                                .description("Trace ID")),
                responseFields(
                        fieldWithPath("id").description("ID"),
                        fieldWithPath("title").description("Title"),
                        fieldWithPath("state").description("State"),
                        fieldWithPath("details").description("Details"))));
```

This is a condensed version of the GET test in section 4; use a MockMvc configuration with Spring REST Docs enabled. Descriptors act as a **documentation contract**: if parameter names or JSON fields do not match, Spring REST Docs can fail the test instead of producing inaccurate documentation.

Commonly generated snippets:

| Snippet | Data Source |
| --- | --- |
| `http-request.adoc`, `http-response.adoc` | HTTP request and response in the test. |
| `curl-request.adoc`, `httpie-request.adoc` | Example client commands to call the API, depending on default snippets. |
| `path-parameters.adoc` | `pathParameters(...)` for URI templates. |
| `query-parameters.adoc` | `queryParameters(...)` for query parameters. |
| `form-parameters.adoc` | `formParameters(...)` for submitted forms. |
| `request-headers.adoc`, `response-headers.adoc` | `requestHeaders(...)` and `responseHeaders(...)`. |
| `request-fields.adoc`, `response-fields.adoc` | `requestFields(...)` and `responseFields(...)` for structured payloads. |
| `request-parts.adoc` | `requestParts(...)` for multipart requests. |

After `./gradlew test`, using Gradle's default output, files will be located in `build/generated-snippets/tasks-get/`. With Maven, the location is usually `target/generated-snippets/`. The exact file list depends on snippet generation configuration and Spring REST Docs version.

Example Asciidoctor page using the generated output:

```adoc
= Tasks API

== Get Task

include::{snippets}/tasks-get/http-request.adoc[]
include::{snippets}/tasks-get/path-parameters.adoc[]
include::{snippets}/tasks-get/query-parameters.adoc[]
include::{snippets}/tasks-get/request-headers.adoc[]
include::{snippets}/tasks-get/http-response.adoc[]
include::{snippets}/tasks-get/response-fields.adoc[]

== Create Task

include::{snippets}/tasks-create/request-fields.adoc[]
include::{snippets}/tasks-create/http-response.adoc[]
include::{snippets}/tasks-create/response-headers.adoc[]
```

`{snippets}` must point to the snippet output directory in the compilation task. When the output is Markdown, you can embed/transform snippets using the build mechanism configured in your project. Build/CI should connect **tests generating snippets → documentation compilation → publishing** via task dependencies so documentation from stale snippets is never published.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Receiving `404 Not Found` | URI/method does not match `@RequestMapping` or controller is not registered | Check method, URI template, and MockMvc configuration source. |
| Receiving `400 Bad Request` | Missing required `@RequestParam`, unparseable body, or invalid data | Check `queryParam`/`param`, data types, and actual JSON sent. |
| Receiving `415 Unsupported Media Type` | Body sent without a `Content-Type` compatible with `consumes` | Set appropriate `contentType(...)`; check JSON converter. |
| Receiving `406 Not Acceptable` | `Accept` does not match `produces` or converter | Compare `accept(...)`, controller configuration, and converters. |
| Unexpected `401`/`403` | Security/filter or CSRF in test scope is not properly configured | Set up authentication/CSRF and security filter chain per API contract. |
| Query data does not appear in snippets as expected | Used `param(...)` when intending to represent a URL query | Use `queryParam(...)` for query data and `queryParameters(...)` accordingly. |
| `pathParameters(...)` fails | Used an already-substituted URL without preserving variable names | Use `get("/api/tasks/{id}", value)`. |
| `requestFields(...)` reports missing field | JSON body differs from descriptor or wrong content type | Compare actual body, update documented fields, check optional/ignored if matching API. |
| No `generated-snippets` directory | REST Docs not configured, missing `document(...)`, or test failed to pass | Check extension, `documentationConfiguration`, `andDo(document(...))`, and test report. |
| Documentation shows `localhost` instead of public host | REST Docs display URI not configured | Use `documentationConfiguration(...).uris().withScheme(...).withHost(...).withPort(...)`. |

When errors occur, start from the actual request constructed and the actual response received. Proper assertions on status, headers, and payload help distinguish API bugs from snippet descriptor mismatches.

## 11. Reinforcement Exercises

1. Add `GET /api/tasks` with `state=OPEN&page=0`; write a test using `queryParam`, verify the JSON list, and generate `queryParameters(...)`.
2. Add `PUT /api/tasks/{id}` accepting JSON with `title` and `state`; verify the response and document request/response fields.
3. Add a `POST /api/subscriptions` form with `application/x-www-form-urlencoded`; verify how the request receives `param(...)` and generate the `formParameters(...)` snippet.
4. Add multipart upload for `POST /api/attachments`; verify status, filename, and document the `file` part with `requestParts(...)`.
5. Run the tests, inspect the snippets directory, include them into Asciidoctor or Markdown, and ensure CI does not compile documentation before tests finish.

**Completion criteria:** requests are built with the correct method, path, query, headers, and body; assertions verify the HTTP response; each published request generates snippets with a stable identifier; documentation builds cleanly from the latest snippets.

## 12. Checklist When Writing MockMvc Requests

- [ ] Choose the right request builder for the HTTP method.
- [ ] Preserve the URI template when documenting path parameters; use `queryParam(...)` for URL queries.
- [ ] Set `Content-Type` when sending a body; set `Accept` when controlling response format.
- [ ] Verify headers, cookies, sessions, and authentication/filters if they affect API behavior.
- [ ] Verify status, content type, and payload with appropriate matchers before recording documentation.
- [ ] Use `andDo(document(...))` and descriptors consistent with the actual request/response.
- [ ] Inspect generated snippets and run tests in build/CI before compiling Asciidoctor/Markdown.

**Remember:** `MockMvcRequestBuilders` defines **the request to send**; `mockMvc.perform(...)` executes the request through Spring MVC; `andExpect(...)` confirms **real behavior within the test scope**; `andDo(document(...))` turns the HTTP result into snippets. This enables REST API documentation to be generated, verified, and updated alongside the source code.
