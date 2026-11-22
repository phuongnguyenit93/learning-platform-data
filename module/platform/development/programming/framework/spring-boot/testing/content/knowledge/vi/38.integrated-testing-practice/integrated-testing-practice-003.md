# Kiểm thử Controller bằng @WebMvcTest và hợp đồng phản hồi trong Spring Boot

## 1. Mục tiêu: kiểm tra HTTP contract ở đúng ranh giới MVC

Một Controller trong Spring Boot không chỉ gọi service rồi trả về một Java object. Khi đi qua Spring MVC, dữ liệu còn chịu **request mapping**, chuyển đổi kiểu tham số, **JSON serialization/deserialization**, **Bean Validation**, exception handling, content negotiation, filters và HTTP status/headers. Viết unit test theo kiểu `new BookController(mockService).get(id)` chỉ kiểm tra một lời gọi Java; nó **không tự chứng minh** client sẽ nhận HTTP 200, 201, 400, 404, 409, 415 hay 406 đúng nghĩa.

`@WebMvcTest` được thiết kế để kiểm thử phần web MVC này **mà không khởi động toàn bộ ứng dụng** và không yêu cầu server HTTP thật. Với Spring Boot 3.5, nó cấu hình `MockMvc`, MVC infrastructure, `@Controller`, `@ControllerAdvice`, converter, filter và các thành phần web phù hợp; các service/repository thông thường không tự được nạp. Các collaborator cần thiết cho controller thường được thay bằng `@MockitoBean`.

Bài này thuộc nhóm **Thực hành tích hợp**. Đây là một *slice integration test*: nó dùng nhiều thành phần Spring MVC thật nhưng thay thế business dependencies. Người học cần nắm:

1. Chọn `@WebMvcTest(BookController.class)` và `MockMvc` để kiểm tra đúng ranh giới HTTP.
2. Dùng `@MockitoBean` để cô lập service nhưng vẫn kiểm thử Spring DI và MVC wiring.
3. Viết contract assertions cho **status**, **Content-Type**, **Location**, body JSON, collection shape và field values.
4. Kiểm tra `@RequestBody`, `@Valid`, `@NotBlank`, `@Size`, request media type và malformed JSON.
5. Kiểm tra `@RestControllerAdvice` trả lỗi có cấu trúc, dùng `ProblemDetail` với mã lỗi ổn định.
6. Phân biệt lỗi **không tìm thấy bản ghi** 404 với **không có route** 404; 400, 401/403, 406, 409, 415 là những hợp đồng khác nhau.
7. Dùng Mockito `given`, `verify`, `verifyNoInteractions` để chắc controller giao tiếp với service đúng tham số.
8. Phân biệt `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc`, `MockMvcBuilders.standaloneSetup` và server HTTP thật.
9. Tránh test giòn dựa vào toàn bộ JSON string, timestamp, thứ tự Map, thông điệp framework hoặc security configuration không được nạp.
10. Chạy đúng Gradle/JUnit test reports, không khẳng định pass khi ví dụ chưa được thực thi.

**Stack mẫu:** Java 17+, Spring Boot 3.5.8, Spring MVC, Jackson, Hibernate Validator/Bean Validation, JUnit Jupiter, Mockito, AssertJ và Gradle. Dự án hoàn chỉnh bên dưới không dùng database, Docker, cloud service hoặc network exporter. Nó có cả **14 bài test `@WebMvcTest`** và **2 bài `@SpringBootTest` có MockMvc** để thấy rõ hai mức tích hợp khác nhau. Mọi ví dụ runtime là **kỳ vọng thiết kế**, không phải kết quả build đã chạy trong môi trường này.

## 2. Phân biệt Controller unit test, MVC slice và full integration

```text
HTTP request giả từ MockMvc
      |
      v
DispatcherServlet + RequestMappingHandlerMapping
      |
      +--> argument conversion / @RequestBody Jackson
      +--> @Valid Bean Validation
      +--> HandlerInterceptor / servlet Filters nếu có
      |
      v
BookController thật
      |
      +--> BookService = @MockitoBean       [@WebMvcTest]
      |                   HOẶC
      +--> InMemoryBookService thật          [@SpringBootTest]
      |
      v
ResponseEntity<T> / @RestControllerAdvice
      |
      +--> HttpMessageConverter / Jackson
      +--> status, headers, Content-Type, JSON/problem+json
      |
      v
MockHttpServletResponse được MockMvc kiểm tra
```

| Phương án | Có Spring MVC thật? | Có Spring ApplicationContext? | Service có thật? | HTTP socket thật? | Phù hợp |
|---|---|---|---|---|---|
| `new BookController(mock)` | Không | Không | Mock | Không | Unit test quyết định trong method |
| `MockMvcBuilders.standaloneSetup(...)` | Một phần MVC do test tự cấu hình | Không cần full Boot context | Tuỳ gắn vào builder | Không | Controller standalone, wiring thủ công |
| `@WebMvcTest(BookController.class)` | **Có**, MVC slice | **Có**, thu hẹp | Thường dùng `@MockitoBean` | Không | HTTP contract của Controller |
| `@SpringBootTest + @AutoConfigureMockMvc` | Có | **Full Boot context** | Có thể là bean thật | Không với MOCK | Kiểm chứng Controller→Service wiring |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Có | Full context | Thật | **Có** | Gần end-to-end server transport |
| `@WebFluxTest` | **WebFlux**, không phải MVC | WebFlux slice | Mock/import phù hợp | Không | Reactive WebFlux controller |

**Không chọn cấp test chỉ vì tên annotation quen thuộc.** Nếu yêu cầu là kiểm tra route, JSON, validation và exception mapping, `@WebMvcTest` thường nhanh và đủ. Nếu yêu cầu là repository/JPA transaction/DB thật, `@WebMvcTest` sẽ không chứng minh được; cần slice dữ liệu hoặc full integration test riêng.

## 3. @WebMvcTest nạp những thành phần nào?

Spring Boot 3.5 `@WebMvcTest` được tối ưu cho Spring MVC:
- `@Controller` và `@RestController`.
- `@ControllerAdvice`/`@RestControllerAdvice`, nếu phù hợp component scan.
- Jackson `@JsonComponent`, converters và related web infrastructure.
- `Filter`, `HandlerInterceptor`, `HandlerMethodArgumentResolver`.
- `WebMvcConfigurer`, `WebMvcRegistrations` và một số MVC-related beans.
- `MockMvc` và có thể `MockMvcTester` (khi AssertJ support có mặt).
- Spring Security configuration/filter chain nếu Security có trên classpath.

Nó **không** tự nạp mọi `@Service`, `@Repository`, JPA EntityManager, datasource hoặc messaging client chỉ vì cùng package. Đây là lý do một constructor-injected service thường phải được `@MockitoBean` hoặc `@Import` khi test.

### 3.1. Controller phải là bean thật, service được mock

```java
@WebMvcTest(BookController.class)
class BookControllerSliceTest {

    @Autowired MockMvc mvc;

    @MockitoBean BookService books;

    // Các @Test sẽ gọi mvc.perform(...),
    // không gọi trực tiếp controller.getById(...).
}
```

Đây là fragment, full runnable class nằm ở phần 10. Import `@MockitoBean` là:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Với Spring Framework 6.2 và Spring Boot 3.5, đây là cách bean override hiện hành. Các ví dụ Boot cũ có `@MockBean` trong package Boot riêng; không trộn import/semantics từ Boot 4 hoặc Spring 7 vào project 3.5 một cách vô ý.

`@MockitoBean` thao tác trên **bean trong test ApplicationContext**, không phải một local Mockito mock được tạo riêng rồi lặng lẽ không inject vào Controller. Trong mock MVC slice, việc mock đúng `BookService` giúp controller constructor injection hoàn tất và mọi lời gọi service có thể được stub/verify.

### 3.2. Khi nào @Import thay vì @MockitoBean?

Có component web thật cần kiểm thử (ví dụ custom `Converter`, Jackson Module, `@ControllerAdvice` riêng, custom `WebMvcConfigurer`)? Có thể `@Import` đúng component/configuration đó vào slice nếu nó chưa được quét.

Nhưng nếu một service có 15 phụ thuộc DB/Kafka/HTTP client, `@Import(WholeApplicationConfiguration.class)` để “sửa context không load” sẽ làm slice nặng và sai mục tiêu. Nên mock collaborator tại ranh giới Controller và kiểm tra service trong bài riêng.

