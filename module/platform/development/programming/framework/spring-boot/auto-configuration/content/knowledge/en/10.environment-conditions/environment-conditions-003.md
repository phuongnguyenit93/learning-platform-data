# `@ConditionalOnNotWebApplication`: Activating Configuration Only When the Application Has No Web Context

## 1. Problem to Solve

A Spring Boot library can serve **both web applications** (REST API, MVC, WebFlux) and **applications without a web context** (CLI, data processing pipelines, workers, consumers, batch jobs). These applications may share many services, yet not every bean is suitable for both environments.

For example, a starter may provide a `CommandJob` specifically for command-line programs. If this bean is registered in a REST API, configuring CLI-mode handling may be unnecessary or even produce unexpected behavior. Spring Boot provides the annotation:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
```

`@ConditionalOnNotWebApplication` is an **auto-configuration condition**: it only allows Spring to register a configuration or bean when the current application **is not detected as a web application context**.

Key implications:

- **Condition matches:** the annotated configuration/bean is allowed to be registered when the context is neither a Servlet web context nor a Reactive web context.
- **Condition does not match:** the annotated configuration/bean is not registered in a web application detected as Servlet or Reactive.
- Evaluation occurs **while creating the ApplicationContext and processing bean definitions**. The annotation does not inspect individual HTTP requests and does not continuously change its result after the application has started.
- The annotation **only controls registration**; it does not run batches automatically, does not schedule tasks, and does not prevent the application from making **outbound** HTTP requests.

This is a **Spring Boot** annotation in the `org.springframework.boot.autoconfigure.condition` package, not a core Spring Framework annotation.

## 2. What Does “No Web Context” Mean?

### 2.1. Three common application types

Spring Boot uses `WebApplicationType` to represent the type of application created by `SpringApplication`:

| `WebApplicationType` | Typical ApplicationContext | Meaning for `@ConditionalOnNotWebApplication` |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | **Matches**: the application does not run with a web context |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | **Does not match**: Servlet web application |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | **Does not match**: Reactive web application |

The class names in the table are the typical context types when running standard Boot applications. In complex applications or custom contexts, Spring Boot's web condition also inspects web characteristics of the `ApplicationContext`/`Environment` (such as Servlet `WebApplicationContext` or Reactive `ReactiveWebApplicationContext`). Therefore, conceptually you should understand it as **whether Spring recognizes the context as having web characteristics**, rather than merely comparing a configuration string.

### 2.2. Classpath and web context are not synonymous

The presence of a web library in dependencies can influence the application type inferred by Boot, but **does not mean the application is forced to run as a web app**.

For example, an application has `spring-boot-starter-web` but starts with:

```properties
spring.main.web-application-type=none
```

then Boot creates a non-web context and does not start an embedded HTTP server. `@ConditionalOnNotWebApplication` can match even though Spring MVC/Tomcat libraries are still on the classpath.

Conversely, simply **not declaring `@RestController`** does not turn a `SERVLET` application into `NONE`. If the application still has a Servlet web context, the condition **does not match**.

It is also important to distinguish:

- `server.port=0`: the web application still runs, just using a **random port**; the non-web condition **does not match**.
- `server.port=-1` (in Boot configurations that support it): may disable HTTP listening, but **does not necessarily change the ApplicationContext type to non-web**; you should not use it to trigger this condition.
- `spring.main.web-application-type=none`: tells Boot to start in non-web mode, which is the clearest way when you want to keep web dependencies without creating a web context.
- A CLI can still use `RestClient`/`WebClient` to call external APIs; **sending HTTP requests** does not automatically turn it into a web server application.

### 2.3. Comparison with related annotations

| Annotation | Condition checked | When to use |
| --- | --- | --- |
| `@ConditionalOnNotWebApplication` | Application **has no web context** | Only create beans supporting non-web CLI/worker/batch |
| `@ConditionalOnWebApplication` | Application **has a web context**; can restrict to `SERVLET` or `REACTIVE` | Beans for servlet filters, web handlers, web-specific integrations |
| `@ConditionalOnClass` | A class is on the classpath | Configure only if the dependency is present |
| `@ConditionalOnProperty` | Configuration property satisfies condition | Toggle features via configuration flags |
| `@ConditionalOnMissingBean` | No matching bean is registered yet | Allow applications to **override a default bean** |
| `@Profile` | Active profile | Split configurations by environment/profile |

`@ConditionalOnNotWebApplication` and `@ConditionalOnClass` do not replace each other: one checks **runtime context characteristics**, while the other checks **libraries**. It also needs no `type = SERVLET` or `type = REACTIVE` argument; type restriction belongs to `@ConditionalOnWebApplication`, whereas `@ConditionalOnNotWebApplication` is designed for the **general non-web** case.

## 3. Placing the Annotation on a Class or on a `@Bean` Method?

### 3.1. Class-level condition: the entire configuration group is non-web only

```java
@AutoConfiguration
@ConditionalOnNotWebApplication
public class CliJobAutoConfiguration {

