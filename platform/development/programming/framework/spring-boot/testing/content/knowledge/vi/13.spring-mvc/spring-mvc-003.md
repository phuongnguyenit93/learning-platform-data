# Gửi request với path variable, query parameter, header và body trong Spring MVC Testing

## 1. Mục tiêu và phạm vi

Một endpoint Spring MVC nhận dữ liệu HTTP từ nhiều nơi: **path variable** trong đường dẫn, **query parameter** sau dấu `?`, **header** của request và **body** chứa JSON hoặc dữ liệu khác. Khi kiểm thử controller, ta cần chứng minh Spring MVC đã **map đúng URL, chuyển đổi kiểu, kiểm tra dữ liệu và truyền đúng đối số cho nghiệp vụ**, sau đó trả về HTTP status, header và response body theo hợp đồng.

Ví dụ một request tạo sách:

```http
POST /api/books?source=mobile HTTP/1.1
Host: localhost
X-Tenant-Id: tenant-a
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":240}
```

Và request lấy sách:

```http
GET /api/books/42?lang=vi HTTP/1.1
Host: localhost
X-Tenant-Id: tenant-a
Accept: application/json
```

Đối tượng được kiểm thử ở bài này là **Spring MVC request binding**: `@PathVariable`, `@RequestParam`, `@RequestHeader` và `@RequestBody`, cùng các thao tác gửi request bằng **MockMvc**. Cuối bài còn có một test chạy embedded server trên port ngẫu nhiên để làm rõ khác biệt giữa kiểm thử MVC giả lập và HTTP thật.

**Kết quả cần đạt:** đọc được một test MockMvc và chỉ ra dữ liệu HTTP nào trở thành tham số Java nào; viết được cả happy path lẫn lỗi 400/415; biết cách đặt `Content-Type` khác `Accept`; hiểu khi nào cần `@WebMvcTest` và khi nào cần `@SpringBootTest`.

## 2. Bốn nguồn dữ liệu của HTTP request

| Nguồn | Ví dụ trong request | Spring MVC nhận bằng | MockMvc gửi bằng |
| --- | --- | --- | --- |
| Path variable | `/api/books/42` | `@PathVariable("id") long id` | `get("/api/books/{id}", 42)` |
| Query parameter | `?lang=vi&page=2` | `@RequestParam("lang") String lang` | `.queryParam("lang", "vi")` hoặc `.param(...)` |
| Header | `X-Tenant-Id: tenant-a` | `@RequestHeader("X-Tenant-Id") String tenantId` | `.header("X-Tenant-Id", "tenant-a")` |
| JSON body | `{"title":"Java","pages":220}` | `@Valid @RequestBody BookRequest body` | `.contentType(APPLICATION_JSON).content(json)` |

Cùng một tên `id` có thể xuất hiện ở path, query, header hoặc JSON, nhưng **không tự động trở thành một giá trị duy nhất**. Mỗi annotation quy định nơi Spring MVC phải đọc dữ liệu.

Đừng đánh đồng **HTTP request** với **Java method call**: khi gọi trực tiếp `controller.getBook(42, "vi", "tenant-a")`, bạn **bỏ qua** route matching, header resolver, JSON converter, validation và phần lớn Spring MVC infrastructure. Để kiểm tra binding của Spring MVC, hãy gửi request qua `MockMvc.perform(...)` hoặc HTTP client.

### Hình dung luồng xử lý

```text
MockMvc.perform(...)
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping: chọn @GetMapping / @PostMapping
    |
    +--> HandlerAdapter / ArgumentResolvers
    |      @PathVariable     -> Long
    |      @RequestParam     -> String, int, List<String>, ...
    |      @RequestHeader    -> String / HttpHeaders / ...
    |      @RequestBody      -> HttpMessageConverter -> Java object
    |                                   |
    |                                @Valid
    v
BookController
    |
    v
BookService (mock trong @WebMvcTest)
    |
    v
ResponseEntity / Java object
    |
    v
HttpMessageConverter -> JSON response
```

Kiểm thử nên quan sát **cả inbound contract** (request được parse đúng và đúng method được chọn) lẫn **outbound contract** (status/JSON/header trả về đúng). Mockito `verify(...)` có thể chứng minh controller truyền đúng tham số tới service, nhưng assertion trên HTTP response vẫn cần thiết.

## 3. Chọn mức kiểm thử Spring MVC phù hợp

Có ba lựa chọn thường gặp:

