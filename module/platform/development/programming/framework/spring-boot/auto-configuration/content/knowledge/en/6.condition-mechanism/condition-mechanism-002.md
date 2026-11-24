# ConditionContext Provides Environment, Registry, BeanFactory, and ClassLoader

> **Scope:** Spring Boot 3.3.x / Spring Framework 6.1, Java 17+. This lesson explains **the `ConditionContext` object Spring passes in when evaluating a `Condition`**: it provides configuration information, bean definitions, and class-loading capability to decide whether to register a configuration/bean. This covers the **condition mechanism**, not a guide to using `ApplicationContext` to access beans at runtime.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the `Condition.matches(ConditionContext, AnnotatedTypeMetadata)` signature and the role of each parameter.
2. Distinguish the five APIs of `ConditionContext`: `getEnvironment()`, `getRegistry()`, `getBeanFactory()`, `getClassLoader()`, and `getResourceLoader()`.
3. Know when to check **properties/profiles**, **bean definitions**, **`BeanFactory` metadata**, or **class presence**; and understand why these questions differ.
4. Recognize the difference between the **parse configuration** phase and the **register bean** phase; avoid reading bean definition results at an inappropriate time.
5. Write and test a custom `Condition` using Spring Boot 3.3 + Java 17 without instantiating beans or mutating the registry inside `matches`.
6. Know when **you do not need to write a custom Condition**, because Spring Boot already provides `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean`.

Key mindset: **`ConditionContext` is a window into the context at the moment Spring evaluates a condition, not a complete snapshot of a fully initialized application.** Each component has its own visibility scope, timing, and limitations.

## 2. From @Conditional to Condition.matches

Spring Framework provides the `@Conditional` annotation. When attaching it to a configuration class or a `@Bean` method, you specify classes implementing `Condition`:

```java
@Conditional(MyCondition.class)
```

This is an **annotation fragment**, not a standalone Java file. The core contract:

```java
public interface Condition {
    boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata);
}
```

This is a **simplified signature for explanation**, not a redefinition of the Spring interface inside your project.

- `context`: provides the tools and state Spring has at evaluation time.
- `metadata`: describes the class or method carrying the annotation; allows reading annotation attributes **without instantiating the bean**.
- `true`: the condition matches; Spring may continue evaluating that class/method.
- `false`: the condition does not match; Spring skips the guarded component at the appropriate phase.

**`true` does not mean "create the bean right now"**. There may still be other conditions, bean registration, or later instantiation. **`false` does not mean "delete an existing bean"**; it mainly blocks processing the configuration or registering the bean definition under evaluation.

### 2.1. At Which Levels Can @Conditional Be Attached?

```java
// Fragment: attached to a configuration class.
@Configuration(proxyBeanMethods = false)
@Conditional(MyCondition.class)
class SomeConfiguration {
}
```

```java
// Fragment: attached to a @Bean method inside @Configuration.
@Bean
@Conditional(MyCondition.class)
SomeService someService() {
    return new SomeService();
}
```

In the first example, the condition can exclude the entire configuration class. In the second example, the condition decides the registration of **the method's bean definition** that it guards.

These are two positions that can be evaluated in **different phases**. Therefore, you cannot assume the registry already contains the same number of bean definitions at both times.

## 3. What Does ConditionContext Contain?

In Spring Framework, the `org.springframework.context.annotation.ConditionContext` interface provides the following methods:

| Method | Return type | Used to ask | Important limitation |
| --- | --- | --- | --- |
| `getRegistry()` | `BeanDefinitionRegistry` | Has a bean definition named X been registered in this registry yet? | Does not mean the bean object has been created |
| `getBeanFactory()` | `ConfigurableListableBeanFactory` or `null` | Which beans' metadata does the factory hold, and how are beans configured? | May be unavailable in certain environments/phases |
| `getEnvironment()` | `Environment` | What are the current properties, profiles, and configuration sources? | Values depend on property-source precedence and evaluation timing |
| `getResourceLoader()` | `ResourceLoader` | Can a resource be accessed through Spring's abstraction? | Resource existence does not guarantee valid content or network readiness |
| `getClassLoader()` | `ClassLoader` or `null` | Which loader is used to find classes; is a required class visible? | Class presence does not guarantee compatible API or successful bean creation |

The two getters that can return `null` are `getBeanFactory()` and `getClassLoader()`. Condition code must have a handling policy instead of calling methods on potentially null values without checking.

The distinction is crucial:

```text
ConditionContext
  |
  +-- Environment    : properties, profiles, property sources
  |
  +-- Registry       : bean definitions registered here
  |
  +-- BeanFactory    : metadata / foundation for creating and managing beans
  |
  +-- ClassLoader    : class visibility at runtime
  |
  +-- ResourceLoader : resource location capability
```

