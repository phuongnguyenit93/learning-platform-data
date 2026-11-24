# JUnit 5 and JUnit 6: Compatibility With Your Current Spring Boot Line

## 1. The Question: Which JUnit Should Your Current Spring Boot Project Use?

In the **Spring Boot - testing** module, **Versions and Migration** group, a Spring Boot project may already have hundreds of tests written with `org.junit.jupiter.api.Test`, `@SpringBootTest`, Mockito, AssertJ, parameterized tests, and JUnit Platform. Upon seeing JUnit 6 released, teams commonly ask:

- Does an application on **Spring Boot 3.5** need to immediately bump `junit-jupiter` to `6.x`?
- Does **Spring Boot 4.1** provide JUnit 6 already? Can JUnit Platform 1.x be paired with Jupiter 6.x?
- Does moving from JUnit 5 → JUnit 6 require changing `org.junit.jupiter.*` imports to a new package?
- Will a test written in JUnit 4 run automatically when `spring-boot-starter-test` is added?
- If Gradle/Maven reports `No tests found`, `TestEngine` not found, `NoSuchMethodError`, or context startup errors, what is the root cause?
- How do you verify the **actual resolved dependency tree** instead of guessing from blog posts, an IDE, or a version declared in one file?

**Practical rule:** by default, **let the Spring Boot BOM/parent manage the entire JUnit version set**, use `spring-boot-starter-test`, and declare the JUnit Platform launcher in the proper scope. Do not bump Jupiter alone to a new major version inside an older Boot application without verifying compatibility across the full test stack.

As of the official documentation verification on **November 8, 2026**, two stable reference points are **Spring Boot 3.5.16** and **Spring Boot 4.1.2**. This lesson provides an exact compatibility matrix for them, explains real changes in JUnit 6, presents two alternative `build.gradle` files, provides a shared Java 17/JUnit/Spring/Mockito test suite, shows the Maven equivalent, gives dependency inspection commands, and outlines a CI migration plan. **Do not confuse structural/code checks in this material with having actually executed Gradle/JUnit.**

## 2. Matrix Verified From Spring Boot Managed Dependency Coordinates

| Spring Boot Line / Reference Release | Spring Framework | JUnit Jupiter | JUnit Platform | Minimum Java | Recommended Approach |
| --- | --- | --- | --- | --- | --- |
| **Spring Boot 3.4.13** | Spring Framework 6.2 | **5.11.4** | **1.11.4** | **17** | Keep Boot BOM-managed JUnit 5 |
| **Spring Boot 3.5.16** | Spring Framework 6.2 | **5.12.2** | **1.12.2** | **17** | Keep JUnit 5; this is Sample A |
| **Spring Boot 4.0.x (per BOM 4.0)** | Spring Framework 7 | **6.0.3** in the consulted BOM 4.0 | **6.0.3** | **17** | Boot BOM-managed JUnit 6; audit test starters/Boot APIs |
| **Spring Boot 4.1.2** | Spring Framework 7.0 | **6.0.3** | **6.0.3** | **17** | JUnit 6; this is Sample B |

The versions in this table are **managed defaults of the referenced BOMs**, not a claim that every patch release in the same line keeps the exact same version string. For example, JUnit 5 already has 5.14.x releases, yet **Boot 3.5.16 manages 5.12.2**; a library releasing a newer version does not automatically change Boot's managed dependency.

**Important naming note:** in JUnit 5, `Jupiter 5.12.2` pairs with **Platform 1.12.2**, not Platform 5.12.2. Starting with **JUnit 6**, Platform, Jupiter, and Vintage artifacts align on the **same version 6.0.3** in the reference BOM. Do not mix `org.junit.jupiter:junit-jupiter:6.0.3` with `org.junit.platform:junit-platform-launcher:1.12.2`.

Spring Boot 4.1.2 supports Gradle **8.14+ in the 8.x line** or **Gradle 9.x** and Maven **3.6.3+**; Spring Boot 3.5.16 supports Gradle **7.6.4+ in the 7.x line** or **8.4+ in the 8.x line** and Maven **3.6.3+**. Both require Java 17+. The examples pick **Gradle 8.14.3 + JDK 17** because it sits in the intersection of both supported matrices.

### Warnings About the 3.x and 4.x Lines

- Do not assume **any Spring Boot 3** project can independently upgrade Jupiter to 6 and still have a supported configuration.
- Do not assume **on Spring Boot 4** that application code and Boot 3 Spring test-slice imports stay unchanged: Boot 4 introduces **modular test starters** and removed/changed Spring Boot APIs.
- Do not take JUnit 6's Java 17 support as proof that Boot 2.x runs on Java 17/JUnit 6: you must check Boot, Framework, launcher, and plugins together.
- Do not take "a test runs in the IDE" as proof that CI with Maven/Gradle and all test engines are compatible.

## 3. JUnit Has Three Components, Not Just One Dependency

Modern JUnit consists of three subprojects:

~~~text
                     Test code
          @Test / @ParameterizedTest
                     |
                     v
              JUnit Jupiter API
                     |
                     v
              JUnit Jupiter Engine
                     |
                     v
               JUnit Platform
          Launcher / TestEngine SPI
                     |
                     v
              Gradle / Maven / IDE
~~~

| Component | Typical Artifact Name | Role |
| --- | --- | --- |
| Jupiter API | `org.junit.jupiter:junit-jupiter-api` | Annotations, assertions, extension APIs |
| Jupiter Engine | `org.junit.jupiter:junit-jupiter-engine` | Discovers and runs tests written with Jupiter |
| Jupiter aggregate | `org.junit.jupiter:junit-jupiter` | Convenience dependency pulling aligned API/engine/params |
| Jupiter Params | `org.junit.jupiter:junit-jupiter-params` | `@ParameterizedTest`, `@CsvSource`, and parameter sources |
| Platform Launcher | `org.junit.platform:junit-platform-launcher` | API for Gradle/Maven/IDEs to launch TestEngines |
| Platform Commons/Engine | `org.junit.platform:junit-platform-commons/engine` | Shared APIs and infrastructure |
| Vintage Engine | `org.junit.vintage:junit-vintage-engine` | Runs legacy JUnit 3/4 tests on Platform; **deprecated in JUnit 6** |
| Spring Test | `org.springframework:spring-test` | `SpringExtension`, TestContext, mocks/integration |
| Spring Boot Test | `spring-boot-starter-test` and test modules | Boot bootstrap, test facilities + managed JUnit/Mockito/AssertJ |

`spring-boot-starter-test` saves you from assembling individual JUnit Jupiter, AssertJ, and Mockito artifacts; however, it does not remove the need to verify **the launcher on test runtime** or compatibility with custom testing plugins.

**JUnit 5 = Platform 1.x + Jupiter 5.x + Vintage 5.x. JUnit 6 = Platform 6.x + Jupiter 6.x + Vintage 6.x.** This is a **real version scheme change**, not a typo in the docs.

## 4. What Does Not Change When Moving From JUnit 5 to JUnit 6

JUnit 6 is designed so most existing Jupiter source code continues to compile. Core imports **do not change**:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.api.extension.ExtendWith;
~~~

`@Test`, `@BeforeEach`, `@AfterEach`, `@ParameterizedTest`, `@CsvSource`, `@TempDir`, `@Nested`, `assertEquals`, `assertThrows`, `assertAll`, `MockitoExtension`, and `SpringExtension` **remain unchanged** (when paired with compatible dependencies). There is no `org.junit6.*` package.

That does not mean every custom extension or build plugin is immediately binary-compatible. The **public JUnit API** is broadly preserved, yet long-deprecated APIs were removed, Java/Kotlin baselines increased, and JSpecify nullability can affect static analysis or Kotlin compilation.

### JUnit 5 → 6 Differs From JUnit 4 → 5

Upgrading `JUnit 5 Jupiter` to `JUnit 6 Jupiter` does **not** require rewriting all tests to new annotations. By contrast, moving from `JUnit 4` to `JUnit Jupiter` is a major programming-model change: `@RunWith`, `@Before`/`@After`, `@Rule`, `@Test(expected=...)`, and JUnit 4 runners/parameterization require migration. Do not treat these two tasks as the same step.

