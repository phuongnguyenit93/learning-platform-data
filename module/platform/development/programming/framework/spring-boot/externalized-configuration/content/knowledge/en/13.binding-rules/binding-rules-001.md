# Relaxed Binding and Canonical Property Names in Spring Boot 3.3

## 1. Objectives

Spring Boot 3.3 typically receives configuration from multiple sources simultaneously: `application.properties`, `application.yaml`, OS environment variables, Java system properties, command-line arguments, and other Config Data sources. These sources do not always share the same naming convention.

For example, the same Java property:

```java
private int maxRetries;
```

can be configured using these forms:

```properties
app.max-retries=3
app.maxRetries=3
app.max_retries=3
```

or when passed via an environment variable:

```bash
APP_MAXRETRIES=3
```

This is Spring Boot's **relaxed binding** capability: the Binder recognizes equivalent property name variants and maps them to the same JavaBean property or constructor parameter when using `@ConfigurationProperties`.

**Important note:** relaxed binding is a **name-mapping** mechanism; it does not mean every name string with any delimiter is automatically equivalent, it does not mean `Map` keys are always normalized without losing information, and it does not override **PropertySource precedence** when two sources provide the same property.

Objectives after this lesson:

- Recognize **canonical property names** using lowercase letters and hyphens `-`.
- Know how to convert property names between Java camelCase, `.properties`/YAML, and environment variables.
- Distinguish relaxed binding for `@ConfigurationProperties` from access via `@Value` or `Environment`.
- Understand exceptions for **List indexes**, **Map keys**, uppercase/lowercase, and special characters.
- Know how to organize examples, write tests, and troubleshoot keys that fail to bind.

## 2. What is a canonical property name?

In the context of Spring Boot configuration properties, the recommended **canonical form** is a name that uses:

1. **Lowercase** letters.
2. Words within a single segment joined by **hyphens `-`** (*kebab-case*).
3. Dots `.` to separate configuration hierarchy levels.
4. Indexes `[0]`, `[1]`… when representing collection elements as a property path.

Example:

```properties
app.name=Catalog
app.max-retries=3
app.client.connect-timeout=5s
app.security.require-https=true
app.endpoints[0].base-url=https://a.example.test
app.endpoints[1].base-url=https://b.example.test
```

Corresponding canonical names:

| Canonical property path | Hierarchy and meaning |
| --- | --- |
| `app.name` | `app` → `name` |
| `app.max-retries` | `app` → `maxRetries` |
| `app.client.connect-timeout` | `app` → `client` → `connectTimeout` |
| `app.security.require-https` | `app` → `security` → `requireHttps` |
| `app.endpoints[0].base-url` | `app` → element 0 of `endpoints` → `baseUrl` |

In Java, **camelCase** is typically used for property names (`maxRetries`, `connectTimeout`, `requireHttps`), while in configuration files the canonical **kebab-case** form should be used (`max-retries`, `connect-timeout`, `require-https`).

### The prefix must also follow the canonical form

If you declare:

```java
@ConfigurationProperties(prefix = "catalog.http-client")
public class HttpClientProperties {
    // ...
}
```

then `catalog.http-client` is a canonical prefix. You should not declare the prefix as `catalog.httpClient` or `Catalog.Http_Client`. Spring Boot requires `@ConfigurationProperties` prefixes to follow the appropriate kebab-case form.

For a multi-level prefix:

```java
@ConfigurationProperties(prefix = "acme.checkout-service")
```

child properties can be:

```properties
acme.checkout-service.enabled=true
acme.checkout-service.request-timeout=3s
```

**Naming rule for documentation:** always use the canonical form, even when the Binder still accepts several other forms. This keeps property names consistent across READMEs, `@Value`, configuration metadata, profile files, and deployment scripts.

## 3. How relaxed binding works in `@ConfigurationProperties`

The Spring Boot Binder reads properties from the `Environment` and assigns them to the target Java type. Given a class:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String displayName;
    private int maxRetries;
    private boolean auditEnabled;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isAuditEnabled() { return auditEnabled; }
    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }
}
```

Spring Boot binds the keys:

```properties
app.display-name=Catalog API
app.max-retries=4
app.audit-enabled=true
```

to `displayName`, `maxRetries`, and `auditEnabled`.

However, it can also recognize forms carrying the same meaning such as:

```properties
app.displayName=Catalog API
app.maxRetries=4
app.auditEnabled=true
```

or:

```properties
app.display_name=Catalog API
app.max_retries=4
app.audit_enabled=true
```

These three example blocks are **three alternatives**, not three configuration sets to declare at the same time. If you declare multiple variants for the same target within the same or different PropertySources, readers will struggle to tell which value takes effect; standardize on a single naming style to avoid ambiguity.

### No need to match Java casing

JavaBean property names are determined by getters/setters or constructor parameters (with constructor binding). The Binder does not require YAML files to use `displayName` just because the class has `getDisplayName()`; `display-name` remains the canonical choice.

### Relaxed binding is distinct from type conversion

These are two related but independent mechanisms:

- **Name:** `app.connect-timeout` is recognized as the Java property `connectTimeout`.
- **Value:** the string `5s` is converted to `Duration` if the Java target type is `Duration`.

Example:

```java
private Duration connectTimeout = Duration.ofSeconds(2);

