# Tracing the Reactive Conditions of WebFluxAutoConfiguration

## 1. Goal: Why Is WebFlux on the Classpath Yet Auto-Configuration Still Does Not Run?

`WebFluxAutoConfiguration` is Spring Boot's auto-configuration for Spring WebFlux. When investigating why this configuration does not create expected WebFlux components, do not check only the `spring-boot-starter-webflux` dependency. You need to trace three independent questions:

1. **Is the framework available?** Are Spring WebFlux classes, especially `WebFluxConfigurer`, on the runtime classpath?
2. **Is the application genuinely running as Reactive web?** Is the current `ApplicationContext`/`Environment` recognized as a reactive web application?
3. **Has the user already provided the WebFlux foundation?** Is there already a bean of type `WebFluxConfigurationSupport` causing Boot's default configuration to back off?

In Spring Boot 3.3.x, these three questions correspond to the class-level conditions of `WebFluxAutoConfiguration`:

- `@ConditionalOnClass(WebFluxConfigurer.class)`
- `@ConditionalOnWebApplication(type = Type.REACTIVE)`
- `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)`

The configuration also declares `after` ordering relationships with other foundational auto-configurations. Those relationships determine bean definition processing order; they do not replace the three conditions above and do not start a web server.

This lesson traces from the classpath, application context type, back-off conditions, and prerequisite relationships to the Condition Evaluation Report. At the end of the lesson, there is a Java 17/JUnit 5 test suite using `ApplicationContextRunner` and `ReactiveWebApplicationContextRunner` to demonstrate the results across three scenarios.

## 2. Distinguishing the Components of the Reactive Web Stack

A WebFlux application does not consist of a single configuration class. The main components have different responsibilities:

| Component | Role | Question to Check |
| --- | --- | --- |
| `spring-webflux` | WebFlux framework: controller, handler, router, WebFlux configuration API | Is `WebFluxConfigurer` on the classpath? |
| `WebFluxAutoConfiguration` | Registers Spring Boot's WebFlux configuration and default customizations | Is the reactive context the right type and does Boot need to back off? |
| `ReactiveWebServerFactoryAutoConfiguration` | Configures the factory for the reactive embedded web server | Is there a suitable server factory? |
| `HttpHandlerAutoConfiguration` | Connects the WebFlux application to the `HttpHandler` used by the server | Is there a handler to process requests? |
| Reactor Netty / Jetty / Tomcat reactive | Corresponding server/client implementation | Does the runtime have a suitable implementation? |
| `WebClientAutoConfiguration` | Supports WebClient for the HTTP client | Can WebClient be used even when the application does not run a reactive server? |

**Having the WebFlux library does not mean having a reactive server.** `WebClient` can be used in an MVC application or a non-web application. Auto-configuration for WebClient and auto-configuration for a WebFlux server are two different flows.

Spring WebFlux is a reactive web framework supporting both annotated controllers and functional endpoints. It uses Reactor/Reactive Streams to express asynchronous, non-blocking processing. However, merely seeing `Mono`, `Flux`, or `WebClient` in code is not enough to conclude the application is running with a reactive web context.

### 2.1. From Dependencies to Runtime Context

Spring Boot selects `WebApplicationType` when bootstrapping via `SpringApplication`:

| Type | Meaning | Typical Context |
| --- | --- | --- |
| `NONE` | Does not run as a web application | `AnnotationConfigApplicationContext` |
| `SERVLET` | Servlet/MVC-based web application | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | Reactive/WebFlux-based web application | `AnnotationConfigReactiveWebServerApplicationContext` |

If only the WebFlux dependency set and a corresponding reactive server are present, Boot usually deduces `REACTIVE`. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present together, Spring MVC takes precedence by default. This case is common because an MVC application may add WebFlux solely to use `WebClient`.

To explicitly run reactive when both MVC and WebFlux are present, set:

```properties
spring.main.web-application-type=reactive
```

Or configure in Java:

```java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

This is an illustrative snippet inside the Boot application's main method; `MyApplication` is the application class and `args` are the command-line arguments. Forcing the type only changes how bootstrap/context is selected. It does not add WebFlux dependencies by itself, does not supply a missing server implementation, and does not guarantee all integration beans initialize successfully.

### 2.2. Classpath Condition and Web Application Condition Ask Different Questions

`@ConditionalOnClass(WebFluxConfigurer.class)` asks whether the WebFlux class is available for configuration. It does not ask whether the running context is reactive.

`@ConditionalOnWebApplication(type = Type.REACTIVE)` asks whether the current context/environment exhibits reactive web characteristics. Boot recognizes a reactive web application based on `ReactiveWebApplicationContext` or `ConfigurableReactiveWebEnvironment`.

Therefore, the following can happen:

- `WebFluxConfigurer` is present, but the context is non-web: class condition matches, reactive web condition does not match.
- `WebFluxConfigurer` is present, but the context is Servlet: class condition matches, reactive web condition does not match.
- `WebFluxConfigurer` is present and the context is Reactive: both conditions can match.
- Context is Reactive, but WebFlux dependencies are incomplete: classpath condition does not match, WebFlux configuration is not applied.

This is the most common cause when developers inspect the dependency tree and wrongly conclude that `WebFluxAutoConfiguration` must certainly be enabled.

## 3. Reading the Class-Level Conditions of WebFluxAutoConfiguration

In Spring Boot 3.3, `WebFluxAutoConfiguration` resides in the package:

```java
org.springframework.boot.autoconfigure.web.reactive
```

The key conditions have the following meanings:

### 3.1. `@ConditionalOnClass(WebFluxConfigurer.class)`

`WebFluxConfigurer` is Spring Framework's API for customizing WebFlux configuration. This condition ensures the required framework is on the classpath before Boot processes configurations that depend on WebFlux.

If the class is missing:

- Auto-configuration is not applied.
- Beans provided by this configuration do not appear.
- The condition report typically shows `OnClassCondition` with a message stating the required class was not found.

When the WebFlux library is an optional dependency, a class-level annotation helps isolate references to classes that only exist in that dependency. Avoid placing an optional class directly as the return type of a bean method and expecting a method-level condition to always prevent the JVM from resolving the signature before the class is loaded.

### 3.2. `@ConditionalOnWebApplication(type = Type.REACTIVE)`

This condition requires the current context to be a reactive web application. It excludes cases such as:

- A batch/CLI application using WebFlux APIs but running with `WebApplicationType.NONE`.
- A Spring MVC application adding the WebFlux dependency to use `WebClient`.
- A test using a plain `ApplicationContext`, even though WebFlux is on the test classpath.

When testing this condition, you must use the right context type. `ApplicationContextRunner` creates a plain context by default; it does not turn into a reactive context just because you add the `spring.main.web-application-type=reactive` property. Use `ReactiveWebApplicationContextRunner` or start a real `SpringApplication` with the reactive type.

### 3.3. `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)`

This is the back-off condition that allows the application to take control of WebFlux configuration. If the context already has a bean of type `WebFluxConfigurationSupport`, Boot skips `WebFluxAutoConfiguration`.

A typical case is when a user declares:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFlux
class MyWebFluxConfiguration {
}
```

`@EnableWebFlux` imports `DelegatingWebFluxConfiguration`; this class extends `WebFluxConfigurationSupport`. Thus Boot's missing-bean condition can detect the user-activated WebFlux configuration and back off.

Distinguish two ways of customizing:

- **Extending Boot configuration:** declare a bean implementing `WebFluxConfigurer` without using `@EnableWebFlux`. This keeps Spring Boot's default customizations.
- **Taking full control of WebFlux configuration:** use `@EnableWebFlux`. Boot backs off and the application is responsible for configuring the foundation as needed.

Merely declaring a `WebFluxConfigurer` bean does not mean `WebFluxConfigurationSupport` is registered. It is an extension point for adding customizations; it does not ask Boot to back off from the entire auto-configuration.

### 3.4. Summary of Conditions in a Table

