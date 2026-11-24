# JUnit Jupiter `@Tag`: Grouping Tests by Execution Purpose in Spring Boot

> **Module:** Spring Boot – testing  
> **Track:** JUnit Jupiter  
> **Topic:** `@Tag` and grouping by execution purpose  
> **Goal:** Place tags in the right spots, understand how JUnit Platform filters tests, run specific groups with Gradle or Maven, and design CI schedules suitable for unit, slice, integration, smoke, and end-to-end (E2E) tests.

## 1. What problem does `@Tag` solve?

A Spring Boot project usually contains many tests with different purposes and costs:

- **Unit tests:** verify Java logic within a small scope; typically very fast.
- **Slice tests:** verify a framework slice (such as Spring MVC with `@WebMvcTest` or JPA with `@DataJpaTest`).
- **Integration tests:** verify multiple real beans/layers working together, possibly needing a database or broker.
- **E2E tests:** verify flows from an external entry point of a running system through to observable outcomes.
- **Smoke tests:** a very small set of core behaviors that must work after a build/deploy.
- **Regression tests:** verify past bugs do not recur and critical contracts remain intact.

If you always run **every test** on every code save, the feedback loop can become slow. If you only run a few unit tests, wiring, configuration, or end-to-end failures can easily slip through. **`@Tag` lets you label tests and select which groups to run for a specific execution.**

Example:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("unit")
@Tag("fast")
class PriceCalculationTest {
    @Test
    @Tag("smoke")
    void calculatesBasePrice() {
        // Assertions checking pricing rules.
    }
}
```

This test has **three effective tags**: `unit`, `fast`, `smoke`. You can run it in the unit group, the fast group, or the smoke group. `@Tag` **does not write assertions, does not run tests on its own, does not load a Spring context, does not create transactions, and does not make tests faster**. It only supplies metadata to the discovery/filtering mechanism of JUnit Platform and build tools.

**Distinguish two concepts:** `@Tag("integration")` is an *execution selection label*; `@SpringBootTest` is a *Spring application loading configuration*. Putting `integration` on a unit test does not turn it into an integration test. Conversely, `@SpringBootTest` without a tag is still a context-loading test and may run under default configurations.

## 2. Where are tags placed and how do they take effect?

JUnit Jupiter lets you place `@Tag` on a **test class** or a **test method**, and allows repeating the annotation so one test can belong to multiple groups.

### 2.1. Class-level tags apply to test methods in that class

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("unit")
@Tag("fast")
class GreetingRulesTest {

    @Test
    void defaultGreeting() {
        assertEquals("Hello", "Hel" + "lo");
    }

    @Test
    @Tag("smoke")
    void essentialGreeting() {
        assertEquals(2, 1 + 1);
    }
}
```

The effective tags are:

| Test method | Effective tags |
| --- | --- |
| `defaultGreeting` | `unit`, `fast` |
| `essentialGreeting` | `unit`, `fast`, `smoke` |

Method-level tags **add to** class-level tags rather than replacing them. When filtering solely for `smoke`, only `essentialGreeting` is selected in the class above; when filtering for `fast`, both tests are selected.

`@Tag` follows JUnit Jupiter's inheritance rules: **class-level tags are inherited from superclasses; method-level tags are not inherited the same way**. Avoid relying on complex inheritance hierarchies for grouping; when needed, prefer clear structures and check actual discovery results.

### 2.2. One test can belong to multiple classification dimensions

Tags are not limited to "test type". Independent dimensions can be used:

| Dimension | Example tags | Question it answers |
| --- | --- | --- |
| Test level | `unit`, `slice`, `integration`, `e2e` | What scope of the system is actually being tested? |
| Speed/cost | `fast`, `slow` | Which group suits fast feedback? |
| Execution purpose | `smoke`, `regression`, `release` | When should it run in the development lifecycle? |
| Dependent systems | `db`, `http`, `external` | What kind of resource/infrastructure does the test need? |
| Business area | `catalog`, `checkout`, `auth` | Which feature is being protected? |

For example, an integration test verifying a repository against PostgreSQL might carry `integration`, `db`, `catalog`. An E2E test merely verifying successful user login might carry `e2e`, `smoke`, `auth`.

