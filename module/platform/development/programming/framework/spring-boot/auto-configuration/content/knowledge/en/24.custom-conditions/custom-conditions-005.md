# Custom Condition Annotations and Reading Annotation Parameters

## Learning Objectives

Spring Boot provides many condition annotations such as \`@ConditionalOnClass\`, \`@ConditionalOnProperty\`, \`@ConditionalOnBean\`, and \`@ConditionalOnMissingBean\`. When a library has specialized activation rules that built-in annotations cannot express clearly, you can create a **custom condition annotation** using \`@Conditional\` and a class implementing \`Condition\`.

An important point is that a condition does not only need to know whether it matches. It must also read parameters passed by the annotation author, such as a list of allowed regions, a feature name, a mode, or classes to inspect. Spring provides \`AnnotatedTypeMetadata\` so conditions can read annotations on a class or method, including annotations created by composing other annotations.

This lesson builds a parameterized \`@ConditionalOnRegion\` annotation, reads those values via metadata, supports composed annotations with \`@AliasFor\`, and verifies behavior using \`ApplicationContextRunner\`.

After this lesson, you will be able to:

- Distinguish \`@Conditional\`, \`Condition\`, \`ConditionContext\`, and \`AnnotatedTypeMetadata\`.
- Create a parameterized condition annotation and apply it to a class or \`@Bean\` method.
- Properly read annotation parameters using \`getAnnotationAttributes(...)\`.
- Understand merged annotations and how \`@AliasFor\` forwards attributes from composed annotations.
- Choose appropriate ways to read class-valued attributes and repeatable annotations.
- Write safe conditions that do not instantiate beans or produce side effects during evaluation.
- Test match, no-match, missing property, and composed annotation cases.

## 1. When Do You Need a Custom Condition Annotation?

Use built-in annotations when the rule can be expressed directly:

~~~java
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true")
@ConditionalOnBean(MeterRegistry.class)
~~~

If multiple modules repeat the same business rule—for instance, enabling an adapter only when the application's region is in a list supported by the library—a dedicated annotation makes the contract much easier to read:

~~~java
@ConditionalOnRegion({"eu", "apac"})
class RegionalAcmeAutoConfiguration {
}
~~~

This annotation expresses intent directly. Classes using it do not need to know the property name, string normalization rules, or how regions are compared. Those details are centralized in a single condition.

Other examples that might call for a custom annotation:

- Enabling an integration only when the tenant belongs to a supported group.
- Selecting an adapter by cloud provider or deployment mode.
- Enabling a bean when the application uses a protocol from an allowed list.
- Checking whether a resource has a specific version or format.
- Combining multiple annotation attributes to express a policy.

Do not write a custom condition just to wrap a built-in annotation without improving clarity. A specialized annotation adds value when it establishes a stable, reusable contract that can be tested independently.

## 2. Basic Mechanism: @Conditional Calls Condition.matches

Spring defines the \`@Conditional\` annotation to attach one or more condition classes to a component eligible for registration:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface Conditional {
    Class<? extends Condition>[] value();
}
~~~

The snippet above shows an abridged structure of the annotation in Spring Framework. In applications, we usually do not declare \`@Conditional\` directly every time; instead, we place it on a custom condition annotation.

A condition implements the interface:

~~~java
public interface Condition {
    boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata);
}
~~~

Two key parameters:

| Parameter | What information does it provide? | Usage examples |
| --- | --- | --- |
| \`ConditionContext\` | Environment, registry, bean factory, resource loader, and class loader | Reading properties, inspecting bean definitions, checking classes/resources |
| \`AnnotatedTypeMetadata\` | Metadata of the class or method currently being evaluated | Reading annotation parameters on a configuration class or \`@Bean\` method |

\`matches\` returns \`true\` when the component is allowed to register, and \`false\` when the condition vetoes registration.

**Metadata represents the element currently being inspected.** If the annotation is placed on a \`@Configuration\` class, metadata describes that class. If placed on a \`@Bean\` method, metadata describes that method. Therefore, the same condition can be reused at both class and bean-method levels.

## 3. ConditionContext: Reading the Environment and Container Infrastructure

\`ConditionContext\` provides five sources of information:

| Method | Content | Notes |
| --- | --- | --- |
| \`getEnvironment()\` | Current Environment | Reads properties and active profiles |
| \`getRegistry()\` | BeanDefinitionRegistry | Checks/registers at the bean definition level if truly needed |
| \`getBeanFactory()\` | ConfigurableListableBeanFactory | May be \`null\` if no suitable bean factory is available |
| \`getResourceLoader()\` | ResourceLoader | Locates resources |
| \`getClassLoader()\` | ClassLoader | Finds or loads classes; may be \`null\` if no system class loader exists |

Example reading a property:

~~~java
String region = context.getEnvironment().getProperty("acme.region");
~~~

Example checking a resource:

~~~java
boolean found = context.getResourceLoader()
        .getResource("classpath:acme/schema.json")
        .exists();
~~~

Example obtaining the class loader:

~~~java
ClassLoader classLoader = context.getClassLoader();
~~~

If you need to check beans, prefer built-in annotations such as \`@ConditionalOnBean\` or \`@ConditionalOnMissingBean\`. If complex logic genuinely requires reading the registry, work with bean definitions and do not retrieve bean instances.

### 3.1. What a Condition Should Not Do

Conditions are evaluated during component registration processing. Spring stipulates that conditions must follow restrictions similar to \`BeanFactoryPostProcessor\` and **must not interact with bean instances**.

Avoid:

- Calling \`context.getBean(...)\` to create or retrieve beans inside a condition.
- Calling databases, HTTP endpoints, or external services.
- Writing files, creating resources, or mutating application state.
- Relying on the current time or continuously changing data to decide bean registration.
- Storing mutable state in the condition instance across multiple evaluations.

Keep conditions lightweight and deterministic from metadata, Environment, classpath, resources, and bean definitions. This keeps results stable and avoids bean initialization cycles.

## 4. AnnotatedTypeMetadata: Reading Annotation Parameters

\`AnnotatedTypeMetadata\` is an abstraction for reading annotations on a class or method without obtaining an instance of that element.

Commonly used methods:

| Method | Result |
| --- | --- |
| \`isAnnotated(annotationName)\` | Checks whether a direct annotation or meta-annotation is present |
| \`getAnnotationAttributes(annotationName)\` | Gets a Map of attribute name → value, supporting merged annotations |
| \`getAnnotationAttributes(annotationName, classValuesAsString)\` | Gets attributes and can convert class values into class names |
| \`getAllAnnotationAttributes(annotationName)\` | Gets attributes of all matching occurrences as a MultiValueMap |
| \`getAnnotations()\` | Accesses MergedAnnotations for advanced processing |

Example:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnRegion.class.getName());

String[] regions = (String[]) attributes.get("value");
boolean matchIfMissing =
        (Boolean) attributes.get("matchIfMissing");
~~~

Values in the Map reflect the declared types of the annotation attributes:

- \`String\` → \`String\`.
- \`boolean\` → \`Boolean\`.
- \`int\` → \`Integer\`.
- \`String[]\` → \`String[]\`.
- \`Class<?>\` → Class value, unless the mode returning class names is selected.
- Enum → corresponding enum instance.

Do not cast blindly. Match each extracted value against the declared attribute type on the annotation and handle the case where the metadata lacks the annotation.

### 4.1. Checking Before Reading

A safe pattern:

~~~java
String annotationName = ConditionalOnRegion.class.getName();

if (!metadata.isAnnotated(annotationName)) {
    return false;
}

Map<String, Object> attributes =
        metadata.getAnnotationAttributes(annotationName);

if (attributes == null) {
    return false;
}
~~~

In a condition triggered by that annotation itself, missing attributes usually point to an unexpected annotation structure. Returning \`false\` avoids \`NullPointerException\`, though in a large library such an annotation configuration mistake may be worth catching early in tests or with a clearer message.

### 4.2. Why Does getAnnotationAttributes Support Composed Annotations?

Spring uses a merged annotation model. If another annotation is meta-annotated with \`@ConditionalOnRegion\`, metadata can locate the root annotation in the hierarchy and return merged attributes.

In particular, \`@AliasFor\` can map an attribute of the composed annotation to an attribute of the meta-annotation. This allows a composed annotation to present a concise API while the condition still reads a unified set of attributes.

### 4.3. getAllAnnotationAttributes Has One Important Difference

\`getAllAnnotationAttributes\` returns attributes of all annotations of the same type found, which is often helpful for repeatable annotations. However, this method **does not apply attribute overrides from composed annotations**.

When you need a single merged attribute set supporting \`@AliasFor\`, prefer \`getAnnotationAttributes\`. For repeatable annotations in Spring Framework 6.1, you can use \`getMergedRepeatableAnnotationAttributes(...)\` to receive each merged attribute set across the annotation hierarchy.

## 5. Creating a Parameterized Condition Annotation

We build the contract:

~~~java
@ConditionalOnRegion({"eu", "apac"})
class RegionalFeatureConfiguration {
}
~~~

Meaning:

- Property \`acme.region\` has value \`eu\` or \`apac\`: condition matches.
- Property is missing or blank: condition does not match by default.
- Property has another value: condition does not match.
- Can enable \`matchIfMissing=true\` if a missing property should be allowed.

**File:** \`ConditionalOnRegion.java\`

~~~java
package example.region;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnRegionCondition.class)
public @interface ConditionalOnRegion {

    String[] value() default {};

    boolean matchIfMissing() default false;
}
~~~

Key points to note:

1. \`@Target(TYPE, METHOD, ANNOTATION_TYPE)\` allows using the annotation on configuration classes, bean methods, and as a meta-annotation on other annotations.
2. \`@Retention(RUNTIME)\` lets Spring read annotation metadata when processing configuration.
3. \`@Documented\` ensures the annotation appears in the Javadoc of annotated elements.
4. \`@Conditional(OnRegionCondition.class)\` connects the annotation to its implementation.
5. \`value()\` is the list of allowed values; shorthand syntax \`@ConditionalOnRegion({"eu","apac"})\` targets the attribute named \`value\`.
6. \`matchIfMissing\` declares the policy when the property is absent or blank.

Using the attribute name \`value\` is not mandatory. If you use \`regions()\`, callers will write \`@ConditionalOnRegion(regions = {"eu", "apac"})\`. Choose a clear name and keep it stable because public annotations are part of the library's API.

## 6. Implementing Condition and Reading Attributes

**File:** \`OnRegionCondition.java\`

~~~java
package example.region;

import java.util.Arrays;
import java.util.Locale;
import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class OnRegionCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String annotationName = ConditionalOnRegion.class.getName();

        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(annotationName);

        if (attributes == null) {
            return ConditionOutcome.noMatch(
                    "ConditionalOnRegion attributes were not found");
        }

        String[] allowedRegions = (String[]) attributes.get("value");
        boolean matchIfMissing =
                (Boolean) attributes.get("matchIfMissing");

        String configuredRegion =
                context.getEnvironment().getProperty("acme.region");

        if (configuredRegion == null || configuredRegion.isBlank()) {
            if (matchIfMissing) {
                return ConditionOutcome.match(
                        "acme.region is missing and matchIfMissing is true");
            }
            return ConditionOutcome.noMatch(
                    "acme.region is missing or blank");
        }

        String actualRegion = configuredRegion.trim()
                .toLowerCase(Locale.ROOT);

        boolean matches = Arrays.stream(allowedRegions)
                .filter(region -> region != null && !region.isBlank())
                .map(region -> region.trim().toLowerCase(Locale.ROOT))
                .anyMatch(actualRegion::equals);

        if (matches) {
            return ConditionOutcome.match(
                    "acme.region '" + configuredRegion
                            + "' is in the allowed region list");
        }

        return ConditionOutcome.noMatch(
                "acme.region '" + configuredRegion
                        + "' is not in " + Arrays.toString(allowedRegions));
    }
}
~~~

This is an implementation for Spring Boot 3.3 and Java 17+. Design decisions made:

- Uses \`getAnnotationAttributes\` to read merged attributes.
- Uses \`Environment\` to read \`acme.region\`.
- Normalizes casing with \`Locale.ROOT\` so results do not depend on the machine's locale.
- Treats null or whitespace-only properties as missing.
- Allows missing properties only when the annotation sets \`matchIfMissing=true\`.
- Returns match/no-match messages with reasons.

### 6.1. Why Extend SpringBootCondition?

Spring Framework only requires a condition to implement \`Condition.matches(...)\`. Spring Boot provides \`SpringBootCondition\` as a base class for conditions used in the Boot ecosystem.

When extending \`SpringBootCondition\`, you implement \`getMatchOutcome(...)\` and return \`ConditionOutcome.match(...)\` or \`ConditionOutcome.noMatch(...)\`. Boot uses this outcome to record and log evaluation reasons, making the Condition Evaluation Report easier to diagnose.

If you want to write a general-purpose condition for Spring Framework without depending on Boot, implement \`Condition\` directly and return a boolean. In that case, design your own logging/diagnostics if the application needs them. For an auto-configuration library built specifically for Boot, \`SpringBootCondition\` is usually more convenient.

### 6.2. What Happens When the Condition Is Placed on a Method?

The same condition class can receive metadata from either a class or a method:

~~~java
@AutoConfiguration
@ConditionalOnRegion({"eu", "apac"})
class RegionalAutoConfiguration {

    @Bean
    RegionalClient regionalClient() {
        return new RegionalClient();
    }

    @Bean
    @ConditionalOnRegion(
            value = {"us"},
            matchIfMissing = true)
    UsFallbackClient usFallbackClient() {
        return new UsFallbackClient();
    }
}
~~~

- The annotation on the class decides whether the entire configuration class is processed.
- The annotation on the bean method decides whether that bean method is registered.
- If the class-level condition does not match, bean methods inside that class are not registered through that branch.
- If the class-level condition matches, each method-level condition is still evaluated independently.

In real code, place the condition at the smallest scope matching the policy. If the entire group of beans is valid only in EU/APAC, place it on the class. If only a single bean needs a condition, place it on the method.

## 7. Composed Annotations and @AliasFor

A library can create a shorter annotation for a commonly used set of regions:

~~~java
@ConditionalOnRegions({"eu", "apac"})
class EuropeAndAsiaConfiguration {
}
~~~

**File:** \`ConditionalOnRegions.java\`

~~~java
package example.region;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;

@Target({
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnRegion
public @interface ConditionalOnRegions {

    @AliasFor(
            annotation = ConditionalOnRegion.class,
            attribute = "value")
    String[] value() default {};

    @AliasFor(
            annotation = ConditionalOnRegion.class,
            attribute = "matchIfMissing")
    boolean matchIfMissing() default false;
}
~~~

Here:

- \`@ConditionalOnRegions\` is meta-annotated with \`@ConditionalOnRegion\`.
- The composed annotation's \`value()\` aliases \`value()\` on the meta-annotation.
- \`matchIfMissing()\` aliases the attribute of the same name.
- When the condition calls \`metadata.getAnnotationAttributes(ConditionalOnRegion.class.getName())\`, Spring returns merged values, including values overridden via the composed annotation.

**Default values must be compatible.** The default value of an aliased attribute should match the default of the meta-attribute. The example above uses an empty array and \`false\` at both layers.

### 7.1. When Should You Use @AliasFor?

Use \`@AliasFor\` when you want users of a composed annotation to customize attributes of the meta-annotation. It is useful for:

- Shortening a common configuration pattern.
- Renaming attributes to better match domain terminology.
- Allowing a high-level annotation to control one or more condition parameters.
- Combining multiple foundational annotations into one public annotation.

If the composed annotation always has a fixed policy, no alias is needed. You can simply set fixed values on the meta-annotation without exposing extra attributes.

### 7.2. Reading the Direct Annotation or the Meta-Annotation?

If the condition always looks up \`ConditionalOnRegion\`, read that exact name:

~~~java
metadata.getAnnotationAttributes(
        ConditionalOnRegion.class.getName());
~~~

Do not read \`ConditionalOnRegions\` in the condition if the goal is to support both the original annotation and composed annotations. Using the meta-annotation name allows one implementation to handle many usages while merged metadata consolidates aliases.

## 8. Reading Class-Valued Attributes Without Early Class Loading

Another annotation might accept class types:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(OnSupportedTypesCondition.class)
public @interface ConditionalOnSupportedTypes {
    Class<?>[] value();
}
~~~

When reading attributes, there are two options:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnSupportedTypes.class.getName());
Class<?>[] types = (Class<?>[]) attributes.get("value");
~~~

This approach returns class references. If the classes may belong to optional dependencies and should not be resolved too early, use the overload:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnSupportedTypes.class.getName(),
                true);

String[] classNames = (String[]) attributes.get("value");
~~~

The \`classValuesAsString=true\` parameter tells Spring to convert class-valued attributes into string class names instead of returning Class objects. This is helpful when the condition only needs to check the class loader or pass class names to another API.

For optional dependencies, do not let optional classes appear in signatures of configuration classes or methods that the JVM might have to resolve before the condition can guard them. Use class names in metadata and isolate configuration classes with classpath conditions when necessary.

## 9. Repeatable Annotations and Multiple Declarations

If an element can receive multiple annotations of the same kind, Java allows declaring a repeatable annotation:

~~~java
@Repeatable(ConditionalOnRegions.List.class)
public @interface ConditionalOnRegions {
    String value();

    @Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @interface List {
        ConditionalOnRegions[] value();
    }
}
~~~

Example:

~~~java
@ConditionalOnRegions("eu")
@ConditionalOnRegions("apac")
class RegionalConfiguration {
}
~~~

When handling repeatable annotations, do not assume \`getAnnotationAttributes\` always returns every occurrence. That method is intended for retrieving a single merged attribute set of the discovered annotation.

Spring Framework 6.1 adds \`getMergedRepeatableAnnotationAttributes(...)\` to retrieve the attribute sets of repeatable annotations across the hierarchy, with \`@AliasFor\` support. You must specify the corresponding annotation type and container type.

If multiple annotations imply logical combination (AND/OR), document the semantics clearly:
- AND: every region/policy must hold simultaneously.
- OR: only one region/policy needs to hold.
- A single annotation accepting a list of values is often easier to understand if the logic is "one of the allowed regions".

Do not use repeatable annotations if readers cannot easily predict how multiple declarations are combined.

## 10. Testing with ApplicationContextRunner

A proper condition must be tested where Spring actually reads annotation metadata and registers beans. You can use \`ApplicationContextRunner\` to create a small context for each case.

Minimum cases:

| Case | Property | Annotation | Result |
| --- | --- | --- | --- |
| Valid region | \`eu\` | \`{"eu","apac"}\` | Bean is registered |
| Different region | \`us\` | \`{"eu","apac"}\` | Bean is not registered |
| Missing property | None | \`matchIfMissing=false\` | Not registered |
| Missing property | None | \`matchIfMissing=true\` | Registered |
| Composed annotation | \`apac\` | \`@ConditionalOnRegions({"eu","apac"})\` | Registered |
| Method-level condition | \`eu\` | Two beans with different policies | Only matching bean is registered |

**File:** \`src/test/java/example/region/OnRegionConditionTest.java\`

~~~java
package example.region;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class OnRegionConditionTest {

    @Test
    void classLevelConditionMatchesAllowedRegion() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ClassRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=APAC")
                .run(context ->
                        assertThat(context).hasSingleBean(RegionFeature.class));
    }

    @Test
    void classLevelConditionRejectsUnsupportedRegion() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ClassRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=us")
                .run(context ->
                        assertThat(context).doesNotHaveBean(RegionFeature.class));
    }

    @Test
    void methodLevelConditionsAreEvaluatedIndependently() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MethodRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=eu")
                .run(context -> {
                    assertThat(context).hasSingleBean(EuropeFeature.class);
                    assertThat(context).doesNotHaveBean(UsFallbackFeature.class);
                });
    }

    @Test
    void matchIfMissingControlsTheMissingPropertyCase() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MethodRegionAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(EuropeFeature.class);
                    assertThat(context).hasSingleBean(UsFallbackFeature.class);
                });
    }

    @Test
    void composedAnnotationAttributesAreMerged() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ComposedRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=apac")
                .run(context ->
                        assertThat(context).hasSingleBean(ComposedRegionFeature.class));
    }

    static class RegionFeature {
    }

    static class EuropeFeature {
    }

    static class UsFallbackFeature {
    }

    static class ComposedRegionFeature {
    }

    @AutoConfiguration
    @ConditionalOnRegion({"eu", "apac"})
    static class ClassRegionAutoConfiguration {

        @Bean
        RegionFeature regionFeature() {
            return new RegionFeature();
        }
    }

    @AutoConfiguration
    static class MethodRegionAutoConfiguration {

        @Bean
        @ConditionalOnRegion({"eu", "apac"})
        EuropeFeature europeFeature() {
            return new EuropeFeature();
        }

        @Bean
        @ConditionalOnRegion(
                value = {"us"},
                matchIfMissing = true)
        UsFallbackFeature usFallbackFeature() {
            return new UsFallbackFeature();
        }
    }

    @AutoConfiguration
    @ConditionalOnRegions({"eu", "apac"})
    static class ComposedRegionAutoConfiguration {

        @Bean
        ComposedRegionFeature composedRegionFeature() {
            return new ComposedRegionFeature();
        }
    }
}
~~~

### 10.1. Explanation of Each Test

- \`classLevelConditionMatchesAllowedRegion\`: annotation on the class reads the region list; value \`APAC\` is normalized and matches \`apac\`.
- \`classLevelConditionRejectsUnsupportedRegion\`: property \`us\` is not in the list, so the configuration class is skipped.
- \`methodLevelConditionsAreEvaluatedIndependently\`: the EU/APAC method is registered; the US method is not registered.
- \`matchIfMissingControlsTheMissingPropertyCase\`: missing property causes the EU/APAC method not to match, while the US method with \`matchIfMissing=true\` is registered.
- \`composedAnnotationAttributesAreMerged\`: the condition reads \`@ConditionalOnRegion\` attributes via the composed annotation \`@ConditionalOnRegions\`; aliased values are merged properly.

The tests only inspect bean registration. They do not open network connections or call external services.

### 10.2. Dependencies and Run Commands

Requires Java 17+, Spring Boot 3.3.x, JUnit 5, and AssertJ. In Gradle Groovy DSL, assuming versions are managed by the Spring Boot plugin or BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run tests:

~~~bash
# Linux/macOS
./gradlew test --tests "example.region.OnRegionConditionTest"

# Windows
gradlew.bat test --tests "example.region.OnRegionConditionTest"
~~~

**Expected result:** five PASS tests. Tests use assertions and have no \`System.out.println\`, so there is no fixed application stdout content. Gradle/JUnit will display pass/fail counts according to the project's logging configuration.

This is example code targeting Spring Boot 3.3 and Java 17+; run it in an actual module to verify dependency versions, packages, and project build configuration. The code was reviewed against the cited APIs and has not been executed inside the current module.

## 11. Diagnosing Unmatched Conditions

If a bean does not appear, check in order:

1. Is the annotation attached to the right class or method?
2. Does the annotation have \`@Retention(RUNTIME)\`?
3. Does the annotation have \`@Conditional(OnRegionCondition.class)\` or a valid meta-annotation chain?
4. Does \`metadata.getAnnotationAttributes(...)\` return a Map?
5. Do the attributes have the exact expected names and types?
6. Is the property set in Environment at the time the condition runs?
7. Does the value have unexpected whitespace, casing, or formatting?
8. If using a composed annotation, does \`@AliasFor\` have the right target attribute, right type, and compatible default?
9. Is the condition placed at class-level or method-level? Did a class-level condition already exclude the entire configuration before the method was considered?
10. Was the auto-configuration included in the context and is its processing order appropriate?

### 11.1. Enabling the Condition Evaluation Report

For a Spring Boot application, run:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot can display the Condition Evaluation Report. If the condition extends \`SpringBootCondition\` and returns a \`ConditionOutcome\` with a message, the log will explain why the condition matched or did not match.

A good message should indicate:
- Which property was read.
- What the actual value was.
- What the expected values were.
- Whether a missing property is accepted.

Avoid generic messages like "condition failed". A specific explanation helps starter users resolve issues themselves without debugging the framework.

## 12. ConfigurationCondition: When You Need to Choose the Evaluation Phase

A basic \`Condition\` is evaluated right before the relevant bean definition is registered. If your logic needs to explicitly control **the configuration parsing phase** versus **the bean registration phase**, Spring provides \`ConfigurationCondition\`.

Two phases:

| Phase | Timing |
| --- | --- |
| \`PARSE_CONFIGURATION\` | While a \`@Configuration\` class is being parsed; if it does not match, the class is not added |
| \`REGISTER_BEAN\` | When registering a regular bean; all configuration classes have already been parsed |

A condition implementing \`ConfigurationCondition\` must additionally provide:

~~~java
@Override
public ConfigurationPhase getConfigurationPhase() {
    return ConfigurationPhase.REGISTER_BEAN;
}
~~~

Do not pick a phase arbitrarily. If the condition only reads properties or annotation parameters, a regular \`Condition\` is usually enough. If the condition depends on bean definitions registered by configuration classes, review the phase and auto-configuration ordering. For common cases, prefer built-in annotations such as \`@ConditionalOnBean\` instead of writing custom registry logic.

## 13. Common Mistakes When Writing Custom Condition Annotations

1. **Forgetting \`@Retention(RUNTIME)\`.** Runtime metadata cannot read the annotation as expected.
2. **Omitting \`ElementType.ANNOTATION_TYPE\` when the annotation needs to be used as a meta-annotation.** Composed annotations will not compile or cannot be applied as designed.
3. **Reading the wrong annotation name.** The condition looks up a different annotation than the one applied; use the full name from \`YourAnnotation.class.getName()\`.
4. **Casting attribute values incorrectly.** Casting \`String[]\` to \`String\` or reading a Boolean as a string; verify against the declared types.
5. **Not handling missing properties.** The condition accidentally enables/disables the feature; explicitly define \`matchIfMissing\`.
6. **Comparing strings without normalization.** \`EU\`, \`eu\`, and \` eu \` may produce different results; document normalization rules and apply them consistently.
7. **Using \`getAllAnnotationAttributes\` when alias merging is needed.** That method does not apply overrides from composed annotations; use \`getAnnotationAttributes\` for merged attributes.
8. **Using reflection to obtain an annotation instance when only metadata is needed.** That can force class loading or bypass metadata benefits; prefer \`AnnotatedTypeMetadata\`.
9. **Calling \`getBean\` inside a condition.** Can initialize beans too early and create dependency cycles; inspect metadata/bean definitions instead.
10. **Calling external services inside a condition.** Startup depends on the network, results are unstable, and testing becomes difficult; move runtime checks to an appropriate component.
11. **Placing the condition too broadly.** A method-level policy may accidentally be placed at class-level and exclude the whole configuration.
12. **Not testing composed annotations.** Direct usage works while aliases fail to merge; add tests for composed annotations.
13. **Not testing missing properties.** Annotation defaults can change behavior; write dedicated tests for \`matchIfMissing\`.
14. **Making a condition mutable or keeping per-context caches.** A condition instance may be reused across multiple evaluations; keep the implementation stateless.
15. **Not providing a no-match reason.** Users do not know which property/annotation caused the bean to be skipped; use \`SpringBootCondition\` and \`ConditionOutcome\` when writing Boot integrations.

## 14. Custom Condition Review Checklist

- [ ] Annotation has the right target (TYPE, METHOD, ANNOTATION_TYPE if needed).
- [ ] Retention is RUNTIME.
- [ ] Annotation is meta-annotated with \`@Conditional\`.
- [ ] Attribute names and types have clear meanings.
- [ ] Default values and missing-property behavior are documented.
- [ ] Condition reads attributes via \`AnnotatedTypeMetadata\`.
- [ ] Merged attributes are used if composed annotations exist.
- [ ] \`@AliasFor\` has valid targets, types, and compatible defaults.
- [ ] Condition reads only necessary Environment/metadata/registry state.
- [ ] No bean instances fetched and no I/O performed in the condition.
- [ ] Tests cover class-level, method-level, match/no-match, and missing property.
- [ ] Composed annotation tests exist if the API supports aliases.
- [ ] Diagnostic messages exist if used in Spring Boot auto-configuration.

## 15. Self-Check Questions

**Question 1.** In \`Condition.matches(context, metadata)\`, what does metadata describe?

**Answer:** Metadata of the class or method currently being evaluated. That is why a condition can be used on both configuration classes and \`@Bean\` methods.

**Question 2.** How do you retrieve the \`value\` parameter of \`@ConditionalOnRegion\`?

**Answer:** Call \`metadata.getAnnotationAttributes(ConditionalOnRegion.class.getName())\`, then read \`attributes.get("value")\` and cast according to the declared \`String[]\` type.

**Question 3.** Why use \`getAnnotationAttributes\` when \`@AliasFor\` is present?

**Answer:** This method returns merged annotation attributes and supports aliases across the annotation hierarchy. \`getAllAnnotationAttributes\` does not apply overrides from composed annotations.

**Question 4.** Should a condition call \`context.getBean(MyService.class)\` to see if the service is active?

**Answer:** No. Conditions should not interact with bean instances. Inspect bean definitions or use \`@ConditionalOnBean\` when you only need to check bean presence.

**Question 5.** When a property does not exist, how should the condition handle it?

**Answer:** According to the annotation's contract. For example, \`matchIfMissing=false\` does not match; \`true\` matches. Both cases must be tested.

**Question 6.** When should \`SpringBootCondition\` be used instead of implementing \`Condition\` directly?

**Answer:** When the condition belongs to Spring Boot auto-configuration and you want \`ConditionOutcome\`, logged match/no-match reasons, and diagnostic support in the Condition Evaluation Report.

## 16. Takeaways

A custom condition has three cohesive parts:

- **Annotation** defines the contract and parameters declared by users.
- **AnnotatedTypeMetadata** supplies annotation values read and merged by Spring, including meta-annotations and \`@AliasFor\`.
- **ConditionContext** supplies the Environment and container infrastructure to decide whether a bean should be registered.

Keep conditions stateless, fast, and free of side effects. Use \`getAnnotationAttributes\` to read a single merged attribute set; use the class-values-as-string overload when you need to avoid resolving class-valued attributes; use appropriate repeatable APIs when an annotation can appear multiple times. For Spring Boot auto-configuration, extend \`SpringBootCondition\` to provide match/no-match reasons and aid user diagnostics.

### Official Spring Framework and Spring Boot Documentation

- [Spring Framework 6.1 — Condition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html)
- [Spring Framework 6.1 — ConditionContext Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html)
- [Spring Framework 6.1 — AnnotatedTypeMetadata Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html)
- [Spring Framework 6.1 — ConfigurationCondition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html)
- [Spring Boot 3.3 — SpringBootCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html)
- [Spring Boot 3.3 — ConditionOutcome Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html)
