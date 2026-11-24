# Configuring Test Environments in Spring Boot: Sharing While Preserving Group Boundaries

## 1. Problem

A Spring Boot project may contain unit tests for business logic, MVC tests for controllers, JPA tests for repositories, and integration tests spanning multiple layers. All groups need certain shared conventions—such as Java/JUnit versions, the `test` profile, safe default properties, and test-data helpers. Yet **sharing configuration does not mean every test should share the same Spring context, database, mocks, or mutable state**.

Putting `@SpringBootTest`, `@Transactional`, `@MockitoBean`, and numerous `@Import`s onto a base class inherited by every test leads to these consequences:

- Unit tests that only need plain Java objects end up starting the entire `ApplicationContext`.
- MVC slices accidentally load repositories, databases, or external clients.
- JPA slices depend on out-of-scope web or service beans.
- Test A mutates singleton or static state, breaking Test B when running the full suite.
- Test A alters a property or active profile, changing the bean graph for another group.
- The context cache fractures due to uncontrolled minor overrides, slowing tests down and complicating debugging.

**Design goal:** share *stable conventions*, while letting each group control its own *test bootstrap, beans, data fixtures, transactions, mocks, and external resources*. That keeps test suites maintainable, fast, and order-independent.

## 2. Grouping by what needs to be proven

| Group | Framework / annotation | Required scope | Should not auto-load |
| --- | --- | --- | --- |
| Business unit | JUnit Jupiter, Mockito, `new Service(...)` | Java objects, boundary fakes/mocks | Spring context, web server, database |
| Controller / MVC | `@WebMvcTest(MyController.class)`, `MockMvc` | Controller, MVC infrastructure, mock services | JPA repositories, real business services, schedulers |
| Repository | `@DataJpaTest` | Entities, repositories, JDBC/JPA infrastructure, test database | Controllers, HTTP clients, messaging |
| Full integration | `@SpringBootTest` | Application wiring, services, repositories, required auto-config | Shared state from other test classes |
| Adapter / remote integration | Spring test with HTTP/broker/container stubs | HTTP client, serialization, timeouts/retries, real or stubbed resource | Production endpoints, hardcoded credentials, fixed ports |
| End-to-end / smoke | App running in a controlled environment | Full API/DB/message flow per contract | Assumption that test-thread transaction rollbacks roll back server state |

A group does not have to use Spring merely because the project uses Spring Boot. When testing a pricing formula or input boundary check, plain JUnit comes first.

### What should be shared?

- Test dependencies and versions managed via the Spring Boot parent/BOM, scoped to `test`.
- The `test` profile, safe default properties, and logging conventions.
- Data builders and assertion utilities **holding no mutable state**.
- Small composed annotations describing shared metadata only.
- CI conventions for tags, group naming, and required suites.

### What must be isolated or explicitly cleaned up?

- Mockito stubbings/interaction history, DB transactions, table rows, consumer offsets.
- Mutable singleton beans, static caches, thread-locals, and background executors.
- Ports, stub server expectations, Testcontainers state, and volumes.
- Files created by tests, test clocks, random seeds, credentials.
- Group-specific properties such as `spring.datasource.url` or `client.base-url`.

## 3. Separating "shared metadata" from "shared runtime"

Two tests can share **the same profile** yet create two distinct `ApplicationContext`s. Conversely, two test classes with equivalent merged configurations can **reuse the same context** via the Spring TestContext cache. Therefore:

- `@ActiveProfiles("test")` is shared metadata, not an instruction for every class to share one context.
- `@WebMvcTest` and `@DataJpaTest` use different bootstraps/configurations; sharing a profile does not turn them into full-context tests.
- Context reuse lets singleton beans live across multiple test classes. **Caching is not a data-isolation mechanism**.
- Multiple tests pointing at the same physical database can still clobber each other's data, even with separate contexts.
- A reused test container saving startup time still requires separate schemas/topics/namespaces or cleanup when tests have side effects.

A sensible boundary layout:

```text
src/
├── main/java/example/demo/          # Production components
└── test/
    ├── java/example/demo/
    │   ├── UseTestProfile.java       # Shared metadata for Spring tests
    │   ├── GreetingServiceUnitTest.java
    │   ├── GreetingControllerTest.java
    │   ├── CustomerNoteRepositoryTest.java
    │   └── FullAppIntegrationTest.java
    └── resources/
        ├── application-test.properties
        ├── fixtures/
        └── sql/
```

