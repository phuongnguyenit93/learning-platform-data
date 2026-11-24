# Designing Profiles for Deployment Needs and Avoiding Unmanageable Combinations

In Spring Boot, **profiles** are a mechanism for selecting configuration and components suited to a runtime context. An application may need to connect to a local database during development, use test infrastructure in staging, and integrate with live services in production. Profiles help describe those differences without editing source code for every deployment.

However, profiles are very easy to overuse. When a project has many independent dimensions—environment, geographic region, cloud provider, features, database engine, logging level, customer tier—creating a profile for every combination causes the number of cases to understand and test to grow rapidly. Conversely, enabling too many profiles simultaneously can make the final configuration depend on precedence orders the team no longer controls clearly.

The goal of this article is to design profiles around **real deployment needs**, using a small count with clear conventions, and separating ordinary parameters from structural application decisions.

## 1. What do profiles actually decide?

Spring profiles serve two common effects:

1. **Selecting configuration** from files or conditional documents, such as `application-dev.yml`, `application-prod.yml`, or YAML documents with `spring.config.activate.on-profile`.
2. **Selecting beans** managed by the Spring container via `@Profile`, such as creating a mock email sender locally while using a real adapter in deployed environments.

Example:

~~~yaml
# application.yml — common configuration
app:
  name: "order-service"
  reporting:
    enabled: false
    timeout: 3s

server:
  port: 8080
~~~

~~~yaml
# application-dev.yml — only differences needed for dev
logging:
  level:
    com.example.orders: DEBUG

app:
  reporting:
    timeout: 1s
~~~

~~~yaml
# application-prod.yml — only differences for production
app:
  reporting:
    enabled: true
    timeout: 5s
~~~

When `dev` is activated, Spring Boot loads configuration corresponding to that profile. When `prod` is activated, production configuration is evaluated according to Config Data rules and property source precedence.

**Profiles do not produce a different application binary.** The application still uses the same artifact; what differs are configuration sources and conditional beans. A good goal is maintaining a single build deployable anywhere with transparent configuration.

Profiles are also **not a place to store business state**. Order status, per-customer feature toggles, or transaction-varying limits should use appropriate business mechanisms.

## 2. Questions to answer before creating a profile

Do not start with a list of `dev`, `test`, `stage`, `prod` assuming every system automatically needs all four profiles. Ask first:

- In **which contexts** is the application deployed? Local workstation, CI, integration environment, staging, production, or other contexts?
- In each context, **what actually needs to change**? Endpoints, database connections, observability, logging levels, a specific implementation, or only a few values?
- Is that difference **a property of the deployment** or runtime state that varies per request or per user?
- Does the change require **selecting a different bean** or merely the same bean with different property values?
- Which settings are **mandatory** for that environment to run safely?
- Who owns changing it: developers, the deployment pipeline, operations, or end users?

If you only need to change a URL or timeout, adding a new profile is usually unnecessary. An externalized configuration source, environment variable, or override value in the deployment system solves it better.

If the same application genuinely needs two distinct topologies—for example, local uses a fake email sender while production uses a real SMTP gateway—a profile can cleanly express that component difference.

## 3. Distinguishing three categories of decisions

To avoid creating too many profiles, classify differences by meaning:

| Category of difference | Example | Usually appropriate representation |
| --- | --- | --- |
| **Deployment context** | local, CI test, staging, production | A few stable, clearly named profiles |
| **Operational parameters** | JDBC URL, timeout, connection pool, log level | Externalized configuration, secret sources / environment variables |
| **Feature/business decisions** | Per-customer feature toggles, A/B testing, plan limits | Feature flags, policies, or business data; never one profile per customer |

Overlap can exist. For instance, `app.mail.enabled=false` is a configuration parameter; the mail-sending bean can be selected via `@ConditionalOnProperty`. If you want to swap the entire implementation for local, `@Profile("local")` can make sense. What matters is that profiles reflect **a stable runtime context**, not an arbitrary combination of every property.

