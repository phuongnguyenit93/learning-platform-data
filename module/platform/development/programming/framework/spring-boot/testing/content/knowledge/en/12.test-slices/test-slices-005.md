# Distinguishing Test Slice Configuration from a Full ApplicationContext in Spring Boot

> **Module:** Spring Boot – testing  
> **Group:** Test slice  
> **Lesson:** Distinguishing slice configuration from a full application context  
> **Goal:** Understand accurately which beans and auto-configurations Spring Boot creates in a slice test, how it differs from `@SpringBootTest`, how to add dependencies to a slice without accidentally loading the whole application, and how to choose the right test level, profiles, database, and HTTP mocking.

## 1. Core Idea: A "Slice" Is ApplicationContext Scope, Not Just a Shorter Test

Spring Boot lets you run tests using two different strategies:

- **Test slice** uses an annotation such as `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`, or `@WebFluxTest`. Spring Boot configures only the components relevant to **one functional slice** under test: for example, controllers and MVC infrastructure, or entities and JPA repositories. Service/repository/HTTP client beans outside that slice **are normally not component-scanned into the context**.
- **Full context test** uses `@SpringBootTest` to build the application via the `SpringApplication` mechanism, applying the primary configuration, component scanning, and auto-configurations according to classpath, properties, profiles, and active conditions. It tests coordination across more real bean layers, but typically starts heavier and may require external infrastructure configuration.

**Two things must not be equated:**

1. **"Full application context" does not mean everything in production is running.** `@SpringBootTest` still depends on profiles, conditional beans, classpath, and test configuration. If a test uses mocks, a fake DB, or stubs, those parts do not become production integration.
2. **"Slice" does not mean every dependency is mocked.** For instance, `@WebMvcTest` still creates real MVC infrastructure (handler mappings, JSON converters, controller advice, appropriate filters). It simply does not auto-load most business services and repositories.

A helpful mental model:

```text
                SPRING BOOT APPLICATION
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
  | MVC            |     | Entity + JPA   |     | Eligible beans          |
  | Real controller|     | Real repository|     | across the whole app    |
  | Mock service * |     | Test DB        |     | per profile/config      |
  +----------------+     +----------------+     +-------------------------+
       * Added explicitly with @MockitoBean
```

The "slice = one part" illustration is a **mental diagram**, not the exact algorithm of every auto-configuration. Which components are loaded depends on the specific annotation and Spring Boot version in use.

## 2. Quick Comparison of Test Annotations

| Choice | Primary beans/configurations loaded | Usually not loaded | Main tools | Best suited for |
| --- | --- | --- | --- | --- |
| `@WebMvcTest(BookController.class)` | MVC infrastructure, specified controller, MVC-related components, `MockMvc` | Business `@Service`, arbitrary repositories | `MockMvc`, `@MockitoBean` | Mapping, binding, validation, JSON/status responses |
| `@WebFluxTest(Controller.class)` | Reactive web controller and WebFlux-related components | Services/repositories outside the reactive web slice | `WebTestClient` bound to context | Reactive controller APIs |
| `@DataJpaTest` | `@Entity`, JPA repositories, `EntityManager`, transactions, test DataSource | MVC controllers, regular business services | `TestEntityManager`, repositories | Entity mapping, queries, constraints |
| `@JdbcTest` | `DataSource`, `JdbcTemplate`, transactions | Services, MVC, unselected Spring Data repositories | `JdbcTemplate` | Plain SQL/JDBC |
| `@JsonTest` | JSON mapper, JSON modules/components, and matching testers | Controllers, business services, data layer | `JacksonTester`/JSON helpers | Serialization/deserialization contracts |
| `@RestClientTest(Client.class)` | Specified client, JSON support, client builders, `MockRestServiceServer` | All other services/repositories/controllers | In-memory HTTP mock server | Outbound REST client requests/responses |
| `@SpringBootTest` | Application configuration, component scan, eligible auto-configurations | No "slice" exclusion list; still subject to conditions/profiles | Spring beans + extra test utilities | Multi-layer wiring/integration, application behavior |

**Key point:** `@*Test` annotations do not merely change how many classes are scanned; they also restrict or select **auto-configurations** suited to the purpose. Do not read the table as "only one single bean type exists."

### 2.1. Test Slices Still Use Spring TestContext

`@WebMvcTest` and `@DataJpaTest` are not like plain unit tests calling `new MyService(...)`. They still initialize a Spring `ApplicationContext` through Spring Boot's test bootstrapper, handling dependency injection, test properties, and caching. Therefore, a slice test can fail due to bean configuration, profiles, or converters despite its narrow scope.

`@SpringBootTest` builds a broad application context; it does not necessarily start an embedded HTTP server. **The default is `webEnvironment = MOCK`**: a simulated web environment that **does not open a listening HTTP port**. When a real HTTP socket is needed, choose `RANDOM_PORT` or `DEFINED_PORT`.