| Mức test | Cấu hình | Điều gì có thật? | Khi nào dùng |
| --- | --- | --- | --- |
| MVC slice | `@WebMvcTest(BookController.class)` + `MockMvc` | DispatcherServlet, binding, converter, validation và MVC config phù hợp với slice; service thường mock | Kiểm tra contract HTTP/controller nhanh và tập trung |
| Full Spring context + MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` | Context ứng dụng rộng hơn; request vẫn qua mock servlet | Kiểm tra nhiều bean nhưng không cần TCP server |
| HTTP server thật | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `TestRestTemplate`/HTTP client | Embedded server và socket, servlet stack, controller, beans | Test HTTP integration qua cổng thật |

**`@WebMvcTest` đã tự cấu hình MockMvc** khi dùng Servlet MVC stack phù hợp; không cần thêm `@AutoConfigureMockMvc` trong ví dụ slice. Ngược lại, `@SpringBootTest` mặc định dùng `webEnvironment = MOCK` nhưng **không tự động đảm bảo có bean MockMvc** nếu thiếu `@AutoConfigureMockMvc`.

Nếu ứng dụng có Spring Security trên classpath, MVC slice có thể nạp security filters; test cần setup authentication/CSRF theo chính sách hoặc dùng hỗ trợ `spring-security-test`. Chỉ thêm `.header("Authorization", "...")` không chứng minh có người dùng đăng nhập nếu không có filter xác thực phù hợp.

Trong bài, ta dùng Spring Boot 3.3.5 và `@MockBean` của Boot để mock service trong `@WebMvcTest`. Các phiên bản mới hơn có thể ưu tiên `@MockitoBean` của Spring Framework 6.2+; không trộn annotation mà không xét BOM.

## 4. Tạo một ứng dụng mẫu Java 17+ có thể chạy

Cấu trúc project:

```text
mvc-request-testing/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/mvc/
│   ├── MvcRequestApplication.java
│   ├── BookRequest.java
│   ├── BookView.java
│   ├── BookService.java
│   ├── InMemoryBookService.java
│   └── BookController.java
└── src/test/java/com/example/mvc/
    ├── BookControllerWebTest.java
    └── BookHttpTest.java
```

Có **một service giả lập in-memory** để toàn ứng dụng có thể khởi động khi chạy HTTP test. Trong `@WebMvcTest`, service đó không được đưa vào slice theo mặc định và được thay bằng Mockito mock để kiểm tra chính xác việc binding và tương tác.

### 4.1. Gradle configuration

`settings.gradle`:

```groovy
rootProject.name = 'mvc-request-testing'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

- `spring-boot-starter-web` cung cấp Spring MVC, Jackson JSON và embedded servlet server.
- `spring-boot-starter-validation` cung cấp Jakarta Bean Validation để `@Valid` trên request body có hiệu lực.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, MockMvc, Mockito và Spring Boot Test.
- `junit-platform-launcher` hỗ trợ test runtime theo cấu hình Gradle.

Dùng Gradle tương thích với Boot 3.3.x, JDK 17+ và kết nối dependency repository khi tải lần đầu. Nếu repository đã có Gradle Wrapper, dùng `./gradlew`; nếu không, dùng `gradle` từ Gradle đã cài.

### 4.2. Class ứng dụng

`src/main/java/com/example/mvc/MvcRequestApplication.java`:

```java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcRequestApplication.class, args);
    }
}
```

Package `com.example.mvc` là package cha của controller, service và test nên `@WebMvcTest`/`@SpringBootTest` có thể tự tìm primary configuration.

### 4.3. Request DTO và response DTO

`src/main/java/com/example/mvc/BookRequest.java`:

```java
package com.example.mvc;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record BookRequest(
        @NotBlank String title,
        @Min(1) int pages
) {
}
```

`src/main/java/com/example/mvc/BookView.java`:

```java
package com.example.mvc;

public record BookView(
        long id,
        String title,
        int pages,
        String language,
        String tenantId
) {
}
```

Dùng Java `record` giúp request/response có constructor, accessor, `equals` và `hashCode` dựa trên các thành phần; Jackson của Spring Boot 3.3.x hỗ trợ serialize/deserialize record. `@NotBlank` cấm title null/rỗng/chỉ khoảng trắng; `@Min(1)` yêu cầu số trang tối thiểu là 1.

Chú ý `record` ở đây chỉ để học binding; response trả tenant ID trong ví dụ không được coi là một thiết kế API an toàn mặc định. Hệ thống thật phải kiểm soát tenant từ danh tính đã xác thực, không tin một header do client tự khai báo.

### 4.4. Service contract và service in-memory

`src/main/java/com/example/mvc/BookService.java`:

```java
package com.example.mvc;

import java.util.List;

public interface BookService {
    BookView find(long id, String language, String tenantId);

    List<BookView> search(
            String query, int page, int size,
            List<String> tags, String tenantId);

    BookView create(String tenantId, BookRequest request);
}
```

`src/main/java/com/example/mvc/InMemoryBookService.java`:

```java
package com.example.mvc;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class InMemoryBookService implements BookService {
    @Override
    public BookView find(long id, String language, String tenantId) {
        return new BookView(
                id, "Book " + id, 100, language, tenantId);
    }

    @Override
    public List<BookView> search(
            String query, int page, int size,
            List<String> tags, String tenantId) {
        return List.of(new BookView(
                1L, "Java", 210, "vi", tenantId));
    }

    @Override
    public BookView create(String tenantId, BookRequest request) {
        return new BookView(
                1000L, request.title(), request.pages(), "vi", tenantId);
    }
}
```

Service trên là **fixture đơn giản cho việc khởi động ứng dụng**, không phải repository hay logic phân trang hoàn chỉnh. Phương thức `search` cố tình trả một kết quả cố định; mục tiêu bài là kiểm tra **binding query parameters tại controller**, không phải thuật toán tìm kiếm.

