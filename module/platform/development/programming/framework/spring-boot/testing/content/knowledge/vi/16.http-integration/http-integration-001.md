# Chọn kiểm thử HTTP thật khi cần kiểm chứng embedded server trong Spring Boot

## 1. Bài toán: API đúng ở MockMvc, nhưng server thật vẫn có thể sai

Trong Spring Boot, rất nhiều test controller viết như sau:

```java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void getBook() throws Exception {
        mvc.perform(get("/api/books/7"))
           .andExpect(status().isOk());
    }
}
```

Đây là **mẫu minh họa**, cần thêm imports và collaborator phù hợp. Test này rất hữu ích để xác minh controller mapping, HTTP status và response body ở **mock servlet environment**. Nhưng **nó không khởi chạy embedded Tomcat/Jetty/Undertow, không mở cổng TCP, và không gửi HTTP thật qua network**.

Nếu rủi ro cần kiểm tra nằm ở phía **embedded server** — ví dụ server có mở cổng, endpoint thật có thể được gọi từ một HTTP client, cơ chế servlet container error dispatch có hoạt động, headers/cookies/redirects/serialization có đi qua HTTP transport đúng hay không — chỉ dùng mock request là **chưa đủ**.

Spring Boot cung cấp:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class BookHttpIntegrationTest {
    // HTTP client gọi server thật qua cổng được cấp.
}
```

Tổ hợp này yêu cầu Boot dựng **WebServerApplicationContext** và khởi động một **embedded web server** trên cổng ngẫu nhiên. Khi test dùng Java `HttpClient`, `TestRestTemplate` hoặc `WebTestClient` kết nối tới port ấy, request đi qua một HTTP transport thực chứ không chỉ đi qua MockMvc.

**Trọng tâm:** Không phải mọi endpoint đều cần test HTTP thật. Chọn mức kiểm thử theo **rủi ro cần chứng minh**. Kiểm tra controller/service logic bằng unit test hoặc mock MVC sẽ nhanh, rõ và ít phụ thuộc môi trường hơn. Chỉ mở embedded server khi sự tồn tại và hành vi của server/network stack thực sự thuộc hợp đồng muốn bảo vệ.

## 2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `@WebMvcTest`, `@SpringBootTest(webEnvironment=MOCK)`, `RANDOM_PORT`, `DEFINED_PORT` và `NONE`.
2. Diễn giải chính xác các tầng chạy thật trong mock request so với HTTP request qua embedded server.
3. Biết **khi nào MockMvc đủ** và **khi nào cần `RANDOM_PORT`** để kiểm chứng phần Servlet container/HTTP transport.
4. Viết test Java 17/Spring Boot 3.3 có cả `MockMvc` và Java `HttpClient` trên cùng một API.
5. Dùng `@LocalServerPort` và URL động, tránh cổng cố định và xung đột khi CI chạy song song.
6. Kiểm tra status, body JSON, `Location`, header do filter tạo và dữ liệu được lưu sau request qua server.
7. Phân biệt bản ghi được ghi trong test-managed transaction của MockMvc với transaction server-side khi gọi live HTTP.
8. Nhận biết các rủi ro: port collision, HTTP redirects, cookies, compression, TLS, HTTP/2, error pages, timeouts, security filter, context cache, dữ liệu test và external dependencies.
9. Lựa chọn chiến lược test cân bằng: nhiều test hẹp, một số ít live HTTP integration tests tại các luồng quan trọng.
10. Biết đọc lỗi startup, connection refused, 404/401/500 và kiểm tra đúng tầng thay vì mở rộng mọi test thành full integration.

## 3. Ba câu hỏi cần đặt ra trước khi chọn kiểu test

### Câu hỏi A — Tôi muốn chứng minh hành vi ở tầng nào?

- **Nghiệp vụ Java**: service tính giá/số dư, validation logic, mapping dữ liệu. Có thể test bằng JUnit thuần, fake/Mockito, **không cần Spring**.
- **Web layer**: route, request binding, JSON conversion, controller advice, HTTP status theo configuration đã nạp. `@WebMvcTest` + `MockMvc` thường đủ.
- **Spring Boot integration**: controller → service → repository và các bean thật trong context. `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` phù hợp nếu **không cần TCP**.
- **Embedded server và transport**: port, socket, HTTP client/server connector, servlet container behavior, request/response ngoài JVM call chain giả lập. Dùng `@SpringBootTest(RANDOM_PORT)` và **HTTP client thật**.
- **Môi trường deployment**: reverse proxy, load balancer, TLS termination, service mesh hoặc DNS production-like. Embedded server trên localhost **chưa đủ**; cần môi trường tích hợp lớn hơn.

### Câu hỏi B — Hành vi ấy có được mô phỏng chính xác trong MockMvc không?

`MockMvc` thực thi request qua **Spring MVC DispatcherServlet** và mock servlet request/response. Nó kiểm tra tốt nhiều tính năng Spring MVC, nhưng không khởi chạy servlet container thực.

Theo tài liệu Spring Boot, **hành vi servlet container cấp thấp** không thể được kiểm thử trực tiếp bằng MockMvc. Một ví dụ điển hình là **custom error page rendering** dựa trên cơ chế error-page support của servlet container. Nếu điều cần chứng minh nằm ở đó, mở embedded server mới cung cấp đúng ranh giới.

Tuy nhiên, nhiều hành vi như controller mappings, `@ControllerAdvice`, validation, custom filters đã được đăng ký và JSON serialization **có thể được kiểm chứng tốt bằng MockMvc**. Đừng dùng live HTTP chỉ vì endpoint trả JSON hoặc dùng Spring Security.

### Câu hỏi C — Hệ thống test có thể khởi động an toàn không?

`RANDOM_PORT` khởi động **full Boot application context**. Khi bean có startup jobs, external clients, database migrations, scheduler hoặc events, chúng có thể tham gia. Trước khi chạy HTTP thật, cần:

- Datasource test riêng, không dùng production database.
- Stub/mock những outbound services **không** thuộc mục tiêu test.
- Port ngẫu nhiên để giảm xung đột.
- Cleanup dữ liệu do request server-side đã commit.
- Không để startup runner gửi email/thanh toán thật.
- Timeouts hữu hạn và log đủ để truy nguyên lỗi.

**Một live HTTP test xanh không có giá trị nếu nó vô tình ghi vào tài nguyên production hoặc bỏ qua cleanup**.

## 4. `webEnvironment` của `@SpringBootTest`

| Giá trị | Có Spring Boot context? | Có web environment? | Embedded server TCP? | Dùng khi |
| --- | --- | --- | --- | --- |
| `MOCK` — mặc định | Có | Mock web environment nếu web stack có trên classpath | **Không** | Full context + `MockMvc`/mock `WebTestClient` |
| `RANDOM_PORT` | Có | WebServerApplicationContext thật | **Có**, cổng được chọn tự động | Kiểm chứng embedded server/HTTP thật |
| `DEFINED_PORT` | Có | WebServerApplicationContext thật | **Có**, cổng cấu hình hoặc mặc định 8080 | Chỉ khi phải dùng cổng xác định |
| `NONE` | Có | Không tạo web environment | **Không** | Service/application bootstrap không cần web |

`MOCK` không phải `NONE`: MOCK vẫn có Spring web infrastructure giả lập, phù hợp cho MockMvc. `NONE` bỏ web environment. Cả hai **không** có live HTTP listener.

Với `RANDOM_PORT`, Spring Boot cấu hình server chạy tại port ngẫu nhiên. Nếu bạn có application management server với cổng riêng, Boot có thể khởi động cả management server trên một cổng ngẫu nhiên **khác** — không được coi management port = application port.

### 4.1. `server.port=0` và `@LocalServerPort`

Một cách khác để yêu cầu cổng khả dụng là property `server.port=0`. Nhưng trong test tích hợp, `@SpringBootTest(RANDOM_PORT)` diễn đạt mục tiêu trực tiếp hơn.

Sau khi embedded server đã được khởi tạo, Spring Boot cung cấp actual port qua `@LocalServerPort`:

```java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
int port;
```

Trong Spring Boot 3.3, annotation này là một meta-annotation dựa trên `local.server.port`. Property chỉ có giá trị **sau khi server được khởi tạo**, nên không nên đọc nó quá sớm trong constructor/`@Bean` startup rồi giả định đã có port.

**Không gán cổng 8080 cứng trong CI.** Nhiều test processes, IDE hoặc services khác có thể chiếm cổng đó.

## 5. Đường đi của request: mock khác HTTP thật thế nào?

```text
Unit test service:
  JUnit -> new BookService(fake repo) -> Java methods
  Không có Spring HTTP.