**Every test does not need every dimension.** Choose a few tags with practical meaning and actual consumers. The more consistent the team's conventions, the easier filter expressions are to understand.

### 2.3. Rules for valid tag names

According to JUnit Platform:

- A tag must not be `null` or blank.
- After trimming, a tag must not contain whitespace or ISO control characters.
- It must not contain characters reserved for filter syntax: `,`, `(`, `)`, `&`, `|`, `!`.
- Concise names such as `fast`, `integration`, `db`, `feature-checkout` are valid examples.
- Tags are case-sensitive: avoid mixing `Fast` and `fast` if you intend the same group.

```java
@Tag("fast")             // Valid
@Tag("checkout-flow")    // Valid
@Tag("slow tests")       // Invalid: contains whitespace
@Tag("unit,smoke")       // Invalid: comma is a reserved character
@Tag("unit")
@Tag("smoke")            // Valid: two separate tags
```

The block above **only illustrates annotation syntax**; it is not a standalone compilable Java file because annotations must be placed on an appropriate class/method.

## 3. JUnit Platform selects tests with tag expressions

JUnit Platform supports filtering via **tag expressions**, using Boolean operators:

| Operator | Meaning | Example |
| --- | --- | --- |
| `!` | Negation | `!e2e`: all tests without the `e2e` tag |
| `&` | AND/intersection | `fast & smoke`: must have both tags |
| `|` | OR/union | `unit | slice`: has at least one tag |
| `( )` | Grouping conditions | `(unit | slice) & !slow` |
| `any()` | Has at least one tag | `any()` |
| `none()` | Has no tags at all | `none()` |

**Precedence:** `!` is highest, then `&`, then `|`. Thus `unit | integration & !slow` is evaluated as `unit | (integration & !slow)`. Always **use parentheses** when an expression mixes operators so readers do not have to guess.

Example using a sample list:

| Test | Tags |
| --- | --- |
| A | `unit`, `fast`, `smoke` |
| B | `unit`, `fast` |
| C | `slice`, `fast` |
| D | `integration`, `db` |
| E | `e2e`, `smoke`, `external` |
| F | no tags |

Results:

| Expression | Selected tests | Reason |
| --- | --- | --- |
| `fast` | A, B, C | Has the fast tag |
| `smoke` | A, E | Both unit and E2E can be smoke tests |
| `fast & smoke` | A | Intersection of both groups |
| `unit | integration` | A, B, D | Union of both groups |
| `smoke & !e2e` | A | Smoke but excluding E2E |
| `!e2e` | A, B, C, D, F | Even untagged tests are selected |
| `none()` | F | Only untagged tests |
| `any()` | A, B, C, D, E | Has at least one tag |

**Note:** Filter expressions decide *which tests are discovered/selected to run*. A test excluded by a filter is not the same as a test marked `@Disabled`. When evaluating CI metrics, distinguish **filtered out**, **skipped by condition**, and **failed**.

## 4. Runnable Spring Boot project: unit, slice, integration, and external E2E

This section is a minimal Gradle Groovy DSL project using **Java 17, Spring Boot 3.5.0, and JUnit Jupiter 5** (test dependency versions managed by the Spring Boot BOM). Tests coexist in `src/test/java` with different tags so they can run on demand.

### 4.1. File structure

```text
tagged-tests-demo/
├── settings.gradle
├── build.gradle
├── gradlew                 # Present if generated with Spring Initializr/Gradle Wrapper
├── gradlew.bat
└── src/
    ├── main/java/com/example/tags/
    │   ├── TaggedTestsApplication.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/java/com/example/tags/
        ├── GreetingServiceTest.java
        ├── GreetingWebSliceTest.java
        ├── GreetingIntegrationTest.java
        └── GreetingExternalE2eTest.java
```

The file snippets below combine into a single project. Use only **one** `build.gradle` file with the given configuration; the `tasks` blocks belong to that same file.

### 4.2. Gradle configuration

```groovy
// settings.gradle
rootProject.name = 'tagged-tests-demo'
```

