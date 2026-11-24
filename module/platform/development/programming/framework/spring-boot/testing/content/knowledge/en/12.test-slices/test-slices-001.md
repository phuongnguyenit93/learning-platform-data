# Which Beans and Auto-Configurations Does a Test Slice Limit in Spring Boot?

In Spring Boot, a **test slice** is an `ApplicationContext` configured to test a **specific technical layer** of the application: Spring MVC, WebFlux, JPA, JDBC, JSON serialization, REST client, or GraphQL. Using a slice is not merely about "starting fewer beans." Each `@...Test` annotation also determines **which components are scanned**, **which group of auto-configurations is imported**, and **which test helpers are provided**.

For example, `@WebMvcTest(OrderController.class)` can include controllers, JSON converters, validation, and `MockMvc`, but **does not automatically load regular `@Service` beans and JPA repositories**. Conversely, `@DataJpaTest` configures entities/repositories/JPA/datasource and transactions, but **does not automatically load MVC controllers and business services**. Therefore, **a passing slice test only proves behavior within the tested slice**, not that the entire application wires all layers together correctly.

The examples in this lesson use **Java 17+, Spring Boot 3.4.5, JUnit Jupiter, and Gradle**. Auto-configuration class names and test components may vary by Spring Boot version, so use the table below only for the underlying principles and check the exact imports list in the reference section when verifying a real project.

## 1. Two Filters That Determine a Slice's Scope

A Spring Boot slice combines two mechanisms:

1. **Component scanning is narrowed by type-exclude filters.** A web slice allows controllers, advice, filters/converters, and certain specified web components, while excluding application `@Component` classes outside its scope. A JPA slice focuses on entities/repositories. This affects **beans created by component scanning**.
2. **A purposefully limited set of auto-configurations.** An MVC slice imports MVC, HTTP converters, `MockMvc`, and related conditional configurations; a JPA slice imports datasource, JPA provider, repositories, transactions, and test database support; a JSON slice focuses on mappers/testers.

Beyond these two mechanisms, `@Import`, `@TestConfiguration`, `@MockitoBean`, properties, profiles, and explicitly declared bean definitions **can add beans**. Therefore, you should not say "`@WebMvcTest` can never have a service": accurately speaking, **it does not automatically scan regular business services**, though a test can deliberately import or mock a service.

```text
                      ApplicationContext in test
                                |
           +--------------------+--------------------+
           |                                         |
    Component scan filter                  Auto-configuration imports
           |                                         |
    MVC / JPA / JSON types                  Web / JPA / JDBC / JSON...
           |                                         |
           +--------------------+--------------------+
                                |
                       Test-specific additions
               @MockitoBean / @Import / properties
                                |
                        Assertions in the slice
```

**Auto-configuration is conditional, not a guarantee that a bean exists.** A class listed in the imports must still satisfy `@ConditionalOnClass`, `@ConditionalOnBean`, property/profile checks, or other conditions. For example, if a JDBC driver is missing, you cannot assume a working datasource exists merely because `DataSourceAutoConfiguration` is present.

## 2. Overview Table: Typical Beans and Auto-Configurations

The table below describes **Spring Boot 3.4.x**. The listed auto-configurations are **representative** classes, not the complete import list.

