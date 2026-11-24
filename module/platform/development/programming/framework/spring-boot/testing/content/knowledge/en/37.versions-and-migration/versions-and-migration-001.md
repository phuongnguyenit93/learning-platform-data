# Comparing Spring Boot, Spring Framework, JUnit, Mockito, and Testcontainers

In the **Versions and Migration** group of the **Spring Boot - testing** module, a system can build green on an older version yet fail large numbers of unit, MVC, or database integration tests after a Spring Boot upgrade. The cause is not always business code: it can be **an incompatible Spring Framework line**, **conflicting JUnit API/engine/launcher versions**, **replaced or removed Mockito mock bean annotations**, or **incompatible Testcontainers modules/packages and Docker runtime**.

This lesson helps learners answer: which testing stack a Spring Boot 2.7, 3.3, 3.5, or 4.1 project uses; the role of dependency management/BOM; choosing unit, slice, and integration tests at the right layer; reading the dependency tree; and upgrading step-by-step with rollback capability. The primary example is built on **Java 17, Spring Boot 3.5.x, Spring Framework 6.2, JUnit Jupiter 5, Mockito 5, Testcontainers 1.x**. The migration section compares **Spring Boot 4.1.x + Spring Framework 7 + JUnit 6 + Testcontainers 2.x**.

The material includes complete source code for the domain, service, controller, Mockito tests, `@WebMvcTest` with `@MockitoBean`, a PostgreSQL integration test using `@ServiceConnection`, Gradle dependencies, and a Java SE program runnable with `javac/java` with its exact stdout stated. Gradle/JUnit/Docker commands are provided for **learners to run themselves**, not as a claim that the test suite was executed while authoring this lesson.

**Core rule:** do not randomly mix the "latest" libraries from five separate projects. **Choose an organization-approved Spring Boot release/BOM**, verify the Java/Gradle/Framework baseline, let the BOM manage JUnit/Mockito/Testcontainers, and then use the dependency graph and regression tests to verify.

## 1. What does each library handle?

```text
                  Spring Boot application
               + auto-configuration / starters
               + spring-boot-dependencies BOM
               + Spring Boot test slices
                           |
            +--------------+-------------+
            |                            |
            v                            v
      Spring Framework             Version alignment
      ApplicationContext           Gradle/Maven BOM
      WebMVC / TestContext                |
      SpringExtension                     |
      @MockitoBean                        |
            |                            |
            +-------------+--------------+
                          |
                          v
                   JUnit Platform
                discovery / execution
                          |
                          v
                     JUnit Jupiter
                 @Test / @BeforeEach
                          |
              +-----------+-------------+
              |                         |
              v                         v
           Mockito                 Testcontainers
      fake collaborator            real PostgreSQL,
      verify interactions          Kafka, Redis, etc.
              |                         |
              +-------------+-----------+
                            |
                   assertions / contracts
```

**Spring Framework**: IoC, MVC/WebFlux, `MockMvc`, Spring TestContext, `SpringExtension`, and framework-level bean overrides. **Spring Boot**: auto-config, starters, `@SpringBootTest`, `@WebMvcTest`, managed dependencies, `@ServiceConnection` integration. **JUnit**: platform/engine, lifecycle, assertions, extensions. **Mockito**: mocks, spies, stubs, and verification. **Testcontainers**: starts real dependencies in a Docker-compatible runtime. Testcontainers does not replace Mockito; Mockito does not prove database dialect behavior.

A `NoSuchMethodError` is usually different from a failing assertion. A Docker error is different from a missing Spring bean. Before changing code, **locate the layer of the failure**.

## 2. Compatibility Matrix Across Version Lines

| Boot line | Spring Framework line | Java baseline | JUnit | Mockito | Testcontainers | Notable changes |
| --- | --- | --- | --- | --- | --- | --- |
| Boot 2.7.x | Framework 5.3.x | Java 8+ | JUnit Jupiter 5 / legacy JUnit4 | Version per patch BOM | 1.x | Java EE `javax.*` ecosystem, legacy Boot test APIs |
| Boot 3.2/3.3.x | Framework 6.1.x | Java 17+ | Jupiter 5 + Platform 1.x | Mockito 5 on modern patches | 1.x | Jakarta `jakarta.*`; Boot 3.1+ has @ServiceConnection |
| Boot 3.4/3.5.x | Framework 6.2.x | Java 17+ | Jupiter 5 + Platform 1.x | Mockito 5 | 1.x | @MockitoBean since Framework 6.2, @MockBean deprecated |
| Boot 4.0/4.1.x | Framework 7.0.x | Java 17+ | JUnit 6 / Platform 6 | Mockito 5 | 2.x | Modular starters, relocated packages, Boot @MockBean removed |

**This is a line-level (major/minor) matrix, not a detailed BOM version lock for every release.** For example, from official documentation: Boot 3.5.16 requires Java 17 and Framework 6.2.19+; its dependency coordinates manage JUnit Jupiter 5.12.x, Mockito 5.x, and Testcontainers 1.21.x. Boot 4.1.2 requires Java 17, Framework 7.0.10+, and Gradle 8.14+ or 9.x; the 4.1 BOM manages JUnit 6 and Testcontainers 2. Patch numbers can change across release upgrades; check the version coordinates page **for the exact version being run** instead of copying blindly from a table.

Spring Framework 5.3 belongs to the Java EE 8/`javax.*` generation; 6.x follows Jakarta EE 9/10; 7.x has a Jakarta EE 11 baseline. Changing Servlet/JPA/Validation API namespaces can affect source code and tests independently of a JUnit upgrade.

## 3. JUnit 5 Is Not Just @Test, and JUnit 6 Is Not Just a Number Bump

Modern JUnit consists of:

- **JUnit Platform**: the launcher and `TestEngine` infrastructure used by Gradle/Maven/IDEs.
- **JUnit Jupiter**: the `org.junit.jupiter.api.Test` programming model, assertions, test lifecycle, parameterized tests, and extension APIs.
- **JUnit Vintage**: runs JUnit 3/4 tests before they are migrated; use it as a planned bridge, not a permanent default.

