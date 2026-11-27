# MockMvc `standaloneSetup` and Context Limitations

## 1. Why Use `standaloneSetup`?

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests using **MockMvc**, WebTestClient, or REST Assured. Each request executed and verified in a test can produce **snippets** for the request, response, JSON payload, parameters, and headers. These snippets are included into Asciidoctor/Markdown documentation and can be regenerated during builds and CI.

In the **MockMvc** chapter, `MockMvcBuilders.standaloneSetup(...)` allows creating MockMvc directly from one or more controllers **without starting the application's `WebApplicationContext`**. This approach is useful when you want to:

- Write fast documentation tests focusing solely on a controller's HTTP contract.
- Pass mock dependencies or deterministic data so snippets remain stable.
- Explicitly add only the MVC components that the controller actually needs.
- Isolate issues in request mapping, response formatting, and REST Docs descriptors.

Minimal initialization example:

```java
TaskService service = new FakeTaskService();
TaskController controller = new TaskController(service);

MockMvc mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .build();
```

MockMvc still simulates the **Spring MVC** HTTP processing pipeline using `DispatcherServlet` and the MVC components created or configured by the builder. However, the beans and controller in the example are **provided directly by the test**, rather than obtained through the application's component scanning or dependency injection.

This is also a limitation to understand clearly: a passing standalone test does not prove that the entire Spring Boot application, filters, security chain, JSON configuration, and other beans work properly in a real runtime environment.

## 2. How It Works and Simulation Scope

```text
JUnit Jupiter Test
    |
    +-- new TaskController(fakeService)
    |
    +-- MockMvcBuilders.standaloneSetup(controller)
    |       +-- prepares minimal MVC infrastructure automatically
    |       +-- registers optional advice / converter / validator
    |       +-- applies documentationConfiguration(...)
    |       +-- build()
    |
    +-- mockMvc.perform(...)
            +-- DispatcherServlet simulates request
            +-- andExpect(...): verify status / headers / body
            +-- andDo(document(...)): write snippets
```

Comparing the two ways to build MockMvc:

| Aspect | `standaloneSetup(controller)` | `webAppContextSetup(context)` |
| --- | --- | --- |
| Controller source | Object supplied directly | Beans and MVC mappings from `WebApplicationContext` |
| Starting Spring application context | Not required | Requires a web context loaded by Spring Test |
| Dependency injection | Test passes via constructor/setter | Spring manages beans according to test configuration |
| Custom MVC converters, validators, advice | Must be explicitly registered to reproduce custom setup | Inherits MVC components present in the context |
| Filters and Spring Security | Must be explicitly integrated; does not auto-load app filter chain | Can integrate filters/security matching the context |
| Speed and isolation | Usually fast and easy to control | Usually incurs context loading cost, closer to integrated setup |
| Evidence provided by test | Controller handles requests correctly in the constructed setup | Controller handles requests correctly in the MVC context loaded by the test |

**Selection rule:** use `standaloneSetup` when the focus is the HTTP contract of a single controller with controllable dependencies. If you need to verify application-wide `@ControllerAdvice`, complex Jackson configuration, custom converters, filters, or real access control, consider `webAppContextSetup` or Spring Boot's auto-configured MockMvc.

## 3. Project Setup

The lesson examples use **Java 17+, Spring Boot 3.x, Spring MVC, JUnit Jupiter 5**, and Gradle:

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

`spring-boot-starter-web` brings Spring MVC and Jackson into the application; `spring-boot-starter-test` provides Spring Test, MockMvc, and JUnit Jupiter; `spring-restdocs-mockmvc` provides snippet generation integration for MockMvc. For projects using Spring Boot dependency management, use the compatible Spring REST Docs version managed by the BOM. Projects not using the BOM must declare a specific version compatible with the Spring Framework in use.

To document requests, MockMvc must have Spring REST Docs configuration applied:

