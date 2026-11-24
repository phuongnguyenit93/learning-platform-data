# Adding Profiles with `SpringApplication` and `ConfigurableEnvironment`

Spring Profiles let the same Spring Boot application operate with different configuration sets, such as `dev`, `test`, and `prod`. Usually, profiles are specified via the `spring.profiles.active` property in configuration or through startup arguments. However, there are also cases where **the program wants to proactively add profiles directly in Java code**.

Spring Boot provides `SpringApplication.setAdditionalProfiles(...)` for that need. Spring Framework also offers `ConfigurableEnvironment.addActiveProfile(...)` and `ConfigurableEnvironment.setActiveProfiles(...)` to manage the profile set inside a specific `Environment`. These three methods are related, yet **do not share the exact same meaning**.

This lesson introduces both ways to add profiles, application order, timing requirements prior to bean initialization, and how to observe profile-specific configuration in Spring Boot 3.3.x (Java 21).

## 1. What do profiles affect?

A *profile* is a name representing a condition or runtime environment, such as `dev`, `prod`, `mock-payment`, or `metrics`. When a profile is active, Spring can:

- Load corresponding configuration files, such as `application-dev.yml` and `application-prod.properties`.
- Activate beans or configuration classes annotated with `@Profile("dev")`, `@Profile("prod")`.
- Select YAML documents conditioned by `spring.config.activate.on-profile`.
- Combine with other profiles according to Config Data ordering and override rules.

Suppose there are three files:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-metrics.yml
~~~

`application.yml` contains common values:

~~~yaml
spring:
  application:
    name: profile-demo

app:
  message: "Default application"
  audit:
    enabled: false
~~~

`application-dev.yml`:

~~~yaml
app:
  message: "Application for development"
~~~

`application-metrics.yml`:

~~~yaml
app:
  audit:
    enabled: true
~~~

If the application runs with both `dev` and `metrics`, the result in the example is:

~~~text
app.message = Application for development
app.audit.enabled = true
~~~

This illustrates that two profiles can be active together and each file only needs to override the keys it owns. If multiple files contain the same key, Spring Boot determines the effective value by Config Data precedence and profile order.

## 2. The direct approach: `SpringApplication.setAdditionalProfiles(...)`

To add profiles before running the application, instantiate a `SpringApplication` object instead of calling the static `SpringApplication.run(...)` method directly.

~~~java
package com.example.profiledemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        // Add a profile for this run.
        application.setAdditionalProfiles("metrics");

        // Start the application after configuring the profile.
        application.run(args);
    }
}
~~~

Here, `metrics` is an **additional profile** of `SpringApplication`. When startup begins, Spring Boot includes this profile in the active profile set used, alongside profiles validly activated from external sources.

Example running from JAR:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev
~~~

The application then uses both `dev` from the CLI and `metrics` added in code. Application values from the previous section can come from `application-dev.yml` and `application-metrics.yml`.

### Why use "Additional" instead of setting a single mandatory profile?

`setAdditionalProfiles("metrics")` preserves profiles already activated from other sources. If the deployment environment runs with `--spring.profiles.active=prod`, the program can still add `metrics` without requiring operators to remember passing both.

Typical intent:

~~~text
Profile chosen by environment:   dev / test / prod
Profile added by application:    metrics

dev run:   dev + metrics
prod run:  prod + metrics
~~~

This method fits profiles representing additive features or shared configuration groups. Do not automatically enable profiles with dangerous behavior or behavior unsuitable across all environments.

### Adding multiple profiles

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);

application.setAdditionalProfiles("metrics", "observability");
application.run(args);
~~~

This is a call with two profile names. The API accepts a varargs parameter `String...`.

### When must it be called?

Call it **before `application.run(args)`**. If you use:

~~~java
SpringApplication.run(ProfileDemoApplication.class, args);
~~~

the application has already started its boot lifecycle on that line, leaving no opportunity to customize `SpringApplication` with `setAdditionalProfiles` before context creation. Use the instance form when bootstrap customization is needed.

## 3. How does `setAdditionalProfiles` differ from `spring.profiles.active`?

`spring.profiles.active` represents the active profile list determined from property sources. This property follows normal precedence order: for example, a value in CLI arguments can override `spring.profiles.active` in `application.yml`.

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

Run:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=prod
~~~

In a simple scenario, the CLI profile `prod` replaces `dev` declared in the file; that is the behavior of `spring.profiles.active`. However, `metrics` configured via `SpringApplication.setAdditionalProfiles("metrics")` is still added to the profile set used at startup.

