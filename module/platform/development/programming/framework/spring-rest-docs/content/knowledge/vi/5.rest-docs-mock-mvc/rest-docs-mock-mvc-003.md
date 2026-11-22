# MockMvc `standaloneSetup` và giới hạn ngữ cảnh

## 1. Vì sao cần `standaloneSetup`?

**Spring REST Docs** sinh tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, WebTestClient hoặc REST Assured. Mỗi request được thực thi và kiểm tra trong test có thể tạo ra các **snippet** về request, response, JSON payload, tham số, header. Những snippet này được ghép vào tài liệu Asciidoctor/Markdown và có thể được tái tạo trong build, CI.

Trong chương **MockMvc**, `MockMvcBuilders.standaloneSetup(...)` cho phép tạo MockMvc trực tiếp từ một hoặc nhiều controller mà **không cần khởi động `WebApplicationContext` của ứng dụng**. Cách này hữu ích khi muốn:

- Viết test tài liệu nhanh, chỉ tập trung vào hợp đồng HTTP của một controller.
- Truyền dependency giả lập hoặc dữ liệu xác định trước để snippet ổn định.
- Chủ động thêm những thành phần MVC mà controller thực sự cần.
- Cô lập lỗi trong ánh xạ request, định dạng response và mô tả REST Docs.

Ví dụ khởi tạo tối thiểu:

```java
TaskService service = new FakeTaskService();
TaskController controller = new TaskController(service);

MockMvc mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .build();
```

MockMvc vẫn mô phỏng đường xử lý HTTP của **Spring MVC** bằng `DispatcherServlet` và các thành phần MVC do builder tạo/cấu hình. Tuy nhiên, bean/controller trong ví dụ do **test tự cung cấp**, chứ không được lấy qua component scan hay dependency injection của ứng dụng.

Đây cũng là giới hạn cần hiểu rõ: một test standalone vượt qua chưa chứng minh rằng toàn bộ ứng dụng Spring Boot, các filter, security chain, JSON configuration và những bean khác đều hoạt động đúng trong môi trường chạy thật.

## 2. Cơ chế hoạt động và phạm vi mô phỏng

```text
Test JUnit Jupiter
    |
    +-- new TaskController(fakeService)
    |
    +-- MockMvcBuilders.standaloneSetup(controller)
    |       +-- tự chuẩn bị MVC infrastructure tối thiểu
    |       +-- đăng ký advice / converter / validator tùy chọn
    |       +-- áp dụng documentationConfiguration(...)
    |       +-- build()
    |
    +-- mockMvc.perform(...)
            +-- DispatcherServlet mô phỏng request
            +-- andExpect(...): kiểm tra status / header / body
            +-- andDo(document(...)): ghi snippet
```

So sánh hai cách xây dựng MockMvc:

| Khía cạnh | `standaloneSetup(controller)` | `webAppContextSetup(context)` |
| --- | --- | --- |
| Nguồn controller | Đối tượng được cung cấp trực tiếp | Bean và ánh xạ MVC từ `WebApplicationContext` |
| Khởi động Spring application context | Không yêu cầu | Yêu cầu ngữ cảnh web do Spring Test tải |
| Dependency injection | Test truyền vào constructor/setter | Spring quản lý bean theo cấu hình của test |
| MVC converter, validator, advice tùy chỉnh | Cần đăng ký rõ ràng khi muốn tái hiện cấu hình riêng | Kế thừa các thành phần MVC có trong context |
| Filter và Spring Security | Cần tích hợp tường minh; không tự lấy filter chain của app | Có thể tích hợp filter/security tương ứng với context |
| Tốc độ và tính cô lập | Thường nhanh và dễ kiểm soát | Thường tốn chi phí tải context nhưng sát cấu hình tích hợp hơn |
| Bằng chứng mà test cung cấp | Controller xử lý đúng trong môi trường được dựng | Controller xử lý đúng trong ngữ cảnh MVC mà test đã tải |

**Quy tắc lựa chọn:** dùng `standaloneSetup` khi trọng tâm là hợp đồng HTTP của một controller với dependency kiểm soát được. Nếu cần kiểm chứng `@ControllerAdvice` toàn ứng dụng, cấu hình Jackson phức tạp, converter riêng, filter hay quyền truy cập thực tế, cân nhắc `webAppContextSetup` hoặc MockMvc do Spring Boot cấu hình.

