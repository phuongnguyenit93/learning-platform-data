# Renaming Properties While Managing Compatibility and Deprecation Roadmap in Spring Boot

## 1. Why Is Renaming a Property a Potentially Breaking Change?

Spring Boot reads configuration from `application.yaml`, `application.properties`, external Config Data, profiles, environment variables, Java system properties, command-line arguments, and other configuration sources. A name like `app.client.request-timeout` lives not only in Java code, but also in:

- Profile-specific files such as `application-prod.yaml`.
- Helm values, ConfigMaps, or Kubernetes Deployments.
- Docker Compose and runtime environment variables.
- CI/CD variables or launch scripts.
- Mounted secret/configuration trees.
- Tests, runbooks, and deployment templates.
- Other modules or systems reading the same configuration contract.

Suppose the old version used:

~~~properties
app.client.request-timeout=5s
~~~

The team wants to rename it to:

~~~properties
app.client.timeout=5s
~~~

If you simply rename the Java member from `requestTimeout` to `timeout` and ship immediately, production deployments still passing the old name may fail to bind the value. Depending on defaults and validation, the app may boot with the wrong timeout, fail later at runtime, or fail startup outright.

**Lesson goal:** design a time-bounded migration, support both old and new names during transition, announce deprecation, define precedence when both coexist, test compatibility, plan removal, and avoid leaking secrets.

Examples use Spring Boot 3.x, Java 17+, Jakarta Validation, and JUnit 5. Version numbers are illustrative, not a universal project policy.

## 2. Concepts to Distinguish

| Concept | Meaning |
| --- | --- |
| Legacy key | Old property name existing deployments may still supply. |
| Canonical key | New recommended property name. |
| Alias or compatibility layer | Logic mapping the old name to the value the app needs. |
| Deprecation | Notice that a name is not yet removed, yet should no longer be used. |
| Replacement | Recommended new name replacing the old one. |
| Migration | Updating code, configs, tooling, docs, and runtime environments. |
| Sunset | Milestone or condition ending support for the old name. |
| Removal | Removing runtime support, not merely deleting text from documentation. |
| PropertySource precedence | Priority order across sources supplying the same property. |

**Deprecation metadata is not a runtime alias.** IDEs knowing an old key is deprecated does not make the Binder automatically map `request-timeout` to `timeout`.

**Relaxed binding is also not an arbitrary alias engine.** It handles spelling variations of the same name, not two differently named keys.

## 3. Running Example: `request-timeout` Migrating to `timeout`

Old version:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration requestTimeout) {
}
~~~

Old YAML:

~~~yaml
app:
  client:
    request-timeout: 10s
~~~

Target YAML in the new version:

~~~yaml
app:
  client:
    timeout: 10s
~~~

A transition contract might specify:

1. Only `app.client.timeout` present: use the new key.
2. Only `app.client.request-timeout` present: temporarily accept it and log a warning with the legacy key name.
3. Both present: the new key wins; warn about duplicate configuration.
4. Neither present: fail fast if timeout is required; if optional, use the documented default.
5. Invalid type: report a clear error rather than silently substituting the other key.
6. After an announced transition window: stop accepting the old key.

This is an **explicitly designed policy**, not default behavior Spring Boot automatically applies to two distinct properties.

## 4. Real Renames Differ from Case/Format Variants

Spring Boot relaxed binding maps canonical:

~~~text
app.client.request-timeout
~~~

to Java member:

~~~text
requestTimeout
~~~

and from the matching environment variable:

~~~text
APP_CLIENT_REQUESTTIMEOUT
~~~

Yet `app.client.timeout` binds to `timeout`, not `requestTimeout`.

Example table:

| Legacy | New | Needs Compatibility Logic? |
| --- | --- | --- |
| `app.client.request-timeout` | `app.client.requestTimeout` | May only be a relaxed-binding spelling variant; verify context. |
| `app.client.request-timeout` | `app.client.timeout` | Yes, because the name changed semantically. |
| `app.retries` | `app.max-attempts` | Yes, and value semantics must also be clarified. |
| `APP_CLIENT_REQUESTTIMEOUT` | `APP_CLIENT_TIMEOUT` | Yes, since the actual env variable name changed. |

Do not ship a new alias when merely changing hyphenation to camelCase for the exact same property already handled by Binder. Conversely, do not rely on relaxed binding to handle a genuine rename.

## 5. Mapping Every Representation of a Property

When renaming `app.client.request-timeout` to `app.client.timeout`, search across all forms:

~~~text
application.yaml:
    app.client.request-timeout -> app.client.timeout

environment:
    APP_CLIENT_REQUESTTIMEOUT -> APP_CLIENT_TIMEOUT

JVM system property:
    -Dapp.client.request-timeout=5s
    -> -Dapp.client.timeout=5s

Command line:
    --app.client.request-timeout=5s
    -> --app.client.timeout=5s

