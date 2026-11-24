# Selecting Configuration with `ImportSelector` in Spring Framework Core Container

## 1. The Problem: Same Application, Not Always the Same Configuration

An application might use in-memory storage during tests, a real connection in production, or enable a dedicated group of beans based on a configuration property. Always `@Import`ing every configuration class may force Spring to register multiple beans for the same interface—causing injection ambiguity—or initialize unnecessary components.

Consider two configuration classes:

```java
@Configuration(proxyBeanMethods = false)
class LocalShippingConfig {
    @Bean
    ShippingClient shippingClient() {
        return new LocalShippingClient();
    }
}

@Configuration(proxyBeanMethods = false)
class RemoteShippingConfig {
    @Bean
    ShippingClient shippingClient() {
        return new RemoteShippingClient();
    }
}
```

This is an **illustrative snippet**: types `ShippingClient`, `LocalShippingClient`, and `RemoteShippingClient` must be declared in the application. Both factory methods produce a bean of type `ShippingClient`, yet the application wants to **select the appropriate configuration** instead of importing both.

`org.springframework.context.annotation.ImportSelector` is an extension point for this purpose. A selector inspects the metadata of the class declaring `@Import`, chooses a list of classes to import, and returns their fully qualified class names. Spring continues processing those selected classes as import candidates.

Direct usage:

```java
@Configuration
@Import(ShippingConfigSelector.class)
class AppConfig {
}
```

In this example, `ShippingConfigSelector` is a class **implementing `ImportSelector`** responsible for choosing either `LocalShippingConfig` or `RemoteShippingConfig`. Spring does not automatically know which one to pick just because both classes exist on the classpath.

Lesson objectives:

- Master the contract of `ImportSelector` and `selectImports(AnnotationMetadata)`.
- Read annotation metadata, annotation attributes, and `Environment` to decide imports.
- Create custom `@Enable...` annotations working with `@Import(Selector.class)`.
- Distinguish selectors from static `@Import`, `@Conditional`, `@Profile`, `@ComponentScan`, `DeferredImportSelector`, and `ImportBeanDefinitionRegistrar`.
- Understand class selection timing versus bean instantiation timing and how to avoid collisions.
- Run a complete Java 17+ example with Spring Framework 6.2, including a property override case.
- Learn how to test, debug, handle missing configurations, and avoid common selector mistakes.

## 2. What Is `ImportSelector` and When Does Spring Call It?

`ImportSelector` is an interface in package `org.springframework.context.annotation`. Its central signature:

```java
public interface ImportSelector {
    String[] selectImports(AnnotationMetadata importingClassMetadata);
}
```

This is a **condensed** signature; the actual interface also has extension methods such as `getExclusionFilter()`. `AnnotationMetadata` belongs to `org.springframework.core.type`. A valid implementation must return an array of **fully qualified class names** of import candidates.

Minimal example:

```java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class FixedShippingSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] { LocalShippingConfig.class.getName() };
    }
}
```

This snippet is a **standalone illustration** (requiring `LocalShippingConfig`). It produces the same class selection result as `@Import(LocalShippingConfig.class)` while providing an extension point where more complex logic can be added later.

### 2.1. Processing Lifecycle

```text
@Configuration / custom @Enable... is registered
                         |
                         v
               ConfigurationClassParser
                         |
                         v
          Detects @Import(Selector.class)
                         |
                         v
            Instantiates ImportSelector
                         |
                         v
         Supplies Aware dependencies
          (for example EnvironmentAware)
                         |
                         v
     selectImports(AnnotationMetadata)
                         |
                  String[] FQCN
                         |
                         v
           Spring processes selected classes
                         |
            +------------+-------------+
            |                          |
            v                          v
   @Configuration classes       Regular component classes
            |                          |
            +------------+-------------+
                         |
                         v
                 Bean definitions
                         |
                         v
                 BeanFactory creates beans
              by DI, scope, and lifecycle
```

**Crucial distinction:** a selector chooses **class definitions participating in configuration**, rather than returning bean objects directly. Logic inside `selectImports` runs during configuration parsing, typically before business singletons are created.

Do not call `new ShippingClient()` inside `selectImports` expecting it to become a managed bean. Registering bean definitions and instantiating objects must be done by Spring via the imported classes or an appropriate extension point.

### 2.2. Return Values Must Be Class Names

Right:

```java
return new String[] {
    LocalShippingConfig.class.getName(),
    MetricsConfig.class.getName()
};
```

Wrong:

```java
return new String[] { "shippingClient", "localShippingConfig" };
```

Both snippets are **illustrative code**; `MetricsConfig` must exist for the first one to compile. Array elements must be valid class names such as `com.example.config.LocalShippingConfig`, not Spring bean names or XML resource paths. For nested classes, using `Class.getName()` is more reliable than typing dot-separated names manually, because Java binary names of nested classes contain `$`.

If nothing needs to be imported, return an empty array:

```java
return new String[0];
```

Do not return `null` to express “no imports”: the method contract expects an array. An empty array is clear and prevents unexpected processing errors.

