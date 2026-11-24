# Servlet, Reactive, and Supporting Dependencies by Spring Version

Spring Test provides testing tools for multiple kinds of Spring applications. A Servlet application typically uses Spring MVC and `MockMvc`; a reactive application typically uses Spring WebFlux and `WebTestClient`. Both rely on `spring-test`, yet require different web modules and supporting libraries on the classpath. Choosing the right dependencies for your stack and Spring version ensures tests compile, initialize the right environment, and run reliably.

When configuring dependencies, distinguish three groups: the Spring modules the application actually uses, test-only libraries needed on the test classpath, and server or HTTP client components required for tests that communicate over the network. `spring-boot-starter-test` provides common testing tools, yet it does not decide whether the application is Servlet or Reactive and does not replace the application's web starter.

## 1. Distinguishing dependency layers

A Spring project may need the following components:

| Group | Example | Purpose |
|---|---|---|
| Core Spring Test | `org.springframework:spring-test` | Spring TestContext Framework, `SpringExtension`, `MockMvc`, `WebTestClient`, and mock utilities |
| Servlet/MVC | `org.springframework:spring-webmvc` | DispatcherServlet, MVC controllers, handler configuration, and Servlet web infrastructure |
| Servlet API | `jakarta.servlet:jakarta.servlet-api` or `javax.servlet:javax.servlet-api` | Servlet interfaces used by Spring MVC and mock request/response objects |
| Reactive/WebFlux | `org.springframework:spring-webflux` | WebFlux, reactive controllers, WebHandler, and Reactor integration |
| Reactive Streams | `io.projectreactor:reactor-core` | `Mono`, `Flux`, and reactive runtime; typically pulled in transitively by WebFlux |
| Reactive test | `io.projectreactor:reactor-test` | `StepVerifier`, `TestPublisher`, and Reactor testing utilities |
| HTTP server | Tomcat, Jetty, Undertow, or Reactor Netty | Accepts real requests in tests running over HTTP ports |
| Supporting test libraries | JUnit Jupiter, Mockito, AssertJ, JSONassert, JsonPath | Test engine, mocking, assertions, and payload verification |

`spring-test` is the shared testing module. It provides APIs for tools such as `MockMvc` and `WebTestClient`, yet booting a web application still requires the matching web module. For example, `MockMvc` tests the Servlet/MVC flow, so the test context needs Spring MVC; `WebTestClient` tests WebFlux, so the context needs Spring WebFlux.

Server libraries are only required when tests actually start a server. A `MockMvc` test running in a mock Servlet environment does not open a TCP port. Similarly, `WebTestClient` can bind directly to a controller or WebFlux application context without a real server. When testing over HTTP against a running server, both a server implementation and an appropriate client connector are needed.

## 2. Choosing the Servlet or Reactive stack

### 2.1. Servlet applications with Spring MVC

A Servlet stack typically consists of:

- `spring-webmvc` for Spring MVC.
- The Servlet API matching the namespace and version required by Spring Framework.
- `spring-test` for `MockMvc` and Spring TestContext.
- A Servlet container such as Tomcat, Jetty, or Undertow if the application needs to run a real server.

With Spring Boot, `spring-boot-starter-web` typically brings in Spring MVC and embedded Tomcat by default. This starter belongs to the application dependencies. `spring-boot-starter-test` is added in test scope to supply JUnit, Mockito, and Spring Boot Test.

`MockMvc` simulates request processing through `DispatcherServlet` without starting an HTTP server. It is suited for verifying mappings, binding, validation, exception handling, filters/interceptors configured in the test context, and HTTP responses. If the goal is to verify real server configuration, network ports, TLS, or container integration, use a test with a running server.

### 2.2. Reactive applications with Spring WebFlux

A Reactive stack typically consists of:

- `spring-webflux` for WebFlux.
- `reactor-core` for `Mono` and `Flux`; this module is usually declared transitively by WebFlux.
- `spring-test` for `WebTestClient` and Spring testing utilities.
- `reactor-test` when testing publishers with `StepVerifier` or `TestPublisher`.
- An HTTP server such as Reactor Netty when running the real application over a network port.

