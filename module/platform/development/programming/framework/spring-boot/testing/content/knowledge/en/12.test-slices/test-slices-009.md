# Test Slices: Do Not Stack Multiple Slices into an Ambiguous Context

## 1. The Problem: A Test Needs MVC and JPA—Should You Combine Two Annotations?

Spring Boot supports **test slices** to load only part of an application, such as `@WebMvcTest` for Spring MVC and `@DataJpaTest` for JPA repositories. Each slice expresses a **deliberate test boundary intent**: activating only the beans, component scanning, and auto-configurations sufficient for that goal.

A snippet that often shows up when learners want "both the controller and the database":

```java
// WRONG: this is an anti-pattern, not a valid test.
@WebMvcTest(AccountController.class)
@DataJpaTest
class AccountControllerAndJpaTest {
    // ...
}
```

It looks like "adding the MVC slice and JPA slice together," yet per **Spring Boot 3.3** documentation, placing **multiple `@…Test` slice annotations on the same test is not supported**. These annotations are not independent switches you can arbitrarily combine. Each annotation defines its own bootstrap mechanism, filters, and auto-configuration group; mixing them makes **the test scope unclear** and typically fails during Spring test context construction.

Practical principle:

> **One test class should make one clear context decision.** If you only need to test the web layer, use an MVC slice and supply fake collaborators. If you only need persistence, use a JPA slice. If you need to verify multiple layers working together, use `@SpringBootTest` with the appropriate test utilities — do not stack slices.

An advanced option Spring Boot permits is **picking a single slice and adding the needed `@AutoConfigure…` annotations from another layer** explicitly. Even so, that does not make stacking multiple slice annotations valid, nor does it automatically materialize missing beans. You must understand the bootstrapper, context type, and activated infrastructure, and usually a **full integration test is simpler** when you genuinely want to test multiple layers.

## 2. Lesson Objectives

After completing this lesson, you will be able to:

1. Explain a "slice test" in terms of three elements: **restricted component scanning**, **selected auto-configuration**, and **configured test infrastructure**.
2. Explain why `@WebMvcTest` + `@DataJpaTest` and `@SpringBootTest` + `@WebMvcTest` are not valid ways to combine annotations arbitrarily.
3. Identify scenarios calling for an MVC slice, JPA slice, JSON test, client test, or full Spring Boot context.
4. Use Spring Boot 3.3's `@MockBean` (or `@MockitoBean` in newer Framework releases) for collaborators outside a slice's scope.
5. Use `@Import`/`@TestConfiguration` to add **a few specific beans** while keeping the test boundary intelligible.
6. Use `@SpringBootTest` + `@AutoConfigureMockMvc` to test controller → service → repository without opening a real HTTP server.
7. Write Java 17/JUnit Jupiter tests with verifiable outcomes, explaining **what the test proves** and **what it does not prove**.
8. Diagnose multiple-bootstrapper errors, missing beans, wrong auto-configurations, datasources, and context caching issues.
9. Protect test boundaries during refactoring, Spring Boot upgrades, or expanding integration scope.

## 3. What Is a Test Slice?

Spring Boot is an IoC container holding many components: controllers, services, repositories, databases, HTTP clients, security filters, schedulers, metrics, and auto-configurations. To test just one slice, Spring Boot provides **`@…Test`** annotations tailored to each technology.

```text
Full Spring Boot application
+--------------------------------------------------+
| MVC controllers / filters / JSON                 |
| Services / domain use cases                      |
| JPA repositories / entities / SQL                |
| HTTP clients / event publishers / security       |
| Configurations / infrastructure / startup jobs   |
+--------------------------------------------------+

@WebMvcTest
+-----------------------------+
| MVC controller              |
| MVC infrastructure / JSON   |
| Selected filters/advice     |
| Mock collaborators          |
+-----------------------------+

@DataJpaTest
+-----------------------------+
| JPA entities                |
| Repositories                |
| EntityManager / datasource  |
| Test transactions           |
+-----------------------------+
```

This is a **conceptual diagram**, not an exhaustive list of every bean. For instance, `@WebMvcTest` may still include security filters, controller advice, or web components depending on classpath/configuration. `@DataJpaTest` may include migrations/test datasource setup. The exact set of auto-configurations must be checked against your **Spring Boot version**, not guessed from the annotation name.

Each slice usually does three things:

1. **Limits component scanning:** only bean types tied to the technology area under test are selected. `@WebMvcTest` does not auto-scan ordinary services, and `@DataJpaTest` does not auto-load all controllers/services.
2. **Selects auto-configuration:** only an appropriate set of framework configurations (MVC dispatcher/JSON, or JPA/transactions/datasource...).
3. **Prepares test infrastructure:** such as `MockMvc` for the web slice, or `TestEntityManager` and transactional rollback for the JPA slice.

Benefits: faster boot, fewer external dependencies, easier failure isolation, and clearer test intent.

**Intentional limitation:** a test slice is not a full model of the entire application. When an MVC test mocks a service, you cannot conclude that SQL/repositories work. When a JPA test queries a repository, you cannot conclude that HTTP statuses/JSON contracts are right.

## 4. Common Slice Annotations

