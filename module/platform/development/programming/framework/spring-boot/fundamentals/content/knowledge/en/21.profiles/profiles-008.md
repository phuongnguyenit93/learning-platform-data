# `spring.config.activate.on-profile` and multi-document configuration

In Spring Boot, configuration often varies by environment: local uses port 8081 and DEBUG logs, staging enables experimental integrations, and production uses real endpoints and INFO logs. You can separate these values into `application-dev.yml` and `application-prod.yml` files, or place them as **multiple configuration documents (multi-document configuration)** within a single file.

With the second approach, `spring.config.activate.on-profile` specifies that **a configuration document is applied only when its profile expression matches the running environment**.

Example:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

logging:
  level:
    com.example.orders: DEBUG
```

The first document is shared configuration. The document after `---` is activated only when profile `dev` matches. Both documents reside in **one file** `application.yml`, yet are treated by Spring Boot as **two separate conditional configuration blocks**.

This lesson explains YAML and `.properties` syntax, how profiles are selected, profile expressions, precedence order, override rules, Config Data restrictions, and how to verify which configuration actually takes effect.

## 1. Three concepts to distinguish

Before using `spring.config.activate.on-profile`, clearly separate:

1. **Active profile**: names of environments/features currently activated in `Environment`, such as `dev`, `prod`, or `cloud`.
2. **Profile-specific file**: a file selected by profile name, such as `application-dev.yml`.
3. **Profile-activated document**: a section of a file activated by `spring.config.activate.on-profile`.

All three relate to profiles, but they are not identical.

### 1.1. Active profile is the state of `Environment`

You can activate a profile when running:

```bash
java -jar order-service.jar --spring.profiles.active=dev
```

Or supply an environment variable:

```text
SPRING_PROFILES_ACTIVE=dev
```

At this point Spring Boot can load profile-specific files and evaluate documents whose `on-profile` expression matches `dev`.

### 1.2. Profile-specific files are recognized by name

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

When `dev` is activated, `application-dev.yml` can be loaded under Config Data lookup rules; when `prod` is activated, `application-prod.yml` is considered instead.

In the simple case, you do not need to declare `spring.config.activate.on-profile` inside each file that already has a profile suffix. The filename already expresses the profile selection condition.

### 1.3. Profile-activated documents live inside a single file

```yaml
app:
  mode: standard

---
spring:
  config:
    activate:
      on-profile: prod

app:
  mode: strict
```

Both parts are in `application.yml`. Spring Boot applies the second part only when the `prod` expression matches.

### 1.4. `@Profile` is a bean registration condition

```java
@Configuration
@Profile("prod")
public class ProductionPaymentConfiguration {
    // Beans intended only for production
}
```

`@Profile` conditions a **bean or configuration class**. In contrast, `spring.config.activate.on-profile` conditions a **property document**. Both inspect active profiles, yet they do not replace each other.

| Mechanism | Subject of the condition |
| --- | --- |
| `spring.profiles.active` | Sets the active profiles |
| `application-prod.yml` | Selects the configuration file matching the profile |
| `spring.config.activate.on-profile` | Selects a document inside a Config Data source |
| `@Profile("prod")` | Conditions a bean or configuration class |
| `@ConditionalOnProperty` | Conditions configuration/beans based on a property value |

## 2. What is multi-document configuration?

A file can contain **multiple documents** separated by a marker. Each document declares its own properties. Spring Boot loads the effective documents and combines them according to Config Data system rules.

Three-part example:

```text
application.yml
    |
    +-- Document 1: shared values
    |
    +-- Document 2: used only with profile dev
    |
    +-- Document 3: used only with profile prod
```

In YAML, the separator marker is the line `---`. In `.properties`, Spring Boot supports its own document-separator syntax, such as `#---`.

### 2.1. A configuration file is not a Java bean

YAML or properties documents are read into property sources. Spring can then use them to bind `@ConfigurationProperties`, resolve `@Value` placeholders, or configure framework beans.

```text
application.yml
     |
     v
Split into documents
     |
     v
Evaluate activation conditions
     |
     v
Combine effective documents
     |
     v
Spring Environment
     |
     v
@ConfigurationProperties / @Value / auto-configuration
```

A document's condition decides **which properties are present in Environment**, not directly creating or destroying a bean instance.

## 3. Multi-document YAML: the `---` marker

Example of an `application.yml` with shared, dev, and prod configurations:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8080

app:
  catalog:
    refresh-interval: 30m
    audit-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

logging:
  level:
    com.example.catalog: DEBUG

app:
  catalog:
    refresh-interval: 30s

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO

app:
  catalog:
    audit-enabled: true
