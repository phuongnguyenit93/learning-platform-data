# PropertySource and MutablePropertySources in ConfigurableEnvironment

## 1. Why Do We Need to Understand Property Sources Instead of Only Reading application.yml?

A Spring Boot application can receive the same configuration key from many places: configuration packaged inside a JAR, external files, environment variables, Java system properties, command-line arguments, sources added by libraries, or a custom source built by the application itself.

For example, the key `warehouse.api-url` can be declared as:

```yaml
# src/main/resources/application.yml
warehouse:
  api-url: https://warehouse-default.example.invalid
```

While the process is started with:

```bash
java -jar app.jar \
  --warehouse.api-url=https://warehouse-prod.example.invalid
```

Why does `Environment.getProperty("warehouse.api-url")` return the value from the command line instead of YAML? If we want to add a "region-specific default values" source, where should we add it so that it does not override the deployer's configuration? Can the precedence order be changed at runtime? Should we directly modify Spring Boot's built-in default sources?

To answer these questions, we need to understand three central types in Spring Framework:

- **`PropertySource<T>`**: represents **a single source** that can look up values by property name.
- **`MutablePropertySources`**: an **ordered and mutable** collection of `PropertySource` instances.
- **`ConfigurableEnvironment`**: a variant of `Environment` that allows accessing/modifying the collection of property sources and certain environment configuration settings.

This is the foundation of the **Environment Extensions** topic: instead of merely consuming configuration, we can intentionally register and order a new source.

The final result depends on the **key**, **value**, **precedence order**, **timing of adding the source**, and **how beans have already been initialized**.

## 2. Overall Model

A simple diagram:

```text
             ConfigurableEnvironment
                      |
                      v
             MutablePropertySources
                      |
         +------------+-------------+
         |            |             |
      index 0      index 1       index 2 ...
         |            |             |
         v            v             v
   PropertySource  PropertySource  PropertySource
   high priority       next        low priority
         |            |             |
         +------------+-------------+
                      |
                      v
            PropertyResolver
             getProperty(key)
                      |
                      v
       Find the first source with a value
                      |
                      v
              @Value / Binder /
          @ConfigurationProperties
```

When resolving a simple key, the mental rule is:

1. Start at the highest-priority `PropertySource` in the list.
2. Ask whether that source has a matching value for the requested property name.
3. If not, move to the next lower-priority source.
4. When a non-`null` value is found, use it according to the property resolution mechanism.
5. Only then handle the appropriate steps such as placeholders, type conversion, and injecting the value into beans.

An important note: an **empty** string value `""` is still different from `null`. A source can actively provide an empty string, preventing lower-priority sources from being selected for that key.

Spring Boot builds and adds many default sources according to its own rules. The list in the diagram is a generalized model, **not a fixed order across all Boot versions**. To observe the actual order, print the source names of the running process itself rather than guessing from file names.

## 3. The PropertySource<T> Interface: Contract of a Single Source

`PropertySource<T>` is located in:

```java
org.springframework.core.env.PropertySource
```

A source has a **name** and an underlying data source object. The most important method is:

```java
Object getProperty(String name)
```

The result can be a value, or `null` if this source does not provide the requested name.

We can visualize it as:

```text
PropertySource("tenantDefaults")
    |
    +-- getProperty("tenant.region") -> "ap-southeast"
    |
    +-- getProperty("tenant.limit")  -> 100
    |
    +-- getProperty("tenant.unknown")-> null
```

Common members on the API include:

| API | Meaning |
| --- | --- |
| `getName()` | Identifying name of the PropertySource |
| `getSource()` | Underlying data object wrapped by the source |
| `getProperty(String)` | Looks up the value of a property name |
| `containsProperty(String)` | Checks existence according to the source's behavior |
| `toString()` | Representation for diagnostics; should not log secret values |

Not every `PropertySource` is a `Map`. The underlying source object can be a map, Java `Properties`, environment variables, servlet context, a config data structure, or even a dynamic lookup provided by a library.

**Do not mutate the underlying data just because `getSource()` returns a Map.** Mutability, immutability, thread safety, and how the source updates depend on the implementation. For adding configuration values, choose an appropriate implementation or create a new PropertySource.

### 3.1. A PropertySource Represents Only One Source

Suppose a source named `baseDefaults` has:

```text
shop.currency = VND
shop.max-items = 20
```

It does not know that a command-line source above it might provide `shop.max-items=50`. Precedence order is determined by the **external collection of PropertySources**, not by `MapPropertySource` itself.

Therefore:

```java
propertySource.getProperty("shop.max-items")
```

and:

```java
environment.getProperty("shop.max-items")
```

can yield different results. The first call queries **exactly one source**; the second traverses the **ordered chain of sources**.

## 4. Common PropertySource Types

In Spring Framework and Spring Boot, there are several implementations or groups of implementations to recognize.

| Type/Group | Role |
| --- | --- |
| `MapPropertySource` | Exposes data from a `Map<String, Object>` as a PropertySource |
| `PropertiesPropertySource` | Wraps a `java.util.Properties` object |
| `SystemEnvironmentPropertySource` | Adapts property lookup to environment variables |
| `CompositePropertySource` | Combines multiple child sources into one composite source in certain scenarios |
| Spring Boot Config Data sources | Represent data loaded from `application.yml`, `application.properties`, imports, and corresponding config locations |
| Custom PropertySource | Implements custom lookup logic when built-in implementations are not sufficient |

The implementation class names and source names appearing in an application may vary depending on the Spring Boot version, startup phase, and source type. When creating a static source in learning examples, **`MapPropertySource`** is usually the easiest choice.

### 4.1. MapPropertySource Example

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

MapPropertySource defaults = new MapPropertySource(
    "shopDefaults",
    Map.of(
        "shop.currency", "VND",
        "shop.max-items", 20,
        "shop.enabled", true
    )
);
```

Here:

- `"shopDefaults"` is the **source name**, not a property name.
- `"shop.currency"` is a **property name** inside the source.
- Values have type `Object`, because a Map can hold strings, numbers, and booleans.
- `defaults.getProperty("shop.max-items")` returns the numeric object `20` as stored.
- `defaults.getProperty("missing")` returns `null`.

When using `Environment.getProperty("shop.max-items")`, the `getProperty(String)` interface typically returns a `String` resolved/converted as appropriate. Do not rely on the raw result of `MapPropertySource` and the resolver result always having the same runtime type.

## 5. How Does ConfigurableEnvironment Extend Environment?

`Environment` provides **read** capabilities for the environment state, such as:

```java
String value = environment.getProperty("shop.currency");
String[] profiles = environment.getActiveProfiles();
```

`ConfigurableEnvironment` additionally provides APIs to **configure** the environment, especially:

```java
MutablePropertySources sources = environment.getPropertySources();
```

Imports:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;
```

