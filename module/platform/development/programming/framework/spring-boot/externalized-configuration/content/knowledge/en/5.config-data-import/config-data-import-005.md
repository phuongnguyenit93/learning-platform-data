# Multiple Imports, Nested Imports, and the Load-Once Rule in Spring Boot 3.3

## 1. Why does an application need multiple configuration imports?

A Spring Boot application can start with `application.properties` or `application.yaml`. As features grow, one large file often holds many different groups of settings: processing limits, service endpoints, notification settings, environment-specific configurations, and shared values. Instead of copying every key into one file, Spring Boot allows **importing additional configuration data** using the `spring.config.import` property.

A file can declare multiple imports, an imported file can in turn import other files, and the same resource can be referenced from multiple places. These cases lead to practical questions:

- If two imported files both define `app.timeout`, which value is used?
- If `application.properties` imports `core.properties`, and `core.properties` imports `limits.properties`, what is the precedence order?
- If `limits.properties` is referenced two or three times, does Spring Boot load and override it repeatedly?
- Where are relative paths in nested files resolved from?
- What happens when a mandatory file is missing, when an import is optional, or when profiles are activated?

This lesson uses **Spring Boot 3.3.x** and Java 17 or higher. The goal is to understand how to design import chains, predict effective values, and trace causes when configuration behaves unexpectedly. Examples apply to the **Config Data** loading system of Spring Boot 3.3.

## 2. Grasping the exact role of `spring.config.import`

`spring.config.import` is a special property processed by Spring Boot during startup to load additional configuration sources. It can be declared in `application.properties`:

```properties
spring.application.name=order-service
spring.config.import=classpath:/config/common.properties
app.name=Order API
```

Or in `application.yaml`:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "classpath:/config/common.properties"

app:
  name: Order API
```

The `config/common.properties` file on the classpath might contain:

```properties
app.name=Order API from common
app.retry.max-attempts=4
```

In this simple scenario, **values from the imported file have higher precedence than values in the document declaring the import**. `app.name` effectively becomes `Order API from common`, and `app.retry.max-attempts` is added to the lookup set of properties.

Keep these terms distinct:

| Concept | Meaning |
| --- | --- |
| Importing document | A configuration document containing the `spring.config.import` key |
| Import location | Address of the resource to load, such as `classpath:/config/common.properties` |
| Imported document | Configuration contents loaded from the import location |
| `PropertySource` | A source of values that Spring uses when resolving properties |
| `Environment` | Interface for looking up effective values after evaluating sources |
| Precedence | Rules deciding which value wins when sources declare the same key |

Importing additional files does **not** mean creating a separate Spring bean per file. It is the process of building the configuration value set before the application consumes those values via `Environment`, `@Value`, or `@ConfigurationProperties`.

An easy-to-remember diagram:

```text
application.properties
  spring.config.import=common.properties
          |
          v
     common.properties
          |
          v
  Loaded config data documents
          |
          v
    Spring Environment
          |
          v
  Beans receive configuration values
```

## 3. A single import: the imported source takes precedence over its caller

Suppose the application's classpath has two files:

```text
src/main/resources/
├── application.properties
└── config/
    └── common.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/common.properties

demo.label=Root application
demo.pool-size=8
```

`config/common.properties`:

```properties
demo.label=Imported value
demo.timeout=5s
```

When no other configuration source overrides them, the expected result is:

| Key | Value | Source |
| --- | --- | --- |
| `demo.label` | `Imported value` | `common.properties`, overriding the file that called the import |
| `demo.pool-size` | `8` | Only in `application.properties` |
| `demo.timeout` | `5s` | Only in `common.properties` |

Spring Boot 3.3 documentation describes imported documents as being placed **immediately after the importing document in precedence order**. Therefore, the imported document can override keys from the document that called it.

Avoid confusing this with text insertion: Spring Boot does not literally concatenate two files into one `.properties` file; it loads configuration documents and applies precedence rules to colliding keys.

### Line position inside the same document does not change precedence

These two ways of writing have the same meaning:

```properties
spring.config.import=classpath:/config/common.properties
demo.label=Root application
```

```properties
demo.label=Root application
spring.config.import=classpath:/config/common.properties
```

`common.properties` still has higher precedence for the `demo.label` key. **The order of the `spring.config.import` line relative to value lines in the same document does not decide overriding.** This rule differs from the order of **locations inside an import list** in the next section.

## 4. Multiple imports in one document: later imports take precedence

### 4.1. List syntax

Place multiple locations in a single `spring.config.import` value, separated by commas:

```properties
spring.config.import=classpath:/config/base.properties,classpath:/config/override.properties
```

For YAML, you can write the same list as a string:

```yaml
spring:
  config:
    import: "classpath:/config/base.properties,classpath:/config/override.properties"
