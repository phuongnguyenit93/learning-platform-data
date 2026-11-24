# Value Injection Timing and Why `static` Fields Are Unsuitable in Spring Boot

## 1. Problem: the configuration is present, so why is the variable still `null`?

In a Spring Boot application, you might declare configuration like this:

```yaml
# src/main/resources/application.yaml
demo:
  display-name: "Configuration Lab"
```

and read it inside a Spring bean:

```java
@Component
public class ExampleService {

    @Value("${demo.display-name}")
    private String displayName;

    public void print() {
        System.out.println(displayName);
    }
}
```

When Spring manages and initializes `ExampleService` normally, the `displayName` field is injected before the bean finishes initialization. However, if you **read that field inside the constructor**, you will usually still see `null`; and if you place the annotation on a **`static` field**, you may find it **never gets injected** even though the configuration is completely valid.

This is not a bug in locating the configuration file. It is a confusion among:

1. **When Spring Boot loads configuration sources** into `Environment`.
2. **When Spring instantiates a bean and injects dependencies** into the object.
3. **The lifecycle of an instance field** versus a **`static` field belonging to a Java class**.
4. **When your code attempts to read the value**.

This lesson belongs to the **Configuration Access** topic of Spring Boot Externalized Configuration. The goal is to understand the underlying lifecycle rather than merely tweaking one annotation line until the program stops reporting `null`.

After this lesson, you will be able to:

- Describe the pipeline from `application.yaml` to `Environment`, `@Value`, `@ConfigurationProperties`, and running beans.
- Distinguish reading a `@Value` field in a constructor versus in `@PostConstruct`, `ApplicationRunner`, and business methods.
- Use **constructor injection** to receive configuration ready right when the constructor is called.
- Explain why `@Value` on a `static` field is not a Spring-supported configuration injection mechanism.
- Choose the right configuration access approach for `static` utilities, singleton services, and applications with multiple `ApplicationContext`s.
- Identify the causes of `null` values, placeholder errors, manual `new` instantiation, and cases where configuration does not update automatically when files change.
- Write and run a Java 21 / Spring Boot 3.3.x application to observe the sequence of initialization milestones.

**Scope:** examples use non-sensitive dummy data. This is a console application requiring neither a database nor an HTTP server.

## 2. Two timelines to distinguish

### 2.1. Configuration sources are prepared early

Spring Boot prepares `Environment` and processes **Config Data** before instantiating most regular application beans. Configuration sources can include:

- `application.properties`, `application.yaml`, and profile-specific files.
- Files outside the JAR or additional sources via `spring.config.import`.
- Process environment variables.
- Java system properties.
- Command-line arguments.
- Other sources integrated into startup by the application or libraries.

Sources have different **precedence levels**. When you request `demo.display-name`, Spring returns the effective value according to resolution rules and source precedence.

This does not mean every Java class can automatically read that value from a field Spring has not injected yet. Even though `Environment` is ready, the **bean instance** still goes through instantiation and dependency injection.

### 2.2. Beans pass through multiple initialization milestones

For a standard Spring bean using field injection:

```text
Spring Boot starts up
         |
         v
Prepare Environment, load Config Data
         |
         v
Create ApplicationContext, register bean definitions
         |
         v
Select bean to instantiate
         |
         v
CALL CONSTRUCTOR  -------------------+
         |                           |
         |                           +--> Instance @Value field has
         |                                not been field-injected yet
         v
Inject dependencies / instance @Value fields
         |
         v
Initialize bean, run @PostConstruct
         |
         v
Bean is ready for use in context
         |
         v
ApplicationRunner / CommandLineRunner
         |
         v
Business calls after application startup
```

This diagram is a conceptual model for simple beans. Spring also performs many steps such as `BeanPostProcessor`s, `Aware` callbacks, initialization methods, proxies, lazy beans, and different scopes. Those additional steps do not change the core principle: **the constructor runs before Spring assigns `@Value` fields on that same instance**.

For **constructor injection**, the timing inside the constructor is different:

```text
Environment already holds values
          |
          v
Spring resolves @Value parameter or dependency
          |
          v
Invoke constructor with prepared arguments
          |
          v
Assign to instance final field
          |
          v
@PostConstruct and bean usage phases
```

Therefore, if you need configuration right inside the constructor, **receive it as a constructor parameter**, instead of expecting Spring to have populated a `@Value` field before the constructor executes.

## 3. Field injection: populated after the constructor

Example:

```java
package dev.example.timing;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class FieldProbe {

    @Value("${demo.display-name:unnamed}")
    private String displayName;

    public FieldProbe() {
        System.out.println("FieldProbe constructor: " + displayName);
    }

    @PostConstruct
    void afterInjection() {
        System.out.println("FieldProbe @PostConstruct: " + displayName);
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

When Spring creates `FieldProbe`, the logical sequence is:

1. Java allocates and initializes the instance.
2. The constructor runs. Because no field injection has happened yet, `displayName` remains Java's default value for `String`, typically `null`.
3. After the constructor, Spring's injection processor resolves `${demo.display-name:unnamed}` via `Environment` and assigns the instance field.
4. The `@PostConstruct` callback runs during bean initialization; at this stage, the newly injected field can be read.
5. `getDisplayName()` reads the value on the initialized bean.

If YAML contains `demo.display-name: Configuration Lab`, the two observable milestones are:

```text
FieldProbe constructor: null
FieldProbe @PostConstruct: Configuration Lab
```

**Do not use `displayName` to set up critical logic inside the constructor of the example above**. If you need it right at object creation, use constructor injection.

### 3.1. When does `@PostConstruct` happen?

`@PostConstruct` is an initialization callback processed after ordinary instance dependencies have been injected, yet before the bean finishes initialization. It suits small configuration logic that needs to run once after injection.

Example:

```java
@PostConstruct
void initialize() {
    if (displayName == null || displayName.isBlank()) {
        throw new IllegalStateException("demo.display-name is blank");
    }
}
```

However, large-scale configuration validation should use `@ConfigurationProperties` with validation rather than writing lots of manual checks inside `@PostConstruct`.

In Spring Boot 3.x, the `@PostConstruct` import is:

```java
import jakarta.annotation.PostConstruct;
```

not the older `javax.annotation.PostConstruct` API.

### 3.2. Do not treat `println` order across different beans as absolute

With multiple beans that have no dependency constraints between them, exact bean creation order can vary. You may see bean A's constructor log interleaved with bean B's callback. Verify **the milestone order within each individual bean**, rather than treating the global log order as an architectural contract.

If logic must run **after the application context has started**, use `ApplicationRunner` or `CommandLineRunner`. If logic must occur right when a bean is created, use the constructor or an appropriate callback. Do not add annotations just to force prettier log ordering.

## 4. Constructor injection: configuration is ready when the constructor is called

The preferred solution when a service needs one or more configuration values is passing them via constructor:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ConstructorProbe {

    private final String displayName;

    public ConstructorProbe(
            @Value("${demo.display-name:unnamed}") String displayName) {
        this.displayName = displayName;
        System.out.println("ConstructorProbe constructor: " + displayName);
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Spring resolves the `@Value` parameter before invoking the constructor. When the constructor executes, `displayName` is already the argument supplied by Spring.

Advantages:

- Dependencies are declared **explicitly** in the constructor signature.
- Fields can be `final`.
- The instance always receives values when properly instantiated.
- Unit tests can instantiate directly with explicit data:
  
  ```java
  ConstructorProbe probe = new ConstructorProbe("test-value");
  ```

- No need to wait for `@PostConstruct` before using the configuration.
- Reduces the chance of accidentally reading an uninjected field inside the constructor.

Note for unit tests instantiating the bean manually: you must **pass actual values into the constructor**. Java does not automatically process `@Value` annotations when calling `new`.

### 4.1. Similar approach with `Environment`

A bean can also accept `Environment` via constructor:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class EnvironmentProbe {

    private final Environment environment;

    public EnvironmentProbe(Environment environment) {
        this.environment = environment;

        String label = environment.getProperty(
                "demo.display-name", "unnamed");

        System.out.println("constructor via Environment: " + label);
    }

    public String currentDisplayName() {
        return environment.getProperty(
                "demo.display-name", "unnamed");
    }
}
```

`Environment` is a valid Spring dependency. Calling `getProperty()` lets you look up properties by name when the method executes. This differs from storing a `@Value` result in a field.

Even though `Environment` can be queried repeatedly, **editing `application.yaml` outside the process does not automatically make `Environment` reload Config Data**. In standard configuration, file values are loaded at startup; dynamic updates require an intentional refresh mechanism.

## 5. Why are `static` fields unsuitable for `@Value`?

Consider:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StaticProbe {

    @Value("${demo.display-name:unnamed}")
    private static String displayName;

    public static String currentValue() {
        return displayName;
    }
}
```

This code looks like ordinary field injection, yet `displayName` is a **static field**. It belongs to the **`StaticProbe` class**, not to any individual bean instance.

In Spring's standard injection mechanism, `@Value` and `@Autowired` on static fields are **not processed as valid bean instance field dependency injection**. The injection processor may skip static fields and log a warning. Consequently, `StaticProbe.currentValue()` normally returns `null` unless other Java code manually assigns that field.

Distinguish:

```text
Instance field:  objectA.displayName
                 objectB.displayName

Static field:    StaticProbe.displayName
                 ^ a single class-level state slot,
                   shared across instances and contexts
```

Spring manages **bean instances**. For `@Value` on an instance field, Spring has a concrete object to populate during that bean's lifecycle. With a static field, the value is not tied to an instance, making bean-lifecycle injection inappropriate.

### 5.1. Why doesn't having `@Component` save a static field?

`@Component` enables Spring to discover and instantiate a **bean instance** of that class. The annotation does not turn `static` fields into instance fields.

```java
@Component
public class StaticProbe {
    @Value("${demo.display-name}")
    private static String displayName;
}
```

Spring can create `StaticProbe` successfully, yet that **does not guarantee** the static field gets populated. If some other code happens to assign a value to the static field, you could even be misled into thinking the annotation worked.

### 5.2. When is `static` initialized?

Java classes can be loaded and initialized on demand by the JVM, independently of when Spring creates beans. Static initializers run during class initialization:

```java
public class StaticExample {