Configuration tree filename:
    /run/secrets/app.client.request-timeout
    -> /run/secrets/app.client.timeout
~~~

Canonical `@ConfigurationProperties` env mapping typically converts dots to `_`, removes hyphens, and uppercases.

When renaming a key, inspect:

- Java classes and configuration metadata.
- Config Data inside and outside the JAR.
- Profile-specific files.
- Docker/Compose, Kubernetes/Helm.
- ConfigMap keys, Secret keys, `env.name`, and `volume.items.path`.
- CI/CD, systemd, and launcher scripts.
- Integration test fixtures.
- Runbooks and operator documentation.

Not finding the old name in the repository **does not prove** runtime deployments have dropped it. Many env vars and Secrets are managed externally.

## 6. Designing an Input Class That Accepts Both Names

A simple pattern for application-owned properties: separate **raw configuration input** from **normalized settings**.

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientInputProperties(
        Duration timeout,
        Duration requestTimeout) {
}
~~~

Mapping:

~~~text
timeout         ← app.client.timeout
requestTimeout  ← app.client.request-timeout
~~~

Both fields are bound by Spring Boot. During transition, do not place a default on the new field if that default would cause the resolver to ignore the legacy value.

Create a clean type holding only normalized values:

~~~java
package com.example.demo.config;

import java.time.Duration;

public record ClientSettings(Duration timeout) {
}
~~~

Business services use only `ClientSettings`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RemoteClientService {

    private final ClientSettings settings;

    public RemoteClientService(ClientSettings settings) {
        this.settings = settings;
    }

    public Duration timeout() {
        return settings.timeout();
    }
}
~~~

This keeps services unaware of both aliases, prevents inconsistent choices across services, and requires zero service changes when legacy support is later removed.

## 7. Complete Java Example: Canonical Key Wins

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientInputProperties.class)
public class ClientSettingsConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(ClientSettingsConfiguration.class);

    @Bean
    ClientSettings clientSettings(ClientInputProperties input) {

        if (input.requestTimeout() != null) {
            log.warn(
                "Property 'app.client.request-timeout' is deprecated; "
                + "use 'app.client.timeout'");
        }

        if (input.timeout() != null
                && input.requestTimeout() != null) {
            log.warn(
                "Both legacy and canonical timeout properties are set; "
                + "'app.client.timeout' takes precedence");
        }

        Duration selected = input.timeout() != null
                ? input.timeout()
                : input.requestTimeout();

        if (selected == null) {
            throw new IllegalStateException(
                "Missing app.client.timeout "
                + "(legacy app.client.request-timeout still supported)");
        }

        if (selected.isZero() || selected.isNegative()) {
            throw new IllegalStateException(
                "app.client.timeout must be positive");
        }

        return new ClientSettings(selected);
    }
}
~~~

How it works:

1. Once the input class is registered, Binder populates `timeout` and `requestTimeout` from whichever keys exist.
2. If the legacy field is present, log a warning with the **key name**, never printing values.
3. If both are present, log the conflict and pick the canonical field.
4. If only the old key is present, use it temporarily.
5. If both are absent, fail startup.
6. If `Duration` is zero or negative, reject it.

### Avoid Duplicate Bean Registration

This example uses `@EnableConfigurationProperties(ClientInputProperties.class)` on the configuration class. If the project uses `@ConfigurationPropertiesScan`, choose one clear registration mechanism to avoid accidentally creating duplicate beans.

### Keep Business Logic Free of Legacy Awareness

Business code should not scatter:

~~~java
Duration timeout = old != null ? old : newer;
~~~

across multiple classes. Doing so risks Service A picking old while Service B picks new when both exist. Maintain **a single compatibility resolver** as the sole source of truth.

## 8. Major Mistake: Putting `@DefaultValue` Too Early

Example:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientInputProperties(
        @DefaultValue("5s") Duration timeout,
        Duration requestTimeout) {
}
~~~

Suppose an older environment sets:

~~~properties
app.client.request-timeout=30s
~~~

When Binder constructs the record, `timeout` receives the default 5 seconds because the new key is absent. The resolver sees `timeout != null` and selects 5 seconds, silently discarding the legacy 30 seconds.

This is an **unintended semantic regression** right in the middle of a promised compatibility window.

If a default is wanted when both keys are absent, resolve aliases first:

~~~java
Duration chosen = input.timeout() != null
        ? input.timeout()
        : input.requestTimeout();

if (chosen == null) {
    chosen = Duration.ofSeconds(5);
}
~~~

Or fail if no default is permitted.

**Rule:** defaults belong to the **normalized value's contract**, never letting a canonical field look "operator-supplied" before legacy keys are checked.

## 9. Source Precedence and Name Precedence Are Two Different Concepts

Spring Boot defines `PropertySource` precedence. Yet two names:

~~~text
app.client.timeout
app.client.request-timeout
~~~

are two separate properties.

Example:

~~~yaml
# application.yaml
app:
  client:
    timeout: 3s