    @Bean
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }

    @Bean
    public CliJobSettings cliJobSettings() {
        return new CliJobSettings(5);
    }
}
```

This is an **illustrative snippet**, assuming the two types `CommandJob` and `CliJobSettings` are already declared. If the application uses a web context, Spring **skips the entire `CliJobAutoConfiguration`**: neither bean is provided from this class.

Choose class-level placement when **the entire group of beans only makes sense in a program without a web context**.

### 3.2. Condition on individual `@Bean`: only one bean is non-web specific

```java
@AutoConfiguration
public class SharedAutoConfiguration {

    @Bean
    @ConditionalOnNotWebApplication
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

This is also an **illustrative snippet** with `CommandJob` already declared. In a web application, the `applicationClock` bean is still provided; only `commandJob` is skipped. In a non-web application, both can be registered.

Choose method-level placement when the same auto-configuration contains both **shared beans** and **non-web-only beans**. Do not place the condition on the whole class if you need to retain the shared beans.

### 3.3. Combining with back-off mechanisms

In a shared starter, we often need two requirements simultaneously:

1. Only provide the default `CommandJob` in **non-web applications**.
2. If the user has already defined a custom `CommandJob`, the default must **back off**.

Two annotations address two different axes:

```java
@Bean
@ConditionalOnNotWebApplication
@ConditionalOnMissingBean(CommandJob.class)
public CommandJob commandJob() {
    return new CommandJob("daily-import");
}
```

The default bean is only registered when **both** there is no web context **and** no matching `CommandJob` bean exists yet. The non-web condition does not mean Spring Boot will automatically back off when a user-declared bean is present; to back off, you must declare the corresponding rule.

## 4. Runnable Spring Boot 3.3.x / Java 17+ Example

We will build a small program with **`spring-boot-starter-web` on the classpath** to compare two startup modes using the **exact same JAR**:

- Normal run: Boot creates a Servlet web context, and `@ConditionalOnNotWebApplication` **does not match**.
- Run with `--spring.main.web-application-type=none`: Boot creates a non-web context, and the annotation **matches**.

The example places `@ConditionalOnNotWebApplication` on the **auto-configuration class**, while placing `@ConditionalOnMissingBean` on the default bean. The auto-configuration class sits outside the component scan package and is registered via `AutoConfiguration.imports` following Spring Boot 3.x standards.

### 4.1. Project structure

```text
non-web-condition-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/CommandJob.java
    │       ├── app/DemoApplication.java
    │       └── autoconfigure/CliJobAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>non-web-condition-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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
```

Using `spring-boot-starter-web` is **intentional**: because of it, unless configured otherwise, Spring Boot chooses the Servlet web type. The goal is to prove the condition relies on the **running context**, not merely the presence or absence of web libraries.

### 4.3. `src/main/java/demo/api/CommandJob.java`

```java
package demo.api;

public record CommandJob(String name) {

    public String runOnce() {
        return "ran:" + name;
    }
}
```

`CommandJob` is a bean illustrating a CLI task. The `runOnce()` method does not run automatically when the bean is created; `main()` calls it so the example produces deterministic output.

### 4.4. `src/main/java/demo/autoconfigure/CliJobAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.CommandJob;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnNotWebApplication
public class CliJobAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CommandJob.class)
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }
}
```

**The two conditions have distinct roles:**

- Class level: if the application has a web context, the entire auto-configuration is excluded.
- `@Bean` level: in a non-web context, the default `CommandJob` only appears if the application has not already provided a matching bean of the same type.

### 4.5. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
demo.autoconfigure.CliJobAutoConfiguration
```

Spring Boot 3.x reads this file to know the list of auto-configuration classes. Each line in the file must match the **fully-qualified class name**. Do not place `CliJobAutoConfiguration` in a package scanned by `@SpringBootApplication`: auto-configurations should be loaded via imports to ensure predictable ordering and application rules.

