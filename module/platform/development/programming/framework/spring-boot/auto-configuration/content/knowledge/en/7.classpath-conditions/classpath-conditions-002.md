# @ConditionalOnMissingClass: Choosing a Fallback When a Library Is Absent

## 1. Objective

A Spring Boot library can support two modes of operation: using an optional SDK/JAR when it is present and using a fallback when it is absent. For example, a module might prefer integrating a third-party encoder; however, if the user does not install that library, the module still needs a basic implementation that does not depend on the SDK.

Spring Boot's `@ConditionalOnMissingClass` serves this exact case of **an absent classpath dependency**:

```java
@ConditionalOnMissingClass("com.vendor.sdk.OptionalClient")
```

When the class with that name cannot be found by the classloader Spring Boot is evaluating, the condition can match. When the class is present, the condition does not match and the annotated configuration is not registered through the corresponding path.

This lesson clarifies:

1. How **class**-based conditions differ from **bean**-based or **property**-based conditions.
2. Why `@ConditionalOnMissingClass` requires the class name as a `String`, and how placing it on a configuration class benefits class-loading safety.
3. How to combine absent and present conditions to select exactly one strategy.
4. How to design auto-configuration with an optional dependency, registered via `.imports`, without widening component scanning.
5. How to run a Spring Boot application in two modes: **without Jackson** and **with Jackson**, verifying results, conditions, and configuration errors.

The focus is on **selecting configuration based on library absence**, not merely introducing annotation syntax.

## 2. Distinguishing Three Types of “Absence”

Common conditional annotations check different layers:

| Annotation | What does it ask? | Example |
| --- | --- | --- |
| `@ConditionalOnMissingClass` | Is the named class **absent** from the inspected classpath? | Absent `com.vendor.sdk.Client` |
| `@ConditionalOnClass` | Is the named class **present** on the classpath? | Present `com.fasterxml.jackson.databind.ObjectMapper` |
| `@ConditionalOnMissingBean` | Is there no matching bean in the `ApplicationContext` when the condition is evaluated? | No bean of type `MessageFormatter` |
| `@ConditionalOnProperty` | Does a configuration property have a matching value? | `feature.enabled=true` |
| `@ConditionalOnResource` | Is a resource present at the specified location? | Additional config resource exists? |

**Having a class does not mean having a bean.** A JAR may contain `ObjectMapper.class`, yet have no `ObjectMapper` bean because auto-configuration was excluded or the user did not register that bean.

**Missing a class differs from missing a declared Maven dependency.** A class can be brought in at runtime through a transitive dependency; conversely, Maven might compile with a dependency yet package or run with a classpath that excludes it. The condition relies on the effective classloader when the application runs, not merely reading the direct dependency list in `pom.xml`.

**Missing a bean differs from a bean not yet created because it is lazy.** `@ConditionalOnMissingBean` checks bean definition metadata at the appropriate time; a singleton bean with a definition that has not yet been instantiated is still not treated as “missing” by default.

## 3. Exact API of @ConditionalOnMissingClass

In Spring Boot 3.3.x, the fully qualified name is:

```java
org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass
```

Annotation structure simplified for reading:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnClassCondition.class)
public @interface ConditionalOnMissingClass {
    String[] value() default {};
}
```

This is an **API description**, not a Java file to copy into your project. Spring Boot already provides this annotation.

Usage:

```java
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

Or with multiple names:

```java
@ConditionalOnMissingClass({
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

With multiple classes, the condition requires **all listed classes to be absent**. If any class is detected, the missing-class condition is no longer satisfied for that set.

### Special Note: There Is No name Attribute

`@ConditionalOnMissingClass` has **a single `value()` attribute of type `String[]`**, so the following form is a **syntax error**:

```java
// WRONG: @ConditionalOnMissingClass does not declare "name".
@ConditionalOnMissingClass(name = "com.vendor.sdk.Client")
```

The correct way:

```java
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

By contrast, `@ConditionalOnClass` can use either a class literal:

```java
@ConditionalOnClass(SomeLibraryType.class)
```

