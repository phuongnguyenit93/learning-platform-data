# AnnotatedTypeMetadata and Annotation Data During Condition Evaluation

## 1. Why Does Spring Need to Read Metadata Instead of Simply Creating Objects?

A Spring Boot application can declare conditional configurations and beans:

```java
@Configuration
@Conditional(SomeCondition.class)
class OptionalConfiguration {

    @Bean
    @Conditional(AnotherCondition.class)
    OptionalService optionalService() {
        return new OptionalService();
    }
}
```

The snippet above is **illustrative only**: `SomeCondition`, `AnotherCondition`, and `OptionalService` are hypothetical types, not a standalone runnable program.

Before Spring decides to register `OptionalConfiguration` and `optionalService`, it must know which annotations are attached to the corresponding **class** or **method**, including their annotation attributes. Creating the bean first and then asking "is it allowed to be created?" both wastes resources and violates lifecycle order.

Spring Framework passes two objects into a `Condition`:

```java
boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
```

- **`ConditionContext`** supplies the context for inspection: `Environment`, registry, bean factory, class loader, and resource loader where applicable.
- **`AnnotatedTypeMetadata`** supplies **annotation information on the target being evaluated**: annotation types, declared attributes, meta-annotations, and how annotations are merged under Spring's mechanism.
- **Return value**: `true` allows Spring to proceed with registering the component under this condition; `false` vetoes registration of that component.

A `Condition` should not create business beans itself or call `getBean()` to test. Conditions are checked during the phases when Spring is building the registry; depending on timing, the required instances might not exist yet.

## 2. What Is AnnotatedTypeMetadata?

The `org.springframework.core.type.AnnotatedTypeMetadata` interface describes annotations of **a specific class or method** without forcing the caller to obtain a reflective `Class<?>`/`Method`. Spring can use an ASM-based implementation that reads class metadata alongside a reflection-based implementation.

Relationship of the main interfaces:

```text
                   AnnotatedTypeMetadata
                      /            \
                     /              \
        AnnotationMetadata        MethodMetadata
          (for a class)           (for a method)
```

This is an interface inheritance relationship, not a bean hierarchy. During condition processing:

- When `@Conditional` is on a **configuration class**, the `metadata` parameter typically provides `AnnotationMetadata` capabilities.
- When `@Conditional` is on a **`@Bean` method**, the `metadata` parameter typically provides `MethodMetadata` capabilities.
- Condition code can be written once against the common methods of `AnnotatedTypeMetadata`, without needing to know whether it is evaluating a class or a method.

Metadata is **not** a `BeanDefinition`, **not** a bean instance, and **not** the set of properties in `application.yml`. It describes the annotations Spring has read on the element under evaluation. To read environment properties, use `ConditionContext#getEnvironment()`.

### Commonly Used APIs

| API | Return / Meaning | Notes |
| --- | --- | --- |
| `getAnnotations()` | `MergedAnnotations` for direct and meta-annotations | Modern API supporting composed annotations and aliases |
| `isAnnotated(String)` | Checks if the matching annotation is present, including via meta-annotations | Takes the **fully qualified class name** of the annotation |
| `getAnnotationAttributes(String)` | `Map<String,Object>` of attributes processed/merged by Spring | Can return `null` when not found |
| `getAnnotationAttributes(String, boolean)` | As above, with an option to represent class-valued attributes as string names | `true` helps avoid resolving a class from an attribute |
| `getAllAnnotationAttributes(String)` | `MultiValueMap` of attribute groups across repeated occurrences | Merging/override semantics differ from `getAnnotationAttributes`; do not substitute arbitrarily |
| `AnnotationMetadata#getClassName()` | Name of the class being described | Use only after confirming metadata is class-level |
| `AnnotationMetadata#getAnnotatedMethods(...)` | `MethodMetadata` entries for annotated methods | Only available on class-level metadata |
| `MethodMetadata#getMethodName()` | Name of the method being described | Only available on method-level metadata |
| `MethodMetadata#getReturnTypeName()` | Name of the method's return type | Useful when analyzing `@Bean` methods |

