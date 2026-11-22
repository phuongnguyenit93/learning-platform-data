# Thực hành REST API: mapping, DTO, validation, lỗi và kiểm thử

## Mục tiêu

Xây dựng REST API quản lý công việc (Task) bằng **Java 17+, Spring Boot 3.3.6 và Spring MVC**. Bài bao gồm HTTP mapping, DTO, Jakarta Bean Validation, xử lý exception, unit/slice test và integration test. Dữ liệu được giữ trong RAM để tập trung vào web layer; không dùng database trong ví dụ.

Sau khi hoàn thành, bạn có thể giải thích đường đi từ HTTP request tới `DispatcherServlet`, controller, DTO, service, error handler; thiết kế HTTP status chính xác và tự viết test với `MockMvc`, `@WebMvcTest`, `@SpringBootTest`.

### Hợp đồng REST API

| HTTP method | URI | Input | Thành công | Lỗi |
| --- | --- | --- | --- | --- |
| GET | `/api/tasks` | Query `completed=true/false` tùy chọn | 200 + JSON array | 400 nếu query sai kiểu |
| GET | `/api/tasks/{id}` | ID là long | 200 + JSON Task | 400 nếu sai kiểu, 404 nếu không tồn tại |
| POST | `/api/tasks` | JSON title, completed | 201 + Task + Location | 400 nếu body sai |
| PUT | `/api/tasks/{id}` | JSON title, completed | 200 + Task | 400 hoặc 404 |
| DELETE | `/api/tasks/{id}` | Không body | 204 No Content | 404 nếu không tồn tại |

PUT trong bài thay thế cả hai trường có thể cập nhật. Nếu muốn cập nhật riêng một field, định nghĩa PATCH và xử lý “không gửi field” khác với “gửi null”. Một Task gồm `id` server cấp, `title` và `completed`. Client không thể tự đặt `id` khi POST.

Ví dụ POST:

~~~http
POST /api/tasks HTTP/1.1
Content-Type: application/json

{"title":"Học REST API","completed":false}
~~~

Với store rỗng và ID bắt đầu từ 1, server trả HTTP 201 Created, header Location trỏ đến task mới và body JSON như:

~~~json
{"id":1,"title":"Học REST API","completed":false}
~~~

Đừng dựa vào thứ tự property trong JSON hoặc host/port cố định trong Location; hai điều đó có thể khác theo môi trường.

## 1. Cấu trúc các tầng

~~~text
HTTP request
  |
DispatcherServlet / HandlerMapping
  |
  +--> Jackson chuyển JSON thành TaskInput
  +--> Bean Validation: @Valid + constraints
  |       |
  |       +--> sai -> MethodArgumentNotValidException
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

**Controller** chỉ đảm nhận binding và HTTP contract; **request DTO** định nghĩa các trường client có thể gửi; **response DTO** chỉ công khai dữ liệu cho client; **service** thực hiện CRUD và quy tắc nghiệp vụ; **exception handler** chuyển lỗi có chủ đích thành status/schema ổn định. Không nên trả trực tiếp JPA entity trong một API production vì có thể lộ trường nội bộ, kích hoạt lazy loading và ràng buộc schema database với client.

## 2. Cấu trúc dự án

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

`spring-boot-starter-web` cung cấp Spring MVC, Jackson và embedded Tomcat. `spring-boot-starter-validation` cung cấp Jakarta Bean Validation implementation. `spring-boot-starter-test` cung cấp JUnit 5, Mockito, MockMvc và Spring Test. Ví dụ cố định Boot **3.3.6**, vì thế `@MockBean` trong test là API hợp lệ; đừng tự áp dụng import của Boot phiên bản mới hơn vào project này.

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

Các file đặt cùng package `demo.tasks` để component scanning nhận được controller, service và advice.

## 3. DTO và validation

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

`@NotBlank` từ chối null, chuỗi rỗng và chỉ có whitespace. `@Size(max=80)` kiểm tra độ dài. `@NotNull` yêu cầu field `completed` tồn tại. Dùng `Boolean` boxed để phân biệt field thiếu/null với `false`; nếu dùng primitive `boolean`, field thiếu có thể trở thành false mặc định và không thể được phát hiện bằng `@NotNull`.

