# General Test Starters and Technology-Specific Test Modules Across Spring Boot Lines

## 1. Scope and core idea

When setting up testing for Spring Boot, you must first identify the **project's release line** (for example, 2.7.x, 3.5.x, or 4.x), and then identify the **technologies being tested** (MVC, WebFlux, JPA, Security, Kafka, GraphQL...). Dependency names and where test annotations live change significantly when moving from Spring Boot 3 to Spring Boot 4.

Three concepts to distinguish:

- **General test starter** (`org.springframework.boot:spring-boot-starter-test`): a convenience dependency that pulls in common testing tools and Spring Boot's core testing support modules. Declared in **test scope**, not packaged into the production application.
- **Test modules** (such as `spring-boot-test`, `spring-boot-test-autoconfigure`, or `spring-boot-webmvc-test`): JARs containing testing APIs/annotations/auto-configuration support. Direct modules are usually narrower than starters and do not necessarily pull in all external tools on their own.
- **Technology-specific test starters** (such as `spring-boot-starter-webmvc-test`, `spring-boot-starter-data-jpa-test`): dependency bundles packaged by Spring Boot 4 for a technology area, including the needed test modules/infrastructure. Boot 4's technology starters pull in `spring-boot-starter-test` transitively.

For example: `@WebMvcTest` requires Spring MVC test infrastructure, while `@DataJpaTest` requires JPA test infrastructure. Having JUnit Jupiter on the classpath **does not automatically** mean every test slice is ready. Conversely, having a Spring MVC production starter cannot replace dependencies for specialized test tooling.

### Overview by release line

| Spring Boot line | General starter | Organization of test features | How to add specialized testing |
| --- | --- | --- | --- |
| **2.7.x (legacy)** | `spring-boot-starter-test` | `spring-boot-test` + `spring-boot-test-autoconfigure` provide utilities and many common test slices | Add technology libraries as needed, e.g. `spring-security-test`, `spring-kafka-test`; stay on the same version line |
| **3.x (e.g., 3.5.x)** | `spring-boot-starter-test` | The two shared modules above still provide most Spring Boot test annotations; uses JUnit Jupiter and Spring Framework 6 | Many test slices are included in the general starter; add test libraries for Security, GraphQL, Kafka, Testcontainers... as needed |
| **4.x (e.g., 4.0/4.1)** | `spring-boot-starter-test` still exists | The two shared test modules **plus technology-specific modules** `spring-boot-<technology>-test`; uses Spring Framework 7 | Prefer `spring-boot-starter-<technology>-test` for each technology actually tested, e.g. MVC, Data JPA, Security; technology starters pull in the general starter |

**You cannot take a Boot 3 configuration example and merely bump the version number to Boot 4.** Version 4 introduces a new module layout, renames some artifacts, and moves many annotations to different packages. Do not assume every Boot 4 `-test` dependency exists in Boot 2 or 3.

Spring Boot 2.x projects have a different Java baseline than Spring Boot 3/4: Boot 3 and 4 require Java **17 or higher**; the Java 17 source in the examples below therefore targets Boot 3/4. For Boot 2.7 projects running an older Java version, adjust language features and libraries accordingly.

## 2. What does the general test starter contain, and what does it NOT do?

`spring-boot-starter-test` manages a familiar toolset:

| Component | Responsibility | Common usage |
| --- | --- | --- |
| JUnit Jupiter | Writing and running tests, assertions, lifecycle, parameterized tests | `@Test`, `@BeforeEach`, `@ParameterizedTest` |
| Spring Test | Testing `ApplicationContext`, TestContext Framework integration, Spring Framework-level MockMvc when suitably configured | `@SpringBootTest`, `MockMvc` |
| Mockito | Mocking dependencies and verifying interactions | `mock`, `when`, `verify`, `@MockitoBean` when supported by Spring Framework |
| AssertJ | Readable assertions for objects, collections, exceptions | `assertThat(actual).isEqualTo(expected)` |
| Hamcrest | Matchers supporting assertions | `assertThat(value, is(...))` |
| `spring-boot-test` | Core Spring Boot testing utilities and support | `@SpringBootTest` |
| `spring-boot-test-autoconfigure` | Common test auto-configuration support; Boot 4 splits much of this by technology | Supports automatic test configuration depending on starter set |

