# Placing `active`, `default`, `include`, and `group` in Valid Documents

Spring Boot uses **profiles** to select configuration slices and beans suited to the runtime context, such as `dev`, `test`, `staging`, or `prod`. Four property groups are very easy to confuse: `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and `spring.profiles.group.*`. They all relate to which profiles are evaluated, yet **do not share the same meaning** and **cannot be declared arbitrarily in every configuration document**.

This lesson focuses on a core rule of Spring Boot Config Data: **properties that decide which profiles are activated must be placed in non-profile-specific documents, or in valid startup sources**. A document loaded only after profiles have already been decided is not an appropriate place to re-select active/default/include/group.

## 1. Four concepts to distinguish

| Property | Purpose | Example | When it takes effect |
| --- | --- | --- | --- |
| `spring.profiles.active` | Selects one or more active profiles | `dev`, `prod` | Activates the specified profiles |
| `spring.profiles.default` | Specifies the default profile when no active profile exists | `local`, `none` | Acts solely as a fallback if no active profile is present |
| `spring.profiles.include` | Appends profiles that should always accompany this config | `common`, `metrics` | Adds profiles alongside other active profiles |
| `spring.profiles.group.<name>` | Defines a group name representing multiple profiles | `production → proddb, prodmq` | When the group name is activated, its member profiles activate too |

For example, an application has `prod` for the production environment, `proddb` for production database config, `prodmq` for the message broker, and `metrics` for monitoring beans. You can set `spring.profiles.active=production` and use a **profile group** to expand `production` into the related profile set. Or configure a `common` profile that always accompanies every environment via `include`.

Although all relate to activating profiles, they answer three distinct questions:

1. **Which environment am I actively running?** — `active`.
2. **If nobody specified an environment, which one should be used?** — `default`.
3. **Beyond the main environment, are there fixed or grouped companion profiles?** — `include` and `group`.

## 2. What counts as a “valid” configuration document for these four properties?

In the modern Config Data mechanism, distinguish two kinds of documents.

**A non-profile-specific document** is evaluated without requiring any specific profile to be active beforehand. Common examples:

~~~properties
# application.properties — base section
spring.application.name=order-service
spring.profiles.active=dev
~~~

Or a base YAML document:

~~~yaml
# application.yml — base document
spring:
  application:
    name: order-service
  profiles:
    active: dev
~~~

In a base section like above, you may declare `active`, `default`, `include`, and `group` as appropriate, though in practice `active` is usually left to the deployment environment.

**A profile-specific document** is applied only after the relevant profiles have been determined. Two typical forms are:

- Profile-named files: `application-dev.properties`, `application-prod.yml`.
- Documents enabled by `spring.config.activate.on-profile=dev` or an equivalent YAML condition.

They **must not be used to declare `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, or `spring.profiles.group.*`** under Config Data rules for profile-selection properties.

Placement rules:

| Declaration location | `active` | `default` | `include` | `group.*` |
| --- | --- | --- | --- | --- |
| Base section of `application.properties` | Allowed | Allowed | Allowed | Allowed |
| Base section of `application.yml` | Allowed | Allowed | Allowed | Allowed |
| Imported non-profile-specific Config Data document | Allowed, per source precedence | Allowed | Allowed | Allowed |
| `application-dev.properties` | No | No | No | No |
| `application-prod.yml` | No | No | No | No |
| Document activated by `spring.config.activate.on-profile` | No | No | No | No |
| Command-line argument or appropriate startup source | Can be specified depending on property | Yes | Yes | Yes |

The reason for this restriction is practical: resolving profiles is a prerequisite step to **know which documents to load**. If a document effective only after `dev` is active tried to add or replace profiles at that stage, startup logic would become circular or depend unpredictably on load order.

The condition `spring.config.activate.on-profile` is not `spring.profiles.active`. One **selects a document when a profile matches**, while the other **activates profiles**. Distinguishing these two roles is the key to placing properties in the right location.

## 3. `spring.profiles.active`: selecting active profiles

`spring.profiles.active` specifies the list of profiles the application will activate. Configuring it in a base document:

~~~properties
# application.properties
spring.profiles.active=dev
~~~

Equivalent in YAML:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

You can also list multiple profiles:

~~~properties
spring.profiles.active=dev,metrics
~~~