    static {
        System.out.println("class initialization");
    }
}
```

You cannot assume a static initializer has access to a ready Spring application context or properties resolved for beans. Class loading order can depend on the first time the class is referenced.

A call such as:

```java
String label = StaticProbe.currentValue();
```

runs on the class and does not automatically ask Spring to construct beans or resolve placeholders on static fields.

### 5.3. `static final` is even further from runtime configuration

Example:

```java
public static final String DISPLAY_NAME = "hard-coded";
```

This is a constant fixed in Java source code. If you need it to vary by profile or environment variable, a `static final` constant is not an appropriate choice.

Some people try:

```java
@Value("${demo.display-name}")
private static final String DISPLAY_NAME = null;
```

This does not turn a constant into a Spring-supplied property. Do not rely on reflection or mutating `final` fields to inject configuration. If a value belongs to runtime, retrieve it through a bean or dependency designed for runtime.

### 5.4. What problems does `static` cause beyond not being injected?

Even if you manually write code assigning a static field from an instance callback, it still carries risks:

1. **Multiple `ApplicationContext`s:** two different contexts may need two configuration sets, yet share one JVM static field.
2. **Testing:** an earlier test can leak state into a subsequent test.
3. **Lifecycle:** when a context closes, static state is not automatically cleared with the bean lifecycle.
4. **Initialization:** code might read the static field before the bean assigns it.
5. **Concurrency:** multiple threads may read/write the same static field, causing visibility or race issues.
6. **Hard to substitute:** you cannot easily mock or supply per-instance configuration.
7. **Hard to trace origin:** it is unclear which context and moment determined the current value.

Therefore, avoid sharing **environment-varying configuration** through mutable static variables.

## 6. What if a `static` method genuinely needs configuration?

A static method cannot read instance fields directly the way an instance method can. However, it can **receive the required value as a parameter**:

```java
public final class LabelFormatter {

    private LabelFormatter() {
    }

    public static String format(String prefix, String message) {
        return prefix + ": " + message;
    }
}
```

A service has configuration injected normally:

```java
import org.springframework.stereotype.Service;

@Service
public class LabelService {

    private final ConstructorProbe configuration;

    public LabelService(ConstructorProbe configuration) {
        this.configuration = configuration;
    }

    public String format(String message) {
        return LabelFormatter.format(
                configuration.getDisplayName(), message);
    }
}
```

Advantage: the static method remains a **stateless utility**, while fetching configuration belongs to the Spring bean. You can unit test the formatter with two arguments without starting a Spring context.

If you want the utility to know its configuration naturally without passing extra arguments on every call, turn the utility into an **instance bean**:

```java
import org.springframework.stereotype.Component;

@Component
public class MessageFormatter {

    private final String prefix;

    public MessageFormatter(
            @Value("${demo.display-name:unnamed}") String prefix) {
        this.prefix = prefix;
    }

    public String format(String message) {
        return prefix + ": " + message;
    }
}
```

Now other beans receive `MessageFormatter` via constructor. This keeps configuration aligned with the application context lifecycle and easy to substitute in tests.

## 7. `@ConfigurationProperties`: the option for a configuration group

`@Value` suits one or a few values. When multiple fields belong to one group, Spring Boot recommends `@ConfigurationProperties`.

Example:

```yaml
demo:
  display-name: "Configuration Lab"
  retry-delay: 2s
  enabled: true
```

Java record:

```java
package dev.example.timing;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String displayName,
        Duration retryDelay,
        boolean enabled
) {}
```

Enable configuration scanning:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class InjectionTimingApplication {
    public static void main(String[] args) {
        SpringApplication.run(InjectionTimingApplication.class, args);
    }
}
```

A service receives the entire record:

```java
import org.springframework.stereotype.Service;

@Service
public class DemoService {

    private final DemoProperties settings;

    public DemoService(DemoProperties settings) {
        this.settings = settings;
    }

    public String describe() {
        return settings.displayName()
                + " / delay=" + settings.retryDelay()
                + " / enabled=" + settings.enabled();
    }
}
```

Benefits:

- Groups related properties into a **typed contract**.
- Configuration can convert into `Duration`, numbers, booleans, URIs, and more.
- Most beans do not need to know string property names.
- Works cleanly with configuration validation and IDE metadata when appropriate build setup is added.
- No need for static fields to "access anywhere": multiple services can receive the same Spring-managed configuration bean.

The `DemoProperties` record is an instance bean. It is **not a static global object**, even though it can be injected into multiple services within the same context.

### 7.1. How does `@ConfigurationProperties` differ from `@Value` in timing?

With both approaches, values are supplied to beans **while Spring initializes and configures beans**, not simply because the JVM loaded the class.

- Constructor parameters with `@Value` are resolved before invoking the constructor.
- Instance fields with `@Value` are assigned after the constructor.
- `@ConfigurationProperties` beans are created and bound according to Spring Boot's configuration properties lifecycle; consuming beans receive them via constructor once dependencies are prepared.

