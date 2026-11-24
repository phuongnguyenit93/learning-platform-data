# Lists Are Replaced When Defined in a Higher-Priority Source in Spring Boot

## 1. The Problem to Understand

In Spring Boot, configuration can reside across multiple `PropertySource` instances and Config Data documents such as `application.yml`, `application-prod.yml`, external files outside the JAR, Java system properties, environment variables, or command-line arguments.

For single scalar values such as `app.timeout=5s`, the behavior is usually straightforward: if a higher-priority source defines the same property name, its value wins. However, when the configuration is a **list (`List`)**, many people expect Spring Boot to merge elements from different sources, or update individual fields of individual elements. That is **not Spring Boot's List binding rule**.

Core rule:

> **When the same list is declared in multiple configuration sources with different priority levels, the `@ConfigurationProperties` binder uses the list from the highest-priority source that supplies that list. Lists from lower-priority sources are not merged into the bound list.**

This means:

- Higher-priority source has one element, lower-priority source has three elements: the effective list may end up with only **one element**.
- Higher-priority source only declares `app.backends[0].url`, while lower-priority source declares both `name` and `timeout` for element 0: during List binding, the missing fields of element 0 are not automatically taken from the lower source.
- Higher-priority source does not declare the list: the list from the lower-priority source can continue to be used.
- **`Map`** configuration behaves differently: multiple keys from different sources can be combined, and values for duplicate keys are resolved by priority.

This lesson focuses on the **collection binding mechanism** via `@ConfigurationProperties`, not on concatenating two `List` instances in Java after the application has started.

## 2. Placing a List in a Spring Boot Configuration

Suppose a service needs a list of backends to send requests to:

~~~yaml
# src/main/resources/application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

The two YAML items above form a list:

| Index | `name` | `url` | `timeout` |
| --- | --- | --- | --- |
| `0` | `primary` | `https://primary.example.test` | `2s` |
| `1` | `backup` | `https://backup.example.test` | `4s` |

Following Spring Boot's property representation convention, you can visualize the leaf properties as:

~~~properties
app.backends[0].name=primary
app.backends[0].url=https://primary.example.test
app.backends[0].timeout=2s

app.backends[1].name=backup
app.backends[1].url=https://backup.example.test
app.backends[1].timeout=4s
~~~

This is **a list of two objects**, not a map with business keys `0` and `1`. The indices `[0]` and `[1]` exist for collection binding.

If only the file above declares `app.backends` in the entire environment, Spring Boot can bind both elements into `List<Backend>`.

## 3. A Shared Java Model Used Across Examples

In Spring Boot 3.x and Java 17+, you can use a record:

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Backend> backends,
        Map<String, String> labels) {

    public record Backend(
            String name,
            String url,
            Duration timeout) {
    }
}
~~~

Register the configuration type:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Place `AppProperties` in a scanned subpackage, or use `@EnableConfigurationProperties(AppProperties.class)` to register it explicitly.

Bean receiving the configuration:

~~~java
package com.example.service;

import com.example.config.AppProperties;
import org.springframework.stereotype.Service;

@Service
public class BackendRouter {
    private final AppProperties properties;

    public BackendRouter(AppProperties properties) {
        this.properties = properties;
    }

    public void printBackends() {
        if (properties.backends() == null) {
            System.out.println("No backend list configured");
            return;
        }

        properties.backends().forEach(backend ->
            System.out.println(backend.name() + " -> " + backend.url()));
    }
}
~~~

For a record, the accessors are `backends()`, `name()`, and `url()`, rather than JavaBean getters like `getBackends()` or `getName()`.

The exact same List replacement rule applies when the model is written as a JavaBean with setters or as an immutable class with constructor binding. **The Java construct used to hold the list does not change the precedence rules between config data sources.**

## 4. Core Example: `application-prod.yml` Replaces the Entire List

Keep `application.yml` from section 2, containing two backends `primary` and `backup`.

Add the file:

~~~yaml
# src/main/resources/application-prod.yml
app:
  backends:
    - name: primary-prod
      url: https://api.example.test
      timeout: 6s
~~~

Run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

