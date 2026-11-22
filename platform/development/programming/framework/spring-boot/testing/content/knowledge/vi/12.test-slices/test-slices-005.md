# Phân biệt cấu hình test slice với ApplicationContext đầy đủ trong Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm:** Test slice  
> **Bài học:** Phân biệt cấu hình slice với context ứng dụng đầy đủ  
> **Mục tiêu:** Hiểu chính xác Spring Boot tạo bean và auto-configuration nào trong một slice test, khác gì với `@SpringBootTest`; biết cách bổ sung dependency cho slice mà không vô tình nạp cả ứng dụng; lựa chọn đúng mức test, profile, database và mock HTTP.

## 1. Ý tưởng cốt lõi: “slice” là phạm vi ApplicationContext, không phải chỉ là test ngắn hơn

Spring Boot cho phép chạy test theo hai chiến lược khác nhau:

- **Test slice** dùng annotation như `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest` hoặc `@WebFluxTest`. Spring Boot chỉ cấu hình những thành phần liên quan đến **một lát chức năng** cần kiểm tra: ví dụ controller và MVC infrastructure, hoặc entity và JPA repository. Các bean service/repository/HTTP client không thuộc lát đó **thường không được component-scan vào context**.
- **Test context đầy đủ** dùng `@SpringBootTest` để tạo ứng dụng qua cơ chế `SpringApplication`, sử dụng cấu hình chính, component scanning và auto-configuration theo classpath, properties, profiles và những điều kiện hiện hành. Nó kiểm tra sự phối hợp giữa nhiều lớp bean thực hơn, nhưng thường khởi động nặng hơn và có thể cần cấu hình hạ tầng ngoài.

**Hai điều không được đánh đồng:**

1. **“Full application context” không có nghĩa mọi thứ trong môi trường production đều chạy.** `@SpringBootTest` vẫn phụ thuộc profiles, conditional beans, classpath và cấu hình test. Nếu test sử dụng mock, DB giả hoặc stub, các phần đó không trở thành production integration.
2. **“Slice” không có nghĩa toàn bộ dependency đều là mock.** Ví dụ `@WebMvcTest` vẫn tạo MVC infrastructure thật (handler mappings, JSON converters, controller advice, filters phù hợp). Nó chỉ không tự nạp phần lớn business services và repositories.

Một cách nhớ:

```text
                ỨNG DỤNG SPRING BOOT
  +----------------------------------------------------+
  | MVC: Controller + converter + filter + advice      |
  |----------------------------------------------------|
  | Business: Service + validation + domain logic      |
  |----------------------------------------------------|
  | Data: Repository + JPA + DataSource                |
  |----------------------------------------------------|
  | Outbound: HTTP client + event publisher + adapters |
  +----------------------------------------------------+

  @WebMvcTest             @DataJpaTest          @SpringBootTest
  +----------------+     +----------------+     +-------------------------+
  | MVC            |     | Entity + JPA   |     | Các bean đủ điều kiện    |
  | Controller thật|     | Repository thật|     | trong toàn ứng dụng     |
  | Service mock * |     | DB test        |     | theo profile/config     |
  +----------------+     +----------------+     +-------------------------+
       * Được thêm tường minh bằng @MockitoBean
```

Ký hiệu “slice chỉ một phần” là **sơ đồ tư duy**, không phải thuật toán chính xác của mọi auto-configuration. Thành phần nào được nạp cần xem annotation cụ thể và Spring Boot version đang sử dụng.

## 2. So sánh nhanh các annotation test

| Lựa chọn | Bean/configuration chủ yếu được nạp | Thường không được nạp | Công cụ chính | Bài toán phù hợp |
| --- | --- | --- | --- | --- |
| `@WebMvcTest(BookController.class)` | MVC infrastructure, controller được chỉ định, MVC-related components, `MockMvc` | Business `@Service`, repository tùy ý | `MockMvc`, `@MockitoBean` | Mapping, binding, validation, response JSON/status |
| `@WebFluxTest(Controller.class)` | Reactive web controller và WebFlux-related components | Service/repository ngoài lát reactive web | `WebTestClient` bind context | API reactive controller |
| `@DataJpaTest` | `@Entity`, JPA repositories, `EntityManager`, transaction, DataSource test | MVC controller, service nghiệp vụ thường | `TestEntityManager`, repositories | Entity mapping, query, constraints |
| `@JdbcTest` | `DataSource`, `JdbcTemplate`, transaction | Service, MVC, Spring Data repository không được chọn | `JdbcTemplate` | SQL/JDBC thuần |
| `@JsonTest` | JSON mapper, module/component JSON và các tester phù hợp | Controller, business service, data layer | `JacksonTester`/JSON helpers | Serialize/deserialize contract |
| `@RestClientTest(Client.class)` | Client được chỉ định, JSON support, client builder, `MockRestServiceServer` | Toàn bộ service/repository/controller khác | HTTP mock server in-memory | Request/response outbound của REST client |
| `@SpringBootTest` | Application configuration, component scan, auto-configurations đủ điều kiện | Không có danh sách loại trừ theo “slice”; vẫn chịu conditions/profiles | Spring beans + test utilities bổ sung | Wiring/tích hợp nhiều tầng, hành vi ứng dụng |

**Điểm chính:** những annotation `@*Test` không chỉ thay đổi số class được quét; chúng còn giới hạn hoặc lựa chọn **auto-configuration** phù hợp mục đích. Không nên đọc bảng theo nghĩa “chỉ có đúng một loại bean duy nhất”.

### 2.1. Test slice vẫn dùng Spring TestContext

`@WebMvcTest` và `@DataJpaTest` không giống unit test thuần `new MyService(...)`. Chúng vẫn khởi tạo Spring `ApplicationContext` bằng test bootstrapper của Spring Boot, xử lý dependency injection, test properties và caching. Do đó slice test có thể fail vì cấu hình bean, profile hoặc converter, mặc dù phạm vi hẹp.

`@SpringBootTest` tạo context ứng dụng rộng; nó không bắt buộc khởi động embedded HTTP server. **Mặc định `webEnvironment = MOCK`**: môi trường web mô phỏng nhưng **không mở HTTP listening port**. Khi cần socket HTTP thật chọn `RANDOM_PORT` hoặc `DEFINED_PORT`.

### 2.2. Test slice không tự tạo Mockito mock cho mọi service

Nếu controller có constructor:

```java
public BookController(BookService service) {
    this.service = service;
}
```

thì `@WebMvcTest(BookController.class)` thường **không nạp `BookService` chỉ vì controller cần nó**. Thiếu dependency, context sẽ không dựng được nếu chưa cấp một bean thay thế. Cách trực tiếp:

```java
@MockitoBean
BookService service;
```

Spring Framework 6.2 và Spring Boot 3.5 có `@MockitoBean` để tạo hoặc override bean trong test context. Nó khác `@Mock` thuần của Mockito: `@Mock` tạo Java mock trong test class, **không tự đặt mock vào Spring bean registry**. Dòng Spring Boot cũ có `@MockBean`; trong Boot 3.4+ annotation ấy đã deprecated, nên với ví dụ Boot 3.5 ưu tiên `@MockitoBean`.

**Cảnh báo:** dùng `@MockitoBean` trong `@SpringBootTest` cũng có thể thay bean thật bằng mock. Vì thế đừng suy ra full context luôn thực hiện toàn bộ logic thật nếu chính test đã mock một khâu then chốt.

## 3. Slice giới hạn scanning và auto-configuration như thế nào?

Trong dự án tiêu chuẩn có `@SpringBootApplication` ở package gốc, Spring Boot tìm primary configuration từ package của test đi lên, rồi áp dụng cơ chế test bootstrap tương ứng.

### 3.1. Với `@WebMvcTest`

Spring Boot tập trung vào web MVC: `@Controller`, `@ControllerAdvice`, converter, `@JsonComponent`, `Filter`, `HandlerInterceptor`, `WebMvcConfigurer` và các loại cấu hình MVC được hỗ trợ. Nó cấu hình `MockMvc`, conversion/JSON và những MVC test support liên quan.

Các `@Service`, `@Repository` và `@Component` nghiệp vụ thông thường **không được scan theo mặc định**. Nếu controller có constructor dependency tới service, cần cung cấp mock/fake hoặc import bean thực một cách chủ động.

`@WebMvcTest(BookController.class)` còn **giới hạn controller trong phạm vi chỉ định**. Điều này giúp một test mapping không bị ảnh hưởng bởi mọi endpoint trong ứng dụng.

Nếu có `spring-boot-starter-security`, web slice có thể nạp security filters và trả 401/403 khi chưa có authentication/CSRF token. Đó là hành vi cần hiểu và kiểm tra; **đừng tắt filter tùy tiện** chỉ để test xanh. Dùng Spring Security test helpers như `@WithMockUser`/`csrf()` khi contract bảo mật có trong phạm vi. Dự án mẫu bên dưới không khai báo Spring Security.

### 3.2. Với `@DataJpaTest`

Slice JPA quét entity và Spring Data JPA repository, nạp ORM/JPA, DataSource, transaction support và test utilities. Nếu có embedded DB như H2 ở test classpath, Boot thường cấu hình database embedded thay cho DataSource thông thường. Các `@Service` nghiệp vụ, MVC controller và component chung không được scan như full context.

Mặc định `@DataJpaTest` là transactional và rollback sau mỗi test method. Đây là lợi thế khi kiểm tra persistence, **không phải** cam kết rằng mọi loại truy cập DB/async/transaction nằm trong transaction test.

Nếu `@AutoConfigureTestDatabase(replace = NONE)` được sử dụng, test có thể dùng DataSource đã cấu hình. Vì vậy phải bảo đảm URL/credentials là **database test**, không phải production. Nếu muốn kiểm tra dialect PostgreSQL thật, dùng Testcontainers hoặc database sandbox có kiểm soát thay vì dựa vào H2 khi SQL đặc thù.

### 3.3. Với `@JsonTest` và `@RestClientTest`

`@JsonTest` nạp mapper và các module/component JSON liên quan, không cần HTTP server hay database. Test DTO/serializer sẽ phát hiện lỗi định dạng mà không phải khởi động business context rộng.

`@RestClientTest(MyClient.class)` tập trung vào HTTP client hướng ra ngoài; Spring Boot cấu hình JSON support, `RestTemplateBuilder`, `RestClient.Builder` và `MockRestServiceServer`. Trong test, HTTP request được kiểm tra nội bộ, không mặc nhiên chạm API production. Nhưng nếu client tự tạo `new HttpClient` bỏ qua builder được test support cấu hình, mock server có thể **không** chặn được request đó; thiết kế client để inject dependencies.

### 3.4. Vì sao một số bean vẫn lọt vào slice?

Các quy tắc scan giới hạn **loại component**, nhưng cấu hình do người viết import, @Bean được khai báo trong configuration hoặc custom component scanning có thể thay đổi bean graph:

- `@Import(SomeConfiguration.class)`: chủ động đưa thêm configuration/bean vào slice.
- `@TestConfiguration`: thêm bean dành cho test.
- `@EnableConfigurationProperties`: nạp `@ConfigurationProperties` cần thiết cho slice.
- Custom `@ComponentScan` đặt trực tiếp ở main `@SpringBootApplication` có thể **vô hiệu hóa các exclude filters mặc định** mà slice sử dụng, khiến test vô tình scan nhiều bean hơn.
- `@Bean` do custom configuration tạo không nhất thiết chịu cùng filter với stereotype `@Component` scan; có thể dẫn đến cấu hình ngoài mong đợi.
- Conditional auto-configuration phụ thuộc classpath/profiles/properties và import chain; không nên đoán chỉ qua tên annotation.

Nếu slice đột nhiên cần database/email/Kafka bean, trước khi chuyển hết sang `@SpringBootTest` hãy kiểm tra chính xác **bean nào được import hoặc scan vào** và cấu hình chính đang được phát hiện thế nào.

## 4. Dự án mẫu Java 17 + Spring Boot 3.5 để so sánh trực tiếp

Ví dụ này là dự án **Maven có thể chạy** với ứng dụng quản lý danh mục sách in-memory. Nó không cần database bên ngoài, secret, Docker hay network bên ngoài khi chạy test (trừ bước Maven tải dependencies nếu cache chưa có).

Bốn loại test sử dụng cùng một mã nguồn:

1. MVC slice: `@WebMvcTest` + `@MockitoBean`.
2. Full application context: `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc`.
3. JSON slice: `@JsonTest` + `JacksonTester`.
4. Full context **và** HTTP server thật: `@SpringBootTest(RANDOM_PORT)`.

Nhờ đó có thể quan sát **mức độ nạp bean** và **HTTP transport** là hai khía cạnh riêng.

### 4.1. Cấu trúc tệp

```text
spring-test-context-compare/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/contextdemo/
    │       ├── ContextDemoApplication.java
    │       ├── Book.java
    │       ├── BookCatalog.java
    │       ├── BookService.java
    │       ├── BookMissingException.java
    │       └── BookController.java
    └── test/
        ├── java/com/example/contextdemo/
        │   ├── BookMvcSliceTest.java
        │   ├── BookFullContextTest.java
        │   ├── BookJsonSliceTest.java
        │   └── BookHttpServerTest.java
        └── resources/
            └── application-test.yml
```

Mỗi `public` type được đặt đúng tên file với `package com.example.contextdemo`. Không đặt nhiều `package` vào cùng một file. `BookCatalog` mang `@Repository` nhưng chỉ là dữ liệu in-memory, không cần JPA; phần JPA được trình bày riêng ở phần 8 để tránh làm project này vô tình nạp DB trong full-context test.

### 4.2. `pom.xml`

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
    <artifactId>spring-test-context-compare</artifactId>
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

`spring-boot-starter-web` cung cấp Spring MVC và Jackson, nên `@WebMvcTest`, `@JsonTest`, MockMvc và ObjectMapper có thể dùng. `spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito, AssertJ và Spring Boot test auto-configuration. Với Spring Boot parent, Maven Surefire/JUnit Platform và các dependency version tương thích được quản lý.

Đây là **một project**; không thêm `spring-boot-starter-data-jpa` vào project này trừ khi bạn chủ động mở rộng nó và cấu hình DataSource test.

### 4.3. Mã ứng dụng: controller → service → catalog

```java
// src/main/java/com/example/contextdemo/ContextDemoApplication.java
package com.example.contextdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextDemoApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/contextdemo/Book.java
package com.example.contextdemo;

public record Book(String code, String title, int copies) {}
```

```java
// src/main/java/com/example/contextdemo/BookCatalog.java
package com.example.contextdemo;

import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;

@Repository
public class BookCatalog {
    private final Map<String, Book> books = Map.of(
            "book-101", new Book("book-101", "Spring Testing", 7),
            "book-202", new Book("book-202", "Java 17", 4));

    public Optional<Book> findByCode(String code) {
        return Optional.ofNullable(books.get(code));
    }
}
```

```java
// src/main/java/com/example/contextdemo/BookMissingException.java
package com.example.contextdemo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class BookMissingException extends RuntimeException {
    public BookMissingException(String code) {
        super("Book not found: " + code);
    }
}
```

```java
// src/main/java/com/example/contextdemo/BookService.java
package com.example.contextdemo;

import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final BookCatalog catalog;

    public BookService(BookCatalog catalog) {
        this.catalog = catalog;
    }

    public Book findByCode(String code) {
        return catalog.findByCode(code)
                .orElseThrow(() -> new BookMissingException(code));
    }
}
```

```java
// src/main/java/com/example/contextdemo/BookController.java
package com.example.contextdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping("/{code}")
    public Book get(@PathVariable String code) {
        return service.findByCode(code);
    }
}
```

**Dữ liệu hợp đồng của ví dụ:**

| Request | Trường hợp | Kết quả kỳ vọng |
| --- | --- | --- |
| `GET /api/books/book-101` | Sách có trong catalog | 200; JSON có `code=book-101`, `title=Spring Testing`, `copies=7` |
| `GET /api/books/book-202` | Sách khác | 200; JSON có `title=Java 17` |
| `GET /api/books/missing` | Không tìm thấy | HTTP 404 nhờ `@ResponseStatus` |

Không có database hoặc API network bên ngoài. Điều này bảo đảm full context của project mẫu nạp các bean thật mà không cần secret/fixture production.

### 4.4. File cấu hình test

```yaml
# src/test/resources/application-test.yml
demo:
  safety-marker: isolated-test
```

Tất cả test context dưới đây dùng `@ActiveProfiles("test")`. Marker này chứng minh profile-specific test config được nạp; nó **không làm test trở thành slice** và không tự tạo mock. `@SpringBootTest` và slice đều có thể sử dụng active profiles/properties, chỉ khác nhau về các thành phần được bootstrap.

### 4.5. Test A: MVC slice không nạp repository thật

```java
// src/test/java/com/example/contextdemo/BookMvcSliceTest.java
package com.example.contextdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
@ActiveProfiles("test")
class BookMvcSliceTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Autowired
    Environment environment;

    @MockitoBean
    BookService service;

    @Test
    void controllerUsesStubResponseInsteadOfRealCatalog() throws Exception {
        when(service.findByCode("book-101"))
                .thenReturn(new Book("book-101", "From MVC Stub", 99));

        mvc.perform(get("/api/books/book-101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("book-101"))
                .andExpect(jsonPath("$.title").value("From MVC Stub"))
                .andExpect(jsonPath("$.copies").value(99));

        verify(service).findByCode("book-101");

        assertTrue(mockingDetails(service).isMock());
        assertTrue(context.getBeansOfType(BookCatalog.class).isEmpty());
        assertEquals("isolated-test",
                environment.getProperty("demo.safety-marker"));
    }

    @Test
    void mapsDomainNotFoundErrorTo404() throws Exception {
        when(service.findByCode("missing"))
                .thenThrow(new BookMissingException("missing"));

        mvc.perform(get("/api/books/missing"))
                .andExpect(status().isNotFound());
    }
}
```

**Ý nghĩa của test:**

- Controller, Spring MVC mapping, JSON serialization và `MockMvc` là thành phần test slice thật.
- `BookService` **là Mockito mock được cung cấp tường minh** bằng `@MockitoBean`. Nó trả `"From MVC Stub"` chứ không dùng dữ liệu catalog thật.
- `BookCatalog` vốn là `@Repository` nên **không nằm trong slice MVC mặc định**. Assertion trên bean graph xác nhận cụ thể điều này trong project mẫu.
- `@ActiveProfiles("test")` nạp cấu hình test; **nó không nạp thêm BookCatalog**.
- Kết quả 200 và JSON đúng cho biết controller nhận request và tạo response đúng **từ dữ liệu của mock service**. Test **không chứng minh** `BookService` thực tìm sách đúng hay gọi repository đúng.
- `BookMissingException` dùng `@ResponseStatus(NOT_FOUND)`, nên test có thể xác nhận Spring MVC xử lý loại exception đó thành status 404.

**Không được đặt mục tiêu “tìm sách thật bằng repository” cho chính test này**, vì repository không thuộc context đang test. Khi cần xác nhận controller + service + repository phối hợp, xem test B.

### 4.6. Test B: `@SpringBootTest` nạp bean service/repository thật

```java
// src/test/java/com/example/contextdemo/BookFullContextTest.java
package com.example.contextdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.mockingDetails;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class BookFullContextTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    BookService service;

    @Autowired
    BookCatalog catalog;

    @Autowired
    ApplicationContext context;

    @Test
    void findsRealCatalogDataThroughControllerAndService() throws Exception {
        assertFalse(mockingDetails(service).isMock());
        assertSame(catalog, context.getBean(BookCatalog.class));

        mvc.perform(get("/api/books/book-101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("book-101"))
                .andExpect(jsonPath("$.title").value("Spring Testing"))
                .andExpect(jsonPath("$.copies").value(7));
    }

    @Test
    void realServiceReturns404ForMissingBook() throws Exception {
        mvc.perform(get("/api/books/missing"))
                .andExpect(status().isNotFound());
    }
}
```

**Khác gì MVC slice?**

- `BookService` là `@Service` thật, được Spring tạo và inject `BookCatalog` thật.
- `BookCatalog` là `@Repository` thật trong ứng dụng mẫu, không bị Mockito stub.
- `MockMvc` vẫn được dùng nhờ `@AutoConfigureMockMvc`; request đi qua **mock servlet request/response**, không mở TCP listening port.
- Trường `title` của book-101 phải là `"Spring Testing"` từ catalog, khác với `"From MVC Stub"` do test slice tự quyết định.
- Hai test method bảo vệ sự phối hợp của controller, service, repository và MVC mapping trong một Spring context rộng.

**Điểm phân biệt quan trọng:** “Full context” ở đây là **full bean graph của ứng dụng** nhưng **không phải HTTP server thật**. Nếu cần kiểm tra cổng socket/HTTP client xem test D; hai trục này độc lập.

### 4.7. Test C: `@JsonTest` chỉ kiểm tra contract JSON

```java
// src/test/java/com/example/contextdemo/BookJsonSliceTest.java
package com.example.contextdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
@ActiveProfiles("test")
class BookJsonSliceTest {
    @Autowired
    JacksonTester<Book> json;

    @Autowired
    ApplicationContext context;

    @Test
    void serializesAndDeserializesBookWithoutBusinessServices()
            throws Exception {
        Book book = new Book("book-101", "Spring Testing", 7);

        assertThat(json.write(book))
                .extractingJsonPathStringValue("$.title")
                .isEqualTo("Spring Testing");

        assertThat(json.parseObject("""
                {"code":"book-101","title":"Spring Testing","copies":7}
                """)).isEqualTo(book);

        assertTrue(context.getBeansOfType(BookService.class).isEmpty());
    }
}
```

**Ý nghĩa:**

- `@JsonTest` tạo mapper/`JacksonTester` phù hợp mà không cần gọi controller hoặc service.
- Test kiểm tra record `Book` serialize/deserialize theo giá trị nghiệp vụ cần bảo vệ.
- Nó không chứng minh endpoint hoạt động và không cần embedded HTTP server.
- Một test JSON lỗi không nhất thiết là lỗi controller hoặc repository; tầng test hẹp giúp khoanh vùng nhanh.

Trong ứng dụng thực, nếu custom Jackson module là một phần contract, hãy đưa cấu hình JSON vào đúng phạm vi được `@JsonTest` quét hoặc `@Import` nó tường minh, thay vì ép dùng `@SpringBootTest` cho tất cả serializer tests.

### 4.8. Test D: full context cùng HTTP server thật

```java
// src/test/java/com/example/contextdemo/BookHttpServerTest.java
package com.example.contextdemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class BookHttpServerTest {
    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    @Test
    void realHttpConnectionReachesApplicationBeans() throws Exception {
        assertTrue(port > 0);

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/books/book-101");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Spring Testing",
                mapper.readTree(response.body())
                        .path("title").asText());
        assertEquals(7,
                mapper.readTree(response.body())
                        .path("copies").asInt());
    }
}
```

**Phân biệt ba tình huống quan trọng:**

- `BookMvcSliceTest`: MVC slice, service mock, không có catalog; MockMvc xử lý request trong process.
- `BookFullContextTest`: full context, service và catalog thật; MockMvc vẫn xử lý request nội bộ.
- `BookHttpServerTest`: full context và embedded HTTP server **thật** trên port ngẫu nhiên; Java `HttpClient` gọi qua socket loopback.

Mức độ “đầy đủ” của context **khác** với quyết định “có khởi động HTTP server thật không”. Cả `@WebMvcTest` và `@SpringBootTest(MOCK)` đều không khởi động embedded listener, nhưng bean graph của chúng khác nhau đáng kể.

### 4.9. Chạy và tự đối chiếu

Cần JDK 17+ và Maven; đặt cấu trúc trên đúng thư mục. Từ thư mục có `pom.xml`:

```bash
java -version
mvn -version

# Chạy tất cả test classes trong mẫu:
mvn test

# Chạy từng loại context riêng:
mvn -Dtest=BookMvcSliceTest test
mvn -Dtest=BookFullContextTest test
mvn -Dtest=BookJsonSliceTest test
mvn -Dtest=BookHttpServerTest test
```

**Kỳ vọng theo đúng mã mẫu:**

| Test class | Số `@Test` | Bean service/catalog thực? | Request qua network? | Oracle chính |
| --- | ---: | --- | --- | --- |
| `BookMvcSliceTest` | 2 | Không; service là mock, catalog vắng | Không | JSON từ stub, 404 mapping |
| `BookFullContextTest` | 2 | Có | Không, dùng MockMvc | JSON từ catalog thật, 404 |
| `BookJsonSliceTest` | 1 | Không | Không | JSON mapper round-trip |
| `BookHttpServerTest` | 1 | Có | Có, loopback HTTP | Status 200, JSON từ ứng dụng thật |

**Tổng là 6 test methods** trong bốn class nếu không có test khác: 2 + 2 + 1 + 1 = 6. Maven/Surefire có thể in thông tin test count, timing và logs khác nhau theo OS, cache, Java version và thứ tự chạy; **không có stdout cố định được bảo đảm**. Port của `RANDOM_PORT` là động, không được hard-code là 8080.

Nếu `BookMvcSliceTest` không start được vì một dependency bị thiếu sau khi bạn chỉnh sửa code, xem mục 6 thay vì chuyển ngay sang `@SpringBootTest`.

## 5. Slice và full context khác nhau ở ba tầng cấu hình

### 5.1. Component scanning

Full context dùng `@SpringBootApplication` ở package root để scan những stereotype components phù hợp: `@Controller`, `@Service`, `@Repository`, `@Component` và các configuration liên quan. Slice giới hạn loại bean được scan theo mục tiêu của annotation.

Trên project mẫu:

| Bean/đối tượng | MVC slice | JSON slice | Full context |
| --- | --- | --- | --- |
| `BookController` | Có | Không | Có |
| `BookService` | Có, **Mockito mock** do test khai báo | Không | Có, **bean thật** |
| `BookCatalog` | Không | Không | Có, **bean thật** |
| `MockMvc` | Có, được auto-configure | Không | Có khi thêm `@AutoConfigureMockMvc` |
| `JacksonTester<Book>` | Không được cấp cho test này theo mặc định | Có | Không được tự cấp như JSON slice |
| Jackson JSON conversion | Có | Có | Có, do web starter |
| Embedded HTTP listener | Không | Không | Không trong `MOCK`; có trong `RANDOM_PORT` |

Bảng trên nói về **project và test annotation cụ thể**. Không lấy bảng làm kết luận áp dụng cho mọi project có import hoặc custom configuration riêng.

### 5.2. Auto-configuration

Trong full context, Spring Boot xét những auto-configuration classes đủ điều kiện bởi `spring-boot-starter-*`, các bean đã có, feature flags và properties. Ví dụ khi thêm Data JPA, datasource và JPA auto-configuration có thể tham gia, kéo theo yêu cầu database.

Slice test **không kích hoạt toàn bộ auto-configuration theo kiểu ứng dụng đầy đủ**; nó import tập auto-configurations phục vụ lát kiểm thử. Tập này có thể thay đổi giữa các dòng Spring Boot, và danh sách chính thức nằm ở Appendix “Test Auto-configuration Annotations”.

Do vậy:

- Một bean type có trên classpath **không có nghĩa** nó luôn có trong slice.
- Một auto-configuration không được chọn có thể khiến dependency bạn mong đợi không được tạo.
- Nếu một test slice yêu cầu dependency custom, việc import thủ công là lựa chọn có chủ đích; đừng coi là mặc định của mọi test cùng annotation.
- Nếu cần kiểm tra nhiều tầng thực cùng nhau, dùng full context thay vì liên tục mở rộng slice tới mức ngang một ứng dụng đầy đủ.

### 5.3. Application properties và active profiles

`@ActiveProfiles("test")`, `@TestPropertySource`, `@SpringBootTest(properties = "...")` và `@DynamicPropertySource` điều chỉnh **giá trị cấu hình của test context**. Chúng **không trực tiếp quyết định một test là slice hay full**.

Ví dụ hai test cùng dùng `@ActiveProfiles("test")` nhưng bean graph khác nhau:

```java
@WebMvcTest(BookController.class)
@ActiveProfiles("test")
class MvcOnlyTest { /* ví dụ cú pháp, cần mock service */ }

@SpringBootTest
@ActiveProfiles("test")
class FullAppTest { /* ví dụ cú pháp, nạp ứng dụng rộng */ }
```

Hai class trên chỉ minh họa annotation, không phải test độc lập để chạy vì thiếu test methods và cấu hình collaborator. Profile giúp cùng đọc `application-test.yml`, nhưng **không thay thế lựa chọn bootstrapper của từng annotation**.

Khi debugging, nên ghi nhận **profiles đang active**, effective properties quan trọng và những bean thực được tạo trong từng context. Không suy đoán từ một YAML file rằng toàn bộ config được áp dụng nếu còn property sources ưu tiên cao hơn.

## 6. Lỗi khởi tạo slice: sửa đúng chỗ, không chuyển full context theo phản xạ

### 6.1. `NoSuchBeanDefinitionException` cho business service

Nếu controller inject `BookService` nhưng test chỉ có:

```java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mvc;
}
```

Spring không nhất thiết tạo `BookService` vì `@Service` nằm ngoài MVC slice. Khi dựng `BookController`, sẽ có lỗi thiếu bean.

**Cách sửa đúng khi chỉ test controller contract:**

```java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    BookService service;
}
```

Hai code blocks minh họa cấu hình, thiếu test methods. `@MockitoBean` cung cấp bean mock vào context. Test tiếp theo nên stub service theo input và assert status/JSON/validation; không khẳng định business logic của mock là đúng.

**Khi nào dùng `@Import(BookService.class)`?** Khi có lý do rõ ràng cần service thật trong một slice và mọi dependency cần thiết của service đều được cấp. Nhưng `BookService` của project mẫu cần `BookCatalog`; nếu import service thật mà không cấp catalog, lỗi thiếu bean chỉ chuyển sang lớp khác. Nếu mục tiêu là kiểm tra cả controller-service-catalog thật, **`@SpringBootTest` hợp lý hơn**.

### 6.2. Slice vô tình tải JPA hoặc Kafka

Một số nguyên nhân:

- Bạn đặt `@ComponentScan` thủ công trên main `@SpringBootApplication`, làm mất exclude filters mặc định của test slice.
- Một `@Configuration` được import tự tạo datasource, Kafka listener hoặc REST client.
- Một `@Bean` factory dùng trực tiếp URL production ngay khi context startup.
- Có custom annotation/meta-annotation hoặc `@ImportAutoConfiguration` đưa thêm auto-configuration.
- Tên class/package primary configuration khiến Spring Boot tìm được một configuration không dự kiến.

**Khắc phục:** xem cấu hình primary và chuỗi import, tách configuration theo lĩnh vực và chỉ import đúng phần slice cần. **Không** dùng `@SpringBootTest` để chữa việc slice quá rộng; full context có thể mở rộng rủi ro hơn.

### 6.3. Đã mock service nhưng test vẫn kiểm tra business calculation

Một lỗi khái niệm:

```java
when(service.findByCode("book-101"))
        .thenReturn(new Book("book-101", "Spring Testing", 7));

mvc.perform(get("/api/books/book-101"))
        .andExpect(jsonPath("$.copies").value(7));
```

Test này chứng minh **controller render dữ liệu do stub trả lại**. Nếu bên trong `BookService` thật tính sai stock, test vẫn pass vì service không được gọi.

Muốn test logic inventory: unit test `BookService` với fake catalog, hoặc full-context test sử dụng bean thật. **Đừng đánh giá chất lượng một test bằng số annotation nó có; hãy xác nhận đường code được thực thi.**

### 6.4. `@SpringBootTest` thất bại vì thiếu secret/DB

Nếu full context nạp production HTTP client, DataSource hoặc listener ngoài, test có thể fail vì môi trường hoặc tệ hơn chạm production.

- Chọn profile `test` thực sự và tài nguyên test-only.
- Mock/fake các outbound boundaries không thuộc mục tiêu đang kiểm tra.
- Với JPA dùng H2/ephemeral Postgres container, không dùng database production.
- Không đặt secret thật trong source/test resources.
- Không suy luận “MOCK web environment” là mọi outbound client đã bị mock.
- Nếu chỉ cần kiểm tra JSON hoặc controller mapping, quay về slice thích hợp thay vì dựng toàn bộ context.

### 6.5. Test chậm hơn mong đợi

Full context thường có nhiều auto-config, bean, migrations, connection pools, schedulers và remote clients. Nhưng slice cũng có thể nặng khi cấu hình scan/import sai hoặc tạo nhiều context khác nhau do mỗi test có properties/mocks riêng.

Spring TestContext **cache context** theo cấu hình phù hợp; dùng quá nhiều biến thể `@MockitoBean`, `@ActiveProfiles`, `@TestPropertySource` hoặc `@DirtiesContext` có thể giảm khả năng tái sử dụng. Tối ưu bằng cách nhóm test theo mục tiêu/cấu hình hợp lý và đo thời gian thực, không chỉ dựa vào nhãn “slice”.

## 7. Mở rộng slice đúng cách

### 7.1. `@MockitoBean` cho dependency ở ranh giới

Với controller mà service là collaborator, cách dùng này phù hợp vì controller test chỉ cần quyết định service trả gì:

```java
@MockitoBean
BookService service;
```

Ngược lại, nếu mục tiêu là xác nhận business service thật thì mock nó làm mất đường code đang cần kiểm tra. Chọn bean mock/fake **dựa trên boundary của test**, không dựa vào việc “có thể mock được”.

### 7.2. `@Import` cho một bean/config thật nhỏ

Khi controller phụ thuộc một custom `Converter` hoặc `Module` mà slice không tự scan, có thể:

```java
@WebMvcTest(BookController.class)
@Import(BookMvcExtrasConfiguration.class)
class BookControllerWithExtrasTest {
    // Ví dụ: cấu hình thêm converter cần thiết.
}
```

Đây là ví dụ annotation, `BookMvcExtrasConfiguration` giả định đã được định nghĩa, không thuộc runnable project phần 4. Chỉ import cấu hình **nhỏ và không có side effect bên ngoài**. Nếu import một `@Configuration` tạo datasource, broker và scheduler thì đã phá sự cô lập của slice.

### 7.3. `@TestConfiguration` thêm bean test-only

Trong test, có thể định nghĩa cấu hình hỗ trợ:

```java
@TestConfiguration(proxyBeanMethods = false)
class FixedClockConfiguration {
    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2030-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
```

Đây là **mẫu code minh họa**, cần imports `Clock`, `Instant`, `ZoneOffset`, `@TestConfiguration` và `@Bean`; không thuộc project phần 4. Sau đó test có thể `@Import(FixedClockConfiguration.class)` để cung cấp thời gian xác định. Top-level `@TestConfiguration` nên được import tường minh vào test cần dùng; tránh để fake cấu hình trở thành bean production.

**Phân biệt:** nested `@TestConfiguration` bổ sung primary app configuration; nested `@Configuration` có thể thay đổi cách Spring tìm primary configuration trong test. Với slice và full context, ưu tiên `@TestConfiguration` hoặc `@Import` có mục đích rõ.

### 7.4. `@EnableConfigurationProperties` cho config bean bị loại khỏi slice

Một class `@ConfigurationProperties(prefix="app.api")` bình thường có thể không được tự scan trong `@WebMvcTest`. Nếu controller/converter đang test thật sự cần nó, thêm `@EnableConfigurationProperties(ApiProperties.class)` trong test hoặc dùng một test configuration nhỏ.

Đây là cơ chế **bổ sung** bean properties có chủ ý, không phải lý do chuyển cả project sang `@SpringBootTest`. Luôn dùng giá trị thử nghiệm, không lôi URL/token production vào MVC slice.

### 7.5. `excludeAutoConfiguration` không phải “tắt cả Spring”

Một số `@*Test` có attribute `excludeAutoConfiguration` để loại auto-configuration cụ thể. Hữu ích khi loại một thành phần làm test lệch mục tiêu, nhưng nên phân tích tại sao component đó xuất hiện. Không lạm dụng một danh sách loại trừ lớn đến mức test không còn đại diện cho MVC/JPA contract mong muốn.

## 8. Ví dụ riêng cho `@DataJpaTest`: khác MVC slice và full context

Trong project mẫu phần 4, `BookCatalog` chỉ là một class in-memory gắn `@Repository`, **không phải Spring Data JPA repository**. Để kiểm tra `@DataJpaTest`, cần một **dự án JPA khác** (hoặc mở rộng project và cập nhật các test full context tương ứng). Không sao chép những snippet JPA dưới đây vào project phần 4 rồi kỳ vọng các full-context tests vẫn không cần DataSource.

### 8.1. Dependencies của một project JPA test

Trong Maven project Boot 3.5 đã cấu hình Java 17, bổ sung:

```xml
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
```

Đây là **đoạn dependencies cần thêm**, không phải toàn bộ `pom.xml`; tránh khai báo `spring-boot-starter-test` trùng nếu nó đã tồn tại.

### 8.2. Entity/repository mẫu của dự án JPA riêng

```java
// src/main/java/com/example/jpaslice/StoredBook.java
package com.example.jpaslice;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class StoredBook {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String code;

    protected StoredBook() {}

    public StoredBook(String code) {
        this.code = code;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
}
```

```java
// src/main/java/com/example/jpaslice/StoredBookRepository.java
package com.example.jpaslice;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface StoredBookRepository
        extends JpaRepository<StoredBook, Long> {
    Optional<StoredBook> findByCode(String code);
}
```

Trong project JPA riêng cần một `@SpringBootApplication` đặt ở `com.example.jpaslice` hoặc package cha cho cấu hình được tìm thấy. Với PostgreSQL thật, còn cần driver/migration và cấu hình riêng; ví dụ này dùng H2 in-memory từ test dependency.

### 8.3. Repository slice test

```java
// src/test/java/com/example/jpaslice/StoredBookRepositoryTest.java
package com.example.jpaslice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest
class StoredBookRepositoryTest {
    @Autowired
    TestEntityManager entityManager;

    @Autowired
    StoredBookRepository repository;

    @Test
    void persistsAndQueriesBookCode() {
        entityManager.persistAndFlush(new StoredBook("book-101"));
        entityManager.clear();

        StoredBook actual = repository
                .findByCode("book-101")
                .orElseThrow();

        assertEquals("book-101", actual.getCode());
    }
}
```

Trong cấu hình test đúng, `@DataJpaTest` nạp entity, repository, JPA và database test (H2 nếu có/cấu hình phù hợp). Nó không cần MVC controller hay business service.

**Điều test chứng minh:** entity mapping + query `findByCode` chạy trên DB thử nghiệm. **Điều test không chứng minh:** HTTP controller, business workflow qua nhiều service, hay sự tương thích tuyệt đối của H2 với PostgreSQL-specific SQL.

Mặc định JPA slice có transaction rollback sau mỗi test method. Nếu test tạo async worker/transaction khác, rollback của test thread không tự bao trùm các thao tác ấy.

### 8.4. Khi cần database thật nhưng vẫn chỉ test repository

Có thể dùng `@DataJpaTest` + `@AutoConfigureTestDatabase(replace = NONE)` để không tự thay DataSource theo mặc định, rồi cấp connection details từ Testcontainers hoặc sandbox test. **Đây vẫn là JPA slice**, vì test slice chủ yếu nói về bean graph, không phải liệu database là H2 hay PostgreSQL.

Ví dụ cấu hình annotation (không phải test đầy đủ):

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlRepositorySliceTest {
    // Cần cấu hình PostgreSQL test-only hoặc @ServiceConnection.
}
```

Đoạn này cần imports và một datasource test thật trước khi có thể chạy. Nếu `replace=NONE` mà cấu hình trỏ production thì test sẽ chạm production. Không sử dụng URL/credentials production để “cho test chạy”.

Nếu muốn **full bean graph** nhưng thay database, có thể kết hợp `@SpringBootTest` với `@AutoConfigureTestDatabase` hoặc Testcontainers cấu hình phù hợp. **Thay DataSource không biến full context thành `@DataJpaTest`.**

## 9. Quy tắc chọn slice hay full context

Hãy đặt câu hỏi: **“Lỗi nào cần phát hiện và bộ phận nào phải chạy thật?”**

| Tình huống cần kiểm tra | Chọn | Vì sao |
| --- | --- | --- |
| Controller nhận path/query/body và trả JSON/status đúng với service result | `@WebMvcTest` + `@MockitoBean` | Tập trung vào MVC contract |
| Jackson serialize enum/date/custom field đúng | `@JsonTest` | Không cần controller và database |
| Repository query và entity mapping đúng trên DB test | `@DataJpaTest` | Tập trung DataSource/JPA/transaction |
| SQL bằng `JdbcTemplate` | `@JdbcTest` | Không kéo toàn bộ business context |
| Outbound REST client dựng URL/header/body đúng | `@RestClientTest(Client.class)` | Fake HTTP response, test mapping |
| Business service tính tiền đúng | JUnit + Mockito/fake, không Spring nếu có thể | Phản hồi nhanh, ranh giới nhỏ |
| Controller → service → repository thật phối hợp | `@SpringBootTest` (+ MockMvc nếu MVC) | Nhiều tầng thực trong một context |
| Request qua embedded HTTP server thực | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Kiểm tra port/transport/container |
| Nhiều service ngoài, broker, DB, HTTP cùng phối hợp | Full integration + containers/stubs/staging | Slice không đại diện liên kết toàn hệ |
| Chỉ cần xác nhận một bean/condition của app được nạp | `@SpringBootTest(NONE)` hoặc test context tối thiểu | Không cần web server |

**Cách ra quyết định:** ưu tiên test nhỏ nhất có thể **thật sự phát hiện lỗi cần bảo vệ**. Không chọn slice chỉ vì mong test nhanh; nếu hợp đồng nằm ở nhiều tầng, slice với mock service sẽ bỏ qua lỗi wiring/transaction. Không chọn full context chỉ vì annotation có vẻ “chắc ăn”; việc nạp thêm bean không thuộc mục tiêu tạo chi phí và rủi ro.

### 9.1. Khi cần nhiều “slices” trong cùng một test?

Spring Boot không hỗ trợ đơn giản việc xếp hai annotation như `@WebMvcTest` và `@DataJpaTest` lên cùng một class: chúng có các bootstrap configurations khác nhau, có thể dẫn tới lỗi bootstrap. Nếu cần MVC + JPA thật trong một test, thường chọn `@SpringBootTest` và thêm các test auto-configuration utilities phù hợp.

Có thể kết hợp một slice với các `@AutoConfigure...` bổ sung bằng tay trong trường hợp có lý do rõ ràng, nhưng **không** xem việc ghép nhiều `@*Test` là cách tạo “slice lớn”. Khi test mô tả cả workflow, full context dễ hiểu và phản ánh contract hơn.

### 9.2. Một hệ thống có nên có cả slice và full tests?

Nên. Ví dụ:

- Nhiều MVC slice tests: kiểm tra nhanh routing/validation/error JSON cho từng controller.
- JPA slice tests: kiểm tra query/mapping/constraints với database test.
- Unit tests: kiểm tra quy tắc giá/authorization/domain.
- Ít full-context integration tests: kiểm tra các luồng nối controller-service-repository, active profiles, security wiring và transaction.
- Một số HTTP real server tests: kiểm tra transport/serialization ở boundary có rủi ro.

Slice và full không thay thế nhau hoàn toàn. **Giá trị của một tầng nằm ở lỗi đặc thù nó phát hiện**, không phải số lượng file test.

## 10. Các hiểu lầm thường gặp

### 10.1. “`@WebMvcTest` cũng có `ApplicationContext`, vậy nó như `@SpringBootTest`”

Sai. Cả hai dùng Spring TestContext nhưng bean graph và auto-configuration được nạp khác nhau. `BookMvcSliceTest` cố ý không có `BookCatalog` trong khi `BookFullContextTest` có nó.

### 10.2. “Đặt `@Mock` là Spring tự inject vào controller”

Không. `@Mock` tạo Mockito object trong test scope. Để đưa vào Spring context Boot 3.5 dùng `@MockitoBean`. Không có Spring bean thay thế, controller constructor có thể báo thiếu service.

### 10.3. “`@WebMvcTest` kiểm tra service business thật”

Không theo mặc định. Service nghiệp vụ không thuộc MVC slice; nếu dùng `@MockitoBean` thì logic service là stub. Cần unit test service hoặc full context test cho business flow.

### 10.4. “`@SpringBootTest` luôn mở server port”

Sai. Mặc định là `MOCK`: full Spring bean context nhưng không có embedded HTTP listener. Muốn HTTP thật dùng `RANDOM_PORT` hoặc `DEFINED_PORT`.

### 10.5. “`@DataJpaTest` không thể chạm database thật”

Sai. Nếu có `@AutoConfigureTestDatabase(replace=NONE)` hoặc cấu hình DataSource đặc thù, test có thể dùng DB thực. Luôn cấp test-only credentials/network.

### 10.6. “Dùng `@Import` mọi thiếu bean cho đến khi slice chạy”

Cách này có thể làm slice phình thành một full context ngầm, chậm và nguy hiểm. Nếu cần kiểm tra nhiều thành phần thật, chủ động chuyển sang `@SpringBootTest` với phụ thuộc ngoài được cô lập.

### 10.7. “Thêm `@ActiveProfiles("test")` là test trở thành slice”

Sai. Profile ảnh hưởng properties/conditional beans, không thay thế `@WebMvcTest`/`@DataJpaTest` hay `@SpringBootTest`. Hai test dùng cùng profile vẫn có bean graph khác nhau.

### 10.8. “Chỉ cần test MVC slice pass thì endpoint chắc chắn chạy ở production”

Không. Slice với service mock không phát hiện service/repository wiring thật, production properties, database schema hoặc HTTP ingress/proxy. Cần tầng integration/E2E tương ứng.

### 10.9. “Có Spring Security thì bỏ toàn bộ filter để test controller cho nhanh”

Không nên mặc định. Nếu security là contract, test phải xử lý authentication/authorization/CSRF đúng. Chỉ tắt filters nếu test cố ý tách validation/handler logic khỏi security và có test security độc lập bao phủ.

### 10.10. “Nếu full context quá chậm thì chuyển hết sang slice”

Phương án này có thể bỏ mất lỗi tích hợp xuyên tầng. Giữ một tập integration tests có mục tiêu, tối ưu context caching và external dependencies, rồi dùng slice cho những test thực sự chỉ cần tầng riêng lẻ.

## 11. Checklist trước khi merge test

- [ ] Đề bài test có xác định ranh giới: controller, JSON, JPA, service hay full workflow?
- [ ] Đã chọn annotation test đúng ranh giới: `@WebMvcTest`/`@DataJpaTest`/`@JsonTest`/`@RestClientTest` hoặc `@SpringBootTest`?
- [ ] Hiểu bean nào thật, bean nào mock và bean nào hoàn toàn không tồn tại trong context.
- [ ] Nếu controller thiếu service ở slice, dùng `@MockitoBean`/`@Import` một cách có mục tiêu.
- [ ] Không dùng `@Mock` như thể nó đã được Spring đăng ký làm bean.
- [ ] Không dùng mock của chính thành phần đang muốn chứng minh logic thật.
- [ ] Không xếp nhiều `@*Test` slice annotation không tương thích trên cùng một class.
- [ ] Không đặt custom `@ComponentScan` làm mất exclude filters của slice mà không hiểu hệ quả.
- [ ] Các properties/profiles test-only được áp dụng, không đụng DB/API production.
- [ ] Với `@DataJpaTest`, biết database đang dùng và phạm vi transaction rollback.
- [ ] Với `@SpringBootTest`, phân biệt full bean graph và real HTTP listener.
- [ ] Nếu dùng `@AutoConfigureMockMvc`, hiểu nó không tự mở TCP socket.
- [ ] Nếu dùng `@DirtiesContext`, có lý do thật và chấp nhận chi phí cache.
- [ ] Assertion đo đúng rủi ro ở tầng được chọn và có case lỗi quan trọng.

## 12. Tự kiểm tra

**Câu 1.** Controller inject `OrderService`, `@WebMvcTest(OrderController.class)` báo thiếu bean. Làm gì khi chỉ muốn kiểm tra mapping/JSON?

**Đáp án:** Thêm `@MockitoBean OrderService` để cấp collaborator giả, stub kết quả theo case. Không cần nạp repository/database thật.

**Câu 2.** Vì sao `@SpringBootTest` có thể kiểm tra controller + service + repository thật mà `@WebMvcTest` với mocked service không làm được?

**Đáp án:** Full context scan/cấu hình nhiều tầng bean đủ điều kiện. MVC slice cố ý giới hạn bean graph; service mock không thực thi business logic hoặc repository.

**Câu 3.** Hai test cùng có `@ActiveProfiles("test")`; chúng có bean graph giống nhau không?

**Đáp án:** Không nhất thiết. Profile chỉ tác động conditional config và properties. `@WebMvcTest` và `@SpringBootTest` vẫn dùng bootstrapper và selected auto-configurations khác nhau.

**Câu 4.** Dùng `@JsonTest` để kiểm tra field serialized của record có đủ bảo đảm endpoint trả 200 không?

**Đáp án:** Không. Nó bảo vệ JSON mapping, không gọi controller hoặc HTTP server. Dùng MVC/full-context HTTP test cho endpoint contract.

**Câu 5.** `@DataJpaTest` rollback có tự bảo đảm dữ liệu không chạm production không?

**Đáp án:** Không. Trước hết phải đảm bảo DataSource là test-only. Rollback không thay cho kiểm soát quyền, network, DDL hoặc các thao tác ở transaction khác.

**Câu 6.** `@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc` có phải full context không, và có listener không?

**Đáp án:** Có full application bean context theo config hiện hành, nhưng MockMvc xử lý request nội bộ và không khởi động embedded HTTP listener. Muốn listener thật dùng `RANDOM_PORT`/`DEFINED_PORT`.

**Câu 7.** Một test slice có thể bất ngờ nạp nhiều bean business vì sao?

**Đáp án:** Custom `@ComponentScan`, `@Import`, `@Bean` configuration hoặc auto-configuration bổ sung đã làm thay đổi selected beans/scan filters. Cần điều tra cấu hình trước khi bỏ annotation slice.

**Câu 8.** Khi cần test truy vấn PostgreSQL có SQL đặc thù, nên dùng gì?

**Đáp án:** Có thể giữ `@DataJpaTest` nhưng cấp PostgreSQL Testcontainers/test-only database và không cho thay bằng H2; cấu hình connection details từ container, không dùng production DB. Full context chỉ cần khi mục tiêu còn bao gồm business wiring ngoài repository.

## 13. Tài liệu tham khảo

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, các test slices, MVC/JSON/JPA tests và cấu hình chọn lọc.
- [Spring Boot 3.5 – Test Auto-configuration Annotations](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): các auto-configurations mà từng slice cung cấp.
- [Spring Boot 3.5 – Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): cách tổ chức `@Configuration`, custom scanning và slice tests.
- [Spring Framework 6.2 – `@MockitoBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): override/replace beans trong TestContext.
- [Spring Framework – Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): tái sử dụng test application contexts.
- [Spring Boot 3.5 – `@DataJpaTest` API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): scanning, transactions và embedded database.

**Tóm lại:** **Test slice nạp đủ bean và auto-configuration cho một lát chức năng; `@SpringBootTest` nạp context ứng dụng rộng theo điều kiện cấu hình.** Hãy kiểm tra **bean nào thật, bean nào mock, bean nào không có**, đồng thời phân biệt phạm vi context với việc có/không HTTP server. Sử dụng tầng test nhỏ nhất nhưng vẫn chứng minh được hợp đồng cần bảo vệ.