### 4.5. Controller nhận đủ path, query, header và JSON body

`src/main/java/com/example/mvc/BookController.java`:

```java
package com.example.mvc;

import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> getById(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi")
                    String language,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return ResponseEntity.ok(
                service.find(id, language, tenantId));
    }

    @GetMapping(
            value = "/search",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public List<BookView> search(
            @RequestParam("q") String query,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "10") int size,
            @RequestParam(name = "tag", required = false)
                    List<String> tags,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return service.search(
                query, page, size,
                tags == null ? List.of() : tags,
                tenantId);
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @RequestHeader("X-Tenant-Id") String tenantId,
            @Valid @RequestBody BookRequest request) {
        BookView result = service.create(tenantId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
```

Những điểm quan trọng:

- `@PathVariable("id") long id` nhận phần `42` trong `/api/books/42` và chuyển sang `long`. Nếu `id=abc`, MVC không chuyển được kiểu và phản hồi mặc định thường là **400 Bad Request**.
- `@RequestParam(name="lang", defaultValue="vi")` dùng `vi` nếu client không gửi `lang` (và theo cơ chế defaultValue, có thể áp dụng khi giá trị rỗng).
- `@RequestParam("q")` mặc định là **bắt buộc**; nếu thiếu query parameter, MVC có thể trả **400** trước khi gọi service.
- `@RequestParam("tag", required=false) List<String> tags` cho phép client gửi lặp `tag=mvc&tag=boot`. Controller chuẩn hóa trường hợp vắng thành danh sách rỗng.
- `@RequestHeader("X-Tenant-Id")` bắt buộc; thiếu header khiến MVC trả 400 theo xử lý mặc định.
- `@Valid @RequestBody BookRequest` yêu cầu JSON hợp lệ và validate title/pages; request body lỗi có thể trả 400 trước khi vào service.
- `consumes` mô tả media type đầu vào. Với POST gửi `text/plain` thay cho `application/json`, MVC phản hồi **415 Unsupported Media Type** theo cấu hình mẫu.
- `produces` mô tả media type response; `Accept` của client có thể ảnh hưởng content negotiation.
- `/search` là route literal, cụ thể hơn `/{id}`. Spring MVC chọn route cụ thể cho `/api/books/search`; thứ tự viết method trong source không phải cơ chế ưu tiên.

## 5. Cách gửi request trong MockMvc

MockMvc không tự gọi HTTP qua socket. Nó mô phỏng request servlet và đưa vào `DispatcherServlet`/Spring MVC infrastructure. API cơ bản:

```java
mockMvc.perform(
        get("/api/books/{id}", 42L)
                .queryParam("lang", "vi")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_JSON)
)
.andExpect(status().isOk())
.andExpect(jsonPath("$.id").value(42));
```

Đây là **đoạn mẫu rút gọn**, cần test đã inject `MockMvc`, các import từ `MockMvcRequestBuilders`, `MockMvcResultMatchers` và controller/service trong context.

### Các builder quan trọng

| API | Tác dụng | Cạm bẫy |
| --- | --- | --- |
| `get("/api/books/{id}", 42L)` | Tạo GET, mở rộng path variable qua URL template | Không dùng `.param("id", "42")` thay cho path variable |
| `.queryParam("lang", "vi")` | Thêm query parameter vào request URL | Khác JSON body |
| `.param("lang", "vi")` | Thêm servlet request parameter trực tiếp | Có thể không tạo query string y hệt client HTTP thực |
| `.header("X-Tenant-Id", "tenant-a")` | Thêm HTTP header | Không thay thế xác thực/ủy quyền thật |
| `.headers(httpHeaders)` | Gắn một `HttpHeaders` đã tạo | Hữu ích khi cần nhiều header |
| `.contentType(MediaType.APPLICATION_JSON)` | Đặt Content-Type của **request body** | Không đồng nghĩa với `Accept` |
| `.accept(MediaType.APPLICATION_JSON)` | Nói client chấp nhận **response JSON** | Không làm JSON body tự tồn tại |
| `.content(json)` | Gửi byte/string vào request body | Cần Content-Type và JSON hợp lệ |
| `.characterEncoding("UTF-8")` | Đặt character encoding của request | Chỉ cần khi encoding là trọng tâm test |
| `.andExpect(status().isCreated())` | Assert HTTP status | Không thay thế assertion response content |
| `.andExpect(jsonPath("$.id").value(42))` | Assert trường JSON | Cần response thực sự là JSON |
| `.andDo(print())` | In request/response để debug | Tránh bật liên tục trong CI nếu log quá dài |

**`.param` và `.queryParam`:** với `@RequestParam` thông thường, cả hai thường cấp được giá trị cho resolver; `.queryParam` cũng bổ sung query string và thích hợp hơn khi muốn thể hiện URL mà client gửi. Không tự URL-encode thủ công nhiều lần rồi truyền vào builder: điều đó có thể gây **double-encoding**.

