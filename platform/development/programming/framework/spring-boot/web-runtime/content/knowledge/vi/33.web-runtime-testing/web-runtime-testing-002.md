# @WebMvcTest, MockMvc và phạm vi kiểm thử MVC trong Spring Boot

**Ngữ cảnh:** Spring Boot → web-runtime → **Kiểm thử web runtime**. Bài học giải thích bản chất **MVC test slice** của `@WebMvcTest`, cách `MockMvc` giả lập request/response ở tầng Spring MVC, những bean và auto-configurations thực sự được nạp, cách cô lập service bằng `@MockitoBean`, test JSON/validation/controller advice/security/CSRF, khi nào cần `@SpringBootTest + @AutoConfigureMockMvc` hoặc `@SpringBootTest(RANDOM_PORT)`, các giới hạn về Servlet container và checklist để tránh false-positive.

**Môi trường:** Java 17+, Maven, Spring Boot **3.5.16** (Spring Framework 6.2.x), JUnit Jupiter 5, Mockito, Spring MVC, Spring Security 6.5.x. Ví dụ là một Maven project có đủ các file để chạy, gồm controller/service/DTO/exception/security và ba loại tests. Bản 3.5.16 thuộc dòng đã kết thúc hỗ trợ OSS (giữa năm 2026): production chọn phiên bản/bản vá còn được hỗ trợ. Chỉ dùng API và tên package tương thích với Boot 3.5; không trộn với package/module mới của Boot 4.x.

> **Thông điệp chính:** `@WebMvcTest` **không** phải full application test cũng **không** phải unit test thuần Java. Nó khởi tạo **Spring Test ApplicationContext chỉ chứa MVC slice**, gắn hạ tầng MVC thật cho các controller được chọn và thường dùng **mock cho collaborator/service**. `MockMvc` chạy Spring MVC processing trong JVM bằng mock Servlet objects, **không mở HTTP port hay chạy embedded Tomcat thật**. Một suite tốt thường kết hợp test slice nhanh với một số bài full-context và HTTP-server integration tests cho những rủi ro mà mock environment không tái tạo.

## 1. Kiểm thử MVC nằm ở đâu trong hệ thống web runtime?

Một request Servlet MVC thường đi theo đường:

~~~text
Browser / HTTP client
        │
        ▼
TCP/TLS, reverse proxy, load balancer
        │
        ▼
Embedded Tomcat/Jetty/Undertow: socket + Servlet container
        │
        ├── Servlet Filters (SecurityFilterChain, tracing, custom)
        │
        ▼
DispatcherServlet
        ├── HandlerMapping / @GetMapping / @PostMapping
        ├── HandlerInterceptor
        ├── HandlerMethodArgumentResolver
        ├── HttpMessageConverter (JSON <-> Java)
        ├── Bean Validation (@Valid)
        ├── Controller method
        ├── @ControllerAdvice / @ExceptionHandler
        └── HandlerAdapter / response rendering
        │
        ▼
Spring service → database/external API
~~~

Không phải test nào cũng cần toàn bộ pipeline. Mục tiêu `@WebMvcTest` là kiểm tra **hợp đồng HTTP của lớp MVC**: URL/method, query/path variables, body serialization/deserialization, status, headers, content type, input validation, exception mapping và các filters/security được đưa vào slice.

Với `MockMvc`, Spring Test tạo `MockHttpServletRequest` và `MockHttpServletResponse` rồi đưa request qua `DispatcherServlet`/MVC infrastructure; không có real TCP socket. Vì vậy có thể kiểm tra **controller routing/JSON/security filters** mà không boot container, nhưng không thể chứng minh **Tomcat connector/TLS/HTTP2/proxy rewrites** hoạt động đúng.

### 1.1. So sánh bốn tầng kiểm thử

| Kiểu test | Context/HTTP runtime | Collaborators | Thứ kiểm tra tốt |
| --- | --- | --- | --- |
| **Unit test controller thuần Java** | Không Spring context, gọi method trực tiếp | Mockito/in-memory object | Nhánh logic trong controller, không chứng minh mapping/JSON |
| **`@WebMvcTest` + `MockMvc`** | **Web MVC slice context**, Servlet mocks, không server thật | `@MockitoBean` service/repository; một số MVC/filter components thực | Routing, JSON, validation, controller advice, mock security policy |
| **`@SpringBootTest` + `@AutoConfigureMockMvc`** | **Full application context** nhưng mock HTTP, không mở port theo `webEnvironment=MOCK` mặc định | Services/repositories thật trừ khi override | Phối hợp MVC với application beans/filters, không kiểm tra socket |
| **`@SpringBootTest(webEnvironment=RANDOM_PORT)`** | **Full context + embedded server thật** trên port ngẫu nhiên | Services, DB/stubs theo test setup | Servlet registrations, headers/network behavior, container error dispatch, end-to-end HTTP |

Không có thứ tự cứng “test loại cuối luôn tốt hơn”: full tests có cost và độ phức tạp lớn hơn; unit/slice tests cung cấp feedback nhanh và kiểm tra chi tiết chính xác hơn. Kết hợp theo rủi ro.

### 1.2. Test MVC hợp đồng HTTP khác test nghiệp vụ

Ví dụ controller:

~~~java
@GetMapping("/api/books/{id}")
public BookView find(@PathVariable long id) {
    return bookService.find(id);
}
~~~

Những điều test MVC nên bảo đảm:
- `GET /api/books/7` match đúng handler;
- `id` được convert thành `long` (input không hợp lệ có thể 400);
- trả 200 và JSON field `id`, `title`;
- khi service báo không tìm thấy, `@RestControllerAdvice` biến thành 404 hợp đồng chuẩn;
- quyền truy cập/rule được áp như dự kiến.

Những điều test MVC slice **không** chứng minh:
- câu SQL đúng, transaction commit, unique constraints hoặc HikariCP hoạt động;
- service thật xử lý đơn hàng chính xác;
- HTTP reverse proxy viết lại `/api` đúng;
- Servlet container tự đăng ký một `Filter`/`Servlet` hay không;
- production token issuer, OAuth2 discovery, mTLS hoặc CORS tại gateway đúng.

**Test cái bạn thực sự chạy.** Nếu test chỉ gọi trực tiếp `controller.find(7)`, bạn chưa kiểm tra Spring MVC routing. Nếu test `MockMvc` nhưng toàn bộ service là mock, bạn chưa kiểm tra business/database logic.

## 2. `@WebMvcTest` làm gì trong Spring Boot 3.5?

Annotation từ `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest` là **test slice** có Spring TestContext integration. Nó tập trung scan MVC-related components, chọn một hay một nhóm controllers và nạp tập auto-configurations cần cho MVC; `@WebMvcTest` còn **auto-configure `MockMvc`** nên có thể `@Autowired MockMvc` mà không tự tạo builder.

Một ví dụ:

~~~java
@WebMvcTest(controllers = BookController.class)
class BookControllerWebMvcTest {
    @Autowired MockMvc mvc;
    @MockitoBean BookService bookService;
}
~~~

Khái niệm ở đây: `BookController` là controller thật của app, còn `BookService` được tạo/thay bằng Mockito mock để không chạm database hoặc network.

### 2.1. Những thành phần được scan/nạp có chọn lọc

