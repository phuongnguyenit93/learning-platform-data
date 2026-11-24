# YAML Limitations, Multi-Document Files, and @PropertySource Timing

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Environment Extensions

## 1. Problem: All Are Configuration, Yet Not Every Loading Mechanism Is Equivalent

Spring Boot lets you bring configuration into an application through many sources: `application.properties`, `application.yml`, environment variables, Java system properties, command-line arguments, `SPRING_APPLICATION_JSON`, imported files, and custom sources. When first learning, it is easy to see the `@PropertySource` annotation and think pointing it to any file will make Spring Boot load that file just like `application.yml`.

This is a misconception that easily leads to bugs in real environments.

Example:

~~~java
@Configuration
@PropertySource("classpath:extra.yml")
public class ExtraConfiguration {}
~~~

An author might expect `extra.yml` to be processed like a Spring Boot YAML configuration file, including multi-document support, profile conditions, and precedence ordering. However, `@PropertySource` is a **Spring Framework** mechanism for adding a `PropertySource` to `Environment`, and it has different limitations from Spring Boot's **Config Data API**.

Three issues must be distinguished:

1. **Format:** `@PropertySource` by default lacks YAML parsing equivalent to `application.yml`.
2. **Multi-document files:** document separation syntax and profile-based document activation are not automatically handled by `@PropertySource` like Config Data.
3. **Timing:** `@PropertySource` is processed while the ApplicationContext is refreshing; some properties Spring Boot must read **before** that point cannot rely on it to take effect.

These three limitations do not make `@PropertySource` useless. It remains appropriate when you want to add a simple `.properties` file into Spring `Environment` for beans initialized at the appropriate phase. What matters is choosing the right tool for the requirement.

### Lesson Objectives

After this lesson, you will be able to:

- Explain the difference between Spring Framework's `@PropertySource` and Spring Boot's Config Data mechanism.
- Load a simple `.properties` file using `@PropertySource`.
- Understand why `@PropertySource("classpath:extra.yml")` is not equivalent to loading a YAML file with Boot.
- Write a `PropertySourceFactory` for YAML when there is a special reason, and understand that solution's limitations.
- Read multi-document YAML configuration, `---` separators, `spring.config.activate.on-profile`, and override ordering.
- Recognize the multi-document mechanism for `.properties` files and why `@PropertySource` is not the right way to load them.
- Distinguish properties that can affect beans during refresh from properties that must be determined very early, such as `logging.*`, `spring.main.*`, or config-data locations.
- Use `spring.config.import`, `spring.config.additional-location`, and environment variables/CLI to replace cases unsuitable for `@PropertySource`.
- Diagnose ignored configuration, unexpected active profiles, and binding differences between local and production.

## 2. Background: Environment Holds PropertySources in Precedence Order

Spring Framework provides `Environment`, where `PropertySources` is a collection of sources containing key/value pairs. A property may be declared in multiple sources, and **precedence order** decides the effective value.

High-level diagram:

~~~text
command-line arguments
SPRING_APPLICATION_JSON
Java system properties
OS environment variables
Config Data: application.yml, imports, profiles ...
@PropertySource from @Configuration
default properties
                 |
                 v
          Spring Environment
                 |
                 v
        Binder / @Value / lookup
                 |
                 v
             Spring beans
~~~

The order in the diagram illustrates common sources and does not list every Spring Boot PropertySource type. In Servlet, test, or custom configurations, additional sources exist. In Boot's default order, **config data typically takes priority over `@PropertySource`**, and command-line properties typically take higher priority than config data.

For example, if `@PropertySource` provides:

~~~properties
catalog.client.timeout=10s
~~~

but `application.yml` has:

~~~yaml
catalog:
  client:
    timeout: 3s
~~~

then under the default ordering, the value from Config Data can beat the `@PropertySource` source. Do not conclude that an annotation appearing "later" in code will always override application files.

### 2.1. PropertySource Differs from Configuration File

A `PropertySource` is a key/value source already placed into `Environment`.

A configuration file is **a medium storing data**. For a file to become a PropertySource, there must be a loader that understands its format and has policies for multiple documents, ordering, and startup lifecycle.

`application.yml` and `application.properties` are processed by Boot's Config Data mechanism. The `@PropertySource` annotation uses a different processing path. This difference explains why both use `Environment` yet do not provide the exact same features.

### 2.2. Do Not Confuse with @ConfigurationProperties

- `@PropertySource`: adds a property source to `Environment`.
- `@ConfigurationProperties`: binds properties already present in `Environment` into a typed Java object.
- `@Value`: injects a value/expression within the scope of a bean.
- `spring.config.import`: instructs Spring Boot to load additional Config Data at the appropriate phase.

You can combine `@PropertySource` with `@ConfigurationProperties` for a simple properties file, but they do not replace each other's roles.

## 3. Where @PropertySource Works Well: A Regular .properties File

File `src/main/resources/legacy-feature.properties`:

~~~properties
legacy.feature.enabled=true
legacy.feature.timeout=5s
legacy.feature.banner=Hello from properties
~~~