## 5. Actual JUnit 6 Changes You Must Review

According to the JUnit 6.0 migration/release notes:

| Topic | JUnit 5 | JUnit 6 | Action |
| --- | --- | --- | --- |
| Java runtime baseline | Java 8+ for JUnit 5 | **Java 17+** | Upgrade test JVM and Gradle/Maven/CI JDK if needed |
| Platform version number | **1.x** | **6.x** (aligned with Jupiter/Vintage) | Align Platform, engine, and launcher |
| `MethodOrderer.Alphanumeric` | Deprecated | **Removed** | Use `MethodOrderer.MethodName` or `OrderAnnotation` per real semantics |
| `InvocationInterceptor.interceptDynamicTest(Invocation, ExtensionContext)` | Deprecated old API | **Removed** | Update custom JUnit extensions |
| `junit.jupiter.tempdir.scope` property | Deprecated | **No longer supported** | Use lifecycle/`@TempDir` via proper API |
| `@CsvFileSource(lineSeparator=...)` | Deprecated option | **Removed** | Let JUnit auto-detect `\r`/`\n`/`\r\n` |
| `junit-platform-runner` | Legacy module for JUnit 4 runner | **Removed** | Use Platform launcher/engines; migrate runner |
| `junit-platform-jfr` | Separate module | **Removed**; JFR support moved into launcher | Remove old dependency; use launcher |
| Vintage Engine | Present | **Deprecated** | Use temporarily only if JUnit 4 tests remain |
| Kotlin metadata/nullability | Older baseline | Higher Kotlin baseline, JSpecify nullability | Check Kotlin/IDE/static checkers |
| Test annotation package | `org.junit.jupiter` | **Still `org.junit.jupiter`** | Do not mass-rename imports |
| Maven Surefire/Failsafe | Depends on current version | **JUnit 6 requires >=3.0.0** | Upgrade test plugins accordingly |

**Do not automatically edit every `@CsvSource` or `@ParameterizedTest` as if they were removed.** Only truly removed/deprecated APIs require code migration. For `@CsvFileSource`, parser behavior and malformed-CSV error messages may differ, while basic valid inputs remain supported.

JUnit 6.0.x introduces JSpecify annotations to describe API nullability; strict null-checkers may warn differently. That does not mean ordinary Java code must annotate every parameter with `@Nullable`.

## 6. Which JUnit Should You Choose? A Quick Decision Table

| Real-World Situation | Preferred Decision |
| --- | --- |
| On Spring Boot 3.4/3.5, tests stable | Keep Boot BOM-managed JUnit 5; resolve any dependency alignment issues |
| On Boot 3.5, wanting to bump JUnit 6 alone because it is newer | **Not by default**; fully evaluate Spring Test, build tool, and all test engines; prefer upgrading to Boot 4 in a dedicated migration |
| Upgrading app to Boot 4.1.2 | Use Boot-managed JUnit 6.0.3; **no need to force JUnit 6 manually** |
| Java runtime still below 17 | Cannot run JUnit 6; upgrade JDK first |
| JUnit 4 tests still need to run | Add Boot-managed JUnit 4 + Vintage engine of matching major temporarily; plan Jupiter migration |
| Framework/library project not using Boot BOM | Use **JUnit BOM** with matching version for Jupiter, Platform, and Vintage |
| IDE runs tests but Gradle runs 0 tests | Check launcher, `TestEngine`, `Test` task, source sets, and filters |
| Boot 4 API tests fail to compile | Check Spring Boot 4 test modularization/import removals; **do not blame JUnit 6 by default** |
| Mockito integration on Spring Boot 4 | Use `@MockitoBean`/`@MockitoSpyBean` and `MockitoExtension`; `@MockBean`/`@SpyBean` are removed |
| Maven has JUnit 6 with Surefire 2.x | Upgrade Surefire/Failsafe >=3.0.0, not just the Jupiter version |

**Treat versions as a cohesive set:** Spring Boot plugin/parent, Spring Framework, JUnit Jupiter/Platform/Vintage, Mockito, AssertJ, JDK, Gradle/Maven, and IDE engine support.

## 7. Gradle Build A — Spring Boot 3.5.16 Using Boot-Managed JUnit 5

This is a **complete `build.gradle`** for Option A, Groovy DSL, JDK 17, Gradle Wrapper 8.14.3:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

**Expected dependencies from the Spring Boot 3.5.16 BOM:** Jupiter **5.12.2**, Platform launcher **1.12.2**. Do not put a version after `spring-boot-starter-test`, `junit-platform-launcher`, or individual JUnit artifacts. Spring Boot dependency management selects tested versions automatically.

### Why Declare the Launcher Explicitly?

`spring-boot-starter-test` brings in Jupiter API/engine and testing libraries. `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` guarantees the launcher is present on test runtime with the **BOM-managed version**. JUnit and Gradle docs recommend an explicit declaration, especially when upgrading Gradle/IDEs. Even if a project already receives the launcher transitively, declaring it explicitly simplifies auditing.

### Do Not Force Jupiter 6 Into Option A

This is an **anti-pattern**, not a working config:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:6.0.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}
~~~

It pairs Jupiter 6 with Platform 1.12 from different release trains, risking linkage and discovery errors. Nor should you assume setting `ext['junit-jupiter.version']='6.0.3'` in Boot 3.5 automatically updates `junit-platform.version` and every transitive extension: you must inspect the BOM/version graph if an unusual override is required.

## 8. Gradle Build B — Spring Boot 4.1.2 Using Boot-Managed JUnit 6

Use this **alternative complete `build.gradle`**, replacing Option A entirely:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

**Expected dependencies from the Spring Boot 4.1.2 BOM:** Jupiter **6.0.3**, Platform launcher **6.0.3**. JUnit 6 has a Java 17 baseline, matching this toolchain. Spring Boot 4.1 uses Spring Framework 7.0; API/auto-configuration differences beyond JUnit are a separate part of migration to review.

Both Gradle scripts share **the exact same Java/JUnit tests** in the sections below. Do not copy both `plugins` blocks into one file, and do not override JUnit versions to be "newer than the BOM" without verified need and compatibility.

**Boot 4 modularization note:** core `spring-boot-starter-test` still exists and provides Jupiter/Mockito/AssertJ; however, for specific technologies like web/JPA/security/GraphQL, Spring Boot 4 introduces **`spring-boot-starter-<technology>-test`**. A Boot 3 `@WebMvcTest` may require the dedicated WebMVC test starter on Boot 4; this example intentionally uses only core `@SpringBootTest` to keep the sources shared across both builds.

## 9. Gradle Wrapper, Java Toolchain, and Setup Commands

**`settings.gradle`:**

~~~groovy
rootProject.name = 'junit-boot-compatibility-demo'
~~~

With Gradle installed locally to generate the wrapper:

~~~bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
./gradlew --version
java -version
~~~

On Windows:

~~~powershell
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
.\gradlew.bat --version
java -version
~~~

Once generated, commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, and `gradle/wrapper/gradle-wrapper.properties`. Avoid relying on system Gradle in CI, which can drift between dev machines and CI. Pin a trusted Gradle distribution/checksum per organization policy.

**Three Javas can differ:** the JDK running the Gradle daemon, the toolchain compiling Java, and the runtime JVM executing `Test` tasks. `java.toolchain` helps Gradle pick a compatible build/test JDK, yet if the Gradle daemon itself runs on an unsupported JDK, the build fails before applying the toolchain. Run `./gradlew --version` to verify Gradle's JVM, and `./gradlew test --info` to inspect task execution.

Gradle 8.14.3 sits in the **intersection of Boot 3.5 and Boot 4.1**; Gradle 9 should only be paired with Boot 4.1 rather than claiming Boot 3.5 supports Gradle 9.

## 10. Shared Project Structure Runnable Under Either Configuration

~~~text
settings.gradle
build.gradle              # choose ONLY A or B
gradle/wrapper/...
gradlew
gradlew.bat