### 2.3. Which Class Types Can ImportSelector Choose?

Classes returned by a selector are processed by Spring according to `@Import` semantics:

- `@Configuration` classes containing `@Bean` factory methods;
- regular component classes with suitable constructors;
- other class types supported by Spring's import parser in advanced scenarios.

In most application code, a selector should return **configuration class names**, selecting a cohesive package of bean definitions that can be tested and managed as a module. An overly complex selector returning dozens of implementation classes without a clear contract is harder to maintain than configuration entry points.

## 3. `AnnotationMetadata`: Reading Metadata Without Instantiating Configuration Classes

The `importingClassMetadata` parameter provides metadata for **the class declaring or indirectly carrying `@Import`**, not an already-instantiated configuration bean object.

Example:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(ShippingConfigSelector.class)
public @interface EnableShipping {
    String mode() default "local";
}
```

And in the application:

```java
@Configuration
@EnableShipping(mode = "remote")
class AppConfig {
}
```

These are illustrative snippets; imports from `java.lang.annotation` and Spring, plus the selector implementation, are required. With `AnnotationMetadata` passed to the selector, Spring can inspect the `mode` attribute without instantiating `AppConfig`.

### 3.1. Reading Custom Annotation Attributes

```java
@Override
public String[] selectImports(AnnotationMetadata metadata) {
    Map<String, Object> attributes =
            metadata.getAnnotationAttributes(EnableShipping.class.getName());

    if (attributes == null) {
        throw new IllegalStateException("@EnableShipping is missing");
    }

    String mode = (String) attributes.get("mode");
    return switch (mode) {
        case "local" -> new String[] { LocalShippingConfig.class.getName() };
        case "remote" -> new String[] { RemoteShippingConfig.class.getName() };
        default -> throw new IllegalArgumentException("Unsupported mode: " + mode);
    };
}
```

This is an **illustrative excerpt**, not standalone. `Map` requires `java.util.Map`, and the config classes must exist.

Distinguish carefully:

- `metadata.getClassName()`: class name of the **importing configuration class**.
- `metadata.hasAnnotation(...)` / `metadata.hasMetaAnnotation(...)`: inspect annotation metadata via the corresponding APIs.
- `metadata.getAnnotationAttributes(...)`: retrieve attributes of the specified annotation.
- Class names returned by `selectImports`: **imported configuration/component classes**, which can be completely different from the input metadata class name.

When `@EnableShipping` is a composed annotation carrying `@Import`, metadata reads the attributes of `@EnableShipping` on the annotated class. You can use `AnnotationAttributes` when you want typed accessors or complex metadata handling; the runnable example in section 8 uses an enum and explicit cast to avoid ambiguity.

### 3.2. Class Metadata Is Not a Bean Factory

You cannot treat `importingClassMetadata` as an `ApplicationContext` to look up `@Bean` instances. At this stage, Spring is still selecting which classes form the configuration graph. When configuration details are needed, prefer environment/properties and annotation metadata rather than looking up business singletons that may not exist yet.

**Do not rely on calling a configuration class constructor** from a selector to “read annotation attributes”: constructors may involve dependency injection, side effects, or container-managed lifecycles. Metadata avoids that.

## 4. Receiving `Environment`, `BeanFactory`, and Other Infrastructure Dependencies

According to the Spring Framework 6.2 Javadoc, an `ImportSelector` can receive certain container infrastructure **before** `selectImports(...)` is invoked, for example via Aware interfaces:

- `EnvironmentAware`;
- `BeanFactoryAware`;
- `BeanClassLoaderAware`;
- `ResourceLoaderAware`.

Spring also supports constructor injection with a single constructor accepting suitable infrastructure parameter types such as `Environment`, `BeanFactory`, `ClassLoader`, or `ResourceLoader`, per the documented API.

### 4.1. `EnvironmentAware` Selecting by Property

```java
public final class ShippingConfigSelector
        implements ImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        String mode = environment.getProperty(
                "shipping.provider", "local");

        return switch (mode) {
            case "local" ->
                    new String[] { LocalShippingConfig.class.getName() };
            case "remote" ->
                    new String[] { RemoteShippingConfig.class.getName() };
            default ->
                    throw new IllegalArgumentException("Invalid provider: " + mode);
        };
    }
}
```

This is an **illustrative snippet** (`EnvironmentAware` and `Environment` come from `org.springframework.context` / `org.springframework.core.env`). Properties can come from system properties, environment variables, or a `PropertySource` registered appropriately before parsing. The logic above throws a clear error for invalid values instead of silently falling back to an unintended provider.

**Avoid calling `BeanFactory.getBean(...)` inside a selector** just to branch on a business bean. Configuration is still being built; eager lookups can trigger circular dependencies, missing bean definitions, or premature initialization. If the decision only depends on `dev/prod`, a config feature flag, or an annotation attribute, `Environment`/metadata is much better suited.

### 4.2. Which Source Takes Priority?

When supporting both annotation attributes and environment properties, define an explicit policy. Example policy:

1. The attribute in `@EnableShipping(channel=STANDARD)` supplies the default value.
2. Property `lesson.shipping.channel`, if set to `standard` or `express`, **overrides** the attribute.
3. Property value `annotation` means keep the annotation value as-is.
4. Any other value raises a configuration error instead of silently falling back to STANDARD.

This policy is demonstrated by the complete program in section 8. Another application might decide that the annotation always wins over properties; what matters is that the rule is documented, tested, and consistent across environments.

## 5. Custom `@Enable...` Annotations: Reusable Configuration Composition

Many Spring APIs are organized around `@EnableXxx`: users just place an annotation on a configuration class, while the library implements a selector/registrar to add the needed bean definitions.

Example:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(ShippingConfigSelector.class)
public @interface EnableShipping {
    Channel channel() default Channel.STANDARD;
}
```

