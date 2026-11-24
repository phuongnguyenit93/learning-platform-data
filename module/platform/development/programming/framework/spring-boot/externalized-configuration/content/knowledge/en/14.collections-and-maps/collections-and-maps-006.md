# Binding Maps with Scalar Values or Complex Objects in Spring Boot 3.3

## 1. Goal and Core Idea

When configuring a Spring Boot application, not every group of properties has a fixed list of keys. Sometimes a service needs configuration keyed by tenant name, deployment region, endpoint name, application labels, or an extensible set of providers. `Map<K,V>` in `@ConfigurationProperties` is the right tool to express a configuration group where **key names vary dynamically with data**.

There are two important cases:

- **Maps with scalar values:** each key maps to a single value such as `String`, `Integer`, `Boolean`, `Duration`, or an enum. For example `Map<String,String>` for labels, or `Map<String,Integer>` for retry limits.
- **Maps with complex object values:** each key maps to an object containing multiple properties, potentially including child objects, `List`s, and nested `Map`s. For example `Map<String,ClientProperties>`, where each client has `baseUrl`, `connectTimeout`, and `enabled`.

These two forms **differ in how segments after dots in the property path are interpreted**, how the binder creates values, the extent to which getters/setters are required, and how configuration is combined across PropertySources.

**Core example:**

```properties
app.labels.team=platform
app.labels.region=ap-southeast-1

app.clients.billing.base-url=https://billing.example.test
app.clients.billing.connect-timeout=3s
app.clients.billing.enabled=true

app.clients.inventory.base-url=https://inventory.example.test
app.clients.inventory.connect-timeout=5s
app.clients.inventory.enabled=false
```

From this, the Java model can be:

```java
private Map<String, String> labels;
private Map<String, ClientProperties> clients;
```

Conceptual result:

```text
labels:
  team        -> "platform"
  region      -> "ap-southeast-1"

clients:
  billing:
    baseUrl        -> https://billing.example.test
    connectTimeout -> PT3S
    enabled        -> true
  inventory:
    baseUrl        -> https://inventory.example.test
    connectTimeout -> PT5S
    enabled        -> false
```

The Spring Boot Binder uses the property path structure and the **declared Java type** to decide how to interpret each branch.

## 2. Why Use `@ConfigurationProperties` Instead of Parsing `Environment` Manually?

Spring Boot 3.3 includes a dedicated `Binder` for externalized configuration. When you declare:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private Map<String, String> labels = new LinkedHashMap<>();
    // getters/setters...
}
```

Spring Boot can:

1. Read data from `application.properties` or YAML files, environment variables, JVM system properties, and CLI.
2. Match the prefix `app` and property `labels` using **relaxed binding**.
3. Discover entries such as `app.labels.team` and `app.labels.region`.
4. Create or update entries in the `Map`.
5. Convert values to the target type, such as `"3s"` to `Duration`.
6. Combine keys from relevant PropertySources according to precedence.
7. Apply validation if the configuration bean is registered for validation.

Calling `getProperty("app.labels.team")` directly is only convenient when you already know the key name `team`. If keys can be `payments`, `analytics`, or `client-42` added by operators, declaring a `Map` lets the Binder discover the key set automatically instead of scanning every configuration source manually.

**Note:** `Map` only makes key names dynamic; it does not guarantee values will always bind properly if the Java type is unsuitable, keys get sanitized, or sources contain conflicting configuration.

## 3. Comparison Table of Common Map Types

| Java type | Value content | Example config path | Notes |
| --- | --- | --- | --- |
| `Map<String,String>` | Scalar string | `app.labels.team=platform` | Keys containing `.` can be preserved in scalar Map form |
| `Map<String,Integer>` | Integer | `app.limits.billing=5` | `0` is a valid number; unparseable text values can fail |
| `Map<String,Boolean>` | Boolean | `app.flags.cache=false` | `false` is data, not an indicator of a missing entry |
| `Map<String,Duration>` | Duration | `app.timeouts.billing=750ms` | Requires type conversion |
| `Map<String,ClientProperties>` | JavaBean with multiple fields | `app.clients.billing.base-url=...` | `billing` is the key; `base-url` is a field of the value |
| `Map<String,Map<String,String>>` | Map nested inside Map | `app.labels-by-team.sales.owner=Mai` | Two levels of dynamic keys |
| `Map<String,List<String>>` | Map containing List | `app.permissions.billing[0]=read` | List binding rules also apply |
| `Map<String,Object>` | Dynamic, potentially nested values | `app.metadata.a.b=value` | Unbracketed dots can create nested Maps |
| `Map<Enum,Something>` | Enum key | `app.tiers.gold=...` | Key must be convertible to the corresponding enum |

All examples assume `@ConfigurationProperties` types are registered, configuration files reside in locations discovered by Boot, and no higher-priority PropertySource overrides them otherwise.

## 4. Example 1 — `Map<String,String>` Holding Scalar Values

Create a JavaBean in `src/main/java/com/example/demo/config/ServiceProperties.java`:

```java
package com.example.demo.config;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public class ServiceProperties {

    private Map<String, String> labels = new LinkedHashMap<>();

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }
}
```

File `src/main/resources/application.properties`:

```properties
service.labels.owner=core-team
service.labels.region=ap-southeast-1
service.labels.stage=staging
```

Equivalent YAML:

```yaml
service:
  labels:
    owner: core-team
    region: ap-southeast-1
    stage: staging
```

After binding:

```java
properties.getLabels().get("owner");  // "core-team"
properties.getLabels().get("region"); // "ap-southeast-1"
properties.getLabels().get("stage");  // "staging"
```

There is no need to declare separate Java fields for `owner`, `region`, or `stage`; they are **keys of the Map**, not fixed properties of `ServiceProperties`.

### 4.1. A Map Can Have Arbitrary Keys — Subject to Syntax Rules

For example, needing a label named `source-system`:

```properties
service.labels.source-system=crm
```

The hyphen `-` is valid in Map keys under standard syntax. If a key contains other special characters, you must apply bracket notation `[key]` as covered later.

### 4.2. Typed Values Still Undergo Conversion

Change the Java type:

```java
private Map<String, Integer> retryLimits = new LinkedHashMap<>();

