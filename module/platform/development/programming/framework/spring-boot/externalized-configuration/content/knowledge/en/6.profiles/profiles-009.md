# `@Profile`: Selecting Beans by Profile and Its Relationship with Configuration Files

## 1. The problem: the same application needs different components

A Spring Boot application can run on a developer's machine, in a test environment, in staging, and in production. These environments usually share **the same source code**, yet have two kinds of differences:

1. **Different configuration values**: API addresses, logging levels, HTTP ports, timeouts, or service names.
2. **Different Java components to instantiate**: on a developer machine, use a console notification sender; in production, use a sender targeting an external system.

Spring Boot provides two related mechanisms that handle two separate responsibilities:

- **Profiles and Config Data**: select appropriate configuration files or documents, such as `application-dev.yaml` and `application-prod.yaml`. Values from those sources feed into `Environment`.
- **Spring Framework's `@Profile`**: set a condition to **register beans** into the `ApplicationContext` depending on which profiles are currently effective.

If you confuse the two mechanisms, you can end up in a situation where `application-prod.yaml` has been read yet the production bean is missing; or the production bean was created yet still receives values from another higher-precedence configuration source.

This article explains the intersection: **Spring determines active profiles → loads matching configuration → evaluates `@Profile` → creates eligible beans and injects dependencies**.

## 2. What is a profile in Spring?

A profile is a **logical environment label** that Spring uses to enable or disable groups of beans or configuration. Common names include:

- `dev`: development.
- `test`: testing.
- `staging`: pre-deployment verification environment.
- `prod`: production.
- `cloud`, `local`: infrastructure or runtime characteristics.

These are **application-chosen names**, not a fixed list enforced by Spring Boot. You can pick names suited to your system; what matters is consistency across configuration, Java code, and launch commands.

An application can activate **multiple profiles simultaneously**. For example, `prod,cloud` means both `prod` and `cloud` are active; it does not create a single combined profile named `prod,cloud`.

The profile mechanism originates from `Environment`. Spring Framework provides:

~~~java
Environment environment;

String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
~~~

`getActiveProfiles()` reports explicitly activated profiles. `getDefaultProfiles()` provides the fallback default profile group used when no profile is explicitly activated. By Spring's default, the default profile name is `default`.

**A profile is not synonymous with a server or a file.** One profile can select multiple beans and multiple configuration sources. Conversely, multiple profiles can be active in the same run.

## 3. What does `@Profile` actually do?

`@Profile` is a Spring Framework annotation:

~~~java
import org.springframework.context.annotation.Profile;
~~~

It sets a **condition for registering components into the Spring container**. When configuration is processed, Spring evaluates this condition against the effective profiles in `Environment`:

- Condition matches → the bean or configuration is considered for registration.
- Condition does not match → that bean definition is not registered from that configuration.
- If another component requires injecting that absent bean → context startup can fail due to a missing dependency.

A crucial distinction:

> `@Profile` does not simply change the return value of an existing bean; it decides whether **the bean definition is registered and instantiated** in the corresponding context.

`@Profile` commonly appears on:

- `@Component`, `@Service`, `@Repository`, or similar stereotype classes.
- `@Configuration` classes so the condition applies to the entire configuration inside.
- `@Bean` methods to condition a single specific bean.

It is not a tool for setting property values, nor does it automatically load YAML files. That job belongs to `Environment`, Config Data, and Spring Boot's configuration binding mechanism.

## 4. First example: creating two beans for `dev` and `prod`

Suppose the application needs a notification gateway. For simplicity, each implementation returns a description of the channel used; the example makes no network calls.

Define a Java interface:

~~~java
package com.example.demo.notice;

public interface NoticeChannel {
    String describe();
}
~~~

Configuration with two beans:

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NoticeChannelConfiguration {

    @Bean
    @Profile("dev")
    NoticeChannel localNoticeChannel() {
        return () -> "Sending notifications via console in dev environment";
    }

    @Bean
    @Profile("prod")
    NoticeChannel productionNoticeChannel() {
        return () -> "Sending notifications via production system";
    }
}
~~~

With profile `dev`, Spring registers `localNoticeChannel` and skips `productionNoticeChannel`. With profile `prod`, the reverse occurs.

