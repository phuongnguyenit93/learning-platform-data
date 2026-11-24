# Nested References and Building Values from Multiple Properties

## 1. From a Single Configuration Value to a Composed Value

In Spring Boot, externalized configuration does not have to contain only independent strings. A service address is often built from a host name, port, path, and deployment environment. If you copy that full URL across multiple files, every host or port change requires updating many places; it is easy to miss one or introduce inconsistent values.

For example, an order service has these components:

```text
Host          = localhost
Port          = 8081
API prefix    = /api/v1
Order path    = /orders

Final URL     = http://localhost:8081/api/v1/orders
```

Spring lets you express this dependency using **placeholders** of the form `${property.name}`. When a value is read through the placeholder resolution mechanism, Spring looks up the referenced property and replaces `${...}` with the corresponding value. You can combine fixed text, multiple placeholders, and nested placeholders.

```text
application.yml
   |
   +-- client.host = localhost
   +-- client.port = 8081
   +-- client.api-prefix = /api/v1
   +-- client.orders-url =
           "http://${client.host}:${client.port}${client.api-prefix}/orders"
   |
   v
Environment and placeholder resolution mechanism
   |
   v
"http://localhost:8081/api/v1/orders"
   |
   v
@Value, @ConfigurationProperties, or configuration-consuming code
```

This lesson explains single references, building values from multiple properties, dynamic key references, default values, and common pitfalls. It is important to distinguish **the declared string**, **the value after placeholder resolution**, and **the final value bound into a bean**.

## 2. Basic Placeholder: ${property.name}

Example in `src/main/resources/application.yml`:

```yaml
client:
  host: localhost
  port: 8081
  api-prefix: /api/v1
  orders-url: "http://${client.host}:${client.port}${client.api-prefix}/orders"
```

When Spring resolves `client.orders-url`, the expected result is:

```text
http://localhost:8081/api/v1/orders
```

A string can contain multiple placeholders in any position:

```properties
app.name=checkout
app.region=ap-southeast-1
app.instance-id=${app.name}-${app.region}
```

The result of `app.instance-id` is `checkout-ap-southeast-1`.

The `${client.host}` part means **look up the property with key `client.host`**. It is not a Java method call and not a YAML variable. Spring Boot loads configuration sources as `PropertySource` instances, and the property/placeholder resolution mechanism uses the effective sources.

### 2.1. Reading the Result with Environment

Create a simple observation application:

```java
package com.example.placeholderlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class PlaceholderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showValues(Environment environment) {
        return args -> {
            System.out.println("orders-url = "
                + environment.getProperty("client.orders-url"));
        };
    }
}
```

With standard Spring Boot sources, `Environment.getProperty("client.orders-url")` can return the string with placeholders resolved, provided all required references have values or valid defaults.

Raw values can still exist inside a `PropertySource` as text containing `${...}`. Do not infer that as soon as YAML is loaded, Spring Boot rewrites the file contents or replaces every placeholder directly inside the data source. **Placeholder resolution is a step in accessing or injecting the value into the application.**

### 2.2. Injecting into a Bean with @Value

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class OrdersClientSettings {

    private final String ordersUrl;

    public OrdersClientSettings(
            @Value("${client.orders-url}") String ordersUrl) {
        this.ordersUrl = ordersUrl;
    }

    public String ordersUrl() {
        return ordersUrl;
    }
}
```

Spring processes the placeholder when creating the bean and supplies the value via the constructor. The bean simply uses `ordersUrl` without needing to know it came from a string composed of four parts in YAML.

You can also compose directly in the annotation:

```java
@Value("http://${client.host}:${client.port}/health")
private String healthUrl;
```

However, when the same address is used by multiple beans, place the formula in configuration or a shared configuration object to avoid repeating key strings across many Java classes.

## 3. Distinguishing Placeholders with Default Values

Common default syntax:

```text
${property.name:default-value}
```

If `property.name` is not found, the resolver uses the part after the colon.

Example:

```yaml
client:
  host: "${CLIENT_HOST:localhost}"
  port: "${CLIENT_PORT:8081}"
  orders-url: "http://${client.host}:${client.port}/api/v1/orders"
