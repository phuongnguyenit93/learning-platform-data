# How does `@SpringBootTest` load an application using Spring Boot's mechanism?

## 1. Essence: testing an ApplicationContext created by SpringApplication

`@SpringBootTest` is an annotation used for **integration testing with a Spring Boot context**. Instead of instantiating a plain Java service using `new`, the test asks Spring TestContext to create or retrieve an **`ApplicationContext`**; Spring Boot provides a loader that uses **`SpringApplication`**, which is Boot's familiar application startup mechanism.

The most important point:

> `@SpringBootTest` **does not simply scan beans**, nor does it **call `main()` by default**. It instructs Spring TestContext to initialize the test context **via SpringApplication**, based on the primary configuration and test options.

This brings along Spring Boot's characteristic mechanisms: managing the `Environment` and config data, activating profiles, component scanning, conditional auto-configuration, `@ConfigurationProperties` binding, dependency injection, bean lifecycle, and — depending on `webEnvironment` — a mock web environment or a real server.

Learning outcomes:

1. Explain the chain **JUnit Jupiter → SpringExtension → Spring TestContext → Spring Boot bootstrapper/loader → SpringApplication → ApplicationContext**.
2. Know how Boot locates the primary `@SpringBootApplication` / `@SpringBootConfiguration` configuration.
3. Distinguish between **SpringApplication running** and **the `main()` method being called**.
4. Choose the right `webEnvironment = MOCK / RANDOM_PORT / DEFINED_PORT / NONE` and understand when a real server runs.
5. Write and run Java 17+ examples demonstrating context loading, config/profile, MockMvc, and real HTTP.
6. Explain context caching, causes of slow startup, startup failures, transaction issues, and differences from unit tests or test slices.

## 2. Who actually triggers loading the application?

A minimal class:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationSmokeTest {
    @Test
    void contextLoads() {
        // No assertion needed to observe context initialization failures.
    }
}
~~~

This is an **illustrative skeleton**, not a standalone runnable file: the project must have an application configuration discoverable by Spring Boot, JUnit Platform, and the required dependencies. The test may PASS because the context starts up, but **an empty method does not prove business logic is correct**. A smoke test should be supplemented with meaningful assertions.

Conceptual mechanism:

~~~text
JUnit Jupiter discovers @Test
  |
  v
SpringExtension integrates into the JUnit lifecycle
  |
  v
Spring TestContext Framework
  |  - manages the test instance
  |  - prepares dependency injection, listeners
  |  - looks up or retrieves ApplicationContext from cache
  v
SpringBootTestContextBootstrapper
  |  - parses test annotations/configuration
  |  - locates the primary Boot configuration
  |  - prepares context customizers, properties, profiles
  v
SpringBootContextLoader
  |
  v
SpringApplication
  |  - prepares Environment and config data
  |  - selects web/non-web application type
  |  - creates context and loads bean definitions
  |  - refreshes; creates beans, applies auto-configuration
  |  - runs appropriate lifecycle callbacks
  v
ApplicationContext is ready for @Test methods
  |
  v
@Autowired / assertions / MockMvc or HTTP client
~~~

The arrows represent a **conceptual model**, not the exact call order of internal Java methods. Spring Boot and Spring Framework may change implementation details across versions, but the **TestContext + Boot context loader + SpringApplication** architecture is the core point.

### 2.1 Role of each component

- **JUnit Jupiter** identifies which methods have `@Test`, orchestrates the lifecycle, and records PASS/FAIL.
- **`SpringExtension`** bridges JUnit Jupiter with Spring TestContext to support dependency injection, callbacks, and test lifecycle.
- **Spring TestContext Framework** creates/configures the test context, applies `TestExecutionListener`, manages test transactions, and caches contexts when appropriate.
- **`SpringBootTestContextBootstrapper`** understands Boot-specific setup for the test, such as primary configuration, properties, and context customizers.
- **`SpringBootContextLoader`** uses `SpringApplication` to load the context, enabling Boot-specific startup capabilities.
- **`SpringApplication`** prepares the environment, runs startup steps, creates/refreshes the context, activates auto-configuration based on classpath and conditions, and returns a ready context.

With **JUnit Jupiter**, `@SpringBootTest` already integrates `SpringExtension`; normally **there is no need to add `@ExtendWith(SpringExtension.class)`**. If you see JUnit 4 examples using `@RunWith(SpringRunner.class)`, do not mix the legacy runner mechanism into JUnit Jupiter.

### 2.2 Why can tests only run after the context is created successfully?

Test methods using `@Autowired` require beans to be created or resolvable. If configuration is invalid, beans have circular dependencies, the database cannot be reached, or a required property is missing, Spring may report **“Failed to load ApplicationContext”** before entering any assertions. This is a **test environment startup failure**, which does not by itself prove the test method logic is wrong.

Conversely, a context starting successfully only proves that **the selected set of beans and configuration can be loaded**; it does not yet prove that HTTP mappings, transactions, SQL, and business logic are all correct.

## 3. How does Spring Boot determine which application to load?

If you write:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {
    // ...
}
~~~

and **do not declare `classes = ...`**, Boot needs to find the primary configuration source. By default, it searches **upward from the test's package to parent packages** to find a class annotated with `@SpringBootApplication` or `@SpringBootConfiguration`.

Example:

~~~text
src/main/java/com/acme/shop/ShopApplication.java
    package com.acme.shop;                 @SpringBootApplication

