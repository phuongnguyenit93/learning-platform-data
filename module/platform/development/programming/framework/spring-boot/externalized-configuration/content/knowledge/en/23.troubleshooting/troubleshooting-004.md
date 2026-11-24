# Using Actuator env to Find the Winning Source and configprops to Inspect Binding Results

## 1. Objective: Separate Configuration Source Issues from Binding Issues

When a Spring Boot application reads external configuration, multiple sources can declare the same key. For example, a development team edits `application.yml` to set `shipping.retry.max-attempts=3`, yet the running process still applies 7 retries. The deployment might be passing command-line arguments, a separate profile, an environment variable, or an external Config Data file. Or `Environment` chose the right value, yet the Java object did not bind as expected.

Spring Boot Actuator provides two complementary views:

- **`env`**: shows which `PropertySource`s exist in `Environment`, their precedence order, which source was selected for a property name, and origin metadata if available.
- **`configprops`**: shows which `@ConfigurationProperties` beans are managed, which prefix is bound, the `properties` state, and the `inputs` details of the binding process.

The two endpoints answer **two different questions**:

```text
1. Where does the effective property come from?
   -> GET /actuator/env/{property.name}

2. How did the configuration bean receive the binding result?
   -> GET /actuator/configprops/{prefix}
```

A complete diagnostic workflow:

```text
YAML / properties / profile / ENV / CLI / imports
                         |
                         v
                Environment
                         |
                         +-- /actuator/env/{key}
                         |    winning source / origin / profiles
                         |
                         v
         Binder + type conversion + validation
                         |
                         +-- /actuator/configprops/{prefix}
                         |    bean / properties / inputs
                         |
                         v
                Service uses bean
                         |
                         v
               Verify behavior
```

**Never draw conclusions from a single endpoint alone.** `env` proves the property resolver's view; `configprops` proves the bound bean's view; the service may still process the value with its own logic.

## 2. Master the Three Data Layers

### 2.1. A PropertySource Is an Independent Source

`PropertySource` belongs to Spring Framework. A source has a name and supplies values for the property names it manages. For example:

```text
application.yml:
  shipping.retry.max-attempts -> 3
  shipping.retry.backoff      -> 1s

application-prod.yml:
  shipping.retry.max-attempts -> 5

commandLineArgs:
  shipping.retry.max-attempts -> 7
```

A source does not need to contain every key. When querying `shipping.retry.backoff`, only `application.yml` can supply a value; when querying `shipping.retry.max-attempts`, multiple sources participate.

### 2.2. Environment Selects by Order

`ConfigurableEnvironment` holds an ordered list of `PropertySource`s. When resolving a standard property, the higher-precedence source supplying a value wins.

```text
commandLineArgs         max-attempts = 7
application-prod.yml    max-attempts = 5
application.yml         max-attempts = 3
                        ---------------
effective value                      7
```

This is an illustrative model of a specific process, **not a mandatory source-order list for every Boot release**. Actual sources and final order can depend on Config Data imports, additional config, web environment, custom PropertySources, and test contexts.

### 2.3. Binder Builds a Typed Object

Example record:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
```

Binder converts `"7"` to `int 7` and `"1s"` to `Duration.ofSeconds(1)`, then constructs the Java object. The value in the source file, the value resolved by `Environment`, and the value in the bean can **have different representations** while carrying the same meaning.

## 3. What Do the Two Endpoints Do?

| URL | Focus of data | Question |
| --- | --- | --- |
| `GET /actuator/env` | `Environment`, profiles, source list | Which sources exist? |
| `GET /actuator/env/{property.name}` | One key, effective source, competing sources | Who is winning for this key? |
| `GET /actuator/configprops` | `@ConfigurationProperties` beans | Which beans have been bound? |
| `GET /actuator/configprops/{prefix}` | Beans under matching prefix | What did objects under this group receive? |

The `/actuator` base path can be changed via `management.endpoints.web.base-path`. Management port can differ from the application port if configured separately. URLs in this lesson assume a lab app at `127.0.0.1:8080`.

Conditions to get a response:

1. Project includes `spring-boot-starter-actuator`.
2. Application has a web stack to serve HTTP endpoints.
3. Endpoint is enabled/accessible and exposed in the corresponding config.
4. Request passes authentication/authorization and network policies.
5. Process is running and the context started successfully.

If one condition is not met, you cannot conclude a property does not exist just because HTTP returns 404/401/403.

## 4. Preparing Dependencies and Actuator Configuration

With Maven where dependencies are managed by Spring Boot parent/BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Gradle Kotlin:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

In a lab environment using dummy data only:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
    jmx:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

**Do not use this exposure list as a production default.** Both diagnostic endpoints can reveal infrastructure metadata even when raw values are masked. In production, expose only required endpoints, with a management network, authentication/authorization, TLS, and auditing as required.

`management.endpoints.web.exposure.include` uses plural `endpoints`; `management.endpoint.env.show-values` and `management.endpoint.configprops.show-values` use singular `endpoint`. Mixing up singular/plural is a frequent configuration mistake.

## 5. Complete Hands-On Lab: Prepare Three Configuration Sources

Directory structure:

```text
shipping-config-lab/
  src/main/java/com/example/shipping/
    ShippingApplication.java
    ShippingProperties.java
    ShippingPlanService.java
  src/main/resources/
    application.yml
    application-prod.yml
  src/test/java/com/example/shipping/
    ShippingBindingTest.java
