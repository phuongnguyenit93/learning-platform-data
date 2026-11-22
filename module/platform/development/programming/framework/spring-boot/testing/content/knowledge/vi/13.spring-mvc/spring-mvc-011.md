# MockMvcTester trong các phiên bản hỗ trợ của Spring MVC và Spring Boot

## 1. Mục tiêu và phạm vi

`MockMvcTester` là API kiểm thử **Spring MVC** dùng `MockMvc` ở bên dưới và cung cấp cú pháp assertion theo **AssertJ**. Nó giúp viết những phép kiểm HTTP mock request dễ đọc hơn mà không phải thay đổi controller hay khởi động HTTP server.

Bạn sẽ học cách:

- Xác định **phiên bản Spring Framework / Spring Boot** nào có `MockMvcTester`.
- Phân biệt `MockMvcTester`, `MockMvc`, `WebTestClient` và HTTP client thật.
- Cấu hình đúng trong `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc` và test standalone.
- Viết request GET/POST, URL template, query parameter, header, request body; kiểm status, text, JSON, JSONPath, content type.
- Tái sử dụng một `MvcTestResult` để kiểm nhiều điều kiện mà không thực thi request nhiều lần.
- Hiểu exception handling, async exchange, security filters, CSRF, cách làm việc với matchers cũ.
- Chẩn đoán lỗi thiếu class/bean, lỗi MVC slice, sai dependency, HTTP 401/403/404 và test flakiness.
- Chạy bài thực hành Java 17+, Maven, JUnit Jupiter với Spring Boot **3.5.16**.

**Không nhầm:** `MockMvcTester` thuộc mô hình **mock servlet request**; mặc định nó không mở cổng TCP, không kiểm trực tiếp TLS, HTTP/2, container error pages, reverse proxy hay deployment. Dù dùng `@SpringBootTest`, nếu bài test chỉ gọi `MockMvcTester` thì request vẫn đi qua MockMvc.

Ví dụ ý tưởng:

```java
assertThat(mvc.get().uri("/books/7"))
        .hasStatusOk()
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .bodyJson()
        .isLenientlyEqualTo("""
                {"id":7,"title":"Spring Testing","status":"AVAILABLE"}
                """);
```

Biến `mvc` có kiểu `MockMvcTester`. `assertThat` được import từ AssertJ. Toàn bộ ứng dụng và test để chạy ví dụ trên được cung cấp trong phần thực hành.

## 2. Các phiên bản hỗ trợ

### 2.1. Mốc xuất hiện

`MockMvcTester` được Spring Framework **6.2** giới thiệu trong thư viện `spring-test`. Spring Boot **3.4** là dòng Boot đầu tiên dùng Framework 6.2 theo BOM mặc định. Các phiên bản trước đó không có lớp này trong API tương ứng.

| Version | Sử dụng MockMvcTester? | Hướng xử lý |
| --- | --- | --- |
| Spring Framework 6.1.x trở xuống | Không có lớp `MockMvcTester` | Giữ `MockMvc`/Hamcrest hoặc nâng Framework đồng bộ |
| Spring Framework 6.2.x | Có | Import từ `org.springframework.test.web.servlet.assertj` |
| Spring Boot 3.3.x theo BOM | Chưa có (Framework 6.1.x) | Dùng MockMvc truyền thống |
| Spring Boot 3.4.x | Có, khi AssertJ/test dependencies đủ | `@WebMvcTest` và `@AutoConfigureMockMvc` có tích hợp |
| Spring Boot 3.5.x | Có; ví dụ này dùng 3.5.16 | Có thể inject bean khi auto-configuration phù hợp |
| Spring Boot 4.x / Spring Framework 7.x | Hỗ trợ AssertJ cho MVC tiếp tục tồn tại; tổ chức package test của Boot khác major 3 | Tra tài liệu/migration guide theo major, không copy tất cả import 3.x |

### 2.2. Import đúng

```java
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.assertj.MvcTestResult;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
```

Đừng tìm `MockMvcTester` trong `org.assertj.core.api`. Nó là class của **Spring Framework spring-test** với integration AssertJ. `MockMvc` truyền thống nằm trong package `org.springframework.test.web.servlet`; hai lớp cùng tồn tại và có thể kiểm một application.

### 2.3. Điều kiện classpath và cấu hình

Có class trên classpath **khác** có bean auto-configured trong test context:

- `spring-test` phiên bản 6.2+ cung cấp lớp `MockMvcTester`.
- AssertJ phải có mặt để sử dụng hỗ trợ AssertJ.
- Spring MVC servlet infrastructure phải được cấu hình khi muốn request được xử lý qua context.
- Trong Spring Boot 3.5, `@WebMvcTest` auto-configure `MockMvc` và `MockMvcTester` nếu có AssertJ.
- `@SpringBootTest` cần thêm `@AutoConfigureMockMvc` để auto-configure tester trong web MVC mock environment.
- Với JUnit thuần không có Spring TestContext, tạo tester bằng `MockMvcTester.of(...)`, `from(...)` hoặc `create(...)`, không mong chờ `@Autowired` tự hoạt động.

`spring-boot-starter-test` Boot 3.5 mang theo AssertJ, JUnit Jupiter, Mockito và các thư viện hỗ trợ test phổ biến. Project demo còn khai báo `spring-boot-starter-web` để có Spring MVC/Jackson.

