# Adding Sources with addFirst, addLast, addBefore, and addAfter

## 1. Context: Why Extend the Spring Environment?

Spring Boot lets you externalize configuration from source code using many sources such as:

- `application.yml` and `application.properties`;
- profile-specific configuration files;
- process environment variables;
- Java system properties;
- command-line arguments;
- sources loaded via the Config Data mechanism;
- sources added by the application itself or integrated libraries.

In real-world deployments, an application sometimes also needs to read configuration from **a custom place**: a tenant settings table, a configuration database, a company-managed file, an in-memory value source, or an integration library.

Spring Framework provides the `Environment` and `PropertySource` abstractions to represent these sources. A `PropertySource` holds a named set of properties, while `Environment` provides a way to resolve values across multiple sources in precedence order.

Example:

```yaml
# application.yml
demo:
  message: "Value from YAML"
  retries: 3
```

The application may want to add a source with:

```text
demo.message = "Value from tenant"
```

The final outcome depends on the **position of the new source** relative to existing sources. That is the job of `MutablePropertySources` and the four operations covered in this lesson:

- `addFirst(...)`;
- `addLast(...)`;
- `addBefore(...)`;
- `addAfter(...)`.

**Goal:** know exactly where these four methods place a new source, how they affect the effective values, how to integrate into Spring Boot at the right time, and how to avoid accidentally overriding operational configuration.

## 2. Three Foundational Concepts

### 2.1. Environment

`org.springframework.core.env.Environment` is the interface used to access properties and profile information.

Example:

```java
import org.springframework.core.env.Environment;

String message = environment.getProperty("demo.message");
String active = String.join(",", environment.getActiveProfiles());
```

`Environment#getProperty("demo.message")` does not necessarily read directly from a YAML file. It returns the value resolved from the current system of property sources.

### 2.2. PropertySource

`org.springframework.core.env.PropertySource<T>` represents a property source with an **identifying name** and an object holding data.

A common implementation is:

```java
org.springframework.core.env.MapPropertySource
```

It allows a `Map<String,Object>` to act as a configuration source:

```java
Map<String, Object> values = new HashMap<>();
values.put("demo.message", "Hello from custom source");
values.put("demo.retries", 5);

MapPropertySource source =
        new MapPropertySource("tenantOverrides", values);
```

The name `tenantOverrides` is the **name of the source**, not the name of a configuration key. The source name helps you identify where that source is placed in the precedence list.

### 2.3. MutablePropertySources

`org.springframework.core.env.MutablePropertySources` is an **ordered and mutable** collection of `PropertySource<?>`.

It provides operations to add, remove, replace, check existence, and move a source by re-adding a source with an existing name.

To access the mutable source collection in an application, you typically use:

```java
ConfigurableEnvironment configurableEnvironment = ...;

MutablePropertySources propertySources =
        configurableEnvironment.getPropertySources();
```

Plain `Environment` only provides read capabilities. The `ConfigurableEnvironment` interface extends it with operations to configure the source collection.

## 3. Most Important Rule: Earlier Sources Have Higher Priority

Imagine a list of sources:

```text
Position 1 — commandLineArgs             (high priority)
Position 2 — systemProperties
Position 3 — systemEnvironment
Position 4 — customDefaults
Position 5 — application.yml             (lower priority)
```

This is an **illustrative diagram**, not a guarantee of the full positions or internal names of all PropertySources across every Spring Boot version.

When the application queries:

```java
environment.getProperty("demo.message");
```

the system searches sources in priority order. Under standard property resolution, **the highest-priority source containing a non-null value for that key** provides the result.

Example:

| Source | `demo.message` |
| --- | --- |
| Source A, high priority | `"A"` |
| Source B, low priority | `"B"` |
| Source C, lower priority | `"C"` |

The result is `"A"`.

If A does not have the key `demo.message`, Spring continues searching in B. A PropertySource does not have to declare every key; it only contributes the keys actually present in it.

**Do not confuse "adding a source" with "rewriting values in application.yml".** When adding a `MapPropertySource`, you are modifying the in-memory source collection of `Environment`, not editing the YAML file on disk.

## 4. How to Obtain MutablePropertySources

Inside a Spring `ApplicationContext` that supports environment configuration:

```java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;

ConfigurableEnvironment environment =
        context.getEnvironment();

MutablePropertySources sources =
        environment.getPropertySources();
```

Here `context` is a `ConfigurableApplicationContext`.

If you are only given an `Environment` interface, do not assume every implementation supports mutation:

```java
if (environment instanceof ConfigurableEnvironment configurable) {
    MutablePropertySources sources = configurable.getPropertySources();
    // Manipulate sources when truly needed.
}
```

In a standard Spring Boot application, the application environment is typically an implementation of `ConfigurableEnvironment`. However, a shared API accepting `Environment` should respect the distinction between the read interface and the configuration interface.

The methods used in this lesson live on `MutablePropertySources`, rather than being called directly on `Environment`.

## 5. addFirst: Placing a Source at the Front of the List

### 5.1. Syntax

```java
propertySources.addFirst(propertySource);
```

Meaning: inserts the specified source at the **front of the list**. For `PropertySources` precedence order, the front of the list is normally the highest-priority position.

Example:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

MapPropertySource override = new MapPropertySource(
        "emergencyOverrides",
        Map.of("demo.message", "Priority from new source")
);

