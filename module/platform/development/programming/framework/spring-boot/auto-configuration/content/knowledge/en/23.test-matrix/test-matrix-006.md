# WebApplicationContextRunner and ReactiveWebApplicationContextRunner

## 1. Why are separate runners needed for web applications?

When testing auto-configuration, the ApplicationContext type can determine which conditions match. For example:

~~~java
@ConditionalOnWebApplication(type = Type.SERVLET)
~~~

matches only inside a servlet web application context. A test using the default `ApplicationContextRunner` creates an `AnnotationConfigApplicationContext`, which is a non-web context. Therefore, the servlet condition will not match, even if the test class has Spring MVC dependencies on the classpath.

Spring Boot provides two specialized runners:

- **`WebApplicationContextRunner`**: runs a servlet-based `ConfigurableWebApplicationContext`.
- **`ReactiveWebApplicationContextRunner`**: runs a `ConfigurableReactiveWebApplicationContext`.

Both inherit the machinery of `AbstractApplicationContextRunner`: configuring the context, adding properties, registering beans, loading auto-configuration, swapping the classloader, and running assertion callbacks. The main difference is the type of web context created.

This article uses **Java 17 and Spring Boot 3.3.13** as its illustrative baseline. If your project runs a different release, check the Javadoc of that exact version; newer API overloads may appear only in later releases.

## 2. Distinguishing the three types of context runners

| Runner | Underlying context | Use when |
| --- | --- | --- |
| `ApplicationContextRunner` | `AnnotationConfigApplicationContext` | Configuration does not depend on web |
| `WebApplicationContextRunner` | `AnnotationConfigServletWebApplicationContext` with `MockServletContext` | Auto-configuration targets Servlet/Spring MVC |
| `ReactiveWebApplicationContextRunner` | `AnnotationConfigReactiveWebApplicationContext` | Auto-configuration targets Spring WebFlux |

### 2.1. ApplicationContextRunner

The standard runner:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyAutoConfiguration.class));
~~~

It is suited for properties, services, repository abstractions, default beans, and conditions independent of web.

If the class under test has:

~~~java
@ConditionalOnWebApplication
~~~

using the regular runner can cause the auto-configuration to be skipped because the context is not a web context. This is not a runner bug; the test is creating a different context type than the code's condition expects.

### 2.2. WebApplicationContextRunner

The default constructor creates an `AnnotationConfigServletWebApplicationContext` and attaches a `MockServletContext`. This lets conditions recognize a servlet web context without starting Tomcat, Jetty, or Undertow.

~~~java
private final WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner();
~~~

The callback receives `AssertableWebApplicationContext`, allowing you to inspect beans and access the servlet context.

### 2.3. ReactiveWebApplicationContextRunner

The default constructor creates an `AnnotationConfigReactiveWebApplicationContext`. This context is recognized as a reactive web application context, so it fits `@ConditionalOnWebApplication(type = Type.REACTIVE)`.

~~~java
private final ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner();
~~~

The callback receives `AssertableReactiveWebApplicationContext`.

**Remember:** both runners simulate the appropriate web ApplicationContext type to test beans and conditions. They do not start a real embedded web server. For testing HTTP endpoints or server lifecycle, MockMvc, WebTestClient, or `@SpringBootTest(webEnvironment = RANDOM_PORT)` is more appropriate.

## 3. When to choose servlet, reactive, or non-web?

Choose the runner based on the condition the code under test uses, not based on the test name or whether dependencies happen to be present.

| Auto-configuration condition | Suitable runner |
| --- | --- |
| `@ConditionalOnWebApplication(type = SERVLET)` | `WebApplicationContextRunner` |
| `@ConditionalOnWebApplication(type = REACTIVE)` | `ReactiveWebApplicationContextRunner` |
| `@ConditionalOnWebApplication(type = ANY)` | One or both web runners, depending on the branches to test |
| `@ConditionalOnWebApplication` without specifying type | Usually test both servlet and reactive |
| No web condition | `ApplicationContextRunner` |
| `@ConditionalOnNotWebApplication` | `ApplicationContextRunner` |

An auto-configuration can combine multiple conditions:

~~~java
@ConditionalOnWebApplication(type = Type.SERVLET)
@ConditionalOnClass(DispatcherServlet.class)
@ConditionalOnProperty(prefix = "acme.web", name = "enabled", havingValue = "true")
~~~

