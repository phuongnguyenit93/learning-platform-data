# What Is a Profile and When to Split Configuration by Environment

## 1. The problem: the same application needs different values across environments

Suppose a Spring Boot service sends notifications to users. During local development on a personal machine, the application should send requests to a mock service, use generous timeouts, and allow convenient logging. When running in a test environment, the application needs to talk to integration services used to verify workflows. In production, the application must use real endpoints, enforce tighter timeouts, and enable only behaviors prepared for real users.

If those values are hardcoded directly into Java code, changing environments can require editing source code, recompiling, and repackaging. If multiple different JARs are produced just because of a service address, it is also hard to guarantee that environments are running the exact same version of the code.

Spring Boot solves this problem with **externalized configuration** and **profiles**.

- *Externalized configuration* separates operational values from Java logic, allowing values to be supplied from files, environment variables, command-line arguments, and other sources.
- A *profile* lets you name an **active configuration context**, such as `dev`, `test`, `staging`, or `prod`, so that Spring Boot loads additional configuration and can register beans suited to that context.

The core idea is **one build, multiple runtime environments**. Profiles help select the corresponding configuration slice; the property source system still determines the final value when multiple places declare the same key.

```text
                    One codebase / one JAR
                               |
                 +-------------+-------------+
                 |             |             |
              profile=dev  profile=staging profile=prod
                 |             |             |
            dev values    staging values   prod values
                 |             |             |
                 +-------------+-------------+
                               |
                    Beans use configuration
                               |
                      Application behavior
```

The diagram above illustrates three different runs of the same build. Each process has its own set of profiles and configuration sources.

## 2. What is a profile in Spring Boot really?

A Spring profile is a **name managed by the Spring Environment** used to represent a group of active conditions. One or more profiles can be active at the same time.

For example:

```text
dev
staging
prod
integration
cloud
```

Names like `dev` or `prod` are simply conventions chosen by the development team; Spring Boot does not automatically infer that an environment is production from the host address, directory name, or JAR naming. The application must receive instructions about the active profiles or use the corresponding default configuration.

Profiles typically affect two things:

1. **Profile-based configuration selection:** alongside the common `application.yml`, Spring Boot can load `application-dev.yml`, `application-prod.yml`, etc., when the corresponding profile is active.
2. **Conditional bean selection:** the `@Profile` annotation can restrict a `@Configuration`, `@Component`, or `@Bean` method to be registered only when the profile expression matches.

These two capabilities are related but distinct. A group of values can change by profile without creating multiple Java classes. Conversely, when you truly need to swap out the implementation of a feature, `@Profile` can help select the appropriate bean.

A profile is **not** a security mechanism, not a deployment environment created automatically by Spring Boot, not a replacement for a secrets management system, and does not guarantee that every value in a profile takes highest precedence if another configuration source has higher priority.

## 3. Common configuration and profile-specific configuration

An easy-to-understand way to organize configuration is to put shared values in `application.yml` and place only the differences in files with a profile suffix.

Project example:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
```

Common file `application.yml`:

```yaml
notification:
  enabled: false
  timeout: 3s
  endpoint: https://example.invalid/notification
```

File `application-dev.yml`:

```yaml
notification:
  enabled: true
  timeout: 10s
  endpoint: http://localhost:9001/notification
```

File `application-staging.yml`:

```yaml
notification:
  enabled: true
  timeout: 5s
  endpoint: https://staging.example.invalid/notification
```

File `application-prod.yml`:

```yaml
notification:
  enabled: true
  timeout: 2s
  endpoint: https://production.example.invalid/notification
```

The `example.invalid` domain names here are illustrative addresses only; they do not represent callable live services.

When `dev` is enabled, the properties in `application-dev.yml` participate in configuration. When `prod` is enabled, `application-prod.yml` participates. The common configuration continues to be used for properties not overridden by a higher-precedence source.

For example, if `application-prod.yml` only contains:

```yaml
notification:
  timeout: 2s