| Slice | Notable boundary | What to assert | Components usually not auto-loaded |
| --- | --- | --- | --- |
| `@WebMvcTest` | Spring MVC controllers, mappings, JSON, validation, MVC filters | HTTP status, headers, JSON response, exception mapping | Regular services/repositories |
| `@WebFluxTest` | Reactive web controllers, WebFlux infrastructure | Web responses, reactive contracts | Application-wide repositories/services |
| `@DataJpaTest` | Entity mapping, repositories, JPA queries, test database | Persist/reload/query, constraints, transaction behavior | MVC controllers and regular services |
| `@JdbcTest` | JDBC, DataSource, JdbcTemplate | SQL/JDBC interactions | MVC controllers and most of the app |
| `@DataJdbcTest` | Spring Data JDBC repositories | Mapping/query/data behavior | MVC and regular services |
| `@JsonTest` | JSON mapper, modules, JSON components | Serialization/deserialization, field types | HTTP server/controllers, database |
| `@RestClientTest` | REST client under test and HTTP mock infrastructure | Outbound method/path/headers/body | Full web server, DB |
| `@WebClientTest` | WebClient-related client slice | Reactive client requests/responses | Full application flow |
| `@GraphQlTest` | GraphQL schema/controller-related infrastructure | GraphQL queries/responses | Full DB/services by default |

The underlying annotations and actual artifacts can differ between Spring Boot 3.x and 4.x. In **Spring Boot 4**, test modules/starters are split more granularly by function, such as `spring-boot-starter-webmvc-test` and `spring-boot-starter-data-jpa-test`. Avoid copying 3.3 packages/imports into 4.x without checking the migration guide.

### 4.1. Is `@SpringBootTest` a Slice?

**No.** `@SpringBootTest` loads the Spring Boot application context according to the application's configuration, typically spanning a broader scope than a slice. It works with **`@AutoConfigure…`** annotations such as `@AutoConfigureMockMvc`, yet should not be paired with `@WebMvcTest` or `@DataJpaTest` as a way to stack two slices.

Comparison:

```java
// RIGHT: pick one MVC slice to test the controller.
@WebMvcTest(AccountController.class)
class AccountWebTest { }

// RIGHT: pick one JPA slice to test the repository.
@DataJpaTest
class AccountJpaTest { }

// RIGHT: pick full Boot context, add MockMvc infrastructure.
@SpringBootTest
@AutoConfigureMockMvc
class AccountFlowTest { }

// NOT SUPPORTED: two test slices on the same class.
@WebMvcTest(AccountController.class)
@DataJpaTest
class WrongMixedSlicesTest { }

// AVOID: mixing full Boot bootstrap with slice bootstrap.
@SpringBootTest
@WebMvcTest(AccountController.class)
class WrongFullPlusSliceTest { }
```

All classes above are **annotation comparison patterns**, lacking imports/beans to run standalone. The last two classes are intentional anti-patterns. Do not keep them in a real build's test sources.

## 5. Why Can't You "Add" Slices Together by Stacking Annotations?

### 5.1. Bootstrap Mechanism Conflict

A Spring Boot slice annotation can be meta-annotated with `@BootstrapWith` to pick a specialized `TestContextBootstrapper`. For example, in Boot 3.3, MVC and JPA slices use distinct specialized test bootstrappers; each bootstrapper governs how context customizers, auto-configurations, and exclusions are applied.

Two slice annotations on the same class can cause Spring TestContext to see **more than one incompatible `@BootstrapWith` declaration**, failing during bootstrapping. The exact message depends on the Boot/Framework version, yet the class of problem is identical: the framework is not designed to infer a "merged bootstrapper" from two independent slice types.

Typical error output (illustrative, not guaranteed character-for-character):

```text
IllegalStateException:
Configuration error: found multiple declarations of @BootstrapWith
...
@WebMvcTest ...
@DataJpaTest ...
```

Seeing this error does not mean a Maven/Gradle dependency is missing. Inspect **the annotations and meta-annotations on the test class** before trying to add starters.

### 5.2. Different Component-Scanning Rules

`@WebMvcTest` focuses on controllers and web components; `@DataJpaTest` focuses on entities/repositories and persistence. Trying to put both together leaves ambiguous questions:

- Should `@Service` beans be scanned?
- Should ControllerAdvice/security be loaded?
- Should repositories be filtered out?
- What scope do EntityManager/DataSource have?
- Should a reader treat the test as web-only, DB-only, or end-to-end?

What the test author actually wants is probably an **integration test**, yet the test annotations declare two distinct narrowing boundaries.

### 5.3. Auto-Configuration Is Not Unconditional Addition

Each slice imports a list of auto-configurations and applies `@OverrideAutoConfiguration`/type-exclude filters/test customizers via its own mechanism. Adding another layer's configuration group without knowing its prerequisites can cause beans to:

- fail to be created because conditions are unmet;
- duplicate existing beans;
- require a datasource or web environment that is not ready;
- get excluded by the original slice's filter;
- collide on bean names or conditional configurations;
- appear without the collaborators needed to run for real.

**Adding an `@AutoConfigure…` does not automatically turn an MVC slice into a full integration context.** Certain configuration groups can be imported deliberately, provided you verify all prerequisites and evidence; do not interpret that as "successfully stacking two slices."

## 6. Design Principle: Choose One Observable Contract

Before picking an annotation, describe **the behavior you want to prove**:

| Question | Smallest reasonable boundary | What runs for real |
| --- | --- | --- |
| Does `GET /accounts/41` return the right JSON? | `@WebMvcTest(AccountController.class)` | Controller/MVC/JSON |
| Does JPA save an account with a unique code and query it back? | `@DataJpaTest` | Entity, repository, datasource |
| Does the service compute opening balance properly? | JUnit unit test | Service/domain |
| Does the service coordinate with the real repository without needing HTTP? | `@DataJpaTest` + `@Import` a specific service, or service integration test | Service + JPA |
| Does `POST /accounts` return 201 and write the account to the DB? | `@SpringBootTest` + `@AutoConfigureMockMvc` | Controller, service, repository |
| Does real HTTP over sockets write to the DB? | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Real server + app + DB |
| Does a JSON record serialize according to contract? | `@JsonTest` | JSON mapper/modules |
| Does the REST client send the right URL/headers/body? | `@RestClientTest` | Client + mock server |