### 2.4. Kiểm dependency khi bị lỗi

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
mvn dependency:tree -Dincludes=org.assertj:assertj-core
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-test-autoconfigure
```

Nếu `spring-test` thực tế vẫn là 6.1.x, import `MockMvcTester` sẽ không compile. **Không** sửa bằng cách pin một mình `spring-test` 6.2 bên cạnh các Spring modules 6.1; nâng BOM Spring Boot thống nhất hoặc tiếp tục dùng `MockMvc`. Khi nâng Boot 4, kiểm packages mới của các annotation Boot, chẳng hạn `@AutoConfigureMockMvc`, thay vì dùng lại import của Boot 3.5.

## 3. MockMvcTester khác gì MockMvc?

### 3.1. Cùng hệ thống request handling

```text
JUnit @Test
    |
    +-- MockMvcTester: fluent request + AssertJ
    |           |
    |           v
    |         MockMvc
    |           |
    +-- MockMvc: perform + andExpect (Hamcrest)
                |
                v
        MockHttpServletRequest/Response
                |
                v
       DispatcherServlet, filters, MVC handlers
                |
                v
       @RestController / @ControllerAdvice
                |
                v
       Service và collaborator trong test context
```

Cả hai kiểm **Spring MVC** trong JVM, sử dụng mock Servlet API. Không tạo HTTP connection đến server thật. Đường đi từ controller tới service còn phụ thuộc scope của test: MVC slice có thể mock service, full context giữ service thật.

### 3.2. MockMvc truyền thống

```java
mockMvc.perform(get("/books/7"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("Spring Testing"));
```

Đoạn này thuộc test có `MockMvc mockMvc`, các static imports `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status` và `jsonPath`, thường khai báo `throws Exception`.

### 3.3. MockMvcTester + AssertJ

```java
assertThat(mvc.get().uri("/books/7"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.title")
        .asString()
        .isEqualTo("Spring Testing");
```

Cú pháp này thuộc test có `MockMvcTester mvc`. AssertJ cung cấp fluent assertions. Cả hai kiểu có thể được dùng trong cùng suite; không có yêu cầu phải chuyển đổi toàn bộ test cũ.

### 3.4. Vì sao chọn AssertJ integration?

- Tìm method qua IDE dễ: `hasStatusOk`, `bodyJson`, `hasContentTypeCompatibleWith`.
- Cú pháp thống nhất `assertThat(...)` với assert domain/collection trong các unit tests khác.
- Dễ chọn JSONPath hoặc so JSON có cấu trúc thay vì raw string.
- Có `MvcTestResult` để kiểm nhiều thuộc tính của một request.
- Async requests mặc định có cơ chế đợi hoàn tất trong `exchange()`.
- Có thể gọi các legacy result matchers hoặc handlers khi cần.

Đây là cải tiến **test DSL và maintainability**, không phải một HTTP server test engine khác. Nếu ứng dụng cũ đang dùng MockMvc tốt và team hiểu API đó, việc migrate không bắt buộc.

## 4. Ba cách tạo tester đúng mục tiêu

### 4.1. MVC slice — @WebMvcTest

```java
@WebMvcTest(BookController.class)
class BookControllerSliceTest {
    @Autowired
    MockMvcTester mvc;

    @MockitoBean
    BookCatalog catalog;
}
```

`@WebMvcTest` đưa vào các MVC components/auto-configuration cần thiết, không tự scan mọi `@Service`/`@Repository`. `@MockitoBean` cấp collaborator của controller. Đừng nhầm nó với `@Mock`: `@Mock` tạo object Java, không tự thay một bean trong Spring context.

### 4.2. Full context — @SpringBootTest + @AutoConfigureMockMvc

```java
@SpringBootTest
@AutoConfigureMockMvc
class BookFullContextTest {
    @Autowired MockMvcTester mvc;
}
```

`@SpringBootTest` tải application context rộng; `@AutoConfigureMockMvc` thêm mock MVC testing infrastructure. Không có HTTP port bắt buộc. Với dự án có datasource/broker, full context có thể cần test profile/Testcontainers hoặc adapter doubles phù hợp.

### 4.3. Standalone — không cần Boot context

```java
MockMvcTester mvc =
        MockMvcTester.of(new BookController(new BookCatalog()));
```

`MockMvcTester.of(...)` tạo standalone MVC setup với controller object mà test tự cung cấp. Nó không tự quét application package, không tự tải mọi `@ControllerAdvice`/filter/security config của app. Phù hợp để kiểm một controller nhẹ nhưng không thay thế hoàn toàn context-based tests.

### 4.4. Từ WebApplicationContext hoặc MockMvc

```java
MockMvcTester fromContext = MockMvcTester.from(webApplicationContext);
MockMvcTester fromMvc = MockMvcTester.create(existingMockMvc);
```

Đây là **mẫu minh họa trong test đã có hai biến tương ứng**. `from(...)` dùng MVC WebApplicationContext; `create(...)` thích hợp khi bạn đã cấu hình `MockMvc` thủ công và muốn tái sử dụng trong AssertJ DSL.

## 5. Phép kiểm căn bản

### 5.1. GET với URI template

```java
assertThat(mvc.get().uri("/books/{id}", 7L))
        .hasStatusOk();
```

`{id}` được thay bằng biến đã cung cấp. Không nối chuỗi URI với input chưa mã hóa thủ công nếu có ký tự đặc biệt; dùng URI template hoặc request parameter APIs.

### 5.2. Header Accept và Content-Type

```java
assertThat(mvc.get().uri("/books/7")
        .accept(MediaType.APPLICATION_JSON))
        .hasStatusOk()
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

`Accept` mô tả kiểu response client mong đợi; `Content-Type` mô tả kiểu request body. Nếu gửi JSON POST, cần `contentType(MediaType.APPLICATION_JSON)`. Nhầm hai header có thể gây HTTP 406 hoặc 415 dù route đúng.

### 5.3. Query parameter

```java
assertThat(mvc.get().uri("/books/search")
        .param("q", "spring"))
        .hasStatusOk();
```

`param("q",...)` gửi servlet request parameter đã decode. Nếu dùng URI template query string, framework sẽ xử lý phần encoding/decoding theo URI builder; đặc biệt lưu ý `+`, `%` và ký tự tiếng Việt.

### 5.4. POST JSON

```java
assertThat(mvc.post().uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"id":11,"title":"Java Web","status":"AVAILABLE"}
                """))
        .hasStatus(HttpStatus.CREATED);
```

Cú pháp trên sẽ được dùng trong project mẫu; không có database. Với Spring Security và CSRF, một request POST có thể nhận 403 nếu chưa cung cấp CSRF token, khác với lỗi binding JSON.

### 5.5. Status và text body

```java
assertThat(mvc.get().uri("/books/8"))
        .hasStatus(HttpStatus.NOT_FOUND);
```

```java
// Ví dụ cho endpoint GET /ping trả body text/plain "pong"
assertThat(mvc.get().uri("/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

Ví dụ `/ping` là **minh họa** (không có trong project mẫu); không tự cho rằng endpoint tồn tại nếu chưa tạo controller phù hợp. Với JSON body, dùng `bodyJson()` thay vì so raw text nếu thứ tự thuộc tính không phải contract.

### 5.6. So JSON theo cấu trúc

```java
assertThat(mvc.get().uri("/books/7"))
        .hasStatusOk()
        .bodyJson()
        .isLenientlyEqualTo("""
                {
                    "id": 7,
                    "title": "Spring Testing",
                    "status": "AVAILABLE"
                }
                """);
```

`isLenientlyEqualTo` dùng chính sách JSON comparator lenient của thư viện JSON testing. Hãy hiểu semantics của JSONAssert/phiên bản (object property order và các khác biệt) trước khi quyết định lenient/strict. Nếu chỉ quan tâm một field, JSONPath rõ ràng hơn; nếu array order là contract, kiểm thứ tự thay vì bỏ qua.

### 5.7. JSONPath chọn một field

```java
assertThat(mvc.get().uri("/books/7"))
        .bodyJson()
        .extractingPath("$.title")
        .asString()
        .isEqualTo("Spring Testing");
```

Cần JSONPath trên test classpath, thường đã có trong Spring Boot starter test. Với số, object hoặc list, dùng typed assertions phù hợp chứ không ép tất cả thành string.

## 6. MvcTestResult: không gửi request hai lần

### 6.1. Lấy kết quả một lần

```java
MvcTestResult result =
        mvc.get().uri("/books/7").exchange();

assertThat(result).hasStatusOk();
assertThat(result)
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
assertThat(result)
        .bodyJson()
        .extractingPath("$.title")
        .asString()
        .isEqualTo("Spring Testing");
```

`exchange()` thực thi request và trả kết quả để tái sử dụng. Đây là lựa chọn tốt với nhiều assertions độc lập, nhất là endpoint có side effects.

### 6.2. Tránh vô tình lặp request

Hai lệnh sau tạo **hai** exchanges:

```java
assertThat(mvc.get().uri("/books/7")).hasStatusOk();
assertThat(mvc.get().uri("/books/7"))
        .bodyJson()
        .extractingPath("$.title")
        .asString()
        .isEqualTo("Spring Testing");
```

Với GET không side effect, đôi khi không đáng ngại. Nhưng với POST tạo bản ghi, gọi hai lần có thể sinh hai row/event. Dùng `MvcTestResult` cho nhiều checks trên cùng response.

### 6.3. Request builder tự chạy khi được AssertJ bọc

`assertThat(mvc.get().uri(...))` dùng integration với AssertJ, nên bạn không nhất thiết gọi `exchange()` trong assertion đơn giản. Nếu muốn phân biệt rõ Given/When/Then hoặc debug response, `exchange()` giúp cấu trúc bài test dễ theo dõi.

## 7. Project Maven hoàn chỉnh (Java 17 / Spring Boot 3.5.16)

Dự án có `BookController`, `BookCatalog`, record `BookView` và bốn lớp test: MVC slice, standalone, full context, tích hợp MockMvc legacy.

### 7.1. Thư mục

```text
mockmvctester-lab/
├── pom.xml
├── src/main/java/com/example/mvctester/
│   ├── MvcTesterApplication.java
│   ├── BookView.java
│   ├── BookCatalog.java
│   └── BookController.java
└── src/test/java/com/example/mvctester/
    ├── BookControllerSliceTest.java
    ├── BookControllerStandaloneTest.java
    ├── FullMvcMockTest.java
    └── LegacyAndTesterIntegrationTest.java
```

Mọi file Java có package `com.example.mvctester`.

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mockmvctester-lab</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot parent/BOM quản lý Spring Framework, JUnit, AssertJ, Mockito và các dependency khác. Không pin riêng `spring-test` hoặc `assertj-core` khi không có lý do cụ thể.

### 7.3. MvcTesterApplication.java

`src/main/java/com/example/mvctester/MvcTesterApplication.java`:

```java
package com.example.mvctester;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcTesterApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcTesterApplication.class, args);
    }
}
```

### 7.4. BookView.java

`src/main/java/com/example/mvctester/BookView.java`:

```java
package com.example.mvctester;

