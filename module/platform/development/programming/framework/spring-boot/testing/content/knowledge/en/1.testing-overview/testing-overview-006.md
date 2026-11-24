# Roles of JUnit, Spring Test, Spring Boot Test, Mockito, and Testcontainers

## 1. The Big Picture: Each Tool Solves One Job

When testing a Spring Boot application, we need to answer different questions: Is the business calculation right? Does Spring instantiate and wire beans properly? Are HTTP requests handled accurately? And does the application work properly with a real PostgreSQL instance or dependent service? No single library answers all of them on its own.

| Component | Core Responsibility | Identifying Markers | What It Does **Not** Guarantee Alone |
| --- | --- | --- | --- |
| **JUnit Jupiter (JUnit 5)** | Defines, runs, and asserts Java test results | `@Test`, `@BeforeEach`, `assertEquals`, `assertThrows` | Does not create a Spring context, mock dependencies, or provide a database |
| **Mockito** | Creates test doubles for collaborators and verifies interactions when needed | `@Mock`, `when(...).thenReturn(...)`, `verify(...)` | Does not prove JDBC, HTTP, DI configuration, or external systems work for real |
| **Spring Test (Spring Framework)** | Integrates JUnit with Spring TestContext, DI, and framework testing utilities | `SpringExtension`, `@SpringJUnitConfig`, `MockMvc`, `@Transactional` | Does not automatically boot all Spring Boot auto-configuration |
| **Spring Boot Test** | Brings Boot auto-configuration conventions to tests; provides full-app and slice tests | `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` | Does not automatically turn fake dependencies into real services; `@SpringBootTest` also does not mean an HTTP port is always opened |
| **Testcontainers** | Provisions real dependent services inside containers for tests | `@Testcontainers`, `@Container`, `PostgreSQLContainer` | Does not replace JUnit, assertions, Mockito, or Spring Test; typically requires a container runtime such as Docker |

A single test can use **JUnit + Mockito**, **JUnit + Spring Test**, **JUnit + Spring Boot Test**, or **JUnit + Spring Boot Test + Testcontainers**. These are composable roles, not five mutually exclusive choices.

Mental model:

```text
JUnit Jupiter: defines tests, invokes tests, asserts pass/fail
  ├─ Mockito: replaces collaborators with mocks when logic isolation is needed
  └─ Spring Test: builds and manages Spring TestContext, supports DI/MockMvc
       └─ Spring Boot Test: adds Boot auto-configuration, test slices,
            @SpringBootTest, and Boot utilities
                 └─ Testcontainers: provides real databases/brokers/services for tests
```

This diagram illustrates **roles in a testing strategy**, not an inheritance hierarchy across all libraries. Testcontainers can be used directly with JUnit without Spring.

## 2. JUnit Jupiter: Execution Framework and PASS/FAIL Criteria

JUnit 5 consists of JUnit Platform (the foundation for running tests), Jupiter (the API and engine for writing/running tests), and support for other engines. When people say “write JUnit 5 tests”, they usually mean **JUnit Jupiter**.

- `@Test`: marks a test method; a failing assertion or unexpected exception causes the test to FAIL.
- `@BeforeEach` / `@AfterEach`: setup and cleanup around each test; `@BeforeAll` / `@AfterAll` apply to the class lifecycle.
- `assertEquals`, `assertTrue`, `assertThrows`, `assertAll`: express expected outcomes.
- `@ParameterizedTest` with a parameter source: tests multiple cases under the same rule.
- `@Nested`, `@DisplayName`: organize tests readably.
- Extension API, such as `MockitoExtension` or `SpringExtension`: hooks additional capabilities into the JUnit lifecycle.

Good tests follow **Arrange → Act → Assert**: prepare data, execute one action, then verify observable behavior. Test names should describe the condition and outcome, such as `rejectsNegativeSubtotal`.

JUnit **does not require Spring**. If an object contains only plain Java logic and can be instantiated directly, running the test directly is faster and has fewer dependencies.

## 3. Mockito: Isolating Collaborators, Not Simulating the Whole System

Suppose `CheckoutService` needs a `DiscountPolicy`. The unit test's goal is to verify `CheckoutService`'s billing decision without yet testing how `DiscountPolicy` retrieves data elsewhere. Mockito provides a stand-in object where outputs can be configured and calls observed.

