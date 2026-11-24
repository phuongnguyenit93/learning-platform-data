# WebApplicationContextRunner and ReactiveWebApplicationContextRunner

## 1. Objective: testing auto-configuration for the right web application type

When building a Spring Boot starter, shared library, or auto-configuration module, you often need to create beans **only when** the application runs on Spring MVC/Servlet or **only when** it runs on Spring WebFlux/Reactive. Those conditions cannot be verified properly by spinning up a plain `ApplicationContext` and asserting a bean exists.

For example, an audit library has two integration points:

- **Servlet:** a `HandlerInterceptor` for Spring MVC applications, setting the `X-Audit-Mode` header.
- **Reactive:** a `WebFilter` for Spring WebFlux, setting the same header yet executing via a `Mono<Void>`.
- Applications can turn off the feature via `lab.audit.enabled=false`.
- Users can declare their own bean to replace the starter's default.
- Even if both MVC and WebFlux appear on the classpath, **the actual `ApplicationContext` type** must still govern `@ConditionalOnWebApplication`, not merely dependency presence.

The two right tools in Spring Boot 3.3 are **`WebApplicationContextRunner`** and **`ReactiveWebApplicationContextRunner`**. They build controlled web application contexts, apply just the auto-configurations under test, vary environment/properties/user beans per test, and close the context after the callback.

This lesson belongs to the **Auto-Configuration Testing** group, focusing directly on **"WebApplicationContextRunner and ReactiveWebApplicationContextRunner"**. Examples use **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1**, and JUnit Jupiter. This is a test suite for an auto-configuration library; no HTTP server or Docker is needed.

### After this lesson, you can

1. Distinguish `ApplicationContextRunner`, `WebApplicationContextRunner`, and `ReactiveWebApplicationContextRunner`.
2. Create a Servlet web context with `MockServletContext` and the corresponding reactive web context.
3. Verify `@ConditionalOnWebApplication(type=SERVLET/REACTIVE)` properly across both environments.
4. Use `AutoConfigurations.of(...)` to load only the auto-configurations under test.
5. Use `withPropertyValues(...)` to test defaults, disabled flags, custom values, and invalid properties.
6. Use `withUserConfiguration(...)` or `withBean(...)` to verify `@ConditionalOnMissingBean` back-off.
7. Use AssertJ to check bean presence/absence, configuration, and small bean behavior.
8. Separate testing **bean creation conditions** from testing a real MVC `HandlerMapping` or WebFlux filter chain.
9. Understand additions needed for `@ConditionalOnClass`, optional classpath configurations, production starter registration, and condition evaluation reports.
10. Write short, isolated tests without launching full `@SpringBootTest` for every condition combination.

## 2. Three runners: picking the tool by ApplicationContext

| Runner | Primary context | Best suited for | Does not do automatically |
| --- | --- | --- | --- |
| `ApplicationContextRunner` | Non-web `AnnotationConfigApplicationContext` | General auto-config: cache, service, repository policy | Does not create Servlet/Reactive web contexts |
| `WebApplicationContextRunner` | Servlet `ConfigurableWebApplicationContext` with mock `ServletContext` | `@ConditionalOnWebApplication(SERVLET)`, `HandlerInterceptor`, Servlet beans | Does not run embedded Tomcat/HTTP requests |
| `ReactiveWebApplicationContextRunner` | `ConfigurableReactiveWebApplicationContext` | `@ConditionalOnWebApplication(REACTIVE)`, WebFlux `WebFilter`, reactive infrastructure | Does not start full Netty/WebFlux HTTP pipeline |

A runner creates **a fresh context per `run(...)` call**, closing it once the callback completes. No `@DirtiesContext` or `Thread.sleep` is needed to manage lifecycle in the example.

```text
JUnit @Test
    |
    +-- runner.withConfiguration(AutoConfigurations.of(...))
    |        |
    |        +-- withPropertyValues("lab.audit.enabled=true")
    |        +-- withUserConfiguration(UserOverrides.class)
    |        +-- withBean(...), if test needs it
    |
    +-- run(context -> {
             assertThat(context).hasSingleBean(...);
             assertThat(context).doesNotHaveBean(...);
         })
         |
         +-- context closes when run finishes
```

### Why not use ApplicationContextRunner for everything?

`@ConditionalOnWebApplication` inspects the **web application context/environment**, not merely whether `spring-webmvc` or `spring-webflux` is on the classpath. A plain `ApplicationContextRunner` must cause both web-only auto-configurations **not to match**. That is a very valuable negative test; if a web-only bean appears in a plain context, the auto-configuration's guard is broken or too permissive.

## 3. Servlet and Reactive are two different condition types

Spring Boot provides:

```java
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET)
```

and:

```java
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE)
```

These are **annotation snippets**, not standalone Java classes. `Type.ANY` applies when both Servlet and Reactive are acceptable, yet if the bean actually invokes `HttpServletRequest` APIs, never use `ANY`.

| Environment | SERVLET condition | REACTIVE condition |
| --- | --- | --- |
| `WebApplicationContextRunner` | Matches | Does not match |
| `ReactiveWebApplicationContextRunner` | Does not match | Matches |
| `ApplicationContextRunner` | Does not match | Does not match |

The table describes **Spring Boot 3.3 default runner contexts** and the demo's auto-configurations. If an application uses custom context factories/parent contexts, verify the specific test type/environment.

### What if both `spring-webmvc` and `spring-webflux` are on the classpath?

In a normal Boot application, **when both MVC and WebFlux are present, Boot prioritizes Servlet/MVC** when inferring the web application type. That does not mean reactive auto-configuration should activate inside a Servlet context.

With runners, you **choose the context type explicitly**: `new WebApplicationContextRunner()` or `new ReactiveWebApplicationContextRunner()`. To test both branches of a starter, use both runners; do not try changing `spring.main.web-application-type=reactive` inside a plain `ApplicationContextRunner` expecting it to turn into a reactive context automatically.

For a full `@SpringBootTest` having both starters, forcing a reactive test requires configuring `spring.main.web-application-type=reactive` per Boot documentation; that is **different** from runners choosing context factories directly.

## 4. Testing auto-configuration differs from testing controller endpoints

`WebApplicationContextRunner` is **not** `MockMvc`, and `ReactiveWebApplicationContextRunner` is **not** `WebTestClient`. In this lesson:

- We verify whether the bean is registered for the right web application type.
- We verify the default bean disappears when the feature is disabled or overridden by the user.
- We verify `ServletAuditInterceptor.preHandle(...)` with isolated mock request/response objects.
- We verify `ReactiveAuditFilter.filter(...)` with `MockServerWebExchange` and `Mono.empty()`.
- We **do not** conclude an HTTP request passed through `DispatcherServlet`/`HandlerMapping` or WebFlux `WebHttpHandlerBuilder`.

To protect annotation routing, JSON binding, whether MVC interceptors are actually added to the registry, or WebFlux filter ordering, add `@WebMvcTest`, `@WebFluxTest`, `MockMvc`, `WebTestClient`, or full-configuration integration tests.

## 5. Conditions commonly placed on auto-configuration

