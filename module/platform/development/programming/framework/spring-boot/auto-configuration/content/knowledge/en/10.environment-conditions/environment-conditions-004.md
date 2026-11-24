# Distinguishing Web Libraries on the Classpath from the Running ApplicationContext Type

## 1. Objectives and Core Question

In Spring Boot, these two statements are **not equivalent**:

1. “The application has Spring MVC, Spring WebFlux, or Servlet API libraries on the **classpath**.”
2. “The currently running `ApplicationContext` is a **web application context** using the Servlet or Reactive model.”

A CLI/batch application may bring in `spring-webmvc` and `spring-webflux` via transitive dependencies and still run with a **non-web** context. Conversely, a Spring MVC application may include the WebFlux library solely to use `WebClient`; that does not make conditions meant for a **reactive web server** match automatically.

Therefore, at least three layers must be distinguished:

- **Classpath**: which libraries/classes *can be loaded*? For example `DispatcherServlet`, `DispatcherHandler`, `jakarta.servlet.Servlet`.
- **Application type selection** (`WebApplicationType`): does Spring Boot intend to bootstrap a `NONE`, `SERVLET`, or `REACTIVE` application? This is a bootstrap-time decision, inferred by default from the classpath but configurable.
- **The actual `ApplicationContext` evaluating the condition**: does the current context/environment carry Servlet/Reactive web characteristics? `@ConditionalOnWebApplication` checks this layer; a context created by a test runner or custom code does not necessarily follow `SpringApplication`'s default inference.

After this lesson, you will know when to choose `@ConditionalOnClass`, `@ConditionalOnWebApplication`, or a combination of both; predict what happens when both MVC and WebFlux are present; distinguish a non-web application from a web server with no open port; and build a test reproducing all three context types. Technical scope: Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x.

## 2. What Does the Classpath Tell You and What Doesn't It?

The classpath is the set of paths/JARs that the classloader can look up. If the `spring-webmvc` dependency is present, `org.springframework.web.servlet.DispatcherServlet` can usually be loaded; if `spring-webflux` is present, `org.springframework.web.reactive.DispatcherHandler` can usually be loaded.

`@ConditionalOnClass` only cares about **the presence of the specified classes**; `@ConditionalOnMissingClass` does the opposite. They **do not ask**:

- Whether `DispatcherServlet` is being used to handle HTTP requests.
- Whether a Servlet/Reactive `ApplicationContext` currently exists.
- Whether any web server has started or any TCP port is listening.
- Whether `DispatcherHandler` appears because of a WebFlux server or just because the client/reactive library was added as a dependency.

Example:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "org.springframework.web.servlet.DispatcherServlet")
class MvcLibraryAvailableConfiguration {
    // Evaluated when the DispatcherServlet class is present.
    // No proof yet that the application is running with a Servlet context.
}
```

In a **non-web** application that still depends on `spring-webmvc`, the configuration above can be activated. Similarly:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "org.springframework.web.reactive.DispatcherHandler")
class WebFluxLibraryAvailableConfiguration {
    // Classpath has WebFlux; does not mean runtime is REACTIVE.
}
```

Note on class conditions when writing optional libraries: Spring Boot reads annotation metadata (usually without needing to load the specified class) on `@Configuration`. However, if a `@Bean` has a **return type** that is an absent optional class, the JVM may have to resolve the method signature before the condition can block it. In that case, isolate the part using the optional class inside a **nested `@Configuration`** with `@ConditionalOnClass` at the class level; avoid relying on per-method conditions as a class-loading safety guarantee.

## 3. Intended Application Type to Launch: `WebApplicationType`

Spring Boot 3.3 has the enum `org.springframework.boot.WebApplicationType`:

| Value | Meaning when `SpringApplication` starts normally | Typical context |
| --- | --- | --- |
| `NONE` | The application does not run as a web application; no embedded HTTP server is created | `AnnotationConfigApplicationContext` |
| `SERVLET` | Servlet-based web application and, when run as an executable JAR with standard config, has a servlet web server | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | Reactive-based web application and, when fully configured, has a reactive web server | `AnnotationConfigReactiveWebServerApplicationContext` |