- `@Mock` or `mock(...)`: creates a mock; unconfigured behavior returns default values by return type.
- `when(mock.method(...)).thenReturn(...)`: configures return results; `doThrow(...).when(mock)...` is useful for other cases.
- `verify(mock).method(...)`: confirms a key interaction; assert only when the interaction is part of the behavioral contract.
- `@InjectMocks`: Mockito attempts to instantiate/inject mocks into the object under test; it does **not** start a Spring ApplicationContext.
- `@ExtendWith(MockitoExtension.class)`: integrates mocks and test lifecycle with JUnit Jupiter.

### Standalone Java 17 Example: JUnit + Mockito

This small Gradle project **does not need Spring Boot**. Create two files:

`settings.gradle`:

```groovy
rootProject.name = 'checkout-unit-testing'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.mockito:mockito-junit-jupiter:5.15.2'
}

test {
    useJUnitPlatform()
}
```

`src/test/java/CheckoutServiceTest.java`:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {
    interface DiscountPolicy {
        int discountFor(int subtotal);
    }

    static final class CheckoutService {
        private final DiscountPolicy policy;

        CheckoutService(DiscountPolicy policy) {
            this.policy = policy;
        }

        int total(int subtotal) {
            if (subtotal < 0) {
                throw new IllegalArgumentException("subtotal must be nonnegative");
            }
            return subtotal - policy.discountFor(subtotal);
        }
    }

    @Mock
    DiscountPolicy policy;

    @Test
    void calculatesTotalAfterDiscount() {
        when(policy.discountFor(100)).thenReturn(15);

        int actual = new CheckoutService(policy).total(100);

        assertEquals(85, actual);
        verify(policy).discountFor(100);
    }

    @Test
    void rejectsNegativeSubtotalWithoutConsultingPolicy() {
        CheckoutService checkout = new CheckoutService(policy);

        assertThrows(
                IllegalArgumentException.class,
                () -> checkout.total(-1)
        );
        verifyNoInteractions(policy);
    }
}
```

In a directory with Gradle installed, run:

```bash
gradle test
```

Or if the project has a Gradle Wrapper, run `./gradlew test` (Linux/macOS) or `gradlew.bat test` (Windows). **2 tests** execute: the first expects total `85`; the second expects `IllegalArgumentException` and no calls to the policy. JUnit reports failure if an assertion fails. Do not hardcode expected stdout because Gradle formats logs depending on version and configuration.

**Example limitation:** mocks prove `CheckoutService` logic under assumed policy behavior; they do not test a real `DiscountPolicy` implementation, Spring DI, or database connectivity. Never mock the class under test itself and only `verify` its own calls: the test would verify no real business outcome.

## 4. Spring Test: Testing When Spring Framework Participates

`spring-test` brings **Spring Framework** testing mechanics into JUnit:

1. `SpringExtension` connects JUnit Jupiter's lifecycle to the Spring TestContext Framework. `@SpringJUnitConfig` is a convenience annotation combining the extension and context configuration.
2. TestContext initializes/caches `ApplicationContext`, supporting `@Autowired` injection, test configuration, active profiles, property sources, and test execution listeners.
3. `MockMvc` simulates calls into the Spring MVC layer through `DispatcherServlet` **without a real HTTP server**. It differs from Mockito: “Mock” in MockMvc refers to running MVC requests in-process inside the test.
4. Supports transaction management in Spring integration tests; for tests running in a framework-managed transaction, rollback can occur after the test depending on configuration.

Example loading only a tiny Spring context, not a full Boot application:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ClockSpringTest.FixedClockConfig.class)
class ClockSpringTest {
    @Configuration
    static class FixedClockConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Autowired
    Clock clock;

    @Test
    void injectsConfiguredBean() {
        assertEquals(2024, LocalDate.now(clock).getYear());
    }
}
```

Place the file at `src/test/java/ClockSpringTest.java` in a project with `spring-test`, `spring-context`, and JUnit Jupiter (usually provided via `spring-boot-starter-test`). This test verifies Spring creates and injects the `Clock` bean from the given configuration. It does not prove the entire Boot application starts.

