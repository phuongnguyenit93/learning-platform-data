# Choosing @WebMvcTest, @WebFluxTest, @JsonTest, or a Data Slice

## 1. What Is a Test Slice and Why Choose the Right One?

In **Spring Boot - testing**, a test does not necessarily need to load every bean in the application. For example, when testing a REST endpoint, you need HTTP routing, the controller, JSON conversion, and a stand-in for the service; you do not need to create repositories, a datasource, a scheduler, or a real email client.

A **test slice** is a testing configuration provided by Spring Boot to load only a **portion (slice) of the ApplicationContext**: selecting the beans, component scanning, and auto-configurations relevant to the layer under test. This typically makes tests faster and failures easier to pinpoint than loading the entire application with `@SpringBootTest`.

Four questions determine the annotation:

1. **Which responsibility is being tested?** HTTP mapping/validation/response, reactive web pipeline, JSON serialization, or repository/database?
2. **Which technology does the application use?** Spring MVC, Spring WebFlux, Jackson/Gson/JSON-B, JPA, JDBC, MongoDB, R2DBC...?
3. **Which dependencies need to run for real?** Real controller but mocked service? Real entity/repository with a test DB? Or just POJO logic?
4. **How far does integration need to be proven?** Just a single layer, or the entire HTTP → service → persistence flow?

A slice test **still loads a Spring context**, just smaller than the full application. It is not synonymous with a plain Java unit test without Spring. Choose the smallest slice that **still sufficiently proves the required behavior**, rather than the smallest slice at all costs.

### Quick Selection Matrix

| Goal to prove | Appropriate annotation | Notable testing tools | Usually not loaded |
| --- | --- | --- | --- |
| Spring **MVC** controller, routes, status, JSON body, advice, filters | `@WebMvcTest(Controller.class)` | `MockMvc`, optionally `MockMvcTester` | Regular services/repositories |
| Spring **WebFlux** controller, reactive responses, routes | `@WebFluxTest(Controller.class)` | `WebTestClient` | Regular services/repositories |
| An object serializes/deserializes JSON according to contract | `@JsonTest` | `JacksonTester<T>`, `ObjectMapper`, Gson/JSON-B testers depending on stack | Controllers, services, repositories |
| JPA entities/repositories/queries | `@DataJpaTest` | Spring Data JPA repositories, `TestEntityManager`, `EntityManager` | Web controllers, regular services |
| Plain SQL queries with `DataSource`/`JdbcTemplate` | `@JdbcTest` | `JdbcTemplate` | JPA repositories, web |
| Spring Data JDBC repositories | `@DataJdbcTest` | Repositories, `JdbcTemplate` | Web, JPA |
| Reactive SQL with Spring Data R2DBC | `@DataR2dbcTest` | R2DBC repositories, `R2dbcEntityTemplate` | Web, JPA |
| MongoDB documents/repositories | `@DataMongoTest` | `MongoTemplate`, Mongo repositories | Regular web/services |
| Real flow across multiple layers, full application wiring | `@SpringBootTest` | `MockMvc`/`WebTestClient` or real server depending on configuration | Not restricted by slice |
| Business functions not needing Spring | JUnit + Mockito (if needed) | `new`, `assertEquals`, `@Mock` | Entire Spring context |

Other slices such as `@DataRedisTest`, `@DataNeo4jTest`, `@JooqTest`, `@RestClientTest`, and `@WebClientTest` also exist in the Boot 3.x ecosystem. Choose based on the **technology boundary**, not simply by package name.

**Important principle:** Spring Boot **does not support stacking multiple slice annotations** such as `@WebMvcTest` and `@DataJpaTest` together on the same test class. When additional capabilities are needed, you can use one slice and customize appropriate `@AutoConfigure...`/`@ImportAutoConfiguration` annotations; if most of the application is already required, consider `@SpringBootTest`.

## 2. What Does a Test Slice Actually Limit?

An `@...Test` typically does all of the following at once:

- Limits components eligible for component scanning (does not load every `@Service`, `@Repository`, or `@ConfigurationProperties` the way the full application does).
- Enables only the **permitted set of auto-configurations** for that layer, such as MVC test infrastructure or JPA repositories.
- Registers JUnit Jupiter/Spring TestContext integration and appropriate test helpers.
- Still uses the **Spring context cache** mechanism; test classes with equivalent configurations can reuse contexts.