This is **Spring Boot's bootstrap choice**, not a check for “is a web JAR present” at arbitrary times. For a `SpringApplication` using default inference:

- Only the libraries required for Spring MVC → typically chooses `SERVLET`.
- WebFlux libraries present without MVC/Jersey indicators prioritized by Boot → typically chooses `REACTIVE`.
- Both `spring-boot-starter-web` and `spring-boot-starter-webflux` → by default **SERVLET / Spring MVC** is prioritized. Very common case: adding WebFlux to use `WebClient` in an MVC app.
- Missing required web application indicators → may choose `NONE`, even if the classpath still has a few isolated web components.

**Do not infer `SERVLET` merely from seeing `jakarta.servlet.Servlet`, and do not infer `REACTIVE` merely from seeing Reactor/`Mono`.** Boot checks specific indicator classes and the precedence rules of the version in use. The practical goal is knowing which context type will be created, rather than memorizing a single classpath condition and applying it across all versions.

### 3.1. Forcing a choice instead of letting Boot infer

In `application.properties`:

```properties
spring.main.web-application-type=none
```

or:

```properties
spring.main.web-application-type=reactive
```

or:

```properties
spring.main.web-application-type=servlet
```

Corresponding programmatic path:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
```

This is an **illustrative snippet**: assuming `MyApplication` and `args` already exist. Forcing the application type only changes **how startup/context is selected**; it does not automatically supply missing classes, beans, server factories, or libraries. If you force `REACTIVE` without dependencies supporting a reactive web server, the application may fail to start. With `NONE`, the classpath can still contain `DispatcherServlet` and `DispatcherHandler`.

You can set `spring.main.web-application-type=reactive` in `@SpringBootTest(properties = "...")` when you need to test WebFlux on a classpath that also has MVC. That is a decision about the application type during test context construction; do not confuse it with an arbitrary property that `@ConditionalOnWebApplication` reads to “guess” the result.

## 4. `@ConditionalOnWebApplication` Checks the Running Context

`org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication` and `@ConditionalOnNotWebApplication` are **conditions based on the nature of the context/environment**, fundamentally different from `@ConditionalOnClass`.

`@ConditionalOnWebApplication` accepts `type`:

- `Type.ANY` (default): matches Servlet **or** Reactive web applications.
- `Type.SERVLET`: matches only servlet web applications.
- `Type.REACTIVE`: matches only reactive web applications.

According to Spring Boot 3.3, **Servlet web application** detection may rely on `WebApplicationContext`, the `session` scope, or `ConfigurableWebEnvironment`; **Reactive web application** detection relies on `ReactiveWebApplicationContext` or `ConfigurableReactiveWebEnvironment`. Therefore, this condition should not be oversimplified as a single check `context instanceof SomeConcreteClass`. In typical Boot applications, those signals correspond to the three context types above.

Examples of typed configurations:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(type = Type.SERVLET)
class ServletRuntimeConfiguration {
    // Configured only when the current context has Servlet web characteristics.
}

@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(type = Type.REACTIVE)
class ReactiveRuntimeConfiguration {
    // Configured only when the current context has Reactive web characteristics.
}
```