src/main/java/com/example/junitmatrix/
    JunitMatrixApplication.java
    GreetingService.java
    PriceCalculator.java
    RateGateway.java
    CurrencyConverter.java

src/main/resources/
    application.properties

src/test/java/com/example/junitmatrix/
    PriceCalculatorTest.java
    FileFixtureTest.java
    MockitoBoundaryTest.java
    SpringBootCompatibilityTest.java

src/test/resources/
    application-test.properties
~~~

**Only four test classes.** Three are unit/Mockito/file tests that do not start Spring, and one is an integration class that boots the Boot `TestContext`. There are **eight annotated test methods** (including one `@ParameterizedTest` running three datasets), yielding **ten logical test invocations**. Numbers displayed in a Gradle/IDE report can vary in container/display grouping, so QA should inspect actual XML/reports. **Do not give a unit test the same name as a production class or place an extra `@SpringBootApplication` inside `src/test`**.

Build options A and B use **this exact same source set**, with no H2, Docker, or web server. That way, if either build fails, you can isolate JUnit/Spring/Mockito/Gradle compatibility without database noise.

## 11. Spring Boot Application and Simple Bean

**`src/main/java/com/example/junitmatrix/JunitMatrixApplication.java`:**

~~~java
package com.example.junitmatrix;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JunitMatrixApplication {
    public static void main(String[] args) {
        SpringApplication.run(JunitMatrixApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/junitmatrix/GreetingService.java`:**

~~~java
package com.example.junitmatrix;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${lesson.greeting:Hello}") String prefix
    ) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }
        return prefix + ", " + name.strip() + "!";
    }

    public String prefix() {
        return prefix;
    }
}
~~~

**`src/main/resources/application.properties`:**

~~~properties
lesson.greeting=Hello
spring.main.banner-mode=off
~~~

A `@SpringBootTest` in the same `com.example.junitmatrix` package finds `JunitMatrixApplication` through Spring Boot's lookup mechanism. A test activating the `test` profile reads `application-test.properties` on the test classpath without packaging test-only properties into the production JAR.

**`src/test/resources/application-test.properties`:**

~~~properties
lesson.greeting=Integration
~~~

Expected:
- When constructed manually via `new GreetingService("Unit")`: `greet(" An ")` -> `Unit, An!`.
- In a Spring test with profile `test`: `GreetingService.prefix()` -> `Integration`, `greet(" An ")` -> `Integration, An!`.
- In the normal application without profile `test`: prefix `Hello`.

The two builds use different Spring Framework versions, yet the Java/Spring annotations above are supported across all referenced versions.

## 12. Pure Business Logic Using JUnit Jupiter

**`src/main/java/com/example/junitmatrix/PriceCalculator.java`:**

~~~java
package com.example.junitmatrix;

public final class PriceCalculator {

    public long afterDiscount(
            long originalCents,
            int discountPercent
    ) {
        if (originalCents < 0
                || discountPercent < 0
                || discountPercent > 100) {
            throw new IllegalArgumentException(
                    "Invalid price or discount"
            );
        }

        // Prototype uses integer cents and integer division only.
        long numerator = Math.multiplyExact(
                originalCents,
                100L - discountPercent
        );
        return numerator / 100L;
    }
}
~~~

The formula uses integer cents and **truncates fractional cents**. `Math.multiplyExact` throws `ArithmeticException` if multiplication overflows `long`; production monetary logic should use a dedicated money type/`BigDecimal` with explicit currency, rounding policy, and overflow bounds. In this demo, amounts are small so results are deterministic.

Examples:
- 1,000 cents with 10% discount -> 900.
- 500 cents with 20% discount -> 400.
- 199 cents with 10% discount -> floor(179.1 cents) = 179.
- 0% discount -> keeps original amount.
- 100% discount -> 0.

Testing this code needs no Spring context, Mockito, or database; do not use `@SpringBootTest` to test pure arithmetic.

## 13. PriceCalculatorTest: @Test, @ParameterizedTest, @CsvSource

**`src/test/java/com/example/junitmatrix/PriceCalculatorTest.java`:**

~~~java
package com.example.junitmatrix;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {

    private final PriceCalculator calculator =
            new PriceCalculator();

    @Test
    void calculatesTenPercentDiscount() {
        assertEquals(
                900L,
                calculator.afterDiscount(1_000L, 10)
        );
    }

    @ParameterizedTest
    @CsvSource({
        "1000, 10, 900",
        "500, 20, 400",
        "199, 10, 179"
    })
    void worksForParameterizedExamples(
            long original,
            int percent,
            long expected
    ) {
        assertEquals(
                expected,
                calculator.afterDiscount(original, percent)
        );
    }

    @Test
    void rejectsInvalidArguments() {
        assertAll(
            () -> assertThrows(
                    IllegalArgumentException.class,
                    () -> calculator.afterDiscount(-1L, 10)
            ),
            () -> assertThrows(
                    IllegalArgumentException.class,
                    () -> calculator.afterDiscount(100L, -1)
            ),
            () -> assertThrows(
                    IllegalArgumentException.class,
                    () -> calculator.afterDiscount(100L, 101)
            )
        );
    }
}
~~~

These are **three test methods**: two `@Test` and one `@ParameterizedTest` with **three invocations**; i.e., **five test invocations** in JUnit Jupiter logic. All imports and annotations above **remain unchanged** between JUnit Jupiter 5.12.2 and 6.0.3.

`@CsvSource` requires `junit-jupiter-params` on the test classpath, already provided by `spring-boot-starter-test`. If Maven/Gradle reports `ParameterizedTest cannot be resolved`, inspect the actual test dependencies first rather than altering the annotation.

Case `199,10,179` verifies the truncation rule: 199 × 90 / 100 = 179 remainder 10. If a different rounding rule is required, change the domain logic and assertions rather than treating it as a JUnit bug.

## 14. @TempDir: Still Present in JUnit 6

**`src/test/java/com/example/junitmatrix/FileFixtureTest.java`:**

~~~java
package com.example.junitmatrix;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FileFixtureTest {

    @Test
    void createsUtf8FileInsideTempDirectory(
            @TempDir Path tempDir
    ) throws IOException {
        Path file = tempDir.resolve("customer.txt");
        String value = "Hello JUnit";

        Files.writeString(
                file,
                value,
                StandardCharsets.UTF_8
        );

        assertTrue(Files.exists(file));
        assertEquals(
                value,
                Files.readString(file, StandardCharsets.UTF_8)
        );
    }
}
~~~

This is **one `@Test` method**. JUnit manages temporary directory lifecycle; tests do not need to write to fixed paths in the project root or use `Thread.sleep`. **JUnit 6 did not remove the `@TempDir` annotation.** What was removed is the **old deprecated configuration parameter `junit.jupiter.tempdir.scope`**, so systems keeping that property must remove it and use the proper JUnit 6 lifecycle API.

Running on both Windows and Linux uses `Path` and explicit UTF-8 encoding rather than assuming `/` separators or the default platform charset. `Files.writeString` requires JDK 11+, which is valid under Java 17 here.

## 15. MockitoExtension in Both JUnit 5 and 6

**`src/main/java/com/example/junitmatrix/RateGateway.java`:**

~~~java
package com.example.junitmatrix;

public interface RateGateway {
    int multiplier();
}
~~~

**`src/main/java/com/example/junitmatrix/CurrencyConverter.java`:**

~~~java
package com.example.junitmatrix;

import java.util.Objects;

public class CurrencyConverter {

    private final RateGateway rates;

    public CurrencyConverter(RateGateway rates) {
        this.rates = Objects.requireNonNull(
                rates, "rates"
        );
    }

    public long convert(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException(
                    "cents must not be negative"
            );
        }

        int multiplier = rates.multiplier();
        if (multiplier <= 0) {
            throw new IllegalStateException(
                    "rate must be positive"
            );
        }

        return Math.multiplyExact(cents, multiplier);
    }
}
~~~

`CurrencyConverter` is not annotated with `@Component`. It is a pure unit fixture and does not create missing-bean dependencies that would break `@SpringBootTest` later. Its method calls the stubbed gateway and validates inputs, showing Mockito running **on the JVM** independently of a Spring context.

**`src/test/java/com/example/junitmatrix/MockitoBoundaryTest.java`:**

~~~java
package com.example.junitmatrix;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MockitoBoundaryTest {

    @Mock
    RateGateway rates;

    @InjectMocks
    CurrencyConverter converter;

    @Test
    void convertsWithTestScopedMock() {
        when(rates.multiplier()).thenReturn(3);

        assertEquals(600L, converter.convert(200L));
        verify(rates).multiplier();
    }

    @Test
    void invalidMultiplierIsNotRetried() {
        when(rates.multiplier()).thenReturn(0);

        assertThrows(
                IllegalStateException.class,
                () -> converter.convert(200L)
        );
        verify(rates).multiplier();
    }
}
~~~

These are **two `@Test` methods**. `@ExtendWith(MockitoExtension.class)` is the Jupiter extension compatible with the Boot-managed Mockito version. It is not synonymous with `@MockitoBean`: `@Mock`/`@InjectMocks` create test-scoped mocks/fixtures and **do not replace beans** in the Spring `ApplicationContext`. To mock a bean for an `@Autowired` service, use Spring `@MockitoBean` where appropriate and avoid running concurrent tests against shared mocks/contexts.

### Spring Boot 4 and MockitoTestExecutionListener

Boot 4 removes the deprecated `MockitoTestExecutionListener` (related to `@Mock`/`@Captor` behavior inside a context). For **pure Mockito unit tests**, use `MockitoExtension` explicitly as above. Spring test Mockito errors after a Boot 4 upgrade may stem from listener or bean override changes rather than `org.junit.jupiter.api.Test` disappearing.

## 16. Real @SpringBootTest on Both Boot Lines

**`src/test/java/com/example/junitmatrix/SpringBootCompatibilityTest.java`:**

~~~java
package com.example.junitmatrix;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
class SpringBootCompatibilityTest {

    @Autowired
    GreetingService greetings;

    @Autowired
    ApplicationContext context;

    @Test
    void loadsAppAndTestProfile() {
        assertNotNull(
                context.getBean(JunitMatrixApplication.class)
        );
        assertEquals(
                "Integration",
                greetings.prefix()
        );
        assertEquals(
                "Integration, An!",
                greetings.greet(" An ")
        );
    }

    @Test
    void rejectsBlankInputInManagedBean() {
        assertThrows(
                IllegalArgumentException.class,
                () -> greetings.greet("   ")
        );
    }
}
~~~

These are **two `@Test` methods**. Placing the test class in the root package of `@SpringBootApplication` lets Spring Boot autodetect the main source; `@ActiveProfiles("test")` loads `src/test/resources/application-test.properties`. Since it starts no web server and needs no database, this is a lean Spring context integration smoke test for both Boot 3.5 and 4.1.

**Compatibility points:** `@SpringBootTest`, `@ActiveProfiles`, `@Autowired`, `ApplicationContext`, and `org.junit.jupiter.api.Test` remain supported across Spring Boot 3.5/Spring 6.2/JUnit 5 and Spring Boot 4.1/Spring 7/JUnit 6. The test avoids Boot 3-specific test-slice packages or the removed `@MockBean` so it stays directly comparable.

Do not use this test to claim **every** `@WebMvcTest`, `@DataJpaTest`, Spring Security setup, Jackson 2/3 feature, Kafka consumer, or plugin in a real project is compatible. It only smoke-tests a Spring context with property binding and DI without additional infrastructure.

## 17. Counting Test Methods and Invocations Clearly

Across the **four** Java test classes in Sections 13–16:

| Class | Annotated Test Methods | Expected Jupiter Test Invocations |
| --- | ---: | ---: |
| `PriceCalculatorTest` | **3** (2 `@Test`, 1 `@ParameterizedTest`) | **5** (2 + 3 CSV rows) |
| `FileFixtureTest` | **1** `@Test` | **1** |
| `MockitoBoundaryTest` | **2** `@Test` | **2** |
| `SpringBootCompatibilityTest` | **2** `@Test` | **2** |
| **Total** | **8** | **10** |

One parameterized method with three CSV rows is **not three Java methods**, yet it produces three JUnit test invocations. Because none of these methods use `@TestFactory`/dynamic tests or disabled annotations, this is the expected logical invocation count. **Do not label this as "10 tests passed" without running it!** Actual Gradle/XML test reports provide execution proof; tests may be skipped or fail in other environments.

The project intentionally omits `System.out.println`; there is no fixed business stdout contract to promise. Spring startup and JUnit runner logs vary by version and IDE and are not an output contract.

## 18. Verifying Resolved Versions With Gradle Instead of Guessing the BOM

Run with either Option A or B selected:

~~~bash
./gradlew --version
./gradlew dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency junit-jupiter-engine
./gradlew dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency junit-platform-launcher
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --rerun-tasks
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencyInsight --configuration testRuntimeClasspath --dependency junit-jupiter-engine
.\gradlew.bat dependencyInsight --configuration testRuntimeClasspath --dependency junit-platform-launcher
.\gradlew.bat dependencies --configuration testRuntimeClasspath
.\gradlew.bat test --rerun-tasks
~~~

**Read the resolved dependencies**, not just one line in `build.gradle`. A dependency constraint, another imported BOM, a test plugin, or a Gradle platform can shift the actual version away from the default. `dependencyInsight` shows the **selection reason** and the dependency path pulling in the artifact.

Expected:
- Boot **3.5.16**: `junit-jupiter-engine:5.12.2`; `junit-platform-launcher:1.12.2`.
- Boot **4.1.2**: `junit-jupiter-engine:6.0.3`; `junit-platform-launcher:6.0.3`.

**Do not run `java -version` and draw conclusions about resolved JUnit versions**; that only shows the Java runtime version. And **do not check only `compileClasspath`**: Jupiter engine/launcher live on test runtime, so query `testRuntimeClasspath`.

To catch empty test discovery, inspect `build/test-results/test/TEST-*.xml` and `build/reports/tests/test/index.html` after `--rerun-tasks`. If the task reports `NO-SOURCE`/`SKIPPED`, there is no proof that 10 invocations ran.

## 19. A Minimal Maven POM Should Also Let the Boot Parent Manage JUnit

Maven uses `spring-boot-starter-parent` and `spring-boot-starter-test`. A **standalone `pom.xml`** for Boot 3.5.16:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>junit-boot-compatibility-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

To use **Boot 4.1.2** in this core example, create an **alternative `pom.xml`** identical to the above except changing the single `<parent><version>4.1.2</version>` field. **Do not use two Boot parents in the same POM.** The core test code in Sections 10–16 does not depend on Boot 3-specialized test modules, making it a fair comparison baseline.

JUnit 6 requires **Maven Surefire/Failsafe >=3.0.0**; the example pins `3.5.4` to avoid an outdated inherited plugin. The Boot Maven parent may already manage a suitable version, though pinning explicitly in this guide illustrates the JUnit 6 requirement. In a production repo, inspect the Maven effective POM to avoid unnecessarily overriding parent-managed versions.

Do not add a standalone JUnit BOM to a project already using the Spring Boot parent/BOM just to "get the newest version": JUnit documentation recommends relying on Boot dependency management when your project depends on Boot.

## 20. Checking Maven Effective POM and Dependency Tree

~~~bash
mvn -version
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.junit.jupiter,org.junit.platform,org.junit.vintage
mvn -Dtest=PriceCalculatorTest test
mvn test
~~~

The same commands work on Windows PowerShell when Maven is on `PATH`; if the project includes Maven Wrapper, use `./mvnw`/`.\mvnw.cmd` accordingly.

`help:effective-pom` shows plugins/configuration after inheritance; `dependency:tree` shows the dependency versions Maven actually resolves. Do not read `pom.xml` alone and assume `junit-jupiter-api` is 6.x when Maven has another imported BOM or plugin constraint.

**Surefire vs. Failsafe:** Surefire runs unit tests in the `test` phase by default. Failsafe is typically used for integration tests in `integration-test`/`verify` based on configuration and naming; JUnit 6 requires both plugins (if used) to be at least version 3.0.0. Simply adding `maven-failsafe-plugin` to a POM is not enough for it to execute integration tests; you must also configure the appropriate executions.

## 21. When Not Using the Spring Boot BOM: The JUnit BOM Is the Right Choice

For a **plain Java library** not using a Spring Boot parent/dependency-management, use the JUnit BOM to align versions:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform(
        'org.junit:junit-bom:6.0.3'
    )
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

This is a **standalone build snippet for non-Boot applications**, not something to paste into either Spring Boot build. If you need JUnit 5 on a plain Java project, choose the corresponding JUnit 5.x BOM (Platform will be 1.x per the BOM); do not mix a 6.x BOM with Jupiter 5.x artifacts.

JUnit 6 artifact POMs also carry platform alignment info; an explicit BOM makes intent clear. Inside a Spring Boot project, **prefer the Boot BOM**, because Boot validates a complete set of compatible third-party versions. Having two BOMs simultaneously governing JUnit can lead to unexpected Gradle/Maven conflict resolution.

## 22. JUnit Vintage: JUnit 4 Tests Do Not Automatically Become Jupiter Tests

Distinguish the two import styles:

~~~java
// JUnit 4:
import org.junit.Test;

// JUnit Jupiter 5 or 6:
import org.junit.jupiter.api.Test;
~~~

With a legacy JUnit 4 test:

~~~java
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyMathTest {

    @Test
    public void adds() {
        assertEquals(4, 2 + 2);
    }
}
~~~

This is an **illustrative JUnit 4 file**, not part of the main demo's source tree. JUnit Jupiter `@Test` will not automatically discover JUnit 4 annotations without the Vintage engine. In Boot 3.5 and Boot 4.1, add intentionally:

~~~groovy
dependencies {
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'
}
~~~

This is an **addition** to one of the two Gradle builds, not a standalone build. The Vintage version is managed by the Boot BOM: **5.12.2** on Boot 3.5.16, **6.0.3** on Boot 4.1.2. **JUnit Vintage 6 is deprecated**; use it only temporarily in a migration plan rather than treating it as a permanent promise of JUnit 4 support.

Once all tests have moved to Jupiter, delete the `junit:junit`/Vintage dependencies if no longer needed. Verify IDE/Gradle reports did not lose previously executed JUnit 4 tests.

## 23. Example: Migrating JUnit 4 to Jupiter vs. Upgrading Jupiter 5 → 6

JUnit 4:

~~~java
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyServiceTest {
    private GreetingService service;

    @Before
    public void init() {
        service = new GreetingService("Legacy");
    }

    @Test
    public void canGreet() {
        assertEquals("Legacy, An!", service.greet("An"));
    }
}
~~~

Corresponding Jupiter 5 or 6:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ModernServiceTest {
    private GreetingService service;

    @BeforeEach
    void init() {
        service = new GreetingService("Modern");
    }

    @Test
    void canGreet() {
        assertEquals("Modern, An!", service.greet("An"));
    }
}
~~~

Both are **standalone illustrative snippets** in a hypothetical package containing `GreetingService`; do not drop them into the demo project without matching files/packages/imports. What changed here is **JUnit 4 → Jupiter**, not JUnit 5 → JUnit 6. Spring Boot JUnit Jupiter integration typically uses `@SpringBootTest` (which already integrates `SpringExtension`) instead of JUnit 4 `@RunWith(SpringRunner.class)`.

Basic mapping:

| JUnit 4 | Jupiter 5 and 6 |
| --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before` / `@After` | `@BeforeEach` / `@AfterEach` |
| `@BeforeClass` / `@AfterClass` | `@BeforeAll` / `@AfterAll` |
| `@RunWith(SpringRunner.class)` | `SpringExtension` or `@SpringBootTest`/`@SpringJUnitConfig` |
| `@Test(expected=X.class)` | `assertThrows(X.class, () -> ...)` |
| `@Rule TemporaryFolder` | `@TempDir` |
| `@RunWith(Parameterized.class)` | `@ParameterizedTest` and source annotations |
| JUnit 4 categories | Jupiter `@Tag` |

`@BeforeAll` is static by default under Jupiter's `PER_METHOD` lifecycle; under `@TestInstance(PER_CLASS)`, instance methods can be used depending on the API. Do not copy lifecycle/runner assumptions straight from JUnit 4.

## 24. Spring Boot 4 Test Starter Modularization: Errors Are Not Always JUnit 6

Spring Boot 4 splits test infrastructure into technology-specific modules. In Boot 3.5, many libraries for web/data testing came from an umbrella starter; in Boot 4, certain technologies require a **companion test starter**.

| Technology | Boot 4 Main Starter | Appropriate Boot 4 Test Starter |
| --- | --- | --- |
| Core Spring Boot + Jupiter | `spring-boot-starter` | `spring-boot-starter-test` |
| Spring MVC | `spring-boot-starter-webmvc` | `spring-boot-starter-webmvc-test` |
| Spring WebFlux | `spring-boot-starter-webflux` | `spring-boot-starter-webflux-test` |
| Spring Data JPA | `spring-boot-starter-data-jpa` | `spring-boot-starter-data-jpa-test` |
| Spring JDBC | `spring-boot-starter-jdbc` | `spring-boot-starter-jdbc-test` |
| Spring Security | `spring-boot-starter-security` | `spring-boot-starter-security-test` |
| Spring Kafka | `spring-boot-starter-kafka` | `spring-boot-starter-kafka-test` |

These are **Spring Boot 4.1 starter naming patterns**, not a claim that all of them existed in Boot 3.5 or that every test starter is needed for a core app. Specialized test starters pull in core `spring-boot-starter-test` as appropriate.

If `@WebMvcTest` or `@DataJpaTest` fails to compile on Boot 4, check **the new annotation package and the technology test starter**. Do not try to "fix" it by bumping JUnit Jupiter to another version; that is Spring Boot modularization.

### @MockBean and @SpyBean

In Boot **3.4/3.5**, `@MockBean`/`@SpyBean` were deprecated; in Boot **4.0+**, they were **removed**. Use Spring Framework `@MockitoBean`/`@MockitoSpyBean`:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

// Inside a Spring Boot test class:
@MockitoBean
PaymentGateway paymentGateway;
~~~

The snippet above uses `PaymentGateway` as an illustrative type and is not part of the runnable project. If the same code must build on both Boot 3.5 and 4.1, `@MockitoBean` is more compatible because both Spring Framework 6.2 and 7 support it. Distinguish Spring context mock beans from plain Mockito `@Mock` in unit tests.

### Boot 4 @SpringBootTest and Web Testing

The Spring Boot 4 migration guide notes that `@SpringBootTest` no longer provides certain MockMvc/HTTP test client support automatically as before; for `MockMvc`, use `@AutoConfigureMockMvc` with the right test dependencies, and for `TestRestTemplate`/`RestTestClient`, add the companion modules and annotations. That is a **Boot 4 change**, not a JUnit 6 `@Test` breaking change.

## 25. Gradle/JUnit Platform TestEngine: No Tests Executed

A build can compile successfully yet the `test` task reports `NO-SOURCE`, `SKIPPED`, `No tests found`, or 0 tests. Before changing code, check four layers:

~~~text
1) Gradle test source set
   src/test/java / custom src/integrationTest/java
        |
        v
2) Test task configuration
   testClassesDirs / runtime classpath / useJUnitPlatform()
        |
        v
3) JUnit Platform launcher + registered engines
   junit-platform-launcher + junit-jupiter-engine
        |
        v