~~~

Container environment:

~~~text
APP_CLIENT_REQUESTTIMEOUT=20s
~~~

If the resolver picks **canonical always wins**, the result is **3s**, even though the legacy value came from an environment variable with higher precedence than YAML.

Why? Binder resolves each property independently, and then your code decides priority between the **two names**.

### Three Policy Options

**A. New name always wins**

- Easy to explain and supports migration.
- Must warn when both old and new appear.
- Can override `PropertySource` precedence between the two names.

**B. Source precedence wins**

- An alias from a higher-priority source beats the other alias from a lower source.
- Requires a dedicated resolver iterating sources and handling relaxed binding properly.
- Significantly more complex; requires testing CLI/env/YAML/configtree.

**C. Both names together is an error**

- Disallows ambiguity when both exist.
- Appropriate for security endpoints, secrets, or high-risk settings.
- Needs careful rollout planning to avoid startup failures during transition.

Spring Boot has no built-in "new alias always wins" rule that it infers on its own. Choose one policy and **codify it in tests**.

## 10. Conversion of Both Fields Can Still Fail Startup

Example:

~~~properties
app.client.timeout=3s
app.client.request-timeout=not-a-duration
~~~

Input class:

~~~java
public record ClientInputProperties(
        Duration timeout,
        Duration requestTimeout) {
}
~~~

Binder normally tries to bind **both `Duration` fields** when constructing the record. An unconvertible legacy field fails binding **before** the bean factory method can select 3s.

If your contract states "when canonical is valid, an invalid legacy key must be ignored", change the architecture:

1. Determine the winning key at the source layer prior to conversion.
2. Convert only the selected value with an appropriate conversion service / `Binder`.
3. Log a warning without forcing conversion of the unused legacy key.
4. Test both old-bad/new-good and old-good/new-bad combinations.

Do not merely write `if (timeout != null)` assuming conversion errors on another field will vanish.

### Strict Policy

In many apps, failing when **any declared key has an unconvertible value** is completely sensible: leftover stale config should be cleaned up rather than silently ignored.

The key is to **publish and test** the chosen behavior rather than assuming one universal rule.

## 11. `@Value` Nested Fallbacks Are a Limited Option

A concise trick for scalars:

~~~java
@Value("${app.client.timeout:${app.client.request-timeout:5s}}")
private Duration timeout;
~~~

Idea: try new; if absent, try old; finally fall back to 5s.

Yet this approach has clear limits:

- Emits no automatic deprecation warning.
- Emits no conflict notice when both names are set.
- Easy to reverse the order accidentally by writing legacy first.
- An empty present String differs from an absent key.
- Hard to reuse across many fields, nested objects, and List/Map.
- Carries no migration metadata or sunset tracking.
- Conversion paths may depend on conversion service setup.

For larger configuration surfaces, prefer `@ConfigurationProperties` and a tested normalizer.

## 12. Deprecation Metadata Helps IDEs, Not Runtime Aliasing

Spring Boot provides configuration metadata so tools know:

- Canonical property names.
- Java types.
- Descriptions, defaults, and hints.
- Which names are deprecated, why, and their replacements.

When metadata marks:

~~~text
app.client.request-timeout
    deprecated
    replacement = app.client.timeout
~~~

IDEs can show warnings. However, Spring Boot's Binder does not automatically treat that metadata as a runtime rename rule for custom application properties.

Distinguish three layers:

| Layer | Role |
| --- | --- |
| Runtime compatibility | Code that actually accepts both old and new keys. |
| IDE metadata | Tooling visibility into deprecated keys and replacements. |
| Documentation + rollout | Operators know when to change and who owns the rollout. |

A complete migration requires all three.

## 13. `@DeprecatedConfigurationProperty` on JavaBean Getters

Spring Boot provides:

~~~java
org.springframework.boot.context.properties.DeprecatedConfigurationProperty
~~~

JavaBean example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.DeprecatedConfigurationProperty;

@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private Duration requestTimeout;

    @Deprecated
    @DeprecatedConfigurationProperty(
            reason = "Use app.client.timeout",
            replacement = "app.client.timeout")
    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

`@DeprecatedConfigurationProperty` is placed on the getter so the configuration processor emits deprecation metadata. Java's `@Deprecated` targets Java API consumers separately.

**It does not automatically:**

- Map `request-timeout` to `timeout` during binding.
- Emit deprecation warnings in startup logs in all situations.
- Block the property once the sunset milestone arrives.

Metadata and runtime enforcement must be handled separately.

### What About Records?

Record components generate accessors like `requestTimeout()`, not JavaBean `getRequestTimeout()`. When clear deprecation metadata is needed for a record or property without a JavaBean getter, supply **additional metadata** directly.

## 14. `additional-spring-configuration-metadata.json`

File:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Example:

~~~json
{
  "properties": [
    {
      "name": "app.client.request-timeout",
      "type": "java.time.Duration",
      "description": "Legacy client timeout; use app.client.timeout.",
      "deprecation": {
        "level": "warning",
        "reason": "Renamed to simplify the client configuration API.",
        "replacement": "app.client.timeout"
      }
    }
  ]
}
~~~

In Spring Boot metadata:

- `name` is the canonical old key.
- `type` documents the data type.
- `deprecation.level` indicates severity for tooling.
- `deprecation.reason` explains why.
- `deprecation.replacement` points to the new key.

`warning` or `error` levels in metadata target tooling. They **do not turn into runtime Java exceptions**. To forbid an old key after support ends, implement a runtime guard/validation or a tested migration check.

### Configuration Processor

Gradle Groovy:

~~~groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
~~~

Maven can declare the dependency and annotation processing per its current plugin setup:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Verify the build actually runs the annotation processor and generates:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Tooling will not automatically pick up the additional file in the repo unless it is packaged into the artifact/classpath properly. Verifying build outputs is separate from testing runtime aliases.

## 15. Do Not Confuse `spring-boot-properties-migrator` with Custom Aliases

During Spring Boot version upgrades, the artifact:

~~~text
org.springframework.boot:spring-boot-properties-migrator
~~~

helps detect Boot-managed properties that were renamed or removed per Boot's own metadata and temporarily migrates supported properties.

Temporary Maven dependency example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Do not assume this module **automatically recognizes arbitrary application key pairs**, such as `app.client.request-timeout` → `app.client.timeout`. Verify against the specific Boot version and key pair.

The migrator tool does not replace:

- Application runtime compatibility code.
- Deprecation metadata for custom properties.
- Updating deployment files outside the repository.
- Unit/integration tests for configuration sources.
- A sunset plan for legacy support.

Once a Boot upgrade finishes, remove the temporary migrator dependency per your version's guide; never leave it as an untracked permanent compatibility layer.

## 16. `@Name` Is Not a Legacy Alias List

The `@Name` binding annotation specifies a single parameter/property name when the Java identifier is unsuitable:

~~~java
import org.springframework.boot.context.properties.bind.Name;

public record ImportOptions(
        @Name("import") String importLocation) {
}
~~~

It does not let one field accept an arbitrary list of old and new names with deprecation, precedence, and sunset rules. `@Name` maps a single binding name at that site, not a general migration mechanism.

Do not apply `@Name("timeout")` and assume `request-timeout` continues to work automatically.

## 17. `EnvironmentPostProcessor`: Use Only When Truly Needed

`EnvironmentPostProcessor` is a Spring Boot extension point that modifies `Environment` during startup, useful if a shared alias layer is required across many properties.

However, it must handle many subtleties:

1. Running at the right phase relative to Config Data.
2. Reading properties from YAML, env, CLI, and system properties.
3. Understanding source ordering and canonical names.
4. Resolving conflicts when old and new coexist.
5. Avoiding letting a lower-source alias overwrite a new property.
6. Never leaking secrets in logs.
7. Leaving unrelated properties untouched.

**Anti-pattern:** reading a legacy value and inserting an alias into the highest-precedence `MapPropertySource` without checking the new key. That overwrites the new value even when an operator explicitly set the canonical key.

For a single application-controlled key, dual binding plus a normalizer (Sections 6–7) is far easier to maintain and test.

### When Source Precedence Must Be Preserved

You may need to iterate through each `PropertySource` in priority order, checking old and new names and promoting the canonical key by policy. That is a custom algorithm; test it across:

- New key in YAML, old key in env.
- Old key in YAML, new key in env.
- New key in CLI, old key in configtree.
- Both names in the same source.
- Empty values, invalid types, duplicates.

Never run one test inside a single properties file and conclude compatibility works across all environments.

## 18. Be Careful When Changing Type and Unit Together

A pure rename:

~~~text
app.client.request-timeout = 5s
    ->
app.client.timeout = 5s
~~~

differs from changing the data representation at the same time:

~~~text
app.client.timeout-ms = 5000
    ->
app.client.timeout = 5s
~~~

If an operator copies `5000` onto the new key, they may get a different result if parsing or default units changed.

When units change:

- Clarify whether the old value was milliseconds or seconds.
- State the new syntax explicitly: `500ms`, `5s`, `PT5S`.
- Avoid ambiguous bare numbers.
- Implement conversion for legacy values if needed.
- Test boundary values: zero, negative, unusually large, and overflow.
- Update sample configs and runbooks.

A proper migration preserves **meaning**, not just property spelling.

## 19. Renaming Lists, Maps, or Large Prefixes

Example:

~~~text
app.targets
    ->
app.client.endpoints
~~~

Both are Lists. To support both side by side, bind two separate properties and select:

~~~text
new list has entries -> use new list
else old list        -> use old list
neither              -> missing policy
~~~

Do not concatenate the two lists unless a merge contract explicitly specifies it. Spring Boot normally **replaces Lists** from higher-precedence sources rather than merging elements across sources.