or a class name:

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
```

For an absence condition, using **a class name string** avoids requiring the source code to directly import `Client` just to assert that the class is absent. It also fits the case where a branch is compiled and run in an environment that does not carry the optional SDK.

### Condition Outcome

```text
@ConditionalOnMissingClass("com.vendor.sdk.Client")

Runtime classpath DOES NOT have that class -> condition MATCH
Runtime classpath HAS that class           -> condition NO MATCH
```

This decides whether the annotated component is allowed to be configured further. `MATCH` does not guarantee every bean in the configuration class will be created, because other conditions or bean initialization errors may still occur.

## 4. Why Are Classpath Conditions Checked Early?

`@ConditionalOnMissingClass` uses Spring Boot's `OnClassCondition`. When Spring analyzes configuration, Boot can evaluate class name presence without necessarily instantiating classes or creating business beans.

In the auto-configuration mechanism:

```text
@SpringBootApplication
  -> @EnableAutoConfiguration
    -> find candidates from AutoConfiguration.imports
      -> select / filter matching candidates
        -> check @Conditionals on the @AutoConfiguration class
          -> check nested configurations and @Beans
            -> register valid BeanDefinitions
              -> create beans per BeanFactory/lifecycle
```

The diagram above illustrates only the major stages. Some optimization filters may decide earlier than detailed configuration class analysis, using metadata generated during compilation. Condition evaluation, imports, and bean definition processing order have implementation details that the diagram intentionally omits.

Importantly: **a class condition selects configuration based on the classpath environment**, not arbitrary `Class.forName(...)` calls in business code. Spring Boot supports annotation metadata reading paths that can use ASM to check conditions without immediately loading the described class.

### Metadata and Annotations

For library-provided auto-configuration, an annotation processor can generate:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Static information can assist the candidate filtering step. It is **different** from the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

The `.imports` file supplies **candidate class names**, whereas metadata `.properties` assists **condition optimization**. And both differ from `spring-configuration-metadata.json`, which serves IDE/tooling for configuration keys.

Do not infer that missing metadata prevents fallback features from working. Spring still has the standard condition evaluation path when a candidate is processed; optimization metadata does not replace the source of truth, which is the annotations together with the runtime classpath.

## 5. Placing Conditions on Configuration Classes Instead of Only on @Bean Methods

Consider a hypothetical module depending on an optional SDK:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.OptionalClient")
class VendorClientConfiguration {

    @Bean
    VendorClientAdapter adapter(com.vendor.sdk.OptionalClient client) {
        return new VendorClientAdapter(client);
    }
}
```

This is an **illustrative snippet, not independently compilable**: `VendorClientAdapter` and `OptionalClient` belong to hypothetical classes. When the SDK is absent, this branch's class or method signatures can cause class loading issues if referenced before the condition gets a chance to intervene.

Spring Boot recommends placing **class conditions on a separate configuration class** to isolate `@Bean` method signatures that depend on optional libraries. Using a static nested `@Configuration(proxyBeanMethods=false)` or a standalone configuration class are common approaches.

Example of organizing two branches:

```java
@AutoConfiguration
class ClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.OptionalClient")
    static class VendorConfiguration {
        // Only define beans using the SDK when the SDK is present.
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("com.vendor.sdk.OptionalClient")
    static class FallbackConfiguration {
        // Define fallback beans without needing the SDK.
    }
}
```

This is schematic code showing class organization. The key point: **the fallback branch must not import, return, or inject types that only exist in the missing SDK**. Return an interface/type belonging to the module's core API so dependency injection does not require the absent class.

`@ConditionalOnMissingClass` can be placed on a method, but if the method's **return type** or **parameters** themselves are a potentially missing class, the JVM may need to resolve method metadata before the condition can protect the program. Therefore you should not rely solely on an annotation placed on an `@Bean` method to hide a signature that uses an optional SDK.

### Case of Composed Annotations (Meta-Annotations)

Spring Boot notes that when wrapping classpath conditions in a composed annotation, you should use **string class names** for optional classes, because the safety of class literals when placed directly is not guaranteed in the same way through a meta-annotation layer.

