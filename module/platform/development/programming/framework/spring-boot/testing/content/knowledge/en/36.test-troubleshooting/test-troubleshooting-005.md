# Missing Beans in Slices, Excessive Imports, and Configuration Dependency Cycles

## 1. Lesson Objectives

One of the biggest time sinks in Spring Boot testing is having a test stop immediately with `Failed to load ApplicationContext`. Developers read the last error line, slap `@Import` onto a few classes, set `spring.main.allow-circular-references=true`, or switch everything to `@SpringBootTest`. Tests might turn green temporarily, yet the real cause goes unresolved: **test slices intentionally omit out-of-scope beans**, an overly broad import pulls in unnecessary infrastructure, or the bean graph contains a dependency cycle preventing Spring from constructing beans.

This lesson belongs to the **Test Troubleshooting** group of **Spring Boot - testing**, covering **Missing beans in slices, excessive imports, and configuration dependency cycles**.

Upon completion, you will be able to:

1. Distinguish **`NoSuchBeanDefinitionException`**, **`NoUniqueBeanDefinitionException`**, **`UnsatisfiedDependencyException`**, **`BeanCreationException`**, and **`BeanCurrentlyInCreationException`**.
2. Explain why `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`, and `@WebFluxTest` do not load all business services like `@SpringBootTest`.
3. Choose accurately among `@MockBean`, `@Import`, `@TestConfiguration`, `@EnableConfigurationProperties`, and `@SpringBootTest`.
4. Avoid importing an entire `@Configuration` holding database clients, messaging, scheduling, security, or `@ComponentScan` just to obtain one helper.
5. Identify **constructor injection cycles**, cycles across `@Bean` factory methods, cycles between test configurations, and hidden dependencies introduced by excessive imports.
6. Use `ApplicationContextRunner` to test scenarios where the context **is expected to fail at startup** without turning the JUnit suite red.
7. Build a working Java 17, Spring Boot 3.3.5, Gradle/JUnit Jupiter project with MVC, JPA, JSON slices, and full-context tests.
8. Read the **first root cause** of startup failures instead of patching only the last line of the error.
9. Diagnose traps such as explicit `@ComponentScan`, `@ContextConfiguration`, security filters, component scanning, package hierarchy, and cache failure thresholds.
10. Write regression tests verifying the fixed bean graph and separate environment faults from wiring faults.

**Principle:** Do not aim to "make every bean appear inside every slice." Aim to **provide the exact subset of beans required for the question the test is asking**. An MVC test needs only the controller, MVC infrastructure, and intentional test doubles for collaborators; a repository test needs only JPA, repositories, and entities; a full-context integration test is where end-to-end wiring belongs.

## 2. Mental Model: The Spring Context Is a Dependency Graph

Imagine an e-commerce application:

~~~text
PurchaseController
  |
  +--> PurchaseService
  |       |
  |       +--> PurchaseRepository
  |                 |
  |                 +--> DataSource / JPA EntityManager
  |
  +--> CustomerLabelFormatter

ApiExceptionHandler
~~~

In a **full application context**, Spring creates the controller, service, repository, formatter, and database infrastructure. When using `@WebMvcTest(PurchaseController.class)`, however, Spring Boot populates only the web slice; `@Service`, regular repositories, and plain `@Component` helpers are not automatically registered.

~~~text
@WebMvcTest(PurchaseController.class)
  |
  +--> PurchaseController
  +--> MVC infrastructure, Jackson, ControllerAdvice...
  +--> PurchaseService?        NOT auto-loaded
  +--> PurchaseRepository?     NOT auto-loaded
  +--> CustomerLabelFormatter? NOT auto-loaded if plain @Component
~~~

If `PurchaseController`'s constructor requires `PurchaseService` and the test supplies no collaborator, Spring cannot instantiate the controller. Here, the **missing bean is by design of the slice**, not Spring "forgetting to scan."

Choose the fix based on the goal:

- Verify controller request mapping/JSON/HTTP status: use `@MockBean PurchaseService`.
- Verify real formatter helper logic inside MVC: use `@Import(CustomerLabelFormatter.class)`.
- Verify repository/SQL queries: use `@DataJpaTest`, without importing controllers or services.
- Verify end-to-end application wiring: use `@SpringBootTest` with matching database/test dependencies.
- Verify a small bean graph expected to fail wiring: use `ApplicationContextRunner` or a standalone `AnnotationConfigApplicationContext`.

A **slice test** is not "a faster full context"; it enforces **its own bean visibility contract**.

## 3. Reading Exceptions Properly: Outer Wrappers vs Root Cause

Common error chains:

~~~text
java.lang.IllegalStateException:
  Failed to load ApplicationContext
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
  Error creating bean 'purchaseController'
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
  No qualifying bean of type 'PurchaseService' available
~~~

Looking only at `IllegalStateException` makes it look like the entire Spring context is broken. The real root cause is **no `PurchaseService` bean exists** in this test context. Under `@WebMvcTest`, that usually happens because the slice filters business services out of component scanning.

Another chain:

~~~text
BeanCreationException: Error creating bean 'alpha'
Caused by: UnsatisfiedDependencyException:
  Error creating bean 'beta'
Caused by: BeanCurrentlyInCreationException:
  Requested bean 'alpha' is currently in creation
~~~

This is a dependency cycle. The fix is not sprinkling `@MockBean`, but inspecting the `Alpha -> Beta -> Alpha` graph design.

### 3.1. Quick Classification

| Error Type | Typical Meaning | Check First |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | No bean matching type/qualifier | Slice filter, package scan, `@Import`/`@MockBean` |
| `UnsatisfiedDependencyException` | Dependency on a constructor/field/bean method unsatisfied | Read nested cause and which bean requires which dependency |
| `NoUniqueBeanDefinitionException` | Multiple candidates; Spring cannot pick one | `@Qualifier`, `@Primary`, bean names |
| `BeanCurrentlyInCreationException` | Bean requested again before creation finished; usually circular ref | Constructor/`@Bean` method graph |
| `BeanCreationException` | Bean factory/init/`@PostConstruct`/property/conversion failed | Deeper root cause |
| `BeanDefinitionOverrideException` | Two definitions share a name while overriding is disallowed | `@Import`/`@ComponentScan` bringing duplicate beans |
| `ConfigurationPropertiesBindException` | Binding property to type invalid | Prefix, keys, validation, active profile |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing or mismatched classpath/dependency version | Gradle dependencies/Boot BOM |
| `Failed to configure a DataSource` | DB auto-configuration lacks URL/driver | Test slice, embedded DB, properties |
| `ApplicationContext failure threshold exceeded` | Context key already failed earlier; Spring skipped retry | Find the **first error**, do not raise threshold first |

**Not every "No qualifying bean" is caused by a slice:** the class might be outside the scan root, excluded by `@Profile`, unmatched by `@ConditionalOnProperty`, mismatched by qualifier, defined in an unimported `@Bean` method, or missing a classpath dependency.

### 3.2. Stack Trace Traversal Steps

1. Identify the test class and the context-creating annotation.
2. Locate `Error creating bean with name ...`.
3. Follow `Caused by` down to the true root cause.
4. Decide whether that bean **belongs in this test's scope**.
5. Inspect the bean constructor and its dependency types/qualifiers.
6. Check config sources, active profiles, conditional annotations, and nested `@TestConfiguration`.
7. Pick the smallest fix: mock one collaborator, import the exact bean, supply test data, or change test scope.
8. Run the failing test alone and then the full test module; verify no new error appears.

Do not search for any class with "Config" in its name and `@Import` it unconditionally.

## 4. Test Slices and Default Beans Provided

| Boot 3.3 Annotation | Target | Typical Beans Included | Do Not Expect |
| --- | --- | --- | --- |
| `@WebMvcTest` | HTTP mapping, controllers, MVC validation, serialization | Controllers, controller advice, relevant MVC converters/filters/configurers | Business `@Service`, repositories, arbitrary `@Component` |
| `@WebFluxTest` | Reactive web controllers | Reactive controllers, WebFlux codecs, `WebTestClient` | Arbitrary business services/repositories |
| `@DataJpaTest` | JPA entities/repositories | `EntityManager`, JPA repositories, embedded DB if present | MVC controllers and regular services |
| `@JdbcTest` | JDBC queries / `JdbcTemplate` | `DataSource`, `JdbcTemplate`, transactions | Business services and MVC |
| `@DataJdbcTest` | Spring Data JDBC | Spring Data JDBC repositories and JDBC layer | The entire app |
| `@JsonTest` | JSON serialization/deserialization | `ObjectMapper`, Jackson modules, `JacksonTester` | Services/HTTP server |
| `@RestClientTest` | HTTP client adapters | `RestTemplateBuilder`/`RestClient.Builder`, `MockRestServiceServer` as supported | Real remote server, whole app |
| `@GraphQlTest` | GraphQL controller/schema tests | `GraphQlTester` and GraphQL slice components | Full business graph |
| `@SpringBootTest` | Full Spring wiring, app integration | Most beans per main config/classpath | External DB/Redis working without setup |

This list guides scope rather than enumerating every auto-configuration. Each slice applies **type exclude filters** and loads a curated subset of auto-configurations; arbitrary `@Import` or `@ComponentScan` usage breaks that isolation.

### 4.1. @WebMvcTest