```

`application.yml`:

```yaml
shipping:
  enabled: true
  endpoint: https://shipping-default.example.invalid/api
  retry:
    max-attempts: 3
    backoff: 1s
```

`application-prod.yml`:

```yaml
shipping:
  endpoint: https://shipping-prod.example.invalid/api
  retry:
    max-attempts: 5
```

In the lab, JAR launch command:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --shipping.retry.max-attempts=7
```

`app.jar` is an illustrative name. URLs ending in `.invalid` are dummy data, not real services.

Prediction assuming no higher source exists:

| Property | Common file | Prod file | Command line | Effective |
| --- | --- | --- | --- | --- |
| `shipping.enabled` | true | Undeclared | Undeclared | true |
| `shipping.endpoint` | Default URL | Prod URL | Undeclared | Prod URL |
| `shipping.retry.max-attempts` | 3 | 5 | 7 | 7 |
| `shipping.retry.backoff` | 1s | Undeclared | Undeclared | 1s |

Now we have an example where `env` helps locate the winning source, while `configprops` lets us inspect the Java object receiving these values.

## 6. Create @ConfigurationProperties and Register the Bean

`ShippingProperties.java`:

```java
package com.example.shipping;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        URI endpoint,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
```

`ShippingApplication.java`:

```java
package com.example.shipping;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShippingApplication.class, args);
    }
}
```

`@EnableConfigurationProperties(ShippingProperties.class)` registers the record so Binder creates the bean. You can use `@ConfigurationPropertiesScan` in larger projects, though choose an explicit registration mechanism and verify scanned packages.

Binding steps:

```text
shipping.enabled             -> boolean enabled
shipping.endpoint            -> URI endpoint
shipping.retry.max-attempts  -> int Retry.maxAttempts
shipping.retry.backoff       -> Duration Retry.backoff
```

A notable pitfall: `@ConfigurationProperties` on a class **does not automatically make that class a bean** if the project has not registered it. Thus, `env` may show the key is right while `configprops` has no corresponding bean.

## 7. Business Bean Consuming Configuration

Create `ShippingPlanService.java`:

```java
package com.example.shipping;

import java.net.URI;
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class ShippingPlanService {

    private final ShippingProperties properties;

    public ShippingPlanService(ShippingProperties properties) {
        this.properties = properties;
    }

    public Plan currentPlan() {
        return new Plan(
            properties.enabled(),
            properties.endpoint(),
            properties.retry().maxAttempts(),
            properties.retry().backoff()
        );
    }

    public record Plan(
        boolean enabled,
        URI endpoint,
        int maxAttempts,
        Duration backoff
    ) {}
}
```

`currentPlan()` only constructs a descriptive value, sending no HTTP traffic. With the lab configuration and command line shown, the expected Java values are:

```text
enabled        = true
endpoint       = https://shipping-prod.example.invalid/api
maxAttempts    = 7
backoff        = PT1S
```

`PT1S` is Java `Duration`'s representation for one second. Compare typed values rather than demanding that the bound representation look textually identical to YAML.

## 8. Reading /actuator/env: Profiles and Source Order

Call from the test machine:

```bash
curl -i 'http://127.0.0.1:8080/actuator/env'
```

According to Spring Boot's REST API, the response can contain fields:

```text
activeProfiles
defaultProfiles
propertySources[]
  name
  properties
```

A shortened response for illustration:

```json
{
  "activeProfiles": ["prod"],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "commandLineArgs",
      "properties": {}
    },
    {
      "name": "systemProperties",
      "properties": {}
    },
    {
      "name": "systemEnvironment",
      "properties": {}
    }
  ]
}
```

**Do not treat the JSON above as a snapshot of a live Boot instance.** Entries are truncated; real applications have additional Config Data sources and many others. Exact names and order depend on version and deployment conditions.

What to observe:

1. Does `activeProfiles` contain `prod`?
2. Is `commandLineArgs` present when the process actually received CLI arguments?
3. Which Config Data sources were loaded?
4. Are there external file sources or `spring.config.import`?
5. Did a custom `EnvironmentPostProcessor` add a source?
6. `propertySources` is in **precedence order**, not alphabetical order.

When you only care about one key, do not fetch the entire Environment. Switch to `/actuator/env/{property.name}`.