**`Content-Type` khác `Accept`:** client gửi JSON cần Content-Type phù hợp để Spring chọn converter; client muốn JSON phản hồi dùng Accept. Chỉ có `.accept(APPLICATION_JSON)` không khiến một string body được parse như JSON.

## 6. Bộ test MVC slice hoàn chỉnh: 10 test cases

Tạo file `src/test/java/com/example/mvc/BookControllerWebTest.java`. Test dùng `@WebMvcTest` để tạo MVC slice, `@MockBean` để mock dependency, và `ObjectMapper` để tạo JSON body chuẩn từ DTO. Mỗi test độc lập với DB hoặc server HTTP ngoài.

```java
package com.example.mvc;

import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerWebTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @MockBean
    BookService service;

    @Test
    void getBindsPathQueryAndHeader() throws Exception {
        BookView view = new BookView(
                42L, "Clean Code", 300, "en", "tenant-a");
        when(service.find(42L, "en", "tenant-a"))
                .thenReturn(view);

        mockMvc.perform(get("/api/books/{id}", 42L)
                        .queryParam("lang", "en")
                        .header("X-Tenant-Id", "tenant-a")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Clean Code"))
                .andExpect(jsonPath("$.language").value("en"))
                .andExpect(jsonPath("$.tenantId").value("tenant-a"));

        verify(service).find(42L, "en", "tenant-a");
    }

    @Test
    void getUsesDefaultLangWhenQueryIsMissing() throws Exception {
        when(service.find(7L, "vi", "tenant-a"))
                .thenReturn(new BookView(
                        7L, "Java", 100, "vi", "tenant-a"));

        mockMvc.perform(get("/api/books/{id}", 7L)
                        .header("X-Tenant-Id", "tenant-a")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("vi"));

        verify(service).find(7L, "vi", "tenant-a");
    }

    @Test
    void searchBindsRepeatedTagsAndPagination() throws Exception {
        List<BookView> results = List.of(new BookView(
                1L, "Java", 210, "vi", "tenant-a"));

        when(service.search(
                "java spring", 2, 5,
                List.of("mvc", "boot"), "tenant-a"))
                .thenReturn(results);

        mockMvc.perform(get("/api/books/search")
                        .queryParam("q", "java spring")
                        .queryParam("page", "2")
                        .queryParam("size", "5")
                        .queryParam("tag", "mvc", "boot")
                        .header("X-Tenant-Id", "tenant-a")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[0].title").value("Java"));

        verify(service).search(
                "java spring", 2, 5,
                List.of("mvc", "boot"), "tenant-a");
    }

    @Test
    void postReadsValidatedJsonBodyAndReturns201()
            throws Exception {
        BookRequest request = new BookRequest("Spring MVC", 240);
        BookView created = new BookView(
                100L, "Spring MVC", 240, "vi", "tenant-a");

        when(service.create("tenant-a", request))
                .thenReturn(created);

        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(request)))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(100))
                .andExpect(jsonPath("$.title").value("Spring MVC"))
                .andExpect(jsonPath("$.pages").value(240));

        verify(service).create("tenant-a", request);
    }

    @Test
    void rejectsNonNumericPathId() throws Exception {
        mockMvc.perform(get("/api/books/{id}", "abc")
                        .header("X-Tenant-Id", "tenant-a"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsMissingRequiredHeader() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42L))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsMissingRequiredSearchQuery() throws Exception {
        mockMvc.perform(get("/api/books/search")
                        .header("X-Tenant-Id", "tenant-a"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsInvalidJsonBodyBeforeService() throws Exception {
        BookRequest invalid = new BookRequest("", 0);

        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(invalid)))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsMalformedJson() throws Exception {
        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("title=Java"))
                .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(service);
    }
}
```

**Kỳ vọng: 10 test method PASS** trong class này với mã ứng dụng và dependencies được cấu hình đúng; các test chưa được thực thi tự động trong bài hướng dẫn. Khi test input không hợp lệ, `verifyNoInteractions(service)` xác nhận lỗi được chặn **trước khi business service được gọi**. Với request hợp lệ, `verify(service)...` xác nhận binding cuối cùng đúng đối số.

### Vì sao @WebMvcTest + @MockBean là lựa chọn phù hợp?

`@WebMvcTest(BookController.class)` chỉ tải hạ tầng/bean phù hợp với MVC slice, không tự nạp `InMemoryBookService` như một service thông thường. `@MockBean BookService` cung cấp một mock được Spring đưa vào context để controller inject được.

Trên Boot 3.3.x, mock bean thường được reset giữa các test theo hạ tầng Spring Boot Test, giúp test không giữ stubbing hoặc invocation history của test trước. Không cần khai báo `@ExtendWith(MockitoExtension.class)` cạnh `@WebMvcTest` để `@MockBean` hoạt động.

Trong Spring Framework 6.2+ / Boot 3.4+, xem cơ chế `@MockitoBean` khi cập nhật dependency; giữ đồng bộ với BOM của dự án thay vì copy annotation mới vào stack cũ.

## 7. Đọc và phân tích từng ca kiểm thử