MutablePropertySources sources = environment.getPropertySources();
sources.addFirst(override);
```

In a situation where the new source genuinely sits at the front of lookup, `demo.message` from `emergencyOverrides` can override the value of the same name provided by lower sources.

### 5.2. Diagram

Before:

```text
1. sourceA    demo.message=A
2. sourceB    demo.message=B
```

Execute:

```java
sources.addFirst(
    new MapPropertySource(
        "prioritySource",
        Map.of("demo.message", "P")
    )
);
```

After:

```text
1. prioritySource    demo.message=P
2. sourceA           demo.message=A
3. sourceB           demo.message=B
```

The lookup result for `demo.message` is `P`.

### 5.3. When to Use It?

`addFirst` is appropriate when **the new source is allowed to beat existing sources** for the keys it declares, such as a system-managed override layer with a clearly designed precedence rule.

However, it is also the riskiest operation if used carelessly.

If you put a MapPropertySource at the front and it contains:

```properties
server.port=9090
spring.profiles.active=prod
logging.level.root=DEBUG
```

you can change how subsequent components see those values, but **you cannot assume every completed startup decision will be recomputed**. In particular, choices regarding Config Data, profiles, or logging may have already been processed before you added the source.

Only use `addFirst` with keys and at lifecycle timings whose processing lifecycle you clearly understand.

## 6. addLast: Placing a Source at the End as a Fallback Layer

### 6.1. Syntax

```java
propertySources.addLast(propertySource);
```

Meaning: adds the source at the **end of the list**, giving it lower priority than existing sources.

Example:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

propertySources.addLast(new MapPropertySource(
        "companyDefaults",
        Map.of(
                "demo.message", "Fallback value",
                "demo.retries", 2
        )
));
```

If a higher-priority source already declares `demo.message`, that value is used. If no source above provides that key, `companyDefaults` can contribute the fallback value.

### 6.2. Diagram

Before:

```text
1. sourceA     demo.message=A
2. sourceB     demo.message=B
```

After:

```java
sources.addLast(
    new MapPropertySource(
        "fallback",
        Map.of("demo.message", "F")
    )
);
```

List:

```text
1. sourceA     demo.message=A
2. sourceB     demo.message=B
3. fallback    demo.message=F
```

The result is still `A`, not `F`.

Only if neither `sourceA` nor `sourceB` has `demo.message` can the result be `F`.

### 6.3. When to Use It?

`addLast` is useful for:

- a library's set of defaults;
- fallback values when the deployer has not configured them;
- a low-priority set of experimental values;
- systems following "application configuration beats library defaults".

For configuration defaults, you can also use `@DefaultValue` or default values in config files. Choosing a dedicated fallback source fits best when multiple values are supplied by a module and need to be managed as a clear source layer.

## 7. addBefore: Inserting Before a Specified Source

### 7.1. Syntax

```java
propertySources.addBefore(
        "sourceName",
        newPropertySource
);
```

The first parameter is the **name of an existing source**. The new source will be placed **immediately before that source**.

Because a source placed earlier has higher priority, `addBefore("sourceName", ...)` typically makes the new source beat the target source when both declare the same key, though **not necessarily every other source ahead of it**.

### 7.2. Example

Initial list:

```text
1. commandLine
2. deploymentOverrides
3. libraryDefaults
```

Run:

```java
sources.addBefore(
        "libraryDefaults",
        new MapPropertySource(
                "teamDefaults",
                Map.of("demo.message", "Team")
        )
);
```

Result:

```text
1. commandLine
2. deploymentOverrides
3. teamDefaults
4. libraryDefaults
```

`teamDefaults` beats `libraryDefaults` on overlapping keys, while still sitting behind `commandLine` and `deploymentOverrides`.

### 7.3. Case Needing Controlled Priority

Suppose a library publishes a `libraryDefaults` source to provide default values. The application wants to add internal defaults **stronger** than the library's but still **weaker** than values supplied by operational users.

`addBefore("libraryDefaults", companyDefaults)` expresses that exact policy without using `addFirst` to override all remaining sources.

This approach is especially useful when you control the target source name and guarantee it actually exists.

## 8. addAfter: Inserting After a Specified Source

### 8.1. Syntax

```java
propertySources.addAfter(
        "sourceName",
        newPropertySource
);
```

The new source is inserted **immediately after** the source named `sourceName`, so it has lower priority than the target source but higher priority than sources following it.

### 8.2. Example

Initially:

```text
1. commandLine
2. deploymentOverrides
3. libraryDefaults
```

Execute:

```java
sources.addAfter(
        "deploymentOverrides",
        new MapPropertySource(
                "tenantFallback",
                Map.of("demo.message", "Tenant")
        )
);
```

Result:

```text
1. commandLine
2. deploymentOverrides
3. tenantFallback
4. libraryDefaults
```

`tenantFallback` does not beat `deploymentOverrides` on duplicate keys, but it can beat `libraryDefaults`.

### 8.3. When to Use It?

`addAfter` is appropriate when:

- an original source holds higher priority than custom values;
- you want to add supplementary configuration immediately after a source you manage;
- you need to ensure a new source has a specific relative position without placing it at the front or end.

For example, a system wants **operator-supplied configuration** to take priority over tenant configuration, while still letting tenant configuration beat library defaults.

## 9. Quick Comparison of the Four Methods

Suppose the initial source list is:

```text
[ A, B, C ]
```

Operations with a new source `X`:

| Operation | Result |
| --- | --- |
| `addFirst(X)` | `[X, A, B, C]` |
| `addLast(X)` | `[A, B, C, X]` |
| `addBefore("B", X)` | `[A, X, B, C]` |
| `addAfter("B", X)` | `[A, B, X, C]` |

Viewed from a priority perspective:

```text
Start of list                            End of list
high priority                            low priority
      |                                           |
      v                                           v
      A  ->  B  ->  C  ->  D  ->  E
```

If two sources both contain `demo.message`, the source closer to the start of the list normally wins when resolving that key.

**Important:** these four methods do not change the **data values** of an existing `PropertySource`; they change the **position/precedence relationship** of sources. If the new source is a Map with completely different keys, moving the source may not change the values currently being queried.

## 10. Standalone Java Example: Observing Order and Results

To learn exactly how the four operations work, you can use a Java example **without starting Spring Boot**.

```java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySourcesPropertyResolver;

public class PropertySourcesOrderingDemo {

    public static void main(String[] args) {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(new MapPropertySource(
                "base",
                Map.of("demo.message", "BASE")
        ));

        sources.addFirst(new MapPropertySource(
                "operator",
                Map.of("demo.message", "OPERATOR")
        ));

        sources.addAfter("operator", new MapPropertySource(
                "tenant",
                Map.of("demo.message", "TENANT")
        ));

        sources.addBefore("base", new MapPropertySource(
                "team",
                Map.of("demo.message", "TEAM")
        ));

        sources.addLast(new MapPropertySource(
                "finalFallback",
                Map.of("demo.message", "FALLBACK")
        ));

        for (var source : sources) {
            System.out.println(source.getName());
        }

        var resolver = new PropertySourcesPropertyResolver(sources);

        System.out.println("demo.message = "
                + resolver.getProperty("demo.message"));
    }
}
```