This layout is a suggestion, not a framework requirement. In larger systems, you can split into `unit`/`web`/`data`/`integration` packages, or separate Gradle/Maven modules when classpaths and resources genuinely diverge.

## 4. Sharing the test profile at the metadata level

A custom composed annotation carrying only `@ActiveProfiles("test")`:

```java
package example.demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ActiveProfiles("test")
@interface UseTestProfile {
}
```

Then Spring test classes can use:

```java
@UseTestProfile
@WebMvcTest(GreetingController.class)
class GreetingControllerTest { /* ... */ }

@UseTestProfile
@DataJpaTest
class CustomerNoteRepositoryTest { /* ... */ }

@UseTestProfile
@SpringBootTest
class FullAppIntegrationTest { /* ... */ }
```

The three declarations above are **illustrative**; complete code is in Section 8. `@UseTestProfile` does not boot a Spring context on its own; each **group's** annotation decides the bootstrap.

**Avoid:** creating a shared annotation containing `@SpringBootTest` and combining it with `@WebMvcTest` or `@DataJpaTest`. Bootstrap annotations can collide, and you unintentionally break slice boundaries. If you want a custom annotation for integration tests, name it clearly like `@FullIntegrationCheck` and use it solely for the full-context group.

### Shared property file

`src/test/resources/application-test.properties` is loaded by Boot when the `test` profile is active:

```properties
app.greeting-prefix=Shared
spring.jpa.hibernate.ddl-auto=create-drop
```

Here `app.greeting-prefix` is read by the application, whereas `spring.jpa.hibernate.ddl-auto` only applies to contexts with JPA. Shared properties do not turn `@WebMvcTest` into a data test. Never store passwords or production URLs in test resources.

If you write `external.enabled=false`, remember a property blocks networking only when production code checks it: **a property line alone does not disable external calls**. Tests that must avoid network calls should mock adapters or use stub servers rather than relying solely on a key name.

## 5. Targeted overrides in the right group

Spring Boot can load `application-test.properties` as a baseline while individual tests override selected keys:

```java
@UseTestProfile
@SpringBootTest
@TestPropertySource(properties = "app.greeting-prefix=Integration")
class FullAppIntegrationTest {
    // Assertions in the complete example section.
}
```

Spring TestContext's `@TestPropertySource` offers `locations` for files and `properties` for inline values; inline test properties outrank `@TestPropertySource` files, and dynamic properties from `@DynamicPropertySource` outrank `@TestPropertySource`. Spring Boot has additional property-source precedence rules; **assert real values via `Environment`** whenever multiple sources touch the same key.

### Controlled inheritance

| Annotation | Inheritance flag | Default | Point to understand |
| --- | --- | --- | --- |
| `@ActiveProfiles` | `inheritProfiles` | `true` | Subclasses can inherit parent profiles and add their own |
| `@TestPropertySource` | `inheritProperties` | `true` | Inherits inline properties from superclass |
| `@TestPropertySource` | `inheritLocations` | `true` | Inherits property files from superclass |
| `@ContextConfiguration` | `inheritLocations` | `true` | Inherits superclass resource locations/classes |
| `@ContextConfiguration` | `inheritInitializers` | `true` | Inherits context initializers |
| `@TestExecutionListeners` | `inheritListeners` | `true` | Can inherit custom test listeners |

For a subclass to replace parent profiles, use `@ActiveProfiles(profiles="special", inheritProfiles=false)`. Note this flag **does not automatically strip** `@TestPropertySource` or config classes from the parent. For test groups with distinct responsibilities, prefer small metadata annotations over a configuration-heavy superclass.

### Configuration inheritance with `@Nested`

JUnit `@Nested` creates non-static inner test classes. Spring TestContext provides `@NestedTestConfiguration(INHERIT/OVERRIDE)` to control inheriting test metadata from the enclosing class (defaulting to `INHERIT` since Spring Framework 5.3). A nested child can share the outer class's bootstrap, yet if it needs a completely different app context, consider making it a **separate top-level test class** to keep boundaries clear. Nested classes work best for grouping scenarios within the same scope.

## 6. Choosing the right bootstrap: `@SpringBootTest` vs. test slices

