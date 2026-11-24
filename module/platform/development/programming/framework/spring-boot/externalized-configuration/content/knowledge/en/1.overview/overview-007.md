# Spring Boot 3.3 Scope and Required Java & IoC Background

## 1. Why Study This Lesson?

An application often has to run in multiple places: developer workstations, testing environments, production servers, and automated deployment systems. The source code may remain identical, while database addresses, network ports, timeouts, log levels, and credentials differ. If all values are hard-coded in Java, every environment transition risks code edits, repackaging, and re-releasing.

**Externalized Configuration** (separating configuration from application code) is how Spring Boot accepts values from multiple sources outside Java classes, selects effective values by precedence rules, and delivers them to running components. This lesson introduces the scope of knowledge for **Spring Boot 3.3** and prepares the **Java, IoC, and DI** fundamentals needed to understand that mechanism.

After this lesson, you should be able to picture:

- Why the same JAR file can run with different configurations across environments.
- The difference between a **configuration source**, a **configuration value**, a **configuration object**, and a **Spring bean consuming configuration**.
- Which parts of Java and Spring IoC you must know before using `@Value`, `Environment`, or `@ConfigurationProperties`.
- How to run a small example to observe configuration being read, overridden, and delivered to a bean.

This is an orientation lesson. In-depth rules such as the complete precedence order of all sources, importing additional files, multi-document YAML configuration, and handling complex deployment scenarios will be covered in dedicated lessons.

## 2. Version Scope: Spring Boot 3.3

Examples and explanations in this material use **Spring Boot 3.3.x** as the baseline. When practicing on your own, choose a patch release from the 3.3 line and keep library versions aligned with Spring Boot dependency management.

| Component | Baseline Assumption | Meaning in Practice |
| --- | --- | --- |
| Spring Boot | 3.3.x branch | Uses Spring Boot 3.3 configuration and property binding mechanisms. |
| Java | **Java 17 or higher** | Java 17 is the minimum for Spring Boot 3.3; examples use Java 17 syntax. |
| Spring Framework | IoC foundation and `ApplicationContext` bundled with Spring Boot 3.3 | Spring creates and manages beans, then passes configuration into beans that need it. |
| Packaging | Spring Boot app run as a JAR or from the build tool | Enables changing command-line arguments and environment variables at startup. |
| Configuration syntax | `.properties`, `.yaml`/`.yml` | Two common formats for representing configuration data; no need to learn a Java-only format. |
| Related APIs | `Environment`, `@Value`, `@ConfigurationProperties` | Three common entry points for reading or consuming configuration. |

Spring Boot 3 uses the **Jakarta** ecosystem for APIs migrated from `javax.*`. For instance, when validating configuration objects with Bean Validation, annotations like `@NotBlank` live in `jakarta.validation.constraints`, not `javax.validation.constraints`. Keep this in mind when reading older Spring Boot 2 examples.

**Within the scope of this Externalized Configuration module**, you need to master:

1. Data sources: `application.properties`, `application.yml`, profile-specific files, environment variables, JVM properties, and command-line arguments.
2. How Spring Boot merges sources into lookup-ready properties and how higher-precedence sources override lower ones.
3. Key naming, type conversion, default values, and binding groups of keys into Java classes.
4. The role of profiles, configuration validation, and distinguishing regular configuration from secrets.
5. How to inspect the values actually used by the application at startup.

**Outside the scope of this introduction** are operating remote config servers, automated secret distribution with dedicated infrastructure, Kubernetes config orchestration, refreshing beans dynamically when configuration changes, and building custom property loaders. Those topics are related, yet unnecessary for understanding Spring Boot's core model.

## 3. Mental Model: Where Does Configuration Come From and Go To?

Separate four concepts:

- **Property source:** a place holding key–value pairs, such as a file, environment variable, or startup argument.
- **Property key:** a logical name such as `app.greeting`, `server.port`, or `logging.level.root`.
- **Configuration environment (`Environment`):** Spring's interface for looking up effective values across ordered sources.
- **Bean receiving configuration:** a Spring-managed object, which can receive a single value via `@Value` or an entire group via `@ConfigurationProperties`.

Overview path:

```text
application.properties / application.yml
application-dev.properties
environment variables / JVM properties / startup args
                  |
                  v
           PropertySources
                  |
                  v
         Spring Environment
                  |
          +-------+------------------+
          |                          |
          v                          v
  @Value / Environment     Binder + @ConfigurationProperties
          |                          |
          v                          v
   individual values        typed Java configuration object
          |                          |
          +------------+-------------+
                       |
                       v
              Spring-managed bean
                       |
                       v
             application behavior
```

For example, `app.limit=5` in a file can be overridden by a corresponding environment variable or `--app.limit=8`. `Environment` sees the effective value; Spring Boot can convert the string `"8"` into an `int` when binding to a Java object.

**Configuration is not a bean.** A `.properties` file only holds data. A bean is a Java object created and managed by Spring. `@ConfigurationProperties` is the bridge turning a group of values into a typed object, and IoC/DI delivers that object where it is needed.

## 4. Prerequisite Java Knowledge

### 4.1. Classes, Objects, Methods, and Constructors

You should be able to read a Java class, understand constructor parameters, fields, access modifiers, and method calls. DI commonly injects dependencies via **constructors**; without understanding object creation with `new`, it is harder to see what work Spring handles for you.

```java
public final class GreetingService {
    private final String greeting;

    public GreetingService(String greeting) {
        this.greeting = greeting;
    }

    public String message(String name) {
        return greeting + ", " + name;
    }
}

// Plain Java: the caller instantiates and passes arguments manually.
GreetingService service = new GreetingService("Hello");
System.out.println(service.message("Alice"));
```

In Spring, the dependency-passing principle stays the same; the difference is that `ApplicationContext` can take charge of creating and wiring the objects.

### 4.2. Data Types and Type Conversion

Be comfortable with `String`, `int`, `long`, `boolean`, floating-point numbers, `enum`, `List`, `Map`, and common date/time types such as `Duration`. Many configuration sources store values as text; Spring Boot must convert them into the types your program expects.

| Configuration Value | Typical Java Type | What to Know |
| --- | --- | --- |
| `app.name=checkout` | `String` | Text string and how it is used in code. |
| `app.limit=5` | `int` or `Integer` | Converted to an integer; invalid input can cause startup failure. |
| `app.enabled=true` | `boolean` | On/off toggle value. |
| `app.timeout=3s` | `Duration` | Duration with units; avoid confusing seconds with milliseconds. |
| `app.mode=FAST` | `enum` | Fixed set of choices requiring a valid constant name. |

Never assume any arbitrary string can convert to your desired Java type. A mistyped value can trigger a configuration binding failure during bean creation.

### 4.3. Immutability and `record`

Spring Boot 3.3 works cleanly with Java **records** to model immutable configuration data.

```java
public record RetryPolicy(int maxAttempts, Duration delay) {
}
```

A `record` generates the constructor, accessor methods `maxAttempts()` and `delay()`, and standard data methods. When binding configuration via the constructor, Spring Boot supplies values at instantiation time; consumer code does not reassign fields.

Distinguish a Java `record` from a Spring bean: declaring a `record` does not automatically register it into `ApplicationContext`.

### 4.4. Annotations, Packages, and Library Dependencies

You should recognize `@Something` syntax, understand `import` statements, and know that an annotation usually only takes effect when a matching library or processor is present. For example, `@ConfigurationProperties` belongs to Spring Boot; `@Bean` belongs to Spring Framework; `@NotBlank` belongs to Jakarta Validation.

Know how to choose Java 17, create a project via Spring Initializr, add dependencies with Maven/Gradle, and read startup errors in the console. You do not need advanced Java features before learning configuration.

## 5. IoC and DI Concepts You Must Understand

### 5.1. What Is IoC?

**Inversion of Control (IoC)** is the practice of delegating object creation, wiring, and lifecycle management to a container. In a Spring application, this container is accessed through `ApplicationContext`.

Instead of writing `new GreetingService(...)` everywhere yourself, you declare a component so Spring creates the bean and supplies it to other components.

### 5.2. What Is DI?

**Dependency Injection (DI)** is how the objects or values a component needs are delivered to it. A clear, readable form is constructor injection:

```java
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final MessageFormatter formatter;

    public WelcomeService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String welcome(String name) {
        return formatter.format(name);
    }
}
```

The snippet assumes `MessageFormatter` is already registered as a Spring bean. Spring locates the matching bean and passes it into `WelcomeService` during creation. If no matching bean exists, the application can fail during startup.

Core point to remember: **DI solves who supplies dependencies; Externalized Configuration solves where configuration values come from and which one is chosen.** The two mechanisms meet when a bean depends on a configuration object.

### 5.3. How Are Beans Registered?

- `@Component`, `@Service`, and `@Repository` mark component types that can be scanned and instantiated as beans.
- `@Configuration` together with `@Bean` allows explicit programmatic bean creation.
- `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` registers `@ConfigurationProperties` classes using Spring Boot's mechanism.