Example for logic that only runs in a non-web application:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
class CommandLineRuntimeConfiguration {
    // Does not match in a web application context.
}
```

Key point: if `@ConditionalOnClass(DispatcherServlet.class)` is **true** while `@ConditionalOnWebApplication(type = SERVLET)` is **false**, that is a normal outcome when the MVC dependency is present but the context is not Servlet. Conversely, if WebFlux is on the classpath while the context is Servlet, `@ConditionalOnWebApplication(type = REACTIVE)` is still **false**.

### 4.1. Decision table: fixed classpath, varying context

Suppose both `DispatcherServlet` and `DispatcherHandler` are present on the **same classpath**; dependencies do not change across rows.

| Condition | Context NONE | Context SERVLET | Context REACTIVE |
| --- | :---: | :---: | :---: |
| `@ConditionalOnClass(DispatcherServlet.class)` | ✅ | ✅ | ✅ |
| `@ConditionalOnClass(DispatcherHandler.class)` | ✅ | ✅ | ✅ |
| `@ConditionalOnWebApplication` (ANY) | ❌ | ✅ | ✅ |
| `@ConditionalOnWebApplication(type=SERVLET)` | ❌ | ✅ | ❌ |
| `@ConditionalOnWebApplication(type=REACTIVE)` | ❌ | ❌ | ✅ |
| `@ConditionalOnNotWebApplication` | ✅ | ❌ | ❌ |

The table assumes each context is validly created and conditions are evaluated within that context. The first two rows **do not change with the context type** because the classpath is fixed; the remaining rows depend on runtime characteristics. This is why a single classpath is not enough to conclude which Servlet/Reactive configurations will be activated.

### 4.2. Having a web context does not mean an HTTP port is open

Distinguish two further layers of questions:

1. **Is the context a web context?** `@ConditionalOnWebApplication`.
2. **Is the server accepting HTTP connections on some port?** That is runtime network/server state, not the annotation's target.

In Spring Boot, `server.port=0` normally requests a random port for the embedded server (when a web server actually runs). Setting `server.port=-1` can disable HTTP endpoints while still creating a `WebApplicationContext`. `spring.main.web-application-type=none` causes the application to start as non-web. **Do not use `server.port` to simulate `WebApplicationType.NONE`.**

Web test context runners can also use a mock environment/servlet context to evaluate conditions **without opening any port**. That does not make them non-web contexts.

## 5. Real-World Scenarios Prone to Confusion

### 5.1. WebFlux used only as an HTTP client in an MVC app

A service already uses:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

`spring-boot-starter-webflux` may be added to use `WebClient`. Unless the application type is actively changed, Boot usually selects **SERVLET** because MVC is present. In that situation:

- `@ConditionalOnClass(DispatcherHandler.class)` can be **true** because the WebFlux library is present.
- `@ConditionalOnWebApplication(type = REACTIVE)` is **false** in a servlet context.
- `@ConditionalOnWebApplication(type = SERVLET)` is **true**.
- Having a `WebClient.Builder` bean or `Mono` does not prove the server is running Netty/WebFlux either.

A common mistake is using `@ConditionalOnClass(WebClient.class)` to enable a **reactive server filter**, `WebFilter`, or `HttpHandler` configuration. That condition is suitable for enabling a **client adapter** needing `WebClient`, whereas components integrating with the reactive web runtime should also carry the `Type.REACTIVE` condition.

### 5.2. Batch/CLI application carrying web dependencies

A data-processing application might pull in `spring-web` or `spring-webmvc` to reuse HTTP types or via transitive dependencies. When running with `WebApplicationType.NONE`, `@ConditionalOnClass(DispatcherServlet.class)` can still be true; `@ConditionalOnWebApplication` does not match. A classpath condition should not automatically create interceptors, Servlet filters, web controllers, or HTTP-runtime infrastructure.

### 5.3. Forcing REACTIVE even when Spring MVC is present

When configuring:

```properties
spring.main.web-application-type=reactive
```

and the classpath actually has enough to start a reactive server, Boot can run a reactive web context even though `DispatcherServlet` is still present. The classpath condition for MVC remains true, yet the Servlet web condition does not match. This is a good scenario to see that the classpath **does not disappear** when changing the application type.

### 5.4. Testing a library module independently

An auto-configuration module can be consumed in Servlet, Reactive, and non-web applications alike. Never assume “starter in POM” ⇒ every consumer runs the same context type. Mark each sub-configuration by *library capability* and *actual environment*. Results should only match where the feature makes sense.

### 5.5. Parent/child contexts or custom test contexts

In a multi-context setup, conditions are evaluated in the **context containing the configuration under evaluation**; do not infer every context's type solely from a parent or shared classpath. A test runner may create a Servlet web context in the JVM while another test creates a non-web context on the exact same classpath. When debugging, note clearly **which context is being inspected** and when the condition is evaluated.

## 6. Designing Auto-Configuration Properly: Checking Both Capability and Environment

When a bean is only useful if both the Servlet MVC library is available and it is running with a Servlet web context, combine the two conditions:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class DemoWebAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name =
            "org.springframework.web.servlet.DispatcherServlet")
    @ConditionalOnWebApplication(type = Type.SERVLET)
    static class ServletPart {

        @Bean
        ServletDiagnosticMarker servletDiagnosticMarker() {
            return new ServletDiagnosticMarker();
        }
    }

    public static final class ServletDiagnosticMarker {
    }
}
```

