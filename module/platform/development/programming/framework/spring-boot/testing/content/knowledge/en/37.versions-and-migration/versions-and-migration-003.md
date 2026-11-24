# Vintage Engine for Coexisting With Legacy Tests During Migration

When migrating a Spring Boot project from a **JUnit 4** test suite to **JUnit Jupiter (JUnit 5)**, you do not have to rewrite hundreds of tests before upgrading the build. The **JUnit Vintage TestEngine** lets you **run existing JUnit 4 tests on JUnit Platform**, while new tests use the **JUnit Jupiter TestEngine**. Both engines coexist within the same test runtime so the team can migrate **class by class, module by module** without losing regression protection from the legacy suite.

The phrase **"running side by side"** requires distinguishing two meanings:
1. **Coexistence within a single suite run:** JUnit 4 and Jupiter are both discovered and executed by JUnit Platform. **This is Vintage's primary purpose.**
2. **Concurrent execution across multiple threads (parallel execution):** JUnit Platform/Jupiter/Vintage each have separate options; enabling concurrency is an additional decision carrying risks for fixtures, transactions, the context cache, and legacy JUnit 4 Rules/Runners. **Adding Vintage does not automatically make legacy tests thread-safe.**

This lesson belongs to the **Versions and Migration** group of **Spring Boot - testing**, focusing on **"Vintage engine for coexisting with legacy tests during migration"**. It covers JUnit Platform mechanics, Spring Boot 3.5 dependencies, Maven Surefire/Gradle, `SpringRunner` vs. `SpringExtension`, compatibility of runners/rules/parameterized/categories, a migration matrix, silent test-loss pitfalls, a multi-phase CI strategy, and a Maven example using **Java 17 + Spring Boot 3.5.0 + JUnit 4.13.2 + Jupiter + Vintage** with **17 test executions**. The example uses no database, Docker, web server, or external API.

> **Migration principle:** Vintage is a **temporary bridge**, not an excuse to keep writing new JUnit 4 code. Once both engines run, write new tests in Jupiter; measure how many legacy tests remain; migrate legacy tests in small batches; and finally remove JUnit 4/Vintage once no legacy tests remain.

## 1. Architecture: JUnit Platform, Jupiter, and Vintage Are Not Synonyms

JUnit 5 has three commonly encountered component groups:

| Component | Artifact/Concept | Role |
|---|---|---|
| **JUnit Platform** | Launcher, discovery selectors, filters, TestEngine SPI | Common entry point for IDEs, Maven, and Gradle to discover and execute tests |
| **JUnit Jupiter API** | `org.junit.jupiter.api.Test`, `BeforeEach`, `Assertions`, extensions | Write tests using the JUnit 5 model |
| **JUnit Jupiter Engine** | `org.junit.jupiter:junit-jupiter-engine` | Executes tests written with the Jupiter API |
| **JUnit 4 API** | `junit:junit:4.13.2`, `org.junit.Test`, `RunWith`, `Rule` | Legacy test source annotations/runners |
| **JUnit Vintage Engine** | `org.junit.vintage:junit-vintage-engine` | Allows JUnit Platform to discover/run JUnit 4 tests (and supported legacy styles) |
| **Spring TestContext** | `spring-test`, `SpringRunner`, `SpringExtension` | Integrates Spring-managed `ApplicationContext` and dependency injection into each testing model |
| **Maven Surefire** | `maven-surefire-plugin` | Launcher executing tests during the Maven `test` lifecycle phase |

```text
mvn test / IDE / Gradle
             |
             v
      JUnit Platform Launcher
             |
             +----------------------+----------------------+
             |                                             |
             v                                             v
   junit-jupiter-engine                          junit-vintage-engine
             |                                             |
             v                                             v
   org.junit.jupiter.api.Test                    org.junit.Test (JUnit 4)
   @BeforeEach / @ParameterizedTest              @Before / @Rule / @RunWith
             |                                             |
             +--------------- Spring ----------------------+
                             |
                Jupiter: SpringExtension
                JUnit 4: SpringRunner
                             |
                             v
              @SpringBootTest ApplicationContext
```

**Note on imports:** `org.junit.Test` and `org.junit.jupiter.api.Test` are **two different annotations**. Vintage does **not** convert JUnit 4 bytecode or source into Jupiter; it executes the JUnit 4 model through a compatible engine. When a test uses `@RunWith(Parameterized.class)` or a legacy `@Rule`, it still runs with JUnit 4 semantics rather than being automatically "upgraded" to Jupiter.

### 1.1. Why Do the Two Engines Not Conflict on the Name `Test`?

Because their packages differ:
- JUnit 4: `import org.junit.Test;`
- Jupiter: `import org.junit.jupiter.api.Test;`

Separate test classes can each import their respective annotation. During migration, avoid mixing both `@Test` annotations inside the **same class** as a shortcut: engine discovery can produce confusing messages, double-run, or silently drop methods. Follow a clean pattern: keep a **pure JUnit 4 class** → convert it to a **pure Jupiter class**.

### 1.2. Does Vintage Run Automatically When You Add the JUnit 4 Dependency?

**Not necessarily.** `junit:junit` supplies JUnit 4 APIs/classes; for JUnit Platform to execute them as legacy tests, `junit-vintage-engine` must be on the test runtime classpath. Conversely, having only Vintage without the matching JUnit 4 API/runtime is not enough to compile sources using `org.junit.Test`. Vintage normally pulls JUnit 4 transitively, but the example POM declares **the JUnit 4 dependency directly** as well to keep the source contract explicit.

Spring Boot 3.5's `spring-boot-starter-test` provides Jupiter, Spring Test, AssertJ, Mockito, and more—it **does not enable Vintage by default**; to run JUnit 4 tests you must add the engine explicitly. This is a notable difference if you read older guides from earlier Spring Boot releases, when `starter-test` used to pull Vintage or users were instructed to exclude Vintage after migration. Always inspect the actual dependency graph instead of guessing from a README written for another version.

## 2. Maven Dependencies in Spring Boot 3.5

### 2.1. Why Use the Boot BOM to Align JUnit Platform?