Theo reference Spring Boot 3.5, `@WebMvcTest` hạn chế component scan chủ yếu vào:
- `@Controller`/`@RestController`;
- `@ControllerAdvice`/`@RestControllerAdvice`;
- `@JsonComponent`;
- `Converter`, `GenericConverter`;
- `Filter` (tùy cấu hình và filter registration trong slice);
- `HandlerInterceptor`;
- `WebMvcConfigurer`, `WebMvcRegistrations`;
- `HandlerMethodArgumentResolver`;
- một số cấu hình Security liên quan, nếu security trên classpath.

Nó có các MVC-related auto-configurations như Jackson/HTTP converters, validation, MVC error infrastructure, template integrations theo dependencies và Spring Security support; **không** có nghĩa toàn bộ app auto-config đều chạy.

Những bean thông thường **không tự được scan** trong slice:
- `@Service`, `@Repository` và business-domain `@Component` thông thường;
- JPA repositories, EntityManager và DataSource nếu không được thêm bằng cấu hình khác;
- scheduler/consumers/HTTP clients ngoại vi không thuộc web slice;
- một cấu hình `@ConfigurationProperties` bất kỳ (có thể chủ động nạp bằng `@EnableConfigurationProperties`).

Bởi vậy constructor injection của controller sẽ fail nếu service collaborator không có bean; cách đúng là **cấp mock qua `@MockitoBean`**, hoặc import một test bean/config phù hợp. **Không** mở rộng slice bằng cách import `@SpringBootApplication` hay cả component scan chỉ để test hết lỗi dependency: như vậy đánh mất isolation.

### 2.2. Giới hạn scan không phải whitelist của cả ApplicationContext

Đừng diễn giải “chỉ scan Controller” thành “context chỉ có 1 bean Controller”. Spring Boot có thể tạo các MVC infrastructure, JSON converters, validator, Security, request mapping và related helper beans. Một component được include qua **`@Import`**, auto-configuration hoặc @Bean explicit có thể xuất hiện dù không nằm trong danh sách scan mặc định.

**Cẩn thận với `@SpringBootApplication` và `@ComponentScan` tự viết.** Nếu application main gắn custom `@ComponentScan` không dùng Boot `TypeExcludeFilter`, slice test có thể vô tình scan toàn ứng dụng. Tốt hơn để main class `@SpringBootApplication` đơn giản, tách domain configuration ra cấu hình riêng và chỉ import cái slice cần.

### 2.3. Chọn controller rõ ràng

~~~java
@WebMvcTest(BookController.class)
~~~

Tập trung vào controller đích và giảm context size. Không khai báo:

~~~java
@WebMvcTest
~~~

khi bạn chỉ muốn một controller nhưng project có hàng trăm controllers; annotation không chỉ định controller có thể tìm nhiều MVC components hơn dự định, tăng mocks cần thiết và làm test brittle.

Cũng không dùng `@WebMvcTest` và `@DataJpaTest` cùng lúc để “có cả web và DB”. Spring Boot docs không hỗ trợ trộn nhiều slice annotations kiểu này. Nếu cần kiểm tra cả controller và persistence, dùng `@SpringBootTest` với database/testcontainers thích hợp.

## 3. MockMvc kiểm tra request/response như thế nào?

`MockMvc` từ `org.springframework.test.web.servlet.MockMvc` có API:

~~~java
mvc.perform(get("/api/books/7")
        .accept(MediaType.APPLICATION_JSON))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.id").value(7))
   .andExpect(jsonPath("$.title").value("Clean Tests"));
~~~

Diễn giải:
1. `perform(...)` tạo và thực hiện request được mô phỏng bằng Servlet API mock, qua Spring MVC.
2. `get("/api/books/7")` kiểm tra mapping và method, không cần socket.
3. `accept(MediaType.APPLICATION_JSON)` kiểm tra negotiated representation; đây là header **Accept**, khác `Content-Type` của request body.
4. `status().isOk()` assert HTTP status 200.
5. `jsonPath` assert nội dung JSON theo selector `$.id`/`$.title`, ít phụ thuộc field order/JSON whitespace.

Các nhóm assertions hữu ích:

| Matcher | Kiểm tra |
| --- | --- |
| `status().isCreated()` | HTTP 201 |
| `header().string("Location", "/api/books/8")` | Header redirect/resource URI |
| `content().contentTypeCompatibleWith(APPLICATION_JSON)` | Content-Type đúng semantics (có thể có charset parameter) |
| `jsonPath("$.title").value("...")` | JSON response field/value |
| `content().json(...)` | JSON semantic comparison; không cần raw whitespace |
| `content().string(...)` | Response text exact, phù hợp plain text |
| `redirectedUrl(...)` | Redirect target |
| `view().name(...)` | Logical Spring MVC view name |
| `model().attributeExists(...)` | Model attribute cho HTML MVC |
| `handler().handlerType(...)` | Controller class được map |
| `handler().methodName(...)` | Handler method |
| `request().asyncStarted()` | MVC async request bắt đầu |
| `cookie().exists(...)` | Response cookie |
| `forwardedUrl(...)` | Forwarded target trong mock response |

**Không kiểm tra mọi implementation detail.** Test hợp đồng API nên tập trung status, headers, body và lời gọi service quan trọng; test tên private method hay số lần gọi converter thường brittle.

### 3.1. Accept khác Content-Type

**Request GET** không có body thì thường cần `Accept: application/json` nếu muốn kiểm tra content negotiation.

**Request POST JSON** cần:

~~~java
mvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"A Book\"}"));
~~~

Nếu thiếu `Content-Type`, Spring MVC không nhất thiết chọn JSON converter; có thể trả 415 hoặc không bind như ý. Nếu controller khai báo `produces=application/json` mà client gửi `Accept: text/plain`, có thể trả **406 Not Acceptable**. Với `consumes=application/json` mà client gửi `Content-Type: text/plain`, có thể trả **415 Unsupported Media Type**.

### 3.2. Phân biệt JSON mapping vs serialize service result

Nếu controller trả `BookView`, Jackson thường serialize record thành JSON object. JSON converter/cấu hình trong `@WebMvcTest` có thể phản ánh MVC auto-config, nhưng **custom ObjectMapper modules của ứng dụng chỉ có khi được include vào slice**. Đừng kết luận production JSON shape chính xác nếu app dùng một `@Configuration` khác tự tạo ObjectMapper mà slice không nạp.

Nếu cần kiểm tra Jackson independently, dùng `@JsonTest`; nếu cần xác nhận mapping trong **đầy đủ app config**, thêm `@SpringBootTest + @AutoConfigureMockMvc` hoặc integration test.

## 4. `@MockitoBean`: mock service mà không nạp toàn bộ nghiệp vụ

Trong Spring Framework 6.2/Spring Boot 3.5, annotation được khuyến nghị là:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

`@MockitoBean` thay bean có sẵn hoặc tạo Mockito mock khi bean cần thiết không có trong slice. Nó không phải `@Mock` đơn thuần:
- `@Mock` là Mockito field, **không tự đưa bean vào Spring ApplicationContext**.
- `@MockitoBean` đăng ký mock như bean để **constructor injection vào controller** thành công.
- `@MockBean` của Spring Boot đời cũ đã bị deprecate từ Boot 3.4, nên dùng `@MockitoBean` khi ở Boot 3.5.
- `@MockitoSpyBean` dùng spy bao quanh bean thật trong context theo quy tắc override khác; không cần thiết trong các slice đơn giản.