- `@SpringBootTest` builds the context via Spring Boot's `SpringApplication`. Default web environment is `MOCK` when a web stack is on the classpath: a web application context exists **without starting an embedded server**.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` launches a real server on a random port; client and server typically execute on separate threads and transactions.
- `@WebMvcTest` selects only MVC components and test MVC infrastructure; service collaborators must be mocked or minimally imported.
- `@DataJpaTest` loads the JPA slice, typically wrapping each method in a test-managed transaction rolled back afterward and substituting an embedded DB if available.
- `@SpringJUnitConfig` is shorthand for `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration`; it **does not automatically** enable Spring Boot auto-configuration.

**Do not place `@Enable...` or overly broad custom `@ComponentScan` on `@SpringBootApplication` just for one test.** Per Boot documentation, custom `@ComponentScan` configuration can disable test slice exclude filters; placing technology-specific setup in separate configuration classes lets slices select the right beans cleanly.

## 7. Principles for managing test beans and mocks

### Plain Mockito, `@MockitoBean`, and `@TestConfiguration`

| Tool | Where used | Effect |
| --- | --- | --- |
| `Mockito.mock(...)` / `@Mock` | Pure unit tests | Creates a mock object in Java/test instance |
| `@MockitoBean` | Spring context tests, Spring Framework 6.2+ | Replaces or supplies a mock bean in the context per contract |
| `@TestConfiguration` + `@Import` | Test groups needing specific fixture beans | Adds Spring beans scoped to that group |
| `@Primary` | Prioritizing one bean among multiple candidates | Selects bean on injection without removing others |
| `@DirtiesContext` | Context mutated beyond safe reset | Closes/evicts context from cache to reload |

In Spring Boot 3.4/3.5, legacy `@MockBean` is deprecated; `@MockitoBean` in `org.springframework.test.context.bean.override.mockito.MockitoBean` is the current path. Boot 4 splits test starters by technology and continues using `@MockitoBean`. Never put mocks in static fields shared across groups.

### `@TestConfiguration` for a group needing a `Clock`

Illustrative **snippet needing imports and a real service**:

```java
@TestConfiguration(proxyBeanMethods = false)
class FixedClockConfig {
    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2024-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}

@UseTestProfile
@SpringBootTest
@Import(FixedClockConfig.class)
class PriceCalculationIntegrationTest {
    // Only this test requires a fixed clock.
}
```

With top-level `@TestConfiguration`, import it explicitly in the group that needs it. With static nested `@TestConfiguration` inside a Boot test, Boot adds it onto the app config. Do not confuse this with static nested `@Configuration`, because Boot treats those two differently during test configuration discovery.

## 8. Complete hands-on example: four test groups sharing one profile

The example uses **Java 17, Maven, Spring Boot 3.5.0, Spring MVC, JPA, JUnit Jupiter, and Mockito**. Everything runs from one POM without Docker or external databases.

### 8.1. Structure

```text
test-boundaries-demo/
├── pom.xml
└── src/
    ├── main/java/example/demo/
    │   ├── DemoApplication.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   ├── CustomerNote.java
    │   └── CustomerNoteRepository.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/demo/
            ├── UseTestProfile.java
            ├── GreetingServiceUnitTest.java
            ├── GreetingControllerTest.java
            ├── CustomerNoteRepositoryTest.java
            └── FullAppIntegrationTest.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>test-boundaries-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`h2` in `test` scope provides an embedded database; real production apps need drivers and datasources matching their environment. The Boot parent manages starter/test dependency versions. Never override JUnit/Mockito versions arbitrarily.

File `src/test/resources/application-test.properties`:

```properties
app.greeting-prefix=Shared
spring.jpa.hibernate.ddl-auto=create-drop
```

File `src/test/java/example/demo/UseTestProfile.java` (dedicated file, defined once):

```java
package example.demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ActiveProfiles("test")
@interface UseTestProfile {
}
```

### 8.3. Production classes

`src/main/java/example/demo/DemoApplication.java`:

```java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/example/demo/GreetingService.java`:

```java
package example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final String prefix;

    public GreetingService(
            @Value("${app.greeting-prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        return prefix + " " + name.strip();
    }
}
```

In the Java code above, `@Value("${app.greeting-prefix:Hello}")` uses Spring's placeholder syntax: if the property is supplied, it uses that value; if absent, it defaults to `Hello`. The name `app.greeting-prefix` is an example, not a built-in Spring Boot property.

`src/main/java/example/demo/GreetingController.java`:

```java
package example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet(@RequestParam String name) {
        return service.greet(name);
    }
}
```

`src/main/java/example/demo/CustomerNote.java`:

```java
package example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_note")
public class CustomerNote {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String body;