A solid auto-configuration often layers multiple conditions:

| Condition | Role | Test needed |
| --- | --- | --- |
| `@ConditionalOnWebApplication(type=...)` | Pick the right web stack | Servlet/Reactive/non-web contexts |
| `@ConditionalOnClass(SomeType.class)` | Only when optional library present | Classpath-present and simulated-absent |
| `@ConditionalOnProperty` | Enable/disable via property | Default, true, false, unexpected value |
| `@ConditionalOnMissingBean` | User overrides default | `withUserConfiguration` or `withBean` |
| `@ConditionalOnBean` | Require an existing collaborator | With/without bean dependency |
| `@ConditionalOnResource` | Only when resource exists | Resource/classpath simulation |
| `@ConditionalOnNotWebApplication` | Run only in non-web environments | Plain runner vs web runners |

**`@ConditionalOnMissingBean` depends on bean definition processing order.** Spring Boot recommends placing this condition in auto-configurations so auto-config is processed **after user-defined configuration**. Never put a fallback bean in an arbitrary regular `@Configuration` assuming it will automatically back off for user beans declared later.

## 6. Complete Java 17+ project structure

The example creates a **library-like module**, with no `@SpringBootApplication` and no runnable main method: the goal is running **Gradle tests** to verify both auto-configurations. The module includes an imports file so users can package it as a starter/autoconfigure JAR.

```text
web-context-runner-lab/
├── settings.gradle
├── build.gradle
├── src/main/
│   ├── java/com/example/audit/
│   │   ├── servlet/ServletAuditInterceptor.java
│   │   ├── reactive/ReactiveAuditFilter.java
│   │   └── autoconfigure/
│   │       ├── ServletAuditAutoConfiguration.java
│   │       └── ReactiveAuditAutoConfiguration.java
│   └── resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── src/test/java/com/example/audit/
    └── AuditAutoConfigurationTests.java
```

**Packaging note:** both `@AutoConfiguration` classes live in `com.example.audit.autoconfigure`. Production libraries must not rely on arbitrary component scanning to find them: Spring Boot uses `AutoConfiguration.imports`. In tests, `AutoConfigurations.of(...)` targets them directly. Because this is a library module, Gradle `bootJar` is disabled and plain `jar` is enabled, avoiding missing-main-class build errors.

The lesson puts both MVC and WebFlux dependencies in **one lab** so both context types can be tested. A production starter should keep optional dependencies/variants clean and avoid pulling both web stacks into applications unnecessarily; here it is an intentional learning choice.

## 7. settings.gradle and build.gradle

### settings.gradle

```groovy
rootProject.name = 'web-context-runner-lab'
```

### build.gradle

```groovy
plugins {
    id 'java-library'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('bootJar') {
    enabled = false
}

tasks.named('jar') {
    enabled = true
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

### Why these dependencies?

- `spring-boot-starter-web`: Servlet API, Spring MVC `HandlerInterceptor`, and Boot autoconfigure classes.
- `spring-boot-starter-webflux`: Spring WebFlux `WebFilter`, Reactor `Mono`, and reactive web context support.
- `spring-boot-starter-test`: context runners, AssertJ, Spring Test mock Servlet/Reactive request types, and JUnit Jupiter.
- `junit-platform-launcher`: Gradle/JUnit Platform support.
- `java-library`: fits library structure, requiring no executable application.

**Do not run `bootRun`** from this project: there is no main class. Run `gradle test` or `gradle build`. For a real Spring Boot application, use a separate app project as a consumer of this auto-config library.

If no Gradle Wrapper exists yet, use a compatible installed Gradle or generate the Wrapper with project tooling; do not mistake `./gradlew: file not found` for a test code error.

## 8. ServletAuditInterceptor.java

`src/main/java/com/example/audit/servlet/ServletAuditInterceptor.java`:

```java
package com.example.audit.servlet;

import java.util.Objects;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

public final class ServletAuditInterceptor
        implements HandlerInterceptor {

    private final String headerValue;

    public ServletAuditInterceptor(String headerValue) {
        this.headerValue = Objects.requireNonNull(headerValue);
    }

    public String headerValue() {
        return headerValue;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        response.setHeader("X-Audit-Mode", headerValue);
        return true;
    }
}
```

This is a real **Servlet `HandlerInterceptor`**: `preHandle(...)` runs before the controller handler is invoked (once the interceptor is registered in the MVC interceptor registry). The demo writes a response header and lets the request proceed.

**Distinguish bean registration from MVC registration:** merely having a `HandlerInterceptor` bean **does not prove** the interceptor was added to all MVC `HandlerMapping`s. In production, you need a `WebMvcConfigurer.addInterceptors(...)` or an equivalent MVC registration mechanism. Runner tests verify the interceptor bean is created/works; a separate integration test must confirm it actually runs in the HTTP pipeline.

### Why return true?

`true` means allow the handler chain to proceed. Returning `false` halts the request at the interceptor, requiring an appropriate response/status. This lesson only adds a header without altering control flow.

### Never write PII into X-Audit-Mode

The header in this lesson is a fixed string `servlet-default` or `custom`, containing no access tokens, usernames, or request bodies. Production audit logic must evaluate security/logging/PII separately; never put secrets into response headers.

## 9. ReactiveAuditFilter.java

`src/main/java/com/example/audit/reactive/ReactiveAuditFilter.java`:

```java
package com.example.audit.reactive;

import java.util.Objects;

import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ReactiveAuditFilter implements WebFilter {

    private final String headerValue;

    public ReactiveAuditFilter(String headerValue) {
        this.headerValue = Objects.requireNonNull(headerValue);
    }

    public String headerValue() {
        return headerValue;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Audit-Mode", headerValue);

        return chain.filter(exchange);
    }
}
```

`WebFilter` is part of the **Spring WebFlux reactive web pipeline**. It receives `ServerWebExchange` and `WebFilterChain`, returning `Mono<Void>`. This is not `jakarta.servlet.Filter` and does not use `HttpServletRequest`.

In the lab, this small logic is invoked directly in tests with a mock WebExchange. In a full reactive application, whether a filter bean participates in the pipeline also depends on WebFlux infrastructure; to verify network/request integration and ordering, add `WebTestClient` or real HTTP integration tests.

### Why not call block() inside production filters?

The filter returns `chain.filter(exchange)` to preserve reactive composition. Never insert `block()` inside production handlers/filters. Tests can call `.block(Duration.ofSeconds(2))` on an **immediately-completing mock `Mono`** to wait for observable side effects; that is test code, not a production reactive request pattern.

## 10. ServletAuditAutoConfiguration.java

`src/main/java/com/example/audit/autoconfigure/ServletAuditAutoConfiguration.java`:

```java
package com.example.audit.autoconfigure;

import com.example.audit.servlet.ServletAuditInterceptor;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.web.servlet.HandlerInterceptor;