At startup, Spring Boot uses the active profile set to evaluate profile-specific config and bean conditions. If `application-dev.yml` or `application-metrics.properties` exists in loaded Config Data locations, those documents can be evaluated.

### Activating profiles from the command line

In real deployments, one JAR is typically run across multiple environments. In that case, omit fixed active profiles from the base file and specify them at startup:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Or:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,metrics
~~~

You can use a Java system property:

~~~bash
java -Dspring.profiles.active=prod -jar order-service.jar
~~~

Or an environment variable passed to the process:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

The environment export command above uses Unix-like shell syntax. On Windows PowerShell, you can use:

~~~powershell
$env:SPRING_PROFILES_ACTIVE="prod"
java -jar order-service.jar
~~~

This example shows that active profiles are a **startup input** rather than something that must be hardcoded in source. If the same property appears in multiple sources, Spring Boot's `PropertySource` precedence decides the effective value; normally the command line can override `application.yml`.

### An example with profile-specific documents

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
~~~

Base file:

~~~yaml
# application.yml
app:
  client:
    connect-timeout: 3s
~~~

Dev file:

~~~yaml
# application-dev.yml
app:
  client:
    base-url: http://localhost:8081
    connect-timeout: 500ms
~~~

Prod file:

~~~yaml
# application-prod.yml
app:
  client:
    base-url: https://internal-api.example.test
    connect-timeout: 2s
~~~

When running `--spring.profiles.active=dev`, Spring Boot evaluates config for `dev`. When running `--spring.profiles.active=prod`, `prod` config is evaluated. **Profile-specific files hold appropriate business/operational values**, and are not used to rewrite `spring.profiles.active`.

## 4. `spring.profiles.default`: fallback when no active profile exists

Spring has the concept of **default profiles**. If you do not activate a specific profile, Spring uses the default profile; in standard setups, the default profile is named `default`.

You can choose another name in the base document:

~~~properties
# application.properties
spring.profiles.default=local
~~~

Or YAML:

~~~yaml
spring:
  profiles:
    default: local
~~~

When no active profile is specified via configuration or launch options, Spring Boot can use `local` as the default profile to evaluate related configuration and beans. For instance, `application-local.yml` can be applied via the default profile.

If running with:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

then `prod` is the selected active profile; `local` is not activated **just because** it is the value of `spring.profiles.default`. The meaning of `default` is a fallback, not “always add this profile.”

### When you do not want a default profile named `default`

Spring Boot lets you set:

~~~properties
spring.profiles.default=none
~~~

The value `none` is a configuration documented by Spring Boot to avoid using the ordinary `default` profile when no active profile is set. However, this does not eliminate all base configuration: `application.properties` or the non-profile-specific section of `application.yml` is still loaded by Config Data.

### Reading active and default from `Environment`

In Java code, the two concepts have separate APIs:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileReporter {
    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    public String describeProfiles() {
        return "active=" + Arrays.toString(environment.getActiveProfiles())
            + ", default=" + Arrays.toString(environment.getDefaultProfiles());
    }
}
~~~

`getActiveProfiles()` reflects currently active profiles. `getDefaultProfiles()` reflects default profiles. Do not conclude “no profile is used” solely because the active profile list is empty; default profiles still matter for bean conditions or profile-specific documents.

## 5. `spring.profiles.include`: adding companion profiles

Suppose a `metrics` or `common` bean group should be enabled in most runtime situations. You can use `spring.profiles.include` in the **base document**:

~~~properties
# application.properties
spring.profiles.include=common,metrics
~~~

YAML:

~~~yaml
# application.yml
spring:
  profiles:
    include:
      - common
      - metrics
~~~

If `--spring.profiles.active=dev` is also specified at startup, Spring Boot can activate `dev` together with the included profiles. `application-common.yml` or `@Profile("metrics")` beans will be evaluated when applicable.

Key distinctions:

- `active` is the primary selected profile list.
- `include` is added profiles, **not a list replacing `active`**.
- `include` should be used for broadly accompanying profile groups, rather than relying on an `application-prod.yml` document to include a profile only for `prod`.

### Mandatory placement rule for `include`

This is **invalid** in profile-specific Config Data:

~~~properties
# application-prod.properties — INVALID
spring.profiles.include=metrics
~~~

Similarly, do not declare `include` in a YAML document governed by `spring.config.activate.on-profile`:

~~~yaml
# application.yml — INVALID example
spring:
  application:
    name: order-service