### 7.1. Path variable: đúng type, đúng vị trí

`get("/api/books/{id}", 42L)` mở rộng path template thành `/api/books/42`. Spring MVC xử lý `@PathVariable("id") long id` và truyền `42L` cho controller.

Không dùng:

```java
get("/api/books").param("id", "42")
```

để thay thế `/api/books/42`. Hai URI này **khác nhau**, route `@GetMapping("/{id}")` không match URI không có segment ID.

Đối với `/api/books/abc`, Spring MVC match URL pattern nhưng không chuyển được `abc` sang `long`. Test `rejectsNonNumericPathId` mong `400`. Đây là **conversion error**, khác với `/api/unknown` không match route và thường thuộc tình huống 404/handler not found.

Với path variable chứa dấu cách hoặc ký tự đặc biệt, ưu tiên URI template/builder và kiểm tra encoding cụ thể. Không nối chuỗi tùy tiện bằng input người dùng để tạo request test.

### 7.2. Query parameter: mặc định, bắt buộc, lặp lại

`@RequestParam(defaultValue="vi")` hoạt động khi query thiếu `lang`, còn `@RequestParam("q")` yêu cầu có `q`. Với query số:

```http
GET /api/books/search?q=java&page=2&size=5&tag=mvc&tag=boot
X-Tenant-Id: tenant-a
```

Spring MVC chuyển `page` và `size` thành số nguyên, tập hợp `tag` thành `List<String>`. Test verify rằng service nhận `List.of("mvc", "boot")`.

Có thể gửi servlet parameter bằng:

```java
get("/api/books/search")
        .param("q", "java spring")
        .param("page", "2")
        .param("tag", "mvc", "boot");
```

Nhưng khi muốn test query string như HTTP client, `.queryParam(...)` thể hiện ý định sát hơn. Khi tham số lặp, Spring nhận nhiều giá trị; không mặc định gộp thành một chuỗi có dấu phẩy nếu contract thực sự yêu cầu danh sách. Cách parse một giá trị `tag=mvc,boot` có thể phụ thuộc converter, nên test riêng nếu API của bạn hỗ trợ dạng đó.

**Giá trị không hợp lệ:** `page=abc` không chuyển được sang `int`, thường dẫn đến `400`. Nếu muốn giới hạn `page >= 0`, `size >= 1`, cần thêm validation phù hợp ở tham số hoặc model, không giả định Spring MVC tự từ chối giá trị âm.

### 7.3. Header: request metadata không phải body

`@RequestHeader("X-Tenant-Id")` đọc HTTP header, không phải query hoặc JSON. Header name theo HTTP không phân biệt chữ hoa/chữ thường; `X-Tenant-Id` và `x-tenant-id` có ý nghĩa cùng tên header. Nhưng **giá trị header** vẫn phải tuân theo contract chính xác (tenant ID, correlation ID, API version...).

Có thể gửi nhiều header bằng:

```java
HttpHeaders headers = new HttpHeaders();
headers.add("X-Tenant-Id", "tenant-a");
headers.add("X-Correlation-Id", "trace-123");

mockMvc.perform(get("/api/books/{id}", 42L)
        .headers(headers));
```

Đây là đoạn rút gọn cần import `org.springframework.http.HttpHeaders`, MockMvc và controller. Không sử dụng header tenant do client gửi làm bằng chứng người dùng thuộc tenant đó: trong ứng dụng thật, cần kiểm tra xác thực/ủy quyền từ security context và các chính sách server-side.

Nếu muốn header không bắt buộc:

```java
@RequestHeader(name = "X-Correlation-Id", required = false)
String correlationId
```

Đây là cú pháp annotation minh họa trong chữ ký method, không phải method đầy đủ. Có thể dùng `defaultValue` khi API quy định fallback. Với header cần tồn tại, giữ `required=true` mặc định và test trường hợp thiếu.

### 7.4. Body: JSON, Content-Type, DTO, validation

POST trong ví dụ:

```http
POST /api/books HTTP/1.1
X-Tenant-Id: tenant-a
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":240}
```

`@RequestBody BookRequest` yêu cầu Jackson chuyển JSON thành Java record. `@Valid` kích hoạt Bean Validation đã được cấu hình; `title=""` hoặc `pages=0` sẽ làm request bị từ chối, mặc định `400`. Một JSON không đúng cú pháp cũng dẫn đến lỗi message conversion và thường `400`.

Trong MockMvc, dùng:

```java
.contentType(MediaType.APPLICATION_JSON)
.content(objectMapper.writeValueAsBytes(request))
```

để tránh sai dấu escape hoặc tên field khi tạo body JSON. Dùng literal JSON cũng được nếu test muốn kiểm tra payload khách hàng gửi thật, đặc biệt các trường thiếu, kiểu sai, unknown field hoặc malformed JSON.

**`@Valid` không thay thế business validation.** Nó kiểm tra các constraint có trong DTO. Nếu điều kiện là “mã sách không được trùng trong database” thì cần logic/service/repository kiểm tra riêng; test MVC slice không tự chứng minh database constraint.

### 7.5. Media type: 400, 415 và 406 khác nhau