public Duration getConnectTimeout() {
    return connectTimeout;
}

public void setConnectTimeout(Duration connectTimeout) {
    this.connectTimeout = connectTimeout;
}
```

```properties
app.connect-timeout=5s
```

The binding pipeline involves both **name recognition** and **value conversion**, not merely turning hyphens into camelCase.

## 4. Accepted name formats by configuration source

Basic representations in Spring Boot 3.3:

| Source | Name styles commonly supported by the Binder | Example for Java `firstName` |
| --- | --- | --- |
| `application.properties` | Kebab-case, camelCase, underscore | `person.first-name`, `person.firstName`, `person.first_name` |
| `application.yaml` / `.yml` | Kebab-case, camelCase, underscore | `person:` → `first-name:` / `firstName:` / `first_name:` |
| Java system properties (`-D`) | Kebab-case, camelCase, underscore | `-Dperson.first-name=An` |
| OS environment variables | Uppercase, underscore, hyphens removed | `PERSON_FIRSTNAME=An` |

This table describes names bound via `@ConfigurationProperties`; do not generalize that every API reading raw keys handles similar variants in all situations.

### 4.1. `.properties`

```properties
app.http-client.connect-timeout=5s
```

Java target:

```java
private HttpClient httpClient;
public static class HttpClient {
    private Duration connectTimeout;
    // getters/setters
}
```

The canonical property path is `app.http-client.connect-timeout`; both dots and hyphens carry meaning: dots separate hierarchy levels, and hyphens separate words within a single Java property name.

### 4.2. YAML

```yaml
app:
  http-client:
    connect-timeout: 5s
    retry-count: 3
```

Spring Boot flattens YAML into the corresponding property paths, for example:

```text
app.http-client.connect-timeout
app.http-client.retry-count
```

YAML can use camelCase, but writing kebab-case keeps all examples consistent with the canonical form.

### 4.3. Java system properties

```bash
java -Dapp.http-client.connect-timeout=5s -jar myapp.jar
```

System properties keep the dot-and-hyphen notation; the Binder still uses relaxed binding to map to `httpClient.connectTimeout`.

### 4.4. Command-line options

```bash
java -jar myapp.jar \
  --app.http-client.connect-timeout=5s \
  --app.http-client.retry-count=3
```

Arguments of the form `--key=value` are added to `Environment` by Spring Boot by default when passed to `SpringApplication.run(args)`. The command line is a separate PropertySource with high precedence in standard configurations.

If the application explicitly disables `setAddCommandLineProperties(false)`, you should not assume those options will be processed as Spring properties.

## 5. Rules for converting to OS environment variables

One of the most error-prone tasks is converting a canonical property name into an environment variable. Spring Boot 3.3 describes three steps:

1. **Replace dots `.` with underscores `_`**.
2. **Remove hyphens `-`**, do not replace them with `_`.
3. **Convert everything to uppercase**.

Example:

```text
spring.main.log-startup-info
        ↓ replace dots
spring_main_log-startup-info
        ↓ remove hyphens
spring_main_logstartupinfo
        ↓ uppercase
SPRING_MAIN_LOGSTARTUPINFO
```

Conversion table:

| Canonical property | Canonical environment variable |
| --- | --- |
| `app.name` | `APP_NAME` |
| `app.display-name` | `APP_DISPLAYNAME` |
| `app.max-retries` | `APP_MAXRETRIES` |
| `app.http-client.connect-timeout` | `APP_HTTPCLIENT_CONNECTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `spring.config.additional-location` | `SPRING_CONFIG_ADDITIONALLOCATION` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |

**Warning:** `APP_MAX_RETRIES` looks "reasonable", but it is not the canonical conversion result of `app.max-retries`. Underscores in an environment variable primarily represent **hierarchy dots**, whereas hyphens are **removed**. When naming variables for Docker/Kubernetes/CI, prefer the exact `APP_MAXRETRIES`.

### Unix-like environment example

```bash
APP_NAME="Catalog API" \
APP_MAXRETRIES=0 \
APP_HTTPCLIENT_CONNECTTIMEOUT=750ms \
java -jar myapp.jar
```

With an appropriate Java target, the result can be:

```text
name = "Catalog API"
maxRetries = 0
httpClient.connectTimeout = 750 ms
```

`0` is still an explicit value; relaxed binding does not turn zero into "not declared".

### Docker Compose

```yaml
services:
  catalog:
    image: example/catalog:1.0
    environment:
      APP_NAME: "Catalog API"
      APP_MAXRETRIES: "0"
      APP_HTTPCLIENT_CONNECTTIMEOUT: "750ms"
```