### 2.2. Test Slices Do Not Automatically Create Mockito Mocks for Services

If a controller has a constructor:

```java
public BookController(BookService service) {
    this.service = service;
}
```

then `@WebMvcTest(BookController.class)` normally **does not load `BookService` just because the controller needs it**. Missing that dependency, the context fails to start unless a replacement bean is provided. Direct approach:

```java
@MockitoBean
BookService service;
```

Spring Framework 6.2 and Spring Boot 3.5 provide `@MockitoBean` to create or override a bean in the test context. It differs from plain Mockito `@Mock`: `@Mock` creates a Java mock in the test class and **does not register the mock in the Spring bean registry**. Older Spring Boot versions had `@MockBean`; in Boot 3.4+ that annotation is deprecated, so Boot 3.5 examples prefer `@MockitoBean`.

**Warning:** using `@MockitoBean` inside `@SpringBootTest` also replaces the real bean with a mock. So never assume a full context executes all real logic if the test itself mocked a key piece.

## 3. How Do Slices Restrict Scanning and Auto-Configuration?

In a standard project with `@SpringBootApplication` in the root package, Spring Boot searches upward from the test's package for the primary configuration, then applies the corresponding test bootstrap mechanism.

### 3.1. With `@WebMvcTest`

Spring Boot focuses on web MVC: `@Controller`, `@ControllerAdvice`, converters, `@JsonComponent`, `Filter`, `HandlerInterceptor`, `WebMvcConfigurer`, and supported MVC configuration types. It configures `MockMvc`, conversion/JSON, and related MVC test support.

Regular business `@Service`, `@Repository`, and `@Component` beans **are not scanned by default**. If a controller has a constructor dependency on a service, you must supply a mock/fake or explicitly import the real bean.

`@WebMvcTest(BookController.class)` also **restricts controllers to the specified scope**. This prevents one mapping test from being affected by every endpoint in the application.

If `spring-boot-starter-security` is present, the web slice can load security filters and return 401/403 without authentication/CSRF tokens. That is behavior to understand and test; **do not disable filters arbitrarily** just to make tests pass. Use Spring Security test helpers such as `@WithMockUser`/`csrf()` when security contracts are in scope. The sample project below does not declare Spring Security.

### 3.2. With `@DataJpaTest`

The JPA slice scans entities and Spring Data JPA repositories, loading ORM/JPA, DataSource, transaction support, and test utilities. If an embedded DB like H2 is on the test classpath, Boot typically configures an embedded database instead of the regular DataSource. Business `@Service` beans, MVC controllers, and general components are not scanned as in a full context.

By default, `@DataJpaTest` is transactional and rolls back after each test method. This is an advantage when testing persistence, **not** a guarantee that every kind of DB/async/transaction access runs inside the test transaction.

If `@AutoConfigureTestDatabase(replace = NONE)` is used, the test can use the configured DataSource. Therefore, verify that the URL/credentials point to a **test database**, never production. When testing real PostgreSQL dialects, use Testcontainers or a controlled sandbox database instead of relying on H2 for vendor-specific SQL.

### 3.3. With `@JsonTest` and `@RestClientTest`

`@JsonTest` loads mappers and related JSON modules/components without an HTTP server or database. Testing DTOs/serializers catches formatting bugs without starting a broad business context.

`@RestClientTest(MyClient.class)` focuses on outbound HTTP clients; Spring Boot configures JSON support, `RestTemplateBuilder`, `RestClient.Builder`, and `MockRestServiceServer`. In tests, HTTP requests are intercepted internally rather than hitting production APIs by default. However, if the client instantiates `new HttpClient` bypassing the test-configured builders, the mock server may **not** intercept those requests; design clients to accept injected dependencies.

### 3.4. Why Do Some Beans Still Enter a Slice?

Scanning rules restrict **component types**, while user-imported configurations, `@Bean` declarations in configurations, or custom component scanning can alter the bean graph:

- `@Import(SomeConfiguration.class)`: explicitly brings additional configuration/beans into the slice.
- `@TestConfiguration`: adds test-specific beans.
- `@EnableConfigurationProperties`: loads `@ConfigurationProperties` needed by the slice.
- A custom `@ComponentScan` placed directly on the main `@SpringBootApplication` can **disable the default exclude filters** used by slices, causing tests to scan extra beans unintentionally.
- `@Bean` methods created by custom configurations do not necessarily undergo the same filter as `@Component` stereotype scanning, which can pull in unexpected configurations.
- Conditional auto-configuration depends on classpath/profiles/properties and import chains; do not guess solely from the annotation name.

If a slice suddenly demands a database/email/Kafka bean, before switching everything to `@SpringBootTest`, inspect **which bean was imported or scanned** and how the primary configuration is being discovered.