public Map<String, Integer> getRetryLimits() {
    return retryLimits;
}

public void setRetryLimits(Map<String, Integer> retryLimits) {
    this.retryLimits = retryLimits;
}
```

Configuration:

```properties
service.retry-limits.billing=3
service.retry-limits.analytics=0
service.retry-limits.search=5
```

Result:

```text
billing   -> 3 (Integer)
analytics -> 0 (Integer)
search    -> 5 (Integer)
```

`0` is an explicit value, which can mean **no retries**. The Binder does not drop the entry simply because its value is zero.

Similarly:

```java
private Map<String, Boolean> featureFlags = new LinkedHashMap<>();
```

```properties
service.feature-flags.new-search=true
service.feature-flags.old-checkout=false
```

`false` is still stored as an entry with key `old-checkout`, not treated as an instruction to skip or delete the key.

### 4.3. `Duration`, `DataSize`, and Enums Are Scalars for Binding Purposes

```java
private Map<String, Duration> timeouts = new LinkedHashMap<>();
```

```properties
service.timeouts.billing=500ms
service.timeouts.inventory=2s
```

The Binder can convert `500ms` and `2s` into `Duration` without a nested JavaBean. Likewise, convertible types such as enums or `DataSize` can serve as Map values; when conversion fails, startup may fail rather than silently skipping the key.

## 5. Example 2 — `Map<String,ClientProperties>` Holding Complex Objects

When each entry needs multiple properties, replace `String` with a class.

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public class GatewayProperties {

    private Map<String, Client> clients = new LinkedHashMap<>();

    public Map<String, Client> getClients() {
        return clients;
    }

    public void setClients(Map<String, Client> clients) {
        this.clients = clients;
    }

    public static class Client {
        private String baseUrl;
        private Duration connectTimeout = Duration.ofSeconds(2);
        private boolean enabled = true;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
```

`.properties` configuration:

```properties
gateway.clients.billing.base-url=https://billing.example.test
gateway.clients.billing.connect-timeout=3s
gateway.clients.billing.enabled=true

gateway.clients.inventory.base-url=https://inventory.example.test
gateway.clients.inventory.connect-timeout=1s
gateway.clients.inventory.enabled=false
```

Equivalent YAML:

```yaml
gateway:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 3s
      enabled: true
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 1s
      enabled: false
```

**How to read the property path:**

```text
gateway.clients.billing.connect-timeout
   |       |      |          |
 prefix  Map    Map key     Client.connectTimeout

gateway.clients.inventory.enabled
   |       |      |          |
 prefix  Map    Map key     Client.enabled
```

When the Binder sees `Map<String,Client>`, the `billing` segment does not become a Java field of `GatewayProperties`. It is a dynamic Map key. The `connect-timeout` segment is relaxed-bound to the `connectTimeout` field **inside** the corresponding `Client` object.

### 5.1. Field Initializers in the Child Object

In this example, each `Client` has:

```java
private Duration connectTimeout = Duration.ofSeconds(2);
private boolean enabled = true;
```

If configuration for `gateway.clients.billing` only includes `base-url`, the Binder can create `Client` and preserve defaults `connectTimeout=2s` and `enabled=true`. If the file specifies:

```properties
gateway.clients.billing.enabled=false
gateway.clients.billing.connect-timeout=0ms
```

then `false` and `0ms` are explicit values; defaults are not reused.

### 5.2. Using the Bound Object

```java
GatewayProperties.Client billing =
        gatewayProperties.getClients().get("billing");

if (billing != null && billing.isEnabled()) {
    Duration timeout = billing.getConnectTimeout();
    String baseUrl = billing.getBaseUrl();
    // Use the values to build the client.
}
```

If `get("billing")` returns `null`, there is no bound entry for that key; do not call `billing.getBaseUrl()` without checking first. If the application requires the `billing` key, validate after binding.

## 6. Key Difference: Dots in Map Keys

Spring Boot 3.3 interprets Map keys based on the **value type** and `[key]` syntax. A dot `.` can either be part of a scalar Map key or act as a nested object boundary.

### 6.1. `Map<String,String>` — Dots Can Stay Inside the Key

Suppose:

```java
private Map<String, String> values = new LinkedHashMap<>();
```

Config:

```properties
app.values.a.b=hello
```

When binding a `Map<String,String>`, the key can be preserved intact as `"a.b"` with value `"hello"`:

```text
values = {"a.b": "hello"}
```

This is documented by Spring Boot for Maps with **scalar values**, such as `Map<String,String>`. Dots do not necessarily indicate a new nesting level in this case.

### 6.2. `Map<String,Object>` — Dots Can Create Nested Levels

Change the Java type:

```java
private Map<String, Object> values = new LinkedHashMap<>();
```

The same config:

```properties
app.values.a.b=hello
```

can be interpreted as nested structured data:

```text
values:
  a:
    b: hello
```

That is, entry `"a"` contains a child Map with entry `"b"`, which is **different** from the literal key `"a.b"`.

### 6.3. Preserving Keys Containing Dots with Brackets

If you must preserve the exact key name `a.b`, use `[a.b]`:

```properties
app.values.[a.b]=hello
```

In YAML, brackets must be wrapped in quotes:

```yaml
app:
  values:
    "[a.b]": hello
```

This is explicit when the target type is `Map<String,Object>`, or when you want to prevent ambiguity if a Map's value type changes later.

**Comparison table:**

