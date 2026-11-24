# Representing Lists and Maps with .properties and YAML in Spring Boot 3.3

## 1. Goal and general idea

In Spring Boot 3.3, both `application.properties` and `application.yaml`/`application.yml` can configure **lists** (`List`, `Set`, arrays) and **maps** (`Map<K,V>`). The two formats express data differently, yet when loaded into `Environment`, Spring Boot flattens YAML into flat configuration keys and uses the **Binder** to map them to Java types, typically via `@ConfigurationProperties`.

Distinguish these up front:

- **List**: an ordered collection of elements, such as a list of servers or endpoints; typically accessed by index `[0]`, `[1]`…
- **Map**: a collection of key–value pairs, such as `region → URL` or `serviceName → service configuration`; accessed by key name.
- **List of objects**: each element has multiple properties such as `name`, `url`, `weight`.
- **Map of objects**: each key points to a structure with its own properties, such as `backends.billing.base-url`.

The examples below use the prefix `app`. For the same data, choose **one** of `application.properties` or `application.yaml`; there is no need to declare both.

## 2. Lists of simple values

### 2.1. `application.properties`: `[index]` notation

```properties
# application.properties
app.regions[0]=ap-southeast-1
app.regions[1]=ap-northeast-1
app.regions[2]=eu-west-1
```

Indices start from **0**. When bound to `List<String> regions`, the expected result in order is:

```text
["ap-southeast-1", "ap-northeast-1", "eu-west-1"]
```

For simple scalar lists, Spring Boot also supports comma-separated values:

```properties
app.regions=ap-southeast-1,ap-northeast-1,eu-west-1
```

The two forms above are **mutually alternative approaches**; choose one style for a given property within the same configuration source. Use `[index]` when assigning each element explicitly or representing lists of objects. Use comma-separated values when elements are short and do not contain delimiters needing special handling.

### 2.2. `application.yaml`: sequences

```yaml
# application.yaml
app:
  regions:
    - ap-southeast-1
    - ap-northeast-1
    - eu-west-1
```

The same data can be written as a flow sequence:

```yaml
app:
  regions: [ap-southeast-1, ap-northeast-1, eu-west-1]
```

When Spring Boot flattens the YAML, the list in the first example is equivalent to:

```properties
app.regions[0]=ap-southeast-1
app.regions[1]=ap-northeast-1
app.regions[2]=eu-west-1
```

**Important:** `-` marks a sequence element in YAML; sibling elements must have consistent indentation. YAML uses **spaces**—avoid tabs for indentation.

### 2.3. Lists of numbers, booleans, and other types

Values from configuration files can be converted by the Binder to the appropriate types declared in Java:

```properties
app.retry-delays[0]=1s
app.retry-delays[1]=5s
app.limits[0]=10
app.limits[1]=20
app.features[0]=true
app.features[1]=false
```

```yaml
app:
  retry-delays:
    - 1s
    - 5s
  limits: [10, 20]
  features: [true, false]
```

This example corresponds to `List<Duration> retryDelays`, `List<Integer> limits`, and `List<Boolean> features` in `@ConfigurationProperties`. For `Duration`, `1s` and `5s` state units explicitly. Type conversion does not happen merely because YAML has a sequence; target types are determined by the configuration class and converters.

## 3. Lists of objects: one element with multiple properties

Suppose each endpoint needs `name`, `url`, and `weight`.

**.properties form:**

```properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.endpoints[0].weight=100

app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.test
app.endpoints[1].weight=10
```

**Equivalent YAML form:**

```yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.test
      weight: 100
    - name: backup
      url: https://backup.example.test
      weight: 10
```

Spring Boot flattens the YAML above to:

```text
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.endpoints[0].weight=100
app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.test
app.endpoints[1].weight=10
```

Think of `endpoints[0]` as **the entire first object**; `.name`, `.url`, and `.weight` are properties of that same object. Adding an element means adding a new index in `.properties` or adding an entry starting with `-` in YAML. Use sequential, contiguous indices starting from 0 so the Binder can construct the expected collection.

