# Flattening YAML Structure into Property Names in Spring Boot

## 1. Why does YAML need to be flattened into property names?

YAML allows configuration to be expressed hierarchically through indentation, which is very convenient when an application has many groups of settings. However, Spring Boot's configuration mechanism needs to look up each property by a uniform name, such as `server.port` or `spring.datasource.url`.

Therefore, when loading `application.yml` or `application.yaml`, Spring Boot converts the hierarchical structure into **flattened property names**. A flattened property name expresses the path to a value using dots and list indices. Afterward, the values are placed into `Environment` and can be read directly or bound to `@ConfigurationProperties` objects.

For example, YAML:

~~~yaml
server:
  port: 8085
spring:
  application:
    name: inventory-service
~~~

Corresponds to two keys:

~~~properties
server.port=8085
spring.application.name=inventory-service
~~~

These two forms differ in syntax, yet express the exact same two settings. **Flattening does not change the meaning of a value**; rather, it represents the value's address as a property name so configuration mechanisms can consume it.

In this lesson, distinguish three concepts:

- **YAML structure:** the tree of mappings, sequences, and leaf values.
- **Flattened property name:** the path to a leaf value, such as `app.clients[1].url`.
- **Binding:** the step where Spring Boot converts values by property name into Java fields, such as `List<Client>` in a `@ConfigurationProperties` class.

Flattening is the step of representing structure; binding is the step of mapping values to Java types.

## 2. Basic rule: indentation becomes dots

A `key: value` pair in YAML is a key and its value. If the value contains child keys, Spring Boot joins key names from outside to inside using dots (`.`).

~~~yaml
app:
  service:
    name: billing
    timeout: 15s
  audit:
    enabled: true
    retention-days: 30
~~~

The resulting property names:

~~~properties
app.service.name=billing
app.service.timeout=15s
app.audit.enabled=true
app.audit.retention-days=30
~~~

You can visualize a path:

~~~text
app
 ├── service
 │    ├── name            → app.service.name
 │    └── timeout         → app.service.timeout
 └── audit
      ├── enabled         → app.audit.enabled
      └── retention-days  → app.audit.retention-days
~~~

Spaces used for indentation determine parent–child positions. YAML does not use curly braces to enclose objects as JSON does. Thus, changing indentation can change property names even when the text lines look almost identical.

Example:

~~~yaml
# Structure A
app:
  service:
    timeout: 15s

# Structure B, as a separate example
app:
  service: active
  timeout: 15s
~~~

In Structure A, the property name is `app.service.timeout`. In Structure B, the names are `app.service` and `app.timeout`; there is no longer an `app.service.timeout` key.

**Rule:** walk from the root node to the leaf value; each mapping level appends `.<key-name>`.

## 3. Leaf values (scalars) keep the key without adding levels

A scalar is a value with no further substructure: string, number, boolean, or special value such as `null`. When flattened, the key name is the path to the scalar; the value representation is passed to the configuration mechanism and can be converted when bound to Java types.

~~~yaml
shop:
  title: "Internal Store"
  port: 8090
  enabled: true
  min-order: 0
  timeout: 750ms
~~~

Equivalent `.properties`-style form:

~~~properties
shop.title=Internal Store
shop.port=8090
shop.enabled=true
shop.min-order=0
shop.timeout=750ms
~~~

Here `750ms` can be bound to `java.time.Duration` when the target type matches; `8090` can be bound to `int`. Expressing entries as flat keys **does not mean every value becomes a Java string**. The actual type depends on the YAML parser, the property source, and the converters applied during binding.

For values with characters that might cause ambiguity, wrap them in quotes:

~~~yaml
shop:
  display-code: "0012"
  base-url: "https://example.org:8443/api"
  message: "Startup succeeded"
~~~

Quotes are YAML syntax for expressing the value; they do not become a segment in the property name. For example, the key remains `shop.base-url`.

## 4. Lists: using `[0]`, `[1]`, `[2]`... indices