**Note on context caching:** Spring Test usually reuses contexts sharing the same configuration across tests to save time. Switching profiles, configuration, or overusing `@DirtiesContext` increases context recreation. Tests must not depend on mutable state/variables left behind by a preceding test.

## 5. Spring Boot Test: Choosing the Right Context Scope

Spring Boot builds on Spring Test and Boot conventions. In an application using Spring Boot 3.3.x, the standard test dependency is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This dependency snippet assumes the project already uses the Spring Boot plugin or Boot dependency management. The test starter supplies JUnit Jupiter, Mockito, Spring Test, AssertJ, and common test utilities. There is no need to spin up a Spring context in every test just because the starter is present.

### 5.1. Slice Tests: Loading Only the “Slice” to Verify

- `@WebMvcTest(MyController.class)`: focuses on Spring MVC (routes, binding, validation, status, JSON, matching exception handlers); collaborators outside the MVC slice typically need mocks or extra configuration.
- `@DataJpaTest`: verifies JPA entities, repositories, mapping, and queries with Data JPA configuration. By default it uses an embedded test database if available; with real PostgreSQL, configure explicitly so it does not auto-replace with an embedded DB.
- `@JdbcTest`: focuses on JDBC and related beans.
- `@JsonTest`: verifies JSON serialization/deserialization.
- `@RestClientTest`: verifies HTTP clients and related configuration within the slice.

For example, suppose the app already has a `GreetingController` serving `GET /greetings/{name}`, which calls `GreetingService.greet(name)` and returns a string. Test in Boot 3.3.x:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    GreetingService greetingService;

    @Test
    void returnsGreetingFromHttpEndpoint() throws Exception {
        when(greetingService.greet("Lan")).thenReturn("Hello Lan");

        mvc.perform(get("/greetings/Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello Lan"));
    }
}
```

This test is an **integration snippet for an existing application**, requiring a controller and service matching the described contract. JUnit executes the test; `@WebMvcTest` builds the MVC slice; `MockMvc` dispatches a simulated request; `@MockBean` replaces the `GreetingService` dependency in the Spring context with a Mockito mock. It verifies mapping and HTTP response, yet **does not prove real service logic** or that the system is listening on a TCP port. If the app enables Spring Security, filter/security configuration affects results too; configure appropriate test user/authorization instead of treating `401/403` as a controller bug.

**Version distinction:** in Spring Boot 3.3.x, Boot's `@MockBean` is the common way to replace a bean with a Mockito mock. Starting in Spring Boot 3.4 / Spring Framework 6.2, the newer API is `@MockitoBean`; do not copy that annotation into a Boot 3.3 project and assume it exists.

### 5.2. `@SpringBootTest`: Broader Scope

`@SpringBootTest` locates Boot configuration and loads an application context close to the real application. It fits when testing multi-layer wiring, auto-configuration, event handling, integration, or a flow spanning multiple beans.

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
        // PASSES if the context initializes successfully, not proof of business logic.
    }
}
```

By default, `@SpringBootTest` uses a `MOCK` web environment when applicable, **without starting an HTTP server on a real port**. To test real HTTP networking, use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` and an HTTP client; choose this only when you need to prove behavior over sockets/network. A `contextLoads` test is a configuration smoke test, not sufficient business evidence.

You can combine `@SpringBootTest` with `@AutoConfigureMockMvc` to test MVC inside a broader context without opening an HTTP port. The trade-off is that larger contexts usually start slower and are sensitive to databases, message brokers, or external configuration.

## 6. Testcontainers: Testing with Realistic Infrastructure Behavior

Mockito mocks are good for isolating interactions. However, SQL queries, transaction semantics, constraints, collations, migrations, message broker behavior, or dialect differences sometimes require a **real service**. Testcontainers launches temporary containers for PostgreSQL, MySQL, Redis, Kafka, and many other systems via a container runtime (commonly Docker).

Example test connecting to a real PostgreSQL instance in a Spring Boot 3.3.x application with `spring-boot-starter-jdbc` and the PostgreSQL driver:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

These dependencies assume Boot's BOM manages versions. In `src/test/java/.../DatabaseConnectionIT.java` of a Boot app that already has `@SpringBootApplication`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class DatabaseConnectionIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void connectsToRealPostgres() {
        Integer value = jdbcTemplate.queryForObject(
                "select 1", Integer.class
        );

        assertEquals(Integer.valueOf(1), value);
    }
}
```

