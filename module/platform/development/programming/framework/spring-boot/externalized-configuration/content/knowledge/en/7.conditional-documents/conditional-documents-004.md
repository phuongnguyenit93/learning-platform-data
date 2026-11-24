# Activating Documents with spring.config.activate.on-profile

## 1. Problem: one configuration file, multiple applicability conditions

In a Spring Boot application, development, testing, and production environments often require different configuration values. For example, development uses a local database, while production uses a managed server and enables monitoring features.

A familiar approach is splitting into `application-dev.yml` and `application-prod.yml`. However, sometimes you want to **keep multiple configuration groups in the same file** and apply each group only when a specific profile is active.

Spring Boot supports **conditionally activated configuration documents** via the key:

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

This means: **the document containing this declaration is activated only when the profile expression matches the current profile set**.

For example, an `application.yml` file consisting of multiple YAML documents:

```yaml
# Document 1: shared configuration
demo:
  message: "Shared configuration"
  retries: 1

---
# Document 2: applies only when the prod profile is active
spring:
  config:
    activate:
      on-profile: prod

demo:
  message: "Production configuration"
  retries: 5
```

When `prod` is not activated, the `demo.message` property comes from the shared document. When `prod` is activated, the second document also applies and can override values from the document before it.

**Distinguish this upfront:** `spring.config.activate.on-profile` is used to **check a condition and select a configuration document**. It is not a command to activate a profile itself.

## 2. What is a document, and how does it differ from a file?

A **file** such as `application.yml` can contain **one or more YAML documents**. Within the same file, each `---` separator starts a new document.

Example:

```yaml
# Document A
demo:
  mode: common

---
# Document B
spring:
  config:
    activate:
      on-profile: dev

demo:
  mode: development

---
# Document C
spring:
  config:
    activate:
      on-profile: prod

demo:
  mode: production
```

The structure above is **one physical file** containing **three configuration documents**:

| Document | Activation condition | Declared value |
| --- | --- | --- |
| A | Unconditional | `demo.mode=common` |
| B | Profile `dev` is active | `demo.mode=development` |
| C | Profile `prod` is active | `demo.mode=production` |

Documents are processed individually within the Config Data mechanism. An unconditional document applies normally; a document with `on-profile` is only evaluated when its condition matches.

In this YAML format, `---` is a **document separator**. Do not mistake it for a configuration key or a string value.

For `.properties` files, Spring Boot also supports multiple documents using a comment-style separator `#---`, though the syntax and file-writing rules differ from YAML. A dedicated Properties example appears below.

## 3. How on-profile works

Suppose `application.yml` contains one shared document and one conditional document:

```yaml
demo:
  title: "Sales Application"
  connection-timeout: 10s

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  connection-timeout: 3s
  logging-level: warn
```

When running the application:

```bash
java -jar app.jar
```

If no source activates the `prod` profile, the second document does not meet its condition. The values readable from the file above are:

```text
demo.title              = Sales Application
demo.connection-timeout = 10s
demo.logging-level      = no value in the two documents above
```

If you run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

the `prod` profile is activated; the second document is eligible to contribute properties:

```text
demo.title              = Sales Application
demo.connection-timeout = 3s
demo.logging-level      = warn
```

Explanation:

1. The shared document provides `demo.title` and the default timeout.
2. The `on-profile: prod` document takes effect only when `prod` is active.
3. When effective, a later document in the file can override matching keys from an earlier document.
4. Keys that are not overridden retain their values from the shared document, provided no higher-precedence source overrides them.

In a real application, sources such as environment variables, JVM properties, or command-line arguments can continue overriding values from Config Data. The profile condition **decides which documents participate**, while precedence order **decides which value wins when the same key appears in multiple sources**.

## 4. Ways to activate the profile checked by the condition

For the `on-profile: prod` document to apply, the `prod` profile must be present in the active profile set. There are several ways to supply active profiles.

### 4.1. Via command-line argument

```bash
java -jar app.jar --spring.profiles.active=prod
```

The argument is placed after `-jar app.jar` and is an application property.

### 4.2. Via Java system property

```bash
java -Dspring.profiles.active=prod -jar app.jar
```

The `-D...` option belongs to the JVM, so place it before `-jar`.

### 4.3. Via environment variable

Bash or POSIX-compatible shells:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

### 4.4. Via valid profile configuration

A profile-independent document can declare profile selection, for example:

```yaml
spring:
  profiles:
    active: dev
```

However, in deployment, a `spring.profiles.active` value from command-line arguments or a higher-precedence source can still replace this value.

