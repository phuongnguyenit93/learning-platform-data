# Unable to Start Web Server or Missing WebServerFactory Bean

**Module:** Spring Boot → web-runtime → **Debugging and Upgrades**.

One of the most confusing messages for newcomers to Spring Boot is:

~~~text
org.springframework.context.ApplicationContextException:
Unable to start ServletWebServerApplicationContext due to missing
ServletWebServerFactory bean.
~~~

The reactive variant may mention `ReactiveWebServerApplicationContext` and `ReactiveWebServerFactory`. These typically appear when Spring Boot has selected **a web application context type that needs an embedded server**, yet **cannot find the corresponding factory** in the `ApplicationContext`. This is **not** a generic error for all HTTP 404/500 responses, nor does it mean port 8080 is already in use.

This article explains:
- what `ServletWebServerFactory` and `ReactiveWebServerFactory` are, and how they differ from Servlet/`DispatcherServlet`/`WebServer`/`WebServerFactoryCustomizer`;
- why `@SpringBootApplication`, auto-configuration, starters, dependency scopes, `WebApplicationType`, parent/child contexts, explicit `@Configuration`, and test annotations determine whether a factory is created;
- how to distinguish **missing factory**, **multiple factories**, **server port occupied**, **`NoClassDefFoundError`**, **`BeanCreationException`**, **startup without web server**, and **request returning 404**;
- how to use `--debug`/conditions report, `mvn dependency:tree`, `jar tf`, `@SpringBootTest(RANDOM_PORT)`, and integration tests to isolate the root cause;
- the proper fixes in Spring MVC, WebFlux, switching Tomcat → Jetty/Undertow, executable JAR/WAR, Boot 2 → 3 migration (Jakarta), and Boot 3 → 4;
- a **Java 17 + Maven + Spring Boot 3.5.16** example with a full project, positive HTTP test, test intentionally triggering the missing-factory error, NONE-mode test, instructions to reproduce via command-line exclusion, and a deployment checklist.

**Reference environment:** Java 17+, Spring Boot **3.5.16**, Spring Framework 6.2.x, Maven. The Boot 3.5 line reaches end of OSS support after the final release in late June 2026, so **do not pick 3.5.16 for new production applications without an appropriate security patching channel**; the version is pinned here strictly for learning Boot 3.5 APIs. Do not copy new Boot 4.x packages/annotations into a 3.5 project without checking the migration notes.

## 1. Understand the Error Message Before Fixing

A typical Servlet Spring Boot application follows this sequence:

~~~text
SpringApplication.run(...)
          │
          ▼
WebApplicationType.SERVLET
          │
          ▼
AnnotationConfigServletWebServerApplicationContext
          │
          ├── refresh() creates/registers bean definitions
          │       │
          │       └─ @EnableAutoConfiguration
          │             └─ ServletWebServerFactoryAutoConfiguration
          │                    ├─ EmbeddedTomcat
          │                    ├─ EmbeddedJetty
          │                    └─ EmbeddedUndertow
          │
          ├── looks up exactly 1 ServletWebServerFactory bean
          │       │
          │       ├─ 0 beans → "missing ServletWebServerFactory" error
          │       ├─ >1 beans → "multiple ServletWebServerFactory" error
          │       └─ 1 bean: Tomcat/Jetty/Undertow factory
          │
          └── factory.getWebServer(initializers...)
                   │
                   └─ WebServer.start() → socket/connector → HTTP
~~~

In Spring Boot 3.5, `ServletWebServerApplicationContext` is the context type for an embedded servlet container. During initialization, it **looks up a single bean of type `ServletWebServerFactory`** in the context; typically the bean auto-configured by Boot is `TomcatServletWebServerFactory`, `JettyServletWebServerFactory`, or `UndertowServletWebServerFactory`.

**Make the distinction crystal clear:**

| Component | What does it actually do? | Does it create an HTTP server? |
| --- | --- | --- |
| `SpringApplication` | Coordinates bootstrap, chooses web type/context, loads configuration | Via the appropriate context |
| `ServletWebServerApplicationContext` | Embedded Servlet context; finds factory, creates/starts server | **Yes**, when a factory exists |
| `ServletWebServerFactory` | Factory creating the `WebServer` container: Tomcat/Jetty/Undertow | **Yes**, when invoked by the context |
| `TomcatServletWebServerFactory` | Concrete Servlet factory for embedded Tomcat | **Yes** |
| `DispatcherServlet` | Spring MVC Servlet handling controller/handler mappings | **Does not** provide an HTTP listener itself |
| `@RestController` | Registers a handler at the MVC layer | **Does not** create a factory/server |
| `WebServerFactoryCustomizer` | Adjusts port, connector, SSL, or options of an existing factory | **Does not** create a factory on its own |
| `WebServer` | Embedded runtime created by the factory | Starts/stops and listens on the network |
| `ReactiveWebServerFactory` | Factory for the reactive HTTP runtime | **Yes** when using a Reactive context |
| `server.port` | Configures the port for an existing server | **Does not** fix a missing factory |

**By contract:** missing factory means **0 beans of the matching type in the place where the context looks**. It does not mean "Java doesn't know what Tomcat is," nor does it prove "Maven is missing `starter-web`" — that is only **one** possibility. If another bean exists but is not in the right context or has a different type (reactive instead of servlet), the servlet context still treats it as missing.

### 1.1. Why Does `@RestController` Compile Yet the Application Fails to Start?

A Java controller can compile because `spring-web`/`spring-webmvc` are on the compile classpath, while **embedded Tomcat runtime classes** were dropped via a Maven exclusion or the wrong scope. Conversely, the HTTP server starter may be present, yet auto-configuration was omitted because `@Configuration` was used instead of `@SpringBootApplication` at bootstrap.

The framework must satisfy **two distinct conditions**:
1. Sufficient runtime/framework classes and configuration to create the right **factory bean**.
2. Create/bind/start the server successfully before requests can be dispatched to controllers.

A `@GetMapping("/ping")` handler cannot fill in for a missing `ServletWebServerFactory`.

### 1.2. The Message Usually Points to the Failure Layer, Not the Full Root Cause

For example:

~~~text
ApplicationContextException: Unable to start ServletWebServerApplicationContext
due to missing ServletWebServerFactory bean.
~~~

The "missing" part tells you Spring looked for the factory **in the context and found none**, but it does not explain:
- Is Maven/Gradle missing Tomcat/Jetty/Undertow?
- Was `ServletWebServerFactoryAutoConfiguration` excluded?
- Is `@EnableAutoConfiguration` missing?
- Was `SpringApplication` forced to `WebApplicationType.SERVLET` on an unsuitable runtime classpath?
- Did a test or custom context import only a minimal configuration?
- Does a parent context have the factory while the child Servlet context does not?
- Did a custom bean, multiple contexts, or auto-config conditions change?

**Standard diagnosis:** gather **root cause + Condition Evaluation Report + runtime dependency tree + effective properties + actual `ApplicationContext` type**, instead of starting by unconditionally adding `@Bean TomcatServletWebServerFactory`.

## 2. Two Factory Families and Which App Needs Which

| Web stack | Context type | Required factory interface | Typical default factory |
| --- | --- | --- | --- |
| **Spring MVC / Servlet** | `ServletWebServerApplicationContext` | `ServletWebServerFactory` | `TomcatServletWebServerFactory` |
| **WebFlux / Reactive** | `ReactiveWebServerApplicationContext` | `ReactiveWebServerFactory` | `NettyReactiveWebServerFactory` |
| **Non-web process** | Non-web `ApplicationContext` | **Not needed** | No HTTP listener |
| **WAR in external container** | Container-managed Servlet lifecycle per deployment | Does not share the same requirement to create an embedded server during external container bootstrap | External container owns the HTTP server |

Spring Boot 3.5 offers these options:
- Servlet: **Tomcat, Jetty, Undertow**.
- Reactive: **Reactor Netty, Tomcat, Jetty, Undertow** via the appropriate factory.
- Reactor Netty is **not** a Servlet factory; `NettyReactiveWebServerFactory` cannot be supplied as a `ServletWebServerFactory` to serve `DispatcherServlet` as on Tomcat.

**Common mistake:** seeing `reactor-netty-http` in dependencies and assuming a Servlet web app already has an embedded server. If Boot picks `SERVLET` without a `TomcatServletWebServerFactory`/Jetty/Undertow factory, a Reactor Netty reactive factory does not satisfy the Servlet context requirement.