## 3. Chuẩn bị project

Ví dụ bài học dùng **Java 17+, Spring Boot 3.x, Spring MVC, JUnit Jupiter 5** và Gradle:

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

`spring-boot-starter-web` đưa Spring MVC và Jackson vào ứng dụng; `spring-boot-starter-test` cung cấp Spring Test, MockMvc và JUnit Jupiter; `spring-restdocs-mockmvc` cung cấp tích hợp tạo snippet cho MockMvc. Với dự án dùng Spring Boot dependency management, nên dùng phiên bản Spring REST Docs tương thích do BOM quản lý. Dự án không dùng BOM cần khai báo phiên bản cụ thể, phù hợp với Spring Framework đang sử dụng.

Để tài liệu hóa request, MockMvc phải được áp dụng cấu hình Spring REST Docs:

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

Trong đoạn rút gọn này cần import các lớp tương ứng từ `org.junit.jupiter.api`, `org.springframework.restdocs`, `org.springframework.test.web.servlet` và hai static method từ `MockMvcRestDocumentation`. `RestDocumentationExtension` cấp `RestDocumentationContextProvider` cho `@BeforeEach`. `documentationConfiguration(...)` phải được áp dụng **trước `build()`**. Bản thân bước khởi tạo không sinh snippet; request cần được ghi bằng `andDo(document(...))`.

## 4. Ví dụ đầy đủ: controller công việc có dependency giả

Giả sử hệ thống quản lý công việc có ba hành vi:

1. `GET /api/tasks/{id}` trả về công việc đã tồn tại và header `X-Trace-Id`.
2. `POST /api/tasks` nhận JSON có `title`, trả về `201 Created` cùng header `Location`.
3. Khi không tìm thấy công việc, API trả `404` với JSON lỗi nhất quán.

Bài test bên dưới tạo controller và service giả ngay trong test, đăng ký thêm `@RestControllerAdvice` và JSON converter. Không cần chạy toàn bộ ứng dụng để sinh tài liệu cho ba trường hợp này.

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
                                        .description("Mã công việc cần xem")),
                        requestHeaders(
                                headerWithName("Accept")
                                        .description("Định dạng response mong muốn")),
                        responseHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Mã truy vết của response")),
                        responseFields(
                                fieldWithPath("id").description("Mã công việc"),
                                fieldWithPath("title").description("Tên công việc"),
                                fieldWithPath("state").description("Trạng thái"))));
    }

    @Test
    void documentCreateTask() throws Exception {
        mockMvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Viết tài liệu API"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/tasks/t-002"))
                .andExpect(jsonPath("$.title").value("Viết tài liệu API"))
                .andDo(document("tasks-create",
                        requestFields(
                                fieldWithPath("title")
                                        .description("Tên công việc cần tạo")),
                        responseHeaders(
                                headerWithName("Location")
                                        .description("Đường dẫn tới công việc vừa tạo")),
                        responseFields(
                                fieldWithPath("id").description("Mã công việc mới"),
                                fieldWithPath("title").description("Tên công việc"),
                                fieldWithPath("state").description("Trạng thái"))));
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
                                        .description("Mã công việc được yêu cầu")),
                        responseFields(
                                fieldWithPath("error").description("Mã lỗi"),
                                fieldWithPath("message").description("Chi tiết lỗi"))));
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
                    "title", "Kiểm thử API",
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
            super("Không tìm thấy công việc: " + id);
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

### Vì sao cấu hình này hoạt động?

