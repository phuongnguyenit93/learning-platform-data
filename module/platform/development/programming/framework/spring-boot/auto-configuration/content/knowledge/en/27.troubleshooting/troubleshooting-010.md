# Web Configuration Mismatch Because Context Type Differs from Expected

## Learning Objectives

An auto-configuration may provide beans meant solely for Spring MVC, Spring WebFlux, or any web application. When a bean does not appear despite its dependencies being present, the cause often lies in the fact that **the actual ApplicationContext does not match the type required by the condition**.

Common scenarios:

- The configuration uses `@ConditionalOnWebApplication(type = SERVLET)`, yet the test uses `ApplicationContextRunner`, which creates a non-web context.
- The application has both Spring MVC and WebFlux, yet Spring Boot selects the Servlet stack by default.
- The application only needs `WebClient` to call APIs from a background service, yet auto-configuration requires a Reactive web context.
- A test manually constructs `AnnotationConfigApplicationContext`, even though the classpath contains full Servlet or Reactive dependencies.
- A test profile sets `spring.main.web-application-type=none`, causing Boot to create a non-web context.

This lesson explains how Spring Boot determines application type, how `@ConditionalOnWebApplication` evaluates the context, how to distinguish Servlet from Reactive, and how to reproduce the issue with context runners.

After this lesson, you will be able to:

- Distinguish `WebApplicationType` from `ConditionalOnWebApplication.Type`.
- Predict condition outcomes in non-web, Servlet, and Reactive contexts.
- Understand why an application with both MVC and WebFlux still runs on the Servlet stack.
- Distinguish a web server from a web ApplicationContext.
- Choose the right conditions for server-side integrations vs. client-only libraries.
- Write tests using `ApplicationContextRunner`, `WebApplicationContextRunner`, and `ReactiveWebApplicationContextRunner`.
- Use the Condition Evaluation Report and dependency tree to find root causes.

## 1. Start with the Actual ApplicationContext Type

Spring Boot chooses the ApplicationContext type when SpringApplication starts. The three main application types are `WebApplicationType.NONE`, `WebApplicationType.SERVLET`, and `WebApplicationType.REACTIVE`.

| WebApplicationType | Typical context | Meaning |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | Application does not run as a web app and starts no embedded web server |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Servlet web application, typically using Spring MVC |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | Reactive web application, typically using Spring WebFlux |

This enum belongs to package `org.springframework.boot`. It controls how SpringApplication creates the context and starts the web server.

You can configure the application type via a property:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Or set it directly during bootstrap:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class AcmeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(AcmeApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
~~~

If the actual context is Servlet, a condition requiring Reactive will not match even if the WebFlux dependency is on the classpath. Conversely, a Servlet-only condition will not match in a Reactive context even if servlet APIs appear indirectly in the dependency tree.

## 2. Distinguish Two Similarly Named Enums

Spring Boot has two separate enums serving two purposes:

| Enum | Package | Values | Role |
| --- | --- | --- | --- |
| `WebApplicationType` | `org.springframework.boot` | `NONE`, `SERVLET`, `REACTIVE` | Chooses the ApplicationContext type when SpringApplication starts |
| `ConditionalOnWebApplication.Type` | `org.springframework.boot.autoconfigure.condition` | `ANY`, `SERVLET`, `REACTIVE` | Chooses which web context types a condition accepts |

Example:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;

@ConditionalOnWebApplication
class AnyWebConfiguration {
}

@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
class ServletOnlyConfiguration {
}

@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
class ReactiveOnlyConfiguration {
}

@ConditionalOnNotWebApplication
class BackgroundWorkerConfiguration {
}
~~~

By default `@ConditionalOnWebApplication` uses `type = ANY`, so both Servlet and Reactive web applications can match.

Do not confuse `ConditionalOnWebApplication.Type.ANY` with `WebApplicationType.NONE`. ANY means accepting any web context; NONE means the application is not a web app.

## 3. What Does `@ConditionalOnWebApplication` Check?

`@ConditionalOnWebApplication` is a Spring Boot condition used to restrict configurations by web application type:

- `ANY`: any web application.
- `SERVLET`: Servlet-based web applications only.
- `REACTIVE`: Reactive-based web applications only.

A Servlet web application is identified via traits such as Spring's `WebApplicationContext`, session scope, or `ConfigurableWebEnvironment`. A Reactive web application uses `ReactiveWebApplicationContext` or `ConfigurableReactiveWebEnvironment`.

Key point: **having web dependencies present is not enough for the condition to match**. The context evaluating the condition must also be of the matching type.

For instance, the following test creates a non-web context:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(MyServletAutoConfiguration.class))
        .run(context -> {
            // Servlet condition does not match in a non-web context.
        });