| Classpath has `WebFluxConfigurer` | Context | Already has `WebFluxConfigurationSupport` | Expected Outcome |
| :---: | --- | :---: | --- |
| No | Reactive | No | No-match due to class condition |
| Yes | Non-web | No | No-match due to reactive web condition |
| Yes | Servlet | No | No-match due to wrong web application type |
| Yes | Reactive | No | WebFluxAutoConfiguration can match |
| Yes | Reactive | Yes | Boot backs off due to missing-bean condition |

The table assumes the candidate is discovered, not excluded/filtered, and has no other conditions beyond the three class-level conditions under examination. "Can match" means the main conditions above are satisfied; other configurations in the application can still affect the initialization of dependent beans.

## 4. Tracing the after Relationships of WebFluxAutoConfiguration

In addition to conditions, this class declares relative ordering. In Boot 3.3, the prerequisite configurations listed via `after` include:

- `ReactiveWebServerFactoryAutoConfiguration`
- `CodecsAutoConfiguration`
- `ReactiveMultipartAutoConfiguration`
- `ValidationAutoConfiguration`
- `WebSessionIdResolverAutoConfiguration`

Translating the relationship into a graph using arrows from configurations that must be applied earlier to the configuration applied later:

```text
ReactiveWebServerFactoryAutoConfiguration ---\
CodecsAutoConfiguration ----------------------\
ReactiveMultipartAutoConfiguration -----------+--> WebFluxAutoConfiguration
ValidationAutoConfiguration ------------------/
WebSessionIdResolverAutoConfiguration --------/
```

This means `WebFluxAutoConfiguration` is ordered after these prerequisite configurations when they are in the same set of sorted candidates. The list does not assert an ordering among the five prerequisite configurations; there are no direct edges between them in the relationship being examined.

### 4.1. Why Is Each Prerequisite Group Needed?

| Prerequisite | Role in reactive stack | Question when investigating |
| --- | --- | --- |
| `ReactiveWebServerFactoryAutoConfiguration` | Configures reactive server factory and customizers | Is any server implementation recognized? |
| `CodecsAutoConfiguration` | Configures codecs used to read/write HTTP content | Are the required codecs available and customizable? |
| `ReactiveMultipartAutoConfiguration` | Multipart support for WebFlux | Have multipart configuration and properties been processed? |
| `ValidationAutoConfiguration` | Shared validation infrastructure | Is a validator configured if the validation dependency is present? |
| `WebSessionIdResolverAutoConfiguration` | Configures how session id is resolved for reactive web | Is there a custom bean replacing the default resolver? |

The `after` relationship only determines auto-configuration processing order. It does not force all prerequisites to create specific beans; each prerequisite's own conditions may still not match. If `ReactiveWebServerFactoryAutoConfiguration` is excluded or finds no server implementation, WebFlux framework configuration and embedded server availability may produce different outcomes.

### 4.2. Do Not Confuse the WebFlux Framework with the Reactive Server

`WebFluxAutoConfiguration` configures Spring Boot's WebFlux foundation. The reactive server factory is handled by a separate auto-configuration. `HttpHandlerAutoConfiguration` is another part in the flow connecting the context with the HTTP handler.

Diagnostics can be separated into three layers:

1. **Framework configuration:** is `WebFluxAutoConfiguration` allowed to apply?
2. **Server factory:** is there a matching `ReactiveWebServerFactory` bean?
3. **HTTP handler and runtime:** can the application create `HttpHandler` and start the server?

A test using `ReactiveWebApplicationContextRunner` can verify conditions and configuration beans without opening an HTTP port. It does not by itself prove a real server bound a port or accepted requests. To verify networking/runtime, a separate integration test is needed.

### 4.3. `@AutoConfigureOrder` Does Not Replace Conditions

The auto-configuration's Javadoc also shows an explicit order value. The order value only participates in general sorting among auto-configurations. It does not turn a Servlet context into Reactive, does not make WebFlux classes appear on the classpath, and does not bypass `@ConditionalOnMissingBean`.