When `prod` is active, `application-prod.yml` participates in the Config Data mechanism. In an example with no higher-priority source, the bound list is:

~~~text
backends.size() = 1

backends[0].name    = primary-prod
backends[0].url     = https://api.example.test
backends[0].timeout = PT6S
~~~

**No** `backends[1]` element from `application.yml` is automatically preserved. `backup` disappears from the List binding result, even though it still exists in the default file.

Compare the two states:

| State | Element 0 | Element 1 | Element count |
| --- | --- | --- | --- |
| Without `prod` active | `primary` | `backup` | `2` |
| With `prod` active | `primary-prod` | None | `1` |

This is a **replacement** mechanism—not appending to the list, and not updating element 0 alone while keeping element 1.

If production needs both a primary and a backup backend, you must declare **both elements** in the list at the higher-priority effective source:

~~~yaml
# application-prod.yml
app:
  backends:
    - name: primary-prod
      url: https://api.example.test
      timeout: 6s
    - name: backup-prod
      url: https://backup-api.example.test
      timeout: 8s
~~~

Now the list has two elements because **the production file declared two elements**, not because Spring Boot merged elements from the default file.

## 5. The Most Confusing Case: Higher Source Overrides Only One Field

Suppose the default file is:

~~~yaml
# application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

Meanwhile, the profile file only has:

~~~yaml
# application-prod.yml
app:
  backends:
    - url: https://api.example.test
~~~

Beginners often predict:

~~~text
backends[0]:
    name    = primary                 (taken from default file)
    url     = https://api.example.test
    timeout = 2s                      (taken from default file)

backends[1]:
    name    = backup                  (preserved)
    url     = https://backup.example.test
    timeout = 4s
~~~

**That prediction is wrong for multi-source List binding in Spring Boot.** The `backends` data from the higher-priority source is used to bind the list, so the result is essentially:

~~~text
backends.size() = 1

backends[0].name    = null
backends[0].url     = https://api.example.test
backends[0].timeout = null
~~~

In this example, the `Backend` record uses reference types `String` and `Duration`, so fields not supplied can be `null`. For primitive fields such as `int`, missing data may result in the primitive type's default value depending on the binding style; however, **that value is never inherited from the list element in the lower-priority source**.

This causes very noticeable real-world bugs:

- A backend gets a new URL but lacks a display name.
- Missing timeout causes a `NullPointerException` in consuming code.
- The backup backend is dropped from the list without the deployer realizing it.
- A required field is missing, causing validation to fail on startup.

**Practical rule:** when overriding a `List` of objects, redeclare the entire list and all required fields of each element in the higher-priority source.

## 6. What If the Higher Source Does Not Define the List?

Replacement only occurs when a higher-priority source **contributes configuration for that list itself**. It does not mean every profile file wipes out all lists from the common file.

For example:

~~~yaml
# application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
  display-name: Demo Service
~~~

Production file:

~~~yaml
# application-prod.yml
app:
  display-name: Production Service
~~~

The production file **does not declare** `app.backends`. Therefore, the default list in `application.yml` can still be bound with two elements. `app.display-name` is overridden independently.

Distinguish three scenarios:

| Configuration in higher source | Practical meaning |
| --- | --- |
| `app.backends` is not declared at all | The list from the lower source can still be used |
| One or more elements of `app.backends` are declared | The list from the higher source replaces the lower source's list |
| `app.backends: []` is explicitly declared as an empty YAML list | Intentionally declares an empty list; verify the binding/format behavior in your application if you want to "clear everything" |

When you want to completely disable a feature, an explicit boolean key such as `app.routing.enabled=false` is often clearer and more reliable than relying on how an empty list is represented across different configuration sources.

## 7. Important Comparison: `Map` Combines Keys

Unlike `List`, Spring Boot's `Map` binding rules allow keys to be combined from multiple sources. Consider the default YAML:

~~~yaml
# application.yml
app:
  labels:
    owner: platform
    region: global
    tier: standard
~~~

Profile file:

~~~yaml
# application-prod.yml
app:
  labels:
    region: apac
    environment: production
~~~

When `prod` is active and there is no higher-priority source, `Map<String, String> labels` can receive:

~~~text
owner       = platform     (from default file)
region      = apac         (prod file overrides duplicate key)
tier        = standard     (from default file)
environment = production   (key only present in prod file)
~~~

Comparison table:

| Characteristic | `List` | `Map` |
| --- | --- | --- |
| Element identification | Position/index `[0]`, `[1]` | Meaningful keys such as `owner`, `region` |
| Same config in two sources | Higher-priority source replaces **the entire list** | Keys can be **combined** |
| When an element/key is absent in higher source | Lower-source list element is not automatically merged in | Map key present only in lower source can remain |
| When a key overlaps in two sources | No per-element merge by index | Value for the key in the higher source takes precedence |
| Suitable for | Ordered lists where each override supplies a complete list | Configurations identified by stable keys |

Do not assume `Map` always deep-merges **every** complex data type in every situation. The outcome also depends on how data is represented, value types, binder rules, and supplying sources. For a map of simple values as in this example, key combination is the most intuitive behavior.

## 8. List of Objects vs. Map of Objects: A Deeper Comparison

Consider configuring services that share `url` and `timeout` properties.

### 8.1. When Represented as a List

~~~yaml
# application.yml
app:
  services:
    - name: catalog
      url: https://catalog.example.test
      timeout: 3s
    - name: inventory
      url: https://inventory.example.test
      timeout: 5s
~~~

Override only the catalog part:

~~~yaml
# application-prod.yml
app:
  services:
    - name: catalog
      url: https://catalog.example.com
~~~

With List binding, the result leaves only one item `catalog`, its `timeout` is not automatically taken from the default file, and the `inventory` item is not kept.

### 8.2. When Represented as a Map with Stable Keys

Change the YAML to:

~~~yaml
# application.yml
app:
  services:
    catalog:
      url: https://catalog.example.test
      timeout: 3s
    inventory:
      url: https://inventory.example.test
      timeout: 5s
~~~

Prod file:

~~~yaml
# application-prod.yml
app:
  services:
    catalog:
      url: https://catalog.example.com
~~~

Java model:

~~~java
@ConfigurationProperties(prefix = "app")
public record ServiceMapProperties(
        Map<String, Service> services) {

    public record Service(String url, Duration timeout) {
    }
}
~~~

With map binding, the properties of `catalog` and the `inventory` key can be combined as follows:

~~~text
services["catalog"].url      = https://catalog.example.com
services["catalog"].timeout  = PT3S
services["inventory"].url    = https://inventory.example.test
services["inventory"].timeout= PT5S
~~~

In a `Map`, `catalog` and `inventory` are **meaningful identifiers**, not numeric indices. Thus, the Map form fits well when the frequent requirement is "change the URL of one service while keeping the other services' configuration".

Criteria for choosing:

- If you need **explicit ordering** (try backends in order 0, 1, 2), a list can be appropriate.
- If you need to override **individual entries by name** from multiple sources, a Map is usually easier to manage.
- If you still need ordering in a Map, define an explicit ordering rule (for example, a `priority` property on each service) rather than assuming YAML order is always preserved across all sources.

## 9. Complete Example with Both List and Map in One Application

Use the model shown in section 3:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Backend> backends,
        Map<String, String> labels) {
    public record Backend(
            String name,
            String url,
            Duration timeout) {
    }
}
~~~

Default file:

~~~yaml
# application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
  labels:
    owner: platform
    environment: default
~~~

Profile file:

~~~yaml
# application-prod.yml
app:
  backends:
    - name: production
      url: https://api.example.test
      timeout: 6s
  labels:
    environment: production
    region: apac
~~~

Enable `prod`:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Result according to binding rules:

| Property | Result |
| --- | --- |
| `backends` | Only **one item** `production` |
| `backends[0].url` | `https://api.example.test` |
| `backends[0].timeout` | `6s` |
| `labels.owner` | `platform` |
| `labels.environment` | `production` |
| `labels.region` | `apac` |

This clearly shows: **List replaces the whole list**, whereas **Map keeps additional keys from lower sources** and overrides matching keys by priority.

If you then add an even higher-priority source such as CLI:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.labels.region=eu
~~~