---
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: metrics  # Invalid in a profile-specific document
~~~

If the true intent is “**whenever `prod` is enabled, automatically enable `metrics`**,” use a **profile group** in the base document instead of `include` inside the `prod` document.

### Why isn't `include` an ordinary override key?

`spring.profiles.include` is processed by Spring Boot while constructing active profiles. Spring Boot documentation notes that `include` is processed per `PropertySource`, unlike picking a single winning value for a regular application property. Therefore, do not design applications assuming “writing an include in a higher-precedence source will always erase all profiles included in another source.”

When you need to determine the exact profile set in a deployment, inspect all sources capable of supplying `spring.profiles.include` at startup and verify the resulting active profiles.

## 6. `spring.profiles.group`: one name representing multiple profiles

Sometimes an application needs several technical profiles that always travel with a deployment context. For instance, running production requires production database, production message broker, and production audit configuration.

Instead of requiring everyone to type:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,proddb,prodmq,prodaudit
~~~

you can define a **profile group** in the base document:

~~~properties
# application.properties — valid
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
spring.profiles.group.production[2]=prodaudit
~~~

Then activate the group name:

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

When `production` is activated, Spring Boot expands the group so `proddb`, `prodmq`, and `prodaudit` are evaluated as well. The group name here is `production`; it does not have to equal `prod`.

In YAML:

~~~yaml
# application.yml — base section
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - prodaudit
~~~

The pattern above can work with configuration files:

~~~text
src/main/resources/
  application.yml
  application-proddb.yml
  application-prodmq.yml
  application-prodaudit.yml
~~~

When using `--spring.profiles.active=production`, the profile-specific documents activated by the group can supply the appropriate values.

### Groups are not unconditional includes

| Scenario | Expected behavior |
| --- | --- |
| Only group `production` defined; run `--spring.profiles.active=dev` | Does not automatically activate members of `production` |
| Group `production` defined; run `--spring.profiles.active=production` | Activates members declared in the group |
| `spring.profiles.include=metrics` in base document | `metrics` is added via include, even when running other profiles |
| No active profile and `spring.profiles.default=local` set | Uses default profile per default mechanism; does not enable `production` merely because the group exists |

**A group defines a relationship between profiles; declaring a group is not an immediate activation command.** The condition for activating a group is that the group name appears in the active profile set through a valid mechanism.

### Group declaration placement

The following declaration is **invalid** if placed inside `application-prod.yml`:

~~~yaml
# application-prod.yml — WRONG PLACEMENT
spring:
  profiles:
    group:
      prod:
        - proddb
        - prodmq
~~~

`application-prod.yml` is already a profile-specific document. Move the `spring.profiles.group` block up into the base `application.yml` document, or an appropriate non-profile-specific configuration source.

## 7. Decision table: use `active`, `default`, `include`, or `group`?

| Need | Recommended mechanism | Where to place |
| --- | --- | --- |
| Run JAR in production | `spring.profiles.active=prod` | Command line, environment variable, or appropriate startup source |
| Developer machine uses local config if no active profile is specified | `spring.profiles.default=local` | Base section of Config Data |
| Every runtime context needs a shared profile | `spring.profiles.include=common` | Base section of Config Data |
| Enabling one profile also pulls in 3 technical profiles | `spring.profiles.group.production[...]` | Base section of Config Data |
| Apply timeout only when `prod` is active | `spring.config.activate.on-profile=prod` | Conditional document, containing only business/operational keys |
| Bean exists only in `prod` | `@Profile("prod")` | Bean declaration or configuration class |
| Different DB address in dev and prod | `application-dev.yml` and `application-prod.yml` | Profile-specific documents, containing operational keys |

You can combine mechanisms, while avoiding confusing profile names. For example, `prod` for the primary environment and `proddb` for infrastructure serve different roles; the group name `production` can clearly express that it is a bundle.

## 8. Complete project structure example

Suppose an application needs:

- Default to `local` when a developer passes no active profile.
- Always include `common` for shared settings.
- When running production, activate `proddb` and `prodmq`.
- Vary timeouts by environment without controlling active profiles inside profile-specific files.

Structure:

~~~text
order-service/
  src/main/resources/
    application.yml
    application-local.yml
    application-common.yml
    application-production.yml
    application-proddb.yml
    application-prodmq.yml
~~~

