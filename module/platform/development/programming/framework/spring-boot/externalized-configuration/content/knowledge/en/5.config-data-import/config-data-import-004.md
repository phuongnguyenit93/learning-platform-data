# Precedence of Imported Data vs. the Importing Document

## 1. The problem: the same property appears in two configuration documents

When learning Spring Boot Externalized Configuration, we usually start with `application.yml` or `application.properties`. However, a real-world application often splits configuration into multiple files: shared configuration in `application.yml`, feature-specific configuration in `feature.yml`, and deployment configuration in files outside the JAR.

Spring Boot provides `spring.config.import` to **load additional configuration data (Config Data)** from another resource. When two documents both declare the same property, an important question arises:

**Does a property in the imported document have higher or lower precedence than the property in the document declaring `spring.config.import`?**

The core rule of the Config Data mechanism is:

> **Values from an imported document have higher precedence than values for the same key in the document that declared that import.**

Consider this configuration:

```yaml
# application.yml
spring:
  config:
    import: "classpath:feature.yml"

demo:
  message: "From application.yml"
  retries: 2
```

And the second file:

```yaml
# feature.yml
demo:
  message: "From feature.yml"
```

After Config Data is loaded, if no other configuration source overrides it, the result is:

| Key | Effective value | Explanation |
| --- | --- | --- |
| `demo.message` | `From feature.yml` | The imported document beats the importing document |
| `demo.retries` | `2` | The imported file lacks this key, so the value from `application.yml` is kept |

This shows that Spring Boot resolves **property by property**. Importing does not mean all properties of the original document are erased or replaced wholesale.

## 2. What are the importing document and the imported document?

To express this clearly, distinguish the two roles:

- **Importing document:** the configuration document containing the `spring.config.import` key, for example `application.yml`.
- **Imported document:** the configuration resource located and loaded based on the value of `spring.config.import`, for example `feature.yml`.

In the example above, `application.yml` is the importing document; `feature.yml` is the imported document. This ordering is a relationship **between documents** in the Config Data mechanism, not the order of YAML lines.

Spring Boot processes import declarations when it discovers them. The imported document is placed into the Config Data set adjacent to the document that triggered the import and takes precedence to **override matching keys of the declaring document**.

Conceptual diagram:

```text
application.yml
    |
    | spring.config.import=classpath:feature.yml
    v
feature.yml

When both declare demo.message:

feature.yml
    > application.yml
```

The `>` symbol indicates higher precedence when resolving the same key, rather than merely read order on disk.

If `feature.yml` does not declare `demo.message`, Spring Boot continues using the matching value from `application.yml` or another configuration source.

## 3. Why do imported values take precedence?

The import mechanism lets you build configuration in layers. The main document defines common values and points to where additional configuration should come from; the imported document can supply more specific values.

For example, an order-processing application with default configuration:

```yaml
# application.yml
spring:
  config:
    import: "classpath:payment-defaults.yml"

payment:
  currency: "VND"
  timeout: 30s
  provider: "basic"
```

Imported file:

```yaml
# payment-defaults.yml
payment:
  timeout: 10s
  provider: "sandbox"
```

The final values can be understood as:

```text
payment.currency  = VND      (only in the declaring document)
payment.timeout   = 10s      (imported document overrides 30s)
payment.provider  = sandbox  (imported document overrides basic)
```

This feature is convenient when additional configuration is managed in a separate location. However, name and organize files so readers can predict which source applies, especially when different deployment environments use different files.

Do not assume that any file with "defaults" in its name automatically has low precedence: **filenames do not decide precedence**. The loading relationship via `spring.config.import` and Config Data rules are what decide it.

## 4. Practical example with application.properties and imported.properties

You can verify the rule with a simple Spring Boot application.

### 4.1. Prepare the files

Place two files in the resources directory:

```text
src/main/resources/
├── application.properties
└── imported.properties
```

File `application.properties`:

```properties
spring.config.import=classpath:imported.properties

demo.source=main
demo.mode=from-main
demo.timeout=45
```

File `imported.properties`:

```properties
demo.mode=from-import
demo.timeout=15
demo.feature-enabled=true
```

### 4.2. Read values with Environment