- **Controller và dependency:** `new TaskController(service)` chủ động truyền vào một `FakeTaskService`. Test không cần Spring quét `@Service` hay kết nối cơ sở dữ liệu.
- **Advice phải đăng ký:** `setControllerAdvice(new TaskErrorAdvice())` đưa handler xử lý `TaskMissingException` vào bộ kiểm thử. Nếu bỏ, không nên kỳ vọng request lỗi sẽ tự được biến thành JSON `404` đúng như ứng dụng.
- **JSON converter:** `setMessageConverters(new MappingJackson2HttpMessageConverter())` quy định cách đọc và ghi JSON trong test. Đây là cấu hình chủ đích, không phải cấu hình Jackson được tự động lấy từ ứng dụng.
- **Spring REST Docs:** `RestDocumentationExtension` cung cấp ngữ cảnh, `documentationConfiguration(...)` áp dụng vào builder, còn `andDo(document(...))` quyết định các request được ghi tài liệu.
- **Assertions và descriptor:** `andExpect(...)` xác minh kết quả HTTP. `pathParameters(...)`, `requestHeaders(...)`, `requestFields(...)`, `responseHeaders(...)` và `responseFields(...)` mô tả dữ liệu thực tế mà test gửi/nhận.

`FakeTaskService` trả dữ liệu cố định nên snippet ổn định qua các lần chạy. Đó là lợi thế khi soạn ví dụ tài liệu, đồng thời cũng là lý do phải có **test tích hợp riêng** nếu muốn chứng minh service và persistence thực tế hoạt động đúng.

## 5. Các giới hạn của môi trường standalone và cách bù cấu hình

`standaloneSetup` cung cấp nhiều hành vi mặc định của Spring MVC, nhưng không tải mọi bean tự định nghĩa trong ứng dụng. Trước khi tin rằng test tài liệu phản ánh đúng API chạy thật, đối chiếu các thành phần sau:

| Tình huống trong ứng dụng | Giới hạn khi standalone | Cách xử lý phù hợp |
| --- | --- | --- |
| Controller dùng service, repository | Không có component scan và dependency injection từ app | Truyền fake/mock/service trực tiếp; dùng test tích hợp nếu cần xác minh wiring thực. |
| `@RestControllerAdvice` xử lý lỗi | Không tự tìm mọi advice trong app | Đăng ký với `setControllerAdvice(...)`. |
| Custom `HttpMessageConverter` hoặc Jackson module | Không tự kế thừa cấu hình converter của app | Dùng `setMessageConverters(...)` và cấu hình ObjectMapper tương ứng. |
| Bean Validation, `@Valid` | Phụ thuộc validator trên test classpath và cấu hình builder | Cung cấp validator phù hợp qua `setValidator(...)` nếu cần hành vi cụ thể. |
| Converter/formatter cho kiểu đặc biệt | Không tự dùng `FormattingConversionService` của app | Cấu hình `setConversionService(...)`. |
| Custom `HandlerMethodArgumentResolver` | Không tự load resolver do ứng dụng đăng ký | Cấu hình `setCustomArgumentResolvers(...)`. |
| Filter, CORS, Spring Security | Filter chain của ứng dụng không tự xuất hiện đầy đủ | Đăng ký filter cần kiểm tra hoặc chọn test từ web context. |
| `@ControllerAdvice`, interceptor hoặc exception resolver theo profile | Những bean liên quan không tự xuất hiện từ profile của app | Cấu hình tường minh hoặc chuyển sang `webAppContextSetup(...)`. |

Ví dụ khi controller cần validator và conversion service đặc thù:

```java
// validator và conversionService là các đối tượng đã khởi tạo phù hợp.
mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .setValidator(validator)
        .setConversionService(conversionService)
        .setControllerAdvice(new ApiErrorAdvice())
        .apply(documentationConfiguration(restDocumentation))
        .build();
```

Đây là **mẫu tùy biến** để đặt trong phương thức setup có sẵn; các biến và lớp minh họa cần được khai báo theo ứng dụng cụ thể. Đối với Bean Validation trên Spring Boot 3, thông thường cần thêm `spring-boot-starter-validation` hoặc provider tương thích khi có nhu cầu kiểm thử validation.

Đừng chỉ thêm các thành phần vào builder để test “xanh” mà bỏ qua hợp đồng thật. Khi API có cấu hình MVC phức tạp, kiểm thử trực tiếp bằng `WebApplicationContext` đáng tin hơn cho phần tích hợp.

## 6. Spring Security: ranh giới quan trọng

Một controller dùng `@PreAuthorize`, authentication, CSRF hoặc security filter chain có thể hoạt động khác khi chạy trong standalone vì test chỉ tạo controller và phần MVC tối thiểu. `standaloneSetup` **không tự tải Spring Security configuration từ application context**.

