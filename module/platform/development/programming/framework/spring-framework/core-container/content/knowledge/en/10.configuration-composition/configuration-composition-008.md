# Designing Feature-Enabling Annotations with the `@Enable` Pattern in Spring Framework

## 1. From Scattered Configurations to One Public Annotation

In Spring, a feature rarely consists of a single object. For example, auditing may require an `AuditSink`, a service using that sink, and perhaps a validator, advisor, or infrastructure bean. If users had to manually import every configuration:

```java
@Configuration
@Import({
    AuditSinkConfig.class,
    AuditServiceConfig.class,
    AuditInfrastructureConfig.class
})
class AppConfig {
}
```

then the startup site would need to know too many implementation details. As the feature evolves, the class list might change, forcing applications using the library to modify code just to add an internal config.

A cleaner API:

```java
@Configuration
@EnableAudit(level = AuditLevel.DETAILED)
class AppConfig {
}
```

In this design, **`@EnableAudit` is a custom-defined annotation**, not built into Spring Framework. Internally, it uses `@Import` to point Spring toward a configuration class, `ImportSelector`, or `ImportBeanDefinitionRegistrar`. The application only declares **the intent to enable the feature**, while the library retains control over organizing beans and implementations.

That is the `@Enable...` design pattern: a **type-level annotation** becomes a declarative entry point for an application capability.

Many real Spring annotations follow this pattern: `@EnableCaching`, `@EnableAsync`, `@EnableScheduling`, `@EnableTransactionManagement`. They differ in implementation details, yet share the same idea: activating infrastructure configuration mechanisms via an annotation on a configuration class.

Lesson objectives:

1. Design metadata for a custom `@Enable...` annotation: `@Target`, `@Retention`, `@Documented`, `@Import`, and attributes.
2. Choose the right extension point: importing a fixed class, `ImportSelector`, `DeferredImportSelector`, or `ImportBeanDefinitionRegistrar`.
3. Ensure a feature is enabled/disabled **consistently across both producer and consumer beans**.
4. Understand when a selector reads annotation attributes, the environment, or conditions.
5. Distinguish enabling framework infrastructure from providing all required underlying dependencies.
6. Design a stable, refactor-friendly public API without scanning too broadly.
7. Run a Java 17+ demo with Spring 6.2 for `@EnableAudit` in BASIC, DETAILED, and OFF modes, matching expected output.
8. Test and diagnose missing beans, duplicate beans, proxy issues, and lifecycle errors.

## 2. How Does an `@Enable...` Annotation Work?

In Java terms, an annotation is just **metadata**; placing `@EnableAudit` on a class does not mean the JVM calls bean-creation code. Spring must see that configuration class, process its metadata, and have a mechanism to turn that metadata into bean definitions.

Typical flow:

```text
AppConfig is registered in ApplicationContext
                    |
                    v
         @EnableAudit(level=DETAILED)
                    |
                    v
     Annotation is meta-annotated with @Import
                    |
                    v
           AuditConfigurationSelector
                    |
          Read metadata/attributes
                    |
                    v
  Select DetailedAuditConfig + AuditServiceConfig
                    |
                    v
    Spring processes imported configuration classes
                    |
                    v
  Register AuditSink and AuditService bean definitions
                    |
                    v
      BeanFactory resolves dependencies & lifecycle
                    |
                    v
        Managed beans are ready to use
```

**Core point:** the public annotation **declares the request**, the internal extension point **selects/registers definitions**, and BeanFactory **creates and manages objects**. Do not collapse all three phases into a method calling `new` directly and assume the container manages the object.

### 2.1. First Prerequisite: The Class Using `@Enable...` Must Be Processed

```java
@EnableAudit
class AppConfig {
}
```

If `AppConfig` is never brought into a Spring context via direct registration, component scanning, another `@Import`, or an equivalent valid mechanism, the annotation **will not be processed**. In our runnable demo, we use:

```java
new AnnotationConfigApplicationContext(BasicAppConfig.class)
```

This is an illustrative snippet from the example in section 8. Bean definitions are created within that context, not JVM-wide.

### 2.2. Enabling a Feature Is Not Enabling Component Scanning

`@EnableAudit` does not require `@ComponentScan`. When an annotation declares `@Import(AuditSelector.class)`, Spring only imports the classes returned by the selector and any registrations stemming from those classes.

If an imported configuration itself contains `@ComponentScan`, it may scan a package and register more beans; however, that comes from **the imported configuration**, not because every `@Enable...` annotation inherently scans the library's packages.

### 2.3. One Capability Often Involves Multiple Beans

“Enabling audit” usually requires both a **writer** and a **service using the writer**. Registering only the service without supplying the writer fails the context when the dependency is mandatory. Disabling the writer while leaving an eager service requiring that writer also breaks the context when disabling the feature.

Therefore, think in terms of **the module's bean graph** rather than a single class: a selector should pick a coherent set of configuration classes. When disabled, either do not register the consumer, or give the consumer an intentional optional dependency/fallback.

## 3. Minimal Anatomy of a Custom `@Enable` Annotation

An annotation typically looks like:

```java
package com.acme.audit;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(AuditModuleConfig.class)
public @interface EnableAudit {
}
```

This is an **illustrative `EnableAudit.java` file** requiring a valid `AuditModuleConfig` class to compile. In this minimal version, `@Import` brings in a fixed configuration class; no selector or registrar is needed.

Meaning of each piece of metadata:

| Annotation | Role |
| --- | --- |
| `@Target(ElementType.TYPE)` | Allows attaching the annotation only to class/interface/annotation types per Java rules |
| `@Retention(RetentionPolicy.RUNTIME)` | Retains the annotation at runtime so the framework can inspect metadata |
| `@Documented` | Allows Javadoc of types using this annotation to display it |
| `@Import(AuditModuleConfig.class)` | Points Spring to the configuration class or extension point to process |
| `public @interface EnableAudit` | Defines a Java annotation usable by applications |