You can obtain `ConfigurableEnvironment` when inside a valid Spring Boot extension point, or from `ConfigurableApplicationContext`.

For example, in an `ApplicationRunner`:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner inspectSources(
        ConfigurableApplicationContext context) {
    return args -> {
        ConfigurableEnvironment env = context.getEnvironment();

        for (PropertySource<?> source : env.getPropertySources()) {
            System.out.println(source.getName());
        }
    };
}
```

Additional imports:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
```

The example prints the PropertySource **names**, not their full contents. That helps inspect precedence order without accidentally logging passwords, tokens, or sensitive information in `Environment`.

### 5.1. Why Is It Called Configurable?

Because it provides configuration operations such as managing sources, selecting profiles, or other environment configuration capabilities. However, the ability to mutate the object **does not mean every running bean automatically updates immediately** when the source list is modified.

In many applications, `@Value` and `@ConfigurationProperties` are evaluated at bean creation time. If a new source is added **after** beans have already been created, subsequent `Environment.getProperty(...)` calls can see the new value, while already-injected or bound fields retain their old values.

That is why the timing of extending the environment matters just as much as precedence order.

## 6. MutablePropertySources Is an Ordered List

`MutablePropertySources` belongs to:

```java
org.springframework.core.env.MutablePropertySources
```

It manages `PropertySource<?>` entries by **source name** and **order**.

Key operations:

| Method | Effect |
| --- | --- |
| `addFirst(source)` | Places the source at the highest-priority position |
| `addLast(source)` | Places the source at the lowest-priority position |
| `addBefore(existingName, source)` | Inserts the source before a source with a known name |
| `addAfter(existingName, source)` | Inserts the source after a source with a known name |
| `replace(name, source)` | Replaces the source with that name with a new source |
| `remove(name)` | Removes the source by name |
| `get(name)` | Retrieves the source by name |
| `contains(name)` | Checks whether the collection contains a source with that name |
| `iterator()` | Iterates over sources in precedence order |

The word **"before"** means **higher priority** in the lookup sequence; **"after"** means **lower priority**.

```text
MutablePropertySources
  index 0: commandLineArgs  (example of a high-priority source)
  index 1: configDataA
  index 2: configDataB
  index 3: customDefaults
  index 4: systemEnvironment
  ...
```

This list only illustrates how indexing works, **not a guarantee of the real default order**. In an application, every source addition should stem from a clear goal and the actual existing source order, rather than treating the diagram as an immutable rule.

### 6.1. PropertySource Names Must Be Meaningful and Managed

Names like `"regionDefaults"`, `"tenantOverrides"`, or `"externalServiceDefaults"` help with diagnostics. Avoid generic names such as `"properties"` or `"custom"` if multiple libraries add sources.

When using `addBefore` or `addAfter`, you must know that **the anchor source name exists**. If that name is absent from the list, the operation can throw `IllegalArgumentException`. Therefore, extension code should check and handle this appropriately rather than assuming every Boot version uses the exact same source names.

Do not arbitrarily call `replace("systemEnvironment", ...)` or `remove("commandLineArgs")` just to achieve a temporary effect; built-in sources may be relied upon by the framework and other libraries.

## 7. First Experiment: addFirst and addLast

To clarify ordering without depending on whatever environment variables happen to exist on a real machine, we can create a test `ConfigurableEnvironment` using `MockEnvironment` from `spring-test`.

Example unit test or experimental program in test sources:

```java
import java.util.Map;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

public class PriorityDemo {

    public static void main(String[] args) {
        ConfigurableEnvironment env = new MockEnvironment()
                .withProperty("shop.currency", "VND");

        MutablePropertySources sources = env.getPropertySources();

        sources.addLast(new MapPropertySource(
                "fallbackRegion",
                Map.of("shop.currency", "USD",
                       "shop.region", "global")
        ));

        System.out.println(env.getProperty("shop.currency"));
        System.out.println(env.getProperty("shop.region"));

        sources.addFirst(new MapPropertySource(
                "emergencyOverride",
                Map.of("shop.currency", "EUR")
        ));

        System.out.println(env.getProperty("shop.currency"));
    }
}
```

Because `MockEnvironment` has a `mockProperties` source containing `shop.currency=VND`, the `fallbackRegion` source placed at the end does not override it.

Expected output:

```text
VND
global
EUR
```

Explanation:

1. `addLast(fallbackRegion)` provides `shop.region` because the initial source does not contain that key.
2. `shop.currency` remains `VND` because `mockProperties` has higher priority.
3. `addFirst(emergencyOverride)` puts `EUR` ahead of both sources, so the resolver picks `EUR`.

This example also shows that **a source does not need to contain every key**. It can contribute a new key without altering keys already provided by higher-priority sources.

### 7.1. Reading the Result in Table Form

| Source order for `shop.currency` | Provided values | Result |
| --- | --- | --- |
| Only `mockProperties` | VND | VND |
| `mockProperties` → `fallbackRegion` | VND → USD | VND |
| `emergencyOverride` → `mockProperties` → `fallbackRegion` | EUR → VND → USD | EUR |

It is not true that the last registered source always wins. **Position in `MutablePropertySources`**, not registration time, determines precedence.

## 8. addBefore and addAfter: Controlling Relative Position

When you do not want to place a source at the very beginning or very end, you can position it relative to an existing source.

Suppose we have a test environment:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment env = new MockEnvironment();
MutablePropertySources sources = env.getPropertySources();

sources.addFirst(new MapPropertySource(
        "applicationOverrides",
        Map.of("feature.limit", 50)
));

sources.addAfter("applicationOverrides", new MapPropertySource(
        "regionalSettings",
        Map.of("feature.limit", 40,
               "feature.region", "SEA")
));

sources.addAfter("regionalSettings", new MapPropertySource(
        "globalDefaults",
        Map.of("feature.limit", 30)
));
```

The order is now:

```text
applicationOverrides
        |
        v