Comparison:

| Mechanism | Meaning |
| --- | --- |
| `spring.profiles.active=dev` | Specifies the active profile set via property |
| `--spring.profiles.active=prod` | Specifies the active profile set from CLI, can override file property |
| `application.setAdditionalProfiles("metrics")` | Adds `metrics` for this run alongside profiles from other config sources |
| `spring.profiles.include=common` | Adds profiles via Spring Boot's configuration mechanism |
| `spring.profiles.group.prod=...` | When enabling a group profile, activates member profiles too |

One thing to avoid: do not think of `setAdditionalProfiles` as **writing `spring.profiles.active` into a file**. It is an API on the bootstrap object affecting the current run.

## 4. Observing active profiles with `Environment`

Spring Framework provides `Environment` to read profile information and configuration properties. Use an `ApplicationRunner` to observe them after the application starts:

~~~java
package com.example.profiledemo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        application.setAdditionalProfiles("metrics");
        application.run(args);
    }

    @Bean
    ApplicationRunner showProfiles(Environment environment) {
        return args -> {
            System.out.println(
                    "Active profiles: "
                            + Arrays.toString(environment.getActiveProfiles()));

            System.out.println(
                    "Default profiles: "
                            + Arrays.toString(environment.getDefaultProfiles()));

            System.out.println(
                    "app.message: " + environment.getProperty("app.message"));

            System.out.println(
                    "app.audit.enabled: "
                            + environment.getProperty("app.audit.enabled"));
        };
    }
}
~~~

Run:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev
~~~

Output may look similar to:

~~~text
Active profiles: [metrics, dev]
Default profiles: [default]
app.message: Application for development
app.audit.enabled: true
~~~

The order of names in the `getActiveProfiles()` array depends on how they were collected during bootstrap; **do not depend on a fixed print order unless the program explicitly establishes one**. The key point is that both profiles are active.

`getDefaultProfiles()` returns fallback profiles, typically containing `default`; these profiles are used when **there are no active profiles**. Their presence in this API output does not mean the `default` profile is active simultaneously with `dev`.

## 5. What is `ConfigurableEnvironment`?

`Environment` is the interface for querying properties and profiles. `ConfigurableEnvironment` extends it with mutating operations, including:

~~~java
void setActiveProfiles(String... profiles);
void addActiveProfile(String profile);
void setDefaultProfiles(String... profiles);
String[] getActiveProfiles();
String[] getDefaultProfiles();
~~~

`ConfigurableEnvironment` lives in package:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
~~~

Three primary operations to distinguish:

- `addActiveProfile("metrics")`: **appends** `metrics` to the active profile set while keeping existing names.
- `setActiveProfiles("dev", "metrics")`: **replaces the entire** active profiles set on that `Environment` object with the supplied list.
- `setDefaultProfiles("local")`: replaces the **default profiles** set used when no active profile exists; it is not the same as adding to active profiles.

Example with a standalone `ConfigurableEnvironment`:

~~~java
import java.util.Arrays;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.StandardEnvironment;

public class EnvironmentExample {

    public static void main(String[] args) {
        ConfigurableEnvironment environment = new StandardEnvironment();

        environment.setActiveProfiles("dev");
        environment.addActiveProfile("metrics");

        System.out.println(Arrays.toString(environment.getActiveProfiles()));
        // Contains "dev" and "metrics".
    }
}
~~~

`StandardEnvironment` is a `ConfigurableEnvironment` implementation in Spring Framework. In this example it is **an independent object** solely to demonstrate the API. Creating `new StandardEnvironment()` and modifying it **does not automatically change the Environment of a running Spring Boot application**. To affect the application, you must operate on the actual Environment used by `SpringApplication`.

## 6. Adding profiles with `ConfigurableEnvironment` before running the application

You can proactively supply a `ConfigurableEnvironment` to `SpringApplication`. The example below is for a **non-web** application so `StandardEnvironment` is used cleanly:

~~~java
package com.example.profiledemo;

import java.util.Arrays;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.StandardEnvironment;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        // Create Environment prior to bootstrap.
        ConfigurableEnvironment environment = new StandardEnvironment();

        // Add profile to the Environment attached to SpringApplication.
        environment.addActiveProfile("metrics");

        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        // Example for a console/batch application without a web server.
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setEnvironment(environment);

        application.run(args);
    }
}
~~~

When the environment above is used to launch the application, the `metrics` profile has already been set **before Config Data loading and bean registration**, so Spring can evaluate `application-metrics.yml` and `@Profile("metrics")` conditions.