**This is an illustrative snippet about annotations**, not a complete standalone runnable application. Here the class-level conditions are **AND**: if the MVC class is absent, the nested configuration does not participate; if the context is not Servlet, the Servlet part is not enabled even if MVC is on the classpath.

The equivalent part for a WebFlux server would have the conditions:

```java
@ConditionalOnClass(name =
        "org.springframework.web.reactive.DispatcherHandler")
@ConditionalOnWebApplication(type =
        ConditionalOnWebApplication.Type.REACTIVE)
```

The two annotations in the block above are a **declaration fragment** to place on an appropriate `@Configuration` class. If the feature requires a specific bean, `@ConditionalOnBean` or `@ConditionalOnMissingBean` can be added, but do not use them as a substitute for asking what type of context is running.

For an auto-configuration published in a library, list its class name in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` per the Spring Boot 3.x contract; merely adding it as a dependency does not guarantee auto-importing without this registration mechanism. When a configuration has optional dependencies, use a nested configuration to isolate bean signatures with optional types so as to avoid unintended class-loading errors.

## 7. Practice: Same Classpath, Three Different Contexts

This lab intentionally leaves **both MVC and WebFlux present** in test dependencies, then varies the `ApplicationContext` type using three runners provided by Spring Boot:

- `ApplicationContextRunner`: creates a regular, non-web context.
- `WebApplicationContextRunner`: creates a servlet web context to test conditions, using a mock servlet context; no HTTP port needs to be opened.
- `ReactiveWebApplicationContextRunner`: creates a reactive web context to test conditions; no HTTP port needs to be opened.

This tests the condition mechanism. It **does not test the default `WebApplicationType` selection algorithm of a full `SpringApplication`**; the three runners explicitly create three separate context types. To verify bootstrap inference when both starters are present, see section 8.

### 7.1. Prepare a standalone test project

Structure:

```text
web-context-conditions/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/WebContextConditionTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'web-context-conditions'
```

`build.gradle` (select the same Spring Boot 3.3.13 version for all starters):

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-web:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

JDK 17+ and a Gradle version compatible with Spring Boot 3.3 are required to run. When a Gradle Wrapper is available, use the project's wrapper; the test code does not depend on Docker or a database.

### 7.2. Full JUnit 5 test

Create `src/test/java/demo/WebContextConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class WebContextConditionTest {

    // Distinct markers to assert which condition types matched.
    record MvcLibraryMarker() {}
    record AnyWebMarker() {}
    record ServletMarker() {}
    record ReactiveMarker() {}
    record NonWebMarker() {}

    @AutoConfiguration
    static class ProbeAutoConfiguration {

        @Bean
        @ConditionalOnClass(name =
                "org.springframework.web.servlet.DispatcherServlet")
        MvcLibraryMarker mvcLibraryMarker() {
            return new MvcLibraryMarker();
        }

        @Bean
        @ConditionalOnWebApplication
        AnyWebMarker anyWebMarker() {
            return new AnyWebMarker();
        }

        @Bean
        @ConditionalOnWebApplication(type = Type.SERVLET)
        ServletMarker servletMarker() {
            return new ServletMarker();
        }

        @Bean
        @ConditionalOnWebApplication(type = Type.REACTIVE)
        ReactiveMarker reactiveMarker() {
            return new ReactiveMarker();
        }

        @Bean
        @ConditionalOnNotWebApplication
        NonWebMarker nonWebMarker() {
            return new NonWebMarker();
        }
    }

    @Test
    void ordinaryContextStillSeesMvcLibraryOnClasspath() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ProbeAutoConfiguration.class))
                .run(ctx -> {
                    assertThat(ctx).hasSingleBean(MvcLibraryMarker.class);
                    assertThat(ctx).hasSingleBean(NonWebMarker.class);
                    assertThat(ctx).doesNotHaveBean(AnyWebMarker.class);
                    assertThat(ctx).doesNotHaveBean(ServletMarker.class);
                    assertThat(ctx).doesNotHaveBean(ReactiveMarker.class);
                });
    }

    @Test
    void servletContextMatchesServletButNotReactiveCondition() {
        new WebApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ProbeAutoConfiguration.class))
                .run(ctx -> {
                    assertThat(ctx).hasSingleBean(MvcLibraryMarker.class);
                    assertThat(ctx).hasSingleBean(AnyWebMarker.class);
                    assertThat(ctx).hasSingleBean(ServletMarker.class);
                    assertThat(ctx).doesNotHaveBean(ReactiveMarker.class);
                    assertThat(ctx).doesNotHaveBean(NonWebMarker.class);
                });
    }

    @Test
    void reactiveContextStillSeesMvcLibraryButIsNotServlet() {
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ProbeAutoConfiguration.class))
                .run(ctx -> {
                    assertThat(ctx).hasSingleBean(MvcLibraryMarker.class);
                    assertThat(ctx).hasSingleBean(AnyWebMarker.class);
                    assertThat(ctx).hasSingleBean(ReactiveMarker.class);
                    assertThat(ctx).doesNotHaveBean(ServletMarker.class);
                    assertThat(ctx).doesNotHaveBean(NonWebMarker.class);
                });
    }
}
```

Run:

```bash
gradle test --tests demo.WebContextConditionTest
```

If using Gradle Wrapper:

```bash
./gradlew test --tests demo.WebContextConditionTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.WebContextConditionTest
```

**Expected result:** the `test` task succeeds with 3 tests passed. No fixed stdout is listed because Gradle log lines depend on version and configuration. On the same classpath, `MvcLibraryMarker` appears in **all three** contexts, whereas `ServletMarker`/`ReactiveMarker`/`NonWebMarker` appear only in their corresponding context.

| Runner | `MvcLibraryMarker` | `AnyWebMarker` | `ServletMarker` | `ReactiveMarker` | `NonWebMarker` |
| --- | :---: | :---: | :---: | :---: | :---: |
| `ApplicationContextRunner` | ✓ | – | – | – | ✓ |
| `WebApplicationContextRunner` | ✓ | ✓ | ✓ | – | – |
| `ReactiveWebApplicationContextRunner` | ✓ | ✓ | – | ✓ | – |

Each test creates an isolated context so there is no interference from leftover beans in other tests. An interesting point in the third test: even though Servlet MVC classes **are still present**, the condition dedicated to a Servlet context **does not match**.

### 7.3. Interpreting common errors in tests

- If you try to test the reactive case with `ApplicationContextRunner` and only add `.withPropertyValues("spring.main.web-application-type=reactive")`, do not expect the runner to switch to a reactive context. **The runner has already chosen its own context factory**; that property is environment data and does not recreate the runner's context type.
- If `@ConditionalOnClass` does not match, verify whether the dependency is actually on the **test runtime classpath**. A dependency declared in another configuration does not necessarily enter the test runtime.
- If you add all web server auto-configurations from multiple starters into the test, unnecessary bean/server infrastructure may be triggered. The test above only imports `ProbeAutoConfiguration` to isolate the condition results.
- If a test uses `@SpringBootTest` instead of a runner, explicitly define `webEnvironment` and `spring.main.web-application-type`. The test context type then also depends on Boot Test configuration and classpath.

## 8. Further Distinction: Context Type Selection When Starting a Full SpringApplication

The test in section 7 **deliberately selects the context type**. For a real Boot application, you must look at `SpringApplication`'s choice. The following application snippet illustrates printing the runtime context using `ApplicationRunner`; it must be placed in a Boot project with a main class and appropriate dependencies.

```java
package demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebTypeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebTypeApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectContext(ApplicationContext context) {
        return args -> System.out.println(
                "Context: " + context.getClass().getName());
    }
}
```

Assuming the project has both web starters and the main class above, the **observable steps** are:

1. Without `spring.main.web-application-type`: Boot defaults to Servlet because both MVC and WebFlux are present. The `Context: ...` line indicates the actual concrete context; the application may open an embedded servlet server if fully configured.
2. Run with `--spring.main.web-application-type=none`: the context takes the non-web type; the classpath does not lose MVC/WebFlux libraries, yet `Type.SERVLET`/`Type.REACTIVE` conditions do not match in this context.
3. Run with `--spring.main.web-application-type=reactive`: with appropriate dependencies and server, Boot uses a reactive web context, even though MVC classes can still be loaded.

Do not hardcode a single stdout line with an absolute class name across all configurations/test modes: the concrete context class name can vary depending on bootstrap, application context factory, custom configuration, or version. What matters is that Servlet/Reactive/non-web characteristics are reflected at runtime.

The difference between **inference** and **forcing** is important: when changing the property from default to `reactive`, you changed the bootstrap choice itself; you did not “remove `DispatcherServlet` from the classpath”. Therefore, class conditions and web conditions can be separated predictably.

### 8.1. Dependencies are an input to inference, not context state

Diagram:

```text
Dependencies / Classpath
  ├── DispatcherServlet present?
  ├── DispatcherHandler present?
  └── Other web indicator classes?
                |
                v
 SpringApplication selects WebApplicationType
     (inferred or explicitly configured)
                |
                v
  ApplicationContext is created & refreshed
                |
                +--> NONE      -> non-web environment/context
                +--> SERVLET   -> Servlet web environment/context
                +--> REACTIVE  -> Reactive web environment/context
                |
                v