You should quote environment values in YAML to make the string representation explicit. The variable names must exist in the **Java process's** environment, not merely in another terminal session.

### Kubernetes (illustrative)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: example/catalog:1.0
          env:
            - name: APP_HTTPCLIENT_CONNECTTIMEOUT
              value: "750ms"
            - name: APP_MAXRETRIES
              value: "0"
```

Each `name/value` pair is supplied when the container starts the process, so Spring Boot can read it through the OS environment source.

### Environment variables and case sensitivity

Environment variable names on Linux are generally case-sensitive at the OS level, whereas Spring Boot's canonical names use uppercase. Creating multiple similar names that differ only in casing or underscores can lead to unpredictable behavior across platforms and in how they enter the PropertySource. It is best **not to use two differently named variables just to simulate the same property**.

## 6. List/array indexes in relaxed binding

Collection configuration in `.properties` is usually written as:

```properties
app.servers[0].host=alpha.example.test
app.servers[0].port=8080
app.servers[1].host=beta.example.test
app.servers[1].port=8081
```

The Java target can be:

```java
private List<Server> servers;

public static class Server {
    private String host;
    private int port;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
```

Equivalent YAML form:

```yaml
app:
  servers:
    - host: alpha.example.test
      port: 8080
    - host: beta.example.test
      port: 8081
```

Specific rule for environment variables: **the index must be surrounded by `_`**. The official documentation example uses:

```text
my.service[0].other -> MY_SERVICE_0_OTHER
```

Applying this to the example above:

```bash
APP_SERVERS_0_HOST=alpha.example.test
APP_SERVERS_0_PORT=8080
APP_SERVERS_1_HOST=beta.example.test
APP_SERVERS_1_PORT=8081
```

**Do not write** `APP_SERVERS0_HOST` expecting the Binder to reliably recognize it as `servers[0].host`. The `_0_` structure clearly represents the element position in the list.

### Indexes and source precedence

If a higher-precedence source defines a `List`, Spring Boot typically **replaces the entire List** from lower-precedence sources rather than merging by index or per-element properties. For example, if the base file has two `servers` and the `dev` profile only has one server, the final list in `dev` contains only the `dev` server. This is a collection-binding rule, not a consequence of naming alone.

## 7. Map keys are not the same as JavaBean property names

This is a very important exception. **Property names in the path** can be relaxed-bound, whereas **Map keys are application data** and often need to preserve their exact characters.

Suppose the model is:

```java
@ConfigurationProperties(prefix = "app")
public class RouteProperties {
    private Map<String, String> routes = new LinkedHashMap<>();

