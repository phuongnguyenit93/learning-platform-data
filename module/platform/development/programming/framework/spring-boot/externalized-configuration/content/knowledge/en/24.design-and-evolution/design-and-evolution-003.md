# Avoiding Full Configuration Duplication Across Profiles

In Spring Boot Externalized Configuration, `application.yml` and profile-specific files such as `application-dev.yml`, `application-staging.yml`, and `application-prod.yml` allow the same artifact to run in multiple environments. Yet as a project grows, a common design mistake appears: **copying the entire `application.yml` into every profile-specific file**, then editing just a few values. At first this looks easy to read, but over time it creates multiple copies that are hard to keep in sync.

Imagine an application with over 100 properties, of which only about 10 differ across development, staging, and production. If you copy all 100 properties into three files, you end up maintaining 300 lines of configuration instead of one base set plus a few deltas. When a timeout, key name, nested structure, or default policy changes, one file can easily be missed, causing environments to drift into different behaviors without anyone intentionally designing it.

The goal is not to eliminate all environment differences. The goal is to **declare only intentional differences** and keep shared settings in **one clear source of truth**. This lesson presents Spring Boot's DRY (Don't Repeat Yourself) approach to organizing configuration, distinguishing override from merge, handling lists and maps, profile groups, Config Data imports, secrets, validation, testing, and step-by-step refactoring of systems with duplicated files.

Examples target Spring Boot 3.x and Java 17+. Profile syntax, Config Data, and precedence order should be verified against your project's actual Spring Boot version.

## 1. The Problem: Every Profile Is a Full Copy of the Configuration

Example initial structure:

~~~text
src/main/resources/
  application-dev.yml
  application-staging.yml
  application-prod.yml
~~~

Development file:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    connect-timeout: 1s
    read-timeout: 3s
    max-retries: 2
  retry:
    backoff: 250ms
    enabled: true
  feature:
    new-checkout: true
~~~

Production file:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    connect-timeout: 3s
    read-timeout: 10s
    max-retries: 2
  retry:
    backoff: 250ms
    enabled: true
  feature:
    new-checkout: false
~~~

`spring.application.name`, `server.port`, `max-retries`, `retry.backoff`, and `retry.enabled` are copied even though their values are identical. When changing a shared setting like `max-retries` from 2 to 3, developers must remember to edit every file. Missing one file produces **configuration drift**.

Main drawbacks of full-copy profiles:

- **Duplicate data:** a single fact is stored in multiple places.
- **Drift-prone:** changes must be synchronized manually.
- **Hard to review:** in pull requests, reviewers cannot tell which lines genuinely vary by environment.
- **Hard to evolve:** renaming keys or restructuring nested objects requires updating many files.
- **Hard to test:** bloated files can hide accidental overrides.
- **Secret exposure risk:** developers may copy passwords or API keys into the production file and commit them.
- **Hard to roll back:** rolling back one profile may accidentally revert unrelated settings.

Core solution: **shared configuration lives in `application.yml`; profile files contain only the differences**.

## 2. Target Design: Base Configuration + Profile-Specific Delta

Recommended structure for a simple application:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-staging.yml
  application-prod.yml
~~~

Base file:

~~~yaml
# application.yml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 2
  retry:
    backoff: 250ms
    enabled: true
  feature:
    new-checkout: false
~~~

Development file:

~~~yaml
# application-dev.yml
app:
  client:
    connect-timeout: 1s
    read-timeout: 3s
  feature:
    new-checkout: true
~~~

Staging file:

~~~yaml
# application-staging.yml
app:
  client:
    read-timeout: 7s
~~~

Production file:

~~~yaml
# application-prod.yml
app:
  client:
    connect-timeout: 3s
    read-timeout: 10s
~~~

Notice: profile files do not redeclare `spring.application.name`, `server.port`, or `max-retries` because they do not differ from the base.

When `prod` is active and no higher-precedence source overrides them:

~~~text
spring.application.name = order-service
server.port             = 8080
app.client.max-retries  = 2
app.client.connect-timeout = 3s
app.client.read-timeout = 10s
app.retry.backoff       = 250ms
app.feature.new-checkout = false
~~~

**You do not need to copy the entire `app.client` block just to change one field.** For ordinary scalar/nested objects, non-overridden keys continue to come from the base configuration, following Config Data precedence rules.

## 3. What Does the "Delta-Only" Principle Mean?

A **delta** is the set of values that **differ** from the default configuration path, not a copy duplicated so readers can see the whole object again.

For example, a service uses:

~~~yaml
# application.yml
app:
  invoice:
    currency: VND
    rounding-scale: 2
    retry-count: 3
    timeout: 5s
~~~

In production, if only `timeout` needs to be 12 seconds:

~~~yaml
# application-prod.yml
app:
  invoice:
    timeout: 12s
~~~

No need to repeat `currency`, `rounding-scale`, or `retry-count`.

A rule of thumb for placing properties:

| Question | Where to Place |
| --- | --- |
| Is the value identical in all environments? | Base `application.yml` |
| Does the value vary only by profile? | `application-{profile}.yml` |
| Does the value depend on deployment infra/region/tenant? | External Config Data outside JAR, env, or managed config store |
| Is the value a password/token/private key? | Secret manager/secret mount/runtime channel |
| Is the value required with no safe default? | Do not hardcode; use validation/fail-fast |
| Must the value change frequently at deploy time? | Versioned deployment source with change control |
| Is a config block shared across multiple services? | Controlled shared Config Data / central config contract |

**The base file does not have to contain every key.** Required deployment-supplied properties can be completely absent from the repository. The base holds only safe defaults and shared policies that truly belong to the artifact.

## 4. How Spring Boot Reads Profile-Specific Files

Spring Boot supports Config Data from files such as:

~~~text
application.properties
application.yml
application-dev.properties
application-dev.yml
application-prod.properties
application-prod.yml
~~~

