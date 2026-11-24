# Declaring Classpath Conditions so Optional Libraries Do Not Cause Class-Loading Failures

**Topic:** Spring Boot Auto Configuration  
**Context:** Auto-Configuration Library  
**Goal:** Design auto-configurations that work when an optional library is present and are safely skipped when that library is absent from the runtime classpath. The focus is on where to place `@ConditionalOnClass`, how to isolate references to optional types, and how to test with a filtered classloader.

## 1. Problem: Optional Dependencies Can Break Applications That Do Not Use Them

Suppose the `acme-json-autoconfigure` library supports Jackson if the application has `jackson-databind`. Some applications want the JSON feature, while others do not want to add Jackson to their dependency graph.

Desired behavior:

- Jackson present: register a Jackson-based codec.
- Jackson absent: Spring Boot still starts; the optional JSON integration is skipped.
- Users can provide their own codec so the starter backs off.
- Common library configuration classes do not force every application to install the optional library.

If the main auto-configuration class directly references types that only exist when Jackson is installed, Spring may hit class linkage errors while reading or introspecting the configuration. An error such as `NoClassDefFoundError` can appear before any bean method is invoked. Even applications not using the JSON feature are then impacted by a dependency they did not request.

This is a **classpath safety** problem. You must ensure the condition checking class presence is evaluated before Spring or the JVM has to load the configuration section containing references to that class.

## 2. `@ConditionalOnClass` and `@ConditionalOnMissingClass`

Spring Boot provides two main class conditions:

```java
@ConditionalOnClass(SomeOptionalApi.class)
```

The condition matches when the specified type can be found on the classpath.

```java
@ConditionalOnMissingClass("com.vendor.optional.Client")
```

The condition matches when the specified type is absent from the classpath.

Both can enable or disable a configuration branch based on actual dependencies:

| Classpath state | `@ConditionalOnClass` | `@ConditionalOnMissingClass` |
| --- | --- | --- |
| Optional API present | Match | No match |
| Optional API absent | No match | Match |

Multiple classes can be declared. With `@ConditionalOnClass`, all listed classes must be present for the condition to match. With `@ConditionalOnMissingClass`, the condition matches when all specified classes are absent.

Direct example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
static class VendorClientConfiguration {
    // Only this section is allowed to reference vendor APIs.
}
```

This is an illustrative nested configuration; its body is included only when the class condition matches.

### 2.1. Why Can a Class-Level Condition Check a Class That Is Not Present Yet?

Spring Boot reads configuration class annotation metadata using ASM. By reading bytecode metadata, the framework can inspect `@ConditionalOnClass` values and decide whether to load the configuration class before the JVM needs to resolve all type references inside that class.

Therefore, for an annotation placed **directly on a `@Configuration` class**, you can use:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(SomeOptionalApi.class)
static class OptionalApiConfiguration {
}
```

Even when `SomeOptionalApi` is not on the runtime classpath, the class's annotation metadata can be read so the condition excludes the configuration branch.

You can also use the `name` attribute with the fully qualified class name as a string:

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
```

`name` is useful when avoiding class literals or building composed annotations. Switching to a string does not change the condition semantics; the package and class name must be exact.

**Important limitation:** reading metadata with ASM does not mean referencing an optional class anywhere is safe. The configuration class must be isolated so risky references reside only inside the guarded branch.

## 3. Common Pitfall: Placing the Condition on a `@Bean` Method with an Optional Return Type

A pattern that looks reasonable but is unsafe:

```java
@AutoConfiguration
public class UnsafeJsonAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
```

The issue lies in the signature:

```java
ObjectMapper objectMapper()
```

To process bean methods, Spring needs to read method metadata and return types. The JVM may have to load the class or resolve method references involving `ObjectMapper` **before** the method-level condition is applied. If Jackson is absent, the method condition may arrive too late to protect the configuration from class-loading failures.

Do not rely on the method body not being invoked to assume the method cannot fail. Introspecting the signature and metadata alone can trigger type resolution.

### 3.1. The Fix: Move the Condition to a Separate Nested `@Configuration`

Spring Boot recommends isolating the optional branch into a separate configuration class:

```java
@AutoConfiguration
public class SafeJsonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
    public static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean
        JsonCodec jsonCodec() {
            return new JacksonJsonCodec();
        }
    }
}
```

Key points:

1. The outer class `SafeJsonAutoConfiguration` references only always-present APIs.
2. `JacksonConfiguration` has the condition at the **class level**.
3. Classes, methods, and fields requiring Jackson stay inside the guarded branch.
4. The bean method returns `JsonCodec`, a stable library interface, rather than exposing `ObjectMapper` as a public return type.
5. `@ConditionalOnMissingBean` allows the application to supply its own `JsonCodec` so the starter backs off.

In real code, every optional reference must be isolated: superclasses, interfaces, fields, constructors, parameters, return types, annotations, static initializers, and nested implementations. Do not merely move a single `new ObjectMapper()` line while leaving `ObjectMapper` in the outer configuration class's signatures.

### 3.2. When to Use `value` vs. `name`?

Keep this distinction in mind:

- **Annotation directly on a configuration class:** `@ConditionalOnClass(SomeOptionalApi.class)` can use `value`; Spring reads the metadata using ASM.
- **Composed/meta-annotations:** when creating a custom annotation annotated with `@ConditionalOnClass` or `@ConditionalOnMissingClass`, you must use `name`.

Correct composed annotation example:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public @interface ConditionalOnJackson {
}
```

