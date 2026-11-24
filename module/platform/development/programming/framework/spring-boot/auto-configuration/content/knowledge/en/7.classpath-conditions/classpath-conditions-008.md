# Composed Annotations with Class Conditions and When to Use Class Names

## 1. Problem to Solve

A library integrating with Spring Boot often has optional features. When an application has an SDK on its classpath, auto-configuration is allowed to register adapters for that SDK; when the SDK is absent, configuration must skip the integration branch or choose a fallback.

Spring Boot provides two built-in annotations for classpath-based decisions:

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

These two lines are **two separate examples** of presence and absence conditions; do not attach both simultaneously to the same configuration and expect both to match.

To reuse rules, we can create a **composed annotation** such as `@WhenJacksonPresent` and place `@ConditionalOnClass` **on that annotation's definition**. This is precisely where a crucial safety rule applies:

> **When `@ConditionalOnClass` is used as a meta-annotation, use the `name` attribute with a string class name, not `value` with `SomeClass.class`.**

Spring Boot 3.3.13 states explicitly: when a class condition is attached **directly to an `@Configuration` class**, ASM metadata reading allows using a class literal even if that class is absent at runtime; **that guarantee does not apply equivalently when the annotation is wrapped through a meta-annotation layer**. Hence composed annotations must use string class names.

This lesson explains the difference between direct and composed annotations, how to choose conditions, class-loading limits, a Java 17/Spring Boot example running on two classpaths, and common pitfalls.

## 2. Direct Annotations and Composed Annotations

### 2.1. Condition Placed Directly on a Configuration Class

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
class VendorClientConfiguration {
}
```

This is an illustrative snippet; appropriate Spring imports are needed. `@ConditionalOnClass` is attached **directly** to the target element. Spring Boot uses `OnClassCondition` to check whether the class with the specified name is present on the classpath.

For a class type present at **compile time** yet potentially missing at **runtime**, the following syntax is also supported by Spring Boot on a directly annotated configuration class:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(com.vendor.sdk.Client.class)
class VendorClientConfiguration {
}
```

This is an illustrative snippet that **will not compile unless the SDK is on the compile classpath**. What Spring Boot guarantees is that inspecting direct annotations via ASM metadata can avoid loading the SDK class itself just to evaluate the condition on the configuration class. It does not guarantee a Java program can compile without the corresponding dependency.

### 2.2. Condition Wrapped into a Reusable Annotation

When another annotation carries `@ConditionalOnClass`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public @interface RequiresVendorClient {
}
```

then `@RequiresVendorClient` is a **composed annotation**. Spring can discover `@ConditionalOnClass` as its meta-annotation. Configuration classes only need to declare:

```java
@Configuration(proxyBeanMethods = false)
@RequiresVendorClient
class VendorClientConfiguration {
}
```

The snippets above are illustrative only; compiling requires `java.lang.annotation.*` and Spring imports. The runnable example later provides every file in full.

Layering:

```text
VendorClientConfiguration
    |
    | @RequiresVendorClient                (direct annotation)
    v
RequiresVendorClient
    |
    | @ConditionalOnClass(name = "...")    (meta-annotation)
    v
OnClassCondition
    |
    v