### 2.1. Which Auto-Configuration Creates the Servlet Factory?

Boot 3.5 class name:

~~~java
org.springframework.boot.autoconfigure.web.servlet
    .ServletWebServerFactoryAutoConfiguration
~~~

Key conditions of the servlet auto-configuration include:
- A suitable Servlet API class on the classpath (for example `jakarta.servlet.ServletRequest`).
- `@ConditionalOnWebApplication(type=SERVLET)` matches.
- Nested configurations for Tomcat/Jetty/Undertow only create the factory when the corresponding runtime container classes are present and bean conditions match.
- `@ConditionalOnMissingBean`/`@ConditionalOnClass` control whether Boot creates the default bean.

Do not stop at the line "`ServletWebServerFactoryAutoConfiguration matched`": the nested `EmbeddedTomcat`/`EmbeddedJetty`/`EmbeddedUndertow` classes can still **not match**. Read **negative matches** to see which class is missing or whether another factory caused the default to back off.

### 2.2. Reactive Factory and Reactive Auto-Configuration

Boot 3.5 class name:

~~~java
org.springframework.boot.autoconfigure.web.reactive
    .ReactiveWebServerFactoryAutoConfiguration
~~~

It configures the appropriate factory for `ReactiveWebServerApplicationContext` when the web application is reactive and a compatible HTTP runtime implementation is on the classpath. With `spring-boot-starter-webflux`, Boot 3.5 normally pulls in **`spring-boot-starter-reactor-netty`**.

If you exclude Reactor Netty without substituting a compatible reactive runtime (Tomcat/Jetty/Undertow), the reactive context can miss `ReactiveWebServerFactory` or fail earlier with a missing class. **Do not fix this by adding `TomcatServletWebServerFactory` when the app selected `REACTIVE`.** The two interfaces are not interchangeable.

### 2.3. How Does Boot Differ from an External WAR Servlet Container?

When running an executable JAR/embedded server, `SpringApplication` creates a `ServletWebServerApplicationContext` and requires an embedded server factory.

When deploying a traditional WAR, an **external Tomcat/Jetty process** manages sockets and `ServletContext`; Boot integrates differently via `SpringBootServletInitializer`. Do not blindly take an executable JAR's `missing ServletWebServerFactory` stack trace and apply the same reasoning to an external-WAR runtime. A WAR marking the embedded container dependency as `provided` **can be correct**; in an executable Boot WAR, `lib-provided` allows it to also run via `java -jar` when the build plugin/config is set up properly.

## 3. `WebApplicationType`: SERVLET, REACTIVE, and NONE

Boot defines the enum `org.springframework.boot.WebApplicationType`:

| Value | Meaning | Factory required? |
| --- | --- | --- |
| `SERVLET` | Servlet-based web application, embedded server | `ServletWebServerFactory` |
| `REACTIVE` | Reactive web application, embedded reactive server | `ReactiveWebServerFactory` |
| `NONE` | Do not create a web server | **No** |

Boot deduces the type from the classpath. **If both `spring-boot-starter-web` (MVC) and `spring-boot-starter-webflux` are present, MVC generally takes precedence and Boot selects SERVLET**. Do not assume adding the WebFlux starter automatically switches the entire application to Reactor Netty.

Set explicitly via property:

~~~properties
spring.main.web-application-type=servlet
~~~

or:

~~~properties
spring.main.web-application-type=reactive
~~~

or for a CLI/headless job:

~~~properties
spring.main.web-application-type=none
~~~

Programmatic approach:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

This is an **illustrative snippet**; do not copy it into the main class of a web server demo. `NONE` intentionally runs without HTTP, and is not a "fix" when business requirements demand serving web requests.

### 3.1. Does Setting `NONE` Remove the WebServerFactory Bean?

In non-web mode, `@ConditionalOnWebApplication` does not match, so **having no embedded `WebServerFactory` is by design**. The application can start cleanly without `/ping` or a listening port.

If users report "the app has no HTTP port" while logs show `Started DemoApplication`, before hunting for a missing factory error, check:

~~~properties
spring.main.web-application-type=none
~~~

along with possible override sources: command-line arguments, environment variables, active profiles, `SpringApplication#setWebApplicationType`, and `SpringApplicationBuilder.web(...)`. An app starting cleanly in `NONE` mode is **not** a missing-factory error, because the context does not ask for a factory.

### 3.2. `server.port=-1` Differs from `NONE`

The Spring Boot docs distinguish:

~~~properties
server.port=-1
~~~

**Disables HTTP endpoints while still creating the web application context.** This is a different design from:

~~~properties
spring.main.web-application-type=none
~~~

`server.port=-1` does not convert `ServletWebServerApplicationContext` into a non-web context, so the context may still require a factory. Nor does it guarantee identical startup behavior across all web server types and versions.

~~~properties
server.port=0
~~~

asks the OS to pick an ephemeral free port **after the factory already exists**, which is useful for `@SpringBootTest(RANDOM_PORT)`. It does not create a missing factory. Changing port 8080 to 8081 or 0 to "fix a missing factory" targets the wrong layer.

### 3.3. Forcing a Web Type That Contradicts the Runtime Classpath

A CLI project that only has `spring-boot-starter` (no Servlet API/server implementation), and then forces `WebApplicationType.SERVLET`, can fail due to missing servlet classes, a missing factory, or classloading errors prior to factory lookup — **the exact stack trace depends on the real classpath**. Do not claim you will always get one exact message.

If Servlet is required, provide a consistent Servlet stack (e.g., `spring-boot-starter-web` + a servlet container starter). If a non-web CLI is wanted, use `NONE`. If WebFlux is wanted, provide the reactive web framework + reactive runtime; do not force `SERVLET` just to get an HTTP port.

## 4. Root Cause 1: Container Dependency Excluded or Packaged Incorrectly

### 4.1. Appropriate Minimal MVC Maven Dependency

With Spring Boot 3.5, `spring-boot-starter-web` normally includes:
- `spring-web`/`spring-webmvc`;
- Jackson JSON integration;
- `spring-boot-starter-tomcat` and the embedded Tomcat artifacts;
- the corresponding Spring Boot auto-configuration.

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Adding this starter is usually the right choice to get MVC + embedded Tomcat. **Do not** manually add `tomcat-embed-core` JARs with arbitrary versions just to compensate for a transitively excluded starter; it may lack compatible companion artifacts or cause `javax`/`jakarta` API mismatches.

### 4.2. Example Maven Exclusion That Removes Tomcat

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

**Only exclude Tomcat when intentionally replacing it with another Servlet container starter**, such as:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

or:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
~~~

The XML blocks above are **configuration snippets**; do not add both Jetty and Undertow simultaneously in the sample project. When swapping servers, use the Spring Boot 3.5 BOM to manage versions. If the project ends up missing Servlet API classes entirely after an exclusion, Boot may detect `NONE` or throw a classloading failure before reporting a missing factory. Always read the actual root cause rather than assuming a single message.

### 4.3. Runtime Dependencies Differ from Compile Dependencies

Maven scopes:
- `compile`: present at compile time and runtime.
- `runtime`: present at runtime, not necessarily at compile time.
- `provided`: normally used for a servlet container supplied by an **external environment** when deploying a WAR; do not assume it is normal for every executable JAR.
- `test`: for tests only, **not** present in the packaged app runtime.
- `optional`/exclusions/`dependencyManagement`: can alter the effective runtime graph.

Gradle equivalents include `implementation`, `runtimeOnly`, `compileOnly`, and `providedRuntime` for WARs. Spring Boot docs prefer `providedRuntime` over `compileOnly` for traditional WARs so the dependency remains on the test classpath and the executable-WAR layout stays valid.

**Do not judge by compile success.** The runtime artifact must actually contain or be able to load the factory implementation in the target environment.

### 4.4. Commands to Inspect Runtime Dependencies

From the Maven project root:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:tomcat-embed-core
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-jetty
mvn help:effective-pom
~~~

Check:
- Is `spring-boot-starter-web` still on the runtime dependency graph?
- Was `spring-boot-starter-tomcat`/Jetty/Undertow excluded by a parent BOM, profile, or exclusion?
- Is the effective scope `test` or `provided`?
- Are multiple embedded servers present simultaneously, causing unexpected bean conditions?
- Are Spring Boot dependencies on the same release line/version family, or did a module override skew versions?

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