Một `@RestControllerAdvice` nằm cùng base package của `@SpringBootApplication` thường được slice scan tự đưa vào. Nếu advice ở package ngoài vùng scan, import nó tường minh và bảo đảm không có hai beans/handlers trùng nhau.

### 3.3. @WebMvcTest không cần @AutoConfigureMockMvc thêm

`@WebMvcTest` **đã** auto-configure `MockMvc`. Nếu dùng `@SpringBootTest(webEnvironment=MOCK)` và muốn `MockMvc` thì thêm:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullMvcTest {
    @Autowired MockMvc mvc;
}
```

Đây là fragment. `@AutoConfigureMockMvc` có `addFilters` để tùy chỉnh việc đăng ký filters, nhưng với security/authorization contract không nên đơn giản tắt filters rồi tuyên bố endpoint đã được bảo vệ.

## 4. “Hợp đồng phản hồi” phải được nêu rõ trước khi viết assertions

Hợp đồng HTTP không chỉ là `status().isOk()`. Nó thường gồm:

| Thành phần | Ví dụ endpoint GET /api/books/42 | Khi nào cần assert? |
|---|---|---|
| URL + HTTP method | GET /api/books/{id} | Routing contract |
| Path/query parameters | 42 hoặc `?author=Ada` | Argument binding |
| Request Content-Type | POST `application/json` | Request converter/consumes |
| Accept | `application/json` | Content negotiation/produces |
| Response status | 200, 201, 400, 404, 409 | Mọi scenario chính |
| Response Content-Type | `application/json` hoặc `application/problem+json` | Client parsing contract |
| Headers | `Location: /api/books/77` khi tạo | Create/redirect/cache/versioning |
| Body structure | object, array, problem detail | API schema |
| Body values | id, title, author; code/message | Business contract |
| Error mapping | `BookNotFoundException`→404 | `@RestControllerAdvice` |
| Validation | blank/too long fields →400 | Request contract |
| Side effects/collaborator | `books.create(request)` gọi đúng 1 lần | Controller-service boundary |
| Security/CORS | 401, 403, preflight headers | Chỉ khi Security/CORS có trong scope |

Chọn các assertions **ổn định và có chủ đích**. Tránh assert những thuộc tính server tự thay đổi như `Date`, request ID ngẫu nhiên, default stack trace, thứ tự keys trong JSON object hoặc message lỗi của framework không thuộc API public contract.

### 4.1. Phân biệt 200, 201 và 204

- **200 OK**: đọc thành công và trả body JSON phù hợp.
- **201 Created**: tạo resource, thường có `Location` trỏ tới resource mới; có thể kèm representation.
- **204 No Content**: thao tác thành công **không có response body**. Đừng trả `204` rồi mong MockMvc thấy JSON.
- **202 Accepted**: request đã được chấp nhận để xử lý async; không chứng minh công việc đã hoàn thành.
- **304 Not Modified**: dùng trong conditional requests/cache; không có body như 200.

Trong ví dụ, POST thành công trả 201 + Location + JSON body; không dùng 200 chỉ để đơn giản hóa test. Đây là một lựa chọn API rõ ràng; dự án thật cần tuân thủ hợp đồng đã công bố.

### 4.2. Lỗi client khác lỗi server

- **400**: JSON sai cú pháp, kiểu path argument không chuyển được, hoặc Bean Validation thất bại.
- **401**: chưa xác thực khi security policy yêu cầu.
- **403**: đã xác thực nhưng không có quyền, hoặc CSRF protection từ chối unsafe method.
- **404**: endpoint không tồn tại **hoặc** resource được tìm nhưng không tồn tại (phân biệt trong nội dung lỗi).
- **409**: xung đột state, ví dụ trùng title khi policy không cho phép.
- **415**: request gửi `Content-Type` không được `consumes` hỗ trợ.
- **406**: client `Accept` một media type không được endpoint `produces` hỗ trợ.
- **500**: lỗi hệ thống không được ánh xạ thành lỗi client; không đổi mọi exception thành 200/404.

**Không mock `BookService` để trả null rồi coi đó là 404.** Nếu controller không xử lý null, nó có thể trả 200 với body rỗng; đúng contract là service ném `BookNotFoundException`, advice biến nó thành HTTP 404 trong sample này.

## 5. Kiến trúc project: controller/service/advice/DTO

Cấu trúc các tệp độc lập:

```text
settings.gradle
build.gradle
src/main/java/com/example/bookapi/
    BookApiApplication.java
    BookView.java
    CreateBookRequest.java
    BookService.java
    InMemoryBookService.java
    BookNotFoundException.java
    DuplicateBookException.java
    BookController.java
    BookApiExceptionHandler.java
src/test/java/com/example/bookapi/
    BookControllerSliceTest.java
    BookApiFullContextTest.java
```

Tất cả cùng package `com.example.bookapi` để `@SpringBootApplication` tìm các components. Dự án:
- Dùng `record` Java 17 cho request/response rõ fields.
- Dùng Jakarta Bean Validation: `@NotBlank`, `@Size`.
- Dùng `ResponseEntity` cho 201 + Location.
- Dùng Spring `ProblemDetail` và `@RestControllerAdvice` cho lỗi có `code` ổn định.
- Có một service in-memory đủ để `@SpringBootTest` chạy **không cần DB**.
- `@WebMvcTest` thay service bằng Mockito mock để tập trung HTTP contract.
- Không có Spring Security trong `build.gradle` mẫu; security được bàn riêng ở mục 13.

## 6. Tạo project Java 17+ và Spring Boot 3.5.8

### 6.1. settings.gradle

```groovy
rootProject.name = 'book-api-mvc-contract'
```

### 6.2. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Tại sao có hai starters?**
- `spring-boot-starter-web`: Spring MVC, Servlet infrastructure và Jackson HTTP message converters.
- `spring-boot-starter-validation`: Hibernate Validator/Jakarta Bean Validation runtime; nếu thiếu, `@Valid` có thể không hoạt động như mong muốn trong app.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, AssertJ, Spring Test/MockMvc và Hamcrest-related testing facilities.
- JUnit Platform Launcher là dependency runtime rõ ràng.
- Spring Boot BOM đồng bộ các phiên bản Spring Framework/JUnit/Mockito/Jackson; đừng copy ngẫu nhiên một `spring-test` version khác.

**Phiên bản là một ví dụ cố định**, không phải tuyên bố nó là Spring Boot mới nhất ở mọi thời điểm. Project cần Gradle wrapper tương thích (hoặc Gradle đã cài) để chạy lệnh. Tệp `build.gradle` **không tự sinh** `gradlew` và `gradlew.bat`.

### 6.3. BookApiApplication.java

```java
package com.example.bookapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApiApplication.class, args);
    }
}
```

Dùng class này làm Boot configuration root; `@WebMvcTest(BookController.class)` tìm được `@SpringBootConfiguration` từ package hierarchy. Đừng vô tình có nhiều `@SpringBootApplication` trong cùng test package khiến cấu hình được chọn không rõ.

## 7. Tạo request/response DTO và service contract

### 7.1. BookView.java: representation JSON

```java
package com.example.bookapi;

public record BookView(
        long id,
        String title,
        String author) {
}
```

Jackson serializes record này thành object có `id`, `title`, `author`. Các test dùng `jsonPath` để kiểm tra field name và giá trị, không so sánh toàn bộ JSON string như một chuỗi có thứ tự keys cố định.

### 7.2. CreateBookRequest.java: validation thuộc input contract

```java
package com.example.bookapi;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateBookRequest(

        @NotBlank
        @Size(max = 80)
        String title,

        @NotBlank
        @Size(max = 60)
        String author) {
}
```

Khi Controller dùng `@Valid @RequestBody CreateBookRequest`, Spring MVC deserialize JSON thành record rồi chạy Bean Validation. `title=""` hoặc `author=" "` không thỏa `@NotBlank`; một title dài quá 80 ký tự không thỏa `@Size(max=80)`. Test cần xác minh **HTTP 400** và một error contract ổn định, đồng thời **không gọi service** nếu validation đã fail.

Nếu request property null hoặc thiếu, Bean Validation `@NotBlank` vẫn xử lý trường null; với Jackson record canonical constructor, lưu ý khác biệt giữa missing và explicit null khi dự án dùng `@JsonProperty(required=...)` hoặc custom validation. Đừng coi mọi dạng JSON không đầy đủ có thông điệp lỗi y hệt nhau.

### 7.3. BookService.java: dependency tại ranh giới Controller

```java
package com.example.bookapi;

import java.util.List;

public interface BookService {

    BookView getById(long id);