regionalSettings
        |
        v
globalDefaults
        |
        v
mockProperties
```

Result:

```java
env.getProperty("feature.limit")   // "50"
env.getProperty("feature.region")  // "SEA"
```

If we place `regionalSettings` (or a new source) **before** `applicationOverrides`:

```java
sources.addBefore("applicationOverrides", new MapPropertySource(
        "urgentRegionalRules",
        Map.of("feature.limit", 70)
));
```

then `feature.limit` becomes `"70"`. The reason is that `urgentRegionalRules` is placed before the source that previously held `50`.

### 8.1. Safely Inserting a Source When Unsure If the Anchor Name Exists

Example:

```java
String anchor = "applicationOverrides";

if (sources.contains(anchor)) {
    sources.addAfter(anchor, new MapPropertySource(
            "regionalDefaults",
            Map.of("feature.currency", "VND")
    ));
} else {
    sources.addLast(new MapPropertySource(
            "regionalDefaults",
            Map.of("feature.currency", "VND")
    ));
}
```

The `addLast` fallback here means **low priority**. However, in a real project, not every missing anchor should be handled silently. If the design requires the source to sit directly after a critical source, a missing anchor might be a configuration error that should stop startup.

You need a clear policy decision: *if the anchor is missing, add at low priority, skip, or fail fast?*

## 9. replace and remove: Replacing Sources, Not Just Adding Values

`MutablePropertySources` also supports replacing or removing sources.

Example:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment env = new MockEnvironment();

env.getPropertySources().addFirst(new MapPropertySource(
    "currentRules",
    Map.of("rules.max-items", 10,
           "rules.enabled", true)
));

System.out.println(env.getProperty("rules.max-items")); // 10

env.getPropertySources().replace(
    "currentRules",
    new MapPropertySource(
        "currentRules",
        Map.of("rules.max-items", 25,
               "rules.enabled", false)
    )
);

System.out.println(env.getProperty("rules.max-items")); // 25

env.getPropertySources().remove("currentRules");

System.out.println(env.getProperty("rules.max-items")); // null
```

In this snippet:

- `replace` replaces the **registered source** by name.
- `remove` removes the entire source with the matching name.
- After removal, if no other source provides `rules.max-items`, `getProperty(...)` returns `null`.
- If a lower-priority source provides the same key, the resolver can continue to see the value from that lower source instead of `null`.

This is a change to the **structure of the source list**, not a direct edit of a line in YAML.

### 9.1. Why Should You Not Use replace to Modify Built-In Sources?

Sources such as system properties, environment variables, and Config Data may be expected to exist by other components. Replacing a built-in source with an arbitrary Map can:

- Lose keys used by libraries.
- Bypass special lookup mechanisms of the original source.
- Create discrepancies between test and production environments.
- Make diagnosing precedence order harder.
- Affect runtime configuration in unrelated places.

Typically, if you want to override a few keys, **adding a new PropertySource with those keys** is a clearer and less risky option than replacing an entire existing source.

## 10. PropertySource Is Not a Map Merging All Sources

Let us distinguish two structures:

```text
A. PropertySource A
   { "shop.currency": "VND", "shop.limit": 10 }

B. PropertySource B
   { "shop.currency": "USD", "shop.region": "global" }

MutablePropertySources:
   [ A, B ]
```

The `Environment` result:

```text
shop.currency -> VND
shop.limit    -> 10
shop.region   -> global
```

However, this **does not mean** Spring Boot creates a single physical Map and overwrites the initial map. `Environment` normally performs value resolution across an ordered collection of `PropertySource` instances.

Keeping sources separate has benefits:

1. Explains which source a value came from when appropriate diagnostic tools are used.
2. Allows adding or removing a group of properties as a single unit.
3. Supports implementations with custom lookup mechanisms that are not necessarily enumerable.
4. Preserves source ownership by module, library, or startup phase.
5. Supports specialized precedence and value conversion mechanisms.

If a PropertySource is constructed from a mutable Map, mutating the underlying Map can affect lookup results depending on the implementation. However, that approach is usually harder to control than a deliberate update strategy and does not automatically guarantee that already-bound beans will update.

## 11. Writing a Custom PropertySource

`MapPropertySource` fits data already stored in a Map. If you need to determine values using custom logic when a key is queried, you can extend `PropertySource<T>`.

For example, a source that provides only two fixed computed keys without network access:

```java
package com.example.config;

import org.springframework.core.env.PropertySource;

public final class CalculatedPropertySource
        extends PropertySource<String> {

    public CalculatedPropertySource(String deploymentId) {
        super("calculatedDeployment", deploymentId);
    }

    @Override
    public Object getProperty(String name) {
        if ("deployment.instance-name".equals(name)) {
            return "worker-" + getSource();
        }

        if ("deployment.features.audit".equals(name)) {
            return "true";
        }

        return null;
    }
}
```

How to register it:

```java
sources.addLast(new CalculatedPropertySource("blue"));
```

When no higher-priority source provides those keys:

```text
deployment.instance-name  -> worker-blue
deployment.features.audit -> true
```

Because `getProperty` returns `null` for unsupported keys, the resolver continues searching lower-priority sources.

### 11.1. Characteristics of a Good Custom Source

A custom `PropertySource` should:

- Have a **unique, stable, and meaningful** name.
- Return `null` when it does not manage a key.
- Produce deterministic results for the same inputs within a single application initialization, unless there is a genuine dynamic requirement.
- Avoid performing heavy I/O or network queries on every `getProperty` call.
- Not log secrets when someone looks up a sensitive key.
- Have synchronization/thread-safety mechanisms if the underlying data changes concurrently.
- Distinguish genuinely absent values from empty strings.
- Have unit tests for both supported and unsupported keys.

If a source must call a secret store or remote API every time a property is read, consider lifecycle, caching, timeouts, and failover mechanisms. Network calls inside `getProperty` can occur during the **application startup phase**, causing external failures to block context creation.

Usually, it is better to gather the required data once at an appropriate phase and put it into a controlled `MapPropertySource`.

## 12. Combining Configuration Sources with @ConfigurationProperties

A key found by `Environment` still needs to be bound into a Java object properly.

Example:

```java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(
        String currency,
        int maxItems,
        boolean enabled
) {}
```

In the application:

```java
@SpringBootApplication
@EnableConfigurationProperties(ShopProperties.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Required imports:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
```

We can supply the keys:

```text
shop.currency
shop.max-items
shop.enabled
```

using a new source, for example:

```java
new MapPropertySource(
    "shopRegionalDefaults",
    Map.of(
        "shop.currency", "VND",
        "shop.max-items", "30",
        "shop.enabled", "true"
    )
)
```

If the source is registered **early enough** and is not overridden by a higher-priority source, the Binder can bind those three values into `ShopProperties`, converting `"30"` to `int 30` and `"true"` to `boolean true`.

### 12.1. Reading Environment Directly Differs from Binder

`Environment.getProperty("shop.max-items")` performs a lookup for a single property name. Spring Boot's `@ConfigurationProperties` adds relaxed binding and conversion mechanisms for property names and Java types.

For example, the Java field `maxItems` can bind from the canonical name `shop.max-items`. However, do not assume every custom PropertySource is automatically understood by Spring like a Config Data source with the exact same metadata, origin tracking, and normalization rules.

When creating property names yourself, use **canonical lowercase kebab-case** such as `shop.max-items` and `shop.delivery-timeout` to align with Boot's standard conventions.

### 12.2. Registering a Source After Bean Creation Does Not Trigger Automatic Rebinding

Suppose `ShopProperties` has already been created with `maxItems=20`. An `ApplicationRunner` adds:

```java
environment.getPropertySources().addFirst(
    new MapPropertySource(
        "lateOverride",
        Map.of("shop.max-items", "99")
    )
);
```

A subsequent call to `environment.getProperty("shop.max-items")` may see `99`, but `shopProperties.maxItems()` may still be `20` because the record was already constructed earlier. **Do not use ApplicationRunner as the official way to supply values that startup beans themselves need to receive.**

To add a source before configuration beans are initialized, use an appropriate extension point such as `EnvironmentPostProcessor`.

## 13. Timing of Extending Environment in the Spring Boot Lifecycle

A simplified startup model:

```text
SpringApplication.run(...)
          |
          v
Create and prepare Environment
          |
          v
EnvironmentPostProcessor / Config Data processing
          |
          v
Prepare ApplicationContext
          |
          v
Bean definitions + @ConfigurationProperties binding
          |
          v
Bean initialization and dependency injection
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
Application serves requests
```

This simplified diagram illustrates the rationale for choosing an extension point; the detailed event sequence depends on the Spring Boot version.

Conceptually:

- **`EnvironmentPostProcessor`** is suitable for adding a `PropertySource` during environment preparation, **before the context creates regular beans**.
- **`ApplicationContextInitializer`** can also customize the context/environment before refresh, but keep in mind that certain decisions such as logging or Config Data processing may have already occurred.
- **`@PropertySource`** on a `@Configuration` class is processed during the context's configuration registration phase; it is often **too late** for properties that Spring Boot needs to read very early.
- **`ApplicationRunner`** runs after context initialization. It is suitable for **observing** or demonstrating, not ideal for changing values already consumed by beans.

If a property affects `spring.main.*`, logging, or config loading location selection, the timing of providing it is especially important. A source added too late may fail to affect decisions that have already been made.

## 14. Using EnvironmentPostProcessor to Add Defaults

Practical example: an application wants to supply defaults for its operating region without overriding data provided by the deployer.

We create an `EnvironmentPostProcessor` that adds the source **to the end of the list**.

### 14.1. RegionDefaultsEnvironmentPostProcessor Class

```java
package com.example.config;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class RegionDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    public static final String SOURCE_NAME =
            "regionDefaultPropertySource";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        MutablePropertySources sources =
                environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        MapPropertySource defaults = new MapPropertySource(
                SOURCE_NAME,
                Map.of(
                    "shop.currency", "VND",
                    "shop.max-items", "30",
                    "shop.enabled", "true"
                )
        );

        sources.addLast(defaults);
    }
}
```

Observations:

- The processor receives `ConfigurableEnvironment` and `SpringApplication`.
- The source is given a distinct name `regionDefaultPropertySource`.
- `contains` prevents duplicate registration under the same name if the processor is invoked again in special circumstances.
- `addLast` expresses the policy: **this is a low-priority fallback**, not a mandatory override.
- The hardcoded data in `Map.of` is illustrative. A real application can load from a controlled source and handle input errors.

### 14.2. Registering EnvironmentPostProcessor

In many Spring Boot 3.x versions, `EnvironmentPostProcessor` is registered via:

```text
src/main/resources/META-INF/spring.factories
```

Contents:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.config.RegionDefaultsEnvironmentPostProcessor
```

The `\` at the end of the first line is for line continuation in Java properties files. You can also write it on a single line if preferred.

This is a **processor registration mechanism at startup**, not a bean declaration via `@Component` or `@Bean`. A processor prepares the environment before the context builds beans; you should not rely on component scanning creating it later.

Across different Spring Boot generations, verify the extension point registration mechanism supported by your project's version. The example above describes the common workflow in Spring Boot 3.

### 14.3. Testing with a YAML File

```yaml
# application.yml
shop:
  currency: USD
  enabled: false
```

The default source provides:

```text
shop.currency = VND
shop.max-items = 30
shop.enabled = true
```

If Config Data sources have higher priority than `regionDefaultPropertySource`:

```text
shop.currency  -> USD    (from YAML)
shop.enabled   -> false  (from YAML)
shop.max-items -> 30     (from fallback source)
```

This is the expected behavior of a default source. The deployer only needs to declare the values they want to change; unconfigured keys receive defaults from the supplementary source.

### 14.4. When to Use addFirst?

If a requirement genuinely needs keys from a new source to **beat existing sources**, `addFirst` can be used. However, consider carefully:

```java
sources.addFirst(new MapPropertySource(
    "forcedPolicy",
    Map.of("shop.enabled", "false")
));
```

This can prevent `--shop.enabled=true` on the command line from beating the `forcedPolicy` source, depending on the source list at the time it is applied. In real products, unexpectedly overriding a deployer's choice can make diagnostics difficult.

For **defaults**, use `addLast` or a clearly designed low position. For **mandatory policies**, clearly explain why the new source must take precedence and verify its impact on remaining sources.

## 15. Ordering Between EnvironmentPostProcessor Implementations

An application can have multiple processors:

```text
Config Data processor
Library defaults processor
Deployment-specific processor
Organization policy processor
...
```

Processor execution order and the final order of `PropertySource` entries are **two distinct things to separate**:

1. Processor order determines **who gets the chance to modify the environment and when**.
2. Source order in `MutablePropertySources` determines **which key wins during lookup**.

A processor running later **does not mean** the source it adds must have higher priority. It can still call `addLast` to place its source at the end of the list.

With a class implementing `Ordered`, you can specify the desired order:

```java
import org.springframework.core.Ordered;

