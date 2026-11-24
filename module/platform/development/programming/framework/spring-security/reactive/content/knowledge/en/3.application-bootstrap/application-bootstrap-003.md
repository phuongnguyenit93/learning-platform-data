# Identifying a Reactive Application When Both Spring MVC and WebFlux Dependencies Are Present

> **Scope:** Bootstrapping and verifying **Spring Boot 3.x + Spring Security 6.x** in the Spring Security reactive module. This lesson focuses on **which web stack is actually running** when both Spring MVC and Spring WebFlux are on the classpath. Java snippets use Java 17+ in a Spring Boot project with the corresponding dependencies; they are not standalone Java SE programs compiled with `javac`.

## Learning objectives

After this lesson, you can:

1. Explain why adding `spring-boot-starter-webflux` **does not automatically turn** a Spring MVC application into a reactive web server.
2. Predict whether Spring Boot selects `SERVLET` or `REACTIVE` in common dependency combinations.
3. Verify the actual application type using `ApplicationContext`, auto-configuration conditions, and security chain indicators, rather than guessing from starter names, Netty, or a `Mono` return type.
4. Explicitly start WebFlux when truly needed, then select the right Spring Security APIs for reactive.
5. Write tests to prevent a reactive application from accidentally reverting to MVC after dependency changes.

## 1. Common trap: both starters are present, yet the application is still MVC

Suppose a Spring Boot application's `build.gradle` declares:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Under default auto-detection, **Spring Boot selects Spring MVC (Servlet)** when both Spring MVC and WebFlux are present. This is intentional behavior: many MVC applications add WebFlux solely to use the reactive HTTP client `WebClient` without wanting to change the server-side web stack.

Therefore, the following statements are **not equivalent**:

- "Has `spring-webflux` dependency" ≠ "server runs WebFlux".
- "Has a `WebClient` bean" ≠ "controllers go through `DispatcherHandler`".
- "Controller returns `Mono<T>` or `Flux<T>`" ≠ "server is WebFlux"; Spring MVC also supports handling some reactive return types on top of Servlet.
- "Logs show Reactor Netty/Netty on the classpath" ≠ "HTTP requests are processed by the reactive server".
- "Uses `@RestController`" ≠ "MVC or WebFlux was selected"; the same annotation can be used in both.

**Key takeaway:** the **web application** type is established when Spring Boot creates the application context. At that moment, starters and bootstrap configuration determine the server-side HTTP infrastructure; Spring Security follows whichever infrastructure is actually running.

### 1.1 Three WebApplicationType values

`org.springframework.boot.WebApplicationType` has three values:

| Value | Meaning | Common indicators |
| --- | --- | --- |
| `SERVLET` | Servlet-based web application | Spring MVC, `DispatcherServlet`, `HttpSecurity`, and servlet filter chain |
| `REACTIVE` | Reactive web application | Spring WebFlux, `DispatcherHandler`, `ServerHttpSecurity`, and reactive web filter chain |
| `NONE` | Does not start a web server as a web application | CLI/batch/job without a Boot-created HTTP server |

For a typical Boot application without forcing the web type: only WebFlux starter → `REACTIVE`; only Web MVC starter → `SERVLET`; both → `SERVLET`. This is the **default rule**, which can be overridden by an explicit application choice.

## 2. At which layers do MVC, WebFlux, and Security differ?