This is a high-level picture; **exact dependency sets must be verified against the version**. For instance, Spring Boot 3.5 uses the JUnit 5 line, while Spring Boot 4 documentation describes the JUnit 6 line; tests written with the Jupiter API usually keep `import org.junit.jupiter.api.Test`, though plugins and Java versions must remain compatible. Do not manually add `junit-jupiter`/`mockito-core` with standalone version numbers when the BOM/parent already manages them.

The general test starter **does not** automatically spin up a database or Docker container, **does not** provide default credentials for external systems, **does not** replace business contract tests, and in Boot 4 **does not** carry every technology's test slice. Adding the right dependencies is the first step; next you still must choose the right test type and configuration.

### Dependencies and classpath behavior

- Maven: `<scope>test</scope>` limits the dependency to test compilation/execution.
- Gradle: `testImplementation(...)` for test compile/runtime; `testRuntimeOnly(...)` for libraries needed only when running tests.
- Production dependencies (e.g., `spring-boot-starter-webmvc`, `spring-boot-starter-data-jpa`) belong in application compile/runtime scope; **do not use them as substitutes** for test starters.
- The Spring Boot Maven parent/BOM or Gradle dependency management ensures versions work together. Do not pin custom versions on Boot-managed starters without a verified technical reason.
- The 2.x/3.x/4.x line should stay consistent across BOM, starters, Spring Framework, and extra dependencies. Mixing a Boot 4 `spring-boot-starter-test` into a Boot 3 application can cause `NoClassDefFoundError` or Spring Framework conflicts.

## 3. Choosing modules by technology: comparing Boot 3.x with Boot 4.x

The table below uses **Spring Boot 3.5.x** as a model of pre-v4 packaging and **Spring Boot 4.x** as a model of the new modular packaging. For 2.7.x, most setups start from the general starter and specialized test libraries, while verifying version compatibility.

| Technology under test | Boot 3.5: commonly used test dependencies | Boot 4.x: suitable test starter | APIs/test slices to look for |
| --- | --- | --- | --- |
| Plain Java logic or general Spring Boot context | `spring-boot-starter-test` | `spring-boot-starter-test` | JUnit, Mockito, `@SpringBootTest` |
| Servlet Spring MVC | `spring-boot-starter-test`; app has MVC dependency | `spring-boot-starter-webmvc-test` | `@WebMvcTest`, `MockMvc`, `@AutoConfigureMockMvc` |
| WebFlux/reactive controllers | `spring-boot-starter-test` + needed Reactor test libraries | `spring-boot-starter-webflux-test`; add Reactor test as needed | `@WebFluxTest`, `WebTestClient`, `StepVerifier` |
| Spring Data JPA | `spring-boot-starter-test` + JPA production starter + test DB | `spring-boot-starter-data-jpa-test` + test DB if needed | `@DataJpaTest`, repositories and entities |
| Spring Data JDBC | `spring-boot-starter-test` + Data JDBC dependency | `spring-boot-starter-data-jdbc-test` | `@DataJdbcTest` |
| Plain JDBC | `spring-boot-starter-test` + JDBC dependency | `spring-boot-starter-jdbc-test` | `@JdbcTest` |
| MongoDB | `spring-boot-starter-test` + MongoDB dependency | `spring-boot-starter-data-mongodb-test`; reactive variant available | `@DataMongoTest` |
| Synchronous REST client (`RestClient`/`RestTemplate`) | `spring-boot-starter-test` + production HTTP client | `spring-boot-starter-restclient-test` | `@RestClientTest`, mock server |
| Spring Security | `spring-boot-starter-test` + `org.springframework.security:spring-security-test` | `spring-boot-starter-security-test` | `@WithMockUser`, security assertions |
| Spring GraphQL | `spring-boot-starter-test` + `org.springframework.graphql:spring-graphql-test` | `spring-boot-starter-graphql-test` | `@GraphQlTest`, `GraphQlTester` |
| Spring Kafka | `spring-boot-starter-test` + `org.springframework.kafka:spring-kafka-test` | `spring-boot-starter-kafka-test` | Embedded Kafka/test support per version |
| Spring AMQP / RabbitMQ | `spring-boot-starter-test` + suitable test library | `spring-boot-starter-amqp-test` | Testing message listeners, broker integration |
| Validation | `spring-boot-starter-test` + Bean Validation when used by app | `spring-boot-starter-validation-test` | `jakarta.validation.Validator` in Boot 3/4 |