Resulting source name order:

```text
operator
tenant
team
base
finalFallback
demo.message = OPERATOR
```

**Why?**

1. `base` is added at the end of an empty collection.
2. `operator` is added at the front, so it precedes `base`.
3. `tenant` is placed after `operator`, before `base`.
4. `team` is placed before `base`, i.e., after `tenant`.
5. `finalFallback` is added last.

`PropertySourcesPropertyResolver` resolves properties from a standalone `MutablePropertySources`. This is a way to observe ordering rules without the noise of default sources from a real Boot application.

## 11. When a New Source Lacks a Key, Spring Continues Searching

Consider:

```java
MutablePropertySources sources = new MutablePropertySources();

sources.addFirst(new MapPropertySource(
        "highPriority",
        Map.of("demo.message", "HIGH")
));

sources.addLast(new MapPropertySource(
        "lowPriority",
        Map.of(
                "demo.message", "LOW",
                "demo.retries", 7
        )
));
```

When querying:

```java
var resolver = new PropertySourcesPropertyResolver(sources);

resolver.getProperty("demo.message"); // "HIGH"
resolver.getProperty("demo.retries"); // "7" as a String when read as String
```

The `highPriority` source only has `demo.message`, so Spring continues looking up `demo.retries` in the lower source.

Having a PropertySource at the front does not mean every property is blocked by that source.

### 11.1. Null Values and Empty Strings

In standard PropertySource resolution, a source returning `null` for a key is interpreted as having no matching value, so searching can continue.

However, an **empty string** `""` is a provided value. For example:

```java
sources.addFirst(new MapPropertySource(
        "override",
        Map.of("demo.message", "")
));
```

The empty value can beat a non-empty string from a lower-priority source.

This is a common cause of the bug "I set a default below, yet the application still gets an empty string". Distinguish **absent key** from **key with an empty value**.

## 12. addBefore/addAfter Require an Existing Source Name

The two methods using relative positions must locate the anchor source.

Example:

```java
sources.addBefore(
        "sourceThatDoesNotExist",
        new MapPropertySource(
                "mySource",
                Map.of("demo.message", "Hello")
        )
);
```

If the anchor source name does not exist, the operation cannot determine the insertion point and may throw `IllegalArgumentException`.

In real code, check before using:

```java
String anchor = "companyDefaults";

MapPropertySource custom = new MapPropertySource(
        "tenantSettings",
        Map.of("demo.message", "tenant")
);

if (sources.contains(anchor)) {
    sources.addBefore(anchor, custom);
} else {
    sources.addLast(custom);
}
```

This is only **an illustrative fallback policy**. If the system strictly requires `companyDefaults` to be present, silently falling back to `addLast` could mask a configuration error. In that case, reject it with a clear message:

```java
if (!sources.contains(anchor)) {
    throw new IllegalStateException(
            "Missing anchor source: " + anchor);
}
sources.addBefore(anchor, custom);
```

Choose handling according to the system's contract rather than silently falling back to an arbitrary position when the anchor name is wrong.

## 13. PropertySource Name Is the Source Management Identifier

Each PropertySource has a name so `MutablePropertySources` can identify it when finding, replacing, and inserting sources relatively.

Example:

```java
new MapPropertySource(
        "customTenantSource",
        Map.of("demo.message", "Tenant")
);
```

In the example, `customTenantSource` is the **source name**, whereas `demo.message` is the **key name**.

Two sources with different names can contain the same key:

```text
customTenantSource: demo.message=Tenant
companyDefaults:   demo.message=Company
```

That is normal; precedence order decides the effective value.

However, you should **choose distinct and stable source names**. If you attempt to add a new source with the same name as an existing one, `MutablePropertySources` manages entries by name rather than maintaining two independent elements with the same name like a regular list.

When using `addFirst` or `addLast` with a PropertySource whose name already exists, the implementation may remove the old entry and place the source at the new position. This reorders an existing source rather than creating two copies.

To avoid tracking confusion, use namespaced names, such as:

```text
acmeTenantOverrides
acmeRemoteDefaults
acmeFeatureFlags
```

and document in the design which component manages these sources.

## 14. Observing PropertySources Names and Order

To see which sources exist, you can list **source names**:

```java
import org.springframework.core.env.ConfigurableEnvironment;

public static void printPropertySourceNames(
        ConfigurableEnvironment environment) {

    int index = 0;

    for (var source : environment.getPropertySources()) {
        System.out.printf("%d. %s%n",
                ++index, source.getName());
    }
}
```

An environment can contain sources for:

- command-line arguments;
- system properties;
- system environment;
- Config Data;
- temporary property sources from tests;
- custom sources;
- composite or internal Spring Boot sources.

**Do not write code depending on a fixed internal name list** if those names are not part of the public contract of a component you control. Config Data source names may include path details or change across versions and loading mechanisms.

### 14.1. Avoid Printing All Values

You can print source names for diagnostics, but you should not iterate over every key and print every value in production: a PropertySource can contain tokens, passwords, API keys, or sensitive configuration data.

To inspect a non-sensitive key:

```java
System.out.println(
        "demo.message = "
        + environment.getProperty("demo.message")
);
```

For secrets, check only presence or use observability tools that mask sensitive values.

## 15. Introducing a Custom Configuration Source into Spring Boot

Moving from the standalone example, let us integrate into a real application.

Suppose we want to provide values:

```text
demo.message = "Hello from tenant"
demo.retries = 5
```

into `Environment` before Spring creates business beans.

An easy-to-understand approach is using `ApplicationContextInitializer`.

### 15.1. Creating the Initializer