| Slice | Typical beans and tools | Representative auto-configuration | Not verified by default |
| --- | --- | --- | --- |
| **`@WebMvcTest`** | `@Controller`, `@ControllerAdvice`, web converters/filters, MVC infrastructure, `MockMvc` | `WebMvcAutoConfiguration`, `MockMvcAutoConfiguration`, `HttpMessageConvertersAutoConfiguration`, validation, security if present | Business services, repositories, transactions, and database |
| **`@WebFluxTest`** | Reactive controllers, WebFlux codecs, `WebTestClient` | `WebFluxAutoConfiguration`, `WebTestClientAutoConfiguration`, codecs/validation | Business services/repositories, real server/remote systems |
| **`@DataJpaTest`** | `@Entity`, JPA repositories, `EntityManager`, datasource, transactions, `TestEntityManager` when applicable | `HibernateJpaAutoConfiguration`, `JpaRepositoriesAutoConfiguration`, `DataSourceAutoConfiguration`, `TestDatabaseAutoConfiguration`, transaction config | Controllers, business `@Service` beans, HTTP |
| **`@JdbcTest`** | `DataSource`, `JdbcTemplate`/`JdbcClient` depending on classpath, transactions | `JdbcTemplateAutoConfiguration`, JDBC datasource/transaction/test database | JPA entities/repositories, services, MVC |
| **`@DataJdbcTest`** | Spring Data JDBC aggregates/repositories and JDBC infra | `JdbcRepositoriesAutoConfiguration`, JDBC/test database group | Hibernate JPA repositories, regular MVC/services |
| **`@JsonTest`** | JSON mapper and `JacksonTester`/testers for the available library | `JsonTestersAutoConfiguration` and matching mapper configuration | Controllers, HTTP routes, services, repositories |
| **`@RestClientTest`** | Selected outbound REST client, serializers, `MockRestServiceServer` | `RestClientAutoConfiguration`, `RestTemplateAutoConfiguration`, `MockRestServiceServerAutoConfiguration` | HTTP server, other services/repositories, real external partners |
| **`@GraphQlTest`** | GraphQL controllers/handlers and tester | `GraphQlAutoConfiguration`, `GraphQlTesterAutoConfiguration` | Everything outside the GraphQL boundary |
| **`@DataMongoTest`** | Mongo mapping/client/repositories depending on dependencies | Mongo auto-configuration, Mongo Data/repositories auto-config | Business services/MVC; does not guarantee a running Mongo server |

Other slices include: `@DataR2dbcTest`, `@DataRedisTest`, `@DataCassandraTest`, `@JooqTest`, `@DataNeo4jTest`, and equivalents. They are **not identical in transactions, repositories, and infrastructure**. In particular, do not apply JPA's H2/SQL expectations to MongoDB, Redis, or R2DBC.

**Authoritative source:** the complete auto-configuration import table for Spring Boot 3.4 is at:

https://docs.spring.io/spring-boot/3.4/appendix/test-auto-configuration/slices.html

When you need to know whether a class such as `FlywayAutoConfiguration` or `SecurityAutoConfiguration` is in the list, check the exact row for the corresponding annotation **and** verify classpath/property conditions, rather than guessing from the slice name.

## 3. `@WebMvcTest`: Controllers and Spring MVC, Without Auto-Loading Services

`@WebMvcTest(OrderController.class)` selects the target controller and loads web components allowed by the filter, typically including `@ControllerAdvice`, `Converter`, `GenericConverter`, `Filter`, `HandlerInterceptor`, `WebMvcConfigurer`, `WebMvcRegistrations`, `HandlerMethodArgumentResolver`, and appropriate JSON components.