**Note on imports:** identical annotation names do not guarantee identical packages. For example, in Boot 3.5, `@WebMvcTest` lives at `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest`; in Boot 4, it lives at `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`. `@DataJpaTest` moved from `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` to `org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest`. After switching starters, the IDE may still report missing annotations if old imports remain.

**Note on artifact names:** do not derive a name by a generic formula without checking the official catalog. For example, Boot 4 actually uses `spring-boot-starter-data-jpa-test`, while the module containing the annotation is `spring-boot-data-jpa-test`; starter and module are two different artifacts. Use the **starter** in most applications to get complete dependencies; only use the module directly when intentionally controlling the classpath and you already know what else must be added.

### Why does Boot 4 prefer technology-specific starters?

In Boot 3, having only the general starter already brought in annotations for many test slices, enlarging the classpath and making it easy to accidentally rely on unrelated test configuration. In Boot 4, modularization moves infrastructure into per-technology modules so each feature participates only when its corresponding dependency is present.

Example of an application testing only MVC in Boot 4:

- Needs `spring-boot-starter-webmvc` to run the application's web MVC layer.
- Needs `spring-boot-starter-webmvc-test` in test scope to receive MVC test support. This starter pulls in the general test starter transitively, so declaring `spring-boot-starter-test` separately is **not mandatory**.
- If JPA tests are later added to the same module, you must add `spring-boot-starter-data-jpa-test` rather than expecting the MVC test starter to bring in JPA testing.
- If there are only pure Java unit tests that do not open a Spring context, `spring-boot-starter-test` can be used without technology-specific test starters.

Which technologies an application **uses** and which technologies a module **tests** are related but distinct facts: you do not necessarily need to add a test starter for every production starter if no tests exercise that infrastructure.

## 4. Maven configuration for common release lines

The XML snippets below are **declarations inside `<dependencies>` of a project that already has a valid Spring Boot parent/BOM**, not a complete `pom.xml`.

### 4.1. Spring Boot 3.5.x: general starter as the foundation

