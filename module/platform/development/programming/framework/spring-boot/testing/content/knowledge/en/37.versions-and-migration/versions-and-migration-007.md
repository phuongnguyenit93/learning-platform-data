# MockMvcTester, RestTestClient, and Version-Gated APIs

## 1. Why Does a Valid Test on Newer Spring Fail to Compile on an Older Project?

In Spring Boot testing, APIs sometimes look similar yet **live in different versions, modules, packages, and testing layers**. An example from newer Spring Framework docs may use `MockMvcTester` or `RestTestClient`. When copied verbatim into a Spring Boot 3.3.5 project, the Java compiler reports `cannot find symbol` or `package ... does not exist`, even though the project already has `spring-boot-starter-test`. It is not because Mockito or MockMvc is broken; the class **had not yet been released in the Spring Framework version managed by Boot 3.3**.

Questions to distinguish clearly:

- `MockMvc` (Spring MVC Test) has existed across multiple Spring Framework generations, including **6.1**.
- `MockMvcTester` provides AssertJ fluent assertions over `MockMvc` and was introduced in **Spring Framework 6.2**.
- `RestClient` is an application HTTP client introduced in **Spring Framework 6.1**.
- `RestTestClient` is an HTTP client **for testing servers**, modeled on `RestClient`, introduced in **Spring Framework 7.0**.
- `WebTestClient` is an older test client from Spring WebFlux; it is not an earlier name for `RestTestClient`.
- `TestRestTemplate` is another Spring Boot HTTP test utility available in Boot 3.3, whose module and package change in Boot 4.
- Boot 3.3's `@MockBean` vs. Spring Framework 6.2+'s `@MockitoBean` are also version-dependent; do not mix imports from newer samples.

This lesson belongs to **Versions and Migration**, on **"MockMvcTester, RestTestClient, and Version-Gated APIs"**, within **Spring Boot - testing**. The goal is to know **which artifact owns each API, the minimum version required, the right dependencies/annotations, and how to migrate** without breaking the existing test suite.

The primary example uses **Java 17+**. We build the same Greeting Controller and present **three separate configurations/builds**:

1. **Spring Boot 3.3.5** with Spring Framework 6.1: `MockMvc`, `@MockBean`, and `TestRestTemplate`.
2. **Spring Boot 3.5.x** with Spring Framework 6.2: `MockMvcTester` and `@MockitoBean`.
3. **Spring Boot 4.0.x** with Spring Framework 7.0: `RestTestClient`, `@AutoConfigureRestTestClient`, and Boot 4 packages/modules.

**Do not mix test classes from all three branches onto a single project classpath.** Each test file notes its supported version. All counts and report descriptions below are **guidance**, not Gradle outputs executed while authoring this lesson.

## 2. Compatibility Table to Read First

| Spring Boot Line | Boot-Managed Spring Framework | MockMvc | MockMvcTester | RestTestClient | Notes |
| --- | --- | --- | --- | --- | --- |
| **3.3.x** (e.g., 3.3.5) | **6.1.x** | Yes | **Not available** | **Not available** | Boot `@MockBean`; `RestClient` exists |
| **3.4.x** | **6.2.x** | Yes | Yes | **Not available** | Framework `@MockitoBean`; Boot `@MockBean` deprecated |
| **3.5.x** | **6.2.x** | Yes | Yes | **Not available** | `@WebMvcTest` normally auto-configures `MockMvcTester` if AssertJ is on the classpath |
| **4.0.x** | **7.0.x** | Yes | Yes | Yes | `@AutoConfigureRestTestClient`, new Boot test modules and packages |

Rows represent **compatible version lines**, without guaranteeing every patch release shares the exact same minor sub-dependencies. When using the Spring Boot BOM, it manages the matching Spring Framework patch version; inspect the real dependency tree before debugging.

### Four Key Conclusions

1. **You cannot use `RestTestClient` on Boot 3.3 or 3.5 just because `RestClient` exists.** The two classes serve different purposes, and `RestTestClient` does not exist in Spring Framework 6.x.
2. **You cannot use `MockMvcTester` directly on Boot 3.3.5** with Spring Framework 6.1. The safe options are staying on `MockMvc` or upgrading consistently to Boot 3.4/3.5.
3. **You do not need to upgrade to Boot 4 just to use `MockMvcTester`.** That API arrived in Framework 6.2 / Boot 3.4+.
4. **Do not bump `spring-test` alone to 7.x inside Boot 3.3.** Spring Core/Web/Context/Test and the Servlet stack must remain compatible; forcing a single JAR's version easily causes `NoSuchMethodError`/`ClassNotFoundException` at runtime.

### About Documentation Versions

Do not look at a `docs.spring.io/spring-framework/reference/...` URL without a version segment and assume it applies to Boot 3.3. "Current" documentation tracks the latest Spring Framework line. Always select the **6.1**, **6.2**, or **7.0** pages matching your project. Official versioned links are listed at the end of this lesson.

## 3. Two Different Layers: Testing Outbound Clients vs. Inbound Servers

Diagram:

```text
Application A                  Application B (REST server)
   |
   |  Production HTTP client
   |  RestClient / WebClient / RestTemplate
   +------------------------------------------> API B
                                                   |
              Testing server application B         |
              MockMvc / MockMvcTester /             |
              RestTestClient / WebTestClient         |
                                                   v
                                            Controller, MVC,
                                            Filters, Advice

              Testing outbound client A:
              MockRestServiceServer / MockWebServer
```

- `RestClient` executes outbound HTTP requests **sent by the application**.
- `MockRestServiceServer` simulates a **remote HTTP server for outbound `RestClient`/`RestTemplate`** via a mock request factory.
- `MockMvc` and `MockMvcTester` test **Spring MVC controllers** without opening an HTTP listening port.
- `RestTestClient` tests **server endpoints** with a fluent API; it can bind to **`MockMvc`** (no real port) or to a **live HTTP server**.
- `WebTestClient` serves WebFlux or can bind to MVC/live servers with matching dependencies/setup; it predates `RestTestClient`.

**Wrong tool for the job:** test code calling `RestClient.builder()` and then trying to invoke `expectStatus().isOk()` like `RestTestClient`; assertion methods do not exist on production `RestClient`. With `RestClient`, you receive a response or exception and assert it yourself. With `RestTestClient`, you get `exchange().expectStatus()` and `expectBody(...)`.

## 4. Imports to Remember by Generation

| API | Boot 3.3 / Framework 6.1 | Boot 3.5 / Framework 6.2 | Boot 4 / Framework 7 |
| --- | --- | --- | --- |
| `MockMvc` | `org.springframework.test.web.servlet.MockMvc` | Unchanged | Unchanged |
| `MockMvcTester` | Does not exist yet | `org.springframework.test.web.servlet.assertj.MockMvcTester` | Same class |
| `RestTestClient` | Does not exist yet | Does not exist yet | `org.springframework.test.web.servlet.client.RestTestClient` |
| `@WebMvcTest` | `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest` | Old package still used | `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` |
| `@AutoConfigureMockMvc` | `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` | Old package still used | `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc` |
| `@MockBean` | `org.springframework.boot.test.mock.mockito.MockBean` | Legacy Boot annotation deprecated | Do not use legacy Boot annotation |
| `@MockitoBean` | Not in Framework 6.1 | `org.springframework.test.context.bean.override.mockito.MockitoBean` | Same Spring Test annotation |
| `@AutoConfigureRestTestClient` | Does not exist yet | Does not exist yet | `org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient` |
| `@SpringBootTest` | `org.springframework.boot.test.context.SpringBootTest` | Unchanged | Unchanged |
| `TestRestTemplate` | `org.springframework.boot.test.web.client.TestRestTemplate` | Unchanged | `org.springframework.boot.resttestclient.TestRestTemplate` |

**Note:** this table guides import selection during migration; never place both `WebMvcTest` imports in the same Java file. Spring Boot 4 splits modules and auto-configuration packages by feature, so an import valid in Boot 3.5 often needs updating when moving to 4.0.

## 5. Finding the Exact Dependency Managing an API

In Gradle (run in the module containing the tests):

```bash
./gradlew dependencyInsight \
  --dependency spring-test \
  --configuration testRuntimeClasspath

./gradlew dependencyInsight \
  --dependency spring-webmvc \
  --configuration testRuntimeClasspath

./gradlew dependencies \
  --configuration testRuntimeClasspath
```