Base documents can be loaded alongside activated profile documents. Profile-specific values typically override matching keys from the base file within the corresponding Config Data group. In addition, higher-precedence sources exist, such as command-line arguments, JVM system properties, and OS environment variables.

For example:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

or via an environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

When the `prod` profile is selected, Spring Boot evaluates `prod` configuration alongside other sources by precedence. **Simply having `application-prod.yml` on disk does not mean it is loaded**; active/default profiles and locations must match.

Keep in mind:

- **Active profiles** determine which profile-specific documents can participate.
- **Default profiles** apply when no profiles are active.
- A file containing a key **is not necessarily the winning source** if a higher-precedence source also provides that key.
- A key in a profile file **is not** the final value when CLI or env overrides it.
- Multiple active profiles must be understood through ordering and Config Data rules, not treated as an unconditional deep-merge of three YAML trees.

## 5. Do Not Put spring.profiles.active Inside Profile-Specific Files

An anti-pattern:

~~~yaml
# application-prod.yml - should not be used to activate prod itself
spring:
  profiles:
    active: prod
~~~

The idea of "the prod file activating prod" is circular: profile-specific files are chosen **after** Spring determines active profiles by its rules. Spring Boot restricts `spring.profiles.active`, `spring.profiles.include`, and profile group configuration inside profile-specific documents or documents with `spring.config.activate.on-profile`.

Place profile activation in an early enough source, such as:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Or at the deployment level:

~~~yaml
services:
  api:
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
~~~

The Compose example above merely passes runtime environment variables; do not equate **Docker Compose profiles** with **Spring profiles**. `docker compose --profile debug` controls which services start—it does not set `spring.profiles.active=debug`.

Be cautious about hardcoding `spring.profiles.active` in the base `application.yml`: an artifact shared across environments should normally let runtime/deployment choose the profile rather than silently defaulting to production or development.

## 6. YAML Is Not Arbitrarily Deep-Merged

This is the single most important point when refactoring: **do not assume Spring Boot "merges all YAML files into one object and deep-merges everything"**.

Spring Boot resolves properties by key name and `PropertySource` precedence. Binding a Java object depends on:

- How YAML is flattened into property paths.
- The Java target type.
- Whether the target is a scalar, nested object, list, or map.
- Which source provides each key.
- Converters, constructor binding, and defaults.
- Source mechanisms that may replace whole collections.

For scalars:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
    max-retries: 3
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 10s
~~~

the result is normally `timeout=10s` and `max-retries=3` assuming no higher override exists.

With lists, however, **if a higher-precedence source supplies a list, the entire list is normally replaced rather than element-wise deep-merged with a lower-precedence source**. Maps may aggregate entries by key, where duplicate keys are overridden by the higher-precedence source. Do not apply the same reasoning to both collection types.

## 7. Scalars: Override the Exact Key and Keep the Rest

Typed configuration example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
    Duration connectTimeout,
    Duration readTimeout,
    int maxRetries,
    boolean retryEnabled
) {}
~~~

Base:

~~~yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 3
    retry-enabled: true
~~~

Production delta:

~~~yaml
app:
  http:
    read-timeout: 12s
~~~

With `prod` active and no higher source:

~~~text
connectTimeout = 2s
readTimeout    = 12s
maxRetries     = 3
retryEnabled   = true
~~~

There is no need to redeclare the 3 unchanged values in the prod file. When adding a new field to the record, you can place a suitable default in the base or via `@DefaultValue`, rather than opening three profile files just to copy values.

**Note:** if code uses `@Value` with placeholder defaults or getters with manual fallbacks, consumers can incur logic outside Config Data. Keeping files DRY does not guarantee all consumers see the exact same defaults if code design is inconsistent.

## 8. Nested Objects: Organize by Responsibility Group

Configurations often have nested groups:

~~~yaml
app:
  notifications:
    mail:
      enabled: true
      retries: 2
      timeout: 3s
    webhook:
      enabled: true
      retries: 1
      timeout: 5s
~~~

If development only disables webhooks:

~~~yaml
# application-dev.yml
app:
  notifications:
    webhook:
      enabled: false
~~~

That is a crisp delta. Copying both `mail` and `webhook` blocks into development obscures what actually differs.

A record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
    Channel mail,
    Channel webhook
) {
    public record Channel(
        boolean enabled,
        int retries,
        Duration timeout
    ) {}
}
~~~

If nested fields are required, use validation rather than expecting the base to always be complete. A profile-specific file that declares only `webhook.enabled` cannot prevent failure if another required key was missing from the base.

## 9. Lists: Copy/Merge Mistakes Easily Cause Bugs

Suppose the base defines a list:

~~~yaml
# application.yml
app:
  servers:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

In `application-prod.yml`, you want primary's timeout to be 5 seconds, so you write:

~~~yaml
app:
  servers:
    - timeout: 5s
~~~

**Do not assume** the final result will be both servers from the base with primary's timeout updated. With Spring Boot list binding, a higher-precedence source normally **replaces the entire list**, rather than merging nested fields by index. This can yield a one-element list missing `name` and `url`.

The explicit way when using a list:

~~~yaml
# application-prod.yml
app:
  servers:
    - name: primary
      url: https://primary.example.test
      timeout: 5s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

Here repeating the **whole list** is technically justified. It does not violate the spirit of DRY: **do not force deduplication at the cost of breaking list-binding semantics**.

If items are identified by name and need per-item overrides, consider a `Map` structure.

## 10. Maps: Pick Identifying Keys for Intentional Overrides

Instead of a list:

~~~yaml
app:
  servers:
    - name: primary
      timeout: 2s
    - name: backup
      timeout: 4s
~~~

you can use a map:

~~~yaml
# application.yml
app:
  servers:
    primary:
      url: https://primary.example.test
      timeout: 2s
    backup:
      url: https://backup.example.test
      timeout: 4s
~~~

Production delta:

~~~yaml
# application-prod.yml
app:
  servers:
    primary:
      timeout: 5s
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ServerCatalog(
    Map<String, Server> servers
) {
    public record Server(
        URI url,
        Duration timeout
    ) {}
}
~~~

Spring Boot supports map binding by aggregating entries by key according to precedence. In many cases, `primary.timeout` from a higher source can override that field while `backup` continues to come from the base.

However, **do not treat maps as unconditional deep-merges for every shape**. Combining scalar map values, nested POJOs, dotted keys, and multiple sources has nuances; test actual binding against your target type and Boot version.

### When Should You Still Use a List?

Use a list when **element order matters**, ordered iteration is required, or external formats naturally represent a sequence. Use a map when **key identity is stable** and per-entry overrides are needed. Switching a list to a map changes the configuration contract, so review consumers and deployment docs.

## 11. A Profile-Specific File Is Not for Cloning Structure

There are two contrasting mindsets:

**Cloning approach:**

~~~text
application-dev.yml    -> entire system, all keys
application-prod.yml   -> entire system, all keys
application-test.yml   -> entire system, all keys
~~~

**Ownership-split approach:**

~~~text
application.yml         -> safe defaults and shared values
application-dev.yml     -> differences for dev
application-staging.yml -> differences for staging
application-prod.yml    -> differences for prod
runtime/secret manager  -> deployment-specific sensitive values
~~~

The benefit of the second approach is not just fewer lines. It creates **reviewable semantics**: every line in a profile-specific file states "this policy genuinely differs from the base."

When shared values change, usually only one place is edited. When environment-specific settings change, only the relevant profile file or deployment config is touched.

## 12. Place Defaults at the Right Layer

Base configuration can hold appropriate defaults:

~~~yaml
app:
  retry:
    enabled: true
    max-attempts: 3
    backoff: 250ms
~~~

In a mutable JavaBean:

~~~java
public class RetryProperties {
    private int maxAttempts = 3;
    // getter/setter...
}
~~~

In a constructor-bound record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

public record RetryProperties(
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("250ms") Duration backoff
) {}
~~~

Three places can hold defaults: base Config Data, field initializers/constructors, and `@DefaultValue`. **Avoid defining different defaults for the same key across multiple layers without reason.**

A pragmatic policy:

1. **Shared operational defaults**: place in base `application.yml`.
2. **Type-invariant defaults**: consider constructor/`@DefaultValue`.
3. **Deployment-mandated values**: do not invent fake fallbacks; fail fast when missing.
4. **Profile-specific differences**: profile files record only deltas.

If both a code default and a base default exist, document which is canonical and test missing-key behavior. Do not assume a Java default acts as a lowest-precedence `PropertySource`; it belongs to object creation/binding.

## 13. Should Values That Match Today Always Go Into Base?

Not necessarily. DRY does not mean collapsing every identical value into a single default.

For example, staging and prod may both currently have:

~~~yaml
app:
  payment:
    sandbox-mode: false
~~~

Yet by policy, **each environment must make an explicit decision** whether to call the sandbox or production payment gateway. If a wrong default could trigger unintended real transactions, requiring an explicit per-environment value or using validation is better—even if lines currently look duplicated.

A question to ask:

> If an environment forgets to declare this key tomorrow, should the application use a shared default or refuse to start?

If the answer is **refuse**, do not place a "convenience" default in the base just to cut line count. DRY should serve safety and clarity, not minimum line count.

Keys tied to billing, authentication, encryption, regulatory region, or user data typically demand more explicitness than ordinary timeouts.

## 14. Secrets Do Not Belong in Copied Profile Files

An anti-pattern:

~~~yaml
# application-prod.yml - DO NOT COMMIT REAL CREDENTIALS
spring:
  datasource:
    username: orders_app
    password: real-secret-here
~~~

There are two problems: committing passwords into the source repository and duplicating them as profiles/environments proliferate.

A better setup keeps non-secret metadata in the file:

~~~yaml
# application.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
~~~

while production supplies:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://db:5432/orders
SPRING_DATASOURCE_USERNAME=orders_app
SPRING_DATASOURCE_PASSWORD=<injected-through-secret-channel>
~~~

In this example, placeholder values are not real credentials. At runtime, secrets should come from a secret manager, file mount, or controlled channel.

**Profiles are not a security boundary.** `application-prod.yml` inside a JAR or repository is no safer than `application.yml`. Never place real secrets in committed files, including profile-specific ones.

## 15. Use Placeholders Carefully

A pattern that can wire parameters together:

~~~yaml
app:
  client:
    base-url: "\${CLIENT_BASE_URL:https://localhost:8443}"
    timeout: "\${CLIENT_TIMEOUT:5s}"
~~~

Meaning: Spring resolves placeholders against `Environment`; if the referenced property is absent, the fallback may be used.

However, once you already have `application.yml` and profile files, scattering placeholder defaults across files easily creates **two layers of defaults**:

- Placeholder default.
- Profile-specific override default.
- Constructor-binding default.
- JavaBean field initializer default.

Set an intentional policy and avoid writing the same default in three places. For required secrets, **never use weak credential fallbacks** like `\${API_TOKEN:demo}` in shared artifacts.

## 16. Config Data Imports: Intentional Configuration Reuse

When a config block grows too large for a single `application.yml`, you can split files and import them via Spring Boot Config Data:

~~~text
src/main/resources/
  application.yml
  config/
    client-defaults.yml
    messaging-defaults.yml
~~~

Example:

~~~yaml
# application.yml
spring:
  config:
    import:
      - classpath:config/client-defaults.yml
      - classpath:config/messaging-defaults.yml
~~~

One file:

~~~yaml
# config/client-defaults.yml
app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 3
~~~

Splitting like this helps organize ownership, yet **is unnecessary for small projects**. Too many imports can obscure the configuration graph unless backed by naming conventions and ordering documentation.