4) Jupiter discovery + filters
   @org.junit.jupiter.api.Test, --tests, tags, engines
~~~

If `src/test/java` is empty, adding the Jupiter engine creates no tests. If `junit-jupiter-api` is present without the engine, Java tests compile yet Platform has no engine to discover them. If `useJUnitPlatform()` is missing on a custom `Test` task, Gradle may not run Jupiter as expected. If `includeTags("slow")` is configured and no test carries that tag, the task finds zero matching tests.

**Gradle 9:** custom `Test` tasks should explicitly configure `testClassesDirs` and `classpath`; a Gradle 9 runner does not automatically repair a project's JUnit/Boot dependency graph. With Spring Boot 3.5, stick to documented Gradle 8.x versions; Boot 4 can use Gradle 9 after verifying plugins.

## 26. Maven Surefire/Failsafe, IDEs, and Version Drift

JUnit 6 requires Maven Surefire/Failsafe **>=3.0.0**. A 2.x `maven-surefire-plugin` may not understand modern engines/launchers, causing 0 tests or platform/provider mismatches. Even with JUnit Jupiter 5, use the parent-managed plugin version or a compatible modern version; do not cling to an old Surefire version because tests previously "worked in the IDE".

Differences between IDE and CI:

- IDEs may run tests via a bundled JUnit launcher, while Gradle/Maven use project runtime dependencies/configurations.
- Older IntelliJ/Eclipse/VS Code versions may not understand JUnit 6/Platform 6 immediately, especially custom test engines or Kotlin projects.
- The IDE's "Run tests using Gradle" mode helps compare against the same task, yet does not eliminate JDK or environment variable differences.
- The JUnit dependency tree cached in an IDE can go stale if project imports are not refreshed.
- Multi-module CI builds may have differing Gradle/Maven parents/`dependencyManagement`; inspect each module/test configuration.
- Verify actual test discovery counts rather than relying on a green gutter icon on a single method.