| Aspect | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Request dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Spring Boot web server context | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Request security | Servlet `Filter` / `FilterChainProxy` | Reactive `WebFilter` / `WebFilterChainProxy` |
| Web security configuration | `HttpSecurity` creates `SecurityFilterChain` | `ServerHttpSecurity` creates `SecurityWebFilterChain` |
| Annotation enabling security | `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| Authorization declaration | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Accessing security context | `SecurityContextHolder` bound to execution thread in Servlet style | `ReactiveSecurityContextHolder` via Reactor Context |
| User details when needed | `UserDetailsService` | `ReactiveUserDetailsService` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| Available HTTP client | `RestClient`, `RestTemplate`, or `WebClient` | `WebClient` is the right choice for non-blocking pipelines |

**Note:** the WebFlux foundation can run on Reactor Netty **or** another compatible server/container such as Tomcat/Jetty via an adapter mechanism. The server name is not a decisive test; inspect the application context and request pipeline.

In a reactive stack, calling thread-blocking APIs (`block()`, synchronous JDBC on the event loop) can destroy the benefits of non-blocking execution. However, changing dependencies to WebFlux **does not automatically** make every library or query non-blocking.

## 3. Check dependencies before running

In a Spring Boot project using Gradle, inspect dependencies on **`runtimeClasspath`**, not just direct declaration lines.

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
```

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`.

Meaning:

- `spring-webmvc` is present → Spring MVC infrastructure is available. If `spring-webflux` is also present, Boot defaults to preferring MVC.
- `spring-webflux` is present → WebFlux and `WebClient` are available, **not yet concluding** the server runs reactive.
- `spring-boot-starter-web` typically pulls in `spring-webmvc` and the Servlet web server starter.
- `spring-boot-starter-webflux` typically pulls in `spring-webflux` and the Reactor Netty starter.
- A third-party library or shared module can add `spring-webmvc` transitively; `dependencyInsight` helps trace the path.

If you intend pure WebFlux, a sensible first step is to **remove the unnecessary MVC starter from the application module** and inspect the runtime classpath after Gradle resolves. If both must be kept for a specific goal, you must explicitly choose `REACTIVE` at bootstrap.

**Do not blindly exclude dependencies from other libraries.** Identify which component needs Spring MVC and check the impact before using `exclude`; removing a transitive dependency can break software that relies on it.

## 4. Reproducible test: reading the actual ApplicationContext type

Here is a direct **runtime** check. In the Spring Boot 3.x application that has the starters from Section 1, create the file:

`src/main/java/com/example/webstack/WebStackDemoApplication.java`

```java
package com.example.webstack;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebStackDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebStackDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner reportWebStack(ApplicationContext context) {
        return args -> {
            String stack;
            if (context instanceof ReactiveWebServerApplicationContext) {
                stack = "REACTIVE";
            } else if (context instanceof ServletWebServerApplicationContext) {
                stack = "SERVLET";
            } else {
                stack = "OTHER";
            }

            System.out.println("WEB_STACK=" + stack);
            System.out.println("CONTEXT_CLASS="
                + context.getClass().getName());
        };
    }
}
```

**Code explanation:**

- `ApplicationRunner` runs after Spring Boot initializes the context successfully.
- `ReactiveWebServerApplicationContext` and `ServletWebServerApplicationContext` indicate the **actual server context type**. Both classes are a stronger signal than seeing the `DispatcherHandler` class on the classpath.
- The `OTHER` branch covers cases where a normal web server is not initialized, such as `WebApplicationType.NONE`; do not rush to blame this as a reactive error.
- The `CONTEXT_CLASS` line helps learners see the concrete class (usually starting with `AnnotationConfig...`). In applications creating multiple contexts, make sure you observe the **main web server application context**, not a management context or test slice.

Run using the Gradle wrapper:

```bash
./gradlew bootRun
```

With **both starters** and no stack-forcing configuration, the verification line must be:

```text
WEB_STACK=SERVLET
```

Spring Boot also prints startup logs and the `CONTEXT_CLASS=...` line; the block above only shows the **conclusion line** to avoid presenting a fabricated full stdout that varies by version and environment.

### 4.1 Why not just look for DispatcherHandler?

`DispatcherHandler` is a class in the `spring-webflux` library, so `Class.forName(...)` succeeding only proves the JAR is on the classpath. Even the bean count of a certain type can be affected by manual configuration, test slices, or other contexts.

When you have to conclude "which type is the main HTTP application running", prioritize:

1. The actual runtime `ApplicationContext` type.
2. Which auto-configuration is activated and which request dispatcher is in use.
3. Whether the security filter chain and request handling operate on the right stack.
4. Starters/classpath as evidence **explaining the cause**, not the final proof.

## 5. How to explicitly choose WebFlux when both MVC and WebFlux must be kept

### 5.1 Declaring via application.yml

When both starters must still exist, set in `src/main/resources/application.yml`:

```yaml
spring:
  main:
    web-application-type: reactive