@AutoConfiguration
@ConditionalOnClass(HandlerInterceptor.class)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnProperty(
        prefix = "lab.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ServletAuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ServletAuditInterceptor.class)
    ServletAuditInterceptor servletAuditInterceptor(
            Environment environment) {

        String label = environment.getProperty(
                "lab.audit.label", "servlet-default");

        return new ServletAuditInterceptor(label);
    }
}
```

### How do the conditions work?

- `@AutoConfiguration`: class is an auto-configuration candidate, not a controller, service, or component picked up accidentally by scanning.
- `@ConditionalOnClass(HandlerInterceptor.class)`: requires the Spring MVC integration API.
- `@ConditionalOnWebApplication(Type.SERVLET)`: does not activate in reactive or plain contexts.
- `@ConditionalOnProperty(...)`: enabled when `lab.audit.enabled=true`, and **enabled by default when absent** because `matchIfMissing=true`.
- `@ConditionalOnMissingBean(ServletAuditInterceptor.class)`: if the user already declared a bean of this exact type, the starter **does not create a duplicate default bean**.
- `Environment.getProperty("lab.audit.label", "servlet-default")`: fetches a label overridable per test without hardcoding a test-only value in production config.
- Bean method returns the **concrete type** `ServletAuditInterceptor` so Spring sees the type when evaluating the missing-bean condition.

### Why not activate the bean solely via `@ConditionalOnClass`?

If you only check that MVC `HandlerInterceptor` is on the classpath, a WebFlux app **that also has `spring-webmvc` on its classpath** could accidentally receive an incompatible Servlet bean. The web-type condition is essential when a feature targets one specific stack.

### Custom beans and ordering

`@ConditionalOnMissingBean` sits inside auto-configuration loaded by Boot after user-defined bean definitions. Later tests use `withUserConfiguration(...)` to confirm the starter backs off. Never use `spring.main.allow-bean-definition-overriding=true` to avoid duplicate beans: it masks a design flaw that back-off conditions must solve.

## 11. ReactiveAuditAutoConfiguration.java

`src/main/java/com/example/audit/autoconfigure/ReactiveAuditAutoConfiguration.java`:

```java
package com.example.audit.autoconfigure;

import com.example.audit.reactive.ReactiveAuditFilter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.web.server.WebFilter;

@AutoConfiguration
@ConditionalOnClass(WebFilter.class)
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnProperty(
        prefix = "lab.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ReactiveAuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReactiveAuditFilter.class)
    ReactiveAuditFilter reactiveAuditFilter(
            Environment environment) {

        String label = environment.getProperty(
                "lab.audit.label", "reactive-default");

        return new ReactiveAuditFilter(label);
    }
}
```

The conditions mirror servlet, using **Reactive type** and **`WebFilter` class**. When tests run via `ReactiveWebApplicationContextRunner`, it can create `ReactiveAuditFilter` without creating `ServletAuditInterceptor`. When tests run via `WebApplicationContextRunner`, the opposite happens.

Both auto-configurations share `lab.audit.enabled` and `lab.audit.label` for easy comparison, though each branch has its own default label. In a production starter, namespaces must be specific to your organization/library, avoiding `spring.*` or `server.*` for custom settings; `lab.audit.*` is purely a learning namespace.

### Why not declare the bean type directly as `WebFilter`?

Declaring the bean method return type as specific `ReactiveAuditFilter` makes `@ConditionalOnMissingBean(ReactiveAuditFilter.class)` clear. Returning generic `WebFilter` when an app has many other filters could cause conditioning on `WebFilter` globally to accidentally turn off the audit filter just because a security filter or tracing filter exists. Choose bean conditions by feature-specific type or appropriate qualifier/marker.

## 12. Registering auto-configurations via the imports file

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.example.audit.autoconfigure.ServletAuditAutoConfiguration
com.example.audit.autoconfigure.ReactiveAuditAutoConfiguration
```

Spring Boot 3.x looks up auto-configuration candidates in this file when consumer applications enable `@EnableAutoConfiguration` (usually via `@SpringBootApplication`). This is the proper production starter registration approach; **do not use `spring.factories` as in older Spring Boot 2.0 tutorials**.

In test runners, we still choose explicitly:

```java
.withConfiguration(AutoConfigurations.of(
        ServletAuditAutoConfiguration.class,
        ReactiveAuditAutoConfiguration.class))
```

This restricts the context to just the auto-configurations under test; the runner does not boot all Spring Boot auto-config classes merely because an imports file exists. **Distinguishing** production discovery from explicit test selection is essential in starter testing.

### Why not put `@AutoConfiguration` inside component scanning?

If an app's `@SpringBootApplication` sits in a parent package encompassing the starter's `@AutoConfiguration` and scans it, the auto-config can be processed as a regular configuration **before** user bean definitions. Then `@ConditionalOnMissingBean` can evaluate wrongly and lose back-off capability. For starters, keep auto-configs in a separate package outside application component scanning, and load them via imports.

## 13. Complete test class: Servlet, Reactive, and non-web

Create `src/test/java/com/example/audit/AuditAutoConfigurationTests.java`:

```java
package com.example.audit;

import java.time.Duration;

import com.example.audit.autoconfigure.ReactiveAuditAutoConfiguration;
import com.example.audit.autoconfigure.ServletAuditAutoConfiguration;
import com.example.audit.reactive.ReactiveAuditFilter;
import com.example.audit.servlet.ServletAuditInterceptor;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.server.MockServerWebExchange;

import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final WebApplicationContextRunner servletRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ServletAuditAutoConfiguration.class,
                            ReactiveAuditAutoConfiguration.class));

    private final ReactiveWebApplicationContextRunner reactiveRunner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ServletAuditAutoConfiguration.class,
                            ReactiveAuditAutoConfiguration.class));

    private final ApplicationContextRunner plainRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ServletAuditAutoConfiguration.class,
                            ReactiveAuditAutoConfiguration.class));

    @Test
    void servletRunnerCreatesOnlyServletBean() {
        servletRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(ServletAuditInterceptor.class);
            assertThat(context)
                    .doesNotHaveBean(ReactiveAuditFilter.class);
            assertThat(context.getBean(
                    ServletAuditInterceptor.class).headerValue())
                    .isEqualTo("servlet-default");
        });
    }

    @Test
    void reactiveRunnerCreatesOnlyReactiveBean() {
        reactiveRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(ReactiveAuditFilter.class);
            assertThat(context)
                    .doesNotHaveBean(ServletAuditInterceptor.class);
            assertThat(context.getBean(
                    ReactiveAuditFilter.class).headerValue())
                    .isEqualTo("reactive-default");
        });
    }

    @Test
    void plainRunnerCreatesNeitherWebBean() {
        plainRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .doesNotHaveBean(ServletAuditInterceptor.class);
            assertThat(context)
                    .doesNotHaveBean(ReactiveAuditFilter.class);
        });
    }

    @Test
    void servletFeatureCanBeDisabledByProperty() {
        servletRunner
                .withPropertyValues("lab.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(ServletAuditInterceptor.class);
                    assertThat(context)
                            .doesNotHaveBean(ReactiveAuditFilter.class);
                });
    }

    @Test
    void reactiveFeatureCanBeDisabledByProperty() {
        reactiveRunner
                .withPropertyValues("lab.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(ReactiveAuditFilter.class);
                    assertThat(context)
                            .doesNotHaveBean(ServletAuditInterceptor.class);
                });
    }

    @Test
    void servletLabelComesFromEnvironment() {
        servletRunner
                .withPropertyValues("lab.audit.label=servlet-custom")
                .run(context -> {
                    assertThat(context).hasSingleBean(
                            ServletAuditInterceptor.class);
                    assertThat(context.getBean(
                            ServletAuditInterceptor.class).headerValue())
                            .isEqualTo("servlet-custom");
                });
    }

    @Test
    void reactiveLabelComesFromEnvironment() {
        reactiveRunner
                .withPropertyValues("lab.audit.label=reactive-custom")
                .run(context -> {
                    assertThat(context).hasSingleBean(
                            ReactiveAuditFilter.class);
                    assertThat(context.getBean(
                            ReactiveAuditFilter.class).headerValue())
                            .isEqualTo("reactive-custom");
                });
    }

    @Test
    void servletAutoConfigBacksOffForUserConfiguration() {
        servletRunner
                .withUserConfiguration(UserServletOverride.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            ServletAuditInterceptor.class);
                    assertThat(context)
                            .doesNotHaveBean("servletAuditInterceptor");
                    assertThat(context.getBean(
                            ServletAuditInterceptor.class).headerValue())
                            .isEqualTo("app-servlet");
                });
    }

    @Test
    void reactiveAutoConfigBacksOffForUserBean() {
        reactiveRunner
                .withBean(
                        ReactiveAuditFilter.class,
                        () -> new ReactiveAuditFilter("app-reactive"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(ReactiveAuditFilter.class);
                    assertThat(context)
                            .doesNotHaveBean("reactiveAuditFilter");
                    assertThat(context.getBean(
                            ReactiveAuditFilter.class).headerValue())
                            .isEqualTo("app-reactive");
                });
    }

    @Test
    void servletInterceptorSetsResponseHeader()
            throws Exception {
        servletRunner.run(context -> {
            ServletAuditInterceptor interceptor = context.getBean(
                    ServletAuditInterceptor.class);
            MockHttpServletRequest request =
                    new MockHttpServletRequest("GET", "/test");
            MockHttpServletResponse response =
                    new MockHttpServletResponse();

            assertThat(interceptor.preHandle(
                    request, response, new Object())).isTrue();
            assertThat(response.getHeader("X-Audit-Mode"))
                    .isEqualTo("servlet-default");
        });
    }

    @Test
    void reactiveWebFilterSetsResponseHeader() {
        reactiveRunner.run(context -> {
            ReactiveAuditFilter filter = context.getBean(
                    ReactiveAuditFilter.class);
            MockServerWebExchange exchange =
                    MockServerWebExchange.from(
                            MockServerHttpRequest.get("/test"));

            filter.filter(
                    exchange,
                    ignored -> Mono.empty())
                    .block(Duration.ofSeconds(2));

            assertThat(exchange.getResponse()
                    .getHeaders()
                    .getFirst("X-Audit-Mode"))
                    .isEqualTo("reactive-default");
        });
    }

    @Test
    void modifiedRunnerDoesNotMutateBaseRunner() {
        WebApplicationContextRunner customized =
                servletRunner.withPropertyValues(
                        "lab.audit.label=one-test-only");

        customized.run(context ->
                assertThat(context.getBean(
                        ServletAuditInterceptor.class).headerValue())
                        .isEqualTo("one-test-only"));

        servletRunner.run(context ->
                assertThat(context.getBean(
                        ServletAuditInterceptor.class).headerValue())
                        .isEqualTo("servlet-default"));
    }

    @Test
    void nonTrueEnabledValueDoesNotMatchCondition() {
        reactiveRunner
                .withPropertyValues(
                        "lab.audit.enabled=unexpected")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(ReactiveAuditFilter.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserServletOverride {

        @Bean
        ServletAuditInterceptor customServletInterceptor() {
            return new ServletAuditInterceptor("app-servlet");
        }
    }
}
```

**Count: 13 `@Test` methods**. The three runners are independent fields, and each test calls `run(...)` to build a fresh context. No `@SpringBootTest`, `@BeforeEach`, database, or embedded server needs manual management.

### Checking concrete types rather than only bean names

`servletRunnerCreatesOnlyServletBean` asserts exactly one `ServletAuditInterceptor` and **no** `ReactiveAuditFilter`. Conversely, `reactiveRunnerCreatesOnlyReactiveBean` asserts one reactive filter and no Servlet interceptor. `plainRunnerCreatesNeitherWebBean` tests the non-web guard. These results are far stronger than merely asserting `context.isActive()`.

### Testing back-off rather than only defaults

Both custom-bean tests matter because auto-configuration usually supplies **defaults for users**, not beans permitted to overwrite every user choice.

- `withUserConfiguration(UserServletOverride.class)` creates `customServletInterceptor` before the fallback auto-configuration is evaluated.
- `withBean(ReactiveAuditFilter.class, supplier)` registers a direct user bean; default `reactiveAuditFilter` is not created.
- Asserting **`hasSingleBean`** catches two instances of the same type if `@ConditionalOnMissingBean` is removed.
- Asserting **`doesNotHaveBean("servletAuditInterceptor")` / `doesNotHaveBean("reactiveAuditFilter")`** confirms the fallback bean does not exist, rather than inferring only from value.

### Testing behavior without faking HTTP transport

The Servlet test uses `MockHttpServletRequest`/`MockHttpServletResponse` and calls `preHandle(...)` directly. The Reactive test uses `MockServerWebExchange` and a `WebFilterChain` lambda returning `Mono.empty()`. They verify **bean behavior** inside the JVM; there is no real HTTP socket or embedded server.

### Verifying no configuration leaks between tests

`withPropertyValues(...)` **returns a customized runner**, without mutating any previously created context. `modifiedRunnerDoesNotMutateBaseRunner` runs a context with a custom label and then a fresh context from the original runner, verifying the default remains intact. This enables writing many scenario tests without `@DirtiesContext`.

## 14. Notes on test scope and run lifecycle

A runner holds **a recipe for creating contexts**, not a shared live context across test methods. Each `run(context -> ...)`:

1. Prepares a context factory matching the runner type.
2. Applies user configurations, auto-configurations, and properties.
3. Refreshes the context, evaluating conditions and creating matching beans.
4. Executes the callback with an assertable context.
5. Closes the context even if assertions fail per utility lifecycle.

Never retain a bean reference from the callback and use it after `run` completes, as the bean/context may already be closed. Singleton beans holding lifecycle resources (connection pools, schedulers, threads) must clean up when the context closes; the runner does not automatically clean up external side effects outside Spring's lifecycle.

If a test needs to verify `@PreDestroy` or resource closing, you can record events via an external helper and assert after `run`, while preserving test isolation.

### ContextRunner vs `@SpringBootTest` cache

`@SpringBootTest` uses the Spring TestContext cache to reuse contexts across multiple tests with identical configurations. ContextRunner is optimized for many **small condition combinations**, running an isolated context each time and closing it immediately. It does not automatically enable all Boot auto-configs of an executable app.

