# @WebMvcTest, MockMvc, and MVC Testing Scope in Spring Boot

**Context:** Spring Boot → web-runtime → **Web runtime testing**. This lesson explains the nature of the `@WebMvcTest` **MVC test slice**, how `MockMvc` simulates request/response at the Spring MVC layer, which beans and auto-configurations are actually loaded, how to isolate services with `@MockitoBean`, testing JSON/validation/controller advice/security/CSRF, when `@SpringBootTest + @AutoConfigureMockMvc` or `@SpringBootTest(RANDOM_PORT)` is needed, Servlet container limitations, and a checklist to avoid false positives.

**Environment:** Java 17+, Maven, Spring Boot **3.5.16** (Spring Framework 6.2.x), JUnit Jupiter 5, Mockito, Spring MVC, Spring Security 6.5.x. The example is a complete runnable Maven project containing controller/service/DTO/exception/security and three kinds of tests. Version 3.5.16 belongs to a line whose OSS support has ended (mid-2026): choose a still-supported version/patch line for production. Only use APIs and package names compatible with Boot 3.5; do not mix with new Boot 4.x packages/modules.

> **Key takeaway:** `@WebMvcTest` is **neither** a full application test **nor** a pure Java unit test. It initializes a **Spring Test ApplicationContext containing only the MVC slice**, wires real MVC infrastructure for the selected controllers, and typically uses **mocks for collaborators/services**. `MockMvc` executes Spring MVC processing inside the JVM using mock Servlet objects, **without opening an HTTP port or running a real embedded Tomcat**. A good suite usually pairs fast slice tests with a few full-context and HTTP-server integration tests for risks that a mock environment cannot reproduce.

## 1. Where Does MVC Testing Fit in the Web Runtime?

A Servlet MVC request typically follows this path:

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

Not every test needs the entire pipeline. The goal of `@WebMvcTest` is to verify the **HTTP contract of the MVC layer**: URL/method, query/path variables, body serialization/deserialization, status, headers, content type, input validation, exception mapping, and filters/security included in the slice.

With `MockMvc`, Spring Test creates `MockHttpServletRequest` and `MockHttpServletResponse` and passes the request through `DispatcherServlet`/MVC infrastructure; there is no real TCP socket. Therefore, you can verify **controller routing/JSON/security filters** without booting a container, but you cannot prove that the **Tomcat connector/TLS/HTTP2/proxy rewrites** work properly.

### 1.1. Comparing Four Testing Levels

| Test Type | Context/HTTP Runtime | Collaborators | What It Tests Well |
| --- | --- | --- | --- |
| **Pure Java controller unit test** | No Spring context, direct method call | Mockito/in-memory objects | Logic branches inside the controller; does not prove mapping/JSON |
| **`@WebMvcTest` + `MockMvc`** | **Web MVC slice context**, Servlet mocks, no real server | `@MockitoBean` service/repository; some real MVC/filter components | Routing, JSON, validation, controller advice, mock security policy |
| **`@SpringBootTest` + `@AutoConfigureMockMvc`** | **Full application context** but mock HTTP, does not open a port under default `webEnvironment=MOCK` | Real services/repositories unless overridden | MVC coordination with application beans/filters; does not check sockets |
| **`@SpringBootTest(webEnvironment=RANDOM_PORT)`** | **Full context + real embedded server** on a random port | Services, DB/stubs per test setup | Servlet registrations, headers/network behavior, container error dispatch, end-to-end HTTP |

There is no rigid rule that “the last test type is always better”: full tests carry higher cost and complexity; unit/slice tests deliver fast feedback and more precise detail checks. Combine them according to risk.

### 1.2. HTTP Contract MVC Testing Differs from Business Logic Testing

Example controller:

~~~java
@GetMapping("/api/books/{id}")
public BookView find(@PathVariable long id) {
    return bookService.find(id);
}
~~~

What MVC tests should ensure:
- `GET /api/books/7` matches the right handler;
- `id` is converted to `long` (invalid input may yield 400);
- returns 200 and JSON fields `id`, `title`;
- when the service reports not found, `@RestControllerAdvice` turns it into a standard 404 contract;
- access permissions/rules are applied as expected.

What MVC slice tests **do not** prove:
- SQL statements are right, transactions commit, unique constraints or HikariCP work;
- the real service processes orders accurately;
- an HTTP reverse proxy rewrites `/api` properly;
- the Servlet container registers a `Filter`/`Servlet` by itself;
- the production token issuer, OAuth2 discovery, mTLS, or CORS at the gateway is right.

**Test what you actually run.** If a test only calls `controller.find(7)` directly, you have not tested Spring MVC routing. If you test with `MockMvc` while the entire service is mocked, you have not tested business/database logic.

## 2. What Does `@WebMvcTest` Do in Spring Boot 3.5?

The annotation from `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest` is a **test slice** with Spring TestContext integration. It focuses scanning on MVC-related components, selects one or a group of controllers, and loads the auto-configurations required for MVC; `@WebMvcTest` also **auto-configures `MockMvc`** so you can `@Autowired MockMvc` without building it manually.

An example:

~~~java
@WebMvcTest(controllers = BookController.class)
class BookControllerWebMvcTest {
    @Autowired MockMvc mvc;
    @MockitoBean BookService bookService;
}
~~~

The idea here: `BookController` is the real app controller, while `BookService` is created/replaced with a Mockito mock so it does not touch a database or network.

### 2.1. Selectively Scanned/Loaded Components

