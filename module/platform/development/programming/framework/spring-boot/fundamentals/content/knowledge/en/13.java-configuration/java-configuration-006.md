# ImportSelector, DeferredImportSelector, and Programmatic Configuration Selection

In Spring, the `@Import` annotation allows a configuration class to bring additional configurations or components into the ApplicationContext. When you need to decide which configuration classes to import based on metadata or runtime environment, Spring provides two extension points: `ImportSelector` and `DeferredImportSelector`.

Both return the fully qualified names of the classes to import. The main difference is when Spring invokes the selector during configuration parsing. `ImportSelector` is processed during the normal configuration parsing flow; `DeferredImportSelector` is processed after Spring has processed regular configurations, allowing it to make choices with more information about the discovered set of configurations.

## 1. The Role of @Import

A configuration class can import other configuration classes directly:

~~~java
@Configuration
@Import({
        DatabaseConfiguration.class,
        MessagingConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

Spring continues parsing the imported classes as configuration sources. They can declare `@Bean` methods, import other configurations, or apply configuration conditions.

Direct importing works well when the set of configurations is known at coding time. When you want to choose based on an annotation on the importing class, an environment property, or a programmatic rule, you can pass a selector to `@Import`:

~~~java
@Configuration
@Import(StorageImportSelector.class)
public class ApplicationConfiguration {
}
~~~

`StorageImportSelector` is not where business bean instances are created manually. It simply returns the names of configuration classes that Spring should include in processing.

## 2. How Does ImportSelector Work?

`ImportSelector` belongs to the `org.springframework.context.annotation` package. The interface's core contract is:

~~~java
public interface ImportSelector {

    String[] selectImports(AnnotationMetadata importingClassMetadata);
}
~~~

Spring passes in the `AnnotationMetadata` of the configuration class importing the selector. The selector can inspect metadata on that class, such as which annotations are present and their attributes. The method returns an array of fully qualified class names to import.

For example, an annotation that enables a storage feature might carry a selection attribute:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(StorageImportSelector.class)
public @interface EnableStorage {

    String mode() default "memory";
}
~~~

Configuration class using the annotation:

~~~java
@Configuration
@EnableStorage(mode = "filesystem")
public class ApplicationConfiguration {
}
~~~

The selector reads the `mode` attribute from the importing class's metadata:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class StorageImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {

        var attributes = importingClassMetadata.getAnnotationAttributes(
                EnableStorage.class.getName()
        );

        if (attributes == null) {
            throw new IllegalStateException(
                    "@EnableStorage metadata is missing"
            );
        }

        String mode = (String) attributes.get("mode");

        return switch (mode) {
            case "memory" -> new String[] {
                    InMemoryStorageConfiguration.class.getName()
            };
            case "filesystem" -> new String[] {
                    FileStorageConfiguration.class.getName()
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported storage mode: " + mode
            );
        };
    }
}
~~~

When `mode` is `filesystem`, the selector returns the name `FileStorageConfiguration`. Spring imports and parses that configuration class. If it is `memory`, the selected configuration class is `InMemoryStorageConfiguration`.

Both configuration classes can fulfill the same contract:

~~~java
@Configuration(proxyBeanMethods = false)
public class InMemoryStorageConfiguration {

    @Bean
    StorageClient storageClient() {
        return new InMemoryStorageClient();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
public class FileStorageConfiguration {

    @Bean
    StorageClient storageClient() {
        return new FileStorageClient();
    }
}
~~~

Services depend only on the `StorageClient` interface:

~~~java
@Service
public class DocumentService {

    private final StorageClient storageClient;

    public DocumentService(StorageClient storageClient) {
        this.storageClient = storageClient;
    }
}
~~~

As a result, selection logic lives inside the selector, while services do not need to check `mode` or instantiate implementations via conditional statements.

### Reading Importing Class Metadata

The `AnnotationMetadata` parameter describes the configuration class importing the selector. It allows the selector to read annotations and attributes without instantiating that configuration class.

Common operations:

~~~java
boolean hasEnableStorage = importingClassMetadata.hasAnnotation(
        EnableStorage.class.getName()
);

Map<String, Object> attributes =
        importingClassMetadata.getAnnotationAttributes(
                EnableStorage.class.getName()
        );
~~~

If the selector is used with a composed annotation or multiple related configuration annotations, clearly identify which metadata serves as the deciding source. Avoid assuming the selector is receiving metadata for an already instantiated bean.

## 3. Selecting Configuration Based on Environment

A selector can also rely on environment properties. Spring supports `Aware` callbacks for framework-instantiated strategy objects, including `EnvironmentAware`. You can use this callback to receive `Environment`:

~~~java
import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;

public class StorageImportSelector
        implements ImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {

        String mode = environment.getProperty(
                "app.storage.mode",
                "memory"
        );

        return switch (mode) {
            case "memory" -> new String[] {
                    InMemoryStorageConfiguration.class.getName()
            };
            case "filesystem" -> new String[] {
                    FileStorageConfiguration.class.getName()
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported app.storage.mode: " + mode
            );
        };
    }
}
~~~

Configuration can be placed in `application.yml`:

~~~yaml
app:
  storage:
    mode: filesystem
~~~

In this example, the selector reads the value from `Environment` and selects a configuration class. The default `memory` is used when the property is absent. For an invalid value, the selector throws an exception so the application fails fast instead of silently picking an unintended implementation.

Values can be passed via environment variables or command-line arguments across any Spring Boot supported configuration source. For example:

~~~bash
APP_STORAGE_MODE=filesystem
~~~

Selection still takes place during configuration parsing and ApplicationContext creation. Changing the property after the context is initialized will not re-run the selector or replace the bean currently in use.

## 4. How Does DeferredImportSelector Differ from ImportSelector?

`DeferredImportSelector` is a subinterface of `ImportSelector`:

~~~java
public interface DeferredImportSelector extends ImportSelector {