When testing, you must create the right servlet context, have the required class on the classpath, and supply the property enabling the feature. If any one of those conditions is missing, the bean will not be registered.

## 4. Common methods inherited by both runners

Both web runners share most of the `AbstractApplicationContextRunner` API:

| API | Purpose |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Loads the auto-configurations under test |
| `withUserConfiguration(...)` | Adds configuration provided by the application |
| `withBean(...)` | Registers a test bean directly |
| `withPropertyValues(...)` | Adds properties for the run |
| `withSystemProperties(...)` | Adds system properties |
| `withClassLoader(...)` | Replaces the classloader, commonly used to simulate missing classes |
| `withInitializer(...)` | Adds an ApplicationContextInitializer |
| `withParent(...)` | Establishes a parent context relationship |
| `run(context -> ...)` | Creates the context, runs assertions, and closes the context |

The configuration methods return a new runner via a fluent API. You can define a shared base runner and then create variants per test:

~~~java
private final WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        ServletFeatureAutoConfiguration.class));

@Test
void disabledFeatureDoesNotCreateBean() {
    this.servletRunner
            .withPropertyValues("acme.web.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(ServletFeature.class);
            });
}
~~~

On each `run` call, the runner creates a separate context, executes the callback, and closes the context afterward. Do not retain bean instances from one run to reuse in another run.

## 5. Complete example: one library supporting both web stacks

Let us build a small library that creates a bean marking the active stack:

- In a servlet context, register `WebStack.Servlet`.
- In a reactive context, register `WebStack.Reactive`.
- If the context is non-web, register no bean.
- If the application already provides a `WebStack`, the default auto-configuration must back off.

The example includes both starters on the test classpath so both auto-configurations can be loaded. The two runners select separate contexts, allowing each stack to be tested independently.

### 5.1. Project structure

~~~text
web-context-runner-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webstack/
    │   │   ├── WebStack.java
    │   │   └── autoconfigure/
    │   │       ├── ServletStackAutoConfiguration.java
    │   │       └── ReactiveStackAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/webstack/
            └── WebStackAutoConfigurationTests.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>web-context-runner-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

Both web starters are included to test both classpath branches. No server starts automatically when calling the context runners.

If a real application has both Spring MVC and WebFlux on the classpath, Spring Boot normally prefers MVC when auto-detecting the application type. That is a rule of creating a context via `SpringApplication`; in this example, the runners directly create a servlet or reactive context as chosen by the test, without relying on that inference.

### 5.3. WebStack.java

**src/main/java/com/example/webstack/WebStack.java**

~~~java
package com.example.webstack;

public interface WebStack {

    String kind();

    record Servlet() implements WebStack {
        @Override
        public String kind() {
            return "servlet";
        }
    }

    record Reactive() implements WebStack {
        @Override
        public String kind() {
            return "reactive";
        }
    }

    record Custom(String kind) implements WebStack {
    }
}
~~~

Records keep the sample data concise. These implementations only tag the stack; they do not start a server or handle requests.

### 5.4. ServletStackAutoConfiguration.java

**src/main/java/com/example/webstack/autoconfigure/ServletStackAutoConfiguration.java**

~~~java
package com.example.webstack.autoconfigure;

import com.example.webstack.WebStack;
import jakarta.servlet.Servlet;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.servlet.DispatcherServlet;

@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnClass({Servlet.class, DispatcherServlet.class})
public class ServletStackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(WebStack.class)
    WebStack.Servlet servletStack() {
        return new WebStack.Servlet();
    }
}
~~~

There are three decision layers:

1. The context must be a servlet web application.
2. Servlet API and Spring MVC `DispatcherServlet` must be on the classpath.
3. No `WebStack` bean is already provided by the application.

The third condition sits on the bean method, so the class can be processed while the default bean still backs off when the user provides a custom implementation.

### 5.5. ReactiveStackAutoConfiguration.java

**src/main/java/com/example/webstack/autoconfigure/ReactiveStackAutoConfiguration.java**

~~~java
package com.example.webstack.autoconfigure;

import com.example.webstack.WebStack;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.DispatcherHandler;
import reactor.core.publisher.Mono;

@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnClass({DispatcherHandler.class, Mono.class})
public class ReactiveStackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(WebStack.class)
    WebStack.Reactive reactiveStack() {
        return new WebStack.Reactive();
    }
}
~~~

Here the classpath gate checks Spring WebFlux and Reactor components. The context gate still must match; merely having `DispatcherHandler` on the classpath does not turn a servlet context into a reactive context.

### 5.6. Registering auto-configuration

Create the file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.webstack.autoconfigure.ServletStackAutoConfiguration
com.example.webstack.autoconfigure.ReactiveStackAutoConfiguration
~~~

This is the Spring Boot 3.x discovery resource. In the tests below, `AutoConfigurations.of(...)` loads the classes directly to test condition logic. Direct class loading in tests **does not automatically verify that the imports resource is packaged properly**; verifying the built/published artifact requires a separate consumer smoke test.

## 6. Setting up both runners and testing the right branch

### 6.1. Declaring shared runners

In the test:

~~~java
private final AutoConfigurations configurations =
        AutoConfigurations.of(
                ServletStackAutoConfiguration.class,
                ReactiveStackAutoConfiguration.class);

private final WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner()
                .withConfiguration(configurations);

private final ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(configurations);
~~~

Each runner has a different context factory. Do not replace a servlet runner with a reactive runner just to make a test pass; doing so changes the condition being tested.

### 6.2. Servlet runner registers only the servlet bean

~~~java
@Test
void servletContextAppliesOnlyServletConfiguration() {
    this.servletRunner.run(context -> {
        assertThat(context).hasSingleBean(WebStack.class);
        assertThat(context).hasSingleBean(WebStack.Servlet.class);
        assertThat(context).doesNotHaveBean(WebStack.Reactive.class);

        assertThat(context.getBean(WebStack.class).kind())
                .isEqualTo("servlet");
    });
}
~~~

Expected result: `WebStack.Servlet` exists and `WebStack.Reactive` does not exist. Even though both classes are in the dependency graph, the web application type condition excludes the reactive branch.

### 6.3. Reactive runner registers only the reactive bean

~~~java
@Test
void reactiveContextAppliesOnlyReactiveConfiguration() {
    this.reactiveRunner.run(context -> {
        assertThat(context).hasSingleBean(WebStack.class);
        assertThat(context).hasSingleBean(WebStack.Reactive.class);
        assertThat(context).doesNotHaveBean(WebStack.Servlet.class);

        assertThat(context.getBean(WebStack.class).kind())
                .isEqualTo("reactive");
    });
}
~~~

Expected result is `reactive`. This test proves a reactive context is not mistaken for servlet just because the test runtime includes both starters.

### 6.4. ApplicationContextRunner matches neither web branch

Use the regular runner as a control test:

~~~java
@Test
void nonWebContextDoesNotApplyEitherWebConfiguration() {
    new ApplicationContextRunner()
            .withConfiguration(this.configurations)
            .run(context -> {
                assertThat(context).doesNotHaveBean(WebStack.class);
            });
}
~~~

This is the clearest demonstration of why testing web conditions requires specialized runners. Both servlet and reactive APIs are on the classpath, yet the context is non-web, so neither branch registers a bean.

## 7. Testing classpath conditions with FilteredClassLoader

A web runner creates the right context type. It does not by itself guarantee all dependencies are present. If you want to test `@ConditionalOnClass`, you can exclude a class from the classloader for a single run.

### 7.1. Missing Spring MVC DispatcherServlet

~~~java
@Test
void servletConfigurationBacksOffWhenMvcClassIsMissing() {
    this.servletRunner
            .withClassLoader(new FilteredClassLoader(DispatcherServlet.class))
            .run(context -> {
                assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
                assertThat(context).doesNotHaveBean(WebStack.class);
            });
}
~~~

The context is still a servlet web context, but the classpath condition does not match because `DispatcherServlet` is missing. This isolates the two causes: the web context is right, yet the required dependency is absent.

### 7.2. Missing Reactive DispatcherHandler

~~~java
@Test
void reactiveConfigurationBacksOffWhenWebFluxClassIsMissing() {
    this.reactiveRunner
            .withClassLoader(new FilteredClassLoader(DispatcherHandler.class))
            .run(context -> {
                assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
                assertThat(context).doesNotHaveBean(WebStack.class);
            });
}
~~~