```

The first document **carries no profile condition**, so it is applied whenever the file is loaded. The dev document takes effect only when `dev` matches, and the prod document only when `prod` matches.

### 3.1. When neither dev nor prod is active

Suppose the application runs without activating `dev` or `prod`:

| Property | Value from example |
| --- | --- |
| `spring.application.name` | `catalog-service` |
| `server.port` | `8080` |
| `app.catalog.refresh-interval` | `30m` |
| `app.catalog.audit-enabled` | `false` |
| `logging.level.com.example.catalog` | Not declared by any of the three documents |

Do not equate "no user-set active profile" with "no profile evaluated": Spring has the **default profile** concept. In this example, no document requires the `default` profile, so the conclusion above does not change.

### 3.2. When the `dev` profile is active

Suppose only `dev` is activated and there is no higher-precedence property source:

| Property | Final value |
| --- | --- |
| `spring.application.name` | `catalog-service` |
| `server.port` | `8081` |
| `app.catalog.refresh-interval` | `30s` |
| `app.catalog.audit-enabled` | `false` |
| `logging.level.com.example.catalog` | `DEBUG` |

The dev document **adds** new properties and **overrides** matching keys from the shared document.

### 3.3. When the `prod` profile is active

Suppose only `prod` is activated:

| Property | Final value |
| --- | --- |
| `server.port` | `8080` |
| `app.catalog.refresh-interval` | `30m` |
| `app.catalog.audit-enabled` | `true` |
| `logging.level.root` | `INFO` |

The dev document does not apply. The prod document overrides only the keys it defines; other keys can still come from the shared document.

### 3.4. Do not misindent `---`

The YAML marker must appear at the document level on a proper separator line:

```yaml
app:
  feature: default

---
spring:
  config:
    activate:
      on-profile: test
```

Do not indent `---` as a child under `app`. A document separator marker is not a key inside a YAML mapping.

## 4. Multi-document in `application.properties`

Spring Boot also supports multiple documents in a single `.properties` file using a marker on its own line:

```properties
spring.application.name=catalog-service
server.port=8080
app.catalog.audit-enabled=false

#---
spring.config.activate.on-profile=dev
server.port=8081
logging.level.com.example.catalog=DEBUG

#---
spring.config.activate.on-profile=prod
app.catalog.audit-enabled=true
logging.level.root=INFO
```

`#---` is Spring Boot Config Data's separator marker in `.properties` files. `!` can also be used as `!---`.

### 4.1. Distinguishing `.properties` markers from YAML

| File | Commonly used marker |
| --- | --- |
| `application.yml` | `---` |
| `application.properties` | `#---` or `!---` |

In `.properties`, the marker must follow syntax recognized by Spring Boot: standing alone on a line, with no arbitrary content after the marker, and not indented in a way that invalidates it. Do not use YAML's `---` marker as a regular property line assuming Spring Boot will split the document.

In particular, comment lines immediately adjacent to the marker can cause separator detection to behave unexpectedly. When adding explanatory comments, place them at the top of the configuration section or structure the file clearly, keeping the marker aligned with Spring Boot conventions.

### 4.2. Why does `spring.config.activate.on-profile` use flat syntax?

In `.properties`, there is no indentation to express structure:

```properties
spring.config.activate.on-profile=dev
```

In YAML, the equivalent configuration:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

Both produce a key named `spring.config.activate.on-profile`.

### 4.3. When to use multi-document properties?

This is a valid option if the team already uses `.properties` and only needs a few profile variants in the same file. However, when documents grow long or there are many profiles, separate files like `application-dev.properties` are usually easier to read and manage.

## 5. Exact meaning of `spring.config.activate.on-profile`

`spring.config.activate.on-profile` is a **condition determining whether the document being read is activated**.

It is not a command saying "enable this profile".

Example:

```yaml
spring:
  config:
    activate:
      on-profile: staging

app:
  api:
    sandbox: true
```

This document means:

> Include `app.api.sandbox=true` in effective configuration only when the profile expression `staging` matches.

It **does not** activate `staging` by itself.

### 5.1. Right order of thinking

```text
1. Active profiles are determined
          |
          v
2. Spring Boot reads matching Config Data sources
          |
          v
3. Each document with on-profile is evaluated
          |
          +--> Match: include properties in effective config sources
          |
          +--> No match: skip that document
          |
          v
4. The system merges and resolves properties
```

This is a conceptual model: Config Data also has to handle source ordering, imports, profile activation, and other internal steps. The key point is that `on-profile` **checks** profiles, it does not **create** profiles.

### 5.2. Right and wrong about intent

Wrong intent:

```yaml
spring:
  config:
    activate:
      on-profile: prod

# Does NOT mean the snippet above enables prod automatically
```

Right if you want to explicitly enable the profile via command line:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

Once active profiles are determined, the `on-profile: prod` document is evaluated against that condition.

## 6. Profile expressions: single profile, OR, AND, and NOT

`on-profile` supports **profile expressions**, not just a single profile name.

Example:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

The document is activated when `dev` matches.

### 6.1. OR: one of several profiles

```yaml
spring:
  config:
    activate:
      on-profile: "dev | staging"

app:
  diagnostics:
    verbose: true
```

The document can apply if `dev` **or** `staging` is active.

This is a good option when sharing the same configuration across multiple non-production environments.

### 6.2. AND: requiring multiple profiles simultaneously

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  integration:
    use-managed-identity: true
```

The document matches only when **both `prod` and `cloud`** are active together.

For example, `prod` represents the production environment, while `cloud` represents an additional infrastructure configuration layer.

### 6.3. NOT: excluding a profile

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"

app:
  demo:
    enabled: true
```

The expression above matches when `prod` is not active according to Spring's profile expression evaluation.

**Important in YAML:** expressions starting with `!` must be quoted, because `!` has special syntactic meaning in YAML.

### 6.4. Combining conditions with parentheses

```yaml
spring:
  config:
    activate:
      on-profile: "(dev | staging) & cloud"

app:
  observability:
    verbose: true
```

This document matches when `cloud` is active alongside either `dev` or `staging`.