**Useful Maven checks:** `mvn -version`, `mvn help:effective-pom`, `mvn dependency:tree`, `mvn -Dtest=... test`. **Useful Gradle checks:** `./gradlew --version`, `dependencyInsight` for Jupiter engine and launcher, `./gradlew test --rerun-tasks`.

## 27. Common Linkage Errors When Mixing JUnit 5 and 6

| Symptom | Possible Origin | Action |
| --- | --- | --- |
| `NoClassDefFoundError` in `org.junit.platform.*` | Missing or mismatched Platform JAR/runtime launcher | Inspect `testRuntimeClasspath`; align BOM |
| `NoSuchMethodError` / `AbstractMethodError` | Extension/engine compiled against a different API version | Find JAR mismatch; upgrade in lockstep |
| `ClassNotFoundException: org.junit.jupiter.api.Test` | Jupiter API missing from test compile classpath | Check `spring-boot-starter-test` scope/test dependency |
| `Cannot create Launcher without at least one TestEngine` | Missing Jupiter/Vintage engine | Add engine via starter or Jupiter aggregate |
| Test classes compile, Gradle discovers nothing | Missing `useJUnitPlatform`, wrong source set, or test filter | Check task/engine/annotations |
| `UnsupportedClassVersionError` | JUnit 6/Boot 4/JDK compiled for newer Java than runtime | Test JVM >= Java 17; check daemon/toolchain |
| `junit-platform-runner` fails to resolve on JUnit 6 | Module was removed | Migrate to launcher/Jupiter; remove runner |
| `MethodOrderer.Alphanumeric` fails to compile | Deprecated API removed in JUnit 6 | Switch ordering strategy |
| `@CsvFileSource(lineSeparator=...)` fails to compile | Attribute removed | Remove attribute; rely on auto-detected line endings |
| JUnit 4 tests do not run | Missing Vintage engine | Add Vintage temporarily or migrate to Jupiter |
| `@MockBean` fails to compile on Boot 4 | Boot API removed | Use `@MockitoBean` |
| `@WebMvcTest` missing on Boot 4 | Different Boot test starter/module/package | Add MVC test starter; update imports |
| `No qualifying bean` after migration | Changed Spring context config/bean scan | Debug Spring Boot context; do not blame JUnit version |
| Mockito extension does not init mocks | Missing `@ExtendWith(MockitoExtension.class)` or dependency mismatch | Use proper Mockito Jupiter extension |
| Mockito inline/ByteBuddy warnings on newer JDK | Mockito/ByteBuddy/agent/JDK compatibility | Use Boot-managed versions; inspect warnings |
| IDE runs tests, CI Maven runs 0 tests | Surefire/Failsafe/provider too old | Upgrade >=3.0.0 for JUnit 6 |
| JUnit report count differs from expected | Parameterized/disabled/dynamic tests or filters | Inspect XML nodes and test discovery |