```

Spring Boot processes locations **in the order listed**; if imported files set the same key, **an import listed later has higher precedence than an earlier import**.

Illustrative structure:

```text
src/main/resources/
├── application.properties
└── config/
    ├── base.properties
    └── override.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/base.properties,classpath:/config/override.properties

demo.name=app
demo.cache.enabled=false
```

`config/base.properties`:

```properties
demo.name=base
demo.region=global
demo.cache.enabled=true
```

`config/override.properties`:

```properties
demo.name=override
demo.region=apac
```

Result in this example:

| Key | Final value | Explanation |
| --- | --- | --- |
| `demo.name` | `override` | Present in all three; later import overrides earlier import and root document |
| `demo.region` | `apac` | Present in both imports; `override.properties` comes later |
| `demo.cache.enabled` | `true` | Only `base.properties` import overrides the original value |
 
Precedence model for **the documents in this example**:

```text
High precedence
    config/override.properties
             |
    config/base.properties
             |
    application.properties
Low precedence
```

This is the local ordering of the import chain under examination. It does **not** claim that these documents always beat every other Spring Boot source such as command-line arguments, environment variables, profile configurations, or documents loaded from locations outside the JAR.

### 4.2. Changing import order can change the result

If you swap to:

```properties
spring.config.import=classpath:/config/override.properties,classpath:/config/base.properties
```

Then in the example above, `base.properties` becomes the later import, so `demo.name=base` and `demo.region=global`. Changing the list order is a **behavior change**, even if the contents of each individual file stay the same.

In deployments, express intent clearly through naming and ordering:

```properties
spring.config.import=classpath:/config/defaults.properties,classpath:/config/team-overrides.properties
```

Putting defaults first and intentional adjustments afterward is easier to read than an arbitrarily ordered list.

### 4.3. Do not repeat the `spring.config.import` key in the same document

Avoid writing:

```properties
spring.config.import=classpath:/config/base.properties
spring.config.import=classpath:/config/override.properties
```

Within a single `.properties` document, two lines with the same property name can be handled by the parser under key-override rules, preventing an import list from being expressed as intended. Use **one declaration** containing a list of locations, rather than expecting two lines with the same key to accumulate:

```properties
spring.config.import=classpath:/config/base.properties,classpath:/config/override.properties
```

If a file has multiple **logical documents** (such as YAML separated by `---`), each document can have its own import declaration; in that case you also need to inspect activation conditions and document order.

## 5. Nested imports: an imported file can import further

### 5.1. Three-level chain example

Spring Boot does not restrict `spring.config.import` to `application.properties` alone. An imported file can continue declaring this property:

```text
src/main/resources/
├── application.properties
└── config/
    ├── core.properties
    └── nested/
        └── limits.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/core.properties

demo.mode=app
demo.limit=2
```

`config/core.properties`:

```properties
spring.config.import=classpath:/config/nested/limits.properties

demo.mode=core
demo.limit=4
```

`config/nested/limits.properties`:

```properties
demo.mode=limits
demo.limit=12
demo.audit.enabled=true
```

The dependency path is:

```text
application.properties
        |
        | spring.config.import
        v
config/core.properties
        |
        | spring.config.import
        v