A service using whichever bean exists:

~~~java
package com.example.demo.notice;

import org.springframework.stereotype.Service;

@Service
public class NoticeService {
    private final NoticeChannel channel;

    public NoticeService(NoticeChannel channel) {
        this.channel = channel;
    }

    public String currentChannel() {
        return channel.describe();
    }
}
~~~

Now launch:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

`NoticeService` receives the dev bean. When running:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

it receives the prod bean.

### Two scenarios to anticipate upfront

**No matching profile:** If no profile is activated, `default` takes effect by default. Both `@Profile("dev")` and `@Profile("prod")` evaluate to false. `NoticeService` requires a `NoticeChannel`, yet no matching bean exists. The context can fail to start due to an unsatisfied dependency.

**Both `dev` and `prod` enabled:** With `--spring.profiles.active=dev,prod`, **both** `NoticeChannel` beans are registered. The constructor `NoticeService(NoticeChannel)` will be ambiguous because two candidates of the same type exist, unless you specify selection via `@Qualifier`, `@Primary`, or mutually exclusive conditions.

This shows that `@Profile` is an independent selection condition **per bean**, not a switch guaranteeing the entire application has exactly one mode.

## 5. Using profile expressions to express conditions accurately

Beyond a single name, `@Profile` supports profile expressions.

### 5.1. Negation condition: `!prod`

~~~java
@Bean
@Profile("!prod")
NoticeChannel localNoticeChannel() {
    return () -> "Channel used outside production";
}

@Bean
@Profile("prod")
NoticeChannel productionNoticeChannel() {
    return () -> "Production channel";
}
~~~

`@Profile("!prod")` means **the `prod` profile is not active**. It matches when:

- `dev` is active and `prod` is not active.
- `test` or `staging` is active without `prod`.
- No profile is explicitly active and only `default` applies, because `prod` is still not active.

If `prod` is active, the `localNoticeChannel` bean is excluded. This style often fits better than a `dev`/`prod` pair when you want a fallback implementation for every non-production environment.

### 5.2. Multiple names in one annotation: OR condition

~~~java
@Bean
@Profile({"dev", "test"})
NoticeChannel developmentNoticeChannel() {
    return () -> "Channel for dev or test";
}
~~~

When using a name array like above, the bean is eligible if **at least one** expression/name matches. In other words, `dev` **or** `test` activates the bean.

### 5.3. AND, OR, and NOT operators

~~~java
@Bean
@Profile("prod & cloud")
NoticeChannel cloudProductionChannel() {
    return () -> "Channel for production running on cloud";
}
~~~

This condition matches only when **both** `prod` and `cloud` are present simultaneously.

~~~java
@Bean
@Profile("dev | test")
NoticeChannel sandboxChannel() {
    return () -> "Channel for dev or test";
}
~~~

Use `|` when either profile suffices; `&` when both are required; `!` for negation. For complex expressions, use parentheses to avoid ambiguity:

~~~java
@Profile("(prod & cloud) | staging")
~~~

Meaning: production on cloud **or** staging. Do not write expressions mixing `&` and `|` without explicit parentheses.

### 5.4. Class-level and method-level conditions

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("cloud")
class CloudConfig {

    @Bean
    @Profile("prod")
    NoticeChannel cloudNoticeChannel() {
        return () -> "Production channel on cloud";
    }
}
~~~

The configuration class is processed only when `cloud` matches. Inside it, the bean method also requires `prod`. As a result, the bean appears only when **both conditions are satisfied**.

Do not assume a method-level condition overrides the class-level condition. If the configuration class is not included in the context, beans inside it cannot be registered from that class.

## 6. How to activate profiles for the application

The `@Profile` mechanism relies on effective profiles in `Environment`. There are several ways to declare them.

### 6.1. Command-line arguments

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Multiple profiles:

~~~bash
java -jar app.jar --spring.profiles.active=prod,cloud
~~~

This is transparent for examples and test runs. `--key=value` command-line arguments typically hold high precedence among Spring Boot configuration sources.

### 6.2. Environment variables

On Unix-like shells:

~~~bash
export SPRING_PROFILES_ACTIVE=dev
java -jar app.jar
~~~

Or:

~~~bash
SPRING_PROFILES_ACTIVE=prod,cloud java -jar app.jar
~~~

