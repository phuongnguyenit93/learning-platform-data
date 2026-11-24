# Explicitly Selecting the Application Type with setWebApplicationType or spring.main.web-application-type

## 1. Why Select the Application Type Explicitly?

When `SpringApplication.run(...)` is called, Spring Boot must decide which type of `ApplicationContext` to create and whether to start an embedded web server. A Spring MVC HTTP application differs from a WebFlux application and differs from a program that only runs background tasks or batch processing.

Normally, Spring Boot **infers the application type from the libraries on the classpath**. This is convenient, but there are cases where the developer must choose explicitly:

- A project includes `spring-boot-starter-web`, yet in a batch run mode it needs to initialize beans and execute a task **without** opening an HTTP port.
- A project contains both Spring MVC and WebFlux libraries, yet a specific runtime configuration must use the WebFlux model.
- You want to keep the Java code unchanged while deciding how each environment runs via `application.properties`, `application.yml`, environment variables, or command-line arguments.
- During testing, you want to initialize business processing without starting an actual web server.

This topic focuses on **two ways to decide the startup type**: calling the Java API `SpringApplication.setWebApplicationType(...)` and declaring the `spring.main.web-application-type` property. They affect the **application context type**, without directly changing ports, endpoints, or automatically adding missing libraries.

## 2. Three Values of WebApplicationType

The enum lives at `org.springframework.boot.WebApplicationType` and has three values:

| Value | Meaning | Default Context in Spring Boot 3.3 | Embedded Web Server |
|---|---|---|---|
| `NONE` | Run as a standard Spring application, not a web application | `AnnotationConfigApplicationContext` | Does not start |
| `SERVLET` | Run a Servlet-based web application, typically Spring MVC | `AnnotationConfigServletWebServerApplicationContext` | Starts when suitable Servlet server infrastructure is present |
| `REACTIVE` | Run a reactive web application, typically Spring WebFlux | `AnnotationConfigReactiveWebServerApplicationContext` | Starts when suitable Reactive web server infrastructure is present |

The context names in the table are **defaults** when `ApplicationContextFactory`/context class is not customized. Choosing `SERVLET` or `REACTIVE` requests a startup type; it does not guarantee the application will run successfully if required components are missing from the classpath.

### Spring Boot Infers Automatically When Not Explicitly Chosen

Conceptualizing the default algorithm:

```text
Does the classpath have Spring MVC / Servlet indicators?
           |
       Yes +--------------------> SERVLET
           |
          No
           v
Does the classpath have WebFlux indicators?
           |
       Yes +--------------------> REACTIVE
           |
          No
           v
          NONE
```

This is a high-level conceptual illustration, not the exact source code of the classpath detector. When **both Spring MVC and WebFlux** are present, Spring Boot typically prefers `SERVLET`. For example, an MVC application adding `spring-webflux` to use `WebClient` **does not automatically turn into a WebFlux application**. You can override the default type, but you must verify all required libraries, auto-configurations, and controller models.

Core point: `WebApplicationType` is a **bootstrap-time decision**. It differs from `spring.profiles.active` (selecting configuration profiles), `server.port` (selecting the port), and `@Primary` (prioritizing beans during dependency injection).

## 3. Approach 1: Selecting the Type with setWebApplicationType(...)

Signature in Spring Boot 3.3:

```java
public void setWebApplicationType(WebApplicationType webApplicationType);
```