### 4.6. `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.CommandJob;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            CommandJob job = context.getBeanProvider(CommandJob.class)
                    .getIfAvailable();

            System.out.println("commandJobExists=" + (job != null));

            if (job != null) {
                System.out.println(job.runOnce());
            }
        }
    }
}
```

`main()` checks for the existence of `CommandJob` and invokes the task **only if the bean is registered**. `try-with-resources` closes the context immediately after the demonstration finishes, so even the web mode with an embedded server exits instead of continuing to listen for HTTP.

### 4.7. Build once, run two modes

Requires **JDK 17+** and **Maven 3.6+**. In the `non-web-condition-demo` directory, build:

```bash
mvn -q -DskipTests package
```

**Run A — Servlet web context** (chosen by default due to `spring-boot-starter-web`):

```bash
java -jar target/non-web-condition-demo-0.0.1-SNAPSHOT.jar --server.port=0 --spring.main.banner-mode=off --logging.level.root=OFF
```

The output line printed by the program:

```text
commandJobExists=false
```

Explanation: Boot initializes a Servlet web context; `CliJobAutoConfiguration` is excluded because `@ConditionalOnNotWebApplication` does not match. `--server.port=0` only tells the web server to use a dynamic port; **the application is still a web application**.

**Run B — non-web context** (same JAR, changed startup mode):

```bash
java -jar target/non-web-condition-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none --spring.main.banner-mode=off --logging.level.root=OFF
```

The output lines printed by the program:

```text
commandJobExists=true
ran:daily-import
```

Explanation: `web-application-type=none` makes Boot use a non-web context. The condition on `CliJobAutoConfiguration` matches, the default `CommandJob` is registered, and the `runOnce()` method can run.

**What this proves:** two runs use the **same artifact with the same dependencies**, yet the condition outcome differs because the **ApplicationContext type** changes. This is the core difference from purely classpath-based conditions like `@ConditionalOnClass`.

### 4.8. Trying the variant with the condition on `@Bean`

If a configuration has a bean shared between web and non-web, move `@ConditionalOnNotWebApplication` from the **class** down to the `commandJob()` method specifically:

```java
package demo.autoconfigure;