A common YAML mistake is placing a field at the wrong indentation level:

```yaml
# WRONG: weight becomes a sibling of endpoints instead of belonging to the first element
app:
  endpoints:
    - name: primary
      url: https://primary.example.test
  weight: 100
```

## 4. Maps with simple values

### 4.1. `Map<String,String>`

**.properties form:**

```properties
app.labels.team=platform
app.labels.env=staging
app.labels.owner=backend
```

**YAML form:**

```yaml
app:
  labels:
    team: platform
    env: staging
    owner: backend
```

Result after binding into `Map<String,String> labels`:

```text
{
  "team": "platform",
  "env": "staging",
  "owner": "backend"
}
```

Here `labels` is the property name, while `team`, `env`, and `owner` are **actual Map keys**. Do not confuse `app.labels.team` with a fixed Java field named `team`: the set of keys can vary by configuration.

### 4.2. Maps with numeric/boolean values

```properties
app.max-connections.alpha=10
app.max-connections.beta=25
app.flags.audit=true
app.flags.preview=false
```

```yaml
app:
  max-connections:
    alpha: 10
    beta: 25
  flags:
    audit: true
    preview: false
```

These bind to `Map<String,Integer> maxConnections` and `Map<String,Boolean> flags`, respectively. Use the appropriate value type so you do not have to parse strings manually after reading configuration.

## 5. Maps whose values are objects or nested structures

For example, each backend is keyed by name and contains a URL and timeout.

**.properties form:**

```properties
app.backends.billing.base-url=https://billing.example.test
app.backends.billing.connect-timeout=2s
app.backends.inventory.base-url=https://inventory.example.test
app.backends.inventory.connect-timeout=5s
```

**YAML form:**

```yaml
app:
  backends:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 5s
```

Data model:

```text
app.backends
  ├── billing   → { baseUrl, connectTimeout }
  └── inventory → { baseUrl, connectTimeout }
```

In Java, `Map<String,Backend> backends` binds two entries: `billing` and `inventory`. With `Backend` as an object, properties after the Map key continue binding as properties of that object. `Duration` accepts values like `2s` and `5s`.

Structures can be nested even deeper, such as a `Map<String,List<Endpoint>>`:

```yaml
app:
  routes-by-region:
    vn:
      - name: primary
        url: https://vn-1.example.test
        weight: 100
    sg:
      - name: primary
        url: https://sg-1.example.test
        weight: 100
      - name: fallback
        url: https://sg-2.example.test
        weight: 20
```

Equivalent in `.properties` (key lines shown):

```properties
app.routes-by-region.vn[0].name=primary
app.routes-by-region.vn[0].url=https://vn-1.example.test
app.routes-by-region.vn[0].weight=100
app.routes-by-region.sg[0].name=primary
app.routes-by-region.sg[0].url=https://sg-1.example.test
app.routes-by-region.sg[0].weight=100
app.routes-by-region.sg[1].name=fallback
app.routes-by-region.sg[1].url=https://sg-2.example.test
app.routes-by-region.sg[1].weight=20
```

This is a combined structure: `routes-by-region` is a Map; `vn` and `sg` are Map keys; each value is an indexed List.

## 6. Map keys with special characters: how to preserve exact key names

This rule is very easy to overlook. When binding Maps, Spring Boot 3.3 uses **square bracket `[key]` notation** to preserve special characters in keys. Without brackets, characters outside letters, digits, `-`, or `.` can be stripped during binding.

### 6.1. Example with `/`

If you want the actual key to be `/api/v1`, write:

```properties
app.routes.[/api/v1]=billing
app.routes.[/health]=management
```

```yaml
app:
  routes:
    "[/api/v1]": billing
    "[/health]": management
```

With `Map<String,String> routes`, the resulting entries are `"/api/v1" → "billing"` and `"/health" → "management"`.

**In YAML, keys containing square brackets must be wrapped in quotes**. If you write:

```properties
app.routes./api/v1=billing
```

