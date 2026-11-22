# Configuration, Properties, and Auto-Configuration Changes

During **Java Advance Compatibility Migration**, upgrading the JDK frequently accompanies upgrading Spring Boot, Spring Framework, Hibernate ORM, a Jakarta EE runtime, or platforms such as Quarkus and Micronaut. An application may **compile cleanly** yet behave differently because property keys were renamed, defaults changed, property source loading order shifted, or a starter auto-registered extra or fewer beans.

These bugs are hard to spot: not every change throws an exception. A service may still return HTTP 200 while targeting the wrong database, falling back to a default timeout, leaving validation disabled, swapping email providers, or exposing management endpoints unexpectedly. During Java upgrades, treat **configuration as an operational contract** spanning source code, framework, dependencies, deployment environments, and operators.

This lesson explains how to inventory and migrate configurations, distinguish property changes from auto-configuration changes using examples across Spring Boot and other frameworks, diagnose bean graphs and property binding, test thoroughly, and coordinate compatible rollouts. It belongs to the **Frameworks and Platforms** chapter; the goal is preserving **observable behavior** after migration, not merely getting the application to boot.

## 1. Configuration Is Part of the Runtime Contract

A Java application can receive configuration from multiple sources:

- `application.properties`, `application.yml`, or profile-specific files.
- Operating system or container environment variables.
- JVM system properties such as `-Duser.timezone=UTC`.
- Application command-line arguments.
- Kubernetes ConfigMaps, Secrets, Helm values, and mounted files.
- Config servers, Vault, Consul, or secret management systems.
- Feature flag services or database-backed settings.
- Defaults embedded inside frameworks/starters.
- Build-time settings for AOT/native images.
- Test-only property sources, IDE run configs, and CI profiles.

**A single key can appear across multiple sources**, so the application does not necessarily use values checked into the repository.

Configuration example:

~~~yaml
# application.yml
server:
  port: 8080

acme:
  connector:
    enabled: true
    timeout: 3s
~~~

If deployment injects `ACME_CONNECTOR_TIMEOUT=10s` and the framework binds it, the effective timeout becomes 10 seconds. If a framework changes key resolution or precedence rules, behavior can change without touching the YAML file.

### 1.1. Layers of Change to Separate

| Layer | Question | Risk |
|---|---|---|
| Property name | Is the old key still recognized? | Config silently ignored |
| Type and unit | What type does the value bind into? | 5000 milliseconds interpreted as 5000 seconds |
| Default | When the key is omitted, what happens? | Feature enabled/disabled differently |
| Property source | Which source takes highest precedence? | Production overrides fail to apply |
| Profile | Which files actually activate? | Wrong environment targeted |
| Auto-configuration | Which beans register from classpath and conditions? | Missing or redundant implementations |
| Lifecycle | Is the value read at build, startup, or runtime? | Env updated without process pickup |
| Security | Do auth, TLS, and management endpoints keep policy? | Exposed resources |
| Persistence | Are datasource, ORM, and transactions wired right? | Wrong DB connected or altered SQL behavior |
| Observability | Are health, metrics, and traces still emitted? | Regressions go unnoticed |

Auditing these layers cannot be replaced by running a single find-and-replace across YAML files.

## 2. Separating JDK Changes from Framework Changes

Upgrading the JDK can affect:
- Charset/encoding defaults, locale, timezone, and tzdb data.
- TLS protocols, truststores, and crypto providers.
- JPMS strong encapsulation and reflective access.
- JVM flags, agent loading, and Security Manager.
- Class-file format and Java SE APIs.

Upgrading a framework can affect:
- Property key renames, deprecations, and removals.
- Profile activation and config data loading.
- Bean registration conditions and auto-configuration.
- Framework dependencies, starters, and annotation processors.
- Jakarta namespace shifts from `javax.*` to `jakarta.*`.
- Defaults for serialization, validation, transactions, and security.
- Web servers, health checks, metrics, tracing, and startup lifecycles.

Both changes often combine:

~~~text
JDK 11 -> JDK 17 or 21
             |
             +-- Spring Boot 2.x -> 3.x
                        |
                        +-- Jakarta namespace
                        +-- Property renames
                        +-- New auto-configuration
                        +-- New ORM and web dependencies
                        +-- Different defaults
~~~

Never conclude "Java 17 caused the bug" merely because an error surfaced after changing the JDK base image. Document **JDK, framework, plugin, starter, and dependency versions** for each baseline.

## 3. Creating a Configuration Inventory Before Migration

Before editing code, catalog every property governing operations: databases, message brokers, HTTP clients, timeouts, retries, security, metrics, feature flags, and scheduled jobs.

| Property / Condition | Source | Type | Owner | Expected Behavior |
|---|---|---|---|---|
| `server.port` | Helm/env | Port | Platform | HTTP listener binds expected port |
| `spring.datasource.url` | Config/Secret | JDBC URL | Data | Connects to intended database |
| `spring.profiles.active` | Launcher/env | Profile list | Release | Loads prod configuration |
| `acme.connector.timeout` | YAML/env | Duration | Integration | Timeout 3s or environment value |
| `management.endpoints.web.exposure.include` | YAML | Endpoint list | SRE/Security | Exposes approved endpoints only |
| `feature.billing-v2` | Feature flag | Boolean | Product | Controls code path toggle cleanly |
| `@ConditionalOnClass` | Runtime classpath | Presence | Framework | Selects appropriate implementation |