src/main/java/com/acme/shop/order/OrderService.java
    package com.acme.shop.order;           @Service

src/test/java/com/acme/shop/order/OrderServiceIntegrationTest.java
    package com.acme.shop.order;           @SpringBootTest
~~~

A test in `com.acme.shop.order` can find `ShopApplication` in `com.acme.shop`, then load the application's primary configuration, component scanning, and auto-configuration.

**Classic mistake:** placing the test in `com.other.tests` outside the application's package hierarchy, and getting an error like:

~~~text
Unable to find a @SpringBootConfiguration
~~~

Do not fix this by arbitrarily adding `@ComponentScan("...")` or moving every class to the root package. The proper fixes are placing the test in the right package hierarchy **or** explicitly declaring the source:

~~~java
@SpringBootTest(classes = ShopApplication.class)
class OrderServiceIntegrationTest {
}
~~~

This snippet is **illustrative code in a project that has `ShopApplication`**, not a self-compiling file. `classes` tells Boot the primary configuration, but **does not call `ShopApplication.main()` by default**.

### 3.1 What mechanisms does @SpringBootApplication include?

Functionally, `@SpringBootApplication` combines:

- `@SpringBootConfiguration`: marks the primary Spring Boot configuration (built on Spring `@Configuration`).
- `@EnableAutoConfiguration`: enables **conditional** selection of auto-configuration classes.
- `@ComponentScan`: scans components in the appropriate packages.

Which components get loaded depends on **classpath, properties, profiles, conditional annotations, component scan, declared beans, and exclusions/customizations**. Therefore, saying “`@SpringBootTest` loads the entire application” is shorthand: more accurately, it loads an **ApplicationContext based on the full primary configuration according to the conditions effective in the test**. A `@Profile("prod")` bean will not appear if the test profile does not match; an auto-configuration may not create beans if the classpath lacks a dependency.

### 3.2 Nested @Configuration in a test differs from @TestConfiguration

In a Spring Boot test with automatic primary configuration discovery:

- A **nested `@TestConfiguration`** is typically used to **add** test beans alongside the primary configuration.
- A **nested `@Configuration`** directly inside a test can be treated as the primary configuration **instead of** auto-discovering the root app, making the test's bean set different from what you expect.
- If you want to intentionally replace the configuration source, declare `@SpringBootTest(classes = ...)` and clearly understand the selected configuration set.
- With test slices, exclusion and scanning mechanisms behave differently; avoid placing custom `@ComponentScan` on the root app in ways that inadvertently disable slice filtering.

Example of adding a bean for testing (illustrative snippet, requires `Clock` and appropriate imports):

~~~java
@SpringBootTest
class InvoiceTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestClockConfiguration {
        @Bean
        Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2026-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    // @Autowired Clock clock;
}
~~~

`@TestConfiguration` comes from `org.springframework.boot.test.context.TestConfiguration`; `@Bean` is from Spring, while `Clock`/`Instant`/`ZoneOffset` belong to `java.time`. **Do not assume you can declare a bean with the same name as a production bean** when Spring Boot disables bean-definition overriding; if you want to replace a dependency, use qualifiers, profiles, explicit test configuration, or a Spring test bean override compatible with your version.

## 4. Through what phases does SpringApplication prepare the ApplicationContext?

A typical running application has:

~~~java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@SpringBootTest` uses `SpringApplication` to create the context, so the following steps generally apply as well:

1. **Select configuration source:** the discovered root class or the one specified in `classes`.
2. **Prepare Environment:** combines config data, `application.properties`/YAML, profile-specific files, OS env, JVM system properties, and test overrides.
3. **Determine web application type:** based on classpath and `webEnvironment`; Spring MVC may take precedence when both MVC and WebFlux are present.
4. **Create appropriate ApplicationContext:** non-web, servlet, or reactive context depending on configuration.
5. **Load bean definitions:** from `@Configuration`, component scan, imports, and auto-configuration classes.
6. **Evaluate conditions:** e.g., `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` decide which beans are created.
7. **Refresh context:** resolve dependency injection, instantiate eager singletons, run bean lifecycle callbacks, post-processors, AOP proxies, and configured components.
8. **Complete startup lifecycle:** some beans with `@PostConstruct`, listeners, or runners may execute; an HTTP server may be started if the mode requires it.
9. **Hand context to TestContext:** Spring can inject test fields/constructors/parameters and execute test methods.

This is a **logical model**, not a guarantee that every bean is initialized immediately: `@Lazy`, scopes, conditional auto-config, repositories, and clients may defer part of the work. Actual events and callbacks depend on version and configuration.

**Consequence:** using `@SpringBootTest` can cause code **outside `@Test` methods** to run, such as Flyway/Liquibase migrations, scheduler initialization beans, ApplicationRunners, listeners, infrastructure connections, or config checks. Thus “just an empty test” does not mean “zero side effects during context loading”.

### 4.1 Why is @ContextConfiguration not necessarily equivalent?

Spring TestContext can create a plain Spring context using `@ContextConfiguration` and another `ContextLoader`. That is useful when you only want a few Java config or XML beans.

`@SpringBootTest` takes the Boot path to create the context via `SpringApplication`, so **externalized configuration, Boot auto-configuration, logging/bootstrap, and web environment** features follow Boot's mechanism. If the goal is to prove that the Boot application configuration actually starts up, `@SpringBootTest` is usually more suitable than a `@ContextConfiguration` that only loads a few manually declared beans.

However, `@SpringBootTest` is not the fastest choice for every test. Pure Java logic should be unit-tested without Spring; controller slices or persistence slices have their own annotations when you want to limit scope.

## 5. A very common misconception: @SpringBootTest does NOT call main() by default

Because `SpringApplication` is used, many people deduce:

> “When a test has @SpringBootTest, Boot calls `main(String[] args)` and starts up just like running a JAR.”

**Not true by default.** Since Spring Boot 3.x introduced the `useMainMethod` API, the default value is:

~~~java
@SpringBootTest(useMainMethod = SpringBootTest.UseMainMethod.NEVER)
~~~

`NEVER` means **do not call the `main()` method**; instead, use the application class as a source to create `SpringApplication` and run the appropriate bootstrap. Consequently:

- Bean declarations, component scan, and auto-configuration still take effect.
- Custom code you **put exclusively inside `main()`** may not be applied to default tests.
- Do not rely on side effects like `System.setProperty(...)` or a custom `SpringApplicationBuilder` placed solely inside `main()` when testing in the default mode.

If customization inside `main()` is part of the behavior that needs testing, there are two options:

~~~java
@SpringBootTest(
        useMainMethod = SpringBootTest.UseMainMethod.WHEN_AVAILABLE)
class MainMethodWhenPresentTest {
}
~~~

~~~java
@SpringBootTest(
        useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
class MainMethodRequiredTest {
}
~~~

These are **annotation skeletons** and must be placed in a project with an appropriate application class/method. `WHEN_AVAILABLE` invokes `main()` if found, otherwise falls back to standard loading; `ALWAYS` requires `main()` to be present and fails if it cannot be found.

**Design recommendation:** important configuration for the application and tests should live in configuration beans, config data, or hooks with explicit contracts, not hidden inside `main()`. Only choose `useMainMethod = ALWAYS` when the test explicitly aims to verify how `main` customizes `SpringApplication`; check side effects, arguments, and infrastructure enabled by `main`.

## 6. webEnvironment decides mock vs. real server

`@SpringBootTest` has a `webEnvironment` attribute. The default value is **`MOCK`**, but “mock” here refers to the **HTTP/Servlet environment**, not that all services/repositories/controllers become Mockito mocks.

| webEnvironment | Loaded Context | Real HTTP server? | When to use |
| --- | --- | --- | --- |
| `MOCK` (default) | Mock web application context if web stack is present; may fall back to non-web if missing | **No** | Test beans and MVC with `@AutoConfigureMockMvc`, without opening a TCP port |
| `RANDOM_PORT` | Web server application context | **Yes**, automatically picks an available port | Test HTTP from a real client, verify routing/serialization/filters/server |
| `DEFINED_PORT` | Web server application context | **Yes**, configured port or default 8080 | Only when a fixed port is truly needed; prone to CI conflicts |
| `NONE` | Non-web ApplicationContext via SpringApplication | **No** | Test services, configuration, bean wiring without servlet/reactive server |

**`MOCK` does not automatically mean `MockMvc` is available.** In a full-context Spring MVC test, add `@AutoConfigureMockMvc` to auto-configure `MockMvc`. Test slices like `@WebMvcTest` have their own MockMvc configuration mechanism. With Spring Boot 4.x, pay extra attention to module/package changes and do not rely on `@SpringBootTest` bringing MockMvc into the context on its own.

### 6.1 What does RANDOM_PORT mean?

For a servlet application and embedded server, Boot sets `server.port=0` under the random-port test mechanism so the OS picks an available port, and the actual port can be injected via `@LocalServerPort`. The actual port value is known only **after the server binds**; do not hardcode 8080 in this test.

With real HTTP, the client and server running on **two different threads** means a test-managed transaction on the test method does not automatically cover transactions executed while the server handles the request. This point is analyzed in section 11.

### 6.2 MOCK can still test controllers like HTTP requests

`MockMvc` creates mock requests/responses and invokes the MVC stack inside the same application without opening a socket or using a real HTTP client. It can still test mappings, filters, validation, and serialization within the configured scope, but it does not test the full network stack, TLS, reverse proxies, or port configuration of a real server.

### 6.3 WebFlux and having both MVC + WebFlux on the classpath

If only Spring WebFlux is present, Boot can create a reactive web context. When **both Spring MVC and WebFlux** are on the classpath, Spring MVC is normally chosen; to force the test to verify the reactive web type, you can set:

~~~java
@SpringBootTest(
    properties = "spring.main.web-application-type=reactive")
class ReactiveModeTest {
}
~~~

This is an **illustrative annotation snippet**, not a standalone WebFlux test. Appropriate reactive dependencies and handlers are required; merely setting the property does not turn an entire MVC application into a functional reactive application.

## 7. Complete Java 17+ example: observing Boot app loading, profiles, MockMvc, and real HTTP

This lab consists of **one small real application** in `src/main/java` and **three test classes** in `src/test/java`. It requires no database, Docker, external network, or credentials. It uses **Spring Boot 3.5.x, Java 17+, JUnit Jupiter**, and `spring-boot-starter-web`. Examples on Spring Boot 4.x need to verify MVC test packages/modules per the migration guide instead of copying imports from 3.5.

The application has a `GreetingSettings` record bound via config data, a component-scanned `GreetingService`, and a `GreetingController` exposing `GET /greet?name=Lan`. They help tests distinguish “bean exists”, “profile/config binding works”, “mocked MVC”, and “real HTTP server”.

### 7.1 Directory tree

~~~text
src/
  main/
    java/
      example/bootstart/
        DemoApplication.java
        GreetingSettings.java
        GreetingService.java
        GreetingController.java
  test/
    java/
      example/bootstart/
        ContextLoadTest.java
        MockHttpTest.java
        RealHttpTest.java
    resources/
      application-test.properties
~~~

**Note:** the tests are in the **same package** as `DemoApplication` so Boot can automatically locate the root configuration. Omitting `classes` in the annotation is intentional for this exercise, not an oversight.

### 7.2 Root application: DemoApplication.java

~~~java
package example.bootstart;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(GreetingSettings.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` activates component scanning in `example.bootstart` and auto-configuration. `@EnableConfigurationProperties(GreetingSettings.class)` registers/binds the configuration record.

