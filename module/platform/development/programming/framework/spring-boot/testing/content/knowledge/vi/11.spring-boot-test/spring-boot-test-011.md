# @SpringBootTest: kiểm tra context khởi động và hành vi ứng dụng

## 1. Mục tiêu

Spring Boot có thể khởi động thành công nhưng xử lý sai yêu cầu của người dùng; ngược lại, các hàm Java được unit test thành công chưa chắc cả ứng dụng có thể tạo Spring beans, mở web server hay kết nối database. Vì vậy kiểm thử tích hợp cần trả lời **hai câu hỏi độc lập**:

1. **Context có khởi động đúng không?** Spring Boot nạp cấu hình test, tạo `ApplicationContext`, autowire các bean, khởi tạo database/infrastructure cần thiết mà không ném lỗi?
2. **Ứng dụng có hành xử đúng không?** Controller có trả HTTP status và JSON theo hợp đồng, service có xử lý logic, repository có lưu/đọc dữ liệu, nhánh lỗi có xử lý đúng và không phát sinh side effect ngoài ý định?

Annotation `@SpringBootTest` nằm trong `org.springframework.boot.test.context.SpringBootTest`. Nó khởi tạo context bằng `SpringApplication` và tích hợp với Spring TestContext. Trong JUnit Jupiter không cần tự thêm `@ExtendWith(SpringExtension.class)` vào một class đã dùng `@SpringBootTest`. Từ đó có thể injection các bean thật và kiểm thử nhiều tầng cùng hoạt động.

**Nhưng `@SpringBootTest` không tự động có nghĩa “test HTTP thật”.** Mặc định nó dùng web environment `MOCK`, không khởi chạy embedded server trên một TCP port. Để kiểm thử HTTP transport thật, chọn `RANDOM_PORT`; để test MVC thông qua mock request/response, dùng `@AutoConfigureMockMvc`.

### Những gì bài này giúp thực hiện

- Viết test `contextLoads` có mục tiêu rõ, không coi một method rỗng là bảo chứng chất lượng.
- Phân biệt `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`.
- Test service thực và JPA repository với database H2 dưới profile test.
- Gửi POST/GET qua `MockMvc` trong full context mà không mở network server.
- Gửi POST/GET qua HTTP server thực bằng `java.net.http.HttpClient` trên Java 17.
- Kiểm tra response body, error paths, persistence và cleanup.
- Xử lý đúng transaction/rollback, context cache và tài nguyên ngoài.
- Biết khi nào `@WebMvcTest` hoặc `@DataJpaTest` phù hợp hơn một full context.

## 2. Phân biệt “khởi động được” với “hành vi đúng”

| Tình huống | `contextLoads` phát hiện được? | Test cần bổ sung |
| --- | --- | --- |
| Thiếu một required bean / constructor injection lỗi | Thường có: context tạo thất bại | Xem root cause, kiểm tra wiring |
| Thiếu datasource, migration thất bại tại startup | Có nếu database/migration được nạp ở context này | DB integration test theo schema/DB thực |
| Controller khai báo sai URL, trả 404 | Thường không | MockMvc/HTTP test với path thật |
| Controller trả 200 nhưng JSON field sai | Không | Assert status **và body** |
| Service tính toán sai hoặc trim input sai | Không | Unit/service integration test |
| Repository không lưu đúng dữ liệu ở một nhánh | Không nhất thiết | Test ghi, đọc lại và kiểm tra transaction |
| HTTP 400/404/409/503 mapping sai | Không | Test các nhánh lỗi tại API |
| Embedded server/TLS/transport trục trặc | Không ở mode MOCK | RANDOM_PORT hoặc test hạ tầng phù hợp |
| Security filter cấu hình sai | Có thể chỉ khi startup lỗi | Kiểm tra 401/403 và quyền khi gửi request |
| API ngoài timeout sau khi app đã khởi động | Không | Contract/adapter/integration test có stub server |

**Một test có tên `contextLoads` nhưng không có assertion vẫn có giá trị nhỏ:** việc tạo context thất bại khiến test FAIL ngay ở lifecycle setup. Tuy nhiên nó **không chứng minh endpoint hoạt động**. Bài học bên dưới dùng một smoke test có assertions về bean quan trọng, cộng thêm ba nhóm behavior tests để hoàn thiện bằng chứng.

