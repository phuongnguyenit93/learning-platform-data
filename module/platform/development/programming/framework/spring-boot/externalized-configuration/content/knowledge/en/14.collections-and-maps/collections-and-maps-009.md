# Distinguishing Dots in Map Keys from Object Paths When Binding Spring Boot Configuration

## 1. The Problem: The Same Dot Can Carry Two Different Meanings

Spring Boot lets you bind properties in `application.yml`, `application.properties`, environment variables, and other configuration sources into Java classes via `@ConfigurationProperties`. A flattened property name commonly contains dots:

~~~properties
app.client.timeout=5s
app.labels.api.example.com=catalog
app.tenants.[team.alpha].timeout=8s
~~~

On the surface, all three lines use the `.` character. Yet their meanings are not identical:

- `app.client.timeout`: dots separate object nesting levels `app` → `client` → `timeout`.
- `app.labels.api.example.com`: if `labels` is bound as `Map<String, String>`, the `api.example.com` portion can be **a single Map key**.
- `app.tenants.[team.alpha].timeout`: `tenants` is a Map with object-typed values; the square brackets protect key `team.alpha`, while the dot after `]` starts the `timeout` property on the mapped object.

Without distinguishing these, an application can bind the wrong type, lose Map keys, fail to look up settings, or ignore values deployers thought they provided.

Lesson goals:

1. Understand that dots are interpreted by the Binder according to the **target type**, not solely by string patterns.
2. Distinguish **nested object paths** from **Map keys containing dots**.
3. Know when **`[key.with.dot]`** syntax is mandatory or recommended.
4. Write proper YAML/properties for `Map<String,String>`, `Map<String,Object>`, and `Map<String, CustomType>`.
5. Diagnose and test configurations containing domain names, tenant IDs, group names, or strings with special characters.

This lesson focuses on Spring Boot 3.x binding, especially `@ConfigurationProperties` and `ConfigurationPropertyName`; verify exact details against your Spring Boot version.

## 2. From YAML to Flattened Property Names

Suppose `application.yml` contains:

~~~yaml
app:
  http:
    client:
      connect-timeout: 5s
      max-retries: 3
~~~

Structurally in YAML, this is a multi-level nested mapping. Spring Boot evaluates equivalent property paths:

~~~properties
app.http.client.connect-timeout=5s
app.http.client.max-retries=3
~~~

With a Java class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(Http http) {
    public record Http(Client client) {}
    public record Client(Duration connectTimeout, int maxRetries) {}
}
~~~

Each dot steps through `http`, `client`, `connectTimeout`, and `maxRetries`. This is an **object property path**.

If you replace `http` with a Map:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        java.util.Map<String, String> http
) {}
~~~

the Binder no longer treats `http` as a Java class having a `client` property. The remainder of the path can become a **Map key**, depending on the Map's value type. Thus, **with the exact same flattened data, changing the Java model can change how key boundaries are interpreted**.

Do not infer that every dot appearing in a property name must correspond to a level of Java objects.

## 3. Distinguishing by Target Type

Consider several Java models:

| Target type | Property name | Typical interpretation |
| --- | --- | --- |
| Nested bean `Client client` | `app.client.timeout` | `timeout` is a property on the `client` object |
| `Map<String, String> labels` | `app.labels.api.example.com` | `api.example.com` can be one complete key |
| `Map<String, Integer> limits` | `app.limits.service.alpha` | With scalar values, `service.alpha` can stay a single key |
| `Map<String, Object> extras` | `app.extras.user.role` | Can build a nested Map structure via segments `user` and `role` |
| `Map<String, TenantPolicy> tenants` | `app.tenants.[team.alpha].timeout` | Map key is `team.alpha`; `timeout` is a field of `TenantPolicy` |

**Spring Boot's key rule:** for Maps with **scalar values** (such as `Map<String, String>`), dots in the key portion can be preserved automatically without requiring square brackets. For non-scalar values such as `Map<String, Object>` or a configuration object with child fields, dots can be treated as nested paths; if you truly want dots inside the Map key, use **bracket notation**.

In the context of Spring Boot documentation, scalars include simple types such as enums and types in `java.lang`, excluding `Object`. Do not extend that exception to arbitrary custom classes or collections.

Remember: **a Map key does not automatically start at the last dot**. The Binder relies on property-name structure, parameter/field types, and binding rules to determine boundaries.

## 4. Case 1: `Map<String, String>` with Keys Containing Dots

An application wants to map hostnames to internal service names:

~~~yaml
app:
  host-aliases:
    api.example.com: catalog
    images.example.com: media
    auth.example.org: identity
~~~

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record HostAliasProperties(
        Map<String, String> hostAliases
) {}
~~~

The flattened property names can be viewed as:

~~~properties
app.host-aliases.api.example.com=catalog
app.host-aliases.images.example.com=media
app.host-aliases.auth.example.org=identity
~~~

With `Map<String, String>`, the Binder can retain `api.example.com` as **one Map key** instead of turning it into an object with `api` → `example` → `com`.

Expected result:

~~~java
Map<String, String> hosts = properties.hostAliases();

hosts.get("api.example.com");      // "catalog"
hosts.get("images.example.com");   // "media"
hosts.get("auth.example.org");     // "identity"
~~~

Notice that even if YAML is written as:

~~~yaml
app:
  host-aliases:
    api:
      example:
        com: catalog
