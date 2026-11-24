# Loading Additional Properties with @PropertySource and Determining Precedence

In Spring Boot, application configuration does not come only from `application.yml`, `application.properties`, environment variables, and command-line arguments. When you need to include a `.properties` file managed alongside a module or library, Spring Framework provides the **`@PropertySource`** annotation to register that file's contents as a `PropertySource` in the Spring `Environment`.

However, "loading an additional file" and "overriding existing configuration" are two different matters. `@PropertySource` has its own **processing timing** and **precedence position**. In a typical Spring Boot application, a source added via `@PropertySource` has **lower priority than Config Data** such as `application.yml` and lower priority than common override sources such as environment variables or command-line arguments. Moreover, this annotation is processed during ApplicationContext refresh, making it **too late** to reliably affect settings read very early, such as `logging.*`, `spring.main.*`, or Config Data/profile selection mechanisms.

This lesson explains the `@PropertySource` syntax, its position in the property sources hierarchy, how to inspect which source wins, differences from `spring.config.import`, caveats when using YAML, and how to test in a Spring Boot project.

## 1. Model: Environment and Multiple PropertySources

Spring `Environment` is not merely a map holding key/value pairs. It can contain **multiple PropertySources**, each owning a set of keys and arranged in precedence order.

You can picture it as:

~~~text
Spring Environment
  |
  +-- High-priority PropertySource
  |     app.client.timeout = 1s
  |
  +-- Medium-priority PropertySource
  |     app.client.timeout = 3s
  |
  +-- Low-priority PropertySource
        app.client.timeout = 5s

getProperty("app.client.timeout")
          |
          v
     selects 1s, if no higher source intervenes
~~~

When reading:

~~~java
String timeoutText =
    environment.getProperty("app.client.timeout");
~~~

Spring looks for a usable value in the order of the sources. For the same key, a value in a higher-priority source typically shadows a value in a lower-priority source.

Sources can include:

- Default properties provided by the application.
- Sources added via `@PropertySource`.
- Spring Boot Config Data such as `application.properties`, `application.yml`, and profile-specific variants.
- Operating system environment variables.
- Java system properties.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- Other sources added by the framework or the application.

The list above shows types of sources, **not an exhaustive list of all Spring Boot precedence levels**. Keep in mind: the final order is determined by Spring Environment and the actual bootstrapping mechanism; it is not simply "the file written last always wins".

## 2. What Need Does @PropertySource Address?

Suppose an inventory integration module wants to ship its own defaults:

~~~text
src/main/java/example/inventory/
  InventoryConfiguration.java
  InventoryClient.java

src/main/resources/
  inventory-client-defaults.properties
~~~

Resource contents:

~~~properties
inventory.client.enabled=true
inventory.client.timeout=3s
inventory.client.max-retries=2
inventory.client.user-agent=order-service
~~~

To make Spring Environment see these properties when the configuration module is loaded, write:

~~~java
package example.inventory;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
public class InventoryConfiguration {
}
~~~

When `InventoryConfiguration` is a configuration class actually processed by Spring, the contents of `inventory-client-defaults.properties` are added to Environment as a property source.

From another bean:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class InventorySettingsReader {

    private final Environment environment;

    InventorySettingsReader(Environment environment) {
        this.environment = environment;
    }

    String timeout() {
        return environment.getProperty("inventory.client.timeout");
    }
}
~~~

If no higher-priority source overrides it, `timeout()` can return the string `"3s"`.

`@PropertySource` is suitable when you want to explicitly declare that **this module carries a specific properties resource**. It is not the best default mechanism for all deployment configuration and does not mean the resource is automatically refreshed after the application has started.

## 3. Where Does the Annotation Live and When Is It Processed?

A common way to write it:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:config/inventory.properties")
public class InventoryConfiguration {
}
~~~

Prerequisites:

1. The `config/inventory.properties` file actually exists on the application's classpath.
2. `InventoryConfiguration` must be **scanned, imported, or registered** by Spring as a configuration class.
3. Spring processes the annotation while creating/refreshing the ApplicationContext.
4. The properties added to Environment take effect according to the current PropertySource ordering.

If you simply create `inventory.properties` in resources **without declaring `@PropertySource` or another import mechanism**, Spring Boot is under no obligation to automatically read that arbitrary file.

If a class has `@PropertySource` but lies outside component scan and is not imported, the annotation may never be processed.

Example of explicitly importing from the application class:

~~~java
package example;