```java
@ExtendWith(RestDocumentationExtension.class)
class TaskControllerDocsTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new TaskController(new FakeTaskService()))
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

In this abbreviated snippet, import the corresponding classes from `org.junit.jupiter.api`, `org.springframework.restdocs`, `org.springframework.test.web.servlet`, and the two static methods from `MockMvcRestDocumentation`. `RestDocumentationExtension` supplies `RestDocumentationContextProvider` to `@BeforeEach`. `documentationConfiguration(...)` must be applied **before `build()`**. The initialization step itself does not generate snippets; requests must be recorded via `andDo(document(...))`.

## 4. Complete Example: Task Controller with a Fake Dependency

Suppose a task management system has three behaviors:

1. `GET /api/tasks/{id}` returns an existing task and the `X-Trace-Id` header.
2. `POST /api/tasks` accepts JSON containing `title` and returns `201 Created` with a `Location` header.
3. When a task is not found, the API returns `404` with a consistent error JSON.

The test below creates the controller and a fake service directly in the test, and additionally registers `@RestControllerAdvice` and a JSON converter. There is no need to run the full application to generate documentation for these three cases.

```java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class TaskControllerDocsTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        TaskService service = new FakeTaskService();

        mockMvc = MockMvcBuilders.standaloneSetup(new TaskController(service))
                .setControllerAdvice(new TaskErrorAdvice())
                .setMessageConverters(new MappingJackson2HttpMessageConverter())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetTask() throws Exception {
        mockMvc.perform(get("/api/tasks/{id}", "t-001")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Trace-Id", "trace-docs-001"))
                .andExpect(jsonPath("$.id").value("t-001"))
                .andExpect(jsonPath("$.state").value("OPEN"))
                .andDo(document("tasks-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Task ID to retrieve")),
                        requestHeaders(
                                headerWithName("Accept")
                                        .description("Desired response format")),
                        responseHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Trace ID of the response")),
                        responseFields(
                                fieldWithPath("id").description("Task ID"),
                                fieldWithPath("title").description("Task title"),
                                fieldWithPath("state").description("Task state"))));
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
                .andExpect(header().string("Location", "/api/tasks/t-002"))
                .andExpect(jsonPath("$.title").value("Write API documentation"))
                .andDo(document("tasks-create",
                        requestFields(
                                fieldWithPath("title")
                                        .description("Title of the task to create")),
                        responseHeaders(
                                headerWithName("Location")
                                        .description("Path to the newly created task")),
                        responseFields(
                                fieldWithPath("id").description("New task ID"),
                                fieldWithPath("title").description("Task title"),
                                fieldWithPath("state").description("Task state"))));
    }

    @Test
    void documentTaskNotFound() throws Exception {
        mockMvc.perform(get("/api/tasks/{id}", "missing")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("TASK_NOT_FOUND"))
                .andDo(document("tasks-get-not-found",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Requested task ID")),
                        responseFields(
                                fieldWithPath("error").description("Error code"),
                                fieldWithPath("message").description("Error details"))));
    }

    interface TaskService {
        Map<String, String> find(String id);
        Map<String, String> create(String title);
    }

    static class FakeTaskService implements TaskService {
        @Override
        public Map<String, String> find(String id) {
            if (!"t-001".equals(id)) {
                throw new TaskMissingException(id);
            }
            return Map.of(
                    "id", id,
                    "title", "Test API",
                    "state", "OPEN");
        }

        @Override
        public Map<String, String> create(String title) {
            return Map.of(
                    "id", "t-002",
                    "title", title,
                    "state", "OPEN");
        }
    }

    public static class TaskMissingException extends RuntimeException {
        TaskMissingException(String id) {
            super("Task not found: " + id);
        }
    }

    @RestController
    public static class TaskController {
        private final TaskService service;

        TaskController(TaskService service) {
            this.service = service;
        }

        @GetMapping(value = "/api/tasks/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, String>> getTask(
                @PathVariable("id") String id) {
            return ResponseEntity.ok()
                    .header("X-Trace-Id", "trace-docs-001")
                    .body(service.find(id));
        }

        @PostMapping(value = "/api/tasks",
                     consumes = MediaType.APPLICATION_JSON_VALUE,
                     produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, String>> createTask(
                @RequestBody Map<String, String> request) {
            Map<String, String> created = service.create(request.get("title"));
            return ResponseEntity.created(
                    URI.create("/api/tasks/" + created.get("id"))).body(created);
        }
    }

    @RestControllerAdvice
    public static class TaskErrorAdvice {
        @ExceptionHandler(TaskMissingException.class)
        public ResponseEntity<Map<String, String>> handle(
                TaskMissingException ex) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                    "error", "TASK_NOT_FOUND",
                    "message", ex.getMessage()));
        }
    }
}
```

### Why Does This Configuration Work?

- **Controller and dependency:** `new TaskController(service)` explicitly passes in a `FakeTaskService`. The test does not need Spring to scan `@Service` or connect to a database.
- **Advice must be registered:** `setControllerAdvice(new TaskErrorAdvice())` brings the `TaskMissingException` handler into the test harness. If omitted, do not expect error requests to automatically turn into `404` JSON as in the real application.
- **JSON converter:** `setMessageConverters(new MappingJackson2HttpMessageConverter())` defines how JSON is read and written in the test. This is an explicit configuration, not the Jackson configuration automatically pulled from the application.
- **Spring REST Docs:** `RestDocumentationExtension` provides the context, `documentationConfiguration(...)` applies it to the builder, and `andDo(document(...))` decides which requests are documented.
- **Assertions and descriptors:** `andExpect(...)` verifies the HTTP result. `pathParameters(...)`, `requestHeaders(...)`, `requestFields(...)`, `responseHeaders(...)`, and `responseFields(...)` describe the actual data the test sends/receives.

`FakeTaskService` returns fixed data so snippets remain consistent across runs. That is an advantage when authoring documentation examples, and also the reason to maintain **separate integration tests** if you need to prove the real service and persistence layers work properly.

## 5. Limitations of the Standalone Environment and How to Compensate

`standaloneSetup` provides many Spring MVC defaults, but does not load custom beans defined in the application. Before trusting that a documentation test reflects the real running API, check the following components:

| Application Scenario | Limitation in Standalone | Appropriate Workaround |
| --- | --- | --- |
| Controller uses service, repository | No component scan and dependency injection from the app | Pass fake/mock/service directly; use integration tests if real wiring needs verification. |
| `@RestControllerAdvice` error handling | Does not automatically discover all advice in the app | Register with `setControllerAdvice(...)`. |
| Custom `HttpMessageConverter` or Jackson module | Does not automatically inherit the app's converter configuration | Use `setMessageConverters(...)` and configure the corresponding `ObjectMapper`. |
| Bean Validation, `@Valid` | Depends on validators on test classpath and builder setup | Provide an appropriate validator via `setValidator(...)` if specific behavior is needed. |
| Converter/formatter for special types | Does not automatically use the app's `FormattingConversionService` | Configure `setConversionService(...)`. |
| Custom `HandlerMethodArgumentResolver` | Does not automatically load resolvers registered by the app | Configure `setCustomArgumentResolvers(...)`. |
| Filters, CORS, Spring Security | Application filter chain does not appear automatically in full | Register filters to be tested or switch to a web context test. |
| Profile-specific `@ControllerAdvice`, interceptors, or exception resolvers | Relevant beans do not appear automatically from app profiles | Configure explicitly or switch to `webAppContextSetup(...)`. |

Example when a controller needs a specific validator and conversion service:

```java
// validator and conversionService are appropriately initialized objects.
mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .setValidator(validator)
        .setConversionService(conversionService)
        .setControllerAdvice(new ApiErrorAdvice())
        .apply(documentationConfiguration(restDocumentation))
        .build();