## 9. Querying One Key: /actuator/env/{property.name}

Use the canonical name:

```bash
curl -i \
  'http://127.0.0.1:8080/actuator/env/shipping.retry.max-attempts'
```

Important fields per Actuator REST API documentation:

| JSON path | Meaning |
| --- | --- |
| `property.source` | Source supplying the effective property |
| `property.value` | Effective value if permitted to display; may be sanitized |
| `activeProfiles` | Currently active profiles |
| `defaultProfiles` | Default profiles |
| `propertySources[]` | Sources in precedence order |
| `propertySources[].name` | Name of each source |
| `propertySources[].property` | Property info within that source, if present |
| `propertySources[].property.origin` | Original location, if source has origin metadata |

Simulated example, shortened with values masked:

```json
{
  "activeProfiles": ["prod"],
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  },
  "propertySources": [
    {
      "name": "commandLineArgs",
      "property": {"value": "******"}
    },
    {
      "name": "Config resource 'application-prod.yml'",
      "property": {
        "value": "******",
        "origin": "application-prod.yml - source location"
      }
    },
    {
      "name": "Config resource 'application.yml'",
      "property": {
        "value": "******",
        "origin": "application.yml - source location"
      }
    }
  ]
}
```

Resource names and origins here are simplified, not strings the framework is required to return.

How to read it:

1. `property.source` points to `commandLineArgs`: that source is winning.
2. Sources from prod and common files can still exist below, without disappearing.
3. Value showing `******` does not prove the real value is six asterisks; that is masked data.
4. When origin is present, it helps identify the resource and line/column of the loaded file.
5. If you only need to know why a source wins, **you do not need to disable sanitization**.

### 9.1. Do Not Infer the Winning Source from the First Source in the Full List

The first source in the list might not contain the queried key. Use **`property.source`** at the top level of the single-key query response; the source list below is for inspecting competing sources, origins, and precedence.

### 9.2. A Source Listed by Name Without a Property Entry

A `propertySources[].name` entry only indicates the source exists in Environment. If the entry has no `property`, it does not mean that source contributed a value for the key. When multiple sources exist, do not count a source lacking the key as an "override."

## 10. Origin: Evidence of Which File the Value Came From

For Config Data loaded from files, Spring Boot can store origin, such as resource and line/column position:

```text
class path resource [application-prod.yml] - 5:19
```

Or an external file:

```text
file [/etc/myapp/application-prod.yml] - 5:19
```

These are **examples of origin style**, not real lab output.

Origin is especially useful when:

- External files outside the JAR are mounted in containers.
- Multiple `spring.config.location` or `spring.config.additional-location` entries exist.
- `spring.config.import` is used.
- Multiple YAML documents are activated by profile.
- Builds or deployments use different resource paths.

Not every PropertySource provides origin. For command-line/system environment, metadata can be sparser than a YAML file. **Lack of origin does not mean lack of value.**

A common diagnostic mistake is reading `src/main/resources/application.yml` in the repository while the running process uses a deployment-mounted file. `env` from the exact instance uncovers the actual loaded source.

## 11. Using configprops to Inspect Binding Results

Call:

```bash
curl -i 'http://127.0.0.1:8080/actuator/configprops/shipping'
```

REST API describes the structure:

```text
contexts
  -> <context-id>
     -> beans
        -> <bean-id>
           -> prefix
           -> properties
           -> inputs
```

Where:

- **`prefix`**: `@ConfigurationProperties` prefix.
- **`properties`**: represented fields/values of the bean.
- **`inputs`**: properties that participated in binding, potentially including origin and input value.
- **`contexts`**: distinguishes application contexts if multiple contexts exist.
- **`beans`**: keyed by bean name; never assume the bean name is always the lowercase class name.

**Illustrative, shortened** JSON example:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "shipping-com.example.shipping.ShippingProperties": {
          "prefix": "shipping",
          "properties": {
            "enabled": "******",
            "endpoint": "******",
            "retry": {
              "maxAttempts": "******",
              "backoff": "******"
            }
          },
          "inputs": {
            "retry": {
              "maxAttempts": {
                "value": "******"
              },
              "backoff": {
                "value": "******"
              }
            }
          }
        }
      }
    }
  }
}
```

**This is not an exact schema for every version and every object type.** A real response can represent nested objects, scalars, collections, origins, and sanitized values differently. This lesson focuses on field meanings rather than requiring identical bean names or mask lengths.

### 11.1. Comparing properties with inputs

A bean can have a property value without a matching input. Possible reasons:

- JavaBean field initializer supplied a default.
- Constructor binding used `@DefaultValue`.
- A getter computed the value.
- The property was not supplied from an external source.
- How the endpoint serializes or aggregates inputs does not reflect the expected path.

`properties` is the **bound object** view; `inputs` is the **inputs participating in binding** view. Do not equate them.

### 11.2. Prefix Filter Does Not Necessarily Match Only One Bean

`GET /actuator/configprops/shipping` can return all configuration-properties beans matching the prefix stem. In multi-module projects, check each bean's `prefix` and class name rather than grabbing the first entry and assuming it is the service in use.

## 12. Step-by-Step Two-Endpoint Diagnostic Workflow

When an incident reports "maxAttempts value is still wrong":

**Step 1 — Lock down the canonical property name.** From `@ConfigurationProperties(prefix="shipping")` and field `retry.maxAttempts`, determine the key `shipping.retry.max-attempts`. Do not guess from Java naming or make typos.

**Step 2 — Query the exact instance.** Record build, pod/container, management host, port, profile, and timestamp. Avoid reading `env` from replica A while user requests hit replica B.

**Step 3 — Check active profiles.** Does `/actuator/env` show `prod` active?

**Step 4 — Query a single key.** Use `/actuator/env/shipping.retry.max-attempts`.

**Step 5 — Note the winning source.** Inspect `property.source` and which other sources also have the key under `propertySources`.

**Step 6 — Check origin.** If the source is a file, identify which file is loaded. If CLI/ENV, cross-check the process/deployment config, not just the repository.

**Step 7 — Inspect configprops by prefix.** Verify `ShippingProperties` exists, prefix matches, and `retry.maxAttempts` is present.

**Step 8 — Distinguish properties from inputs.** The value may come from a Java default rather than a source with origin.

**Step 9 — Verify typed values safely.** For non-sensitive data, use tests/assertions or a secured internal channel rather than exposing raw values on the whole endpoint.

**Step 10 — Inspect the service.** If the bean is 7 yet the service caps it at 4, the issue is in application logic, not source precedence.

**Step 11 — Record the root cause.** State precisely whether "CLI beat profile," "field was not bound," "converter rejected value," "default was used," or "service transformed the value."

## 13. Experiment A: CLI Beats Profile File

With the lab app:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --shipping.retry.max-attempts=7
```

Common file sets 3; profile file sets 5; command line sets 7.

Assuming no higher source exists, `env/shipping.retry.max-attempts` reports the effective source is `commandLineArgs`. In `configprops/shipping`, the bean's `retry.maxAttempts` is bound as 7, provided config and classes are valid.

If an operator wants to remove the override, editing `application.yml` from 3 to 9 may have no effect because CLI keeps winning. Inspect the launcher, service manifest, Helm values, container args, or pipeline passing `--shipping.retry.max-attempts=7`.

**Proper diagnosis locates what actually supplies the override**, instead of bumping numbers in every file at once.

## 14. Experiment B: Profile Beats Common File

Run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

With no CLI override and no higher source:

```text
shipping.retry.max-attempts = 5
shipping.retry.backoff      = 1s
shipping.endpoint           = prod endpoint
```

Query `env/shipping.retry.max-attempts`: the source can be Config Data from `application-prod.yml`.

Run:

```bash
java -jar app.jar --spring.profiles.active=dev
```

If no `application-dev.yml` overrides it and no other source exists, `maxAttempts` falls back to 3 from the common file.

Lesson: seeing `activeProfiles=["prod"]` is not enough to know **every key** came from the profile file. For each key, still inspect the source chosen by the resolver.

## 15. Experiment C: Environment Variables

A container can supply:

```text
SHIPPING_RETRY_MAXATTEMPTS=9
```

Spring Boot has rules converting canonical names to environment-variable form: for instance `shipping.retry.max-attempts` converts to `SHIPPING_RETRY_MAXATTEMPTS` when replacing dots with underscores, removing dashes, and uppercasing.

With no CLI or higher source, the bean can receive 9.

If an operator opens a terminal outside the container and sees a variable of the same name, that does not guarantee the running process receives that variable. One shell's environment is not every process's environment. Check the `systemEnvironment` source on **the exact application** and cross-check deployment specs.

For keys with Maps/Lists or special characters, mapping rules have extra details. Do not deduce env names by swapping characters arbitrarily and assuming Binder interprets them as intended; when needed, write a test on the actual Boot version.

## 16. When env Is Right but configprops Lacks the Bean

Suppose:

```text
GET /actuator/env/shipping.retry.max-attempts
  -> has property and effective source

GET /actuator/configprops/shipping
  -> ShippingProperties not found
```

Possible causes:

1. Class was not registered with `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
2. Package scanning did not cover the class.
3. Bean creation had an unmet condition/profile.
4. Java prefix is not `shipping`.
5. Application uses `@Value` or `Environment` directly, with no configuration-properties bean.
6. You are querying the wrong instance or context.
7. Bean was constructed manually outside Spring, so it does not appear as Actuator expects.
8. Endpoint is not exposed or the request was blocked by security, making the reader mistake it for an empty response.

A key in Environment **does not auto-generate a Java bean**. You need a class, registration mechanism, and matching target type.

## 17. When Bean Has a Default but env Does Not Find the Key

Java:

```java
@ConfigurationProperties(prefix = "reports")
public class ReportProperties {
    private int maxRows = 100;

    public int getMaxRows() { return maxRows; }
    public void setMaxRows(int maxRows) {
        this.maxRows = maxRows;
    }
}
```

If no source declares `reports.max-rows`:

- `env/reports.max-rows` may not find the property.
- Bean `ReportProperties` still has `maxRows=100` from the Java initializer.
- `configprops` may show property 100 while `inputs` does not necessarily have a config-file origin.

Similarly with a record:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        @DefaultValue("100") int maxRows
) {}
```

`@DefaultValue` is a runtime binding default during constructor binding; it **does not create an extra PropertySource** with key `reports.max-rows`.

Therefore, "bean has a value while env lacks the key" **is not necessarily an error**. Distinguish object defaults from values supplied by an external source.

## 18. When env Is String but Bean Has a Different Type

Example:

```properties
shipping.retry.backoff=250ms
```

`Environment.getProperty("shipping.retry.backoff")` can return the string `"250ms"`. The record with `Duration backoff` binds to a `Duration` equivalent to 250 ms.

Java's printed representation can be `PT0.25S`; it differs from source text while having the same meaning.

Examples:

| Source string | Java type | Result |
| --- | --- | --- |
| `"7"` | `int` | 7 |
| `"false"` | `boolean` | false |
| `"250ms"` | `Duration` | 250 milliseconds |
| `"8MB"` | `DataSize` | DataSize object |
| `"https://x.example.invalid"` | `URI` | URI object |
| `"FAST"` | enum `Mode` | Enum `FAST` if declared validly |

`configprops` is where you inspect bean structure, yet if policy masks values, assert directly via tests for non-sensitive values instead of setting `always` in production.

### 18.1. Conversion Failures Prevent Application Startup

If configured:

```properties
shipping.retry.max-attempts=seven
```

and Java requires `int`, Binder can cause startup failure. When the application fails to start, **there is no live Actuator HTTP endpoint on the failed instance** to query. Use startup logs, secured stack traces, or a minimal test context.

Never query `env` of another running replica to infer the state of a crashed instance.

## 19. Placeholders Make Multiple Sources Determine the Result Together

Suppose the common file contains:

```yaml
partner:
  host: localhost
  url: "https://${partner.host}/api"
```

A Java system property or CLI supplies:

```properties
partner.host=partner.internal
```

`partner.url` may still come from `application.yml`, yet after placeholder resolution the value is:

```text
https://partner.internal/api
```

Therefore query both:

```bash
curl -i 'http://127.0.0.1:8080/actuator/env/partner.url'
curl -i 'http://127.0.0.1:8080/actuator/env/partner.host'
```

The winning source of `partner.url` is not necessarily the source that supplied the `host` portion. When a property has placeholders, diagnose **component keys**, not just the resulting key.

Another case:

```yaml
partner:
  url: "https://${partner.host:localhost}/api"
```

If `partner.host` is absent, the placeholder has fallback `localhost`. `env/partner.host` will not necessarily find a value because that fallback lives inside the expression rather than an independent property source.

## 20. Watch Lists and Maps When Comparing env and configprops

For scalars, picking the higher source is fairly intuitive. For collections, Binder has specific rules.

### 20.1. List

`application.yml`:

```yaml
routing:
  servers:
    - first.example.invalid
    - second.example.invalid
```

`application-prod.yml`:

```yaml
routing:
  servers:
    - prod.example.invalid
```

Spring Boot has rules replacing Lists across sources rather than always appending elements. The bean can receive only the single server from the profile.

When diagnosing, do not inspect only `routing.servers[0]` and extrapolate the entire List. Inspect `configprops` to see the bound structure.

### 20.2. Map

`application.yml`:

```yaml
routing:
  handlers:
    orders: order-handler
    payments: payment-handler
```

Profile file:

```yaml
routing:
  handlers:
    payments: prod-payment-handler
```

The Map can contain both `orders` and `payments`, where `payments` carries the value from the higher-precedence source.

If Map keys contain `/`, `@`, or special characters, use bracket notation to preserve literal keys, such as `"[/api/v1]"` in YAML. When a key is normalized incorrectly, `env` might show one property name while the bound Map has another key name; check the final Map structure in `configprops` as well.

## 21. When the Bean Is Right Yet the Service Uses Another Value

A service can apply a business rule:

```java
public int effectiveAttempts() {
    return Math.min(properties.retry().maxAttempts(), 4);
}
```

When the bean has `maxAttempts=7`, the service intentionally caps it at 4. There is no bug in sources or Binder.

Another variant:

```java
public final class RetryClient {
    private final int retryLimit;

    public RetryClient(ShippingProperties properties) {
        this.retryLimit = properties.retry().maxAttempts();
    }
}
```

If an operator adds a new PropertySource **after RetryClient was created**, a later `Environment.getProperty` call sees the new value, whereas `retryLimit` already captured the old snapshot.

**Modifying MutablePropertySources does not automatically refresh every bean.** When `env` and `configprops` or the service disagree in timing, check lifecycle, caching, refresh scope, and where beans are created. Do not treat runtime `Environment` changes as automatic rebinding.

## 22. Relaxed Binding, Canonical Names, and Typos

Java field:

```java
int maxAttempts;
```

Canonical configuration:

```properties
shipping.retry.max-attempts=7
```

Some name variants can be handled by Binder thanks to relaxed binding, yet that does not turn every typo into the right name.

Wrong:

```properties
shipping.retry.max-attmpts=7
```

This name is not equivalent to `max-attempts` just because it "looks close." Outcomes may be:

- `env/shipping.retry.max-attmpts` sees the misspelled key loaded.
- `env/shipping.retry.max-attempts` does not see the right key.
- The bean keeps a default or value from another source.
- Under default or custom `ignoreUnknownFields`, a property with no target may be ignored or fail depending on configuration.

Detection workflow:

1. Determine prefix and field from Java.
2. Use canonical lowercase kebab-case to query `env`.
3. Inspect actual key names in the identified sources.
4. Cross-check `configprops`.
5. Add tests to prevent typos from recurring.

## 23. Why Does @Value Not Appear Like configprops?

A bean can read directly:

```java
@Component
public class PartnerClient {

    public PartnerClient(
        @Value("${partner.timeout:2s}") Duration timeout) {
        // ...
    }
}
```

Or:

```java
String value = environment.getProperty("partner.timeout");
```

These approaches do not automatically register a `@ConfigurationProperties` bean with prefix `partner`. Therefore:

- `env/partner.timeout` can find the property.
- `configprops/partner` will not necessarily contain a corresponding bean.
- If you need to verify the injected `@Value`, test or diagnose that bean through a safe mechanism.

`configprops` is not a list of every bean or every injected field in the application. It focuses on **configuration properties beans**.

## 24. Test Cross-Checking Environment, Typed Bean, and Service

Create `ShippingBindingTest.java`:

```java
package com.example.shipping;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("prod")
@SpringBootTest(
    classes = ShippingApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "shipping.retry.max-attempts=7",
        "shipping.retry.backoff=250ms"
    }
)
class ShippingBindingTest {

    @Autowired
    Environment environment;

    @Autowired
    ShippingProperties properties;

    @Autowired
    ShippingPlanService service;

    @Test
    void checksResolverBindingAndConsumer() {
        assertThat(environment.getProperty(
            "shipping.retry.max-attempts"
        )).isEqualTo("7");

        assertThat(properties.retry().maxAttempts())
            .isEqualTo(7);

        assertThat(properties.retry().backoff())
            .isEqualTo(Duration.ofMillis(250));

        assertThat(service.currentPlan().maxAttempts())
            .isEqualTo(7);
    }
}
```

This test proves the test override data is used consistently by Resolver, Binder, and the service. **It does not test that command-line sources win**, because `@SpringBootTest.properties` is a **test PropertySource**, not `commandLineArgs`. If you need to prove the winning source in a CLI deployment, observe the actual CLI-launched process or write an appropriate bootstrap test.

### 24.1. Testing Without Opening Raw Values via Actuator

When `show-values=never`, HTTP requests may return only `******`. You can still use a test like the one above to assert `7` or `Duration.ofMillis(250)` independently, using non-sensitive values and an isolated context.

For passwords/tokens, do not write tests printing secrets; use a dummy sentinel and assert diagnostic responses **do not contain** the sentinel.

## 25. Safely Reading Responses with curl and jq

In a test environment with dummy data, you can filter relevant fields:

```bash
curl -fsS \
  'http://127.0.0.1:8080/actuator/env/shipping.retry.max-attempts' |
jq '{
  activeProfiles,
  winningSource: .property.source,
  sources: [
    .propertySources[] |
    {name, origin: .property.origin}
  ]
}'
```

This query targets source names and origins without pulling raw values. With `jq`, the `origin` field may be absent or null for sources that do not store origin info.

Viewing configprops bean names:

```bash
curl -fsS \
  'http://127.0.0.1:8080/actuator/configprops/shipping' |
jq '.contexts | to_entries[] | {
  context: .key,
  beans: (.value.beans | keys)
}'
```

In an authorized diagnostic environment, these two commands help reduce the amount of data inspected. **Filtering does not replace security.** Endpoints must still be secured, and transferring full JSON across proxies/networks still needs to obey security policy.

Do not record raw output in tickets, terminal history, or centralized logs unnecessarily.