**Base file `application.yml` — where profile-selection properties live:**

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    default: local
    include:
      - common
    group:
      production:
        - proddb
        - prodmq

app:
  client:
    connect-timeout: 3s
    max-retries: 2
~~~

**`application-local.yml` — holds only local-specific values:**

~~~yaml
app:
  client:
    base-url: http://localhost:8090
    connect-timeout: 700ms

logging:
  level:
    com.example.orders: DEBUG
~~~

**`application-common.yml` — shared configuration:**

~~~yaml
app:
  feature:
    audit-enabled: true
~~~

**`application-production.yml` — business/operational values for the production context:**

~~~yaml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s

logging:
  level:
    com.example.orders: INFO
~~~

**`application-proddb.yml` — production database parameters:**

~~~yaml
app:
  database:
    pool-size: 20
~~~

**`application-prodmq.yml` — production message broker parameters:**

~~~yaml
app:
  messaging:
    consumers: 8
~~~

Note that in this example, `app.database.*` and `app.messaging.*` are illustrative custom properties; the application needs beans or code that actually read them. They do not alter the datasource or message broker merely by appearing in YAML.

### Case A — no active profile passed

~~~bash
java -jar order-service.jar
~~~

Because the base configuration specifies `spring.profiles.default=local`, `local` acts as default when no other active profile exists. `common` is added via include. Assuming no other source overrides them, local keys like `app.client.base-url` take values from `application-local.yml`.

### Case B — running production

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

Then `production` is activated from the command line, so the group expands to add `proddb` and `prodmq`. `common` remains an included profile. `local` is not used as a fallback because an active profile exists.

### Case C — running development while still needing `common`

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

If `application-dev.yml` exists in Config Data search paths, it is evaluated for `dev`. `common` is still included from the base document. The `production` group does not activate because that group was not requested.

## 9. Version using `application.properties` instead of YAML

The same design can be written using properties:

~~~properties
# application.properties
spring.application.name=order-service
spring.profiles.default=local
spring.profiles.include=common
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq

app.client.connect-timeout=3s
app.client.max-retries=2
~~~

Valid profile-specific files:

~~~properties
# application-production.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=2s
~~~

~~~properties
# application-proddb.properties
app.database.pool-size=20
~~~

~~~properties
# application-prodmq.properties
app.messaging.consumers=8
~~~

**Do not place the `spring.profiles.group.production[...]` block inside `application-production.properties`.** Even though the filename looks like a natural spot to “describe production,” it is evaluated only after `production` is already active. Group definitions belong to profile selection and must reside in a non-profile-specific document.

## 10. Multi-document YAML: where do conditions go?

A single YAML file can hold multiple documents separated by `---`. The first, unconditional document can define profile policies; subsequent documents contain values for a given profile:

~~~yaml
# application.yml — base document, VALID
spring:
  profiles:
    default: local
    group:
      production:
        - proddb
        - prodmq

app:
  client:
    connect-timeout: 3s

---
# Document used only when production is active
spring:
  config:
    activate:
      on-profile: production

app:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
~~~

Here, `spring.config.activate.on-profile` is a **document-loading condition**. The section below `---` does not change active/default/include/group; it only supplies operational keys when the condition holds.

### Incorrect pattern: `active` inside a conditional document

~~~yaml
# INVALID
spring:
  application:
    name: order-service

---
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: metrics
~~~

The second document is evaluated only when `dev` is active; yet it tries to declare `spring.profiles.active`, a profile-control property. Spring Boot can reject this with an error such as `InvalidConfigDataPropertyException` because this key is disallowed in profile-specific documents.

**Correct fix:** if `metrics` always accompanies every profile, use `spring.profiles.include=metrics` in the base document. If `metrics` is needed only when `dev` is active, use a group in the base document:

~~~yaml
spring:
  profiles:
    group:
      dev:
        - metrics

---
spring:
  config:
    activate:
      on-profile: dev

app:
  diagnostics:
    verbose: true
~~~

When `dev` is activated, group `dev` causes `metrics` to be evaluated. `app.diagnostics.verbose` belongs to the conditional document and remains valid.

## 11. Multi-document properties: the `#---` boundary

Spring Boot also supports multiple documents in a single `application.properties` via the special document separator `#---`:

~~~properties
# application.properties — base document
spring.profiles.default=local
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
app.client.connect-timeout=3s