```

Then restart the same application. With a compatible server factory and configuration, the observed line changes to:

```text
WEB_STACK=REACTIVE
```

The `spring.main.web-application-type` property is processed by Spring Boot when creating the context; place it where bootstrap configuration is loaded. Check profiles, environment variables, command-line args, and deployed config because higher-priority sources can override the value.

You can pass it directly on the run command to inspect without changing shared configuration:

```bash
./gradlew bootRun --args='--spring.main.web-application-type=reactive'
```

On Windows PowerShell, run the corresponding command with `.\gradlew.bat`. If the project has custom `bootRun` logic, check how arguments are passed to the Java program.

### 5.2 Selecting via startup code

When you do not want to rely on configuration files, set `WebApplicationType` before `run()`:

```java
package com.example.webstack;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebStackDemoApplication {
    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(WebStackDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.REACTIVE);
        app.run(args);
    }
}
```

This is an **alternative way to write the `main` part** of the previous example; do not put two classes with the same name in one package. If you want to keep the `ApplicationRunner` used for observation, keep the probe bean in a separate `@Configuration` or inside this same class.

### 5.3 Design decision to prioritize

If the server is truly WebFlux and has no MVC server functionality, **you should remove `spring-boot-starter-web`** from the application, avoiding unnecessary dependencies and avoiding stack-switching incidents during upgrades. Forcing `REACTIVE` while keeping extensive Servlet infrastructure is a valid option, but requires checking auto-configuration, dependency compatibility, and security configuration upon deployment.

If you need **an MVC server + WebClient** to call other services, keep the `SERVLET` default. `WebClient` is an HTTP client library; using it does not require switching the entire HTTP server to WebFlux.

## 6. Why does the web stack choice directly impact Spring Security?

Spring Security has two **configuration sets meant for two different runtimes**:

| If the app actually is... | Right configuration bean | DSL and pipeline |
| --- | --- | --- |
| `SERVLET` | `SecurityFilterChain` | `HttpSecurity`, `authorizeHttpRequests`, Servlet filter chain |
| `REACTIVE` | `SecurityWebFilterChain` | `ServerHttpSecurity`, `authorizeExchange`, `WebFilter` |

Do not treat these two beans as freely interchangeable variants. A reactive configuration using `@EnableWebFluxSecurity` does not turn an MVC app into WebFlux, and a servlet `SecurityFilterChain` does not protect requests passing through a reactive web filter chain. When Spring Boot selects the wrong type, the security configuration you intended to apply may not initialize, may initialize wrongly, or may be replaced by another security setup; **you must test runtime and actual requests**, not just see annotations in source code.

### 6.1 Illustrative configuration for the reactive stack

Once the application **has been confirmed** to run WebFlux, configure:

```java
package com.example.webstack;

import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Key points:**

- `@ConditionalOnWebApplication(type = REACTIVE)` is a guard so this config only participates when the app has a reactive web context. It is **not a command to switch web type**.
- `@EnableWebFluxSecurity` enables Spring Security infrastructure for WebFlux. `SecurityWebFilterChain` is applied as a reactive `WebFilter`.
- `authorizeExchange` works with `ServerWebExchange`; `pathMatchers("/public/**")` allows public routes, while remaining routes must be authenticated.
- `httpBasic` here is only to demo a simple authentication mechanism; production systems may use session/OIDC or JWT Resource Server depending on the problem.
- This configuration **does not disable CSRF**. For browsers using cookies, keep CSRF; only consider disabling it on clearly defined Bearer-only APIs.
- If a servlet `@EnableWebSecurity`/`SecurityFilterChain` configuration still exists in the project, identify the active scope and remove the stack-mismatched configuration. Do not maintain two different policies and assume both are applied together.

To use the classes above, `spring-boot-starter-security` is required; a pure WebFlux demo can use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

The two dependency groups above are a **simpler standardized form** for a WebFlux server application. Security class names and APIs in the example belong to Spring Security 6.x / Spring Boot 3.x.

### 6.2 If intentionally staying with Servlet

An MVC application using `WebClient` still configures server-side security in MVC style:

```java
package com.example.webstack;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain servletSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

This is an **alternative option** when the app chooses MVC; do not use it simultaneously with `ReactiveSecurityConfig` in the same application to infer the stack. Having `WebClient` in the project does not turn `HttpSecurity` into `ServerHttpSecurity`.

## 7. Three sources of evidence when diagnosing issues

### 7.1 ApplicationContext is the primary evidence

The check types in Section 4 exist in Spring Boot 3.x:

- `org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext`
- `org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext`

They indicate whether the context was created to run a reactive or servlet HTTP server. If a test runs a different context from the production application, conclusions only hold within that test's scope.

### 7.2 Auto-configuration condition report

Run the application when diagnosing with the argument:

```bash
./gradlew bootRun --args='--debug'
```

Inspect the **Conditions Evaluation Report** for `WebFluxAutoConfiguration`, `WebMvcAutoConfiguration`, `ReactiveWebServerFactoryAutoConfiguration`, `ServletWebServerFactoryAutoConfiguration`, and the corresponding security auto-configurations. Exact names/conditions may vary by Boot version; read the matched or unmatched conditions in the log.

If using Spring Boot Actuator, the `/actuator/conditions` endpoint can provide a similar report when configured and authorized appropriately. Do not expose sensitive diagnostic endpoints to the public Internet. **Do not infer solely from having WebFlux classes on the classpath**; read the conditions that actually matched.

### 7.3 Web server, dispatcher, and filter chain logs

In default starter configurations, you typically see MVC with Tomcat and WebFlux with Reactor Netty. However, WebFlux can use Tomcat/Jetty as the HTTP server, so **Tomcat appearing does not always mean MVC**. Identify the dispatcher:

- MVC: `DispatcherServlet` and Servlet Security's `FilterChainProxy`.
- WebFlux: `DispatcherHandler` and Reactive Security's `WebFilterChainProxy`.

Classes in dependencies are not enough to prove requests went through them. Observe the **active** context/beans, logs of the filter being used, and test request responses.

## 8. Tests preventing unintended stack switching

If the module's architectural requirement is **a reactive server**, add an integration test that boots the real application and asserts the context type. Example in `src/test/java/com/example/webstack/ReactiveWebStackTest.java`:

```java
package com.example.webstack;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = WebStackDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.main.web-application-type=reactive"
)
class ReactiveWebStackTest {

