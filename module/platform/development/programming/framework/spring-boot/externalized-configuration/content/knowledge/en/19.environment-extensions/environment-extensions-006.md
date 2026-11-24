# Early Intervention with EnvironmentPostProcessor in Spring Boot

## Objective

Spring Boot supports external configuration via application.properties/application.yml files, environment variables, JVM system properties, command-line arguments, Config Data, and application-added PropertySources. In most projects, standard configuration sources suffice: groups of values are bound via **@ConfigurationProperties**, and single values can be read via **@Value** or **Environment**.

However, some platforms or libraries need to **modify Environment before the ApplicationContext is refreshed**: adding library defaults, loading custom configuration sources, supporting legacy property names, or preparing property sources so the rest of the application can consume them. **EnvironmentPostProcessor** is Spring Boot's extension point for this purpose.

Core method:

~~~java
void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application);
~~~

It allows manipulating Environment's PropertySource list during the bootstrap phase. Example:

~~~java
environment.getPropertySources().addLast(
    new MapPropertySource("companyDefaults", Map.of(
        "company.http.connect-timeout", "2s",
        "company.http.max-connections", "20"
    ))
);
~~~

The snippet above puts two default values into Environment. Placed at the end of the PropertySource list, higher-priority sources can still override these values.

After this lesson, the reader will be able to:

- Explain when an EPP runs in the Spring Boot lifecycle.
- Register processors via **META-INF/spring.factories** accurately for Spring Boot 3 or Spring Boot 4.
- Use **ConfigurableEnvironment**, **MutablePropertySources**, and **MapPropertySource** safely.
- Determine processor order relative to **ConfigDataEnvironmentPostProcessor**.
- Distinguish processor invocation order from PropertySource precedence order.
- Write processors to add defaults or a configuration file.
- Diagnose discovery, precedence, binding errors, missing files, and logging issues.
- Understand limitations regarding dependency injection, secret management, and dynamic refresh.
- Write tests verifying both processor behavior and discovery via SpringApplication.
- Know when **spring.config.import** or another hook is more suitable than EnvironmentPostProcessor.

## 1. Why Is an Early-Phase Hook Needed?

Suppose an application has an HTTP client configured via:

~~~yaml
company:
  client:
    connect-timeout: 5s
    read-timeout: 10s
~~~

A bean can use:

~~~java
@ConfigurationProperties(prefix = "company.client")
public record ClientProperties(
        Duration connectTimeout,
        Duration readTimeout
) {}
~~~

If there are only these two values, **no EPP is needed**. Spring Boot already knows how to load YAML and bind records.

Now imagine a shared platform library must provide a default **company.client.connect-timeout=2s** for every application. You do not want to force every project to copy the same value into application.yml. An EnvironmentPostProcessor packaged with the library can add a PropertySource containing defaults to Environment before configuration beans are created.

Similarly, a system migrating key names from **legacy.client.timeout-ms** to **company.client.read-timeout** may need a temporary alias layer during upgrades. EPP allows enforcing this rule very early, provided precedence policies and data validation are clearly defined.

Core point: **EnvironmentPostProcessor modifies data that subsequently created components will read; it is not an API for mutating already-running beans.**

## 2. Position in the Startup Process

A simplified startup flow:

~~~text
main()
   |
   v
SpringApplication.run(...)
   |
   v
Prepare Environment and initial sources
   |
   v
Boot and application EnvironmentPostProcessors
   |-- ConfigDataEnvironmentPostProcessor
   |-- Other processors, by Ordered/@Order
   |-- Platform processors, if registered
   |
   v
Environment continues to be used when creating context
   |
   v
Create ApplicationContext and refresh
   |
   v
Create beans, bind @ConfigurationProperties, resolve @Value
   |
   v
ApplicationRunner / CommandLineRunner
   |
   v
Application runs
~~~

This diagram explains timing semantics, not an exact listing of all internal events and listeners across every version. Processors are invoked in an order determined by the framework; application processors are not always called after every internal processor if the author selects a different order.

### 2.1. Things That Cannot Be Assumed to Exist Yet

When an EPP runs, the ApplicationContext has not yet refreshed, so the following components must not be assumed ready:

- @Service, @Repository, controller, and datasource beans.
- EntityManager, transaction manager, and Spring Data repositories.
- @ConfigurationProperties beans normally created by the IoC container.
- Objects created by auto-configuration only during refresh.
- Completed logging/runtime configuration.

EPP receives **Environment** and **SpringApplication**, not a bean container to query arbitrarily.

### 2.2. Intervening Too Late

If a bean has already bound readTimeout=5s and the application later adds a PropertySource with readTimeout=10s, that bean is not automatically rebound. With EPP, the goal is introducing values early to avoid that situation.

However, certain properties affect logging, Config Data locations, or profiles very early. Even an EPP running before context refresh can run **after the step that consumed** a special property. Thus ordering relative to other processors still matters.

## 3. Package Differences Between Spring Boot 3.x and 4.x

This is an important change when using examples found online.

| Version | Interface | spring.factories registration key |
| --- | --- | --- |
| Spring Boot 2.x/3.x | org.springframework.boot.env.EnvironmentPostProcessor | org.springframework.boot.env.EnvironmentPostProcessor |
| Spring Boot 4.x | org.springframework.boot.EnvironmentPostProcessor | org.springframework.boot.EnvironmentPostProcessor |

In Spring Boot 4, the interface moved to the **org.springframework.boot** package. Some 4.x releases keep the old interface deprecated for migration, but new code should use the new package.

Import for Boot 3.x:

~~~java
import org.springframework.boot.env.EnvironmentPostProcessor;
~~~

Import for Boot 4.x:

~~~java
import org.springframework.boot.EnvironmentPostProcessor;
~~~

The callback method essentially keeps the same signature:

~~~java
@Override
public void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application) {
    // ...
}
~~~