To understand `NoSuchBeanDefinitionException`, remember: **being excluded from a slice does not necessarily mean the application code is missing a bean**. That bean may exist at runtime, while the slice intentionally does not scan it. When testing a controller that needs a service, use `@MockitoBean` to add a replacement mock in the **Spring context**, or deliberately import a real configuration.

For example, `@WebMvcTest(ProductController.class)` loads only the target controller and related web infrastructure; it does not automatically instantiate every `@Service` injected into the controller. If a test needs to prove a real service and a real repository interacting, `@WebMvcTest` is not the primary tool.

### Why Not Use @SpringBootTest for Everything?

`@SpringBootTest` can be the right choice for integration tests, but when used to verify a single JSON rule or route, it can:

- Initialize unrelated infrastructure, leading to slow tests.
- Fail because of database/email/queue configuration, obscuring failures in the primary target.
- Force the use of more mocks than necessary.
- Create many context/cache variants when profiles, properties, or mock sets differ.

However, **slices do not guarantee speed in every project**: a small context still takes time to build, and how tests/configurations are organized affects cache reuse. Measure actual results rather than assuming every slice test is faster than every unit test or every full-context test.

## 3. Versions, Project Structure, and Dependencies

The examples below use **Java 17 + Spring Boot 3.5.x + JUnit Jupiter** for consistent APIs and imports. In Boot 3.4/3.5, the `@MockitoBean` annotation belongs to:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

It replaces/registers a mock bean in the Spring TestContext. Plain Mockito `@Mock` **does not automatically replace a Spring bean**. The older `@MockBean` in Spring Boot 3.4/3.5 is deprecated in favor of `@MockitoBean`. Do not copy Boot 3.5 imports verbatim into **Spring Boot 4.x** without checking again: test modules and auto-configuration packages have been reorganized.

To avoid mixing stacks, this lesson uses **two independent example projects**:

- **Project A — `slice-web-data`:** Spring MVC, Jackson JSON, and Spring Data JPA/H2. The `@WebMvcTest`, `@JsonTest`, and `@DataJpaTest` tests live in the same project but exercise different slices.
- **Project B — `slice-webflux`:** uses only Spring WebFlux (without pulling in `spring-boot-starter-web`), with a separate `@WebFluxTest`.

Keeping WebFlux separate in Project B is an intentional decision. When Spring MVC and WebFlux **are both on the classpath**, Boot defaults to **MVC** when inferring the application type; in full application tests wanting reactive mode, the appropriate web application type must be selected. Tests for the two web stacks should not be mixed accidentally.

### Baseline Gradle Configuration

**Project A — relevant section in `build.gradle` (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Project B — relevant section in `build.gradle`:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The two blocks above are **configuration snippets**, assuming each project already has the Spring Boot 3.5.x plugin, repositories, dependency management, and Java 17+ toolchain. Do not paste both blocks into the same project to run all examples. Place the Java classes in the proper packages and `src/main/java` or `src/test/java` source sets.

If Project A uses Spring Security, add corresponding test support and design authentication/authorization cases. The runnable examples below assume **Spring Security is not installed**, so filter chains do not inadvertently return `401`/`403`.

## 4. @WebMvcTest: Testing Spring MVC Controllers with MockMvc

**When to choose:** the application uses the servlet stack/Spring MVC with `@RestController`, `@GetMapping`, `@PostMapping`, web validation, exception handlers, filters, or JSON responses. You want to run **real** Spring MVC routing and serialization, without calling databases or remote services.

`@WebMvcTest` typically loads `@Controller`, `@ControllerAdvice`, `@JsonComponent`, certain converters, filters, interceptors, and Boot-permitted MVC infrastructure. Regular `@Service`/`@Repository` beans **are not automatically scanned**. `MockMvc` dispatches requests through the MVC stack **without starting a real HTTP server**.

### 4.1. Complete Example in Project A

All files belong to package `com.example.slicedemo`.

**`src/main/java/com/example/slicedemo/SliceDemoApplication.java`:**

~~~java
package com.example.slicedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceDemoApplication.class, args);
    }
}
~~~

This class lets slice tests locate the root configuration when running. The demo loads individual slices; there is no need to start the full application to verify the MVC/JSON/JPA tests.

**`src/main/java/com/example/slicedemo/ProductView.java`:**

~~~java
package com.example.slicedemo;