**Do not put `spring.profiles.active` inside a document already activated by `spring.config.activate.on-profile`.** Doing so creates a circular dependency between "which profiles are active" and "which documents are allowed to set profiles", so Spring Boot restricts using profile-control properties inside profile-specific documents.

## 5. on-profile does not turn on a profile

Look at this configuration:

```yaml
demo:
  region: default

---
spring:
  config:
    activate:
      on-profile: eu

demo:
  region: europe
```

Many people read this YAML snippet and think Spring Boot automatically enables `eu` because it is mentioned in the file. In fact, `on-profile: eu` only sets **a condition for the document to be used**.

Correct interpretation:

```text
If profile eu is already active:
    the second document is activated
If profile eu is not active:
    the second document is not applied
```

Nothing in the example instructs the application to activate `eu` on its own. To actively select `eu`, use `spring.profiles.active=eu` or a profile-expansion mechanism such as `spring.profiles.include` or profile groups, depending on context.

Therefore:

| Key | Purpose |
| --- | --- |
| `spring.profiles.active` | Selects active profiles |
| `spring.profiles.include` | Adds profiles to the active profile set |
| `spring.profiles.group.*` | Defines profile groups expanded when a group profile is selected |
| `spring.config.activate.on-profile` | Specifies the condition for **a Config Data document** to be applied |

These properties are related, but not interchangeable.

## 6. Profile expressions: OR, AND, negation

`spring.config.activate.on-profile` accepts a **profile expression**, not just a simple name. Important operators include:

- `|`: OR;
- `&`: AND;
- `!`: NOT;
- parentheses to group expressions.

### 6.1. Either of two profiles

```yaml
spring:
  config:
    activate:
      on-profile: "dev | test"

demo:
  debug-tools-enabled: true
```

This document is activated when `dev` **or** `test` matches.

### 6.2. Requiring both profiles simultaneously

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"

demo:
  connection-pool-size: 40
```

The document is activated only when both `prod` **and** `cloud` are satisfied.

Example startup command:

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

In this situation, both profiles are active so the expression can match.

### 6.3. Negating a profile

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"

demo:
  diagnostics-enabled: true
```

The expression above matches when the `prod` profile is inactive according to Spring's profile expression semantics.

To express complex conditions, use parentheses:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & (aws | gcp)"

demo:
  cloud-endpoint-enabled: true
```

The condition requires `prod` together with **at least one** of `aws` or `gcp`. When combining `&` and `|`, use explicit parentheses to avoid ambiguity or expression syntax errors.

Expression strings in the examples are wrapped in YAML quotes. Double quotes are especially necessary for expressions starting with `!` because the exclamation mark has special meaning in YAML.

## 7. How are expressions evaluated?

Suppose a document uses:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & (aws | gcp)"
```

Scenarios:

| Active profiles | Condition matches? | Reason |
| --- | --- | --- |
| `prod` | No | Missing `aws` and `gcp` |
| `aws` | No | Missing `prod` |
| `prod,aws` | Yes | Has `prod` and `aws` |
| `prod,gcp` | Yes | Has `prod` and `gcp` |
| `prod,aws,gcp` | Yes | Has `prod` and at least one branch |
| `dev,aws` | No | Missing `prod` |

The purpose of the expression is to activate configuration when a **combination of states** is already present. It does not add profile names to the active set by itself.

You can use expressions to avoid duplicating configuration for the same feature across multiple environments. For instance, shared configuration for `dev` and `test` can live in a single document conditioned on `"dev | test"`.

If configuration needs to activate a set of interdependent profiles, `spring.profiles.group` is another mechanism for defining activation relationships; `on-profile` only reads the resulting active profile set.

## 8. Document order and property overrides

In a multi-document file loaded by Spring Boot via Config Data, **a later document can override values for the same keys in an earlier document**, when those documents are both activated.

Example:

```yaml
# Document 1
demo:
  mode: base
  retries: 2

---
# Document 2
spring:
  config:
    activate:
      on-profile: "dev | test"

demo:
  mode: development
  retries: 1

---
# Document 3
spring:
  config:
    activate:
      on-profile: "prod | test"

demo:
  mode: hardened
```

When running with `--spring.profiles.active=dev`:

```text
demo.mode    = development
demo.retries = 1
```

When running with `--spring.profiles.active=prod`:

```text
demo.mode    = hardened
demo.retries = 2
```

When running with `--spring.profiles.active=test`, **both document 2 and document 3** match. In this single-file example, document 3 appears later and can override `demo.mode`, while `demo.retries` retains the value from document 2:

```text
demo.mode    = hardened
demo.retries = 1
```

Do not deduce absolute precedence across all files from a document's position within one file. External configuration files outside the JAR, profile-specific files, `spring.config.import`, and sources such as environment variables and command-line arguments also participate in selecting the final value.

## 9. Comparison with application-prod.yml

The following two organizational styles often serve similar needs.

**Approach A: multiple profile-specific files**

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

The `application-prod.yml` file:

```yaml
demo:
  timeout: 5s
  audit: true
```

This file belongs to the Config Data group for the `prod` profile by filename convention.

**Approach B: one file containing multiple documents**

```yaml
# application.yml
demo:
  timeout: 30s
  audit: false

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  timeout: 5s
  audit: true
```

Approach B declares the condition directly inside the document, so the filename does not need the `-prod` suffix to express that condition.

| Aspect | Profile-specific file | `on-profile` document |
| --- | --- | --- |
| Where condition is placed | Naming convention `application-prod.yml` | Key `spring.config.activate.on-profile` |
| Organization | Split into separate files | Multiple documents in the same file |
| Multi-profile conditions | May require extra files/mechanisms | Can write expressions such as `"dev | test"` |
| Can be combined? | Yes | Yes, though source order must be understood |

Neither option is automatically superior in every project. When a configuration is large enough and belongs solely to one environment, a separate file is easy to manage. When a short set of values differs only across a few profile combinations, conditional documents help make the relationships visible in one file.

## 10. Using on-profile in application.properties

Spring Boot also supports multi-part configuration documents in Properties files. The document separator is `#---`.

Example:

```properties
# application.properties - shared document
demo.mode=default
demo.retries=2

#---
spring.config.activate.on-profile=dev
demo.mode=development
demo.retries=1

#---
spring.config.activate.on-profile=prod
demo.mode=production
demo.retries=5
```

Conditional behavior works similarly to YAML: the document containing `spring.config.activate.on-profile=prod` is applied when `prod` is active.

Distinctions:

- In YAML, `---` is the document separator.
- In Properties, Spring Boot recognizes the `#---` comment line as a separator under its own rules.
- The Properties separator must be written in exact form, with no leading whitespace and exactly three dashes. Do not accidentally write `# ----` or add spaces inside.
- This multi-document format is supported by Spring Boot's Config Data loader; do not assume every `.properties` reader library or every `@PropertySource` setup understands these separators like Spring Boot does.

Use the format your team understands best and apply it consistently.

## 11. Complete example with Java code

### 11.1. Create the configuration

Create `src/main/resources/application.yml`:

```yaml
# Shared configuration
demo:
  service: catalog
  message: "running with base config"
  retries: 2
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

demo:
  message: "running in development"
  retries: 1
  feature-enabled: true

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  message: "running in production"
  retries: 5
```

The configuration consists of three documents. The shared document has no condition; the next two are for `dev` and `prod`.

### 11.2. Write a component to inspect Environment

In a Spring Boot application with `@SpringBootApplication`, create the component:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConditionalDocumentPrinter implements ApplicationRunner {

    private final Environment environment;

    public ConditionalDocumentPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Active profiles = "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("demo.service = "
                + environment.getProperty("demo.service"));

        System.out.println("demo.message = "
                + environment.getProperty("demo.message"));

        System.out.println("demo.retries = "
                + environment.getProperty("demo.retries", Integer.class));

        System.out.println("demo.feature-enabled = "
                + environment.getProperty("demo.feature-enabled", Boolean.class));
    }
}
```

The `Environment#getProperty` methods read the effective values. Passing `Integer.class` or `Boolean.class` lets Spring convert the configuration string to the appropriate type.

### 11.3. Case without dev or prod activated

Run:

```bash
java -jar app.jar
```

If no source adds `dev` or `prod`, the values selected from these three documents are:

```text
demo.service = catalog
demo.message = running with base config
demo.retries = 2
demo.feature-enabled = false
```

No `dev` or `prod` conditional document matches.

### 11.4. The dev case

Run:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Output from the illustrative properties:

```text
demo.service = catalog
demo.message = running in development
demo.retries = 1
demo.feature-enabled = true
```

The `dev` document adds or overrides keys from the shared document.

### 11.5. The prod case

Run:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Output:

```text
demo.service = catalog
demo.message = running in production
demo.retries = 5
demo.feature-enabled = false
```

The value `demo.feature-enabled=false` comes from the shared document because the `prod` document does not declare that key.