import example.inventory.InventoryConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(InventoryConfiguration.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Do not create a `@Configuration` class that is never loaded by the context and expect its properties source to appear automatically.

## 4. Relationship with @ConfigurationProperties

One of the primary goals of externalized configuration is binding values into typed objects.

Example:

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory.client")
public record InventoryClientProperties(
        boolean enabled,
        Duration timeout,
        int maxRetries,
        String userAgent
) {}
~~~

Registering the configuration type:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {
}
~~~

Properties contents:

~~~properties
inventory.client.enabled=true
inventory.client.timeout=3s
inventory.client.max-retries=2
inventory.client.user-agent=inventory-module
~~~

When the context processes configuration, Spring Boot Binder can look up values from Environment and bind them into the `InventoryClientProperties` record using the appropriate converters.

**Division of roles:**

- `@PropertySource`: adds a key/value source to Environment.
- `@ConfigurationProperties`: describes a group of properties and the target Java type.
- `@EnableConfigurationProperties`: registers the typed configuration bean.
- Binder/ConversionService: converts values to `Duration`, `int`, `boolean`…
- Validation: checks whether values satisfy operational constraints, if configured.

Do not confuse the file-loading annotation with the bean-registration annotation. `@PropertySource` does not automatically turn every `@ConfigurationProperties` class into a Spring bean.

## 5. classpath: and file: Syntax

`@PropertySource` accepts resource locations. Two important forms:

**Classpath resource:**

~~~java
@PropertySource("classpath:inventory-client-defaults.properties")
~~~

Suitable when the file is packaged inside `src/main/resources` and travels with the JAR/module.

**Filesystem resource:**

~~~java
@PropertySource("file:./config/inventory-client.properties")
~~~

This form reads a file outside the package via a filesystem path. For relative paths, the result depends on the process's **working directory**, not necessarily the directory containing the JAR.

Example:

~~~text
deployment/
  app.jar
  config/
    inventory-client.properties
~~~

If run with:

~~~bash
cd deployment
java -jar app.jar
~~~

then `file:./config/inventory-client.properties` can point to the expected file.

However, if a service manager runs the application with a different working directory, the relative path may no longer be valid.

Operational convention:

- Classpath resource: used for module defaults or resources bundled with the artifact.
- Filesystem resource: used when external paths outside the artifact are explicitly managed by deployment.
- Spring Boot Config Data documents: usually better suited when you want to read deployment files early and control profiles/priority in a standard way.

Do not put real secrets into default resources that are committed or packaged into the JAR.

## 6. When a File Is Missing: ignoreResourceNotFound

By default, if a location declared with `@PropertySource` does not exist or cannot be read, context creation can fail.

Example requiring the file to exist:

~~~java
@PropertySource("classpath:required-settings.properties")
~~~

For a genuinely optional resource:

~~~java
@PropertySource(
    value = "file:./config/local-overrides.properties",
    ignoreResourceNotFound = true
)
~~~

Setting `ignoreResourceNotFound=true` allows ignoring a **not-found** resource in cases supported by Spring, rather than requiring every machine to have that file.

However, distinguish carefully:

- **Missing file:** can be ignored when declared optional.
- **File exists with malformed content:** do not assume all parse errors are ignored.
- **File exists with invalid permissions:** treat as an operational incident, do not silently treat it as "empty configuration".
- **Property with wrong value type:** occurs during binding/conversion and is not fixed by `ignoreResourceNotFound`.
- **Bean validation failure:** is also not disabled by this annotation.

If the application needs a key to operate safely in production, do not casually set `ignoreResourceNotFound=true` and let it start with unintended defaults. Use fail-fast or proper validation.

## 7. Using name and encoding

When you need a clear source name for diagnostics or positioning in `MutablePropertySources`:

~~~java
@PropertySource(
    name = "inventory-client-defaults",
    value = "classpath:inventory-client-defaults.properties"
)
~~~

The name helps readers or diagnostic tools distinguish the added source from other sources.

For content with Unicode characters, you can declare the encoding:

~~~java
@PropertySource(
    name = "inventory-labels",
    value = "classpath:inventory-labels.properties",
    encoding = "UTF-8"
)
~~~

Resource:

~~~properties
inventory.label.display-name=Southern Warehouse
inventory.label.status-name=Active
~~~

Specifying encoding explicitly avoids depending on file-reading defaults across different platforms or framework versions.

**Note:** do not confuse the configuration file's encoding with the HTTP request charset or Java source file encoding. They are separate stages.

## 8. Loading Multiple Files with One @PropertySource

The annotation can accept an array of resource locations:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource({
    "classpath:inventory-common.properties",
    "classpath:inventory-advanced.properties"
})
class InventoryConfiguration {
}
~~~

Suppose:

~~~properties
# inventory-common.properties
inventory.timeout=3s
inventory.max-retries=2
~~~

~~~properties
# inventory-advanced.properties
inventory.timeout=5s
inventory.enabled=true
~~~

When Spring processes multiple resources in the same annotation in declaration order, later resources can override the same key from earlier resources according to `@PropertySource` processing rules. In this example, the timeout value from `inventory-advanced.properties` can beat the value in common **among the `@PropertySource` sources relative to each other**.

However, separate two precedence layers:

1. **Between resources added by `@PropertySource`**: processing order can affect overlapping keys.
2. **Between `@PropertySource` and other Spring Boot sources**: Config Data, environment, and command line still hold their own precedence positions; they can continue to override values from both resources.

Do not conclude that because the second file beats the first file, it also beats `application.yml`.

## 9. Multiple @PropertySource or @PropertySources

You can declare multiple annotations:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-defaults.properties")
@PropertySource("classpath:inventory-feature.properties")
class InventoryConfiguration {
}
~~~

Or group them with `@PropertySources`:

~~~java
import org.springframework.context.annotation.PropertySource;
import org.springframework.context.annotation.PropertySources;

@Configuration(proxyBeanMethods = false)
@PropertySources({
    @PropertySource("classpath:inventory-defaults.properties"),
    @PropertySource("classpath:inventory-feature.properties")
})
class InventoryConfiguration {
}
~~~

Within a single configuration class with a well-defined processing order, a resource processed later can take higher priority for duplicate keys according to the corresponding rules.

However, when annotations are spread across **different configuration classes** discovered by Spring through various scan/import paths, processing order can be unclear and may depend on registration order. Do not design a production contract relying on key collisions between classes whose loading order is not formally guaranteed.

If intentional and verifiable overrides are needed, establish a clear strategy:

- Each module owns a specific prefix.
- Each source contains its own defaults.
- Deployment uses Config Data, environment, or CLI to override.
- Have tests proving the effective value when keys collide.

## 10. Where Does @PropertySource Sit in Spring Boot Precedence Order?

In **standard Spring Boot**, configuration sources are evaluated in a defined precedence order. In the chain relevant to this lesson, from **lowest to highest**:

~~~text
SpringApplication defaultProperties
          |
          v
@PropertySource on @Configuration
          |
          v
Config Data: application.yml, application.properties,
             profile-specific documents, config imports...
          |
          v
Higher-priority sources per Spring Boot rules:
random.*, OS environment, Java system properties,
SPRING_APPLICATION_JSON, command-line arguments, etc.
~~~

The diagram does not list every test, servlet/JNDI, or custom source. It emphasizes: **`@PropertySource` is not a "final override" for `application.yml`**.

A practical table:

| Source | `inventory.client.timeout` |
| --- | --- |
| `@PropertySource`: `inventory-client-defaults.properties` | `3s` |
| `application.yml` | `5s` |
| Matching deployment environment variable | `2s` |
| Command line `--inventory.client.timeout=1s` | `1s` |

If all of the above sources are valid and present in standard Spring Boot processing, the effective value will be `1s` from the command line.

If you remove the command line, it may become `2s` from environment. If you also remove environment, `5s` from `application.yml` can beat `3s` from `@PropertySource`.

Writing `@PropertySource` in Java code does not automatically give it higher priority than Boot config files.

## 11. An Important Test: application.yml Beats @PropertySource

Module defaults file:

~~~properties
# inventory-client-defaults.properties
inventory.client.timeout=3s
inventory.client.max-retries=2
~~~

Shared application file:

~~~yaml
# application.yml
inventory:
  client:
    timeout: 7s
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {}
~~~

Without any higher-priority source, expected result:

~~~text
inventory.client.timeout     = 7s
inventory.client.max-retries = 2
~~~

Explanation:

- Timeout exists in both sources: `application.yml` wins.
- Max retries exists only in the module's default file: `@PropertySource` acts as a fallback.
- The two keys are independent; overriding one key does not erase the rest of the properties resource.

This is a good pattern for libraries wanting to provide **defaults that can be overridden by the application** without modifying the library's JAR.

## 12. @PropertySource and SpringApplication defaultProperties

Spring Boot also allows providing default properties from code:

~~~java
public static void main(String[] args) {
    SpringApplication application =
        new SpringApplication(Application.class);

    application.setDefaultProperties(
        java.util.Map.of(
            "inventory.client.timeout", "10s"
        )
    );

    application.run(args);
}
~~~

These defaults are one of the **lowest-priority** sources in Spring Boot.

If a module adds:

~~~properties
inventory.client.timeout=3s
~~~

via `@PropertySource`, and no Config Data/environment/CLI overrides it, `3s` can beat `10s` from `defaultProperties`.

Therefore, do not treat all "defaults" as a single tier:

- `SpringApplication` default properties.
- Module resources added via `@PropertySource`.
- `@DefaultValue` on typed configuration constructors.
- Values in `application.yml`.

They have their own mechanisms and timings. Accurately predicting the final value requires identifying the exact **source**, not just whether a value is labeled a default.

## 13. Processing Timing: @PropertySource Arrives Fairly Late

Spring Boot does not wait until all `@Configuration` classes are processed before making every startup decision. Some subsystems need values **before ApplicationContext refresh**.

Spring Boot documentation explicitly notes that `@PropertySource` sources are added to Environment while the context is refreshing. Therefore, they can arrive too late for settings such as:

- `logging.*`: the logging system is typically configured very early.
- `spring.main.*`: many properties controlling initial `SpringApplication` configuration.
- Early Config Data and profile decisions: do not rely on `@PropertySource` to select `application-prod.yml` or control `spring.config.import` processed in an earlier step.

Example of what **not to do**:

~~~properties
# early-settings.properties
logging.level.root=DEBUG
spring.main.banner-mode=off
spring.profiles.active=prod
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:early-settings.properties")
class EarlySettingsConfiguration {}
~~~

The author might expect all three settings to always apply from the moment `SpringApplication` begins starting up. However, adding a source during context refresh **does not guarantee** that previously initialized components are reconfigured.

If you need values that affect bootstrap, supply them from sources Spring Boot reads early, such as command-line arguments, environment variables, Java system properties, or Config Data as supported by each property.

**Do not use `@PropertySource` to solve a bootstrap problem it was not designed to solve.**

## 14. Why Should You Not Put spring.profiles.active in @PropertySource?

Suppose a project has:

~~~text
application.yml
application-prod.yml
prod-selector.properties
~~~

File:

~~~properties
# prod-selector.properties
spring.profiles.active=prod
~~~

Class:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:prod-selector.properties")
class ProdSelectorConfiguration {}
~~~

If the author expects Spring Boot to read `prod-selector.properties` and then automatically load `application-prod.yml` within the same bootstrap pass, this design is unreliable. Config Data selection and profile-specific document activation already happened before `@PropertySource` processing.

Select the profile at deployment:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Or:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
~~~

That way Spring Boot knows the profile early, loads the appropriate documents, and then completes the context.

If a module genuinely needs certain beans only in production, `@Profile("prod")` on a configuration class can be a conditional bean-creation mechanism. However, **`@Profile` does not turn `@PropertySource` into an early bootstrap source**; the profile condition still needs to be determined properly in an earlier step.

## 15. No Direct YAML Support by Default

A very common misconception is:

~~~java
@PropertySource("classpath:integration.yml")
~~~

Spring Framework's `@PropertySource` with its default factory is designed to load resources in formats supported by `ResourcePropertySource`/PropertiesLoader, primarily `.properties`; it **does not provide YAML support equivalent to Spring Boot's Config Data by default**.

Therefore, do not assume the file:

~~~yaml
integration:
  timeout: 3s
~~~

will be flattened into `integration.timeout` simply by attaching `@PropertySource("classpath:integration.yml")`.

Appropriate alternatives:

1. **Prefer Spring Boot Config Data** when needing to load YAML.
2. Use `spring.config.import` or `spring.config.additional-location` depending on deployment needs.
3. If you truly must use `@PropertySource`, write a custom `PropertySourceFactory` capable of reading YAML and handling multi-document files, then specify it via the `factory` attribute. This approach requires custom code and testing.

For most Spring Boot applications, **there is no need to write a custom YAML factory** just to bring an auxiliary YAML file into Environment.

## 16. Using spring.config.import for YAML and Config Data

An example in `application.yml`:

~~~yaml
spring:
  config:
    import: "classpath:integration-defaults.yml"

integration:
  enabled: true
~~~

Supplementary file:

~~~yaml
# integration-defaults.yml
integration:
  timeout: 3s
  max-retries: 2
~~~

Spring Boot Config Data supports YAML, multi-document files, and profile activation mechanisms according to its rules.

A crucial difference is **precedence position**: a document imported via Config Data is part of the Config Data system and is not placed at the low priority level of `@PropertySource` by default. Under Config Data rules, an imported document can be placed at a **higher priority position than the document declaring the import**, according to Spring Boot's import processing rules.

Do not mechanically replace:

~~~java
@PropertySource("classpath:integration-defaults.properties")
~~~

with:

~~~yaml
spring:
  config:
    import: "classpath:integration-defaults.properties"
~~~

without accounting for the **change in precedence**. Previously, the file only supplied defaults below `application.yml`; with the new import approach, keys from the supplementary file can beat keys in the importing document if they overlap.

When switching loading mechanisms, write tests for overlapping keys to ensure effective values still match intent.

## 17. When to Use spring.config.additional-location?

If the goal is to **add external configuration directories or files outside the artifact** for deployment, Spring Boot also has the property:

~~~text
spring.config.additional-location
~~~

Example on the command line:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deployment-config/
~~~

This setting is used by Boot during the Config Data discovery/loading phase. It fits well when you want to expand the locations scanned for `application.properties`/`application.yml` without adding a `@Configuration` class just to load files.

Distinction:

| Need | Typically appropriate tool |
| --- | --- |
| Java module with its own `.properties` defaults file | `@PropertySource` |
| Import additional YAML/properties with Config Data semantics | `spring.config.import` |
| Add a Config Data search location at deploy time | `spring.config.additional-location` |
| Supply environment-specific values without changing the artifact | OS environment, command line, secret/config service |
| Need to alter configuration sources before context refresh | Appropriate bootstrap/`EnvironmentPostProcessor` mechanism |
| Only want to bind existing keys to Java | `@ConfigurationProperties` |

Not every project needs all of these mechanisms. Choose a simple model consistent with your deployment workflow.

## 18. Placeholders in @PropertySource Location

A resource location can use placeholders resolved from properties **already in Environment when the location is processed**.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "classpath:defaults/${integration.defaults-file:client.properties}"
)
class IntegrationConfiguration {}
~~~