The right usage is to create `SpringApplication`, set the type, and then call `run(args)`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class ExampleBootstrap {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExampleBootstrap.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

The snippet above illustrates calling the API. In practice, the bootstrap class needs to sit inside a Spring Boot project with appropriate dependencies and is usually annotated with `@SpringBootApplication`, as in the complete example in section 5.

Common options:

```java
application.setWebApplicationType(WebApplicationType.NONE);     // Do not run Web
application.setWebApplicationType(WebApplicationType.SERVLET);  // Servlet Web
application.setWebApplicationType(WebApplicationType.REACTIVE); // Reactive Web
```

In real code, only call the value needed for that run. These are **not** three statements to run back-to-back: if called multiple times before `run` with no other configuration, the last value set is the one held on the `SpringApplication` object at that moment.

Why use `new SpringApplication(...)`? The shorthand `SpringApplication.run(App.class, args)` creates and runs the application in a single call, so it does not expose an `application` variable on which to call the setter before `run`. When startup configuration needs to be customized in code, create the object explicitly.

Retrieving the value on the application object:

```java
WebApplicationType chosen = application.getWebApplicationType();
System.out.println(chosen);
```

This call reports the **configuration state at the time of reading**. If read **before** `run(args)`, note that `spring.main.web-application-type` from the environment may be bound onto `SpringApplication` during startup preparation and change the final selection.

## 4. Approach 2: Selecting the Type with spring.main.web-application-type

Exact property:

```properties
spring.main.web-application-type=none
```

Common values are `none`, `servlet`, and `reactive` (Spring Boot converts them into the corresponding enum). Use lowercase in configuration files to match Spring Boot's property naming conventions.

### In application.properties

File `src/main/resources/application.properties`:

```properties
spring.application.name=web-mode-demo
spring.main.web-application-type=none
```

When run, the application initializes a non-web Spring context even if the project includes `spring-boot-starter-web`.

### In application.yml

Use **one** file format matching your project; do not duplicate declarations in both:

```yaml
spring:
  application:
    name: web-mode-demo
  main:
    web-application-type: none
```

### Via Command-Line Arguments

Once packaged as a Spring Boot executable JAR:

```bash
java -jar build/libs/web-mode-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

When running via Gradle Wrapper (Linux/macOS):

```bash
./gradlew bootRun --args='--spring.main.web-application-type=none'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

The `--spring.main.web-application-type=none` argument is a **Spring Boot argument** passed to `main(String[] args)`. `--args` is the Gradle `bootRun` task option for forwarding arguments into the application. Do not confuse these two mechanisms.

### Via Environment Variables

Spring Boot supports binding environment variable names via relaxed binding rules. For example:

```bash
SPRING_MAIN_WEB_APPLICATION_TYPE=none java -jar build/libs/web-mode-demo-0.0.1-SNAPSHOT.jar
```

The Bash syntax above applies only to that single invocation. In PowerShell:

```powershell
$env:SPRING_MAIN_WEB_APPLICATION_TYPE = "none"
java -jar .\build\libs\web-mode-demo-0.0.1-SNAPSHOT.jar
Remove-Item Env:SPRING_MAIN_WEB_APPLICATION_TYPE
```

Environment variables are convenient when running in containers or deployment platforms without modifying source code or repackaging the JAR. External configuration variables remain subject to Spring Boot's `PropertySource` precedence rules.

## 5. Complete Example: One Project Running SERVLET or NONE

The example uses **Java 17+**, **Spring Boot 3.3.x**, **Gradle Groovy DSL**, and `spring-boot-starter-web`. We deliberately include the Web dependency and observe how explicit type selection changes the outcome.

Structure:

```text
web-mode-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/webmode/
    │   ├── WebModeDemoApplication.java
    │   └── HelloController.java
    └── resources/
        └── application.properties
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'web-mode-demo'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
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
}
```

**File `src/main/java/com/example/webmode/WebModeDemoApplication.java`:**

```java
package com.example.webmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebModeDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(WebModeDemoApplication.class);

        // Select type via Java API.
        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.run(args);
    }

    @Bean
    CommandLineRunner showContext(ApplicationContext context) {
        return args -> System.out.println(
                "Context type: " + context.getClass().getSimpleName());
    }
}
```

**File `src/main/java/com/example/webmode/HelloController.java`:**

```java
package com.example.webmode;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
```

**File `src/main/resources/application.properties`** (initially without setting the type):

```properties
spring.application.name=web-mode-demo
server.port=8080
```

The example is designed to run with a Gradle Wrapper generated by a project initializer or pre-installed Gradle. If the repository lacks `gradlew`/`gradlew.bat`, generate the Wrapper using your project's standard mechanism before running the commands below; you cannot invoke the Wrapper when the files do not yet exist.

### Pass A — Run SERVLET via Java API

Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Because `main` calls `setWebApplicationType(WebApplicationType.SERVLET)` and no external property overrides it, the default context is a Servlet Web context. Logs include the line printed by the program, typically:

```text
Context type: AnnotationConfigServletWebServerApplicationContext
```

Run in a second terminal:

```bash
curl -s http://localhost:8080/hello
```

Response body:

```text
hello
```

Windows PowerShell can use `Invoke-RestMethod http://localhost:8080/hello`. The successful HTTP request confirms the application is serving under the Servlet model. Stop this run with Ctrl+C before starting another run on the same port.

### Pass B — Same Java Code, Setting NONE on the Command Line

Keep both Java files unchanged and run:

```bash
./gradlew bootRun --args='--spring.main.web-application-type=none'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

This time the property from application arguments is bound by Spring Boot during startup, which can **override** the `SERVLET` value set via the Java API. The line printed by the application will resemble:

```text
Context type: AnnotationConfigApplicationContext
```

The application still creates appropriate Spring beans and runs `CommandLineRunner`, yet **does not** create a Servlet Web server. If no threads keep the JVM alive, the process exits after finishing the task; that is normal behavior for a non-web application. There is no `http://localhost:8080/hello` endpoint from **this run**; if the URL still responds, another process may be running on port 8080.

Something worth remembering: the `HelloController` bean may still be registered via component scan, yet under `WebApplicationType.NONE`, there is no actual Web infrastructure to accept and map HTTP requests to that controller.

### Pass C — Selecting NONE in the Configuration File

Remove `--spring.main.web-application-type=none` from the command, then add to `application.properties`:

```properties
spring.application.name=web-mode-demo
server.port=8080
spring.main.web-application-type=none
```

Run `./gradlew bootRun` again. The result is likewise a **non-web application** even though `main` still calls `setWebApplicationType(SERVLET)`. This demonstrates that **external configuration properties are not only for setting defaults**; they can replace the setter value during startup preparation.

To return to Servlet **without editing the file**, you can use a command-line argument with higher precedence than the config file:

```bash
./gradlew bootRun --args='--spring.main.web-application-type=servlet'
```

The outcome depends on whether the application retains default command-line argument reading; the example above keeps standard Spring Boot configuration. If the port is occupied by another application, stop that process or change `server.port`.

## 6. If You Do Not Want to Hard-Code the Choice in main

When you want the project's type configured entirely via `spring.main.web-application-type`, use the simple entry point:

```java
package com.example.webmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebModeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebModeDemoApplication.class, args);
    }
}
```

This is an **alternative version of the same Java file**, not placed alongside the version in section 5. If using this variant for the hands-on project, re-add the `@Bean CommandLineRunner` from section 5 to retain the log line observing the context type.

When no type property is set, Boot infers from the classpath. With `spring-boot-starter-web`, the usual result is `SERVLET`. When `spring.main.web-application-type=none` is present, the environment chooses `NONE`. Calling the static `SpringApplication.run(...)` **does not prevent** Spring Boot from reading and applying `spring.main.*` properties.

Choose the form according to your intent: use the setter when `main` must decide programmatically, and use properties when operations need to switch types without rewriting source code.

## 7. Choosing REACTIVE: Needs Both the Right Type and Matching Dependencies

To run real WebFlux, the application requires reactive HTTP server infrastructure. For example, a separate project has:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

When **only the WebFlux starter** is present as the web stack and Spring MVC is absent, Spring Boot normally picks `REACTIVE` automatically. To specify it explicitly, use either approach:

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

or:

```properties
spring.main.web-application-type=reactive
```

Merely putting `reactive` in the property **does not automatically download** Reactor Netty, WebFlux, or supporting classes. In a project that currently has `spring-boot-starter-web` without a reactive server, forcing `REACTIVE` can make startup fail. Do not treat changing the property as an automatic migration of an entire architecture from Servlet to reactive.

When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, the usual default is Servlet. Forcing Reactive requires verifying Spring Boot auto-configuration, servlet/reactive components, web server libraries, endpoints, and security compatibility. Only do this when there is a clear architectural requirement, not to fix an isolated port or controller bug.

## 8. Relationship Between Setter, Properties, and Configuration Precedence

When runtime behavior differs from the setter call, examine both layers:

1. **Initial state:** the `new SpringApplication(...)` constructor infers from the classpath; calling `setWebApplicationType(...)` updates the type on the Java object.
2. **Configuration during execution:** Spring Boot prepares `Environment` and binds `spring.main.*` properties onto `SpringApplication`. Loaded external properties can **replace the selection from the Java API** before creating the appropriate context.

Example from section 5:

```text
Classpath: spring-boot-starter-web
              |
       Inferred: SERVLET
              |
      Java setter: SERVLET
              |
--spring.main.web-application-type=none
              |
         Final: NONE
              |
  AnnotationConfigApplicationContext
              |
        Does not run HTTP
```

If `application.properties` sets `none` while a command-line argument sets `servlet`, under Spring Boot's default mechanism, **command-line arguments take higher precedence than file values**. Other configuration sources (environment variables, JVM system properties, profiles, and external config files) also participate in the precedence order; when conflicts arise, check which source actually gets loaded.

**Two easy-to-remember rules:**

- Do not assume `setWebApplicationType(SERVLET)` is always the final choice if `spring.main.web-application-type` exists in external configuration.
- Do not assume `getWebApplicationType()` printed **before `run`** is final proof. Inspect the actual context or check HTTP behavior **after startup succeeds**.

If the application uses a custom `ApplicationContextFactory`, the actual context class is also influenced by how that factory is written; the table in section 2 reflects the default mechanism.

## 9. Distinguishing from server.port and Other Settings

| Intent | Configuration | Consequence |
|---|---|---|
| Do not run a Web server | `spring.main.web-application-type=none` or `setWebApplicationType(NONE)` | Selects a non-web `ApplicationContext`. |
| Run Servlet Web | `spring.main.web-application-type=servlet` or setter `SERVLET` | Uses Servlet infrastructure, if dependencies support it. |
| Run Reactive Web | `spring.main.web-application-type=reactive` or setter `REACTIVE` | Uses Reactive infrastructure, if dependencies support it. |
| Change HTTP port | `server.port=9090` | Still a Web application; only changes the port. |
| Let OS pick the Web port | `server.port=0` | Web server still starts on an available random port. |
| Disable HTTP endpoints while keeping Web context | `server.port=-1` | Not equivalent to `WebApplicationType.NONE`. |
| Switch configuration profile | `spring.profiles.active=dev` | Selects profile-based config/beans; not directly a Web type choice. |

Spring Boot also has properties for SSL, context paths, sessions, graceful shutdown, and many other Web settings. They tune the chosen Web system; they **do not replace the `WebApplicationType` decision**.

For example: if `NONE` is already selected, changing `server.port=9090` does not create an HTTP server. If you want to keep a Servlet Web context without opening HTTP endpoints, `server.port=-1` carries a different meaning and requires verifying which infrastructure is still initialized.

## 10. What Can a Non-Web Application Still Do?

`WebApplicationType.NONE` does not mean dropping Spring or dropping all beans. The application can still:

- Load `@Configuration`, `@Component`, and `@Bean` definitions that do not depend on Web infrastructure.
- Use Spring Dependency Injection, externalized configuration, logging, validation, and the bean lifecycle.
- Run `CommandLineRunner` or `ApplicationRunner` to process data, execute batch jobs, or validate configuration at startup.
- Make **outbound** HTTP calls through an HTTP client if matching dependencies are configured; `NONE` only governs the **application's web server role**, not all network connections.
- Exit the process once work finishes, provided no non-daemon threads keep the JVM alive.

Conversely, components requiring a Servlet request/context or Reactive Web infrastructure may not be configured or may fail to initialize. For example, a Servlet `Filter` needs a full Servlet Web runtime; a `@GetMapping` in a controller does not open an HTTP endpoint under `NONE`.

A batch processing program using Spring can select `NONE` and declare a `CommandLineRunner`:

```java
@Bean
CommandLineRunner runJob() {
    return args -> System.out.println("Job processing finished");
}
```

This is an illustrative bean placed **inside** a `@SpringBootApplication` or `@Configuration` class; it is not an independently compilable Java file. To handle exit codes, errors, and resources for background jobs in real systems, additionally design process termination rules and job monitoring.

## 11. Common Errors and How to Verify

| Symptom | Common Cause | How to Check |
|---|---|---|
| Called setter `SERVLET`, yet app opens no port | `spring.main.web-application-type=none` from file, env var, or CLI overrode it | Check external config and actual running context type. |
| Set `none`, yet `localhost:8080` is still reachable | A **different** Web process is still alive | Stop the old instance; inspect PID and startup logs of the right process. |
| Selected `SERVLET`, yet startup reports missing Servlet Web server factory | Missing embedded server dependency or wrong exclusion config | Inspect `runtimeClasspath`, starter-web/server dependencies, and root exception cause. |
| Selected `REACTIVE`, yet fails to start | Missing WebFlux/reactive server or conflicting config | Inspect Gradle dependencies and auto-configuration conditions. |
| Lost `@GetMapping` endpoints when choosing `NONE` | App creates no Web server so it receives no HTTP requests | Switch back to `SERVLET`/`REACTIVE` if needed, or use a non-web runner if HTTP is unneeded. |
| Set `server.port=9090` with no listening port | App is still `NONE`; port applies only when a server exists | Check `spring.main.web-application-type` first. |
| Calling `getWebApplicationType()` before `run` shows a different value from runtime | `spring.main.*` is bound during bootstrap after the print point | Inspect the context after startup and actual property sources. |
| Entered `web` or invalid string for the property | Only `none`, `servlet`, `reactive` exist | Change to a supported enum value and read config binding errors. |
| Both MVC and WebFlux present, expected automatic REACTIVE | Servlet default wins when MVC is present | Choose type explicitly and confirm full compatible reactive infrastructure. |

Practical troubleshooting workflow:

1. Identify the exact process and launch command: IDE, `bootRun`, or `java -jar`.
2. Inspect `runtimeClasspath` for which Servlet/WebFlux starters exist; do not guess from module names.
3. Locate every place declaring `spring.main.web-application-type`: packaged config, external config, profiles, env vars, and command line.
4. Observe the context class the application creates after bootstrap. For Web modes, confirm the server and endpoint via logs/actual HTTP calls.
5. Read the root error cause (`Caused by`) if the application fails to run. Only change the Web type when the error relates directly to runtime type or application design.

When deep analysis of why an auto-configuration was applied or skipped is needed, enable the condition evaluation report with `--debug`. Distinguish Spring Boot's condition debug flag from an IDE's line-by-line debugger mode.

## 12. Verified Hands-On Practice

Using the project from section 5, proceed sequentially, stopping the previous process before each rerun:

1. Keep the `SERVLET` setter and declare no property. Verify the Servlet context log and `GET /hello` returning `hello`.
2. Keep the Java code unchanged, run `bootRun --args='--spring.main.web-application-type=none'`. Verify the non-web context and confirm **that specific run** opens no HTTP server.
3. Add `spring.main.web-application-type=none` to `application.properties`. Run without `--args` to verify file configuration still overrides the Java setter.
4. Keep `none` in the file, yet run with `--spring.main.web-application-type=servlet`. Confirm that in the standard example, application arguments take precedence over the file.
5. Replace `main` with the `SpringApplication.run(...)` variant from section 6; repeat both `none`/`servlet` property values to see the type can be controlled entirely via configuration.
6. In a **separate test project**, replace the Web MVC dependency with WebFlux and try `spring.main.web-application-type=reactive`. Confirm the Reactive context and avoid equating enum selection with adding libraries.

Self-assessment questions: **Why can `WebApplicationType.NONE` still run `CommandLineRunner`?** **Why is `server.port=0` not equivalent to `NONE`?** **When setter and property differ, what must you observe to know which configuration actually took effect?** Answering all three means you understand both the mechanism and how to verify it.

## Official Documentation for Reference

- Spring Boot 3.3, `SpringApplication` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3, `WebApplicationType` enum: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3, `SpringApplication` mechanism and Web Environment: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, disabling the Web server configuration: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot, Externalized Configuration and `spring.main.*` binding: https://docs.spring.io/spring-boot/reference/features/external-config.html

Technical conclusion: **both `setWebApplicationType(...)` and `spring.main.web-application-type` determine the Spring Boot application type before the context is created.** By default, Spring Boot infers from the classpath; with an explicit selection, it attempts to create the context of the specified type. Final success still depends on dependencies, configuration, and application beans.