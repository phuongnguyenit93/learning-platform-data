# Decision Matrix for Choosing a Test Slice by Component and Required Evidence

In Spring Boot, a *test slice* is a testing configuration that loads only **the portion of the Spring ApplicationContext tied to a specific technology or layer** rather than automatically starting the entire application. For instance, `@WebMvcTest` focuses on Spring MVC controllers, while `@DataJpaTest` focuses on JPA entities/repositories. What matters is not just "which test runs faster," but **which defects the test can catch and which lie outside its scope**.

A web slice verifying HTTP status/JSON **does not prove** real SQL queries; a JPA slice verifying mapping/queries **does not prove** URLs/controllers/security; unit tests with Mockito **do not prove** Spring dependency injection. This lesson provides a matrix from **component under test → required evidence → suitable slice → excluded dependencies → when to step up to integration/full-context**, accompanied by runnable Java 17+, Spring Boot 3.5, and JUnit Jupiter examples.

## 1. Getting It Right: What Does a Test Slice Load, and What Does It Omit?

A slice typically combines these mechanisms:

1. **Restricted component scanning:** selects relevant bean types—such as controllers, converters, and MVC advice for a web slice; entities/repositories for a data slice.
2. **Loads only required auto-configurations:** `@WebMvcTest` supports MVC, JSON, and related validation/filters; `@DataJpaTest` supports the entity manager, repositories, and datasource/transactions.
3. **Supplies targeted test utilities:** `MockMvc`, `WebTestClient`, `TestEntityManager`, `JacksonTester`, `MockRestServiceServer`, or `GraphQlTester` depending on slice and version.
4. **Caches contexts by configuration:** tests with compatible slice types, bean overrides, and properties/profiles can reuse contexts; changing configuration creates a new context.

**Slice does not mean a single class:** `@WebMvcTest` still loads many MVC infrastructure beans, and `@DataJpaTest` can load Hibernate, a DataSource, and repositories. Conversely, a slice **does not guarantee zero I/O**: a JPA slice can hit a real DB, and Redis/Mongo slices can connect to real services if test configuration points to them. "Slice" primarily describes the **context boundary**, not "guaranteed mocks only."

When an application bean needs a dependency **outside** the slice, supply the collaborator via `@MockitoBean`, `@Import`, `@TestConfiguration`, or another mechanism **deliberately**. Gradually importing every production class into a web slice just so the context boots defeats the slice's purpose. Step the test up to integration level when real cross-boundary wiring needs verification.

## 2. Main Matrix: Component → Evidence → Slice