```

This is a **customization template** to place inside an existing setup method; the sample variables and classes must be declared according to your specific application. For Bean Validation on Spring Boot 3, you typically need to add `spring-boot-starter-validation` or a compatible provider when validation testing is required.

Do not just add components to the builder to make tests "green" while ignoring the real contract. When an API has complex MVC configuration, testing directly with `WebApplicationContext` is more reliable for integration aspects.

## 6. Spring Security: An Important Boundary

A controller using `@PreAuthorize`, authentication, CSRF, or a security filter chain may behave differently when run in standalone mode because the test creates only the controller and minimal MVC infrastructure. `standaloneSetup` **does not automatically load Spring Security configuration from the application context**.

Approaches to handle this:

1. If you only need to document the JSON contract of an independent controller, fake the dependencies and clearly note that the test verifies the controller in standalone scope.
2. If you need to prove requests are blocked by authentication/authorization/CSRF under the real configuration, prefer `webAppContextSetup(context)`, integrating `spring-security-test` and `springSecurity()` when appropriate.
3. If you want to integrate filters manually, use `addFilters(...)` on the builder with prepared `jakarta.servlet.Filter` instances; ensure the filter order and configuration reflect the scenario under test.

Example showing where to attach a simple filter:

```java
mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .addFilters(traceFilter)
        .apply(documentationConfiguration(restDocumentation))
        .build();
```

`traceFilter` here is a filter instance created in the test. Adding one filter does not mean the entire Spring Security filter chain has been accurately simulated.

**Common pitfall:** standalone documentation records a `200 OK` response for an endpoint that requires a token in the real application. Only publish endpoint security behavior when tests have run with appropriate filter/security config and include assertions for required `401`/`403` status codes.

## 7. Generating Snippets and Including Them in Documentation

With the example in section 4, the three identifiers `tasks-get`, `tasks-create`, and `tasks-get-not-found` create separate snippet groups. When running Gradle:

```bash
./gradlew test
```

On Windows, you can use `gradlew.bat test`. With the default output configuration in Gradle, the structure typically looks like:

```text
build/generated-snippets/
├── tasks-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── path-parameters.adoc
│   ├── request-headers.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
├── tasks-create/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── request-fields.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── tasks-get-not-found/
    ├── http-response.adoc
    └── response-fields.adoc
