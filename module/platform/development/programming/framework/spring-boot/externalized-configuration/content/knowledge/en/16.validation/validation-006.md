# Validating Collection Elements and Map Values

In Spring Boot Externalized Configuration, configuration does not consist solely of single scalar values. An application may bind endpoint lists, email sets, job lists, or named connection maps into a `@ConfigurationProperties` bean. For those structures, **validation** does not stop at checking whether the collection exists: individual elements, `Map` keys, and objects stored as `Map` values can each carry their own rules.

For example, `@NotEmpty List<Endpoint>` only indicates that the list is neither null nor empty; it does not ensure every `Endpoint` has a valid URL, timeout, and name. Likewise, `@NotEmpty Map<String, Client>` does not mean every `Client` in the map has been validated. Validating nested objects requires **cascaded validation** via `@Valid` or **container-element constraints** placed directly on element types, combined with `@Validated` on the configuration-properties root and a compatible Bean Validation provider.

This lesson focuses on Jakarta Bean Validation in Spring Boot 3.x: `List`, `Set`, `Map`, container-element constraints, recursive checks, binding errors vs. validation errors, profile effects, and testing. Examples assume Java 17+ and Spring Boot 3.x; for older versions using `javax.validation` or different mechanisms, adjust imports and dependencies accordingly.

## 1. Why Does Collection Validation Differ from Scalar Validation?

Suppose we have:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: "backup"
      url: "https://backup.example.invalid"
      max-retries: 2
~~~

A Java type:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<Endpoint> endpoints) {

    public record Endpoint(
            String name,
            URI url,
            int maxRetries
    ) {}
}
~~~

The Binder can construct a `List<Endpoint>` containing an element with `name=null`, `url=null`, or `maxRetries=-1`. Binding success alone does not prove the configuration is safe to use.

Independent validation questions:

1. Is the list declared?
2. Does the list contain at least one element?
3. Is every element non-null?
4. Are the fields of each element valid?
5. Are there cross-element rules, such as unique names?
6. Are there cross-collection or cross-map constraints within the same properties bean?

One annotation usually answers only **part** of those questions. Choose constraints at the right level.

## 2. Setting Up Bean Validation for Spring Boot

In Spring Boot 3.x, examples use annotations from `jakarta.validation` and `jakarta.validation.constraints`. In a project using Spring Boot starters, the standard dependency is:

~~~xml
<!-- Maven -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Or Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

The starter provides Bean Validation integration with a compatible provider, typically Hibernate Validator per Spring Boot's dependency management. Do not add only an annotation API and assume a runtime validator is automatically present to evaluate it.

To have Spring Boot validate typed configuration properties, place `@Validated` on the root properties class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(/* ... */) {}
~~~

And register it as a configuration-properties bean:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
class RoutingConfiguration {
}
~~~

You can use `@ConfigurationPropertiesScan` instead if that is your project's convention. Annotating `@ConfigurationProperties` without proper registration can leave the bean uncreated. Registering the bean without a compatible validator likewise does not guarantee constraints run.

**Separation of roles:** the Binder turns config sources into objects; Bean Validation verifies those objects against declared rules after binding.

## 3. Does the Collection Exist? `@NotNull`, `@NotEmpty`, and `@Size`

For `List`, `Set`, or `Map`, common container constraints are:

| Constraint | Null | Empty Collection | Non-Empty Collection |
| --- | --- | --- | --- |
| `@NotNull` | Invalid | Valid | Valid |
| `@NotEmpty` | Invalid | Invalid | Valid |
| `@Size(min = 2, max = 10)` | Null is usually treated as valid | Invalid for min=2 | Valid if count within range |
| `@NotNull @Size(min = 2)` | Invalid | Invalid | Valid if enough elements |

Example:

~~~java
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        @NotEmpty
        @Size(max = 20)
        List<String> tags,

        @NotEmpty
        Map<String, String> labels
) {}
~~~

These are only **root-level collection checks**. They do not specify that each tag must be non-empty or that each map value cannot be blank.

Important: under Bean Validation, many constraints like `@Size` accept `null`; if the property must be present and within bounds, combine it with `@NotNull` or `@NotEmpty`.

For example, requiring at least two destinations:

~~~java
@NotNull
@Size(min = 2, max = 5)
List<Endpoint> endpoints
~~~

If the collection is absent, `@NotNull` catches it. If the collection is empty or has only one element, `@Size` catches it. If there are two elements and one has a null URL, **both constraints still pass**; element-level validation is needed.

## 4. Validating Each String: `List<@NotBlank String>`

Suppose configuration has:

~~~yaml
notification:
  recipients:
    - "ops@example.invalid"
    - ""
    - "alerts@example.invalid"
~~~

If Java only writes:

~~~java
@NotEmpty
List<String> recipients
~~~

the list has three elements, so `@NotEmpty` passes. The `""` element goes unchecked.

To require every string not to be blank:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

@NotEmpty
List<@NotBlank String> recipients
~~~