public final class RegionDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE - 100;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        // Add PropertySource here
    }
}
```

This illustrates the API; if combining with the complete example in the previous section, keep the required imports, constants, and logic. **Do not treat `-100` relative to `LOWEST_PRECEDENCE` as a universal rule for every extension point.** When a project needs to intervene before/after Config Data, check the actual processor order and constants of the Boot version in use.

Avoid executing logic that depends on config loaded **after** your processor. For instance, a processor running before Config Data might not yet see a property located in `application.yml`.

If the requirement is to create a configuration source integrated into the Config Data mechanism itself, study more specialized extension points; not every config import need should be handled with a simple `EnvironmentPostProcessor`.

## 16. How Do @PropertySource and PropertySource in Environment Differ?

`@PropertySource` is a Spring Framework annotation for adding a source from a resource when a `@Configuration` class is processed.

Example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:shipping-defaults.properties")
public class ShippingDefaultsConfiguration {
}
```

In `shipping-defaults.properties`:

```properties
shipping.connect-timeout=3s
shipping.max-attempts=4
```

The annotation adds properties from a `.properties` file into `Environment` during a context processing phase. Note the distinctions:

| Mechanism | Timing / Purpose |
| --- | --- |
| `@PropertySource` | Registers a source via Spring context configuration |
| `EnvironmentPostProcessor` | Modifies the environment during application preparation |
| `application.yml` / `spring.config.import` | Config Data sources processed by Spring Boot |
| `MutablePropertySources.addFirst/addLast` | Direct manipulation of the source collection at the call site |

Note: standard `@PropertySource` does not automatically handle YAML in the same way as Spring Boot's Config Data. If you want to use YAML with `@PropertySource`, an appropriate `PropertySourceFactory` may be needed. For typical Spring Boot application configuration, **`application.yml` and Config Data** are the more natural integration path.

In particular, `@PropertySource` is usually processed too late for certain very early startup properties, such as settings needed before context refresh. Therefore, do not choose this annotation for every "Environment extension" goal.

## 17. Do Not Arbitrarily Modify Environment Inside a @Bean or Service

The snippet below can alter subsequent property lookups:

```java
@Service
public class ShippingService {

    public ShippingService(ConfigurableEnvironment environment) {
        environment.getPropertySources().addFirst(
            new MapPropertySource(
                "shippingRuntimeOverride",
                Map.of("shipping.max-attempts", "99")
            )
        );
    }
}
```

However, this is a design to avoid because:

- Bean creation order affects configuration outcomes.
- A business bean interferes with shared configuration infrastructure.
- Beans created earlier may retain old values.
- Other beans created later may receive the new value, causing inconsistent state.
- Testing the service becomes heavily container-dependent.
- Behavior differs across startups if dependency ordering changes.

Services should receive data via `@ConfigurationProperties` or typed dependencies. If you need to modify application-wide configuration sources, do so at a **deliberately chosen configuration/extension layer**.

Separation of responsibilities:

```text
EnvironmentPostProcessor
        |
        v
MapPropertySource
        |
        v
ConfigurableEnvironment
        |
        v
Spring Boot Binder
        |
        v
ShippingProperties
        |
        v
ShippingService
```

The business layer only consumes the provided values and does not own the mechanism deciding source ordering.

## 18. Difference Between "Replacing a Source" and "Refreshing Beans"

Suppose startup creates a bean:

```java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(int retryLimit) {}
```

with `service.retry-limit=3`.

After the context is running, some code alters the sources via:

```java
environment.getPropertySources().addFirst(
    new MapPropertySource(
        "newRuntimeSettings",
        Map.of("service.retry-limit", "8")
    )
);
```

Two observations may differ:

```java
environment.getProperty("service.retry-limit"); // "8"
serviceProperties.retryLimit();                  // 3
```

This is not a Binder bug. The `ServiceProperties` bean was already constructed and bound in the previous state; the record is not automatically recreated.

An application may also have:

- Beans using `@Value` already injected.
- Clients constructed with timeouts at startup.
- Infrastructure beans reading configuration in constructors.
- Code calling `Environment` directly on each use.

Components have different **configuration observation times**. Therefore, dynamically changing sources without a synchronized refresh mechanism can lead to inconsistent configuration state.

If the system needs runtime configuration changes, design it explicitly: snapshots, lifecycle management, client recreation, cross-thread synchronization, refresh scopes, or a dedicated configuration management platform. `MutablePropertySources` alone **does not provide** an application-wide refresh protocol.

## 19. How Does PropertySource Order Affect Placeholders?

Suppose there are two sources:

```text
highPriority:
  api.host = prod.internal

lowPriority:
  api.host = localhost
  api.url  = http://${api.host}:8080
```

When `Environment` resolves `api.url`, it takes the template from the lower source because the higher source does not declare `api.url`; inside the template, `${api.host}` is normally resolved against the entire `Environment`. Thus the host can become `prod.internal`.

Expected result:

```text
http://prod.internal:8080
```

Implications:

- The source containing the template does not necessarily hold the final values of every placeholder.
- A placeholder can reference keys overridden by another source.
- To understand a final URL, check both the **URL key** and the **component keys** in precedence order.
- If a higher source directly overrides `api.url`, the template in the lower source is no longer the chosen target value.

A test example:

```java
MockEnvironment env = new MockEnvironment();
MutablePropertySources sources = env.getPropertySources();

sources.addLast(new MapPropertySource(
    "urlTemplate",
    Map.of(
        "api.host", "localhost",
        "api.url", "http://${api.host}:8080"
    )
));

sources.addFirst(new MapPropertySource(
    "hostOverride",
    Map.of("api.host", "prod.internal")
));

System.out.println(env.getProperty("api.url"));
```

With placeholder resolution configured in Spring `Environment`, the result is `http://prod.internal:8080`.