| Component or risk | Starting choice | Evidence you can obtain | Not proven by default |
|---|---|---|---|
| Domain functions, custom validators, pure Java pricing/discount rules | **JUnit Jupiter + Mockito/fake**, no Spring | Logic branches, invariants, exceptions, interactions with fakes | DI, annotations, HTTP, SQL, real transactions |
| **Spring MVC controller**, binding, validation, `@ControllerAdvice`, status/JSON | **`@WebMvcTest(Controller.class)`** + `MockMvc` | MVC routes, HTTP serialization, loaded filters/security, error mapping | Real service/JPA when collaborators are mocked; does not test TCP sockets |
| **Spring WebFlux controller/handler** | **`@WebFluxTest`** + appropriate `WebTestClient` | Reactive web routing, status/body, codecs/filters in the slice | End-to-end with remote dependencies, real database, full reactive service graph |
| Jackson serialization/deserialization, custom JSON modules, field names/formats | **`@JsonTest`** + `JacksonTester` or another JSON tester | Object ↔ JSON, loaded custom serializers/deserializers/configs | Controller mapping, HTTP status/filters, DB, services |
| **JPA entity**, repository queries, mapping, flush, basic constraints | **`@DataJpaTest`** | Entity mapping, real JPA repository and SQL on test DB, slice transactions | Controller/service wiring, production DB dialect when using H2, concurrency outside test transaction |
| Spring Data JDBC aggregates/repositories | **`@DataJdbcTest`** | Spring Data JDBC mapping and repositories with test DB | Hibernate/JPA semantics or overall business workflows |
| `JdbcTemplate`, `JdbcClient`, manual SQL/`RowMapper` | **`@JdbcTest`** | SQL statements, row mapping, datasource/transactions in the slice | JPA repositories or web |
| jOOQ DSL and SQL mapping | **`@JooqTest`** | jOOQ `DSLContext`/queries on test datasource | Web/controllers, service orchestration |
| Reactive SQL, R2DBC repositories | **`@DataR2dbcTest`** | Reactive repositories and mapping on test DB/R2DBC | Servlet/JPA behavior; JDBC-style transaction/rollback unless explicitly configured |
| MongoDB / Redis / Elasticsearch / Cassandra / Couchbase / Neo4j data access | **Corresponding data slice** (`@DataMongoTest`, `@DataRedisTest`, `@DataElasticsearchTest`, etc.) | Repository/client mapping, queries/interactions with real dependency or configured test fixture | Production constraints/behavior if only mocked or using a different server |
| **Synchronous REST client** using `RestTemplate`/`RestClient` | **`@RestClientTest(Client.class)`** | URL, method, headers, JSON, error mapping via mock HTTP server | Real remote server, real TLS/network, caller business workflow |
| GraphQL controllers, schemas/queries/resolvers | **`@GraphQlTest`** + `GraphQlTester` | GraphQL documents, data fetcher/controller mapping, responses and errors in slice | Real HTTP/WebSocket transport, database, or real services if mocked |
| SOAP client/server | **`@WebServiceClientTest` / `@WebServiceServerTest`** | XML/SOAP mapping, marshaling, endpoint/client behavior in slice | Real remote SOAP service/network |
| Full application startup and controller → service → repository coordination | **`@SpringBootTest`** (not a slice) + appropriate test tools | Spring wiring and multiple real layers working together | Real network path if using `MOCK`; production infra if test environment differs |
| End-to-end HTTP over sockets, cross-request transactions, external services | **`@SpringBootTest(webEnvironment = RANDOM_PORT)`** + DB/containers/contracts | Real HTTP server, serialization, multi-layer wiring, integration with selected dependencies | Reverse proxies, TLS/real deployment if absent from test environment |

**How to read the table:** start from the **evidence you need**, not from package names. For example, "controller returns 404 properly when service finds nothing" → web slice with mocked service covers the **mapping**; "finding a record by real SKU works" → JPA slice; "calling GET fetches price from DB through controller" → requires an integration test connecting both, which cannot be inferred from two separate slice tests alone.

The slices listed above are supported per technology and Spring Boot version based on declared dependencies; do not pull all of them into a single module just because the list is long.

## 3. Quick Decision Flowchart

```text
What could break and needs proving?
 |
 +-- Only conditions/algorithms inside an object? ------> Plain JUnit + fake/mock
 |
 +-- Object ↔ JSON serialization? -----------------------> @JsonTest
 |
 +-- HTTP request mapping/controller?
 |      |
 |      +-- Servlet MVC? --------------------------------> @WebMvcTest + MockMvc
 |      +-- Reactive WebFlux? ---------------------------> @WebFluxTest + WebTestClient
 |      +-- Must cross a real HTTP socket? --------------> @SpringBootTest(RANDOM_PORT)
 |
 +-- Persistence/queries?
 |      |
 |      +-- JPA/Hibernate? ------------------------------> @DataJpaTest
 |      +-- Spring Data JDBC? ---------------------------> @DataJdbcTest
 |      +-- SQL/JdbcTemplate/JdbcClient? ----------------> @JdbcTest
 |      +-- R2DBC or NoSQL? -----------------------------> Corresponding data slice
 |
 +-- Calling external APIs, checking request/response? --> @RestClientTest
 |
 +-- GraphQL schema/resolver? ---------------------------> @GraphQlTest
 |
 +-- Multi-layer interactions, transactions, wiring? ----> @SpringBootTest/Integration
```