**Do not equate** every `Failed to load ApplicationContext` with a JUnit 6 bug. When the Spring test extension runs and the context fails due to a datasource, profile, or bean ambiguity, that is a **Spring bootstrap/business infrastructure** error. Read the root cause before touching the BOM.

## 28. A Migration Plan That Will Not Break CI

To migrate a real application from Boot 3.5/JUnit 5 to Boot 4.1/JUnit 6:

1. **Record the baseline:** on your current Boot 3.5 patch, run `./gradlew test`/`mvn test` and save JUnit XML counts and the list of skipped tests.
2. **Verify Java:** ensure production and test JVMs are >=17 and the JDK running Gradle/Maven/plugins is within the supported range.
3. **Audit deprecated APIs:** search for `@MockBean`, `@SpyBean`, `org.junit.platform.runner`, `MethodOrderer.Alphanumeric`, `@CsvFileSource(lineSeparator=...)`, `junit.jupiter.tempdir.scope`, and custom extensions.
4. **Read the Boot 4 migration guide:** package moves, modular test starters, Jackson 3, Spring Framework 7, auto-configuration, and Mockito bean override changes.
5. **Create a migration branch:** update the Spring Boot plugin/parent to the target Boot 4 release; **let the Boot BOM pull in JUnit 6**.
6. **Align build tooling:** Gradle 8.14+ or 9 for Boot 4; Maven 3.6.3+ and Surefire/Failsafe >=3.0.0.
7. **Select test starters:** add technology-specific test starters for MVC/JPA/Security/Kafka/WebFlux/GraphQL as needed; do not add every starter indiscriminately.
8. **Fix deprecated/removed imports and code:** prefer `@MockitoBean`, and update runner/ordering/CSV options if actually used.
9. **Check the resolved tree:** ensure Jupiter/Platform/Vintage share the same major/release train, with no stale engine 5 or Platform 1 on Boot 4.
10. **Run in small groups:** pure unit, Mockito, Spring Boot context, MVC/data slices, then the full suite.
11. **Check CI artifacts:** actual test counts, failures, skipped/disabled counts, XML/HTML paths, Gradle test forks, and Maven Surefire reports.
12. **Verify external integrations:** Testcontainers, embedded Kafka, Spring Security/REST docs, and dependency plugins may require Boot 4-specific versions.
13. **Never hide errors by skipping:** avoid `-x test`, `-DskipTests`, or `ignoreFailures=true` as a migration workaround.
14. **Keep a fallback:** if the Boot 4 migration is not ready, stay on managed Boot 3.5/JUnit 5 and prioritize build reliability over forcing a new major.
15. **Measure performance and isolation:** context cache, mocks, JUnit parallelism, and DB cleanup; JUnit 6 does not magically eliminate state leaks.

Separate **dependency platform upgrade** PRs from **business test refactoring** PRs whenever possible; changing everything at once makes it hard to tell whether failures come from JUnit, Boot, Java, or another framework.

## 29. Test Slices, SpringExtension, and @MockitoBean After Upgrading

**`SpringExtension`** integrates Jupiter with Spring TestContext:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MiniConfig.class)
class SmallSpringTest {
}
~~~

This is an **illustrative snippet** missing `MiniConfig` and imports, so it is not part of the runnable project. `@SpringJUnitConfig(MiniConfig.class)` is usually cleaner. With `@SpringBootTest`, Spring Boot already configures Jupiter/`SpringExtension`; you do not always need to repeat `@ExtendWith(SpringExtension.class)`.

For bean mocks in a Spring context, a typical pattern is:

~~~java
@SpringBootTest
class PartnerServiceTest {
    @MockitoBean
    RemotePartner partner;