For Maps or nested objects, mixing some fields from the old prefix and others from the new prefix can create dangerous hybrid configurations—especially for endpoints, TLS, and credentials. Prefer choosing the whole new/old object or rejecting partial mixes.

### When Renaming an Entire Prefix

~~~text
legacy.billing.endpoint   -> payments.billing.endpoint
legacy.billing.timeout    -> payments.billing.timeout
legacy.billing.client-id  -> payments.billing.client-id
legacy.billing.secret     -> payments.billing.secret
~~~

Map out every field:

| Old Key | New Key | Type | Default | Required | Notes |
| --- | --- | --- | --- | --- | --- |
| `legacy.billing.endpoint` | `payments.billing.endpoint` | URI | None | Yes | Do not alter host accidentally |
| `legacy.billing.timeout` | `payments.billing.timeout` | Duration | 5s if valid | No | Explicit unit |
| `legacy.billing.client-id` | `payments.billing.client-id` | String | None | Yes | Never log value |
| `legacy.billing.secret` | `payments.billing.secret` | String/secret | None | Yes | Separate rotation/permissions |

A prefix rename can span teams on different release schedules, making a compatibility window even more critical.

## 20. Testing Migration with `ApplicationContextRunner`

Using `ClientInputProperties`, `ClientSettings`, and `ClientSettingsConfiguration` from earlier:

~~~java
package com.example.demo.config;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ClientSettingsMigrationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(
                    ClientSettingsConfiguration.class);

    @Test
    void usesCanonicalProperty() {
        runner.withPropertyValues(
                "app.client.timeout=3s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(ClientSettings.class).timeout())
                        .isEqualTo(Duration.ofSeconds(3));
            });
    }

    @Test
    void temporarilyAcceptsLegacyProperty() {
        runner.withPropertyValues(
                "app.client.request-timeout=7s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(ClientSettings.class).timeout())
                        .isEqualTo(Duration.ofSeconds(7));
            });
    }

    @Test
    void canonicalWinsWhenBothPresent() {
        runner.withPropertyValues(
                "app.client.timeout=3s",
                "app.client.request-timeout=7s")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(ClientSettings.class).timeout())
                        .isEqualTo(Duration.ofSeconds(3));
            });
    }

    @Test
    void missingBothFails() {
        runner.run(context ->
                assertThat(context).hasFailed());
    }

    @Test
    void rejectsZeroValue() {
        runner.withPropertyValues(
                "app.client.timeout=0ms")
            .run(context ->
                assertThat(context).hasFailed());
    }
}
~~~

This test suite verifies runtime compatibility in a small context; it does not prove profile files or Kubernetes env vars load properly. Add tests covering real sources.

### Do Not Assert Only That the Bean Exists

~~~java
assertThat(context).hasSingleBean(ClientSettings.class);
~~~

does not prove the app picked the right timeout. Always assert the **final resolved value**.

## 21. Testing Invalid Types and Missing Values

Extend the matrix:

| New | Old | Expected Result for Example Resolver |
| --- | --- | --- |
| `3s` | Missing | 3s |
| Missing | `7s` | 7s and warning |
| `3s` | `7s` | 3s and conflict warning |
| Missing | Missing | Startup failure |
| `0ms` | `7s` | Startup failure, no fallback |
| `bad` | `7s` | Binding/conversion error |
| `3s` | `bad` | May fail binding legacy, since both fields bind |
| `3s` (YAML) | `20s` (env) | 3s under new-wins policy |
| `3s` (env) | `20s` (YAML) | 3s |

If policy requires ignoring an invalid legacy value whenever the new key is present, the example code must be replaced; testing `old=bad / new=3s` catches this distinction.

For Strings, an empty string `""` can be treated as a supplied yet invalid value. Do not silently treat it as Missing unless policy explicitly states so.

## 22. Testing Warnings Without Printing Secret Values

During migration, verify startup logs include the legacy name and replacement name while never containing values.

Safe message:

~~~text
Property app.client.request-timeout is deprecated.
Use app.client.timeout instead.
~~~

For secret keys:

~~~text
Deprecated property app.auth.legacy-token is set.
Use app.auth.token.
~~~

**Never** log:

~~~text
Deprecated token=REAL_TOKEN_HERE
~~~

Remember Java records auto-generate `toString()`. Never log an entire `@ConfigurationProperties` bean if it holds passwords or tokens.

When building metrics to track adoption, emit only key names or boolean status, avoiding values and high-cardinality labels.

## 23. Testing Profiles and Real Files with `@SpringBootTest`

Suppose:

~~~yaml
# application.yaml
app:
  client:
    request-timeout: 10s
~~~

~~~yaml
# application-prod.yaml
app:
  client:
    timeout: 3s
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ClientProdConfigTest {

    @Autowired
    ClientSettings settings;

    @Test
    void readsCanonicalPropertyFromProdProfile() {
        assertThat(settings.timeout())
                .isEqualTo(Duration.ofSeconds(3));
    }
}
~~~