For YAML lists (sequences), Spring Boot uses **zero-based indices** enclosed in square brackets after the property name.

~~~yaml
app:
  supported-locales:
    - vi
    - en
    - ja
~~~

Flattened form:

~~~properties
app.supported-locales[0]=vi
app.supported-locales[1]=en
app.supported-locales[2]=ja
~~~

An inline list carries the same meaning:

~~~yaml
app:
  supported-locales: [vi, en, ja]
~~~

Indices reflect element positions accurately, so reordering items in YAML also changes the values attached to `[0]`, `[1]`, and so on.

### 4.1. Lists containing objects

A common example is a list of endpoints:

~~~yaml
app:
  endpoints:
    - name: primary
      url: "https://primary.example.org"
      retries: 2
    - name: backup
      url: "https://backup.example.org"
      retries: 1
~~~

Flattened form:

~~~properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.org
app.endpoints[0].retries=2
app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.org
app.endpoints[1].retries=1
~~~

How to read `app.endpoints[1].url`: enter `app` → property `endpoints` → second element (`[1]`) → property `url`.

### 4.2. Nested lists

~~~yaml
app:
  teams:
    - name: backend
      members:
        - An
        - Binh
    - name: frontend
      members:
        - Chi
~~~

Flattened form:

~~~properties
app.teams[0].name=backend
app.teams[0].members[0]=An
app.teams[0].members[1]=Binh
app.teams[1].name=frontend
app.teams[1].members[0]=Chi
~~~

Each time you traverse a list, append `[index]`; each time you traverse a mapping, append `.key`. Both rules combine cleanly with no extra exceptions.

## 5. Mappings, Maps, and key names with special characters

YAML mappings have keys, usually strings. In simple cases, they are joined with dots:

~~~yaml
app:
  labels:
    region: asia
    tier: gold
~~~

Flattened form:

~~~properties
app.labels.region=asia
app.labels.tier=gold
~~~

If Java has `Map<String, String> labels`, Spring Boot can bind the two keys `region` and `tier` as entries in the map.

However, for **Map key names containing special characters**, distinguish generating flattened property names from preserving literal keys during binding. Spring Boot supports **bracket notation** to preserve characters that do not conform to standard property-name rules.

~~~yaml
app:
  labels:
    "[/api/v1]": public
    "[user.role]": admin
~~~

The corresponding paths with bracket notation:

~~~properties
app.labels.[/api/v1]=public
app.labels.[user.role]=admin
~~~

Here, when binding to `Map<String, String>`, the intended keys are `/api/v1` and `user.role`, not two nested property levels `user` → `role`.

**Note:** in YAML, when using keys with square brackets, **wrap the entire key in quotes** (`"[/api/v1]"`). Without quotes, `[` and `]` may be parsed by YAML as structural syntax instead of literal characters inside the key name.

For complex Maps or keys containing dots, slashes, or spaces, verify the target Map type and choose bracket notation accordingly. Do not assume a dot always represents a dot inside a Map key: normally it acts as a separator between levels of a property name.

## 6. Combined example: from a YAML tree to a flat list of keys

Suppose `application.yml` contains configuration for a storefront application:

~~~yaml
server:
  port: 8088

spring:
  application:
    name: storefront

store:
  region: vn
  checkout:
    enabled: true
    timeout: 4s
  currencies:
    - VND
    - USD
  warehouses:
    - code: hcm
      address:
        city: Ho Chi Minh City
        country: VN
      priorities: [1, 2]
    - code: hn
      address:
        city: Ha Noi
        country: VN
      priorities: [3]
~~~

All leaf values are represented in flattened form as follows:

~~~properties
server.port=8088
spring.application.name=storefront
store.region=vn
store.checkout.enabled=true
store.checkout.timeout=4s
store.currencies[0]=VND
store.currencies[1]=USD
store.warehouses[0].code=hcm
store.warehouses[0].address.city=Ho Chi Minh City
store.warehouses[0].address.country=VN
store.warehouses[0].priorities[0]=1
store.warehouses[0].priorities[1]=2
store.warehouses[1].code=hn
store.warehouses[1].address.city=Ha Noi
store.warehouses[1].address.country=VN
store.warehouses[1].priorities[0]=3
~~~

Path pattern reference table:

| YAML structure | Example | Naming rule |
| --- | --- | --- |
| Mapping nested in mapping | `store.checkout.timeout` | Join keys with `.` |
| Mapping containing scalar list | `store.currencies[1]` | Append element index |
| List containing mappings | `store.warehouses[0].code` | Index followed by child key |
| Mapping nested inside list element | `store.warehouses[0].address.city` | Continue joining keys with `.` |
| List inside list element | `store.warehouses[0].priorities[1]` | Each list gets its own `[index]` |

A YAML tree can be many levels deep; the rule remains joining the path to each leaf value. You do not need a separate `store.warehouses` line just to indicate that it is a list: the child elements already express the full structure.

## 7. Retrieving flattened values through Environment

Once Spring Boot loads configuration, you can query `Environment` by property name. For example, using the combined YAML above:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigInspector {
    private final Environment environment;

    public ConfigInspector(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("store.region");
    }

    public String firstCurrency() {
        return environment.getProperty("store.currencies[0]");
    }

    public String firstWarehouseCity() {
        return environment.getProperty("store.warehouses[0].address.city");
    }

    public Integer serverPort() {
        return environment.getProperty("server.port", Integer.class);
    }
}
~~~

Here:

- `getProperty("store.region")` accesses the scalar `vn`.
- `getProperty("store.currencies[0]")` accesses the first element `VND`.
- `getProperty("store.warehouses[0].address.city")` accesses `Ho Chi Minh City`.
- `getProperty("server.port", Integer.class)` requests conversion to `Integer`.

The actual result can be overridden by **higher-precedence configuration sources**, such as environment variables, Java system properties, or command-line arguments. Flattening YAML into keys does not guarantee the retrieved value always comes from the YAML file you are looking at.

Do not assume `Environment#getProperty("store.warehouses")` will return the whole list as a Java object. To retrieve complex structures, bind with `@ConfigurationProperties`.

## 8. Binding flattened names into Java objects with @ConfigurationProperties

Spring Boot supports binding a group of properties sharing a prefix into a structured object. We can translate the example above into Java records:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;
import java.util.List;

@ConfigurationProperties(prefix = "store")
public record StoreProperties(
        String region,
        Checkout checkout,
        List<String> currencies,
        List<Warehouse> warehouses
) {
    public record Checkout(boolean enabled, Duration timeout) {}

    public record Warehouse(
            String code,
            Address address,
            List<Integer> priorities
    ) {}

    public record Address(String city, String country) {}
}
~~~

Enable scanning for `@ConfigurationProperties` classes:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

A service using the bound type:

~~~java
import org.springframework.stereotype.Service;

@Service
public class WarehouseService {
    private final StoreProperties properties;

    public WarehouseService(StoreProperties properties) {
        this.properties = properties;
    }

    public String primaryWarehouseCity() {
        return properties.warehouses().get(0).address().city();
    }
}
~~~

Looking from the data direction:

~~~text
store.warehouses[0].address.city
          │         │       │
          ▼         ▼       ▼
   warehouses()   address() city()
   (List)         (record)  (String)
~~~

`app` or `store` is a **prefix** chosen by the author; `spring` and `server` are familiar Spring Boot configuration prefixes. You do not need to create a Java field containing `.` or `[0]`: the Binder understands flattened names and constructs the target structure automatically.

Common conversions during binding:

- `store.checkout.timeout=4s` → `Duration.ofSeconds(4)`.
- `store.checkout.enabled=true` → `boolean true`.
- `store.warehouses[0].priorities[1]=2` → second element of `List<Integer>` in the first warehouse.
- `store.region=vn` → `String region`.