According to the Spring Boot 3.5 reference, `@WebMvcTest` restricts component scanning primarily to:
- `@Controller`/`@RestController`;
- `@ControllerAdvice`/`@RestControllerAdvice`;
- `@JsonComponent`;
- `Converter`, `GenericConverter`;
- `Filter` (depending on configuration and filter registration in the slice);
- `HandlerInterceptor`;
- `WebMvcConfigurer`, `WebMvcRegistrations`;
- `HandlerMethodArgumentResolver`;
- certain Security configurations, if security is on the classpath.

It includes MVC-related auto-configurations such as Jackson/HTTP converters, validation, MVC error infrastructure, template integrations per dependencies, and Spring Security support; this **does not** mean all app auto-configs run.

Regular beans **not automatically scanned** in the slice:
- `@Service`, `@Repository`, and ordinary business-domain `@Component` beans;
- JPA repositories, EntityManager, and DataSource unless added by other configuration;
- schedulers/consumers/external HTTP clients outside the web slice;
- arbitrary `@ConfigurationProperties` configurations (can be explicitly loaded with `@EnableConfigurationProperties`).

Therefore, controller constructor injection will fail if a service collaborator has no bean; the right approach is to **provide a mock via `@MockitoBean`**, or import an appropriate test bean/config. **Do not** widen the slice by importing `@SpringBootApplication` or full component scanning just to clear dependency errors: doing so destroys isolation.

### 2.2. Scan Restriction Is Not a Whitelist of the Whole ApplicationContext

Do not interpret “scans only Controller” as “the context has only 1 Controller bean.” Spring Boot can create MVC infrastructure, JSON converters, validators, Security, request mappings, and related helper beans. A component included via **`@Import`**, auto-configuration, or an explicit `@Bean` can still appear even if it is not in the default scan list.

**Be careful with `@SpringBootApplication` and custom `@ComponentScan`.** If the main application adds a custom `@ComponentScan` without Boot's `TypeExcludeFilter`, slice tests may accidentally scan the entire application. It is better to keep the `@SpringBootApplication` main class simple, separate domain configurations into dedicated configs, and only import what the slice needs.

### 2.3. Selecting Controllers Explicitly

~~~java
@WebMvcTest(BookController.class)
~~~

Focuses on the target controller and reduces context size. Do not declare:

~~~java
@WebMvcTest
~~~

when you only want one controller in a project with hundreds of controllers; an annotation without a specified controller can pick up more MVC components than intended, increase the required mocks, and make tests brittle.

Also do not combine `@WebMvcTest` and `@DataJpaTest` together to “get both web and DB.” Spring Boot docs do not support mixing multiple slice annotations like this. If you need to test both controller and persistence, use `@SpringBootTest` with an appropriate database/testcontainers setup.

## 3. How Does MockMvc Verify Requests and Responses?

`MockMvc` from `org.springframework.test.web.servlet.MockMvc` has this API:

~~~java
mvc.perform(get("/api/books/7")
        .accept(MediaType.APPLICATION_JSON))
   .andExpect(status().isOk())
   .andExpect(jsonPath("$.id").value(7))
   .andExpect(jsonPath("$.title").value("Clean Tests"));
~~~

Explanation:
1. `perform(...)` builds and executes a simulated request using mock Servlet APIs through Spring MVC.
2. `get("/api/books/7")` verifies mapping and method, without a socket.
3. `accept(MediaType.APPLICATION_JSON)` checks negotiated representation; this is the **Accept** header, distinct from the request body's `Content-Type`.
4. `status().isOk()` asserts HTTP status 200.
5. `jsonPath` asserts JSON content via `$.id`/`$.title` selectors, less sensitive to field order/JSON whitespace.

Useful assertion groups:

| Matcher | Verifies |
| --- | --- |
| `status().isCreated()` | HTTP 201 |
| `header().string("Location", "/api/books/8")` | Redirect/resource URI header |
| `content().contentTypeCompatibleWith(APPLICATION_JSON)` | Semantically matching Content-Type (may include charset parameter) |
| `jsonPath("$.title").value("...")` | JSON response field/value |
| `content().json(...)` | JSON semantic comparison; insensitive to raw whitespace |
| `content().string(...)` | Exact response text, suitable for plain text |
| `redirectedUrl(...)` | Redirect target |
| `view().name(...)` | Logical Spring MVC view name |
| `model().attributeExists(...)` | Model attribute for HTML MVC |
| `handler().handlerType(...)` | Mapped controller class |
| `handler().methodName(...)` | Handler method |
| `request().asyncStarted()` | MVC async request started |
| `cookie().exists(...)` | Response cookie |
| `forwardedUrl(...)` | Forwarded target in mock response |

**Do not assert every implementation detail.** API contract tests should focus on status, headers, body, and key service calls; asserting private method names or converter invocation counts is usually brittle.

### 3.1. Accept vs Content-Type

**A GET request** without a body typically needs `Accept: application/json` if you want to verify content negotiation.

**A JSON POST request** needs:

~~~java
mvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"A Book\"}"));
~~~

Without `Content-Type`, Spring MVC will not necessarily pick the JSON converter; it may return 415 or fail to bind as intended. If a controller declares `produces=application/json` and the client sends `Accept: text/plain`, it may return **406 Not Acceptable**. With `consumes=application/json` and the client sends `Content-Type: text/plain`, it may return **415 Unsupported Media Type**.

### 3.2. JSON Mapping vs Serializing a Service Result

If the controller returns `BookView`, Jackson usually serializes the record into a JSON object. The JSON converter/configuration in `@WebMvcTest` reflects MVC auto-config, but **custom application `ObjectMapper` modules are only present if included in the slice**. Do not conclude that the production JSON shape is exact if the app uses another `@Configuration` to build a custom `ObjectMapper` that the slice does not load.

If you need to test Jackson independently, use `@JsonTest`; if you need to confirm mapping under **full app config**, add `@SpringBootTest + @AutoConfigureMockMvc` or an integration test.