```xml
<dependencies>
    <!-- JUnit Jupiter, Mockito, AssertJ, Spring Boot test utilities -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Add only when actually testing Spring Security -->
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Add only when testing Spring GraphQL -->
    <dependency>
        <groupId>org.springframework.graphql</groupId>
        <artifactId>spring-graphql-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The snippet above does not create MVC/JPA in the application on its own. To run `@DataJpaTest`, the application also needs JPA dependencies and a datasource, such as `com.h2database:h2` in test scope or another test database configuration. For `@WebMvcTest`, the application needs Spring MVC. For `spring-graphql-test`, the application needs the appropriate GraphQL components.

In Boot 2.7, the general starter declaration looks similar, but it must follow the version's BOM and `javax`/`jakarta` imports; do not introduce Boot 3.4+ annotation APIs into a Boot 2.x project.

### 4.2. Spring Boot 4.x: compose by technologies actually tested

Example of a module **with MVC, JPA, and Security tests**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Each technology-specific `-test` starter in Boot 4 already pulls in the general starter transitively; also declaring the general starter is valid if you want to make intent explicit, though usually redundant. `h2` here is an example test database, **not mandatory** if testing against another database. The application still needs the appropriate production starters and real entities/repositories/controllers. If you only want MVC, drop JPA, Security, and H2 from the example.

### 4.3. Spring Boot 4: classic starter for temporary migration

Spring Boot 4 provides `spring-boot-starter-test-classic` as a stepping stone when upgrading from Boot 3 to retain a classpath layout similar to before. This is an option for **migration**, not a permanent replacement for choosing technology-specific test starters. Even when using it, you must still review third-party libraries, classpaths, and changed imports; never assume every old dependency stays identical.

## 5. Equivalent Gradle Kotlin DSL configuration

The snippets below belong inside `build.gradle.kts` of a project using the Spring Boot Gradle plugin with appropriate dependency management.

### Boot 3.5.x, application needs only the general starter

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

If using `@WithMockUser`, add:

```kotlin
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
```

### Boot 4.x, application has MVC and Data JPA tests

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("org.springframework.boot:spring-boot-starter-data-jpa-test")
    testRuntimeOnly("com.h2database:h2")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

`useJUnitPlatform()` tells Gradle to run via JUnit Platform; `testImplementation` does not automatically enable it on the test task. If the build already has this configuration from a template, do not duplicate it. Maven uses Surefire/JUnit Platform per build configuration; do not pin a custom Surefire version conflicting with the project's management unless specifically required.

### Java version

- Boot 3.x and 4.x: Java 17+.
- Boot 2.7.x: may run on older Java; do not copy Java 17 syntax (such as `record`) into projects using an older compiler.
- Use `java -version`, `mvn -v`, or `./gradlew -version` to confirm the build uses a matching JDK. Source/target/toolchain versions must also match.

## 6. A runnable unit test example with the general starter

This example does not depend on a Spring context; the goal is to demonstrate that adding the general starter makes JUnit Jupiter ready to run plain Java tests. It uses **Java 17**, compatible with Boot 3.x and 4.x after configuring the build in Section 4 or 5.

File `src/main/java/example/GreetingService.java`:

```java
package example;

public final class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

File `src/test/java/example/GreetingServiceTest.java`:

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void greetsUsingTrimmedName() {
        assertEquals("Hello, Lan!", service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet("  "));
    }
}
```

Command to run from the directory containing the build file:

```bash
mvn test -Dtest=GreetingServiceTest
```

Or Gradle on Linux/macOS:

```bash
./gradlew test --tests 'example.GreetingServiceTest'
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.GreetingServiceTest"
```

**Expected:** both tests PASS; the code itself prints no `System.out.println` lines, so there is no fixed program stdout to compare against. Maven/Gradle prints test execution logs depending on configuration. Neither `@SpringBootTest` nor `@ExtendWith(SpringExtension.class)` is needed for this example. Running it verifies JUnit on the test classpath; it does not verify that MVC/JPA/Security test slices are configured.

## 7. Examples of annotations and imports that change when upgrading to Boot 4

### @WebMvcTest

Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
```

Boot 4.x:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
```

Boot 3.5 uses the test infrastructure inside the general starter; Boot 4 adds `spring-boot-starter-webmvc-test` in test scope. Both use `@WebMvcTest(MyController.class)` to load a limited web slice and normally auto-configure `MockMvc`. Dependencies required by the controller, such as services, must be supplied via test mocks or `@Import` of appropriate configuration.

### @DataJpaTest

Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
```

Boot 4.x:

```java
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
```

Boot 4 adds `spring-boot-starter-data-jpa-test`. JPA tests require a suitable database driver or test datasource; adding the annotation alone does not supply an actual database. When an embedded database is on the classpath, `@DataJpaTest` normally auto-configures it and test transactions typically roll back after each test; verify the actual datasource/transaction policy before writing assertions.

### Mocking beans in the Spring context

- Boot 2.7 / Boot 3.3 and earlier: typically used `org.springframework.boot.test.mock.mockito.MockBean`.
- Boot 3.4/3.5: Boot's `@MockBean` is deprecated; prefer `org.springframework.test.context.bean.override.mockito.MockitoBean` (Spring Framework 6.2+).
- Boot 4.x: use `@MockitoBean`; do not keep removed Boot `@MockBean` imports.