`labels.region` can become `eu`, while the `backends` list still comes from the profile file because the CLI does not declare the list.

Conversely, if the CLI has `--app.backends[0].url=...`, it can become the highest-priority list source and cause the effective list to reflect only what was provided from that CLI source.

## 10. Overriding a List via Command-Line Arguments

Suppose the packaged YAML is:

~~~yaml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

In a shell that supports passing string arguments, you can pass an indexed property:

~~~bash
java -jar app.jar '--app.backends[0].url=https://temporary.example.test'
~~~

Single quotes here ensure Unix shells pass the literal `[` and `]` characters; other shells have their own quoting rules. When `SpringApplication` still accepts command-line properties, this option can supply configuration for `app.backends` from a high-priority source.

When `@ConfigurationProperties` binds a List, do not expect it to only replace `url` of element 0 and keep `name`, `timeout`, and element 1 from YAML. It can cause the bound list from the higher source to have only element 0 with the new `url`, leaving other fields missing.

If you want to redefine **a complete list** via CLI, you must specify every required index and field, such as:

~~~bash
java -jar app.jar \
  '--app.backends[0].name=primary-temp' \
  '--app.backends[0].url=https://temporary.example.test' \
  '--app.backends[0].timeout=3s' \
  '--app.backends[1].name=backup-temp' \
  '--app.backends[1].url=https://backup-temporary.example.test' \
  '--app.backends[1].timeout=5s'
~~~

This approach is verbose and error-prone. For a List of objects with many fields, supplying **a complete environment-specific YAML config data file** is usually easier to control than passing individual indices on the command line.

Note: if code has called `setAddCommandLineProperties(false)`, `--app.backends[...]` options are not added to the `Environment` via the default command-line property source.

## 11. Overriding a List via Environment Variables

Environment variable names follow a different convention from property names in YAML. With Spring Boot's relaxed binding, when binding a List, **element indices are placed between underscores** in the environment variable name.

For example:

~~~text
Property name:        app.backends[0].name
Environment variable: APP_BACKENDS_0_NAME

Property name:        app.backends[1].url
Environment variable: APP_BACKENDS_1_URL
~~~

A deployment might pass:

~~~bash
APP_BACKENDS_0_URL=https://temporary.example.test java -jar app.jar
~~~

Assuming that environment variable is recognized and is the highest-priority source related to the list, be aware that **the entire List binding may take its data from the environment variable source** rather than automatically pulling remaining fields and items from YAML.

This point is especially important in Docker Compose and Kubernetes: even changing what looks like one small environment variable can make the list binding result differ from an expected per-field update.

To avoid incomplete configuration, you can:

- Supply all required environment variables for the entire List.
- Create an environment-specific config file containing the complete list.
- Switch the structure to a Map if you want to override objects by a stable key.
- Add validation to reject a list missing required fields.

Do not put passwords, tokens, or secrets in CLI examples or logs. For sensitive data, use an appropriate secret source and enforce read access controls.

## 12. Do Profiles Create a Different List Merge Behavior?

No. A profile only changes **which configuration documents are active and their precedence order**. When multiple documents supply the same List, the replacement rule still applies.

Suppose:

~~~yaml
# application.yml
app:
  backends:
    - name: default
      url: https://default.example.test
~~~

~~~yaml
# application-staging.yml
app:
  backends:
    - name: staging
      url: https://staging.example.test
~~~

~~~yaml
# application-prod.yml
app:
  backends:
    - name: prod
      url: https://prod.example.test
~~~

When running with the `staging` profile, the list contains the `staging` item. When running with the `prod` profile, the list contains the `prod` item. When running with multiple profiles, the corresponding files participate according to profile ordering, location group, and config data priority rules. **The List comes from the highest-priority matching document**, not a concatenation of all active profile files.

For example:

~~~bash
java -jar app.jar --spring.profiles.active=staging,prod
~~~

In this simple setup with no other overriding sources, a profile declared later can override matching keys from an earlier profile. Do not assume that having two profiles produces a list containing both the `staging` item and the `prod` item.

When using multiple external files, `spring.config.import`, or location groups via `spring.config.location`, you need to determine the exact document priorities. The List selection rule **does not change**, though figuring out "which source is highest" can be more complex.