These commands analyze the **runtime classpath** without touching production hosts or inspecting the auto-configuration source code directly. In Windows PowerShell you can run `.\gradlew.bat`; Maven `-Dincludes=...` may need quotes depending on your shell.

### 4.5. Inspecting the Executable JAR/WAR

~~~bash
mvn clean package
jar tf target/server-factory-lab-0.0.1-SNAPSHOT.jar
~~~

In an executable Boot JAR, dependencies are packaged under `BOOT-INF/lib/` and classes/resources under `BOOT-INF/classes/`; look for the expected embedded Tomcat/Jetty/Undertow JARs. If `jar tf` cannot find the embedded runtime even though the dependency tree lists it, inspect Spring Boot Maven/Gradle repackaging, shade/minimize rules, assembly plugins, exclusions, and Docker image copy/layering.

**Do not** treat `java -cp app.jar com.example.App` as equivalent to `java -jar executable.jar`: Boot executable JARs hold nested libraries that require Boot's launcher or standard classpath layout. Run with `java -jar` as produced by the build; when deploying a traditional WAR in external Tomcat, check the WAR deployment path and container logs.

## 5. Root Cause 2: Auto-Configuration Not Enabled or Excluded

### 5.1. What Does `@SpringBootApplication` Actually Do?

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` combines **`@SpringBootConfiguration` + `@EnableAutoConfiguration` + `@ComponentScan`**. When the classpath contains embedded Tomcat and the web type is `SERVLET`, auto-configuration can create `TomcatServletWebServerFactory`. If the main class is replaced by:

~~~java
@Configuration
public class BareApp {
    public static void main(String[] args) {
        SpringApplication.run(BareApp.class, args);
    }
}
~~~

then `@Configuration` alone **does not enable Boot auto-configuration**. When Boot still starts a Servlet WebServer context, having no factory produces the exact **missing `ServletWebServerFactory`** error. Section 10 includes a test that reproduces this intentionally.

**Subtle note:** missing `@ComponentScan` or placing the main class in the wrong package can cause **controllers/services not to be found**, but it **does not by itself cause a missing factory** if auto-configuration still creates the server. Separate application beans from infrastructure factory beans.

### 5.2. Excluding a Specific Auto-Configuration by Mistake

Either configuration below can deliberately disable factory auto-configuration:

~~~java
@SpringBootApplication(
    exclude = ServletWebServerFactoryAutoConfiguration.class
)
class BadServletApplication {
}
~~~

Or:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration
~~~

**This is a broken example configuration**, meant only to **reproduce the failure intentionally** in the lab. For a normal Servlet web app, **removing the exclude** is the proper fix. If a library or team added the exclude to work around another error, find out why and solve that underlying cause instead of blindly adding a custom factory.

### 5.3. `@EnableWebMvc` Is Not a Factory Switch

`@EnableWebMvc` affects how Spring MVC is configured and can prevent Boot's MVC auto-configuration from providing default static resource mappings, message converters, or handlers in the usual way. However, it **does not mean** `ServletWebServerFactoryAutoConfiguration` is disabled. An app with `@EnableWebMvc` can still start Tomcat if a factory is created.

**Do not blame every missing factory on `@EnableWebMvc`** simply because the failure happened after adding the annotation; check the conditions report and actual bean definitions. Conversely, if the app starts up yet static resources return 404 after `@EnableWebMvc`, that is an **MVC mapping issue**, not a missing factory.

### 5.4. Manual Bean: When Is It Truly Needed?

Spring Boot docs allow customizing the server via `WebServerFactoryCustomizer`:

~~~java
@Component
public class ServerTuner implements
        WebServerFactoryCustomizer<TomcatServletWebServerFactory> {
    @Override
    public void customize(TomcatServletWebServerFactory factory) {
        factory.setPort(9090);
    }
}
~~~

This is an **illustrative snippet**, requiring imports from `org.springframework.boot.web.server.WebServerFactoryCustomizer`, `org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory`, and `org.springframework.stereotype.Component`. Using `server.port=9090` in properties is usually simpler.

`WebServerFactoryCustomizer` **does not create a factory bean**: it only customizes an existing bean. If the factory is null/absent, adding a customizer fixes nothing. In very special cases you can declare:

~~~java
@Configuration(proxyBeanMethods = false)
public class ExplicitFactoryConfig {
    @Bean
    ServletWebServerFactory servletWebServerFactory() {
        return new TomcatServletWebServerFactory();
    }
}
~~~

This is also an **illustrative snippet** (requiring imports and the embedded Tomcat dependency), **not the default fix step**. A custom bean causes Boot auto-config to back off; you must ensure there is only **one** matching factory, and that customizers, SSL, ports, session settings, and security policies are still applied. When the root cause is a missing starter or excluded auto-configuration, **fix the root cause** first.

## 6. Root Cause 3: Tests, Custom `ApplicationContext`, or Narrow Component Scan

### 6.1. Slice Tests Do Not Open a Real Server

`@WebMvcTest` + `MockMvc` loads the **MVC test slice**, typically without starting a socket-listening HTTP server. That is **by design**, not a missing factory. If controller tests pass while `java -jar` fails with missing factory, those tests did not cover runtime bootstrap.

By default, `@SpringBootTest` uses `webEnvironment=MOCK`, which likewise does not open an embedded server. To verify startup has a factory/socket:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebRuntimeTest {
    @LocalServerPort
    int port;
}
~~~

The project in section 10 includes a test that calls `/ping` through a real HTTP client and asserts that exactly one Servlet factory exists.

### 6.2. `@ContextConfiguration(classes=...)` Can Change the Configuration Source

A test like:

~~~java
@SpringBootTest(
    classes = BareConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class AccidentalTest {
}
~~~

may point to a `BareConfiguration` that is a plain `@Configuration` instead of the main `@SpringBootApplication`. Without enabling auto-configuration, the Servlet web context cannot find a factory. This snippet **illustrates an anti-pattern**, not a standalone compilable test class.

The usual fix is to point to the Boot main configuration:

~~~java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CorrectIntegrationTest {
}
~~~

or, if testing an isolated `@Configuration`, **do not force `webEnvironment=RANDOM_PORT`** when the goal is only to test beans. Use `ApplicationContextRunner` or `@SpringBootTest(webEnvironment=NONE)` where appropriate. Do not force every test config to boot Tomcat just to satisfy a stack trace.

### 6.3. Nested `@Configuration` in a Test Can Replace the Primary Config

Spring Boot test docs distinguish:
- A nested plain `@Configuration` inside a test can **replace** the primary Boot config for that context.
- A nested `@TestConfiguration` is normally **added to** the primary Boot config, rather than replacing it.

When a test writes:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class MyTest {
    @Configuration
    static class OverrideOnly {
        @Bean MyService service() { ... }
    }
}
~~~

Spring TestContext can treat the nested config as the primary source, dropping Boot auto-configuration if that source lacks `@EnableAutoConfiguration`. That is how a missing `WebServerFactory` happens even when all dependencies are present.

For test-only beans:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class MyTest {
    @TestConfiguration
    static class AddOnly {
        @Bean MyService service() { ... }
    }
}
~~~

This is an **illustrative snippet** needing `MyService` and imports; in real applications, avoid duplicate service beans and ensure the primary Boot config remains active. Use `@TestConfiguration` or explicit `classes=DemoApplication.class` + `@Import(...)` as appropriate.

### 6.4. `new AnnotationConfigServletWebServerApplicationContext(...)` Is Not Self-Sufficient

Constructing a Servlet context manually:

~~~java
new AnnotationConfigServletWebServerApplicationContext(
    BareConfiguration.class);
~~~

can lack a server factory if auto-configuration or the factory bean is not imported. Unlike `SpringApplication.run(@SpringBootApplication)`, manual instantiation skips Boot's `Environment`/listeners/auto-config/web-type setup. If a project integrates Spring into another framework or uses a custom bootstrap, inspect **which context class** is created, **which configs** are registered, and **which context holds the factory bean**.

### 6.5. Parent/Child `ApplicationContext`s

With `SpringApplicationBuilder.parent(...).child(...)`, the parent context does not automatically expose beans the same way a single context does, and vice versa. `ServletWebServerApplicationContext` looks for the factory in its own context (the Boot API states the bean is looked up **in the ApplicationContext itself**). A factory sitting only in the parent is no guarantee it will serve as the child's embedded server factory. Similarly, creating a child Servlet context that only imports controller config can trigger a missing factory even when the parent app starts fine.

Avoid multi-level context hierarchies unless genuinely needed; keep server ownership and auto-configuration in the proper context and test the hierarchy. Do not pull `TomcatServletWebServerFactory` down from a parent via a naive shortcut, as that can create **two embedded servers** or duplicate lifecycles.

### 6.6. Custom Component Scan and Upgrades

`@SpringBootApplication(scanBasePackages=...)` selects application packages to scan. However, Boot auto-configuration imports rely on `@EnableAutoConfiguration`, not simply component-scanning application packages. A custom `@ComponentScan` can cause test slicing to lose `TypeExcludeFilter` and drag unintended beans into tests, but do not claim "wrong `scanBasePackages` is definitely the cause of a missing factory." Check effective auto-config and `@SpringBootApplication` first.

## 7. Root Cause 4: Servlet ↔ Reactive Mismatch During Upgrades

### 7.1. When a Project Has Both Web MVC and WebFlux

In Spring Boot 3.5, when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot **prioritizes MVC/SERVLET**. Adding WebFlux solely to use `WebClient` does not automatically run the application on Reactor Netty.

~~~text
Classpath:
  spring-boot-starter-web
  spring-boot-starter-webflux

Default WebApplicationType:
  SERVLET → requires ServletWebServerFactory
~~~

If you truly want a WebFlux/reactive server:

~~~properties
spring.main.web-application-type=reactive
~~~

**But a property does not conjure a runtime implementation out of thin air.** You need an available reactive web-server factory on the classpath (normally Netty via `spring-boot-starter-webflux`, or Tomcat/Jetty/Undertow per Boot 3.5). When a reactive context is missing a factory, inspect `ReactiveWebServerFactoryAutoConfiguration` and the reactive starter/runtime, **not** just the Servlet factory.

### 7.2. Minimal Reactive Maven Setup (Configuration Snippet)

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Spring Boot 3.5's WebFlux starter typically pulls in Reactor Netty. If a project excludes:

~~~xml
<exclusion>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-reactor-netty</artifactId>
</exclusion>
~~~

without substituting another reactive server implementation, startup can fail due to a missing factory or missing class. This is an **illustrative snippet**; the exclusion must sit inside the appropriate dependency—do not copy it as a standalone dependency.

### 7.3. Jakarta Migration from Boot 2.x to 3.x

Spring Boot 3.x moved to Jakarta EE namespaces. For Servlets:
- Boot 2 / Spring 5 generally used `javax.servlet.*`.
- Boot 3 / Spring 6 uses `jakarta.servlet.*`.
- The containers themselves must also support compatible Servlet/Jakarta APIs.

If a project carries legacy libraries that only provide `javax.servlet.Filter`, or pins an incompatible Tomcat/Jetty version, you can get `NoClassDefFoundError`, `ClassCastException`, `NoSuchMethodError`, or startup failures while creating the factory/server. **Do not lump every upgrade error under "missing factory"**; inspect the real nested cause.

The right fix is aligning **Spring Boot BOM + server implementation + Servlet API + third-party filters/security libraries**. Do not merely search-and-replace `javax` with `jakarta` in a few imports while leaving old dependencies in place.

### 7.4. Upgrading Boot 3 → Boot 4

Starters, modules, packages, and baselines change across major versions. When upgrading:
1. Read the upgrade guide and dependency BOM for the exact branch.
2. Do not copy exact FQNs of `ServletWebServerFactoryAutoConfiguration` or type imports from Boot 3.5 into Boot 4.x without verifying.
3. Do not mix some 3.x `spring-boot-*.jar` files with 4.x to "keep" an embedded server.
4. Check Servlet/Reactive web types and supported embedded servers for the **exact release**, rather than relying on the Boot 3.5 table.
5. Run both `@SpringBootTest(RANDOM_PORT)` and packaged `java -jar` smoke tests.
6. Test WAR/container deployment if using an external Servlet engine.

## 8. Distinguishing Commonly Conflated Errors

| Symptom / log | Error class | First thing to check |
| --- | --- | --- |
| `missing ServletWebServerFactory bean` | **No** factory for Servlet context | Auto-config, container starter, context class/type |
| `missing ReactiveWebServerFactory bean` | **No** reactive factory | WebFlux/runtime dependencies, REACTIVE type, reactive auto-config |
| `multiple ServletWebServerFactory beans` | **Multiple** factories of the same type | Custom `@Bean` colliding with auto-config or >1 server implementation |
| `Port 8080 was already in use` | Factory exists, **socket bind failed** | PID/listening process/`server.port`/network |
| `Unable to start web server` | Wrapper covering many possible causes | Read the final **`Caused by`** or failure analysis |
| `NoClassDefFoundError: jakarta/servlet/...` | Classpath/runtime incompatibility | Servlet API/starter version/scope |
| `BeanCreationException` in customizer | Factory or option bean failed initialization | SSL/keystore/port/custom code |
| `NoSuchMethodError` involving Tomcat/Jetty | Binary version mismatch | BOM, dependency overrides, duplicate JARs |
| `Started Application` yet no HTTP port | Possibly `WebApplicationType.NONE`, `server.port=-1`, or wrong port | Effective properties, context type, listening sockets |
| HTTP `404 Not Found` | Server accepted request; router found no handler/resource | Controller scan, path mapping, context path, security/proxy |
| HTTP `503` during shutdown | Runtime draining or downstream unavailable | Graceful shutdown/health/proxy |
| `ApplicationContextException` when runner fails | Post-refresh startup failure | Runner/error chain; do not assume missing factory |
| `@WebMvcTest` passes while packaged JAR fails | Slice does not start an embedded server | Real HTTP integration + artifact runtime classpath |
| Reactive `Mono` controller compiles yet Boot picks SERVLET | Framework mix | Check both web starters and web application type |
| Factory bean sits in parent context | Context hierarchy ownership | Verify factory is in the child context needing the server |
| Failure happens only in Docker/container | Build image differs from runtime or host-port mapping | Inspect packaged JAR/image/dependencies/entrypoint |

**Do not "fix" with actions at an unrelated layer.** Setting `server.port=0` only helps port conflicts; adding `@RestController` only helps endpoint mapping; changing `server.shutdown=immediate` only alters shutdown behavior; none of those will make a removed `ServletWebServerFactory` bean reappear.

## 9. Ordered 12-Step Debugging Workflow with Concrete Conclusions

### Step 1: Capture the Full Stack Trace, Especially the Root Cause Line

Determine exactly:
- `ServletWebServerApplicationContext` or `ReactiveWebServerApplicationContext`?
- missing factory or multiple factories?
- is the root `Caused by` a `BindException`, classpath error, `IllegalStateException`, or `BeanCreationException`?
- `ApplicationFailedEvent`, exit code, and which build artifact?
- does it occur in the local IDE, `mvn spring-boot:run`, `java -jar`, Docker, or external WAR?

Do not debug from a cropped screenshot that cuts off 20 critical `Caused by` lines.

### Step 2: Verify the Real Requirement: HTTP Server or CLI/Job?

If it is a batch job:
~~~properties
spring.main.web-application-type=none
~~~

is by design. If an API is required, `NONE` is not a fix. Record effective profiles/properties, deployment flags, and `SpringApplication.setWebApplicationType`.

### Step 3: Inspect the Runtime Classpath, Not Just the Visible pom.xml

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Look for `spring-boot-starter-web` or `spring-boot-starter-webflux`, embedded container starters, exclusions, scopes, and version overrides. If using Gradle, inspect `runtimeClasspath` and `dependencyInsight`.

### Step 4: Choose the Correct Web Type

- MVC app → `SERVLET`.
- WebFlux server → `REACTIVE`.
- Non-web tool → `NONE`.
- Both MVC/WebFlux → defaults to MVC/SERVLET unless configured otherwise.

Do not change the type just because an exception mentions "reactive" or "servlet" in a method name; inspect the actual context type.

### Step 5: Check Main/Source Configuration

Is `@SpringBootApplication` or `@EnableAutoConfiguration` present? **Which class** is passed to `SpringApplication.run(...)`? Are there custom `SpringApplicationBuilder`/parent-child contexts? Is a test-specific plain `@Configuration` replacing the primary config?

### Step 6: Search for Auto-Config Exclusions

Search source/config/profiles/CLI for:
~~~text
ServletWebServerFactoryAutoConfiguration
ReactiveWebServerFactoryAutoConfiguration
spring.autoconfigure.exclude
@SpringBootApplication(exclude = ...)
@EnableAutoConfiguration(exclude = ...)
~~~

If you find an exclude, ask **why** it is there and remove it if there is no valid reason. Do not add a manual factory bean to "work around" a hidden exclude.

### Step 7: Print the Condition Evaluation Report

Run from the executable JAR:

~~~bash
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar \
  --debug \
  --server.port=0
~~~

Boot's `--debug` flag prints the auto-configuration conditions report with **positive matches** and **negative matches**. Check:
- `ServletWebServerFactoryAutoConfiguration`;
- `ServletWebServerFactoryConfiguration.EmbeddedTomcat`/`EmbeddedJetty`/`EmbeddedUndertow`;
- `ReactiveWebServerFactoryAutoConfiguration` and nested reactive server conditions;
- `@ConditionalOnClass`, `@ConditionalOnWebApplication`, `@ConditionalOnMissingBean`.

When startup fails before Actuator is reachable, **the startup conditions report + dependency tree** are the primary tools. If the app starts and the Actuator `conditions` endpoint is safely exposed, `/actuator/conditions` helps inspect condition outcomes. **Do not expose this endpoint publicly** because it reveals classpath and bean config. Enable locally/in dev with security policy if needed.

### Step 8: Verify the Factory Is Created in the *Right Context*

Once running, you can inspect `getBeanNamesForType(ServletWebServerFactory.class)` or its reactive equivalent. For a missing-factory error, `ApplicationRunner` code will **not be reached** if startup fails before refresh; use the conditions report, an early listener, or an isolated context test instead of waiting for runner logs.

### Step 9: Inspect the Runtime Packaged Artifact

~~~bash
mvn clean package
jar tf target/server-factory-lab-0.0.1-SNAPSHOT.jar
~~~

Locate the container JAR in `BOOT-INF/lib/`. Compare against the actual artifacts inside the Docker image/CI; do not assume runtime matches your local IDE.

### Step 10: Compare Positive Real HTTP Test Against Negative Injection

A positive `@SpringBootTest(RANDOM_PORT)` test proves factory + connector + route. A negative test without auto-config shows the missing-factory failure path works. If positive passes yet production fails, compare classpath, profiles, startup source, environment, and packaging.

### Step 11: When Switching Servers, Change Dependencies Consistently

Tomcat is the MVC default; when switching to Jetty/Undertow, exclude Tomcat and add the matching starter for **Boot 3.5**. When using Reactive, use a compatible reactive runtime. Never mix multiple factory beans or pin server versions manually.

### Step 12: Lock In Regression Tests and Verify Deployed Versions

Add a `RANDOM_PORT` smoke test to CI, verify the packaged JAR, liveness/readiness probes, and startup logs. For deployments behind a reverse proxy, test the public path and load balancer separately. Consider the task "fixed" only when the app **starts up and serves real HTTP requests** if an HTTP server is required.

## 10. Java 17/Maven Sample Project: Working Factory and Reproducible Failure Tests

**Goal:** A **runnable** project requiring no DB or external services:
- Normal Boot main creates an embedded Tomcat `ServletWebServerFactory`.
- `GET /ping` returns `pong`.
- `RuntimeInspector` logs factory bean names/count and actual port after startup.
- `HealthyWebServerTest` proves a real server and a single factory.
- `MissingFactoryTest` intentionally bootstraps a Servlet context with a **plain `@Configuration` without auto-config**, producing a controlled missing-factory failure.
- `NonWebModeTest` shows `NONE` starts **without requiring** a web server.
- Includes a `--spring.autoconfigure.exclude=...` command to reproduce the failure from the same executable JAR without modifying main code.

**Directory tree:**

~~~text
server-factory-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/serverfactory/
    │   │   ├── DemoApplication.java
    │   │   ├── PingController.java
    │   │   └── RuntimeInspector.java
    │   └── resources/application.properties
    └── test/java/com/example/serverfactory/
        ├── HealthyWebServerTest.java
        ├── MissingFactoryTest.java
        └── NonWebModeTest.java
~~~

### 10.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>server-factory-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
        </plugins>
    </build>
</project>
~~~

This is the **complete POM** for embedded servlet + tests. Do not add `spring-boot-starter-webflux` or Jetty just to debug a servlet app. `starter-web` includes embedded Tomcat by default along with Spring MVC auto-config.

### 10.2. `src/main/java/com/example/serverfactory/DemoApplication.java`

~~~java
package com.example.serverfactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` is placed in the root package `com.example.serverfactory` so it scans `PingController` and `RuntimeInspector` underneath. Do not replace it with plain `@Configuration` in the main app, as that disables Boot auto-configuration that creates the server factory.