With Spring Boot, `spring-boot-starter-webflux` brings in WebFlux and defaults to Reactor Netty as the server unless replaced with another server. `spring-boot-starter-test` supplies Spring testing tools and JUnit. `reactor-test` is a separate dependency when tests need `StepVerifier`.

`WebTestClient` can bind to a controller or WebFlux application context to test requests and responses without a real server. It can also connect to a running server to test the full HTTP stack. Therefore, identify which binding style your tests use before adding server or connector dependencies.

### 2.3. Do not add both web stacks arbitrarily

An application can have both `spring-webmvc` and `spring-webflux` on the classpath, yet that does not mean every test needs both. Spring Boot typically favors MVC configuration when both MVC and WebFlux appear together in a servlet-capable application. If a project intentionally uses both, understand how application type, server, and test configuration are selected.

For modules that only test MVC, focus on `MockMvc`. For modules that only test WebFlux, focus on `WebTestClient` and Reactor tools. Keeping the classpath aligned with the architecture avoids having the test context pick the wrong application type or pull in unrelated configuration.

## 3. Dependencies by Spring generation

The Spring version determines the Servlet namespace, minimum Java level, and available APIs. The points below help choose the right dependency family; exact patch versions must still come from the BOM of the release train in use.

| Generation | Web foundation | Servlet namespace | Testing notes |
|---|---|---|---|
| Spring Framework 5.x / Spring Boot 2.x | Spring MVC or WebFlux | `javax.servlet.*` | Use dependencies from the Spring 5/Boot 2 line; JUnit Jupiter tests need versions managed by the BOM or explicitly aligned |
| Spring Framework 6.x / Spring Boot 3.x | Spring MVC or WebFlux | `jakarta.servlet.*` | Requires Java 17 or higher; Servlet ecosystem moved to the Jakarta EE namespace |
| Spring Framework 7.x / Spring Boot 4.x | Spring MVC or WebFlux | `jakarta.servlet.*` | Continues using the Jakarta namespace; choose dependencies from the corresponding release train BOM |

Do not mix `spring-test` 5.x with `spring-webmvc` 6.x or `spring-webflux` 7.x. Spring Framework modules such as `spring-core`, `spring-context`, `spring-web`, `spring-webmvc`, `spring-webflux`, and `spring-test` should share the same Framework version. Spring Boot manages a curated set of Spring Framework, JUnit, and supporting library versions for each release train.

### 3.1. Differences between javax and jakarta

Spring Framework 5.x belongs to the generation using the Java EE `javax.servlet` namespace. Starting with Spring Framework 6.x, Jakarta EE APIs are used under the `jakarta.servlet` namespace. Spring Boot 2.x belongs to the `javax` generation; Spring Boot 3.x migrated to `jakarta` alongside Spring Framework 6.

The two APIs share similar class names yet live in different packages. A class compiled against `javax.servlet.http.HttpServletRequest` cannot be passed in place of `jakarta.servlet.http.HttpServletRequest`. Therefore, you cannot fix errors by putting both Servlet APIs on the classpath and expecting them to substitute for each other.

Import examples across the two generations:

```java
// Spring Framework 5.x / Spring Boot 2.x
import javax.servlet.http.HttpServletRequest;
```

```java
// Spring Framework 6.x+ / Spring Boot 3.x+
import jakarta.servlet.http.HttpServletRequest;
```

When upgrading from Boot 2 to Boot 3, migrate Servlet imports and dependencies to Jakarta. Testing libraries, filters, servlet containers, and third-party libraries must also support the Jakarta namespace. Upgrading only `spring-test` while keeping the old Servlet API will cause compilation failures or class linkage errors.

### 3.2. JUnit and supporting libraries must also be aligned

