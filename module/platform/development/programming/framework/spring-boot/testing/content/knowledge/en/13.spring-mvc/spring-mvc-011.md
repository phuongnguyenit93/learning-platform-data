# MockMvcTester in Supported Versions of Spring MVC and Spring Boot

## 1. Goal and Scope

`MockMvcTester` is a **Spring MVC** testing API backed by `MockMvc` underneath that provides **AssertJ**-style assertions. It makes mock HTTP request assertions easier to read without changing controllers or starting an HTTP server.

You will learn how to:

- Identify **which Spring Framework / Spring Boot versions** include `MockMvcTester`.
- Distinguish `MockMvcTester`, `MockMvc`, `WebTestClient`, and real HTTP clients.
- Configure it properly in `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc`, and standalone tests.
- Write GET/POST requests with URI templates, query parameters, headers, and request bodies; assert status, text, JSON, JSONPath, and content types.
- Reuse an `MvcTestResult` across multiple assertions without executing the request twice.
- Understand exception handling, async exchanges, security filters, CSRF, and interoperability with legacy matchers.
- Diagnose missing class/bean errors, MVC slice gaps, dependency mismatches, HTTP 401/403/404 responses, and test flakiness.
- Run a hands-on Java 17+, Maven, JUnit Jupiter project on Spring Boot **3.5.16**.

**Do not confuse layers:** `MockMvcTester` operates on **mock servlet requests**; by default it opens no TCP port and does not directly verify TLS, HTTP/2, container error pages, reverse proxies, or deployment setups. Even inside `@SpringBootTest`, calling only `MockMvcTester` still sends requests through `MockMvc`.

Conceptual example:

```java
assertThat(mvc.get().uri("/books/7"))
        .hasStatusOk()
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .bodyJson()
        .isLenientlyEqualTo("""
                {"id":7,"title":"Spring Testing","status":"AVAILABLE"}
                """);
```

`mvc` has type `MockMvcTester`. `assertThat` is imported from AssertJ. The full application and tests to run this example appear in the hands-on section.

## 2. Supported Versions

### 2.1. Version Milestones

`MockMvcTester` was introduced in Spring Framework **6.2** inside `spring-test`. Spring Boot **3.4** is the first Boot line bundling Framework 6.2 in its default BOM. Earlier releases do not include this class in their APIs.

| Version | Use `MockMvcTester`? | Guidance |
| --- | --- | --- |
| Spring Framework 6.1.x and earlier | `MockMvcTester` does not exist | Keep `MockMvc`/Hamcrest or upgrade Framework consistently |
| Spring Framework 6.2.x | Yes | Import from `org.springframework.test.web.servlet.assertj` |
| Spring Boot 3.3.x BOM | Not yet (uses Framework 6.1.x) | Use traditional `MockMvc` |
| Spring Boot 3.4.x | Yes, with AssertJ/test dependencies present | Integrated in `@WebMvcTest` and `@AutoConfigureMockMvc` |
| Spring Boot 3.5.x | Yes; this guide uses 3.5.16 | Bean can be injected with appropriate auto-configuration |
| Spring Boot 4.x / Spring Framework 7.x | AssertJ support for MVC continues; Boot test packages differ from major 3 | Consult migration guides for that major rather than copying all 3.x imports |

### 2.2. Correct Imports

```java
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.assertj.MvcTestResult;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
```

Do not look for `MockMvcTester` under `org.assertj.core.api`. It is a **Spring Framework `spring-test`** class with AssertJ integration. Traditional `MockMvc` lives in `org.springframework.test.web.servlet`; both classes coexist and can test the same application.

### 2.3. Classpath and Configuration Requirements

Having the class on the classpath is **different** from having an auto-configured bean in the test context:

- `spring-test` version 6.2+ supplies `MockMvcTester`.
- AssertJ must be present to use AssertJ assertions.
- Spring MVC servlet infrastructure must be configured when requests run through a context.
- In Spring Boot 3.5, `@WebMvcTest` auto-configures both `MockMvc` and `MockMvcTester` when AssertJ is present.
- `@SpringBootTest` needs `@AutoConfigureMockMvc` to auto-configure the tester in a mock web MVC environment.
- In plain JUnit without Spring TestContext, construct the tester using `MockMvcTester.of(...)`, `from(...)`, or `create(...)` instead of expecting `@Autowired` to work.

Boot 3.5's `spring-boot-starter-test` includes AssertJ, JUnit Jupiter, Mockito, and common testing libraries. The demo project also declares `spring-boot-starter-web` for Spring MVC and Jackson.

### 2.4. Inspecting Dependencies on Failure

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
mvn dependency:tree -Dincludes=org.assertj:assertj-core
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-test-autoconfigure
```

If `spring-test` resolves to 6.1.x, importing `MockMvcTester` will not compile. **Never** fix this by pinning `spring-test` 6.2 alone alongside 6.1 Spring modules; upgrade the Spring Boot BOM uniformly or stick with `MockMvc`. When upgrading to Boot 4, verify new Boot annotation packages—such as `@AutoConfigureMockMvc`—rather than reusing Boot 3.5 imports blindly.

## 3. How Does MockMvcTester Differ from MockMvc?

### 3.1. Same Underlying Request Handling

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
       Services and collaborators in test context
```

Both test **Spring MVC** inside the JVM using mock Servlet APIs without opening an HTTP connection to a real server. How far requests reach from controller to service depends on test scope: MVC slices normally mock services, while full contexts keep real services.

### 3.2. Traditional MockMvc

```java
mockMvc.perform(get("/books/7"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("Spring Testing"));
```

This belongs in a test with `MockMvc mockMvc`, static imports `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status`, and `jsonPath`, typically declaring `throws Exception`.

### 3.3. MockMvcTester + AssertJ

```java
assertThat(mvc.get().uri("/books/7"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.title")
        .asString()
        .isEqualTo("Spring Testing");
```

This syntax belongs in a test with `MockMvcTester mvc`. AssertJ drives the fluent assertions. Both styles can coexist in the same test suite; migrating all existing tests is not mandatory.

### 3.4. Why Choose AssertJ Integration?

- Easy IDE discovery: `hasStatusOk`, `bodyJson`, `hasContentTypeCompatibleWith`.
- Unified `assertThat(...)` style matching domain/collection assertions in unit tests.
- Clean JSONPath or structural JSON comparison instead of raw strings.
- `MvcTestResult` lets you assert multiple properties of one request cleanly.
- Async requests automatically wait for completion in `exchange()` by default.
- Can still invoke legacy result matchers or handlers when needed.

This improves **test DSL ergonomics and maintainability** rather than introducing a different HTTP server engine. If a legacy codebase already uses `MockMvc` cleanly and the team knows it well, migration is optional.

## 4. Three Ways to Create the Tester for Your Goal

### 4.1. MVC Slice — @WebMvcTest

```java
@WebMvcTest(BookController.class)
class BookControllerSliceTest {
    @Autowired
    MockMvcTester mvc;

    @MockitoBean
    BookCatalog catalog;
}
```

`@WebMvcTest` loads required MVC components and auto-configuration without scanning every `@Service`/`@Repository`. `@MockitoBean` supplies the controller's collaborator. Do not confuse it with `@Mock`: `@Mock` creates a plain Java object and does not override a Spring context bean.

### 4.2. Full Context — @SpringBootTest + @AutoConfigureMockMvc

```java
@SpringBootTest
@AutoConfigureMockMvc
class BookFullContextTest {
    @Autowired MockMvcTester mvc;
}
```

`@SpringBootTest` loads the full application context; `@AutoConfigureMockMvc` adds mock MVC test infrastructure without requiring an HTTP port. For apps with datasources or brokers, full contexts may require test profiles, Testcontainers, or adapter doubles.