config/nested/limits.properties
```

In this **linear chain**:

- `core.properties` is imported by `application.properties`, so it can override `demo.mode=app`.
- `limits.properties` is imported by `core.properties`, so it can override `demo.mode=core`.
- The final value of `demo.mode` is `limits`, `demo.limit` is `12`, and `demo.audit.enabled` is `true`.

A deeply nested import document does not mean it always beats every other source across the whole application. When additional import branches, multiple profiles, and configuration locations exist, inspect **the actual order in which documents are processed by Spring Boot**, rather than merely counting file depth.

### 5.2. Distinguish nesting diagrams from function-call reads

An `A -> B -> C` diagram helps understand import relationships, yet these documents do not behave like Java functions calling one another each time a property is queried. Spring Boot processes config data at startup, builds value sources, and exposes them to `Environment`. Beans read final values based on the established precedence.

Therefore, if a bean calls `environment.getProperty("demo.mode")` twice, that is **not** opening `application.properties` twice or re-executing the import chain. It is simply looking up a property in the existing environment.

## 6. Where are relative import paths resolved from?

This is a part where mistakes happen very easily with nested imports.

Spring Boot 3.3 distinguishes between a **fixed location** and an **import-relative location**.

- A location starting with `/` or having a location prefix such as `classpath:` or `file:` is **fixed**; the address's meaning does not change with the declaring file.
- A location without a leading `/` and without such a location prefix is **import-relative to the declaring file**.
- The `optional:` prefix does **not** decide whether a location is fixed or relative; evaluate the address portion after `optional:`.

### 6.1. Nested relative location example

Suppose there are external files outside the application in the working directory `/demo`:

```text
/demo/
├── application.jar
├── application.properties
└── core/
    ├── core.properties
    └── extra/
        └── extra.properties
```

`/demo/application.properties`:

```properties
spring.config.import=optional:core/core.properties
demo.source=application
```

`/demo/core/core.properties`:

```properties
spring.config.import=optional:extra/extra.properties
demo.source=core
```

`/demo/core/extra/extra.properties`:

```properties
demo.source=extra
```

The path `core/core.properties` is resolved relative to the location of **`application.properties`**. When `core.properties` imports `extra/extra.properties`, the address is resolved relative to **`core.properties`**, i.e., `/demo/core/extra/extra.properties`.

```text
/demo/application.properties
   + "core/core.properties"
   = /demo/core/core.properties

/demo/core/core.properties
   + "extra/extra.properties"
   = /demo/core/extra/extra.properties
```

Do not automatically combine every import path with the process's working directory or with the directory containing the JAR. **Whichever file declares an import, import-relative paths are resolved against that file.**

### 6.2. Fixed location example

The following examples use addresses with explicit semantics:

```properties
spring.config.import=classpath:/config/global.properties
```

```properties
spring.config.import=file:./config/runtime.properties
```

`classpath:/...` denotes a resource on the classpath; `file:./...` denotes a file path under file-system and working-directory semantics. Because it has the `file:` prefix, this address belongs to the **fixed location** group under the import mechanism's classification; it is not automatically combined relative to the directory of the file declaring the import.

A common mistake is moving the line:

```properties
spring.config.import=extra.properties
```

from `application.properties` into `core/core.properties` without reviewing the path. Once moved, `extra.properties` is searched relative to `core/core.properties` and may point to a different file or fail to exist.

### 6.3. A multi-path list can mix both styles

Example:

```properties
spring.config.import=defaults.properties,optional:file:./deployment/override.properties,classpath:/shared/common.yaml
```

Each entry must be resolved according to **the rules of that specific location**. Do not assume the entire list resolves from a single directory. If packaging and deployment vary across environments, use explicit paths to reduce confusion.

## 7. Important rule: the same resource is imported only once

Spring Boot 3.3 documentation states clearly that an import is loaded only **once**, regardless of how many times it is declared.

Suppose:

```text
application.properties
  |
  +---> defaults.properties
  |
  +---> ui.properties
           |
           +---> defaults.properties
