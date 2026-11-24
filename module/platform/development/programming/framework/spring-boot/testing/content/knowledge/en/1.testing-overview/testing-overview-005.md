# Application Running, Spring Context Starting, and Correct Business Logic Are Three Different Kinds of Evidence

In Spring Boot testing, the three statements “the app runs”, “the context-loading test is green”, and “the business logic is correct” describe **three kinds of evidence with different scopes**. One piece of evidence can be true while the other two remain unverified—or are already broken. This lesson helps you read test results accurately and choose checks that match the risk you want to rule out.

## 1. Distinguish Immediately by the Question Being Answered

| Evidence | Question Actually Answered | Typical Observation | What Cannot Be Concluded Yet |
| --- | --- | --- | --- |
| **Application runs** (runtime/smoke) | Can the process start and serve minimal behavior in the environment being tested? | Run the JAR/application, observe the process, and call an HTTP endpoint | That all beans, routes, config in other environments, or business rules are correct |
| **ApplicationContext starts** (context-loading) | Can Spring assemble the bean set and configuration of the selected *test context*? | `@SpringBootTest`, load context, and retrieve required beans | That endpoints accept network requests, business flows produce right results, or production config matches test |
| **Business logic is correct** (behavior/correctness) | Given stated inputs and conditions, do outcomes and effects match expected rules? | Assertions on values, errors, data state, and key interactions; unit/integration/API tests | That untested branches are right; unit tests alone also do not verify Spring wiring or HTTP works |

These three dimensions can overlap: an HTTP integration test that actually starts a web server and calls an endpoint can provide evidence of both startup and behavior **for that specific scenario**. Even so, do not generalize from that to “the whole system is correct”.

## 2. “The Application Runs” Must Tie to Observable Signals

Distinguish three levels that are easily lumped together as “runnable”:

1. **Successful compile/packaging:** `./gradlew classes` or `./gradlew bootJar` proves the corresponding build steps completed. This is **not yet** evidence that the application process has run. The `build` task may also run tests, yet the strength of that conclusion still depends on which tests exist and actually executed.
2. **Process startup:** `./gradlew bootRun` or `java -jar ...` launches the application. For a web app, startup logs are one signal; you should also verify the process stays alive and the port accepts requests.
3. **Minimal end-to-end smoke check:** call an expected URL and check the HTTP status and body. This confirms the invoked path works in the current environment; it does not replace tests for other rules.

For example, `GET /api/prices/after-discount?original=100000&percent=20` returning `200` with body `80000` is evidence that the endpoint and the 20% discount scenario worked at runtime. A health endpoint reporting `UP` (if the project includes Actuator and is configured accordingly) is only a health signal for the enabled health indicators; it does not by itself prove the pricing rule is right.

**Ask the right questions:** how was it launched, with which profile, on which port, was a real request sent, and what response was observed? “No exceptions in the log” is weaker evidence than “a specific request returned the expected response”.

## 3. What Does “Spring Context Starts” Prove?

Spring Boot uses `ApplicationContext` to read configuration, scan components, apply auto-configuration, and instantiate/wire beans. Context initialization tests catch many errors such as missing required beans, bean conflicts, unresolvable circular dependencies, missing required properties, or errors thrown during initialization. Exact failures depend on which configuration is loaded.