### 4.3. Standalone — No Boot Context Required

```java
MockMvcTester mvc =
        MockMvcTester.of(new BookController(new BookCatalog()));
```

`MockMvcTester.of(...)` builds a standalone MVC setup around controller objects supplied directly by the test. It does not scan application packages or automatically load global `@ControllerAdvice`, filters, or security config. It fits lightweight controller checks, not full replacements for context-based tests.

### 4.4. From WebApplicationContext or MockMvc

```java
MockMvcTester fromContext = MockMvcTester.from(webApplicationContext);
MockMvcTester fromMvc = MockMvcTester.create(existingMockMvc);
```

These **illustrative patterns require the corresponding test fields**. `from(...)` wraps a configured MVC `WebApplicationContext`; `create(...)` wraps a manually configured `MockMvc` so you can reuse its setup with the AssertJ DSL.

## 5. Essential Assertions

### 5.1. GET with URI Template

```java
assertThat(mvc.get().uri("/books/{id}", 7L))
        .hasStatusOk();
```

`{id}` expands using the provided argument. Avoid raw string concatenation with unencoded special characters; use URI templates or request parameter builders.

### 5.2. Accept and Content-Type Headers

```java
assertThat(mvc.get().uri("/books/7")
        .accept(MediaType.APPLICATION_JSON))
        .hasStatusOk()
        .hasContentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

`Accept` specifies the response format the client expects; `Content-Type` specifies the request body format. For JSON POSTs, add `contentType(MediaType.APPLICATION_JSON)`. Mixing up these headers can cause HTTP 406 or 415 even on valid routes.

### 5.3. Query Parameters

```java
assertThat(mvc.get().uri("/books/search")
        .param("q", "spring"))
        .hasStatusOk();
