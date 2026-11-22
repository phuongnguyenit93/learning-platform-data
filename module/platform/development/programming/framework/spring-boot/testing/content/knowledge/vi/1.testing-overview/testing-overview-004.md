# Phân biệt Unit Test, Test Slice, Integration Test và End-to-End Test trong Spring Boot

> **Chủ đề:** Spring Boot – testing  
> **Ngữ cảnh:** Bức tranh kiểm thử  
> **Mục tiêu:** Chọn đúng phạm vi kiểm thử, hiểu thành phần nào được chạy thật hay thay thế, biết lỗi nào mỗi tầng có thể phát hiện và viết được các ví dụ tương ứng.

## 1. Bốn mức kiểm thử khác nhau ở đâu?

Đặt câu hỏi: **“Một test cần đi qua những ranh giới nào để chứng minh điều đang quan tâm?”** Không nên chỉ nhìn tên annotation. Cùng một `@SpringBootTest` có thể kiểm tra một bean với mock, toàn bộ ứng dụng cùng cơ sở dữ liệu, hoặc ứng dụng chạy qua cổng HTTP; phạm vi thực tế phụ thuộc vào cấu hình và dependency.

| Mức | Phạm vi chủ yếu | Spring context | Phụ thuộc ngoài | Chứng minh tốt nhất | Điểm mù thường gặp |
| --- | --- | --- | --- | --- | --- |
| **Unit test** | Một hàm/lớp hoặc một đơn vị hành vi nhỏ | **Không cần** | Thay bằng mock/fake khi cần | Quy tắc nghiệp vụ, nhánh điều kiện, xử lý lỗi của đơn vị | Không xác nhận wiring Spring, JSON/HTTP, SQL hay tích hợp thật |
| **Test slice** | Một lát công nghệ, như MVC hoặc JPA | **Có, nhưng thu hẹp** | Những phần bên ngoài lát thường mock hoặc dùng hệ thử nghiệm | Mapping HTTP, binding/validation, serialization; entity mapping/repository | Không chứng minh toàn bộ các tầng phối hợp chính xác |
| **Integration test** | Hai hay nhiều thành phần thật hoạt động cùng nhau | Thường **có** trong Spring Boot | Có thể dùng DB thật/Testcontainers, service giả lập hoặc DB nhúng theo mục tiêu | Wiring, transaction, repository, service, controller cùng vận hành | Nếu vẫn mock hoặc DB thử khác production thì chưa kiểm tra các phụ thuộc đó |
| **End-to-end (E2E)** | Luồng nghiệp vụ từ điểm vào bên ngoài đến kết quả quan sát được | Không bắt buộc nạp context vào **tiến trình test** | Hệ thống đã chạy, HTTP/UI, cấu hình và hạ tầng ở mức gần thực tế | Cấu hình triển khai, routing, xác thực, tương tác nhiều thành phần và luồng người dùng | Chậm, dễ bị môi trường/dữ liệu gây nhiễu, khó định vị lỗi khi đứng một mình |

Hai trục thường bị nhầm:

- **Độ rộng:** bao nhiêu lớp/hệ thống thật cùng tham gia?
- **Độ trung thực:** DB, HTTP server, dịch vụ bên thứ ba và cấu hình có giống môi trường sử dụng thật đến mức nào?

Vì vậy, test có HTTP thật nhưng chỉ chạy server nhúng và H2 trong cùng tiến trình vẫn là một **integration test qua HTTP** hữu ích; chưa mặc nhiên là E2E của hệ thống đã triển khai. Ngược lại, kiểm thử E2E có thể gọi REST API thay vì trình duyệt nếu API chính là điểm vào mà người dùng/khách hàng sử dụng.

## 2. Ví dụ xuyên suốt: API quản lý sách

Xét luồng:

`POST /books` → `BookController` → `BookService` → `BookRepository` → cơ sở dữ liệu; sau đó `GET /books/{id}` trả lại sách vừa tạo.

Ta sẽ kiểm tra cùng một ứng dụng ở các biên khác nhau. Mẫu dùng **Java 17, Maven, Spring Boot 3.5.0, JUnit Jupiter, Mockito, Spring MVC, Spring Data JPA và H2** để giữ import nhất quán. Đây là một dự án mẫu tối giản, không có authentication/validation nghiệp vụ nâng cao. Spring Boot 4 thay đổi một số package và mô-đun test; đừng trộn import giữa các dòng phiên bản.