**Limitation of this example:** Spring Boot has specific `Environment` and `ApplicationContext` types tailored to servlet, reactive, or non-web applications. Do not arbitrarily use `StandardEnvironment` to replace the environment in a web application needing servlet/reactive-specific property sources. In typical Spring Boot applications, if you only want to add profiles, `setAdditionalProfiles(...)` is usually simpler and less tied to environment type.

Another way to use `ConfigurableEnvironment` is obtaining the actual Environment object prepared during bootstrap. What matters is not where the `environment` variable is constructed, but **when modifications occur and whether that exact object is used by SpringApplication**.

## 7. `addActiveProfile` vs. `setActiveProfiles`: add or replace?

Suppose Environment currently has active profiles:

~~~text
[dev]
~~~

Calling:

~~~java
environment.addActiveProfile("metrics");
~~~

changes the profile set to:

~~~text
[dev, metrics]
~~~

However, calling:

~~~java
environment.setActiveProfiles("metrics");
~~~

replaces the existing profile set with:

~~~text
[metrics]
~~~

For applications with environment-specific configuration, this difference is huge: calling `setActiveProfiles("metrics")` can drop `dev` or `prod` from the active profiles managed by that Environment.

Contrasting example:

~~~java
ConfigurableEnvironment environment = new StandardEnvironment();

environment.setActiveProfiles("dev");
environment.addActiveProfile("metrics");
// Active set: dev, metrics.

environment.setActiveProfiles("prod");
// Active set: prod. Both dev and metrics are no longer in this set.
~~~

This directly demonstrates the Spring Framework API. During a Spring Boot run, Config Data and other configuration sources also participate in resolving profiles; therefore, for predictable results, prefer adjusting profiles via one clearly chosen bootstrap mechanism.

### Which API fits an "additive" requirement?

| Requirement | Appropriate API |
| --- | --- |
| Add a profile when creating a Spring Boot application | `SpringApplication.setAdditionalProfiles(...)` |
| Already have the actual bootstrap `ConfigurableEnvironment` and want to preserve existing profiles | `ConfigurableEnvironment.addActiveProfile(...)` |
| Intentionally redefine the entire active profiles set in an Environment | `ConfigurableEnvironment.setActiveProfiles(...)` |
| Change only the fallback used when no profile is active | `ConfigurableEnvironment.setDefaultProfiles(...)` |

The names `setActiveProfiles` and `setAdditionalProfiles` sound similar, yet one **replaces the Environment's active set**, while the other **adds profiles to SpringApplication**.

## 8. Why does the timing of adding a profile determine the result?

Profiles can influence two major steps during startup:

1. **Loading Config Data:** reading `application-dev.yml`, `application-prod.yml`, or profile-activated YAML documents.
2. **Bean registration:** evaluating `@Profile` on `@Configuration`, `@Component`, bean factory methods, and other configuration definitions.

These steps occur across the startup lifecycle, so profiles must be established early if you want both **file loading** and **bean selection** to reflect them.

Example that is **unsuitable** for activating application-wide profile configuration:

~~~java
@Component
class LateProfileChange implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    LateProfileChange(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        environment.addActiveProfile("metrics");
    }
}
~~~

In this example, `ApplicationRunner` executes **after the ApplicationContext has already been refreshed**. Calling `addActiveProfile` may modify the active name list inside the Environment object at that point, yet **does not cause Spring Boot to go back and load `application-metrics.yml`** nor **re-register previously skipped `@Profile("metrics")` beans**.

Consequently, reading `getActiveProfiles()` afterward may show `metrics`, while inspecting beans or properties from the metrics file yields unexpected results. This is a **late-timing** mistake, not an API syntax error.

Similarly, do not use `@PostConstruct` inside a normal bean to activate profiles that the system needed from the start of bootstrap.

Place profile-addition intent at the entry point, before `run(args)`, or in a bootstrap hook with guaranteed execution order. For most cases, `SpringApplication.setAdditionalProfiles` is the direct choice.

## 9. Example using `@Profile` to enable matching beans

Once profiles are configured via one of the valid pre-startup mechanisms, Spring can select beans according to `@Profile` conditions.

~~~java
package com.example.profiledemo;

public interface NotificationSender {
    String send(String message);
}
~~~

Development implementation:

~~~java
package com.example.profiledemo;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public String send(String message) {
        return "Console: " + message;
    }
}
~~~

Production implementation:

~~~java
package com.example.profiledemo;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class ProductionNotificationSender implements NotificationSender {

    @Override
    public String send(String message) {
        return "Production sender: " + message;
    }
}
~~~

In this minimal example, `send` merely returns a string to illustrate bean selection; it performs no external delivery. If the application injects a single `NotificationSender`, ensure the active profile set produces exactly one matching implementation. With neither `dev` nor `prod`, there may be no bean; with both enabled, there may be multiple beans of the same type.

Verification bean example:

~~~java
package com.example.profiledemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    ApplicationRunner sendTestNotification(NotificationSender sender) {
        return args -> System.out.println(sender.send("Hello"));
    }
}
~~~

Running with `--spring.profiles.active=dev` and additional profile `metrics` selects `ConsoleNotificationSender`. Running with `prod` selects `ProductionNotificationSender`. Having `metrics` present here does not create another implementation because no bean is annotated with `@Profile("metrics")`.

**Do not use `@Profile` to define precedence order among YAML files.** `@Profile` decides whether a bean is registered; `application-<profile>.yml` files and properties inside belong to Config Data.

## 10. Combining two profiles with two different configuration types

A common organizational pattern uses one profile for deployment environment and another profile for an auxiliary capability.

Example:

~~~text
Environment profile: dev or prod
Auxiliary profile:   metrics
~~~

File layout:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-prod.yml
└── application-metrics.yml
~~~

`application.yml`:

~~~yaml
app:
  name: customer-service
  endpoint: https://api.example.org
  monitoring:
    enabled: false
~~~

`application-dev.yml`:

~~~yaml
app:
  endpoint: http://localhost:8080
~~~

`application-prod.yml`:

~~~yaml
app:
  endpoint: https://api.production.example.org
~~~

`application-metrics.yml`:

~~~yaml
app:
  monitoring:
    enabled: true
~~~

Bootstrap code:

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);
application.setAdditionalProfiles("metrics");
application.run(args);
~~~

When running with `--spring.profiles.active=dev`, the final configuration in the example:

~~~text
app.name = customer-service
app.endpoint = http://localhost:8080
app.monitoring.enabled = true
~~~

When running with `--spring.profiles.active=prod`:

~~~text
app.name = customer-service
app.endpoint = https://api.production.example.org
app.monitoring.enabled = true
~~~

This example has no overlapping keys between `application-dev.yml`/`application-prod.yml` and `application-metrics.yml`, so observing the outcome does not depend on override order across these profiles. If multiple profile-specific files declare `app.endpoint`, the outcome must be determined by actual profile order and location group order.

## 11. Adding profiles from a programmatic value decided prior to bootstrap

Sometimes a launcher accepts a custom flag and decides to add a profile. For instance, a console application accepts `--enable-metrics` per its own launcher convention:

~~~java
package com.example.profiledemo;

import java.util.Arrays;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        boolean metricsRequested = Arrays.asList(args)
                .contains("--enable-metrics");

        if (metricsRequested) {
            application.setAdditionalProfiles("metrics");
        }

        application.run(args);
    }
}
~~~

This example parses the flag simply before calling `run`. In real systems, design clear parameter names and consider using Spring Boot's built-in configuration mechanisms instead of building a complex custom CLI parser. The crucial requirement is that the decision to add the profile occurs **before** startup begins.

Run:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev --enable-metrics
~~~

In this illustration, `--enable-metrics` is a flag checked by launcher code. If the goal is merely conditionally toggling a feature, a boolean property like `app.metrics.enabled` can be simpler than creating a new profile.

## 12. Distinguishing `spring.profiles.include`, profile groups, and Java APIs

Not every profile-addition need requires modifying Java code.

### 12.1. `spring.profiles.include`

In common `application.yml`:

~~~yaml
spring:
  profiles:
    include:
      - common
      - metrics
~~~

The `common` and `metrics` profiles are added in addition to the list from `spring.profiles.active`. According to Spring Boot documentation, included profiles are added before profiles activated via `spring.profiles.active`.

This mechanism fits when the auxiliary profile set is a configuration decision manageable through files.

### 12.2. Profile groups

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

When enabling `production`, Spring Boot also activates `proddb` and `prodmq` via the group. This lets operators choose one representative profile instead of remembering multiple names.

### 12.3. `setAdditionalProfiles(...)`

~~~java
application.setAdditionalProfiles("metrics");
~~~

This is a decision placed directly at bootstrap in Java. It fits when a launcher, integration library, or application-level choice must ensure a profile is always added for the run.