## 4. `@MockitoBean`: Mocking Services Without Loading All Business Logic

In Spring Framework 6.2/Spring Boot 3.5, the recommended annotation is:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

`@MockitoBean` replaces an existing bean or creates a Mockito mock when the needed bean is absent from the slice. It is not a plain `@Mock`:
- `@Mock` is a Mockito field, **it does not register a bean in the Spring ApplicationContext**.
- `@MockitoBean` registers the mock as a bean so **constructor injection into the controller** succeeds.
- Legacy Spring Boot `@MockBean` was deprecated starting in Boot 3.4, so use `@MockitoBean` on Boot 3.5.
- `@MockitoSpyBean` wraps a real bean in the context with a spy under different override rules; unnecessary in simple slices.

~~~java
@MockitoBean
BookService bookService;

@Test
void example() {
    when(bookService.find(7L))
        .thenReturn(new BookView(7L, "Clean Tests"));
}
~~~

If there are multiple beans of the same type, `@MockitoBean` requires a consistent qualifier/name; do not guess. The `enforceOverride = true` option can fail if no original bean exists; with `@WebMvcTest` excluding services from the slice, understand the default **replace-or-create** behavior before using this option. Do not mock the controller when the goal is to test the controller itself; mock collaborators at the business/external infrastructure boundary.

**Note:** when replacing a service with a mock, advice such as `@Transactional`/`@Cacheable`/method-level security may no longer be present; none of the real service logic **executes**. `when(...).thenReturn(...)`/`thenThrow(...)` defines fake behavior, so passing tests do not prove the database/repository works correctly.

## 5. Complete Java 17 Project: Book API with Security + Validation

The following project intentionally illustrates both happy paths and common failures: controller calling a service, JSON body via Jackson, `@Valid` handling input, `@RestControllerAdvice` turning not-found errors into JSON 404, Spring Security permitting public GET and restricting POST to `ROLE_EDITOR`, with CSRF kept enabled.

**Structure:**

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

Spring Boot's Maven BOM manages compatible versions. `spring-boot-starter-validation` is essential for `@Valid` + `@NotBlank` to work. `spring-security-test` provides `user(...)`, `csrf()`, and `@WithMockUser`; without this dependency those security-test imports will not compile.

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

Keep the `@SpringBootApplication` main class simple; do not add arbitrary `@ComponentScan` annotations that could break test slicing.

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

`@NotBlank` rejects null/empty/whitespace-only inputs; `@Size(max=80)` prevents overly long titles. Java records work as DTOs with Jackson in Spring Boot 3.5. `@Valid @RequestBody BookCreateRequest` on the controller triggers validation after deserialization. Never trust a client solely because it sent syntactically valid JSON.

### 5.4. `BookView.java`

~~~java
package com.example.mvcslice;

public record BookView(long id, String title) {
}
~~~

This is the response DTO. With the standard JSON converter, it has two fields: `id` and `title`. Do not return a JPA Entity with lazy-loading/secret fields directly just because JSON tests happen to pass.

### 5.5. `BookNotFoundException.java`

~~~java
package com.example.mvcslice;

public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}
~~~

The service uses a descriptive exception. HTTP status **is not decided in the service**; `BookErrorAdvice` maps the exception to a 404 response.

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

This service **holds data in the JVM**, without using a DB. Having a seeded book `id=1` lets full-context/real HTTP tests exercise the **real service** without Testcontainers. It is not a production persistence design; restarting loses newly created books. In `@WebMvcTest`, the real service **is not scanned** and is replaced by `@MockitoBean`, so the seeded book **does not exist in the mock** unless the test stubs it explicitly.

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

Test cases to cover:
- `GET /api/books/7` → long path variable, service.find(7), JSON body.
- `POST /api/books` → deserialize JSON into record, validate title, trim, service.create, return 201 + Location + JSON.
- `GET non-existent id` → service throws, controller advice maps to 404.
- `POST blank title` → HTTP 400 **before** service.create runs.
- `POST missing auth/role/CSRF` → Security filters block before controller.
- Sending incompatible Content-Type or Accept → 415/406 depending on the request.

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

Spring MVC handles exceptions via handler exception resolvers and `@RestControllerAdvice`. In `@WebMvcTest`, this kind of advice belongs to the **scanned** components, so when a test receives an error from the mock service, the 404 JSON reflects the advice mapping (provided the advice lies under the component-scanned package and is not excluded). For other exceptions such as `MethodArgumentNotValidException`, Spring MVC converts them to 400 by default if no custom handler exists; do not assume the default JSON error body is identical across all Boot versions/configs.

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

        // Do not disable CSRF: POST requires a token in tests/demo.
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

This is a **demo user setup** with `{noop}` plaintext password; **never use this password configuration in production**. Production uses strong password hashing/an identity provider, TLS, security auditing, and proper authorization policies.

**CSRF is intentionally enabled** so the lesson shows `MockMvc` must test real security. REST APIs authenticated via bearer tokens in the Authorization header have a different CSRF policy, but never apply `csrf.disable()` indiscriminately to apps with cookies/Basic credentials that browsers send automatically. `@WebMvcTest` does not necessarily component-scan a custom business/security `@Configuration`, so the slice test will **explicitly `@Import(ApiSecurityConfig.class)`** so the policy is genuinely tested. The full-context app scans this configuration automatically.

## 6. Core Test File: `@WebMvcTest + MockMvc + @MockitoBean`

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

### 6.1. Analyzing Each Test Group

**GET happy path** mocks `BookService.find` to return a DTO, while routing/JSON conversion uses real MVC in the slice. It checks status, Content-Type, and JSON shape, adding `verify(bookService).find(7L)` to confirm the mapping passes the right id.