```

then `notification.timeout` can receive `2s` from the profile-specific file, while `notification.enabled` and `notification.endpoint` continue using the common values, provided no other source overrides them.

This avoids copying the entire identical configuration into every file. Shared values change in one place; actual differences between environments remain clearly visible.

### Are profile-specific files loaded automatically?

Merely having `application-prod.yml` present does not mean the application loads it as active configuration. The `prod` profile must be activated, or another valid profile configuration must cause it to be used.

If no profile is explicitly active, Spring uses the default profile group, typically named `default`. `default` is the **default profile name**, not synonymous with `dev`. Therefore, do not assume that running on a laptop causes Spring Boot to automatically enable `dev`.

Similarly, when an application runs on a production machine without being configured to activate `prod`, `application-prod.yml` does not automatically become effective configuration.

## 4. How to activate a profile at startup

With Spring Boot, the most common way is to pass the value of `spring.profiles.active` before or when the application starts.

### 4.1. Passing command-line arguments

Example running an executable JAR:

```bash
java -jar app.jar --spring.profiles.active=dev
```

To run in production:

```bash
java -jar app.jar --spring.profiles.active=prod
```

`app.jar` is a placeholder name: replace it with the actual JAR after packaging the application. The `--spring.profiles.active=prod` argument is a command-line argument configuration source that Spring Boot understands in standard startup.

This option is easy to observe during testing because the profile is visible directly in the run command.

### 4.2. Using environment variables

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

The `SPRING_PROFILES_ACTIVE` variable supplies the value for the `spring.profiles.active` property. For automated deployment systems, this is often convenient because the same JAR is launched with different environment variables.

In PowerShell, it is good practice to remove the variable after a practice session so subsequent runs do not accidentally inherit the profile. In Bash, using `SPRING_PROFILES_ACTIVE=prod java -jar app.jar` applies only to that command; if you have run `export`, you may need `unset SPRING_PROFILES_ACTIVE` to remove it from the current shell.

### 4.3. Using a Java system property

You can set a profile via a JVM property:

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

Here `-Dspring.profiles.active=dev` must appear before `-jar` so the JVM treats it as a system property. Unlike the `--spring.profiles.active=dev` argument placed after the JAR name, the `-D` form belongs to the JVM.

### 4.4. Configuring a profile in the common file

In some applications, `application.yml` can declare:

```yaml
spring:
  profiles:
    active: dev
```

However, if you want the same build to deploy easily across multiple environments, it is usually better to let the runtime platform supply the profile via environment variables or startup arguments. Hardcoding `dev` inside packaged configuration makes it easy for deployers to forget that the application has a default value for profile selection.

In particular, **do not put `spring.profiles.active` inside a file or YAML document that is itself activated by a profile**, because Spring Boot restricts profile-selection properties in such locations. For example, do not put `spring.profiles.active=prod` inside `application-dev.yml` expecting it to switch automatically to `prod`.

## 5. How do beans actually receive profile-specific configuration?

Profiles select which configuration sources are considered; beans still receive values through Spring Boot's configuration mechanism.

Suppose we define:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        boolean enabled,
        Duration timeout,
        URI endpoint
) {
}
```

Register the configuration on the main application class:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
```

In Spring Boot 3, a record with a single constructor like this example supports constructor binding without needing `@ConstructorBinding`.

A service depends only on the configuration object:

```java
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public boolean enabled() {
        return properties.enabled();
    }

    public String destination() {
        return properties.endpoint().toString();
    }
}
```

When starting with `--spring.profiles.active=dev`, the endpoint value in `NotificationProperties` will be `http://localhost:9001/notification` per the example. When starting with `prod`, the endpoint will be `https://production.example.invalid/notification`, assuming no environment variable or other argument overrides it.

Notably: **`NotificationService` contains no `if (profile.equals("prod"))`**. It simply uses values already bound into a typed dependency. This is the preferred approach when environments differ in values while business logic remains identical.

## 6. When should you separate configuration by environment?

Use profiles when there is **a stable, operationally meaningful set of differences** between runtime contexts. Those differences typically appear together and are chosen when starting an application instance.

| Need | Example | Is a profile appropriate? |
| --- | --- | --- |
| Different external service endpoints | Dev calls mock, staging calls test service, prod calls real service | Yes, if this group of values is tied to the environment |
| Different observability policies | Dev logs verbosely, prod logs moderately | Profiles can be used combined with logging configuration |
| Different infrastructure resources | Datasource or queue names per environment | Profiles can be used for non-sensitive names/URLs; supply secrets separately |
| Selecting mock beans in development | Dev uses simulated adapter, prod uses real adapter | `@Profile` can be used for beans |
| Enabling a contextual integration group | Profile `integration` activates integration test config | Yes, if the shared config set is clear |
| A user wants a personal preference | User A prefers light theme, B prefers dark | No; this is user data or preference, not an application profile |
| Different pricing per customer | Read from database per customer | Should not use one profile per customer |
| Temporarily disabling a specific feature | `feature.checkout-enabled=false` | Usually use a property or feature flag directly |
| Rotating secrets at runtime | Tokens, passwords, certificates | Use a secret store/environment variables; profiles are not for holding secrets |