Cấu trúc tệp:

```text
pom.xml
src/main/java/com/example/testing/
  TestingLevelsApplication.java
  Book.java
  BookRepository.java
  BookDto.java
  CreateBookRequest.java
  BookService.java
  BookController.java
src/test/java/com/example/testing/
  BookServiceTest.java
  BookControllerSliceTest.java
  BookRepositorySliceTest.java
  BookIntegrationTest.java
  BookHttpTest.java
  BookE2eTest.java
```

### 2.1. Maven dependencies

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>testing-levels</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <scope>runtime</scope>
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

`spring-boot-starter-test` mang đến JUnit Jupiter, AssertJ, Mockito và các tiện ích Spring Test phổ biến. H2 ở đây là database nhúng để ví dụ có thể chạy độc lập; với truy vấn đặc thù PostgreSQL/MySQL cần bổ sung integration test chạy đúng engine bằng Testcontainers hoặc môi trường thử nghiệm phù hợp.

### 2.2. Mã ứng dụng

Tạo từng tệp Java dưới `src/main/java/com/example/testing/` với **đúng** tên tương ứng trong chú thích.

```java
// TestingLevelsApplication.java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingLevelsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingLevelsApplication.class, args);
    }
}
```

```java
// Book.java
package com.example.testing;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Book() {} // JPA yêu cầu constructor không tham số.

    public Book(String title) {
        this.title = title;
    }

    // Chỉ dùng để dựng object đầu vào trong unit test/mock; không dùng để insert qua JPA.
    Book(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

```java
// BookRepository.java
package com.example.testing;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {}
```

```java
// BookDto.java
package com.example.testing;

public record BookDto(Long id, String title) {}
```

```java
// CreateBookRequest.java
package com.example.testing;

public record CreateBookRequest(String title) {}
```

```java
// BookService.java
package com.example.testing;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public BookDto create(String title) {
        Book saved = repository.save(new Book(title));
        return new BookDto(saved.getId(), saved.getTitle());
    }

    public Optional<BookDto> findById(long id) {
        return repository.findById(id)
                .map(book -> new BookDto(book.getId(), book.getTitle()));
    }
}
```

```java
// BookController.java
package com.example.testing;