~~~

it can still flatten into `app.host-aliases.api.example.com`. When the target type is `Map<String,String>`, the Binder can treat `api.example.com` as a scalar Map key. Therefore, **YAML layout alone is not enough to determine Map results**; you must inspect the Java type.

Even though dots can be kept automatically in scalar Maps, bracket notation expresses intent more clearly when a key is meant to remain an intact identifier:

~~~yaml
app:
  host-aliases:
    "[api.example.com]": catalog
    "[images.example.com]": media
~~~

`[ ]` inside YAML keys must be wrapped in quotes so the YAML parser reads it as a **key string**, not flow sequence/collection syntax.

## 5. Case 2: Nested Objects Use Dots as Paths

Suppose we need to configure an HTTP client:

~~~yaml
app:
  client:
    connection:
      timeout: 3s
      max-connections: 20
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(Client client) {
    public record Client(Connection connection) {}
    public record Connection(Duration timeout, int maxConnections) {}
}
~~~

Here the names:

~~~properties
app.client.connection.timeout=3s
app.client.connection.max-connections=20
~~~

mean:

~~~text
app
 └─ client                      Client object
     └─ connection             Connection object
         ├─ timeout            Duration
         └─ max-connections    int
~~~

There is no Map at `app.client` or `app.client.connection`. Hence `connection.timeout` is not a Map key. The Binder must traverse the corresponding properties/nested types.

This creates a clean boundary:

- `Map<String,String>`: segments after the Map name can be combined into a scalar key.
- Nested Java objects: each segment maps to a Java property; there are no arbitrary Map keys.

If you want arbitrary per-client names like `team.alpha`, the Java model should use a Map:

~~~java
public record AppProperties(
        java.util.Map<String, Client> clients
) {
    public record Client(Duration timeout, int maxConnections) {}
}
~~~

and declare dotted keys with square brackets as shown next.

## 6. Case 3: `Map<String, CustomType>` and Dotted Keys

A multi-tenant application has tenant IDs `team.alpha` and `team.beta`. Each tenant has a timeout and an enable/disable flag.

Configuration:

~~~yaml
app:
  tenants:
    "[team.alpha]":
      enabled: true
      timeout: 5s
    "[team.beta]":
      enabled: false
      timeout: 9s
~~~

Java:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record TenantProperties(
        Map<String, TenantPolicy> tenants
) {
    public record TenantPolicy(
            boolean enabled,
            Duration timeout
    ) {}
}
~~~

Flattened property names:

~~~properties
app.tenants.[team.alpha].enabled=true
app.tenants.[team.alpha].timeout=5s
app.tenants.[team.beta].enabled=false
app.tenants.[team.beta].timeout=9s
~~~

Result:

~~~java
TenantProperties.TenantPolicy alpha =
        properties.tenants().get("team.alpha");

boolean enabled = alpha.enabled();        // true
Duration timeout = alpha.timeout();        // PT5S
~~~

Let's break down the path:

~~~text
app.tenants.[team.alpha].timeout
│   │        │            │
│   │        │            └── field "timeout" of TenantPolicy
│   │        └─────────────── intact key "team.alpha"
│   └──────────────────────── Map field name "tenants"
└──────────────────────────── prefix "app"
~~~

If brackets are omitted:

~~~properties
app.tenants.team.alpha.timeout=5s
~~~

then `team`, `alpha`, and `timeout` can be interpreted by the Binder as nested path segments. With `Map<String, TenantPolicy>`, that is **not a reliable way to pass key `team.alpha`**: the Binder may try binding key `team` to an object and then look for property `alpha`, whereas `TenantPolicy` only has `enabled` and `timeout`.

The outcome can be a binding failure, an ignored property, or unexpected objects depending on types and binder settings. Do not guess a fixed behavior: explicitly write the key with square brackets.

## 7. Bracket Notation Syntax: `[key]`

Spring Boot supports bracket notation for Map keys that must stay intact:

~~~text
map-name.[literal.key].field
map-name.[/literal/key].field
map-name.[some:key].field
~~~

Form in `application.properties`:

~~~properties
app.tenants.[team.alpha].timeout=5s
app.tenants.[team.beta].timeout=9s
app.labels.[api.example.com]=catalog
~~~

Form in `application.yml`:

~~~yaml
app:
  tenants:
    "[team.alpha]":
      timeout: 5s
    "[team.beta]":
      timeout: 9s
  labels:
    "[api.example.com]": catalog
~~~

### Two Syntax Layers to Distinguish

1. **YAML syntax:** bracketed keys should be **quoted** like `"[team.alpha]"` so they form valid string keys.
2. **Spring Boot binding syntax:** `[ ]` signals that the contents are a **Map key to preserve**, rather than regular path segments.

Writing:

~~~yaml
app:
  tenants:
    team.alpha:
      timeout: 5s
~~~

is not reliably equivalent to:

~~~yaml
app:
  tenants:
    "[team.alpha]":
      timeout: 5s
~~~

when the value type of `tenants` is a custom class.

### Is a Dot Needed Before the Bracket?

In property names, you may see both examples using `map.[key]` and index syntax directly attached to the Map segment. In application code and documentation, a readable and common style is:

~~~properties
app.tenants.[team.alpha].timeout=5s
~~~

What matters is not dot placement around brackets, but that **the dotted key is enclosed completely inside the brackets**. Pick one consistent convention and test binding on your target version.