If `integration.defaults-file` already exists from an early enough source, the location can point to the selected resource. The part after `:` in the placeholder serves as a fallback if the key is not found in that context.

Limitations to understand:

- The placeholder is in the **resource path**, not an intelligent parser for arbitrary file contents.
- Placeholder priority/visibility depends on Environment at the moment the annotation is processed.
- Do not create circular dependencies: an unloaded file cannot determine its own path via a property that only exists inside that file.
- If the location is wrong, the resource may not be found; `ignoreResourceNotFound` can help for optional resources, but does not turn every error into valid configuration.
- Any value used to select an external file should be controlled; do not arbitrarily let runtime user input dictate filesystem paths.

This is an option when a module needs to choose among clearly named defaults files. For application-wide Config Data/profiles, Boot's built-in mechanisms are usually more consistent.

## 19. @PropertySource with @Profile

If a resource only needs to be loaded in a specific environment:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@Profile("local")
@PropertySource("classpath:inventory-local-defaults.properties")
class LocalInventoryDefaultsConfiguration {}
~~~

When `local` is active and the configuration class is included in the context, Spring can additionally process that property resource.

However, understand that:

- `@Profile("local")` selects the **conditional configuration class**.
- `@PropertySource` adds the resource when that class is processed.
- The `local` profile must already have been determined through an appropriate mechanism at context startup.
- The resource still keeps `@PropertySource` precedence; it does not suddenly outrank `application-local.yml`.
- If multiple configuration classes have `@PropertySource` with different conditions, ordering must be designed and tested.