OnClassCondition asks: is the class present?
OnWebApplicationCondition asks: what type of web context/environment is it?
                |
                v
Register or skip configuration / bean
```

Note in custom tests/bootstraps: another framework or custom code can create the context directly, bypassing `SpringApplication`'s default inference step. Therefore, the **current context** is the proper evidence for `@ConditionalOnWebApplication`.

## 9. Debugging Unexpected Condition Decisions

Move from symptoms to testable questions:

1. **Identify which condition is failing.** `@ConditionalOnClass` checks classes, `@ConditionalOnWebApplication` checks the context, `@ConditionalOnBean` checks beans. A configuration can be blocked by multiple conditions, so do not blame everything on web type.
2. **Verify class names on the classpath.** Check `DispatcherServlet`, `DispatcherHandler`, or the class matching the actual condition. Being in the build file is not enough; it must be on the runtime classpath. Use `./gradlew dependencies --configuration runtimeClasspath` to trace transitive dependencies (in projects with a wrapper).
3. **Verify the active context type.** Print `ApplicationContext#getClass()`, check the corresponding web interface, and record the actual environment. A generic context in a test can be non-web even when web JARs are present.
4. **Check bootstrap mode.** Is there `spring.main.web-application-type`, `SpringApplication#setWebApplicationType`, a custom `ApplicationContextFactory`, `@SpringBootTest(webEnvironment=...)`, a specific runner, or a parent/child context? The `server.port` property does not determine the web type.
5. **Check the MVC/WebFlux pair.** Both starters present together usually yield Servlet by default. If you want a reactive server, you must explicitly choose `REACTIVE` and have sufficient server dependencies.
6. **Read the Conditions Evaluation Report.** When using Boot, enable `--debug` or `debug=true` to view positive/negative matches in the logs. Look for the configuration name, `OnClassCondition`, and `OnWebApplicationCondition` sections to see **which conditions matched and which did not**. If Actuator is configured and the endpoint is exposed, `/actuator/conditions` also displays the matches.
7. **Write a small test with the three runners.** Keep dependencies unchanged, varying only the context. Then vary the classpath with `FilteredClassLoader` if you need to verify class conditions; avoid changing classpath, web type, and configuration simultaneously, which makes root-cause tracing hard.