Add a component that prints the exact properties to observe:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigImportPrinter implements ApplicationRunner {

    private final Environment environment;

    public ConfigImportPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("demo.source = "
                + environment.getProperty("demo.source"));
        System.out.println("demo.mode = "
                + environment.getProperty("demo.mode"));
        System.out.println("demo.timeout = "
                + environment.getProperty("demo.timeout", Integer.class));
        System.out.println("demo.feature-enabled = "
                + environment.getProperty("demo.feature-enabled", Boolean.class));
    }
}
```

This is an example reading `Environment`, with no Controller or HTTP API needed. In a real application, you can also bind the properties to a `@ConfigurationProperties` class.

### 4.3. Run and explain

Suppose the application has been packaged as `app.jar`:

```bash
java -jar app.jar
```

Lines printed by the sample component:

```text
demo.source = main
demo.mode = from-import
demo.timeout = 15
demo.feature-enabled = true
```

Analysis table:

| Property | application.properties | imported.properties | Result |
| --- | --- | --- | --- |
| `demo.source` | `main` | Absent | `main` |
| `demo.mode` | `from-main` | `from-import` | `from-import` |
| `demo.timeout` | `45` | `15` | `15` |
| `demo.feature-enabled` | Absent | `true` | `true` |

We have two combination modes: **overriding** when the same key appears, and **supplementing** when a key exists in only one source. This is the basis for explaining most simple import scenarios.

## 5. The position of import in YAML does not determine precedence

A common misconception is thinking that if `spring.config.import` is written at the top of the file, the imported values will be overridden by lines below it; and if written at the bottom, the imported values will win. That assumption is incorrect for a standard YAML document.

Both ways below declare an import within the same document:

```yaml
spring:
  config:
    import: "classpath:feature.yml"

demo:
  mode: "main"
```

And:

```yaml
demo:
  mode: "main"

spring:
  config:
    import: "classpath:feature.yml"
```

If `feature.yml` has `demo.mode=feature`, the imported value still beats `demo.mode=main` in the declaring document. Spring Boot does not apply a "whichever line appears later wins" rule to key order inside a YAML object.

Distinguish **the position of a key inside a document** from **the precedence order between configuration documents**.

When a YAML file contains multiple documents separated by `---`, each document participates in Config Data ordering in its own context. Therefore, check which document declares the import and whether it has profile activation conditions, rather than treating the entire physical file as a single block.

## 6. Imports do not outrank every configuration source

The rule "an import beats the declaring document" is a **local rule within Config Data loading**. It does not mean the imported file is placed at the top of every `PropertySource` the application has.

Using the same two files:

```properties
# application.properties
spring.config.import=classpath:imported.properties
demo.mode=from-main
```

```properties
# imported.properties
demo.mode=from-import
```

When running:

```bash
java -jar app.jar --demo.mode=from-cli
```

The value of `demo.mode` is:

```text
from-cli
```

A standard command-line argument `--demo.mode=from-cli` has higher precedence than values in the Config Data group, including imported files.

Among common sources in Spring Boot 3.x, the generalized model from highest to lowest is:

```text
Command-line argument --demo.mode=...
    >
SPRING_APPLICATION_JSON source
    >
Java system property -Ddemo.mode=...
    >
Environment variable DEMO_MODE
    >
Imported Config Data: imported.properties
    >
Importing Config Data document: application.properties
```

The last two lines apply only to **the specific importing/imported document pair under discussion**. If the application also has profile files, external locations outside the JAR, location groups, or other documents, you must consider the precedence rules of Config Data as a whole. Do not elevate this illustrative diagram into an absolute order for every file in every application.

Key takeaway: there are **two levels of resolution**. The first level is the order across source types such as command line, JVM, environment variables, and Config Data. The second level is the order **within Config Data**, including which document declared an import and which documents were loaded by that import.

## 7. Imported documents can reside outside the JAR

Imports are not restricted to files on the classpath. For instance, you might have:

```text
deploy/
├── app.jar
└── config/
    └── overrides.properties