Web MVC slice:
  JUnit -> MockMvc
         -> MockHttpServletRequest
         -> DispatcherServlet + controllers in MVC slice
         -> MockHttpServletResponse
  Không có embedded Tomcat/Jetty socket.

Full Boot MOCK:
  JUnit -> MockMvc
         -> mock Servlet objects
         -> DispatcherServlet + Boot controllers/services/repositories
         -> mock response
  Có full Spring context; không có TCP server.

Full Boot RANDOM_PORT:
  JUnit -> Java HttpClient / TestRestTemplate / WebTestClient
         -> TCP loopback socket
         -> embedded Tomcat/Jetty/Undertow
         -> servlet filters -> DispatcherServlet
         -> controller -> service -> repository/DB
         -> HTTP response bytes về client
  Có embedded server thật.
```

Đừng hiểu “MockMvc không dùng TCP” thành “MockMvc không dùng filters”. Trong `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc`, các servlet filters được đăng ký và được MockMvc cấu hình có thể thực thi. Phần không được chứng minh là **native container/network behavior**, không phải mọi tính năng web.

Đừng hiểu “HTTP thật” thành “mọi thành phần production thật”. Nếu bạn `@MockBean` một payment gateway, live request vẫn đi qua server thật nhưng gateway chỉ là fake. Bằng chứng đúng là **HTTP server + những bean không bị thay thế**, không phải tích hợp với payment provider production.

## 6. Khi nào nên mở embedded server thật?

Những tình huống có **giá trị bổ sung rõ** từ `RANDOM_PORT`:

1. **Server thật có bind cổng không?** Client ngoài có kết nối qua HTTP được không?
2. **Custom servlet container error handling** có đưa về status/body/error page kỳ vọng không? Spring Boot docs nêu đây là ví dụ không thể kiểm tra đầy đủ với MockMvc.
3. **Container-specific configuration:** servlet container, connectors, customizers, request size limits, compression và một số thuộc tính network cần kiểm tra trong HTTP transport.
4. **Headers/redirects/cookies qua wire:** ví dụ `Location`, `Set-Cookie`, response encoding theo cách client ngoài quan sát.
5. **End-to-end HTTP request lifecycle:** parse request HTTP, định tuyến, xử lý, trả status/body qua embedded server.
6. **Khác biệt request concurrency và async handling**: những vấn đề chỉ xuất hiện khi server thực điều phối nhiều request/callback.
7. **Sự tương thích HTTP client/server** khi test có một real client đã cấu hình.
8. **Ứng dụng trả health/readiness endpoint qua server** trong môi trường test có actuator/configuration tương ứng.
9. **Lỗi chỉ xuất hiện khi deploy server thật:** connector startup, port conflict, server-specific filters hoặc error dispatch.

### 6.1. Những việc thường không cần server thật

- Service calculation và guard clauses.
- Controller status/JSON/body mapping với service fake.
- Validation và `@ControllerAdvice` được cấu hình trong MVC slice.
- Spring Data repository query test.
- Chạy nhiều use cases nội bộ, nhưng không kiểm tra TCP.
- Mapper/serializer unit tests.
- Reactive operator tests với `StepVerifier`.
- Security policy ở mock web chain khi infrastructure được cấu hình đúng.

Với các trường hợp này, unit test, `@WebMvcTest`/`@WebFluxTest` hoặc `@SpringBootTest(MOCK)` thường đạt mục tiêu với thời gian và độ ổn định tốt hơn.

## 7. Ví dụ trọn bộ: cùng một API, ba tầng kiểm thử

Ta dựng ứng dụng **Java 17 + Spring Boot 3.3.0 + Spring MVC + Spring Data JPA + H2 test database**. API cho phép:

- `POST /api/books` tạo một sách, trả **201 Created**, `Location` và JSON của bản ghi.
- `GET /api/books/{id}` lấy sách, trả **200 OK**; ID không tồn tại trả **404 Not Found**.
- Một servlet filter thêm header `X-App-Filter: book-api`.

Sau đó chạy ba test class độc lập:

1. `BookControllerSliceTest` — MVC slice và service mock, test contract controller.
2. `BookMockIntegrationTest` — full Boot context + MockMvc + JPA thật, nhưng **không chạy embedded server**.
3. `BookHttpServerIntegrationTest` — Boot chạy **embedded server thật trên RANDOM_PORT**, Java 17 `HttpClient` gửi HTTP qua TCP, kiểm tra persistence/cleanup.

Vì sao chọn Java `HttpClient`? Nó có sẵn trong Java 17, không phải phụ thuộc Spring Test. Khi một lời gọi trả response, đó là **HTTP response từ server ở URL cụ thể**. Các dự án Boot 3.3 cũng có `TestRestTemplate`/`WebTestClient`, nhưng dùng một client không phụ thuộc Spring giúp ranh giới test dễ quan sát.

### 7.1. Cấu trúc dự án

```text
embedded-http-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── BookApplication.java
    │   ├── BookEntity.java
    │   ├── BookRepository.java
    │   ├── BookCreateRequest.java
    │   ├── BookView.java
    │   ├── BookService.java
    │   ├── BookController.java
    │   └── AppFilter.java
    └── test/java/example/
        ├── BookControllerSliceTest.java
        ├── BookMockIntegrationTest.java
        └── BookHttpServerIntegrationTest.java
```

### 7.2. Gradle settings

**`settings.gradle`:**

```groovy
rootProject.name = 'embedded-http-demo'
```

### 7.3. Gradle build

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Lưu ý về môi trường:** Bộ mã này dùng Spring MVC/Servlet + embedded Tomcat mặc định của starter-web, không phải WebFlux. JPA dùng H2 embedded để chạy demo độc lập; H2 **không bảo đảm** các SQL/locking/transaction semantics của database production. Với Gradle Wrapper tương thích (ví dụ Gradle 8.5), JDK 17 và truy cập Maven Central, có thể chạy các test. Trong production nên dùng phiên bản bảo trì Spring Boot được tổ chức hỗ trợ; `3.3.0` chỉ là mốc để ví dụ nhất quán.

### 7.4. Spring Boot entry point

**`src/main/java/example/BookApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookApplication.class, args);
    }
}
```

Đặt các classes trong package `example` để Boot scan controller/service/filter/entity/repository. `@SpringBootTest` không cần gọi trực tiếp `main` theo mặc định, nhưng vẫn tạo context qua `SpringApplication`.

### 7.5. JPA entity

**`src/main/java/example/BookEntity.java`:**

```java
package example;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class BookEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String title;

    protected BookEntity() {
        // JPA constructor
    }

    public BookEntity(String code, String title) {
        this.code = code;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getTitle() {
        return title;
    }
}
```

`jakarta.persistence` đúng với Spring Boot 3.x. `@GeneratedValue(IDENTITY)` tương thích H2 trong demo. Không cần dự đoán ID chính xác (1, 2...) vì ID có thể khác khi chạy suite.

### 7.6. Repository

**`src/main/java/example/BookRepository.java`:**

```java
package example;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<BookEntity, Long> {
    Optional<BookEntity> findByCode(String code);
}
```

`findByCode` dựa vào tên thuộc tính `code` của entity; Spring Data JPA tạo implementation ở runtime. Trong test HTTP thật, ta có thể query repository **sau request** để kiểm chứng server thực sự đã lưu dữ liệu.

### 7.7. Request và response DTO

**`src/main/java/example/BookCreateRequest.java`:**

```java
package example;

