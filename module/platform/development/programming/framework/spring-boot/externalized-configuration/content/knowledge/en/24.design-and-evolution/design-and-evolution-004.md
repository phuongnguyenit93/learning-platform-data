# Managing Optional and Required Keys per Environment in Spring Boot

## 1. The Problem to Solve

A Spring Boot application typically runs across multiple environments: local, development, test, staging, and production. Each environment may use the same application artifact while requiring different configuration. For instance, local may use a mock service, whereas production must have a real endpoint, authentication credentials, and strict operational limits.

Suppose a configuration group:

~~~yaml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
    api-token: "DEMO-ONLY"
    connect-timeout: 3s
    max-retries: 2
~~~

The design question is not merely what value each key takes, but:

- Which keys are **required in every environment**?
- Which keys are required only when a feature is enabled?
- Which keys have safe defaults and can be omitted?
- Which keys are required in staging/production yet optional when running locally?
- Are a missing key and an empty value treated the same?
- Should the system fail fast or fall back?
- When renaming a key, how do you upgrade without breaking existing deployments?
- How do you test to catch errors before release?

The goal of this lesson is to design a **per-environment configuration contract**, not just write an `application-prod.yml` file. That contract should be expressed through a Java schema, validation, secret delivery sources, documentation, and tests.

## 2. Concepts to Separate

| Term | Meaning | Example |
| --- | --- | --- |
| Required property | Must be supplied and valid within the defined scope | `app.partner.base-url` |
| Optional property | May be absent while the application remains valid | `app.partner.proxy-host` |
| Default value | Value used when no configuration is provided | `connect-timeout=3s` |
| Conditionally required | Required only when a condition holds | `api-token` when `partner.enabled=true` |
| Environment-specific required | Required in specific environments | Real token in production |
| Invalid value | Key is present but fails type/constraint checks | `max-retries=-5` |
| Missing value | No effective source provides the key | Missing `base-url` |
| Empty/blank value | Key is present with an empty string or whitespace | `api-token=""` |

A property can be optional in terms of presence, yet if supplied it must still be **valid in type and range**. For instance, `max-retries` defaults to 2, yet when `-20` is entered it must not silently revert to 2.

On the other hand, a key required in production is not necessarily required locally. The problem needs explicit rules to prevent environment differences from turning into accidental behavior.

## 3. Do Not Confuse "Key Present" with "Usable Value"

Consider three cases:

~~~properties
# app.partner.api-token is completely absent
~~~

~~~properties
app.partner.api-token=
~~~

~~~properties
app.partner.api-token=   
~~~

With a `String` target, these cases may bind to `null`, an empty string, or a whitespace-only string depending on the source and pipeline.

If a credential must contain text, the annotation:

~~~java
@NotNull String apiToken
~~~

is not enough, because `""` is still non-null.

A usually better choice:

~~~java
@NotBlank String apiToken
~~~

in a validation-enabled configuration bean. `@NotBlank` checks null, empty strings, and whitespace-only strings. However, it does not prove the token is active, has the right scopes, or belongs to the right environment.

In schema docs, specify what "required" means: merely non-null, non-blank, matching a format, or satisfying a relationship with another field.

## 4. Per-Environment Configuration Contract Table

Before writing Java code, create a reviewable table:

| Property | Local | Test | Staging | Production | Default / Rules |
| --- | --- | --- | --- | --- | --- |
| `app.partner.enabled` | Optional | Optional | Required | Required | Local/test default false |
| `app.partner.base-url` | When enabled | When enabled | When enabled | When enabled | Never default to production |
| `app.partner.api-token` | Optional when stubbed | Fake token if needed | Required when enabled | Required when enabled | Supplied via secret source |
| `app.partner.connect-timeout` | Optional | Optional | Optional | Optional | `3s`, must be positive |
| `app.partner.max-retries` | Optional | Optional | Optional | Optional | `2`, range 0–5 |
| `app.partner.proxy-host` | Optional | Optional | Optional | Optional | Absence means no proxy |
| `app.partner.tls-enabled` | Optional | Optional | Required | Required | Production enforces true by policy |

This table is only a **policy example**. TLS, proxy, or feature flag conditions must reflect your application's actual threat model and requirements.

Columns needed in a large project's schema documentation:

- Canonical property name and Java type.
- Required/optional status per environment.
- Default and its meaning.
- Valid values or constraints.
- Dependencies on other fields.
- Allowed configuration sources.
- Whether it is a secret.
- Owner and required reviewers for changes.
- App/schema versions supporting the property.
- Migration/deprecation path when upgrading.

The contract table should be versioned alongside the code or in an audited documentation system.

## 5. A Java Schema with Basic Requirements

Record example:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @NotNull @DefaultValue("false") Boolean enabled,
        String baseUrl,
        String apiToken,
        @NotNull @DefaultValue("3s") Duration connectTimeout,
        @Min(0) @Max(5) @DefaultValue("2") int maxRetries
) {}
~~~

Interpretation:

- `enabled` defaults to `false`, so **deployers are not forced to supply it** in this example.
- `connectTimeout` defaults to 3 seconds and can be omitted if that value is acceptable.
- `maxRetries` defaults to 2, yet supplying `-5` violates `@Min(0)`.
- `baseUrl` and `apiToken` currently allow null; conditional requirements are designed separately below.
- `@Validated` requests constraint validation when the `@ConfigurationProperties` bean is created via a suitable mechanism with a Bean Validation provider present.

When `enabled` **must be explicitly declared** in production, do not attach a `false` default to that field in the production schema. A default fine for local development may be wrong for production.

## 6. Validation Dependencies

For Spring Boot 3.x, Jakarta Bean Validation constraints typically require:

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

### Gradle Groovy DSL

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Common annotations:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
~~~

Do not mix legacy `javax.validation` and modern `jakarta.validation` namespaces in Spring Boot 3.x.

Register the properties bean properly:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Or use `@EnableConfigurationProperties(PartnerProperties.class)` on an intentional configuration class.

**The configuration processor** for IDE metadata is distinct from the **validation starter**; adding `spring-boot-configuration-processor` does not enforce `@NotBlank`.

## 7. Primitives vs Wrappers When Checking Required Keys

Consider:

~~~java
@ConfigurationProperties(prefix = "app.jobs")
public record JobProperties(
        int workers,
        boolean enabled
) {}
~~~

When properties are absent, primitives receive Java defaults like `0` and `false`. Code then struggles to distinguish:

- The deployer intentionally set `enabled=false`.
- The deployer forgot to declare `enabled`.

When presence must be checked, use wrappers:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.jobs")
public record JobProperties(
        @NotNull @Min(1) Integer workers,
        @NotNull Boolean enabled
) {}
~~~

Without a value or default, nullable fields remain null so the validator rejects them.

Notes:

- `@NotNull Boolean enabled` allows both `true` and `false`.
- `@NotNull boolean enabled` cannot detect absence because a primitive cannot be null.
- `@Min(1) int workers` rejects 0, yet does not distinguish missing from explicitly passing 0.
- A nullable wrapper with `@NotNull` fits when a required contract needs an explicit distinction.

## 8. `@NotNull`, `@NotEmpty`, and `@NotBlank`

| Constraint | Used For | Violation |
| --- | --- | --- |
| `@NotNull` | Nullable objects | Null |
| `@NotEmpty` | String, collection, map, array | Null or empty |
| `@NotBlank` | String/CharSequence | Null, empty, or whitespace-only |

Example:

~~~java
public record MailSettings(
        @NotBlank String senderAddress,
        @NotEmpty java.util.List<String> recipients,
        @NotNull Boolean sendEnabled
) {}
~~~

If `senderAddress="  "`, `@NotBlank` catches it. If `recipients=[]`, `@NotEmpty` catches it. If `sendEnabled=false`, `@NotNull` **passes**.

Do not put `@NotBlank` on `Duration` or `Integer`; that constraint is not intended for those types.

Many fields also need range constraints such as `@Min`/`@Max` or `@Size`. Required does not mean valid: a non-blank String can still be an invalid URL or email.

## 9. Defaults via `@DefaultValue` vs Required

Constructor binding with a record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue("2") int maxRetries
) {}
~~~

When the key is absent, the Binder uses the annotation default. Yet if runtime passes:

~~~properties
app.http.connect-timeout=tomorrow
~~~

the `3s` default does not auto-heal the mistyped value. Conversion fails.

Similarly:

~~~properties
app.http.max-retries=-1
~~~

still requires a constraint or business validation if negative numbers are disallowed.

Governance rule:

- **Default:** absence is allowed and has a sensible substitute.
- **Required:** absence is a configuration error to fix at the source.
- **Optional/no default:** absence has its own meaning and code intentionally handles null/absence.

Never add defaults haphazardly just to avoid startup failures; doing so hides deployment bugs.

## 10. Defaults in YAML and Placeholders

Example:

~~~yaml
app:
  http:
    connect-timeout: "${HTTP_CONNECT_TIMEOUT:3s}"
~~~

If `HTTP_CONNECT_TIMEOUT` is unset, the placeholder falls back to `3s`.

Conversely:

~~~yaml
app:
  partner:
    api-token: "${PARTNER_API_TOKEN}"
~~~

has no default. When the property is actually resolved and bound, a missing variable should be treated as an error if the value is required.

A subtle pitfall:

~~~yaml
app:
  partner:
    api-token: "${PARTNER_API_TOKEN:}"
~~~

The trailing colon supplies an **empty string fallback**. If bound to a `String`, an empty string exists even though the variable was unset. When a token is required, `@NotBlank` is an essential safeguard.

Do not rely solely on default-less placeholders assuming every path fails fast: if the property is never read or its bean is not created, the error may not surface at startup as expected.

## 11. `Optional<T>` Is Not Recommended by Default in `@ConfigurationProperties`

Java has `Optional<String>`, yet avoid declaring:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        java.util.Optional<String> proxyHost
) {}
~~~

assuming the Binder always supplies `Optional.empty()` when missing. Spring Boot documentation discourages `Optional` as a `@ConfigurationProperties` field type; when no value is set, the result can be null rather than the expected `Optional`.