Example reading a specific annotation:

```java
String annotationName = "com.example.condition.FeatureEnabled";
Map<String, Object> attrs =
    metadata.getAnnotationAttributes(annotationName);

if (attrs != null) {
    String property = (String) attrs.get("property");
}
```

This snippet is **not standalone**: it assumes the `metadata` variable was passed by Spring into `Condition` and `java.util.Map` is imported. A production condition must clearly define whether the annotation is required, check data types, and handle missing values with proper semantics.

### What Can "Annotation Data" Include?

Suppose you create an annotation:

```java
@FeatureEnabled(
    property = "demo.feature.enabled",
    matchIfMissing = true
)
```

Readable data can include:

- Annotation name: `com.example.condition.FeatureEnabled`.
- `property` attribute: the string `"demo.feature.enabled"`.
- `matchIfMissing` attribute: the value `true`.
- Annotations that `@FeatureEnabled` uses as meta-annotations, such as `@Conditional`.
- Attributes processed by Spring when a composed annotation uses `@AliasFor`.

Thus, a `Condition` can check **rules declared by the annotation itself** and compare them against **state outside the annotation** from `Environment` or the registry.

## 3. What Does @Conditional Decide?

The Spring annotation:

```java
@Conditional(FeatureEnabledCondition.class)
```

can be placed directly on a configuration class, a `@Bean` method, or used as a meta-annotation to build custom annotations. It accepts one or more classes implementing `org.springframework.context.annotation.Condition`.

With multiple conditions on the same component, in principle **all** required conditions must match for the element to be eligible for registration. Spring has corresponding rules for ordering/evaluating conditions; do not treat conditions as an arbitrary sequence of interchangeable calls.

### Scope of Impact on Class vs. Method

```text
@Configuration
@Conditional(ClassCondition.class)
class FeatureConfiguration {
    @Bean
    @Conditional(MethodCondition.class)
    Service service() { ... }
}
```

- If the **class-level** condition is false, the configuration class may be skipped, meaning its associated `@Bean`, `@Import`, and `@ComponentScan` declarations are not processed in the normal way.
- If the **class-level** condition is true but the **method-level** condition is false, the `@Bean` method is skipped while other parts of the configuration class can still be processed.
- If both are true, the bean definition can be registered; **it is still not guaranteed that the instance will be created successfully** due to dependencies and lifecycle.

`@Conditional` is a tool for deciding registration eligibility, not an annotation for running or testing an existing bean. This is especially important for auto-configuration: `@AutoConfiguration` classes and the `@Bean` methods inside them can carry many different conditions.

## 4. What Does ConditionContext Provide That AnnotatedTypeMetadata Does Not?

The `Condition` signature has two parameters because they answer **two different questions**:

```text
AnnotatedTypeMetadata:
  Which annotations are on this class/method?
  Which attributes does that annotation declare?
  Are there any related meta-annotations/aliases?

ConditionContext:
  Which properties are currently in effect?
  Which bean definitions have been registered?
  Which class loader is being used?
  Which resources can be accessed?
```

Typical `ConditionContext` APIs:

```java
context.getEnvironment()
context.getRegistry()
context.getBeanFactory()
context.getClassLoader()
context.getResourceLoader()
```

This is an API illustration inside a `matches(...)` method, not standalone runnable code. Depending on the context and phase, some parts may be absent or incomplete. Conditions should only read appropriate data and avoid instantiating bean instances during the definition registration phase.

For example: metadata says the annotation requires the property `"demo.feature.enabled"`, while environment says the actual value of that key in this run is `true` or `false`.

You can think of a condition as a function:

```text
matches(context, metadata)
    = rules described in the annotation
      + contextual info inspectable at this phase
      -> boolean
```

Not every `Condition` needs to read every API. For example, a condition depending only on the environment does not need to know the annotated class name; a classpath-based condition can use the class loader.

## 5. Reading Direct Annotations, Meta-Annotations, and Composed Annotations