These commands reveal the **actual resolved version**, the selection reason, and dependency constraints rather than guessing from another module's `build.gradle`. In multi-module builds, use `:module-name:dependencyInsight` and inspect the relevant test task/source set.

Maven equivalents:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
```

If test compilation fails, inspect **`testCompileClasspath`** as well. A JAR on the test runtime classpath is not guaranteed to be on the compile classpath, or vice versa.

### Typical Java Compiler Symptoms

```text
error: cannot find symbol
  symbol: class MockMvcTester

error: package org.springframework.test.web.servlet.client
  does not exist

error: cannot find symbol
  symbol: class MockitoBean
```

These are **illustrative message shapes**, not stdout from an executed build. Verify the class/package exists in the `spring-test` artifact of your active branch. If Gradle's cache is stale, refresh dependencies per team workflow; **do not** add the new import and disable the test.

## 6. Example Structure Rule: Three Separate Projects or Three Git Branches

So a single README does not mix incompatible code in one source set, you can:

- Create **three standalone directories**: `boot33-mockmvc/`, `boot35-mockmvctester/`, `boot40-resttestclient/`. Each directory has its own `settings.gradle` and `build.gradle`.
- Or use **three Git branches** with the same application package, each picking one Boot/Gradle/dependency version and its own test files.
- Or use a Gradle multi-project with independent subprojects; **do not** force all subprojects onto one Spring BOM if you want to run all 3 versions.

In this lesson, the production Java files are identical across all three branches and are listed **once** in Sections 8–11. Each branch has its own **`build.gradle` and test classes**, so copy the shared sources into **the branch project you are testing**.

```text
boot33-mockmvc/
  settings.gradle
  build.gradle
  src/main/java/com/example/compat/
    GreetingApplication.java
    GreetingMessage.java
    GreetingService.java
    GreetingController.java
  src/test/java/com/example/compat/
    GreetingController33SliceTest.java
    GreetingController33HttpTest.java

boot35-mockmvctester/
  settings.gradle
  build.gradle
  src/main/java/com/example/compat/
    (same four application files as the 3.3 branch)
  src/test/java/com/example/compat/
    GreetingController35SliceTest.java

boot40-resttestclient/
  settings.gradle
  build.gradle
  src/main/java/com/example/compat/
    (same four application files as the 3.3 branch)
  src/test/java/com/example/compat/
    GreetingController40SliceTest.java
    GreetingController40HttpTest.java
    GreetingController40StandaloneTest.java
```

This is a structural description, **not** an instruction to create these files in the current repository. Knowledge lessons store code for learners to practice locally; workers do not modify a live application repo or run Gradle here.

## 7. Common `settings.gradle` Setup and Java 17 Rules

Each branch uses a `settings.gradle` with a distinct project name:

**boot33-mockmvc/settings.gradle**:

```groovy
rootProject.name = 'boot33-mockmvc'
```

**boot35-mockmvctester/settings.gradle**:

```groovy
rootProject.name = 'boot35-mockmvctester'
```

**boot40-resttestclient/settings.gradle**:

```groovy
rootProject.name = 'boot40-resttestclient'
```

All three use a Java 17 toolchain. Boot 4.0 keeps Java 17 as its baseline and requires **Gradle 8.14+ or 9.x** per Boot 4.0 requirements. Do not expect Gradle 8.5/8.8 from a Boot 3.3 project to automatically run the 4.0 Gradle plugin.

### Gradle Wrapper

If `gradlew`/`gradlew.bat` is missing, `./gradlew test` will not run. Use `gradle test` with a compatible installed Gradle or generate the Wrapper at the right version. When upgrading Boot majors, update `gradle/wrapper/gradle-wrapper.properties` and check plugins/Java toolchains before concluding a test class is missing.

## 8. Shared Java File: GreetingApplication.java

`src/main/java/com/example/compat/GreetingApplication.java`:

```java
package com.example.compat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }
}
```

This class is the entry point, whose parent package encompasses the other Spring components. `@WebMvcTest` restricts the slice to MVC, whereas `@SpringBootTest` loads the broader application context. Both find `@SpringBootApplication` via the package hierarchy.

## 9. Shared Java Record: GreetingMessage.java

`src/main/java/com/example/compat/GreetingMessage.java`:

```java
package com.example.compat;