    protected CustomerNote() {
    }

    public CustomerNote(String body) {
        this.body = body;
    }

    public Long getId() {
        return id;
    }

    public String getBody() {
        return body;
    }
}
```

`src/main/java/example/demo/CustomerNoteRepository.java`:

```java
package example.demo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerNoteRepository
        extends JpaRepository<CustomerNote, Long> {
}
```

Production classes have no knowledge of which test group calls them; they are never altered to "turn into mocks" in production profiles.

### 8.4. Unit test creating no Spring context

`src/test/java/example/demo/GreetingServiceUnitTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingServiceUnitTest {
    private final GreetingService service =
            new GreetingService("Manual");

    @Test
    void trimsNameWithoutStartingSpringContext() {
        assertEquals("Manual Lan", service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet("   "));
    }
}
```

Having `@Service` on a production class does not prevent a test from instantiating it with `new`. This test is fast and independent of `application-test.properties`.

### 8.5. MVC test loading only the web layer, with a mocked service

`src/test/java/example/demo/GreetingControllerTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@UseTestProfile
@WebMvcTest(GreetingController.class)
class GreetingControllerTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @MockitoBean
    GreetingService service;

    @Test
    void returnsHttpResponseFromMockedService() throws Exception {
        when(service.greet("Lan")).thenReturn("Web Lan");

        mvc.perform(get("/greet").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Web Lan"));

        verify(service).greet("Lan");
    }

    @Test
    void loadsWebSliceWithoutJpaRepository() {
        assertTrue(context.getBeansOfType(
                CustomerNoteRepository.class).isEmpty());
        assertTrue(Mockito.mockingDetails(service).isMock());
    }
}
```

Matching Boot 3.5, `@WebMvcTest` lives in `org.springframework.boot.test.autoconfigure.web.servlet`, and `@MockitoBean` lives in Spring Framework 6.2 `org.springframework.test.context.bean.override.mockito`. The controller verifies HTTP request/response handling, while `GreetingService`'s real logic is skipped because it is mocked.

### 8.6. JPA test with a database and no controllers

`src/test/java/example/demo/CustomerNoteRepositoryTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.ApplicationContext;

@UseTestProfile
@DataJpaTest
class CustomerNoteRepositoryTest {
    @Autowired
    CustomerNoteRepository repository;

    @Autowired
    ApplicationContext context;

    @Test
    void canSaveAndReadEntityInTestTransaction() {
        CustomerNote saved =
                repository.saveAndFlush(new CustomerNote("A"));

        assertNotNull(saved.getId());
        CustomerNote reloaded =
                repository.findById(saved.getId()).orElseThrow();
        assertEquals("A", reloaded.getBody());
    }

    @Test
    void jpaSliceExcludesWebAndServiceBeans() {
        assertTrue(context.getBeansOfType(
                GreetingController.class).isEmpty());
        assertTrue(context.getBeansOfType(
                GreetingService.class).isEmpty());
    }
}
```

`@DataJpaTest` creates a JPA slice using H2 from the test classpath and normally rolls back the transaction after each test. No test assumes the first ID is always `1`; identity/sequence counters may advance despite rollbacks. Repository tests need not mock controllers or services.

### 8.7. Full integration overriding a dedicated property

`src/test/java/example/demo/FullAppIntegrationTest.java`:

```java
package example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@UseTestProfile
@SpringBootTest
@TestPropertySource(properties =
        "app.greeting-prefix=Integration")
class FullAppIntegrationTest {
    @Autowired
    GreetingService service;

    @Autowired
    CustomerNoteRepository repository;