The core design question is: **“Do these values change because of a shared startup context, or because of independent decisions?”**

If multiple settings always travel together by environment, profiles help organize them cleanly. If a value can change independently by customer, request, or time, do not create a new profile just to hold it.

## 7. When is a single property enough without adding a profile?

Suppose the application only needs to adjust a timeout:

```yaml
notification:
  timeout: 3s
```

At deployment time, it can be overridden with:

```bash
java -jar app.jar --notification.timeout=7s
```

Or the corresponding environment variable such as `NOTIFICATION_TIMEOUT=7s`. If only a single value changes and there is no environment-specific rule set to organize, a property provided from an external source can be simpler than creating an extra `application-special.yml`.

Similarly, if the application implements an optional feature:

```yaml
notification:
  enabled: false
```

then a clearly named configuration flag is usually better than creating a `notification-off` profile. A profile expresses *a context or set of conditions*; a flag expresses *the state of a single feature*. Do not turn profiles into a long list of every combination of independent flags.

Example to avoid:

```text
dev-with-email
dev-without-email
staging-with-email
staging-without-email
prod-with-email
prod-without-email
```

If environment and enabling email are two independent decisions, you can choose profiles `dev/staging/prod` to manage environment differences, and use `notification.enabled` to control the feature. This prevents the number of profiles from multiplying with every flag.

## 8. Profile-specific configuration overrides per key, not the entire application

Look at the example:

```yaml
# application.yml
notification:
  enabled: false
  timeout: 3s
  endpoint: https://example.invalid/notification
```

```yaml
# application-prod.yml
notification:
  timeout: 2s
  endpoint: https://production.example.invalid/notification
```

When profile `prod` is selected, `timeout` and `endpoint` take values from the profile-specific file, while `enabled` still comes from the common configuration. The mechanism operates on the properties contributed by configuration sources; there is no default rule that the entire `notification` branch must be deleted and completely replaced.

For complex collections such as lists, binding rules can differ from individual standalone properties; do not assume elements in every list are merged across profiles the same way maps or scalars are. In the first example, all three fields are independent and easy to observe.

However, **profiles do not override every other configuration source**. For example:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.timeout=9s
```

In a standard setup, `--notification.timeout=9s` on the command line has higher precedence than `notification.timeout=2s` in `application-prod.yml`. The bean will receive a timeout of nine seconds. When investigating configuration, check the entire precedence chain of sources, not just the profile-specific file.

## 9. Multiple profiles can be active together

Spring Boot can accept multiple profiles in a single run, for example:

```bash
java -jar app.jar --spring.profiles.active=staging,cloud
```

This can be useful when distinguishing two separate dimensions:

- `staging` describes the deployment stage and service endpoints.
- `cloud` describes the infrastructure environment that has certain dedicated features or settings.

Combining them is only useful if the meaning of both profiles is clearly designed. Do not activate `dev` and `prod` simultaneously and expect Spring Boot to automatically know which value is “right” for each purpose.

For profile-specific configurations in the same location group, a profile evaluated later can override values from an earlier profile when both declare the same key. Thus `--spring.profiles.active=staging,cloud` and `--spring.profiles.active=cloud,staging` can produce different results if their respective files define overlapping properties.

Even so, the order among **configuration sources and location groups** still has an effect. A file outside the JAR or a command-line argument has different precedence from a file packaged inside the JAR. Do not treat “last profile wins” as an absolute rule for every way configuration sources are organized.

### The default profile

When no active profile is set, Spring uses the default profile, typically named `default`. Spring Boot can load `application-default.yml` if it exists. You can customize the default profiles using `spring.profiles.default` in a valid configuration location.

A common design choice is to let `application.yml` hold safe, environment-agnostic values, and then explicitly enable `dev`, `staging`, or `prod` in the launch command. That way, deployment into real environments can be observed and controlled.

## 10. Use `@Profile` when you need to select beans, not just values

There are differences that cannot be solved with just a URL or a flag: development uses a simulated bean, while other environments use a real implementation. In those cases, Spring supports `@Profile` to register beans only when the condition matches.

For example, suppose you want a fixed clock in a special test profile, and the system clock in other profiles:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ClockConfiguration {

    @Bean
    @Profile("time-simulation")
    Clock simulationClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }

    @Bean
    @Profile("!time-simulation")
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
```