public record GreetingMessage(String message) {
}
```

Java 17 records support JSON serialization when Jackson message converters are present. JSON tests verify the `message` field instead of relying on key ordering, whitespace, or formatting quirks.

Never use a dummy JSON `record` alone to claim an MVC controller is tested: actually invoke the endpoint via `MockMvc`, `MockMvcTester`, or `RestTestClient`.

## 10. Shared Java Service: GreetingService.java

`src/main/java/com/example/compat/GreetingService.java`:

```java
package com.example.compat;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public GreetingMessage greeting(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        return new GreetingMessage("Hello " + name);
    }
}
```

Because the service makes no DB or external HTTP calls, full HTTP tests can use the real bean. MVC slice tests use `@MockBean`/`@MockitoBean` to focus strictly on controller request mapping, status codes, and response bodies.

**Note:** there is no `@RestControllerAdvice` mapping `IllegalArgumentException` to HTTP 400 in this project. Do not add a test expecting 400 for a blank input and assume Spring Boot automatically converts every `IllegalArgumentException` into Bad Request. That is a separate contract that must be explicitly designed.

## 11. Shared Controller: GreetingController.java

`src/main/java/com/example/compat/GreetingController.java`:

```java
package com.example.compat;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(
            path = "/api/hello/{name}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello(@PathVariable String name) {
        return greetingService.greeting(name).message();
    }

    @GetMapping(
            path = "/api/greetings/{name}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingMessage json(@PathVariable String name) {
        return greetingService.greeting(name);
    }

    @GetMapping(
            path = "/api/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
```

Constructor injection makes mocking the service straightforward. The controller exposes three endpoints:
- `GET /api/hello/Ada` returns text `Hello Ada`;
- `GET /api/greetings/Ada` returns a JSON object with `message="Hello Ada"`;
- `GET /api/ping` returns text `pong`.

For JSON, tests should avoid comparing raw serialized byte formatting unless byte-level equivalence is required; use JsonPath or DTO decoding.

## 12. Branch A — Spring Boot 3.3.5: build.gradle

**Only for `boot33-mockmvc`**:

```groovy
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Rationale:
- `spring-boot-starter-web` provides Spring MVC, the embedded Servlet server, and JSON converters.
- `spring-boot-starter-test` provides Spring Test, JUnit Jupiter, AssertJ, Mockito, and JsonPath/Hamcrest.
- `spring-boot-test-autoconfigure` comes via `starter-test` for `@WebMvcTest` and `@AutoConfigureMockMvc`.
- `MockMvc` works with Spring Framework 6.1 in Boot 3.3.
- **Neither `MockMvcTester` nor `RestTestClient` exists** in Spring Test 6.1, so do not import them.

## 13. Boot 3.3: MVC Slice Test With MockMvc and @MockBean

`boot33-mockmvc/src/test/java/com/example/compat/GreetingController33SliceTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingController33SliceTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    GreetingService service;

    @Test
    void textResponseUsesExpectedMapping() throws Exception {
        when(service.greeting("Ada"))
                .thenReturn(new GreetingMessage("Hello Ada"));

        mvc.perform(get("/api/hello/Ada")
                        .accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello Ada"));

        verify(service).greeting("Ada");
    }

    @Test
    void jsonResponseHasMessageField() throws Exception {
        when(service.greeting("Lin"))
                .thenReturn(new GreetingMessage("Hello Lin"));

        mvc.perform(get("/api/greetings/Lin")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message")
                        .value("Hello Lin"));

        verify(service).greeting("Lin");
    }

    @Test
    void missingPathReturnsNotFound() throws Exception {
        mvc.perform(get("/api/not-defined"))
                .andExpect(status().isNotFound());
    }
}
```

These are **3 `@Test` methods** for the 3.3 slice branch.

### Explanation

`@WebMvcTest(GreetingController.class)` loads only the MVC slice. `GreetingService` is a `@Service` and is **not automatically scanned** into the slice; without a mock/bean, the context fails due to a missing constructor dependency. Boot 3.3's `@MockBean` creates or replaces a bean of matching type/name in the `ApplicationContext`.

`@Autowired MockMvc` simulates server-side request handling using mock Servlet requests/responses. **There is no HTTP listening port**; thus the test does not verify TCP/TLS/proxies or a real embedded server. It verifies request mapping, content negotiation, serialization, controller logic, and any filters included in the slice.

### Assert Behavior, Not Just Compilation

- Status 200 is one assertion.
- Plain-text body vs. JSON `$.message` are two distinct contracts.
- `verify(service).greeting("Ada")` proves the controller invoked the mocked collaborator.
- The 404 nonexistent-route test needs no service stub; adding an unused stub there can trigger strict-stubbing failures depending on Mockito policy and adds no value to testing routing.

**Do not copy `MockMvcTester` code into this file.** An import missing from the classpath fails `compileTestJava` before JUnit even runs.

## 14. Boot 3.3: Testing a Real HTTP Server With TestRestTemplate

`boot33-mockmvc/src/test/java/com/example/compat/GreetingController33HttpTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingController33HttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void realHttpTextResponseIsOk() {
        ResponseEntity<String> response =
                http.getForEntity(
                        "/api/hello/Ada", String.class);

        assertEquals(HttpStatus.OK,
                response.getStatusCode());
        assertEquals("Hello Ada",
                response.getBody());
    }

    @Test
    void realHttpJsonResponseIsDecoded() {
        ResponseEntity<GreetingMessage> response =
                http.getForEntity(
                        "/api/greetings/Lin",
                        GreetingMessage.class);

        assertEquals(HttpStatus.OK,
                response.getStatusCode());
        assertEquals(
                new GreetingMessage("Hello Lin"),
                response.getBody());
    }
}
```

These are **2 additional `@Test` methods** in Boot 3.3. `RANDOM_PORT` starts an embedded Servlet HTTP server on an OS-assigned port; Boot's auto-configured `TestRestTemplate` resolves relative URLs against that server.

### TestRestTemplate Is Not RestTestClient

`TestRestTemplate` wraps `RestTemplate` with test conveniences; notably, it **does not throw automatically** on HTTP 4xx/5xx responses like typical production clients, allowing assertions via `ResponseEntity.getStatusCode()`.

`RestTestClient` does not exist in Boot 3.3. If you want a fluent `exchange().expectStatus()` API on Boot 3.3, you can consider `WebTestClient` with matching dependencies/config (or stick with `MockMvc`/`TestRestTemplate`). Never **swap imports hoping the compiler will find the newer class**.

### Random Port and Transactions

When a test sends real HTTP requests, client and server run on separate threads/transactions. `@Transactional` on the test method **does not roll back** server-side commits if the controller/service writes to a database. This is a critical distinction between `MockMvc` tests and live server tests when designing cleanup.

## 15. Run Commands and Verifiable Results for Boot 3.3

Inside the `boot33-mockmvc` directory:

```bash
./gradlew clean test
./gradlew test --tests 'com.example.compat.GreetingController33SliceTest'
./gradlew test --tests 'com.example.compat.GreetingController33HttpTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

If the directory has no Wrapper yet, use `gradle clean test` with a compatible installed Gradle or generate a Wrapper per team standards.

**Branch A defines 5 `@Test` methods** (3 slice + 2 live HTTP). No actual PASS numbers are claimed since Gradle was not executed here. Check reports at `build/reports/tests/test/index.html` and `build/test-results/test/` after running.

## 16. Branch B — Spring Boot 3.5.x: Why MockMvcTester Exists

Spring Framework **6.2** introduced `org.springframework.test.web.servlet.assertj.MockMvcTester`. It builds on `MockMvc` infrastructure while offering an AssertJ fluent API to send requests, inspect results, and chain assertions like:

```java
assertThat(mvc.get().uri("/api/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

Compared to traditional `MockMvc.perform(...).andExpect(...)`, this approach:
- Composes smoothly with other AssertJ assertions in the same test.
- Provides `bodyJson()` for comparing JSON and JsonPath values.
- Includes assertions for requests, responses, and exceptions.
- Handles async results differently from raw `MockMvc`; you still must understand its contracts and timeouts.
- **Does not open a real HTTP port just because you called `MockMvcTester`**—it remains a server simulation over mock Servlet objects.

**Why use Boot 3.5 in the example?** This branch manages Framework 6.2. Boot 3.4 also includes the API, while 3.5 documentation presents clear `@WebMvcTest` + `@MockitoBean` + `MockMvcTester` patterns suitable as a migration reference.

## 17. Boot 3.5: build.gradle and Dependency Choices

**Only for `boot35-mockmvctester`**:

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Version 3.5.16 is an example patch in the 3.5 line**, not necessarily the latest patch in every future environment. When picking another patch, let the Boot BOM manage the Spring Framework version.

Do not add `org.springframework:spring-test:7.0.0` manually to "unlock `RestTestClient`" inside a 3.5 project. Spring Framework 7 is a different major upgrade involving the Servlet/Jakarta stack and Spring Boot 4.

### Conditions for Auto-Configuring MockMvcTester

- `spring-test` containing `MockMvcTester` (Framework 6.2+) is present.
- AssertJ from `spring-boot-starter-test` is on the test classpath.
- The test loads an MVC slice via `@WebMvcTest`, or `@SpringBootTest` combined with `@AutoConfigureMockMvc`.
- The test injects `MockMvcTester` directly rather than defining a competing custom bean that drops MVC filters/converters.

In a plain Java project using `spring-test` without Boot test auto-configuration, create one manually with `MockMvcTester.of(controller)` or `MockMvcTester.from(WebApplicationContext)`; **do not expect an `@Autowired` bean** outside a Spring Boot test setup.

## 18. Boot 3.5: MockMvcTester With @MockitoBean

`boot35-mockmvctester/src/test/java/com/example/compat/GreetingController35SliceTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebMvcTest(GreetingController.class)
class GreetingController35SliceTest {

    @Autowired
    MockMvcTester mvc;

    @MockitoBean
    GreetingService service;

    @Test
    void plainTextWithAssertJFluentApi() {
        when(service.greeting("Ada"))
                .thenReturn(new GreetingMessage("Hello Ada"));

        assertThat(mvc.get().uri("/api/hello/Ada")
                        .accept(MediaType.TEXT_PLAIN))
                .hasStatusOk()
                .hasBodyTextEqualTo("Hello Ada");

        verify(service).greeting("Ada");
    }

    @Test
    void jsonPathFromResponseBody() {
        when(service.greeting("Lin"))
                .thenReturn(new GreetingMessage("Hello Lin"));

        assertThat(mvc.get().uri("/api/greetings/Lin")
                        .accept(MediaType.APPLICATION_JSON))
                .hasStatusOk()
                .hasContentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .bodyJson()
                .extractingPath("$.message")
                .asString()
                .isEqualTo("Hello Lin");

        verify(service).greeting("Lin");
    }

    @Test
    void unknownRouteIsNotFound() {
        assertThat(mvc.get().uri("/api/not-defined"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
```

There are **3 `@Test` methods** in Branch B. `MockMvcTester` lives in `org.springframework.test.web.servlet.assertj`. On Boot 3.5, `@WebMvcTest` still uses `org.springframework.boot.test.autoconfigure.web.servlet`; on Boot 4, the Boot slice package changes.

### Why `.asString()` After JSONPath?

`bodyJson().extractingPath("$.message")` returns an assertion target representing the JSON value; `asString()` narrows it to a string assertion. Alternatively, `assertThat(...).bodyJson().isLenientlyEqualTo(...)` compares JSON against a fixture; avoid using `hasBodyTextEqualTo` on JSON just to check one field, since raw JSON spacing can change.

### Notes on `@MockitoBean`

Spring Framework 6.2 provides `@MockitoBean` through Spring Test's bean override infrastructure, replacing the controller's collaborator inside the context slice. Boot's legacy `@MockBean` is deprecated in 3.4+, so when moving to 3.5 you can migrate incrementally to `@MockitoBean`. Never swap the annotation while ignoring differences in bean naming, qualifiers, context caching, and override strategies.

## 19. MockMvcTester.of and MockMvcTester.from: Standalone vs. Full Context?

Also in Framework 6.2, instead of Spring Boot auto-injection, you can build one manually:

```java
GreetingController controller =
        new GreetingController(new GreetingService());

MockMvcTester tester =
        MockMvcTester.of(controller);

assertThat(tester.get().uri("/api/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

**This is a snippet**, not an extra test file in Project B. It requires `MockMvcTester`, AssertJ `assertThat`, and controller/service imports. `of(controller)` uses standalone MockMvc setup, ideal for quick tests yet **it does not automatically load** global controller advice, security filters, or custom converters from the production app.

When you need infrastructure/config from a Spring `WebApplicationContext`:

```java
MockMvcTester tester =
        MockMvcTester.from(webApplicationContext);
```

This snippet requires a `WebApplicationContext webApplicationContext` created by Spring TestContext. It uses the MVC application context, closer to real configuration, while still not opening a TCP port.

## 20. MockMvcTester and Unhandled Exceptions

With `MockMvc.perform(...)`, an exception unhandled by a controller or advice can propagate out of `perform`; with `MockMvcTester`, the AssertJ result captures it so you can assert the failure. Per Spring 6.2 docs, assertions such as `hasFailed()`/`failure()` inspect exceptions, while `hasStatus(...)` applies to completed responses.

Do not assume a `RuntimeException` thrown by a controller automatically becomes HTTP 500 with a JSON `ProblemDetail`. Producing a consistent status/body requires `@ExceptionHandler`/`@RestControllerAdvice` or configured framework error handling. **The difference between an unresolved exception and an HTTP 500 response is part of the contract test.**

### Async Requests

`MockMvcTester.exchange()` waits for async processing to finish within its configured timeout, unlike raw `MockMvc` which often requires `asyncDispatch(...)`. However, "waiting" here does not mean every fire-and-forget `@Async` job or event started by a controller has finished. Always test the real completion boundary of the operation rather than using fixed sleeps in CI.

## 21. Branch C — Spring Boot 4.0.x: RestTestClient From Framework 7.0

Spring Framework **7.0** adds `org.springframework.test.web.servlet.client.RestTestClient` to `spring-test`. Unlike `MockMvcTester`, which wraps MockMvc/AssertJ, `RestTestClient` models its fluent request API after blocking `RestClient` up to `exchange()`, then chains into `expectStatus()`, `expectHeader()`, and `expectBody(...)`.

Key setup modes:

| Factory | TCP Server Running? | Test Scope |
| --- | --- | --- |
| `RestTestClient.bindToController(controller)` | No | Standalone MVC controller |
| `RestTestClient.bindToApplicationContext(context)` | No | MVC context via MockMvc |
| `RestTestClient.bindToRouterFunction(router)` | No | Spring MVC functional routes |
| `RestTestClient.bindToServer().baseUrl(url)` | Yes | Running HTTP server |
| Boot `@AutoConfigureRestTestClient` + `@WebMvcTest` | No | MVC slice bound to MockMvc |
| Boot `@AutoConfigureRestTestClient` + `@SpringBootTest(RANDOM_PORT)` | Yes | Live embedded server |

**One API, two connection modes.** When reading a test, check whether it binds to a controller/context or a real server. An `expectStatus().isOk()` assertion alone does not tell you TCP was exercised.

### RestTestClient Is Not RestClient

`RestClient` is the application HTTP client with `retrieve().body(...)` and `exchange(...)` callbacks. `RestTestClient` is a server-testing facade/wrapper exposing expectations after `exchange()`. Do not rename a variable and try calling test-only assertion methods on `RestClient`.

## 22. Boot 4: build.gradle and Feature-Split Modules

**Only for `boot40-resttestclient`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.9'
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
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-resttestclient'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

### Why Does It Differ From Boot 3.3/3.5?

Spring Boot 4 splits many auto-configuration and test modules by feature:

- `spring-boot-starter-webmvc` is the recommended Web MVC starter replacing legacy `spring-boot-starter-web`.
- `spring-boot-starter-webmvc-test` supports Spring MVC tests and `@WebMvcTest` in Boot 4.
- `spring-boot-starter-test` holds general test libraries.
- `spring-boot-resttestclient` is declared explicitly in this example to provide Boot's `@AutoConfigureRestTestClient` and customizers; the project also gets `spring-test`/`RestTestClient` from Framework 7 through the related dependencies.
- Do not add `spring-boot-starter-webflux` just because the test API name resembles `WebTestClient`. Those are different stacks.

**Build requirements:** Java 17+, Gradle **8.14+ or 9.x**, and Jakarta Servlet APIs compatible with Boot 4/Spring 7. If a build uses Gradle 8.7, upgrade the Wrapper first. All patch upgrades must follow the Boot BOM and release notes.

### Why Not Copy `boot33/build.gradle` and Just Bump the Version?

Boot 4 changes many module names and annotation packages. A legacy artifact may linger as a deprecated alias in one patch, yet new tests should not rely on it. A migration should update **plugins, starters, testing modules, and imports** across the 4.0 line together.

## 23. Boot 4: @WebMvcTest + @AutoConfigureRestTestClient

`boot40-resttestclient/src/test/java/com/example/compat/GreetingController40SliceTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.client.RestTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebMvcTest(GreetingController.class)
@AutoConfigureRestTestClient
class GreetingController40SliceTest {

    @Autowired
    RestTestClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void mvcSliceTextWithoutListeningPort() {
        when(service.greeting("Ada"))
                .thenReturn(new GreetingMessage("Hello Ada"));

        client.get()
                .uri("/api/hello/Ada")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello Ada");

        verify(service).greeting("Ada");
    }

    @Test
    void mvcSliceJsonPath() {
        when(service.greeting("Lin"))
                .thenReturn(new GreetingMessage("Hello Lin"));

        client.get()
                .uri("/api/greetings/Lin")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello Lin");

        verify(service).greeting("Lin");
    }

    @Test
    void mvcSliceUnknownRoute() {
        client.get()
                .uri("/api/not-defined")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody();
    }
}
```

There are **3 `@Test` methods** in the Boot 4 slice.

### No Real Network Port

`@WebMvcTest` configures the MVC slice and `MockMvc` infrastructure. `@AutoConfigureRestTestClient` provides an autowirable `RestTestClient` bound to that context's `MockMvc`. Even though the code looks like an HTTP REST client, requests never cross a TCP socket. It remains a controller test, not a live HTTP end-to-end test.

### Why `@MockitoBean` Instead of `@MockBean`?

`GreetingService` is not created automatically by the MVC slice. Spring Framework 7 supports `@MockitoBean` via Spring Test. In Boot 4, do not copy Boot 3.3's `org.springframework.boot.test.mock.mockito.MockBean` into new tests; that legacy Boot package is not supported in Boot 4.

### JSON Body With `expectBody().jsonPath`

`expectBody().jsonPath("$.message").isEqualTo("Hello Lin")` asserts a JSON field without depending on whitespace or key ordering. `expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)` checks the MIME type without requiring an exact charset parameter, fitting JSON responses well.

## 24. Boot 4: Full HTTP Server With `@SpringBootTest(RANDOM_PORT)`

`boot40-resttestclient/src/test/java/com/example/compat/GreetingController40HttpTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient
class GreetingController40HttpTest {

    @Autowired
    RestTestClient client;

    @Test
    void liveHttpTextEndpoint() {
        client.get()
                .uri("/api/hello/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello Ada");
    }

    @Test
    void liveHttpJsonEndpoint() {
        client.get()
                .uri("/api/greetings/Lin")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello Lin");
    }
}
```

There are **2 `@Test` methods** in the Boot 4 live HTTP class.

`@SpringBootTest(RANDOM_PORT)` starts a real server; Boot 4 `@AutoConfigureRestTestClient` automatically points relative URLs at the embedded server running on that random port. Never hardcode `localhost:8080` or test against a production URL.

### Real HTTP vs. MockMvc

A full HTTP test exercises sockets, the embedded server connector, request serialization, and full application runtime configuration. It catches networking, filter, and container configuration bugs that mock MVC tests miss. The trade-offs are slower startup and different transaction boundaries.

**Do not conclude from status/body assertions that production TLS, real proxies, or distributed deployments were tested.** An embedded localhost server is one integration tier, not production-infrastructure E2E.

## 25. Boot 4: Using RestTestClient Directly Without a Spring Boot Context

`boot40-resttestclient/src/test/java/com/example/compat/GreetingController40StandaloneTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

class GreetingController40StandaloneTest {

    private RestTestClient newClient() {
        GreetingController controller =
                new GreetingController(new GreetingService());

        return RestTestClient.bindToController(controller)
                .build();
    }

    @Test
    void standaloneControllerText() {
        newClient().get()
                .uri("/api/hello/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello Ada");
    }

    @Test
    void standaloneControllerJson() {
        newClient().get()
                .uri("/api/greetings/Lin")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello Lin");
    }
}
```

There are **2 `@Test` methods** in the standalone class. `RestTestClient.bindToController` is a Spring Framework API: no `@AutoConfigureRestTestClient` annotation is needed because the client is built directly. Spring MVC mock infrastructure must still be on the test classpath, yet no full Boot `ApplicationContext` is started and no live port is opened.

### Standalone Limitations

You instantiate the real `GreetingService` and pass it to the controller via constructor. This works well for focused controller tests, but does **not** automatically load:
- app `@ControllerAdvice`,
- security filter chains,
- global JSON customizations,
- interceptors,
- context-specific conversion/validation,
- custom Servlet filters,
- Spring AOP proxies around the service.

To test those configurations, use `bindToApplicationContext(...)` or Boot `@WebMvcTest`/`@SpringBootTest` depending on the goal. Never call a standalone controller test a full application integration test.

## 26. `RestTestClient.bindToServer()`: An Externally Managed Live Server

When an integration environment already has an HTTP server at a trusted URL, you can use:

```java
RestTestClient client =
        RestTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:8080")
                .build();

client.get().uri("/api/ping")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("pong");
```

**Conceptual standalone snippet**, requiring a local server implementing the API on port 8080 and `RestTestClient` on Framework 7.0+. Do not put a fixed port into default CI tests; use a local server managed by `@SpringBootTest(RANDOM_PORT)` or a Testcontainers mapped port/URI.

### Do Not Confuse Test Clients With Production HTTP Clients

`RestTestClient` provides a `RestClient`-like facade to simulate **callers hitting a server**. Production code should never inject `RestTestClient` as an ordinary HTTP adapter. It belongs strictly in test scope; use `RestClient` or `WebClient` in production code.

## 27. RestTestClient Assertions: Built-In vs. AssertJ

Per Spring Framework 7.0, built-in fluent expectations:

```java
client.get()
        .uri("/api/greetings/Lin")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello Lin");
```

With a typed body:

```java
client.get().uri("/api/hello/Ada")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello Ada");
```

These are snippets using a `client` already bound to a controller/server; they are not additional test methods.

### AssertJ Response API

Spring Framework 7 provides `RestTestClientResponse` in `org.springframework.test.web.servlet.client.assertj`. Usage (snippet):

```java
RestTestClient.ResponseSpec spec =
        client.get().uri("/api/hello/Ada")
                .exchange();

RestTestClientResponse response =
        RestTestClientResponse.from(spec);

assertThat(response)
        .hasStatusOk()
        .bodyText()
        .isEqualTo("Hello Ada");
```

Requires imports `RestTestClient`, `RestTestClientResponse`, and `org.assertj.core.api.Assertions.assertThat`. This enables **AssertJ** checks on the result rather than replacing built-in expectations. For simple typed bodies and JSONPath checks, built-in `expectBody` is often clear enough.

### `expectAll` Is Not a Retry

`expectAll(...)` runs multiple assertions even if an earlier one fails, similar to soft assertions. It **does not** re-send the HTTP request and is not a resilience retry mechanism. A test with multiple assertions still normally performs a single HTTP exchange.

### Consume the Response Body When Needed

When using pooled HTTP buffers or leak detection, Spring documentation recommends **consuming the response body**, e.g., via `expectBody()` or `expectBody(Void.class)` depending on context. Do not neglect resource cleanup simply because you only check the status. In mock environments buffer lifecycle differences are less visible, yet the habit pays off.

## 28. What Still Works on Boot 4?

**`MockMvc` is not gone.** Spring Framework 7 still supports `MockMvc`, and `MockMvcTester` continues to exist. `RestTestClient` is a **new option**, not a mandate to rewrite every legacy test.

For example, Boot 4 can still use:

```java
assertThat(mvc.get().uri("/api/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

when `mvc` is a `MockMvcTester` auto-configured by Boot 4 `@WebMvcTest` with AssertJ present. With raw `MockMvc`, `mvc.perform(get(...)).andExpect(...)` still works too. Migrating an entire suite to `RestTestClient` can generate huge diffs without adding value if your team already has solid coverage with `MockMvc`/`MockMvcTester`.

### When Should You Migrate?

- You want the **same test API** for `MockMvc`-bound tests and live HTTP tests.
- You want fluent expectations and typed bodies in MVC tests.
- You are already on Boot 4 and want to standardize HTTP server tests.
- You want to narrow differences between local controller tests and embedded HTTP tests.

### When Should You NOT Migrate?

- You are on Boot 3.3 or 3.5 without budget for an upgrade.
- You are testing pure Java service logic that needs no MVC machinery.
- Existing tests rely heavily on `MockMvc`-specific extensions/custom handlers that have not been evaluated for conversion.
- The team must maintain compatibility across multiple Spring Boot lines in one codebase.
- You already use `WebTestClient` for reactive/WebFlux tests and it fits well.
- You are testing an outbound HTTP client: use `MockRestServiceServer`/`MockWebServer`, not server-side `RestTestClient`.

## 29. `@MockitoBean` Is Another Common Version-Related Error

A StackOverflow snippet for newer Boot:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

On Boot 3.3.5 (Spring Framework 6.1), Framework 6.2's Mockito bean override package **does not exist**. The proper import on Boot 3.3 is:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

In 3.4/3.5, Framework 6.2 provides `@MockitoBean` and legacy Boot `@MockBean` is deprecated; in Boot 4, Spring Test overrides are used. Never swap the import **while forgetting bean matching semantics**, especially when dealing with:
- Multiple beans of the same type.
- Bean name/qualifier selection.
- Spring context cache reuse.
- Scoped proxies.
- `FactoryBean`.
- Stubbing needed before `@PostConstruct` code invokes a collaborator.

### Mock Setup During Startup

If a service is called inside `@PostConstruct` or an application runner, stubbing inside the `@Test` method runs too late—the Spring context has already refreshed. Use test-specific configuration/injection before startup or refactor startup side effects. Do not confuse this issue with a missing `MockMvcTester` API.

## 30. Boot 4 `@WebMvcTest` Package Relocation: An Easy-to-Miss Error

A test using:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
```

works on Boot 3.3/3.5. When moving to Boot 4, use the new module package:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
```

Similarly, Boot 4's `@AutoConfigureMockMvc` resides in `org.springframework.boot.webmvc.test.autoconfigure`. Bumping only the plugin while keeping old imports causes `package does not exist` errors before tests are even discovered.

### Import Checklist per Branch

**Boot 3.3**: legacy Boot `@WebMvcTest`, legacy Boot `@MockBean`, Spring `MockMvc`.

**Boot 3.5**: legacy Boot `@WebMvcTest`, new Framework `@MockitoBean`, new Spring `MockMvcTester`.

**Boot 4.0**: new Boot `@WebMvcTest`, Framework `@MockitoBean`, Spring `RestTestClient`, Boot `@AutoConfigureRestTestClient`.

**No single set of imports compiles across all three branches** if the source directly references `RestTestClient`.

## 31. Why Not Force `spring-test` 7 Into Boot 3.3?

Wrong build patch example:

```groovy
dependencies {
    // Wrong: trying to force Spring Test 7 alone into Boot 3.3.
    testImplementation 'org.springframework:spring-test:7.0.0'
}
```

This is a **counterexample snippet**, not part of the runnable project. `spring-test` 7 is built against Spring Framework 7 and its matching runtime/container dependencies. Boot 3.3 manages Spring Framework 6.1. Mixing major versions can let tests compile while failing at runtime, or fail compilation due to changed API signatures.

Possible failures:
- `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException`.
- `BeanCreationException` from incompatible Spring context methods.
- One controller test passes while another auto-configuration class fails.
- Incompatible Servlet/Jakarta types.
- Maven/Gradle resolution pulling multiple Spring versions at once.
- Test dependency conflicts with JUnit/Jackson/Mockito.

**Proper fix:** choose a Spring Boot release line compatible with the Framework version you want; inspect BOM/`dependencyInsight`; upgrade the full stack per migration notes; and run all tests. Never "bolt" Spring Framework 7 onto Boot 3.3 via ad-hoc dependency overrides.

## 32. How Do MockMvcTester, WebTestClient, and RestTestClient Differ?

| Criterion | MockMvcTester | WebTestClient | RestTestClient |
| --- | --- | --- | --- |
| Available since | Framework 6.2 | Prior to Framework 6.2 | Framework 7.0 |
| Backend | `MockMvc`, mock Servlet | WebFlux mock, or bound to MVC/real HTTP | `RestClient` + `MockMvc` bridge or real HTTP |
| Focus | MVC AssertJ assertions | Reactive-style API | Blocking HTTP test-style API |
| Server port | No | Depends on setup | Depends on `bindTo...` |
| Ideal context | Spring MVC controller/slice | WebFlux, or teams already standardized on it | Boot 4 MVC tests or live HTTP under one API |
| Test dependencies | `spring-test` + AssertJ + MVC test | `spring-test`/WebFlux test dependencies | Spring 7 `spring-test` + Boot test wiring when autowired |
| Production app HTTP client? | No | No | No |

All three are **test APIs**. Do not assume fluent syntax gives them identical backpressure, threading, connection pooling, or message decoding. For WebFlux, `WebTestClient` is the natural choice; for Spring MVC on Boot 3.5, `MockMvcTester` is concise and capable; for Spring MVC on Boot 4, `RestTestClient` adds a unified mock/live option.

### RestTestClient Is Not an Alias for WebTestClient

Method names look similar, such as `exchange().expectStatus().isOk()`, yet packages, implementations, dependencies, and supported server setups differ. Do not import `org.springframework.test.web.reactive.server.WebTestClient` and call `RestTestClient.bindToController(...)` examples—they are different classes.

## 33. Common Compile and Runtime Errors

| Symptom | Possible Cause | Remedy |
| --- | --- | --- |
| `cannot find symbol MockMvcTester` in Boot 3.3 | Missing in Spring Test 6.1 | Use `MockMvc` or upgrade to Boot 3.4/3.5 |
| `cannot find symbol RestTestClient` in Boot 3.5 | Missing in Spring Test 6.2 | Use `MockMvcTester`/`WebTestClient` or upgrade to Boot 4 |
| `package ...web.servlet.assertj does not exist` | `spring-test` too old or missing dep | Inspect `spring-test` on `testCompileClasspath` |
| `package ...web.servlet.client does not exist` | Not on Framework 7 | Check Boot 4 BOM |
| `package ...bean.override.mockito... does not exist` | Framework 6.1 | Use `@MockBean` in Boot 3.3 or upgrade release line |
| Legacy `@WebMvcTest` import fails on Boot 4 | Boot test packages split | Switch to Boot 4 package and test starter |
| `No qualifying bean of type MockMvcTester` | MVC test bean not auto-configured | `@WebMvcTest`/`@AutoConfigureMockMvc`, AssertJ & classpath |
| `No qualifying bean of type RestTestClient` | Missing `@AutoConfigureRestTestClient` or module | Add Boot 4 test config/dependency or bind manually |
| `NoSuchMethodError` after bumping a JAR | Spring artifacts from different major/minor lines | Re-align Boot BOM/Framework dependencies |
| `NoClassDefFoundError Servlet...` | Incompatible Jakarta Servlet API/container | Align stack/Servlet dependency versions |
| `Failed to load ApplicationContext` | Missing mock collaborator or bad slice | Use `@MockitoBean`/`@MockBean` for your branch |
| Test status 200 but body is null | Service mock unstubbed | Stub matching arguments; assert payload |
| Unexpected 404 on mock request | Request mapping differs | Verify annotations/URI |
| `RestClient` lacks `expectStatus` | Confused production client with test client | Use `RestTestClient`/`WebTestClient`/`MockMvc` |
| Live HTTP test cannot connect | Hardcoded port 8080 or server not started | `RANDOM_PORT` + auto-configured `RestTestClient` |
| Passes with `MockMvc` but fails live | Different filters/session/encoding/network/transactions | Add real HTTP contract tests |
| Boot 4 Gradle plugin build fails | Gradle below 8.14 or mismatched Java/toolchain | Upgrade Wrapper and verify JDK |
| JSON assertions fail after migration | Jackson/codec/property naming changed | Check content type, mapper/schema, fixtures |
| `@MockitoBean` fails to replace intended bean | Ambiguous type/qualifier | Use named override or explicit qualifier |
| Other tests fail after adding new test modules | Classpath/auto-config changes | Inspect dependency graph and startup logs |

## 34. Do Not Work Around Compile Errors With Reflection in Production Tests

One trick might check `Class.forName("...MockMvcTester")` at runtime. However, if a Java source imports a class that does not exist, **the compiler fails before runtime**. Reflection-based "if present" checks cannot make that file compile under Boot 3.3.

If a library must support multiple Spring versions, better options are:
- Rely only on APIs available in the minimum supported version (e.g., `MockMvc`).
- Separate version-specific adapters/test sources into dedicated `sourceSets`/modules with release-specific classpaths.
- Run a multi-release testing matrix in CI where each version's test classes compile separately.
- Run real integration tests on each supported version rather than relying on dynamic detection.
- Pin Java toolchains, Gradle/Maven plugins, and BOMs per variant.
- If reflection is genuinely needed to bridge an optional API, write thorough linkage/catch/compatibility tests rather than ad-hoc workarounds.

**Version gates are compile-time contracts**, not merely runtime `assumeTrue(...)` checks.

## 35. What Should a CI Matrix Verify?

A project supporting multiple Boot lines can use a CI matrix:

```text
Variant A: Java 17 | Boot 3.3.5 | Framework 6.1
  -> compile MockMvc tests
  -> run MVC slice + TestRestTemplate HTTP tests

Variant B: Java 17 | Boot 3.5.x | Framework 6.2
  -> compile MockMvcTester tests
  -> run slice with @MockitoBean

Variant C: Java 17 | Boot 4.0.x | Framework 7.0
  -> Gradle 8.14+
  -> compile RestTestClient tests
  -> run MockMvc-bound slice + RANDOM_PORT HTTP tests
```

Do not put the newest test files into a source set shared across all Boot lines and annotate them `@Disabled` or with JUnit conditions. `@Disabled`/`@EnabledIf...` only control execution **after compilation**; missing classes still fail `compileTestJava`. If Test C uses `RestTestClient`, compile C only against the Boot 4 classpath.

### CI Artifacts and Reports

Track separately:
- compilation status;
- JUnit case counts and skipped counts;
- Java/Gradle/Boot/Framework versions;
- HTML/JUnit XML reports;
- TestContext startup errors;
- `dependencyInsight` output when failures stem from classpath conflicts.

If a matrix variant fails during compilation, there will be no JUnit test cases for it. Never report "0 test failures" while overlooking a build failure.

## 36. Sharpening Naming and API Selection

A quick decision table:

| Context | Recommendation |
| --- | --- |
| Boot 3.3, MVC slice | `MockMvc` |
| Boot 3.3, live HTTP server | `TestRestTemplate`, or `WebTestClient` when configured |
| Boot 3.4/3.5, MVC slice | `MockMvc` or `MockMvcTester` |
| Boot 3.4/3.5, live HTTP | `TestRestTemplate`/`WebTestClient` |
| Boot 4, MVC slice | `MockMvc`/`MockMvcTester`/`RestTestClient` |
| Boot 4, live HTTP | `RestTestClient` bound to server or auto-configured |
| Testing outbound `RestClient` | `MockRestServiceServer`, `MockWebServer`, WireMock |
| Testing WebFlux/reactive endpoint | `WebTestClient` |
| Unit testing service unrelated to HTTP | JUnit + Mockito, no MVC needed |
| Testing business DB commits | JDBC/JPA/Testcontainers integration, not inferred from HTTP mocks |

**Principle of least change:** if an existing `MockMvc` test expresses the contract clearly and runs stably, you do not have to rewrite it to `RestTestClient` just because a newer release exists. When you need to catch real HTTP/serialization bugs missed by mock servlets, add a small set of `RANDOM_PORT` tests instead of moving every test to a heavier live server.

## 37. Mistakes When Migrating `@WebMvcTest` Slices

1. **Forgetting to mock dependencies:** `@WebMvcTest` does not scan all `@Service` beans, causing controller constructor injection to fail.
2. **Using unit-style `@Mock` instead of `@MockitoBean` in a Boot 4 Spring context:** a Mockito field does not replace a Spring bean.
3. **Updating the `@WebMvcTest` import without adding the Boot 4 test starter:** annotations/packages remain missing.
4. **Wrong test path strings:** Swagger URLs, controller class paths, or media types changed after upgrading.
5. **`MockMvcTester` missing AssertJ:** bean or assertion classes are missing compared to examples.
6. **Different default security filters:** a `401/403` may come from security configuration rather than an API bug.
7. **Swapping only the Spring Framework BOM:** causes class linkage failures.
8. **Unclear mix of Spring WebMVC and WebFlux:** Boot prefers MVC when both are on the classpath; test config must be explicit.
9. **Forgetting to update test report paths/source sets:** CI loses tests even when local builds run.
10. **Asserting only status:** broken schemas, Content-Type headers, or bodies slip through.
11. **Using `@Transactional` with `RANDOM_PORT`:** the server transaction runs on a different thread from the test client.
12. **Treating compile success as integration pass:** compilation only verifies part of the API and linkage.

## 38. Why Auto-Configuration Differs Between `@WebMvcTest` and `@SpringBootTest`

`@WebMvcTest` is a test slice loading only the slice of the application context relevant to Spring MVC. Beans outside its scan scope (business services/repositories) need `@MockBean` or `@MockitoBean` matching your version, or `@Import`/test configuration when real beans are needed.

`@SpringBootTest` loads the full application context; combined with `@AutoConfigureMockMvc`, it still uses a mock Servlet environment with no listening port by default. `@SpringBootTest(RANDOM_PORT)` starts a real HTTP server. With Boot 4's `@AutoConfigureRestTestClient`, the client target depends on the test environment—mock-MVC-bound or server-bound. `@SpringBootTest` alone does **not** guarantee `@Autowired RestTestClient` is available without the right test auto-configuration and module.

### When Is `@AutoConfigureMockMvc` Needed?

On Boot 3.3/3.5:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullContextMvcTests {
    @Autowired MockMvc mvc;
}
```

This is a **test class snippet without `@Test`**, requiring Boot-version-appropriate imports. `@SpringBootTest` does not automatically create a `MockMvc` bean without `@AutoConfigureMockMvc`, whereas `@WebMvcTest` already provides it. In Boot 4, `@AutoConfigureMockMvc`'s package moves to `org.springframework.boot.webmvc.test.autoconfigure`.

### Mock MVC Is Not Live HTTP

`@AutoConfigureMockMvc` still handles requests via mock servlet objects. Even with controller security filters enabled, it will not prove TCP connection handling or real deployed proxy headers. Choose the test level by contract rather than "integration feel".

## 39. Separating Classpath Errors From Business Errors During Investigation

Debugging order:

1. Check which task failed: `compileTestJava` or `test`?
2. For compile errors, inspect imports/packages and the dependency tree before touching business code.
3. For `NoClassDefFoundError`/`NoSuchMethodError`, inspect resolved versions of all Spring artifacts, not only `spring-test`.
4. For context failures, verify the Boot `@WebMvcTest` package and collaborator bean overrides.
5. For single JUnit assertion failures, inspect request URI, `Accept`/`Content-Type`, body, stubbing, and MVC advice.
6. If `MockMvc` passes while live HTTP fails, inspect embedded server port, serialization, filters, cookies/headers, transactions, and networking.
7. If only CI fails, check JDK, Gradle Wrapper, test source sets, caches, and JUnit versions.
8. If still stuck, build a minimal reproduction with one controller and one test on the target branch rather than mixing 6.1/6.2/7.0 code.

A common pitfall: IDE caching resolves `MockMvcTester` from Project A (Boot 3.5) while Project B (Boot 3.3) fails Gradle compilation with missing classes. Always trust the **resolved build classpath of the active module**, not autocomplete from another module.

## 40. MockMvcTester Makes Tests Concise, Not Mandatory to Migrate Everything

`MockMvc`:

```java
mvc.perform(get("/api/hello/Ada"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello Ada"));
```

`MockMvcTester`:

```java
assertThat(mvc.get().uri("/api/hello/Ada"))
        .hasStatusOk()
        .hasBodyTextEqualTo("Hello Ada");
```

`RestTestClient`:

```java
client.get().uri("/api/hello/Ada")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello Ada");
```

These three snippets show the API surface differences; the `mvc` variable has different types in the first two snippets. Do not mix all three into a Boot 3.3 class. Newer Spring Boot versions still support the first style; pick an API based on dependency support and assertion needs.

## 41. When to Use Typed Bodies Instead of Raw JSON

With `RestTestClient`, `expectBody(GreetingMessage.class)` decodes JSON into a Java record. When a test checks schema fields against an API contract, JSONPath is often clearer. When a test checks business object equality, typed bodies are handy.

Example in Boot 4 standalone/live:

```java
client.get().uri("/api/greetings/Lin")
        .exchange()
        .expectStatus().isOk()
        .expectBody(GreetingMessage.class)
        .isEqualTo(new GreetingMessage("Hello Lin"));
```

This is a **snippet, not an extra `@Test` method**. When an app uses Jackson customizations, polymorphism, date/timezone formatting, or JSON modules, client-side decoding can mask wire JSON differences; pick assertions carefully and inspect raw JSON when needed.

`MockMvcTester` leans on AssertJ over `MockMvc` results with `bodyJson().extractingPath(...)`; it does not share `RestTestClient`'s `expectBody(Class)` API. Likewise, traditional `MockMvc` uses `jsonPath(...)` result matchers. These differing APIs explain many "cannot resolve method" errors when copying snippets between clients.

## 42. Limitations and Changes Related to Servlet 6.1, Jakarta, and Boot 4

Boot 4/Spring 7 updates major parts of the web stack, including the Servlet API baseline. An older third-party filter or Servlet container may be incompatible even when REST controller code compiles cleanly. If `@WebMvcTest` passes while live HTTP fails, check:
- Servlet version and embedded Tomcat/Jetty compatibility;
- Jakarta imports replacing legacy `javax`;
- custom Servlet filter implementations;
- MVC request path matching;
- HTTP message converter/Jackson upgrades;
- Spring Security version/config;
- bean/auto-configuration changes;
- test modules and JUnit Platform versions;
- logging/observation filters.

Do not conclude "`RestTestClient` caused the failure" merely because it coincided with an API switch. Upgrading to Boot 4 is a broad framework migration; separate test-code compile issues from runtime application configuration errors.

### A Practical Trick

Before migrating tests to `RestTestClient`, run the **same endpoint** through `MockMvc` on Boot 4. If `MockMvc` passes while mock-bound `RestTestClient` fails, examine test wiring and assertion semantics. If both pass mock-bound while live HTTP fails, investigate networking, container, and real-server behavior. Comparing the two isolates the boundary.

## 43. Maintaining Multi-Branch Codebases: Version-Specific Test Adapters

An internal library supporting both Boot 3.3 and Boot 4 can:
- Write **core contract tests** independent of newer test facades, e.g., plain `MockMvc` usable on both versions.
- Place **version-specific module tests** in `sourceSets` or subprojects compiled only against the matching BOM.
- Add `MockMvcTester` once the minimum supported version reaches Boot 3.5.
- Add `RestTestClient` once the minimum supported version reaches Boot 4.
- Use a dependency-compatibility test suite instead of hiding missing classes behind reflection fallbacks.
- Never paste all three test classes into every module and `@Disabled` the ones missing dependencies—the compiler will still fail.
- Use a CI version matrix with separate build reports per module/JDK/Boot line.
- Run tests on at least the minimum and maximum supported versions; an API existing on the latest version does not prove the oldest supported line works.

### Support Commitments

If a team advertises "compatible with Spring Boot 3.3–4.0", there must be **code compilable for each supported version** or separate modules; if a library's public API directly exposes `RestTestClient` in signatures, Boot 3.3 consumers cannot compile against that artifact without an adapter layer.

## 44. Reading Release Notes and Javadoc `@since`

When encountering an unfamiliar class in a test snippet:

1. Identify its **fully qualified class name**.
2. Open the versioned API Javadoc for Spring Framework/Boot.
3. Look for the **Since** tag; distinguish the introduction version from deprecation/removal versions.
4. Check which package and artifact contain the class.
5. Check the dependency BOM mapping for your Spring Boot release line.
6. Read the Spring Boot testing reference for **your exact version**, not the default "current" page.
7. Verify the annotated auto-config module is on the test runtime classpath.
8. Check method-call examples in the matching Javadoc version, since signatures can evolve across milestones.
9. Run Gradle `dependencyInsight` and compile a minimal test.
10. Only then refactor tests broadly, keeping regression reports intact.

**Milestone/RC/SNAPSHOT APIs** can change before GA; never apply a milestone example to a different GA release without checking. For `MockMvcTester`, both Framework 6.2.0 milestone and GA Javadocs document the entrypoint; for `RestTestClient`, verify against 7.0 GA/current APIs.

## 45. QA Checklist for Migration Pull Requests

- [ ] Stated exact Boot branch/patch, Framework branch, and Java/Gradle versions?
- [ ] Confirmed `MockMvcTester` is used only on Framework 6.2+?
- [ ] Confirmed `RestTestClient` is used only on Framework 7.0+?
- [ ] Not confusing production `RestClient` with testing `RestTestClient`?
- [ ] Not confusing `WebTestClient` with `RestTestClient`?
- [ ] Not bumping `spring-test` major version beyond the Boot BOM?
- [ ] No unsupported test sources left inside Boot 3.3/3.5 projects?
- [ ] Boot 3.3 uses `@MockBean` from the proper package?
- [ ] Boot 3.5+ uses `@MockitoBean` when migrating and verifies bean overrides?
- [ ] Boot 4 `@WebMvcTest` and `@AutoConfigureMockMvc` use the new packages?
- [ ] Boot 4 includes the matching test starter/module and `@AutoConfigureRestTestClient`?
- [ ] Boot 4 uses Gradle 8.14+ and JDK 17+?
- [ ] `@WebMvcTest` mocks needed collaborators without accidentally loading a DB?
- [ ] `MockMvcTester` tests have the AssertJ dependency?
- [ ] Distinguished mock-bound tests from real HTTP tests?
- [ ] Tests assert status, `Content-Type`, and body instead of merely asserting no exception?
- [ ] JSONPath/typed body assertions avoid brittle formatting assumptions?
- [ ] Added 404/negative branch tests without masking context failures?
- [ ] `@SpringBootTest(RANDOM_PORT)` avoids hardcoded listening ports?
- [ ] Accounted for separate server threads when live HTTP tests write to a DB?
- [ ] Maintained reports/CI matrix per supported version?
- [ ] Checked `dependencyInsight` on compile/linkage errors?
- [ ] Never claimed tests PASSED without running Gradle?
- [ ] Avoided false green builds from skipping uncompilable tests?
- [ ] Code examples in docs tagged with exact versions/modules?

## 46. Hands-On Exercises

1. Create `boot33-mockmvc` from Project A; run `GreetingController33SliceTest`.
2. Run `GreetingController33HttpTest` and compare the real port against the mock servlet.
3. Try importing `MockMvcTester` into a Boot 3.3 sandbox, read the compiler error, then remove the import to restore it.
4. Run `dependencyInsight --dependency spring-test` to observe Framework 6.1.
5. Upgrade the sandbox to Boot 3.5, remove version-incompatible test files, and add `GreetingController35SliceTest`.
6. Try `MockMvcTester.of(new GreetingController(new GreetingService()))` in a standalone test and compare with `@WebMvcTest`.
7. Add a JSON field to `GreetingMessage` and compare `bodyJson().extractingPath` with raw body equality.
8. Use `@MockitoBean` in Boot 3.5 and compare with legacy `@MockBean` behavior.
9. Try importing `RestTestClient` in the Boot 3.5 sandbox and analyze why it is absent.
10. Upgrade a separate project to Boot 4.0 with Gradle 8.14+, updating test starters and `@WebMvcTest` imports.
11. Run a Boot 4 slice test with `@AutoConfigureRestTestClient` and assert the response with JSONPath.
12. Run a Boot 4 live HTTP test with `RANDOM_PORT` + `RestTestClient`.
13. Run standalone `RestTestClient.bindToController` and verify no port is opened.
14. Use `RestTestClient.bindToServer` against an owned local test server—never call a production URL.
15. Create an outbound REST client and test it with `MockRestServiceServer`; explain how it differs from a server test.
16. Write a WebFlux endpoint and test it with `WebTestClient`; contrast it clearly with `RestTestClient`.
17. Check how missing AssertJ on the classpath affects `MockMvcTester` assertions and bean injection.
18. Intentionally mix `spring-test` 7 into a Boot 3.3 sandbox, inspect the dependency tree, then restore the proper BOM.
19. Add Spring Security on a branch and observe 401/403 responses before adding test auth.
20. Build a 3-variant CI matrix keeping JUnit XML/HTML reports separate.
21. Try putting `@Disabled` on a test source importing an unsupported class and verify the compiler still fails.
22. Experiment with `MockMvcTester` async APIs (`exchange()`/`asyncExchange()`) on a properly configured async endpoint.
23. Read `@since` Javadocs and references for Framework 6.1/6.2/7.0 and create an import lookup table for your team.
24. After migrating, run the full suite/CI and compare pass/fail/skip counts before and after.

## 47. Official References

- [Spring Framework 6.1 — Spring MVC Test / MockMvc](https://docs.spring.io/spring-framework/reference/6.1/testing/spring-mvc-test-framework.html): `MockMvc` and MVC testing prior to `MockMvcTester`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@AutoConfigureMockMvc`, `@MockBean`, `TestRestTemplate`.
- [Spring Framework 6.2 — MockMvc AssertJ Integration](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj.html): `MockMvcTester`, AssertJ assertions, and JSON support.
- [Spring Framework 6.2 — MockMvcTester Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/web/servlet/assertj/MockMvcTester.html): `of`/`from` factories and fluent API.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `MockMvcTester` bean injection, `@MockitoBean`, and MVC testing.
- [Spring Framework 7.0 — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html): `bindToController`, `bindToApplicationContext`, `bindToServer`, built-in expectations.
- [Spring Boot 4.0 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): `@AutoConfigureRestTestClient`, mock-bound and `RANDOM_PORT`.
- [Spring Boot 4.0 — Test Modules](https://docs.spring.io/spring-boot/4.0/reference/testing/test-modules.html): feature-split modules.
- [Spring Boot 4.0 — Build Systems](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html): `webmvc`/test starter coordinates.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Java 17, Gradle 8.14+.
- [Spring Framework 7 — RestTestClient Builder Javadoc](https://docs.spring.io/spring-framework/docs/7.0.0-M8/javadoc-api/org/springframework/test/web/servlet/client/RestTestClient.Builder.html): Since 7.0, builder semantics.
- [Spring Blog — The state of HTTP clients in Spring](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/): rationale for `RestTestClient` and differences from `WebTestClient`.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, context lifecycle/runner.
- [Gradle — Dependency Management & Dependency Insight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencyInsight`, versions, and conflicts.

## 48. Conclusion

**An API is usable only when both the version and module support it.** On Spring Boot 3.3.5 / Framework 6.1, use `MockMvc` and `TestRestTemplate` with matching dependencies; `MockMvcTester` and `RestTestClient` do not exist yet. Upgrading to Boot 3.4/3.5 / Framework 6.2 brings `MockMvcTester` and `@MockitoBean` for AssertJ MVC tests. Upgrading to Boot 4.0 / Framework 7.0 introduces `RestTestClient`, providing one test facade across two modes—MockMvc-bound without a real server and `bindToServer`/`RANDOM_PORT` with real HTTP—alongside Boot 4's new test modules and relocated annotation packages.

Never force `spring-test` from another major version into an older Boot BOM, never `@Disabled` a test file that fails to compile, and never confuse outbound `RestClient` with inbound `RestTestClient`. Instead of rewriting an entire suite just for fluent syntax, pick the test API matching your release line, verify contracts via status/body assertions, and expand from mock MVC to live HTTP where needed. **Seeing 15 `@Test` methods across the three example branches is not proof that 15 tests PASSED; run Gradle/JUnit separately per branch and inspect actual test reports.**