`ClientSettingsConfiguration` must be discovered/registered in the application context.

Do not add:

~~~java
@SpringBootTest(properties = "app.client.timeout=3s")
~~~

to the very test meant to verify `application-prod.yaml`, because test properties override the file and can pass even if the file is broken.

## 24. Kubernetes, ConfigMap, Secret, and Environment

Old Deployment:

~~~yaml
env:
  - name: APP_CLIENT_REQUESTTIMEOUT
    value: "7s"
~~~

New Deployment:

~~~yaml
env:
  - name: APP_CLIENT_TIMEOUT
    value: "3s"
~~~

When using `configMapKeyRef`, check both `env.name` and `configMapKeyRef.key`:

~~~yaml
env:
  - name: APP_CLIENT_TIMEOUT
    valueFrom:
      configMapKeyRef:
        name: client-settings
        key: timeout
~~~

Keys inside a ConfigMap do not automatically rename when you rename an env var. If using `envFrom`, valid keys in the ConfigMap/Secret become env var names, so update the source keys.

For Secrets, never put literal credentials inside Deployments. Use `secretKeyRef` or secret volumes with proper permissions and rotation.

### Running Pod Env Vars Do Not Auto-Update

When a ConfigMap or Secret supplying environment variables changes, environment variables inside already-running containers do not automatically update. Pods must be recreated/rolling-restarted to pick up new values. During a rollout, multiple Pod generations using different property names may therefore run concurrently.

This makes a compatibility window even more critical than local single-instance testing suggests.

## 25. Configtree Imports Require Filename or Path Mapping Updates

Suppose runtime mounts:

~~~text
/run/secrets/app.client.request-timeout
~~~

and the app imports:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

That file creates the property `app.client.request-timeout`. Renaming a Java field does not rename the mounted file.

The new migration can rename it to:

~~~text
/run/secrets/app.client.timeout
~~~

If both files coexist, the resolver must apply the defined new-vs-old policy. Do not expect Spring Boot's `configtree:` to understand aliases automatically.

Kubernetes may update secret volume files after a propagation delay, yet Spring Boot beans bound at startup **are not guaranteed to refresh** on file updates. Furthermore, `subPath` mounts have their own update limitations.

### Safe Rollout Sequence

1. Deploy the app version that accepts both keys.
2. Wait until old Pods are replaced.
3. Switch mounts/configs to the new key.
4. Verify connectivity and that expected settings took effect without printing secrets.
5. Remove the old file once rollback is no longer needed.
6. Remove the alias only in a subsequent scheduled release.

## 26. Phased Sunset Process

### Phase A — Introduce and Warn

- Add the canonical key.
- Add dual binding or an alias resolver.
- Define policy when both keys exist.
- Add deprecation metadata.
- Update example configs to use the new key.
- Write tests for old-only, new-only, both, missing, and invalid.
- Document in changelog and migration guide.

### Phase B — Observe Adoption

- Warn once at startup when the legacy key is used.
- Inventory environments still using the old key without logging values.
- Update ConfigMaps, Secret references, Helm values, and CI/CD.
- Coordinate with operators and consumer teams.
- Preserve rollback capability.
- Build adoption dashboards or reports if needed.

### Phase C — Tighten Compatibility

- Publish a firm deadline.
- Optionally escalate from warning to fail-on-conflict after notice.
- Test release candidates without the alias in staging.
- Ensure no remaining deployments use the old key.
- Audit infrequently deployed workloads such as batch jobs and disaster recovery.

### Phase D — Removal

- Remove the legacy field and resolver logic.
- Update metadata and docs to reflect the new state.
- Add a startup guard or test to catch the old key.
- Document the breaking change in release notes.
- Verify production and recovery environments.

**Important:** merely deleting the legacy field from `@ConfigurationProperties` causes Binder to **silently ignore** the old key. To reject it with a clear error, add an explicit key-presence check covering real configuration sources.

## 27. Startup Guard After Alias Removal

You can build a guard to reject the legacy key.

Conceptual example:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class LegacyPropertyGuard {

    public LegacyPropertyGuard(Environment environment) {
        if (environment.containsProperty(
                "app.client.request-timeout")) {
            throw new IllegalStateException(
                "app.client.request-timeout was removed; "
                + "use app.client.timeout");
        }
    }
}
~~~

This illustrates key-based fail-fast, yet `Environment.containsProperty` does not necessarily cover relaxed binding variants across every OS env, CLI, or configtree source. Test every source production uses, or build the guard against a compatible configuration property source abstraction.

### Why Include a Guard?

Removing a field from Java does not make the old property fail. If the old key is ignored and the new field is missing or defaulted, the app may run with wrong defaults.

A good removal experience produces an explicit error:

~~~text
Legacy property app.client.request-timeout is no longer supported.
Set app.client.timeout instead.
~~~

rather than silently ignoring it.