Spring Boot maps the `SPRING_PROFILES_ACTIVE` environment variable to the `spring.profiles.active` property.

On Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar app.jar
~~~

If both an environment variable and `--spring.profiles.active=prod` are present, under default source ordering the command-line argument can override the environment variable value.

### 6.3. Java system property

~~~bash
java -Dspring.profiles.active=dev -jar app.jar
~~~

Note that `-D...` is a **JVM** option and normally precedes `-jar`; `--spring.profiles.active=...` is an application argument placed after `app.jar`.

### 6.4. Non-profile-specific `application.yaml`

You can set a default active profile for launching the application in a regular configuration document:

~~~yaml
spring:
  profiles:
    active: dev
~~~

However, packaging `active: dev` inside the common file may not reflect production deployment intent. Let the deployment environment choose profiles via an appropriate configuration mechanism.

**Important Spring Boot Config Data restriction:** `spring.profiles.active` and `spring.profiles.default` are valid only in **non-profile-specific documents**. Do not place them inside `application-prod.yaml` or inside a YAML document activated by `spring.config.activate.on-profile`. Those documents may not be used to decide active profiles themselves.

### 6.5. Setting via `SpringApplication`

~~~java
import org.springframework.boot.SpringApplication;

public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(DemoApplication.class);
        application.setAdditionalProfiles("local");
        application.run(args);
    }
}
~~~

`setAdditionalProfiles` adds profiles to the effective set. This is a programmatic option when startup behavior genuinely requires code-level control. For applications deployed across multiple environments, external declaration is usually more convenient because no recompilation is needed.

## 7. Relationship with `application-dev.yaml` and `application-prod.yaml`

Spring Boot does not use profiles solely to evaluate `@Profile`. It also uses profiles to select matching Config Data documents.

Suppose you have:

~~~text
src/main/resources/
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
~~~

Base file:

~~~yaml
# application.yaml
app:
  notice:
    title: "Notification"
    endpoint: "https://example.invalid"
    retry-count: 2
~~~

Dev file:

~~~yaml
# application-dev.yaml
app:
  notice:
    title: "Development notification"
    endpoint: "http://localhost:8089"
    retry-count: 1
~~~

Prod file:

~~~yaml
# application-prod.yaml
app:
  notice:
    title: "Production notification"
    endpoint: "https://notify.example.com"
    retry-count: 5
~~~

With:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Spring Boot normally loads the base configuration and then adds the `dev` profile document. Keys in `application-dev.yaml` can override matching keys in `application.yaml` under Config Data precedence rules.

With `--spring.profiles.active=prod`, `application-prod.yaml` is considered instead of the dev variant, and the effective values for the illustrative keys are:

| Property | With `dev` | With `prod` |
| --- | --- | --- |
| `app.notice.title` | `Development notification` | `Production notification` |
| `app.notice.endpoint` | `http://localhost:8089` | `https://notify.example.com` |
| `app.notice.retry-count` | `1` | `5` |

Actual values can still be overridden by environment variables, Java system properties, CLI arguments, or other higher-precedence sources. Profiles decide only **which documents get a chance to participate**; they do not guarantee a profile-specific file always beats every source.

### Clearly separating two questions

**“When `prod` is active, where does `app.notice.endpoint` come from?”**

That is a question about **configuration sources and precedence order**. Spring Boot resolves it via Config Data and `Environment`.

**“When `prod` is active, which `NoticeChannel` bean exists?”**

That is a question about **bean registration conditions**. Spring Framework evaluates `@Profile`.

Both mechanisms share active profiles as input, yet neither replaces the other.

## 8. Putting it together: `@Profile` and `@ConfigurationProperties`

Real-world designs often need **the right bean type** and **the right parameters for that bean**. You can let `@Profile` choose the implementation, and use `@ConfigurationProperties` to supply configuration values.

### 8.1. Define a typed properties class

~~~java
package com.example.demo.notice;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notice")
public record NoticeProperties(
        String title,
        URI endpoint,
        int retryCount) {
}
~~~