All three mechanisms can contribute to active profiles simultaneously. Do not assume ordering across different mechanisms solely from profile names; understand the specific profile conditions and configuration load order.

**Rule for profile-specific files:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and profile group declarations may only be placed in documents without profile conditions. Never place those properties inside a document with `spring.config.activate.on-profile` or `application-prod.yml` to circularly activate additional profiles.

## 13. Comparing `setDefaultProfiles` with `setAdditionalProfiles`

The name “default profile” can easily be confused with “additional profile.”

Suppose there is no active profile yet:

~~~java
ConfigurableEnvironment environment = new StandardEnvironment();

environment.setDefaultProfiles("local");
System.out.println(Arrays.toString(environment.getDefaultProfiles()));
// [local]
~~~

With this Environment, when there is no active profile, configuration using the default profile can apply per Spring's policy. However, if `prod` is subsequently enabled:

~~~java
environment.addActiveProfile("prod");
~~~

`local` no longer acts as the fallback active profile when evaluating profile conditions. It remains in the object's *default profiles* list, yet applies only when no active profiles exist.

Conversely, `setAdditionalProfiles("metrics")` adds an active profile via `SpringApplication` bootstrap even when the environment already has `dev` or `prod`.

| API | When does it apply? | Replace or add? |
| --- | --- | --- |
| `setDefaultProfiles("local")` | Sets the Environment's fallback set | Replaces default set |
| `setActiveProfiles("prod")` | Sets the Environment's active set | Replaces active set |
| `addActiveProfile("metrics")` | Adds to Environment | Adds active |
| `SpringApplication.setAdditionalProfiles("metrics")` | Adds before Spring Boot runs | Adds profile to application |

## 14. Inspecting active profiles and final configuration

In learning or diagnostic settings, print the active profiles set and relevant properties:

~~~java
@Bean
ApplicationRunner inspectEnvironment(Environment environment) {
    return args -> {
        System.out.println("Active profiles: "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("app.message: "
                + environment.getProperty("app.message"));

        System.out.println("app.monitoring.enabled: "
                + environment.getProperty("app.monitoring.enabled", Boolean.class));
    };
}
~~~

Place this inside a `@Configuration` or `@SpringBootApplication` class, with imports:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
~~~

If you want to check profiles via logical conditions, Spring Framework provides `Profiles`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean metricsEnabled = environment.acceptsProfiles(Profiles.of("metrics"));
boolean devWithMetrics =
        environment.acceptsProfiles(Profiles.of("dev & metrics"));
~~~

The result is evaluated against the current active profiles set. This is a condition check, not an operation that activates additional profiles.

### Note on startup logs

Spring Boot typically displays active profile information in startup messages. You can use those logs for a quick check, yet never rely on log formatting or profile string ordering as a business contract. For application logic, use `Environment` and bound configuration.

### Profile-specific configuration takes effect only when loaded

If an added profile is `metrics` and `application-metrics.yml` exists, that file is evaluated in Config Data when the profile is active **during the configuration loading phase**. If you only change active profiles in Java code after startup, `getActiveProfiles()` may change while skipped files do not automatically reload.

## 15. Common mistakes

### 15.1. Calling `SpringApplication.run(...)` too early

There is no `SpringApplication` instance to customize before calling static `run`:

~~~java
// Once this line runs, startup has already happened.
SpringApplication.run(ProfileDemoApplication.class, args);
~~~

To add a profile:

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);
application.setAdditionalProfiles("metrics");
application.run(args);
~~~

### 15.2. Replacing existing profiles by mistaking `setActiveProfiles`

~~~java
environment.setActiveProfiles("metrics");
~~~

This command replaces the active list of **that Environment itself**. If you want to keep existing `dev` or `prod`, use:

~~~java
environment.addActiveProfile("metrics");
~~~

Or, with Spring Boot, use `SpringApplication.setAdditionalProfiles("metrics")` before running.

### 15.3. Modifying an Environment that does not belong to the application

~~~java
ConfigurableEnvironment independent = new StandardEnvironment();
independent.addActiveProfile("metrics");

// This creates and modifies a separate object.
// It has not modified the Environment of another SpringApplication.
~~~

Only the Environment actually used during bootstrap affects that application's beans and Config Data. If supplying a custom Environment, attach it with `SpringApplication.setEnvironment(...)` before `run` and pick the appropriate Environment type.

### 15.4. Adding profiles after the context has already been created