Example of a design that quickly becomes unmanageable:

~~~text
dev-mysql-debug
dev-postgres-debug
dev-postgres-no-mail
stage-postgres-real-mail
prod-postgres-real-mail
prod-postgres-no-mail
prod-postgres-real-mail-eu
prod-postgres-real-mail-us
...
~~~

With 4 environments × 2 databases × 2 email states × 3 regions, you already have **48 theoretical combinations**, before even counting observability and retries. Never encode all those combinations into profile names.

A cleaner design:

~~~text
Primary profile: local | test | staging | prod
Separate properties: datasource.url, mail.enabled, region, log level, retry
Conditional beans: select adapter only when genuinely needed
Deployment config: supply concrete values per deployment
~~~

## 4. Keep the number of profiles small and meaningful

An initial profile set might include:

| Profile | Typical role | Notable characteristics |
| --- | --- | --- |
| `local` | Running on a developer's machine | Test endpoints, developer conveniences, may use mock adapters |
| `test` | Test execution context | Isolated resources, deterministic dependencies, avoids calling real services |
| `staging` | Production-like environment | Verifies integration and deployment config before release |
| `prod` | Production | Uses real services, appropriate observability and operational policies |

This is an **example**, not a mandatory Spring Boot profile set. Some projects need only `local` and `prod`; others separate `integration-test` because CI genuinely runs a distinct topology.

Helpful conventions:

1. **One primary profile represents the deployment context** at a time, if the architecture treats environments as mutually exclusive.
2. Profile names describe durable contexts, independent of individual people or specific build versions.
3. Avoid `prod2`, `prod-new`, or `dev-john` lacking long-term meaning and lifecycle rules.
4. Small value-only differences belong in configuration; true bean differences warrant considering `@Profile`.
5. Document explicitly in pipelines or deployment manifests which environment requires which profile.

A primary profile such as `prod` **does not by itself verify the application is safe to run in production**. Secrets, validation, access control, endpoint protection, and connectivity checks still need independent design.

## 5. How are profiles activated?

Spring Boot supports the `spring.profiles.active` property to select active profiles.

Example running the application:

~~~bash
java -jar order-service.jar --spring.profiles.active=local
~~~

Or using an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

The environment variable example uses POSIX shell syntax; when using Windows PowerShell, Docker, Kubernetes, or CI, variable setup depends on the environment.

Several important points:

- Multiple profiles can be activated using a comma-separated list, such as `--spring.profiles.active=staging,metrics`. Do this only when each profile's ordering and purpose are well defined.
- The `spring.profiles.active` property is also subject to **configuration source precedence**. For instance, command-line arguments can override the corresponding value in configuration files under Spring Boot's default setup.
- When **no active profile** is specified, Spring uses the default profile named `default`, unless default settings have been changed.
- `spring.profiles.default` lets you specify the default profile set; if you want to disable the default profile in a Spring Boot-supported way, you can configure `none`.
- Do not default to `prod` in `application.yml` merely to avoid setting it in production. The runtime environment should **actively declare** the production choice; if targeting the wrong deployment environment, that condition must surface clearly.

Example deployment policy:

~~~text
Local run      -> SPRING_PROFILES_ACTIVE=local
CI integration -> SPRING_PROFILES_ACTIVE=test
Staging        -> SPRING_PROFILES_ACTIVE=staging
Production     -> SPRING_PROFILES_ACTIVE=prod
~~~

This serves as a contract between the application and the pipeline, reducing the risk of running in an unintended environment.

## 6. Organize configuration files as common first, differences second

A readable layout:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

**`application.yml` should hold common values** independent of environment, such as service name, sensible default timeouts, shared retry rules, or flags with safe defaults.

**Profile-specific files should contain only what genuinely differs.** Avoid copying the entire `application.yml` into four files and tweaking a few lines, because over time they drift apart and make it hard to tell which values actually matter.