**Do not choose annotations because the test "needs many beans."** First identify the external boundary the test must observe: **HTTP boundary, persistence boundary, or integration flow**. Annotations are just tools for building the environment matching that goal.

## 7. Runnable Example: Java 17, Spring Boot 3.3.0, JUnit Jupiter

This example suite compares **four valid tests** on the same simple Account application:

1. **MVC slice:** Real controller, mocked service, no database.
2. **JPA slice:** Real repository and H2 test database, no controller.
3. **JPA slice with imported service:** Real service + real repository, no MVC.
4. **Full integration:** Real controller → service → repository, MockMvc, H2.

We pin **Spring Boot 3.3.0** and Java 17 for consistent imports. This is an illustrative baseline for the 3.x API; production should use an approved patch release and verify security/support status. H2 serves demo testing purposes and does not automatically prove every semantic detail of production PostgreSQL/MySQL.

### 7.1. Project Structure

```text
slice-boundaries-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── SliceDemoApplication.java
    │   ├── Account.java
    │   ├── AccountRepository.java
    │   ├── AccountView.java
    │   ├── AccountService.java
    │   └── AccountController.java
    └── test/java/example/
        ├── AccountControllerSliceTest.java
        ├── AccountRepositorySliceTest.java
        ├── AccountServiceJpaSliceTest.java
        └── AccountFlowIntegrationTest.java
```

### 7.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'slice-boundaries-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Both `spring-boot-starter-web` and `spring-boot-starter-data-jpa` are on the main classpath, yet **that does not cause every slice to load all beans**. Slice boundaries are determined by test annotations/configuration, not merely by which dependencies are present.

Here H2 sits only on the **test runtime classpath**; running the app via `bootRun` outside tests would require separate database/driver configuration. The primary verification commands for this example are `./gradlew test` and running individual test classes.

### 7.3. Main Application

**`src/main/java/example/SliceDemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceDemoApplication.class, args);
    }
}
```

Placing this class in package `example` lets the remaining classes in that package be component-scanned in a full application context. Slice tests use the primary configuration to locate application scope while applying their own slice filters.

### 7.4. JPA Entity

**`src/main/java/example/Account.java`:**

```java
package example;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private long balance;

    protected Account() {
        // JPA requires a no-arg constructor.
    }

    public Account(String code, long balance) {
        this.code = code;
        this.balance = balance;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public long getBalance() {
        return balance;
    }
}
```

The file uses `jakarta.persistence` per Spring Boot 3.x, rather than `javax.persistence` from older Spring Boot 2.x projects. `IDENTITY` works with H2 in the demo; with another production database, verify the generation strategy and actual schema.

### 7.5. Spring Data Repository

**`src/main/java/example/AccountRepository.java`:**

```java
package example;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<Account, Long> {
    Optional<Account> findByCode(String code);
}
```

Spring Data JPA generates the repository interface implementation in the JPA context. `findByCode` derives from the entity's `code` property name. Thus, the JPA slice can test the query method without a controller.

### 7.6. DTO and Service

**`src/main/java/example/AccountView.java`:**

```java
package example;

public record AccountView(
        Long id,
        String code,
        long balance) {}
```

**`src/main/java/example/AccountService.java`:**

```java
package example;

import java.util.NoSuchElementException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public AccountView create(String code, long openingBalance) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException(
                    "account code is required");
        }
        if (openingBalance < 0L) {
            throw new IllegalArgumentException(
                    "negative opening balance");
        }

        Account saved =
                repository.save(new Account(code, openingBalance));

        return new AccountView(
                saved.getId(), saved.getCode(), saved.getBalance());
    }

    @Transactional(readOnly = true)
    public AccountView get(Long id) {
        Account found = repository.findById(id)
                .orElseThrow(() -> new NoSuchElementException(
                        "account " + id + " not found"));

        return new AccountView(
                found.getId(),
                found.getCode(),
                found.getBalance());
    }
}
```

The service belongs to the business layer and is not auto-scanned by `@WebMvcTest`. It needs the real repository when testing persistence, or can be replaced with a mock when testing only controller mapping. `@Transactional` on the service works only when invoked through an appropriate Spring proxy; a unit test using `new` does not trigger transaction advice.

### 7.7. Controller

