# REST API Practice: Mapping, DTOs, Validation, Errors, and Testing

## Goal

Build a Task management REST API using **Java 17+, Spring Boot 3.3.6, and Spring MVC**. This lesson covers HTTP mapping, DTOs, Jakarta Bean Validation, exception handling, unit/slice tests, and integration tests. Data is kept in RAM to focus on the web layer; no database is used in the example.

After completing it, you will be able to trace the path from an HTTP request to `DispatcherServlet`, controller, DTOs, service, and error handler; design accurate HTTP statuses; and write tests using `MockMvc`, `@WebMvcTest`, and `@SpringBootTest`.

### REST API contract

| HTTP method | URI | Input | Success | Errors |
| --- | --- | --- | --- | --- |
| GET | `/api/tasks` | Optional query `completed=true/false` | 200 + JSON array | 400 if query has wrong type |
| GET | `/api/tasks/{id}` | ID as long | 200 + Task JSON | 400 if wrong type, 404 if not found |
| POST | `/api/tasks` | JSON title, completed | 201 + Task + Location | 400 if body is invalid |
| PUT | `/api/tasks/{id}` | JSON title, completed | 200 + Task | 400 or 404 |
| DELETE | `/api/tasks/{id}` | No body | 204 No Content | 404 if not found |

PUT in this lesson replaces both updatable fields. To update a single field selectively, define PATCH and distinguish "field omitted" from "field sent as null." A Task consists of a server-assigned `id`, `title`, and `completed`. Clients cannot supply `id` on POST.

Example POST:

~~~http
POST /api/tasks HTTP/1.1
Content-Type: application/json

{"title":"Learn REST API","completed":false}
~~~

With an empty store and IDs starting at 1, the server returns HTTP 201 Created, a Location header pointing to the new task, and a JSON body such as:

~~~json
{"id":1,"title":"Learn REST API","completed":false}
~~~

Do not rely on JSON property ordering or a hardcoded host/port in Location; both can vary by environment.

## 1. Layer structure

~~~text
HTTP request
  |
DispatcherServlet / HandlerMapping
  |
  +--> Jackson converts JSON to TaskInput
  +--> Bean Validation: @Valid + constraints
  |       |
  |       +--> invalid -> MethodArgumentNotValidException
  |                    -> ApiExceptionHandler -> 400 JSON
  |
TaskController
  |
TaskService -> ConcurrentHashMap
  |
TaskResponse
  |
ResponseEntity / Jackson
  |
HTTP response (status + headers + JSON)
~~~

The **controller** handles only binding and the HTTP contract; the **request DTO** defines fields clients may send; the **response DTO** exposes only public client data; the **service** implements CRUD and business rules; and the **exception handler** maps intentional errors to stable statuses/schemas. Never return JPA entities directly in a production API because doing so can leak internal fields, trigger lazy loading, and couple database schemas to clients.

## 2. Project structure