    public Map<String, String> getRoutes() { return routes; }
    public void setRoutes(Map<String, String> routes) {
        this.routes = routes;
    }
}
```

And the configuration is:

```properties
app.routes.public=frontend
app.routes.internal=backend
```

The Binder interprets `public` and `internal` as **keys** of `Map<String,String> routes`, rather than two required JavaBean fields. If a key contains `/` or special characters, it requires dedicated syntax.

### 7.1. Use `[key]` to preserve special characters

To make the actual key `/api/v1`:

```properties
app.routes.[/api/v1]=frontend
app.routes.[/admin]=backend
```

In YAML:

```yaml
app:
  routes:
    "[/api/v1]": frontend
    "[/admin]": backend
```

Expected result:

```text
routes.get("/api/v1") == "frontend"
routes.get("/admin")  == "backend"
```

**In YAML specifically, keys with bracket notation must be quoted**, e.g., `"[/api/v1]"`. Without `[]`, characters other than alphanumeric characters, `-`, or `.` may be stripped from the key during binding. For example:

```properties
app.routes./api/v1=frontend
```

may produce the key `apiv1` instead of `/api/v1`; this is a data bug, not merely a naming style issue.

### 7.2. Keys containing dots depend on the Map value type

If `routes` is `Map<String,String>`, a key containing a dot such as `a.b` can be preserved without brackets:

```properties
app.routes.a.b=value
```

However, if the target type is `Map<String,Object>` or a complex structure, an unbracketed dot may represent a **nested level**.

To guarantee the literal key `a.b` when unsure of the Map type:

```properties
app.metadata.[a.b]=value
```

YAML:

```yaml
app:
  metadata:
    "[a.b]": value
```

Do not assume relaxed binding will "strip dots", "keep dots", or "turn into nested keys" identically for every Map type. You must consider both the **Map value type** and bracket notation.

### 7.3. Case of Map keys from environment variables

When binding a Map from environment variables, Spring Boot converts Map key names from the environment source to **lowercase**. For example:

```bash
APP_LABELS_TEAM=platform
```

With `Map<String,String> labels`, the resulting key is `team`, not `TEAM`. If business logic needs mixed-case keys, `/`, `.`, or special Unicode characters, environment variables are not always the easiest source to express them; use a Config Data file with bracketed keys when exact preservation is required.

## 8. Distinguishing key names in sources from target Java property names

Look at a configuration entry:

```properties
app.payment-gateway.base-url=https://pay.example.test
```

It can be modeled as:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private PaymentGateway paymentGateway = new PaymentGateway();

    public PaymentGateway getPaymentGateway() {
        return paymentGateway;
    }

    public void setPaymentGateway(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public static class PaymentGateway {
        private String baseUrl;

        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    }
}
```

The Binder follows the chain:

```text
app.payment-gateway.base-url
 |         |              |
prefix   paymentGateway   baseUrl
```

In Java, `paymentGateway` and `baseUrl` are field/property names; in Config Data, `payment-gateway` and `base-url` are their canonical names.

Contrast this with:

```java
Map<String, PaymentGateway> gateways;
```

In that case:

```properties
app.gateways.billing.base-url=https://pay.example.test
```

`billing` is a **Map key**, not a fixed JavaBean property. Map key preservation rules can become important if the key contains special characters.

## 9. `@Value` and placeholders: canonical form matters

`@ConfigurationProperties` uses the Binder with dedicated relaxed binding. `@Value` uses the Spring Framework/Boot property placeholder mechanism; the two APIs are **not completely identical**.

**Spring Boot 3.3 recommendation:** when writing placeholders in `@Value`, use the **canonical property name (lowercase kebab-case)**. This allows Spring Boot to apply lookup logic similar to `@ConfigurationProperties` relaxed binding in supported cases.

Example:

```java
@Value("${app.max-retries:3}")
private int maxRetries;
```

With the canonical placeholder `app.max-retries`, Spring Boot can consider corresponding variants such as `app.max-retries` and `app.maxRetries` from files and `APP_MAXRETRIES` from environment variables.

Conversely:

```java
@Value("${app.maxRetries:3}")
private int maxRetries;
```

writing the placeholder name in camelCase may **not consider all** equivalent variants the way the canonical name does. Even if a specific source can still be read, do not infer that `@Value` always carries full Binder semantics for every property name.

**Choose the canonical style:**

```java
@Value("${app.http-client.connect-timeout:5s}")
private Duration connectTimeout;
```

Instead of:

```java
@Value("${app.httpClient.connectTimeout:5s}")
private Duration connectTimeout;
```

### What is `@Value` good for?

- One or a few simple scalar values.
- Placeholders with defaults such as `${app.name:Catalog}`.
- Cases that need SpEL expressions by Spring design.

### When should you use `@ConfigurationProperties`?

- Multiple properties sharing a prefix.
- Nested objects, `List<T>`, `Map<K,V>`.
- Type-safe binding, constructor/record binding, and validation.
- Need configuration metadata for IDEs and documentation.
- Want consistent relaxed binding across multiple sources.

Do not use `@Value("${app.servers}")` expecting it to construct a complex `List<Server>` from keys like `app.servers[0].host`. Use the Binder/`@ConfigurationProperties` instead.

## 10. Does `Environment#getProperty` follow the same rules?

An example:

```java
String timeout = environment.getProperty(
        "app.http-client.connect-timeout");
```

`Environment` resolves keys through `PropertySource` instances; the level of name-variant support depends on the PropertySource type and property-name mapping mechanism. Therefore:

- When reading files and environment variables with `@ConfigurationProperties`, the Binder is the path specifically designed for relaxed binding.
- When reading a single String key, use the **canonical name** consistently.
- Do not use `getProperty` to check a set of near-duplicate keys and assemble an object manually when the Binder can handle it.
- `Environment.containsProperty(key)` and `getProperty(key)` describe whether a property is resolvable in `Environment`, not which file a literal text key appeared in.

In Spring Boot, environment variables are represented by a PropertySource capable of mapping from `APP_MAXRETRIES` to the corresponding property name; however, API usage and lookup keys should still consistently use the canonical form to avoid unexpected differences.

## 11. Complete application example

### 11.1. The `CatalogProperties` class

This example uses Spring Boot 3.3 and Java 17+:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties {

    private String displayName = "Catalog";
    private int maxRetries = 3;
    private boolean auditEnabled = true;

    private HttpClient httpClient = new HttpClient();
    private List<Endpoint> endpoints = new ArrayList<>();
    private Map<String, String> routes = new LinkedHashMap<>();

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isAuditEnabled() {
        return auditEnabled;
    }

    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }

    public HttpClient getHttpClient() {
        return httpClient;
    }

    public void setHttpClient(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    public List<Endpoint> getEndpoints() {
        return endpoints;
    }

    public void setEndpoints(List<Endpoint> endpoints) {
        this.endpoints = endpoints;
    }

    public Map<String, String> getRoutes() {
        return routes;
    }

    public void setRoutes(Map<String, String> routes) {
        this.routes = routes;
    }

    public static class HttpClient {
        private Duration connectTimeout = Duration.ofSeconds(2);

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }
    }