```groovy
// build.gradle
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

// Regular test run: excludes E2E needing an external server by default.
// -PtagQuery=... lets you select a tag expression for a specific run.
tasks.named('test', Test) {
    useJUnitPlatform {
        def tagQuery = project.findProperty('tagQuery')?.toString()
        if (tagQuery) {
            includeTags tagQuery
        } else {
            excludeTags 'e2e'
        }
    }
}

// Dedicated task for integration tests from the same 'test' source set.
tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Run tests tagged integration'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    shouldRunAfter tasks.named('test')
    useJUnitPlatform {
        includeTags 'integration'
    }
}

// Dedicated task for HTTP E2E tests against a separately started server.
tasks.register('e2eTest', Test) {
    group = 'verification'
    description = 'Run tests tagged e2e against a running application'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    shouldRunAfter tasks.named('test')
    useJUnitPlatform {
        includeTags 'e2e'
    }
}
```

Configuration explanation:

1. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, Mockito, Spring Boot Test, and Spring Test; tests import these APIs at compile time, so `testImplementation` is used.
2. `junit-platform-launcher` is needed by JUnit Platform at runtime, so `testRuntimeOnly` is used. With versions managed by the BOM, you do not need to write version numbers on each dependency.
3. `useJUnitPlatform` tells Gradle to use JUnit Platform to discover and execute Jupiter tests.
4. By default, `test` **excludes `e2e`**, while unit/slice/integration run; when `-PtagQuery=...` is passed, it selects using the given expression instead of the default.
5. `integrationTest` and `e2eTest` are **custom-defined Gradle tasks** reusing the test classes and runtime classpath. They only filter tests by tag; by themselves they do not start DBs, servers, or Docker.
6. Extra registered tasks do not automatically become dependencies of `check` unless you configure `check.dependsOn(...)`. CI can invoke them in the proper stage instead of running everything by default.

**Boundary:** `@Tag` does not create a new source set. In this example all tests still reside in the `test` source set, differing only in how they are selected at run time.

### 4.3. Application production code

```java
// src/main/java/com/example/tags/TaggedTestsApplication.java
package com.example.tags;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaggedTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TaggedTestsApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/tags/GreetingService.java
package com.example.tags;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        return "Hello, " + name.trim() + "!";
    }
}
```

```java
// src/main/java/com/example/tags/GreetingController.java
package com.example.tags;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet/{name}")
    public String greet(@PathVariable String name) {
        return service.greet(name);
    }
}
```

Endpoint `GET /greet/Mai` returns HTTP 200 and body text `Hello, Mai!`. There is no Spring Security or database in this minimal project, so booting with `bootRun` needs no extra setup to test the endpoint.

### 4.4. Unit test tagged `unit`, `fast`, and `smoke`

```java
// src/test/java/com/example/tags/GreetingServiceTest.java
package com.example.tags;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
@Tag("fast")
class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    @Tag("smoke")
    void trimsName() {
        assertEquals("Hello, An!", service.greet("  An  "));
    }

    @Test
    void rejectsBlankName() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.greet("  "));
        assertEquals("Name is required", error.getMessage());
    }
}
```

Here **both tests** have tags `unit` and `fast`, while only `trimsName` also carries `smoke`. There is no `@SpringBootTest` or HTTP request; both tests instantiate the Java class directly. These are unit tests, regardless of which Gradle task invokes them.

### 4.5. MVC slice test tagged `slice` and `fast`

```java
// src/test/java/com/example/tags/GreetingWebSliceTest.java
package com.example.tags;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Tag("slice")
@Tag("fast")
@WebMvcTest(GreetingController.class)
class GreetingWebSliceTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    GreetingService service;

    @Test
    void routesGetRequestAndRendersBody() throws Exception {
        when(service.greet("Mai")).thenReturn("Hello, Mai!");

        mockMvc.perform(get("/greet/Mai"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Mai!"));
    }
}
```

`@WebMvcTest` loads the Spring MVC slice, MockMvc verifies routing and response, and `@MockitoBean` registers a mock service into the Spring context in place of the real service. `@Tag("fast")` is a team **convention** because this test is relatively lightweight; a slice test can still be slow if you add heavy beans or expensive setup.

### 4.6. Integration test tagged `integration`

```java
// src/test/java/com/example/tags/GreetingIntegrationTest.java
package com.example.tags;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Tag("integration")
@Tag("http")
@SpringBootTest
@AutoConfigureMockMvc
class GreetingIntegrationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void controllerAndRealServiceWorkTogether() throws Exception {
        mockMvc.perform(get("/greet/Mai"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Mai!"));
    }
}
```