**404 handling** lets the fake service throw a domain exception, and the real `BookErrorAdvice` maps it to a 404 JSON error. This is a valuable test because clients do not need to know internal Java exceptions.

**POST success** uses **`user("editor").roles("EDITOR")`** and **`csrf()`**. The first creates a mock authenticated principal for the MockMvc request, and the second supplies a valid token for the security filter. The JSON body has spaces, which the controller trims before calling the service. The test asserts `Location` and the `201 Created` body.

**Input validation** uses `@NotBlank`/`@Valid`. HTTP 400 is returned **before** the service is called. `verifyNoInteractions` helps catch validation being bypassed in the controller.

**Security negative cases** verify missing CSRF (403), anonymous with CSRF but unauthenticated (401 via HTTP Basic entry point), and authenticated without required role (403). Specific statuses are designed according to `ApiSecurityConfig` in the lab; applications with form login, OAuth2, custom entry points, or other filters may use 302/401/403 differently. You must test your own app's contract.

**Media type cases** verify 415 from `consumes=application/json` and 406 from `produces=application/json`. If you modify routes/matchers, statuses should be reviewed alongside the API contract—do not treat the example's values as universal for every Spring Boot service.

### 6.2. Does `@WebMvcTest` Automatically Apply Spring Security?

When `spring-boot-starter-security` is on the classpath, the Boot test slice normally includes **security auto-configuration** and `MockMvc` with filters applied. **However, a custom team-written `SecurityFilterChain` is not automatically scanned like any `@Configuration`**; therefore this lesson uses:

~~~java
@WebMvcTest(BookController.class)
@Import(ApiSecurityConfig.class)
~~~

The goal is to test **the exact policy the controller needs**, rather than silently using the default Security chain and misinterpreting results. If you see `GET` unexpectedly requiring login, check which chain was actually loaded in the slice rather than immediately disabling security.

`@AutoConfigureMockMvc(addFilters = false)` can skip filter registration in MockMvc. That is occasionally convenient for isolating mappings, **but those tests no longer prove security/CSRF/filter behavior**. Do not use it as a permanent “fix” for failing 401/403 tests. Check filter ordering and proper security configuration instead of stripping filters.

### 6.3. `@WithMockUser` Can Replace `.with(user(...))`

If you want a method/group of tests to run with a mock principal:

~~~java
@Test
@WithMockUser(username = "editor", roles = "EDITOR")
void example() throws Exception {
    mvc.perform(post("/api/books")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"Example\"}"))
        // Assertions depending on service stub.
        .andExpect(status().isCreated());
}
~~~

This is an **illustrative fragment**, do not copy it directly into the project without stubbing the service: mock `BookService.create` returns null by default, causing an error in the controller. If applied, you must stub `bookService.create("Example")` before `perform`.

`@WithMockUser` creates a mock authentication context; **it does not verify real passwords/OAuth2 signatures/token introspection**. To test login/JWT resource servers accurately against a provider, add dedicated security integration tests. With MockMvc, `user(...)` and `@WithMockUser` require Spring Security test integration/an appropriate filter chain.

## 7. Testing Full Application Context While Still Using MockMvc

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

Difference from slice:
- `@SpringBootTest` loads the **full application context**, including the real `BookService` with seeded book id 1 and the real `ApiSecurityConfig`.
- `@AutoConfigureMockMvc` provides MockMvc for the full context.
- Without `@MockitoBean`, the controller actually calls the runtime-created service.
- **Still does not run a real HTTP server** under the default `webEnvironment=MOCK`. Does not prove Servlet container-level registrations, network timeouts, TLS, reverse proxy, or container error-page handling.