It also configures Spring MVC, converters/JSON, validation when the dependency is present, error handling, and `MockMvc`. It **does not automatically load** business `@Service` beans, Spring Data repositories, datasource/JPA, or regular `@ConfigurationProperties` beans merely because they exist in the app.

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {
    @Autowired MockMvc mockMvc;

    @MockitoBean OrderQuoteService service;
}
```

This is an excerpt; section 8 has a runnable class. `OrderController` requires `OrderQuoteService`, but the slice does not scan services by default. `@MockitoBean` provides a **mock bean in the test context** so the controller can be instantiated and stubbed. Without it, the application may throw `NoSuchBeanDefinitionException` for the dependency; that is usually **the intended behavior of the slice**, not Spring randomly failing to scan.

### Security and Validation in the Web Slice

When Spring Security is on the classpath, security filters and related auto-configurations can participate in `@WebMvcTest`; a `POST` may return 401/403 due to authentication or CSRF before reaching the controller. Use `spring-security-test`, `@WithMockUser`, `csrf()`, and appropriate configuration when the goal is to test filters/security.

If you use `@AutoConfigureMockMvc(addFilters=false)` to isolate the controller from filters, you must explicitly note that the test **does not verify filters/security**. With `@Valid @RequestBody` and a Bean Validation provider on the classpath, `@WebMvcTest` can verify request binding/validation/HTTP 400, but it does not verify business logic or real persistence.

## 4. `@DataJpaTest`: JPA Repositories, EntityManager, Transactions

`@DataJpaTest` scans `@Entity` classes and Spring Data JPA repositories by default, loading JPA/Hibernate, datasource, transactions, and test-database infrastructure. It **does not automatically scan** controllers, business services, or arbitrary `@Component` beans.

Representative Boot 3.4 auto-configurations include:

- `DataSourceAutoConfiguration` and test database `TestDatabaseAutoConfiguration`.
- `HibernateJpaAutoConfiguration` and `JpaRepositoriesAutoConfiguration`.
- `TransactionAutoConfiguration`, datasource/transaction manager.
- JDBC helpers, SQL initialization, `TestEntityManagerAutoConfiguration`.
- Flyway/Liquibase when classpath/configuration conditions match.

**By default, the JPA slice is transactional and rolls back at the end of each test method.** This helps keep individual repository tests from polluting the DB. However, it does not prove that a production service has `@Transactional` configured properly, nor does it prove data was committed after a real request.

If H2/HSQL/Derby is on the classpath, the slice typically uses an embedded database for testing. To use a container datasource or a configured real DB, consider `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` along with a complete connection/test container configuration. Do not assume this setting starts a DB on its own.

**Scope of evidence:** the repository can save/find and map entities correctly **within the JPA test context**. For vendor-specific SQL, locking, or isolation, testing against the production DB engine is still necessary.

## 5. `@JdbcTest` Is Not `@DataJdbcTest` or `@DataJpaTest`

`@JdbcTest` targets `JdbcTemplate`, `JdbcClient`, datasource/transactions, and SQL adapters; it **does not automatically register Spring Data JDBC/JPA repositories**.

`@DataJdbcTest` adds Spring Data JDBC repositories/mapping on top of JDBC; `@DataJpaTest` adds Hibernate/JPA repositories and `EntityManager`. All three include datasource/transaction-related auto-configuration, but **differ in technology and the types of beans scanned**.

JDBC test excerpt (requires JUnit/JDBC imports and an embedded driver):

```java
@JdbcTest
class BasicSqlTest {
    @Autowired JdbcTemplate jdbc;

    @Test
    void executesSql() {
        assertEquals(1,
                jdbc.queryForObject("SELECT 1", Integer.class));
    }
}
```

The check above only proves that the test datasource/JDBC runs a simple SQL statement; it does not prove JPA repositories or order-processing logic.

## 6. JSON, Outbound HTTP, Reactive Web, and Other Slices

**`@JsonTest`** configures JSON mappers and helpers such as `JacksonTester<T>` to compare serialization/deserialization. It does **not** create controller routes, servlet filters, or services/repositories. A passing JSON contract is different from a passing HTTP status.

**`@RestClientTest(RemoteCatalogClient.class)`** focuses on clients the application uses to **make outbound calls**, serializers/client builders, and `MockRestServiceServer`. It is suitable for checking URLs, methods, headers/bodies, and how the client handles simulated responses. It does not open a real server and does not guarantee that a real external partner returns the right data.

**`@WebFluxTest`** focuses on reactive controllers, WebFlux codecs/configurers, and `WebTestClient`, without automatically loading arbitrary services/repositories. If the application is MVC, use `@WebMvcTest` for MVC; do not confuse the presence of `WebTestClient` with the app definitely using the reactive stack.

**`@GraphQlTest`** tests GraphQL handlers/mappings/testers and does not automatically cover business services or persistence. **`@DataMongoTest`** tests Mongo mapping/repositories when an appropriate client and test server are available; there is no default embedded MongoDB in the way H2 commonly works for JDBC.

## 7. Comparing `@SpringBootTest` with Slices

`@SpringBootTest` creates a Spring Boot `ApplicationContext` according to the application's configuration, allowing controllers/services/repositories to be scanned and applying eligible auto-configurations based on classpath/profiles. It **does not mean every possible auto-configuration produces a bean**; conditions still decide.

| Criterion | Test slice | `@SpringBootTest` |
| --- | --- | --- |
| Scope | One filtered layer | Multiple application layers |
| Component scan | Slice-specific type-exclude filters | Standard application scanning |
| Auto-config | Only slice-relevant group | App auto-configs whose conditions match |
| Cross-layer dependencies | Mock/`@Import` when needed | Usually present if app wiring is complete |
| Context | Usually smaller, potentially faster | Usually larger; depends on context cache |
| Real HTTP server | Does not start a server automatically | Only when `RANDOM_PORT`/`DEFINED_PORT` is selected |
| Conclusion | Only the tested layer and configured test doubles | Can verify multiple layers if assertions are sufficient |

**`@SpringBootTest @AutoConfigureMockMvc` is not an MVC slice.** It provides `MockMvc` for a full context. `@WebMvcTest` also has `MockMvc`, but services/repositories remain excluded by default. Having the same test helper **does not define** the context scope.

Do not stack two slice annotations such as `@WebMvcTest` and `@DataJpaTest` on the same test class. When you need controller → service → repository, use `@SpringBootTest` and verify the proper integration contract.

## 8. Runnable Project: One Business Flow, Four Levels of Evidence

This Spring Boot 3.4.5 project uses Java 17+, Gradle, JUnit Jupiter, Spring MVC, Spring Data JPA, H2, Jackson, and Bean Validation. Business rule: `POST /api/orders` accepts `customer` and `subtotal`; if valid, the service adds a fee of 20, saves the order, and returns JSON with `id` and `total`.

Structure:

```text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/slices/SlicesApplication.java
src/main/java/com/example/slices/OrderRecord.java
src/main/java/com/example/slices/OrderRepository.java
src/main/java/com/example/slices/OrderReceipt.java
src/main/java/com/example/slices/OrderQuoteService.java
src/main/java/com/example/slices/OrderController.java
src/test/java/com/example/slices/OrderMvcSliceTest.java
src/test/java/com/example/slices/OrderJpaSliceTest.java
src/test/java/com/example/slices/OrderJsonSliceTest.java
src/test/java/com/example/slices/OrderFullContextTest.java
```

### 8.1. Gradle and Test Database Configuration

**`settings.gradle`**

```groovy
rootProject.name = 'spring-slice-scope'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  datasource:
    generate-unique-name: true
  jpa:
    hibernate:
      ddl-auto: create-drop