In Boot 3.3, `@WebMvcTest` includes MVC components like `@Controller`, `@ControllerAdvice`, `@JsonComponent`, `Converter`, `Filter`, `HandlerInterceptor`, `WebMvcConfigurer`, and relevant infrastructure. **Regular `@Component` and `@Service` beans are not scanned as in the full application.** Controller collaborators therefore require `@MockBean` or intentional `@Import`.

### 4.2. @DataJpaTest

`@DataJpaTest` configures JPA, scans `@Entity`/repositories, and usually configures an embedded database from the test classpath. Tests are transactional by default and roll back after each method. Business `@Service` beans are not auto-scanned. If a repository test needs a custom converter, import that specific converter; if service logic is what you need to test, move to an intentional integration test.

### 4.3. @JsonTest

`@JsonTest` targets Jackson serialization contracts and `JacksonTester<T>`; never import REST controllers or databases just to serialize a DTO. If a custom Jackson module is missing, import that module/configuration rather than the full application graph.

### 4.4. Warning on Combining Multiple Slices

Spring Boot **does not support putting multiple test slice annotations like `@WebMvcTest` and `@DataJpaTest` on the same test class** to stitch two halves together. If you genuinely need MVC and repositories integrated, use `@SpringBootTest` + `@AutoConfigureMockMvc`, or a single slice paired selectively with `@AutoConfigure...` annotations. Do not try to "trick" test type filters.

## 5. Choosing `@MockBean`, `@Import`, `@TestConfiguration`, or Full Context?

### `@MockBean` — Replace a Collaborator to Test a Boundary

~~~java
@WebMvcTest(PurchaseController.class)
class PurchaseWebSliceTest {

    @MockBean
    PurchaseService service;
}
~~~

In Boot 3.3, `@MockBean` adds or replaces a bean inside the Spring test `ApplicationContext`, unlike `@Mock` which creates a Mockito object outside Spring. For controller tests focused on mapping, responses, and error handling, mocking the service is usually the right choice.

`@MockBean` does not unit-test the business service itself; test `PurchaseService` separately with a fake/mock repository or full JPA integration.

### `@Import` — Bring a Specific Real Collaborator into Scope

~~~java
@WebMvcTest(PurchaseController.class)
@Import(CustomerLabelFormatter.class)
class PurchaseWebSliceTest {
}
~~~

`CustomerLabelFormatter` is a lightweight helper with no DB or network dependencies. Importing this specific class lets the real controller run real formatting logic without pulling in the entire service and repository graph.

`@Import` can also pull in a `@Configuration` class containing many `@Bean` definitions, so always check what it drags along. An `@Import` placed on an abstract base test class inherited by dozens of tests can bloat contexts and complicate troubleshooting.

### `@TestConfiguration` — Define Test-Only Beans

~~~java
@SpringBootTest
class PaymentIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class StubConfiguration {
        @Bean
        ExternalPaymentGateway paymentGateway() {
            return new FakePaymentGateway();
        }
    }
}
~~~

This is an **illustrative snippet** (`FakePaymentGateway` is not defined). In Boot, nested `@TestConfiguration` adds test beans alongside the main application configuration. This differs from a nested plain `@Configuration`, which can act as a replacement primary test configuration and suppress discovering the main app.

Do not dump every fake service into one global `@TestConfiguration` and import it everywhere; keep each fixture's scope and ownership explicit.

### `@EnableConfigurationProperties` — Bring Config Properties into a Slice

~~~java
@WebMvcTest(PurchaseController.class)
@EnableConfigurationProperties(PurchaseViewProperties.class)
class PurchaseConfigurationTest {
}
~~~

Illustrative snippet. Regular `@ConfigurationProperties` beans are not always scanned in slices. If a controller, advice, or mapper needs a real properties class, register that specific class and supply matching test properties.

### `@SpringBootTest` — Verify Full Wiring

~~~java
@SpringBootTest(
    classes = DiagnosticApplication.class)
@AutoConfigureMockMvc
class FullHttpWiringTest {
}
~~~

When a test must verify `controller -> service -> repository -> database`, mocking the service defeats the integration goal. `@SpringBootTest` with proper test database setup is the right tool. Do not treat this as a "fix" for a `@WebMvcTest` missing a bean if all you wanted was MVC mapping.

## 6. Excessive Imports: Domino Effects and Warning Signs

A production configuration might look like:

~~~text
BillingConfiguration
  |
  +--> PaymentGatewayClient
          |
          +--> OAuthTokenProvider
                  |
                  +--> SecretStoreClient
                          |
                          +--> CloudCredentials

  +--> WebhookPublisher
          |
          +--> KafkaTemplate
                  |
                  +--> Kafka ProducerFactory
~~~

If a `@WebMvcTest` needs only a formatting converter yet you add:

~~~java
@Import(BillingConfiguration.class)
~~~

Spring is forced to build numerous unrelated beans. The original failure ("missing mapper") mutates into "missing CloudCredentials", "cannot connect to Kafka bootstrap server", or `BeanCurrentlyInCreation`. Meanwhile, the test still is not focused on MVC.

### Signs of Excessive Imports

- `@WebMvcTest` startup time rivals `@SpringBootTest`.
- Logs start initializing a DataSource or Kafka/Redis clients even though the test only calls MockMvc.
- `UnsatisfiedDependencyException` points to beans outside the layer under test.
- Tests pass on a laptop with local env vars yet fail on CI due to missing credentials.
- Context cache keys proliferate because each test imports a different bundle.
- `@MockBean` fields multiply class after class just to satisfy accidentally imported beans.
- A shared `@Import` silently makes tests depend on the network.

**Fix:** remove the broad import and import only the tiny helper, mapper, or configuration actually needed. If the graph genuinely requires every layer, intentionally write a full-context test and configure fixtures properly.

## 7. Imports and Configurations That Accidentally Break Slices

### 7.1. Re-Declaring `@ComponentScan` on the Main Application

~~~java
@SpringBootApplication
@ComponentScan("com.example")
public class DiagnosticApplication {
}
~~~

This is an **illustrative anti-pattern**, absent from the runnable project. Per Spring Boot guidance, placing an explicit `@ComponentScan` on the `@SpringBootApplication` class can disable the exclude filters Boot uses for test slices, causing `@DataJpaTest` to load regular components and configs.

**Instead:** keep `@SpringBootApplication` free of arbitrary `@ComponentScan` overrides when package layout is sound, or isolate specialized scanning in a separate configuration imported only where needed. Do not rush to add custom `excludeFilters` when clean package structure solves it.

### 7.2. Importing Auto-Configuration with the Wrong Annotation

When adding an **auto-configuration** to a slice, Spring Boot recommends `@ImportAutoConfiguration(...)`, **not** plain `@Import(...)`, because Boot processes auto-configurations through dedicated ordering and condition mechanics.

~~~java
@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class JdbcWithIntegrationTest {
}
~~~

Illustrative snippet, outside the runnable lab. `@Import` is for **regular configuration/helper classes**; `@ImportAutoConfiguration` is for additional Boot auto-configurations.

### 7.3. Test `@ContextConfiguration(classes = ...)` Accidentally Replacing Primary Config

Attaching a nested `@Configuration` as primary source or passing `classes` without the main app configuration in `@SpringBootTest` can strip expected component scanning, entities, or repositories. Do not fix that by importing classes one by one; determine which configuration source is actually active.

### 7.4. Main Application Enabling Specialized Infrastructure Too Early

Putting `@EnableMongoAuditing`, `@EnableScheduling`, or custom imports directly on the top-level `@SpringBootApplication` forces slices to pull in unwanted infrastructure. Move specialized features to scoped `@Configuration` classes imported only by relevant tests or production profiles.

## 8. Dependency Cycles: Not Simply a "Missing Bean"

A constructor injection cycle:

~~~text
AlphaService ---> BetaService
      ^               |
      |_______________|
~~~

Illustrative code:

~~~java
final class AlphaService {
    AlphaService(BetaService beta) {}
}
final class BetaService {
    BetaService(AlphaService alpha) {}
}
~~~

Spring cannot create `AlphaService` before `BetaService` completes, nor `BetaService` before `AlphaService`. Spring typically reports `BeanCurrentlyInCreationException` beneath `UnsatisfiedDependencyException`/`BeanCreationException`.

### 8.1. Do Not Enable Circular References to Dodge the Error

In modern Spring Boot, circular references are disabled by default. Setting:

~~~properties
spring.main.allow-circular-references=true
~~~

is not recommended; even when enabled, **pure constructor injection cycles cannot be resolved via early setter references**. Flipping that flag masks design smells and creates hard-to-debug startup behavior.

### 8.2. Fixing the Dependency Graph

Separate responsibilities:

~~~text
Before:
  InvoiceService --> NotificationService
        ^                  |
        |__________________|

After:
  InvoiceService ---> NotificationPort
  NotificationService ---> InvoiceEvents
  ApplicationService orchestrates both
~~~

A port, event boundary, or higher-level orchestrator breaks the cycle by establishing a clear dependency direction. Do not slap `@Lazy` onto a constructor just to turn tests green while leaving the domain cycle tangled.

### 8.3. `@Lazy` and `ObjectProvider`

`@Lazy` or `ObjectProvider<T>` defers resolution and fits valid cases such as optional dependencies, plugin registries, or lazy startup. However, it does not cure a **business logic cycle**; calling the lazy bean at runtime can still trigger infinite recursion or logic bugs. For constructor cycles, prefer **refactoring** rather than defaulting to `@Lazy`.