    @Autowired
    ApplicationContext context;

    @Test
    void webApplicationContextIsReactive() {
        assertThat(context)
            .isInstanceOf(ReactiveWebServerApplicationContext.class);
    }
}
```

Corresponding test dependency in Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run:

```bash
./gradlew test --tests '*ReactiveWebStackTest'
```

**Important limitation of the test above:** `properties = "spring.main.web-application-type=reactive"` forces the stack **only in the test**. The test proves how it runs when reactive is forced, but **does not prove the default deployment configuration will choose reactive**. For real regression protection, add a test without forcing `web-application-type`, using the actual production configuration and asserting `ReactiveWebServerApplicationContext`. If you intentionally keep both starters, place the reactive configuration in the corresponding production profile/default and verify the test loads **the same configuration source**.

Example test verifying the **default** (separated into `DefaultWebStackTest.java`):

```java
package com.example.webstack;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = WebStackDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DefaultWebStackTest {

    @Autowired
    ApplicationContext context;

    @Test
    void defaultStackIsServletWhenBothStartersArePresent() {
        assertThat(context)
            .isInstanceOf(ServletWebServerApplicationContext.class);
    }
}
```

`DefaultWebStackTest` only holds when both starters are present **and no other configuration forces REACTIVE**. If `application.yml` already contains `spring.main.web-application-type=reactive`, this test **must change its expectation** to reactive or move to a project/profile fixture to accurately demonstrate the default behavior. The two tests here illustrate **two intentional modes**, without requiring both classes to always be kept when the project policy only allows one mode.

To avoid misleading tests caused by mock/slice contexts:

- `@WebFluxTest` only builds a WebFlux slice, which may not reflect how the whole production application chooses its web stack.
- `WebTestClient` can bind directly to controllers/routers without starting a real server; a passing request test does not prove production Boot is WebFlux.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` is closer to runtime; still check that properties/profiles/launchers match the production execution path.
- For an app forced to WebFlux, also verify `SecurityWebFilterChain` operates on real endpoints and access permissions work as designed.

## 9. Scenarios A/B/C for hands-on practice

| Scenario | Present dependencies | Application configuration | Expected `WEB_STACK` |
| --- | --- | --- | --- |
| A | `starter-webflux`, no `starter-web` | Do not force `web-application-type` | `REACTIVE` |
| B | Both `starter-web` and `starter-webflux` | Do not force `web-application-type` | `SERVLET` |
| C | Both `starter-web` and `starter-webflux` | `spring.main.web-application-type=reactive` | `REACTIVE` |
| D | `starter-web`, no `starter-webflux` | Do not force `web-application-type` | `SERVLET` |
| E | No suitable web server starter | Depends on config | May be `NONE` or startup error if stack is forced without server factory |

**Practice sequence:**

1. Create a Boot 3.x Java 17+ project and place the probe class from Section 4.
2. Run with only `starter-webflux` and observe `WEB_STACK=REACTIVE`.
3. Add `starter-web`; re-run and see `WEB_STACK=SERVLET`.
4. Keep both but set `spring.main.web-application-type=reactive`; re-run and see `WEB_STACK=REACTIVE`.
5. Remove the property and replace main with the `setWebApplicationType(REACTIVE)` version; confirm the same result.
6. When adding `starter-security`, test the chain on the right stack using a protected endpoint. An unauthenticated request should be blocked per policy; a request with appropriate credentials/role must pass the right check, not letting default status results hide configuration errors.

Expectations A/B/C/D assume the starters create an appropriate web server, without special launcher/profile configurations or custom beans altering behavior.