## 3. Chọn webEnvironment theo mục tiêu

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class MockEnvironmentExample { /* Minh họa annotation. */ }

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealServerExample { /* Minh họa annotation. */ }

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NoWebExample { /* Minh họa annotation. */ }
```

Đây là **trích đoạn minh họa**, chưa phải test classes hoàn chỉnh.

| Mode | Context được tạo | Embedded HTTP server thật? | Dùng khi |
| --- | --- | --- | --- |
| `MOCK` *(default)* | Web context giả lập nếu web stack có trên classpath; nếu không có web stack thì context thường | **Không** | Startup, service integration, MockMvc với `@AutoConfigureMockMvc` |
| `RANDOM_PORT` | WebServerApplicationContext | **Có**, port được cấp tự động | Kiểm tra HTTP request qua socket và server |
| `DEFINED_PORT` | WebServerApplicationContext | **Có**, port được cấu hình hoặc 8080 mặc định | Chỉ khi bắt buộc có một port cụ thể |
| `NONE` | Không tạo web environment | **Không** | Batch, command-line app hoặc integration không liên quan HTTP |

Ở mode MOCK, `@SpringBootTest` chỉ đơn thuần khởi tạo context và không nhất thiết có bean `MockMvc`. Gắn `@AutoConfigureMockMvc` để có client mock theo đúng cấu hình Spring MVC. `@WebMvcTest` khác ở chỗ nó **chỉ nạp web slice**, còn `@SpringBootTest + @AutoConfigureMockMvc` nạp **full application context**.

Ở mode RANDOM_PORT, dùng `@LocalServerPort` (Boot 3.5 import `org.springframework.boot.test.web.server.LocalServerPort`) để nhận port thật; không hard-code 8080. DEFINED_PORT dễ đụng process khác hoặc test CI chạy song song, nên thường không phải lựa chọn mặc định.

**Quan trọng về môi trường:** `RANDOM_PORT` dùng HTTP server thật nhưng vẫn chạy **ứng dụng trong môi trường test**, không tự chứng minh hiệu năng production, reverse proxy, TLS certificate thật, cloud load balancer hay database production.

## 4. Quy tắc thiết kế test: Given–When–Then + trạng thái + side effect

Một integration test không nên dừng ở `assertNotNull(context)`. Hãy lập hợp đồng:

| ID | Given | When | Then |
| --- | --- | --- | --- |
| CT01 | Test profile, datasource test, bean definitions | Spring startup | Không lỗi; controller, service, repository được inject |
| SV01 | Repository thực, input có khoảng trắng | `service.create("  Lan  ")` | Message chuẩn hóa, row được lưu và đọc lại |
| SV02 | Input chỉ có khoảng trắng | `service.create("   ")` | Exception validation, repository count không đổi |
| MVC01 | Full context + MockMvc | POST JSON rồi GET ID mới | 201 rồi 200; JSON đúng; row có trong DB |
| MVC02 | Input trống / ID không tồn tại | POST/GET | 400/404; JSON lỗi đúng; không ghi thêm row |
| HTTP01 | RANDOM_PORT server đã mở | HTTP POST rồi GET qua Java HttpClient | Status/body đúng và DB đã commit |

Test nên kiểm tra cả **bề mặt nhận request** và **kết quả nghiệp vụ**. Ví dụ POST 201 không đủ nếu yêu cầu là tạo bản ghi; test cần xác nhận dữ liệu được lưu, hoặc có test repository riêng bảo đảm behavior đó.

Một HTTP 500, một dòng log hoặc exception không thuộc hợp đồng phải làm test FAIL. Không dùng JUnit assumptions để che lỗi của dependency **bắt buộc** trong CI release.

## 5. Dự án mẫu chạy được trên Java 17

Dự án mẫu dùng **Spring Boot 3.5.0**, Maven, Spring MVC, Spring Data JPA, H2, JUnit Jupiter. Không cần Docker, network bên ngoài hoặc server cài riêng. Ứng dụng có hai endpoint:

- `POST /api/greetings` nhận `{"name":"Lan"}` và lưu `"Hello, Lan!"`; trả 201 và JSON có `id`/`message`.
- `GET /api/greetings/{id}` đọc bản ghi; trả 200 và JSON tương ứng.
- Tên rỗng hoặc chỉ khoảng trắng trả 400 cùng `{"error":"name must not be blank"}`.
- ID không có trả 404 cùng `{"error":"greeting not found"}`.

HTTP 400/404 là **chính sách do controller mẫu định nghĩa bằng `@ExceptionHandler`**, không phải mọi `IllegalArgumentException`/`NoSuchElementException` trong Spring Boot mặc nhiên được map như vậy.

### 5.1. Cây tệp

```text
springboottest-demo/
├── pom.xml
└── src/
    ├── main/java/example/contextdemo/
    │   ├── DemoApplication.java
    │   ├── GreetingEntry.java
    │   ├── GreetingRepository.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/contextdemo/
            ├── ContextLoadsTest.java
            ├── ServiceIntegrationTest.java
            ├── MockMvcFullContextTest.java
            └── RandomPortHttpTest.java
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>springboottest-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Spring Boot parent quản lý versions của test framework và các starters. `h2` ở test scope phục vụ DB kiểm thử, không thay thế driver production. Nếu dự án thật cần thử SQL đặc thù PostgreSQL/MySQL, phải viết integration test với database tương ứng, chẳng hạn Testcontainers; H2 chưa đủ để khẳng định tương thích.