| Target type | Input | Bound key/structure |
| --- | --- | --- |
| `Map<String,String>` | `app.values.a.b=hello` | Can be key `"a.b"` → `"hello"` |
| `Map<String,Object>` | `app.values.a.b=hello` | Can be `"a"` → child Map `"b"` |
| `Map<String,Object>` | `app.values.[a.b]=hello` | Literal key `"a.b"` |
| `Map<String,String>` | `app.values.[a.b]=hello` | Literal key `"a.b"` |

With `Map<String,Client>`, segments after the key are typically treated as child properties of `Client`. If the key itself contains a dot, such as `eu.west`, use `gateway.clients.[eu.west].base-url` to mark the key boundary.

## 7. Bracket Notation to Preserve Map Keys Containing Special Characters

A Map key might be:

- A path: `/api/v1`
- A dotted string: `eu.west`
- A name containing `_` or characters outside the usual key character set.
- A name containing both `/` and `.` at the same time: `/hooks/v2.public`.

According to Spring Boot, if you do not wrap the key in `[]`, characters other than alphanumeric characters, `-`, or `.` can be stripped from the key name during binding. This can unintentionally collapse two distinct keys into the same name.

### 7.1. `.properties` Syntax

```properties
gateway.routes.[/api/v1]=billing
gateway.routes.[/api/v2]=inventory
gateway.routes.[/hooks/v2.public]=webhook
```

Correspondingly:

```text
routes.get("/api/v1")        -> "billing"
routes.get("/api/v2")        -> "inventory"
routes.get("/hooks/v2.public")-> "webhook"
```

Writing without brackets:

```properties
gateway.routes./api/v1=billing
```

can cause `/` characters to be stripped, producing key `"apiv1"` instead of `"/api/v1"`. That is a data bug with business impact if Map keys represent routing paths.

### 7.2. YAML Syntax

```yaml
gateway:
  routes:
    "[/api/v1]": billing
    "[/api/v2]": inventory
    "[/hooks/v2.public]": webhook
```

In YAML, **you must quote keys using bracket notation**. Do not rely on:

```yaml
gateway:
  routes:
    [/api/v1]: billing
```

to achieve the same semantics. YAML has flow collection syntax using `[ ]`, so keys expressed in bracket notation need to be placed inside quoted strings.

### 7.3. Special Map Keys When the Value Is an Object

```properties
gateway.clients.[tenant/eu].base-url=https://eu.example.test
gateway.clients.[tenant/eu].enabled=true
```

YAML equivalent:

```yaml
gateway:
  clients:
    "[tenant/eu]":
      base-url: https://eu.example.test
      enabled: true
```

The Map key is `"tenant/eu"`, while `base-url` and `enabled` are properties of the child object.

### 7.4. Dotted Map Keys with Child Objects

```properties
gateway.clients.[eu.west].base-url=https://eu-west.example.test
gateway.clients.[eu.west].connect-timeout=5s
```

Do not write:

```properties
gateway.clients.eu.west.base-url=https://eu-west.example.test
```

if the intent is **a single key `eu.west`**: unbracketed `eu` and `west` segments can be interpreted as deeper nesting and fail to bind into `Client` as intended.

## 8. Nested Maps (Map Inside Map)

Not every complex Map value needs to be a JavaBean. You can use `Map<String,Map<String,String>>`.

```java
@ConfigurationProperties(prefix = "access")
public class AccessProperties {

    private Map<String, Map<String, String>> policies =
            new LinkedHashMap<>();

    public Map<String, Map<String, String>> getPolicies() {
        return policies;
    }

    public void setPolicies(
            Map<String, Map<String, String>> policies) {
        this.policies = policies;
    }
}
```

YAML file:

```yaml
access:
  policies:
    billing:
      read: role-billing-read
      write: role-billing-admin
    inventory:
      read: role-inventory-read
      write: role-inventory-admin
```

Data paths:

```text
policies["billing"]["read"]    = "role-billing-read"
policies["billing"]["write"]   = "role-billing-admin"
policies["inventory"]["read"]  = "role-inventory-read"
policies["inventory"]["write"] = "role-inventory-admin"
```

`.properties` form:

```properties
access.policies.billing.read=role-billing-read
access.policies.billing.write=role-billing-admin
access.policies.inventory.read=role-inventory-read
access.policies.inventory.write=role-inventory-admin
```

Here `policies` is the outer Map, `billing`/`inventory` are first-level keys, and `read`/`write` are second-level keys. The Java type tells the Binder that each level should be a Map.

If an inner key contains `/` or special characters, bracket notation still applies:

```properties
access.policies.billing.[/reports/export]=role-exporter
```

## 9. Maps Containing Lists or Objects Containing Lists

An example of role sets per tenant:

```java
@ConfigurationProperties(prefix = "tenants")
public class TenantProperties {

    private Map<String, List<String>> roles = new LinkedHashMap<>();

    public Map<String, List<String>> getRoles() {
        return roles;
    }

    public void setRoles(Map<String, List<String>> roles) {
        this.roles = roles;
    }
}
```

YAML:

```yaml
tenants:
  roles:
    billing:
      - READ
      - WRITE
    analytics:
      - READ
```

`.properties`:

```properties
tenants.roles.billing[0]=READ
tenants.roles.billing[1]=WRITE
tenants.roles.analytics[0]=READ
```

When bound, `roles.get("billing")` can be `["READ", "WRITE"]`; `roles.get("analytics")` is `["READ"]`.

Similarly, a complex Map value can contain a List:

```java
public static class Client {
    private List<String> allowedMethods = new ArrayList<>();

    public List<String> getAllowedMethods() {
        return allowedMethods;
    }

    public void setAllowedMethods(List<String> allowedMethods) {
        this.allowedMethods = allowedMethods;
    }
}
```

```properties
gateway.clients.billing.allowed-methods[0]=GET
gateway.clients.billing.allowed-methods[1]=POST
```

