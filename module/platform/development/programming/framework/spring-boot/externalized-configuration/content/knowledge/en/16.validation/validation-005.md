# Validating Nested Objects with `@Valid` in Spring Boot `@ConfigurationProperties`

## Objectives

In Spring Boot, **`@ConfigurationProperties`** binds external configuration into a typed Java object. For flat configurations, a few constraints like **`@NotBlank`** or **`@Min`** on root-level fields may suffice to prevent the application from starting with invalid data. However, real-world configurations typically span multiple levels: database → pool, HTTP → timeout, retry → backoff, security → issuer, or a list of endpoints.

A common mistake is putting **`@Validated`** only on the root configuration class and expecting every child object's constraints to be checked automatically in all cases. In Jakarta Bean Validation, **cascaded validation into nested objects** is expressed by placing **`@Valid`** on the reference to the child object or collection elements.

Example configuration:

~~~yaml
app:
  client:
    base-url: "https://api.example.test"
    http:
      connect-timeout: 2s
      read-timeout: 10s
      max-connections: 20
~~~

If **`client.base-url`** is blank or **`http.max-connections`** is `0`, the application should report a configuration error before serving requests. This requires properly modeling the levels and stating validation rules explicitly.

After this lesson, you will be able to:

- Distinguish **`@ConfigurationProperties`**, **`@Validated`**, **`@Valid`**, and constraints such as **`@NotNull`**, **`@NotBlank`**, **`@Min`**, and **`@NotEmpty`**.
- Place **`@Valid`** at the exact boundary between root and child objects, including multi-level nesting.
- Understand why **`@Valid` does not require a child object to be non-null**.
- Apply validation to **`List`**, **`Map`**, and nested elements.
- Design Java **records (constructor binding)** and **JavaBeans (setter binding)** with validation.
- Handle default values, missing configuration groups, type mismatches, and nested binding errors.
- Write tests verifying that invalid configuration prevents the application from starting.
- Read binding/validation error reports to locate the exact property path causing the failure.

Code snippets follow **Spring Boot 3.x** and Jakarta Validation (**`jakarta.validation`**). Projects on Spring Boot 2.x differ in packages and certain constructor-binding behaviors, so adjust according to your actual dependencies.

## 1. Why Does Configuration Need Validation?

Suppose a service depends on a partner endpoint:

~~~yaml
integration:
  catalog:
    endpoint: ""
    timeout: -1s
    retry:
      max-attempts: 0
~~~

This YAML may be **syntactically valid**, and the Binder may convert some values into Java types, yet the configuration is invalid under business rules:

- Empty endpoint: the service does not know where to call.
- Negative timeout: meaningless under the timeout policy in use.
- `max-attempts = 0`: if the contract requires at least one attempt, this violates the constraint.

If not caught at startup, the bug may surface only when the feature is exercised. For critical settings, the principle should be **fail fast**: refuse startup if mandatory configuration requirements are unmet.

Validation should be expressed on the configuration model rather than relying on a YAML line "looking reasonable."

### 1.1. Three Error Categories to Distinguish

| Error Category | Example | Handling Layer |
| --- | --- | --- |
| Property not found | Missing `integration.catalog.endpoint` | Binder/default/validation |
| Conversion failure | `max-attempts: many` when Java expects `int` | Type conversion during binding |
| Type-valid data violating constraints | `max-attempts: 0` with `@Min(1)` | Bean Validation |

**`@Valid` does not fix misspelled property names or type mismatches.** It simply propagates validation into suitable nested objects after they have been instantiated or supplied for validation.

## 2. How Do `@Validated` and `@Valid` Differ?

This is the single most important takeaway of the lesson.

**`@Validated`** is a Spring annotation. On a **`@ConfigurationProperties`** bean, it is normally placed on the root class/record to enable validation when configuration is bound, provided the project has a compatible Bean Validation provider.

**`@Valid`** belongs to Jakarta Validation. It denotes **cascaded validation**: when the validator encounters a reference to a child object, it continues evaluating constraints on that object.

Example:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String name,
        @Valid Client client
) {
    public record Client(
            @NotBlank String baseUrl
    ) {}
}
~~~

If `app.name` is blank, **`@NotBlank`** on the root reports an error. If `app.client.base-url` is blank and `Client` is bound into an object, **`@Valid`** on the `client` component allows the validator to descend into `Client` and check **`@NotBlank`**.

A helpful mnemonic:

~~~text
@Validated on root
    -> Spring Boot performs validation for the configuration bean

@Valid on nested boundary
    -> Validator descends into the child object

@NotBlank / @NotNull / @Min / @Size...
    -> Defines which values are valid
~~~

### 2.1. `@Valid` Does Not Replace `@Validated` at the Root

Placing `@Valid` on a field without enabling validation for the configuration bean is not enough to guarantee data gets validated at startup.

In the standard Spring Boot pattern:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(@Valid Client client) { ... }
~~~

**`@Validated`** declares the intent to validate the configuration bean; **`@Valid`** marks the boundary to traverse deeper.

### 2.2. `@Validated` Does Not Replace `@Valid` at Every Level

If a child object contains constraints, place **`@Valid`** on the reference to that child object to make cascaded validation explicit and ensure evaluation when needed, even when no child properties are supplied.

Do not rely on guessing that "the class has `@Validated`, so every nested object at every depth is automatically checked." While the Binder can participate in nested validation in certain cases, the explicit and recommended way to express cascaded validation remains **`@Valid`**.

### 2.3. `@Valid` Is Not a Null-Check Constraint

Writing:

~~~java
@Valid Client client
~~~

does **not** mean **`client` must be non-null**. Under Jakarta Validation rules, cascading skips null references.

To require the child object to exist:

~~~java
@Valid @NotNull Client client
~~~

Each annotation has a distinct job:

- **`@NotNull`**: the `client` reference must hold an object.
- **`@Valid`**: if an object exists, validate the constraints inside `Client`.

This distinction accounts for a huge share of real-world configuration validation bugs.

## 3. Setting Up Dependencies and Registering Configuration Properties

To use Jakarta Bean Validation with Spring Boot 3, the project needs a compatible provider, usually added via the validation starter.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Wait—check the original line 172 in `validation-005.md`: it's `~~~`! Let's keep `~~~` consistently.

This starter provides the integration and validator implementation aligned with Spring Boot's dependency management.

### 3.1. Registering `@ConfigurationProperties` Beans

Using scanning:

~~~java
package example;

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

The configuration record must reside in a scanned package.

Explicit registration:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(AppProperties.class)
class PropertiesRegistration {
}
~~~

If you forget to register the bean, the app can fail due to a missing dependency when injecting `AppProperties`. That is a **bean registration error**, not a `@Valid` error.

### 3.2. `javax.validation` vs. `jakarta.validation` Packages

In Spring Boot 3.x projects, standard Bean Validation annotations are imported from **`jakarta.validation`**:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotBlank;
~~~

Many older Spring Boot 2.x examples use **`javax.validation`**. Copying that code into Boot 3 without updating dependencies/packages can cause compilation errors or prevent annotations from participating in validation.

Distinguish those from **`org.springframework.validation.annotation.Validated`**, which remains a Spring annotation.

## 4. Complete Example: Multi-Level Record

Configuration:

~~~yaml
app:
  name: "Order Service"
  client:
    base-url: "https://orders.example.test"
    http:
      connect-timeout: 2s
      read-timeout: 8s
      max-connections: 20
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