```

`param("q", ...)` supplies decoded servlet request parameters. When embedding query strings inside URI templates, the URI builder manages encoding/decoding—pay special attention to `+`, `%`, and Vietnamese characters.

### 5.4. POST JSON

```java
assertThat(mvc.post().uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"id":11,"title":"Java Web","status":"AVAILABLE"}
                """))
        .hasStatus(HttpStatus.CREATED);
```

This syntax is used in the sample project without a database. With Spring Security and CSRF enabled, POST requests can return 403 without a CSRF token, distinct from JSON binding errors.

### 5.5. Status and Text Body

```java
assertThat(mvc.get().uri("/books/8"))
        .hasStatus(HttpStatus.NOT_FOUND);
```

```java
// Example for an endpoint GET /ping returning text/plain "pong"
assertThat(mvc.get().uri("/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

The `/ping` example is **illustrative** (absent from the sample project); never assume an endpoint exists without a matching controller. For JSON bodies, prefer `bodyJson()` over raw text equality when property order is not contracted.

### 5.6. Structural JSON Comparison

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

`isLenientlyEqualTo` uses lenient JSON comparison semantics from the JSON testing library. Know your JSONassert/library semantics (object property ordering and comparison rules) before choosing lenient vs. strict. When asserting a single field, JSONPath is clearer; when array ordering is contracted, verify ordering explicitly rather than ignoring it.

### 5.7. Selecting a Field with JSONPath

```java
assertThat(mvc.get().uri("/books/7"))
        .bodyJson()
        .extractingPath("$.title")
        .asString()
        .isEqualTo("Spring Testing");
```

Requires JSONPath on the test classpath, normally bundled with Spring Boot's test starter. For numbers, objects, or lists, use matching typed assertions instead of coercing everything to strings.

## 6. MvcTestResult: Never Send a Request Twice by Mistake

### 6.1. Capture the Exchange Once

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

`exchange()` executes the request and returns a reusable result. This is ideal for multiple independent assertions, especially on endpoints with side effects.

### 6.2. Avoid Accidental Duplicate Requests

The two lines below perform **two** separate exchanges:

```java
assertThat(mvc.get().uri("/books/7")).hasStatusOk();
assertThat(mvc.get().uri("/books/7"))
        .bodyJson()
        .extractingPath("$.title")
        .asString()
        .isEqualTo("Spring Testing");
```

For read-only GETs this is merely wasteful. For a POST creating records, executing twice can create duplicate rows or events. Capture `MvcTestResult` whenever asserting multiple aspects of one response.

### 6.3. Request Builders Execute Lazily When Wrapped by AssertJ

`assertThat(mvc.get().uri(...))` executes via AssertJ integration, so calling `exchange()` is optional for a single assertion chain. When you want clear Given/When/Then structure or debugging checkpoints, `exchange()` keeps the test easy to follow.

## 7. Complete Maven Project (Java 17 / Spring Boot 3.5.16)

The project includes `BookController`, `BookCatalog`, `BookView` record, and four test classes: MVC slice, standalone, full context, and legacy MockMvc interoperability.

### 7.1. Directory Layout

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

All Java files use package `com.example.mvctester`.

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

The Spring Boot parent/BOM manages Spring Framework, JUnit, AssertJ, Mockito, and related libraries. Do not pin `spring-test` or `assertj-core` individually without a specific reason.

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

Using a Java record defines the JSON response cleanly. Real-world DTOs may include nested objects, timestamps, and validation annotations; those are omitted here to keep the example focused.

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

The service connects to no database and returns deterministic results, making it easy to contrast mocked-service slice tests with real-service full-context tests.

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

Illustrative contract:
- `GET /books/7` returns 200 and `BookView` JSON.
- `GET /books/8` returns 404.
- `GET /books/search?q=spring` returns a JSON array.
- `POST /books` returns 201 if `title` is valid, 400 if `title` is blank.

POST here merely echoes the DTO to exercise JSON binding, **without** persisting or generating IDs.

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

Inside the slice:
- `BookController` and MVC infrastructure are real.
- `BookCatalog` mock is provided by `@MockitoBean`.
- `MockMvcTester` is auto-configured by Boot when AssertJ is present.
- Assertions check HTTP mapping, JSON, and delegation, **not** `BookCatalog`'s real service logic.
- POST needs no catalog stubbing because the sample controller method does not call `Catalog`.

If Spring Security starter is added, supply principals and CSRF tokens as required; plain `spring-boot-starter-web` in this POM installs no Security filter chain.

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

This is a standalone MVC test without `@Autowired` and without starting an application context. The test instantiates both the controller and `BookCatalog` in Java. Production global `@ControllerAdvice`, security filters, and custom MVC converters **are not scanned automatically**.

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

In the full context, the real `BookCatalog` runs. `@AutoConfigureMockMvc` provides `MockMvcTester` to exercise controllers via mock requests. It differs from testing a live server via `@SpringBootTest(RANDOM_PORT)`.

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

You do not need to delete existing `MockMvc` tests when adopting `MockMvcTester`. Legacy `ResultMatcher`s work via `matches(...)`, and `MockMvcTester.create(mockMvc)` wraps an existing configured `MockMvc`.

### 7.11. Run Commands

From `mockmvctester-lab`:

```bash
mvn -q clean test

mvn -q -Dtest=BookControllerSliceTest test
mvn -q -Dtest=BookControllerStandaloneTest test
mvn -q -Dtest=FullMvcMockTest test
mvn -q -Dtest=LegacyAndTesterIntegrationTest test
```

Tests are designed to PASS with valid sources and dependencies. Maven returns exit code `0` on success; startup logs depend on the environment. View reports under:

```text
target/surefire-reports/
```

To run the real application:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
curl "http://localhost:8080/books/7"
```

The JSON response contains `id=7`, `title="Spring Testing"`, and `status="AVAILABLE"` (property order is unimportant). This is a real HTTP call to the running app, distinct from mock exchanges via the tester.

## 8. Manually Configuring the Tester Further

### 8.1. From WebApplicationContext

```java
// Illustrative inside a test with @Autowired WebApplicationContext wac
MockMvcTester mvc = MockMvcTester.from(wac);
```

`from` wraps a configured Spring MVC `WebApplicationContext`. It fits when tests skip Boot auto-configuration or customize the builder. Meaningful only for servlet MVC contexts; never use it in place of WebFlux `WebHandler` binding.

### 8.2. From an Existing MockMvc

```java
// Illustrative inside a test with an already-configured MockMvc:
MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

If an existing `MockMvc` has filters, custom request builders, or result handlers, you can keep that setup and adopt AssertJ assertions. For JSON-to-domain conversion on a self-created tester, you may need to register message converters via `withHttpMessageConverters(...)`.

### 8.3. Integrating Legacy Matchers and Handlers

```java
assertThat(mvc.get().uri("/books/7"))
        .matches(status().isOk());
```

`matches` accepts a MockMvc `ResultMatcher`. `apply(...)` accepts a `ResultHandler` such as `print()` or Spring REST Docs. These hooks allow incremental migration without rewriting existing custom matchers upfront.

### 8.4. JSON-to-Domain Conversion

```java
assertThat(mvc.get().uri("/books/7"))
        .bodyJson()
        .convertTo(BookView.class)
        .satisfies(book -> {
            assertThat(book.id()).isEqualTo(7L);
            assertThat(book.title()).isEqualTo("Spring Testing");
        });
```

This advanced pattern requires a suitable message converter, such as Jackson in an MVC context. If no converter is registered on a standalone tester, check JSON via `bodyJson().isLenientlyEqualTo(...)` or configure `withHttpMessageConverters(...)`. Structural JSON assertion and domain conversion are distinct mechanisms.

## 9. Async MVC and Exception Handling

### 9.1. Async Exchange

When an MVC controller returns `Callable` or `DeferredResult`, `exchange()` waits for completion before assertions run; the tester's default async timeout is documented in 6.2 as 10 seconds. You can specify a custom timeout:

```java
MvcTestResult result = mvc.get()
        .uri("/reports/slow")
        .exchange(java.time.Duration.ofSeconds(5));

assertThat(result).hasStatusOk();
```

This snippet is **illustrative**, assuming a `/reports/slow` endpoint exists. Never mistake 5 seconds here for a production HTTP client network timeout. To inspect the initial async state before completion, explore `asyncExchange()` rather than `exchange()`.

### 9.2. HTTP Error Responses vs. Unhandled Exceptions

`BookController` returns `ResponseEntity.notFound().build()` for missing IDs, so the exchange completes cleanly with HTTP 404. The proper assertion is `hasStatus(HttpStatus.NOT_FOUND)`, **not** `hasFailed()`.

By contrast, if a controller throws an exception unhandled by any Spring MVC handler/resolver, the tester represents a failed exchange:

```java
// Illustrative when /boom throws an unhandled exception
assertThat(mvc.get().uri("/boom"))
        .hasFailed()
        .failure()
        .hasMessageContaining("unexpected");
```

Never assume an unhandled exception automatically turns into status 500 inside MockMvc. When `@RestControllerAdvice` maps exceptions into 400/404/409 responses, assert the **HTTP status and error JSON body** per contract.

### 9.3. Test Failures vs. Config Errors

If `@Autowired MockMvcTester` fails for a missing bean, the test never even enters `@Test`—that is a context setup or auto-configuration failure. If the request runs into `assertThat(...)` with an unexpected status or body, that is an assertion mismatch. If a controller throws an unexpected exception, inspect the root cause and exception resolvers before altering expectations.

## 10. Security and Filters

### 10.1. MVC Slices May Include Spring Security

When an application has Spring Security, `@WebMvcTest`/`@AutoConfigureMockMvc` can wire the security filter chain into `MockMvc`. Unauthenticated requests may return 401/302; POSTs without CSRF may return 403.

How to handle it:
- Add `spring-security-test` if principal/role request post-processors are needed.
- Use `@WithMockUser` or security request post-processors aligned with your security stack.
- For POST/PUT/PATCH/DELETE, supply CSRF tokens as configured by your app.
- Never disable filters globally just to get 200 everywhere; that hides security bugs.

### 10.2. addFilters

```java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityMvcExample {
    @Autowired MockMvcTester mvc;
}
```

This is an **illustrative snippet**; the sample project omits the Security starter. `addFilters=true` includes filters from the application context in mock requests. You may disable filters for a narrowly scoped test with explicit justification, provided separate tests cover the security policy.

### 10.3. MockMvcTester Does Not Test Network Security

MVC-layer security filters can be verified, yet TLS certificates, proxy-rewritten headers at ingress, and network-level authentication lie outside MockMvc. Use live server or deployed environment tests for those risks.

## 11. Comparison with WebTestClient and Real HTTP Tests

| Question | MockMvc | MockMvcTester | WebTestClient |
| --- | --- | --- | --- |
| Default stack | Spring MVC | Spring MVC | WebFlux mock / MockMvc-backed / live HTTP |
| Request API | `perform` | `get/post().uri` | `get/post().uri().exchange` |
| Assertions | `andExpect` + Hamcrest/`ResultMatcher` | AssertJ | `WebTestClient` expectations |
| Needs real server? | No | No | Optional; supports `bindToServer` |
| Servlet mock pipeline | Yes | Yes (via `MockMvc`) | Yes when bound to `MockMvc` |
| Supported versions | Long-standing | Spring Framework 6.2+ | Spring WebFlux test support |
| Tests real HTTP? | No | No | Yes when using `bindToServer` |
| Boot 3.5 MVC slice | Auto-configured | Auto-configured with AssertJ | Usable via adapter when dependencies present |

To test **WebFlux**, use `@WebFluxTest` and `WebTestClient`. To test MVC using the `WebTestClient` DSL, Spring Framework offers a `MockMvcWebTestClient` adapter. Still, never conflate those APIs with `MockMvcTester`: they have distinct entry points, response assertions, and binding mechanics.

With `@SpringBootTest(webEnvironment=RANDOM_PORT)`, only an HTTP client such as `TestRestTemplate` or `WebTestClient` (when properly bound) talks over the server port. `MockMvcTester` always remains a `MockMvc` facade, even inside a test class that starts a live server.

## 12. Common Errors and How to Fix Them

### 12.1. Cannot resolve symbol MockMvcTester

**Cause:** `spring-test` is still 6.1 or wrong import. **Fix:** inspect the BOM/dependency tree and import `org.springframework.test.web.servlet.assertj.MockMvcTester`. Never pin a single 6.2 Spring Framework module alongside 6.1 modules.

### 12.2. No qualifying bean of type MockMvcTester

**Cause:** the class exists, but no bean was auto-configured. **Fix:** in Boot 3.5 MVC tests, use `@WebMvcTest` or `@SpringBootTest + @AutoConfigureMockMvc`, and ensure AssertJ is on the classpath. In non-Spring unit tests, use `of(...)` instead of autowiring.

### 12.3. @WebMvcTest Missing Collaborator

**Cause:** the slice does not scan services/repositories like the full app. **Fix:** add `@MockitoBean` for collaborators or `@Import` if a real service is intentionally desired. Never use `@Mock` assuming it enters the Spring context.

### 12.4. Missing AssertJ Dependency

**Cause:** `assertj-core` was excluded or hit a version conflict. **Fix:** check `spring-boot-starter-test` dependency management and avoid ad-hoc library overrides.

### 12.5. Controller Returns 404 Though Test Expects 200

**Cause:** wrong URI/controller scope, mapping, path variables, context path, security, or profile. **Fix:** verify request URIs and handler mappings in the MVC test context; never add `@AutoConfigureMockMvc` expecting it to fix URLs.

### 12.6. GET Returns JSON Body Yet JsonPath Errors

**Cause:** missing JSONPath dependency, non-JSON response content, wrong path expression, or missing converter. **Fix:** check content type first, use `bodyJson` and accurate JSONPath; register converters explicitly in standalone tests when conversion is needed.

### 12.7. JSON Property Order Changes

**Cause:** using raw string equality instead of structural comparison. **Fix:** use `bodyJson().isLenientlyEqualTo(...)` or JSONPath; for arrays with contracted ordering, assert order explicitly.

### 12.8. POST Returns 403 in the MVC Slice

**Cause:** Spring Security + CSRF. **Fix:** supply an authenticated principal and CSRF token per policy; never change the expectation to 403 when the contract expects 201 for an authorized user.

### 12.9. Assertions Fire the Request Twice

**Cause:** creating two separate builder/assertion chains for the same endpoint. **Fix:** capture `MvcTestResult result = ...exchange();` and assert against `result`.

### 12.10. @SpringBootTest(RANDOM_PORT) Yet Thinking the Tester Calls the Server

**Cause:** confusing the MockMvc facade with an HTTP client. **Fix:** use a real HTTP client targeting the live port when testing networking; never assume an annotation routes MockMvc over TCP.

### 12.11. Async Request Times Out

**Cause:** controller never completes the async result, deadlocks, runs too slowly, or test timeout is too short. **Fix:** inspect request lifecycle and timeouts; `exchange(Duration)` sets the async test wait limit, not a cure for blocked event loops or thread pools.

### 12.12. Standalone PASSES While Full Context FAILS

**Cause:** standalone omits the app's custom advice, security, filters, `ObjectMapper`, converters, or property sources. **Fix:** configure standalone accurately or add `@WebMvcTest`/full-context tests for the contracts under protection.

### 12.13. Mixing Spring Boot 3 and 4 Imports

**Cause:** Boot 4 reorganized several test packages and starter modules. **Fix:** follow the migration guide for your major version rather than mixing Boot 4 runtime with old Boot 3.5 `test-autoconfigure` just to get an IDE to compile.

## 13. Advanced Scenarios

### 13.1. Headers, Cookies, Redirects, and MVC Result Matchers

Not every check needs a new assertion method. For custom `ResultMatcher` checks on redirects, cookies, or model/views, keep existing rules via `matches(...)`. For custom result handlers or documentation, `apply(...)` integrates cleanly—valuable when gradually adopting `MockMvcTester` in large existing codebases.

### 13.2. Multipart

```java
// Illustrative when POST /upload exists
assertThat(mvc.post().uri("/upload")
        .multipart()
        .file("note.txt", "Hello".getBytes(
                java.nio.charset.StandardCharsets.UTF_8)))
        .hasStatusOk();
```

Multipart in MockMvc simulates a mock Servlet request and does not verify container parser behavior or file-size limits. Use real integration tests when upload infrastructure is a key risk.

### 13.3. Context Path / Servlet Path

```java
// Illustrative if the app configures context path /app and servlet path /main
assertThat(mvc.get().uri("/app/main/books/7")
        .contextPath("/app")
        .servletPath("/main"))
        .hasStatusOk();
```

Do not copy these paths into the sample project, which does not configure those servlet paths. If an app sets custom context/servlet paths, tests must mirror that routing context accurately.

### 13.4. Jackson Converters and Domain Conversion

Using `bodyJson().convertTo(BookView.class)` requires a compatible message converter (Jackson). With `MockMvcTester.of(...)` standalone and a custom `ObjectMapper`, conversions can diverge from the full app. When JSON serialization matters, use an MVC slice configured with the real mapper or a full context to avoid testing the wrong setup.

### 13.5. Unhandled Exceptions

If a request throws an exception with no matching resolver, the tester can assert `hasFailed`/`failure`. Once controller advice maps it to a 4xx response, it is a completed exchange—assert the HTTP status and error JSON instead of expecting an exception to bubble out of the test call.

## 14. Self-Study Exercises

1. Boot 3.3 uses Spring 6.1: why does importing `MockMvcTester` fail to compile? Name two paths—upgrading or keeping the existing API—without breaking the BOM.
2. Convert a GET test from `perform(get(...)).andExpect(status().isOk())` to `assertThat(mvc.get().uri(...)).hasStatusOk()`.
3. Use `MvcTestResult` to assert status, content type, and JSON title from the **same** request.
4. Create `@WebMvcTest(BookController.class)`, mock `BookCatalog` with `@MockitoBean`, and explain why `@Mock` alone is not injected into the controller.
5. Run `@SpringBootTest + @AutoConfigureMockMvc` and compare results against the mocked-service slice.
6. Use `MockMvcTester.of(...)` around the plain Java controller; analyze which MVC features are not automatically included.
7. Write tests for valid POST JSON and blank titles; with Spring Security enabled, how must the request change when CSRF is active?
8. Compare a JSON object via raw string vs. `bodyJson`; explain when object property order should not be treated as part of the contract.
9. Explain the difference between a 404 response from `ResponseEntity.notFound()` and an unhandled exception requiring `hasFailed`.
10. Explain why a passing `MockMvcTester` test does not prove TLS, reverse proxies, or servlet container error pages work.

Success criteria: know the **framework version**, **web stack type**, **test level**, **mock request setup**, and **what contract each assertion protects** before writing code.

## 15. Pre-Merge Test Checklist

- [ ] Is `spring-test` actually 6.2+ and `MockMvcTester` imported from the right package?
- [ ] Does Boot 3.4+/3.5+ include AssertJ and test dependencies without mixing incompatible Spring modules?
- [ ] Did you pick Servlet MVC testing rather than WebFlux?
- [ ] Under `@WebMvcTest`, do controller collaborators have `@MockitoBean`?
- [ ] Under `@SpringBootTest`, is `@AutoConfigureMockMvc` present?
- [ ] Without Spring, are `MockMvcTester.of`/`from`/`create` used properly?
- [ ] Do URI, path variables, params, `Accept`, and `Content-Type` match the contract?
- [ ] Are status and JSON/text/body asserted in the actual representation?
- [ ] For JSONPath, are the dependency and paths right; for domain conversion, is a converter available?
- [ ] Is a single `MvcTestResult` used when making multiple assertions on one request?
- [ ] Do security tests configure principals/roles/CSRF cleanly without needlessly disabling filters?
- [ ] Are HTTP error responses clearly distinguished from unhandled exceptions?
- [ ] Are async completion and timeouts explicitly accounted for?
- [ ] Do you avoid claiming real networking/TLS/container verification when using MockMvc?
- [ ] When migrating, are legacy `matches`/`apply` hooks reused where helpful?
- [ ] Did you run the Maven/Gradle test task and inspect root causes on failure?

**Conclusion:** `MockMvcTester` is the AssertJ facade over `MockMvc`, introduced in **Spring Framework 6.2** and convenient from **Spring Boot 3.4+**. In Boot 3.5, `@WebMvcTest` auto-configures the tester when AssertJ is available; with `@SpringBootTest`, add `@AutoConfigureMockMvc`. It tests MVC behavior using **mock Servlet requests** and does not replace WebFlux tests or live-network integration tests.

## 16. Official References

- Spring Framework 6.2 — MockMvc AssertJ integration: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj.html
- Spring Framework 6.2 — Configuring MockMvcTester: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/setup.html
- Spring Framework 6.2 — Performing Requests: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/requests.html
- Spring Framework 6.2 — Defining Expectations and JSON Support: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/assertions.html
- Spring Framework 6.2 — Legacy MockMvc integration: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj/integration.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — `@AutoConfigureMockMvc` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html
- Spring Framework 6.2 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes
- Spring Boot 4 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide