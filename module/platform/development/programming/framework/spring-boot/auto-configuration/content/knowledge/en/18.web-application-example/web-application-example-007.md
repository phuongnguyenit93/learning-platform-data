# Using a Non-Web Application to Verify Web Configuration Is Not Activated

## 1. Goal and Use Cases

A Spring Boot project may contain web dependencies yet still need to run as a **background (batch), command-line, or worker application**. For example:
- A scheduled job that reads data, processes it, and writes results.
- A consumer that receives messages from a broker, processes them, and exits.
- A command-line data import/export tool.
- An application that uses a web library to make outbound HTTP calls without exposing HTTP endpoints to users.

In such cases, you must verify that Spring Boot creates a **non-web ApplicationContext** and that auto-configurations meant only for servlet/reactive web are not applied.

This lesson focuses on three tasks:

1. Distinguishing **having web libraries on the classpath** from **the application running in web mode**.
2. Selecting `WebApplicationType.NONE` or the corresponding property to create a non-web context.
3. Verifying `@ConditionalOnWebApplication` and `@ConditionalOnNotWebApplication` using tests and the condition report.

Examples use **Spring Boot 3.5.x, Java 17+**. When applying to another version, verify the APIs and packages for that exact version.

## 2. Web Classpath Does Not Mean Web Application

When adding `spring-boot-starter-web`, the classpath usually includes Spring MVC, the Servlet API, and an embedded server (e.g., Tomcat). By default, Spring Boot probes the classpath to decide `WebApplicationType`; with MVC present, the application is normally selected as **SERVLET**.

However, if the same codebase needs to run a worker/batch process, you can explicitly select **NONE**. Spring Boot then creates a non-web context, even though servlet/MVC classes still exist in the JAR.

Three main types:

| `WebApplicationType` | Context type | Purpose |
| --- | --- | --- |
| `SERVLET` | Servlet `WebApplicationContext` | MVC/Servlet applications |
| `REACTIVE` | Reactive web context | WebFlux applications |
| `NONE` | Plain, non-web context | Batch, CLI, worker, scheduler |

**Key point:** `WebApplicationType.NONE` does not remove Spring MVC, the Servlet API, or Tomcat from the classpath. It chooses the ApplicationContext type the application will use, from which web conditions are evaluated against the actual context type and environment.

Spring Boot Reference explains that if the classpath has the necessary components to run a web server, the server is normally started automatically; this behavior can be disabled with `spring.main.web-application-type=none`. See [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).

## 3. Conditions for Web Applications

Spring Boot provides two primary annotations:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
~~~

### 3.1. @ConditionalOnWebApplication

The condition matches when the application is recognized as a web application. You can restrict the type:

~~~java
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
~~~

These are three independent selection examples:
- Omitting `type`: applies to web applications in general, including servlet or reactive.
- `SERVLET`: requires specifically a servlet web application.
- `REACTIVE`: requires specifically a reactive web application.

### 3.2. @ConditionalOnNotWebApplication

The condition matches when the context is not recognized as a web application:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
class WorkerOnlyConfiguration {

    @Bean
    WorkerService workerService() {
        return new WorkerService();
    }
}
~~~

This configuration is suitable for beans that should appear only in batch/CLI/worker runs. If an application is started with a servlet or reactive context, this configuration does not match.

### 3.3. How Does Spring Recognize a Web Application?

According to Spring Boot 3.5 Reference, a servlet-based web application is recognized by one of the following indicators:
- The context is a `WebApplicationContext`;
- It has a session scope;
- The environment is a `ConfigurableWebEnvironment`.

A reactive web application is recognized by:
- The context is a `ReactiveWebApplicationContext`;
- Or the environment is a `ConfigurableReactiveWebEnvironment`.

Therefore, the condition relies on the **ApplicationContext/Environment type**, not solely on whether `DispatcherServlet` or `WebClient` exists on the classpath. See [Spring Boot 3.5 — Condition Annotations](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html).

## 4. Selecting WebApplicationType.NONE in Java

The most explicit way is to instantiate `SpringApplication` and set the application type before calling `run`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
~~~

**Order matters:** you must set `WebApplicationType.NONE` before `run(args)`, because Boot needs to know the context type while preparing startup.

You can use `SpringApplicationBuilder`:

~~~java
new SpringApplicationBuilder(BatchApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
~~~

This approach is useful when building parent/child contexts or configuring with a fluent API.

## 5. Selecting NONE via application.properties or YAML

You do not always want to edit Java code. You can set the property in `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
~~~

Or in `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

It can be passed at startup:

~~~bash
java -jar target/batch-app.jar --spring.main.web-application-type=none
~~~

With the Maven Spring Boot Plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments="--spring.main.web-application-type=none"
~~~

On Windows PowerShell with Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.arguments=--spring.main.web-application-type=none'
~~~

If the same property is declared in multiple sources, Spring Environment applies configuration source precedence rules. Command-line application arguments `--spring.main.web-application-type=none` generally have higher precedence than properties in files.

**Choose one primary approach** per application. If the code already calls `setWebApplicationType`, avoid scattering configurations across multiple sources that make it hard for operators to know the actual context type.

## 6. Distinguishing NONE from server.port=-1

This is a common configuration mistake.

| Configuration | ApplicationContext type | Is a web server listening on HTTP? | Web condition |
| --- | --- | --- | --- |
| `spring.main.web-application-type=none` | Non-web context | No | `@ConditionalOnWebApplication` does not match |
| `server.port=-1` | Still a web context | Does not open an HTTP port | Web condition can still match |
| `server.port=0` | Web context | Yes, server uses a random port | Web condition matches if other conditions pass |

If you only want to disable the listener while still needing a `WebApplicationContext`, `server.port=-1` is the right choice. If you want to verify **web configuration is not activated**, choose `WebApplicationType.NONE`.

Spring Boot Reference explicitly states that `server.port=-1` disables the HTTP endpoint while still creating a `WebApplicationContext`; therefore it is not equivalent to NONE. See [Embedded Web Servers — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).

## 7. Runnable Example: Same Web Classpath, Running a Non-Web Batch Application

The following example intentionally uses `spring-boot-starter-web` to prove the classpath has MVC/Servlet yet the application can still run non-web when NONE is selected.

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>non-web-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Intentionally includes full Spring MVC and embedded server on classpath. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 7.2. Application Code

Create `src/main/java/example/BatchApplication.java`:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.context.WebApplicationContext;

@SpringBootApplication(proxyBeanMethods = false)
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    @ConditionalOnWebApplication(
            type = ConditionalOnWebApplication.Type.SERVLET)
    WebFeature webFeature() {
        return new WebFeature();
    }

    @Bean
    @ConditionalOnNotWebApplication
    BatchFeature batchFeature() {
        return new BatchFeature();
    }

    @Bean
    CommandLineRunner reportContextMode(
            ConfigurableApplicationContext context) {

        return args -> {
            System.out.println(
                    "WEB_APPLICATION_CONTEXT="
                            + (context instanceof WebApplicationContext));

            System.out.println(
                    "WEB_FEATURE_PRESENT="
                            + context.containsBean("webFeature"));

            System.out.println(
                    "BATCH_FEATURE_PRESENT="
                            + context.containsBean("batchFeature"));
        };
    }

    static class WebFeature {
    }

    static class BatchFeature {
    }
}
~~~

Explanation:
- `setWebApplicationType(WebApplicationType.NONE)` tells Spring Boot to create a non-web context.
- `webFeature()` is registered only when the context is a servlet web application.
- `batchFeature()` is registered only when the context is not a web application.
- `CommandLineRunner` prints the context type and presence of both beans after the context starts.

### 7.3. Running the Application

~~~bash
mvn spring-boot:run
~~~

Or:

~~~bash
java -jar target/non-web-condition-demo-1.0.0.jar
~~~

**Output of the three verification lines:**

~~~text
WEB_APPLICATION_CONTEXT=false
WEB_FEATURE_PRESENT=false
BATCH_FEATURE_PRESENT=true
~~~

Spring Boot may still print the banner and startup logs. The three lines above are the output produced by the example's `CommandLineRunner`; they do not represent the entire console output.

Because the web starter is still on the classpath yet there is no `WebApplicationContext`, the servlet-only bean is not registered and the batch bean is registered. The application does not start an embedded web server.

### 7.4. Trying Without NONE Mode

To see the difference, temporarily remove the line:

~~~java
application.setWebApplicationType(WebApplicationType.NONE);
~~~

With `spring-boot-starter-web` still on the classpath, Boot normally auto-detects a servlet application. When other dependencies and conditions match:
- `WEB_APPLICATION_CONTEXT=true`;
- `WEB_FEATURE_PRESENT=true`;
- `BATCH_FEATURE_PRESENT=false`.

Exact results depend on properties and other conditions, but this is a useful control comparison to confirm the conditions were written correctly.

## 8. Testing Conditions with ApplicationContextRunner

Spring Boot Test provides two key runners:

- `ApplicationContextRunner`: creates a plain context, suited for testing non-web conditions.
- `WebApplicationContextRunner`: creates a servlet web context, suited for testing configurations that only work in a servlet application.

If testing auto-configuration meant only for reactive applications, use `ReactiveWebApplicationContextRunner`.

Spring Boot Reference recommends using the runner matching the context type required by the auto-configuration. See [Creating Your Own Auto-configuration — Simulating a Web Context](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html).

### 8.1. Test Dependency

Add to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Keep `spring-boot-starter-web` in main dependencies so the servlet API is on the test classpath.

### 8.2. Illustrative Auto-Configuration

Create `src/test/java/example/WebConditionTests.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class WebConditionTests {

    static class WebFeature {
    }

    static class BatchFeature {
    }

    @AutoConfiguration
    static class ModeAutoConfiguration {

        @Bean
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.SERVLET)
        WebFeature webFeature() {
            return new WebFeature();
        }

        @Bean
        @ConditionalOnNotWebApplication
        BatchFeature batchFeature() {
            return new BatchFeature();
        }
    }

    private final ApplicationContextRunner nonWebRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ModeAutoConfiguration.class));

    private final WebApplicationContextRunner servletRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ModeAutoConfiguration.class));

    @Test
    void servletOnlyBeanIsAbsentFromNonWebContext() {
        nonWebRunner.run(context -> {
            assertThat(context).doesNotHaveBean(WebFeature.class);
            assertThat(context).hasSingleBean(BatchFeature.class);
        });
    }

    @Test
    void servletOnlyBeanIsPresentInServletContext() {
        servletRunner.run(context -> {
            assertThat(context).hasSingleBean(WebFeature.class);
            assertThat(context).doesNotHaveBean(BatchFeature.class);
        });
    }
}
~~~

### 8.3. Running the Tests

~~~bash
mvn test -Dtest=WebConditionTests
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=WebConditionTests'
~~~

**Expected result:** two tests PASS:
1. The default context of `ApplicationContextRunner` does not register `WebFeature`, yet has `BatchFeature`.
2. `WebApplicationContextRunner` registers `WebFeature`, and does not register `BatchFeature`.

This is a good control test: the exact same auto-configuration, changing only the context type, yields opposite condition outcomes. The test runner does not need to open a public HTTP port.

## 9. Checking Real Auto-Configuration and the Condition Evaluation Report

The example above uses custom configuration to verify the condition principle. When investigating a real application, you also need to inspect the auto-configurations provided by Spring Boot.

Some common web configurations with web conditions:
- `WebMvcAutoConfiguration`: for servlet web applications and required MVC classes.
- `DispatcherServletAutoConfiguration`: configures DispatcherServlet for servlet applications.
- `WebFluxAutoConfiguration`: configures WebFlux when the application is recognized as reactive and the classpath matches.
- Server/servlet container configurations: require the right context type and dependencies.

Not every auto-configuration with "web" in its name uses the exact same condition. Read the annotations of the specific class to verify.

### 9.1. Enabling the Debug Report

Run:

~~~bash
java -jar target/non-web-condition-demo-1.0.0.jar --debug
~~~

Spring Boot prints the **Conditions Evaluation Report**. Find the web-related sources and inspect the unmatched conditions, such as the condition requiring a servlet web application. Exact messages depend on the class and version; do not hard-code messages into tests or runbooks.

### 9.2. Actuator Conditions Endpoint

If the application has Actuator, you can expose the conditions endpoint:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

In a **web application**, you can call:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

An application configured with `WebApplicationType.NONE` has no embedded web server to serve HTTP endpoints; therefore you cannot by default use that URL to inspect a non-web application. For non-web apps, use the `--debug` log, access `ConditionEvaluationReport` in tests, or use another appropriate observability tool.

### 9.3. Checking the Bean Inventory

You can use Actuator `/actuator/beans` when a web management context is exposed, or inspect bean definitions in tests. However, do not conclude that all web auto-configuration was disabled just because one specific bean is missing; check the condition source and the entire related context.

## 10. How to Check via API in Code

In a test or diagnostic tool, you can verify whether the context is web:

~~~java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.web.context.WebApplicationContext;

boolean isWeb =
        applicationContext instanceof WebApplicationContext;
~~~

This is a useful check for servlet contexts. For reactive applications, check `ReactiveWebApplicationContext`; if you want to distinguish servlet/reactive/none completely, check the corresponding context types or use the `WebApplicationType` configured on the application.

Do not use a classpath check such as:

~~~java
ClassUtils.isPresent(
        "org.springframework.web.servlet.DispatcherServlet",
        classLoader);
~~~

to conclude the application is running in web mode. It only tells you whether the class can be loaded, not whether the current context is a servlet web context.

## 11. Misleading Scenarios

| Scenario | What actually happens? | How to verify |
| --- | --- | --- |
| Has `spring-boot-starter-web`, NONE not set | Boot normally auto-selects servlet application | Inspect context type and web conditions |
| Has web starter, sets `WebApplicationType.NONE` | Web classes remain on classpath, context is non-web | Check `WebApplicationContext` and marker beans |
| Sets `server.port=-1` | Web context is still created, just does not open HTTP port | Do not use as proof of non-web |
| Only `spring-boot-starter-webflux` | Boot normally selects reactive when MVC is absent | Check `WebApplicationType.REACTIVE` |
| Has both MVC and WebFlux | Boot defaults to prioritizing servlet | Explicitly set `spring.main.web-application-type=reactive` if reactive is wanted |
| Uses `ApplicationContextRunner` | Test creates a generic non-web context | Use `WebApplicationContextRunner` for servlet positive cases |
| Uses `@SpringBootTest(webEnvironment = NONE)` | Test does not start a web server, yet context type depends on the test's web type config | If the goal is a non-web context, set `spring.main.web-application-type=none` explicitly |
| A web bean still appears in a NONE context | The bean may come from user configuration or another condition not depending on web | Locate the bean source and its annotations |
| No server yet web condition still matches | May be using `server.port=-1` or a web context not running a listener | Check context type, not just the port |

### Not Every HTTP-Related Configuration Is Disabled

For example, a batch application may need `RestClient` or `WebClient` to **call external APIs**. These clients can be configured based on the classpath and do not require the application to be a web server. Therefore, `WebApplicationType.NONE` does not mean stripping all HTTP client support.

What must be verified is that **beans meant only for an inbound web server / servlet / reactive web context** are not registered when the context is non-web. Distinguish inbound servers from outbound HTTP clients to avoid accidentally removing the ability to call external services.

## 12. Common Pitfalls and Fixes

| Error | Cause | Fix |
| --- | --- | --- |
| Web starter present so server still runs in batch | Boot probes classpath and chooses servlet | Set `WebApplicationType.NONE` or `spring.main.web-application-type=none` |
| Only set `server.port=-1` expecting web condition to be false | Port does not determine ApplicationContext type | Use NONE if a non-web context is needed |
| Using `@ConditionalOnWebApplication` for a batch bean | Condition is inverted from the goal | Use `@ConditionalOnNotWebApplication` |
| Testing web conditions with ApplicationContextRunner expecting a match | Runner creates a generic non-web context | Use WebApplicationContextRunner for servlet cases |
| Using classpath checks to determine web mode | Class may be present even when context is non-web | Check context/environment or ConditionEvaluationReport |
| Thinking NONE removes web libraries from the JAR | NONE only chooses context type | Remove dependencies if you truly want to exclude them from the artifact |
| Still seeing a web bean in NONE | Bean may be created by user config or another condition | Trace bean definition and source |
| Using Actuator HTTP endpoint in a NONE app | No web server serving HTTP | Use `--debug`, tests, or other diagnostic tools |
| Both MVC and WebFlux present, Boot picks the wrong type | Auto-detection prioritizes servlet when MVC is present | Set explicit `spring.main.web-application-type` |

## 13. Verification Workflow in a Real Project

1. **Check dependencies:** see whether `spring-boot-starter-web`, `spring-boot-starter-webflux`, the Servlet API, or any server implementation is on the classpath.
2. **Determine startup mode:** look for `setWebApplicationType`, `spring.main.web-application-type`, `SpringApplicationBuilder.web(...)`, and overriding configuration sources.
3. **Check context type:** confirm whether the current context is generic, servlet, or reactive.
4. **Read the conditions of the auto-configuration to verify:** inspect `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication`, `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and other conditions.
5. **Enable the condition report:** run `--debug`, read the web condition source and message.
6. **Check the bean inventory:** confirm specific web beans are absent in the non-web context; check the bean source if one still appears.
7. **Write bidirectional tests:** one non-web test and one servlet/reactive positive control test using the appropriate runner.
8. **Verify the packaged application:** run the JAR with the NONE property in a production-like environment, because profile/command-line configurations may differ from tests.

A high-quality conclusion must state: **the actual context type, condition source, specific beans, and proving tests**. Merely saying "port 8080 is not open" is not enough to assert that web auto-configuration did not run.

## 14. Self-Check Questions

**Question 1.** A project has `spring-boot-starter-web`, yet sets `spring.main.web-application-type=none`. Are servlet classes removed from the classpath?

**Answer:** No. The dependencies remain; Boot creates a non-web context and web conditions are evaluated against that context.

**Question 2.** Is `server.port=-1` equivalent to `WebApplicationType.NONE`?

**Answer:** No. `server.port=-1` can disable the HTTP listener while still creating a `WebApplicationContext`, so web conditions can still match.

**Question 3.** Which annotation is appropriate for a bean used only in batch applications?

**Answer:** `@ConditionalOnNotWebApplication`.

**Question 4.** Which runner should be used to test a configuration meant only for a servlet web application?

**Answer:** `WebApplicationContextRunner`. Use `ApplicationContextRunner` to test non-web contexts and `ReactiveWebApplicationContextRunner` for reactive contexts.

**Question 5.** Why can an HTTP client still exist in a NONE application?

**Answer:** An outbound HTTP client does not mean the application provides an inbound web server. Client conditions can rely on the classpath and beans without requiring a web application context.

## 15. Official References

- Spring Boot 3.5 — Embedded Web Servers (disabling server, `spring.main.web-application-type=none`, difference from `server.port=-1`): https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration (web application conditions, runners for servlet/reactive contexts): https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `WebApplicationType`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.5 API — `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
- Spring Boot 3.5 API — `ConditionalOnNotWebApplication`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnNotWebApplication.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 API — `WebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html
