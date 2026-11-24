# Structure of `src/test/java`, `src/test/resources`, and Package Organization in Spring Boot

A Spring Boot project can run the application normally yet have tests that are hard to maintain if test code, sample data, and environment configuration are mixed together. Proper organization helps readers quickly answer four questions: **which test protects which class/feature, where are the fixtures located, which configuration is the test loading, and which command will run that test?**

Lesson objectives: understand the roles of the two standard Maven/Gradle test directories, choose appropriate packages for unit/slice/integration tests, use classpath resources properly, and avoid mistakes that make tests pass only on a local machine.

## 1. Production source and test source are two separate source roots

For a Java Spring Boot project using the standard layout, Maven and the Gradle Java plugin recognize the following directories:

| Path | What does it contain? | Where is it present? |
|---|---|---|
| `src/main/java` | Application Java source: controllers, services, domain, repositories, config | Compiled into main classes; can be packaged into the application |
| `src/main/resources` | Configuration and resources for application runtime, e.g., `application.yml`, templates, migrations | Main runtime classpath; typically included in the application artifact |
| `src/test/java` | Test Java code: JUnit tests, helpers, fakes, factories, test support configuration | Test compile/runtime classpath; not packaged into the application JAR by default |
| `src/test/resources` | JSON/CSV/XML fixtures, SQL files, test profile configuration, sample data | Test runtime classpath; not packaged into the application JAR by default |

A **source root** is the base path from which the build tool infers packages and the classpath. It is not part of the Java package name. Therefore, a file at `src/test/java/com/example/shop/order/ShippingPolicyTest.java` declares `package com.example.shop.order;`, not `package src.test.java.com.example...`.

When running tests, the test classpath typically contains **`main` classes + `test` classes + resources from both + test dependencies**. As a result, code in `src/test/java` can use classes from `src/main/java` and the JUnit library, while production source cannot depend on helpers that exist only in test. An application running from a release artifact also cannot see fixtures located only in `src/test/resources` by default.

> Remember: `src/test/java` is for **executable test code**; `src/test/resources` is for **test data/configuration**. Do not place Java test cases in resources or put JSON fixtures as long string constants across multiple test classes if they need to be shared.

## 2. Sample directory tree by feature

Example Spring Boot module named `shop`, root package `com.example.shop`:

```text
shop/
├── pom.xml                          # or build.gradle(.kts)
└── src/
    ├── main/
    │   ├── java/com/example/shop/
    │   │   ├── ShopApplication.java
    │   │   ├── order/
    │   │   │   ├── OrderController.java
    │   │   │   ├── OrderService.java
    │   │   │   └── ShippingPolicy.java
    │   │   └── customer/
    │   │       └── CustomerService.java
    │   └── resources/
    │       └── application.yml
    └── test/
        ├── java/com/example/shop/
        │   ├── ShopApplicationContextTest.java
        │   ├── order/
        │   │   ├── ShippingPolicyTest.java
        │   │   ├── OrderControllerTest.java
        │   │   ├── OrderServiceTest.java
        │   │   └── OrderRepositoryIT.java
        │   ├── customer/
        │   │   └── CustomerServiceTest.java
        │   └── testing/
        │       ├── OrderTestDataFactory.java
        │       └── IntegrationTestSupport.java
        └── resources/
            ├── application-test.yml
            ├── fixtures/
            │   └── orders/
            │       ├── create-order-valid.json
            │       └── create-order-invalid.json
            └── sql/
                ├── orders-before.sql
                └── orders-cleanup.sql
```

This is an **illustrative structure**, not a mandatory file list. Only create packages and helpers that are actually used. For example, a module without persistence does not need `OrderRepositoryIT` or an `sql` directory.

### Package placement rules