To avoid confusion about operator precedence, always use explicit parentheses when an expression combines multiple operators.

### 6.5. Example evaluation table

With expression `(dev | staging) & cloud`:

| Active profiles | Result |
| --- | --- |
| `dev` | No |
| `cloud` | No |
| `dev,cloud` | Yes |
| `staging,cloud` | Yes |
| `prod,cloud` | No |
| `dev,staging,cloud` | Yes |

### 6.6. `.properties` syntax for expressions

```properties
#---
spring.config.activate.on-profile=(dev | staging) & cloud
app.observability.verbose=true
```

In `.properties`, everything to the right of `=` is the expression value. In YAML, use quoted strings so the parser does not misinterpret special characters.

### 6.7. Do not confuse profile expressions with property conditions

`on-profile` checks only profiles. If you want a document to apply only when the property `feature.x.enabled=true`, you cannot treat that value as a profile on its own.

Use `@ConditionalOnProperty` to condition beans, or structure profile/property configuration appropriately. If the goal is controlling Config Data based on an environment recognized by Spring Boot, look at supported activation mechanisms like `on-cloud-platform`.

## 7. One application having multiple active profiles

Spring supports multiple simultaneous active profiles:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod,cloud
```

You can organize configuration along two dimensions:

- `prod` or `dev` describes the deployment lifecycle.
- `cloud` or `on-premise` describes infrastructure.

Example:

```yaml
app:
  telemetry:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: prod

app:
  telemetry:
    enabled: true

---
spring:
  config:
    activate:
      on-profile: cloud

app:
  telemetry:
    export-endpoint: "https://telemetry.example.com"

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  telemetry:
    batch-size: 1000
```

If `prod,cloud` are active together, matching documents can contribute configuration under the same `app.telemetry` prefix.

| Property | Expected value under `prod,cloud` |
| --- | --- |
| `app.telemetry.enabled` | `true` |
| `app.telemetry.export-endpoint` | `https://telemetry.example.com` |
| `app.telemetry.batch-size` | `1000` |

The example assumes no other configuration source overrides them. If two documents declare **the same key**, document order and precedence decide the final value.

### 7.1. Avoid ambiguous multi-profile combinations

A combination like `dev,prod` active at the same time can cause multiple environment documents to match. When those documents both declare `server.port` or endpoints, the outcome may differ from expectations.

If environments are designed to be mutually exclusive, the deployment system must ensure only one primary environment profile is chosen, or explicitly validate profile combinations.

### 7.2. Profiles are not a permissions system

Profiles help select configuration and beans in Spring; they do not replace authentication, authorization, secret separation, or deployment policies. Having `prod` active does not automatically make an application more secure.

## 8. Later documents can override earlier documents

When multiple documents within **the same file** take effect together, Spring Boot processes them top to bottom, and **a document appearing later has higher precedence** than an earlier document for overlapping keys, within the scope of those documents.

Example:

```yaml
app:
  mode: base
  retries: 2

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: debug

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: local-override
  retries: 5
```

When `dev` is active, all three documents match, and with no higher source:

```text
app.mode    = local-override
app.retries = 5
```

Because the last document overrides the corresponding keys.

### 8.1. Should you rely on multiple documents for the same profile?

You can, but if a profile appears multiple times with overlapping keys, readers must scan the entire file to determine the final value.

In real projects, prefer:

- One shared document.
- One document per profile or easily recognizable condition group.
- Intentional additional override layers with clear purpose.
- Minimizing unnecessary declarations of the same key across multiple documents.

### 8.2. Document order does not replace system-wide PropertySource order

A later document beating an earlier document **within the same configuration source** does not mean it beats every other source. Environment variables, command-line arguments, test properties, external Config Data, and other sources still participate in Spring Boot's overall precedence order.

For example, if YAML sets `server.port=8081` yet the command line passes `--server.port=9000`, the command-line value usually takes precedence under default Spring Boot configuration.

## 9. Properties forbidden inside profile-activated documents

This is an important restriction of modern Spring Boot Config Data.

Properties controlling **which profiles themselves are activated** must be defined in a **non-profile-specific** document. Properties such as:

- `spring.profiles.active`
- `spring.profiles.default`
- `spring.profiles.include`
- `spring.profiles.group.*`

must not be placed in profile-specific files or documents that already have `spring.config.activate.on-profile`.

### 9.1. Invalid example: activating a profile inside a conditional document

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod

app:
  mode: debug
```

This is invalid configuration under modern Spring Boot Config Data rules. Spring Boot may report an error about profile-activation properties being used inside a profile-specific document.

Semantically, this configuration also creates a confusing loop: the document only applies if `dev` is already active, yet tries to alter the active profiles set from inside that document.

### 9.2. Valid example: active profile in the shared document

```yaml
spring:
  profiles:
    active: dev

app:
  mode: default

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: debug
```

This example is valid regarding where profile configuration sits. However, in an artifact deployed across multiple environments, usually **do not hard-code** `dev` into the shared file. Pass `SPRING_PROFILES_ACTIVE` or `--spring.profiles.active` from the deployment environment.

### 9.3. Invalid example with `spring.profiles.include`

Do not write:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: cloud
```

`spring.profiles.include` must be declared in an appropriate non-profile-specific source.

### 9.4. Profile groups must also be defined in the right place

Example of a shared configuration:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - cloud
        - metrics