`@Retention(RUNTIME)` is the standard choice for configuration annotations read via reflection. Spring also has class-file metadata readers, yet you should not use an unclear retention policy for public configuration annotations.

### 3.1. Parameterless Version

If there is always only one way to set up auditing, use a static configuration:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(AuditModuleConfig.class)
public @interface EnableAudit {
}
```

And in the application:

```java
@Configuration(proxyBeanMethods = false)
@EnableAudit
class ShopConfiguration {
}
```

These are two separate illustrative excerpts. Pros: minimal code, easy debugging, and the imported config clearly defines the beans. If logic depends on profiles/properties yet remains a simple present/absent toggle, you can place `@Conditional` on the configuration or bean factory methods without needing a selector.

### 3.2. Version with Attributes

When you want to offer BASIC/DETAILED choices or allow disabling:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(AuditSelector.class)
public @interface EnableAudit {
    boolean enabled() default true;
    AuditLevel level() default AuditLevel.BASIC;
}
```

This is an **illustrative excerpt** requiring `AuditSelector` and enum `AuditLevel`. Those attributes become **the annotation's public API**; users can write:

```java
@EnableAudit(enabled = true, level = AuditLevel.DETAILED)
```

Or:

```java
@EnableAudit(enabled = false)
```

Do not pick defaults carelessly: if enabling audit by default incurs costs or compliance obligations, establish clear agreement on what `enabled=true` means, supported environments, required dependencies, and behavior when providers are missing.

### 3.3. Is `@AliasFor` Required?

**Not every `@Enable...` annotation needs `@AliasFor`.** With `enabled()` and `level()` as dedicated attributes read by a selector, no alias is needed.

`@AliasFor` is useful when a custom annotation **re-exposes** or synchronizes attributes of a corresponding meta-annotation. For instance, when building a composed annotation directly over `@ComponentScan`, aliasing to `basePackages` must declare proper semantics with clear tests and documentation.

Do not use `@AliasFor` thinking “`enabled` will automatically propagate to every imported configuration”. `@Import` has no `enabled` attribute to alias to; a selector or condition handles how that attribute behaves.

## 4. Three Ways to Implement Feature-Enabling Annotations

### 4.1. Approach A — `@Import` a Fixed Configuration Class

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AuditModuleConfig.class)
public @interface EnableAudit {
}
```

Fits when:

- a module always has the same set of bean definitions;
- no implementation selection based on annotation attributes is needed;
- you want a minimal structure easy to trace from annotation to configuration.

`AuditModuleConfig` can declare multiple `@Bean` methods or import further configs. Once processed, resulting bean definitions remain subject to all scope, dependency, condition, and naming rules.

### 4.2. Approach B — `@Import(ImportSelector.class)`

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AuditSelector.class)
public @interface EnableAudit {
    AuditLevel level() default AuditLevel.BASIC;
}
```

`AuditSelector` implements `org.springframework.context.annotation.ImportSelector`:

```java
@Override
public String[] selectImports(AnnotationMetadata metadata) {
    Map<String, Object> attrs =
            metadata.getAnnotationAttributes(EnableAudit.class.getName());
    if (attrs == null) {
        throw new IllegalStateException("Missing @EnableAudit");
    }
    AuditLevel level = (AuditLevel) attrs.get("level");
    return level == AuditLevel.DETAILED
            ? new String[] { DetailedAuditConfig.class.getName() }
            : new String[] { BasicAuditConfig.class.getName() };
}
```

The snippets above are **illustrative**, requiring full imports, the enum, and classes. `ImportSelector` returns **fully qualified class names**, not bean names and not bean object instances.

Fits when:

- attributes of `@Enable...` determine which classes to import;
- there are multiple implementation configurations;
- you want to hide internal packages/classes behind the annotation;
- selection happens at context build time and can be tested cleanly.

`ImportSelector` can read `Environment` via `EnvironmentAware` or constructor injection of supported infrastructure types per Spring Javadoc. However, avoid eagerly looking up business beans just to choose imports: selection happens during configuration parsing, usually before application beans are ready.

### 4.3. Approach C — `@Import(ImportBeanDefinitionRegistrar.class)`

A registrar can use `AnnotationMetadata` and `BeanDefinitionRegistry` to programmatically construct bean definitions:

```java
public final class AuditRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata,
            BeanDefinitionRegistry registry) {
        RootBeanDefinition definition =
                new RootBeanDefinition(AuditRuntime.class);
        registry.registerBeanDefinition("auditRuntime", definition);
    }
}
```

This is an **illustrative snippet** requiring imports from `org.springframework.context.annotation.ImportBeanDefinitionRegistrar`, `org.springframework.core.type.AnnotationMetadata`, `org.springframework.beans.factory.support.BeanDefinitionRegistry`/`RootBeanDefinition`, and an `AuditRuntime` class with a suitable constructor.

Fits when:

- bean counts/types/names depend on dynamic metadata;
- a framework needs to register definitions at a lower level than `@Bean`;
- you genuinely need control over `BeanDefinitionRegistry`.

Do not use a registrar when you only need two fixed factory methods. It is more complex than a selector/configuration, prone to name collisions, and carries lifecycle constraints for infrastructure post-processors. In particular, Spring's Javadoc warns against registering `BeanDefinitionRegistryPostProcessor` via a registrar; follow the appropriate extension point.

### 4.4. Comparing Choices

| Requirement | First Recommendation |
| --- | --- |
| Enable a fixed configuration set | `@Import(MyFeatureConfig.class)` |
| Two configs selected by a `mode` attribute | `ImportSelector` |
| Only toggle one config by property | `@Conditional` on the config may suffice |
| Dev/prod environments | `@Profile` where appropriate |
| Add many dynamic bean definitions from metadata | `ImportBeanDefinitionRegistrar` |
| Auto-configuration with complex ordering/aggregation | Look at `DeferredImportSelector` and matching auto-config mechanisms |
| Discover all application components under a package | `@ComponentScan`, do not misuse `@Import` |