```java
package com.example.configdemo;

import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class TenantPropertySourceInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        MutablePropertySources sources =
                context.getEnvironment().getPropertySources();

        MapPropertySource tenantSource = new MapPropertySource(
                "acmeTenantOverrides",
                Map.of(
                        "demo.message", "Hello from tenant",
                        "demo.retries", 5
                )
        );

        sources.addFirst(tenantSource);
    }
}
```

Here:

- `MapPropertySource` creates a source from a Map.
- `acmeTenantOverrides` is the source's dedicated name.
- `addFirst` requests placing the source at the front of the list when the initializer runs.
- Properties can subsequently be read by Spring via `Environment` and the binder.

### 15.2. Registering the Initializer at Startup

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ConfigDemoApplication.class);

        application.addInitializers(
                new TenantPropertySourceInitializer()
        );

        application.run(args);
    }
}
```

The initializer is called during the ApplicationContext preparation phase, before the refresh that creates regular singleton beans. For configuration keys that beans read during subsequent creation, this is a useful moment to add a PropertySource.

**Important limitation:** an initializer **is not the earliest extension point** in Spring Boot. Config Data, profile selection, part of logging setup, and Environment preparation decisions may have already been processed before the initializer runs. Adding `spring.config.import` or `spring.profiles.active` here does not mean the entire configuration loading pipeline will be recomputed.

If the goal is simply supplying business values like `demo.message` or `demo.retries` for beans created after the initializer, the example above is clear and appropriate.

## 16. Reading the New Source with @ConfigurationProperties

Continuing the example, create a record:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String message,
        int retries) {
}
```

Register using:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    // The main method registers the initializer as in the previous section.
}
```

The `application.yml` file:

```yaml
demo:
  message: "Value from YAML"
  retries: 3
```

Because the initializer adds:

```text
demo.message = Hello from tenant
demo.retries = 5
```

to a high-priority source in the example, the `DemoProperties` bean bound afterward can receive the two values from the custom source.

Use a runner to observe:

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class DemoPrinter implements ApplicationRunner {

    private final DemoProperties properties;

    public DemoPrinter(DemoProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("message=" + properties.message());
        System.out.println("retries=" + properties.retries());
    }
}
```

Expected output:

```text
message=Hello from tenant
retries=5
```

Note: this result assumes the example sources have no other special mechanisms intervening. In practice, check the PropertySource list and `Environment#getProperty(...)` results after the initializer if the application has many custom extensions.

## 17. Should a Custom Source Beat Command-Line Arguments?

Suppose the application is run with:

```bash
java -jar app.jar --demo.message="Value from CLI"
```

And your initializer calls:

```java
sources.addFirst(tenantSource);
```

When `tenantSource` is at the front of the list at read time, it can **beat even values passed via command-line arguments** for the key `demo.message`.

This differs from Spring Boot's default precedence rules, where application arguments normally have higher priority than regular Config Data sources.

**An important design decision:** do you really want application code adding a data source in a position authorized to override configuration provided by the operator?

If the answer is no, avoid calling `addFirst` just because it is convenient. You can:

- place the custom source at the end with `addLast` if it is defaults;
- use `addAfter` relative to a source you manage and have a reliable anchor for;
- design a Config Data source using Spring Boot's supported mechanisms if it needs to participate in the system's precedence policy;
- clearly document in deployment docs which source is allowed to beat which.

Choosing the right **position** is just as important as choosing the right **value**.

## 18. Comparing addFirst and addLast in the Same Application

`application.yml` file:

```yaml
demo:
  message: "YAML"
  retries: 3
```

Custom source:

```java
MapPropertySource source = new MapPropertySource(
        "companySettings",
        Map.of(
                "demo.message", "COMPANY",
                "demo.retries", 6
        )
);
```

If using:

```java
sources.addFirst(source);
```

then the new source is placed at the front and can produce:

```text
demo.message = COMPANY
demo.retries = 6
```

If using:

```java
sources.addLast(source);
```

then the YAML configuration can still win:

```text
demo.message = YAML
demo.retries = 3
```

The source at the end still takes effect for a key that sources above **do not declare**.

For example, if only `companySettings` has `demo.region=vn`, the application can still read `demo.region=vn`, even though `companySettings` sits last.

This is why `addLast` generally fits **supplementary default** sources, whereas `addFirst` represents **deliberate override** sources.

## 19. Relative Insertion Against an Application-Created Source

When using `addBefore` and `addAfter`, it is best to have an **anchor source you control** instead of relying on internal Config Data names.

Example:

```java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class PropertySourceLayers {

    public static void install(MutablePropertySources sources) {
        sources.addLast(new MapPropertySource(
                "acmeLibraryDefaults",
                Map.of(
                        "demo.message", "Library",
                        "demo.retries", 1
                )
        ));

        sources.addBefore(
                "acmeLibraryDefaults",
                new MapPropertySource(
                        "acmeTenantDefaults",
                        Map.of("demo.message", "Tenant")
                )
        );

        sources.addAfter(
                "acmeTenantDefaults",
                new MapPropertySource(
                        "acmeRegionalDefaults",
                        Map.of("demo.region", "vn")
                )
        );
    }
}
```

Among the three sources we manage, the order is:

```text
acmeTenantDefaults
acmeRegionalDefaults
acmeLibraryDefaults
```

However, because all three sources are built atop the existing list via `addLast` followed by relative insertions, they can still sit **behind the application's existing sources**.

This lets operators use `application.yml` or other higher-placed sources to override library defaults, while the library's default layers maintain a clear internal order.

## 20. Do Not Blindly Rely on Internal Boot PropertySource Names

In a real application, you may see Config Data source names describing paths to `application.yml`, import locations, or Boot-generated names.

Code like:

```java
sources.addBefore(
        "Config resource 'class path resource [application.yml]' ...",
        customSource
);
```

breaks easily if:

- configuration is switched from YAML to Properties;
- the application uses additional profiles;
- paths change;
- a Spring Boot version changes how sources are named;
- the file is loaded from outside the JAR;
- configuration is imported rather than being a standard file.