`@MockitoBean` is used when mocking **a Spring bean in the ApplicationContext**, whereas Mockito's `@Mock` creates only a regular mock, which can be paired with `@InjectMocks` for non-Spring unit tests. Do not treat them as interchangeable: `@Mock` does not register a mock into the Spring context.

### @SpringBootTest, MockMvc, and HTTP test clients

`@SpringBootTest` focuses on creating the Spring application context; it does not mean every MVC client bean is automatically ready. For full-context tests needing `MockMvc`, combine `@SpringBootTest` with `@AutoConfigureMockMvc` and the MVC test dependency for that version. In Boot 4, import `@AutoConfigureMockMvc` from the new MVC module package:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiIntegrationTest {
    // Inject MockMvc and write tests in a real project.
}
```

The snippet above **illustrates annotations** and is not a standalone test class with test methods. Boot 3.5 imports `AutoConfigureMockMvc` from `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`. When using `@SpringBootTest(webEnvironment = RANDOM_PORT)` and a real HTTP client, choose and configure the corresponding client; Boot 4 does not create `TestRestTemplate` or `WebClient` by default in the way older examples might expect. Per the migration guide, `@AutoConfigureTestRestTemplate` or `@AutoConfigureRestTestClient` exist with their required modules; verify exact dependencies and imports for your version.

## 8. Choosing dependencies from the test type, not mechanically from class names

| Testing question | First choice | Things to keep in mind |
| --- | --- | --- |
| "Does the billing function return the right number?" | Plain JUnit/Mockito unit test with general starter | Does not open a Spring context |
| "Does the controller return HTTP 400/201 properly?" | `@WebMvcTest` + MockMvc, MVC test starter for Boot 4 | Mock services; verify serialization and validation |
| "Does the repository save and query entities properly?" | `@DataJpaTest` + test DB | Verify transactions, schema, and datasource |
| "Does the WebFlux endpoint emit the right signals?" | `@WebFluxTest` + WebTestClient; Reactor test if using StepVerifier | Distinguish reactive from servlet web stack |
| "Is the ADMIN role enforced properly?" | Security test support with `@WithMockUser` | Test filter chain, URL permissions, and CSRF if applicable |
| "Does the GraphQL resolver/error mapping work?" | GraphQL test support | Real schema/resolver, mock collaborators |
| "Does the Kafka consumer process messages properly?" | Kafka test support or Testcontainers broker | Do not rely solely on mocks to assert broker integration |
| "Does the app boot against a real database?" | `@SpringBootTest` + driver + Testcontainers | Needs Docker or a runnable test backend |

**Test slices differ from full integration tests.** Slices such as `@WebMvcTest` and `@DataJpaTest` load only a narrow subset of components for that layer. If a test requires multiple layers together, consider `@SpringBootTest` with client/DB test tools; trying to combine multiple slice annotations on one class is generally unsupported. Pick the test level based on the claim you need to prove, not by "which annotation is easiest to run."

## 9. Technologies with additional test dependencies

### Security

In Boot 3.5, `@WithMockUser` comes from `org.springframework.security:spring-security-test`; the general starter does not replace it by default. In Boot 4, use `spring-boot-starter-security-test` for integrated infrastructure; keep the old direct dependency only if you fully understand transitive/configuration compatibility.

Illustrative example:

```java
import org.springframework.security.test.context.support.WithMockUser;