Example common file:

~~~yaml
# application.yml
app:
  checkout:
    retry-count: 2
    timeout: 3s
  mail:
    enabled: false

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Local file:

~~~yaml
# application-local.yml
logging:
  level:
    com.example.checkout: DEBUG

app:
  checkout:
    timeout: 1s
~~~

Staging file:

~~~yaml
# application-staging.yml
app:
  checkout:
    timeout: 4s
~~~

Production file:

~~~yaml
# application-prod.yml
app:
  checkout:
    timeout: 5s
~~~

In real projects, database URLs, credentials, API keys, and sensitive endpoints should come from deployment configuration or a secrets manager. Committed files can contain **keys, safe defaults, and examples**, never live secrets.

### Avoid creating a file for every minor combination

You do not need `application-prod-eu-postgres-mail.yml` if the only goal is changing `region`, `datasource.url`, and `mail.enabled`. Supply those values from deployment configuration, while `prod` represents the general production context.

## 7. Using conditional YAML documents with `on-profile`

Besides `application-<profile>.yml` files, Spring Boot supports multiple documents inside one YAML file separated by `---` and conditioned with `spring.config.activate.on-profile`.

~~~yaml
app:
  pricing:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "local"

app:
  pricing:
    timeout: 1s

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  pricing:
    timeout: 5s
~~~

The common document applies under normal loading rules; the `on-profile: "local"` document is activated only when the profile expression matches the active profile set.

You can use profile expressions:

~~~yaml
spring:
  config:
    activate:
      on-profile: "staging | prod"
~~~

The `staging | prod` expression represents an OR condition. Spring supports appropriate profile expression syntax, including `&`, `|`, and `!` in supported contexts. Use quotes so YAML preserves the expression string and makes it clear to readers that this is a condition string.

Weighing the two styles:

- **Separate files per profile**: easy to inspect each environment's differences; suits long environment-specific configs.
- **One multi-document YAML**: convenient when each profile has only a few differing lines and viewing them side by side helps.

Avoid mixing both styles haphazardly so a single key is not scattered across places, making final sources hard to trace.

## 8. `@Profile` should select components only when topology truly differs

Spring's `@Profile` restricts registering a bean or configuration class to when a profile is active.

Example of a notification-sending interface:

~~~java
public interface NotificationSender {
    void send(String address, String message);
}
~~~

Locally, only log to avoid sending real emails:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
class LoggingNotificationSender implements NotificationSender {

    @Override
    public void send(String address, String message) {
        // Demo: record send request without sending to a live system.
    }
}
~~~

In staging and production, the application uses an SMTP adapter:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("staging | prod")
class SmtpNotificationSender implements NotificationSender {

    private final MailGateway gateway;