public record BookCreateRequest(String code, String title) {}
```

**`src/main/java/example/BookView.java`:**

```java
package example;

public record BookView(Long id, String code, String title) {}
```

Đây là Java 17 records. Jackson trong `spring-boot-starter-web` xử lý JSON body theo tên record components. Test không nên phụ thuộc thứ tự JSON keys.

### 7.8. Service nghiệp vụ

**`src/main/java/example/BookService.java`:**

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public BookView create(BookCreateRequest input) {
        if (input == null
                || input.code() == null
                || input.code().isBlank()
                || input.title() == null
                || input.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "code and title are required");
        }

        BookEntity saved = repository.save(
                new BookEntity(input.code(), input.title()));

        return new BookView(
                saved.getId(), saved.getCode(), saved.getTitle());
    }

    @Transactional(readOnly = true)
    public BookView get(Long id) {
        BookEntity book = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "book not found"));

        return new BookView(
                book.getId(), book.getCode(), book.getTitle());
    }
}
```

Phương thức `create` mở transaction ứng dụng qua proxy Spring khi gọi từ controller; `get` dùng read-only transaction. Lỗi thiếu dữ liệu được translate thành HTTP 400; ID không tồn tại thành HTTP 404 qua `ResponseStatusException`.

**Không suy luận rằng unique constraint violation chắc chắn thành 409 Conflict:** ví dụ chưa có `@ControllerAdvice` xử lý lỗi database. Nếu muốn contract 409, cần thiết kế exception mapping rõ ràng.

### 7.9. Controller HTTP

**`src/main/java/example/BookController.java`:**

```java
package example;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookView> create(
            @RequestBody BookCreateRequest request) {
        BookView created = service.create(request);
        URI location = URI.create("/api/books/" + created.id());

        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{id}")
    public BookView get(@PathVariable Long id) {
        return service.get(id);
    }
}
```

`ResponseEntity.created(location)` trả **201 Created** và `Location`, dùng relative URI theo ID vừa tạo. Kết quả body là JSON của `BookView`. Trong HTTP live test, kiểm tra header có suffix path đúng; không giả định server luôn giữ nguyên định dạng absolute/relative mà mọi client được phép quan sát.

### 7.10. Servlet filter

**`src/main/java/example/AppFilter.java`:**

```java
package example;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class AppFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        response.setHeader("X-App-Filter", "book-api");
        chain.doFilter(request, response);
    }
}
```

Filter này được Spring Boot đăng ký trong servlet web application. Nó sẽ xuất hiện cả ở full MockMvc test **khi filter được MockMvc cấu hình**, lẫn ở live HTTP server. Vì vậy **header có mặt không phải bằng chứng duy nhất rằng HTTP đã qua TCP**; bằng chứng TCP là client thật kết nối tới `127.0.0.1:port` do embedded server mở.

## 8. Test A — MVC slice với service mock, không có server

**`src/test/java/example/BookControllerSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerSliceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    BookService service;

    @Test
    void mapsGetAndSerializesResponse() throws Exception {
        when(service.get(7L))
                .thenReturn(new BookView(
                        7L, "BK-7", "Sách ví dụ"));

        mvc.perform(get("/api/books/{id}", 7L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.code").value("BK-7"))
                .andExpect(jsonPath("$.title").value("Sách ví dụ"));

        verify(service).get(7L);
    }
}
```

Bằng chứng của test này:

- Spring MVC nhận route `GET /api/books/7`, bind `id` thành `Long`.
- Controller trả status 200 và JSON fields đúng với dữ liệu được mock.
- Controller gọi đúng service mock theo ID.

**Không có JPA thật, không có embedded HTTP server.** Một route đúng ở test này chưa bảo đảm `BookService.get`/repository hoạt động hoặc server có thể nhận request từ network.

Trong Spring Boot 3.3, `@MockBean` thuộc `org.springframework.boot.test.mock.mockito`. Từ Boot 3.4 API này deprecated và khi nâng lên Boot 4 cần dùng Framework `@MockitoBean` cùng test modules/import phù hợp.

## 9. Test B — Full Boot context + MockMvc, có JPA nhưng không TCP

**`src/test/java/example/BookMockIntegrationTest.java`:**

```java
package example;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = BookApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
@AutoConfigureMockMvc
@Transactional
class BookMockIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    BookRepository repository;

    @Test
    void storesBookWithRealBeansWithoutTcp() throws Exception {
        String code = "mock-" + UUID.randomUUID();
        String json = mapper.writeValueAsString(
                new BookCreateRequest(code, "Sách mock MVC"));

        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(header()
                        .string("X-App-Filter", "book-api"))
                .andExpect(jsonPath("$.code").value(code))
                .andExpect(jsonPath("$.title")
                        .value("Sách mock MVC"));

        BookEntity saved =
                repository.findByCode(code).orElseThrow();

        assertEquals("Sách mock MVC", saved.getTitle());
    }
}
```

### Test B chứng minh điều gì?

- Boot nạp context gồm controller, service, filter, JPA repository và H2 database.
- MockMvc gọi qua Spring MVC DispatcherServlet và filters được cấu hình.
- HTTP status/JSON/controller/service/persistence **trong context** phối hợp đúng.
- Repository có thể truy vấn bản ghi được tạo trong **test-managed transaction**.
- `@Transactional` trên test method mặc định rollback giao dịch sau test (khi transaction manager phù hợp).

### Test B chưa chứng minh điều gì?

- Chưa mở embedded Tomcat socket.
- Chưa gửi HTTP request qua Java networking stack.
- Chưa kiểm tra port/HTTP connector/servlet container error dispatch.
- Chưa chứng minh transaction đã commit và được quan sát từ một request ngoài process; test hiện nằm trong một transaction của test method.

Đây là mẫu **full integration mà không cần HTTP thật**. Khi mục tiêu chỉ là controller-service-repository integration, nó thường nhanh và dễ cleanup hơn RANDOM_PORT.

## 10. Test C — `RANDOM_PORT` + Java `HttpClient`, đi qua embedded server

**`src/test/java/example/BookHttpServerIntegrationTest.java`:**

```java
package example;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = BookApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class BookHttpServerIntegrationTest {
    @LocalServerPort
    int port;

    @Autowired
    ServletWebServerApplicationContext webContext;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    BookRepository repository;

    private String createdCode;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    @AfterEach
    void cleanupCreatedBook() {
        if (createdCode != null) {
            repository.findByCode(createdCode)
                    .ifPresent(repository::delete);
        }
    }

    @Test
    void serverHasAnActualAssignedPort() {
        assertTrue(port > 0);
        assertEquals(port, webContext.getWebServer().getPort());
    }

    @Test
    void postAndGetCrossRealHttpAndCommitServerData()
            throws Exception {
        createdCode = "live-" + UUID.randomUUID();
        String title = "Sách HTTP thật";
        String payload = mapper.writeValueAsString(
                new BookCreateRequest(createdCode, title));

        HttpRequest createRequest = HttpRequest.newBuilder()
                .uri(uri("/api/books"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        payload, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> created = http.send(
                createRequest,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(201, created.statusCode());
        assertEquals(
                "book-api",
                created.headers().firstValue("X-App-Filter")
                        .orElse(""));

        BookView book =
                mapper.readValue(created.body(), BookView.class);

        assertNotNull(book.id());
        assertEquals(createdCode, book.code());
        assertEquals(title, book.title());

        assertTrue(created.headers()
                .firstValue("Location")
                .orElse("")
                .endsWith("/api/books/" + book.id()));

        BookEntity fromDatabase = repository
                .findByCode(createdCode)
                .orElseThrow();

        assertEquals(title, fromDatabase.getTitle());

        HttpRequest getRequest = HttpRequest.newBuilder()
                .uri(uri("/api/books/" + book.id()))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> fetched = http.send(
                getRequest,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(200, fetched.statusCode());

        BookView reloaded =
                mapper.readValue(fetched.body(), BookView.class);

        assertEquals(book, reloaded);
    }

    @Test
    void missingIdReturns404OverRealHttp()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri("/api/books/999999999"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(404, response.statusCode());
    }
}
```