Remember that **Map merging** and **List replacement** are two different rules. When a List property is defined in multiple PropertySources/profiles, Spring Boot typically takes the List from the higher-priority source instead of concatenating Lists across sources, whereas a Map can retain non-overlapping keys.

## 10. Map Merging Across Multiple PropertySources

Spring Boot supports Map binding across different PropertySources. A Map can combine keys appearing across multiple sources, while duplicate keys use the value from the higher-priority source.

### 10.1. Scalar-Valued Map: Merging by Key

Suppose common configuration in `application.yaml`:

```yaml
app:
  labels:
    owner: platform
    environment: base
```

Higher-priority configuration, such as `application-prod.yaml` when the `prod` profile is active:

```yaml
app:
  labels:
    environment: production
    cost-center: cc-42
```

The resulting Map is typically:

```text
owner       -> platform
environment -> production
cost-center -> cc-42
```

Reason: key `owner` is absent from the higher source so it is kept from the lower source; `environment` collides so the higher-priority value wins; `cost-center` is added from the higher source.

This is not an unconditional merge behavior for every Java construct. It is **Map binding** behavior in Spring Boot, applied through the Binder and PropertySource ordering.

### 10.2. Object-Valued Map: Combining Fields

Common configuration:

```yaml
# application.yaml
gateway:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
      enabled: true
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 4s
```

Production configuration:

```yaml
# application-prod.yaml
gateway:
  clients:
    billing:
      connect-timeout: 10s
      enabled: false
    payments:
      base-url: https://payments.example.test
      connect-timeout: 3s
```

When the `prod` profile is active, the Map configuration can yield:

```text
billing:
  baseUrl        = https://billing.example.test   # common source
  connectTimeout = 10s                            # prod source
  enabled        = false                          # prod source

inventory:
  baseUrl        = https://inventory.example.test # common source
  connectTimeout = 4s                             # common source
  enabled        = true                           # field initializer

payments:
  baseUrl        = https://payments.example.test  # prod source
  connectTimeout = 3s                             # prod source
  enabled        = true                           # field initializer
```

Using a JavaBean as a Map value lets child fields of the same key come from different sources. For instance, `billing.base-url` is not wiped out just because `application-prod.yaml` overrides `billing.connect-timeout`. However, **when child fields are Lists**, List replacement rules still apply separately.

### 10.3. Config Data Precedence and External Sources

Typical precedence order for the same property: command-line arguments can take precedence over Java system properties, OS environment variables, and Config Data files (in standard Boot setups). For example:

```properties
# application.properties
gateway.clients.billing.connect-timeout=2s
```

```bash
java -jar myapp.jar \
  --gateway.clients.billing.connect-timeout=8s
```

The command-line property can set `billing.connectTimeout=8s`. Other properties of `billing` can still come from Config Data if not overridden.

**Subtle detail:** Map keys can be normalized differently depending on the source type, especially environment variables, so two keys that look different in input do not necessarily produce two independent entries.

## 11. Environment Variables for Maps: Syntax and Limitations

Spring Boot 3.3 supports relaxed binding with environment variables. To convert a canonical property name to an environment variable:

1. Replace dots `.` with `_`.
2. Remove dashes `-`.
3. Uppercase everything.

Examples:

```text
gateway.clients.billing.connect-timeout
→ GATEWAY_CLIENTS_BILLING_CONNECTTIMEOUT

gateway.clients.billing.enabled
→ GATEWAY_CLIENTS_BILLING_ENABLED

service.retry-limits.analytics
→ SERVICE_RETRYLIMITS_ANALYTICS
```

Declaration:

```bash
GATEWAY_CLIENTS_BILLING_CONNECTTIMEOUT=750ms \
GATEWAY_CLIENTS_BILLING_ENABLED=false \
SERVICE_RETRYLIMITS_ANALYTICS=0 \
java -jar myapp.jar
```

The `billing`/`analytics` Map keys are extracted from the corresponding segment of the variable name. For **Maps bound from environment variables**, Spring Boot normalizes Map keys to **lowercase**, so do not rely on OS environment variables to preserve a distinction between `Billing` and `billing`.

### 11.1. Map Keys with Dots, Slashes, or Special Characters

For a key like `"/api/v1"`, it is not straightforward to encode bracket notation and `/` characters in standard environment variable names. If a key truly needs to preserve a URL path, route pattern, or dotted label, **using Config Data (.properties/YAML) with `[key]`** is usually clearer and safer.

For example:

```properties
gateway.routes.[/api/v1]=billing
```

Do not turn it into `GATEWAY_ROUTES_API_V1` and assume the Map key will reconstruct `/api/v1` accurately. Relaxed binding cannot arbitrarily reverse-infer characters that were removed.

### 11.2. Case-Sensitive Map Keys

If business logic requires two separate keys `"US-East"` and `"us-east"`, environment variables are not suitable for preserving this distinction once Spring Boot normalizes Map keys. Use a source that preserves key casing, or change the key model (for example a normalized enum) according to business needs.

### 11.3. Containers and CI

Kubernetes/Compose can supply environment variables for scalar and object Map values, for example:

```yaml
services:
  gateway:
    image: example/gateway:1.0
    environment:
      GATEWAY_CLIENTS_BILLING_CONNECTTIMEOUT: "750ms"
      GATEWAY_CLIENTS_BILLING_ENABLED: "false"
```

Text values are converted by the Binder to `Duration` and `boolean` when target types match. When debugging, separate environment-variable naming mistakes from value conversion errors.

## 12. Map Keys with Enum or Numeric Types

### 12.1. Enum Keys

Suppose a fixed set of service tiers:

```java
public enum Tier {
    FREE, STANDARD, PREMIUM
}
```

```java
@ConfigurationProperties(prefix = "plan")
public class PlanProperties {

    private Map<Tier, Integer> quotas =
            new EnumMap<>(Tier.class);

    public Map<Tier, Integer> getQuotas() {
        return quotas;
    }

    public void setQuotas(Map<Tier, Integer> quotas) {
        this.quotas = quotas;
    }
}
```