When reading code, distinguish:

- `after`: specific prerequisite relationship.
- `@AutoConfigureOrder`: general priority during sorting.
- `@ConditionalOnClass` / `@ConditionalOnWebApplication` / `@ConditionalOnMissingBean`: decides whether the configuration applies.
- `@DependsOn` or injection: instance initialization relationship.

Do not change order when the real error is the wrong context type or missing dependencies.

## 5. Nested Configurations and WebFlux Extension Points

Spring Boot 3.3 Javadoc lists the nested classes inside `WebFluxAutoConfiguration`, including:

- `EnableWebFluxConfiguration`: configuration equivalent to `@EnableWebFlux`.
- `WebFluxConfig`.
- `WelcomePageConfiguration`.

`EnableWebFluxConfiguration` extends Spring Framework's WebFlux configuration and serves as the foundation for registering components supporting controllers/functional endpoints. Nested classes are Boot implementation details; library applications should not depend on their internal names or methods as a stable extension API.

### 5.1. Extending via WebFluxConfigurer

If you only want to customize a few parts while keeping Boot defaults, create a configuration like this:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configurePathMatching(PathMatchConfigurer configurer) {
        // Add path matching customization here.
    }
}
```

This is an illustrative snippet; import `WebFluxConfigurer` and `PathMatchConfigurer` from the corresponding WebFlux packages. Do not add `@EnableWebFlux` to this configuration if you want to retain Boot's default customizations.

Spring Boot can continue to provide codec configuration, static resource support, and default WebFlux integrations. You only add the callbacks you actually need.

### 5.2. When to Use @EnableWebFlux?

Use `@EnableWebFlux` when you want complete control over the WebFlux foundation. This annotation imports Spring Framework's configuration in place of Boot's corresponding default configuration. At that point, `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)` causes Boot to back off.

Do not use `@EnableWebFlux` just to register a controller or a simple `WebFluxConfigurer`. If misused, some customizations that developers expect from Boot may no longer be provided.

### 5.3. WebFluxRegistrations and HttpHandler Customizers

Some specialized extension points:

- `WebFluxRegistrations` allows replacing key components provided by default by `WebFluxAutoConfiguration`.
- `WebHttpHandlerBuilderCustomizer` allows customizing `WebHttpHandlerBuilder` before creating the HTTP handler.
- `WebFluxConfigurer` is suited for framework configuration callbacks such as path matching, formatters, resource handlers, and message codecs.

Choose the extension point matching the exact layer you need to change. If you only need to add a formatter or route configuration, there is no need to replace all of `WebFluxConfigurationSupport`.

### 5.4. Static Resources and Welcome Page

Spring Boot WebFlux auto-configuration supports serving static resources and WebJars. By default, static resources can be looked up in classpath directories such as `/static`, `/public`, `/resources`, and `/META-INF/resources`. The default resource mapping is `/**`; it can be changed via `spring.webflux.static-path-pattern` and `spring.web.resources.static-locations`.

`WelcomePageConfiguration` is the nested configuration related to the welcome page. When the default page does not appear, inspect static resource locations, static path pattern, custom resource handlers, and the conditions in the report before concluding `WebFluxAutoConfiguration` did not run.

## 6. Tracing the Conditions Evaluation Report

When running the application with `--debug`, Spring Boot writes the Condition Evaluation Report to the log. For `WebFluxAutoConfiguration`, look for the source:

```text
org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration
```

Conditions commonly read:

| Condition implementation | Meaning in this case |
| --- | --- |
| `OnClassCondition` | Is `WebFluxConfigurer` on the runtime classpath? |
| `OnWebApplicationCondition` | Is the current context a reactive web application? |
| `OnBeanCondition` | Is there a `WebFluxConfigurationSupport` causing Boot to back off? |

### 6.1. Examples of Common Results

**Scenario A — WebFlux is on the classpath, non-web application**

```text
WebFluxAutoConfiguration:
    @ConditionalOnClass found required class
    @ConditionalOnWebApplication did not find reactive web application
```

Meaning: classpath condition matches, but the context is not reactive web. Having no WebFlux auto-configuration is the right outcome.

**Scenario B — Reactive application, no custom WebFlux configuration**

```text
WebFluxAutoConfiguration:
    @ConditionalOnClass found required class
    @ConditionalOnWebApplication found reactive web application
    @ConditionalOnMissingBean did not find WebFluxConfigurationSupport
```

Meaning: all three main conditions allow the default configuration to apply.

**Scenario C — Reactive application already using @EnableWebFlux**

```text
WebFluxAutoConfiguration:
    @ConditionalOnClass found required class
    @ConditionalOnWebApplication found reactive web application
    @ConditionalOnMissingBean found WebFluxConfigurationSupport
```

Meaning: framework and context match, but user configuration already provides the WebFlux foundation. Boot backs off intentionally.

The sentences above paraphrase the messages by meaning, not fixed literal logs. Actual output may include class names, bean names, or version details.

### 6.2. Retrieving the Report via API in Tests

You can read outcomes by source class:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

ConditionEvaluationReport.ConditionAndOutcomes outcomes =
        report.getConditionAndOutcomesBySource()
                .get(WebFluxAutoConfiguration.class.getName());

if (outcomes != null) {
    System.out.println("fullMatch=" + outcomes.isFullMatch());

    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        System.out.println(
                item.getCondition().getClass().getSimpleName()
                        + " matched=" + item.getOutcome().isMatch()
                        + " message=" + item.getOutcome().getMessage());
    }
}
```

This is an illustrative snippet inside the callback of `ApplicationContextRunner` or `ReactiveWebApplicationContextRunner`; the variable `context` is the created test context. Import `ConditionEvaluationReport` from `org.springframework.boot.autoconfigure.condition`.

`isFullMatch()` is true only when all conditions recorded for the source match. If one condition does not match, the source is not applied even if the remaining conditions match.

If `outcomes` is null, do not immediately conclude the WebFlux condition did not match. Check whether the candidate was imported, whether it was excluded/filtered, and whether you are reading the report of the right context.

### 6.3. Actuator Endpoint

If the application has Actuator and the endpoint is exposed, `GET /actuator/conditions` provides the condition report in JSON format. You can use the endpoint to inspect positive/negative matches of `WebFluxAutoConfiguration` in a running context.

The endpoint must be configured with appropriate access/exposure. Do not expose diagnostics endpoints to an uncontrolled Internet environment; the report may contain class names, properties, and internal configuration structure. For local debugging, `--debug` is usually the fastest approach.

## 7. Java 17/JUnit 5 Test Suite: Three Context Types, One Classpath

The exercise below intentionally keeps Spring WebFlux on the classpath in every test, then changes the context type and user configuration. That demonstrates reactive conditions rely on context and bean state rather than dependencies alone.

Three scenarios:

1. `ApplicationContextRunner` creates a non-web context: class condition matches, reactive condition does not match.
2. `ReactiveWebApplicationContextRunner` creates a reactive context: main conditions match and Boot registers WebFlux infrastructure.
3. Reactive context with user `@EnableWebFlux`: missing-bean condition does not match, Boot yields configuration to the user.

Runners do not open an HTTP port; the tests focus on auto-configuration and bean definitions.

### 7.1. Project Structure

```text
webflux-auto-configuration-trace/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/WebFluxAutoConfigurationConditionTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'webflux-auto-configuration-trace'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

JDK 17+ is required for Spring Boot 3.3. Dependencies are pinned to the same version 3.3.13 to avoid mixing APIs across Boot lines.

### 7.2. Complete Test File

Create `src/test/java/demo/WebFluxAutoConfigurationConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurationSupport;

import static org.assertj.core.api.Assertions.assertThat;

class WebFluxAutoConfigurationConditionTest {

    private final ApplicationContextRunner nonWebRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(WebFluxAutoConfiguration.class));

    private final ReactiveWebApplicationContextRunner reactiveRunner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(WebFluxAutoConfiguration.class));

    @Configuration(proxyBeanMethods = false)
    @EnableWebFlux
    static class UserWebFluxConfiguration {
    }

    private ConditionAndOutcomes webFluxOutcomes(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        ConditionAndOutcomes outcomes =
                report.getConditionAndOutcomesBySource()
                        .get(WebFluxAutoConfiguration.class.getName());

        assertThat(outcomes)
                .as("Condition report for WebFluxAutoConfiguration")
                .isNotNull();

        return outcomes;
    }

    private boolean hasOutcome(
            ConditionAndOutcomes outcomes,
            String conditionSimpleName,
            boolean expectedMatch) {

        for (ConditionAndOutcome item : outcomes) {
            if (item.getCondition().getClass().getSimpleName()
                    .equals(conditionSimpleName)
                    && item.getOutcome().isMatch() == expectedMatch) {
                return true;
            }
        }
        return false;
    }

    @Test
    void nonWebContextDoesNotActivateWebFluxEvenWhenClassesArePresent() {
        nonWebRunner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                    .doesNotHaveBean(WebFluxConfigurationSupport.class);

            ConditionAndOutcomes outcomes = webFluxOutcomes(context);

            assertThat(outcomes.isFullMatch()).isFalse();
            assertThat(hasOutcome(
                    outcomes, "OnClassCondition", true)).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnWebApplicationCondition", false)).isTrue();
        });
    }

    @Test
    void reactiveContextActivatesBootWebFluxConfiguration() {
        reactiveRunner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                    .hasSingleBean(WebFluxConfigurationSupport.class);

            ConditionAndOutcomes outcomes = webFluxOutcomes(context);

            assertThat(outcomes.isFullMatch()).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnClassCondition", true)).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnWebApplicationCondition", true)).isTrue();
            assertThat(hasOutcome(
                    outcomes, "OnBeanCondition", true)).isTrue();
        });
    }

    @Test
    void userEnableWebFluxMakesBootBackOff() {
        reactiveRunner
                .withUserConfiguration(UserWebFluxConfiguration.class)
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context)
                            .hasSingleBean(WebFluxConfigurationSupport.class);

                    ConditionAndOutcomes outcomes = webFluxOutcomes(context);

                    assertThat(outcomes.isFullMatch()).isFalse();
                    assertThat(hasOutcome(
                            outcomes, "OnWebApplicationCondition", true))
                            .isTrue();
                    assertThat(hasOutcome(
                            outcomes, "OnBeanCondition", false))
                            .isTrue();
                });
    }
}
```

### 7.3. Running the Tests

From the project directory:

```bash
gradle test --tests demo.WebFluxAutoConfigurationConditionTest
```

If using Gradle Wrapper on Linux/macOS:

```bash
./gradlew test --tests demo.WebFluxAutoConfigurationConditionTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.WebFluxAutoConfigurationConditionTest
```

The expected result is **3 tests passed** when JDK and dependencies are compatible. This is the expected result of the sample test suite; do not treat Gradle logs as fixed stdout and do not claim the tests were run on the learner's environment.

### 7.4. Reading Each Test Result

| Test | Context | Class condition | Reactive condition | Missing-bean condition | Bean result |
| --- | --- | --- | --- | --- | --- |
| `nonWebContextDoesNotActivate...` | Non-web | Match | No-match | Does not decide final outcome | No `WebFluxConfigurationSupport` from Boot |
| `reactiveContextActivates...` | Reactive | Match | Match | Match | `WebFluxConfigurationSupport` present |
| `userEnableWebFluxMakesBootBackOff...` | Reactive + user `@EnableWebFlux` | Match | Match | No-match | User WebFlux configuration present; Boot backs off |

The first test is direct proof that having the WebFlux dependency on the test classpath still does not enable auto-configuration in a non-web context. The second test proves a reactive context and matching classpath allow Boot to configure. The final test proves custom WebFlux configuration causes the missing-bean condition to fail.

### 7.5. Limitations of the Test Runner

`ReactiveWebApplicationContextRunner` creates a reactive context to verify conditions and bean definitions. It does not simulate the full port-binding process of an executable JAR application.

If you want to verify the server actually accepts requests, write a separate integration test with `@SpringBootTest(webEnvironment = RANDOM_PORT)` and a server implementation on the classpath. You can use `WebTestClient` to send requests to the test application.

If the application has both MVC and WebFlux, default test bootstrapping with `@SpringBootTest` may create a Servlet context because MVC takes precedence. When the goal is to test reactive in a mixed classpath, set:

```java
@SpringBootTest(properties =
        "spring.main.web-application-type=reactive")
class ReactiveApplicationIntegrationTest {
}
```

This is an illustrative skeleton; a main application and appropriate test dependencies are required. For pure condition testing, `ReactiveWebApplicationContextRunner` is more direct and has fewer dependencies.

## 8. Investigation Workflow When WebFluxAutoConfiguration Does Not Match

Follow this sequence to avoid fixing the wrong dependency or annotation:

1. **Verify the candidate:** check that `WebFluxAutoConfiguration` is in `AutoConfiguration.imports` of Boot's autoconfigure JAR and is not excluded.
2. **Verify the classpath:** check whether runtime has `org.springframework.web.reactive.config.WebFluxConfigurer`. Use `./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath` to find the actual dependency.
3. **Verify the application type:** inspect `WebApplicationType` and the concrete `ApplicationContext`. If both MVC and WebFlux starters are present, check whether MVC takes precedence by default.
4. **Read the condition report:** locate the `WebFluxAutoConfiguration` source; distinguish `OnClassCondition`, `OnWebApplicationCondition`, and `OnBeanCondition`.
5. **Check custom configuration:** look for `@EnableWebFlux` or a bean of type `WebFluxConfigurationSupport`. If present, determine whether Boot backing off is intentional.
6. **Check predecessors:** see if reactive server factory, codecs, multipart, validation, and session resolver auto-configurations are selected and whether their conditions match.
7. **Check the server factory:** if WebFlux framework configuration matched but the app does not open a port, inspect `ReactiveWebServerFactory` and the Netty/Jetty/Tomcat reactive implementation.
8. **Check the HTTP handler:** if the server factory exists but requests are not handled, inspect `HttpHandler`, dispatcher handler, controllers/RouterFunctions, and customizers.
9. **Reproduce with tests:** keep dependencies fixed and switch sequentially through non-web, reactive, and user `@EnableWebFlux`. Assert both report outcomes and beans.
10. **Fix at the right layer:** add dependencies when classes are missing, change web application type when the context is wrong, remove `@EnableWebFlux` when you only want Boot customizations, or supply custom framework config if you genuinely want Boot to back off.

### 8.1. Symptoms and Troubleshooting Directions

| Symptom | Possible Cause | Inspection Direction |
| --- | --- | --- |
| `OnClassCondition` no-match | `spring-webflux` is not on the runtime classpath | Dependency tree, scope, starter |
| `OnClassCondition` matches but `OnWebApplicationCondition` no-match | Non-web or Servlet application | `WebApplicationType`, context class, MVC starter |
| Both above match, `OnBeanCondition` no-match | User config provides `WebFluxConfigurationSupport` | Look for `@EnableWebFlux`/`DelegatingWebFluxConfiguration` |
| WebFlux config matches but server does not start | Missing reactive server factory/implementation or server startup failure | `ReactiveWebServerFactory`, Reactor Netty/Jetty/Tomcat |
| Server starts but no endpoints | Controller/RouterFunction not scanned/imported, wrong mapping | Handler mappings, component scan, route beans |
| Static resources do not appear | Resource locations/path pattern/custom handler | `spring.web.resources.static-locations`, `spring.webflux.static-path-pattern` |
| Added WebFlux starter to MVC but still runs MVC | Boot prioritizes Spring MVC when both starters are present | Force `spring.main.web-application-type=reactive` if a WebFlux server is truly desired |
| Codec customizations stop working | Using `@EnableWebFlux` causes Boot to back off or customizer uses wrong extension point | Use `WebFluxConfigurer`/codec customizer if you want to keep Boot defaults |

## 9. Common Misconceptions

### 9.1. Having the WebFlux Dependency Means a Reactive Server

Incorrect. The dependency provides the API/framework; context type is a bootstrap decision. WebFlux can be used solely as an HTTP client in an MVC app.

### 9.2. @ConditionalOnClass Is Enough

Incorrect for `WebFluxAutoConfiguration`. It also needs a reactive web application context and no registered `WebFluxConfigurationSupport`.

### 9.3. Having a WebFluxConfigurer Bean Makes Boot Back Off

Not necessarily. `WebFluxConfigurer` is an extension point for Boot to apply customizations. The back-off condition checks `WebFluxConfigurationSupport`. `@EnableWebFlux` typically creates the support foundation and makes Boot back off.

### 9.4. @EnableWebFlux Only Adds One Configurer

No. It enables Spring Framework's foundational configuration and changes ownership of WebFlux configuration. Use it when you want to manage the entire framework configuration yourself.

### 9.5. WebFluxAutoConfiguration Opens the Port by Itself

Do not conclude this. Framework configuration, reactive server factory, and HTTP handler are related yet separate layers. A reactive test context can have WebFlux configuration without running an embedded server.

### 9.6. Source Missing from the Report Means Condition No-Match

Not necessarily. The candidate may not have been imported, may have been excluded/filtered, or you may be looking at a different context's report. Check discovery before drawing conclusions.

### 9.7. Relying on Log Order to Infer Initialization Order

The condition report describes condition evaluation; the `after` annotation describes auto-configuration processing order. They are not constructor or request timelines. Use dependency injection/lifecycle tracing for initialization questions.

## 10. Review Checklist When Modifying WebFlux Auto-Configuration

- [ ] `WebFluxAutoConfiguration` is in candidate imports and is not excluded.
- [ ] `WebFluxConfigurer` is on the runtime classpath.
- [ ] The context is genuinely `REACTIVE`, not `SERVLET` or `NONE`.
- [ ] If both MVC and WebFlux are present, a clear decision has been made whether to force `WebApplicationType.REACTIVE`.
- [ ] No user-configured `WebFluxConfigurationSupport` exists if Boot defaults are desired.
- [ ] If the user uses `@EnableWebFlux`, Boot back-off is accepted and required configurations are self-managed.
- [ ] Predecessors in `after` have been identified and their conditions checked separately.
- [ ] Framework configuration is distinguished from server factory and HTTP handler.
- [ ] There is a non-web test proving classpath presence alone does not enable WebFlux.
- [ ] There is a reactive test proving auto-configuration matches.
- [ ] There is a user `@EnableWebFlux` test proving back-off.
- [ ] If real HTTP verification is needed, a separate integration test exists rather than relying solely on the context runner.
- [ ] The condition report has been checked for the exact source and context.

**Takeaway:** `WebFluxAutoConfiguration` applies only when the WebFlux framework is on the classpath, the running context is a reactive web application, and no user-supplied `WebFluxConfigurationSupport` exists. The `after` relationships ensure it is processed after foundational configurations such as reactive server factory, codecs, multipart, validation, and session resolver. Trace the three conditions first, then inspect the server factory, HTTP handler, and actual endpoints.

## Official Documentation

- Spring Boot 3.3.13 API — `WebFluxAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html
- Spring Boot 3.3.13 API — package `org.springframework.boot.autoconfigure.web.reactive`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/package-summary.html
- Spring Boot 3.3 — Reactive Web Applications and WebFlux auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration, candidate discovery, conditions, and ordering: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 API — `ReactiveWebServerFactoryAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveWebServerFactoryAutoConfiguration.html
- Spring Boot 3.3.13 API — `WebFluxRegistrations`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxRegistrations.html
- Spring Framework — WebFlux configuration and `@EnableWebFlux`: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