### 10.1. Vì sao đây thực sự là HTTP server test?

- `@SpringBootTest(RANDOM_PORT)` khởi động embedded servlet web server.
- `@LocalServerPort` nhận cổng thực do OS/Boot cấp.
- `ServletWebServerApplicationContext.getWebServer().getPort()` cho phép xác nhận web server object đã có cổng tương ứng.
- Java 17 `HttpClient` mở HTTP connection tới `127.0.0.1:port`; đây không phải MockMvc.
- `POST` đi vào server, qua servlet filter, DispatcherServlet, controller, service và repository.
- `GET` là request HTTP **thứ hai**, đọc lại bản ghi server đã tạo.
- `GET` ID không tồn tại trả HTTP 404 theo `ResponseStatusException`.

Các assertions kiểm tra actual HTTP status/headers/body từ client phía ngoài controller call chain và query database sau request. Đây là một bước kiểm chứng bổ sung có nghĩa so với Test B.

### 10.2. Tại sao không gắn `@Transactional` lên live test?

Khi dùng `RANDOM_PORT`, **HTTP client và server thường xử lý trên threads/transactions khác nhau**. `@Transactional` trên JUnit test method chỉ bao quanh các thao tác nằm trong test-managed transaction, **không rollback tự động các transaction được server commit trong request**.

Nếu đánh dấu class live test là `@Transactional` rồi mặc định data biến mất sau test, bạn có thể để lại record. Bộ ví dụ **không** gắn annotation đó và có `@AfterEach` dọn đúng record bằng `createdCode`.

### 10.3. Vì sao cleanup bằng mã duy nhất?

`createdCode = "live-" + UUID.randomUUID()` giúp test giảm va chạm unique key. Cleanup dùng `findByCode(createdCode)` rồi xóa **đúng record mà test vừa tạo**, không gọi `deleteAll()` trên toàn database. Điều này an toàn hơn trong suite có thể có các test/context khác dùng chung DB.

Nếu request fail trước khi tạo dữ liệu, cleanup không thấy record và bỏ qua. Trong project production-like, dùng database test riêng, schema/transaction isolation và teardown phù hợp; không dùng cơ chế này để dọn production data.

**Lưu ý:** test `serverHasAnActualAssignedPort` chỉ là một bằng chứng startup. Bằng chứng quan trọng hơn là Java HttpClient thực sự gửi/nhận status/body qua port ấy. Port > 0 một mình chưa chứng minh endpoint trả đúng.

## 11. Chạy ba lớp test và đọc kết quả

Trong dự án có Gradle Wrapper tương thích (ví dụ Gradle 8.5), chạy:

```bash
./gradlew test
./gradlew test --tests example.BookControllerSliceTest
./gradlew test --tests example.BookMockIntegrationTest
./gradlew test --tests example.BookHttpServerIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.BookHttpServerIntegrationTest
```

**Kết quả mong đợi:** **5 phương thức test pass** — 1 ở MVC slice, 1 ở full MockMvc, 3 ở HTTP live test. Không có stdout nghiệp vụ cố định vì code không in ra console. Gradle thường in `BUILD SUCCESSFUL` nếu tất cả các task thành công. Port, log startup, ID được sinh và thời gian chạy là giá trị động; **không** assert số cổng/ID cố định.

| Lớp test | Số methods | Context | Server TCP | Dữ liệu được kiểm chứng |
| --- | ---: | --- | --- | --- |
| `BookControllerSliceTest` | 1 | MVC slice, service mock | Không | Controller mapping/JSON từ mock |
| `BookMockIntegrationTest` | 1 | Full Boot, service/repo thật | Không | HTTP mock request + JPA trong test transaction |
| `BookHttpServerIntegrationTest` | 3 | Full Boot, server thật | Có | Actual port, HTTP POST/GET/404, DB state và cleanup |

### 11.1. Cách xem HTTP evidence khi debug

Trong live test, có thể in **địa chỉ test localhost** và status để gỡ lỗi, nhưng đừng đưa credentials/cookies/token vào logs. `HttpResponse` cung cấp:

- `statusCode()`: HTTP status numeric.
- `headers()`: map headers từ response thực.
- `body()`: body text đã decode.
- `uri()`: URI của HTTP response theo client; nếu client follow redirects theo policy, cần hiểu URI nào được dùng.
- `version()`: HTTP version mà client báo; cần cấu hình/request đúng nếu mục tiêu là HTTP/2.

Trong demo, test không cố assert version hay encoding chi tiết của từng server connector vì đó không phải hợp đồng của mẫu. Khi kiểm chứng HTTP/2, compression, TLS hoặc cookies, bổ sung **cấu hình server thực** và test đúng điều kiện ấy.

## 12. Vì sao `MockMvc` và live server có thể cho kết quả khác?

### 12.1. Servlet container error pages

Spring Boot tài liệu hóa trường hợp **custom error page rendering**: ứng dụng có thể dựa vào cơ chế error page của servlet container. `MockMvc` làm việc ở Spring MVC layer và mock servlet objects, nên không kiểm chứng trực tiếp hành vi error page cấp container.

Nếu yêu cầu sản phẩm là:

> Với một loại lỗi trong request, embedded Tomcat phải thực hiện error dispatch và client ngoài nhận error page cụ thể.

Thì nên có **live-server test** assert status, content type và body/error page sau khi gửi HTTP thật. Đừng chỉ gọi controller method hoặc assert controller throw exception rồi kết luận container đã hiển thị trang lỗi đúng.

**Không áp đặt một response error JSON cố định** cho `ResponseStatusException` trong mọi app/version. JSON/error page mặc định còn phụ thuộc exception resolver, Boot error configuration, content negotiation và môi trường. Dự án mẫu chỉ assert status 404, không assert raw error body.

### 12.2. HTTP connector, headers, compression và body limits

Một số yêu cầu phụ thuộc thuộc tính embedded server:

- HTTP request header size limit.
- HTTP response compression khi được bật và đáp ứng điều kiện về size/MIME/Accept-Encoding.
- Max request body/form upload size.
- Connection timeout, idle timeout.
- Server-side redirect, cookie flags và encoding behavior.
- HTTP/2 hoặc TLS trên connector đã được cấu hình.

Các thuộc tính này cần **server thật** để xác minh. Tuy nhiên, đừng viết test kiểu “Accept-Encoding: gzip thì luôn có Content-Encoding: gzip” nếu không bật compression và không bảo đảm response đủ kích thước/MIME đúng. Mỗi assertion cần xuất phát từ configuration và contract thực tế.

### 12.3. Các filter có mặt ở cả MockMvc và server thật

Một `Filter` Spring bean thường có thể được áp dụng trong `@AutoConfigureMockMvc`; test B đã assert `X-App-Filter: book-api`. Live test C assert cùng header.

Vì vậy:

- `X-App-Filter` có mặt trong MockMvc **không chứng minh** Tomcat đã mở cổng.
- `X-App-Filter` có mặt trong live test, kết hợp HTTP request qua actual port, chứng minh filter trên đường server request.
- Một số native container dispatch/filter ordering behavior cần live test riêng nếu nằm trong rủi ro sản phẩm.

### 12.4. Redirects và cookies

Nếu endpoint thiết lập `Set-Cookie` (HttpOnly, Secure, SameSite) hoặc trả `Location` redirect, client thật nhìn thấy headers trên wire. Test có thể:

1. Gửi request **không tự động follow redirect** để assert status 3xx và `Location`.
2. Kiểm tra `Set-Cookie` fields được yêu cầu.
3. Chạy client với redirect policy khác trong một test riêng nếu cần xác minh full navigation.

Java `HttpClient` mặc định không tự follow mọi redirect theo cùng cách mà browser làm; `TestRestTemplate` cũng có behavior error/redirect khác `RestTemplate` thuần. Chọn client config đúng mục tiêu, không dựa vào mặc định chưa kiểm chứng.