### 5.3. Spring Boot application

`src/main/java/example/contextdemo/DemoApplication.java`:

```java
package example.contextdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Đặt `@SpringBootApplication` cùng package cha của toàn bộ bean/entity/repository để component scanning và JPA scanning theo mặc định hoạt động. Các test classes ở cùng package giúp Boot tìm application configuration.

### 5.4. JPA entity

`src/main/java/example/contextdemo/GreetingEntry.java`:

```java
package example.contextdemo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "greeting_entry")
public class GreetingEntry {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String message;

    protected GreetingEntry() {
    }

    public GreetingEntry(String message) {
        this.message = message;
    }

    public Long getId() {
        return id;
    }

    public String getMessage() {
        return message;
    }
}
```

Primary key tự tạo bởi database; không có requirement nào bảo đảm bản ghi đầu tiên có ID bằng 1 trong mọi test run.

### 5.5. Repository

`src/main/java/example/contextdemo/GreetingRepository.java`:

```java
package example.contextdemo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface GreetingRepository
        extends JpaRepository<GreetingEntry, Long> {
}
```

### 5.6. Service thực hiện validation và persistence

`src/main/java/example/contextdemo/GreetingService.java`:

```java
package example.contextdemo;

import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GreetingService {
    private final GreetingRepository repository;

    public GreetingService(GreetingRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public GreetingEntry create(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return repository.save(
                new GreetingEntry("Hello, " + name.strip() + "!"));
    }

    @Transactional(readOnly = true)
    public GreetingEntry find(long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new NoSuchElementException("greeting not found"));
    }
}
```

`@Transactional` do Spring quản lý khi phương thức được gọi thông qua Spring bean/proxy. Pure unit test tạo `new GreetingService(mockRepository)` không tự bật Spring transaction. Bài này dùng bean thật ở integration tests để kiểm tra wiring và dữ liệu.

### 5.7. Controller và mapping lỗi

`src/main/java/example/contextdemo/GreetingController.java`:

```java
package example.contextdemo;

