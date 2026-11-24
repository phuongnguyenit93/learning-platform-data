# How Maps Combine Keys from Multiple Configuration Sources

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Collections and Maps

## 1. The Problem: Multiple Sources Supplying the Same Map

In Spring Boot, an application can receive configuration from `application.yml`, `application-{profile}.yml`, files outside the JAR, environment variables, Java system properties, `SPRING_APPLICATION_JSON`, or command-line arguments. When configuration is a single scalar value like `server.port`, the rule is easy to see: the higher-priority source provides the final value.

With a `Map<K, V>` in `@ConfigurationProperties`, the situation is more interesting: two configuration sources can contain **different keys of the same map**, or **the same key with different values**. The Spring Boot Binder does not simply pick one whole map from one source and discard all entries from other sources.

Core rule:

> When binding a `Map`, Spring Boot can **combine entries coming from multiple property sources**. New entries in a higher-priority source are added; if **the same property** appears in multiple sources, the value from the higher-priority source is used.

This behavior is described in the **Merging Complex Types** section of the Spring Boot documentation. It **differs from Lists**, which are typically replaced wholesale by the list from the higher-priority source rather than concatenating or merging elements.

### Lesson Objectives

After this lesson, you will be able to:

- Bind `Map<String,String>` and `Map<String, SomeProperties>` from multiple sources.
- Determine the resulting map when a lower source declares keys A, B and a higher source declares B, C.
- Understand how an object nested **inside a Map entry** can receive fields from multiple sources.
- Distinguish Map combination from List replacement.
- Explain precedence across default files, profile-specific files, environment variables, system properties, JSON, and CLI.
- Preserve exact map keys when names contain `/`, dots, or special characters.
- Diagnose wrong keys, wrong types, configuration conflicts, and design reproducible tests.

## 2. General Mechanism: `Environment`, `PropertySource`, and `Binder`

There are three distinct layers:

1. **`PropertySource`**: each configuration source contributes named properties and values into `Environment`.
2. **Precedence order**: if the same property name appears in multiple places, Spring Boot resolves the effective value by precedence.
3. **`ConfigurationProperties Binder`**: collects properties matching a prefix and turns them into Java objects, including scalar fields, nested objects, collections, and Maps.

Diagram:

~~~text
application.yml             catalog.labels.owner = platform
application-dev.yml         catalog.labels.region = apac
OS environment              CATALOG_LABELS_TEAM = catalog
Command line                --catalog.labels.region=eu
          \                       |                       /
           \                      v                      /
            +---- Spring Environment / PropertySources ---+
                                |
                                v
                  @ConfigurationProperties Binder
                                |
                                v
                  Map<String, String> labels
                    owner  = platform
                    region = eu
                    team   = catalog
~~~

The diagram illustrates when the `dev` profile is active and no higher-priority source exists beyond those listed. `region` comes from the CLI and beats `application-dev.yml`; `owner` and `team` remain from their respective sources.

**Key point:** A Map in a bean is built from **sub-properties** under its prefix, not necessarily a single scalar property named `catalog.labels`.

## 3. Basic Example: `Map<String, String>` Combining Entries

### 3.1. Default Configuration

`src/main/resources/application.yml`:

~~~yaml
catalog:
  labels:
    owner: platform
    region: global
    version: v1
~~~

Suppose the bean is:

~~~java
package com.example.catalog.config;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        Map<String, String> labels
) {}
~~~

With only the default file present, `labels` contains:

~~~text
owner   = platform
region  = global
version = v1
~~~

### 3.2. Overriding One Entry and Adding Another Entry

`src/main/resources/application-dev.yml`:

~~~yaml
catalog:
  labels:
    region: apac
    stage: development
~~~

Start with:

~~~bash
java -jar catalog.jar --spring.profiles.active=dev
~~~

In standard Config Data setups, the profile-specific file has higher priority than the default file in the same location. Resulting Map:

| Key | `application.yml` | `application-dev.yml` | Result |
| --- | --- | --- | --- |
| `owner` | `platform` | undeclared | `platform` |
| `region` | `global` | `apac` | `apac` |
| `version` | `v1` | undeclared | `v1` |
| `stage` | undeclared | `development` | `development` |

Equivalent output:

~~~text
labels = {
  owner=platform,
  region=apac,
  version=v1,
  stage=development
}
~~~

The new map does not shrink to just `region` and `stage`. Keys `owner` and `version` continue to bind from the default file because the higher-priority source did not redeclare their specific properties.

### 3.3. Overriding Further via CLI

Run:

~~~bash
java -jar catalog.jar \
  --spring.profiles.active=dev \
  --catalog.labels.region=eu \
  --catalog.labels.deploy-id=build-42
~~~

With command-line properties enabled by default, the result is:

~~~text
owner     = platform
region    = eu
version   = v1
stage     = development
deploy-id = build-42
~~~

`region` from the CLI takes higher precedence than `apac` from the profile file. `deploy-id` is an added entry without removing entries bound from lower-priority sources.

## 4. Distinguishing a Map Entry from Properties Inside the Entry

With `Map<String,String>`, each entry has one scalar value. However, `Map<String, Backend>` can hold **multi-field objects**. In that case, a single map key (for example `primary`) can receive its fields from multiple sources.