### 10.3. `src/main/java/com/example/serverfactory/PingController.java`

~~~java
package com.example.serverfactory;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping(value = "/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong\n";
    }
}
~~~

`PingController` is a Spring MVC handler **only served after Tomcat and `DispatcherServlet` have been created**. If the context lacks a factory, the endpoint will never be served. If the server starts yet `/ping` returns 404, that is a mapping/package-scan issue rather than a missing factory.

### 10.4. `src/main/java/com/example/serverfactory/RuntimeInspector.java`

~~~java
package com.example.serverfactory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class RuntimeInspector implements ApplicationRunner {
    private static final Logger log =
            LoggerFactory.getLogger(RuntimeInspector.class);

    private final ApplicationContext context;

    public RuntimeInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] names =
                context.getBeanNamesForType(ServletWebServerFactory.class);
        log.info("SERVLET_FACTORY_COUNT={}", names.length);
        for (String name : names) {
            log.info("SERVLET_FACTORY_BEAN={} TYPE={}",
                     name, context.getType(name).getName());
        }

        if (context instanceof ServletWebServerApplicationContext web) {
            log.info("WEB_CONTEXT_TYPE={}",
                     web.getClass().getSimpleName());
            log.info("HTTP_PORT={}", web.getWebServer().getPort());
        } else {
            log.info("NON_SERVLET_WEB_CONTEXT={}",
                     context.getClass().getSimpleName());
        }
    }
}
~~~