If the goal is simply environment-specific values, it is usually simpler to put them in `application-local.yml` or externalized deployment configuration.

## 20. Reading Values After Adding a PropertySource

After the context has initialized, beans can read from `Environment`:

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
class InventorySyncService {

    private final Duration timeout;
    private final int maxRetries;

    InventorySyncService(Environment environment) {
        this.timeout = environment.getProperty(
            "inventory.client.timeout",
            Duration.class,
            Duration.ofSeconds(3)
        );

        this.maxRetries = environment.getProperty(
            "inventory.client.max-retries",
            Integer.class,
            2
        );
    }
}
~~~

Points to note:

- `Environment#getProperty(key)` can return a String or null if no value exists.
- The overload taking `Class<T>` requests conversion to the target type.
- The overload with a default handles missing keys.
- Present data of the wrong type can cause a conversion error; a default does not swallow errors by default.
- Assigning variables in a constructor does not mean they automatically change if the source file changes later.

If a property group has multiple fields, use `@ConfigurationProperties` to clearly manage the prefix, types, validation, and defaults instead of scattering string keys across many services.

## 21. How to Know Which Source Actually Won?

An application has:

~~~properties
# inventory-client-defaults.properties
inventory.client.timeout=3s
~~~

~~~yaml
# application.yml
inventory:
  client:
    timeout: 5s