Because `@SpringBootTest` **does not need to call `main()` by default**, the app still starting up in tests demonstrates the difference between **using `SpringApplication` to bootstrap** and **invoking the `main` method itself**.

### 7.3 Configuration record: GreetingSettings.java

~~~java
package example.bootstart;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public record GreetingSettings(String prefix) {
}
~~~

Boot binds `demo.greeting.prefix` from `Environment` into `GreetingSettings.prefix()`. If the test sees this bean has `prefix() == "Hello"`, we know **the configuration was loaded and bound**, not merely sitting as a file in resources.

### 7.4 Real service: GreetingService.java

~~~java
package example.bootstart;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingSettings settings;

    public GreetingService(GreetingSettings settings) {
        this.settings = settings;
    }

    public String greet(String name) {
        return settings.prefix() + ", " + name + "!";
    }
}
~~~

`@Service` is a Spring component. Boot discovers this bean via `@ComponentScan` from the root app, then injects the bound `GreetingSettings`. A unit test could create `new GreetingService(new GreetingSettings("Hello"))`, but this lab aims to prove Boot **actually creates and wires the bean**.

### 7.5 Real controller: GreetingController.java

~~~java
package example.bootstart;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "World") String name) {
        return service.greet(name);
    }
}
~~~

The controller is created by Spring, and the `/greet` mapping is handled by Spring MVC. With `@RestController`, the returned `String` is used as the HTTP response body, not a view name. The example does not add Spring Security or custom filters.

### 7.6 Profile file: application-test.properties

File `src/test/resources/application-test.properties`:

~~~properties
demo.greeting.prefix=Hello
demo.startup.check=from-profile
~~~

`@ActiveProfiles("test")` activates the `test` profile and lets Spring Boot load profile-specific config data. The `demo.startup.check` value is used to demonstrate an override via a test annotation in one test class.

### 7.7 Test 1: ContextLoadTest.java — Boot creates a non-web context

~~~java
package example.bootstart;

import java.util.Arrays;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ActiveProfiles("test")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.startup.check=from-annotation")
@DisplayName("SpringBootTest loads context via SpringApplication")
class ContextLoadTest {

    @Autowired
    ConfigurableApplicationContext context;

    @Autowired
    ApplicationArguments applicationArguments;

    @Autowired
    Environment environment;

    @Autowired
    GreetingSettings settings;

    @Autowired
    GreetingService service;

    @Test
    @DisplayName("Context is active and production beans are wired")
    void contextAndRealBeansAreCreated() {
        assertAll(
                () -> assertTrue(context.isActive()),
                () -> assertNotNull(applicationArguments),
                () -> assertNotNull(context.getBean(DemoApplication.class)),
                () -> assertNotNull(context.getBean(GreetingService.class)),
                () -> assertEquals("Hello, Lan!",
                        service.greet("Lan")));
    }

    @Test
    @DisplayName("Test profile is loaded and test properties are applied")
    void testProfileAndOverrideAreEffective() {
        assertAll(
                () -> assertTrue(Arrays.asList(
                        environment.getActiveProfiles()).contains("test")),
                () -> assertEquals("Hello", settings.prefix()),
                () -> assertEquals("Hello",
                        environment.getRequiredProperty(
                                "demo.greeting.prefix")),
                () -> assertEquals("from-annotation",
                        environment.getRequiredProperty(
                                "demo.startup.check")));
    }
}
~~~

**These two tests prove:**

- The context is actually **refreshed and active**.
- Boot registers components working with `SpringApplication`, including `ApplicationArguments`.
- `DemoApplication` is used as the root configuration even though the test does not specify `classes`.
- The production service is scanned, instantiated, and injected successfully.
- The `test` profile is enabled, and `GreetingSettings` is bound from config data.
- `@SpringBootTest(properties = ...)` supplies a specific test override value.

`webEnvironment = NONE` intentionally does not start an HTTP server: therefore these tests **do not prove the `/greet` endpoint handles requests**.

### 7.8 Test 2: MockHttpTest.java — full context, simulated HTTP with MockMvc

~~~java
package example.bootstart;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@DisplayName("SpringBootTest with MockMvc, without opening a TCP port")
class MockHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    @DisplayName("GET /greet goes through Spring MVC and the real controller")
    void controllerWorksInMockServletEnvironment() throws Exception {
        mvc.perform(get("/greet").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Lan!"));
    }
}
~~~

`MockHttpTest` starts the **full application context** for web MVC, but `MockMvc` creates mock requests/responses and goes through the MVC stack without **opening a real HTTP port**. `@AutoConfigureMockMvc` adds the required configuration; having `@SpringBootTest(webEnvironment = MOCK)` alone should not be assumed to guarantee `MockMvc` availability across all versions.