Never record raw secret values in the inventory; record only key names, sources, types, owners, and verification tests.

### 3.1. Searching Across Source and Deployment Artifacts

Example repository search:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'spring\.|quarkus\.|micronaut\.|management\.|server\.|datasource' .

rg -n --hidden -g '!**/.git/**' \
  'SPRING_PROFILES_ACTIVE|SPRING_CONFIG|JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS|--spring\.' .
~~~

Files to inspect may live in:
- `src/main/resources/application.yml` and profile files.
- `src/test/resources`.
- `pom.xml` or `build.gradle(.kts)`.
- Dockerfiles, entrypoint shell scripts, Windows service configs.
- Helm charts, Kubernetes manifests, Kustomize overlays.
- CI variables and pipeline templates.
- Remote config services and secret stores.

Text searches **cannot see final rendered production values**. Inspect rendered manifests and effective runtime environments through infrastructure governance workflows with sensitive data redacted.

### 3.2. Catalog Implicit Config Absent from Files

A dependency starter may auto-register:
- A `DataSource` based on JDBC drivers on the classpath.
- An embedded web server based on web framework dependencies.
- A JSON serializer or validation provider.
- Metrics registries and health indicators.
- Security filter chains or default components.
- HTTP clients and connection pools.

Thus, the inventory needs the **classpath/dependency graph and auto-configuration report**, not just YAML keys.

## 4. Property Renames, Removals, and Semantic Changes

Common categories of change:

| Type | Characteristic | Handling |
|---|---|---|
| Rename | Key renamed with roughly equivalent meaning | Update every source and test binding |
| Removed | Key has no effect anymore | Remove and adopt replacement design if needed |
| Split | Single key divided into multiple keys | Verify individual semantics |
| Merge | Multiple keys combined into one | Resolve overrides/conflicts |
| Type change | Integer -> Duration, string -> enum | Specify explicit units and input checks |
| Default change | Omitted key behaves differently | Set explicit values |
| Scope change | Global -> per-client/per-profile | Move to matching hierarchy |
| Conditional change | Bean activates under new dependency/property | Test conditions |
| Behavior change | Same key yet new runtime semantics | Run business/integration tests |
| Deprecation | Key kept as temporary alias | Schedule removal |

### 4.1. A Spring Boot 2.x -> 3.x Illustration

Examples of renames documented when moving from Spring Boot 2 to 3 include:

| Before | After in matching Boot 3 stack | Note |
|---|---|---|
| `spring.redis.host` | `spring.data.redis.host` | Verify Redis auto-config used |
| `spring.redis.port` | `spring.data.redis.port` | Verify env overrides |
| `server.max-http-header-size` | `server.max-http-request-header-size` | Request vs. response header scope differs |

Before:

~~~yaml
spring:
  redis:
    host: redis.internal
    port: 6379

server:
  max-http-header-size: 16KB
~~~

Target example on a matching Boot 3 release:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379

server:
  max-http-request-header-size: 16KB
~~~

This table illustrates **one specific migration**, not an exhaustive list or formula for every Spring Boot minor/major release. Consult the **configuration properties appendix and migration guide for your exact target release** to confirm keys, defaults, and behavior.

### 4.2. Silently Ignored Keys Are More Dangerous Than Startup Failures

When a framework ignores unknown properties without failing:
- Connection timeouts may fall back to much longer defaults.
- Circuit breakers or feature flags may stay inactive.
- HTTP header limits may fall back wrongly.
- Connection pool sizes may shift.
- Security or management endpoint restrictions may fail to apply.

Clean startup does not prove a property was bound. Verify both **effective resolved values and functional outcomes**.

### 4.3. Spring Boot Properties Migrator Is a Temporary Aid

In supported releases, `spring-boot-properties-migrator` can help report renamed properties during a Spring Boot upgrade and temporarily alias certain keys within its supported scope.

Illustrative Maven dependency:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-properties-migrator</artifactId>
  <scope>runtime</scope>
</dependency>
~~~

Illustrative Gradle dependency:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
}
~~~

Confirm the tool supports the **exact target release** you are upgrading to. Use it during diagnosis, fix actual config sources, and then **remove the migrator dependency**. It does not automatically migrate every key, default, semantic shift, or secret/config service entry.

## 5. Property Sources and Precedence Order

Spring Boot reads multiple property sources: config data files, profile-specific configs, environment variables, Java system properties, CLI arguments, JSON application properties, and test-specific overrides. **Exact precedence depends on the framework version and source setup**, so consult official docs for your release rather than a simplified list.

Example:

~~~yaml
# application.yml
acme:
  connector:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
acme:
  connector:
    timeout: 5s
~~~

Container environment variable:

~~~text
ACME_CONNECTOR_TIMEOUT=10s
~~~

Effective timeout can become `10s`. If the launch command passes a higher-precedence argument, it changes again. Know **every loaded property source**, not only the YAML checked into source control.

### 5.1. Relaxed Binding Is Not Arbitrary Character Substitution

In Spring Boot, `@ConfigurationProperties` generally supports relaxed naming variants such as mapping kebab-case keys to Java camelCase. However, environment variable mapping, list indices, and map keys follow specific rules.

Canonical key example:

~~~text
acme.connector.read-timeout
~~~

This maps according to environment binding rules. Do not assume every underscore/camelCase permutation works identically. **Record the exact environment variable names** injected into containers/CI and test them on the target framework release.