A cleaner alternative:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        String proxyHost
) {}
~~~

Then at usage sites:

~~~java
if (properties.proxyHost() != null
        && !properties.proxyHost().isBlank()) {
    configureProxy(properties.proxyHost());
}
~~~

If internal code genuinely needs an `Optional` model, convert after binding and test the semantics explicitly.

## 12. Environment-Specific Requirements: Two Design Patterns

Two common patterns exist.

**Approach A — One schema, conditionally required per field.** For example, `apiToken` is required only when `enabled=true`. This does not depend on profile names and fits when the primary driver is a feature mode.

**Approach B — Profile-specific schemas or bean registrations.** For example, production requires a compliance properties group that local does not instantiate. This fits when contracts truly differ across environments.

Do not turn profile names into free-form strings queried across random classes to check individual fields. The more scattered the contract, the harder it is to enforce consistently.

In both patterns, profile-specific YAML files are merely **sources of values**. Requiredness rules should be expressed in Java validation and/or testable deployment policies.

## 13. Conditionally Required: When a Feature Is Enabled

Suppose the token is needed only when actually calling upstream:

~~~yaml
app:
  partner:
    enabled: false
~~~

With the feature off, omitting the token is valid. Yet if:

~~~yaml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
~~~

then a missing token must fail fast.

One way to express invariants right in the constructor:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @DefaultValue("false") boolean enabled,
        String baseUrl,
        String apiToken,
        @DefaultValue("3s") Duration connectTimeout
) {
    public PartnerProperties {
        if (enabled) {
            if (baseUrl == null || baseUrl.isBlank()) {
                throw new IllegalArgumentException(
                        "app.partner.base-url is required when enabled");
            }
            if (apiToken == null || apiToken.isBlank()) {
                throw new IllegalArgumentException(
                        "app.partner.api-token is required when enabled");
            }
        }
        if (connectTimeout == null
                || connectTimeout.isZero()
                || connectTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.partner.connect-timeout must be positive");
        }
    }
}
~~~

This is a **constructor invariant**, not Jakarta Bean Validation. It prevents constructing an invalid object, though the exception message format differs from Bean Validation constraint violations.

Important: the exception names only the **property key**, never printing the token value or the full config record.

If reuse or standard Jakarta constraint reporting is desired, write a custom class-level constraint validating `enabled`/`baseUrl`/`apiToken` instead of constructor checks.

## 14. Do Not Rely Solely on `@ConditionalOnProperty` to Enforce Requiredness

A configuration bean can depend on a flag:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.partner",
            name = "enabled",
            havingValue = "true"
    )
    PartnerClient partnerClient(PartnerProperties properties) {
        return new PartnerClient(
                properties.baseUrl(),
                properties.apiToken()
        );
    }
}
~~~

`PartnerClient` is a hypothetical application-defined class.

That condition decides **whether to create the bean**, not whether `apiToken` is non-blank. If `enabled=true` and token is null, the bean can fail later or slip through misconfigured without validation.

Conversely, if the bean is not created when the feature is off, an absent token may be valid under the contract.

Distinguish:

- **Conditional bean registration:** under what conditions a bean is created.
- **Required property validation:** what constraints fields must satisfy.
- **Runtime health:** whether the remote service is actually reachable.

These three responsibilities do not substitute for one another.

## 15. `@ConditionalOnProperty` and Missing Values

Example:

~~~java
@ConditionalOnProperty(
        prefix = "app.partner",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
~~~

When the property is absent, the condition does not match under this policy. Yet that does not force an environment to declare `enabled=false` explicitly.

If production requires **the `enabled` key to be present**, use a separate required check—such as a default-less `Boolean` wrapper with `@NotNull` registered in production, or a deploy-time check.

`matchIfMissing=true` allows bean creation when a property is absent; that is a bean registration choice, not confirmation that omitting the key is valid under the business contract.

In particular, for collection/indexed properties, Spring Boot docs note limitations when using `@ConditionalOnProperty` on collection structures; do not turn it into a general schema validator.

## 16. Separating Production and Non-Production Beans

When requiredness policies differ sharply, beans can be registered by profile.

Example contract strictly for production:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record ProductionPartnerProperties(
        @NotNull Boolean enabled,
        @NotBlank String baseUrl,
        @NotBlank String apiToken
) {}
~~~

Bean registration:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("prod")
@EnableConfigurationProperties(ProductionPartnerProperties.class)
public class ProductionPartnerConfiguration {}
~~~

With this pattern, do not simultaneously scan `ProductionPartnerProperties` via a broad `@ConfigurationPropertiesScan`, which could register it outside `prod`. Pick **one explicit bean registration strategy** and test it.

In non-production environments, you can use a different properties class or a mock/stub client registered under `@Profile("!prod")`. When two classes share a prefix, avoid injecting the wrong type or causing duplicate-bean ambiguity.

The profile name `prod` is purely a project convention; Spring Boot does not treat it as intrinsically security-enforced. Deployment pipelines must ensure the right profile is activated.

## 17. Do Not Gate Validation on Environment by Guessing Hostnames

An anti-pattern:

~~~java
if (hostname.contains("prod")) {
    requireApiToken();
}
~~~

or:

~~~java
if (System.getenv("ENV_NAME").equals("production")) {
    ...
}
~~~

without null guards or controlled provisioning.

Risks:

- Hostnames change under auto-scaling.
- Staging may accidentally contain the substring `prod`.
- CI fails to reproduce the condition accurately.
- Required logic scatters without a central contract.
- A mistyped env variable silently disables validation in a critical environment.

Use explicitly managed signals: profiles, deployment policies, explicit mode settings, and tests verifying combinations.

For critical security constraints, enforce additional checks in **deployment policy** instead of trusting only a runtime flag that deployers can override.

## 18. Profiles Select Sources/Config, Not Enforce Required Schemas by Themselves

Production example:

~~~yaml
# application-prod.yml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
    api-token: "${PARTNER_API_TOKEN}"
~~~

This file supplies values when `prod` is activated. Requiredness semantics come from the registered properties type and validation, not merely from `prod` in the filename.

Test cases to cover:

1. `prod` active and `PARTNER_API_TOKEN` populated: bean is created.
2. `prod` active and variable absent: bind/resolve/validation fails by design.
3. `prod` active with empty string: `@NotBlank` rejects it.
4. `prod` inactive: stub can be used without binding production beans unnecessarily.
5. CLI/env overrides `enabled` or token: system follows the policy.

When multiple profiles are active concurrently, define clear ordering and expectations; never infer behavior from a single profile name alone.

## 19. `spring.config.import=optional:` Differs from Optional Keys

Example:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

The `optional:` prefix on Config Data imports means **do not fail solely because the import location does not exist** in that context. It does not mean every property beneath that location is business-optional.

If production requires:

~~~properties
app.partner.api-token
~~~

the properties bean must still enforce its own required/validation rules. If the mounted directory is missing and the import is marked optional, Spring skips the source, and then token validation (if properly registered) catches the missing value.

Conversely, if the secrets location must always exist, use a non-optional import or verify mounts/secret references at deploy time. Yet even a directory existing **does not prove the right secret file and value are present**.

Distinguish:

- Optional **config location**: file or directory may be absent.
- Optional **business property**: application remains valid when a key is omitted.
- Optional **feature**: a subsystem may not run.

## 20. A Schema for Nested Objects

Suppose configuration:

~~~yaml
app:
  client:
    name: catalog
    connection:
      host: api.example.org
      port: 443
~~~

Java:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @NotBlank String name,
        @NotNull @Valid Connection connection
) {
    public record Connection(
            @NotBlank String host,
            @Min(1) @Max(65535) int port
    ) {}
}
~~~

Here:

- `@NotNull` requires the entire `connection` group to be present.
- `@Valid` directs the validator into the nested object.
- `@NotBlank` requires a non-blank host.
- `@Min` and `@Max` validate the port range.

A null nested object is not automatically instantiated just by `@Valid`; when the group is required, `@NotNull` and nested creation must be designed appropriately.

If `connection` is only needed when a feature is enabled, avoid unconditional `@NotNull` at the root if that forces local stub mode to supply a host. Use conditional constraints, mode-split schemas, or separate registration.

## 21. List and Map: Requiredness for Container and Elements

An endpoint list:

~~~yaml
app:
  gateways:
    - name: primary
      url: https://primary.example.org
    - name: backup
      url: https://backup.example.org
~~~

Java:

~~~java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record GatewayProperties(
        @NotEmpty List<@Valid Gateway> gateways
) {
    public record Gateway(
            @NotBlank String name,
            @NotBlank String url
    ) {}
}
~~~

`@NotEmpty` requires at least one list element. `@Valid` cascades validation to each element. If the list is optional, omit `@NotEmpty` unless required by the scope or mode.

With `Map`, container constraints and cascading also apply:

~~~java
@NotEmpty Map<String, @Valid Tenant> tenants
~~~

However, lists, maps, and nested objects have distinct binding semantics. Never assume lists merge across property sources; a higher-precedence source replaces the list.

When each environment must have at least one endpoint, test against the **effective result**, not individual files in isolation.

## 22. Requiring a Boolean to Be True in Production

Example policy requiring TLS:

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public record ProductionSecurityProperties(
        @NotNull @AssertTrue Boolean tlsEnabled
) {}
~~~

`@NotNull` requires a value; `@AssertTrue` requires true. Note that Bean Validation `@AssertTrue` normally considers null valid, so pair it with `@NotNull` to catch missing keys.

Place these constraints on a bean actually registered for production, or inside an explicit conditional custom constraint. Do not default to `true` if policy requires deployers to **declare it explicitly**.

For security settings, infrastructure-level enforcement may also be needed beyond bean-level validation, such as enforcing HTTPS/TLS at ingress or service mesh.

## 23. Validating Positive Durations

~~~java
@NotNull Duration requestTimeout
~~~

checks only for non-null; `0s` binds as `Duration.ZERO` and passes `@NotNull`.