Do not copy a PropertySource name observed in logs on one machine and treat it as a stable API across all environments.

Instead, you can:

1. Give unique names to sources you create.
2. Use `addBefore`/`addAfter` with source names you control.
3. Provide explicit fallbacks if an optional anchor is absent.
4. For Config Data-style precedence requirements, consider the Config Data mechanism instead of manually inserting around an internal name.

## 21. When Should Environment Extension Be Performed?

**The timing of modifying sources** determines which components can observe the new values.

Common phases:

```text
SpringApplication.run()
       |
       v
Prepare Environment
       |
       +-- Load Config Data / handle related profiles
       |
       v
Prepare ApplicationContext
       |
       +-- ApplicationContextInitializer
       |
       v
Refresh ApplicationContext
       |
       +-- create beans
       +-- resolve @Value
       +-- bind @ConfigurationProperties
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
Application serves requests
```

This is a **simplified diagram**. Individual Boot subsystems may process configuration at different times; do not infer that every startup decision happens in a single step.

### 21.1. Initializer

Useful when needing to add a PropertySource **before Spring creates regular application beans**. This is an approachable choice for learning examples.

### 21.2. EnvironmentPostProcessor

Appropriate when needing to intervene in the earlier Environment preparation phase and integrate with Spring Boot's startup process.

However, processor ordering matters. An EnvironmentPostProcessor running too early might not see Config Data; a processor running later also does not cause completed decisions to be re-executed.

### 21.3. @PostConstruct or ApplicationRunner

If you add a PropertySource at these points, many beans may already have been created and bound with old values. Reading `Environment` directly afterward can see the new values, but already-injected `@Value` fields or already-created `@ConfigurationProperties` beans **do not automatically receive updated values**.

Therefore, do not use overly late timings just hoping the whole application will "automatically update configuration".

## 22. EnvironmentPostProcessor for Early Integration Cases

Spring Boot provides the SPI:

```java
org.springframework.boot.env.EnvironmentPostProcessor
```

It lets you modify `ConfigurableEnvironment` while preparing the application environment.

Example:

```java
package com.example.configdemo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class CompanyDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "acmeCompanyDefaults",
                        Map.of(
                                "demo.retries", 2,
                                "demo.region", "vn"
                        )
                )
        );
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
```

The example uses `addLast` because it only wants to provide fallback values. `Ordered.LOWEST_PRECEDENCE` expresses an intent to run late among processors using ordered sorting, **not a guarantee across every startup subsystem or every other extension**.

### 22.1. Registering the Processor

In Spring Boot 3.x, a common registration approach is placing:

```text
src/main/resources/META-INF/spring.factories
```

with contents:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.configdemo.CompanyDefaultsEnvironmentPostProcessor
```

When starting via a supported Boot mechanism, Spring Boot can discover the implementation declared here.

**Do not confuse** declaring `EnvironmentPostProcessor` via `spring.factories` with the `AutoConfiguration.imports` list meant for auto-configuration. The two extension types have different responsibilities.

Depending on your Spring Boot version or application build framework, follow the corresponding SPI guide. If a processor needs to run before or after Config Data processing, inspect the specific ordering of processors rather than picking an arbitrary number.

## 23. When Is EnvironmentPostProcessor Still Not the Right Solution?

Suppose you want a remote file to decide:

```properties
spring.profiles.active=prod
spring.config.import=...
```

Manually adding a source via `addFirst` at an arbitrary time does not guarantee Spring Boot will recompute profile selection or Config Data loading order that has already occurred.

Certain configuration is used **very early** by Boot to decide how to prepare the environment. When your requirement is integrating **a new Config Data type** with file loading, profiles, and import mechanics, consider official extension points such as:

- `ConfigDataLocationResolver`;
- `ConfigDataLoader`;
- the `spring.config.import` mechanism and Boot-supported config locations.

A `MapPropertySource` added by an initializer may suit **business values** but does not fully replace the Config Data loading mechanism.

**Principle:** if the new source only supplies `demo.*` for beans, manipulating PropertySources may suffice; if the new source defines startup/config resolution itself, evaluate earlier and more specialized extension points.

## 24. How Is Adding a PropertySource via @PropertySource Different?

In Spring Framework, there is the annotation:

```java
@PropertySource("classpath:company.properties")
```

to declare a Properties source for the context.

Example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:company.properties")
public class CompanyPropertyConfiguration {
}
```

This mechanism differs from manually calling:

```java
sources.addFirst(...);
sources.addLast(...);
sources.addBefore(...);
sources.addAfter(...);
```

With `@PropertySource`, Spring processes the annotation while building the ApplicationContext; you do not directly specify its position using those four operations.

In particular, Spring Boot documentation notes that `@PropertySource` is added during the context refresh phase, which **may be too late** to affect certain very early properties, such as startup and logging settings.

If you need exact precedence order or a specific source-addition timing, manipulating `ConfigurableEnvironment` at an appropriate lifecycle point gives clearer control.

However, "more control" does not mean "everything should be done with addFirst". For ordinary file configuration, Boot's built-in Config Data mechanism is usually the less complex choice.

## 25. Custom Sources Can Be Read via Environment

Suppose an initializer adds:

```java
MapPropertySource source = new MapPropertySource(
        "myRuntimeSettings",
        Map.of(
                "demo.message", "Hello",
                "demo.retries", 4
        )
);

environment.getPropertySources().addFirst(source);
```

Then:

```java
String message = environment.getProperty("demo.message");
Integer retries = environment.getProperty(
        "demo.retries",
        Integer.class
);
```

Expected values in a simple context:

```text
message = Hello
retries = 4
```

Spring `Environment` has type conversion mechanisms for common cases. However, do not assume every custom converter meant specifically for `@ConfigurationProperties` is automatically used identically by `Environment#getProperty(..., TargetType.class)`.

### 25.1. Interaction with @Value