~~~

Even though the test runtime may contain spring-webmvc, `ApplicationContextRunner` creates an `AnnotationConfigApplicationContext` by default. That is not a Servlet `WebApplicationContext`.

## 4. How Does Spring Boot Choose Servlet vs. Reactive?

When using SpringApplication without forcing an application type via configuration, Boot infers the web type from the classpath:

1. If Spring MVC is present, Boot chooses a Servlet web application.
2. If Spring MVC is absent while Spring WebFlux is present, Boot chooses a Reactive web application.
3. If neither is present, Boot chooses a non-web application.

**If both Spring MVC and WebFlux are present, Spring MVC takes precedence by default.**

This choice is intentional. Many MVC applications add WebFlux solely to use `WebClient` as an asynchronous HTTP client; having WebFlux on the classpath does not mean the application wants to run a Reactive server.

Example:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

With both starters, the application normally runs on the Servlet stack. If you want to run WebFlux, set explicitly:

~~~properties
spring.main.web-application-type=reactive
~~~

Or call `application.setWebApplicationType(WebApplicationType.REACTIVE)` before running the application.

### 4.1. WebClient Does Not Mean Reactive Server

`WebClient` is an HTTP client. It can be used in:
- Spring MVC applications.
- Spring WebFlux applications.
- Non-web applications such as batch jobs or scheduled workers, if the required client dependencies are present.

Therefore, if a library provides only an HTTP client, the appropriate condition is usually `@ConditionalOnClass(WebClient.class)` or a property condition. Do not require `@ConditionalOnWebApplication(type = REACTIVE)` if the library does not need a Reactive server context.

Conversely, if the library registers `WebFilter`, `ServerWebExchange`, `HandlerMapping`, or WebFlux server configuration, a Reactive context is part of the contract and the REACTIVE condition fits.

Similarly, `Filter`, `HttpServletRequest`, `HandlerInterceptor`, and Servlet APIs belong to the Servlet stack. A Servlet integration should be gated with the SERVLET condition when needed.

## 5. Web ApplicationContext Does Not Mean a Server Listening on a Port

A common diagnostic mistake is thinking the condition matches only when an embedded web server is running. In fact, web context and server lifecycle are related yet distinct concepts.

For example, setting:

~~~properties
server.port=-1
~~~

can disable HTTP endpoints while the application still creates a `WebApplicationContext`. This is useful for tests needing web infrastructure without opening a port.

Conversely:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

tells Spring Boot to create a non-web ApplicationContext. In that case `@ConditionalOnWebApplication` does not match and `@ConditionalOnNotWebApplication` can match.

A Servlet application can be deployed as a WAR into a servlet container or use an embedded server. If you need to distinguish traditional WAR deployments, use the dedicated `@ConditionalOnWarDeployment` condition; do not infer that solely from `@ConditionalOnWebApplication(type = SERVLET)`.

## 6. Separating Classpath Conditions from Web-Context Conditions

The two conditions answer different questions:

- `@ConditionalOnClass`: Is the API/framework class on the classpath?
- `@ConditionalOnWebApplication`: Is the current ApplicationContext the web type the feature requires?

A Servlet integration may need both:

~~~java
package com.acme.web.servlet;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;

@AutoConfiguration
@ConditionalOnClass(name = "org.springframework.web.servlet.DispatcherServlet")
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
public class AcmeServletAutoConfiguration {
}
~~~

A corresponding Reactive integration:

~~~java
package com.acme.web.reactive;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;