```

When activating the `production` group profile, Spring Boot can expand the active profiles set according to the group definition.

Do not place this group declaration inside a document that already has `on-profile: prod`; groups are used to **determine the set of profiles**, not as properties that appear only after a profile condition matches.

## 10. Default profile and the `!prod` expression

When no active profile is declared, Spring Framework has the concept of **default profiles**; under standard settings, the default profile is named `default`.

This affects documents such as:

```yaml
spring:
  config:
    activate:
      on-profile: default

app:
  mode: local-default
```

This document can be applied when the application has no active profile and `default` is the default profile.

### 10.1. Do not confuse `default` with an unconditional document

```yaml
app:
  mode: base
```

The document above **does not require** the `default` profile; it is the shared document of the loaded file and applies even when `dev`, `prod`, or another profile is active.

In contrast:

```yaml
spring:
  config:
    activate:
      on-profile: default
```

places a specific profile condition on that document.

### 10.2. `!prod` means `prod` is absent during active/default profile evaluation

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

This document can apply for local/dev/staging or whenever no `prod` profile matches.

However, do not put secrets or dangerous settings into a `!prod` document assuming all non-production environments are safe. Real environments can still carry multiple profiles, and conditional documents can behave unexpectedly if profile names are misconfigured.

## 11. `application-{profile}.yml` vs. documents with `on-profile`

These two strategies typically solve the same problem.

### 11.1. Multi-file strategy

```text
application.yml
application-dev.yml
application-prod.yml
```

**`application.yml`:**

```yaml
app:
  cache:
    ttl: 10m
```

**`application-dev.yml`:**

```yaml
app:
  cache:
    ttl: 10s
```

**`application-prod.yml`:**

```yaml
app:
  cache:
    ttl: 30m
```

### 11.2. Single multi-document file strategy

```yaml
app:
  cache:
    ttl: 10m

---
spring:
  config:
    activate:
      on-profile: dev

app:
  cache:
    ttl: 10s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  cache:
    ttl: 30m
```

### 11.3. Selection criteria

| Criterion | Separate files per profile | Multi-document in one file |
| --- | --- | --- |
| Few properties change | Can feel like too many files | Compact, easy to compare |
| Profiles have lots of dedicated config | Easy to organize | File easily grows long |
| Reviewing changes for one environment | Focused on the right file | Must locate the right document |
| Sharing common configuration | Shared base file | Shared first document |
| Compound profile conditions | May require extra organization | `on-profile` expresses directly |
| Ease of scanning in an editor | Clear via filenames | Must recognize separators |
| Risk of duplicate keys | Across files | Across documents |

Neither strategy is always superior. For a few simple variants, multi-document is very convenient. When each environment has extensive dedicated configuration or requires group-owned reviews, separate profile files can be easier to maintain.

### 11.4. Can both be combined?

Yes. A project can use `application.yml` containing a shared document and some conditional documents, while also having `application-prod.yml`.

However, when multiple sources write the same key, you must understand the **overall Config Data precedence order**. Avoid combining them solely to "guarantee an override" without conventions, as it makes effective values harder to trace.

## 12. Lists, maps, and override behavior

Not all data types combine the same way across multiple documents.

### 12.1. Scalar property

```yaml
app:
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  timeout: 3s
```

When `prod` is active and there is no higher source, `app.timeout=3s`.

### 12.2. Maps can be bound from multiple sources

```yaml
app:
  headers:
    x-client: order-service
    x-region: default

---
spring:
  config:
    activate:
      on-profile: prod

app:
  headers:
    x-region: ap-southeast
```

When binding into a `Map<String, String>` under configuration properties mechanics, Spring Boot can combine entries from multiple property sources and use the higher-precedence value for overlapping keys.

In this example, the map can contain `x-client=order-service` and `x-region=ap-southeast`.

### 12.3. Lists are usually replaced, not appended

```yaml
app:
  regions:
    - HCM
    - HN

---
spring:
  config:
    activate:
      on-profile: prod

app:
  regions:
    - HCM
    - DN
```

When `prod` is active and `app.regions` is bound to `List<String>`, the list from the higher-precedence source usually **replaces** the list from the lower-precedence source instead of merging into four elements.

This is an important practical difference: if you want to keep common elements while adding specific elements, design the configuration differently or merge the data with explicit logic.

### 12.4. Do not guess merge behavior from YAML structure

YAML looks like a configuration tree, but Spring Boot ultimately processes property sources and a binder. Having one YAML node nested under another does not mean collections always merge like JavaScript object structures.

## 13. `spring.config.activate.on-cloud-platform` and other activation conditions

Spring Boot Config Data also supports activation based on matching cloud platforms, for example:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  discovery:
    enabled: true
```

The document is applied only when the cloud platform condition is detected and matched by Spring Boot. This is a separate activation dimension from profiles.

### 13.1. Combining with `on-profile`

Example:

```yaml
spring:
  config:
    activate:
      on-profile: prod
      on-cloud-platform: kubernetes

app:
  observability:
    mode: cluster
```

In this case, the document must satisfy **both the profile condition and the cloud platform condition** under the corresponding activation rules.

Do not put `kubernetes` in `on-profile` assuming Spring Boot automatically enables that profile just because the application runs on Kubernetes. Profiles and cloud-platform detection are two separate mechanisms.

### 13.2. When to use?

If configuration differs solely by infrastructure deployment platform, `on-cloud-platform` can fit. If differences follow `dev`, `staging`, `prod` conventions, `on-profile` is usually more direct and understandable.