This test boots the application with the real controller and service to verify wiring, MVC, and coordinated responses. `MockMvc` **does not open an HTTP socket port**; the `http` tag only describes the request/response interface purpose, not proof of real network connectivity. If you need to verify an actual HTTP server, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client.

### 4.7. E2E/API smoke test tagged `e2e`, `smoke`

The test below runs from a Java client outside any Spring context and calls an **already running server**. The `E2E_BASE_URL` variable specifies the target test environment endpoint. A JUnit condition prevents the test from running if the URL is not configured.

```java
// src/test/java/com/example/tags/GreetingExternalE2eTest.java
package com.example.tags;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("e2e")
@Tag("smoke")
@EnabledIfEnvironmentVariable(
        named = "E2E_BASE_URL", matches = "https?://.+")
class GreetingExternalE2eTest {
    @Test
    void runningApplicationRespondsToExternalHttp() throws Exception {
        String base = System.getenv("E2E_BASE_URL")
                .replaceAll("/+$", "");

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(base + "/greet/Mai"))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Mai!", response.body());
    }
}
```

This is **E2E at the REST API boundary** of a running application. If the real system has a reverse proxy, database, authentication, or multiple services, this local test **does not yet prove** components absent from this environment; run against a staging environment matching the target configuration when that scope is needed. `@EnabledIfEnvironmentVariable` is an enable/disable condition, different from `@Tag`: when the URL is absent, the test selected by tag can still be reported as *skipped* by the JUnit condition.

## 5. Running groups with Gradle

Use the Gradle Wrapper inside `tagged-tests-demo`, with JDK 17+ and an environment able to resolve dependencies:

```bash
# Default run: everything except e2e tag (2 unit + 1 slice + 1 integration).
./gradlew test

# Run tests tagged fast (2 unit + 1 slice).
./gradlew test -PtagQuery=fast

# Run exact intersection of fast and smoke (1 unit method).
./gradlew test '-PtagQuery=fast & smoke'

# Run unit or integration, excluding e2e.
./gradlew test '-PtagQuery=(unit | integration) & !e2e'

# Run dedicated integration task (1 integration test).
./gradlew integrationTest

# Select e2e; if E2E_BASE_URL is missing, JUnit will skip it.
./gradlew e2eTest
```

On PowerShell/Windows:

```powershell
.\gradlew.bat test
.\gradlew.bat test -PtagQuery=fast
.\gradlew.bat test "-PtagQuery=fast & smoke"
.\gradlew.bat integrationTest
.\gradlew.bat e2eTest
```

**Running E2E against an external server:** open a first terminal in the project directory:

```bash
./gradlew bootRun
```

Wait for the application to start, then in a second terminal (Bash):

```bash
E2E_BASE_URL=http://localhost:8080 ./gradlew e2eTest
```

Or PowerShell:

```powershell
$env:E2E_BASE_URL = "http://localhost:8080"
.\gradlew.bat e2eTest
Remove-Item Env:E2E_BASE_URL
```

**Expected results** when the sample project and environment work properly:

| Command | Methods selected and executed |
| --- | --- |
| `./gradlew test` | `GreetingServiceTest`: 2; `GreetingWebSliceTest`: 1; `GreetingIntegrationTest`: 1; E2E filtered out |
| `./gradlew test -PtagQuery=fast` | 2 unit + 1 slice = 3 |
| `./gradlew test '-PtagQuery=fast & smoke'` | `GreetingServiceTest.trimsName` = 1 |
| `./gradlew integrationTest` | `GreetingIntegrationTest.controllerAndRealServiceWorkTogether` = 1 |
| `./gradlew e2eTest` with valid URL and server ready | `GreetingExternalE2eTest.runningApplicationRespondsToExternalHttp` = 1 |

Gradle logs, timings, and `UP-TO-DATE` tasks vary by environment. If a task is up-to-date while rechecking selection, try `./gradlew test -PtagQuery=fast --rerun-tasks`. For E2E without a URL, you may see one test *skipped* due to `@EnabledIfEnvironmentVariable`. **Do not equate "not seen in report" with "test passed"**: inspect counts of tests actually selected, executed, and skipped.