File:

```properties
plan.quotas.free=100
plan.quotas.standard=1000
plan.quotas.premium=10000
```

The Binder converts Map keys to the enum type using the appropriate conversion service. A key that cannot be converted to the `Tier` enum can cause binding to fail. Enum keys make sense when the key set is known and fixed, whereas `Map<String, ...>` fits tenants/providers that may be added dynamically.

### 12.2. Numeric Keys and YAML

With `Map<String,String>`:

```yaml
app:
  http-status-labels:
    "200": success
    "404": not-found
```

Quoting the numbers makes it explicit for YAML to treat keys as `"200"` strings rather than relying on the YAML parser's scalar type inference.

If using `Map<Integer,String>`, the target key type is `Integer` and gets converted when supported by the Binder. Choose a key type that matches how code looks up entries; do not declare `Map<String,...>` and then look up keys using an `Integer`.

## 13. `Map<String,Object>` Is Dynamic Configuration, Not a Schema-Backed JavaBean

`Map<String,Object>` can be handy when configuration holds arbitrary keys and multi-level nesting, though it trades away part of **type safety**.

For example:

```java
@ConfigurationProperties(prefix = "app")
public class DynamicProperties {

    private Map<String, Object> metadata =
            new LinkedHashMap<>();

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }
}
```

YAML:

```yaml
app:
  metadata:
    service:
      name: catalog
      replicas: 3
    owner: platform
```

In the resulting Map, `metadata.get("service")` can be a nested Map rather than a custom JavaBean. Consuming code must understand the actual runtime types and perform proper checks/casts.

If the inner structure is known, switch to:

```java
Map<String, ServiceMetadata>
```

with:

```java
public static class ServiceMetadata {
    private String name;
    private int replicas;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getReplicas() { return replicas; }
    public void setReplicas(int replicas) {
        this.replicas = replicas;
    }
}
```

That way the Binder can perform type conversion, code gets IDE support, and validation on nested objects becomes much easier to express.

**Do not assume** `Object` will always be a `String` or always an `Integer` across every type of PropertySource. When exact semantics are required, declare typed values instead of relying on raw `Object`.

## 14. Getter-Only Maps and Pre-Initialized Maps

In JavaBean binding, a pre-initialized Map with a getter can usually be populated by the Binder **without requiring a setter**.

```java
@ConfigurationProperties(prefix = "app")
public class LabelsProperties {

    private final Map<String, String> labels =
            new LinkedHashMap<>();

    public Map<String, String> getLabels() {
        return labels;
    }
}
```

Spring Boot can use the getter to retrieve the existing Map and bind entries from `app.labels.*`. `setLabels(Map<...>)` is not required if the Binder can mutate the existing Map.

However, this **requires a mutable Map**:

```java
// Not suitable if Binder needs to add entries to the Map.
private final Map<String, String> labels = Map.of();
```

`Map.of()` returns an immutable Map. Do not provide an immutable getter-only Map and expect the Binder to add keys by mutation.

Safe options:

```java
private final Map<String, String> labels =
        new LinkedHashMap<>();
```

Or use a field with a setter so the Binder has a way to assign a new Map instance:

```java
private Map<String, String> labels =
        new LinkedHashMap<>();

public Map<String, String> getLabels() {
    return labels;
}

public void setLabels(Map<String, String> labels) {
    this.labels = labels;
}
```

**Nested object values** in a Map must satisfy standard JavaBean binding requirements: the child class needs an appropriate way to instantiate it and setters for scalar properties. If the value is an immutable constructor-bound class, register and structure it in a form properly supported by the Binder.

### Maps Pre-Populated with Initial Values

```java
private Map<String, String> labels =
        new LinkedHashMap<>(Map.of(
            "owner", "default-team",
            "region", "global"
        ));
```

Initial values can serve as defaults for unoverridden entries, though when the Binder binds a Map from config sources there can be merge/replace behaviors depending on the object type and how it is assigned. If the application strictly requires "every default key must always exist", define an explicit merge policy in the application layer and write tests rather than assuming every Map type and binding style preserves the exact reference and all initial entries.

## 15. Constructor Binding and Records Containing Maps

Spring Boot 3.3 also allows declaring configuration in an immutable style instead of JavaBean setters.

```java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayConfig(
        Map<String, Endpoint> clients) {

    public record Endpoint(
            URI baseUrl,
            Duration connectTimeout,
            boolean enabled) {
    }
}
```

YAML:

```yaml
gateway:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 3s
      enabled: true
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 1s
      enabled: false
```

The Binder can construct `Endpoint` from the specified fields and pass the resulting Map into the `GatewayConfig` record. This avoids setters, though it comes with important differences:

- There are no JavaBean field initializers in a record to hold defaults.
- If a property is not provided, the constructor argument may need a default or validation depending on design.
- Use `@DefaultValue` as supported by Spring Boot for constructor-bound properties when explicit defaults are needed.
- For a `Map` with immutable nested values, verify all required fields before consuming them.

A Java record only guarantees that **the record field reference** is immutable; a Map passed in can still be mutable unless defensively copied. If immutability of the Map itself is required, the application can copy it in the constructor after binding according to its own rules.