In Spring Boot, imported documents participate in Config Data with their own precedence rules; they are not simple raw YAML text concatenation. Notably, **imported values can override the document declaring the import** under Boot's rules, and profile-specific variants of imported configs may also be considered.

Test duplicate keys between the importing file and imported files. Do not use imports to accidentally create hidden override layers that reviewers miss.

## 17. When to Use Imports vs Profile-Specific Files

| Need | Usually Appropriate Choice |
| --- | --- |
| A few scalars differ between dev and prod | `application-dev.yml` / `application-prod.yml` |
| Large shared default group with separate ownership | Imported Config Data file |
| Region- or deployment-specific configuration | External Config Data, env, or config store |
| Shared config across multiple applications | Centralized config with versioning/ownership |
| Group containing secrets | Secret manager/configtree/file mount |
| Enabling/disabling beans per environment | `@Profile` or explicit conditional config |
| Bundling logical profiles | `spring.profiles.group.*` |
| Setting a value everywhere | Base `application.yml` |

Pick the fewest mechanisms that keep things clear. Do not mix profile groups, imports, environment variables, placeholders, and custom `EnvironmentPostProcessor` implementations for a simple timeout.

## 18. Profile Groups: Bundling "Capability Profiles"

In systems with multiple logical profiles, an environment might combine capabilities such as `prod`, `metrics`, and `remote-cache`.

You can configure a profile group in a non-profile-specific document:

~~~yaml
# application.yml
spring:
  profiles:
    group:
      production:
        - prod
        - metrics
        - remote-cache
~~~

When activated:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Spring Boot expands the group to activate the declared profiles. This avoids repeating the same list of profiles across deployment commands.

However, **profile groups are not a tool for changing one scalar** like a timeout; they fit when organizing profiles into operational bundles.

Another risk: profile groups increase the number of loaded documents. If multiple documents override the same key, test the ordering and final value. Never assume groups merge files "equally".

### Do Not Define Groups in Profile-Activated Documents

Profile-controlling properties such as `spring.profiles.group.*` have placement restrictions; put them in an appropriate non-profile-specific document to avoid circular profile-selection dependencies.

## 19. Multi-Document YAML with on-profile

Instead of separate files, a single `application.yml` can contain multiple YAML documents:

~~~yaml
app:
  client:
    timeout: 5s
    max-retries: 3

---
spring:
  config:
    activate:
      on-profile: dev

app:
  client:
    timeout: 2s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  client:
    timeout: 10s
~~~

Here, the first document is the base; subsequent documents apply only when profile activation matches. This is still **base + delta configuration**, just packaged in one file.

Pros:

- Readers see base and overrides in the same file.
- Fewer files for projects with a small number of profiles.

Cons:

- The file gets long as environments grow.
- Easy to miss a `---` delimiter.
- Easy to get confused when profile groups or imports are involved.
- Rules against placing `spring.profiles.active` inside profile-activated documents still apply.

Pick one project convention. Do not duplicate the same override in both `application-prod.yml` and an `on-profile: prod` YAML document unless there is a clear reason and precedence is tested.

## 20. Do Not Treat on-profile as a Security Mechanism

Example:

~~~yaml
---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    client-secret: real-secret
~~~

This is still a real secret stored inside a config file; profile activation only controls when the document applies—**it does not encrypt the value**. The file can still be read from the repository or build artifact.

Rather than placing credentials in profile YAML documents, supply them from a secret store/runtime under explicit keys. Profile documents may contain **endpoint names**, **timeouts**, **feature toggles**, or non-secret production parameters.

## 21. application-local, application-dev, and Git

A project that runs locally:

~~~text
application.yml
application-dev.yml
application-prod.yml
application-local.yml
~~~

`application-local.yml` can hold laptop ports, mock server URLs, and feature flags, yet should not contain real committed credentials.

If each developer needs personal settings:

- Use env vars or local files outside the repo.
- Provide `.env.example` or a secret-free sample file.
- Use `.gitignore` to prevent committing untracked files, remembering it does not untrack already-committed files.
- Do not add a dedicated profile per individual in the main repository just for temporary personal tweaks.

A clean pattern is a `local` profile for shared development defaults plus personal overrides via environment variables. Separate **team defaults** from **machine secrets/overrides**.

## 22. Do Not Copy application-prod.yml into application-staging.yml

A dangerous habit is taking the production file, copying it to staging, and swapping URLs. That can carry over:

- Production feature flags not yet meant for staging.
- Low logging levels that hinder staging debugging.
- Callback URLs or queue names still pointing at production.
- Oversized resource limits or quotas.
- Wrong credentials or certificate paths.
- Incorrect profile activation.
- Wrong regulatory or region constraints.

Instead of copying, start from the base and **list only staging's real differences**:

~~~yaml
# application-staging.yml
app:
  external-api:
    base-url: https://sandbox.example.test
  job:
    concurrency: 2
  feature:
    new-checkout: true
~~~

Then test required properties and external environments. A short staging file is not incomplete if the base and runtime supply the rest.

## 23. Governing Intentional Differences

A contract table helps the team track which keys may vary by environment:

| Key | Base | Dev | Staging | Prod | Rationale |
| --- | --- | --- | --- | --- | --- |
| `app.client.timeout` | 5s | 2s | 7s | 12s | Network latency/SLA |
| `app.retry.max-attempts` | 3 | inherit | inherit | inherit | Shared policy |
| `app.feature.new-checkout` | false | true | true | false | Rollout |
| `app.job.concurrency` | 4 | 1 | 2 | 8 | Capacity |
| `spring.datasource.password` | None | Dev secret | Staging secret | Prod secret | Per-env credentials |
| `app.payment.mode` | Required | sandbox | sandbox | live | Must choose mode explicitly |

The word `inherit` simply means **the profile file omits the key and a lower source supplies the value**. It is not literal YAML to write.

A separate contract doc aids review, yet **avoid generating another copy holding all secret values**. Record key names, owners, policies, and reasons for differences—never store secrets.

## 24. Type-Safe Configuration Reduces Code Duplication

If one service uses:

~~~java
@Value("\${app.client.timeout:5s}")
private Duration timeout;
~~~

and another bean uses:

~~~java
@Value("\${app.client.timeout:3s}")
private Duration timeout;
~~~

then two consumers have **conflicting defaults**. Keeping config files DRY is not enough if code duplicates policy.

A consistent approach:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

Register it:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Inject into consuming services:

~~~java
@Service
public class ClientScheduler {
    private final ClientProperties options;

    public ClientScheduler(ClientProperties options) {
        this.options = options;
    }

    public Duration timeout() {
        return options.timeout();
    }
}
~~~

A typed bean centralizes the contract, conversion, and validation instead of scattered `@Value` fields with ad-hoc defaults. If custom conversion is needed, consider `@ConfigurationPropertiesBinding` rather than replacing the entire conversion registry.

## 25. Validation Prevents Base Defaults from Hiding Missing Config

For required configuration:

~~~java
import java.net.URI;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
    @NotNull URI endpoint,
    @NotBlank String merchantId
) {}
~~~

The application can omit `endpoint` and `merchant-id` from the base if every deployment must supply its own, then fail fast when missing.

For Bean Validation to run, a compatible provider—such as `spring-boot-starter-validation` in Spring Boot 3.x—and proper registration of the configuration properties bean are required.

**Do not put a production URL as a base default just so the app starts.** A test or staging environment lacking config that silently calls production is far worse than an explicit startup failure.

Distinguish:

- **Missing required config**: validation/policy.
- **Invalid format**: conversion/binding.
- **Wrong profile/source**: selection/precedence.
- **Valid value for the wrong environment**: requires deployment contracts and additional tests.

## 26. Distinguish Validation from Defaults

A value like:

~~~yaml
app:
  worker:
    concurrency: 0
~~~

converts cleanly to `int`. Yet if a constraint requires `@Min(1)`, startup should fail when validation is enabled.

Model:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @Min(1) @Max(32) int concurrency
) {}
~~~

Never enable `ignoreInvalidFields` or drop constraints just to let a broken profile start.

A shared default of 4 workers may be fine. Yet if production requires capacity-sized concurrency, enforcing explicit declaration is sound. DRY does not preclude **explicit exceptions designed to prevent fail-open behavior**.

## 27. Adding a New Field: Edit One Place and Verify Every Profile

Suppose the original model is:

~~~java
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

After evolution:

~~~java
public record ClientProperties(
    Duration timeout,
    int maxRetries,
    boolean circuitBreakerEnabled
) {}
~~~

Full-copy approach: add `circuit-breaker-enabled` to dev, staging, and prod, risking missing one file.

Base + delta approach:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
    max-retries: 3
    circuit-breaker-enabled: true
~~~

Only where an environment differs:

~~~yaml
# application-dev.yml
app:
  client:
    circuit-breaker-enabled: false
~~~

However, if the new field has security impact or requires an explicit per-environment decision, require explicit config and tests. **Shared defaults must be reviewed semantically, never added mechanically.**

## 28. Renaming Keys: Avoid Letting Two Config Generations Coexist

Example rename:

~~~text
app.client.request-timeout
    -> app.client.read-timeout
~~~

With full-copy profiles, three files may end up out of sync; one file keeps the old key and the new bean ignores it.

Migration:

1. Inventory all sources supplying the old key: base, profiles, env, CLI, external files, Helm/Compose.
2. Define the new canonical name and its impact on the Java model.
3. Decide on a compatibility window if needed (alias/converter/migration policy).
4. Update the base and **only the deltas that actually contain the old key**.
5. Update deployment variables per canonical rules.
6. Test critical profiles and runtime sources.
7. Remove the old key per the release plan.

Do not assume relaxed binding understands semantic word changes. `request-timeout` and `read-timeout` are **two different names**, not just hyphenation differences.

## 29. Multiple Active Profiles: Do Not Rely on Duplication to "Merge"

Suppose the app activates:

~~~text
spring.profiles.active=prod,metrics
~~~

and has:

~~~yaml
# application-prod.yml
app:
  telemetry:
    endpoint: https://metrics-prod.example.test
    sampling-rate: 0.1
~~~

~~~yaml
# application-metrics.yml
app:
  telemetry:
    sampling-rate: 1.0
~~~

You must determine **source ordering and the "last wins" rules in your exact Spring Boot version**. Do not treat two files as an unordered union; a duplicate key can be overwritten by the higher-precedence profile.

If two capability profiles can be active together, minimize overlapping keys between them or document precedence explicitly. Capability profiles should have **distinct ownership areas**, such as `app.telemetry.*` in the metrics profile, instead of also editing `app.payment.*` from prod.

Test real profile combinations whenever they occur in practice, not only each profile in isolation.

## 30. Separate Infrastructure-Related Config from Business Flags

A profile file may contain:

~~~yaml
app:
  client:
    timeout: 3s
  feature:
    new-checkout: true
  billing:
    tax-policy: strict
~~~

These groups have different owners and lifecycles:

- Timeouts depend on networking and operations.
- Feature flags may be managed by release/rollout teams.
- Tax policy may be governed by business or legal requirements.

They do not necessarily share the same override mechanism or reviewers. Base + delta reduces duplication, while **ownership** ensures changes receive proper review.

For frequently toggled feature flags, consider a dedicated feature management system when requirements warrant it; do not turn Spring profiles into a runtime rollout engine.

## 31. Limits of "One Giant Base File"

DRY does not mean every setting must live in one thousand-line `application.yml`. When a file grows too large:

- Organize prefixes clearly by module, e.g., `app.client`, `app.worker`, `app.notifications`.
- Evaluate splitting Config Data imports by topic.
- Assign each group an owner.
- Avoid tiny overlapping files or circular imports.
- Maintain effective configuration documentation and tests.

However, splitting into files containing only 3 properties creates indirection that makes finding sources harder. **Optimize for clarity**, not for minimal file count or minimal line count.

## 32. Avoid YAML Anchors as a Default Multi-Profile Solution

YAML has anchors and aliases, for example:

~~~yaml
defaults: &defaults
  timeout: 5s
  max-retries: 3
~~~

However, **YAML anchors cannot share data across independent files** like `application.yml` and `application-prod.yml`. Anchor scope is limited to the YAML document/parser and does not replace Spring Boot Config Data precedence.

Do not rely on cross-file anchors or YAML merge keys to solve DRY across profiles. In Spring Boot, prefer **base file + profile-specific delta**; it directly expresses how the application resolves properties.

If using anchors within a single YAML document for minor local repetition, understand your YAML parser and how Spring Boot flattens the result; do not use them as an excuse to skip precedence tests.

## 33. Fixing List Duplication: Consider Profile-Scoped Lists

Some large lists genuinely differ wholesale across environments:

~~~yaml
# application.yml
app:
  allowed-regions:
    - ap-southeast-1
    - ap-east-1
~~~

Production:

~~~yaml
# application-prod.yml
app:
  allowed-regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
~~~

If that list is a contract that cannot merge elements by name, declaring the full list per profile can be the **right choice**.

If a list differs only in one field of an object with stable identity, consider converting it to a map like `app.regions.primary` to reduce duplication.

Another option is keeping whole-list configs in centrally managed **environment files** imported from the proper location, rather than copying the entire application profile file. The goal is picking the **right unit of override**, not eliminating every repeated line at any cost.

## 34. Start Refactoring from a Difference Table

In a legacy codebase with three nearly identical files, do not delete duplicates until you understand semantics. Safe workflow:

1. List all keys currently declared in each file.
2. Classify scalars, nested objects, lists, and maps.
3. Identify values that match across profiles.
4. Identify values that **intentionally match** yet must remain explicitly required.
5. Locate secrets and values placed in the wrong source.
6. Identify external overrides (env/CLI/imports) outside the repository.
7. Propose a base + delta layout.
8. For lists, decide between whole-list override or refactoring to an identity-keyed map.
9. Add tests for effective values in every profile.
10. Make small incremental edits and compare before/after effective results.

**Never rely on plain text diffs alone.** Two YAML files may differ in key ordering, placeholders, profile activation, list binding, or imports, causing effective values to diverge from visual appearance.

## 35. Before and After Migration Example

**Before:**

~~~text
application-dev.yml
  app.client.timeout=2s
  app.client.max-retries=3
  app.worker.concurrency=1
  app.feature.new-checkout=true

application-prod.yml
  app.client.timeout=12s
  app.client.max-retries=3
  app.worker.concurrency=8
  app.feature.new-checkout=false
~~~

**After:**

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
    max-retries: 3
  worker:
    concurrency: 4
  feature:
    new-checkout: false
~~~

~~~yaml
# application-dev.yml
app:
  client:
    timeout: 2s
  worker:
    concurrency: 1
  feature:
    new-checkout: true
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 12s
  worker:
    concurrency: 8
~~~

Before and after, effective values for dev and prod must **be verified in practice**. You may choose base defaults aligned with the project's default environment, yet never accidentally alter the contract of an already-deployed profile.

If the app previously had no base `application.yml` and could run with no profile, adding base defaults can change the "no active profile" behavior. Test that scenario explicitly during migration.

## 36. Testing Profile Configuration with @SpringBootTest

Model:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

Once registered with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, you can test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("prod")
class ProdConfigTest {

    @Autowired
    ClientProperties client;

    @Test
    void appliesOnlyIntendedProdOverride() {
        assertThat(client.timeout())
            .isEqualTo(Duration.ofSeconds(12));
        assertThat(client.maxRetries())
            .isEqualTo(3);
    }
}
~~~

This test uses the test context's profile files and resources; it verifies **effective values** rather than counting YAML lines.

For dev:

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class DevConfigTest {

    @Autowired
    ClientProperties client;

    @Test
    void keepsBaseRetryPolicy() {
        assertThat(client.timeout())
            .isEqualTo(Duration.ofSeconds(2));
        assertThat(client.maxRetries())
            .isEqualTo(3);
    }
}
~~~

Ensure tests do not include `@SpringBootTest(properties=...)` or test property sources that accidentally override the very keys under test. If production supplies env/CLI externally, add deployment contract tests at the appropriate layer.

## 37. ApplicationContextRunner for Testing Small Config Slices

A lightweight test without starting a full web server can use `ApplicationContextRunner`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientDefaultsTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void baseValuesBindWhenNoOverride() {
        runner
            .withPropertyValues(
                "app.client.timeout=5s",
                "app.client.max-retries=3"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                ClientProperties props =
                    context.getBean(ClientProperties.class);
                assertThat(props.maxRetries()).isEqualTo(3);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {}
}
~~~

This tests binding against explicitly supplied inputs. **It does not automatically prove `application-prod.yml` was loaded**, because `ApplicationContextRunner` does not simulate the full Config Data startup path in all setups.

Use `@SpringBootTest` or appropriate integration setups to verify Config Data and real profiles, while `ApplicationContextRunner` fits testing conversions, defaults, and small configuration slices.

## 38. Test Matrix Across Multiple Environments

A helpful matrix:

| Scenario | Profile | Timeout | Retries | Concurrency | Feature |
| --- | --- | --- | --- | --- | --- |
| Base/default | None active | 5s | 3 | 4 | false |
| Development | dev | 2s | 3 | 1 | true |
| Staging | staging | Per staging delta | 3 | Per staging delta | Per policy |
| Production | prod | 12s | 3 | 8 | false |
| Production + metrics | prod,metrics | No unintended change | 3 | 8 | false |
| Missing required secret | prod, secret omitted | Clear startup failure | — | — | — |
| CLI override | prod + CLI timeout | CLI wins | 3 | 8 | false |

This table is illustrative; adapt it to your real contract. **Test both keys that must stay unchanged and keys that are overridden**: checking only prod timeout will not catch `maxRetries` accidentally copied as a different value.

For sensitive properties, tests can assert "missing causes failure" without using real production credentials. Use fake or sandbox secrets in test contexts.

## 39. Automated Detection of Configuration Drift

DRY reduces drift but does not eliminate all risk. CI can verify:

- Every new key has an owner and documented behavior.
- No deprecated keys remain in profile files.
- No real secrets appear in resources.
- No accidental duplication of shared scalars.
- Critical keys have validation.
- Profile tests continue to pass.
- List/map shapes bind cleanly to Java targets.
- No profile-specific documents violate profile activation rules.

A static tool can compare key sets, yet **must not automatically delete or edit duplicate keys without understanding semantics**. Duplication is sometimes intentional, especially with lists or per-environment required settings.

If multiple services share a config library, enforce versioning and compatibility rules rather than editing a shared file and impacting dozens of services at once.

## 40. Using Centralized Configuration

An organization with many microservices may consider a central config repository (such as Spring Cloud Config or a cloud configuration service).

Goals may include:

- Sharing common defaults/policies across environments.
- Access control and auditing for changes.
- Versioning and rollback of configuration.
- Decoupling config from artifacts.
- Reducing copies across repositories.

However, this is **not** a feature provided automatically by core Spring Boot simply via `spring.config.import`. Specific integrations require dedicated dependencies, server/backends, and security setup.

Centralized config introduces another override layer, so document its **precedence relative to packaged/external Config Data, env, and CLI**. Otherwise, eliminating duplication in the repo merely shifts confusion to runtime.

## 41. Design Rules for Multi-Profile Evolution

A practical rule set for teams:

1. **Maintain one base** holding safe shared values.
2. **Profile files hold only deltas**, never full tree copies.
3. **Keep secrets out** of repositories and profile files.
4. **For lists**, intentionally replace whole lists or remodel as identity-keyed maps.
5. **Test map overrides**; never assume unconditional deep merge.
6. **Keep critical settings explicit** if absence must fail startup.
7. **One key, one owner**: know which module owns the contract.
8. **Never activate profiles inside profile-specific documents**.
9. **Standardize key naming** with canonical kebab-case and verify env names.
10. **Test effective values**, not just YAML text diffs.
11. **Separate deployment-specific settings** from artifact defaults.
12. **Limit layers**: use profiles/imports/groups only when genuinely needed.
13. **Review multi-profile changes** as a migration contract.
14. **Document inherited values** and active profile combinations.
15. **Never trade away fail-fast safety just to reduce line count**.

## 42. Troubleshooting: "Removed Duplicates, Now Values Are Wrong"

If an environment behaves differently after refactoring, follow this sequence:

1. Identify the canonical key and target Java field.
2. Compare effective values before and after migration under the same profile and deployment sources.
3. Inspect candidate sources: base file, profile file, external Config Data, imports, env, and CLI.
4. Verify actual active/default profiles.
5. Check whether the key sits inside a replaced list.
6. Check whether nested maps are structured properly.
7. Check whether constructor defaults, `@DefaultValue`, or field initializers changed behavior.
8. Check whether a missing key is falling back or failing validation.
9. Verify the new artifact/container was deployed and the process restarted.
10. Check whether a consumer cached or snapshotted the value earlier.
11. Inspect origin/source names if tooling and permissions allow.
12. Fix at the right layer, then rerun profile tests and deployment cases.

Never dump the entire `Environment` in production: property sources may hold passwords/tokens. For Actuator `env` and `configprops`, secure the endpoints, restrict access, and avoid exposing raw sensitive values.

## 43. Anti-Pattern: Staging Indirectly Inheriting Production

Some projects define staging by directly importing all production settings and overriding a few values:

~~~yaml
# application-staging.yml
spring:
  config:
    import: classpath:application-prod.yml
~~~

This is usually error-prone because staging is **not a copy of production minus a few keys**. It can accidentally inherit production endpoints, feature flags, policies, or resources.

Instead of inheriting from another environment, **both staging and production should inherit from a neutral base**, then declare independent deltas. If two environments truly share a well-defined non-secret block, extract it into a properly named and owned common file/module—do not call it `application-prod.yml`.

Same principle: **environments are sibling variants of the base, not an ambiguous subclass hierarchy**.

## 44. Anti-Pattern: Duplicating Ordinary Values into Every Kubernetes/Compose Manifest

An application has base `application.yml`:

~~~yaml
app:
  retry:
    max-attempts: 3
    backoff: 250ms
~~~

Yet Compose, Helm values, and CI pipelines all redeclare those same two values. When the retry policy changes, one place gets forgotten.

Decide cleanly:

- If it is an **application default**, leave it in the base.
- If a deployment needs an override for capacity/network, declare it in the deployment.
- If it is a secret, manage it via a secret channel.
- If it is a policy that must be explicit per environment, document and validate it.

Do not export the entire `application.yml` as environment variables just to "stay in sync"; that adds another copy to maintain and can unexpectedly alter precedence.

## 45. Exercise 1 — Converting a Copied File into a Delta

Old base:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 5m
    max-entries: 200
~~~

Copied production:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 10m
    max-entries: 200
~~~

**Task:** write `application-prod.yml` as a delta.

**Answer:**

~~~yaml
app:
  cache:
    ttl: 10m
~~~

`enabled` and `max-entries` still come from the base unless overridden by a higher source.

## 46. Exercise 2 — List Override

The base has two endpoints; production wants to change the timeout of the first endpoint. A developer writes only:

~~~yaml
app:
  endpoints:
    - timeout: 10s
~~~

**Answer:** unsafe if you intend to preserve the rest of the list. With Spring Boot list binding, a higher source normally replaces the whole list rather than deep-merging elements. Rewrite the full list or redesign as a map keyed by endpoint ID if per-entry overrides are desired.

## 47. Exercise 3 — Map Instead of List

Base:

~~~yaml
app:
  endpoints:
    primary:
      timeout: 2s
      url: https://primary.example.test
    backup:
      timeout: 5s
      url: https://backup.example.test
~~~

Production:

~~~yaml
app:
  endpoints:
    primary:
      timeout: 9s
~~~

**Answer:** a map can fit better than a list when identities are stable and key-based overrides are needed, though you should verify Spring Boot `Binder` behavior against the actual target model. Do not assume all nested maps share identical merge semantics.

## 48. Exercise 4 — Missing Secret

Production lacks `spring.datasource.password`. A developer suggests putting a demo password in the base to avoid startup failures.

**Answer:** do not do that. Credentials must be supplied securely at runtime; if required, fail fast when missing. Reducing duplication never outranks security.

## 49. Exercise 5 — Profile Groups

A deployment must always enable `prod`, `metrics`, and `remote-cache`. What can be used?

**Answer:** declare a `spring.profiles.group.production` group in a non-profile-specific document, then activate `production`. Check for key conflicts across profiles before deploying.

## 50. Exercise 6 — Multi-Document YAML

A file contains a base document and a `spring.config.activate.on-profile=prod` document. A developer declares `spring.profiles.active=prod` inside the `on-profile: prod` document.

**Answer:** do not use a profile-activated document to activate profiles; Spring Boot restricts profile activation properties in such documents. Supply the active profile from deployment or an earlier source.

## 51. Exercise 7 — Refactoring and @Value

Two services use `@Value` with the same key but fallbacks of `2s` and `5s`, respectively.

**Answer:** even if YAML files are DRY, the code duplicates policy. Prefer a shared typed `@ConfigurationProperties` bean with an explicit default, and test missing-key behavior.

## 52. Exercise 8 — Renaming a Key

`app.client.request-timeout` is renamed to `app.client.read-timeout`. A dev file still uses the old key.

**Answer:** refactoring must update the base, any overriding profiles, env vars/CLI/deployments, the Java model, and docs. Relaxed binding does not interpret semantic renames from `request` to `read`.

## 53. Exercise 9 — Regular Setting That Is Critical

`app.payment.mode` is `sandbox` or `live`. Should `live` be placed in the base to save two repeated lines?

**Answer:** do not default it. If an environment omits the value and must fail fast to prevent unintended real transactions, enforce explicit declaration and validation.

## 54. Exercise 10 — Profile Test Checking Only One Key

A prod test asserts timeout is 12s, while `max-retries` accidentally changed to 1 due to an old copied file.

**Answer:** tests must verify both overridden keys and keys expected to inherit from the base. Testing only "changed keys" is insufficient to catch configuration drift.

## 55. Summary Decision Table

| Problem | Approach |
| --- | --- |
| Scalar identical across environments | Place once in `application.yml` |
| Scalar varies by profile | Put only the override in `application-{profile}.yml` |
| Nested object differs by one field | Override only the leaf key; test binding |
| List varies by environment | Declare full list or remodel as map |
| Map has ID-keyed entries | Consider map binding and test merge/override |
| Multiple logical profiles travel together | Profile groups with clear ownership |
| Large shared defaults | Modular Config Data imports if needed |
| Environment-specific secrets | Controlled secret manager/env/mount |
| Critical setting with no safe default | Require explicit declaration; validate/fail fast |
| Shared config across multiple services | Versioned central config with access control |
| Structural or key rename | Migration contract and tests across all profiles |
| CI drift detection | Test effective values, secret scans, schema checks |
| Dynamic feature rollouts | Consider a feature flag system, not profile overload |
| Debugging "file not read" | Check active profiles, Config Data, precedence, origin, startup |
| Team has nearly identical files | Base + delta + incremental refactor |

## 56. Pull Request Review Checklist for Config Changes

When reviewing a profile change, ask:

- [ ] Does this key genuinely differ across environments?
- [ ] If it matches the base, why is it repeated?
- [ ] If the key is omitted, is the default safe?
- [ ] Were any real secrets added to the repository?
- [ ] Does the change affect other profiles?
- [ ] Is this a scalar, nested object, list, or map?
- [ ] If a list, is the resulting full list correct?
- [ ] Which profiles are active during testing, including groups/includes?
- [ ] Is a higher env/CLI/import source masking this override?
- [ ] Does typed `@ConfigurationProperties` have proper validation?
- [ ] Do deployment templates, documentation, or charts need updates?
- [ ] Do tests assert both overridden and inherited values?
- [ ] Is any `@Value` code holding a conflicting default?
- [ ] Are there rollback plans and change-control reviews?

## 57. Summary

**Avoiding full configuration duplication across profiles is about designing sources of truth and controlling differences, not merely shortening YAML.** The base + delta model gives every shared value one managed home, while each profile file states precisely what differs in that environment.

Remember four points:

1. **`application.yml` holds shared, safe defaults; `application-{profile}.yml` records only intentional differences.**
2. **Scalars and nested properties can typically be overridden per key; never assume lists deep-merge.** For structures needing identity-based overrides, consider maps and test actual behavior.
3. **Secrets and critical settings need dedicated policies.** Never copy credentials into profile files; never sacrifice fail-fast just to trim duplication.
4. **Refactors must be verified against effective configuration.** Check source precedence, active profiles, typed binding, environment/CLI, and regression tests before and after removing duplicates.

A well-designed configuration system quickly answers: **where is the default, how does this profile differ from the base, why does it differ, and what happens if a key is missing?** When those answers are clear, maintaining and deploying Spring Boot across environments becomes far less surprising.