### 9.1 Self-check questions

**Question 1:** A project has MVC + WebFlux, and a controller returns `Mono<String>`. Can we conclude the server is running reactive?

**Answer:** No. Spring Boot defaults to preferring MVC when both are present. You must check `ApplicationContext` or runtime auto-configuration.

**Question 2:** After adding `WebClient` to an MVC application, do we need to switch to `@EnableWebFluxSecurity`?

**Answer:** No. `WebClient` is an HTTP client; server security still uses `HttpSecurity` / `SecurityFilterChain` in the servlet stack.

**Question 3:** Logs contain "Tomcat started". Can we be sure WebFlux is not active?

**Answer:** No. WebFlux can use a servlet container via an adapter; you need to check the context and dispatcher.

**Question 4:** Setting `@SpringBootTest(properties="spring.main.web-application-type=reactive")` and the test passes. Does that guarantee the production application is reactive?

**Answer:** Not yet. That property only applies to that test; inspect bootstrap and profiles for deployment.

**Question 5:** The app is MVC, but someone copies `SecurityWebFilterChain` code from reactive docs. What is the consequence?

**Answer:** You cannot assume reactive security will protect MVC HTTP requests. Startup may fail or the intended policy may not activate. Use the right security stack, check the context, and verify request behavior.

## 10. Common errors and how to fix them

1. **Looking only at the WebFlux starter name:** listing dependencies does not prove runtime behavior. Use `ApplicationRunner` to read the context, combined with the condition report.
2. **Assuming every `Mono` is non-blocking WebFlux:** Spring MVC can also accept reactive return types; verify the dispatcher and inspect blocking call sites.
3. **Seeing Netty JARs and concluding Netty receives requests:** classpath differs from the actual web server. Check the context/web server factory and startup logs.
4. **Adding `@EnableWebFlux` to "force" web application type:** this annotation customizes WebFlux configuration, it is **not** Boot's mechanism for choosing `WebApplicationType`; it can also unintentionally disable Boot customizations.
5. **Using the wrong security DSL:** `authorizeHttpRequests`/`HttpSecurity` belong to Servlet; `authorizeExchange`/`ServerHttpSecurity` belong to reactive. Do not mix bean/config types.
6. **Loading both Servlet and Reactive security configs without conditional checks:** easily creates unexpected policies, missing beans, or startup failures. Use conditions matching web type and split modules when sensible.
7. **Using `@WebFluxTest` as proof for the production server:** slice tests do not show how Boot bootstraps the entire app. Write integration tests using the real context.
8. **Forcing REACTIVE while letting Servlet-only libraries handle requests:** can cause startup errors or broken features. Audit filters, listeners, servlet integrations, and migrate separately.
9. **Excluding transitive dependencies by mistake:** check `dependencyInsight` and consumers before excluding.
10. **Not testing after changing starters:** changing the classpath can change the context and all Spring Security auto-configuration. Set up regression tests verifying both the web stack type **and** route/authorization policies.

## 11. Checklist before calling an application "Spring Security reactive"

- [ ] Distinguished the need for a **WebFlux HTTP server** from the need to only use reactive `WebClient`.
- [ ] Identified whether `spring-webmvc` / `spring-webflux` are on the runtime classpath and why they appear.
- [ ] The main web server `ApplicationContext` is `ReactiveWebServerApplicationContext`; not relying solely on `Mono` types or server names.
- [ ] If keeping both MVC and WebFlux, explicitly selected `REACTIVE` and verified the config is loaded in the deployment environment.
- [ ] Server Spring Security uses `SecurityWebFilterChain` / `ServerHttpSecurity`, with authentication/authorization tested via HTTP requests.
- [ ] If pure WebFlux is desired, considered removing `spring-boot-starter-web` and unused Servlet components.
- [ ] Full-application startup tests verify the actual **production web stack**, not just a test slice or test-only forced property.

**Conclusion:** When both Spring MVC and WebFlux are present, **Boot defaults to running MVC**. In Spring Security reactive lessons, the sufficient condition to accurately call a system a "reactive web application" is proving **WebFlux runtime is actually activated** and the security chain runs on `ServerHttpSecurity`/`SecurityWebFilterChain`. Classpath and reactive return types are only supporting diagnostic data.

### Official references

- [Spring Boot — Reactive Web Applications (two-starter rule)](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Testing Spring Boot Applications (Detecting Web Application Type)](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — WebFlux Overview and server support](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Boot 3.3 API — ReactiveWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/context/ReactiveWebServerApplicationContext.html)
- [Spring Boot 3.3 API — ServletWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html)