## 20. Diagnostics: Printing Source Order Without Exposing Values

A safe diagnostic utility should focus on **source names, positions, and pre-specified key names**, without printing all values.

Example:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertySourceInspector {

    private PropertySourceInspector() {}

    public static void printNames(ConfigurableEnvironment env) {
        int index = 0;

        for (PropertySource<?> source : env.getPropertySources()) {
            System.out.println(
                index + " : " + source.getName()
            );
            index++;
        }
    }

    public static void printPresence(
            ConfigurableEnvironment env,
            String key) {

        for (PropertySource<?> source : env.getPropertySources()) {
            if (source.containsProperty(key)) {
                System.out.println(
                    "found in " + source.getName()
                );
                return;
            }
        }

        System.out.println("key not found in listed sources");
    }
}
```

`printPresence` is strictly observational. It does not print values. Furthermore, because some sources have custom lookup rules or associated converters, iterating and calling `containsProperty` directly does not always reflect all special semantics of the Binder.

**Do not treat this utility as absolute proof for every source and every style of relaxed binding.** It is useful for inspecting source structure and specific key names in a known environment.

In Spring Boot, Actuator provides the `env` endpoint for configuration diagnostics when properly enabled. This endpoint can contain sensitive information and has value-masking rules. Do not expose diagnostic endpoints to public networks just to inspect source order.

## 21. Do Not Confuse Source Indices and Names Across Spring Boot Versions

Some tutorials show a fixed list:

```text
commandLineArgs
systemProperties
systemEnvironment
applicationConfig: [...]
...
```

This list may only hold true for **a single Spring Boot version or a specific runtime condition**. Spring Boot has Config Data, config imports, testing sources, and many sources added by auto-configuration or libraries.

Differences between runs include:

- Presence or absence of command-line arguments.
- Presence or absence of external config files outside the JAR.
- Which profiles are active.
- Whether `spring.config.import` is used.
- Presence of test properties or `@DynamicPropertySource`.
- Presence of library `EnvironmentPostProcessor` implementations.
- Running as a servlet web, reactive web, test, or console application.

When inserting a source using `addBefore` or `addAfter`, rely on **actual source names verified at that exact extension point**. Do not hardcode a Config Data source name containing path details and expect it to exist everywhere.

If the goal is simply a fallback, `addLast` generally depends less on internal source names.

## 22. Sources with the Same Key Where the Value Is an Empty String

An easily misunderstood case:

```text
highPriority:
  app.display-name = ""

lowPriority:
  app.display-name = "Default App"
```

When `Environment` looks up `app.display-name`, the higher-priority source may return an **empty string**; an empty string is still a non-`null` value. The result is usually `""`, not `"Default App"`.

To illustrate:

```java
MockEnvironment env = new MockEnvironment();
MutablePropertySources sources = env.getPropertySources();

sources.addLast(new MapPropertySource(
    "fallback",
    Map.of("app.display-name", "Default App")
));

sources.addFirst(new MapPropertySource(
    "explicitEmpty",
    Map.of("app.display-name", "")
));

System.out.println(
    "[" + env.getProperty("app.display-name") + "]"
);
```

Output:

```text
[]
```

Key takeaway: **a PropertySource returning `null` usually causes the resolver to keep searching**, whereas an empty string can block the fallback. If a value must be non-empty, enforce it with validation or business rules rather than relying solely on placing a default source at the end.

## 23. Some Values Cannot Be Used Directly with Map.of

`Map.of(...)` in Java does not allow `null` keys or values. When a dynamic data source has missing values, attempting to construct a Map via `Map.of("key", null)` fails immediately, even before Spring binds anything.

If you need a structure that tolerates `null` while preparing data:

```java
Map<String, Object> values = new HashMap<>();
values.put("shop.currency", "VND");
// Do not add a key with null just to mark it as missing.
```

A `MapPropertySource` can accept data from a mutable Map, but **`null` values normally mean the property is absent** during resolution. To rely on defaults, it is better to omit unpopulated keys from the source or resolve defaults at an appropriate place.

In a multithreaded application, do not share a continuously mutated `HashMap` and let multiple threads look up keys directly without synchronization. For mostly immutable configuration, creating a snapshot and registering the source once is simpler.

## 24. When to Use ConfigurableEnvironment Instead of Environment?

A helpful design rule:

- Business beans needing a few values: prefer **`@ConfigurationProperties`** or typed dependencies.
- Code that only needs to look up a property name: use **`Environment`** if appropriate.
- An extension point that needs to **add or order PropertySources**: use **`ConfigurableEnvironment`**.
- A component that needs to build a special source: write a **`PropertySource`** or use **`MapPropertySource`**, then register it at the right time.
- Tests needing controlled configuration overrides: use **`MockEnvironment`**, `ApplicationContextRunner`, or Spring Boot's test property mechanisms.

Do not inject `ConfigurableEnvironment` into every service just because the interface offers more capabilities. The authority to alter application-wide configuration sources is an infrastructure responsibility; handing it to many business beans makes code unpredictable.

## 25. Unit Testing Precedence Order with MockEnvironment

A test using JUnit 5 and AssertJ:

```java
package com.example.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

class PropertySourcesPriorityTest {

    @Test
    void firstPropertySourceWins() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("feature.limit", "20");

        MutablePropertySources sources = env.getPropertySources();

        sources.addLast(new MapPropertySource(
            "defaults",
            Map.of("feature.limit", "10",
                   "feature.name", "catalog")
        ));

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("20");
        assertThat(env.getProperty("feature.name"))
                .isEqualTo("catalog");