```

When `CLIENT_HOST` and `CLIENT_PORT` environment variables are absent, the result is `http://localhost:8081/api/v1/orders`. If those two environment variables exist, their corresponding values are used.

Note: `CLIENT_HOST` is used directly here inside the placeholder as a key; for regular application properties, prefer **canonical kebab-case** names in references, such as `${client.host}`, so Spring Boot can apply relaxed binding consistently with sources like environment variables. A cleaner organization is to set `client.host=localhost` as the default and let the conventional environment variable `CLIENT_HOST` override `client.host` from another source.

Recommended example:

```yaml
client:
  host: localhost
  port: 8081
  orders-url: "http://${client.host}:${client.port}/api/v1/orders"
```

At deployment time:

```bash
CLIENT_HOST=orders.internal CLIENT_PORT=9090 java -jar app.jar
```

Spring Boot can map these environment variables to `client.host` and `client.port`. After lookup, the URL becomes `http://orders.internal:9090/api/v1/orders` in the example without modifying `client.orders-url` in the file.

### 3.1. Default for a Component vs. Default for the Entire String

The following two approaches have different meanings.

**Per-component default:**

```properties
client.host=localhost
client.url=http://${client.host}:${client.port:8081}/api
```

If `client.port` is absent, `8081` is used, while host still comes from `client.host`.

**Default for the entire address:**

```properties
client.resolved-url=${client.explicit-url:http://localhost:8081/api}
```

Here, when `client.explicit-url` is missing, the entire default string is used. The `http://` part contains a colon, but it remains part of the **default value** after the first delimiter.

Do not interpret `:` inside a placeholder as YAML syntax or a port separator. In `${client.port:8081}`, the colon belongs to the fallback syntax; in `http://${client.host}:${client.port}`, the colons outside the placeholders are literal URL text.

### 3.2. Missing Values, Empty Values, and Defaults

When a value is **absent** from configuration sources, a placeholder with a default can take the value after the `:`. However, a property declared as an empty string is not always equivalent to an absent property:

```properties
client.host=
client.url=http://${client.host:localhost}:8081/api
```

In a scenario where the resolver receives an empty string, `client.host` is considered **present**, so `localhost` may not be chosen; the resulting URL becomes `http://:8081/api`. Thus, a default does not check for empty strings, valid URLs, or business validity.

For required data, combine with `@ConfigurationProperties` validation or an appropriate verification mechanism.

## 4. Building a Value from Multiple Properties

Suppose an application needs an API address, a health check address, and a documentation address for the same service. We can declare the shared components:

```yaml
catalog:
  scheme: https
  host: catalog.example.invalid
  port: 8443
  base-path: /v1

  base-url: "${catalog.scheme}://${catalog.host}:${catalog.port}${catalog.base-path}"
  products-url: "${catalog.base-url}/products"
  health-url: "${catalog.scheme}://${catalog.host}:${catalog.port}/health"
```

Resolved values:

```text
catalog.base-url
  = https://catalog.example.invalid:8443/v1

catalog.products-url
  = https://catalog.example.invalid:8443/v1/products

catalog.health-url
  = https://catalog.example.invalid:8443/health
```

`catalog.products-url` references `catalog.base-url`, which in turn contains four other placeholders. This is a **multi-level dependency chain**. The resolver can continue resolving placeholders within referenced values to return the final URL.

```text
catalog.products-url
     |
     +-- catalog.base-url
               |
               +-- catalog.scheme
               +-- catalog.host
               +-- catalog.port
               +-- catalog.base-path
     |
     +-- string "/products"
     |
     v
https://catalog.example.invalid:8443/v1/products
```