### 8.4. Cycles Across `@Bean` Methods

~~~java
@Configuration(proxyBeanMethods = false)
class CycleConfig {
    @Bean Alpha alpha(Beta beta) {
        return new Alpha(beta);
    }

    @Bean Beta beta(Alpha alpha) {
        return new Beta(alpha);
    }
}
~~~

This is an **illustrative failure pattern**, assuming `Alpha`/`Beta` have matching constructors. Method parameter dependencies form a cycle. Setting `proxyBeanMethods=false` does **not** eliminate cycles caused by method parameters; it only changes proxying for direct intra-class `@Bean` method calls.

### 8.5. Cycles via `@Configuration` Constructor Injection

If `WebConfig`'s constructor requires `SecurityConfig` and `SecurityConfig`'s constructor requires `WebConfig`, neither configuration bean can finish instantiating. Do not patch this by importing both into a slice; fix the dependency direction or extract shared properties/constants/interfaces.

## 9. Runnable Project: Java 17 + Spring Boot 3.3.5 + Gradle

A small project demonstrating:

- Production app with `PurchaseController`, `PurchaseService`, `PurchaseRepository`, JPA entity `Purchase`, `CustomerLabelFormatter`, and `ApiErrorHandler`.
- MVC slice **mocking the service** and **importing only the formatter**.
- JPA slice using an H2 test database and asserting the service is not scanned in the slice.
- JSON slice testing only DTO/Jackson serialization, without a DB.
- Full-context test verifying `Controller -> Service -> Repository` via MockMvc.
- `ApplicationContextRunner` demonstrating **missing dependency**, **circular constructor injection**, **unnecessary extra registration**, and **ambiguous beans** as negative demonstrations while every JUnit test still PASSES when the expected startup error is detected.

No Docker, external PostgreSQL, or real HTTP port is needed. H2 lives only on **test runtime**; running the application in production requires configuring a real DataSource instead of relying on test-scoped H2.

### 9.1. Directory Tree

~~~text
slice-diagnostics-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/slicediag/
    │   ├── DiagnosticApplication.java
    │   ├── model/Purchase.java
    │   ├── model/PurchaseRepository.java
    │   ├── model/PurchaseNotFoundException.java
    │   ├── service/PurchaseService.java
    │   ├── web/CustomerLabelFormatter.java
    │   ├── web/PurchaseDto.java
    │   ├── web/PurchaseController.java
    │   └── web/ApiErrorHandler.java
    └── test/
        ├── resources/application.properties
        └── java/com/example/slicediag/
            ├── PurchaseWebSliceTest.java
            ├── PurchaseJpaSliceTest.java
            ├── PurchaseJsonSliceTest.java
            ├── PurchaseFullContextTest.java
            └── ContextGraphDiagnosticsTest.java
~~~

Gradle Wrapper scripts/binaries must be generated via Gradle or already exist in the repository. Markdown cannot embed the binary `gradle-wrapper.jar`.

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'slice-diagnostics-lab'
~~~

### 9.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = false
    }
}
~~~

**Why include JPA and H2?** To model a multi-layered system showing `@WebMvcTest` lacks repositories/DataSource even when the project depends on JPA. `@DataJpaTest` needs an embedded test DB; `testRuntimeOnly` H2 satisfies the lab without any external network server.

**Why omit `spring-boot-starter-security`?** The security filter chain can return 401/403 before reaching the controller, distracting from bean-graph issues. Production apps with Security must test proper auth configurations rather than disabling security just to pass tests.

### 9.4. src/test/resources/application.properties

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

Test config ensures Hibernate generates the H2 schema for full-context and data slices. In production, manage schemas via migrations and dedicated DB config; never copy `create-drop` to production.

### 9.5. DiagnosticApplication.java

~~~java
package com.example.slicediag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticApplication.class, args);
    }
}
~~~

Do not add an arbitrary `@ComponentScan`, since Spring Boot automatically scans subpackages under `com.example.slicediag` while preserving slice type filters.

## 10. Data Model and Spring Data Repository

### 10.1. src/main/java/com/example/slicediag/model/Purchase.java

~~~java
package com.example.slicediag.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchases")
public class Purchase {

    @Id
    private Long id;

    @Column(nullable = false)
    private String customer;

    @Column(nullable = false)
    private long totalCents;

    protected Purchase() {
    }

    public Purchase(Long id, String customer, long totalCents) {
        this.id = id;
        this.customer = customer;
        this.totalCents = totalCents;
    }

    public Long getId() {
        return id;
    }

    public String getCustomer() {
        return customer;
    }

    public long getTotalCents() {
        return totalCents;
    }
}
~~~

A protected no-arg constructor satisfies JPA. Uses Java 17 and `jakarta.persistence` (not `javax.persistence` from Boot 2.x). IDs are assigned in fixtures, avoiding sequence generation complexity.

### 10.2. src/main/java/com/example/slicediag/model/PurchaseRepository.java

~~~java
package com.example.slicediag.model;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRepository
        extends JpaRepository<Purchase, Long> {
}
~~~

Spring Data JPA generates the implementation from this interface inside `@DataJpaTest` or the full application context with matching JPA auto-configuration. `@WebMvcTest` does not load this repository automatically.

### 10.3. src/main/java/com/example/slicediag/model/PurchaseNotFoundException.java

~~~java
package com.example.slicediag.model;

public class PurchaseNotFoundException
        extends RuntimeException {

    public PurchaseNotFoundException(long id) {
        super("Purchase not found: " + id);
    }
}
~~~

The exception is a domain signal. At the MVC boundary, `ApiErrorHandler` translates it into HTTP 404; throwing an exception at runtime does not make it a "missing bean" error.

## 11. Service, Formatter, and REST Controller

### 11.1. src/main/java/com/example/slicediag/service/PurchaseService.java

~~~java
package com.example.slicediag.service;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseNotFoundException;
import com.example.slicediag.model.PurchaseRepository;

import org.springframework.stereotype.Service;

@Service
public class PurchaseService {

    private final PurchaseRepository repository;

    public PurchaseService(PurchaseRepository repository) {
        this.repository = repository;
    }

    public Purchase find(long id) {
        return repository.findById(id)
            .orElseThrow(
                () -> new PurchaseNotFoundException(id));
    }
}
~~~

Constructor injection exposes the dependency clearly. In the full context, Spring injects the repository bean. In the MVC slice, the service is not scanned automatically, so the controller test mocks the service when verifying MVC behavior alone.

### 11.2. src/main/java/com/example/slicediag/web/CustomerLabelFormatter.java

~~~java
package com.example.slicediag.web;

import org.springframework.stereotype.Component;

@Component
public class CustomerLabelFormatter {

    public String format(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException(
                "customer must not be blank");
        }
        return "Customer: " + customer.trim();
    }
}
~~~

This helper has no database or network dependencies. `@Component` includes it in the **full context**, yet `@WebMvcTest` does not auto-scan arbitrary components. To run the real formatter inside the slice, use **`@Import(CustomerLabelFormatter.class)`**.

### 11.3. src/main/java/com/example/slicediag/web/PurchaseDto.java

~~~java
package com.example.slicediag.web;

public record PurchaseDto(
        long id,
        String customerLabel,
        long totalCents) {
}
~~~

Java 17 record DTO, serialized by Jackson into JSON fields `id`, `customerLabel`, and `totalCents`.

### 11.4. src/main/java/com/example/slicediag/web/PurchaseController.java

~~~java
package com.example.slicediag.web;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.service.PurchaseService;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/purchases")
public class PurchaseController {

    private final PurchaseService service;
    private final CustomerLabelFormatter formatter;

    public PurchaseController(
            PurchaseService service,
            CustomerLabelFormatter formatter) {

        this.service = service;
        this.formatter = formatter;
    }

    @GetMapping("/{id}")
    public PurchaseDto find(@PathVariable long id) {
        Purchase purchase = service.find(id);

        return new PurchaseDto(
            purchase.getId(),
            formatter.format(purchase.getCustomer()),
            purchase.getTotalCents());
    }
}
~~~

The controller requires **two dependencies**: business `PurchaseService` and the formatter. The slice mocks the business dependency and imports the real formatter. Full-context scanning creates both.

### 11.5. src/main/java/com/example/slicediag/web/ApiErrorHandler.java

~~~java
package com.example.slicediag.web;

import com.example.slicediag.model.PurchaseNotFoundException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(PurchaseNotFoundException.class)
    public ResponseEntity<ApiError> purchaseMissing() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("PURCHASE_NOT_FOUND"));
    }

    public record ApiError(String code) {
    }
}
~~~

`@RestControllerAdvice` is included in `@WebMvcTest` by its MVC filter; there is no need to import the entire production configuration just to get the handler. If your real advice depends on an external service, consider decoupling that logic and mocking appropriately.



## 12. Proper MVC Slice: One Mock and One Narrow Import