## 13. `TestRestTemplate`, `WebTestClient`, Java `HttpClient`: chọn client nào?

Bài mẫu dùng Java `HttpClient` để thể hiện TCP trực tiếp. Trong Spring Boot 3.3 còn có các lựa chọn tiện lợi:

| Client | Khi nào dùng | Ghi chú |
| --- | --- | --- |
| Java 17 `HttpClient` | Muốn HTTP client độc lập Spring, điều khiển URI/headers/status rõ ràng | Có sẵn trong JDK, tự build absolute URL từ `@LocalServerPort` |
| `TestRestTemplate` | REST tests với Boot 3.3, thuận tiện root URI và JSON conversion | `org.springframework.boot.test.web.client.TestRestTemplate` ở dòng này |
| `WebTestClient` | Fluent HTTP assertions, thích hợp WebFlux và dùng được với live server | Cần Spring WebFlux/test dependency đúng classpath |
| `RestAssured` | DSL assertions chuyên HTTP/API | Thêm dependency, cấu hình port riêng |
| Browser automation | Chỉ khi thật sự cần browser DOM/JS, CSP, cookie UX | Không thay thế toàn bộ backend HTTP tests |

### 13.1. `TestRestTemplate` trong Boot 3.3

Ví dụ rút gọn:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class TestRestTemplateExample {
    @Autowired
    TestRestTemplate rest;

    @Test
    void returnsNotFound() {
        ResponseEntity<String> response =
                rest.getForEntity(
                        "/api/books/999999999", String.class);

        assertEquals(
                HttpStatus.NOT_FOUND,
                response.getStatusCode());
    }
}
```

Đây là **khung**, thiếu imports và test properties/datasource của demo; trong Boot 3.3 import `org.springframework.boot.test.web.client.TestRestTemplate`. Khi Boot quản lý RANDOM_PORT context, bean TestRestTemplate được cấu hình để request relative URI vào local server.

TestRestTemplate được thiết kế **fault tolerant** cho HTTP test: HTTP 4xx/5xx có thể được trả về dưới dạng `ResponseEntity` thay vì ném exception như một số cấu hình RestTemplate chuẩn. Đọc status thực thay vì chỉ chờ exception.

### 13.2. `WebTestClient` với live server

Spring Boot 3.3 hỗ trợ sử dụng `WebTestClient` để gọi server thật trong RANDOM_PORT test nếu có `spring-webflux` trên classpath, hoặc tự xây:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port)
        .build();

client.get()
        .uri("/api/books/999999999")
        .exchange()
        .expectStatus().isNotFound();
```

Đây là đoạn minh họa cần `WebTestClient` dependency và biến `port` lấy từ `@LocalServerPort`. **`WebTestClient` không luôn đồng nghĩa live HTTP:** nó còn có `bindToController` và `bindToApplicationContext` cho mock server requests. Muốn chứng minh embedded server, phải chắc rằng client được bind đến live server.

### 13.3. Khác biệt theo major version

Các dòng Boot 4 tổ chức lại test modules/clients và có `RestTestClient` cùng các auto-configuration riêng. Không copy import TestRestTemplate hoặc `@AutoConfigureMockMvc` từ Boot 3.3 sang Boot 4 mà không tra test module và package tương ứng.

Nguyên tắc không đổi: **RANDOM_PORT/DEFINED_PORT dựng live server; MOCK không dựng live server**. API client chỉ là cách gửi request/đọc response.

## 14. Đừng suy luận live HTTP = xác minh security hoàn chỉnh

Nếu app có Spring Security, request qua embedded server thực đi qua security filter chain đã được cấu hình. Đây là lợi thế khi kiểm chứng authentication/session/CSRF/header behavior ngoài mock client.

Nhưng ngay cả live server test cũng có thể làm sai mục tiêu:

- Nếu bạn cấu hình test profile bỏ toàn bộ security filters, test không chứng minh security production.
- Nếu mock authentication service, bạn chỉ chứng minh flow dựa trên mock, không chứng minh IdP/OAuth provider thật.
- Nếu test gửi token thiếu hoặc sai nhưng client auto đính kèm credentials từ config chung, có thể assert sai kịch bản.
- Với HTTPS, localhost HTTP không chứng minh TLS protocol/CA/certificate/redirect policy của môi trường thật.

Thiết kế các trường hợp:

1. Anonymous GET/POST vào endpoint được bảo vệ → status 401/403 đúng hợp đồng.
2. Authenticated/authorized → status thành công và effect quan sát được.
3. Unauthorized mutation → không có thay đổi DB/event.
4. Cookie/header policy → assert qua HTTP response thực.
5. TLS/ingress behavior → kiểm chứng trong môi trường có đúng tầng TLS/ingress ấy.

**Không tắt Spring Security filter chain chỉ để test status 200 rồi gọi đó là end-to-end security test.**

## 15. HTTP request và transaction: vấn đề quan trọng nhất của `RANDOM_PORT`

### 15.1. MockMvc trong cùng test-managed transaction

Trong `BookMockIntegrationTest`:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
@Transactional
class MockBookIT {
    // MockMvc request chạy trong test thread thông thường.
}
```

Đây là mẫu rút gọn; class runnable đầy đủ ở mục 9. Với MockMvc đồng bộ, request và repository operations thường tham gia vào **test-managed transaction** của method. Spring TestContext rollback sau test.

Tuy nhiên, nếu ứng dụng tự tạo thread, gọi async tasks hoặc một đường xử lý có transaction boundaries khác, không được suy luận mọi effect cùng transaction. Đây là lời giải thích cho demo đơn giản, không phải bảo đảm tuyệt đối cho mọi loại async servlet processing.

### 15.2. HTTP server thật dùng transaction khác

Trong `BookHttpServerIntegrationTest`:

```text
JUnit test thread
    |
    | Java HttpClient POST /api/books
    v
localhost TCP socket
    |
    v
Embedded Tomcat request thread
    |
    +--> BookService.create()
    |      +--> @Transactional service method
    |      +--> JPA save
    |      +--> commit on successful return
    v
HTTP 201 response
    |
    v
JUnit test receives response
    |
    +--> query repository and assert saved record
    +--> @AfterEach deletes record