`@NotBlank` sits on the **type argument** of `List`, constraining each `String` element. With Jakarta Bean Validation supporting container-element validation, the validator checks every value yielded by the `List` value extractor.

You can also layer email format checking:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

List<@NotBlank @Email String> recipients
~~~

Notes:

- `@Email` checks syntax per the Bean Validation provider; it does not send an email to verify deliverability.
- `@NotBlank` ensures non-null, non-empty, and non-whitespace-only; it suits `String`, not numbers.
- `@NotEmpty` on `List` ensures **at least one element**, unlike `@NotBlank` on each element.
- If recipients are optional, you can omit `@NotEmpty` at the `List` level while keeping element constraints whenever the `List` is present.

Complete example:

~~~java
package example.notification;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank @Email String> recipients
) {}
~~~

If YAML includes a blank address, validation causes Spring Boot to reject creation of the configuration-properties bean rather than letting the app continue and fail when sending notifications.

## 5. Validating Numbers in a Collection: `List<@Min(...) Integer>`

A batch system has tiered retry limits:

~~~yaml
batch:
  retry-limits:
    - 1
    - 3
    - 0
~~~

To require each value to fall between 1 and 10:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

@NotEmpty
List<@NotNull @Min(1) @Max(10) Integer> retryLimits
~~~

These constraints have distinct jobs:

- `@NotEmpty`: `List` must have elements.
- `@NotNull` on `Integer`: null elements are rejected.
- `@Min(1)`: numbers under 1 are rejected.
- `@Max(10)`: numbers over 10 are rejected.

Do not use `@NotBlank` with `Integer` because that is a string constraint. Do not rely on `@Min(1)` alone assuming nulls are forbidden: numeric constraints normally allow null unless paired with `@NotNull`.

If YAML contains `retry-limits: ["many"]`, the Binder fails converting `"many"` to `Integer` **before validation** runs. That is a conversion/binding error, distinct from integer `0` being rejected by `@Min(1)`.

## 6. Validating Objects Inside a `List` with `@Valid`

The most common case is `List<Endpoint>`:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: ""
      url: "https://backup.example.invalid"
      max-retries: 0
~~~

A nested record with constraints:

~~~java
package example.routing;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;

public record Endpoint(
        @NotBlank String name,
        @NotNull URI url,
        @Min(1) int maxRetries
) {}
~~~

If the root declares:

~~~java
@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty List<Endpoint> endpoints
) {}
~~~

having constraints on `Endpoint`'s fields **is not enough to ensure they are evaluated**. You must declare **cascaded validation**:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

@NotEmpty
List<@NotNull @Valid Endpoint> endpoints
~~~

Here:

- `@NotEmpty` checks the `List`.
- `@NotNull` inside angle brackets checks that each element is non-null.
- `@Valid` inside angle brackets instructs the validator to descend into each `Endpoint` to check `name`, `url`, and `maxRetries`.

You can place `@Valid` on the container property—e.g., `@Valid List<Endpoint> endpoints`—to cascade across the collection with a supporting Bean Validation provider. Placing it on the type argument `List<@Valid Endpoint>` usually makes the **validation target** clearer, especially with multi-level collections.

**Do not put `@Valid` on elements thinking it replaces `@NotNull`.** In Bean Validation, cascading across a null element does not trigger inner field checks; if null elements must be rejected, add `@NotNull`.

## 7. Complete Example: `List` of Nested Objects

A complete root properties class with structure and validation:

~~~java
package example.routing;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty
        @MaxItems(5)
        List<@NotNull @Valid Endpoint> endpoints
) {
    public record Endpoint(
            @NotBlank String name,
            @NotNull URI url,
            @Min(1) @Max(10) int maxRetries
    ) {}
}
~~~

In this snippet, `@MaxItems(5)` is **a hypothetical custom constraint**, not a standard Jakarta Validation annotation. If you only need a standard Bean Validation size cap, use `@Size(max = 5)`:

~~~java
import jakarta.validation.constraints.Size;

@NotEmpty
@Size(max = 5)
List<@NotNull @Valid Endpoint> endpoints
~~~

Registration:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
class RoutingConfiguration {}
~~~

Valid configuration:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: "backup"
      url: "https://backup.example.invalid"
      max-retries: 2
~~~

Invalid configuration:

~~~yaml
routing:
  endpoints:
    - name: ""
      url: "https://primary.example.invalid"
      max-retries: 0
~~~

When the application has a validation provider and binding enabled, `name` violates `@NotBlank` and `maxRetries` violates `@Min(1)`. Startup is rejected with a configuration error; violation paths typically point to `routing.endpoints[0]` or a similar path depending on how the provider/Boot formats it.

For runnable standalone examples, use the `@Size(max = 5)` version so no custom annotation is required.

## 8. Container-Element Constraints vs. Cascading Are Different

Compare two annotation styles:

~~~java
List<@NotBlank String> labels
~~~

and:

~~~java
List<@Valid Endpoint> endpoints
~~~