## 4. Java 17 + Spring Boot 3.5 Sample Project for Direct Comparison

This example is a **runnable Maven project** featuring an in-memory book catalog application. It requires no external database, secrets, Docker, or external network to run tests (aside from Maven downloading dependencies if not cached).

Four test types operate on the exact same source code:

1. MVC slice: `@WebMvcTest` + `@MockitoBean`.
2. Full application context: `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc`.
3. JSON slice: `@JsonTest` + `JacksonTester`.
4. Full context **plus** a real HTTP server: `@SpringBootTest(RANDOM_PORT)`.

This lets you observe that **context loading scope** and **HTTP transport** are two separate dimensions.

### 4.1. File Structure

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

Each `public` type is placed in its matching filename under `package com.example.contextdemo`. Do not put multiple `package`s into the same file. `BookCatalog` carries `@Repository` but holds only in-memory data without JPA; JPA is covered separately in section 8 so this project does not accidentally require a DB in full-context tests.

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

`spring-boot-starter-web` provides Spring MVC and Jackson, making `@WebMvcTest`, `@JsonTest`, MockMvc, and ObjectMapper available. `spring-boot-starter-test` provides JUnit Jupiter, Mockito, AssertJ, and Spring Boot test auto-configuration. With Spring Boot parent, Maven Surefire/JUnit Platform and compatible dependency versions are managed.

This is **one project**; do not add `spring-boot-starter-data-jpa` to this project unless you deliberately extend it and configure a test DataSource.

### 4.3. Application Code: Controller → Service → Catalog

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

**Contract data for the example:**

| Request | Case | Expected outcome |
| --- | --- | --- |
| `GET /api/books/book-101` | Book exists in catalog | 200; JSON with `code=book-101`, `title=Spring Testing`, `copies=7` |
| `GET /api/books/book-202` | Another book | 200; JSON with `title=Java 17` |
| `GET /api/books/missing` | Not found | HTTP 404 via `@ResponseStatus` |

There is no external database or network API. This ensures the sample project's full context loads real beans without production secrets/fixtures.

### 4.4. Test Configuration File

```yaml
# src/test/resources/application-test.yml
demo:
  safety-marker: isolated-test
```

All test contexts below use `@ActiveProfiles("test")`. This marker proves profile-specific test configuration is loaded; it **does not turn a test into a slice** and does not create mocks. Both `@SpringBootTest` and slices can use active profiles/properties, differing only in which components are bootstrapped.

### 4.5. Test A: MVC Slice Without Loading Real Repository

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

**Meaning of the test:**

- Controller, Spring MVC mapping, JSON serialization, and `MockMvc` are real test-slice components.
- `BookService` **is a Mockito mock explicitly provided** via `@MockitoBean`. It returns `"From MVC Stub"` rather than using real catalog data.
- `BookCatalog` is an `@Repository`, so it is **not in the default MVC slice**. The bean-graph assertion explicitly confirms this in the sample project.
- `@ActiveProfiles("test")` loads test configuration; **it does not load `BookCatalog`**.
- The 200 status and matching JSON show the controller accepts the request and builds the right response **from the mock service's data**. The test **does not prove** that `BookService` actually finds books properly or invokes the repository properly.
- `BookMissingException` uses `@ResponseStatus(NOT_FOUND)`, so the test can confirm Spring MVC translates that exception into status 404.

**Do not assign the goal "find real books using the repository" to this test**, because the repository is not in the tested context. When you need to verify controller + service + repository working together, see Test B.

### 4.6. Test B: `@SpringBootTest` Loads Real Service/Repository Beans

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

**How does it differ from the MVC slice?**

- `BookService` is the real `@Service`, created by Spring and injected with the real `BookCatalog`.
- `BookCatalog` is the real `@Repository` in the sample app, not stubbed by Mockito.
- `MockMvc` is still used thanks to `@AutoConfigureMockMvc`; requests go through **mock servlet request/response objects**, without opening a listening TCP port.
- The `title` field of `book-101` must be `"Spring Testing"` from the catalog, unlike `"From MVC Stub"` decided by the slice test.
- Both test methods protect the collaboration of controller, service, repository, and MVC mapping inside a broad Spring context.

**Crucial distinction:** "Full context" here means the **application's full bean graph**, **not a real HTTP server**. If you need to test socket ports/HTTP clients, see Test D; those two axes are independent.

### 4.7. Test C: `@JsonTest` Tests Only the JSON Contract

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

**Meaning:**

- `@JsonTest` creates the appropriate mapper/`JacksonTester` without calling controllers or services.
- The test verifies that the `Book` record serializes/deserializes with the business values we want to protect.
- It does not prove the endpoint works and requires no embedded HTTP server.
- A failing JSON test is not necessarily a controller or repository bug; a narrow test layer isolates failures quickly.

