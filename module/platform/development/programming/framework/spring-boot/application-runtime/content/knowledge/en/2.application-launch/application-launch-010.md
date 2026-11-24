# Building a Spring Boot Command-Line Application Without Starting a Web Server

## 1. Purpose and When to Use

A **command-line interface (CLI) application** runs a task from the terminal, accepts arguments, outputs results, and typically exits with a process status code. Not every Spring Boot application needs to serve HTTP. Typical examples include periodic data imports, file processing, report generation, data synchronization, maintenance utilities, or jobs invoked by a scheduler.

Spring Boot remains valuable for CLI tools because it provides **dependency injection**, bean management, profile-based configuration, logging, data integration, and lifecycle management. The core difference is:

- **Web applications** typically create a web-capable `ApplicationContext` and start an embedded server when suitable dependencies and configuration are present.
- **Pure CLI applications** use a non-web Spring context, execute business logic, and exit. They do not need to open an HTTP port, controllers, a servlet container, or a reactive web server.

Within the scope of this lesson, we build a Java 17+ program capable of running:

~~~text
java -jar target/cli-demo-1.0.0.jar --name=Lan --repeat=2
~~~

The program loads Spring beans, reads two command-line options, prints greetings twice, closes the context, and returns control to the shell. **No HTTP server is started by Spring Boot**.

## 2. How Does Spring Boot Decide Whether to Run Web or Not?

`SpringApplication` infers `WebApplicationType` from the classpath if not explicitly specified. The three main choices are:

| Value | Meaning |
| --- | --- |
| `NONE` | Runs a non-web Spring `ApplicationContext`. Does not initialize an embedded web server. |
| `SERVLET` | Runs a Servlet-based web application when the appropriate stack is configured. |
| `REACTIVE` | Runs a reactive web application when the appropriate stack is configured. |