With JUnit 5, you typically have `junit-jupiter-api:5.x`, `junit-jupiter-engine:5.x`, and `junit-platform-launcher:1.x`. With JUnit 6, the Jupiter/Platform/Vintage JUnit modules all align on the **6.x** line and require Java 17+ at runtime. Jupiter Java imports such as `org.junit.jupiter.api.Test` and `Assertions.assertEquals` remain familiar. The danger is **overriding only the API to 6.x while leaving the engine at 5.x or Platform at 1.x** outside dependency management.

Enable Jupiter discovery in Gradle:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

The JUnit engine/launcher must be present on the test runtime classpath. Boot 3.5's `spring-boot-starter-test` pulls in JUnit/Jupiter infrastructure via the dependency BOM; you can add `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` without a version to keep the Gradle launcher aligned. For Maven, Surefire/Failsafe must support JUnit Platform and a compatible engine.

**Migrating JUnit 4 → Jupiter:**

| JUnit 4 | Jupiter |
| --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before`, `@After` | `@BeforeEach`, `@AfterEach` |
| `@BeforeClass`, `@AfterClass` | `@BeforeAll`, `@AfterAll` |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` or Boot integration annotation |
| `@RunWith(MockitoJUnitRunner.class)` | `@ExtendWith(MockitoExtension.class)` |
| `@Ignore` | `@Disabled` |
| `ExpectedException` rule | `assertThrows(ExactException.class,...)` |
| `@Category` | `@Tag` |

**Do not mechanically convert** rule/runner extensions that have special behavior. Compare the number of discovered tests before and after migration: a green build that actually skipped half the tests is a CI regression.

## 4. The BOM and Dependency Graph Matter More Than Hardcoded Versions

Spring Boot manages transitive library versions through the `spring-boot-dependencies` BOM. In Maven you can use `spring-boot-starter-parent` or import the BOM via `dependencyManagement`; Gradle uses the Boot Gradle plugin with appropriate dependency management.

An anti-pattern (do not use in a build):

```groovy
// Anti-pattern: versions mixed out of sync
testImplementation 'org.junit.jupiter:junit-jupiter-api:6.0.0'
testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine:5.12.2'
testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
testImplementation 'org.mockito:mockito-core:4.11.0'
testImplementation 'org.testcontainers:postgresql:2.0.5'
```

Problems: Jupiter 6/5/Platform 1 can be binary-incompatible; Mockito 4 differs in mock maker/Java support behavior; Testcontainers 2 renamed the `postgresql` artifact to `testcontainers-postgresql`. Mixing versions just to "pick the latest" can cause `ClassNotFoundException`, `NoSuchMethodError`, or test discovery failures.

**Practice:** declare BOM-managed dependencies **without versions**, print `testRuntimeClasspath`, and confirm the actual resolved versions. Only override the BOM if there is a reviewed reason (such as an urgent security fix), with compatibility verification and a rollback plan.

## 5. Spring Framework Test APIs vs. Spring Boot Test Slices

| Contract | Appropriate test | Guarantees | Does not guarantee |
| --- | --- | --- | --- |
| Pure Java logic | Jupiter, no Spring | Expected output/exceptions | MVC/DB |
| Service calling collaborator | Mockito unit test | Stubbing/interaction | Bean proxies/context |
| Controller mapping | Boot `@WebMvcTest` + MockMvc | HTTP status/JSON/binding | Remote TCP, real DB |
| Repository SQL | `@DataJdbcTest`/`@DataJpaTest` | SQL behavior on test DB | Entire full app |
| Auto-configuration | `ApplicationContextRunner` | Condition/bean presence | External service |
| Full application graph | `@SpringBootTest` | Integration of beans | All production outages |
| Real PostgreSQL | Testcontainers | JDBC/dialect/constraints | Production network/HA |

Spring Framework TestContext creates and caches an `ApplicationContext` for classes with compatible merged configurations. Spring Boot test slices limit beans/auto-config to stay fast and focused. **An MVC slice does not auto-load all `@Service` beans**, so `@MockitoBean` is needed to provide a service mock or `@Import` to bring in a real config/service.

The Spring context cache does not reset JVM static state or Docker volumes. If a test mutates a singleton's cache/state and the context is reused, other tests can be affected. `@DirtiesContext` only tells the framework to evict the context from the cache according to its lifecycle; it does not replace all isolation mechanisms.

## 6. Distinguishing Mockito @Mock, @InjectMocks, @MockitoBean, and @MockBean

| Usage | Library | Needs Spring? | Effect |
| --- | --- | --- | --- |
| `@Mock` | Mockito | No | Creates a mock object |
| `@InjectMocks` | Mockito | No | Mockito attempts to inject mocks into the object under test |
| `@Spy` | Mockito | No | Wraps a real object with a spy |
| `@ExtendWith(MockitoExtension.class)` | Mockito/Jupiter | No | Initializes mocks and lifecycle |
| `@MockitoBean` | Spring Framework 6.2/7 | Yes | Overrides or creates a mock bean in the test context |
| `@MockitoSpyBean` | Spring Framework 6.2/7 | Yes | Wraps a Spring bean with a Mockito spy |
| `@MockBean`/`@SpyBean` | Older Spring Boot | Yes | Boot bean override, deprecated in 3.4 and removed in 4 |

Imports:

```java
// Mockito unit test
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

// Spring Framework bean override
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

// Deprecated Boot 3.x API: do not use when upgrading to Boot 4
import org.springframework.boot.test.mock.mockito.MockBean;
```

This is only an **import reference**, not a Java class. `@Mock InvoiceService` in an MVC test does not make the Spring controller receive that bean; `@MockitoBean InvoiceService` is processed by Spring TestContext to create/override the bean.