```

H2 is available on the runtime/test classpath; `generate-unique-name` reduces the risk of test contexts sharing an in-memory DB name; JPA creates the schema in contexts that include Hibernate. The `ddl-auto=create-drop` setting is for learning only—**do not use it as-is in production**.

### 8.2. Application, Entity, and Repository

**`src/main/java/com/example/slices/SlicesApplication.java`**

```java
package com.example.slices;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SlicesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlicesApplication.class, args);
    }
}
```

**`src/main/java/com/example/slices/OrderRecord.java`**

```java
package com.example.slices;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class OrderRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String customer;
    private int total;

    protected OrderRecord() {
    }

    public OrderRecord(String customer, int total) {
        this.customer = customer;
        this.total = total;
    }

    public Long getId() { return id; }
    public String getCustomer() { return customer; }
    public int getTotal() { return total; }
}
```

**`src/main/java/com/example/slices/OrderRepository.java`**

```java
package com.example.slices;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderRecord, Long> {
}
```

This is a real JPA repository: Spring Data creates the bean when JPA repository auto-configuration participates in the context (JPA slice or full context), but not in MVC/JSON slices.

**`src/main/java/com/example/slices/OrderReceipt.java`**

```java
package com.example.slices;

public record OrderReceipt(Long id, int total) {
}
```

A record is just a Java data type, not a Spring bean. `@JsonTest` serializes the record without needing it in component scanning.

### 8.3. Service and Controller

**`src/main/java/com/example/slices/OrderQuoteService.java`**

```java
package com.example.slices;

import org.springframework.stereotype.Service;

@Service
public class OrderQuoteService {
    private final OrderRepository repository;

    public OrderQuoteService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderReceipt create(String customer, int subtotal) {
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException(
                    "customer must not be blank");
        }
        if (subtotal <= 0) {
            throw new IllegalArgumentException(
                    "subtotal must be positive");
        }