import java.util.Map;
import java.util.NoSuchElementException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    public record CreateRequest(String name) {}
    public record GreetingResponse(Long id, String message) {}

    @PostMapping
    public ResponseEntity<GreetingResponse> create(
            @RequestBody CreateRequest request) {
        GreetingEntry saved = service.create(request.name());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new GreetingResponse(
                        saved.getId(), saved.getMessage()));
    }

    @GetMapping("/{id}")
    public GreetingResponse get(@PathVariable long id) {
        GreetingEntry found = service.find(id);
        return new GreetingResponse(
                found.getId(), found.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalid(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", exception.getMessage()));
    }

    @ExceptionHandler(NoSuchElementException.class)
    public ResponseEntity<Map<String, String>> missing(
            NoSuchElementException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", exception.getMessage()));
    }
}
```

Hợp đồng validation đơn giản nhằm học tập. Ứng dụng production có thể chuyển sang request DTO `@Valid` và `@RestControllerAdvice`/`ProblemDetail` để chuẩn hóa lỗi toàn API. Test cần cập nhật theo hợp đồng đó thay vì cứ cố cho HTTP 400 của mẫu.

### 5.8. Cấu hình test

`src/test/resources/application-test.properties`:

```properties
spring.datasource.generate-unique-name=true
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.main.banner-mode=off
```

Khi `@ActiveProfiles("test")` được kích hoạt, Boot nạp file trên từ test classpath. H2 có mặt ở test scope nên Boot có thể tự tạo embedded datasource. `create-drop` chỉ phù hợp môi trường test tạm thời; đừng trỏ cấu hình này vào database production. `generate-unique-name=true` giảm nguy cơ hai contexts độc lập vô tình dùng một tên in-memory DB chung.

## 6. Test khởi động: ContextLoadsTest.java

Tạo `src/test/java/example/contextdemo/ContextLoadsTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ContextLoadsTest {
    @Autowired
    ApplicationContext context;

    @Test
    void contextLoadsAndImportantBeansExist() {
        assertNotNull(context);
        assertNotNull(context.getBean(GreetingController.class));
        assertNotNull(context.getBean(GreetingService.class));
        assertNotNull(context.getBean(GreetingRepository.class));
    }
}
```

Nếu context tạo thất bại, test FAIL ngay trong setup; nếu tạo được nhưng thiếu những bean quan trọng thì assertions không đạt. Cả hai là tín hiệu **startup/wiring**, chưa chứng minh POST/GET hoạt động.

So với một `@Test void contextLoads() {}` rỗng, kiểm tra bean cụ thể giúp mô tả rõ kỳ vọng của smoke test. Không nên kiểm tra tất cả các endpoint trong cùng method này, vì khi đó test dài, khó xác định lỗi và trùng nhiệm vụ của behavior tests.

## 7. Test hành vi service/JPA: ServiceIntegrationTest.java

Tạo `src/test/java/example/contextdemo/ServiceIntegrationTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class ServiceIntegrationTest {
    @Autowired
    GreetingService service;

    @Autowired
    GreetingRepository repository;

    @Test
    void createsAndReadsPersistentGreeting() {
        GreetingEntry saved = service.create("  Lan  ");

        assertNotNull(saved.getId());
        assertEquals("Hello, Lan!", saved.getMessage());

        GreetingEntry read = service.find(saved.getId());
        assertEquals("Hello, Lan!", read.getMessage());
    }

    @Test
    void rejectsBlankNameWithoutWritingNewRow() {
        long before = repository.count();

        IllegalArgumentException exception =
                assertThrows(IllegalArgumentException.class,
                        () -> service.create("   "));

        assertEquals("name must not be blank",
                exception.getMessage());
        assertEquals(before, repository.count());
    }
}
```

**Điều được xác minh:** Spring inject service/repository thật; service chuẩn hóa input; JPA có thể lưu và đọc entity; nhánh lỗi không thêm dữ liệu.

Vì test class có `@Transactional`, mỗi test method thường chạy trong một test-managed transaction và rollback khi kết thúc. Đây là behavior test ở tầng Spring service/JPA, **không phải HTTP test**. Test không kiểm tra status 201/400, JSON hoặc MVC routing.

Rollback của test thread không chứng minh production commit xảy ra chính xác. Với logic liên quan `REQUIRES_NEW`, async work, domain events sau commit hoặc HTTP server thread khác, cần kiểm thử transaction boundaries riêng.

## 8. Full context + MockMvc: MockMvcFullContextTest.java

Tạo `src/test/java/example/contextdemo/MockMvcFullContextTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class MockMvcFullContextTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    GreetingRepository repository;

    @Test
    void postThenGetChecksHttpAndPersistence() throws Exception {
        long before = repository.count();

        MvcResult created = mvc.perform(
                post("/api/greetings")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNumber())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan!"))
                .andReturn();

        JsonNode createdJson = objectMapper.readTree(
                created.getResponse().getContentAsString());
        long id = createdJson.path("id").asLong();

        mvc.perform(get("/api/greetings/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan!"));

        assertTrue(repository.existsById(id));
        assertEquals(before + 1, repository.count());
    }

    @Test
    void invalidInputAndUnknownIdMapToHttpErrors()
            throws Exception {
        long before = repository.count();

        mvc.perform(post("/api/greetings")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"   \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("name must not be blank"));

        mvc.perform(get("/api/greetings/{id}", -1L))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error")
                        .value("greeting not found"));

        assertEquals(before, repository.count());
    }
}
```

Lý do đây là integration test:

- `@SpringBootTest` nạp service/repository và các Boot beans thật.
- `@AutoConfigureMockMvc` tạo MockMvc trong web environment giả lập, không mở cổng TCP.
- Requests đi qua controller, request mapping, JSON conversion và xử lý lỗi.
- Test assert cả response và DB side effect, nên không chỉ kiểm tra một mock đã trả status đúng.

Với full context và MockMvc **đồng bộ**, test-managed transaction có thể bao bọc các thao tác cùng thread, nên dữ liệu thường rollback sau method. Không suy luận nó đúng cho controller chạy async/luồng khác. Nếu ứng dụng có Spring Security, MockMvc có thể đi qua security filters; test cần request authentication/CSRF hợp lệ thay vì vô hiệu hóa bảo mật để làm test xanh.

**Cẩn thận JSON number assertion:** ở ví dụ này `jsonPath("$.id").isNumber()` rồi dùng Jackson đọc ID; tránh viết một assertion so sánh boxed `Long` với `Integer` bị phụ thuộc JSONPath provider khi giá trị ID nhỏ.

## 9. HTTP server thật: RandomPortHttpTest.java

Tạo `src/test/java/example/contextdemo/RandomPortHttpTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class RandomPortHttpTest {
    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    GreetingRepository repository;

    private Long createdId;

    @AfterEach
    void removeOwnedTestData() {
        if (createdId != null
                && repository.existsById(createdId)) {
            repository.deleteById(createdId);
        }
    }

    @Test
    void realHttpRequestPersistsAndReadsGreeting()
            throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        URI endpoint = URI.create(
                "http://localhost:" + port + "/api/greetings");

        HttpRequest post = HttpRequest.newBuilder(endpoint)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"Minh\"}"))
                .build();
        HttpResponse<String> created = client.send(
                post, HttpResponse.BodyHandlers.ofString());

        assertEquals(201, created.statusCode());
        JsonNode body = objectMapper.readTree(created.body());
        assertEquals("Hello, Minh!",
                body.path("message").asText());

        long id = body.path("id").asLong();
        assertTrue(id > 0);
        createdId = id;
        assertTrue(repository.existsById(id));

        HttpRequest get = HttpRequest.newBuilder(
                URI.create(endpoint + "/" + id)).GET().build();
        HttpResponse<String> found = client.send(
                get, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, found.statusCode());
        JsonNode foundBody = objectMapper.readTree(found.body());
        assertEquals(id, foundBody.path("id").asLong());
        assertEquals("Hello, Minh!",
                foundBody.path("message").asText());
    }
}
```

`java.net.http.HttpClient` là thư viện chuẩn của Java 17, không cần thêm `TestRestTemplate`/`WebTestClient`. Test thực sự gửi HTTP qua socket tới embedded server trên random port; service thực lưu database và commit transaction phía server.

**Vì sao không gắn `@Transactional` vào test HTTP thật?** Client và server thường chạy ở các thread/transactions khác nhau, nên rollback test-managed transaction của client **không rollback** transaction server đã commit. Test dùng `@AfterEach` xóa **bản ghi do chính mình tạo**, thay vì `deleteAll()` gây ảnh hưởng test khác.

Đây là cleanup minh họa: nếu POST thành công nhưng network mất response trước khi đọc được ID, teardown trên có thể không biết cần xóa row nào. Với hệ thống production-like, nên có correlation ID/unique test identifier, DB/schema/container riêng hoặc fixture cleanup đáng tin cậy ngay cả khi test fail giữa chừng.

### Khi nào cần TestRestTemplate hoặc RestTestClient?

- Spring Boot 3.x có `TestRestTemplate` và các khả năng web client test khi có dependencies tương ứng.
- Spring Boot 4 reorganize các module test clients, có `RestTestClient` và `@AutoConfigureRestTestClient`; import và dependencies khác dòng 3.x.
- Java `HttpClient` là lựa chọn minh họa tránh phụ thuộc client test cụ thể, nhưng với suites lớn có thể dùng client hỗ trợ fluent assertions theo chính xác Boot version.

Không giả định mọi loại HTTP client luôn được Boot auto-inject chỉ nhờ `RANDOM_PORT`.

## 10. Chạy dự án và đọc báo cáo đúng cách

Cần JDK 17+, Maven và quyền tải Maven artifacts. Từ thư mục có `pom.xml`:

```bash
mvn test
```

Chạy từng nhóm:

```bash
mvn test -Dtest=ContextLoadsTest
mvn test -Dtest=ServiceIntegrationTest
mvn test -Dtest=MockMvcFullContextTest
mvn test -Dtest=RandomPortHttpTest
```

Dự án có **6 test methods**: 1 startup test, 2 service/JPA tests, 2 MockMvc tests, 1 HTTP server test. Kỳ vọng **6 passed, 0 failed, 0 skipped** khi môi trường và dependency đúng. Các method không gọi `System.out.println`, vì vậy không có stdout ứng dụng cố định; Maven và Hibernate có thể in log khác nhau. Báo cáo Surefire nằm ở `target/surefire-reports`.

| Test | Bằng chứng chính |
| --- | --- |
| `contextLoadsAndImportantBeansExist` | Boot context và bean graph thiết yếu tồn tại |
| `createsAndReadsPersistentGreeting` | Service chuẩn hóa input, JPA lưu/đọc |
| `rejectsBlankNameWithoutWritingNewRow` | Validation ném đúng lỗi, DB count không tăng |
| `postThenGetChecksHttpAndPersistence` | MockMvc POST 201, GET 200, JSON và row đúng |
| `invalidInputAndUnknownIdMapToHttpErrors` | HTTP 400/404 đúng contract, không ghi dữ liệu |
| `realHttpRequestPersistsAndReadsGreeting` | Embedded server nhận POST/GET qua HTTP thật và dữ liệu đã commit |

**Không dựa vào thứ tự chạy:** JUnit không hứa test classes chạy theo một thứ tự cụ thể. Ví dụ dùng rollback cho các tests `@Transactional`, cleanup đúng ID cho HTTP test và đo `count` tương đối so với trước hành động; không hard-code `id=1`.

## 11. Những giới hạn transaction thường gây hiểu nhầm

| Cách gọi | Transaction test thread | Dữ liệu thay đổi được rollback? |
| --- | --- | --- |
| Service/repository trong test `@Transactional` | Có | Thường có nếu join cùng transaction |
| MockMvc đồng bộ trong test `@Transactional` | Thường cùng thread | Thường có đối với thay đổi trong transaction |
| `RANDOM_PORT` HTTP thật | Server xử lý thread/transaction khác | **Không**, client rollback không hoàn tác server commit |
| Worker/event listener async | Transaction riêng | Không được rollback chỉ vì test transaction |
| HTTP API hoặc message broker ngoài | Ngoài transaction DB test | Cần cleanup/compensation riêng |

Các ngoại lệ như `REQUIRES_NEW`, commit sau callback, nhiều datasources hoặc async controller có thể khiến dữ liệu vẫn tồn tại dù test method được rollback. Khi mục tiêu là chứng minh **commit/rollback chính xác**, cần thiết kế integration test theo transaction boundary thật, không bọc mọi test bằng `@Transactional` theo thói quen.

Không dùng `@Rollback(false)` trong mọi test để xem dữ liệu sau chạy nếu không có dọn dẹp. Một test nên tạo data riêng và khôi phục môi trường của chính nó.

## 12. @SpringBootTest và test slices: chọn mức nhỏ nhất đủ chứng minh

| Câu hỏi | Mức kiểm thử đầu tiên | Khi nào cần full context? |
| --- | --- | --- |
| Hàm tính giá đúng không? | Pure JUnit/Mockito | Khi behavior phụ thuộc wiring/proxy/config thực |
| Controller parse JSON/map status đúng không? | `@WebMvcTest` + MockMvc | Khi muốn kiểm tra controller và service/repository thật cùng lúc |
| JPA mapping/query đúng không? | `@DataJpaTest` + test DB | Khi cần luồng nhiều tầng hoặc app config |
| Bean graph startup được không? | `@SpringBootTest` smoke | Phù hợp |
| HTTP request đi qua embedded server được không? | `@SpringBootTest(RANDOM_PORT)` | Phù hợp |
| Adapter làm việc với Kafka/Postgres thật? | Integration với broker/DB tương ứng | Có thể `@SpringBootTest` cùng Testcontainers |

**Đừng đặt `@WebMvcTest` và `@SpringBootTest` trên cùng một class** để “vừa slice vừa full”. Chúng chọn bootstrap không cùng mục tiêu; chọn một và cấu hình công cụ phù hợp. Full context có chi phí cao hơn, vì vậy test thuần nên giữ ở unit level.

Đối với ứng dụng sử dụng Spring Boot auto-configuration nâng cao, full context có giá trị chứng minh các thành phần hoạt động cùng nhau. Đối với method không cần container, `new Service(...)` và mock collaborator cho feedback nhanh hơn, dễ chẩn đoán hơn.

## 13. Mock dependency có kiểm soát

Full context không có nghĩa mọi dependency phải là thật. Nếu ứng dụng có một cổng gửi email hay thanh toán, có thể thay **biên ngoài** bằng Mockito mock:

```java
@SpringBootTest
@ActiveProfiles("test")
class SignupFlowIntegrationTest {
    @MockitoBean
    EmailGateway mailGateway;