## 8. Scalar Maps vs. `Map<String, Object>`

Here is an easily overlooked exception. Consider a flat property:

~~~properties
app.metadata.user.role=reader
~~~

With:

~~~java
@ConfigurationProperties(prefix = "app")
public record MetadataProperties(
        java.util.Map<String, String> metadata
) {}
~~~

the value type is `String`. The Binder can keep the key as:

~~~text
metadata["user.role"] = "reader"
~~~

However, with:

~~~java
@ConfigurationProperties(prefix = "app")
public record MetadataProperties(
        java.util.Map<String, Object> metadata
) {}
~~~

`Object` is not included in the scalar group eligible for automatic dot preservation. The path `user.role` can be interpreted as a nested Map structure:

~~~text
metadata
  └─ user
      └─ role = "reader"
~~~

instead of a single entry with key `user.role`.

If the requirement is to **keep the literal key** even when the Map value is declared `Object`, use brackets:

~~~properties
app.metadata.[user.role]=reader
~~~

or:

~~~yaml
app:
  metadata:
    "[user.role]": reader
~~~

In multi-level structures with mixed types, `Map<String, Object>` adds flexibility yet makes key parsing harder to predict. When the schema is fixed, consider using **nested records or classes** rather than a generic `Object` Map.

### Why Is `Object` Special?

Do not conclude that "because `Object` accepts anything, it counts as scalar". In Spring Boot's Map binding rules, `Object` is an **exception** compared to standard scalar types in `java.lang`. Consequently, the generic value type `Object` in `Map<String, Object>` causes dots to be treated as nested map structure.

If you change `Map<String, String>` to `Map<String, Object>` during a refactor, review all dotted keys and add bracket notation in configuration when keys must stay verbatim.

## 9. Special Characters Beyond Dots: Slashes, Colons, and Spaces

Besides dots, Map keys may contain:

- URL paths: `/api/v1`.
- Resource names: `/metrics/prometheus`.
- Identifiers with colons: `region:asia`.
- Symbolic characters used by external systems.

For example:

~~~yaml
app:
  route-permissions:
    "[/api/v1]": read
    "[/internal/health]": monitor
    "[tenant:premium]": write
~~~

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RouteProperties(
        Map<String, String> routePermissions
) {}
~~~

When bound with bracket notation:

~~~java
routeProperties.routePermissions().get("/api/v1");          // "read"
routeProperties.routePermissions().get("/internal/health"); // "monitor"
routeProperties.routePermissions().get("tenant:premium");   // "write"
~~~

If you remove brackets from a key containing slashes:

~~~yaml
app:
  route-permissions:
    /api/v1: read
~~~

characters outside the allowed property-name character set can be stripped or normalized during binding, making the Map key **differ from the original string**. By Spring Boot's Map naming rules, unbracketed keys do not fully preserve characters other than alphanumeric characters, hyphens, and dots.

Therefore:

- Dotted key with a **scalar Map value**: brackets may be optional, though brackets still clarify intent.
- Key containing `/` or symbols that must stay verbatim: **use brackets**.
- Dotted key with an **object/non-scalar Map value**: **use brackets** to avoid path interpretation.

For keys containing spaces or unusual symbols, mind both YAML quoting rules and Binder key-preservation rules. Do not guess escape rules from another language's syntax.

## 10. Object Paths Inside a Map: Which Dots Are Real Paths?

An object-valued Map still relies on dots to reach fields on that value object.

For example:

~~~yaml
app:
  queues:
    "[priority.high]":
      consumer:
        concurrency: 6
        poll-timeout: 2s
    "[priority.low]":
      consumer:
        concurrency: 2
        poll-timeout: 10s
~~~

Java:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record QueueProperties(Map<String, Queue> queues) {
    public record Queue(Consumer consumer) {}

    public record Consumer(
            int concurrency,
            Duration pollTimeout
    ) {}
}
~~~

Flattened names:

~~~properties
app.queues.[priority.high].consumer.concurrency=6
app.queues.[priority.high].consumer.poll-timeout=2s
app.queues.[priority.low].consumer.concurrency=2
app.queues.[priority.low].consumer.poll-timeout=10s
~~~

In `app.queues.[priority.high].consumer.poll-timeout`:

1. `app` is the prefix of `QueueProperties`.
2. `queues` is the `Map<String, Queue>` field.
3. `[priority.high]` is **one Map key**.
4. `consumer` is a field of `Queue`.
5. `poll-timeout` is a field of `Consumer`.

A single property expression containing multiple dots can contain both **literal dots inside a key** and **object-hierarchy dots**. Brackets tell the Binder exactly which boundaries the developer wants preserved.

### Why Not Just Replace Dots with Underscores?

For tenant key `priority.high`, changing it to `priority_high` creates a **different identifier**. If external systems look up the original dotted tenant ID, altering the key corrupts data.

Brackets preserve the key name as a unit without forcing changes to business identifiers.

## 11. Example: Same Property Name, Different Java Types Give Different Results

Suppose there is only one line:

~~~properties
app.flags.feature.alpha=true
~~~

**Approach A — Bind to a scalar Map:**

~~~java
@ConfigurationProperties(prefix = "app")
public record FlagMapProperties(
        java.util.Map<String, Boolean> flags
) {}
~~~