@AutoConfiguration
@ConditionalOnClass(name = "org.springframework.web.reactive.DispatcherHandler")
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
public class AcmeReactiveAutoConfiguration {
}
~~~

Here:
- The classpath condition guarantees the corresponding stack's API is present.
- The web condition guarantees the application actually uses the right web context type.
- If either condition fails to match, the configuration is not applied.

Splitting Servlet and Reactive configurations into separate classes also prevents classes or method signatures of one optional stack from being resolved in an application using only the other stack.

### 6.1. Do Not Substitute Classpath Conditions for Web Conditions

If you write only:

~~~java
@ConditionalOnClass(name = "org.springframework.web.servlet.DispatcherServlet")
class ServletConfiguration {
}
~~~

the configuration could be considered in a non-web context if servlet APIs happen to be on the classpath. That may be inappropriate if the bean needs a Servlet `WebApplicationContext`.

### 6.2. Do Not Substitute Web Conditions for Classpath Conditions

If an integration has optional dependencies and writes only:

~~~java
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
class ReactiveConfiguration {
}
~~~

the condition speaks only to the context. It does not guarantee every WebFlux library/adapter class the implementation needs is present. Add a classpath condition when the dependency is genuinely optional.

### 6.3. Guarding Optional Types at the Configuration-Class Level

If a bean method has return types or parameter types from an optional library, do not put the condition only on the method and assume the JVM will skip resolving signatures. For an optional stack, extract a separate configuration class and place `@ConditionalOnClass` at the class level. Spring Boot can read class-level metadata before loading the configuration class, avoiding errors from non-existent types.

## 7. Choosing Conditions Matching the Feature Type

| Library feature | Usually appropriate condition | Reason |
| --- | --- | --- |
| Servlet Filter or MVC interceptor | `@ConditionalOnWebApplication(SERVLET)` + classpath condition if needed | Depends on Servlet context/API |
| WebFlux WebFilter or HandlerFunction | `@ConditionalOnWebApplication(REACTIVE)` + classpath condition | Depends on Reactive context/API |
| Bean shared across any web stack | `@ConditionalOnWebApplication` (ANY) | Needs a web context without depending on a specific stack |
| WebClient HTTP client | `@ConditionalOnClass(WebClient.class)` | Client works in MVC, WebFlux, or non-web apps |
| RestClient/RestTemplate | Classpath condition and property if needed | HTTP clients do not require a server-side web context |
| Batch/scheduled worker | `@ConditionalOnNotWebApplication` if truly non-web only | Feature strictly for non-web applications |
| Shared library needing no web API | No web condition | Avoids accidentally excluding from non-web apps |

Conditions should reflect the bean's actual role, not just the dependency's package.

## 8. Testing with All Three ApplicationContextRunner Types

Spring Boot 3.3 provides three useful runners:

- `ApplicationContextRunner`: standard non-web context.
- `WebApplicationContextRunner`: Servlet-based web context.
- `ReactiveWebApplicationContextRunner`: Reactive web context.

These three runners test conditions in the right environment. Never use the default `ApplicationContextRunner` to conclude a Servlet or Reactive condition is broken in production.