        int total = Math.addExact(subtotal, 20);
        OrderRecord saved =
                repository.save(new OrderRecord(customer, total));
        return new OrderReceipt(saved.getId(), saved.getTotal());
    }
}
```

**`src/main/java/com/example/slices/OrderController.java`**

```java
package com.example.slices;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderQuoteService service;

    public OrderController(OrderQuoteService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderReceipt create(@Valid @RequestBody CreateOrderRequest req) {
        return service.create(req.customer(), req.subtotal());
    }

    public record CreateOrderRequest(
            @NotBlank String customer,
            @Positive int subtotal) {
    }
}
```

MVC receives JSON, Bean Validation applies to the request body, and the controller calls the service. When using slices, these parts do not necessarily exist together.

## 9. Runnable `@WebMvcTest`: Real Controller, Mock Service

**`src/test/java/com/example/slices/OrderMvcSliceTest.java`**

```java
package com.example.slices;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderMvcSliceTest {
    @Autowired MockMvc mockMvc;
    @Autowired ApplicationContext context;

    @MockitoBean OrderQuoteService service;

    @Test
    void mapsValidRequestAndUsesMock() throws Exception {
        when(service.create("Lan", 100))
                .thenReturn(new OrderReceipt(9L, 120));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customer":"Lan","subtotal":100}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.total").value(120));

        verify(service).create("Lan", 100);
        assertTrue(mockingDetails(service).isMock());
        assertEquals(0,
                context.getBeanNamesForType(OrderRepository.class).length);
    }

    @Test
    void rejectsInvalidRequestBeforeService() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customer":" ","subtotal":0}
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

Expected outcome: HTTP 201, JSON, and mock invocation match; an invalid request gets 400 before calling the service. However, the mock **does not save data**: this test has no repository bean (`getBeanNamesForType(...).length == 0`). `@MockitoBean` is available from Spring Framework 6.2/Boot 3.4; older Boot 3.3 projects typically use `@MockBean` for that version.

## 10. Runnable `@DataJpaTest`: Real Entity/Repository

**`src/test/java/com/example/slices/OrderJpaSliceTest.java`**

```java
package com.example.slices;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
class OrderJpaSliceTest {
    @Autowired OrderRepository repository;
    @Autowired ApplicationContext context;

    @PersistenceContext EntityManager entityManager;

    @Test
    void savesAndReloadsThroughJpa() {
        OrderRecord saved =
                repository.saveAndFlush(new OrderRecord("Lan", 120));
        assertNotNull(saved.getId());

        entityManager.clear();
        OrderRecord reloaded =
                repository.findById(saved.getId()).orElseThrow();

        assertEquals("Lan", reloaded.getCustomer());
        assertEquals(120, reloaded.getTotal());
        assertEquals(0,
                context.getBeanNamesForType(OrderQuoteService.class).length);
    }
}
```

`saveAndFlush` executes SQL inside the test transaction; `entityManager.clear()` proves the retrieval goes back through the repository instead of merely reading the entity already managed in the persistence context. After the test, the transaction rolls back by default. The business service is **not** part of the JPA slice; this test proves repository/mapping behavior, but not the controller or the add-20 fee business rule.

## 11. Runnable `@JsonTest`: DTO JSON Without MVC

**`src/test/java/com/example/slices/OrderJsonSliceTest.java`**

```java
package com.example.slices;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;

@JsonTest
class OrderJsonSliceTest {
    @Autowired JacksonTester<OrderReceipt> json;
    @Autowired ApplicationContext context;

    @Test
    void roundTripsReceiptWithoutHttpServer() throws Exception {
        OrderReceipt receipt = new OrderReceipt(9L, 120);
        assertThat(json.write(receipt)).isEqualToJson("""
                {"id":9,"total":120}
                """);
        assertThat(json.parseObject("""
                {"id":9,"total":120}
                """)).isEqualTo(receipt);

        assertEquals(0,
                context.getBeanNamesForType(OrderController.class).length);
    }
}
```

This test proves serialization/deserialization and that no controller bean exists in the JSON slice. If you only need to guard `@JsonProperty`, enum/date formats, or field naming, there is no need to start MVC/services/database.

## 12. `@SpringBootTest`: Connecting Controller, Service, and Repository

**`src/test/java/com/example/slices/OrderFullContextTest.java`**

```java
package com.example.slices;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderFullContextTest {
    @Autowired MockMvc mockMvc;
    @Autowired OrderRepository repository;

    @Test
    void webServiceAndJpaWorkTogether() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customer":"Lan","subtotal":100}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.total").value(120));

        assertEquals(1L, repository.count());
        OrderRecord saved = repository.findAll().get(0);
        assertEquals("Lan", saved.getCustomer());
        assertEquals(120, saved.getTotal());
    }
}
```