Java model:

~~~java
package example.config;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String name,
        @Valid @NotNull Client client
) {
    public record Client(
            @NotBlank String baseUrl,
            @Valid @NotNull Http http,
            @Valid @NotNull Retry retry
    ) {}

    public record Http(
            @NotNull Duration connectTimeout,
            @NotNull Duration readTimeout,
            @Min(1) int maxConnections
    ) {}

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
~~~

Paths to bind:

| Canonical Property | Java Field | Constraint |
| --- | --- | --- |
| `app.name` | `name` | `@NotBlank` |
| `app.client` | `client` | `@NotNull` + `@Valid` |
| `app.client.base-url` | `client.baseUrl` | `@NotBlank` |
| `app.client.http` | `client.http` | `@NotNull` + `@Valid` |
| `app.client.http.connect-timeout` | `http.connectTimeout` | `@NotNull` |
| `app.client.http.read-timeout` | `http.readTimeout` | `@NotNull` |
| `app.client.http.max-connections` | `http.maxConnections` | `@Min(1)` |
| `app.client.retry` | `client.retry` | `@NotNull` + `@Valid` |
| `app.client.retry.max-attempts` | `retry.maxAttempts` | `@Min(1)` |
| `app.client.retry.backoff` | `retry.backoff` | `@NotNull` |

To validate down to **`maxConnections`**, picture the steps:

~~~text
AppProperties (@Validated)
  |
  +-- name (@NotBlank)
  |
  +-- client (@NotNull + @Valid)
        |
        +-- baseUrl (@NotBlank)
        |
        +-- http (@NotNull + @Valid)
        |     |
        |     +-- connectTimeout (@NotNull)
        |     +-- readTimeout (@NotNull)
        |     +-- maxConnections (@Min(1))
        |
        +-- retry (@NotNull + @Valid)
              |
              +-- maxAttempts (@Min(1))
              +-- backoff (@NotNull)
~~~

**`@Valid` must appear at every boundary that requires cascading**, from `AppProperties` to `Client` and from `Client` to `Http`/`Retry`. If `@Valid` is omitted at any boundary, do not expect deeper constraints to run under the Jakarta Validation cascade contract.

## 5. Testing Invalid Configurations and Understanding Errors

Suppose we change the YAML to:

~~~yaml
app:
  name: "Order Service"
  client:
    base-url: ""
    http:
      connect-timeout: 2s
      read-timeout: 8s
      max-connections: 0
    retry:
      max-attempts: 0
      backoff: 500ms
~~~

Three notable values:

- **`app.client.base-url = ""`** violates **`@NotBlank`**.
- **`app.client.http.max-connections = 0`** violates **`@Min(1)`**.
- **`app.client.retry.max-attempts = 0`** violates **`@Min(1)`**.

When Spring Boot binds and validates `AppProperties`, startup can fail with details about the invalid fields, such as their paths and violated constraints. Exact message wording varies by Boot version, validator, and bean-creation path.

Startup failure in this case **is the expected behavior**. It prevents the system from running with a blank endpoint or invalid retry policy.

### 5.1. Why Distinguish Validation Errors from Conversion Errors?

If the configuration is:

~~~yaml
app:
  client:
    http:
      max-connections: "many"
~~~

then **`many`** cannot convert to `int`. A conversion error occurs before the validator checks **`@Min(1)`**. Adding `@Valid` does not turn an alphabetic string into a number.

Conversely, with **`max-connections: 0`**, the value is already a type-valid `int` that fails the business constraint. When debugging, inspect the **root cause** to see which stage failed.

## 6. Missing Configuration Branch: `@Valid` vs. `@NotNull`

A crucial edge case:

~~~yaml
app:
  name: "Order Service"
~~~

No **`app.client`** is present.

If declared as:

~~~java
@Valid Client client
~~~

then when `client` is null, **`@Valid` does not report a null error**. The validator only descends when an object exists to inspect.

If `client` is required:

~~~java
@Valid @NotNull Client client
~~~

then **`@NotNull`** detects that the `client` branch produced no object after binding; **`@Valid`** enforces `Client`'s constraints when the object exists.

### 6.1. When the Branch Has an Object Missing Child Fields

Example:

~~~yaml
app:
  name: "Order Service"
  client:
    http:
      max-connections: 5
~~~

Under the design in section 4, the Binder can create `Client` and `Http`, while **`baseUrl`** may be null and **`retry`** may be null.

Each constraint plays its part:

~~~text
client.baseUrl -> @NotBlank catches null/blank
client.retry   -> @NotNull catches missing Retry object
client.http    -> @Valid routes validator into Http
~~~

**Validation intent must be stated at the right level**: a missing object and a missing child field are two different errors.

### 6.2. When a Child Group Is Optional

Not every nested object is mandatory. For instance, an exporter configuration may exist only when the feature is enabled.

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        boolean exporterEnabled,
        @Valid Exporter exporter
) {
    public record Exporter(
            @NotBlank String endpoint
    ) {}
}
~~~

Here **`exporter`** is cascaded if present, yet is not forced to be non-null. If business rules require "when `exporterEnabled=true`, `exporter` must have an endpoint," `@Valid` and `@NotBlank` alone do not express that cross-field relationship.

In that case, use an **object-level constraint**, an invariant check method, or appropriate configuration validation logic. Do not add unconditional `@NotNull` if `exporter` is genuinely allowed to be absent when the feature is off.

## 7. When No Child Properties Exist: Why Is `@Valid` Important?

Spring Boot has specific rules for binding and validating nested properties. A key detail highlighted in the Spring Boot documentation is: **to ensure validation of nested properties is triggered even when no child properties are found, annotate the nested field with `@Valid`**.

JavaBean example:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private final Security security = new Security();

    @Valid
    public Security getSecurity() {
        return security;
    }

    public static class Security {
        @NotBlank
        private String issuer;

        public String getIssuer() {
            return issuer;
        }

        public void setIssuer(String issuer) {
            this.issuer = issuer;
        }
    }
}
~~~

In a JavaBean class with an eagerly initialized nested `Security`, placing `@Valid` on the getter expresses the intent to validate that object even if configuration contains no **`app.security.issuer`**.

In practice, placing `@Valid` on a field, getter, or record component depends on the binding style and how the framework discovers property metadata. Standardize annotation placement across your project, verify Bean Validation metadata, and test a case where the entire branch is absent.

### 7.1. `@Valid` Does Not Magically Instantiate Objects

If `security` starts as null, `@Valid` alone does not instantiate `Security`. **Creating nested objects** is the job of the Binder, constructor, setter, or field initializer—not `@Valid`.

To force an object to exist, use `@NotNull`; to create a default object, use constructor binding or JavaBean field initialization.

### 7.2. Do Not Rely on Primitive Defaults

A nested record has:

~~~java
public record Retry(int maxAttempts) {}
~~~

When the property is absent, the primitive may become `0` depending on constructor/binding behavior. **`@Min(1)`** catches `0` if validation reaches `Retry`. However, if the `Retry` object itself is null and the parent lacks `@NotNull`, inner constraints may never be evaluated.

For required properties where "omitted" must be distinguished from "set to 0," consider **`Integer`** combined with **`@NotNull`** and **`@Min(1)`** instead of primitive `int`.