public record BookView(long id, String title, String status) {}
```

Dùng Java record để định nghĩa JSON response. Trong ứng dụng thực tế, DTO có thể chứa nested objects, timestamps, validation annotations; những phần đó không cần cho ví dụ này.

### 7.5. BookCatalog.java

`src/main/java/com/example/mvctester/BookCatalog.java`:

```java
package com.example.mvctester;

import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookCatalog {

    public Optional<BookView> find(long id) {
        if (id == 7L) {
            return Optional.of(
                    new BookView(7L, "Spring Testing", "AVAILABLE"));
        }
        return Optional.empty();
    }

    public List<BookView> search(String q) {
        if ("spring".equalsIgnoreCase(q)) {
            return List.of(
                    new BookView(7L, "Spring Testing", "AVAILABLE"));
        }
        return List.of();
    }
}
```

Service không kết nối DB; kết quả xác định. Điều đó giúp phân biệt test controller có mock service với full context dùng service thật.

### 7.6. BookController.java

`src/main/java/com/example/mvctester/BookController.java`:

```java
package com.example.mvctester;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
public class BookController {

    private final BookCatalog catalog;

    public BookController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    public ResponseEntity<BookView> find(@PathVariable long id) {
        return catalog.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/search")
    public List<BookView> search(@RequestParam String q) {
        return catalog.search(q);
    }

    @PostMapping
    public ResponseEntity<BookView> create(@RequestBody BookView request) {
        if (request.title() == null || request.title().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(request);
    }
}
```

Contract minh họa:
- `GET /books/7` trả 200, JSON BookView.
- `GET /books/8` trả 404.
- `GET /books/search?q=spring` trả JSON array.
- `POST /books` trả 201 nếu title hợp lệ, 400 nếu title trống.

POST ở đây chỉ echo DTO để thử JSON binding, **không** thực hiện persistence/ID generation.

### 7.7. BookControllerSliceTest.java

`src/test/java/com/example/mvctester/BookControllerSliceTest.java`:

```java
package com.example.mvctester;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebMvcTest(BookController.class)
class BookControllerSliceTest {

    @Autowired
    MockMvcTester mvc;

    @MockitoBean
    BookCatalog catalog;

    @Test
    void getsBookAsJson() {
        when(catalog.find(7L))
                .thenReturn(Optional.of(
                        new BookView(7L, "Spring Testing", "AVAILABLE")));

        assertThat(mvc.get().uri("/books/{id}", 7L)
                .accept(MediaType.APPLICATION_JSON))
                .hasStatusOk()
                .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .bodyJson()
                .isLenientlyEqualTo("""
                        {"id":7,"title":"Spring Testing","status":"AVAILABLE"}
                        """);

        verify(catalog).find(7L);
    }

    @Test
    void missingBookReturns404() {
        when(catalog.find(8L)).thenReturn(Optional.empty());

        assertThat(mvc.get().uri("/books/8"))
                .hasStatus(HttpStatus.NOT_FOUND);

        verify(catalog).find(8L);
    }

    @Test
    void searchUsesRequestParam() {
        when(catalog.search("spring"))
                .thenReturn(List.of(
                        new BookView(7L, "Spring Testing", "AVAILABLE")));

        assertThat(mvc.get().uri("/books/search")
                .param("q", "spring"))
                .hasStatusOk()
                .bodyJson()
                .isLenientlyEqualTo("""
                        [
                          {"id":7,"title":"Spring Testing","status":"AVAILABLE"}
                        ]
                        """);

        verify(catalog).search("spring");
    }

    @Test
    void postJsonReturnsCreated() {
        assertThat(mvc.post().uri("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"id":11,"title":"Java Web","status":"AVAILABLE"}
                        """))
                .hasStatus(HttpStatus.CREATED)
                .bodyJson()
                .isLenientlyEqualTo("""
                        {"id":11,"title":"Java Web","status":"AVAILABLE"}
                        """);
    }

    @Test
    void postBlankTitleReturnsBadRequest() {
        assertThat(mvc.post().uri("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"id":11,"title":" ","status":"AVAILABLE"}
                        """))
                .hasStatus(HttpStatus.BAD_REQUEST);
    }
}
```

Trong slice:
- `BookController` và MVC infrastructure thật.
- `BookCatalog` mock do `@MockitoBean` cung cấp.
- `MockMvcTester` được Boot auto-configure khi AssertJ có mặt.
- Các assertions kiểm HTTP mapping/JSON/delegation, **không** kiểm logic thật của Catalog service.
- POST không cần stub catalog vì controller method trong mẫu không gọi Catalog.

Nếu có thêm Spring Security starter, cần bổ sung principal/CSRF phù hợp; `spring-boot-starter-web` đơn thuần của POM này không thêm Security filter chain.

### 7.8. BookControllerStandaloneTest.java

`src/test/java/com/example/mvctester/BookControllerStandaloneTest.java`:

```java
package com.example.mvctester;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

class BookControllerStandaloneTest {

    private final MockMvcTester mvc =
            MockMvcTester.of(new BookController(new BookCatalog()));

    @Test
    void standaloneGetUsesJavaService() {
        assertThat(mvc.get().uri("/books/7")
                .accept(MediaType.APPLICATION_JSON))
                .hasStatusOk()
                .bodyJson()
                .isLenientlyEqualTo("""
                        {"id":7,"title":"Spring Testing","status":"AVAILABLE"}
                        """);
    }

    @Test
    void standaloneNotFound() {
        assertThat(mvc.get().uri("/books/8"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
```

Đây là MVC standalone test không `@Autowired`, không khởi động application context. Test chủ động tạo controller và BookCatalog Java objects. Các global `@ControllerAdvice`, security filters hay MVC converters tùy biến khác của production **không tự được scan**.

### 7.9. FullMvcMockTest.java

`src/test/java/com/example/mvctester/FullMvcMockTest.java`:

```java
package com.example.mvctester;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureMockMvc
class FullMvcMockTest {

    @Autowired
    MockMvcTester mvc;

    @Test
    void fullContextUsesRealBookCatalog() {
        assertThat(mvc.get().uri("/books/7"))
                .hasStatusOk()
                .bodyJson()
                .isLenientlyEqualTo("""
                        {"id":7,"title":"Spring Testing","status":"AVAILABLE"}
                        """);
    }

    @Test
    void fullContextMissingBook() {
        assertThat(mvc.get().uri("/books/8"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
```

Trong full context, `BookCatalog` thật hoạt động. `@AutoConfigureMockMvc` cung cấp `MockMvcTester` để test controller qua mock request. Nó khác kiểm server thật ở `@SpringBootTest(RANDOM_PORT)`.

### 7.10. LegacyAndTesterIntegrationTest.java

`src/test/java/com/example/mvctester/LegacyAndTesterIntegrationTest.java`:

```java
package com.example.mvctester;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LegacyAndTesterIntegrationTest {

    @Autowired MockMvc mockMvc;
    @Autowired MockMvcTester tester;

    @Test
    void legacyMatcherStillWorks() throws Exception {
        mockMvc.perform(get("/books/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Spring Testing"));
    }

    @Test
    void testerCanUseLegacyMatcher() {
        assertThat(tester.get().uri("/books/7"))
                .matches(status().isOk());
    }

    @Test
    void testerCanWrapExistingMockMvc() {
        MockMvcTester adapted = MockMvcTester.create(mockMvc);

        assertThat(adapted.get().uri("/books/7"))
                .hasStatusOk();
    }
}
```

Không cần xóa test dùng `MockMvc` khi áp dụng `MockMvcTester`. Có thể giữ `ResultMatcher` cũ qua `matches(...)`; `MockMvcTester.create(mockMvc)` giúp tái sử dụng một MockMvc đã có setup.

### 7.11. Lệnh chạy

Trong thư mục `mockmvctester-lab`:

```bash
mvn -q clean test

mvn -q -Dtest=BookControllerSliceTest test
mvn -q -Dtest=BookControllerStandaloneTest test
mvn -q -Dtest=FullMvcMockTest test
mvn -q -Dtest=LegacyAndTesterIntegrationTest test
```

Các test được thiết kế để PASS khi source/dependencies đúng. Maven trả exit code `0` khi test thành công; log/khởi động context tùy môi trường. Xem report tại:

```text
target/surefire-reports/
```

Khi chạy application thật:

```bash
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl "http://localhost:8080/books/7"
```

Response JSON chứa `id=7`, `title="Spring Testing"` và `status="AVAILABLE"` (thứ tự thuộc tính không quan trọng). Đây là request HTTP thật tới app, khác với mock exchange từ tester.

## 8. Thủ công cấu hình thêm tester

### 8.1. Từ WebApplicationContext

```java
// Minh họa trong test có @Autowired WebApplicationContext wac
MockMvcTester mvc = MockMvcTester.from(wac);
```

`from` dùng Spring MVC WebApplicationContext đã cấu hình. Nó phù hợp khi test không dùng Boot auto-configuration hoặc muốn tùy chỉnh builder. Chỉ có ý nghĩa với servlet MVC context; không dùng thay thế WebFlux WebHandler binding.

### 8.2. Từ MockMvc có sẵn

```java
// Minh họa trong test có một MockMvc đã được cấu hình:
MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

Nếu MockMvc cũ có filters/custom request builders/result handlers, bạn có thể giữ setup và bắt đầu dùng AssertJ assertions. Với JSON-to-domain conversion, có thể cần đăng ký message converters bằng `withHttpMessageConverters(...)` khi dùng tester do tự tạo.

### 8.3. Tích hợp matcher/handler cũ

```java
assertThat(mvc.get().uri("/books/7"))
        .matches(status().isOk());
```

`matches` nhận MockMvc `ResultMatcher`. `apply(...)` có thể dùng với `ResultHandler` như `print()` hoặc Spring REST Docs. Các ví dụ tích hợp chính thức cho phép migrate dần, không cần viết lại custom matchers ngay.

### 8.4. JSON-to-domain conversion

```java
assertThat(mvc.get().uri("/books/7"))
        .bodyJson()
        .convertTo(BookView.class)
        .satisfies(book -> {
            assertThat(book.id()).isEqualTo(7L);
            assertThat(book.title()).isEqualTo("Spring Testing");
        });
```

Đây là mẫu nâng cao cần message converter phù hợp, như Jackson trong MVC context. Nếu converter không được đăng ký trong standalone tester, kiểm JSON bằng `bodyJson().isLenientlyEqualTo(...)` hoặc cấu hình `withHttpMessageConverters(...)`. JSON assertion và domain conversion không phải cùng một việc.

## 9. Async MVC và exception handling

### 9.1. Async exchange

Với MVC controller trả `Callable` hoặc `DeferredResult`, `exchange()` có cơ chế đợi completion trước khi assertion; default async timeout của tester thường được tài liệu phiên bản 6.2 mô tả là 10 giây. Có thể chỉ định timeout:

```java
MvcTestResult result = mvc.get()
        .uri("/reports/slow")
        .exchange(java.time.Duration.ofSeconds(5));

assertThat(result).hasStatusOk();
```

Đoạn này là **minh họa**, yêu cầu có endpoint `/reports/slow`. Không hiểu 5 giây ở đây là network timeout của production HTTP client. Nếu muốn kiểm initial async state, nghiên cứu `asyncExchange()` thay vì `exchange()`.

### 9.2. HTTP error response khác exception chưa được xử lý

`BookController` trả `ResponseEntity.notFound().build()` cho ID không tồn tại, nên request hoàn thành với HTTP 404. Test đúng là `hasStatus(HttpStatus.NOT_FOUND)`, **không** phải `hasFailed()`.

Ngược lại, nếu controller ném exception chưa được Spring MVC handler/resolver xử lý, tester có thể biểu diễn failed exchange:

```java
// Mẫu minh họa khi /boom ném exception chưa được xử lý
assertThat(mvc.get().uri("/boom"))
        .hasFailed()
        .failure()
        .hasMessageContaining("unexpected");
```

Không tự khẳng định unhandled exception sẽ luôn biến thành status 500 trong MockMvc. Với `@RestControllerAdvice` xử lý exception thành response 400/404/409, hãy assert **status và JSON error body** theo HTTP contract.

### 9.3. Test failure và lỗi config

Nếu `@Autowired MockMvcTester` fail vì không có bean, test có thể chưa chạy tới `@Test`. Đây là lỗi context setup/auto-configuration. Nếu request chạy tới `assertThat(...)` nhưng status/body khác expected, đó là assertion mismatch. Nếu controller ném exception bất ngờ, đọc root cause và exception resolver trước khi sửa expected.

## 10. Security và filters

### 10.1. MVC slice có thể có Spring Security

Nếu application có Spring Security, `@WebMvcTest`/`@AutoConfigureMockMvc` có thể đưa filter chain vào MockMvc. Request chưa authenticate có thể trả 401/302; POST thiếu CSRF có thể trả 403.

Cách xử lý:
- Bổ sung `spring-security-test` nếu cần auth principal/roles request post processors.
- Dùng `@WithMockUser` hoặc test security request post processors đúng với security stack.
- Với POST/PUT/PATCH/DELETE, cân nhắc CSRF theo ứng dụng.
- Không bỏ filters toàn cục chỉ để mọi test trả 200; việc đó che security bugs.

### 10.2. addFilters

```java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityMvcExample {
    @Autowired MockMvcTester mvc;
}
```

Đây là **snippet minh họa**; project mẫu không thêm Security starter. `addFilters=true` muốn filters từ application context tham gia mock requests. Có thể tắt filters cho test rất hẹp với lý do rõ ràng, nhưng phải có các test khác kiểm policy.

### 10.3. Test MockMvcTester không kiểm network security

Security filter ở MVC layer có thể được kiểm, nhưng TLS certificate, proxy headers được rewrite bởi ingress và network authentication nằm ngoài MockMvc. Dùng running server/deployed environment test cho những rủi ro đó.

## 11. So sánh với WebTestClient và test HTTP thật

| Câu hỏi | MockMvc | MockMvcTester | WebTestClient |
| --- | --- | --- | --- |
| Stack mặc định | Spring MVC | Spring MVC | WebFlux mock / MockMvc-backed / live HTTP |
| Request API | `perform` | `get/post().uri` | `get/post().uri().exchange` |
| Assertion | `andExpect` + Hamcrest/ResultMatcher | AssertJ | WebTestClient expectations |
| Cần server thật? | Không | Không | Không bắt buộc; có thể bindToServer |
| Servlet mock pipeline | Có | Có (dùng MockMvc) | Có nếu bind đến MockMvc |
| Phiên bản hỗ trợ | Đã lâu | Spring Framework 6.2+ | Spring WebFlux test support |
| Test real HTTP | Không | Không | Có nếu bindToServer |
| MVC web slice Boot 3.5 | Auto-configured | Auto-configured nếu AssertJ | Có thể dùng adapter khi dependency đủ |

Nếu cần test **WebFlux**, dùng `@WebFluxTest` và `WebTestClient`. Nếu cần kiểm MVC nhưng thích DSL của WebTestClient, Spring Framework có MockMvcWebTestClient adapter. Nhưng đừng đánh đồng những API đó với `MockMvcTester`: chúng có điểm vào, response assertions và binding mechanisms khác nhau.

Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, một HTTP client như `TestRestTemplate` hoặc WebTestClient (khi cấu hình phù hợp) mới đi qua server port. `MockMvcTester` luôn là MockMvc facade, kể cả khi dùng trong test đồng thời có server chạy.

## 12. Các lỗi phổ biến và cách sửa

### 12.1. Cannot resolve symbol MockMvcTester

**Nguyên nhân:** `spring-test` còn ở 6.1 hoặc import sai. **Sửa:** kiểm BOM/dependency tree và dùng package `org.springframework.test.web.servlet.assertj.MockMvcTester`. Không pin riêng một Spring Framework module 6.2 cạnh nhiều modules 6.1.

### 12.2. No qualifying bean of type MockMvcTester

**Nguyên nhân:** có class nhưng không có bean auto-configured. **Sửa:** với Boot 3.5 MVC dùng `@WebMvcTest` hoặc `@SpringBootTest + @AutoConfigureMockMvc`; bảo đảm AssertJ có trên classpath. Với unit test không Spring dùng `of(...)` thay vì autowire.

### 12.3. @WebMvcTest thiếu collaborator

**Nguyên nhân:** slice không scan service/repository như full app. **Sửa:** `@MockitoBean` cho service collaborator hoặc `@Import` nếu thực sự muốn service thật. Không dùng `@Mock` rồi nghĩ nó đã vào Spring context.

### 12.4. AssertJ dependency thiếu

**Nguyên nhân:** `assertj-core` bị exclude hoặc version conflict. **Sửa:** kiểm dependency management của `spring-boot-starter-test`; tránh trộn thư viện theo bản tùy ý.

### 12.5. Controller trả 404 dù test expect 200

**Nguyên nhân:** URI/scope controller, mapping, path variables, context path, security hoặc profile sai. **Sửa:** kiểm request URI và handler mappings trong MVC test context; không gắn `@AutoConfigureMockMvc` với ý nghĩ nó sửa URL.

### 12.6. GET có body JSON nhưng JsonPath báo lỗi

**Nguyên nhân:** test thiếu JSONPath, response content không phải JSON, field path sai hoặc converter không phù hợp. **Sửa:** kiểm content type trước, dùng `bodyJson` và JSONPath đúng; trong standalone test đăng ký converters nếu cần conversion.

### 12.7. Body JSON order thay đổi

**Nguyên nhân:** dùng raw string equality thay vì structural comparison. **Sửa:** `bodyJson().isLenientlyEqualTo(...)` hoặc JSONPath; với array có thứ tự contract thì dùng strict/explicit ordering assertions.

### 12.8. POST bị 403 trong MVC slice

**Nguyên nhân:** Spring Security + CSRF. **Sửa:** setup principal và CSRF đúng policy; không đổi expected sang 403 khi contract là 201 với user hợp lệ.

### 12.9. Assertion đang gửi request hai lần

**Nguyên nhân:** tạo hai builder/assertions riêng cho cùng endpoint. **Sửa:** `MvcTestResult result = ...exchange();` rồi assert nhiều lần trên `result`.

### 12.10. @SpringBootTest(RANDOM_PORT) nhưng tưởng tester gọi server

**Nguyên nhân:** nhầm MockMvc facade với HTTP client. **Sửa:** dùng client hướng tới port thật khi cần kiểm network; đừng suy luận từ annotation rằng mọi request đều đi qua server.

### 12.11. Async request bị timeout

**Nguyên nhân:** controller không hoàn tất async result, deadlock, quá chậm hoặc test timeout ngắn. **Sửa:** kiểm request lifecycle và timeout; `exchange(Duration)` là timeout ở async test layer, không chữa code block event-loop/thread pool.

### 12.12. Standalone PASS nhưng full context FAIL

**Nguyên nhân:** standalone chưa có custom advice, security, filters, object mapper, converters hoặc property sources của ứng dụng. **Sửa:** cấu hình standalone thích hợp hoặc bổ sung `@WebMvcTest`/full context test cho contract cần bảo vệ.

### 12.13. Trộn Spring Boot 3/4 imports

**Nguyên nhân:** Boot 4 tổ chức lại một số test package và starter/module. **Sửa:** theo migration guide đúng major; không ghép Boot 4 runtime với Spring Boot 3.5 test-autoconfigure cũ chỉ vì IDE muốn compile.

## 13. Tình huống nâng cao

### 13.1. Headers, cookies, redirects và MVC result matchers

Không phải API nào cũng cần assertion mới. Với custom `ResultMatcher` cho redirect, cookie hoặc model/view, dùng `matches(...)` để giữ rule cũ. Với custom result handler/documentation, `apply(...)` cho phép tích hợp. Việc đó quan trọng khi migrate một codebase lớn có kiểm thử chuyên sâu.

### 13.2. Multipart

```java
// Minh họa khi có POST /upload
assertThat(mvc.post().uri("/upload")
        .multipart()
        .file("note.txt", "Hello".getBytes(
                java.nio.charset.StandardCharsets.UTF_8)))
        .hasStatusOk();
```

Multipart ở MockMvc là mock Servlet request; không kiểm behavior thật của container parser/file size limits. Dùng integration test thực tế khi upload infrastructure là rủi ro cần bảo vệ.

### 13.3. Context path/servlet path

```java
// Minh họa nếu ứng dụng có context path /app và servlet path /main
assertThat(mvc.get().uri("/app/main/books/7")
        .contextPath("/app")
        .servletPath("/main"))
        .hasStatusOk();
```

Không thêm hai path này vào project mẫu, vì nó không cấu hình servlet path như trên. Nếu app có context/servlet path, test phải mô phỏng đúng routing context.

### 13.4. Jackson converter và domain conversion

Khi dùng `bodyJson().convertTo(BookView.class)`, cần message converter (Jackson) phù hợp. Với `MockMvcTester.of(...)` standalone và custom ObjectMapper, conversions có thể khác full app. Khi kiểm JSON serialization quan trọng, dùng MVC slice có cấu hình mapper cần thiết hoặc full context để tránh test sai implementation.

### 13.5. Exception chưa được xử lý

Nếu request ném exception mà không có resolver xử lý, tester có thể assert `hasFailed`/`failure`. Nếu controller advice đã map thành response 4xx, đó là completed exchange, nên assert HTTP status/error JSON. Đừng bắt buộc exception từ controller phải bay qua test method khi contract là HTTP response.

## 14. Bài tập tự luyện

1. Boot 3.3 dùng Spring 6.1: vì sao import `MockMvcTester` không compile? Chỉ ra hai hướng nâng cấp/giữ API cũ không phá BOM.
2. Chuyển một GET test từ `perform(get(...)).andExpect(status().isOk())` sang `assertThat(mvc.get().uri(...)).hasStatusOk()`.
3. Dùng `MvcTestResult` kiểm status, content type và title JSON của **cùng** request.
4. Tạo `@WebMvcTest(BookController.class)`, mock BookCatalog bằng `@MockitoBean`, giải thích vì sao `@Mock` không đủ để inject vào controller.
5. Chạy `@SpringBootTest + @AutoConfigureMockMvc`, so sánh kết quả với slice mock service.
6. Dùng `MockMvcTester.of(...)` tạo controller thuần Java; phân tích những MVC features không tự mang theo.
7. Viết test POST JSON hợp lệ và title trống; với Spring Security, cần điều chỉnh request như thế nào khi CSRF bật?
8. So một JSON object qua raw string và qua `bodyJson`; giải thích khi nào object property order không nên được coi là contract.
9. Nêu sự khác nhau giữa 404 response từ `ResponseEntity.notFound()` và unhandled exception cần `hasFailed`.
10. Giải thích vì sao MockMvcTester PASS không chứng minh TLS, reverse proxy hay servlet container error page hoạt động.

Tiêu chí đạt: biết **framework version**, **kiểu web stack**, **mức test**, **setup mock request**, và **assertion nào kiểm được hợp đồng gì** trước khi chọn code.

## 15. Checklist trước khi merge test

- [ ] `spring-test` thực tế là 6.2+ và import `MockMvcTester` đúng package?
- [ ] Boot 3.4+/3.5+ có đủ AssertJ và test dependencies, không trộn Spring modules không tương thích?
- [ ] Đã chọn MVC servlet test, không phải WebFlux?
- [ ] Nếu `@WebMvcTest`, controller có collaborator cần `@MockitoBean`?
- [ ] Nếu `@SpringBootTest`, đã thêm `@AutoConfigureMockMvc`?
- [ ] Nếu không Spring, dùng `MockMvcTester.of`/`from`/`create` đúng cách?
- [ ] URI, path variable, params, Accept, Content-Type đúng contract?
- [ ] Assert status, JSON/text/body theo representation thực?
- [ ] Với JSONPath, dependency và path đúng; với domain conversion, converter có sẵn?
- [ ] Có một `MvcTestResult` khi cần nhiều assertion trên cùng request?
- [ ] Test security có principal/role/CSRF đúng; không tắt filters vô cớ?
- [ ] HTTP error response được phân biệt với exception chưa được handle?
- [ ] Async request có completion/timeout được xác định?
- [ ] Không tuyên bố đã kiểm real network/TLS/container khi chỉ dùng MockMvc?
- [ ] Khi migrate, đã tận dụng legacy `matches`/`apply` nếu cần?
- [ ] Đã chạy thử Maven/Gradle test task và xem root cause khi fail?

**Kết luận:** `MockMvcTester` là AssertJ facade của `MockMvc`, được giới thiệu trong **Spring Framework 6.2** và thuận tiện từ **Spring Boot 3.4+**. Trong Boot 3.5, `@WebMvcTest` có thể auto-configure tester khi có AssertJ; với `@SpringBootTest` hãy dùng `@AutoConfigureMockMvc`. Nó kiểm hành vi MVC bằng **mock Servlet requests**, không thay thế WebFlux test hay integration test qua network.

## 16. Tài liệu chính thức

- Spring Framework 6.2 — MockMvc AssertJ integration: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj.html
- Spring Framework 6.2 — Configuring MockMvcTester: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/setup.html
- Spring Framework 6.2 — Performing Requests: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/requests.html
- Spring Framework 6.2 — Defining Expectations và JSON Support: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/assertions.html
- Spring Framework 6.2 — Legacy MockMvc integration: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/integration.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — `@AutoConfigureMockMvc` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html
- Spring Framework 6.2 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes
- Spring Boot 4 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