`Boolean` is a scalar type. `feature.alpha` can stay a single Map key, giving effectively:

~~~java
flags.get("feature.alpha"); // true
~~~

**Approach B — Bind to nested objects:**

~~~java
@ConfigurationProperties(prefix = "app")
public record FlagObjectProperties(Flags flags) {
    public record Flags(Feature feature) {}
    public record Feature(boolean alpha) {}
}
~~~

Now `flags` is an object, `feature` is a child object, and `alpha` is a boolean field. This is an entire property path, not a Map key.

**Approach C — Bind to an object-valued Map:**

~~~java
@ConfigurationProperties(prefix = "app")
public record FlagPolicyProperties(
        java.util.Map<String, FeaturePolicy> flags
) {
    public record FeaturePolicy(boolean enabled) {}
}
~~~

If the intended key is `feature.alpha` and the value object has field `enabled`, the old line no longer describes the binding target. Write:

~~~properties
app.flags.[feature.alpha].enabled=true
~~~

Takeaway: decide the target data model **before writing property names**. No generic dot-splitting rule can substitute for the Binder's type-aware behavior across all cases.

## 12. Using `@ConfigurationProperties` Properly to Verify

A complete example with both Map styles:

~~~yaml
# src/main/resources/application.yml
demo:
  host-aliases:
    "[api.example.com]": catalog
    "[images.example.com]": media
  tenants:
    "[team.alpha]":
      enabled: true
      timeout: 5s
    "[team.beta]":
      enabled: false
      timeout: 10s
~~~

Java record:

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        Map<String, String> hostAliases,
        Map<String, TenantSettings> tenants
) {
    public record TenantSettings(
            boolean enabled,
            Duration timeout
    ) {}
}
~~~

Register via scanning:

~~~java
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
~~~

Service using the bean:

~~~java
package com.example.demo.service;

import com.example.demo.config.DemoProperties;
import org.springframework.stereotype.Service;

@Service
public class RoutingService {

    private final DemoProperties properties;

    public RoutingService(DemoProperties properties) {
        this.properties = properties;
    }

    public String routeForHost(String host) {
        return properties.hostAliases().get(host);
    }

    public boolean tenantEnabled(String tenantId) {
        DemoProperties.TenantSettings settings =
                properties.tenants().get(tenantId);
        return settings != null && settings.enabled();
    }
}
~~~

When called:

~~~java
routeForHost("api.example.com");      // "catalog"
tenantEnabled("team.alpha");          // true
tenantEnabled("team.beta");           // false
~~~

Through `Map<String, String>` and `Map<String, TenantSettings>`, you can see both kinds of dotted keys preserved as intended.

In Spring Boot 3.x, a `@ConfigurationProperties` record with an appropriate constructor is implicitly constructor-bound when registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. Do not put `@Component` directly on this record.

## 13. Using `application.properties` Instead of YAML

The same example can be written as:

~~~properties
demo.host-aliases.[api.example.com]=catalog
demo.host-aliases.[images.example.com]=media

demo.tenants.[team.alpha].enabled=true
demo.tenants.[team.alpha].timeout=5s

demo.tenants.[team.beta].enabled=false
demo.tenants.[team.beta].timeout=10s
~~~

The benefit of `.properties` is seeing the exact flattened names processed by the Binder. For a dotted key, the part inside brackets is treated as a unit:

~~~text
demo.tenants.[team.alpha].timeout
             └──────────┘
                 Map key
~~~

Do not change it to:

~~~properties
demo.tenants.team.alpha.timeout=5s
~~~

and expect an identical result. The unbracketed form can represent nested object paths rather than Map key `team.alpha`.

### When Can Brackets Be Omitted?

For `demo.host-aliases` of type `Map<String, String>`:

~~~properties
demo.host-aliases.api.example.com=catalog
~~~

key `api.example.com` can be preserved because the Map value is scalar.

Still, if you are writing long-lived configuration or might refactor the value type into an object later, bracket syntax makes "this is a dotted key" explicit and reduces guesswork.

## 14. Warning: Map Keys and Relaxed Binding Are Not the Same Thing

Spring Boot provides **relaxed binding**, allowing property names such as:

~~~text
demo.client.connect-timeout
demo.client.connectTimeout
DEMO_CLIENT_CONNECTTIMEOUT
~~~

to map to the same `connectTimeout` field across appropriate configuration contexts.

However, Map keys are often **meaningful domain data**, such as:

~~~text
api.example.com
team.alpha
/metrics
priority.high
~~~

Do not assume every property-name normalization preserves every character of a Map key. This is particularly critical for:

- Dots `.`.
- Slashes `/`.
- Letter casing in identifiers.
- Whitespace.
- Colons or special symbols.
- Key names that could be mistaken for object paths.

Brackets express which key segment should be preserved inside a property name, while each source type also enforces **its own naming and escaping rules**.

For example, OS environment variables generally do not support names containing `.` or `[ ]` the same way `.properties` files do. For complex Map keys, prefer YAML/properties files or another suitable structured format rather than inventing arbitrary environment variable names and expecting the Binder to reconstruct original characters.

## 15. Dotted Map Keys via Environment Variables: Do Not Convert Mechanically

Example property in a file:

~~~properties
demo.tenants.[team.alpha].timeout=5s
~~~

A basic recipe for converting a **standard property name** into an environment variable replaces dots with `_`, removes hyphens, and uppercases. That recipe **does not automatically preserve bracket boundaries and literal dots inside keys**.