~~~text
tasks-rest-demo/
  build.gradle
  src/main/java/demo/tasks/
    TaskApiApplication.java
    TaskInput.java
    TaskResponse.java
    TaskNotFoundException.java
    TaskService.java
    TaskController.java
    ApiError.java
    ApiExceptionHandler.java
  src/test/java/demo/tasks/
    TaskControllerMvcTest.java
    TaskApiIntegrationTest.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` provides Spring MVC, Jackson, and embedded Tomcat. `spring-boot-starter-validation` provides a Jakarta Bean Validation implementation. `spring-boot-starter-test` provides JUnit 5, Mockito, MockMvc, and Spring Test. The example pins Boot **3.3.6**, so `@MockBean` in tests is a valid API; do not mix imports from newer Boot versions into this project.

**TaskApiApplication.java**:

~~~java
package demo.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(TaskApiApplication.class, args);
    }
}
~~~

All files share the `demo.tasks` package so component scanning picks up the controller, service, and advice.

## 3. DTOs and validation

**TaskInput.java**:

~~~java
package demo.tasks;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record TaskInput(
        @NotBlank(message = "title must not be blank")
        @Size(max = 80, message = "title must contain at most 80 characters")
        String title,

        @NotNull(message = "completed is required")
        Boolean completed
) {}
~~~

`@NotBlank` rejects null, empty strings, and whitespace-only strings. `@Size(max=80)` checks length. `@NotNull` requires the `completed` field to be present. Use boxed `Boolean` to distinguish missing/null from `false`; with primitive `boolean`, a missing field can default to false and escape `@NotNull` detection.

**TaskResponse.java**:

~~~java
package demo.tasks;

public record TaskResponse(
        long id,
        String title,
        boolean completed
) {}
~~~

The response carries the server-generated ID; the request has no ID. Java 17 records are handled by Jackson in Boot 3 as JSON DTOs.

| Request JSON | Outcome |
| --- | --- |
| `{"title":"Learn","completed":false}` | Valid |
| `{"title":" ","completed":false}` | Violates NotBlank |
| `{"title":"Learn"}` | Violates NotNull on completed |
| `{"title":` | Malformed JSON, no DTO to validate yet |
| `{"title":"Learn","completed":"maybe"}` | JSON type conversion error |

You must place `@Valid` on the controller parameter alongside `@RequestBody`. Having constraint annotations on the record while forgetting `@Valid` on the controller means validation will not run along the expected path.

## 4. Service and business exceptions

**TaskNotFoundException.java**:

~~~java
package demo.tasks;

public class TaskNotFoundException extends RuntimeException {
    public TaskNotFoundException(long id) {
        super("Task " + id + " not found");
    }
}
~~~

The service does not choose HTTP statuses itself. Advice translates this error into 404.

**TaskService.java**:

~~~java
package demo.tasks;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class TaskService {
    private final Map<Long, TaskResponse> tasks =
            new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    public List<TaskResponse> list(Boolean completed) {
        return tasks.values().stream()
                .filter(task -> completed == null
                        || task.completed() == completed)
                .sorted(Comparator.comparingLong(TaskResponse::id))
                .toList();
    }

    public TaskResponse get(long id) {
        TaskResponse found = tasks.get(id);
        if (found == null) {
            throw new TaskNotFoundException(id);
        }
        return found;
    }

    public TaskResponse create(TaskInput input) {
        long id = sequence.incrementAndGet();
        TaskResponse task = new TaskResponse(
                id, input.title().trim(), input.completed());
        tasks.put(id, task);
        return task;
    }

    public TaskResponse replace(long id, TaskInput input) {
        TaskResponse task = tasks.computeIfPresent(id,
                (key, old) -> new TaskResponse(
                        key, input.title().trim(), input.completed()));
        if (task == null) {
            throw new TaskNotFoundException(id);
        }
        return task;
    }

    public void delete(long id) {
        if (tasks.remove(id) == null) {
            throw new TaskNotFoundException(id);
        }
    }
}
~~~

`ConcurrentHashMap` allows concurrent map operations across threads; `AtomicLong` generates unique IDs within **a single process**. `computeIfPresent` updates the value for a key atomically instead of doing separate `get` and `put` calls. Immutable `TaskResponse` records prevent mutating shared objects across threads. `list` sorts by ID so results are easy to assert.

Limitation: this is a RAM store—data is lost on restart, there are no transactions, and it is not synchronized across replicas. When moving to a database, add repositories, migrations, transactions, and optimistic locking policies as needed.

## 5. HTTP mapping in the controller

**TaskController.java**:

~~~java
package demo.tasks;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping
    public List<TaskResponse> list(
            @RequestParam(required = false) Boolean completed) {
        return service.list(completed);
    }

    @GetMapping("/{id}")
    public TaskResponse get(@PathVariable long id) {
        return service.get(id);
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @Valid @RequestBody TaskInput input) {
        TaskResponse created = service.create(input);
        URI location = ServletUriComponentsBuilder
                .fromCurrentRequest()
                .path("/{id}")
                .buildAndExpand(created.id())
                .toUri();
        return ResponseEntity.created(location).body(created);
    }

    @PutMapping("/{id}")
    public TaskResponse replace(
            @PathVariable long id,
            @Valid @RequestBody TaskInput input) {
        return service.replace(id, input);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

`@RestController` indicates return values are written to the HTTP body, not resolved as view template names. `@RequestMapping` sets the path prefix; GET/POST/PUT/DELETE annotations match the corresponding HTTP methods. `@PathVariable` extracts `id` from the URI, while `@RequestParam` reads `?completed=true`. `@RequestBody` uses Jackson to decode request JSON; `@Valid` checks constraints before calling the service.

`ResponseEntity.created(location)` returns 201 + a Location header and the Task body. `ServletUriComponentsBuilder.fromCurrentRequest()` derives the URI from the current request; when deploying behind a proxy, configure trusted forwarded headers properly so Location does not leak an internal host/port. GET/PUT return the DTO and default to 200; DELETE returns 204 with no body.

HTTP statuses in the demo:

| Status | Scenario |
| --- | --- |
| 200 | Successfully read or replaced Task |
| 201 + Location | Created new Task |
| 204 | Deleted existing Task, no body |
| 400 | Constraint violation, malformed JSON, or unparseable ID/query |
| 404 | Syntactically valid ID, but Task does not exist |
| 500 | Unexpected server error; must be logged safely internally |

A second DELETE returns 404 under this lesson's contract. HTTP DELETE idempotence concerns the **final effect** on resource state, not requiring the same status code on every repeat call. Repeating PUT with the same payload must also leave the same final state. To support partial updates, design PATCH separately.

## 6. Consistent error mapping with @RestControllerAdvice

**ApiError.java**:

~~~java
package demo.tasks;

import java.util.Map;

public record ApiError(
        String code,
        String message,
        Map<String, String> fields
) {}
~~~

**ApiExceptionHandler.java**:

~~~java
package demo.tasks;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(TaskNotFoundException.class)
    public ResponseEntity<ApiError> missing(
            TaskNotFoundException error) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "TASK_NOT_FOUND",
                        error.getMessage(),
                        Map.of()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidDto(
            MethodArgumentNotValidException error) {
        Map<String, String> fields = new LinkedHashMap<>();
        error.getBindingResult().getFieldErrors()
                .forEach(fieldError -> fields.putIfAbsent(
                        fieldError.getField(),
                        fieldError.getDefaultMessage() == null
                                ? "Invalid value"
                                : fieldError.getDefaultMessage()));

        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "VALIDATION_FAILED",
                        "Request validation failed",
                        fields));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> invalidJson(
            HttpMessageNotReadableException error) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_JSON",
                        "Request body is missing or malformed",
                        Map.of()));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidParameter(
            MethodArgumentTypeMismatchException error) {
        String name = error.getName() == null
                ? "parameter" : error.getName();
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_PARAMETER",
                        "Request parameter has an invalid type",
                        Map.of(name, "Invalid value")));
    }
}
~~~

Four distinct error categories:

1. `TaskNotFoundException` → HTTP 404 + `TASK_NOT_FOUND`.
2. `MethodArgumentNotValidException` from `@Valid` → HTTP 400 + `VALIDATION_FAILED` with fields.
3. `HttpMessageNotReadableException` from the JSON converter → HTTP 400 + `INVALID_JSON`.
4. `MethodArgumentTypeMismatchException` from unconvertible ID/query → 400 + `INVALID_PARAMETER`.

Example field error:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request validation failed",
  "fields": {
    "title": "title must not be blank",
    "completed": "completed is required"
  }
}
~~~

This is the **demo's** error schema, not a mandatory standard; Spring 6 also supports `ProblemDetail` (RFC 9457) and `ResponseEntityExceptionHandler`. If you add constraints directly on method parameters, such as `@Min(1) @PathVariable long id`, Spring MVC 6.1+ may raise `HandlerMethodValidationException` instead of a DTO error; extend handlers and tests accordingly.

Never funnel every `Exception` into HTTP 400. Unexpected exceptions are server errors that must be logged internally and answered with a safe response that exposes no stack traces, tokens, SQL, or private data.

## 7. Controller slice testing with @WebMvcTest

`@WebMvcTest(TaskController.class)` boots MVC components to test mapping, JSON conversion, validation, and exception mapping. The service is replaced with a Mockito mock. No embedded HTTP server or DB is needed.

**TaskControllerMvcTest.java**:

~~~java
package demo.tasks;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(TaskController.class)
class TaskControllerMvcTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    TaskService service;

    @Test
    void postMapsDtoAndReturns201() throws Exception {
        when(service.create(any(TaskInput.class)))
                .thenReturn(new TaskResponse(42, "Learn MVC", false));

        mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Learn MVC","completed":false}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", endsWith("/api/tasks/42")))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Learn MVC"));

        verify(service).create(argThat(input ->
                "Learn MVC".equals(input.title())
                        && Boolean.FALSE.equals(input.completed())));
    }

    @Test
    void invalidDtoIsRejectedBeforeService() throws Exception {
        mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"   "}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields.title").exists())
                .andExpect(jsonPath("$.fields.completed").exists());

        verifyNoInteractions(service);
    }

    @Test
    void notFoundBecomes404() throws Exception {
        when(service.get(999))
                .thenThrow(new TaskNotFoundException(999));

        mvc.perform(get("/api/tasks/999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("TASK_NOT_FOUND"));
    }

    @Test
    void malformedJsonBecomes400() throws Exception {
        mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void invalidPathVariableBecomes400() throws Exception {
        mvc.perform(get("/api/tasks/not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_PARAMETER"));
    }
}
~~~

Slice tests genuinely pass through the MVC request lifecycle, Jackson, `@Valid`, and exception handlers; calling `new TaskController(service).create(dto)` directly checks none of those. `verifyNoInteractions(service)` proves invalid input is stopped before entering business logic.

In Boot 3.3, `@WebMvcTest` scans `@ControllerAdvice`, so `ApiExceptionHandler` in the same package is loaded. If a project uses custom component scanning/filters, explicitly import the advice into the test configuration.

## 8. Integration testing with the real service

`@SpringBootTest` builds the full application context, while `@AutoConfigureMockMvc` uses mocked Servlet requests/responses. This test **does not open a TCP port**, yet invokes the real controller/service/advice and verifies state.

**TaskApiIntegrationTest.java**:

~~~java
package demo.tasks;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TaskApiIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void createReadUpdateDelete() throws Exception {
        MvcResult created = mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Learn REST","completed":false}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Learn REST"))
                .andReturn();

        JsonNode json = mapper.readTree(
                created.getResponse().getContentAsString());
        long id = json.path("id").asLong();

        mvc.perform(get("/api/tasks/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.completed").value(false));

        mvc.perform(put("/api/tasks/{id}", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Learn REST well","completed":true}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                        .value("Learn REST well"))
                .andExpect(jsonPath("$.completed").value(true));

        mvc.perform(delete("/api/tasks/{id}", id))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/tasks/{id}", id))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("TASK_NOT_FOUND"));
    }

    @Test
    void invalidPutFailsValidationFirst() throws Exception {
        mvc.perform(put("/api/tasks/999999")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"","completed":null}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"));
    }
}
~~~

Do not assume ID equals 1 in tests: extract the actual ID from the POST response, because Spring Test may reuse the application context and test execution order is not guaranteed. An invalid PUT returns 400 before the service looks up the ID. Add service unit tests, DB integration tests, and real-network tests as requirements grow.

To test a real server over TCP, use `@SpringBootTest(webEnvironment=RANDOM_PORT)`, `@LocalServerPort`, and an HTTP client such as `RestClient` or `WebTestClient.bindToServer` when available. To verify proxies/TLS, send requests through that proxy/TLS layer itself; MockMvc does not test real networking.

## 9. Running and sending HTTP requests

Requires JDK 17+ and a compatible Gradle version. In the directory containing `build.gradle`:

~~~bash
gradle test
gradle bootRun
~~~

If the project includes a Gradle Wrapper, use `./gradlew test` and `./gradlew bootRun` on Unix/macOS, or `gradlew.bat test` and `gradlew.bat bootRun` on Windows.

**Create a Task** with curl in a shell supporting single quotes:

~~~bash
curl -i -X POST "http://localhost:8080/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"Learn Spring REST","completed":false}'
~~~

**Read, filter, update, delete:**

~~~bash
curl -i "http://localhost:8080/api/tasks"
curl -i "http://localhost:8080/api/tasks?completed=false"
curl -i "http://localhost:8080/api/tasks/1"

curl -i -X PUT "http://localhost:8080/api/tasks/1" \
  -H "Content-Type: application/json" \
  -d '{"title":"Practiced","completed":true}'

curl -i -X DELETE "http://localhost:8080/api/tasks/1"
curl -i "http://localhost:8080/api/tasks/1"
~~~

**Test errors:**

~~~bash
curl -i -X POST "http://localhost:8080/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"  ","completed":null}'

curl -i -X POST "http://localhost:8080/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":'

curl -i "http://localhost:8080/api/tasks/abc"
curl -i "http://localhost:8080/api/tasks/99999"
~~~

The four cases return respectively: 400 `VALIDATION_FAILED`, 400 `INVALID_JSON`, 400 `INVALID_PARAMETER`, 404 `TASK_NOT_FOUND`. On Windows PowerShell 5.1, `curl` may be an alias for `Invoke-WebRequest`; use `curl.exe` or `Invoke-RestMethod` with proper JSON body quoting. The demo API defaults to port 8080 unless configured otherwise.

## 10. Common mistakes

1. **Confusing path and query mappings:** `/tasks/7` is a path variable; `?completed=true` is a query parameter.
2. **Forgetting `@Valid` or starter-validation:** record annotations alone do not ensure web requests are validated.
3. **Using primitive boolean for required input:** cannot distinguish missing from false.
4. **Returning JPA entities directly:** risks exposing internal fields, circular references, lazy loading, and schema coupling.
5. **POST creates a resource without 201/Location:** leaves the HTTP contract incomplete.
6. **DELETE 204 returning a body:** violates No Content semantics.
7. **Treating invalid DTOs as server errors:** return 400 and field errors instead.
8. **Treating every exception as 400:** hides server bugs and hurts monitoring.
9. **Testing only the happy path:** neglecting missing resources, malformed JSON, invalid queries, and validation.
10. **Calling Java controller methods directly in tests:** skips HTTP binding/Jackson/validation/exception handling.
11. **Relying on fixed IDs or test execution order:** leads to flaky tests.
12. **Using ConcurrentHashMap instead of a database in production:** lacks durability, transactions, and multi-node consistency.
13. **Hardcoding host/port into Location:** breaks when deployed behind a reverse proxy.
14. **Believing validation replaces authentication/authorization:** every resource needs its own access policy.
15. **Ignoring Content-Type/Accept:** can trigger 415 or 406 when media types do not match.

## 11. Extension exercises

**Exercise 1:** Implement GET `/api/tasks/{id}/status` returning only `id` and `completed`, and test both 200 and 404.

**Exercise 2:** Add an optional `description` up to 500 characters to the DTO. Test that oversized input gets 400 and valid input appears in the response.

**Exercise 3:** Create three tasks with completed true/false/true. Test that query `completed=true` returns only the two matching IDs. Ensure tests do not depend on leftover data from other tests.

**Exercise 4:** Compare `GET /api/tasks/abc` and `GET /api/tasks/99999`. Why do 400 and 404 differ? Write MockMvc tests.

**Exercise 5:** Add `@Min(1)` directly onto `@PathVariable long id`, investigate `HandlerMethodValidationException`, and update advice/tests.

**Exercise 6:** Design PATCH updating only completed; distinguish an absent field from JSON null and define a testable contract.

**Exercise 7:** Replace the RAM store with a database, adding migrations, repositories, transaction boundaries, versioning, and lost-update tests.

**Exercise 8:** Add owner-based authorization, testing unauthenticated (401) and authenticated-but-forbidden (403) callers.

## 12. Completion checklist

- [ ] Mappings and HTTP methods match the contract.
- [ ] Input/output DTOs are separated; constraints and `@Valid` are active.
- [ ] POST returns 201 + Location; GET/PUT return 200; DELETE returns 204.
- [ ] 400/404 are classified and return stable error JSON.
- [ ] Controller handles only the HTTP boundary; service holds the logic.
- [ ] Slice tests verify DTO binding, JSON, status, validation, and exception mapping.
- [ ] Integration tests use the real service to verify create/read/update/delete.
- [ ] Tried curl and inspected full status/headers/body.
- [ ] Understand RAM storage limitations and what is required for production.

## Official references

- Spring MVC annotated controllers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller.html
- Request mapping: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Request body: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Exception handling: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html
- MockMvc: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Boot 3.3 testing: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