With `@ConditionalOnMissingClass`, the string form is already mandatory; with `@ConditionalOnClass`, when designing a composed annotation, use `name` instead of a class literal.

## 6. Designing a Fallback: One Abstraction, Two Implementations

Suppose a library provides an abstraction:

```java
public interface MessageFormatter {
    String mode();
}
```

There are two implementations:

- `basic`: does not depend on any external SDK.
- `jackson-ready`: registered only when `com.fasterxml.jackson.databind.ObjectMapper` is present at runtime.

In the hands-on example, the `jackson-ready` branch **only simulates the strategy selection decision**; it does not implement JSON serialization with Jackson. This keeps the example free of optional class dependencies in Java signatures, so we can observe the exact effect of adding/removing a dependency on the classpath.

The corresponding conditions:

```java
@ConditionalOnMissingClass("com.fasterxml.jackson.databind.ObjectMapper")
```

and:

```java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
```

For the same class name, these two conditions are **complementary** assuming a consistent classloader evaluation: when absent, choose the basic branch; when present, choose the jackson-ready branch. This is an essential pattern for designing fallbacks without scattering `if/else` dependency checks across every service.

### Decision Table

| `ObjectMapper` at runtime? | MissingClass | OnClass | Expected bean |
| --- | --- | --- | --- |
| No | Match | No match | `basic` |
| Yes | No match | Match | `jackson-ready` |

When branches define the same type, conditions must be **explicitly mutually exclusive**. If written asymmetrically, both branches could create the bean and trigger `NoUniqueBeanDefinitionException` or bean name collisions.

In real production auto-configuration, you should also combine `@ConditionalOnMissingBean` if the intent is to allow applications to replace the default implementation themselves; classpath conditions alone only choose based on class presence/absence, **not whether a user-supplied bean takes priority**.

## 7. Runnable Java 17 + Spring Boot 3.3.13 Example

The example creates a non-web Maven application, registering custom auto-configuration via `.imports`. Run two builds from the **same source**:

1. The default build has only `spring-boot-starter`, without adding Jackson Databind to dependencies: selects the `basic` fallback.
2. The build using Maven profile `with-jackson` adds `jackson-databind`: selects the `jackson-ready` strategy.

**Note:** The strategy name `jackson-ready` demonstrates the **classpath condition**; it is not an actual JSON codec yet. In a real integration, classes in the Jackson-present branch can call `ObjectMapper`, provided classes are structured so the classloader does not touch optional types when the SDK is absent.

### 7.1. File Structure

```text
missing-class-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── api/
    │   │   └── MessageFormatter.java
    │   ├── app/
    │   │   └── MissingClassDemoApplication.java
    │   └── autoconfigure/
    │       └── MessageAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`demo.app` and `demo.autoconfigure` are **sibling** packages, so the default `@ComponentScan` of the main class in `demo.app` does not discover `MessageAutoConfiguration`. This class is loaded via the **auto-configuration mechanism** as intended.

### 7.2. pom.xml with an Optional Profile

**`pom.xml`:**

```xml
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

    <groupId>demo</groupId>
    <artifactId>missing-class-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <profiles>
        <profile>
            <id>with-jackson</id>
            <dependencies>
                <dependency>
                    <groupId>com.fasterxml.jackson.core</groupId>
                    <artifactId>jackson-databind</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

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

The version of `jackson-databind` is managed by the Spring Boot starter parent/dependency management for Boot 3.3.13. Do not add arbitrary versions just to test classpath conditions.

**Distinguishing the two builds:** Maven `clean` on each build deletes the previous JAR and creates a new JAR with the same name. To compare against the old build later, run and record the output **before building the new one**, or intentionally save the two artifacts at separate paths.

### 7.3. Interface Independent of Jackson

**`src/main/java/demo/api/MessageFormatter.java`:**

```java
package demo.api;

public interface MessageFormatter {
    String mode();
}
```

The interface belongs to the project's own code and has no imports from Jackson. This is the core of a fallback: services depend on a stable abstraction, not on an SDK that might not exist.