On the `@SpringBootApplication` class, enable configuration properties scanning:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.2. Create profile-specific beans and read values via properties

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NoticeConfiguration {

    @Bean
    @Profile("!prod")
    NoticeChannel localChannel(NoticeProperties properties) {
        return () -> "[LOCAL] " + properties.title()
                + " -> " + properties.endpoint();
    }

    @Bean
    @Profile("prod")
    NoticeChannel productionChannel(NoticeProperties properties) {
        return () -> "[PROD] " + properties.title()
                + " -> " + properties.endpoint();
    }
}
~~~

In this example:

- `@Profile("!prod")` and `@Profile("prod")` decide which bean is registered.
- `NoticeProperties` is bound from effective `app.notice.*` properties.
- `application-dev.yaml` and `application-prod.yaml` are value-providing sources among those loaded by Spring Boot.
- If an environment variable or CLI argument overrides `app.notice.title`, the selected bean receives the new effective value at creation time, rather than sticking to the raw profile file value.

For example:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.notice.title="Urgent notice"
~~~

The `productionChannel` bean is registered because `prod` is active; however, the received title is `Urgent notice` because the CLI argument overrides the property in the file.

**Special note:** `NoticeChannel.describe()` only returns an illustrative string. In a real system, implementations might use an HTTP client or message broker, requiring additional configuration and error handling. This example focuses on bean selection and configuration binding.

## 9. Using `@Profile` on classes instead of `@Bean`

You can place `@Profile` directly on component classes:

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class DevNoticeChannel implements NoticeChannel {
    @Override
    public String describe() {
        return "Notification for dev environment";
    }
}
~~~

~~~java
package com.example.demo.notice;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class ProdNoticeChannel implements NoticeChannel {
    @Override
    public String describe() {
        return "Notification for prod environment";
    }
}
~~~

Spring component scanning finds these classes, while `@Profile` determines whether they are registered as beans.

Choosing between the two approaches:

- **Place on `@Component` classes** when components are self-contained, manage their own dependencies cleanly, and fit component scanning.
- **Place on `@Bean` methods** when constructing the object requires configuration logic, comes from a third-party library, or you want bean creation centralized in one place.
- **Place on `@Configuration` classes** when an entire group of beans exists only in a specific environment.

Do not combine all three styles for the same object in real code; pick one clear registration approach to avoid creating unexpected duplicate beans.

## 10. `@Profile("default")` and when no profile is set

Spring Framework has a default profile named `default`. When **no profile is explicitly activated**, the default profile group is used to evaluate conditions.

Example:

~~~java
@Bean
@Profile("default")
NoticeChannel defaultChannel() {
    return () -> "Default channel";
}
~~~

When running normally without setting `spring.profiles.active`, that bean can be registered because `default` is in effect. However, if running with `spring.profiles.active=dev`, the default profile no longer serves in place of the active set; `@Profile("default")` does not automatically match just because Spring has a default concept.

You can specify default profiles via `spring.profiles.default` in a non-profile-specific document:

~~~properties
spring.profiles.default=local
~~~

Then, if no explicit active profile exists, `local` can act as the default profile. Spring Boot also supports `spring.profiles.default=none` to avoid activating the conventional default profile.

Compare the two options:

~~~java
@Profile("default")
~~~

means matching **only** the profile named `default`.

~~~java
@Profile("!prod")
~~~

means **`prod` is absent from the effective profile group**. The second condition is broader: it also matches `dev`, `test`, `staging`, and many other scenarios where `prod` is inactive.

If the goal is a fallback choice for every non-production environment, `!prod` usually expresses that intent better than `default`.

## 11. YAML documents activated by profile

Aside from splitting multiple `application-{profile}.yaml` files, Spring Boot supports **multiple documents in a single YAML file** using the `---` separator and the `spring.config.activate.on-profile` condition.

Example:

~~~yaml
# application.yaml — shared document
app:
  banner: "Demo Application"
  notice:
    retry-count: 2

---
spring:
  config:
    activate:
      on-profile: dev

app:
  banner: "Demo Application — DEV"
  notice:
    retry-count: 1

---
spring:
  config:
    activate:
      on-profile: prod

app:
  banner: "Demo Application — PROD"
  notice:
    retry-count: 5
~~~

When `dev` is active, the `on-profile: dev` document is activated. When `prod` is active, the `on-profile: prod` document is activated.