```

Nếu gắn `@Transactional` trên test method, giao dịch đó **không tự bao lấy** Spring MVC request thread thật. Server có thể commit thành công, trong khi test-managed transaction cuối cùng rollback độc lập. Vì vậy dữ liệu do HTTP request tạo có thể còn tồn tại sau method test.

**Cách xử lý an toàn:** H2/test database ephemeral, unique test IDs và cleanup đúng record; hoặc Testcontainers/test schema riêng, SQL cleanup có phạm vi, API delete test-only. Đừng dùng `@DirtiesContext` như câu lệnh rollback: đóng context không đảo ngược transaction đã commit.

### 15.3. Testcontainers khi cần DB gần production

H2 hữu ích để demo nhưng không chứng minh PostgreSQL/MySQL-specific semantics. Nếu API phụ thuộc SQL dialect, locking, transaction isolation, indexes hay triggers, dùng Testcontainers với DB cùng loại production.

Khi đó cần quản lý:

- Container startup và lifecycle.
- JDBC URL/username/password cấp qua Spring Boot service connections hoặc dynamic properties theo version.
- Data isolation cho các test chạy song song.
- Cleanup sau HTTP requests server-side.
- Database migrations được chạy ở thời điểm phù hợp.

Dùng live server không bắt buộc dùng Testcontainers; chọn mỗi thành phần theo rủi ro. Một full MockMvc test vẫn có thể kết nối real DB test container nếu phần cần chứng minh là persistence, không phải HTTP transport.

## 16. ApplicationContext caching và port reuse

Spring TestContext cache Spring application contexts theo cấu hình. Hai test `@SpringBootTest(RANDOM_PORT)` có cùng app/profile/properties/context customizers có thể tái sử dụng cùng **WebServerApplicationContext**. Do đó:

- Port có thể được giữ nguyên khi context cache hit.
- Đừng kỳ vọng mỗi `@Test` nhận một cổng mới.
- Khi có property/profile/mock set khác nhau, Boot có thể tạo context mới và cổng khác.
- `@DirtiesContext` làm context bị đóng/loại cache, lần sau có thể startup server mới.
- Cache chỉ chia sẻ trong cùng JVM; test workers/forks riêng không chia sẻ cùng context.

**Không lưu port vào constant/static state dùng chung rồi dùng với context khác.** Mỗi live test lấy port từ `@LocalServerPort` được inject cho chính context đang chạy.

### 16.1. Random port không giải quyết mọi race

OS chọn port khả dụng khi server bind, giúp giảm xung đột so với cố định 8080. Nhưng test vẫn có thể race do:

- Shared database/table.
- Cùng file upload directory.
- Cùng external message queue topic.
- Cùng static mutable state.
- Cùng OAuth mock credentials/token store.
- Global properties hoặc server resources bị thay đổi ở thời điểm khác.

Đừng đánh đồng **port isolation** với **data isolation**. Test cần cả hai khi chạy song song.

## 17. Startup behavior và embedded server

`@SpringBootTest(RANDOM_PORT)` tạo Boot context bằng `SpringApplication`. Khi đó những bean được nạp có thể thực hiện:

- `@PostConstruct`/initialization callbacks.
- `ApplicationRunner`/`CommandLineRunner`.
- Flyway/Liquibase migrations hoặc JPA initialization.
- Security/filter registration, REST client initialization.
- Scheduled tasks nếu scheduling được bật.
- Application events/listeners.

Các công việc này có thể chạy **trước `@Test`**. Đừng stub một mock trong `@BeforeEach` rồi nghĩ nó kiểm soát lời gọi gateway đã xảy ra trong runner lúc context bootstrap.

Nếu startup job không thuộc mục tiêu test HTTP, loại nó khỏi context bằng `@ConditionalOnProperty` hoặc profile test có chủ đích. Nếu muốn kiểm tra startup job, tạo test riêng với fixture được chuẩn bị **trước context load**.

HTTP server thật không tự làm external services an toàn. Các port/gateway ngoài cần có test doubles, test-specific URLs hoặc containers độc lập.

## 18. `RANDOM_PORT` hay `DEFINED_PORT`?

`DEFINED_PORT` chạy server ở cổng được cấu hình, hoặc mặc định 8080. Nó hữu ích khi kiểm tra một hệ thống phụ thuộc port xác định hoặc kết nối từ test external process đã cấu hình sẵn. Nhưng rủi ro:

- Port bị chiếm.
- Hai test classes chạy song song xung đột.
- IDE đang chạy app cùng cổng.
- Test vô tình gọi nhầm một server khác đang lắng nghe.

Vì vậy Spring Boot docs **khuyến nghị RANDOM_PORT** cho tests cần running server. Chỉ chọn `DEFINED_PORT` khi fixed port thực sự là phần hợp đồng và môi trường được quản lý cô lập.

Nếu yêu cầu là “server có chạy trên cổng 8080 ở production khi deploy không?”, unit/integration localhost không thể thay thế kiểm chứng deployment config. Có thể kiểm tra config property trong test và một environment/deployment smoke test thực trong pipeline.

## 19. URL, URI, headers và redirects khi gọi live HTTP

### 19.1. Địa chỉ loopback

Trong bài mẫu:

```java
URI.create("http://127.0.0.1:" + port + "/api/books")
```

`127.0.0.1` là loopback trong máy/process host test. Với Docker/test chạy bên ngoài container, địa chỉ đúng có thể là mapped host port chứ không phải localhost trong container; cần lấy URL/port từ container runtime hoặc config test hợp lệ.

### 19.2. `Location` và status 201

Endpoint tạo sách trả `201 Created` với `Location: /api/books/{id}`. Client test nên assert status 201, path đích đúng và response body có code/title/ID. Không giả định property `Location` là absolute hay relative nếu contract không quy định; nếu contract quy định absolute URI, triển khai controller theo đó và assert cụ thể.

### 19.3. JSON và Content-Type

`java.net.http.HttpClient` gửi body theo `BodyPublishers.ofString(...)`. Test chủ động đặt `Content-Type: application/json` để Spring sử dụng JSON message converter. Server trả JSON record.

Test có thể assert response `Content-Type` compatible với `application/json`. Tránh so sánh một header byte-string cụ thể nếu charset parameter/case không nằm trong contract.

### 19.4. Redirect policy

Java `HttpClient` có lựa chọn follow redirects. Nếu cần test redirect, **không** bật tự follow trong test chỉ kiểm tra 302/Location; nếu client follow, status cuối cùng có thể là 200 và che redirect hop. Kiểm tra behavior của client đang dùng thay vì đoán.

### 19.5. Cookies và sessions

Nếu endpoint dùng session cookies:

- Test qua live HTTP nhận `Set-Cookie` từ server.
- Client có hoặc không có cookie manager sẽ ảnh hưởng request sau có gửi cookie lại không.
- Kiểm tra `HttpOnly`, `Secure`, `SameSite` theo policy của app và môi trường.
- Test HTTP localhost không tự chứng minh browser cookie policy trong HTTPS/cross-site deployment nếu những tầng đó không hiện diện.

## 20. Error handling: khi nào mock đủ, khi nào phải live?

Giả sử controller dùng `@ControllerAdvice` để map `BookNotFoundException` thành 404 JSON. `MockMvc` hoàn toàn có thể kiểm tra mapping này khi advice được nạp vào test context. Nếu chỉ cần business-level exception mapping, không nhất thiết bật live server.

Nhưng khi yêu cầu liên quan:

- Servlet container error page dispatch.
- Default error page phục vụ bởi container/configuration.
- Container-specific status handling.
- Request bị từ chối trước khi vào DispatcherServlet (ví dụ HTTP parser/body/header limits).

thì **MockMvc không đại diện đầy đủ** cho tầng cần test. Dùng live HTTP request để lấy response thực từ embedded server.

Trong demo, `BookService.get` dùng `ResponseStatusException(NOT_FOUND)`. Live test assert 404, không tự đặt expected JSON schema cho error body vì Boot default error response có thể khác theo config/version/media type.

Nếu hợp đồng API bắt buộc JSON code ổn định như `BOOK_NOT_FOUND`, cần implement `@RestControllerAdvice` hoặc error response mapping phù hợp rồi assert `code` ở cả mock và live test.

## 21. Khi nào cần HTTPS/TLS hoặc HTTP/2 thật?

HTTP test ở localhost bằng `http://` **không chứng minh HTTPS**. Nếu feature cần:

- TLS protocols/ciphers.
- Server certificate/keystore được nạp đúng.
- Client trust store và hostname validation.
- HTTP/2 negotiation.
- Reverse proxy forwarded headers/`X-Forwarded-*`.
- HSTS/secure cookie behavior sau HTTPS.

thì phải cấu hình embedded server HTTPS/HTTP2 thật hoặc môi trường deployment test có proxy/TLS. Sau đó dùng HTTP client được cấu hình trust đúng CA. **Không tắt certificate verification bừa bãi** để ép test xanh.

Ngoài ra, nếu TLS termination xảy ra ở ingress (không phải embedded server), việc chỉ bật HTTPS trong Spring Boot embedded server không chứng minh cấu hình ingress thực tế. Chọn lớp kiểm thử tương ứng với nơi rủi ro tồn tại.

## 22. Compression, upload limits và container-specific behavior

Các thuộc tính server như response compression và upload size cần test với server thật nếu là yêu cầu. Ví dụ test response nén:

1. Bật compression trong test profile.
2. Đặt threshold nhỏ và nội dung trả về đủ lớn.
3. Đảm bảo MIME type thuộc tập được nén.
4. Gửi `Accept-Encoding: gzip` từ client thật.
5. Assert response `Content-Encoding` và giải mã body đúng.

**Không kỳ vọng compression tự bật chỉ vì client gửi `Accept-Encoding`.** Test data phải đáp ứng threshold và configuration; điều này không được chứng minh bởi demo đơn giản.