@WithMockUser(roles = "ADMIN")
```

This is an annotation placed on a class/test method, not a standalone test. It sets up a simulated security context for the scenario needed, and **does not** replace real OAuth2/JWT authentication tests when the goal is to verify the entire security chain.

### GraphQL, Kafka, and messaging

- Spring Boot 3.x: add `spring-graphql-test` when using `GraphQlTester`, or `spring-kafka-test` when needing an embedded broker/Kafka test utilities, alongside the general starter.
- Spring Boot 4.x: use `spring-boot-starter-graphql-test` and `spring-boot-starter-kafka-test`; choose `spring-boot-starter-amqp-test` or other specialized messaging starters as needed.
- Testing messages on a real broker, consumer rebalancing, offsets, retries, and dead-letter queues cannot be fully verified with service mocks alone; proper integration tests need a broker or equivalent environment.

### Testcontainers and real databases

Testcontainers is a separate choice for integration tests and **is not automatically started** just by adding the general starter. Spring Boot 3.1+ provides `spring-boot-testcontainers` to integrate `@ServiceConnection`; at the same time you still need the corresponding `org.testcontainers` libraries and an available Docker/container runtime. Boot 2.7 projects can use Testcontainers with `@DynamicPropertySource` or manual configuration, but `@ServiceConnection` is not a built-in feature of Boot 2.7.

For Boot 4, check the Testcontainers documentation and the dependency providing `@ServiceConnection` for the 4.x line; do not assume a technology test starter brings in all drivers or container modules. For example, real PostgreSQL testing needs the PostgreSQL driver and Testcontainers PostgreSQL module; it cannot be completely replaced by H2 if you want to test PostgreSQL-specific SQL behavior.

### JUnit Vintage

JUnit Jupiter is the primary platform. If a project still has `org.junit.Test` from JUnit 4, configure the **Vintage Engine** matching the JUnit version managed by Spring Boot; do not mix an arbitrary `junit-vintage-engine` with a JUnit Jupiter of a different major version. Gradually migrating to `org.junit.jupiter.api.Test` reduces compatibility overhead. Check the engine version via the BOM before enabling it.

## 10. How to verify actual dependencies after configuration

Correct dependency names on paper are not enough: inspect the dependency tree and run a minimal test.

Maven:

```bash
mvn dependency:tree -Dscope=test
mvn test -Dtest=GreetingServiceTest
```

Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --tests 'example.GreetingServiceTest'
```

Verify:

1. Test starters/modules match the parent/BOM Boot line. Do not pull Spring Framework 6 into Boot 4 (Framework 7) or vice versa.
2. Test dependencies appear on the **test classpath**. If the IDE reports a missing annotation, compare imports and artifacts; in Boot 4, a missing focused starter is a common culprit.
3. JUnit Platform is executed by the test task; Jupiter tests appear in the report, not "BUILD SUCCESS" with **0 tests**.
4. Test slices load only the beans under test; avoid accidentally booting the full context for unit/slice tests.
5. For JPA, database/driver and schema are correct, and tests do not accidentally touch a production database.
6. For Security/GraphQL/Kafka, specialized test libraries are present and configured properly.
7. For Testcontainers integration tests, the container runtime is available locally/in CI and lifecycle management does not cause flaky tests.

When fixing dependencies, rerun the dependency tree before mass-updating imports; a "package does not exist" error can come from a **missing starter**, **wrong post-migration import**, **wrong scope**, or **an unrefreshed IDE classpath**.

## 11. Common version-specific errors and fixes

| Symptom | Common cause | How to check or fix |
| --- | --- | --- |
| Boot 4 reports `WebMvcTest cannot be resolved` | Only general test starter present, or old Boot 3 import kept | Add `spring-boot-starter-webmvc-test` in test scope; change import to `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` |
| Boot 4 reports `DataJpaTest cannot be resolved` | Missing `spring-boot-starter-data-jpa-test` or old Boot 3 import kept | Add the technology test starter; change import to package `org.springframework.boot.data.jpa.test.autoconfigure` |
| `@MockBean` fails to compile after upgrading to Boot 4 | Old Boot API was removed | Switch to `@MockitoBean`; review how context beans are mocked |
| `@WithMockUser` missing or behaves unexpectedly | Missing version-matching Security test support | Boot 3 adds `spring-security-test`; Boot 4 prefers `spring-boot-starter-security-test` |
| `No qualifying bean` in `@WebMvcTest` | Slice does not load service collaborators | Mock the bean with the appropriate annotation or `@Import` needed real test beans |
| `NoSuchMethodError`/`NoClassDefFoundError` | Dependencies from multiple Boot/Spring Framework major versions | Inspect tree and BOM, remove unneeded version overrides |
| Unit tests run but `@DataJpaTest` fails on datasource | Missing driver/embedded DB, wrong URL, or real backend needed | Add test DB/driver, configure test datasource or Testcontainers |
| Docker errors when running tests | Testcontainers needs a working container runtime | Verify Docker, image, permissions, and CI setup; do not blame JUnit |
| Gradle build succeeds yet does not run JUnit Jupiter tests | Test task missing JUnit Platform or wrong filter | Add `useJUnitPlatform()`, check test report and `--tests` |
| After Boot 4 upgrade, full-context test cannot inject MockMvc | Missing MVC test module or auto-configuration | Use `spring-boot-starter-webmvc-test` and `@AutoConfigureMockMvc` as needed |
| Project tests are too slow | Every test boots a full `ApplicationContext` | Move pure logic to unit tests; use test slices per layer, full context only when needed |
| Leaving `spring-boot-starter-test-classic` indefinitely | Keeping temporary compatibility classpath layout without finishing migration | Migrate piece by piece to focused starters; remove extra dependencies after verifying tests |