Keep dependency graphs shallow and key names meaningful. If a value has to pass through too many layers, operators will have a hard time determining which source produced the final URL.

### 4.1. Why Compose Values in Configuration?

This is useful when parts have different lifecycles. For example, `catalog.host` varies by machine, whereas `catalog.base-path` is a stable service convention. When a higher-precedence source overrides `catalog.host`, URLs referencing that value can also pick up the new host upon resolution.

Do not copy full addresses into multiple lines or files:

```properties
catalog.products-url=https://catalog.example.invalid:8443/v1/products
catalog.categories-url=https://catalog.example.invalid:8443/v1/categories
catalog.inventory-url=https://catalog.example.invalid:8443/v1/inventory
```

If only the host changes, all three lines must be edited. Referencing a single `catalog.base-url` makes the intent clearer and reduces the risk of configuration drift.

However, if the URLs genuinely differ in how they are constructed—for instance, involving proxies, URL signing, paths computed by business logic, or parameter encoding rules—use appropriate Java code instead of trying to turn configuration into a programming language.

## 5. Two Kinds of "Nesting" to Distinguish

The term *nested* is often confused between **chained references** and **a placeholder inside the name of another placeholder**.

### 5.1. Chained References: Value A Leads to B Leads to C

```properties
service.host=localhost
service.base-url=http://${service.host}:8080
service.orders-url=${service.base-url}/orders
```

Here:

```text
service.orders-url
  -> service.base-url
      -> service.host
```

The placeholders do not have to be inside the same pair of braces, yet resolving one value triggers resolving the value it references.

### 5.2. Placeholder Nested in a Key Name: Dynamic Key Selection

Suppose the application declares endpoints for three regions:

```properties
payments.targets.dev=http://localhost:9000
payments.targets.staging=https://staging-payments.example.invalid
payments.targets.prod=https://payments.example.invalid
payments.selected=staging
payments.endpoint=${payments.targets.${payments.selected}}
```

The expression:

```text
${payments.targets.${payments.selected}}
```

is evaluated in two steps:

1. Resolve the **inner** placeholder: `${payments.selected}` → `staging`.
2. Form the **outer** key name: `payments.targets.staging`, then look up that key → `https://staging-payments.example.invalid`.

Result for `payments.endpoint`:

```text
https://staging-payments.example.invalid
```

This is a **dynamic key reference**. If you change `payments.selected` to `prod` and restart the application, the outer expression points to `payments.targets.prod`. Distinguish this from string concatenation `${payments.host}/api`: in a dynamic key, the inner placeholder's value becomes **part of the property name to look up**.

Equivalent YAML example:

```yaml
payments:
  selected: staging
  targets:
    dev: http://localhost:9000
    staging: https://staging-payments.example.invalid
    prod: https://payments.example.invalid

  endpoint: "${payments.targets.${payments.selected}}"
```

The string has two opening `${` and two closing `}`. Do not omit the trailing brace or mistakenly write `${payments.targets}.${payments.selected}`: the latter merely **concatenates two values** rather than selecting a key under the `payments.targets.*` branch.

## 6. Combining Dynamic Keys with Default Values

When the selected key might be missing, design the fallback clearly.

Example:

```properties
payments.selected=preview
payments.targets.dev=http://localhost:9000
payments.targets.prod=https://payments.example.invalid
payments.endpoint=${payments.targets.${payments.selected}:http://localhost:9099}
```

Resolution:

1. `payments.selected` → `preview`.
2. The outer key name becomes `payments.targets.preview`.
3. That key is not present in the example's sources.
4. The default value of the outer placeholder is `http://localhost:9099`.

The result is:

```text
http://localhost:9099
```

You can also set a default for the **selected name**:

```properties
payments.targets.dev=http://localhost:9000
payments.selected-endpoint=${payments.targets.${payments.selected:dev}}
```