The first requires each **`String` element value** to satisfy a direct constraint. The second requests **descending into `Endpoint`'s fields** to check constraints declared on that class/record.

If you write only:

~~~java
List<@Valid String> labels
~~~

`@Valid` does not substitute for `@NotBlank`, because `String` carries no internal Bean Validation constraints to cascade into like a configuration object.

If you write only:

~~~java
List<@NotNull Endpoint> endpoints
~~~

non-null elements are enforced, yet `name` and `url` can still go unchecked without cascading.

When objects must both exist and have valid fields, combine them:

~~~java
List<@NotNull @Valid Endpoint> endpoints
~~~

Choosing the right annotation determines whether validation actually covers the elements.

## 9. `Set`: Validating Elements Without Assuming Order

`Set` is another collection bindable from externalized configuration:

~~~yaml
security:
  roles:
    - "ADMIN"
    - "VIEWER"
~~~

Properties:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.Set;

@NotEmpty
Set<@NotBlank String> roles
~~~

Container-element constraints validate each element just like `List`. However:

- `Set` models uniqueness, not business ordering.
- Duplicate entries can be collapsed under `Set` semantics; post-binding `Set` validation does not guarantee detection of every duplicate in the original YAML.
- If you need an ordered list of roles, `Set` is the wrong type.
- If duplicate input entries must be forbidden prior to `Set` deduplication, choose a different model or pre-binding check that inspects raw input.

`@Size(min = 2)` on a `Set` checks element count **after binding into the `Set`**, not whether the original input contained two semantically distinct values.

## 10. Validating a `Map`: Three Independent Levels

For a `Map`, separate three questions:

1. **Does the `Map` exist and contain entries?** `@NotEmpty Map<...>`.
2. **Are `Map` keys valid?** Container-element constraints on the key type, e.g., `Map<@NotBlank String, ...>`.
3. **Are `Map` values valid?** Direct constraints on the value type, or `@Valid` to cascade into object values.

Example:

~~~yaml
rates:
  categories:
    standard: 1.0
    premium: 1.5
~~~

Root:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "rates")
public record RateProperties(
        @NotEmpty
        Map<
            @NotBlank String,
            @NotNull @DecimalMin("0.01") BigDecimal
        > categories
) {}
~~~

Meaning:

- The `Map` is not empty.
- Each key is a non-blank string.
- Each value is non-null and at least `0.01`.
- Values like `0` or `-2` violate `@DecimalMin`.

`Map` keys may be processed/normalized by the Binder per property naming rules. Constraints evaluate **the bound keys**, not necessarily the raw YAML text. If business rules require keys with special characters, handle bracket notation and `Map` binding rules separately.

## 11. `Map<String, @NotBlank String>` for Validating String Values

Example configuring headers:

~~~yaml
client:
  headers:
    X-Client-Id: "order-service"
    X-Region: ""
~~~

Java:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.Map;

@NotEmpty
Map<String, @NotBlank String> headers
~~~

`@NotEmpty` only sees that the `Map` has two entries. `@NotBlank` on the value type inspects each `String` value. The entry with `""` fails validation.

If keys must also be non-blank:

~~~java
@NotEmpty
Map<@NotBlank String, @NotBlank String> headers
~~~

Keep in mind this only validates **bound data**. For real HTTP header names, `@NotBlank` alone is insufficient: header names must also follow HTTP character rules, requiring a dedicated validator. Never log sensitive header values such as authorization tokens when debugging errors.

## 12. `Map` with Object Values: `@Valid` on the Value Type

An application has multiple outbound clients:

~~~yaml
connectors:
  clients:
    billing:
      base-url: "https://billing.example.invalid"
      timeout: 3s
      pool-size: 10
    inventory:
      base-url: "https://inventory.example.invalid"
      timeout: 2s
      pool-size: 8
~~~

Typed properties:

~~~java
package example.connectors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "connectors")
public record ConnectorsProperties(
        @NotEmpty
        Map<
            @NotBlank String,
            @NotNull @Valid Client
        > clients
) {
    public record Client(
            @NotNull URI baseUrl,
            @NotNull Duration timeout,
            @Min(1) int poolSize
    ) {}
}
~~~

With `@Valid` on the `Map` value type, Bean Validation descends into each `Client` object to validate its three fields. If `inventory.pool-size=0` or `billing.timeout` is absent, the corresponding constraint fails.

If you declare only:

~~~java
@NotEmpty
Map<String, Client> clients
~~~

then having an entry satisfies `@NotEmpty`, while constraints inside `Client` are not automatically traversed. Explicit cascading is needed.

Some codebases write:

~~~java
@Valid
Map<String, Client> clients
~~~

to cascade across values. The `Map<String, @Valid Client>` syntax makes it crystal clear that you want to validate **each `Map` value**, not just the `Map` itself.

## 13. Do Not Accidentally Put `@Valid` on the Key

With:

~~~java
Map<String, Client> clients
~~~

the usual intent is validating each `Client` in the **value position**. Writing:

~~~java
Map<@Valid String, Client> clients
~~~