    @Test
    void groupOverrideIsVisibleInFullContext() {
        assertEquals("Integration Lan", service.greet("Lan"));
        assertNotNull(repository);
    }
}
```

MVC, JPA, and full integration all share `@UseTestProfile`; yet only full integration overrides `app.greeting-prefix`, and only full integration creates the full application context. By default `@SpringBootTest` does not start an embedded HTTP server; this test verifies wiring and bean properties.

### 8.8. Run commands and expected results

Requires JDK 17+, Maven, and repository access for initial dependency downloads. From the directory containing `pom.xml`:

```bash
mvn test
```

Or run individual groups:

```bash
mvn test -Dtest=GreetingServiceUnitTest
mvn test -Dtest=GreetingControllerTest
mvn test -Dtest=CustomerNoteRepositoryTest
mvn test -Dtest=FullAppIntegrationTest
```

Expected result per the example contract: **7 test methods PASS** (unit 2, MVC 2, JPA 2, full integration 1). The source makes no `System.out.println` calls so there is no fixed program stdout; Maven/Spring/Hibernate emit logs depending on version. On failure, inspect `target/surefire-reports`. This is the expected outcome of the example code and must actually be run in a dependency-ready environment to confirm.

| Test group | Test count | Evidence |
| --- | --- | --- |
| Unit | 2 | Instantiates service directly, verifies logic, no Spring context |
| MVC | 2 | HTTP response from mocked service, repository excluded |
| JPA | 2 | Entity saved/read on H2, controller/service excluded |
| Full integration | 1 | Real service and repository loaded, property override applied |

The crucial takeaway is that **the shared profile is still reused**, while each test class declares boundaries suited to its own goal.

## 9. Data isolation: a separate Spring context does not guarantee a separate database

### Rollbacks in `@DataJpaTest`

`@DataJpaTest` normally runs each test method inside a test-managed transaction and rolls it back afterward. That works well for DML inside that transaction, yet does not guarantee resetting everything:

- DDL, identity/sequence counters, or connection/session state may not roll back like DML.
- External HTTP/file/message side effects sit outside JDBC transactions.
- `REQUIRES_NEW` or transactions on other threads commit independently of the test transaction.
- When `@SpringBootTest(webEnvironment=RANDOM_PORT)` makes real HTTP requests, the server executes its own transactions, which do not roll back just because the client test has `@Transactional`.

For integration tests verifying real commits or multi-transaction flows, design explicit fixture cleanup instead of treating rollbacks as an absolute guarantee.

### Avoid fixed, colliding test data

- Avoid hardcoding ID `1L` for auto-generated primary keys.
- Create fresh data per test and clean up via transactions or fixture cleanup.
- If using `@Sql` seed scripts, place them only on DB-tier groups rather than globally on MVC/unit tests.
- When multiple test classes share one PostgreSQL container, consider distinct schemas/namespaces or controlled cleanup.
- With JUnit parallel execution enabled, never let two tests assume read/write ordering on a shared table.

### Files, clocks, static state

- For files, use JUnit's `@TempDir`; never write to the same hardcoded file path.
- For time, inject `Clock` and use `Clock.fixed(...)` in groups needing deterministic time.
- Avoid static mutable maps/caches in test builders; give each test fresh instances.
- `@DirtiesContext` creates a new context, yet **does not reset** static fields, files, or external databases outside the context.

## 10. Dynamic properties and real resources in integration tests

When integration tests use Testcontainers or random-port HTTP stubs, pass runtime values to Spring:

```java
// Snippet: requires Testcontainers dependency, Docker, and container startup lifecycle.
static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

`@DynamicPropertySource` typically uses a `static` method accepting `DynamicPropertyRegistry` and supplying `Supplier`s. The container must start properly in its lifecycle before properties are read. With Spring Boot 3.1+, `spring-boot-testcontainers` and `@ServiceConnection` can configure connection details instead of manual JDBC properties, depending on the container type.

**Cache warning:** when subclasses inherit a `@DynamicPropertySource` from a base class while each subclass uses a separate container with a different runtime URL, a cached context can retain connections to the old resource. Per Spring guidance, when dynamic properties vary across subclasses, consider `@DirtiesContext` or separate resource/context setups to keep values accurate. Never apply `@DirtiesContext` across the entire suite if the issue affects only one group.

### HTTP stubs and message brokers

HTTP adapter tests need random-port stub servers with recorded requests/mappings reset per test. Messaging integration tests need distinctly named test topics/consumer groups or clean teardown. Never embed production URLs/credentials in test sources; CI should inject test secrets if sandbox access is unavoidable. If a job requires a broker and the broker is unavailable, the test/job must fail—never turn outages into "skipped" tests to keep dashboards green.

## 11. Organizing pipelines and selecting test suites