## 15. What is `withConfiguration(AutoConfigurations.of(...))` for?

In the demo:

```java
.withConfiguration(AutoConfigurations.of(
    ServletAuditAutoConfiguration.class,
    ReactiveAuditAutoConfiguration.class))
```

passes **auto-configuration candidates** into the context runner using Spring Boot semantics, so they are evaluated like standard auto-config, including ordering/conditions.

**Do not confuse with `withUserConfiguration(...)`**:

| API | Used for | Example |
| --- | --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Auto-configurations under test | Servlet/ReactiveAuditAutoConfiguration |
| `withUserConfiguration(...)` | Regular user `@Configuration` to test overrides | UserServletOverride |
| `withBean(Type.class, supplier)` | One small user-defined bean | ReactiveAuditFilter("app-reactive") |
| `withPropertyValues("k=v")` | External configuration per scenario | `lab.audit.enabled=false` |
| `withClassLoader(...)` | Simulate classpath availability | FilteredClassLoader for optional library |
| `withInitializer(...)` | Condition report/logging or custom initializer | ConditionEvaluationReportLoggingListener |
| `withParent(...)` | Parent-child context scenarios | Parent bean search/visibility |
| `run(...)` | Execute and assert inside callback | hasSingleBean/doesNotHaveBean |

If a starter's auto-configuration depends on `JacksonAutoConfiguration`, `WebMvcAutoConfiguration`, or `CodecAutoConfiguration`, pass those exact dependencies into `AutoConfigurations.of(...)` when testing their integration. However, **never import the entire Boot auto-config catalog** just to fix a test failure, as that defeats environment control and runner speed.

## 16. `@ConditionalOnProperty`: `matchIfMissing` and `havingValue`

In both auto-config classes:

```java
@ConditionalOnProperty(
    prefix = "lab.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
```

means:

| `lab.audit.enabled` | Expected |
| --- | --- |
| Not declared | Enabled, due to `matchIfMissing=true` |
| `true` | Enabled |
| `false` | Disabled |
| `unexpected` | Does not match because `havingValue="true"` |

`@ConditionalOnProperty` is not a validator for arbitrary data types; it checks property values per condition semantics. For typed config properties like `Duration timeout` or `URI endpoint`, use `@ConfigurationProperties` with separate validation. Do not rely solely on a condition matching to assume values are valid.

In tests, add a property with:

```java
servletRunner
    .withPropertyValues(
        "lab.audit.enabled=true",
        "lab.audit.label=my-label")
    .run(context ->
        assertThat(context.getBean(
            ServletAuditInterceptor.class).headerValue())
            .isEqualTo("my-label"));
```

This is a **snippet directly using fields from the test class**; not a standalone test file. Values from `withPropertyValues` live inside that run's isolated context without touching `application.yml` or system properties.

### Why must custom values actually be tested?

A `hasSingleBean` test would still PASS if the implementation accidentally ignored `lab.audit.label` and always used the default. Asserting `headerValue()==custom` forces the auto-config to genuinely consume Spring `Environment`.

## 17. `@ConditionalOnMissingBean`: right type, right time

Spring Boot defines `@ConditionalOnMissingBean` to supply a fallback when the user lacks a bean. In the demo, the condition sits **on the bean method** with a concrete type:

```java
@Bean
@ConditionalOnMissingBean(ServletAuditInterceptor.class)
ServletAuditInterceptor servletAuditInterceptor(
        Environment environment) {
    return new ServletAuditInterceptor(
            environment.getProperty(
                    "lab.audit.label", "servlet-default"));
}
```

If user config has:

```java
@Bean
ServletAuditInterceptor customServletInterceptor() {
    return new ServletAuditInterceptor("app-servlet");
}
```

then the auto-config fallback should not create a second bean. Tests verify both type count and bean name.

### Warning about registration order

Bean conditions inspect **definitions already processed at evaluation time**, without scanning ahead across the entire future. Spring Boot recommends `@ConditionalOnMissingBean` inside auto-configurations because they are processed after regular user configuration. Putting a fallback condition in a regular `@Configuration` imported in the wrong order can cause back-off to behave differently than in production.

### Never use Allow Bean Definition Overriding to mask bugs

`withAllowBeanDefinitionOverriding(true)` or `spring.main.allow-bean-definition-overriding=true` can let two same-named definitions overwrite one another depending on order. That is not proof of well-designed auto-configuration. Prefer condition back-off and `hasSingleBean` assertions.

## 18. `@ConditionalOnClass` and `FilteredClassLoader`

`@ConditionalOnClass` lets a starter activate only when an optional library is present. The two auto-configs check these API types:

- Servlet branch: `HandlerInterceptor.class`.
- Reactive branch: `WebFilter.class`.

In the lab both starters are on the classpath, so **the main test suite does not simulate a missing dependency**. To test optional classpaths, Spring Boot provides `FilteredClassLoader` with `runner.withClassLoader(...)`.

An illustrative pattern for **another auto-configuration** (not a runnable file of this lab since `VendorClientAutoConfiguration`/`VendorClient` are undefined):

```java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        VendorClientAutoConfiguration.class))
    .withClassLoader(
        new FilteredClassLoader(VendorClient.class))
    .run(context ->
        assertThat(context).doesNotHaveBean("vendorClient"));
```

### Class-loading pitfall with optional APIs

Never merely slap `@ConditionalOnClass` onto a `@Bean` method whose return type belongs to an **absent** library; the JVM may have to resolve return types while reading method metadata before the method-level condition is applied. Spring Boot recommends putting classpath conditions at the **class level** or on an isolated nested `@Configuration` to prevent `NoClassDefFoundError` before the condition runs.

Architectural example:

```java
@AutoConfiguration
class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.api.Client")
    static class VendorPresentConfiguration {

        // @Bean Client client(...) resides solely inside
        // a separate class conditioned at the class level.
    }
}
```

This is an **architectural snippet**; `com.vendor.api.Client` has not been added to the project. Do not claim it compiles standalone as runnable code.

`FilteredClassLoader` simulates classpath visibility; it does not replace running a consumer module genuinely lacking the dependency in its build. For complex auto-configs, add a small consumer test carrying only the required optional classpath to catch linkage bugs.

## 19. `ConditionEvaluationReport` and diagnosing why a bean is absent

When a `doesNotHaveBean(...)` test PASSES, understand why it is absent:

- Web type did not match?
- Property flag disabled?
- Optional class missing?
- User bean made auto-config back off?
- Dependency bean missing or wrong auto-config ordering?

Spring Boot provides `ConditionEvaluationReport` and the logging listener:

```java
new WebApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        ServletAuditAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
            LogLevel.INFO))
    .run(context -> {
        assertThat(context).hasNotFailed();
    });
```

**This snippet requires imports**:
`org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener`,
`org.springframework.boot.logging.LogLevel`,
`WebApplicationContextRunner`, and `AutoConfigurations`. It uses the auto-config class from the project. Report logging depends on logger configuration; do not treat the presence of a fixed text line as a mandatory assertion.

### Reading the report directly

You can obtain the report from the source context's bean factory, e.g.:

```java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(
        context.getSourceApplicationContext().getBeanFactory());
```

Requires `context` from the runner callback, importing `ConditionEvaluationReport`, and using the exact API of your Spring Boot version. This is a debug snippet, **not part of the project's 13 methods**. When asserting a specific condition, inspect `report.getConditionAndOutcomesBySource()`, yet avoid brittle assertions on message wording — report text can change across versions.

### Do not guess the cause solely from a missing bean

If context startup fails, asserting bean absence can mask the underlying error; check `assertThat(context).hasNotFailed()` first or inspect `context.getStartupFailure()` for the root cause. If `ConditionEvaluationReport` reports a classpath mismatch, fix the dependency/guard rather than tweaking expected values to make the test green.

## 20. How to test context startup failures

With auto-configurations creating complex beans, a bean factory method can throw an exception, fail binding, or lack a constructor dependency. `run(...)` still provides an assertable context to inspect startup failures where supported by the runner.

Test pattern:

```java
runner.run(context -> {
    assertThat(context).hasFailed();
    Throwable root = context.getStartupFailure();
    assertThat(root).isNotNull();
});
```

This is a **snippet** where `runner` must be declared and configured to fail intentionally. Do not run it against the default demo runners because the example auto-configurations are designed to start cleanly.

Using `assertThat(context).hasNotFailed()` when a condition is broken pins down the startup failure immediately instead of throwing a confusing `NoSuchBeanDefinitionException` from `context.getBean(...)`.

## 21. Why doesn't `WebApplicationContextRunner` automatically verify MVC routing?

`WebApplicationContextRunner` provides a mock `ServletContext`, yet in the demo we **import only the lab's two auto-configurations**, without setting up all of:

- `DispatcherServlet`.
- `WebMvcAutoConfiguration`.
- MVC `HandlerMapping` and `HandlerAdapter`.
- `MockMvc` wiring for a controller route.

Therefore, `servletInterceptorSetsResponseHeader` **calls the interceptor method directly**, rather than dispatching a Servlet request through `DispatcherServlet`. For the production interceptor to work, register it with MVC:

```java
@Configuration(proxyBeanMethods = false)
class AuditMvcRegistration implements WebMvcConfigurer {

    private final ServletAuditInterceptor audit;

    AuditMvcRegistration(ServletAuditInterceptor audit) {
        this.audit = audit;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(audit);
    }
}
```

This is an **extension snippet** requiring imports `Configuration`, `WebMvcConfigurer`, and `InterceptorRegistry`; not part of the main project. In a production starter, place this registration config inside the Servlet conditional branch rather than assuming merely having a bean registers it with MVC. Write `@WebMvcTest` with a controller and `MockMvc` or `@SpringBootTest` for routing integration.

### Do not confuse bean tests with security filter chain tests

A `HandlerInterceptor` is not a substitute for Spring Security's `SecurityFilterChain`. If auth logic is placed in an interceptor, verify it applies to the right paths and filter/handler order; security authentication/authorization should use its dedicated infrastructure. Tests in this lesson only add a demo header, with no security role.

## 22. Why doesn't `ReactiveWebApplicationContextRunner` automatically verify the WebFlux pipeline?

The reactive runner builds a reactive context, yet does not configure full HTTP routing, codecs, handler strategies, and a Netty server. `ReactiveAuditFilter` is created with the right type by conditions, while `reactiveWebFilterSetsResponseHeader` calls the method with `MockServerWebExchange`.

A full WebFlux request normally traverses:

```text
HTTP request
  -> HttpHandler / WebHttpHandlerBuilder
  -> WebFilter chain
  -> DispatcherHandler / RouterFunction
  -> HandlerAdapter / message codecs
  -> HTTP response
```

Runner tests in this lesson stop at **bean construction + direct filter behavior**, short of the network layer. To verify `WebFilter` order and rules with actual routes:

- Use `@WebFluxTest` + `WebTestClient` for a slice with matching routers/controllers.
- Or `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an HTTP client when testing a real server.
- Import the right configuration so the chain includes the filter under test; do not merely create a `WebFilter` bean and assume tests sent a request.
- For complex reactive behavior, use `StepVerifier` rather than `block()` in production.

## 23. Both MVC and WebFlux on classpath: a must-have test

The lab intentionally includes both starters. This setup separates two facts:

1. **Classpath presence**: both Spring MVC and WebFlux APIs exist in the JVM.
2. **Context type**: the runner is Servlet or Reactive according to the constructor used.

`@ConditionalOnClass(WebFilter.class)` can match inside the Servlet runner because `WebFilter` is on the classpath, yet `@ConditionalOnWebApplication(REACTIVE)` does not match. Likewise, the Servlet branch does not match in the Reactive runner. Combining both conditions creates the right bean **for each environment**, preventing cross-activation.

If you test only with `new ApplicationContextRunner()`, both web conditions are false and both beans disappear. That is insufficient to conclude auto-config works in an MVC/WebFlux application.

### How to spot the wrong runner

- Testing WebFlux with `WebApplicationContextRunner`: reactive bean does not appear because type mismatches.
- Testing MVC with `ReactiveWebApplicationContextRunner`: Servlet bean does not appear.
- Using `ApplicationContextRunner` and adding `spring.main.web-application-type=servlet`: if the context factory remains non-web, conditions can still fail to match.
- Both deps present in full `@SpringBootTest`, expecting Spring to automatically pick reactive: MVC takes precedence by default.
- Running only Servlet tests and forgetting the reactive branch: the starter can be broken on one web stack while CI stays green.

## 24. Comparing runners with common test slices

| Tool | Scope | Use when |
| --- | --- | --- |
| `ApplicationContextRunner` | Small non-web context | Testing web-independent auto-configs |
| `WebApplicationContextRunner` | Small Servlet web context | Testing MVC/Servlet conditional beans |
| `ReactiveWebApplicationContextRunner` | Small Reactive web context | Testing WebFlux conditional beans |
| `@WebMvcTest` | MVC stack/controller slice | Routing, binding, controller/filter behavior |
| `@WebFluxTest` | WebFlux controller/handler slice | Reactive routing and serialization |
| `@RestClientTest` | Outbound HTTP client slice | RestClient/RestTemplate and mock HTTP responses |
| `@SpringBootTest` | Boot application context | Full wiring/integration across many components |
| Real HTTP server test | Socket/network boundary | TLS/proxy/network/timeouts |

**No single tool replaces all other tests.** Each answers a distinct question: bean conditions, MVC routes, reactive endpoints, outbound clients, or full-application integration.

### When is `ApplicationContextRunner` alone enough?

An auto-config indifferent to web type — for instance, providing a `Clock`, cache codec, or serializer when a dependency is present — can be tested with `ApplicationContextRunner`. Never spin up a Servlet/Reactive context without a web-related requirement — it blurs test intent and introduces unexpected scopes/beans.

## 25. `@ConfigurationProperties` in web auto-configuration

The example uses `Environment.getProperty` because there are only two settings, `enabled` and `label`. For complex settings (URI, Duration, nested lists), use typed `@ConfigurationProperties` and enable the bean properly:

```java
@ConfigurationProperties(prefix = "lab.audit")
public record AuditProperties(
        boolean enabled,
        String label
) {
}
```

This record snippet **does not directly replace** the two existing auto-configurations without adding binding/registration and a default policy. A configuration using a record can declare:

```java
@EnableConfigurationProperties(AuditProperties.class)
```

on the auto-config class needing that type; use `withPropertyValues("lab.audit.label=...")` in the runner to verify binding. For Bean Validation with `@Validated` and Jakarta constraints, add the validation starter and test both valid/invalid property cases.

**Do not forget defaults and null handling** when switching from `Environment.getProperty("...", default)` to a Java record: records have only constructor values, so an unconfigured `label` field can be null. A default auto-config test must guard the actual implemented fallback logic rather than assuming behavior from old code.

## 26. Classpath simulation: when to add more tests?

A library with optional Servlet/WebFlux integrations needs two matrices:

| Input | Expected |
| --- | --- |
| MVC API + Servlet context | Servlet bean can be created |
| WebFlux API + Reactive context | Reactive bean can be created |
| MVC API present + Reactive context | Servlet bean must be absent |
| WebFlux API present + Servlet context | Reactive bean must be absent |
| No MVC classes | Servlet auto-config backs off, no linkage error |
| No WebFlux classes | Reactive auto-config backs off, no linkage error |
| Feature disabled | No bean created despite matching type/classpath |
| User-provided bean | No duplicate default created |

The lab covers the first five groups around **context type, flag, and override**, yet **has no runnable classpath-hidden tests** among the 13 methods. To truly safeguard optional dependencies when publishing a starter, add a test set using `FilteredClassLoader` on isolated configs, plus a consumer build carrying only one starter. Avoid stuffing them into a test where classloader filtering accidentally breaks resolution of a return type used directly by the test class itself.

### Why not only assert `hasSingleBean` with all starters on the classpath?

If an auto-config forgets `@ConditionalOnClass` while test runtime always includes the optional library, tests miss the missing-dependency failure for consumers. Simulating an absent-library classpath is an especially valuable test for starter maintainers.

## 27. Never test with shared mutable state

The `servletRunner`, `reactiveRunner`, and `plainRunner` fields are **immutable-style runner recipes**. Each `withPropertyValues(...)`, `withUserConfiguration(...)`, or `withBean(...)` returns a variant recipe; `run` creates and closes an isolated context.

Never:

- Reuse one live `ApplicationContext` across the entire test suite adding/removing bean definitions between methods.
- Rely on JUnit execution order so test B inherits properties from test A.
- Use a static mutable registry to record bean counts across contexts without resetting.
- Call `System.setProperty("lab.audit.enabled", "false")` in a test and forget to restore it; that leaks global state into other tests.
- Keep context/beans past the callback and invoke methods after disposal.
- Use `@DirtiesContext` to work around a bug in runner tests that already build fresh contexts.

When a test must set system properties or a custom classloader, use the runner's own hooks and keep scope strictly within each callback to avoid polluting the JVM.

## 28. Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Servlet bean missing in plain runner | Plain context is not Servlet web | Use `WebApplicationContextRunner` |
| Reactive bean missing in servlet runner | `Type.REACTIVE` does not match | Use `ReactiveWebApplicationContextRunner` |
| Both beans appear in servlet context | Missing/wrong `@ConditionalOnWebApplication` | Add type-specific guards |
| Bean remains when `enabled=false` | `@ConditionalOnProperty` wrong prefix/name/havingValue | Assert exact property key |
| No bean when flag absent | `matchIfMissing=false` or different policy | Clarify needed default |
| User bean exists yet starter creates default | Missing/wrong `@ConditionalOnMissingBean` or ordering | Test `withUserConfiguration`/`withBean` |
| Bean skipped due to unrelated `WebFilter` | Condition used overly broad `WebFilter` | Use feature-specific type/marker |
| `NoClassDefFoundError` when optional API absent | `@Bean` signature resolved early | Isolate class-level `@ConditionalOnClass` |
| Error "no ServletContext" | Plain runner or wrong custom context factory | Web runner with mock `ServletContext` |
| Reactive HTTP test lacks server | Runner creates only a small context | `WebTestClient`/full server integration |
| MVC interceptor bean exists yet does not run in HTTP | Missing `addInterceptors` registration | `WebMvcConfigurer` + MVC integration test |
| Test only asserts `context.isActive()` | Fails to verify conditions/defaults/overrides | Assert bean presence/absence and behavior |
| Both starters make full app use MVC | Boot prioritizes MVC by default | Set explicit web type in full test if needed |
| Imported too many auto-configs | Heavy context, out-of-scope side effects | Import only targeted `AutoConfigurations.of` |
| Classpath tests PASS yet consumer jar fails | Missing actual optional-dependency scenario | Test filtered classloader/consumer fixture |
| Order-dependent test failures | Shared static state/system properties | Use per-run properties/beans |
| Missing bean seen yet startup failure unread | Context failed due to dependency | Assert `hasNotFailed` and `ConditionEvaluationReport` |
| Using Spring Boot 4 imports with Boot 3.3 | APIs/packages differ across versions | Keep exact Boot 3.3 imports |

### Debugging workflow

1. Confirm Java 17+, Spring Boot 3.3.5, and starter dependencies.
2. Confirm the test uses the right runner type.
3. Confirm `AutoConfigurations.of(...)` contains the auto-config class under test.
4. Confirm the config class has `@ConditionalOnWebApplication(Type.SERVLET/REACTIVE)`.
5. Confirm `@ConditionalOnClass` for the optional web API.
6. Confirm `@ConditionalOnProperty` has the right prefix, name, `havingValue`, and `matchIfMissing`.
7. Confirm the user bean is registered **before** fallback auto-config and the missing-bean condition targets the exact feature type.
8. Check `assertThat(context).hasNotFailed()` before dereferencing beans.
9. If a bean is absent, inspect `ConditionEvaluationReport` to distinguish web/class/property/bean conditions.
10. Verify bean values/behavior, not mere existence.
11. To prove the HTTP pipeline, add a `MockMvc`/`WebTestClient` integration test for the right stack.
12. Run Gradle tests individually and as a full suite, inspecting JUnit HTML/XML reports.

## 29. Project test matrix

| Method | Runner | Verified behavior |
| --- | --- | --- |
| `servletRunnerCreatesOnlyServletBean` | Servlet | Servlet bean only, default label |
| `reactiveRunnerCreatesOnlyReactiveBean` | Reactive | Reactive bean only, default label |
| `plainRunnerCreatesNeitherWebBean` | Plain | No web beans |
| `servletFeatureCanBeDisabledByProperty` | Servlet | Flag false disables servlet |
| `reactiveFeatureCanBeDisabledByProperty` | Reactive | Flag false disables reactive |
| `servletLabelComesFromEnvironment` | Servlet | Custom label property |
| `reactiveLabelComesFromEnvironment` | Reactive | Custom label property |
| `servletAutoConfigBacksOffForUserConfiguration` | Servlet | `withUserConfiguration` back-off |
| `reactiveAutoConfigBacksOffForUserBean` | Reactive | `withBean` back-off |
| `servletInterceptorSetsResponseHeader` | Servlet | Direct interceptor method |
| `reactiveWebFilterSetsResponseHeader` | Reactive | Direct reactive WebFilter method |
| `modifiedRunnerDoesNotMutateBaseRunner` | Servlet | Runner recipe isolation |
| `nonTrueEnabledValueDoesNotMatchCondition` | Reactive | `havingValue=true` rejects unexpected |

**Total: 13 `@Test` methods from source**. This is the designed assertion matrix, not an executed and observed JUnit report.

### Run commands

When the project has a Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.audit.AuditAutoConfigurationTests'
./gradlew test
./gradlew build
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat build
```