~~~

When querying:

~~~java
environment.getProperty("inventory.client.timeout")
~~~

the result may be `"5s"`. However, to explain which source won, you need to inspect the `PropertySource` list.

A diagnostic approach **only for non-sensitive keys**:

~~~java
package example.debug;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration(proxyBeanMethods = false)
class PropertySourceInspectionConfiguration {

    @Bean
    ApplicationRunner inspectSources(
            ConfigurableEnvironment environment) {
        return args -> {
            String key = "inventory.client.timeout";

            for (PropertySource<?> source :
                    environment.getPropertySources()) {
                Object value = source.getProperty(key);
                if (value != null) {
                    System.out.println(
                        "Source with key: " + source.getName());
                }
            }
        };
    }
}
~~~

This code lists sources that provide a **non-null value** for the key, without printing the value. The iteration order of `getPropertySources()` reflects the order Environment uses at that moment; the first matching source can be the winning source under normal resolution.

**Warnings:**

- A PropertySource name can contain file paths or deployment details; avoid broad logging unnecessarily.
- Do not iterate and print all keys/values, as that easily exposes credentials, tokens, or sensitive data.
- Some sources may receive special handling from Spring, such as placeholders, environment variable name aliases, or composite sources.
- Diagnostic code in an `ApplicationRunner` reports Environment **after context creation** and cannot prove which values were effective at the very beginning of bootstrap.

For inspecting ordering, use tests or internal debug tools rather than leaving a configuration dumper enabled in production.

## 22. ConfigurableEnvironment and MutablePropertySources

If you need direct access to source ordering, Spring provides:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;

MutablePropertySources sources =
    environment.getPropertySources();
~~~

`MutablePropertySources` provides operations such as `addFirst`, `addLast`, `addBefore`, and `addAfter` to insert a source at a specific position. Example illustrating this on a configurable environment:

~~~java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

MapPropertySource overrides = new MapPropertySource(
    "integration-overrides",
    Map.of("integration.timeout", "1s")
);

environment.getPropertySources().addFirst(overrides);
~~~

`addFirst` puts the new source at the front of the list, so it can take high priority during key resolution.

**Do not treat this snippet as a recommendation to add sources arbitrarily inside an `ApplicationRunner`**: by the time `ApplicationRunner` runs, many beans and subsystems are already initialized and some values may have already been bound/read earlier. Mutating Environment late does not automatically recreate those beans or reconfigure the logging system.

If the requirement genuinely is to **define a custom-priority source during bootstrap**, use an appropriate Spring Boot lifecycle extension instead of adding a source late and guessing whether beans updated.

## 23. When Is EnvironmentPostProcessor Needed?

`EnvironmentPostProcessor` is Spring Boot's extension mechanism for modifying `Environment` during preparation before the ApplicationContext is finalized. It is suitable when you need to:

- Load a special configuration source outside standard Config Data.
- Add defaults or overrides before many beans are created.
- Define a clear precedence position using `MutablePropertySources`.
- Integrate a config service or specialized source format within a supported lifecycle phase.

However, this mechanism is **more powerful and more complex** than `@PropertySource`; you must understand extension registration by Spring Boot version, lifecycle phases, priority between processors, resource access constraints, and testing.