When `time-simulation` is active, the application has the fixed `Clock` bean; when that profile is not active, the application gets the system `Clock`. The syntax `!time-simulation` is the negation condition in a profile expression.

`@Profile` can be placed on a `@Configuration` class or on a `@Bean` method. It can also be applied to Spring-scanned components, depending on the goal.

However, do not use `@Profile` to create two identical service classes that differ only by a URL. In that case, a single bean receiving a `@ConfigurationProperties` object is usually clearer and reduces duplication.

You should also consider cases where a bean is missing or multiple beans of the same type exist due to activating an unexpected profile combination. If part of the application requires exactly one bean of type `Clock`, the configuration must ensure every supported profile combination satisfies that condition.

## 11. Profiles and multi-document YAML configuration

You do not necessarily have to create a separate file for every profile. Spring Boot also supports a single YAML file containing multiple documents separated by `---`, where each document can be activated by profile via `spring.config.activate.on-profile`.

Example alternative to separate files:

```yaml
# application.yml - common document
notification:
  enabled: false
  timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev

notification:
  enabled: true
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: prod

notification:
  enabled: true
  timeout: 2s
```

When `dev` is active, the `on-profile: dev` document is applied; when `prod` is active, the `on-profile: prod` document is applied.

Both organizational styles have their place:

- **Separate files:** `application-dev.yml` and `application-prod.yml` make large or complex environment differences easy to inspect and review.
- **Multiple documents in one file:** convenient when differences are small and you want an overview in a single place.

Choose one primary organizational style for the same group of properties in practice to avoid making results hard to trace. The fact that Spring Boot supports both does not mean you should mix them simultaneously.

Note that `spring.config.activate.on-profile` is a condition for **activating a configuration document**, whereas `spring.profiles.active` is the mechanism for **selecting active profiles**. Do not put profile-selection properties such as `spring.profiles.active`, `spring.profiles.default`, or `spring.profiles.include` inside a profile-activated document because of Config Data constraints.

## 12. Profile groups: grouping profiles under a convenient name

When an environment always requires multiple profiles together, Spring Boot provides **profile groups**. For example, production needs both `prod-db` and `prod-messaging`:

```yaml
# application.yml - common document, without on-profile
spring:
  profiles:
    group:
      production:
        - prod-db
        - prod-messaging
```

When running:

```bash
java -jar app.jar --spring.profiles.active=production
```

the `production` group causes member profiles `prod-db` and `prod-messaging` to participate as well. As a result, deployment commands express a high-level intent without listing every dependent profile.

However, do not create a profile group just because a configuration file is long. This mechanism fits when a set of profiles has independent meaning yet needs to be enabled together across many scenarios.

Under Spring Boot's Config Data rules, `spring.profiles.group` declarations must live in a non-profile-specific configuration document, similar to `spring.profiles.active` and `spring.profiles.include`. Placing a group inside `application-prod.yml` to generate additional profiles when that file loads is an invalid design.

## 13. Combining profiles with environment variables and secret stores

A common mistake is treating `application-prod.yml` as the place to put all production information, including passwords and tokens. Separate the concerns:

**Profiles** are suited for environment-describing, non-sensitive values such as timeouts, public URLs of a service, connection limits, or logging policies.

**Secret sources** are suited for passwords, access keys, tokens, and certificates. These values can be supplied via environment variables, the deployment platform's secret store, or an appropriate Config Data mechanism.

Example in `application-prod.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal.invalid:5432/app

notification:
  timeout: 2s
```

And in the runtime environment, the password can be supplied via the corresponding environment variable, such as `SPRING_DATASOURCE_PASSWORD`, using the platform's secrets management tool. Do not commit real passwords to Git just to make a profile file feel complete.

This keeps configuration intent clear: the `prod` profile selects the shared parameter set for production, while secrets are supplied where access to them is controlled. Profiles do not encrypt or conceal values inside files.