This condition can also use profile expressions, for example:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"
~~~

**Do not confuse these two annotations/settings:**

- `@Profile("prod")` is a registration condition for **Java beans**.
- `spring.config.activate.on-profile: prod` is an activation condition for **configuration documents**.

They share profile names, yet control different objects.

### What to avoid

Do not write:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: dev
~~~

A profile-activated document is not a valid place to set `spring.profiles.active`. Configuration controlling profile selection must reside in a source effective before profile-specific document activation, such as a common document or launch argument.

Similarly, in modern Spring Boot, do not use the legacy `spring.profiles` key inside a YAML document to activate that document. Use `spring.config.activate.on-profile`.

## 12. Multiple active profiles: two separate effects

The command:

~~~bash
java -jar app.jar --spring.profiles.active=dev,cloud
~~~

has two consequences:

1. Configuration sources for `dev` and `cloud` can be loaded; if keys overlap, Spring Boot applies Config Data ordering rules, where a profile declared later typically takes precedence when sources are at the same relevant tier.
2. Beans with `@Profile("dev")` or `@Profile("cloud")` can both be eligible; a bean with `@Profile("dev & cloud")` is also eligible.

Suppose:

~~~java
@Bean
@Profile("dev")
NoticeChannel devChannel() {
    return () -> "dev";
}

@Bean
@Profile("cloud")
NoticeChannel cloudChannel() {
    return () -> "cloud";
}
~~~

With both `dev` and `cloud` active, **both beans are registered**. The fact that `application-cloud.yaml` takes higher precedence than `application-dev.yaml` for the same property **does not eliminate** the `devChannel` bean.

This is a critical misconception: **configuration precedence is not `@Profile` bean precedence**.

If you want only one bean, design mutually exclusive conditions, or select the bean intentionally when injecting via `@Primary` or `@Qualifier`. Never rely on profile order for Spring to pick a “winning bean.”

### Profile groups

Spring Boot supports profile groups to activate multiple related profiles with a single name:

~~~yaml
spring:
  profiles:
    group:
      production:
        - "proddb"
        - "prodmq"
~~~

When `production` is activated, member profiles `proddb` and `prodmq` are also added to the effective profile set. Consequently, beans or documents conditioned on those names can be activated as well.

Profile group declarations belong to non-profile-specific configuration; do not place them inside `application-production.yaml` or a document active only when another profile matches.

Profile groups reduce the number of names typed at startup, yet do not automatically resolve ambiguities among beans of the same type.

## 13. Differences between `@Profile` and `@ConditionalOnProperty`

In Spring Boot, alongside `@Profile`, there are conditions based on **property values**:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
~~~

Comparison:

| Need | Usually reasonable choice |
| --- | --- |
| Use a different implementation in production | `@Profile("prod")` |
| Use a bean in dev or test | `@Profile({"dev", "test"})` |
| Enable a feature when `app.audit.enabled=true` | `@ConditionalOnProperty` |
| Create a bean only if another class/component exists | Other conditional annotations, e.g. `@ConditionalOnClass`, `@ConditionalOnBean` |
| Change only endpoint, timeout, or retry count | `@ConfigurationProperties` or `@Value`; a separate bean is not necessarily needed |

Example enabling a feature via a configuration value:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true")
AuditReporter auditReporter() {
    return new AuditReporter();
}
~~~

Assume `AuditReporter` is an application-defined class. This bean is created if `app.audit.enabled` has a matching value; the decision does not have to be tied to `dev` or `prod`.

When a feature can be toggled in any environment, property-based conditions are usually more flexible than creating extra profiles for every combination of options.

Conversely, when you want to describe **operational environment groups**, `@Profile` remains clear and expressive.

## 14. What happens when a bean does not exist?

This is a practical consequence to anticipate before placing `@Profile`.

### 14.1. Missing required bean

~~~java
@Service
class NoticeFacade {
    NoticeFacade(NoticeChannel channel) {
        // ...
    }
}
~~~

If `NoticeChannel` is created only with `@Profile("prod")` yet the application runs `dev`, Spring will not find a bean satisfying the required type. The context typically fails at startup with an unsatisfied dependency error.

Proper fixes depend on the design:

- Supply an appropriate implementation for the remaining environments.
- Move the consuming component itself under the same profile condition if the entire feature belongs to one environment.
- Define an optional dependency when the feature is genuinely optional, rather than ignoring accidental absence.
- Use a negated condition or an intentional fallback bean.

### 14.2. Multiple beans of the same type

When multiple conditions evaluate to true simultaneously, both beans can be created:

~~~java
@Bean
@Profile("dev")
NoticeChannel firstChannel() {
    return () -> "first";
}

@Bean
@Profile("cloud")
NoticeChannel secondChannel() {
    return () -> "second";
}
~~~

If both `dev` and `cloud` are active, injecting a single `NoticeChannel` may fail to identify a unique candidate. A fix can use `@Qualifier` at the injection point:

~~~java
@Service
class NoticeFacade {
    private final NoticeChannel channel;

    NoticeFacade(@Qualifier("firstChannel") NoticeChannel channel) {
        this.channel = channel;
    }
}
~~~

The snippet above requires importing `org.springframework.beans.factory.annotation.Qualifier`. The profile condition still decides whether `firstChannel` exists at all; `@Qualifier` only selects among already-registered beans.

If `firstChannel` is absent in prod, `@Qualifier` does not create it. Think carefully before using this as a default pattern across multiple environments.

## 15. Testing profile-specific beans

A direct way to test environment-specific configuration in Spring Boot is combining `@ActiveProfiles` with `@SpringBootTest`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("dev")
class NoticeProfileTest {

    @Autowired
    NoticeChannel channel;

    @Test
    void loadsDevChannel() {
        assertTrue(channel.describe().contains("dev"));
    }
}
~~~

`@ActiveProfiles("dev")` supplies the profile for the test run's context, making `@Profile("dev")` beans eligible. In the example above, assume the application configures a matching `dev` bean and no second `NoticeChannel` bean also matches.

You can write another test class with `@ActiveProfiles("prod")` to verify the production context.

A more helpful check than string matching alone is asserting **bean type, bean count, and bound configuration**. Example in a dev test:

~~~java
@Autowired
ApplicationContext context;

@Test
void registersOnlyOneNoticeChannel() {
    assertEquals(1, context.getBeansOfType(NoticeChannel.class).size());
}
~~~

This requires importing `org.springframework.context.ApplicationContext` and `org.junit.jupiter.api.Assertions.assertEquals`. This test confirms configuration does not accidentally create two beans of the same type under the selected profile.

### Test profiles and test configuration data

`application-test.yaml` can supply data when `test` is active:

~~~yaml
app:
  notice:
    title: "Test notification"
    endpoint: "http://localhost:9999"
    retry-count: 0
~~~

However, having this file in `src/test/resources` does not guarantee tests use the `test` profile; activate it with `@ActiveProfiles("test")` or an equivalent configuration.

For tests needing beans present only in production, watch out for external dependencies. Do not let an integration test accidentally call a production service just by enabling the `prod` profile. Mocking mechanisms or test configuration sources must still be designed explicitly.

## 16. Observing profiles and configuration sources at startup

In development environments, you can print **profile names** to see which group the context is running with:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ProfileLogger implements ApplicationRunner {
    private final Environment environment;

    ProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Active profiles = "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("Default profiles = "
                + Arrays.toString(environment.getDefaultProfiles()));
    }
}
~~~

If `getActiveProfiles()` returns an empty array, that **does not mean** no profiles are involved in condition evaluation. Default profiles may be in use at that point.

To test a specific condition, you can use:

~~~java
import org.springframework.core.env.Profiles;

boolean prod = environment.acceptsProfiles(Profiles.of("prod"));
boolean nonProd = environment.acceptsProfiles(Profiles.of("!prod"));
~~~

This method reflects how Spring evaluates profile expressions. It does not create beans itself; to see which beans were actually registered, inspect `ApplicationContext`.

Spring Boot also provides the **Condition Evaluation Report** for diagnosing auto-configuration and bean conditions. Run with `--debug` or use appropriate observability output to see why a condition applied or did not apply. Avoid printing all properties that might contain secrets.

If using Spring Boot Actuator, `/actuator/conditions` can help find why conditions matched/did not match; `/actuator/env` can help inspect property sources. These endpoints must be configured and secured appropriately because they can expose internal details.