### 11.6. Overriding with an application argument

Try:

```bash
java -jar app.jar --spring.profiles.active=prod --demo.retries=9
```

The result for `demo.retries` is `9`: command-line arguments have higher precedence than Config Data in standard Spring Boot runs. The `prod` condition still matches, but **the final value for a specific key** can come from a higher-precedence source.

This is the difference between **an activated document** and **the winning value source**.

## 12. on-profile combined with profile groups and include

In an application with many profiles, the active profile set can be expanded using `spring.profiles.include` or `spring.profiles.group.*`.

Example:

```yaml
spring:
  profiles:
    group:
      prod:
        - proddb
        - observability

---
spring:
  config:
    activate:
      on-profile: "prod & observability"

demo:
  tracing-enabled: true
```

When starting with:

```bash
java -jar app.jar --spring.profiles.active=prod
```

the `prod` group activates its member profiles, including `observability`. Consequently, the document containing the `"prod & observability"` expression can be applied.

The key point to understand is:

1. Selecting and expanding profiles is handled by the profile activation mechanism.
2. `spring.config.activate.on-profile` checks the resolved profile set.
3. Properties of matching documents then enter Config Data.

**Important restriction:** do not move `spring.profiles.group`, `spring.profiles.active`, or `spring.profiles.include` down into a document with `on-profile`. Properties that define or alter the profile set should reside in profile-independent documents according to Spring Boot's rules.

## 13. Combining profile conditions with Config Data Import

A conditional document can contain environment-dependent configuration, including declarations to load other configuration sources in cases supported by Config Data.

Example:

```yaml
demo:
  region: local

---
spring:
  config:
    activate:
      on-profile: prod
    import: "optional:file:./config/prod-overrides.properties"

demo:
  region: production
```

In this example, the second document is activated only when `prod` matches. When the document is activated, the Config Data mechanism can process its import declaration to load the additional file.

If `./config/prod-overrides.properties` exists and contains:

```properties
demo.region=external-production
```

the imported value takes precedence over the same key in the document that declared the import in that direct relationship, assuming no higher-precedence source overrides it.

If the file does not exist and the import is marked `optional:`, merely missing that resource does not force the application to fail under missing-import-location rules.

In applications with multiple documents, multiple locations, and various profiles, evaluate the entire Config Data order rather than assuming every imported file beats every other file.

## 14. Common pitfalls

### 14.1. Putting active inside an activated document

Incorrect example:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: audit
```

The document already depends on the `prod` profile yet tries to alter the active profile set. Spring Boot does not allow using `spring.profiles.active` in such a profile-specific document.

If you want `prod` to bring in `audit`, define a profile group in a profile-independent document:

```yaml
spring:
  profiles:
    group:
      prod:
        - audit
```

### 14.2. Omitting the YAML separator

Example:

```yaml
demo:
  mode: base
spring:
  config:
    activate:
      on-profile: prod
demo:
  mode: production
```

This is not a valid way to create two separate YAML documents. Repeating the root key `demo` within the same document also causes YAML parsing issues. Separate them with `---` if you want distinct shared and conditional documents.

### 14.3. Writing on-profile outside the document needing the condition

Example:

```yaml
spring:
  config:
    activate:
      on-profile: prod

demo:
  mode: production

---
demo:
  feature-enabled: true
```

Only **the document before `---`** is bound by `on-profile: prod`. The document after the separator does not automatically inherit the condition from the preceding document. If it also needs a condition, declare `on-profile` inside the second document.

### 14.4. Omitting quotes for an expression starting with an exclamation mark

In YAML, the expression:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

is the unambiguous way to represent a negated condition. If you omit quotes and start the value with `!`, YAML may interpret it as tag syntax rather than a string, causing a document parsing error.

### 14.5. Thinking an activated document always beats environment variables

If a production document sets:

```yaml
demo:
  timeout: 5s