## 14. Supplying profiles from environment variables and command line

Production applications are typically deployed using a single artifact, while profiles are supplied by operations.

### 14.1. Command-line arguments

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

With multiple profiles:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod,cloud
```

### 14.2. Environment variables

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar catalog-service.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar catalog-service.jar
```

### 14.3. In Gradle or an IDE

When using an appropriate Gradle Boot plugin:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

In an IDE, pass `--spring.profiles.active=dev` in **Program arguments** or configure appropriate environment variables.

Do not copy those commands into Java code. In production, the deployment system usually decides active profiles.

### 14.4. Note on precedence

If the shared file says:

```properties
spring.profiles.active=dev
```

yet the command line passes:

```text
--spring.profiles.active=prod
```

then the command-line property normally has higher precedence under default Spring Boot configuration. That is one reason deployment environment profiles should be set outside the artifact.

## 15. `spring.profiles.include` and profile groups

These two mechanisms help organize multiple related profiles without listing all of them in every startup command.

### 15.1. `spring.profiles.include`

Example in a non-profile-specific document:

```yaml
spring:
  profiles:
    include:
      - common-metrics
```

The `common-metrics` profile is added to the active profiles set according to Spring Boot rules. Note not to place `include` inside a document activated by `on-profile`.

### 15.2. Profile groups

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - cloud
        - observability
```

Then run:

```bash
java -jar catalog-service.jar --spring.profiles.active=production
```

Spring Boot can expand `production` into the group members so that matching documents are activated.

Groups let a "high-level" profile carry multiple capability profiles along with it. However, groups must be defined **in a non-profile-specific document** to avoid circular conditional dependencies when determining active profiles.

### 15.3. When to use group vs. expression?

- **Group:** you want one profile name to represent multiple profiles that should be activated together.
- **Expression:** you want a document to be applied when a combination of profiles is already active.

For example, the `production` group activates `prod,cloud`, whereas an `on-profile: "prod & cloud"` document only **checks** that those two profiles are both effective.

## 16. Binding into Java: profiles select properties, not changing code

Consider an application calling a partner API.

### 16.1. Configuration properties

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        Duration timeout,
        boolean sandbox
) {
}
```

Spring Boot 3.x can bind records via constructor. For older generations, using immutable properties may require different annotations or registration setup.

### 16.2. Multi-document declaration

```yaml
app:
  partner:
    base-url: "https://sandbox.example.com"
    timeout: 5s
    sandbox: true

---
spring:
  config:
    activate:
      on-profile: prod

app:
  partner:
    base-url: "https://api.example.com"
    timeout: 2s
    sandbox: false
```

When `prod` is not active, the record receives sandbox values from the shared document. When `prod` is active and there is no higher-precedence override source, the record receives the production endpoint and `sandbox=false`.

### 16.3. Registering the bean

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Place `PartnerProperties` in a subpackage of `com.example.orders` or declare explicit scan packages so the class is registered.

### 16.4. Services do not need to know which file was selected

```java
package com.example.orders.service;

import com.example.orders.config.PartnerProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerGateway {

    private final PartnerProperties properties;

    public PartnerGateway(PartnerProperties properties) {
        this.properties = properties;
    }

    public boolean useSandbox() {
        return properties.sandbox();
    }

    public URI target() {
        return properties.baseUrl();
    }
}
```

The service depends only on `PartnerProperties`. Config Data and the binder already resolved appropriate values before the service uses them.

### 16.5. Configuration validation

With an appropriate Jakarta Validation dependency:

```java
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        boolean sandbox
) {
}
```

Validation helps catch missing or wrongly typed configuration at startup. For instance, `app.partner.timeout=abc` cannot bind validly to `Duration`.

Do not place secrets directly into a record and then log the whole record, because the record's `toString()` can print sensitive fields.

## 17. How do `@Profile` bean conditions relate?

Suppose an application needs different implementations by environment:

```java
public interface NotificationSender {
    void send(String message);
}
```

```java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    public NotificationSender devNotificationSender() {
        return message -> System.out.println("DEV: " + message);
    }

    @Bean
    @Profile("prod")
    public NotificationSender prodNotificationSender() {
        return new SmtpNotificationSender();
    }
}
```

`@Profile` decides which bean method is used to register the bean. Meanwhile, `on-profile` selects the matching property document. Both can be used when the application genuinely needs to change both implementation and configuration.

### 17.1. Do not overuse profiles to select every value

If only timeout and URL change, two implementations are usually unnecessary:

```yaml
app:
  partner:
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  partner:
    timeout: 2s
```

A single `PartnerGateway` using `PartnerProperties` is enough.

### 17.2. What if no profile matches?

With two beans carrying only `@Profile("dev")` and `@Profile("prod")`, when neither matching profile is active, **no `NotificationSender` bean** may exist. If another service injects a required `NotificationSender`, startup can fail.

Solutions include providing a valid fallback, checking required profiles, or designing conditions properly for the environments the application supports.

## 18. `spring.config.import` and multi-part configuration

In systems with multiple modules or configuration sources, Spring Boot can import additional Config Data:

```yaml
spring:
  config:
    import: "optional:classpath:partner-settings.yml"
```

`optional:` allows the source to be absent. If `optional:` is omitted and a required file is missing, startup can fail.

An imported source can contain multiple documents and its own activation conditions under Config Data rules.