**Compile note:** In Boot 3.5, the package for `ServletWebServerFactory` is `org.springframework.boot.web.servlet.server.ServletWebServerFactory`; the package for `ServletWebServerApplicationContext` is `org.springframework.boot.web.servlet.context`. Do not copy package FQNs from Boot 4 docs verbatim into Boot 3.5.

**Why doesn't the inspector "fix" the bug by itself?** `ApplicationRunner` only runs **after the context refreshes successfully**. If the context fails while looking up `ServletWebServerFactory`, the inspector is never invoked. When startup succeeds, the inspector is helpful for confirming:
- one factory bean in the Servlet context;
- the implementation bean name/type (usually Tomcat);
- the web context class;
- the actual listening port created by the factory/web server.

Example **expected log format**, not a captured run:

~~~text
SERVLET_FACTORY_COUNT=1
SERVLET_FACTORY_BEAN=tomcatServletWebServerFactory TYPE=org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory
WEB_CONTEXT_TYPE=AnnotationConfigServletWebServerApplicationContext
HTTP_PORT=8080
~~~

Bean names, ordering, and logger prefixes may vary with customization. **Do not assert exact full log lines**; testing the bean type and HTTP response directly is much more stable.

### 10.5. `src/main/resources/application.properties`

~~~properties
spring.application.name=server-factory-lab
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health
logging.level.com.example.serverfactory=INFO
~~~

Bind only to loopback for the lab because `/ping` has no authentication. When running in a container/Kubernetes, `127.0.0.1` is the **container's** loopback; override with an appropriate bind address and network policy before routing to Pod IP. The port is overridden to 0 in JUnit `RANDOM_PORT`.

### 10.6. `HealthyWebServerTest.java` — positive real HTTP integration

File `src/test/java/com/example/serverfactory/HealthyWebServerTest.java`:

~~~java
package com.example.serverfactory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class HealthyWebServerTest {

    @LocalServerPort
    int port;

    @Autowired
    ApplicationContext context;

    @Autowired
    ServletWebServerFactory factory;

    @Test
    void servletFactoryAndRealHttpServerAreAvailable() {
        assertInstanceOf(TomcatServletWebServerFactory.class, factory);
        assertInstanceOf(ServletWebServerApplicationContext.class,
                         context);

        assertEquals(1,
                context.getBeanNamesForType(
                        ServletWebServerFactory.class).length);
        assertTrue(port > 0);

        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port + "/ping")
                .retrieve()
                .body(String.class);
        assertEquals("pong\n", body);
    }
}
~~~