This is a **starting guide**, not a rigid law. A controller backed by complex calculation logic should still have unit tests at the domain/service level; the HTTP slice checks the web layer, while detailed calculations belong to business tests. A strong test suite is **a set of complementary layers**, rather than picking one annotation and discarding the rest.

## 4. "Proven / Not Proven" Matrix Along a Request Chain

Consider `GET /api/products/BOOK-1/price` flowing through controller → service → repository → database.

| Evidence to assert | Unit `ProductService` with fake | `@WebMvcTest` | `@DataJpaTest` | `@SpringBootTest(MOCK)` + MockMvc + test DB | `@SpringBootTest(RANDOM_PORT)` + test DB |
|---|---|---|---|---|---|
| Service handles product returned by repository | **Yes** | No (service usually mocked) | No | **Yes** if using real service | **Yes** if using real service |
| URL, `@PathVariable`, status, and JSON | No | **Yes** | No | **Yes** | **Yes** |
| JPA entity/query and DB round-trip | No | No | **Yes** | **Yes** | **Yes** |
| Spring DI wiring controller → service → repository | No | **Incomplete** if service mocked | No | **Yes** | **Yes** |
| Real HTTP server handling requests over socket | No | No | No | No | **Yes** |
| Compatibility with production PostgreSQL | No | No | **Only with matching DB** | **Only with matching DB** | **Only with matching DB** |
| Full deployment infra (proxy, TLS, gateway) | No | No | No | No | **Insufficient** if test is localhost-only |

Every "Yes" cell is conditional: assertions must actually check the behavior, and the beans/database must be the stated types. `@SpringBootTest` loads many beans, yet if `@MockitoBean` replaces the repository, the test proves nothing about real SQL. Annotation names never replace checking **which dependencies are mocked**.

## 5. Runnable Java 17 + Spring Boot 3.5 Example: Two Slices and One Layer-Connecting Test

This hands-on example demonstrates three boundaries:

1. `@WebMvcTest` proves **routing, JSON, and 404** with a mocked service.
2. `@DataJpaTest` proves **JPA mapping/queries** against real in-memory H2.
3. `@SpringBootTest(MOCK)` + `MockMvc` proves **controller → service → JPA repository → H2** in one context; still without testing HTTP sockets.

Suppose products have an SKU and a VND price. `GET /api/products/{sku}/price` returns `{"sku":"BOOK-1","priceVnd":120000}` when present and HTTP 404 when missing.

### 5.1. Directory Tree

```text
product-slice-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/shop/
    │   ├── ShopApplication.java
    │   ├── Product.java
    │   ├── ProductRepository.java
    │   ├── ProductService.java
    │   └── PriceController.java
    └── test/java/com/example/shop/
        ├── PriceControllerSliceTest.java
        ├── ProductRepositorySliceTest.java
        └── ProductFlowIntegrationTest.java
```

### 5.2. Maven POM

File **`pom.xml`** uses Spring Boot **3.5.0**, Java 17; in real projects, upgrade to a project-approved patch version:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>product-slice-demo</artifactId>
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

H2 is an **educational choice to run slices**, not a guarantee that all SQL or transactions behave identically on production PostgreSQL/MySQL. `spring-boot-starter-test` brings JUnit Jupiter, AssertJ, MockMvc, Mockito, and Spring TestContext onto the test classpath under Boot's dependency management.

### 5.3. Application Code

File **`src/main/java/com/example/shop/ShopApplication.java`**:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

File **`src/main/java/com/example/shop/Product.java`**:

```java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private long priceVnd;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(String sku, long priceVnd) {
        this.sku = sku;
        this.priceVnd = priceVnd;
    }

    public String getSku() {
        return sku;
    }

    public long getPriceVnd() {
        return priceVnd;
    }
}
```