does not validate `Client` fields, because `@Valid` is placed on the key type. To validate key names, use constraints like `@NotBlank` or `@Pattern`:

~~~java
Map<
    @NotBlank String,
    @NotNull @Valid Client
> clients
~~~

Avoid scattering `@Valid` mechanically at every position: identify **which types are composite objects to traverse**, and which constraints apply directly to strings or numbers.

## 14. Nested `Map`s and Nested `List`s

Structures can look like:

~~~yaml
policies:
  groups:
    public:
      - code: "READ"
        limit: 100
      - code: "SEARCH"
        limit: 50
    internal:
      - code: "WRITE"
        limit: 20
~~~

Configuration type:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "policies")
public record PolicyProperties(
        @NotEmpty
        Map<
            @NotBlank String,
            @NotEmpty List<@NotNull @Valid Rule>
        > groups
) {
    public record Rule(
            @NotBlank String code,
            @Min(1) int limit
    ) {}
}
~~~

Here there are multiple layers:

- Root `Map` `groups` must have entries.
- `Map` keys must not be blank.
- Each group's `List` must not be empty.
- Each `Rule` must not be null.
- Bean Validation cascades into each `Rule` to check `code` and `limit`.

Multi-level validation relies on the provider having a **`ValueExtractor`** supporting the container types used, such as standard `Map` and `List`. For custom container classes, you may need a custom `ValueExtractor`; do not assume every generic wrapper is automatically traversed.

Complex configurations should always be verified with real integration tests rather than guessing from annotations alone.

## 15. `Map` Merging Across Property Sources Does Not Replace Validation

Spring Boot applies different binding rules to `Map` vs. `List` when multiple sources define the same collection. For `Map`, keys can merge across property sources; for `List`, a higher-precedence source normally replaces the entire `List`.

Base file:

~~~yaml
# application.yml
connectors:
  clients:
    billing:
      base-url: "https://billing.example.invalid"
      timeout: 3s
      pool-size: 10
    inventory:
      base-url: "https://inventory.example.invalid"
      timeout: 2s
      pool-size: 8
~~~

Dev file:

~~~yaml
# application-dev.yml
connectors:
  clients:
    billing:
      base-url: "http://localhost:9090"
~~~

With `Map<String, Client>`, the `billing` entry can take its URL from dev while taking timeout and pool size from base; the `inventory` entry can still come from base. Validation applies to the **effective object after binding**, not isolated snippets in the dev file.

This is often convenient, yet poses a risk: an operator thinks they deleted a field by omitting it from the dev file, while the `Map` still inherits it from the base file. If a field must never inherit across environments, design sources and constraints explicitly.

In particular, JSON `null` in `SPRING_APPLICATION_JSON` does not automatically delete a property from a lower-precedence source. Do not rely on null as a deletion marker to bypass or trigger validation.

## 16. `List` Replacement Can Leave Elements Missing Data

Base configuration:

~~~yaml
# application.yml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      max-retries: 3
    - name: "backup"
      url: "https://backup.example.invalid"
      max-retries: 2
~~~

Dev file specifies only:

~~~yaml
# application-dev.yml
routing:
  endpoints:
    - name: "local"
      url: "http://localhost:9080"
~~~

When `dev` is active and its list wins, there is only one `local` endpoint; `max-retries` is **not** inherited from `primary` in the base file.

If Java uses:

~~~java
@Min(1) int maxRetries
~~~

the missing value becomes primitive default `0`, leading to a validation failure. This is helpful: if retry count must be at least 1, the context should reject the incomplete configuration instead of misbehaving.

If `Integer` is used with `@Min(1)`, add `@NotNull` to forbid missing values; numeric constraints normally let null pass.

In tests, activate the relevant profile and validate **each element after binding**, rather than merely checking that the dev YAML is syntactically valid.

## 17. Difference Between `@NotNull` on Value and `@Valid` Cascade

Map example:

~~~java
Map<String, @NotNull Client> clients
~~~

Requires each value to be non-null, yet **does not automatically validate fields inside `Client`**.

Conversely:

~~~java
Map<String, @Valid Client> clients
~~~

cascades into fields of non-null `Client`s, yet `@Valid` does not turn a null value into a violation by itself.

If you need both:

~~~java
Map<String, @NotNull @Valid Client> clients
~~~

Likewise for `List`:

~~~java
List<@NotNull @Valid Endpoint> endpoints
~~~

If you write only:

~~~java
@NotNull Map<String, Client> clients
~~~

a non-empty `Map` containing null values can still pass the root container constraint. Place constraints at the right level.

## 18. Constraints Only Apply to Compatible Types

Each constraint supports a specific set of types. Not every annotation works on every field type.

