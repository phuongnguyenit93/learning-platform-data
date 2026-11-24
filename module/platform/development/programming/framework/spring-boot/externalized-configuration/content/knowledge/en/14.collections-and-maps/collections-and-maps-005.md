# How Profiles Affect Lists and Elements with Missing Properties

In Spring Boot Externalized Configuration, profiles let you selectively load environment-specific configuration: `application-dev.yml`, `application-prod.yml`, or a YAML document activated by `spring.config.activate.on-profile`. A common pitfall is that **lists (`List`) are not merged element-by-element across configuration sources**. If a higher-priority profile redeclares a list, that list can replace the entire list from the lower-priority source. When an element in the new list omits a property, Spring Boot does not automatically copy that property from the element with the same index or same name in the old list.

This differs from **`Map`**: when binding a Map, keys and nested properties can be combined from multiple property sources by precedence. Understanding this distinction helps avoid subtle bugs such as dropped elements, missing timeouts, booleans defaulting to `false`, or beans initializing with `null` values.

## 1. Three Layers to Distinguish

Spring Boot performs related but distinct steps:

1. **Loading configuration sources:** common `application`, profile documents, Config Data imports, environment variables, and command line.
2. **Determining precedence:** which source wins when the same property key appears in multiple places.
3. **Binding into Java types:** scalars, Lists, Maps, and nested objects follow different combination rules.

For a scalar:

~~~yaml
# application.yml
client:
  timeout: 3s
~~~

~~~yaml
# application-dev.yml
client:
  timeout: 1s
~~~

When `dev` is active and no higher-priority source overrides it, the effective timeout is 1 second. You cannot extrapolate from this that the same "override one field, keep the others" rule applies to each element of a List.

Initial mental model table:

| Target Java type to bind | Typical precedence behavior |
| --- | --- |
| `String`, `int`, `Duration` | Value from the winning priority source |
| `List<T>` | List from the winning priority source replaces the List in the lower source |
| `Map<String, T>` | Map keys can be combined; child fields resolve by priority |
| Nested object in a Map | Can gather fields from multiple sources |
| Nested object in an overridden List | Does not automatically inherit fields from the lower-source List element |

## 2. Basic Example: List in `application.yml`

Suppose an application configures two backends:

~~~yaml
# application.yml
routing:
  backends:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
      enabled: true
    - name: "secondary"
      url: "https://secondary.example.invalid"
      timeout: 7s
      enabled: true
~~~

Typed configuration:

~~~java
package example.routing;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<Backend> backends) {

    public record Backend(
            String name,
            URI url,
            Duration timeout,
            boolean enabled
    ) {}
}
~~~

Register the properties type:

~~~java
package example.routing;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
class RoutingConfiguration {
}
~~~

When there is no overriding source, `RoutingProperties.backends()` receives two elements in declared order. Each element has all four properties.

| Index | name | timeout | enabled |
| --- | --- | --- | --- |
| 0 | primary | 3 seconds | true |
| 1 | secondary | 7 seconds | true |

## 3. Profile Specifies One Element: The List Is Replaced Whole

A developer wants to change the `primary` URL when running locally and writes:

~~~yaml
# application-dev.yml
routing:
  backends:
    - name: "primary"
      url: "http://localhost:9080"
~~~

Run with:

~~~bash
java -jar routing-app.jar --spring.profiles.active=dev
~~~

A **wrong** assumption is that the `primary` element still keeps `timeout=3s` and `enabled=true` from the common file, and `secondary` stays intact.

In reality, under Spring Boot's List binding rules when the `dev` profile wins for `routing.backends`:

~~~text
backends.size() = 1

backends[0]:
  name    = "primary"
  url     = http://localhost:9080
  timeout = null if there is no other default
  enabled = false if using primitive boolean with no other default

backends[1]: no longer in the effective list
~~~

This is **replacement**, not "patching by index". The `dev` source is used to bind the list, without pulling child values of the list from the common file to fill in missing pieces.

If consuming code immediately uses the `timeout` field:

~~~java
long timeoutMillis =
    properties.backends().get(0).timeout().toMillis();
~~~

it can throw a `NullPointerException` because `timeout` is missing. If the application has proper validation, the error can surface at startup, which is usually better behavior.

## 4. Matching `name` or `id` Does Not Make a List Merge Automatically

For example:

~~~yaml
# application.yml
workers:
  entries:
    - id: "invoice"
      threads: 4
      queue-size: 100
    - id: "email"
      threads: 2
      queue-size: 50
~~~

~~~yaml
# application-staging.yml
workers:
  entries:
    - id: "invoice"
      threads: 1
~~~

There is no default rule in the Binder treating elements with `id=invoice` across two sources as the same object to merge. `id` is simply an application-defined field. When the staging list wins, the result typically has only one `invoice` entry; `queue-size` does not automatically take `100` from base, and the `email` entry disappears.

Likewise, using the same index `[0]` in two sources does **not** define element identity. A List has positional semantics, not a primary-key record update mechanism.

## 5. Two Types of Missing Data to Separate

**Case A: an entire element is missing.**

~~~yaml
# common
jobs:
  entries:
    - name: "validate"
    - name: "enrich"
    - name: "publish"
~~~

~~~yaml
# profile
jobs:
  entries:
    - name: "validate"
~~~

The profile list has only `validate`. The two elements `enrich` and `publish` are not automatically retained.

**Case B: the element is present, but properties are missing.**

~~~yaml
# common
jobs:
  entries:
    - name: "validate"
      timeout: 2s
      enabled: true
~~~

~~~yaml
# profile
jobs:
  entries:
    - name: "validate"
~~~

The `validate` element is still present, but `timeout` and `enabled` are **not automatically inherited** from the element in the lower source. The result depends on the Java types, defaults, constructors, setters, and validation.

| Missing field | Java type | Typical value if no other default |
| --- | --- | --- |
| `timeout` | `Duration` | `null` |
| `enabled` | `boolean` | `false` |
| `retryCount` | `Integer` | `null` |
| `name` | `String` | `null` |

Do not just check the List size. You must also check all required fields on each element.

## 6. Multi-Document YAML with `on-profile` Follows the Same Rule

Two separate files are not required. Documents can be separated inside `application.yml`:

~~~yaml
app:
  processors:
    - name: "alpha"
      timeout: 4s
      description: "Base Alpha"
    - name: "beta"
      timeout: 6s
      description: "Base Beta"

---
spring:
  config:
    activate:
      on-profile: "dev"

app:
  processors:
    - name: "alpha-dev"
~~~

When `dev` is active and the dev document wins for the list, `app.processors` contains only one element, `name=alpha-dev`; `timeout` and `description` are not automatically pulled from the first element of the common document.

`spring.config.activate.on-profile` only determines which documents are activated. It **does not enable deep merging for Lists**.

Similarly, configuration files imported via `spring.config.import` can form a higher-priority source and replace another source's List. The `optional:` prefix on an import only permits a missing location; it does not mean Lists inside are merged.

## 7. Comparison with Map: Key-Based Combination

Change the backend configuration from a sequence to a map:

~~~yaml
# application.yml
routing:
  backends:
    primary:
      url: "https://primary.example.invalid"
      timeout: 3s
      enabled: true
    secondary:
      url: "https://secondary.example.invalid"
      timeout: 7s
      enabled: true
~~~

Java:

~~~java
package example.routing;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        Map<String, Backend> backends
) {
    public record Backend(
            URI url,
            Duration timeout,
            boolean enabled
    ) {}
}
~~~

The `dev` profile only needs:

~~~yaml
# application-dev.yml
routing:
  backends:
    primary:
      url: "http://localhost:9080"
~~~

Map binding can combine keys from multiple sources. Typical result:

~~~text
backends["primary"]:
  url     = http://localhost:9080     # dev
  timeout = 3s                        # base
  enabled = true                      # base

backends["secondary"]:
  url     = https://secondary.example.invalid
  timeout = 7s
  enabled = true
~~~

Child fields of a Map entry have **explicit property names** such as `routing.backends.primary.timeout`, so they can be resolved across property sources.

This is the right behavior when you need to override one backend by ID without repeating the entire list.

## 8. List vs. Map Comparison Table

| Criterion | `List<Backend>` | `Map<String, Backend>` |
| --- | --- | --- |
| Entry identifier | Position `0,1,2...` | Keys such as `primary` |
| Profile override | New List replaces old List | Map keys and fields can be combined |
| Changing one URL | Redeclare the complete List or redesign | Override the field under the corresponding key |
| Entry unmentioned in new profile | Not preserved automatically when List replaces | Can remain from lower source |
| Missing field on an element | Not pulled from element in lower List | Can be pulled from lower Map entry |
| Ordering significance | Yes | Should not treat Map iteration order as business logic |
| Best suited for | Ordered pipelines, lists meant to be replaced wholesale | ID-keyed catalogs, named clients and integrations |