## 28. Rollout and Rollback Must Be Designed Together

In distributed systems, four combinations occur:

| App Version | Config Name | Expectation |
| --- | --- | --- |
| Old app | Old key | Works as before. |
| New app with compatibility | Old key | Works and warns. |
| New app with compatibility | New key | Works. |
| Old app | New key | May not understand; rollback is risky. |

If you may need to roll back to the old app after updating to the new config, ensure the old app still receives config it understands, or roll back config in lockstep.

A practical sequence:

1. **Code first:** deploy the version supporting both old and new.
2. **Config second:** switch to the new key in config-as-code and runtime.
3. **Observe:** check startup, health, business behavior, and warnings.
4. **Remove old:** after the rollback window closes.
5. **Sunset:** ship the version rejecting the legacy key with prior notice.

Do not delete old secrets or files prematurely while older instances may still depend on them.

## 29. Writing an Actionable Migration Guide

A clear notice includes all necessary details:

~~~text
Deprecated since: 1.8 (example)
Legacy: app.client.request-timeout
Replacement: app.client.timeout

Old:
  app.client.request-timeout=5s

New:
  app.client.timeout=5s

During transition:
  - Both names accepted.
  - New name takes precedence.
  - Legacy name produces a startup warning.
  - Missing both is an error.

Removal target:
  2.0, subject to rollout completion.

Actions:
  - Update YAML/Properties.
  - Update APP_CLIENT_REQUESTTIMEOUT to APP_CLIENT_TIMEOUT.
  - Update Helm/ConfigMap/secret filenames as necessary.
  - Run compatibility tests.
~~~

Version numbers are illustrative; teams must publish exact milestones and responsibilities for consuming groups.

If types or units changed, the migration guide must show how to convert values, not just state a rename.

## 30. CI/CD Can Help Catch Legacy Keys

For version-controlled deployment configs, pipelines can scan for:

~~~text
app.client.request-timeout
APP_CLIENT_REQUESTTIMEOUT
--app.client.request-timeout
~~~

Avoid false positives in:

- Migration guide docs.
- Tests intentionally checking the legacy alias.
- Compatibility code still within its support window.
- Historical release notes.

Scan scoped to real deployment files with managed exemptions rather than blindly banning all occurrences repo-wide.

A Git-only pipeline still cannot guarantee runtime is free of old keys: secret managers, manual systemd units, CI variables, or cluster environments may live outside the repository.

## 31. Comprehensive Test Matrix

| Category | Case | Expected Check |
| --- | --- | --- |
| Basic | New only | Uses new |
| Compatibility | Old only | Uses old, warns |
| Conflict | Both old and new | Precedence policy enforced |
| Missing | Neither present | Valid default or fails |
| Validation | New=0/negative | Fails |
| Conversion | New=bad | Clear failure |
| Conversion | Old=bad, new good | Per implementation's binder policy |
| Precedence | Old env, new YAML | Follows cross-name policy |
| Precedence | Old YAML, new env | Follows cross-name policy |
| Profiles | Profile-specific files | Config Data loads properly |
| Environment | Old/new env names | Binding works |
| Mounted files | Old/new files | Configtree root and property name correct |
| Metadata | Old deprecated | IDE metadata shows replacement |
| Logging | Old present | Warning omits value |
| Removal | Old after sunset | Explicitly rejected |
| Rollback | Old app + new config | Compatibility/rollback plan verified |

Testing `new=3s` and `old=7s` only inside the **same property source** misses cross-source scenarios that often surprise teams in production.

## 32. Common Mistakes

### Mistake 1 — Renaming Only the Java Field
Existing deployments do not update themselves. Build a compatibility layer or schedule a breaking release.

### Mistake 2 — Assuming Relaxed Binding Handles Any Alias
`request-timeout` and `timeout` differ semantically and are not mapped automatically.

### Mistake 3 — Assuming `@DeprecatedConfigurationProperty` Remaps Keys
Metadata informs tooling only; it does not alter runtime logic.

### Mistake 4 — Putting `@DefaultValue` on the New Field Before Migration Logic
It can mask an explicitly supplied legacy value; apply defaults after resolving aliases.

### Mistake 5 — Leaving Concurrent Old/New Behavior Undefined
Business services may disagree or depend on arbitrary evaluation order.

### Mistake 6 — Ignoring Source Precedence
New in YAML vs old in env produces different outcomes under new-wins vs highest-source-wins policies.

### Mistake 7 — Ignoring Conversion of the Unselected Key
When binding two typed fields, an invalid legacy type can still fail startup.

### Mistake 8 — Changing Name and Unit Together Without Conversion
Operators copy old numbers onto the new key and get unexpected timeouts.

### Mistake 9 — Updating Only YAML Inside the Repo
Helm charts, ConfigMaps, Secrets, env vars, CLI args, and production runtimes still hold the old key.

### Mistake 10 — Keeping `properties-migrator` Permanently
An upgrade helper is not a general-purpose alias engine for custom application keys.