### 18.1. Do not confuse importing files with activating profiles

`spring.config.import` tells Spring Boot to inspect an additional Config Data source. `spring.config.activate.on-profile` decides whether a document takes effect when profiles match. Importing a file does not automatically activate profiles mentioned inside that file.

### 18.2. Config Data order can be more complex than document order

When a file imports additional Config Data, the imported source has rules governing ordering and precedence relative to the importing source. When multiple imports and multiple profiles operate together, reading documents top to bottom in one file **is not enough** to know the final value.

Inspect actual property sources or test with the corresponding profiles, rather than guessing by filename order.

### 18.3. Location properties must be provided early enough

Properties such as:

```text
spring.config.name
spring.config.location
spring.config.additional-location
```

are used when Spring Boot decides where to look for Config Data. They usually need to be supplied from environment variables, Java system properties, or command-line arguments during early startup.

Do not put them inside a file that Spring Boot does not yet know how to find expecting that file to change its own search location.

## 19. How to verify which documents were activated

When configuration is wrong, typical symptoms are:

- A property uses the shared value instead of the profile value.
- Log levels do not change even though `dev` was activated.
- Endpoints or ports do not match the desired environment.
- A `@Profile` bean does not appear.
- Startup fails because a profile-controlling property was placed in the wrong document.

Inspect from the outside in.

### 19.1. Confirm active profiles

An `ApplicationRunner` can print the profile list:

```java
package com.example.catalog;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileReporter implements ApplicationRunner {

    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: " +
                Arrays.toString(environment.getActiveProfiles())
        );

        System.out.println(
                "Catalog refresh interval: " +
                environment.getProperty(
                        "app.catalog.refresh-interval"
                )
        );
    }
}
```

Example output when `dev` is active:

```text
Active profiles: [dev]
Catalog refresh interval: 30s
```

This is illustrative output when the earlier config files take effect and there is no higher-precedence source.

### 19.2. `getActiveProfiles()` differs from `getDefaultProfiles()`

You can inspect default profiles too:

```java
System.out.println(
        Arrays.toString(environment.getDefaultProfiles())
);
```

If no explicit active profile is set, the active profiles array can be empty while `getDefaultProfiles()` contains `default`.

This is very useful when a document with `on-profile: default` applies even though you did not pass `spring.profiles.active`.

### 19.3. Check the final property

```java
String mode = environment.getProperty(
        "app.mode",
        "unknown"
);
```

If mode is not as expected, check:

1. Actual active profiles.
2. Which files Spring Boot discovered.
3. Whether a `---` or `#---` separator is missing.
4. Whether `on-profile` has valid syntax and the right condition.
5. Whether a later document or higher-precedence source overrode the key.

### 19.4. Viewing Config Data loading information

When deep analysis is needed, you can raise logging for config loading in a development environment:

```properties
logging.level.org.springframework.boot.context.config=TRACE
```

TRACE logs help observe Config Data search and loading steps. Enable it only in controlled environments and do not write sensitive logs to unprotected locations.

### 19.5. Actuator `/env` and `/configprops`

If you add Spring Boot Actuator and expose appropriate endpoints:

- `/actuator/env` provides information about environment and property sources.
- `/actuator/configprops` provides binding data for configuration properties beans.

These endpoints can contain property names or sensitive data. Spring Boot provides sanitization depending on version, yet **you should not expose them publicly just to debug**.

### 19.6. When conditions are on beans

If an `on-profile` document supplies properties used by `@ConditionalOnProperty`, you can pass `--debug` to view Spring Boot's **Conditions Evaluation Report**.

Note: this report primarily explains condition/auto-configuration decisions, not a full listing of every selected config document. To trace final values, you still need to check Environment and property sources.

## 20. Automated profile testing examples

Writing tests preserves behavior when multiple documents and profiles exist.

### 20.1. Testing with the dev profile

Suppose configuration in `application.yml` is:

```yaml
app:
  mode: standard
  request-timeout: 10s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: development
  request-timeout: 30s
```

Test using Spring Boot Test:

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class DevConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void loadsDevDocument() {
        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("development");
        assertThat(environment.getProperty("app.request-timeout"))
                .isEqualTo("30s");
    }
}
```

`@ActiveProfiles("dev")` sets the profile for the test context. The test assumes no higher-precedence test property source or environment variable overrides the asserted keys.

### 20.2. Testing with another profile

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProdConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void keepsBaseValueWithoutProdOverride() {
        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("standard");
    }
}
```

In this example there is only an `on-profile: dev` document, so `prod` does not change `app.mode`. If a prod document declaring a different `app.mode` is added later, update the test expectations according to the new contract.

### 20.3. Verifying typed binding

You can also create a record:

```java
@ConfigurationProperties(prefix = "app")
public record AppSettings(
        String mode,
        Duration requestTimeout
) {
}
```

After registering the configuration properties bean, tests can assert:

```java
assertThat(settings.mode()).isEqualTo("development");
assertThat(settings.requestTimeout())
        .isEqualTo(Duration.ofSeconds(30));
```

This additionally verifies converting text from Config Data into Java types, rather than merely reading strings from `Environment`.

## 21. Common mistakes

### 21.1. Mistaking `on-profile` for an active profile command

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

It **does not enable** `prod`. If no profile is passed or no other mechanism activates it, the document may be skipped.

