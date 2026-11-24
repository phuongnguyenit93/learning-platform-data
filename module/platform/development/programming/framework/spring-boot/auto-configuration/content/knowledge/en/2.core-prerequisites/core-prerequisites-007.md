# Composed Annotations, Annotation Metadata, and Class-Name Declarations in Spring Boot Auto-configuration

When writing or reading Spring Boot **auto-configuration**, three ideas frequently appear together:

1. **Composed annotations**: an annotation that uses other annotations as *meta-annotations*, creating a new label with convenient and consistent semantics.
2. **Annotation metadata**: information about annotations, attributes, classes, and methods that Spring reads to discover configuration or evaluate conditions. Spring can read metadata from bytecode without instantiating beans or loading every referenced class.
3. **Class-name declarations**: using the fully qualified class name as a `String` in appropriate places, especially when the class or dependency is *optional* and may be absent from the runtime classpath.

These are **mechanisms that support discovering and selecting configurations**, not three different ways to directly create an object. Spring Boot uses them to locate auto-configuration candidates, process annotations/conditions, and register beans only when conditions match.

## 1. Direct annotations, meta-annotations, and composed annotations

A Java annotation can be placed directly on a class:

```java
@Component
public class InventoryService {
}
```

`@Component` is a **direct** annotation on `InventoryService`. However, Spring's `@Service` can be modeled as:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface Service {
    // Omit attributes to focus on the meta-annotation relationship.
}
```

Here, `@Component` is placed **on the `@Service` annotation definition**; it is a *meta-annotation*. Because Spring understands this annotation chain, `@Service` is a valid stereotype for component scanning to detect.

A **composed annotation** typically combines one or more meta-annotations to create a concise, domain-meaningful annotation API. For example, `@RestController` combines the behavior of `@Controller` and `@ResponseBody`; `@SpringBootApplication` composes `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`; `@AutoConfiguration` carries Spring configuration semantics and specific declarations for the auto-configuration mechanism.

Do not confuse the three conceptual layers:

| Term | Question it answers | Example |
| --- | --- | --- |
| Direct annotation | Which annotation is placed on the class/method? | `@Service` on `OrderService` |
| Meta-annotation | Which annotations is the used annotation built from? | `@Component` on the `@Service` definition |
| Composed annotation | What new annotation API combines/restricts/customizes meanings? | `@SpringBootApplication`, custom annotation `@FeatureComponent` |

**Plain Java caveat:** annotation A being meta-annotated with B does not mean every Java reflection API will return B as a direct annotation on a class using A. `Class.getAnnotation(B.class)` and Spring's annotation/meta-annotation lookup algorithm behave differently. Spring provides the *merged annotations* model to query this hierarchy.

### 1.1. Java meta-annotations that define an annotation's contract

When defining your own annotation, you should understand at least:

- `@Target`: valid locations where the annotation can be placed, such as `ElementType.TYPE` for classes/interfaces/annotation types or `ElementType.METHOD` for methods.
- `@Retention(RetentionPolicy.RUNTIME)`: lets reflection APIs read the annotation at runtime. Spring configuration annotations generally declare appropriate retention.
- `@Documented`: includes the annotation in Javadoc of annotated elements.
- `@Inherited`: if present, Java supports annotation inheritance on **classes** in certain reflection calls; it does not extend automatically to interfaces or overridden methods. Spring also has its own annotation search strategies, so `@Inherited` cannot substitute for all merging mechanisms.

A composed annotation should **have a clearly defined purpose**. Do not bundle dozens of unrelated annotations into a custom label just to save lines; that obscures component behavior when reading code.

## 2. Annotation attributes and `@AliasFor`

In composed annotations, the issue is not just "placing one annotation on another"; there is also **forwarding attribute values**. If you want a custom annotation to let users set a bean name like `@Component("name")`, declare an explicit alias.

The example definition below is complete Java in `FeatureComponent.java`:

```java
package com.example.app;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface FeatureComponent {

    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

Application usage:

```java
@FeatureComponent("timeReporter")
public class TimeReporter {
    // ...
}
```

**What happens:**

1. `@FeatureComponent` is directly on `TimeReporter`.
2. `@Component` sits at the meta-annotation level and lets Spring recognize this class as a component.
3. `@AliasFor(annotation = Component.class, attribute = "value")` declares that `FeatureComponent.value` aliases `Component.value` in the merged annotations model.
4. When the class is within component scanning scope, Spring can use `"timeReporter"` as the bean name.

`@AliasFor` can also express aliases **between two attributes in the same annotation** or **explicit aliases to another meta-annotation**, though aliases must follow rules regarding compatible types, defaults, and equivalence. You cannot rename an attribute arbitrarily and expect Spring to infer it as an alias. Especially with Spring Framework 6.1+, custom stereotypes should declare explicit aliases for bean-naming attributes.

Distinguish:

- `@AliasFor` governs **how Spring interprets and merges annotation attributes**.
- Dependency injection governs **supplying beans into constructors/methods/fields**.
- Property binding from `application.properties` governs **assigning configuration data**, not aliasing Java annotation attributes.

## 3. Annotation metadata: reading configuration from metadata instead of creating beans

In Spring Framework, `AnnotationMetadata` represents annotation information of a class; `MethodMetadata` represents information about a method. The `MergedAnnotations` API lets you inspect direct annotations, meta-level annotations, and merged attribute values, taking `@AliasFor` into account.

Common queries:

| API | Meaning |
| --- | --- |
| `metadata.getClassName()` | Fully qualified name of the described class |
| `metadata.getAnnotationTypes()` | Direct annotation types on the class |
| `metadata.hasAnnotation(fqcn)` | Does the class carry that annotation **directly**? |
| `metadata.hasMetaAnnotation(fqcn)` | Does the class carry an annotation whose meta-annotation hierarchy includes this type? |
| `metadata.isAnnotated(fqcn)` | Is the annotation present **directly or as a meta-annotation** by name? |
| `metadata.getAnnotations()` | Access the `MergedAnnotations` model, including meta-annotation checks and merged attributes |

`fqcn` stands for *fully qualified class name*, e.g. `org.springframework.boot.autoconfigure.condition.ConditionalOnClass`.

There are two distinct approaches to keep separate **even though both return metadata**:

- `AnnotationMetadata.introspect(SomeClass.class)`: starts from an already-loaded `Class` and uses reflection. Suitable for illustrative/test code or when you already have the class.
- `MetadataReaderFactory`/`MetadataReader`: reads metadata **from the class resource/bytecode** via ASM, generally avoiding loading the scanned class. This mechanism is crucial when inspecting classpaths with optional dependencies.

Therefore, "Spring reads annotation metadata without loading classes" must be understood accurately: **many scanning/metadata-parsing paths can do so**, not every way of obtaining `AnnotationMetadata` has this property. When calling `introspect(SomeClass.class)`, you have already passed in a `Class`.

### 3.1. Direct illustration with metadata

Suppose `ClockAutoConfiguration` is annotated as in the full example in section 5:

```java
AnnotationMetadata metadata =
        AnnotationMetadata.introspect(ClockAutoConfiguration.class);

boolean direct = metadata.hasAnnotation(ClockAvailable.class.getName());
boolean meta = metadata.hasMetaAnnotation(ConditionalOnClass.class.getName());
boolean annotated = metadata.isAnnotated(ConditionalOnClass.class.getName());
```

This is a **snippet inside the Spring application in section 5**, not a standalone runnable file. Expected results:

- `direct == true` because `@ClockAvailable` is placed directly on the class.
- `meta == true` because `@ClockAvailable` carries the `@ConditionalOnClass` meta-annotation.
- `annotated == true` because `isAnnotated` searches both direct and meta-annotations.

This result describes **declared metadata**; it does not prove the `@ConditionalOnClass` condition matched in the running application. To check whether the condition matched, inspect the classpath and condition evaluation; to check whether a bean exists, inspect the context.

## 4. Class-name declarations: why is `String` useful with optional dependencies?

Suppose an optional library `com.vendor.sdk.ExternalClient` might not be installed. If you directly `import com.vendor.sdk.ExternalClient;` and write code depending on that type, the program **cannot compile** without the dependency at compile time. If the code was compiled yet the class disappears at runtime, certain accesses to class/method signatures can trigger linkage errors.

By contrast, a condition that **only needs to check presence or absence** can use the class name:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
public class OptionalClientAutoConfiguration {
    // Beans relevant only when ExternalClient exists.
}
```

`@ConditionalOnClass(name = "...")` does not require source code to import `ExternalClient`. Spring Boot uses metadata and the classpath to evaluate the condition. If that class is absent, this auto-configuration **does not match**; merely writing the class name does not load the class, download it, or create beans.

Comparing three usages:

| Declaration | When to use | What to watch out for |
| --- | --- | --- |
| `@ConditionalOnClass(value = ExternalClient.class)` | Conditional annotation placed **directly on a configuration class**; Boot can read metadata via ASM and check missing classes | The type in source still needs to exist on the **compile classpath** |
| `@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")` | Avoiding a direct type reference or working with an optional class name | Must spell the class name accurately; typos can prevent matching |
| Composed `@MyConditionalFeature` containing `@ConditionalOnClass(name = "...")` | When the class condition is placed as a **meta-annotation** on a custom annotation | **Must use `name`** for class conditions inside composed annotations, per Spring Boot guidance; avoid `value = OptionalClass.class` here |

Important Spring Boot caveat: **the safety guarantee for `Class<?>` literals in `@ConditionalOnClass` placed directly on a configuration class is not guaranteed the same way when the annotation is nested inside a composed annotation**. Inside custom meta-annotations, always choose the `name` attribute to check optional classes.

### 4.1. Where else are class names used?

- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` contains lines of fully qualified auto-configuration class names. This is a **candidate declaration for Boot to discover**, not a Java annotation.
- `@AutoConfiguration(afterName = "com.vendor.sdk.SdkAutoConfiguration")` declares ordering by name, useful when avoiding direct linkage to an optional class. `beforeName` works similarly.
- `@SpringBootApplication(excludeName = "com.vendor.sdk.SdkAutoConfiguration")` and `spring.autoconfigure.exclude` are mechanisms for excluding **auto-configurations** by name.
- `@ConditionalOnMissingClass("com.vendor.sdk.ExternalClient")` is the inverse condition, using the class name to check **absence**.

Depending on the API, names may be a single string or an array; **do not assume a `name` attribute on one annotation has the same meaning as `name` on another**. For example, `@ConditionalOnBean(name = "beanName")` checks a *bean name*, whereas `@ConditionalOnClass(name = "...")` checks a *Java class name*.

A class residing in a package does not mean it is on the runtime classpath; nor does a class name listed in `.imports` guarantee all auto-configuration conditions will match.

## 5. Complete runnable example: composed annotations, metadata, and class names

This example uses **Java 17+**, **Spring Boot 3.3.13**, and Maven. It demonstrates all three ideas:

- `@FeatureComponent` is a composed stereotype setting the bean name via `@AliasFor`.
- `@ClockAvailable` contains `@ConditionalOnClass(name = "java.time.Clock")` as a meta-annotation.
- `ClockAutoConfiguration` is discovered by Boot via its **class name** in `AutoConfiguration.imports`, even though it lies **outside the application's scanned package**.
- `OptionalClientAutoConfiguration` is also listed yet skipped because the optional SDK does not exist; it does not import a nonexistent type.
- `AnnotationMetadata` inspects direct and meta-annotations; `ApplicationContext` shows which beans actually exist.

**Project structure** (file names and packages must match):

```text
annotation-metadata-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── com/example/
    │       ├── app/
    │       │   ├── DemoApplication.java
    │       │   ├── FeatureComponent.java
    │       │   └── TimeReporter.java
    │       └── library/autoconfigure/
    │           ├── ClockAvailable.java
    │           ├── ClockAutoConfiguration.java
    │           └── OptionalClientAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**`pom.xml`** (basic starter, no web server needed):

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
    <groupId>com.example</groupId>
    <artifactId>annotation-metadata-demo</artifactId>
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
```

**`src/main/java/com/example/app/FeatureComponent.java`**

```java
package com.example.app;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface FeatureComponent {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

**`src/main/java/com/example/app/TimeReporter.java`**

```java
package com.example.app;

import java.time.Clock;

@FeatureComponent("timeReporter")
public final class TimeReporter {
    private final Clock clock;

    public TimeReporter(Clock clock) {
        this.clock = clock;
    }

    public String zoneId() {
        return clock.getZone().getId();
    }
}
```

`TimeReporter` does not have `@Component` directly at all; Spring recognizes the composed annotation. `Clock` is requested via constructor injection, and a matching bean must exist for the application to start successfully.

**`src/main/java/com/example/library/autoconfigure/ClockAvailable.java`**

```java
package com.example.library.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "java.time.Clock")
public @interface ClockAvailable {
}
```

This is a composed condition. `java.time.Clock` is a standard Java class, so it is present on Java 17. Although the example uses an always-available class for easy execution, the rule **`name` instead of `value` inside meta-annotations** becomes critical when checking classes from optional libraries.

**`src/main/java/com/example/library/autoconfigure/ClockAutoConfiguration.java`**

```java
package com.example.library.autoconfigure;

import java.time.Clock;
import java.time.ZoneId;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ClockAvailable
@ConditionalOnProperty(
        prefix = "demo.clock",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock demoClock() {
        return Clock.system(ZoneId.of("UTC"));
    }
}
```

`@AutoConfiguration` denotes a configuration class Boot can apply. `@ClockAvailable` provides the class condition; `@ConditionalOnProperty` toggles activation by configuration; `@ConditionalOnMissingBean(Clock.class)` lets the default bean back off when a matching `Clock` already exists. The `Clock` bean is **defined by auto-configuration**, while passing it into `TimeReporter` is DI.

**`src/main/java/com/example/library/autoconfigure/OptionalClientAutoConfiguration.java`**

```java
package com.example.library.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
public class OptionalClientAutoConfiguration {

    @Bean
    String optionalSdkMarker() {
        return "SDK_PRESENT";
    }
}
```

The class `com.vendor.sdk.ExternalClient` does not need to exist when compiling this sample because the entire reference is just a string in `name`. In a project without that SDK, the condition does not match and the `optionalSdkMarker` bean is not registered. `String` is used here solely to **observe the condition**, not as a real SDK integration API.

**`src/main/java/com/example/app/DemoApplication.java`**

```java
package com.example.app;

import com.example.library.autoconfigure.ClockAutoConfiguration;
import com.example.library.autoconfigure.ClockAvailable;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.type.AnnotationMetadata;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printEvidence(
            ApplicationContext context, TimeReporter reporter) {
        return args -> {
            AnnotationMetadata metadata =
                    AnnotationMetadata.introspect(ClockAutoConfiguration.class);

            System.out.println("DIRECT_CLOCK_AVAILABLE="
                    + metadata.hasAnnotation(ClockAvailable.class.getName()));
            System.out.println("META_CONDITIONAL_ON_CLASS="
                    + metadata.hasMetaAnnotation(ConditionalOnClass.class.getName()));
            System.out.println("CLOCK_BEAN=" + context.containsBean("demoClock"));
            System.out.println("OPTIONAL_BEAN="
                    + context.containsBean("optionalSdkMarker"));
            System.out.println("REPORTER_BEAN="
                    + context.containsBean("timeReporter"));
            System.out.println("REPORTER_ZONE=" + reporter.zoneId());
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.clock.enabled=true
```

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
com.example.library.autoconfigure.ClockAutoConfiguration
com.example.library.autoconfigure.OptionalClientAutoConfiguration
```

This is a **fixed-name resource file**, not an annotation and without a `.java` extension. Each line is the fully qualified class name of a candidate auto-configuration. Spring Boot checks this file on the classpath of JARs and the application; merely appearing in the file does **not** make the class's conditions match.

To highlight the two mechanisms clearly, `DemoApplication` sits in `com.example.app`, whereas the auto-configs sit in `com.example.library.autoconfigure` — outside default component scanning scope. `ClockAutoConfiguration` is still found via the imports file.

**Run:** install Java 17+ and Maven, then from the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

With the exact code and properties above, the lines printed by `ApplicationRunner` (excluding environment/Maven messages) are:

```text
DIRECT_CLOCK_AVAILABLE=true
META_CONDITIONAL_ON_CLASS=true
CLOCK_BEAN=true
OPTIONAL_BEAN=false
REPORTER_BEAN=true
REPORTER_ZONE=UTC
```

**Line-by-line explanation:**

1. `DIRECT_CLOCK_AVAILABLE=true`: `ClockAutoConfiguration` is directly annotated with `@ClockAvailable`.
2. `META_CONDITIONAL_ON_CLASS=true`: Spring locates `@ConditionalOnClass` on the `@ClockAvailable` annotation definition.
3. `CLOCK_BEAN=true`: Boot imported the auto-config, `Clock` exists, the property is enabled, and no other `Clock` bean exists; `demoClock` is registered.
4. `OPTIONAL_BEAN=false`: the second auto-config was a candidate yet was excluded by `@ConditionalOnClass(name=...)` because the SDK class name does not exist.
5. `REPORTER_BEAN=true`: component scanning found `TimeReporter` via the composed stereotype; the alias set the bean name to `timeReporter`.
6. `REPORTER_ZONE=UTC`: DI injected the auto-configured `Clock` into `TimeReporter`; the bean provides the `UTC` zone.

**Intentional change test:** if you change `demo.clock.enabled=false`, `ClockAutoConfiguration` does not match, so the current example **fails to start** because `TimeReporter` still requires a `Clock` bean. This illustrates that configuration conditions control bean registration, while DI cannot synthesize a missing bean. To run with auto-config disabled, you must supply a `Clock` bean manually (e.g., via an application `@Bean` method).

## 6. When is bytecode-level metadata especially useful?

Imagine an auto-config JAR containing an optional class. If Spring always had to load and link every class before evaluating conditions, a missing optional library would easily cause `ClassNotFoundException` or `NoClassDefFoundError` during configuration discovery.

Reading class resources via ASM lets Spring inspect annotations and class names **without instantiating beans and in many cases without loading the described classes**. Classpath conditions can thus be filtered out early.

However, never interpret this as "metadata eliminates all class-loading issues". Certain patterns remain hazardous:

**Case A — annotation on an `@Bean` method whose return type is an optional class:**

```java
// ILLUSTRATIVE code, assuming ExternalClient comes from an optional dependency.
@Bean
@ConditionalOnClass(ExternalClient.class)
ExternalClient externalClient() {
    return new ExternalClient();
}
```

The condition may not be evaluated before the JVM or Spring must inspect the signature of `externalClient()`. Spring Boot recommends **isolating the condition onto a separate nested `@Configuration` class** to guard the methods that use optional classes:

```java
// ILLUSTRATIVE code; only compiles if ExternalClient is on the compile classpath.
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
static class ExternalClientConfiguration {

    @Bean
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

The class containing methods that depend on optional types is isolated behind the class condition. This pattern is typically placed inside a parent auto-configuration. Without the SDK on the compile classpath, an illustrative example referencing `ExternalClient` will not compile; in that case, place the integration in a module with the appropriate compile dependency.

**Case B — composed annotation using a class literal for an optional class:**

```java
// Do not choose this approach for optional class conditions inside a meta-annotation.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(value = ExternalClient.class)
public @interface ConditionalOnExternalClient {
}
```

Reading annotations via meta-annotations can require resolving the class reference before applying ASM protection the way direct conditional annotations do. The recommended approach is:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
public @interface ConditionalOnExternalClient {
}
```

These two snippets are **mechanism illustrations**, not two complete Java files (missing imports and dependency declarations).

**Case C — listing a class name in the imports list when the class does not actually exist:** Spring Boot must be able to import the **actual candidate configuration class**; the imports file is not a "skip misspelled names" mechanism for the library's own auto-config. `name` in a conditional annotation is the name of the *class being checked*; a name in `AutoConfiguration.imports` is the name of the *configuration class to load if applicable*. Those are two different meanings.

## 7. Spring Boot metadata types not to confuse

| Resource/API | Role | When is it needed? |
| --- | --- | --- |
| `AnnotationMetadata`, `MergedAnnotations` | Model for reading direct annotations, meta-annotations, and merged attributes; usable in frameworks/tests | When reading/inspecting annotations on classes and methods |
| `MetadataReader`, ASM | Reads class metadata from bytecode without necessarily loading the class | Component scanning, configuration parsing, and filtering |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Lists candidate auto-configuration class names in the JAR | **Required** for Boot to discover custom auto-configs per Boot 3.x standards |
| `META-INF/spring-autoconfigure-metadata.properties` | Optimization metadata generated by annotation processor to pre-filter auto-configs failing conditions | Startup optimization when packaging auto-config libraries; does not replace imports |
| `META-INF/spring-configuration-metadata.json` | Metadata about **configuration properties**, powering IDE suggestions/docs | When publishing property groups like `acme.timeout`; not an auto-config list |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` | Maps old auto-config names to new names for ordering/exclusion when classes are renamed | When moving packages/renaming published auto-configs in a library |

In Spring Boot 3.x, do not rely solely on the `EnableAutoConfiguration` key in `META-INF/spring.factories` from older tutorials to register custom auto-configs. The standard candidate format is `AutoConfiguration.imports`. Optimization metadata and properties metadata files serve **two separate purposes**.

## 8. Diagnostic tips and common pitfalls

**1. Composed annotation does not create a bean as expected:** check `@Target`/`@Retention`, `@Component` meta-annotation, package scan scope, aliases, and bean name. A "pretty" annotation without `@Component` or an import mechanism will not register beans automatically.

**2. Bean name alias does not work:** verify that `@AliasFor(annotation = Component.class, attribute = "value")` declares the right attribute, return type, and compatible default value; avoid conflicting alias values.

**3. `metadata.hasAnnotation(...)` returns `false`:** the annotation may sit at the **meta level**; use `hasMetaAnnotation` or `isAnnotated`/`MergedAnnotations` for the right question. Do not confuse "annotation not directly present" with "Spring did not recognize the annotation".

**4. `@ConditionalOnClass` looks right yet a missing-class error occurs:** check type references in method return types, constructors, composed annotations, or eagerly loaded code. In composed annotations check `name`; for bean methods depending on optional types, isolate them into a guarded `@Configuration` class.

**5. Auto-config is not discovered:** check spelling and path of `AutoConfiguration.imports`, one FQCN per line, packaged inside the JAR. Do not expect component scanning to discover auto-config classes; do not declare auto-configs as application components.

**6. Auto-config is in imports yet the bean is still missing:** this can be a valid outcome of `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, or other conditions. Use `--debug` to view the *Condition Evaluation Report*, for example:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--debug
```

If trying this command, adjust the demo's `logging.level.root=OFF` so debug logs can appear. With Actuator, `/actuator/conditions` also helps inspect conditions when dependencies and exposure are properly configured; it is not public by default.

**7. Ordering auto-configs by class name:** with `@AutoConfiguration(afterName=...)`, ordering relates to **bean definitions**, not a guarantee of instantiation order for every bean. Bean creation order remains governed by dependencies and relationships such as `@DependsOn`.

**8. Class renamed/moved package:** string references in `AutoConfiguration.imports`, `beforeName`/`afterName`, and exclusions must be updated accurately; when renaming a published auto-config, consider `AutoConfiguration.replacements` for compatibility.

## 9. Self-check questions

1. Can a class with `@FeatureComponent` but no direct `@Component` be scanned? **Yes**, if the custom annotation is meta-annotated with a valid `@Component` and the class is within scan scope.
2. How does `metadata.hasAnnotation(ConditionalOnClass.class.getName())` differ from `metadata.hasMetaAnnotation(...)`? The first asks about a **direct** annotation; the second asks about a **meta-annotation**.
3. Why should a composed annotation checking an optional class use `@ConditionalOnClass(name="...")`? Because Spring Boot does not guarantee handling class literals via meta-annotations as safely as conditional annotations placed directly on configurations.
4. Both `AutoConfiguration.imports` and `ConditionalOnClass.name` hold class names; do they share the same job? **No**. Imports lists **auto-config candidates**; the condition checks **presence of a dependency/class**.
5. An auto-config is discovered yet creates no bean: is that definitely an error? **No**. Check whether `@Conditional...` conditions or user beans caused the configuration not to match or to back off.
6. Which API helps read metadata before loading a class? `MetadataReader` using classfile/ASM is one option; `AnnotationMetadata.introspect(SomeClass.class)` is not in that group since it already takes a `Class` object.

## 10. References

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): imports file, class conditions, optional dependencies, ordering, and metadata processor.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): meta-annotations, composed stereotypes, and bean name aliases.
- [Spring Framework — AnnotationMetadata API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotationMetadata.html): distinguishing direct annotations from meta-annotations.
- [Spring Framework — MergedAnnotations API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/annotation/MergedAnnotations.html): how Spring merges annotations/meta-annotations and `@AliasFor`.

**Practical mindset:** When encountering an annotation in auto-configuration, ask: is the annotation declared **directly or via meta**? Is Spring reading it **via reflection or bytecode metadata**? Is the attribute a **Java class literal**, a **string class name**, or a **bean name**? Is the class in `AutoConfiguration.imports` a **candidate** or a matched condition? Separating those four layers prevents most missing-optional-dependency errors and inactive auto-configuration issues.