**Map is not a universal deep merge at every level.** If a Map holds a List-typed field and a profile overrides that List field, the List layer still obeys replacement rules.

## 9. A List Nested Inside a Map Does Not Concatenate Either

Common configuration:

~~~yaml
clients:
  pricing:
    timeout: 3s
    retry-codes:
      - 429
      - 503
~~~

Dev profile:

~~~yaml
clients:
  pricing:
    timeout: 1s
    retry-codes:
      - 500
~~~

If the typed properties use `Map<String, Client>`, the `pricing` entry's `timeout` can change to 1 second, while `retry-codes` is a List: the result may contain only code `500`, without concatenating `429` and `503`.

When examining a complex structure, you must evaluate the **Java type at each level**, not just whether the root is a Map or a List.

## 10. Safe Approach 1: Declare the Full List per Profile

If the list truly needs ordering and each environment has a clear sequence, declare **all required elements and fields** in the profile file.

~~~yaml
# application.yml
pipeline:
  stages:
    - name: "validate"
      timeout: 2s
      enabled: true
    - name: "publish"
      timeout: 10s
      enabled: true
~~~

~~~yaml
# application-dev.yml
pipeline:
  stages:
    - name: "validate"
      timeout: 1s
      enabled: true
    - name: "publish"
      timeout: 10s
      enabled: true
~~~

Here `dev` defines an effective list with two complete stages. Nothing has to be guessed about index-based inheritance.

Pros: easy to read the exact sequence; fits pipelines or destination lists where a profile intentionally replaces the entire set.

Cons: configuration duplication; when adding a new stage to base, you must remember to update profile files. Add integration tests/validation to detect unintended divergence.

## 11. Safe Approach 2: Use a Map with Stable Keys

If the requirement is "edit a few properties of an element identified by name", a Map expresses that contract better:

~~~yaml
# application.yml
integrations:
  clients:
    inventory:
      base-url: "https://inventory.example.invalid"
      timeout: 3s
      max-retries: 2
    pricing:
      base-url: "https://pricing.example.invalid"
      timeout: 5s
      max-retries: 3
~~~

Dev changes only one URL:

~~~yaml
# application-dev.yml
integrations:
  clients:
    pricing:
      base-url: "http://localhost:9090"
~~~

When binding a Map as before, other keys and fields are combined by precedence without copying the entire client list. This is a useful pattern for configuration catalogs, service endpoints, and ID-based definitions.

However, if the application must call `inventory` before `pricing`, do not rely on Map iteration order; model the order separately.

## 12. Hybrid Approach: `definitions` Map and `execution-order` List

When you need both override-by-ID and explicit ordering:

~~~yaml
# application.yml
pipeline:
  definitions:
    validate:
      timeout: 2s
      enabled: true
    enrich:
      timeout: 5s
      enabled: true
    publish:
      timeout: 10s
      enabled: true
  execution-order:
    - "validate"
    - "enrich"
    - "publish"
~~~

Dev file:

~~~yaml
pipeline:
  definitions:
    enrich:
      timeout: 1s
~~~

Java:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pipeline")
public record PipelineProperties(
        Map<String, Stage> definitions,
        List<String> executionOrder
) {
    public record Stage(Duration timeout, boolean enabled) {}
}
~~~

When `dev` is active, `definitions.enrich.timeout` can become `1s` while `definitions.validate` and `publish` are preserved. `execution-order` comes from the common file unless the profile declares a new List.

Consuming code must verify that every stage name in `executionOrder` exists in `definitions`:

~~~java
for (String name : properties.executionOrder()) {
    if (!properties.definitions().containsKey(name)) {
        throw new IllegalStateException(
            "Unknown stage in execution order: " + name);
    }
}
~~~

This is application business validation, not an automatic check performed by Spring Boot.

## 13. Alternative: Move Shared Properties Outside the List

If many elements share the same timeout or retry count, extract defaults into a top-level object:

~~~yaml
# application.yml
remote:
  defaults:
    timeout: 3s
    max-retries: 2
  targets:
    - name: "inventory"
      url: "https://inventory.example.invalid"
    - name: "pricing"
      url: "https://pricing.example.invalid"