    SmtpNotificationSender(MailGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public void send(String address, String message) {
        gateway.send(address, message);
    }
}
~~~

`MailGateway` here is an integration-layer abstraction; it needs a concrete implementation and configuration. This example only illustrates bean selection conditions.

If it is simply **the same SMTP client with a different URL between staging and prod**, you usually do not need two `@Profile` classes; use one bean and supply the URL from externalized configuration.

Watch out for:

- Two implementations registered simultaneously can cause ambiguity when injecting by interface if there is no qualifier, primary, or other disambiguation.
- Zero implementations registered can cause a missing-bean error at startup if a service has a required dependency.
- `@Profile("!prod")` does not mean “local only,” because it also matches `test`, `staging`, and any context where prod is inactive. When you want a narrow scope, use an explicit name like `@Profile("local")`.
- If you want to enable/disable a component based on a dedicated property, `@ConditionalOnProperty` usually expresses that intent better than a new profile.

## 9. Profile groups bundle stable configs, yet do not replace design

Spring Boot supports **profile groups** to activate a set of related profiles using one group name.

Example declared in non-profile-specific common configuration:

~~~yaml
spring:
  profiles:
    group:
      local:
        - "local-db"
        - "local-diagnostics"
      prod:
        - "prod-db"
        - "prod-observability"
~~~

When activating `local`, the group activates its corresponding members together. When activating `prod`, its member profiles activate according to profile group rules.

Auxiliary files can be organized as:

~~~text
application.yml
application-local.yml
application-local-db.yml
application-local-diagnostics.yml
application-prod.yml
application-prod-db.yml
application-prod-observability.yml
~~~

Profile groups fit when the bundled slices are **a stable configuration package** that always travels together in a given deployment style. For example, locally an in-memory database or local container always pairs with local diagnostic tools.

However, groups are not an excuse to turn every independent axis into profiles:

~~~text
region-eu, region-us, use-postgres, use-mysql,
enable-reporting, disable-reporting, debug, verbose-http ...
~~~

Arbitrarily combining profiles like these still produces unmanageable combinations. Use **properties** for ordinary configuration choices and groups for stable topology bundles.

**Declaration rule:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and `spring.profiles.group` must be declared in non-profile-specific documents, never inside `application-prod.yml` or documents with `spring.config.activate.on-profile`. Putting profile-control properties in profile-constrained documents can be rejected by Spring Boot.

## 10. Be careful with multiple active profiles and override order

Spring Boot allows multiple profiles to be active together:

~~~bash
java -jar order-service.jar --spring.profiles.active=staging,observability
~~~

This can be useful when two profiles are designed to cooperate. However, if the same key is defined in multiple sources:

~~~yaml
# application-staging.yml
app:
  client:
    timeout: 2s
~~~

~~~yaml
# application-observability.yml
app:
  client:
    timeout: 10s
~~~

then the final value depends on load order and source precedence. Across multiple profile files at the same tier, Spring Boot applies a **later profile wins** strategy for conflicting values under Config Data rules. Still, higher-precedence sources such as command-line arguments can override the outcome.

This is a poor design smell: an observability profile changing a business client's timeout.

Conventions to follow:

1. Each auxiliary profile has a **clear property scope**.
2. Avoid letting two simultaneously active profiles define the same key unless there is a concrete reason.
3. Never treat profile order as a business orchestration mechanism.
4. For critical keys, verify the final value in actual deployment configuration.
5. When conflicts arise, clarify which source owns the key instead of relying on “flipping the order until it works.”

In particular, avoid activating `dev,prod` or `staging,prod` simultaneously just to borrow a few missing properties: that blurs environment boundaries and risks mixing endpoints, secrets, or distinct beans.

## 11. `spring.profiles.include` and configuration groups

Beyond the active profiles list, Spring Boot provides `spring.profiles.include` to add profiles during configuration processing.

Example:

~~~yaml
spring:
  profiles:
    include:
      - "common-observability"
~~~

Keep in mind:

- `include` adds profiles; do not think of it simply as replacing `spring.profiles.active`.
- Activating extra profiles can pull in matching configuration files and conditional beans.
- `include` should not be placed inside profile-specific configuration documents or documents with `on-profile`.
- If a group of profiles needs to accompany only **one specific environment name**, `spring.profiles.group.<name>` usually expresses that intent better than global `include`.
- Whether using include or groups, keep the profile set small and document it.

You can choose among three options:

| Need | Solution |
| --- | --- |
| Select one deployment context | Primary active profile, e.g. `prod` |
| One deployment name always brings in a few auxiliary profiles | Profile group |
| A slice is always added to active profiles by common configuration | `spring.profiles.include`, used thoughtfully |

Many projects do not need both groups and include. If auxiliary profile files do not simplify things, keeping settings in the common file and per-environment files is easier to maintain.

## 12. Separating configuration by region, tenant, and feature

A classic example creating unmanageable combinations is **environment × region × customer × feature flag**.

Suppose a system runs across:

- 4 environments: local, test, staging, prod.
- 3 regions: APAC, EU, US.
- 2 database providers.
- 3 states of a feature.

Encoding every combination as a profile name produces **72 theoretical combinations**. Adding one more dimension multiplies the count further. Never create 72 `application-...yml` files to represent them.

Instead:

~~~yaml
app:
  deployment:
    region: "apac"
  feature:
    invoice-export-enabled: false
~~~

In practice, the pipeline can supply `APP_DEPLOYMENT_REGION` and `APP_FEATURE_INVOICE_EXPORT_ENABLED` or an environment-appropriate config source. Database provider and URL can be configured per deployment while the primary profile remains `prod`.

**Region** can affect data residency or endpoints, so it must be controlled rigorously, yet it does not automatically need to be a profile name. An important property is not automatically a profile.

**Tenant/customer** is typically application data or business policy varying per request. Do not create Spring profiles `customer-acme` and `customer-beta` to handle individual transactions, because active profiles belong to **the running instance's ApplicationContext**, not per-request state.

**Feature flags** also need separation:

- Startup flags deciding whether an entire integration is created at all: `@ConditionalOnProperty` can fit.
- Flags changeable at runtime per customer or rollout cohort: use a feature-flag service or appropriate business mechanism.
- Profiles fit when declaring the shared environment for all requests in a deployment.

## 13. Do not use profiles as a substitute for secrets management

Bad example:

~~~yaml
# application-prod.yml
payment:
  api-key: "production-secret-value"
~~~

Files in a repository should never contain real keys, even when used only in the production profile.

Instead, supply configuration from a secrets manager, environment, or deployment config tree. For instance, files can specify keys or placeholders resolved at runtime by Spring Boot, while real values stay out of source control.

What needs to be designed:

- Who has permission to read/modify secrets.
- Which environment receives which secrets.
- Which secrets are mandatory at startup.
- Rotation mechanisms and preventing secrets from being printed to logs.
- Detecting misconfiguration before serving traffic.

`prod` is just a profile name. A profile does not create a security boundary; security comes from infrastructure, permissions, and application hardening.

## 14. Do not turn profiles into business-logic controls

The following requirements usually should **not** use profiles:

- “VIP customers receive a different discount rate.”
- “Orders after 6 PM follow an approval workflow.”
- “A cohort of users tries a new feature.”
- “One tenant has a 200 req/min limit, another has 100.”
- “Pricing varies by region and effective date.”

These decisions involve data, policies, and business logic. They need appropriate storage models, update permissions, auditing, or scoped feature flags.

A singleton bean running in an application can serve many tenants. Active profiles do not change per request. Trying to use profiles to represent each tenant forces **application startup** configuration to solve a **runtime** problem.

You can use a config property such as `billing.policy-source=database` to pick the adapter that reads policies; individual customer policy data still belongs in business data sources.

## 15. Designing profiles for testing

A `test` profile is helpful if the test suite needs a stable topology, such as an embedded database or external API stubs.

Example in a Spring Boot test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class CheckoutApplicationTests {

    @Test
    void contextLoads() {
        // Verify ApplicationContext starts in the test context.
    }
}
~~~

`@ActiveProfiles("test")` comes from Spring Test and selects the profile for the test's context. However:

- A pure unit test that does not start the Spring container usually **needs no profile**.
- Integration tests can use `@DynamicPropertySource`, Testcontainers, or test-specific properties to supply endpoints and credentials of real resources spun up for tests.
- Do not add `test-postgres-debug-local-external-api` just for one test class.
- When testing bean-creation conditions, intentionally test different active profiles.
- Ensure tests never accidentally call production endpoints or use real secrets.

A test configuration can be minimal:

~~~yaml
# application-test.yml
app:
  notification:
    enabled: false
  checkout:
    retry-count: 0
~~~

For integration tests requiring databases, real endpoints should come from the test harness. What matters is isolating side effects and keeping tests repeatable, not inventing many profile combinations.

## 16. A compact, verifiable deployment matrix

Instead of letting each team guess which profiles to enable, write down a configuration contract. Example:

| Context | Primary active profile | Additional config sources | Bean differences |
| --- | --- | --- | --- |
| Local workstation | `local` | Personal override files, env vars | May use fake sender |
| CI integration | `test` | Testcontainers, CI variables | Stubs / test resources |
| Staging | `staging` | Deployment config, staging secrets | Real adapter with staging endpoint |
| Production | `prod` | Deployment config, production secrets | Real adapter with production endpoint |

Each row needs an owner and a verification method. This is a **deployment matrix**, not a matrix of every combination of region, feature, database, and tenant.

Practical requirements to state clearly:

1. **One place specifying active profiles**: such as deployment manifests or CI/CD environment variables.
2. **Common file stores only shared values**: avoid duplication.
3. **Critical properties have clear source ownership**: e.g., URLs from deployment config, secrets from secrets manager.
4. **Restrict allowed profile combinations**: e.g., never allow `local` and `prod` together.
5. **Verify startup with realistic config**: catch missing properties, wrong profiles, and binding/validation errors early.
6. **Ensure reproducibility**: the same artifact version with the same input configuration must behave consistently at startup.

For multi-component deployments, you can automatically check that active profiles belong to the approved set for that environment. You do not need dozens of new profiles to enforce that rule.

## 17. Verifying final configuration and resolving conflicts

When an application has many property sources (common file, profile files, config imports, environment variables, command line), final configuration is not simply “take the file matching the profile.”

Helpful verification steps:

- Inspect startup logs to verify active profiles.
- Read actual manifests/pipelines to confirm `SPRING_PROFILES_ACTIVE` and supplied config sources.
- Use test contexts or staging environments to verify the right beans are registered.
- Spring Boot Actuator `/actuator/env` or `/actuator/configprops` can be used when configured and **properly access-controlled**; these endpoints can touch sensitive configuration and must never be exposed publicly without care.
- Enable `@ConfigurationProperties` binding/validation checks to fail fast when critical config is missing.

For example, suppose a system has:

~~~yaml
# application.yml
app:
  integration:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  integration:
    timeout: 5s
~~~

Yet the deployment passes the corresponding value via environment or command line with higher precedence. The effective timeout can differ from 5s. Always inspect **the final winning source**, rather than relying solely on filenames.

If two profiles are active simultaneously and both declare the same key, improve the design so each key has clear ownership. Shuffling profile order until the app runs only treats the symptom.

## 18. Common design mistakes

### 18.1. Creating a personal profile for every developer

~~~text
dev-phuong
dev-linh
dev-minh
~~~

Hard to keep in sync, easy to commit personal machine paths, and creates unnecessary variants. Use one shared `local` profile with personal non-committed override sources containing no secrets in the repository.

### 18.2. Using a profile to toggle one small flag

~~~text
prod-with-report
prod-without-report
~~~

If it is just a configuration flag, prefer `app.reporting.enabled`. Consider `@ConditionalOnProperty` if the flag controls whether a bean is created. Create a new profile only when it represents a stable topology with deployment meaning.

### 18.3. Copying the entire config file for each environment

Four nearly identical files of hundreds of lines cause default updates to be missed. Move shared configuration into `application.yml` and keep only differences in each profile file.

### 18.4. Running both `dev` and `prod` simultaneously

~~~bash
java -jar app.jar --spring.profiles.active=dev,prod
~~~

Properties and beans can get mixed according to load order. If a property is missing in production, supply it from the proper source rather than enabling `dev` to “borrow” values.

### 18.5. Treating profiles as an authorization mechanism

`@Profile("prod")` is not an authorization or secret-access check. A misconfigured runtime can still boot with an unintended profile. Endpoint access, credentials, and data must be protected independently.

### 18.6. Placing `active`/`group`/`include` in the wrong place

Example to avoid:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod"
  profiles:
    active: "extra"
~~~

Properties used to decide active profiles such as `spring.profiles.active` must not be declared inside a document active only by profile. Declare them in non-profile-specific config or control them from deployment.

### 18.7. Overusing broad negations

`@Profile("!prod")` matches everything without prod, including unintended environments. If you intend local only, declare `@Profile("local")` to reduce surprises.

### 18.8. Using profiles as per-request feature flags

A single HTTP request cannot “activate a new Spring profile” just for itself in normal usage. Profile conditions are used by Spring for context structure and bean creation; runtime per-request variation requires strategies, policies, or runtime routing.

## 19. Design exercise: profile or property?

Suppose an ordering service runs in local, CI, staging, and prod. Classify the requirements:

| Requirement | Suggested choice | Reason |
| --- | --- | --- |
| Local logs emails, staging/prod sends real emails | Profile or bean condition | Different implementation at initialization |
| Endpoint differs between staging and prod | Deployment property | Same adapter, only value differs |
| Change timeout from 3s to 5s | Property | Operational parameter |
| Enable reporting per tenant | Feature flag / business policy | Varies per tenant |
| CI uses a database started by Testcontainers | Test property injection | Endpoint generated when tests run |
| Production in EU and US | `region` property with deployment config | Avoids duplicating every profile |
| Tests must never send real emails | Test profile, stubs, and test constraints | Isolates side effects |
| Each customer has a distinct tax rate | Business data / policy | Not startup configuration |

From there you can choose the structure:

~~~text
application.yml              -> common, safe defaults
application-local.yml        -> genuine differences for local
application-test.yml         -> genuine differences for test
application-staging.yml      -> genuine differences for staging
application-prod.yml         -> genuine differences for prod

Deployment -> chooses one primary profile
           -> supplies URLs, region, credentials, secrets, technical flags
Application -> binds properties into Java types
            -> selects beans only if topology must differ
Runtime -> executes business logic per request/tenant data
~~~

### Example `@ConfigurationProperties` for shared config

~~~java
package example.orders;

import java.time.Duration;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        URI endpoint,
        Duration timeout,
        boolean enabled
) {}
~~~