JUnit Jupiter is versioned independently from Spring Framework. In Boot applications, rely on the Boot BOM to manage JUnit, Mockito, and test libraries. In standalone Spring Framework projects, manage the Spring Framework BOM and JUnit BOM separately. For WebFlux, align `reactor-core`, `reactor-test`, and Reactor Netty via a compatible BOM or release train.

Do not infer JUnit or Reactor version numbers from Spring version numbers. Check the actual dependency management of the chosen Boot/Framework release. This matters especially when upgrading an individual library, because the API may compile while the test engine or connector is incompatible at runtime.

## 4. Maven configuration for Spring Boot

### 4.1. Servlet/MVC applications

With Maven inheriting `spring-boot-starter-parent`, declare the web starter in main dependencies and the test starter in `test` scope:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-web` brings Spring MVC and the default server into the application. `spring-boot-starter-test` provides `spring-test`, JUnit Jupiter, Mockito, and common assertion libraries. There is no need to declare `spring-test`, `spring-webmvc`, or the Servlet API manually at matching versions when the starters already manage them.

### 4.2. Reactive/WebFlux applications

For WebFlux applications:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The WebFlux starter supplies reactive infrastructure and Boot's default server. `reactor-test` adds `StepVerifier` to test publishers for signals, demand, completion, and errors. If tests only bind `WebTestClient` to controllers or a context, no separate server is needed beyond the dependencies the application already requires.

### 4.3. Without Spring Boot parent

If the project inherits a custom parent POM, you can import `spring-boot-dependencies` in `dependencyManagement` and then declare starters without specifying individual dependency versions. The BOM manages versions; it does not automatically apply all plugin configurations from the Spring Boot parent. Maven Surefire and test execution configuration must be managed separately if your parent does not provide them.

The dependency structure remains the same as in the two sections above. Ensure the Boot version property is declared once, the BOM is imported in the proper scope, and individual modules do not override Spring or JUnit versions independently.

## 5. Maven configuration for standalone Spring Framework

For non-Boot projects, explicitly declare the web module matching the application architecture, `spring-test` for testing, and BOMs to manage versions.

### 5.1. Servlet/MVC

Example for Spring Framework 6.x:

```xml
<properties>
    <spring-framework.version>6.2.0</spring-framework.version>
    <junit.version>5.11.0</junit.version>
    <servlet-api.version>6.0.0</servlet-api.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>${servlet-api.version}</version>
        <scope>provided</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

This illustrates a Servlet application using Jakarta Servlet. `provided` fits when an external Servlet container supplies the API at runtime; Maven still includes the dependency on the test classpath. If the Servlet API is only used in test code, consider `test` scope. The Servlet API version must be compatible with your chosen container and Spring baseline.

For Spring Framework 5.x, use `javax.servlet:javax.servlet-api` and the `javax.servlet.*` namespace along with the Spring Framework 5.x BOM. Do not add the Jakarta Servlet API to a Spring 5.x application just to make imports compile.

### 5.2. Reactive/WebFlux

Example for a standalone Spring Framework project using WebFlux:

```xml
<properties>
    <spring-framework.version>6.2.0</spring-framework.version>
    <junit.version>5.11.0</junit.version>
    <reactor.version>2024.0.0</reactor.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-bom</artifactId>
            <version>${reactor.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The version properties in this example only illustrate structure; the project must select a Reactor BOM compatible with the Spring Framework and Java versions in use. If testing WebFlux through a real server, add an appropriate HTTP server implementation such as Reactor Netty. If only binding `WebTestClient` to a context or controller, tests do not need to start a real server.

The Spring Framework BOM manages Spring modules. The JUnit BOM manages JUnit modules. The Reactor BOM manages Reactor Core, Reactor Test, and related Reactor modules. Keeping each ecosystem in its proper BOM prevents assuming a Spring version number can substitute directly for Reactor or JUnit versions.

## 6. Gradle configuration for Spring Boot

### 6.1. Servlet/MVC

For Boot MVC applications:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 6.2. Reactive/WebFlux

For Boot WebFlux applications:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

When using the Spring Boot Gradle Plugin alongside the dependency management plugin, the Boot BOM is typically imported automatically. If the project uses native Gradle platforms, declare `platform("org.springframework.boot:spring-boot-dependencies:${springBootVersion}")` in the appropriate configurations before declaring starters. Do not specify separate versions for modules already managed by the BOM.

## 7. Gradle configuration for standalone Spring Framework

With standalone Spring Framework, you can use Gradle's native BOM support to manage dependency groups:

### 7.1. Servlet/MVC

```groovy
dependencies {
    implementation platform("org.springframework:spring-framework-bom:${springFrameworkVersion}")
    implementation 'org.springframework:spring-webmvc'

    testImplementation 'org.springframework:spring-test'
    testImplementation platform("org.junit:junit-bom:${junitVersion}")
    testImplementation 'org.junit.jupiter:junit-jupiter'

    // Spring Framework 6.x+; use javax.servlet API for Spring 5.x.
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`compileOnly` fits when an external container supplies the Servlet API at runtime. If only test code needs the API, `testImplementation` can be used. With Spring Boot, the web starter already manages web and server dependencies, so declaring the Servlet API separately is usually unnecessary.

### 7.2. Reactive/WebFlux

```groovy
dependencies {
    implementation platform("org.springframework:spring-framework-bom:${springFrameworkVersion}")
    implementation 'org.springframework:spring-webflux'

    implementation platform("io.projectreactor:reactor-bom:${reactorVersion}")

    testImplementation 'org.springframework:spring-test'
    testImplementation platform("org.junit:junit-bom:${junitVersion}")
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If tests connect to a real server, add a compatible server implementation, such as `io.projectreactor.netty:reactor-netty-http` in `runtimeOnly` or an appropriate configuration. For tests bound to a WebFlux context, no server implementation is needed just to invoke `WebTestClient`.

The variables `springFrameworkVersion`, `junitVersion`, and `reactorVersion` must be defined in `gradle.properties`, a version catalog, or a convention plugin. When using a BOM, let the BOM manage versions for artifacts in its ecosystem.

## 8. Choosing testing tools by application type

### 8.1. MockMvc for Servlet/MVC

`MockMvc` tests requests through Spring MVC without opening a socket. You can use the `@WebMvcTest` test slice to load the needed MVC parts, or `@SpringBootTest` combined with `@AutoConfigureMockMvc` when a broader context is needed.

Example:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsAcceptedForValidRequest() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""{"quantity": 2}"""))
                .andExpect(status().isAccepted());
    }
}
```

Imports and mock bean annotations must match the project's Spring Boot version. In newer releases, a replacement annotation for `@MockBean` may be provided by Spring Framework itself. `MockMvc` fits when verifying mappings, validation, converters, exception handlers, filters, or MVC responses.

If you want to verify the application running on an embedded server, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client. In that case, the test needs a server implementation on the runtime classpath. This is a network-level test with a broader scope than MockMvc.

### 8.2. WebTestClient for WebFlux

`WebTestClient` provides a fluent API similar to WebClient, designed for testing. It supports binding directly to controllers, an application context, or connecting to a running server.

Example testing a WebFlux controller with mock binding:

```java
@Test
void returnsGreetingFromReactiveController() {
    WebTestClient client = WebTestClient
            .bindToController(new GreetingController())
            .build();

    client.get()
            .uri("/greeting")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello");
}

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Mono<String> greeting() {
        return Mono.just("Hello");
    }
}
```

This test requires `spring-webflux`, `spring-test`, and Reactor on the test classpath. It needs no TCP server because the client binds directly to the controller. When using `@WebFluxTest`, Spring Boot can auto-configure `WebTestClient` for injection into the test.

If you want to test over real HTTP, use `WebTestClient.bindToServer()` against a running server. This requires an appropriate HTTP client connector and a server implementation serving the application. In default Boot WebFlux setups, Reactor Netty typically serves as the server.

### 8.3. StepVerifier for Reactor publishers

`WebTestClient` verifies HTTP contracts; `StepVerifier` verifies the signal sequence of a `Mono` or `Flux` directly. The two tools complement each other.

```java
@Test
void emitsValuesAndCompletes() {
    Flux<String> names = Flux.just("Lan", "Minh");

    StepVerifier.create(names)
            .expectNext("Lan")
            .expectNext("Minh")
            .verifyComplete();
}
```

`StepVerifier` belongs to `reactor-test`, so that module must be declared in test scope. You can use it to assert emitted values, signal ordering, errors, completion, timeouts, and backpressure behavior according to the publisher's contract.

## 9. Commonly used supporting libraries

Not every project needs every test library. Choose dependencies according to the assertion styles and environments your tests require.

| Library | When needed | Dependency notes |
|---|---|---|
| JUnit Jupiter | Writing and running unit/integration tests | API, Params, and Engine must be aligned; Boot starter usually provides them |
| Mockito | Mocking, stubbing, verifying, and capturing arguments | Use the version managed by the Boot BOM or an explicit BOM |
| AssertJ | Fluent assertions for objects, collections, and exceptions | Included in `spring-boot-starter-test` |
| Hamcrest | Matchers used in assertions or MockMvc | Usually included in the Boot test starter |
| JSONassert | Comparing JSON responses | Useful when verifying JSON contracts |
| JsonPath | Extracting fields in JSON responses | Usable with MockMvc/WebTestClient when tests need it |
| XMLUnit | Comparing and verifying XML | Add only when the application has XML contracts |
| Awaitility | Waiting for asynchronous conditions to reach expected state | Used in tests with eventual consistency or background processing |
| Reactor Test | `StepVerifier`, `TestPublisher` | Required for testing Reactor publishers |
| Testcontainers | Running databases, brokers, or backing services in containers | Add only for integration tests needing real infrastructure dependencies |

In Spring Boot, `spring-boot-starter-test` already includes many common libraries such as JUnit Jupiter, Mockito, AssertJ, Hamcrest, JSONassert, JsonPath, Awaitility, and XMLUnit. Inspect the dependency tree before adding duplicate artifacts. `reactor-test` and Testcontainers are usually declared separately per module needs.

For projects not using Boot, declare each library in test scope and use appropriate BOMs. For example, Mockito and AssertJ can be managed through dedicated BOMs or a version catalog; avoid picking a version simply because it is the latest if the project uses an older Spring/JUnit baseline.

## 10. Distinguishing mock tests from real-server tests

Dependency selection depends on the level of integration being verified:

| Goal | Servlet/MVC | Reactive/WebFlux | Real server needed? |
|---|---|---|---|
| Testing controllers and response mappings | `MockMvc` | `WebTestClient.bindToController(...)` | No |
| Testing web application context configuration | `MockMvc` with context or `@WebMvcTest` | `WebTestClient.bindToApplicationContext(...)` or `@WebFluxTest` | No |
| Testing full application over an HTTP port | HTTP client with `@SpringBootTest(RANDOM_PORT)` | `WebTestClient.bindToServer()` against running server | Yes |
| Testing publisher logic | Not applicable to pure MVC | `StepVerifier` | No |
| Testing real database or broker | Testcontainers or integration environment | Testcontainers or integration environment | Requires backing service; does not necessarily require a web server |

Mock tests are fast and focus on a single layer's contract. Real-server tests additionally verify network configuration, server adapters, serialization over real HTTP, and parts of deployment behavior. Do not use a real server for every simple scenario if mock tests already verify the behavior under protection.

## 11. Common dependency errors

### 11.1. Servlet class or method not found

If you encounter `ClassNotFoundException` or `NoClassDefFoundError` involving `javax.servlet.*` or `jakarta.servlet.*`, check the Spring generation and Servlet API namespace. Spring 5.x uses `javax`; Spring 6.x and newer use `jakarta`. Check both the container and third-party filter/security libraries.

### 11.2. `MockMvc` fails to initialize

`spring-test` may already be on the classpath while the application lacks `spring-webmvc` or the test context is not configured as a Servlet application. With Boot, check that the module has `spring-boot-starter-web` and the test slice targets the right controller. With standalone Spring Framework, verify `spring-webmvc` and a compatible Servlet API are present.

### 11.3. `WebTestClient` or `Mono` not found

`WebTestClient` lives in Spring Test, while `Mono` and `Flux` come from Reactor Core. Verify that `spring-test`, `spring-webflux`, and Reactor dependencies are on the test classpath. If using Boot WebFlux, verify `spring-boot-starter-webflux` is declared.

### 11.4. `WebTestClient.bindToServer()` cannot connect

Mock binding requires no server, whereas `bindToServer()` requires a running server and an HTTP client connector. Confirm that the application started, the port is right, and a server implementation is on the runtime classpath. With Boot WebFlux, check Reactor Netty or the server adapter chosen by the project.

### 11.5. `NoSuchMethodError` across Spring modules

This error usually indicates mismatched versions across Spring modules. Inspect the dependency tree to see whether `spring-core`, `spring-context`, `spring-web`, `spring-webmvc`, `spring-webflux`, and `spring-test` have diverging versions. Use a Spring Framework BOM or Boot BOM to align them.

### 11.6. Reactor Test cannot find StepVerifier

`StepVerifier` belongs to `reactor-test`, not `spring-test` or JUnit. Add `io.projectreactor:reactor-test` in test scope and let the Reactor BOM or Boot BOM manage its version.

### 11.7. Both MVC and WebFlux are active simultaneously

If both web starters are present, Boot may pick MVC via auto-configuration. Inspect auto-configuration condition logs and the application type to see which stack the context runs on. If a module only needs one stack, remove the other web dependency from that module to avoid ambiguous configuration.

## 12. Inspecting the dependency graph

When classpath errors occur, inspect the actual resolved test dependencies instead of guessing from `pom.xml` or `build.gradle`.

With Maven:

```bash
mvn dependency:tree -Dscope=test -Dincludes=org.springframework,org.springframework.boot,org.junit,org.junit.jupiter,org.junit.platform,io.projectreactor,jakarta.servlet,javax.servlet
```

This command reveals the resolved versions of Spring, JUnit, Reactor, and Servlet APIs. You can use `mvn help:effective-pom` to inspect the final BOMs, parent, and plugin configurations.

With Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

To see why a specific artifact version was selected:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency reactor-test --configuration testRuntimeClasspath
```

Once the dependency graph is aligned, run the project's test task (`mvn test` or `./gradlew test`). For real-server integration tests, confirm the runtime classpath includes a server implementation. For mock-bound tests, confirm the web module and `spring-test` are present.

## 13. Dependency rules in multi-module projects

In multi-module projects, each module should declare only the web stack it actually uses. MVC modules can use `spring-webmvc`; WebFlux modules use `spring-webflux`; plain Java modules only need JUnit and necessary test libraries. Shared root configuration should manage versions through BOMs or a version catalog so modules do not independently pull in different Spring versions.

With Spring Boot, use one Boot release train across modules belonging to the same application and let the Boot BOM manage related dependencies. With standalone Spring Framework, use the Spring Framework BOM for Spring modules, the JUnit BOM for JUnit, and the Reactor BOM for Reactor when needed. Do not keep a version catalog full of isolated version numbers without clearly showing which artifacts belong to which release train.

Test dependencies belong in `testImplementation` or Maven `test` scope. The Servlet API can be `provided`/`compileOnly` when supplied by an external container, while Boot's embedded server is normally managed by the web starter. Reactor Netty only needs explicit declaration when the application or real-server tests require it; `reactor-test` belongs in test scope.

When upgrading Spring, check the Java baseline, Servlet namespace, server/container, Spring Test, JUnit, and supporting libraries together. When migrating from Spring 5 to Spring 6, shifting from `javax` to `jakarta` is a foundational change that must be handled consistently across code, dependencies, and runtime environments. When the dependency graph is aligned with the stack and release train, `MockMvc`, `WebTestClient`, and supporting test libraries operate in the exact environment each test needs to simulate.