**`src/main/java/example/AccountController.java`:**

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {
    public record CreateAccountRequest(
            String code,
            long balance) {}

    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public AccountView get(@PathVariable Long id) {
        return service.get(id);
    }

    @PostMapping
    public ResponseEntity<AccountView> create(
            @RequestBody CreateAccountRequest request) {
        AccountView created =
                service.create(request.code(), request.balance());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }
}
```

The controller simply delegates to the service and turns the data into an HTTP response. The exercise focuses on the happy path; the example omits validation annotations, exception handlers, and security. Accordingly, **do not assume** invalid inputs automatically return 400/404/409 unless corresponding mappings are implemented.

## 8. Test 1 — Choosing Only `@WebMvcTest` to Test HTTP

**`src/test/java/example/AccountControllerSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerSliceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    AccountService service;

    @Test
    void mapsGetAndSerializesAccountJson() throws Exception {
        when(service.get(41L))
                .thenReturn(new AccountView(41L, "AC-41", 5000L));

        mvc.perform(get("/api/accounts/{id}", 41L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.code").value("AC-41"))
                .andExpect(jsonPath("$.balance").value(5000));

        verify(service).get(41L);
    }
}
```

### What Is Proven

- `AccountController` is discovered by Spring MVC with route `GET /api/accounts/{id}`.
- Path variable `41` binds to `Long`.
- The controller invokes the `AccountService` bean in the MVC test context.
- HTTP status 200 and JSON fields `id`, `code`, `balance` match the simulated service result.
- No real TCP HTTP server: `MockMvc` runs in a mock servlet environment.

### What Is **Not** Yet Proven

- Whether `AccountService.get` queries the repository properly: the service is mocked.
- Whether JPA mapping/queries work: JPA is outside the slice's scope.
- Whether account 41 actually exists in the database: the JSON comes from a Mockito stub.
- HTTP network/connection behavior on a real server: there is no `RANDOM_PORT`.

In **Spring Boot 3.3**, `@MockBean` is imported from `org.springframework.boot.test.mock.mockito`. For Spring Boot 3.4+/Framework 6.2+ and Boot 4, check `@MockitoBean` and the corresponding test starters — do not mix imports across major versions.

**If Spring Security is on the classpath:** `@WebMvcTest` can activate security filters. This test does not add the security starter, so no principal/CSRF setup is needed. In a real project, HTTP 401/403 may be valid security behavior rather than a missing controller bean; use Spring Security Test if needed.

## 9. Test 2 — Choosing Only `@DataJpaTest` to Test the Repository

**`src/test/java/example/AccountRepositorySliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
class AccountRepositorySliceTest {
    @Autowired
    TestEntityManager entityManager;

    @Autowired
    AccountRepository repository;

    @Test
    void persistsAndFindsAccountByCode() {
        entityManager.persistAndFlush(
                new Account("AC-77", 7000L));
        entityManager.clear();

        Account found = repository.findByCode("AC-77")
                .orElseThrow();

        assertEquals("AC-77", found.getCode());
        assertEquals(7000L, found.getBalance());
    }
}
```

### What Is Proven

- The `Account` entity is discovered by JPA.
- The schema in the H2 test database is generated according to the configured mapping.
- `AccountRepository.findByCode` runs successfully with SQL/JPA.
- State can be reloaded after `flush` and `clear`ing the persistence context.
- The test runs inside `@DataJpaTest`'s default transaction and rolls back afterward when managed by the framework.

### What Is **Not** Yet Proven

- Whether the MVC controller returns the right HTTP response.
- Whether other services outside JPA scope are scanned by Spring.
- Complete compatibility with production PostgreSQL/MySQL dialects, constraints, or locking.
- That data was committed and visible to another transaction: the test rolls back by default.

`TestEntityManager` is a JPA test utility in Boot 3.3 that helps persist/flush/clear when testing entities/repositories. It **does not automatically add Spring MVC beans**.

**When a database matching production is needed:** use Testcontainers or a dedicated test database, configuring `@AutoConfigureTestDatabase(replace = NONE)` properly with the right driver/JDBC URL instead of mixing in `@WebMvcTest`. Account for transactions, cleanup, and container startup time.

## 10. Test 3 — One JPA Slice, Adding Only the Needed Service with `@Import`

This solves a common need: "I want to test the service with the real repository, without web." Instead of stacking `@DataJpaTest` with `@WebMvcTest`, keep the JPA slice and **add one specific application bean**.

**`src/test/java/example/AccountServiceJpaSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest(properties =
        "spring.jpa.hibernate.ddl-auto=create-drop")
@Import(AccountService.class)
class AccountServiceJpaSliceTest {
    @Autowired
    AccountService service;

    @Autowired
    AccountRepository repository;

    @Test
    void usesRealServiceAndRealRepositoryWithoutWeb() {
        AccountView created =
                service.create("AC-88", 8800L);

        assertEquals("AC-88", created.code());
        assertEquals(8800L, created.balance());

        Account fromDatabase = repository.findByCode("AC-88")
                .orElseThrow();

        assertEquals(8800L, fromDatabase.getBalance());
    }
}
```

Here there is only **one slice annotation**: `@DataJpaTest`. `@Import(AccountService.class)` registers the exact service under test in the slice context; the service's dependency `AccountRepository` is supplied by the JPA slice. No controller, `MockMvc`, or server is needed.

### When Does `@Import` Fit?

- A service has just a few clear dependencies and all of them exist in the JPA slice.
- A small converter/configuration supports serializers/repositories.
- A test bean/fake needs to be added to the context.
- A policy or validator is tested alongside an adapter without pulling in the entire app.

### When Does `@Import` Become Dangerous?

If you `@Import` a large `@Configuration` carrying application-wide `@ComponentScan`, `@EnableScheduling`, HTTP clients, security, or numerous `@Bean` definitions depending on remote services, the slice boundary can expand excessively. The test stops being "lightweight" or "clearly scoped," even though the class still bears only `@DataJpaTest`.

**Rule:** import a small, explainable set of beans; do not import the whole application configuration just to avoid writing an integration test. If the service truly depends on MVC + database + message broker, choose an appropriate full integration test.

## 11. Test 4 — Needing Real HTTP and JPA: `@SpringBootTest` + `@AutoConfigureMockMvc`

When the contract requires:

> Sending `POST /api/accounts` must return HTTP 201 with the right account JSON, and that account must be queryable from the database.

This is a **multi-layer flow**, no longer a single slice. The clean approach is using the **full Boot context** and adding MockMvc test infrastructure.

**`src/test/java/example/AccountFlowIntegrationTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = SliceDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
@AutoConfigureMockMvc
@Transactional
class AccountFlowIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    AccountRepository repository;

    @Test
    void postReturns201AndPersistsReadableAccount() throws Exception {
        mvc.perform(post("/api/accounts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"code":"AC-99","balance":9900}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value("AC-99"))
                .andExpect(jsonPath("$.balance").value(9900));

        Account persisted = repository.findByCode("AC-99")
                .orElseThrow();
        assertEquals(9900L, persisted.getBalance());

        mvc.perform(get("/api/accounts/{id}", persisted.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("AC-99"))
                .andExpect(jsonPath("$.balance").value(9900));
    }
}
```

**This is a valid combination**, because:

- `@SpringBootTest` selects the bootstrapper and **full context scope**.
- `@AutoConfigureMockMvc` adds/configures `MockMvc` for that context. It is **not** a second `@…Test` slice annotation.
- `@Transactional` wraps the test method in a test-managed transaction when a transaction manager is present, rolling back by default; synchronous `MockMvc` in a mock servlet environment normally runs on the test thread.
- H2 is used at test runtime; the schema is created per test properties.
- Controller, service, and repository are all **real beans** in the application.

### What Is Proven

- `POST` mapping/JSON request, service, JPA save, and HTTP 201 body flow through real beans in the Spring context.
- The repository finds the newly written account inside the **test transaction**.
- `GET` retrieves the account by its saved ID and returns the expected JSON.

### What Is Not Yet Proven

- Real TCP HTTP socket/server: `MockMvc` does not open a network port.
- Commit/visibility from another transaction: the test is `@Transactional` and rolls back afterward.
- Exact production SQL dialect or transaction behavior if the real DB is PostgreSQL/MySQL.
- Effects of other remote services, since the example has none.

If testing real HTTP is required, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `TestRestTemplate`/an appropriate HTTP client; in that mode, server threads and the test thread have separate transactions, so **test rollback does not roll back server-committed data**. You need real fixture isolation/cleanup, rather than assuming `MockMvc` semantics.

## 12. Running the Sample Tests and Interpreting Results

The project requires a compatible Gradle Wrapper (e.g., Gradle 8.5 with Boot 3.3.0), JDK 17+, and repository access:

```bash
./gradlew test
./gradlew test --tests example.AccountControllerSliceTest
./gradlew test --tests example.AccountRepositorySliceTest
./gradlew test --tests example.AccountServiceJpaSliceTest
./gradlew test --tests example.AccountFlowIntegrationTest
```

On Windows:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.AccountFlowIntegrationTest
```

With the example code, **4 test methods are expected to pass** (one method per class). Gradle typically finishes with `BUILD SUCCESSFUL` when tasks succeed; task counts, timings, and startup logs are not fixed and should not be asserted against.

You do not need to keep a "stacked-slice" test inside the source tree to verify it fails: it is an **anti-pattern explicitly documented by Spring Boot as unsupported**. If you want to observe the error mechanics, try it only on a sandbox branch and revert it, never committing it to project CI.

**Observing runtime differences:** the MVC slice typically avoids spinning up a JPA database; the JPA slice needs no MVC dispatcher; the full-context integration test creates both. Watch those boundaries in logs and bean listings rather than comparing total durations alone.

## 13. What Does "One Slice + Another Auto-Config" Actually Mean?

Spring Boot 3.3 documentation notes that if you need extra test capabilities, **choose one `@…Test` annotation and explicitly add `@AutoConfigure…` annotations from other areas**, or use `@AutoConfigure…` alongside `@SpringBootTest` when slicing is not needed.

This **does not contradict** the "do not stack slices" rule:

- `@WebMvcTest` and `@DataJpaTest` are both **slice selectors**, each carrying its own bootstrapper, filters, and context design.
- `@AutoConfigureMockMvc` is **test auto-configuration enabling MockMvc**, not an independent context slice selector.
- `@AutoConfigureTestDatabase` is test database configuration, not `@DataJpaTest`.
- `@Import` registers a chosen bean/configuration.
- `@ImportAutoConfiguration` can import a specific auto-configuration via Boot's mechanism when needed.

Valid examples:

```java
// One Boot context, adding MockMvc infrastructure:
@SpringBootTest
@AutoConfigureMockMvc
class HttpAndPersistenceFlowIT {
    // ...
}

// One JPA slice, adding a specific business bean:
@DataJpaTest
@Import(AccountService.class)
class ServiceWithJpaIT {
    // ...
}

// One MVC slice, mocking an out-of-scope collaborator:
@WebMvcTest(AccountController.class)
class AccountWebTest {
    @MockBean AccountService service;
}
```

These are **configuration patterns**, requiring the application class, imports, and real test logic in practice. They do not imply you can slap `@AutoConfigureMockMvc` onto `@DataJpaTest` and automatically get a full MVC context: a JPA slice may lack a servlet web application context, MVC controllers, and all `MockMvc` prerequisites. If you find yourself adding lots of infrastructure just to make a test run, recognize that you are writing an **integration test**.

### 13.1. `@Import` and `@ImportAutoConfiguration` Differ

- **`@Import`**: imports a specific Java configuration/bean class, such as `@Import(AccountService.class)`. Suited for helper beans or application components you explicitly select.
- **`@ImportAutoConfiguration`**: imports **auto-configuration classes** in the Spring Boot-supported way for tests, instead of using regular `@Import` to load an auto-configuration with incorrect semantics. Boot supports `@ImportAutoConfiguration(exclude=...)` and selective annotation-driven importing.

Do not import the entire `@SpringBootApplication` inside a slice just to "restore" filtered-out beans. That easily turns the test into a hybrid context harder to reason about than `@SpringBootTest`.

### 13.2. Adding Test Collaborators Deliberately

When a controller needs a service, three options exist:

1. **Mock the service:** `@WebMvcTest` + `@MockBean`/`@MockitoBean`, testing the HTTP contract.
2. **Import the real service into the MVC slice:** only when the service is truly lean, all its dependencies can be supplied cleanly, and you want to test service logic near MVC; note the boundary is now wider. If the service needs a repository, the MVC slice does not bring JPA along automatically.
3. **Full integration:** `@SpringBootTest` + `@AutoConfigureMockMvc` with real repositories/database, testing multiple layers.

Choose based on **the risk that needs verification**, not just on writing fewer annotations.

## 14. Wrong or Misleading Combinations

| Combination | Assessment | Why |
| --- | --- | --- |
| `@WebMvcTest` + `@DataJpaTest` | **Not supported** | Two competing slice selectors/bootstrap contexts |
| `@WebMvcTest` + `@JsonTest` | **Not supported** | Two slice selectors, not JSON addition |
| `@DataJpaTest` + `@JdbcTest` | **Not supported** | Two slice selectors with distinct auto-configurations |
| `@SpringBootTest` + `@WebMvcTest` | **Do not use to combine contexts** | Full Boot and slice bootstrap are not a designed combination |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | **Valid** | Full context + test utility |
| `@DataJpaTest` + `@Import(AccountService.class)` | **Valid when dependencies are clear** | One slice + specified bean |
| `@WebMvcTest` + `@MockBean Service` | **Valid in Boot 3.3** | Real controller + mocked service |
| `@DataJpaTest` + `@AutoConfigureTestDatabase` | **Valid when DB needs configuring** | One slice + test database choice |
| `@RestClientTest` + `@WebMvcTest` | **Not supported** | Client and server slices serve different goals |
| `@SpringBootTest` + `@AutoConfigureWebTestClient` | **Can fit depending on stack/goal** | Full context + WebTestClient utility for matching version |

Every `@AutoConfigure…` choice still requires checking technology prerequisites, classpath, and version. "Structurally valid annotations" does not guarantee the bean graph starts in every application.

## 15. Test Slices and Spring Security

With `spring-boot-starter-security` on the classpath, an MVC slice may include security-related infrastructure and filters. If a test expects HTTP 200 yet gets 401/403, the reason is not automatically "missing JPA slice."

Right fixes:

- Decide whether the controller contract requires identity, roles, and CSRF.
- Use Spring Security Test, such as `@WithMockUser` and MockMvc request postprocessors when appropriate.
- If you want to test real security filters, keep them inside the test scope.
- Disable filters with `@AutoConfigureMockMvc(addFilters=false)` only in tests where filter behavior is **truly out of scope**, and document that the test **no longer proves security**.

Adding `@DataJpaTest` will not solve HTTP 401/403. Conversely, if a security policy requires loading accounts from the DB, that may be a real integration test using a full context and test DB.

## 16. JPA Slice: Embedded Database, Transactions, and Limits

`@DataJpaTest` typically:

- loads entities and Spring Data JPA repositories;
- uses an embedded database available on the classpath when suitable;
- configures `TestEntityManager`;
- runs each test in a transaction rolled back by default;
- excludes many application services/controllers from component scanning.

Pitfalls to avoid:

1. Passing on H2 does not guarantee production PostgreSQL query dialects work identically.
2. `saveAndFlush`/`persistAndFlush` + `clear` checks queries after flushing, yet **does not prove commits** if the test transaction rolls back.
3. `@Transactional(propagation=NOT_SUPPORTED)` can disable the test-managed transaction when necessary, though you must manage cleanup and fixtures properly.
4. `@AutoConfigureTestDatabase(replace=NONE)` can be used when deliberately preserving a supplied datasource (e.g., Testcontainers); verify that connection **is not a production DB**.
5. `@DataJpaTest` does not start an HTTP server or provide `MockMvc`.

If a repository must verify unique constraints, locking, transaction isolation, or native SQL, choose a database matching reality. If testing simple derived queries, an H2 test database gives fast feedback and easy isolation.

## 17. Spring TestContext Cache: The More Tangled the Scope, the Harder the Cost to Understand

Spring TestContext maintains a context cache keyed by the merged configuration: classes/locations, active profiles, test properties, context customizers, bean overrides, initializers, and loader.

When tests are split along clear boundaries:

```text
AccountControllerSliceTest (@WebMvcTest + mock service)
    -> MVC context A

AccountRepositorySliceTest (@DataJpaTest)
    -> JPA context B

AccountServiceJpaSliceTest (@DataJpaTest + @Import service)
    -> JPA context C (config differs from B)

AccountFlowIntegrationTest (@SpringBootTest + MockMvc)
    -> Full Boot context D
```

The contexts in the example differ because their configurations differ. **Loading separate contexts for good reasons** is not bad: each test proves a distinct behavioral layer.

Conversely, if every test class arbitrarily imports a different mix of `@Configuration` classes and mocks, cache keys can explode. The suite slows down and injection errors become harder to diagnose. Do not use `@DirtiesContext` to "clean up" unclear annotation mixes; it forces repeated reloads.

**Important:** the context cache does not reset singleton bean state. In the JPA slice, rollback handles only data inside the test's managed transaction; a runner or service that committed at startup will not roll back automatically. Keep fixtures/DB state independent and free of test execution order.

## 18. Anti-Pattern Snippets and Minimal Fixes

### Scenario A: Web Slice Missing `AccountService`

Wrong direction:

```java
@WebMvcTest(AccountController.class)
@DataJpaTest // Trying to bring in repository so service appears.
class IncorrectTest { }
```

Fix when only HTTP needs testing:

```java
@WebMvcTest(AccountController.class)
class ControllerOnlyTest {
    @MockBean
    AccountService service;
}
```

If you truly want real service + database: do not combine both slices; choose `@SpringBootTest` + `@AutoConfigureMockMvc`.

### Scenario B: JPA Slice Missing Service

Wrong direction:

```java
@DataJpaTest
@WebMvcTest(AccountController.class)
class IncorrectServiceTest { }
```

If the service only needs the repository and you want to test the use case at the database boundary:

```java
@DataJpaTest
@Import(AccountService.class)
class ServiceRepositoryTest {
    @Autowired AccountService service;
}
```

When the service has many collaborators outside JPA, a JPA slice test may no longer fit; use a full context or unit tests with fakes/Mockito.

### Scenario C: Full Integration Needing MockMvc

Wrong direction:

```java
@SpringBootTest
@WebMvcTest(AccountController.class)
class WrongFullTest { }
```

Fix:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullHttpFlowTest {
    @Autowired MockMvc mvc;
}
```

**Key distinction:** `@AutoConfigureMockMvc` merely configures test infrastructure, whereas `@WebMvcTest` defines an independent slice. If you want real HTTP sockets, use `RANDOM_PORT` instead of assuming `MockMvc` sends requests over the network.

### Scenario D: Using `@Import` to Bypass Boundaries

Risk:

```java
@WebMvcTest(AccountController.class)
@Import(BigProductionConfiguration.class)
class ExpandingSliceTest { }
```

This code may compile, yet if a hypothetical `BigProductionConfiguration` scans every bean and triggers DB/events, the context becomes unpredictable. Review which beans are added, which filters still apply, and what external effects run. If you need the whole application, state the integration goal and use `@SpringBootTest` instead of stretching a slice past recognition.

Snippets in this section are **abbreviated configuration examples**, not standalone runnable test classes; undeclared types are illustrative. Complete code appears in sections 7–11.

## 19. Debug by the Actual Error, Not by Reflexively Adding Annotations

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `found multiple declarations of @BootstrapWith` | Multiple slice/full bootstrap annotations on the class | Remove conflicting annotation; pick one context strategy |
| `No qualifying bean of type AccountService` in MVC test | `@WebMvcTest` does not scan ordinary services | Mock collaborator or use full context |
| `NoSuchBeanDefinitionException` when `@DataJpaTest` injects controller | JPA slice does not load MVC | Remove controller from JPA test or use full context |
| `NoSuchBeanDefinitionException: MockMvc` in JPA test | No MVC auto-config/context | Do not mix MVC; choose full + `@AutoConfigureMockMvc` |
| `Failed to configure DataSource` | Missing DB driver, URL, credentials, or test DB | Check H2/Testcontainers/profiles |
| HTTP 401/403 in web test | Spring Security filters/CSRF | Check authentication/security test setup |
| `@SpringBootConfiguration` not found | Test package or primary config cannot be located | Place test in the right package or set `classes=...` |
| Duplicate/ambiguous beans | Overly broad `@Import` or multiple impls of same type | Narrow configuration; use `@Qualifier`/`@Primary` with justification |
| Very slow test startup | Oversized full context or too many cache keys | Return tests to proper slices; trim arbitrary imports/mocks |
| JPA test passes yet production SQL fails | H2 differs in dialect/schema/locking | Test against a DB compatible with production |
| HTTP test passes yet DB has no record | Service is mocked or persistence is out of scope | Add an integration test at the right boundary |
| Build passes without running tests | Wrong JUnit Platform/engine/filter | Check discovered and executed test counts |
| Repeated `Failed to load ApplicationContext` | Spring context failure threshold after first failure | Find the root cause of the first context load failure |

### 19.1. Root-Cause Troubleshooting Workflow

1. Inspect **the exact test class** and its list of annotations/meta-annotations.
2. Identify the boundary under test: HTTP, JPA, client, JSON, or full integration.
3. Check whether the missing dependency/bean belongs in the expected scope.
4. Read the first stack trace of `Failed to load ApplicationContext`; separate bootstrap errors from bean/runtime errors.
5. Check active profiles, bean overrides, datasource properties, and classpath.
6. Make the **smallest justified change**: mock the collaborator, import a small service, or move to a full context.
7. Re-run both the individual class and the full suite to catch state/context-cache issues.
8. Inspect executed test counts and assertions, not trusting `contextLoads` passing alone.

**Do not fix symptoms by throwing `@SpringBootTest` or every starter onto the class.** That can hide the root cause by loading extra beans, slowing tests down and blurring scope.

## 20. Version Knowledge: Spring Boot 3.x and 4.x

The sample project pins **Spring Boot 3.3.0** to run with these imports:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.mock.mockito.MockBean;
```

In Spring Boot **3.4+**, Spring Framework 6.2 introduces `@MockitoBean` to replace `@MockBean` (old Boot annotation deprecated). In **Spring Boot 4**, testing is split into functional modules/starters and package imports can change, for example:

```java
// Spring Boot 4.x: check the matching module/starter before importing.
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

These two import sets are **version-specific alternatives**, never mixed in one Java class. In Boot 4, starters such as `spring-boot-starter-webmvc-test` and `spring-boot-starter-data-jpa-test` bring in their respective test modules, yet **having both starters in the build does not mean you can stack both slices on the same test class**.

The rule "do not stack multiple `@…Test` annotations" does not depend on old vs. new import names: it reflects how Spring Boot designs context slicing.

When upgrading:

- Upgrade the Spring Boot BOM in lockstep with Framework, JUnit, Mockito, and test starters.
- Migrate `@MockBean` to `@MockitoBean` in the appropriate release line, checking bean override semantics.
- Update slice/test auto-configuration imports to match the version.
- Keep the four boundary tests like sections 7–11 to verify each boundary still guards behavior.
- If a new slice lacks a bean, find the right module/configuration instead of restoring every bean unconditionally.
- Do not force Boot 3.x artifacts into a Boot 4 BOM just to keep an old annotation alive.

## 21. Practice: Choose the Boundary Instead of Adding Annotations

### Exercise 1 — Fix a Stacked-Slice Test

Put the following code on a learning branch, **never keeping it in CI**:

```java
@WebMvcTest(AccountController.class)
@DataJpaTest
class CombinedTest { }
```

Explain why Spring Boot does not support two slice selectors on the same class. Pick one of two directions:

- Goal is HTTP JSON → keep `@WebMvcTest`, mock the service.
- Goal is `POST` returning 201 and writing to DB → `@SpringBootTest` + `@AutoConfigureMockMvc`.

**Criterion:** learners can state which contract each direction proves.

### Exercise 2 — Widen Scope When Requirements Change

Initially the test only required the controller to return `{"code":"AC-41"}` when the service supplied an account. Later the product owner requires: "A successful POST must create a real record in the DB." Why is simply adding `@DataJpaTest` to the MVC test wrong? Convert the test to a full context, letting the real service/repository run, and query the DB after the request.

### Exercise 3 — Keep a JPA Slice Lean with `@Import`

Use `AccountServiceJpaSliceTest` from the example. Remove `@Import(AccountService.class)`: the service is no longer scanned in the JPA slice, so injection fails. Add it back. Explain why neither controller nor MVC is needed to test the service against the repository.

### Exercise 4 — Catching Mocks That Hide Scope Gaps

In `AccountControllerSliceTest`, temporarily break production `AccountService.get` to return the wrong code. The MVC slice can still pass because the service is mocked. In `AccountFlowIntegrationTest`, alter service logic in the experiment branch to return wrong data; the GET/DB assertions must catch the mutation affecting the contract. Restore the code afterward.

**Lesson:** no single isolated test proves every layer by default. Know each test's blind spots and supplement with the right layer of evidence.

### Exercise 5 — Do Not Abuse Full Contexts

Time `AccountControllerSliceTest` and `AccountFlowIntegrationTest` on the same machine after warm-up. Explain why the full context is usually heavier, without treating a single measurement as universal law. Caching, classpath, JVM, and database all affect results.

### Exercise 6 — Real Transactions and Databases

Swap H2 for Testcontainers PostgreSQL on a learning branch. Configure the datasource and `@AutoConfigureTestDatabase(replace=NONE)` if appropriate. Compare constraint/schema/query behavior between the two DBs. Never use a production database, and never rely on test rollback to clean up transactions committed in another request.

### Exercise 7 — Classify Annotations

For each annotation below, classify it as a **slice selector**, **full context selector**, or **test infrastructure customizer**:

| Annotation | Classification |
| --- | --- |
| `@WebMvcTest` | Slice |
| `@DataJpaTest` | Slice |
| `@JsonTest` | Slice |
| `@RestClientTest` | Slice |
| `@SpringBootTest` | Full context |
| `@AutoConfigureMockMvc` | Test auto-configuration |
| `@AutoConfigureTestDatabase` | Test database configuration |
| `@Import(AccountService.class)` | Explicit bean import |
| `@MockitoBean` / `@MockBean` | Bean override/test double |

Explain why **two selectors** differ from **one selector plus one customizer**.

## 22. Test Boundary Review Checklist

- [ ] Can I describe the expected test verification in one business sentence?
- [ ] Does the test class have **exactly one context strategy**: one slice or full Spring Boot context?
- [ ] Not stacking `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`... on the same class.
- [ ] Not putting `@WebMvcTest` on `@SpringBootTest` to be "both full and slice."
- [ ] Did I distinguish `@AutoConfigure…` from `@…Test` slice selectors?
- [ ] Are mocked services/repositories genuinely **outside the test's goal**?
- [ ] When an out-of-slice bean is needed, did I choose a mock, small `@Import`, or full integration with clear justification?
- [ ] Did I avoid importing a large production configuration that accidentally breaks slice boundaries?
- [ ] For MVC tests, did I assert status/JSON/headers/security contracts?
- [ ] For JPA tests, did I assert persist/query/constraints/transactions appropriately?
- [ ] For multi-layer tests, did I use a full context and observe both HTTP and persisted state when needed?
- [ ] Is the test DB a safe environment, never pointing at production; are rollback/commit semantics understood?
- [ ] Do I recognize H2 does not guarantee all production DB behaviors?
- [ ] Do I understand that test context caching can reuse contexts and share singleton state?
- [ ] Did I verify the matching Spring Boot version, test starters, and imports?
- [ ] When tests fail, do I find the root cause instead of reflexively adding slice annotations?
- [ ] Did I run on the proper JUnit Platform and verify the actual executed test count?

## 23. End-of-Lesson Decision Diagram

```text
What outcome needs verification?
    |
    +--> Pure calculation/service logic?
    |       -> JUnit + Mockito/fake, no Spring needed.
    |
    +--> HTTP mapping/JSON?
    |       -> @WebMvcTest + mock services outside the slice.
    |
    +--> Repository/JPA?
    |       -> @DataJpaTest + test database.
    |
    +--> Service + JPA, no web needed?
    |       -> @DataJpaTest + @Import(small service)
    |          or service integration test.
    |
    +--> Real controller + service + DB?
            -> @SpringBootTest + @AutoConfigureMockMvc
               (or RANDOM_PORT if a real socket is needed).

Do not do:
    @WebMvcTest + @DataJpaTest
    @WebMvcTest + @JsonTest
    @SpringBootTest + @WebMvcTest

Add @AutoConfigure... / @Import only when you know the exact
prerequisites and boundary to preserve.
```

**Core message:** a test slice is an **intentional exclusion decision**, not pieces of a Spring context you can arbitrarily stack together. The more real layers you want to verify, the sooner you should switch to an explicitly declared integration test with `@SpringBootTest`, rather than turning a slice into an unexplainable half-web, half-JPA context.

## 24. Official Documentation

- Spring Boot 3.3 — Testing Spring Boot Applications, "Auto-configured Tests": https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Test slices and auto-configuration list: https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html
- Spring Boot — Testing Spring Boot Applications (current line): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Test Modules (4.x line): https://docs.spring.io/spring-boot/reference/testing/test-modules.html
- Spring Boot — Test Slices appendix (current line): https://docs.spring.io/spring-boot/appendix/test-auto-configuration/slices.html
- Spring Framework — TestContext Framework: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Testing Transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