Then use it as:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnJackson
static class JacksonConfiguration {
}
```

Do not use `@ConditionalOnClass(ObjectMapper.class)` inside a meta-annotation definition. Spring Boot does not process class literals in meta-annotations in the same way as annotations placed directly on configuration classes; use `name` so the condition can be read safely.

## 4. Organizing Auto-Configuration for Optional Dependencies

A maintainable structure:

```text
acme-json-autoconfigure/
├── pom.xml
└── src/main/
    ├── java/com/acme/json/
    │   ├── JsonCodec.java
    │   ├── ConditionalOnJackson.java
    │   └── autoconfigure/
    │       └── JsonAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Separation of responsibilities:

- **Stable library API:** interfaces like `JsonCodec`, shared configuration, and properties that applications can use.
- **Outer configuration:** the auto-configuration class discovered by Spring Boot; makes no mention of Jackson types.
- **Optional branch configuration:** nested static class guarded by a class condition.
- **Optional implementation:** classes using `ObjectMapper` reside solely inside the Jackson branch.
- **Imports file:** lists the top-level auto-configuration class; do not list internal helpers as independent auto-configurations unless intended.

In Spring Boot 3.x, library auto-configurations are discovered via:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example content:

```text
com.acme.json.autoconfigure.JsonAutoConfiguration
```

The class name in the file is the fully qualified name of the outer auto-configuration. Nested configurations are processed when Spring reads the enclosing configuration; they do not need to be listed as separate auto-configurations.

Auto-configurations should be loaded through the imports file rather than relying on component scanning of internal packages. That ensures applications receive only configurations intentionally published by the starter.

## 5. Optional Dependencies in Maven and Gradle

Class conditions and dependency declarations solve two different problems:

- Dependency declarations decide which libraries enter the application's dependency graph.
- Class conditions decide which auto-configuration branches activate based on the actual runtime classpath.

In Maven, the `autoconfigure` module can declare an optional library like this:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

`optional=true` means this dependency is used to compile and test the current module, but it is not automatically propagated transitively as a required dependency to consuming applications. If an application wants the Jackson branch, the application or corresponding starter must put Jackson on the runtime classpath.

In Gradle, you can use `compileOnly` for dependencies needed only when compiling the autoconfigure module, while adding appropriate runtime/test dependencies in test modules. If a dedicated starter wants to include Jackson out of the box as a default choice, that starter can declare the corresponding runtime dependency.

A common layout when a library has multiple adapters:

- `acme-core`: stable API, with no Jackson dependency.
- `acme-jackson`: Jackson integration implementation.
- `acme-spring-boot-autoconfigure`: auto-configuration with an optional Jackson dependency.
- `acme-spring-boot-starter`: starter aggregating the dependencies chosen as defaults.

A base starter should not always pull in all optional libraries if most applications do not use them. However, if a starter is explicitly named `acme-jackson-starter`, pulling in Jackson is an intentional choice.

**Optional dependencies do not automatically protect class loading.** If the autoconfigure module has an outer class referencing `ObjectMapper` in a method signature, field, or superclass, marking the Maven dependency optional does not fix the error. You need both an appropriate dependency graph and a safe class-condition structure.

## 6. Complete Example: Optional JSON Adapter with Spring Boot 3.3.13

The following example uses **Java 17**, **Spring Boot 3.3.13**, Maven, Jackson, and JUnit 5. The goal is to test the same auto-configuration across three scenarios:

1. Jackson present: a Jackson-based `JsonCodec` bean is created.
2. Jackson hidden from the classloader: the context still starts and the Jackson branch creates no bean.
3. Application provides its own `JsonCodec`: the default bean backs off.

### 6.1. `pom.xml`