This differs from `@WebMvcTest(GreetingController.class)`: `@WebMvcTest` is a web-focused **slice** and may require mocking or importing the service; `@SpringBootTest` uses the full application configuration, thus having the real `GreetingService`.

### 7.9 Test 3: RealHttpTest.java — opening an HTTP server on a random port

~~~java
package example.bootstart;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ActiveProfiles("test")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("SpringBootTest starts a real HTTP server")
class RealHttpTest {

    @LocalServerPort
    int port;

    @Test
    @DisplayName("HTTP GET to the real server receives data from the service")
    void realServerHandlesHttpRequest() throws Exception {
        assertTrue(port > 0);

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/greet?name=Lan"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertAll(
                () -> assertEquals(200, response.statusCode()),
                () -> assertEquals("Hello, Lan!", response.body()));
    }
}
~~~

This test uses **`java.net.http.HttpClient` built into Java 17** so it does not depend on a Spring Boot-specific test client. `@LocalServerPort` receives the **real** bound server port. This is a test over the loopback network, verifying the servlet container, HTTP string serialization, and MVC routing.

Its scope is still not production end-to-end: there is no reverse proxy, production TLS, production database, queue, or real mobile client. However, it provides stronger evidence of actual server configuration than mock HTTP.

### 7.10 Gradle and running the example

In a **Spring Boot 3.5.x project with the Gradle plugin and dependency management already configured**, add the appropriate dependencies to `build.gradle` (this snippet is **not a complete build file**):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use Java toolchain 17 or newer. From the module's Gradle root:

~~~bash
./gradlew test
~~~

Or select only the three classes:

~~~bash
./gradlew test --tests example.bootstart.ContextLoadTest \
    --tests example.bootstart.MockHttpTest \
    --tests example.bootstart.RealHttpTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**Expected result in a properly configured environment:** there are **4 tests** (two in `ContextLoadTest`, one in `MockHttpTest`, one in `RealHttpTest`), all PASS. There is no fixed stdout printed by the tests themselves; Gradle may finish with `BUILD SUCCESSFUL` and generate a report under `build/reports/tests/test/index.html`. Spring Boot may print startup logs, so duration/port/log text are **not fixed**.

The configuration may load **multiple contexts** because the three test classes choose different `webEnvironment` values. Do not infer “four tests = four startups” because caching and context keys determine how many contexts are actually created.

## 8. Reading the exact meaning of each test

| Test Type | Execution Context | Evidence | Does Not Prove by Itself |
| --- | --- | --- | --- |
| Plain Java unit test | No Spring context | Algorithm/branches of a class | Bean wiring, profiles, auto-config |
| `@SpringBootTest(NONE)` | Non-web Boot context | Component scan, DI, config binding, service startup | HTTP routing or server |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Boot MVC context + mock request | Mapping, controller, validation, filters in test config | TCP binding, TLS, network stack |
| `@SpringBootTest(RANDOM_PORT)` | Boot context + real server | HTTP request/response over loopback, servlet server | Full production environment |
| `@WebMvcTest` | Web slice | Controller/MVC and provided collaborators | All real services/repositories in the app |
| `@DataJpaTest` | Persistence slice | Entity mapping/repository and slice-configured DB | Full HTTP/service workflow |

**Do not default to the biggest annotation possible.** Choose the smallest level that still includes all components where a bug could reside. `@SpringBootTest` is especially valuable when verifying *Boot configuration of the whole application or cross-layer interactions*, not when merely testing `calculateTax(...)`.

## 9. Which auto-configurations does @SpringBootTest load?

`@EnableAutoConfiguration` does not mean “all starters enable all features”. Boot uses **conditional configuration**:

- A class must be on the classpath to select configurations depending on it (`@ConditionalOnClass`).
- Properties must match to enable a feature (`@ConditionalOnProperty`).
- If the application already defines a given bean, Boot can **back off** (`@ConditionalOnMissingBean`).
- Profiles, resources, existing beans, and other framework conditions also affect selection.

With `spring-boot-starter-web` and an MVC classpath, Boot typically loads auto-configurations related to servlet MVC, JSON, message converters, and the server when `webEnvironment` requires it. If a test uses `NONE`, it can still create application beans and non-web configurations, but it will not start a server.

### When investigating why a bean does not appear

In an appropriate test context:

~~~java
@Autowired
ApplicationContext context;

// Inside a @Test method:
assertTrue(context.containsBean("greetingService"));
~~~

This is only an **illustrative snippet inside a test class**, requiring imports for `ApplicationContext`, `@Autowired`, and JUnit assertions. The default name `greetingService` comes from `@Service` on the example's `GreetingService` class; if the bean name changes, the assertion must be adjusted.

When startup fails due to auto-configuration, you can enable condition logging for the test:

~~~java
@SpringBootTest(properties = "debug=true")
class AutoConfigurationDebugTest {
    // Only use when diagnosing, avoid overly verbose logs routinely.
}
~~~

In some cases, the **Condition Evaluation Report** helps distinguish which auto-configurations matched or did not match. Do not confuse “missing dependency”, “inactive profile”, or “conditional property false” with `@SpringBootTest` failing to run auto-configuration.

**Regarding external resources like databases:** context loading can trigger datasources, migrations, or connections if dependencies/config require them. `@SpringBootTest` by itself **does not start a PostgreSQL Docker container**, nor does it **automatically pick H2** just because it is running in a test. You must explicitly configure a test datasource, Testcontainers/`@ServiceConnection`, or a mock adapter matching your goal. Avoid letting tests accidentally connect to a production DB.