JUnit Platform, Jupiter, and Vintage share interfaces across multiple artifacts. A mismatched combination—such as Jupiter/Platform from Boot 3.5 paired with Vintage pinned to another JUnit branch—can cause `NoSuchMethodError`, `ClassNotFoundException`, discovery failures, or IDE-vs-CLI discrepancies. To reduce risk:
- Use the matching `spring-boot-starter-parent`/BOM.
- Do not mix mismatched versions of `junit-platform-*`, `junit-jupiter-*`, and `junit-vintage-*`.
- Explicitly specify a version only for **`junit:junit:4.13.2`**; let Boot manage Vintage and launcher versions.
- Use Maven Surefire managed by the Boot parent (or a version compatible with JUnit Platform).
- Run `mvn dependency:tree` whenever stale transitive test frameworks are suspected.

### 2.2. Official POM for the Runnable Example

File **`pom.xml`**:

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
    <artifactId>junit-vintage-bridge</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <!-- Jupiter, Spring TestContext, AssertJ, Mockito -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- JUnit 4 API for legacy test sources -->
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13.2</version>
            <scope>test</scope>
            <exclusions>
                <exclusion>
                    <groupId>org.hamcrest</groupId>
                    <artifactId>hamcrest-core</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <!-- Bridge JUnit 4 -> JUnit Platform -->
        <dependency>
            <groupId>org.junit.vintage</groupId>
            <artifactId>junit-vintage-engine</artifactId>
            <scope>test</scope>
            <exclusions>
                <exclusion>
                    <groupId>org.hamcrest</groupId>
                    <artifactId>hamcrest-core</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <!-- For tests verifying both engines via the Launcher API -->
        <dependency>
            <groupId>org.junit.platform</groupId>
            <artifactId>junit-platform-launcher</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why exclude `hamcrest-core`?** Spring Boot `starter-test` brings in modern Hamcrest, whereas the JUnit 4/Vintage path can pull in old `hamcrest-core` transitively. Spring Boot 3.5 docs recommend excluding `hamcrest-core` from Vintage to avoid Hamcrest duplication/version skew. This POM also excludes it on the direct JUnit 4 dependency so it is not pulled back in through that path. If a real project uses matchers from another Hamcrest version, inspect the full resolved graph before intervening.

`junit-platform-launcher` is not a separate test framework; it is present because the example includes `EngineDiscoveryTest`, which uses `LauncherFactory` to assert that **both engines are present at runtime**. If a project does not call the Launcher API directly, you may not need to declare this dependency separately when Surefire/your IDE already provides a compatible launcher; declaring it explicitly, however, gives tooling a BOM-managed version.

**Do not pin** `junit-vintage-engine` to a version outside the Boot BOM just because an old blog post shows `5.4.2`; if you must override the JUnit version, follow Spring Boot's official instructions to update **Platform/Jupiter/Vintage together**.

## 3. How Does Maven Surefire Discover and Execute Tests?

Surefire selects classes by default filename patterns such as:
- `**/Test*.java`
- `**/*Test.java`
- `**/*Tests.java`
- `**/*TestCase.java`

Then JUnit Platform/engines determine the test methods inside. The runnable project names both JUnit 4 and Jupiter classes ending with **`Test`** so none are skipped due to naming conventions.

### 3.1. Test Counts Must Include Both Vintage and Jupiter

If Vintage is accidentally dropped, `LegacyPlainTest`/`LegacySpringTest` sources may still **compile** thanks to `junit:junit`, yet **JUnit Platform has no engine to run them**. When a suite already has many Jupiter tests, the build can still PASS even though **legacy regression tests disappeared from the results**.

CI should therefore verify:
1. the `org.junit.vintage:junit-vintage-engine` dependency is present on test runtime during the transition;
2. `EngineDiscoveryTest` confirms JUnit Platform sees engine IDs `junit-vintage` and `junit-jupiter`;
3. Surefire reports contain the expected legacy classes;
4. total test counts/engine counts do not drop unexpectedly;
5. removing any JUnit 4 class is accompanied by its Jupiter replacement, never just deleting the file.

`BUILD SUCCESS` is not proof that every test was discovered. If the log reports `Tests run: 0` for a module that previously had tests, **investigate and fail CI** rather than treating it as success.

### 3.2. Run Both, or Select an Engine for Diagnostics

With Maven Surefire supporting filtering by JUnit engine IDs:

```bash
# Run both JUnit 4 via Vintage and Jupiter.
mvn test

# Run only JUnit 4/Vintage tests.
mvn test -Dsurefire.includeJUnit5Engines=junit-vintage

# Run only JUnit Jupiter tests.
mvn test -Dsurefire.includeJUnit5Engines=junit-jupiter
```

`surefire.includeJUnit5Engines` is a Surefire user property, not an annotation or Java system property interpreted by test classes. In projects with custom Surefire configurations/providers, verify the effect in reports. **Do not put a Jupiter-only filter in the main CI job** while expecting legacy tests to still run.

Selecting specific classes:

```bash
mvn -Dtest=LegacyPlainTest test
mvn -Dtest=LegacySpringTest test
mvn -Dtest=ModernSpringTest test
```

The sample project provides specific tests in Section 6. In multi-module Maven builds, `-Dtest=...` and `failIfNoSpecifiedTests` can behave differently per module; do not use `-Dtest` to judge full-reactor test counts when many modules lack a class by that name.

### 3.3. Surefire vs. Failsafe

- `maven-surefire-plugin` typically runs unit-style tests during the Maven `test` phase, matching `*Test` patterns.
- `maven-failsafe-plugin` typically runs integration-style tests during `integration-test`/`verify`, matching `*IT`/`ITCase` patterns.
- Both can use JUnit Platform/Vintage when configured properly, but **`mvn test` does not replace `mvn verify` for the Failsafe integration suite**.
- If a project has legacy `*IT` tests, inspect reports from **both Surefire and Failsafe**, not only unit test classes in `src/test/java`.
- Do not assume a "migrated Jupiter test" will automatically be discovered despite a mismatched filename. Build conventions and filters still apply.

### 3.4. Gradle Equivalent

In a Gradle project with appropriate Spring Boot/BOM dependency management, the configuration pattern is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **Gradle snippet**, not a second build inside Section 6's Maven project. With Gradle, `useJUnitPlatform()` is critical; if a build still uses the old JUnit 4 runner, the test task must switch to JUnit Platform to pick up Jupiter and Vintage engines. Check the Boot BOM/plugin setup so versions align; do not let Gradle resolve a newer Vintage version that differs from the project's Jupiter/Platform.

## 4. Spring TestContext: SpringRunner vs. SpringExtension

### 4.1. JUnit 4 Requires `@RunWith(SpringRunner.class)`