### 7.4. Auto-Configuration with Two Static Nested Configurations

**`src/main/java/demo/autoconfigure/MessageAutoConfiguration.java`:**

```java
package demo.autoconfigure;

import demo.api.MessageFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class MessageAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass(
        "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class BasicConfiguration {

        @Bean
        MessageFormatter selectedMessageFormatter() {
            return () -> "basic";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
        name = "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class JacksonAvailableConfiguration {

        @Bean
        MessageFormatter selectedMessageFormatter() {
            return () -> "jackson-ready";
        }
    }
}
```

In this file:

- `@AutoConfiguration` marks the main class as an auto-configuration candidate.
- `BasicConfiguration` is allowed to participate in processing **when** `ObjectMapper` **is absent** from the classpath.
- `JacksonAvailableConfiguration` is allowed to participate in processing **when** `ObjectMapper` **is present**.
- Both provide a bean of type `MessageFormatter`, with the same bean name `selectedMessageFormatter`, but only one branch matches between the two symmetrical configurations.
- The `@Bean` methods return the shared interface, independent of Jackson; when Jackson is missing, the JVM is not forced to resolve SDK classes from return types.
- `static class` ensures the nested configurations do not require an enclosing instance of the outer class.
- `proxyBeanMethods=false` is suitable because these `@Bean` methods do not call each other.

This code omits `@ConditionalOnMissingBean` so the lesson stays focused on **classpath conditions**. If users need to replace the default bean, extend the auto-configuration with bean conditions in the right place and thoroughly test the case where a user bean is present.

### 7.5. Registering the Candidate in the .imports Resource

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

```text
demo.autoconfigure.MessageAutoConfiguration
```

This path must be exact. If `.imports` is missing, Boot 3.x will not discover the example's auto-configuration via the metadata path meant for auto-configuration. Do not work around this by putting `MessageAutoConfiguration` in a broad package and scanning it as an application component.

### 7.6. Main Class and ApplicationRunner

**`src/main/java/demo/app/MissingClassDemoApplication.java`:**

```java
package demo.app;

import demo.api.MessageFormatter;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class MissingClassDemoApplication {

    private static final String JACKSON_CLASS =
        "com.fasterxml.jackson.databind.ObjectMapper";

    public static void main(String[] args) {
        SpringApplication.run(MissingClassDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSelection(MessageFormatter formatter) {
        return args -> {
            boolean present = ClassUtils.isPresent(
                JACKSON_CLASS, getClass().getClassLoader());

            System.out.println("JACKSON_PRESENT: " + present);
            System.out.println("SELECTED: " + formatter.mode());
        };
    }
}
```

`ClassUtils.isPresent(...)` is used here **only to print the classpath state during the demo**. The actual decision-making mechanism lies in `@ConditionalOnMissingClass` and `@ConditionalOnClass` on `MessageAutoConfiguration`. In production code, there is no need to call `ClassUtils` everywhere to duplicate the condition's job.

`ApplicationRunner` receives the `MessageFormatter` bean provided by auto-configuration. If neither condition matches or another classpath issue leaves no bean available, the application will fail-fast due to being unable to inject the dependency — which is also a helpful signal when testing the setup.

### 7.7. Running Without Jackson

In the `missing-class-demo` directory, with **JDK 17+ and Maven**, run:

```bash
mvn -q -DskipTests clean package
java -jar target/missing-class-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

With the dependencies declared in the example's default profile, aside from the Spring Boot banner and logs, the two lines printed by `ApplicationRunner` are:

```text
JACKSON_PRESENT: false
SELECTED: basic
```

**Reason:** Basic `spring-boot-starter` does not declare Jackson Databind. `com.fasterxml.jackson.databind.ObjectMapper` is absent; `@ConditionalOnMissingClass` matches, and the `BasicConfiguration` branch registers the `selectedMessageFormatter` bean. The `JacksonAvailableConfiguration` branch does not match.

If an environment modifies the POM or adds a transitive dependency that brings the Jackson class in, the output can differ. In that case the condition is not wrong: inspect the actual dependency tree.

### 7.8. Running With Jackson

Next, rebuild the same source with the Maven profile:

```bash
mvn -q -Pwith-jackson -DskipTests clean package
java -jar target/missing-class-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Expected two lines:

```text
JACKSON_PRESENT: true
SELECTED: jackson-ready
```

Because the `with-jackson` profile adds `jackson-databind`, the runtime classpath inside the executable JAR contains `ObjectMapper`. The **missing** condition no longer matches, while the **present** condition matches. The other branch provides a `MessageFormatter` bean.

`jackson-ready` is just a label to observe branch selection. It **does not assert** that the program created an `ObjectMapper` bean or performed JSON serialization. Another Boot auto-configuration may create an `ObjectMapper` if its own conditions match, but that is a separate bean/infrastructure concern.

### 7.9. Comparing the Two Builds

| Characteristic | Build without profile | Build with `-Pwith-jackson` |
| --- | --- | --- |
| `ObjectMapper` class at runtime | No | Yes |
| `@ConditionalOnMissingClass` | Match | No match |
| `@ConditionalOnClass` | No match | Match |
| Injected `MessageFormatter` | Basic strategy | Jackson-ready strategy |
| `SELECTED` output line | `basic` | `jackson-ready` |
| Need to edit Java source? | No | No |
| Need a web server? | No | No |

The experiment shows that **the same configuration code** can adapt behavior based on library availability at runtime, rather than using scattered `if` statements inside services.

## 8. Practical Approach When an SDK Is Completely Absent

In the previous example both branches merely returned a strategy name. In a real integration, the SDK branch typically has an implementation that needs to import SDK classes. To avoid `NoClassDefFoundError`, separate classes cleanly by package and condition:

```text
com.acme.integration.api
  └── ClientGateway.java                   (stable interface)

com.acme.integration.basic
  └── BasicClientGateway.java              (uses only JDK/Spring core)

com.acme.integration.sdk
  └── SdkClientGateway.java                (depends on optional SDK)

com.acme.integration.autoconfigure
  └── ClientAutoConfiguration.java
       ├── FallbackConfiguration          (@ConditionalOnMissingClass)
       └── SdkConfiguration               (@ConditionalOnClass)
```

In auto-configuration, do not use `SdkClientGateway` in the signature of the **fallback branch**. If the SDK branch needs optional classes, isolate it in a configuration guarded by a class-level condition before method signatures are analyzed.

Dependencies must be examined from two angles:

1. **Compile:** the module containing `SdkClientGateway` must have the SDK on its compile classpath; you can use an optional dependency or a separate module layout.
2. **Runtime:** the starter/consuming application may omit the SDK. Classes depending on the SDK must not be loaded in the absent branch.
3. **Condition:** check a characteristic class of the SDK; avoid checking a class that is too generic and might be pulled in by another library.
4. **Contract:** all implementations must return a shared interface that the application can inject.

Place auto-configuration in a package **outside the application's component-scan area** and declare the candidate in `.imports`. Avoid letting `@ComponentScan` scan the entire library package, because classes depending on the SDK could be scanned unintentionally.

## 9. Edge Cases to Understand Precisely

### 9.1. An Absent Class Differs from a Class That Fails to Load Due to Missing Sub-Dependencies

It is possible for `com.vendor.sdk.Client` to exist in a JAR yet fail to load because one of its dependent types is missing, or due to a classloader/module error. Do not lump all class loading errors together as “SDK not installed”. Classpath conditions evaluate class visibility in the classloader, whereas actual execution can still encounter class linkage errors (`LinkageError`), module access issues, or missing native libraries.

If the SDK branch is selected and bean creation fails, read the root cause instead of switching to a fallback after an exception has occurred. Fallback via `@ConditionalOnMissingClass` is a **startup configuration decision**, not a runtime retry/circuit-breaker fallback mechanism.

### 9.2. Maven Dependency Exists, Yet Condition Still Reports Missing

Check:

- Dependency scope (`test`, `provided`, `runtime`, `compile`) and executable JAR packaging.
- Whether the dependency was excluded or omitted by a profile/variant.
- Whether the library renamed packages/classes across versions.
- Whether you are running the newly built JAR.
- Whether the app uses a custom classloader or a different module path.

Maven `dependency:tree` is useful for finding resolved versions, but it does not replace checking the **runtime classpath** of the actual process. For a Spring Boot executable JAR, you can inspect libraries inside the archive with `jar tf`.

### 9.3. Class Exists, but No Bean Exists Yet

`@ConditionalOnMissingClass("com.vendor.sdk.Client")` will **not match** if the class already exists, even if there is no `Client` bean. If you need rules based on bean presence, look at `@ConditionalOnBean`/`@ConditionalOnMissingBean`. If an SDK branch should only activate when the user enables a feature, add an appropriate property condition.

### 9.4. Multiple Classes in the Condition

With:

```java
@ConditionalOnMissingClass({
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

the condition only matches when **all listed class names cannot be found**. If the intent is to fall back when **at least one** of the two classes is missing, the representation must be redesigned, because a list in one annotation does not mean “OR of absences”.

A simple solution for a standard SDK is to choose **one characteristic class** representing integration availability. If a feature needs multiple classes, check the required list with `@ConditionalOnClass(name = {...})` on the advanced branch, then design the fallback branch so it covers the exact remaining domain. Do not assume that two annotations with multi-element class lists are automatically logical complements of each other.

### 9.5. Combining Conditions with @ConditionalOnMissingBean

A library wanting users to be able to configure their own bean can add:

```java
@Bean
@ConditionalOnMissingBean(MessageFormatter.class)
MessageFormatter defaultFormatter() {
    return ...;
}
```

This is an illustrative snippet. Classpath conditions first decide which branch is eligible; bean conditions allow the default to **back off** when the application has already registered a matching custom bean. `@ConditionalOnMissingBean` has nuances regarding type/name, context hierarchy, and evaluation timing; use it in auto-configuration and test the user-defined bean scenario.

Do not confuse default bean back-off with **bean overriding** (overwriting definitions with the same name) or `@Primary` (prioritizing when injecting among multiple beans). They are different mechanisms.

## 10. Are @ConditionalOnMissingClass and @ConditionalOnClass Always Interchangeable Complements?

With a **single class**, they express the two states of class presence/absence quite intuitively:

```java
@ConditionalOnMissingClass("com.example.OptionalApi")
```

versus:

```java
@ConditionalOnClass(name = "com.example.OptionalApi")
```

However, when combining conditions, you must inspect the **entire logical expression**.

For example:

```text
Advanced branch: has A AND has B
Fallback branch: lacks A AND lacks B
```

Those two branches **do not cover** the two intermediate cases:

```text
has A, lacks B
lacks A, has B
```

Therefore, for a library needing two classes to run, you should not write two configurations like above and assume exactly one bean will always be created. You can:

- Choose one marker class that accurately reflects “SDK is usable” at the configuration level.
- Split conditions into smaller capabilities.
- Write a custom condition only when built-in annotations cannot express the requirement clearly.
- Add tests for every realistic classpath combination.

**Design a case matrix before writing conditions**; this reduces the bug where “some classes are present yet neither branch matches”.

## 11. When to Use a Runtime Fallback Instead of a Startup Fallback?

`@ConditionalOnMissingClass` fits **fixed deployment environment** decisions: whether the application has or lacks a library at startup.

If the SDK is present but an external service has a network error, the class still exists; `@ConditionalOnMissingClass` **will not switch to the fallback**. To handle runtime availability, different mechanisms are needed:

- Controlled business error handling that returns an appropriate fallback value.
- Bounded timeouts, retries, and circuit breakers when needed.
- Health checks/observability to detect unresponsive dependencies.
- Feature flags/properties to intentionally switch configuration on the next restart, if architecture permits.

Do not use classpath conditions to replace resilience. A branch selected at startup does not mean it will switch automatically while the application is running.

## 12. Diagnosing with the Conditions Evaluation Report

Spring Boot can print a condition report when run with `--debug`:

```bash
java -jar target/missing-class-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Look for entries such as `BasicConfiguration` and `JacksonAvailableConfiguration`. Depending on version/logging, the report shows whether classpath conditions matched or did not match and which classes were evaluated.