## 10. When are test properties, profiles, and dynamic properties applied?

### 10.1 @ActiveProfiles and application-test.properties

~~~java
@ActiveProfiles("test")
@SpringBootTest
class CheckoutIntegrationTest {
}
~~~

This annotation pair tells TestContext to select the `test` profile and Boot to load matching profile config data (such as `application-test.properties`), but **`@ActiveProfiles` does not guarantee every property in the profile file beats all other sources**. Test inline properties, dynamic property sources, system properties, and environment variables can override it according to their respective precedence order.

In tests, verify profiles via:

~~~java
@Autowired Environment environment;

// Inside a @Test method:
assertTrue(Arrays.asList(
        environment.getActiveProfiles()).contains("test"));
~~~

This is illustrative code; it requires imports for `Arrays`, `Environment`, `@Autowired`, assertions, and JUnit. **Do not just check the `spring.profiles.active` string** and conclude whether TestContext has activated the profile.

### 10.2 @SpringBootTest(properties = ...)

Use when you need a few fixed overrides for a test class:

~~~java
@SpringBootTest(properties = {
    "demo.greeting.prefix=Hello",
    "spring.main.banner-mode=off"
})
class GreetingPropertiesTest {
}
~~~

These keys are injected into the test context; they can override standard file configurations. If a test has `@TestPropertySource` or `@DynamicPropertySource` supplying the **same key**, do not guess based on annotation order in source code: consult the precedence documentation for your exact version and verify the final value via `Environment`/beans.

### 10.3 @DynamicPropertySource and Testcontainers

When an endpoint is runtime data (container/HTTP stub port), it cannot be completely hardcoded in a file:

~~~java
@DynamicPropertySource
static void externalConfig(DynamicPropertyRegistry registry) {
    registry.add("demo.remote.base-url",
            () -> "http://127.0.0.1:19090");
}
~~~

This is an **illustrative method snippet**; it does not declare a server on port 19090 and is not a standalone test file. `@DynamicPropertySource` declares a `static` method accepting `DynamicPropertyRegistry` to register property-returning suppliers. With Testcontainers, the supplier can reference a method fetching the JDBC URL or mapped port from a lifecycle-managed container.

**Important:** `@SpringBootTest` does not automatically start containers just because `@DynamicPropertySource` is present; you still have to configure and manage the container or the corresponding service connection mechanism.

When Boot provides `ConnectionDetails` from `@ServiceConnection`, the final client bean can use that connection source. Reading `spring.datasource.url` alone from `Environment` **is not enough** to prove which database the real datasource is connecting to. Check the bean and connection metadata if that is the test's goal.

## 11. Transactions: why doesn't RANDOM_PORT roll back data like MOCK?

Spring TestContext can manage a **test transaction** when a `@Transactional` test method/class is properly configured with a transaction manager. By default, a test-managed transaction is usually rolled back after the test.

However, with `@SpringBootTest(webEnvironment = RANDOM_PORT)` or `DEFINED_PORT`:

~~~text
Test thread                         Server HTTP thread
  |
  | @Transactional test             Spring MVC handler
  |    opens test transaction T1         |
  |                                      v
  +---- HTTP request ----------------> Service @Transactional
  |                                      |
  |                                      +-- transaction T2
  |                                      +-- commit (if successful)
  |
  +---- HTTP response
  |
  +-- rollback T1
      (DOES NOT roll back data committed by T2)
~~~

The test thread and the HTTP server thread run on different threads and transactions; rolling back T1 **does not automatically reverse** the server-side transaction. In real tests, transaction propagation, databases, and error handling may vary, but **never assume an HTTP call runs inside the calling thread's test-managed transaction**.

With `MockMvc`, requests may execute synchronously on the same test thread in typical cases, allowing some transaction contexts to continue applying. However, it still depends on async dispatch, propagation, and framework wiring; verify specific behavior rather than claiming “every MockMvc test rolls back every side effect”.

**Solutions when real HTTP writes data:**

1. Use a dedicated database for testing, never production data.
2. Clean up state intentionally between tests (SQL scripts/fixture cleanup, isolated schemas, sensible transactional APIs), or initialize database containers according to a suite strategy.
3. Verify observable conditions after the request; do not infer “the test passed/rolled back so the DB is clean”.
4. For Kafka/email/HTTP side effects, use fake/mock servers or isolated data and separate cleanup.

This is one of the most important differences between **“loading the real app”** and **“every operation running inside the test's transaction”**.

## 12. Context caching: does @SpringBootTest restart before every @Test?

**Usually no.** Spring TestContext maintains an **ApplicationContext cache** within the same test process. For test classes with equivalent context configurations, the framework can reuse the context instead of restarting.

Factors contributing to the cache key include:

- Configuration classes/locations and context loader.
- Active profiles from `@ActiveProfiles`.
- Inline properties and test property source locations.
- Context customizers: e.g., dynamic properties, bean overrides, test customizations.
- Parent context, initializers, and certain web context settings.
- Boot options related to context type, such as `webEnvironment`.

Therefore, two classes both annotated with `@SpringBootTest` are **not guaranteed** to share the same context. If one class uses `NONE` and another uses `RANDOM_PORT`, they must initialize different environment types. If two classes have the same configuration, the context can be reused.

### 12.1 Caching explains “single test passes, full suite fails”