The reactive context still exists, yet the classpath gate does not match. If only `ApplicationContextRunner` were used, the test could not prove this classpath branch because the web condition would already fail to match from the start.

### 7.3. Distinguishing context failures from classpath failures

| Test setup | Web condition | Class condition | Result |
| --- | --- | --- | --- |
| Servlet runner, MVC classes present | Matches | Matches | Servlet bean created |
| Servlet runner, missing DispatcherServlet | Matches | Does not match | No servlet bean |
| Reactive runner, WebFlux classes present | Matches | Matches | Reactive bean created |
| Reactive runner, missing DispatcherHandler | Matches | Does not match | No reactive bean |
| ApplicationContextRunner, both stacks present | Does not match | May match | No web bean |

Each test should vary one primary factor so the cause of the result is easy to read.

## 8. Testing user beans causing auto-configuration to back off

A well-behaved auto-configuration creates a default only when the application has not provided an implementation. Both sample configurations use:

~~~java
@ConditionalOnMissingBean(WebStack.class)
~~~

This can be verified with a user configuration:

~~~java
@Configuration(proxyBeanMethods = false)
static class CustomWebStackConfiguration {

    @Bean
    WebStack customWebStack() {
        return new WebStack.Custom("custom");
    }
}
~~~

Test in a servlet context:

~~~java
@Test
void servletConfigurationBacksOffForCustomBean() {
    this.servletRunner
            .withUserConfiguration(CustomWebStackConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(WebStack.class);
                assertThat(context).hasBean("customWebStack");
                assertThat(context).doesNotHaveBean(WebStack.Servlet.class);

                assertThat(context.getBean(WebStack.class).kind())
                        .isEqualTo("custom");
            });
}
~~~

Test in a reactive context:

~~~java
@Test
void reactiveConfigurationBacksOffForCustomBean() {
    this.reactiveRunner
            .withUserConfiguration(CustomWebStackConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(WebStack.class);
                assertThat(context).hasBean("customWebStack");
                assertThat(context).doesNotHaveBean(WebStack.Reactive.class);

                assertThat(context.getBean(WebStack.class).kind())
                        .isEqualTo("custom");
            });
}
~~~

These tests confirm that auto-configuration yields in both context types. If you want to test registration ordering separately, inspect the Condition Evaluation Report; do not add ordering annotations merely to make assertions pass without understanding the dependencies between configurations.

## 9. Complete test file

**src/test/java/com/example/webstack/WebStackAutoConfigurationTests.java**

~~~java
package com.example.webstack;

import com.example.webstack.autoconfigure.ReactiveStackAutoConfiguration;
import com.example.webstack.autoconfigure.ServletStackAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.boot.test.util.FilteredClassLoader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.DispatcherHandler;
import org.springframework.web.servlet.DispatcherServlet;

import static org.assertj.core.api.Assertions.assertThat;

class WebStackAutoConfigurationTests {

    private final AutoConfigurations configurations =
            AutoConfigurations.of(
                    ServletStackAutoConfiguration.class,
                    ReactiveStackAutoConfiguration.class);

    private final WebApplicationContextRunner servletRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(configurations);

    private final ReactiveWebApplicationContextRunner reactiveRunner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(configurations);

    @Test
    void servletContextAppliesOnlyServletConfiguration() {
        servletRunner.run(context -> {
            assertThat(context).hasSingleBean(WebStack.class);
            assertThat(context).hasSingleBean(WebStack.Servlet.class);
            assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
            assertThat(context.getBean(WebStack.class).kind())
                    .isEqualTo("servlet");
        });
    }

    @Test
    void reactiveContextAppliesOnlyReactiveConfiguration() {
        reactiveRunner.run(context -> {
            assertThat(context).hasSingleBean(WebStack.class);
            assertThat(context).hasSingleBean(WebStack.Reactive.class);
            assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
            assertThat(context.getBean(WebStack.class).kind())
                    .isEqualTo("reactive");
        });
    }

    @Test
    void nonWebContextAppliesNeitherConfiguration() {
        new ApplicationContextRunner()
                .withConfiguration(configurations)
                .run(context ->
                        assertThat(context).doesNotHaveBean(WebStack.class));
    }

    @Test
    void missingServletClassDisablesServletConfiguration() {
        servletRunner
                .withClassLoader(new FilteredClassLoader(DispatcherServlet.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
                    assertThat(context).doesNotHaveBean(WebStack.class);
                });
    }