A bean created after the initializer can use:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingService {

    private final String message;

    public GreetingService(
            @Value("${demo.message:Default}") String message) {
        this.message = message;
    }

    public String greeting() {
        return message;
    }
}
```

When Spring creates the bean and resolves placeholders, the custom source can already contribute the value for `demo.message`.

If you add the PropertySource **after the bean has been created**, the `message` field in this example does not change automatically.

## 26. @ConfigurationProperties and Source Ordering

A record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String message,
        int retries) {
}
```

does not need to know whether configuration came from YAML, CLI, or a Map source. Spring Boot's Binder uses the configuration sources in Environment and their corresponding binding mechanisms.

When sources are established before binding, the record receives effective values in precedence order.

That means:

```text
PropertySources ordered
      |
      v
Value resolution
      |
      v
ConfigurationProperties Binder
      |
      v
DemoProperties(message, retries)
```

**Changing the source list after the record has been created does not cause the record's constructor to re-run automatically.** Immutable configuration acts as a snapshot at normal binding time.

If you need dynamic configuration updates at runtime, you must design a refresh/rebind mechanism or recreate dependent objects, rather than just adding a PropertySource and expecting every bean to change.

## 27. Do Not Arbitrarily Modify Environment from Business Services

An order-processing service should not routinely execute:

```java
environment.getPropertySources().addFirst(...);
```

on every incoming request, because this:

1. Mutates application-wide configuration sources.
2. Can create unpredictable precedence order.
3. Does not automatically refresh beans that already received old values.
4. Causes behavior to depend on timing when multiple requests execute concurrently.
5. Makes it hard to trace which source produced the current value.
6. Risks overriding deployment policies or other system keys.

To manage dynamic or per-tenant configuration, one strategy is providing a **service that reads configuration at point of use**, with clear caching and synchronization mechanisms, instead of turning `Environment` into a per-request mutable state store.

Manipulating `MutablePropertySources` fits best during **deliberate configuration setup**, not as a technique replacing every runtime feature flag or tenant configuration system.

## 28. MapPropertySource and Map Mutability

`MapPropertySource` holds a Map containing values. If you pass in a mutable `HashMap` and continue modifying that Map, subsequent reads can see the changes.

Example:

```java
Map<String, Object> values = new HashMap<>();
values.put("demo.message", "A");

MapPropertySource source =
        new MapPropertySource("custom", values);
```

If code later performs:

```java
values.put("demo.message", "B");
```

then the Map source has been mutated.

In a multithreaded application, this behavior requires careful synchronization design. The four methods `addFirst`, `addLast`, `addBefore`, `addAfter` manage **source position**; they do not turn the backing Map into a dynamic config store with consistency, validation, auditing, or automatic refresh.

For stable values:

```java
MapPropertySource source = new MapPropertySource(
        "custom",
        Map.of("demo.message", "A")
);
```

is easier to control because the Map disallows mutating contents via standard update methods.

**Note:** `Map.of` itself does not permit `null` keys or values. If data can be `null`, handle it before constructing the Map.

## 29. Use Separate Sources for Each Purpose

A manageable way to organize sources is splitting them into meaningful layers:

```text
operatorOverrides
tenantConfiguration
regionalDefaults
libraryDefaults
```

This separation makes it possible to define clear precedence rules:

1. Are operational values allowed to override tenant values?
2. Are tenant values allowed to override regional defaults?
3. Are regional defaults allowed to override library defaults?
4. Which sources are allowed to contain Spring Boot system keys?
5. Should changes to those sources be audited?

If everything is lumped into a single `custom` source at the front, it is very hard to tell why a final value was chosen.

**Design the ordering before writing code.** Then choose `addFirst`, `addLast`, `addBefore`, and `addAfter` according to the defined policy.

## 30. Stay Safe When Adding Configuration from External Sources

A remote configuration source or tenant data store is not necessarily trustworthy to supply **every Spring Boot key**.

For example, a source intended only for tenant business settings should have a whitelist:

```text
tenant.display-name
tenant.max-items
tenant.feature-enabled
```

Instead of arbitrarily accepting:

```text
spring.*
server.*
management.*
logging.*
```

and placing all of them at the front of the list.

Safer design practices include:

- Loading only permitted keys.
- Checking types and bounds of data before building the PropertySource.
- Not logging secrets from the entire Map.
- Having a specific precedence policy.
- Adding sources at the right time and avoiding updates after beans are created.
- Testing the application with sources that have overlapping keys.
- Rejecting data that alters system behavior beyond the trust boundary.

A `MapPropertySource` is very simple in API terms, yet its scope of impact can be broad once placed in the application-wide Environment.

## 31. Directly Testing Precedence Order with JUnit

You can write unit tests without a Spring Boot context to verify the four operations.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySourcesPropertyResolver;

class MutablePropertySourcesTest {

    private static MapPropertySource source(
            String name, String value) {
        return new MapPropertySource(
                name,
                Map.of("demo.message", value)
        );
    }