Spring cares not only whether `@Conditional` is written directly or indirectly. An annotation such as:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(FeatureEnabledCondition.class)
public @interface FeatureEnabled {
    String property();
    boolean matchIfMissing() default false;
}
```

is both a user-facing annotation and a **composed** annotation with the `@Conditional` meta-annotation. When `@FeatureEnabled` appears on a class or method, Spring can discover the condition through the meta-annotation.

The principles:

1. **Direct annotation:** an annotation placed directly on the element, such as `@FeatureEnabled`.
2. **Meta-annotation:** an annotation placed on another annotation; here `@Conditional` sits on `@FeatureEnabled`.
3. **Merged annotations:** Spring provides the `MergedAnnotations` model to handle the annotation system, including many cases of aliases and composed annotations.
4. **Attribute aliasing:** with `@AliasFor`, an attribute of a composed annotation can be mapped to an attribute at another level. When aliases exist, reading through Spring's API is usually more accurate than writing simple reflection and assembling a Map manually.
5. **Repeated annotations:** an annotation can appear along multiple paths in a hierarchy. Know whether you want **a single merged attribute set** or **all occurrences** before choosing `getAnnotationAttributes` or `getAllAnnotationAttributes`.

Note: `AnnotatedTypeMetadata` can avoid loading **the described class**, but that does not mean every kind of annotation can be accessed without loading any classes at all. Some annotations and related types may still need to be loaded; class-valued attributes and annotations with missing dependencies must be designed carefully.

## 6. Runnable Java 17 Example: Same Condition for Class and @Bean

We build a Spring Boot application **without a web server**, featuring a custom `@FeatureEnabled` annotation and a `Condition` that reads:

- Property name and `matchIfMissing` from **`AnnotatedTypeMetadata`**.
- Effective property value from **`ConditionContext#getEnvironment()`**.

The annotation is attached to both a `@Configuration` class and a `@Bean` method. On startup, the program reads back the class and method metadata to prove they are two distinct levels. Thanks to `ObjectProvider`, the program still runs when the condition disables the bean.

The example uses **JDK 17+**, **Spring Boot 3.3.13**, and **Maven**.

### 6.1. Project Structure

```text
annotation-metadata-demo/
├── pom.xml
└── src/main/java/demo/
    ├── MetadataDemoApplication.java
    ├── condition/
    │   ├── FeatureEnabled.java
    │   └── FeatureEnabledCondition.java
    ├── config/
    │   └── GreetingConfiguration.java
    └── model/
        └── Greeting.java
```

The main class is in package `demo`, and packages `condition`, `config`, and `model` sit underneath it. This lets Spring Boot scan `GreetingConfiguration`; classes without stereotypes will not automatically become beans just by sharing the package.

### 6.2. pom.xml

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
    <artifactId>annotation-metadata-demo</artifactId>
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

`spring-boot-starter` brings in the necessary Spring container dependencies, so the example does not need to declare separate `spring-core`, `spring-context`, or `spring-boot` JARs manually.

### 6.3. Annotation Applicable to Both Class and Method

**`src/main/java/demo/condition/FeatureEnabled.java`**

```java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(FeatureEnabledCondition.class)
public @interface FeatureEnabled {

    String property();

    boolean matchIfMissing() default false;
}
```

Two attributes describe the policy:

- `property`: the key name to check in the Spring `Environment`.
- `matchIfMissing`: the default result if the property does not exist yet (this example sets it to `false` when undeclared).

`@Conditional` on the annotation lets Spring use `FeatureEnabledCondition` without declaring it separately on every class and method.

### 6.4. Condition Reads Metadata, Then Checks Environment

**`src/main/java/demo/condition/FeatureEnabledCondition.java`**

```java
package demo.condition;

import java.util.Map;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
            metadata.getAnnotationAttributes(FeatureEnabled.class.getName());

        if (attributes == null) {
            return false;
        }

        String property = (String) attributes.get("property");
        boolean matchIfMissing = (Boolean) attributes.get("matchIfMissing");

        return context.getEnvironment()
            .getProperty(property, Boolean.class, matchIfMissing);
    }
}
```

This is the core of the lesson:

1. `getAnnotationAttributes(...)` reads the attributes declared by `@FeatureEnabled` on **the element currently being evaluated**.
2. The condition does not need to cast `metadata` to `AnnotationMetadata` or `MethodMetadata`, because the common API is sufficient.
3. `Environment#getProperty(key, Boolean.class, defaultValue)` converts the property to boolean; if missing, it uses `matchIfMissing` declared in the annotation.
4. The method does not call `getBean()`, create instances, or mutate the registry. It only answers whether this annotation satisfies the condition.

This is a **condition designed specifically for the lesson**, not a full replacement for `@ConditionalOnProperty`. In real applications, when only a standard boolean property is needed, prefer Spring Boot's built-in annotation for battle-tested behavior and condition reporting.

### 6.5. Simple Model

**`src/main/java/demo/model/Greeting.java`**

```java
package demo.model;

public record Greeting(String message) {
}
```

This record has no `@Component`, so Spring does not register it automatically. A `Greeting` bean will only exist if the `@Bean` method below satisfies its conditions.

### 6.6. One Condition on the Class, One Condition on the Method

**`src/main/java/demo/config/GreetingConfiguration.java`**

```java
package demo.config;

import demo.condition.FeatureEnabled;
import demo.model.Greeting;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@FeatureEnabled(
    property = "demo.module.enabled",
    matchIfMissing = true
)
public class GreetingConfiguration {

    @Bean
    @FeatureEnabled(
        property = "demo.greeting.enabled",
        matchIfMissing = true
    )
    Greeting greeting() {
        return new Greeting("Hello from Spring");
    }
}
```

Evaluation order:

- The `GreetingConfiguration` class must satisfy `demo.module.enabled`. Otherwise, this configuration is skipped; the `greeting()` method is not registered through this path.
- Once the class is selected, the `@Bean greeting()` method must also satisfy `demo.greeting.enabled`.
- Only when both required conditions match can the `greeting` bean definition be registered.
- `Greeting` is created by the container after the bean definition is valid; `AnnotatedTypeMetadata` describes the annotation, **not the `Greeting` instance**.

Both properties are defined by this example; Spring Boot does not provide them as built-in properties.

### 6.7. Observing AnnotationMetadata and MethodMetadata

**`src/main/java/demo/MetadataDemoApplication.java`**

```java
package demo;

import java.util.Map;
import demo.condition.FeatureEnabled;
import demo.config.GreetingConfiguration;
import demo.model.Greeting;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.type.AnnotationMetadata;
import org.springframework.core.type.MethodMetadata;

@SpringBootApplication
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ObjectProvider<Greeting> greetings) {
        return args -> {
            AnnotationMetadata classMetadata =
                AnnotationMetadata.introspect(GreetingConfiguration.class);

            Map<String, Object> classAttributes =
                classMetadata.getAnnotationAttributes(
                    FeatureEnabled.class.getName());

            MethodMetadata methodMetadata = classMetadata
                .getAnnotatedMethods(FeatureEnabled.class.getName())
                .stream()
                .filter(m -> m.getMethodName().equals("greeting"))
                .findFirst()
                .orElseThrow();

            Map<String, Object> methodAttributes =
                methodMetadata.getAnnotationAttributes(
                    FeatureEnabled.class.getName());

            System.out.println("CLASS_PROPERTY: "
                + classAttributes.get("property"));
            System.out.println("METHOD_NAME: "
                + methodMetadata.getMethodName());
            System.out.println("METHOD_PROPERTY: "
                + methodAttributes.get("property"));

            Greeting greeting = greetings.getIfAvailable();

            System.out.println("GREETING_PRESENT: "
                + (greeting != null));
            if (greeting != null) {
                System.out.println("GREETING: "
                    + greeting.message());
            }
        };
    }
}
```

Here `AnnotationMetadata.introspect(GreetingConfiguration.class)` is a **reflection-based way to observe metadata in the example**, not a claim that Spring always uses this exact metadata instance at startup. During classpath scanning, Spring can read metadata via ASM.