## 26. Protecting Secrets When Using env and configprops

Configuration data can contain:

- Database passwords.
- Service tokens and API keys.
- Signing keys.
- URIs with user/password.
- Authorization headers.
- Client secrets, certificates, internal configuration.
- System names, topology, file paths, and sensitive profiles.

According to Spring Boot Actuator docs, `env` and `configprops` **sanitize all values by default** in modern versions; usually displaying `******`. There are three modes:

| `show-values` | Behavior |
| --- | --- |
| `never` | Always masks values |
| `when-authorized` | Can let authorized users see values; custom sanitizers can still mask |
| `always` | Can let endpoint callers see values; custom sanitizers can still mask |

Conservative configuration:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

If configuring `when-authorized`, understand roles and access channels:

- HTTP: principal is authenticated and satisfies configured endpoint roles.
- If no roles are configured, any authenticated user can be considered authorized.
- JMX has different rules: in the `when-authorized` context, JMX callers are considered authorized per modern docs.

**Do not enable `always` just to see a timeout.** If a non-sensitive value is needed, test the bean directly or build an authorized allowlisted diagnostic.

A response with masked values can still expose **key names, beans, paths, origins, and profiles**. Therefore never treat masked `env` as safe to expose publicly.

## 27. When Actuator Is Unreachable

| Symptom | Possible cause | Next step |
| --- | --- | --- |
| Connection refused | Wrong host/port, app not running | Check process and management port |
| `404` | Endpoint not exposed/missing, wrong path | Check enablement/access, exposure, base path |
| `401` | Authentication required | Use an authorized access path |
| `403` | Missing authorization | Check roles/security chain |
| `200` yet value is `******` | Sanitization enabled | Use source/origin or test typed bean |
| `200` yet bean missing | Bean unregistered / wrong prefix | Check `@ConfigurationProperties` |
| App crashes at startup | Bind/validation/conversion error | Read startup failure; do not rely on Actuator |
| Output differs across calls | Different instance/time/context | Pin target instance and record timestamp |

If a project defines its own `SecurityFilterChain`, verify it genuinely protects management endpoints. Never assume "Spring Security is on the classpath so all Actuator endpoints are locked down properly" once the app customizes security.

## 28. Diagnosing When the Application Fails to Start

Example:

```properties
shipping.retry.max-attempts=seven
```

If the record needs `int`, Binder can fail before the HTTP server is ready. You cannot query `/actuator/configprops` on the failed instance.

Troubleshooting order:

1. Read the `Failed to bind properties` message and type conversion cause.
2. Identify the exact property and Java type.
3. Find the loaded source indicated by error/origin if available.
4. Check files/ENV/CLI of **the exact process**.
5. Build a small test context with `ApplicationContextRunner` if wanting to confirm the expected startup failure.
6. Do not enable debug output that leaks real secrets.
7. Do not use a response from another replica as evidence for the failed instance.

`env` and `configprops` are tools for inspecting **a running application**; they do not replace startup logs in every scenario.

## 29. Diagnosing When Multiple Instances Exist

During a rolling update deployment:

```text
pod-A:
  image v1
  maxAttempts = 5

pod-B:
  image v2
  maxAttempts = 7
```

A load balancer can route `GET /actuator/env/...` to pod-A while business requests go to pod-B. Without knowing which instance answered, concluding "env=5 yet service uses 7" can be comparing two different systems.

Record:

- Instance ID/pod name.
- Artifact version.
- Active profiles.
- Timestamp.
- Property source and origin.
- Corresponding bean/configprops.
- Deployment config of that specific instance.

Use an internal management path per **individual instance** when investigating, rather than letting a gateway randomly pick a replica.

## 30. Exercise 1: Which Source Wins?

Given:

```text
application.yml:
  feature.limit = 10

application-prod.yml:
  feature.limit = 20

commandLineArgs:
  feature.limit = 30
```

The `prod` profile is active. Predict:

- Environment value is 30.
- `property.source` from `env/feature.limit` is `commandLineArgs` assuming no higher source exists.
- Both Config Data sources can still appear in `propertySources`.
- When `show-values=never`, origin/source names still help detect the override without seeing raw values.

Then remove the command-line argument, query the endpoint again on a new instance, and predict the effective value is 20.

## 31. Exercise 2: env Has Property, configprops Does Not Bind

Java:

```java
@ConfigurationProperties(prefix = "feature")
public record FeatureProperties(int maxItems) {}
```

Config:

```properties
feature.max-itmes=30
```

Explain:

1. `env/feature.max-itmes` can find this misspelled key.
2. `feature.max-items` is the canonical key matching Java.
3. Relaxed binding does not fix the typo `itmes`.
4. `maxItems` can keep its default or a value from another source.
5. Test typed beans and check spelling/unknown property policy.

## 32. Exercise 3: Comparing Typed Values