Đối với multipart upload:

- MVC mock test có thể kiểm tra controller nhận `MultipartFile` đúng.
- Live server test cần thiết nếu muốn kiểm tra native servlet multipart resolver/container limits, max file size hoặc tempfile behavior theo configuration.
- Tạo file test trong sandbox, cleanup, không upload dữ liệu nhạy cảm ra external endpoints.

## 23. Readiness, health và server startup

Một dấu hiệu tốt của running server là test HTTP thực nhận 200 từ endpoint. Tuy nhiên, một endpoint `/actuator/health` trả 200 chưa chắc mọi integration bên ngoài sẵn sàng nếu app không đưa dependency ấy vào health indicator.

Nếu application có Actuator management server ở **port riêng**, `RANDOM_PORT` có thể khởi động application port và management port khác nhau. Khi muốn kiểm tra management endpoint qua HTTP:

- Xác định đúng management port, không tự giả định bằng `@LocalServerPort`.
- Dùng annotation/property API quản lý cổng phù hợp với Boot version (ví dụ `@LocalManagementPort` khi hỗ trợ).
- Cấu hình security/auth cho management endpoints an toàn.
- Assert contract readiness/health mà deployment thực sự dùng.

**Không dùng health endpoint làm bằng chứng rằng mọi API endpoint được cấu hình đúng.** Một live smoke test cho một luồng HTTP quan trọng sẽ bổ sung bằng chứng cụ thể hơn.

## 24. Hiệu năng: tối ưu phân tầng, không chạy full server cho mọi method

Mở embedded server và full application context thường tốn nhiều thời gian hơn JUnit thuần hoặc MVC slice. Trong suite có hàng nghìn tests, chạy mọi controller case bằng `RANDOM_PORT` có thể:

- Tạo nhiều server instances do context cache keys khác nhau.
- Động tới DB migrations, caches, startup runners.
- Mất thời gian chờ/điều phối network.
- Tăng số điểm fail vì external dependencies.
- Gây port/data/resource contention khi test song song.

Cách cân bằng:

- **Nhiều unit tests** cho domain/service logic.
- **Nhiều slice tests** cho controller mapping, validation, status, JSON.
- **Một tập full MockMvc tests** cho wiring controller-service-repo.
- **Một số live HTTP tests** cho server connector, error dispatch, cookies/redirects, upload/compression/security behavior quan trọng.
- **Một vài deployment smoke tests** cho ingress/TLS/proxy thật nếu cần.

Không nên lặp cùng một “GET trả 200” ở 5 tầng mà không thêm bằng chứng. Mỗi tầng cần một câu rõ: **“Lỗi nào mà tầng nhẹ hơn sẽ không bắt được?”**

## 25. Chẩn đoán lỗi: bắt đầu từ tầng sai

| Triệu chứng | Tầng cần xem | Bước điều tra |
| --- | --- | --- |
| `No tests found` | JUnit/Gradle | Kiểm tra Jupiter imports, `useJUnitPlatform()` và filter |
| `Failed to load ApplicationContext` | Spring startup | Tìm root cause bean/DB/property/runner |
| `Port already in use` | Embedded server | Có dùng DEFINED_PORT/8080? đổi RANDOM_PORT |
| `Connection refused` | Network/port | Server đã mở chưa? URL/port thực có đúng? |
| MockMvc pass, live HTTP 404 | Routing/context path/URL | Kiểm tra base URL, port, servlet mapping, headers |
| Live trả 401/403 | Security | Authentication, CSRF, filter chain, endpoint policy |
| Live trả 415 | Media type | `Content-Type` và message converters |
| Live trả 400 | Request decode/validation | JSON schema, body, parser errors |
| Live trả 500 | Server exception/DB | Server logs và full stack trace |
| Live status 201 nhưng record còn sau test | Transaction server-side | Cleanup/DB isolation, không trông chờ test rollback |
| MockMvc thiếu error page | Container error support | Cần live server test |
| Header thiếu chỉ ở live | Filter chain/connector | Kiểm tra registration, dispatch, security |
| Test chạy riêng pass nhưng suite fail | Shared data/cache/parallelism | Unique IDs, cleanup, cache keys, forks |
| Test timeout | HTTP/server/DB/external call | Hữu hạn timeouts, logs; không tăng vô hạn |
| Boot 4 code không compile | Imports/test modules khác | Kiểm tra BOM, starter và client annotations |

### 25.1. Connection refused không giống HTTP 404

- `Connection refused` nghĩa là HTTP client **không thiết lập được kết nối** tới host/port. Không có HTTP response từ endpoint.
- `404` nghĩa là client đã **nhận được một HTTP response** với status 404 từ server/gateway đang liên lạc. Lúc đó cần kiểm tra routing, base path, security, context và đúng server.

Đừng sửa controller mapping khi lỗi thật sự là không có process lắng nghe trên port.

### 25.2. 404 từ một server khác

Nếu hard-code 8080 và có service khác chiếm cổng, client có thể nhận HTTP 404 từ **ứng dụng sai**. Vì vậy `@LocalServerPort` và random port không chỉ tránh collision; chúng giúp gắn client đúng server do test context khởi động.

### 25.3. Context failure threshold

Từ Spring Framework 6.1, context load failure threshold có thể khiến các test yêu cầu cùng cấu hình thất bại sớm sau lần load đầu tiên. Khi thấy nhiều lỗi `Failed to load ApplicationContext`, tìm **lần lỗi gốc đầu tiên** — có thể là datasource, bean constructor hoặc embedded server connector.

## 26. Một số anti-pattern và cách sửa

### 26.1. “Chỉ thêm `@SpringBootTest` là đã có HTTP thật”

**Sai.** Mặc định là `MOCK` và **không** khởi động embedded server. Muốn live HTTP, phải dùng `RANDOM_PORT`/`DEFINED_PORT` và một HTTP client gọi đúng URL.

### 26.2. “Test có `MockMvc` nghĩa là đã qua embedded Tomcat”

**Sai.** MockMvc dùng mock Servlet infrastructure, không qua socket. Nó vẫn có thể thực thi filters, controllers và services thật tùy context.

### 26.3. “Mọi endpoint đều phải test live vì integration test mạnh hơn”

**Không hợp lý.** Live HTTP có chi phí và rủi ro state/network, nhưng chưa chắc thêm bằng chứng cho một pure calculation. Giữ các test hẹp nhanh và rõ, chỉ dùng live khi có rủi ro mới.

### 26.4. “Đã dùng `@Transactional` nên live HTTP rollback sạch”

**Sai.** Server request thường chạy trong transaction khác test method. Dùng DB test cô lập và cleanup rõ.

### 26.5. “Một cổng cố định giúp test dễ đọc hơn”

Thường sai khi CI chạy song song. Dùng `RANDOM_PORT` và `@LocalServerPort`. Nếu một hệ thống bắt buộc port cố định, chạy trong môi trường được quản lý và giải thích lý do.

### 26.6. “Localhost HTTP đã chứng minh TLS/nginx production”

**Sai.** Loopback HTTP chỉ chứng minh embedded server + đường HTTP tại máy test. TLS/ingress phải hiện diện trong môi trường test mới được chứng minh.

### 26.7. “Trả 200 là đủ”

Không nếu contract yêu cầu 201, `Location`, JSON fields, cookies, filter headers, authorization và effect DB. Assert chính xác những gì khách hàng HTTP quan sát được, cộng state/effects ngoài nếu cần.

### 26.8. “`@DirtiesContext` dọn dữ liệu server đã commit”

**Sai.** Đóng Spring context không rollback commit hoặc xóa dữ liệu external. Có thể còn làm startup server/migrations/jobs chạy lại, tăng thời gian suite.

## 27. Kiểm thử không cần Spring client: ưu và nhược

Dùng Java `HttpClient` độc lập trong demo có ưu điểm:

- Khó vô tình nhầm mock binding với live binding.
- Kiểm soát rõ absolute URI có host/port/scheme.
- Chủ động status, headers, body và timeout.
- Không phụ thuộc `TestRestTemplate`/`WebTestClient` imports khi nâng Boot major.
- Có thể dùng với server không phải Spring.