| Tình huống | Response thông thường trong mẫu | Nguyên nhân |
| --- | --- | --- |
| `POST` với JSON hợp lệ, Content-Type JSON | 201 | Binding và validation thành công |
| `POST` với JSON cú pháp sai | 400 | Không parse được body |
| `POST` với JSON hợp lệ nhưng title rỗng/pages=0 | 400 | DTO validation thất bại |
| `POST` với `Content-Type: text/plain` | 415 | Không thỏa `consumes=application/json` |
| `GET` không có `X-Tenant-Id` | 400 | Thiếu required header |
| `GET /api/books/abc` | 400 | Không convert được path variable sang long |
| Client chỉ chấp nhận response khác `produces=application/json` | Có thể 406 | Content negotiation không thể đáp ứng `Accept` |

Các status trên dựa vào **exception handling mặc định** trong Spring MVC của project mẫu, chưa có `@ControllerAdvice` tùy biến. Nếu ứng dụng xử lý exception và trả lỗi riêng, hãy assert đúng hợp đồng của ứng dụng thay vì áp đặt một status mặc định.

`.accept(APPLICATION_JSON)` là nhu cầu về **response**; `.contentType(APPLICATION_JSON)` là metadata của **request body**. Một test có thể gửi `Accept: application/json` mà body lại `text/plain`; trong trường hợp `consumes=application/json`, request vẫn bị 415.

## 8. Test HTTP thực qua RANDOM_PORT

MockMvc đủ để kiểm tra routing/binding/MVC layer, nhưng không mở TCP connection. Để xác nhận controller hoạt động qua HTTP server thật, tạo thêm một lớp `@SpringBootTest` với `RANDOM_PORT`.

`src/test/java/com/example/mvc/BookHttpTest.java`:

```java
package com.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void sendsGetAndPostOverRealHttp() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Tenant-Id", "tenant-http");
        headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));

        HttpEntity<Void> getEntity = new HttpEntity<>(headers);

        ResponseEntity<BookView> found = restTemplate.exchange(
                "/api/books/42?lang=en",
                HttpMethod.GET,
                getEntity,
                BookView.class);

        assertEquals(HttpStatus.OK, found.getStatusCode());
        assertNotNull(found.getBody());
        assertEquals(42L, found.getBody().id());
        assertEquals("en", found.getBody().language());
        assertEquals("tenant-http", found.getBody().tenantId());

        headers.setContentType(MediaType.APPLICATION_JSON);
        BookRequest input = new BookRequest("HTTP Book", 150);

        ResponseEntity<BookView> created = restTemplate.exchange(
                "/api/books",
                HttpMethod.POST,
                new HttpEntity<>(input, headers),
                BookView.class);

        assertEquals(HttpStatus.CREATED, created.getStatusCode());
        assertNotNull(created.getBody());
        assertEquals("HTTP Book", created.getBody().title());
        assertEquals(150, created.getBody().pages());
    }
}
```

**Kỳ vọng: 1 test PASS.** TestRestTemplate dùng HTTP client gọi embedded server thật do Spring Boot khởi động trên port ngẫu nhiên. Vì `InMemoryBookService` là `@Service` và application root được scan, request chạy qua service in-memory thay vì Mockito mock của MVC slice.

Dùng URL tương đối như `/api/books/42?lang=en` với `TestRestTemplate` được Spring Boot Test cấu hình cho embedded server. Không hardcode port 8080. Khi cần tự xây URI có ký tự đặc biệt, dùng URI builder và xác minh encoding theo hợp đồng.

**Giới hạn:** test này vẫn sử dụng in-memory service, nên chưa kiểm tra database/transaction/business consistency thực. Nó kiểm tra HTTP ingress, binding và response trên server thật. Với test tạo dữ liệu thật, chú ý việc `@Transactional` trên test thread không tự rollback transaction ở server thread khi dùng RANDOM_PORT.

## 9. Chạy test và xác nhận kết quả

Có hai test class hoàn chỉnh:

| Class | Số test method | Kiểm thử |
| --- | ---: | --- |
| `BookControllerWebTest` | 10 | MockMvc MVC slice: path, query, header, body và các nhánh lỗi |
| `BookHttpTest` | 1 | GET + POST qua embedded HTTP server thật |

Tổng số **11 phương thức `@Test`** trong ví dụ. Các lệnh:

```bash
./gradlew test --tests 'com.example.mvc.BookControllerWebTest'
./gradlew test --tests 'com.example.mvc.BookHttpTest'
./gradlew test
```

Trên Windows dùng `gradlew.bat test` hoặc `.\gradlew.bat test` trong PowerShell. Nếu project không có Wrapper, dùng `gradle test` khi Gradle đã được cài.

Đầu ra Gradle có thể khác theo máy và phiên bản; không có stdout nghiệp vụ cố định. Khi chạy suite thành công, mở:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

Kiểm tra số test thực sự chạy, failed/skipped count và các exception cause. **Không nên tuyên bố đã kiểm thử toàn bộ ứng dụng production** chỉ vì 11 test của project mẫu PASS.