```

Inside `application.properties` packaged in the JAR:

```properties
spring.config.import=optional:file:./config/overrides.properties
demo.mode=default
demo.timeout=30
```

File `deploy/config/overrides.properties`:

```properties
demo.mode=external
```

When the working directory is `deploy/` and you run:

```bash
java -jar app.jar
```

`demo.mode` will be `external` while `demo.timeout` remains `30`, assuming no higher-precedence source exists.

Components in the import location:

- `file:` denotes a resource on the file system.
- `./config/overrides.properties` is a path relative to the working directory in this example.
- `optional:` allows the application to continue if the import location does not exist, rather than treating the mere absence of that location as a mandatory failure.

If `overrides.properties` is deleted or omitted, the example with `optional:` can still use `demo.mode=default` from `application.properties`.

**`optional:` does not change precedence when the file is present.** It only changes how a missing resource is handled. Once loaded successfully, `overrides.properties` still overrides matching keys in the importing document.

Be careful not to confuse a missing file with a syntax error inside an existing file: `optional:` does not make malformed configuration contents valid.

## 8. Fixed-location import vs. relative import

Two ways of referencing are worth noting:

```properties
spring.config.import=classpath:feature.properties
```

This explicitly points to a resource on the classpath.

```properties
spring.config.import=feature.properties
```

An import location without a fixed prefix such as `classpath:` or `file:` can be resolved **relative to the location of the importing document** under the Config Data mechanism. Therefore, `feature.properties` does not automatically mean "search in the current working directory."

For example, if a configuration file at `file:./config/application.properties` declares:

```properties
spring.config.import=feature.properties
```

Spring Boot resolves the import relative to that configuration location, so `./config/feature.properties` is the natural candidate. If you want to specify a particular resource at an explicit location, use the `file:` or `classpath:` prefix.

**The precedence relationship does not change because of path notation:** once a document is successfully imported, matching keys in it still take precedence over values in the importing document.

## 9. When imports meet profile-specific configuration

Profile-specific configuration introduces more documents into the picture. Example:

```text
src/main/resources/
├── application.yml
├── feature.yml
└── feature-prod.yml
```

File `application.yml`:

```yaml
spring:
  config:
    import: "classpath:feature.yml"

demo:
  mode: "main"
  region: "local"
```

File `feature.yml`:

```yaml
demo:
  mode: "feature-base"
```

File `feature-prod.yml`:

```yaml
demo:
  mode: "feature-prod"
```

When running the application with the `prod` profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

The Config Data mechanism takes into account profile-specific variants of the imported resource. With this simple set of files and no other overriding source:

```text
demo.mode   = feature-prod
demo.region = local
```

Explanation:

- `feature.yml` supplies the base imported configuration values.
- `feature-prod.yml` supplies the variant matching the `prod` profile.
- `demo.region` exists only in `application.yml`, so it still uses the value `local`.

Now suppose `application-prod.yml` or YAML documents conditioned by `spring.config.activate.on-profile` are also present. The number of participating documents grows and you must evaluate the entire Config Data order, including profiles and locations; you cannot simply say "anything imported beats every profile configuration."

A useful practical rule is: when facing a puzzling result, first list **which documents were actually loaded**, then locate the conflicting key and examine the precedence of those documents. A file existing on disk does not prove it was loaded.

## 10. Nested imports and repeated imports

An imported file can itself declare `spring.config.import` to load further resources. Example:

```text
application.properties
    |
    v
feature.properties
    |
    v
feature-overrides.properties
```

Main file:

```properties
# application.properties
spring.config.import=classpath:feature.properties
demo.mode=main
```

Second file:

```properties
# feature.properties
spring.config.import=classpath:feature-overrides.properties
demo.mode=feature
```

Third file:

```properties
# feature-overrides.properties
demo.mode=override
```

With this simple chain of documents, `demo.mode` resolves to `override`: the outermost document loads `feature.properties`, then `feature.properties` loads `feature-overrides.properties`; each import relationship applies the same override rule.

Spring Boot also has a mechanism to avoid importing the same resource multiple times just because it is declared repeatedly. Therefore, do not expect that writing the same import path twice will change precedence or create two copies of the configuration.

When organizing many files, keep import relationships clear and avoid circular dependencies or overly deep import chains. A small set of files with easy-to-understand roles is much easier to diagnose because readers can trace the source of every property.

## 11. Distinguishing import order from the order of other configuration groups

Saying "an imported document has higher precedence than the importing document" is very helpful, yet it only directly resolves **a pair of documents in an import relationship**. It is not enough to answer every "which file wins?" question in a system with many configurations.

Example:

```text
application.yml
    import: feature.yml

./config/application.yml
application-prod.yml
./config/application-prod.yml