### 5.2. Placeholders and Defaults Create Hidden Dependencies

~~~yaml
acme:
  connector:
    base-url: "${ACME_CONNECTOR_URL}"
    timeout: "${ACME_TIMEOUT:3s}"
~~~

Here, if `ACME_TIMEOUT` is unset, `3s` takes effect. That fallback may be fine when business-approved; yet for database URLs, encryption keys, or authentication secrets, an arbitrary default can be hazardous.

Classify configs clearly:
- **Required config**: fail fast when missing.
- **Optional config**: documented and tested default.
- **Secret**: supplied via secure store, never logged raw.
- **Feature flag**: clear default and rollout semantics.

## 6. Profiles and the Config Data API

Profiles govern which configuration sources activate. An application may work locally yet misbehave in production because profile files no longer load the old way.

Example:

~~~yaml
# application.yml
acme:
  connector:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
acme:
  connector:
    timeout: 10s
~~~

Spring Boot 2.4 substantially redesigned **config data** processing, including `spring.config.import` and profile activation constraints. When upgrading from older versions, inspect:
- `spring.config.location` vs. `spring.config.additional-location`.
- `spring.config.import` and remote sources.
- `spring.config.activate.on-profile` inside multi-document YAML.
- Restrictions on active vs. included profiles.
- Profile groups and config data ordering.
- Spring Cloud Config integration if used.

Multi-document YAML example:

~~~yaml
acme:
  connector:
    timeout: 3s
---
spring:
  config:
    activate:
      on-profile: prod
acme:
  connector:
    timeout: 10s
~~~

Not every legacy profile syntax migrates via regex. Verify behavior against the **effective configuration** of the running process.

### 6.1. Profiles Are Not a Security Boundary

Setting `spring.profiles.active=prod` does not automatically prove:
- Correct database/secrets are active.
- TLS validation is enabled.
- Management endpoints are locked down.
- Debug logging is disabled.
- Configs cannot be overridden by stray env vars.

Verify security through explicit policies and negative tests, not profile names alone.

## 7. `@ConfigurationProperties`: Binding and Validation

Spring Boot uses `@ConfigurationProperties` to bind settings onto typed Java objects. Across framework or JDK upgrades, check constructor binding, registration, type converters, and validation behavior.

### 7.1. Record Example on Java 17 and Spring Boot 3

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.connector")
public record ConnectorProperties(
        boolean enabled,
        Duration timeout,
        String baseUrl
) {
    public ConnectorProperties {
        if (timeout == null) {
            timeout = Duration.ofSeconds(3);
        }
    }
}
~~~

Config:

~~~yaml
acme:
  connector:
    enabled: true
    timeout: 5s
    base-url: "https://gateway.internal"
~~~

Registration class:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ConnectorProperties.class)
public class ConnectorConfig {
}
~~~

A record with a canonical constructor can use constructor binding in Spring Boot 3 when registered properly. **Do not apply this example verbatim to Spring Boot 2 / JDK 8**: records are a newer Java feature, and binding annotations/rules evolved across releases.

### 7.2. Time and Data Size Units

Legacy code might parse an integer timeout in milliseconds. Modern `Duration` properties accept values like `500ms`, `3s`, or `2m` via duration converters.

Prefer explicit units:

~~~yaml
acme:
  connector:
    timeout: 3s
    max-payload: 10MB
~~~

When declaring `max-payload`, the bound class/record must define a matching component such as `DataSize maxPayload`. This illustrates unit clarity rather than built-in framework keys.

Avoid unitless settings like `timeout: 3000` if a newer framework parses units differently. Add characterization tests checking exact bound values.

### 7.3. Jakarta Validation and `@Validated`

When moving from Spring Boot 2 / Java EE to Spring Boot 3 / Jakarta, validation annotations also move namespaces:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.connector")
public record ConnectorProperties(
        @NotNull Duration timeout,
        @NotBlank String baseUrl
) {}
~~~

For validation to enforce constraints, both the Jakarta Validation API and a matching provider must be present alongside valid bean registration. **Clean compilation does not prove validation runs.** Test missing/blank properties and confirm startup rejection.

### 7.4. Unknown Properties

If a file contains a typo such as `timeuot` instead of `timeout`, binders commonly ignore the unknown key and apply defaults. For critical settings, evaluate strict binding/validation capabilities offered by your framework.

Even then, strict binding does not inspect every inactive profile or unreachable config service; still maintain inventories and test rendered startup configs.

### 7.5. `@Value` Differs from `@ConfigurationProperties`

Example:

~~~java
@Value("${acme.connector.timeout:3s}")
private Duration timeout;
~~~

and `@ConfigurationProperties` can both read values, yet differ in metadata, constructor/type binding, validation, and testability. When refactoring away from `@Value`, preserve or intentionally adjust **the `3s` default**. Removing placeholders when switching to records can alter behavior when keys are absent.

## 8. Auto-Configuration: Conditions Controlling Bean Creation

Spring Boot auto-configuration inspects the classpath, environment, property values, and registered bean definitions to create default components.

Common conditions include:
- `@ConditionalOnClass`: is a dependency class present?
- `@ConditionalOnMissingClass`: is a dependency class absent?
- `@ConditionalOnBean`: does a matching bean already exist?
- `@ConditionalOnMissingBean`: is no matching bean registered yet?
- `@ConditionalOnProperty`: does a property match expectations?
- `@ConditionalOnWebApplication`: is the app a matching web type?
- `@ConditionalOnResource`: does a resource exist?
- Custom conditions defined by frameworks or starters.