If there are mandatory constraints on element counts or valid values, validate the object after binding; flattening only resolves **the path to the value**, and does not enforce business rules by itself.

## 9. Relaxed binding and property naming styles

Spring Boot uses **relaxed binding** when mapping property names to `@ConfigurationProperties`. Thus, kebab-case names in configuration can map to camelCase names in Java.

~~~yaml
app:
  request-timeout: 5s
  max-retries: 4
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "app")
public record AppSettings(Duration requestTimeout, int maxRetries) {}
~~~

The canonical configuration paths are `app.request-timeout` and `app.max-retries`; the Java record components are `requestTimeout` and `maxRetries`.

These are two distinct steps:

1. **Flattening:** `app` + `request-timeout` → `app.request-timeout`.
2. **Relaxed binding:** `app.request-timeout` → Java `requestTimeout`.

Generally, use **lowercase kebab-case** in configuration documents so property names remain consistent. Do not rely on relaxed binding to explain every direct lookup via `Environment#getProperty`: property resolver lookups and object binding have related rules that are not completely identical.

Operating system environment variables follow a different naming convention, such as `APP_REQUESTTIMEOUT` or normalized names matching Binder rules. Mapping flattened keys to environment variables belongs to the configuration source layer, not YAML indentation syntax. For lists, environment variable names can use indices separated by underscores, such as `APP_ENDPOINTS_0_NAME`.

## 10. Multi-document YAML and profiles: flattening per active document

A YAML file can contain multiple documents separated by `---`. Spring Boot can activate a document only when its matching profile is active:

~~~yaml
app:
  banner: common
  retries: 2

---
spring:
  config:
    activate:
      on-profile: prod
app:
  banner: production
  retries: 5
~~~

The first document defines `app.banner=common` and `app.retries=2`. When the `prod` profile is active, the second document activates and can override those values to `production` and `5`.

**`---` does not become a segment in the property name.** It separates configuration documents. Similarly, `application-prod.yml` still produces key names like `app.banner`; the word `prod` in the filename is not automatically prepended or inserted into the property path.

Multiple sources can produce `app.banner`. Spring Boot resolves the final value via property source precedence rules, rather than encoding filenames into keys.

## 11. Lists across multiple configuration sources: not merged element by element

Flattening reveals each index, yet that does not mean Spring Boot merges lists from different precedence sources element by element when binding to `@ConfigurationProperties`.

For example, a default file inside the JAR:

~~~yaml
app:
  servers:
    - host: dev-one
      port: 8080
    - host: dev-two
      port: 8081
~~~

A higher-precedence external configuration file:

~~~yaml
app:
  servers:
    - host: prod-one
      port: 9090
~~~

For a `List<Server>` bound from `app.servers`, Spring Boot normally uses **the list from the highest-precedence source**, rather than merging `prod-one` with `dev-two` into a two-element list.

Practical consequence: when overriding a configured list for an environment, declare **the complete desired list** in the overriding source. Do not assume `[1]` from the default file will still be kept.

This differs from many object or Map configurations, where distinct keys can be combined according to Binder rules. Combining values across sources is a matter of **merging/binding and precedence**, not the initial flattening step.

## 12. How to flatten YAML manually

You can do this by hand using a consistent procedure:

1. Start from the root node of the YAML document with an initially empty current path.
2. If the node is a **mapping**, append `.<key>` to the path for each child key (omit the leading dot at the root).
3. If the node is a **sequence**, append `[0]`, `[1]`, ... for each element.
4. If the node is a **scalar**, record a `path = value` pair.
5. For Map keys with special characters that must be preserved during binding, consider **bracket notation** such as `.[/api]` and YAML quoting.

Illustrated in pseudocode:

~~~text
flatten(node, path):
    if node is mapping:
        for each (key, value):
            childPath = path is empty ? key : path + "." + key
            flatten(value, childPath)

    else if node is sequence:
        for each (item, index):
            childPath = path + "[" + index + "]"
            flatten(item, childPath)

    else:
        output(path, node)
~~~

This model explains **how key names are formed**, not a complete implementation of a YAML parser or Spring Binder. The parser also processes YAML syntax, tags, escaping, and other special rules before producing data to flatten.

## 13. Common mistakes

| Symptom | Common cause | Direction to fix |
| --- | --- | --- |
| `Environment#getProperty("app.server.port")` returns `null` | Actual YAML path may be `app.servers.port` or have different indentation | Trace levels carefully from root to scalar |
| Thinking `app.roles.0` is the standard list key | Spring Boot represents lists with `[0]` | Use `app.roles[0]` when reading flattened names |
| `List<Client>` loses elements after overriding config | List from higher-precedence source replaces old list during binding | Write the complete list in the overriding source |
| Map key with `/` or `.` gets altered on bind | Key contains special characters without proper bracket notation | Use bracketed key wrapped in YAML quotes |
| Boolean or numeric value fails to bind to expected type | YAML value type does not match Java field expectation | Inspect scalar, quotes, and target field type |
| Key is visible in YAML but runtime value differs | Higher-precedence source overrides it, or another profile is active | Check property source order and active profiles |
| Using `@Value` for a complex list | Using scalar lookup for a structure needing binder | Use `@ConfigurationProperties` with `List` or `Map` |

To investigate, first determine **the exact flattened property name**, then inspect every source that may define that same key. Spring Boot Actuator can help inspect configuration via `env` and `configprops`, provided endpoints are secured and sensitive values remain masked.

## 14. Practice exercises

### Exercise 1 — Nested mappings

Given the YAML:

~~~yaml
mail:
  smtp:
    host: "smtp.example.org"
    port: 587
    auth:
      enabled: true
~~~

Write the flattened property names for all three leaf values.

**Answer:**

~~~properties
mail.smtp.host=smtp.example.org
mail.smtp.port=587
mail.smtp.auth.enabled=true
~~~

### Exercise 2 — List of objects

Given the YAML:

~~~yaml
app:
  workers:
    - id: alpha
      enabled: true
    - id: beta
      enabled: false
~~~

Find the key corresponding to the value `false`.

**Answer:** `app.workers[1].enabled`.

### Exercise 3 — Combining lists and nested structures

Given the YAML:

~~~yaml
academy:
  courses:
    - title: Java Core
      lessons:
        - name: Variables
        - name: Loops
    - title: Spring Boot
      lessons:
        - name: Configuration
~~~

Find the flattened property names for `Loops` and `Configuration`.

**Answer:**

~~~properties
academy.courses[0].lessons[1].name=Loops
academy.courses[1].lessons[0].name=Configuration
~~~

### Exercise 4 — Distinguishing key names from overriding sources

There is a packaged `application.yml`:

~~~yaml
app:
  timeout: 3s
~~~

And an external `./config/application.yml`:

~~~yaml
app:
  timeout: 12s
~~~

Do the two files generate the same property name? Which value does the application receive if no higher-precedence override exists?

**Answer:** both generate `app.timeout`. The file outside the JAR has higher precedence in standard Config Data loading, so the final value is `12s`. **Property names do not encode which file they came from**.

## 15. Takeaways

- **Nested mappings → dots:** `app.database.pool.size`.
- **Lists → indices in square brackets:** `app.regions[0]`.
- **Lists of objects → combining indices and dots:** `app.clients[1].url`.
- **Special Map keys → consider bracket notation and quoted YAML keys** to preserve names during binding.
- **Flattening** produces key names; **relaxed binding** maps key names to Java field names; **precedence** selects the final value source.
- **Profiles and source files** do not automatically become part of key names; they determine which documents are active and override ordering.
- With `@ConfigurationProperties` lists, do not assume elements from multiple sources are merged.

References: [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html) and [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