Here:

- `@Target(ElementType.TYPE)` allows placing it on classes;
- `@Retention(RetentionPolicy.RUNTIME)` retains annotation metadata at runtime;
- `@Documented` includes the annotation in the Javadoc of classes using it;
- `@Import(ShippingConfigSelector.class)` provides the import processing hook;
- `channel` is the public attribute for configuring the application.

The caller simply writes:

```java
@Configuration(proxyBeanMethods = false)
@EnableShipping(channel = Channel.EXPRESS)
class CheckoutConfig {
}
```

This gives a **concise configuration API**: client modules do not have to remember the names of internal classes like `ExpressShippingConfig` and `StandardShippingConfig`.

### 5.1. Avoid Exposing Implementation Details in Annotations

An annotation like `@EnableShipping(channel=EXPRESS)` expresses a business/configuration decision more clearly than asking callers to write `@Import(ExpressShippingConfig.class)` from an internal package. When implementations change, the library can change how the selector maps enum → config class without forcing applications to refactor multiple imports.

Still, do not wrap every pair of configuration classes in a custom annotation. If an application only imports one fixed configuration in one place, `@Import(MyConfig.class)` is simpler and easier to follow.

### 5.2. Enum Names and Versioning

If a public annotation defines `Channel.STANDARD` and `Channel.EXPRESS`, adding, removing, or renaming enum constants affects source compatibility and runtime policy. Never silently pick a “close enough” fallback on unknown enum/property values; instead report a clear error and provide a proper migration path.

## 6. How `ImportSelector` Differs from Common Configuration Alternatives

| Mechanism | Selection Condition | What Does It Produce? | When It Fits |
| --- | --- | --- | --- |
| `@Import(AConfig.class)` | Fixed in source | Imports the specific configuration class | Static configuration composition, few branches |
| `ImportSelector` | Code chooses based on annotation metadata, environment, etc. | Class names for Spring to continue importing | Custom `@Enable...`, module/config selection |
| `@Profile` | Active profiles | Enables/disables config or bean definitions | Environment-specific configurations |
| `@Conditional` | `Condition.matches(...)` | Enables/disables config/bean conditionally | Local conditional rules |
| `@ComponentScan` | Package roots and filters | Discovers component candidates | Groups of components in an application area |
| `ImportBeanDefinitionRegistrar` | Registry-level logic | Registers bean definitions directly | Complex framework extensions |
| `DeferredImportSelector` | Selection at deferred processing stage | Classes imported after regular configs are processed | Auto-configuration/advanced selector groups |

### 6.1. When Is `@Profile` Enough?

If an application merely wants bean A in `dev` and bean B in `prod`, two `@Configuration` classes annotated with `@Profile("dev")` and `@Profile("prod")` can be simpler than writing a selector. However, ensure exactly one configuration is activated when the dependency is required.

`ImportSelector` fits better when selection depends on more than a profile: for instance, an annotation with multiple attributes, choosing among multiple implementation modules, or a library exposing a public `@Enable...` API.

### 6.2. When Is `@Conditional` Simpler?

`@Conditional(SomeCondition.class)` evaluates a condition to skip or keep a bean/configuration. It does not need to return other class names. If the task is “register bean X when condition holds”, conditionals are usually more concise than a selector. If the task is “based on a choice, import **an entire matching configuration class**”, a selector can be clearer.

### 6.3. `@Import` Does Not Scan Packages Automatically

`@Import(ShippingConfigSelector.class)` does not turn every class in the selector's package into a bean. Spring only processes the returned classes and any registrations/imports hanging off those classes. If a selected configuration contains `@ComponentScan`, that scan itself may bring multiple components into the registry; the actual scope therefore depends on the chosen configuration.

### 6.4. ImportSelector Selects Classes, Not All Bean Candidates

Suppose a selector picks `RemoteShippingConfig`, yet the application also defines `@Bean ShippingClient localClient()` from another source. When a service injects a single `ShippingClient`, there will still be two candidates and `NoUniqueBeanDefinitionException` can occur without an explicit choice.

Selectors help prevent redundant imports, **not replace** `@Qualifier`, `@Primary`, bean naming, or proper dependency design.