**File:** `src/test/java/example/web/WebStackConditionTests.java`

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class WebStackConditionTests {

    private final AutoConfigurations autoConfigurations =
            AutoConfigurations.of(WebStackAutoConfiguration.class);

    @Test
    void standardApplicationContextRunnerCreatesNonWebContext() {
        new ApplicationContextRunner()
                .withConfiguration(this.autoConfigurations)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AnyWebMarker.class);
                    assertThat(context).doesNotHaveBean(ServletMarker.class);
                    assertThat(context).doesNotHaveBean(ReactiveMarker.class);
                    assertThat(context).hasSingleBean(NonWebMarker.class);
                });
    }

    @Test
    void servletRunnerMatchesAnyAndServletConditions() {
        new WebApplicationContextRunner()
                .withConfiguration(this.autoConfigurations)
                .run(context -> {
                    assertThat(context).hasSingleBean(AnyWebMarker.class);
                    assertThat(context).hasSingleBean(ServletMarker.class);
                    assertThat(context).doesNotHaveBean(ReactiveMarker.class);
                    assertThat(context).doesNotHaveBean(NonWebMarker.class);
                });
    }

    @Test
    void reactiveRunnerMatchesAnyAndReactiveConditions() {
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(this.autoConfigurations)
                .run(context -> {
                    assertThat(context).hasSingleBean(AnyWebMarker.class);
                    assertThat(context).doesNotHaveBean(ServletMarker.class);
                    assertThat(context).hasSingleBean(ReactiveMarker.class);
                    assertThat(context).doesNotHaveBean(NonWebMarker.class);
                });
    }

    static class AnyWebMarker {
    }

    static class ServletMarker {
    }

    static class ReactiveMarker {
    }

    static class NonWebMarker {
    }

    @AutoConfiguration
    static class WebStackAutoConfiguration {

        @Bean
        @ConditionalOnWebApplication
        AnyWebMarker anyWebMarker() {
            return new AnyWebMarker();
        }

        @Bean
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.SERVLET)
        ServletMarker servletMarker() {
            return new ServletMarker();
        }

        @Bean
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.REACTIVE)
        ReactiveMarker reactiveMarker() {
            return new ReactiveMarker();
        }

        @Bean
        @ConditionalOnNotWebApplication
        NonWebMarker nonWebMarker() {
            return new NonWebMarker();
        }
    }
}
~~~

### 8.1. Reading the Results

**Test 1 — ApplicationContextRunner**

The default runner creates a non-web `AnnotationConfigApplicationContext`. It does not turn into a web context simply because `spring-webmvc` and `spring-webflux` are on the test classpath.

- ANY does not match.
- SERVLET does not match.
- REACTIVE does not match.
- NOT WEB matches.

**Test 2 — WebApplicationContextRunner**

The runner creates a Servlet-based `ConfigurableWebApplicationContext`. It does not need to start a real embedded server just to test conditions.

- ANY matches.
- SERVLET matches.
- REACTIVE does not match.
- NOT WEB does not match.

**Test 3 — ReactiveWebApplicationContextRunner**

The runner creates a `ConfigurableReactiveWebApplicationContext`.

- ANY matches.
- SERVLET does not match.
- REACTIVE matches.
- NOT WEB does not match.

This test suite proves context type is a direct factor in web conditions. It also shows classpath checks alone cannot substitute for context tests.

## 9. Dependencies and Test Run Commands

The example uses Java 17+, Spring Boot 3.3.x, JUnit 5, and AssertJ. In Gradle Groovy DSL, assuming Spring Boot versions are managed by plugin or BOM:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Both web starters are added in test scope to supply both Servlet and Reactive test infrastructure. If the test module already includes those dependencies, no duplicate declaration is needed.

Run the single test class:

~~~bash
# Linux/macOS
./gradlew test --tests "example.web.WebStackConditionTests"

# Windows
gradlew.bat test --tests "example.web.WebStackConditionTests"
~~~

**Expected result:** three tests PASS. The tests verify bean registration only, opening no HTTP ports and calling no external services.

## 10. Testing When an Application Has Both MVC and WebFlux

A real-world case:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

When booting via `SpringApplication` with default configuration, Boot prioritizes MVC and selects a Servlet context. Consequently:
- `@ConditionalOnWebApplication(type = SERVLET)` can match.
- `@ConditionalOnWebApplication(type = REACTIVE)` does not match.
- `@ConditionalOnWebApplication` (default ANY) can match.

If the application truly wants to run a WebFlux server, set explicitly:

~~~properties
spring.main.web-application-type=reactive
~~~

For integration tests using `@SpringBootTest`, you can set:

~~~java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class ReactiveApplicationTests {
}
~~~

Or force the type directly on `SpringApplication` before calling `run`. Do not try to fix it merely by adding WebFlux dependencies while MVC is still selected.

### 10.1. Distinguishing Test Slices