## 13. Precedence Does Not Depend on Element Position

A list is represented by indices, but **indices do not determine priority across sources**.

Example YAML in a lower source:

~~~yaml
app:
  backends:
    - name: alpha
      url: https://alpha.example.test
    - name: beta
      url: https://beta.example.test
    - name: gamma
      url: https://gamma.example.test
~~~

Higher source:

~~~properties
app.backends[2].name=gamma-override
app.backends[2].url=https://gamma-new.example.test
~~~

Do not assume the binder will keep ``alpha`` and ``beta`` from the lower source and fill in element index `2` from the higher source. An index is only an element's address **within a single source**; multi-source List binding is not an index-by-index merge.

In addition, many collection binders expect indices to start at `0` and form a suitable range to build a list. Declaring only index `2` while omitting `0` and `1` in a high-priority source can lead to an unexpected list or binding failure depending on the scenario and data types. The safe approach is to declare a complete list, starting at index `0` with no gaps.

## 14. Declaring an Empty List: Avoid Confusing "Omitted" with "Clear All"

YAML configuration can express an empty list:

~~~yaml
app:
  backends: []
~~~

However, distinguish between:

~~~yaml
# Do not declare the app.backends property:
app:
  routing-enabled: false
~~~

and:

~~~yaml
# Explicitly declare app.backends as an empty list:
app:
  backends: []
~~~

They **do not carry the same intent**. The first case usually lets the binder pick up the list from a lower-priority source; the second expresses the intent that the list has no elements.

In practice, how an empty collection is represented can be affected by format, binder behavior, and flattening into property sources. If a business rule needs to reliably disable backend routing, use a dedicated property such as:

~~~yaml
app:
  routing-enabled: false
~~~

and have code skip the list when routing is disabled. That way the system does not rely solely on a YAML "empty list" trick in a higher-priority source.

Regardless of implementation, the application should validate state: if `routing-enabled=true`, there must be at least one valid backend.

## 15. Validation to Catch Unintended List Replacement

When a higher source only partially configures an object in a list, missing fields can cause the application to misbehave. A good practice is to fail fast on incomplete configuration.

In Spring Boot 3.x, use Jakarta Bean Validation:

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty @Valid List<Backend> backends) {

    public record Backend(
            @NotBlank String name,
            @NotBlank String url,
            @NotNull Duration timeout) {
    }
}
~~~