        sources.addFirst(new MapPropertySource(
            "overrides",
            Map.of("feature.limit", "50")
        ));

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("50");
    }

    @Test
    void removingOverrideRevealsLowerPriorityValue() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("feature.limit", "20");

        MutablePropertySources sources = env.getPropertySources();

        sources.addFirst(new MapPropertySource(
            "overrides",
            Map.of("feature.limit", "50")
        ));

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("50");

        sources.remove("overrides");

        assertThat(env.getProperty("feature.limit"))
                .isEqualTo("20");
    }
}
```

This test only requires `spring-test` along with JUnit/AssertJ on the test classpath (usually included in `spring-boot-starter-test`). It does not start a Spring Boot application context, needs no `application.yml` file, and does not alter real environment variables.

One benefit of testing without a Spring context is **not depending on the source ordering set up by a specific Boot version**. We deliberately construct the order and verify the outcome of each operation.

## 26. Testing addBefore, addAfter, and replace

Example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

class MutablePropertySourcesOperationsTest {

    @Test
    void orderAndReplacementAreObservable() {
        MockEnvironment env = new MockEnvironment();
        MutablePropertySources sources = env.getPropertySources();

        sources.addFirst(new MapPropertySource(
            "defaults",
            Map.of("sample.mode", "basic")
        ));

        sources.addBefore("defaults", new MapPropertySource(
            "regional",
            Map.of("sample.mode", "regional")
        ));

        assertThat(env.getProperty("sample.mode"))
                .isEqualTo("regional");

        sources.replace("regional", new MapPropertySource(
            "regional",
            Map.of("sample.mode", "enterprise")
        ));

        assertThat(env.getProperty("sample.mode"))
                .isEqualTo("enterprise");

        sources.remove("regional");

        assertThat(env.getProperty("sample.mode"))
                .isEqualTo("basic");
    }
}
```

This tests the **structure of the source list**. It verifies that a source placed earlier is looked up first, replacing a source by name changes the result, and removing a source reveals the lower-priority value.

In a real application, do not call `replace` or `remove` periodically just because the API exists. If dynamic configuration is needed, thread safety and bean lifecycle issues also arise.

## 27. Unit Testing EnvironmentPostProcessor in Isolation

You do not need to run a packaged JAR to verify that a processor adds a source correctly.

With `RegionDefaultsEnvironmentPostProcessor` from section 14, we can test the core logic:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.mock.env.MockEnvironment;

class RegionDefaultsEnvironmentPostProcessorTest {

    @Test
    void addsOnlyLowPriorityFallbackValues() {
        MockEnvironment env = new MockEnvironment()
                .withProperty("shop.currency", "USD");

        RegionDefaultsEnvironmentPostProcessor processor =
                new RegionDefaultsEnvironmentPostProcessor();

        processor.postProcessEnvironment(
                env, new SpringApplication(Object.class)
        );

        assertThat(env.getProperty("shop.currency"))
                .isEqualTo("USD");
        assertThat(env.getProperty("shop.max-items"))
                .isEqualTo("30");

        assertThat(env.getPropertySources()
                .contains("regionDefaultPropertySource")).isTrue();
    }
}
```

This test proves the logic puts the source lower than `mockProperties`. However, **it does not replace a bootstrapping integration test** to verify that `META-INF/spring.factories` is discovered, or that the processor runs at the right time relative to Config Data in a real project.

When you need to test the full pipeline, run a small Spring Boot test/application and observe the values bound into `@ConfigurationProperties`. Keeping unit tests and startup tests separate makes failure analysis easier.

## 28. A Safe Environment Extension Strategy

Suppose a company needs to add a default source for multiple applications, such as `organizationDefaults`. It should be designed as follows:

1. **Define source responsibility**: only provide permitted keys, such as `org.region` and `org.timeout`.
2. **Choose precedence**: if it is only defaults, add at the end; if it is a mandatory policy, clearly document why it must take high priority.
3. **Give the source a stable name** that does not collide with framework or library source names.
4. **Register at an early extension point** if beans need to receive the values at startup.
5. **Do not replace entire built-in sources** to override a few keys.
6. **Do not load sensitive data and log** the constructed Map.
7. **Return null for unmanaged keys** when writing a custom PropertySource.
8. **Check existing sources** before performing relative insertions with `addBefore/addAfter`.
9. **Write precedence unit tests** and binding integration tests.
10. **Document how to remove the source** or restore configuration if an extension is disabled.

The key is maintaining observability and predictability. An undocumented custom source that "wins everything" can suddenly render command-line arguments passed by operators ineffective.

## 29. When Should You Not Create a Custom PropertySource?

Not every configuration requirement needs extending `ConfigurableEnvironment`.

If the goal is to read another YAML file, Spring Boot already has Config Data, config locations, and `spring.config.import`. If the goal is to group multiple properties into a class, `@ConfigurationProperties` can handle that without a custom source.

If you want default values for a few keys, sometimes you only need:

```yaml
# application.yml
shop:
  currency: VND
  max-items: 30
```

If you want profile-specific overrides:

```yaml
# application-prod.yml
shop:
  max-items: 50