**When upgrading Boot major versions, update both the import and the discovery key in spring.factories.** A Java class that compiles does not prove Boot's factory loader will find and invoke the processor.

### 3.1. Do Not Confuse with AutoConfiguration.imports

Auto-configuration uses a separate discovery mechanism, typically based on the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Meanwhile, **EnvironmentPostProcessor** must be registered via **META-INF/spring.factories** per the API contract. A library can contain both types of extensions, as they solve different phases.

## 4. Complete Example: Library Defaults, Spring Boot 3.x

Suppose a library provides three defaults:

~~~properties
company.http.connect-timeout=2s
company.http.max-connections=20
company.audit.enabled=false
~~~

Create class:

~~~text
src/main/java/com/example/platform/CompanyDefaultsEnvironmentPostProcessor.java
~~~

Code:

~~~java
package com.example.platform;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class CompanyDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private static final String SOURCE_NAME =
            "company.platform.defaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        MutablePropertySources sources =
                environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = Map.of(
                "company.http.connect-timeout", "2s",
                "company.http.max-connections", "20",
                "company.audit.enabled", "false"
        );

        sources.addLast(new MapPropertySource(
                SOURCE_NAME,
                defaults
        ));
    }
}
~~~

### 4.1. Step-by-Step Explanation

**MutablePropertySources** is an ordered list of property sources. **MapPropertySource** turns a key/value Map into a named PropertySource.

**contains(SOURCE_NAME)** keeps the processor idempotent on the same Environment: if the source was already added, subsequent calls do not add duplicates.

**addLast** places the source at the end of the current list. This is the right choice when the library only provides fallbacks/defaults and wants application.yml, environment variables, or CLI to retain override rights.

**Map.of** creates an unmodifiable Map via API. The defaults in the example are non-sensitive values and can be kept as internal constants.

### 4.2. Why Not Use @Component?

EnvironmentPostProcessor is not discovered by regular component scanning. When it needs to run, ApplicationContext bean creation has not completed.

Adding @Component does not replace discovery registration. Leave the implementation as a plain Java class found by Spring Boot via spring.factories.

## 5. Registering in META-INF/spring.factories

Create:

~~~text
src/main/resources/META-INF/spring.factories
~~~

For **Spring Boot 3.x**, contents:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.platform.CompanyDefaultsEnvironmentPostProcessor
~~~

For **Spring Boot 4.x**, use:

~~~properties
org.springframework.boot.EnvironmentPostProcessor=com.example.platform.CompanyDefaultsEnvironmentPostProcessor
~~~

In Boot 4, the Java class source must also import the **org.springframework.boot.EnvironmentPostProcessor** interface.

### 5.1. Sample Directory Structure

~~~text
my-service/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/platform/
    │   │       └── CompanyDefaultsEnvironmentPostProcessor.java
    │   └── resources/
    │       ├── META-INF/
    │       │   └── spring.factories
    │       └── application.yml
    └── test/
        └── java/
            └── com/example/platform/
                └── CompanyDefaultsEnvironmentPostProcessorTest.java
~~~

For a library JAR, the resources and implementation must be packaged onto the runtime classpath of the consuming application.

### 5.2. Executable JAR Packaging

In a Spring Boot executable JAR, the application's classes/resources may reside in **BOOT-INF/classes/**. For libraries, they may live inside JARs under **BOOT-INF/lib/**. The actual requirement is that SpringFactoriesLoader finds the **META-INF/spring.factories** entry on the runtime classpath.

If the build uses custom shading/merging, ensure multiple spring.factories files from dependencies are merged properly rather than overwriting each other down to one file.

### 5.3. Wrong Filename Is a Discovery Error, Not a Binder Error

Common mistakes:

- Writing **spring.factory** instead of **spring.factories**.
- Placing the file outside the **META-INF** folder.
- Key using the wrong interface package.
- Value missing the package name.
- Implementation class missing from the runtime classpath.
- Constructor not matching parameter types supported by factory loading.

A discovery error can let the application start up normally while the custom defaults or source are never added.

## 6. Reading Results with Environment and @ConfigurationProperties

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "company.http")
public record HttpProperties(
        Duration connectTimeout,
        int maxConnections
) {}
~~~

Once registered via @ConfigurationPropertiesScan or @EnableConfigurationProperties, the bean can receive values from the EPP source.

Without overrides:

~~~text
connectTimeout = 2s
maxConnections = 20
~~~

With application.yml:

~~~yaml
company:
  http:
    connect-timeout: 5s
~~~

`connectTimeout` can receive 5s from Config Data, while `maxConnections` still uses the library default 20.

With command line:

~~~bash
java -jar demo.jar --company.http.max-connections=60
~~~

`60` can beat the default `20`.

### 6.1. Canonical Naming

Use canonical keys:

~~~text
company.http.connect-timeout
company.http.max-connections
company.audit.enabled
~~~

Corresponding environment variables:

~~~text
COMPANY_HTTP_CONNECTTIMEOUT
COMPANY_HTTP_MAXCONNECTIONS
COMPANY_AUDIT_ENABLED
~~~

EnvironmentPostProcessor does not change @ConfigurationProperties relaxed binding rules. Writing a MapPropertySource does not invent special custom syntax for Java fields.

### 6.2. Do Not Use EPP to Manually Bind All Beans

EPP only needs to add a PropertySource. Standard Spring Boot components can then read/bind the values.

Do not write code inside EPP to manually instantiate every HTTP client, service, and repository from the newly added values. That is the responsibility of the context and appropriate auto-configuration/bean factories.

## 7. Precedence Order of MutablePropertySources

Common operations:

| Method | Meaning | Notes |
| --- | --- | --- |
| addFirst(source) | Places source at front of list | May shadow CLI/env and other sources |
| addLast(source) | Places source at end of list | Appropriate for low-priority defaults |
| addBefore(name, source) | Inserts before a named source | Referenced source must exist |
| addAfter(name, source) | Inserts after a named source | Referenced source must exist |
| replace(name, source) | Replaces source by name | Only when ownership/intent is certain |
| remove(name) | Removes source | May drop large numbers of keys |
| contains(name) | Checks whether source exists | Useful for idempotency |
| get(name) | Retrieves source by name | Useful for bounded diagnostics |

### 7.1. addFirst Is Not a Way to "Increase Certainty"

Putting defaults at the front can cause values passed by operators via CLI or environment variables to be shadowed. For example, the library defaults maxConnections=20, the operator passes 60, yet EPP addFirst places 20 at higher priority.

If these are only defaults, that behavior is wrong. Adding the source at the end protects override capability.

### 7.2. addBefore and addAfter

Example:

~~~java
var sources = environment.getPropertySources();

if (sources.contains("systemEnvironment")) {
    sources.addAfter(
            "systemEnvironment",
            new MapPropertySource("platformOverrides", values)
    );
} else {
    sources.addLast(
            new MapPropertySource("platformOverrides", values)
    );
}
~~~

This only illustrates the mechanism. On a customized Environment, source names can differ, so check existence first.

Do not pick positions relying solely on internal source names without tests verifying actual precedence results.

### 7.3. replace Can Cause Data Loss

Replacing the entire **systemEnvironment** source with a Map holding only a few keys can cause the application to lose large sets of environment variables. Avoid replacing/removing sources the processor does not own.

For a new source, create a dedicated namespaced name, such as **company.platform.defaults** or **company.platform.legacy-aliases**.

## 8. EPP Invocation Order Differs from PropertySource Order

There are two kinds of ordering:

**Processor order:** which processor Spring Boot invokes earlier/later, governed by Ordered or @Order.

**PropertySource order:** when looking up a key, which source Environment prioritizes.

For example, an EPP can run after Config Data yet still call **addFirst**, putting its created source at the front to beat Config Data.

Conversely, an EPP running early yet calling **addLast** can produce a low-priority source; processors running later can also alter list order.

Therefore, **"the processor running last has its values win"** is not true in every case. Consider both callback order and PropertySource position together.

## 9. Ordered and ConfigDataEnvironmentPostProcessor

Spring Boot uses **ConfigDataEnvironmentPostProcessor** to load and apply Config Data. If your EPP needs to read keys from application.yml, it usually must run **after Config Data has been loaded**.

A way to express relative order:

~~~java
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.core.Ordered;

public final class CompanyDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 1;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        // ...
    }
}
~~~

As shown, **Ordered** supplies an order value; smaller values are invoked earlier under the standard Ordered contract.

### 9.1. Why Not Pick an Arbitrary Integer?

If you write:

~~~java
@Override
public int getOrder() {
    return 100;
}
~~~

you only know a number, not whether it sits before or after Config Data in the version in use. When the real requirement is **after Config Data**, express the relationship relative to the appropriate constant.

### 9.2. Does ORDER + 1 Mean Running After Everything?

No. It only expresses relative order against ConfigDataEnvironmentPostProcessor. Other processors may have smaller, larger, or equal orders. If multiple extensions touch the same key, write tests to avoid relying on incidental ordering.

### 9.3. Reading YAML Too Early

A processor placed before Config Data might not yet see:

~~~yaml
company:
  deployment:
    mode: production
~~~

If the method tries to read **company.deployment.mode** from Environment at that moment, it may receive null or a value from another source.

The fix is running after Config Data if the goal is reading properties declared in application.yml.

## 10. Do Not Change spring.config.* Too Late

Certain properties directly govern configuration file loading:

~~~text
spring.config.name
spring.config.location
spring.config.additional-location
spring.config.import
spring.profiles.active
~~~

If a processor runs after Config Data has already been processed, adding a **spring.config.location** value to Environment **does not guarantee** Boot will go back and load files at the new location.

Similarly, adding spring.profiles.active late is not equivalent to enabling the profile from the start.

To determine config locations/profiles, usually use a source Boot reads early enough:

~~~bash
java -jar demo.jar   --spring.config.additional-location=optional:file:./extra/
~~~

Or env:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
~~~

Or JVM system property:

~~~bash
java -Dspring.config.name=company -jar demo.jar
~~~

### 10.1. If You Genuinely Must Run Before Config Data

This is an advanced case requiring knowledge of internal ordering. The processor may only see system properties, env vars, and initial bootstrap sources. It must not depend on an as-yet-unloaded application.yml.

If the task is simply adding defaults for beans, **there is no need to run earlier than Config Data**. Choosing an order after Config Data is simpler and easier to test.

## 11. Comparing EPP with @PropertySource

Spring Framework example:

~~~java
@Configuration
@PropertySource("classpath:extra.properties")
class ExtraConfiguration {}
~~~

The @PropertySource mechanism on @Configuration classes is processed during context refresh. This can be too late for properties requiring early configuration, such as **logging.*** or **spring.main.*** already read before refresh.

Meanwhile, EPP receives Environment during preparation and can add sources before most beans are created.

### 11.1. Decision Table

| Need | Approach to consider |
| --- | --- |
| Standard configuration from application.yml | Config Data |
| Loading an additional standard YAML/properties file | spring.config.import |
| Adding a PropertySource very early with custom order | EnvironmentPostProcessor |
| Adding a file serving only ordinary beans | @PropertySource when suitable |
| Customizing context before refresh | ApplicationContextInitializer |
| Creating beans by feature flag | @ConditionalOnProperty |
| Binding a config group to an object | @ConfigurationProperties |
| Reading a single value | @Value / Environment |
| Running work after startup | ApplicationRunner |

**Choose the simplest hook that meets the requirement**, not the earliest hook just because it sounds flexible.

## 12. Comparing with spring.config.import

If you want to load an external file at startup:

~~~yaml
spring:
  config:
    import: "optional:file:./config/platform-extra.yml"