One constructor check:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(Duration requestTimeout) {
    public HttpProperties {
        if (requestTimeout == null
                || requestTimeout.isZero()
                || requestTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "app.http.request-timeout must be positive");
        }
    }
}
~~~

This is a constructor invariant. If needed repeatedly across many properties classes, write a custom Jakarta Bean Validation constraint specifically for `Duration`.

Do not place `@Positive` directly on `Duration` assuming the provider treats it like a number; `@Positive` applies to numeric types supported by Bean Validation.

## 24. Detecting Extra Keys or Typos

Suppose:

~~~yaml
app:
  partner:
    connect-timeout: 3s
    max-retrise: 4
~~~

If the Java class only has `maxRetries`, `max-retrise` has no matching target. Standard binding ignores unknown properties, leaving defaults intact and misleading operators.

Inside a namespace owned by one properties class, you can use:

~~~java
@ConfigurationProperties(
        prefix = "app.partner",
        ignoreUnknownFields = false
)
public record PartnerProperties(
        Duration connectTimeout,
        int maxRetries
) {}
~~~

This enables stricter checking for unbound keys within the right scope. However, if multiple subsystems share a prefix, enabling strict unknown-field checking on too broad a root can reject valid keys belonging to other subsystems.

Keep distinct:

- **Missing required key:** a required key is absent.
- **Unknown/unbound key:** a key exists with no schema field.
- **Invalid value:** a key exists, yet conversion or validation fails.

All three failure modes should be tested independently.

## 25. Do Not Use `ignoreInvalidFields=true` to Hide Errors

Example:

~~~java
@ConfigurationProperties(
        prefix = "app.http",
        ignoreInvalidFields = true
)
~~~

can cause binding errors to be silently ignored. If a mistyped value leaves a field at its default, the app may run with unintended settings.

For important configurations, keep strict behavior:

- Type errors should fail rather than silently fall back to defaults.
- Constraint violations should fail.
- Unbound keys should be caught if the namespace demands strictness.
- Error messages should clearly state the property name without leaking secrets.

Never use `ignoreInvalidFields` as a substitute for a required/optional policy.

## 26. Per-Environment Required Secrets

Example where production requires a token while local uses a stub:

~~~yaml
# application-local.yml
app:
  partner:
    enabled: false
~~~

~~~yaml
# application-prod.yml
app:
  partner:
    enabled: true
    base-url: https://partner.example.org
    api-token: "${PARTNER_API_TOKEN}"
~~~

In production, supply the token via a secret manager, mounted file, or organization-approved channel. Never commit real tokens into YAML.

Principles:

1. Secrets must have a reference, owner, and rotation policy.
2. Never log `apiToken` when reporting missing or invalid errors.
3. Never use real secrets in unit tests.
4. When a profile does not need a token, do not require loading production secrets locally.
5. When the feature is enabled, missing tokens must be rejected before serving requests.
6. Never confuse "non-blank token" with "valid token at upstream".
7. Deployments must verify secret references and workload permissions.

Use fake sentinels like `TEST_ONLY_TOKEN` when testing binding; never use credentials with real privileges.

## 27. Optional Keys Do Not Permit Dereferencing Null

If `proxyHost` is optional:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        String proxyHost
) {}
~~~

Buggy code:

~~~java
String normalized = properties.proxyHost().trim();
~~~

When no proxy host is set, this throws `NullPointerException`.

Express semantics clearly:

~~~java
String proxyHost = properties.proxyHost();

if (proxyHost != null && !proxyHost.isBlank()) {
    configureProxy(proxyHost.trim());
} else {
    useDirectConnection();
}
~~~

If null and blank carry different meanings, state that explicitly in the schema—for instance, null means no proxy, while a blank string is an invalid config rather than silently equating the two.

An optional field may also carry constraints when present—for instance, `proxyPort` must be 1–65535 if `proxyHost` is set. That is cross-field validation.

## 28. Local, Test, Staging, and Production Environments Are Not Uniform

A sample policy:

### Local

- Allows mock HTTP clients and embedded databases.
- Provides safe defaults for timeouts and retries.
- Uses no production credentials.
- Includes sample files showing fake placeholder values.
- Can disable optional integrations.

### Test/CI

- Tests must be reproducible with controlled values.
- Must not depend on accidental developer machine environment variables.
- Tests required missing, blank, invalid, and config overrides.
- Credentials used in tests are fake sentinels.
- Testing the production profile does not require connecting to real external systems when only checking binding.

### Staging

- Closely mirrors production policy for required fields.
- Secrets and endpoints are isolated from production.
- Validates schema, security, and readiness.
- Tests configuration upgrades with upcoming app versions.

### Production

- Never falls back to test environments if endpoint or token is missing.
- Required fields must fail fast.
- Secrets originate from authorized managed sources.
- Audits non-secret effective configuration.
- Has rollback and app/config compatibility runbooks.

A policy table prevents the anti-pattern of "if no token is set, switch to anonymous mode" in production without an intentional design decision.

## 29. A Profile Is Not a Security Boundary

A deployment might accidentally activate:

~~~properties
spring.profiles.active=local
~~~