Some `@MockitoBean` semantics are not 100% identical to Boot `@MockBean`: Spring Framework uses `REPLACE_OR_CREATE` by default; `enforceOverride=true` requires the bean to already exist; target selection uses qualifier/name and field-name fallback; overriding a non-singleton bean can turn it into a singleton mock. **Do not use `enforceOverride=true` mechanically** in an MVC slice where the real service is not part of the slice: in that case, the mock bean needs to be *created*.

If a mock replaces an AOP/proxied bean, the mock test does not prove that `@Transactional`/`@Cacheable`/`@Retryable` on the original bean actually runs. Those behaviors require integration tests against the real bean.

## 7. Complete Java 17 Reference Project

```text
compatibility-lab/
├── build.gradle
└── src/
    ├── main/java/example/compat/
    │   ├── CompatApplication.java
    │   ├── PricePolicy.java
    │   ├── TaxGateway.java
    │   ├── ZeroTaxGateway.java
    │   ├── InvoiceService.java
    │   ├── InvoiceController.java
    │   ├── InvoiceErrorAdvice.java
    │   └── CompatDemo.java
    └── test/java/example/compat/
        ├── PricePolicyTest.java
        ├── InvoiceServiceTest.java
        ├── InvoiceControllerTest.java
        └── PostgreSqlContainerTest.java
```

The example suite has **14 JUnit test methods**: 5 pure Java tests, 4 Mockito service tests, 3 MockMvc tests, and 2 PostgreSQL Testcontainers integration tests. The Java SE demo runs standalone; the integration suite requires a Docker-compatible runtime.

**Boundary design:** `PricePolicy` holds subtotal/validation logic and knows nothing about Spring. `InvoiceService` receives `TaxGateway` via constructor so Mockito mocks the true collaborator. The Spring MVC controller receives `InvoiceService` (mocked in the test slice). The PostgreSQL integration test does not use H2; it queries real PostgreSQL to verify JDBC + service connection.

## 8. build.gradle — Boot 3.5.x Stack via BOM

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Dependency roles:**

- `spring-boot-starter-web` provides the MVC application and testing slice ecosystem.
- `spring-boot-starter-jdbc` provides `DataSource` and `JdbcTemplate`.
- `spring-boot-starter-test` includes Boot testing infrastructure, JUnit Jupiter, Mockito/Jupiter, and AssertJ via the BOM.
- `spring-boot-testcontainers` provides Boot `@ServiceConnection` integration.
- `org.testcontainers:junit-jupiter` brings Testcontainers 1.x `@Testcontainers`/`@Container`.
- `org.testcontainers:postgresql` provides Testcontainers 1.x `PostgreSQLContainer`.
- `org.postgresql:postgresql` is the JDBC driver; it is a **different** library from the Testcontainers module.
- `junit-platform-launcher` at runtime keeps the runner/IDE aligned with the BOM's JUnit engine.

All libraries in the `dependencies` block **omit explicit versions**; the Boot BOM selects aligned versions. The build plugin version is tooling configuration, not a JUnit dependency.

**Runtime note:** Because the project includes the JDBC starter, running the full application outside tests requires configuring a real datasource. In the Testcontainers integration test, `@ServiceConnection` supplies connection details from the PostgreSQL container. Unit and MVC slice tests do **not** require Docker or a database. `build.gradle` does not generate a Gradle wrapper on its own; create a wrapper matching the Spring Boot system requirements before running `./gradlew`.

## 9. Maven: Parent or BOM Instead of Per-Dependency Versions

An **illustrative POM snippet**, not a standalone `pom.xml` file:

```xml
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>3.5.16</version>
  <relativePath/>
</parent>

<properties>
  <java.version>17</java.version>
</properties>

<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

A complete project also needs Maven coordinates, Web/JDBC dependencies, and plugin settings. If not using the Spring Boot parent, import the `spring-boot-dependencies` BOM in `dependencyManagement` and configure Maven Surefire/Failsafe to run JUnit Platform. The BOM manages libraries; **it does not automatically guarantee the Maven test plugin is new enough**.

## 10. PricePolicy.java: Pure Java Domain

Create `src/main/java/example/compat/PricePolicy.java`:

```java
package example.compat;

public final class PricePolicy {

    public int subtotalCents(
            int unitCents, int quantity) {

        if (unitCents < 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                    "unitCents must be >= 0 and quantity > 0");
        }

        return Math.multiplyExact(unitCents, quantity);
    }
}
```

Business contract: non-negative unit price, positive quantity, result equals the exact product in cents. `Math.multiplyExact` throws `ArithmeticException` on `int` overflow. Real monetary applications need currency/rounding/bounds handling; this is a testing compatibility lesson, not a production pricing engine.

Because it is a plain Java class, unit tests have no dependency on Spring context or Docker. Keeping these unit tests during a Boot upgrade helps distinguish business bugs from framework/testing infrastructure errors.

## 11. TaxGateway.java and ZeroTaxGateway.java

Create `src/main/java/example/compat/TaxGateway.java`:

```java
package example.compat;

public interface TaxGateway {
    int taxCents(int subtotalCents);
}
```

Create `src/main/java/example/compat/ZeroTaxGateway.java`:

```java
package example.compat;

import org.springframework.stereotype.Component;

@Component
public final class ZeroTaxGateway implements TaxGateway {

    @Override
    public int taxCents(int subtotalCents) {
        return 0;
    }
}
```

`ZeroTaxGateway` is only a **demo bean** so the full Spring context has a collaborator without calling an external system. It does not represent real tax policy. Mockito unit tests do not use this bean: we mock the `TaxGateway` interface to test the real service.

**Mock boundary:** replace the external port/collaborator, do not mock the service under test itself. Mocking the SUT usually only verifies that "Mockito returns what you stubbed", not business logic.

## 12. InvoiceService.java — Explicit Constructor Injection

Create `src/main/java/example/compat/InvoiceService.java`:

```java
package example.compat;

import org.springframework.stereotype.Service;

@Service
public final class InvoiceService {

    private final PricePolicy pricePolicy;
    private final TaxGateway taxGateway;