    @Test
    void replacesRemoteDependency() {
        // Stub/verify partner according to the contract under test.
    }
}
~~~

This is a **skeleton** without `RemotePartner`/service implementation and is not a runnable test. In Boot 3.5, `@MockitoBean` comes from Spring Framework 6.2; in Boot 4.1, from Spring 7. When multiple tests share a cached `ApplicationContext`, mocks in the context may be reused/reset; avoid running tests sharing the same mock in parallel without isolation.

**Slice APIs:** Boot 4 modularizes packages and test dependencies; a `@WebMvcTest` import from Boot 3 will not stay in the same package in Boot 4. When upgrading Boot, update annotation packages and companion starters per migration docs, and verify the test's primary `@SpringBootApplication` is still discovered. JUnit 6 is not directly responsible for test-slice import relocations.

## 30. Version Overrides: When Are They Justified and What Must You Check?

Not all overrides are forbidden: an organization may need to patch a JUnit/Mockito vulnerability while waiting for a Boot maintenance release. However, an override must be **intentional and backed by evidence**, not a developer's default habit.

Process when truly necessary:

- Identify the specific CVE/bug or required feature, the risk, and the affected test stack scope.
- Compare the effective Boot BOM version against JUnit/Mockito release notes and Spring Framework compatibility.
- With Spring Boot dependency management, use the **appropriate BOM properties** or dependency constraints rather than pinning a single artifact alone.
- Align Jupiter API/engine/params, Platform launcher/engine/commons, and Vintage (if used).
- Run pure unit + `@SpringBootTest` + Mockito + integration/slices on at least your primary JDK/Gradle/Maven CI pipeline.
- Check third-party JUnit Platform custom `TestEngine` implementations and IDE support.
- Document the approved exception and plan to return to the Boot-managed version once Boot updates.
- If an override crosses a major boundary like JUnit 5 → 6 **inside Boot 3.x**, treat it as an **unsupported self-maintained compatibility configuration**, not a recommended upgrade path.

**Do not** add both `org.junit:junit-bom:6.0.3` and the Spring Boot 3.5 BOM and assume engine/launcher/Spring Test will stay consistent. Use `dependencyInsight` or Maven `dependency:tree` to verify every JAR.

## 31. JUnit Vintage 6 Deprecation and the Risk of Forgotten Tests

If a project contains both:

~~~text
LegacyOrderTest.java    import org.junit.Test;          (JUnit 4)
ModernOrderTest.java    import org.junit.jupiter.api.Test; (Jupiter)
~~~

Boot 4.1 `spring-boot-starter-test` provides Jupiter by default, so **never assume JUnit 4 tests run automatically**. Add `junit:junit:4.13.2` and `junit-vintage-engine` in the matching 6.x version if temporarily needed, then inspect reports to confirm each legacy class executes.

Key points when moving from JUnit 5 → 6:
- **Vintage 6 still exists**; JUnit 4 is not banned overnight.
- However, Vintage 6 is **deprecated** and emits an INFO-level discovery notice when JUnit 4 tests are detected, per release notes.
- Do not rely on the old `junit-platform-runner`: that module was removed.
- Migrate JUnit 4 classes to Jupiter in separate PRs while preserving test coverage.
- When removing Vintage, configure CI to fail if compiled JUnit 4 tests remain undiscovered.

Test classes using `@RunWith(SpringRunner.class)` belong to JUnit 4; convert them to Jupiter `@SpringBootTest`/`SpringExtension` per contract. Do not confuse that with changing JUnit 5's `org.junit.jupiter.api.Test` for JUnit 6—that import does not change.

## 32. Test Speed, Parallelism, and Context Caching Are Not Solved by a Version Bump

Adopting JUnit 6 does not automatically eliminate flaky Spring tests. Check:

- JUnit's default `PER_METHOD` test instance lifecycle vs. optional `PER_CLASS`.
- `@Execution(CONCURRENT)`/`@ResourceLock`/`@Isolated` when enabling parallel execution (using the version-appropriate APIs).
- Spring TestContext cached `ApplicationContext` sharing singleton beans and `@MockitoBean` across test classes.
- Spring mock reset lifecycles do not guarantee thread-safety for concurrent tests sharing the same mock.
- `@Transactional` test rollback on the test thread does not automatically roll back HTTP server or `@Async` worker threads.
- Shared H2/Redis/Kafka/DB data requires unique IDs, scoped cleanup, and awaited worker completion.
- `@TempDir` is a test temp-file utility; it does not clean up external databases.
- Gradle test forks and JUnit internal parallel threads operate at different levels.

If tests fail intermittently under parallel execution after migration while passing sequentially, investigate shared mutable state and context/mocks before blaming Jupiter 6. A version upgrade often merely shifts timing and exposes pre-existing race conditions.

## 33. Troubleshooting JUnit 6 in IDEs and CLI

| Scenario | Why It Happens | Check |
| --- | --- | --- |
| IDE Test button passes, Gradle fails | Bundled IDE runner differs from JUnit Platform launcher/runtime deps | Delegate tests to Gradle; inspect `testRuntimeClasspath` |
| Gradle passes, Maven fails | Outdated Surefire/Failsafe or effective POM differs from Gradle | `mvn help:effective-pom`, Surefire >=3.0.0 |
| Build compiles, zero tests run | Missing Jupiter engine/runtime launcher or filter mismatch | `useJUnitPlatform`, dependencies, XML counts |
| Mix of Jupiter 5 and Jupiter 6 | Conflicting imported BOMs/constraints | `dependencyInsight` for every JUnit module |
| Java 11 in CI, Java 17 locally | JUnit 6 bytecode requires Java 17 | Java toolchain/test JVM, pipeline JDK |
| Test class still uses `org.junit.Test` | Remaining JUnit 4 code | Temporary Vintage or migrate |
| `@MockBean` errors on Boot 4 | Removed Spring Boot API | `@MockitoBean` (Spring Test) |
| `@DataJpaTest` import errors on Boot 4 | Test modules split | Matching starter and new import |
| `Failed to load ApplicationContext` | Bean/profile/DB/component-scan issue | Read the root `Caused by` in the Spring context |
| System `gradle` invoked | Wrapper version drift | `./gradlew --version` |
| API present without engine | Jupiter API on compile classpath only | Add proper test runtime Jupiter aggregate/engine |
| `@SpringBootConfiguration` not found | Wrong test package or source layout | App package, `classes=...` |
| Parameterized test display name differs | JUnit 6 CSV display name formatting changes | Assert data/results rather than fragile display names |
| CSV parser treats line endings differently | `lineSeparator` removed; auto-detection used | Use proper UTF-8 fixtures; remove deprecated option |
| Gradle 9 + Boot 3.5 | Spring Boot 3.5 does not support Gradle 9 | Stay on Gradle 8 or upgrade to Boot 4 |
| Old IDE version does not recognize JUnit 6 | IDE runtime integration outdated | Update IDE or delegate to Gradle/Maven |

**Diagnostic order:** (1) Java/Gradle/Maven versions; (2) resolved JUnit artifacts; (3) test engine/task discovery; (4) Spring context sources/beans; (5) Mockito/extensions; (6) domain assertions. Never modify business code before pinpointing the failing layer.

## 34. Dual CI Branches for Boot 3.5 and Boot 4.1: Never Mix Dependencies

If a library or shared codebase genuinely supports both Boot 3.5 and 4.1, run **two independent jobs** with separate Boot BOM/parent versions rather than assembling a single JVM classpath containing **both Spring Boot 3 and 4**.

Logical pipeline example:

~~~text
Job A:
  Java 17 + Gradle 8.14.3
  build.gradle with Boot 3.5.16
  JUnit Jupiter 5.12.2 / Platform 1.12.2
  ./gradlew clean test

Job B:
  Java 17 + Gradle 8.14.3
  build.gradle with Boot 4.1.2
  JUnit Jupiter 6.0.3 / Platform 6.0.3
  ./gradlew clean test

Both:
  inspect JUnit test results/XML
  inspect errors/ignored/skipped
  inspect dependencyInsight and JDK
~~~

