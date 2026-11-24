# MockMvc: standaloneSetup vs. webAppContextSetup

When testing Spring MVC in a Spring Boot application, `MockMvc` lets you send **simulated requests** into the MVC processing pipeline and verify HTTP status, headers, response body, exception handlers, binding, and validation **without starting an HTTP server on a real network port**. However, how you construct `MockMvc` determines how much Spring MVC configuration is actually being verified.

Two setup approaches must be distinguished:

- **`MockMvcBuilders.standaloneSetup(controller)`**: provides the controller instance directly, optionally passing a mock or fake service via constructor; builds MVC test infrastructure with default configuration and customizations declared in code. **Does not load the application's `ApplicationContext`.**
- **`MockMvcBuilders.webAppContextSetup(webApplicationContext)`**: obtains beans and MVC configuration from a `WebApplicationContext` loaded by Spring TestContext. **Has an `ApplicationContext`**, enabling verification of components, interceptors, exception handlers, converters, and bean wiring defined in *the loaded test context*.

The difference is not just execution time. A `standaloneSetup` test can pass even if the application forgot to register a `HandlerInterceptor` or `@ControllerAdvice`; a `webAppContextSetup` test can catch that discrepancy if the configuration is actually included in the `WebApplicationContext`. Conversely, standalone tests are useful for quickly testing a single controller without depending on a datasource, component scanning, or unrelated auto-configuration.

**Rule of thumb:** use **the narrowest configuration that still provides sufficient evidence** for the contract you want to protect.

## 1. Which Path Does MockMvc Test?

With servlet-based Spring MVC, the general flow when calling `mockMvc.perform(...)` is:

```text
JUnit Jupiter test
       |
       v
MockMvc.perform(MockHttpServletRequest)
       |
       v
Spring MVC DispatcherServlet (mock servlet environment)
       |
       +-- HandlerMapping / HandlerAdapter
       +-- argument binding / validation / converters
       +-- controller (and provided dependencies)
       +-- HandlerExceptionResolver / @ControllerAdvice
       +-- interceptors, filters if registered
       |
       v
MockHttpServletResponse
       |
       v
status(), header(), content(), jsonPath(), ...
```

MockMvc **uses real MVC infrastructure** to handle simulated requests rather than simply calling a Java method directly on the controller. Even so, it **does not open a network socket**, and it does not measure TLS, reverse proxies, runtime servlet container differences, or real HTTP clients/connections.

MockMvc is intended for **Spring Web MVC (servlet stack)**. For reactive **Spring WebFlux** controllers, look at `WebTestClient` and `@WebFluxTest` instead of assuming MockMvc is the default for both application types.

Common checks:

- `status().isOk()` or `status().isBadRequest()`: HTTP status produced by MVC.
- `content().string(...)`: text body.
- `jsonPath("$.id").value(...)`: a field in JSON if the response uses JSON.
- `header().string(...)` or `header().doesNotExist(...)`: header values.
- Checking request parameters, path variables, media types, exception mapping, HTTP filters, and authentication when configured.

**Distinguish clearly:** MockMvc can verify interactions between a controller and a real service if the context supplies the real service. If you attach a mock to the service, assertions no longer prove that the service/business logic/DB works; they only prove the MVC contract against the stubbed response.

## 2. Comparison Table: standaloneSetup vs. webAppContextSetup

| Criterion | `standaloneSetup(...)` | `webAppContextSetup(...)` |
| --- | --- | --- |
| How controller is provided | Directly specified instance, often `new Controller(fakeService)` | Controller bean from `WebApplicationContext` |
| Loads a Spring ApplicationContext? | **No** | **Yes** |
| Runs MVC request dispatching? | Yes | Yes |
| Real bean wiring/component scanning | Not verified automatically | Verified within the loaded context scope |
| Application's global `@ControllerAdvice` | Not read from context automatically; call `setControllerAdvice(...)` if needed | Discovers advice beans in the context |
| Application's custom interceptors/formatters/converters | Not pulled from the app's `WebMvcConfigurer` automatically; configure via builder | Uses MVC infrastructure configured by the context |
| Servlet filters / Spring Security | Only filters added via the corresponding builder/configurer | Can attach the filter chain from the context; check builder/test config |
| Speed/isolation | Usually fast, easy to pinpoint failures | Incurs context startup cost, though TestContext caches contexts |
| Best suited for | Controller logic, routing, basic binding, fast debugging | MVC wiring/config, global advice, interceptors, converters, security with proper context |
| What it cannot prove | That the app registers production MVC beans properly | Real HTTP sockets; also DB/network if dependencies remain mocked |