File **`src/main/java/com/example/shop/ProductRepository.java`**:

```java
package com.example.shop;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

File **`src/main/java/com/example/shop/ProductService.java`**:

```java
package com.example.shop;

import java.util.NoSuchElementException;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public long priceOf(String sku) {
        return repository.findBySku(sku)
                .orElseThrow(() -> new NoSuchElementException("Missing SKU: " + sku))
                .getPriceVnd();
    }
}
```

File **`src/main/java/com/example/shop/PriceController.java`**:

```java
package com.example.shop;

import java.util.NoSuchElementException;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/products")
public class PriceController {
    private final ProductService service;

    public PriceController(ProductService service) {
        this.service = service;
    }

    public record PriceResponse(String sku, long priceVnd) {
    }

    @GetMapping("/{sku}/price")
    public PriceResponse price(@PathVariable String sku) {
        try {
            return new PriceResponse(sku, service.priceOf(sku));
        } catch (NoSuchElementException ex) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found", ex);
        }
    }
}
```

The controller translates "not found" to HTTP 404; the service stays unaware of HTTP statuses and talks only to the repository. `Product` is a real JPA entity; `ProductRepository` executes SQL when the context includes a datasource. All classes sit under `com.example.shop` so the root configuration is discovered.

### 5.4. Web Slice: Mock Service, Test HTTP Mapping

File **`src/test/java/com/example/shop/PriceControllerSliceTest.java`**:

```java
package com.example.shop;

import java.util.NoSuchElementException;

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

@WebMvcTest(PriceController.class)
class PriceControllerSliceTest {
    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ProductService service;