- `@WebMvcTest`: focuses on Spring MVC/Servlet components.
- `@WebFluxTest`: focuses on Spring WebFlux/Reactive components.
- `@SpringBootTest(webEnvironment = NONE)`: creates a non-web environment.
- `@SpringBootTest(webEnvironment = MOCK)`: uses a matching web context when the app has a web stack; the stack type still depends on how Boot resolves web application type.
- `RANDOM_PORT` or `DEFINED_PORT`: launches a real server on the corresponding port.

If an application has both stacks and a test slice does not reflect the desired context type, set `spring.main.web-application-type` explicitly and verify which runner/test annotation is used.

## 11. Other Reasons a Web Condition Might Not Match

### 11.1. Application Configured as NONE

Look for values like:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

This property may live in a specific profile, environment variable, command line, ConfigMap, or imported config file. If a test profile sets NONE, web auto-configurations will not match in that profile.

### 11.2. Test Manually Constructs a Context

Code like:

~~~java
new AnnotationConfigApplicationContext(MyConfiguration.class);
~~~

always creates a non-web context. Having Servlet/Reactive dependencies on the test runtime does not change this context's class.

To test Servlet conditions, use `WebApplicationContextRunner` or construct a proper Servlet `WebApplicationContext`. To test Reactive conditions, use `ReactiveWebApplicationContextRunner`.

### 11.3. Custom ApplicationContextFactory

An application may configure a custom factory on `SpringApplication`. If the factory returns a context not matching the expected web type, conditions can fail to match even when `WebApplicationType` and classpath look right.

Check:
- The class of context created by the factory.
- Web interfaces implemented by the context.
- The `Environment` used by the context.
- Whether factory configuration is overridden in tests/profiles.

### 11.4. Servlet API Present Without a Spring MVC Context

A dependency might bring the Servlet API onto the classpath for another integration, while the application does not actually use Spring MVC. Having Servlet types on the classpath does not automatically turn `AnnotationConfigApplicationContext` into a Servlet `WebApplicationContext`.

If a feature needs only Servlet APIs and can run outside a Spring web context, re-evaluate whether to use `@ConditionalOnWebApplication` or only a classpath condition.

### 11.5. Using a Condition at the Wrong Scope

If a condition is placed at the class level, the entire configuration class is skipped when the condition fails. If only one bean requires a Servlet context, consider placing the condition on that bean method rather than excluding the whole class.

However, if the configuration class directly references optional APIs in method signatures, extract a separate class-level configuration to guard type resolution.

### 11.6. Confusing Web Application with WAR Deployment

`@ConditionalOnWebApplication(type = SERVLET)` matches both embedded-server Servlet apps and container-deployed Servlet apps. If a feature is strictly for traditional WAR deployments, use the dedicated `@ConditionalOnWarDeployment` condition.

### 11.7. Confusing Parent/Child Contexts

An application can have a root context and a child context. Determine which context the condition is evaluated in. A bean or web infrastructure registered in another context does not automatically mean the current context shares the same web context type.

## 12. Diagnosing with the Condition Evaluation Report

When the application boots yet an auto-configuration does not appear, run with debug:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot prints the Condition Evaluation Report. Locate the configuration class name or relevant condition, then check:

- Was the configuration excluded by a classpath condition?
- Does the web condition require ANY, SERVLET, or REACTIVE?
- Is the current context recognized as Servlet or Reactive?
- Did another property/profile condition veto the configuration?
- Did another condition on the same configuration fail to match?

Never look at only one annotation and draw conclusions. Multiple conditions on the same configuration generally combine with AND: all must match for the configuration to apply.

### 12.1. Inspecting Context Type at Runtime

When direct confirmation is needed, log the context and `Environment` classes:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
class ContextTypeProbe {

    private static final Logger log =
            LoggerFactory.getLogger(ContextTypeProbe.class);

    ContextTypeProbe(ApplicationContext context) {
        log.info("ApplicationContext type: {}",
                context.getClass().getName());
        log.info("Environment type: {}",
                context.getEnvironment().getClass().getName());
    }
}
~~~

Example log illustrating the info to inspect:

~~~text
ApplicationContext type: org.springframework.boot.web.servlet.context.AnnotationConfigServletWebServerApplicationContext
Environment type: org.springframework.web.context.support.StandardServletEnvironment
~~~