The key distinction is **how dependencies are declared**, not that switching from `@Value` to `@ConfigurationProperties` enables injecting into static fields.

## 8. Hands-on application: Injection Timing Observer

Let's build a runnable project to compare four approaches:

1. Instance field injection.
2. Constructor injection.
3. `@Value` mistakenly placed on a static field.
4. Typed binding with `@ConfigurationProperties`.

The program prints output to the console and exits. No HTTP endpoint is needed, so there is no risk of accidentally exposing configuration values over a public API.

### 8.1. Project structure

```text
injection-timing/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/timing/
    │   │   ├── InjectionTimingApplication.java
    │   │   ├── DemoProperties.java
    │   │   ├── FieldProbe.java
    │   │   ├── ConstructorProbe.java
    │   │   ├── StaticProbe.java
    │   │   └── ReportRunner.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/timing/
            └── InjectionTimingTest.java
```

Generate the skeleton with Spring Initializr using Java 21, Gradle, and a Spring Boot 3.3.x release. `gradlew` and `gradlew.bat` are generated by the Gradle Wrapper; you do not need to copy their contents manually.

`settings.gradle`:

```groovy
rootProject.name = 'injection-timing'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If the application lives in a repository with convention plugins or a version catalog, use the repository's dependency management system. This sample uses minimal dependencies for a console application.

### 8.2. Base configuration files

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none

demo:
  display-name: "from-application-yaml"
  retry-delay: 2s
  enabled: true
```

Set `web-application-type: none` so that after the runner finishes, the application does not keep a background web server alive.

File `src/main/resources/application-dev.yaml`:

```yaml
demo:
  display-name: "from-dev-profile"
  retry-delay: 500ms
```

Notice the `dev` file does not need to redeclare `demo.enabled`. When the `dev` profile is active, values from the base configuration and the profile-specific file are combined; `demo.enabled` can still come from the base file.

### 8.3. Main class

`src/main/java/dev/example/timing/InjectionTimingApplication.java`:

```java
package dev.example.timing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class InjectionTimingApplication {

    public static void main(String[] args) {
        SpringApplication.run(InjectionTimingApplication.class, args);
    }
}
```

### 8.4. Typed binding record

`src/main/java/dev/example/timing/DemoProperties.java`:

```java
package dev.example.timing;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String displayName,
        Duration retryDelay,
        boolean enabled
) {}
```

In YAML, the canonical property names are `display-name` and `retry-delay`, while in Java they bind to camelCase record components.

### 8.5. FieldProbe: constructor and `@PostConstruct`

`src/main/java/dev/example/timing/FieldProbe.java`:

```java
package dev.example.timing;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class FieldProbe {

    @Value("${demo.display-name:unnamed}")
    private String displayName;

    public FieldProbe() {
        System.out.println("FIELD constructor = "
                + show(displayName));
    }

    @PostConstruct
    void afterInjection() {
        System.out.println("FIELD @PostConstruct = "
                + show(displayName));
    }

    public String displayName() {
        return displayName;
    }

    private static String show(String value) {
        return value == null ? "<null>" : value;
    }
}
```

Here you observe two phases of the **same bean instance**: before field injection and after field injection.

### 8.6. ConstructorProbe: populated upon instance creation

`src/main/java/dev/example/timing/ConstructorProbe.java`:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ConstructorProbe {

    private final String displayName;

    public ConstructorProbe(
            @Value("${demo.display-name:unnamed}") String displayName) {
        this.displayName = displayName;
        System.out.println("CTOR constructor = " + displayName);
    }

    public String displayName() {
        return displayName;
    }
}
```

Spring resolves the parameter before calling the constructor. The `final` instance field is assigned right at object creation, instead of waiting for Spring to inject a field afterward.

### 8.7. StaticProbe: intentionally misplaced annotation example

`src/main/java/dev/example/timing/StaticProbe.java`:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StaticProbe {

    @Value("${demo.display-name:unnamed}")
    private static String displayName;

    public static String displayName() {
        return displayName;
    }
}
```

This is a **counter-example** for observation: the `@Value` annotation is not injected into static fields by standard bean injection. Never use this pattern in production code.

### 8.8. ReportRunner: reading beans after initialization

`src/main/java/dev/example/timing/ReportRunner.java`:

```java
package dev.example.timing;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ReportRunner implements ApplicationRunner {

    private final Environment environment;
    private final FieldProbe fieldProbe;
    private final ConstructorProbe constructorProbe;
    private final DemoProperties demo;

    public ReportRunner(
            Environment environment,
            FieldProbe fieldProbe,
            ConstructorProbe constructorProbe,
            DemoProperties demo) {
        this.environment = environment;
        this.fieldProbe = fieldProbe;
        this.constructorProbe = constructorProbe;
        this.demo = demo;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("=== INJECTION TIMING REPORT ===");
        System.out.println("activeProfiles = "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("Environment demo.display-name = "
                + environment.getProperty("demo.display-name"));
        System.out.println("fieldProbe.displayName = "
                + fieldProbe.displayName());
        System.out.println("constructorProbe.displayName = "
                + constructorProbe.displayName());
        System.out.println("DemoProperties.displayName = "
                + demo.displayName());
        System.out.println("DemoProperties.retryDelay = "
                + demo.retryDelay());
        System.out.println("DemoProperties.enabled = "
                + demo.enabled());
        System.out.println("StaticProbe.displayName = "
                + (StaticProbe.displayName() == null
                        ? "<null>" : StaticProbe.displayName()));
    }
}
```