If `payments.selected` is absent, the inner placeholder uses `dev`, and the outer one looks up `payments.targets.dev`. However, if `payments.selected=preview` while `payments.targets.preview` is absent, the default `dev` on the **inner** placeholder does not rescue the missing outer key.

Two different kinds of missing values:

| What is missing? | Placeholder with default | Is default applied? |
| --- | --- | --- |
| `payments.selected` | `${payments.selected:dev}` | Yes, selects `dev` |
| `payments.targets.preview` | `${payments.targets.${payments.selected}:http://localhost:9099}` | Yes, uses fallback URL |
| `payments.targets.preview` when only `selected` has a default | `${payments.targets.${payments.selected:dev}}` | No fallback for the outer key |

Using both default levels makes the expression harder to read. Usually it is better to separate an environment-selector property with a safe default while allowing only validated `selected` values. For choices affecting transactions, consider **failing when configuration is missing** instead of silently calling a fallback endpoint.

## 7. Which Configuration Source Is Used When a Component Is Overridden?

Spring Boot allows the same key to be declared in multiple sources. When resolving `${catalog.host}`, the resolver uses the effective value of that key according to `Environment`.

Suppose the JAR contains:

```yaml
catalog:
  scheme: http
  host: localhost
  port: 8080
  base-url: "${catalog.scheme}://${catalog.host}:${catalog.port}"
```

When running:

```bash
java -jar app.jar --catalog.host=catalog.internal --catalog.port=9090
```

assuming no other source has higher precedence, the result is:

```text
catalog.base-url = http://catalog.internal:9090
```

`catalog.base-url` is still declared in YAML. But the inner placeholders pick up the effective values of `catalog.host` and `catalog.port` from command-line arguments. This is why one **configuration formula** can work across environments: its components receive values from different sources.

You can also override **the entire target key**:

```bash
java -jar app.jar --catalog.base-url=https://gateway.example.invalid/catalog
```

In this case, the application can read the complete URL from the command-line argument without using the YAML formula for that key. Therefore, when the final value differs from expectations, inspect both **the target key** and **the component keys**, not just one configuration file.

### Profile Combination Example

```yaml
# application.yml
catalog:
  host: localhost
  port: 8080
  base-url: "http://${catalog.host}:${catalog.port}"
```

```yaml
# application-prod.yml
catalog:
  host: catalog.internal
  port: 9090
```

Run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Under standard configuration and with no other overrides, `catalog.base-url` receives `http://catalog.internal:9090`. Profiles select which configuration sources are loaded; placeholders use the effective values from those sources. **Profiles do not alter `${...}` syntax.**

## 8. A Complete Example with @ConfigurationProperties

For multiple related properties, bind them into a typed class and inject that class into services via dependency injection.

`application.yml`:

```yaml
shipping:
  scheme: https
  host: shipping.example.invalid
  port: 8443
  root-path: /api
  rates-url: "${shipping.scheme}://${shipping.host}:${shipping.port}${shipping.root-path}/rates"
  labels-url: "${shipping.scheme}://${shipping.host}:${shipping.port}${shipping.root-path}/labels"
```

Java record:

```java
package com.example.placeholderlab;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        String scheme,
        String host,
        int port,
        String rootPath,
        URI ratesUrl,
        URI labelsUrl
) {}
```

Register on the application class:

```java
package com.example.placeholderlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ShippingProperties.class)
public class PlaceholderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderLabApplication.class, args);
    }
}
```

Bean consuming the configuration object:

```java
package com.example.placeholderlab;

import org.springframework.stereotype.Service;

@Service
public class ShippingClientSettings {
    private final ShippingProperties properties;

    public ShippingClientSettings(ShippingProperties properties) {
        this.properties = properties;
    }

    public String ratesUrl() {
        return properties.ratesUrl().toString();
    }

    public String labelsUrl() {
        return properties.labelsUrl().toString();
    }
}
```