Useful diagnostic questions when reading the report:

- “Did the condition fail because `DispatcherServlet` is missing, or because there is no Servlet web application?”
- “Is the app currently running `SERVLET` even though `DispatcherHandler` can still be loaded?”
- “What context type does this test initialize, and am I confusing a runner with a real `SpringApplication`?”
- “Is the feature a **web client**, **Servlet server**, **Reactive server**, or **common non-web service**?” Choose annotations to match the actual purpose.

## 10. Common Design Mistakes

| Symptom | Misunderstanding | Adjustment |
| --- | --- | --- |
| MVC bean created in non-web process | `spring-webmvc` is present so it must be a Servlet app | Add `@ConditionalOnWebApplication(type=SERVLET)` if the bean is tied to the Servlet runtime |
| Reactive server bean created in MVC app with `WebClient` | WebFlux is on the classpath so it must be running REACTIVE | Only enable reactive server features when `Type.REACTIVE` matches |
| Bean does not appear even though library is present | Only looking at `@ConditionalOnClass`, ignoring other web conditions | Check the condition report and `ApplicationContext` type |
| Still runs MVC after adding `spring-boot-starter-webflux` | Thinking Boot prioritizes WebFlux or picks randomly | MVC is prioritized when both are present; for reactive, configure `web-application-type=reactive` |
| Set `server.port=-1` expecting `@ConditionalOnNotWebApplication` | Not opening a port means non-web | `server.port` and web context nature are two separate questions |
| Set `spring.main.web-application-type=reactive` in `ApplicationContextRunner` expecting reactive condition to match | Property automatically switches the runner's context factory | Use `ReactiveWebApplicationContextRunner` or real Boot bootstrapping |
| Checking an optional class on a method whose return type depends on that class | `@ConditionalOnClass` always prevents the JVM from loading the signature | Isolate into a nested configuration guarded at the class level |
| Using `@ConditionalOnWebApplication` as a check for an open HTTP port | Having a web context means a port is listening | Check server runtime separately; conditions do not probe sockets |