Registration class:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy-feature.properties")
public class LegacyFeatureConfiguration {}
~~~

Another bean can read:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class LegacyFeatureReader {

    private final boolean enabled;
    private final String banner;

    public LegacyFeatureReader(
            @Value("${legacy.feature.enabled:false}") boolean enabled,
            @Value("${legacy.feature.banner:Welcome}") String banner) {
        this.enabled = enabled;
        this.banner = banner;
    }

    public boolean enabled() {
        return enabled;
    }

    public String banner() {
        return banner;
    }
}
~~~

When the file is found, the annotation is processed, and no higher source overrides the keys, the bean can receive the values from `legacy-feature.properties`.

### 3.1. Placing @PropertySource on a @Configuration Class

The annotation is usually placed on a `@Configuration` class, where Spring processes configuration metadata during context creation.

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(value = "classpath:legacy-feature.properties")
class LegacyConfig {}
~~~

Do not place the annotation arbitrarily on a Java class that is not included in Spring configuration processing and expect it to always work.

### 3.2. Optional Files

When the file is not required:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "classpath:optional-feature.properties",
    ignoreResourceNotFound = true
)
class OptionalFeatureConfig {}
~~~

`ignoreResourceNotFound=true` lets missing-resource cases be ignored. However, **a missing file** is different from **an existing file with malformed content**. Do not use this option as a way to ignore all configuration errors.

If a file holds critical properties, allowing it to be missing can mask deployment errors. Weigh how mandatory the file is.

### 3.3. Using Placeholders in the Resource Path

You can reference a property that already exists when the location is processed:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:/config/${app.config.region}.properties")
class RegionPropertiesConfiguration {}
~~~

Idea: Spring resolves `app.config.region` from already-available sources to construct the path. This does **not** mean `@PropertySource` is allowed to decide profiles or config-data sources from a property loaded later. If the resource location placeholder is not yet available at processing time, supply the value early via an appropriate source.

## 4. First Limitation: @PropertySource Does Not Read YAML by Default Like Boot

Standard YAML configuration:

~~~yaml
demo:
  service:
    endpoint: "https://example.test"
    enabled: true
    timeout: 3s
~~~

If you write:

~~~java
@Configuration
@PropertySource("classpath:custom.yml")
class YamlConfig {}
~~~

this is **not** the default path recommended by Spring Boot for loading YAML. `@PropertySource` uses Spring Framework's standard factory/loader for properties format, and does not automatically trigger all interpretations of `YamlPropertySourceLoader` and Config Data.

Depending on implementation and content, YAML may be misread as plain text-line properties, fail to flatten into `demo.service.endpoint` as expected, or cause errors. Therefore, do not put it simply as "YAML always crashes the JVM"; the real issue is that **there is no proper YAML-parsing contract through the default factory**.

### 4.1. Why Does YAML Need a Separate Loader?

Properties file:

~~~properties
demo.service.endpoint=https://example.test
demo.service.enabled=true
demo.service.timeout=3s
~~~

YAML:

~~~yaml
demo:
  service:
    endpoint: "https://example.test"
    enabled: true
    timeout: 3s
~~~

YAML has nested objects, lists, YAML-syntax scalars, and multiple documents in the same file. To put it into `Environment`, a loader must understand the structure, flatten property paths, and apply document-specific rules.

A parser meant for Java `.properties` cannot be treated as a YAML parser just because the filename ends in `.yml` or `.yaml`.

### 4.2. Difference from application.yml

Spring Boot has a Config Data mechanism that automatically considers `application.yml`, `application.yaml`, and `application.properties` in supported locations. This mechanism understands YAML, profile-specific files, YAML document separators, and activation metadata according to Boot rules.

Therefore, **if the content needs to behave like standard Boot configuration**, the right choice is usually placing the file into the Config Data mechanism rather than putting `@PropertySource` on a YAML file.

### 4.3. YAML Is Not Just "Properties with Nicer Line Breaks"

YAML list example:

~~~yaml
demo:
  regions:
    - ap-southeast-1
    - ap-northeast-1
~~~

A loader must know how to map elements into data the binder can understand, such as indexed properties. For maps with special keys, there are also key-preservation rules. Using a loader that does not properly support YAML can lose structure or cause mismatches between the file and the Java model.

## 5. You Can Write a PropertySourceFactory for YAML, but Must Understand Its Limits

In cases where you genuinely need to integrate a separate YAML file via annotation, Spring Framework lets you specify a `factory` in `@PropertySource`.

The following example illustrates a **simple** YAML factory, not one meant to replicate all Spring Boot Config Data semantics.

~~~java
package com.example.config;

import java.io.IOException;
import java.util.Properties;

import org.springframework.beans.factory.config.YamlPropertiesFactoryBean;
import org.springframework.core.env.PropertiesPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.core.io.support.PropertySourceFactory;