```

This is an **abbreviated structure** of typical snippets; Spring REST Docs can also generate `curl-request.adoc`, `httpie-request.adoc`, `request-body.adoc`, and `response-body.adoc` depending on the version, default snippet set, and project configuration. Do not treat this diagram as an exhaustive file list.

An Asciidoctor page can use these verified snippets:

```adoc
= Tasks API

== View Task

include::{snippets}/tasks-get/http-request.adoc[]
include::{snippets}/tasks-get/path-parameters.adoc[]
include::{snippets}/tasks-get/response-fields.adoc[]

== Create Task

include::{snippets}/tasks-create/request-fields.adoc[]
include::{snippets}/tasks-create/http-response.adoc[]
include::{snippets}/tasks-create/response-headers.adoc[]

== Task Not Found

include::{snippets}/tasks-get-not-found/http-response.adoc[]
include::{snippets}/tasks-get-not-found/response-fields.adoc[]
```

The `{snippets}` attribute must point to the snippets directory during the Asciidoctor compilation step. If the final documentation uses Markdown, merge/convert snippet contents using an appropriate build mechanism. In CI, set up the order **run tests → generate snippets → compile documentation → publish**, and declare a dependency between the compilation task and the test task to avoid publishing stale documentation.

## 8. Common Errors When Using `standaloneSetup`

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| Controller throws `NullPointerException` on service | Expecting `@Autowired` to inject after `new Controller()` | Pass service via constructor, or use a mock created by the test. |
| `GET` request returns `404` | Controller not passed to builder, or wrong mapping | Check `standaloneSetup(controller)`, `@GetMapping`, and path. |
| JSON response differs from real application | Test uses default converter/ObjectMapper or custom setup differing from app | Register the matching converter, then cross-check with a web context test. |
| JSON POST not accepted, may report `415` | Missing converter or `Content-Type` mismatch | Check `contentType(APPLICATION_JSON)`, `consumes`, and `setMessageConverters`. |
| `@ExceptionHandler` does not run | Application advice not registered in standalone setup | Use `setControllerAdvice(...)`. |
| `@Valid` does not return expected errors | Missing provider or appropriate validator | Check validation dependencies and `setValidator(...)`. |
| Access permissions differ from real API | Spring Security filter chain not simulated | Use a web context test with security configuration and proper assertions. |
| No snippets generated | Missing `documentationConfiguration(...)` or `andDo(document(...))`, test did not reach recording step | Check extension, builder, test result, and output directory. |
| `pathParameters(...)` fails | URI template not used or wrong variable name declared | Call `get("/api/tasks/{id}", value)` and use `parameterWithName("id")`. |
| `responseFields(...)` fails | Documentation missing actual JSON field or wrong path declared | Document all fields; only use `optional()`/`ignored()` when matching the contract. |

Spring REST Docs can **fail tests when descriptors do not match requests/responses**. That is the advantage of verifiable documentation; do not disable checks just to generate documentation.

## 9. Exercises and Completion Criteria

Extend the example with the following steps:

1. Add `GET /api/tasks` with a `state` query parameter. Use `param("state", "OPEN")`, assertions, and `queryParameters(...)` to generate documentation.
2. Add `POST /api/tasks` with a body missing `title`. Use validation or explicit checking logic, register error advice, and record snippets for the error response.
3. Create a custom converter or argument resolver in standalone setup, and verify the difference when removing that configuration.
4. Write another test using `@WebMvcTest` or `@SpringBootTest`/`webAppContextSetup` for the same endpoints; compare responses, advice configuration, and security between the two approaches.
5. Compile Asciidoctor/Markdown from the test-generated snippets and wire the snippet generation step into CI.

**Success criteria:** tests verify HTTP status, headers, and payloads; descriptors match actual data; snippets are generated per endpoint; standalone scope is clearly documented and supplemented by integration tests for application-dependent behavior.

## 10. Checklist Before Using for Real Documentation

- [ ] Controller and all required dependencies are explicitly supplied to `standaloneSetup(...)`.
- [ ] Required advice, converters, validators, argument resolvers, and filters are registered within the proper scope.
- [ ] `RestDocumentationExtension` supplies the context and `documentationConfiguration(...)` is called before `build()`.
- [ ] Each documented request has appropriate assertions and `andDo(document(...))`.
- [ ] Tests use URI templates when describing path parameters, and real headers/bodies when describing them.
- [ ] Security behaviors, bean wiring, or integrated MVC configurations have separate web context tests when needed.
- [ ] Build/CI generates fresh snippets before compiling and publishing Asciidoctor/Markdown.

**Remember:** `standaloneSetup(...)` creates a lean, fast, test-controlled MockMvc environment; `documentationConfiguration(...)` and `document(...)` enable generating REST API documentation from verified HTTP results. The value of the documentation depends on **the configuration scope that the test actually builds**, so clearly distinguish isolated controller behavior from full-application behavior.