Calling `environment.addActiveProfile(...)` from an `ApplicationRunner` or an already-initialized bean **does not re-trigger** `@Profile` beans and does not reload YAML. Choose a point prior to bootstrap.

### 15.5. Profile name mismatch with filename

~~~text
Active profile:    production
Existing file:     application-prod.yml
~~~

`production` and `prod` are two different names. To use `application-prod.yml`, activate `prod` explicitly or rename the file to `application-production.yml`.

### 15.6. Value mismatch due to source precedence

An `application-dev.yml` file might contain `app.message=local`, while CLI `--app.message=remote` normally takes higher precedence. In that case the profile is working properly; the **final value** simply comes from another source.

Do not use the contents of a single file alone to conclude a profile was not activated. Check `getActiveProfiles()` first, then check the relevant property sources.

### 15.7. Multiple beans of the same type when enabling multiple profiles

If `@Profile("dev")` and `@Profile("prod")` both create a `NotificationSender` bean, enabling both `dev` and `prod` can yield multiple injection candidates. Establish deployment profile sets cleanly, or use bean-selection mechanisms like `@Primary`/`@Qualifier` when genuinely appropriate.

### 15.8. Using profiles to represent every feature setting

Profiles are useful for bean conditions and configuration groups. Yet independently toggleable flags like `app.feature.enabled` or thresholds like `app.retry-count` are usually simpler when expressed as typed configuration properties instead of adding dozens of distinct profile names.

## 16. Practice exercises

### Exercise 1 — Adding a profile via `SpringApplication`

Prepare `application.yml` and `application-metrics.yml` with:

~~~yaml
# application.yml
app:
  monitoring:
    enabled: false
~~~

~~~yaml
# application-metrics.yml
app:
  monitoring:
    enabled: true
~~~

Add:

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);
application.setAdditionalProfiles("metrics");
application.run(args);
~~~

Use `Environment` to read `app.monitoring.enabled`. The expected value is `true`, assuming no higher-precedence source overrides it.

### Exercise 2 — Checking CLI profile alongside additional profile

Run the JAR with:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev
~~~

Code still has `setAdditionalProfiles("metrics")`. Print `getActiveProfiles()` and explain why both `dev` and `metrics` appear even though the CLI command mentioned only `dev`.

### Exercise 3 — Adding and replacing with `ConfigurableEnvironment`

~~~java
ConfigurableEnvironment environment = new StandardEnvironment();
environment.setActiveProfiles("dev");
environment.addActiveProfile("metrics");
// Predict getActiveProfiles().

environment.setActiveProfiles("prod");
// Predict getActiveProfiles() again.
~~~

Answer: first set contains `dev` and `metrics`; second set contains only `prod`.

### Exercise 4 — Investigating adding a profile too late

Try calling `environment.addActiveProfile("metrics")` inside an `ApplicationRunner` without adding the profile at bootstrap. Afterward, read `getActiveProfiles()` and `app.monitoring.enabled`. Explain why the profile name list may have changed yet values from `application-metrics.yml` were not automatically reloaded.

### Exercise 5 — Testing profile-based configuration and beans

Create two beans implementing the same interface with `@Profile("dev")` and `@Profile("prod")`. Run each profile individually; then enable both to observe the difference when Spring needs to inject a single bean.

### Exercise 6 — Default profile set

With a standalone `ConfigurableEnvironment`, call `setDefaultProfiles("local")` and then `getDefaultProfiles()`. Next call `addActiveProfile("prod")`. Explain when the default profile is used.

## 17. Key takeaways

- `SpringApplication.setAdditionalProfiles(...)` is the direct way to **add profiles in Java before Spring Boot starts**.
- `ConfigurableEnvironment.addActiveProfile(...)` adds an active profile on the actual Environment object; `setActiveProfiles(...)` replaces the Environment's active profiles set.
- `setDefaultProfiles(...)` controls the fallback set when there are no active profiles, differing from adding active profiles.
- Profile activation timing must be early enough to affect loading `application-<profile>.yml`, profile-specific YAML documents, and evaluating `@Profile` for beans.
- Modifying active profiles after context initialization does not automatically rerun Config Data loading or bean registration.
- CLI arguments, environment variables, config data, and additional profiles can all interact. Check `Environment.getActiveProfiles()` for actual profiles; read effective values to understand overrides.
- When you only need to add profiles for a standard Spring Boot application, prefer `SpringApplication.setAdditionalProfiles(...)` because the API expresses clear intent and avoids replacing the Environment type manually.

## References

- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework 6.1 — ConfigurableEnvironment API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)