Conceptual example inside a processor:

~~~java
import java.util.Map;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public void addDefaults(ConfigurableEnvironment env) {
    env.getPropertySources().addLast(
        new MapPropertySource(
            "warehouse-module-defaults",
            Map.of("warehouse.timeout", "3s")
        )
    );
}
~~~

The snippet above **only illustrates adding a source**, not a complete `EnvironmentPostProcessor` with registration. In production, implement the proper extension point and place the source deliberately.

If you only need a few default properties from a `.properties` file, `@PropertySource` remains simpler. If the requirement is profile-specific YAML or deployment config, prefer the built-in Config Data mechanism before building a custom processor.

## 24. @PropertySource Does Not Automatically Reload Files

If you declare:

~~~java
@PropertySource("file:./config/inventory-client.properties")
~~~

the file is read when the context processes configuration. If someone edits the file on disk after startup, Spring Boot does not automatically promise to:

- re-read the file,
- replace the PropertySource with new contents,
- rebind all `@ConfigurationProperties`,
- or recreate beans that received values in their constructors.

To achieve **dynamic refresh**, you need a dedicated lifecycle and configuration update mechanism (potentially involving Spring Cloud, events, reload logic, or controlled restarts).

Do not choose `@PropertySource` thinking "resource on the filesystem" equals "live updates". Those are two separate problems.

For immutable artifacts/containers, the simplest approach is usually updating configuration and **restarting/rolling out** the application via CI/CD.

## 25. Overlapping Config Keys and a Clear Ownership Policy

Suppose there are two modules:

~~~text
payments-defaults.properties:
  http.timeout=2s

inventory-defaults.properties:
  http.timeout=5s
~~~

If both modules put an overly generic key like `http.timeout` into Environment, the effective value can depend on configuration class loading order. This design easily causes conflicts.

Instead of generic keys, use clear namespaces:

~~~properties
payment.client.timeout=2s
inventory.client.timeout=5s
~~~

Each module can load its defaults file independently without fighting over a single key.

Principles:

1. Each module owns a clear prefix.
2. Internal resource files mainly provide defaults.
3. The application/deployment is allowed to override via standard Spring Boot sources.
4. Do not let modules compete over one key and rely on scan order to decide the winner.
5. If a shared key is truly needed, publish the owning source and supported override mechanism.

A good design can explain precedence order **without relying on which class happened to be scanned first**.

## 26. @PropertySource and Environment Variables

File:

~~~properties
inventory.client.timeout=3s
~~~

Deployment can provide an environment variable following Spring Boot's relaxed binding conventions, for example:

~~~bash
INVENTORY_CLIENT_TIMEOUT=1s java -jar app.jar
~~~

When binding `InventoryClientProperties`, the environment variable source normally has higher priority than the `@PropertySource` source; the effective timeout can become 1 second.

Distinguish two things:

- **Source precedence:** OS environment typically beats defaults files.
- **Property name normalization:** Spring Boot Binder has relaxed binding rules to map environment variable names to Java property keys, such as uppercase + underscore.

When calling `Environment#getProperty` directly, recognition of equivalent names depends on the PropertySource and resolver; use canonical names where possible and test in a real context.

If debugging an environment override, verify that the variable was passed to the **exact Java process** and is not being overridden by an even higher source.

## 27. @Value Reads Properties from @PropertySource