Exact class names depend on Boot version, context factory, and startup mode. This is a format example, not fixed stdout for every application.

### 12.2. Inspecting the Dependency Tree

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree
~~~

Look for:
- `spring-boot-starter-web`.
- `spring-boot-starter-webflux`.
- `spring-webmvc`.
- `spring-webflux`.
- Servlet API.
- Transitive dependencies pulling in a web stack.

The dependency tree shows which libraries are present. It does not by itself show which context was actually created; combine it with `WebApplicationType`, `ApplicationContextFactory`, and the runtime context class.

## 13. Ordered Troubleshooting Workflow

1. **Read what the condition requires.** ANY, SERVLET, or REACTIVE? Are there extra classpath/property conditions?
2. **Confirm the actual context.** Check the ApplicationContext class, Environment, and WebApplicationType.
3. **Check effective properties.** Search for `spring.main.web-application-type` across profiles, deployment environment, and command line.
4. **Check for both web stacks.** If MVC and WebFlux are both present, remember MVC wins by default.
5. **Check the test runner.** `ApplicationContextRunner` is non-web; use the right runner for Servlet/Reactive.
6. **Check custom factories.** Ensure no context factory creates an unexpected context.
7. **Read the Condition Evaluation Report.** Look up the exact reason for each condition.
8. **Check the dependency tree.** Confirm required stacks and APIs exist on the runtime classpath.
9. **Re-evaluate feature boundaries.** Client-only code may not need web conditions; server integrations need stack-specific conditions.
10. **Add regression tests.** Test both matching and non-matching contexts to prevent recurrence.

## 14. Common Mistakes

1. **Seeing WebFlux on the classpath and assuming the app is Reactive.** If Spring MVC is also present, Boot picks Servlet by default.
2. **Using `ApplicationContextRunner` to test Servlet conditions.** That runner creates a non-web context; use `WebApplicationContextRunner`.
3. **Using `ApplicationContextRunner` to test Reactive conditions.** Use `ReactiveWebApplicationContextRunner` or a properly constructed Reactive context.
4. **Confusing `WebApplicationType` with `ConditionalOnWebApplication.Type`.** One selects the context, the other restricts the condition.
5. **Using REACTIVE for client-only `WebClient`.** `WebClient` works in MVC or non-web apps; require Reactive context only if beans depend on Reactive server APIs.
6. **Using ANY for Servlet-only beans.** The condition can match in a Reactive context even though the bean requires Servlet APIs.
7. **Checking only the classpath.** Class presence does not prove the context has the right type.
8. **Checking only the context.** The right context does not prove optional APIs exist; add classpath conditions if needed.
9. **Setting `spring.main.web-application-type=none` in tests.** This property prevents web conditions from matching.
10. **Confusing `server.port=-1` with `web-application-type=none`.** Port -1 can still keep a `WebApplicationContext`; NONE creates a non-web context.
11. **Manually creating `AnnotationConfigApplicationContext` and expecting a web context.** Choose the appropriate context class or runner.
12. **Leaving both MVC and WebFlux present without choosing a stack explicitly.** Boot prefers MVC; set the type explicitly if Reactive is intended.
13. **Putting classpath conditions on methods with optional types.** Extract a class-level configuration to avoid resolving signatures before conditions protect them.
14. **Skipping the Condition Evaluation Report.** Another condition might be excluding the configuration; enable `--debug`.
15. **Using `@ConditionalOnWarDeployment` to match every Servlet app.** Embedded Servlet apps are not traditional WAR deployments.
16. **Assuming a web context always has a listening server.** `WebApplicationContext` can exist without opening an HTTP port.
17. **Ignoring context hierarchy.** Conditions evaluate in a specific context; do not infer from beans in another context.
18. **Testing only the happy-path branch.** Test non-web, Servlet, and Reactive to catch misactivated configurations.

## 15. Web Auto-Configuration Review Checklist

### Context and Conditions