    List<BookView> findByAuthor(String author);

    BookView create(CreateBookRequest request);
}
```

Controller chỉ phụ thuộc interface. Trong `@WebMvcTest`, Mockito cung cấp implementation để mock HTTP behavior; trong `@SpringBootTest`, Spring tạo `InMemoryBookService` thật.

### 7.4. BookNotFoundException.java

```java
package com.example.bookapi;

public final class BookNotFoundException
        extends RuntimeException {

    public BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}
```

### 7.5. DuplicateBookException.java

```java
package com.example.bookapi;

public final class DuplicateBookException
        extends RuntimeException {

    public DuplicateBookException(String title) {
        super("Book title already exists: " + title);
    }
}
```

Exception message nội bộ có thể chứa dữ liệu đầu vào. **Trong API response**, sample dùng `ProblemDetail.detail` cố định để không trả lại input tùy ý hoặc để client phụ thuộc exception message. Đây là một quyết định tốt cho ổn định contract và hạn chế data exposure.

### 7.6. InMemoryBookService.java: implementation đủ để chạy full-context test

```java
package com.example.bookapi;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class InMemoryBookService implements BookService {

    private final Map<Long, BookView> books =
            new ConcurrentHashMap<>();

    private final AtomicLong nextId =
            new AtomicLong(100);

    @Override
    public BookView getById(long id) {
        BookView found = books.get(id);

        if (found == null) {
            throw new BookNotFoundException(id);
        }

        return found;
    }

    @Override
    public List<BookView> findByAuthor(String author) {
        String filter = author == null
                ? ""
                : author.trim();

        return books.values().stream()
                .filter(book ->
                    filter.isEmpty()
                        || book.author().equalsIgnoreCase(filter))
                .sorted(Comparator.comparingLong(BookView::id))
                .toList();
    }

    @Override
    public synchronized BookView create(
            CreateBookRequest request) {

        String title = request.title().trim();
        String author = request.author().trim();

        boolean duplicate = books.values().stream()
                .anyMatch(book ->
                    book.title().equalsIgnoreCase(title));

        if (duplicate) {
            throw new DuplicateBookException(title);
        }

        long id = nextId.incrementAndGet();

        BookView saved = new BookView(id, title, author);
        books.put(id, saved);

        return saved;
    }
}
```

Đây là **in-memory teaching implementation**, không phải production repository. `synchronized` bảo vệ chuỗi kiểm tra duplicate→insert trong một JVM. Nó không thay thế **unique constraint và transaction** của database trong hệ thống thật. `ConcurrentHashMap` dùng để đọc an toàn hơn khi các HTTP calls độc lập; response list được sắp theo `id` để có order ổn định ở full-context test.

Đối với slice test, service thật **không được dùng**: Mockito mock quyết định từng case và Controller phải diễn giải kết quả thành HTTP response chính xác.

## 8. BookController.java: các contract GET/list/POST

```java
package com.example.bookapi;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(
    path = "/api/books",
    produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {

    private final BookService books;

    public BookController(BookService books) {
        this.books = books;
    }

    @GetMapping("/{id}")
    public ResponseEntity<BookView> getById(
            @PathVariable long id) {

        return ResponseEntity.ok(books.getById(id));
    }

    @GetMapping
    public ResponseEntity<List<BookView>> list(
            @RequestParam(defaultValue = "") String author) {

        return ResponseEntity.ok(
                books.findByAuthor(author));
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @Valid @RequestBody CreateBookRequest request) {

        BookView saved = books.create(request);

        URI resourceUri = URI.create(
                "/api/books/" + saved.id());

        return ResponseEntity.created(resourceUri)
                .body(saved);
    }
}
```

Đọc contract:
- GET `/api/books/42` gọi `books.getById(42)`; trả HTTP 200 và JSON BookView.
- GET `/api/books?author=Ada` lấy đúng query parameter `author`, trả HTTP 200 và **JSON array**.
- GET `/api/books` truyền `author=""` theo default.
- POST `/api/books` chỉ nhận `application/json`, deserializes `CreateBookRequest`, validates rồi gọi `books.create(request)`.
- POST thành công trả **201 Created**, header `Location: /api/books/{id}` và JSON body của resource mới.
- Nếu service ném `BookNotFoundException` hoặc `DuplicateBookException`, exception được `@RestControllerAdvice` chuyển thành lỗi HTTP.

**Không dùng Controller trả `null` để báo không thấy bản ghi.** Tránh để client phải đoán giữa 200-empty, 204 và 404; hợp đồng phải thống nhất.

### 8.1. @Valid phải nằm đúng chỗ

Với `@Valid @RequestBody CreateBookRequest request`, Bean Validation hoạt động sau Jackson deserialization và trước lời gọi service. `@Valid` **không tự chạy** nếu bạn đơn giản `new BookController(...).create(request)` trong một unit test Java. Vì vậy `MockMvc` có giá trị: nó đi qua Spring argument resolver và validation infrastructure thật.

Đối với `@PathVariable`/`@RequestParam` cần `@Positive`, `@Min`, custom constraints hoặc class-level `@Validated` phù hợp với phiên bản Spring 6.2, phải xác định rõ method validation semantics. Dự án mẫu chỉ dùng conversion `long` cho path ID; `id="not-a-number"` được MVC phát hiện là request 400 do type mismatch.

### 8.2. Content negotiation diễn ra trước Controller trong một số cases

GET handler được định nghĩa `produces=application/json`. Khi client gửi `Accept: application/xml` mà app không hỗ trợ XML representation, MVC có thể trả 406 trước khi service được gọi. POST có `consumes=application/json`; khi client gửi `Content-Type: text/plain`, MVC trả 415. Test nên assert **service không bị gọi** trong các nhánh bị chặn tại MVC layer.

## 9. @RestControllerAdvice và ProblemDetail: lỗi có schema ổn định

Tệp `src/main/java/com/example/bookapi/BookApiExceptionHandler.java`:

```java
package com.example.bookapi;

import java.util.Comparator;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BookApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            BookNotFoundException exception) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Requested book does not exist");

        body.setTitle("Book not found");
        body.setProperty("code", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(body);
    }

    @ExceptionHandler(DuplicateBookException.class)
    public ResponseEntity<ProblemDetail> conflict(
            DuplicateBookException exception) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "A book with that title already exists");

        body.setTitle("Duplicate book");
        body.setProperty("code", "DUPLICATE_BOOK");

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidBody(
            MethodArgumentNotValidException exception) {

        var violations = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "message", error.getDefaultMessage() == null
                        ? "invalid"
                        : error.getDefaultMessage()))
                .sorted(Comparator.comparing(
                    item -> item.get("field")))
                .toList();

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body failed validation");

        body.setTitle("Invalid book request");
        body.setProperty("code", "VALIDATION_ERROR");
        body.setProperty("violations", violations);

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(body);
    }
}
```

**Tại sao dùng `ProblemDetail`?** Spring Framework 6 hỗ trợ RFC-style problem details với các trường chuẩn như `type`, `title`, `status`, `detail`, `instance`; Spring Jackson integration có thể serialize extension properties của `ProblemDetail` thành các JSON fields (ở đây `code`, `violations`).

Hợp đồng response mẫu cho 404 được hiểu như sau:

```json
{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "Requested book does not exist",
  "code": "BOOK_NOT_FOUND"
}
```

Đây là **biểu diễn tối thiểu minh họa** của những trường có ý nghĩa; serializer có thể bổ sung `instance` hoặc sắp xếp JSON keys khác. Test không so sánh toàn bộ string trên. `Content-Type` là `application/problem+json` theo response advice.

### 9.1. Vì sao không dùng default exception message làm public API?

Message từ `MethodArgumentNotValidException` và Spring MVC default error handling có thể thay đổi theo framework, locale hoặc validation provider. Nếu client dựa vào exact text dài của exception, nâng cấp Spring có thể làm contract test vỡ dù API semantics không đổi.

Giữ:
- `status` đúng chuẩn HTTP.
- `code` machine-readable ổn định (`BOOK_NOT_FOUND`, `DUPLICATE_BOOK`, `VALIDATION_ERROR`).
- `violations[*].field` tên input field ổn định theo schema.
- `detail` ngắn, không chứa nội bộ stack trace hoặc PII.

Validation `violations[*].message` có thể thay đổi với Bean Validation provider/i18n; nếu message không phải public contract, test chỉ nên kiểm tra danh sách field lỗi và code, không hard-code toàn bộ validator message.

### 9.2. Vì sao lỗi 400 malformed JSON khác validation 400?

- `{"title":"","author":""}`: JSON hợp lệ, DTO được tạo, `@Valid` fail → `MethodArgumentNotValidException`, advice mẫu trả ProblemDetail code `VALIDATION_ERROR`.
- `{broken`: JSON sai syntax → thường `HttpMessageNotReadableException`, **không** đi vào handler `MethodArgumentNotValidException` này. Spring MVC mặc định trả 400; nếu API yêu cầu cùng một ProblemDetail schema cho cả hai trường hợp, cần thêm handler phù hợp và test riêng.

Đừng viết test malformed JSON rồi assert `VALIDATION_ERROR` nếu chưa có mapping cho lỗi parse. Test mẫu chỉ assert 400 và `verifyNoInteractions(books)` ở nhánh malformed.

### 9.3. Class-level produces và problem+json

`@RequestMapping(produces="application/json")` giới hạn những media types mà handler thành công có thể cung cấp. Advice trả `application/problem+json` **khi có exception**. Khi test nhánh lỗi, đừng gửi `Accept: application/problem+json` một cách máy móc nếu mapping thành công chỉ declares JSON; để request dùng `Accept: */*` (mặc định không đặt Accept) rồi assert response problem+json. Khi thiết kế API production, xác định rõ content negotiation cho cả success và error representation.

## 10. @WebMvcTest thực hành: 14 tests cho HTTP contract

Tệp `src/test/java/com/example/bookapi/BookControllerSliceTest.java`:

```java
package com.example.bookapi;

import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    BookService books;

    @Test
    void getBookReturns200WithJsonContract() throws Exception {
        BookView book = new BookView(
                42L, "Domain-Driven Design", "Eric Evans");

        given(books.getById(42L)).willReturn(book);

        mvc.perform(get("/api/books/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title")
                .value("Domain-Driven Design"))
            .andExpect(jsonPath("$.author")
                .value("Eric Evans"));

        verify(books).getById(42L);
    }

    @Test
    void missingBookReturns404ProblemDetail() throws Exception {
        given(books.getById(404L))
            .willThrow(new BookNotFoundException(404L));

        mvc.perform(get("/api/books/{id}", 404))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.title")
                .value("Book not found"))
            .andExpect(jsonPath("$.detail")
                .value("Requested book does not exist"))
            .andExpect(jsonPath("$.code")
                .value("BOOK_NOT_FOUND"));

        verify(books).getById(404L);
    }

    @Test
    void listFilterPassesQueryParameter() throws Exception {
        given(books.findByAuthor("Ada")).willReturn(
                List.of(
                    new BookView(7L, "Algorithms A", "Ada"),
                    new BookView(9L, "Algorithms B", "Ada")));

        mvc.perform(get("/api/books")
                .param("author", "Ada")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].id").value(7))
            .andExpect(jsonPath("$[1].title")
                .value("Algorithms B"));

        verify(books).findByAuthor("Ada");
    }

    @Test
    void emptyCollectionIsArrayNotNull() throws Exception {
        given(books.findByAuthor("")).willReturn(List.of());

        mvc.perform(get("/api/books"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$", hasSize(0)));

        verify(books).findByAuthor("");
    }

    @Test
    void createReturns201AndLocation() throws Exception {
        CreateBookRequest request =
                new CreateBookRequest(
                    "Effective Java", "Joshua Bloch");

        given(books.create(request)).willReturn(
                new BookView(
                    77L, "Effective Java", "Joshua Bloch"));

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(request)))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                "Location", "/api/books/77"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(77))
            .andExpect(jsonPath("$.title")
                .value("Effective Java"))
            .andExpect(jsonPath("$.author")
                .value("Joshua Bloch"));

        verify(books).create(request);
    }

    @Test
    void invalidBodyReturnsFieldErrors() throws Exception {
        CreateBookRequest invalid =
                new CreateBookRequest("", " ");

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(invalid)))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_ERROR"))
            .andExpect(jsonPath(
                "$.violations[*].field",
                hasItems("title", "author")));

        verifyNoInteractions(books);
    }

    @Test
    void titleOverLimitReturns400() throws Exception {
        CreateBookRequest invalid =
                new CreateBookRequest("X".repeat(81), "Ada");

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(invalid)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_ERROR"))
            .andExpect(jsonPath(
                "$.violations[*].field",
                hasItems("title")));

        verifyNoInteractions(books);
    }

    @Test
    void duplicateReturns409WithStableCode() throws Exception {
        CreateBookRequest request =
                new CreateBookRequest("Clean Code", "Author");

        given(books.create(request)).willThrow(
                new DuplicateBookException("Clean Code"));

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(request)))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code")
                .value("DUPLICATE_BOOK"))
            .andExpect(jsonPath("$.detail")
                .value(
                    "A book with that title already exists"));

        verify(books).create(request);
    }

    @Test
    void malformedJsonReturns400WithoutCallingService()
            throws Exception {

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{ broken"))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(books);
    }

    @Test
    void unsupportedRequestContentTypeReturns415()
            throws Exception {

        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("a plain text book"))
            .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(books);
    }

    @Test
    void unacceptableRepresentationReturns406()
            throws Exception {

        mvc.perform(get("/api/books/{id}", 42)
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());

        verifyNoInteractions(books);
    }

    @Test
    void badPathVariableReturns400() throws Exception {
        mvc.perform(get("/api/books/{id}", "not-a-number"))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(books);
    }

    @Test
    void wrongRouteReturns404() throws Exception {
        mvc.perform(get("/api/unknown-books"))
            .andExpect(status().isNotFound());

        verifyNoInteractions(books);
    }

    @Test
    void unicodeTitlePreservedInJson() throws Exception {
        given(books.getById(8L)).willReturn(
                new BookView(
                    8L,
                    "Cấu trúc dữ liệu",
                    "Tác giả Việt"));

        mvc.perform(get("/api/books/{id}", 8))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Cấu trúc dữ liệu"))
            .andExpect(jsonPath("$.author")
                .value("Tác giả Việt"));

        verify(books).getById(8L);
    }
}
```

Có **14 methods `@Test`** trong class slice này. Tất cả giao tiếp với `MockMvc` qua request builders, để Spring MVC thực hiện mapping, argument conversion, validation, handler invocation và response serialization. Không bài nào gọi trực tiếp `controller.create(...)` rồi khẳng định nó là HTTP test.

### 10.1. Đọc test GET thành công theo từng tầng

```java
given(books.getById(42L))
    .willReturn(new BookView(42L, "ABC", "Author"));

mvc.perform(get("/api/books/{id}", 42))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));

verify(books).getById(42L);
```

Đây là fragment minh họa của một test.
- `given`: chuẩn bị điều kiện khi service được gọi.
- `mvc.perform`: gửi mock HTTP request qua DispatcherServlet.
- `status()`: HTTP response semantics.
- `jsonPath`: serialization/schema của JSON body.
- `verify`: service method được gọi đúng tham số, không bị controller thay đổi route argument.

Một test chỉ `verify(books).getById(42L)` **chưa đủ**: controller có thể trả HTTP 500 hoặc serialize sai body. Ngược lại, chỉ assert body mà không verify collaborator có thể bỏ sót bug route truyền sai ID vào service nếu mock stub quá rộng.

### 10.2. Vì sao dùng ObjectMapper để gửi JSON?

```java
.content(mapper.writeValueAsBytes(
    new CreateBookRequest("ABC", "Author")))
```

Đây là fragment. Nó tạo request JSON phù hợp với Java record, giảm lỗi escape dấu ngoặc, ký tự Unicode và đổi field names không đồng bộ. Nhưng khi **kiểm thử chính xác JSON wire format**, vẫn cần assertions về **keys và representation** độc lập với cùng ObjectMapper; nếu cả code dưới test và test writer cùng thay naming strategy, test có thể vẫn pass dù public API vô tình đổi.

Trong suite mẫu, response `jsonPath("$.title")`, `jsonPath("$.author")` chính là các assertions về contract public, không chỉ round-trip deserialize một DTO bằng cùng config.

### 10.3. Khi nào verifyNoInteractions quan trọng?

Với POST body không hợp lệ, malformed JSON, wrong Content-Type và unacceptable Accept, request phải bị chặn ở MVC layer trước khi Controller gọi service. `verifyNoInteractions(books)` chứng minh điều đó trong phạm vi mock bean.

Không áp dụng cứng `verifyNoMoreInteractions` cho mọi endpoint chỉ để tăng độ nghiêm ngặt: nếu service thêm một lời gọi hợp lệ không ảnh hưởng public contract, test có thể giòn. Dùng interaction verification khi tương tác là một phần yêu cầu (không ghi DB nếu request invalid, không gọi external adapter khi media type sai).

### 10.4. Tại sao không assert nguyên văn JSON response?

So sánh:

```java
.andExpect(content().json(
    "{\"id\":42,\"title\":\"ABC\",\"author\":\"Author\"}"))
```

Đây là fragment hợp lệ nhưng vẫn cần hiểu `content().json` có cơ chế JSON comparison, khác `content().string`. **Sai điển hình** là so sánh string thô kèm thứ tự property/whitespace. Tốt hơn dùng `jsonPath` cho những fields là hợp đồng, và dùng JSON comparison ở những trường hợp muốn xác nhận toàn bộ structure (cấu hình strict/lenient đúng mục tiêu).

Không dùng `content().string("{...}")` để “khóa thứ tự field” nếu API chưa hứa thứ tự đó; JSON object về mặt semantic không bảo đảm order.

## 11. @SpringBootTest: hai ca để thấy giới hạn của slice

`@WebMvcTest` kiểm tra Controller→Mock Service, nên nó **không** chứng minh một POST đã thực sự lưu dữ liệu và GET đọc lại được. Để xác nhận flow Controller→Service thật trong project in-memory, dùng `@SpringBootTest + @AutoConfigureMockMvc` với full context.

Tệp `src/test/java/com/example/bookapi/BookApiFullContextTest.java`:

```java
package com.example.bookapi;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class BookApiFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void fullContextPostThenGetWorks() throws Exception {
        String title = "Title-" + UUID.randomUUID();

        CreateBookRequest request =
                new CreateBookRequest(title, "Tester");

        String location = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(request)))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value(title))
            .andReturn()
            .getResponse()
            .getHeader("Location");

        assertThat(location)
                .startsWith("/api/books/");

        mvc.perform(get(location))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value(title))
            .andExpect(jsonPath("$.author")
                .value("Tester"));
    }

    @Test
    void fullContextUnknownBookReturns404()
            throws Exception {

        mvc.perform(get("/api/books/{id}",
                Long.MAX_VALUE))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("BOOK_NOT_FOUND"));
    }
}
```

Hai tests này dùng `InMemoryBookService` thật, không `@MockitoBean`. Tên title ngẫu nhiên giúp tránh đụng duplicate khi full Spring context được cache giữa test methods; test **không assert UUID cụ thể**, chỉ giữ lại giá trị đã dùng. Đây là context integration nhưng **không có DB thật**, nên không được quảng bá thành persistence integration test.

**Điểm thiết kế quan trọng:** Full context test có mutable in-memory store. Nếu chạy song song, cần kiểm soát fixture ownership và các assertions không phụ thuộc total record count hoặc execution order. Trong sample, test GET một ID gần tối đa `Long.MAX_VALUE`, không thể nhầm với ID do service phát sinh từ 100 trong kịch bản thực hành thông thường.

### 11.1. Khi nào nên dùng RANDOM_PORT?

Nếu muốn chứng minh TCP listener của embedded Tomcat/Jetty, Servlet container startup, network stack hoặc reverse-proxy-related behaviors, `@SpringBootTest(webEnvironment=RANDOM_PORT)` kết hợp HTTP test client sẽ gần thực tế hơn. Nhưng server xử lý request trên thread khác JUnit test thread; **test-managed `@Transactional` không tự bao phủ transaction của HTTP request**. Khi có DB, cần cleanup/transaction policy rõ.

Với hợp đồng Controller HTTP mapping, MockMvc thường đủ và nhanh hơn. Không phải mọi HTTP contract test đều cần mở socket.

## 12. Kiểm thử JSON schema và contract theo mức ổn định

### 12.1. JSON object vs JSON array

`GET /api/books/42` trả object:

```json
{
  "id": 42,
  "title": "Domain-Driven Design",
  "author": "Eric Evans"
}
```

`GET /api/books` trả array:

```json
[]
```

Đừng trả `null` thay cho array rỗng nếu client contract là collection. Test `jsonPath("$", hasSize(0))` bảo vệ điều này, không chỉ check 200.

### 12.2. Kiểm tra object field mà không quá phụ thuộc thứ tự

Với `jsonPath("$.id").value(42)` và `jsonPath("$.title").value(...)`, test kiểm tra keys/values cụ thể. Nếu public API cam kết một field bắt buộc luôn có, test nên assert nó tồn tại và đúng type. Có thể dùng:

```java
.andExpect(jsonPath("$.id").isNumber())
.andExpect(jsonPath("$.title").isString())
.andExpect(jsonPath("$.author").isString())
```

Đây là fragment có request builder và MockMvc result chain. Nếu API có nullability versioning, phải assert tương ứng với OpenAPI/JSON Schema contract; không chỉ dựa vào default Jackson behavior.

### 12.3. BigDecimal, Instant và enum khác string

Một API production có `BigDecimal amount`, `Instant createdAt` hoặc enum status:
- Tránh assert float bằng tolerance nếu JSON contract là decimal chính xác; có thể đọc response bytes vào `JsonNode`/BigDecimal.
- Assert UTC/ISO-8601 format nếu contract yêu cầu; inject `Clock` cho deterministic timestamps.
- Assert enum wire values (ví dụ `"ACTIVE"`) là hợp đồng, không dựa vào `toString()` nếu app dùng `@JsonValue`.
- Đặt timezone/locale có kiểm soát khi test date formatting; không sửa JVM global default trong concurrent suite.
- Khi dùng Jackson `@JsonProperty` và `@JsonInclude`, có test riêng cho field names và missing/null behavior.

Dự án mẫu giữ representation đơn giản, nhờ đó người học tập trung vào `@WebMvcTest` thay vì bị nhiễu bởi custom serializers.

### 12.4. Content-Type assertions cần phù hợp charset và version

Dùng `content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` khi muốn kiểm tra tương thích với JSON nhưng không khóa charset parameters không quan trọng. Khi contract yêu cầu **chính xác** `application/problem+json`, có thể assert content type tương ứng; với server/filter thêm charset, chọn match phù hợp.

Không chỉ `status().isOk()` rồi coi response đã dùng JSON converter; nếu controller vô tình trả HTML/text, client vẫn có thể lỗi mặc dù status là 200.

## 13. Spring Security/CSRF và filters trong @WebMvcTest

**Dự án mẫu không đưa `spring-boot-starter-security` vào classpath.** Vì vậy POST `/api/books` trong các test trên không bị CSRF protection mặc định từ Security cản trở. Trong ứng dụng thực đã dùng Spring Security, `@WebMvcTest` thường nạp security filters; cùng một POST có thể trả **403** nếu thiếu CSRF token hoặc **401** nếu authentication không hợp lệ.

### 13.1. Đừng tắt filters chỉ để test xanh

Anti-pattern:

```java
@WebMvcTest(BookController.class)
@AutoConfigureMockMvc(addFilters = false)
class TestWithoutSecurityFilters {
    // Bỏ filters không kiểm chứng security contract.
}
```

Đây là fragment minh họa. Nó có thể hữu ích khi mục tiêu **rõ ràng chỉ là controller mapping**, nhưng không được tuyên bố đã test authentication/authorization/CSRF. Nếu API có yêu cầu security, nên có một bộ tests riêng **giữ filters** để assert 401/403/200 đúng role.

### 13.2. Test Security đúng khi có dependencies

Để test endpoint có bảo vệ:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
testImplementation 'org.springframework.security:spring-security-test'
```

Đây là **fragment dependency bổ sung** cho dự án có Security, **không phải phần của build mẫu chạy ở mục 6**. Một ví dụ MockMvc request:

```java
mvc.perform(post("/api/books")
        .with(user("editor").roles("EDITOR"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content(validJson))
    .andExpect(status().isCreated());
```

Đây là fragment cần static imports `user`, `csrf`, `validJson` và security config tạo role policy đúng. **Không thể khẳng định 201 chỉ nhờ có user+csrf** nếu endpoint yêu cầu role khác hoặc authentication adapter khác; test phải cấu hình contract thật.

Với token-based stateless API, CSRF có thể bị disable theo security policy; hãy kiểm tra filter chain thực, không tự thêm `.with(csrf())` như một yêu cầu của mọi POST.

### 13.3. ControllerAdvice, filters và error contract

Một exception do Controller/service ném có thể đi qua `@ExceptionHandler` trong advice. Nhưng exception do **Servlet Filter** (ví dụ authentication filter) tạo có thể không đi qua cùng exception handler chain hoặc trả response theo `AuthenticationEntryPoint`/`AccessDeniedHandler`. Do đó error JSON schema cho 401/403 có thể khác 400/404/409 nếu application chưa đồng bộ cấu hình Security; cần test riêng.

CORS preflight `OPTIONS` cũng là HTTP contract; khi CORS policy được thiết kế, test `Origin`, `Access-Control-Request-Method`, `Access-Control-Allow-Origin` tại filter/MVC config thật. Không dùng HTTP status của GET thành công để suy ra CORS đúng.

## 14. Mocking không đồng nghĩa kiểm tra service business logic

`@MockitoBean BookService books` thay service thật bằng mock trong MVC slice. Có hai kết quả quan trọng:

1. **Lợi ích**: test không phụ thuộc database/remote API/logic phức tạp. Nó tập trung vào Controller HTTP mapping, validation, headers, error mapping.
2. **Giới hạn**: nếu `InMemoryBookService` có bug duplicate detection hoặc persistence repository ném exception không dự kiến, slice test có thể vẫn pass vì Mockito trả kết quả giả đúng như bạn stub.

Tách responsibilities:
- **Controller contract tests**: MockMvc + @WebMvcTest + mock collaborator.
- **Service unit tests**: new service + fake repo, business invariants, exceptions.
- **Repository slice tests**: `@DataJpaTest`/`@JdbcTest` với DB cấu hình phù hợp.
- **Full integration**: `@SpringBootTest` với real dependencies/containers nếu contract yêu cầu.
- **Consumer contract**: OpenAPI/JSON schema/provider-client verification nếu team bảo trì API công khai.

Không dùng một test `@WebMvcTest` duy nhất làm “bằng chứng end-to-end” cho toàn hệ thống.

### 14.1. Mockito stubbing đúng loại lỗi

```java
given(books.getById(404L))
    .willThrow(new BookNotFoundException(404L));
```

Đây là fragment. Controller gọi service và advice trả 404; test kiểm tra cả status lẫn machine-readable code. Nếu mock trả `null` hoặc exception khác, test không chứng minh đúng branch. Khi thêm exception handler, đừng bắt `Exception.class` rồi luôn chuyển thành 404: nó che lỗi 500 và biến sự cố hệ thống thành “record không tồn tại”.

### 14.2. @MockitoBean và Spring context cache

Một `@WebMvcTest` thường dùng Spring TestContext cache. Mockito mocks trong context có thể được reset bởi Spring Test listeners giữa test methods. Với một suite bật JUnit parallel execution, nhiều tests có khả năng dùng chung context/mock state: một test có thể stub/verify/reset trong lúc test khác chạy. Nếu gặp flaky verification:
- Mặc định giữ methods tuần tự trong cùng class có `@MockitoBean`, trừ khi mocks/fixture được cô lập thật.
- Không lạm dụng `@DirtiesContext` để reset mọi thứ vì gây bootstrap chậm và có thể phá tests concurrent khác.
- Tránh static mocks hoặc shared `MockMvc` helpers lưu mutable per-test state.
- Nếu có nhiều beans cùng type, dùng `@Qualifier`/name cho `@MockitoBean` hoặc refactor rõ collaborator, tránh mock nhầm bean.

Với Spring Framework 6.2, `@MockitoBean` có `enforceOverride=true` nếu bạn muốn **fail khi không tồn tại bean cần replace** thay vì âm thầm tạo mới; trong MVC slice, service thường không được scan nên mặc định REPLACE_OR_CREATE là phù hợp.

### 14.3. Mock quá mức khiến test thiếu giá trị

Đừng mock `MockMvc`, `ObjectMapper`, `RequestMappingHandlerAdapter`, `DispatcherServlet` và mọi converter chỉ để test Controller. Nếu mock luôn framework web internals, bạn quay về unit test Java nhưng tưởng đã kiểm tra HTTP semantics.

Ngược lại, đừng mock `BookController` trong `@WebMvcTest`: Controller phải là subject under test thật, chỉ mock collaborators ở ranh giới.

## 15. @WebMvcTest với exception handler, filter và custom serialization

Nếu Controller dùng:
- Custom `HandlerMethodArgumentResolver`: phải được slice nạp/import đúng.
- Custom `Converter<String, CustomId>`: test route argument conversion với actual converter.
- Jackson `Module`/custom serializer: import config mà production dùng và assert wire format.
- `@ControllerAdvice` ở package ngoài base scan: import advice cụ thể.
- `@ConfigurationProperties`: dùng `@EnableConfigurationProperties` hoặc `@Import` config theo đúng Boot docs.
- Spring Security configuration: giữ filter chain nếu test cần auth/CSRF/CORS.
- Locale/resolver: gửi `Accept-Language` và assert message nếu localized error contract là requirement.

**Nguyên tắc:** Không mở full application context mỗi khi slice thiếu một bean. Đầu tiên xác định bean đó có thuộc web contract thật không, sau đó import/mock **đúng ranh giới**. Đừng dùng `@ComponentScan` không giới hạn hoặc `@SpringBootTest` làm workaround vô thức khi mục tiêu còn là MVC slice.

### 15.1. Vì sao @WebMvcTest đôi khi fail "No qualifying bean"?

Nếu `BookController` constructor nhận `BookService`, slice không scan service `@Service`, nên Spring không có bean phù hợp. Fix đúng với bài test Controller:

```java
@MockitoBean
BookService books;
```

Không phải thêm `@Import(InMemoryBookService.class)` trừ khi test thực sự muốn dùng service thật (khi đó mục tiêu khác và có thể cần dependencies của service). Để giữ slice nhanh, mock service và viết service tests riêng.

### 15.2. Vì sao response có 404 nhưng advice không chạy?

Hai loại 404:
- `BookNotFoundException` do service ném khi `/api/books/42` route đã match; advice tạo ProblemDetail code `BOOK_NOT_FOUND`.
- `/api/unknown-books`: không có controller route phù hợp; Spring trả 404 theo default handling. Không có lý do để kỳ vọng advice xử lý `BookNotFoundException` trong trường hợp này.

Nếu API đòi mọi 404 theo cùng error schema, cần cấu hình no-handler/static-resource exception mapping phù hợp Spring Framework version và test riêng; không chỉ thêm một `@ExceptionHandler(BookNotFoundException.class)` rồi giả định nó bắt mọi route 404.

## 16. Anti-pattern: gọi trực tiếp Controller rồi xem là HTTP test

Sai ở mục tiêu:

```java
BookController controller = new BookController(books);
ResponseEntity<BookView> response =
        controller.getById(42L);
assertThat(response.getStatusCode().value())
        .isEqualTo(200);
```

Đây là fragment với `books` đã được tạo. Nó kiểm tra **Java method return value**; không đi qua:
- `@GetMapping` route resolution.
- `@PathVariable` conversion.
- `@RequestBody` và Jackson.
- `@Valid` argument validation.
- `@RestControllerAdvice` exception mapping.
- Servlet Filters/interceptors.
- Content negotiation và response JSON serialization.

Direct test có thể hữu ích cho logic không cần MVC, nhưng không phải chứng cứ hợp đồng HTTP. Khi user yêu cầu “Controller trả status 400 nếu body sai”, cần `MockMvc.perform(post(...))`.

## 17. Tests với status 401/403/404/409/415/406: đọc lỗi đúng lớp

| Status | Khi nào trong bài? | Tầng tạo status | Cần mock service? |
|---|---|---|---|
| 200 | GET BookView hoặc list | Controller + response conversion | Stub kết quả |
| 201 | POST CreateBookRequest hợp lệ | Controller ResponseEntity.created | Stub create |
| 400 | @Valid fail | MVC validation + advice | Không gọi service |
| 400 | Malformed JSON | HttpMessageConverter/MVC | Không gọi service |
| 400 | Path id không parse được long | Argument resolver/converter | Không gọi service |
| 404 | Service ném BookNotFoundException | Advice | Stub exception |
| 404 | URL không tồn tại | MVC handler mapping | Không gọi service |
| 409 | DuplicateBookException | Advice | Stub exception |
| 415 | POST text/plain trái consumes | MVC mapping/media type | Không gọi service |
| 406 | GET chỉ chấp nhận XML trái produces JSON | MVC content negotiation | Không gọi service |
| 401 | Không authenticated khi Security có mặt | Security filter/entrypoint | Phụ thuộc config |
| 403 | Không authorized hoặc thiếu CSRF token | Security filter/access denied | Phụ thuộc config |
| 500 | Unexpected server-side failure | Error handling pipeline | Không đổi thành 404/200 |

**Lưu ý response error schema:** Trong sample, 404 của `BookNotFoundException`, 409 và validation 400 có `application/problem+json` với `code`. Các 400 do parse/path, 406, 415 hoặc route 404 có thể dùng MVC default error handling và không bắt buộc có `code`. Đây là một **contract có chủ đích của ví dụ**; production API nếu yêu cầu một schema thống nhất phải thêm handlers/filters và tests tương ứng.

### 17.1. Một assertion quá yếu

```java
mvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{}"))
    .andExpect(status().is4xxClientError());
```

Đây là fragment. Nó có thể pass với 400, 403, 404, 405, 406 hoặc 415; nhưng những status đó khác nhau về ý nghĩa. Với validation contract, nên assert **400**, `VALIDATION_ERROR` và `title/author` fields nếu thực sự mong lỗi Bean Validation. Với security contract, assert 401 hoặc 403 đúng policy, không chỉ “4xx”.

### 17.2. Một assertion quá giòn

```java
assertThat(responseText).isEqualTo(
    "{\"title\":\"ABC\",\"id\":1,\"author\":\"Ada\"}");
```

Đây là anti-pattern fragment: thứ tự fields và whitespace là chi tiết serializer, không thuộc JSON semantic contract. Trừ khi API public hứa byte-level serialization (ví dụ signed payload), không nên snapshot nguyên chuỗi như vậy.

## 18. Gỡ lỗi khi @WebMvcTest không pass

| Triệu chứng | Nguyên nhân hay gặp | Cách xác nhận và sửa |
|---|---|---|
| `NoSuchBeanDefinitionException BookService` | Slice không scan @Service | Thêm @MockitoBean cho service |
| Context load quá nhiều beans/DB | @Import hoặc @ComponentScan quá rộng | Thu hẹp slice và dependency boundary |
| ControllerAdvice không áp dụng | Advice ngoài vùng scan, sai exception type | Kiểm tra scan/import, exception handler mapping |
| POST nhận 403 thay vì 201 | Spring Security CSRF/filter đang bật | Dùng `spring-security-test`, auth+csrf đúng policy |
| GET nhận 401 | Security yêu cầu authentication | Test mock user/token hoặc chỉnh expectation |
| `status 415` khi gửi JSON | Quên Content-Type hoặc consumes khác | Gửi `contentType(application/json)` |
| `status 406` khi GET | Accept không phù hợp produces | Điều chỉnh Accept theo contract |
| `status 400` trước service | JSON parse/type conversion/validation | In `andDo(print())`, kiểm tra exception |
| POST invalid vẫn gọi service | Thiếu @Valid/validation starter | Kiểm tra `@Valid @RequestBody` và dependency |
| `jsonPath` không thấy field | Jackson naming/visibility/@JsonIgnore | Xem response body thực |
| `Location` null | Controller trả 200 thay vì created | Dùng ResponseEntity.created |
| Test 404 có JSON code khác | Nhầm route 404 với record 404 | Stub service exception và match route |
| 409 bị trả 500 | Advice thiếu handler DuplicateBookException | Thêm/kiểm tra @ExceptionHandler |
| `verifyNoInteractions` fail | Controller/service vẫn được gọi | Kiểm tra validation/mapping timing |
| Test chỉ pass một mình | Shared mock/context/global state trong parallel suite | Cô lập fixtures, tránh parallel shared Mockito |
| `@WebMvcTest` có 2 Boot configurations | Multiple @SpringBootConfiguration | Chỉ định context root đúng package |
| Application có WebFlux và MVC | Boot lựa chọn web app type | Dùng đúng @WebMvcTest cho Servlet MVC |
| `@MockBean` import không hợp version | Spring Framework/Boot API drift | Boot3.5 ưu tiên @MockitoBean |
| Response 500 khi serializing DTO | Jackson module/missing getters/record mapping | Test ObjectMapper/MVC converter thực |
| Mock returns null vì unstubbed | given(...) không match argument | Stub chính xác, verify argument |
| Filter custom bị bỏ qua | Test tắt addFilters hoặc filter bean chưa scan | Bật/import đúng filter khi là HTTP contract |
| `@SpringBootTest` chạy chậm hơn slice | Nạp full Spring context | Dùng @WebMvcTest cho MVC-only contract |
| Task `NO-SOURCE` hoặc 0 tests | Gradle/JUnit discovery/filter sai | Kiểm tra useJUnitPlatform, report/test names |

### 18.1. MockMvc andDo(print()) để thấy thực tế

Khi debug một test khó, tạm thêm:

```java
mvc.perform(get("/api/books/{id}", 42))
        .andDo(print())
        .andExpect(status().isOk());
```

Đây là fragment, cần static import `org.springframework.test.web.servlet.result.MockMvcResultHandlers.print`. Output sẽ cho thấy request/handler/resolved exception/response fields phù hợp. Không đưa `print()` ồ ạt vào mọi test trên CI nếu logs chứa dữ liệu nhạy cảm; dùng khi cần chẩn đoán.

### 18.2. Lỗi JSON assertion khác lỗi service

Nếu `verify(books).getById(42L)` pass nhưng `jsonPath("$.title")` fail:
- Mapping vào Controller có thể đã đúng.
- Chưa chắc lỗi business service, vì service đang mock.
- Kiểm tra Jackson serialization, response DTO, naming strategy, @JsonIgnore, converter, response media type.
- Đọc `MockHttpServletResponse.getContentAsString()` khi debug, không cập nhật expected value tùy tiện để làm test xanh.

Ngược lại, nếu status 404 trước khi Mockito được gọi, có thể route không match; kiểm tra request method/path/produces/consumes trước khi nghi service.

## 19. Kiểm thử cùng một contract theo chiều âm và dương

Một ca **positive** thường chỉ chứng minh request hợp lệ hoạt động. Để có coverage chất lượng:
- GET tồn tại: 200 + object JSON + exact route ID.
- GET không tồn tại: 404 + ProblemDetail code ổn định.
- GET list có filter: 200 + JSON array + query parameter vào service.
- GET list rỗng: 200 + `[]`, không null.
- POST hợp lệ: 201 + Location + body.
- POST blank fields: 400 + validation fields, không gọi service.
- POST quá dài: 400 + title validation.
- POST trùng: 409 + conflict code.
- Malformed JSON: 400, không gọi service.
- Wrong Content-Type: 415.
- Unsupported Accept: 406.
- Path ID sai kiểu: 400.
- Route không tồn tại: 404, phân biệt record 404.
- Unicode: không bị sai encoding.
- Full context: POST→GET qua service thật, để nhận ra lỗi nằm dưới Controller slice.

Đây không phải danh sách status phải “tick cho đủ” ở mọi API. Với endpoint nào chỉ GET, không tự tạo test POST; với API không có duplicate constraint, không gán 409 giả. Test matrix phải xuất phát từ hợp đồng resource và lỗi của hệ thống thật.

## 20. Một chính sách API contract tests để tránh kiểm thử giòn

### 20.1. Giữ machine-readable error codes

Client nên điều khiển logic dựa vào `status` + `code` công khai, không parse `detail` bản địa hóa. Nếu đổi `BOOK_NOT_FOUND` thành `NOT_FOUND_BOOK`, đó là **API breaking change** cần review/versioning hoặc backward compatibility.

### 20.2. Không đưa stack trace nội bộ ra lỗi JSON

`ProblemDetail` có thể chứa `detail` ngắn và URI `type` tham chiếu tài liệu lỗi; không cần exposing class names, SQL, filesystem paths hoặc credentials. Test `jsonPath("$.code")` quan trọng hơn assert full exception message.

### 20.3. Thay đổi API schema phải được phát hiện

Nếu `BookView.title` đổi thành `name`, test `$.title` nên fail vì client contract đã đổi. Không chỉ deserialize response vào BookView mới rồi assert object equals: nếu test model cùng đổi với production, test có thể bỏ qua breaking change. Với API public lớn, kết hợp OpenAPI diff/schema checks và consumer-driven contract tests.

### 20.4. Đừng trộn MockMvc controller test với DB assertions

Trong `@WebMvcTest`, không có real repository. Nếu test viết:

```java
assertThat(bookRepository.count()).isEqualTo(1);
```

Đây là fragment sai phạm vi (repository chưa tồn tại trong slice). Một test Controller phải tập trung HTTP response và service invocation. Việc insert/commit/rollback thuộc service/repository/full integration suite.

### 20.5. Tránh shared mutable mock state khi song song

JUnit parallel execution trong một cached Spring context có thể khiến Mockito stubbing/reset giữa tests đè nhau. Nếu suite có `@MockitoBean`, không coi nó là per-thread bean. Chạy class test với default sequential semantics hoặc thiết kế test context isolation, rồi mới tối ưu concurrency.

## 21. Thực hành nâng cấp theo yêu cầu mới

### 21.1. Thêm DELETE đúng hợp đồng 204

Nếu API định nghĩa `DELETE /api/books/{id}` trả 204 khi xóa thành công:
- Service có `delete(id)` hoặc xác nhận not found.
- Controller `@DeleteMapping("/{id}")` trả `ResponseEntity.noContent().build()`.
- Test success assert `status().isNoContent()` **và body trống**.
- Test not found assert 404 ProblemDetail.
- Nếu có Spring Security, kiểm CSRF/auth policy trên DELETE.

Không tự thêm endpoint vào sample trên để tránh nội dung lệch giữa file/controller/test; đây là bài tập mở rộng.

### 21.2. Thêm pagination/query filters

Nếu `GET /api/books?page=0&size=20`:
- Test `@RequestParam` chuyển integer đúng.
- Test invalid `page=-1`/size>max nếu business validation có triển khai.
- Body có `items`, `page`, `size`, `total` theo schema đã công bố.
- Assert order **chỉ khi** API contract bảo đảm order.
- Mock service đúng PageQuery; full DB pagination test thuộc data layer.

Không dùng `jsonPath("$[0]")` khi schema thực đã chuyển từ array thuần sang paged object.

### 21.3. Thêm ETag hoặc conditional GET

Nếu API hỗ trợ `ETag`, `If-None-Match`:
- Assert `ETag` response header.
- Request với `If-None-Match` phù hợp trả 304 nếu policy yêu cầu.
- 304 không kèm body.
- Cần nêu rõ ETag do controller/filter/service nào tính; test slice chỉ nạp đúng component.
- Không assert ETag hash bất ổn nếu dùng timestamp/random data mà không kiểm soát.

## 22. Cách chạy Gradle/JUnit và đọc reports

Cần có Gradle wrapper tương thích với Spring Boot 3.5 và Java toolchain 17; nếu chưa có wrapper, dùng một Gradle installation phù hợp tạo wrapper. Project bài học cung cấp `settings.gradle`, `build.gradle`, source `java` và tests; **không** tự tạo `gradlew`.

Linux/macOS:

```bash
./gradlew test --tests "com.example.bookapi.BookControllerSliceTest"
./gradlew test --tests "com.example.bookapi.BookApiFullContextTest"
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.bookapi.BookControllerSliceTest"
.\gradlew.bat test --tests "com.example.bookapi.BookApiFullContextTest"
.\gradlew.bat test
```

Khi cần chẩn đoán một method:

```bash
./gradlew test --tests "com.example.bookapi.BookControllerSliceTest.invalidBodyReturnsFieldErrors" --info
```

**Dự kiến theo source:** 14 methods trong `BookControllerSliceTest` + 2 methods `BookApiFullContextTest` = **16 JUnit Jupiter `@Test` methods**. Không có `@Disabled` hoặc test intentionally flaky trong project. Không khẳng định 16 tests đã được chạy PASS trước khi Gradle thực thi.

### 22.1. Đọc reports chứ không chỉ BUILD SUCCESSFUL

Gradle HTML report:

```text
build/reports/tests/test/index.html
```

JUnit XML results:

```text
build/test-results/test/
```

Kiểm:
- Số tests **discovered**, executed, failed, skipped.
- `No tests found`, `NO-SOURCE`, `UP-TO-DATE`, `FROM-CACHE` trong Gradle task output.
- Tên JUnit test thực tế và stack traces.
- Thời gian context bootstrap, exception converter/validation, Mockito mismatches.
- Một test có được filter bởi `--tests`/tags hay không.

`BUILD SUCCESSFUL` với task cached/skipped chưa chứng minh mọi test vừa chạy trong lần build hiện tại. `--rerun-tasks` có thể dùng để loại nghi vấn Gradle up-to-date khi điều tra, nhưng không cần dùng cho mọi PR nếu CI cache được quản lý tốt.

### 22.2. Phân biệt lỗi build với lỗi HTTP contract

Nếu Gradle build fail vì không resolve được dependencies, đó chưa phải test HTTP thất bại. Nếu JUnit context fail ngay do thiếu bean, đó là **test configuration failure**, không phải Controller trả status 500. Nếu test body assertion fail, hãy kiểm `MockMvc` response/selected handler/resolved exception và `@ControllerAdvice` trước khi sửa business code.

## 23. Checklist QA cho hợp đồng phản hồi

- [ ] Có `@WebMvcTest(Controller.class)` giới hạn subject rõ ràng.
- [ ] Controller dưới test là bean thật, không được mock.
- [ ] Collaborators thuộc service layer được @MockitoBean/mock phù hợp.
- [ ] `MockMvc` được auto-configure, không tự giả định server socket đã chạy.
- [ ] Kiểm tra đúng URL, path, query và HTTP method.
- [ ] Có positive tests cho 200/201 tương ứng contract.
- [ ] Với POST 201, assert `Location` và body nếu API quy định.
- [ ] Response `Content-Type` tương thích JSON hoặc problem+json đúng nhánh.
- [ ] JSON field names/values/types được assert bằng jsonPath hoặc JSON-aware comparison.
- [ ] Empty collection được trả `[]` nếu public contract quy định.
- [ ] `@Valid @RequestBody` và validation starter hoạt động.
- [ ] Body invalid/malformed không gọi service.
- [ ] Phân biệt 400 do Bean Validation và 400 do JSON parse/type conversion.
- [ ] 404 record-not-found có code riêng; route-not-found được hiểu khác.
- [ ] 409 duplicate conflict được mapping bởi @RestControllerAdvice.
- [ ] Kiểm tra 415 khi request Content-Type sai và 406 khi Accept sai.
- [ ] Error schema có `status`, `title`, `detail`, `code` theo hợp đồng.
- [ ] Không expose internal exception message, SQL, stack trace hoặc PII.
- [ ] Assertions không khóa tùy tiện thứ tự JSON keys hoặc auto-generated timestamps.
- [ ] `verify(books).method(...)` đúng tham số khi tương tác là một phần contract.
- [ ] Không dùng `verifyNoInteractions` như tiêu chí mặc định cho mọi request.
- [ ] Nếu Spring Security hiện diện, test có auth/CSRF/filter chain đúng policy.
- [ ] Không dùng `addFilters=false` để tuyên bố endpoint đã bảo mật.
- [ ] Không nhầm @WebMvcTest với @WebFluxTest hoặc @SpringBootTest.
- [ ] Đã có service/full integration tests riêng cho persistence/business constraints.
- [ ] Mockito mocks/context cache không gây race khi JUnit chạy parallel.
- [ ] Classpath/Boot BOM/JUnit Launcher tương thích.
- [ ] Đã đọc JUnit reports thật trước khi báo runtime pass.

## 24. Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): phạm vi `@WebMvcTest`, `MockMvc`, `@MockitoBean`, `@AutoConfigureMockMvc` và test context.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): testing với Security/MockMvc.
- [Spring Framework 6.2 — @MockitoBean/@MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean override scopes, attributes, qualifiers.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): standalone/web application context setup, request builders và assertions.
- [Spring Framework — HTTP message conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): Jackson converters, content negotiation.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@RequestBody`, method validation.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse` và `@ExceptionHandler`.
- [Spring Framework — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): scope và exception mapping.
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): mock user, CSRF và filter integration.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `Test` tasks, filters, reports.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): JUnit 5 assertions, annotations và execution.

**Kết luận:** `@WebMvcTest` giúp kiểm chứng **hợp đồng HTTP** của Spring MVC Controller bằng framework web thật và service mock: route, conversion, validation, headers, JSON và mapping lỗi. Muốn test tốt, phải xác định rõ từng contract 200/201/400/404/409/415/406, kiểm tra status + body + headers + service interaction theo nhu cầu, và giữ error schema ổn định như ProblemDetail với `code` riêng. `@MockitoBean` giúp tập trung vào web layer nhưng không chứng minh persistence/service behavior; `@SpringBootTest + @AutoConfigureMockMvc` hoặc HTTP server thật là cấp test bổ sung khi cần. Đọc reports JUnit thực tế, không biến một test chỉ gọi trực tiếp method thành bằng chứng HTTP response đã đúng.