In a real application, if a custom Jackson module is part of the contract, place the JSON configuration within `@JsonTest`'s scan scope or `@Import` it explicitly, rather than forcing `@SpringBootTest` for all serializer tests.

### 4.8. Test D: Full Context with a Real HTTP Server

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

**Distinguishing three important cases:**

- `BookMvcSliceTest`: MVC slice, mocked service, no catalog; MockMvc handles requests in-process.
- `BookFullContextTest`: full context, real service and catalog; MockMvc still handles requests internally.
- `BookHttpServerTest`: full context and a **real** embedded HTTP server on a random port; Java `HttpClient` calls over a loopback socket.

Context "fullness" is **separate** from deciding "whether to start a real HTTP server." Both `@WebMvcTest` and `@SpringBootTest(MOCK)` skip starting an embedded listener, yet their bean graphs differ substantially.

### 4.9. Running and Comparing Yourself

Requires JDK 17+ and Maven; place the structure above in the proper directories. From the directory containing `pom.xml`:

```bash
java -version
mvn -version

# Run all test classes in the sample:
mvn test

# Run each context type individually:
mvn -Dtest=BookMvcSliceTest test
mvn -Dtest=BookFullContextTest test
mvn -Dtest=BookJsonSliceTest test
mvn -Dtest=BookHttpServerTest test
```

**Expectations for the exact sample code:**

| Test class | `@Test` count | Real service/catalog beans? | Requests over network? | Primary oracle |
| --- | ---: | --- | --- | --- |
| `BookMvcSliceTest` | 2 | No; service is mocked, catalog absent | No | JSON from stub, 404 mapping |
| `BookFullContextTest` | 2 | Yes | No, uses MockMvc | JSON from real catalog, 404 |
| `BookJsonSliceTest` | 1 | No | No | JSON mapper round-trip |
| `BookHttpServerTest` | 1 | Yes | Yes, loopback HTTP | Status 200, JSON from real app |

**Total is 6 test methods** across the four classes if no other tests exist: 2 + 2 + 1 + 1 = 6. Maven/Surefire may print varying test counts, timings, and logs depending on OS, cache, Java version, and execution order; **no fixed stdout is guaranteed**. The `RANDOM_PORT` port is dynamic; do not hard-code 8080.

If `BookMvcSliceTest` fails to start due to a missing dependency after you edit the code, see section 6 rather than immediately switching to `@SpringBootTest`.

## 5. Slices and Full Contexts Differ Across Three Configuration Layers

### 5.1. Component Scanning

A full context uses `@SpringBootApplication` at the root package to scan eligible stereotype components: `@Controller`, `@Service`, `@Repository`, `@Component`, and related configurations. A slice narrows the bean types scanned according to the annotation's goal.

In the sample project:

| Bean/object | MVC slice | JSON slice | Full context |
| --- | --- | --- | --- |
| `BookController` | Yes | No | Yes |
| `BookService` | Yes, **Mockito mock** declared by test | No | Yes, **real bean** |
| `BookCatalog` | No | No | Yes, **real bean** |
| `MockMvc` | Yes, auto-configured | No | Yes when `@AutoConfigureMockMvc` is added |
| `JacksonTester<Book>` | Not provided to this test by default | Yes | Not automatically provided like JSON slice |
| Jackson JSON conversion | Yes | Yes | Yes, from web starter |
| Embedded HTTP listener | No | No | No in `MOCK`; yes in `RANDOM_PORT` |

The table above describes the **specific sample project and test annotations**. Do not treat it as universal across projects with custom imports or configurations.

### 5.2. Auto-Configuration

In a full context, Spring Boot evaluates auto-configuration classes eligible via `spring-boot-starter-*`, existing beans, feature flags, and properties. For example, adding Data JPA enables datasource and JPA auto-configurations, bringing database requirements along.

A slice test **does not activate all auto-configuration like the full application**; it imports the set of auto-configurations serving that test slice. This set can change between Spring Boot release lines, and the official list is in the "Test Auto-configuration Annotations" Appendix.

Consequently:

- A bean type being on the classpath **does not mean** it is always present in a slice.
- An unselected auto-configuration can leave an expected dependency uncreated.
- When a slice test requires a custom dependency, manually importing it is a deliberate choice; do not assume it is default behavior across every test with the same annotation.
- When multiple real layers need to be tested together, use a full context instead of repeatedly expanding a slice until it rivals a full application.

### 5.3. Application Properties and Active Profiles

`@ActiveProfiles("test")`, `@TestPropertySource`, `@SpringBootTest(properties = "...")`, and `@DynamicPropertySource` adjust **configuration values of the test context**. They **do not directly decide whether a test is a slice or full**.