## 8. JavaBean Binding: `@Valid` on Nested Fields/Getters

Not every project uses Java records. You can write a JavaBean with setters:

~~~java
package example.config;

import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    @Valid
    @NotNull
    private Http http = new Http();

    public Http getHttp() {
        return http;
    }

    public void setHttp(Http http) {
        this.http = http;
    }

    public static class Http {
        @NotBlank
        private String baseUrl;

        @NotNull
        private Duration timeout;

        @Min(1)
        private int maxConnections;

        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

        public Duration getTimeout() { return timeout; }
        public void setTimeout(Duration timeout) { this.timeout = timeout; }

        public int getMaxConnections() { return maxConnections; }
        public void setMaxConnections(int maxConnections) {
            this.maxConnections = maxConnections;
        }
    }
}
~~~

YAML:

~~~yaml
app:
  http:
    base-url: "https://api.example.test"
    timeout: 5s
    max-connections: 20
~~~

JavaBean binding populates properties using getters and setters as supported by the Binder. Bean Validation then checks the root and cascades into `Http` via **`@Valid`**.

### 8.1. Eagerly Initializing Nested Objects

For instance:

~~~java
private Http http = new Http();
~~~

supplies an `Http` instance even when `app.http` is completely absent. This is useful when you want **validation to catch missing required inner fields**, using `@Valid` and appropriate constraints.

If instead you write:

~~~java
private Http http;
~~~

then when `app.http` has no data, the field can remain null. In that case, **`@Valid`** skips null and **`@NotNull`** is what catches the missing branch.

Whether to provide a setter or eager initialization depends on your JavaBean design; do not conflate object creation with `@Valid`'s semantics.

### 8.2. Can `@Valid` Be Placed on a Getter?

Jakarta Bean Validation supports property metadata on either fields or getters. For example:

~~~java
@Valid
public Http getHttp() {
    return http;
}
~~~

can express cascaded validation through the getter. However, avoid placing constraints on both the field and the getter of the same property unintentionally, as that can cause duplicate validation or confusing metadata.

Within a JavaBean class, pick a consistent annotation placement so readers immediately see which property each constraint applies to.

## 9. Records and Constructor Binding: `@Valid` on Components

In Spring Boot 3, Java records are commonly used for `@ConfigurationProperties` via constructor binding.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotBlank String name,
        @Valid @NotNull Database database
) {
    public record Database(
            @NotBlank String url,
            @NotBlank String username
    ) {}
}
~~~

Here **`database`** is a component of the root record. When the Binder instantiates `AppProperties`, Jakarta Validation reads constraints attached to the record's components, fields, or accessors as valid metadata.

No setters are needed for records. `@Valid` **is not a workaround for missing setters**; it simply tells the validator to descend into `Database` after the Binder creates the object.

### 9.1. Registration Appropriate for Constructor-Bound Properties