## 10. Thêm ca kiểm thử khi API thực tế phức tạp hơn

### 10.1. Một tham số query lặp lại và nhiều giá trị

`@RequestParam("tag") List<String> tags` có thể nhận `?tag=a&tag=b`. Dùng `.queryParam("tag", "a", "b")` và verify thứ tự/giá trị nếu đó là hợp đồng. Nếu API cho phép comma-separated value, test riêng `?tag=a,b` để kiểm tra converter thực tế; đừng suy hai kiểu mã hóa luôn tương đương.

### 10.2. Path variable có dấu cách hoặc slash

Khi ID là slug `"java basics"` hoặc chứa `/`, việc encode và route matching phức tạp hơn numeric ID. Hãy truyền URI template/`UriComponentsBuilder` đúng cách, tránh ghép chuỗi vào URL không encode. **Slash được encode** có thể bị server/proxy chặn hoặc xử lý khác; nên chọn thiết kế route an toàn thay vì cố che vấn đề bằng test MockMvc.

### 10.3. Header có nhiều giá trị

`@RequestHeader List<String>` hoặc `HttpHeaders` có thể dùng khi API cho phép nhiều giá trị. Test bằng `.header("X-Feature", "a", "b")` và assert resolver nhận đúng danh sách. Với header như `Authorization`, cần sử dụng security test infrastructure để kiểm tra danh tính, không dựa vào header thủ công như bằng chứng xác thực.

### 10.4. Multipart và form body khác JSON

`@RequestBody` JSON không phải cách duy nhất gửi body. `multipart("/upload").file(...)` phù hợp với `MultipartFile`; form URL-encoded thường dùng `@RequestParam`/`@ModelAttribute` với `Content-Type: application/x-www-form-urlencoded`. Không copy `.contentType(APPLICATION_JSON)` vào multipart rồi kỳ vọng resolver nhận file.

### 10.5. Nested JSON và validation

DTO có nested objects cần `@Valid` trên nested field phù hợp; danh sách object và các constraint khác có yêu cầu riêng. Dùng `ObjectMapper` serialize fixture có thể che lỗi trường sai tên từ client thật, vì object Java và server cùng một DTO. Bổ sung một số **literal JSON contract tests** cho field names/optional field/null/unknown field theo yêu cầu API.

### 10.6. Status và error format

Trong hệ thống thật, `@RestControllerAdvice` có thể chuyển lỗi binding thành JSON tiêu chuẩn:

```json
{"code":"INVALID_REQUEST","message":"pages must be >= 1"}
```

Đây là **payload ví dụ**, không phải output tự động của Spring Boot. Muốn assert `$.code` và `$.message`, phải triển khai advice phù hợp. Test chỉ assert 400 có thể đủ cho lỗi conversion đơn giản, nhưng API công khai thường cần bảo vệ cả error schema.

## 11. Các lỗi thường gặp khi viết MockMvc test

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `404 Not Found` | URL không match `@GetMapping`/`@PostMapping` | Kiểm tra `@RequestMapping` prefix, path template, HTTP method |
| `400 Bad Request` khi truyền id | `@PathVariable long` không parse được chuỗi | Kiểm tra URL segment/type, không thay bằng query |
| `400 Bad Request` vì thiếu header | `@RequestHeader` mặc định required | Truyền `.header(...)` đúng tên |
| `400 Bad Request` vì thiếu query | `@RequestParam` required | Dùng `.queryParam(...)` đúng key |
| `400 Bad Request` với JSON | JSON sai cú pháp hoặc DTO validation fail | Kiểm tra request body và `@Valid` |
| `415 Unsupported Media Type` | POST `consumes=application/json` nhưng Content-Type sai | Thêm `.contentType(APPLICATION_JSON)` |
| `406 Not Acceptable` | Client Accept không khớp `produces` | Kiểm tra `.accept(...)` |
| `No qualifying bean of type BookService` | MVC slice không nạp service | Thêm `@MockBean` đúng type cho Boot 3.3 |
| `401/403` trong app có Security | Filters/CSRF/authentication đang áp dụng | Dùng `spring-security-test` và setup đúng chính sách |
| `Wanted but not invoked` từ Mockito | Controller không gọi service hoặc mock khác instance | Xem resolved handler, arguments và dependency wiring |
| Test chỉ chạy trực tiếp controller nhưng không phát hiện lỗi header | Bỏ qua Spring MVC argument resolvers | Gửi request qua MockMvc |
| MockMvc PASS nhưng cổng HTTP không truy cập được | MockMvc không mở socket | Thêm RANDOM_PORT integration test |
| JSON field khác kỳ vọng | Mapping/Jackson/property naming sai | Assert `jsonPath` hoặc `content().json(...)` |
| Test PASS riêng nhưng FAIL theo suite | State fixture/context cache/concurrency | Kiểm tra cleanup và sự cô lập dữ liệu |

### Debug request chính xác

Trong lúc phát triển, thêm:

```java
mockMvc.perform(get("/api/books/{id}", 42L)
        .header("X-Tenant-Id", "tenant-a"))
    .andDo(print());
```