~~~

Usually no EPP is needed. Config Data already handles file loading, profile-specific variants, import ordering, optional locations, and appropriate error reporting.

When reading files manually in an EPP, you must manage:

- Path rules and resource lookup.
- Properties/YAML formats.
- Whether missing files are permitted.
- I/O errors and permissions.
- Source precedence on overlapping keys.
- Profile activation and multi-document YAML if present.
- Origin metadata if needed for diagnostics.
- Processing timing and startup impact.

If you only need to import another file, **Config Data** typically requires less code and is easier to operate.

### 12.1. EPP Is Not a Config Data Replacement

EPP can add sources from a file read manually by code, but it does not re-run every rule of the Config Data subsystem.

Calling a YAML loader directly does not mean Boot automatically handles profile activation, location groups, and imports for that file the way it does via spring.config.import.

## 13. Example: Reading an Additional .properties File

Suppose a library contains:

~~~text
src/main/resources/company-defaults.properties
~~~

With contents:

~~~properties
company.worker.pool-size=12
company.worker.idle-timeout=30s
company.feature.enabled=false
~~~

A processor can read the file and add a MapPropertySource:

~~~java
package com.example.platform;

import java.io.IOException;
import java.io.InputStream;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.io.ClassPathResource;

public final class CompanyFileEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private static final String SOURCE = "companyFileDefaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        var sources = environment.getPropertySources();

        if (sources.contains(SOURCE)) {
            return;
        }

        var resource = new ClassPathResource(
                "company-defaults.properties"
        );

        if (!resource.exists()) {
            // Example: file is allowed to be absent.
            return;
        }

        Properties properties = new Properties();

        try (InputStream input = resource.getInputStream()) {
            properties.load(input);
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Cannot load company-defaults.properties",
                    e
            );
        }

        Map<String, Object> values = new LinkedHashMap<>();
        for (String key : properties.stringPropertyNames()) {
            values.put(key, properties.getProperty(key));
        }

        sources.addLast(new MapPropertySource(SOURCE, values));
    }
}
~~~

This code uses the **Spring Boot 3.x** EPP import; for Boot 4, update the interface package and spring.factories.

### 13.1. Optional File Policy

In the example, if the file does not exist, the method returns. That is a **business decision**, not behavior every required resource should share.

If the application requires the file to exist:

~~~java
if (!resource.exists()) {
    throw new IllegalStateException(
            "Missing required company-defaults.properties"
    );
}
~~~

If the file exists yet cannot be read, throwing with the cause helps pinpoint the failure. Do not catch all exceptions and silently ignore them, as that can mask permission errors or corrupted files.

### 13.2. Using the Right Loader

Java Properties.load(InputStream) follows traditional Java properties encoding/escaping rules. For complex Unicode data or sources needing metadata support, use Spring Boot's loaders or Config Data.

**Do not write a simplistic custom parser** and assume it always matches Boot's parser. For multi-level YAML, lists, and multi-document files, custom parsers easily cause property path discrepancies.

## 14. Example: Loading YAML with YamlPropertySourceLoader

Spring Boot provides **YamlPropertySourceLoader**. An example accepting only **a single YAML document**:

~~~java
import java.io.IOException;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public final class ExtraYamlEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private final YamlPropertySourceLoader loader =
            new YamlPropertySourceLoader();

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment env,
            SpringApplication app) {

        Resource resource =
                new ClassPathResource("company-extra.yml");

        if (!resource.exists()) {
            return;
        }

        List<PropertySource<?>> loaded;

        try {
            loaded = loader.load("companyExtra", resource);
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Cannot load company-extra.yml", e
            );
        }

        if (loaded.size() != 1) {
            throw new IllegalStateException(
                    "This example requires exactly one YAML document"
            );
        }

        String sourceName = loaded.get(0).getName();
        if (!env.getPropertySources().contains(sourceName)) {
            env.getPropertySources().addLast(loaded.get(0));
        }
    }
}
~~~

This is still a Boot 3.x example. **Do not use this code expecting it to handle all multi-document YAML scenarios.** If multiple documents are desired, define precedence order and add all PropertySources returned by the loader.

### 14.1. When to Use Config Data Instead of YAML Loader?

If the file has:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

or uses spring.config.import, calling YamlPropertySourceLoader manually does not automatically bring along Spring Boot's full Config Data handling.

**When Config Data semantics are the goal**, load the file via Config Data rather than mimicking it with YamlPropertySourceLoader alone.

## 15. Migration Alias: Translating Legacy Properties to New Ones

A practical scenario is supporting older deployments when a library renames a key.

Old name:

~~~text
legacy.timeout-ms
~~~

New name:

~~~text
company.http.timeout
~~~

Illustrative policy: the new name **always wins** if declared in any source; the old name is only used when the new name is completely absent.

~~~java
@Override
public void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application) {

    var sources = environment.getPropertySources();
    String aliasSource = "company.legacy.timeout-alias";

    if (sources.contains(aliasSource)) {
        return;
    }

    String targetKey = "company.http.timeout";
    String legacyKey = "legacy.timeout-ms";

    if (environment.containsProperty(targetKey)) {
        return;
    }

    String millis = environment.getProperty(legacyKey);
    if (millis == null) {
        return;
    }

    // Example: legacy is always in milliseconds.
    long parsed = Long.parseLong(millis);

    if (parsed <= 0) {
        throw new IllegalArgumentException(
                "legacy.timeout-ms must be positive"
        );
    }

    sources.addLast(new MapPropertySource(
            aliasSource,
            Map.of(targetKey, parsed + "ms")
    ));
}
~~~

### 15.1. Precedence Policy Must Be Published

The example above prioritizes the new name even if the old name sits in a higher-precedence PropertySource. This is an intentional policy, **not a full emulation of PropertySource ordering**.