    // Extension methods for deferred processing
}
~~~

The key difference is that Spring defers processing this selector until after regular configuration classes have been processed. That is useful when the import decision depends on the set of configurations already discovered or needs to coordinate with configuration conditions.

For example, an ordinary selector may be processed while Spring is parsing one configuration class, while other configurations are still in the parsing pipeline. With a deferred selector, Spring batches processing until after normal configuration parsing completes. This enables selection logic to operate at a later point during bootstrap.

You can convert the earlier Environment-based example into a deferred selector:

~~~java
import org.springframework.context.EnvironmentAware;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class DeferredStorageImportSelector
        implements DeferredImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {

        String mode = environment.getProperty(
                "app.storage.mode",
                "memory"
        );

        return switch (mode) {
            case "memory" -> new String[] {
                    InMemoryStorageConfiguration.class.getName()
            };
            case "filesystem" -> new String[] {
                    FileStorageConfiguration.class.getName()
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported app.storage.mode: " + mode
            );
        };
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

The feature-enabling annotation can import this deferred selector:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(DeferredStorageImportSelector.class)
public @interface EnableStorage {
}
~~~

When Spring processes the configuration, the deferred selector is recorded and processed during the deferred phase. It still returns configuration class names like `ImportSelector`; Spring proceeds to register and parse those classes.

Do not choose `DeferredImportSelector` merely because its name sounds more powerful. If a selector only needs to read metadata from the importing annotation and return a configuration, `ImportSelector` is usually enough. Choose deferred when later timing actually matters to configuration rules.

## 5. What Is DeferredImportSelector.Group Used For?

Beyond deferral, `DeferredImportSelector` also supports a `Group` mechanism. A group allows collecting results from multiple deferred selectors, processing them together, and deciding the final list of imports.

The simplified contract of a group consists of two steps:

~~~java
public interface Group {

    void process(
            AnnotationMetadata metadata,
            DeferredImportSelector selector
    );

    Iterable<Entry> selectImports();
}
~~~

- `process(...)` receives the metadata of the importing class and the corresponding selector to collect selections.
- `selectImports()` returns the aggregated entries. Each `Entry` associates the importing class metadata with the imported class name.

A selector can specify a group by overriding `getImportGroup()`:

~~~java
@Override
public Class<? extends Group> getImportGroup() {
    return StorageImportGroup.class;
}
~~~

Example illustrating a group that collects results:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class StorageImportGroup implements DeferredImportSelector.Group {

    private final List<Entry> entries = new ArrayList<>();

    @Override
    public void process(
            AnnotationMetadata metadata,
            DeferredImportSelector selector) {

        for (String className : selector.selectImports(metadata)) {
            entries.add(new Entry(metadata, className));
        }
    }

    @Override
    public Iterable<Entry> selectImports() {
        return List.copyOf(entries);
    }
}
~~~

This example retains the collected imports. A real-world group can add deduplication, prioritization, or exclusion logic based on system rules. Groups are particularly useful when multiple selectors must coordinate to produce a unified set of configurations.

There is no need to write a custom `Group` if you only have one selector choosing one configuration. Use the default mechanism first; only add a `Group` when you need to aggregate or coordinate results across multiple selectors.

### Selector Processing Order

`DeferredImportSelector` extends `Ordered`. Relative order can be controlled by implementing `getOrder()` or using the corresponding ordering mechanism. Ordering helps the framework sort selectors during deferred processing; it is not a guarantee that every bean imported by a selector will be initialized in an arbitrary business order.

If multiple selectors need to coordinate, a `Group` is a better place to express result aggregation. Do not rely on incidental component scan order or class declaration order to govern dependencies between beans.

## 6. Real-World Example: Spring Boot Auto-Configuration

Spring Boot uses deferred imports to implement auto-configuration. The `@EnableAutoConfiguration` annotation is activated via `@SpringBootApplication`; this brings `AutoConfigurationImportSelector` into configuration parsing.

The selector collects auto-configuration candidates, and then conditions such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and others decide which configurations actually take effect.

In Spring Boot 3, the auto-configuration list is published via the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

A library can declare its auto-configuration class names in this file. Spring Boot reads the candidate list via the deferred import mechanism and evaluates the conditions on those configurations.

This lets libraries provide integrations based on classpath and configuration without requiring applications to import each configuration manually. For instance, when a client library is present and the user has not provided an alternative bean, auto-configuration can register a default implementation.

`AutoConfigurationImportSelector` is a real-world example showing how deferred selection can orchestrate a large set of configurations. In ordinary application code, you rarely need to rebuild Spring Boot's entire auto-configuration machinery yourself.

## 7. Comparing Selectors with Other Bean Registration Mechanisms

Configuration extension points serve different purposes:

| Mechanism | Primary job | When to use |
|---|---|---|
| `@Import(SomeConfiguration.class)` | Imports a known configuration class | Fixed set of configurations |
| `ImportSelector` | Programmatically selects configuration class names | Selection based on metadata or rules |
| `DeferredImportSelector` | Selects configurations during the deferred phase | Needs to run after regular configurations |
| `DeferredImportSelector.Group` | Aggregates and coordinates multiple deferred results | Multiple selectors need to coordinate |
| `ImportBeanDefinitionRegistrar` | Registers `BeanDefinition`s programmatically | Needs direct control over bean definitions |
| `@Conditional` | Decides whether a configuration or bean is applied | Conditions tied to a specific configuration/bean |

A selector returns class names to import, whereas `ImportBeanDefinitionRegistrar` interacts directly with `BeanDefinitionRegistry` to register bean definitions. If the goal is bringing more configuration classes into the context, a selector usually expresses intent better. If you need to generate many `BeanDefinition`s based on metadata or a custom registration model, a registrar may fit better.

`@Conditional` annotations can also be placed on imported configuration classes. The selector decides which classes enter parsing; conditions decide whether that class or bean qualifies to be applied. Both mechanisms complement each other.

## 8. Common Mistakes When Writing Selectors

### Returning Incorrect Class Names

Elements in the returned array must be fully qualified class names, such as `com.example.storage.FileStorageConfiguration`. Using `SomeConfiguration.class.getName()` avoids typos and package refactoring bugs.

If a class name does not exist or cannot be loaded, configuration processing will fail.

### Returning an Implementation Instead of an Appropriate Configuration

A selector can import a configuration class containing `@Bean` methods. This is usually a clean way to group related beans and keep registration logic inside Spring's configuration mechanism.

Do not call a service or repository constructor manually inside a selector. Doing so bypasses the container, dependency injection, bean post-processing, and scope rules.

### Allowing Multiple Configurations to Register Incompatible Beans

If a selector returns two configurations that both declare a bean of the same type and name, the application may hit conflicts or ambiguous injection candidates. Ensure selection rules produce an unambiguous outcome, or design appropriate conditions/qualifiers when multiple implementations truly must coexist.

### Using a Deferred Selector While Assuming It Runs After All Beans

Deferred refers only to processing order during configuration parsing. It does not mean all lazy, prototype, or request-scoped beans or all startup tasks have finished. Nor does it mean the application is ready to serve requests.

### Expecting the Selector to Re-Run When Properties Change

Selectors participate in building the ApplicationContext. Changing a property after the context has refreshed does not trigger re-selection. For another configuration to take effect, an appropriate context initialization or refresh strategy is required.

## 9. Workflow for Programmatic Configuration Selection

When you need to select configuration programmatically, follow these steps:

1. Identify the activation point using `@Import` or a feature-enabling annotation.
2. Identify the deciding data: importing class metadata, `Environment`, or a candidate list.
3. Use `ImportSelector` if selection can happen during normal configuration processing.
4. Use `DeferredImportSelector` if regular configurations need to be processed first.
5. Only use `Group` when multiple deferred selectors need to aggregate, filter, deduplicate, or coordinate results.
6. Return fully qualified names of configuration classes and let Spring manage bean creation.
7. Clearly define behavior for missing properties, invalid values, or when no configuration is selected.
8. Test all selection branches to ensure a single valid set of configurations is registered.

`ImportSelector` and `DeferredImportSelector` extend Spring's configuration capabilities by separating selection rules from business beans. Understanding when each type runs helps choose the right extension point, structure auto-configuration cleanly, and let the ApplicationContext continue managing the dependencies, lifecycles, and scopes of imported components.