| Data Type | Common Constraints | Purpose |
| --- | --- | --- |
| `String` | `@NotBlank`, `@Size`, `@Pattern`, `@Email` | String content/format |
| `Integer` / `Long` | `@Min`, `@Max`, `@Positive` | Numeric bounds |
| `BigDecimal` | `@DecimalMin`, `@DecimalMax`, `@Digits` | Decimal values |
| `List` / `Set` / `Map` | `@NotNull`, `@NotEmpty`, `@Size` | Presence and size |
| Nested object | `@Valid` | Cascade into object fields |
| Nullable object | `@NotNull` | Forbid null |
| `Duration` | `@NotNull` and custom check when positive needed | Presence and duration rules |
| `URI` | `@NotNull`, plus dedicated scheme/host checks | Non-null URI alone does not guarantee safety |

For example, putting `@NotBlank` or `@Min(1)` directly on `Duration` can cause a validator error indicating no validator supports that type, rather than giving you the intended check.

When a positive duration is required, use a class-level validator, custom constraint, or client initialization check. Do not expect built-in constraints to verify every domain invariant automatically.

## 19. Validating `Map` Keys Themselves

Suppose client keys must follow `lowercase-kebab-case`:

~~~java
import jakarta.validation.constraints.Pattern;
import java.util.Map;

Map<
    @Pattern(regexp = "[a-z][a-z0-9-]*") String,
    @Valid Client
> clients
~~~

Constraints on `String` keys validate names after Binder processing. However, if keys contain dots, slashes, brackets, or special characters, Spring Boot uses **`Map` binding and bracket notation** rules to preserve keys:

~~~yaml
features:
  labels:
    "[/api/v1]": "public"
~~~

For `Map`s with special characters in keys, YAML generally requires bracket notation and proper quoting. If a key is normalized differently from what you expect before Bean Validation runs, constraints cannot recover the original raw characters.

Do not use `Map` key constraints as a substitute for valid key schema design or application route/path validation.

## 20. Type Mismatches Happen Before Validation

With:

~~~yaml
connectors:
  clients:
    billing:
      pool-size: "many"
~~~

Java:

~~~java
@Min(1) int poolSize
~~~

The Binder must convert `"many"` to `int`. If conversion fails, Spring Boot reports a binding error before Bean Validation ever checks `@Min(1)`. Contrast this with:

~~~yaml
connectors:
  clients:
    billing:
      pool-size: 0
~~~

`0` binds to `int` cleanly, yet fails `@Min(1)`.

Diagnostic breakdown:

| Error Category | Example | Resolution |
| --- | --- | --- |
| Malformed YAML | Bad indentation, invalid `:` | Fix YAML |
| Conversion/binding | `"many"` for `int` | Fix property value or converter |
| Collection constraint | Empty list failing `@NotEmpty` | Supply valid elements |
| Element constraint | List containing `""` failing `@NotBlank` | Fix element value |
| Cascaded validation | Endpoint missing URL | Fix nested property or default |
| Map key constraint | Key failing regex | Normalize key name |
| Map value constraint | Pool size `0` | Fix value or contract |
| Bean registration | No `@ConfigurationProperties` bean | Enable/scan the type properly |

Never "fix" validation failures by removing `@Validated` or catching broad exceptions to let startup continue. If production needs those fields, failing fast is valuable.

## 21. `@Valid` Does Not Replace a Bean Validation Provider

Annotated code like:

~~~java
@Validated
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        List<@Valid Target> targets
) {}
~~~

does not guarantee every field is checked if the project lacks a validation provider or bean registration. You need:

- Compatible Jakarta Bean Validation dependency.
- An implementation such as Hibernate Validator or your project's chosen provider.
- Properly registered configuration-properties bean.
- `@Validated` or an equivalent validation trigger.
- Concrete constraints on `Target` and nested types.
- `@Valid` at the right boundaries to cascade.

If a nested object declares no constraints, `@Valid` traverses the object yet has no way to guess "which fields are required." Mandatory rules must be stated explicitly.

## 22. Why Does `@NotEmpty` on a `Map` Not Guarantee Non-Null Values?

Example:

~~~java
@NotEmpty
Map<String, String> labels
~~~

A `Map` with one entry whose value is `null` is **not empty**. `@NotEmpty` checks the size of the `Map`, not the values inside.

If every value must be a non-blank string:

~~~java
@NotEmpty
Map<String, @NotBlank String> labels
~~~

If values are objects:

~~~java
@NotEmpty
Map<String, @NotNull @Valid LabelSettings> labels
~~~

This is why `Map` configuration must be checked at three levels at minimum: `Map` root, `Map` keys, and `Map` values.

## 23. Focused Example: Multi-Channel Notification Configuration

Suppose an application sends notifications across multiple channels keyed by ID.

~~~yaml
notification:
  default-recipients:
    - "ops@example.invalid"
    - "audit@example.invalid"
  channels:
    email:
      enabled: true
      endpoint: "https://mail.example.invalid"
      attempts: 3
      tags:
        - "critical"
        - "audit"
    webhook:
      enabled: false
      endpoint: "https://hooks.example.invalid"
      attempts: 1
      tags:
        - "system"
~~~

Java type:

~~~java
package example.notification;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank @Email String> defaultRecipients,

        @NotEmpty
        Map<@NotBlank String, @NotNull @Valid Channel> channels
) {
    public record Channel(
            boolean enabled,
            @NotNull URI endpoint,
            @Min(1) @Max(10) int attempts,
            @NotEmpty @Size(max = 8)
            List<@NotBlank String> tags
    ) {}
}
~~~

Registration:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotificationProperties.class)
class NotificationConfiguration {}
~~~

This example validates:

1. `defaultRecipients` is not empty.
2. Every recipient address is non-blank and has valid email syntax.
3. `channels` `Map` is not empty.
4. Every channel key is non-blank.
5. Every `Channel` value is non-null and cascaded into its fields.
6. `endpoint` is non-null.
7. `attempts` is within `1..10`.
8. Each channel's `tags` is non-empty and at most 8 elements.
9. Every tag is non-blank.

**Further design consideration:** if `enabled=false` means a `Channel` does not need an `endpoint`, `@NotNull URI endpoint` here is too strict. In that case, use conditional validation based on `enabled` or split config types. `@Valid` cannot infer business rules like "required only when enabled."

## 24. Conditional Validation Across Fields

Suppose a `Channel` can be disabled:

~~~yaml
notification:
  channels:
    webhook:
      enabled: false
~~~

If the contract states "endpoint is required only when the channel is enabled," class-level/cross-field validation is the right fit.

A simple approach for this example:

~~~java
import jakarta.validation.constraints.AssertTrue;
import java.net.URI;

public record Channel(
        boolean enabled,
        URI endpoint
) {
    @AssertTrue(message = "endpoint is required when enabled")
    public boolean isEndpointPresentWhenEnabled() {
        return !enabled || endpoint != null;
    }
}
~~~

For that method to run, the root configuration-properties bean must have validation enabled and `@Valid` must cascade into `Channel` as shown earlier. This illustrates a two-field dependency; in larger applications, you can use a custom class-level constraint to check multiple conditions and report errors on specific fields.

When an endpoint is provided, continue validating its scheme/host and security rules. A syntactically valid URI does not prove the address is safe or authorized to call.

## 25. Cross-Element Rules: Unique Names

Standard Bean Validation does not automatically require every `List<Endpoint>` to have unique names. `@NotEmpty`, `@Valid`, and `@NotBlank` inspect each value individually, not cross-element invariants.

Example:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://one.example.invalid"
    - name: "primary"
      url: "https://two.example.invalid"
~~~

Both entries have non-blank names and non-null URLs, yet violate a uniqueness requirement.

You can add a post-binding check in a factory or dedicated validator:

~~~java
import java.util.HashSet;
import java.util.Set;

Set<String> names = new HashSet<>();
for (RoutingProperties.Endpoint endpoint : properties.endpoints()) {
    if (!names.add(endpoint.name())) {
        throw new IllegalStateException(
            "Duplicate endpoint name: " + endpoint.name());
    }
}
~~~

This snippet assumes each endpoint is non-null and `name` has been validated; otherwise guard against nulls first. For complex configuration contracts, build a class-level custom constraint instead of scattering checks across services.

Similarly, if a `Map` holds endpoint names as keys and a `List` specifies call order, verify that every name in the `List` exists in the `Map` and contains no disallowed duplicates.

## 26. Distinguishing Empty, Null, and Missing

In externalized configuration:

~~~yaml
app:
  tags: []
~~~

differs from omitting `app.tags` in every source. Post-binding results depend on the Java model, constructor defaults, providers, and higher-precedence sources.

Cases:

| Bound Data | `@NotNull` | `@NotEmpty` | `@Size(min=2)` |
| --- | --- | --- | --- |
| `null` | Violated | Violated | Usually allowed if `@Size` alone |
| `[]` | Passes | Violated | Violated |
| `["a"]` | Passes | Passes | Violated |
| `["a","b"]` | Passes | Passes | Passes |

For `Map`, `{}` is an empty map if the Binder constructs it. `@NotEmpty` rejects an empty map, whereas `@NotNull` permits it.

If an entire configuration can legitimately be omitted, do not put unconditional `@NotEmpty` on every field. If required in production, express that requirement per deployment/validation contract.

Never use JSON `null` in `SPRING_APPLICATION_JSON` as a way to delete properties from lower-precedence sources; it has no "tombstone" semantics.

## 27. `DefaultValue` and Validation in Collections

With Spring Boot 3.x constructor binding, `@DefaultValue` can be placed on constructor parameters/record components:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;
import jakarta.validation.constraints.Min;

public record Endpoint(
        String name,
        @DefaultValue("3")
        @Min(1)
        int maxRetries
) {}
~~~

If an element is present without `max-retries`, the Binder uses default `3` and Bean Validation validates it. However:

- `@DefaultValue` does not turn `List` replacement between profiles into a merge.
- If `max-retries: "many"`, defaults do not bypass conversion errors.
- If `max-retries: 0`, `@Min(1)` still rejects it.
- Defaults must be safe across all applicable environments and should not mask settings that deployment must supply.