**Important:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` creates a real server, but adding `@AutoConfigureMockMvc` there does not turn `mvc.perform(...)` calls into network calls; they still execute in-process via MockMvc. To test the real network, use an HTTP client calling `localhost:randomPort`.

### 7.1. Full Context and Database

If the production service uses JPA/DataSource, full tests need a proper test DB: Testcontainers, an appropriate embedded DB, or a dedicated test database. Do not assume `@Transactional` on the test will roll back changes from requests sent over a **real HTTP socket**: server/client normally run in different threads/transactions. In-process full-context MockMvc and a real HTTP server have different transaction scopes.

You must decide on fixtures, cleanup/isolation, and reasonable test duration. Mocking the service inside a full test can make it behave more like a slice while still paying full application startup; use it only for clear reasons to avoid building a slow suite that adds no coverage.

## 8. Real HTTP Integration Test: Checking Layers That MockMvc Lacks

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

This test uses **embedded Tomcat with a real socket**, suitable for checking the HTTP connector, Servlet registrations, runtime filters, and real headers. Here it only asserts GET 200 to avoid handling CSRF tokens over a live session. In real client tests for POST with CSRF, generate/tokenize the session according to contract; **do not** disable CSRF just to make curl easier to use.

In practice, real server integration tests also **do not automatically verify Nginx/CDN/k8s ingress** if they are not set up in the test environment. To ensure public route rewrites or TLS/HTTP2, you need staging tests over the real network path or infrastructure-level integration tests.

## 9. Building, Running, and Expected Results

In the `mvc-slice-demo` directory:

~~~bash
java -version
mvn test
mvn clean package
java -jar target/mvc-slice-demo-0.0.1-SNAPSHOT.jar
~~~

**Expected if sources are placed at the right paths and Java/Maven and dependencies are available:** `mvn test` runs the slice group (9 test methods), full-context MockMvc (1 test), and real HTTP (1 test); all are designed to **PASS**. Running on the reader's machine is what confirms reality; do not treat expected outputs as captured logs.

In another terminal, test the public GET against the real app:

~~~bash
curl -i http://127.0.0.1:8080/api/books/1
curl -i http://127.0.0.1:8080/api/books/999
~~~

**Expected semantics:**
- `GET /api/books/1` → 200, JSON body containing `"id":1`, `"title":"Spring MVC Guide"`.
- `GET /api/books/999` → 404, JSON body containing `"code":"BOOK_NOT_FOUND"`, message from the exception.
- HTTP headers like `Date`, `Content-Length`, and encoding may vary by runtime.

A POST via curl **without CSRF**:

~~~bash
curl -i -u editor:demo-only \
  -H 'Content-Type: application/json' \
  -d '{"title":"HTTP Test"}' \
  http://127.0.0.1:8080/api/books
~~~

Expected result is **403 Forbidden**, because the CSRF filter rejects POST requests missing a token even with valid HTTP Basic credentials. **Do not try to force this command to return 201** just to prove the controller: the `MockMvc` test in section 6 uses `.with(csrf())` and `.with(user(...))` to perform the positive test safely. In a real browser/session app, an appropriate backend token issuance and submission flow is required; for stateless bearer-token APIs, CSRF policy can be designed differently according to the threat model.

### 9.1. Running a Single Test Class

~~~bash
mvn -Dtest=BookControllerWebMvcTest test
mvn -Dtest=BookFullContextMockMvcTest test
mvn -Dtest=BookRealHttpTest test
~~~

The Maven commands above use `-Dtest` to filter JUnit classes under Surefire; this may differ when a project uses Gradle or multi-module setups. Running the slice alone will typically be faster than full context, but do not expect fixed millisecond timings because classpath, test context cache, and CI machines vary.

## 10. MockMvc Standalone vs WebApplicationContext Setup

There are **two modes for building MockMvc** (Spring Framework 6.2 official docs), distinct from choosing the Boot test annotation.

### 10.1. `MockMvcBuilders.standaloneSetup(...)`

A near-unit-style test that does not start a Spring Test ApplicationContext:

~~~java
BookService service = org.mockito.Mockito.mock(BookService.class);
BookController controller = new BookController(service);

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new BookErrorAdvice())
        .build();
~~~

This is an **illustrative fragment**, requiring `MockMvc`, `MockMvcBuilders`, and Mockito imports; it does not automatically include SecurityFilterChain/Bean Validation/JSON customizations like a full Spring context. To test security in standalone mode, you must manually configure Spring Security `springSecurity()` and appropriate filters/context. To test validation accurately, you must configure the validator as in production. Therefore, standalone can produce **false positives** if the real pipeline has interceptors, security config, or exception advice omitted from the builder.

**Pros:** very fast, explicit controller and collaborator setup. **Cons:** the more specialized MVC config exists, the more must be wired manually; it will diverge from runtime if a filter/converter is missed.

### 10.2. `MockMvcBuilders.webAppContextSetup(...)`

If you already have a `WebApplicationContext` from Spring TestContext:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
~~~

This is also an **illustrative fragment**; it needs `MockMvcBuilders`, `WebApplicationContext`, and `MockMvc` imports. It uses the MVC configuration loaded by the context, reflecting Spring MVC config more accurately than standalone. **Spring Boot `@WebMvcTest` already creates `MockMvc`**, so you normally do not need to rebuild it manually; creating an extra builder might inadvertently skip Boot customizers/filters.

For manual Spring Security MockMvc setup, Spring Security docs typically use:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
~~~

`springSecurity()` requires a static import from `SecurityMockMvcConfigurers`; `spring-security-test` must be on the test classpath. In the Boot `@WebMvcTest` example, auto-configured MockMvc already handles Security integration so tests work directly.

### 10.3. How Does Context Caching Affect Tests?

Spring TestContext caches ApplicationContexts across test classes with compatible configurations. `@MockitoBean` definitions, `@Import`, active profiles, properties, and test customizers can alter the test context cache key, leading to multiple contexts being created. Do not break the context cache by putting `@DirtiesContext` on every test without reason.

A test that mutates static globals or shared DB state can also cause order-dependent failures even when using the context cache. Controller tests with mock services should be independent; do not let state naturally “leak” between test methods.

## 11. When Security Is Present, Test the Real Protection Layer

### 11.1. Do Not Remove Security Just to Turn Tests Green

Common mistakes:
- `GET` is public in the app, yet `@WebMvcTest` returns 401: custom `SecurityFilterChain` was not imported or the mock context uses default security.
- `POST` returns 403: could be **missing CSRF**, not necessarily a missing role.
- `POST` with `@WithMockUser` still returns 403: a mock principal does not automatically generate a CSRF token; check `csrf()`.
- `.with(user("editor"))` gets 403: the user only has default `ROLE_USER`; `hasRole("EDITOR")` needs `roles("EDITOR")`.
- `@AutoConfigureMockMvc(addFilters=false)` lets POST get 201 even though the real app returns 403: the security test becomes bogus.
- `@WithMockUser` passes, yet Basic credentials/JWT fail on the real server: the annotation **does not exercise authentication providers/token decoders**.

**Do not** change the policy to `anyRequest().permitAll()` to “fix tests” if production needs authorization. Write tests for **anonymous, authenticated, insufficient role, valid/invalid CSRF**, plus some integration tests for real authentication.

### 11.2. About 401 and 403

In the demo:
- Missing auth but valid CSRF present → HTTP Basic entry point may return **401 Unauthorized**.
- Authenticated but insufficient role → **403 Forbidden**.
- Authenticated with right role but missing CSRF on POST → **403 Forbidden**.
- Missing CSRF and missing auth → outcome depends on security filter order, often **403** before reaching authentication, so when testing 401 auth specifically, **supply valid CSRF in the test**.

With form login, an unauthenticated request may redirect `302` instead of returning 401. With an OAuth2 resource server, status/headers may differ. Assertions must reflect the **actual security chain**.

### 11.3. CORS Preflight, CSRF, Cookies

Browser CORS preflight is an `OPTIONS` request and typically does not carry authenticated session cookies like the main request. If the app configures `http.cors(...)` or `CorsFilter`/`WebMvcConfigurer#addCorsMappings`, the slice test must include the real policy; you can use MockMvc:

~~~java
mvc.perform(options("/api/books")
        .header("Origin", "https://ui.example.test")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isOk());
~~~

**This is only an illustrative fragment**: the current project **has not configured CORS**, so **do not** copy this 200 assertion as a passing test. You need to add `CorsConfigurationSource`/MVC CORS config and test allowed/disallowed origins. Do not treat CORS as authorization; it does not stop curl/non-browser HTTP clients. When clients use cookies, align SameSite, CSRF, and session policy.

### 11.4. Mock SecurityContext vs Real Auth

`@WithMockUser`/`user()` creates a fake Authentication at the test boundary. If the controller relies on `Principal` or `@AuthenticationPrincipal`, the test can supply user/roles as needed; however, this **does not** verify password hashes, OAuth2 `JwtDecoder`, JWK rotation, token expiry, or reverse-proxy trusted headers. Those require tests at the security component/integration layer.

## 12. Important Limitations of MockMvc Regarding the Web Runtime

### 12.1. Servlet Container-Level Behavior

MockMvc relies on mock Servlet APIs, so it **has no real HTTP socket**, TLS handshake, container connection timeout, HTTP/2 multiplexing, proxy buffering, actual gateway compression, or network redirect hops. If the app uses a Jersey `ServletContainer` at `/api/*` and MVC `DispatcherServlet` at `/`, MockMvc only talks to Spring MVC; it **does not prove** the Servlet container actually selects the right servlet mapping.

Similarly, a `Filter` bean may be auto-registered into the real Servlet container by Boot, yet standalone MockMvc tests will not see that registration. Test with `@SpringBootTest(RANDOM_PORT)`/embedded Tomcat when that coverage is required.

### 12.2. 404/Error Pages and Error Dispatch

MockMvc can verify that a controller throws an exception and `@ControllerAdvice` converts it to 404/JSON. However, **container error pages**, Servlet `ERROR` dispatch, and Boot's `/error` pipeline at runtime may behave differently. Spring Boot docs note that MockMvc cannot directly verify error pages rendered by container support.

If a test only sees `NoHandlerFoundException` or `NoResourceFoundException` in a slice, do not assume the byte-level error body on a real HTTP server is identical. Check with a real client if the 404/error page contract matters.

### 12.3. JSP, Redirects, and Rendered HTML

MockMvc can assert logical views, `forwardedUrl`, or redirect `Location`, but it **does not execute real JSP** because JSP requires container forwarding/rendering. Thymeleaf/Freemarker work differently and can render HTML inside MockMvc if the template engine/config is loaded in the context. For JSP, a container integration test is needed to inspect the final HTML.

If a controller returns `"home"` and you assert `view().name("home")`, that does not automatically guarantee the real template exists, static resources are served at the right URL, or the client receives CSS.

### 12.4. Multipart and Uploads

MockMvc provides a request builder for multipart; it verifies the controller receives `MultipartFile` and checks validation/mapping, but it does not prove full multipart parsing of the real container, upload size limits, temp disk behavior, reverse proxy body size limits, or antivirus/storage integration. Test via real HTTP with small and large files to check real limits.

### 12.5. Async Endpoints and Streaming

Spring MVC async (`Callable`, `DeferredResult`, `SseEmitter`) has a different lifecycle than synchronous controllers. With `MockMvc`, asynchronous requests can be tested with:

~~~java
MvcResult result = mvc.perform(get("/async"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk());
~~~

**This is an illustrative fragment** requiring `MvcResult`, static `request`/`asyncDispatch` imports, and an `/async` controller returning a real async type. The demo project only has sync endpoints, so do not copy and run this directly. In real streaming/SSE, you must also test client disconnect, flushing, proxy buffering, and timeouts on a real server; MockMvc does not fully simulate long-lived network connections.

### 12.6. Static Resources and MIME

`@WebMvcTest` may load MVC static handler infrastructure via auto-config, but you should not take a controller-targeted slice as proof that classpath assets were packaged into the executable JAR, or that Jersey/other Servlet mappings do not shadow static paths. Use a JAR/real HTTP integration test if you need to check `/index.html`, `/assets/app.js`, or caching/ETag via Tomcat/nginx.

## 13. Validation, Exception Contracts, and JSON Precision

### 13.1. An Error Response Is More Than Just a Status Code

For public API endpoints, assert a stable error contract:
- 400 when `@Valid` fails or JSON body cannot be parsed;
- 404 when a business resource does not exist;
- 415/406 when content negotiation is wrong;
- 401/403 when auth/csrf/role fails;
- 500 only for unexpected errors; avoid exposing internal stack traces.

In the example, `BookErrorAdvice` defines JSON `{"code":"BOOK_NOT_FOUND","message":"Book 99 not found"}`. There is no need to assert exact whitespace/field ordering. Do not assert the error body for validation 400 if you have not defined the output shape in `@ControllerAdvice`; Spring Boot 3.5 default error handling may vary when versions/properties change.

### 13.2. Testing Deserialization + Converters

Because the DTO is a Java record, Jackson must deserialize the JSON body into `BookCreateRequest`. A passing `POST` test verifying `create("Effective MockMvc")` proves the body bound, trimmed, and passed validation.

Additional tests you can add:
- request missing `title` → 400 via `@NotBlank`;
- `title` longer than 80 characters → 400;
- malformed JSON syntax → 400 via `HttpMessageNotReadableException`;
- non-numeric `id` in path variable → 400 (conversion failure);
- unsupported media type → 415;
- unacceptable Accept → 406;
- wrong HTTP method → 405 if mapping/path and security allow it through to MVC to return 405.

**Note:** security may return 403 before MVC can report 405/415/400; when testing validation/content type, provide proper auth+CSRF to isolate the cause.

### 13.3. Do Not Mock the Very Thing Under Test

If you mock `Validator`, `ObjectMapper`, `HandlerMapping`, or `DispatcherServlet` in a slice without reason, assertions may no longer prove MVC infrastructure. Normally mock only the **service boundary**: `BookService`, event publishers, or remote clients, letting controller/advice/converters/validator run for real.

If a controller is just a thin layer calling a service, focus on testing the HTTP contract; business service logic is tested separately with unit/integration tests and an appropriate database.

## 14. Risk-Driven Test Suite Design

A sensible strategy:

| Risk | First Test to Use | Supplement When Needed |
| --- | --- | --- |
| Wrong URL/method/path variables | `@WebMvcTest` + MockMvc | Real HTTP smoke |
| Wrong JSON body/headers | `@WebMvcTest` + MockMvc | Full context if custom ObjectMapper |
| `@Valid` not firing | `@WebMvcTest` + validation dependency | API contract integration |
| Wrong 404 exception mapping | `@WebMvcTest` with mock service throws | Full context if multiple advices |
| Wrong CSRF/roles in MVC | `@WebMvcTest` + real SecurityFilterChain import | Security integration/auth provider test |
| Faulty business service | Service unit test with appropriate mocks | Repository/database integration |
| JPA/transaction bugs | `@DataJpaTest` / testcontainers | Full application integration |
| Colliding custom filters/Servlet auto-registration | `@SpringBootTest(RANDOM_PORT)` | Container/deployment staging |
| Tomcat vs Jersey mapping, static 404 | Real embedded server test | Packaged JAR/staging |
| Proxy/path rewrite/TLS | Staging end-to-end HTTP | Infrastructure-specific tests |
| SSE/WebSocket disconnect/idle behavior | Protocol-level tests | Real proxy/load tests |
| Invalid security identity provider/JWT | Security integration with real-like token decoder | Staging identity provider contract |

Every case should place assertions reflecting the **target under test**, not merely to chase percentage coverage. For example, 100% passing `@WebMvcTest` methods **do not prove** production DB/HTTP gateway integration.

### 14.1. Pre-Merge Practices

- Run fast slice tests on every commit.
- Have a few `@SpringBootTest + @AutoConfigureMockMvc` tests for wiring/application security config.
- Have real HTTP integration tests for critical routes and at least one negative case like 404/401.
- When the product uses reverse proxies, CORS, large multipart uploads, static content, or custom servlet registrations, add staging tests over the real path.
- For DB/service dependencies, use deterministic fixtures/testcontainers and clean up between tests.
- Do not rely on JUnit execution order or leftover data from a previous test.
- Do not disable security or CSRF just to get green builds.
- Limit context variations to reduce startup cost/cache misses.
- When changing the API contract, update assertions, REST Docs/OpenAPI, and consumer contract tests accordingly.

## 15. Common Errors and Fixes

| Symptom | Likely Explanation | Resolution |
| --- | --- | --- |
| `@WebMvcTest` fails to start context due to missing `BookService` | Service excluded from slice | `@MockitoBean BookService` or explicit test bean |
| `@Mock BookService` present yet controller still lacks bean | Mockito field does not register a Spring bean | Use `@MockitoBean` |
| `@MockBean` deprecation warning in Boot 3.5 | Legacy annotation | Use Spring Framework `@MockitoBean` |
| Two beans of type `BookService`, `@MockitoBean` ambiguous | Unclear target | Use appropriate bean name/qualifier |
| Slice unexpectedly pulls in database | Custom component scan/`@Import` too broad | Separate configs, preserve Boot type exclusion |
| Public GET returns 401 in slice | Custom `SecurityFilterChain` not imported, default policy active | `@Import(ApiSecurityConfig.class)` for needed part |
| POST returns 403 despite `@WithMockUser` | Missing CSRF or missing role | `.with(csrf())` and appropriate role |
| Unauthenticated POST missing CSRF expected 401 | `CsrfFilter` may return 403 before auth | Provide valid csrf when testing auth specifically |
| POST succeeds after `addFilters=false` | Security filters removed from MockMvc | Do not use as proof of security |
| Null JSON body/missing fields | Unstubbed mock service, converter/DTO mismatch | Stub collaborator, inspect status/content body |
| `@WithMockUser` passes yet real token fails | Auth provider/decoder not tested | Test login/JWT separately |
| `ControllerAdvice` 404 not applied | Advice outside slice or excluded | Check scan/package, `@Import` advice if needed |
| JSON 400 body differs from expected | No custom error contract | Assert status or define advice |
| `@Valid` does not produce 400 | Missing validation starter or annotation on `@RequestBody` | Add validation starter and `@Valid` |
| 415 because POST lacks Content-Type | Converter/consumes mismatch | Set `contentType(APPLICATION_JSON)` |
| 406 due to wrong Accept | Controller produces JSON yet Accept is text/plain | Set `accept(APPLICATION_JSON)` |
| MockMvc passes yet real HTTP returns 404 | Servlet mapping/proxy rewrite/Jersey/container differs | RANDOM_PORT and staging test |
| MockMvc does not render JSP | JSP needs real container forward | Real HTTP test |
| File upload test passes yet prod 413/500 | Proxy/body/temp-disk limits | Real upload tests per env |
| Tests slow like full app despite slice | Full configs imported, too many controllers, context cache misses | Narrow `@WebMvcTest` scope and mocks |
| Multiple `@...Test` slices on same class | Slices are not composable that way | Pick one slice or `@SpringBootTest` |
| Tests share data/leak state | Static globals/DB fixtures/context cache | Isolate fixtures, reset state, selective `@DirtiesContext` |
| `@SpringBootTest(RANDOM_PORT)` yet using MockMvc to test sockets | MockMvc does not go over network | Use `RestClient`/`WebTestClient` against random port |
| Async assertion fails because response incomplete | Missing `asyncDispatch` | `request().asyncStarted()` and `asyncDispatch` |
| Exception test produces 500 instead of 404 | Wrong domain exception class/advice package | Check `@ExceptionHandler` + mock throw |
| Static file packaged yet MockMvc misses Jersey swallowing route | No real container selection | Real HTTP tests/JAR |

## 16. Self-Check Exercises

1. Does `@WebMvcTest` start embedded Tomcat? Why?
2. Does `MockMvc` process requests with real HTTP sockets or mock Servlet APIs?
3. When choosing `@WebMvcTest(BookController.class)`, is `@Service BookService` automatically scanned?
4. How does `@MockitoBean` differ from `@Mock` and `@MockBean`?
5. Why should you not mock `DispatcherServlet`/Jackson themselves if the goal is to test MVC?
6. In the lesson, why does `@Import(ApiSecurityConfig.class)` appear on the slice test?
7. If a POST returns 403, how do you separate a CSRF error from a role error?
8. Why does `@WithMockUser` not prove JWT decoding or password hashing is correct?
9. How does `@AutoConfigureMockMvc(addFilters=false)` render security tests meaningless?
10. How does `@Valid @RequestBody` differ from merely deserializing JSON?
11. Why should a 400 validation test call `verifyNoInteractions(bookService)`?
12. When the service is mocked, does a passing test prove transactions/DB are right?
13. How does `GET /api/books/999` in the slice use an exception to test advice?
14. How do the `contentType` request header and `accept` header differ?
15. How do status 415 and 406 differ in root cause?
16. How does `@SpringBootTest + @AutoConfigureMockMvc` differ from `@WebMvcTest` in context?
17. How does `@SpringBootTest(RANDOM_PORT)` differ from `@SpringBootTest(MOCK)`?
18. In `BookRealHttpTest`, why does calling `RestClient.create()` make sense?
19. For JSP, does MockMvc render real HTML?
20. Why does a MockMvc test not prove a Jersey Servlet mapping `/api/*`?
21. If an app uses a custom Jackson `ObjectMapper` bean outside the MVC slice, what extra test is needed?
22. Why should you not put `@WebMvcTest` and `@DataJpaTest` on the same class?
23. What is needed to make a custom CORS preflight test genuinely reliable?
24. Can `@RestControllerAdvice` be included in `@WebMvcTest`?
25. If an async endpoint returns `DeferredResult`, what are the two MockMvc test steps?
26. Why do `RANDOM_PORT` HTTP tests need explicit DB fixtures/cleanup?
27. When upgrading from Boot 3.5 to Boot 4.x, why review test annotation packages/dependencies?
28. If a slice runs slowly, what factors affect the Spring TestContext cache?
29. Should you change a policy to `permitAll()` to “fix” a suite getting 401/403?
30. Which test helps verify container error dispatch or reverse proxy rewrites work?

**Core answers:** (1) No, mock environment. (2) Mock Servlet objects inside the JVM. (3) No; use `@MockitoBean`. (4) Mockito bean in Spring context; `@Mock` is a field, legacy `@MockBean` is deprecated. (5) Real infrastructure needs testing. (6) Loads custom security policy for the slice. (7) Supply csrf then vary auth/role; test all 3 cases. (8) Uses mock authentication, does not verify real tokens/passwords. (9) Filters are skipped. (10) Triggers Bean Validation. (11) Ensures rejection happens before business logic. (12) No. (13) Mock service `thenThrow` and assert 404 JSON. (14) Request body media type vs client response preference. (15) Unsupported request media vs unacceptable response media. (16) Full context vs web slice. (17) Real server vs mock HTTP. (18) It is a real HTTP client calling the localhost socket, needing no auto-tracing for the test. (19) No for JSP container forwarding. (20) Servlet mapping sits outside MockMvc. (21) Full-context/real HTTP config test. (22) Combining slices is unsupported. (23) Load the real policy and assert origins/headers/security, plus browser/staging tests. (24) Yes. (25) `asyncStarted` then `asyncDispatch`. (26) Real HTTP transactions are separate from the test thread. (27) Test modules/packages changed. (28) Mocks/imports/profiles/properties/context dirtiness. (29) No. (30) `RANDOM_PORT`/staging proxy test.

## 17. Official Documentation Sources

- **Spring Boot 3.5 – Testing Spring Boot Applications**, `@WebMvcTest`, `@MockitoBean`, MockMvc, and full-context tests: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Boot 3.5 – Test Slices / @WebMvcTest auto-configurations**: https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- **Spring Boot 3.5 – How-to: Testing**, security integration and structuring configuration for slice tests: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- **Spring Framework 6.2 – Bean Overriding in Tests**, `@MockitoBean`, `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- **Spring Framework 6.2 – MockMvc Setup Options**, standalone vs webAppContext: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html
- **Spring Framework 6.2 – MockMvc vs End-to-End Tests**, Servlet API mocks, JSP/container limitations: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/vs-end-to-end-integration-tests.html
- **Spring Framework 6.2 – MockMvc Async Requests**: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html
- **Spring Security 6.5 – MockMvc testing with user and CSRF**: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html and https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- **Spring Boot 3.5.16 release/OSS support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/