The Spring Boot `Binder` processes the `shipping.*` group, converts the post-placeholder URI strings to `java.net.URI`, and provides the configuration object to the bean. In this example, the service does not need to know which keys `shipping.rates-url` was composed from; it simply receives a bound URI.

However, for URLs requiring parameter encoding, dynamic path handling, or complex query string assembly, prefer APIs like `URI`, `UriComponentsBuilder`, or an appropriate HTTP client at runtime. Placeholders are convenient for **static configuration values**, not a full replacement for proper URL construction.

## 9. Dynamic Key Experiment: Changing the Selector and Observing Results

Set up a small hands-on exercise with the file:

```yaml
lookup:
  selected: dev

  endpoints:
    dev: http://localhost:8085
    staging: https://staging.example.invalid
    prod: https://prod.example.invalid

  base-url: "${lookup.endpoints.${lookup.selected}}"
  health-url: "${lookup.base-url}/health"
```

In an `ApplicationRunner`, you can print:

```java
@Bean
ApplicationRunner report(Environment environment) {
    return args -> {
        System.out.println(
            "selected = " + environment.getProperty("lookup.selected")
        );
        System.out.println(
            "base-url = " + environment.getProperty("lookup.base-url")
        );
        System.out.println(
            "health-url = " + environment.getProperty("lookup.health-url")
        );
    };
}
```

Place the `@Bean` method in a `@Configuration` or `@SpringBootApplication` class, and ensure `ApplicationRunner`, `Bean`, and `Environment` are imported.

### Run A: Default dev

```bash
java -jar app.jar
```

Expected:

```text
selected = dev
base-url = http://localhost:8085
health-url = http://localhost:8085/health
```

Here, `lookup.selected` → `dev`; the outer key name becomes `lookup.endpoints.dev`; the health URL in turn references `lookup.base-url`.

### Run B: Select staging on the Command Line

```bash
java -jar app.jar --lookup.selected=staging
```

Expected:

```text
selected = staging
base-url = https://staging.example.invalid
health-url = https://staging.example.invalid/health
```

Not a single line in YAML was changed. Only the single `lookup.selected` key was overridden, yet two derived values changed because they depend on the selected key.

### Run C: Select prod and Override the prod Endpoint

```bash
java -jar app.jar \
  --lookup.selected=prod \
  --lookup.endpoints.prod=https://private-gateway.example.invalid
```

Expected:

```text
selected = prod
base-url = https://private-gateway.example.invalid
health-url = https://private-gateway.example.invalid/health
```

This experiment has **two dynamic levels**: the selector determines which key is read, and the higher-precedence source determines that key's value.

### Run D: Select a Value Not in the Map

```bash
java -jar app.jar --lookup.selected=unknown
```

Now the outer placeholder attempts to look up `lookup.endpoints.unknown`. Because the sample YAML does not have that key and defines no fallback, resolution can fail with an unresolved placeholder error when the value is accessed or bound. Depending on where and when the property is used, the error can occur during bean startup or when code accesses the property.

In real applications, you should **validate the input selector** or design an explicit fallback. Do not assume Spring will pick `dev` just because `dev` is first in the list.

## 10. Inspecting All Three Layers: Source, Placeholder, and Bean

When a bean receives an incorrect URL, ask three questions in order:

```text
Configuration sources
  - What is the value of "lookup.selected"?
  - Where does "lookup.endpoints.prod" come from?
             |
             v
Placeholder resolution
  - What is the dynamic key after substituting "selected"?
  - Does the target value contain other chained placeholders?
             |
             v
Bean
  - Which key is the bean using?
  - What is the target Java type?
  - At what point is the value initialized?
```

For example, if `lookup.base-url` comes from the command line instead:

```bash
java -jar app.jar --lookup.base-url=https://override.example.invalid
```