**TaskResponse.java**:

~~~java
package demo.tasks;

public record TaskResponse(
        long id,
        String title,
        boolean completed
) {}
~~~

Response có ID server tạo; request không có ID. Java 17 record được Jackson trong Boot 3 xử lý như DTO JSON.

| Request JSON | Kết quả |
| --- | --- |
| `{"title":"Learn","completed":false}` | Hợp lệ |
| `{"title":" ","completed":false}` | Vi phạm NotBlank |
| `{"title":"Learn"}` | Vi phạm NotNull của completed |
| `{"title":` | JSON malformed, chưa có DTO để validate |
| `{"title":"Learn","completed":"maybe"}` | Lỗi chuyển kiểu JSON |

Phải đặt `@Valid` trên controller parameter cùng `@RequestBody`. Annotation constraint có mặt trên record nhưng controller quên `@Valid` thì validation không được kích hoạt theo đường xử lý dự kiến.

## 4. Service và exception nghiệp vụ

**TaskNotFoundException.java**:

~~~java
package demo.tasks;

public class TaskNotFoundException extends RuntimeException {
    public TaskNotFoundException(long id) {
        super("Task " + id + " not found");
    }
}
~~~

Service không tự chọn HTTP status. Advice chuyển lỗi này thành 404.

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

`ConcurrentHashMap` cho phép thao tác map từ nhiều thread; `AtomicLong` tạo ID không trùng trong **một process**. `computeIfPresent` cập nhật value theo key trong một bước thay vì gọi `get` rồi `put` rời rạc. Record TaskResponse immutable tránh sửa data trong object được nhiều thread dùng chung. `list` sắp xếp theo ID để kết quả dễ kiểm chứng.

Giới hạn: đây là RAM store, mất dữ liệu khi restart, không có transaction, không đồng bộ giữa replicas. Khi chuyển sang database, bổ sung repository, migration, transaction và chính sách optimistic locking khi cần.

## 5. HTTP mapping trong controller

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

`@RestController` cho biết return value được ghi ra HTTP body, không phải tên view template. `@RequestMapping` đặt tiền tố; các annotation GET/POST/PUT/DELETE chọn HTTP method tương ứng. `@PathVariable` lấy `id` từ URI, còn `@RequestParam` lấy query `?completed=true`. `@RequestBody` dùng Jackson decode request JSON; `@Valid` kiểm tra constraints trước khi gọi service.

`ResponseEntity.created(location)` trả 201 + header Location và body Task. `ServletUriComponentsBuilder.fromCurrentRequest()` lấy URI theo request hiện tại; nếu deploy sau proxy, cấu hình trusted forwarded headers đúng để Location không trả host/port bên trong. GET/PUT trả DTO và mặc định 200; DELETE trả 204 không body.

HTTP status trong demo:

| Status | Tình huống |
| --- | --- |
| 200 | Đọc hoặc thay Task thành công |
| 201 + Location | Tạo Task mới |
| 204 | Xóa Task đã tồn tại, không body |
| 400 | Input sai constraint, JSON malformed hoặc ID/query không parse được |
| 404 | ID hợp lệ về cú pháp nhưng Task không tồn tại |
| 500 | Lỗi server không dự kiến, cần log nội bộ an toàn |

DELETE lần hai trả 404 theo hợp đồng bài này. Idempotence của HTTP DELETE là về **hiệu ứng cuối** trên trạng thái resource, không bắt buộc mọi lần có cùng response code. PUT lặp cùng payload cũng phải có cùng trạng thái cuối. Để hỗ trợ partial updates, thiết kế PATCH riêng.

## 6. Ánh xạ lỗi nhất quán bằng @RestControllerAdvice

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

Bốn loại lỗi khác nhau:

1. `TaskNotFoundException` → HTTP 404 + `TASK_NOT_FOUND`.
2. `MethodArgumentNotValidException` từ `@Valid` → HTTP 400 + `VALIDATION_FAILED` kèm fields.
3. `HttpMessageNotReadableException` từ converter JSON → HTTP 400 + `INVALID_JSON`.
4. `MethodArgumentTypeMismatchException` từ ID/query không chuyển kiểu được → 400 + `INVALID_PARAMETER`.

Ví dụ lỗi field:

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

Đây là error schema của **demo**, không phải chuẩn bắt buộc; Spring 6 cũng hỗ trợ `ProblemDetail` (RFC 9457) và `ResponseEntityExceptionHandler`. Nếu thêm constraint trực tiếp trên method parameter, như `@Min(1) @PathVariable long id`, Spring MVC 6.1+ có thể phát `HandlerMethodValidationException` thay vì lỗi DTO; phải mở rộng handler/test tương ứng.

Không gom mọi `Exception` thành HTTP 400. Exception không dự kiến là lỗi server, thường phải được log riêng, trả phản hồi an toàn và không lộ stack trace, token, SQL hay dữ liệu riêng tư.

## 7. Controller slice test bằng @WebMvcTest

`@WebMvcTest(TaskController.class)` dựng MVC components để kiểm tra mapping, JSON conversion, validation và exception mapping. Service được thay bằng Mockito mock. Không cần chạy embedded HTTP server/DB.

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

Slice test thật sự đi qua MVC request lifecycle, Jackson, `@Valid` và exception handler; chỉ gọi trực tiếp `new TaskController(service).create(dto)` không kiểm tra những thành phần đó. `verifyNoInteractions(service)` chứng minh input sai bị chặn trước khi vào nghiệp vụ.

Trong Boot 3.3, `@WebMvcTest` có khả năng scan `@ControllerAdvice`, vì vậy `ApiExceptionHandler` trong cùng package được nạp. Nếu project có component scan/filter đặc biệt, hãy import advice vào test configuration một cách tường minh.

## 8. Integration test với service thật

`@SpringBootTest` dựng application context đầy đủ, còn `@AutoConfigureMockMvc` dùng mock Servlet request/response. Test này **không mở TCP port**, nhưng gọi qua controller/service/advice thật và xác minh state.

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

Không đoán ID bằng 1 trong test: lấy ID thực từ POST response, vì Spring Test có thể reuse application context và thứ tự chạy test không được bảo đảm. PUT invalid trả 400 trước khi service tra ID. Unit test service, DB integration test và real-network test bổ sung sau khi có yêu cầu.

Để test server thật qua TCP, có thể dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`, `@LocalServerPort` và HTTP client như `RestClient` hoặc `WebTestClient.bindToServer` khi có dependency. Muốn kiểm tra proxy/TLS phải gửi request qua chính tầng proxy/TLS đó; MockMvc không kiểm tra mạng thật.

## 9. Chạy và gửi HTTP request

Cần JDK 17+ và Gradle tương thích. Tại thư mục chứa `build.gradle`:

~~~bash
gradle test
gradle bootRun
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew test` và `./gradlew bootRun` trên Unix/macOS, hoặc `gradlew.bat test` và `gradlew.bat bootRun` trên Windows.

**Tạo Task** bằng curl trong shell hỗ trợ single quotes:

~~~bash
curl -i -X POST "http://localhost:8080/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"Học Spring REST","completed":false}'
~~~

**Đọc, lọc, cập nhật, xóa:**

~~~bash
curl -i "http://localhost:8080/api/tasks"
curl -i "http://localhost:8080/api/tasks?completed=false"
curl -i "http://localhost:8080/api/tasks/1"

curl -i -X PUT "http://localhost:8080/api/tasks/1" \
  -H "Content-Type: application/json" \
  -d '{"title":"Đã thực hành","completed":true}'

curl -i -X DELETE "http://localhost:8080/api/tasks/1"
curl -i "http://localhost:8080/api/tasks/1"
~~~

**Kiểm tra lỗi:**

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

Bốn trường hợp trả lần lượt: 400 `VALIDATION_FAILED`, 400 `INVALID_JSON`, 400 `INVALID_PARAMETER`, 404 `TASK_NOT_FOUND`. Trên Windows PowerShell 5.1, `curl` có thể là alias của `Invoke-WebRequest`; dùng `curl.exe` hoặc `Invoke-RestMethod` với JSON request body đúng cách. API demo dùng port 8080 mặc định trừ khi bạn đổi cấu hình.