    public InvoiceService(
            PricePolicy pricePolicy, TaxGateway taxGateway) {
        this.pricePolicy = pricePolicy;
        this.taxGateway = taxGateway;
    }

    public int totalCents(int unitCents, int quantity) {
        int subtotal =
                pricePolicy.subtotalCents(unitCents, quantity);

        int tax = taxGateway.taxCents(subtotal);

        return Math.addExact(subtotal, tax);
    }
}
```

Assertions to have: the service computes the right subtotal, does not call the gateway on invalid input, does not swallow gateway failures, and does not overflow the sum. Unit tests construct the service with a real `PricePolicy` + mock `TaxGateway`. No Spring context needed.

Mockito 5 supports mocking many `final` classes via the inline mock-maker when appropriately configured. However, **prefer mocking external port interfaces** to reduce reliance on JVM instrumentation. Java agent/Byte Buddy warnings on newer JDKs must be addressed per Mockito/JDK documentation, not by disabling security flags arbitrarily.

## 13. InvoiceController.java — HTTP Boundary

Create `src/main/java/example/compat/InvoiceController.java`:

```java
package example.compat;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InvoiceController {

    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping("/invoices/total")
    public Map<String, Integer> total(
            @RequestParam int unitCents,
            @RequestParam int quantity) {

        return Map.of(
                "totalCents",
                service.totalCents(unitCents, quantity));
    }
}
```

Create `src/main/java/example/compat/InvoiceErrorAdvice.java`:

```java
package example.compat;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InvoiceErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidInvoice() {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid invoice inputs"));
    }
}
```

`GET /invoices/total?unitCents=250&quantity=2` returns JSON `{"totalCents":500}` when tax is 0. Invalid business input receives HTTP 400 with error JSON; a missing required param also receives 400 from Spring MVC binding. Service unit tests **do not prove** controller mapping; MVC slice tests cover this contract.

## 14. CompatApplication.java — A Spring Boot Main Class

Create `src/main/java/example/compat/CompatApplication.java`:

```java
package example.compat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompatApplication {

    @Bean
    PricePolicy pricePolicy() {
        return new PricePolicy();
    }

    public static void main(String[] args) {
        SpringApplication.run(
                CompatApplication.class, args);
    }
}
```

Package `example.compat` is the component scanning root. The full context finds `ZeroTaxGateway`, `InvoiceService`, `InvoiceController`, and `InvoiceErrorAdvice`. The MVC slice does not auto-scan `@Service`, so the service is mocked in that test. Do not add multiple `@SpringBootApplication` classes arbitrarily under the same test root, which leaves the framework unable to choose a single configuration.

## 15. PricePolicyTest.java: Five JUnit Jupiter Unit Tests

Create `src/test/java/example/compat/PricePolicyTest.java`:

```java
package example.compat;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PricePolicyTest {

    private final PricePolicy policy = new PricePolicy();

    @Test
    void multipliesUnitPriceAndQuantity() {
        assertEquals(750, policy.subtotalCents(250, 3));
    }

    @Test
    void zeroUnitPriceIsAllowed() {
        assertEquals(0, policy.subtotalCents(0, 1));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.subtotalCents(-1, 2));

        assertEquals(
                "unitCents must be >= 0 and quantity > 0",
                error.getMessage());
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.subtotalCents(100, 0));
    }

    @Test
    void rejectsIntegerOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> policy.subtotalCents(
                        Integer.MAX_VALUE, 2));
    }
}
```

**5 JUnit methods**, JDK/Jupiter only, no Spring/Docker. Tests expected result, zero boundary, validation, and overflow. `org.junit.jupiter.api.Test` is used in both Jupiter 5 and Jupiter 6; during migration, these assertions serve as the regression baseline.

## 16. InvoiceServiceTest.java: MockitoExtension With Four Test Methods

Create `src/test/java/example/compat/InvoiceServiceTest.java`:

```java
package example.compat;

import org.junit.jupiter.api.BeforeEach;
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
class InvoiceServiceTest {

    @Mock
    TaxGateway taxGateway;

    private InvoiceService service;

    @BeforeEach
    void setup() {
        service = new InvoiceService(
                new PricePolicy(), taxGateway);
    }

    @Test
    void calculatesTotalWithMockGateway() {
        when(taxGateway.taxCents(600)).thenReturn(60);

        assertEquals(660, service.totalCents(200, 3));
        verify(taxGateway).taxCents(600);
    }