For example:

~~~text
routing.backends.primary.url
routing.backends.primary.timeout
routing.backends.primary.enabled
routing.backends.backup.url
routing.backends.backup.timeout
~~~

Here:

- `backends` is the Map field name.
- `primary` and `backup` are map keys.
- `url`, `timeout`, and `enabled` are fields on the value object.
- Precedence applies down to individual leaf properties such as `routing.backends.primary.timeout`.

### 4.1. Java Model for a Map of Objects

Use JavaBean binding to clearly illustrate updating nested fields:

~~~java
package com.example.routing.config;

import java.net.URI;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public class RoutingProperties {

    private final Map<String, Backend> backends = new LinkedHashMap<>();

    public Map<String, Backend> getBackends() {
        return backends;
    }

    public static class Backend {
        private URI url;
        private Duration timeout;
        private boolean enabled;

        public URI getUrl() { return url; }
        public void setUrl(URI url) { this.url = url; }

        public Duration getTimeout() { return timeout; }
        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }

        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
~~~

Register configuration via scanning:

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

Spring Boot binds values into `RoutingProperties` once the bean is registered properly. `LinkedHashMap` in the example is the Java collection type; **do not depend on Map iteration order to determine property source precedence**. Precedence is resolved beforehand in the Binder, not based on entry position when iterating the map.

### 4.2. Default File Defines Two Backends

`application.yml`:

~~~yaml
routing:
  backends:
    primary:
      url: "https://primary.example.test"
      timeout: 5s
      enabled: true
    backup:
      url: "https://backup.example.test"
      timeout: 10s
      enabled: false
~~~

Initial result:

~~~text
primary.url      = https://primary.example.test
primary.timeout  = 5s
primary.enabled  = true

backup.url       = https://backup.example.test
backup.timeout   = 10s
backup.enabled   = false
~~~

### 4.3. Profile File Changes One Field of `primary` and Adds a Backend

`application-prod.yml`:

~~~yaml
routing:
  backends:
    primary:
      timeout: 2s
    analytics:
      url: "https://analytics.example.test"
      timeout: 7s
      enabled: true
~~~

With `prod` active, across the example files:

| Map key | Field | Default | Prod | Result |
| --- | --- | --- | --- | --- |
| `primary` | `url` | `https://primary.example.test` | absent | from default |
| `primary` | `timeout` | `5s` | `2s` | `2s` |
| `primary` | `enabled` | `true` | absent | `true` |
| `backup` | `url` | `https://backup.example.test` | absent | from default |
| `backup` | `timeout` | `10s` | absent | `10s` |
| `backup` | `enabled` | `false` | absent | `false` |
| `analytics` | `url` | absent | `https://analytics.example.test` | from prod |
| `analytics` | `timeout` | absent | `7s` | `7s` |
| `analytics` | `enabled` | absent | `true` | `true` |

The resulting `Map<String, Backend>` contains **three keys**: `primary`, `backup`, and `analytics`. Within entry `primary`, `timeout` gets the new value while `url` and `enabled` can still come from the default file.

This is important: "Map merge" does not just mean adding new top-level keys. With **object values**, individual fields of the same map entry can be bound from different property sources.

### 4.4. Omitting a Field Does Not Delete It from Lower Sources

If `application-prod.yml` only declares:

~~~yaml
routing:
  backends:
    primary:
      timeout: 2s
~~~

then omitting `url` is **not** equivalent to saying "delete url". The Binder can still resolve `routing.backends.primary.url` from another source.

If you want behavior like "disable primary", configure it explicitly:

~~~yaml
routing:
  backends:
    primary:
      enabled: false
~~~

Never treat the absence of a field in a higher-priority source as an intentional property deletion.

## 5. Maps Do Not Behave Like Lists

Spring Boot has a different rule for `List`/`Array`. When a list appears across multiple configuration sources, the list from the higher-priority source typically **replaces the entire list** from the lower source.

### 5.1. Side-by-Side Comparison on the Same Problem

`application.yml`:

~~~yaml
routing:
  regions:
    - "sg"
    - "jp"
  labels:
    owner: "core"
    stage: "default"
~~~

`application-prod.yml`:

~~~yaml
routing:
  regions:
    - "eu"
  labels:
    stage: "production"
    cluster: "blue"
~~~

When the `prod` profile is active:

~~~text
routing.regions = ["eu"]

routing.labels = {
  owner="core",
  stage="production",
  cluster="blue"
}
~~~

**List `regions`** does not become `["sg", "jp", "eu"]`. It contains only `["eu"]` from the higher-priority source.

**Map `labels`** preserves the `owner` entry, overrides `stage`, and adds `cluster`.

### 5.2. Object Lists Can Also Lose Unrepeated Fields

Example list in a lower source:

~~~yaml
routing:
  servers:
    - name: primary
      description: Main server
~~~

Higher source:

~~~yaml
routing:
  servers:
    - name: production-primary
~~~

When bound into `List<Server>`, the normal outcome is **one element** with `name=production-primary` and `description=null` if there is no other default. It does not pull `description=Main server` from the same-index element in the lower source.

That is precisely why **Map** fits better than List when the goal is overriding **a subset of properties on objects identified by stable keys**, such as `backends.primary.timeout`.

### 5.3. Do Not Turn a List into a Map Just to Get Merging

Choose the structure according to domain semantics:

- If data is an **ordered** sequence or element position matters, List may be the right choice.
- If data is a set of objects **accessed by stable identifiers** such as `primary`, `backup`, `team-a`, Map usually expresses intent clearly.
- A Map does not guarantee business ordering on its own, even when the Java class uses `LinkedHashMap`.
- Using stable map keys lets you override fields of the same object across environments without relying on fragile `[0]`, `[1]` indices.

## 6. Precedence Decides Duplicate Keys

Map combination does not bypass Spring Boot's precedence system. For properties with the same name, **higher priority wins**.

A simplified view in a typical running application:

| Source | Example | Role |
| --- | --- | --- |
| Default config data | `application.yml` | Supplies baseline values |
| Profile-specific config data | `application-prod.yml` | Can override defaults within the same location group |
| External config data / imports | `./config/application.yml`, `spring.config.import` | Participate under Config Data ordering rules |
| OS environment variables | `ROUTING_LABELS_REGION` | Typically higher priority than config data |
| Java system properties | `-Drouting.labels.region=...` | Typically higher priority than OS env |
| `SPRING_APPLICATION_JSON` | JSON object containing `routing.labels` | Higher priority than many standard sources |
| Command-line arguments | `--routing.labels.region=...` | Typically higher priority than JSON in default setups |

This is a list of **several common sources**, not every source in Spring Boot. In Servlet, test, devtools, or custom environments, additional sources exist. Moreover, ordering among files and imports depends on location groups, profiles, document activation, and `spring.config.*` options.

### 6.1. Conflict Example Across Three Sources

Default `application.yml`:

~~~yaml
catalog:
  labels:
    owner: platform
    region: global
~~~

Environment variable:

~~~bash
export CATALOG_LABELS_REGION=apac
~~~

Run:

~~~bash
java -jar catalog.jar \
  --catalog.labels.owner=commerce \
  --catalog.labels.revision=2026-11
~~~

Resulting Map under standard configuration:

~~~text
owner    = commerce  (CLI)
region   = apac      (OS environment)
revision = 2026-11   (CLI)
~~~

`owner` from CLI overrides `platform`. `region` from the environment overrides `global`. `revision` is added from CLI.

### 6.2. Do Not Equate File Order with Precedence Across All Sources

If `application-prod.yml` is loaded after `application.yml`, that is a Config Data rule in that specific context. A CLI argument can still beat both. Never claim "the bottom-most line in YAML always wins" across all configuration sources.

Similarly, across files loaded via `spring.config.import`, Boot applies specific import and priority rules. When predicting a map, identify **which sources are actually loaded** and **which source has higher priority**.

## 7. Maps in Multi-Document YAML Files

A single `application.yml` file can contain multiple documents separated by `---`:

~~~yaml
catalog:
  labels:
    owner: platform
    stage: default
    trace: "false"

---
spring:
  config:
    activate:
      on-profile: dev

catalog:
  labels:
    stage: development
    debug: "true"
~~~

When `dev` is inactive:

~~~text
owner=platform, stage=default, trace=false
~~~

When `dev` is active:

~~~text
owner=platform, stage=development, trace=false, debug=true
~~~

Documents in the same file are processed in order; an active later document can override matching properties from an earlier document. The Map binder combines keys present across effective documents.

Here `trace` and `debug` are written as quoted strings because the target Map is `Map<String,String>`. If the Map is defined as `Map<String, Boolean>`, unquoted boolean scalars can be used and Spring Boot converts types accordingly.

## 8. Maps in `.properties` Files

YAML is not strictly required to bind a Map. Dotted `.properties` format works as well:

~~~properties
catalog.labels.owner=platform
catalog.labels.region=global
catalog.labels.version=v1
~~~

When using a profile-specific file:

~~~properties
# application-prod.properties
catalog.labels.region=eu
catalog.labels.stage=production
~~~

Result under normal precedence:

~~~text
owner=platform
region=eu
version=v1
stage=production
~~~

Notice that Spring Boot binds by **property paths with prefix `catalog.labels`**, rather than requiring a YAML block named `labels`. `.properties` and YAML can express the exact same configuration contract.

If both `application.properties` and `application.yml` exist in the same location, Spring Boot applies precedence rules between the two formats. Stick to one consistent format to avoid hard-to-spot conflicts.

## 9. Maps from Environment Variables

Environment variables typically use uppercase letters and underscores. Spring Boot supports relaxed binding to map variable names to properties.

For example:

~~~bash
export CATALOG_LABELS_TEAM=backend
export CATALOG_LABELS_REGION=apac
java -jar catalog.jar
~~~

With `@ConfigurationProperties(prefix="catalog")` and field `Map<String,String> labels`, this can bind entries:

~~~text
team   = backend
region = apac
~~~

### 9.1. Map Keys from Environment Variables Are Lowercased

An easily overlooked rule documented by Spring Boot under **Binding Maps From Environment Variables**: when binding from system environment variables, Boot converts the environment variable name to lowercase. Thus, an entry defined via:

~~~bash
export MY_PROPS_VALUES_KEY=VALUE
~~~

in a model with `@ConfigurationProperties(prefix="my.props")` and `Map<String,String> values` typically produces key `key` and value `VALUE`. **The key name** is lowercased, while **the value content** is not lowercased.

Do not rely on environment variables to supply a map key that requires exact case sensitivity (such as header names or case-sensitive token identifiers) if binding rules do not satisfy your requirement. For complex map keys, consider YAML/properties or JSON with appropriate syntax.

### 9.2. Hyphens in Field Names

A Java field `defaultRegion` typically has the canonical property `catalog.default-region`. Following Boot conventions, the matching environment variable is `CATALOG_DEFAULTREGION`: replace `.` with `_`, drop `-`, uppercase. When configuration includes a Map, segments for field names and map keys must be organized consistently.

Do not assume every underscore remains a literal character in a map key. Relaxed binding parses property names according to source rules.

### 9.3. Keys That Must Preserve Dots or Special Characters

Environment variables have character restrictions on names. For instance, `/webhook` or `tenant.a` cannot always be represented verbatim as standard environment variables. In such cases, JSON or YAML/properties files using **bracket notation** are usually easier to control.

## 10. Maps from `SPRING_APPLICATION_JSON`

`SPRING_APPLICATION_JSON` lets you pass a structured JSON object. For example:

~~~bash
export SPRING_APPLICATION_JSON='{"catalog":{"labels":{"region":"apac","stage":"staging","owner":"commerce"}}}'
java -jar catalog.jar
~~~

With this value, `catalog.labels.region`, `catalog.labels.stage`, and `catalog.labels.owner` are added to Spring Boot's JSON property source.

If `application.yml` also has:

~~~yaml
catalog:
  labels:
    version: v1
    owner: platform
~~~

then, with no source having higher priority than JSON:

~~~text
region  = apac
stage   = staging
owner   = commerce
version = v1
~~~

`owner` comes from JSON; `version` still comes from YAML. This demonstrates a Map receiving entries from **two different PropertySource types**, not only Config Data files.

### 10.1. JSON `null` Is Not a Way to Delete Old Entries

If the JSON source contains:

~~~json
{
  "catalog": {
    "labels": {
      "owner": null
    }
  }
}
~~~

do not expect `null` to delete `catalog.labels.owner` from YAML. Spring Boot treats JSON `null` as a missing value during property resolution, so a lower-priority source can still provide the value.

This is the difference between **overwriting a key with a real value** and **requesting key deletion**. Spring Boot configuration is not a JSON Patch engine. If you need to deactivate an entry, design an explicit business flag instead of assuming `null` means delete.

### 10.2. Multi-Level JSON and Object-Valued Maps

~~~json
{
  "routing": {
    "backends": {
      "primary": {
        "timeout": "2s"
      },
      "analytics": {
        "url": "https://analytics.example.test",
        "enabled": true
      }
    }
  }
}
~~~

With `Map<String, Backend>` from section 4, JSON can override only `primary.timeout` and add `analytics`, while `primary.url`, `primary.enabled`, and the `backup` entry still come from default YAML if no higher source replaces them.

You do not need to parse JSON strings manually inside services when Spring Boot already provides the `spring.application.json` source.

## 11. Map Keys with Dots, Slashes, and Special Characters

Not every map key is a simple word like `primary` or `region`. Some applications use routes like `/v1/orders`, header names, or domain names.

Spring Boot provides **bracket notation** when binding Maps to preserve keys containing special characters. If a key is not wrapped in `[ ]`, characters other than alphanumeric characters, `-`, or `.` can be stripped during name normalization.

### 11.1. In `.properties` Files

~~~properties
gateway.routes.[/orders]=orders-service
gateway.routes.[/inventory]=inventory-service
gateway.routes./legacy=legacy-service
~~~

Assuming `Map<String,String> routes`, the result can be:

~~~text
/orders    -> orders-service
/inventory -> inventory-service
legacy     -> legacy-service
~~~

The `/legacy` key loses its leading `/` because bracket notation was omitted. This can be a very subtle bug when configuring routes.

### 11.2. In YAML, Keys Containing Brackets Must Be Quoted

~~~yaml
gateway:
  routes:
    "[/orders]": orders-service
    "[/inventory]": inventory-service
    "/legacy": legacy-service
~~~

Quotes around `"[/orders]"` tell the YAML parser to treat it as a scalar key. The Binder then uses bracket notation to keep the slash in the map key.

**Do not write** bare `[/orders]` in YAML assuming it will parse as a normal string. Brackets have syntactic meaning in YAML.

### 11.3. Dots in Map Keys: Depends on Value Type

Spring Boot documentation distinguishes two cases:

- With `Map<String,String>` or maps with supported scalar value types, dots in keys can often be preserved without brackets.
- With `Map<String,Object>` or nested object values, dots can be interpreted as **separators between property levels**, so keeping the entire key intact requires bracket notation.

For example:

~~~properties
example.values.a.b=c
~~~

With `Map<String,String> values`, this can bind an entry with key `a.b` and value `c`.

However, if `values` is `Map<String,Object>`, the path `a.b` can create a nested Map `a -> b -> c` instead of a literal key `a.b`.

To keep the literal key:

~~~properties
example.values.[a.b]=c
~~~

In YAML:

~~~yaml
example:
  values:
    "[a.b]": c
~~~

Never choose a key naming pattern without considering the **Map's value type**.

### 11.4. Map Keys Are Business Identifiers, Not Java Fields

In:

~~~yaml
tenant:
  endpoints:
    "[tenant.a]": "https://tenant-a.example.test"
    "[tenant.b]": "https://tenant-b.example.test"
~~~

`tenant.a` and `tenant.b` are **map keys**, not fields of a Java class. When these names are meaningful business IDs, preserve them with bracket notation where needed and retrieve them via `map.get("tenant.a")`.

Difference with nested objects: `Map<String, Endpoint>` may require literal key quoting/bracketing so the Binder does not misinterpret dots as nested fields inside `Endpoint`.

## 12. Design Pattern: Maps for Typed Configuration

A common pattern uses environment names, backend names, or provider names as keys:

~~~yaml
payments:
  providers:
    primary:
      endpoint: "https://pay-a.example.test"
      timeout: 3s
    secondary:
      endpoint: "https://pay-b.example.test"
      timeout: 5s
~~~

Configuration record:

~~~java
package com.example.payments.config;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(
        Map<String, Provider> providers
) {
    public record Provider(URI endpoint, Duration timeout) {}
}
~~~

Register the record via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. A service can retrieve a provider:

~~~java
public PaymentProperties.Provider findProvider(
        PaymentProperties properties, String name) {
    PaymentProperties.Provider provider =
            properties.providers().get(name);

    if (provider == null) {
        throw new IllegalArgumentException(
                "Missing provider configuration: " + name);
    }
    return provider;
}
~~~

### 12.1. Advantages of Using a Map with Stable Keys

- Adding a provider requires only declaring a new key in config.
- Override `payments.providers.primary.timeout` without copying the entire provider.
- You can use default values and layer environment-specific settings on top.
- Code looks up providers by name more cleanly than by list index.
- Differences across environments stay small and focused on the fields that actually change.

### 12.2. Risks to Control

- A provider configured without `endpoint` in all sources can produce an object with a missing field.
- A misspelled map key (`primray` instead of `primary`) creates an **unintended new entry** instead of overriding the existing one.
- Individual environments can introduce unwanted entries if the allowed provider set is not constrained.
- Invalid URL or Duration values trigger binding/conversion errors.
- Maps with special-character keys can get normalized if proper key-preserving syntax is omitted.

Use validation and binding tests for critical keys instead of merely checking that the map has at least one entry.

## 13. Validation for Maps and Value Objects

Use `@Validated` together with Bean Validation when configuration has mandatory requirements. Example for Spring Boot 3, Java 17+:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "payments")
@Validated
public record PaymentProperties(
        @NotEmpty Map<String, @Valid Provider> providers
) {
    public record Provider(
            @NotNull URI endpoint,
            @NotNull Duration timeout
    ) {}
}
~~~