```

If you want deployment-environment-specific values, use appropriate environment variables or command-line arguments. All of these approaches are generally simpler than creating a new source in code.

Consider `EnvironmentPostProcessor` or a custom PropertySource only when there is a genuine need such as:

- A library wanting to provide default values across multiple applications.
- A system integrating with a configuration source outside standard loading mechanisms.
- Needing to supply a custom-structured group of keys during environment preparation.
- Needing deliberate precedence control between a custom source and existing sources.
- A product needing to package infrastructure configuration rules into a testable module.

Avoid choosing a more complex mechanism merely because it allows deeper intervention.

## 30. Common Mistakes

### 30.1. Assuming addLast Always Wins

`addLast` places the source at the end of the list; typically this source only provides values when higher-priority sources **have no value** for the corresponding key.

### 30.2. Assuming a Source Added Later Has Higher Priority

Chronological registration order does not determine precedence. `addFirst`, `addLast`, and relative insertion operations determine position.

### 30.3. Forgetting That the Source Name Is an Identifier

`addBefore("missingName", custom)` can fail when the anchor name does not exist. Use `contains` or design explicit fail-fast behavior.

### 30.4. Using @PropertySource for Properties Needed Very Early

Some startup properties are processed before `@Configuration` is read. `@PropertySource` can be too late to affect them.

### 30.5. Registering Custom Sources Inside a Service

This makes business logic depend on bean initialization order and global mutable state. Use an appropriate infrastructure extension point instead.

### 30.6. Thinking Modifying PropertySources Refreshes @ConfigurationProperties

Updating the resolver may reveal new values; already-bound beans generally are not recreated automatically. A separate refresh mechanism is required for runtime updates.

### 30.7. Calling getProperty on a Single Source and Assuming It Is the Final Value

`source.getProperty(key)` reads only that specific source. `environment.getProperty(key)` evaluates multiple sources in order.

### 30.8. Logging the Entire Source Map

A source may contain passwords or tokens. Print source names or controlled harmless keys rather than logging all values.

### 30.9. Relying on Fixed Source Indices

Applications may add Config Data, profiles, test sources, command-line args, or library processors. Actual order varies across environments and versions.

### 30.10. Confusing an Empty String with an Absent Value

A source providing `""` can block lower sources from being chosen. Adding a default at the last source does not automatically fix empty strings.

### 30.11. Trying to Use Custom Sources for Every YAML Import

If the problem is simply adding a configuration file, consider Spring Boot's Config Data mechanism first. Do not reimplement file loading, profile handling, and precedence logic without a special requirement.

### 30.12. Ignoring the Difference Between String Properties and Binder

`Environment.getProperty` and `@ConfigurationProperties` are related but not identical in relaxed binding, conversion, and object structure. For custom keys, test both direct lookups and binding.

## 31. Hands-On Exercises

### Exercise 1: Predicting Order

Given three sources in order:

```text
A: app.mode=alpha, app.region=north
B: app.mode=beta,  app.timeout=2s
C: app.mode=gamma, app.feature=true
```

Predict:

- `app.mode` resolves to `alpha`.
- `app.region` resolves to `north`.
- `app.timeout` resolves to `2s`.
- `app.feature` resolves to `true`.

Then add source D using `addFirst` with `app.mode=delta`. The resulting mode will become `delta`.

### Exercise 2: Choosing the Right Operation

Requirements:

1. Add a lowest-priority default source.
2. Add a highest-priority source.
3. Add a source right after a known source.
4. Replace an old source by name.
5. Remove a source when no longer needed.

Corresponding answers:

```java
sources.addLast(defaults);
sources.addFirst(overrides);
sources.addAfter("knownSource", regional);
sources.replace("oldSource", replacement);
sources.remove("oldSource");
```

In cases 3 and 4, ensure the source name exists. In case 5, check whether removing the source exposes another value from a lower-priority source.

### Exercise 3: Source Containing an Empty String

A higher source declares `app.label=""`, and a lower source declares `app.label="Default"`. Explain why the result is usually an empty string rather than `Default`, and what validation mechanism might be appropriate if `label` must have content.

### Exercise 4: Custom PropertySource

Write a `PropertySource<String>` that returns `"acme-" + getSource()` for the key `app.instance-id`, and `null` for all other keys. Register it with `addLast` and verify it can be looked up from `Environment` when no higher source exists.

### Exercise 5: EnvironmentPostProcessor

Create `RegionDefaultsEnvironmentPostProcessor` with:

```text
shop.currency = VND
shop.max-items = 30
```

Use `addLast`. Register it via `META-INF/spring.factories` according to your project version, then run with YAML declaring only `shop.currency=USD`. Predict that the properties object receives currency `USD` and maxItems `30`.

### Exercise 6: Changing Sources After the Context Is Running

A `@ConfigurationProperties` bean has bound `shop.max-items=20`. Afterward, add a source at the front of the list providing `99`. Compare `Environment.getProperty("shop.max-items")` with `ShopProperties.maxItems()`. Why is it necessary to separate runtime lookups from already-bound snapshots?

### Exercise 7: Replacing a Source

Create a source `rulesDefaults` providing `rules.limit=10`, then call `replace("rulesDefaults", ...)` to provide `25`. Next, call `remove("rulesDefaults")`. Explain the final value both when another source provides `rules.limit` and when none does.

### Exercise 8: Spotting Dangerous Design

A service has a constructor that adds a high-priority source with the key `spring.main.banner-mode`. Explain:

- Why service creation time is too late to reliably change startup settings.
- Why a service should not modify the application-wide environment.
- Which extension point is more suitable if you truly need to supply a very early property.
- Why precedence should be tested and built-in sources should not be arbitrarily overridden.

### Exercise 9: Finding the Overriding Source

YAML sets `service.timeout=2s`, yet the program receives `5s`. Outline the diagnostic sequence:

1. Read the source names in order.
2. Check whether command-line arguments, system properties, environment variables, or custom sources provide the key.
3. Inspect sources placed before YAML.
4. Inspect the target key and any dependent placeholders.
5. Check at what point the bean was bound.
6. Avoid printing secrets while tracing sources.

### Exercise 10: Distinguishing Two Extension Points

Design two solutions:

- Adding `defaults.properties` via `@PropertySource`.
- Adding `MapPropertySource` via `EnvironmentPostProcessor`.

Explain why the two approaches can differ in **when** the data becomes present in the environment, and why certain properties needed early should not be handled via `@PropertySource`.

## 32. Summary

`PropertySource`, `MutablePropertySources`, and `ConfigurableEnvironment` form Spring's powerful configuration extension model.

```text
PropertySource<T>
  -> a single key-based lookup source

MutablePropertySources
  -> an ordered collection of sources that can be added, replaced, or removed

ConfigurableEnvironment
  -> an Environment capable of configuring sources
     and other environment properties
```

Core rules:

1. **Sources placed earlier have higher priority** in standard lookup order.
2. **`addFirst` has high priority; `addLast` has low priority.** Do not confuse registration timing with precedence.
3. **`getProperty` on a single source differs from `Environment.getProperty`.** One queries only a single place; the other checks sources in order.
4. **A PropertySource name is an identifier for management.** `addBefore`, `addAfter`, and `replace` depend on exact names.
5. **Default sources should be placed low** so deployers can still override values.
6. **Add sources early enough** if values must be present before `@ConfigurationProperties` or infrastructure beans are created.
7. **Changing a source does not mean refreshing beans.** Already-injected or bound fields typically retain their previous values.
8. **Configuration extension belongs to the infrastructure layer**, not business services.
9. **Diagnose carefully**: inspect source order without logging secrets.
10. **Prefer built-in Config Data mechanisms** if the requirement is simply loading standard configuration files.

The best mental model:

```text
          [Property Sources]
         /        |         \
       CLI      YAML      Custom
         \        |         /
          v       v        v
         MutablePropertySources
                  |
                  v
         ConfigurableEnvironment
                  |
                  v
         Binder / @Value / Bean
```

Once you understand this chain, you can answer why one value overrides another, where to introduce a new default, and why modifying `Environment` at runtime does not automatically update every bean.

Official documentation for further study:

- [Spring Framework — PropertySource API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html)
- [Spring Framework — MutablePropertySources API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html)
- [Spring Framework — ConfigurableEnvironment API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — EnvironmentPostProcessor API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html)