```java
@RunWith(SpringRunner.class)
@SpringBootTest
public class LegacyServiceTest {
    @Autowired
    private PricingService service;

    @Test // import org.junit.Test
    public void shouldWork() {
        assertEquals(6, service.lineTotal(2, 3));
    }
}
```

This is a snippet, not a standalone runnable file. `SpringRunner` is the JUnit 4 Runner that enables Spring TestContext to manage lifecycle, application context, injection, and test execution listeners. **Vintage is responsible for running the JUnit 4 Runner**, but **it does not automatically add `SpringRunner`** to classes that only have `@SpringBootTest`. Spring Boot 3.5 documentation explicitly notes that JUnit 4 tests need `@RunWith(SpringRunner.class)` for Spring integration.

If `@RunWith` is omitted:
- A plain JUnit 4 test that does not use Spring still runs via Vintage.
- A test with `@Autowired` but missing `SpringRunner` receives `null`/no Spring context. The test fails at runtime—or worse, fails to test what you think it tests.
- Do not try to fix this by adding `@ExtendWith(SpringExtension.class)` to a **class still using `org.junit.Test`**; a Jupiter extension does not automatically apply to Vintage methods.

### 4.2. Jupiter Uses SpringExtension (Already Included via @SpringBootTest)

```java
@SpringBootTest
class ModernServiceTest {
    @Autowired
    private PricingService service;

    @Test // import org.junit.jupiter.api.Test
    void shouldWork() {
        assertEquals(6, service.lineTotal(2, 3));
    }
}
```

In Spring Boot 3.5, `@SpringBootTest` is already meta-annotated with `@ExtendWith(SpringExtension.class)`, so **there is no need** to repeat the extension. When using plain Spring Framework tests with `@ContextConfiguration` and Jupiter, `@ExtendWith(SpringExtension.class)` or `@SpringJUnitConfig` may be required.

### 4.3. Do Not Force Both Models Into One Class

Avoid:

```java
@RunWith(SpringRunner.class)
@ExtendWith(SpringExtension.class)
class ConfusedTest {
    @org.junit.Test
    public void oldStyle() {
    }

    @org.junit.jupiter.api.Test
    void newStyle() {
    }
}
```

The snippet above is strictly an **illustrative anti-pattern**: engine filtering and lifecycle callbacks can behave unexpectedly. The goal of migration is not cramming every annotation into one class, but ensuring **each class follows exactly one engine model**. Use Vintage for existing JUnit 4 classes; migrate an entire class cleanly to Jupiter with its matching annotations/imports and extension.

### 4.4. Context Cache, Rollback, and Test Isolation

Although both JUnit 4 `SpringRunner` and Jupiter `SpringExtension` use Spring TestContext, do not assume every test class shares the same `ApplicationContext`. The cache key changes with `@SpringBootTest(classes/properties)`, `@ActiveProfiles`, `@DynamicPropertySource`, `@MockitoBean`, or differing test configurations.

- Context reuse reduces startup time, yet mutable singleton beans still persist across tests.
- `@Transactional` tests roll back by default under test-managed transactions, whereas HTTP server threads, `REQUIRES_NEW`, or async work do not automatically roll back with the test.
- `@DirtiesContext` evicts the context from the cache; overusing it slows down the suite and does not clean up committed data in an external DB.
- Running both engines in the same suite **does not mean JUnit 4 `@Before` executes before Jupiter `@BeforeEach`**; each class/method has its own lifecycle.
- Legacy tests using static fixtures, JUnit 4 `@ClassRule`, or external resources must be audited before enabling parallel execution.

## 5. JUnit 4 → Jupiter Migration Matrix

| Legacy JUnit 4 | Common Jupiter Replacement | Notes |
|---|---|---|
| `org.junit.Test` | `org.junit.jupiter.api.Test` | **Change import**, not just method signature |
| `@Before` | `@BeforeEach` | Jupiter methods can be package-private, not necessarily public |
| `@After` | `@AfterEach` | Verify cleanup and exception semantics |
| `@BeforeClass` | `@BeforeAll` | Must normally be static under `PER_METHOD` lifecycle |
| `@AfterClass` | `@AfterAll` | Verify teardown of shared resources |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` or `@SpringBootTest` meta-extension | Do not keep `@RunWith` in Jupiter |
| `@RunWith(MockitoJUnitRunner.class)` | `@ExtendWith(MockitoExtension.class)` | Requires Mockito Jupiter extension dependency |
| `@RunWith(Parameterized.class)` | `@ParameterizedTest` with `@CsvSource`/`@MethodSource` | Different model from constructor injection/runner |
| `@Rule TemporaryFolder` | `@TempDir` | Verify per-test cleanup/filesystem ownership |
| `@Rule ExpectedException` | `assertThrows(...)` | Assert exact exception type/message |
| `@Rule TestName` | `TestInfo` parameter injection | No automatic Rule callback equivalent |
| `@Rule Timeout` or `@Test(timeout=...)` | `@Timeout`/`assertTimeout` | Watch preemptive execution and Spring transactions |
| `@Ignore` | `@Disabled` | Do not batch "un-ignore" tests blindly |
| `@Category(MyCategory.class)` | `@Tag("my-category")` | Vintage exposes categories as FQN tags |
| `org.junit.Assert.assertEquals(expected, actual)` | `org.junit.jupiter.api.Assertions.assertEquals(expected, actual)` | With a message, Jupiter puts the message **last** instead of first |
| `@Test(expected=IllegalArgumentException.class)` | `assertThrows(IllegalArgumentException.class, executable)` | Assert the exact throwing call in the body |

**Do not convert all `@Rule` usages to Jupiter with a simple import swap.** Rules and custom Runners belong to the JUnit 4 extension model; Vintage continues running them with JUnit 4 semantics, whereas Jupiter has `@ExtendWith`/`@RegisterExtension`/`TestInfo`/`@TempDir` and its own extension contracts. Limited migration support exists for certain JUnit 4 rules, but never assume every custom Rule works out of the box in Jupiter.

### 5.1. JUnit 4 `@Category` Under Vintage

JUnit Vintage 5.12 converts a `@Category(com.example.legacy.Fast.class)` into a **JUnit Platform tag** using the fully qualified class name, e.g., `com.example.legacy.Fast`. Jupiter `@Tag("fast")` is a different tag string. If CI uses `-Dgroups=...`, establish an intentional tag/mapping policy so legacy tests are not accidentally dropped when a filter matches `fast` while Vintage emits `com.example.legacy.Fast`.

Do not guess new tags using wildcards on category class names. Run each engine individually and inspect reports/classifications before changing filters.

### 5.2. JUnit 4 Parameterized Runner Cannot Be Swapped Inline Immediately

Legacy:
```java
@RunWith(Parameterized.class)
public class OldParameterizedTest {
    @Parameters public static Iterable<Object[]> data() {
        // ...
    }
    @Test public void verifiesCase() {
        // ...
    }
}
```

This is a snippet for recognition, not a runnable file. Under Vintage, the JUnit 4 `Parameterized` Runner continues to be used. When migrating to Jupiter, switch to `@ParameterizedTest` with `@CsvSource` or `@MethodSource`; do not try to attach both `@RunWith(Parameterized.class)` and `@RunWith(SpringRunner.class)`, since Java/JUnit 4 does not support two runners at once. If you need Spring injection in a parameterized test, Jupiter with `SpringExtension` is a better fit.

### 5.3. Verify Equivalent Behavior, Not Just Equal Method Counts

A `@RunWith(Parameterized.class)` class may have **one `@Test` method** with **three parameter sets**, resulting in **three executions**. When converting to a `@ParameterizedTest` with three `@CsvSource` rows, confirm all three cases still execute. If a migration accidentally keeps only one row, the test method count stays identical while test coverage drops.

Similarly, custom JUnit 4 Runners can generate test cases dynamically; comparing class or method counts alone is insufficient. Use execution invocation counts/test IDs and a case matrix, especially for browser/DB/contract tests.

## 6. Runnable Java 17 + Spring Boot 3.5 Project: Two Engines in One Maven Suite

### 6.1. File Layout

```text
junit-vintage-bridge/
├── pom.xml
└── src/
    ├── main/java/com/example/vintage/
    │   ├── VintageDemoApplication.java
    │   └── PricingService.java
    └── test/
        ├── java/com/example/vintage/
        │   ├── LegacyCategory.java
        │   ├── LegacyPlainTest.java
        │   ├── LegacySpringTest.java
        │   ├── LegacyParameterizedTest.java
        │   ├── ModernSpringTest.java
        │   └── EngineDiscoveryTest.java
        └── resources/
            └── junit-platform.properties