Information groups:

- **Positive matches**: conditions that matched.
- **Negative matches**: conditions that did not match; usually accompanied by a reason.
- **Exclusions**: explicitly excluded auto-configurations.

The condition report answers **why a configuration/bean definition was selected or skipped**, not a report of whether every instance was successfully instantiated. If the context fails afterwards, read the exception and the `Caused by` chain.

To be certain the runtime classpath has Jackson, check the demo output or inspect the JAR:

```bash
jar tf target/missing-class-demo-0.0.1-SNAPSHOT.jar
```

In a fat JAR, dependencies normally live in `BOOT-INF/lib/`. If you need to search specifically, use an OS-appropriate text search tool; there is no need to rely on Bash when running on Windows.

### Quick Debugging Workflow

1. Check the exact class name string: is `com.fasterxml.jackson.databind.ObjectMapper` spelled accurately?
2. Check that the running JAR contains the expected dependency.
3. Check that the annotation is placed **on the right configuration class**, especially if a method returns an optional class.
4. Check that auto-configuration is loaded via `.imports` and not excluded.
5. Enable `--debug` and look for OnClassCondition results.
6. Check `@ConditionalOnMissingBean`/other properties if the branch matched yet the bean was not registered.
7. If the bean has a definition yet fails during creation, read the root cause; do not treat that as `MissingClass` failing to match.

## 13. Common Mistakes and How to Fix Them

### Mistake 1: Using @ConditionalOnMissingClass(name = "...")

`@ConditionalOnMissingClass` has no `name`. Use:

```java
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

### Mistake 2: Using a Class Literal for a Class Absent from Dependencies

Do not use:

```java
// WRONG: the annotation requires strings, does not accept Client.class.
@ConditionalOnMissingClass(com.vendor.sdk.Client.class)
```

Besides the wrong type, the code cannot even compile if the SDK is not on the compile classpath. Use a fully qualified class name string to represent a potentially missing dependency.

### Mistake 3: Placing the Annotation Only on an @Bean Method Whose Return Type Belongs to an Optional SDK

If the JVM resolves the method signature before the condition, the application may throw a class loading error. Extract a static nested `@Configuration` with a class-level condition and keep the fallback free of SDK class references.

### Mistake 4: Using MissingClass When Only an Unconfigured Bean Is Missing

If the JAR is present, MissingClass will not match regardless of whether a bean was created. Use the appropriate BeanCondition instead.

### Mistake 5: SDK Exists on Maven, but Runtime Class Changed Packages

The condition evaluates **specific class names** in the runtime classloader. If a vendor moves `com.old.Client` to `com.new.Client`, checking the old name can report missing even though the new SDK is present. Read the API documentation for the exact SDK version.

### Mistake 6: Automatically Scanning Every Package of the Library

A class depending on the SDK can be processed by the scanner outside the intended configuration. Auto-configuration should reside outside the application's component-scan scope, be declared via `.imports`, and use explicit `@Import` for auxiliary configurations.

### Mistake 7: Not Handling User-Written Beans

Classpath conditions do not automatically yield to another bean of the same type. Add `@ConditionalOnMissingBean` if the default configuration needs to back off, and test custom beans.

### Mistake 8: Calling Class.forName in a Constructor to Decide the Fallback

Once a bean's constructor is invoked, definition selection has already occurred. Let auto-configuration choose the branch beforehand; use reflection only when a module genuinely needs a dynamic runtime adapter with a clearly controlled contract.

### Mistake 9: Assuming an Absent Class Means the Dependency Is Always Absent

The classpath can be assembled from transitive JARs, plugins, or classes provided by a special classloader. Verify actual classes, not just a single `dependency` line in the POM.

### Mistake 10: Treating the Condition as a Solution for Network Errors When the SDK Is Present

MissingClass relies solely on the classpath. Circuit breakers, retries, and timeouts are separate solutions for runtime failures.

## 14. Checklist for Auto-Configuration Authors

Before publishing a starter with a classpath-based fallback, verify:

1. **Stable abstraction:** application services inject an interface/core API independent of the SDK.
2. **Accurate classpath marker:** the class checked for presence/absence genuinely reflects the desired capability.
3. **Complete conditions:** main and fallback branches are mutually exclusive and cover the exact supported classpath combinations.
4. **Class-loading isolation:** `@Bean` methods with SDK signatures sit in configuration classes guarded by conditions; the fallback branch does not import the SDK.
5. **Bean override/back-off:** add bean conditions when users need to supply custom implementations.
6. **Registration:** auto-configuration names are in `AutoConfiguration.imports`; do not arbitrarily scan library packages.
7. **Build matrix:** test when the SDK is absent, present, and present with an incompatible version.
8. **Diagnostics:** inspect the Conditions Evaluation Report, root causes, and dependency tree.
9. **Lifecycle:** distinguish an unregistered bean definition from a registered bean definition that failed to instantiate.
10. **Tests:** in a dedicated module, you can use `ApplicationContextRunner` and filtered classloaders (`FilteredClassLoader`) from the test library to simulate absent classes without manually building multiple JARs.

`ApplicationContextRunner` and `FilteredClassLoader` are Spring Boot testing tools, not imported into the example's production files. They are well suited for automatically verifying both condition branches in CI.

## 15. Self-Check Questions

**Question 1.** Does `@ConditionalOnMissingClass` check beans or classes?

**Answer:** It checks the **absence of classes with the specified names** in the effective classpath/classloader when the condition is evaluated. It does not check bean instances.

**Question 2.** Does the `name` attribute exist on `@ConditionalOnMissingClass`?

**Answer:** No. Spring Boot 3.3.x uses the `value` attribute of type `String[]`; you can write `@ConditionalOnMissingClass("fully.qualified.ClassName")`.

**Question 3.** If Jackson Databind is missing, which branch does the Maven example select?

**Answer:** `BasicConfiguration`, because `com.fasterxml.jackson.databind.ObjectMapper` is absent and the `@ConditionalOnMissingClass` condition matches.

**Question 4.** Why is `MessageFormatter` an interface in the core API instead of directly using ObjectMapper in the fallback return type?

**Answer:** The fallback branch must compile and run when the optional library is absent; using an SDK-independent abstraction avoids unnecessary class loading and keeps DI stable.

**Question 5.** When the `ObjectMapper` class is present yet no `ObjectMapper` bean exists, does MissingClass match?

**Answer:** No. The condition is classpath-based; bean presence is a separate condition.

**Question 6.** If two classes A and B are listed in `@ConditionalOnMissingClass`, does only one need to be missing for the condition to match?

**Answer:** No. With multiple names in this annotation, the condition expects all listed classes to be absent.

**Question 7.** Why is placing a class-level condition on a nested configuration safer than placing it on a method returning an SDK type?

**Answer:** Spring can skip the entire optional configuration class before the JVM needs to resolve a method signature using SDK classes, reducing the risk of `NoClassDefFoundError`.

**Question 8.** If an SDK is present but calling the server times out, does it trigger the MissingClass fallback?

**Answer:** No. That is a runtime failure; use resilience/timeouts/circuit breakers per system requirements.

**Question 9.** Are class names in `.imports` the SDK class names for MissingClass to check?

**Answer:** No. `.imports` lists the **module's auto-configuration classes**; the `MissingClass` annotation contains the **optional class names to check**.

**Question 10.** Does a matching condition guarantee the bean is ready?

**Answer:** No. Other conditions may still exclude the bean, or the bean may have a definition yet fail to instantiate or be lazy-initialized.

## 16. References

- Spring Boot 3.3.13, `ConditionalOnMissingClass` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html
- Spring Boot 3.3.13, `ConditionalOnClass` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3, Developing Auto-configuration / Class Conditions: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Framework, Classpath Scanning: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