Principle: **choose the lowest level of abstraction that cleanly meets the requirement**.

## 5. Distinguishing `@Enable...` from Spring's Built-In Annotations

Spring Framework provides several well-known annotations. Let's inspect their usage and activation mechanisms so we can design our own annotations with clear responsibilities.

| Annotation | What Capability Does It Enable? | What Else Is Required? |
| --- | --- | --- |
| `@EnableCaching` | Infrastructure handling cache annotations such as `@Cacheable` | Suitable `CacheManager`/cache resolver and caching configuration |
| `@EnableAsync` | Infrastructure handling `@Async` methods | Eligible managed beans and suitable executor/configuration |
| `@EnableScheduling` | Infrastructure discovering/registering `@Scheduled` methods | Managed beans with scheduled methods and suitable scheduler |
| `@EnableTransactionManagement` | Infrastructure handling `@Transactional` | Transaction manager suited to the resources and application |
| Custom `@EnableAudit` | Application/library-defined audit module | Config/beans properly registered by selector or registrar |

### 5.1. Real Example: `@EnableCaching`

In Spring Framework 6.2, `@EnableCaching` is meta-annotated with `@Import(CachingConfigurationSelector.class)`. This selector chooses the infrastructure matching `AdviceMode`/configuration. It is a classic example of the “public annotation → selector → infrastructure configurations” design.

However, merely writing `@EnableCaching` **does not guarantee every method is cached**. You still need cache annotations on managed beans, an appropriate manager/resolver, and the configured proxy/AspectJ mechanism. In proxy mode, normal self-invocation can bypass the proxy; that is an AOP concern, not something `@Enable` solves automatically.

### 5.2. Real Example: `@EnableAsync`

`@EnableAsync` uses `AsyncConfigurationSelector` to import configuration for asynchronous method execution. It does not turn every Java method asynchronous. Methods must be annotated with `@Async` on Spring-managed beans, and calls must pass through the configured infrastructure/proxy.

Do not conclude that a custom `@EnableAudit` must use AOP to be a “proper `@Enable`”. If auditing only needs producer/service beans, `@Import` or a simple selector is completely valid.

### 5.3. Real Example: `@EnableScheduling`

`@EnableScheduling` registers infrastructure beans that detect `@Scheduled` on managed beans. It does not create jobs if the application has no matching methods. Scheduler sizing, thread pools, execution errors, and job execution lifecycles must be considered separately.

### 5.4. Real Example: `@EnableTransactionManagement`

This annotation enables infrastructure supporting `@Transactional`, yet **does not automatically create a database**, `DataSource`, or transaction manager for every app. The same holds for custom `@Enable...` annotations: clearly publish which beans/resources users must provide and when the capability is actually ready.

## 6. Public API: Designing Meaningful Attributes

A feature-enabling annotation should have a small, clear, stable surface area.

### 6.1. `enabled`, `mode`, `level`, and Default Values

A clean design:

```java
public @interface EnableAudit {
    boolean enabled() default true;
    AuditLevel level() default AuditLevel.BASIC;
}
```

This is an attribute-only illustrative snippet, omitting `@Target`/`@Retention`/`@Import`.

- `enabled` expresses **turning the entire module on/off**.
- `level` selects the implementation/behavior when the module is enabled.
- `default` ensures parameterless `@EnableAudit` has well-defined semantics.
- When `enabled=false`, other attributes may be ignored or validated per documented policy.

If the use case picks between two protocols, an attribute named `protocol` can be clearer than a generic `mode`. Do not add dozens of switches for every internal bean just because annotations allow many attributes.

### 6.2. Why Use Enums Instead of Strings?

`AuditLevel.BASIC` and `AuditLevel.DETAILED` are checked by the Java compiler; a typo like `DETAILD` is a compile error. By contrast, `String level()` easily lets typos slip to runtime.

Enums suit small, stable option sets. When third-party plugins must extend providers, another model may fit better: class tokens, provider types, or configuration properties. Do not try to enumerate every future extension in a public enum if the ecosystem is meant to stay open.

### 6.3. Never Put Secrets in Annotation Attributes

Java annotation attributes are static class metadata by nature. Never use annotations to hold passwords, API keys, or secrets. Values that vary by environment should come through runtime configuration or proper secret management, not be compiled into source code.

### 6.4. Be Careful with Renames and Refactoring

Selector and config classes should use `SomeConfig.class.getName()` rather than string class-name literals to reduce package typo risks, especially with nested classes. Renaming a public annotation or enum constants is a breaking API change affecting all callers.

Bean names referenced by consumers as strings can also be contracts, though they do not need to be exposed as annotation attributes if users only need interface/type injection.

### 6.5. What `@Enable...` Should Not Promise

Never advertise that an annotation “enables auditing for **all** objects” when the module actually only configures an `AuditService`. Objects created via `new` outside Spring are not automatically managed. If the feature uses AOP, callers must go through the proper proxy; if it uses a bean factory, only consumers injected with the service benefit from the capability.

Describe accurately:
- Which bean definitions are registered?
- Which dependencies are required?
- What does disabling the feature mean?
- Does it affect existing beans once the context refreshes?
- Are there notable bean scopes/lifecycles, side effects, or startup costs?

## 7. Lifecycle and When the Feature Takes Effect

Key milestones:

```text
Class is registered in context
           |
           v
Configuration metadata is read
           |
           v
@Import / selector / registrar runs
           |
           v
Bean definitions are registered
           |
           v
Bean post-processors and factory phases run
           |
           v
Beans created as needed by scope/lazy/dependencies
           |
           v
Application starts using the capability
```