If the root `List` is missing entirely, element-level defaults cannot synthesize concrete entries the app never defined. Handle root defaults/absence or source configuration properly.

## 28. Testing the Binding + Validation Path Instead of Only Calling `Validator` Manually

Testing with:

~~~java
Validator validator =
    Validation.buildDefaultValidatorFactory().getValidator();

var violations = validator.validate(someObject);
~~~

is useful for verifying pure Jakarta Bean Validation constraints. However, it does not test:

- Spring Boot loading YAML and profiles.
- The Binder resolving configuration keys.
- Converting values into Java types.
- Registering `@ConfigurationProperties` beans.
- Executing validation in the startup lifecycle.

To verify integration, include **Spring Boot context tests** using realistic or deployment-like property values.

Context test example with `ApplicationContextRunner` (requiring matching test dependencies):

~~~java
package example.connectors;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConnectorsPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    ValidationAutoConfiguration.class
                ))
            .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsValidMapEntries() {
        runner.withPropertyValues(
            "connectors.clients.billing.base-url=https://billing.example.invalid",
            "connectors.clients.billing.timeout=3s",
            "connectors.clients.billing.pool-size=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            var props = context.getBean(ConnectorsProperties.class);
            assertThat(props.clients()).containsKey("billing");
            assertThat(props.clients().get("billing").poolSize())
                .isEqualTo(4);
        });
    }

    @Test
    void rejectsInvalidMapValue() {
        runner.withPropertyValues(
            "connectors.clients.billing.base-url=https://billing.example.invalid",
            "connectors.clients.billing.timeout=3s",
            "connectors.clients.billing.pool-size=0"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ConnectorsProperties.class)
    static class TestConfiguration {}
}
~~~

This test assumes `ConnectorsProperties` from the `Map` example is defined and a compatible validator is on the classpath. `hasNotFailed()` works in modern AssertJ-backed Boot test assertions; if an older test library lacks that method, assert `context.getStartupFailure()` is null per your available API.

Notice the key takeaway: the valid test initializes the bean; the `@Min(1)` violation test makes the context fail. This exercises registration, Binder, and validation together.

## 29. Directly Testing Container-Element Validation Principles

A Jakarta Bean Validation unit test can isolate `List` elements:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class LabelValidationTest {

    record Labels(
        @NotEmpty List<@NotBlank String> values
    ) {}

    @Test
    void rejectsBlankListElement() {
        try (var factory =
                 Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Labels sample = new Labels(
                List.of("audit", " "));

            assertThat(validator.validate(sample))
                .isNotEmpty();
        }
    }
}
~~~

This test needs no Spring `ApplicationContext`. It proves `@NotEmpty` on `List` and `@NotBlank` on elements are two separate checks. Still, to be sure `@ConfigurationProperties` beans are validated at startup, keep matching integration tests.

If using custom constraints, register validator implementations and ensure the provider detects the annotations and `ValueExtractor`s. That belongs to the Bean Validation layer, not Spring Boot config file syntax.

## 30. Common Mistake: Adding `@Valid` Without Constraints

Example:

~~~java
public record Target(String name, URI url) {}
~~~

And:

~~~java
List<@Valid Target> targets
~~~

The validator cascades into each `Target`, yet has no idea `name` or `url` is required because `Target` defines no constraints. You need:

~~~java
public record Target(
        @NotBlank String name,
        @NotNull URI url
) {}
~~~

Similarly, `Map<String, @Valid Settings>` only helps when `Settings` itself carries constraints or nested constraints to evaluate.

## 31. Common Mistake: Validating the Collection While Forgetting Items

~~~java
@NotEmpty List<Endpoint> endpoints
~~~

Requires the `List` to have at least one element; does not automatically check `Endpoint` fields. You need:

~~~java
@NotEmpty List<@NotNull @Valid Endpoint> endpoints
~~~

along with constraints inside `Endpoint`.

## 32. Common Mistake: Numeric Constraint Without `@NotNull`

~~~java
List<@Min(1) Integer> limits
~~~

In Bean Validation, null is normally considered valid by `@Min`. If nulls are forbidden:

~~~java
List<@NotNull @Min(1) Integer> limits
~~~

Use `Integer` when you need to detect absence, paired with an explicit contract. If using primitive `int` in a record, missing values can default to `0`, which `@Min(1)` catches.

## 33. Common Mistake: Confusing `Map` Structure with `List` Structure

A `Map` keyed by name:

~~~yaml
clients:
  definitions:
    billing:
      max-connections: 5
~~~

differs from a `List`:

~~~yaml
clients:
  definitions:
    - name: "billing"
      max-connections: 5
~~~

If the Java target is `Map<String, Client>`, use a YAML mapping keyed by name. If the Java target is `List<Client>`, use a YAML sequence. Never tweak validation annotations to fix a YAML structural mismatch with the target type.

## 34. Common Mistake: `Map` Entry Valid by Fields Yet Invalid by Key Name