public class SimpleYamlPropertySourceFactory
        implements PropertySourceFactory {

    @Override
    public PropertySource<?> createPropertySource(
            String name, EncodedResource resource) throws IOException {

        YamlPropertiesFactoryBean yaml = new YamlPropertiesFactoryBean();
        yaml.setResources(resource.getResource());
        yaml.afterPropertiesSet();

        Properties properties = yaml.getObject();
        if (properties == null) {
            throw new IllegalStateException("Unable to read YAML resource");
        }

        String sourceName = name != null
                ? name : resource.getResource().getDescription();

        return new PropertiesPropertySource(sourceName, properties);
    }
}
~~~

Configuration using the factory:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource(
    value = "classpath:custom-settings.yml",
    factory = SimpleYamlPropertySourceFactory.class
)
public class CustomYamlConfiguration {}
~~~

File `custom-settings.yml`:

~~~yaml
demo:
  service:
    endpoint: "https://api.example.test"
    timeout: 3s
~~~

### 5.1. What Problem Does the Factory Solve?

It solves the requirement of **parsing YAML syntax and converting it into a `PropertiesPropertySource`** in simple cases, so keys can be looked up from `Environment`.

It does **not** turn the annotation into the Spring Boot Config Data API:

- Does not change when `@PropertySource` is processed.
- Does not automatically apply Boot's profile activation policies.
- Does not apply Config Data import/document location ordering.
- Makes no guarantee of replicating all multi-document syntax.
- Does not grant source precedence equivalent to an `application.yml` outside the JAR.
- Does not turn late-read properties into bootstrap properties.

### 5.2. YamlPropertiesFactoryBean Is Not Spring Boot ConfigDataImporter

Spring Framework's `YamlPropertiesFactoryBean` converts YAML into properties. Spring Boot also has YAML-handling classes in the Config Data pipeline, but using a YAML parser **does not bring along config data loading, profile-based document selection, and source-based overriding**.

If a team needs to use a custom factory, limit its scope to simple YAML files and explicitly test semantics when nested properties or complex structures exist.

### 5.3. When Should You Not Write a Factory?

Do not write a custom factory just because you want to:

- Load a YAML file outside the JAR.
- Have configuration by active profile.
- Combine multiple YAML documents.
- Adjust override order between packaged files and externalized files.
- Use `spring.config.import` or optional imports.

Those goals usually have more suitable and less risky Config Data mechanisms.

## 6. Second Limitation: Multi-Document Configuration Files

Spring Boot supports **multi-document configuration files**. A single file can hold multiple "logical documents", each adding a property source group or values with their own conditions.

### 6.1. YAML Uses ---

Example `application.yml`:

~~~yaml
app:
  message: "default"
  timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  message: "production"
  timeout: 2s
~~~

The first document applies in normal cases. The second document only participates when the `prod` profile is active under Boot's mechanism. When `prod` is active, `app.message` can become `production` and `app.timeout` `2s` because the later active document overrides matching keys from the earlier document.

When `prod` is inactive, values from the first document are retained if no higher-priority source intervenes.

### 6.2. Document Order and Property Precedence

Within the same multi-document file, documents accepted under Boot's conditions are typically processed in order; later documents can override matching values from earlier ones.

However, **order among documents in one file** does not replace precedence across files, import locations, OS environment, and CLI. For example:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.timeout=1s
~~~

When command-line properties are enabled by default, `--app.timeout=1s` normally beats `2s` from the profile-specific YAML document.

### 6.3. Multi-Document Is Not Only for YAML

Spring Boot also supports separating documents in `application.properties` files using designated markers, typically a dedicated line `#---` or `!---`.

Example:

~~~properties
app.message=default
app.timeout=5s

#---
spring.config.activate.on-profile=prod
app.message=production
app.timeout=2s
~~~

There are syntax rules for separator lines and adjacent comment lines. In real use, follow the exact separator format documented for your Spring Boot version; do not assume every comment line with dashes is a valid separator.

### 6.4. @PropertySource Is Not the Right Path for Multi-Document Files

A point warned in Spring Boot's externalized configuration docs: **multi-document property files cannot be loaded with the same semantics via `@PropertySource` or `@TestPropertySource`**.

With traditional `.properties` files, the `#---` marker may simply be treated as an ordinary comment rather than a separator for Config Data documents. Duplicate keys may be handled according to properties parser behavior rather than Boot's profile activation and document order.

With YAML, a custom factory might parse multiple documents in its own way yet still lack `spring.config.activate.on-profile` semantics. Therefore, if the goal is Spring Boot multi-document config, use the **Config Data** pipeline.

## 7. Document Activation Conditions and Profiles

### 7.1. spring.config.activate.on-profile

A YAML document can specify:

~~~yaml
spring:
  config:
    activate:
      on-profile: dev
~~~

This means the document only participates when the profile activation expression matches. This is part of Spring Boot's Config Data mechanism.

Example:

~~~yaml
app:
  feature:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

app:
  feature:
    enabled: true
~~~

When `dev` is active, `app.feature.enabled` can become `true`; when `dev` is inactive, the value stays `false` if no higher source overrides it.

### 7.2. spring.config.activate.on-cloud-platform

A document can be activated based on cloud platform according to values supported by Spring Boot. This activation mechanism also belongs to the Config Data pipeline, not a general condition that every YAML parser understands automatically.

