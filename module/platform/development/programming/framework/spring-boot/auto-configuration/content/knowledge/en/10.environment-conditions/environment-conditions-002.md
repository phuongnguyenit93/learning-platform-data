# `@ConditionalOnWebApplication` with `ANY`, `SERVLET`, and `REACTIVE`

In **Spring Boot Auto Configuration**, many default configurations only make sense when the application actually runs in a **web environment**. A Servlet `Filter`, a WebFlux `WebFilter`, or a bean shared between both branches should not be arbitrarily registered into a command-line application. Spring Boot provides `@ConditionalOnWebApplication` to describe this condition accurately.

This article explains the three values `ANY`, `SERVLET`, and `REACTIVE`, how Spring Boot detects the environment, the case where a project has both Spring MVC and WebFlux, how to place the annotation in auto-configuration, and a reproducible Java 17/Spring Boot 3.x test suite.

## 1. Syntax and Meaning

`@ConditionalOnWebApplication` belongs to the package:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
```

The annotation has a `type` attribute of type `ConditionalOnWebApplication.Type`; **the default value is `ANY`**.

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;

// Matches both Servlet and Reactive web applications:
@ConditionalOnWebApplication
class AnyWebConfiguration {
}

// Equivalent to default, written explicitly:
@ConditionalOnWebApplication(type = Type.ANY)
class ExplicitAnyWebConfiguration {
}

// Only when the application uses the Servlet web stack:
@ConditionalOnWebApplication(type = Type.SERVLET)
class ServletWebConfiguration {
}

// Only when the application uses the Reactive web stack:
@ConditionalOnWebApplication(type = Type.REACTIVE)
class ReactiveWebConfiguration {
}
```

The classes above are **syntax illustration snippets**, not auto-configuration classes loaded automatically by Boot; a standalone runnable example is in section 4.

| `type` | When does it match? | Commonly used for |
| --- | --- | --- |
| `Type.ANY` | **Servlet or Reactive** web application. | Web-supporting beans not tied to a single stack, such as general web app policies. |
| `Type.SERVLET` | **Servlet**-based web application. | Configuring `jakarta.servlet.Filter`, Spring MVC `HandlerInterceptor`, `ServletRegistrationBean`. |
| `Type.REACTIVE` | **Reactive**-based web application. | Configuring `org.springframework.web.server.WebFilter`, `WebFluxConfigurer`, WebFlux infrastructure. |

In a **non-web application**, none of the three match. `ANY` means “**either web type**”, **not** requiring both Servlet and Reactive simultaneously. `SERVLET` and `REACTIVE` check the **web application context** type; they do not indicate whether business methods use `Mono`/`Flux`, `CompletableFuture`, or asynchronous HTTP calls.

## 2. How Does Spring Boot Evaluate the Condition?

This annotation is a Spring Boot condition checked when the framework processes configurations and registers bean definitions. It uses **application/context environment** information and the presence of required web classes to detect the web application type. Therefore, merely having Servlet/WebFlux libraries in `pom.xml` is **not enough** to conclude the condition will match: a regular `ApplicationContext` can still be **non-web**.

For a web application started by `SpringApplication`, Spring Boot selects one dominant `WebApplicationType`:

- `WebApplicationType.SERVLET`: uses a Servlet stack web context, typically a Spring MVC application.
- `WebApplicationType.REACTIVE`: uses a Reactive stack web context, typically a Spring WebFlux application.
- `WebApplicationType.NONE`: non-web context.

**Name distinction:** `WebApplicationType` is the enum used to bootstrap the application, whereas `ConditionalOnWebApplication.Type` is the enum used to describe the configuration activation condition. They relate to the same environment kinds but **are not the same Java type** and cannot be interchanged in the annotation.

Expected matrix given an appropriate context and the required web classes available:

| Actual environment | `ANY` | `SERVLET` | `REACTIVE` |
| --- | :---: | :---: | :---: |
| Non-web (`NONE`) | No | No | No |
| Web Servlet (`SERVLET`) | Yes | Yes | No |
| Web Reactive (`REACTIVE`) | Yes | No | Yes |

When an annotation applies to an **entire configuration class**, the beans inside that class are only evaluated when the class condition matches. When placed on a **`@Bean` method**, it only controls the bean definition of that corresponding method.

```java
// Illustrative snippet: shared configuration with two independent branches.
@AutoConfiguration
public class MyWebAutoConfiguration {

    @Bean
    @ConditionalOnWebApplication(type = Type.SERVLET)
    ServletSupport servletSupport() {
        return new ServletSupport();
    }

    @Bean
    @ConditionalOnWebApplication(type = Type.REACTIVE)
    ReactiveSupport reactiveSupport() {
        return new ReactiveSupport();
    }
}
```

Here `ServletSupport` and `ReactiveSupport` are hypothetical project classes; the snippet illustrates annotation placement and is not a standalone compilable program.

## 3. Common Confusion: Having Both Spring MVC and WebFlux

Two popular starters:

- `spring-boot-starter-web`: used for Spring MVC/Servlet applications.
- `spring-boot-starter-webflux`: used for Spring WebFlux/Reactive applications; also provides `WebClient`, which is often added to MVC projects just for asynchronous HTTP calls.

If **both starters** are on the classpath together, Spring Boot **defaults to prioritizing MVC/Servlet** when auto-detecting the application type. Consequently:

1. `@ConditionalOnWebApplication(type = SERVLET)` usually matches.
2. `@ConditionalOnWebApplication(type = REACTIVE)` usually **does not** match.
3. `@ConditionalOnWebApplication` or `type = ANY` matches because the application is still a web app.

This **does not contradict** the WebFlux library being present. **Having WebFlux on the classpath does not mean running a Reactive web server.** An MVC application can still use `WebClient`.

When you want a real Boot application to use Reactive even when both starters are present, you must **explicitly select the application type**:

```properties
# src/main/resources/application.properties
spring.main.web-application-type=reactive
```

Or when bootstrapping manually:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

SpringApplication application = new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

The second snippet is an **excerpt inside a `main(String[] args)` method**; `MyApplication` and `args` must be defined in the actual application.

Similarly, to **disable the web environment** when an application has web dependencies but only runs background tasks:

```properties
spring.main.web-application-type=none
```

In that case, `ANY`/`SERVLET`/`REACTIVE` conditions should not be assumed to match just because the classpath still contains web libraries.

Specific note for testing: `WebApplicationContextRunner` and `ReactiveWebApplicationContextRunner` (section 4) directly create a **context of the type to be tested**. They help test each branch in isolation; do not assume that adding `spring.main.web-application-type` to a standard `ApplicationContextRunner` will automatically change that runner's context type.

## 4. Runnable Test Example with Java 17 and Spring Boot 3.x

The example uses three simple **auto-configurations**, each creating a single marker bean if the environment matches. Three context runners verify three scenarios: non-web, Servlet, and Reactive.

### 4.1. Project structure

```text
web-condition-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ConditionalOnWebApplicationTest.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>web-condition-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Both `starter-web` and `starter-webflux` are included **so the test suite has the full classes of both stacks**. The three runners still create three different contexts, so the result does not depend on Boot defaulting to MVC for a full application having both starters.

### 4.2. Complete test code

Create `src/test/java/demo/ConditionalOnWebApplicationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication.Type;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalOnWebApplicationTest {

    record Marker(String source) {
    }

    @AutoConfiguration
    @ConditionalOnWebApplication
    static class AnyWebAutoConfiguration {

        @Bean
        Marker anyWebMarker() {
            return new Marker("any");
        }
    }

    @AutoConfiguration
    @ConditionalOnWebApplication(type = Type.SERVLET)
    static class ServletAutoConfiguration {

        @Bean
        Marker servletMarker() {
            return new Marker("servlet");
        }
    }

    @AutoConfiguration
    @ConditionalOnWebApplication(type = Type.REACTIVE)
    static class ReactiveAutoConfiguration {

        @Bean
        Marker reactiveMarker() {
            return new Marker("reactive");
        }
    }

    private final AutoConfigurations configurations = AutoConfigurations.of(
            AnyWebAutoConfiguration.class,
            ServletAutoConfiguration.class,
            ReactiveAutoConfiguration.class
    );

    @Test
    void nonWebContextMatchesNone() {
        new ApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context -> {
                    assertThat(context.containsBean("anyWebMarker")).isFalse();
                    assertThat(context.containsBean("servletMarker")).isFalse();
                    assertThat(context.containsBean("reactiveMarker")).isFalse();
                });
    }

    @Test
    void servletContextMatchesAnyAndServlet() {
        new WebApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context -> {
                    assertThat(context.containsBean("anyWebMarker")).isTrue();
                    assertThat(context.containsBean("servletMarker")).isTrue();
                    assertThat(context.containsBean("reactiveMarker")).isFalse();
                    assertThat(context.getBean(
                            "servletMarker", Marker.class).source())
                            .isEqualTo("servlet");
                });
    }

    @Test
    void reactiveContextMatchesAnyAndReactive() {
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context -> {
                    assertThat(context.containsBean("anyWebMarker")).isTrue();
                    assertThat(context.containsBean("servletMarker")).isFalse();
                    assertThat(context.containsBean("reactiveMarker")).isTrue();
                    assertThat(context.getBean(
                            "reactiveMarker", Marker.class).source())
                            .isEqualTo("reactive");
                });
    }
}
```

`record Marker` is valid Java 17 syntax. The nested auto-configurations in the test are passed **directly** via `AutoConfigurations.of(…)`, so this test example **does not need** an `AutoConfiguration.imports` file.

Run from the `web-condition-demo` directory (requires Java 17 and Maven on the machine):

```bash
mvn test
```

**Expected result:** all three tests `nonWebContextMatchesNone`, `servletContextMatchesAnyAndServlet`, and `reactiveContextMatchesAnyAndReactive` pass. The command generates a Surefire report; no fixed stdout line is asserted because Maven log formatting depends on configuration and version.

| Test | `anyWebMarker` | `servletMarker` | `reactiveMarker` |
| --- | :---: | :---: | :---: |
| `nonWebContextMatchesNone` | ✗ | ✗ | ✗ |
| `servletContextMatchesAnyAndServlet` | ✓ | ✓ | ✗ |
| `reactiveContextMatchesAnyAndReactive` | ✓ | ✗ | ✓ |

Explanation of each test:

- `ApplicationContextRunner` creates a generic context; even though dependencies include both web starters, this context is not a Servlet/Reactive web context, so **none of the three conditions match**.
- `WebApplicationContextRunner` simulates a Servlet web context; `ANY` and `SERVLET` match, while `REACTIVE` does not.
- `ReactiveWebApplicationContextRunner` simulates a Reactive web context; `ANY` and `REACTIVE` match, while `SERVLET` does not.
- Having **two beans of type `Marker`** in each web branch of the test is intentional: the example only demonstrates **environment conditions**, without using `@ConditionalOnMissingBean`. The beans have **distinct names**, so there is no name collision error; they are retrieved by name to avoid ambiguity with type-based injection when multiple beans of the same type exist.

### 4.3. In a real starter

A library can separate configurations by technology:

```java
// Architectural snippet, not a standalone Java file:
@AutoConfiguration
@ConditionalOnWebApplication(type = Type.SERVLET)
class ServletTracingAutoConfiguration {
    // Beans using jakarta.servlet.Filter or Spring MVC.
}

@AutoConfiguration
@ConditionalOnWebApplication(type = Type.REACTIVE)
class ReactiveTracingAutoConfiguration {
    // Beans using org.springframework.web.server.WebFilter.
}

@AutoConfiguration
@ConditionalOnWebApplication
class CommonWebTracingAutoConfiguration {
    // Shared web beans if truly supporting both environments.
}
```

In Spring Boot 3.x, register the library's auto-configuration classes in the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resource, each line containing a **fully qualified class name**. This is the loading mechanism for a real starter's auto-configuration; do not ask users to `@ComponentScan` auto-config classes like regular application configurations.

If a bean needs additional conditions, they can be combined:

```java
@Bean
@ConditionalOnWebApplication(type = Type.REACTIVE)
@ConditionalOnClass(name = "org.springframework.web.reactive.DispatcherHandler")
@ConditionalOnMissingBean(MyReactiveHandler.class)
MyReactiveHandler myReactiveHandler() {
    return new MyReactiveHandler();
}
```

This example **assumes** `MyReactiveHandler` is a library-defined class with a no-arg constructor. `@ConditionalOnClass` checks the dependency, `@ConditionalOnWebApplication` checks the web environment, and `@ConditionalOnMissingBean` allows a custom application bean to override the default. On `@Bean` methods, be especially careful when the method signature references a class that may **not exist**; for checking an optional classpath, it is usually better to separate a nested configuration class with the condition at the **class level**.

## 5. Choosing `ANY`, `SERVLET`, or `REACTIVE` Based on Requirements

Choose `ANY` when the bean genuinely works in **both** web stacks and does not directly depend on Servlet API/Reactive API. For example, general web application metadata configuration, as long as the implementation does not assume `HttpServletRequest` or `ServerWebExchange`.

Choose `SERVLET` when the bean uses a Servlet/Spring MVC contract, such as `jakarta.servlet.Filter`, `HandlerInterceptor`, or `ServletRegistrationBean`. A Servlet filter cannot automatically act as a WebFlux `WebFilter`.

Choose `REACTIVE` when the bean uses a WebFlux contract, such as `WebFilter`, `WebFluxConfigurer`, or a pipeline working with `ServerWebExchange`. Do not use `ANY` just because both frameworks have “web” in their names; the concrete bean type must still be compatible with the selected runtime stack.

**If two implementations are needed** for the same feature, separate into two auto-configurations and use distinct conditions. If adding `@ConditionalOnMissingBean` so applications can override the configuration, define a **common contract type** clearly and pay attention to ordering relationships between auto-configurations when they can both register a default.

## 6. Diagnosing Unmatched Conditions

When a bean does not appear, check in order:

1. **Context type:** Is the actual application running with `WebApplicationType.NONE`, `SERVLET`, or `REACTIVE`? Is `spring.main.web-application-type` configured?
2. **Classpath:** Are the necessary servlet/webflux APIs present? If running `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`, are the dependencies sufficient to create the corresponding context type?
3. **Annotation:** Is `@ConditionalOnWebApplication` using the default `ANY` or explicitly `type = SERVLET/REACTIVE`? Is the annotation placed on the class or only on the `@Bean` method?
4. **Loading mechanism:** Is the library's auto-configuration listed in `AutoConfiguration.imports`? Is it excluded by another configuration?
5. **Other conditions:** Are `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, or `@ConditionalOnProperty` also applied and preventing the bean from being registered?
6. **Condition report:** Enable debug when running the application using the `--debug` argument to view the Condition Evaluation Report; when Actuator is enabled and accessible, the `/actuator/conditions` endpoint also helps analyze results.
7. **Reproducible test:** Use the three context runners as in section 4 to isolate environment condition issues from issues caused by other auto-configurations.

Common misconceptions:

| Misconception | Correct understanding |
| --- | --- |
| “Having the `spring-webflux` dependency means `REACTIVE` definitely matches.” | WebFlux may be added just to use `WebClient` in an MVC app; the context determines the condition branch. |
| “`ANY` will create two beans when both starters are present.” | `ANY` is just a condition; the number of beans depends on the registered methods/configurations. |
| “`SERVLET` means code is not allowed to run asynchronously.” | The Servlet web stack still supports many ways of asynchronous processing. |
| “`REACTIVE` means every bean runs on Netty.” | The condition refers to the web context type; the Reactive stack can have other runtime choices and does not lock into a single specific server. |
| “Adding `@ConditionalOnWebApplication` turns an app into a web app.” | The annotation **checks** the environment; it does not change `WebApplicationType` or start a server itself. |
| “`spring.main.web-application-type=reactive` turns the default `ApplicationContextRunner` into a reactive context.” | When testing web context conditions, choose `ReactiveWebApplicationContextRunner`. |

## 7. Self-Check

**Q1:** An application using only `spring-boot-starter-web` is running Spring MVC. Which conditions match?  
**Answer:** `ANY` and `SERVLET`.

**Q2:** An application uses `spring-boot-starter-webflux` as a Reactive web server. Which conditions match?  
**Answer:** `ANY` and `REACTIVE`.

**Q3:** An application has both starters and **does not force the web type**. Can `REACTIVE` be assumed to match because WebFlux classes exist?  
**Answer:** No. Spring Boot defaults to prioritizing MVC/Servlet when both stacks are present.

**Q4:** A command-line application runs with `spring.main.web-application-type=none` while still having web starters. Does `ANY` match?  
**Answer:** No, because the runtime environment is non-web.

**Q5:** If a starter wants to provide a `Filter` for MVC and a `WebFilter` for WebFlux, should it use one `ANY` configuration for both beans?  
**Answer:** No. Split into `SERVLET` and `REACTIVE` branches or place separate conditions on each `@Bean` method.

**Takeaway:** `@ConditionalOnWebApplication` checks the **actual web environment of the application** when registering configurations: `ANY` accepts both web types; `SERVLET` accepts only Servlet; `REACTIVE` accepts only Reactive. Test all three with the appropriate context runners and do not confuse **libraries on the classpath** with the **running web context type**.

### Official Documentation

- Spring Boot API — `@ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
- Spring Boot API — `ConditionalOnWebApplication.Type`: https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.Type.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html