**What this test actually proves:**
- `@SpringBootTest(RANDOM_PORT)` starts a real embedded Tomcat without hardcoding the port.
- The context belongs to the `ServletWebServerApplicationContext` family.
- There is **one** `ServletWebServerFactory` bean and the default implementation is Tomcat per the POM.
- Does the real HTTP GET over the socket return JSON? **No**: this endpoint returns plain text `pong\n`; the assertion matches that exact body.
- `RestClient.create()` is used in the test as a normal HTTP client, without needing tracing auto-config in this demo.

Do not verify solely with `MockMvc.perform(get("/ping"))` because that can pass without a real HTTP port. For a project that chose Jetty/Undertow, swap the Tomcat assertion for the matching factory instead of removing integration tests.

### 10.7. `MissingFactoryTest.java` — reproducing the missing factory error

File `src/test/java/com/example/serverfactory/MissingFactoryTest.java`:

~~~java
package com.example.serverfactory;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MissingFactoryTest {

    // Intentionally omit @EnableAutoConfiguration/@SpringBootApplication.
    // This class is standalone and does not replace the main DemoApplication.
    @Configuration(proxyBeanMethods = false)
    static class BareServletConfiguration {
    }

    @Test
    void bareServletContextFailsWithMissingFactory() {
        SpringApplication app =
                new SpringApplication(BareServletConfiguration.class);
        app.setWebApplicationType(WebApplicationType.SERVLET);
        app.setBannerMode(Banner.Mode.OFF);

        AtomicReference<Throwable> failure =
                new AtomicReference<>();
        app.addListeners(
            (ApplicationListener<ApplicationFailedEvent>) event ->
                failure.set(event.getException()));

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run(
                    "--server.port=0",
                    "--spring.main.log-startup-info=false"));

        assertNotNull(thrown);
        assertNotNull(failure.get(),
                "Expected ApplicationFailedEvent");
        assertTrue(hasMessage(failure.get(),
                "ServletWebServerFactory"),
                "Missing factory reason should appear in cause chain");
    }

    private static boolean hasMessage(
            Throwable error, String needle) {
        for (Throwable e = error;
             e != null; e = e.getCause()) {
            if (String.valueOf(e.getMessage()).contains(needle)) {
                return true;
            }
        }
        return false;
    }
}
~~~

**Why is this negative test reliable?**
1. The project test classpath **has** `spring-boot-starter-web`/Tomcat, so Servlet APIs are available.
2. `setWebApplicationType(SERVLET)` instructs Boot to create a Servlet web-server context instead of falling back to `NONE`.
3. `BareServletConfiguration` has only `@Configuration`, without `@EnableAutoConfiguration`.
4. With no auto-config creating `ServletWebServerFactory`, startup fails **before binding a port**.
5. The test captures `ApplicationFailedEvent` via a listener registered **before `run`**, since bean listeners inside the context may not exist when the failure occurs.
6. The test checks the cause chain for the factory name, rather than matching an exact string across versions.

**Do not call `app.run()` again inside this test to "heal" the error**, and do not add a `@Bean` factory to `BareServletConfiguration`: doing so destroys the exact failure scenario under test. The positive path already has its own `HealthyWebServerTest`.

### 10.8. `NonWebModeTest.java` — NONE needs no factory

File `src/test/java/com/example/serverfactory/NonWebModeTest.java`:

~~~java
package com.example.serverfactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class NonWebModeTest {

    @Test
    void noneModeRunsWithoutServletFactory() {
        SpringApplication app =
                new SpringApplication(DemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context =
                app.run("--server.port=0")) {
            assertFalse(
                context instanceof ServletWebServerApplicationContext);

            assertEquals(0,
                context.getBeanFactory().getBeanNamesForType(
                    ServletWebServerFactory.class).length);
        }
    }
}
~~~

**Meaning:** `NONE` is not a "missing factory startup failure." It is a **non-web context** created cleanly; therefore having no factory or HTTP port is **expected behavior**. If a production server unexpectedly fails to listen, check `spring.main.web-application-type=none` or programmatic `WebApplicationType` overrides before changing dependencies.

**Do not use `NONE` as a substitute test** for `@SpringBootTest(RANDOM_PORT)` on an API that must accept requests: a non-web test can pass even when the real HTTP app is broken.

### 10.9. Running Tests and the Application

~~~bash
java -version
mvn clean test
mvn clean package
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar
~~~

In a second terminal:

~~~bash
curl -i http://127.0.0.1:8080/ping
~~~

**Expected response shape:**

~~~http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

pong
~~~

The actual body includes a trailing newline from Java `"pong\n"`, and header formatting/casing may vary across embedded server versions. Do not treat `HTTP/1.1 200` as captured observed output — it is the **expected semantics** of the code.

### 10.10. Reproducing Missing Factory via CLI on the Same JAR

**Use only on a lab machine, never in production config:**

~~~bash
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar \
  --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration \
  --server.port=0 \
  --debug
~~~

When the factory auto-configuration is excluded, the Servlet web context still requires a factory, so **startup is expected to fail** with a message mentioning `ServletWebServerFactory`. Exact error text/failure analysis depends on the Boot version; you will see the direct reason in the conditions report and logs.

To fix it, **remove the `--spring.autoconfigure.exclude=...` option** and run the JAR normally. This demonstrates first-hand that adding `@RestController`, changing the port, or adding `WebServerFactoryCustomizer` cannot substitute for proper auto-configuration.

## 11. If You Really Need WebFlux: Minimal Reactive Comparison Project

This is **a separate project**; do not mix its dependencies into the main servlet project. A WebFlux server in Boot 3.5:

**Maven dependency snippet:**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

**Main class:**

~~~java
package com.example.reactivedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

**Reactive controller:**

~~~java
package com.example.reactivedemo;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveController {
    @GetMapping("/ping")
    public Mono<String> ping() {
        return Mono.just("reactive-pong\n");
    }
}
~~~

With the right dependency and reactive web application type, Boot selects `ReactiveWebServerApplicationContext` and usually creates `NettyReactiveWebServerFactory` from Reactor Netty. **This is a reference snippet**, not a complete standalone project since it omits its own parent POM, directory structure, properties, and tests. If you need to run this project, use a Maven parent/POM similar to section 10, replace `spring-boot-starter-web` with `spring-boot-starter-webflux`, change `groupId/artifactId`, and place both classes under the same root package. Do not retain the servlet starter if the goal is to test pure WebFlux selection.

**Test idea:**

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.main.web-application-type=reactive"
)
class ReactiveHttpTest {
    @LocalServerPort int port;
    // Use an HTTP client to call localhost:port/ping and
    // verify the ReactiveWebServerFactory bean in the context.
}
~~~

This is an **illustrative test snippet**; do not copy it expecting it to compile as-is since it lacks full imports and body. For WebFlux, `@WebFluxTest` is the equivalent slice test at the reactive web layer, and **does not** prove a runtime port. If you hit a missing `ReactiveWebServerFactory` error, inspect reactive runtime/transitives and `ReactiveWebServerFactoryAutoConfiguration` rather than adding a Servlet-specific bean.

### 11.1. Is Having Both MVC and WebFlux in One App Always a Bug?

Not necessarily. An MVC app can use `WebClient` (and the WebFlux dependency) for outbound HTTP calls while still running Tomcat + `DispatcherServlet`. However, you must know which stack the server is running; a controller method returning `Mono` does not automatically imply a Netty server.

**Distinguish:**
- **MVC server + WebClient:** servlet factory belongs to Tomcat, reactive client is a client library.
- **WebFlux server + Reactor Netty:** reactive factory belongs to Netty.
- **Reactive server running Tomcat/Jetty:** requires the corresponding **reactive factory**, not a servlet factory just because the container name is the same.
- **Non-web scheduled job using WebClient:** can set `WebApplicationType.NONE`, needing no HTTP listener.

## 12. Spring Boot Actuator, `--debug`, and the Conditions Report

### 12.1. Safe Automated Investigation

Run locally:

~~~bash
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar \
  --debug \
  --server.port=0
~~~

When `--debug` is enabled, Spring Boot prints the **CONDITIONS EVALUATION REPORT**, containing:
- Positive matches: auto-configuration conditions that were satisfied.
- Negative matches: excluded due to missing class, existing bean, wrong web type, or non-matching property.
- Unconditional classes.