Registering via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` is recommended for constructor-bound records.

Do not simultaneously add `@Component` to the record assuming IoC constructor injection automatically performs constructor binding. The two mechanisms have different semantics: one binds **property values**, while the other resolves **bean dependencies**.

### 9.2. `@DefaultValue` and Nested Objects

Recent Spring Boot versions support **`@DefaultValue`** on constructor parameters/record components.

Example:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @DefaultValue Http http
) {
    public record Http(
            @DefaultValue("5s") java.time.Duration timeout
    ) {}
}
~~~

An **empty `@DefaultValue`** on a nested component instructs the Binder to instantiate the nested object even when no child properties exist, allowing defaults and validation on the child object to run. Exact behavior depends on constructor structure, Spring Boot version, and conversion support.

If the object must genuinely be configured by the operator, avoid creating an unconditional default just to let the app start. Defaulting an entire group can defeat a business requirement that it be explicitly declared.

## 10. `@Valid` Across Multiple Levels: Do Not Break the Chain

A three-level configuration:

~~~text
app
  -> client
      -> http
          -> pool
              -> max-size
~~~

Model:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @NotNull Client client
) {
    public record Client(
            @Valid @NotNull Http http
    ) {}

    public record Http(
            @Valid @NotNull Pool pool
    ) {}

    public record Pool(
            @Min(1) int maxSize
    ) {}
}
~~~

If **`app.client.http.pool.max-size=0`**, cascading proceeds as:

~~~text
AppProperties
 -> client (@Valid)
 -> http (@Valid)
 -> pool (@Valid)
 -> maxSize (@Min(1))
~~~

A common mistake is writing:

~~~java
public record Http(Pool pool) {}
~~~

without `@Valid` on `pool`, assuming `@Min` inside `Pool` will naturally be checked just because the root has `@Validated`. With cascaded validation, every object boundary you want traversed must declare it.

### 10.1. At Which Levels Should `@NotNull` Appear?

Put **`@NotNull`** on every required nested object, not only at the root.

- If `client` is required: `@NotNull Client client`.
- If `http` is required inside `Client`: `@NotNull Http http`.
- If `pool` is required inside `Http`: `@NotNull Pool pool`.

When a branch is optional, omit unconditional `@NotNull`; use `@Valid` alone to validate if an instance exists, or define an appropriate conditional constraint.

## 11. `@Valid` for a `List` of Objects

A configuration group can contain multiple endpoints:

~~~yaml
app:
  endpoints:
    - name: primary
      url: "https://api-a.example.test"
      timeout: 3s
    - name: backup
      url: ""
      timeout: 5s
~~~

Record:

~~~java
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
public record EndpointProperties(
        @NotEmpty List<@Valid Endpoint> endpoints
) {
    public record Endpoint(
            @NotBlank String name,
            @NotBlank String url,
            @NotNull Duration timeout
    ) {}
}
~~~

There are two constraint levels:

- **`@NotEmpty`** on `List`: the list must have at least one element.
- **`@Valid`** on the `Endpoint` element type: each non-null `Endpoint` has its constraints checked.

If the second endpoint has **`url=""`**, **`@NotBlank`** in `Endpoint` produces a violation with a path equivalent to **`endpoints[1].url`**, depending on how the provider formats property paths.

### 11.1. `@Valid List<Endpoint>` vs. `List<@Valid Endpoint>`?

You may see both patterns:

~~~java
@Valid
private List<Endpoint> endpoints;
~~~

and:

~~~java
private List<@Valid Endpoint> endpoints;
~~~

Jakarta Validation supports cascaded validation of container elements in compatible versions. **`List<@Valid Endpoint>`** directly expresses validating each element. **`@Valid`** on the collection property is also a valid pattern, relying on provider metadata and container value extractors.

For new code, pick one clear, consistent style supported by your validator version. Do not double-annotate both positions "just to be safe" without reason.

### 11.2. What If the `List` Contains Null?

**`@Valid`** does not forbid a null element in a list. If elements must be non-null, use a container-element constraint:

~~~java
@NotEmpty
List<@NotNull @Valid Endpoint> endpoints
~~~

Then:

- `@NotEmpty` checks that the list has elements.
- `@NotNull` on the element checks that each element is non-null.
- `@Valid` on the element checks the fields inside each `Endpoint`.

This distinguishes **container** validation from **element** validation.

## 12. `@Valid` for a `Map` with Object Values

Suppose we configure regions:

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
      timeout: 4s
    europe:
      endpoint: ""
      timeout: 5s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record RegionProperties(
        @NotEmpty Map<@NotBlank String, @NotNull @Valid Region> regions
) {
    public record Region(
            @NotBlank String endpoint,
            @NotNull Duration timeout
    ) {}
}
~~~

Here:

- `@NotEmpty` on the `Map` ensures at least one entry.
- `@NotBlank` on the `String` key ensures keys are not blank.
- `@NotNull` on the value ensures every value holds a `Region` object.
- `@Valid` on the value validates `endpoint` and `timeout` on each `Region`.

**Placing `@Valid` on the value** differs from placing `@Valid` on the key, and differs from entry-count constraints. Each level has its own job.

### 12.1. Watch Out for Dotted `Map` Keys

For keys containing dots such as **`tenant.eu`**, the Binder may require bracket notation to preserve the key intact:

~~~yaml
app:
  regions:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
      timeout: 4s
~~~

Adding `@Valid` will not fix the Binder splitting an unbracketed dotted key into a nested path unexpectedly. **Property names and Map keys** must bind correctly before the validator inspects the values.

### 12.2. Validation Does Not Enforce Business Uniqueness Rules Across Keys

A `Map` by definition has unique keys at runtime by `equals`/`hashCode`, yet the validator does not automatically enforce business rules like "the region must exist in a registered catalog" or "two regions cannot share the same endpoint."

Such rules may require a custom constraint at the `Map` or configuration-class level.

## 13. Nested Objects Inside Lists Inside Maps

Multiple layers can be combined:

~~~yaml
app:
  tenants:
    - name: alpha
      routes:
        users:
          path: "/users"
          timeout: 2s
        orders:
          path: "/orders"
          timeout: 3s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record TenantProperties(
        @NotEmpty List<@Valid Tenant> tenants
) {
    public record Tenant(
            @NotBlank String name,
            @NotEmpty Map<@NotBlank String, @Valid Route> routes
    ) {}

    public record Route(
            @NotBlank String path,
            @NotNull Duration timeout
    ) {}
}
~~~

Flow:

~~~text
TenantProperties
  -> tenants[0] (List<@Valid Tenant>)
       -> name (@NotBlank)
       -> routes (Map<String, @Valid Route>)
            -> users (Route)
                 -> path (@NotBlank)
                 -> timeout (@NotNull)
            -> orders (Route)
                 -> path (@NotBlank)
                 -> timeout (@NotNull)
~~~

If **`orders.path`** is empty, the `Route` constraint fails. If `routes` is an empty `Map`, **`@NotEmpty`** on `Tenant.routes` fails. If `tenants` has no elements, **`@NotEmpty`** on `TenantProperties.tenants` fails.

This structure reports violations at the exact right level rather than relying on one generic check method returning `false`.

## 14. Common Constraints in Nested Configurations

A practical set of constraints:

| Constraint | Applies To | Meaning |
| --- | --- | --- |
| `@NotNull` | Objects, wrapper types, `String`, collections | Must not be null |
| `@NotBlank` | `String` / compatible `CharSequence` | Not null, not empty, not whitespace-only |
| `@NotEmpty` | Collections, `Map`, `String`, compatible arrays | At least one element/character |
| `@Min(n)` | Supported integral types | Value at least `n` |
| `@Max(n)` | Supported integral types | Value at most `n` |
| `@Positive` | Supported numeric types | Must be strictly greater than 0 |
| `@Size(min,max)` | `String`, collections, `Map`, arrays | Checks length or size |
| `@Pattern(regexp=...)` | `String` / `CharSequence` | Matches regular expression |
| `@Valid` | Objects or container elements | Cascades into child object |
| `@AssertTrue` | Boolean property/method | Value or condition must be true |

Do not put `@NotBlank` on **`Duration`**, **`Integer`**, or nested objects, because that constraint is for character sequences.

Do not put `@Min` directly on `Duration` assuming the validator treats it as milliseconds. **`@Min`** is defined for supported numeric types, not as a universal `Duration` constraint.

### 14.1. Size Constraints and Collection Levels

Example:

~~~java
@Size(min = 1, max = 10)
List<@Valid Endpoint> endpoints
~~~

The size constraint checks the `List` length, while `@Valid` checks each `Endpoint`'s contents. A `List` of 2 `Endpoint`s where one has an empty URL still fails the element-level constraint.

### 14.2. Regex with `@Pattern`

Example restricting a cluster name to alphanumeric characters:

~~~java
@Pattern(regexp = "[a-zA-Z0-9]+")
String clusterName
~~~

Wait—let's check line 975 in `validation-005.md`: it's `~~~`! Always preserve exact fence style (`~~~java` / `~~~`).

This is a straightforward constraint. For URLs, URIs, or complex identifiers, choose a Java type with appropriate conversion and business validation instead of an overly long, error-prone regex.

### 14.3. Constraints Require a Validation Provider

Compiling imports for these annotations is not enough to guarantee a Jakarta Bean Validation provider is present at runtime. In Boot applications, typically add **`spring-boot-starter-validation`** and start with matching auto-configuration.

When tests show invalid data being accepted, inspect the **validation provider**, **`@Validated` on the root**, **`@Valid` on nested boundaries**, and **whether the config class is actually bound as a bean**.

## 15. How Should `Duration` Be Constrained?

Timeouts, intervals, and backoffs typically use **`java.time.Duration`**:

~~~java
public record Http(Duration readTimeout) {}
~~~

YAML example:

~~~yaml
app:
  http:
    read-timeout: 0s
~~~

If business rules require a positive timeout, `@NotNull` alone is insufficient because `Duration.ZERO` is not null. On the other hand, do not apply `@Min(1)` to `Duration` as if it were an `int`.

You can add a custom constraint or Java invariant:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public record Http(@NotNull Duration readTimeout) {

    @AssertTrue(message = "readTimeout must be positive")
    public boolean isReadTimeoutPositive() {
        return readTimeout != null
                && !readTimeout.isZero()
                && !readTimeout.isNegative();
    }
}
~~~

When `Http` is validated via `@Valid`, the `@AssertTrue` constraint on property **`readTimeoutPositive`** ensures `Duration` is greater than 0.

### 15.1. Limits of `@AssertTrue`

An `@AssertTrue` method suits short boolean checks. However, if a class has multiple interdependent conditions, a custom class-level constraint or dedicated validator can be cleaner.

Never put side effects such as database calls, HTTP requests, or file writes inside validation methods. Configuration validation must run quickly and reproducibly at startup.

### 15.2. Handling Null `Duration`

The example above has both `@NotNull` and a positivity check. When `readTimeout=null`, multiple related violations could be produced. That is not necessarily wrong, though if you want a single clean message, design a custom constraint handling null consistently.

If an "unspecified" value is permitted, do not add `@NotNull` reflexively just because the type is `Duration`; define null semantics and defaults in your configuration policy.

## 16. Cross-Field Constraints Inside a Nested Object

Not every condition constrains a single field independently.

Example:

~~~yaml
app:
  retry:
    enabled: true
    max-attempts: 0
~~~

Business rule: if `enabled=true`, `max-attempts` must be at least 1; if `enabled=false`, `0` is allowed.

Record:

~~~java
import jakarta.validation.constraints.AssertTrue;

public record Retry(
        boolean enabled,
        int maxAttempts
) {
    @AssertTrue(message =
            "maxAttempts must be >= 1 when retry is enabled")
    public boolean isRetryConfigurationValid() {
        return !enabled || maxAttempts >= 1;
    }
}
~~~

This constraint belongs to the **entire `Retry` object**, even though it is exposed as a boolean property. For it to execute, `Retry` must lie on a cascaded validation path or be validated directly.

### 16.1. When to Write a Custom Constraint?

For more complex conditions:

- `minConnections` must not exceed `maxConnections`.
- `enabled=true` requires an endpoint to exist.
- A server list must contain at least one primary node.
- Regions must not share duplicate identifiers.
- Backoff must be positive and shorter than request timeout.
- Authentication fields must be supplied together.

In these cases, create a class-level annotation and **`ConstraintValidator`**. That adds a bit more code, yet decouples the validation contract from binding and allows standalone unit testing.

### 16.2. Do Not Replace Validation with First-Request Checks

If a configuration state is knowably invalid at startup, reject application boot instead of letting errors wait until a user hits an endpoint. This matters especially for safety settings, resource limits, and critical connections.

## 17. Is `@Valid` Needed If the Child Object Already Has `@Validated`?

A pattern that causes confusion:

~~~java
@Validated
public record Client(
        @NotBlank String baseUrl
) {}
~~~

and at the root:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(Client client) {}
~~~

Assuming validation automatically jumps from `AppProperties` down into `Client` in every situation simply because `Client` has `@Validated` is unreliable.

Jakarta Bean Validation cascaded validation is declared with **`@Valid`** on the reference at the root:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid Client client
) {}
~~~

And if `client` is required:

~~~java
@Valid @NotNull Client client
~~~

**Where a validator is triggered** and **the cascade path** are two distinct concepts. Constraints on a child object do not automatically mean the parent validates them unless the corresponding cascade path actually traverses it.

## 18. `@NestedConfigurationProperty` Is Not `@Valid`

Spring Boot provides **`@NestedConfigurationProperty`** to supply configuration metadata about nested types in certain scenarios.

Example:

~~~java
import org.springframework.boot.context.properties.NestedConfigurationProperty;

public class ClientProperties {
    @NestedConfigurationProperty
    private HttpOptions http;
}
~~~

This annotation **does not replace**:

~~~java
@Valid
private HttpOptions http;
~~~

Differences:

| Annotation | Primary Responsibility |
| --- | --- |
| `@NestedConfigurationProperty` | Describes nested structure for configuration metadata/tooling |
| `@Valid` | Instructs the validator to descend into the child object |
| `@NotNull` | Requires the object reference to exist |
| `@Validated` | Enables/configures validation at the Spring integration point |

A field can carry both `@NestedConfigurationProperty` and `@Valid` since they serve two different purposes, but never add a metadata annotation hoping to fix validation or vice versa.

## 19. `@Valid` with Immutable Collections or Java Records

Immutable collections and cascaded validation are independent concepts.

Record example:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty List<@Valid Server> servers
) {
    public AppProperties {
        servers = servers == null
                ? List.of()
                : List.copyOf(servers);
    }

    public record Server(
            @jakarta.validation.constraints.NotBlank String host,
            @jakarta.validation.constraints.Min(1) int port
    ) {}
}
~~~

The Binder passes the `List` data to the constructor. The compact constructor creates an unmodifiable snapshot via `List.copyOf`. Validation can still inspect each `Server` through `@Valid` on the element type.

### 19.1. An Immutable `List` Does Not Make Child Objects Valid

**`List.copyOf`** prevents adding or removing elements, yet does not check whether `host` is blank or `port` is `0`. That is the job of constraints.

If `Server` elements were mutable objects, copying the `List` would not make the elements immutable either; inner element data still needs its own contract.

### 19.2. `List.copyOf` Can Fail Before Validation

`List.copyOf` rejects null elements. If the `List` contains a null element, the compact constructor can throw an exception before `@NotNull` on the element reports in the expected way.

If you need consistent validation messages for null elements, consider normalizing/copying without short-circuiting validation, or use a constructor invariant with a clear message. Never insert an unexamined defensive copy assuming every failure will surface as a `ConstraintViolation`.

## 20. Validating `Map` and `List` Across Multiple `PropertySource`s

Suppose the base file has:

~~~yaml
app:
  servers:
    - host: alpha.example.test
      port: 8080
    - host: beta.example.test
      port: 8081
~~~

And the prod file has:

~~~yaml
app:
  servers:
    - host: production.example.test
      port: 0
~~~

Under Spring Boot's standard list-binding behavior, **a `List` from a higher-precedence source replaces the `List` from a lower-precedence source**. When the `prod` profile is active, the Binder produces a list containing only `production.example.test` with `port=0`, and the validator catches **`@Min(1)`** on `Server.port`.

Validation **does not merge** elements from the base file to borrow port `8080` or `8081`. It checks the **final bound object**.

### 20.1. `Map`s Typically Merge Keys, `List`s Typically Replace

Map example:

~~~yaml
# application.yml
app:
  labels:
    owner: platform
    region: global
~~~

~~~yaml
# application-prod.yml
app:
  labels:
    region: asia
    tier: critical
~~~

The Binder produces a final `Map` with `owner=platform`, `region=asia`, `tier=critical`.

If `Map` values are nested objects with `@Valid`, constraints apply to the **values after the Binder resolves precedence**, not directly to lines in individual source files.

Consequently, when troubleshooting, separate:

- Wrong property name/nesting level.
- Which configuration source won.
- What structure the final collection has.
- Which constraint was violated after binding.

## 21. Using `@Valid` Does Not Solve Nulls Inside `List`/`Map`

Consider:

~~~java
List<@Valid Endpoint> endpoints;
~~~

This means each non-null `Endpoint` is cascaded; it does not forbid a null `List`, an empty `List`, or null elements.

To constrain multiple levels:

~~~java
@NotEmpty
List<@NotNull @Valid Endpoint> endpoints;
~~~

For `Map`:

~~~java
@NotEmpty
Map<@NotBlank String, @NotNull @Valid Endpoint> routes;
~~~

Each constraint carries a distinct meaning. A sound design **defines contracts for the container, keys/values, and child objects layer by layer**, rather than scattering `@Valid` everywhere.

### 21.1. When an Element Is Optional

If business logic intentionally permits a null element as a placeholder, omit `@NotNull` on the element. Ensure every service reading the collection handles nulls safely. For operational configuration, null elements usually indicate an unclear schema; modeling optionality explicitly is easier to maintain.

## 22. Validation and Defaults: Do Not Confuse Them

Three common sources of default values:

1. Values declared in the base `application.yml`.
2. Defaults supported by Spring Boot constructor binding, such as **`@DefaultValue`**.
3. Defaults supplied by JavaBean field initializers or record constructors.

Example:

~~~yaml
app:
  http:
    timeout: 5s
~~~

If the `prod` profile does not override `timeout`, `5s` is bound and validated. `@Valid` does not need to "invent" `5s`.

If a constructor substitutes `Duration.ofSeconds(5)` when `timeout` is null, validation sees a `Duration` of 5s rather than null. Consequently, `@NotNull` will not report the original missing property because the default replaced it.

### 22.1. Defaults Can Hide Required Configuration Errors

If a backend URL must be supplied per production environment, yet a JavaBean writes:

~~~java
private String baseUrl = "http://localhost:8080";
~~~

with `@NotBlank` on `baseUrl`, validation sees a non-blank string and passes even when an operator forgets to configure the real URL.

If a required value must come from the deployment environment, avoid **providing a plausible-looking default**, and use `@NotBlank`/`@NotNull` to catch omissions.

### 22.2. Defaulting a Nested Object Does Not Mean Defaulting Its Children

Writing:

~~~java
private Http http = new Http();
~~~

provides an `Http` instance, yet its inner fields such as `timeout` and `endpoint` can still be null or zero. Validation with `@Valid` then checks `Http`'s constraints.

This differs from creating an `Http` already populated with valid defaults. Distinguish object instantiation policy from field-level default policy.

## 23. Do Not Use `@NotNull` on Primitives to Detect Missing Keys

Java primitives **`int`**, **`long`**, and **`boolean`** cannot be null.

Example:

~~~java
public record Pool(
        @NotNull int maxConnections
) {}
~~~

`@jakarta.validation.constraints.NotNull` cannot detect an absent `int` as intended, because a primitive passed to the validator never has a null state.

Instead, use:

~~~java
public record Pool(
        @Min(1) int maxConnections
) {}
~~~

if a positive number is required, or:

~~~java
public record Pool(
        @NotNull @Min(1) Integer maxConnections
) {}
~~~

if you genuinely need to distinguish **no value supplied** from **`0`** using a wrapper type.

### 23.1. Explicitly Required Booleans

If you need to distinguish "property not configured" from **`false`**, use:

~~~java
@NotNull Boolean enabled
~~~

instead of just:

~~~java
boolean enabled
~~~

With primitive `boolean`, `false` can be the default value, indistinguishable from an intentionally configured `false`. Your Java model should match the configuration contract.

## 24. Do Not Expect `@Valid` to Catch Wrong Prefixes or YAML Indentation

The bean expects:

~~~text
app.client.http.max-connections
~~~

Yet YAML declares:

~~~yaml
app:
  client:
    max-connections: 20
~~~

The actual path is:

~~~text
app.client.max-connections
~~~

If the nested `Http` receives no data, `Http` may remain null or initialize with defaults. Validation might then report `@NotNull Http` or `@Min maxConnections`, depending on design.

**The root cause is still a wrong property path.** Do not fix it by adding arbitrary annotations without fixing the YAML structure.

A systematic way to check:

1. Write down the root prefix.
2. Append each nested component name.
3. Form the full canonical path.
4. Compare against the YAML mapping.
5. Inspect the final `PropertySource` and what the Binder received.

## 25. Reading Spring Boot Error Messages

When binding/validation fails, Spring Boot commonly prints details such as:

~~~text
Failed to bind properties under 'app.client.http'
Property: app.client.http.max-connections
Value: 0
Reason: must be greater than or equal to 1
~~~

This is an **illustrative example of information layout**, not a fixed log format across every version. Actual output may wrap multiple exceptions such as `BindException`, `BindValidationException`, or `BeanCreationException`, plus file origin metadata when loaded from files.

With multi-level objects, look at the **full property path**, not only the leaf field name. Two fields **`retry.maxAttempts`** and **`client.maxAttempts`** can share a short name while belonging to different branches.

### 25.1. Reading the Root Cause

An `ApplicationContext` startup failure may be wrapped in several exception layers. When analyzing, determine:

- Was there a YAML parse error?
- Was there a type conversion error prior to validation?
- Did the validator report specific constraints?
- Did nested object constructor binding fail?
- Is the configuration-properties bean missing because scanning/enabling was omitted?

Only add `@Valid` when the actual bug is un-cascaded validation. If the cause is a missing validator dependency, malformed YAML, or constructor error, fix the corresponding layer.

## 26. Inspecting Configuration Values via `Environment`

You can read a property from Spring's `Environment`:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {

    private final Environment environment;

    public ConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
            environment.getProperty("app.client.http.max-connections")
        );
    }
}
~~~

This snippet is useful when the application **starts successfully** and you want to inspect a non-sensitive property. However, if validation causes startup to fail, `ApplicationRunner` never runs. In that case, inspect startup error reports, context tests, or source origin diagnostics.

### 26.1. Never Print Secrets While Debugging

Nested properties often contain passwords, API keys, and tokens. Never print entire records via `toString`, and do not turn on overly verbose `Environment` logging in production just to debug a minor issue.

When needed, print property names or "present/missing" status—never sensitive values. If Spring Boot Actuator is enabled, secure configuration endpoints and apply appropriate sanitization policies.

## 27. Testing Binding and `@Valid` with `ApplicationContextRunner`

A valuable test verifies that **valid configuration creates the bean** and **invalid configuration prevents bean creation**. Spring Boot provides `ApplicationContextRunner` to launch a lightweight test `ApplicationContext` with isolated property values.

Setup example:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AppPropertiesValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                    ValidationAutoConfiguration.class
                ))
                .withUserConfiguration(TestConfig.class);

    @Test
    void rejectsInvalidNestedProperty() {
        runner.withPropertyValues(
            "app.name=Order Service",
            "app.client.base-url=https://api.example.test",
            "app.client.http.connect-timeout=2s",
            "app.client.http.read-timeout=5s",
            "app.client.http.max-connections=0",
            "app.client.retry.max-attempts=3",
            "app.client.retry.backoff=500ms"
        ).run(context -> {
            assertThat(context).hasFailed();
        });
    }

    @Test
    void acceptsValidNestedProperty() {
        runner.withPropertyValues(
            "app.name=Order Service",
            "app.client.base-url=https://api.example.test",
            "app.client.http.connect-timeout=2s",
            "app.client.http.read-timeout=5s",
            "app.client.http.max-connections=20",
            "app.client.retry.max-attempts=3",
            "app.client.retry.backoff=500ms"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AppProperties.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AppProperties.class)
    static class TestConfig {}
}
~~~

This test uses the `AppProperties` record from section 4. The project needs **`spring-boot-test`**, AssertJ, JUnit Jupiter, the validation starter/provider, and supporting dependencies.

Key design choice: supply real property strings to the Binder instead of instantiating `AppProperties` with `new` inside the test. That allows the test to exercise binding, cascaded validation, and bean instantiation together.

### 27.1. Is Asserting Startup Failure Alone Enough?

Not always. A context can fail due to a package typo or missing dependency unrelated to the expected constraint. In dedicated validation tests, inspect the root cause or verify the message contains the expected property/constraint name.

Still, cause inspection should tolerate minor differences across versions. Avoid brittle assertions on full log transcripts; verify key facts instead of rigid message strings.

### 27.2. Testing an Entire Missing Nested Branch

Add a test supplying only:

~~~text
app.name=Order Service
~~~

If `AppProperties` has **`@Valid @NotNull Client client`**, expect context rejection because `client` is absent. This verifies the distinction between `@Valid` and `@NotNull`.

### 27.3. Testing a Missing Child While Parent Exists

Supply:

~~~text
app.name=Order Service
app.client.base-url=https://api.example.test
app.client.http.connect-timeout=2s
app.client.http.read-timeout=5s
app.client.http.max-connections=20
~~~

while omitting the `retry` branch. With **`@NotNull Retry retry`**, a validation error should occur if the Binder supplies no default `Retry`. This is a classic test for required nested branches.

## 28. Testing Cascaded Validation on `List`/`Map`

Using `EndpointProperties` from section 11, supply:

~~~properties
app.endpoints[0].name=primary
app.endpoints[0].url=
app.endpoints[0].timeout=3s
~~~

Because the `List` is non-empty, `@NotEmpty` passes, yet **`@NotBlank`** on `Endpoint.url` must fail if cascading works.

Another test:

~~~properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://api.example.test
app.endpoints[0].timeout=3s
~~~

contains valid data and lets the context create the bean.

Similarly for `Map`:

~~~properties
app.regions.asia.endpoint=
app.regions.asia.timeout=5s
~~~

Because the `Map` has an entry, `@NotEmpty` passes; since the value carries `@Valid`, `@NotBlank` on `Region.endpoint` fails.

**Tests should separate container constraints from element constraints.** If you only test an empty `Map`, you prove `@NotEmpty` works without proving `@Valid` actually entered `Region`.

## 29. `@Valid` Does Not Make Collections Immutable

A configuration record having:

~~~java
List<@Valid Endpoint> endpoints
~~~

validates its elements. It does not stop other code from calling `endpoints.add(...)` if the `List` is mutable.

To prevent post-startup mutation:

~~~java
public EndpointProperties {
    endpoints = endpoints == null
            ? List.of()
            : List.copyOf(endpoints);
}
~~~

This protects the outer collection, while `@Valid` guards the validity of each element.

Two independent responsibilities:

| Mechanism | What Does It Guarantee? |
| --- | --- |
| `@Valid` | Evaluates child object constraints |
| `@NotEmpty` | Collection is not empty |
| `List.copyOf` | Collection cannot be mutated through its API after copying |
| `@ConfigurationProperties` | Binds configuration sources into Java types |
| `PropertySource` precedence | Determines which source wins |

Do not use defensive copies as a substitute for validation, nor `@Valid` as a substitute for immutability.

## 30. When Using a Custom Spring Boot `Validator`

Beyond Jakarta Bean Validation, Spring Boot also lets you configure **`org.springframework.validation.Validator`** at integration points. In projects needing complex rules, a custom `Validator` can complement or replace annotations, provided it integrates cleanly into the configuration-properties lifecycle.

Distinctions to keep clear:

- **Jakarta `@Valid`** is metadata for cascaded validation.
- **Jakarta constraints** like `@NotBlank`/`@Min` describe data constraints.
- **Spring `Validator`** is a separate validation API invokable at Spring integration hooks.
- **`@Validated`** can carry validation group metadata in supported contexts.

Never write a `Validator` implementation and expect Spring Boot to discover it automatically without registration. For typical nested configuration needs, Jakarta Bean Validation with `@Validated` + `@Valid` is usually simpler and clearer.

## 31. Validation Groups: When Policies Differ

Jakarta Validation supports **validation groups**, useful when the exact same type needs different constraint sets in specific contexts.

However, with externalized configuration, constraints usually need to be predictable right at startup. Varying groups per environment or profile can make the configuration contract harder to reason about.

If the requirement is "production must supply a property, local can omit it," clearer options usually include:

- Designing explicit local default values.
- Splitting mandatory and optional settings by module.
- Applying an intentional conditional constraint.
- Writing tests for the actual profile combinations in use.

Only use validation groups when your project genuinely needs them and you have verified exactly which group Spring Boot applies to configuration beans.

## 32. Cycles in Object Graphs

Bean Validation can cascade across multiple objects. In tree-shaped configurations bound from YAML, object graphs are normally acyclic and easy to validate.

If Java classes manually create cyclic references between parent and child, or share a single instance across branches, the validation graph becomes complex. Jakarta Validation providers handle graph cycles, yet cyclic configuration structures are confusing for the Binder as well.

Externalized configuration should favor **simple trees or DAGs** over arbitrary object graphs. Model cross-references via identifiers or lookup keys when complex relationships are needed.

## 33. Comprehensive Example: Server Cluster Configuration

YAML:

~~~yaml
cluster:
  name: "orders"
  regions:
    asia:
      endpoint: "https://asia.example.test"
      timeout: 4s
    europe:
      endpoint: "https://eu.example.test"
      timeout: 5s
  nodes:
    - name: node-a
      host: node-a.example.test
      port: 8080
    - name: node-b
      host: node-b.example.test
      port: 8081
~~~

Record:

~~~java
package example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "cluster")
public record ClusterProperties(
        @NotBlank String name,
        @NotEmpty Map<@NotBlank String, @NotNull @Valid Region> regions,
        @NotEmpty List<@NotNull @Valid Node> nodes
) {
    public record Region(
            @NotBlank String endpoint,
            @NotNull Duration timeout
    ) {}

    public record Node(
            @NotBlank String name,
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

Notable paths:

~~~text
cluster.name
cluster.regions.asia.endpoint
cluster.regions.asia.timeout
cluster.regions.europe.endpoint
cluster.regions.europe.timeout
cluster.nodes[0].name
cluster.nodes[0].host
cluster.nodes[0].port
cluster.nodes[1].name
cluster.nodes[1].host
cluster.nodes[1].port
~~~

This configuration has three validation layers:

1. Root: `name` is required; `regions` and `nodes` must have entries/elements.
2. Container: region keys cannot be blank; region values and node elements cannot be null.
3. Nested value objects: `Region.endpoint`, `Region.timeout`, and `Node.name`/`host`/`port` must be valid.

If `node-b.port = 0`, **`@Min(1)`** fails. If `regions.europe.endpoint = ""`, **`@NotBlank`** fails. If `nodes` is empty, **`@NotEmpty`** on the `List` fails rather than any constraint on `Node`.

## 34. Security Configuration Case

A security configuration may contain an issuer, public key location, or token audience. Such fields typically have strict presence requirements.

~~~java
@Validated
@ConfigurationProperties(prefix = "app.security")
public record SecurityProperties(
        @Valid @NotNull Jwt jwt
) {
    public record Jwt(
            @NotBlank String issuer,
            @NotBlank String audience
    ) {}
}
~~~

If an application requires JWT authentication in every environment, do not provide a default **`issuer="localhost"`** just to let validation pass. A missing issuer must be caught early.

On the other hand, `@NotBlank` only checks that the string has content; it does not confirm the issuer is trusted, the URL is reachable, or token signatures are verified properly. Configuration validation is **one defense layer**, not a substitute for sound security design.

In logs, avoid printing secrets or entire `SecurityProperties` instances if the record contains sensitive information.

## 35. Practice 1: Missing `@Valid`

Given the code:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(Client client) {
    public record Client(
            @NotBlank String baseUrl
    ) {}
}
~~~

Configuration:

~~~yaml
app:
  client:
    base-url: ""
~~~

Identify what must be added to ensure validation descends into `Client`.

Answer:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid Client client
) {
    public record Client(@NotBlank String baseUrl) {}
}
~~~

If `client` must be present as an object, use **`@Valid @NotNull Client client`**.

## 36. Practice 2: Nulls and Cascaded Validation

Code:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid Client client
) {
    public record Client(@NotBlank String endpoint) {}
}
~~~

No `app.client.*` properties exist.

Question: does `@Valid` alone mean `client` cannot be null? **No.** Under cascade rules, null does not cause the validator to descend or produce a violation. To catch the missing branch, add **`@NotNull`** on `client` or an equivalent business constraint.

## 37. Practice 3: Two Levels of Nesting

Configuration:

~~~yaml
app:
  http:
    pool:
      max-size: 0
~~~

Model:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid @NotNull Http http
) {
    public record Http(
            @Valid @NotNull Pool pool
    ) {}

    public record Pool(
            @Min(1) int maxSize
    ) {}
}
~~~

Question: why must `@Valid` appear on `Http.pool`? Because the validator needs a cascade path from `Http` to `Pool` in order to evaluate `@Min(1)`. Having `@Valid` only on `http` at the root should not be assumed to validate `Pool`'s inner constraints under standard cascade contracts.

## 38. Practice 4: `List` Element with Invalid Data

YAML:

~~~yaml
app:
  providers:
    - name: fast
      timeout: 2s
    - name: ""
      timeout: 3s
~~~

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty List<@Valid Provider> providers
) {
    public record Provider(
            @NotBlank String name,
            @NotNull Duration timeout
    ) {}
}
~~~

The `List` has two elements, so **`@NotEmpty`** passes. However, the second element has a blank name, so `Provider`'s constraint fails thanks to `@Valid` on the element type. This illustrates the difference between container validation and element validation.

## 39. Practice 5: `Map` Value and Nested `@Valid`

YAML:

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
    europe:
      endpoint: ""
~~~

Record:

~~~java
@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty Map<String, @Valid Region> regions
) {
    public record Region(
            @NotBlank String endpoint
    ) {}
}
~~~

Question: is having two entries in the `Map` enough for the config to be valid? No. `@NotEmpty` only checks entry count; `@Valid` directs the validator into each entry's `Region`, catching the blank `europe.endpoint`.

## 40. Practice 6: Conditional Constraints

YAML:

~~~yaml
app:
  notifications:
    enabled: false
~~~

Suppose `endpoint` is required only when `enabled=true`. If you write:

~~~java
public record Notifications(
        boolean enabled,
        @NotBlank String endpoint
) {}
~~~

the `endpoint` constraint applies unconditionally even when `enabled=false`. If business rules allow `endpoint` to be omitted when disabled, direct `@NotBlank` does not fit.

A solution using an invariant:

~~~java
public record Notifications(
        boolean enabled,
        String endpoint
) {
    @AssertTrue
    public boolean isConfigurationValid() {
        return !enabled || (endpoint != null && !endpoint.isBlank());
    }
}
~~~

For the invariant on `Notifications` to run when nested inside `AppProperties`, cascade into `Notifications` by putting `@Valid` on the reference.

## 41. Practice 7: Validation for `Duration`

Record:

~~~java
public record TimeoutProperties(
        @NotNull Duration timeout
) {}
~~~

Configured timeout: **`0s`**. Question: does `@NotNull` fail? **No**, because `Duration.ZERO` is not null.

To require positivity, use a `Duration`-compatible constraint or a rule such as:

~~~java
@AssertTrue
public boolean isTimeoutPositive() {
    return timeout != null && !timeout.isZero() && !timeout.isNegative();
}
~~~

Place the invariant on the appropriate object and ensure that object lies on a validated path.

## 42. Practice 8: Identifying the Real Error

Consider:

~~~yaml
app:
  client:
    http:
      max-connections: "many"
~~~

Java:

~~~java
public record Http(
        @Min(1) int maxConnections
) {}
~~~

Question: is the cause a missing `@Valid`? We cannot jump to that conclusion. **`many`** cannot convert to `int`, so a conversion error occurs before validation. Fix the value to a valid integer first, then verify `@Min`.

This is a diagnostic rule: **validation does not replace conversion**.

## 43. Nested Validation Debugging Workflow

When invalid config still allows the app to run or produces unclear errors, trace in order:

1. **Check the prefix** of the `@ConfigurationProperties` class.
2. **Write out the full property path** to the field, e.g., `app.client.http.max-connections`.
3. **Inspect sources**: YAML, `.properties`, profiles, env vars, JVM properties, CLI flags, and imports.
4. **Check target types and conversion**: `int`, `String`, `Duration`, `List`, `Map`.
5. **Check whether the child object is instantiated**: constructor binding, setter binding, default, or null.
6. **Check that root has `@Validated`** and a Jakarta Validation provider is present.
7. **Check `@Valid` on every nested boundary** requiring cascading.
8. **Check `@NotNull` or `@NotEmpty`** for required objects/collections.
9. **Check constraints on target fields**: `@NotBlank`, `@Min`, `@Size`, or custom validators.
10. **Inspect the startup failure root cause** and write a test reproducing the exact scenario.
11. **Avoid printing sensitive data** in diagnostic logs.
12. **Check data after precedence resolution** rather than reading only one source file.

A clean mental checklist:

~~~text
Correct key name?
   |
   v
Source active?
   |
   v
Bind + conversion succeeded?
   |
   v
Nested object exists?
   |
   v
Validation enabled?
   |
   v
@Valid cascades to target depth?
   |
   v
Field/container/element constraint correct?
~~~

If one stage fails, adding annotations at a different stage will not resolve the root cause.

## 44. Real-World Project Conventions

Conventions that keep Spring Boot configuration maintainable:

- Use **`@ConfigurationProperties`** to group related configuration cohesively.
- Put **`@Validated`** on configuration beans that need startup validation.
- Put **`@Valid`** on child objects and container elements when deep validation is required.
- Put **`@NotNull`** when a branch is required; do not misuse `@Valid` as a substitute for `@NotNull`.
- Use **`@NotBlank`** for non-whitespace strings; **`@NotEmpty`** for non-empty collections.
- For numbers, use range constraints such as `@Min`, `@Max`, or `@Positive`.
- For `Duration`, `URI`, or multi-field rules, pick matching Java types and type-compatible constraints.
- Write **tests for missing branches**, **blank fields**, **wrong types**, and **invalid `List`/`Map` elements**.
- Avoid fake plausible defaults when required values must come from deployment.
- Never build validation on side effects or uncontrolled external connections.
- Never log secret-bearing config records because `toString` exposes component values.
- Never treat successful application startup as proof that every nested config branch was validated.

For stronger guarantees, require every important configuration group to have at least two tests: one valid configuration and one intentionally invalid nested configuration.

## 45. Summary

**`@Validated`** and **`@Valid`** frequently appear together in Spring Boot yet are not synonymous.

- **`@Validated`** on a **`@ConfigurationProperties`** bean tells Spring Boot to trigger validation during binding under compatible integration.
- **`@Valid`** signals **cascaded validation**: continue checking nested objects, `List` elements, or `Map` values.
- **`@NotNull`** requires an object or field to exist. **`@Valid` does not forbid null**.
- Across multiple nesting levels, the cascade path must pass through every level to be checked.
- **`@NotEmpty`** checks collection size; element-level constraints still require `@Valid` or container-element metadata.
- Absent config, blank strings, wrong types, and type-valid constraint violations are distinct issues.
- Constructor binding, setter binding, and defaults determine **which objects get created**; Bean Validation determines **whether created objects satisfy the contract**.
- Validation runs **after Spring resolves sources and the Binder processes values**, so separate precedence from constraint logic.
- A solid validation model enables **fail-fast** behavior on invalid critical settings and ties error messages to specific property paths.

A handy rule of thumb: **root gets `@Validated`, deep branches get `@Valid`, mandatory branches get `@NotNull`, and every field/container gets business-accurate constraints**. Applied consistently, nested configuration becomes an explicit data contract instead of a collection of values checked only when the first request arrives.