# Profiles, Profile-Specific Files, and Profile Groups

> **Chapter:** Configuration Loading  
> **Module:** SPRING_CLOUD_CORE

A Spring Boot application is typically deployed across multiple environments such as local, test, staging, and production. These environments can share the same artifact while requiring different endpoints, ports, connection limits, log levels, and certain beans. **Spring Profiles** provide a way to name those configuration contexts so the application selects the appropriate properties and components at startup.

In the **SPRING_CLOUD_CORE** module, profiles are part of the externalized configuration loading process. Profiles work alongside `application.yml`, `application-{profile}.yml` files, `@Profile`, Spring Cloud Config, and other property sources. It is important to understand when profiles are activated, which files are loaded, which configuration overrides which, and how to group multiple profiles into a meaningful deployment selection.

## 1. What Is a Profile?

A **Profile** is a label used by Spring to identify a group of configurations and beans suitable for a given runtime context. For example:

- `local`: running on a developer machine, possibly calling dependent services on localhost.
- `test`: configuration for integration testing.
- `staging`: a pre-production testing environment close to production.
- `production`: the live environment serving real users.

Profiles serve two related yet distinct roles:

1. **Configuration selection:** Spring Boot loads files or documents intended for active profiles.
2. **Bean selection:** Spring Framework registers beans annotated with `@Profile` only when the profile condition is satisfied.

A profile does not create infrastructure environments on its own, replace authorization mechanisms, or guarantee that external services are ready. It is strictly a condition for selecting configuration and beans inside the ApplicationContext.

### 1.1. A profile is not an instance name

`production` may be the application's profile; `order-service` is the logical name of the application; a specific instance might be `order-7f8c9d`. These three values answer three different questions:

| Value | Meaning | Example |
| --- | --- | --- |
| Profile | Which configuration/bean set is the application using? | `production` |
| Application/service name | By what name is the application or service identified? | `order-service` |
| Instance ID | Which specific running replica is active? | `order-7f8c9d` |

In Spring Cloud, `spring.application.name` is commonly used as the application name when integrating with discovery or Config Client. Active profiles can be sent alongside the application name to Config Server to retrieve the matching configuration set. Profiles do not replace service discovery, service registries, or load balancing.

## 2. Organizing Shared and Profile-Specific Configuration

The common practice is to keep shared properties in `application.yml`, and only record differences in each profile file.

Example structure:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-production.yml
~~~

The `application.yml` file holds shared defaults:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080
  shutdown: graceful

catalog:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-attempts: 2

logging:
  level:
    root: INFO
~~~

The `application-local.yml` file declares only local differences:

~~~yaml
server:
  port: 8081

catalog:
  client:
    base-url: "http://localhost:8090"

logging:
  level:
    com.example.order: DEBUG
~~~

The `application-production.yml` file declares values for production:

~~~yaml
server:
  port: 8080

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 800ms
    read-timeout: 2s
    max-attempts: 2

logging:
  level:
    root: WARN
~~~

When the `production` profile is active, Spring Boot loads shared configuration and the corresponding profile configuration. Keys declared in `application-production.yml` can override matching keys from `application.yml`; non-overridden keys keep their shared values.

This structure avoids repeating the entire configuration across every environment. For example, `catalog.client.max-attempts` does not need to appear in the production file if two attempts remain appropriate for that environment.

**Note:** `catalog.client.*` is an application-defined custom namespace. These values only take effect when bound via `@ConfigurationProperties`, read via `@Value`, or consumed by the corresponding component. A profile filename alone does not automatically give meaning to arbitrary YAML keys.

## 3. Activating Profiles

Profiles can be activated via environment variables, command-line arguments, or system properties. This is the right way to run the same artifact across multiple environments without modifying packaged files.

### 3.1. Activating via environment variable

On Linux/macOS:

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar order-service.jar
~~~

On PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "production"
java -jar order-service.jar
~~~

Multiple profiles can be activated together, separated by commas:

~~~bash
SPRING_PROFILES_ACTIVE=production,observability java -jar order-service.jar
~~~

Active profiles participate together in configuration and bean selection. If the same property is declared in multiple profiles, profile order matters; among profile-specific sources at the same level, a profile evaluated later can override earlier values.

### 3.2. Activating via command-line arguments

~~~bash
java -jar order-service.jar --spring.profiles.active=staging
~~~

Or pass a JVM system property:

~~~bash
java -Dspring.profiles.active=staging -jar order-service.jar
~~~

Command-line arguments and system properties are high-precedence configuration sources in standard startup configuration. Therefore, they can override values declared in configuration files. When multiple sources set `spring.profiles.active`, check the highest-precedence source to see which profiles are actually selected.

### 3.3. Default profile

If no profile is explicitly activated, Spring Boot uses a default profile named `default`. Thus, shared configuration in `application.yml` still applies when no specific profile is chosen.

You can rename the default profile with `spring.profiles.default`, though do so carefully. If the default is set to `local`, a production application started without `SPRING_PROFILES_ACTIVE` could accidentally pick up local settings. For real deployed services, it is generally safer to keep shared defaults safe and require pipelines or deployment platforms to specify profiles explicitly.

Never rely on the default profile to enforce access control or protect secrets.

## 4. How Spring Boot Loads Profile-Specific Files

Spring Boot follows the file naming convention:

- `application.yml`: shared configuration.
- `application-{profile}.yml`: profile-specific configuration.

For example, `application-test.yml` is evaluated when the `test` profile is active; `application-production.yml` is evaluated when the `production` profile is active.

### 4.1. Profile-specific configuration overrides shared configuration

Suppose shared configuration has:

~~~yaml
catalog:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-attempts: 3
~~~

While `application-production.yml` has:

~~~yaml
catalog:
  client:
    connect-timeout: 500ms
    read-timeout: 2s
~~~

When the `production` profile is active, the outcome looks like:

| Property | Effective Value | Source |
| --- | --- | --- |
| `catalog.client.connect-timeout` | `500ms` | `application-production.yml` |
| `catalog.client.read-timeout` | `2s` | `application-production.yml` |
| `catalog.client.max-attempts` | `3` | `application.yml` |

Spring Boot merges properties across property sources; profile-specific keys override corresponding shared keys. Properties absent from the profile file can still come from shared configuration.

For collections, pay attention to merge rules. For example, a list in a higher-precedence configuration typically replaces the entire list in a lower-precedence configuration rather than appending elements. Never assume two lists will concatenate automatically. Test binding results when configurations contain complex lists or maps.

### 4.2. Multiple active profiles and precedence order

Suppose you launch:

~~~bash
SPRING_PROFILES_ACTIVE=staging,observability java -jar order-service.jar
~~~

The application loads configuration sources matching the activated profiles. When the same key is declared across multiple profile-specific sources, profile order can determine the final value. Therefore, avoid having independent profiles define conflicting values for critical properties.

A clean approach is separating responsibilities:

- `staging` and `production` define endpoints, resource limits, and environment attributes.
- `observability` defines logging, metrics, or tracing settings.
- Stable baseline values live in `application.yml`.

If multiple profiles must be combined, explicitly document their order in deployment configs and write tests to verify effective values.

## 5. Multiple Documents in One `application.yml`

Instead of creating separate files, multiple YAML documents can be placed in one file, separated by `---`. Use `spring.config.activate.on-profile` to determine when a document applies.

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

catalog:
  client:
    connect-timeout: 2s

---
spring:
  config:
    activate:
      on-profile: local

server:
  port: 8081

catalog:
  client:
    base-url: "http://localhost:8090"

---
spring:
  config:
    activate:
      on-profile: production

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 800ms
~~~

The first document has no profile condition, so it serves as shared configuration. The second document applies only when `local` is active; the third applies only when `production` is active.

### 5.1. Profile expressions