If `ServletWebServerFactoryAutoConfiguration` shows up as a positive match while nested `EmbeddedTomcat` is negative, investigate embedded server classes/dependencies. If the entire servlet factory auto-config is negative due to **Not a servlet web application**, check the application type. If Boot says a custom factory bean already exists, check whether that bean has the right type and resides in the context starting the server.

**Do not analyze the report by a single keyword.** The conditions report only explains why conditions matched or did not match at evaluation time; combine it with the runtime bean count and actual exception.

### 12.2. Actuator `conditions` Is Not the Only Tool

If the app still starts up, you can configure internally:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

Then, with proper authorization, inspect `GET /actuator/conditions` to view condition outcomes. **Do not** open this endpoint unauthenticated on the Internet; it leaks runtime classpath and configuration topology. When the app fails before creating the HTTP server, the endpoint is unavailable to query; rely on `--debug`, early listeners, and CI logs.

### 12.3. `ConditionEvaluationReport` in Java (Advanced Snippet)

Once a context has refreshed:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(
                configurableContext.getBeanFactory());
~~~

Import `org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` and `ConfigurableApplicationContext`; this is an **illustrative snippet** requiring a properly typed `configurableContext`. In auto-configuration tests, you can use `ApplicationContextRunner` + `ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` to log outcomes.

**Do not put the code above inside an `ApplicationRunner` expecting it to debug a context that fails to start**: runners are never executed when the context fails early. For startup-failure diagnostics, a listener registered before `SpringApplication.run` and Boot `--debug` are far more useful.

### 12.4. Why Don't Slice Tests Need a Factory?

Per Boot testing docs, `@WebMvcTest` creates an auto-configured MVC slice with `MockMvc`, needing no real embedded server. `@SpringBootTest(MOCK)` creates a mock servlet environment. **Missing `ServletWebServerFactory` only applies when starting a real `ServletWebServerApplicationContext`**; not finding a factory bean inside a slice is not a "failure" to fix.

## 13. WAR, `provided` Scope, and External Containers

Example traditional WAR with `provided` embedded Tomcat dependency:

~~~xml
<packaging>war</packaging>

<!-- ... project dependencies ... -->

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

This requires a class extending `SpringBootServletInitializer`, proper WAR packaging, and an external Servlet container version compatible with Boot 3.5 / Jakarta Servlet API. This is a POM **snippet**, not a replacement for the full WAR guide.

**Traps:**
- Running `java -jar app.jar` built as an executable JAR without bundling an embedded container and expecting an external Tomcat to materialize.
- Seeing `provided` in a traditional WAR and immediately deleting it: it may be right for the deployment target.
- Deploying a WAR into an older external Tomcat that does not support Jakarta EE 10 / Servlet 6: classloading can fail differently from a missing factory.
- Packaging an executable WAR with the Spring Boot plugin puts provided embedded servers in `WEB-INF/lib-provided`; it can still run via `java -jar app.war` per the docs. Hence claiming "`provided` always loses the runtime container" is **false**.

**Choose the deployment model before choosing the scope:** an embedded runnable JAR differs from an external WAR. Verify the actual artifact and entrypoint in CI/staging, not just in a local build.

## 14. Upgrades and Version Dependencies

### 14.1. Switching Server Implementations

When swapping Tomcat for Jetty/Undertow in **Boot 3.5**, use Boot starters matching the BOM version. Test:
- Exactly one `ServletWebServerFactory` bean exists.
- The factory type matches the selected server.
- `GET /ping` actually returns 200 over a random port.
- Session/SSL/HTTP2/static/Actuator still behave per contract.
- Graceful shutdown lifecycle is tested under the new server's behavior.

**Do not copy** factory bean class names from docs of another major Boot version. Check the corresponding API and dependency graph.

### 14.2. Dependency Overrides and Binary Mismatch

A parent POM or Gradle constraints can force `tomcat-embed-core` or `jetty-server` to a version different from the Boot BOM. The result can be `NoSuchMethodError`/`LinkageError` right when instantiating the factory, or a condition mismatch—**not** necessarily a missing bean. The stable choice: let Spring Boot dependency management pin versions consistently, and override only with a tested compatibility matrix.

### 14.3. Native Image / AOT

With GraalVM native images, runtime classpath/reflection hints and **build-time application type** must agree. If an image is built with `WebApplicationType.NONE` and you try switching to `SERVLET` at runtime, the web server classes and bean definitions may not have been compiled into the image. This is not like a JVM JAR with the full classpath. The Spring Boot issue tracker has warned that the correct web application type must be set **at native image build time**, not just on the runtime command line.

**Workflow:** establish the intended web type before AOT/native build, keep the same configuration at runtime, and run a native image `GET /ping` smoke test. Do not pass `--spring.main.web-application-type=servlet` at runtime to a binary optimized for `NONE` and expect a factory to appear.

## 15. Anti-Patterns to Avoid

1. **Manually adding `@Bean TomcatServletWebServerFactory` the moment you see missing factory.** It can mask bad auto-config/exclusions/scopes and cause duplicate factories later.
2. **Changing `server.port=0` to fix a missing bean.** Random port only resolves bind collisions after a factory exists.
3. **Adding `@RestController` expecting Tomcat to appear.** Controllers handle requests; they do not create HTTP listeners.
4. **Using `WebServerFactoryCustomizer` to fix a missing factory.** A customizer is not a factory bean.
5. **Replacing `@SpringBootApplication` with `@Configuration` just to make bootstrap minimal.** You must account for auto-configuration imports.
6. **Blindly adding `@EnableWebMvc`/`@EnableWebFlux`.** They alter web framework configuration rather than replacing the embedded server runtime.
7. **Forcing `WebApplicationType.SERVLET` when only a reactive runtime exists.** The two factory interfaces differ; there is no automatic Netty → Servlet conversion.
8. **Adding Tomcat, Jetty, and Undertow all together to see which one starts.** This causes unexpected conditions or multiple candidates and is hard to audit.
9. **Running only `@WebMvcTest` before releasing a Docker image.** Slice tests do not catch runtime packaging or port-bind failures.
10. **Slapping a broad `@ComponentScan` everywhere to "expose beans".** It can cause bean conflicts/circular dependencies and does not fix auto-config.
11. **Reading only the top-level `Unable to start web server` line.** You must read the deepest cause and conditions report.
12. **Equating external WARs with executable JARs.** Scope and container ownership differ.
13. **Forcing old `javax.servlet` JARs into Spring Boot 3.5.** Jakarta namespaces differ and cause binary errors.
14. **Using `server.port=-1` to bypass factory errors.** It keeps a web context while exposing no HTTP endpoints.
15. **Disabling Actuator security to read `/conditions`.** Expose only on internal networks with authentication.
16. **Letting production machines patch dependencies when startup fails.** Dependency resolution and container images must be reproducible from CI.
17. **Treating the lack of a factory in `@WebMvcTest` as a bug.** Slices do not require an embedded server; using the right test layer matters.
18. **Relying on exact failure log strings across Boot versions/OSes.** Test cause/type/missing-bean behavior instead of a full literal stack trace.

## 16. Scenario-Based Diagnostic Table