### 7.1. `@Enable` Is Normally Bootstrap Configuration, Not a Runtime Toggle

If `@EnableAudit(enabled=true)` routes a selector to `AuditServiceConfig`, that choice is applied while building the context. After `refresh()`, flipping an arbitrary property **does not automatically re-run** `ImportSelector` to add or remove bean definitions.

To toggle auditing while the application is running, you normally need an always-present facade—such as an `AuditService` checking a feature flag per invocation—or a deliberately designed context refresh/rebuild mechanism. That is a different requirement from the static `@Enable...` pattern.

### 7.2. Scope and Lazy Semantics Still Belong to BeanFactory

`@Enable...` by itself does not turn singletons into prototypes, does not make beans lazy, and does not dictate initialization order. Every imported bean still follows `@Scope`, `@Lazy`, `@DependsOn`, the dependency graph, and BeanPostProcessors just like any other bean.

### 7.3. “Enable” Does Not Mean “Bypass All Other Conditions”

An imported `@Configuration` can carry `@Profile`/`@Conditional`. If those conditions fail, its bean definitions may be skipped even though the selector returned the class name. A consumer requiring a mandatory dependency can still cause the context to fail. Design consumer and producer configs together.

### 7.4. Classpath Conditions

If a selector returns `com.vendor.AuditIntegrationConfig` when the module containing that class is absent from the runtime classpath, import processing can fail. Do not return an optional class name without checking the corresponding conditions; for Spring Boot libraries, conditional auto-configuration mechanisms usually fit classpath-conditional modules better.

## 8. Complete Java 17+ Runnable Example: Designing `@EnableAudit`

We build a plain Spring Context Java application with three configuration classes:

- `BasicApp`: default `@EnableAudit`, selecting BASIC.
- `DetailedApp`: `@EnableAudit(level=DETAILED)`, selecting DETAILED.
- `OffApp`: `@EnableAudit(enabled=false)`, registering none of the audit module's beans.

Each context is independent. `AuditImportSelector` selects **two configurations** when enabled: one providing `AuditSink`, and one providing `AuditService` depending on that sink. When disabled, it returns an empty array so no consumer is left missing a dependency.

No Spring Boot, HTTP, database, XML, or external services are needed.

### 8.1. File Structure

```text
enable-audit-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── EnableAuditDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'enable-audit-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'EnableAuditDemo'
}
```

Run with JDK 17+ and a JDK-compatible Gradle version. `spring-context` brings in the Spring Beans/Core modules needed for `@Configuration`, `@Import`, `AnnotationMetadata`, and `AnnotationConfigApplicationContext`.

### 8.2. Complete Source Code