A mutated singleton bean, in-memory repository, static state, queue, mutable cache, or shared container can leave data behind from an earlier test. The context cache **does not reset the entire application before each method**.

Solutions:

- Create explicit test fixtures and intentional cleanup.
- Do not let tests depend on execution order or state from a previous class.
- For databases, isolate data and manage transactions/cleanup appropriately.
- Only use `@DirtiesContext` when the context has genuinely been dirtied and must be recreated; doing so slows down the suite.
- Avoid unnecessary differences in inline test properties/bean overrides across dozens of classes because each distinct configuration can cause a cache miss.

### 12.2 How to measure how many times the context loads?

Enable TestContext cache logging in the test environment:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

In Gradle/IDEs, depending on logging configuration, you can observe context cache hits/misses/size. Results can be affected when tests run across **multiple JVMs/forks**: the static cache is not automatically shared across processes. Do not assert exact context load counts inside business unit tests.

**Biggest optimization:** move pure logic to unit tests, replace full-context tests with slices when scope suffices, group integration tests that share the same test context configuration, avoid excessive `@DirtiesContext`, and limit unnecessary external dependencies.

## 13. @SpringBootTest vs. other testing approaches: choosing the right scope

| Need | Usually Appropriate Tool | Why |
| --- | --- | --- |
| Compute values, validate input, pure Java rules | JUnit Jupiter + Mockito/fake | No need to create a Spring context; fast and isolated |
| Test a few Java config beans without Boot auto-config | `@ContextConfiguration` or `ApplicationContextRunner` | Loads a small scope, selects specific beans |
| Test controller mapping/validation/filters, mock service | `@WebMvcTest` + override/mock required collaborators | Web slice, fewer beans than full Boot |
| Test JPA mappings/repositories/queries | `@DataJpaTest` and appropriate DB | Persistence slice; requires understanding test DB/rollback |
| Test JSON serialization | `@JsonTest` when appropriate | Targets JSON layer instead of full app |
| Test wiring, profiles, auto-config, multi-layer services | `@SpringBootTest(NONE/MOCK)` | Close to real app configuration, without necessarily starting a server |
| Test HTTP/TCP/request serialization via embedded server | `@SpringBootTest(RANDOM_PORT)` | Real server and client |
| Test contract with real PostgreSQL/Kafka/Redis | Spring integration test + Testcontainers/real service | Mocks/fakes do not prove real protocol or transactions |

**A common misconception:** writing `@SpringBootTest` does not mean “the integration test will always test the database too”. If the SUT injects a mocked repository, you still have not tested SQL. Conversely, pure service tests can cover business logic very well without Spring Boot. Test scope is determined by **which collaborators are real vs. fake** and what environment is loaded.

## 14. Failures when @SpringBootTest cannot load the application

### 14.1 Cannot find @SpringBootConfiguration

**Symptom:** message “Unable to find a `@SpringBootConfiguration`”.

**Common cause:** the test package is not under the app package or the configuration source is unclear.

**Fix:** place the test in the proper package, or specify `@SpringBootTest(classes = DemoApplication.class)`. Do not configure unlimited package scanning just to patch a placement error.

### 14.2 “Failed to load ApplicationContext” caused by a failing bean