`spring.config.activate.on-profile` supports profile expressions. Examples:

| Expression | Condition |
| --- | --- |
| `local` | Profile `local` is active |
| `!test` | Profile `test` is not active |
| `"production & cloud"` | Both `production` and `cloud` are active |
| `"staging | production"` | At least one of the two profiles is active |

In YAML, wrap expressions containing special characters such as `!` or `&` in quotes to prevent the parser from interpreting them as YAML syntax.

Similar expressions can be used in `@Profile`. When combining `&` and `|`, use parentheses to make logical precedence explicit; avoid hard-to-read or hard-to-test expressions.

### 5.2. Do not use legacy document activation syntax in new configurations

Since Spring Boot 2.4, the Config Data mechanism changed how documents are activated by profile. The modern form is:

~~~yaml
spring:
  config:
    activate:
      on-profile: production
~~~

Legacy projects may still contain the older syntax using `spring.profiles` to mark documents. Do not copy legacy syntax into newer Spring Boot projects without checking the documentation for your exact version. Also, never put `spring.profiles.active`, `spring.profiles.default`, or `spring.profiles.include` inside a document restricted by a profile condition; these properties must reside in a profile-unconditional document.

## 6. Grouping Profiles with `spring.profiles.group`

When an environment needs to activate multiple component profiles, passing a long list everywhere is error-prone. A **Profile group** lets you define one group name representing a set of profiles.

For example, the production environment needs:

- `production`: production environment configuration.
- `prod-database`: production database configuration.
- `prod-observability`: production metrics, tracing, and logging configuration.

You can declare the group in `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    group:
      production:
        - prod-database
        - prod-observability
~~~

When activated:

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar order-service.jar
~~~

Spring Boot activates the `production` profile along with the component profiles in the group. As a result, pipelines only need to know the group name `production`, while component structure is managed inside the application configuration.

Component files can be organized separately:

~~~text
application.yml
application-production.yml
application-prod-database.yml
application-prod-observability.yml
~~~

Example `application-prod-database.yml`:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      connection-timeout: 1500
~~~

Example `application-prod-observability.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus

logging:
  level:
    root: WARN
~~~

When `production` is active, the component configurations are loaded together. Profile groups give a meaningful name to a configuration bundle while allowing component profiles to be reused in other groups if designed cleanly.

### 6.1. Declaring multiple groups

An application can define multiple groups:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-observability
      staging:
        - staging-database
        - staging-observability
~~~

Activating `staging` activates `staging` along with its component profiles. Activating `production` activates its corresponding group.

Profile groups must be declared in a profile-unconditional configuration document. Do not place group declarations in `application-production.yml` or inside a YAML document activated only by `production`, because the application needs to know how to expand groups before fully processing profile-specific configurations.

### 6.2. How do profile groups differ from `spring.profiles.include`?

Both can add profiles, but their intended uses differ:

| Mechanism | Meaning | When to use |
| --- | --- | --- |
| `spring.profiles.active` | Directly specifies active profiles | Deployment environment chooses `local`, `staging`, or `production` |
| `spring.profiles.include` | Appends profiles always needed when a base config is used | A configuration needs to pull in shared config such as `common` |
| `spring.profiles.group` | Defines a group name representing a set of profiles | Selecting `production` needs to activate multiple component profiles |

Example of include:

~~~yaml
spring:
  profiles:
    include:
      - common
      - metrics
~~~

`include` can be used to pull in profiles unconditionally from configuration. Meanwhile, groups express the relationship between a representative profile name and its constituent profiles. When `active`, `include`, and `group` are all used together, verify expansion order and configuration precedence on your exact Spring Boot version.

Like `spring.profiles.active`, `spring.profiles.include` must be declared in a profile-unconditional document. Avoid declaring the same profile in multiple ways without clear reason; that makes the effective profile set harder to predict.

## 7. Using `@Profile` to Select Beans

Profiles affect more than YAML. Spring Framework allows conditioning beans using the `@Profile` annotation.