**Fix:** supply `spring.profiles.active=prod` from a valid source, typically the deployment environment.

### 21.2. Putting `spring.profiles.active` in an `on-profile` document

Example:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod
```

This configuration violates modern Spring Boot Config Data restrictions.

**Fix:** move the property specifying active profiles to a non-profile-specific document or external startup configuration.

### 21.3. Forgetting the `---` separator

```yaml
app:
  mode: standard

spring:
  config:
    activate:
      on-profile: dev
```

Without a separator, all keys sit in **the same document**, including `app.mode=standard`. When that document is conditioned on `dev`, the "shared" config can be skipped outside dev.

**Fix:** use `---` to separate the shared document from the dev-only document.

### 21.4. Wrong YAML indentation

Wrong:

```yaml
spring:
  config:
  activate:
    on-profile: dev
```

`activate` is not nested under `config` as intended.

Right:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

### 21.5. Not quoting expressions starting with `!`

Do not write:

```yaml
spring:
  config:
    activate:
      on-profile: !prod
```

The `!` character is used by YAML for tags, which can cause parser errors or different semantics.

Right:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

### 21.6. Using the wrong separator in `.properties`

Do not copy the YAML marker verbatim:

```properties
server.port=8080
---
spring.config.activate.on-profile=dev
server.port=8081
```

Replace with:

```properties
server.port=8080

#---
spring.config.activate.on-profile=dev
server.port=8081
```

### 21.7. Two documents with the same condition and overlapping keys

If two `on-profile: dev` documents both declare `app.mode`, the document processed later can beat the earlier one. No error necessarily appears; configuration simply uses a value from a place different from where you are looking.

**Fix:** consolidate related keys in one place or clearly document intentional override layers.

### 21.8. List configuration loses elements

The shared document has three servers, and the prod document declares only one server. After list binding, the result may retain only the server in the prod document due to list replacement.

**Fix:** if the entire list matters in prod, declare the full prod list or design a structure with custom merging rules.

### 21.9. Confusing profiles and property sources

You edit `application.yml`, yet the running process still has an environment variable or command-line argument overriding that key.

**Fix:** inspect `Environment`, Actuator, and property sources. Do not deduce values from a single file alone.

### 21.10. Putting real secrets in a production document

```yaml
spring:
  config:
    activate:
      on-profile: prod

spring:
  datasource:
    password: "real-production-secret"
```

The snippet above also has a duplicate `spring` key error in the same mapping. Even after fixing syntax, **do not** commit real passwords in configuration files.

Use:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  datasource:
    password: "${DB_PASSWORD}"
```

Secrets are provided by the deployment environment or secret manager. Using profiles is not a secret-protection mechanism.

## 22. Choosing how to organize a real project

Suppose a team develops a REST API with these requirements:

- Shared configuration: application name, default timeout, feature flags.
- Local: mock endpoints, DEBUG logs, port 8081.
- Staging: test database and API, INFO logs.
- Production: auditing enabled, INFO logs, secrets from environment.
- Cloud: enable extra metadata or infrastructure integrations.

You can choose the structure:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
```

and use an `on-profile: cloud` document inside the shared file if only a few cloud-specific properties are needed.

Or a single `application.yml` containing:

```text
Shared document
  -> on-profile: dev
  -> on-profile: staging
  -> on-profile: prod
  -> on-profile: cloud
  -> on-profile: "prod & cloud"
```

### 22.1. Principles to avoid messy configuration

1. **Put shared config in an unconditional document.** Avoid copying the same values across every profile.
2. **Every override must have a reason.** Do not use multiple documents with duplicate keys unnecessarily.
3. **Do not use profiles to store secrets.** Profiles only select configuration.
4. **Name profiles with stable meaning.** E.g., `dev`, `staging`, `prod` for environments and `cloud` for deployment capabilities.
5. **Test multi-profile combinations.** Especially when using OR, AND, NOT.
6. **Have tests for critical configuration.** Check endpoints, timeouts, and environment business flags.
7. **Keep the same artifact across environments.** Pass profiles, secrets, and deployment config externally.

### 22.2. When should you split into separate files?

Split into `application-prod.yml` if production has dozens of dedicated properties, or when operations teams need to review production changes independently.

Keep multi-document if only a few values differ and comparing them in one file reduces overhead.

## 23. Comprehensive multi-document configuration example

Create an ordering application using:

```text
src/main/resources/application.yml
```

Contents:

```yaml
spring:
  application:
    name: order-api

server:
  port: 8080

app:
  order:
    mode: normal
    max-items: 20
    timeout: 10s
    regions:
      - HCM
      - HN

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

logging:
  level:
    com.example.orders: DEBUG

app:
  order:
    mode: demo
    timeout: 30s

---
spring:
  config:
    activate:
      on-profile: staging

server:
  port: 8082

app:
  order:
    mode: preproduction
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  order:
    mode: live
    max-items: 50
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  order:
    regions:
      - HCM
      - DN