## 17. Does changing profiles while the application is running automatically swap beans?

Normally **no**.

When Spring Boot starts, it prepares `Environment`, processes Config Data, evaluates registration conditions, and builds the `ApplicationContext`. `@Profile` is evaluated during context setup.

If an operator edits `application-prod.yaml` on disk after the application is already running, Spring Boot does not automatically reload every value. Likewise, changing active profiles on a live `Environment` **does not automatically remove or recreate** beans registered via `@Profile`.

To switch reliably from dev to prod deployment, normally **restart the application with the appropriate profile set**. Systems needing dynamic runtime changes to configuration or components require dedicated refresh and lifecycle management mechanisms; `@Profile` alone does not provide that.

## 18. Operational scenario: `prod` profile yet value from environment variable

Suppose the configuration is:

~~~yaml
# application.yaml
app:
  notice:
    endpoint: "https://fallback.invalid"
~~~

~~~yaml
# application-prod.yaml
app:
  notice:
    endpoint: "https://notify.internal"
~~~

Bean:

~~~java
@Bean
@Profile("prod")
NoticeChannel prodChannel(NoticeProperties properties) {
    return () -> properties.endpoint().toString();
}
~~~

Command:

~~~bash
APP_NOTICE_ENDPOINT=https://gateway.example.com \
java -jar app.jar --spring.profiles.active=prod
~~~

Result under Spring Boot's default source order:

- `prod` is the active profile, so `prodChannel` is registered.
- `application-prod.yaml` can be loaded thanks to profile `prod`.
- `APP_NOTICE_ENDPOINT` overrides `app.notice.endpoint` from the file, so the value received through `NoticeProperties` is `https://gateway.example.com`.

Looking solely at `application-prod.yaml`, you might wrongly conclude the production bean must use `https://notify.internal`. In reality, profiles and source precedence are **two distinct axes of decision**.

When diagnosing, ask in order:

1. Which profile set is currently effective?
2. Which beans' `@Profile` conditions match?
3. Which profile-specific configuration files were loaded?
4. Which higher-precedence source supplied the final property value?
5. At what point in the lifecycle did the component receive the value?

## 19. Common mistakes when using `@Profile`

### 19.1. Thinking a profile name automatically generates a matching bean

Activating `prod` does not automatically generate a `ProductionService` bean. A bean exists only if there is a definition via component scanning, `@Bean`, or another registration mechanism and all relevant conditions match.

### 19.2. Assuming a YAML file creates beans

`application-prod.yaml` supplies **configuration values** when `prod` is active. It does not instantiate a Java class or bean merely because a property mentions a class name.

### 19.3. Assuming only one profile can be active

Spring supports multiple simultaneous profiles. `@Profile("dev")` and `@Profile("cloud")` can both be true. This easily leads to multiple beans of the same type and dependency injection errors.

### 19.4. Putting `@Profile("default")` as if it meant “every environment except prod”

`default` is a profile with specific semantics when no explicit active profile exists. `!prod` is the condition negating the production profile.

### 19.5. Putting `spring.profiles.active` in `application-prod.yaml`

In the modern Config Data system, `spring.profiles.active` may not be declared in a configuration document dedicated to a single profile. Declare it in a common document or an appropriate early configuration source.

### 19.6. Using profiles for every feature flag

If you simply want to toggle a feature in both dev and production via `app.feature.enabled`, a property-based condition can be clearer than creating proliferated profiles like `dev-feature-on` and `prod-feature-off`.

### 19.7. Confusing `@Profile` with Spring Security roles

Names like `prod`, `admin`, or `test` in `@Profile` are **operational profiles**, not user roles in an authorization system. `@Profile("admin")` does not check the identity or permissions of an HTTP request sender.

### 19.8. Expecting profiles to change after the application has started

Beans are selected when creating the context. Editing environment variables or config files on disk afterward does not re-evaluate all `@Profile` conditions automatically.

### 19.9. Leaving a required configuration active only in `test` and missing in live runs

If an essential bean only has `@Profile("test")`, tests may pass while production fails to start due to a missing bean. Check all startup variants the application must support.

## 20. Practice exercises: predict beans and values

### Exercise 1 — selecting beans