Suppose an application needs a mock implementation locally and a real system-calling implementation in production.

Interface declaration:

~~~java
public interface PaymentGateway {
    PaymentResult charge(String orderId, long amount);
}
~~~

Implementation for local:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class LocalPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, long amount) {
        return new PaymentResult("LOCAL-" + orderId, true);
    }
}
~~~

Implementation for production:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("production")
public class RemotePaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, long amount) {
        // Call the payment provider via the configured HTTP client.
        return new PaymentResult("REMOTE-" + orderId, true);
    }
}
~~~

When `local` is active, Spring registers `LocalPaymentGateway`. When `production` is active, Spring registers `RemotePaymentGateway`. Ensure exactly one matching implementation exists in each context; if no bean matches or multiple beans satisfy a single dependency, the application may fail to start or require an appropriate qualifier/primary bean.

You can place `@Profile` on `@Configuration` classes or `@Bean` methods:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class PaymentConfiguration {

    @Bean
    @Profile("test")
    PaymentGateway testPaymentGateway() {
        return (orderId, amount) ->
                new PaymentResult("TEST-" + orderId, true);
    }
}
~~~

### 7.1. Expressions in `@Profile`

Common usages:

~~~java
@Profile("production")
class ProductionOnlyConfiguration {
}

@Profile("local | test")
class DevelopmentConfiguration {
}

@Profile("production & cloud")
class CloudProductionConfiguration {
}

@Profile("!production")
class NonProductionConfiguration {
}
~~~

`@Profile("local | test")` means the bean is registered if either profile is active. `@Profile("production & cloud")` requires both. `@Profile("!production")` applies when `production` is not active.

An array of profile names such as `@Profile({"local", "test"})` can express an OR condition. Favor simple, readable, testable expressions.

Do not use `@Profile` as a per-user or per-request feature toggle. Profiles are resolved while building the `ApplicationContext`; dynamic feature flags and authorization are separate concerns.

## 8. Profiles in Spring Cloud Applications

Profiles are particularly helpful when the same service runs in multiple environments while sharing codebase and artifacts.

### 8.1. Combining profiles with Spring Cloud Config

When an application uses Spring Cloud Config Client, the application name and active profiles are part of the request sent to Config Server. Example:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

If launched with:

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar order-service.jar
~~~

Config Client can request the configuration set for `order-service` and the `production` profile. Config Server can return shared application configuration plus the profile-specific portion, depending on repository layout, label, and server configuration.

Distinguish clearly:
- `application.yml` in the application is a local configuration source.
- Config Server provides a remote configuration source.
- Profiles identify which configuration variant to retrieve.
- Property source precedence determines the final value when multiple sources declare the same key.

Never assume remote configuration always overrides all local values in the exact same way across every version. Import and override rules depend on Config Data, import placement, and Config Server configuration. For critical values like URLs, timeouts, or secrets, verify actual resolved outputs and test startup behavior.

### 8.2. Profiles do not replace discovery and service registries

For example, `application-production.yml` can specify gateway endpoints or connection properties for a discovery provider. Yet profiles only select configuration values. They do not register instances, perform health checks, update service lists, or pick instances for requests.

In a production application, you may simultaneously need:
- The `production` profile to load environment configuration.
- Discovery integration to locate service instances.
- Spring Cloud LoadBalancer to select suitable instances.
- Spring Cloud Context if a refresh mechanism is needed for certain beans.
- Externalized configuration to vary endpoints, credentials, and timeouts across environments.

Each component handles a distinct responsibility; do not conflate all of them under the profile concept.

## 9. Testing Profiles and Profile-Specific Configuration

Profiles affect both which beans are created and which properties are loaded, so both sides must be tested.

### 9.1. Selecting profiles in Spring Boot Tests

Use `@ActiveProfiles` to specify profiles for a test context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationProfileTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void loadsTestCatalogEndpoint() {
        assertThat(properties.baseUrl().toString())
                .isEqualTo("http://localhost:9090");
    }
}
~~~