#---
spring.config.activate.on-profile=production
app.client.connect-timeout=2s
app.client.base-url=https://api.example.test
~~~

The first document can determine default and group; the second document only describes values used once `production` is active.

As with YAML, do not attempt to place `spring.profiles.include`, `spring.profiles.active`, or `spring.profiles.default` in a document below `#---` if it is activated by `spring.config.activate.on-profile`.

The `#---` marker has special meaning in Spring Boot's multi-document properties mechanism; that does not mean every `java.util.Properties` reader will understand and split multiple documents. To avoid errors, use the exact document-separator syntax prescribed by Spring Boot rather than inventing arbitrary separators.

## 12. Can an imported document declare `active`/`default`/`include`/`group`?

`spring.config.import` lets you import a Config Data document from `classpath:`, `file:`, or another Spring Boot-supported location. **What matters is not just where it is imported from, but whether the imported document is profile-specific.**

Example base document:

~~~properties
# application.properties
spring.config.import=classpath:config/profile-policy.properties
~~~

Imported document:

~~~properties
# config/profile-policy.properties — non-profile-specific document
spring.profiles.default=local
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

This is an organization pattern that can be valid in Config Data: the properties are declared in a non-profile-specific document even though the file sits at an auxiliary path.

Conversely, if an import appears only inside an `on-profile: dev` document and the imported document contains `spring.profiles.active` or another profile-selection property, Spring Boot can treat that data as invalid because it belongs to a profile-specific loading chain. Do not use imports to bypass profile-specific document rules.

Distinguish this from importing a multi-document file: only the appropriate non-profile-specific portion is a valid place for profile-selection properties; portions constrained by `on-profile` remain subject to the restriction.

## 13. `@Profile` selects beans, not active profiles

The `@Profile` annotation in Spring Framework conditionally controls registration of beans or configuration classes. Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ClientTransportConfig {

    @Bean
    @Profile("dev")
    ClientTransport localTransport() {
        return new LocalClientTransport();
    }

    @Bean
    @Profile("production")
    ClientTransport productionTransport() {
        return new RemoteClientTransport();
    }
}
~~~

In this illustrative example, `ClientTransport`, `LocalClientTransport`, and `RemoteClientTransport` are application-defined types. When `production` is active, the `@Profile("production")` bean is eligible for registration.

You can use Spring profile expression syntax, such as `@Profile("production & proddb")` or `@Profile("!dev")`, when conditioning on profile combinations. Avoid creating ambiguous bean combinations: whether a bean exists should follow clear logic for all supported active profile combinations.

**Profiles sit at two separate layers:**

- `spring.profiles.active/default/include/group`: policy for constructing the profile set at startup.
- `@Profile(...)` or `spring.config.activate.on-profile`: condition checking whether a bean or document applies to the already-determined profile set.

There is no behavior where “seeing `@Profile("prod")` makes Spring automatically enable `prod`.” The annotation only checks the condition; it does not activate profile names.

## 14. Pitfalls when multiple active profiles exist

You can declare multiple profiles:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev,metrics
~~~

If both `application-dev.yml` and `application-metrics.yml` contain `app.logging.level`, the effective value is determined by Config Data precedence rules, profile order, and higher-precedence sources. Never rely on a single `@Profile` expression or one line in a file to conclude you always know which value wins.

When overriding values across multiple profiles is needed, Spring Boot supports profile ordering in Config Data; when multiple profile-specific documents define the same property, activation order can influence the winning document. However, also check which file holds the key, whether imports exist, and whether a command-line override is present.

When using the `production` group, group members contribute additional profiles to the active set. That also affects files suffixed `-proddb` or `-prodmq`. Minimize defining the same business key across multiple technical files unless there is a clear reason.

### Nested profile groups and profile names

From a design standpoint, groups should be small and functionally clear. Avoid building multi-level group graphs or cyclic relationships without a concrete requirement. Names such as `dev`, `prod`, `proddb`, and `metrics` should be documented consistently in project docs to avoid confusing “primary profiles” and “member profiles.”

## 15. Startup scenarios: `active`, `default`, `include`, and `group` combined

Suppose `application.properties` (base section) contains:

~~~properties
spring.profiles.default=local
spring.profiles.include=common
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

Scenarios:

| Startup | Primary profile | Added profiles | Key point |
| --- | --- | --- | --- |
| No `spring.profiles.active` specified | `local` via default | `common` via include | Default applies only when no active profile exists |
| `--spring.profiles.active=dev` | `dev` | `common` via include | `production` group does not open automatically |
| `--spring.profiles.active=production` | `production` | `proddb`, `prodmq` via group; `common` via include | Group expands when group name is active |
| `--spring.profiles.active=prod` | `prod` | `common` via include | Does not automatically trigger group named `production` |
| `--spring.profiles.active=production,metrics` | `production` and `metrics` | `proddb`, `prodmq`, `common` | Multiple active profiles can be combined |

This table illustrates **configuration relationships** in the example. In real deployments, use `Environment.getActiveProfiles()` to observe actual active profiles; never guess which profile a machine runs solely from hostname or directory name.

## 16. Two most common errors from invalid placement

### Error A: `active` in `application-dev.yml`

~~~yaml
# application-dev.yml — INVALID
spring:
  profiles:
    active: metrics
~~~

**Why is this invalid?** `application-dev.yml` is a profile-specific document; it is evaluated only when `dev` applies. That document cannot be used to re-specify `spring.profiles.active`.

**How to fix if `metrics` always accompanies `dev`:**

~~~yaml
# application.yml — base document
spring:
  profiles:
    group:
      dev:
        - metrics
~~~

`application-dev.yml` keeps only `dev` values:

~~~yaml
app:
  diagnostics:
    verbose: true
~~~

### Error B: `include` in an `on-profile` document

~~~yaml
# application.yml — INVALID in second document
spring:
  application:
    name: order-service

---
spring:
  config:
    activate:
      on-profile: production
  profiles:
    include: proddb
~~~

**Why is this invalid?** A document with `spring.config.activate.on-profile` is a profile-conditional document and may not declare `spring.profiles.include`.

**How to fix if `production` should bring in `proddb`:**

~~~yaml
# application.yml — VALID
spring:
  profiles:
    group:
      production:
        - proddb

---
spring:
  config:
    activate:
      on-profile: production

app:
  client:
    connect-timeout: 2s
~~~

### Error C: `default` in `application-local.properties`

~~~properties
# application-local.properties — INVALID
spring.profiles.default=local
~~~

This is also a profile-selection property. Place `spring.profiles.default=local` in `application.properties` or an appropriate startup source. Do not try to define the fallback for selecting the local file inside `application-local.properties` itself.

### Error D: `group` defined after `#---` in a profile-constrained document

~~~properties
# application.properties — INVALID in second document
spring.application.name=order-service

#---
spring.config.activate.on-profile=production
spring.profiles.group.production[0]=proddb
~~~

Even though it resides in the same physical `application.properties` file, the group line belongs to the **second logical document**, which is profile-constrained. It remains invalid. When determining allowed locations, distinguish **logical documents** from **physical files**.

## 17. Organizing profile policies for maintainability

A clean structure keeps “profile policy” at the front of the configuration pipeline and puts only “operational values” in specialized documents:

~~~text
application.yml
  ├─ spring.profiles.default
  ├─ spring.profiles.include
  ├─ spring.profiles.group.*
  └─ default operational keys

application-dev.yml
  └─ operational values for dev

application-production.yml
  └─ operational values for production

application-proddb.yml
  └─ production DB values

application-prodmq.yml
  └─ production broker values

Command line / environment
  └─ spring.profiles.active=...
~~~

Across multi-service projects, a team can adopt a consistent convention: `active` decided by the deployment environment; `default` serving developers; `include` reserved for profiles that truly always accompany every run; `group` describing mandatory components of an operational context.

When a profile name is too broad—like `production` representing both environment and infrastructure—you can split member names to avoid overlapping intent. Whatever structure you adopt, document profile meanings so operators know whether activating a group name suffices or individual members must be listed.

## 18. Workflow for reading profile-related errors

When the application fails to start or a config value changes unexpectedly:

**Step 1 — Read the error message.** If you see something like `InvalidConfigDataPropertyException` or text saying `spring.profiles.active` / `spring.profiles.include` is invalid in a profile-specific resource, check **declaration placement** first.

**Step 2 — Inspect the source containing the property.** Is the line in the top section of `application.yml`, in `application-prod.yml`, or below `---` with `on-profile`? The same physical file can have different logical documents with different validity.