**src/test/java/com/example/slicediag/PurchaseWebSliceTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseNotFoundException;
import com.example.slicediag.model.PurchaseRepository;
import com.example.slicediag.service.PurchaseService;
import com.example.slicediag.web.CustomerLabelFormatter;
import com.example.slicediag.web.PurchaseController;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(PurchaseController.class)
@Import(CustomerLabelFormatter.class)
class PurchaseWebSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Autowired
    CustomerLabelFormatter formatter;

    @MockBean
    PurchaseService service;

    @Test
    void controllerUsesMockedServiceAndRealFormatter()
            throws Exception {

        when(service.find(7L))
            .thenReturn(new Purchase(7L, " An ", 1999L));

        mvc.perform(get("/api/purchases/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.customerLabel")
                .value("Customer: An"))
            .andExpect(jsonPath("$.totalCents")
                .value(1999));

        verify(service).find(7L);
    }

    @Test
    void controllerAdviceConvertsDomainErrorTo404()
            throws Exception {

        when(service.find(404L))
            .thenThrow(new PurchaseNotFoundException(404L));

        mvc.perform(get("/api/purchases/404"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("PURCHASE_NOT_FOUND"));
    }

    @Test
    void sliceContainsMockButNotRepositoryBean() {
        assertTrue(mockingDetails(service).isMock());
        assertNotNull(formatter);

        assertEquals(
            0,
            context.getBeanNamesForType(
                PurchaseRepository.class).length);
    }
}
~~~

### 12.1. Why Does This Test Compile and Start?

`@WebMvcTest(PurchaseController.class)` creates MVC infrastructure, the controller, and advice. `@MockBean PurchaseService` supplies a bean of the right type for the controller constructor. `@Import(CustomerLabelFormatter.class)` adds **one helper** to the context. Repository and DataSource are neither needed nor loaded.

**Do not replace `@MockBean` with Mockito `@Mock`** when Spring instantiates the controller: `@Mock` lives only on the JUnit test instance, so Spring will not inject it into the controller bean. If you construct the controller manually with `@InjectMocks`, that becomes a pure unit test that bypasses MVC annotations and serialization.

### 12.2. Why Not `@Import(PurchaseService.class)`?

In this example, `PurchaseService`'s constructor requires `PurchaseRepository`. Importing the real service immediately creates another missing-bean error for the repository inside the MVC slice. Importing the repository, JPA, and DataSource next would destroy MVC isolation. When you want to test the real repository, use `@SpringBootTest` with H2 or an appropriate DB.

### 12.3. Why Does `@MockBean` Work on a `@Service` Class?

In Boot 3.3, `@MockBean` **registers a new mock** when the type is absent from the slice, or replaces an existing bean when present. Thus, the service implementation does not need to enter the slice beforehand. This is the official Boot 3.3 API. In Boot 3.4+ some mock APIs were deprecated/evolved, so always match the BOM version; this lesson avoids Spring Framework 6.2's `@MockitoBean` to prevent compile errors on Boot 3.3.

### 12.4. A Green MVC Test Does Not Prove Service/Repository Wiring

Because the mocked service returns a canned `Purchase`, the controller test passes even if the production repository implementation is broken. That is why the project maintains separate JPA and full-context tests.

## 13. Proper JPA Slice: Repository Present, Service Absent

**src/test/java/com/example/slicediag/PurchaseJpaSliceTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseRepository;
import com.example.slicediag.service.PurchaseService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.ApplicationContext;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
class PurchaseJpaSliceTest {

    @Autowired
    PurchaseRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    ApplicationContext context;

    @Test
    void repositoryPersistsAndReadsEntity() {
        entityManager.persistAndFlush(
            new Purchase(7L, "An", 1999L));
        entityManager.clear();

        Purchase result = repository.findById(7L)
            .orElseThrow();

        assertEquals(7L, result.getId());
        assertEquals("An", result.getCustomer());
        assertEquals(1999L, result.getTotalCents());
    }

    @Test
    void dataJpaSliceHasRepositoryButNotService() {
        assertNotNull(repository);

        assertThrows(
            NoSuchBeanDefinitionException.class,
            () -> context.getBean(PurchaseService.class));
    }

    @Test
    void repositoryCanDeleteOwnFixture() {
        repository.save(new Purchase(
            8L, "Binh", 5000L));

        assertTrue(repository.existsById(8L));

        repository.deleteById(8L);

        assertFalse(repository.existsById(8L));
    }
}
~~~

### 13.1. Why Is `assertThrows` Here Not a Failing Test?

Inside the **JPA slice**, the absence of the business service is the **expected outcome**. The test proves the repository is present and the service was not unnecessarily imported. It does not break context startup: the test actively queries `context.getBean(PurchaseService.class)` and asserts the expected exception.

If a developer adds `@Import(PurchaseService.class)` to a base `@DataJpaTest` thinking "more beans is better," the second test fails. It serves as a clean regression guard against excessive imports.

### 13.2. Rollback and Test Data

`@DataJpaTest` runs inside a transaction by default and rolls back after each test method. `TestEntityManager.persistAndFlush` flushes writes to the DB before reading back, and `clear()` prevents assertions from reading only the first-level persistence context. H2 is merely a lab persistence store and **does not replace PostgreSQL-specific integration tests** when production uses native SQL, locks, or dialect-specific features.

### 13.3. Why Does Full-Context Differ from the JPA Slice?

A full-context test includes the controller, service, formatter, repository, and advice. The JPA slice needs only entities, repositories, and `EntityManager`. To test `PurchaseService.find` formally, write a unit test with a mock/fake repository or a full-context integration test; do not turn the JPA slice into the full app through cascading imports.

## 14. JSON Slice: Serialization Independent of Web/Database

**src/test/java/com/example/slicediag/PurchaseJsonSliceTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.web.PurchaseDto;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.junit.jupiter.api.Assertions.*;

@JsonTest
class PurchaseJsonSliceTest {

    @Autowired
    JacksonTester<PurchaseDto> json;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesContractFieldsWithoutWebContext()
            throws Exception {

        PurchaseDto dto = new PurchaseDto(
            7L, "Customer: An", 1999L);

        String serialized = json.write(dto).getJson();
        JsonNode document = objectMapper.readTree(serialized);

        assertEquals(7L, document.get("id").longValue());
        assertEquals(
            "Customer: An",
            document.get("customerLabel").asText());
        assertEquals(
            1999L,
            document.get("totalCents").longValue());
    }

    @Test
    void deserializesDtoWithJacksonTester()
            throws Exception {

        String input =
            "{\"id\":7,\"customerLabel\":\"Customer: An\","
                + "\"totalCents\":1999}";

        PurchaseDto result = json.parseObject(input);

        assertEquals(7L, result.id());
        assertEquals("Customer: An", result.customerLabel());
        assertEquals(1999L, result.totalCents());
    }
}
~~~

`@JsonTest` needs no HTTP server, service, or repository to verify the Jackson contract. If you hit `No qualifying bean of type JacksonTester<T>`, check `spring-boot-starter-test`, `@JsonTest`, the generic type parameter, and Spring Boot auto-configuration; never import MVC/controllers just to get an `ObjectMapper`.

## 15. Full-Context Integration: When Real Wiring Is Needed, Do Not Mock the Wrong Boundary

**src/test/java/com/example/slicediag/PurchaseFullContextTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.model.Purchase;
import com.example.slicediag.model.PurchaseRepository;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(classes = DiagnosticApplication.class)
@AutoConfigureMockMvc
class PurchaseFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    PurchaseRepository repository;

    @BeforeEach
    void seedFixture() {
        repository.deleteAll();
        repository.save(new Purchase(
            7L, " An ", 1999L));
    }

    @Test
    void fullBeanGraphWorksThroughController()
            throws Exception {

        mvc.perform(get("/api/purchases/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.customerLabel")
                .value("Customer: An"))
            .andExpect(jsonPath("$.totalCents")
                .value(1999));
    }

    @Test
    void missingPurchaseGoesThroughRealService()
            throws Exception {

        mvc.perform(get("/api/purchases/404"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("PURCHASE_NOT_FOUND"));
    }
}
~~~

This test brings the controller, service, formatter, repository, and H2 together in one `ApplicationContext`. Do not mock the service here because the test is verifying **real wiring**.