Save everything in `src/main/java/EnableAuditDemo.java`:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Map;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class EnableAuditDemo {

    public enum AuditLevel {
        BASIC, DETAILED
    }

    public interface AuditSink {
        String format(String action);
    }

    public record BasicAuditSink() implements AuditSink {
        @Override
        public String format(String action) {
            return "basic:" + action;
        }
    }

    public record DetailedAuditSink() implements AuditSink {
        @Override
        public String format(String action) {
            return "detailed:" + action + "|trace";
        }
    }

    public record AuditService(AuditSink sink) {
        public String report(String action) {
            return sink.format(action);
        }
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Import(AuditImportSelector.class)
    public @interface EnableAudit {
        boolean enabled() default true;
        AuditLevel level() default AuditLevel.BASIC;
    }

    public static class AuditImportSelector implements ImportSelector {
        @Override
        public String[] selectImports(
                AnnotationMetadata importingClassMetadata) {

            Map<String, Object> attributes =
                    importingClassMetadata.getAnnotationAttributes(
                            EnableAudit.class.getName());

            if (attributes == null) {
                throw new IllegalStateException(
                        "Missing @EnableAudit metadata");
            }

            boolean enabled = (Boolean) attributes.get("enabled");
            if (!enabled) {
                return new String[0];
            }

            AuditLevel level =
                    (AuditLevel) attributes.get("level");

            Class<?> sinkConfig = level == AuditLevel.DETAILED
                    ? DetailedAuditConfig.class
                    : BasicAuditConfig.class;

            return new String[] {
                    sinkConfig.getName(),
                    AuditServiceConfig.class.getName()
            };
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BasicAuditConfig {
        @Bean
        AuditSink auditSink() {
            return new BasicAuditSink();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DetailedAuditConfig {
        @Bean
        AuditSink auditSink() {
            return new DetailedAuditSink();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AuditServiceConfig {
        @Bean
        AuditService auditService(AuditSink sink) {
            return new AuditService(sink);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAudit
    public static class BasicApp {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAudit(level = AuditLevel.DETAILED)
    public static class DetailedApp {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAudit(enabled = false)
    public static class OffApp {
    }

    private static void show(
            String label, Class<?> applicationConfig) {

        try (var context =
                     new AnnotationConfigApplicationContext(
                             applicationConfig)) {

            int sinkCount =
                    context.getBeanNamesForType(AuditSink.class).length;
            int serviceCount =
                    context.getBeanNamesForType(AuditService.class).length;

            System.out.println(label + ": sinks=" + sinkCount +
                    ", services=" + serviceCount);

            if (serviceCount > 0) {
                AuditService service =
                        context.getBean(AuditService.class);
                System.out.println(label + ": " +
                        service.report("checkout"));
            }
        }
    }

    public static void main(String[] args) {
        show("BASIC", BasicApp.class);
        show("DETAILED", DetailedApp.class);
        show("OFF", OffApp.class);
    }
}
```

### 8.3. Running and Stdout

In the `enable-audit-demo` directory:

```bash
gradle run --quiet
```

If the project has Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS, or `.\gradlew.bat run --quiet` on Windows PowerShell.

Stdout **printed by the program itself**:

```text
BASIC: sinks=1, services=1
BASIC: basic:checkout
DETAILED: sinks=1, services=1
DETAILED: detailed:checkout|trace
OFF: sinks=0, services=0
```

These are the `System.out.println` lines from the demo. A build tool or logging backend may emit extra lines of its own; do not treat them as application business output.

### 8.4. Analyzing Each Case

**BASIC:** `@EnableAudit` on `BasicApp` uses defaults `enabled=true` and `level=BASIC`. The selector receives metadata, picks `BasicAuditConfig` and `AuditServiceConfig`, creating an `AuditSink` bean returning `BasicAuditSink` and an `AuditService` bean consuming that sink. There is exactly one bean of each type. `report("checkout")` returns `basic:checkout`.

**DETAILED:** `DetailedApp` declares `level=DETAILED`, so the selector picks `DetailedAuditConfig`. The `AuditService` bean is created from the same `AuditServiceConfig`, receiving `DetailedAuditSink` via the `AuditSink` interface. The audit line includes the `|trace` suffix.

**OFF:** `OffApp` is still processed by Spring as a valid configuration class, yet the selector reads `enabled=false` and returns an empty array. **Neither `AuditSink` nor `AuditService` is registered**, because both config sources sit behind the selector. The context refreshes cleanly; the program skips `getBean(AuditService.class)` when no service exists.

This design gives “disable feature” clean semantics: none of the audit capability beans exist in that context. If you want the audit service to remain present as a no-op, that is a different policy: have the selector pick `NoOpAuditConfig` while still satisfying consumer dependencies.

### 8.5. Why Do Both Configs Share the Bean Name `auditSink` Without Conflict?

Both `BasicAuditConfig` and `DetailedAuditConfig` declare `@Bean auditSink()`. However, the selector **picks only one of the two configs at a time**, and each case creates **a separate ApplicationContext**. Thus the registry never receives two `auditSink` bean definitions simultaneously.

If other code imports both configs, the `auditSink` name can collide or be overridden depending on registry policy; even after renaming, both can still cause ambiguity when injecting a single `AuditSink`. A selector cannot stop independent registrations performed by other modules.

### 8.6. Why Does `AuditServiceConfig` Use a Method Parameter?

`AuditServiceConfig.auditService(AuditSink sink)` receives a dependency resolved by Spring. It does not call `BasicAuditConfig.auditSink()` or `DetailedAuditConfig.auditSink()` directly and does not need to know which implementation is active.

This keeps configuration decoupled: the selector chooses the provider config, and BeanFactory injects the right provider into the consumer. When implementations change, the consumer config stays untouched.

### 8.7. Why Is `@ComponentScan` Not Used in the Example?

To clearly demonstrate “only imported classes participate”, the demo does not scan packages. If you enabled a scanner on a package containing the configs and put stereotypes on all of them, you could easily register both BASIC and DETAILED accidentally before the selector makes a choice, defeating the demo's goal.

A library can use component scanning internally, but when designing `@Enable...` to pick one implementation, watch **package and registration boundaries**. Do not scan an entire library just to use one bean.

## 9. Common Design Variations

### 9.1. Enabling the Feature While Allowing No-Op When Disabled

If auditing is optional yet the application always injects `AuditService`, disabling by **not registering the service** will fail if a consumer unconditionally requires it. Another strategy is always registering the service interface and plugging in a `NoOpAuditSink` when disabled.

Illustrative example:

```java
public record NoOpAuditSink() implements AuditSink {
    @Override
    public String format(String action) {
        return "ignored";
    }
}
```

This snippet requires the `AuditSink` interface from section 8's demo. A selector can pick `NoOpAuditConfig` + `AuditServiceConfig` when `enabled=false`. The public contract then becomes “the audit service is always present, though it may not record”. Choose the design based on consumer needs and safety/compliance requirements; never silently drop mandatory auditing in real systems.

### 9.2. Separating `enabled` from `level`

`enabled=false` usually takes precedence over `level` since there is nothing to choose when the module is off. However, if you want to report an error when someone sets `enabled=false, level=DETAILED`, the selector can validate that combination. Rules must be clearly documented in the API; section 8's example intentionally ignores `level` when disabled.

### 9.3. Selecting via `Environment`

You can have the selector implement `EnvironmentAware` and read a property such as `audit.level` to override the annotation attribute. This variation fits when deployment configuration must be adjusted without editing code. Publish the precedence order: whether the attribute or property wins, how invalid values are handled, and note that properties must be set **before configuration processing**.

Using `@ConditionalOnProperty` in Spring Boot or `@Conditional` in Spring Framework for simple conditions can take less code than a custom selector. Do not build an overly broad custom condition/flag framework when Spring already provides the needed extension point.

### 9.4. Annotation Pointing to the Chosen Class

For ecosystems with many providers where an enum is not flexible enough, a design like `Class<? extends AuditSink> implementation()` lets callers pick a class. Note that doing so exposes implementation types in the public API and still needs proper registration/DI. User-selected objects should be instantiated by Spring rather than `new` inside a selector, to avoid losing injection and lifecycle support.

### 9.5. Annotations Activating Advisors/Proxies

Some `@Enable...` annotations turn on infrastructure `BeanPostProcessor`s, `Advisor`s, or proxies to apply behavior to managed beans. When designing this style, distinguish:

- **Import/registration** creates infrastructure definitions.
- **Post-processing/AOP** applies behavior to eligible beans/calls.
- **Method calls**: do they pass through the proxy (self-invocation)?
- **Proxy/post-processor count**: are they duplicated when multiple configs are imported?

Not every `@Enable...` annotation needs proxying. Pick infrastructure matching the capability you need rather than mimicking all of `@EnableCaching`'s internals.

## 10. ImportSelector, DeferredImportSelector, and ImportBeanDefinitionRegistrar

### 10.1. Regular ImportSelector

`ImportSelector.selectImports(AnnotationMetadata)` runs while Spring parses configuration. It returns `String[]` class names to import. It can select based on annotation attributes, `Environment`, or other bootstrap metadata; this fits the demo's scenario.

**Do not return bean names** like `"auditService"`. Return class names via `AuditServiceConfig.class.getName()`. For nested classes, JVM binary names include `$`; use `Class.getName()` to avoid formatting errors.

### 10.2. DeferredImportSelector

`DeferredImportSelector` is a variant that defers selection until a processing stage after regular configuration classes have been examined. This is a bootstrap mechanism, **not runtime reloading** or an async task. `DeferredImportSelector.Group` can coordinate multiple deferred selectors, useful in complex auto-configuration frameworks.

For an audit feature with BASIC/DETAILED, a regular selector suffices. Choose deferred only when specific ordering/aggregation is clearly justified.

### 10.3. ImportBeanDefinitionRegistrar

A registrar interacts directly with the bean definition registry. It allows creating bean names, types, and metadata not tied to fixed `@Bean` methods, though it is more complex and requires understanding the bean factory lifecycle.

A library `@Enable...` can use a registrar when registering adapter/proxy factories for interfaces declared on the annotation. Do not use a registrar just to avoid writing a clear configuration class.

### 10.4. Can These Mechanisms Be Combined?

Yes: a custom annotation can import a configuration class that imports a selector or registrar; a selector can also return a configuration containing `@Bean` methods and conditions. This creates a powerful import graph, though it can become very hard to debug.

Recommended practice: keep **one entry point, one selection rule, and one registration owner per bean**. Document the import graph and assert the final bean definition count in tests.

## 11. Integrating into Multi-Module Projects

A library should separate **public configuration API** from **implementation details**:

```text
audit-api/
  AuditSink.java
  AuditService.java
  EnableAudit.java               <-- public annotation
  AuditLevel.java                <-- public option

audit-spring/
  AuditImportSelector.java       <-- internal implementation
  BasicAuditConfig.java
  DetailedAuditConfig.java
  AuditServiceConfig.java

shop-app/
  ShopApplication.java           <-- uses @EnableAudit
```

This is an illustrative architectural layout; the actual build must ensure the annotation and selector/config classes are present on runtime dependencies. When splitting into multiple JARs, watch for dependency cycles: an annotation in the API module cannot reference `AuditImportSelector.class` in the implementation module if the implementation depends back on the API in a naive split. You can place the annotation in the Spring integration module, or separate contracts/entry points so dependencies remain acyclic.

In real modules, a cleaner structure is often:

```text
audit-contracts/
  AuditSink.java
  AuditService.java

audit-spring/
  EnableAudit.java
  AuditLevel.java
  AuditImportSelector.java
  configurations...

shop-app/
  ShopApplication.java
```

`audit-spring` depends on `audit-contracts`, and `shop-app` depends on both or receives transitive dependencies cleanly. `@EnableAudit` is public in `audit-spring`; consumers do not need to know internal configuration classes.

### 11.1. Keep Infrastructure Configs Out of Broad Component Scans

If imported configuration classes carry `@Configuration` and sit under a root package scanned by Spring Boot, they can be discovered **independently of the selector**. For example, if both `BasicAuditConfig` and `DetailedAuditConfig` are `@Configuration` classes under Boot's root package while `@EnableAudit` only selects one, the scanner may register both—causing duplicate bean names/types or leaving beans active even when disabled.

Design solutions:

- place internal module configurations outside the application scan root;
- prevent them from being component-scanned unless intentional;
- use explicit module imports or conditional auto-configuration;
- add integration tests using a real Spring Boot application context to verify no accidental registrations occur.

Do not confuse “class selected by selector” with “class never registered from any other path”.

### 11.2. Do Not Overuse the Same `@Enable` Across Multiple Configurations

If a context imports multiple configurations carrying `@EnableAudit` with **different levels**, the selector may receive incompatible requests. This is an API design decision: fail fast, apply precedence rules, or support multiple audit providers?

Do not rely on scan/import order to guess which config wins. For a capability allowing only one provider, establish a clear policy and avoid repeating `@Enable...` in different places within the same composition root.

### 11.3. Spring Boot Starters and Auto-Configuration

A reusable Spring Boot starter typically declares **auto-configuration** following the conventions/metadata of its Boot version, guarded by conditions on classpath, properties, and missing beans. Not every consumer needs to attach a custom `@Enable...`.

Custom `@Enable...` makes sense when users want **explicit opt-in**, have attributes expressing choices, or need an integration activated only on a specific configuration. Auto-configuration makes sense for plug-and-play behavior with strict conditional semantics. Both can coexist, provided you avoid registering the same capability twice.

## 12. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@EnableAudit` has no effect | Class carrying the annotation was not registered/imported/scanned by Spring | Verify the real configuration entry point |
| `selectImports` never runs | Missing `@Import` meta-annotation or invalid selector class | Check `@Target`, `@Retention`, imports, and classpath |
| Selector returns `"auditService"` | Returned a bean name instead of a class name | Return `AuditServiceConfig.class.getName()` |
| Reading metadata returns `null` | Wrong annotation type or selector was not invoked from the expected annotation | Check `EnableAudit.class.getName()` and the importing class |
| Casting `level` fails | Enum/attribute type mismatch | Use the exact `AuditLevel` and metadata accessor |
| `enabled=false` causes dependency errors | Consumer still registered while producer was excluded | Disable the whole module graph or use no-op/optional consumers |
| Both BASIC and DETAILED become beans | Another config scanned/imported both | Audit component scan roots and import graph |
| Duplicate bean name `auditSink` | Both provider configs were registered | Register only the chosen provider, or name them distinctly |
| `NoUniqueBeanDefinitionException` | Multiple `AuditSink` implementations of the same type | Use `@Qualifier`, `@Primary`, or clear module selection |
| Context lacks bean even though `@EnableAudit` ran | Imported config excluded by `@Profile`/`@Conditional` | Check profiles, conditions, and classpath |
| Property changes after `refresh` without changing behavior | Selection is a bootstrap decision | Design a separate runtime flag/facade if needed |
| Test calls `new AppConfig()` expecting beans | No Spring container processed the metadata | Create an `AnnotationConfigApplicationContext` |
| Using `@ImportResource` instead of `@Import` in custom annotation | Confusing XML resources with Java class imports | Use `@Import` for Java classes/selectors/registrars |
| Annotation stores String secrets | Secrets get compiled into class metadata | Use controlled secret providers/environment |
| Registrar collides with existing bean name | Duplicate registry keys or repeated execution | Check existence, naming policy, and module ownership |
| Custom `@Enable` slows startup | Selector performs I/O or scans overly broad packages | Keep selectors lightweight, import targeted configs, measure startup |
| Proxy feature skips self-calls | Standard Spring AOP self-invocation bypasses proxy | Design proper service boundaries; do not confuse with import |
| Two contexts give different results | Each context has its own registry/profiles/conditions | Inspect each context separately; do not assume JVM-wide singletons |

### 12.1. Evidence-Based Debugging Process

1. **Check the entry point:** which class initialized the context? Does it carry `@Enable...` directly or via meta-annotation?
2. **Trace the import graph:** which config, selector, or registrar does the annotation lead to? What exactly do they select/register?
3. **Check metadata:** are the types of `enabled`, `level`, and source annotations as expected?
4. **Inspect bean candidates:** after a successful context refresh, call `getBeanNamesForType(AuditSink.class)` and `getBeanNamesForType(AuditService.class)`.
5. **Verify disabled mode:** in section 8's design, both counts must be zero.
6. **Check extra configs:** are component scans, Boot auto-configs, profiles, or conditional declarations registering another provider?
7. **Read the exception root cause:** missing beans, duplicate names, and multiple type candidates are distinct errors; do not try to fix all of them with `@Primary`.
8. **Test both small contexts and real app contexts:** do not only unit-test the selector while ignoring how packaging/component scanning behaves in production.

## 13. Testing `@Enable...` Annotations Across Layers

### 13.1. Testing the Selector Contract

A unit test can inspect metadata for test configuration classes and verify the selected class-name array. Minimum cases:

| Annotation on Class | Expectation |
| --- | --- |
| `@EnableAudit` | BASIC config + service config |
| `@EnableAudit(level=DETAILED)` | DETAILED config + service config |
| `@EnableAudit(enabled=false)` | Empty import array |
| Annotation absent yet selector invoked directly | Clear metadata error |

If decision logic is extracted into a pure helper like `selectConfigs(boolean enabled, AuditLevel level)`, unit tests can verify branches quickly without spinning up a container. However, such tests do not verify the real `@Import` mechanism.

### 13.2. Integration Tests Must Verify Registry and DI

Example test using section 8's types:

```java
try (var context =
        new AnnotationConfigApplicationContext(
                EnableAuditDemo.DetailedApp.class)) {

    var sinkNames = context.getBeanNamesForType(
            EnableAuditDemo.AuditSink.class);
    var service = context.getBean(
            EnableAuditDemo.AuditService.class);

    if (sinkNames.length != 1) {
        throw new AssertionError("Expected one AuditSink");
    }
    if (!"detailed:checkout|trace".equals(
            service.report("checkout"))) {
        throw new AssertionError("Wrong audit implementation");
    }
}
```

This is a **test excerpt** using the demo's public nested types, not a standalone source file. Such a test verifies **annotation → import → bean definition → dependency injection → behavior**, rather than checking only that the selector returned the right class name.

### 13.3. Why Test Disabled Mode?

A feature working only when enabled is not safe enough. Disabling a feature can leave consumer beans with unsatisfied dependencies or auto-scanned components active. For `OFF`, verify:

- The context refreshes successfully.
- Zero `AuditSink` beans exist.
- Zero `AuditService` beans exist per the published contract.
- No scheduled tasks or side effects belonging to the capability remain if real implementations add infrastructure.
- No other auto-configuration unexpectedly re-enables auditing.

### 13.4. Testing Multiple Contexts Has Purpose

Creating separate BASIC, DETAILED, and OFF contexts prevents registry cross-contamination and keeps output deterministic. Spring singletons are not JVM-wide singletons; separate contexts can hold different instances/bean sets without conflict.

## 14. Practice Exercises and Answers

### Exercise 1 — When Is a Selector Needed?

A module has only a single `MetricsConfig`, no attributes, and does not vary with environment. Should you write an `ImportSelector`?

**Answer:** Not necessary. Using `@Import(MetricsConfig.class)` directly on a custom `@EnableMetrics` is simpler and clearer.

### Exercise 2 — What Makes an Annotation Actually Take Effect?

An `AppConfig` class carries `@EnableAudit` but is never registered/scanned/imported into any `ApplicationContext`. Will any audit beans exist?

**Answer:** Not from that annotation. Metadata does not activate itself outside a container; Spring must process the configuration class.

### Exercise 3 — Two Classes Imported When Enabled

The selector returns `BasicAuditConfig.class.getName()` but forgets `AuditServiceConfig.class.getName()`. Will `AuditService` be registered automatically?

**Answer:** Not via that selector. The basic config only creates `AuditSink`, while the service needs its own registration source. The module graph must be complete.

### Exercise 4 — OFF Mode Causing Errors

The selector returns an empty array when disabled, yet `AppConfig` declares a non-optional `@Bean CheckoutService checkoutService(AuditService service)`. What happens?

**Answer:** The context will fail due to a missing `AuditService` bean. You must disable the consumer too, use an optional dependency, or supply a no-op implementation per contract.

### Exercise 5 — Enum-Based Selection

With `@EnableAudit(level=DETAILED)` in the demo, how many `AuditSink` beans exist?

**Answer:** One, assuming no extra registrations. The selector picks only `DetailedAuditConfig` and `AuditServiceConfig`.

### Exercise 6 — Duplicate Bean Names

Both `BasicAuditConfig` and `DetailedAuditConfig` exist in one context due to another scanner, and both declare `@Bean auditSink()`. What is the risk?

**Answer:** Bean name collision/overriding or picking the wrong provider. Fix registration scope and avoid scanning internal configs outside the selector.

### Exercise 7 — Is `@AliasFor` Required for `level`?

Custom `@EnableAudit` has its own `AuditLevel level()`, read by the selector from metadata. Must `level` be aliased to `@Import.value`?

**Answer:** No. `@Import.value` accepts a class array, not `AuditLevel`. The `level` attribute is a dedicated input for the selector.

### Exercise 8 — Changing a Property While the Application Is Running

Does changing `audit.level=BASIC` to `DETAILED` after `ApplicationContext.refresh()` automatically swap the imported config?

**Answer:** No. Import decisions belong to bootstrap; runtime switching requires a different mechanism.

### Exercise 9 — Using `@EnableCaching` Without a CacheManager

An application declares `@EnableCaching` and `@Cacheable` on a managed bean without configuring an appropriate cache provider/manager. Should you assume caching works completely?

**Answer:** No. The annotation enables infrastructure, yet the infrastructure's own dependencies must still be satisfied. Verify cache configuration and actual calls.

### Exercise 10 — Difference Between Selector and Registrar

One library wants to choose between two `@Configuration` classes. Another library wants to register many bean definitions driven by annotation metadata. Which tool should each choose?

**Answer:** `ImportSelector` for selecting configuration classes; `ImportBeanDefinitionRegistrar` for dynamic low-level definition registration.

### Exercise 11 — Dependencies Between Factory Methods

`AuditServiceConfig` wants to use the `AuditSink` created by another config. Should it call `new BasicAuditSink()` directly inside the service method?

**Answer:** No, if you want the module selector to decide the implementation. Write `@Bean AuditService auditService(AuditSink sink)`; BeanFactory supplies the managed dependency.

### Exercise 12 — Scope of an Enable Annotation

Two independent `AnnotationConfigApplicationContext`s both use `@EnableAudit`. Must they share one JVM-wide `AuditSink` singleton?

**Answer:** No. Spring singleton scope applies within one container/BeanFactory; independent contexts have separate bean registries.

### Exercise 13 — Enabling Transactions via a Custom `@Enable`?

Someone creates `@EnablePayments` that only imports `PaymentServiceConfig` and expects every method to become transactional automatically. Is that right?

**Answer:** No. `@EnablePayments` in that design only imports bean definitions declared by the config. Transaction management requires dedicated infrastructure, a transaction manager, and proper interception/mechanisms; it does not appear merely from naming an annotation `Enable`.

### Exercise 14 — Module Public API

A library moves `DetailedAuditConfig` and `AuditImportSelector` to different packages between versions, while keeping `EnableAudit` and `AuditLevel` stable. Does the application need to know the new packages of those two internal classes?

**Answer:** Usually not, as long as the public entry point and contract remain stable and the library JAR/module ships the right classes. This is a primary benefit of a configuration facade annotation.

## 15. Checklist Before Releasing a Custom `@Enable...`

- Does the capability truly need an explicit enable annotation, or are `@Import`/`@Conditional` enough?
- Does the annotation have `@Target(TYPE)`, `@Retention(RUNTIME)`, `@Documented`, and the right `@Import`?
- Do attributes carry business meaning, clear names, sensible defaults, and compiler-checkable types?
- Do selectors/registrars perform only bootstrap work without instantiating business objects outside BeanFactory?
- When **enabled**, are all necessary producers/consumers/configurations registered consistently?
- When **disabled**, are any mandatory consumers left with missing dependencies?
- Could configs be accidentally scanned or auto-configured from another path?
- Does the selector return **fully qualified class names** and handle classpath/profiles/conditions?
- Are there bean name collisions or multiple candidates for the same interface?
- Do `@Bean`/constructor parameters express dependencies explicitly instead of calling config methods directly?
- Is the difference between a runtime toggle and bootstrap-time enabling clearly understood?
- Does the public API avoid exposing secrets or internal class names?
- Have you tested BASIC, DETAILED, and OFF modes and verified bean counts and behavior in a real Spring context?

## 16. Summary

The **`@Enable...`** pattern turns a set of configurations and extension points into a concise declarative API: users place one annotation on a configuration class, while the library uses **`@Import`** to register fixed configurations, select via **`ImportSelector`**, or register bean definitions through **`ImportBeanDefinitionRegistrar`** when needed.

Good design does more than make the annotation “work” when turned on; it keeps **enabled/disabled semantics, the dependency graph, bean ownership, and classpath boundaries** consistent. For simple use cases, import a fixed configuration; for attribute-driven choices, use a selector; for highly dynamic infrastructure registration, consider a registrar. Avoid building complex infrastructure merely to imitate a built-in Spring annotation.

**Final rule:** `@Enable...` is a decision made during **configuration processing**, not inherently a runtime switch. Every selected object still needs valid bean definitions, proper scopes/qualifiers, and management by BeanFactory.

### Official Spring Documentation

- [Spring Framework 6.2 — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Import.html).
- [Spring Framework 6.2 — `ImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ImportSelector.html).
- [Spring Framework 6.2 — `ImportBeanDefinitionRegistrar` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html).
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — `@EnableCaching` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/EnableCaching.html).
- [Spring Framework 6.2 — `@EnableAsync` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html).
- [Spring Framework 6.2 — `@EnableScheduling` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html).
- [Spring Framework 6.2 — `@EnableTransactionManagement` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html).