`ConditionContext` is **not** `ApplicationContext`; it has no contract to "return all fully initialized singletons".

## 4. getEnvironment(): Configuration-Based Conditions

`context.getEnvironment()` returns `Environment`, allowing checks on a property or profile state:

```java
String mode = context.getEnvironment()
        .getProperty("demo.mode", "safe");
boolean enabled = context.getEnvironment()
        .getProperty("demo.feature.enabled", Boolean.class, false);
boolean prod = context.getEnvironment()
        .acceptsProfiles(
                org.springframework.core.env.Profiles.of("prod"));
```

This is a **fragment placed inside the `matches` method**; it requires imports and an enclosing class to compile.

- `getProperty(key, defaultValue)` retrieves a string or default value.
- `getProperty(key, targetType, defaultValue)` asks Spring to convert the type, e.g., `Boolean`.
- `acceptsProfiles(Profiles.of(...))` checks a profile expression (Spring Framework 6.1).
- Property sources have precedence order; the same key may receive different values across CLI, environment variables, and configuration files according to Spring Boot's rules.

Example:

```properties
demo.feature.enabled=true
demo.feature.required-class=java.time.Instant
```

A condition can check both keys, but if you only need to toggle on/off by one property, **prefer `@ConditionalOnProperty`**: the code is more declarative, supported by Boot's condition diagnostics, and less error-prone in value handling.

### 4.1. Reading a Property Is Not Equivalent to Binding an Entire Object

`Environment#getProperty` is suitable when you need a few keys. For complex configuration, Spring Boot provides `@ConfigurationProperties` and its binder; do not write a custom Condition using long property chains to reimplement production binding and validation logic.

Additionally, properties **do not automatically alter condition outcomes on a running context** when an environment variable is modified after startup. Standard conditions are evaluated during context construction; dynamic runtime feature flags require a different mechanism.

## 5. getRegistry(): Inspect Bean Definitions, Not Instances

`context.getRegistry()` returns `BeanDefinitionRegistry`, which has APIs such as:

```java
boolean declaredHere = context.getRegistry()
        .containsBeanDefinition("featureMarker");
int count = context.getRegistry().getBeanDefinitionCount();
```

This is a fragment inside `matches`. It queries whether a **bean definition** has been registered without starting object instantiation. A bean definition might not have a singleton yet; a bean can also be created through mechanisms that a simple definition-name check does not fully capture.

An example:

```java
@Bean
String featureMarker() {
    return "ready";
}
```

If Spring has processed this method and registered a bean definition named `featureMarker`, the registry can return `true` even before the `String` instance is created.

### 5.1. Do Not Confuse Bean Name with Type

`containsBeanDefinition("featureMarker")` is a definition-name check, not a search for "any bean of type `FeatureMarker`".

- If the bean name changes to `anotherMarker` while the type stays the same, the name condition can become false.
- Beans in a parent context are not automatically present when checking a local registry.
- Aliases, bean definitions from registrars, scopes, or factory mechanisms mean checking by name is not always equivalent to asking "which bean type is available".

Therefore, for the requirement **"if a bean of type X already exists, do not register the default"**, use Boot's `@ConditionalOnMissingBean(X.class)` instead of manually looping over `containsBeanDefinition` and guessing types.

### 5.2. Why Should You Not Mutate the Registry Inside a Condition?

`BeanDefinitionRegistry` has **mutating** methods like `registerBeanDefinition(...)`, but a Condition should primarily be a read-only check.

**Do not** use `Condition.matches` to secretly register/remove bean definitions, cause side effects, or depend on invocation order. To register beans programmatically, Spring provides `ImportBeanDefinitionRegistrar`, bean definition registry post-processors, or dedicated configuration mechanisms. A Condition only returns a match decision.

## 6. getBeanFactory(): Know Its Metadata and Limits

`context.getBeanFactory()` returns `ConfigurableListableBeanFactory` if the current registry can supply this object; the contract allows returning `null`. Therefore:

```java
org.springframework.beans.factory.config.ConfigurableListableBeanFactory factory =
        context.getBeanFactory();

if (factory == null) {
    // No BeanFactory available: do not dereference.
    return false;
}

boolean defined = factory.containsBeanDefinition("featureMarker");
```

This is a **fragment inside `matches`**, not a standalone file.

A `BeanFactory` can provide information such as bean names, definition metadata, scopes, aliases, known types, or managed beans. However, distinguish carefully:

| What you ask | Where it comes from | Guaranteed instance exists? |
| --- | --- | --- |
| Is definition name `featureMarker` registered? | Registry / Factory definition metadata | No |
| What is the bean definition's `lazyInit` or scope? | Definition metadata | No |
| What is the bean's type per the current factory? | Type lookup | Not necessarily; `FactoryBean` and type prediction have their own subtleties |
| What does `getBean("featureMarker")` return? | BeanFactory | May trigger bean creation; **do not do this in a Condition** |