Do not assume a manually invoked `YamlPropertiesFactoryBean` applies all of Spring Boot's cloud platform activation rules.

### 7.3. Do Not Arbitrarily Put spring.profiles.active in Activated Documents

Profile-activating properties like `spring.profiles.active` have very early loading rules. Spring Boot restricts their use in documents that already carry activation/profile-specific conditions. Do not put `spring.profiles.active` inside a document activated by `spring.config.activate.on-profile` expecting it to activate additional documents.

Select active profiles via environment, CLI, or valid configuration sources during bootstrap. Boot then decides which documents participate.

### 7.4. Selecting a Profile Differs from Selecting a Property Source

`spring.profiles.active=prod` instructs Spring Boot to select profiles during the appropriate startup mechanism. It is not merely an arbitrary text property that any late-added source can use to make Boot go back and load all profile-specific files from scratch.

This is the intersection of **processing order** and **timing** clarified in the next section.

## 8. Third Limitation: @PropertySource Is Processed Too Late for Certain Properties

Spring Boot has multiple startup phases. A generalized model:

~~~text
main(String[] args)
          |
          v
Create and prepare Environment
          |
          v
Read command line, OS env, system properties
          |
          v
Config Data: locations, profiles, imports, activation
          |
          v
Early bootstrap decisions
  - early logging configuration
  - spring.main.* and application settings
          |
          v
Create / refresh ApplicationContext
          |
          v
Process @Configuration classes
  - @PropertySource contributes a PropertySource
          |
          v
Initialize / bind / inject beans
          |
          v
Application runs
~~~

The diagram helps visualize the flow and does not replace documentation of all Spring Boot event listeners, initializers, and hooks. **Core point:** `@PropertySource` on `@Configuration` is normally added to `Environment` while the ApplicationContext is refreshing, whereas Boot already needed certain values before that moment.

### 8.1. Logging Configuration Is Read Early

Example:

~~~properties
# late-logging.properties
logging.level.root=DEBUG
logging.file.name=service.log
~~~

If this file is only introduced via:

~~~java
@Configuration
@PropertySource("classpath:late-logging.properties")
class LoggingPropertiesConfiguration {}
~~~

do not expect Boot to use it for full bootstrap logging setup. Spring Boot documentation clearly states that properties such as `logging.*` are read before context refresh, so `@PropertySource` can be **too late** to affect those settings.

Some components or late lookups might see the value after the annotation is processed, but the value appearing in `Environment` at that point **does not prove the logging system was reconfigured**.

For logging configuration that must apply early, use `application.yml`/`application.properties`, environment variables, Java system properties, CLI, or Boot-supported logging mechanisms.

### 8.2. spring.main.* Must Also Be Resolved Early

Example:

~~~properties
# late-main.properties
spring.main.banner-mode=off
spring.main.lazy-initialization=true
~~~

Do not choose `@PropertySource` as the sole source for controlling properties that govern `SpringApplication` creation and context initialization. `spring.main.*` values are consumed earlier than annotation processing during refresh.

For example, to turn off the banner, use:

~~~bash
java -jar app.jar --spring.main.banner-mode=off
~~~

or inside a Config Data file loaded early by Boot:

~~~yaml
spring:
  main:
    banner-mode: off
~~~

### 8.3. spring.config.location / additional-location / import

Keys controlling where to find and import Config Data must be understood with proper timing. Typical examples:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`
- `spring.config.import` inside a Config Data document currently being processed

Do not place keys specifying where to find config data **only inside a file brought in late by `@PropertySource`** and expect Boot to turn back time to search for more files after the config data phase has passed.

In particular, `spring.config.location` and `spring.config.additional-location` determine locations right when Boot prepares the environment. They generally need to come from early sources such as OS environment, system properties, or CLI.

`spring.config.import` is used **inside a loaded Config Data document**, so the loader can follow imports at the proper phase. Writing it in a plain properties file attached to Environment only via `@PropertySource` does not re-trigger the import mechanism.

### 8.4. spring.profiles.active and Profile-Specific Files

Profiles are used by Boot to select Config Data documents. If a properties file only appears after `@PropertySource` runs and provides `spring.profiles.active=prod`, do not expect Boot to load `application-prod.yml` retroactively from the earlier phase.

When selecting a profile for a run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

or via environment:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar app.jar
~~~

In real deployments, ensure the exact Java process receives the environment variable and no higher-priority source overrides it.

## 9. Using Config Data for YAML Outside the JAR

Suppose there is a file:

~~~text
project/
├── app.jar
└── config/
    └── application.yml
~~~

If run from the proper working directory without changing default file discovery, Spring Boot typically searches for config data in locations such as:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

`file:./` is a path relative to the **working directory**, not automatically the directory containing the JAR. This matters when running in Docker, systemd, or an IDE.

### 9.1. Example Outside the JAR

File `./config/application.yml`:

~~~yaml
catalog:
  client:
    endpoint: "https://internal.example.test"
    timeout: 2s
~~~

If this file is loaded by Boot via default search locations, its keys can take precedence over matching values packaged inside the JAR, according to Config Data mechanics.

There is no need to add:

~~~java
@PropertySource("file:./config/application.yml")
~~~

to accomplish that. Omitting the annotation is beneficial because Boot handles YAML, profile activation, precedence, and location semantics inside the pipeline designed for application config files.

### 9.2. spring.config.location

You can explicitly specify locations:

~~~bash
java -jar app.jar \
  --spring.config.location=optional:file:./deployment/
~~~

Be careful: `spring.config.location` **replaces** the default search locations unless you also include the ones you still need. Using it can prevent the application from loading default files you assumed were still read.

The `optional:` prefix allows ignoring a non-existent location in supported mechanisms. It does **not** allow ignoring malformed YAML or invalid required properties.

### 9.3. spring.config.additional-location

When you want to keep default search locations and add another location:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deployment/
~~~

Usually this is a better fit than `spring.config.location` if you only need to load additional external files, because it preserves original search places and adds the new location with precedence ordered per Boot rules.

### 9.4. Location Groups and Order

When using multiple locations or location groups, override order can depend on how locations are grouped. Separators and how Boot processes profile-specific files are important details of Config Data.

Do not replace this principle with "whichever file is listed later in `@PropertySource` always wins". For systems with multiple environments and profiles, determine location groups/precedence per Boot documentation and verify actual keys.

## 10. spring.config.import: Importing Additional Config Files at the Right Phase

An application has `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment/partner.yml"