Các hướng xử lý:

1. Nếu chỉ cần mô tả JSON contract của controller độc lập, fake dependency và viết rõ rằng test đang kiểm chứng controller ở phạm vi standalone.
2. Nếu cần chứng minh request được chặn bởi authentication/authorization/CSRF trong cấu hình thực, ưu tiên `webAppContextSetup(context)`, tích hợp `spring-security-test` và `springSecurity()` khi thích hợp.
3. Nếu muốn tích hợp filter thủ công, dùng `addFilters(...)` trên builder với các `jakarta.servlet.Filter` đã chuẩn bị; cần bảo đảm thứ tự và cấu hình filter phản ánh tình huống được kiểm thử.

Ví dụ minh họa chỗ gắn filter đơn giản:

```java
mockMvc = MockMvcBuilders.standaloneSetup(controller)
        .addFilters(traceFilter)
        .apply(documentationConfiguration(restDocumentation))
        .build();
```

`traceFilter` ở đây là đối tượng filter đã được tạo trong test. Việc thêm một filter không có nghĩa toàn bộ Spring Security filter chain đã được mô phỏng chính xác.

**Bẫy thường gặp:** tài liệu standalone ghi response `200 OK` cho endpoint vốn yêu cầu token trong ứng dụng thực. Chỉ nên công bố hành vi bảo mật của endpoint khi test đã chạy với các filter/security config thích hợp và có assertion cho các mã `401`/`403` cần thiết.

## 7. Sinh snippet và đưa vào tài liệu

Với ví dụ phần 4, ba identifier `tasks-get`, `tasks-create` và `tasks-get-not-found` tạo các nhóm snippet riêng. Khi chạy Gradle:

```bash
./gradlew test
```

Trên Windows có thể dùng `gradlew.bat test`. Nếu dùng cấu hình output mặc định tương ứng Gradle, cấu trúc thường có dạng:

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

Đây là **cấu trúc rút gọn** các snippet tiêu biểu; Spring REST Docs còn có thể sinh `curl-request.adoc`, `httpie-request.adoc`, `request-body.adoc`, `response-body.adoc` theo phiên bản, bộ snippet mặc định và cấu hình của dự án. Không nên coi sơ đồ này là danh sách file đầy đủ.

Một trang Asciidoctor có thể dùng những snippet đã được kiểm chứng:

```adoc
= Tasks API

== Xem công việc

include::{snippets}/tasks-get/http-request.adoc[]
include::{snippets}/tasks-get/path-parameters.adoc[]
include::{snippets}/tasks-get/response-fields.adoc[]

== Tạo công việc

include::{snippets}/tasks-create/request-fields.adoc[]
include::{snippets}/tasks-create/http-response.adoc[]
include::{snippets}/tasks-create/response-headers.adoc[]

== Không tìm thấy công việc

include::{snippets}/tasks-get-not-found/http-response.adoc[]
include::{snippets}/tasks-get-not-found/response-fields.adoc[]
```

Thuộc tính `{snippets}` phải trỏ đến thư mục snippet trong bước biên soạn Asciidoctor. Nếu tài liệu cuối cùng dùng Markdown, cần ghép/chuyển nội dung snippet bằng cơ chế build thích hợp. Trong CI, hãy thiết lập thứ tự **chạy test → tạo snippet → biên soạn tài liệu → publish** và khai báo phụ thuộc giữa tác vụ biên soạn với test để tránh đưa tài liệu cũ lên website.

## 8. Lỗi thường gặp khi dùng `standaloneSetup`