**Avoid calling `getBean()` inside `Condition.matches`** to "check if a bean exists". It can cause beans to be created prematurely, pulling in dependencies, network calls, or side effects and causing circular dependencies. Even certain type-lookup approaches can cause a `FactoryBean` to be eagerly initialized; choose the right APIs and flags if complex checks are unavoidable.

To express bean conditions by type/name, prefer Boot's `@ConditionalOnBean`, `@ConditionalOnSingleCandidate`, or `@ConditionalOnMissingBean`. They are built for the auto-configuration flow and provide better diagnostics than manual lookups.

### 6.1. Registry and BeanFactory May Overlap Internally, but Do Not Equate Them

In common ApplicationContexts, the bean factory both holds bean definitions and implements the registry contract. Thus both calls to `containsBeanDefinition("x")` can return the same result. Yet **their interfaces and purposes differ**:

- `BeanDefinitionRegistry` focuses on storing definitions;
- `ConfigurableListableBeanFactory` supports managing/querying metadata and bean objects;
- `ConditionContext` exposes both because conditions may be evaluated in different environments or phases.

Do not assume the factory is always distinct from the registry, and do not assume it is always available.

## 7. getClassLoader(): Class Presence Conditions

`context.getClassLoader()` returns the loader Spring uses in the condition's context, which may be null. An application that has an SDK on the compile classpath but not on the runtime classpath may be unable to load the SDK class through the current loader.

If you need to check by **class name**, Spring provides a helper:

```java
boolean found = org.springframework.util.ClassUtils.isPresent(
        "java.time.Instant",
        context.getClassLoader());
```

This is a fragment inside `matches`. `ClassUtils.isPresent` is a relatively safe presence check that handles cases where a class cannot be loaded/linked; the helper uses an appropriate fallback loader when the loader argument is null. You should not invoke an SDK constructor just to check whether a class exists.

Limitations to remember:

1. "Class is present" means the loader can locate/link the class; it does **not** guarantee matching API method versions.
2. A JAR sitting on disk does not mean the active ClassLoader sees it.
3. The test classpath can differ from production runtime; `FilteredClassLoader` can simulate hiding a class from the context in tests.
4. The same binary name defined by different custom loaders can represent **two distinct JVM types**.
5. Classpath conditions on auto-configurations should normally use **`@ConditionalOnClass`** or `@ConditionalOnMissingClass`, because Spring Boot optimizes metadata and handles them more safely than hand-rolled conditions.

### 7.1. Why Avoid Referencing OptionalClient.class in Early-Loaded Classes?

Example with a vendor SDK absent at runtime:

```java
// Risky fragment: avoid referencing an optional SDK in an unguarded location.
@Bean
com.vendor.sdk.OptionalClient optionalClient() {
    return new com.vendor.sdk.OptionalClient();
}
```

If an optional type appears in the `@Bean` signature of a configuration that is always parsed, Spring/JVM may have to resolve the type before the method-level condition can guard it. The Spring Boot pattern should use a separate configuration class or a nested static configuration with `@ConditionalOnClass(name = "...")` at the **class level**.

Conditions do not turn a "non-existent" type into a compilable type. For Java code to compile, the module providing the adapter must still have the SDK at compile time (typically optional/compile-only when published), while the runtime consumer may omit that dependency.

## 8. getResourceLoader(): Resources on the Classpath and Beyond

Although the title emphasizes the first four components, `ConditionContext` also has `getResourceLoader()`. Example:

```java
org.springframework.core.io.Resource resource =
        context.getResourceLoader()
                .getResource("classpath:demo/feature.properties");

boolean exists = resource.exists();
```

This is a fragment inside `matches`. `ResourceLoader` allows locating resources using Spring's location abstraction, such as `classpath:...`. `exists()` only checks whether the resource is accessible under the contract; it does not prove valid content, full permissions for all operations, or reliable network availability.

If you only need to check resource existence, Spring Boot already provides `@ConditionalOnResource`. For remote URLs, **do not** perform network probes inside `Condition.matches` because it slows down startup and makes it unpredictable. Move connectivity checks to an appropriate health check/lifecycle step.

## 9. Evaluation Timing: At Which Phase Do You Read the Context?

This part is critical to avoid wrong results even when Condition code has no syntax errors.

Spring Framework processes configurations in multiple steps. Two phases are represented by `ConfigurationCondition.ConfigurationPhase`:

- `PARSE_CONFIGURATION`: decides whether to parse a `@Configuration` class.
- `REGISTER_BEAN`: decides whether to register the corresponding bean definition.