You can annotate infrastructure-heavy tests with `@Tag("integration")`:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class RemoteGatewayContractTest {
    @Test
    void verifiesGatewayContract() {
        // Write assertions against a prepared stub or sandbox.
    }
}
```

This is a **snippet**, not proof a live gateway works. JUnit tags provide runner filtering metadata only; they do not start databases/containers or configure CI automatically.

| CI job | Suite | Infrastructure | Evaluation criteria |
| --- | --- | --- | --- |
| Fast PR | Unit, key MVC/slice tests | JDK, no external network | Behavior/validation pass |
| DB tests | JPA/repository slices | H2 or appropriate Testcontainers | Queries/schemas/transactions pass |
| Integration | Full app, external adapters | Containers, stubs/sandboxes, test secrets | Cross-layer wiring and contracts pass |
| Smoke | Controlled deployment | Live test system | Real API meets SLA |

Maven Surefire supports tag filtering via `groups`/`excludedGroups` on JUnit Platform, or Maven Failsafe with `*IT` naming and proper lifecycle bindings. **Renaming a class alone does not trigger Failsafe**; configure the plugin goals properly. Gradle supports filtering via `useJUnitPlatform { includeTags(...) }` in a dedicated task; if integration tags are excluded from the default task, make sure another CI job actually executes them. Verify discovered and executed test counts, not just `BUILD SUCCESS`.

### Standalone and parallel executability

Run a single test method, a single test class, and then the full suite. If a test fails only in suite runs, check static/shared state, DB rows, mock stubbings, fixed ports, thread-locals, and context caching. For intermittent failures, record seeds, timeouts, and resource lifecycles before adding retries. Automatic CI retries hide flakiness; a test suite's job is to deliver stable, reproducible evidence.

## 12. Optimizing the Spring TestContext cache properly

Spring TestContext caches `ApplicationContext` instances by **merged context configuration**, not by class name. The cache key reflects configuration classes, context loaders, profiles, properties, initializers, context customizers (including mock beans and dynamic property methods), and hierarchy.

- Two tests with matching types and configurations reuse the context → saving startup time.
- Adding a `@TestPropertySource` or `@MockitoBean` override produces a distinct cache key.
- `@DirtiesContext` closes/evicts that context so subsequent tests reload a fresh one.
- The cache is in-process; separate Maven/Gradle JVM forks do not share a static cache.
- Singleton beans persist across test classes sharing a cached context, so they must stay stateless or reset cleanly per lifecycle.

**Never sacrifice test isolation just to lower context count.** When two groups test different behaviors, separate contexts make sense; meaningful optimization comes from avoiding accidental overrides, minimizing `@DirtiesContext`, and using unit/slice tests where possible.

If Spring contexts reload too frequently, enable test context cache debug/statistics in a diagnostic run to see where classes/profiles/properties diverge before restructuring the suite.

## 13. Common test-organization mistakes

| Symptom | Why it happens | Fix |
| --- | --- | --- |
| `@WebMvcTest` asks for a datasource | Overly broad import/component scan or base class carries integration bootstrap | Narrow app config, use a true web slice |
| `@DataJpaTest` loads controllers | Custom scan or `@Import` drags in web beans | Preserve JPA slice, drop out-of-scope configs |
| Unit tests boot the full Boot context | Base `@SpringBootTest` applied to all tests | Use plain JUnit/Mockito and `new` |
| One property override alters multiple groups | Oversized shared base/config | Move overrides to the specific group needing them |
| Separate contexts still corrupt each other's data | Shared DB/schema/file/broker | Use transactions/cleanup or separate namespaces |
| Contexts reload constantly | Overusing `@DirtiesContext` or reckless overrides | Audit cache keys and lifecycles |
| Test passes alone, fails in suite | Shared mutable singletons/statics, fixed ports | Clean state, fresh fixtures, random ports |
| MVC test calls a real service that hits the network | Collaborator not mocked at the boundary | Use `@MockitoBean` for service/adapter and verify |
| `@DataJpaTest` fails on DB URL | Missing embedded DB, driver, or test datasource | Add H2/Testcontainers and explicit test config |
| Full test at `RANDOM_PORT` leaves server data unrolled back | Test and server run in separate transactions/threads | Clean up DB or test commits explicitly |
| Test profile seems ignored | Missing `@ActiveProfiles` or meta-annotation not applied | Assert `Environment.getActiveProfiles()` and properties |
| CI stays green while skipping integration tests | Tag filters/task lifecycles missing an integration job | Add a dedicated job and check test counts |
| Spring Boot 4 misses slice annotations | Module splits and package renames | Add focused technology test starters |

## 14. Upgrading from Spring Boot 3 to 4

Boundary principles stay the same, though Spring Boot 4 splits test modules by technology. The runnable examples in this lesson target **Boot 3.5.0**:

- Boot 3.5 typically builds on `spring-boot-starter-test`; `@WebMvcTest` and `@DataJpaTest` live in `org.springframework.boot.test.autoconfigure...` packages.
- Boot 4 introduces focused test starters such as `spring-boot-starter-webmvc-test` and `spring-boot-starter-data-jpa-test`. Technology test annotations move packages accordingly.
- Spring Framework 6.2+/Boot 3.4+ uses `@MockitoBean`; legacy `@MockBean` is deprecated and removed in newer releases.
- Let the parent/BOM align Spring Framework, JUnit, Mockito, and H2/Testcontainers versions; never mix major versions manually.

When upgrading, first confirm dependency trees/imports and executed test counts in the runner, then address application behavior changes. Do not dump every focused starter into every module just to force the build green.

## 15. Design and acceptance checklist

- [ ] Grouped unit/MVC/JPA/full integration/external tests appropriately by purpose?
- [ ] Pure unit tests avoid `@SpringBootTest` just to obtain a bean?
- [ ] Shared annotations hold safe metadata only, never multiple bootstrap annotations?
- [ ] Test profiles declared consistently with zero production credentials?
- [ ] `@TestPropertySource`/`@Import`/`@MockitoBean` overrides scoped strictly to groups that need them?
- [ ] MVC slices never pull in JPA repositories or unintended external dependencies?
- [ ] JPA slices use proper test DBs/transactions and stay independent of other tests' state?
- [ ] Full integration tests verify real wiring while cleaning up side effects?
- [ ] No shared static mutable objects or fixed ports/files/paths causing races?
- [ ] Testcontainers/HTTP stubs have explicit lifecycles and isolated resources?
- [ ] Dynamic properties align with context caching and container lifecycles?
- [ ] `@DirtiesContext` reserved solely for contexts truly dirtied beyond safe reset?
- [ ] CI job actually executes integration-tagged tests or separated source sets?
- [ ] All tests pass standalone and across the full suite, including parallel mode if enabled?
- [ ] Checked executed/filtered/skipped test counts rather than just build exit status?

### Decision matrix for applying to other projects

| Question | If "yes" | Choice |
| --- | --- | --- |
| Only testing Java logic? | No Spring bean wiring needed | Plain JUnit/Mockito unit tests |
| Need HTTP mappings/validation? | No real repositories needed | MVC slice with mocked collaborators |
| Need queries/entities/transactions? | No controllers needed | JPA slice with test DB |
| Need Boot auto-config across multiple layers? | Startup cost acceptable | `@SpringBootTest` |
| Need remote/broker behavior? | Real I/O or stub contracts | Integration tests + resource lifecycles |
| Only sharing a standard profile? | Groups still choose distinct bootstraps | Small composed `@ActiveProfiles` annotation |
| Need custom beans/properties for one group? | Unsuitable as global defaults | Group-specific `@Import`/`@TestPropertySource` |

## 16. Official references

1. [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): full-context, slices, configuration discovery, `@TestConfiguration`, and test caching.
2. [Spring Boot 3.5 – Test Auto-configuration Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): components included in each test slice.
3. [Spring Framework – Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): merged context keys, cache behavior, and `@DirtiesContext`.
4. [Spring Framework – Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): precedence and inheritance of `@TestPropertySource`.
5. [Spring Framework – Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource`, Testcontainers, and cache considerations.
6. [Spring Framework – Active Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html): `@ActiveProfiles` and `inheritProfiles`.
7. [Spring Framework – Meta-Annotation Support](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-meta.html): composed annotations for tests.
8. [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): service connections and resource lifecycles.
9. [JUnit Jupiter – Tags and Filtering](https://docs.junit.org/5.13.4/writing-tests/tagging-and-filtering.html): grouping tests and selecting suites.
10. [Spring Boot Reference – Testing](https://docs.spring.io/spring-boot/reference/testing/): comparing module layouts when using Boot 4.

**Key takeaway:** share **immutable conventions and metadata**, let each test group choose its own **Spring bootstrap and boundaries**, and proactively isolate **state and side effects**. Good shared configuration eliminates duplication; clear boundaries keep tests from breaking one another.