If you mechanically turn it into:

~~~text
DEMO_TENANTS_TEAM_ALPHA_TIMEOUT
~~~

the information that "`team.alpha` is one single Map key" is lost. The variable name looks like a multi-level hierarchy and should not be assumed to bind into the intended Map entry.

Design options:

1. When Map keys are arbitrary identifiers containing dots, **place configuration in YAML/properties** using bracket notation.
2. If environment variables are mandatory, consider changing the **schema** so keys use env-friendly characters while storing the original identifier in a field, or use a structured configuration property parsed explicitly by the application.
3. If using `SPRING_APPLICATION_JSON` or a Config Data source supporting structured data, check how that source represents keys and how the Binder receives property names; do not extrapolate from simple variable names.
4. Write integration tests matching your real deployment environment (shell, Docker, Kubernetes).

Example schema avoiding dotted Map keys:

~~~yaml
demo:
  tenants:
    team-alpha:
      external-id: "team.alpha"
      enabled: true
      timeout: 5s
~~~

Java can bind under internal key `team-alpha` while treating `external-id` as data. Such a schema change is an **intentional design decision**, not an automatic equivalence when external systems rely on the original key name.

Never silently rename business keys if other systems reference the original identifier.

## 16. YAML Quoting and Why Bare Brackets Should Not Be Written

In YAML, `[ ]` carries special meaning for flow sequences. So when you want a key string `[team.alpha]`, wrap it in quotes:

~~~yaml
demo:
  tenants:
    "[team.alpha]":
      enabled: true
~~~

Single quotes work as well:

~~~yaml
demo:
  tenants:
    '[team.alpha]':
      enabled: true
~~~

Do not write:

~~~yaml
demo:
  tenants:
    [team.alpha]:
      enabled: true
~~~

assuming the YAML parser reads it as an ordinary scalar key. Depending on context, that can parse as a different construct or fail as invalid syntax.

Quotes **do not become part of the Map key** after the YAML parser decodes the string. The string passed to the Binder is `[team.alpha]`, where bracket notation denotes key `team.alpha`.

### Do Not Place Brackets in the Wrong Spot

Two different names:

~~~properties
demo.tenants.[team.alpha].enabled=true
demo.tenants.team.[alpha].enabled=true
~~~

The first denotes a single key `team.alpha`. The second brackets `alpha` after a `team` segment, potentially yielding a different structure depending on target types. **Wrap the entire key you want preserved**, not just the segment after a dot.

## 17. Do Not Confuse Map Brackets with List Index Brackets

Spring Boot also uses square brackets to represent list elements:

~~~yaml
demo:
  endpoints:
    - name: first
      url: "https://first.example.org"
    - name: second
      url: "https://second.example.org"
~~~

Property names:

~~~properties
demo.endpoints[0].name=first
demo.endpoints[0].url=https://first.example.org
demo.endpoints[1].name=second
demo.endpoints[1].url=https://second.example.org
~~~

Difference:

| Expression | Bound to matching type | Meaning |
| --- | --- | --- |
| `endpoints[0]` | `List<Endpoint>` | Element at index 0 of the list |
| `tenants.[team.alpha]` | `Map<String, Tenant>` | String key `team.alpha` of the Map |
| `labels.[api.example.com]` | `Map<String, String>` | Key `api.example.com` |
| `routes.[/api/v1]` | `Map<String, String>` | Key `/api/v1` |

The distinction comes from **the target type and position in the path**. You cannot infer a List merely by spotting square brackets.

A Map with string key `"0"` differs conceptually from a List at index `0`. If your configuration schema uses numeric keys, choose explicit Java types and add tests to eliminate ambiguity.

## 18. Effect of Profiles and `PropertySource` Precedence

Suppose the common file is:

~~~yaml
# application.yml
demo:
  host-aliases:
    "[api.example.com]": catalog-default
    "[images.example.com]": media-default
~~~

Production profile file:

~~~yaml
# application-prod.yml
demo:
  host-aliases:
    "[api.example.com]": catalog-prod
~~~

When the `prod` profile is active and no higher-priority source exists, the value for key `api.example.com` comes from the profile file, while key `images.example.com` keeps its value from the common file:

~~~text
api.example.com    → catalog-prod
images.example.com → media-default
~~~

Map binding can combine **entries with different keys** across multiple PropertySources when structure permits; for identical keys, the higher-priority source usually wins. Still, **do not equate Maps with Lists**: when binding a list across multiple sources, the higher-priority list typically replaces lower-priority lists instead of merging element by element.

For instance, if another source omits brackets:

~~~properties
demo.host-aliases.api.example.com=override
~~~

with `Map<String, String>`, both notations can point to the same key `api.example.com`. Yet if the Map changes to `Map<String,Object>` or a Map of custom objects, that assumption is no longer safe.

### Dotted Keys Configured Across Multiple Sources

Do not inspect only the final value; check whether **all sources express the exact same key**.

For example:

~~~properties
demo.tenants.[team.alpha].timeout=5s
~~~

and:

~~~properties
demo.tenants.team.alpha.timeout=8s
~~~

must not be assumed to reliably override one another in a Map of custom objects. Brackets alter how keys bind, so whether two sources target the same entry must be verified against the actual target type.

## 19. Binding a Map Nested in an Object vs. an Object Nested in a Map