A common check looks like:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextStartsTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void requiredPriceServiceIsPresent() {
        assertNotNull(context.getBean(PriceService.class));
    }
}
```

This is an **excerpt illustration**; Section 5 provides a complete class with full imports and a sample project. `webEnvironment = NONE` asks to start the application context **without running an HTTP server**. It is suitable for checking application wiring, but cannot prove HTTP routes handle requests. `@SpringBootTest(webEnvironment = RANDOM_PORT)` also starts an embedded web server on a random port, enabling real HTTP testing.

Be explicit about the context scope:

- `@SpringBootTest` loads the application context under test configuration. If using a test profile, property overrides, a fake server, or a test database, the result directly applies only to those choices.
- `@WebMvcTest` builds only an MVC slice for controller tests; a passing slice test is not equivalent to the full application context succeeding.
- `@MockBean` or mocks injected into the context help isolate components, yet can also mask integration errors with real dependencies. Interpret evidence according to the real wiring under test.
- Context loading does not check every logic branch: a service that wrongly calculates 20% as 10% can still be instantiated cleanly by Spring as a bean.

## 4. “Correct Business Logic” Needs Clear Rules and Meaningful Assertions

Suppose the business requirement for a pricing service is: accept `original` (non-negative integer amount) and `percent` (from 0 to 100), apply the percentage discount; the discount amount is **rounded down to an integer unit**, the discounted price is non-negative; invalid parameters must be rejected.

Scenarios to verify include normal cases (100,000, 20% → 80,000), boundaries (0%, 100%, price 0), rounding (99, 10% → 90 since the discount is 9), and invalid inputs (negative price, out-of-range percentage). Assertions must compare against **an expected value derived independently from requirements**. A test that merely calls a method without failing, or only does `assertNotNull(result)`, is insufficient to prove the formula works.

Unit tests running the Java class directly can prove the formula without a Spring context. Integration/API tests can additionally verify controller mapping, HTTP handling, data serialization, and related components. For applications with a DB, message broker, or transactions, test actual state changes/rollbacks with suitable environment setup; a unit test using mocks does not verify effects on a real DB.

## 5. Complete Spring Boot Example to Cross-Check the Three Kinds of Evidence

The following files form a small example running on **Java 17+**, Spring Boot **3.3.x**, Gradle, and JUnit Jupiter. Place them in a Spring Boot project with the Gradle Wrapper; this example uses no DB, security, or external APIs so the illustrative checks remain cleanly separated.

Main structure:

```text
settings.gradle
build.gradle
src/main/java/com/example/testing/TestingApplication.java
src/main/java/com/example/testing/PriceService.java
src/main/java/com/example/testing/PriceController.java
src/test/java/com/example/testing/PriceServiceTest.java
src/test/java/com/example/testing/ContextStartsTest.java
src/test/java/com/example/testing/PriceHttpTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'testing-evidence'
```

**`build.gradle`** (Groovy DSL, for a standalone sample project):

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/testing/TestingApplication.java`**

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
```

**`src/main/java/com/example/testing/PriceService.java`**

```java
package com.example.testing;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public int afterDiscount(int original, int percent) {
        if (original < 0) {
            throw new IllegalArgumentException("original must be non-negative");
        }
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be between 0 and 100");
        }

        long discount = (long) original * percent / 100;
        return (int) (original - discount);
    }
}
```

The multiplication widens to `long` first to prevent `int` overflow when computing the percentage. Integer division rounds the discount down; the final result stays within `0..original` because `percent` is already validated.

**`src/main/java/com/example/testing/PriceController.java`**

```java
package com.example.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {
    private final PriceService service;

    public PriceController(PriceService service) {
        this.service = service;
    }

    @GetMapping("/api/prices/after-discount")
    public int afterDiscount(@RequestParam int original, @RequestParam int percent) {
        return service.afterDiscount(original, percent);
    }
}
```

The controller uses constructor injection: if `PriceService` is not registered by Spring as a bean, the full context cannot instantiate `PriceController`. The HTTP endpoint returns a JSON number, such as body `80000`. The sample code intentionally does not map `IllegalArgumentException` to HTTP 400; therefore, do not infer that the API properly handles HTTP errors merely from unit tests for invalid input.

### 5.1. Testing Business Logic Without Spring

**`src/test/java/com/example/testing/PriceServiceTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceServiceTest {
    private final PriceService service = new PriceService();

    @Test
    void appliesTwentyPercentDiscount() {
        assertEquals(80_000, service.afterDiscount(100_000, 20));
    }

    @Test
    void acceptsBoundaryPercentages() {
        assertEquals(100_000, service.afterDiscount(100_000, 0));
        assertEquals(0, service.afterDiscount(100_000, 100));
        assertEquals(0, service.afterDiscount(0, 40));
    }

    @Test
    void roundsDownTheDiscount() {
        assertEquals(90, service.afterDiscount(99, 10));
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> service.afterDiscount(-1, 20));
        assertThrows(IllegalArgumentException.class,
                () -> service.afterDiscount(100, -1));
        assertThrows(IllegalArgumentException.class,
                () -> service.afterDiscount(100, 101));
    }
}
```

This is **evidence of the pricing rule** on the asserted scenarios. If `@Service` is removed from `PriceService`, these unit tests can still pass because they use `new PriceService()`; that does **not** prove Spring found the bean.

### 5.2. Testing Context Startup Without Calling HTTP

**`src/test/java/com/example/testing/ContextStartsTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextStartsTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void requiredPriceServiceIsPresent() {
        assertNotNull(context.getBean(PriceService.class));
    }
}
```

The test only runs its assertion once Spring finishes creating the context. If the controller requires a missing bean, the test can fail right at initialization before entering the test method. Yet if the formula is changed to `return original;`, the context can still start completely normally: valid wiring does not mean correct business results.

### 5.3. Testing HTTP with a Real Web Server Inside the Test

**`src/test/java/com/example/testing/PriceHttpTest.java`**

```java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PriceHttpTest {
    @LocalServerPort
    private int port;

    @Test
    void returnsTheExpectedPriceThroughHttp() throws Exception {
        String url = "http://localhost:" + port
                + "/api/prices/after-discount?original=100000&percent=20";
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("80000", response.body());
    }
}
```

This test starts an embedded server on a random port, sends an HTTP request over loopback, and asserts both status and body. It proves web wiring and behavior for **one** end-to-end scenario in the test profile. It does not replace boundary testing, API error handling, authentication, high load, or production configuration testing.

### 5.4. Running and Reading the Evidence

In a project with the Gradle Wrapper, use:

```bash
./gradlew test
./gradlew bootJar
./gradlew bootRun
```

On Windows, use `gradlew.bat test`, `gradlew.bat bootJar`, `gradlew.bat bootRun`. `test` runs JUnit tests (when configured and not excluded); `bootJar` packages the JAR; `bootRun` launches the application. To test the packaged JAR separately, run `java -jar build/libs/testing-evidence-0.0.1-SNAPSHOT.jar` when that JAR exists. Do not treat `bootJar` succeeding as proof that the JAR has run.

Once the web app is running (default port 8080 if unchanged), call from another terminal:

```bash
curl -i "http://localhost:8080/api/prices/after-discount?original=100000&percent=20"
```

The expected response has **HTTP status 200** and **response body `80000`**; exact HTTP headers may differ by environment. If the app uses a different port/profile, update the URL accordingly. The `curl` command is a manual smoke/integration check; running automated tests does not automatically execute this against the newly packaged JAR.

You can run each layer individually to see where a failure lies:

```bash
./gradlew test --tests com.example.testing.PriceServiceTest
./gradlew test --tests com.example.testing.ContextStartsTest
./gradlew test --tests com.example.testing.PriceHttpTest
```

## 6. Counterexamples: Why Can't You Cross-Infer?

| Situation | Possible Observation | Correct Conclusion |
| --- | --- | --- |
| Remove `@Service` from `PriceService` | Unit tests using `new` stay green; context test and HTTP test fail when Spring cannot create `PriceController` | Logic was tested independently, yet application wiring is broken |
| Change calculation to always return `original` | Context still creates beans and can start the web server; the 20% unit test and HTTP body test fail | App starts up, yet pricing behavior is wrong |
| Call only the health endpoint | Server returns a healthy signal | `afterDiscount` result has not been tested |
| Run only `bootJar` | JAR file is produced | No runtime or correctness evidence yet; must run and test |
| Context test uses mocked configuration | Context test passes with mocks/test database | Does not prove connectivity or operation with real configuration |
| HTTP test checks only status 200 | Controller returns 200 even when the price is calculated wrong | Must also assert meaningful body/data/side effects |

A green test is a conditional statement: **with the setup, inputs, and assertions used, observed behavior matched expectations**. No test automatically confirms any unobserved state.

## 7. Strategy for Development and CI

1. **Start from business risk:** write fast unit tests for rules, boundary conditions, and input errors; name tests after behaviors.
2. **Verify required wiring:** use context-loading tests broad enough to catch bean/configuration declaration errors, keeping track of profiles and dependencies replaced in tests.
3. **Follow a real flow:** use HTTP integration tests to verify entry points, serialization, and externally visible outcomes. With a DB or broker, use an appropriate test environment and assert post-operation state too.
4. **Verify the packaged runnable artifact on release:** beyond the test suite, launch the artifact with its intended configuration and smoke-check an endpoint or readiness in a suitable environment.
5. **Read logs and reports according to the check executed:** distinguish compile/build errors, context initialization errors, network/HTTP errors, and business assertions; record inputs, environment, and expectations before drawing conclusions.

**Result-interpretation checklist:** Was there a real process? Which context loaded and under which profile? Which requests or method calls actually executed? Which values/effects did assertions verify? Were critical boundaries and failure paths covered? That is how you turn a “BUILD SUCCESSFUL” line or “green tests” into meaningful engineering evidence.

Keep the core conclusion intact: **running** shows a form of operational availability; **context starting** shows a Spring configuration can be assembled; **correct business logic** is supported only by concrete behavioral comparisons. To trust the system, gather all three kinds of evidence across the right risk scope.