The `application-test.yml` file can declare:

~~~yaml
catalog:
  client:
    base-url: "http://localhost:9090"
    connect-timeout: 300ms
    read-timeout: 1s
    max-attempts: 1
~~~

`@ActiveProfiles("test")` lets the test context select profiles explicitly and deterministically. Avoid relying on whatever profile happens to be set in the test runner's terminal or IDE.

### 9.2. Testing beans per profile

You can verify that the intended implementation is created. For example, if local must use a mock gateway, a test should confirm the Spring context contains `LocalPaymentGateway` and does not register the production implementation.

~~~java
@SpringBootTest
@ActiveProfiles("local")
class LocalPaymentGatewayProfileTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersLocalGateway() {
        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(LocalPaymentGateway.class);
    }
}
~~~

The example above requires importing `ApplicationContext`, AssertJ, and the project classes. The key point is that the test verifies **bean selection behavior**, not merely that a profile string exists.

### 9.3. Testing profile groups

For a `production` group containing `prod-database` and `prod-observability`, test properties from all three sources when the profile group is activated. You can use a test context with `@ActiveProfiles("production")` and assert expected beans and properties.

Beyond unit tests, CI/CD pipelines should run smoke tests booting the application with its target deployment profile. This catches missing environment variables, missing profile files, misconfigured groups, or beans lacking matching implementations.

## 10. Common Mistakes and How to Avoid Them

1. **Putting `spring.profiles.active` inside `application-production.yml`:** profile activation properties must come from a profile-unconditional configuration or external source; never use a profile file to activate itself.
2. **Confusing `spring.config.activate.on-profile` with `spring.profiles.active`:** one restricts when a document applies; the other selects active profiles.
3. **Using legacy syntax on modern Spring Boot:** since Boot 2.4, use Config Data and `spring.config.activate.on-profile` for conditional documents.
4. **Misspelling profile names:** `prod` and `production` are two distinct names. Standardize naming across pipelines and files.
5. **Putting conflicting values across multiple profiles:** inspect activation order and effective values; avoid relying on accidental runtime ordering.
6. **Duplicating entire configs across every file:** record only differences in profile-specific files to reduce drift.
7. **Using profiles as a secret or authorization mechanism:** secrets must come from secure stores; access control must be enforced independently.
8. **Creating too many combinatorial profiles:** profile groups can bundle meaningful parts, but avoid turning every minor property or variation into its own profile.
9. **Never testing the production profile:** add smoke tests using the actual deployment profile and configuration.
10. **Assuming profile groups provision infrastructure:** groups only activate additional profiles; they do not create databases, registries, secrets, or endpoints.

## 11. Workflow for Designing Profiles for a Service

When designing profiles for a Spring Cloud service, follow this sequence:

1. Identify the real environments the artifact must run in: local, test, staging, and production.
2. Put safe, reusable shared defaults in `application.yml`.
3. Create `application-{profile}.yml` files for genuine per-environment differences.
4. Choose how profiles are activated via environment variables or deployment flags; avoid hardcoding production in the artifact.
5. If an environment needs multiple component configuration groups, define `spring.profiles.group`.
6. Use `@Profile` for environment-specific bean implementations while ensuring every context has a valid implementation.
7. If using Config Server, verify application name, profiles, label, and loaded configuration sources.
8. Write tests for property binding, bean selection, profile groups, and override values.
9. Verify syntax and compatibility with the exact Spring Boot/Spring Cloud versions in use.

**Key takeaway:** A profile is a label for selecting configuration and beans during application startup. `application-{profile}.yml` supplies profile-specific settings, `spring.config.activate.on-profile` selects documents within a file, and `spring.profiles.group` bundles multiple profiles into a meaningful deployment choice. In Spring Cloud, profiles cooperate with Config Client and external configuration sources; they still have their own lifecycle and do not replace discovery, registries, load balancing, or security mechanisms.