If the requirement is preserving per-source precedence across names, the implementation must inspect each PropertySource individually and requires more complex logic. In that case, thoroughly test combinations such as old CLI + new file, or old env + new CLI.

### 15.2. Aliases Do Not Replace a Migration Plan

Operational documentation should publish:

- The new canonical name.
- Supported legacy names.
- Unit and data type conversion rules.
- Behavior if both legacy and new names are declared.
- Error reporting when a legacy value is invalid.
- Target version for removing the alias.

Without bounds, EPP can turn into a hard-to-maintain name-translation layer.

## 16. What Can Be Done with ConfigurableEnvironment?

At the EPP stage, environment permits:

~~~java
String appName =
        environment.getProperty("spring.application.name");

String mode =
        environment.getProperty("company.deployment.mode", "local");

boolean exists =
        environment.containsProperty("company.feature.enabled");
~~~

And PropertySource management:

~~~java
var sources = environment.getPropertySources();

if (!sources.contains("company.platform.defaults")) {
    sources.addLast(customSource);
}
~~~

However, **Environment.getProperty** only reflects lookups across sources registered at that moment. If Config Data has not yet loaded, it cannot read a property sitting only in an unprocessed application.yml.

### 16.1. Do Not Turn EPP into a Per-Request Config Service

If a Controller needs to pick per-tenant config on every request, EnvironmentPostProcessor is not that hook. It is designed for startup, not as a multi-tenant runtime service.

You can use the Binder API, an immutable registry, or a dedicated config service depending on data, access control, and lifecycle.

## 17. Logging and DeferredLogFactory

Spring Boot logging is prepared very early; many logging values may already be read before a custom EPP runs.

Therefore:

- Do not assume adding **logging.level.root** to a source in an EPP running after Config Data will adjust the entire initial logging phase.
- For logging properties that must be read early, prefer env vars, JVM system properties, or CLI unless exact bootstrap order has been verified.
- Avoid using a regular logger inside a processor without accounting for logging system state.

Some Boot versions support supplying **DeferredLogFactory** in an EPP constructor to defer log output until an appropriate moment.

Conceptual example:

~~~java
import org.apache.commons.logging.Log;
import org.springframework.boot.logging.DeferredLogFactory;

public final class DiagnosticEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private final Log log;

    public DiagnosticEnvironmentPostProcessor(
            DeferredLogFactory factory) {
        this.log = factory.getLog(getClass());
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment env,
            SpringApplication app) {
        log.info("Installing company environment defaults");
    }
}
~~~

Advanced Boot packages should be checked against the running version. **DeferredLogFactory is not needed** for a processor that only adds a Map and emits no logs.

### 17.1. Do Not Log Secrets

Deferred logging only adjusts when logs are emitted. It does not automatically mask tokens, passwords, or keys. Do not print the entire Environment, MapPropertySource, or exception messages containing sensitive data.

## 18. Bootstrap Context Is Not ApplicationContext

In Boot versions with appropriate APIs, the factory creating EPPs can supply **ConfigurableBootstrapContext** via constructor alongside **DeferredLogFactory**.

Idea:

~~~java
public SomeEnvironmentPostProcessor(
        DeferredLogFactory logFactory,
        ConfigurableBootstrapContext bootstrapContext) {
    // Store or reuse a bootstrap resource when needed.
}
~~~

The bootstrap context is useful for specially initialized resources shared early. It is **not** a full Spring ApplicationContext, nor a place to inject ordinary repositories or services.

### 18.1. Spring Boot 4 Upgrade Note

Not only does EPP change packages. Some APIs related to BootstrapRegistry/BootstrapContext also change packages. When migrating, consult the migration guide and corresponding APIs rather than copying Boot 3 imports into Boot 4.

### 18.2. When Is It Unnecessary?

If you are only creating:

~~~java
new MapPropertySource("companyDefaults", Map.of(...))
~~~

you do not need bootstrap context. Keeping extensions small leaves fewer failure points.

## 19. Do Not @Autowired Application Beans in EPP

Architecturally incorrect example:

~~~java
@Component
public class BadProcessor implements EnvironmentPostProcessor {

    @Autowired
    private CustomerRepository repository;

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment env,
            SpringApplication app) {
        // Cannot rely on repository as a ready bean.
    }
}
~~~

Because EPP runs before context refresh and is discovered via factory loading, repositories are not ready under the normal lifecycle.

Do not use a static ApplicationContext holder to "steal" beans from an earlier context: this can fail in tests or when multiple ApplicationContexts exist.

If data from a database or remote service is genuinely needed during bootstrap, design a dedicated integration with authentication, timeouts, failure policies, and proper lifecycle.

## 20. Idempotency and Source Naming

An EPP may be invoked again on the same Environment in tests or special bootstrap flows. Thus source names should be stable and processors should not unconditionally add duplicate sources.

Example:

~~~java
String sourceName = "company.platform.defaults";

if (!environment.getPropertySources().contains(sourceName)) {
    environment.getPropertySources().addLast(
            new MapPropertySource(sourceName, defaults)
    );
}
~~~

### 20.1. What If the Source Already Exists?

There are several options:

- Skip because the processor is idempotent.
- Compare against expected data and raise an error on unexpected name collision.
- Replace if the source is owned by this processor and that is the designed policy.

**Do not replace blindly.** A source with the same name might belong to another library. Namespaced names reduce collisions.

### 20.2. Do Not Mutate Global State

Do not store Environment in a static field. Also do not use System.setProperty as a way to pass arbitrary values across tests or multiple apps in the same JVM. Keep changes scoped to the Environment passed in.

## 21. Optional Files and Required Files

For supplementary config sources, establish a clear contract:

| Scenario | Optional Source | Required Source |
| --- | --- | --- |
| File does not exist | Can be skipped | Fail-fast |
| File exists but cannot be read | Usually report error | Report error |
| File has invalid format | Report error unless policy specifies otherwise | Report error |
| Value has wrong type | Should not silently ignore | Report error |
| Remote service unresponsive | Timeout/fallback per design | Timeout then fail-fast |
| Sensitive values | Do not log raw value | Do not log raw value |

Do not write catch(Exception) and return for all errors. That can turn a severe deployment failure into a hard-to-detect fallback value.

### 21.1. Config Data optional Can Be Used

If the requirement is merely adding a file that might be missing:

~~~yaml
spring:
  config:
    import: "optional:file:./extra/application.yml"
~~~

is usually easier to understand than an EPP implementing custom file-checking logic.

## 22. I/O Cost During Bootstrap

EnvironmentPostProcessor sits on the startup path, so heavy operations can delay when the entire application becomes ready.

Things to avoid:

- Network calls without timeouts.
- Infinite retries when a secret/config service does not respond.
- Unbounded filesystem or classpath scanning.
- Database queries via connections depending on unready auto-configuration.
- Loading configuration for thousands of tenants when the app only needs one group.
- Calling business logic with side effects.

If I/O is unavoidable:

1. Set timeouts and bounded retries.
2. Define the policy when the source is unavailable.
3. Do not read secrets beyond the required scope.
4. Make the operation idempotent when possible.
5. Keep error messages informative enough to identify the cause.
6. Write tests for missing files, permission denied, and timeouts.
7. Avoid assuming beans exist to serve requests.

**EPP should do little work, at the right time.**

## 23. Security and Secret Management

Spring Boot allows customizing Environment, but that does not mean you should write a custom secret decryption system inside an EPP.

When values are tokens, passwords, or private keys:

- Do not hardcode decryption keys in the JAR.
- Use dedicated secret stores/integrations where appropriate.
- Control process identity and permissions.
- Do not log the entire PropertySource or config records containing secrets.
- Do not include secrets in exception messages.
- Define separate rotation/reloading if runtime changes are required.
- Do not expose config via public endpoints.
- Load only the exact secrets the module needs.

If using EPP as part of a secret integration, clearly design responsibility boundaries and security policies. A MapPropertySource does not automatically provide secure caching, token rotation, or audit logging.

## 24. Unit Testing PropertySource-Addition Logic

A simple EPP can be tested directly without creating an ApplicationContext.

Example with JUnit Jupiter and AssertJ:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class CompanyDefaultsEnvironmentPostProcessorTest {

    private final CompanyDefaultsEnvironmentPostProcessor processor =
            new CompanyDefaultsEnvironmentPostProcessor();

    @Test
    void addsExpectedDefaults() {
        StandardEnvironment environment = new StandardEnvironment();

        processor.postProcessEnvironment(
                environment,
                new SpringApplication(Object.class)
        );

        assertThat(environment.getProperty(
                "company.http.connect-timeout")).isEqualTo("2s");
        assertThat(environment.getProperty(
                "company.http.max-connections")).isEqualTo("20");
    }

    @Test
    void doesNotOverrideHigherPriorityValue() {
        StandardEnvironment environment = new StandardEnvironment();

        environment.getPropertySources().addFirst(
            new MapPropertySource("testOverride", Map.of(
                "company.http.max-connections", "70"
            ))
        );

        processor.postProcessEnvironment(
                environment,
                new SpringApplication(Object.class)
        );

        assertThat(environment.getProperty(
                "company.http.max-connections")).isEqualTo("70");
    }

    @Test
    void canRunTwiceOnSameEnvironment() {
        StandardEnvironment environment = new StandardEnvironment();
        SpringApplication application = new SpringApplication(Object.class);

        processor.postProcessEnvironment(environment, application);
        processor.postProcessEnvironment(environment, application);

        assertThat(environment.getPropertySources()
                .contains("company.platform.defaults")).isTrue();
    }
}
~~~

The tests verify:

- The processor adds the source and right values.
- addLast does not shadow a higher-priority source.
- The code does not fail when invoked twice on the same Environment.

**This test does not verify spring.factories discovery**, because it invokes the method directly.

## 25. Integration Testing Discovery via SpringApplication

To verify Spring Boot actually finds the EPP in META-INF/spring.factories, write a test starting SpringApplication.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

class EnvironmentProcessorDiscoveryTest {

    @Test
    void registersCustomPropertySourceAtStartup() {
        SpringApplication application =
                new SpringApplication(TestApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run()) {

            Environment env = context.getEnvironment();

            assertThat(env.getProperty(
                "company.http.connect-timeout")).isEqualTo("2s");
        }
    }

    @org.springframework.boot.SpringBootConfiguration
    @org.springframework.boot.autoconfigure.EnableAutoConfiguration
    static class TestApplication {}
}
~~~

The test is meaningful when:

- spring.factories is on the test runtime classpath.
- No higher-priority source accidentally overrides the asserted value.
- TestApplication is minimal enough to start the context.
- The processor class is packaged and loaded properly.

A direct unit test can pass while an integration test fails due to a wrong spring.factories key; therefore distinguish the two test types.

### 25.1. Testing Inside a Separately Packaged Library

If the processor belongs to a library JAR, create a test application consuming the library as a real dependency. This helps catch resource files omitted or corrupted during packaging.

## 26. Testing Order Relative to Config Data

If a processor needs to read:

~~~java
String mode =
        environment.getProperty("company.deployment.mode");
~~~

where mode lives in application.yml, a unit test manually creating a MapPropertySource with that key does not prove **order** is correct.

You need a SpringApplication integration test loading actual YAML and confirming the processor sees the value.

Example:

~~~yaml
company:
  deployment:
    mode: production
~~~

With a processor running after ConfigDataEnvironmentPostProcessor, mode can be production. If running before, it may not yet be present.

Test sources matching how you deploy: base files, profile-specific files, environment variables, system properties, or CLI.

## 27. Precedence with Files, Env, and CLI

Suppose:

~~~yaml
company:
  http:
    max-connections: 30
~~~

Environment:

~~~bash
COMPANY_HTTP_MAXCONNECTIONS=40 java -jar demo.jar   --company.http.max-connections=50
~~~

EPP adds default 20 via addLast.

The final value is typically **50** because command line takes higher priority than the other sources.

| Source | Value |
| --- | ---: |
| EPP default addLast | 20 |
| application.yml | 30 |
| OS environment | 40 |
| Command-line | 50 |

If EPP calls addFirst on the default source, the outcome can differ and strip operators of override control. Therefore write integration tests verifying precedence instead of only testing that defaults exist.

### 27.1. Do Not Confuse Naming with Precedence

If an environment variable is misnamed:

~~~text
COMPANY_HTTP_MAX_CONNECTIONS
~~~

instead of the canonical mapping:

~~~text
COMPANY_HTTP_MAXCONNECTIONS
~~~

the application may fail to pick up the desired override. When debugging, distinguish **a key name that failed to bind** from **a higher-priority source winning**.

## 28. Why Not Use ApplicationRunner to Add Sources?

ApplicationRunner runs after context refresh and after many beans have already been created. If a @ConfigurationProperties bean already bound timeout=5s, and a runner later adds a source with timeout=10s, that bean does not automatically change to 10s.

EnvironmentPostProcessor is designed specifically for modifying Environment earlier.

However, if the goal is solely running a task once the application is ready, ApplicationRunner is the right hook. Do not move a business task into EPP just to make it run early.

## 29. Why Not Use EPP for Dynamic Refresh?

Some developers think:

~~~java
Map<String, Object> values = new HashMap<>();
sources.addFirst(new MapPropertySource("dynamic", values));
~~~

and mutating `values` after startup will cause every bean to receive new values.

This is not guaranteed. @Value and @ConfigurationProperties are typically processed at bean creation; mutating an existing MapPropertySource does not rebind every object automatically.

If hot-reloading configuration is needed:

- Identify which sources are actually reloadable.
- Have synchronization/atomic snapshot mechanisms.
- Validate before putting new values into service.
- Have rollback rules when new configuration is invalid.
- Have a way to reconfigure dependent clients/beans.
- Enforce access control and secret protection.

EPP only provides a startup hook. It does not build a runtime refresh system.

## 30. Do Not Use EPP as a Multi-Tenant Service

Suppose a system has thousands of tenants and each tenant has configuration changing per request. Do not try to load everything into Environment at startup and use EPP as a tenant management mechanism.

Problems will arise:

- Memory usage and startup time.
- Cross-tenant access control.
- Config changes without already-bound objects refreshing.
- Secrets lingering in Environment longer than necessary.
- Difficulty isolating errors per tenant.

If tenant configuration is truly runtime data, build a dedicated service and storage/registry with its own lifecycle. If the tenant set is small and fixed at startup, a Map via @ConfigurationProperties may suffice.

## 31. Common Error: Processor Does Not Run

Common causes:

| Symptom | Cause to check |
| --- | --- |
| Custom source missing | Wrong spring.factories path or key |
| Source missing in executable JAR | Resources excluded during build |
| ClassNotFound error | Wrong class name or dependency |
| Instantiation error | Constructor not supported by factory loading |
| Running Boot 4 with Boot 3 import/key | Package migration incomplete |
| YAML properties not visible | Processor ran before Config Data |
| Source present but value loses | PropertySource precedence |
| Processor skips silently | Optional file missing or early return condition |
| Bean fails to bind | Property present but conversion/validation fails |

Before changing addLast to addFirst to "fix the bug", confirm whether the processor actually ran and whether the source is present.

### 31.1. Printing Source Names Safely

In test environments you can list:

~~~java
for (PropertySource<?> source
        : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

This snippet requires `environment` to have type ConfigurableEnvironment and the appropriate PropertySource import.

Do not print all configuration data as it may contain passwords, tokens, and sensitive information.

## 32. Common Error: Wrong Configuration Value Type

If EPP adds:

~~~properties
company.http.max-connections=not-a-number
~~~

and the target bean has:

~~~java
@ConfigurationProperties(prefix = "company.http")
public record HttpProperties(int maxConnections) {}
~~~

Binder may report a conversion error. That is not proof EPP failed; on the contrary, it may have placed the key into Environment correctly while the value is invalid.

If the value is 0 and **@Min(1)** is present, that is a validation error, not conversion.

To diagnose, trace:

~~~text
Source added?
       |
       v
Property name right?
       |
       v
Source precedence?
       |
       v
Raw value?
       |
       v
Conversion to Java type?
       |
       v
Validation?
~~~

Do not use a high-priority default to mask an invalid production value. Fix the data or deployment policy.

## 33. Common Error: Duplicate Source Names

Two libraries both add a source named **customDefaults**. A name collision can occur and one library will not behave as intended.

Choose clearly namespaced names:

~~~text
company.gateway.defaults
company.billing.legacy-aliases
company.shared.extra-properties
~~~

When a source already exists:

~~~java
if (sources.contains(sourceName)) {
    return;
}
~~~

is an idempotent choice, though if the name is unexpected and has different contents, raising an error may be appropriate. Do not blindly replace a source whose ownership is unclear.

## 34. Common Error: Changing Logging Too Late

A processor running after Config Data is invoked before context refresh, but that does not mean it runs before every step where the logging system reads configuration.

If you need:

~~~text
logging.level.root=DEBUG
logging.config=classpath:logback-custom.xml
~~~

supply them via a Boot-supported early source, or verify the exact lifecycle/order of the extension thoroughly. Do not simply add the property with addLast and conclude the log level is guaranteed to change from JVM startup.

## 35. Common Error: Swallowing I/O Errors

Poor code:

~~~java
try {
    loadFileAndAddProperties();
} catch (Exception ignored) {
    // Ignore all errors.
}
~~~

If the file is a required source, swallowing the error lets the application start with missing configuration.

Better approach:

~~~java
try {
    loadFileAndAddProperties();
} catch (IOException e) {
    throw new IllegalStateException(
            "Failed to initialize company configuration source",
            e
    );
}
~~~

If the source is allowed to be absent, skip only the absence case per explicit rules. An existing file that cannot be read should still raise an error.

## 36. Common Error: Assuming @Autowired Works

An EPP is not a regular application context bean. Therefore you cannot expect:

~~~java
@Autowired
private SecretService secretService;
~~~

to be injected the way an initialized @Service is. Use Boot-supported bootstrap APIs and minimize dependencies on the service graph.

If you genuinely need a Spring bean to process something later, EPP may not be the right hook.

## 37. Complete Platform Defaults Scenario

A library supplies:

~~~text
company.http.connect-timeout
company.http.read-timeout
company.http.max-connections
company.audit.enabled
~~~

EPP adds low-priority defaults:

~~~java
Map<String, Object> defaults = Map.of(
        "company.http.connect-timeout", "2s",
        "company.http.read-timeout", "5s",
        "company.http.max-connections", "20",
        "company.audit.enabled", "false"
);

sources.addLast(
        new MapPropertySource(
                "company.platform.defaults",
                defaults
        )
);
~~~

Application declares:

~~~yaml
company:
  http:
    read-timeout: 12s
    max-connections: 40
  audit:
    enabled: true
~~~

Under normal ordering, the HttpProperties bean receives **connectTimeout=2s** from defaults, and **readTimeout=12s** and **maxConnections=40** from YAML.

When running:

~~~bash
COMPANY_HTTP_MAXCONNECTIONS=80 java -jar demo.jar
~~~

`maxConnections` can become 80 from the environment variable.

This design meets the goal: **the library supplies defaults, while applications and operators retain override control**.

## 38. When Should You Not Write an EnvironmentPostProcessor?

Do not use it if:

1. You only need to bind a property group: use @ConfigurationProperties.
2. You only need a single scalar: use Environment or @Value.
3. You only want to import another YAML/properties file: use spring.config.import.
4. You need conditional bean creation: use @ConditionalOnProperty or auto-configuration.
5. You need to run a task after startup: use ApplicationRunner.
6. You need to customize bean definitions/context: check ApplicationContextInitializer or suitable context hooks.
7. You need to query secrets/config from an external system: prefer that system's standard integration.
8. You need runtime configuration refresh: use a refresh mechanism with validation and synchronization.
9. You need to select prefixes at runtime: inspect Binder API or a registry rather than a startup EPP.
10. You only want to unintentionally override CLI/env: review your precedence policy.

**EPP adds value when a requirement demands a PropertySource or Environment transformation during bootstrap**, not as a default way to handle all configuration.

## 39. Checklist for Publishing a Library Containing an EPP

- [ ] Target Spring Boot version chosen.
- [ ] Interface and spring.factories key match Boot 3 or 4.
- [ ] META-INF/spring.factories file is on the runtime classpath.
- [ ] Processor class can be instantiated by SpringFactoriesLoader.
- [ ] No @Autowired business beans.
- [ ] Order explicitly defined if depending on Config Data.
- [ ] PropertySource name is namespaced and non-colliding.
- [ ] addFirst/addLast aligns with override policy.
- [ ] Does not remove/replace sources not owned by the processor.
- [ ] Optional and required files have distinct behaviors.
- [ ] I/O is bounded and has timeouts if needed.
- [ ] Does not log secrets or the full Environment.
- [ ] Defaults do not mask invalid production configuration values.
- [ ] Unit tests check data and idempotency.
- [ ] Integration tests verify discovery via SpringApplication.
- [ ] Priority tests cover YAML, env, JVM system properties, or CLI.
- [ ] Boot 3 → 4 upgrade tests exist if the library supports both.
- [ ] Operator documentation covers keys, defaults, and overrides.

## 40. Official Documentation

Cross-check guides against your application's version:

- Spring Boot — Customize the Environment or ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/how-to/application.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot 3.5 — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 4.x — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/EnvironmentPostProcessor.html
- Spring Boot — ConfigDataEnvironmentPostProcessor: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html

Older guides may still use the org.springframework.boot.env.EnvironmentPostProcessor package. When learning or upgrading, verify the exact Spring Boot line to avoid conceptually valid snippets with incorrect imports or discovery keys.

## 41. Summary

**EnvironmentPostProcessor** is Spring Boot's hook to **modify Environment before ApplicationContext refresh**. It is particularly well suited for adding default sources, translating legacy property groups, or loading a controlled custom configuration source right during bootstrap.

Key takeaways:

- Boot 2/3 uses **org.springframework.boot.env.EnvironmentPostProcessor**; Boot 4 uses **org.springframework.boot.EnvironmentPostProcessor**.
- Register implementations using **META-INF/spring.factories** with the version's exact key.
- **addLast** generally fits defaults; **addFirst** creates a high-priority source and requires a clear justification.
- **Processor order** and **PropertySource precedence** are two distinct concepts.
- When needing properties from application.yml, consider relative order against ConfigDataEnvironmentPostProcessor.
- Do not expect EPP to receive @Autowired business beans or a ready ApplicationContext.
- Do not add spring.config.location/profiles.active too late expecting Config Data to reload automatically.
- Do not use EPP as a homemade dynamic refresh system or secret manager.
- Test **logic**, **discovery**, **precedence**, and **failure policy** separately.
- If **spring.config.import** or @ConfigurationProperties solves the need, choose the simpler option.

The deciding question is: **"Does this property need to be placed into Environment before context refresh, and is standard Config Data loading insufficient?"**. When early intervention is genuinely needed, EnvironmentPostProcessor is an effective tool when applied with proper lifecycle, source ordering, and error-handling policies.