```

`defaults.properties` is referenced directly from `application.properties` and indirectly from `ui.properties`. Spring Boot does not create a duplicate copy of the same document just because another import path points to it.

### 7.1. Duplicate declaration in a list example

`application.properties`:

```properties
spring.config.import=classpath:/config/defaults.properties,classpath:/config/labels.properties,classpath:/config/defaults.properties
```

In terms of **resource load count**, `defaults.properties` is loaded only once. Do not infer that declaring `defaults.properties` at the end of the list is a fresh load pass that can be used to force precedence.

Better way to write it:

```properties
spring.config.import=classpath:/config/defaults.properties,classpath:/config/labels.properties
```

There are still only two independent import sources, yet the intent and maintainability are much clearer.

### 7.2. Repeated import does not mean repeated override

Distinguish these concepts:

| Concept | Meaning |
| --- | --- |
| Import appears twice | The same location is declared in multiple places or repeated in a list |
| Resource loaded twice | Reading and inserting the same resource into config data twice |
| Value overridden | Another source with higher precedence sets the same key |
| Value looked up multiple times | A bean calls `Environment` multiple times after startup |

**Repeated import declarations do not produce multiple resource loads.** However, **different** configuration files can certainly declare the same key and override each other according to precedence.

For example, if `defaults.properties` and `labels.properties` both define `app.label`, the result can be determined by precedence between two **different documents**. That is not `defaults.properties` being loaded twice.

### 7.3. Can repeated imports resolve circular dependencies?

Do not design circular configurations:

```text
a.properties -> b.properties -> a.properties
```

The load-once rule helps prevent the misunderstanding that each re-encounter creates another copy. Still, **circular import dependencies are hard-to-maintain designs**: readers struggle to tell which file is the default source and which has override authority. Move shared values into a file that does not import back, or organize import chains in one direction.

Nor should you rely on different path spellings to intentionally reload the same resource. Prefer uniform addresses, avoiding mixing relative and absolute paths that point to the same place in the configuration graph.

### 7.4. "Only once" does not mean profile-specific files are the same file

`common.properties` and `common-dev.properties` are **two different resources**. If the `dev` profile is active and Spring Boot evaluates profile-specific variants of the import location, both files participating does not violate the rule that each resource is loaded once.

Similarly, `defaults.properties` and `defaults.yaml` are two different physical resources, even though they might contain overlapping logical keys. Do not use the load-once rule to conclude that all documents with similar content or the same name prefix will be skipped.

## 8. Coordinating multiple imports and nested imports

A system can have layers:

```text
application.properties
  |
  +---> config/base.properties
  |         |
  |         +---> config/region.properties
  |
  +---> config/tenant.properties
            |
            +---> config/feature.properties
```

If `base.properties` and `tenant.properties` both define a key, remember **the location order within the direct import**. If a child file is imported by another file, remember that the imported document can override the document declaring it. When multiple branches participate, the diagram helps identify sources, while the final value is decided by the order of documents during config data loading.

To reduce complexity, apply these conventions:

1. Keep the root file as the single entry point of the import graph.
2. Give each configuration group a clear owning location.
3. Place default files before override files in intentional lists.
4. Avoid declaring a key across too many branches.
5. Files holding shared values should avoid importing back up to higher-layer files.
6. Avoid bringing the same resource into multiple branches unless necessary.
7. When encountering an unexpected value, identify the document providing the effective value rather than guessing from directory structure alone.

The more complex an import graph becomes, the more it needs notes describing each file's purpose and examples of actual configuration after startup.

## 9. Interaction with profiles

An import location can expand to **profile-specific variants** when applicable. Suppose:

```text
src/main/resources/
├── application.properties
└── config/
    ├── payment.properties
    └── payment-dev.properties