For sensitive information, also avoid printing the entire `Environment` or logging configuration at startup. When diagnostics are necessary, inspect only harmless keys or use diagnostic endpoints that have access control and sensitive-value sanitization enabled.

## 14. Testing profile-specific configuration

An application with multiple profiles risks running fine in `dev` yet failing to start in `prod` due to missing keys, type mismatches, or missing beans. Therefore, you need ways to verify every supported profile combination.

### 14.1. Direct verification via run commands

To test them one by one:

```bash
java -jar app.jar --spring.profiles.active=dev
java -jar app.jar --spring.profiles.active=staging
java -jar app.jar --spring.profiles.active=prod
```

Each command is a separate run; stop the previous process before running the next if needed. All use the same JAR and only vary how it is launched. Do not treat a successful `dev` run as automatic proof that `prod` is also correct.

### 14.2. Selecting profiles in Spring tests

For tests using Spring Test, `@ActiveProfiles` lets you select the profile for the test context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class NotificationApplicationTest {

    @Test
    void contextLoads() {
    }
}
```

When using the `test` profile, you can place `application-test.yml` under `src/test/resources` or use other test configuration sources as appropriate. This separates the test environment from production configuration without modifying main sources.

Remember that `@ActiveProfiles` controls profiles **in the test context**, not a switch that changes environment variables of a running production process.

### 14.3. Observing active profiles and effective values

For experimentation, you can print active profile names and a harmless key:

```java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

// Place this method inside a @Configuration or @SpringBootApplication class.
@Bean
ApplicationRunner showConfig(Environment env) {
    return args -> {
        System.out.println("Active profiles: "
            + Arrays.toString(env.getActiveProfiles()));
        System.out.println("Notification timeout: "
            + env.getProperty("notification.timeout"));
    };
}
```

`getActiveProfiles()` shows explicitly activated profiles; when this list is empty, Spring may still use default profiles. If you also want to inspect those, `getDefaultProfiles()` provides the default list.

In real applications, prefer managed observability practices and avoid logging sensitive data. Spring Boot Actuator can expose environment details or `@ConfigurationProperties` objects when properly configured, though those endpoints must be secured.

## 15. Common mistakes

### 15.1. Assuming the machine name determines the profile

A machine with a hostname containing `prod` does not cause Spring Boot to automatically activate the `prod` profile. You must set `SPRING_PROFILES_ACTIVE`, `spring.profiles.active`, or another valid profile-selection mechanism. When debugging deployment issues, inspect the actually active profiles instead of guessing from the machine name.

### 15.2. Hardcoding environment profiles in code

Example:

```java
String active = "prod";
if ("prod".equals(active)) {
    // Select service URL here
}
```

This is just a Java conditional branch, not a Spring profile. Writing code like this mixes deployment decisions into business logic and forces code edits when switching environments. If only a URL differs, configuring a property is more appropriate.

### 15.3. Putting too many secrets in a profile file

An `application-prod.yml` file in a repository does not become secure simply because it has `prod` in its name. Passwords, tokens, and access keys must be supplied through appropriate secure channels. Profiles decide which documents or beans are activated; they do not grant permissions or encrypt data.

### 15.4. Activating conflicting profiles

If you enable `dev,prod` simultaneously, both sets of files may declare `notification.endpoint`. The final value will depend on source precedence rules and profile ordering in the loaded configuration. `@Profile("dev")` and `@Profile("prod")` beans may also both be registered and cause conflicts if they serve the same role.

Design profiles to be compatible with each other; avoid simultaneously enabling two profiles representing mutually exclusive environments unless the application has clear handling rules.

### 15.5. Assuming the application automatically reloads running profiles

Changing `application-prod.yml` or environment variables after the application has started does not guarantee already-created beans update their values. In typical Spring Boot applications, operators restart the process to apply new configuration. Dynamic refresh mechanisms must be designed explicitly.

### 15.6. Using profiles for per-user or per-request decisions

Spring profiles apply to the application context at startup. Decisions like “customer A gets a 10% discount,” “user B has admin permissions,” or “this request should run campaign X” belong to business data, authorization, or feature flags. Do not create Spring profiles per user or per request.

## 16. Step-by-step practice: one JAR for three environments

Create an application with `application.yml`, `application-dev.yml`, and `application-prod.yml` as in section 3, keeping `NotificationProperties` and `NotificationService` unchanged.

**Step 1 — Run with dev.**

```bash
java -jar app.jar --spring.profiles.active=dev
```

Prediction: `enabled=true`, `timeout=10s`, `endpoint=http://localhost:9001/notification`.