### Mistake 11 — Logging Secret Values in Warnings
Log only old/new property names and status, never tokens or passwords.

### Mistake 12 — Neglecting Rollback
Older app binaries may not understand the new config; ship code before switching config.

### Mistake 13 — Removing the Field Without a Removal Guard
The old key may be silently ignored; add checks so it fails clearly after sunset.

### Mistake 14 — Setting a Removal Date Without Tracking Adoption
Infrequently run workloads like batch jobs, staging, or DR may still rely on the old key.

## 33. Exercises with Answers

### Exercise 1 — Relaxed Binding vs Rename
`app.client.requestTimeout` vs `app.client.request-timeout` can be spelling variants of one property; `app.client.timeout` is a different key requiring migration. **Answer:** true.

### Exercise 2 — Legacy Only
`app.client.request-timeout=7s`, new absent. **Answer:** during transition, select 7s and warn.

### Exercise 3 — Both Keys
Old=7s, new=3s. **Answer:** under new-wins policy, use 3s and log conflict.

### Exercise 4 — Neither Present
Timeout is required. **Answer:** fail fast; do not invent an arbitrary default.

### Exercise 5 — `@DefaultValue` Bug
Legacy=20s, new field has default 5s. **Answer:** the new default masks legacy; apply default after selection.

### Exercise 6 — New in YAML, Old in Env
New=3s, old=20s. **Answer:** under name-first new-wins policy, pick 3s even though old sits in a higher-precedence source.

### Exercise 7 — Legacy Invalid Type
New=3s, old=not-a-duration, raw input class uses two `Duration` fields. **Answer:** fails at Binder before the resolver runs; to avoid this, design conversion after key selection.

### Exercise 8 — Deprecated Annotation
`@DeprecatedConfigurationProperty(replacement="app.client.timeout")` is present. **Answer:** does not create a runtime alias automatically.

### Exercise 9 — Environment Variables
Old `APP_CLIENT_REQUESTTIMEOUT`, new `APP_CLIENT_TIMEOUT`. **Answer:** update variable names and test at runtime.

### Exercise 10 — Configtree File
Old file `/run/secrets/app.client.request-timeout`. **Answer:** rename the file/path mapping or maintain a runtime alias; Java renames do not rename files.

### Exercise 11 — Rollback
Old app knows only legacy; config already switched to new. **Answer:** rolling back the app can break; roll back config in parallel or keep the old key during the rollback window.

### Exercise 12 — Removal
Old field deleted from the record. **Answer:** the old key is not guaranteed to fail; write a guard and test it.

### Exercise 13 — Prefix Migration
`legacy.billing.*` → `payments.billing.*`. **Answer:** map each key, type, default, and secret policy; do not merely change the prefix annotation.

### Exercise 14 — Logging Deprecated Tokens
**Answer:** log only legacy/replacement key names, never values.

### Exercise 15 — CI Scan
Old name appears in migration docs and compatibility tests. **Answer:** distinguish legitimate occurrences from active deployments using old keys; avoid blind search-and-replace bans.

## 34. Release Checklist

- [ ] Old → new table with type, unit, default, and requiredness.
- [ ] Defined policy for old-only / new-only / both / neither.
- [ ] Tested conversion errors and zero/blank values.
- [ ] Tested old/new across different precedence sources.
- [ ] Business code consumes only normalized configuration.
- [ ] Deprecation metadata specifies replacement.
- [ ] Runtime warnings log key names only, never secrets.
- [ ] YAML/Properties/Helm/ConfigMap/Secret/env/CLI/CI inventoried.
- [ ] Sample configs and runbooks updated to the new key.
- [ ] Rollback across both app/config generations accounted for.
- [ ] Sunset milestone and adoption tracking in place.
- [ ] After removal, old keys are detected instead of silently ignored.
- [ ] No compatibility code retained without an owner or deadline.

## 35. Summary

Renaming a property in Spring Boot is an **operational contract change**. A controlled approach:

1. Introduce the canonical name while preserving the legacy name for an announced window.
2. Bind both names and normalize into a single object so business code sees only the new name.
3. Explicitly specify precedence and handling of invalid, blank, or missing values.
4. Use configuration metadata to inform tooling of deprecation—**never confuse metadata with runtime aliases**.
5. Thoroughly test `Binder`, application context, profiles, environment variables, and mounted files where applicable.
6. Update deployments and documentation in a rollback-safe order.
7. Monitor remaining usage of the old key, then remove it on schedule with clear fail-fast behavior.

Good compatibility does not mean keeping aliases forever. It means giving consumers time and tooling to migrate while keeping the final configuration contract clean, explicit, and well-tested.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html).
- [Spring Boot — Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html).
- [Spring Boot — DeprecatedConfigurationProperty API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/DeprecatedConfigurationProperty.html).
- [Spring Boot — Binder API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html).
- [Spring Boot — ApplicationContextRunner API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html).