| Hiện tượng | Nguyên nhân phổ biến | Hướng kiểm tra |
| --- | --- | --- |
| Controller ném `NullPointerException` tại service | Trông chờ `@Autowired` tự inject sau `new Controller()` | Truyền service vào constructor, hoặc dùng mock được test tạo. |
| Request `GET` trả `404` | Controller chưa được truyền vào builder, mapping sai | Kiểm tra `standaloneSetup(controller)`, `@GetMapping` và đường dẫn. |
| Response JSON khác ứng dụng thật | Test dùng converter/ObjectMapper mặc định hoặc tự cấu hình khác app | Đăng ký converter tương ứng, sau đó đối chiếu với test web context. |
| Không nhận JSON POST, có thể báo `415` | Thiếu converter hoặc `Content-Type` không khớp | Kiểm tra `contentType(APPLICATION_JSON)`, `consumes` và `setMessageConverters`. |
| `@ExceptionHandler` không chạy | Advice trong ứng dụng chưa đăng ký ở standalone | Dùng `setControllerAdvice(...)`. |
| `@Valid` không trả lỗi như mong đợi | Thiếu provider hoặc validator phù hợp | Kiểm tra dependency validation và `setValidator(...)`. |
| Quyền truy cập khác với API thật | Không mô phỏng Spring Security filter chain | Dùng test web context có cấu hình security và assertions phù hợp. |
| Không có snippet | Thiếu `documentationConfiguration(...)` hoặc `andDo(document(...))`, test không đến bước ghi | Kiểm tra extension, builder, kết quả test và thư mục output. |
| `pathParameters(...)` lỗi | Không dùng URI template hoặc khai báo nhầm tên biến | Gọi `get("/api/tasks/{id}", value)` và dùng `parameterWithName("id")`. |
| `responseFields(...)` thất bại | Tài liệu thiếu field JSON thực tế hoặc khai báo sai path | Mô tả đủ các field; chỉ dùng `optional()`/`ignored()` khi đúng hợp đồng. |

Spring REST Docs có thể làm **test thất bại khi descriptor không khớp request/response**. Đó là lợi thế của tài liệu có thể kiểm chứng; không nên tắt kiểm tra chỉ để tạo tài liệu.

## 9. Bài tập và tiêu chí hoàn thành

Hãy mở rộng ví dụ theo các bước:

1. Thêm `GET /api/tasks` có query parameter `state`. Dùng `param("state", "OPEN")`, assertions và `queryParameters(...)` để sinh tài liệu.
2. Thêm `POST /api/tasks` với body thiếu `title`. Dùng validation hoặc logic kiểm tra rõ ràng, đăng ký error advice và ghi snippet cho response lỗi.
3. Tạo một converter hoặc argument resolver tùy chỉnh trên standalone, kiểm tra sự khác biệt khi bỏ cấu hình đó.
4. Viết thêm một test với `@WebMvcTest` hoặc `@SpringBootTest`/`webAppContextSetup` cho cùng endpoint; đối chiếu response, cấu hình advice và security giữa hai cách.
5. Biên soạn Asciidoctor/Markdown từ các snippet tạo bởi test và nối bước sinh snippet vào CI.

**Tiêu chí đạt:** test kiểm chứng được HTTP status, header và payload; descriptor khớp dữ liệu thực tế; snippet được tạo theo từng endpoint; phạm vi standalone được ghi nhận rõ và có test tích hợp bổ sung cho những hành vi phụ thuộc ứng dụng.

## 10. Checklist trước khi sử dụng cho tài liệu thật

- [ ] Controller và tất cả dependency cần thiết được cung cấp tường minh cho `standaloneSetup(...)`.
- [ ] Advice, converter, validator, argument resolver và filter cần dùng đã được đăng ký đúng phạm vi.
- [ ] `RestDocumentationExtension` cấp ngữ cảnh và `documentationConfiguration(...)` được gọi trước `build()`.
- [ ] Mỗi request cần tài liệu đều có assertions và `andDo(document(...))` phù hợp.
- [ ] Test dùng URI template khi mô tả path parameter, header/body thật khi mô tả chúng.
- [ ] Những hành vi về security, bean wiring hoặc cấu hình MVC tích hợp đã có test web context riêng khi cần.
- [ ] Build/CI tạo snippet mới trước khi biên soạn và xuất bản Asciidoctor/Markdown.

**Ghi nhớ:** `standaloneSetup(...)` tạo môi trường MockMvc gọn, nhanh, do test kiểm soát; `documentationConfiguration(...)` và `document(...)` cho phép tạo tài liệu REST API từ những kết quả HTTP đã được kiểm chứng. Giá trị của tài liệu phụ thuộc vào **phạm vi cấu hình mà test thực sự dựng lên**, nên cần phân biệt rõ hành vi controller độc lập và hành vi của toàn ứng dụng.