In addition to `Environment` and `@ConfigurationProperties`, a bean can use `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class InventoryBanner {

    private final String userAgent;

    InventoryBanner(
            @Value("${inventory.client.user-agent:inventory}")
            String userAgent) {
        this.userAgent = userAgent;
    }
}
~~~

If the file loaded via `@PropertySource` contains:

~~~properties
inventory.client.user-agent=inventory-module
~~~

and no higher source overrides it, the injected value can be `"inventory-module"`.

`@Value` has no special precedence advantage over Environment. It still relies on the property resolution system. The placeholder fallback `:inventory` is used when no matching value is found; it is not a high-priority PropertySource.

With many related keys, `@ConfigurationProperties` is usually easier to maintain than `@Value` across many fields or constructor parameters.

## 28. Do Not Use @PropertySource to Store Secrets

A file inside the JAR's resources:

~~~properties
payment.api-token=real-production-secret
~~~

is easily exposed through repositories, artifacts, CI logs, or tools inspecting the JAR. `@PropertySource` does not encrypt or protect that content.

For secrets:

- Use a secret manager, Kubernetes Secret, environment, or config service suited to your infrastructure.
- Restrict read permissions at the deployment level.
- Do not commit real secrets.
- Do not print tokens/passwords when inspecting PropertySources.
- Add validation so startup fails if credentials are missing or dummy placeholders remain.
- Do not provide a "default secret" that could accidentally be used in production.

Even if an external file is generated at runtime by infrastructure, permissions and lifecycle must be clearly managed. `ignoreResourceNotFound=true` is not a secret management strategy.

## 29. Testing @PropertySource with ApplicationContextRunner

To confirm a resource is loaded, you can create a small test config.

File in test resources:

~~~properties
# src/test/resources/module-defaults.properties
demo.feature.enabled=true
demo.feature.retry-count=2
~~~

Configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:module-defaults.properties")
class ModuleDefaultsConfiguration {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.assertThat;

class PropertySourceLoadingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(ModuleDefaultsConfiguration.class);

    @Test
    void loadsModuleDefaults() {
        runner.run(context -> {
            assertThat(
                context.getEnvironment()
                    .getProperty("demo.feature.enabled")
            ).isEqualTo("true");

            assertThat(
                context.getEnvironment()
                    .getProperty("demo.feature.retry-count")
            ).isEqualTo("2");
        });
    }
}
~~~

This test verifies:

1. The config class is loaded into the context.
2. The `module-defaults.properties` resource is loaded.
3. Environment can read keys from that source.

It does not yet test the full precedence order inside a running Spring Boot application with real Config Data.

## 30. Testing Override Priority

You can add a higher-priority property source in the test context:

~~~java
@Test
void explicitTestPropertyOverridesModuleDefaults() {
    runner
        .withPropertyValues(
            "demo.feature.retry-count=7"
        )
        .run(context -> {
            assertThat(
                context.getEnvironment().getProperty(
                    "demo.feature.retry-count"
                )
            ).isEqualTo("7");
        });
}
~~~

Here the test value is supplied via `withPropertyValues` under `ApplicationContextRunner`'s mechanism and can take higher priority than the `@PropertySource` defaults source. The test specifically verifies that **adding a properties resource does not necessarily make it beat all other sources**.

For applications with Config Data profiles, add integration tests that actually load `application.yml` and `application-dev.yml` as intended, rather than assuming plain `ApplicationContextRunner` includes all boot rules and auto-configurations.

## 31. Integration Testing with @SpringBootTest

Suppose the application loads `InventoryConfiguration`.

Module defaults file:

~~~properties
inventory.client.timeout=3s
inventory.client.max-retries=2
~~~

Test/application `application.yml` file:

~~~yaml
inventory:
  client:
    timeout: 5s
~~~

Test:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class InventoryPriorityIntegrationTest {

    @Autowired
    InventoryClientProperties properties;

    @Test
    void applicationConfigOverridesModuleDefault() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofSeconds(5));

        assertThat(properties.maxRetries())
            .isEqualTo(2);
    }
}
~~~

The test above requires an application context, properties registration, and configuration resources matching the example. If another test supplies the same key using `@SpringBootTest(properties=...)`, the test property can take higher priority and the expected value must adjust accordingly.

You do not need to write tests covering the entire Spring Boot framework; focus on the **key module properties** the application actually depends on.

## 32. Avoid Tests Depending on Logging and Bootstrap Properties

An incorrect way to test is writing:

~~~properties
# module-defaults.properties
logging.level.root=DEBUG
spring.profiles.active=prod
~~~

and then testing whether the module loaded by observing startup logging or active profiles.

These properties may be processed early, before `@PropertySource` is added to Environment. Thus the test can produce unexpected results even though the resource actually loaded during context refresh.

To test `@PropertySource`, use a regular module key such as `demo.feature.retry-count`. To test bootstrap configuration, supply keys from sources read during the appropriate phase, such as Config Data or the launch environment.

Do not conclude from an early-processed property that `@PropertySource` does not work in general.

## 33. Testing Optional Resources

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "file:./config/not-present-local.properties",
    ignoreResourceNotFound = true
)
class OptionalLocalConfig {}
~~~

In a test run from a working directory without that file, the context can still initialize if the only issue is the missing optional resource and other components do not require keys from that file.

However, do not rely on an arbitrary working directory in CI. For reproducible tests, use a temporary directory or an explicitly controlled test path and assert the file state clearly.

If a file is required in production, write a test asserting startup fails when the file is missing rather than marking it optional for every environment.

## 34. When Two @Configurations Both Add Sources with Overlapping Keys

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:module-a.properties")
class ModuleAConfiguration {}

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:module-b.properties")
class ModuleBConfiguration {}
~~~

Both files contain:

~~~properties
integration.timeout=...
~~~

Even though Spring has a source processing order, you should not design an application relying on the processing order of auto-discovered configuration classes without an explicit contract on registration/import order.

Better solutions:

- Use distinct prefixes: `module-a.timeout` and `module-b.timeout`.
- Or have only one module own `integration.timeout`.
- If overrides are needed, place values in application/deployment sources with clear precedence.
- Add integration tests with the real combination of modules.

Ambiguity in precedence is a sign of unclear key ownership, not a reason to add more `@PropertySource` annotations.

## 35. Identifying Resource Loading Errors vs. Binding Errors

When an application fails after adding the annotation, identify the error layer:

| Symptom | Cause to inspect |
| --- | --- |
| `classpath:defaults.properties` not found | Resource not packaged, wrong path, or wrong module |
| External file not found | Working directory, mount, path, read permissions |
| File exists but YAML does not bind | Default `@PropertySource` does not parse YAML like Boot Config Data |
| Key does not have expected value | Wrong key name or overridden by higher-priority source |
| Value `"many"` fails to bind to `int` | Conversion error |
| `@ConfigurationProperties` bean does not exist | Missing scanning/registration |
| Bean has value but violates `@Min` | Validation |
| Logging does not change per file | Property was read early before `@PropertySource` was added |
| Edited file but bean did not change | No automatic refresh/rebind mechanism |
| Works in IDE but fails in container | Different classpath/working directory/mounts |

Resource errors, precedence errors, and conversion errors **should not be handled with the same workaround**. Fix the right layer.

## 36. Checklist: Choosing @PropertySource or Another Mechanism

Before adding `@PropertySource`, ask:

1. Is the resource a properly formatted `.properties` file?
2. Does the resource travel with the module, or is it supplied externally by deployment?
3. Is the `@Configuration` class containing the annotation actually loaded?
4. Is the goal providing **low-priority defaults** or overriding `application.yml`?
5. Which keys can overlap and which source must win?
6. Is profile-specific YAML or multi-document support needed?
7. Must any keys take effect before context refresh, such as `logging.*`?
8. Is automatic refresh needed when the file changes?
9. Are there any secrets that must not be packaged into the JAR?
10. Can the resource legitimately be missing? Should startup fail fast?
11. Is UTF-8 encoding needed for Unicode content?
12. Are there tests with real application config and environment overrides?
13. Is another module competing for the same prefix?
14. Has Config Data been prioritized for Spring Boot deployment concerns?

**Selection rule:** use `@PropertySource` for supplementary properties files tied to a configuration/module; use Config Data to manage startup, profile, and deployment configuration; use an appropriate bootstrap source if early intervention or specialized priority control is needed.

## 37. Hands-On Exercise: Module Defaults and App Overrides

**Requirement:** an HTTP client module has defaults of 3s / 2 retries, while the application may change timeout to 5s via `application.yml` and production may further change it to 1s via an environment variable.

### Step 1 — Default Resource

Create:

~~~text
src/main/resources/inventory-client-defaults.properties
~~~

Contents:

~~~properties
inventory.client.timeout=3s
inventory.client.max-retries=2
inventory.client.enabled=true
~~~

### Step 2 — Configuration Loading the Resource and Binding the Record

~~~java
package example.inventory;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory.client")
public record InventoryClientProperties(
        Duration timeout,
        int maxRetries,
        boolean enabled
) {}
~~~

~~~java
package example.inventory;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:inventory-client-defaults.properties")
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {}
~~~

### Step 3 — Application Override via Config Data

~~~yaml
# application.yml
inventory:
  client:
    timeout: 5s
~~~

Without a higher source, expected result:

~~~text
timeout     = 5s
maxRetries  = 2
enabled     = true
~~~

### Step 4 — Deployment Override

POSIX shell example:

~~~bash
INVENTORY_CLIENT_TIMEOUT=1s java -jar app.jar
~~~

When the variable is passed and recognized by the binder under Spring Boot rules, timeout can become 1s. The two un-overridden keys still come from the module defaults or another appropriate source.

### Step 5 — Verification

Write integration tests covering:

- A case with defaults only: timeout 3s.
- A case with application config override: timeout 5s.
- A case with a higher-priority override source: timeout 1s.
- A case with a missing required resource: context fails.
- A case with a malformed timeout value: binding fails or is handled by explicit converter/validation configuration.

No need to print the entire Environment, especially if tokens or passwords exist. Assert directly on `InventoryClientProperties`.

### Step 6 — Self-Check Questions

**Question 1:** Does adding `@PropertySource` automatically activate the `prod` profile?

**Answer:** Not reliably. Profiles/Config Data must be selected during the appropriate bootstrap phase.

**Question 2:** Why does `application.yml` setting 5s beat the resource setting 3s?

**Answer:** Under standard Spring Boot precedence, Config Data has higher priority than sources added via `@PropertySource`.

**Question 3:** Can you just change the annotation to `@PropertySource("classpath:defaults.yml")` to use YAML?

**Answer:** Not with the default factory. Use Config Data or a tested custom `PropertySourceFactory`.

**Question 4:** Does `ignoreResourceNotFound=true` ignore a malformed timeout?

**Answer:** No. It applies to missing resources, not conversion/validation.

**Question 5:** If you need a source with higher priority than the command line, should you add it in `ApplicationRunner`?

**Answer:** No. That is too late for many already-bound/read values. You need an early extension point and explicit priority design, while also considering operational and security implications.

## 38. Summary

`@PropertySource` is a Spring Framework tool for **loading additional properties resources into the Spring Environment** when a configuration class is processed. It is useful for module defaults or a clearly defined supplementary properties file. The annotation supports `classpath:`/`file:` locations, `name`, `encoding`, `ignoreResourceNotFound`, and multiple resources.

In Spring Boot, this source typically sits **below Config Data** and common deployment override sources. Because `@PropertySource` is processed during context refresh, do not use it to decide properties read very early by Boot such as logging, `spring.main` settings, or profile/Config Data selection.

When you need YAML, profile-specific config, import priority, or external configuration paths outside the artifact, prefer **Spring Boot Config Data** mechanisms such as `spring.config.import` and `spring.config.additional-location`. When determining which source wins, inspect Environment/PropertySources in tests or controlled debug environments rather than guessing solely from file names.

**Remember:** `@PropertySource` **adds a configuration source**, not an "override all sources" directive; the final outcome depends on **loading timing**, **precedence order**, and **how the property is bound**.