Do not fix compile errors by randomly adding a bunch of Boot 4 test starters; doing so defeats modularization, increases ambiguity, and makes the dependency tree hard to understand. Start from the annotation or feature being tested.

## 12. Right workflow for choosing dependencies in a real project

**Step 1 — Identify the Boot line.** Open `pom.xml` / `build.gradle(.kts)`, read the version from parent, plugin, or BOM. In multi-module projects, verify dependency management for the **module containing the tests**, not only the version at the repository root.

**Step 2 — Inventory actual tests.** Separate pure Java unit, Spring context integration, MVC/WebFlux, JPA/JDBC/Mongo, Security, GraphQL, messaging, and Testcontainers. Having a production starter alone is not enough to conclude specialized test support is needed.

**Step 3 — Choose the right starters.** In Boot 2.7/3.x, start from `spring-boot-starter-test` and add required specialized test libraries. In Boot 4, add `spring-boot-starter-<technology>-test` for each technology actually tested; the general starter comes along transitively. For pure unit tests, the general starter still works fine.

**Step 4 — Check imports.** When moving from 3 to 4, search for old `org.springframework.boot.test.autoconfigure...` imports; cross-check annotations per module. Migrate `@MockBean` to `@MockitoBean` where applicable and update HTTP test clients accordingly.

**Step 5 — Lock dependency scopes and inspect the tree.** Maven `test` or Gradle `testImplementation`/`testRuntimeOnly`. Let the BOM manage versions. Keep test databases and external connections isolated from production.

**Step 6 — Run by tier.** Run a minimal unit test to verify JUnit; slice tests to verify technology starters; integration tests to verify configuration, database, and external infrastructure. Inspect test counts and reports, not just build status.

### Acceptance checklist

- [ ] Identified the active Spring Boot line and compatible Java/toolchain.
- [ ] General test dependency uses the right version and test scope.
- [ ] If using Boot 4, focused test starters match the technologies under test.
- [ ] Boot 3 and Boot 4 imports are not mixed.
- [ ] `@MockitoBean`/`@MockBean` match the project's version.
- [ ] JUnit Platform actually executes tests and reports the expected count.
- [ ] Database, Security, GraphQL, Kafka, and Testcontainers are configured only when required by tests.
- [ ] Dependency tree contains no incompatible overrides.
- [ ] Unit, slice, and integration tests pass independently without relying on production services.

## 13. Official references to consult when upgrading

Open these links for your **exact project version**, because starter/module catalogs and annotation packages can change between releases:

1. [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html) and [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
2. [Spring Boot 4.x — Testing](https://docs.spring.io/spring-boot/reference/testing/) and [Test Modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html).
3. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): module names, technology-specific test starters, classic migration starter, and package migrations.
4. [Spring Boot — Build Systems, starter catalog](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
5. [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html) if the project uses containerized databases or brokers.

**Long-term rule:** the general test starter provides the testing foundation; technology-specific test infrastructure must be chosen according to the **Spring Boot line** and **actual test types**. When upgrading Boot, recheck artifact names, APIs/imports, JUnit runtime, and Maven/Gradle configuration before diagnosing test failures as business logic bugs.