    @Test
    void returnsJsonFromControllerForKnownSku() throws Exception {
        when(service.priceOf("BOOK-1")).thenReturn(120_000L);

        mvc.perform(get("/api/products/BOOK-1/price"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK-1"))
                .andExpect(jsonPath("$.priceVnd").value(120_000));

        verify(service).priceOf("BOOK-1");
    }

    @Test
    void mapsMissingProductTo404() throws Exception {
        when(service.priceOf("MISSING"))
                .thenThrow(new NoSuchElementException("MISSING"));

        mvc.perform(get("/api/products/MISSING/price"))
                .andExpect(status().isNotFound());

        verify(service).priceOf("MISSING");
    }
}
```

**Evidence obtained:** path routing, `@PathVariable`, JSON serialization, HTTP 200/404, and the controller's invocation of the service collaborator. **No evidence** that the repository executed SQL: the service is a **Mockito mock in the Spring context**. `@WebMvcTest` auto-configures `MockMvc` without loading all services/repositories like `@SpringBootTest`.

`@MockitoBean` in the example uses the import from **Spring Framework 6.2+**, included in Spring Boot 3.5. In a web slice, the original `ProductService` bean is not normally scanned; by default `@MockitoBean` can **create a new mock bean** to satisfy the dependency. Do not set `enforceOverride = true` when intentionally using only a mock without an original service bean to replace.

**Security note:** when Spring Security is on the classpath, matching filters/security auto-configurations can join the web slice. Tests expecting 200/404 may need authentication/CSRF setup or security-specific test dependencies. Do not disable filters arbitrarily just to make tests green when authorization is the very thing you want to prove.

### 5.5. JPA Slice: Repository and Real SQL on Test DB

File **`src/test/java/com/example/shop/ProductRepositorySliceTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class ProductRepositorySliceTest {
    @Autowired
    private ProductRepository repository;

    @Test
    void findsPersistedProductBySku() {
        repository.saveAndFlush(new Product("BOOK-2", 150_000L));

        Product found = repository.findBySku("BOOK-2").orElseThrow();

        assertEquals("BOOK-2", found.getSku());
        assertEquals(150_000L, found.getPriceVnd());
    }

    @Test
    void returnsEmptyForUnknownSku() {
        assertTrue(repository.findBySku("UNKNOWN").isEmpty());
    }
}
```

`@DataJpaTest` loads Spring Data JPA, the entity manager, repositories, and datasource/test transactions per configuration. With H2 on the classpath, this test runs real queries against **in-memory H2**. Typical `@DataJpaTest` tests are **transactional and roll back at the end of each test**, so the `BOOK-2` fixture is not retained long-term.

**Evidence obtained:** entity mapping, the `findBySku` query, flush/read-back, and persisted values. **No evidence** of controller routes or service HTTP mappings, as those beans lie outside the JPA slice.

If the code uses PostgreSQL-specific functions, transaction isolation, or complex migrations, H2 can hide bugs. When production DB compatibility must be proven, use a test database of the exact engine — typically via **Testcontainers** — and disable embedded DB replacement if needed via `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` alongside the version-appropriate datasource setup. Do not claim a JPA slice "never touches a real DB": it touches whatever database **is configured for the test**, which can be an external DB.

### 5.6. Connecting the Slices: Running Controller → Service → JPA

File **`src/test/java/com/example/shop/ProductFlowIntegrationTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
@Transactional
class ProductFlowIntegrationTest {
    @Autowired
    private MockMvc mvc;

    @Autowired
    private ProductRepository repository;

    @Test
    void readsPersistedPriceThroughRealServiceAndController() throws Exception {
        repository.saveAndFlush(new Product("BOOK-3", 160_000L));

        mvc.perform(get("/api/products/BOOK-3/price"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK-3"))
                .andExpect(jsonPath("$.priceVnd").value(160_000));
    }
}
```

This test **is not a slice**. It loads the controller, service, repository, datasource, and application beans, then executes a request via **in-process MockMvc**. Because this test runs synchronous MockMvc alongside JPA operations on the same test thread, `@Transactional` normally rolls back data created during the test. However, **do not claim this holds for a real HTTP server** under `RANDOM_PORT`: server-thread requests run in a separate transaction, so committed data does not automatically roll back with the test thread.

The new evidence gained is that **the layers wire together properly via Spring DI**. Still, the test sends no real network request, and the database is just H2. If the target defect involves the servlet container, a real HTTP client, TLS, or PostgreSQL dialects, you need a separate integration test at that boundary.

### 5.7. Running the Tests

In the Maven project directory containing `pom.xml`:

```bash
mvn test
```

If you have the Maven Wrapper generated by your project tool:

```bash
./mvnw test
```

Run each type individually to observe scope:

```bash
./mvnw -Dtest=PriceControllerSliceTest test
./mvnw -Dtest=ProductRepositorySliceTest test
./mvnw -Dtest=ProductFlowIntegrationTest test
```

On Windows, use `mvnw.cmd` if the wrapper exists, or `mvn` if Maven is installed. With the three classes above containing **5 `@Test` methods** (2 web + 2 JPA + 1 integration), expect **5 passes, 0 failures** once H2 dependencies/config are loaded properly. These are JUnit tests with no required business stdout; Surefire/JUnit formatting varies by version.

**Conclusion from the three tests:** web slice + JPA slice yield *per-layer* evidence, while `@SpringBootTest` yields **cross-layer wiring** evidence. Never assume cross-layer wiring works merely because individual slices pass.

## 6. Other Slices: Using the Right Tool at the Right Boundary

### `@JsonTest`: Serializers and Deserializers

Use when the risk involves field names, date/number formats, custom Jackson modules, deserializers, or `@JsonComponent`. Typically injects `JacksonTester<MyDto>` / `JsonContent` depending on library and config. A skeleton snippet:

```java
@JsonTest
class PriceJsonTest {
    @Autowired
    private JacksonTester<PriceDto> json;

    // @Test: json.write(...), compare against expected JSON;
    // @Test: json.parseObject(...), assert fields.
}
```

This is a **snippet** and will not compile on its own because `PriceDto` and imports are application types. The JSON slice does not test `@GetMapping`, controller `@Valid`, or HTTP status. If you only want to test two domain rules with no serialization, `@JsonTest` is unnecessary.

### `@RestClientTest`: Outgoing HTTP Clients

When the application has a **synchronous REST client** using `RestTemplate` or `RestClient`, this slice configures the HTTP client and `MockRestServiceServer` to assert **URL, method, headers, body, and response mapping** without calling external services. A conceptual pattern:

```java
@RestClientTest(ExchangeRateClient.class)
class ExchangeRateClientTest {
    @Autowired
    private ExchangeRateClient client;

    @Autowired
    private MockRestServiceServer server;

    // @Test: server.expect(requestTo("https://..."))
    //              .andRespond(withSuccess("{...}", APPLICATION_JSON));
    // Invoke client, assert result, server.verify().
}
```

This snippet **is not standalone**: `ExchangeRateClient`, URI, JSON contract, and imports depend on the project. Avoid confusing `@RestClientTest` with testing an **inbound HTTP controller**: it focuses on **outgoing HTTP clients**. For `WebClient`/reactive HTTP clients, check the version's exact module/utilities; do not assume every `WebClient` is supported by `MockRestServiceServer` the same way as `RestTemplate`.

### `@GraphQlTest`: Queries/Resolvers in GraphQL

When the risk involves schema, argument binding, data fetchers, error shapes, or GraphQL responses, use `@GraphQlTest` with `GraphQlTester`. Mock/import collaborators outside the GraphQL slice. A passing `GraphQlTester` **does not prove HTTP/WebSocket transport** or a real DB unless the test explicitly adds that boundary.

### Data Slices Beyond JPA

- **`@JdbcTest`**: SQL/`JdbcTemplate`/`JdbcClient` when Spring Data repositories are not needed.
- **`@DataJdbcTest`**: Spring Data JDBC aggregates/repositories, distinct from ORM/JPA.
- **`@JooqTest`**: jOOQ's query DSL and SQL mapping.
- **`@DataR2dbcTest`**: reactive SQL repositories. Reactive transactions differ from blocking transactions; do not assume `@Transactional` tests roll back like the JPA slice without verifying explicitly.
- **`@DataMongoTest`**, **`@DataRedisTest`**, **`@DataElasticsearchTest`**, **`@DataCassandraTest`**, **`@DataCouchbaseTest`**, **`@DataNeo4jTest`**: matching data-stack slices. Many technologies **do not spin up an embedded server automatically**; real verification may require dedicated test containers/services.

Choose slices by **actual implementation technology**. If a module writes repositories with manual JDBC, `@DataJpaTest` does not help prove SQL correctness just because both access a relational DB. And for database-vendor-dependent queries, choosing the right DB engine matters more than the slice name.

## 7. Spring Boot 3.5 and 4.x: Avoid Copying the Wrong Imports

**The runnable examples in section 5 target Spring Boot 3.5.0.** In 3.5, typical imports are:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

`@MockitoBean` comes from **Spring Framework 6.2+**, matching Boot 3.5. Spring Boot's `@MockBean` was deprecated in 3.4 and removed in Boot 4.0. Thus, using `@MockitoBean` is more future-ready for 3.5 → 4.x.

**Spring Boot 4.x reorganizes testing into technology-focused modules/starters** (such as `spring-boot-webmvc-test`, `spring-boot-data-jpa-test`, `spring-boot-restclient-test`) with auto-configuration packages different from 3.5. Do not copy `org.springframework.boot.test.autoconfigure...` imports from a Boot 3.5 example into Boot 4.0 without checking API/Javadoc and your dependency tree. Annotation/slice names generally remain, yet **class locations, modules, and starters** must be verified for the pinned version.

Also verify at the same time:

1. Minimum Java version for your project's Boot/Framework line.
2. Whether the matching test starter/module dependency is on the test classpath.
3. Whether `@...Test` names/imports match the version.
4. Whether bean overrides `@MockitoBean`/`@MockitoSpyBean` work and target the right bean.
5. Which auto-configurations are actually imported into the slice; consult the **test slices appendix** for your exact Boot line.

That is why you should never assume from a single slice-name table that **all versions** share identical packages, attributes, and auto-configs.

## 8. When a Slice Fails to Load a Bean: Fix the Right Scope

For instance, `@WebMvcTest(ProductController.class)` reporting a missing `ProductService` makes complete sense: ordinary services **sit outside the MVC slice**. Three reasonable responses:

| Goal | Approach |
|---|---|
| Only want to prove HTTP mapping and controller behavior | Provide `@MockitoBean ProductService`, stub responses/exceptions, and assert HTTP |
| Need one specific bean for mapping/serialization | `@Import` a small config/bean or use `@TestConfiguration`, without dragging the whole app |
| Want to prove the controller uses the real service and real repository | Use `@SpringBootTest` (e.g., `MOCK` + `MockMvc`) with a test DB, without turning the MVC slice into a full context |

**Do not bulk-import every `@Service`, `@Repository`, and `@Configuration`** just to make a slice boot. That adds startup time, alters scope, and blurs conclusions. If the real service is the focus, write unit tests for the service first, then add an appropriate integration test.

Watch out when the application places an explicit `@ComponentScan` on `@SpringBootApplication`: it can disable the slice's default exclude filters and drag unintended beans in. If a slice test seems to load "too much," inspect scan/import configuration rather than patching over it with arbitrary mocks.

## 9. Be Careful with DB Replacement, Transactions, and Mocks

### `@DataJpaTest` Does Not Automatically Mean "Production DB"

With embedded H2 on the classpath, Boot can select/replace the datasource with an embedded test database. That is great for catching common mapping/query mistakes, yet it can **miss** bugs in PostgreSQL-specific SQL, JSONB, collations, locking, isolation, or production migrations.

When exact engine compatibility is needed, use a test database of the matching engine—typically Testcontainers—with appropriate datasource config. `@AutoConfigureTestDatabase(replace = NONE)` is commonly used to block replacement when preserving a specified datasource. Widen dependency scope only when a real risk calls for it, rather than inflating the cost of every test.

### Rollback Depends on Threads and Transaction Boundaries

Relational data slices like `@DataJpaTest` are normally transactional with rollback at the end of each test. By contrast, **HTTP tests using a real server** at `@SpringBootTest(RANDOM_PORT)` run server-side code on a different thread/transaction from the test client; `@Transactional` on the test does not automatically roll back server-committed data. In socket-based integration tests, use explicit cleanup and a dedicated test DB.

### Over-Mocking Produces "False Greens"

If `@WebMvcTest` mocks the entire service, that is **right** when only testing the HTTP layer. It is **insufficient** when the goal is "does the system fetch the right price from the database?" Ask about the risk before mocking; do not measure test quality by counting green contexts.

## 10. Performance and Layering Tests in CI

A practical strategy:

- **Every commit / PR:** plenty of plain unit tests for rules, narrowly scoped web/data/JSON/REST client slices, and key cross-layer integration tests.
- **Per suitable pipeline:** integration tests requiring real DB engines/containers, contract tests against external services, and real HTTP server tests for high-risk paths.
- **Before release:** end-to-end scenarios needing deployment/proxy/security/migration fidelity when required by product commitments.

There is no universal "80% unit, 15% slice, 5% E2E" ratio. Choose by **actual defect cost, rate of change, feedback speed, and environmental reliability**. Slices often hit the sweet spot: catching framework mapping/configuration bugs that pure unit tests miss while costing less than a full application context.

Spring TestContext caches by configuration. Two web slices with `@MockitoBean` differing only in field name/qualifier, properties, or imports can generate distinct context cache keys. Keep mock naming consistent when targeting the same bean, avoid unnecessary `@DirtiesContext`, and avoid shared mutable fixtures to curb flakiness.

## 11. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| `@WebMvcTest` is missing `@Service` | Slice intentionally skips scanning business services | `@MockitoBean`/minimal import; or step up to `@SpringBootTest` if real service is needed |
| `@DataJpaTest` cannot inject a controller | JPA slice does not load MVC | Write a separate web slice or integration test |
| Web test returns 401/403 instead of 200 | Security/filters are active in MVC slice | Configure user/CSRF/mock auth per goal; do not drop security accidentally |
| JSON test passes yet endpoint JSON is wrong | `@JsonTest` does not test HTTP/controller mapping | Add `@WebMvcTest` or HTTP integration tests |
| `@RestClientTest` passes yet remote API changed contract | Mock server uses stale fixtures | Add contract/integration tests with suitable upstream coverage |
| JPA slice passes on H2, production fails SQL | Dialect/schema/transaction incompatibility | Use matching DB engine + migrations, Testcontainers |
| Test context starts tons of unintended beans | `@ComponentScan`/imports broke slice exclusions | Inspect scan/exclude filters; minimize imports |
| Mock service bean does not affect controller | Mock is not in the Spring context or wrong qualifier | `@MockitoBean` the right bean; verify interaction on the injected bean |
| Slice tests are too slow | Many distinct configs, poor context cache reuse | Keep profiles/imports/overrides consistent; trim `@DirtiesContext` |
| "Two slices passed so full flow passes" | Cross-layer DI/wiring was never tested | Add an integration test connecting controller, service, and repository |
| Test uses the wrong slice for the stack | Confused MVC vs. WebFlux, JPA vs. JDBC/R2DBC | Choose by real implementation and risk to prove |
| Boot 4 fails to compile old slice imports | Test modules/packages reorganized | Check version docs and add matching test starters/modules |

## 12. Checklist for Choosing a Slice Before Writing a Test

- [ ] Can I state **one concrete bug to catch** and the assertion proving it?
- [ ] Have I identified whether the target is **domain, MVC, WebFlux, JSON, JPA, JDBC, HTTP client, or GraphQL**?
- [ ] Do I know which beans the slice loads for real, which are **excluded**, and which are mocked?
- [ ] Am I avoiding `@SpringBootTest` for pure logic when plain JUnit suffices?
- [ ] Am I avoiding using `@WebMvcTest` to claim SQL or real business service behavior was tested when the service is mocked?
- [ ] For JPA slices, do I know **which database** is running and whether a production-like engine is needed?
- [ ] For web slices, are security/filters, validation, controller advice, and JSON config properly in scope?
- [ ] If the test must prove **layer A wires to layer B**, is there an actual integration test connecting them?
- [ ] If HTTP sockets/TLS/external contracts matter, am I avoiding confusing MockMvc with real networking?
- [ ] Have I verified package/module/annotation compatibility with **Spring Boot 3.5 vs. 4.x** in use?
- [ ] Have I run tests through the build tool and verified assertions/side effects, not just context startup?
- [ ] Am I balancing speed, reliability, and defect cost instead of picking a slice by name alone?

**Conclusion:** **Choose a slice by the evidence you need to gather, not by annotation preference.** `@WebMvcTest` proves the in-process HTTP/MVC layer; `@DataJpaTest` proves persistence against a test database; `@JsonTest` proves serialization; `@RestClientTest` proves outgoing HTTP clients; `@SpringBootTest` wires layers together when that is the risk. A strong test suite explicitly states **the scope of what is proven and what remains unproven**.

### Official Documentation for Version Verification

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Test Slices and auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 4 — Test modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html)
- [Spring Boot 4 — Test Slices](https://docs.spring.io/spring-boot/appendix/test-auto-configuration/slices.html)