~~~java
@MockitoBean
BookService bookService;

@Test
void example() {
    when(bookService.find(7L))
        .thenReturn(new BookView(7L, "Clean Tests"));
}
~~~

Nếu có nhiều beans cùng type, `@MockitoBean` cần qualifier/name nhất quán; không chọn bừa. Option `enforceOverride = true` có thể fail nếu không có bean gốc; với `@WebMvcTest` service bị loại khỏi slice, phải hiểu rõ default **replace-or-create** trước khi dùng option này. Không mock controller khi mục tiêu test chính controller; mock các collaborators ở ranh giới nghiệp vụ/external infrastructure.

**Lưu ý:** khi thay service bằng mock, các advice như `@Transactional`/`@Cacheable`/security method-level có thể không còn; mọi logic gốc của service **không được chạy**. `when(...).thenReturn(...)`/`thenThrow(...)` định nghĩa hành vi giả, nên test pass không chứng minh database/repository hoạt động đúng.

## 5. Project Java 17 hoàn chỉnh: Book API với security + validation

Dự án sau cố ý minh họa cả happy path và lỗi thường gặp: controller gọi service, body JSON qua Jackson, `@Valid` xử lý đầu vào, `@RestControllerAdvice` chuyển lỗi not-found thành JSON 404, Spring Security cho GET công khai và POST chỉ cho `ROLE_EDITOR`, CSRF vẫn bật.

**Cấu trúc:**

~~~text
mvc-slice-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/mvcslice/
    │       ├── MvcSliceApplication.java
    │       ├── BookCreateRequest.java
    │       ├── BookView.java
    │       ├── BookNotFoundException.java
    │       ├── BookService.java
    │       ├── BookController.java
    │       ├── BookErrorAdvice.java
    │       └── ApiSecurityConfig.java
    └── test/
        └── java/com/example/mvcslice/
            ├── BookControllerWebMvcTest.java
            ├── BookFullContextMockMvcTest.java
            └── BookRealHttpTest.java
~~~

### 5.1. `pom.xml`

~~~xml
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
    <artifactId>mvc-slice-demo</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

Maven BOM của Spring Boot quản lý versions tương thích. `spring-boot-starter-validation` quan trọng để `@Valid` + `@NotBlank` hoạt động. `spring-security-test` cung cấp `user(...)`, `csrf()` và `@WithMockUser`; không có dependency này thì những import security-test không compile.

### 5.2. `src/main/java/com/example/mvcslice/MvcSliceApplication.java`

~~~java
package com.example.mvcslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcSliceApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcSliceApplication.class, args);
    }
}
~~~

Giữ main class `@SpringBootApplication` đơn giản, không thêm `@ComponentScan` tùy ý có thể phá test slicing.

### 5.3. `BookCreateRequest.java`

~~~java
package com.example.mvcslice;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookCreateRequest(
        @NotBlank
        @Size(max = 80)
        String title) {
}
~~~

`@NotBlank` bắt đầu vào null/empty/toàn dấu cách; `@Size(max=80)` ngăn title quá dài. Java record dùng được cho DTO với Jackson trong Spring Boot 3.5. `@Valid @RequestBody BookCreateRequest` ở controller kích hoạt validation sau deserialize. Không tin client chỉ vì nó có JSON đúng syntax.

### 5.4. `BookView.java`

~~~java
package com.example.mvcslice;

public record BookView(long id, String title) {
}
~~~

Đây là response DTO. Với JSON converter thông thường, nó có hai fields `id` và `title`. Đừng trả Entity JPA có lazy-loading/secret fields trực tiếp chỉ vì test JSON đang pass.

### 5.5. `BookNotFoundException.java`

~~~java
package com.example.mvcslice;

public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}
~~~

Service dùng exception rõ nghĩa. HTTP status **không được quyết định ở service**; `BookErrorAdvice` sẽ map exception sang response 404.

### 5.6. `BookService.java`

~~~java
package com.example.mvcslice;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final Map<Long, BookView> books =
            new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong(1);

    public BookService() {
        books.put(1L, new BookView(1L, "Spring MVC Guide"));
    }

    public BookView find(long id) {
        BookView book = books.get(id);
        if (book == null) {
            throw new BookNotFoundException(id);
        }
        return book;
    }

    public BookView create(String title) {
        long id = ids.incrementAndGet();
        BookView result = new BookView(id, title);
        books.put(id, result);
        return result;
    }
}
~~~

Service này **đang giữ dữ liệu trong JVM**, không dùng DB. Việc có một seeded book `id=1` khiến full-context/real HTTP tests kiểm tra được **service thật** mà không phải Testcontainers. Nó không phải thiết kế persistence cho production; restart sẽ mất books tạo mới. Ở `@WebMvcTest`, service thật **không được scan** và được thay bằng `@MockitoBean`, nên seeded book **không tồn tại trong mock** trừ khi test stub riêng.

### 5.7. `BookController.java`

~~~java
package com.example.mvcslice;

import java.net.URI;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/api/books",
                produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {
    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping("/{id}")
    public BookView find(@PathVariable long id) {
        return bookService.find(id);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @Valid @RequestBody BookCreateRequest request) {
        BookView created = bookService.create(
                request.title().trim());
        return ResponseEntity
                .created(URI.create("/api/books/" + created.id()))
                .body(created);
    }
}
~~~

Các bước test cần bao phủ:
- `GET /api/books/7` → path variable long, service.find(7), JSON body.
- `POST /api/books` → deserialize JSON thành record, validate title, trim, service.create, trả 201 + Location + JSON.
- `GET id không tồn tại` → service throws, controller advice map 404.
- `POST title rỗng` → HTTP 400 **trước khi** service.create chạy.
- `POST thiếu auth/role/CSRF` → Security filters chặn trước controller.
- Gửi Content-Type hoặc Accept không phù hợp → 415/406 tùy request.

### 5.8. `BookErrorAdvice.java`

~~~java
package com.example.mvcslice;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BookErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ApiError> missing(
            BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("BOOK_NOT_FOUND",
                                   ex.getMessage()));
    }

    public record ApiError(String code, String message) {
    }
}
~~~

Spring MVC xử lý exception qua handler exception resolvers và `@RestControllerAdvice`. Trong `@WebMvcTest`, advice dạng này thuộc nhóm components **được scan**, nên khi test nhận lỗi từ mock service, JSON 404 phản ánh mapping của advice (miễn advice nằm dưới package component scan và không bị exclude). Với các exception khác như `MethodArgumentNotValidException`, Spring MVC mặc định chuyển thành 400 nếu không có custom handler; không giả định error JSON body mặc định giống nhau giữa mọi Boot versions/config.

### 5.9. `ApiSecurityConfig.java`

~~~java
package com.example.mvcslice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/books/**")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/api/books")
                    .hasRole("EDITOR")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Không disable CSRF: POST cần token trong test/demo.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails editor = User.withUsername("editor")
            .password("{noop}demo-only")
            .roles("EDITOR")
            .build();
        return new InMemoryUserDetailsManager(editor);
    }
}
~~~

Đây là **hệ thống user demo** với `{noop}` plaintext password; **tuyệt đối không dùng cấu hình mật khẩu này trong production**. Production dùng password hash mạnh/identity provider, TLS, security auditing và authorization policy phù hợp.

**CSRF cố ý bật** để bài cho thấy `MockMvc` phải test bảo mật thực. Với REST API xác thực bằng bearer token qua Authorization header có policy CSRF khác, nhưng không áp dụng `csrf.disable()` bừa cho ứng dụng có cookie/Basic credentials mà browser tự gửi. `@WebMvcTest` không nhất thiết component-scan một `@Configuration` business/security tùy chỉnh, nên test slice sẽ **`@Import(ApiSecurityConfig.class)` tường minh** để policy được kiểm tra thực sự. Full-context app tự scan cấu hình này.

## 6. File test trọng tâm: `@WebMvcTest + MockMvc + @MockitoBean`

File **`src/test/java/com/example/mvcslice/BookControllerWebMvcTest.java`**:

~~~java
package com.example.mvcslice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = BookController.class)
@Import(ApiSecurityConfig.class)
class BookControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    BookService bookService;

    @Test
    void getBookReturnsJson() throws Exception {
        when(bookService.find(7L))
            .thenReturn(new BookView(7L, "Clean Tests"));

        mvc.perform(get("/api/books/{id}", 7L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.title").value("Clean Tests"));

        verify(bookService).find(7L);
    }

    @Test
    void notFoundUsesControllerAdvice() throws Exception {
        when(bookService.find(99L))
            .thenThrow(new BookNotFoundException(99L));

        mvc.perform(get("/api/books/{id}", 99L))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                       .value("BOOK_NOT_FOUND"))
            .andExpect(jsonPath("$.message")
                       .value("Book 99 not found"));

        verify(bookService).find(99L);
    }

    @Test
    void editorWithCsrfCanCreate() throws Exception {
        when(bookService.create("Effective MockMvc"))
            .thenReturn(new BookView(8L, "Effective MockMvc"));

        mvc.perform(post("/api/books")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"title\":\" Effective MockMvc \"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    "Location", "/api/books/8"))
            .andExpect(jsonPath("$.id").value(8))
            .andExpect(jsonPath("$.title")
                       .value("Effective MockMvc"));

        verify(bookService).create("Effective MockMvc");
    }

    @Test
    void blankTitleIsRejectedBeforeService() throws Exception {
        mvc.perform(post("/api/books")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"   \"}"))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(bookService);
    }

    @Test
    void missingCsrfReturns403() throws Exception {
        mvc.perform(post("/api/books")
                .with(user("editor").roles("EDITOR"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Test\"}"))
            .andExpect(status().isForbidden());

        verifyNoInteractions(bookService);
    }

    @Test
    void anonymousPostWithCsrfNeedsAuthentication()
            throws Exception {
        mvc.perform(post("/api/books")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Test\"}"))
            .andExpect(status().isUnauthorized());

        verifyNoInteractions(bookService);
    }

    @Test
    void wrongRoleCannotCreate() throws Exception {
        mvc.perform(post("/api/books")
                .with(user("viewer").roles("VIEWER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Test\"}"))
            .andExpect(status().isForbidden());

        verifyNoInteractions(bookService);
    }

    @Test
    void nonJsonRequestContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/books")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("title=Test"))
            .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(bookService);
    }

    @Test
    void unacceptableResponseMediaTypeReturns406()
            throws Exception {
        mvc.perform(get("/api/books/7")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isNotAcceptable());

        verifyNoInteractions(bookService);
    }
}
~~~

### 6.1. Phân tích từng nhóm test

**GET happy path** mock `BookService.find` trả DTO, nhưng routing/JSON converter là MVC thật trong slice. Nó kiểm tra status, Content-Type và JSON shape, thêm `verify(bookService).find(7L)` để xác nhận mapping truyền đúng id.

**404 handling** cho service giả ném domain exception, `BookErrorAdvice` thật map thành JSON error 404. Đây là test giá trị vì client không cần biết exception Java nội bộ.

**POST success** sử dụng **`user("editor").roles("EDITOR")`** và **`csrf()`**. Thứ nhất tạo mock authenticated principal cho MockMvc request, thứ hai cấp token hợp lệ cho security filter. Body JSON có khoảng trắng, controller trim trước khi gọi service. Test khẳng định `Location` và body `201 Created`.

**Input validation** dùng `@NotBlank`/`@Valid`. HTTP 400 được trả **trước** khi service được gọi. `verifyNoInteractions` giúp phát hiện validation bị bỏ qua trong controller.

**Security negative cases** kiểm tra thiếu CSRF (403), anonymous có CSRF nhưng chưa auth (401 do HTTP Basic entry point), authenticated thiếu role (403). Trạng thái cụ thể được thiết kế theo `ApiSecurityConfig` trong lab; ứng dụng có form login, OAuth2, custom entry point hoặc filters khác có thể dùng 302/401/403 khác nhau. Phải test contract của chính app.

**Media type cases** kiểm tra 415 từ `consumes=application/json` và 406 từ `produces=application/json`. Nếu bạn sửa routes/matchers, các status cần được review cùng API contract, không coi values trong ví dụ là tất định mọi Spring Boot service.

### 6.2. `@WebMvcTest` có tự áp Spring Security không?

Khi `spring-boot-starter-security` nằm trên classpath, Boot test slice thông thường có **security auto-configuration** và `MockMvc` với filters được áp dụng. **Nhưng custom `SecurityFilterChain` do team viết không đương nhiên được scan như mọi `@Configuration`**; vì vậy bài sử dụng:

~~~java
@WebMvcTest(BookController.class)
@Import(ApiSecurityConfig.class)
~~~

Mục tiêu là test **đúng policy mà controller cần**, không âm thầm dùng default Security chain rồi hiểu sai kết quả. Nếu bạn thấy `GET` yêu cầu login ngoài dự kiến, hãy kiểm tra chain thực sự được nạp trong slice, không ngay lập tức tắt security.

`@AutoConfigureMockMvc(addFilters = false)` có thể bỏ qua đăng ký filters trong MockMvc. Nó đôi khi tiện để cô lập mapping, **nhưng các test đó không còn chứng minh security/CSRF/filter behavior**. Không dùng làm “fix” lâu dài cho test 401/403 đỏ. Kiểm tra filter order và security configuration đúng thay vì loại bỏ filters.

### 6.3. `@WithMockUser` có thể thay `.with(user(...))`

Nếu muốn một method/nhóm tests chạy với principal giả:

~~~java
@Test
@WithMockUser(username = "editor", roles = "EDITOR")
void example() throws Exception {
    mvc.perform(post("/api/books")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"Example\"}"))
        // Các assertions tùy service stub.
        .andExpect(status().isCreated());
}
~~~

Đây là **mảnh minh họa**, không copy nguyên vào project mà thiếu stub service: mock `BookService.create` mặc định trả null, dẫn tới lỗi trong controller. Nếu áp dụng, phải stub `bookService.create("Example")` trước `perform`.

`@WithMockUser` tạo mock authentication context, **không xác minh password thật/OAuth2 signature/token introspection**. Nếu muốn test login/jwt resource server chính xác với provider, thêm security integration tests chuyên biệt. Với MockMvc, `user(...)` và `@WithMockUser` cần Spring Security test integration/filter chain phù hợp.

## 7. Test full application context nhưng vẫn dùng MockMvc

File `src/test/java/com/example/mvcslice/BookFullContextMockMvcTest.java`:

~~~java
package com.example.mvcslice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookFullContextMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void actualServiceSuppliesSeededBook() throws Exception {
        mvc.perform(get("/api/books/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.title")
                       .value("Spring MVC Guide"));
    }
}
~~~

Khác slice:
- `@SpringBootTest` nạp **full application context**, gồm `BookService` thật với seeded book id 1 và `ApiSecurityConfig` thật.
- `@AutoConfigureMockMvc` cung cấp MockMvc cho full context.
- Không có `@MockitoBean` nên controller thực sự gọi service tạo tại runtime.
- **Vẫn không chạy HTTP server thật** trong `webEnvironment=MOCK` mặc định. Không chứng minh Servlet container-level registrations, network timeout, TLS, reverse proxy hoặc xử lý error page của container.

**Quan trọng:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` tạo server thật, nhưng thêm `@AutoConfigureMockMvc` vào đó không biến chính các lệnh `mvc.perform(...)` thành network calls; chúng vẫn xử lý in-process bằng MockMvc. Muốn kiểm tra real network, dùng HTTP client gọi localhost:randomPort.

### 7.1. Full context và database

Nếu production service có JPA/DataSource, full test cần DB test đúng: Testcontainers, embedded DB phù hợp hoặc test database riêng. Không tự giả định `@Transactional` ở test sẽ rollback mọi thay đổi của request gửi qua **real HTTP socket**: server/client thường chạy khác threads/transactions. MockMvc full-context in-process và real HTTP server có transaction scopes khác nhau.

Cần quyết định fixtures, cleanup/isolation và thời gian test hợp lý. Mock service trong một full test có thể làm nó giống slice hơn mà vẫn phải startup cả application; sử dụng chỉ khi lý do rõ, tránh tạo suite chậm nhưng không gia tăng coverage.

## 8. Real HTTP integration test: kiểm tra tầng mà MockMvc không có

File `src/test/java/com/example/mvcslice/BookRealHttpTest.java`:

~~~java
package com.example.mvcslice;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookRealHttpTest {

    @LocalServerPort
    int port;

    @Test
    void realTomcatServesPublicGet() {
        ResponseEntity<String> response =
            RestClient.create().get()
                .uri("http://127.0.0.1:" + port + "/api/books/1")
                .retrieve()
                .toEntity(String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody() != null &&
                   response.getBody().contains("Spring MVC Guide"));
    }
}
~~~

Test này dùng **embedded Tomcat có real socket**, phù hợp để kiểm tra HTTP connector, Servlet registrations, filters ở runtime và headers thực. Trong bài chỉ assert GET 200 để không cần xử lý CSRF token qua live session. Ở real client tests cho POST có CSRF, hãy tạo/tokenize session đúng contract; **không** tắt CSRF chỉ để curl dễ dùng.

Thực tế real server integration test cũng **không tự kiểm tra Nginx/CDN/k8s ingress** nếu chúng không được dựng trong test environment. Muốn bảo đảm public route rewrite hoặc TLS/HTTP2, cần staging test qua tuyến mạng thật hoặc infrastructure-level integration tests.

## 9. Build, chạy và kết quả kỳ vọng

Tại thư mục `mvc-slice-demo`:

~~~bash
java -version
mvn test
mvn clean package
java -jar target/mvc-slice-demo-0.0.1-SNAPSHOT.jar
~~~

**Kỳ vọng nếu source được đặt đúng đường dẫn, Java/Maven và dependencies khả dụng:** `mvn test` chạy nhóm slice (9 test methods), full-context MockMvc (1 test) và real HTTP (1 test); tất cả được thiết kế để **PASS**. Chạy trên máy người đọc mới khẳng định được thực tế; không coi các expected outputs là logs đã capture.

Ở terminal khác, test GET public qua real app:

~~~bash
curl -i http://127.0.0.1:8080/api/books/1
curl -i http://127.0.0.1:8080/api/books/999
~~~

**Expected semantics:**
- `GET /api/books/1` → 200, body JSON chứa `"id":1`, `"title":"Spring MVC Guide"`.
- `GET /api/books/999` → 404, body JSON chứa `"code":"BOOK_NOT_FOUND"`, message từ exception.
- HTTP headers như `Date`, `Content-Length`, encoding có thể khác theo runtime.

Một POST bằng curl **không kèm CSRF**:

~~~bash
curl -i -u editor:demo-only \
  -H 'Content-Type: application/json' \
  -d '{"title":"HTTP Test"}' \
  http://127.0.0.1:8080/api/books
~~~

Kết quả dự kiến **403 Forbidden**, bởi CSRF filter từ chối request POST thiếu token dù HTTP Basic credentials hợp lệ. **Không cần cố làm lệnh này trả 201** để chứng minh controller: `MockMvc` test ở phần 6 dùng `.with(csrf())` và `.with(user(...))` để thực hiện positive test an toàn. Trong browser/session app thật, cần quy trình cấp và gửi token từ backend phù hợp; với API stateless bearer-token có thể thiết kế CSRF policy khác theo threat model.

### 9.1. Chạy riêng lớp test

~~~bash
mvn -Dtest=BookControllerWebMvcTest test
mvn -Dtest=BookFullContextMockMvcTest test
mvn -Dtest=BookRealHttpTest test
~~~

Lệnh Maven trên dùng `-Dtest` để lọc lớp JUnit theo Surefire; có thể khác khi project dùng Gradle hoặc multi-module. Chạy riêng slice sẽ thường nhanh hơn full context, nhưng không đặt kỳ vọng millisecond cố định vì classpath, test context cache và máy CI khác nhau.

## 10. MockMvc standalone vs WebApplicationContext setup

Có **hai chế độ xây MockMvc** (Spring Framework 6.2 official docs), khác việc chọn Boot test annotation.

### 10.1. `MockMvcBuilders.standaloneSetup(...)`

Test kiểu gần unit test, không khởi động Spring Test ApplicationContext:

~~~java
BookService service = org.mockito.Mockito.mock(BookService.class);
BookController controller = new BookController(service);

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new BookErrorAdvice())
        .build();
~~~

Đây là **mảnh minh họa**, cần imports `MockMvc`, `MockMvcBuilders` và Mockito; không tự động có SecurityFilterChain/Bean Validation/JSON customization như full Spring context. Muốn test security trong standalone, phải tự cấu hình Spring Security `springSecurity()` và filters/context thích hợp. Muốn test validation chính xác, phải cấu hình validator như trong production. Vì vậy standalone có thể cho kết quả **false positive** nếu pipeline thật có interceptor, security config hoặc exception advice chưa được đưa vào builder.

**Ưu điểm:** cực nhanh, setup rõ controller và collaborators. **Nhược điểm:** càng nhiều MVC config đặc thù thì càng phải dựng bằng tay; sẽ khác runtime nếu bỏ sót filter/converter.

### 10.2. `MockMvcBuilders.webAppContextSetup(...)`

Nếu đã có `WebApplicationContext` từ Spring TestContext:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
~~~

Đây cũng là **mảnh minh họa**; cần `MockMvcBuilders`, `WebApplicationContext` và `MockMvc` imports. Nó dùng MVC configuration do context nạp, phản ánh Spring MVC config chính xác hơn standalone. **Spring Boot `@WebMvcTest` đã tự tạo `MockMvc`** nên bình thường không cần tự build lại; làm thêm builder có thể vô tình bỏ qua Boot customizers/filters.

Đối với Spring Security MockMvc setup thủ công, Spring Security docs thường dùng:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
~~~

`springSecurity()` cần static import từ `SecurityMockMvcConfigurers`; `spring-security-test` cần trên test classpath. Trong Boot `@WebMvcTest` của ví dụ, auto-configured MockMvc đã xử lý tích hợp Security nên test trực tiếp được.

### 10.3. Context caching làm sao ảnh hưởng?

Spring TestContext cache ApplicationContext giữa các test classes có cấu hình tương thích. `@MockitoBean` definitions, `@Import`, active profiles, properties và test customizers có thể làm test context cache key khác, dẫn tới khởi tạo nhiều contexts. Không phá context cache bằng `@DirtiesContext` ở mọi test mà không có lý do.

Một test tác động static globals hoặc DB shared state còn có thể gây order-dependent failure dù dùng context cache. Test controller mock service cần độc lập; đừng để trạng thái giữa test methods tự nhiên “chuyền” nhau.

## 11. Khi có Security, cần test đúng lớp bảo vệ

### 11.1. Đừng xóa security để cho test chuyển sang xanh

Các lỗi hay gặp:
- `GET` public trong app nhưng `@WebMvcTest` trả 401: custom `SecurityFilterChain` chưa import hoặc mock context dùng default security.
- `POST` trả 403: có thể **CSRF missing**, không nhất thiết thiếu role.
- `POST` với `@WithMockUser` vẫn 403: mock principal không tự tạo CSRF token, hãy xem `csrf()`.
- `.with(user("editor"))` bị 403: user chỉ có `ROLE_USER` mặc định; `hasRole("EDITOR")` cần `roles("EDITOR")`.
- `@AutoConfigureMockMvc(addFilters=false)` làm POST được 201 dù app thật sẽ 403: security test trở nên giả dối.
- `@WithMockUser` pass nhưng Basic credentials/JWT fail trên server thật: annotation **không xác minh authentication provider/token decoder**.

**Đừng** thay policy `anyRequest().permitAll()` để “sửa test” nếu production cần authorization. Viết test cho **anonymous, authenticated, role thiếu, CSRF valid/invalid**, và một số integration tests cho authentication thật.

### 11.2. Về 401 và 403

Trong demo:
- Missing auth nhưng đã có valid CSRF → HTTP Basic entry point có thể trả **401 Unauthorized**.
- Authenticated nhưng role không đủ → **403 Forbidden**.
- Authenticated đủ role nhưng thiếu CSRF trên POST → **403 Forbidden**.
- Missing CSRF và missing auth → kết quả phụ thuộc thứ tự security filters, thường **403** trước khi đến authentication, vì vậy khi muốn test riêng 401 của auth thì **cấp CSRF hợp lệ trong test**.

Với form login, một request unauthenticated có thể redirect `302` thay vì trả 401. Với OAuth2 resource server, status/headers có thể khác. Assertions phải phản ánh **security chain thực tế**.

### 11.3. CORS preflight, CSRF, cookies

Browser CORS preflight là `OPTIONS` và thường không mang authenticated session cookies như request chính. Nếu ứng dụng có `http.cors(...)` hoặc `CorsFilter`/`WebMvcConfigurer#addCorsMappings`, slice test phải include policy thật; có thể dùng MockMvc:

~~~java
mvc.perform(options("/api/books")
        .header("Origin", "https://ui.example.test")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isOk());
~~~

**Đây chỉ là đoạn minh họa**: project hiện tại **chưa cấu hình CORS**, nên **không** copy assertion 200 này như một test phải pass. Cần thêm CorsConfigurationSource/MVC CORS config và test allowed/disallowed origins. Không dùng CORS như authorization; nó không ngăn curl/non-browser HTTP clients. Khi client có cookies, phối hợp SameSite, CSRF và session policy.

### 11.4. Mock SecurityContext vs real auth

`@WithMockUser`/`user()` tạo Authentication giả tại test boundary. Nếu controller dựa vào `Principal` hoặc `@AuthenticationPrincipal`, test có thể cung cấp user/roles theo nhu cầu; nhưng đây **không** phải test verify password hash, OAuth2 JwtDecoder, JWK rotation, token expiry hoặc reverse-proxy trusted headers. Cần test ở security component/integration layer cho những thứ đó.

## 12. Những giới hạn quan trọng của MockMvc với web runtime

### 12.1. Servlet container-level behavior

MockMvc dựa trên mock Servlet API nên **không có real HTTP socket**, TLS handshake, container connection timeout, HTTP/2 multiplexing, proxy buffering, actual compression ở gateway hay redirect network hop. Nếu app dùng Jersey ServletContainer ở `/api/*` và MVC DispatcherServlet ở `/`, MockMvc chỉ hỏi Spring MVC; nó **không chứng minh** Servlet container thực sự chọn đúng servlet mapping.

Cũng vậy, một `Filter` bean có thể được Boot auto-register vào real Servlet container nhưng test standalone MockMvc không thấy registration đó. Hãy kiểm tra bằng `@SpringBootTest(RANDOM_PORT)`/embedded Tomcat test khi yêu cầu đúng loại.

### 12.2. 404/error page và error dispatch

MockMvc có thể kiểm tra controller ném exception và `@ControllerAdvice` chuyển nó thành 404/JSON. Nhưng **container error pages**, Servlet `ERROR` dispatch và Boot `/error` pipeline tại runtime có thể hoạt động khác. Spring Boot docs nói MockMvc không thể trực tiếp xác minh error page được render từ container support.

Nếu test chỉ thấy `NoHandlerFoundException` hoặc `NoResourceFoundException` trong slice, đừng suy ra byte-level error body tại HTTP server thật như thế. Kiểm tra bằng real client nếu contract 404/error page là quan trọng.

### 12.3. JSP, redirects và rendered HTML

MockMvc có thể assert logical view, forwardedUrl hoặc redirect Location, nhưng **không chạy JSP thật** vì JSP cần container forward/render. Thymeleaf/Freemarker hoạt động theo mô hình khác và có thể render HTML trong MockMvc nếu template engine/config được nạp vào context. Với JSP, cần integration test container để xem HTML cuối.

Nếu controller return `"home"` và bạn assert `view().name("home")`, điều đó không tự bảo đảm template thật tồn tại, static resources phục vụ đúng URL hay client nhận CSS.

### 12.4. Multipart và upload

MockMvc có request builder cho multipart; nó kiểm tra controller nhận `MultipartFile` và validation/mapping, nhưng không chứng minh toàn bộ multipart parsing của real container, upload size limits, temp disk, reverse proxy body size limits hay antivirus/storage integration. Thử bằng real HTTP với file nhỏ/lớn để test các giới hạn thực.

### 12.5. Async endpoints và streaming

Spring MVC async (`Callable`, `DeferredResult`, `SseEmitter`) có lifecycle khác synchronous controller. Với `MockMvc`, asynchronous requests có thể kiểm tra bằng:

~~~java
MvcResult result = mvc.perform(get("/async"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk());
~~~

**Đây là mảnh minh họa** cần imports `MvcResult`, static `request`/`asyncDispatch`, và controller `/async` trả async type thực. Project demo chỉ có sync endpoints nên không copy chạy trực tiếp. Trong real streaming/SSE, còn phải kiểm tra client disconnect, flush, proxy buffering và timeout qua server thật; MockMvc không mô phỏng kết nối mạng tồn tại lâu đầy đủ.

### 12.6. Static resources và MIME

`@WebMvcTest` có thể nạp MVC static handler infrastructure theo auto-config, nhưng không nên lấy một slice chỉ nhắm Controller làm bằng chứng classpath assets đã được packaged vào executable JAR, hoặc Jersey/other Servlet mappings không chặn static path. Dùng integration test JAR/real HTTP nếu cần kiểm tra `/index.html`, `/assets/app.js` hay caching/ETag qua Tomcat/nginx.

## 13. Validation, exception contracts và JSON precision

### 13.1. Error response không chỉ là status code

Với endpoint public API, nên assert một error contract ổn định:
- 400 khi `@Valid` thất bại hoặc body JSON không parse được;
- 404 khi business resource không tồn tại;
- 415/406 khi content negotiation sai;
- 401/403 khi auth/csrf/role sai;
- 500 chỉ khi lỗi bất ngờ; tránh expose stack traces nội bộ.

Trong ví dụ, `BookErrorAdvice` quy định JSON `{"code":"BOOK_NOT_FOUND","message":"Book 99 not found"}`. Không cần test exact whitespace/field ordering. Đừng assert error body cho validation 400 nếu bạn chưa định nghĩa output shape ở `@ControllerAdvice`; Spring Boot 3.5 default error handling có thể khác khi version/properties thay đổi.

### 13.2. Cần test deserialize + converter

Vì DTO là Java record, Jackson phải deserialize body JSON vào `BookCreateRequest`. Test `POST` thành công và verify `create("Effective MockMvc")` chứng minh body đã bind, trim và đi qua validation.

Có thể bổ sung các bài:
- request thiếu `title` → 400 nhờ `@NotBlank`;
- `title` dài quá 80 ký tự → 400;
- JSON syntax hỏng → 400 do `HttpMessageNotReadableException`;
- `id` non-numeric trong path variable → 400 (conversion failure);
- unsupported media type → 415;
- unacceptable Accept → 406;
- wrong HTTP method → 405 nếu mapping/path và security permits qua để MVC trả 405.

**Lưu ý:** security có thể trả 403 trước khi MVC kịp báo 405/415/400; khi test validation/content type, cấp đúng auth+CSRF để cô lập nguyên nhân.

### 13.3. Không mock chính thứ cần kiểm tra

Nếu bạn mock `Validator`, `ObjectMapper`, `HandlerMapping` hay `DispatcherServlet` trong slice mà không có lý do, các assertions có thể không còn chứng minh MVC infrastructure. Thường chỉ mock **service boundary**: `BookService`, event publisher hoặc remote client, còn controller/advice/converters/validator chạy thật.

Nếu controller chỉ là một lớp mỏng gọi service, chủ yếu test HTTP contract; service nghiệp vụ được test riêng bằng unit/integration tests với database phù hợp.

## 14. Test suite thiết kế theo rủi ro

Một chiến lược hợp lý:

| Rủi ro | Test đầu tiên nên dùng | Bổ sung khi cần |
| --- | --- | --- |
| URL/method/path variables sai | `@WebMvcTest` + MockMvc | Real HTTP smoke |
| JSON body/header không đúng | `@WebMvcTest` + MockMvc | Full context nếu có custom ObjectMapper |
| `@Valid` không hoạt động | `@WebMvcTest` + validation dependency | API contract integration |
| 404 exception mapping sai | `@WebMvcTest` với mock service throws | Full context nếu nhiều advices |
| CSRF/roles sai trong MVC | `@WebMvcTest` + real SecurityFilterChain import | Security integration/auth provider test |
| Business service sai | Service unit test với mocks thích hợp | Repository/database integration |
| JPA/transaction lỗi | `@DataJpaTest` / testcontainers | Full application integration |
| Custom filters/Servlet auto-registration trùng | `@SpringBootTest(RANDOM_PORT)` | Container/deployment staging |
| Tomcat vs Jersey mapping, static 404 | Real embedded server test | Packaged JAR/staging |
| Proxy/path rewrite/TLS | Staging end-to-end HTTP | Infrastructure-specific tests |
| SSE/WebSocket disconnect/idle behavior | Protocol-level tests | Real proxy/load tests |
| Security identity provider/JWT invalid | Security integration with real-like token decoder | Staging identity provider contract |

Mỗi case nên đặt assertions phản ánh **đối tượng đang test**, không phải chỉ đạt coverage phần trăm. Chẳng hạn `@WebMvcTest` 100% test methods pass **không chứng minh** production DB/HTTP gateway integration.

### 14.1. Thực hành trước khi merge

- Chạy slice tests nhanh ở mỗi commit.
- Có vài `@SpringBootTest + @AutoConfigureMockMvc` cho wiring/application security config.
- Có real HTTP integration tests cho routes quan trọng và ít nhất một negative case như 404/401.
- Khi sản phẩm có reverse proxy, CORS, multipart lớn, static content hoặc servlet registrations, thêm staging tests đúng tuyến thực.
- Với DB/service dependencies, dùng deterministic fixtures/testcontainers và cleanup giữa tests.
- Không dựa vào thứ tự execution của JUnit hoặc dữ liệu còn từ test trước.
- Đừng tắt security hoặc CSRF để đạt xanh.
- Giới hạn context variations để giảm startup cost/cache misses.
- Khi thay API contract, cập nhật assertions, REST Docs/OpenAPI và consumer contract tests tương ứng.

## 15. Bảng lỗi thường gặp và cách sửa

| Triệu chứng | Giải thích khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `@WebMvcTest` không start context vì thiếu `BookService` | Service bị exclude khỏi slice | `@MockitoBean BookService` hoặc explicit test bean |
| `@Mock BookService` nhưng controller vẫn thiếu bean | Mockito field chưa đăng ký Spring bean | Dùng `@MockitoBean` |
| `@MockBean` deprecation warning trong Boot 3.5 | Annotation cũ | Dùng Spring Framework `@MockitoBean` |
| Có hai beans type BookService, @MockitoBean ambiguous | Không rõ target | Dùng bean name/qualifier đúng |
| Slice kéo lên database ngoài ý muốn | Custom component scan/@Import quá rộng | Tách configs, giữ Boot type exclusion |
| GET public trả 401 trong slice | Custom SecurityFilterChain không được import, default policy | `@Import(ApiSecurityConfig.class)` đúng phần cần |
| POST trả 403 dù có @WithMockUser | Thiếu CSRF hoặc thiếu role | `.with(csrf())` và role phù hợp |
| POST không auth, thiếu CSRF mà kỳ vọng 401 | CsrfFilter có thể trả 403 trước auth | Cấp valid csrf khi test riêng auth |
| POST thành công sau `addFilters=false` | Security filters bị bỏ khỏi MockMvc | Không dùng làm proof cho security |
| JSON body null/missing fields | Service mock chưa stub, converter/DTO mismatch | Stub collaborator, xem status/content body |
| Test `@WithMockUser` pass nhưng real token fail | Không test auth provider/decoder | Test login/JWT separately |
| ControllerAdvice 404 không áp dụng | Advice không nằm trong slice hoặc bị exclude | Check scan/package, @Import advice nếu cần |
| JSON 400 body khác expected | Không có custom error contract | Assert status hoặc định nghĩa advice |
| `@Valid` không tạo 400 | Thiếu validation starter hoặc annotation trên @RequestBody | Thêm validation starter và `@Valid` |
| 415 do POST thiếu Content-Type | Converter/consumes không match | Set `contentType(APPLICATION_JSON)` |
| 406 do Accept sai | Controller produces JSON nhưng Accept text/plain | Set `accept(APPLICATION_JSON)` |
| MockMvc pass nhưng HTTP thật 404 | Servlet mapping/proxy rewrite/Jersey/container khác | RANDOM_PORT và staging test |
| MockMvc không render JSP | JSP cần real container forward | Real HTTP test |
| Test file upload pass nhưng prod 413/500 | Proxy/body/temp-disk limits | Real upload tests theo env |
| Tests chậm như full app dù dùng slice | Import full configs, nhiều controllers, context cache miss | Scope @WebMvcTest rõ và mocks |
| Multiple @...Test slices trên cùng test | Slices không composable kiểu đó | Chọn một slice hoặc @SpringBootTest |
| Tests chia sẻ data/leak state | Static global/DB fixtures/context cache | Isolate fixtures, reset state, @DirtiesContext có chọn lọc |
| `@SpringBootTest(RANDOM_PORT)` mà vẫn dùng MockMvc để test socket | MockMvc không đi network | Dùng RestClient/WebTestClient đến random port |
| Async assertion fail vì response chưa hoàn tất | Chưa asyncDispatch | `request().asyncStarted()` và `asyncDispatch` |
| Exception test ra 500 thay vì 404 | Sai domain exception class/advice package | Kiểm tra `@ExceptionHandler` + mock throw |
| Static file đã đóng gói nhưng MockMvc không phát hiện Jersey nuốt route | Không có real container selection | Real HTTP tests/JAR |

## 16. Bài tập tự kiểm tra

1. `@WebMvcTest` có khởi động embedded Tomcat không? Vì sao?
2. `MockMvc` xử lý request bằng socket HTTP thật hay mock Servlet API?
3. Khi chọn `@WebMvcTest(BookController.class)`, `@Service BookService` có tự được scan không?
4. `@MockitoBean` khác `@Mock` và `@MockBean` ở điểm nào?
5. Tại sao không nên mock chính `DispatcherServlet`/Jackson nếu mục tiêu là kiểm tra MVC?
6. Trong bài, vì sao `@Import(ApiSecurityConfig.class)` xuất hiện trên slice test?
7. Nếu một POST trả 403, làm sao tách lỗi CSRF khỏi lỗi role?
8. Vì sao `@WithMockUser` không chứng minh JWT decoder hoặc password hashing đúng?
9. `@AutoConfigureMockMvc(addFilters=false)` làm security tests mất ý nghĩa thế nào?
10. `@Valid @RequestBody` khác việc chỉ deserialize JSON ở đâu?
11. Vì sao test validation 400 nên `verifyNoInteractions(bookService)`?
12. Khi service bị mock, test pass có chứng minh transaction/DB đúng không?
13. `GET /api/books/999` trong slice dùng exception như thế nào để kiểm tra advice?
14. `contentType` request header và `accept` header khác gì nhau?
15. Status 415 khác 406 về nguyên nhân?
16. `@SpringBootTest + @AutoConfigureMockMvc` khác `@WebMvcTest` ở context?
17. `@SpringBootTest(RANDOM_PORT)` khác `@SpringBootTest(MOCK)` ở gì?
18. Trong `BookRealHttpTest`, vì sao gọi `RestClient.create()` lại hợp lý?
19. Với JSP, MockMvc có render HTML thật không?
20. Tại sao một test MockMvc không chứng minh Jersey Servlet mapping `/api/*`?
21. Nếu app dùng custom Jackson ObjectMapper bean ngoài MVC slice, cần test bổ sung gì?
22. Vì sao không gắn `@WebMvcTest` và `@DataJpaTest` vào một lớp?
23. Cần làm gì để test custom CORS preflight thực sự đáng tin?
24. `@RestControllerAdvice` có thể được include trong @WebMvcTest không?
25. Nếu async endpoint trả `DeferredResult`, hai bước MockMvc test là gì?
26. Vì sao `RANDOM_PORT` HTTP test cần fixture/cleanup rõ với DB?
27. Khi từ Boot 3.5 lên Boot 4.x, vì sao cần xem lại package/dependencies của test annotations?
28. Nếu slice chạy chậm, những yếu tố nào ảnh hưởng Spring TestContext cache?
29. Có nên đổi policy `permitAll()` để “sửa” một suite nhận 401/403 không?
30. Test nào giúp xác minh container error dispatch hoặc reverse proxy rewrite đúng?

**Đáp án trọng tâm:** (1) Không, mock environment. (2) Mock Servlet objects trong JVM. (3) Không; dùng @MockitoBean. (4) Mockito bean trong Spring context; @Mock là field, @MockBean cũ deprecated. (5) Cần test infrastructure thật. (6) Nạp custom security policy cho slice. (7) Cấp csrf rồi đổi auth/role; test cả 3 case. (8) Dùng mock authentication, không thực token/password verification. (9) Filters bị bỏ qua. (10) Kích hoạt Bean Validation. (11) Đảm bảo chặn trước business. (12) Không. (13) Mock service thenThrow và assert JSON 404. (14) Request body media type vs client response preference. (15) Unsupported request media vs unacceptable response media. (16) Full context vs web slice. (17) Real server vs mock HTTP. (18) Nó là real HTTP client gọi socket localhost, không cần auto tracing cho test. (19) Không với JSP container forwarding. (20) Servlet mapping nằm ngoài MockMvc. (21) Full-context/real HTTP config test. (22) Không hỗ trợ kết hợp slices. (23) Nạp policy thật và assert origins/headers/security, thêm browser/staging test. (24) Có. (25) asyncStarted rồi asyncDispatch. (26) Real HTTP transactions tách test thread. (27) Test modules/packages có thay đổi. (28) Mocks/imports/profiles/properties/context dirtiness. (29) Không. (30) RANDOM_PORT/staging proxy test.

## 17. Nguồn tài liệu chính thức

- **Spring Boot 3.5 – Testing Spring Boot Applications**, `@WebMvcTest`, @MockitoBean, MockMvc và full-context tests: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Boot 3.5 – Test Slices / @WebMvcTest auto-configurations**: https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- **Spring Boot 3.5 – How-to: Testing**, security tích hợp và cấu trúc configuration cho slice tests: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- **Spring Framework 6.2 – Bean Overriding in Tests**, `@MockitoBean`, `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- **Spring Framework 6.2 – MockMvc Setup Options**, standalone vs webAppContext: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html
- **Spring Framework 6.2 – MockMvc vs End-to-End Tests**, Servlet API mocks, JSP/container limitations: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/vs-end-to-end-integration-tests.html
- **Spring Framework 6.2 – MockMvc Async Requests**: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html
- **Spring Security 6.5 – MockMvc testing with user and CSRF**: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html và https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- **Spring Boot 3.5.16 release/OSS support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