Check classpath -> select/skip config
```

A composed annotation lets you name rules in domain language: “requires vendor X's client”, “only runs with driver Y”, or “when JSON module is present”, instead of scattering class name strings across every configuration.

### 2.3. Unsafe Example as a Meta-Annotation

Do not design it like this:

```java
// NOT RECOMMENDED for composed annotations:
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(com.vendor.sdk.Client.class)
public @interface RequiresVendorClient {
}
```

The issue is that **this is `@ConditionalOnClass` sitting on a composed annotation**, no longer direct metadata reading on the target configuration class. Per Boot documentation, the guarantee of avoiding class literal resolution when a class may be missing does not apply to meta-annotations. Additionally, a class literal requires the dependency at compile time.

Solution:

```java
// RIGHT: express the optional class by its fully qualified name.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public @interface RequiresVendorClient {
}
```

This is not merely a matter of syntax style; it determines whether a starter can operate safely when an optional dependency is omitted from runtime.

## 3. Why Use String Class Names?

The two attributes of `@ConditionalOnClass` (Spring Boot 3.3.x) have different types:

| Attribute | Data type | Example |
| --- | --- | --- |
| `value` | `Class<?>[]` | `@ConditionalOnClass(Foo.class)` |
| `name` | `String[]` | `@ConditionalOnClass(name = "com.example.Foo")` |

`SomeClass.class` is a Java class literal. A class must exist at compile time for source to reference that type directly. At runtime, reading, synthesizing, and resolving annotations can touch class references. **If a type may be absent and the condition is wrapped in a meta-annotation, use `name` so Spring checks by string without having to resolve that class literal first.**

Do not oversimplify to “using `value` always fails”. The exact distinction is:

- On an `@Configuration` class with `@ConditionalOnClass` **directly**, Boot has an ASM bytecode/metadata reading mechanism to evaluate safely, even if the specified class may not be on the runtime classpath.
- On a **composed annotation**, Boot does not promise an equivalent safety mechanism for `Class<?>` references inside the meta-annotation; **choose `name`**.
- When a condition is placed on an **`@Bean` method**, the method signature can force the JVM to process an absent type **before** the method condition is applied. Use a separate configuration class with a class-level condition to isolate those methods.
- With string class names, you still must write the exact **fully qualified class name**, including the package. Typos will cause the condition to check the wrong class.
- `name` does not automatically install dependencies. It only expresses the condition to check.

Boot 3.3.13 documentation highlights both distinctions: **meta-annotations** and **method-level class loading**. They are two different risks with two complementary solutions.

## 4. @ConditionalOnMissingClass as a Meta-Annotation

Sometimes we need a composed annotation expressing that a class is **absent**:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnMissingClass("com.vendor.sdk.Client")
public @interface WithoutVendorClient {
}
```

`@ConditionalOnMissingClass` in Spring Boot 3.3.x has a **`value` attribute of type `String[]`**, and no `name` attribute. Therefore the following is **wrong**:

```java
// WRONG: ConditionalOnMissingClass does not declare a name attribute.
@ConditionalOnMissingClass(name = "com.vendor.sdk.Client")
```

Do not mechanically apply “every classpath condition must write `name`” to the missing-class annotation. The exact rule:

```text
@ConditionalOnClass:
  - value = Class<?>[]; direct class-level has ASM support
  - name  = String[]; SHOULD/MUST be used for composed meta-annotations

@ConditionalOnMissingClass:
  - value = String[]; already uses string class names
  - has no name attribute
```

Overview docs sometimes say “use class names when writing meta-annotations” for both groups. When translating into concrete Java code, read the corresponding API signature: `@ConditionalOnClass(name = "...")` versus `@ConditionalOnMissingClass("...")`.

### Conditions with Multiple Classes

For example:

```java
@ConditionalOnClass(name = {
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

requires **all** listed classes to be present.

Conversely:

```java
@ConditionalOnMissingClass({
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

requires **all** listed classes to be absent. This is not an “only one missing class is enough” condition. If the main feature only works when both A and B are present, two annotations like those above do not automatically ensure the fallback works in the two cases where A is present/B is absent and A is absent/B is present. You must design the classpath matrix accurately.

## 5. How Does Spring Process Composed Annotations?

At the Spring configuration level:

```text
@Configuration or @AutoConfiguration
  -> read AnnotationMetadata / AnnotatedTypeMetadata
  -> discover direct annotations, meta-annotations
  -> read attributes and evaluate @Conditional annotations
  -> register BeanDefinition when conditions match
  -> BeanFactory creates beans per scope and dependencies
```

Spring Framework has the **`MergedAnnotations`** model to handle direct annotations, meta-annotations, and aliasing/composition cases. However, **being able to read meta-annotations** does not mean **every form of Class literal is safe** on a classpath lacking dependencies. Spring's metadata reading APIs and mechanisms for avoiding optional class loading must be used together properly.

Some APIs you may see in the framework or custom conditions:

```java
AnnotatedTypeMetadata metadata = ...; // example of an already-provided variable
boolean found = metadata.isAnnotated("com.example.RequiresVendorClient");
Map<String, Object> attributes =
    metadata.getAnnotationAttributes(
        "org.springframework.boot.autoconfigure.condition.ConditionalOnClass");
```

This illustrative snippet **does not compile standalone** because it lacks the `metadata` variable source and imports. It merely shows that annotation metadata can be retrieved by string class name. In `Condition.matches(...)`, Spring passes the metadata of the evaluated class or method into the corresponding parameter.

**`AnnotationMetadata`** describes class-level metadata. **`MethodMetadata`** describes method-level metadata. Both extend `AnnotatedTypeMetadata`. A condition can use the common API when inspecting annotation attributes, yet must not cast every metadata object to `AnnotationMetadata`: when a condition sits on an `@Bean` method, the metadata may be `MethodMetadata`.

To inspect environment properties, bean definitions, or classloaders, use `ConditionContext`, rather than expecting annotation metadata to contain all of `application.properties`.

## 6. Combining with @AutoConfiguration and @Import

Composed annotations often appear in auto-configuration modules developed by libraries. A valid auto-configuration in Spring Boot 3.x is registered in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example:

```text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
```

`AutoConfiguration.imports` is a candidate list; selected classes must still satisfy conditions. It **differs** from `spring-autoconfigure-metadata.properties` used to speed up filtering, and differs from `spring-configuration-metadata.json` used by IDEs/tooling.

A general structure:

```java
@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @RequiresVendorClient
    static class VendorConfiguration {
        // @Bean methods using the SDK when the SDK is present.
    }
}
```

This is an illustrative snippet because it needs the `@RequiresVendorClient` declaration and imports. `@RequiresVendorClient` uses `@ConditionalOnClass(name="...")`, allowing the SDK branch configuration to be skipped when the optional class is absent.

**Do not put `@ComponentScan` to scan the entire library inside an auto-configuration.** If there are multiple auxiliary configuration classes, use explicit `@Import` or conditional nested `@Configuration` classes. At the same time, place `@AutoConfiguration` classes in a package **outside the application's default component-scanning scope**, so Boot discovers them via `.imports` rather than unintended scanning.

**Classpath conditions are not a bean override policy.** If users should be able to supply their own implementation, consider `@ConditionalOnMissingBean` on default beans. That condition inspects **bean definitions** at evaluation time, not class absence.

## 7. Runnable Example: Two Composed Annotations and Two Classpath Environments

We create a **Java 17 + Spring Boot 3.3.13 + Maven** application with two composed annotations:

- `@WhenJacksonPresent`: meta-annotated with `@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")`.
- `@WhenJacksonAbsent`: meta-annotated with `@ConditionalOnMissingClass("com.fasterxml.jackson.databind.ObjectMapper")`.

Two `static` nested configuration classes are marked with these two annotations and provide the **same interface** `ModeService`. The app is built twice using a Maven profile: without Jackson Databind and with Jackson Databind. This verifies classpath conditions without needing Jackson to perform real serialization.

### 7.1. File Tree

```text
composed-annotation-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── api/
    │   │   └── ModeService.java
    │   ├── app/
    │   │   └── ComposedAnnotationApplication.java
    │   ├── condition/
    │   │   ├── WhenJacksonPresent.java
    │   │   └── WhenJacksonAbsent.java
    │   └── autoconfigure/
    │       └── ModeAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`demo.app` and `demo.autoconfigure` are **sibling packages**. The main class belongs to `demo.app`, so default component scanning does not load `ModeAutoConfiguration` by scanning `demo.autoconfigure`. Boot loads it from `.imports`. Custom annotations are only used as metadata by the compiler and Spring, without becoming beans.

### 7.2. pom.xml: Default Dependencies and Optional Profile

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

    <groupId>example</groupId>
    <artifactId>composed-annotation-demo</artifactId>
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

`spring-boot-starter-parent` manages the version of `jackson-databind`. Do not pin an arbitrary Jackson version when only testing presence. The `with-jackson` profile changes the **build's dependencies**, not just a runtime property.

The build without the profile must run and record output **before** building with the profile, since `clean package` afterwards overwrites the same-named JAR. No two different source trees are needed.

### 7.3. Stable API, Independent of Jackson

**`src/main/java/demo/api/ModeService.java`:**

```java
package demo.api;

@FunctionalInterface
public interface ModeService {
    String mode();
}
```

Consumers depend only on the `ModeService` interface. Its signature requires no `ObjectMapper` or Jackson classes; therefore the fallback branch can compile and run when the Jackson library is absent.

### 7.4. Composed Annotation Selecting When Jackson Is Present

**`src/main/java/demo/condition/WhenJacksonPresent.java`:**

```java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
public @interface WhenJacksonPresent {
}
```

The most important point sits in the annotation definition:

```java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
```

`@ConditionalOnClass` is a **meta-annotation** of `@WhenJacksonPresent`, so we use a string class name. This Java file **does not import Jackson** and still compiles when the POM lacks `jackson-databind`.

If the annotation were written with `@ConditionalOnClass(ObjectMapper.class)`, the module would need a Jackson compile dependency, and meta-annotation resolution at runtime when the class is absent would lack the same safety guarantee as the string form. Hence we do not pick a class literal in composed annotations for optional libraries.

`@Target(ElementType.TYPE)` is deliberate: the annotation is used on **configuration classes**, guarding an entire group of `@Bean` methods before method signatures need to be inspected.

### 7.5. Composed Annotation Selecting When Jackson Is Absent

**`src/main/java/demo/condition/WhenJacksonAbsent.java`:**

```java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnMissingClass(
    "com.fasterxml.jackson.databind.ObjectMapper"
)
public @interface WhenJacksonAbsent {
}
```

Because `@ConditionalOnMissingClass` only has a `value` attribute of type `String[]`, passing the string directly is standard syntax. Do not use `name = ...`, because this annotation does not define a `name` attribute.

`@WhenJacksonAbsent` also has `@Target(ElementType.TYPE)` so it is placed on a separate nested configuration, rather than placing a condition on a method that might contain signatures depending on an optional SDK.

### 7.6. Auto-Configuration Using Both Annotations

**`src/main/java/demo/autoconfigure/ModeAutoConfiguration.java`:**

```java
package demo.autoconfigure;

import demo.api.ModeService;
import demo.condition.WhenJacksonAbsent;
import demo.condition.WhenJacksonPresent;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ModeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @WhenJacksonPresent
    static class JacksonConfiguration {

        @Bean
        ModeService selectedMode() {
            return () -> "jackson-supported";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @WhenJacksonAbsent
    static class FallbackConfiguration {

        @Bean
        ModeService selectedMode() {
            return () -> "baseline";
        }
    }
}
```

Here:

1. `@AutoConfiguration` is the class selected by Boot from the candidate list.
2. `JacksonConfiguration` is only processed when Jackson is present; `FallbackConfiguration` is only processed when Jackson is absent.
3. Both nested configurations use the shared `ModeService` interface, with no method signatures involving `ObjectMapper`.
4. `selectedMode()` has the same bean name in both branches, yet **only one branch applies** for a known marker class. Thus there is no need to rename beans to avoid conflict across the two illustrative environments.
5. `static` nested classes avoid needing an enclosing instance; `proxyBeanMethods=false` fits because no `@Bean` methods call each other.

Both branches only print labels about **integration capability**. Selecting `jackson-supported` does not prove the app is serializing JSON with Jackson or has an `ObjectMapper` bean. This lesson only verifies **class conditions via composed annotations**.

### 7.7. Registering Auto-Configuration via the Right Mechanism

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

```text
demo.autoconfigure.ModeAutoConfiguration
```

The path and fully qualified class name must be exact. This file lists **auto-configuration candidates**, not composed annotation names, the `ModeService` interface name, or the `ObjectMapper` class name.

Do not place auto-configuration within the `@SpringBootApplication` class's scan scope. If the app scans or imports auto-configuration via a path outside `.imports`, assumptions about selection/order/exclusion may differ; the experiment would no longer be cleanly isolated.

### 7.8. Application Printing the Result

**`src/main/java/demo/app/ComposedAnnotationApplication.java`:**

```java
package demo.app;

import demo.api.ModeService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class ComposedAnnotationApplication {

    private static final String JACKSON_CLASS =
        "com.fasterxml.jackson.databind.ObjectMapper";

    public static void main(String[] args) {
        SpringApplication.run(ComposedAnnotationApplication.class, args);
    }

    @Bean
    ApplicationRunner printMode(ModeService service) {
        return args -> {
            boolean present = ClassUtils.isPresent(
                JACKSON_CLASS,
                ComposedAnnotationApplication.class.getClassLoader()
            );
            System.out.println("JACKSON_ON_CLASSPATH: " + present);
            System.out.println("MODE: " + service.mode());
        };
    }
}
```

In the example, `ClassUtils.isPresent(...)` **only helps display** whether the class is on the classpath. Spring Boot does not use that statement in `ApplicationRunner` to decide auto-configuration; branch selection already happened **before** the runner was invoked, via `OnClassCondition`.

`ModeService` is injected directly, so if neither branch registers a bean, startup will fail with a dependency error. With two symmetrical conditions on the same marker, a standard environment will select exactly one branch.

## 8. Building and Running Both Cases

### 8.1. Running Without Jackson Databind

In the directory containing `pom.xml`, with Java 17+ and Maven:

```bash
mvn -q -DskipTests clean package
java -jar target/composed-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Ignoring the Spring Boot banner and startup logs, the program prints:

```text
JACKSON_ON_CLASSPATH: false
MODE: baseline
```

Explanation:

- Basic `spring-boot-starter` does not put Jackson Databind on the classpath in the given project.
- The `@ConditionalOnClass(name = "...ObjectMapper")` condition inside `@WhenJacksonPresent` does not match.
- `@ConditionalOnMissingClass("...ObjectMapper")` inside `@WhenJacksonAbsent` matches.
- `FallbackConfiguration` contributes the `ModeService` bean whose `mode()` returns `"baseline"`.

If you modified the POM or another dependency pulled Jackson into the project, the output may differ; check the dependency tree before concluding the condition is wrong.

### 8.2. Rebuilding With Jackson Databind

```bash
mvn -q -Pwith-jackson -DskipTests clean package
java -jar target/composed-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Lines printed by the program:

```text
JACKSON_ON_CLASSPATH: true
MODE: jackson-supported
```

Explanation:

- Maven profile `with-jackson` adds the `jackson-databind` dependency; the new executable JAR carries the related JARs.
- The presence condition matches, so nested `JacksonConfiguration` is processed.
- The absence condition does not match, so nested `FallbackConfiguration` creates no bean.
- The `selectedMode` bean is retrieved by `ApplicationRunner`, making the program print the label of the selected branch.

Note that both builds use **the exact same source annotations**. They differ in **effective classpath**, not in `application.properties` changes.

### 8.3. Results Table

| Runtime condition | `@WhenJacksonPresent` | `@WhenJacksonAbsent` | `MODE` output |
| --- | --- | --- | --- |
| No `ObjectMapper` | No match | Match | `baseline` |
| Has `ObjectMapper` | Match | No match | `jackson-supported` |

This is a simple example with a **single marker class**. If an integration condition requires multiple classes simultaneously, test every classpath combination instead of assuming a “present/absent” rule always partitions into two mutually exhaustive branches.

### 8.4. Inspecting the JAR and Dependencies

If output does not match expectations, verify the build and libraries inside the JAR:

```bash
mvn dependency:tree
jar tf target/composed-annotation-demo-0.0.1-SNAPSHOT.jar
```

For a Spring Boot executable JAR, dependencies normally sit under `BOOT-INF/lib/`. You can look for `jackson-databind` in the list after building with the profile.

Checking the JAR path alone is insufficient if the program runs from a custom classpath. You must compare the **same process** and **same build artifact** used when observing the condition.

## 9. Why Are Class-Level Conditions Safer Than Method-Level Conditions?

Consider an optional SDK integration:

```java
// RISK ILLUSTRATION, not a standalone file:
@Bean
@ConditionalOnClass(name = "com.vendor.sdk.Client")
com.vendor.sdk.Client vendorClient() {
    return new com.vendor.sdk.Client();
}
```

The `@Bean` method references the SDK directly in its **return type**. The JVM may need to process the method signature when loading the configuration class, before Spring can apply the method condition. This risks causing `NoClassDefFoundError` or class linkage errors when the SDK is absent.

The solution recommended by Spring Boot is to **move SDK-using methods into a separate `@Configuration` class**, placing a class-level condition on that class:

```java
@AutoConfiguration
class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class VendorOnlyConfiguration {

        // @Bean methods using SDK types go here.
        // Only deeply inspect this class when the SDK is present.
    }
}
```

This snippet illustrates class organization, not a runnable program. To reuse the condition, you can replace the direct annotation with `@RequiresVendorClient` **defined using `name` as in section 2**.

At the same time, the fallback configuration class must not place SDK types in `@Bean` signatures, fields, or constructors. If the fallback already depends on the SDK, it is no longer a viable branch when the SDK is missing.

Do not assume that placing `@ConditionalOnClass(name="...")` on **every** `@Bean` method is enough to guard signatures containing absent types. This is precisely why configuration classes should be split by capability.

## 10. Composed Annotations and Combined Conditions

A composed annotation can carry only a classpath condition:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public @interface RequiresVendorSdk {
}
```

Or combine with a property condition:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
@ConditionalOnProperty(
    prefix = "vendor.sdk",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public @interface RequiresEnabledVendorSdk {
}
```

This is an illustrative snippet needing imports. Per `@Conditional` semantics, **all applied conditions must match** for the configuration class to be eligible for processing.

Truth table:

| SDK class present? | `vendor.sdk.enabled` | Can configuration apply? |
| --- | --- | --- |
| No | `true` | No: missing class |
| Yes | `false` | No: property mismatch |
| Yes | Unset | No: `matchIfMissing=false` |
| Yes | `true` | Possibly: both conditions match |

The word **“possibly”** matters: other conditions, exclusions, or bean registration/initialization errors can still leave the feature unavailable.

Group rules into a composed annotation when they represent a stable capability reused across multiple configurations. For a single one-off condition, placing `@ConditionalOnClass(name=...)` directly is usually simpler and easier to diagnose.

### Can You Pass Class Names Dynamically to a Composed Annotation?

A fixed annotation like `@RequiresVendorSdk` hardcodes one explicit class name. If you want to declare:

```java
@RequiresLibrary("com.vendor.sdk.Client")
```

you need to design an annotation with attributes and an `@AliasFor` mapping mechanism or an appropriate custom condition; **do not assume any attribute on a custom annotation automatically maps to `@ConditionalOnClass`'s `name`**.

Prefer a clear fixed rule for a specific library. When many SDKs with dynamically varying class names are needed, you can implement a custom `Condition` reading `AnnotatedTypeMetadata`, or use tested annotation aliasing. That is an extension problem distinct from the core requirement of composed class conditions.

## 11. Comparison with Other Condition Types

A common mistake is using a classpath condition for missing **beans**, missing **properties**, or a feature failing at **runtime**.

| Scenario | Appropriate mechanism |
| --- | --- |
| SDK class present/absent at runtime | `@ConditionalOnClass(name=...)`, `@ConditionalOnMissingClass("...")` |
| User already supplied a bean of the same type | `@ConditionalOnMissingBean` |
| Enable feature only when configured on | `@ConditionalOnProperty` |
| Configuration only for servlet/reactive web | `@ConditionalOnWebApplication` with matching type |
| Bean created yet constructor fails | Inspect `BeanCreationException` and root cause |
| SDK present yet external service times out | Timeouts/retries/circuit breakers or controlled runtime fallback |

**Having a class** is not **having a bean**. A JAR may sit on the classpath without registering any bean because another condition did not match. Conversely, if a bean definition exists yet its instance has not been initialized due to `@Lazy`, it is not simply treated as “missing” under `@ConditionalOnMissingBean` semantics.

`@ConditionalOnMissingBean` is typically used in auto-configuration to let users replace default beans. It checks bean definitions **already processed at the time the condition is evaluated**, rather than checking whether every singleton has been instantiated. Hence pay attention to ordering and avoid placing it arbitrarily in regular application configuration.

## 12. Diagnosing When a Composed Annotation Does Not Work

### 12.1. Enabling the Condition Report

Spring Boot supports the Conditions Evaluation Report when debug is enabled:

```bash
java -jar target/composed-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Look for `ModeAutoConfiguration`, `JacksonConfiguration`, `FallbackConfiguration`, and `OnClassCondition` results.

- **Positive matches**: conditions that were evaluated and matched.
- **Negative matches**: conditions that were evaluated and did not match; usually with reasons.
- **Exclusions**: auto-configurations excluded by configuration.

The report is not a complete history of every JVM class-loading operation. If a bean has a definition yet fails creation, inspect the stack trace and root cause separately.

### 12.2. When Conditions Do Not Match as Expected

Check in order:

1. **Exact fully qualified name?** E.g. `com.fasterxml.jackson.databind.ObjectMapper`, not `ObjectMapper` or the module name `jackson-databind`.
2. **Correct annotation definition?** Composed `@ConditionalOnClass` must use `name`, not `ObjectMapper.class`.
3. **Right runtime artifact?** Did the build profile include the dependency in the executable JAR you are running?
4. **Right package/import path?** The library's auto-configuration must be named in `.imports`, outside component scanning.
5. **Right condition placement?** Class-level conditions guard the entire nested configuration; method-level conditions do not reliably protect optional types in return signatures.
6. **Are other conditions co-present?** A matching class condition does not guarantee bean definition registration if another property, bean, or web condition fails to match.
7. **Confusing class presence with bean presence?** `ObjectMapper` being on the classpath does not mean `ObjectMapper` is a Spring bean.
8. **Added via transitive dependency?** A class absent from direct dependencies can still be pulled in by another starter.

You can check the Maven dependency tree:

```bash
mvn dependency:tree
```

When using multiple profiles, add `-Pwith-jackson` to the dependency inspection command when investigating the Jackson-enabled build. Also inspect the runtime classpath, not just the POM.

### 12.3. When Encountering NoClassDefFoundError

This is a class loading/linking error. Check whether code referenced the optional class directly in an `@Bean` method signature, superclass, interface, or field/constructor of an early-loaded configuration. Do not try to fix it solely by changing a condition on the method if the JVM still must resolve the type before Spring evaluates the method condition.

A safer layout:

```text
core-api/
  CommonService.java                  (does not reference SDK)

auto-configuration/
  IntegrationAutoConfiguration.java
    nested SdkConfiguration           (@ConditionalOnClass(name="..."))
      SDK-specific @Bean methods
    nested FallbackConfiguration      (@ConditionalOnMissingClass("..."))
      core-only @Bean methods
```

Depending on actual usage, SDK implementation classes may live in a separate optional module, placed on that module's compile classpath while omitted at runtime for apps not using the SDK.

## 13. Common Mistakes

### Mistake 1: Using a Class Literal in Composed @ConditionalOnClass

**Wrong for libraries with optional SDKs:** wrapping `@ConditionalOnClass(OptionalSdk.class)` inside `@RequiresOptionalSdk`. Use `@ConditionalOnClass(name="fully.qualified.OptionalSdk")`.

### Mistake 2: Writing @ConditionalOnMissingClass(name = "...")

`@ConditionalOnMissingClass` has no `name`. Its attribute is `value` of type `String[]`; pass the string directly.

### Mistake 3: Treating @Bean-Level Conditions as an Absolute Shield Against Missing SDKs

The JVM may need to process the method signature before the method condition is applied. Extract a nested `@Configuration` with a class-level condition.

### Mistake 4: Turning Composed Annotations into the Solution for Everything

Composed annotations are useful when a rule is stable and reusable. For a single standalone condition, placing the built-in annotation directly is often clearer.

### Mistake 5: Using @ComponentScan to Discover Auto-Configuration

In Boot 3.x, auto-configuration registers via `.imports`. Scanning library packages can pull in unintended configurations and interfere with exclusion control.

### Mistake 6: Thinking @ConditionalOnClass Automatically Downloads the SDK

The condition only checks whether a class is present. It does not install dependencies, create SDK beans, or verify availability of a network endpoint.

### Mistake 7: Using Two Multi-Class Annotations Without Checking Intermediate Cases

If the main branch requires **both A and B present**, while the fallback requires **both A and B absent**, the two cases where one class is present and the other is absent go uncovered. Design a decision table.

### Mistake 8: Confusing Compile-Time Class Literals with Runtime Class Presence

A dependency may exist at compile time yet be omitted during packaging or execution. Use `name` in meta-annotations for optional dependencies, and check the runtime process.

### Mistake 9: Reading Annotations with Arbitrary Reflection and Handling Aliases Manually

Spring provides `MergedAnnotations`/`AnnotatedTypeMetadata`. When composed annotations and meta-annotations have aliases, use Spring APIs rather than assuming `Class#getDeclaredAnnotation` reflects what the framework sees.

### Mistake 10: Using Classpath Conditions to Handle Runtime Timeouts

If the SDK class exists yet the external server errors, the class condition still matches. Runtime fallback is a separate reliability concern, not `@ConditionalOnMissingClass`.

## 14. Checklist for Applying in Libraries/Starters

Before publishing a composed annotation for a classpath condition:

1. **Choose names expressing capabilities**, such as `@WhenJacksonPresent`, instead of names that obscure the rule.
2. **Use `@ConditionalOnClass(name="...")`** in the composed annotation definition.
3. **Use `@ConditionalOnMissingClass("...")`** when needing a missing-class branch; do not use the non-existent `name` attribute.
4. **Choose a sensible `@Target`**: prefer TYPE when needing to guard an entire configuration containing SDK method signatures.
5. **Set appropriate retention**, such as `RUNTIME`, so Spring's annotation system can observe it.
6. **Separate SDK config and fallback config**, keeping shared interfaces independent of the optional SDK.
7. **Do not scan auto-configuration as a component**; register the class in `AutoConfiguration.imports`.
8. **Test absent/present classpaths** and a few SDK versions if needed.
9. **Add `@ConditionalOnMissingBean`** when the app needs bean customization rights; do not confuse it with class conditions.
10. **Enable debug/reports when investigating**, comparing the actual classpath against conditions.
11. **Avoid premature optimization** with custom `Condition` implementations when built-in annotations suffice.
12. **Consider automated tests** with `ApplicationContextRunner` and `FilteredClassLoader` when developing real auto-configuration.

Helpers like `ApplicationContextRunner` and `FilteredClassLoader` belong to Spring Boot's test module and need not be added to the runnable's production code. The goal is to verify classpath logic across combinations, avoiding reliance on a single developer environment packed with libraries.

## 15. Knowledge Self-Check

**Question 1.** What is the difference between placing `@ConditionalOnClass` directly and using it inside a composed annotation?

**Answer:** With a direct annotation on a configuration class, Boot can read ASM metadata to safely support class literals of potentially missing dependencies. When `@ConditionalOnClass` is a meta-annotation on another annotation, you must use string class names via `name`.

**Question 2.** What is the right declaration inside `@WhenJacksonPresent`?

**Answer:** `@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")`.

**Question 3.** Can you write `@ConditionalOnMissingClass(name = "...")`?

**Answer:** No. `@ConditionalOnMissingClass` uses `value` of type `String[]`. Write `@ConditionalOnMissingClass("...")`.

**Question 4.** Why does the example with only `spring-boot-starter` print `MODE: baseline`?

**Answer:** The default POM's runtime classpath has no Jackson Databind; `ObjectMapper` is absent, so the `@WhenJacksonAbsent` branch matches.

**Question 5.** When enabling the `with-jackson` Maven profile, why does output change without editing source?

**Answer:** The `ObjectMapper` class appears in the JAR/runtime classpath; `@WhenJacksonPresent` matches and `@WhenJacksonAbsent` does not.

**Question 6.** Does a classpath condition guarantee an `ObjectMapper` bean already exists in the container?

**Answer:** No. It only checks class availability. Bean existence depends on other configurations/conditions.

**Question 7.** If an `@Bean` method returns `OptionalSdkType` when the SDK is absent at runtime, is adding a condition on that method itself always safe?

**Answer:** No. The JVM may resolve the method signature before Spring checks the condition; isolate the method inside an `@Configuration` class guarded by a class-level condition.

**Question 8.** Are two multi-class conditions automatically logical complements of each other?

**Answer:** Not necessarily. “All of A, B present” and “all of A, B absent” miss the two cases where one is present and the other is absent.

**Question 9.** Does `AutoConfiguration.imports` contain SDK class names or auto-configuration class names?

**Answer:** It contains fully qualified names of `@AutoConfiguration` classes. Checked SDK class names live inside the condition annotations.

**Question 10.** When should you write a custom composed annotation?

**Answer:** When a classpath rule is a clear, reusable capability with domain meaning. For a simple one-off use, direct `@ConditionalOnClass(name=...)` can be easier to read.

## 16. References

- Spring Boot 3.3.13, Creating Your Own Auto-configuration (Class Conditions): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13, `ConditionalOnClass` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3.13, `ConditionalOnMissingClass` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html
- Spring Framework 6.1, `AnnotatedTypeMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html
- Spring Framework 6.1, `@Conditional` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html