1. **Keep tests close to the subject under test**: production code `com.example.shop.order.ShippingPolicy` has its test at `com.example.shop.order.ShippingPolicyTest`. Mirroring the production package makes it easy for the IDE to navigate back and forth.
2. **Do not mechanically append `.test` to every package**: `com.example.shop.order` is appropriate for unit tests that need to check package-private members. `com.example.shop.order.test` is a different Java package and has no package-private access.
3. **Group by feature when production code is grouped by feature**: if the application is already divided into `order`, `customer`, `payment`, tests should follow the same boundaries. If the project organizes by `service`/`repository`/`web`, you can mirror that structure, but avoid creating an independent test package tree that cannot be traced back to main code.
4. **Separate genuinely shared utilities**: for example `com.example.shop.testing.OrderTestDataFactory` to build valid test data; do not put real business logic into test helpers that makes tests rely on a duplicate copy of the behavior being tested.
5. **Place tests in a subpackage of the package containing `@SpringBootApplication`** when you want Spring Boot to automatically locate the root configuration. Depending on the setup, `@SpringBootTest` and test slices locate the `@SpringBootConfiguration` class by scanning upward from the test package to parent packages. If a test is placed outside that package tree, you must specify the configuration explicitly, such as `@SpringBootTest(classes = ShopApplication.class)`.

**Mirroring the production package does not mean every test needs to boot Spring.** Plain JUnit unit tests can sit next to the corresponding class and instantiate objects directly; only use a Spring context when the behavior being verified depends on bean wiring, web, database, or Spring configuration.

## 3. Complete unit test example: where does the file live, and how is the package written?

Suppose shipping costs 30,000 VND for orders under 500,000 VND; 500,000 VND and above gets free shipping. Negative input is rejected.

File **`src/main/java/com/example/shop/order/ShippingPolicy.java`**:

```java
package com.example.shop.order;

public final class ShippingPolicy {
    public long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }
        return subtotalVnd >= 500_000 ? 0 : 30_000;
    }
}
```

File **`src/test/java/com/example/shop/order/ShippingPolicyTest.java`**:

```java
package com.example.shop.order;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {
    private final ShippingPolicy policy = new ShippingPolicy();

    @Test
    void feeAppliesBelowThreshold() {
        assertEquals(30_000, policy.feeVnd(499_999));
    }

    @Test
    void freeShippingStartsAtThreshold() {
        assertEquals(0, policy.feeVnd(500_000));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeVnd(-1));
    }
}
```