**Do not confuse `@Configuration` with `@ConfigurationProperties`.** `@Configuration` typically declares bean factory methods; `@ConfigurationProperties` describes how to bind a group of properties into a Java object.

## 6. Minimal Example: Same Java Code, Multiple Configurations

The example below needs only a Spring Boot 3.3.x application, Java 17, and the core `spring-boot-starter` dependency. Use Spring Initializr or an existing Spring Boot project, and place the classes in the same `example.configdemo` package. When packaged, replace `app.jar` with your actual JAR path.

**Step 1 — declare a configuration source.**

`src/main/resources/application.properties`:

```properties
app.greeting=Hello from file
app.limit=3
```

**Step 2 — create a typed configuration object.**

`AppSettings.java`:

```java
package example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppSettings(String greeting, int limit) {
}
```

The keys `app.greeting` and `app.limit` match the two record components. Spring Boot uses constructor binding to construct `AppSettings`. For a record with a single primary constructor as above, `@ConstructorBinding` is not needed.

**Step 3 — register the configuration object and consume it with DI.**

`ConfigDemoApplication.java`:

```java
package example.configdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSettings(AppSettings settings) {
        return args -> System.out.printf(
            "Greeting=%s; limit=%d%n",
            settings.greeting(),
            settings.limit()
        );
    }
}
```

`@ConfigurationPropertiesScan` lets Spring Boot find and register `AppSettings`. When creating `ApplicationRunner`, Spring injects the `AppSettings` bean into the `showSettings(...)` parameter. That is DI: the code does not read files itself and does not call `new AppSettings(...)`.

Running the application with default configuration prints:

```text
Greeting=Hello from file; limit=3
```

**Step 4 — try overriding from startup arguments.**

```bash
java -jar app.jar --app.greeting="Hello from command line" --app.limit=7
```

Expected output:

```text
Greeting=Hello from command line; limit=7
```

`application.properties` did not change. Spring Boot places command-line arguments in a configuration source with higher precedence than the file in this scenario.

**Step 5 — try environment variables.**

On Bash:

```bash
APP_GREETING="Hello from environment variable" java -jar app.jar
```

On PowerShell:

```powershell
$env:APP_GREETING = "Hello from environment variable"
java -jar app.jar
```

Without a `--app.greeting` argument overriding it, the greeting comes from the environment variable. `app.limit` stays `3` from the file. Through Spring Boot's relaxed binding, `APP_GREETING` maps to the `app.greeting` key.

If you run multiple experiments in the same terminal, remember that an exported environment variable can persist across subsequent runs. Unset the variable or open a clean terminal for an accurate comparison.

## 7. Profiles and Precedence: What to Know at the Introductory Level

**Profiles** let you select configuration groups suited to a runtime context. For example, create `src/main/resources/application-dev.properties`:

```properties
app.greeting=Hello from dev profile
```

Then run:

```bash
java -jar app.jar --spring.profiles.active=dev
```

If no higher-precedence source sets `app.greeting`, Spring Boot takes the greeting from the `dev` profile file; `app.limit` can still come from the base file. You can replace `dev` with another profile name defined by your project.

In this typical example, when **the same key** appears in multiple places, you can picture the precedence from highest to lowest as follows:

```text
Application argument: --app.greeting=...
          >
Environment variable: APP_GREETING
          >
Active profile file: application-dev.properties
          >
Base file: application.properties
```

This is a **practical working sketch**, not the full precedence table of every `PropertySource` Spring Boot supports. Test configuration, JVM properties, JSON configuration, imported sources, and multi-file/multi-location setups also exist. When explaining an unexpected value, inspect **all actual participating sources** rather than looking at just one file.

Key distinctions to grasp right away:

- **Key name and value** are separate: `app.greeting` is the key; the specific greeting text is the value.
- **Profiles are not OS environment variables.** A profile is a Spring mechanism; you activate it via `spring.profiles.active` from an appropriate configuration source.
- **Environment variables** are inherited by the process at launch. Editing a variable or file on disk does not automatically recreate or update running beans.
- **Precedence determines the effective value** when multiple sources supply the same key; it does not mean all content from lower-precedence sources is discarded.

## 8. When to Use `@Value`, `Environment`, or `@ConfigurationProperties`?

All three options consume configuration, but serve different purposes.

| Approach | When to Use | Points to Note |
| --- | --- | --- |
| `@Value("${app.greeting}")` | Need to inject a small, standalone value into a bean | Key is referenced directly; many scattered values become hard to manage. |
| `Environment#getProperty("app.greeting")` | Need to look up a value at a specific point in code or diagnostics | Caller must know the key name; result can be `null` if missing. |
| `@ConfigurationProperties(prefix = "app")` | Have a group of settings belonging to the same feature | Binds into Java types, works nicely with records, supports conversion and validation. |