Đây là đoạn minh họa cần static import `org.springframework.test.web.servlet.result.MockMvcResultHandlers.print`. Output thường hiển thị request URI, headers, resolved handler, exception, status và response body, giúp tìm nguyên nhân. Chỉ bật có chọn lọc; đừng để log chứa token hoặc dữ liệu nhạy cảm.

Trong Spring Boot Test, khi xem log hãy phân biệt exception do **HandlerMapping** không match, do **argument binding** lỗi, do **JSON conversion/validation**, hay do **service thực sự ném exception**. Nếu chưa biết bước nào thất bại, đừng vội đổi status assertion để “cho PASS”.

## 12. Tiêu chí QA cho request-binding test

Trước khi merge một controller test, xác minh:

1. URL có đúng route và HTTP method không? Path variable truyền trong URI, không giả lập bằng query parameter.
2. Query parameter có tên và kiểu chính xác, có test default và missing required không?
3. Header bắt buộc có được gửi đúng, và test thiếu header có chặn service không?
4. `Content-Type` của request body có phù hợp `consumes`? `Accept` có phù hợp response `produces`?
5. JSON có đúng tên field, kiểu dữ liệu và schema theo API không?
6. `@Valid` có hoạt động với dependency validation trên classpath không?
7. Có assert **status và response body** thay vì chỉ verify một lời gọi không?
8. Với `@WebMvcTest`, dependency của controller đã mock/import đúng trong context chưa?
9. Lời `verify(service)...` có kiểm tra đúng các giá trị sau conversion và defaulting không?
10. Request không hợp lệ có được xử lý **trước khi gọi business service** không?
11. Test có security thì authentication/authorization/CSRF có được thiết lập đúng không?
12. Nếu hợp đồng cần TCP thật, đã có test `RANDOM_PORT` thay vì chỉ MockMvc chưa?
13. Bộ dữ liệu test có độc lập với test khác, không gọi database/API production ngoài ý muốn không?
14. Sau khi chạy, báo cáo test có đúng số lượng PASS/FAIL/SKIPPED kỳ vọng không?

## 13. Bài tập tự kiểm tra

Với project ở mục 4–9:

1. Thay `get("/api/books/{id}", 42L)` thành `get("/api/books").param("id","42")`. Dự đoán lỗi và giải thích khác biệt path variable/query.
2. Bỏ `.queryParam("lang","en")` ở test đầu. Nếu vẫn stub service với language "en", chuyện gì xảy ra? Sửa stub thành language mặc định "vi".
3. Thêm `.queryParam("size","abc")` vào search test. Viết assertion 400 và `verifyNoInteractions(service)`.
4. Bỏ header `X-Tenant-Id` trong POST. Vì sao status có thể 400 trước khi service được gọi?
5. Gửi JSON `{"title":"","pages":0}`. Tại sao phải có `spring-boot-starter-validation` để kiểm tra đúng constraint?
6. Đổi POST Content-Type thành `text/plain` và giữ JSON body. Phân biệt lỗi 415 với JSON malformed 400.
7. Bổ sung test `Accept: text/plain` với endpoint `produces=application/json`. Quan sát behavior 406 và vai trò của content negotiation.
8. Thêm một trường tùy chọn vào `BookRequest`, viết test body có/không có field và kiểm tra defaulting theo contract.
9. Mở rộng `BookHttpTest` gửi query parameter nhiều giá trị; kiểm tra kết quả khi qua server thật.
10. Nếu có Spring Security, áp dụng `@WithMockUser`/CSRF test support cho route được bảo vệ, thay vì chỉ header tự chế.

## 14. Tài liệu tham khảo

- [Spring Framework — Testing Spring MVC Applications](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): MockMvc, request builders, response assertions.
- [Spring Framework — @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/uri-variables.html): URI template variables và type conversion.
- [Spring Framework — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): query parameters, default, multiple values.
- [Spring Framework — @RequestHeader](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html): header binding.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): message converters, JSON binding và validation.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/): `@WebMvcTest`, `@SpringBootTest`, `@MockBean` và MockMvc/TestRestTemplate.

## 15. Tổng kết

Trong Spring MVC Testing, gửi request đúng nghĩa là để **DispatcherServlet** nhận URL, method, query string, headers và body, rồi quan sát cách Spring MVC resolve từng tham số. Dùng `get("/path/{id}", id)` cho **path variable**, `.queryParam(...)`/`.param(...)` cho **query parameter**, `.header(...)` cho **header** và `.contentType(...).content(...)` cho **JSON body**; `.accept(...)` diễn đạt media type response mà client chấp nhận.

Để có test đáng tin, hãy assert cả **HTTP status, JSON response và tham số service được gọi**, đồng thời kiểm tra nhánh lỗi conversion/validation/media type. `@WebMvcTest` + MockMvc giúp kiểm tra lớp MVC nhanh, có kiểm soát; `RANDOM_PORT` bổ sung bằng chứng về HTTP server thật khi cần. Giữ phạm vi test phù hợp, cô lập external dependencies và không nhầm việc controller method chạy đúng với việc **HTTP request đã được binding đúng**.