## 7. `DeferredImportSelector` and Advanced Extension Points

`DeferredImportSelector` extends `ImportSelector` but is processed **after** all regular `@Configuration` classes have been examined by the parser, rather than immediately in normal selector order. It is useful when imported configurations must be selected only after fuller information about the configuration set is available.

Minimal example:

```java
public class LateShippingSelector implements DeferredImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] { StandardShippingConfig.class.getName() };
    }
}
```

This is an **illustrative snippet** (requiring `DeferredImportSelector`, `AnnotationMetadata`, and the config class). To use it, place `@Import(LateShippingSelector.class)` on a configuration class. Deferred does not mean “wait until the app is running to add beans dynamically” or “create beans asynchronously”; it only changes **when imports are processed during bootstrap**.

### 7.1. `DeferredImportSelector.Group`

Deferred selectors can be grouped to coordinate processing order/policy via the `DeferredImportSelector.Group` interface. A group receives selectors and metadata and provides import entries. This is a framework-level tool; you do not need a custom group just to pick STANDARD/EXPRESS in a small application.

**In particular:** import selector processing order **is not** singleton bean initialization order. If bean B needs bean A, declare the dependency via constructor/factory-method parameters; `@Order` on selectors or import order does not replace the dependency graph.

### 7.2. `getExclusionFilter()`

`ImportSelector` has a default `getExclusionFilter()` method returning a predicate used to exclude class candidates from import sets under Spring's rules, which can apply transitively to classes found through the selector's imports. This is an advanced feature allowing a selector to exclude class names during import processing; it is **not** a global component-scan exclude filter for the whole application.

If you just need to choose one of two configs, returning an array with that single class name is far easier to verify than using an exclusion filter to import broadly and filter down.

### 7.3. What Does `ImportBeanDefinitionRegistrar` Do Differently?

A registrar interacts directly with `BeanDefinitionRegistry` to register definitions, typically used in libraries building dynamic infrastructure beans. In contrast, a selector only returns class names for Spring to process via `@Import`.

If the requirement is “based on `channel`, select a `@Configuration` containing `@Bean` methods”, a selector is the right tool. If the requirement is “register a dynamic set of bean definitions with highly customized types, bean names, and metadata derived from annotation attributes”, a registrar may fit better, though it is harder to implement and test.

## 8. Complete Java 17+ Example: Selecting Shipping Configuration

This program runs on **Spring Framework 6.2.19**, requiring no Spring Boot or server. It demonstrates:

1. `@EnableShipping(channel=STANDARD)` selects `StandardShippingConfig`.
2. `@EnableShipping(channel=EXPRESS)` selects `ExpressShippingConfig`.
3. Property `lesson.shipping.channel=express` overrides the STANDARD attribute, selecting EXPRESS.
4. Without `@EnableShipping`, no `Carrier` bean exists unless registered elsewhere.
5. Each context has exactly **one** `Carrier` bean; `CheckoutService` receives it via a parameterized `@Bean` method.

### 8.1. Structure

```text
spring-import-selector-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ImportSelectorDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-import-selector-demo'
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
    mainClass = 'ImportSelectorDemo'
}
```

Use JDK 17+ and a compatible Gradle version. `spring-context` brings along `spring-beans` and `spring-core` required for `ImportSelector`, metadata, `EnvironmentAware`, and `AnnotationConfigApplicationContext`.

### 8.2. Full Java Code

Create `src/main/java/ImportSelectorDemo.java`:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Locale;
import java.util.Map;

import org.springframework.context.EnvironmentAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.type.AnnotationMetadata;

public class ImportSelectorDemo {

    public enum Channel {
        STANDARD, EXPRESS
    }

    public interface Carrier {
        String code();
        int surcharge();
    }

    public record StandardCarrier() implements Carrier {
        @Override
        public String code() {
            return "standard";
        }

        @Override
        public int surcharge() {
            return 5;
        }
    }

    public record ExpressCarrier() implements Carrier {
        @Override
        public String code() {
            return "express";
        }

        @Override
        public int surcharge() {
            return 20;
        }
    }

    public record CheckoutService(Carrier carrier) {
        public int total(int subtotal) {
            return subtotal + carrier.surcharge();
        }
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Import(ShippingSelector.class)
    public @interface EnableShipping {
        Channel channel() default Channel.STANDARD;
    }