~~~

Dev:

~~~yaml
remote:
  defaults:
    timeout: 1s
  targets:
    - name: "inventory"
      url: "http://localhost:9091"
    - name: "pricing"
      url: "http://localhost:9092"
~~~

Java type:

~~~java
@ConfigurationProperties(prefix = "remote")
public record RemoteProperties(
        Defaults defaults,
        java.util.List<Target> targets
) {
    public record Defaults(
            java.time.Duration timeout,
            int maxRetries
    ) {}
    public record Target(String name, java.net.URI url) {}
}
~~~

The application applies `defaults.timeout()` to targets. That way the list avoids repeating the timeout field; when a profile replaces the list, it is less likely to drop shared settings.

**Note:** applying `defaults` to each target is application-defined logic, not automatic per-element inheritance by Spring Boot.

## 14. `@DefaultValue` Helps with Missing Fields but Does Not Merge Profiles

In Spring Boot 3.x, constructor-bound typed properties can use `@DefaultValue`:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(List<Backend> backends) {

    public record Backend(
            String name,
            URI url,
            @DefaultValue("3s") Duration timeout,
            @DefaultValue("true") boolean enabled
    ) {}
}
~~~

With the profile's new list:

~~~yaml
routing:
  backends:
    - name: "local"
      url: "http://localhost:9080"
~~~

`timeout` and `enabled` can receive the defaults declared on the constructor. But those are **Java-level defaults**, not copies of `timeout` or `enabled` from the same-index element in the common file.

If the profile file has `timeout: "later"` while Java expects `Duration`, defaults do not act as a fallback to ignore invalid types. Fix the configuration or add a converter.

Never use defaults merely to mask a required production setting that is missing.

## 15. Validation for List Elements

When an important field is missing, failing fast at startup is usually much better than letting a bean receive `null` and fail later.