~~~text
                Runtime classpath
                       |
                Configuration sources
                       |
                  Bean definitions
                       |
                Evaluate conditions
                 /            \
              match          no match
                |               |
           Register bean      Skip bean
                |
          Initialize component
                |
             Behavior
~~~

**The same YAML combined with a different dependency graph can produce a different bean graph.** Upgrading frameworks or starters can make beans appear or vanish without changing application code.

### 8.1. `@ConditionalOnProperty`

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfig {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.metrics",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    MetricsExporter metricsExporter() {
        return new MetricsExporter();
    }
}
~~~

`MetricsExporter` is an illustrative application class. If the config key changed from `acme.metrics.enabled` to `acme.observability.enabled` without updating the annotation and config together, the bean silently disappears.

For optional components, this causes **silent behavioral changes** rather than startup errors.

### 8.2. `@ConditionalOnMissingBean`

~~~java
@Bean
@ConditionalOnMissingBean(OutboundClient.class)
OutboundClient outboundClient() {
    return new DefaultOutboundClient();
}
~~~

Here, the default bean registers only if no other matching bean exists. After migration:
- Another starter might register an `OutboundClient`, suppressing your default.
- Removing a dependency might unexpectedly activate your default.
- Changed bean types, qualifiers, or search scopes might flip condition outcomes.

Inspect the condition evaluation report and bean graph rather than guessing from source file order.

## 9. Auto-Configuration Registration in Spring Boot 2 and 3

Internal libraries and starters must pay close attention to how auto-configurations are registered.

### 9.1. Legacy Registration via `spring.factories`

Spring Boot 2.x starters commonly registered auto-configurations in:

~~~text
META-INF/spring.factories
~~~

With content such as:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.autoconfigure.OutboundAutoConfiguration
~~~

This is a **legacy auto-configuration registration mechanism**. Do not infer that every other use of `spring.factories` across the Spring ecosystem was removed.

### 9.2. `AutoConfiguration.imports`

Spring Boot 2.7 introduced the new registration file; in Spring Boot 3, auto-configuration registration uses:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
com.example.autoconfigure.OutboundAutoConfiguration
~~~

Illustrative auto-configuration class:

~~~java
package com.example.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(OutboundClient.class)
@EnableConfigurationProperties(ConnectorProperties.class)
public class OutboundAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(OutboundClient.class)
    @ConditionalOnProperty(
            prefix = "acme.connector",
            name = "enabled",
            havingValue = "true"
    )
    OutboundClient outboundClient(ConnectorProperties properties) {
        return new DefaultOutboundClient(properties.timeout());
    }
}
~~~

`OutboundClient`, `DefaultOutboundClient`, and `ConnectorProperties` must have real implementations in the library. This snippet shows the relationship between **registration metadata, conditional properties, and bean creation**, not a full standalone Java project.

A starter containing only the old `EnableAutoConfiguration` entry in `spring.factories` may no longer be picked up by Spring Boot 3 via that legacy mechanism. Even with the class present in the JAR, auto-configuration fails to load. Upgrading application dependencies does not rewrite metadata **inside starter JARs**.

### 9.3. Metadata Alone Fixes Nothing Else

An old starter can still:
- Import `javax.servlet` or `javax.validation` instead of `jakarta.*`.
- Call Spring APIs whose signatures or semantics changed.
- Rely on obsolete property prefixes or binding types.
- Reference conditional classes that no longer exist.
- Register beans conflicting with the new framework.
- Require a different JDK baseline or transitive dependencies.

Upgrade and test **the entire starter**, not just `AutoConfiguration.imports`.

## 10. Bean Overrides, Ambiguity, and Dependency Injection

Common errors after migration:

~~~text
NoSuchBeanDefinitionException
NoUniqueBeanDefinitionException
BeanDefinitionOverrideException
UnsatisfiedDependencyException
BeanCreationException
~~~

These can result from missing beans, duplicate implementations of a type, renamed bean definitions, failed conditions, or dependency cycles.

For instance, `spring.main.allow-bean-definition-overriding=true` in supported Spring Boot releases permits beans sharing a name to override one another. **Never enable that flag as a blanket fix**: critical implementations can silently get replaced without failing tests.

Instead:
1. Identify the exact bean name/type and root cause stack trace.
2. Check which configuration class registers the bean.
3. Inspect matched/unmatched entries in the auto-config report.
4. Inspect starter dependencies and versions.
5. Check `@Primary`, `@Qualifier`, and custom bean definitions.
6. Lock down the intended implementation and test the bean graph.

Never exclude broad auto-configurations without knowing what transaction, health, metrics, or converter beans they also create.

## 11. Diagnosing with Condition Evaluation Reports and Actuator

Spring Boot can output a **condition evaluation report**. One way during local or staging test runs:

~~~bash
java -jar app.jar --debug
~~~

Do not leave debug logging permanently enabled in production where it inflates logs or leaks operational internals.

Actuator endpoints, when present and secured properly, assist inspection:

| Endpoint | Purpose | Risk |
|---|---|---|
| `conditions` | View matched/unmatched auto-configs | Exposes class/bean graph |
| `beans` | List active beans | Exposes internal structure |
| `configprops` | Bound configuration properties | May expose sensitive values |
| `env` | Active property sources and values | Requires strict protection/sanitization |
| `health` | Readiness/liveness/health status | `UP` alone does not prove business config is valid |
| `metrics` | Track runtime behavior/latency | Control metric labels and endpoint access |