When there is no Wrapper yet but a compatible Gradle is installed locally:

```bash
gradle test
gradle build
```

Test reports are generated after running at:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**Gradle was not executed while authoring this lesson.** Expected behavior from source is that tests verify the scenarios above; report PASS only after Gradle runs cleanly and the JUnit report confirms actual passed/failed/skipped counts.

## 30. Practice exercises

1. Run `AuditAutoConfigurationTests`; observe both Servlet and Reactive runners without a TCP server.
2. Change `Type.REACTIVE` to `Type.SERVLET` in the Reactive auto-config in a sandbox; which tests catch it?
3. Remove `@ConditionalOnWebApplication` from the Servlet auto-config, then run non-web/reactive tests.
4. Change `matchIfMissing=true` to false and inspect default tests.
5. Change `havingValue="true"` to false and check property-disabled tests.
6. Remove `@ConditionalOnMissingBean` and watch the custom user bean test fail due to duplicate types.
7. Change `@ConditionalOnMissingBean` to the supertype `WebFilter.class`, and analyze why it can accidentally back off due to unrelated filters.
8. Add a user configuration with `@Bean ServletAuditInterceptor` and verify exactly one bean.
9. Add a label property on the reactive runner and verify the custom value appears on the mock response.
10. Try using `ApplicationContextRunner` for a Servlet-only feature; explain why the guard fails to match.
11. Use `ConditionEvaluationReportLoggingListener` to print matched/mismatched conditions.
12. Add a nested config using `@ConditionalOnClass` with an optional fake API, tested via `FilteredClassLoader`.
13. Create a consumer module depending solely on `spring-boot-starter-web` and verify reactive auto-config backs off with no linkage error.
14. Create a consumer module with only `spring-boot-starter-webflux` and verify Servlet auto-config does not activate.
15. Add a `WebMvcConfigurer` registering the interceptor, then use `MockMvc` with a test controller.
16. Create a reactive `RouterFunction` route and use `WebTestClient` to verify the `WebFilter` is invoked in the pipeline.
17. Add `@ConfigurationProperties` with a typed `Duration`, testing valid/invalid values via `withPropertyValues`.
18. Try `@ConditionalOnBean` with a required collaborator and test both absent/present.
19. Add `withParent` to test bean search strategy in parent-child contexts.
20. Run the entire suite and inspect condition reports/Gradle HTML report before concluding PASS.

## 31. QA checklist before merging

- [ ] Chose the right `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`?
- [ ] Tested plain context as well to guard negative web conditions?
- [ ] Target auto-configurations passed via `AutoConfigurations.of(...)`?
- [ ] `@ConditionalOnWebApplication` specifies exact SERVLET/REACTIVE?
- [ ] `@ConditionalOnClass` placed at the right level for optional APIs?
- [ ] `@ConditionalOnProperty` has tests for default, false, true, and unexpected?
- [ ] `@ConditionalOnMissingBean` uses a feature-specific type, not overly broad?
- [ ] Tested user overrides via `withUserConfiguration`/`withBean`?
- [ ] Tested concrete beans and counts, not merely an active application context?
- [ ] Tested config properties actually affecting the bean?
- [ ] Tested bean method behavior without claiming it traversed the HTTP pipeline?
- [ ] Distinguished direct method calls from `MockMvc`/`WebTestClient` integration?
- [ ] When both MVC and WebFlux are present, verified which context type is chosen?
- [ ] `AutoConfiguration.imports` contains exact fully-qualified config classes?
- [ ] Auto-config package is not accidentally caught by consumer component scanning?
- [ ] Production starter has appropriate optional deps and classpath tests?
- [ ] Did not use bean overriding to mask missing-bean conditions?
- [ ] Context closes after `run`, without retaining destroyed beans?
- [ ] No static mutable state or system properties leaking across tests?
- [ ] `ConditionEvaluationReport` used when explaining mismatches?
- [ ] Startup failure tests are not masked by missing-bean assertions?
- [ ] Checked imports/APIs against Spring Boot 3.3.5?
- [ ] Did not claim Gradle PASS without an execution report?
- [ ] Test code never hits production endpoints or secrets?
- [ ] CI runs both Servlet and Reactive scenarios, not just one side?

## 32. Official references

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, runner tests, `AutoConfigurations.of`, `FilteredClassLoader`, and `ConditionEvaluationReport`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test contexts, MVC/Reactive type detection, and test slices.
- [Spring Boot 3.3 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): non-web runner and fluent APIs.
- [Spring Boot 3.3 — WebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html): Servlet context runner and `MockServletContext`.
- [Spring Boot 3.3 — ReactiveWebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html): reactive context runner.
- [Spring Boot 3.3 — ConditionalOnWebApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html): `Type.SERVLET`/`REACTIVE`/`ANY`.
- [Spring Boot 3.3 — ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): bean back-off.
- [Spring Boot 3.3 — ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `havingValue` and `matchIfMissing`.
- [Spring Framework — HandlerInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): MVC interceptor registration.
- [Spring Framework — WebFlux WebFilter](https://docs.spring.io/spring-framework/reference/web/webflux-web-handler-api.html): reactive filter chain/handler infrastructure.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test` and test lifecycle.

## 33. Summary

**`WebApplicationContextRunner`** and **`ReactiveWebApplicationContextRunner`** let you test Spring Boot auto-configurations that depend on web context types without booting the whole application or an HTTP server. They are especially valuable when building starters that enable a bean on Spring MVC yet not on WebFlux, or vice versa.

A reliable test suite must check **all three environments — Servlet, Reactive, and non-web** — along with property flags, user bean overrides, and bean behavior. Use `AutoConfigurations.of(...)` to load the exact auto-configurations, `withPropertyValues(...)` to simulate environments, `withUserConfiguration(...)`/`withBean(...)` to prove `@ConditionalOnMissingBean` back-off, and AssertJ to verify bean counts, types, and values.

Remember the boundary: **a bean's existence does not prove it participates in the MVC/WebFlux HTTP pipeline**; use `MockMvc`/`WebTestClient` or integration tests to verify request-level wiring. When a starter has optional dependencies, add classpath-absence tests with `FilteredClassLoader` and a real consumer module. The sample uses Java 17+, Spring Boot 3.3.5, and 13 test methods as a reproducible baseline, while actual PASS status must be verified via Gradle/CI reports before publishing.