    public static class Endpoint {
        private String baseUrl;
        private boolean enabled = true;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
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

The JavaBeans names here are camelCase (`displayName`, `maxRetries`, `auditEnabled`, `httpClient`, `connectTimeout`, `baseUrl`), whereas the canonical configuration file uses kebab-case.

### 11.2. Enabling `@ConfigurationProperties` scanning

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

`@ConfigurationPropertiesScan` registers `@ConfigurationProperties` classes in the scanned packages. It can be replaced with `@EnableConfigurationProperties(CatalogProperties.class)` when you want to register a specific class explicitly, without needing both for the same bean.

### 11.3. Canonical YAML configuration

```yaml
# src/main/resources/application.yaml
catalog:
  display-name: Catalog API
  max-retries: 3
  audit-enabled: true

  http-client:
    connect-timeout: 2s

  endpoints:
    - base-url: https://first.example.test
      enabled: true
    - base-url: https://second.example.test
      enabled: false

  routes:
    "[/api/v1]": first
    "[/health]": second
```

### 11.4. Equivalent `.properties` configuration

```properties
# src/main/resources/application.properties
catalog.display-name=Catalog API
catalog.max-retries=3
catalog.audit-enabled=true

catalog.http-client.connect-timeout=2s

catalog.endpoints[0].base-url=https://first.example.test
catalog.endpoints[0].enabled=true
catalog.endpoints[1].base-url=https://second.example.test
catalog.endpoints[1].enabled=false

catalog.routes.[/api/v1]=first
catalog.routes.[/health]=second
```

Only **one** of these two equivalent files is needed for this scenario. Do not put both in the same location and assume Boot will merge keys arbitrarily.

### 11.5. Overriding with environment variables

```bash
CATALOG_DISPLAYNAME="Catalog deployed" \
CATALOG_MAXRETRIES=0 \
CATALOG_AUDITENABLED=false \
CATALOG_HTTPCLIENT_CONNECTTIMEOUT=750ms \
CATALOG_ENDPOINTS_0_BASEURL=https://internal.example.test \
java -jar myapp.jar
```

Environment variable names follow the canonical rule, removing `-` and turning `.` into `_`. In this example, `max-retries` can receive `0`, `audit-enabled` can receive `false`, and `connect-timeout` can receive `750ms`.

**Note on collection precedence:** if you override list elements using higher-precedence environment variables, the List may be replaced entirely; do not rely on assuming only `endpoints[0].base-url` is replaced while properties or elements from lower-precedence sources are automatically merged. When overriding a list, provide the full structure from the higher-precedence source or design the configuration as a Map if you want key-based merging.

### 11.6. Using in a service

```java
package com.example.demo.service;

import com.example.demo.config.CatalogProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CatalogProperties properties;

    public CatalogService(CatalogProperties properties) {
        this.properties = properties;
    }

    public void showEffectiveSettings() {
        System.out.println(properties.getDisplayName());
        System.out.println(properties.getMaxRetries());
        System.out.println(properties.isAuditEnabled());
        System.out.println(
                properties.getHttpClient().getConnectTimeout());
        System.out.println(
                properties.getRoutes().get("/api/v1"));
    }
}
```

The example above prints only non-sensitive values. Do not log passwords, API keys, tokens, or the entire `Environment` in a real application.

## 12. When multiple sources use different names for the same property

Suppose:

```properties
# application.properties
catalog.max-retries=5
```

Environment variable:

```bash
CATALOG_MAXRETRIES=3
```

Command line:

```bash
java -jar myapp.jar --catalog.max-retries=0
```

With Spring Boot 3.3's default PropertySource precedence, the command line takes precedence over OS environment and Config Data. The final value can be `maxRetries=0`.

**Do not confuse the two mechanisms:**

1. **Relaxed binding:** `catalog.max-retries` and `CATALOG_MAXRETRIES` can map to the same Java property `maxRetries`.
2. **PropertySource precedence:** which source wins when two or more sources can provide a value for that property.

Different names do not mean two independent settings. And `0` is an explicit value that can override `5` or `3`; it is not a "not configured" signal.

### Do not declare duplicate aliases in the same file

Example to avoid:

```properties
catalog.max-retries=3
catalog.maxRetries=5
catalog.max_retries=7
```

These lines target the same Java property meaning, creating ambiguity about effective value and source origin. Write only:

```properties
catalog.max-retries=3
```

If multiple overrides are needed, use **clear configuration sources** per environment and rely on precedence rather than creating multiple aliases in one file as an ordering trick.

## 13. Canonical names for nested structures

### Nested JavaBean

Java:

```java
public class Logging {
    private boolean includeRequestId;
    public boolean isIncludeRequestId() { return includeRequestId; }
    public void setIncludeRequestId(boolean value) {
        includeRequestId = value;
    }
}
```

If the parent has a `logging` property, the canonical path can be:

```properties
catalog.logging.include-request-id=true
```

YAML:

```yaml
catalog:
  logging:
    include-request-id: true
```

Environment variable:

```bash
CATALOG_LOGGING_INCLUDEREQUESTID=true
```

### Nested Map

Java:

```java
private Map<String, ServiceConfig> services;
```

Config:

```properties
catalog.services.billing.base-url=https://billing.example.test
catalog.services.inventory.base-url=https://inventory.example.test
```

Where:

- `catalog.services` is the path to the Map.
- `billing` and `inventory` are **Map keys**.
- `base-url` is the canonical name for the Java property `baseUrl` of `ServiceConfig`.

If a Map key contains dots or slashes, consider dedicated bracket notation as described in the Map keys section.

### Map containing a List

Java:

```java
private Map<String, List<String>> allowedRegionsByService;
```

Config:

```properties
catalog.allowed-regions-by-service.billing[0]=vn
catalog.allowed-regions-by-service.billing[1]=sg
catalog.allowed-regions-by-service.inventory[0]=vn
```

Here `allowed-regions-by-service` is the canonical name of the Java property `allowedRegionsByService`; `billing`/`inventory` are Map keys, and `[0]`/`[1]` are List indexes. Each segment type in a property path has its own meaning; do not apply a single hyphen-replacement rule across the entire structure.

## 14. Interaction with constructor binding and records

Relaxed binding is not limited to JavaBeans with setters. Spring Boot 3.3 can also bind records or classes using constructor binding.

Example:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("3s") Duration requestTimeout,
        @DefaultValue("3") int maxRetries) {
}
```

File:

```properties
checkout.enabled=true
checkout.request-timeout=5s
checkout.max-retries=0
```

Environment:

```bash
CHECKOUT_ENABLED=true
CHECKOUT_REQUESTTIMEOUT=5s
CHECKOUT_MAXRETRIES=0
```

The Binder recognizes `request-timeout` to pass to constructor parameter `requestTimeout` and `max-retries` for `maxRetries`, even without setters. Canonical property names remain the same.

`@DefaultValue` can be used on constructor-binding parameters when the corresponding property is **not found**. Having a default does not turn an explicit `false`/`0` into missing. With JavaBean binding, field initializers are a different default mechanism.

**Note:** `@ConfigurationProperties` constructor binding is supported for beans registered via appropriate configuration-properties mechanisms, such as `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. It does not apply automatically to every bean created by `@Component` or a regular `@Bean` factory method.

## 15. Hyphens, underscores, and whitespace: putting them in the right place

### 15.1. Kebab-case is for names, it does not alter values

```properties
app.display-name=Hello World
```

`display-name` is the **property name**, while `Hello World` is the **value**. Relaxed binding only maps the name to the Java property; it does not turn the value into `hello-world` or strip whitespace.

### 15.2. Underscores in files do not mean environment-variable rules

```properties
app.max_retries=3
```

can be recognized by the Binder as a variant of `app.max-retries`, but the canonical environment variable is still:

```text
APP_MAXRETRIES
```

not `APP_MAX_RETRIES`. Underscores `_` in OS environment names represent hierarchy dots; do not use them to replace every separator from a `.properties` file.

### 15.3. Java snake_case and non-standard naming

In Java, you could write a `max_retries` field, but JavaBean property names and getters/setters become unnatural. Use `maxRetries` in Java, `max-retries` in configuration files, and `MAXRETRIES` in the final segment of the corresponding environment variable.

### 15.4. Unusual characters in Map keys

When a Map key is literally the path `/api/v1`, do not turn it into a Java property name `apiV1`. The key is data: use `[/api/v1]` in a property path or `"[/api/v1]"` in YAML. This preserves routing behavior and prevents unwanted key sanitization.

## 16. Configuration metadata and benefits of canonical names

Spring Boot provides **configuration metadata** so IDEs can offer property suggestions, inspect property descriptions, and display documentation for `@ConfigurationProperties`.

With Maven, you can declare the processor as a build-purpose dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

With Gradle (e.g., the Java plugin):

```groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-configuration-processor"
}
```

Depending on your project's build configuration and version management, ensure the version is managed compatibly with Spring Boot 3.3.

The processor can generate metadata in:

```text
META-INF/spring-configuration-metadata.json
```

Properties are described in names following the convention, such as `catalog.display-name`, `catalog.max-retries`, and `catalog.http-client.connect-timeout`.

Metadata helps tooling assist config file authors, but it is not required for the Binder to work at runtime. Do not rely on an IDE squiggle alone as proof that the runtime Binder will or will not bind a name; examine the Java model, property path, and actual PropertySources.

## 17. When relaxed binding cannot rescue a configuration

### Case A — Wrong prefix

```java
@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties { /* ... */ }
```

```properties
payments.max-retries=3
```

The property `payments.max-retries` does not automatically bind to `catalog.maxRetries` just because both contain the `max-retries` segment. Relaxed binding supports **spelling variants of the same logical name**, not changing prefixes with different business meanings.

### Case B — Non-equivalent property name

```java
private int maxRetries;
```

```properties
catalog.retry-limit=3
```

`retry-limit` is not the same name as `maxRetries`. To use that name, rename the Java property to `retryLimit`, change the file to `catalog.max-retries`, or build explicit alias logic at the application layer.

### Case C — JavaBean missing a setter

```java
private String displayName;
public String getDisplayName() { return displayName; }
```

Even though `catalog.display-name=Catalog` has the right name, standard JavaBean binding cannot update a getter-only scalar without a setter. Add `setDisplayName(...)` or use constructor binding.

### Case D — Unregistered bean

Merely annotating a class with `@ConfigurationProperties` does not guarantee Boot scans it. Without `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an appropriate bean registration method, no bean is bound. The error is not in `maxRetries`/`max-retries` spelling.

### Case E — Unconvertible value

```properties
catalog.max-retries=unlimited
```

Even with the right name, `unlimited` does not convert to `int` under standard rules. The Binder may report a conversion error. Do not attribute a type conversion failure to relaxed binding.

### Case F — Map key losing characters

```properties
catalog.routes./api/v1=frontend
```

The name looks like a property path, but if the goal is the literal Map key `/api/v1`, write:

```properties
catalog.routes.[/api/v1]=frontend
```

### Case G — Incorrectly written environment variable

```text
APP_HTTP_CLIENT_CONNECT_TIMEOUT
```

This name is typically interpreted with different hierarchy boundaries than intended for `app.http-client.connect-timeout`. Use the canonical form:

```text
APP_HTTPCLIENT_CONNECTTIMEOUT
```

This mistake is especially common when someone simply converts every `-` and `.` into `_`.

### Case H — Using camelCase in a `@Value` placeholder

```java
@Value("${catalog.maxRetries:3}")
private int maxRetries;
```

May not leverage canonical property name lookup as fully as:

```java
@Value("${catalog.max-retries:3}")
private int maxRetries;
```

Use the canonical form in placeholders.

### Case I — Confusing empty with missing

```properties
catalog.display-name=
```

`""` is an explicit empty String, not "undeclared". An empty value can override a value from another source; placeholder defaults are generally used only when the property is not found. Relaxed binding does not automatically replace empty with a default.

### Case J — Multiple sources for the same property

```properties
# application.properties
catalog.max-retries=5
```

```bash
CATALOG_MAXRETRIES=1 java -jar myapp.jar
```

The Binder can recognize both names as the same Java property, while the outcome depends on PropertySource precedence. This is expected behavior; identify the higher-precedence source rather than renaming the Java field from `maxRetries` to `max_retries` to work around it.

## 18. Diagnosing binding errors systematically

When a Java field does not receive the expected value, follow this order:

1. **Verify the prefix:** `@ConfigurationProperties(prefix="catalog")` must match the start of the configuration path.
2. **Write the canonical name:** convert Java camelCase to kebab-case at each level, e.g., `httpClient.connectTimeout` → `http-client.connect-timeout`.
3. **Check the source type:** `.properties`, YAML, JVM `-D`, CLI, or OS environment? Apply the corresponding naming rule, especially **removing `-`** in environment variables.
4. **Check nested paths:** dots separate hierarchy levels, Lists have `[i]`, and Map keys use brackets when needed.
5. **Check bean registration:** has scan/enable/component/factory created the bean?
6. **Check binding strategy:** is JavaBean setter or constructor binding appropriate?
7. **Check conversion:** can the value be converted to the Java type (`Duration`, `DataSize`, `Boolean`, enum…)?
8. **Check precedence:** an OS env var, JVM property, test property, or CLI argument may override the file.
9. **Inspect configuration sources:** use `Environment` or secured Actuator endpoints to find the effective property and its source.
10. **Standardize names for long-term config:** avoid multiple alias variants that complicate debugging; keep one canonical property name in READMEs and source files.

### Minimal diagnostic snippet

```java
package com.example.demo.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ConfigDiagnostics {

    @Bean
    ApplicationRunner showConfig(
            Environment environment,
            CatalogProperties catalog) {

        return args -> {
            String key = "catalog.max-retries";
            System.out.println("Resolved raw value: "
                    + environment.getProperty(key));
            System.out.println("Bound JavaBean value: "
                    + catalog.getMaxRetries());
        };
    }
}
```

If `environment.getProperty(key)` has the expected value while the bean does not, check bean registration, conversion, and binding mechanics. If the raw value is absent or unexpected, inspect Config Data locations, exact environment variable names, and PropertySource order.

Do not print secrets to logs. With Actuator, you can consult `/actuator/configprops` and `/actuator/env`, provided proper security and sanitization are configured.

## 19. Conversion formula reference table

| Java or meaning | Canonical `.properties` | YAML key by level | Environment variable |
| --- | --- | --- | --- |
| `displayName` under `catalog` | `catalog.display-name` | `catalog:` → `display-name:` | `CATALOG_DISPLAYNAME` |
| `maxRetries` under `catalog` | `catalog.max-retries` | `catalog:` → `max-retries:` | `CATALOG_MAXRETRIES` |
| `httpClient.connectTimeout` | `catalog.http-client.connect-timeout` | `http-client:` → `connect-timeout:` | `CATALOG_HTTPCLIENT_CONNECTTIMEOUT` |
| `logging.includeRequestId` | `catalog.logging.include-request-id` | `logging:` → `include-request-id:` | `CATALOG_LOGGING_INCLUDEREQUESTID` |
| `servers[0].baseUrl` | `catalog.servers[0].base-url` | `servers:` → `- base-url:` | `CATALOG_SERVERS_0_BASEURL` |
| `servers[1].enabled` | `catalog.servers[1].enabled` | `servers:` → `- enabled:` | `CATALOG_SERVERS_1_ENABLED` |
| `routes["/api/v1"]` | `catalog.routes.[/api/v1]` | `routes:` → `"[/api/v1]":` | Prefer Config Data to preserve special keys |
| `Map<String,Object> metadata["a.b"]` | `catalog.metadata.[a.b]` | `metadata:` → `"[a.b]":` | Prefer Config Data for dotted keys that must be preserved |

### One-line cheat sheet

```text
Java camelCase  →  file lowercase kebab-case
file with .     →  env replaces . with _
file with -     →  env REMOVES -
List [0]        →  env _0_
Special Map key →  file uses [key], YAML quotes "[key]"
@Value          →  placeholder uses canonical name
```

## 20. Practice questions

### Question 1. Correct conversion to OS environment

Canonical property:

```properties
payments.card-reader.read-timeout=250ms
```

What is the canonical environment variable name?

**Answer:**

```text
PAYMENTS_CARDREADER_READTIMEOUT
```

Not `PAYMENTS_CARD_READ_READ_TIMEOUT`. Both `card-reader` and `read-timeout` drop `-`.

### Question 2. Environment variable for a List

Canonical:

```properties
app.backends[2].base-url=https://three.example.test
```

Environment variable name:

```text
APP_BACKENDS_2_BASEURL
```

Index `2` is placed between underscores; `base-url` drops the hyphen.

### Question 3. Is the Map key `/prod/api` preserved as-is?

Configuration:

```properties
app.routes./prod/api=payment
```

You should not expect the Map key to preserve `/`. Write:

```properties
app.routes.[/prod/api]=payment
```

Or in YAML:

```yaml
app:
  routes:
    "[/prod/api]": payment
```

### Question 4. Why does `@Value` use kebab-case?

So that placeholders like `${app.max-retries:3}` take full advantage of Spring Boot's canonical property name lookup logic. When using camelCase in placeholders, some variants from files or environment variables may not be evaluated the same way as with the Binder.

### Question 5. Do two configuration names for one target add together?

```properties
app.max-retries=3
```

```bash
APP_MAXRETRIES=0
```

Both can bind to Java `maxRetries`, but their values do not "add up". The higher-precedence source determines the value; in typical setups, OS environment overrides Config Data, so `maxRetries=0`.

## 21. Project configuration naming checklist

- [ ] All property names in READMEs and Config Data use lowercase kebab-case.
- [ ] `@ConfigurationProperties` prefixes use canonical form, e.g., `billing.http-client`.
- [ ] JavaBean fields/record components use camelCase, e.g., `readTimeout`.
- [ ] Do not place multiple variants `read-timeout`, `readTimeout`, `read_timeout` for the same key in one source.
- [ ] Deployment scripts convert `.` to `_`, **remove `-`**, then uppercase.
- [ ] List indexes in environment variables use `_0_`, `_1_`...
- [ ] Map keys containing special characters use `[key]` and YAML quotes `"[key]"`.
- [ ] `@Value` placeholders use canonical names.
- [ ] Do not confuse conversion/registration/precedence errors with relaxed binding errors.
- [ ] When renaming a user-facing property, plan for compatibility and update docs; do not rely on relaxed binding to turn two different logical names into aliases.
- [ ] Avoid exposing secrets in logs or example documentation.
- [ ] Have application-level tests for critical environment variable names before deployment.

## 22. References

- **Spring Boot 3.3 Reference — Externalized Configuration**, sections *Type-safe Configuration Properties*, *Relaxed Binding*, *Binding From Environment Variables*, *Binding Maps*, *Property Placeholders*, and *PropertySource Order*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 Reference — Configuration Metadata**, how metadata describes canonical property names: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- **Spring Boot 3.3 API — `@ConfigurationProperties`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Boot 3.3 API — `ConfigurationPropertyName`**, configuration property name and hierarchy model: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertyName.html

**Summary:** Relaxed binding helps Spring Boot bind different name spellings to **the same Java property**, but it does not bypass prefixes, List/Map structure, conversion, or PropertySource precedence. Standardize names in files and placeholders to **lowercase kebab-case**, convert to OS environment variables using **dot → underscore, dash → remove, uppercase**, and use `[key]` when a Map must preserve special characters.