`classMetadata.getAnnotatedMethods(...)` returns the `MethodMetadata` for methods marked with the matching annotation. Filtering by name `greeting` keeps the result clear and independent of listing order. Even when the configuration is excluded by a condition, `GreetingConfiguration.class` is still on the classpath, so this reflection-based class metadata reading **still works**; only its bean is not registered into the context.

Use `ObjectProvider<Greeting>` instead of required `Greeting` injection so runs with the condition disabled do not fail due to a missing bean.

## 7. Running Tests and Reading the Exact Output

From the directory containing `pom.xml`, with Maven and Java 17+:

```bash
mvn -q -DskipTests package
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Excluding the Boot banner and logs, the lines printed by our code in order:

```text
CLASS_PROPERTY: demo.module.enabled
METHOD_NAME: greeting
METHOD_PROPERTY: demo.greeting.enabled
GREETING_PRESENT: true
GREETING: Hello from Spring
```

Explanation: since no properties are supplied and both annotations set `matchIfMissing=true`, both class and method conditions match. Spring registers the `Greeting` bean and `ObjectProvider` finds it.

### 7.1. Disabling the Method-Level Condition

Run:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.enabled=false
```

Lines printed by the program:

```text
CLASS_PROPERTY: demo.module.enabled
METHOD_NAME: greeting
METHOD_PROPERTY: demo.greeting.enabled
GREETING_PRESENT: false
```

The configuration class remains eligible because `demo.module.enabled` is undeclared and `matchIfMissing=true`. However, the condition on `@Bean greeting()` reads **method-level** metadata, sees `demo.greeting.enabled=false` in the environment, and returns `false`. Thus the method's bean definition is not registered.

### 7.2. Disabling the Class-Level Condition

Run:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.module.enabled=false
```

Lines printed by the program:

```text
CLASS_PROPERTY: demo.module.enabled
METHOD_NAME: greeting
METHOD_PROPERTY: demo.greeting.enabled
GREETING_PRESENT: false
```

This time the `GreetingConfiguration` class is excluded when the class-level condition fails to match. Even though the method's default attribute allows it, the `@Bean` inside the class is no longer processed through the skipped configuration. The metadata printout still runs because it **reads annotations from the Java class**, regardless of whether the `Greeting` bean was registered by Spring.

### 7.3. Both Properties Set to true

Run:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.module.enabled=true \
  --demo.greeting.enabled=true
```

The printed lines match the default case at the start of section 7. There are no "two beans" because each condition only allows or vetoes registering the corresponding definition; it does not duplicate objects when enabled.

### 7.4. Summary Table

| `demo.module.enabled` | `demo.greeting.enabled` | `Greeting` bean result |
| --- | --- | --- |
| Unset | Unset | Present (both `matchIfMissing=true`) |
| `true` | `true` | Present |
| `true` | `false` | Absent (method-level condition) |
| `false` | `true` | Absent (class-level condition) |
| `false` | `false` | Absent (class-level condition already false) |
| Unset | `false` | Absent (method-level condition false) |

Across all runs, `AnnotationMetadata.introspect(...)` still sees **the annotation attributes written in source**. What changes is the **`Environment` value**, so the bean registration decision differs without modifying the Java class.

## 8. When Do You Need to Cast to AnnotationMetadata or MethodMetadata?

Most custom conditions only need:

```java
metadata.getAnnotationAttributes(MyAnnotation.class.getName())
```

However, some specialized conditions need extra class/method details:

```java
if (metadata instanceof AnnotationMetadata classMetadata) {
    String className = classMetadata.getClassName();
    // inspect class name or metadata of related methods
}
else if (metadata instanceof MethodMetadata methodMetadata) {
    String methodName = methodMetadata.getMethodName();
    String returnType = methodMetadata.getReturnTypeName();
    // logic specific to a @Bean method
}
```

This is an illustrative snippet requiring `metadata` and imports inside a `Condition` implementation class. **Do not assume** every `AnnotatedTypeMetadata` has `getClassName()` or `getMethodName()`: they belong to two different sub-interfaces.

When a condition depends on whether it is evaluating a class or a method, ask yourself if that is the right design. Sometimes writing two separate annotations/conditions makes rules clearer than one condition trying to apply everywhere.