The two configurations in Sections 7–8 are **two alternative build files**; do not build a dynamic Gradle matrix by mutating files in a shared workspace across parallel tasks. If using a CI matrix with `-PbootVersion=...`, design the build script with configurable plugin/dependency versions, give each job a clean workspace, and verify plugin markers/dependency management rather than running `sed` on a file shared by two jobs.

For an ordinary service application, there is no need to support two Boot majors simultaneously; focus on the target release and run full CI against it.

## 35. QA Checklist Before Concluding Compatibility

- [ ] What are the exact Spring Boot/plugin/parent versions in use?
- [ ] Were **managed dependency coordinates** checked for the exact patch version?
- [ ] Is Jupiter **5.x** distinguished from Platform **1.x** on Boot 3.5?
- [ ] Are Jupiter/Platform/Vintage aligned on **6.x** on Boot 4.1?
- [ ] Are Jupiter/Platform versions not pinned arbitrarily outside the release train?
- [ ] Does only one Boot BOM/parent govern test dependencies?
- [ ] Is `spring-boot-starter-test` present in test scope?
- [ ] Are JUnit Platform launcher and Jupiter engine present at test runtime?
- [ ] Is `useJUnitPlatform()` called on the Gradle `Test` task?
- [ ] Is Maven Surefire/Failsafe >=3.0.0 when using JUnit 6?
- [ ] Is the test JVM >=17 when using JUnit 6?
- [ ] Does the Gradle Wrapper match the Spring Boot plugin (Boot 3.5: 7.6.4+/8.4+; Boot 4.1: 8.14+/9.x)?
- [ ] Are Jupiter Java imports `org.junit.jupiter.*` preserved intact?
- [ ] Were removed APIs checked, such as `MethodOrderer.Alphanumeric` and `junit-platform-runner`?
- [ ] Were legacy `junit.jupiter.tempdir.scope` and `@CsvFileSource(lineSeparator)` removed?
- [ ] Are `@TempDir`, `@ParameterizedTest`, and `@CsvSource` still imported properly?
- [ ] Do Mockito unit tests use `MockitoExtension` with a compatible Mockito version?
- [ ] Have Boot 4 tests replaced `@MockBean`/`@SpyBean` with `@MockitoBean`/`@MockitoSpyBean`?
- [ ] Do Boot 4 tech-specific tests include their matching `-test` starter?
- [ ] Is Boot 4 test-slice migration kept distinct from Jupiter API migration?
- [ ] Do legacy JUnit 4 tests have explicit Vintage configured or have they migrated to Jupiter?
- [ ] Does `dependencyInsight`/`dependency:tree` confirm the actual resolved versions?
- [ ] Do JUnit XML/test reports show the expected test invocations executed without unintended filtering/skipping?
- [ ] Does the `ApplicationContext` smoke test match the target app/config/profile?
- [ ] Are the CI test JVM/JDK and IDE runner aligned?
- [ ] Are `-x test`, `skipTests`, and `ignoreFailures` avoided rather than masking errors?
- [ ] Are test classes isolated without leaking shared singleton/DB/mock state?
- [ ] Are expected results in READMEs kept distinct from actual build execution results?

## 36. Run Commands and Expected Results for the Sample Project

With **one** of the two `build.gradle` files, Java 17, Gradle Wrapper, and the files from Sections 10–16:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew test --tests "com.example.junitmatrix.PriceCalculatorTest"
./gradlew test --tests "com.example.junitmatrix.FileFixtureTest"
./gradlew test --tests "com.example.junitmatrix.MockitoBoundaryTest"
./gradlew test --tests "com.example.junitmatrix.SpringBootCompatibilityTest"
./gradlew test --rerun-tasks --stacktrace
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.junitmatrix.PriceCalculatorTest"
.\gradlew.bat test --tests "com.example.junitmatrix.FileFixtureTest"
.\gradlew.bat test --tests "com.example.junitmatrix.MockitoBoundaryTest"
.\gradlew.bat test --tests "com.example.junitmatrix.SpringBootCompatibilityTest"
.\gradlew.bat test --rerun-tasks --stacktrace
~~~

**Code and Expected Assertions:**

| Test / Group | Expected if Project Compiles and Runs Properly |
| --- | --- |
| `PriceCalculatorTest.calculatesTenPercentDiscount` | `afterDiscount(1000,10)==900` |
| `PriceCalculatorTest.worksForParameterizedExamples` | 3 CSV cases: 900, 400, 179 |
| `PriceCalculatorTest.rejectsInvalidArguments` | All 3 invalid inputs throw `IllegalArgumentException` |
| `FileFixtureTest.createsUtf8FileInsideTempDirectory` | Writes and reads back `"Hello JUnit"` in UTF-8 |
| `MockitoBoundaryTest.convertsWithTestScopedMock` | Mock multiplier=3, result 600, verifies gateway call |
| `MockitoBoundaryTest.invalidMultiplierIsNotRetried` | Mock multiplier=0, throws `IllegalStateException` |
| `SpringBootCompatibilityTest.loadsAppAndTestProfile` | `JunitMatrixApplication` bean exists, prefix `Integration`, greeting `"Integration, An!"` |
| `SpringBootCompatibilityTest.rejectsBlankInputInManagedBean` | Throws `IllegalArgumentException` when name is blank |
| **Total** | **8 test methods; 10 expected Jupiter invocations** |

With the Maven POM in Section 19, use `mvn test` and `mvn -Dtest=SpringBootCompatibilityTest test` to run the corresponding groups.

**This is expected behavior inferred from source code and API documentation, not actual Gradle/Maven/JUnit execution output.** The sample project requires proper file paths, Gradle Wrapper, and dependencies to run; when executed, logs from Spring Boot/Gradle may vary and counts reflect the active engine/provider. Never claim "10 tests PASS" without an actual report or CI output.

## 37. Conclusion: Choose JUnit Using Your Spring Boot Line's BOM

**Spring Boot 3.5.16 → Jupiter 5.12.2 + Platform 1.12.2. Spring Boot 4.1.2 → Jupiter/Platform 6.0.3.** These are the two managed dependency sets verified in the official documentation. There is no rule saying "because JUnit 6 is newer, pin it immediately in every Boot 3 project."

JUnit 6 preserves `org.junit.jupiter` and most of the JUnit 5 programming model, while raising the Java baseline to 17, unifying Platform/Jupiter/Vintage numbering, and removing several deprecated APIs. When moving Boot 3 → Boot 4, you must also address Spring Framework 7, starter modularization, `@MockBean` removal, Maven/Gradle/IDE test engines, and test source discovery.

**A safe upgrade strategy:** establish a test baseline on Boot 3/JUnit 5 → upgrade Boot 4/BOM together → fix genuinely removed APIs → inspect the dependency tree and actual JUnit XML counts → run unit, Spring, and integration tests. Until you move to Boot 4, stick to Boot 3 BOM-managed JUnit 5 unless you have a compelling reason and full compatibility verification.

### Official References

- [Spring Boot 3.5 — Managed Dependency Coordinates (JUnit Jupiter 5.12.2, Platform 1.12.2)](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.4 — Managed Dependency Coordinates (Jupiter 5.11.4, Platform 1.11.4)](https://docs.spring.io/spring-boot/3.4/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.1 — Managed Dependency Coordinates (Jupiter/Platform 6.0.3)](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4 — Migration Guide, test module split, MockitoBean](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [JUnit 6 — User Guide / Getting Started](https://docs.junit.org/6.0.3/index.html)
- [JUnit 6 — Build Support, Gradle, Maven Surefire, BOM, launcher](https://docs.junit.org/6.0.3/running-tests/build-support.html)
- [JUnit 6 — Release Notes / API removals and Java 17 baseline](https://docs.junit.org/6.0.3/release-notes.html)
- [JUnit — Upgrading to JUnit 6.0 Migration Guide](https://github.com/junit-team/junit-framework/wiki/Upgrading-to-JUnit-6.0)
- [Spring Framework — @MockitoBean / @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Boot 4 — Core Testing](https://docs.spring.io/spring-boot/reference/testing/)
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html)