    @Test
    void rejectsBadInputBeforeCallingGateway() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.totalCents(-1, 2));

        verifyNoInteractions(taxGateway);
    }

    @Test
    void doesNotHideGatewayFailure() {
        when(taxGateway.taxCents(500))
                .thenThrow(new IllegalStateException("offline"));

        assertThrows(
                IllegalStateException.class,
                () -> service.totalCents(250, 2));

        verify(taxGateway).taxCents(500);
    }

    @Test
    void detectsTaxAdditionOverflow() {
        when(taxGateway.taxCents(Integer.MAX_VALUE))
                .thenReturn(1);

        assertThrows(
                ArithmeticException.class,
                () -> service.totalCents(
                        Integer.MAX_VALUE, 1));

        verify(taxGateway).taxCents(Integer.MAX_VALUE);
    }
}
```

**4 JUnit methods**: real SUT, mocked external port. `@Mock` does not create a Spring bean; `MockitoExtension` initializes mocks for Jupiter tests and enforces strict stubbing. Tests include `verify`, not just stubbed return values. If `UnnecessaryStubbingException` occurs after migration, inspect unused stubs or mismatched inputs; do not disable strictness suite-wide to mask bugs.

`@InjectMocks` is a Mockito feature that attempts to inject mocks, **not Spring `@Autowired`**. Explicit constructor injection is more transparent here.

## 17. InvoiceControllerTest.java: @MockitoBean in an MVC Slice

Create `src/test/java/example/compat/InvoiceControllerTest.java` for **Boot 3.5**:

```java
package example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    InvoiceService service;

    @Test
    void producesExpectedJson() throws Exception {
        when(service.totalCents(250, 2)).thenReturn(500);

        mvc.perform(get("/invoices/total")
                        .param("unitCents", "250")
                        .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.totalCents").value(500));
    }

    @Test
    void mapsValidationFailureTo400() throws Exception {
        when(service.totalCents(-1, 2))
                .thenThrow(new IllegalArgumentException(
                        "bad invoice"));

        mvc.perform(get("/invoices/total")
                        .param("unitCents", "-1")
                        .param("quantity", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error").value(
                                "invalid invoice inputs"));
    }

    @Test
    void missingQuantityFailsBeforeService() throws Exception {
        mvc.perform(get("/invoices/total")
                        .param("unitCents", "250"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

**3 JUnit methods** verifying query binding, 200 + JSON, validation exception mapping via `InvoiceErrorAdvice`, and missing-param 400. `@WebMvcTest` is a slice and does not open external network connections or a database. `@MockitoBean` places the service mock into the Spring TestContext so the controller can autowire it.

**Do not use `@Mock` instead of `@MockitoBean` in an MVC slice**: a plain Mockito field is not a bean in the `ApplicationContext`. Conversely, pure Mockito unit tests should use `@Mock`/`MockitoExtension` rather than starting a Spring context just to mock a collaborator.

**Boot 4 migration import:** Boot 3.5 `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest` → Boot 4 `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`. `@MockitoBean` remains in `org.springframework.test.context.bean.override.mockito`. Boot 4 removes the old Spring Boot `@MockBean`.

## 18. PostgreSqlContainerTest.java: Real Testcontainers 1.x

Create `src/test/java/example/compat/PostgreSqlContainerTest.java` for **Boot 3.5 / Testcontainers 1.x**:

```java
package example.compat;

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
class PostgreSqlContainerTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("compatibility");

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void selectsRealPostgresDatabaseName() {
        String database = jdbc.queryForObject(
                "select current_database()", String.class);

        assertEquals("compatibility", database);
    }

    @Test
    void executesPostgresUuidCast() {
        String uuid = jdbc.queryForObject(
                "select '00000000-0000-0000-0000-000000000001'::uuid::text",
                String.class);

        assertEquals(
                "00000000-0000-0000-0000-000000000001",
                uuid);
    }
}
```

**2 JUnit integration methods**, **requiring a Docker-compatible runtime**:

- `@Testcontainers` is a JUnit Jupiter extension.
- `@Container` manages a static `PostgreSQLContainer`.
- `@ServiceConnection` provides Spring Boot `JdbcConnectionDetails` so the datasource automatically connects to the container without hardcoding host, port, or password.
- `JdbcTemplate` sends SQL to **real PostgreSQL**, testing `current_database()` and a PostgreSQL UUID cast.
- The `org.postgresql:postgresql` JDBC driver is still required at runtime. The Testcontainers PostgreSQL module is not a JDBC driver.

**Do not use H2 and claim PostgreSQL dialect was tested.** H2 has different SQL/types/transactions; database migrations require PostgreSQL or an equivalent test environment. When Docker is unavailable, report the test as blocked/failed or **explicitly** skipped according to policy; never treat unrun tests as PASS.

In Boot 4/Testcontainers 2, `PostgreSQLContainer` changes package and artifact; the code above targets Boot 3.5 and should **not** be mixed with TC2 imports.

## 19. Java SE Demo With javac/java and Exact Stdout

Create `src/main/java/example/compat/CompatDemo.java`:

```java
package example.compat;

public class CompatDemo {

    public static void main(String[] args) {
        PricePolicy policy = new PricePolicy();

        System.out.println(
                "subtotal=" + policy.subtotalCents(250, 3));
        System.out.println(
                "zero=" + policy.subtotalCents(0, 1));

        try {
            policy.subtotalCents(-1, 2);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid=" + error.getMessage());
        }
    }
}
```

From the project root with JDK 17+:

```bash
javac -d out src/main/java/example/compat/PricePolicy.java src/main/java/example/compat/CompatDemo.java
java -cp out example.compat.CompatDemo
```

**Exact** stdout:

```text
subtotal=750
zero=0
invalid=unitCents must be >= 0 and quantity > 0
```

This demo only runs `PricePolicy` in Java SE; it does not verify Spring Context/JUnit/Mockito/Testcontainers integration. Proving stack compatibility requires running Gradle tests and the DB container on the proper CI runner.

## 20. Test Matrix and Run Commands

| Class | Methods | Dependencies | Contract |
| --- | ---: | --- | --- |
| PricePolicyTest | 5 | Java/Jupiter | Validation, exact math, overflow |
| InvoiceServiceTest | 4 | Jupiter/Mockito | Interaction, propagating failures |
| InvoiceControllerTest | 3 | Spring Framework TestContext/Boot MVC slice | Bean override/HTTP JSON |
| PostgreSqlContainerTest | 2 | Spring full context/Testcontainers/Docker | Real PostgreSQL JDBC |
| **Total** | **14** | | |

Run unit/MVC tests without Docker:

```bash
./gradlew test --tests example.compat.PricePolicyTest
./gradlew test --tests example.compat.InvoiceServiceTest
./gradlew test --tests example.compat.InvoiceControllerTest
```

Run database integration when Docker is ready:

```bash
./gradlew test --tests example.compat.PostgreSqlContainerTest
```

Run everything:

```bash
./gradlew clean test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.compat.PricePolicyTest"
.\gradlew.bat test --tests "example.compat.InvoiceServiceTest"
.\gradlew.bat test --tests "example.compat.InvoiceControllerTest"
.\gradlew.bat test --tests "example.compat.PostgreSqlContainerTest"
```

**14 is the number of `@Test` methods in the source code, not collected execution output.** Gradle console output, test reports, and Docker startup time vary by environment. CI must check discovered/executed/skipped/failed counts separately and confirm container tests were not skipped.

## 21. Boot 4.1.x: Dependency/Test Starter Changes

Spring Boot 4 moves to per-technology starters. A **Gradle migration snippet**, not a standalone tested Boot 4 project:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers-postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Substantive changes:**

- Boot 3 `spring-boot-starter-web` → Boot 4 recommends `spring-boot-starter-webmvc`.
- Boot 4 provides `spring-boot-starter-webmvc-test`, `spring-boot-starter-jdbc-test`, and other technology test starters. `spring-boot-starter-test` still has core test support, but does not automatically replace all technology-specific support.
- Testcontainers 2 artifacts rename to `testcontainers-junit-jupiter` and `testcontainers-postgresql`.
- JUnit 6 and Spring Framework 7 are managed by the Boot 4 BOM.
- Boot 4.1 Gradle requires **8.14+ or 9.x** per system requirements; an older Boot 3.5 wrapper may no longer be valid.
- Several Spring Boot annotation packages relocated to match the new modules.

This is the delta for an MVC/JDBC project. If the app uses Spring Security, GraphQL, JPA, Kafka, or WebFlux, check the dedicated technology starter table; do not assume changing three Gradle lines suffices for production migration.

## 22. @WebMvcTest, MockMvc, and Mockito in Boot 4

Boot 3.5 import:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
```

Boot 4 import:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
```

Spring Framework 6.2+/7 mock bean import **does not change**:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Boot 4 removes the Boot `@MockBean`/`@SpyBean` annotations from package `org.springframework.boot.test.mock.mockito`. Replace them with Spring `@MockitoBean`/`@MockitoSpyBean` and check bean override behavior and qualifiers/scope.

**For full `@SpringBootTest` in Boot 4**, if you want to use `MockMvc`, add `@AutoConfigureMockMvc` and the corresponding module/test starter, because a full context test no longer provides `MockMvc` support automatically from `@SpringBootTest` alone. For `TestRestTemplate`, Boot 4 reorganizes test clients and auto-config annotations; check packages/imports/dependencies in the migration guide rather than assuming the full context supplies it like older examples.

A Boot 4 test with `@WebMvcTest` does not necessarily need `@SpringBootTest`; those are two different test styles. Do not add both mechanically when fixing imports.

## 23. Testcontainers 1.x to 2.x: Two Mandatory Pairs of Changes

| Role | Testcontainers 1.x / Boot 3.5 | Testcontainers 2.x / Boot 4 |
| --- | --- | --- |
| Postgres dependency | `org.testcontainers:postgresql` | `org.testcontainers:testcontainers-postgresql` |
| JUnit extension dependency | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| Postgres class | `org.testcontainers.containers.PostgreSQLContainer` | `org.testcontainers.postgresql.PostgreSQLContainer` |
| JUnit `@Testcontainers` | `org.testcontainers.junit.jupiter.Testcontainers` | Same package |
| JUnit `@Container` | `org.testcontainers.junit.jupiter.Container` | Same package |
| Boot `@ServiceConnection` | `org.springframework.boot.testcontainers.service.connection.ServiceConnection` | Same package |

**Do not** use `org.testcontainers:postgresql:2.0.x` expecting the same artifact ID as 1.x. **Do not** import `org.testcontainers.postgresql.PostgreSQLContainer` while the dependency is still Testcontainers 1.21.x. Ensure all core/JUnit/Postgres modules belong to one aligned line, typically managed by the Boot BOM.

Service Connection supplies the appropriate `ConnectionDetails` when Boot recognizes a container; it can take precedence over ordinary `spring.datasource.url` settings. `@ServiceConnection` does not change Docker daemon behavior or replace `@Container`/lifecycle management. If using `GenericContainer` for a specialized service, check image-name matching—you may need `@ServiceConnection(name = "...")` or `@DynamicPropertySource`.

## 24. Boot 2.7 → 3: Java 17 and javax/jakarta

Upgrading from Boot 2 to Boot 3 is not just bumping the JUnit version:

- Java baseline moves from 8+ to 17+.
- Spring Framework 5.3 → 6.x.
- Jakarta EE packages such as `javax.servlet.*`, `javax.persistence.*`, and `javax.validation.*` move to `jakarta.servlet.*`, `jakarta.persistence.*`, and `jakarta.validation.*` for their Jakarta counterparts.
- Do not change **every** `javax.*`; several Java SE APIs keep their original names.
- MVC/Servlet, Bean Validation, JPA, Security, and embedded server versions each have their own migration considerations.
- JUnit 4 `@RunWith` tests may need Jupiter `@ExtendWith` or the temporary Vintage engine.
- On Boot 3.1+, `@ServiceConnection` can replace dynamic datasource property wiring in supported Testcontainers use cases.

**Risk-reduction strategy:** upgrade JDK/tooling and clean up deprecations first, migrate javax/Jakarta/APIs, run unit tests, then run web/repository/full integration tests. Do not mix all changes at once without a baseline.

## 25. Boot 3.3 → 3.4/3.5: @MockBean Deprecated

Spring Boot 3.4 marks Boot `@MockBean`/`@SpyBean` **deprecated for removal**, moving to Spring Framework 6.2 `@MockitoBean`/`@MockitoSpyBean`.

Renaming is not enough. Check:

- Does the bean exist in the context/slice?
- Do the qualifier/field name select the right bean when multiple candidates exist?
- Is the default `REPLACE_OR_CREATE` appropriate? Is `enforceOverride` needed?
- How do mocks/spies affect AOP proxies, transactions, or cache annotations?
- Is the context cache key fragmented by differing mock configurations?
- Is mock state reset between tests according to framework/version?
- Does spy stubbing invoke the real method with side effects if using `when(spy.method())`? When needed, use `doReturn(...).when(spy)...`.

**Avoid confusion:** Mockito `@Mock` still belongs to Mockito and is not replaced by `@MockitoBean` in unit tests without Spring.

## 26. @DynamicPropertySource vs. @ServiceConnection

These two solutions serve different situations:

**@ServiceConnection**: Boot recognizes the container type/image and creates `JdbcConnectionDetails`, `RedisConnectionDetails`, or the matching type. `PostgreSQLContainer` in the demo supplies JDBC details, avoiding hardcoded mapped ports or passwords.

**@DynamicPropertySource**: for arbitrary dynamic application properties, such as a mocked service URL when no built-in `ConnectionDetails` factory exists:

```java
@DynamicPropertySource
static void addEndpoint(DynamicPropertyRegistry registry) {
    registry.add(
            "catalog.client.base-url",
            () -> "http://" + catalogContainer.getHost()
                    + ":" + catalogContainer.getMappedPort(8080));
}
```

This is a **snippet** requiring imports/Testcontainers setup and an already started static `catalogContainer`; it is not a runnable file. `@DynamicPropertySource` only injects values into the Spring `Environment`; it does not start Docker or modify global JVM system properties.

Do not declare both `@ServiceConnection` and a test `spring.datasource.url` override while assuming the datasource uses the URL you expect; check precedence order and the actual `ConnectionDetails`.

## 27. Dependency Graph and Diagnostics

**Gradle:**

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency testcontainers --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew test --tests example.compat.PricePolicyTest
```

**Windows PowerShell:**

```powershell
.\gradlew.bat dependencies --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency testcontainers --configuration testRuntimeClasspath
```

**Maven:**

```bash
./mvnw dependency:tree -Dscope=test
./mvnw test
```

**Why inspect `testRuntimeClasspath`?** Code may compile against the API while runtime loads a different version of the engine, `spring-test`, `mockito-core`, or Testcontainers. `NoSuchMethodError` often appears only when the JVM loads classes/methods. Print the selected version and what pulls each dependency into the graph rather than only reading declared versions in `build.gradle`.

Specific checks:

1. Is the Boot BOM active?
2. Is `spring-test` on the same Framework train as Spring Boot?
3. Do JUnit Jupiter API/Engine/Platform Launcher match the JUnit 5/6 line?
4. Are Mockito core, the junit-jupiter extension, and Byte Buddy compatible with the JDK?
5. Are Testcontainers module names valid for 1.x vs 2.x?
6. Is the PostgreSQL JDBC driver present when creating the `DataSource`?
7. Does the Gradle/Maven runner actually discover Jupiter tests?
8. Does CI have a Docker container runtime ready for DB tests?

## 28. CI Matrix and Scope of Proof

| Job | Needs Docker? | Proof |
| --- | --- | --- |
| Compile Java + test compile | No | Imports/APIs/classpath compile |
| PricePolicyTest | No | Java domain behavior |
| InvoiceServiceTest | No | Mockito Jupiter interaction/exception |
| InvoiceControllerTest | No | Spring MVC slice and @MockitoBean |
| PostgreSqlContainerTest | **Yes** | Spring Boot @ServiceConnection + real PostgreSQL JDBC |
| Boot4 migration branch | Depends on suite | New starters/packages, JUnit 6, Testcontainers 2 |
| Supported JDK matrix | Depends on suite | Compatibility with JDK/Byte Buddy/Gradle versions |

A CI job where Docker is unavailable **must not report PostgreSQL integration as PASS** if tests were skipped. If the DB contract is a quality gate, provision a runtime with appropriate permissions and fail the pipeline if it does not run. When intentional skipping is needed (developer laptop), display skipped tests and have a mandatory CI job that runs containers.

**CI security:** The Docker socket/daemon has high privileges on a runner. Do not mount an unisolated daemon socket for untrusted forks/PRs that have access to production secrets. Pin images by version/digest and enforce vulnerability/license policies before using in production CI.

**Speed:** Unit/MVC tests are faster than `@SpringBootTest` with a DB. Do not force every test into a full context just to be "comprehensive"; keep a test pyramid with focused failure signals.

## 29. Common Errors and Diagnostics

**1. No tests found:** missing JUnit Jupiter engine/launcher, `useJUnitPlatform()`, or wrong JUnit 4 import. Check discovery output and `testRuntimeClasspath`.

**2. NoSuchMethodError from JUnit Platform:** mixed JUnit 6/5/Platform 1 due to BOM override or transitive dependency. Print `dependencyInsight`.

**3. Cannot find MockitoBean:** code imports the Spring Framework 6.2 API while actually running Spring Framework 6.1 (Boot 3.3). Upgrade to a valid Boot line or use the matching test API.

**4. Boot 4 fails to compile @MockBean:** the old annotation was removed. Use Spring TestContext `@MockitoBean` and verify qualifier/scope.

**5. @Mock in @WebMvcTest does not create a bean:** a Mockito field is not registered in the Spring container. Use `@MockitoBean`.

**6. Mockito strict-stubbing failure:** unused stub; fix the test rather than disabling strictness globally.

**7. Mockito final/mock maker warning:** check Mockito 5/Byte Buddy/JDK Java-agent policy; mock an external interface when possible.

**8. Spring AOP behavior missing in mock test:** `@MockitoBean` replaces the real service/proxy; do not use slice mock results to prove transaction/retry behavior.

**9. Testcontainers 2 postgresql package missing:** switch to module `testcontainers-postgresql` and import `org.testcontainers.postgresql.PostgreSQLContainer`.

**10. Testcontainers 2 junit-jupiter dependency unresolved:** the artifact ID is `testcontainers-junit-jupiter`, not the 1.x ID.

**11. Docker runtime not found:** container engine/permissions environment issue, not a JUnit code bug.

**12. @ServiceConnection does not provide datasource:** missing `spring-boot-testcontainers` or factory/type matching, container not started, or competing config.

**13. Spring Boot 4 WebMvcTest import fail:** new package `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` + `webmvc-test` starter.

**14. Full Boot 4 @SpringBootTest has no MockMvc:** add `@AutoConfigureMockMvc` and the corresponding test module.

**15. javax.servlet does not exist in Boot 3:** move related APIs to Jakarta (do not change Java SE `javax.*` packages).

**16. H2 test passes but production Postgres fails:** dialect/types/constraints are not equivalent; run real Testcontainers.

**17. Individual tests pass, full suite fails:** cached Spring singletons, static state, shared DB rows, container lifecycle, parallel test ordering.

**18. Boot 4 build fails before compile:** Gradle wrapper/JDK does not meet system requirements; do not edit Java assertions to fix a toolchain error.

**19. Security tests compile but annotations are ignored:** Boot 4 modular test starters require the right technology starter; verify runtime support.

**20. Maven dependency:tree looks right but 0 tests run:** the BOM does not configure the Surefire test engine; inspect plugin/runner configuration.

## 30. Step-by-Step Upgrade Process and Rollback

**Phase A — Inventory:** lock down current Boot/JDK/Gradle/Maven versions, Spring Framework train, dependency overrides, Testcontainers/JUnit/Mockito/Byte Buddy, DB driver, and Docker runtime. Record legacy class imports to build a migration map.

**Phase B — Baseline:** run pure JUnit, Mockito, Web MVC, SQL container, and full tests separately. Record discovered/executed/skipped/failed counts and HTTP/SQL behaviors. Do not look only at a GREEN status.

**Phase C — Patch cleanup:** on the old line, upgrade to an approved security patch, address deprecations such as `@MockBean`, and remove unnecessary overrides. When coming from Boot 2, handle Java 17/Jakarta first.

**Phase D — Build tool/BOM:** upgrade the Gradle wrapper or Maven plugins before switching to Boot 4; update the Boot plugin/parent/BOM and resolve the dependency tree. Do not override five test libraries individually.

**Phase E — Imports/starter migration:** update `@WebMvcTest` package, WebMVC/JDBC test starters, `@MockitoBean`, Testcontainers 2 artifacts/`PostgreSQLContainer`, and Jakarta imports. Give each change a compile or validation test target.

**Phase F — Layered testing:** pure Java → Mockito unit → MVC slices → Spring full context → Docker/PostgreSQL integration → full CI. Diagnose failures at the first failing layer without mixing causes.

**Phase G — Observability/rollback:** verify 200/400 HTTP, SQL dialect, startup behavior, Docker image policy, and JUnit test counts before rollout. Maintain a rollback branch/tag for code, with a separate reversible/forward-compatible strategy for database migrations.

## 31. QA Checklist When Auditing the Testing Stack

**Version:**

- Has a specific Boot release/BOM been selected in line with the Java/Gradle support matrix?
- Are Framework jars on the same train as Boot, without overriding `spring-test` individually?
- Are JUnit Jupiter/Platform/TestEngine versions aligned, with Gradle `useJUnitPlatform` enabled?
- Are Mockito core/`MockitoExtension` and Byte Buddy compatible with the JDK?
- Are Testcontainers modules/Core/JUnit extension all within 1.x or all within 2.x?
- Are Testcontainers 1 module IDs/import packages absent once upgraded to 2?

**Unit and MVC:**

- Do pure Java JUnit tests assert boundaries and exceptions properly?
- Do Mockito unit tests mock external collaborators while testing the real service?
- Are `@Mock` vs `@MockitoBean` used in the right contexts?
- When upgrading to 3.4/3.5, was `@MockBean` migrated according to the new Framework semantics?
- Are Boot 4 `WebMvcTest` imports and test starter correct?
- Is `@SpringBootTest`/`MockMvc` auto-configuration explicitly declared in Boot 4 when needed?
- Are unit tests not mislabeled as Testcontainers integration tests?

**DB and CI:**

- Does `PostgreSQLContainer` use an appropriate image, with `@Container` lifecycle and `@ServiceConnection` working?
- Do DB integration tests send real queries rather than mocking `JdbcTemplate`?
- Is the JDBC driver present and not confused with the Testcontainers module?
- Is a Docker-compatible runtime available in CI and are DB tests not silently skipped?
- Do files/test logs avoid exposing credentials, and is the Docker daemon protected?
- Is there a baseline of 5+4+3+2 = 14 test methods with executed counts verified after migration?

**Migration:**

- Were `javax`/Jakarta/Servlet/Security APIs reviewed when moving to Boot 3?
- Were technology-specific test starters/module packages updated when moving to Boot 4?
- Were context cache/parallel state leaks checked?
- Is `dependencyInsight`/`dependency:tree` captured as evidence of actual resolved versions?
- Are a rollback plan and regression tests protecting HTTP/SQL behavior in place?

**Conclusion:** a sound testing stack is a compatible combination of **Spring Boot BOM + Spring Framework TestContext + JUnit engine + Mockito mocks + Testcontainers integration**. Spring Boot 3.5 and 4.1 differ across Framework, JUnit, Testcontainers artifacts, and test starters; never just bump a single version number. During migration, inspect the dependency graph and run tests layer by layer, from pure Java logic to real PostgreSQL. A successful build only shows the project can run tests; assertions and integration contracts prove the behavior that must be preserved.

## 32. Official References

- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java 17, Framework 6.2, Gradle/Maven.
- [Spring Boot 4.1 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java 17, Framework 7, Gradle 8.14+/9.
- [Boot 3.5 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): JUnit 5/Mockito 5/Testcontainers 1 managed versions.
- [Boot 4.1 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): JUnit 6/Mockito 5/Testcontainers 2.
- [Spring Boot 3.5 Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`/`ConnectionDetails`.
- [Spring Boot 4.1 Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): updated container packages/services.
- [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters, API imports, MockMvc/TestRestTemplate migration.
- [Spring Framework Version Matrix](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): Java and Jakarta support for 5.x/6.x/7.x.
- [Spring Framework @MockitoBean/@MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override semantics.
- [Boot 3.4 @MockBean Deprecation](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): migration to MockitoBean.
- [JUnit 6 Overview](https://docs.junit.org/6.0.0/overview.html): Platform/Jupiter/Vintage and Java 17.
- [Mockito Documentation](https://site.mockito.org/): `@Mock`, `MockitoExtension`, strict stubbing.
- [Testcontainers Spring Boot Quickstart](https://github.com/testcontainers/testcontainers-java-spring-boot-quickstart): container-driven integration tests.