```xml
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
    <artifactId>optional-classpath-autoconfig</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Jackson is available when compiling and running tests in this module, but Maven does not propagate that dependency transitively to every application using the autoconfigure module. `FilteredClassLoader` in the test simulates a consumer that cannot see Jackson at runtime.

### 6.2. Always-Present API: `JsonCodec.java`

```java
package demo;

import java.util.Map;

public interface JsonCodec {
    String encode(Map<String, Object> value);
}
```

This interface does not reference Jackson. It is the stable type that other services in the application can use regardless of whether the concrete implementation is Jackson or user-supplied.

### 6.3. Composed Condition: `ConditionalOnJackson.java`

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public @interface ConditionalOnJackson {
}
```

Because `@ConditionalOnJackson` is a meta-annotation, it uses `name` so Spring Boot reads the optional class name as a string.

### 6.4. Auto-Configuration: `JsonAutoConfiguration.java`

```java
package demo;

import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class JsonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnJackson
    public static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(JsonCodec.class)
        JsonCodec jsonCodec() {
            return new JacksonJsonCodec();
        }

        static final class JacksonJsonCodec implements JsonCodec {

            private final ObjectMapper objectMapper = new ObjectMapper();

            @Override
            public String encode(Map<String, Object> value) {
                try {
                    return this.objectMapper.writeValueAsString(value);
                }
                catch (JsonProcessingException ex) {
                    throw new IllegalArgumentException(
                            "Cannot encode the supplied value as JSON", ex);
                }
            }
        }
    }
}
```

The outer class `JsonAutoConfiguration` does not use `ObjectMapper` in any field, superclass, interface, or method signature. All Jackson references stay inside the `JacksonConfiguration` branch guarded by the class-level condition.

The `jsonCodec()` method returns `JsonCodec`, an always-present interface. Only the concrete implementation `JacksonJsonCodec` instantiates `ObjectMapper`. `@ConditionalOnMissingBean(JsonCodec.class)` allows an application-supplied bean to make the auto-configuration back off.