    public static class ShippingSelector
            implements ImportSelector, EnvironmentAware {

        private Environment environment;

        @Override
        public void setEnvironment(Environment environment) {
            this.environment = environment;
        }

        @Override
        public String[] selectImports(
                AnnotationMetadata importingClassMetadata) {

            Map<String, Object> attributes =
                    importingClassMetadata.getAnnotationAttributes(
                            EnableShipping.class.getName());

            if (attributes == null) {
                throw new IllegalStateException(
                        "@EnableShipping is required");
            }

            Channel channel = (Channel) attributes.get("channel");

            String configured = environment.getProperty(
                    "lesson.shipping.channel", "annotation");
            switch (configured.toLowerCase(Locale.ROOT)) {
                case "annotation" -> {
                    // Keep value from @EnableShipping.
                }
                case "standard" -> channel = Channel.STANDARD;
                case "express" -> channel = Channel.EXPRESS;
                default -> throw new IllegalArgumentException(
                        "Unsupported shipping channel: " + configured);
            }

            Class<?> selected = channel == Channel.EXPRESS
                    ? ExpressShippingConfig.class
                    : StandardShippingConfig.class;
            return new String[] { selected.getName() };
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class StandardShippingConfig {
        @Bean
        Carrier carrier() {
            return new StandardCarrier();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExpressShippingConfig {
        @Bean
        Carrier carrier() {
            return new ExpressCarrier();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableShipping(channel = Channel.STANDARD)
    public static class StandardAppConfig {
        @Bean
        CheckoutService checkoutService(Carrier carrier) {
            return new CheckoutService(carrier);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableShipping(channel = Channel.EXPRESS)
    public static class ExpressAppConfig {
        @Bean
        CheckoutService checkoutService(Carrier carrier) {
            return new CheckoutService(carrier);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PlainAppConfig {
        // No @Import or @EnableShipping.
    }

    private static void run(
            String name, Class<?> appConfig, String selectedProperty) {

        try (var context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "lesson-case",
                            Map.of("lesson.shipping.channel",
                                    selectedProperty)));

            context.register(appConfig);
            context.refresh();

            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            System.out.println(name + ": carrier=" +
                    checkout.carrier().code() +
                    ", total=" + checkout.total(100));
            System.out.println(name + ": carrierCount=" +
                    context.getBeanNamesForType(Carrier.class).length);
        }
    }

    public static void main(String[] args) {
        run("STANDARD", StandardAppConfig.class, "annotation");
        run("EXPRESS", ExpressAppConfig.class, "annotation");
        run("OVERRIDE", StandardAppConfig.class, "express");

        try (var plain =
                new AnnotationConfigApplicationContext(PlainAppConfig.class)) {
            System.out.println("PLAIN: carrierCount=" +
                    plain.getBeanNamesForType(Carrier.class).length);
        }
    }
}
```

This is a complete Java file: `ImportSelectorDemo` is the top-level public class; the interfaces, enum, records, annotation, selector, and configuration classes are declared as nested types. `Class.getName()` returns the exact JVM name of the nested configs, so the selector never has to assemble class names manually.

`ShippingSelector` does not instantiate `Carrier` with `new`; it only decides which **configuration class** to import. Spring then processes `@Bean Carrier carrier()` on the chosen config. `CheckoutService` receives `Carrier` from the container via method parameter injection.

### 8.3. Running the Program

In the `spring-import-selector-demo` directory:

```bash
gradle run --quiet
```

If Gradle Wrapper is present, use `./gradlew run --quiet` on Linux/macOS or `.\gradlew.bat run --quiet` on Windows PowerShell.

**Stdout printed by the program itself:**

```text
STANDARD: carrier=standard, total=105
STANDARD: carrierCount=1
EXPRESS: carrier=express, total=120
EXPRESS: carrierCount=1
OVERRIDE: carrier=express, total=120
OVERRIDE: carrierCount=1
PLAIN: carrierCount=0
```

The lines above are produced by `System.out.println`; if the environment configures additional logging, Gradle/Spring may display extra information.

### 8.4. Analyzing Each Case

**STANDARD:** `StandardAppConfig` carries `@EnableShipping(channel=STANDARD)`. Property `lesson.shipping.channel=annotation` preserves the annotation value, so the selector returns `StandardShippingConfig`. Spring registers the `Carrier` bean from that config's factory method. The surcharge is 5, totaling 100 + 5 = 105.

**EXPRESS:** `ExpressAppConfig` carries `@EnableShipping(channel=EXPRESS)` and the property remains `annotation`. The selector returns `ExpressShippingConfig`, registering `ExpressCarrier` with surcharge 20. The total equals 120.

**OVERRIDE:** Same `StandardAppConfig` class as STANDARD, except the property is set to `express` before `register` and `refresh`. The selector receives `Environment`, reads the property, and chooses EXPRESS instead of the STANDARD annotation. Configuration and dependent beans are decided while building the context, not deferred until `checkout.total(...)` is called.

**PLAIN:** `PlainAppConfig` has no `@EnableShipping`, and neither imports nor scans `Carrier`. Thus `getBeanNamesForType(Carrier.class)` returns an empty array. It also does not declare `CheckoutService`, avoiding creating a consumer that unconditionally requires a Carrier.

**carrierCount = 1:** In each context using the selector, only one of the two shipping configurations is imported. That is why there is no `Carrier` type ambiguity in the example. If the application has another source declaring `Carrier`, the count can be higher; the selector does not automatically remove independent bean definitions.

### 8.5. Why Use `MapPropertySource` Instead of Mutating JVM-Wide System Properties?

`MapPropertySource` is added to **each context's** `Environment` before parsing. This keeps the example's output deterministic without altering shared `System.setProperty` state that might affect other tests. `addFirst(...)` places the property source at the highest precedence in the created context.

In real projects, you can use environment variables, system properties, or config files loaded by Spring/Boot at the right time. Keep in mind that the selector reads the value **while configuration is being parsed**: changing a property after context refresh generally **does not re-run `selectImports`** and does not replace existing bean definitions.

## 9. Designing Safe Configuration Selection

### 9.1. Select Only the Imports Needed

If configurations have factory methods sharing the bean name `carrier`, importing both `StandardShippingConfig` and `ExpressShippingConfig` into the same context is a different design from selecting one of the two. Depending on bean definition overriding policy, a conflict or silent override may happen.

The selector in section 8 returns **a single** config name to express “one active channel”. Do not rely on import ordering as a default mechanism to pick a provider.

### 9.2. Fail Fast on Invalid Configuration

If the property receives a value outside `annotation`, `standard`, `express`—such as `slow`—the example throws `IllegalArgumentException` during configuration parsing. This is intentional: a typo in configuration is an error that should be reported clearly rather than silently switching to another provider.

```java
default -> throw new IllegalArgumentException(
        "Unsupported shipping channel: " + configured);
```

This is an excerpt from the selector in section 8, not a standalone file.

If a feature is genuinely optional, the selector can return an empty array when disabled by a flag. Still, check consumers: a `CheckoutService` bean that unconditionally requires `Carrier` will still fail dependency resolution if the selector registers no carrier. For a fully optional module, pair it with conditional consumer configuration or an appropriate optional dependency policy.

### 9.3. Predictable Selection Precedence

Clearly document which attribute or property wins. In section 8's code, property override is evaluated **after** the annotation. If users only read the annotation and do not know a property override exists, runtime behavior can surprise them. Consider recording the selected option in startup structured logs or configuration metrics, while never logging secrets such as credentials.

### 9.4. Avoid Side Effects in Selectors

Avoid doing the following inside `selectImports(...)`:

- calling HTTP APIs to decide which class to import;
- querying databases or uninitialized business beans;
- writing files or mutating global state;
- spawning threads/timers to pick configuration;
- instantiating beans manually and caching them in selector fields;
- picking classes randomly or by time without stable configuration.

Selection should be **lightweight, deterministic, and driven by metadata/environment** so the application starts fast, tests are reproducible, and no bootstrap-time circular dependencies arise.

### 9.5. Classpath and Module Dependencies

When a selector returns a class name, that class must exist on the runtime classpath and be loadable by the active classloader. If a selector returns `com.vendor.OptionalStorageConfig` when the corresponding module/JAR is absent, the context can fail during import processing. For optional integrations, inspect classpath/environment deliberately before selecting, or use `@ConditionalOnClass` in Spring Boot auto-configuration per standard convention.

Do not call `Class.forName(...)` indiscriminately to initialize every class before deciding: loading classes can have side effects. For straightforward applications, explicit dependencies and enum → config class mapping are enough.

### 9.6. Bean Names, Scopes, and Qualifiers Still Matter

`@ImportSelector` does not invent new singleton rules, does not automatically make beans lazy, and does not attach `@Primary` to the chosen configuration. Once the class is imported, `@Bean`, `@Scope`, `@Lazy`, `@Qualifier`, `@Profile`, and related conditions operate as normal.

If two independent configurations share an interface and only one is selected, injection by type is usually simple. However, if another `Carrier` bean is registered via component scanning, the selector does not automatically guarantee uniqueness. Audit the entire registry.

## 10. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `selectImports` returns `"shippingClient"` | Confusing Spring bean name with fully qualified class name | Return `ShippingConfig.class.getName()` |
| Selector is never called | Class with `@Import`/`@Enable...` is not registered or annotation has wrong target | Verify configuration entry point and meta-annotations |
| `attributes == null` | Selector attached to a class lacking the `@EnableShipping` it expects | Inspect metadata and annotation declarations |
| Wrong type cast on enum attribute | Assuming attribute is a String when declared as an enum | Use the exact enum type or `AnnotationAttributes` |
| Property changes after `refresh()` but bean does not change | Selector chooses classes during parsing/bootstrap, not re-run automatically | Create a new context or use a dedicated runtime switching mechanism |
| Two `Carrier` beans exist even though selector picked one | Another registration path also creates a Carrier | Search for all related `@Bean`/`@ComponentScan`/`@Import` declarations |
| `NoSuchBeanDefinitionException` when selector returns empty array | Consumer still requires a mandatory dependency | Use optional dependencies or conditional consumer configuration |
| Returned class does not exist | Wrong binary name/FQCN or missing JAR | Use `SelectedConfig.class.getName()` and verify runtime classpath |
| Selector fetches business beans too early | Import processing runs before the context finishes initializing | Read only metadata/environment or supported bootstrap infrastructure |
| Both `@Profile` and selector used, bean disappears | Selected configuration is further filtered out by profile/conditions | Check active profiles and conditions |
| Confusing `@ImportSelector` with `@ComponentScan` | Selector only picks classes; it does not scan packages | Use the right mechanism for the job |
| Confusing selector with registrar | Selector does not directly register arbitrary bean definitions | Use `ImportBeanDefinitionRegistrar` if registry APIs are truly needed |
| Using `DeferredImportSelector` for simple needs | Adds ordering/group complexity with no benefit | Start with regular `ImportSelector` |
| Hardcoding nested class names with dots | JVM binary name of nested classes uses `$` | Use `Class.getName()` |
| Adding `@Order` expecting it to control bean init order | Import selection order does not replace the dependency graph | Express DI or `@DependsOn` appropriately |
| Choosing configuration randomly or by clock | Context is hard to reproduce, tests become flaky | Select from stable config inputs |
| Imported config gets scanned/imported a second time | Overlapping bean definition sources | Audit import graph, scanners, bean naming, and overriding policy |

### 10.1. Six-Step Diagnostic Process

1. **Confirm the selector runs:** which configuration class carries `@Import` or `@EnableShipping`, and was that class actually registered with the context?
2. **Check metadata:** are the annotation name and attribute types exact? Could `metadata.getAnnotationAttributes(...)` return `null`?
3. **Check environment:** were property sources added **before refresh**, and what is their precedence order?
4. **Check returned class names:** use `Class.getName()` and ensure the classes are on the runtime classpath.
5. **Inspect final bean definitions:** if the context starts, use `getBeanNamesForType(...)` to inspect beans from the chosen configuration; if the context fails, read the root cause instead of querying an unstarted context.
6. **Check consumers:** do dependent beans match the actual number of candidates? If no provider was selected, a mandatory consumer cannot work on its own.

## 11. Testing Selectors Without Spinning Up the Entire Application

There are two distinct testing levels.

### 11.1. Unit-Testing Selection Logic

If rules depend only on an enum and a property, extract config selection logic into a pure method taking explicit inputs; unit tests can verify:

| Annotation channel | Property | Selected Class |
| --- | --- | --- |
| STANDARD | annotation | StandardShippingConfig |
| EXPRESS | annotation | ExpressShippingConfig |
| STANDARD | express | ExpressShippingConfig |
| EXPRESS | standard | StandardShippingConfig |
| STANDARD | unknown value | Throws configuration error |

Unit tests do not need to create a Spring context. However, they do not prove that `@Bean` definitions are actually registered; integration tests are needed for that.

### 11.2. Integration-Testing with a Small Context

The section 8 example creates three contexts with different selections. A similar test can use assertions:

```java
try (var context = new AnnotationConfigApplicationContext()) {
    context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource(
                    "test", Map.of("lesson.shipping.channel", "express")));
    context.register(StandardAppConfig.class);
    context.refresh();

    Carrier carrier = context.getBean(Carrier.class);
    if (!"express".equals(carrier.code())) {
        throw new AssertionError("Expected express carrier");
    }
    if (context.getBeanNamesForType(Carrier.class).length != 1) {
        throw new AssertionError("Expected exactly one Carrier");
    }
}
```

This is an **excerpt** using the nested types `StandardAppConfig` and `Carrier` from `ImportSelectorDemo`; when placed in another class, full type names/imports are needed. Assertions catch regressions instead of relying on manual stdout inspection. You can expand tests to cover the invalid property branch, missing provider case, and collision with another `Carrier`.

### 11.3. Why Should Each Test Have Its Own Context?

An `ApplicationContext` processes bean definitions during initialization. If you want to test two different configurations, create **two separate contexts** rather than mutating a property and expecting the same context to drop old beans and import a new config. This keeps tests independent, avoids state leaks, and mirrors actual import selection timing.

## 12. Self-Check Exercises with Answers

### Exercise 1 — Class Name or Bean Name?

`selectImports(...)` returns `new String[]{"expressCarrier"}`, which is the bean name of `@Bean Carrier expressCarrier()`. Does this satisfy the contract?

**Answer:** No. It must return class names to import, such as `ExpressShippingConfig.class.getName()`. Bean names are only determined when Spring processes the selected class/config.

### Exercise 2 — Selection via Attribute

`@EnableShipping(channel=EXPRESS)` and property `lesson.shipping.channel=annotation`. Which class does the section 8 selector return?

**Answer:** `ExpressShippingConfig`, because the `"annotation"` property means preserving the EXPRESS enum attribute.

### Exercise 3 — Property Overriding Annotation

`@EnableShipping(channel=STANDARD)`, property `lesson.shipping.channel=express`. What is the result?

**Answer:** `ExpressShippingConfig`. Property takes higher precedence than the attribute in the example.

### Exercise 4 — Missing Feature

The selector returns an empty array, while `CheckoutService` has a factory method requiring a mandatory `Carrier carrier` parameter. Will the context always refresh successfully?

**Answer:** No. Without a `Carrier` bean from another source, creating `CheckoutService` will fail due to a missing dependency. You must design optional/conditional consumers accordingly.

### Exercise 5 — One Context, Two Different Modules

The selector imports only `StandardShippingConfig`, but `AppConfig` also has `@Import(ExpressShippingConfig.class)`. Is there guaranteed to be exactly one `Carrier`?

**Answer:** No. The other import still adds bean definitions. The two configs can collide on bean names or produce multiple beans of the same type, causing conflicts/ambiguity depending on design.

### Exercise 6 — ImportSelector or `@Profile`?

An application has `DevConfig` and `ProdConfig` differing only between dev and prod environments, with no custom annotation attributes. Must you write an `ImportSelector`?

**Answer:** No. `@Profile` or conditional configuration can be simpler. Use `ImportSelector` when class selection relies on extension-style logic/metadata.

### Exercise 7 — Metadata

Inside `ShippingSelector`, does `metadata.getClassName()` return `ExpressShippingConfig`?

**Answer:** Not necessarily, and that is not the semantics of the method. It describes the **importing class**, such as `ExpressAppConfig`; the selected class goes into the array returned from `selectImports`.

### Exercise 8 — Static Inner Config

In section 8's example, `StandardShippingConfig` is a nested class. Why is `StandardShippingConfig.class.getName()` better than typing `"ImportSelectorDemo.StandardShippingConfig"`?

**Answer:** Because the JVM binary name of a nested class contains `$`; `Class.getName()` returns the exact identifier Spring needs to load it and avoids stale string names during refactoring.

### Exercise 9 — DeferredImportSelector

Do you need `DeferredImportSelector` to make Spring wait until the first HTTP request before choosing a provider?

**Answer:** No. Deferred only defers import processing during bootstrap; it does not dynamically choose beans per request. Runtime switching requires a separate service/routing abstraction.

### Exercise 10 — EnvironmentAware

`ShippingSelector` implements `EnvironmentAware`. When does Spring invoke `setEnvironment(...)` relative to `selectImports(...)`?

**Answer:** Per the contract, Aware callbacks run before the selector makes its choice. This allows the selector to read properties from `Environment`.

### Exercise 11 — Selecting Multiple Configurations

Can you return an array containing both `MetricsConfig.class.getName()` and `ShippingConfig.class.getName()`?

**Answer:** Yes, provided both classes exist and do not cause unintended bean definition collisions. `ImportSelector` is not limited to one class; the shipping example picks one to ensure exactly one `Carrier`.

### Exercise 12 — Testing Two Modes in the Same Container

A test builds a context with STANDARD, calls `context.getEnvironment().getPropertySources().addFirst(...)` to switch to EXPRESS **after refresh**, and checks `Carrier`. Will Spring automatically swap the existing `Carrier`?

**Answer:** No. Import selection already happened during configuration processing; changing a property after refresh does not automatically re-evaluate the import graph. Create a separate context to compare bootstrap behavior.

## 13. Checklist for Designing an ImportSelector

- Is the annotation/`@Import` placed on a class known to Spring?
- Does `selectImports` return **fully qualified class names** (and an empty array when importing nothing), never bean names?
- Are selection inputs coming clearly from metadata/`Environment` with a documented precedence policy?
- Does the selector avoid side effects, I/O, and eager lookups of business beans?
- Are all potentially selected classes present on the runtime classpath or properly guarded upfront?
- Have you ensured two configuration implementations for a single dependency are not accidentally imported together?
- Do imported beans have valid constructor/factory dependencies and qualifiers?
- Could `@Conditional`/`@Profile` on imported configs cause an expected bean to disappear?
- Have you distinguished regular `ImportSelector` from `DeferredImportSelector` and registrars?
- Are there integration tests for every branch plus invalid configuration values?
- Are post-refresh property changes mistakenly treated as config-reloading mechanisms?
- Have you verified real context bean definitions rather than only unit-testing the selector method?

## 14. Summary

`ImportSelector` lets you **select which classes enter the Spring configuration graph** based on `AnnotationMetadata` and infrastructure inputs such as `Environment`. Its `selectImports(...)` method returns an **array of fully qualified class names**, not bean instances or bean names. Spring then processes the selected classes to register bean definitions and instantiate managed beans under normal dependency-graph, scope, and lifecycle rules.

Using `@Import(Selector.class)` directly or wrapping it inside a custom `@Enable...` annotation provides a clean module configuration API. `@Conditional`/`@Profile` suit simple on/off conditions; `DeferredImportSelector` handles late-phase parsing selection, not per-request configuration switching. **Making decisions at bootstrap** is different from **runtime routing**: if providers must switch while the app is running, design a service abstraction with explicit switching policies rather than expecting a selector to re-run.

### Official Documentation

- [Spring Framework 6.2 — `ImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportSelector.html).
- [Spring Framework 6.2 — `DeferredImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html).
- [Spring Framework 6.2 — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Import.html).
- [Spring Framework 6.2 — `ImportBeanDefinitionRegistrar` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html).
- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — Conditional Bean Definitions](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html#beans-java-conditional).