in production. If requiredness logic depends solely on profiles and `local` skips the token, the app could start in an unintended mode.

Build guardrails:

- Pipelines enforce allowed profiles per environment.
- Manifests and release records capture the active profile.
- Deploy-time checks verify expected environments.
- Critical secrets/security invariants do not rest on a single arbitrary flag alone.
- Health/readiness checks verify critical preconditions appropriately.
- Never allow local stub clients to activate in production via silent fallback.

Never rely on hostname substrings to identify environments. Use platform-managed deployment policies and test them.

## 30. Testing Required Fields with `ApplicationContextRunner`

Class:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotBlank String endpoint,
        @NotBlank String apiToken
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class IntegrationPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(IntegrationProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void validPropertiesCreateBean() {
        runner.withPropertyValues(
                "app.integration.endpoint=https://test.example.org",
                "app.integration.api-token=TEST_ONLY_TOKEN"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            IntegrationProperties p =
                    context.getBean(IntegrationProperties.class);
            assertThat(p.endpoint())
                    .isEqualTo("https://test.example.org");
        });
    }

    @Test
    void missingTokenFails() {
        runner.withPropertyValues(
                "app.integration.endpoint=https://test.example.org"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void blankTokenFails() {
        runner.withPropertyValues(
                "app.integration.endpoint=https://test.example.org",
                "app.integration.api-token="
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

This example assumes Spring Boot Test, AssertJ, JUnit 5, and a Bean Validation provider. In real projects, assert the exception cause chain to verify the context failed due to **validation** rather than a missing dependency.

`ApplicationContextRunner` tests a minimal application context. It does not prove profile-specific files are handled properly by Spring Boot's Config Data loader in a full application; add integration tests for the real loading path.

## 31. Testing Profiles with Two Distinct Registrations

A pattern with a production configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
@EnableConfigurationProperties(ProductionPartnerProperties.class)
class ProdRegistration {}
~~~

And non-production:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("!prod")
@EnableConfigurationProperties(LocalPartnerProperties.class)
class NonProdRegistration {}
~~~

To test, run `ApplicationContextRunner` with both registration classes and `withPropertyValues("spring.profiles.active=prod")` or configure active profiles via the test framework. Then assert:

- The production properties bean exists when `prod` is active.
- The production properties bean is not registered in non-prod.
- Missing/blank tokens in prod cause startup failure.
- Local config does not demand a production token.
- No duplicate beans sharing the same responsibility cause ambiguity.

If using `@ConfigurationPropertiesScan` over environment-specific classes, verify scanning does not accidentally register both.

Note that `spring.profiles.active` has rules on where it may be placed in Config Data; keep profile tests realistic and avoid putting it inside restricted documents.

## 32. Testing Across Multiple Override Sources

Sometimes the file holds a valid value while env or CLI overrides it with an invalid one.

Suppose:

~~~yaml
app:
  partner:
    connect-timeout: 3s
~~~

Environment:

~~~text
APP_PARTNER_CONNECTTIMEOUT=0s
~~~

By typical precedence, the environment overrides Config Data. If the timeout must be positive, the app must reject `0s` via validation or invariants.

Your test suite should include:

1. Valid default when omitted.
2. Profile file supplying a valid value.
3. Environment overriding with a valid value.
4. Environment overriding with an invalid value.
5. CLI overrides if allowed by policy.
6. Multiple active profile combinations.
7. Missing config import source.
8. Empty or missing secret reference.

Verify the **effective value** after binding, not merely key presence in one isolated source.

## 33. Deployment Environments and Standard Environment Variable Names

In Spring Boot, canonical property names:

~~~text
app.partner.connect-timeout
app.partner.max-retries
app.partner.api-token
~~~

typically map to environment variables:

~~~text
APP_PARTNER_CONNECTTIMEOUT
APP_PARTNER_MAXRETRIES
APP_PARTNER_APITOKEN
~~~

Standard rule: replace dots with underscores, **remove hyphens**, and uppercase.

A common mistake is inserting an underscore inside kebab-case words:

~~~text
APP_PARTNER_CONNECT_TIMEOUT
~~~

assuming it always matches `connect-timeout`. Follow Spring Boot's canonical naming rules and test binding against your runtime.

Environment variable names are merely a delivery mechanism, **not a security guarantee**. If tokens are passed via environment variables, still restrict process access, debug logs, and container inspection.

## 34. Separating Secret-Required from Non-Secret-Required

Some fields can be safely logged for diagnostics:

~~~java
log.info(
        "Partner enabled={} timeoutSeconds={}",
        properties.enabled(),
        properties.connectTimeout().toSeconds()
);
~~~

Log only fields classified as non-sensitive.

Never do:

~~~java
log.info("Partner configuration: {}", properties);
~~~

Default Java records generate `toString()`, which can print `apiToken`. With Lombok `@Data` on a DTO containing secrets, the same leak happens.

If validation catches a missing token, the exception should report the **property name** and reason, without echoing the token. Do not hash raw secrets into logs as "config proof", especially for low-entropy credentials.

A field's requiredness and its secrecy are orthogonal. An optional field can still be highly sensitive if supplied.

## 35. When the Schema Changes Across Application Versions

Suppose the old version used:

~~~properties
app.partner.retry-count=3
~~~

The new version switches to:

~~~properties
app.partner.max-retries=3
~~~

If production still has the old file, the new application may ignore `retry-count` and use the default for `max-retries`. That is an upgrade hazard.

A migration plan:

1. Document the change in release notes and the configuration contract.
2. Mark the old name deprecated in metadata and docs where appropriate.
3. Support an alias/migration over a compatibility window if rolling deployments need it.
4. Add CI checks for config files still using the old name.
5. Update config artifacts before or alongside the compatible app version.
6. Enable strict unknown-field detection where schema ownership permits.
7. Remove old-name support once all environments have migrated.
8. Maintain a compatibility matrix and rollback plan.

`spring-boot-configuration-processor` generates metadata for tooling, yet deprecation metadata **does not make the binder rewrite every old key to the new key**. Migration must be designed explicitly.

## 36. Do Not Let Defaults Mask Schema Drift

Suppose:

~~~java
@DefaultValue("2") int maxRetries
~~~

while legacy config still contains:

~~~properties
app.partner.retry-count=9
~~~

If the new app does not recognize `retry-count`, it may silently use the default `2` without warning the operator that `9` was ignored.

To prevent this:

- Review schema diffs in PRs.
- Use strict unknown fields where appropriate.
- Run rendered configs through tests against the target app version.
- Never add defaults just to bypass required-field violations.
- Keep a migration window for impactful key renames.
- Observe selected non-secret effective values after rollout.

When debugging, distinguish **a runtime default used as designed** from **a default masking an ignored legacy key**.

## 37. Do Not Confuse Optional Imports with Fail-Fast Secrets

A local setup example:

~~~yaml
spring:
  config:
    import: "optional:file:./local-overrides.properties"
~~~

An absent local file can still be valid.

Yet production needs a required config tree:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

If the location is missing, Spring Boot fails to load Config Data. However, if the directory exists while the `app.partner.api-token` file is missing, the import location itself still succeeds. Required tokens still need validation.

If you intentionally use `optional:configtree:` to support local runs, do not treat it as waiving required properties in production. Choose import policies per environment and test them.

## 38. Register Beans Only When a Feature Is Actually Active

A clean design can separate:

~~~text
PartnerProperties (state and options)
          |
      enabled?
       /    \
     no      yes
     |        |
  NoOp       Validated real client
  Client     requiring endpoint + token
~~~

In disabled mode, missing endpoint and token are valid. In enabled mode, both are required.

Never instantiate the real client with an empty token in disabled mode, because an unintended code path might still call upstream.

Conversely, if production policy **requires the feature to be enabled**, explicitly verify production cannot silently drop into NoOp mode just because `enabled` was omitted or false. A `false` boolean default is handy locally yet may violate production policy.

## 39. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Prod starts without token | Missing validation or bean not created | Add required constraint/invariant and startup test |
| `@NotNull` misses whitespace | Non-null is insufficient | Use `@NotBlank` |
| Missing `boolean enabled` passes silently | Primitive defaults to false | Use `Boolean` + `@NotNull` when explicitness is needed |
| `@DefaultValue` present yet invalid input still fails | Defaults apply only when missing | Fix the invalid source; keep validation |
| Local fails due to missing prod token | Unconditional required constraint | Separate profile/mode contracts |
| Prod enters stub mode | Wrong profile/feature flag or risky default | Deployment guardrails and prod-specific checks |
| Missing config import yet app starts | `optional:` skips missing location | Enforce location and property requirements separately |
| Typo in key, app uses default | Unknown field ignored | Schema validation and strict unknown checking |
| `@Valid` misses null nested object | Cascade does not require presence | Combine with `@NotNull` |
| `@NotNull Duration` accepts 0s | Positive check missing | Custom validator or constructor invariant |
| YAML property right, runtime value wrong | Env/CLI override | Inspect effective source |
| `Optional<String>` unexpectedly null | `Optional` discouraged on properties fields | Use clear nullable fields |
| Test fails for unrelated reason | Only asserted `hasFailed()` | Inspect cause chain and beans |
| Key rename during upgrade loses value | Missing schema migration | Compatibility window, deprecation, linting |
| Debug log leaks API token | Logged configuration record | Allowlisted diagnostics and redaction |
| Staging passes, prod fails | Different overlays/secrets/profiles | Profile matrix tests and production preflight |

## 40. Hands-On Exercises

### Exercise 1 — Detecting Required Text

A property `app.mail.sender-name` is a `String` and must contain at least one non-whitespace character. Which annotation?

**Answer:** `@NotBlank` in a properly validated properties bean.

### Exercise 2 — Explicit Boolean

Prod must declare `app.feature.enabled`, allowing true or false. Use `boolean` or `Boolean`?

**Answer:** `Boolean` with `@NotNull` and no default if absence must be detected.

### Exercise 3 — Optional Timeout with Default

If timeout is omitted, use 3 seconds, yet a zero timeout must be rejected. How to design it?

**Answer:** `@DefaultValue("3s")` on `Duration` plus custom positive-duration validation or a constructor invariant. `@NotNull` alone does not reject zero.

### Exercise 4 — Token Needed Only When Feature Enabled

`enabled=false` with token absent; `enabled=true` with token blank. Which case should fail?

**Answer:** under the conditional contract, the second case must fail; the first is allowed if the integration is truly disabled.

### Exercise 5 — Optional Config Data

Does `spring.config.import=optional:configtree:/run/secrets/` make `api-token` business-optional?

**Answer:** no. `optional:` governs missing import locations only. Required properties must still be validated separately.

### Exercise 6 — Primitive Trap

Does `@NotNull boolean tlsEnabled` detect a missing key?

**Answer:** no. Primitives cannot be null; use `Boolean` with appropriate constraints when explicit declaration is required.

### Exercise 7 — Production Profile

An app has `@Profile("prod")` on a configuration class, yet another scan still registers the production properties class locally. What is wrong?

**Answer:** inconsistent bean registration strategy. Control registration cleanly and test active profiles so production beans never run outside their profile.

### Exercise 8 — Precedence Value

`application-prod.yml` has `max-retries=2`, env sets `APP_PARTNER_MAXRETRIES=9`. If `@Max(5)` is active, what happens?

**Answer:** env normally overrides Config Data; `9` is bound and then rejected by validation.

### Exercise 9 — Required List

A production config must have at least one endpoint, and each endpoint needs a non-blank name. What is needed?

**Answer:** `@NotEmpty List<@Valid Endpoint>` and `@NotBlank` on `Endpoint.name` inside a validated properties bean.

### Exercise 10 — Renaming a Key

`retry-count` changes to `max-retries`. Is adding deprecation metadata alone enough?

**Answer:** no. Provide migration/compatibility code if needed, update config artifacts, and test app/config pairs.

### Exercise 11 — Secrets in Logs

A record with `apiToken` is logged via `log.info("{}", properties)`. What is the risk?

**Answer:** the record's `toString()` can print the real token. Avoid logging the object; use an allowlisted diagnostic.

### Exercise 12 — Testing Fail-Fast

In `ApplicationContextRunner`, a test only asserts `hasFailed()` when the token is missing. What should be added?

**Answer:** inspect the cause chain to confirm failure came from the required violation rather than an unrelated error.

## 41. Project Implementation Checklist

### Design

- [ ] Maintain a property catalog with canonical names and types.
- [ ] Every property has a clear owner, per-environment requirement, and default.
- [ ] Distinguish missing, blank, invalid, and unbound states.
- [ ] Avoid primitives when explicit presence must be detected.
- [ ] Never use defaults merely to mask config errors.
- [ ] Document conditional requirements tied to modes/features.
- [ ] Nested objects, lists, and maps have appropriate constraints and cascades.
- [ ] Secrets are marked sensitive and excluded from source code.

### Spring Boot Implementation

- [ ] Beans are registered cleanly via scan/enable.
- [ ] A Bean Validation provider is present when using Jakarta constraints.
- [ ] `@Validated` and constraints sit on the right root/fields.
- [ ] Cross-field invariants are checked.
- [ ] Profile-specific registration does not leak unexpected beans.
- [ ] Strict unknown-field checking is enabled in appropriate namespaces.
- [ ] Conversion errors are not swallowed with `ignoreInvalidFields=true`.
- [ ] Do not rely on `Optional` fields with unsupported assumptions.

### Testing and Deployment

- [ ] Test valid, missing, blank, invalid, optional, and default cases.
- [ ] Test local, test, staging, and prod profiles.
- [ ] Test feature on/off modes.
- [ ] Test env/CLI precedence and config imports.
- [ ] Test app/config schema compatibility across key renames.
- [ ] Include production token fail-fast tests without real secrets.
- [ ] Pipelines verify expected profiles and required secret references.
- [ ] Never log raw configs, tokens, or exceptions holding credentials.
- [ ] Rollback plans record compatible app, config, and secret references.

## 42. Summary

- **Required** is an explicit contract for presence and validity; **optional** must define what absence means.
- **Defaults** apply only when absence is permitted, never as a fix for invalid input.
- `@NotNull`, `@NotBlank`, and `@NotEmpty` serve distinct roles.
- When missing fields must be detected, prefer `Boolean`/`Integer` wrappers over primitives.
- On `@ConfigurationProperties`, pair `@Validated` with an appropriate Bean Validation provider.
- **Conditionally required** rules should rely on modes/features or dedicated schemas, not scattered `if (prod)` checks.
- `@Profile` controls registration and config activation; it does not enforce field requiredness on its own.
- **Config Data `optional:`** governs locations only, not a key's business requirement.
- **Effective configuration** can be overridden by env/CLI; test actual bound results.
- Optional secrets are still secrets when supplied; never log credentials or objects holding them.
- During upgrades, key renames need migration/compatibility and paired app/config tests.
- For production, favor fail-fast for critical settings, profile matrix tests, and deploy preflight checks.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Config Data and Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot — Profile-specific Files](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — `@ConditionalOnProperty` API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