### What Else Can AnnotationMetadata Be Used to Read?

Beyond common annotation attributes, `AnnotationMetadata` combines class structure information via `ClassMetadata`:

- Class name (`getClassName()`).
- Superclass or interface names when the metadata includes that data.
- Direct annotations (`getAnnotationTypes()`).
- Annotated methods (`getAnnotatedMethods(...)`).
- Methods declared by the class (`getDeclaredMethods()`).

Not all metadata should drive a condition: for example, a condition with side effects when checking a class name is usually harder to test than one based on a specific property or classpath check.

## 9. Reading Annotation Data as a Map vs. MergedAnnotations

Both approaches exist in modern Spring Framework, with different levels of expressiveness.

### Map-Based API

```java
Map<String, Object> attrs = metadata.getAnnotationAttributes(
    FeatureEnabled.class.getName());

if (attrs != null) {
    String key = (String) attrs.get("property");
}
```

Advantage: simple and easy to integrate when the annotation is identified by **a string class name**. Caveat: returns `null` if the annotation is not found, and reading attributes requires knowing the exact value types.

### MergedAnnotations API

```java
String key = metadata.getAnnotations()
    .get(FeatureEnabled.class)
    .getString("property");
```

This is an illustrative snippet assuming `metadata`/`FeatureEnabled` are in scope. It is convenient when using the annotation type at compile time and retrieving attributes via `MergedAnnotation`. For complex composed annotations or `@AliasFor`, rely on Spring's merged semantics rather than inferring a Map through ad-hoc reflection.

`getAnnotationAttributes(annotationName, true)` is also useful when an annotation has `Class`-valued attributes: in supported cases, it can return class names as strings instead of forcing immediate resolution of a `Class<?>`. This is not a mechanism to "disable class loading completely"; the annotation itself and other elements may still need to be loaded.

### Repeatable / Meta-Annotation Cases

When an annotation occurs multiple times, `getAllAnnotationAttributes` returns a `MultiValueMap` representing multiple attribute sets, but you must carefully read the Javadoc on how attributes from composed/aliased annotations are handled. Do not replace `getAnnotationAttributes` with `getAllAnnotationAttributes` expecting them to always be equivalent.

## 10. Annotation Metadata in Auto-Configuration