For example, `/actuator/conditions` only works when Actuator is installed and the endpoint is enabled/exposed per your framework version.

### 11.1. Distinguishing Three Failure Classes

**Property fails to bind:** check key name, type, source precedence, constructors, and validation.

**Auto-config fails to match:** check `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, and registration metadata.

**Bean registers yet behaves wrongly:** check defaults, client/provider settings, runtime/JDK behavior, network, database, and business logic.

Condition reports cannot replace integration tests; they illuminate only the context-assembly layer.

## 12. Testing Configuration Binding

Spring Boot provides `ApplicationContextRunner` for lightweight context tests in starters and configuration tests.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ConnectorPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfig.class);

    @Test
    void bindsTimeoutAndUrl() {
        runner.withPropertyValues(
                "acme.connector.enabled=true",
                "acme.connector.timeout=5s",
                "acme.connector.base-url=https://api.internal"
        ).run(context -> {
            ConnectorProperties props =
                    context.getBean(ConnectorProperties.class);

            assertThat(props.enabled()).isTrue();
            assertThat(props.timeout()).hasSeconds(5);
            assertThat(props.baseUrl())
                    .isEqualTo("https://api.internal");
        });
    }

    @EnableConfigurationProperties(ConnectorProperties.class)
    static class TestConfig {}
}
~~~

This uses the `ConnectorProperties` record defined earlier. Compatible JUnit, AssertJ, and Spring Boot Test dependencies are required. It **verifies actual bound runtime values** rather than merely reading raw YAML.

### 12.1. Testing Conditional Bean Presence/Absence

Example for `OutboundAutoConfiguration`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class OutboundAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(OutboundAutoConfiguration.class)
                );

    @Test
    void doesNotCreateClientWhenDisabled() {
        runner.withPropertyValues("acme.connector.enabled=false")
              .run(ctx ->
                  assertThat(ctx).doesNotHaveBean(OutboundClient.class)
              );
    }

    @Test
    void createsClientWhenEnabled() {
        runner.withPropertyValues(
                    "acme.connector.enabled=true",
                    "acme.connector.timeout=500ms"
              )
              .run(ctx ->
                  assertThat(ctx).hasSingleBean(OutboundClient.class)
              );
    }
}
~~~

This is an **illustrative starter test outline**; real implementations and dependencies are required to execute it. Beyond isolated context tests, add integration tests verifying the client connects to real endpoints, honors timeouts, and handles errors/retries properly.

### 12.2. Testing Missing and Invalid Values

Add test cases for:
- Missing required URL or credentials.
- Negative or zero `Duration` where disallowed.
- Invalid enum values.
- Unitless numeric timeout settings.
- Misspelled property keys.
- Both old and new keys present with conflicting values.
- Environment variables overriding profile YAML.
- Disabled features failing to instantiate network clients.

For critical properties, tests should verify **fail-fast rejection or approved fallbacks**, not merely "context loads."

## 13. Security Settings Can Change with Framework Upgrades

Spring Security and framework security integrations often alter APIs and defaults across major versions. Examples:
- How `SecurityFilterChain` and request matcher APIs are configured.
- Servlet filters switching from `javax.servlet` to `jakarta.servlet` in Jakarta stacks.
- OAuth2 resource server / JWT validation rules.
- CSRF, CORS, and session/cookie policies.
- Actuator security defaults and management port access.
- Role mapping and method authorization annotations.

Never treat a migrated security config as safe just because the app starts. Define concrete contracts, such as:
- `GET /public/health` permits anonymous access.
- `GET /orders/{id}` requires authentication and ownership authorization.
- `POST /admin/reindex` restricts access strictly to admins.
- `/actuator/env` and `/actuator/configprops` are never publicly exposed.

Run both **positive and negative tests** on the target framework and JDK. Never apply production workarounds like disabling security filters, opening wildcard CORS, skipping certificate validation, or exposing all Actuator endpoints just to "get the migration green."

## 14. Web Servers, HTTP Defaults, and Proxies

Upgrading embedded Tomcat, Jetty, Undertow, or Netty can alter:
- Connection, read, and write timeouts.
- Maximum request header and body sizes.
- HTTP/2, keep-alive, and compression behavior.
- Forwarded headers and reverse-proxy handling.
- Context paths, route matching, and error mappings.
- Default TLS cipher suites and protocols.
- Session cookies, `SameSite`, and servlet lifecycles.

A renamed property affects more than your application—it interacts with gateways too:

~~~text
Client
  |
  v
Ingress / API gateway
  |   TLS, header/body limit, timeout
  v
Load balancer
  |   keep-alive, connection pooling
  v
Tomcat / Netty
  |   header limit, request decoding
  v
Spring filters/controllers
~~~

If the gateway rejects requests for oversized headers, raising Tomcat's limit alone fixes nothing. Conversely, if the framework stops binding an old limit key, Tomcat may fall back to a smaller default even when the gateway allows larger requests. Inspect **which layer actually rejects requests** and compare statuses, bodies, and logs at every hop.

## 15. Persistence, Connection Pools, and ORM

Framework upgrades often pull in newer Hibernate ORM, Jakarta Persistence, JDBC drivers, and connection pools. Keys and behavior can shift across:
- `DataSource` discovery and bean selection.
- HikariCP min/max pool sizes and idle/connection timeouts.
- Transaction managers, propagation, and exception translation.
- ORM dialects, physical naming strategies, and generated SQL.
- Schema generation and validation behavior.
- Entity scanning, converters, listeners, and bytecode enhancement.
- `javax.persistence.*` -> `jakarta.persistence.*` on Jakarta stacks.

Example:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal:5432/orders"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 20
      connection-timeout: 5s
~~~

This illustrates HikariCP settings in a Spring Boot stack; confirm exact supported keys/values for your version. Never log passwords or commit live secrets into repositories.

### 15.1. Database Health Checks Do Not Prove Valid Persistence Migration

An application can report health `UP` while:
- Connecting to a test database due to an env override.
- Running with a different pool size or timeout default.
- Switching SQL dialects and breaking rare queries.
- Running unexpected DDL auto-generation.
- Shifting transaction boundaries and causing data inconsistency.

Test transactions, database identity, integrations, and query semantics. Never rely on `hibernate.hbm2ddl.auto=update` as a production schema migration plan without reviewed database change controls.

## 16. Observability and Management Configuration

Upgrading frameworks can alter:
- Actuator endpoints and exposure settings.
- Micrometer metric names and tags.
- Tracing bridges, context propagation, and sampling.
- Health/readiness probe payloads.
- Exporter credentials, batching, and buffering.
- Log formats and correlation IDs.

For instance, migrating from Spring Boot 2 to 3 often entails updating observability integrations; **do not merely rename a tracing key**—verify end-to-end trace spans and monitoring dashboards.

A v2 service can operate normally while silently dropping metrics, blinding regression detection. Verify metric names, latency histograms, service/operation tags, trace propagation, and PII/secret masking.

## 17. Quarkus, Micronaut, and Jakarta Application Servers

The principle of **"inventory properties → verify bean graph → test runtime"** applies broadly, though mechanics differ per platform.

### 17.1. Quarkus: Build-Time vs. Runtime Configuration

Quarkus classifies settings as build-time or runtime depending on extensions and releases. With native images or AOT builds, some properties lock at build time.

During migration:
- Read the configuration guide for your exact target Quarkus release.
- Separate build-time keys from runtime keys.
- Never assume changing env vars at startup updates every property.
- Rebuild artifacts/images whenever build-time properties change.
- Check extension versions, profiles, and config precedence.
- Test both JVM mode and native mode separately if used.

Do not copy Spring Boot's `@ConditionalOnClass` or `AutoConfiguration.imports` assumptions onto Quarkus.

### 17.2. Micronaut: Compile-Time Bean Metadata

Micronaut relies heavily on annotation processing and compile-time metadata for dependency injection. Upgrading JDKs or Micronaut often requires updating annotation processors and regenerating metadata.

Check:
- Micronaut runtime, processor, and build plugin versions.
- Configuration prefixes, type conversions, and validation.
- `@Requires` conditions and environments.
- Generated bean definitions after a clean build.
- Target runtime/JDK and native/AOT modes.
- HTTP clients, security, database, and metrics behavior.

### 17.3. Jakarta EE Application Servers

For Tomcat, Jetty, WildFly, Payara, Open Liberty, and similar servers:
- Cross-check Java EE vs. Jakarta EE namespaces.
- Inspect `web.xml`, `persistence.xml`, and deployment descriptors.
- Verify JNDI `DataSource` and JMS bindings.
- Check CDI bean discovery and provider integrations.
- Inspect class loader / module isolation, security realms, and TLS.
- Audit operator-managed server configs external to the WAR/EAR.

Migrating application source to `jakarta.*` does not automatically update resource mappings or production server configuration.

## 18. Containers, Kubernetes, and Operational Configuration

Repository YAML can be overridden completely by deployment templates or container environments.

Illustrative Deployment manifest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: orders
          image: registry.example/orders:PINNED_VERSION
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: ACME_CONNECTOR_TIMEOUT
              value: "5s"
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: password
~~~

This is not a complete production manifest; real deployments require resource limits, probes, `securityContext`, service accounts, image digest/signing policies, and network controls.

### 18.1. Configuration and Binaries Must Roll Out in Sync

During rolling deployments, v1 and v2 may expect different property keys. Updating ConfigMaps/Secrets before binaries can cause:
- v1 failing to recognize new keys.
- v2 dropping support for old keys.
- Already-running pods missing updated env vars.
- Rollbacks to v1 failing under updated configs.

A safer rollout sequence:
1. Introduce new keys in a backwards-compatible transition step.
2. Temporarily let v2 read both old and new keys where necessary, with explicit precedence.
3. Migrate Helm charts, CI variables, Secrets, and config services to new keys.
4. Canary deploy and verify effective configs.
5. Delete old keys only once v1 leaves the rollback window.

Never let one property key carry **two incompatible semantics** between v1 and v2; introduce a new key or explicit version instead.

### 18.2. Environment Matrix

| Environment | JDK | Framework | Config Source | What to Verify |
|---|---|---|---|---|
| Local | Developer JDK | Target | YAML/env | Binding, unit tests |
| CI | Pinned test JDK | Target | Test properties | Conditions, validation |
| Integration | Target runtime | Target | Test containers/secrets | DB, HTTP, broker |
| Staging | Prod-like image | Target | Helm/config service | Canary, probes, auth |
| Production v1 | Old JDK | Old framework | Old config | Baseline |
| Production v2 | New JDK | New framework | New config | Compatibility, rollback |

Avoid running tests solely with `application-test.yml` when production pulls overrides from external sources.

## 19. Practical Migration Example: Legacy Client Config to Modern

Suppose legacy config reads:

~~~yaml
acme:
  connector:
    enabled: true
    timeoutMillis: 5000
    endpoint: "https://legacy.internal"
~~~

Legacy code:

~~~java
@Value("${acme.connector.timeoutMillis:5000}")
private int timeoutMillis;
~~~

The new version adopts `Duration` and clearer naming:

~~~yaml
acme:
  connector:
    enabled: true
    timeout: 5s
    base-url: "https://legacy.internal"
~~~

Behavioral checklist for this change:
- Does `5000` milliseconds genuinely map to 5 seconds in the new client library?
- Does the fallback default when omitted match previous behavior?
- Which env/Helm sources still inject `timeoutMillis`?
- If both keys coexist, which one wins?
- Does `enabled=false` prevent client bean creation and side effects?
- Upon rolling back to v1, do legacy configs still apply cleanly?

**Never keep legacy aliases forever.** A compatibility bridge helps during transitions, yet needs an owner, clear precedence rules, deprecation warnings, and removal criteria.

## 20. Troubleshooting Table

| Symptom | Suspected Layer | What to Check |
|---|---|---|
| Failed to bind properties | Key/type/constructor/validation | Root cause and effective values |
| No error, yet property ignored | Renamed/removed key or precedence | Runtime config report and release notes |
| `NoSuchBeanDefinitionException` | Auto-config failed to match/register | Conditions, starters, import metadata |
| `NoUniqueBeanDefinitionException` | Multiple beans of same type | `@Qualifier`, `@Primary`, dependencies |
| `BeanDefinitionOverrideException` | Duplicate bean name | Owners and bean graph; never blindly enable overrides |
| App connects to wrong DB | Profile/env/secret precedence | JDBC URL source and DB identity |
| Actuator endpoint missing | Exposure/security/management config | Dependencies and access policies |
| Metrics/tracing vanish | Observability plugins/properties | Exporters, registries, and logs |
| Passes locally, fails on Kubernetes | Env naming, mounts, image, profiles | Rendered deployment manifests |
| HTTP 431 after upgrade | Gateway/container header limits | Every proxy hop and app server |
| Bean validation skipped | Jakarta provider/annotation mismatch | Invalid-input integration tests |
| Quarkus native ignores new env | Build-time config locked | Build-time vs. runtime classification |
| TLS fails on new JDK | Truststore/provider/cipher updates | TLS handshakes and JDK release notes |
| Tests pass, prod uses wrong default | Test property overrides | Prod-like integration tests |
| Startup UP, feature inactive | Optional bean omitted | Bean graph and business-level tests |

Fix errors at the right layer. `--add-opens` will not repair wrong property keys; bean overriding will not fix missing dependencies; raising JVM memory will not fix timeouts or conditional binding.

## 21. Regression Testing Strategy

Configuration migration requires multiple layers of proof:

**Static inventory**
- Lists of deprecated, removed, and renamed keys.
- Dependency and starter versions.
- JVM args and Docker/Helm/CI overrides.
- Jakarta, XML, and provider configs.

**Binding tests**
- Missing, invalid, and valid values.
- `Duration` and `DataSize` parsing.
- Environment precedence.
- Profile activation.
- Unknown keys and legacy aliases.

**Auto-configuration tests**
- Bean created when enabled.
- Bean skipped when disabled.
- Conditions evaluate false when dependencies are absent.
- Custom beans override defaults per policy.
- No duplicate or ambiguous beans.

**Integration tests**
- HTTP routes, status codes, and headers.
- TLS, authorization, and DB transactions.
- Messaging retries and broker integration.
- Health, readiness, metrics, and tracing.
- Startup and shutdown under the target JDK and container image.

**Rollout tests**
- v1 and v2 running concurrently with transitional configs.
- Canary checks and rollback thresholds.
- v1 reading v2 data within the rollback window if required.
- Removing legacy aliases/keys only after all consumers transition.

### 21.1. A Compact Test Matrix

| Case | Input | Expected Outcome |
|---|---|---|
| Missing optional key | No `timeout` | Approved default applies |
| Valid value | `5s` | 5 seconds |
| Equivalent representation | `5000ms` | 5 seconds |
| Invalid value | `abc` | Fail fast |
| Env override | `ACME_CONNECTOR_TIMEOUT=10s` | Override source wins |
| Feature disabled | `enabled=false` | No client bean or side effects |
| Legacy key | `timeoutMillis` | Warning/alias/fail per policy |
| Old/new key conflict | Divergent values | Resolved per explicit contract |
| Missing class | Client library absent | Auto-config skips bean |
| Prod profile | Profile `prod` active | Only intended sources load |

For security-sensitive configs, include **negative tests**: unauthorized requests must be rejected, admin endpoints must stay private, and invalid secrets/configs must never fall back into insecure modes.

## 22. Step-by-Step Rollout Workflow

### Step 1: Lock Target Versions

Record exact JDK vendor/build, framework version, starters, ORM, web server, validation/security providers, container images, and support windows. Read migration guides for the **exact target release**.

### Step 2: Capture Baseline

Record effective configuration (with secrets redacted), active profiles, matched/unmatched conditions, bean graphs, startup warnings, observed timeouts/health behavior, and legacy artifact hashes.

### Step 3: Classify Changes

Separate into:
- Renamed/removed configuration keys.
- Type/default/semantic changes.
- Profile and property-source precedence shifts.
- Auto-configuration conditions and registration metadata.
- Starter, dependency, and Jakarta shifts.
- JDK runtime behavioral changes.

### Step 4: Migrate Config Sources and Code

Update YAML, properties, Helm, CI, config services, `@ConfigurationProperties`, validation annotations, and custom starters. If using migrators, OpenRewrite, or IDE refactoring, document their scope and fix unsupported cases manually.

### Step 5: Verify Bean Graph and Effective Config

Use context tests, condition evaluation reports, and safe startup inspection. When beans are missing or duplicated, trace the exact configuration class and condition rather than disabling auto-configurations broadly.

### Step 6: Run Integration Tests on Target Runtime

Exercise databases, HTTP endpoints, TLS, authorization, validation, messaging, metrics, scheduled jobs, and lifecycle operations using the exact target JDK, framework, and container image.

### Step 7: Canary and Rollback Verification

Shift partial traffic, track business metrics and error rates, and maintain v1/v2 config compatibility. If new settings alter persisted data formats that v1 cannot read, prepare data rollback steps or gate the feature flag before enabling it.

### Step 8: Retire Legacy Configuration

Once no instances rely on legacy settings, delete transitional aliases, properties migrator dependencies, legacy starter pins, flag workarounds, and stale docs. Keep regression tests and config inventories current for future upgrades.

## 23. Common Pitfalls

- **Green build means valid config:** legacy keys may silently be ignored.
- **Identical YAML means identical behavior:** precedence, profiles, and defaults can shift.
- **Unset property means feature disabled:** classpath auto-configuration can activate defaults.
- **Updating one file suffices:** Helm, Secrets, CI, and config services may still inject legacy keys.
- **Relaxed binding accepts arbitrary formats:** environment variable mapping obeys specific rules.
- **Migrators fix everything:** automated tools only handle predefined rules.
- **Property binds cleanly implies bean exists:** auto-configuration still hinges on conditions.
- **Adding a starter adds only a JAR:** starters trigger bean creation and runtime side effects.
- **Enabling bean overriding solves conflicts:** it masks duplicate implementation bugs.
- **Actuator `env`/`beans` can stay open in prod for debugging:** requires strict access control and sanitization.
- **A `prod` profile equals a security boundary:** profiles do not replace authentication or authorization.
- **JDK upgrade requires switching `javax` to `jakarta`:** that is a separate framework/API migration.
- **Quarkus/Micronaut behave identically to Spring Boot:** build-time and compile-time models differ.
- **Native images pick up every new env var at runtime:** build-time config may already be baked in.
- **Health `UP` proves the app is configured right:** health checks rarely cover every business setting.
- **Binary rollback suffices to roll back:** databases, configs, and event state may have mutated.

## 24. Checklist for Completing Configuration Migration

- [ ] Verified actual JDK, framework, starter, provider, and container versions.
- [ ] Read migration guides and property appendices for the exact release.
- [ ] Inventoried config sources: files, env vars, JVM args, remote config, Helm, Secrets.
- [ ] Classified renamed, removed, split, type, default, and semantic changes.
- [ ] Confirmed effective values, profile activation, and precedence rules.
- [ ] Required settings fail fast or enforce validation; optional defaults are approved.
- [ ] `@ConfigurationProperties` bind exact types, units, and beans properly.
- [ ] Jakarta Validation annotations and providers work where configured.
- [ ] Auto-configuration metadata and conditional beans covered by tests.
- [ ] No missing beans, duplicate beans, or unintended overrides remain.
- [ ] Security, Actuator, TLS, and authorization verified via negative tests.
- [ ] DB, ORM, transactions, and connection pool settings retain intended behavior.
- [ ] HTTP limits, proxy hops, and session handling tested.
- [ ] Health, metrics, and traces continue reporting without leaking sensitive data.
- [ ] Cross-checked local, CI, staging, and production-like environments.
- [ ] Prepared canary checks, coexistence windows, and rollback procedures.
- [ ] Never log secrets or expose unguarded `env`/`configprops` endpoints.
- [ ] Assigned owners and removal criteria for migrators, aliases, and workarounds.

## 25. Reference Documentation

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html).
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html).
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html).
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide).
- [Quarkus Configuration Reference](https://quarkus.io/guides/config-reference).
- [Micronaut Documentation](https://docs.micronaut.io/latest/guide/).
- [Jakarta EE Specifications](https://jakarta.ee/specifications/).

"Current/latest" links evolve over time. During migration, prioritize documentation for your **exact pinned version** together with test evidence on your own artifacts and runtime, rather than extrapolating from examples written for another version.

## 26. Conclusion

**Configuration and auto-configuration changes represent operational contract migrations, not merely renaming YAML keys.** A Java application can compile and boot cleanly yet alter timeouts, database targets, security behavior, bean graphs, or observability due to upgraded frameworks, starters, JDKs, and deployment overrides.

A reliable path is **capture baseline → inventory config sources and dependencies → classify property, default, and conditional shifts → update configs and starter metadata → verify binding and bean graphs → run integration tests on the target JDK/framework → execute controlled canary and rollback**. For every critical setting, answer: **who provides the value, what reads it, which condition activates it, and what behavior must remain invariant**. When those contracts are tested and documented, teams can upgrade Java and frameworks incrementally without turning defaults or auto-configuration into hidden risks.