then even with `lookup.selected=dev`, the received URL can still be `https://override.example.invalid`. The reason is that **the target key `lookup.base-url` was overridden directly**, so the YAML formula is no longer the effective value.

If a `@ConfigurationProperties` field is initialized when the context starts, editing the YAML file while the process is running **does not guarantee** the bean is updated. In hands-on experiments, restart the process after each configuration change to observe a stable state.

## 11. Placeholders Differ from Spring Expression Language (SpEL)

Two common syntaxes in Spring:

```text
${server.port:8080}         -> placeholder: look up property
#{2 * 3}                    -> SpEL: evaluate expression
```

Placeholders find and substitute values from configuration. SpEL is an expression language capable of performing calculations or accessing components within a permitted context. **Do not equate the two syntaxes.**

For example, `@Value("${client.port:8080}")` uses a property placeholder to retrieve a configured port. `@Value("#{2 * 3}")` asks Spring to evaluate an expression to `6`. Both can appear in `@Value`, whereas Spring Boot `@ConfigurationProperties` binding has its own mechanisms and limits; do not assume every configuration value in YAML is executed as SpEL.

If complex calculations or decisions are needed, it is clearer and more testable to handle them in Java code rather than trying to build a long expression tree in configuration files.

## 12. Difference Between Spring Placeholders and Shell Interpolation

The `${...}` notation also appears in some shells, CI/CD tools, or template systems. However, when present **in Spring Boot YAML or properties files**, placeholders are resolved by Spring when configuration is accessed.

When passed through a shell, `$` can be processed by the shell first. For example in Bash, the command:

```text
java -jar app.jar --client.url=${client.host}
```

may be interpreted by the shell according to its own syntax or expanded unintentionally. If you want to pass a **literal** placeholder for Spring to process, quote it properly for the shell, for example:

```bash
java -jar app.jar '--client.url=http://${client.host}:8080'
```

In PowerShell, single quotes also prevent variable expansion inside the string:

```powershell
java -jar app.jar '--client.url=http://${client.host}:8080'
```

It is usually easier to put the placeholder formula in `application.yml` and only pass the components you want to override on the command line.

Also distinguish Spring Boot placeholders from build-time substitution in Maven/Gradle or deployment-time substitution in Helm/Kubernetes. If another tool already replaced text before the application starts, Spring will not necessarily see the original placeholder syntax. Determine **which tool owns interpolation** to avoid resolving the same variable in two different phases.

## 13. Conditions Where References May Fail to Resolve

### 13.1. Referenced Key Is Absent

```properties
client.url=http://${client.host}:8080
```

If `client.host` is missing and there is no fallback, resolution can fail when the bean is created or when the property is accessed. The error usually names the missing placeholder. Fix by declaring a valid source or designing an appropriate default.

### 13.2. Referenced Key Is Misspelled

For instance, the file declares `client.hostname`, but the formula uses `${client.host}`. Spring will not automatically infer that the two key names are the same. Standardize the name and prefer canonical form compatible with Spring Boot's relaxed binding mechanism.

### 13.3. Reference Cycles

Do not create cycles such as:

```properties
a.value=${b.value}
b.value=${a.value}
```

Or self-references:

```properties
a.value=${a.value}
```

The resolver cannot derive a finite final value from an infinite loop. Spring usually reports an error when encountering a cycle during resolution. Do not treat fallbacks as a valid way to design cyclic dependencies. Organize keys in the direction **base values → derived values**, never pointing back to base values.

### 13.4. Overly Deep Multi-Level References

```text
url.current
  -> url.alias
      -> url.region
          -> url.host-by-region
              -> url.host
```

The longer the dependency chain, the harder it is to read and debug. If multiple conditions must be combined, move to a typed configuration class and compute derived values in Java.

### 13.5. Empty Configuration Where Fallback Does Not Run

```properties
service.path=
service.url=http://localhost:8080${service.path:/api}
```