Breakdown of responsibilities:

1. **JUnit** runs `connectsToRealPostgres` and compares the result.
2. **Testcontainers** manages the PostgreSQL container lifecycle for the test; a `static` field allows reusing the container across the class.
3. **Spring Boot Test** builds the application context and configures `JdbcTemplate`.
4. **`@ServiceConnection`** (Boot 3.1+) tells Boot how to obtain connection details from the PostgreSQL container; no need to hardcode a random port. Requires `spring-boot-testcontainers`.
5. **Real PostgreSQL** executes the SQL statement and returns `1`, so the test verifies end-to-end connectivity from Spring JDBC to the database inside the container.

This is an **integration pattern inside a configured Boot application**, not a standalone single-file program. Running it successfully requires an active container runtime, ability to pull the PostgreSQL image, Boot's plugin/dependency management, and no other app configuration causing the context to fail. It can be run with `./gradlew test --tests '*DatabaseConnectionIT'` if the class belongs to the `test` task; some projects define a separate `integrationTest` task and require adjustment.

An alternative way to connect containers to Spring configuration without `@ServiceConnection` is `@DynamicPropertySource` to supply `spring.datasource.url`, `username`, and `password` from the container. Use **one** clear connection management strategy and avoid declaring conflicting configuration values.

With `@DataJpaTest` or `@JdbcTest` needing a PostgreSQL container, check the slice's auto-replacement of DataSource; when necessary, use `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` to keep the Testcontainers DataSource. Testcontainers **does not automatically boot the full Spring context**, and not every unit test needs a container.

## 7. Choosing Tools by the Question You Need to Prove

| Test Question | Suggested Scope | Typical Tools Needed | Why |
| --- | --- | --- | --- |
| Are pricing rules / conditions / transformations right? | Unit test | JUnit; Mockito if collaborators exist | Pure Java logic, fast, isolated |
| Does a service call the mail port properly when handling a request? | Interaction unit test | JUnit + Mockito | Verifies collaborator call contract without sending real email |
| Does Spring create a bean from specific config and inject it properly? | Spring component test | JUnit + Spring Test | Needs a small `ApplicationContext` |
| Are the controller's URL, JSON, validation, and HTTP status right? | MVC slice | JUnit + Spring Boot Test `@WebMvcTest` + MockMvc; Mockito at service boundary | Needs MVC runtime without the whole app |
| Do repository/migrations/queries run properly on PostgreSQL? | Database integration | JUnit + Spring Boot Test slice or full + Testcontainers | Needs real database/dialect |
| Does a request flow cross multiple layers and persist to DB properly? | Integration/system test | `@SpringBootTest` + Testcontainers; HTTP client/MockMvc depending on goal | Tests wiring and real interactions across layers |

Rule for choosing test level: start at **the smallest level where the behavior to prove is observable**; broaden scope when the nature of the risk lies in wiring, serialization, HTTP/security filters, SQL dialect, or service integration. A test using more libraries is not automatically higher quality.

### Example: Breaking Down One Requirement

Requirement: “A valid order must deduct inventory stock and return `201 Created`; insufficient stock must return an appropriate error.”

- **JUnit + Mockito:** verify the service rejects the order when stock is insufficient; no DB needed.
- **`@WebMvcTest` + MockMvc:** verify the endpoint returns `201` or an error response, JSON mapping/request validation; mock the service to focus on MVC.
- **`@DataJpaTest` + Testcontainers PostgreSQL:** verify the stock-update query and constraints on real PostgreSQL.
- **`@SpringBootTest` + Testcontainers:** verify one critical flow passing through controller → service → repository → DB. If proving a real HTTP server is required, use `RANDOM_PORT`; if only MVC dispatch inside the app context is needed, consider MockMvc.

These tests **contribute distinct evidence**. You do not need to repeat every input variation across all four layers.

## 8. Common Confusions and Pitfalls

**1. Confusing `@Mock` with `@MockBean`.** `@Mock` only creates a Mockito object inside the test; it does not automatically replace a Spring bean when `@SpringBootTest` or `@WebMvcTest` builds the context. In Boot 3.3, `@MockBean` registers/replaces a bean in the context. Conversely, do not spin up a Boot context just to have Mockito inject a POJO.