When using constructor binding, register the class via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` as appropriate; do not assume constructor binding automatically applies to beans created via plain `@Component` or `@Bean`.

## 16. Registering `@ConfigurationProperties` Properly

An annotated class is not automatically a bean unless it is registered.

### Option 1 — `ConfigurationPropertiesScan`

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

Scans `@ConfigurationProperties` classes in the target package, including JavaBean Map properties like `GatewayProperties`.

### Option 2 — `EnableConfigurationProperties`

```java
@SpringBootApplication
@EnableConfigurationProperties(GatewayProperties.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Requires importing `org.springframework.boot.context.properties.EnableConfigurationProperties`. This registers the specific class explicitly.

### Option 3 — `@Component` with JavaBean Binding

```java
@Component
@ConfigurationProperties(prefix = "gateway")
public class GatewayProperties {
    // JavaBean getters, setters, Map...
}
```

Suitable for mutable JavaBeans instantiated by Spring as regular beans. Do not use `@Component` expecting constructor binding to be picked up the way configuration-properties scanning does.

Do not carelessly combine `@Component` and scan/enable on the same class; avoid duplicate bean registration.

## 17. Validation for Scalar-Valued and Object-Valued Maps

Configuration can load cleanly yet still be invalid in business terms. For example, an endpoint missing `base-url`, a negative timeout, or a Map lacking a mandatory provider.

Use Jakarta Bean Validation with `@Validated`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public class ValidatedGatewayProperties {

    @NotEmpty
    @Valid
    private Map<String, Client> clients =
            new LinkedHashMap<>();

    public Map<String, Client> getClients() {
        return clients;
    }

    public void setClients(Map<String, Client> clients) {
        this.clients = clients;
    }

    public static class Client {

        @NotBlank
        private String baseUrl;

        @NotNull
        private Duration connectTimeout;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }
    }
}
```

**Meaning:**

- `@NotEmpty` on the Map: must contain at least one entry.
- `@Valid`: triggers cascading validation into value objects held in the Map (depending on validator and registration).
- `@NotBlank`: `baseUrl` must not be missing, empty, or whitespace-only.
- `@NotNull`: `connectTimeout` must have a value.

In a Spring Boot 3.3 project, `spring-boot-starter-validation` is usually needed if the classpath does not already include a Jakarta Validation provider.

### 17.1. Constraints on Keys and Values

Java Bean Validation supports container element constraints, such as:

```java
private Map<@NotBlank String, @NotNull String> labels;
```

This enforces constraints on Map keys/values at the Java type level. Validation requires a compatible Bean Validation provider and a properly validated bean. If keys can contain `/`, do not apply a regex pattern that forbids slashes when the application actually needs them.

### 17.2. Validating Required Keys

`@NotEmpty` only ensures the Map is non-empty; it does not require a specific key to be present:

```java
if (!clients.containsKey("billing")) {
    throw new IllegalStateException(
            "Missing gateway.clients.billing configuration");
}
```

You can place this logic in a configuration validation layer or use a suitable custom validator. Also verify that the `Client` value is non-null if your data representation can produce nulls.

### 17.3. Do Not Use Validation to Mask Syntax Errors

If a Map key contains `/` and loses the slash due to missing bracket notation, `@NotBlank` on the value can still pass. Write keys with the correct syntax directly in the config file:

```properties
gateway.clients.[tenant/eu].base-url=https://eu.example.test
```

Validation checks the validity of bound objects; it does not repair keys that were mis-normalized.

## 18. Missing Keys, Empty Strings, Zero, and `false` in Maps

Map binding preserves configuration value semantics:

```properties
app.labels.display-name=
app.limits.analytics=0
app.flags.legacy=false
```

Cases:

- `app.labels.display-name=`: key `display-name` can exist with `String ""`.
- `app.limits.analytics=0`: key `analytics` has value `Integer 0`.
- `app.flags.legacy=false`: key `legacy` has value `Boolean false`.
- Key absent from every source: typically has no entry in the bound Map unless code supplies a default.

Do not blindly write:

```java
if (!flags.get("legacy")) {
    // ...
}
```

if `flags.get("legacy")` can be null; unboxing a null `Boolean` throws `NullPointerException`. Choose an explicit policy:

```java
boolean enabled = Boolean.TRUE.equals(
        flags.get("legacy"));
```

or:

```java
Boolean configured = flags.get("legacy");

if (configured == null) {
    // Key not configured.
} else if (configured) {
    // Explicitly enabled.
} else {
    // Explicitly disabled.
}
```

With `Map<String, Integer>`, do not treat zero as "undeclared" if zero is a valid value. `null`, absence, and value `0` can carry different meanings.

### Scalar Maps and Keys Containing Dots

If a scalar Map uses a key like `a.b` and you want an unambiguous distinction between the literal key `"a.b"` and nested data, consider bracket notation right from the start:

```properties
app.labels.[a.b]=value
```

This keeps configuration resilient if `Map<String,String>` is later refactored to `Map<String,Object>`.

## 19. Using a Map in a Real Service

Example Spring service using a Map to look up a client by tenant code:

```java
package com.example.demo.service;

import com.example.demo.config.GatewayProperties;
import com.example.demo.config.GatewayProperties.Client;

import org.springframework.stereotype.Service;

@Service
public class ClientRouter {

    private final GatewayProperties gatewayProperties;

    public ClientRouter(GatewayProperties gatewayProperties) {
        this.gatewayProperties = gatewayProperties;
    }