public record ProductView(String sku, String name) {
}
~~~

**`src/main/java/com/example/slicedemo/ProductCatalog.java`:**

~~~java
package com.example.slicedemo;

public interface ProductCatalog {
    ProductView findBySku(String sku);
}
~~~

**`src/main/java/com/example/slicedemo/ProductController.java`:**

~~~java
package com.example.slicedemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {
    private final ProductCatalog catalog;

    public ProductController(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{sku}")
    public ProductView find(@PathVariable String sku) {
        return catalog.findBySku(sku);
    }
}
~~~

**`src/test/java/com/example/slicedemo/ProductControllerTest.java`:**

~~~java
package com.example.slicedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductCatalog catalog;

    @Test
    void getProduct_whenCatalogReturnsData_writesJsonResponse()
            throws Exception {
        when(catalog.findBySku("P-1"))
                .thenReturn(new ProductView("P-1", "Notebook"));

        mvc.perform(get("/products/P-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("P-1"))
                .andExpect(jsonPath("$.name").value("Notebook"));

        verify(catalog).findBySku("P-1");
    }

    @Test
    void getUnknownPath_returnsNotFoundWithoutCallingCatalog()
            throws Exception {
        mvc.perform(get("/not-an-endpoint"))
                .andExpect(status().isNotFound());
    }
}
~~~

**What the test proves:**

- The URL `GET /products/P-1` maps to the controller method and returns HTTP 200.
- `ProductView` is serialized by the JSON converter into a body with the expected `sku`/`name`.
- The controller actually invokes the `ProductCatalog` collaborator with the right SKU.
- An unmapped URL returns 404 (under the active web test configuration).

`@MockitoBean` provides a mock **inside the ApplicationContext**. The controller is a real bean. If `@MockitoBean` is replaced with plain Mockito `@Mock`, the controller may miss the dependency in the slice or use another bean, because `@Mock` does not automatically register itself in the Spring context.

### 4.2. MVC Validation, Security, and Exception Handlers

For a `POST` accepting `@Valid @RequestBody`, if the project includes `spring-boot-starter-validation`, `@WebMvcTest` is the right place to verify HTTP 400 when a DTO violates Jakarta constraints. Similarly, `@ControllerAdvice`/`@ExceptionHandler` can be verified with real requests flowing through Spring MVC test infrastructure.

If Spring Security is on the classpath, security filters may be applied in `@WebMvcTest`. Verifying `401`/`403` is meaningful behavior. To simulate a user or CSRF, use `spring-security-test` and helpers like `@WithMockUser` and `csrf()` as appropriate. Do not disable filters with `@AutoConfigureMockMvc(addFilters = false)` just to make tests pass, unless **the test's goal intentionally excludes security** and security is covered elsewhere.

`@WebMvcTest` does not prove database transactions or real service logic. If an endpoint is supposed to return 404 when an entity is absent, while the controller merely forwards the mock's result, you must stub or configure that error branch; a `404` from a nonexistent path **does not substitute for** the service reporting missing data.

## 5. @WebFluxTest: Testing Reactive Controllers with WebTestClient

**When to choose:** the application truly uses **Spring WebFlux**, with endpoints returning `Mono<T>`/`Flux<T>` or handling reactive streams, and you want to test routing/JSON/status without booting the entire app. `@WebFluxTest` loads permitted reactive web components, without scanning all services or repositories automatically.

`WebTestClient` sends requests to **mock WebFlux infrastructure**; in this slice mode it does not need to listen on a real HTTP port. `exchange()` dispatches the request through the reactive pipeline, followed by `expectStatus()`/`expectBody()`.

### 5.1. Complete Example in Project B (Standalone WebFlux)

The package is `com.example.fluxdemo`.

**`src/main/java/com/example/fluxdemo/FluxDemoApplication.java`:**

~~~java
package com.example.fluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxDemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/fluxdemo/StatusView.java`:**

~~~java
package com.example.fluxdemo;

public record StatusView(String code, String label) {
}
~~~

**`src/main/java/com/example/fluxdemo/StatusLookup.java`:**

~~~java
package com.example.fluxdemo;

import reactor.core.publisher.Mono;

public interface StatusLookup {
    Mono<StatusView> find(String code);
}
~~~

**`src/main/java/com/example/fluxdemo/StatusController.java`:**

~~~java
package com.example.fluxdemo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/statuses")
public class StatusController {
    private final StatusLookup lookup;

    public StatusController(StatusLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/{code}")
    public Mono<StatusView> get(@PathVariable String code) {
        return lookup.find(code)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Status not found"
                        )
                ));
    }
}
~~~

**`src/test/java/com/example/fluxdemo/StatusControllerTest.java`:**

~~~java
package com.example.fluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(StatusController.class)
class StatusControllerTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    StatusLookup lookup;

    @Test
    void getStatus_whenFound_returnsJson() {
        when(lookup.find("A"))
                .thenReturn(Mono.just(new StatusView("A", "Available")));

        client.get().uri("/statuses/A")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.code").isEqualTo("A")
                .jsonPath("$.label").isEqualTo("Available");

        verify(lookup).find("A");
    }

    @Test
    void getStatus_whenMissing_returns404() {
        when(lookup.find("missing"))
                .thenReturn(Mono.empty());

        client.get().uri("/statuses/missing")
                .exchange()
                .expectStatus().isNotFound();

        verify(lookup).find("missing");
    }
}
~~~

**Differences from MVC:**

- The service contract returns a `Mono<StatusView>` rather than `StatusView` directly.
- When lookup returns `Mono.empty()`, the controller translates it to `ResponseStatusException(404)`; this is an explicit rule, rather than assuming `Mono.empty()` **automatically** means HTTP 404.
- The test uses `WebTestClient`, not `MockMvc`.
- No server port needs to be opened; this is still a slice test of the reactive controller.

### 5.2. Functional Endpoints and Custom Security

`@WebFluxTest` **does not automatically detect all routes built with `RouterFunction`/functional WebFlux**. If using functional routing, consider testing with `WebTestClient.bindToRouterFunction(...)` in Spring Test, `@Import`ing the needed `RouterFunction`/handler, or using `@SpringBootTest` when testing real wiring. Do not assume an annotated-controller test covers a functional route outside that controller.

A `SecurityWebFilterChain` bean declared in a custom `@Configuration` may also not be discovered automatically by the slice. If security configuration needs to be verified, import the configuration deliberately or choose an appropriate integration test.

### 5.3. Do Not Equate WebFluxTest with Reactive Database Tests

A WebFlux application using reactive MongoDB or R2DBC has two distinct boundaries: **reactive web** and **reactive persistence**. `@WebFluxTest` is not meant to test Mongo/R2DBC queries. For reactive repositories, choose the corresponding data slice (e.g., `@DataR2dbcTest`) or an integration test with a real test DB.

## 6. @JsonTest: Testing JSON Contracts Without Calling Controllers

**When to choose:** the main requirement is serializing/deserializing DTOs with the right field names, formatting, Jackson module configuration, date/time handling, or a custom `@JsonComponent`. No HTTP routes, filters, or server are needed.

`@JsonTest` can configure supported mappers present on the classpath, such as **Jackson**, Gson, and JSON-B; with Jackson, you can inject `JacksonTester<T>` or `ObjectMapper`. It does **not** verify whether `@GetMapping` is registered or whether a controller returns the right status; that is the web slice's job.

### 6.1. Complete Example in Project A

**`src/main/java/com/example/slicedemo/InvoicePayload.java`:**

~~~java
package com.example.slicedemo;

import com.fasterxml.jackson.annotation.JsonProperty;

public record InvoicePayload(
        @JsonProperty("invoice_id") String invoiceId,
        int quantity
) {
}
~~~

**`src/test/java/com/example/slicedemo/InvoicePayloadJsonTest.java`:**

~~~java
package com.example.slicedemo;

import java.io.IOException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class InvoicePayloadJsonTest {
    @Autowired
    JacksonTester<InvoicePayload> json;

    @Test
    void serialize_usesConfiguredSnakeCaseField() throws IOException {
        InvoicePayload source = new InvoicePayload("INV-7", 2);

        assertThat(json.write(source))
                .extractingJsonPathStringValue("@.invoice_id")
                .isEqualTo("INV-7");

        assertThat(json.write(source))
                .extractingJsonPathNumberValue("@.quantity")
                .satisfies(number -> assertThat(number.intValue()).isEqualTo(2));
    }

    @Test
    void deserialize_populatesRecordComponents() throws IOException {
        String source = """
                {"invoice_id":"INV-7","quantity":2}
                """;

        InvoicePayload parsed = json.parseObject(source);

        assertThat(parsed).isEqualTo(new InvoicePayload("INV-7", 2));
    }
}
~~~

`@JsonProperty("invoice_id")` is the JSON naming contract, distinct from the Java record component name `invoiceId`. Both tests prove **bidirectional** serialization/deserialization. Comparing JSON numbers via `Number.intValue()` avoids depending on the exact `Number` subtype returned by JSONPath.

If you want to compare the entire JSON, use `isEqualToJson("expected.json")` with a fixture placed properly in `src/test/resources` or an equivalent JSON assertion; avoid comparing raw JSON strings when field order/whitespace is not part of the contract.

### 6.2. When @JsonTest Is Not Enough

If the system requires "a JSON request missing a required field returns HTTP 400," whether `@JsonTest` succeeds or fails to deserialize **does not prove** the controller has `@Valid` enabled, a configured exception handler, or the HTTP status. Use `@WebMvcTest`/`@WebFluxTest` to test HTTP interaction. If you need to test security, validation, transactions, and database together on a real request, consider a full integration test.

With a custom `ObjectMapper` or Jackson `Module`, ensure that configuration actually enters the slice via appropriate scanning/auto-config/`@Import`; do not assume `@JsonTest` loads all `@Configuration` classes from the application.

## 7. @DataJpaTest: Testing Repositories, Entity Mapping, and Queries

**When to choose:** you need to verify JPA `@Entity` classes, column mappings, repository queries, DB/JPA-level constraints, and persistence behavior. `@DataJpaTest` typically scans entities and Spring Data JPA repositories, creates `EntityManager`/`TestEntityManager`, and does not scan regular `@Service`/controller beans.

By default, `@DataJpaTest` has a **test-managed transaction** and **rolls back after each test**, in an appropriately configured transaction manager environment. When an embedded DB library is on the classpath, Boot can configure it for testing; for example, using **H2**.

### 7.1. Complete Example in Project A

**`src/main/java/com/example/slicedemo/InventoryItem.java`:**

~~~java
package com.example.slicedemo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    protected InventoryItem() {
    }

    public InventoryItem(String sku) {
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
~~~

**`src/main/java/com/example/slicedemo/InventoryItemRepository.java`:**

~~~java
package com.example.slicedemo;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {
    Optional<InventoryItem> findBySku(String sku);
}
~~~

**`src/test/java/com/example/slicedemo/InventoryItemRepositoryTest.java`:**

~~~java
package com.example.slicedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class InventoryItemRepositoryTest {
    @Autowired
    TestEntityManager entityManager;

    @Autowired
    InventoryItemRepository repository;

    @Test
    void findBySku_whenRowExists_returnsMappedEntity() {
        InventoryItem stored = new InventoryItem("SKU-7");
        entityManager.persistAndFlush(stored);
        entityManager.clear();

        var found = repository.findBySku("SKU-7");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().getSku()).isEqualTo("SKU-7");
    }

    @Test
    void findBySku_whenMissing_returnsEmptyOptional() {
        assertThat(repository.findBySku("missing")).isEmpty();
    }
}
~~~

The test creates a real entity, writes and `flush`es it to the test DB, clears `EntityManager`'s persistence context to force the repository query to read from the database again, and then asserts the result. The `@DataJpaTest` annotation creates a persistence test slice; there is no need to mock the repository because **the repository is the object under real test**.

The property `spring.jpa.hibernate.ddl-auto=create-drop` in the example explicitly asks Hibernate to create the test schema for the simple model. In projects with Flyway/Liquibase and real schemas/migrations, use a schema creation strategy consistent with the test's goal; do not assume `create-drop` fits every system.

### 7.2. H2 Differs from Production Databases

Testing with H2 is useful, but it **does not prove** that queries and transactions behave identically on PostgreSQL, MySQL, or Oracle in all cases. Differences can include SQL dialects, collations, JSON features, indexes, locking, concurrency, native queries, and constraint semantics.

When higher fidelity is required, use the same database type as production via Testcontainers or a dedicated test DB, and configure the datasource properly. `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` is one way to prevent Boot from replacing a test datasource you deliberately provided (where applicable). This changes the **DB infrastructure** of the data slice; it does not turn `@DataJpaTest` into a full application test.

**Rollback does not equal resetting everything:** sequences/identities or side effects outside the transaction may not roll back; different DBs have different DDL/transaction policies. If a test spawns another thread or process, do not assume it shares the test-managed transaction.

## 8. Choosing the Right Data Slice: JPA, JDBC, R2DBC, MongoDB

The word **"data"** does not equal **JPA**. Choose based on the actual library and API the application uses:

| Persistence stack | Slice | Objects you usually need to test | Important notes |
| --- | --- | --- | --- |
| Hibernate/JPA + Spring Data repositories | `@DataJpaTest` | `JpaRepository`, `EntityManager`, entity mapping | Transaction + rollback by default |
| SQL with `JdbcTemplate` and `DataSource` | `@JdbcTest` | SQL executed via JdbcTemplate | Has test DB and rollback by default |
| Spring Data JDBC | `@DataJdbcTest` | Spring Data JDBC repositories | Differs from JPA; transactional/rollback by default |
| Spring Data R2DBC | `@DataR2dbcTest` | Reactive repositories, `R2dbcEntityTemplate` | **Not transactional by default** in the test slice |
| MongoDB (sync/reactive depending on config/driver) | `@DataMongoTest` | Mongo repositories, `MongoTemplate` | Requires an actually available test MongoDB |
| Neo4j | `@DataNeo4jTest` | Neo4j repositories, graph mapping | Distinguish reactive access and transaction support |
| Redis | `@DataRedisTest` | Redis repositories, key/value mapping | Not an SQL/JPA test |
| jOOQ | `@JooqTest` | `DSLContext`, SQL mapping | Uses appropriate schema/datasource |

**Do not use `@DataJpaTest` for a project that only uses MongoDB**, and do not use `@WebFluxTest` to test reactive repositories just because an API returns `Flux`. The data layer's technology determines the data slice.

### @JdbcTest and @DataJdbcTest Are Different

`@JdbcTest` focuses on `DataSource` and `JdbcTemplate` for SQL operations, without automatically creating all Spring Data JDBC repositories. `@DataJdbcTest` adds Spring Data JDBC infrastructure and repository scanning. If the code uses a DAO class calling `JdbcTemplate`, `@JdbcTest` is usually sufficient; if the code uses Spring Data JDBC repository interfaces, choose `@DataJdbcTest`.

A brief illustration of `@JdbcTest` (placed in a project with H2 and proper test configuration):

~~~java
package com.example.slicedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@JdbcTest
class ArithmeticJdbcTest {
    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void queryForObject_returnsScalarFromDatabase() {
        Integer value = jdbcTemplate.queryForObject(
                "SELECT 2 + 3", Integer.class
        );

        assertThat(value).isEqualTo(5);
    }
}
~~~

This example illustrates **a real JdbcTemplate running SQL against a test DB**, not a business repository, since there is no custom DAO. If you want to test a real DAO, explicitly import the DAO/config or place it in a configuration supported by the slice; do not assume every `@Repository` in the project will be scanned.

### Does @DataR2dbcTest Roll Back by Default?

**No.** By default behavior in Spring Boot 3.5, `@DataR2dbcTest` does not wrap tests in an automatic transaction like `@DataJpaTest`. Reactive transactions require a reactive context and dedicated management. Therefore, you must design test data isolation/cleanup yourself when using a reactive database.

### Does @DataMongoTest Provide a MongoDB Server Automatically?

It configures Mongo data components such as `MongoTemplate` and repositories, but **the annotation alone does not mean a MongoDB server is already running**. You need a suitable MongoDB test endpoint/instance, such as via Testcontainers, a test environment, or a compatible embedded tool if the project deliberately configures one. Never point tests to production MongoDB just to fix a connection error.

## 9. When a Bean Is Missing in a Slice: Fix the Right Layer Instead of Widening the Whole Test

A typical symptom:

~~~text
UnsatisfiedDependencyException:
  No qualifying bean of type 'ProductCatalog' available
~~~

With `@WebMvcTest(ProductController.class)`, that is usually an **intentional** consequence of the component scan filter: the controller needs `ProductCatalog`, but the service implementation is excluded from the slice.

Approaches, depending on your goal:

1. **Mock collaborators outside the scope under test:** `@MockitoBean ProductCatalog catalog;` when testing only the controller.
2. **Deliberately import a real implementation/configuration:** `@Import(...)` when you need a formatter, converter, exception mapper, or small helper bean that the slice does not scan.
3. **Deliberately load configuration properties:** `@EnableConfigurationProperties(SomeProperties.class)` when the slice needs a specific `@ConfigurationProperties`.
4. **Need multiple real business and persistence layers:** switch to `@SpringBootTest` or split into multiple slice tests verifying clear individual contracts.

**Do not fix the error by unconditionally adding `@ComponentScan("com.example")`.** That can break slice filters, pull in unwanted beans, and make the test behave like a harder-to-understand full context. Spring Boot warns that placing a separate `@ComponentScan` on the `@SpringBootApplication` class can override the exclude filters used for slicing.

### @Import and @ImportAutoConfiguration Have Different Purposes

- `@Import(MySmallConfig.class)`: adds a specific `@Configuration` class or component.
- `@ImportAutoConfiguration(SomeAutoConfiguration.class)`: adds a Boot **auto-configuration** through the proper mechanism.

Do not use plain `@Import` to add an auto-configuration that should be processed through Boot's mechanism. If you need extra infrastructure, first check whether the slice has a corresponding `@AutoConfigure...` annotation.

## 10. When Should You Switch from a Slice to @SpringBootTest?

Choose `@SpringBootTest` when the real goal is to:

- Test controller → real service → real repository within the same Spring context.
- Prove bean wiring, transaction boundaries, security chains, or multi-layer integrated configuration.
- Run with a real server on a random port to test HTTP over sockets.
- Test multi-component flows such as event publishing, jobs, queues, or interactions across many beans that test slices intentionally exclude.

Common configurations:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class FullContextMockMvcTest {
    // Spring MVC, full context; HTTP requests mocked via MockMvc.
}
~~~

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealServerTest {
    // Full context, real embedded server running on a random port.
}
~~~

These are **annotation skeletons**, not complete enough to run as standalone Java files; they need an application class, dependencies, imports, and `@Test` methods. For a WebFlux full context, you can use `@AutoConfigureWebTestClient` according to the appropriate stack.

**Transaction caution:** A full test with `RANDOM_PORT` typically runs the HTTP client and server on two different threads. `@Transactional` on a test method on the client side **does not automatically roll back transactions on the server**. Do not rely on "the test has `@Transactional`" as a guarantee that server data is clean after a real HTTP request.

## 11. Context Cost, Caching, and Organizing the Test Suite

Spring TestContext caches **`ApplicationContext` instances by test configuration**, not by individual class name. If two `@WebMvcTest` classes target different controllers, different mock sets, or different profiles or test properties, their context keys may differ, leading to multiple startups.

Several operational guidelines:

- Keep the target controller scope clear, e.g., `@WebMvcTest(ProductController.class)` rather than arbitrarily scanning too many controllers.
- Declare only `@MockitoBean` fields that are truly necessary; across classes sharing the same target, keep field names/qualifiers consistent to avoid unnecessary cache key mismatches.
- Avoid overusing `@DirtiesContext`, as it can force the cache to reload.
- Use `org.springframework.test.context.cache=DEBUG` logging to inspect hits/misses if startup time becomes an issue.
- Do not mix different slice annotations on one class; if multiple layers are needed, pick the right test level.
- In CI, do not expect two separate JVM test workers to share Spring's static cache.
- Separate tests that run outside Spring (Java unit tests) for pure data rules.

**Necessary balance:** two different slices creating two types of contexts is normal and right. Do not optimize for "fewest contexts" by dropping important checks or using one oversized context for every test.

## 12. Common Mistakes When Choosing a Test Slice

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Testing an MVC `@RestController` with `@WebFluxTest` | Test infrastructure mismatches the controller stack | Choose `@WebMvcTest` for Spring MVC |
| Testing a WebFlux controller with `MockMvc` | `MockMvc` belongs to servlet MVC | Choose `@WebFluxTest` + `WebTestClient` |
| Using `@JsonTest` to assert HTTP status | No routing/web exception handling | Use a web slice |
| Using `@WebMvcTest` and expecting a real repository to load | Repositories are typically excluded | Mock the service boundary or run full integration |
| Using `@DataJpaTest` for R2DBC SQL | JPA and R2DBC are different mechanisms | Choose `@DataR2dbcTest` |
| Assuming `@DataJpaTest` always uses the production DB | Often replaced with an embedded DB if present | Check datasource; use an appropriate test DB |
| Assuming `@DataMongoTest` starts a Mongo server automatically | The slice only configures Spring Data infra | Provide a test server via Testcontainers or environment |
| Treating `@Mock` as a bean override | Mockito mocks only belong to test fields/parameters | Use `@MockitoBean` for the Spring context |
| Missing Spring Security test support | Filters return 401/403 when the test expects 200 | Test auth/CSRF with test security |
| Stacking multiple slice annotations | Spring Boot does not support combining them directly | Pick one slice, customize it, or use full context |
| Using `@Import` for an auto-configuration | Auto-configs have their own registration mechanism | Use `@ImportAutoConfiguration` when needed |
| Adding an overly broad `@ComponentScan` | Can break slice filtering | Use narrowly scoped imports/configs |
| No `@SpringBootConfiguration` found | Test cannot locate root Boot configuration | Place test under app package or specify appropriate config |
| Using H2 to claim PostgreSQL-specific SQL is tested | Dialects and transaction semantics differ | Test against a DB matching production |
| Tests pass individually but fail as a suite | Mutable state in data/mock beans leaks | Isolate data; do not depend on execution order |
| Turning every test into `@SpringBootTest` | Loads out-of-scope infra, slow suite | Pick the right slice plus a few targeted integration tests |

## 13. How to Run the Examples and Verification Limits

In **Project A**, with all described Java files and the Gradle wrapper:

~~~bash
./gradlew test --tests "com.example.slicedemo.ProductControllerTest"
./gradlew test --tests "com.example.slicedemo.InvoicePayloadJsonTest"
./gradlew test --tests "com.example.slicedemo.InventoryItemRepositoryTest"
./gradlew test --tests "com.example.slicedemo.ArithmeticJdbcTest"
~~~

In **Project B** (WebFlux starter, without MVC starter):

~~~bash
./gradlew test --tests "com.example.fluxdemo.StatusControllerTest"
~~~

On Windows, use `.\gradlew.bat` instead of `./gradlew`. The tests above do not call `System.out.println`, so **there is no fixed stdout from application code** to reproduce. Gradle/JUnit console output also depends on version, logging, and environment.

These tests require the Spring Boot/JUnit/Mockito/H2/Jackson classpath described above; a test file cannot be run with plain `javac` lacking those libraries.

If an example fails to start, check in order: dependencies/versions → `@SpringBootApplication` package → stack-appropriate slice annotation → real bean scanned vs. mock overridden → datasource/reactive server configuration → startup log root cause. Never alter assertions just to make a test green before understanding the failure.

## 14. Annotation Decision Checklist Before Writing a Test

- [ ] Have I stated clearly the **behavior to prove** (HTTP, JSON, persistence, or full workflow)?
- [ ] Have I identified **Spring MVC vs. Spring WebFlux**, rather than choosing just because I like reactive APIs?
- [ ] For MVC: `@WebMvcTest` uses `MockMvc`, real controller, and appropriately mocked/imported collaborators.
- [ ] For WebFlux: `@WebFluxTest` uses `WebTestClient` and checks reactive publisher responses.
- [ ] For JSON: `@JsonTest` tests both serialization and deserialization when both are part of the contract.
- [ ] For data: choose **JPA/JDBC/R2DBC/MongoDB** based on the actual stack, without conflating them.
- [ ] Have I checked datasource/H2/Testcontainers conditions and cleanup/rollback policies?
- [ ] Not using `@Mock` to replace a Spring bean; when overriding in context, using `@MockitoBean` appropriate for the version.
- [ ] Not stacking multiple `@...Test` slices on the same class.
- [ ] The test does not scan beans more broadly than needed; only specific configurations are imported.
- [ ] If security is present, have filters, auth, and CSRF been modeled and tested properly?
- [ ] If the goal genuinely spans multiple layers, has an appropriate `@SpringBootTest` been added?
- [ ] Do the examples/run commands match the chosen Java, Spring Boot, and dependency versions?

**Conclusion:** There is no single "best" slice annotation for every test. **`@WebMvcTest` tests the MVC boundary; `@WebFluxTest` tests the reactive web boundary; `@JsonTest` tests JSON contracts; data slices test the persistence layer according to the actual technology.** Pick the right boundary first, keep collaborators outside that boundary clearly substituted or configured, and only use `@SpringBootTest` when you need to prove integration across layers.

### References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Test Auto-configuration Annotations](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework — Spring MVC Test Framework](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Framework — Testing WebFlux](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)