**2. Confusing `MockMvc` with mocking a service.** MockMvc runs the Spring MVC pipeline without a real HTTP server; a Mockito-mocked service returns programmed responses. Thus `@WebMvcTest` can verify mapping/validation, yet does not prove the real service persists data.

**3. Using `@SpringBootTest` for every test.** Full application contexts consume resources, slow down tests, and introduce environment dependencies. Appropriate unit and slice tests are faster and pinpoint FAIL reasons more clearly. Broaden the context only when needed.

**4. Using an embedded database alone to extrapolate to production databases.** H2 or other embedded databases can differ from PostgreSQL in SQL syntax, locking, isolation, constraints, and data types. For DB-dependent logic, use Testcontainers to test the target engine.

**5. Assuming `@Transactional` always rolls back every change.** Test transactions managed by Spring Test can roll back operations inside the test thread's transaction. When `RANDOM_PORT` sends HTTP to a server running in a different thread/transaction, server-side commits are not automatically rolled back just because the test method has `@Transactional`. Clean up data or isolate state appropriately.

**6. Non-independent tests and shared data causing flakiness.** Avoid execution-order dependence, reusing the same record without cleanup, fixed-duration sleeps, hardcoded ports, or hitting production services. Build clear fixtures; assign distinct test names/IDs, manage cleanup, and wait on conditions for asynchronous work.

**7. Verifying every internal call.** Overly detailed `verify` calls cause harmless refactorings to break tests even when user-visible results stay unchanged. Prefer asserting on outputs and state. Use `verify` for meaningful interactions such as “send exactly one notification” or “do not call the payment gateway on invalid input”.

**8. Mistaking a running test for a meaningful test.** A `contextLoads` test only confirms the context starts. A test with weak assertions like `assertNotNull(service)` cannot substitute for checking outputs, errors, side effects, or interaction contracts.

## 9. How to Organize and Operate the Test Suite

In a Boot project, `src/test/java` holds JUnit classes; `src/test/resources` holds fixtures and test-specific configuration. Use clear names like `OrderServiceTest`, `OrderControllerTest`, and `OrderRepositoryIT` so readers understand the purpose. The `IT` suffix is only a naming convention: Gradle **does not automatically create a separate integration test task** because of that suffix; you must configure a source set/task if you want separate schedules.

A reference pipeline:

1. Run JUnit/Mockito unit tests frequently for fast feedback.
2. Run Spring MVC/JPA slice tests for framework contracts.
3. Run integration tests with PostgreSQL/Testcontainers for database and real-service paths.
4. Maintain a few smoke/E2E tests for critical flows, avoiding making the entire suite depend on multiple services on every commit.

In applications using the Gradle Wrapper, common commands:

```bash
./gradlew test
./gradlew test --tests '*CheckoutServiceTest'
./gradlew test --tests '*DatabaseConnectionIT'
```

On Windows use `gradlew.bat` instead of `./gradlew`. These commands run only classes belonging to the `test` task; a separate integration task must be defined in the build. Testcontainers requires an available container runtime locally/in CI; CI configuration must grant appropriate permissions and can cache images to reduce runtime.

### Checklist When Designing a Test

- **Behavior:** Which rule does the test protect? What observable outcome for users or external systems is asserted?
- **Boundary:** Does it truly need a Spring context, HTTP stack, transactions, or a real DB?
- **Dependencies:** Should collaborators be real objects, Mockito mocks, or Testcontainers services?
- **Independence:** Are data, time, execution order, network ports, credentials, and cleanup stable?
- **Speed/Reliability:** Does a slow test buy evidence that a smaller test cannot provide?
- **On FAIL:** Can you clearly tell whether the bug is in Java logic, wiring, MVC/security, persistence, or infrastructure?

## 10. Guiding Conclusion

**JUnit** is the organizer and judge of tests; **Mockito** isolates collaborators when needed; **Spring Test** provides framework and context testing utilities; **Spring Boot Test** determines which Boot application context or slice is tested; **Testcontainers** provides temporary real infrastructure to observe integration behavior. Choose them according to **the question you need to prove**, then verify with concrete assertions. Combining them this way yields a suite that is both fast at the logic layer and trustworthy at framework and infrastructure boundaries.