**Step 3 — Identify where active profiles are set.** Check command line, system properties, environment variables, and non-profile-specific Config Data. Across sources setting `spring.profiles.active`, apply precedence rules; never assume file values always win.

**Step 4 — Check `default`.** If no user-supplied active profile exists, `spring.profiles.default` can cause a profile-specific document to apply. Do not confuse default with an always-active profile.

**Step 5 — Check `include` and `group`.** Was the group name activated? Is `include` in the base document? Do group members have matching config files or beans? Are profile spellings consistent?

**Step 6 — Check operational keys and source order.** Once the active profile set is verified, if `app.client.connect-timeout` still differs from expectations, examine precedence across Config Data files, imports, command line, and related sources.

**Step 7 — Inspect `Environment`.** Use `getActiveProfiles()` and `getDefaultProfiles()`, or properly secured configuration diagnostic tools. Never print secrets or open public endpoints just to debug profiles.

## 19. Practice exercises: valid or invalid?

### Exercise 1 — `active` in the base document

~~~properties
# application.properties
spring.profiles.active=dev
~~~

**Answer:** valid in placement. However, because active is hardcoded inside the artifact, for multi-environment deployments consider passing it via command line or environment variable.

### Exercise 2 — `active` in the `dev` file

~~~properties
# application-dev.properties
spring.profiles.active=prod
~~~

**Answer:** invalid in profile-specific Config Data. Do not use a file enabled by `dev` to re-select `prod`. Choose profiles from an appropriate startup source.

### Exercise 3 — `include` in the base file

~~~properties
# application.properties
spring.profiles.include=common,metrics
~~~

**Answer:** valid in placement. The goal is adding `common` and `metrics` alongside other active profiles.

### Exercise 4 — conditional `include`

~~~yaml
# application.yml
spring:
  application:
    name: order-service
---
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: metrics
~~~

**Answer:** invalid because `include` sits in a profile-conditionally activated document. Use a group in the base section if `metrics` should accompany `prod`.

### Exercise 5 — group defined, not activated

~~~properties
# application.properties
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

The application runs with `--spring.profiles.active=dev`. **Answer:** members of `production` do not activate automatically just because the group is defined. You must activate `production` or the member profiles via a valid source.

### Exercise 6 — `default` and `active` both present

~~~properties
# application.properties
spring.profiles.default=local
~~~

Run with:

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

**Answer:** the application has active profile `production`, so `local` is not chosen merely as default. If a valid `production` group is defined in the base document, its members are evaluated as well.

### Exercise 7 — group in the second YAML document

~~~yaml
spring:
  application:
    name: order-service
---
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    group:
      prod:
        - proddb
~~~

**Answer:** invalid. The group is declared in the second document, which has an `on-profile` condition. Move the group declaration up to the base document, keeping only values applicable to `prod` below `---`.

### Exercise 8 — properties with documents separated by `#---`

~~~properties
spring.profiles.default=local
spring.profiles.group.prod[0]=proddb

#---
spring.config.activate.on-profile=prod
app.database.pool-size=20
~~~

**Answer:** valid in placement. `default` and `group` sit in the first, non-profile-specific document; the second document contains only a conditional operational key. If `prod` is activated, `proddb` is considered; `app.database.pool-size` applies when the condition matches.

## 20. End-of-lesson summary table

| What do you want to do? | Where to place it? | Where NOT to place it? |
| --- | --- | --- |
| Specify the running profile with `active` | Startup source or base document | `application-dev.yml` / `on-profile` document |
| Set a fallback profile with `default` | Non-profile-specific base document | Profile-specific file or document |
| Add a shared profile with `include` | Non-profile-specific base document | Profile-specific file or document |
| Declare a profile group | Non-profile-specific base document | Profile-specific file or document |
| Choose operational keys for `dev` | `application-dev.yml` or `on-profile: dev` document | No need to put active policy here |
| Select beans for `prod` | `@Profile("prod")` | Do not try changing active inside the annotation |
| Inspect which profiles are actually enabled | `Environment.getActiveProfiles()` | Do not conclude from a single filename |

You can remember one practical rule: **things that change the profile set are decided in non-profile-specific documents or startup sources; things that depend on the profile set belong in profile-specific documents and bean conditions**. With this rule, `active`, `default`, `include`, and `group` each have a clear place, and `application-{profile}.yml` files focus solely on describing what changes once profiles are selected.