```

but an environment variable or command-line argument provides a different value with higher precedence, the final value of `demo.timeout` might not be `5s`. Document activation conditions and source precedence order are two distinct concepts.

### 14.6. Thinking every profile must have an application-<profile>.yml file

A document with `on-profile: prod` can still reside inside the base `application.yml`. Profiles are also used by `@Profile` conditions in Spring code. Therefore, "an active profile" and "a file with a profile suffix exists" are not the same condition.

### 14.7. Assuming two unconditional documents depend on each other

Each document is evaluated with its own condition. A document without `on-profile` can apply in every run, but that does not mean the document before or after it automatically shares the same condition.

## 15. Distinguishing from @Profile in Java code

Both mechanisms rely on profiles, yet they control different targets:

| Mechanism | Target controlled | Example |
| --- | --- | --- |
| `spring.config.activate.on-profile` | A **Config Data document** | Load `demo.mode` only when `prod` matches |
| `@Profile` | A Spring Framework bean or configuration | Create a bean only when `prod` matches |

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ExternalClientConfiguration {

    @Bean
    @Profile("prod")
    public ExternalClient externalClient() {
        return new ExternalClient("https://api.example.invalid");
    }
}

class ExternalClient {
    private final String url;

    ExternalClient(String url) {
        this.url = url;
    }

    public String getUrl() {
        return url;
    }
}
```

`@Profile("prod")` conditions bean registration. A YAML document with `spring.config.activate.on-profile: prod` conditions configuration data. The same `prod` profile can make both conditions true, yet the two features have different scopes.

You do not need to create a bean just to use a conditional configuration document, and you do not need an `on-profile` document to use `@Profile`.

## 16. Observing active profiles and effective configuration

When unsure why a document is applied, check the active profiles and specific keys. Example:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileDocumentInspector implements ApplicationRunner {

    private final Environment environment;

    public ProfileDocumentInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Profiles: "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("Mode: "
                + environment.getProperty("demo.mode", "<none>"));

        System.out.println("Retries: "
                + environment.getProperty("demo.retries", Integer.class));
    }
}
```

The snippet above reveals the actual profile set and the values received by the application. If values do not match expectations, check in order:

1. Was the matching profile actually activated?
2. Does the document have `---` in the right place?
3. Does the `on-profile` expression match and is it properly quoted?
4. Are multiple documents activated simultaneously and overriding the same key?
5. Is there a higher-precedence Config Data file or an imported file?
6. Is a command-line argument, environment variable, or JVM property overriding it?

In controlled environments, Spring Boot Actuator `env` can also help inspect property sources when the endpoint is configured to allow access. Inspect only non-sensitive keys and protect deployment configuration details.

## 17. Self-check exercises

Given `application.yml`:

```yaml
# Document 1
app:
  name: example
  message: base
  retries: 2
  metrics: false

---
# Document 2
spring:
  config:
    activate:
      on-profile: "dev | test"

app:
  message: non-production
  metrics: true

---
# Document 3
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  message: production-cloud
  retries: 7

---
# Document 4
spring:
  config:
    activate:
      on-profile: "!prod"

app:
  retries: 1
```

Assume no other configuration sources override these. Determine which properties take effect in three scenarios.

### Scenario A: dev only

```bash
java -jar app.jar --spring.profiles.active=dev
```

Documents 1, 2, and 4 match. Expected values:

```text
app.name    = example
app.message = non-production
app.retries = 1
app.metrics = true
```

Explanation: document 2 changes `message` and `metrics`; document 4 appears later and overrides `retries`.

### Scenario B: prod and cloud

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Documents 1 and 3 match. Document 2 does not match, and document 4 does not match because `prod` is active.

```text
app.name    = example
app.message = production-cloud
app.retries = 7
app.metrics = false
```

### Scenario C: prod only

```bash
java -jar app.jar --spring.profiles.active=prod
```

Document 3 does not match because `cloud` is missing; document 4 does not match because `prod` is active. Document 1 provides the values:

```text
app.name    = example
app.message = base
app.retries = 2
app.metrics = false
```

Try replacing document 3's expression with `"prod | cloud"` and re-deriving the result: with an OR expression, having just one of the two profiles active is enough for the document to be activated.

## 18. Key takeaways

- `spring.config.activate.on-profile` is **an activation condition for a Config Data document**, not a property that activates profiles on its own.
- In YAML, separate documents with `---`. Each document can have its own condition.
- The `on-profile` value can be a profile name or an expression with `!`, `&`, `|`, and parentheses; wrap expressions in quoted strings to avoid YAML syntax errors.
- Documents whose conditions are not satisfied contribute no properties; activated documents enter the Config Data precedence order.
- Within a single multi-document file, a matching document appearing later can override overlapping keys in an earlier document.
- Do not declare `spring.profiles.active`, `spring.profiles.include`, or profile groups inside a document already constrained by `on-profile`.
- Distinguish `spring.config.activate.on-profile` from `application-prod.yml` files, from `@Profile` on beans, and from `spring.profiles.active`.
- For diagnostics, check actual profiles with `Environment#getActiveProfiles()` and inspect individual values with `Environment#getProperty()`.