Environment variables, JVM properties, command-line arguments
```

Beyond the import relationship, the following factors can also alter the chosen value:

1. **Configuration locations:** resources packaged on the classpath and resources outside the JAR participate in Config Data location precedence rules.
2. **Profiles:** documents applicable to active profiles can override properties in general documents.
3. **Multiple documents in one file:** the `---` marker can split a YAML file into separate documents; each document can have activation conditions or import declarations.
4. **Sources outside Config Data:** command-line arguments, environment variables, and JVM properties can override values from configuration documents.
5. **Application-added configuration sources:** libraries or startup code can insert additional `PropertySource` entries into `Environment`.

Hence, you should not describe every scenario with a single rule: "whichever file is imported last beats everything." To know the exact value, check **the actual set of sources** Spring Boot builds and how they are ordered.

## 12. Common errors

### 12.1. Thinking the main document always has higher precedence

Incorrect reasoning:

> `application.yml` is the main file, so values in it must beat the `feature.yml` file it loads.

In reality, for a document directly declaring an import, matching keys in the imported file **take precedence over** values in the declaring document. Calling a file "main" does not grant special precedence in this relationship.

### 12.2. Thinking import is like copying text to the top of the file

Importing is an operation that loads documents into the Config Data system, not pasting raw file contents into a position in YAML or Properties text. Therefore, placing `spring.config.import` before or after another key in the same document does not determine override order.

### 12.3. Thinking every value in the original document is lost

If the imported document does not declare a key, the value in the declaring document can still be used. Overriding happens on **colliding keys**, not by wiping out the entire property set of the original document.

### 12.4. Using `optional` and thinking the import's precedence is lowered

`optional:` allows skipping a missing location in supported cases. It does not lower the precedence of an existing file below the declaring document.

### 12.5. Overlooking command-line arguments

Suppose `feature.properties` defines `demo.mode=feature` and the application runs with `--demo.mode=cli`. The effective value is `cli` because command-line arguments have higher precedence than Config Data in a standard Spring Boot setup.

### 12.6. Only checking whether the file exists

A file can exist yet fail to load due to a wrong import path, an inactive profile, or a different search location than expected. Verify that the document actually entered `Environment` before drawing conclusions about precedence.

## 13. How to observe property values and sources

The simplest way to verify this lesson is to read the exact key experiencing a conflict:

```java
String mode = environment.getProperty("demo.mode");
System.out.println("demo.mode = " + mode);
```

If you want to find which source provided a value during investigation, you can iterate over the `PropertySource` entries from `ConfigurableEnvironment`:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class ConfigSourceInspector implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigSourceInspector(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "demo.mode";

        System.out.println("Effective value: "
                + environment.getProperty(key));

        for (PropertySource<?> source : environment.getPropertySources()) {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        }
    }
}
```

The `PropertySource` entries are traversed in the order `Environment` uses to look up properties. The value from the highest-precedence matching source is usually the one selected. Source names typically help identify the corresponding configuration document, for example a source created from `application.properties` or `imported.properties`.

The snippet above should only be used with non-sensitive sample keys. Never log all environment variables, passwords, access tokens, or secret values. In an application with Spring Boot Actuator, the `env` endpoint can assist investigation when properly configured and secured.

**Note:** observation methods show the effective result and the active property sources, but they do not replace understanding the import principles in Config Data.

## 14. Exercise: predict effective properties

Given two files:

```yaml
# application.yml
spring:
  config:
    import: "classpath:module.yml"

demo:
  name: "main"
  retries: 3
  enabled: false
```

```yaml
# module.yml
demo:
  name: "module"
  enabled: true
  region: "asia"
```

**Question 1:** If the application uses only these two files, what are the results for the four keys?

| Key | Answer |
| --- | --- |
| `demo.name` | `module` |
| `demo.retries` | `3` |
| `demo.enabled` | `true` |
| `demo.region` | `asia` |

**Explanation:** `demo.name` and `demo.enabled` are overridden by the import; `demo.retries` remains from the original document; `demo.region` is added by the imported document.

**Question 2:** If you also run:

```bash
java -jar app.jar --demo.name=cli --demo.retries=8
```

where do the results change?

```text
demo.name    = cli
demo.retries = 8
demo.enabled = true
demo.region  = asia
```

The two keys provided by the command line have higher precedence than Config Data, while the other keys keep the values chosen after processing the import relationship.

**Question 3:** If you remove `demo.enabled` from `module.yml`, what is the result of `demo.enabled`?

```text
demo.enabled = false
```

When the imported document no longer defines that key, the configuration in the declaring document remains in effect.

## 15. Takeaways

- `spring.config.import` instructs Spring Boot to load additional resources under the **Config Data** mechanism.
- In a direct relationship between two documents, **the imported document has higher precedence than the importing document** for colliding keys.
- Configuration is combined **key by key**; data that is not overridden can still come from the declaring document.
- Where `spring.config.import` appears inside a YAML/Properties document does not decide precedence between documents.
- `optional:` adjusts handling when an import location does not exist; it does not alter the precedence of a successfully loaded file.
- Other sources, especially **command-line arguments**, can override Config Data results. Profiles, configuration locations, and multi-document files also affect the final order.
- When verifying, read keys through `Environment` and, if needed, inspect the loaded `PropertySource` entries rather than guessing from filenames alone.