    @Autowired
    SignupService service;

    // Các test methods sẽ assert kết quả signup và verify mailGateway.
}
```

Đây là **trích đoạn, không runnable độc lập**, vì `EmailGateway`/`SignupService` thuộc domain giả định khác. Trong Boot 3.5, `@MockitoBean` đến từ Spring Framework 6.2: `org.springframework.test.context.bean.override.mockito.MockitoBean`. `@MockBean` cũ của Boot đã deprecated ở 3.4/3.5 và bị loại bỏ khi chuyển sang Boot 4.

Giá trị của ví dụ: test có thể chứng minh nghiệp vụ đã **quyết định gọi email gateway** với đúng đối số, nhưng không chứng minh SMTP/remote email API hoạt động. Không mock repository nếu mục tiêu là test JPA persistence; không mock service nếu mục tiêu là test logic thật của service.

Một số bean test có thể cung cấp qua `@TestConfiguration` và `@Import`, ví dụ `Clock.fixed(...)`, fake adapter hoặc configuration của sandbox. Đặt test config trong `src/test` và chỉ import nơi cần; không tạo bean fake trong production configuration rồi dựa vào giả định profile sẽ luôn tắt nó.

## 14. Profile, datasource và external infrastructure

Một `@SpringBootTest` chỉ có ý nghĩa với **configuration được nó thực sự sử dụng**. Với profile `test`:

- Khai báo `@ActiveProfiles("test")` hoặc composed annotation tương đương.
- Ghi test properties tại `src/test/resources/application-test.properties`.
- Không để mật khẩu/URL production trong file.
- Dùng H2 cho bài học đơn giản; với PostgreSQL-specific behavior, test PostgreSQL thật qua Testcontainers.
- External API có thể dùng WireMock/MockWebServer, fake bean hoặc sandbox khi cần contract thật.
- Credential phục vụ CI nên cấp từ secret store, hạn chế scope và không log.

Nếu dùng Testcontainers, Spring Boot 3.1+ hỗ trợ `@ServiceConnection` thông qua `spring-boot-testcontainers`; `@DynamicPropertySource` cũng có thể đăng ký JDBC URL/port sinh tại runtime. Khi dynamic properties thay đổi giữa các test subclasses, cần kiểm tra compatibility với context caching và resource lifecycle để tránh test dùng lại connection cũ.

Không dùng `assumeTrue(false)` khi một dependency **bắt buộc của release job** không sẵn sàng. Điều đó biến lỗi hạ tầng thành “skipped” và có thể làm báo cáo xanh giả.

## 15. Context cache và @DirtiesContext

Spring TestContext cache `ApplicationContext` dựa trên merged context configuration (application/configuration classes, profiles, properties, initializers, context customizers, bean overrides, hierarchy...). Hai test classes có cấu hình tương đương có thể dùng lại context; context nạp một lần sẽ giúp suite nhanh hơn.

Hệ quả:

- Chỉ khác một property override hoặc một `@MockitoBean` cũng có thể tạo cache key khác.
- `@AutoConfigureMockMvc`/`RANDOM_PORT` không nhất thiết có cùng key với startup MOCK.
- `@DirtiesContext` đóng/loại context khỏi cache ở thời điểm tương ứng, khiến test sau phải nạp lại. Chỉ dùng khi bean/context bị thay đổi và không thể reset an toàn.
- Cùng context nghĩa là singleton bean có thể tồn tại qua nhiều test classes. **Context reuse không tự reset mutable bean state**.
- Context cache thường ở cùng JVM process; Maven/Gradle fork khác process sẽ không chia sẻ static cache.

Trong Spring Framework 6.1+, có **ApplicationContext failure threshold**: nếu cùng một context cache key đã load thất bại, một số lần load sau có thể bị bỏ qua để không lặp chi phí và chỉ báo ngưỡng lỗi. Khi thấy nhiều lỗi threshold, tìm exception root cause của **lần load đầu tiên**, không xem đó là nhiều lỗi độc lập.

## 16. Chẩn đoán lỗi startup và lỗi behavior

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Failed to load ApplicationContext` | Bean/config/profile/datasource/init lỗi | Xem root `Caused by` sâu nhất |
| `UnsatisfiedDependencyException` | Constructor yêu cầu bean không có | Kiểm tra component scan, profile, imports |
| `NoSuchBeanDefinitionException` | Bean không được đăng ký | Kiểm tra bean graph và conditions |
| `BeanCreationException` | Factory/init method ném lỗi | Đọc exception của bean gây lỗi |
| JPA schema chưa có | H2/driver/DDL/migration chưa đúng | Kiểm tra test DB và migration lifecycle |
| Port đã bị chiếm | DEFINED_PORT hoặc stub server dùng fixed port | Dùng RANDOM_PORT, cổng động |
| `MockMvc` không autowire được | Full context chưa có `@AutoConfigureMockMvc` hoặc thiếu module | Thêm cấu hình MVC test đúng Boot version |
| `@LocalServerPort` không có giá trị | Không mở server thật | Dùng RANDOM_PORT/DEFINED_PORT |
| contextLoads PASS, HTTP trả 404 | Mapping/controller route sai | MockMvc/HTTP test path thật |
| Test HTTP 201 nhưng DB không có row | Service không lưu/transaction rollback/DB khác | Assert persistence, kiểm tra datasource/transaction |
| Test RANDOM_PORT để lại row sau khi chạy | Server commit ở transaction khác | Cleanup theo ID hoặc DB riêng |
| Security 401/403 khi test | Filter chain đang chặn request | Cấp auth/CSRF theo contract, không tắt filter bừa |
| Nâng Boot thấy `ClassNotFoundException` | Test starters/imports khác major | Đồng bộ parent/BOM và module |
| Một mình PASS, chạy suite FAIL | DB/static mutable state, fixed ports, context reuse | Cô lập fixture/cleanup và kiểm tra parallel |
| Suite xanh nhưng 0 tests | Test runner/filter cấu hình sai | Xem Surefire reports và executed test count |