import demo.api.CommandJob;
import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CliJobAutoConfiguration {

    @Bean
    @ConditionalOnNotWebApplication
    @ConditionalOnMissingBean(CommandJob.class)
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

This is a **complete replacement class** for `CliJobAutoConfiguration.java` in the example above. After rebuilding, both runs still produce the same `CommandJob` outputs as before. The difference is that `applicationClock` is registered in **both modes** because only `commandJob()` carries the non-web condition.

## 5. How to Apply in a Real Starter or Application

**Scenario 1 — starter used for both batch and REST API.** The library has a shared `SharedClient` and a CLI-only `CliJobRunner`:

```java
@AutoConfiguration
public class SharedClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SharedClient sharedClient() {
        return new SharedClient();
    }

    @Bean
    @ConditionalOnNotWebApplication
    @ConditionalOnMissingBean
    CliJobRunner cliJobRunner() {
        return new CliJobRunner();
    }
}
```

*This snippet is illustrative for design; `SharedClient` and `CliJobRunner` are hypothetical types not defined in the runnable example.* The condition must be placed on the `cliJobRunner()` method so that web apps still receive the `SharedClient` bean. If placed on the entire class, web apps lose the shared client as well.

**Scenario 2 — an entire configuration dedicated to a worker.** A group of beans such as a file reader, CLI parser, and data import task only make sense in a non-web context. Place `@ConditionalOnNotWebApplication` on a standalone `@AutoConfiguration` to maintain a clear boundary.

**Scenario 3 — a task that also needs to run inside a REST API.** Do not use the non-web condition just because a component runs in the background or does not use the Servlet API. Scheduled tasks, queue consumers, and batch jobs **can still run inside a web application**. If the actual requirement is flag-based toggling, use `@ConditionalOnProperty` (and, if needed, `@ConditionalOnMissingBean`) instead of inferring intent from the web context type.

**Scenario 4 — needing to separate two entry points.** A REST API and a worker can live in the same codebase while needing different configurations/startup entry points. You can use `spring.main.web-application-type=none` for the worker process, while still managing dependencies, configs, auto-running jobs, and lifecycle clearly. The annotation does not define deployment structure or guarantee the worker runs only once.

## 6. Debugging When the Condition Does Not Behave as Expected

When a bean does not appear, do not immediately conclude that `@ConditionalOnNotWebApplication` is broken. Check in this order:

1. **Determine the actual context:** is the application running `NONE`, `SERVLET`, or `REACTIVE`? Are `spring-boot-starter-web`/`spring-boot-starter-webflux` present and is `spring.main.web-application-type` forced?
2. **Verify the auto-configuration class is loaded:** for a starter, is the class name exact in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`? Is the auto-configuration package accidentally being component-scanned?
3. **Check remaining conditions:** `@ConditionalOnMissingBean` might be making the default back off; `@ConditionalOnProperty` or `@ConditionalOnClass` might not match; all applied conditions must be satisfied simultaneously.
4. **Inspect the Condition Evaluation Report:** add `--debug` when running, or enable auto-configuration-related logging. The report shows which conditions matched/did not match and why; exact messages depend on the Spring Boot version.
5. **Check the annotation placement level:** if attached to the class, all beans in the class depend on the condition. If attached only to a method, other beans in the class can still be registered.
6. **Check the test context:** a unit test using `ApplicationContextRunner` typically creates a non-web context, so the bean may appear there while missing in a real Servlet app. Tests must simulate the **right context type**.

You can verify against this target matrix:

| Scenario | Expected result for default `CommandJob` |
| --- | --- |
| Non-web context, no user `CommandJob` | Default bean is present |
| Non-web context, user `CommandJob` already exists | Default not created due to `@ConditionalOnMissingBean` |
| Servlet web context, no user `CommandJob` | Default not created |
| Reactive web context, no user `CommandJob` | Default not created |
| Spring MVC on classpath but `web-application-type=none` forced | Default present unless excluded by another condition |

In an auto-configuration test suite, use `ApplicationContextRunner` for the non-web case; for web cases, use the appropriate context runner such as `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`. Tests should verify both the **presence** and **absence** of beans, rather than merely checking that the application starts successfully.

## 7. Common Misconceptions

**Misconception 1 — “No controllers means non-web.”** False: a web application without any declared controller still has a Servlet/Reactive web context. The context's characteristics are what matter.

**Misconception 2 — “Having `spring-boot-starter-web` means the condition is always false.”** Not necessarily: if `web-application-type=none` is configured, the context can be non-web even while the dependency remains present.

**Misconception 3 — “Setting `server.port=0` makes it non-web.”** False: a random port does not remove the web context. To use non-web mode, set `spring.main.web-application-type=none`.

**Misconception 4 — “Non-web means no HTTP calls allowed.”** False: a CLI worker can use an HTTP client to call other services. The condition concerns the **application context acting as a web server**, not the ability to use the HTTP protocol.

**Misconception 5 — “The annotation will run or block the job itself.”** False: it only allows or disallows Spring to **register the bean**. Execution depends on `CommandLineRunner`, `ApplicationRunner`, schedulers, listeners, or business calls; you must design job lifecycle and idempotency separately.

**Misconception 6 — “The condition removes user-declared beans.”** False: a condition on an auto-configuration only controls the configuration/bean carrying that condition; it never deletes beans declared by the application. To provide an overridable default, combine with `@ConditionalOnMissingBean`.

**Misconception 7 — “I can use the non-web condition to distinguish Servlet from Reactive.”** False: this annotation excludes **both web types**. If you want configuration specific to Servlet or Reactive, use `@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)` or `REACTIVE` respectively.

**Misconception 8 — “Always put the condition on the whole class to keep it tidy.”** If the class also holds shared beans, web apps will lose those beans too. Place the condition on `@Bean` to scope it accurately.

## 8. Key Takeaways and Self-Check Questions

- `@ConditionalOnNotWebApplication`: **matches in a non-web context**, does not match in a Servlet/Reactive web context.
- `spring.main.web-application-type=none` is the explicit way to force a Boot program to run non-web, even when web dependencies are present.
- An annotation on a **class** affects the entire configuration; on a **`@Bean`** it affects only the marked bean.
- This is a **startup bean-registration** condition, not a tool for scheduling, orchestrating jobs, or inspecting HTTP requests.
- When providing a default bean in a starter, usually combine with `@ConditionalOnMissingBean` so users can replace it.

**Self-check:**

1. An application has `spring-boot-starter-web`, no controllers, and runs with defaults. Does `@ConditionalOnNotWebApplication` match? **No**: Boot still creates a Servlet web context.
2. Keep the same JAR but add `--spring.main.web-application-type=none`. Does it match? **Yes**, unless another condition blocks the configuration.
3. An `@AutoConfiguration` has a shared bean A and a CLI-only bean B. Where should the condition go? **On the `@Bean` creating B**, so A continues to work in web apps.
4. If the user has already created their own B, does `@ConditionalOnNotWebApplication` alone make default B back off? **No**; `@ConditionalOnMissingBean` or an equivalent rule is needed.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Web Application Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): how to use web conditions, bean conditions, and `AutoConfiguration.imports`.
- [Spring Boot 3.3 — WebApplicationType API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html): meaning of `NONE`, `SERVLET`, and `REACTIVE`.
- [Spring Boot 3.3 — ConditionalOnNotWebApplication API](https://docs.spring.io/spring-boot/3.3.13/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnNotWebApplication.html): annotation that only matches when the ApplicationContext is not a web context.