```

`application.properties`:

```properties
spring.config.import=classpath:/config/payment.properties
```

`config/payment.properties`:

```properties
app.payment.endpoint=https://payments.example.test
app.payment.timeout=5s
```

`config/payment-dev.properties`:

```properties
app.payment.endpoint=http://localhost:9090
```

When the `dev` profile is active, Spring Boot can load **both the ordinary imported file and the profile-specific variant**; the `app.payment.endpoint` value for `dev` can come from `payment-dev.properties`, while `app.payment.timeout` comes from `payment.properties`.

```bash
java -jar app.jar --spring.profiles.active=dev
```

Keep in mind:

- An import location does not necessarily correspond to just a single final file in every case; Spring Boot also considers profile-specific files when appropriate.
- A loaded profile variant will not be loaded again simply because it appears along another import route.
- With multiple active profiles, consider the precedence order of the profiles and related configuration location groups.
- If a higher-precedence source such as a command-line argument or environment variable also sets `app.payment.endpoint`, that source can still beat the value from the profile file.

Do **not** use `spring.profiles.active` indiscriminately inside a document that is already profile-activated. Spring Boot imposes its own restrictions on profile activation properties inside profile-specific documents; configure profile activation from an appropriate source.

## 10. Mandatory and optional files

### 10.1. By default, a missing import location can prevent startup

Example:

```properties
spring.config.import=file:./deployment/required.properties
```

If this mandatory location does not exist, Spring Boot may throw `ConfigDataLocationNotFoundException` and fail to start the application.

This behavior fits configuration that the application **cannot function properly without**, such as required connection details supplied by the deployment environment.

### 10.2. `optional:` only allows skipping a missing location

If additional configuration is optional:

```properties
spring.config.import=optional:file:./deployment/local.properties
```

When the file does not exist, the application can continue starting. If the file exists, values inside it are still loaded according to precedence rules.

You can combine mandatory and optional files in one list:

```properties
spring.config.import=classpath:/config/base.properties,optional:file:./deployment/local.properties
```

In the example above, `base.properties` must exist at the declared address, whereas `local.properties` may be absent.

**Note:** `optional:` does not turn every error into a valid state. It serves the **location not found** case; if a file exists yet has invalid YAML syntax, wrong value types, or another part of the application fails to initialize, `optional:` is not a mechanism that auto-heals those errors.

### 10.3. When should you not use `optional:`?

Do not put `optional:` on every file just to make the application start easily. If external configuration is a mandatory requirement for the system to run safely, silently missing the file can make the application fall back to unsuitable defaults.

Choose optionality based on intent:

| Configuration type | Can it be optional? | Reason |
| --- | --- | --- |
| Local developer machine adjustments | Usually yes | When missing, shared defaults are used |
| Override file present only in certain environments | Yes | Other environments do not need this file |
| Mandatory file to access an essential service | Usually no | Absence must be detected early |
| File containing safety-critical configuration flags | Needs explicit decision | Should not silently fall back to uncontrolled values |

## 11. Full practical example

Let's create a Spring Boot 3.3.x application using Java 17 and the `spring-boot-starter` dependency. The following example uses an `ApplicationRunner` to print non-sensitive keys at startup.

### 11.1. File structure

```text
src/main/
├── java/
│   └── example/importlab/
│       └── ImportLabApplication.java
└── resources/
    ├── application.properties
    ├── base/
    │   ├── defaults.properties
    │   └── nested/
    │       └── channels.properties
    └── overrides/
        └── local.properties
```

### 11.2. Root file imports two files in order

`src/main/resources/application.properties`:

```properties
spring.application.name=config-import-lab
spring.config.import=base/defaults.properties,overrides/local.properties

demo.name=from-application
demo.channel=from-application
demo.limit=1
```

Here both paths are **import-relative**, resolved relative to `application.properties`. If you want independence from where the root file is located, you can also use `classpath:/base/defaults.properties` and `classpath:/overrides/local.properties`.

### 11.3. The first imported file imports a child file

`src/main/resources/base/defaults.properties`:

```properties
spring.config.import=nested/channels.properties

demo.name=from-defaults
demo.channel=from-defaults
demo.limit=3
demo.description=default-layer
```

From the location of `base/defaults.properties`, the path `nested/channels.properties` points to `base/nested/channels.properties`.

`src/main/resources/base/nested/channels.properties`:

```properties
demo.channel=from-nested
demo.limit=7
```

### 11.4. The later import overrides several keys

`src/main/resources/overrides/local.properties`:

```properties
demo.name=from-local
demo.limit=10
```

Because `local.properties` is the later import in the list in `application.properties`, values like `demo.name` and `demo.limit` from this file can override the corresponding values from the earlier import branch.

Meanwhile, `demo.description` exists only in `defaults.properties`, and `demo.channel` is contributed by the nested import document `channels.properties` and is not declared in `local.properties`.

### 11.5. Write Java application to print effective values

`src/main/java/example/importlab/ImportLabApplication.java`:

```java
package example.importlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ImportLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ImportLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfiguration(Environment env) {
        return args -> {
            print(env, "demo.name");
            print(env, "demo.channel");
            print(env, "demo.limit");
            print(env, "demo.description");
        };
    }

    private static void print(Environment env, String key) {
        System.out.printf("%s=%s%n", key, env.getProperty(key));
    }
}
```

Spring automatically injects `Environment` into the `showConfiguration` bean method. The snippet only reads illustrative keys; it accesses no secrets.

### 11.6. Launch and observe

If the project uses the Maven wrapper:

```bash
./mvnw spring-boot:run
```

Or package and run with the actual JAR path:

```bash
java -jar target/config-import-lab-0.0.1-SNAPSHOT.jar
```

With the structure and files declared above, the expected output of the lines printed by `ApplicationRunner` is:

```text
demo.name=from-local
demo.channel=from-nested
demo.limit=10
demo.description=default-layer
```

Here is the interpretation:

- `demo.name`: `local.properties` beats earlier declarations.
- `demo.channel`: `channels.properties` is imported from `defaults.properties` and overrides `from-defaults`, while `local.properties` does not override this key.
- `demo.limit`: present at multiple levels, but the later import `local.properties` sets the value `10`.
- `demo.description`: present only in `defaults.properties`.

These values are **predictions for the illustrative configuration**, provided no arguments, environment variables, or other additional sources override them. To observe the packaged JAR, repackage after changing files in `src/main/resources`.

### 11.7. Test the impact of list order

In `application.properties`, change to:

```properties
spring.config.import=overrides/local.properties,base/defaults.properties
```

Keep the remaining files unchanged and restart. You will see that keys present in both branches can change depending on the import order. This experiment demonstrates that **list order matters**, whereas the position of the `spring.config.import` line relative to other lines in the same document does **not** decide that order.

### 11.8. Test an optional import

Restore the list to its original order and change the second import to:

```properties
spring.config.import=base/defaults.properties,optional:file:./deployment/local.properties
```

If the `deployment` directory lacks `local.properties`, the application can still run using values from the `defaults` branch. If you create the file at the process's working location, Spring Boot will load the new values from that external file. This is also a way to observe the difference between sources on the classpath and file sources on the operating system.

## 12. Describing the same layout with YAML

Imported files do not all have to use the same format. For example, the root file can be YAML while one of the imported files remains `.properties`.

`application.yaml`:

```yaml
spring:
  application:
    name: config-import-lab
  config:
    import: "classpath:/base/defaults.properties,optional:file:./deployment/overrides.yaml"