Unlike the MVC slice, here both the service and repository are real beans in the full context; the test observes request → service → DB. `@Transactional` on the test rolls back after the method, but **does not prove commits on a real HTTP server running in a different transaction**. `MockMvc` does not open a TCP port; with `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the server and client can run on different threads and transactions, requiring proper cleanup.

### Evidence Table Derived from the Tests

| Test class | Controller | Service | Repository | What was verified |
| --- | --- | --- | --- | --- |
| `OrderMvcSliceTest` | Real | Mock | Absent | HTTP status/body/validation/delegation |
| `OrderJpaSliceTest` | Absent | Absent | Real (H2) | Entity mapping/save/reload |
| `OrderJsonSliceTest` | Absent | Absent | Absent | JSON mapping of DTO |
| `OrderFullContextTest` | Real | Real | Real (H2) | Multiple layers working together in test context |

Do not replace these conclusions with a single summary claim like "passing tests mean the whole application is correct."

## 13. Running the Tests and Interpreting Errors

With a compatible Gradle Wrapper and JDK 17:

```bash
./gradlew clean test
./gradlew test --tests com.example.slices.OrderMvcSliceTest
./gradlew test --tests com.example.slices.OrderJpaSliceTest
./gradlew test --tests com.example.slices.OrderJsonSliceTest
./gradlew test --tests com.example.slices.OrderFullContextTest
```

On Windows, use `gradlew.bat` instead of `./gradlew`. The tests are **designed to PASS** when the files and dependencies above are set up properly; this is an expectation inferred from the code, **not a Gradle execution log**.

If the MVC slice reports a missing service: check mocks/`@Import`. If the JPA slice lacks a datasource: check H2/DB config. If the JSON slice lacks `JacksonTester`: check Jackson and `spring-boot-starter-test`. If the full context hits 401/403 when applied to a project with security: check auth/CSRF/filters; this sample does not add the security starter.

## 14. How to Safely Extend a Slice

**`@Import`** brings specific beans/configurations into the context. Use it to add a genuinely needed converter, mapper, or test fake; do not import the entire application configuration and unintentionally widen the slice.

**`@EnableConfigurationProperties(MyProperties.class)`** can bring a `@ConfigurationProperties` bean into a slice because this kind of bean is not scanned by default as in a full context.

**`@MockitoBean`** (Framework 6.2) adds/replaces a mock dependency in the test context; a plain Mockito `@Mock` on a field does not automatically register a Spring bean. For `@RestClientTest`, `@WebMvcTest`, and services needing collaborators, this is an important distinction.

**`@ImportAutoConfiguration`** is the right way to import additional **auto-configuration** into a slice. Do not arbitrarily substitute regular `@Import`, because auto-configs have their own registration/condition mechanisms. If a slice ends up needing many layers of auto-config, consider switching to `@SpringBootTest`.

**`excludeAutoConfiguration`**, when supported by the annotation, excludes unsuitable auto-configurations; however, excluding a mechanism and having the test pass **does not prove the excluded mechanism works**. Use exclusions deliberately, not merely to silence context errors.

**Do not stack multiple slice annotations** on a single test class; Boot is not designed to merge `@WebMvcTest + @DataJpaTest` into one combined context. Pick one slice, or use a full context for scenarios requiring multiple layers.

## 15. Context Cache, Component Scanning, and Performance

Spring TestContext caches `ApplicationContext` instances by merged configuration; slice type, classes, active profiles, properties, `@Import`, and bean overrides/test customizers can all alter the cache key. Therefore, many small tests with very different configurations can still spend time starting multiple contexts. `@DirtiesContext` tells Spring to evict the context from the cache when needed, but should not be used to mask missing data cleanup.

An important caveat: if the application customizes `@ComponentScan` directly on the application class and inadvertently drops the type-exclude filters Boot provides, components that should be excluded can leak into slices. An explicit `@Bean` or broad `@Import` from the main configuration can also cause a slice to include unexpected beans. Therefore, **do not just read the annotation**—understand the primary configuration and actual bean graph.

A test containing only `contextLoads()` shows that the context built, without protecting output/contracts. Valuable tests should assert HTTP responses, JSON, repository state, interactions, or bean identity according to the slice's goal.

## 16. Common Failure Table

| Symptom | Typical cause | Resolution |
| --- | --- | --- |
| `@WebMvcTest` is missing `@Service` | Services are not scanned by default | Mock/fake or use full context |
| `@DataJpaTest` is missing business service | Data slice focuses only on persistence | Test service with unit/`@SpringBootTest` |
| `@JsonTest` has no `MockMvc` | JSON mapper slice is not MVC | Use `@WebMvcTest` |
| `@JdbcTest` is missing JPA repository | JDBC is not JPA | Choose `@DataJpaTest` |
| MVC test returns 403 | Security/CSRF is active | Configure security tests; do not blindly drop filters |
| JPA test rollback loses data | Default behavior | Do not confuse with service commit |
| JPA slice does not connect to PostgreSQL | Database replacement picks embedded DB | Use real datasource + `Replace.NONE` |
| Real service is still untested | `@MockitoBean` replaces real logic | Add separate unit/full-context tests |
| Slice loads unwanted beans | `@Import`, explicit config, or custom component scan | Inspect configuration and type-exclude filters |
| Test context is slow | Hibernate/DB/validation or fragmented cache keys | Group tests by purpose, reduce config variants |
| Combining multiple slices fails | Conflicting bootstraps/filters | Pick one slice or `@SpringBootTest` |
| `@SpringBootTest @AutoConfigureMockMvc` called a slice | `MockMvc` helper does not define scope | Check the context-loading annotation |

## 17. Self-Check

**A.** `@WebMvcTest(OrderController.class)` does not create `OrderQuoteService`. Is this a Spring bug? **No**; you need to mock/import the collaborator or choose a full context.

**B.** `@DataJpaTest` runs with H2 and rolls back by default. Does this prove production server transaction commits? **No**; the transaction and database in the test differ from the context that needs verification.

**C.** `@JsonTest` confirms DTO `{"total":120}`, yet the HTTP API returns 500. Do the two results contradict? **No**; valid JSON mapping does not guarantee the route/service/DB work correctly.

**D.** `@WebMvcTest` and `@SpringBootTest @AutoConfigureMockMvc` both have `MockMvc`. Can you say they load the same bean graph? **No**.

**E.** You need to test a REST client sending the right headers/URL to a simulated partner. Use `@RestClientTest` with `MockRestServiceServer`, not an MVC slice for an outbound client.

**F.** A test adds `@Import` to bring a real business service into an MVC slice. Is it still a slice? **It is still an extended slice**, not equivalent to a full context. Record its limits and the dependencies deliberately imported.

**G.** Why can `@WebMvcTest` contain security filters while omitting services? Because the web slice's filters and auto-configuration intentionally allow web/security infrastructure, whereas business services are excluded from regular component scanning.

**H.** When you need to test controller → service → repository in one flow, use `@SpringBootTest` with integration assertions; do not stack two slice annotations.

### Test Slice Review Checklist

- Which **layer** is the slice testing, and was the right technology annotation chosen?
- Which beans are scanned by the slice? Which are excluded? Have missing dependencies been deliberately stubbed/mocked?
- Which auto-configurations are imported according to the appendix for the **exact Boot version**? Are classpath/profile conditions satisfied?
- Does the test assert real behavior rather than only context loading?
- Is data/state from mocks clearly distinguished from real services/repositories?
- Is the data slice using H2 or a real database engine? Does the transaction roll back by default?
- When end-to-end security/HTTP/transactions are required, is there a test at the right boundary?
- Do `@Import`, `@TestConfiguration`, or custom component scanning unexpectedly widen the slice?
- Is the context cache fragmented by profiles/properties/mock configurations?
- Is there a clear reason before choosing a full context instead of a narrow slice?

**Conclusion:** A test slice controls both **which component types are loaded** and **appropriate auto-configuration**, making it effective for testing one layer precisely without proving the excluded layers. Use `@WebMvcTest` for MVC, `@DataJpaTest` for JPA, `@JdbcTest` for JDBC, `@JsonTest` for JSON, `@RestClientTest` for outbound HTTP, and `@WebFluxTest` for reactive web. When you need evidence of multi-layer wiring, use `@SpringBootTest` with appropriate integration assertions.

## Official Documentation

- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Test Slices and auto-config imports list: https://docs.spring.io/spring-boot/3.4/appendix/test-auto-configuration/slices.html
- Spring Framework — TestContext Bean Overriding: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