### 6.5. Registration in `AutoConfiguration.imports`

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
demo.JsonAutoConfiguration
```

Spring Boot applications will discover the outer auto-configuration via this file. There is no need to list `JacksonConfiguration` in imports because it is a nested configuration processed inside the parent auto-configuration.

### 6.6. Test: `JsonAutoConfigurationTest.java`

```java
package demo;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class JsonAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(JsonAutoConfiguration.class));

    @Test
    void jacksonOnClasspathRegistersJsonCodec() {
        this.contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(JsonCodec.class);

            String json = context.getBean(JsonCodec.class)
                    .encode(Map.of("status", "ok"));

            assertThat(json).isEqualTo("{\"status\":\"ok\"}");
        });
    }

    @Test
    void missingJacksonSkipsOptionalConfigurationWithoutFailure() {
        this.contextRunner
                .withClassLoader(new FilteredClassLoader("com.fasterxml.jackson"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(JsonCodec.class);
                });
    }

    @Test
    void userCodecMakesJacksonDefaultBackOff() {
        this.contextRunner
                .withUserConfiguration(UserJsonCodecConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(JsonCodec.class);
                    assertThat(context).hasBean("customJsonCodec");
                    assertThat(context).doesNotHaveBean("jsonCodec");

                    String result = context.getBean(JsonCodec.class)
                            .encode(Map.of("status", "ok"));

                    assertThat(result).isEqualTo("custom-codec");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserJsonCodecConfiguration {

        @Bean
        JsonCodec customJsonCodec() {
            return value -> "custom-codec";
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

Expected output:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

The test code does not print custom stdout. Maven Surefire may display additional logs depending on its version and environment.

The three tests prove:

- **Jackson on classpath:** the nested configuration matches and creates exactly one `JsonCodec`; the encoded result is `{"status":"ok"}`.
- **Jackson absent from classpath:** `FilteredClassLoader` hides the `com.fasterxml.jackson` package; the context does not fail and no default `JsonCodec` bean exists.
- **Application-provided bean:** `@ConditionalOnMissingBean(JsonCodec.class)` does not match, the default implementation is not registered, and the custom bean is used.

`FilteredClassLoader` simulates a consumer lacking the dependency without creating a second Maven module. When releasing a real library, you should still test the packaged artifact in a consumer module that does not declare Jackson to catch references outside the guarded branch.

## 7. `@ConditionalOnMissingClass`: When You Want a Fallback Branch

Sometimes you still need an alternative implementation when the optional library is absent. You can create a separate branch guarded by `@ConditionalOnMissingClass`:

```java
@AutoConfiguration
public class TransportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class VendorConfiguration {
        @Bean
        Transport vendorTransport() {
            return new VendorTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("com.vendor.sdk.Client")
    static class BasicConfiguration {
        @Bean
        Transport basicTransport() {
            return new BasicTransport();
        }
    }
}
```

This is an illustrative snippet requiring the library's `Transport`, `VendorTransport`, and `BasicTransport` interfaces/classes. The vendor branch may reference the optional SDK; the basic branch uses only always-present types.

The two classpath conditions select the branch according to dependencies. If both branches produce the same contract, clearly define back-off rules and ensure no extra condition causes both to register or both to be excluded unintentionally.

If no reasonable fallback implementation exists, skipping the optional branch completely is also a valid design. Do not register a dummy bean just so the application appears to start successfully only to throw exceptions on every call.

## 8. Common Design Mistakes

### Mistake 1: Condition placed on a method whose return type is optional

`@Bean ObjectMapper objectMapper()` may force the JVM to resolve `ObjectMapper` before the method condition can protect it. Move the condition up to a nested configuration.

### Mistake 2: Outer class still retains an optional reference

Moving the `@Bean` method while forgetting that the outer class still has a field, constructor parameter, superclass, or annotation referencing the optional library. The nested class's class condition does not protect those references. Keep the outer configuration dependent only on stable APIs.

### Mistake 3: Using `value` in a composed annotation

`@ConditionalOnClass(OptionalApi.class)` on a custom annotation does not share the same safe metadata handling as a direct annotation. Inside meta-annotations, use `name = "fully.qualified.ClassName"`.

### Mistake 4: Assuming Maven `optional` solves class loading on its own

`<optional>true</optional>` prevents transitive dependency propagation. It does not protect a class whose bytecode/signature references a missing type. You still must place class conditions properly.

### Mistake 5: Including optional dependencies in the default starter

If the base starter always pulls in every adapter, the class condition still matches because the dependency is present, and users receive unwanted dependencies. Split starters/adapters by usage needs.

### Mistake 6: Testing only when the dependency is present

Tests running on the development classpath usually have all required libraries, hiding optional dependency bugs. Always test missing classpaths with `FilteredClassLoader` or a separate consumer module.

### Mistake 7: Hiding only one class while the package still has other required types

An integration may depend on multiple classes in the same library. Hiding the vendor package in `FilteredClassLoader` usually simulates absence more thoroughly; you can also hide specific multiple classes when targeting a single type.

### Mistake 8: Using `@ConditionalOnClass` to mask version mismatches

Class presence does not guarantee every method or field the code needs exists in that library version. `@ConditionalOnClass` checks class existence, not full binary compatibility. If newer APIs are required, specify appropriate versions/capabilities or catch linkage issues during development and testing.

### Mistake 9: Exposing optional types unnecessarily in public APIs

If the starter's public interface returns `ObjectMapper`, every consumer using that interface may need Jackson. Prefer neutral library-owned types like `JsonCodec`; let optional implementations use `ObjectMapper` internally.

## 9. Annotation Processor and Condition Metadata

Spring Boot can generate the file:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Using `spring-boot-autoconfigure-processor`, conditions on auto-configurations can be collected as metadata so Spring Boot filters out non-matching configurations early, improving startup time.

This is an optimization for auto-configuration discovery. It **does not replace** class-level conditions in source code and cannot fix a class structure that puts optional types in unsafe signatures. A proper design must work safely even when the framework processes normal configuration metadata.

With Maven Compiler Plugin 3.12.0 and newer, Spring Boot 3.3 documentation instructs configuring `spring-boot-autoconfigure-processor` inside `annotationProcessorPaths`. With Gradle, declare the processor in the `annotationProcessor` configuration.

Do not confuse this file with `META-INF/spring-configuration-metadata.json`: the former serves auto-configuration condition filtering; the latter describes properties for IDE/tooling configuration hints.

## 10. Workflow for Diagnosing `NoClassDefFoundError` in a Starter

When an application does not use an optional feature yet still hits a class-loading failure:

1. Read the stack trace and locate the first missing class. Identify which dependency's API it belongs to.
2. Find the auto-configuration, configuration, or bean method referencing that type.
3. Check whether the reference lives in the outer configuration or inside a guarded nested branch.
4. Check whether the optional type appears in any superclass, interface, field, constructor/method signature, or annotation of the outer class.
5. Check whether `@ConditionalOnClass` is at the class level or only on the `@Bean` method.
6. If the condition is inside a composed annotation, verify it uses `name`.
7. Inspect the consumer's dependency graph: did the starter pull in the optional library unintentionally?
8. Use `ApplicationContextRunner` and `FilteredClassLoader` to reproduce the exact missing classpath.
9. Test the packaged artifact in a minimal consumer. Tests in a source module with full dependencies can mask transitive/runtime bugs.

Distinguish several situations:

| Symptom | Possible meaning | What to check |
| --- | --- | --- |
| `NoClassDefFoundError` while parsing configuration | A reference to a class missing at runtime | Outer config, method signatures, nested configuration |
| `ClassNotFoundException` from reflection | Code actively loads a class by name, but the classloader cannot find it | Class name, dependencies, classloader |
| `NoSuchMethodError` | Class exists, but runtime version lacks a method compiled against | Dependency mediation, version alignment |
| `NoSuchFieldError` | Class exists, but a field is incompatible | Version and binary compatibility |
| Condition no-match and context runs normally | Optional branch skipped as designed | Confirm whether the feature needs to be enabled in this environment |
| Condition matches then bean creation fails | Dependency is present, but implementation/constructor/init failed | Root cause, version, config, and runtime behavior |

Do not catch `Throwable` to swallow all class-loading errors. That can hide `LinkageError`, implementation bugs, or version mismatches. Fix the auto-configuration structure and dependency contract instead.

## 11. Pre-Release Review Checklist

- [ ] Outer auto-configuration uses only always-present types.
- [ ] Each optional integration lives in its own nested static `@Configuration`.
- [ ] `@ConditionalOnClass`/`@ConditionalOnMissingClass` sits on the configuration class guarding the branch.
- [ ] Optional types never appear in method/class signatures outside the branch.
- [ ] Meta-annotations use `name`, not class literals in `value`.
- [ ] Optional library dependencies are not transitively propagated unconditionally.
- [ ] Dedicated starters pull in optional dependencies only when that is an intentional product choice.
- [ ] `AutoConfiguration.imports` lists the top-level auto-configuration accurately.
- [ ] Tests cover classpath with the library, classpath without the library, and user bean override.
- [ ] Consumer tests verify the packaged artifact, not just tests in the development module.
- [ ] If using the annotation processor, confirm metadata is generated without relying on it to hide design flaws.

## 12. Self-Check Questions

**Question 1.** Why can `@ConditionalOnClass(OptionalClient.class)` on a `@Configuration` class work even when `OptionalClient` is not on the runtime classpath?  
**Answer:** Spring Boot reads annotation metadata via ASM before loading the configuration class; the condition can exclude the class before the JVM needs to resolve internal references.

**Question 2.** Why is `@ConditionalOnClass` on a `@Bean` method with return type `OptionalClient` unsafe?  
**Answer:** Spring/the JVM may need to load or introspect the method signature before the method-level condition is evaluated.

**Question 3.** What pattern should be used for an optional integration?  
**Answer:** Place the condition on a dedicated nested static `@Configuration(proxyBeanMethods=false)`, then keep all methods and implementations referencing optional APIs inside that branch.

**Question 4.** When writing a composed annotation containing `@ConditionalOnClass`, which attribute should be used?  
**Answer:** `name`, because the `value` class literal in a meta-annotation is not processed with the same safe metadata mechanism as a direct annotation.

**Question 5.** Does `optional=true` in Maven replace class conditions?  
**Answer:** No. Maven `optional` controls dependency propagation; class conditions control configuration branches according to the runtime classpath.

**Question 6.** How do you test that an application missing Jackson still starts?  
**Answer:** Use `ApplicationContextRunner.withClassLoader(new FilteredClassLoader("com.fasterxml.jackson"))`, then assert the context has not failed and beans from the Jackson branch do not exist.

**Question 7.** If a class is present but lacks a method needed by the integration, does `@ConditionalOnClass` detect it?  
**Answer:** No. This condition checks class presence, not full API binary compatibility.

## 13. Key Principles to Remember

1. Guard optional dependencies with class conditions at the **configuration class level**.
2. Put all references to optional types inside a guarded nested configuration.
3. Do not rely on method-level conditions to rescue a return type or method signature that already references a missing class.
4. Use `value` on direct class annotations when appropriate; use `name` inside composed/meta-annotations.
5. Separate optional dependencies in Maven/Gradle from the starter's default dependencies.
6. Test both classpath states with `FilteredClassLoader`.
7. Use neutral APIs for shared contracts, leaving optional adapters to depend on concrete implementations.

### Official References

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration, Class Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@ConditionalOnClass`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 API — `@ConditionalOnMissingClass`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html)
- [Spring Boot 3.3 API — `FilteredClassLoader`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot 3.3 API — `ApplicationContextRunner`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