partner:
  timeout: 5s
~~~

And `./deployment/partner.yml`:

~~~yaml
partner:
  endpoint: "https://partner.example.test"
  timeout: 2s
~~~

When Boot loads the document declaring `spring.config.import`, it can load the imported file within the Config Data phase. Under Boot's import rules, the imported file receives an appropriate precedence level so imported properties can override matching properties in the importing document. For example, `partner.timeout` can receive `2s`.

### 10.1. Why Does import Differ from @PropertySource?

| Criterion | `spring.config.import` | `@PropertySource` |
| --- | --- | --- |
| Processing phase | Config Data processing | Context refresh / configuration class processing |
| Default YAML | Yes, among Boot-supported formats | No, not by default |
| Multi-document activation | Follows Config Data rules | Not built-in |
| Profile-specific variants | Integrated per Boot rules | Not equivalent |
| Optional location | `optional:` per Boot rules | `ignoreResourceNotFound` for annotation resource |
| Early `logging.*`/`spring.main.*` | More suitable | Can be too late |
| Simple properties file added late | Usable, though not always needed | Can be suitable |

### 10.2. Import Does Not Mean Every File on Disk Is Read

Paths in imports must match the working directory or resource location. If a file does not exist, depending on whether `optional:` is declared, Boot may report a location error or skip it. If the file exists with invalid YAML, parser/binding errors can still appear.

Do not use `optional:` to hide **required** configuration. If an endpoint must exist in every production environment, add validation on the typed configuration.

### 10.3. Do Not Assume JSON Is Parsed Like Config Data YAML

An arbitrary JSON file is not necessarily loaded like a default application configuration file. `SPRING_APPLICATION_JSON` is a separate mechanism for passing a JSON object via environment/system property/CLI. Do not equate "importing a file" with "parsing any format into config" without a proper loader.

## 11. Distinguishing @PropertySource and PropertySourceFactory from the Config Data API

### 11.1. @PropertySource

- Declares adding a resource (typically `.properties`) to `Environment`.
- Tied to `@Configuration` processing lifecycle.
- Has a custom factory option to alter how the resource is read.
- Not the right place for bootstrap configuration and multi-document Boot semantics.

### 11.2. PropertySourceFactory

- Determines how to turn an annotation resource into a `PropertySource`.
- Can use a YAML parser and produce a `PropertiesPropertySource`.
- Does **not** move annotation processing timing from refresh to config-data bootstrap.
- Does not automatically provide APIs for profile-based document selection or location groups unless you implement them yourself.

### 11.3. Spring Boot Config Data

- Processes application config files and imports early.
- Has rules for profile activation, search locations, profile-specific variants, and document ordering.
- Supplies values for many settings needed before context refresh.
- Should be the preferred solution for Spring Boot convention externalized configuration.

### 11.4. EnvironmentPostProcessor

When you genuinely need to **programmatically add or transform PropertySources before context refresh**, Spring Boot provides an extension mechanism during `Environment` preparation, such as `EnvironmentPostProcessor`.

Conceptual example:

~~~java
package com.example.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;

public class CustomEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        // Add or adjust PropertySources during the Environment phase.
        // Choose source names and precedence order explicitly.
        // Avoid printing secrets or overriding out-of-scope keys.
    }
}
~~~

For Spring Boot to discover the processor, register it according to your version's mechanism (typically `META-INF/spring.factories` for `EnvironmentPostProcessor`). **Writing a class that implements the interface is not enough**.

If complex Config Data processing is required, there is a dedicated Config Data extension API rather than relying solely on `EnvironmentPostProcessor`. Custom bootstrapping increases maintenance cost, so use it only when Config Data files/imports and standard sources fall short.