A map key `"legacy-prod"` satisfies `@NotBlank` yet might not be supported by the application. When keys belong to a controlled set, use `@Pattern`, enum/naming policies, or a membership validator—not `@NotBlank` alone.

If valid keys must come from a fixed set such as `billing` and `inventory`, validate `keySet()` after binding or write a custom constraint. That is an application rule, not a built-in collection constraint.

## 35. Common Mistake: `@Valid` with a Null Nested Object

~~~java
public record AppProperties(
        @Valid Client client
) {}
~~~

If `client=null`, cascading skips the null value. If `client` is required:

~~~java
public record AppProperties(
        @NotNull @Valid Client client
) {}
~~~

The same applies to `Map` values and `List` elements. Remember `@Valid` means **traverse inside**, whereas `@NotNull` means **must exist**.

## 36. Implementation Checklist

Before shipping a `@ConfigurationProperties` bean containing collections or `Map`s:

1. Does the root class have `@ConfigurationProperties`, `@Validated`, and proper bean registration?
2. Is a Bean Validation provider compatible with your Spring Boot version included?
3. Must the collection exist and be non-empty? Choose `@NotNull`/`@NotEmpty`/`@Size` accordingly.
4. Are elements `String` or numbers? Place constraints directly on container element types.
5. Are elements objects? Use `@Valid` to cascade and put constraints on inner fields.
6. Must null elements be forbidden? Add `@NotNull` on the type argument.
7. Do `Map` keys have naming rules? Put constraints on the key type and check post-binding keys.
8. Do `Map` values have rules? Put constraints directly on the value type or `@Valid` into value objects.
9. Are collections nested inside `Map`s or records? Check every nesting boundary.
10. Does a profile replace a `List`? Verify the entire effective list rather than assuming index-based merging.
11. Does a `Map` inherit fields from a lower-precedence source? Confirm that inheritance is intended.
12. Do all chosen constraints support the exact Java types used?
13. Are there cross-element rules like uniqueness or ordering? Build a dedicated validator.
14. Is logic conditional on an `enabled` flag? Use conditional/cross-field validation appropriately.
15. Are there startup tests for missing, empty, wrong-type, and constraint-violating values?
16. Are secrets kept out of diagnostic error logs?

## 37. Capstone Exercise

Given the configuration:

~~~yaml
dispatch:
  recipients:
    - "ops@example.invalid"
    - ""
  routes:
    urgent:
      destination: "https://urgent.example.invalid"
      max-attempts: 3
    ordinary:
      destination: "https://ordinary.example.invalid"
      max-attempts: 0
~~~

Requirements:

- At least one recipient.
- No blank recipients.
- `routes` `Map` is non-empty.
- Every route key is non-blank.
- Every route value is non-null.
- Every route destination is non-null.
- Retry count is at least 1.

A model:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "dispatch")
public record DispatchProperties(
        @NotEmpty
        List<@NotBlank @Email String> recipients,

        @NotEmpty
        Map<@NotBlank String, @NotNull @Valid Route> routes
) {
    public record Route(
            @NotNull URI destination,
            @Min(1) int maxAttempts
    ) {}
}
~~~

Predictions:

1. The second recipient is `""`, violating `@NotBlank`.
2. The `Map` has two entries, so `@NotEmpty` passes.
3. Both route keys are non-blank, so key constraints pass.
4. Route `ordinary` has `maxAttempts=0`, violating `@Min(1)`.
5. All `URI`s are non-null, passing `@NotNull`; any HTTPS scheme/host check would need additional validation.

Fixed YAML:

~~~yaml
dispatch:
  recipients:
    - "ops@example.invalid"
    - "audit@example.invalid"
  routes:
    urgent:
      destination: "https://urgent.example.invalid"
      max-attempts: 3
    ordinary:
      destination: "https://ordinary.example.invalid"
      max-attempts: 2
~~~

With the validation dependency and proper registration, this configuration satisfies all defined constraints.

## 38. Conclusion

When binding collections and `Map`s in Spring Boot:

- `@NotNull`, `@NotEmpty`, and `@Size` on a container check **container presence and size**, not every element inside.
- Container-element constraints like `List<@NotBlank String>`, `List<@Min(1) Integer>`, and `Map<String, @NotBlank String>` validate **values at each position**.
- `@Valid` on an element or value type like `List<@Valid Endpoint>` or `Map<String, @Valid Client>` triggers **cascaded validation** into nested objects, provided those objects define constraints.
- To forbid null elements, combine `@NotNull` with `@Valid`; `@Valid` alone does not treat null as a violation.
- When profiles replace `List`s or `Map`s merge keys across sources, validation evaluates the **effective post-binding configuration**, not individual YAML files in isolation.
- Conversion errors, YAML syntax errors, registration errors, and constraint violations are separate categories; diagnose at the right layer.

**Remember:** to keep configuration safe, place constraints at the **right layer**: root collection, elements, `Map` keys, `Map` values, and nested objects. `@Validated` + `@Valid` + container-element constraints form the core toolkit for catching invalid data before your application begins processing business requests.