~~~java
package example.routing;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty @Valid List<Backend> backends
) {
    public record Backend(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {}
}
~~~

If the winning profile defines:

~~~yaml
routing:
  backends:
    - name: "local"
      url: "http://localhost:9080"
~~~

then `timeout` is not supplied. With a proper Bean Validation dependency (typically `spring-boot-starter-validation`) and `RoutingProperties` registered, `@NotNull` can fail context startup immediately during binding/validation.

Distinguish clearly:

- **List replacement:** selects which list configuration takes effect.
- **Binding/conversion:** constructs Java objects and converts each field's type.
- **Validation:** verifies objects satisfy the configuration contract.

`@NotNull Duration timeout` does not ensure timeout is greater than zero; add a constraint or custom check if needed. Successful `URI` conversion also does not ensure the endpoint is reachable.

## 16. Scalar Lists Are Also Replaced

This behavior is not limited to Lists of objects:

~~~yaml
# application.yml
security:
  allowed-hosts:
    - "internal.example.invalid"
    - "partner.example.invalid"
~~~

~~~yaml
# application-dev.yml
security:
  allowed-hosts:
    - "localhost"
~~~

When `dev` wins for the list, the result can be just `["localhost"]`. Spring Boot does not automatically append `localhost` to the two hosts from base.

For allowlists, denylists, CORS origins, routing targets, or topic subscriptions, replacing a List can affect operations and security. This is not a YAML formatting quirk; it is the **binding semantics of externalized configuration**.

If the goal is truly to swap the entire host set in `dev`, replacement is appropriate. If you want to keep the common list and add an entry, design an explicit combination mechanism rather than assuming profiles append.

## 17. Multiple Profiles Active at Once

Spring Boot supports:

~~~bash
java -jar app.jar --spring.profiles.active=staging,metrics
~~~

Two files:

~~~yaml
# application-staging.yml
app:
  collectors:
    - "staging-request"
    - "staging-error"
~~~

~~~yaml
# application-metrics.yml
app:
  collectors:
    - "jvm"
    - "http"
~~~

When both are active, the list does not become four elements. For profile sources at the same precedence level, **the later profile can win** when configuration is loaded, so the effective list can become `["jvm","http"]`. The final value also depends on Config Data imports and higher-priority sources such as the command line.

A dangerous habit is enabling two conflicting profiles together and relying on accidental order to get a desired list. Better practices:

- Define which profile owns each collection.
- Avoid letting a monitoring profile overwrite a business list in staging.
- Use explicit configuration for lists that genuinely need replacement.
- Verify bound results with tests for your actual deployment profile combination.

## 18. Overriding Lists via Environment Variables

For indexed lists, Spring Boot supports mapping from environment variables via relaxed binding. A key like:

~~~text
routing.backends[0].url
~~~

can correspond to an environment variable named:

~~~text
ROUTING_BACKENDS_0_URL
~~~

If a higher-priority environment variable source supplies only the URL for element 0, do not assume `name`, `timeout`, and element 1 will automatically merge in from lower-priority YAML. Because of list replacement, overriding individual items across environment variables can leave missing fields or replace the entire list.

A safer approach when a list has multiple fields is a complete profile-specific file, or switching to a Map if you want overrides by stable key. Always verify which variable names the Binder actually accepts on your deployed Spring Boot version.

## 19. Testing with a Real Profile

You can create test resources:

~~~yaml
# src/test/resources/application.yml
demo:
  endpoints:
    - name: "base"
      description: "From base"
      timeout: 3s
    - name: "second"
      description: "Second endpoint"
      timeout: 5s
~~~

~~~yaml
# src/test/resources/application-dev.yml
demo:
  endpoints:
    - name: "dev"
~~~

Properties record:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(List<Endpoint> endpoints) {
    public record Endpoint(
            String name,
            String description,
            Duration timeout
    ) {}
}
~~~

Register `DemoProperties` via `@EnableConfigurationProperties` or scanning in the application context.

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class ListProfileBindingTest {

    @Autowired
    DemoProperties properties;

    @Test
    void devListReplacesBaseList() {
        assertThat(properties.endpoints()).hasSize(1);

        DemoProperties.Endpoint entry =
            properties.endpoints().get(0);

        assertThat(entry.name()).isEqualTo("dev");
        assertThat(entry.description()).isNull();
        assertThat(entry.timeout()).isNull();
    }
}
~~~

This test only illustrates a context with registration and no other defaults or validators; if you add `@NotNull`, the context can fail early rather than creating a bean with a null timeout. That is a different outcome, though it also demonstrates the consequence of missing fields.

Tests should not merely call `new DemoProperties(...)`, because that bypasses the Spring Binder and proves nothing about how property sources are resolved.

## 20. Contrasting with Map in Tests

Change the model to:

~~~yaml
# application.yml
demo:
  endpoints:
    alpha:
      description: "From base"
      timeout: 3s
    beta:
      description: "Second endpoint"
      timeout: 5s
~~~

~~~yaml
# application-dev.yml
demo:
  endpoints:
    alpha:
      description: "From dev"
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        java.util.Map<String, Endpoint> endpoints
) {
    public record Endpoint(
            String description,
            java.time.Duration timeout
    ) {}
}
~~~

When `dev` is active, the map can preserve both `alpha` and `beta`. `alpha.description` comes from `dev` and `alpha.timeout` comes from `base`; `beta` comes from `base`.

The test should verify:

~~~java
assertThat(properties.endpoints())
    .containsKeys("alpha", "beta");

assertThat(properties.endpoints().get("alpha").description())
    .isEqualTo("From dev");

assertThat(properties.endpoints().get("alpha").timeout())
    .isEqualTo(java.time.Duration.ofSeconds(3));
~~~

This expresses the intent of overriding a field of a named entry much better than a list.

## 21. Common Mistakes

**Mistake 1 — Assuming Lists merge by index.** The `dev` file defines only element 0, yet the author expects element 1 from the base file to stay intact. You must define the full list for replacement, or use a Map for merging by name.

**Mistake 2 — Thinking an `id` field acts as a merge key.** Spring Boot does not match or join elements based on `name`/`id`. Those fields are purely application data.

**Mistake 3 — Skipping validation on nested item fields.** Missing `timeout`, `url`, or `enabled` can lead to unexpected nulls/defaults. Use `@Valid` and constraints, or meaningful defaults.

**Mistake 4 — Creating too many profiles just to patch a list.** For instance `dev-with-backend-a`, `dev-with-backend-b`, `prod-with-both`. Revisit using a Map model and normal properties before multiplying profiles.

**Mistake 5 — Thinking Map merge means nested lists merge too.** If a Map entry contains `List<String> retryCodes`, that field still undergoes list replacement.