Nhược điểm:

- Phải tự build JSON request/deserialize response.
- Test dài hơn và có thêm boilerplate.
- Cần tự cấu hình redirect/cookie/auth/timeouts.
- Không có DSL assert HTTP fluent như WebTestClient.

Để test nhiều HTTP cases, `TestRestTemplate` hoặc `WebTestClient` thuận tiện hơn. Nhưng dù dùng client nào, **điều cần kiểm tra là nó có thực sự gọi live base URL hay không**. `WebTestClient.bindToController` không thành HTTP live chỉ vì test class có chữ “Integration”.

## 28. Bài tập có hướng dẫn

### Bài 1 — Chứng minh `MOCK` không mở TCP

Chạy `BookMockIntegrationTest`. Thêm một assertion query repository để xác minh service/JPA thật hoạt động. Giải thích vì sao điều này vẫn **không** chứng minh embedded server đang nghe port. Đừng thử đoán port 8080 để gọi.

**Đáp án:** Full Spring context có thể xử lý mock servlet request và DB operations mà không có HTTP socket.

### Bài 2 — Chuyển một test sang HTTP thật

Chạy `BookHttpServerIntegrationTest`, log cổng từ `@LocalServerPort` chỉ trong sandbox, xác minh `port > 0` và request POST/GET qua Java `HttpClient`. Giải thích khác biệt trong call stack so với MockMvc.

**Đáp án:** Request chạy qua TCP và embedded server, sau đó qua DispatcherServlet/beans.

### Bài 3 — Quan sát transaction khác nhau

Trong `BookMockIntegrationTest`, giữ `@Transactional` và kiểm tra record được truy vấn trong test transaction rồi rollback. Trong live test, tạo record qua POST và truy vấn repository ở JUnit thread sau response. Nếu không cleanup, record có thể vẫn tồn tại sau test.

**Đáp án:** Server-side transaction không bị rollback bởi test-managed transaction riêng.

### Bài 4 — Sai cổng

Tạm đổi URL live test sang một cổng không có listener trong sandbox. Test nhận lỗi kết nối chứ không phải 404. Khôi phục `@LocalServerPort`.

**Đáp án:** HTTP client phải kết nối thành công mới có thể nhận status.

### Bài 5 — Kiểm thử error handling

Sửa `BookService.get` trong nhánh thí nghiệm để có error contract JSON với error code `BOOK_NOT_FOUND` qua `@RestControllerAdvice`. Viết một test MockMvc cho advice, sau đó thêm một live test chứng minh response HTTP thật. Nếu yêu cầu riêng **servlet error dispatch**, cần cấu hình và assert behavior container tương ứng, không chỉ controller advice.

### Bài 6 — Compression

Bật response compression trong một test profile, tạo endpoint trả JSON/text đủ lớn. Gửi `Accept-Encoding: gzip` bằng HTTP client, assert encoding và body sau giải nén. Giải thích vì sao MockMvc không phải bằng chứng native connector đã nén response.

### Bài 7 — Authentication

Tạo endpoint có role requirement và test hai đường qua live HTTP: anonymous bị từ chối, user hợp lệ được phép. Assert status và effect. Không dùng production credentials; cấu hình test security và token/identity provider độc lập.

### Bài 8 — Nhiều test song song

Tạo hai POST requests đồng thời với code khác nhau bằng Java HttpClient async hoặc JUnit parallel. Kiểm tra cả hai bản ghi và cleanup đúng record. Không assert thứ tự các response; Spring và OS không hứa response order theo thứ tự request khi concurrent.

### Bài 9 — Đánh giá TestRestTemplate và WebTestClient

Viết lại test GET 404 bằng `TestRestTemplate` Boot 3.3 rồi bằng `WebTestClient.bindToServer` (bổ sung dependency cần thiết). So sánh API, error handling và cách xác định base URL. Đảm bảo cả hai **thực sự** trỏ vào live port.

### Bài 10 — Đề xuất test pyramid

Cho ứng dụng có 30 controllers, 15 services, 10 repositories, một custom Tomcat error page và một OAuth2 security chain. Hãy chọn những test dùng unit, MVC slice, full MockMvc, live HTTP và deployment smoke. Mỗi live test phải trả lời: “Điều gì ở embedded server mà MockMvc không thể chứng minh?”

## 29. Checklist review trước khi đánh dấu hoàn thành

- [ ] Tôi đã nêu chính xác **rủi ro nào yêu cầu HTTP transport thật**.
- [ ] Tôi không dùng live server chỉ vì endpoint có JSON.
- [ ] Tôi hiểu `@SpringBootTest` mặc định `MOCK`, không mở port.
- [ ] Tôi dùng `RANDOM_PORT` khi cần embedded server và tránh hard-coded port.
- [ ] `@LocalServerPort` được inject sau khi server đã khởi tạo.
- [ ] HTTP client thực sự gọi absolute URL có host/port đúng test server.
- [ ] Tôi phân biệt MockMvc mock Servlet objects với HTTP connection qua TCP.
- [ ] Tôi biết filters/controllers/advices có thể được test cả trong mock context.
- [ ] Tôi không coi localhost HTTP là bằng chứng ingress/TLS/proxy production.
- [ ] Tôi assert status/body/header/Location đúng contract, không chỉ kiểm tra 200.
- [ ] Tôi có negative test cho 404/validation/security nếu nằm trong mục tiêu.
- [ ] Tôi không để test chạm production DB hoặc external payment/email.
- [ ] Với live HTTP, tôi không dựa vào `@Transactional` test method để rollback server data.
- [ ] Test data có unique IDs, cleanup đúng bản ghi, không `deleteAll` vô tình.
- [ ] Context cache, port reuse và JVM forks không làm test phụ thuộc thứ tự.
- [ ] Nếu cần container-specific error page/limits/compression, đã bật cấu hình đúng trước khi assert.
- [ ] Tôi có timeouts hữu hạn và thông tin log phù hợp để tìm root cause.
- [ ] Với Boot 4, tôi kiểm tra test module/import/client API đúng phiên bản.
- [ ] Tôi kiểm tra số test được thực thi thật, không chỉ thấy build xanh.

## 30. Quy tắc quyết định cuối cùng

```text
Cần chứng minh điều gì?
     |
     +-- Logic Java / service?
     |      -> JUnit, Mockito/fake. Không cần web.
     |
     +-- Controller mapping, validation, JSON?
     |      -> @WebMvcTest + MockMvc.
     |
     +-- Controller + service + repository thật,
     |   nhưng không cần network?
     |      -> @SpringBootTest(MOCK) + @AutoConfigureMockMvc.
     |
     +-- Embedded server có chạy và trả HTTP thật?
     |      -> @SpringBootTest(RANDOM_PORT)
     |         + @LocalServerPort + Java HttpClient/
     |           TestRestTemplate/WebTestClient live.
     |
     +-- TLS/ingress/load balancer/deployment thật?
            -> Test môi trường tương đương deployment.
               Local RANDOM_PORT chưa đủ.
```

**Thông điệp chính:** `MockMvc` và live HTTP không cạnh tranh nhau; chúng bảo vệ **các ranh giới khác nhau**. Để kiểm tra controller/service nhanh và ổn định, mock environment thường là lựa chọn tốt. Khi hợp đồng thật sự phụ thuộc embedded server — cổng, connector, HTTP transport, servlet container error handling và các behavior cấp thấp — hãy chọn `@SpringBootTest(RANDOM_PORT)` và gửi request qua client thật. Sau đó quản lý dữ liệu/transactions của server-side effects đúng cách.

## 31. Tài liệu chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications, Testing with Mock/Running Server: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Embedded Web Servers, Random Port và `@LocalServerPort`: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot — Testing Spring Boot Applications (phiên bản mới): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Embedded Web Servers: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework — TestContext transaction management: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TestContext caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Java SE 17 — `java.net.http.HttpClient`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