without `[]`, `/` is not preserved under Map binding rules; the key may be turned into `apiv1`. Distinguish a property name looking valid in the file from whether **the Map key after binding** remains intact.

### 6.2. Dots in keys: depends on the Map value type

- With **`Map<String,String>`** or similar scalars, a key like `a.b` can preserve its dot even without `[]`.
- With **`Map<String,Object>`** or complex values, an unbracketed dot may be interpreted as nested object/map levels.

Example to preserve the exact key `a.b` when Map values may not be scalars:

```properties
app.metadata.[a.b]=value
```

```yaml
app:
  metadata:
    "[a.b]": value
```

Do not mechanically write `app.metadata.a.b=value` when your goal is to store the literal key `a.b` in `Map<String,Object>`; that can produce a nested structure `a → b`. Likewise, keys containing `/` or other special characters should use bracket notation so normalization does not alter the name.

### 6.3. Map keys from environment variables

Environment variable names are normalized during relaxed binding, and when binding Maps, key names coming from environment variables are typically **converted to lowercase**. Example:

```bash
APP_LABELS_TEAM=PLATFORM
```

When bound to `Map<String,String> labels`, the key is `team`, while the value remains `PLATFORM`. If you need to preserve exact casing or special characters in keys, consider using a configuration file or a source capable of representing keys verbatim.

## 7. Binding to Java with `@ConfigurationProperties`

`@ConfigurationProperties` is well suited for collections and nested configuration objects because it provides **type-safe binding**, type conversion, and relaxed binding. The following complete example works with **Java 17+ and Spring Boot 3.3**.

**File `AppProperties.java`:**

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<String> regions,
        List<Endpoint> endpoints,
        Map<String, String> labels,
        Map<String, Backend> backends,
        Map<String, String> routes) {

    public record Endpoint(String name, String url, int weight) {
    }

    public record Backend(String baseUrl, Duration connectTimeout) {
    }
}
```

**Enable configuration scanning in the application:**

```java
package com.example.demo;

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
```

**File `application.yaml` matching the record:**

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1

  endpoints:
    - name: primary
      url: https://primary.example.test
      weight: 100
    - name: backup
      url: https://backup.example.test
      weight: 10

  labels:
    team: platform
    env: staging

  backends:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 5s

  routes:
    "[/api/v1]": billing
    "[/health]": management
```

**Using the bound bean:**

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import org.springframework.stereotype.Service;

@Service
public class EndpointService {

    private final AppProperties config;

    public EndpointService(AppProperties config) {
        this.config = config;
    }

    public void printConfig() {
        System.out.println(config.regions());
        System.out.println(config.endpoints().get(0).url());
        System.out.println(config.labels().get("team"));
        System.out.println(config.backends().get("billing").connectTimeout());
        System.out.println(config.routes().get("/api/v1"));
    }
}
```

In Spring Boot 3.3, configuration records with a single constructor are natively supported via constructor binding; `@ConstructorBinding` is not needed for the single-constructor case. If you use a JavaBean class instead of a record, you can use constructor binding or appropriate getters/setters. `@ConfigurationPropertiesScan` discovers classes/records annotated with `@ConfigurationProperties` in the scanned packages. You can also register explicitly via `@EnableConfigurationProperties(AppProperties.class)` instead of scanning when needed.

**Relaxed binding:** YAML `base-url` maps to the Java component `baseUrl`, and `connect-timeout` maps to `connectTimeout`. Similarly, `routes-by-region` can bind to `routesByRegion`. The prefix of `@ConfigurationProperties` should use canonical lowercase kebab-case.

## 8. Lists and Maps when configuration comes from multiple sources/profiles

This is the **most important behavioral difference**, independent of whether `.properties` or YAML is used.

### 8.1. **Lists are replaced wholesale, not merged element by element**

Suppose `application.yaml`:

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
  endpoints:
    - name: primary
      url: https://primary.example.test
      weight: 100
    - name: backup
      url: https://backup.example.test
      weight: 10
```

And `application-dev.yaml`:

```yaml
app:
  regions:
    - localhost
  endpoints:
    - name: local
      url: http://localhost:8081
```

When the `dev` profile is active and both files are loaded in normal precedence order:

- `regions` becomes **`["localhost"]`**, not a three-element list.
- `endpoints` has only **one** object with `name=local`, `url=http://localhost:8081`.
- This object's `weight` is not inherited from element `[0]` in the lower-precedence source. With primitive `int weight` in the record example, the default when omitted can be `0`; if you need to distinguish "not declared", use the wrapper type `Integer` (which can be `null`) or define an explicit default value.

For collections, the configuration from the **highest-precedence source** is used for the entire List. Do not rely on writing only `app.endpoints[0].name` in a higher profile and expecting `url` or `weight` from a lower profile to merge into the same element.

**Equivalent using `.properties`:**

```properties
# application.properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.endpoints[0].weight=100
app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.test
app.endpoints[1].weight=10

# application-dev.properties (DIFFERENT file)
app.regions[0]=localhost
app.endpoints[0].name=local
app.endpoints[0].url=http://localhost:8081
```

The List outcome in the `dev` profile follows the exact same rule, regardless of YAML or `.properties`.

### 8.2. **Maps can merge keys and properties from multiple sources**

Suppose `application.yaml`:

```yaml
app:
  backends:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 5s
```

And `application-dev.yaml`:

```yaml
app:
  backends:
    billing:
      base-url: http://localhost:9000
    notifications:
      base-url: http://localhost:9010
      connect-timeout: 1s
```

When `dev` is active, the Map has keys `billing`, `inventory`, and `notifications`:

| Key | `baseUrl` | `connectTimeout` |
| --- | --- | --- |
| `billing` | `http://localhost:9000` | `2s` from lower source |
| `inventory` | `https://inventory.example.test` | `5s` |
| `notifications` | `http://localhost:9010` | `1s` |

For Map objects, **different properties** of the same entry can come from multiple sources; when **the same property** appears multiple times, the higher-precedence source wins. Unlike Lists, you do not have to rewrite the entire Map in the higher profile.

The List-replacement and Map-merging rules apply when binding from **multiple PropertySources** in general, not only profile files. To understand "which source is higher", check Spring Boot's PropertySource precedence order and the order in which Config Data files are loaded.

## 9. From environment variables to Lists, Maps, and objects

If the application gets configuration from a container, Spring Boot supports relaxed binding for environment variables. The conversion rule from canonical names is: **dots become `_`, hyphens `-` are removed, convert to uppercase**. For List elements, indices are surrounded by underscores.

```properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.backends.billing.base-url=https://billing.example.test
```

Conceptually, these can be replaced by environment variables:

```bash
APP_ENDPOINTS_0_NAME=primary
APP_ENDPOINTS_0_URL=https://primary.example.test
APP_BACKENDS_BILLING_BASEURL=https://billing.example.test
```

Specifically: `APP_ENDPOINTS_0_NAME` maps to `app.endpoints[0].name`; `BASEURL` matches the canonical property `base-url` because `-` is stripped when converting to environment variable form. Do not expect an environment variable with a complex Map key—containing `/` or requiring case sensitivity—to keep its exact key after binding.

When configuring long lists or complex Maps, YAML files can be easier to manage than many scattered environment variables. However, choosing how to supply configuration also depends on deployment infrastructure and data sensitivity.

## 10. How do `@ConfigurationProperties`, `@Value`, and `Environment` differ?

| Reading approach | Best suited for | Key notes |
| --- | --- | --- |
| `@ConfigurationProperties` | `List<T>`, `Map<K,V>`, nested objects, multiple properties under a prefix | Provides relaxed binding and type conversion; the primary choice for collection configuration. |
| `Environment#getProperty(String)` | Reading a single **flattened key** | For example, `getProperty("app.regions[0]")` can read one element; does not automatically construct `List<Endpoint>` from a prefix. |
| `@Value` | A few single values or specific expressions | Lacks the full type-safe/relaxed binding capabilities of `@ConfigurationProperties`; in particular, do not rely on `@Value("${app.endpoints}")` to build complex object Lists. |