A plain `Condition` may be evaluated by Spring at appropriate processing points; a `ConfigurationCondition` can explicitly declare the phase in which it wants to run. Boot's built-in conditions are designed to operate properly under this mechanism.

### 9.1. Why Can the Registry Legitimately "Miss" a Bean?

Suppose bean A is declared in application configuration and bean B is intended to be created by auto-configuration. If a condition checks the registry **before** Spring has registered A's definition, it sees `false` even though A is in the source code. After the parser/reader processes further configurations, the registry may already contain A.

Do not use `ConditionContext.getRegistry().getBeanDefinitionCount()` as a final metric for the total number of application beans after startup completes.

### 9.2. Method-Level Conditions Help Check Declared Beans

If a condition depends on a bean definition supplied by the application, placing the condition in the **bean registration** phase is usually better suited than a class-level parse condition. In the demo in the next section, the custom `Condition` is attached **to a `@Bean` method inside an auto-configuration** to inspect a marker declared by the application. This is an intentional demonstration of timing. For production applications, use `@ConditionalOnBean`/`@ConditionalOnMissingBean` instead of writing custom lookups when the logic can be expressed with built-in annotations.

### 9.3. When to Use ConfigurationCondition?

Example of **declaring the phase**:

```java
public final class RegistrationOnlyCondition
        implements org.springframework.context.annotation.ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            org.springframework.context.annotation.ConditionContext context,
            org.springframework.core.type.AnnotatedTypeMetadata metadata) {
        return context.getRegistry()
                .containsBeanDefinition("someMarker");
    }
}
```

This is **illustrative Java class code needing appropriate package/imports**; the marker name is hypothetical. `ConfigurationCondition` extends `Condition` and adds `getConfigurationPhase()`. Do not apply this setup everywhere: if a condition decides immediately whether to parse a class containing optional types, deferring improperly can cause other issues. Choose the phase according to the question the condition actually needs to answer.

## 10. Complete Demo: Using ConditionContext in a Feature

This demo uses **Java 17, Maven, and Spring Boot 3.3.13**. It demonstrates a `FeatureService` created by default if:
- The `demo.feature.enabled` property is enabled (enabled by default);
- The class named in `demo.feature.required-class` is present (defaulting to the JDK class `java.time.Instant`);
- If `demo.feature.require-marker=true`, the application has registered a bean definition named `featureMarker`.

Through this, a concise Condition exercises **Environment, ClassLoader, Registry, and BeanFactory**. Tests will cover both the presence and absence of the marker. The goal is to understand the getters; in production design, you can decompose these conditions into clear built-in annotations.

### 10.1. Directory Structure

```text
condition-context-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── feature/
    │   │       ├── FeatureService.java
    │   │       └── autoconfigure/
    │   │           ├── FeatureGateCondition.java
    │   │           └── FeatureAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/feature/autoconfigure/
            └── FeatureAutoConfigurationTest.java
```

`com.example.app` does not cover `com.example.feature.autoconfigure` in default component scanning; the auto-configuration is discovered via the imports resource, rather than accidentally picked up by component scan.

### 10.2. Maven POM

Create `pom.xml`:

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

    <groupId>com.example</groupId>
    <artifactId>condition-context-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

The parent manages Spring versions compatible with Boot 3.3.13. The demo needs neither a database nor a web server.

### 10.3. Minimal Spring-Independent API

Create `src/main/java/com/example/feature/FeatureService.java`:

```java
package com.example.feature;

@FunctionalInterface
public interface FeatureService {
    String process(String input);
}
```

The service uses a single method so observing the Condition result stays clear.

### 10.4. Custom Condition Using Four Getters

Create `src/main/java/com/example/feature/autoconfigure/FeatureGateCondition.java`:

```java
package com.example.feature.autoconfigure;

import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;

public final class FeatureGateCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        boolean enabled = context.getEnvironment().getProperty(
                "demo.feature.enabled", Boolean.class, true);
        if (!enabled) {
            return false;
        }

        String requiredClass = context.getEnvironment().getProperty(
                "demo.feature.required-class", "java.time.Instant");
        if (!ClassUtils.isPresent(
                requiredClass, context.getClassLoader())) {
            return false;
        }

        boolean requireMarker = context.getEnvironment().getProperty(
                "demo.feature.require-marker", Boolean.class, false);
        if (!requireMarker) {
            return true;
        }

        boolean declaredInRegistry = context.getRegistry()
                .containsBeanDefinition("featureMarker");

        ConfigurableListableBeanFactory factory =
                context.getBeanFactory();

        boolean declaredInFactory = factory == null
                || factory.containsBeanDefinition("featureMarker");

        return declaredInRegistry && declaredInFactory;
    }
}
```

Reading in order:

1. **Environment:** if `demo.feature.enabled` is absent, it defaults to `true`; `false` causes the condition not to match.
2. **Environment + ClassLoader:** reads the required class name, then `ClassUtils.isPresent` checks it via the context's loader; the default `java.time.Instant` is a JDK type present in Java 17.
3. **Environment:** if the marker is not required, returns `true` without reading registry/factory.
4. **Registry:** if the marker is required, checks whether a bean definition named `featureMarker` has been registered.
5. **BeanFactory:** if the factory exists, additionally checks that same bean definition; if the factory is null, avoids dereferencing and relies only on the registry result.
6. **Return:** creates no beans, does not call `getBean()`, does not write to the registry, and simply returns a decision.

Checking both registry and factory in the demo is intentionally slightly redundant to illustrate **both** getters. In a real library, use a suitable built-in bean condition instead of repeating name lookups. Also, `AnnotatedTypeMetadata` is not needed in this logic; the parameter is still required by the interface. You can use metadata to read attributes of custom annotations, but you should not instantiate the described class just to inspect annotations.

**Note on timing:** this condition will be attached to the auto-configuration's `@Bean` method in the next section. Marker definitions in user configuration have already been processed in normal application configuration order before auto-configuration. Do not move this registry logic up to class-level parsing and expect the same result.

### 10.5. Auto-Configuration Registering FeatureService

Create `src/main/java/com/example/feature/autoconfigure/FeatureAutoConfiguration.java`:

```java
package com.example.feature.autoconfigure;

import com.example.feature.FeatureService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    @Conditional(FeatureGateCondition.class)
    @ConditionalOnMissingBean(FeatureService.class)
    FeatureService featureService() {
        return input -> "feature:" + input;
    }
}
```

Distinguish:
- `FeatureGateCondition` is the custom condition; it checks the property, class presence, and marker if required.
- `@ConditionalOnMissingBean(FeatureService.class)` is Boot's **back-off** condition: when the app already supplies a `FeatureService`, auto-configuration does not create the default.
- Both must match for the default `FeatureService` to be registered.

Spring Boot already provides `@ConditionalOnProperty` and `@ConditionalOnClass` for most of the first part of this logic; the demo combines them into one Condition **to study the API**, rather than recommending every starter write manual Conditions.

### 10.6. Registering the Auto-Configuration Candidate

Create the exact resource:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.feature.autoconfigure.FeatureAutoConfiguration
```

This is how Spring Boot 3.x discovers auto-configurations on the classpath. Without this file, the Java class can compile, but the application will not automatically receive the default bean via the imports mechanism.

### 10.7. ApplicationRunner to Observe Whether the Feature Is Present

Create `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.feature.FeatureService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printFeature(
            ObjectProvider<FeatureService> services) {
        return args -> {
            FeatureService service = services.getIfAvailable();
            System.out.println(service == null
                    ? "FEATURE=ABSENT"
                    : "FEATURE=" + service.process("hello"));
        };
    }
}
```

`ObjectProvider<FeatureService>` lets the runner execute even when the bean is absent; that is how you observe an optional feature without failing startup due to a required injection.

Run:

```bash
mvn test
mvn spring-boot:run
```

With default properties, the runner prints **one line**:

```text
FEATURE=feature:hello
```

This is the line printed by `ApplicationRunner`, **not the entire stdout**, since Maven and Spring Boot also produce startup logs.

### 10.8. Disabling via Property

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.feature.enabled=false
```

Line printed by the runner:

```text
FEATURE=ABSENT
```

`Environment` supplies the false property, the custom Condition returns false, so Spring does not register the default `FeatureService`.

### 10.9. Requiring a Class Absent at Runtime

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.feature.required-class=com.example.missing.OptionalSdk
```

Because this hypothetical class name does not exist in the project, `ClassUtils.isPresent(...)` returns false and the runner prints:

```text
FEATURE=ABSENT
```

This is **missing-class detection** behavior, not attempting to connect to a real SDK. When integrating an external SDK, place the class condition on a configuration with proper guard scope and avoid using optional types prematurely in method signatures.

### 10.10. Requiring a Marker and Adding the Bean Definition

Run:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.feature.require-marker=true
```

Without a bean definition named `featureMarker`, the condition does not match; the runner prints:

```text
FEATURE=ABSENT
```

To add the marker, **add the following method inside `DemoApplication`**:

```java
@Bean
String featureMarker() {
    return "ready";
}
```

This is only an **additional fragment**, not a standalone Java file. Run again with the same marker-requiring property:

```text
FEATURE=feature:hello
```

When Spring processes the auto-configuration bean method, the registry and factory can see the marker definition already registered by the user configuration. There is no need to call `getBean("featureMarker")` to check whether the marker exists.

### 10.11. Trying a Consumer Override

Instead of the marker, you can also add inside `DemoApplication`:

```java
@Bean
FeatureService customFeatureService() {
    return input -> "app:" + input;
}
```

This is a separate additional fragment; do not add it at the same time as the marker experiment unless you want to vary multiple conditions. When run with default properties, the runner prints:

```text
FEATURE=app:hello
```

Reason: auto-configuration's `@ConditionalOnMissingBean` backs off because the application already supplied a bean. This differs from the custom `FeatureGateCondition` returning false due to property/classpath/marker.

## 11. Testing Condition Branches with ApplicationContextRunner

Create `src/test/java/com/example/feature/autoconfigure/FeatureAutoConfigurationTest.java`:

```java
package com.example.feature.autoconfigure;

import com.example.feature.FeatureService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FeatureAutoConfiguration.class));

    @Test
    void defaultPropertiesCreateFeature() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context.getBean(FeatureService.class)
                    .process("hello")).isEqualTo("feature:hello");
        });
    }

    @Test
    void disabledPropertySkipsFeature() {
        runner.withPropertyValues("demo.feature.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(FeatureService.class));
    }

    @Test
    void missingRequiredClassSkipsFeature() {
        runner.withPropertyValues(
                "demo.feature.required-class=com.example.missing.OptionalSdk")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(FeatureService.class));
    }

    @Test
    void requiredMarkerButAbsentSkipsFeature() {
        runner.withPropertyValues("demo.feature.require-marker=true")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(FeatureService.class));
    }

    @Test
    void registeredMarkerAllowsFeature() {
        runner.withUserConfiguration(MarkerConfiguration.class)
                .withPropertyValues("demo.feature.require-marker=true")
                .run(context -> {
                    assertThat(context).hasBean("featureMarker");
                    assertThat(context).hasSingleBean(FeatureService.class);
                });
    }

    @Test
    void consumerFeatureBeanOverridesDefault() {
        runner.withUserConfiguration(UserFeatureConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class)
                            .process("hello")).isEqualTo("app:hello");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class MarkerConfiguration {

        @Bean
        String featureMarker() {
            return "ready";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFeatureConfiguration {

        @Bean
        FeatureService customFeatureService() {
            return input -> "app:" + input;
        }
    }
}
```

Run:

```bash
mvn test
```

The test suite verifies six scenarios:

| Test | Question | Expectation |
| --- | --- | --- |
| `defaultPropertiesCreateFeature` | No property/bean overrides | One default `FeatureService` |
| `disabledPropertySkipsFeature` | Environment disables flag | No default feature |
| `missingRequiredClassSkipsFeature` | ClassLoader cannot find class name | No default feature |
| `requiredMarkerButAbsentSkipsFeature` | Registry lacks marker name | No default feature |
| `registeredMarkerAllowsFeature` | User config registered marker definition | Feature is created |
| `consumerFeatureBeanOverridesDefault` | App has `FeatureService` bean | Only app's bean is used |

**Limitation:** `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` supplies the auto-configuration class directly; this test is great for conditions but **does not prove** the JAR's `AutoConfiguration.imports` file is properly discovered. Run `DemoApplication` or a consumer integration test and inspect the packaged resource to verify completely.

The test suite also **does not directly prove all parse/register phase timings across every ApplicationContext type**; it verifies the demo's contract under `ApplicationContextRunner`. For custom conditions depending on the registry in complex systems, add integration tests suited to the deployment environment.

### 11.1. Inspecting the Artifact and Imports Resource

```bash
mvn package
jar tf target/condition-context-demo-0.0.1-SNAPSHOT.jar
```

In a Spring Boot executable JAR, the imports resource is packaged under:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

For a regular library JAR, the resource resides at `META-INF/spring/...` from the root. A class not registered via imports may go unseen by a consuming app even if its conditions match.

## 12. When to Use Built-in Annotations Instead of a Custom Condition?

Most requirements in the demo can be written as multiple declarative conditions:

```java
@AutoConfiguration
public class BuiltInConditionsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.feature", name = "enabled",
            havingValue = "true", matchIfMissing = true)
    @ConditionalOnClass(name = "java.time.Instant")
    @ConditionalOnMissingBean(FeatureService.class)
    FeatureService featureService() {
        return input -> "feature:" + input;
    }
}
```

This is **non-standalone illustrative configuration code**: it requires package/imports and `FeatureService` from the example. It expresses three common conditions in a way Spring Boot understands natively, producing readable positive/negative match reports.

The **required marker by bean name** part can be expressed with `@ConditionalOnBean(name = "featureMarker")` when aligned with application bean definition order; there is no need to write custom registry/factory lookup code.