    public Client route(String clientName) {
        Client client = gatewayProperties.getClients().get(clientName);

        if (client == null) {
            throw new IllegalArgumentException(
                    "Unknown client configuration: " + clientName);
        }

        if (!client.isEnabled()) {
            throw new IllegalStateException(
                    "Client is disabled: " + clientName);
        }

        return client;
    }
}
```

Using `Map<String,Client>` lets you add `notifications`/`payments` keys purely via configuration without adding corresponding Java fields. Still, the service must validate requested keys and ensure arbitrary client names cannot trigger unsafe behavior if Maps are loaded from untrusted sources.

**Security note:** If Map values hold credentials, tokens, or secrets, never log the entire `getClients()` map. For Spring Actuator `/actuator/configprops` and `/actuator/env`, restrict exposure and ensure proper sanitization so sensitive configuration is never exposed publicly.

## 20. Unit/Integration Testing Map Binding

A `@SpringBootTest` test can verify that multiple Map entries bind into the expected Java types:

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;

import com.example.demo.config.GatewayProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "gateway.clients.billing.base-url=https://billing.example.test",
        "gateway.clients.billing.connect-timeout=3s",
        "gateway.clients.billing.enabled=true",
        "gateway.clients.[tenant/eu].base-url=https://eu.example.test",
        "gateway.clients.[tenant/eu].enabled=false"
})
class GatewayPropertiesTest {

    @Autowired
    GatewayProperties gatewayProperties;

    @Test
    void bindsSimpleAndComplexMapValues() {
        GatewayProperties.Client billing =
                gatewayProperties.getClients().get("billing");

        assertNotNull(billing);
        assertEquals("https://billing.example.test",
                billing.getBaseUrl());
        assertEquals(Duration.ofSeconds(3),
                billing.getConnectTimeout());
        assertTrue(billing.isEnabled());

        GatewayProperties.Client eu =
                gatewayProperties.getClients().get("tenant/eu");
        assertNotNull(eu);
        assertFalse(eu.isEnabled());
    }
}
```

This test assumes `GatewayProperties` is registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, and no higher-priority source alters the relevant keys.

When testing multiple PropertySources, account for precedence: `@SpringBootTest(properties=...)` usually adds test properties with higher priority than standard application files. If you need to test multi-source merging logic precisely, construct a dedicated test `Environment` containing PropertySources in a known order.

### Isolated Testing with `ApplicationContextRunner`

When writing auto-configuration or a component library, `ApplicationContextRunner` from `spring-boot-test` conveniently spins up an isolated context with explicit property values:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

class GatewayBindingRunnerTest {

    @Test
    void readsBillingClient() {
        new ApplicationContextRunner()
                .withUserConfiguration(GatewayConfig.class)
                .withPropertyValues(
                    "gateway.clients.billing.base-url=https://billing.example.test",
                    "gateway.clients.billing.enabled=false")
                .run(context -> {
                    GatewayProperties props =
                            context.getBean(GatewayProperties.class);
                    assertFalse(
                        props.getClients().get("billing").isEnabled());
                });
    }

    @EnableConfigurationProperties(GatewayProperties.class)
    static class GatewayConfig { }
}
```

Add the appropriate static assertion import, such as `org.junit.jupiter.api.Assertions.assertFalse`. This snippet illustrates the test flow; real projects may need additional auto-configurations depending on their components.

## 21. Troubleshooting When a Map Does Not Bind Correctly

When you observe an empty `Map` or unexpected keys/values, check step by step:

1. **Is the prefix right?** For instance `@ConfigurationProperties(prefix="gateway")` only targets `gateway.*` paths.
2. **Is the bean registered?** `@ConfigurationProperties` alone does not turn a class into a bean without proper scanning, enabling, or bean registration.
3. **Is the JavaBean property name right?** `clients` must be visible to the Binder as a property via getter/setter or constructor parameter.
4. **Is the Map mutable?** A getter-only Map needs a mutable instance; avoid `Map.of()` when relying on mutation.
5. **Does the value type match?** `Map<String,String>` has different semantics from `Map<String,Object>` and `Map<String,Client>`.
6. **Does the key contain dots or slashes?** Use `[key]`; YAML requires quoting `"[key]"`.
7. **Does the value object have valid setters or constructor?** Nested scalar properties cannot bind into an immutable object lacking an appropriate construction mechanism.
8. **Is there a conversion error?** `Duration` accepts `750ms`, `5s`; a string like `never` fails to parse.
9. **Have you accounted for PropertySource precedence?** A higher-priority source may override keys or nested properties.
10. **Is there a List inside?** Lists follow replacement rules rather than Map merging.
11. **Are environment variables named using canonical relaxed binding?** `-` removed, `.` turned into `_`; Map keys can become lowercase.
12. **Is validation failing startup?** `@NotBlank`/`@NotEmpty`/`@Valid` can reject objects missing required data.
13. **Was the config file actually loaded by Boot?** Check `spring.config.location`, `spring.config.additional-location`, profiles, and `spring.config.import` if used.
14. **Are unrecognized properties silently ignored?** The default `ignoreUnknownFields` setting on `@ConfigurationProperties` can hide typos quietly; standardize schemas, generate metadata, and write tests.

### Diagnostic Snippet for Runtime Map Values

```java
@Configuration
class GatewayDiagnostics {

    @Bean
    ApplicationRunner showClients(GatewayProperties properties) {
        return args -> {
            for (String client : properties.getClients().keySet()) {
                GatewayProperties.Client value =
                        properties.getClients().get(client);

                System.out.println("Configured client key: " + client);
                System.out.println("Enabled: " + value.isEnabled());
            }
        };
    }
}
```

Required imports:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
```

Only log keys and safe fields when needed. Never dump secrets, passwords, API tokens, or unsanitized Maps.

## 22. Common Mistakes

### Mistake 1 — Dots in Keys Misinterpreted

```properties
app.metadata.a.b=value
```

If the target is `Map<String,Object>` and you need the exact key `"a.b"`, use:

```properties
app.metadata.[a.b]=value
```

### Mistake 2 — Slashes Stripped from Path Keys

```properties
gateway.routes./api/v1=billing
```

Use:

```properties
gateway.routes.[/api/v1]=billing
```

### Mistake 3 — Unquoted Brackets in YAML

```yaml
routes:
  [/api/v1]: billing
```

Use:

```yaml
routes:
  "[/api/v1]": billing
```

### Mistake 4 — Assuming Lists Merge Like Maps

The base file has `roles.billing=[READ,WRITE]` and the prod file has `roles.billing=[ADMIN]`. The List value can become `[ADMIN]` from the higher-priority source rather than `[READ,WRITE,ADMIN]`. Maps combine keys; Lists are not guaranteed to concatenate.

### Mistake 5 — Complex Map Value Missing Setter