## 11. Pre-Release Checklist for Auto-Configuration

- If a feature needs an API in an optional JAR: use `@ConditionalOnClass` with the proper representative class.
- If a feature is only valid when requests are handled via Servlet/MVC: add `@ConditionalOnWebApplication(type=SERVLET)`.
- If a feature is only valid with a reactive web server: add `@ConditionalOnWebApplication(type=REACTIVE)`.
- If a feature works across both Servlet and Reactive web: `Type.ANY` may fit, while not auto-enabling the feature in a non-web context.
- If a feature serves only batch/CLI: use `@ConditionalOnNotWebApplication` when that is a genuine requirement, rather than relying on web classes being absent.
- If the classpath has both MVC and WebFlux, test both the default **SERVLET** case and the **REACTIVE** override.
- Write tests for at least `NONE`, `SERVLET`, and `REACTIVE` on the **same classpath**; add a missing-dependency test if the feature has optional classes.
- Distinguish **condition outcome**, **context type**, and **whether the server opened a port** in logs/tests; they are three different pieces of evidence.
- When a module provides auto-configuration, remember to register it in `AutoConfiguration.imports` and avoid letting the class only be component-scanned like a user configuration.

**Takeaway:** `@ConditionalOnClass` answers “is the library class present?”; `@ConditionalOnWebApplication` answers “is the context being configured a Servlet/Reactive web context?”. `WebApplicationType` expresses the bootstrap selection. The exact same classpath can lead to different contexts, and a Servlet context can still contain every WebFlux class. Proper condition design requires checking **both available dependencies and the actual runtime context** when a feature needs both.

## Official References

- Spring Boot 3.3, **Creating Your Own Auto-configuration**, Class Conditions, Web Application Conditions, and Simulating a Web Context sections: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, **Reactive Web Applications**, note on Spring MVC priority when both starters are present: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3, **Testing Spring Boot Applications**, Detecting Web Application Type section: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3, **Embedded Web Servers**, `spring.main.web-application-type=none` and `server.port=-1` configurations: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 API, `WebApplicationType`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3 API, `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