```

### 23.1. Case `dev`

Run:

```bash
java -jar order-api.jar --spring.profiles.active=dev
```

If not overridden by another source:

```text
server.port=8081
app.order.mode=demo
app.order.max-items=20
app.order.timeout=30s
app.order.regions=[HCM, HN]
```

### 23.2. Case `prod`

Run:

```bash
java -jar order-api.jar --spring.profiles.active=prod
```

Values:

```text
server.port=8080
app.order.mode=live
app.order.max-items=50
app.order.timeout=3s
app.order.regions=[HCM, HN]
```

### 23.3. Case `prod,cloud`

Run:

```bash
java -jar order-api.jar --spring.profiles.active=prod,cloud
```

The final document matches and replaces the regions list:

```text
server.port=8080
app.order.mode=live
app.order.max-items=50
app.order.timeout=3s
app.order.regions=[HCM, DN]
```

### 23.4. Java model

```java
package com.example.orders.config;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.order")
public record OrderProperties(
        String mode,
        int maxItems,
        Duration timeout,
        List<String> regions
) {
}
```

This bean can be registered via `@ConfigurationPropertiesScan` in a Spring Boot application. Regardless of which document matches, Java code receives a single typed model.

### 23.5. Endpoint illustrating effective values

```java
package com.example.orders.web;

import com.example.orders.config.OrderProperties;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigDemoController {

    private final OrderProperties properties;

    public ConfigDemoController(OrderProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/demo/config")
    public Map<String, Object> configuration() {
        return Map.of(
                "mode", properties.mode(),
                "maxItems", properties.maxItems(),
                "timeout", properties.timeout().toString(),
                "regions", properties.regions()
        );
    }
}
```

This endpoint should only be used for practice exercises with non-sensitive data. Never build a public endpoint returning an entire configuration object if the object contains passwords, API keys, or internal infrastructure details.

## 24. Practice exercises

### Exercise 1 — Splitting dev and prod documents

Given the configuration:

```yaml
server:
  port: 8080
app:
  feature:
    enabled: false
```

Add a `dev` document overriding port to 8081 and enabling the feature; add a `prod` document keeping port 8080 while enabling the feature. Use `spring.config.activate.on-profile` in the right place.

### Exercise 2 — Rewriting in `.properties`

Convert Exercise 1 to `application.properties` using the `#---` marker. Verify each section has the needed keys and explain why a standalone `---` is not `.properties` separator syntax.

### Exercise 3 — Evaluating profile expressions

Given:

```yaml
spring:
  config:
    activate:
      on-profile: "(dev | staging) & cloud"
```

Evaluate the outcome for:

- `dev`
- `staging,cloud`
- `prod,cloud`
- `dev,cloud`
- `dev,prod,cloud`

Then write an expression for "every environment without prod" and explain why `!prod` must be quoted in YAML.

### Exercise 4 — Analyzing document order

A file has three documents:

```yaml
app:
  mode: base

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: debug

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: local
```

Predict `app.mode` when `dev` is active and there are no other override sources. Why? Swap the order of the two dev documents and predict again.

### Exercise 5 — Spotting invalid declarations

Inspect:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: audit
```

Explain why `spring.profiles.include` should not be placed inside a profile-conditional document. Fix it by moving the include or group into an appropriate non-profile-specific document.

### Exercise 6 — Multi-profile configuration

Create:

- A shared document with `app.metrics.enabled=false`.
- A `prod` document enabling metrics.
- A `cloud` document defining the metrics endpoint.
- A `"prod & cloud"` document defining batch size.

Run with `prod`, `cloud`, and `prod,cloud`. Record the properties appearing in each case.

### Exercise 7 — Lists do not append

The shared document has:

```yaml
app:
  nodes:
    - node-a
    - node-b
```

The prod document has:

```yaml
app:
  nodes:
    - node-prod
```

Bind to `List<String>` and check the result with the prod profile. Why should you not expect the list to contain all three nodes?

### Exercise 8 — Default profile

Create a document:

```yaml
spring:
  config:
    activate:
      on-profile: default
```

and add `app.mode=local-default`. Start without passing an active profile, then run with `--spring.profiles.active=dev`.

Compare the results and distinguish a `default` document from an unconditional document.

### Exercise 9 — Verifying with tests

Write two tests:

```java
@SpringBootTest
@ActiveProfiles("dev")
class DevConfigTest {
}
```

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProdConfigTest {
}
```

Inject `Environment` or a configuration properties bean to verify matching timeouts and modes. When tests fail, inspect profiles, document separators, and higher-precedence configuration sources.

### Exercise 10 — Choosing file organization

One application has three profiles and each differs by only five properties. Another application has six environments, many secrets, and over a hundred environment-specific properties. Propose whether to use multi-document or separate files, citing reviewability, complexity, and secret protection.

## 25. Summary

`spring.config.activate.on-profile` **does not activate a profile**; it **conditions the loading of a configuration document** based on already-determined profiles. Spring Boot supports multi-document YAML with `---` and multi-document `.properties` with markers like `#---`.

Within one file, an effective document appearing later can override keys in an earlier document. However, broader Config Data precedence, environment variables, command-line arguments, and other sources also apply. For lists bound from multiple sources, remember that a higher-precedence source usually replaces the entire list rather than appending elements.

Properties that determine the active profile set itself—such as `spring.profiles.active`, `spring.profiles.include`, and profile groups—must be placed in a **non-profile-specific document**, not inside a document that already has `on-profile` or a profile-specific file.

When designing environment-based configuration, use a shared document for defaults, override only keys that need to change, write clear profile expressions, never put real secrets in files, and verify final configuration via `Environment`, configuration properties, and tests. Understanding the relationship between **active profiles**, **profile-specific files**, and **profile-activated documents** makes Spring Boot applications easier to deploy, diagnose, and keep consistent across environments.