**Do not equate `webAppContextSetup` with `@SpringBootTest`.** A `WebApplicationContext` can come from a small `@SpringJUnitWebConfig`, `@WebMvcTest`, or `@SpringBootTest`. The *builder* determines where MockMvc gets its MVC infrastructure from; the *test configuration* determines **how broad the context is**.

## 3. Setup Mechanics: Who Creates the Controller, Who Supplies MVC Infrastructure?

### 3.1. Standalone Setup

Minimal pattern:

```java
GreetingService service = name -> "Hello, " + name + "!";
GreetingController controller = new GreetingController(service);

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(controller)
        .build();
```

This is a **snippet inside a test method**, depending on classes defined in the example section. Here the test constructs the controller itself and passes the collaborator through the constructor. The builder initializes `DispatcherServlet` and the MVC components required for request handling in test scope, but **does not load the application's MVC configuration**.

If the application has a global exception handler, interceptor, custom `ObjectMapper`, or validator, the standalone builder **does not automatically discover all production configuration**. You can add them intentionally:

```java
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new GreetingAdvice())
        .addInterceptors(customInterceptor)
        .build();
```

This is an illustrative snippet (`customInterceptor` must be defined), not a complete standalone Java file. The `StandaloneMockMvcBuilder` API also offers ways to customize message converters, argument resolvers, conversion service, validator, view resolvers, exception resolvers, and more as needed.

**Trade-off:** manual configuration keeps tests fast and explicit, but if production changes its custom MVC configuration and the test forgets to update, the standalone test can continue passing. That is not a bug in MockMvc; it is a **limit of the test evidence**.

### 3.2. WebApplicationContext Setup

Pattern requiring a `WebApplicationContext` managed by Spring TestContext:

```java
@Autowired
WebApplicationContext webApplicationContext;

@BeforeEach
void initMockMvc() {
    mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .build();
}
```

This snippet lives inside a **Spring test class**, requires a `mockMvc` field and imports, and will not run standalone without annotations/config that load a `WebApplicationContext`. The builder uses the MVC infrastructure and beans in the active context.

**Web context breadth depends on how it is loaded:**

- `@SpringJUnitWebConfig(TestMvcConfig.class)`: creates a web context from the specified configuration; suitable when verifying specific MVC wiring without loading all of Boot.
- `@WebMvcTest(ExampleController.class)`: Spring Boot MVC slice; you can typically `@Autowired MockMvc` directly, though underneath it still uses the slice's `WebApplicationContext`.
- `@SpringBootTest` + `@AutoConfigureMockMvc`: broader context with Boot configuring `MockMvc`; suitable when verifying multiple production beans coordinating with HTTP MVC. `@AutoConfigureMockMvc` belongs to Spring Boot test auto-configuration and its import path may vary across versions.

If the goal is controller routes/JSON inside a web slice, injecting the ready-made `MockMvc` from `@WebMvcTest` is usually cleaner than calling `webAppContextSetup` manually. Calling the builder yourself is helpful to understand where configuration comes from or to explicitly add a `MockMvcConfigurer`.

### 3.3. Same URL, Different MVC Configuration

Suppose a system has an interceptor that adds the header `X-App-Interceptor: enabled` to every request.

- Calling the controller via `standaloneSetup` **does not automatically bring** the interceptor from app config → the response **lacks** that header unless the test calls `addInterceptors(...)`.
- Going through `webAppContextSetup` with a context containing `WebMvcConfigurer.addInterceptors(...)` → the header **appears**.
- If the created web context **does not include** the `WebMvcConfigurer` you intend to verify, context setup will not reveal the expected header either. You must load **the right configuration**.

The runnable example below proves this difference with **two passing test suites** whose assertions match their respective boundaries.

## 4. Runnable Java 17+ Example: Controller, Advice, and Interceptor

We build an endpoint `GET /greetings?name=Ada` returning the text `Hello, Ada!`. Name-formatting logic lives in plain Java so it can be checked independently. When the name is empty or whitespace-only, the service throws `IllegalArgumentException`; `@RestControllerAdvice` maps it to HTTP 400.

The `WebApplicationContext` configuration also installs an interceptor that writes the header `X-App-Interceptor: enabled`. The standalone test does not install the interceptor, demonstrating that this builder does not automatically load the application's `WebMvcConfigurer`.