This is a generic wrapper message. Read the **root cause** at the bottom of the exception chain: `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, `BeanCreationException`, property binding errors, or datasource connection failures. These causes differ and need separate fixes.

For example, a production bean requires `DataSource` but the test lacks a JDBC URL/driver; Boot may fail during auto-config before the test method runs. Do not disable all auto-config just to force a smoke test to PASS if the goal is to verify production configuration.

### 14.3 Test has @SpringBootTest but @Autowired is null

Check that the test runs with **JUnit Jupiter**, importing `org.junit.jupiter.api.Test`, JUnit Platform, and extension integration. If you instantiate the test class manually with `new` or call methods outside the test runner, `@Autowired` has no opportunity to be injected by Spring TestContext.

In standard JUnit Jupiter, `@SpringBootTest` already pulls in `SpringExtension`; no need to repeat `@ExtendWith`.

### 14.4 Controller test returns 404 or lacks MockMvc

With `MOCK`, `@AutoConfigureMockMvc` is required in a full-context MVC test. If it still returns 404, check whether the controller is within component scan, what the mapping is, whether profiles/security/filters block the request, and whether the app uses MVC or WebFlux.

A `@SpringBootTest(webEnvironment = NONE)` has no HTTP server, so you cannot call port 8080 and expect a response from the test context.

### 14.5 RANDOM_PORT is not 8080

Do not hardcode `localhost:8080`. Use `@LocalServerPort` (or an appropriate auto-configured client) to obtain the actual port. `DEFINED_PORT` can collide with a port already used by another service in CI.

### 14.6 A bean with @Profile("prod") does not appear in tests

If the test enables `@ActiveProfiles("test")`, beans restricted to the `prod` profile are not created (unless other conditions change the logic). This is expected Spring behavior. Verify active profiles via `Environment.getActiveProfiles()`, not merely by checking file names.

### 14.7 Custom code in main() does not run in tests

Because `useMainMethod=NEVER` is the default. Move valid configuration into beans/config data/hooks, or select `WHEN_AVAILABLE`/`ALWAYS` when testing `main` is required. Do not alter code just to force tests to call `main` in every case.

### 14.8 Tests unexpectedly call production infrastructure

The root context can instantiate email clients, schedulers, migrations, data sources, and listeners. Use test profiles, fake gateways, Testcontainers, service stubs, or explicit disable flags. **Never put production credentials into test properties**.

### 14.9 Context loads very slowly or suite uses excessive RAM

Often caused by an overly broad context, database/container startup, numerous cache keys, or `@DirtiesContext`. Measure startup time, profile bean init, cache hits, and reasons configs differ across classes; pick unit/slice tests when sufficient.

### 14.10 @Mock does not replace a production bean in ApplicationContext

A Mockito `@Mock` on a test field does not automatically replace the bean Spring injects into a service. For Spring Boot 3.4+/Spring Framework 6.2, `@MockitoBean`/`@MockitoSpyBean` are available in Spring TestContext; Boot 3.3 and earlier typically use Boot's `@MockBean`/`@SpyBean`. Choose the annotation matching your version and clearly identify which component needs mocking.

### 14.11 Spring Boot 4.x and test imports differ from Boot 3.x

The TestContext/SpringApplication architecture and the four web environment modes remain meaningful, but **modules and packages of several test utilities** changed in Boot 4.x (e.g., MVC/test clients). The source files in section 7 are written intentionally for **Boot 3.5.x**. When upgrading to Boot 4.x, follow the migration guide and import the right artifacts; do not claim 3.5 examples can copy imports verbatim to every 4.x release.

### 14.12 @Transactional on a real HTTP test does not clean the database

Client and server run on separate threads, so rolling back the test-managed transaction on the client thread does not cover server transactions. Use an isolated test DB and clean up state per contract, rather than relying on an illusory rollback.

## 15. Process to verify a valuable @SpringBootTest

When writing a new full-context test, follow this order:

1. **State the test goal:** “The application starts and binds configuration properly”, “controller handles requests”, or “repository writes to real PostgreSQL”?
2. **Choose root configuration:** ensure the test sits in the right package hierarchy or specify `classes`, without accidentally replacing configuration via nested `@Configuration`.
3. **Choose webEnvironment:** `NONE` for non-web wiring, `MOCK` for MockMvc, `RANDOM_PORT` for real HTTP, `DEFINED_PORT` only when a fixed port is mandatory.
4. **Determine profiles and properties:** `@ActiveProfiles`, config data, `@SpringBootTest(properties)`, `@TestPropertySource`, `@DynamicPropertySource` as needed.
5. **Identify which beans are real:** logic, controller, repository, database, HTTP client, broker. Use fakes/mocks right at boundaries so tests do not touch production.
6. **Run the context the first time:** read the root cause if startup fails, do not stop at the generic “Failed to load ApplicationContext” message.
7. **Assert bound configuration and observable behavior:** active `ApplicationContext`, bean presence, valid `ConfigurationProperties`, HTTP status/body, or database state.
8. **Check side effects and transactions:** especially with real servers, schedulers, listeners, migrations, and asynchronous tasks.
9. **Monitor timing/context cache:** avoid unnecessary differences across test classes, do not reset the context when only fixture cleanup is needed.
10. **Split tests once scope is clear:** pure rules → unit; MVC → slice or MockMvc; real network/DB → integration with test resources.

### Pre-commit checklist

- [ ] Understand `@SpringBootTest` creates `ApplicationContext` via `SpringApplication`, not merely by running `main()`.
- [ ] Use JUnit Jupiter with proper imports and Spring TestContext, without arbitrarily mixing JUnit 4 runners.
- [ ] Know where the root `@SpringBootConfiguration` is discovered or specified.
- [ ] Understand `@SpringBootApplication` includes configuration, auto-configuration, and component scan; auto-config is conditional.
- [ ] Select the right `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, or `NONE`.
- [ ] If using MockMvc in a full-context Spring MVC test, include `@AutoConfigureMockMvc`.
- [ ] If using real HTTP, obtain the actual port instead of hardcoding; do not rely on test-thread rollback.
- [ ] Test properties, active profiles, and dynamic properties do not accidentally point to production infrastructure.
- [ ] Include assertions on beans/config/behavior, not just an empty test method.
- [ ] Do not expect `@SpringBootTest` to automatically start DB/Kafka containers or replace beans via Mockito `@Mock`.
- [ ] Account for startup hooks, side effects, context caching, and cleanup between test methods.
- [ ] Verify Spring Boot version when using `useMainMethod` API or Boot 4.x test modules.

**Conclusion:** `@SpringBootTest` creates an **application context using Spring Boot's mechanism** via Spring TestContext collaborating with `SpringBootContextLoader` and `SpringApplication`. It locates the primary configuration, loads config/profiles, creates beans and applies conditional auto-configuration, and lets tests interact with the initialized context. **By default it does not call `main()` and does not open a real HTTP server.** Whether there is a server, what web context type is used, and the scope of evidence depend on `webEnvironment` and the real/fake dependencies wired into the test.

### Official reference documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): SpringApplication in tests, primary configuration discovery, four `webEnvironment` modes, transactions, and context cache.
- [Spring Boot 3.5 — Use the Main Method](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `useMainMethod` and how it differs from invoking `main`.
- [Spring Boot API — @SpringBootTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html): `classes`, `properties`, `args`, `webEnvironment`, and `useMainMethod`.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): test context mechanics, injection, and lifecycle.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys, context reuse, and `@DirtiesContext`.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): config data, profile-specific sources, and properties.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource` for runtime resources.
- [Spring Boot 4.0 Migration Guide — Testing](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): changes to test modules and APIs when upgrading from Boot 3.x to 4.x.