Simple example with `@Value`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingLabel {
    private final String greeting;

    public GreetingLabel(@Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    public String text() {
        return greeting;
    }
}
```

In `${app.greeting:Hello}`, the part after `:` is a fallback value if the key is not found. This is Spring placeholder syntax, not native Java property syntax.

For multiple settings sharing a feature—such as timeout, retry count, service URL, and feature toggle—`@ConfigurationProperties` is usually clearer because it groups them into one typed object. There is no need to mix all three approaches for the same property without a specific reason.

## 9. Validation and Handling Missing Configuration

Configuration is application input. Some values convert cleanly to Java types yet are invalid functionally, such as zero retries or a blank greeting. You can place constraints on configuration objects.

If you add the `spring-boot-starter-validation` dependency, replace `AppSettings` in the example with:

```java
package example.configdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppSettings(
    @NotBlank String greeting,
    @Min(1) int limit
) {
}
```

When Spring Boot binds and validates configuration, a constraint violation causes the application to fail with an error rather than starting with invalid configuration. Without the corresponding Bean Validation library, do not assume adding annotations alone enforces constraints.

Three failure cases to distinguish when reading errors:

1. **Missing key:** no value found and no applicable default.
2. **Wrong type:** for example `app.limit=abc` when the Java field is `int`.
3. **Validation rule failure:** for example `app.limit=0` with `@Min(1)`.

Error messages typically point to the key name or binding path. Check the **actual key**, the **winning source by precedence**, and the **Java type/constraints**.

## 10. Common Misconceptions Before Going Deeper

**Misconception 1 — `application.properties` is the only source.** It is just one of many sources Spring Boot supports. What you read in that file may not be the final runtime value.

**Misconception 2 — Adding `@ConfigurationProperties` is enough to get a bean.** You must also register the configuration class via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate registration mechanism. In this example we used `@ConfigurationPropertiesScan`.

**Misconception 3 — IoC understands arbitrary key names automatically.** Spring can bind properly only when the key name, configuration prefix, data type, and bean registration align. A mistake in any of these can lead to missing values or startup failure.

**Misconception 4 — Spring Boot 2 example syntax can be copied without checking.** Watch the Java level, the `javax` to `jakarta` migration, and constructor binding in Spring Boot 3.3. For a record with a single constructor, you do not need `@ConstructorBinding` to enable constructor binding.

**Misconception 5 — Environment variables are always safe for secrets.** Environment variables are convenient for deployment, yet can leak via infrastructure configs, logs, or process inspection tools. Never place real passwords, access keys, or tokens in examples, files committed to Git, or logs. In real environments, choose secret management suited to your infrastructure.

**Misconception 6 — Editing a file updates running configuration objects automatically.** In standard Spring Boot applications, configuration beans are constructed during startup. Dynamic refresh requires a specially designed mechanism; do not assume this capability by default.

**Misconception 7 — Using profiles to hide secrets.** Profiles select configuration by context; they are not encryption or secret management.

## 11. Self-Check Foundation Exercise

Perform these steps sequentially on `ConfigDemoApplication`:

1. Start with only `application.properties`; predict and record the two printed values.
2. Set `APP_GREETING` and restart; verify which value changed and which stayed the same.
3. Keep the environment variable, add `--app.greeting=...` at startup; explain why the argument's value is chosen.
4. Create `application-dev.properties`, activate the `dev` profile, and observe the result when **no** environment variable or argument overrides the greeting.
5. Change `app.limit=abc`; recognize this as a type conversion error.
6. Add Bean Validation, change `app.limit=0`; recognize this as a constraint validation error.
7. Reopen the Java code and point out: where configuration sources are read, where `AppSettings` is created, and where DI passes `AppSettings` into `ApplicationRunner`.

You have the foundation for upcoming lessons once you can answer in your own words:

- Why can the same JAR receive different configurations without editing Java code?
- What distinct roles do `Environment`, `PropertySource`, `@ConfigurationProperties`, and Spring beans play?
- How do `record` and constructors model immutable configuration?
- When the same key appears in multiple sources, where should you look to find why the final value won?
- Which parts belong to Java, which to IoC/DI, and which to Spring Boot's Externalized Configuration?

From this foundation, you can progress in order: **configuration sources → precedence order → profiles → type-safe binding → validation → secure operations**. That learning path connects Java fundamentals with how Spring Boot 3.3 uses configuration in a real application.