`ApplicationRunner.run` is called after the application context has started. In this lab, the needed beans have already been prepared and injected before the runner prints the report.

`StaticProbe` is called via its class name to emphasize that it is a static method. Calling this method does **not** trigger Spring to inject the static field.

## 9. Test run 1: using values from `application.yaml`

From the project root directory:

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Key lines expected to appear, without requiring strict ordering across different beans:

```text
FIELD constructor = <null>
FIELD @PostConstruct = from-application-yaml
CTOR constructor = from-application-yaml
=== INJECTION TIMING REPORT ===
activeProfiles = []
Environment demo.display-name = from-application-yaml
fieldProbe.displayName = from-application-yaml
constructorProbe.displayName = from-application-yaml
DemoProperties.displayName = from-application-yaml
DemoProperties.retryDelay = PT2S
DemoProperties.enabled = true
StaticProbe.displayName = <null>
```

`PT2S` is how Java `Duration` represents a 2-second interval. Some Spring log lines may warn about an annotation on a static field. That is an additional signal, yet the key observation is that **the instance field gets its value after injection; the static field does not automatically get populated**.

### 9.1. What happens if `demo.display-name` is absent?

In the example, the `@Value` sites have a fallback:

```java
@Value("${demo.display-name:unnamed}")
```

If the property cannot be resolved from effective sources, Spring uses the string `unnamed` for those injection points. However, the `DemoProperties` record does not automatically inherit `@Value`'s fallback; it is bound from whatever configuration the Binder sees. Thus, differences can appear between field/constructor injection and the record if you delete the property without adding explicit defaults/validation for `@ConfigurationProperties`.

This is not a timing issue, but **two different mechanisms for declaring defaults**. When the exercise asks to compare timing, keep the property present so you do not mix fallback behavior into the same experiment.

## 10. Test run 2: `dev` profile

File `application-dev.yaml` is only loaded as a profile document when `dev` is active. Run:

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Expected values:

```text
FIELD constructor = <null>
FIELD @PostConstruct = from-dev-profile
CTOR constructor = from-dev-profile
activeProfiles = [dev]
Environment demo.display-name = from-dev-profile
fieldProbe.displayName = from-dev-profile
constructorProbe.displayName = from-dev-profile
DemoProperties.displayName = from-dev-profile
DemoProperties.retryDelay = PT0.5S
DemoProperties.enabled = true
StaticProbe.displayName = <null>
```

The sources changed the effective value, yet **the field injection sequence did not change**. `FieldProbe`'s constructor still runs before the instance field is injected; `ConstructorProbe`'s constructor still receives the value via its parameter; the static field is still not injected.

Key takeaway: profiles determine **which value** is selected, without making `@Value` on a static field valid.

## 11. Test run 3: CLI argument override

Try:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --demo.display-name=from-cli'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --demo.display-name=from-cli"
```

Expected:

```text
FIELD constructor = <null>
FIELD @PostConstruct = from-cli
CTOR constructor = from-cli
Environment demo.display-name = from-cli
DemoProperties.displayName = from-cli
StaticProbe.displayName = <null>
```

Normally, CLI arguments have higher precedence than Config Data files. Once again, the value changes with the configuration source, while injection timing and static field behavior remain unchanged.

You can also build the JAR:

macOS/Linux:

```bash
./gradlew bootJar
java -jar build/libs/injection-timing-0.0.1-SNAPSHOT.jar \
  --demo.display-name=from-jar-cli
```

PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build\libs\injection-timing-0.0.1-SNAPSHOT.jar --demo.display-name=from-jar-cli
```

When running the JAR, arguments after the JAR name are passed into Spring Boot. If the project changes its version or artifact name, use the actual JAR path under `build/libs`.

## 12. Why does manual `new` stop `@Value` from working?

Spring only injects dependencies into objects processed by its bean management mechanism. Consider:

```java
FieldProbe manual = new FieldProbe();
System.out.println(manual.displayName());
```

This invokes a regular Java constructor. It does **not** register the object as a bean or run `BeanPostProcessor`s to populate `@Value` fields. Therefore, `manual.displayName()` may remain `null`.

Whereas when retrieving the bean from Spring:

```java
FieldProbe managed = applicationContext.getBean(FieldProbe.class);
System.out.println(managed.displayName());
```

the instance field was injected during bean creation.

A common situation:

```java
@Service
public class OrderService {
    public void process() {
        EmailHelper helper = new EmailHelper();
        helper.send();
    }
}
```

If `EmailHelper` expects field injection:

```java
@Component
public class EmailHelper {
    @Value("${mail.from-address}")
    private String fromAddress;
}
```

then `new EmailHelper()` creates an object outside Spring; annotations on the class do not cause that instance to be injected automatically.