Example:

```java
String firstRegion = environment.getProperty("app.regions[0]");
```

For YAML lists, the indexed form is the flattened key; do not assume `environment.getProperty("app.regions")` always returns a complete list string. The reliable approach for collections is the binder plus an appropriate Java model.

## 11. Common errors and how to avoid them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| List is missing elements | Wrong index, skipped index, or higher-precedence source overrides entire List | Use contiguous indices from 0; check profiles and configuration sources. |
| `List<Endpoint>` lacks expected properties | Misspelled `[i].field` or wrong YAML indentation | Compare flattened keys against the Java structure. |
| Map loses `/` in keys | Missing `[key]` notation | Write `app.routes.[/api/v1]` or YAML `"[/api/v1]"`. |
| Map has nested key `a → b` instead of literal key `a.b` | Using `Map<String,Object>` and omitting `[a.b]` | Use bracket notation for keys with dots when literal preservation is needed. |
| `dev` config loses base elements | List is replaced wholesale by higher source | Declare the full desired List in the profile file or model data as a Map if key-based merging is needed. |
| Boolean/numeric value fails to bind | Value cannot convert to target type | Check Java type and configuration string; quote YAML when preserving special strings. |
| YAML not loaded via `@PropertySource` | Default annotation does not support loading YAML directly | Use `application.yaml` via Config Data or an appropriate loader. |
| Two formats yield unexpected results | Same location has both `application.properties` and `application.yaml` | Choose one format; in the same location, `.properties` takes precedence over YAML per Spring Boot rules. |

Practical tips:

- **Quote strings in YAML:** wrap URLs, strings containing `:#{}[]`, or values easily coerced to another type in quotes to make intent clear. Keys like `"[/path]"` must be quoted when using bracket notation.
- **Never use tabs to indent YAML.** Spaces and `-` alignment determine element levels.
- **Name consistently:** use lowercase kebab-case property names such as `connect-timeout` and `routes-by-region`, and let the Binder map them to Java camelCase.
- **Do not depend on Map iteration order** for business logic unless an ordering contract is guaranteed; for lists, element order is part of the meaning.
- **Avoid manually concatenating strings** from multiple sources to build configuration: let the Spring Boot Binder apply collection and precedence rules.
- **Never place secrets** such as API tokens in examples, logs, or source control; secret configuration should come from a secret management mechanism appropriate for the runtime environment.

## 12. Quick reference table

| Data type | `application.properties` | `application.yaml` | Common Java type |
| --- | --- | --- | --- |
| List of scalars | `app.regions[0]=vn`, `app.regions[1]=sg` | `regions: [vn, sg]` | `List<String>` |
| List of objects | `app.endpoints[0].name=primary` | `endpoints:` then `- name: primary` | `List<Endpoint>` |
| Map of scalars | `app.labels.team=platform` | `labels:` then `team: platform` | `Map<String,String>` |
| Map of objects | `app.backends.billing.base-url=...` | `backends:` → `billing:` → `base-url: ...` | `Map<String,Backend>` |
| Special Map key | `app.routes.[/api/v1]=billing` | `routes:` → `"[/api/v1]": billing` | `Map<String,String>` |
| Map containing Lists | `app.routes-by-region.vn[0].name=primary` | `routes-by-region:` → `vn:` → `- name: primary` | `Map<String,List<Endpoint>>` |

**Rule to remember:** **Lists are positional** (`[index]`) and when overridden by a higher-precedence source they **replace the entire list**; **Maps are keyed** and can **merge entries/properties** across sources; to preserve keys with special characters, use **`[key]`** and quote the key in YAML.

## 13. References

- Spring Boot **3.3** Reference – *Externalized Configuration*, sections *Working With YAML*, *Mapping YAML to Properties*, *Relaxed Binding*, *Binding Maps*, *Binding From Environment Variables*, and *Merging Complex Types*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3** Reference – *Type-safe Configuration Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