Register the record via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(AppProperties.class)`. Typically you need the `spring-boot-starter-validation` dependency to provide an appropriate Bean Validation implementation.

If the higher source only has:

~~~yaml
app:
  backends:
    - url: https://api.example.test
~~~

then `name` and `timeout` are not pulled from the lower-priority file to complete the item. The `@NotBlank` and `@NotNull` constraints can cause the application to fail during binding/validation, catching missing configuration right at startup.

Notes:

- `@NotEmpty` checks that the List is not empty; it does not check individual element fields.
- `@Valid` triggers validation on child elements as well.
- `@NotBlank` rejects null/blank strings.
- `@NotNull` rejects a missing timeout but does not guarantee a positive timeout; add a separate constraint if business rules require it.
- For the `url` field, `@NotBlank` does not verify a valid HTTPS URL. If HTTPS is required, use dedicated validation.
- If the list is allowed to be empty when a feature is turned off, do not always apply `@NotEmpty`; use an appropriate conditional check.

## 16. Diagnostics with `Environment` and Actuator

Distinguish **looking up a leaf property** from **binding an entire collection**.

For example, the lower source declares:

~~~properties
app.backends[0].name=primary
app.backends[0].url=https://primary.example.test
app.backends[0].timeout=2s
~~~

The higher source only declares:

~~~properties
app.backends[0].url=https://api.example.test
~~~

A single property lookup like:

~~~java
String name =
        environment.getProperty("app.backends[0].name");
~~~

can find `"primary"` in the lower source, because the property name **`app.backends[0].name`** is absent from the higher source.

However, a call that binds the entire list:

~~~java
List<Backend> backends =
        Binder.get(environment)
              .bind("app.backends", Bindable.listOf(Backend.class))
              .orElseGet(List::of);
~~~

applies **List binding rules**. Do not use the result of `Environment.getProperty("app.backends[0].name")` to infer that the binder will merge the `name` field from the lower source into the object in the higher-priority list.

To use the `Binder` snippet shown above, you need to import:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
~~~

And define `Backend` as a bindable Java type (such as the record in section 3, or an appropriate static nested record).

**Practical diagnostics:** if Spring Boot Actuator is present and its endpoints are enabled/secured, `/actuator/env` helps inspect raw values and property sources, while `/actuator/configprops` helps inspect bound objects. Distinguishing these two levels of observation is very useful when debugging list overrides.

These endpoints may expose internal URLs or secrets; grant access only to authorized users, apply redaction, and never leave them open publicly for debugging convenience.

## 17. Solutions When You Truly Want to Merge List Elements

### Solution A — Redeclare the Whole List in the Higher-Priority Source

This is the simplest solution when the element count is small or environment-specific lists are managed centrally.

~~~yaml
# application-prod.yml
app:
  backends:
    - name: primary
      url: https://primary-prod.example.test
      timeout: 5s
    - name: backup
      url: https://backup-prod.example.test
      timeout: 7s
~~~

Pros: clear outcome, easy to validate, no merge code needed. Cons: identical fields may have to be repeated across environments.

### Solution B — Model the Configuration as a Map

If elements are identified by a stable name:

~~~yaml
# application.yml
app:
  backends:
    primary:
      url: https://primary.example.test
      timeout: 2s
    backup:
      url: https://backup.example.test
      timeout: 4s
~~~

~~~yaml
# application-prod.yml
app:
  backends:
    primary:
      url: https://primary-prod.example.test
~~~

Use:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Map<String, Backend> backends) {

    public record Backend(String url, Duration timeout) {
    }
}
~~~

With Map binding, the `primary` key can take its URL from the profile and its timeout from the base file, while the `backup` key can remain intact.

If routing requires an order, add a dedicated property such as `order` or `priority` to each entry and sort in Java code after binding.

### Solution C — Two Lists Under Two Prefixes Merged in Business Code

Some systems need a clear distinction between a default list and an additional list:

~~~yaml
app:
  defaults:
    backends:
      - name: primary
        url: https://primary.example.test
        timeout: 2s

  extra:
    backends:
      - name: secondary
        url: https://secondary.example.test
        timeout: 4s
~~~

Bind the two collections to two separate property paths, then combine them with custom logic:

~~~java
List<Backend> combined = new ArrayList<>(defaults.backends());
combined.addAll(extra.backends());
~~~

This is an **application-defined merge**, not default Spring Boot Binder merging. You must decide rules for duplicate elements by name/id, ordering, conflicts, and validation. The snippet requires importing `java.util.ArrayList` and using the appropriate `Backend` type.

### Solution D — Prepare One Effective Config File Before Runtime

In a deployment pipeline, you can generate an environment-specific YAML file containing the complete list, rather than trying to override individual indices across scattered files.

Choose this approach when operations teams want to inspect **one clear final configuration set** without introducing merge logic into Java.

## 18. An Example of a Production Risk

Suppose the default has two standby servers:

~~~yaml
app:
  targets:
    - id: east
      address: https://east.example.test
      timeout: 2s
    - id: west
      address: https://west.example.test
      timeout: 2s
~~~

A production deployment only wants to change the address of `east`, so it adds:

~~~yaml
app:
  targets:
    - address: https://east-prod.example.test
~~~

With List binding, the outcome is not "keep `east` with a 2s timeout and keep `west`". The list can end up with only **one target** using the new `address`; `id` and `timeout` are not inherited from the lower-source list.

Potential consequences:

1. **Loss of redundancy:** target `west` is no longer in the effective list.
2. **Missing metadata:** the application does not know the `id` name of the remaining element.
3. **Unexpected timeout:** missing `Duration` causes errors or unexpected fallback behavior.
4. **Incident occurs only in production:** local runs have no overriding profile, so the list is complete locally.

How to prevent this:

- Validate at startup.
- Write unit tests with two property sources at different precedence levels.
- Log/summarize **non-sensitive metadata** about target count and identifiers, avoiding logging credentials.
- Document in deployment guidelines that overriding a List means **supplying a complete new list**.

## 19. Exercise: Predict List and Map After Activating a Profile

File `application.yml`:

~~~yaml
app:
  workers:
    - name: normal
      threads: 2
    - name: fallback
      threads: 1

  flags:
    audit: "true"
    region: global
~~~

File `application-prod.yml`:

~~~yaml
app:
  workers:
    - name: production
      threads: 8

  flags:
    region: apac
    metrics: "enabled"
~~~

Run:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

**Question 1:** How many elements does `workers` have?

**Answer:** One element `production` with `threads=8`. The `fallback` item from the default file is not kept because the list in the production file has higher priority.

**Question 2:** Which keys does `flags` have?

**Answer:** Three keys: `audit`, `region`, `metrics`. `audit=true` comes from the default file, `region=apac` is overridden, and `metrics=enabled` is added from the production file.

**Question 3:** If `application-prod.yml` only contains:

~~~yaml
app:
  workers:
    - name: production
~~~

will `threads` of element 0 automatically take `2` from the default file?

**Answer:** No. If the type of `threads` is `Integer`, the result can be `null`; if it is primitive `int`, the value can be the type default `0`. The key point is that **`2` is not automatically merged by index from the lower source**. Validation should catch missing or invalid values.

**Question 4:** What if the production file only overrides `flags.region` without declaring `workers`?

**Answer:** The `workers` list can continue to take its two elements from the default file, while the `flags` map updates the `region` key and preserves `audit`.

**Question 5:** If you want to change only `threads` for the worker named `normal` without losing `fallback`, how should you design it?

**Answer:** You can redeclare the entire list in the higher-priority file, or switch from a List to a Map with keys `normal` and `fallback` so key-associated values can be combined across multiple sources. If worker ordering is still needed, define ordering independently.

## 20. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "The prod profile only overrides `backends[0]`, so `backends[1]` from default still exists." | List binds from the higher-priority source; lower-source elements are not automatically merged. |
| "Lists merge by index like JavaScript objects." | No. Spring Boot's config binding differs from general-purpose object merging. |
| "If the higher source only declares `url`, `name` is still inherited from element 0 of the lower source." | Do not expect that; nested fields may be missing. |
| "All collections get completely replaced." | `Map` can combine keys from multiple sources. |
| "`@ConfigurationProperties` uses a record, so List merging differs from a JavaBean." | The configuration container type does not change List precedence rules. |
| "`Environment.getProperty` sees a leaf field from the lower source, which means List merges that field too." | Single-key lookup and collection binding are two operations with different rules. |
| "Simply adding another profile makes Spring Boot concatenate profile lists." | Profiles select which config data participates; they do not enable List concatenation. |
| "Overriding a single index via an environment variable is safe." | An environment variable can become the highest-priority list source, preventing other items/fields from being inherited. |
| "An empty List and an undeclared List are the same." | They differ in intent and representation; observe actual behavior if you intend to clear a list using empty config. |
| "No startup error means the list is complete." | Without validation, a truncated list or one with missing fields can still bind. |

## 21. Key Takeaways

- **`List`:** a higher-priority configuration source supplying a list **replaces the list** from a lower-priority source during `@ConfigurationProperties` binding; elements are not appended and fields are not merged by index.
- **`Map`:** can **combine keys** from multiple sources, with duplicate keys resolved by priority.
- **A source that omits the list:** does not automatically erase a list defined in a lower-priority source.
- **Overriding one List element:** can drop undeclared fields and other elements; rewrite the complete list or use a Map model keyed by stable identifiers.
- **Verify via the bound bean**, not solely by checking one key with `Environment.getProperty`. Consider `@Validated`, `@NotEmpty`, `@Valid`, and constraints on each required field.
- **Source precedence and binding rules are distinct:** which source wins is determined by property-source priority, whereas whether a List merges is determined by the binder for that collection type.

### References

- Spring Boot Reference — Externalized Configuration, Merging Complex Types: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Profiles: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot API — Binder: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html