- [ ] Determined whether beans target Servlet, Reactive, or any web context.
- [ ] Used the proper `ConditionalOnWebApplication.Type`.
- [ ] Used `ConditionalOnNotWebApplication` for non-web-only features when needed.
- [ ] Distinguished `WebApplicationType` from `ConditionalOnWebApplication.Type`.
- [ ] Did not confuse client libraries with server-side web integrations.
- [ ] Considered classpath conditions for optional framework APIs.

### Bootstrap and Environment

- [ ] `spring.main.web-application-type` is not unintentionally overridden.
- [ ] When MVC and WebFlux coexist, the chosen stack matches expectations.
- [ ] Custom `ApplicationContextFactory` returns the right context type.
- [ ] Distinguished web context from embedded server and WAR deployment.

### Testing and Diagnostics

- [ ] Non-web conditions tested with `ApplicationContextRunner`.
- [ ] Servlet conditions tested with `WebApplicationContextRunner`.
- [ ] Reactive conditions tested with `ReactiveWebApplicationContextRunner`.
- [ ] Tests cover both matching and non-matching branches.
- [ ] Condition Evaluation Report inspected when failures occur.
- [ ] Dependency tree and runtime context type confirmed.

## 16. Self-Check Questions

**Question 1.** A test uses `ApplicationContextRunner` with `spring-boot-starter-web` on the test classpath. Why does `@ConditionalOnWebApplication(SERVLET)` still not match?

**Answer:** `ApplicationContextRunner` creates a non-web `AnnotationConfigApplicationContext` by default. Having dependencies present does not automatically turn the context into a Servlet `WebApplicationContext`.

**Question 2.** An application includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`. Which stack does Boot choose by default?

**Answer:** Servlet/MVC takes precedence. For a Reactive server, set `spring.main.web-application-type=reactive` or configure `WebApplicationType.REACTIVE` during bootstrap.

**Question 3.** A background service uses `WebClient` to call an API. Should it require `@ConditionalOnWebApplication(REACTIVE)`?

**Answer:** No, if the service only needs an HTTP client. Check the classpath for `WebClient` and required dependencies; a Reactive web context is needed only for server-side WebFlux integrations.

**Question 4.** What is the difference between `server.port=-1` and `spring.main.web-application-type=none`?

**Answer:** `server.port=-1` can disable HTTP endpoints while still creating a `WebApplicationContext`. `web-application-type=none` instructs the application to use a non-web context.

**Question 5.** Which runners test Servlet and Reactive conditions without starting an embedded server?

**Answer:** `WebApplicationContextRunner` for Servlet and `ReactiveWebApplicationContextRunner` for Reactive. Both create suitable contexts for evaluating conditions.

**Question 6.** What type does `@ConditionalOnWebApplication` accept by default?

**Answer:** ANY, meaning it accepts any web application, including both Servlet and Reactive.

**Question 7.** To confirm a condition failed to match due to context type, what should you inspect?

**Answer:** The Condition Evaluation Report, actual `ApplicationContext` class, `Environment` type, effective `WebApplicationType`, and properties/profiles configuring web application type.

## 17. Key Takeaways

A web condition matches only when the actual `ApplicationContext` type matches what the annotation requires. Spring Boot distinguishes non-web, Servlet, and Reactive; when MVC and WebFlux coexist, MVC wins by default. `@ConditionalOnWebApplication` defaults to ANY, whereas SERVLET and REACTIVE restrict to their respective stacks.

Distinguish server-side integrations from HTTP clients. A `WebClient` does not make an application a Reactive web application. When testing, pick the right runner: `ApplicationContextRunner` for non-web, `WebApplicationContextRunner` for Servlet, and `ReactiveWebApplicationContextRunner` for Reactive. Finally, use the Condition Evaluation Report and runtime context class to confirm the root cause before changing dependencies or conditions.

### Official Spring Boot 3.3 Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — WebApplicationType Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html)
- [Spring Boot 3.3 — ConditionalOnWebApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html)
- [Spring Boot 3.3 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 — WebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html)
- [Spring Boot 3.3 — ReactiveWebApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html)
- [Spring Boot 3.3 — Core Features: Web Environment](https://docs.spring.io/spring-boot/docs/3.3.0-M2/reference/html/features.html)