import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookDto> create(@RequestBody CreateBookRequest request) {
        BookDto created = service.create(request.title());
        return ResponseEntity.created(URI.create("/books/" + created.id()))
                .body(created);
    }

    @GetMapping("/{id}")
    public ResponseEntity<BookDto> find(@PathVariable long id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

Ở ứng dụng này, `POST /books` hợp lệ trả **201 Created**, header `Location: /books/{id}` và JSON sách; `GET /books/{id}` tìm thấy trả **200 OK**, không tìm thấy trả **404 Not Found**. Đây là contract quan sát được. Do H2 nằm trên classpath và không có công cụ migration, Spring Boot có thể khởi tạo schema cho database nhúng; ví dụ không nhằm mô tả cấu hình schema production.

## 3. Unit test: cô lập một đơn vị

**Mục tiêu:** chứng minh `BookService` biến dữ liệu từ repository thành DTO đúng cách mà không nạp Spring context, không gửi HTTP, không dùng database. Mockito thay thế repository; chỉ service chạy thật.

```java
// BookServiceTest.java
package com.example.testing;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class BookServiceTest {
    @Mock
    BookRepository repository;

    @InjectMocks
    BookService service;

    @Test
    void convertsFoundBookToDto() {
        when(repository.findById(7L))
                .thenReturn(Optional.of(new Book(7L, "Java")));

        assertThat(service.findById(7L))
                .contains(new BookDto(7L, "Java"));
        verify(repository).findById(7L);
    }

    @Test
    void returnsEmptyWhenBookDoesNotExist() {
        when(repository.findById(99L)).thenReturn(Optional.empty());

        assertThat(service.findById(99L)).isEmpty();
    }
}
```

**Điểm cốt lõi:** `@Mock` là Mockito mock độc lập với Spring; `@InjectMocks` dựng service và tiêm mock vào constructor. Không dùng `@SpringBootTest` chỉ để test một phép biến đổi hoặc nhánh if. Test có thể pass dù SQL, cấu hình bean, JSON endpoint bị lỗi: đó không phải lỗi của unit test mà là giới hạn phạm vi được chọn.

Unit test phù hợp với phép tính giá, chuyển đổi trạng thái, phân quyền bằng hàm thuần, validate rule nghiệp vụ. Với những logic không phụ thuộc framework, gọi constructor trực tiếp còn đơn giản hơn Mockito.

## 4. Test slice: kiểm thử một lát framework

Một slice nạp **một phần** ApplicationContext để kiểm tra hành vi framework thực của tầng đó. Nó nằm giữa unit và tích hợp toàn ứng dụng. Hai ví dụ thường gặp:

### 4.1. MVC slice với `@WebMvcTest`

`@WebMvcTest(BookController.class)` kiểm tra routing, Jackson JSON, status, binding và xử lý request của controller bằng `MockMvc`. Nó không chạy HTTP server thật. `BookService` được thay bằng mock **trong Spring context** qua `@MockitoBean`.

```java
// BookControllerSliceTest.java
package com.example.testing;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerSliceTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    BookService service;

    @Test
    void mapsGetAndSerializesDto() throws Exception {
        when(service.findById(7L))
                .thenReturn(Optional.of(new BookDto(7L, "Java")));

        mockMvc.perform(get("/books/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.title").value("Java"));
    }

    @Test
    void mapsMissingBookTo404() throws Exception {
        when(service.findById(99L)).thenReturn(Optional.empty());

        mockMvc.perform(get("/books/99"))
                .andExpect(status().isNotFound());
    }
}
```

Ở Spring Boot 3.5, import `@WebMvcTest` là `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest`. `@MockitoBean` đến từ Spring Framework (`org.springframework.test.context.bean.override.mockito.MockitoBean`); đây là hướng mới thay cho `@MockBean` đã bị deprecated từ Spring Boot 3.4. Không trộn `@Mock` (chỉ Mockito) với `@MockitoBean` (ghi đè/đăng ký bean trong context).

**Giới hạn:** 200/404 và JSON có thể đúng dù service thật gọi repository sai. Nếu dự án có Spring Security, filter và authorization có thể tham gia MVC slice; phải cung cấp user/CSRF test phù hợp thay vì vô hiệu hóa security tùy tiện. Khi thiếu converter, mapper hay config cần thiết, cân nhắc `@Import` có mục đích và giữ slice gọn.

### 4.2. JPA slice với `@DataJpaTest`

`@DataJpaTest` chỉ nạp cơ chế persistence cần thiết như entity mapping, `JpaRepository`, EntityManager và DataSource. Nó không nạp toàn bộ controller/service. Với H2 trong dependency, test dưới đây dùng database nhúng thực sự và mặc định rollback transaction của mỗi test.

```java
// BookRepositorySliceTest.java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class BookRepositorySliceTest {
    @Autowired
    BookRepository repository;

    @Test
    void persistsAndReadsBook() {
        Book saved = repository.saveAndFlush(new Book("Database"));

        assertThat(repository.findById(saved.getId()))
                .hasValueSatisfying(found ->
                        assertThat(found.getTitle()).isEqualTo("Database"));
    }
}
```

**Điểm cốt lõi:** đây là test tích hợp ở **lát dữ liệu**, dù thường được gọi riêng là “slice test”. Nó kiểm tra mapping/truy vấn với DB; không chạy logic HTTP. Với SQL native, index, transaction isolation hay dialect khác H2, dùng cơ sở dữ liệu cùng loại môi trường thật (thường nhờ Testcontainers) để tăng độ tin cậy. `saveAndFlush` giúp đẩy SQL xuống DB trước khi đọc/đánh giá các ràng buộc.

## 5. Integration test: nhiều tầng thật hợp tác

**Mục tiêu:** kiểm tra controller → service → repository → DB cùng hoạt động trong một ApplicationContext. `@SpringBootTest` nạp cấu hình ứng dụng; `@AutoConfigureMockMvc` cung cấp MockMvc mà không cần cổng HTTP. Không mock `BookService` hoặc `BookRepository` trong test này.

```java
// BookIntegrationTest.java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class BookIntegrationTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    BookRepository repository;

    @Test
    void controllerServiceRepositoryAndDbWorkTogether() throws Exception {
        Book saved = repository.saveAndFlush(new Book("Integration"));

        mockMvc.perform(get("/books/" + saved.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Integration"));
    }
}
```

Test này sẽ bắt được các lỗi mà unit và MVC slice có thể bỏ qua: thiếu bean, tiêm dependency sai, cách service map entity, repository không hoạt động với schema test, lỗi nối các tầng.

`@Transactional` trong test MockMvc thông thường giúp rollback dữ liệu thử nghiệm vì request được xử lý cùng luồng giao dịch của test. **Đừng mặc định rollback theo cách đó khi gọi server qua HTTP thật:** request được xử lý ở luồng khác, transaction của test không bao quanh transaction server. Với test HTTP, cần reset dữ liệu bằng cơ chế rõ ràng, ID riêng, truncate hoặc cô lập database/container.

### 5.1. Integration qua HTTP thật nhưng vẫn ở trong tiến trình test

`@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động embedded server trên cổng ngẫu nhiên. `TestRestTemplate` gọi qua socket HTTP thật, nên còn kiểm tra HTTP serialization, server và request dispatch. Dữ liệu vẫn nằm ở ứng dụng test + H2, chưa phải bản triển khai production.

```java
// BookHttpTest.java
package com.example.testing;

import java.util.Objects;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void createsThenReadsViaRealHttp() {
        ResponseEntity<BookDto> created = http.postForEntity(
                "/books", new CreateBookRequest("HTTP"), BookDto.class);

        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        BookDto book = Objects.requireNonNull(created.getBody());

        ResponseEntity<BookDto> read =
                http.getForEntity("/books/" + book.id(), BookDto.class);

        assertThat(read.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(read.getBody()).isEqualTo(book);
    }
}
```

Sự khác biệt giữa hai test tích hợp trên là **ranh giới HTTP và server thực**, không đơn giản ở tên annotation. Cả hai có thể sử dụng database nhúng; cả hai đều kiểm chứng sự phối hợp nhiều tầng.

## 6. End-to-end test: đi từ bên ngoài một hệ thống đang chạy

**Mục tiêu:** xác nhận một kịch bản sử dụng hoàn chỉnh đối với **bản ứng dụng được chạy như một hệ thống**: gửi lệnh tạo sách, theo `Location` nhận được, rồi đọc lại sách. Test là HTTP client riêng, không tạo Spring context hoặc repository bằng cách tiêm bean vào test. Bản kiểm thử càng gần production (database, reverse proxy, auth, service dependency, migrations...), mức tự tin càng cao.

Đây là một E2E ở **ranh giới REST API**. Nếu sản phẩm có giao diện web, hãy bổ sung E2E trình duyệt bằng Playwright/Selenium để xác minh UI → API → DB → UI; HTTP-only test không chứng minh hành vi JavaScript hay giao diện.

```java
// BookE2eTest.java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.assertj.core.api.Assertions.assertThat;

@EnabledIfEnvironmentVariable(named = "E2E_BASE_URL", matches = "https?://.+")
class BookE2eTest {
    @Test
    void createsAndRetrievesBookFromRunningApp() throws Exception {
        URI base = URI.create(System.getenv("E2E_BASE_URL") + "/");
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest create = HttpRequest.newBuilder(base.resolve("books"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"title\":\"External flow\"}"))
                .build();

        HttpResponse<String> created = client.send(
                create, HttpResponse.BodyHandlers.ofString());

        assertThat(created.statusCode()).isEqualTo(201);

        String location = created.headers()
                .firstValue("Location").orElseThrow();
        HttpRequest get = HttpRequest.newBuilder(base.resolve(location))
                .GET()
                .build();

        HttpResponse<String> found = client.send(
                get, HttpResponse.BodyHandlers.ofString());

        assertThat(found.statusCode()).isEqualTo(200);
        assertThat(found.body()).contains("\"title\":\"External flow\"");
    }
}
```

`@EnabledIfEnvironmentVariable` chỉ cho chạy test khi `E2E_BASE_URL` có giá trị; vì thế lệnh `mvn test` thông thường bỏ qua E2E ngoài hệ thống. Khi chạy với `E2E_BASE_URL=http://localhost:8080`, test gửi request tới server đang chạy ở địa chỉ này; có thể đổi thành URL staging đã chuẩn bị.

**Cảnh báo về “E2E” trên thực tế:** gọi một instance chạy local bằng H2 kiểm tra được luồng từ client ngoài nhưng vẫn chưa bao trùm load balancer, secret, database production-like hay nhiều service. Một E2E có ý nghĩa phải nêu rõ **môi trường và ranh giới được bao phủ**. Tránh gọi “full E2E” nếu phần quan trọng của hệ thống vẫn mock.

## 7. Cách chạy và đọc kết quả

Trong thư mục chứa `pom.xml`, sử dụng JDK 17+ và Maven 3.9+:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=BookServiceTest test
mvn -Dtest=BookControllerSliceTest test
mvn -Dtest=BookRepositorySliceTest test
mvn -Dtest=BookIntegrationTest test
mvn -Dtest=BookHttpTest test
```

Mỗi lệnh `-Dtest=...` chạy test class tương ứng; `mvn test` chạy các test trong project, còn `BookE2eTest` được bỏ qua khi chưa có biến môi trường. Vì log Maven, cổng random và ID do DB sinh thay đổi theo lần chạy, **không có một transcript stdout cố định đáng tin**. Điều cần kiểm tra là build thành công, các assertion pass và không có test nào bị bỏ qua ngoài chủ ý.

Để chạy E2E qua một server riêng, mở terminal 1:

```bash
mvn spring-boot:run
```

Sau khi server đã sẵn sàng, mở terminal 2 (Bash):

```bash
E2E_BASE_URL=http://localhost:8080 mvn -Dtest=BookE2eTest test
```

Tương đương trong PowerShell:

```powershell
$env:E2E_BASE_URL = "http://localhost:8080"
mvn -Dtest=BookE2eTest test
Remove-Item Env:E2E_BASE_URL
```

Với ứng dụng mẫu, request hợp lệ có dạng:

```http
POST /books HTTP/1.1
Content-Type: application/json

{"title":"External flow"}
```

Response dự kiến: **201 Created** và header `Location` trỏ tới `/books/<id>`; `GET` URL đó sẽ trả **200 OK** cùng JSON chứa `title: "External flow"`. ID là số được DB sinh, không dự đoán trước.

## 8. Chọn mức nào cho từng thay đổi?

| Thay đổi / rủi ro | Kiểm thử nên ưu tiên | Vì sao |
| --- | --- | --- |
| Quy tắc giảm giá, làm tròn, phân loại đơn hàng | Unit test nhiều trường hợp | Feedback nhanh, xét đủ nhánh và biên mà không phải dựng app |
| Đổi đường dẫn, request body, status code, JSON DTO | `@WebMvcTest` | Bắt lỗi mapping, converter, request/response contract của MVC |
| Đổi quan hệ JPA, câu query, constraint, khóa ngoại | `@DataJpaTest` với DB phù hợp | Bắt lỗi persistence thực; dùng DB giống thật khi có SQL đặc thù |
| Đổi transaction/service flow giữa nhiều bean | `@SpringBootTest` + thành phần thật | Chứng minh wiring và dòng chảy qua các tầng |
| Đổi HTTP server config, serialization toàn app | `@SpringBootTest(RANDOM_PORT)` | Chứng minh có thể giao tiếp qua network socket thật |
| Đổi triển khai, API gateway, auth, luồng mua hàng/đăng ký | E2E trên môi trường đang chạy | Quan sát hành vi từ điểm vào hệ thống, phát hiện lỗi cấu hình hoặc tích hợp ngoài |

Không cần “mỗi phương thức một E2E”. Một chiến lược là **nhiều unit test nhỏ**, các slice test đúng biên framework, integration test cho đường phối hợp quan trọng và **một số E2E đại diện cho hành trình có giá trị cao**. Độ nhiều ít phụ thuộc chi phí và rủi ro, không có tỷ lệ phần trăm bắt buộc.

### Luồng suy luận nhanh

1. Nếu lỗi có thể chứng minh từ một hàm/đơn vị cô lập → bắt đầu bằng **unit**.
2. Nếu lỗi liên quan hành vi framework trong đúng một tầng → dùng **slice**.
3. Nếu lỗi chỉ xuất hiện khi nhiều tầng chạy cùng nhau → dùng **integration**.
4. Nếu cần chứng minh người dùng/khách hàng tương tác được với hệ thống đã chạy và cấu hình môi trường → dùng **E2E**.
5. Nếu lỗi vượt ra dịch vụ khác, thêm contract test, giả lập dịch vụ có kiểm soát hoặc integration test với dependency thật tùy rủi ro; đây là các kỹ thuật bổ trợ chứ không phải nhãn thay thế cho bốn mức trên.

## 9. Lỗi phổ biến và cách tránh

**1. Gọi `@SpringBootTest` là unit test.** Nó tạo context nên đang kiểm tra hơn một đơn vị, thường làm bộ test chậm mà không tăng giá trị cho quy tắc nghiệp vụ đơn giản. Dùng JUnit + Mockito hoặc class thật khi không cần Spring.

**2. Mock đến mức test chỉ xác nhận cách mock được cấu hình.** Nếu mock controller, service và repository rồi assert dữ liệu dựng sẵn, bạn chưa kiểm chứng đường đi thực nào. Chỉ thay dependency nằm ngoài ranh giới mục tiêu; assert đầu ra/hệ quả quan sát được.

**3. Coi `MockMvc` là HTTP server thật.** MockMvc xử lý request qua Spring MVC test infrastructure, không mở socket. Dùng `RANDOM_PORT` + HTTP client khi cần kiểm tra network stack.

**4. Dùng H2 để khẳng định SQL PostgreSQL/MySQL chắc chắn chạy.** DB dialect, kiểu dữ liệu, transaction và index có thể khác. Đối với truy vấn phức tạp, dùng Testcontainers hoặc DB thử nghiệm đúng hệ.

**5. Giả định rollback tự động cho E2E qua HTTP.** Transaction của test và request server thường khác luồng. Làm sạch dữ liệu tường minh, tạo test data riêng biệt và test phải chạy lại được.

**6. Chỉ kiểm tra happy path.** Bổ sung ID không tồn tại (404), dữ liệu sai (400 khi có validation), xung đột, authorization (401/403), rollback/constraint, timeout và lỗi dịch vụ khi phù hợp. Không có một tầng kiểm thử nào tự động bảo đảm tất cả tình huống đó.

**7. E2E chạy thiếu ổn định.** Tránh phụ thuộc thứ tự test, ID cố định, thời gian chờ bằng `sleep`, dữ liệu dùng chung và service bên ngoài không kiểm soát. Chờ theo trạng thái/điều kiện, cô lập dữ liệu, cung cấp health checks, lưu log và định rõ môi trường.

**8. Dựa hoàn toàn vào số lượng test/coverage.** Một test bao đúng ranh giới có thể mang nhiều giá trị hơn nhiều test chỉ gọi getter hoặc khẳng định mock. Cần xem xét mức rủi ro đã được bảo vệ, assertion có ý nghĩa và tính lặp lại.

## 10. Tự kiểm tra hiểu bài

- `BookServiceTest` pass nhưng `BookControllerSliceTest` fail vì đổi `@GetMapping("/books/{id}")` thành URL khác. Vì sao unit không phát hiện? → Unit không gọi MVC routing; MVC slice mới bao đường dẫn.
- MVC slice pass nhưng `BookIntegrationTest` fail do không tạo được bean `BookRepository`. Vì sao? → Service/repository thật bị mock hoặc không nạp trong MVC slice.
- `BookRepositorySliceTest` pass trên H2 nhưng staging lỗi SQL riêng PostgreSQL. Cần gì? → Test persistence bằng cùng database engine/dialect, kiểm tra migrations/schema.
- `BookHttpTest` pass nhưng yêu cầu qua gateway thực tế trả 502. Cần gì? → E2E/kiểm thử triển khai bao gồm gateway và dependency thật.
- E2E fail lúc tạo sách. Làm sao xác định nhanh? → Truy bằng log/correlation ID, chạy integration → slice → unit theo đường lỗi; giữ test hẹp để định vị.

## 11. Nguồn tham khảo chính thức

- Spring Boot 3.5 – Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 – Testing how-to: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Framework 6.2 – `@MockitoBean` và `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/

**Tiêu chí nhận biết đã hiểu:** có thể nói rõ trong mỗi test **thành phần nào chạy thật, thành phần nào được giả lập, boundary nào được đi qua, lỗi nào test có khả năng phát hiện và lỗi nào nằm ngoài phạm vi**.