**Files:**

```text
src/
├── main/java/example/testing/mockmvc/
│   ├── GreetingText.java
│   ├── GreetingTextDemo.java
│   ├── GreetingController.java
│   └── GreetingAdvice.java
└── test/java/example/testing/mockmvc/
    ├── GreetingStandaloneTest.java
    └── GreetingWebContextTest.java
```

### 4.1. Plain Java Logic: GreetingText.java

Create `src/main/java/example/testing/mockmvc/GreetingText.java`:

```java
package example.testing.mockmvc;

public final class GreetingText {
    private GreetingText() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

`String.isBlank()` and `strip()` have been available since Java 11; the project uses Java 17+. They distinguish strings with no meaningful characters from strings with surrounding whitespace. This lesson intentionally keeps the plain logic small and avoids database/remote API dependencies to stay focused on MVC setup.

### 4.2. Real Controller: GreetingController.java

Create `src/main/java/example/testing/mockmvc/GreetingController.java`:

```java
package example.testing.mockmvc;

import java.util.Objects;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = Objects.requireNonNull(
                service, "service");
    }

    @GetMapping(
            path = "/greetings",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greet(@RequestParam("name") String name) {
        return service.greet(name);
    }
}

@FunctionalInterface
interface GreetingService {
    String greet(String name);
}
```

The Java file has one `public` top-level type `GreetingController`; the `GreetingService` interface is package-private. Both tests sit in package `example.testing.mockmvc`, so they can access this interface. If a larger project needs adapters in other packages, extract the interface into an appropriate `public` file.

We do not put `@Service` on `GreetingService` because it is just an interface. In the standalone test, we pass a lambda directly. In the web context test, Spring creates the `GreetingService` bean via `@Bean`. **Same production controller, two ways of supplying the collaborator**, so the tests genuinely compare the two builders.

### 4.3. Exception Handler: GreetingAdvice.java

Create `src/main/java/example/testing/mockmvc/GreetingAdvice.java`:

```java
package example.testing.mockmvc;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GreetingAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> badName(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .contentType(MediaType.TEXT_PLAIN)
                .body(exception.getMessage());
    }
}
```

`GreetingAdvice` is a real class with Spring annotations. **In standalone mode**, the test must register it explicitly via `setControllerAdvice(new GreetingAdvice())`. **In web context mode**, the test registers it as a Spring bean so the MVC exception resolver discovers it.

Do not assume every exception defaults to HTTP 400. If `IllegalArgumentException` from the service is not caught by an `@ExceptionHandler` or appropriate handler mechanism, it may bubble up and cause `MockMvc.perform(...)` to throw an exception, or be handled differently depending on configuration. Tests should verify the exact exception mapping you want to protect.

### 4.4. Complete Standalone Test

Create `src/test/java/example/testing/mockmvc/GreetingStandaloneTest.java`:

```java
package example.testing.mockmvc;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GreetingStandaloneTest {
    private MockMvc mvc;

    @BeforeEach
    void setup() {
        GreetingService service = GreetingText::greet;
        GreetingController controller =
                new GreetingController(service);

        mvc = MockMvcBuilders
                .standaloneSetup(controller)
                .setControllerAdvice(new GreetingAdvice())
                .build();
    }

    @Test
    void returnsTextWithoutApplicationInterceptor()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " Ada "))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Ada!"))
                .andExpect(header()
                        .doesNotExist("X-App-Interceptor"));
    }

    @Test
    void mapsBlankNameWithExplicitlyRegisteredAdvice()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " "))
                .andExpect(status().isBadRequest())
                .andExpect(content()
                        .string("name must not be blank"));
    }
}
```

**Two test points:**

1. The real controller and real `GreetingText` run through `MockMvc`, returning trimmed content as required; the interceptor header **does not exist** because the test has not registered that interceptor.
2. With a single space parameter, the logic throws `IllegalArgumentException`. Because the test called `setControllerAdvice(...)`, MVC converts the exception into **400 + text message**. This proves the handler was registered *in the test's own setup*; it **does not prove production has an advice bean**.

This test **does not use** `@SpringBootTest`, `@WebMvcTest`, `@SpringJUnitWebConfig`, or `@Autowired`. There is no Spring `ApplicationContext`, yet it still uses Spring MVC test infrastructure.

### 4.5. Complete WebApplicationContext Test

Create `src/test/java/example/testing/mockmvc/GreetingWebContextTest.java`:

```java
package example.testing.mockmvc;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringJUnitWebConfig(GreetingWebContextTest.WebConfig.class)
class GreetingWebContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mvc;

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void appliesInterceptorDefinedInWebContext()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " Ada "))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Ada!"))
                .andExpect(header()
                        .string("X-App-Interceptor", "enabled"));
    }

    @Test
    void discoversAdviceBeanAndAppliesInterceptor()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " "))
                .andExpect(status().isBadRequest())
                .andExpect(content()
                        .string("name must not be blank"))
                .andExpect(header()
                        .string("X-App-Interceptor", "enabled"));
    }

    @Configuration(proxyBeanMethods = false)
    @EnableWebMvc
    static class WebConfig implements WebMvcConfigurer {

        @Bean
        GreetingService greetingService() {
            return GreetingText::greet;
        }

        @Bean
        GreetingController greetingController(
                GreetingService service) {
            return new GreetingController(service);
        }

        @Bean
        GreetingAdvice greetingAdvice() {
            return new GreetingAdvice();
        }

        @Override
        public void addInterceptors(
                InterceptorRegistry registry) {
            registry.addInterceptor(new HandlerInterceptor() {
                @Override
                public boolean preHandle(
                        HttpServletRequest request,
                        HttpServletResponse response,
                        Object handler) {
                    response.setHeader(
                            "X-App-Interceptor", "enabled");
                    return true;
                }
            });
        }
    }
}
```

**Why does this work with Spring Framework 6.x / Spring Boot 3.x?**

- `@SpringJUnitWebConfig` integrates Spring TestContext with JUnit Jupiter and configures a web application context.
- `@EnableWebMvc` brings MVC infrastructure into the test context. `WebConfig implements WebMvcConfigurer` to configure the interceptor.
- `@Bean GreetingController` supplies the **real controller bean**; `@Bean GreetingAdvice` supplies the **global exception advice bean**; `@Bean GreetingService` wires the service into the controller.
- `MockMvcBuilders.webAppContextSetup(webApplicationContext)` picks up that context's MVC configuration rather than assembling a disconnected controller.
- `HandlerInterceptor.preHandle(...)` adds the header to the response before the controller runs. When the blank-name error is turned into HTTP 400 by the advice, the interceptor has still run, so the header still appears.

Here the servlet imports use the **`jakarta.servlet.*`** namespace (Spring Framework 6 / Boot 3+) rather than `javax.servlet.*` from older Spring generations. If you are on Spring Framework 7 / Spring Boot 4, the builder semantics remain the same, though you must keep dependencies/Jakarta Servlet and test plugins compatible with your version.

**Important note:** the context in the example loads only the `WebConfig` declared by the test. It verifies **this `WebConfig` configuration**; it does not automatically prove that the production application has the same interceptor, advice, and service wiring. If you want to test production configuration, load the corresponding application config/profiles using an appropriate test slice or full integration test.

### 4.6. Configuring Dependencies and Running Tests

In a **Spring Boot 3.4/3.5 + Java 17+** project that already has the plugin and dependency management, the relevant part in `build.gradle` (Groovy DSL) is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additional configuration snippet**, not a standalone `build.gradle`. `spring-boot-starter-web` provides Spring MVC and compatible servlet APIs; the test starter in standard setups provides JUnit Jupiter along with Spring Test.

Run the two test classes separately:

```bash
./gradlew test --tests example.testing.mockmvc.GreetingStandaloneTest
./gradlew test --tests example.testing.mockmvc.GreetingWebContextTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.mockmvc.GreetingStandaloneTest"
.\gradlew.bat test --tests "example.testing.mockmvc.GreetingWebContextTest"
```

**Expected result:** each class has **2 test methods**, for a total of **4 tests** passing when the project and dependencies are properly configured. Standalone tests do not create an `ApplicationContext`; web-context tests create a small web context. Do not rely on fixed Gradle stdout because runners, plugins, and logging configuration may format output differently.

If `GreetingWebContextTest` reports a missing bean, check `@SpringJUnitWebConfig(WebConfig.class)`, `@Bean`, and package visibility. If the context reports missing MVC infrastructure, check `@EnableWebMvc`. If status/headers are wrong, inspect the actual interceptor/advice classes loaded by the context.

### 4.7. Running the Plain Java Logic with javac/java

This example has one Spring-independent part: `GreetingText`. Create `src/main/java/example/testing/mockmvc/GreetingTextDemo.java`:

```java
package example.testing.mockmvc;