Profile files can override timeout; deployments can supply endpoint. Unless different implementations are required, one service accepting `IntegrationProperties` is simpler than multiple `@Profile` services differing only by constants.

## 20. Checklist when adding or modifying a profile

Before adding a profile, ask:

1. **Is there truly a new deployment kind?** If not, try a property.
2. **Does this difference require selecting a different bean?** If only values change, avoid adding a profile.
3. **Does it risk combinatorial explosion with existing profiles?** Calculate how many combinations would multiply.
4. **Does this profile set belong to a stable group?** If yes, consider a profile group; if not, do not force grouping.
5. **Does the profile file contain only differences?** Avoid repeating common config.
6. **Are override sources understood?** Check config imports, environment variables, command line, and active profile order.
7. **Does the profile accidentally enable unintended beans or endpoints?** Try booting in every supported context.
8. **Are secrets or business data creeping into config files?** Separate them into appropriate sources.
9. **Can the profile be explained to an operator in one sentence?** If not, its name or scope may be unclear.
10. **Can the team switch environments without rebuilding the artifact?** Verify externalized configuration is used properly.

## 21. Key takeaways

Profiles express **deployment context and component selection at startup**. Keep the number of profiles small with stable names, prefer `application.yml` for shared config, put only differences in `application-<profile>.yml`, and let deployments supply operational values and secrets. Use `@Profile` when bean topology differs; use `@ConfigurationProperties` or `@ConditionalOnProperty` when varying parameters or toggling a component.

Profile groups help when a context consistently brings along a bundle of auxiliary profiles, yet they do not solve arbitrary combinations across regions, customers, databases, and feature flags. A good design is one where developers and operators **can point out which profiles are active, why they are active, and which source each final value came from**, with only a small set of cases to manage.