    @Test
    void missingReactiveClassDisablesReactiveConfiguration() {
        reactiveRunner
                .withClassLoader(new FilteredClassLoader(DispatcherHandler.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
                    assertThat(context).doesNotHaveBean(WebStack.class);
                });
    }

    @Test
    void servletConfigurationBacksOffForCustomBean() {
        servletRunner
                .withUserConfiguration(CustomWebStackConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(WebStack.class);
                    assertThat(context).hasBean("customWebStack");
                    assertThat(context).doesNotHaveBean(WebStack.Servlet.class);
                    assertThat(context.getBean(WebStack.class).kind())
                            .isEqualTo("custom");
                });
    }

    @Test
    void reactiveConfigurationBacksOffForCustomBean() {
        reactiveRunner
                .withUserConfiguration(CustomWebStackConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(WebStack.class);
                    assertThat(context).hasBean("customWebStack");
                    assertThat(context).doesNotHaveBean(WebStack.Reactive.class);
                    assertThat(context.getBean(WebStack.class).kind())
                            .isEqualTo("custom");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomWebStackConfiguration {

        @Bean
        WebStack customWebStack() {
            return new WebStack.Custom("custom");
        }
    }
}
~~~

Run all tests:

~~~bash
mvn clean test
~~~

Expect **seven passing tests**. Each runner creates an isolated context and closes it after the callback; tests do not require an HTTP port or embedded server.

## 10. When are the runners not enough?

These two runners test **conditions and beans inside a web ApplicationContext**. They do not replace all forms of web testing.

| Goal | Suitable tool |
| --- | --- |
| Do servlet/reactive conditions match? | WebApplicationContextRunner / ReactiveWebApplicationContextRunner |
| Is the default bean created or does it back off? | Web runner + Assertable context |
| Does auto-config turn off when a class is missing on the classpath? | Web runner + FilteredClassLoader |
| MVC controller handling HTTP requests with mock servlet infrastructure | `@WebMvcTest` or `@SpringBootTest` + MockMvc |
| WebFlux controller handling requests in a mock environment | `@WebFluxTest` or `@SpringBootTest` + WebTestClient |
| Testing a real server, port, connector, and network | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Verifying starter JAR has valid discovery metadata | Consumer smoke test against the packaged artifact |

### 10.1. Do not confuse WebApplicationContextRunner with MockMvc

`WebApplicationContextRunner` provides a servlet context with `MockServletContext`; the runner itself does not provide the full request-dispatching workflow of MockMvc. If you need to test routing, controller advice, filter chains, or response bodies, use the appropriate MVC test tools.

### 10.2. Do not confuse ReactiveWebApplicationContextRunner with WebTestClient

`ReactiveWebApplicationContextRunner` creates a reactive ApplicationContext; it does not send HTTP requests on its own. To test WebFlux endpoints, use WebTestClient in a mock web test or connect to a real server in an integration test.

### 10.3. Verify discovery metadata separately

In the sample tests, `AutoConfigurations.of(...)` loads the specified classes directly. This focuses on conditions and bean behavior, but does not verify that Spring Boot finds the classes through:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

To verify distribution, build the JAR, create an independent consumer application that adds only the starter, start the context, and verify the beans appear. That is a smoke test for metadata and POM dependencies, distinct from condition unit tests.

## 11. When both Spring MVC and WebFlux are on the classpath

A project may use MVC for its server and WebFlux `WebClient` for outbound HTTP. When both Spring MVC and WebFlux are present, `SpringApplication` usually selects MVC as the default web application type.

This does not mean reactive auto-configuration cannot be tested. `ReactiveWebApplicationContextRunner` creates a reactive context directly, so the reactive branch can be tested even when both starters are on the test classpath.

If you need to test a **real Spring Boot application** running WebFlux while both stacks are present, specify it explicitly:

~~~properties
spring.main.web-application-type=reactive
~~~

Or in a test:

~~~java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class ReactiveApplicationTests {
}
~~~

Do not confuse a runner choosing a context for isolated tests with SpringApplication auto-detecting the web application type at application startup.

## 12. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Servlet condition does not match despite starter-web | Using non-web ApplicationContextRunner | Use WebApplicationContextRunner |
| Reactive condition does not match despite spring-webflux | Context is still non-web or servlet | Use ReactiveWebApplicationContextRunner |
| Expecting the runner to open an HTTP port | Confusing context runner with server integration test | Use RANDOM_PORT when a real server is needed |
| Testing servlet and reactive produces the same bean | Two auto-configurations do not distinguish web type or share the same condition | Specify explicit type in @ConditionalOnWebApplication |
| Missing-class test still has condition match | FilteredClassLoader filtered the wrong class or another class still satisfies it | Filter the exact class required by the annotation |
| Test does not prove imports resource | Using AutoConfigurations.of to load classes directly | Add a consumer smoke test with the packaged JAR |
| Both MVC and WebFlux present, yet app runs MVC | SpringApplication prefers MVC when auto-detecting | Set web-application-type=reactive if the app needs WebFlux |
| Runner tests share mutable state | Keeping stateful instances/configurations outside the context | Keep fixtures immutable and use a fresh context per run |
| Custom bean does not cause default to back off | Custom bean has a different type or misconfiguration | Check return type and @ConditionalOnMissingBean |
| Using runner to test controller responses | Runner verifies only context/beans | Use MockMvc or WebTestClient |

## 13. Checklist for choosing and writing tests

Before writing auto-configuration tests:

1. Read the conditions on the class and bean methods.
2. Determine whether the context needs to be non-web, servlet, or reactive.
3. Choose the right runner.
4. Ensure required classpath dependencies are present.
5. Use `withConfiguration(AutoConfigurations.of(...))` to load the classes under test.
6. Use `withPropertyValues` for each property branch.
7. Use `withClassLoader(FilteredClassLoader(...))` for missing-dependency branches.
8. Use `withUserConfiguration` to verify custom beans cause auto-configuration to back off.
9. Assert by type and name, not merely that the context starts.
10. Use MockMvc/WebTestClient or a server test when HTTP behavior needs checking.
11. Test an independent consumer if you need to verify the imports resource and published POM.

## 14. Self-check questions

**Question 1.** Why is `ApplicationContextRunner` unsuitable for testing `@ConditionalOnWebApplication(type = SERVLET)`?  
**Answer:** Its default constructor creates a non-web `AnnotationConfigApplicationContext`, so the servlet condition does not match.

**Question 2.** Which context does `WebApplicationContextRunner` create by default?  
**Answer:** `AnnotationConfigServletWebApplicationContext` with a `MockServletContext`.

**Question 3.** Which context does `ReactiveWebApplicationContextRunner` create by default?  
**Answer:** `AnnotationConfigReactiveWebApplicationContext`.

**Question 4.** Do the two runners automatically start an embedded server?  
**Answer:** No. They create a web ApplicationContext to test conditions and beans; use RANDOM_PORT or test clients when HTTP/server is needed.

**Question 5.** How can you prove a servlet bean is absent because DispatcherServlet is missing, rather than because the context is not servlet?  
**Answer:** Use WebApplicationContextRunner so the servlet condition matches, then use FilteredClassLoader to exclude DispatcherServlet so only the classpath condition fails.

**Question 6.** Does `AutoConfigurations.of(...)` verify the AutoConfiguration.imports file?  
**Answer:** No. It registers classes directly for the test. A consumer smoke test with the packaged JAR is needed to verify discovery metadata.

**Question 7.** When an application has both MVC and WebFlux, why can the reactive runner still test reactive auto-configuration?  
**Answer:** The runner creates a reactive ApplicationContext directly; it does not depend on SpringApplication inferring the context type from the classpath.

**Question 8.** To test that a controller returns the right HTTP response, which tool should be used?  
**Answer:** Use MockMvc for MVC or WebTestClient for WebFlux; the specialized context runners focus on context/conditions/beans.

## 15. Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing section](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [WebApplicationContextRunner — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html)
- [ReactiveWebApplicationContextRunner — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html)
- [ApplicationContextRunner — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)

**Takeaway:** Choose the runner according to the **ApplicationContext type required by the condition**. `WebApplicationContextRunner` tests the servlet stack; `ReactiveWebApplicationContextRunner` tests the reactive stack; `ApplicationContextRunner` tests non-web. Use them to verify conditions, beans, and back-off in isolated contexts; use MockMvc, WebTestClient, or server integration tests for HTTP behavior.