For example, two tests both using `@ActiveProfiles("test")` yet having different bean graphs:

```java
@WebMvcTest(BookController.class)
@ActiveProfiles("test")
class MvcOnlyTest { /* syntax example, needs mock service */ }

@SpringBootTest
@ActiveProfiles("test")
class FullAppTest { /* syntax example, loads broad application */ }
```

The two classes above only illustrate annotations and are not standalone runnable tests because they lack test methods and collaborator configuration. Profiles let both read `application-test.yml`, but **do not replace each annotation's bootstrapper choice**.

When debugging, note the **active profiles**, key effective properties, and actual beans created in each context. Do not infer from one YAML file that every setting applies if higher-precedence property sources exist.

## 6. Slice Initialization Failures: Fix the Right Spot Instead of Reflexively Switching to Full Context

### 6.1. `NoSuchBeanDefinitionException` for a Business Service

If the controller injects `BookService` yet the test only has:

```java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mvc;
}
```

Spring does not necessarily instantiate `BookService` because `@Service` sits outside the MVC slice. When building `BookController`, a missing-bean error occurs.

**Right fix when testing only the controller contract:**

```java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    BookService service;
}
```

Both code blocks illustrate configuration and omit test methods. `@MockitoBean` supplies the mock bean to the context. Subsequent tests should stub the service per input and assert status/JSON/validation, without claiming the mock's business logic is verified.

**When to use `@Import(BookService.class)`?** When there is a clear reason to need the real service inside a slice and all of the service's required dependencies are supplied. However, the sample project's `BookService` needs `BookCatalog`; importing the real service without supplying the catalog simply shifts the missing-bean error down a layer. If the goal is testing real controller-service-catalog together, **`@SpringBootTest` makes more sense**.

### 6.2. Slice Accidentally Loads JPA or Kafka

Possible causes:

- You placed a manual `@ComponentScan` on the main `@SpringBootApplication`, breaking the test slice's default exclude filters.
- An imported `@Configuration` creates a datasource, Kafka listener, or REST client.
- A `@Bean` factory directly uses a production URL at context startup.
- A custom annotation/meta-annotation or `@ImportAutoConfiguration` brings in extra auto-configuration.
- Primary configuration class/package naming causes Spring Boot to discover an unexpected configuration.

**Fix:** inspect the primary configuration and import chain, split configurations by concern, and import only what the slice needs. **Do not** use `@SpringBootTest` to "fix" an overly broad slice; a full context can widen the risk further.

### 6.3. Service Is Mocked, Yet the Test Claims to Verify Business Calculations

A conceptual mistake:

```java
when(service.findByCode("book-101"))
        .thenReturn(new Book("book-101", "Spring Testing", 7));

mvc.perform(get("/api/books/book-101"))
        .andExpect(jsonPath("$.copies").value(7));
```

This test proves **the controller renders the data returned by the stub**. If real `BookService` miscalculates stock internally, the test still passes because the service is never called.

To test inventory logic: write a unit test for `BookService` with a fake catalog, or a full-context test using real beans. **Do not judge test quality by how many annotations it has; verify which code paths actually execute.**

### 6.4. `@SpringBootTest` Fails Due to Missing Secrets/DB

If a full context loads production HTTP clients, a DataSource, or external listeners, tests may fail due to environment issues or, worse, touch production.

- Select an actual `test` profile and test-only resources.
- Mock/fake outbound boundaries outside the target under test.
- For JPA, use H2 or an ephemeral Postgres container, never a production database.
- Never place real secrets in source/test resources.
- Do not assume "MOCK web environment" means all outbound clients are mocked.
- If you only need to test JSON or controller mapping, return to the appropriate slice instead of booting the full context.

### 6.5. Tests Run Slower Than Expected

A full context often carries many auto-configs, beans, migrations, connection pools, schedulers, and remote clients. Yet a slice can also become heavy if scanning/imports are misconfigured or if tests spawn many distinct contexts due to per-test properties/mocks.

Spring TestContext **caches contexts** by matching configuration; using too many variations of `@MockitoBean`, `@ActiveProfiles`, `@TestPropertySource`, or `@DirtiesContext` reduces reuse. Optimize by grouping tests sensibly by purpose/configuration and measuring real timings, rather than relying only on the "slice" label.

## 7. Extending a Slice Properly

### 7.1. `@MockitoBean` for Boundary Dependencies

For a controller whose service is a collaborator, this fits well because a controller test only needs to control what the service returns:

```java
@MockitoBean
BookService service;
```

Conversely, if the goal is to verify the real business service, mocking it removes the very code path you need to test. Choose mocked/fake beans **based on the test boundary**, not based on "what is mockable."

### 7.2. `@Import` for a Small Real Bean/Config

When a controller depends on a custom `Converter` or `Module` that the slice does not auto-scan, you can do:

```java
@WebMvcTest(BookController.class)
@Import(BookMvcExtrasConfiguration.class)
class BookControllerWithExtrasTest {
    // Example: configures an extra required converter.
}
```

This is an annotation example; `BookMvcExtrasConfiguration` is assumed defined and is not part of the section 4 runnable project. Only import **small configurations with no external side effects**. Importing a `@Configuration` that creates a datasource, broker, and scheduler breaks slice isolation.

### 7.3. `@TestConfiguration` to Add Test-Only Beans

In tests, you can define supporting configurations:

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

This is an **illustrative code sample**, requiring imports for `Clock`, `Instant`, `ZoneOffset`, `@TestConfiguration`, and `@Bean`; it is not part of the section 4 project. Tests can then `@Import(FixedClockConfiguration.class)` to provide deterministic time. Top-level `@TestConfiguration` should be imported explicitly into the tests that need it; avoid letting fake configurations become production beans.

**Distinction:** nested `@TestConfiguration` supplements the primary app configuration; nested `@Configuration` can alter how Spring locates the primary configuration in tests. For both slices and full contexts, prefer `@TestConfiguration` or targeted `@Import`.

### 7.4. `@EnableConfigurationProperties` for Config Beans Excluded from a Slice

A `@ConfigurationProperties(prefix="app.api")` class may not be scanned automatically inside `@WebMvcTest`. If the controller/converter under test genuinely needs it, add `@EnableConfigurationProperties(ApiProperties.class)` in the test or use a small test configuration.

This is a deliberate mechanism for **adding** a properties bean, not a reason to switch the entire project to `@SpringBootTest`. Always use test values, never dragging production URLs/tokens into an MVC slice.

### 7.5. `excludeAutoConfiguration` Is Not "Turn Off All of Spring"

Some `@*Test` annotations provide an `excludeAutoConfiguration` attribute to omit specific auto-configurations. It helps exclude a component that distracts from the test's target, though you should investigate why that component appeared. Do not abuse a giant exclusion list to the point where the test no longer represents the expected MVC/JPA contract.

## 8. Separate Example for `@DataJpaTest`: Different from MVC Slice and Full Context

In the section 4 sample project, `BookCatalog` is simply an in-memory class annotated with `@Repository`, **not a Spring Data JPA repository**. To test `@DataJpaTest`, you need a **separate JPA project** (or extend the project and update the full-context tests accordingly). Do not copy the JPA snippets below into the section 4 project and expect the full-context tests to keep running without a DataSource.

### 8.1. Dependencies of a JPA Test Project

In a Boot 3.5 Maven project already configured for Java 17, add:

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

This is an **additive dependency snippet**, not a complete `pom.xml`; avoid duplicating `spring-boot-starter-test` if it is already present.

### 8.2. Sample Entity/Repository of the Separate JPA Project

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

In the separate JPA project, an `@SpringBootApplication` must sit in `com.example.jpaslice` or a parent package so the configuration can be found. With real PostgreSQL, you would also need the driver/migrations and dedicated config; this example uses in-memory H2 from test dependencies.

### 8.3. Repository Slice Test

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

With proper test configuration, `@DataJpaTest` loads entities, repositories, JPA, and the test database (H2 if present/configured appropriately). It needs neither MVC controllers nor business services.

**What the test proves:** entity mapping + the `findByCode` query work against the test DB. **What the test does not prove:** HTTP controllers, business workflows spanning multiple services, or complete compatibility of H2 with PostgreSQL-specific SQL.

By default, the JPA slice rolls back transactions after each test method. If a test spawns an async worker/different transaction, the test thread's rollback does not automatically cover those operations.

### 8.4. When You Need a Real Database While Still Testing Only the Repository

You can use `@DataJpaTest` + `@AutoConfigureTestDatabase(replace = NONE)` to prevent replacing the DataSource by default, and supply connection details from Testcontainers or a test sandbox. **This is still a JPA slice**, because test slices are primarily about the bean graph, not whether the database is H2 or PostgreSQL.