public class GreetingTextDemo {
    public static void main(String[] args) {
        System.out.println(GreetingText.greet(" Ada "));

        try {
            GreetingText.greet(" ");
        } catch (IllegalArgumentException e) {
            System.out.println(e.getMessage());
        }
    }
}
```

Compile and run from the project root directory (requires JDK 17+):

```bash
javac -d out src/main/java/example/testing/mockmvc/GreetingText.java src/main/java/example/testing/mockmvc/GreetingTextDemo.java
java -cp out example.testing.mockmvc.GreetingTextDemo
```

**Exact stdout:**

```text
Hello, Ada!
name must not be blank
```

This is only a **plain Java demo** and does not test MockMvc. The `standaloneSetup` and `webAppContextSetup` behaviors are verified via Gradle/JUnit + Spring Test in the preceding section. `GreetingController.java`/`GreetingAdvice.java` cannot be compiled with bare `javac` without Spring dependencies on the classpath.

## 5. When Is standaloneSetup a Good Choice?

### 5.1. Fast, Focused Controller Tests

If the goal is:

- Controller receiving `@RequestParam` and selecting the right arguments to pass to the service.
- Internal HTTP method/path mappings of the controller.
- Status/body for cases handled by `@ExceptionHandler` explicitly provided in the test.
- Simple request binding, path variables, query strings, or headers.
- Checking controller output with a stubbed collaborator.

Then standalone setup can reduce bootstrap time, requires no app configuration, and keeps tests readable. The controller is constructed using constructor injection, often with `Mockito.mock(...)` or a fake, without needing Spring dependency injection.

Example with Mockito inside **an illustrative test method**:

```java
GreetingService service =
        org.mockito.Mockito.mock(GreetingService.class);