    @Test
    void addFirstHasHighestPriority() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(source("base", "BASE"));
        sources.addFirst(source("override", "OVERRIDE"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("OVERRIDE",
                resolver.getProperty("demo.message"));
    }

    @Test
    void addLastActsAsFallback() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addFirst(source("primary", "PRIMARY"));
        sources.addLast(source("fallback", "FALLBACK"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("PRIMARY",
                resolver.getProperty("demo.message"));
    }

    @Test
    void addBeforePositionsSourceAheadOfAnchor() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(source("base", "BASE"));
        sources.addBefore("base", source("team", "TEAM"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("TEAM",
                resolver.getProperty("demo.message"));
    }

    @Test
    void addAfterPositionsSourceBehindAnchor() {
        MutablePropertySources sources =
                new MutablePropertySources();

        sources.addLast(source("base", "BASE"));
        sources.addAfter("base", source("fallback", "FALLBACK"));

        var resolver = new PropertySourcesPropertyResolver(sources);

        assertEquals("BASE",
                resolver.getProperty("demo.message"));
    }
}
```

The four tests check one exact thing: **which precedence outcome the PropertySources order produces**. They do not need to start a servlet container or Spring Boot application.

If a test only checks the list of source names without querying `resolver.getProperty(...)`, you might overlook that the sources hold different keys. Therefore, having at least one overlapping key to verify ordering is a very clear learning approach.

## 32. Testing Adding a Source Before Beans Are Bound

When you need to confirm that a source added by an initializer is seen by the binder, use a small test context.

Suppose:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String message) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

class CustomSourceBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withInitializer(context ->
                            context.getEnvironment()
                                    .getPropertySources()
                                    .addFirst(new MapPropertySource(
                                            "acmeTestOverrides",
                                            Map.of("demo.message", "CUSTOM")
                                    )))
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void constructorBindingSeesCustomSource() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();

            DemoProperties properties =
                    context.getBean(DemoProperties.class);

            assertThat(properties.message()).isEqualTo("CUSTOM");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DemoProperties.class)
    static class TestConfiguration {
    }
}
```

This test checks something different from a pure PropertySources unit test: **the Spring Boot binder actually creates the bean using the data added to Environment**.

It does not test every Config Data scenario or very early logging phase. For those cases, integration tests with a real startup path and corresponding extension points are needed.

## 33. Testing a Missing Anchor Source

When an application depends on a specific anchor source, test the case where the anchor name does not exist.

Example:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

class MissingAnchorTest {

    @Test
    void addBeforeNeedsExistingAnchor() {
        MutablePropertySources sources =
                new MutablePropertySources();

        assertThrows(IllegalArgumentException.class, () ->
                sources.addBefore(
                        "unknownAnchor",
                        new MapPropertySource(
                                "custom",
                                Map.of("demo.message", "A")
                        )
                )
        );
    }
}
```

If the policy requires a fallback when an optional anchor is absent, write a dedicated test for that fallback rather than merely catching and ignoring the error.

Lesson: **`addBefore` and `addAfter` depend on an existing source identifier**, so the source name is part of the contract when multiple components manage the source list together.

## 34. Relationship with SPRING_APPLICATION_JSON

Spring Boot can accept a JSON object supplied via `SPRING_APPLICATION_JSON` or a corresponding mechanism and turn it into configuration data.

This is a Boot-supported configuration source, not something you must reimplement yourself using:

```java
sources.addFirst(new MapPropertySource(...))
```

If the problem is simply providing several properties for a run, first consider built-in mechanisms such as environment variables, CLI arguments, or Config Data rather than creating a new initializer.

Customizing PropertySources is generally worthwhile when the application needs a **new data source with its own meaning**, such as an adapter translating from an internal configuration registry into properties Spring understands.

## 35. Relationship with spring.config.import

`spring.config.import` lets Spring Boot load additional configuration resources during the Config Data phase. It is part of the configuration loading mechanism integrated with profile selection and precedence ordering.

Meanwhile:

```java
environment.getPropertySources().addFirst(custom);
```

is a direct manipulation on the PropertySource list at a specific moment.

The two approaches do not share the same contract regarding:

- loading timing;
- profile handling;
- config locations;
- import rules;
- missing source errors;
- format handling and precedence between Config Data documents.

If a file or location needs to act as a configuration source following full Config Data semantics, use Spring Boot's supported capability instead of trying to emulate all those rules using the four list operations.

## 36. Relationship with @PropertySource

`@PropertySource` is a Spring Framework mechanism for declaring a Properties resource in context configuration.

`@PropertySource` can suit traditional Properties files, but it does not fully replace Spring Boot's Config Data, especially when needing profile-specific documents, imports, or early startup decisions.

The four methods of `MutablePropertySources` give you **direct control over position**, while also increasing your responsibility to understand ordering and lifecycle.

Choosing the right tool:

| Need | Typically appropriate mechanism |
| --- | --- |
| Application config via standard files | `application.yml` / `application.properties` |
| Profile-specific documents, imports | Config Data |
| Property source from an in-memory Map | `MapPropertySource` |
| Custom source position control | `MutablePropertySources` |
| Extending Environment preparation | `EnvironmentPostProcessor` |
| Adding a source before regular bean creation | `ApplicationContextInitializer` |
| Spring Framework-style Properties file | `@PropertySource`, when appropriate |

There is no reason to replace every standard configuration method with an `addFirst` call.

## 37. Common Mistakes

### 37.1. Assuming addLast Always Overrides YAML

No. `addLast` puts the source at the end, so existing sources above it can win on overlapping keys.

### 37.2. Assuming addBefore Beats All Sources

No. `addBefore("B", X)` only places X before B. If A is already before B, A can still beat X.

### 37.3. Assuming addAfter Loses to All Sources

No. `addAfter("B", X)` places X after B, but X can sit ahead of sources C and D behind it and beat them.

### 37.4. Using a Non-Existent Anchor Source Name

`addBefore`/`addAfter` must find the anchor source name. Otherwise, it may throw `IllegalArgumentException`.

### 37.5. Confusing Source Names with Configuration Keys

`MapPropertySource("mySource", Map.of("demo.message", "A"))` has the source name `mySource`. `demo.message` is not a source name to pass to `addBefore`.

### 37.6. Using addFirst Without Considering Operator Control

A source placed at the front can beat CLI or environment variables for the same key, making the application hard to adjust at deployment time.

### 37.7. Adding a Source After Beans Have Bound

Direct reads of `Environment` may see new values, but `@Value` and `@ConfigurationProperties` processed normally do not update automatically.

### 37.8. Using an Initializer Expecting Config Data to Re-Run

Config Data loading and certain startup configuration processing can happen before the initializer. To add a new Config Data source type, consider an extension at the right phase.

### 37.9. Relying on Internal Config Data Source Names

Config Data source names can change by file, profile, or version. If you need a stable anchor, prefer a source you named and control.

### 37.10. Printing the Entire Configuration Map

PropertySources may contain secrets. Only log source names or values confirmed to be non-sensitive.

### 37.11. Mutating Sources on Every Request

Mutating the application-wide Environment inside request-handling threads creates state risks and does not refresh existing beans.

### 37.12. Not Testing Order with Overlapping Keys

If tests only have disjoint keys, you have not really verified which source wins. Create at least one overlapping key across sources to test precedence.

## 38. Diagnostic Procedure When Values Are Incorrect

When `demo.message` does not match expectations after adding a PropertySource, proceed in order:

1. **Confirm Environment is the right environment of the running application.** A different test context may use a different source list.
2. **List source names in order.** No need to print sensitive values.
3. **Confirm your custom source name appears.** If not, the initializer/processor was not registered or did not run.
4. **Check the position of the new source.** Do `addFirst`, `addLast`, `addBefore`, `addAfter` match the policy?
5. **Check that the source actually contains the key.** For example, `demo.message` differs from `demo.mesage`.
6. **Check whether a higher-priority source provides the same key.**
7. **Check the timing of adding the source.** Were beans already created and bound beforehand?
8. **Check whether the value was rejected by conversion or validation.**
9. **Check profiles and Config Data.** Was a source not loaded, or loaded under a different profile?
10. **Write an isolated test with `MutablePropertySources` and `PropertySourcesPropertyResolver`.** Only then test with a Spring Boot context.

This diagnostic flow separates "wrong source order" from "wrong key", "source not registered", and "added too late".

## 39. Exercise A: Predict the Order

Initially:

```text
[A, B, C]
```

Execute:

```java
sources.addFirst(X);
sources.addAfter("B", Y);
sources.addBefore("C", Z);
sources.addLast(W);
```

Assume the existing source names exist, and `X, Y, Z, W` are new sources with distinct names.

**Question:** what is the final order?

**Answer:**

```text
[X, A, B, Y, Z, C, W]
```

Explanation:

- `X` goes to the front.
- `Y` goes after B.
- `Z` goes before C (after Y).
- `W` goes to the end.

## 40. Exercise B: Which Source Wins?

Given sources in order:

```text
1. commandLine       demo.mode=cli
2. tenantSettings    demo.mode=tenant
3. libraryDefaults   demo.mode=default
```

**Question 1:** What does `Environment#getProperty("demo.mode")` return?

**Answer:** `cli`.

**Question 2:** If `tenantSettings` is moved to the front using `addFirst`, what could the result be?

**Answer:** `tenant`.

**Question 3:** If a source `regionalSettings` with `demo.mode=region` is placed with `addAfter("tenantSettings", ...)` while the initial order is unchanged, which source wins?

**Answer:** `commandLine` still precedes `tenantSettings`, so `cli` wins.

## 41. Exercise C: Adding Defaults Without Overriding Users

The application receives user configuration via YAML and CLI. You want to supply:

```properties
demo.retries=2
demo.region=vn
```

only when other sources do not have the keys.

**Question:** which of the four methods should be used?

**Suggested answer:** `addLast`, because the source is placed at the end as a fallback.

Example:

```java
sources.addLast(new MapPropertySource(
        "acmeDefaults",
        Map.of(
                "demo.retries", 2,
                "demo.region", "vn"
        )
));
```

If the system already has multiple internally ordered defaults, `addBefore` or `addAfter` around an anchor source you manage can also be appropriate.

## 42. Exercise D: Choosing addBefore or addAfter

List:

```text
operatorSettings
tenantSettings
libraryDefaults
```

Requirement: `regionalSettings` must **lose to tenantSettings** but **beat libraryDefaults**.

One way:

```java
sources.addAfter(
        "tenantSettings",
        regionalSettings
);
```

Result:

```text
operatorSettings
tenantSettings
regionalSettings
libraryDefaults
```

Another way is `addBefore("libraryDefaults", regionalSettings)` on the initial list. Both satisfy the required precedence relationship in this scenario.

## 43. Exercise E: Why Did addBefore Fail to Run?

Code:

```java
sources.addBefore(
        "applicationConfig",
        new MapPropertySource(
                "tenantSettings",
                Map.of("demo.message", "Tenant")
        )
);
```

However, the actual source list does not contain the name `applicationConfig`.

**Conclusion:** the operation can fail because the anchor name does not exist. Do not guess internal Config Data source names from an older Spring Boot version.

**Fix:** retrieve the actual name or, better yet, use an application-defined anchor source with a stable name.

## 44. Exercise F: Adding a Source After ApplicationRunner

In an `ApplicationRunner`, you add:

```java
environment.getPropertySources().addFirst(
        new MapPropertySource(
                "lateOverride",
                Map.of("demo.message", "LATE")
        )
);
```

Previously, a singleton bean was created with:

```java
public GreetingService(
        @Value("${demo.message}") String message) {
    this.message = message;
}
```

**Question:** does the `message` field in the bean automatically change to `LATE`?

**Answer:** no. `@Value` was already resolved when the bean was created. Modifying sources afterward can affect direct reads of `Environment`, but does not automatically re-inject the field or re-run the constructor.

## 45. Takeaways

- `Environment` provides the configuration read API; `ConfigurableEnvironment` grants access to the mutable source list.
- `PropertySource` represents a named property source; `MapPropertySource` is a convenient implementation for Map-backed data.
- `MutablePropertySources` manages source ordering. **Earlier sources typically have higher priority when resolving an overlapping key.**
- `addFirst(X)` puts X at the front; `addLast(X)` puts X at the end; `addBefore("B",X)` puts X before B; `addAfter("B",X)` puts X after B.
- `addBefore` and `addAfter` require the anchor source name to actually exist. Choose unique and stable custom source names.
- Use `addLast` for fallback defaults; use `addFirst` when strong overrides are genuinely needed; use relative operations for multi-layer precedence policies.
- Extend Environment **at the right time**: `ApplicationContextInitializer` suits running before regular bean creation; `EnvironmentPostProcessor` serves the earlier environment preparation phase.
- Modifying PropertySources **does not automatically refresh** `@Value` or `@ConfigurationProperties` beans that have already received values.
- Adding a PropertySource does not replace all of Config Data, profiles, `spring.config.import`, or specialized extension points for new configuration sources.
- Avoid using custom sources to arbitrarily override system keys, avoid exposing secrets, and do not update the application-wide source list per request.
- Test precedence using `MutablePropertySources` + `PropertySourcesPropertyResolver`, then test that the binder picks up the custom source at initialization time.