The example illustrates validation intent:

- `@NotEmpty` requires the map to have at least one entry.
- `@Valid` on the map value type requests cascading validation on `Provider` fields when Bean Validation and container-element validation are active.
- `@NotNull` guards `endpoint` and `timeout` once configuration is bound.

To use Jakarta annotations in Spring Boot, you need an appropriate validation dependency such as `spring-boot-starter-validation`. Depending on how classes are declared and the validator version, you may also place `@Valid` on the record component / constructor parameter; verify the desired behavior with startup/binding tests.

For `Map<String,String>`, consider specific constraints on values, or a custom validator when each key requires a distinct format.

### 13.1. Do Not Assume "Merge Succeeded" Means Every Entry Is Valid

A Map can combine entries cleanly across multiple sources and still hold invalid configuration:

~~~yaml
payments:
  providers:
    primary:
      timeout: 3s
~~~

If no other source provides `primary.endpoint`, the `primary` entry is incomplete. This is a configuration error to catch, not a bug in the map merge algorithm.

### 13.2. Validation and Security

If a map holds API keys or secrets, avoid logging the entire `@ConfigurationProperties` object. A record can expose fields via `toString()`. Actuator endpoints such as `env` and `configprops` must be secured, access-controlled, and configured to mask sensitive values.

Map merging does not encrypt, manage lifecycle, or protect secrets. For sensitive data, use a proper secret source and bind into Java models only where necessary.