The clearest approach for a CLI is setting this in `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
~~~

Or in YAML:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Choose **one** config file format for this setting to avoid duplicate configuration. When set to `none`, even if web-related dependencies are added to the project later, Spring Boot is instructed to create a non-web application. Having HTTP client libraries to **call** external services does not mean the application must **open** an HTTP port to accept requests.

You can also configure this directly in Java:

~~~java
SpringApplication application = new SpringApplication(CliApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

The snippet above only illustrates an alternative configuration style; to compile, you need to import `org.springframework.boot.SpringApplication` and `org.springframework.boot.WebApplicationType` alongside `CliApplication` in the project. `spring.main.*` properties from external configuration can override the corresponding API values, so check which config sources are effective.

**Do not equate `server.port=-1` with `WebApplicationType.NONE`:** setting `server.port=-1` may disable the HTTP connector while still creating a web application context in a Servlet application. `WebApplicationType.NONE` is the right choice when the intent is a **non-web** application.

## 3. Where Should Tasks Run? ApplicationRunner and CommandLineRunner

`main()` should only bootstrap Spring. Place logic that needs to run **after beans are created and injected** inside a bean implementing one of these two interfaces:

| Interface | `run` Parameter | When to Use |
| --- | --- | --- |
| `CommandLineRunner` | `run(String... args)`, raw argument array | Simple logic, custom argument parsing, or no complex options needed |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Need to distinguish `--option=value` from positional arguments, reading options by name |

Both are called by Spring Boot after `ApplicationContext` refreshes successfully, before the `SpringApplication.run(...)` call completes. If there are multiple runners, you can control their order using `@Order` or `Ordered`. Avoid relying on classpath scan order.

Startup flow for a CLI:

~~~text
JVM -> CliApplication.main(args)
    -> SpringApplication.run(CliApplication.class, args)
       -> read Environment/profiles/properties
       -> create non-web ApplicationContext
       -> scan components and create beans
       -> inject dependencies into runners
       -> invoke ApplicationRunner/CommandLineRunner
    -> run(...) returns ConfigurableApplicationContext
    -> close context, return exit code to OS
~~~

Spring Boot can still initialize database connections or other resources if application dependencies and configuration require them. Disabling the web server **does not automatically disable** those components.

## 4. Complete Runnable Maven Project

The following example uses **Java 17+**, **Maven**, and Spring Boot **3.3.13**. To avoid pulling in web dependencies, the project declares only the base `spring-boot-starter`. All files below can be created inside a `cli-demo` project directory. Before running, install a compatible JDK and Maven; verify with `java -version` and `mvn -version`.

Project structure:

~~~text
cli-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/cli/
   │  ├─ CliApplication.java
   │  ├─ GreetingService.java
   │  └─ GreetingRunner.java
   └─ resources/
      └─ application.properties
~~~

### 4.1. `pom.xml`: base starter, no Spring Web

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>cli-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

`spring-boot-starter` provides the foundational components to bootstrap Spring Boot, auto-configuration, and logging. Omitting the web starter avoids pulling in a web server solely because the application needs Spring. The Maven plugin packages the JAR to run via `java -jar`.

### 4.2. `application.properties`: force non-web execution

**File `src/main/resources/application.properties`:**

~~~properties
spring.application.name=cli-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
~~~

`web-application-type=none` is the most important setting. `banner-mode=off` only hides the banner to keep output concise; it has no effect on enabling/disabling a web server. Spring Boot may still emit normal startup logs.

### 4.3. Main Class `CliApplication.java`

**File `src/main/java/com/example/cli/CliApplication.java`:**

~~~java
package com.example.cli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CliApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(CliApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
~~~

The class annotated with `@SpringBootApplication` sits in the root package `com.example.cli`, so components in the same package or subpackages can be scanned. `SpringApplication.run(...)` initializes the Spring context, injects beans, and runs runners. Only **after runners finish successfully** does `run(...)` return the context to `main()`.

`SpringApplication.exit(context)` closes the context and collects the exit code from registered `ExitCodeGenerator` beans (if any). `System.exit(exitCode)` terminates the JVM with that code so scripts, terminals, or schedulers receive the result. For a very simple CLI program with no threads keeping the JVM alive, you can let the JVM exit naturally; being explicit here illustrates job lifecycle and exit codes.

### 4.4. Business Logic `GreetingService.java`

**File `src/main/java/com/example/cli/GreetingService.java`:**

~~~java
package com.example.cli;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`@Service` registers the business bean; there is no need to instantiate `GreetingService` manually from `main()`. In a real application, the service might process data or call external systems; separating it from the runner keeps logic testable and reusable.

### 4.5. CLI Task `GreetingRunner.java`

**File `src/main/java/com/example/cli/GreetingRunner.java`:**

~~~java
package com.example.cli;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class GreetingRunner implements ApplicationRunner {

    private final GreetingService greetingService;

    public GreetingRunner(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @Override
    public void run(ApplicationArguments args) {
        String name = optionOrDefault(args, "name", "friend");
        String repeatText = optionOrDefault(args, "repeat", "1");

        int repeat;
        try {
            repeat = Integer.parseInt(repeatText);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "--repeat must be an integer", ex);
        }

        if (repeat < 1 || repeat > 10) {
            throw new IllegalArgumentException(
                    "--repeat must be between 1 and 10");
        }

        for (int i = 0; i < repeat; i++) {
            System.out.println(greetingService.greet(name));
        }
        System.out.println("Printed " + repeat + " greeting(s).");
    }

    private static String optionOrDefault(
            ApplicationArguments args, String name, String defaultValue) {
        List<String> values = args.getOptionValues(name);

        if (values == null) {
            return defaultValue;
        }
        if (values.size() != 1 || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "--" + name + " requires exactly one non-empty value");
        }
        return values.get(0);
    }
}
~~~

**Explanation:**

- `@Component` lets Spring manage the runner. Spring creates `GreetingService` and passes it via constructor injection; do not use `new GreetingService()`.
- `ApplicationArguments.getOptionValues("name")` reads `--name=Lan`. When the option is absent, the API returns `null`; the example defaults to `friend`. When a user passes `--name` without a value or specifies a blank value, the program reports a clear error.
- `--repeat=N` requires an integer from 1 to 10; the bound prevents a mistyped invocation from printing an excessive amount of output.
- Centralizing option parsing in one helper makes input rules easy to extend and verify.
- When the runner throws an exception, `SpringApplication.run(...)` treats startup as failed; `SpringApplication.exit(context)` in the example's `main()` is only reached on the successful path.

This is a complete program: every `public` class has a matching filename, all imports are declared, and no controller, `@EnableWebMvc`, or HTTP server configuration is required.

## 5. Compile and Run

Open a terminal in the directory containing `pom.xml`, compile, and package with:

~~~bash
mvn clean package
~~~

Maven builds the executable JAR `target/cli-demo-1.0.0.jar` upon successful build (the name comes from `artifactId` and `version` in `pom.xml` above).

Run:

~~~bash
java -jar target/cli-demo-1.0.0.jar --name=Lan --repeat=2
~~~

**Lines printed to stdout by application code, in exact order:**

~~~text
Hello, Lan!
Hello, Lan!
Printed 2 greeting(s).
~~~

Spring Boot may print additional startup or error logs depending on configuration; the three lines above are the exact output produced by `GreetingRunner`. The application completes its work and the JVM exits with code `0` on success. No Tomcat/Jetty/Netty web server is started by this configuration.

Run without passing options:

~~~bash
java -jar target/cli-demo-1.0.0.jar
~~~

Lines printed by the runner:

~~~text
Hello, friend!
Printed 1 greeting(s).
~~~

You can also use Maven to run without building the JAR:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments="--name=Mai --repeat=3"
~~~

If shells handle quoting differently, packaging and running `java -jar` as shown above passes arguments more predictably. On Windows with the Maven Wrapper from Spring Initializr, use `.\mvnw.cmd`; on Linux/macOS use `./mvnw`, if the project has the wrapper.

**Test invalid input cases:**

~~~bash
java -jar target/cli-demo-1.0.0.jar --repeat=0
java -jar target/cli-demo-1.0.0.jar --repeat=abc
java -jar target/cli-demo-1.0.0.jar --name=
~~~

The runner reports a range error, a number format error, and an empty-value error respectively. Startup fails so no completion summary is printed, and a scheduler should not treat it as a successful run. When diagnosing errors, inspect the stack trace / failure analysis to locate the offending argument.

## 6. Command-Line Arguments, Configuration, and Value Sources

Distinguish three common categories:

| Kind | Example | How to Use |
| --- | --- | --- |
| Application option | `--name=Lan`, `--repeat=2` | Read via `ApplicationArguments.getOptionValues(...)`; Spring Boot also exposes eligible options in `Environment`. |
| Positional argument | `input.csv` | Read via `ApplicationArguments.getNonOptionArgs()` or the raw array of `CommandLineRunner`. |
| Java system property | `-Dfile.encoding=UTF-8` | Pass **before** `-jar`: `java -Dfile.encoding=UTF-8 -jar ...`; query via corresponding config APIs. |

With Spring Boot, `--spring.profiles.active=dev` can also select the `dev` profile, and `--logging.level.root=INFO` can change the logging level, subject to property source precedence rules. Those are framework configuration options; the demo program itself only handles `name` and `repeat`.

If you need to turn a positional argument into a file path, validate file existence, permissions, encoding, and output target before processing. Never assume user-supplied strings are always valid paths or stay within the intended directory.

### When to Use CommandLineRunner?

If you only need a string array, you can replace `GreetingRunner` with a `CommandLineRunner`:

~~~java
@Bean
CommandLineRunner quickTask(GreetingService service) {
    return args -> System.out.println(service.greet("CLI"));
}
~~~

This is an **illustrative bean declaration** placed in a Spring configuration class importing `org.springframework.context.annotation.Bean` and `org.springframework.boot.CommandLineRunner`; `GreetingService` is the class from section 4. If you add this bean alongside `GreetingRunner`, both runners will execute. When switching approaches, remove the old runner or coordinate order explicitly. When parsing `--option=value`, `ApplicationRunner` is usually cleaner.

## 7. Application Termination, Resources, and Exit Codes

A good CLI needs a clear completion point and must report the right result to the shell or scheduler.

- **Normal completion:** runners finish and `SpringApplication.run(...)` returns. In the example, `SpringApplication.exit(context)` closes the Spring context and `System.exit(0)` terminates the process when no `ExitCodeGenerator` signals an error.
- **Error in runner:** an exception fails startup, Boot logs the error, and cleans up the context via its startup failure flow. Let errors be surfaced; do not swallow exceptions and claim the job succeeded.
- **Spring-managed resources:** beans with `@PreDestroy` or `DisposableBean` callbacks are handled when the context closes. For file streams, transactions, or resources opened manually outside Spring, still use `try-with-resources`/proper cleanup.
- **Background threads:** schedulers, connection managers, or application-created threads can prevent the JVM from exiting even after `run(...)` returns. Do not use infinite schedulers for a finite job meant to exit. `System.exit` terminates the process, so place it after resource cleanup and only when you truly want to terminate the JVM.
- **Exit codes:** the operating system uses `0` for success; non-zero values usually indicate failure. You can use `ExitCodeGenerator` with `SpringApplication.exit(...)` to supply specific exit codes from the application.

Example bean returning an exit code:

~~~java
@Bean
ExitCodeGenerator customExitCode() {
    return () -> 0;
}
~~~

This snippet only illustrates a bean inside a Spring configuration class, requiring imports for `org.springframework.context.annotation.Bean` and `org.springframework.boot.ExitCodeGenerator`. There is no need to add a bean that always returns `0` to the main program: when no error occurs, `SpringApplication.exit(...)` can already return `0` by default. In practice, use `ExitCodeGenerator` to convey specific business outcomes that can be inspected from the shell.

**Testing note:** do not call `System.exit(...)` indiscriminately inside services or runners because it terminates the entire JVM running your tests. Keep exit-code termination responsibility at the `main()` entry point, and test business logic and argument parsers independently.

## 8. No HTTP Server Needed, Yet Sound Spring Architecture Still Matters

Place `@SpringBootApplication` at the root package of the module, for example:

~~~text
com.example.cli
├─ CliApplication
├─ GreetingRunner
└─ GreetingService
~~~

Thanks to default component scanning, the runner and service are created under Spring management. If you place them in sibling packages outside the scan scope or forget `@Component`/`@Service`, bean injection errors will typically occur. Do not widen scanning to the entire classpath just to fix a missing bean.

A CLI **can still** use JDBC, JPA, transactions, validation, HTTP clients, messaging, configuration properties, and DI. Add appropriate dependencies according to task needs. However, each dependency can trigger auto-configuration, open connections, or require extra properties. If a database connection failure prevents the CLI from starting, do not blame `WebApplicationType.NONE`.

**For long-running or background jobs:** `ApplicationRunner` fits one-shot startup/execution workflows. If you need retries, restarts, checkpoints, large chunk processing, or multi-step tracking, consider a dedicated batch framework such as Spring Batch. If you want to keep an HTTP API to trigger jobs remotely, that is a web architecture requirement outside the scope of this CLI pattern.

## 9. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Logs still show a web server running | `spring.main.web-application-type=none` was not loaded or was overridden by a higher-precedence config source | Check the actual `application.properties` in classpath/JAR, profiles, environment variables, and `spring.main.*` arguments |
| HTTP port is not opened, yet context is still a web context | Only `server.port=-1` was set | Use `spring.main.web-application-type=none` to switch to a non-web context |
| No output line from runner | Runner lacks `@Component`/`@Bean`, lies outside scan region, or an error occurred before runners ran | Check packages, bean definitions, and the first error cause in logs |
| `No qualifying bean` when injecting service | Missing `@Service`/`@Bean` or wrong package | Place bean in scan scope, declare bean properly |
| Process does not exit on its own | Non-daemon threads, schedulers, held resources, or tasks still running | Inspect thread dump, lifecycle, stop background tasks, and close context properly |
| Input `--repeat=abc` fails the application | Value is not an integer | Check option validation and CLI usage instructions |
| `java -jar` reports missing main manifest or dependencies | Plain JAR was not packaged by the Spring Boot plugin into an executable archive | Check `spring-boot-maven-plugin`, `mvn package`, and the actual JAR file |
| Expected to open `localhost:8080` but cannot connect | Running a non-web app, so there is no HTTP endpoint | This is expected behavior with `NONE`; check stdout/exit code instead of a browser |

Do not judge a CLI's health by "whether port 8080 is open" like a web service. Meaningful signals are **exit code, logs, output content, processed record count, and task outcome**.

## 10. Production Operations and Testing

For automated jobs, you should:

1. **Validate inputs explicitly:** define required options, default values, bounds, and error messages. If accepting files or passwords, avoid logging sensitive data.
2. **Keep tasks testable:** the runner should only coordinate input/output and invoke services; separate processing logic from `main()` and framework classes.
3. **Handle errors properly:** do not catch every `Exception` and print `Done`; let the job fail with an appropriate exit code, even when invoked by cron or CI.
4. **Close resources:** prefer Spring-managed beans, close files/streams with `try-with-resources`, and wrap data changes in transactions.
5. **Consider re-entrancy:** a job may be retried by a scheduler after failure; avoid writing duplicate data and consider idempotency and checkpoints for large workloads.
6. **Monitor completion time:** a healthy CLI job is not an endless daemon; for long tasks, add milestone logs and appropriate metrics.

Manually test at least three scenarios on the section 4 project:

- **No options passed:** runner prints the default greeting and exits with code `0`.
- **`--name=Lan --repeat=2`:** prints exactly two greetings for Lan followed by a summary line; does not start an HTTP server.
- **`--repeat=0` or `--repeat=abc`:** application reports an error before finishing the task; verify the scheduler or script sees a failure status.

In Bash/Linux shells, you can read the exit code of the previous command with `echo $?`; in PowerShell, inspect `$LASTEXITCODE` after running `java -jar`. Do not confuse another command's exit code with the JVM result: check immediately after the Java command.

## 11. Practice Exercises

**Exercise 1:** Replace `GreetingService` with `ReportService` generating a report from a fixed dataset, accepting `--format=text`. Ensure option parsing lives in the runner and report generation lives in the service.

**Exercise 2:** Add `--repeat=4` and use `@Order` to define order if creating two runners. Observe what happens without order control and explain why classpath order should not be relied upon.

**Exercise 3:** Temporarily add a suitable web dependency in Maven and verify whether `spring.main.web-application-type=none` still prevents the web server from starting. Then remove only the `none` property to observe the difference in auto-detection. Do this only in a learning environment, never alter production config arbitrarily.

**Self-check questions:**

1. Do you have to add `spring-boot-starter-web` to run `@SpringBootApplication`? **No**. The base starter is sufficient for the CLI example.
2. Why not run business logic directly before `SpringApplication.run()`? Because beans, dependency injection, and runtime configuration may not be initialized yet.
3. How does `ApplicationRunner` differ from `CommandLineRunner`? Mainly in how arguments are received: parsed `ApplicationArguments` options vs a raw `String[]` array.
4. Does `server.port=-1` replace `WebApplicationType.NONE`? **No**, because it does not guarantee a non-web context is used.
5. Why should a CLI have a clear exit code? Because shells, CI, cron, and orchestrators need to know whether the job succeeded or failed to decide next steps.

## 12. Takeaways and References

A Spring Boot CLI application still starts with `@SpringBootApplication` and `SpringApplication.run()`, but uses **`WebApplicationType.NONE`** to omit the web runtime. Place the task in an `ApplicationRunner` or `CommandLineRunner`, parse arguments cleanly, use Spring beans for business logic, close the context upon completion, and return the proper exit code. That is the right model for command-line tools and finite jobs.

Official documentation:

- Spring Boot — SpringApplication, runners, application arguments, application exit: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot — Disabling the Web Server: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot — Properties and Configuration: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Spring Boot — Starters and build systems: https://docs.spring.io/spring-boot/reference/using/build-systems.html