Khi context thất bại ở setup, các assertions trong test method **chưa chạy**; đừng gán lỗi cho `assertEquals`. Khi context thành công nhưng assertion sai, kiểm tra dữ liệu, business contract và call path thay vì reset toàn bộ Spring context ngay.

## 17. CI và tính ổn định

Một chiến lược kiểm thử hợp lý:

1. **Fast PR:** unit tests và slice tests cho feedback nhanh.
2. **Full-context integration:** smoke contextLoads và behavior integration với datasource/test infrastructure.
3. **HTTP integration:** RANDOM_PORT với random ports, rõ test ownership/cleanup.
4. **External integrations:** Testcontainers hoặc sandbox, chạy tại job có hạ tầng và secrets.
5. **Release verification:** kiểm tra các hành vi bắt buộc, số test thực thi, failed/skipped, không dựa vào một contextLoads duy nhất.

Nếu integration test flaky, xem thứ tự thực thi, resource lifecycle, transaction boundaries, static state, H2 DB URL, fixed port, async behavior và TestContext caching. Việc chạy lại test nhiều lần có thể giúp tái hiện nhưng không nên là cách che lỗi.

Đừng giả định tất cả tests chạy trong một process hay cùng một context. Build tool có thể fork JVM; JUnit có thể chạy song song nếu được bật. Khi dọn dữ liệu test, chỉ xóa tài nguyên thuộc phạm vi của chính test hoặc dùng DB/schema/container disposable.