| Scenario | Common mechanism | Fix / verification |
| --- | --- | --- |
| Created a controller and ran with a `@Configuration` main | Missing `@EnableAutoConfiguration` | Use `@SpringBootApplication` / proper auto-config |
| Boot MVC build yet `missing ServletWebServerFactory` | Container dependency excluded or factory auto-config didn't match | Maven runtime tree + conditions report |
| `spring-boot-starter-web` excludes Tomcat | No default Servlet container left | Add Jetty/Undertow starter or restore Tomcat |
| `spring.autoconfigure.exclude` lists Servlet factory auto-config | Factory deliberately disabled | Remove exclude if embedded HTTP is needed |
| Running CLI worker, log has no HTTP port | `WebApplicationType.NONE` | Normal if no web needed |
| Running API yet `NONE` from env/profile | Non-web context, no endpoints | Remove/change override to the proper web type |
| Running Servlet with only Reactor Netty | Reactive runtime is not a Servlet factory | Switch stack or add the proper Servlet container |
| Running WebFlux with Reactor Netty excluded | No reactive HTTP factory | Restore Netty or use a supported reactive server |
| Both MVC + WebFlux starters | Boot defaults to MVC | Clarify intent, configure reactive if desired |
| JUnit custom `@Configuration` + `RANDOM_PORT` | Lost primary Boot auto-config | Point to main `@SpringBootApplication` or use `@TestConfiguration` |
| Manually created child Servlet web context | Factory not in that context | Put auto-config/factory in the right child context |
| Custom `ServletWebServerFactory` `@Bean` | Default backs off, possibly 2 beans | Check factory count/type and ownership |
| Upgraded Boot 2→3, filter still uses `javax.servlet` | Jakarta binary incompatibility | Upgrade third-party library/server API properly |
| Upgraded Boot 3→4, kept old auto-config packages | Classes/packages moved, auto-config mismatch | Follow migration docs and new BOM |
| Native image built `NONE`, runtime forces `SERVLET` | AOT lacks required web classes/beans | Rebuild native image with the right web type |
| Tomcat exists yet `Port 8080 in use` | Socket bind conflict; factory **already exists** | Check PID/port, `server.port`, `RANDOM_PORT` |
| App boots yet GET returns 404 | Controller scan/route/static/security | Debug mappings; do not swap server factory |
| Unreachable from container host | Loopback bind or Docker port publish | `server.address`/ports/network |
| Boot JVM JAR runs, Docker image fails | Different artifact/classpath/layer | Inspect `BOOT-INF/lib` and image contents |
| Executable WAR has `provided` Tomcat | `lib-provided` per Boot plugin | Understand WAR deploy model; `provided` isn't always wrong |

## 17. Final Verification Checklist

**Intent:** Does the HTTP service need MVC/Servlet, WebFlux/Reactive, or a non-web CLI?

- [ ] Captured exact stack trace and deepest `Caused by`.
- [ ] Determined effective `SERVLET`, `REACTIVE`, or `NONE` (classpath + properties + API override).
- [ ] Identified runtime context type instead of guessing from controllers.
- [ ] MVC has `spring-boot-starter-web` and embedded Tomcat or compatible Jetty/Undertow.
- [ ] Reactive has WebFlux + a reactive HTTP server implementation.
- [ ] `@SpringBootApplication`/`@EnableAutoConfiguration` is active on the Boot context needing a server.
- [ ] Factory auto-configuration was not excluded by mistake.
- [ ] Conditions report explains embedded server nested conditions.
- [ ] Exactly **one** factory bean exists in the right context when an embedded server is required.
- [ ] No dependency scope/exclusion/BOM override strips required runtime classes.
- [ ] Servlet factory is not confused with reactive factory.
- [ ] Custom `WebServerFactoryCustomizer` is not being used to create a missing bean.
- [ ] Servlet/Jakarta versions are compatible with Spring Boot 3.x.
- [ ] `@SpringBootTest(RANDOM_PORT)` test makes a real HTTP call to `/ping`.
- [ ] Negative missing-factory/failure-event test covers the targeted isolated context.
- [ ] Checked `server.port=-1` vs `NONE` and `server.port=0`.
- [ ] Packaged executable JAR/WAR has the right runtime dependencies and entrypoint.
- [ ] In containers, bind address, exposed ports, ingress, and security are properly configured.
- [ ] Native/AOT build-time web type matches runtime.
- [ ] CI smoke tests cover version upgrades, factory type, HTTP port, and startup failures.

## 18. Self-Check Questions

1. How does `ServletWebServerFactory` differ in responsibility from `DispatcherServlet`?
2. How many factory beans does `ServletWebServerApplicationContext` require?
3. Does having `@RestController` guarantee Tomcat will start?
4. Are reactive and servlet factories interchangeable?
5. Which embedded server does `spring-boot-starter-web` usually bring to runtime?
6. Excluding Tomcat without adding a replacement server can lead to what kinds of failures?
7. Which three core annotations make up `@SpringBootApplication`?
8. Why can plain `@Configuration` leave a Servlet context missing a factory?
9. Does `@EnableWebMvc` make the factory disappear by default?
10. Does `WebServerFactoryCustomizer` create a server factory?
11. How do `spring.main.web-application-type=none` and `server.port=-1` differ?
12. Does `server.port=0` fix a missing factory?
13. When both MVC and WebFlux are present, which stack does Boot 3.5 select by default?
14. Is having no `ServletWebServerFactory` in `@WebMvcTest` a bug?
15. What does `@SpringBootTest(webEnvironment=RANDOM_PORT)` prove that `MockMvc` does not?
16. Why does nested `@TestConfiguration` behave differently from nested plain `@Configuration` in JUnit?
17. Why should an `ApplicationFailedEvent` listener be registered before `run` in a failure test?
18. Why does the missing-factory test explicitly set `WebApplicationType.SERVLET`?
19. Which commands reveal the Maven runtime dependency graph and exclusions?
20. What does `--debug` reveal about auto-configuration?
21. When `ServletWebServerFactoryAutoConfiguration` is positive yet `EmbeddedTomcat` is negative, what do you investigate?
22. Why shouldn't you declare a manual `@Bean TomcatServletWebServerFactory` to silence every error?
23. At which step does `Port 8080 was already in use` occur relative to looking up the factory?
24. If Boot logs `Started Application` yet HTTP returns 404, does it mean a missing factory?
25. Does the external WAR model require an embedded factory during external Tomcat bootstrap?
26. How can a `provided` container starter be packaged inside an executable WAR?
27. How did the Boot 2→3 migration affect the Servlet namespace?
28. Can a native image built as non-web enable a web server via a runtime property alone?
29. What does a `NoSuchMethodError` in a Tomcat factory usually indicate?
30. When upgrading Spring Boot 3→4, should you keep all imports/dependency names from Boot 3.5 unchanged?

**Summary answers:** (1) The factory creates the HTTP server; `DispatcherServlet` handles MVC requests. (2) Exactly one. (3) No. (4) No. (5) Tomcat. (6) Different type detection, classpath/missing-factory failures. (7) `SpringBootConfiguration`/`EnableAutoConfiguration`/`ComponentScan`. (8) It does not enable Boot auto-config. (9) No. (10) No. (11) Non-web context vs. web context not exposing HTTP. (12) No. (13) MVC/SERVLET. (14) No, slices do not start an embedded container. (15) Real web server/socket/bean context. (16) `TestConfiguration` augments the primary config; plain config can replace it. (17) The context may not exist when startup fails. (18) Forces a servlet context despite minimal config. (19) `mvn dependency:tree`/`help:effective-pom`. (20) Positive/negative condition matches. (21) Embedded server classes and `@ConditionalOnMissingBean`. (22) Masks root causes/creates duplicate beans. (23) After factory lookup, when binding the socket. (24) No, the server is running so it is routing/port/proxy. (25) Not like an embedded JAR. (26) `WEB-INF/lib-provided`. (27) `javax.servlet` → `jakarta.servlet`. (28) Must rebuild with the proper web type/closed-world config. (29) Binary version mismatch. (30) No; read the migration guide.

## 19. Official Documentation

- **Spring Boot 3.5 — Servlet Web Applications / ServletWebServerApplicationContext**, mechanism for finding a single factory bean: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- **Spring Boot 3.5 — Embedded Web Servers**, switching servers, disabling HTTP, `server.port=-1`, random port, custom factory: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- **Spring Boot 3.5 — Testing Spring Boot Applications**, `MOCK`/`RANDOM_PORT`, web application type, and nested `@TestConfiguration`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Boot 3.5.16 API — WebApplicationType**, `SERVLET`/`REACTIVE`/`NONE`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/WebApplicationType.html
- **Spring Boot 3.5.16 API — ServletWebServerApplicationContext**, factory bean lookup: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html
- **Spring Boot 3.5.16 API — ServletWebServerFactoryAutoConfiguration**, auto-config conditions: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/ServletWebServerFactoryAutoConfiguration.html
- **Spring Boot 3.5.16 API — @SpringBootApplication**, `@EnableAutoConfiguration` and component scan: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- **Spring Boot 3.5.16 API — @EnableAutoConfiguration**, container factory and custom bean backing off: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- **Spring Boot 3.5.16 API — ReactiveWebServerApplicationContext/ReactiveWebServerFactoryAutoConfiguration**: https://docs.spring.io/spring-boot/3.5/api/java/allclasses-index.html
- **Spring Boot — Creating Your Own Auto-configuration**, condition report and `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- **Spring Boot 3.5 — Traditional Deployment**, WAR/external container and provided runtime: https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html
- **Spring Boot 3.5.16 release/OSS support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