## 14. Adding Configuration with Files Outside the JAR

A major benefit of Map merging is supplying a **baseline configuration inside the artifact** and adding or overriding select entries via externalized files.

`classpath:/application.yml`:

~~~yaml
services:
  endpoints:
    billing: "https://billing.default.test"
    inventory: "https://inventory.default.test"
~~~

External `./config/application.yml` outside the JAR:

~~~yaml
services:
  endpoints:
    billing: "https://billing.prod.internal"
    reporting: "https://reporting.prod.internal"
~~~

If the application runs with the appropriate working directory and Spring Boot loads the external file via default Config Data search paths:

~~~text
billing   = https://billing.prod.internal
inventory = https://inventory.default.test
reporting = https://reporting.prod.internal
~~~

You do not need to copy the `inventory` entry into the external file just to preserve it. This reduces duplication between default and deployment configuration.

Note: an external file is only picked up if placed in a location Boot searches or explicitly imported. An arbitrary file does not automatically become a property source.

## 15. `spring.config.import` and Multiple Sources

Example `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./config/routing-extra.yml"

routing:
  backends:
    primary:
      url: "https://default.example.test"
      timeout: 5s
~~~

File `./config/routing-extra.yml`:

~~~yaml
routing:
  backends:
    primary:
      timeout: 2s
    analytics:
      url: "https://analytics.example.test"
      timeout: 8s
~~~

Imported documents have their own precedence order under Config Data rules. When the import loads with higher precedence than the declaring document, the resulting Map can be:

~~~text
primary.url     = https://default.example.test
primary.timeout = 2s

analytics.url     = https://analytics.example.test
analytics.timeout = 8s
~~~

Keep in mind: **importing a file via `spring.config.import`** is a Config Data loading step; **Map combining entries** is a binding/property-resolution step. Both mechanisms work together, but they are not the same operation.

If the imported file does not exist and has the `optional:` prefix, Boot skips that location without a missing-location failure. That does not guarantee required properties are present: validation is still necessary.

## 16. Config Trees Can Also Supply Map Keys

When a deployment platform mounts secrets or config as individual files, Spring Boot supports:

~~~properties
spring.config.import=optional:configtree:/run/config/
~~~

Suppose the files are:

~~~text
/run/config/
├── services.endpoints.billing
└── services.endpoints.reporting
~~~

Each file's content becomes the value of the corresponding property, such as a service URL. If `services.endpoints.inventory` already exists in `application.yml`, the `inventory` entry can still bind into the Map alongside entries coming from the config tree.

The difference from YAML is that **the filename becomes the property key** and **the file content becomes the value**. A config tree does not parse each file as a `key=value` document.

If a map stores secrets like passwords, restrict file permissions, avoid printing values to logs, and understand your runtime refresh policy. Updating a Secret on a volume does not automatically refresh already-bound configuration beans by default.

## 17. Overlapping Keys and "Delete" Semantics

Spring Boot externalized configuration is a mechanism for **defining and overriding properties**, not a full patch language for adding/updating/deleting objects like JSON Patch.

### 17.1. Omitting a Key in a Higher Source Does Not Delete It from a Lower Source

Default:

~~~yaml
features:
  flags:
    beta: true
    legacy: true
~~~

Prod:

~~~yaml
features:
  flags:
    beta: false
~~~

Resulting Map typically:

~~~text
beta   = false
legacy = true
~~~

If you want to disable `legacy`, set it explicitly to `false` when the value type supports it. If you want **no `legacy` entry at all**, use another design policy: omit it from the baseline source, filter/sanitize after binding using controlled business logic, or adopt a configuration structure with explicit removal semantics.

### 17.2. Empty Values Differ from Undeclared Keys

A higher source containing:

~~~properties
features.labels.owner=
~~~

declares an **empty string** for `features.labels.owner`. When binding `Map<String,String>`, this can act as an effective empty value that overrides the string from the lower source; it does not default to "remove map entry".

For other types, an empty string can cause a conversion error or be handled by the target converter. Never use an empty string as a generic deletion signal across types.

### 17.3. JSON `null` Is Not a Guaranteed Delete Operation

`SPRING_APPLICATION_JSON` containing a key with value `null` does not guarantee deleting the matching value from a lower source; Spring Boot treats JSON `null` as missing during property resolution.

Good design uses an explicit flag or setting, such as:

~~~yaml
routing:
  backends:
    backup:
      enabled: false
~~~

instead of relying on `null` or key omission in a higher source to erase a backend from default configuration.

## 18. Reading the Result in Code

### 18.1. Accessing the Map from the Bound Bean

With `CatalogProperties`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class LabelService {

    private final CatalogProperties properties;

    public LabelService(CatalogProperties properties) {
        this.properties = properties;
    }

    public String region() {
        return properties.labels().get("region");
    }
}
~~~

The service reads the post-binding result without manually merging multiple files. If an entry is mandatory, validate or check explicitly rather than letting `Map.get(...)` return `null` and fail downstream.

### 18.2. `Environment.getProperty("catalog.labels")` Is Not the Same as Binding a Map

A common mistake:

~~~java
String labels = environment.getProperty("catalog.labels");
~~~

This looks up **a property literally named `catalog.labels`**. Spring does not automatically synthesize a string containing all child keys. When actual data lives under `catalog.labels.owner` and `catalog.labels.region`, reading a scalar named `catalog.labels` will not give the expected result.

To obtain the entire Map, bind via `@ConfigurationProperties` or use Spring Boot's `Binder` with an explicit target type.

### 18.3. Using `Binder` for On-Demand Binding

Example when binding directly from a prepared `Environment`:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public Map<String, String> readLabels(Environment environment) {
    return Binder.get(environment)
            .bind("catalog.labels",
                    Bindable.mapOf(String.class, String.class))
            .orElse(Map.of());
}
~~~

This snippet illustrates the `Binder` API and an empty-map fallback if the group is unbound. It is not a rule that services should call `Binder` manually; for static configuration, `@ConfigurationProperties` beans remain recommended.

Remember: `Environment` and `Binder` do not share the same lookup model. A scalar `getProperty` call cannot replace multi-source Map binding.

## 19. Diagnosing When a Map Lacks Expected Entries

Typical scenarios:

| Symptom | Causes worth checking | How to fix |
| --- | --- | --- |
| Map only has entries from one source | Other source wasn't loaded, wrong prefix, or wrong key | Inspect actual files/profiles/imports/env |
| Duplicate key has unexpected value | Higher-priority source overrode it | Check precedence and property sources |
| Entry `primray` exists instead of `primary` | Typo in map key | Fix key, add valid-key validation |
| Slashes disappeared from keys | Missing bracket notation | Write `[/orders]` and quote in YAML |
| Keys from env vars turned lowercase | System environment binding rule | Use another source if casing matters |
| Map value object has missing fields | No property set for that field in any source | Add missing property or validation |
| Map still has old key despite profile omitting it | Lower source still supplies that key | Use an enabled/disabled flag or explicit removal design |
| List did not merge entries like a Map | Lists undergo replacement by precedence | Pick the right structure or supply the full list |
| `Environment.getProperty("prefix.map")` returns null | No scalar exists at the prefix key itself | Use `@ConfigurationProperties` or `Binder` |
| Empty string overwrote a value | Empty value present in higher source | Never use an empty string to represent absence |
| Failure binding URL/Duration | Converter cannot parse the value | Check format and target type |
| Stale values after ConfigMap change | Bean not refreshed/rebound or app not restarted | Design appropriate rollout/refresh strategy |

### 19.1. Inspecting Sources for a Specific Property

For **non-sensitive** keys, you can inspect:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class MapPropertyProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public MapPropertyProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.labels.region";

        System.out.println("Resolved = "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " => " + value);
            }
        });
    }
}
~~~

This snippet only checks one literal key. Property source names and direct lookup behavior depend on the source type and Spring Boot version; with relaxed binding, env-formatted names may require different inspection or Actuator origin tracking.

Never log passwords, tokens, private keys, or entire sensitive Maps. When enabling Actuator `env` or `configprops`, secure the endpoints and configure safe value masking.

### 19.2. Reasoning Checklist When an Entry Is Wrong

1. Verify the bean has `@ConfigurationProperties` and is registered via appropriate scanning/enabling.
2. Identify the actual prefix, such as `catalog.labels`.
3. List corresponding child properties across every loaded source.
4. Identify the higher-priority source for **each key or field of a map value object**.
5. Check whether special-character keys require bracket notation.
6. Check whether env keys were lowercased or normalized.
7. Distinguish Maps, Lists, nested objects, and scalars.
8. Check conversions, defaults, and validation.
9. Re-read the bound bean and compare it against effective property sources.

Never just inspect the final YAML file on a developer machine and assume it represents the entire production configuration.

## 20. Systematic Testing for Map Merging

### 20.1. Testing with `ApplicationContextRunner`

In Spring Boot tests, you can spin up a minimal context to verify Map binding.

Example using `CatalogProperties` from section 3:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void mapHasMultipleKeys() {
        runner.withPropertyValues(
                "catalog.labels.owner=platform",
                "catalog.labels.region=apac",
                "catalog.labels.stage=dev")
            .run(context -> {
                CatalogProperties config =
                        context.getBean(CatalogProperties.class);

                assertThat(config.labels())
                        .containsEntry("owner", "platform")
                        .containsEntry("region", "apac")
                        .containsEntry("stage", "dev");
            });
    }
}
~~~

The test above verifies binding distinct entries into the Map, though values come from **a single** set of test properties. To properly test precedence across **multiple property sources**, create two independent sources with an explicit priority order.

### 20.2. Testing Conflicts Between Two Sources

Example initializing `StandardEnvironment` and two `MapPropertySource` instances for illustration:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

public class MapBindingExample {

    public static Map<String, String> bind() {
        StandardEnvironment environment = new StandardEnvironment();

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("catalog.labels.owner", "platform");
        defaults.put("catalog.labels.region", "global");

        Map<String, Object> overrides = new LinkedHashMap<>();
        overrides.put("catalog.labels.region", "apac");
        overrides.put("catalog.labels.stage", "dev");

        environment.getPropertySources().addLast(
                new MapPropertySource("defaults", defaults));

        environment.getPropertySources().addFirst(
                new MapPropertySource("overrides", overrides));

        return Binder.get(environment)
                .bind("catalog.labels",
                        Bindable.mapOf(String.class, String.class))
                .orElse(Map.of());
    }
}
~~~

`addFirst` places the `overrides` source at high priority. Expected result:

~~~text
owner  = platform
region = apac
stage  = dev
~~~

This example illustrates source ordering. `StandardEnvironment` already includes system property sources; in real tests/applications, isolate or control the environment to avoid colliding keys from the test runner machine.

### 20.3. Testing Maps with Object Values

Create a default `application.yml` setting `routing.backends.primary.url` and `routing.backends.primary.timeout`. Then provide a higher-priority source setting only `routing.backends.primary.timeout=2s` along with `routing.backends.analytics.url=...`.

Verify:

- `primary.url` retains its value from the lower source.
- `primary.timeout` is overridden.
- `analytics` is added as a new entry.
- Other entries such as `backup` are not deleted.

This style of test demonstrates the nature of Map merging much better than testing scalar entries alone.

## 21. Hands-On Exercises

### Exercise A: Simple String Map

`application.yml`:

~~~yaml
lesson:
  attributes:
    owner: platform
    level: basic
    region: global
~~~

`application-dev.yml`:

~~~yaml
lesson:
  attributes:
    level: advanced
    stage: development
~~~

Create `@ConfigurationProperties(prefix="lesson")` with `Map<String,String> attributes`. Predict keys and values when `dev` is active. The result should contain `owner=platform`, `level=advanced`, `region=global`, and `stage=development`.

### Exercise B: CLI Overrides Exactly One Entry

Keep Exercise A and additionally run with:

~~~bash
java -jar lesson.jar \
  --spring.profiles.active=dev \
  --lesson.attributes.level=expert
~~~

Predict that `level=expert` beats `advanced` from the profile file, while other keys still resolve from their respective sources.

### Exercise C: Object-Valued Map

Create `Map<String, Service>`, where each `Service` has `endpoint`, `timeout`, and `enabled`. Default configuration declares a complete `primary` entry. The `prod` profile overrides only `primary.timeout` and adds `analytics`. Verify `primary.endpoint` is not lost.

### Exercise D: Comparing with a List

Change the model in Exercise C from a name-keyed Map to `List<Service>`. Give the `prod` profile a list containing only one element. Bind and observe why List elements do not merge by index like Map values with stable keys.

### Exercise E: Special Keys

Try three keys in YAML:

~~~yaml
lesson:
  routes:
    "[/v1/orders]": order-service
    "[/v1/products]": product-service
    "/legacy": legacy-service
~~~

Bind into `Map<String,String> routes`. Observe keys that retain slashes versus keys normalized when brackets are omitted. Fix `/legacy` to `"[/legacy]"` to preserve the exact characters.

### Exercise F: Multiple PropertySources

Use `MapPropertySource` and `Binder` as in section 20.2. Supply `catalog.labels.region` in both sources, and other keys in each individual source. Verify precedence changes `region` without dropping `owner` and `stage`.

### Exercise G: Catching Misspelled Keys

Default source defines `payments.providers.primary`. Production source accidentally writes `payments.providers.primray.timeout`. Bind the map and observe how a new entry or incomplete configuration is created instead of overriding the existing entry. Add validation on allowed provider keys to catch the mistake.

### Exercise H: Do Not Use `null` to Delete Keys

Default configuration sets `features.flags.legacy=true`. In a higher JSON source, supply `legacy:null`. Inspect the result, then switch to `legacy:false` to express disabling the feature accurately.

## 22. Quick Decision Table

| Need | Suitable structure / approach |
| --- | --- |
| Adding new keys across environments | `Map<String,String>` or `Map<String, Config>` |
| Overriding one field of a backend with a stable ID | `Map<String, Backend>` keyed by backend name |
| List of elements with business-significant order | `List<T>`; overrides typically supply the complete list |
| Map key containing slashes | Bracket notation `[/path]` |
| Map key containing dots with complex values | Bracket notation `[tenant.a]` |
| Picking the winning source on field collisions | Governed by `Environment` precedence |
| Removing old configuration | Design an explicit disable/remove mechanism rather than relying on omission in higher sources |
| Validating mandatory entries | Bean Validation and binding tests |
| Secrets stored as a map | Secure secret source, restrict logs/Actuator |
| Reading the full Map | `@ConfigurationProperties` or `Binder` |
| Testing two sources with overlapping keys | Construct independent property sources and assert precedence |

## 23. Things to Remember

1. **Maps combine keys** across multiple property sources. Keys present in only one source still appear in the final Map.
2. **Colliding property names take the value from the higher-priority source.** This comes from `Environment` precedence, not map iteration order.
3. With `Map<String, ObjectType>`, fields of the same value object can come from multiple sources: overriding one field does not wipe out other fields.
4. **Lists do not merge like Maps**: when configured in multiple sources, a higher-priority list typically replaces lower-priority lists.
5. Map key names must be preserved with bracket notation when containing `/`, dots with complex value types, or special characters. Environment variables also lowercase map keys.
6. **Omitting an entry in a higher source does not delete the entry from a lower source**; empty strings and JSON `null` do not provide uniform deletion semantics either.
7. Map merging does not replace validation, secret protection, or real environment testing. Always verify prefixes, source priority, value types, and map key names.
8. When code needs a combined Map, prefer `@ConfigurationProperties` rather than reading individual strings and merging manually.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): configuration sources, precedence, profile-specific files, and imports.
- [Spring Boot Reference — Merging Complex Types](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types): Map entry merging and List replacement rules.
- [Spring Boot Reference — Binding Maps](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps): bracket notation and special key names.
- [Spring Boot Reference — Binding From Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables): variable name translation and lowercased map keys.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): typed binding, JavaBean, constructor binding, and validation.
- [Spring Boot Reference — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): importing config files and priority ordering.