In Spring Boot, many built-in conditions are annotation-driven: `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, `@ConditionalOnResource`, and others. Spring Boot uses `SpringBootCondition` as the base class for many conditions and provides `ConditionOutcome` to record match/non-match reasons.

Important signature in Boot:

```java
ConditionOutcome getMatchOutcome(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
```

This is an API signature for reference: when **extending `SpringBootCondition`**, implement `getMatchOutcome(...)`, rather than overriding `matches(...)` which `SpringBootCondition` handles itself. The example in section 6 uses plain `Condition`, so implementing `matches(...)` is correct.

Key distinctions:

| Component | Metadata / data type | Purpose |
| --- | --- | --- |
| `AnnotatedTypeMetadata` | Annotations of a class/method under evaluation | `Condition.matches(...)` evaluates the condition |
| `ConditionContext` | Environment, registry, classloader, resources | Queries state external to the annotation |
| `AutoConfigurationMetadata` (Boot) | Metadata generated by annotation processor for auto-configuration candidates | Optimizes early filtering before parsing full configurations |
| `BeanDefinition` | Container metadata on how to create a bean | Registered if required conditions match |
| `ConfigurationProperties` | Configuration data bound into objects when the corresponding system runs | Not annotation metadata of a `Condition` |

**`AnnotatedTypeMetadata` and `AutoConfigurationMetadata` are not the same interface.** Both relate to optimizing/reading metadata, but they have different timing, structure, and responsibilities.

### Conditions on Auto-Configuration Classes and @Bean Methods

An auto-configuration class can carry a class-level condition:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.OptionalClient")
class OptionalClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Connector.class)
    Connector connector() { return new Connector(); }
}
```

This is illustrative code, not standalone. The class-level condition checks the classpath; the method-level condition checks for matching bean candidates at registration time. The metadata passed to a condition depends on which element is being evaluated.

Do not assume all conditions can run at a single point in time. Spring may evaluate during configuration parsing or bean registration; registry-dependent conditions must pay attention to order. A custom condition relying on bean **instances** before context refresh can break startup logic.

## 11. ConfigurationCondition: Choosing the Right Evaluation Phase When Needed

`org.springframework.context.annotation.ConfigurationCondition` extends `Condition` so a condition can declare the appropriate phase:

```java
ConfigurationPhase getConfigurationPhase();
```

Two meaningful phases:

- **`PARSE_CONFIGURATION`**: decides whether to parse this configuration class.
- **`REGISTER_BEAN`**: decides at the bean definition registration stage.

This is an advanced tool. A plain `Condition` does not specify a phase; the framework determines where/when to check during configuration processing. If a condition needs to observe already registered bean definitions, carefully consider phase, ordering, and the possibility of incomplete candidates.

Avoid:

- Calling `context.getBeanFactory().getBean(...)` inside `matches`.
- Mutating the registry when the condition is only asked for a true/false decision.
- Assuming all singletons are already instantiated during the `REGISTER_BEAN` phase.
- Relying on logging side effects to determine condition order; Spring may invoke a condition multiple times across phases or follow different processing paths.

For simple conditional bean creation, built-in annotations like `@ConditionalOnProperty` are better suited. A custom `ConfigurationCondition` is valuable when you genuinely need a specialized configuration parsing/registration policy.

## 12. Common Mistakes

### 12.1. Reading Annotation Values by Looking Up a Same-Named Property in Environment

**Wrong:** metadata itself holds the values from `application.properties`.

**Right:** metadata holds attributes **on the annotation** such as the key name and default flag; `Environment` holds the property value loaded when the application starts. In the example, `metadata` returns `"demo.greeting.enabled"` while `Environment` returns `true` or `false` for that key.

### 12.2. Casting Every Metadata Object to AnnotationMetadata

A `Condition` used on a `@Bean` method may receive `MethodMetadata`. Casting directly without a type check can throw `ClassCastException`. Prefer the common `AnnotatedTypeMetadata` API, or use `instanceof` if you need type-specific details.

### 12.3. Assuming getAnnotationAttributes Is Never Null

False. The annotation might be absent from the element or looked up with an incorrect name. Handle `null`/absent results and understand your custom annotation's contract.

### 12.4. Instantiating Beans Inside a Condition to "See If It Runs"

This violates the separation between registration decisions and instance creation. It can cause circular dependencies, eager initialization, missing post-processors, or premature side effects. Only read information appropriate to the current phase.

### 12.5. Confusing Condition true with Bean Existence

`true` only makes the component eligible under that condition. The class/method may have other conditions or fail during instantiation. `false` typically prevents the corresponding definition from being registered, which differs from deferring instantiation with `@Lazy`.

### 12.6. Treating Meta-Annotations and Aliases Like Plain Java Reflection

Spring supports composed annotations and aliases, so calling `getDeclaredAnnotation(...)` directly and handling it manually may diverge from the metadata Spring sees. Use `getAnnotations()`/`getAnnotationAttributes()` when you want Spring's exact semantics.

### 12.7. Creating a Custom Condition Just to Toggle a Boolean Property

If the requirement is merely `feature.enabled=true`, `@ConditionalOnProperty` is usually clearer and easier to maintain while leveraging Boot's built-in condition diagnostics. Writing a custom `Condition` is great for learning the mechanism; weigh the trade-offs before shipping one to production.

### 12.8. Equating ASM-Read Metadata with Reflection

`AnnotationMetadata.introspect(SomeClass.class)` uses an already loaded Java class; classpath scanning can read metadata from `.class` files via ASM without loading the target class immediately. Both implementations can expose the same interface, yet differ in mechanism and class-loading timing. Do not conclude from the example's introspection call that all internal Spring paths use reflection.

## 13. Evidence-Based Debugging

If a bean does not appear as expected:

1. **Locate the annotation:** `@Configuration` level, `@Bean` level, or custom meta-annotation.
2. **Verify the actual metadata:** fully qualified annotation name, attributes, value types, defaults, and aliases.
3. **Cross-check Environment:** was the property loaded, is the boolean value valid, did a profile alter the value?
4. **Evaluate the condition in the right phase:** does the condition depend on other bean definitions or the classloader?
5. **Distinguish missing definition from instantiation failure:** if the condition is `false`, the bean definition may be absent; if the condition is `true` but construction fails, inspect the root cause of `BeanCreationException`.
6. **Enable diagnostics:** for Boot built-in conditions, use `--debug` to view the Conditions Evaluation Report. For a plain custom `Condition`, do not assume it will show detailed reason messages like `SpringBootCondition`; add controlled logging or write unit tests.

Example checking the application output from section 6:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.enabled=false \
  --debug
```

The lines printed by the application itself do not change compared to section 7.1; Boot may add debug logs. A condition without its own logging can still return the right boolean and cause the bean definition to be skipped.

### Testing Conditions Without Starting a Server

No HTTP server is needed in this lesson because we are only observing the IoC container. For real auto-configuration libraries, use `ApplicationContextRunner` from `spring-boot-test` to spin up lightweight contexts under combinations of properties/beans and assert which beans are registered. When testing annotation metadata, cover:

- Annotations placed on classes and on methods.
- Missing properties, `true`, and `false`.
- Composed annotations and default attributes.
- Metadata missing the required annotation.
- Other conditions present simultaneously.
- A `@Bean` method whose definition exists but fails during instantiation (distinct from condition false).

You do not need to call `getBean()` inside the `Condition` itself to perform these tests.

## 14. Self-Check Questions

**Q1.** Does `AnnotatedTypeMetadata` already hold the `demo.module.enabled` value from the configuration file?

**Answer:** No. It describes the annotation and attributes such as the key name. The effective property value lives in `Environment` via `ConditionContext`.

**Q2.** When a condition is placed on `@Bean greeting()`, is `metadata` necessarily an `AnnotationMetadata`?

**Answer:** No. It may provide `MethodMetadata` capabilities. Use the common `AnnotatedTypeMetadata` API or check the type before casting if needed.

**Q3.** How does `@FeatureEnabled` in the example connect to `Condition`?

**Answer:** The custom annotation itself is meta-annotated with `@Conditional(FeatureEnabledCondition.class)`. Spring finds the condition when analyzing classes or methods annotated with `@FeatureEnabled`.

**Q4.** Why can `GreetingConfiguration` class metadata still be printed even when `demo.module.enabled=false`?

**Answer:** `AnnotationMetadata.introspect(GreetingConfiguration.class)` reads annotations from the Java class on the classpath. Having a condition prevent Spring from registering a bean does not remove the class or annotations from bytecode.

**Q5.** If `getAnnotationAttributes(...)` returns null, what should you do?

**Answer:** Define the condition's contract. If the annotation is required, return `false` or report a clear configuration error; do not cast `null` and treat it as a Map.

**Q6.** How does `getAnnotations()` differ from reading annotations directly with Java reflection?

**Answer:** It uses Spring's `MergedAnnotations` system, handling many aspects of composed annotations, meta-annotations, and aliases. It is not merely a mirror of the `Class#getAnnotation` API.

**Q7.** Does a custom condition returning `true` guarantee the bean will definitely be created?

**Answer:** No. The component may have other conditions, the bean definition may be created while a lazy bean remains uninitialized, or bean creation may fail later.

**Q8.** Is `AutoConfigurationMetadata` a parent interface of `AnnotatedTypeMetadata`?

**Answer:** No. They are two separate APIs serving different jobs and phases.

## 15. References

- Spring Framework 6.1, `AnnotatedTypeMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html
- Spring Framework 6.1, `AnnotationMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotationMetadata.html
- Spring Framework 6.1, `MethodMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/MethodMetadata.html
- Spring Framework 6.1, `Condition` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html
- Spring Framework 6.1, `@Conditional` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html
- Spring Boot 3.3.13, `SpringBootCondition` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- Spring Boot, Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