### 11.5. Custom Processor Bootstrap Order Also Has Limits

Even though `EnvironmentPostProcessor` runs before context refresh, you cannot assume it runs before **every** Spring Boot step. Other processors, logging initialization, and Config Data processing have orders defined by specific ordering/registration rules. If a property must appear **before another processor**, design the ordering and verify against your Boot version.

Do not treat an extension mechanism as a magic wand fixing every "loaded too late" issue.

## 12. When Is @PropertySource Still Useful?

Relatively suitable scenarios:

1. A legacy module has its own `.properties` file containing keys for the module's beans.
2. A Spring Framework library that does not rely heavily on Boot Config Data conventions.
3. Internal bean configuration that does not affect logging or bootstrap.
4. A packaged properties resource that needs to be added to `Environment` when processing a configuration class.

Example `feature-flags.properties`:

~~~properties
feature.preview.enabled=false
feature.preview.title=Preview mode
~~~

In the module:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:feature-flags.properties")
class PreviewFeatureConfiguration {}
~~~

Reading code:

~~~java
@Component
class PreviewService {

    private final Environment env;

    PreviewService(Environment env) {
        this.env = env;
    }

    boolean enabled() {
        return env.getProperty(
                "feature.preview.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

This is an easy-to-understand use case. However, if you need changes by profile, deployment, or external YAML files, look at migrating to `application.yml` or `spring.config.import`.

## 13. XML, .properties, and YAML Configuration: Accurate Distinctions

### 13.1. .properties Files

Key/value format:

~~~properties
acme.client.endpoint=https://api.example.test
acme.client.timeout=3s
~~~

Default `@PropertySource` handles this format through the appropriate properties resource mechanism.

### 13.2. Java Properties-Format XML Files

Spring Framework can load certain XML resources formatted as XML properties via supported loaders. However, **this does not mean arbitrary XML files** become a PropertySource. An XML bean definition file and an XML properties file are two different document types.

When configuring an annotation to use an XML resource, verify whether the loader and format are genuinely supported.

### 13.3. YAML

YAML requires a parser/loader that understands objects, lists, and documents. Boot provides full support under Config Data conventions, whereas default `@PropertySource` is not equivalent.

Do not assume renaming `.properties` to `.yml` suffices or that a minimal YAML factory automatically applies all profile rules.

## 14. Common Mistakes When Combining YAML and @PropertySource

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| `@PropertySource("classpath:extra.yml")` fails to bind nested keys | Default factory does not process YAML the Boot way | Use Config Data or a controlled custom YAML factory |
| Multi-document YAML does not switch by profile | Parser/annotation lacks Boot activation semantics | Move file into Config Data |
| `#---` does not create a new document with `@PropertySource` | Separator line is treated as a normal properties comment | Use Boot's application config loader |
| `logging.level.root` in `@PropertySource` has no effect at bootstrap | Annotation runs after logging is already set up | Put property in an early source |
| `spring.main.banner-mode` in `@PropertySource` has no effect | `SpringApplication` settings were already read | Use Config Data/CLI/env |
| `spring.config.location` in `@PropertySource` does not make Boot load new files | Config Data search already finished | Provide location via an early bootstrap source |
| Active profile set late does not load profile file | Profile activation already occurred | Provide profile via valid CLI/env |
| Property in `@PropertySource` differs from observed value | Config Data/OS/CLI has higher precedence | Inspect actual PropertySources |
| External file outside JAR not found | Wrong working directory/resource location | Check `user.dir`, absolute/relative paths |
| YAML partially read but lists/maps lost | Flattening factory has limits or binding code differs | Test schema, use appropriate loader |
| `@PropertySource` class not processed | Class was not included in configuration processing | Import/scan configuration properly |
| Properties file has duplicate keys | Duplicate keys/multiple loading paths | Check precedence rules and source configuration |
| Secrets exposed when printing Environment | Logging all values or exposing unprotected Actuator endpoints | Restrict access, mask, do not log secrets |

### 14.1. Do Not Lump File-Loading Errors with Binding Errors

A file may be read successfully yet Java fields remain null because:

- `@ConfigurationProperties` prefix does not match.
- Property key is misspelled.
- Higher-priority source overrides it.
- Properties class is not registered.
- Nested object has no data or special semantics.
- Conversion does not recognize the type.

Conversely, if the file is not loaded properly by the loader, there will be no matching property for the Binder to use. Diagnostics must separate these two phases.

## 15. Inspecting PropertySources to Understand the Winning Source

For a **non-sensitive** key:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.client.timeout";

        System.out.println("Effective: "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

In specific cases, `PropertySource` names may reflect Config Data files or annotations. However, do not write business logic relying on a hardcoded `source.getName()` string.

**Note:** Some sources (especially env vars) have relaxed binding when processed by Binder. `source.getProperty(key)` returning null for a specific name is not conclusive proof that the corresponding property cannot bind via an environment variable name. When needed, inspect binding results and origin metadata provided by Boot.

### 15.1. Actuator and Security

Spring Boot Actuator provides endpoints like `env` and `configprops` to help diagnose configuration in permitted environments. Enable and access them strictly under control; protect sensitive values and avoid exposing configuration endpoints publicly just to debug property sources.

Values such as passwords, API keys, and signing secrets must not be printed in logs, error messages, or public endpoints just to debug property sources.

## 16. Choosing an Option Based on Need

| Need | Typically appropriate tool |
| --- | --- |
| Add a few keys from an internal `.properties` file when processing `@Configuration` | `@PropertySource` |
| Load standard profile-specific YAML | Config Data `application.yml`/`application-{profile}.yml` |
| Load a separate YAML file outside the JAR | `spring.config.import` or additional-location |
| Single YAML file with multiple documents using `---` | Boot Config Data loader |
| Multi-document `.properties` file using `#---` | Boot Config Data loader |
| Adjust `logging.*` early | Config Data, env, JVM property, or CLI |
| Adjust `spring.main.*` | Early sources such as Config Data/env/CLI |
| Specify where to search for config data | `spring.config.location`/`additional-location` during bootstrap |
| Create a custom property source very early | `EnvironmentPostProcessor` with proper ordering/registration |
| Extend specialized Config Data types | Spring Boot Config Data API |
| Bind multiple structured keys to a Java type | `@ConfigurationProperties` |
| Add configuration validation | `@Validated` and Bean Validation |

### 16.1. Pick the Simplest Solution with the Right Semantics

If the requirement is "add a YAML file containing timeout, endpoint, and profile-specific documents", do not solve it by creating a YAML factory and reimplementing profile and location logic. Config Data is built for that need.

If the requirement is merely "a legacy module has a small properties file", `@PropertySource` may be sufficient without bringing in complex Bootstrap extensions.

## 17. Testing: Ensuring the Loading Mechanism Matches Intent

When behavior matters, tests must exercise the **actual loader mechanism**, not just read a file and assert syntax.

### 17.1. Testing @PropertySource with .properties

Create `src/test/resources/extra-test.properties`:

~~~properties
demo.greeting=Hello
demo.timeout=5s
~~~

Test config:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:extra-test.properties")
class ExtraTestConfiguration {}
~~~

With a Spring context verifying this class is processed, you can assert `Environment.getProperty("demo.greeting")` is `Hello`. This tests resource loading and `PropertySource` creation, not Config Data profile activation.

### 17.2. Testing Multi-Document Files with Real Spring Boot Config Data

If you need to test:

~~~yaml
demo:
  greeting: "default"

---
spring:
  config:
    activate:
      on-profile: test

demo:
  greeting: "from-test-profile"
~~~

place the YAML in a config location loaded by Boot and start a test context with the `test` profile active, for example via `@ActiveProfiles("test")` combined with Spring Boot tests. The expected result is `from-test-profile` if no higher-priority source overrides it.

Do not use an `ApplicationContextRunner` unconfigured for Config Data loading and then be surprised that the YAML document was not read. The test harness must actually use the pipeline under test.

### 17.3. Testing Properties Needed Early

To verify bootstrap logging or `spring.main.*`, test the actual behavior of a Spring Boot run with appropriate config data/CLI, not merely asserting that `Environment` eventually contains a property. A property present **after refresh** does not prove it affected the bootstrap phase.

### 17.4. Testing Precedence Between Sources

`application.yml`:

~~~yaml
demo:
  color: blue
~~~

A file loaded via `@PropertySource`:

~~~properties
demo.color=red
~~~

Under default precedence, config data can win so `demo.color=blue`. If CLI supplies `--demo.color=green`, the value can become `green`.

Tests must clearly define which sources are present, which profiles are active, and which custom processors are installed, avoiding assumptions that the test runner's environment lacks colliding properties.

## 18. Hands-On Exercises

### Exercise A — A Simple Properties File

Create `src/main/resources/my-extra.properties`:

~~~properties
lesson.message=Hello Extra
lesson.enabled=true
~~~

Create a `@Configuration` with `@PropertySource("classpath:my-extra.properties")`. Read both keys from `Environment`. Try deleting the file and observing the load error, then consider `ignoreResourceNotFound=true` when the file is genuinely optional.

### Exercise B — Switching to YAML

Write `my-extra.yml`:

~~~yaml
lesson:
  message: "Hello YAML"
  enabled: true
~~~

Try using the default annotation and observe the difference from `.properties`. Then use `spring.config.import` inside a Config Data file to load YAML properly. Explain why the two processing paths differ.

### Exercise C — Custom YAML Factory

Implement `SimpleYamlPropertySourceFactory` following the example in section 5. Use a single YAML document and verify `lesson.enabled` is read. Then add a second document with `spring.config.activate.on-profile` and explain why factory results should not be assumed identical to Boot Config Data.

### Exercise D — Multi-Document YAML

Create `application.yml`:

~~~yaml
lesson:
  mode: default
---
spring:
  config:
    activate:
      on-profile: prod
lesson:
  mode: prod
~~~

Run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Predict `lesson.mode`. Run without the `prod` profile and compare. Check which source wins if CLI adds `--lesson.mode=from-cli`.

### Exercise E — Multi-Document Properties

Create `application.properties` with the `#---` separator and a `spring.config.activate.on-profile=prod` document. Let Boot load it via Config Data. Then try the same file via `@PropertySource` and explain why similar profile activation cannot be expected.

### Exercise F — Logging Timing

Add `logging.level.root=DEBUG` to a file loaded only via `@PropertySource`. Compare with placing the property in `application.yml` or CLI. Observe bootstrap logging to understand the difference between **a property present in the final Environment** and **a property present when logging is configured**.

### Exercise G — File Outside the JAR

Place `./config/application.yml` next to a test run directory, then launch from the appropriate working directory. Try changing the working directory and compare results. Explain why `file:./config/` does not automatically mean the directory containing the JAR.

### Exercise H — Optional Import

In `application.yml` set:

~~~yaml
spring:
  config:
    import: "optional:file:./extra.yml"
~~~

Run when the file is missing and when the file exists. Then intentionally write invalid YAML in the existing file. Explain the difference between an optional location and malformed configuration syntax.

### Exercise I — Choosing the Tool

For each requirement, pick `@PropertySource`, Config Data, or `EnvironmentPostProcessor`:

1. Add a `.properties` file containing labels for a legacy module.
2. Use YAML with three profile-activated documents.
3. Change the value of `spring.main.banner-mode`.
4. Add a config data location outside the JAR.
5. Supply properties from a custom system before context refresh where Boot has no built-in loader.
6. Bind HTTP client configuration into a typed record with validation.

Explain why a single annotation is not optimal for every case.

## 19. Checklist When Investigating Ineffective Configuration

- [ ] Verify the exact key name and prefix.
- [ ] Verify the resource exists at the actual classpath/file path.
- [ ] Check whether the file is `.properties` or YAML and whether the loader understands the format.
- [ ] Check requirements for multiple documents, separators, and profile activation.
- [ ] Identify whether the application is using `@PropertySource` or Config Data.
- [ ] Confirm active profiles were provided from an early source.
- [ ] Check working directory for `file:./...` paths.
- [ ] Check whether `spring.config.location` accidentally replaced default search locations.
- [ ] Check whether `spring.config.import` is inside a Config Data document processed by Boot.
- [ ] Distinguish late-added properties from properties needed during bootstrap.
- [ ] Check precedence across config data, env, system properties, JSON, and CLI.
- [ ] Distinguish file loading from whether the `@ConfigurationProperties` bean is registered/bound.
- [ ] Do not print secrets when inspecting Environment or Actuator.
- [ ] Have tests matching the actual loading path and profiles used in production.

## 20. Takeaways

1. **`@PropertySource` is not equivalent to Spring Boot Config Data.** It adds a property source while processing `@Configuration` and does not automatically perform full application configuration loading rules.
2. **YAML is not supported by `@PropertySource` by default like `application.yml`.** You can create a custom `PropertySourceFactory` for simple YAML, but that does not turn it into a Config Data loader.
3. **Multi-document YAML with `---` and multi-document properties with `#---`/`!---`** have semantics processed by Spring Boot Config Data; do not load these files via `@PropertySource` or `@TestPropertySource` if document-level activation is needed.
4. **Processing timing determines the outcome:** `@PropertySource` is added during context refresh; `logging.*` and `spring.main.*` may have already been read earlier.
5. **Keys selecting config-data locations and profiles** must be supplied from an appropriate source early enough, rather than expecting a late resource annotation to re-trigger the pipeline.
6. For YAML/profiles/imports/external files, generally prefer **`application.yml`, `spring.config.import`, `spring.config.location`, or `spring.config.additional-location`**.
7. `@ConfigurationProperties` is the binding mechanism for already-loaded data, not a file loader; Bean Validation is a separate validation layer.
8. **A property present in the final Environment has not necessarily influenced the bootstrap phase.** To verify an early property, test actual startup behavior.
9. Choose extension mechanisms like `EnvironmentPostProcessor` or the Config Data API only when standard configuration sources cannot meet the need, and control processing order explicitly.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): configuration sources, precedence, `@PropertySource`, and timing limitations.
- [Spring Boot Reference — Multi-Document Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.multi-document): YAML `---`, properties separators, and limitations of `@PropertySource`/`@TestPropertySource`.
- [Spring Boot Reference — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): `spring.config.import` and optional locations.
- [Spring Boot Reference — Config Data Files](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files): file locations, profile-specific files, and loading order.
- [Spring Framework Reference — @PropertySource](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html): placeholders and `Environment`; review the `PropertySource` API to distinguish the annotation from Config Data.
- [Spring Framework Javadoc — PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/PropertySource.html): processing timing and usage of `@PropertySource`.
- [Spring Framework Javadoc — PropertySourceFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/support/PropertySourceFactory.html): extension point for annotation resource loaders.
- [Spring Framework Javadoc — YamlPropertiesFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/YamlPropertiesFactoryBean.html): converting YAML into Java Properties in appropriate scenarios.
- [Spring Boot Reference — EnvironmentPostProcessor](https://docs.spring.io/spring-boot/how-to/application.html): `SpringApplication`/`Environment` extension points by version.