### 5.1. Is `--tests` a tag filtering syntax?

No. In Gradle, `--tests` filters by **class/method name pattern**, such as:

```bash
./gradlew test --tests 'com.example.tags.GreetingServiceTest'
```

In this project, `-PtagQuery=...` only works because we **wrote the logic reading that Gradle property** in `build.gradle`. It does not mean every Gradle project understands `-PtagQuery` by default or has a built-in `--include-tags` option. Tag filters and `--tests` are two distinct mechanisms; using both simultaneously makes the selected set the **intersection** of both filters. If no tests match, check both.

### 5.2. Selecting groups when using Kotlin DSL

In `build.gradle.kts`, the equivalent configuration is:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform {
        val tagQuery = providers.gradleProperty("tagQuery").orNull
        if (tagQuery != null && tagQuery.isNotBlank()) {
            includeTags(tagQuery)
        } else {
            excludeTags("e2e")
        }
    }
}
```

This is a **corresponding alternative configuration snippet** for Kotlin DSL builds, not a complete standalone runnable file. `dependencies`, plugins, and source sets are still needed in `build.gradle.kts`. Do not mix Groovy syntax `includeTags 'fast'` into Kotlin DSL; Kotlin requires `includeTags("fast")`.

## 6. Running by tag with Maven Surefire/Failsafe

When a project uses Maven, **do not apply `build.gradle` configuration**. Maven Surefire Plugin supports filtering JUnit 5/Jupiter tags with two properties:

- `groups`: selects tags or tag expressions to **include**.
- `excludedGroups`: selects tags or tag expressions to **exclude**.

Example Surefire plugin configuration in `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.6.1</version>
            <configuration>
                <excludedGroups>e2e</excludedGroups>
            </configuration>
        </plugin>
    </plugins>
</build>
```

The XML block above is **a snippet of `pom.xml`**, assuming the project already has suitable JUnit Jupiter/Spring Boot Test dependencies and compiler plugin. To select other tags via CLI:

```bash
# Only tests tagged fast:
mvn -Dgroups=fast test

# Only tests tagged integration:
mvn -Dgroups=integration test

# Logical combination, wrap the whole argument in shell quotes:
mvn '-Dgroups=(fast | integration) & !e2e' test

# Exclude tests tagged e2e:
mvn -DexcludedGroups=e2e test
```

If `pom.xml` sets `excludedGroups=e2e`, a CLI command specifying `groups=...` **does not automatically erase that exclusion**; effective configuration combines the include and exclude conditions. For example, the `e2e` tag can still be excluded if `excludedGroups` is configured. For certain CI stages, create explicit Maven profiles or reconfigure both sides to avoid hidden filters.

**Surefire/Failsafe and file names:** Surefire typically picks `*Test`/`*Tests` by convention, while Failsafe typically uses `*IT`/`IT*`. `@Tag("integration")` **does not automatically move a class to Failsafe** or change Maven phases. Separating unit/integration between Surefire and Failsafe requires configuring plugins, include/exclude patterns, and lifecycles accordingly; tags are simply **another filtering condition**. Failsafe also supports tag filtering via the JUnit Platform provider when configured appropriately.

## 7. Creating meaningful annotations using meta-annotations

When an entire project repeatedly applies the same tag, you can define your team's own annotation instead of repeating the string `"integration"` everywhere. JUnit Jupiter supports **composed annotations**: custom annotations carrying `@Tag` as a meta-annotation.

```java
// src/test/java/com/example/tags/IntegrationTagged.java
package com.example.tags;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.Tag;