**Mistake 6 — Using Optional Config Data Import and expecting partial merge.** `optional:` only allows the import location to be missing. Lists inside an imported file still obey Binder rules.

**Mistake 7 — Confusing missing fields with a parser error.** Completely valid YAML can still bind into an object with missing fields. If a property is required, validation must enforce that requirement.

**Mistake 8 — Failing to confirm the winning source.** When multiple profiles, environment variables, and command-line arguments interact, the effective value may not come from the file the developer is looking at.

## 22. Diagnostic Workflow When a List Has Missing Data

When you see fewer list elements than expected or an entry contains `null`:

1. Identify which profiles are active.
2. Find every source supplying **the same list prefix**, including common YAML, profile files, imports, environment variables, and CLI.
3. Determine the highest-priority source defining the list.
4. Inspect the **bound list size**, not just YAML files visually.
5. Check each element: index, name/ID, required fields, defaults, and validation.
6. Check for sparse indices or misformatted environment variable names.
7. If merging by ID is desired, evaluate whether a Map expresses the intent more clearly.
8. If ordering must be preserved, consider defining the full sequence in one source or separating a `definitions` Map + `order` List.
9. Add integration tests for real configuration/profile combinations.
10. Do not print secrets to logs or carelessly expose configuration Actuator endpoints.

Property inspection tools such as `Environment`, `@ConfigurationProperties`, and Actuator `/actuator/configprops` can be helpful when properly access-controlled, though the final source of truth is the bound value in the deployed application context.

## 23. Result Prediction Exercise

Common configuration:

~~~yaml
catalog:
  targets:
    - id: "alpha"
      base-url: "https://alpha.example.invalid"
      timeout: 4s
      enabled: true
    - id: "beta"
      base-url: "https://beta.example.invalid"
      timeout: 6s
      enabled: true
  providers:
    alpha:
      region: "apac"
      retries: 3
    beta:
      region: "eu"
      retries: 2
~~~

Staging profile:

~~~yaml
catalog:
  targets:
    - id: "alpha"
      base-url: "https://staging-alpha.example.invalid"
  providers:
    alpha:
      retries: 1
~~~

Binding:

~~~java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        java.util.List<Target> targets,
        java.util.Map<String, Provider> providers
) {
    public record Target(
            String id,
            java.net.URI baseUrl,
            java.time.Duration timeout,
            boolean enabled
    ) {}

    public record Provider(
            String region,
            int retries
    ) {}
}
~~~

Predict when `staging` is active and there is no higher-priority source:

| Question | Result |
| --- | --- |
| `targets.size()` | 1 |
| `targets[0].id` | alpha |
| `targets[0].baseUrl` | Staging URL |
| `targets[0].timeout` | Does not automatically take 4s; can be null |
| `targets[0].enabled` | Does not automatically take true; usually false |
| `targets[1]` | Does not exist |
| `providers["alpha"].region` | apac from base |
| `providers["alpha"].retries` | 1 from staging |
| `providers["beta"]` | Can remain from base |

This table shows clearly: **List replacement** is not the same as **Map merging**, even within the same configuration properties group.

## 24. Pre-Deployment Design Checklist

- Does the collection have business-significant ordering? If not, consider a Map.
- Is a profile file accidentally redeclaring a List just to edit one field?
- If a new List is declared, are all required elements listed?
- Does each element include every critical field?
- Are primitive defaults like `false` or `0` operationally safe?
- Are there explicit, meaningful default rules in code or via `@DefaultValue`?
- Is validation in place to fail fast when URLs, timeouts, names, or other constraints are missing?
- Can multiple profiles declare this list at the same time?
- Is there a list nested under a Map entry?
- Are there tests loading configuration with the exact profiles and property sources used in deployment?
- If both per-ID overrides and explicit order are needed, have you considered a `definitions` Map + `order` List?

## 25. Key Takeaways

**Spring Boot does not automatically deep-merge Lists across different configuration sources.** When a profile redefines a list in a higher-priority source, that list can replace the entire original list. New elements missing a field do not automatically inherit values from the same-index or same-name element in a lower-priority source. Consequences can include dropped elements, nulls, Java type defaults, or validation errors.

**Maps can combine keys and fields from multiple sources** according to precedence order. Use a Map when each entry has a stable identifier and individual fields often need overrides; use a List when sequence and order genuinely matter. For critical configuration, always verify bound values under real deployment profiles and check the completeness of every entry.