Fix: receive `EmailHelper` via `OrderService`'s constructor, or pass needed parameters to manually instantiated objects. In designs where many objects must be created dynamically, consider a managed bean factory or separating Spring-free logic from configuration retrieval.

## 13. Unit tests and integration tests: controlled observation

### 13.1. Unit testing constructor injection

Because `ConstructorProbe` accepts a concrete string in its constructor, you do not need a Spring context to unit test how it holds configuration:

```java
package dev.example.timing;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ConstructorProbeUnitTest {

    @Test
    void storesPassedConfiguration() {
        ConstructorProbe probe = new ConstructorProbe("from-test");

        assertEquals("from-test", probe.displayName());
    }
}
```

This test checks the Java class's contract. It does **not** prove Spring can read `application.yaml`, because it does not run Spring's property resolution.

### 13.2. Integration testing binding inside a Spring context

`src/test/java/dev/example/timing/InjectionTimingTest.java`:

```java
package dev.example.timing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.display-name=from-spring-test",
        "demo.retry-delay=3s",
        "demo.enabled=false"
})
class InjectionTimingTest {

    @Autowired
    private FieldProbe fieldProbe;

    @Autowired
    private ConstructorProbe constructorProbe;

    @Autowired
    private DemoProperties demo;

    @Test
    void injectsInstancePropertiesAndBindsConfiguration() {
        assertEquals("from-spring-test", fieldProbe.displayName());
        assertEquals("from-spring-test", constructorProbe.displayName());
        assertEquals("from-spring-test", demo.displayName());
        assertEquals(java.time.Duration.ofSeconds(3),
                demo.retryDelay());
        assertEquals(false, demo.enabled());
        assertNull(StaticProbe.displayName());
    }
}
```

Run:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

The Spring test context supplies test properties into `Environment`. Instance beans receive their corresponding values; the static field in the example remains unprocessed by `@Value`.

When running multiple tests in the same JVM, static state can be affected if other code assigned that field. That is why this test example intentionally **has no setter or callback assigning the static field**. In real applications, never rely on a static property to share state across tests.

### 13.3. Avoid overusing tests that assert log ordering

Good tests assert **values available at the right usage time**, rather than asserting the exact order of `System.out` lines. If a test genuinely needs to observe lifecycle order, record events for one specific bean and check "constructor before callback", while avoiding coupling to the initialization order of independent beans.

## 14. What if you urgently need to feed values to legacy `static` code?

Sometimes an old library or class has a static API you cannot refactor immediately:

```java
LegacyGlobalClient.configure("some value");
```

One bridging approach is to create **an instance Spring bean** that receives the value via constructor and calls the static API in an initialization callback:

```java
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class LegacyClientInitializer {

    private final String endpoint;

    public LegacyClientInitializer(
            @Value("${legacy.endpoint}") String endpoint) {
        this.endpoint = endpoint;
    }

    @PostConstruct
    void configureLegacyClient() {
        LegacyGlobalClient.configure(endpoint);
    }
}
```

This is **not static injection**. Spring injects into the `LegacyClientInitializer` instance, and you explicitly invoke a static API owned by the legacy system.

Risks still remain:

- `LegacyGlobalClient` might be called before the initialization callback runs.
- Two Spring contexts can configure the same global client differently.
- Parallel tests or multi-tenant apps can contend over global state.
- When the context closes, the application needs to decide whether global state must be reset.
- If the library offers an API to construct separate client instances, migrate to instance clients instead.

Therefore, a bridge should only be a **temporary workaround for strictly constrained legacy systems**, not a pattern to make `@Value` work on static fields.

### 14.1. Why is an instance setter assigning a static field not a sustainable solution?

You may encounter snippets like:

```java
@Component
public class LegacyStaticHolder {

    private static String value;

    @Value("${demo.display-name}")
    public void setValue(String configured) {
        value = configured;
    }

    public static String getValue() {
        return value;
    }
}
```

The instance method called by Spring serves as the injection point, while assigning `value` is done by your code. This may run in a simple application, yet it fails to solve the **lifecycle, multi-context, test isolation, and concurrency** issues of static state.

Treat it as a limited workaround, not a recommended form of constructor or field injection.

## 15. Comparing configuration access options

| Usage | When value is available | Usable in constructor? | Recommendation |
| --- | --- | --- | --- |
| Instance field `@Value` | After constructor runs, during bean injection | **No**, do not read field directly before injection | Use for simple cases; avoid constructor depending on field |
| Constructor parameter `@Value` | When Spring invokes constructor | **Yes**, via parameter | Good for a few configuration keys |
| `@ConfigurationProperties` bean | Created and bound during context lifecycle | **Yes**, when injecting bean into other services | Good for typed key groups |
| Inject `Environment` via constructor | When Spring supplies dependency | **Yes**, queried via `getProperty()` | Use when deliberate key-based lookup is needed |
| Static field `@Value` | No standard injection | No | **Do not use** |
| Static utility taking parameters | When caller passes arguments | Yes, controlled by caller | Good for pure stateless functions |
| Static global assigned via callback | Depends on callback and call order | Unsafe if read early | Only consider for controlled legacy integration |