**Step 2 — Run with prod.**

```bash
java -jar app.jar --spring.profiles.active=prod
```

Prediction: `enabled=true`, `timeout=2s`, `endpoint=https://production.example.invalid/notification`.

**Step 3 — Override a key from the command line.**

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.timeout=8s
```

Prediction: the endpoint still comes from `prod` configuration, while the timeout is eight seconds because command-line arguments have higher precedence than Config Data files in standard scenarios.

**Step 4 — Omit profiles and override arguments.**

```bash
java -jar app.jar
```

If no other configuration sources or profiles are involved, prediction: `enabled=false`, `timeout=3s`, and the default endpoint from `application.yml`. If the result differs, check actual active/default profiles as well as any lingering environment variables.

**Step 5 — Create a test with `@ActiveProfiles("test")`.**

Place `application-test.yml` with `notification.timeout: 1s`. Write a test that starts the context and reads `NotificationProperties.timeout()` to verify the test value is bound properly. Use only dummy endpoints and safe data.

After each step, answer:

1. Which profile is active?
2. Which files were loaded because of that profile?
3. Which keys come from common configuration and which are overridden?
4. Is there any source with higher precedence than the profile-specific file?
5. Did any bean require Java code changes when switching environments?

The answer to step 5 is especially important: profiles swap configuration sets for the test context, while the bean code does not need to know whether it is running in `test` or `prod`.

## 17. A maintainable approach to designing configuration

When starting to design configuration for a service, you can follow this decision sequence:

1. **Identify needed properties:** endpoints, timeouts, connection limits, enable/disable flags, etc.
2. **Set safe defaults in `application.yml`:** prefer values that do not trigger dangerous operations if an operator forgets to enable a profile.
3. **Group true environment differences:** such as `application-dev.yml` and `application-prod.yml`, but only when they represent a meaningful set of values.
4. **Let environment variables or the deployment platform decide the active profile:** the same build is released to different places.
5. **Supply secrets separately:** do not put real credentials in committed configuration.
6. **Bind configuration into typed objects:** use `@ConfigurationProperties` so beans receive controlled values instead of scattering key names throughout code.
7. **Use `@Profile` on beans only when behavior/implementation truly differs:** do not create multiple beans if only a few values differ.
8. **Test all supported profiles:** specifically verify required values are present and no beans are missing or duplicated.

A small convention table in deployment documentation can help the whole team:

| Profile | Purpose | Key differences | Secret source |
| --- | --- | --- | --- |
| `dev` | Personal machine development | Mock/local endpoints, verbose logs | Developer machine or dev secrets |
| `test` | Running automated tests | Mock services, test database | Test secrets or none needed |
| `staging` | Pre-release verification | Integration services, near-production policies | Staging secrets |
| `prod` | Serving real users | Real endpoints, appropriate resource limits | Production secrets |

This table is only a reference design convention. Not every application needs all four profiles, and profile names should accurately reflect how the project's deployments are grouped.

## 18. Key takeaways

A profile is **Spring's mechanism for selecting configuration contexts and bean registrations**, allowing an application to use different values or components depending on the runtime environment. A profile is not an entire environment; it is a conditional label that Spring Boot can use to load corresponding configuration files and apply `@Profile`.

You should separate configuration by profile when a group of differences moves together by environment, when maintaining **one JAR for multiple deployment targets**, or when selecting a bean implementation for a clear context. Do not use profiles as a substitute for per-user dynamic values, independent feature flags, or secrets management systems.

The practical flow is:

```text
Select profile at startup
       |
       v
Load common and profile-specific configuration
       |
       v
Resolve precedence among property sources
       |
       v
Bind / inject into beans
       |
       v
One Java codebase operates with environment-appropriate values
```

When encountering the symptom “`prod` is enabled, yet the bean still uses another value,” inspect the **actually active profiles**, **loaded files**, and **higher-precedence sources** before checking binding. That approach separates profile-selection issues from property-source issues or data-binding errors.

Further reading: [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) and [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).