## 18. Spring Boot 3.5 so với Spring Boot 4

Mã hoàn chỉnh trong bài **nhắm Spring Boot 3.5.0** và import `@AutoConfigureMockMvc` tương ứng. Khi dùng Boot 4:

- `@SpringBootTest` và bốn web environment modes vẫn mang ý nghĩa startup/HTTP tương tự.
- Test infrastructure được chia module theo công nghệ. Để test Spring MVC trong Boot 4, dùng focused starter phù hợp, chẳng hạn `spring-boot-starter-webmvc-test`; các import của `@AutoConfigureMockMvc` đổi theo module.
- Boot 4 có `RestTestClient` và `@AutoConfigureRestTestClient` theo các module test client; không copy `TestRestTemplate` package của Boot 3 một cách máy móc.
- `@MockitoBean` thuộc Spring Framework là hướng dùng thay `@MockBean` cũ.
- Đồng bộ JDK, Spring Framework 7, JUnit 6 và dependencies theo BOM/parent Boot 4.

Dùng Java `HttpClient` của JDK trong RANDOM_PORT test là cách ổn định để minh họa HTTP thật xuyên các dòng Boot, miễn application và test client được cấu hình tương thích.

## 19. Checklist nghiệm thu

- [ ] Đã phân biệt context startup với behavior assertions?
- [ ] Hiểu mặc định `@SpringBootTest` là MOCK, không mở server?
- [ ] Chọn webEnvironment theo mục tiêu: MOCK, RANDOM_PORT, DEFINED_PORT, NONE?
- [ ] Test startup xác nhận context và bean trọng yếu cần có?
- [ ] Test service/repository kiểm tra dữ liệu thật hoặc side effect đúng phạm vi?
- [ ] MockMvc test assert HTTP status, JSON body và hệ quả persistence?
- [ ] RANDOM_PORT test gửi HTTP thật tới port được inject?
- [ ] Các nhánh input sai và resource không tồn tại có assertion đúng contract?
- [ ] Test HTTP thật có cleanup, không giả định test `@Transactional` rollback server?
- [ ] Test không phụ thuộc ID cố định, thứ tự test hoặc dữ liệu của test khác?
- [ ] Test profile và datasource không có khả năng chạm production?
- [ ] Không mock dependency chính mà test đang tuyên bố kiểm chứng?
- [ ] Hiểu khác nhau giữa full `@SpringBootTest` và MVC/JPA test slices?
- [ ] Context cache/`@DirtiesContext` dùng có chủ đích?
- [ ] Khi startup lỗi, đã đọc root `Caused by` và log hạ tầng?
- [ ] Maven/CI thực sự chạy đủ test methods và báo 0 failures/errors/skips?
- [ ] Khi dùng Boot 4, đã cập nhật test starter và package imports?

## 20. Tài liệu chính thức để kiểm chứng

1. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, webEnvironment, MockMvc, running server và transaction caveat.
2. [Spring Boot 3.5 — Test Scope Dependencies](https://docs.spring.io/spring-boot/3.5/reference/testing/test-scope-dependencies.html): starter test và JUnit/Mockito.
3. [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): cơ sở dữ liệu/broker thật cho test.
4. [Spring Framework — TestContext Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache key, context failure threshold, `@DirtiesContext`.
5. [Spring Framework — Test Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, propagation và test transactions.
6. [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): runtime URLs/ports, subclass caching.
7. [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/): kiểm tra import và test modules trên dòng Boot mới.
8. [JUnit Jupiter User Guide](https://docs.junit.org/5.13.4/writing-tests/): lifecycle, assertions, test execution và filtering.

**Ghi nhớ:** một `contextLoads` PASS cho biết cấu hình đang thử **có thể khởi động**; kiểm tra service, MockMvc và HTTP thật cho biết **ứng dụng hành xử đúng qua các tầng**. Cần kết hợp cả startup, behavior và isolation dữ liệu để `@SpringBootTest` mang lại bằng chứng chất lượng thực sự.