Input:

```properties
client.timeout=750ms
```

Java:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {}
```

Ask:

- Which source and text value can `env/client.timeout` display if permitted to view?
- Does `configprops/client` show the bean has a `timeout` field?
- What is the proper Java assertion?

Answer:

```java
assertThat(properties.timeout())
    .isEqualTo(Duration.ofMillis(750));
```

Do not demand that the `Duration` object print verbatim as `750ms`.

## 33. Exercise 4: Default Without Origin

Record:

```java
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
    @DefaultValue("100") int maxRows
) {}
```

No source declares `reports.max-rows`. Explain why `env` may not find the key while the bean still receives 100 from constructor binding. Do `configprops.properties` and `configprops.inputs` mean the same thing?

## 34. Exercise 5: URL with Placeholder

YAML:

```yaml
service:
  host: localhost
  url: "http://${service.host}:8080"
```

A higher-precedence source supplies `service.host=service.internal`. Query `env/service.host` and `env/service.url` separately, compare the winning source of each key, and deduce the resolved URL. Why is the URL's source not necessarily the host's source?

## 35. Exercise 6: Lists and Maps

The common file declares two servers in a List and two handlers in a Map. The prod file declares one server and overrides one handler. Use `configprops` to inspect the List under replacement rules and the Map under merge/override rules. Explain why inspecting individual keys via `env` alone is insufficient to predict every bound structure.

## 36. Exercise 7: Fixing Security Risks

A deployment has:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
  endpoint:
    env:
      show-values: always
    configprops:
      show-values: always
```

Propose ways to reduce risk:

1. Allowlist endpoints.
2. Set `show-values=never` when raw values are unnecessary.
3. Use authentication/authorization and a management network.
4. Check JMX exposure.
5. Do not print responses containing secrets.
6. Use tests with dummy tokens to verify masking.

## 37. Exercise 8: Service Differs from Bean

`ShippingProperties.retry.maxAttempts=7`, yet the service uses:

```java
int effective = Math.min(properties.retry().maxAttempts(), 4);
```

Determine the output of:

- `env/{key}`.
- `configprops`.
- Actual service.
- Root cause.

Hint: there is no conflict between sources or Binder; the cap of 4 comes from service logic.

## 38. Exercise 9: Handling Startup Failure

Config declares:

```properties
shipping.retry.max-attempts=seven
```

The app fails to start because converting `String` to `int` failed. Why can you not wait for `/actuator/env` to respond on that exact instance? Propose a workflow to read startup failure and create a small binding test to verify.

## 39. Practical Operations Checklist

- [ ] Right instance, right version, and timestamp.
- [ ] Canonical property name determined from Java.
- [ ] Checked `activeProfiles`.
- [ ] Queried `env/{property.name}`.
- [ ] Recorded `property.source`.
- [ ] Inspected competing sources in order.
- [ ] Read origin if available.
- [ ] Confirmed `@ConfigurationProperties` bean is registered.
- [ ] Queried `configprops/{prefix}`.
- [ ] Distinguished `properties` and `inputs`.
- [ ] Accounted for defaults, placeholders, and type conversion.
- [ ] Accounted for List/Map/relaxed binding.
- [ ] Verified the service consumer.
- [ ] Maintained sanitization and secured endpoints.
- [ ] Identified the root cause at the right layer.

## 40. Summary

When Spring Boot uses Externalized Configuration, a value can change before reaching a bean due to **higher-precedence sources**, or differ in representation after reaching the bean due to **Binder, defaults, conversion, and object structure**. The two Actuator endpoints provide a strong verification chain:

```text
/actuator/env/{key}
  -> property.source
  -> propertySources by precedence
  -> origin, profiles if present
             |
             v
   @ConfigurationProperties Binder
             |
             v
/actuator/configprops/{prefix}
  -> bean name / prefix
  -> properties / inputs
             |
             v
   Service receives typed object
```

Remember:

1. **`env` identifies the winning source**; it does not prove the service uses the right object.
2. **`configprops` shows binding results**; it does not replace checking Config Data sources and precedence.
3. **`properties` differs from `inputs`**: defaults can give a bean a value without a corresponding source origin.
4. **Keep exact canonical names**; relaxed binding does not fix arbitrary typos.
5. **Lists, Maps, placeholders, and converters** mean a single scalar lookup cannot describe an entire target structure.
6. **Cross-check on the same instance at the same time**, especially during rolling deployments.
7. **Never enable raw values just for debugging convenience**: Actuator masks values by default and endpoints still require security.
8. **When the app fails to start**, read startup errors and use a test context instead of trying to call Actuator.
9. **Conclude at the right layer**: source, profile, precedence, binding, validation, lifecycle, or service logic.

### Official Documentation

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Environment (env) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Boot — Configuration Properties (configprops) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Framework — ConfigurableEnvironment API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)