If `service.path` actually exists with an empty value, the result will not necessarily include `/api`. Standard placeholder fallbacks handle **missing keys**, not every unsatisfactory value. Validate input data rather than relying on fallbacks for validation.

### 13.6. URI Composition Creating Extra or Missing Slashes

```properties
service.root=https://example.invalid/api/
service.url=${service.root}/orders
```

The result can be `https://example.invalid/api//orders`. Placeholders only perform text substitution; they do not normalize slashes. Similarly, if `service.root` lacks a trailing slash and the suffix lacks a leading slash, the URL segments run together.

To reduce errors, establish a clear convention: `base-url` has **no** trailing slash; sub-paths **have** a leading slash. When URLs contain parameters or require encoding, build URIs using the appropriate API.

## 14. Nested References Are Not Arbitrary Data Concatenation

A placeholder retrieves a configuration value by name. It does **not** inherently have the ability to:

- Run a database query to build a URL for the current user.
- Read configuration that changes per HTTP request without a dedicated refresh mechanism.
- Guarantee the endpoint is reachable or that the URI is structurally valid.
- Guarantee a dynamic selector only picks allowed targets.
- Automatically URL-encode or keep secrets safe if the result is logged.

For example, the dynamic key `${payments.targets.${payments.selected}}` is very convenient when the selector has a controlled set of values at startup. But if `payments.selected` can receive untrusted input, validation is required to avoid selecting the wrong target.

For tokens or passwords, values can come from a proper secret-management source, but you should not concatenate them into a URL and log the URL. Sensitive values remain sensitive after placeholder resolution.

## 15. Debugging Workflow When the Final URL Is Wrong

Suppose you expect:

```text
https://catalog.example.invalid:8443/v1/products
```

but the bean receives a different value. Check using this workflow:

1. **Read the target key**: does the bean use `catalog.products-url` or another key? Does any `@Value`/`@ConfigurationProperties` define its own fallback?
2. **Check source precedence**: was `catalog.products-url` completely overridden from command-line arguments, environment variables, profile files, or other Config Data?
3. **Trace each reference**: `products-url` → `base-url` → `scheme`, `host`, `port`, `base-path`. For dynamic keys, check the selector first and then determine the outer key name.
4. **Check missing keys**: a non-existent property differs from a property with an empty string; verify fallbacks at the right level.
5. **Check structure**: missing/extra slashes, `http`/`https` scheme, port, URL component encoding.
6. **Check timing**: was the file edited after the application started; is the bean still holding values bound from a previous startup?
7. **Check cycle errors**: are two keys pointing back at each other?

With harmless test data, you can use an `ApplicationRunner` to print the relevant keys via `Environment.getProperty(...)`. If the application includes Spring Boot Actuator and the `env` endpoint is securely configured, you can inspect source information. Avoid exposing public endpoints or printing all configuration when passwords/tokens are present.

A simple technique is to temporarily reduce the formula layer by layer:

```text
Step 1: catalog.host
Step 2: catalog.port
Step 3: catalog.base-url
Step 4: catalog.products-url
```

If steps 1 and 2 are right but step 3 is wrong, focus on the formula string or overrides of `base-url`. If step 3 is right but step 4 is wrong, inspect the `/products` suffix or a possible override of `products-url`.

## 16. Practice Exercise: One Change Rippling Through Multiple Values

Initial setup:

```yaml
app:
  env: dev

  hosts:
    dev: localhost
    stage: stage.example.invalid
    prod: prod.example.invalid

  scheme: https
  port: 8443
  api-root: /api/v1

  selected-host: "${app.hosts.${app.env}}"
  base-url: "${app.scheme}://${app.selected-host}:${app.port}${app.api-root}"
  customers-url: "${app.base-url}/customers"
  orders-url: "${app.base-url}/orders"
```

Predict the values:

| Run | Override | `app.selected-host` | `app.orders-url` |
| --- | --- | --- | --- |
| A | None | `localhost` | `https://localhost:8443/api/v1/orders` |
| B | `--app.env=stage` | `stage.example.invalid` | `https://stage.example.invalid:8443/api/v1/orders` |
| C | `--app.env=prod --app.port=9443` | `prod.example.invalid` | `https://prod.example.invalid:9443/api/v1/orders` |
| D | `--app.env=prod --app.base-url=https://proxy.example.invalid/v2` | `prod.example.invalid` | `https://proxy.example.invalid/v2/orders` |

In D, `app.selected-host` can still be `prod.example.invalid`, but `app.base-url` was overridden directly, so `app.orders-url` is no longer forced to use the `scheme://selected-host:port/api-root` formula from YAML.

Try another scenario E:

```bash
java -jar app.jar --app.env=unknown
```

Here, `app.selected-host` looks up `app.hosts.unknown`. Because that key does not exist, your business rules must decide whether to **fail early**, **reject the selector**, or **use an explicitly declared fallback endpoint**. There is no rule where Spring guesses a name similar to `unknown`.

### Reasoning Exercises

1. If `app.port` is overridden with `9443`, which derived keys change?
2. If `app.base-url` is overridden with an absolute URL, does changing `app.scheme` still affect `app.orders-url`?
3. If `app.env` is absent, should the default be placed on `app.env` or on the inner placeholder inside `app.selected-host`? What error conditions does each create?
4. If `app.hosts.prod` contains an empty string, will the fallback on the outer placeholder definitely be chosen?
5. With two keys `one=${two}` and `two=${one}`, what prevents them from resolving to a finite value?

These exercises highlight the relationship between **precedence-selected values**, **dynamic key names**, and **the dependency tree of derived values**.

## 17. Organizing Configuration for Maintainability

Separate three kinds of properties:

| Kind | Role | Examples |
| --- | --- | --- |
| Base values | Vary by environment | `app.host`, `app.port`, `app.env` |
| Derived values | Composed from base values | `app.base-url`, `app.orders-url` |
| Selector values | Determine configuration branch | `app.selected`, `payments.region` |

Useful conventions:

- **Use full descriptive names**: `payments.selected-region` is clearer than `payments.sel`.
- **Prefer canonical keys**: use lowercase, dots for groups, and hyphens for compound words inside `${...}` references.
- **Add fallbacks deliberately**: only include a default value if it is safe and meaningful when sources are missing.
- **Limit reference chains**: avoid overly deep trees; if a formula becomes hard to read, consider creating a configuration object and computing it with checks in Java.
- **Do not create cycles**: derived values depend on base values, never the reverse.
- **Validate URIs and required data**: placeholders do not replace validation.
- **Do not log secrets**: URLs containing tokens/passwords remain sensitive data even after composition.
- **Document overridable sources**: if `base-url` is allowed to be overridden independently, communicate that to operators so they understand why the formula is not used.

## 18. Key Takeaways

Placeholders in Spring Boot allow one property to be **built from other properties** without repeating values across multiple files.

```text
${app.host}                         -> single reference

http://${app.host}:${app.port}      -> composing multiple properties

${app.base-url}/orders             -> chained reference

${app.hosts.${app.env}}            -> placeholder nested in key name

${app.host:localhost}              -> default value for missing key
```

Always trace the processing flow in order:

```text
Effective configuration sources
        |
        v
Resolve each ${...} reference
        |
        v
Substitute nested placeholders, if any
        |
        v
Produce resulting string and convert type as needed
        |
        v
Bean receives and uses the value
```

In multi-environment systems, referencing enables configuration reuse, while **per-key overriding** allows a single JAR to run with different hosts, ports, or endpoints. When a URL is not as expected, trace backward from the target key through each placeholder to the source providing the value, then check fallbacks, cycles, and precedence order.

Further reading: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) and [Spring Framework — Property Resolution](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html).