| Need | Preferred default choice |
| --- | --- |
| Toggle on/off via property | `@ConditionalOnProperty` |
| Depend on a class being present | `@ConditionalOnClass` |
| Depend on a class being absent | `@ConditionalOnMissingClass` |
| Bean type/name present | `@ConditionalOnBean` |
| Create default when no matching bean exists | `@ConditionalOnMissingBean` |
| Exactly one specific bean candidate | `@ConditionalOnSingleCandidate` |
| Resource exists | `@ConditionalOnResource` |
| Context is Servlet/Reactive/web | `@ConditionalOnWebApplication` or corresponding condition |
| Domain-specific logic combining multiple inputs with no suitable built-in | Consider custom `Condition` / `SpringBootCondition` |

**When does a custom Condition bring real value?** For example, an integration requiring a library-specific combination of properties/metadata, meaningful registry state, or a custom multi-attribute annotation; or when you want to provide a reusable condition with thoroughly tested rules.

When writing a condition for a library, consider extending `SpringBootCondition` and returning a `ConditionOutcome` with match/non-match reasons. This helps the condition evaluation report explain decisions better than a custom `Condition` returning only a boolean. Do not log repeatedly on your own or print secrets from property sources.

## 13. Common Mistakes When Using ConditionContext

### 13.1. Calling getBean() Inside matches()

```java
// WRONG FOR CHECKING PURPOSE:
boolean ok = context.getBeanFactory()
        .getBean("client") != null;
```

Besides the risk of `getBeanFactory()` being null, this call can trigger bean instantiation while Spring is still building bean definitions. Read the necessary metadata instead or use `@ConditionalOnBean`.

### 13.2. Taking the Registry Count as the "App's Total Bean Count"

The definition count at evaluation phase is not the total instance count after context refresh; the registry can still change through subsequent steps. Avoid using the count as a feature gate in production without very clear rules.

### 13.3. Checking a Bean by Name When You Actually Need Its Type

A bean `auditClient` can be renamed to `customAuditClient`. If the requirement is "there is an `AuditClient` implementation", a type-based built-in condition is far more resilient than a hardcoded name.

### 13.4. Placing a Definition-Based Condition Too Early

If a condition needs a user application bean but runs during class-level parsing, the registry may not have that definition yet. Move the logic to the proper phase or use Boot's built-in bean conditions. Do not work around it by calling `getBean()` to force Spring to instantiate early.

### 13.5. Failing to Handle Null BeanFactory or ClassLoader

`getBeanFactory()` and `getClassLoader()` are not guaranteed to return a non-null instance in every context. Follow the contract; do not omit null checks just because current tests always provide a value.

### 13.6. Using Class.forName with initialize=true or Instantiating the SDK to "Test Presence"

These actions can trigger static initialization or unready dependencies. For classpath conditions, prefer `@ConditionalOnClass` and Boot's metadata scanning; if forced to check manually, use `ClassUtils.isPresent` or controlled class-loading APIs.

### 13.7. Writing a Condition with Side Effects

Writing files, sending network requests, registering beans, mutating the environment, or removing bean definitions inside `matches` makes startup unpredictable. A Condition should act like a **predicate** over the current context.

### 13.8. Treating Environment as a Permanently Immutable Configuration Source

Environment can be assembled across multiple property sources and profiles. Condition results primarily apply during context initialization; changing a property after startup does not automatically re-evaluate conditions and add/remove registered beans.

### 13.9. Confusing "Class Exists" with "External Service Is Usable"

`ClassUtils.isPresent("com.vendor.Client", loader)` does not guarantee the endpoint is reachable, the token is valid, or the SDK version is compatible. A classpath condition answers only one part of enabling an integration; health checks and exception handling are separate responsibilities.

### 13.10. Checking Definition Names While Forgetting Parent Contexts

`registry.containsBeanDefinition("x")` checks that specific registry, not the entire hierarchy by default. In parent/child `ApplicationContext` structures, built-in conditions offer `SearchStrategy` options better suited than manual name lookups.

### 13.11. Writing a Custom Condition for What Already Has a Standard Annotation

This easily leads to bugs in property value handling, bean definitions, and missing condition messages. Prefer built-in annotations; reserve custom code for genuinely specialized logic.

## 14. How to Debug When a Condition Does Not Match

When auto-configuration does not create a bean as expected, separate two questions:

**A. Was the auto-configuration class discovered?** Check the right JAR, runtime classpath, `AutoConfiguration.imports`, exclusions, and import filters.

**B. Once the class was evaluated, which condition failed to match?** Enable the condition evaluation report and check properties, classpath, bean definitions, phase, and bean overrides.

In the demo:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Boot-provided conditions usually show clear reasons in the report. A custom `Condition` returning only a boolean may provide less detail. If you need structured custom reporting, `SpringBootCondition` with `ConditionOutcome` and reason messages is the right path.

### 14.1. Diagnostic Matrix