org.mockito.Mockito.when(service.greet("Ada"))
        .thenReturn("Hello, Ada!");

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new GreetingController(service))
        .build();

mvc.perform(get("/greetings").param("name", "Ada"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello, Ada!"));

org.mockito.Mockito.verify(service).greet("Ada");
```

The snippet assumes the test method declares `throws Exception` and has static imports for request/assertion builders. It requires no Spring context. However, do not conclude the production service works: the `service.greet` call is a Mockito stub.

### 5.2. Explicitly Configuring What Is Needed

In standalone setup, you can register:

- `setControllerAdvice(...)` for controller advice/error handling.
- `addInterceptors(...)` for one or more MVC interceptors.
- `addFilters(...)` for required servlet filters.
- `setMessageConverters(...)` for specific request/response conversion configuration.
- `setValidator(...)` for validation when exact behavior control is needed.
- Configuring argument resolvers, conversion service, handler exception resolvers, formatters, or view resolvers via the builder API.

However, **the more you configure manually, the greater the risk of drifting from production**. If the main point of the test is verifying that those MVC customizations are actually registered/applied in the application, use a `WebApplicationContext` instead of copying the config into the standalone builder and testing your copy.

### 5.3. Evidence Standalone Does Not Provide

- Does not discover production `@ControllerAdvice` or `WebMvcConfigurer` unless you install them.
- Does not prove bean discovery, qualifiers, profiles, or production auto-configuration.
- Does not prove the Spring Security filter chain unless you register it.
- Does not prove transaction proxies, repositories, DB, or HTTP client adapters run for real when collaborators are mocks.
- Does not prove requests pass through a real servlet container or network.

Standalone is **not wrong** for lacking these; it simply protects a narrower contract.

## 6. When Is webAppContextSetup Worth More?

### 6.1. When Verifying MVC Configuration Present in the Context

Use context setup when the question is:

- Does the application auto-discover a global `@RestControllerAdvice`?
- Is `WebMvcConfigurer.addInterceptors(...)` actually applied?
- Do custom converters/formatters/argument resolvers, validation configuration, locale/timezone, or exception resolvers behave as configured?
- Does the controller receive the right service bean, qualifiers, and profile?
- Do URL mappings across multiple controllers conflict?
- Are the Spring Security filter chain, authorization, and CSRF configured properly at the MVC boundary?

The web context builder pulls beans and MVC config from the **loaded** `TestContext`. To catch production config bugs, make sure the test context loads the relevant production config, not just a simplistic handwritten test `WebConfig`.

### 6.2. Loading the Full Spring Boot Context Is Not Always Necessary

The example above uses `@SpringJUnitWebConfig(WebConfig.class)` and `@EnableWebMvc` to get a minimal web context. This is a **narrow integration test of MVC configuration**, without a DB or unnecessary auto-configured beans.

In Spring Boot, `@WebMvcTest` is often the more convenient option for a web slice. It configures Boot's MVC test infrastructure and lets you inject `MockMvc`; out-of-slice controller collaborators can be provided via `@MockitoBean`. Still, the slice may **exclude** service/DB/non-MVC config components, so you must keep conclusions appropriately scoped.

`@SpringBootTest` + `@AutoConfigureMockMvc` fits when you want many application beans participating along the request path, at a higher startup cost and possibly needing extra infrastructure. If the goal is still just "controller maps HTTP status properly," the full context may be overly broad.

### 6.3. Empirical Comparison with an Interceptor

The two tests in Section 4 provide different evidence:

| Test | Controller/Service | Advice | Interceptor |
| --- | --- | --- | --- |
| `GreetingStandaloneTest` | Created with Java `new` / method reference | Registered with `setControllerAdvice` | **Not** installed → header absent |
| `GreetingWebContextTest` | Beans from `WebApplicationContext` | Bean from context, discovered by MVC | Installed by `WebMvcConfigurer` → header `enabled` |

Both are accurate for **their own setup**. If a standalone test starts checking the `X-App-Interceptor` header without calling `addInterceptors`, it will fail because the test setup lacks the interceptor, **not proving production config is broken**. Conversely, if production requires the header and you only run standalone, a passing test without the header is a **gap in test coverage**.

## 7. MockMvc, Spring Security, and Servlet Filters

Spring Security is not automatically present in a minimal `standaloneSetup`, even if the controller source has security annotations. Method security and servlet security filters are also two different mechanisms; choose the right test boundary.

To integrate Spring Security with `webAppContextSetup` when the context includes the corresponding filter chain and the `spring-security-test` dependency, the Spring Security documentation pattern is:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

**This is a Spring Security test snippet, not part of the runnable tests in Section 4.** It requires the static import `org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity`, a context with a security filter chain, and Spring Security test dependencies. `springSecurity()` adds the Spring Security `FilterChainProxy` and appropriate test `SecurityContext` integration.

If using `@WebMvcTest`/`@SpringBootTest` with `@AutoConfigureMockMvc`, Boot may already configure filters depending on settings. **Do not add the same filter chain multiple times** when it is already attached by another mechanism; inspect your current config and test type before customizing the builder.

When testing HTTP authorization or CSRF, send requests with and deliberately without authentication/CSRF tokens and assert 401/403/responses per real configuration. A standalone test without filters returning 200 **does not mean the endpoint is protected against unauthenticated requests**. Conversely, a test returning 403 due to CSRF does not by itself prove method security works.

`MockMvc` executes requests against mock servlet infrastructure, so if the contract involves the network stack, TLS termination, reverse proxy headers, connection timeouts, or the deployed servlet container, use integration/end-to-end tests over real HTTP (such as `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an appropriate client).

## 8. Exception Handling, Validation, and JSON: Easy-to-Miss Differences

### 8.1. @ControllerAdvice Does Not Appear Automatically in Standalone

If a controller throws an exception handled in production by `@RestControllerAdvice`, a standalone test must register the advice if it wants to test the corresponding HTTP error response. If you *instantiate* the advice in the test, that only proves the advice instance works, **not that production Spring scanned and registered it**.

A web context test can verify that the advice bean is actually discovered by Spring MVC's resolver. When advice is scoped by package or `assignableTypes`, load the relevant controller and advice to verify the matching rules.

### 8.2. @Valid/@Validated Depend on Validation Infrastructure

Bean Validation annotations can work in an MVC setup with a matching provider on the classpath, but the application's custom `Validator`, group sequences, message sources, or conversion rules **are not automatically copied** into a standalone test.

If the target is registered custom validation, use an appropriate web context or configure the standalone equivalent explicitly. In Spring Boot 3, Bean Validation typically requires a dedicated dependency like `spring-boot-starter-validation`; do not assume that merely having Spring Web MVC means all constraint annotations are enforced.

### 8.3. Message Converters and ObjectMapper

HTTP JSON does not depend solely on controller code:

- Jackson module registration, naming strategies, date/time serialization, unknown-property handling.
- Request body conversion, `Content-Type` and `Accept` negotiation.
- How HTTP 400 is returned for parse/binding errors.
- Custom converters or argument resolvers.

The standalone builder uses defaults based on the classpath and explicit configuration; it **does not automatically pick up an `ObjectMapper` bean customized by the Spring Boot application**. If the JSON contract is a key risk, a web context or JSON slice test with real configuration is more valuable. Do not pass a hand-built serializer in a test and conclude the production `ObjectMapper` is right.

### 8.4. Servlet Filter vs. HandlerInterceptor

- **Filter** belongs to the servlet chain and can run before a request enters Spring MVC's `DispatcherServlet`; commonly used for security, tracing, request wrappers.
- **HandlerInterceptor** belongs to Spring MVC's handler execution chain, configured via `WebMvcConfigurer.addInterceptors` or equivalent MVC mechanisms.
- `@ControllerAdvice` belongs to MVC exception handling and does not automatically replace all filter-level exception mapping.

Do not confuse calling `addInterceptors(...)` with adding `springSecurityFilterChain`. Verify at the right layer: HTTP security filters usually need the filter chain from the context; headers added by an MVC interceptor can be tested with the setup in this lesson.

## 9. MockMvc Features Shared by Both Builders

Both standalone and web context setups use the same request/assertion API:

```java
mvc.perform(get("/greetings").param("name", "Ada"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello, Ada!"));
```

This is a snippet inside a test method that has `mvc` and the appropriate imports.

**Useful techniques:**

- `perform(get("/path").param("key", "value"))` simulates a Servlet request parameter. The value in `param(...)` is already supplied to the parameter API, **unlike** constructing a raw query string and passing through URL decoding.
- `perform(post("/path").contentType(MediaType.APPLICATION_JSON).content(json))` simulates a JSON body when required by the endpoint; the response must have a matching converter in the setup.
- `andExpect(status().isOk())`, `andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))`, `andExpect(jsonPath("$.name").value("..."))` check observable responses.
- `andDo(print())` helps diagnose request/response when a test fails; avoid printing sensitive data in CI logs.
- `defaultRequest(...)` or `alwaysExpect(...)` can apply defaults across many tests through the builder when appropriate. Do not let defaults mask specific cases you need to test.

**Async controllers:** for controllers returning `Callable`, `DeferredResult`, or similar async servlet mechanisms, you may need to check `request().asyncStarted()` and then `asyncDispatch(...)` to assert the final response. Neither standalone nor context setup makes async tests wait automatically if the test does not perform the required dispatch step.

**Multipart:** MockMvc provides request builders for file uploads, but it simulates multipart requests; it does not prove streaming/network upload through a real servlet container.

**Views/templates:** controllers returning view names may need a view resolver; standalone requires explicit configuration, whereas web context uses loaded view resolvers. If you only test status/string APIs like the example, no template engine config is needed.

## 10. Performance, Stability, and Context Management

**Standalone setup** does not initialize an `ApplicationContext`, so it usually gives fast feedback, makes instantiating each controller via constructor straightforward, and avoids interference from external datasources/caches/servers. However, production configuration errors will go unnoticed unless broader tests exist.

**Web context setup** uses Spring TestContext to load configuration. Contexts can be **cached and reused** across test classes sharing the same configuration to reduce startup time. However, context caching does not automatically clean up:

- Database rows.
- Mutable singleton fields.
- Shared caches.
- Static state or external resources.
- Authentication/security context if tests mismanage lifecycles.

Use independent fixtures/cleanup and avoid test-order dependencies. `@DirtiesContext` can force a context reload when truly necessary, but should not be the default fix for tests that fail to manage data.

**Key detail:** `MockMvcBuilders.webAppContextSetup(wac)` builds `MockMvc` from an **already existing** context; the `ApplicationContext` startup cost comes mainly from Spring TestContext beforehand, not from the builder call itself inside `@BeforeEach`. Thus you can reuse the context while still creating a fresh `MockMvc` instance per test setup.

If an MVC test requires a real DB, cache, or HTTP client, consider splitting tests by risk. Avoid accidentally turning a header/status check into a heavy full integration test simply because the controller calls a service with many dependencies.

## 11. Common Mistakes

**1. Using standalone and concluding production MVC config is right.** Standalone does not load the application's `@ControllerAdvice`/interceptors/configuration. It proves only the controller with the setup registered in the test.

**2. Thinking standalone just calls the controller method directly.** It still runs `DispatcherServlet` and MVC request infrastructure in a mock environment; it is different from plain Java `controller.greet(...)`.

**3. Assuming `webAppContextSetup` always means full Spring Boot.** It uses only the loaded `WebApplicationContext`. If the context holds only a small test configuration, the conclusion is correspondingly narrow.

**4. Forgetting `@ControllerAdvice` in standalone.** Error paths may throw exceptions instead of returning 400/JSON as in production. Attach `setControllerAdvice(...)` when testing error mapping.

**5. Constructing a `new` controller with `webAppContextSetup` and thinking the builder uses that instance.** The context builder uses the controller **bean** from the context. To test a manually instantiated instance, use the standalone builder.

**6. Forgetting `@EnableWebMvc` or failing to load MVC configuration in a custom `WebApplicationContext`.** Tests may lack expected mappings/interceptors. With `@SpringBootTest`/`@WebMvcTest`, Boot auto-configures MVC under different rules; do not blindly add `@EnableWebMvc` to production config because it can alter Boot MVC auto-configuration.

**7. Mocking a service and concluding the service or DB ran.** `@MockitoBean`/Mockito stubbing does not prove real logic/DB. Keep the right SUT real at the boundary under test.

**8. Missing the security filter chain.** A passing 200 test does not prove an endpoint is protected. Check builder/configurer/filter chain when security is the contract.

**9. Disabling filters to make a test pass and claiming authentication/CSRF is verified.** Test security at the layer with the proper filter chain, rather than altering setup to bypass the behavior under test.

**10. Using a custom `ObjectMapper`/validator in tests that differs from production.** Identical controller code can serialize or validate differently. Context tests with matching config catch those differences.

**11. Using MockMvc to prove real networking/TLS.** The mock servlet environment has no real HTTP port. Use HTTP client integration tests when needed.

**12. Testing an interceptor header in standalone without installing the interceptor.** That is a setup error for the chosen goal, not proof that production beans lack the interceptor.

**13. Not managing shared data/beans inside a cached context.** Context caching can retain mutable singletons, DB rows, or caches, causing order-dependent failures. Clean fixtures at the right boundary and isolate parallel runs.

**14. Turning every test into a full-context test to avoid thinking about scope.** This slows down the suite and obscures where failures originate. Keep standalone tests for narrow controller logic, context tests for MVC config, and full integration tests for flows that genuinely need them.

## 12. Checklist for Choosing a MockMvc Setup

Before writing:

- Is the contract to verify **controller logic** or **Spring-loaded MVC configuration**?
- Do you need **real** global `@ControllerAdvice`, `WebMvcConfigurer`, converters, custom validators, security filters, or bean wiring?
- If using standalone, have you explicitly registered the MVC components to test?
- If using a web context, what configuration is the test loading: minimal `@SpringJUnitWebConfig`, `@WebMvcTest` slice, or `@SpringBootTest`?
- Are the controller and service real instances or mocks? Are test conclusions scoped accordingly?
- Does `MockMvc` include security filters already, or does it need `springSecurity()` and the right dependencies?
- Does the goal require a real HTTP server/port? If so, `MockMvc` alone is not enough.

When running:

- Does the request have the exact HTTP method, path, `Content-Type`, `Accept`, and parameters needed?
- Do response assertions verify **status + body/headers** rather than just a stubbed value?
- For error cases, did you verify the MVC handler/advice of the active setup?
- For custom interceptors, is there an assertion proving the real interceptor ran?
- When a test fails, is the cause controller logic, test setup, MVC configuration, or an out-of-scope dependency?

Once green:

- Is there a context-based test protecting critical configuration that standalone cannot protect?
- Does the test wrongly extrapolate DB/transaction/security/network guarantees from a MockMvc setup lacking those layers?
- Are context/fixtures isolated so tests are order-independent and flake-free?
- If production controller advice, interceptors, or converters change, which test will turn red? If none, add evidence in an appropriate context test.

**Remember:** `standaloneSetup` gives **fast feedback on a controller and MVC config declared directly in the test**. `webAppContextSetup` gives **stronger evidence about MVC wiring and configuration in the loaded `WebApplicationContext`**. Both run requests on mock servlet infrastructure and **do not open a real HTTP server**. Choose the builder based on what you need to prove, and choose the context based on the scope of configuration you actually want to protect.

## 13. References

- [Spring Framework — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html): differences between standalone and `WebApplicationContext`.
- [Spring Framework — MockMvc Performing Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): building requests, parameters, and default requests.
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `springSecurity()` and filter chains in MVC tests.