Note: "available in constructor" here means **Spring supplies the dependency via constructor**. It does not mean another `@Value` field in the same class has been injected prior to the constructor.

## 16. Common misconceptions

### 16.1. "Environment is already loaded, so the constructor should see the `@Value` field, right?"

False. There are two distinct phases. `Environment` may already hold the property, yet the instance field keeps its Java default until the injection step runs. Pass the property as a **constructor parameter** to use it immediately.

### 16.2. "I added `@Component`, yet the static field is still null"

`@Component` makes the class a candidate for a bean instance; it does not change Java's rules for static fields. Standard Spring does not support field injection this way. Switch to an instance field, constructor injection, or `@ConfigurationProperties`.

### 16.3. "Should `@Autowired` on static work instead of `@Value`?"

Neither is a supported way to inject into static fields. Switching from `@Value` to `@Autowired` does not solve lifecycle or ownership problems.

### 16.4. "I called `new`, yet the annotation is still on the class"

Annotations are just metadata. An object instantiated via `new` outside Spring does not automatically go through the bean lifecycle. If you need Spring injection, let Spring create the object or use an explicit management process.

### 16.5. "Is adding `@PostConstruct` to a static method enough?"

No. Bean-instance lifecycle callbacks are not a general API for Spring to invoke arbitrary annotated static methods. Place callbacks on an **instance bean** and let it do the work, rather than using static callbacks to replace injection.

### 16.6. "The static field was populated by an earlier test, so my code works"

This may be state leaking across tests/contexts. Static fields live per class in the JVM, not per Spring context. Test isolation is a key reason to avoid this design.

### 16.7. "A `@Value` variable being `null` means the property source was ignored"

There are several other possibilities: the object was not created by Spring, the field is read too early, the annotation is on a static field, the property is missing with a fallback, profile/location is wrong, or a higher-precedence source overrides it. Diagnose step by step instead of concluding from a single `null`.

### 16.8. "Editing the YAML file updates `@Value` immediately"

Not by default. Beans are typically created and injected from a configuration snapshot at startup. External files do not automatically refresh already-assigned fields. Dynamic refresh mechanisms exist in certain setups, yet they must be configured and tested separately.

### 16.9. "If an app has one instance, a singleton bean is the same as static"

They are not the same. A standard Spring singleton is a single bean instance **within one application context**. A static field belongs to the class in the JVM, so it can be shared across multiple contexts in the same JVM. This is a crucial difference when running integration tests, child contexts, or embedded applications.

## 17. Troubleshooting procedure when `@Value` does not receive a value

If you see:

```java
@Value("${demo.display-name}")
private String displayName;
```

yet get `null` at runtime, check in order:

**Step 1 — Verify the object is a Spring bean.** Find where the object is created. If code contains `new SomeService()`, Spring does not automatically inject that instance.

**Step 2 — Check if the field is `static`.** If so, drop static field injection. Move to a constructor parameter or `@ConfigurationProperties` inside a bean.

**Step 3 — Check where you read the value.** If inside a constructor while the field is directly `@Value`-annotated, that is too early. Use constructor injection or only read the field after Spring finishes injection.

**Step 4 — Check the canonical property name.** For `demo.display-name`, placeholders should use exact kebab-case: `${demo.display-name}`.

**Step 5 — Check actual configuration sources.** Was `application.yaml` packaged and loaded? Is the right profile active? Did the working directory change? Are there imports or extra config locations?

**Step 6 — Check source precedence.** Environment variables, system properties, or CLI flags may override files. The effective value does not necessarily come from the file you just edited.

**Step 7 — Check fallbacks vs. unresolved placeholder errors.** `${demo.display-name:unnamed}` has a fallback; `${demo.display-name}` can fail bean creation if unresolved. These differ from an uninjected static field.

**Step 8 — Probe with a test value.** Temporarily pass `--demo.display-name=probe-value`, run a fresh process, and compare `Environment`, constructor injection, and post-initialization field injection.

**Step 9 — Separate lifecycle errors from data errors.** If `Environment` shows `probe-value` and constructor injection works, yet the static field is `null`, it is an injection-mechanism issue, not a missing file.

**Step 10 — Add tests and fix the design.** When a service relies on critical configuration, receive the configuration bean via constructor and write an integration test verifying the binding contract.

Do not temporarily expose public diagnostic endpoints or log the entire `Environment` just to inspect one value. In production, doing so can leak secrets, tokens, or credentials.

## 18. Additional practice exercises

### Exercise A — Predict the milestone order of a bean

Read the code:

```java
@Component
public class OrderProbe {

    @Value("${demo.display-name}")
    private String name;

    public OrderProbe() {
        System.out.println("constructor: " + name);
    }

    @PostConstruct
    void initialized() {
        System.out.println("postConstruct: " + name);
    }
}
```

With the property present and the bean created by Spring, predict the two printed lines. Explain based on **constructor vs. field injection order**, not when Spring read the YAML file.

### Exercise B — Fix a class using static

Input:

```java
@Component
public class UrlHelper {
    @Value("${remote.base-url}")
    private static String baseUrl;

    public static String resource(String id) {
        return baseUrl + "/resources/" + id;
    }
}
```

Requirement: rewrite it as a Spring bean with a `final String baseUrl` injected via constructor, make `resource(String id)` an instance method, and have other services consume it via constructor injection.

Hint: do not add a static setter just to preserve old call sites if you can refactor to an instance dependency.

### Exercise C — Testing profile values

Add:

```yaml
# application-staging.yaml
demo:
  display-name: "from-staging"
```

Run the same JAR with `--spring.profiles.active=staging`, and then with `--demo.display-name=forced-value`. Record these three values:

- `Environment.getProperty("demo.display-name")`.
- `ConstructorProbe.displayName()`.
- `StaticProbe.displayName()`.

Explain why the first two values change with source precedence while the static value remains uninjected.

### Exercise D — Compare `Environment` and bean-stored values

A service holds:

```java
private final String initialName;
private final Environment environment;

public DemoConsumer(
        @Value("${demo.display-name}") String initialName,
        Environment environment) {
    this.initialName = initialName;
    this.environment = environment;
}
```

Explain the difference between `initialName` and `environment.getProperty("demo.display-name")` regarding **read timing**. In standard configuration without refresh, both usually see the same startup value, whereas a system updating property sources dynamically may require reviewing the refresh strategy of beans holding injected values.

### Exercise E — Choose the right design for a utility

There are three ways to invoke a formatter:

1. `static format(String message)` reading a static configuration field.
2. `static format(String prefix, String message)` taking explicit parameters.
3. `formatter.format(String message)` using a constructor-configured bean.

Choose the appropriate option for: a plain Java library without Spring, a Spring service using the same prefix across many business paths, and a legacy class whose API cannot yet change. State the reasons and risks of each choice.

## 19. Self-check questions and hints

**Question 1.** Spring Boot loads `application.yaml` before creating beans, so why can a `@Value` field still be `null` inside a constructor?

**Question 2.** Inside a bean, when is it appropriate to read an instance `@Value` field after injection: the constructor or `@PostConstruct`?

**Question 3.** If a configuration value is needed immediately inside the constructor, which declaration style should you switch to?

**Question 4.** Does `private static String name` belong to an instance or to the class? Why does that matter for injection?

**Question 5.** A class has `@Component`, yet is instantiated with `new` elsewhere. Is the object created by `new` automatically injected?

**Question 6.** Why is `@ConfigurationProperties` not a way to inject values directly into a static field?

**Question 7.** Why should you avoid using a static holder to share configuration across multiple Spring test contexts?

**Question 8.** If you edit the YAML file and read `@Value` again, does it automatically pick up the new value inside the running process?

**Question 9.** What must be distinguished between a source being loaded and a field having been injected?

**Question 10.** If a static method genuinely just formats strings using configuration, how can it avoid holding global state?

**Answer hints:**

1. Because the constructor runs before the bean instance's field injection phase.
2. `@PostConstruct` or calls after the bean has been initialized.
3. Use a constructor parameter with `@Value` or inject a `@ConfigurationProperties` bean.
4. It belongs to the class; standard Spring field injection targets bean instances.
5. No; Spring must manage the instance, or dependencies must be passed another way.
6. `@ConfigurationProperties` creates and binds **bean instances**, not static injection.
7. Contexts can share one static field, leaking state and causing test ordering bugs.
8. Not by default; basic configuration is loaded and injected at startup.
9. A source existing in `Environment` does not mean an arbitrary object went through lifecycle injection.
10. Use a static method taking parameters, or turn the formatter into an instance bean.

## 20. Applying in real-world projects

A simple convention for Spring Boot services:

- **Single value:** constructor parameter with `@Value("${service.some-key}")` if the problem is small.
- **Multiple related values:** `@ConfigurationProperties` and inject the configuration bean via constructor.
- **Never read a field-injected property inside a constructor.**
- **Never place `@Value` or `@Autowired` directly on static fields** expecting dependency injection.
- **Never manually `new` an object** if it relies on Spring management, unless you pass all dependencies directly to the constructor.
- **Static utilities should be stateless**, receiving configuration or required data via parameters.
- **Every runtime value needs a clear lifecycle**, tied to the context and tested under critical profiles/precedence sources.
- **Never print sensitive configuration to logs**, including inside `@PostConstruct` callbacks or runners.

When a property is missing where you expect it, ask yourself:

```text
1. Does Environment already have the effective value?
2. Is this object a Spring bean?
3. Am I reading before or after injection?
4. Is the field instance or static?
5. Is a higher-precedence source or fallback changing the result?
```

If you answer these five questions in order, you will separate **configuration source** bugs, **injection timing** bugs, and **Java static design** bugs. That is the foundation for safe and consistent configuration access in Spring Boot.

### References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): configuration values from sources, precedence order, and accessing via `@Value`, `Environment`, and `@ConfigurationProperties`.
- [Spring Framework — Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html): how bean parameters and fields receive values.
- [Spring Framework — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): dependency injection processing for bean instances.
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization callbacks, including `@PostConstruct`.