demo:
  name: from-application
```

`deployment/overrides.yaml` (if present):

```yaml
demo:
  name: from-external-yaml
  limit: 20
```

When Spring Boot loads YAML, hierarchical keys are flattened into property form for lookup. The `spring.config.import` mechanism still applies to the declared locations; using YAML does not alter the core principles.

However, when `.properties` and YAML files coexist in default configuration locations, they are also subject to format and location precedence rules. **You cannot deduce the application's final value from import order alone** if other `PropertySource` entries exist.

## 13. Diagnosing when values differ from expectations

When a running application behaves differently from the configuration you just edited, trace along this flow:

```text
Identify the incorrect key
         |
         v
List documents declaring the key
         |
         v
Find spring.config.import in each document
         |
         v
Resolve relative / fixed paths
         |
         v
Identify imported documents and nested branches
         |
         v
Check duplicate imports, profiles, and other higher-precedence sources
         |
         v
Inspect values in Environment
         |
         v
Fix file / path / order / intended override source
```

### 13.1. Observing the config data loading process

In development environments, you can temporarily enable verbose logging for the configuration loader:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

This helps observe how configuration sources are located and loaded. After finding the cause, turn off verbose logging or return it to an appropriate level; avoid publishing logs containing internal paths or secret values.

### 13.2. Checking the final value in `Environment`

In the `ApplicationRunner` from the practice section, add the key you want to observe:

```java
System.out.println(env.getProperty("demo.name"));
```

This shows **the effective value** after processing configuration sources. It does not by itself give full details of which location supplied that value. When you need to trace provenance, carefully combine configuration loading logs with inspecting the `PropertySource` entries of `ConfigurableEnvironment`.

### 13.3. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Application reports file not found | Mandatory import points to wrong place or file wasn't packaged | Verify actual location and path resolution |
| A key does not pick up a new value | Higher-precedence source overrides it | Check later imports, profiles, external files outside JAR, env vars, and CLI args |
| Moving a file breaks child imports | Import-relative changed its anchor directory | Fix relative paths or use an appropriate fixed location |
| Repeated import declaration shows no change | Spring Boot loads a resource only once | Remove duplicate import; place overrides in a separate file |
| Added `optional:` yet application still fails | File has syntax errors or error is unrelated to missing location | Check exception type and fix the actual configuration |
| Running JAR does not see newly added file | New file is not inside the running JAR | Rebuild or supply external file outside JAR at the right location |
| `dev` profile has values different from default | Profile-specific variant was loaded | Check `-dev` files along with higher-precedence sources |

## 14. Designing maintainable import graphs

As the number of files grows, a sensible structure usually matters more than how many levels you can import. A convention you can adopt:

```text
application.properties
    |
    +--> config/common.properties
    |
    +--> config/module-a.properties
    |
    +--> config/module-b.properties
    |
    +--> config/overrides.properties