@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@Tag("integration")
public @interface IntegrationTagged {}
```

Usage:

```java
@IntegrationTagged
@SpringBootTest
class PaymentFlowIntegrationTest {
    @Test
    void persistsPayment() {
        // Skeleton example: real tests need assertions + appropriate fixtures.
    }
}
```

The `PaymentFlowIntegrationTest` snippet only **illustrates annotation usage**, not a full functional test or standalone runnable file. `@IntegrationTagged` encapsulates the **label**, while `@SpringBootTest` separately encapsulates **how the Spring context is created**. If you want a test stereotype carrying both, you can build a custom composed annotation combining `@Tag` and `@SpringBootTest`, though you must clearly manage implications for Spring test contexts, inheritance, and test configuration. Avoid hiding heavy system dependencies behind vague annotation names.

## 8. Designing test run groups for CI/CD

A helpful way to organize runs is using multiple stages rather than forcing every test under one label:

| Trigger | Selected group | Purpose |
| --- | --- | --- |
| Developer running locally while editing logic | `fast` or `unit | slice` | Catch regressions quickly |
| Every pull request | `fast`; plus critical integration tests | Feedback fast enough to fix immediately |
| Before merge / on main branch | `integration` and DB/service-related tests | Verify wiring and real dependencies |
| After staging deploy | `smoke & e2e` | Verify minimal end-to-end paths in the environment |
| Nightly / scheduled runs | `regression`, `slow`, broader E2E | Catch issues that take longer to run |
| Before release | `release` plus high-risk tests | Cover critical contracts and journeys |

Example target expressions:

- **Fast local:** `fast & !external`.
- **Catalog business domain:** `catalog & (unit | slice | integration)`.
- **Post-deploy smoke:** `smoke & e2e`.
- **Untagged tests:** `none()`, used to spot tests not yet categorized.

Adoption also depends on execution time, stability, protection value, and codebase size. Do not force every test to carry `smoke` just to inflate smoke counts; smoke tests should protect **core behaviors, kept small enough for early feedback**.

### 8.1. If a test needs external services, are tags enough?

No. `@Tag("db")` is only metadata. For the test to succeed, you still need the database/testcontainer, schema, migrations, seed data, credentials, endpoints, timeouts, and proper cleanup. If CI runs in an environment lacking a database, merely including the `db` tag will cause failures rather than creating a database.

You can combine `@Tag` with:

- `@ActiveProfiles("test")` to select a Spring profile; the two annotations solve **two different concerns**.
- `@Testcontainers` or container lifecycles to start dependencies on demand.
- `@EnabledIfEnvironmentVariable` to conditionally disable tests when the environment is not ready.
- Gradle/Maven/CI configuration to supply URLs, secrets, and appropriate resources.

A tag is a **test selection label**, not a test environment management mechanism.

## 9. Common mistakes

### 9.1. Adding `@Tag` yet all tests still run

Cause: tag filtering was not configured in Gradle/Maven/IDE, or another task without filters is running. **By default, JUnit Platform does not skip a test just because it carries `slow` or `e2e`.** Check the exact task/runner, inspect logs and reports.

### 9.2. Using `@Tag("fast,smoke")` to apply two tags

That is **one invalid tag string** because it contains a comma. Use two annotations `@Tag("fast")` and `@Tag("smoke")`. When filtering multiple tags, use `fast | smoke` or `fast & smoke` depending on the desired logic.

### 9.3. Confusing `@Disabled` with `@Tag("skip")`

`@Disabled` is JUnit's annotation for unconditionally disabling tests (barring other overrides); `@Tag("skip")` has no special effect unless a runner actively excludes it. Do not use a tag named "skip" expecting JUnit to turn off the test automatically.

### 9.4. Believing a test tagged `integration` certainly tests a real database

Tags do not validate real scope. A test using `@MockitoBean` to mock a repository can still run under `@SpringBootTest` without proving any SQL queries. Inspect the actual components and boundaries involved, then choose the right tag.

### 9.5. Using inconsistent tag names

`Integration`, `integration`, `int-test`, and `IT` may be treated as separate tags; filtering for `integration` will not automatically match the others. Establish a standard tag table in the project, standardize lowercase/word-joining style, and avoid unexpected renames.

### 9.6. Using wrong precedence in tag expressions

`unit | integration & !slow` differs from `(unit | integration) & !slow`. The first selects **all unit tests**, including slow ones; the second excludes slow tests from both groups. Use parentheses to communicate intent unmistakably.

### 9.7. Trusting passing count while ignoring filtered/skipped tests

If you only run `fast` and see everything pass, you cannot infer that `integration`/`e2e` also pass. If `e2eTest` is selected while `E2E_BASE_URL` is missing, tests may be skipped; track selected/executed/skipped counts and have CI policies to catch accidentally empty test groups.

### 9.8. Creating too many tags at once

A set of 40 tags with no actual execution lanes only adds maintenance burden. Start with essential dimensions (test level, cost, critical flows), document conventions, and add more only when a concrete filtering need arises.

### 9.9. Confusing `--tests` with tag filtering

Gradle's `--tests` selects tests by class/method name; `@Tag` filters by metadata. Renaming a class or method should not change its semantic tags, and changing tags does not change class names. If a test "disappears", check both tag filters and class name filters.

### 9.10. Treating an unselected test as a failing test

Filtering out a test does not make it fail. CI reporting "0 tests" or "successful with only N tests" must be evaluated against the stage's expectations: smoke groups must not be empty, and critical groups must include their committed cases.

## 10. Hands-on exercises

Using the sample project:

1. Run `./gradlew test -PtagQuery=fast` and note which classes/methods are selected. **Answer:** two methods in `GreetingServiceTest` and one in `GreetingWebSliceTest`.
2. Run `./gradlew test '-PtagQuery=fast & smoke'`. **Answer:** only `GreetingServiceTest.trimsName`.
3. Run `./gradlew integrationTest`. **Answer:** one method in `GreetingIntegrationTest`, using the Spring context and MockMvc.
4. Run `./gradlew e2eTest` without `E2E_BASE_URL`. **Expectation:** the `e2e`-tagged test is selected but disabled/skipped by the JUnit condition; no successful HTTP request is sent.
5. Start `bootRun`, set `E2E_BASE_URL`, then run `e2eTest`. **Expectation:** 1 method executes, receiving 200 and `Hello, Mai!`.
6. Add `@Tag("regression")` to `rejectsBlankName` and run `-PtagQuery=regression`. **Expectation:** only that method is selected (while still inheriting class tags `unit`, `fast`).
7. Add `@Tag("slow")` to class `GreetingServiceTest` and run `-PtagQuery='(unit | slice) & !slow'`. **Expectation:** both unit tests are excluded; only the slice test remains within the expression scope.
8. Try filtering `none()` on the same sample project. **Expectation:** no untagged tests exist, so the selected set is empty; treat this as a signal to check under CI rules, not proof the application is correct.

## 11. Self-assessment checklist

- [ ] Understand that `@Tag` only attaches metadata for JUnit Platform selection; it does not decide how Spring contexts are loaded.
- [ ] Know how to place tags at class/method level, combine multiple tags, and understand that class-level tags apply to methods.
- [ ] Use `!`, `&`, `|`, parentheses, and `any()`/`none()` accurately.
- [ ] Avoid empty tag names, whitespace, or `,()&|!` characters; follow consistent naming conventions.
- [ ] Distinguish filtered-out tests from `@Disabled`/conditionally skipped or failed tests.
- [ ] Know how to configure `useJUnitPlatform { includeTags ...; excludeTags ... }` in Gradle.
- [ ] Know `groups`/`excludedGroups` in Maven Surefire and how Surefire/Failsafe relate to naming conventions.
- [ ] Distinguish `--tests` (class/method names) from filtering via `@Tag`.
- [ ] Can design fast, integration, E2E, and smoke groups suited for local/PR/staging/nightly runs.
- [ ] Verify environments/fixtures and executed test counts; do not treat tags as a substitute for test infrastructure.

## 12. Official references

- [JUnit Jupiter – Writing Tests: Tagging and Filtering](https://docs.junit.org/5.14.1/writing-tests/tagging-and-filtering.html): `@Tag`, tag syntax, and composed annotations (JUnit 5 line).
- [JUnit Platform – Tags and Tag Expressions](https://docs.junit.org/5.14.0/user-guide/index.html): Boolean operators, precedence, and `any()`/`none()`.
- [Gradle – Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, `includeTags`/`excludeTags`, `--tests`.
- [Maven Surefire – Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): filtering JUnit 5 with `groups` and `excludedGroups`.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, `@AutoConfigureMockMvc`.

**Remember:** A test can simultaneously be `unit`, `fast`, and `smoke`, because those three labels answer three different questions. `@Tag` works with **discovery/filtering**; Gradle/Maven decide **which group runs**; Spring annotations and test infrastructure decide **what is actually being verified**.