| Symptom | Likely cause and where to check |
| --- | --- |
| Property `demo.feature.enabled=false` | Environment gate returns false |
| Required class not found | Runtime classpath/ClassLoader; may be an optional dependency |
| `require-marker=true` without definition | Registry/factory lacks `featureMarker` or has a different name |
| Consumer already defined `FeatureService` | `@ConditionalOnMissingBean` backed off, **not** necessarily the custom Condition returning false |
| Tests pass but real app lacks the bean | Imports resource, packaging, runtime dependencies, component scan |
| Bean-dependent condition behaves differently across runs | Check phase, registration order, parent/child context |
| Startup fails even though condition is true | Factory method, dependency injection, type mismatch, or side effect during bean creation |
| BeanFactory is null | How `ConditionContext` was constructed in that environment; handle the missing factory case |

In tests, you can use `ApplicationContextRunner` to vary properties, classloaders, and user configurations independently. For absent classes, `FilteredClassLoader` in `spring-boot-test` can simulate an environment missing a specific dependency when testing an optional adapter.

### 14.2. Do Not Leak Sensitive Information

Condition reports or custom logs can accidentally expose property values, including endpoints or secrets. When designing reason messages, describe **which condition passed/failed** without printing tokens/passwords. Do not enable long-term debug logging in production without considering access scope.

## 15. Self-Check Questions

**Q1.** Are `ConditionContext` and `ApplicationContext` the same interface?

**Answer:** No. `ConditionContext` provides abstractions relevant to the condition evaluation phase; it does not expose the full lifecycle and bean access of `ApplicationContext`.

**Q2.** Does `getRegistry().containsBeanDefinition("foo")` returning true mean bean `foo` has already been instantiated?

**Answer:** No. It refers to a bean definition registered in the current registry; the object may not exist yet.

**Q3.** Why should you avoid calling `getBean()` inside a Condition?

**Answer:** It can trigger premature instantiation, side effects, and dependency/circular errors while Spring is parsing configuration. Rely on metadata or built-in conditions.

**Q4.** Will a property absent from `Environment` always evaluate to false?

**Answer:** No. It depends on the condition's logic and default value. In the demo, `enabled` defaults to `true`; `require-marker` defaults to `false`.

**Q5.** Does having `SomeClient.class` on the compile classpath guarantee the production `ClassLoader` sees it?

**Answer:** No. The runtime classpath can differ, especially with optional, provided, compile-only dependencies, or custom loaders.

**Q6.** Is `getBeanFactory()` always non-null?

**Answer:** No, per the `ConditionContext` contract. Condition code must handle the case where no factory is available.

**Q7.** Why can a registry-based condition yield different results during the parse phase versus the register phase?

**Answer:** Bean definitions are added as Spring parses and registers configurations; the registry at the two moments can hold different numbers of definitions.

**Q8.** If the logic only needs "a bean of type X exists", should you write a custom Condition using the registry?

**Answer:** Usually no. Prefer `@ConditionalOnBean(X.class)` or `@ConditionalOnMissingBean(X.class)` according to the intended semantics.

**Q9.** Does `@ConditionalOnClass` matching guarantee the SDK bean instantiates and connects successfully?

**Answer:** No. It only checks class presence under Boot's mechanism; version compatibility, configuration, and connectivity are separate concerns.

**Q10.** Does an `ApplicationContextRunner` test that directly passes the auto-configuration class prove the imports resource is correct?

**Answer:** No. It tests conditions/bean registration of the supplied class; a consumer integration test or JAR artifact inspection is needed to verify discovery.

## 16. Summary

`ConditionContext` serves as the **read-only context when evaluating a condition**:

```text
Environment   -> which properties and profiles are active?
Registry      -> is bean definition named X registered here?
BeanFactory   -> is bean metadata available? (may be null)
ClassLoader   -> is the required class visible?
ResourceLoader-> can the required resource be located?
                      |
                      v
             Condition.matches(...) -> true / false
                      |
                      v
        Spring proceeds with or skips the corresponding component
```

When designing auto-configuration:
- **Prefer Boot's built-in conditions** for properties, classes, beans, and resources.
- **Read metadata, do not instantiate beans inside `matches`**.
- **Be phase-aware**: registry/factory may not know every definition yet.
- **Keep conditions pure-read and side-effect-free**.
- **Test both matching and non-matching conditions**, plus consumer overrides and packaging metadata.

### Official References

- Spring Framework 6.1 API — `ConditionContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html
- Spring Framework 6.1 API — `Condition`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html
- Spring Framework 6.1 API — `ConfigurationCondition`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration (Condition Annotations & Testing): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `ConditionalOnBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 API — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Framework 6.1 API — `BeanDefinitionRegistry`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistry.html
- Spring Framework 6.1 API — `Environment`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/Environment.html