```java
public static class Client {
    private String baseUrl;
    public String getBaseUrl() { return baseUrl; }
}
```

If using JavaBean binding for `Client`, add `setBaseUrl(...)` or switch to appropriate constructor binding. A valid Map key cannot compensate for an un-updatable value object.

### Mistake 6 — Map Initialized with `Map.of()`

```java
private final Map<String, String> labels = Map.of();
public Map<String, String> getLabels() { return labels; }
```

When the Binder needs to insert entries into a getter-only Map, an immutable Map refuses mutation. Use `new LinkedHashMap<>()` or another setter/binding style.

### Mistake 7 — Expecting Environment Variables to Preserve Complex Key Names

```text
GATEWAY_ROUTES_API_V1=billing
```

This name lacks enough information to reconstruct the key `"/api/v1"`. Use a Config Data file with `[/api/v1]`.

### Mistake 8 — Using `@Value` to Auto-Bind a Complex Map

```java
@Value("${gateway.clients}")
private Map<String, GatewayProperties.Client> clients;
```

This is not how Spring is designed to bind a complex Map value object from `gateway.clients.billing.base-url`... Use `@ConfigurationProperties` and the Binder for nested structures.

### Mistake 9 — Treating `false` or `0` as an Absent Key

```properties
gateway.clients.billing.enabled=false
app.retry-limits.billing=0
```

Both values are explicit and should not revert to defaults or drop the entry when they carry operational meaning.

### Mistake 10 — Assuming a Map Entry in a Profile Clears All Base Fields

A Map object can receive child fields from multiple sources. Declaring only `enabled=false` in a higher-priority profile does not automatically clear `base-url` from the common source. If business logic must block using an entry, check the `enabled` flag or implement explicit removal rules.

### Mistake 11 — Removing a Key from a Higher Source Thinking It Deletes It from the Map

If the key still exists in a lower-priority PropertySource, the Binder can still pick it up from there. Do not treat "deleting a line in the prod file" as globally deleting that key from the merged configuration.

### Mistake 12 — Value Objects Left Unvalidated

The Binder can instantiate `Client` with `baseUrl` as `null`. If callers require non-empty values, use `@NotBlank` with cascading `@Valid` on the Map, or check after binding.

## 23. Decision Table: Which Map Type to Choose?

| Need | Suitable Java type | Config syntax |
| --- | --- | --- |
| Arbitrary labels, one String each | `Map<String,String>` | `app.labels.team=platform` |
| Numeric limits per service | `Map<String,Integer>` | `app.limits.billing=5` |
| Feature toggles per tenant | `Map<String,Boolean>` | `app.flags.billing=false` |
| Timeouts per endpoint | `Map<String,Duration>` | `app.timeouts.billing=2s` |
| Multiple clients with URL/timeout/flag | `Map<String,Client>` | `app.clients.billing.base-url=...` |
| Role sets per client | `Map<String,List<String>>` | `app.roles.billing[0]=READ` |
| Arbitrary nested keys under outer key | `Map<String,Map<String,String>>` | `app.policies.billing.read=role-a` |
| Dynamic config with unknown schema | `Map<String,Object>` | `app.metadata.service.name=...` |
| Fixed tier set defined by enum | `Map<Tier,Integer>` | `app.quotas.free=100` |
| Keys containing slashes | `Map<String,?>` | `app.routes.[/api/v1]=...` |
| Keys containing literal dots to preserve | `Map<String,?>` | `app.metadata.[eu.west]=...` |

When values have a stable schema, prefer a typed JavaBean/record over `Object` to gain type conversion, validation, and clear metadata.

## 24. Implementation Checklist

- [ ] Determine whether Map keys are truly dynamic data or fixed fields of a single object.
- [ ] Choose the right value type: scalar, typed JavaBean/record, List, or nested Map.
- [ ] Declare `@ConfigurationProperties` with a valid lowercase kebab-case prefix.
- [ ] Register the bean via `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or proper bean registration.
- [ ] For JavaBeans, provide getters/setters for scalars and child objects as appropriate.
- [ ] Initialize getter-only Maps with a mutable instance when mutation is needed.
- [ ] Use bracket notation `[key]` for special Map keys.
- [ ] In YAML, quote bracketed keys as `"[key]"`.
- [ ] For `Object` or complex nested Map values, handle the dot semantics in keys properly.
- [ ] For deployment environments, name OS variables using the canonical formula: dot → underscore, dash → remove, uppercase.
- [ ] Do not rely on environment variables to preserve slashes or significant letter casing in keys.
- [ ] Distinguish multi-source Map merging from List replacement.
- [ ] Define clear policies for missing keys, empty Strings, `0`, and `false`.
- [ ] Validate complex values and required keys per business rules.
- [ ] Write tests for bracket notation, profile overrides, typed conversion, and source precedence.
- [ ] Never log secrets; protect configuration diagnostic endpoints.
- [ ] For important dynamic key names, document allowed formats in operations guides to avoid key collisions after normalization.

## 25. References

- Spring Boot **3.3 Reference — Externalized Configuration**, sections *Type-safe Configuration Properties*, *Binding Maps*, *Merging Complex Types*, *Relaxed Binding*, *Binding From Environment Variables*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3 API — @ConfigurationProperties**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot **3.3 API — Binder**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot **3.3 Reference — Configuration Metadata**: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- Spring Framework Reference — `Environment` and `PropertySource`: https://docs.spring.io/spring-framework/reference/core/beans/environment.html

**Key takeaway:** `Map<String,String>` holds scalars and can preserve dots inside keys; `Map<String,Object>` or `Map<String,Client>` interprets dots as nested structure. Use **`[key]`** to preserve special Map keys, use **typed JavaBeans/records** for multi-field values, and remember that Spring Boot can **merge Maps by key/field across multiple PropertySources**, while **Lists are typically replaced** according to precedence.