```

In this structure, `common.properties` holds shared values, module files own feature-specific configuration, and `overrides.properties` overrides only the keys allowed to be tuned. If a module needs an auxiliary document, import it inside that module using a clear path.

Maintenance principles:

- **Keep a clear entry point.** Readers should know where to start following the import graph.
- **Do not repeat a key across files unintentionally.** Intentional collisions should be explainable by precedence.
- **Avoid overly deep nested imports.** A long chain makes it harder to read why a value won.
- **Use consistent addresses.** Avoid referencing the same resource with multiple path forms.
- **Do not make `optional:` the default for every source.** Classify mandatory and optional files based on operational needs.
- **Let profile-specific files hold environment differences.** Do not copy every shared key indiscriminately.
- **Never put real secrets in source control.** Adding import layers does not by itself provide secret protection.
- **Treat changing import order as a behavior change.** Identify which keys are affected before releasing.

## 15. Self-check exercises

### Exercise 1 — order of multiple imports

`application.properties`:

```properties
spring.config.import=a.properties,b.properties
sample.value=app
```

`a.properties`:

```properties
sample.value=A
sample.only-a=present
```

`b.properties`:

```properties
sample.value=B
```

**Question:** What are `sample.value` and `sample.only-a`?

**Answer:** `B` and `present`. The later import overrides colliding keys, while keys present only in `a.properties` are still used.

### Exercise 2 — nested imports

`application.properties` imports `a.properties`. `a.properties` imports `b.properties`. All three set `sample.level`, to `app`, `A`, and `B` respectively.

**Question:** In this linear chain, what is the final value?

**Answer:** `B`, because `b.properties` is imported by `a.properties`, which was imported by `application.properties`.

### Exercise 3 — relative location

`/workspace/config/root.properties` contains:

```properties
spring.config.import=sub/child.properties
```

`/workspace/config/sub/child.properties` contains:

```properties
spring.config.import=extra/more.properties
```

**Question:** Where does the second path resolve?

**Answer:** `/workspace/config/sub/extra/more.properties`, because it is relative to `child.properties`.

### Exercise 4 — duplicate import declaration

`application.properties` directly imports `shared.properties`; `feature.properties` also imports the exact same `shared.properties` resource.

**Question:** How many times does Spring Boot load `shared.properties`, and how should it be organized?

**Answer:** Once for the same resource. Place the shared import location at one clear point and avoid duplicate declarations across branches unless needed.

### Exercise 5 — missing file

Two configurations:

```properties
spring.config.import=file:./missing.properties
```

```properties
spring.config.import=optional:file:./missing.properties
```

**Question:** Where do they differ?

**Answer:** With a mandatory location not found, the application may halt startup due to a missing config data exception. `optional:` allows skipping a missing location. Both cases still require valid configuration for needed properties elsewhere.

### Exercise 6 — distinguishing load-once from precedence

`a.properties` and `b.properties` both define `demo.mode`. `a.properties` is imported twice, `b.properties` once. Can you conclude `a.properties` wins because it was referenced twice?

**Answer:** No. The number of times the same import is declared does not give that resource extra load passes. The effective value depends on **the precedence order of the distinct documents** and the remaining configuration sources.

## 16. Key takeaways before moving on

Five core rules of `spring.config.import` in Spring Boot 3.3:

1. **Imports add configuration documents**, and values in an imported document can override values in the document that declared it.
2. **An import list is processed in declaration order; an import listed later has higher precedence than one listed earlier** for colliding keys in the corresponding scenario.
3. **An imported file can declare new imports**, creating nested chains or import graphs.
4. **Import-relative paths resolve relative to the declaring document**, whereas prefixed addresses such as `classpath:` or `file:` are handled under fixed-location semantics.
5. **Each imported resource is loaded only once even if referenced multiple times.** Repeating declarations does not create additional override rounds.

Finally, the value an application uses remains the result of **the entire configuration system**, including profiles, external sources, environment variables, JVM properties, and startup arguments. When unsure which file wins, sketch the import graph, check each document's location, and observe actual values via `Environment`.

### References

- Spring Boot 3.3 Reference — Externalized Configuration, *Importing Additional Data*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#importing-additional-data
- Spring Boot 3.3 Reference — *Using Fixed and Import Relative Locations*, *Property Ordering*, *Profile Specific Files*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