```

All tests are deterministic; no DB, Docker, network, or fake secrets are needed. `PricingService` holds no mutable singleton state, so both JUnit 4 and Jupiter can verify the same business behavior without order dependence. The sample sets `webEnvironment=NONE` for Spring integration tests to avoid starting an HTTP server.

### 6.2. Boot Application

File **`src/main/java/com/example/vintage/VintageDemoApplication.java`**:

```java
package com.example.vintage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VintageDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(VintageDemoApplication.class, args);
    }
}
```

### 6.3. PricingService: Shared Behavior Tested Across Both Engines

File **`src/main/java/com/example/vintage/PricingService.java`**:

```java
package com.example.vintage;

import org.springframework.stereotype.Service;

@Service
public class PricingService {

    public int lineTotal(int unitPrice, int quantity) {
        if (unitPrice < 0) {
            throw new IllegalArgumentException(
                    "unitPrice must be non-negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

`Math.multiplyExact` throws `ArithmeticException` on `int` overflow; this is a standard JDK Java 17 API. Tests separate input validation from overflow so a test cannot accidentally pass via the wrong exception type. The service has no DB/clock/network dependencies; `@Service` gives Spring TestContext a bean to inject.

### 6.4. JUnit 4 Category Marker

File **`src/test/java/com/example/vintage/LegacyCategory.java`**:

```java
package com.example.vintage;

public interface LegacyCategory {
}
```

This interface only serves as a marker for JUnit 4 `@Category`. Under Vintage, it can appear under tag `com.example.vintage.LegacyCategory` in metadata. It is **not** Jupiter `@Tag("legacy")`; if filtering tags in CI, use the exact tag.

### 6.5. Plain JUnit 4 With @Rule/@Before/@After: 3 Tests

File **`src/test/java/com/example/vintage/LegacyPlainTest.java`**:

```java
package com.example.vintage;

import org.junit.After;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.experimental.categories.Category;
import org.junit.rules.TestName;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

@Category(LegacyCategory.class)
public class LegacyPlainTest {

    @Rule
    public final TestName testName = new TestName();

    private PricingService service;

    @Before
    public void setUp() {
        service = new PricingService();
    }

    @After
    public void tearDown() {
        assertNotNull(service);
    }

    @Test
    public void computesLineTotal() {
        assertEquals(10, service.lineTotal(5, 2));
        assertEquals(
                "computesLineTotal", testName.getMethodName());
    }

    @Test
    public void zeroPriceIsAllowed() {
        assertEquals(0, service.lineTotal(0, 3));
    }

    @Test(expected = IllegalArgumentException.class)
    public void zeroQuantityIsRejected() {
        service.lineTotal(3, 0);
    }
}
```

**3 JUnit 4 `@Test` methods.** This is a plain Java class: it uses `new PricingService()` without a Spring context, demonstrating that Vintage preserves JUnit 4 `@Before`, `@After`, `@Rule TestName`, and `@Test(expected=...)` semantics. It does not test Spring dependency injection; that is covered by `LegacySpringTest`.

If run with only the `junit-jupiter` engine, none of these three methods **will execute**. If run with only the `junit-vintage` engine, all three are discovered by their JUnit 4 annotations.

### 6.6. JUnit 4 Integrated With SpringRunner: 3 Tests

File **`src/test/java/com/example/vintage/LegacySpringTest.java`**:

```java
package com.example.vintage;

import org.junit.Test;
import org.junit.runner.RunWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.junit4.SpringRunner;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

@RunWith(SpringRunner.class)
@SpringBootTest(
        classes = VintageDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
public class LegacySpringTest {

    @Autowired
    private PricingService service;

    @Test
    public void springInjectsRealService() {
        assertNotNull(service);
    }

    @Test
    public void calculatesUsingSpringBean() {
        assertEquals(21, service.lineTotal(7, 3));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsNegativeUnitPrice() {
        service.lineTotal(-1, 2);
    }
}
```

**3 JUnit 4 `@Test` methods.** `@RunWith(SpringRunner.class)` is the key piece: `SpringRunner` starts the TestContext/lifecycle and injects the service, while Vintage bridges Platform to the JUnit 4 Runner. This test class allows upgrading Maven/Boot/JUnit Platform while keeping legacy code intact.

With JUnit 4, `public` test classes and `public void` `@Test` methods avoid classic visibility constraints; Jupiter allows package-private and non-public methods under standard conditions. Do not prematurely alter modifiers or imports of legacy tests before establishing a baseline.

### 6.7. JUnit 4 Parameterized Runner: 3 Invocations

File **`src/test/java/com/example/vintage/LegacyParameterizedTest.java`**:

```java
package com.example.vintage;

import java.util.Arrays;
import java.util.Collection;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;
import org.junit.runners.Parameterized.Parameters;

import static org.junit.Assert.assertEquals;

@RunWith(Parameterized.class)
public class LegacyParameterizedTest {

    private final int unitPrice;
    private final int quantity;
    private final int expected;

    public LegacyParameterizedTest(
            int unitPrice, int quantity, int expected) {
        this.unitPrice = unitPrice;
        this.quantity = quantity;
        this.expected = expected;
    }

    @Parameters(name = "{index}: {0} x {1} = {2}")
    public static Collection<Object[]> cases() {
        return Arrays.asList(new Object[][] {
                {2, 3, 6},
                {0, 4, 0},
                {7, 1, 7}
        });
    }

    @Test
    public void computesForEachCase() {
        PricingService service = new PricingService();
        assertEquals(
                expected,
                service.lineTotal(unitPrice, quantity));
    }
}
```

The class has **one `@Test` method**, while `@Parameters` supplies three cases, so Vintage/JUnit 4's Parameterized Runner executes **three invocations**. This is important evidence when comparing test counts during migration. Jupiter `@ParameterizedTest` will replace this model, though during the transition the runner stays as-is.

### 6.8. Jupiter + Spring Boot: 4 @Test + 3 Parameterized Invocations

File **`src/test/java/com/example/vintage/ModernSpringTest.java`**:

```java
package com.example.vintage;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = VintageDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ModernSpringTest {

    @Autowired
    private PricingService service;

    @Test
    void springInjectsRealService() {
        assertNotNull(service);
    }

    @Test
    void calculatesUsingSpringBean() {
        assertEquals(21, service.lineTotal(7, 3));
    }

    @Test
    void rejectsZeroQuantityWithAssertThrows() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class,
                        () -> service.lineTotal(4, 0));

        assertEquals("quantity must be positive",
                error.getMessage());
    }

    @Test
    void reportsArithmeticOverflowSeparately() {
        assertThrows(ArithmeticException.class,
                () -> service.lineTotal(
                        Integer.MAX_VALUE, 2));
    }

    @ParameterizedTest(name = "{index}: {0} x {1} = {2}")
    @CsvSource({
            "2, 3, 6",
            "0, 4, 0",
            "7, 1, 7"
    })
    void calculatesCsvCases(
            int unitPrice, int quantity, int expected) {
        assertEquals(expected,
                service.lineTotal(unitPrice, quantity));
    }
}
```

This consists of **4 Jupiter `@Test` methods** + **1 `@ParameterizedTest` method running 3 times** = **7 Jupiter test invocations**. There is no `@RunWith`. With Spring Boot `@SpringBootTest`, Jupiter receives `SpringExtension` through the meta-annotation.

Look at the pair `LegacySpringTest` and `ModernSpringTest`: they intentionally test some overlapping behaviors to prove migration can coexist in one suite, whereas in a real project you should **migrate the legacy test and then delete the duplicate legacy version** instead of keeping duplicates permanently and inflating build costs.

### 6.9. Verifying Engine IDs via JUnit Platform Launcher: 1 Test

File **`src/test/java/com/example/vintage/EngineDiscoveryTest.java`**:

```java
package com.example.vintage;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.TestPlan;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.platform.engine.discovery.DiscoverySelectors
        .selectClass;

class EngineDiscoveryTest {

    @Test
    void jupiterAndVintageAreBothDiscoverable() {
        LauncherDiscoveryRequest request =
                LauncherDiscoveryRequestBuilder.request()
                        .selectors(
                                selectClass(LegacyPlainTest.class),
                                selectClass(ModernSpringTest.class))
                        .build();

        TestPlan plan = LauncherFactory.create()
                .discover(request);

        Set<String> ids = plan.getRoots().stream()
                .map(TestIdentifier::getUniqueId)
                .collect(Collectors.toSet());

        assertThat(ids).contains(
                "[engine:junit-jupiter]",
                "[engine:junit-vintage]");
    }
}
```

This test uses **Launcher discovery** and does not call `execute(...)` on other tests, avoiding recursive execution from an engine-check test. It will FAIL if either `junit-vintage` or `junit-jupiter` cannot be found at runtime when selectors target those classes.

**Limitation of this test:** discovering both engines does not prove the pipeline actually **executes all** legacy tests. Surefire could still apply engine filters, exclusions, or filename patterns. Surefire reports + CI checks on total test counts/migration coverage remain necessary. `EngineDiscoveryTest` is an easy-to-read canary for the bridge phase; once JUnit 4 migration finishes and Vintage is intentionally removed, **update or delete the canary along the roadmap** rather than keeping an assertion demanding a removed engine.

### 6.10. JUnit Platform Properties: Do Not Enable Parallelism Accidentally

File **`src/test/resources/junit-platform.properties`**:

```properties
# Both engines are discovered in the same JUnit Platform run.
# Do not set a global include/exclude engine filter here.

junit.jupiter.execution.parallel.enabled=false
junit.vintage.execution.parallel.enabled=false
```

The sample focuses on **coexistence** between JUnit 4 and Jupiter, not thread safety. In JUnit 5.12, Vintage has its own configuration parameters for parallel classes/methods; because legacy suites use Rules and static fixtures, keeping **parallelism disabled** until audited is the safest default.

### 6.11. Running the Demo and Checking Test Counts

In the directory containing `pom.xml`, with **JDK 17+** and Maven:

```bash
mvn test
```

Expected **17 executions**:

| Class | Engine | Methods | Invocations |
|---|---|---:|---:|
| `LegacyPlainTest` | Vintage/JUnit4 | 3 | 3 |
| `LegacySpringTest` | Vintage/JUnit4 + SpringRunner | 3 | 3 |
| `LegacyParameterizedTest` | Vintage/JUnit4 Parameterized | 1 | 3 |
| `ModernSpringTest` | Jupiter + SpringExtension | 5 (4 @Test, 1 @ParameterizedTest) | 7 |
| `EngineDiscoveryTest` | Jupiter + Platform Launcher | 1 | 1 |
| **Total** | **2 engines** | **13** | **17** |

Counts per engine: **Vintage = 9 invocations**, **Jupiter = 8 invocations**. Do not assume every invocation corresponds to a separate source method because parameterized runners generate multiple cases.

You can also run:

```bash
# With Surefire filters supporting JUnit engine selection:
mvn test -Dsurefire.includeJUnit5Engines=junit-vintage
mvn test -Dsurefire.includeJUnit5Engines=junit-jupiter
```

Expected filtered runs are **9** and **8** invocations, respectively. If a filter does not behave as expected due to plugin version or custom providers, check official Surefire configuration and reports rather than assuming from the command typed.

**Do not fabricate stdout:** Maven Surefire displays class names, test counts, durations, and Spring startup logs differently depending on versions. The numbers **17/9/8** are expected from the sample code, not copied output executed in the authoring environment.

Check the dependency tree and reports:

```bash
mvn dependency:tree
mvn test
```

After running, inspect `target/surefire-reports` to verify results exist for **all five test classes**. In CI, a JUnit XML aggregator/quality gate can compare against the baseline and alert if legacy classes disappear. When a project uses Failsafe, also check `target/failsafe-reports` and run `mvn verify`.

## 7. Vintage and Jupiter Running Side by Side: Things That Do NOT Automatically Unify

### 7.1. `@Before` and `@BeforeEach` Do Not Share a Lifecycle

A JUnit 4 test only recognizes JUnit 4 Runner `@Before`/`@After`; Jupiter only recognizes Jupiter `@BeforeEach`/`@AfterEach`. Do not put Jupiter `@BeforeEach` in a superclass and expect it to run when a JUnit 4 Vintage test executes. To share fixture logic, extract plain Java helpers and invoke them from each framework's lifecycle methods.

### 7.2. JUnit 4 Rules Continue Working Under Vintage

Vintage runs the JUnit 4 Runner, so valid `@Rule TestName`, `TemporaryFolder`, or custom JUnit 4 Rules continue working **with JUnit 4 semantics**. It does not convert rules into Jupiter extensions. When migrating a class to Jupiter, map each Rule to `@TempDir`, `TestInfo`, `@RegisterExtension`, or a dedicated extension; do not just delete `@Rule` to make code compile while losing cleanup/logging/timeout behavior.

### 7.3. JUnit 4 `@RunWith` Allows Only One Runner at a Time

A JUnit 4 class cannot have two valid `@RunWith` annotations to combine `SpringRunner` and `Parameterized` in the usual way. If a legacy suite uses a custom Runner:
- keep the runner intact during the Vintage phase if still compatible;
- evaluate whether the runner invokes Spring TestContext;
- migrate to the Jupiter extension and parameterized model when appropriate;
- write behavioral regression tests before changing the extension architecture.

Do not "fix" tests by slapping `@RunWith(SpringRunner.class)` onto every class, as that can break a custom runner responsible for generating test cases.

### 7.4. Spring Boot Annotations Do Not Replace TestEngine

`@SpringBootTest` is a test context bootstrapper/extension integration, not a JUnit 4 engine. Without Vintage, legacy tests will not magically appear just because a class has `@SpringBootTest`. Without `@RunWith(SpringRunner.class)`, Vintage may execute JUnit 4 methods without Spring-managed injection. The two failures **are distinct**:
- missing engine → test does not run;
- missing runner → test runs without the expected Spring context behavior.

### 7.5. Jupiter `@Test` on a Public Method Is Not a JUnit 4 Test

A `public void foo()` method annotated with `org.junit.jupiter.api.Test` is **not** a JUnit 4 test, even though it uses JUnit 4's `public void` style. Conversely, `org.junit.Test` on a package-private method violates JUnit 4 public visibility rules and leads to an initialization error. During automated import refactoring, check visibility and annotations for the target framework.

### 7.6. Assertion APIs and Message Order

JUnit 4:
```java
org.junit.Assert.assertEquals(
        "total must match", 6, service.lineTotal(2, 3));
```

Jupiter:
```java
org.junit.jupiter.api.Assertions.assertEquals(
        6, service.lineTotal(2, 3), "total must match");
```

Same result, **different message position**. The compiler catches many mismatches, yet some overloads accept compatible types such that a test compiles while printing the wrong failure message. Verify semantics rather than relying solely on search-and-replace on imports.

### 7.7. Exception and Timeout Semantics Need Review

JUnit 4 `@Test(expected=...)` checks for an exception anywhere inside the test method; Jupiter `assertThrows(...)` checks the exact **executable** supplied. This is an opportunity to tighten assertions, such as checking expected messages or causes. For timeouts, `@Timeout`/`assertTimeoutPreemptively` carry thread/lifecycle implications; with Spring test-managed `@Transactional`, a preemptive timeout can move business calls to another thread outside the transaction and commit data instead of rolling back. Do not convert `@Test(timeout=...)` mechanically when tests hold DB transactions.

## 8. True Parallel Execution Is a Separate Topic

### 8.1. The Demo Defaults to Sequential Execution

Above:
```properties
junit.jupiter.execution.parallel.enabled=false
junit.vintage.execution.parallel.enabled=false
```

Test classes share the same suite without a "run across 4 threads" policy. Vintage 5.12 supports its own keys, for example (for reference only, **do not put in the runnable project**):

```properties
junit.vintage.execution.parallel.enabled=true
junit.vintage.execution.parallel.classes=true
junit.vintage.execution.parallel.methods=false
junit.vintage.execution.parallel.pool-size=2
```

Enable these flags only after auditing legacy fixtures, static state, Spring context caching, ports/filesystem, and databases. **JUnit Vintage has separate parallel settings** from `junit.jupiter.execution.parallel.enabled`; do not assume enabling Jupiter parallelism automatically runs Vintage methods concurrently.

### 8.2. Risks When Both Engines Share Resources

- Spring TestContext maintains a **static context cache** in the same JVM. Legacy `SpringRunner` and Jupiter `SpringExtension` may use equivalent context keys, yet mutable singleton state remains shared.
- A JUnit 4 `@ClassRule` may bind a server on a fixed port; another Jupiter test using the same port will fail.
- Legacy tests may use `static Map`/shared clocks/system properties; concurrent execution can trigger races.
- Mockito mocks/spies and `@MockitoBean` inside a cached context have lifecycle/reset behavior that must be checked to prevent competing stub/verify calls.
- `@DirtiesContext` can close a context while another test is still running; Spring Framework recommends avoiding parallelism with such tests.
- `@Transactional` tests do not necessarily roll back side effects from `RANDOM_PORT`, `REQUIRES_NEW`, or async workers.
- Do not run global `TRUNCATE` across the DB while multiple tests execute concurrently; use unique run IDs and scoped cleanup.
- Test ordering via `@FixMethodOrder` in JUnit 4 or Jupiter `@TestMethodOrder` can hide dependencies; enabling parallelism breaks order assumptions.
- "Parallel flakiness" is not a reason to delete Vintage: the root cause is concurrency/data isolation and requires fixing fixtures or synchronization.

**Safe plan:** run both engines **sequentially** first and capture a baseline; then opt-in isolated test classes to parallel execution in a CI job sized for the CPU/network budget. Do not flip a suite-wide flag just to shave runtime while ignoring reproducibility.

## 9. Phased Migration Roadmap

### Phase 0 — Establish Baseline

1. On a stable branch, record test counts by module/class and PASS/FAIL rates.
2. Categorize tests into plain JUnit 4, JUnit 4 `SpringRunner`, `Parameterized`, `Category`, custom Runners, Rules, and JUnit 3.
3. Verify CI actually runs the legacy tests (do not merely read the code).
4. Ensure Java 17/Spring Boot 3.5/plugin versions are compatible with test dependencies.
5. Document external fixtures, DB cleanup, flaky tests, and engine filters.

**Exit criterion:** every legacy test class that must be kept has its name and invocation count recorded in a report. Do not rush to change imports before the baseline is trustworthy.

### Phase 1 — Enable Vintage, Keep Legacy Code

1. Add the JUnit 4 dependency and `junit-vintage-engine` in `test` scope.
2. Keep `spring-boot-starter-test` to run Jupiter.
3. Verify Surefire/Gradle test tasks use JUnit Platform.
4. Run `mvn test` and inspect reports for both Vintage and Jupiter.
5. Add an engine discovery canary or CI gate on test counts.
6. Do not enable parallelism immediately.

**Exit criterion:** the build PASSES with both engines, legacy tests have not vanished, and reports confirm coverage is preserved.

### Phase 2 — Write New Tests With Jupiter

- All new classes import `org.junit.jupiter.api.Test`.
- Use `@ParameterizedTest`, `assertThrows`, `@TempDir`, and Jupiter extensions.
- With Spring Boot `@SpringBootTest`, omit `@RunWith`.
- When Mockito is needed in Jupiter, use `MockitoExtension` or Spring bean overrides at the proper boundary.
- Do not add new JUnit 4 tests simply because Vintage is available.

**Exit criterion:** the proportion of Jupiter tests grows per module while JUnit 4 counts do not increase.

### Phase 3 — Migrate Legacy Classes One by One

For each legacy class:
1. Record current behavior and expected test invocations (including parameter sets).
2. Convert `Test`/`Assertions`/`Before`/`After`/`Ignore`/`Category` imports.
3. Replace `@RunWith` with the corresponding Jupiter extension model; `@SpringBootTest` already provides the meta-extension.
4. Migrate Rules and custom runners to Jupiter extensions/test fixtures.
5. Run the migrated class individually and with the full suite; verify data setup/cleanup/transactions.
6. **Delete or retire the legacy JUnit 4 class** only after its behavior is replaced and CI coverage is verified.

**Exit criterion:** no JUnit 4 annotations remain in migrated modules; Jupiter tests run on the Jupiter engine and case counts have not dropped.

### Phase 4 — Remove Vintage Once No Legacy Tests Remain

- Search for legacy `org.junit.*` imports in `src/test` (distinguishing platform/jupiter APIs from JUnit 4).
- Check custom runners/rules/libraries for transitive JUnit 4 dependencies.
- Run a full `mvn verify` if Failsafe is used.
- Remove `junit-vintage-engine` and `junit:junit` from dependencies.
- Update/remove `EngineDiscoveryTest` if it requires Vintage.
- Only the Jupiter engine (and any intentionally used engines) remains in reports.
- Watch test counts after dependency cleanup to ensure no legacy class was overlooked.
- Remove legacy engine filters/tags and update onboarding/CI docs.

**Exit criterion:** zero regression tests rely solely on JUnit 4; fewer engines and dependencies are an intentional result, not an "accidental green build".

## 10. Common Errors When Enabling Vintage

| Symptom | Possible Cause | Check / Action |
|---|---|---|
| JUnit 4 classes compile but do not run | `junit:junit` present without Vintage engine | Check test runtime dependencies and Surefire reports |
| `Tests run: 0` despite test sources | Wrong filenames, missing engine, filter/exclude | Check patterns, engine IDs, test selectors |
| `@Autowired` is null in JUnit 4 test | Missing `@RunWith(SpringRunner.class)` | Use `SpringRunner`, not `@SpringBootTest` alone |
| Jupiter test has `@RunWith` and misses expected lifecycle | Mixed annotations/JUnit frameworks | Migrate the whole class cleanly to Jupiter APIs |
| `NoSuchMethodError` from Platform/Launcher | Mismatched Platform/Jupiter/Vintage versions | Let Boot BOM manage versions; inspect dependency tree |
| Parameterized class only runs 1 case | Migration dropped input rows | Compare invocations/case data before and after |
| Jupiter `@BeforeEach` does not run on JUnit 4 test | Different framework lifecycle | Use JUnit 4 `@Before` or migrate the class |
| `@Rule` stops working after swapping `@Test` | Rules are not Jupiter extensions | Migrate the Rule to an extension/fixture |
| JUnit 4 `@Category` fails `@Tag("legacy")` filter | Vintage uses FQN category tags | Adjust the CI tag expression |
| Vintage-only run drops Jupiter tests | Fixed engine filter left configured | Run the unfiltered suite; gate both engines |
| JUnit 4 test runs twice | Duplicate plugin/provider or suite selectors | Check Surefire config, runners, and reports |
| Repeated context startups | Different profiles/mock overrides per test class | Check cache keys/logs and standardize where sensible |
| H2/DB state leaks across engines | Shared database/context cache, missing cleanup | Unique test IDs, rollback/cleanup, avoid global `TRUNCATE` |
| Flaky after enabling parallelism | Non-thread-safe Rules/static fixtures | Disable parallelism, isolate resources, enable gradually |
| JUnit 4 tests visible in IDE but not Maven | Different IDE JUnit Platform config/version | Reload Maven dependencies; select Platform runner |
| Legacy JUnit 3 tests missed by runner | Compatibility varies by Surefire version | Prefer upgrading to JUnit 4.12+ or Jupiter and verify reports |
| `@Ignore` still skips legacy test | JUnit 4 behavior preserved | Remove skip only after fixing root cause |
| `@Test(timeout)` migration leaves transaction residue | Different timeout/preemptive thread semantics | Design timeouts around client/transaction boundaries |
| Vintage removed before migration finishes | Legacy test coverage vanishes | Engine canary, test inventory, revert dependency removal |
| Vintage still present with zero JUnit 4 code | Bridge left around too long | Audit and remove dependency post-migration |

## 11. Setting CI Criteria to Prevent "False Green" Builds

There are at least three valuable quality gates:

1. **Engine presence gate:** while JUnit 4 tests remain, the JUnit Platform runtime must see `junit-vintage`, alongside `junit-jupiter` for new tests—for example via `EngineDiscoveryTest`.
2. **Execution count gate:** reports must contain legacy class names and expected invocation counts, not just `dependency:tree`. Add thresholds per module/engine and adjust intentionally in PRs when tests are added or retired.
3. **Behavior gate:** for critical behaviors, Jupiter replacements must assert the same invariants and negative cases. Two tests running does not prove they assert the same business rules.

### Do Not Hardcode Total Counts Forever

In the sample project, **17 invocations** are expected across the 5 classes in Section 6. In a production suite, test counts naturally change as coverage grows or is consolidated; use a **baseline review/gate updated explicitly in PRs** rather than treating any count delta as an absolute failure. In particular, `@ParameterizedTest` and JUnit 4's Parameterized Runner produce invocation counts that differ from method declarations.

A report may also contain **skipped tests** from `@Ignore`/`@Disabled`; track executed, skipped, and failure/error counts separately. If tests are disabled during a quick migration, total discovered counts may still look high while effective coverage drops.

### Never Ignore Missing Engines

When a module contains **only JUnit 4 tests**, Surefire may report no tests executed if Vintage is missing or selection fails. Build plugin options like `failIfNoTests`/`failIfNoSpecifiedTests` depend on Surefire versions; verify your current config. CI should treat "a critical module executed zero tests" as an error, regardless of a zero Maven exit code.

### Run Maven/Failsafe at the Right Scope

`mvn test` runs Surefire by default; if the project has integration tests managed by Failsafe, run `mvn verify`. In a multi-module reactor where some modules have no JUnit 4 tests, distinguish a legitimately test-free module from missing tests caused by engine misconfiguration. Do not force Vintage into every module: keep the bridge only in modules not yet migrated.

## 12. Checklist Before Declaring the Bridge Phase Complete

- [ ] Project uses Java 17+ and compatible Spring Boot/JUnit/Surefire versions.
- [ ] I understand JUnit Platform is the launcher, while Jupiter and Vintage are two separate engines.
- [ ] `spring-boot-starter-test` provides Jupiter while **Vintage is declared explicitly at test runtime**.
- [ ] `junit:junit:4.13.2` is present for legacy JUnit 4 test sources.
- [ ] JUnit Platform/Jupiter/Vintage artifacts are aligned via the Spring Boot BOM.
- [ ] Dependency tree has been inspected to prevent JUnit/Hamcrest conflicts.
- [ ] Surefire or Gradle is configured to run JUnit Platform.
- [ ] No engine filter accidentally excludes `junit-vintage` in the full job.
- [ ] Legacy file patterns/class names are discovered by Surefire/Failsafe.
- [ ] JUnit 4 `@Test` imports `org.junit.Test`, and Jupiter tests import `org.junit.jupiter.api.Test`.
- [ ] Spring Boot JUnit 4 classes use `@RunWith(SpringRunner.class)`.
- [ ] Jupiter Spring Boot classes use `@SpringBootTest`/`SpringExtension` without retaining `@RunWith`.
- [ ] Legacy `@Rule`, `@ClassRule`, and custom Runners keep their semantics under Vintage until migrated.
- [ ] JUnit 4 Parameterized cases are tracked by **invocations**, not just test methods.
- [ ] JUnit 4 `@Category` tag mapping is accounted for when using groups/tag filters.
- [ ] A canary/CI gate proves both engines are discoverable while needed.
- [ ] Surefire reports confirm legacy classes actually executed.
- [ ] A green build is not assumed to mean all legacy tests ran.
- [ ] Enabling both engines is not treated as enabling parallel threads.
- [ ] Vintage/Jupiter parallel settings are evaluated separately; concurrency is off until isolation is audited.
- [ ] Spring context cache, `@DirtiesContext`, mutable singletons, and DB/Redis/Kafka/file fixtures are handled properly.
- [ ] New tests use Jupiter only, with a roadmap to shrink legacy test counts.
- [ ] Every class migration includes behavioral regression and case-count comparison.
- [ ] Once legacy tests are gone, Vintage/JUnit 4 dependencies are removed and engine canaries/CI filters updated.
- [ ] `mvn verify` is checked when Failsafe integration tests exist.
- [ ] The bridge dependency is not left in place permanently simply because "it works".

**Conclusion:** **JUnit Vintage** is a practical way to **preserve JUnit 4 regression tests while migrating incrementally to JUnit Jupiter** on the same JUnit Platform. It **does not automatically upgrade code, does not add `SpringRunner`, does not align `@Rule` with Jupiter, and does not make tests run concurrently by default**. Migration quality depends on **correct dependencies/engine discovery, accurate test execution counts, proper Spring test lifecycles, fixture isolation, and a controlled plan to remove the bridge**.

### Official References

- [Spring Boot 3.5 — Testing and Vintage Engine](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html)
- [Spring Boot 3.5 — @SpringBootTest With JUnit 4 SpringRunner and JUnit 5](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit 5.12 — User Guide: Migrating from JUnit 4, Vintage Engine, Categories, Parallel Execution](https://docs.junit.org/5.12.0/user-guide/)
- [JUnit 5.12 — JUnit Platform Launcher API](https://junit.org/junit5/docs/5.12.0/api/org.junit.platform.launcher/org/junit/platform/launcher/core/LauncherFactory.html)
- [Maven Surefire — JUnit Platform, Engine Filtering](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Surefire — Configuring JUnit](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit.html)
- [Spring Framework 6.2 — Spring TestContext Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html)