The example requires Java 17+ and JUnit Jupiter (usually included via a test dependency such as `spring-boot-starter-test` matching the project's Spring Boot version). With Maven Wrapper and the test plugin configured, run this class alone:

```bash
./mvnw -Dtest=ShippingPolicyTest test
```

Or on Gradle with JUnit Platform enabled:

```bash
./gradlew test --tests "com.example.shop.order.ShippingPolicyTest"
```

On Windows, use `mvnw.cmd` or `gradlew.bat`. Expected result: **3 tests pass**. No business stdout is required. The test does not need `@SpringBootTest`, loads no beans, and touches no DB; the right path and matching production package help both the IDE and build tool discover the class easily.

The name `ShippingPolicyTest` describes the subject under test; the method names describe behavior. A test class should focus on one clear subject or responsibility; do not create a giant `AllTests.java` just because classes share the same package.

## 4. `src/test/resources`: classpath paths differ from OS filesystem paths

Suppose we create the file **`src/test/resources/fixtures/orders/create-order-valid.json`**:

```json
{
  "sku": "BOOK-001",
  "quantity": 2
}
```

At test runtime, the resource has the classpath path **`fixtures/orders/create-order-valid.json`**. The `src/test/resources` prefix does not appear in the classpath resource name.

Example test reading a fixture without depending on the current working directory.

File **`src/test/java/com/example/shop/order/OrderFixtureTest.java`**:

```java
package com.example.shop.order;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderFixtureTest {
    @Test
    void loadsOrderRequestFromTestClasspath() throws Exception {
        try (InputStream input = Objects.requireNonNull(
                getClass().getResourceAsStream(
                        "/fixtures/orders/create-order-valid.json"))) {
            String json = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(json.contains("\"BOOK-001\""));
        }
    }
}
```

Expected: the test passes when the JSON file is at the right path. `Objects.requireNonNull` clearly reports a missing resource; in real code, you can use an assertion with a message describing the path. This path pair is very important:

| Access method | Correct path |
|---|---|
| `SomeTest.class.getResourceAsStream(...)` | `"/fixtures/orders/create-order-valid.json"` with a leading `/` to resolve from the classpath root |
| `SomeTest.class.getClassLoader().getResourceAsStream(...)` | `"fixtures/orders/create-order-valid.json"` without a leading `/` |
| Spring `ClassPathResource` | `new ClassPathResource("fixtures/orders/create-order-valid.json")` |

If you use `Class.getResourceAsStream("create-order-valid.json")` without a leading `/`, Java looks up the resource **relative to the test class's package** (e.g., `com/example/shop/order/`), which is usually not where root fixtures are placed. That is a common cause of `null` and `NullPointerException`.

**Avoid** `Files.readString(Path.of("src/test/resources/..."))` in tests that need to run across all environments: this approach depends on the current working directory and how the build tool lays out the project. Reading via the classpath works much better for CI, running tests from an IDE, and submodules. Only use filesystem paths when the behavior under test actually involves disk file operations.

### How should sample data be organized?

- `fixtures/orders/`: HTTP/JSON request data; separate `valid`, `missing-field`, `invalid-state` by the scenario being tested.
- `sql/`: setup/cleanup scripts when DB integration tests exist; name them to reflect the suite or scenario, avoiding one giant SQL file used by all tests.
- `contracts/` or `stubs/`: schemas and sample responses of external services when actually using contract/stub tests.
- `application-test.yml`: lives at the root of test resources because Spring Boot searches for configs by standard names on the classpath.
- Do not put secrets, real tokens, real personal data, or very large binaries into fixtures; use fake, deterministic, reproducible data.

If a fixture serves only a single test, placing it in a subdirectory named after the feature is sufficient. If multiple tests share a fixture, keep one canonical copy and avoid mutating global state during tests (which can introduce test-order dependency).

## 5. Configuring `application-test.yml` and the test profile

File **`src/test/resources/application-test.yml`**:

```yaml
app:
  greeting: "hello-from-test"
logging:
  level:
    root: WARN
```

Place `@ActiveProfiles("test")` on tests that **use a Spring context** to enable the `test` profile and load configuration according to Spring Boot rules:

File **`src/test/java/com/example/shop/TestProfileLoadingTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class TestProfileLoadingTest {
    @Value("${app.greeting}")
    private String greeting;

    @Test
    void readsTestProfileConfig() {
        assertEquals("hello-from-test", greeting);
    }
}
```

Condition: `@SpringBootApplication` is present in `com.example.shop` (or an explicit root configuration is specified). Expected result is **1 test pass** when the application can initialize the context with the configured dependencies. `application-test.yml` is only automatically applied when the `test` profile is activated appropriately; **merely creating the file does not guarantee it is always in effect**.

Spring Boot typically merges base configuration such as `application.yml` with profile-specific configuration; profile values take precedence according to Spring's config loading rules. Do not place another `application.yml` at the test root to accidentally shadow the application's content if your real goal is selective overrides: use `application-test.yml`, `@TestPropertySource`, or `@DynamicPropertySource` depending on the need.

For databases or brokers started by Testcontainers, the host/port can change on every run; retrieve connection details from the container and register them into the Spring Environment using the appropriate supported mechanism (`@DynamicPropertySource`, or service connection if the version supports it) instead of hardcoding ports. Do not use production connection details as fallbacks in test profiles.

**Distinguish two configuration layers:** `@ActiveProfiles` selects the **Spring** profile for tests that have an application context; whether Gradle/Maven runs the test class is decided by the **build/test engine**, not by the profile name.

## 6. How does the test package affect the Spring Boot context?

Consider the application:

```text
src/main/java/com/example/shop/ShopApplication.java
src/test/java/com/example/shop/order/OrderControllerTest.java
src/test/java/com/example/shop/ShopApplicationContextTest.java
```

`ShopApplication` is typically in the root package `com.example.shop`. Tests in `com.example.shop.order` reside beneath the root package, so Spring Boot can locate the configuration when a test uses an annotation like `@SpringBootTest` or a slice test that supports that mechanism.

There are three common layout patterns:

| Goal | Where to place the test | How the context is loaded |
|---|---|---|
| Unit test of `OrderService` | Same package as `OrderService` | No Spring context needed |
| Web slice of `OrderController` | `order` package, beneath the app root | `@WebMvcTest(OrderController.class)` with required mocks/security setup |
| Integration across controller, service, and DB | Feature package or `com.example.shop.integration`, beneath the root | `@SpringBootTest` plus corresponding real test dependencies/environment |

Do not let a unit test boot a context just because it sits in an `integration` package, and do not assume a test is treated as an integration test merely because the file has an `IT` suffix. Annotations, dependencies, source sets, and actual build tasks determine what runs.

If the same repository contains **multiple Spring Boot applications** or **multiple `@SpringBootConfiguration` classes** that could be discovered, specify `classes = ...` or explicit test configuration to avoid loading the wrong context. When using `@WebMvcTest`, keep in mind that the slice only loads the relevant web layer; services are mocked/stubbed as needed, and DB behavior is not verified by the slice.

**`@TestConfiguration`**, when needed to declare auxiliary beans for tests, belongs in test code (for example in `src/test/java` or as a nested static class inside a test) and is imported/loaded intentionally. Do not put test-only beans into `src/main/java` just to make tests run more easily, as that alters the production artifact or bean scanning.

## 7. Naming classes, test suites, and run commands

An intuitive naming set within a feature:

- `ShippingPolicyTest`: unit test for business rules.
- `OrderControllerTest`: HTTP/MVC slice or controller test; check annotations to see actual scope.
- `OrderRepositoryIT`: integration test with DB; the `IT` suffix signals intent, though build configuration is needed to run it at the desired phase.
- `ShopApplicationContextTest`: verifies context startup; does not replace business assertions.

**Maven:** Maven Surefire by default matches `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java`. Names like `*IT.java` are typically intended for Maven Failsafe with its configuration and the `integration-test` / `verify` lifecycle; do not assume `mvn test` already runs all `*IT` tests.

**Gradle:** test classes in the `test` source set are run by the `test` task when the test engine and JUnit Platform are configured accordingly. If you want to separate integration tests, create a dedicated source set/task or use JUnit tags and filters in the build script; the `*IT` suffix alone does not create a separate task. For example, a Gradle Groovy DSL project may need:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Reference common commands from the module directory containing `pom.xml` or `build.gradle`:

```bash
# Maven: run standard tests
./mvnw test

# Maven: select one unit test class by name
./mvnw -Dtest=ShippingPolicyTest test

# Gradle: run the test task
./gradlew test

# Gradle: select one class by fully qualified name
./gradlew test --tests "com.example.shop.order.ShippingPolicyTest"
```

On Windows, use the corresponding wrapper with `.cmd` or `.bat`. Actual commands and task names depend on the module's build; for example, `./gradlew :shop:test` when running a multi-module build from the root.

Do not trust the IDE showing a Run button as proof that CI will run that test. Always verify test discovery patterns, the JUnit engine, tasks, and pipeline commands. If you place tests in `src/integrationTest/java` without declaring the source set/plugin, the build tool may neither compile nor run them.

## 8. Multi-module projects: each module owns its tests

With Maven multi-module or Gradle multi-project:

```text
project-root/
├── settings.gradle
├── order-domain/
│   └── src/
│       ├── main/java/...
│       └── test/java/...
└── order-api/
    └── src/
        ├── main/java/...
        ├── test/java/...
        └── test/resources/application-test.yml
```

- Unit tests for `order-domain` should live inside the `order-domain` module, where they can run independently without depending on the web framework.
- Web tests for `order-api` belong in `order-api`, where Spring MVC and the appropriate application configuration live.
- Only create a separate `integration-test` module or source set when there is a practical reason: running across multiple services, needing different dependencies, a different schedule, and clear ownership. Creating a directory alone does not create a task.
- If multiple modules share fixtures/helpers, prefer extracting fixtures into an explicitly configured test artifact, such as Gradle `java-test-fixtures` or a clearly published Maven test-JAR configuration. Never make a production module depend on another module's test source set.
- In a monorepo with multiple applications, do not create a "global" test package and rely on accidental context scanning. Each module must know which application/configuration is its target under test.

## 9. How to inspect source roots and fixtures when errors occur

| Symptom | Common cause | How to fix |
|---|---|---|
| `package ... does not exist` when compiling tests | File is in the wrong source root, wrong package/import, or missing test dependency | Check path under `src/test/java`, `package` declaration, dependencies, and build configuration |
| IDE detects JUnit but `mvn test` does not run `*IT` classes | Surefire and Failsafe have different patterns/scopes | Configure Failsafe for integration tests or rename to match the desired task |
| `getResourceAsStream` returns `null` | Missing/extra leading `/` in resource path, wrong directory, or not on test classpath | Check path from `src/test/resources` root and Class vs. ClassLoader lookup rules |
| Tests pass in IDE but fail in CI | Filesystem path depends on working directory, different profile, or test not included in task | Use classpath resources, inspect environment, and run the exact wrapper/task |
| `Unable to find a @SpringBootConfiguration` | Test package is outside the application package tree or root configuration cannot be found | Place beneath the root package or specify `classes = ShopApplication.class` |
| Tests hit the real DB by mistake | Test profile is not active or datasource is not overridden | `@ActiveProfiles("test")`, verified test datasource, explicit container/test DB config |
| Tests read wrong property value | Multiple `application*.yml` files, profiles, or property sources have different precedence than expected | Check active profiles, config imports, and actual precedence order |
| Tests sharing data fail intermittently | Mutable/shared fixture state, missing cleanup, or test-order dependency | Create isolated data per test, use proper transactions/cleanup, reset dependencies |
| Tests run slowly even for a single calculation | Unnecessary use of `@SpringBootTest` | Write plain JUnit unit tests for standalone logic |

Specifically for SQL scripts: `@Sql(scripts = "/sql/orders-before.sql")` in Spring integration tests uses the classpath (assuming the file is at `src/test/resources/sql/orders-before.sql`). Understand when the script runs, whether the transaction rolls back, and whether it actually cleans up enough data. Do not assume `@Transactional` on a test automatically rolls back transactions executed in another thread/process during an HTTP E2E test.

## 10. Checklist for organizing a testable Spring Boot module

- [ ] Production Java is in `src/main/java` and test Java is in `src/test/java`; declared packages match the path from each source root.
- [ ] Test classes sit close to the production package/feature they protect; names indicate the subject or behavior.
- [ ] Test fixtures/configs live in `src/test/resources` and are referenced via classpath rather than environment-dependent relative filesystem paths.
- [ ] `application-test.yml` contains only safe test values; tests using a Spring context explicitly activate the profile.
- [ ] Plain unit tests do not boot Spring unnecessarily; slice/integration tests load the right configuration and real dependencies.
- [ ] Helpers, fakes, and `@TestConfiguration` stay in test scope; no reverse dependency from production code into test code.
- [ ] `*Test`/`*IT` conventions, source sets, and Maven/Gradle tasks match what CI actually runs.
- [ ] Multi-application modules clearly specify `@SpringBootConfiguration` and each test suite's boundaries.
- [ ] Test data is reproducible, isolated, free of secrets, and backed by a reliable cleanup strategy.
- [ ] At least one test can be run via the wrapper from the command line, and you can explain which resources/classpath it uses.

**Key takeaway:** `src/test/java` defines **test code**, `src/test/resources` defines **test classpath data/configuration**, while packages and build tasks define **what a test covers and how it is discovered/executed**. Use a structure that mirrors the application's features and explicit configuration so every test is easy to locate, rerun, and trust in CI.