Annotation configuration example (not a complete test):

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlRepositorySliceTest {
    // Requires test-only PostgreSQL config or @ServiceConnection.
}
```

This snippet requires imports and a real test datasource before it can run. If `replace=NONE` is set while configuration points to production, the test will hit production. Never use production URLs/credentials "just to make the test run."

If you want a **full bean graph** with a swapped database, combine `@SpringBootTest` with `@AutoConfigureTestDatabase` or properly configured Testcontainers. **Swapping the DataSource does not turn a full context into `@DataJpaTest`.**

## 9. Rules for Choosing Slice vs. Full Context

Ask: **"Which bug needs to be caught, and which parts must run for real?"**

| Scenario to verify | Choose | Why |
| --- | --- | --- |
| Controller accepts path/query/body and returns right JSON/status for service result | `@WebMvcTest` + `@MockitoBean` | Focused on MVC contract |
| Jackson serializes enums/dates/custom fields properly | `@JsonTest` | No controller or database needed |
| Repository query and entity mapping work on test DB | `@DataJpaTest` | Focused on DataSource/JPA/transactions |
| SQL via `JdbcTemplate` | `@JdbcTest` | Does not pull in the whole business context |
| Outbound REST client builds right URL/headers/body | `@RestClientTest(Client.class)` | Fake HTTP responses, tests mapping |
| Business service calculates pricing properly | JUnit + Mockito/fake, without Spring if possible | Fast feedback, tiny boundary |
| Real controller → service → repository coordinating | `@SpringBootTest` (+ MockMvc if MVC) | Multiple real layers in one context |
| Requests through a real embedded HTTP server | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Tests port/transport/container |
| Multiple external services, broker, DB, HTTP collaborating | Full integration + containers/stubs/staging | Slices do not represent system-wide links |
| Only need to confirm an app bean/condition is loaded | `@SpringBootTest(NONE)` or minimal test context | No web server needed |

**Decision rule:** prefer the smallest test that can **genuinely catch the bug you are guarding against**. Do not pick a slice just for speed; if the contract spans multiple layers, a slice with mocked services misses wiring/transaction bugs. Do not pick a full context just because the annotation feels "safer"; loading unrelated beans adds cost and risk.

### 9.1. What When You Need Multiple "Slices" in One Test?

Spring Boot does not cleanly support stacking two annotations like `@WebMvcTest` and `@DataJpaTest` on the same class: they carry distinct bootstrap configurations that can cause bootstrap failures. If you need real MVC + JPA in one test, typically choose `@SpringBootTest` and add the appropriate test auto-configuration utilities.

You can combine one slice with manual `@AutoConfigure...` additions when there is a clear rationale, but **do not** treat stacking multiple `@*Test` annotations as a way to build a "larger slice." When a test exercises an entire workflow, a full context is easier to understand and reflects the contract better.

### 9.2. Should a System Have Both Slice and Full Tests?

Yes. For example:

- Many MVC slice tests: fast checks for routing/validation/error JSON per controller.
- JPA slice tests: verify queries/mappings/constraints against a test database.
- Unit tests: verify pricing/authorization/domain rules.
- A few full-context integration tests: verify controller-service-repository flows, active profiles, security wiring, and transactions.
- A few real HTTP server tests: verify transport/serialization at high-risk boundaries.

Slices and full tests do not completely replace each other. **A layer's value lies in the specific defects it catches**, not in test file counts.

## 10. Common Misconceptions

### 10.1. "`@WebMvcTest` also has an `ApplicationContext`, so it is just like `@SpringBootTest`"

False. Both use Spring TestContext, yet their bean graphs and auto-configurations differ. `BookMvcSliceTest` intentionally omits `BookCatalog`, whereas `BookFullContextTest` includes it.

### 10.2. "Adding `@Mock` makes Spring inject it into the controller"

No. `@Mock` creates a Mockito object in the test scope. To put a mock into a Boot 3.5 Spring context, use `@MockitoBean`. Without a Spring replacement bean, the controller constructor may report a missing service.

### 10.3. "`@WebMvcTest` tests real business services"

Not by default. Business services sit outside the MVC slice; if `@MockitoBean` is used, service logic is stubbed. Use unit tests or full-context tests for business flows.

### 10.4. "`@SpringBootTest` always opens a server port"

False. The default is `MOCK`: a full Spring bean context without an embedded HTTP listener. For real HTTP, use `RANDOM_PORT` or `DEFINED_PORT`.

### 10.5. "`@DataJpaTest` cannot touch a real database"

False. With `@AutoConfigureTestDatabase(replace=NONE)` or specific DataSource configurations, the test can use a real DB. Always supply test-only credentials/network.

### 10.6. "`@Import` every missing bean until the slice runs"

That can bloat a slice into an implicit full context, making it slow and risky. When you need to test multiple real components, explicitly switch to `@SpringBootTest` with external dependencies isolated.

### 10.7. "Adding `@ActiveProfiles("test")` makes the test a slice"

False. Profiles affect properties/conditional beans and do not replace `@WebMvcTest`/`@DataJpaTest` or `@SpringBootTest`. Two tests sharing the same profile still have different bean graphs.

### 10.8. "If the MVC slice test passes, the endpoint definitely works in production"

No. A slice with mocked services cannot detect real service/repository wiring errors, production properties, database schemas, or HTTP ingress/proxy issues. You need corresponding integration/E2E layers.

### 10.9. "With Spring Security, drop all filters so controller tests run faster"

Do not do this by default. If security is part of the contract, tests must exercise authentication/authorization/CSRF properly. Disable filters only if a test intentionally separates validation/handler logic from security and independent security tests cover the gap.

### 10.10. "If the full context is too slow, convert everything to slices"

This risks missing cross-layer integration bugs. Keep a targeted set of integration tests, optimize context caching and external dependencies, and use slices where tests genuinely only need a single layer.

## 11. Pre-Merge Test Checklist

- [ ] Does the test prompt/spec identify the boundary: controller, JSON, JPA, service, or full workflow?
- [ ] Was the test annotation chosen to match that boundary: `@WebMvcTest`/`@DataJpaTest`/`@JsonTest`/`@RestClientTest` or `@SpringBootTest`?
- [ ] Is it clear which beans are real, which are mocked, and which do not exist in the context at all?
- [ ] If the controller lacks a service in a slice, is `@MockitoBean`/`@Import` used purposefully?
- [ ] Not using `@Mock` as if Spring registered it as a bean.
- [ ] Not mocking the very component whose real logic you are trying to prove.
- [ ] Not stacking incompatible `@*Test` slice annotations on the same class.
- [ ] Not placing a custom `@ComponentScan` that breaks slice exclude filters without understanding the effect.
- [ ] Test-only properties/profiles are applied, never touching production DBs/APIs.
- [ ] For `@DataJpaTest`, the active database and transaction rollback scope are understood.
- [ ] For `@SpringBootTest`, full bean graph and real HTTP listener are clearly distinguished.
- [ ] When using `@AutoConfigureMockMvc`, it is understood not to open a TCP socket.
- [ ] If using `@DirtiesContext`, there is a real reason and the cache cost is accepted.
- [ ] Assertions measure the right risk for the chosen layer and include key failure cases.

## 12. Self-Check

**Q1.** The controller injects `OrderService`, and `@WebMvcTest(OrderController.class)` reports a missing bean. What should you do when you only want to test mapping/JSON?

**Answer:** Add `@MockitoBean OrderService` to provide a fake collaborator and stub outcomes per case. No real repository or database needs to be loaded.

**Q2.** Why can `@SpringBootTest` verify controller + service + real repository when `@WebMvcTest` with a mocked service cannot?

**Answer:** Full context scans/configures eligible beans across multiple layers. The MVC slice intentionally limits the bean graph; a mocked service executes neither business logic nor repositories.

**Q3.** Two tests both have `@ActiveProfiles("test")`; do they have the same bean graph?

**Answer:** Not necessarily. Profiles only influence conditional configs and properties. `@WebMvcTest` and `@SpringBootTest` still use different bootstrappers and selected auto-configurations.

**Q4.** Is using `@JsonTest` to check serialized fields of a record enough to guarantee the endpoint returns 200?

**Answer:** No. It protects JSON mapping without calling the controller or HTTP server. Use MVC or full-context HTTP tests for the endpoint contract.

**Q5.** Does `@DataJpaTest` rollback by itself guarantee data never touches production?

**Answer:** No. First you must ensure the DataSource is test-only. Rollback does not substitute for access control, network isolation, DDL safety, or operations in other transactions.

**Q6.** Is `@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc` a full context, and does it have a listener?

**Answer:** It has the full application bean context per active configuration, while MockMvc processes requests internally without starting an embedded HTTP listener. For a real listener, use `RANDOM_PORT`/`DEFINED_PORT`.

**Q7.** Why might a slice test unexpectedly load many business beans?

**Answer:** A custom `@ComponentScan`, `@Import`, `@Bean` configuration, or added auto-configuration altered the selected beans or scan filters. Investigate the configuration before abandoning slice annotations.

**Q8.** When you need to test PostgreSQL queries with vendor-specific SQL, what should you use?

**Answer:** You can keep `@DataJpaTest` while providing PostgreSQL Testcontainers or a test-only database and disabling H2 replacement; configure connection details from the container, never a production DB. Full context is only needed if the goal also involves business wiring outside the repository.

## 13. References

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices, MVC/JSON/JPA tests, and selective configuration.
- [Spring Boot 3.5 – Test Auto-configuration Annotations](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): the auto-configurations provided by each slice.
- [Spring Boot 3.5 – Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): organizing `@Configuration`, custom scanning, and slice tests.
- [Spring Framework 6.2 – `@MockitoBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): overriding/replacing beans in TestContext.
- [Spring Framework – Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): reusing test application contexts.
- [Spring Boot 3.5 – `@DataJpaTest` API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): scanning, transactions, and embedded databases.

**Summary:** **A test slice loads enough beans and auto-configuration for one functional slice; `@SpringBootTest` loads the broad application context subject to configuration conditions.** Always inspect **which beans are real, which are mocked, and which are absent**, while distinguishing context scope from having a real HTTP server. Use the smallest test layer that still proves the contract you need to protect.