~~~java
@Bean
@Profile("dev")
NoticeChannel dev() {
    return () -> "DEV";
}

@Bean
@Profile("prod")
NoticeChannel prod() {
    return () -> "PROD";
}
~~~

Predict the number of `NoticeChannel` beans in four cases:

| Active profiles | Bean count |
| --- | ---: |
| `dev` | 1 |
| `prod` | 1 |
| `dev,prod` | 2 |
| Unspecified (defaults to `default`) | 0 |

Explanation: each condition is evaluated independently. There is no “earlier profile wins” rule for bean registration.

### Exercise 2 — using negation

Replace the first definition with:

~~~java
@Bean
@Profile("!prod")
NoticeChannel nonProd() {
    return () -> "NON_PROD";
}
~~~

Keep the second definition `@Profile("prod")`. Predict:

- `dev` → `nonProd` bean.
- No active profile set → `nonProd` bean.
- `prod` → `prod` bean.
- `dev,prod` → `prod` bean because `!prod` is not satisfied.

### Exercise 3 — distinguishing beans from configuration data

~~~yaml
# application.yaml
app:
  mode: base
~~~

~~~yaml
# application-dev.yaml
app:
  mode: dev-file
~~~

~~~yaml
# application-prod.yaml
app:
  mode: prod-file
~~~

Bean:

~~~java
@Bean
@Profile("prod")
ModeReporter modeReporter(Environment environment) {
    return new ModeReporter(environment.getProperty("app.mode"));
}
~~~

Assume `ModeReporter` is a class accepting a string in its constructor.

Question: With `--spring.profiles.active=prod --app.mode=cli`, does the bean exist and what value does its property hold?

**Answer:** The bean exists because `prod` is active; `app.mode` is `cli` because the CLI argument takes higher precedence than the profile file. If you change only `--spring.profiles.active=dev` while keeping the bean definition, `modeReporter` is not registered.

### Exercise 4 — compound expressions

Condition:

~~~java
@Profile("(prod & cloud) | staging")
~~~

Determine whether it is true or false:

| Active profiles | Condition |
| --- | --- |
| `prod` | False |
| `cloud` | False |
| `prod,cloud` | True |
| `staging` | True |
| `dev,staging` | True |
| `prod,local` | False |

### Exercise 5 — testing

Create two independent Spring Boot tests: one using `@ActiveProfiles("dev")`, one using `@ActiveProfiles("prod")`. In each test, inject `ApplicationContext` and assert the count of `NoticeChannel`. Then add a test with both `dev` and `prod` to observe why mutually exclusive conditions or explicit bean selection are necessary.

This exercise reinforces distinguishing **bean creation** from **reading property values**.

## 21. Choosing the right tool

| Question being solved | Appropriate mechanism |
| --- | --- |
| Which logical environment set to run the app with? | `spring.profiles.active` or corresponding active profile configuration. |
| When dev/prod is active, which configuration documents load? | `application-{profile}.yaml`, `spring.config.activate.on-profile`, and Config Data. |
| When prod is active, which beans are registered? | `@Profile("prod")` on classes or `@Bean`. |
| What is the final value of a property? | `Environment`, `@ConfigurationProperties`, `PropertySource` order. |
| Toggle a feature via a flag independent of environment name? | `@ConditionalOnProperty`. |
| When multiple beans of the same type exist, which bean to inject? | `@Qualifier`, `@Primary`, or mutually exclusive conditions. |
| Swap implementations at runtime without restarting? | Dedicated lifecycle/refresh mechanism; `@Profile` does not do this automatically. |

## 22. Key takeaways

Profiles are a shared context used by Spring Framework and Spring Boot to select components and configuration sources. **`@Profile` controls bean registration**. **Config Data controls loading profile-specific configuration documents**. Both rely on effective profiles, yet neither replaces the other.

When analyzing environment bugs, separate three questions:

1. **Which profiles are active?**
2. **Which beans are eligible to appear in `ApplicationContext`?**
3. **Which source in `Environment` did the property received by the bean actually come from?**

Answering these three questions avoids common pitfalls: missing beans, multiple beans of the same type, and configuration values not matching the YAML file you just read.

## References

- [Spring Framework — Bean Definition Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles).
- [Spring Framework — @Profile](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Profile.html).
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).