`@AutoConfigureMockMvc` verifies HTTP MVC dispatch and serialization **without opening a server socket**. When real TCP port behavior is required, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` with `RestClient`/`TestRestTemplate`, keeping in mind different transaction boundaries and cost.

### 15.1. Why Seed in `@BeforeEach`?

A full-context test can reuse the Spring `ApplicationContext` across methods. If H2 rows from an earlier test remain, an order-dependent test may pass or fail spuriously. `repository.deleteAll(); save(...)` establishes a deterministic fixture for both methods. Against a real shared DB, use isolated test DBs/schemas/transactions and targeted cleanup instead of wiping tables outside test ownership.

### 15.2. Distinguishing Wiring Failures from Query Failures

If the full-context test fails with `UnsatisfiedDependencyException` because the repository is absent, check JPA auto-config, `DataSource`, and entities. If the context starts yet `GET` returns 500 from SQL, inspect the repository, query, and transaction. Do not "fix" either by mocking the repository: mocking destroys integration coverage.

## 16. Safe Negative Tests Using `ApplicationContextRunner`

A test that **intentionally lacks a bean or contains a dependency cycle** should not be written as a `@SpringBootTest` failing at class initialization: that turns the entire suite red and can trigger "failure threshold exceeded" across subsequent tests.

`ApplicationContextRunner` builds a lightweight context and accepts a callback to assert that startup **failed as expected**. Because the runner's context lives independently and closes after the callback, it does not pollute the Spring TestContext cache used by `@SpringBootTest` tests.

**src/test/java/com/example/slicediag/ContextGraphDiagnosticsTest.java**

~~~java
package com.example.slicediag;

import com.example.slicediag.web.CustomerLabelFormatter;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.BeanCurrentlyInCreationException;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.*;

class ContextGraphDiagnosticsTest {

    private static boolean causeContains(
            Throwable failure,
            Class<? extends Throwable> type) {

        Throwable cursor = failure;
        while (cursor != null) {
            if (type.isInstance(cursor)) {
                return true;
            }
            cursor = cursor.getCause();
        }
        return false;
    }

    static class MissingSecrets {
    }

    static class NeedsSecrets {
        NeedsSecrets(MissingSecrets secrets) {
        }
    }

    static class Alpha {
        Alpha(Beta beta) {
        }
    }

    static class Beta {
        Beta(Alpha alpha) {
        }
    }

    static class ExtraAuditClient {
        ExtraAuditClient(MissingSecrets secrets) {
        }
    }

    interface PaymentGateway {
    }

    static class CardGateway implements PaymentGateway {
    }

    static class BankGateway implements PaymentGateway {
    }

    static class PaymentHandler {
        PaymentHandler(PaymentGateway gateway) {
        }
    }

    @Test
    void missingBeanHasNoSuchBeanDefinitionRootCause() {
        new ApplicationContextRunner()
            .withBean(NeedsSecrets.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    NoSuchBeanDefinitionException.class));
            });
    }

    @Test
    void constructorCycleIsDetectableByCauseChain() {
        new ApplicationContextRunner()
            .withBean(Alpha.class)
            .withBean(Beta.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    BeanCurrentlyInCreationException.class));
            });
    }

    @Test
    void oneUnnecessaryBeanCanBreakAHealthyContext() {
        new ApplicationContextRunner()
            .withBean(CustomerLabelFormatter.class)
            .run(context ->
                assertNull(context.getStartupFailure()));

        new ApplicationContextRunner()
            .withBean(CustomerLabelFormatter.class)
            .withBean(ExtraAuditClient.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    NoSuchBeanDefinitionException.class));
            });
    }

    @Test
    void multipleCandidatesNeedQualifierOrPrimary() {
        new ApplicationContextRunner()
            .withBean(CardGateway.class)
            .withBean(BankGateway.class)
            .withBean(PaymentHandler.class)
            .run(context -> {
                assertNotNull(context.getStartupFailure());
                assertTrue(causeContains(
                    context.getStartupFailure(),
                    NoUniqueBeanDefinitionException.class));
            });
    }
}
~~~

### 16.1. Missing Bean Test

`NeedsSecrets` has only a constructor requiring `MissingSecrets`. The runner registers only `NeedsSecrets`, so Spring cannot resolve the dependency and startup fails. The test checks the cause chain for `NoSuchBeanDefinitionException`. **This JUnit test passes because it confirms the expected startup failure**, not because the real app is broken.

### 16.2. Constructor Cycle Test

The runner registers `Alpha` and `Beta` with mutually dependent constructors. Spring traverses the dependency chain and detects a bean currently in creation. `BeanCurrentlyInCreationException` is the classic signal to look for. Do not assume it is always the top-level exception: it is typically wrapped in `BeanCreationException`/`UnsatisfiedDependencyException`.

### 16.3. "Excessive Import" Test

Runner A registers only `CustomerLabelFormatter`: the context starts cleanly. Runner B adds `ExtraAuditClient`, which demands an unregistered `MissingSecrets`: the context fails. This simulates an `@Import` or broad component scan pulling an unrelated bean into an MVC slice. The fix is not registering all secrets, but removing the **unnecessary bean** from test scope.

### 16.4. Multiple Candidates Test

The runner registers two implementations of `PaymentGateway`, while `PaymentHandler`'s constructor asks only for the interface. Spring cannot tell whether to pick Card or Bank; `NoUniqueBeanDefinitionException` is the typical root cause. In the real application:

~~~java
@Service
class PaymentHandler {
    PaymentHandler(
        @Qualifier("cardGateway") PaymentGateway gateway) {
    }
}
~~~

This snippet illustrates fixing the injection point, assuming a bean named `cardGateway` exists. `@Primary` can mark a true default implementation per design, though never slap `@Primary` on arbitrarily just to suppress an exception when two implementations serve distinct use cases.

### 16.5. Do Not Assert Full Error Messages

Spring Boot 3.3.5, Spring Framework, Mockito, and Java versions can change stack trace formatting and bean name prefixes. Tests should assert **exception classes in the cause chain** and behavior rather than hardcoding a 300-character message string. Full logs remain indispensable when diagnosing CI failures.



## 17. How Many Test Methods and Expected Results?

The complete project has **14 `@Test` methods**:

| Test Class | `@Test` Count | What Is Verified |
| --- | ---: | --- |
| `PurchaseWebSliceTest` | 3 | MVC slice, mocked service, imported formatter, controller advice |
| `PurchaseJpaSliceTest` | 3 | JPA repo/H2, service excluded from scan |
| `PurchaseJsonSliceTest` | 2 | Jackson DTO serialization/deserialization |
| `PurchaseFullContextTest` | 2 | Real Controller -> Service -> JPA repository |
| `ContextGraphDiagnosticsTest` | 4 | Missing dependency, constructor cycle, excessive import, multi-bean |
| **Total** | **14** | Positive wiring + intentional negative diagnostics |

Code is written for **Java 17, Spring Boot 3.3.5, Gradle**; this guide **does not claim Gradle/JUnit was executed** during authoring. Expected outcome is all 14 methods passing with proper dependencies, H2, and JDK. Several negative tests pass **because they verify expected failures accurately**, not because broken configs were pushed into the main Spring application.

### 17.1. Run Commands

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run individual groups:

~~~bash
./gradlew test --tests 'com.example.slicediag.PurchaseWebSliceTest'
./gradlew test --tests 'com.example.slicediag.PurchaseJpaSliceTest'
./gradlew test --tests 'com.example.slicediag.PurchaseJsonSliceTest'
./gradlew test --tests 'com.example.slicediag.PurchaseFullContextTest'
./gradlew test --tests 'com.example.slicediag.ContextGraphDiagnosticsTest'
~~~

If the project lacks a Gradle Wrapper yet you have a compatible Gradle installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Check Java and Gradle:

~~~bash
java --version
./gradlew --version
~~~

### 17.2. Inspecting Reports

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.slicediag.PurchaseWebSliceTest.xml
build/test-results/test/TEST-com.example.slicediag.PurchaseJpaSliceTest.xml
build/test-results/test/TEST-com.example.slicediag.PurchaseJsonSliceTest.xml
build/test-results/test/TEST-com.example.slicediag.PurchaseFullContextTest.xml
build/test-results/test/TEST-com.example.slicediag.ContextGraphDiagnosticsTest.xml
~~~

Do not invent fixed stdout expectations for Spring context startup or Gradle because timestamps, thread names, startup durations, and H2 details vary across machines. The JSON assertions inside tests are the concrete output contracts of the application code.

### 17.3. Notes on Caching and Test Execution

Running `./gradlew test` may report `UP-TO-DATE` when sources have not changed. When you need a fresh run for troubleshooting:

~~~bash
./gradlew test --rerun-tasks --stacktrace
~~~

Gradle's task cache **is not** the Spring TestContext cache. When a context failed earlier in the same JVM, Spring Framework 6.1 can report **failure threshold exceeded** on later attempts; the root cause usually appears in the **first failure's** log for that context cache key.

## 18. Sandbox Mutations to Observe Real Failures

Perform the mutations below only on a **sandbox copy or branch**, reverting after observation. Never leave intentionally failing configurations on main.

### 18.1. Remove `@MockBean`

In `PurchaseWebSliceTest`, remove:

~~~java
@MockBean
PurchaseService service;
~~~

Boot the MVC slice: `PurchaseController`'s constructor needs `PurchaseService`, which the slice omits. Expect root cause `NoSuchBeanDefinitionException` wrapped in `UnsatisfiedDependencyException`. **Fix:** restore the mock because this is a controller boundary test; do not import service + repository + database.

### 18.2. Remove `@Import(formatter)`

Remove:

~~~java
@Import(CustomerLabelFormatter.class)
~~~

The formatter is only a regular `@Component`, so it is excluded from the default MVC slice. The controller lacks the formatter. **Fix:** import the exact class since this test exercises the real formatter.

### 18.3. Import the Real Service into MVC

Add:

~~~java
@Import(PurchaseService.class)
~~~

while omitting the service mock. Spring now asks for `PurchaseRepository`, which is also absent from the MVC slice; the error simply **shifts from missing service to missing repository**. Do not keep piling on `@Import(PurchaseRepository.class)`, `@EnableJpaRepositories`, and DataSource config; return to mocking the service or move to `@SpringBootTest` if integration is the goal.

### 18.4. Remove the H2 Test Dependency

Remove `testRuntimeOnly 'com.h2database:h2'` and run JPA/full tests without supplying another DataSource. Expect a DataSource configuration failure—not a dependency cycle. Fix with a proper test DB or Testcontainers; never mock `DataSource` if the test targets real JPA persistence.

### 18.5. Introduce a Production Dependency Cycle

Temporarily add two scanned beans `Alpha`/`Beta` whose constructors depend on each other. `BeanCurrentlyInCreationException` should surface at context startup. Revert and refactor the graph. Never set `spring.main.allow-circular-references=true` as a default remedy.

### 18.6. Enable Explicit `@ComponentScan` on the Main Class

Try a copy of `DiagnosticApplication` with `@ComponentScan("com.example.slicediag")`. Per Boot docs, this can disable slice exclude filters, exposing unwanted beans to MVC/JPA slices. Never keep this anti-pattern in production; keep default application package scanning.

### 18.7. Import a Broad `@Configuration`

If an application has a `BillingConfiguration` creating secrets, Kafka, or HTTP clients, try importing it into an MVC test sandbox. Note the first failing bean and the pulled-in graph. Fix by importing only the needed helper or mocking a **port** at the boundary.

### 18.8. Replace `@MockBean` with `@Mock`

Mockito `@Mock` creates an object on the test instance without injecting it into the Spring context. `PurchaseController` still lacks the service. This highlights the boundary between Mockito unit tests and Spring slice integration.

## 19. Decision Table for Fixing the Right Fault

| Test Goal | Error Observed | Preferred Fix | Avoid |
| --- | --- | --- | --- |
| Controller status/JSON only | Missing `@Service` | `@MockBean` service | `@Import`ing full service/repository |
| Controller + real helper formatter | Missing formatter | `@Import` single helper | `@ComponentScan` across whole app |
| JPA repo test | Missing business service | Omit service from slice | Importing controllers/services |
| JPA repo test | Missing `DataSource` | Embedded DB or Testcontainers config | Fake DB when real SQL is required |
| JSON DTO | Missing `JacksonTester` | Proper `@JsonTest` + `starter-test` | `@SpringBootTest` without reason |
| Full integration | Missing repository | Check main scan/JPA/DB config | Mocking repo when full wiring is needed |
| Two beans of same interface | `NoUniqueBeanDefinitionException` | `@Qualifier`/`@Primary` matching semantics | Picking an implementation arbitrarily |
| Bean A -> B -> A | `BeanCurrentlyInCreationException` | Refactor dependency direction | `allow-circular-references=true` |
| Extra external client startup | Broad `@Import` | Drop extra import, split config | Supplying credentials for unused clients |
| Missing property bean | `@ConfigurationProperties` not scanned | `@EnableConfigurationProperties` for exact type | Importing whole production config tree |
| Multiple contexts fail on same key | Failure threshold exceeded | Inspect first root error | Raising threshold to mask |
| Security 401/403 before controller | Security filter chain/credentials | Mock user/auth config per contract | Unconditionally disabling all filters |

### One Error Can Have Multiple Causes

For instance, `No qualifying bean of type PurchaseService` could mean:

- The MVC slice intentionally excluded the service.
- Full context has the component scan root in the wrong package.
- `@Profile("prod")` is inactive during tests.
- `@ConditionalOnProperty` did not match.
- A `@Bean` factory method sits in an unimported config.
- The injection point uses a different qualifier than the registered bean.
- Test configuration accidentally replaced the primary configuration source.

Never pick a fix solely from the exception type. Ask **which Spring context is being built** and **why that bean was or was not registered**.

## 20. `@TestConfiguration`: Nested, Top-Level, and Scope

An important nuance in Spring Boot testing:

**Nested plain `@Configuration`:** can be treated as a replacement configuration source overriding the main application configuration for that test class. If your goal was adding one small bean alongside the main application config, accidentally using a plain nested `@Configuration` can drop all your other app beans.

**Nested `@TestConfiguration`:** designed to **supplement** test-only beans alongside the main application configuration when Spring Boot discovers it on the test class.

**Top-level `@TestConfiguration`:** excluded from ordinary component scanning like production `@Configuration`; import it explicitly when needed. This keeps test fixtures from leaking into the production app.

### Small Test-Only Config Example

~~~java
@TestConfiguration(proxyBeanMethods = false)
class StubBillingConfiguration {

    @Bean
    BillingGateway billingGateway() {
        return request -> BillingResult.approved();
    }
}
~~~

This is an illustrative snippet with hypothetical `BillingGateway`/`BillingResult`. A test wanting the fake gateway can `@Import(StubBillingConfiguration.class)` where appropriate. Do not reuse a production bean name without understanding the overriding policy.

### Duplicate Bean Definition Errors

When an imported test config defines a bean with the same name as a production bean under Boot's default **disallowed bean-definition overriding**, you can hit `BeanDefinitionOverrideException` or type ambiguity. Choose an intentional strategy:

- `@MockBean` to replace a collaborator in Boot 3.3 tests.
- `@Primary` on an alternative bean when both must exist yet one is the preferred default candidate.
- `@Qualifier` when consumers require specific named strategies.
- Exclude/split production configuration when test scope needs only a fake.
- Use explicit profiles or conditions instead of enabling global bean overriding.

**Do not enable `spring.main.allow-bean-definition-overriding=true` by default** to "fix" duplicate imports. Tests might silently exercise a different bean than production.

## 21. `@ConfigurationProperties` and Conditional Auto-Configurations

A test slice can lack a configuration properties bean because regular `@ConfigurationProperties` classes are not always scanned by default. For example, a formatter relying on `PurchaseViewProperties(prefix, locale)` might need:

~~~java
@WebMvcTest(PurchaseController.class)
@EnableConfigurationProperties(PurchaseViewProperties.class)
@TestPropertySource(
    properties = "purchase.label-prefix=Customer")
class PurchaseConfigSliceTest {
}
~~~

This is an illustrative snippet, outside the runnable project. If `PurchaseViewProperties` uses constructor binding or validation, supply valid test properties. Do not import `AllProductionPropertiesConfiguration` and pull in unrelated credentials and clients.

A bean can also be absent due to conditions:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "mail",
    name = "enabled",
    havingValue = "true")
MailSender mailSender() {
    return new RealMailSender();
}
~~~

Illustrative snippet assuming `MailSender`/`RealMailSender` exist. If the property does not match, no `BeanDefinition` is created—which may be **intended behavior**. Inspect the **Condition Evaluation Report** or enable targeted debug logging rather than throwing in arbitrary `@Import`s.

### Condition Evaluation Report

Spring Boot emits condition match/non-match details for diagnosing auto-configurations. Enable targeted test runtime logging, e.g.:

~~~properties
logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Depending on startup timing and logging initialization, `ConditionEvaluationReportLoggingListener` inside `ApplicationContextRunner` is also useful. Do not leave `org.springframework=TRACE` on CI permanently because logs get huge. If failure occurs before logging initializes, read Gradle `--stacktrace` and the exception chain.

## 22. Spring Security Errors in `@WebMvcTest`

An MVC test can return **401/403** instead of 200 because active security filters intercepted the request even when the controller/service bean graph is completely healthy. That is **not** `NoSuchBeanDefinitionException`. When production uses Spring Security, `@WebMvcTest` usually pulls in Spring Security auto-configuration from the classpath.

Proper options when security is part of the contract:

- Use `@WithMockUser` from `spring-security-test` to supply the right principal/roles.
- For CSRF-protected `POST`s, pass `with(csrf())` per security policy and request type.
- Test 401/403 explicitly on unauthenticated/unauthorized paths.
- If scope is purely serialization without security, separate it into `@JsonTest`.
- Disable filters intentionally only for an isolated MVC mapper test backed by separate security contract tests.

**Do not add `@MockBean` services or `@Import` random security configs merely because you received a 403.** Inspect the HTTP status first and separate security layer behavior from context startup.

## 23. Repository and Transaction Failures in `@DataJpaTest`

When a JPA slice fails, distinguish:

1. **Missing repository bean:** package scan, interface generics, entity discovery, or auto-configuration.
2. **Repository exists, yet query fails:** JPQL or derived query method mismatches entity properties.
3. **Missing `DataSource`:** no embedded DB on test classpath or missing connection properties.
4. **SQL migration/init failure:** broken Flyway/Liquibase/schema scripts.
5. **Persistence context masking assertions:** `EntityManager` returns cached objects instead of DB reads; flush and clear appropriately.
6. **Unexpected transaction rollback behavior:** non-transactional test, async boundary, or data seeded in a different transaction.
7. **Importing services into the slice pulls too many deps:** wrong test scope.

If production uses PostgreSQL native queries, H2 can behave differently. `@DataJpaTest` paired with a PostgreSQL Testcontainers instance and `@AutoConfigureTestDatabase(replace=NONE)` in Boot 3.3 is appropriate when real SQL dialect fidelity is required.

Never use `@ImportAutoConfiguration` to pull in the entire production app just because one converter or callback is missing; import only the narrow type/config needed.

## 24. How Does Context Caching Affect Diagnosis?

Spring TestContext's cache keys `ApplicationContext` instances by context configuration so tests can reuse them. Changing `@MockBean`, `@Import`, profiles, or properties alters the cache key and increases context reloads.

If context K fails startup, with Spring Framework 6.1+'s default failure threshold of **1**, later tests sharing that key fail fast with:

~~~text
ApplicationContext failure threshold (1) exceeded
~~~

This line appears **after the first failure**, not as a new root cause. To diagnose:

1. Locate the first test class that started context K.
2. Inspect the stack trace and `Caused by` of that first failure.
3. Compare config differences that separate context keys.
4. If Gradle forks multiple JVMs, each worker maintains its own cache and failure counters; filter logs by PID.
5. Do not set `spring.test.context.failure.threshold=1000000` to hide the real failure.

A consistent `@MockBean` service allows good cache reuse across MVC tests sharing metadata, whereas arbitrary mock variations split contexts. Still, **never force reuse by making tests share global mutable mock state**.

## 25. Step-by-Step Walkthrough of a Real Case

Suppose CI reports:

~~~text
PurchaseWebSliceTest > controllerUsesMockedServiceAndRealFormatter FAILED
IllegalStateException: Failed to load ApplicationContext
Caused by: UnsatisfiedDependencyException:
  Error creating bean 'purchaseController'
Caused by: NoSuchBeanDefinitionException:
  No qualifying bean of type 'PurchaseService'
~~~

### Step 1. Verify the Test Annotation

The test uses `@WebMvcTest(PurchaseController.class)`. This is an MVC slice, not a full context.

### Step 2. Trace the Controller's Dependency Graph

The constructor requires `PurchaseService` and `CustomerLabelFormatter`.

### Step 3. Compare Against Expected Bean Scope

`PurchaseService` is a business `@Service` -> excluded by default. `CustomerLabelFormatter` is a plain `@Component` -> also excluded. MVC/advice beans are included in the slice.

### Step 4. Pick the Fix Matching the Boundary

Mock the business service, import **only** the formatter:

~~~java
@WebMvcTest(PurchaseController.class)
@Import(CustomerLabelFormatter.class)
class PurchaseWebSliceTest {
    @MockBean PurchaseService service;
}
~~~

### Step 5. Do Not Import Repository/Database

If you find yourself importing `PurchaseRepository`, JPA, and DataSource just to get a controller test running, your scope is wrong. Write a separate full-context test when real layers are needed.

### Step 6. Add Status/Error Assertions

Once the context starts, test 200, 404, and JSON fields. A booting context **does not prove** controller mappings are correct.

### Step 7. Run Isolated and Full Suite

~~~bash
./gradlew test --tests 'com.example.slicediag.PurchaseWebSliceTest' --stacktrace
./gradlew test --rerun-tasks --stacktrace
~~~

If it passes in isolation yet fails in the full suite, check shared state, context cache variations, inherited annotations, test order/parallelism, and CI environment differences.

## 26. Failure Mode: Excessive Imports Shift the Error Type

A classic progression:

~~~text
Initially:
  @WebMvcTest
  Missing PurchaseService -> NoSuchBeanDefinitionException

Developer applies wrong fix:
  @Import(AllServiceConfiguration.class)

Next:
  Missing MessageBrokerClient -> UnsatisfiedDependencyException

Developer keeps patching:
  @MockBean MessageBrokerClient
  @Import(ExternalSecretsConfiguration.class)

Next:
  Missing cloud credentials / circular config graph
~~~

This is **symptom migration**, not incremental progress fixing dependencies. For an MVC test, return to defining the boundary: mock the service, import the narrow formatter. For full integration, provide explicit test infrastructure for brokers and secret stores rather than letting a slice bloat into an uncontrolled full context.

### Finding the Offending Import

- Check annotations on the test class and meta-annotations on abstract base classes.
- Inspect `@Import`, `@ImportAutoConfiguration`, `@ComponentScan`, `@TestConfiguration`, and `@ContextConfiguration`.
- Check imports hidden inside custom composed annotations.
- Inspect `@Bean` methods inside imported configs and the constructors they invoke.
- Remove **unnecessary imports one at a time in a test sandbox**, rather than randomly editing global production configs.
- Use the Condition Evaluation Report if the bean comes from auto-configuration.
- Record the first bean with a relevant cause chain, not just the last bean in the stack trace.

## 27. Dependency Cycles and Verifiable Refactoring

If `InvoiceService` calls `NotificationService` and `NotificationService` injects `InvoiceService`, make an architectural choice:

- Who owns the primary transaction?
- Should notification consume an immutable event/DTO rather than calling back into invoice service?
- Should an application orchestrator coordinate both?
- Can a read-only port be separated from the write service?
- Does one bean truly need the other in its **constructor**, or only an event publisher at runtime?
- Can shared logic move into an independent component?

Example refactoring direction:

~~~java
public interface PurchaseEvents {
    void published(long purchaseId);
}

@Service
public final class PurchaseService {
    private final PurchaseEvents events;
    // ...
}

@Component
public final class EmailPurchaseListener {
    // Listens to events; does not inject PurchaseService back.
}
~~~

This snippet is an **architectural sketch**, not a runnable Java file since implementations and imports are omitted. Avoid introducing an event bus merely to paper over a trivial cycle; if two services do not need separation, merging or extracting a shared utility is often cleaner.

### Testing After Refactoring

- `ApplicationContextRunner` registers both new components and asserts zero startup failures.
- Unit tests verify the orchestrator invokes the port properly.
- `@SpringBootTest` integration verifies real components wire together.
- For async events, test transaction boundaries, retries, and idempotency separately rather than assuming synchronous delivery.

## 28. Common `@MockBean` Mistakes

**Mistake A — using Mockito `@Mock` instead of `@MockBean`:** Spring does not see the bean. Fix with a Boot test mock in context, or construct the controller directly with `@InjectMocks` in a unit test.

**Mistake B — wrong `@MockBean` type:** Controller injects interface A, while the test mocks concrete class B or an unrelated type; match the exact type/qualifier.

**Mistake C — multiple beans of the same type:** Specify an explicit `name`/qualifier or `@Primary`; do not add a third mock that worsens ambiguity.

**Mistake D — mocking too deeply:** Mocking repository, DataSource, HTTP client, and service inside an MVC test hides design errors; mock right at the target boundary.

**Mistake E — stubbing in `@BeforeAll` while mocks reset per method:** Boot test mock resets clear stubs between methods. Place stubbing inside each test or `@BeforeEach` per policy.

**Mistake F — needing mock behavior during context refresh:** If a bean calls a dependency during `ApplicationContext` startup (`@PostConstruct`, `SmartInitializingSingleton`), stubbing inside the test method is **too late**. Use a `@TestConfiguration` `@Bean` returning a pre-stubbed mock or redesign startup side effects.

**Mistake G — mixing new APIs with an old BOM:** This Boot 3.3 lesson uses `org.springframework.boot.test.mock.mockito.MockBean`. When upgrading Boot/Spring Framework, verify deprecations and migrations before swapping annotations.

## 29. Common `@Import` Mistakes

**Importing a regular class:** `@Import(CustomerLabelFormatter.class)` in an MVC slice has clear, narrow scope.

**Importing a `@Configuration`:** Can register dozens of `@Bean` definitions, trigger nested `@Import`s, custom component scans, or external clients. Audit the graph before using.

**Importing an AutoConfiguration with `@Import`:** Spring Boot recommends `@ImportAutoConfiguration` for auto-configurations inside slices; plain `@Import` can bypass intended ordering and condition semantics.

**Importing `@SpringBootApplication`:** Usually defeats slice isolation, triggering full component scanning and auto-configuration. Pick the right test type instead of importing the app root indiscriminately.

**Importing configs with `@EnableScheduling`/`@EnableKafka`:** Starts background threads/listeners and external connections, making tests flaky. Enable those only in integration tests verifying such behavior.

**Importing nested plain `@Configuration`:** Can replace the primary config source or alter scanning unexpectedly. When adding test beans, prefer `@TestConfiguration` with proper semantics.

**Importing production repository config into MVC:** Pulls in JPA/DataSource with extra cost and failure modes. Unnecessary when mocking the service boundary.

## 30. Why Is `@Lazy` Not the Default Fix for Dependency Cycles?

`@Lazy` can inject a proxy or defer bean resolution in specific cases, which helps for genuinely optional or expensive dependencies (e.g., plugin registries or heavy adapters). However:

1. The logical business cycle remains intact.
2. When the proxy is invoked, failures simply surface later at runtime.
3. Startup ordering and transactional proxies become harder to reason about.
4. Mutual calls can cause runtime recursion up to a `StackOverflowError` instead of failing cleanly at startup.
5. It does not clarify unit-of-work or component responsibilities.
6. Tests can pass startup yet crash when exercising the real use case.

Whenever `@Lazy` is used, add an integration test executing **the real code path across both beans**. Refactoring the dependency direction remains far more maintainable and lower risk.

## 31. Why Not Enable Bean Definition Overriding by Default?

A distinct error from circular dependencies:

~~~text
BeanDefinitionOverrideException:
  Invalid bean definition with name 'purchaseService'
  ... cannot register ... another definition already bound
~~~

This usually means two bean definitions share the same name—commonly from `@TestConfiguration` colliding with production config, duplicate `@ComponentScan`, or broad `@Import`s.

Setting:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

lets the later bean silently replace the earlier one based on registration order, risking tests running against **a different implementation than expected**. Better fixes: use distinct names/qualifiers, scope test fixtures properly, use `@MockBean` for explicit replacement, or remove the duplicate import.

Do not confuse bean definition overriding with circular reference settings; they target completely different errors and both risk masking design flaws.

## 32. Debugging Workflow with Gradle and Logging

### 32.1. Running a Single Test

~~~bash
./gradlew test \
  --tests 'com.example.slicediag.PurchaseWebSliceTest' \
  --stacktrace --info
~~~

`--stacktrace` prints Gradle's exception chain; `--info` provides richer logs. For Spring context creation failures, always inspect the JUnit XML/HTML test reports as well.

### 32.2. Targeted Bean/Condition Logging

~~~properties
logging.level.org.springframework.beans.factory.support=DEBUG
logging.level.org.springframework.boot.autoconfigure=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Enable only during a diagnostic run; across a full suite, logs grow huge. Some startup errors occur before logging initializes, so reading the root exception chain remains essential.

### 32.3. Inspecting Bean Names in a Started Test Context

~~~java
String[] names =
    context.getBeanNamesForType(PurchaseService.class);

assertEquals(0, names.length);
~~~

This pattern is ideal for asserting a slice excludes a service. Never attempt bean inspection inside a context **that already failed startup**; use the cause chain, context runner, and condition evaluation report instead.

### 32.4. Remembering Test Slices Maintain Separate Spring Cache Keys

Two MVC test classes with different `@MockBean`/`@Import` combinations produce separate cache keys. When fixing a missing bean, watch startup overhead and cache hit rates, yet **never drop a necessary mock merely to boost cache reuse**.

### 32.5. When It Fails Only on CI

Verify JDK/Gradle/Boot versions, active profiles, secrets availability, case-sensitive package/resource names, test classpath, H2 runtime dependencies, conditional beans, and OS/clock assumptions. Never blame different behavior across machines on a "Spring cache bug" without evidence.

## 33. From Errors to a Layered Testing Strategy

A healthy codebase balances:

- **Plain Java unit tests:** service/domain logic with mocks/fakes, no Spring.
- **`@JsonTest`:** DTO mapping and serialization.
- **`@WebMvcTest`:** HTTP contracts, MVC mapping, validation, advice, mocking business collaborators.
- **`@DataJpaTest`:** JPA mappings, queries, transactions against a controlled database.
- **`@RestClientTest`:** outgoing HTTP adapters against a mock server, no live network.
- **`@SpringBootTest`:** full DI, auto-config, and integration flows.
- **`RANDOM_PORT` tests:** socket-level HTTP behavior with awareness of transaction boundaries.
- **Containerized service tests:** real database/broker wire protocols when required.

No single test must exercise every layer for every behavior. Each test should answer one clear question with a minimal bean graph, fast execution, and obvious failure signals. When a context fails to load, scope immediately reveals which collaborator is missing without guessing across the whole app.

## 34. Hands-On Exercises

**Exercise A — missing service:** Remove `@MockBean PurchaseService` from the MVC test, record the real exception chain, and restore the mock with the right type.

**Exercise B — missing helper:** Remove `@Import(CustomerLabelFormatter.class)` and observe which bean is reported missing. Restore the narrow import.

**Exercise C — excessive import:** Add `@Import(PurchaseService.class)` after removing the mock. Observe the error shifting to a missing repository and explain why that is the wrong direction.

**Exercise D — JPA slice:** Assert the repository exists while the service does not. Temporarily add `@Import` for the service and compare context bootstrap and startup time.

**Exercise E — `@JsonTest`:** Add a new field to the DTO record and add JSON contract tests without loading MVC.

**Exercise F — full context:** Run `PurchaseFullContextTest` with H2; verify 200/404 through real service and repository.

**Exercise G — constructor cycle:** Use `ApplicationContextRunner` to register `Alpha`/`Beta` and assert `BeanCurrentlyInCreationException` in the cause chain.

**Exercise H — refactor cycle:** Extract an interface/port or orchestrator, and write a positive runner test confirming the context starts cleanly.

**Exercise I — ambiguous beans:** Register `CardGateway`/`BankGateway` with `PaymentHandler`, observe `NoUniqueBeanDefinitionException`, and resolve via `@Qualifier` or `@Primary` per requirements.

**Exercise J — `@TestConfiguration`:** Add a small test-only bean via nested `@TestConfiguration`; contrast with nested plain `@Configuration`.

**Exercise K — broad component scan:** In a sandbox, add explicit `@ComponentScan` to the application and observe `@WebMvcTest`/`@DataJpaTest` behavior; revert afterward.

**Exercise L — conditions:** Add `@ConditionalOnProperty` to a bean, toggle the property on/off, and inspect negative matches in the report.

**Exercise M — `@ConfigurationProperties`:** Create a config properties record, register it with `@EnableConfigurationProperties` in an MVC slice, and assert values.

**Exercise N — external client import:** Create a config with a credential-dependent client, mistakenly import it into an MVC test, and trace the failure origin.

**Exercise O — mock reset:** Stub inside `@BeforeEach`, verify mocks reset between methods, and avoid assuming `@BeforeAll` stubs persist.

**Exercise P — security:** Add `starter-security` in a sandbox, test 401/403 and `@WithMockUser` properly rather than blindly disabling filters.

**Exercise Q — cache failure threshold:** Create a failing context in a sandbox class and observe the first attempt vs subsequent skips under Spring Framework 6.1.

**Exercise R — DB Testcontainers:** Switch `@DataJpaTest` from H2 to a PostgreSQL container to test dialect-specific queries instead of relying permanently on H2.

**Exercise S — Gradle diagnostics:** Run a single test with `--stacktrace --info` and inspect JUnit XML to trace the root cause.

**Exercise T — context performance:** Count unique context configurations across `@MockBean`/`@Import` combinations; optimize only while preserving correctness.

**Exercise U — singleton state:** Write a test that overuses `@DirtiesContext`, then replace it with targeted data/mock cleanup and compare startup times.

**Exercise V — review:** Pick a failing slice in a real codebase, sketch its 2–3 level dependency graph, and propose the minimal justified fix.

## 35. Pre-Conclusion Checklist

- [ ] Read the `Caused by` root cause of the first failure?
- [ ] Identified the exact test annotation and intended bean graph scope?
- [ ] Know whether the missing bean belongs to controller, service, repository, configuration, or condition?
- [ ] Avoided turning `@WebMvcTest` into the full app via excessive `@Import`s?
- [ ] Mocked business collaborators intentionally in MVC slices?
- [ ] Imported real helpers via narrow class/config `@Import`s?
- [ ] Distinguished Mockito `@Mock` from Spring `@MockBean`?
- [ ] Used annotations matching the current Spring Boot version?
- [ ] Verified `@DataJpaTest` loads only entities/repositories and the right test database?
- [ ] Verified `@JsonTest` avoids pulling in web/database layers needlessly?
- [ ] Reserved `@SpringBootTest` for cases needing full wiring?
- [ ] Avoided combining multiple `@...Test` slices on the same class?
- [ ] Checked for explicit `@ComponentScan` or accidental primary test configurations?
- [ ] Used `@TestConfiguration` properly to supplement rather than replace config?
- [ ] Used `@ImportAutoConfiguration` for supplemental Boot auto-configurations?
- [ ] Registered `@ConfigurationProperties` test beans intentionally?
- [ ] Distinguished `NoSuchBeanDefinition` from `NoUniqueBeanDefinition`?
- [ ] Used `@Qualifier`/`@Primary` reflecting business intent when multiple implementations exist?
- [ ] Refactored constructor cycles instead of setting `allow-circular-references`?
- [ ] Avoided `@Lazy` as a default workaround to hide graph cycles?
- [ ] Refused to enable `bean-definition-overriding` merely for duplicate imports?
- [ ] Restricted `@DirtiesContext` to genuinely dirtied contexts?
- [ ] Traced earlier root failures whenever `failure threshold exceeded` appeared?
- [ ] Separated Security 401/403 responses from context startup failures?
- [ ] Isolated JUnit negative tests in `ApplicationContextRunner` so they PASS on expected failures?
- [ ] Prevented Mockito stubbing/resets from introducing test order dependencies?
- [ ] Cleaned up test data and transactions within the proper scope?
- [ ] Re-run both the individual test class and full module after fixing?
- [ ] Confirmed test reports show actual executions rather than only Gradle `UP-TO-DATE`?
- [ ] Kept business assertions intact instead of stripping them just to load the context?
- [ ] Kept external secrets/network calls out of slices that do not need them?

## 36. Official References

Helpful references for **Spring Boot 3.3.5, Spring Framework 6.1, JUnit Jupiter, and Java 17**:

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, mock beans, `@TestConfiguration`, and component scan filters.
- [Spring Boot 3.3 — Test Slices Appendix](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html): auto-configurations active in each slice.
- [Spring Boot 3.3 — @MockBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): registering/replacing mocks in the test context.
- [Spring Boot — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): testing context success, failures, and conditional bean graphs.
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): constructor injection and circular dependencies.
- [Spring Framework — TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys and configuration differences.
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html): default 1 since Framework 6.1.
- [Spring Framework — @Import](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html): importing configuration classes.
- [Spring Data JPA — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): repository infrastructure.
- [JUnit Jupiter — Assertions](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests-assertions): `assertThrows` and test failure semantics.
- [Gradle — Testing in Java](https://docs.gradle.org/current/userguide/java_testing.html): test filtering, reports, and JUnit Platform.

**Key takeaway:** A missing bean inside a slice usually signals a **misunderstood test scope**, not a reason to import the entire production config. Use `@MockBean` for business collaborators at MVC boundaries, `@Import` for narrow real helpers, `@DataJpaTest` for repositories, and `@SpringBootTest` for the full graph. When adding an import shifts the failure toward external services or dependency cycles, **shrink the graph** instead of piling on more imports. Use `ApplicationContextRunner` for intentionally failing configurations, read the root cause, and refactor cycles along a clean dependency direction.