These two structures differ substantially.

### 19.1. An Object Containing a Map

~~~yaml
demo:
  routing:
    enabled: true
    destinations:
      "[api.example.com]": catalog
      "[images.example.com]": media
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(Routing routing) {
    public record Routing(
            boolean enabled,
            java.util.Map<String, String> destinations
    ) {}
}
~~~

Path:

~~~text
demo.routing.destinations.[api.example.com]
│    │       │            └── Map key
│    │       └─────────────── Map field
│    └─────────────────────── nested Routing object
└──────────────────────────── prefix
~~~

### 19.2. A Map Containing Objects

~~~yaml
demo:
  routing:
    "[api.example.com]":
      enabled: true
      destination: catalog
    "[images.example.com]":
      enabled: false
      destination: media
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        java.util.Map<String, Route> routing
) {
    public record Route(boolean enabled, String destination) {}
}
~~~

Path:

~~~text
demo.routing.[api.example.com].destination
│    │       │                 └── field Route.destination
│    │       └──────────────────── key of Map
│    └──────────────────────────── routing Map
└───────────────────────────────── prefix
~~~

The difference is **the type of `routing`**. In the first model, `routing` is an object and `destinations` is a Map inside it. In the second model, `routing` itself is the Map and each entry holds a `Route` object.

If you copy YAML from one model onto Java classes from the other, the Binder will not construct the expected objects. Check the actual data schema before tuning dot notation.

## 20. Bug Caused by Switching from `Map<String, String>` to `Map<String, Object>`

Suppose an application originally has:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(java.util.Map<String, String> tags) {}
~~~

And configuration:

~~~properties
demo.tags.security.level=high
demo.tags.app.version=1.2
~~~

Originally the developer wanted two entries:

~~~text
tags["security.level"] = "high"
tags["app.version"]     = "1.2"
~~~

Later they change the generic value type to `Object` to "support more data types":

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(java.util.Map<String, Object> tags) {}
~~~

If property names stay unchanged, the Binder can create a nested Map structure instead of dotted keys:

~~~text
tags
  security
    level = high
  app
    version = 1.2
~~~

This can break calling code:

~~~java
properties.tags().get("security.level");
~~~

Correct property syntax after refactoring:

~~~properties
demo.tags.[security.level]=high
demo.tags.[app.version]=1.2
~~~

Also evaluate whether `Object` is truly needed. If all values are text, keeping `Map<String,String>` is simpler and less ambiguous.

What looks like a tiny generic type change can be a **configuration schema change**. Write tests to verify binding before deploying.

## 21. Bugs from Keys Containing Slashes Being Stripped or Mangled

Suppose an application maps HTTP paths to permissions:

~~~properties
demo.permissions./api/v1=read
demo.permissions./admin/write=write
~~~

The author expects Map keys to keep `/api/v1` and `/admin/write`. However, `/` characters are not preserved as regular property-name segments when brackets are missing.

Explicit syntax:

~~~properties
demo.permissions.[/api/v1]=read
demo.permissions.[/admin/write]=write
~~~

Equivalent in YAML:

~~~yaml
demo:
  permissions:
    "[/api/v1]": read
    "[/admin/write]": write
~~~

For keys used in access control or routing logic, losing slashes can cause lookups to fail or routes to map incorrectly.

Distinguish **key binding correctness** from **access-policy security**: even when the Binder reads the Map properly, the application must still enforce proper security principles rather than treating a sample config file as a complete authorization mechanism.

## 22. When a Property Path Resembles a Literal Key

Suppose:

~~~properties
demo.metadata.region.code=VN
~~~

There are at least three interpretations depending on the Java model:

**A. Nested object**

~~~java
record Metadata(Region region) {}
record Region(String code) {}
~~~

`region.code` is a field path.

**B. Scalar Map**

~~~java
Map<String, String> metadata
~~~

`region.code` can be an intact key inside the Map.

**C. Map with custom object values**

~~~java
Map<String, RegionInfo> metadata
record RegionInfo(String code) {}
~~~

If you want key `region` and property `code`, `demo.metadata.region.code=VN` can fit. However, if you want literal key `region.code`, you need a field on the value object, such as:

~~~properties
demo.metadata.[region.code].display-name=Vietnam
~~~

with `Map<String, RegionInfo>` where `RegionInfo` has field `displayName`.

Ask yourself:

- "Is `region` a key name or a field name?"
- "Does `code` belong to the value object or inside the key?"
- "Is the Map value a scalar or an object?"
- "Which dots must stay literal?"

If you cannot answer those four questions, it is easy to write property names that are syntactically valid yet wrong for your data model.

## 23. Diagnosing with `@ConfigurationProperties` and Small Tests

Instead of guessing how the Binder will split dots, write a small Spring Boot test to verify.

Example configuration:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record MapBindingProperties(
        Map<String, String> aliases,
        Map<String, Tenant> tenants
) {
    public record Tenant(boolean enabled, Duration timeout) {}
}
~~~

Test with `ApplicationContextRunner`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;
import static org.assertj.core.api.Assertions.assertThat;

class MapBindingPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(MapBindingProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void preservesDottedMapKeys() {
        runner.withPropertyValues(
                "demo.aliases.api.example.com=catalog",
                "demo.tenants.[team.alpha].enabled=true",
                "demo.tenants.[team.alpha].timeout=5s"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            MapBindingProperties props =
                    context.getBean(MapBindingProperties.class);

            assertThat(props.aliases())
                    .containsEntry("api.example.com", "catalog");

            assertThat(props.tenants())
                    .containsKey("team.alpha");

            assertThat(props.tenants().get("team.alpha").enabled())
                    .isTrue();

            assertThat(props.tenants().get("team.alpha").timeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
    }
}
~~~

This test verifies two things:

1. Dotted keys in `Map<String,String>` can be preserved.
2. Bracket notation preserves `team.alpha` as a Map key with an object value.

In a real project, run tests using the appropriate Spring Boot Test dependency, such as `spring-boot-starter-test` in test scope.

For keys containing characters other than dots such as slashes, add a case:

~~~java
runner.withPropertyValues(
    "demo.aliases.[/api/v1]=catalog"
).run(context -> {
    MapBindingProperties props =
            context.getBean(MapBindingProperties.class);
    assertThat(props.aliases())
            .containsEntry("/api/v1", "catalog");
});
~~~

Test results are a reliable way to verify your schema before integrating into deployment systems.

## 24. Configurations with Deeper Nested Maps

An application has a Map of tenants, and each tenant holds a Map of routes:

~~~yaml
demo:
  tenants:
    "[tenant.alpha]":
      routes:
        "[/api/v1]": read
        "[/api/v2]": write
    "[tenant.beta]":
      routes:
        "[/api/v1]": monitor
~~~

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        Map<String, Tenant> tenants
) {
    public record Tenant(Map<String, String> routes) {}
}
~~~

Flattened names:

~~~properties
demo.tenants.[tenant.alpha].routes.[/api/v1]=read
demo.tenants.[tenant.alpha].routes.[/api/v2]=write
demo.tenants.[tenant.beta].routes.[/api/v1]=monitor
~~~

Breakdown:

~~~text
demo
└─ tenants (Map<String,Tenant>)
   ├─ [tenant.alpha] (key)
   │  └─ routes (Map<String,String>)
   │     ├─ [/api/v1] (key) → read
   │     └─ [/api/v2] (key) → write
   └─ [tenant.beta] (key)
      └─ routes (Map<String,String>)
         └─ [/api/v1] (key) → monitor
~~~

There are **two distinct Map key levels**. Each key containing special characters should be placed in its own brackets, while `routes` is the field name on the `Tenant` object.

Never lump `tenant.alpha.routes./api/v1` into a single key, as that destroys the object/Map boundaries expected by the Java model.

## 25. Inspecting Actual Keys via Logs, Actuator, and Code

When a Map key is not read properly, diagnose in order:

1. **Identify the Java field:** is it `Map<String,String>`, `Map<String,Object>`, `Map<String, CustomType>`, or a nested object?
2. **Trace out the full path:** `@ConfigurationProperties` prefix, Map field name, key, then fields of the value object.
3. **Wrap the entire literal key containing dots/symbols in brackets.**
4. **Verify YAML quoting:** is the bracketed key wrapped in quotes?
5. **Check property sources:** is a profile file, environment variable, or CLI overriding the same name?
6. **Inspect keys in the post-binding object**, not just YAML text.
7. **Write tests** covering both special keys and ordinary keys.
8. **Check validation:** if a required entry is missing, do not let the app run misconfigured silently.

You can temporarily inspect **key names** of a Map in a test environment:

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class MapKeyPrinter implements CommandLineRunner {
    private final DemoProperties properties;

    public MapKeyPrinter(DemoProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(String... args) {
        if (properties.tenants() != null) {
            System.out.println("Tenant keys: "
                    + properties.tenants().keySet());
        }
    }
}
~~~

This is strictly for demonstration. In production, keys might contain customer names, sensitive identifiers, or protected metadata; never log full keys/values carelessly.

With Spring Boot Actuator, `configprops` can inspect post-binding configuration beans and `env` can trace configuration sources when enabled. Always lock down access and mask sensitive values.

## 26. Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `Map<String,String>` keeps `a.b` as a single key | Expected scalar Map rule | If nested objects are intended, update the Java model accordingly |
| `Map<String,Object>` creates unintended nested Maps | Dots are treated as paths | Use `[a.b]` to keep the literal key |
| `Map<String,Tenant>` lacks key `team.alpha` | Brackets omitted around dotted key | Use `[team.alpha]` |
| YAML throws syntax error on key `[team.alpha]` | Key name unquoted | Write `"[team.alpha]"` |
| Key `/api/v1` loses its slashes | Missing brackets to preserve special characters | Use `"[/api/v1]"` or `.[/api/v1]` depending on source |
| Map keys look different after refactoring generic type | Changed scalar value to `Object` or custom class | Update property schema and tests |
| Map entry has key but child fields are unbound | Remaining path doesn't match object type | Check field names and record/class layout |
| Using env vars for dotted keys fails lookups | Variable names lose dotted Map key boundaries | Use a bracket-capable config source or deliberately redesign schema |
| `@Value("${demo.tags.a.b}")` behaves unexpectedly | Single placeholders don't replace full Map binding | Use `@ConfigurationProperties` and test Map output |
| List index `[0]` confused with a Map key | Ignored target type and data structure | Distinguish `List` vs `Map` in Java model |
| Dotted key treated as nested fields | Map value is a custom object | Wrap the entire Map key in brackets |
| External file value differs from JAR file | `PropertySource` precedence order | Check which source is currently effective |

To keep naming consistent, adopt one project-wide convention: **free-form identifier keys containing dots or special characters always use bracket notation in config files**. This makes intent clear even while a Map currently holds scalar values.

## 27. Practice Exercises

### Exercise 1 — Scalar Map with Domain-Style Keys

Configuration:

~~~properties
demo.hosts.api.example.com=catalog
demo.hosts.auth.example.com=identity
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record HostProperties(
        java.util.Map<String, String> hosts
) {}
~~~

Question: can key `api.example.com` be preserved intact?

**Answer:** yes. With `Map<String,String>`, values are scalars, so dots in keys can stay intact. You may also switch to `demo.hosts.[api.example.com]` to state intent explicitly.

### Exercise 2 — Object-Valued Map

Given:

~~~java
@ConfigurationProperties(prefix = "demo")
public record TenantProperties(
        java.util.Map<String, Tenant> tenants
) {
    public record Tenant(String region, boolean enabled) {}
}
~~~

You want tenant ID `team.alpha` with `region=asia` and `enabled=true`. Write the YAML.

**Answer:**

~~~yaml
demo:
  tenants:
    "[team.alpha]":
      region: asia
      enabled: true
~~~

Or `.properties`:

~~~properties
demo.tenants.[team.alpha].region=asia
demo.tenants.[team.alpha].enabled=true
~~~

### Exercise 3 — Object Path or Map Key?

Two names:

~~~properties
demo.client.connection.timeout=5s
demo.clients.[connection.timeout].enabled=true
~~~

Question: do the dots in `connection.timeout` mean the same thing on both lines?

**Answer:** no. The first line can be an object path `client` → `connection` → `timeout`. The second line, if `clients` is a Map whose value has an `enabled` field, holds literal key `connection.timeout` inside brackets.

### Exercise 4 — Difference Between `Map<String,String>` and `Map<String,Object>`

Data:

~~~properties
demo.tags.security.level=high
~~~

Question: why might `tags.get("security.level")` stop working after changing the type from `Map<String,String>` to `Map<String,Object>`?

**Answer:** in a scalar Map, `security.level` can stay a single key. With an `Object` Map value, dots can produce nested Map structure. Use `demo.tags.[security.level]=high` to keep the literal key.

### Exercise 5 — Key Containing Slashes

Given:

~~~yaml
demo:
  routes:
    /api/v1: catalog
~~~

You need a `Map<String,String>` with exact key `/api/v1`. Fix the YAML.

**Answer:**

~~~yaml
demo:
  routes:
    "[/api/v1]": catalog
~~~

### Exercise 6 — Map Containing a Map

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record RoutingProperties(
        java.util.Map<String, java.util.Map<String, String>> routes
) {}
~~~

You want outer key `tenant.alpha` and inner key `/orders`, with value `allow`. Write the property.

**Suggested answer:**

~~~properties
demo.routes.[tenant.alpha].[/orders]=allow
~~~

In YAML:

~~~yaml
demo:
  routes:
    "[tenant.alpha]":
      "[/orders]": allow
~~~

Two bracket pairs denote two distinct keys, not a single path.

### Exercise 7 — Catching Bugs from Missing Brackets

Given:

~~~properties
demo.tenants.team.alpha.timeout=5s
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record TenantProperties(
        java.util.Map<String, Tenant> tenants
) {
    public record Tenant(java.time.Duration timeout) {}
}
~~~

The goal is `tenants.get("team.alpha").timeout()` equals 5 seconds. What should you change it to?

**Answer:**

~~~properties
demo.tenants.[team.alpha].timeout=5s
~~~

Brackets keep key `team.alpha` intact before the Binder accesses field `timeout`.

### Exercise 8 — Does a Dot in a Key Mean Brackets Are Required in Every Case?

**Answer:** not mandatory in every case. With scalar-valued Maps like `Map<String,String>`, Spring Boot can keep dots inside keys even without brackets. However, with non-scalar Map values, brackets are needed to distinguish literal keys from object paths. As a configuration style, always using brackets for dotted identifier keys is very helpful.

## 28. Key Takeaways

- **A dot `.` in a property name can be either a hierarchy separator or part of a Map key**, depending on the target type processed by the Spring Boot Binder.
- With **`Map<String,String>`** and other scalar values, a key like `api.example.com` can stay intact without brackets.
- With **`Map<String,Object>` or `Map<String, CustomType>`**, unbracketed dots can be interpreted as nested paths.
- When you want a key preserved verbatim as `team.alpha`, use **`[team.alpha]`**; if the value is an object, follow it with `.field`, e.g. `app.tenants.[team.alpha].timeout`.
- In **YAML**, bracketed keys must be wrapped in quotes: `"[team.alpha]"`.
- For special characters such as **`/api/v1`**, brackets express the literal key to preserve.
- **List indices** like `[0]` differ from **Map keys** like `[tenant.alpha]`; interpretation relies on Java type and path position.
- Switching from a scalar Map to an object Map can be a **schema change**, so test dotted keys carefully.
- Never turn dotted keys into environment variables via mechanical character replacement expecting literal semantics to survive.
- When diagnosing issues, check **prefix, Map value type, bracket notation, YAML/properties files, winning property source, and actual bound Map keys**.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot Reference — Binding Maps](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