## 10. Những lỗi phổ biến

1. **Nhầm mapping path/query:** `/tasks/7` là path variable, `?completed=true` là query.
2. **Quên `@Valid` hoặc starter-validation:** record annotations không tự đảm bảo web request bị chặn.
3. **Dùng primitive boolean cho input required:** không phân biệt missing với false.
4. **Trả JPA entity trực tiếp:** dễ lộ field nội bộ, circular references, lazy-loading và coupling schema.
5. **POST tạo resource nhưng không trả 201/Location:** làm HTTP contract thiếu thông tin.
6. **DELETE 204 kèm body:** trái ngữ nghĩa No Content.
7. **Coi DTO invalid là server error:** nên trả 400 và field errors.
8. **Coi mọi exception là 400:** che bug server, khó monitoring.
9. **Chỉ test happy path:** bỏ quên missing resource, JSON malformed, invalid query và validation.
10. **Chỉ gọi Java controller method trong test:** không xác minh HTTP binding/Jackson/validation/exception handling.
11. **Phụ thuộc ID cố định hay thứ tự chạy test:** dẫn tới flaky tests.
12. **Dùng ConcurrentHashMap thay database trong production:** không có durability, transaction hay multi-node consistency.
13. **Hardcode host/port vào Location:** sai khi deploy sau reverse proxy.
14. **Tin rằng validation thay authentication/authorization:** mỗi resource cần chính sách quyền riêng.
15. **Không xử lý Content-Type/Accept:** có thể nhận 415 hoặc 406 khi media types không phù hợp.

## 11. Bài tập mở rộng

**Bài 1:** Viết GET `/api/tasks/{id}/status` chỉ trả `id`, `completed` và test cả 200/404.

**Bài 2:** Thêm `description` tùy chọn tối đa 500 ký tự vào DTO. Test input quá dài bị 400 và input hợp lệ xuất hiện trong response.

**Bài 3:** Tạo ba task với completed true/false/true. Test query `completed=true` chỉ trả hai ID đúng. Đảm bảo test không phụ thuộc dữ liệu dư từ test khác.

**Bài 4:** So sánh `GET /api/tasks/abc` và `GET /api/tasks/99999`. Vì sao 400 và 404 khác nhau? Viết MockMvc test.

**Bài 5:** Thêm `@Min(1)` trực tiếp lên `@PathVariable long id`, nghiên cứu `HandlerMethodValidationException` và cập nhật advice/test.

**Bài 6:** Thiết kế PATCH chỉ cập nhật completed; phân biệt field absent và JSON null, quyết định hợp đồng có thể kiểm thử.

**Bài 7:** Thay RAM store bằng database, bổ sung migration, repository, transaction boundaries, versioning và kiểm thử lost update.

**Bài 8:** Thêm authorization theo owner, kiểm tra người chưa đăng nhập (401) và có đăng nhập nhưng không có quyền (403).

## 12. Checklist hoàn thành

- [ ] Mapping và HTTP method đúng hợp đồng.
- [ ] DTO input/output tách biệt, constraint và `@Valid` hoạt động.
- [ ] POST trả 201 + Location; GET/PUT 200; DELETE 204.
- [ ] 400/404 được phân loại và trả JSON lỗi ổn định.
- [ ] Controller chỉ làm HTTP boundary, service giữ logic.
- [ ] Slice test xác minh DTO binding, JSON, status, validation và exception mapping.
- [ ] Integration test dùng service thật, kiểm tra create/read/update/delete.
- [ ] Đã thử curl và xem đầy đủ status/header/body.
- [ ] Nắm rõ giới hạn storage RAM và những việc cần làm khi đưa vào production.

## Tài liệu tham khảo chính thức

- Spring MVC annotated controllers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller.html
- Request mapping: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Request body: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Exception handling: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html
- MockMvc: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Boot 3.3 testing: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
