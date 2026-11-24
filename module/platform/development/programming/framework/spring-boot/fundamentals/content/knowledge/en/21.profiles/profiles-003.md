# spring.profiles.active and default profile

Spring Boot often needs to run the same source code in multiple contexts: a developer's machine, a testing environment, staging, and production. Those contexts can use different databases, endpoints, logging, and implementations. If you had to modify source code for every deployment, the application would quickly become hard to control and error-prone.

**Spring Profiles** is a mechanism that lets you associate a group of configurations or beans with a profile name. The two most important concepts are:

- **Active profiles:** the profiles currently activated; in Spring Boot they can be configured using `spring.profiles.active`.
- **Default profiles:** the profile used when *there are no active profiles*; Spring's default name is `default`, and it can be changed via `spring.profiles.default`.

These are not two names for the same thing. When active profile `prod` exists, configuration dedicated to the default profile is not automatically activated alongside it. Conversely, if the active profiles list is empty, Spring uses the default profile to decide which configurations with `@Profile` match.

This lesson explains how to set, combine, and diagnose active/default profiles in Spring Boot, including configuration via YAML, properties, command line, environment variables, Java API, Config Data, and testing.

## 1. What problem do profiles solve?

Suppose an application sends order notifications. In the development environment, we want to use a mock implementation so we do not send real emails. In production, the application needs an implementation that sends through a real service.

Without profiles, code might have scattered environment conditionals:

~~~java
if ("prod".equals(environmentName)) {
    return new SmtpNotificationSender(...);
}

return new LoggingNotificationSender();
~~~

This approach forces many services to know environment names and couples business logic to deployment configuration.

With profiles, Spring can select the right bean when building the `ApplicationContext`:

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    NotificationSender developmentNotificationSender() {
        return new LoggingNotificationSender();
    }

    @Bean
    @Profile("prod")
    NotificationSender productionNotificationSender() {
        return new SmtpNotificationSender();
    }
}
~~~

`NotificationSender`, `LoggingNotificationSender`, and `SmtpNotificationSender` are illustrative application components.

The consuming service only needs the dependency:

~~~java
@Service
public class OrderService {

    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void confirmOrder(String customerId) {
        notificationSender.send(
                customerId,
                "Your order has been confirmed"
        );
    }
}
~~~

`OrderService` does not need to check profiles itself. Spring decides which bean definitions are registered when the context is built.

**Note:** if neither `dev` nor `prod` is enabled, neither of the two beans above is created from this configuration. If `OrderService` requires a `NotificationSender` and no other bean exists, the application will fail at startup. This is behavior that must be designed intentionally, rather than Spring picking an arbitrary implementation on its own.

## 2. What is an active profile?

An active profile is a profile that has been activated in Spring's `Environment`. For example:

~~~yaml
spring:
  profiles:
    active: dev
~~~

With this configuration, the `dev` profile is considered active. Beans or configuration classes with the `@Profile("dev")` condition can be applied, provided other registration conditions are also satisfied.

Multiple profiles can be enabled:

~~~yaml
spring:
  profiles:
    active: dev,observability
~~~

Or using YAML list syntax:

~~~yaml
spring:
  profiles:
    active:
      - dev
      - observability
~~~

Then the application simultaneously has both the `dev` and `observability` configuration groups.

### Profiles do not have to be deployment environment names

Many projects name profiles `dev`, `test`, `staging`, `prod`. However, Spring does not restrict you to just those four names. A profile can represent a capability group:

- `observability`: adds observability configuration.
- `cloud`: enables a group of cloud integration components.
- `mock-payment`: uses a simulated payment adapter.
- `local-db`: local database configuration.

However, avoid overusing profiles for every small feature flag. For capabilities that need to be toggled independently via configuration, `@ConditionalOnProperty` and `@ConfigurationProperties` can be easier to maintain.

### One application having multiple active profiles

For example:

~~~bash
java -jar store.jar --spring.profiles.active=prod,observability
~~~

Spring evaluates configurations for both `prod` and `observability`. If two profiles register two beans of the same type and injection does not disambiguate the choice, `NoUniqueBeanDefinitionException` may occur. Therefore, having multiple profiles does not mean their configurations always combine without conflict.

## 3. What is the default profile?

When no active profiles are declared, Spring still needs a context to evaluate profile-conditional configurations. It uses the **default profile**.

In Spring's default configuration, the default profile name is:

~~~text
default
~~~

If no profile is enabled:

~~~java
@Profile("default")
@Configuration
public class DefaultOnlyConfiguration {
    // ...
}
~~~

this configuration can be applied.

Conversely:

~~~java
@Profile("prod")
@Configuration
public class ProductionConfiguration {
    // ...
}
~~~

is not applied because `prod` is not active.

### Default does not mean dev

Spring uses the name `default` by default, **not `dev`**. Some applications explicitly configure their default profile to `local` or `dev`, but that is a project decision.

Nor should you assume that an environment with no active profile automatically runs the whole application with dev configuration. Only beans without profile conditions and beans whose conditions match the default profile are registered.

### What happens when an active profile is enabled?

Suppose an application has:

~~~java
@Bean
@Profile("default")
DataSource embeddedDataSource() {
    return createEmbeddedDataSource();
}

@Bean
@Profile("prod")
DataSource productionDataSource() {
    return createProductionDataSource();
}
~~~

If no active profile is enabled, the bean from `@Profile("default")` can be registered. If run with:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

the default bean will not be registered from that configuration, whereas the production bean can be registered.

The default profile is only a **fallback when active profiles are empty**, and is not automatically added to active profiles.

## 4. spring.profiles.default: changing the default profile name

Spring Boot lets you change the default profile:

~~~yaml
spring:
  profiles:
    default: local
~~~

With this configuration, if there are no active profiles, Spring treats `local` as the default profile. The condition:

~~~java
@Profile("local")
@Configuration
public class LocalConfiguration {
}
~~~

can match even though `environment.getActiveProfiles()` still returns an empty array.

### Local fallback configuration example

`application.yml`:

~~~yaml
spring:
  profiles:
    default: local
~~~

`application-local.yml`:

~~~yaml
app:
  payment:
    mode: simulation
    endpoint: http://localhost:9095
~~~

`application-prod.yml`:

~~~yaml
app:
  payment:
    mode: live
    endpoint: https://payments.example.internal
~~~

When starting without providing an active profile:

1. Spring reads the common configuration.
2. The active profiles list has no elements.
3. The default profile `local` is used for profile matching and loading matching Config Data.
4. `application-local.yml` can be loaded.

When starting with `prod`:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

Spring uses `prod` instead of the `local` fallback; `application-prod.yml` is applied according to Config Data rules.

### Can the default profile be disabled?

In Spring Boot's Config Data mechanism, you can configure:

~~~yaml
spring:
  profiles:
    default: none
~~~

`none` is a Spring Boot documented value to **avoid enabling a default profile used as an ordinary environment configuration**. When choosing this approach, design the application to require an explicit active profile or ensure that beans without profiles are sufficient to start.

Do not use `none` as the name of a business environment and expect it to behave like `dev` or `prod`.

## 5. How do active and default profiles differ?

A summary table:

| Criterion | Active profiles | Default profiles |
|---|---|---|
| Boot configuration | `spring.profiles.active` | `spring.profiles.default` |
| Purpose | Choose which profiles to run | Fallback when no active profile is chosen |
| Reading API | `Environment.getActiveProfiles()` | `Environment.getDefaultProfiles()` |
| When active profiles exist | Used for matching | Not automatically applied additionally |
| When active is empty | No active profiles | Used for matching |
| Common Spring value | No specific profile preset | `default` |
| Can be changed via command line? | Yes | Yes |
| Can relate to profile-specific files? | Yes | Yes, when used as fallback |

### Example 1: no profile configured

~~~text
spring.profiles.active:  [not set]
spring.profiles.default: [not set]
~~~

Then:

~~~text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["default"]
Profile used for matching -> default
~~~

### Example 2: changing default to local

~~~yaml
spring:
  profiles:
    default: local
~~~

When there is no active profile:

~~~text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["local"]
Profile used for matching -> local
~~~

### Example 3: setting both active and default

~~~yaml
spring:
  profiles:
    active: prod
    default: local
~~~

Then:

~~~text
getActiveProfiles()  -> ["prod"]
getDefaultProfiles() -> ["local"]
Profile used for matching -> prod
~~~

`local` remains the configured default value, but it only acts as a fallback if active profiles are absent.

## 6. Declaring in application.properties

YAML is not the only way. In `application.properties`:

~~~properties
spring.profiles.active=dev
~~~

Or multiple profiles:

~~~properties
spring.profiles.active=dev,observability
~~~

Default profile:

~~~properties
spring.profiles.default=local
~~~

To disable the default profile under Boot's mechanism:

~~~properties
spring.profiles.default=none
~~~

Spring Boot loads `application.properties` and `application.yml` via Config Data. If the same key is present in multiple property sources, the final value depends on the **precedence order** of those sources.

### No need for both properties and YAML to set the same value

A project should avoid scattering the same core configuration across multiple files unless overriding is intentional. When you need to know which profile is running, look for the **effective value in Environment**, rather than concluding solely from the file currently open.

## 7. Activating profiles from the command line

A common way when deploying an application is passing an option at launch:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

Multiple profiles:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod,observability
~~~

Changing the default profile without activating a specific profile:

~~~bash
java -jar store-service.jar --spring.profiles.default=local
~~~

### Command-line properties can override YAML

Suppose `application.yml` declares:

~~~yaml
spring:
  profiles:
    active: dev
~~~

But the launch command is:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

In standard Spring Boot configuration, command-line properties have higher precedence than Config Data from application files. The effective result is `prod`, not `dev`.

This is useful for building a single artifact and deploying it to multiple environments without modifying the JAR.

### Be careful with Java argument order

A JVM system property must be placed before `-jar`:

~~~bash
java -Dspring.profiles.active=prod -jar store-service.jar
~~~

Whereas a Spring Boot command-line argument is normally placed after the JAR name:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

The two syntaxes belong to two different mechanisms, though both can supply properties during startup.

## 8. Activating profiles with environment variables

In a Linux/macOS shell:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar store-service.jar
~~~

Or in a single command:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar store-service.jar
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar store-service.jar
~~~

The environment variable `SPRING_PROFILES_ACTIVE` is recognized by Spring Boot as corresponding to the `spring.profiles.active` property through Environment configuration mechanisms.

Commas can be used for multiple profiles:

~~~bash
export SPRING_PROFILES_ACTIVE=prod,observability
~~~

Changing the default:

~~~bash
export SPRING_PROFILES_DEFAULT=local
~~~

### Environment variables fit containers and CI/CD

In Docker, Kubernetes, or pipelines, profiles are usually selected at deployment time rather than hard-coded in source code.

Conceptual example for a container:

~~~yaml
services:
  store:
    image: example/store-service:latest
    environment:
      SPRING_PROFILES_ACTIVE: prod
~~~

This is a Compose-style snippet illustrating passing environment variables. Actual configuration depends on the deployment tool.

**Do not put credentials or secrets into profile names.** Profiles are environment/capability labels; secrets should be provided via a secret manager, config tree, or appropriate secure configuration source.

## 9. Precedence when multiple sources set spring.profiles.active

Environment contains multiple `PropertySource` entries. The same property can be declared in several places, for example:

~~~text
Command line:      --spring.profiles.active=prod
System property:   -Dspring.profiles.active=staging
Environment:       SPRING_PROFILES_ACTIVE=qa
application.yml:   spring.profiles.active=dev
Default property:  spring.profiles.active=local
~~~

In standard Boot configuration, command-line arguments have higher precedence than system properties, environment variables, and Config Data files; the higher-precedence value is used.

Important point: **`spring.profiles.active` from multiple sources is not automatically merged into a combined list**. The higher-precedence source determines the effective value for that property.

For example:

`application.yml`:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Command line:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

The result is not `dev,prod`. The typical result is `prod`.

If the goal is to **add profiles** rather than override the active list, look at `spring.profiles.include`, profile groups, or `SpringApplication.setAdditionalProfiles`.

### Notes on other sources

In test environments, `@TestPropertySource`, `@SpringBootTest(properties = ...)`, or `@ActiveProfiles` can alter how profiles are selected. Some environments also have config data imports, cloud config, and custom property sources. When in doubt, inspect the runtime Environment and loaded configuration sources.

## 10. Profile-specific application files: application-{profile}.yml

Spring Boot recognizes profile-specific configuration files, for example:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
├── application-staging.yml
└── application-prod.yml
~~~

Common file:

~~~yaml
spring:
  application:
    name: store-service

app:
  payment:
    timeout: 3s
  catalog:
    cache-enabled: false
~~~

Development file:

~~~yaml
app:
  payment:
    endpoint: http://localhost:9090
  catalog:
    cache-enabled: false
~~~

Production file:

~~~yaml
app:
  payment:
    endpoint: https://payments.example.internal
    timeout: 8s
  catalog:
    cache-enabled: true
~~~

When the `prod` profile is active, Spring Boot can load `application-prod.yml` alongside the common configuration. Profile-specific values can override corresponding values in the common file according to Config Data rules.

With the example:

~~~text
app.payment.timeout -> 8s
app.catalog.cache-enabled -> true
app.payment.endpoint -> https://payments.example.internal
~~~

### Files must be in locations searched by Spring Boot

If you place `application-prod.yml` in an arbitrary directory that Boot does not search, the file will not be loaded merely because its name ends in `prod`. Default locations and properties such as `spring.config.location`, `spring.config.additional-location`, or `spring.config.import` determine where Config Data is loaded from.

### Not every profile needs a file

A profile can be used solely to select beans with `@Profile` without having an `application-{profile}.yml` file. Conversely, a profile-specific file can change properties without the application having any `@Profile` beans.

A profile is a shared label for both mechanisms, though both do not have to exist at the same time.

## 11. Default profile and application-default.yml

Because Spring has a default profile named `default`, the file:

~~~text
application-default.yml
~~~

can be loaded when there are no active profiles and the default profile remains `default`.

For example:

~~~yaml
app:
  mail:
    sender: logging
  payment:
    mode: simulation
~~~

If running without active profiles, these values can be used according to precedence.

If you change the default profile:

~~~yaml
spring:
  profiles:
    default: local
~~~

then `application-local.yml` becomes the matching profile-specific file for fallback, and you should not assume `application-default.yml` is still loaded as before.

### Should application-default.yml be used for production?

Normally **no**. If an application is launched without explicit environment configuration and defaults to connecting to production systems, a test run could cause real side effects.

A project should choose a clear policy:

- Without an active profile, run only with local-safe defaults.
- Or require the application to be given a profile/configuration at deployment, failing fast if missing.
- Never use a production environment as an uncontrolled fallback.

## 12. Multiple active profiles and override order

You can activate:

~~~properties
spring.profiles.active=dev,observability
~~~

When multiple profile-specific files contain the same key, **profile order and Config Data precedence rules** can change the final value.

For example:

`application-dev.yml`:

~~~yaml
app:
  diagnostics:
    level: basic
~~~

`application-observability.yml`:

~~~yaml
app:
  diagnostics:
    level: detailed
~~~

For standard locations at the same precedence level, in modern Spring Boot versions, configuration from a profile processed later can override earlier configuration; the profile list typically uses a *last wins* rule for profile-specific property values. However, in real-world scenarios there are also location groups, imports, environment property sources, and other rules.

Therefore:

- Avoid letting multiple independent profiles decide the same critical property.
- When conflicts occur, read the effective value from Environment.
- Do not use profile ordering as a hard-to-observe business routing mechanism.
- If two profiles are mutually exclusive in intent, avoid activating them together or validate startup conditions.

### Two profiles can register two beans of the same type

~~~java
@Bean
@Profile("dev")
PaymentGateway devGateway() {
    return new FakePaymentGateway();
}

@Bean
@Profile("staging")
PaymentGateway stagingGateway() {
    return new SandboxPaymentGateway();
}
~~~

If both `dev` and `staging` are active, both beans can be registered. A consumer injecting a single `PaymentGateway` may encounter ambiguity without an appropriate `@Primary` or `@Qualifier`.

Do not assume a later profile automatically "overrides" an earlier bean like properties do. **Property overriding and bean registration are two different mechanisms.**

## 13. @Profile on @Configuration and @Bean

`@Profile` is part of Spring Framework:

~~~java
org.springframework.context.annotation.Profile
~~~

Placed on a class:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RealPaymentGateway();
    }

    @Bean
    PaymentAuditPublisher paymentAuditPublisher() {
        return new PaymentAuditPublisher();
    }
}
~~~

If `prod` does not match, the configuration class is skipped during processing, and the bean definitions provided by this class are not registered either.

Placed on a method:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway realPaymentGateway() {
        return new RealPaymentGateway();
    }
}
~~~

Each bean method has an independent condition.

### What about beans without @Profile?

~~~java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
~~~

If not excluded by another condition and the configuration class is processed, a bean without `@Profile` can be registered in every environment. `@Profile` is not required on all beans.

### @Profile only takes effect for Spring-managed beans

~~~java
RealPaymentGateway gateway = new RealPaymentGateway();
~~~

An object instantiated directly with `new` does not have `@Profile` applied by Spring. The profile annotation is a bean/configuration registration condition in the container, not a switch for arbitrary Java objects.

## 14. How does @Profile("default") work?

Example:

~~~java
@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {

    @Bean
    @Profile("default")
    StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("prod")
    StorageClient productionStorageClient() {
        return new CloudStorageClient();
    }
}
~~~

Case A: no active profile and default profile is `default`. The local bean can be registered.

Case B: active profile is `prod`. The production bean can be registered; the default bean does not come along automatically.

Case C: default profile was changed to `local` and there is no active profile. `@Profile("default")` is no longer a matching fallback; to get the local fallback, use `@Profile("local")`.

Case D: active profile is `test`, but there is no `StorageClient` bean for `test`. The default bean does not automatically run just because test lacks an implementation.

Thus, `@Profile("default")` is a **specific profile condition**, not "pick this bean if every other bean is absent". If you need a fallback bean based on the absence of another bean, `@ConditionalOnMissingBean` in appropriate auto-configuration has different semantics and must consider bean registration order.

## 15. Profile expressions: combining and negating

`@Profile` supports profile expressions in modern Spring Framework. For example:

~~~java
@Configuration
@Profile("prod & !test")
public class ProductionOnlyConfiguration {
}
~~~

Meaning: profile `prod` is selected and profile `test` is not selected.

Another condition:

~~~java
@Profile("dev | staging")
@Configuration
public class NonProductionConfiguration {
}
~~~

Meaning: `dev` or `staging` matches.

Negation:

~~~java
@Profile("!prod")
@Configuration
public class NotProductionConfiguration {
}
~~~

This configuration can match when `prod` is not active, including in a new environment not anticipated by the development team. Therefore, `!prod` does not mean "local only".

### Choosing clear expressions

If you want strictly dev and test, use:

~~~java
@Profile("dev | test")
~~~

instead of:

~~~java
@Profile("!prod")
~~~

because the system may have other profiles like `staging`, `benchmark`, or `disaster-recovery`.

### Multiple values in the annotation

~~~java
@Profile({"dev", "test"})
~~~

expresses an OR condition among the declared values. When expressions get complex, use a single clear expression instead of combining multiple strings whose logical intent is hard to read.

## 16. Multi-document configuration in application.yml

In addition to `application-{profile}.yml` files, Spring Boot supports multiple documents in a single YAML file separated by `---`.

Example:

~~~yaml
app:
  payment:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  payment:
    endpoint: http://localhost:9090

---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    endpoint: https://payments.example.internal
    timeout: 8s
~~~

The first document holds common configuration. The second document is used only when the `on-profile: dev` expression matches. The third document is used only with `prod`.

### spring.config.activate.on-profile does not activate a profile

Configuration:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

**does not tell Spring to switch to the prod profile**. It means: "only use this document when the prod profile already matches according to Environment."

To choose an active profile, use `spring.profiles.active` in a valid location or a startup configuration source such as the command line.

### Multi-document .properties

In Boot versions that support multi-document properties, you can use the appropriate marker for that format, which differs from YAML's `---`. If a project uses properties instead of YAML, check the syntax for your Boot version and avoid copying YAML syntax directly into `.properties` files.

## 17. Do not put spring.profiles.active in a profile-specific document

This is an important restriction of the **Config Data** mechanism from Spring Boot 2.4 onward:

Profile-selecting properties such as `spring.profiles.active` and `spring.profiles.default` may only be declared in **non-profile-specific documents**. Do not put them in profile-specific files or documents activated by `spring.config.activate.on-profile`.

**Invalid** example in `application-prod.yml`:

~~~yaml
spring:
  profiles:
    active: metrics
~~~

`application-prod.yml` is only loaded once the prod profile already matches. If it tried to decide active profiles, profile selection could easily become a circular dependency, so Boot disallows this declaration.

**Invalid** example in multi-document YAML:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: metrics
~~~

The document already depends on the `prod` profile yet tries to set the active profiles list.

### The right way

Place the active profile in a shared document before the profile-activated sections:

~~~yaml
spring:
  profiles:
    active: prod

---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    endpoint: https://payments.example.internal
~~~

In real deployment environments, it is usually better **not to hard-code prod in source** and instead pass `--spring.profiles.active=prod` or `SPRING_PROFILES_ACTIVE=prod`.

### Similar restriction for profile include and group

Properties such as `spring.profiles.include` and `spring.profiles.group` must also reside in valid locations under Config Data rules; do not put them in profile-specific documents or profile-activated documents.

If the application reports an invalid profile property error, check **which document declared the property**, not just the key name and value.

## 18. spring.profiles.include: adding profiles

`spring.profiles.include` is used to **add** profiles to the set of profiles to activate. Example:

~~~yaml
spring:
  profiles:
    include:
      - common
      - observability
~~~

The application can run with:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

and still include the `common` and `observability` profiles according to Spring Boot's profile processing rules.

`include` differs from `active` in that its purpose is adding profiles, rather than replacing the active list value from a higher-precedence property source.

### Do not put include in application-prod.yml

Example invalid under the modern Config Data mechanism:

~~~yaml
# application-prod.yml
spring:
  profiles:
    include: observability
~~~

If you only want the `prod` profile to activate additional appropriate groups, consider a **profile group** defined in a non-profile-specific document.

### Include also needs a clear purpose

If multiple modules/libraries add profiles on their own without a unified design, the final active profiles can become hard to predict. Profiles should be a documented configuration contract, not a hidden side effect in an unrelated module.

## 19. spring.profiles.group: expanding one profile into a group

Profile groups allow a single profile name to represent multiple member profiles.

Example in `application.yml` (common document):

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-security
        - observability
~~~

When activating:

~~~bash
java -jar store.jar --spring.profiles.active=production
~~~

Spring Boot can expand the group so that the `prod-database`, `prod-security`, and `observability` profiles all operate together.

### Why are groups useful?

If an environment needs three profiles enabled, operators do not have to remember a long command:

~~~bash
java -jar store.jar --spring.profiles.active=prod-database,prod-security,observability
~~~

They only need:

~~~bash
java -jar store.jar --spring.profiles.active=production
~~~

Groups help describe deployment configuration more meaningfully.

### Groups are not an authorization mechanism

Naming a profile `prod-security` does not automatically enable security measures if the corresponding beans and properties are not defined. Profile groups are a mechanism for activating a group of profiles, not a tool for managing policies or secrets.

### Put profile groups in a common document

Do not put group definitions in `application-production.yml`, because doing so depends on a document used only after the profile is already activated. Define groups in non-profile-specific configuration.

## 20. SpringApplication.setAdditionalProfiles in Java

Besides properties, you can add profiles via code before calling `run`:

~~~java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StoreApplication.class);

        app.setAdditionalProfiles("observability");
        app.run(args);
    }
}
~~~

`setAdditionalProfiles` adds profiles for that application run. It is useful when a library or launcher needs to add a configuration group.

However, for ordinary deployed applications, let the runtime environment decide `dev` or `prod`. Hard-coding active profiles in source code makes it harder to use the same JAR consistently across multiple environments.

### SpringApplicationBuilder

~~~java
new SpringApplicationBuilder(StoreApplication.class)
        .profiles("dev")
        .run(args);
~~~

`SpringApplicationBuilder` lets you configure fluently before running. This is an option when the application needs launcher control or builds a context hierarchy.

### Do not change profiles after context refresh and expect beans to swap

If the context has already created beans for `dev`, calling to change active profiles in `Environment` afterward does not automatically:

- Remove already-created dev beans.
- Create missing prod beans.
- Reload all of `application-prod.yml`.
- Re-evaluate all `@Profile` and `@Conditional` annotations.

Profiles are primarily a **configuration decision during bootstrap/bean registration**. Changing things while running requires a dedicated architecture, not just modifying the active profiles array.

## 21. Using Environment to inspect effective profiles

You can inject `Environment`:

~~~java
@Component
public class ProfileReporter implements ApplicationRunner {

    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active: " +
                Arrays.toString(environment.getActiveProfiles())
        );

        System.out.println(
                "Default: " +
                Arrays.toString(environment.getDefaultProfiles())
        );
    }
}
~~~

Import the corresponding Java and Spring classes such as `java.util.Arrays`, `Environment`, `ApplicationRunner`, and `Component`.

Typical output when no profile is enabled and default is local:

~~~text
Active: []
Default: [local]
~~~

When prod is enabled:

~~~text
Active: [prod]
Default: [local]
~~~

This output makes clear why `getDefaultProfiles()` still has a value, yet default is not used for matching while active profiles exist.

### Checking whether a profile matches

Spring has the `Profiles` API:

~~~java
boolean production =
        environment.acceptsProfiles(
                Profiles.of("prod")
        );
~~~

Or an expression:

~~~java
boolean nonProduction =
        environment.acceptsProfiles(
                Profiles.of("!prod")
        );
~~~

`acceptsProfiles(Profiles.of(...))` is the right API for modern Spring Framework. It checks a profile expression against the current Environment, including default profile semantics when there are no active profiles.

However, avoid scattering `environment.acceptsProfiles(...)` across business methods. If you are deciding which beans to register, prefer `@Profile` at the configuration layer.

## 22. How do profiles and @ConditionalOnProperty differ?

Sometimes a choice depends on the deployment environment; sometimes it is just a feature that can be toggled on or off.

Example selecting a database adapter by environment:

~~~java
@Bean
@Profile("dev")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}

@Bean
@Profile("prod")
PaymentGateway livePaymentGateway() {
    return new LivePaymentGateway();
}
~~~

Example enabling an independent feature:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
AuditPublisher auditPublisher() {
    return new AuditPublisher();
}
~~~

| Criterion | `@Profile` | `@ConditionalOnProperty` |
|---|---|---|
| Question | Which environment/profile group applies? | Does a specific property have a matching value? |
| Input | Active/default profiles | Environment property |
| Example | `prod`, `dev`, `observability` | `app.audit.enabled=true` |
| Suitable for | Context-based configuration clusters | Independent feature options |
| Risk of overuse | Too many profile combinations become hard to predict | Too many interdependent flags |

A practical rule of thumb: use profiles for **context or configuration combinations**, and typed properties/conditions for **independent options**.

## 23. Profiles do not replace production safeguards

A dangerous mistake is treating profiles as a security boundary:

~~~java
@Profile("prod")
public class RealPaymentGateway {
}
~~~

Using `@Profile("prod")` alone does not guarantee that all production access paths are blocked in other environments. If the wrong config source is chosen or an alternate bean exists, the application can still connect to the real endpoint.

Necessary safeguards include:

- Production credentials supplied only in the appropriate environment.
- Network policies restricting access to production services.
- Configuration validation at startup.
- Not putting secrets in committed source/YAML.
- Separating fake and real endpoints clearly.
- Testing missing-profile and wrong-active-profile scenarios.

Profiles are a **configuration mechanism**, not an independent security layer.

## 24. Activating profiles in tests with @ActiveProfiles

Spring Test supports `@ActiveProfiles` to select profiles for a test context.

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentServiceIntegrationTest {

    @Autowired
    PaymentGateway paymentGateway;

    @Test
    void usesTestGateway() {
        assertThat(paymentGateway)
                .isInstanceOf(FakePaymentGateway.class);
    }
}
~~~

The example assumes a `FakePaymentGateway` bean matches when the `test` profile is active and assertion dependencies have been added to the project.

### @ActiveProfiles differs from runtime configuration

`@ActiveProfiles` is a Spring Test annotation for preparing a test ApplicationContext. It is not the mechanism used to decide active profiles for a production application.

If a test does not declare a profile, the outcome still depends on configuration, test environment, and default profiles; do not assume every test automatically uses `test`.

### Using profile-specific properties for tests

`application-test.yml`:

~~~yaml
app:
  payment:
    endpoint: http://localhost:9999
  audit:
    enabled: false
~~~

Test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentIntegrationTest {
}
~~~

Spring Boot can load `application-test.yml` corresponding to the active test profile.

### Testing with multiple profiles

~~~java
@SpringBootTest
@ActiveProfiles({"test", "observability"})
class ObservabilityIntegrationTest {
}
~~~

If two profiles both register beans of the same type, tests can fail just like production. Control conflicts instead of assuming test annotations resolve all ambiguities.

## 25. Testing the default profile

To test fallback behavior, you need a context in which no active profiles are enabled. Simple example of bean configuration:

~~~java
@Configuration
public class FallbackConfiguration {

    @Bean
    @Profile("default")
    String fallbackMessage() {
        return "default-message";
    }

    @Bean
    @Profile("prod")
    String productionMessage() {
        return "production-message";
    }
}
~~~

In a test using `AnnotationConfigApplicationContext`:

~~~java
@Test
void usesDefaultProfileWhenNoActiveProfileExists() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                         FallbackConfiguration.class
                 )) {

        assertEquals(
                "default-message",
                context.getBean(String.class)
        );
    }
}
~~~

Because the context activates no profiles and Spring's default is `default`, the fallback bean can be selected.

Test with active prod:

~~~java
@Test
void usesProductionProfile() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

        context.getEnvironment().setActiveProfiles("prod");
        context.register(FallbackConfiguration.class);
        context.refresh();

        assertEquals(
                "production-message",
                context.getBean(String.class)
        );
    }
}
~~~

Here, `setActiveProfiles` is called **before `refresh()`**. If called after bean definitions have been processed, do not expect beans to be re-selected.

### Testing when the default profile is renamed

~~~java
@Test
void usesLocalAsConfiguredDefault() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

        context.getEnvironment().setDefaultProfiles("local");
        context.register(LocalOnlyConfiguration.class);
        context.refresh();

        assertNotNull(context.getBean(LocalService.class));
    }
}
~~~

The test assumes `LocalOnlyConfiguration` registers `LocalService` with `@Profile("local")`. This is a pure Spring Framework test of default profile semantics.

## 26. Common mistake: putting active in application-prod.yml

A common mistake is thinking "once inside the prod file, I will enable the metrics profile there too":

~~~yaml
# application-prod.yml
spring:
  profiles:
    active: metrics
~~~

The modern Config Data mechanism does not allow `spring.profiles.active` in a profile-specific file.

**Fix:** choose profiles in a non-profile-specific document or bootstrap source like the command line. If you need `prod` to enable an additional group of profiles, declare a profile group in a shared document:

~~~yaml
spring:
  profiles:
    group:
      prod:
        - observability
        - prod-security
~~~

Then activate `prod` via command line or environment variable.

## 27. Common mistake: confusing default profile with active profile

Suppose:

~~~yaml
spring:
  profiles:
    default: local
~~~

When there is no active profile, a developer might check:

~~~java
boolean hasLocal =
        Arrays.asList(environment.getActiveProfiles())
                .contains("local");
~~~

and get `false`.

This does not contradict `@Profile("local")` still matching. Because `getActiveProfiles()` returns the actual active list without injecting the default fallback into it.

If you want to check profile matching semantics, use:

~~~java
boolean localMatches =
        environment.acceptsProfiles(
                Profiles.of("local")
        );
~~~

If you want to display **actual active and configured default profiles**, read both `getActiveProfiles()` and `getDefaultProfiles()`.

## 28. Common mistake: profile-specific file not loaded

Symptom: ran:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

yet a property in `application-prod.yml` does not have the expected value.

Common causes:

1. The file is not in a location searched by the Config Data loader.
2. Wrong filename, e.g., `applications-prod.yml`.
3. The file uses an unsupported extension or format.
4. The property is overridden by a higher-precedence source.
5. Another YAML document has an `on-profile` condition that does not match.
6. `spring.config.location` replaced the default locations.
7. Config imports changed sources and precedence order.
8. The application does not actually have the `prod` profile active.
9. The property name differs from the key bound/read by code.

The troubleshooting path is to read the startup logs, actual active/default profiles, and applied property sources.

### Do not check only files in source

Applications run from a JAR or container image. Files in the repository may differ from packaged files, and external config can override them. Inspect the actual artifact and runtime environment when diagnosing.

## 29. Common mistake: @Profile has no effect

Example:

~~~java
@Service
@Profile("prod")
public class RealPaymentGateway implements PaymentGateway {
}
~~~

Yet the application does not create this bean even when prod is active.

Causes:

- The class is outside the component-scanning area.
- The configuration class is not imported.
- Another condition does not match.
- The bean was created manually with `new`, so Spring does not manage it.
- The project is running a different ApplicationContext than the one being inspected.
- The actual active profile was overridden by another configuration source.

It does not mean the `@Profile` annotation was "ignored" just because Spring did not see the class. Check the entire bean registration process.

### Two beans with the same name in two profiles

If different profiles register beans with the same name and both profiles are activated simultaneously, a bean definition conflict may occur depending on the application's overriding policy. If they use different names but the same type, injection ambiguity may occur.

Choose valid profile combinations, assign stable bean names, and use `@Qualifier` or clear configuration classes when needed.

## 30. Common mistake: changing Environment after startup

Example:

~~~java
environment.setActiveProfiles("prod");
~~~

If the call happens after the ApplicationContext has refreshed, do not expect dev beans to vanish and prod beans to appear automatically. Spring already evaluated `@Profile` and built the object graph earlier.

If the application genuinely needs to switch endpoints or behavior at runtime, consider:

- A strategy bean configured with properties that can be refreshed via an explicit mechanism.
- A factory/resolver choosing an implementation intentionally per request.
- Framework-supported refreshable configuration with a designed lifecycle.
- Redeploying/restarting the application when the environment context changes.

Do not turn profiles into dynamic feature toggles if the architecture does not support refresh.

## 31. Diagnosing profiles via logs and Actuator

At startup, Spring Boot typically logs active profiles or default fallbacks. A typical message when there is no active profile indicates Spring is using a default profile, such as `default`.

You can safely log it yourself:

~~~java
@Component
public class ProfileLogger implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ProfileLogger.class);

    private final Environment environment;

    public ProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info(
                "Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles())
        );

        log.info(
                "Default profiles: {}",
                Arrays.toString(environment.getDefaultProfiles())
        );
    }
}
~~~

Logging only profile names is suitable for most cases. Never log the entire Environment because property sources may contain passwords, tokens, or secrets.

If the application includes Spring Boot Actuator and admin endpoints are secured, the `env` endpoint can help inspect property sources; the `conditions` endpoint helps investigate why an auto-configuration matched or did not match. Exposing endpoints requires careful security control to avoid leaking internal configuration.

### Which property source determines the active profile?

The question to answer is: **Which configuration source with the highest precedence is supplying `spring.profiles.active` or `spring.profiles.default`?**

Do not just look at:

~~~yaml
spring:
  profiles:
    active: dev
~~~

in the repository and conclude the application runs in dev. An environment variable, command-line argument, or config import can make the effective value different.

## 32. End-to-end example: same JAR running locally and in production

A payment application has these files:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-prod.yml
~~~

Common configuration:

~~~yaml
spring:
  application:
    name: checkout-service
  profiles:
    default: local

app:
  payment:
    timeout: 3s
~~~

Local configuration:

~~~yaml
app:
  payment:
    mode: simulation
    endpoint: http://localhost:9090
~~~

Production configuration:

~~~yaml
app:
  payment:
    mode: live
    endpoint: https://payments.example.internal
    timeout: 8s
~~~

Typed configuration:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String mode;
    private URI endpoint;
    private Duration timeout = Duration.ofSeconds(3);

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Register `PaymentProperties` via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(PaymentProperties.class)` according to the application structure.

Service:

~~~java
@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI targetEndpoint() {
        return properties.getEndpoint();
    }
}
~~~

### Running locally without passing an active profile

~~~bash
java -jar checkout-service.jar
~~~

Because there is no active profile, the default `local` takes effect and `application-local.yml` is loaded according to Config Data rules.

### Running in production

~~~bash
java -jar checkout-service.jar --spring.profiles.active=prod
~~~

Because `prod` is active, the `local` fallback is not used. `application-prod.yml` supplies the appropriate endpoint and timeout.

### What if you forget to activate a profile when deploying?

The application may run the local fallback, leading to an unintended endpoint. If this is a major risk, production deployment needs checks for required environment variables, config validation, and a fail-fast policy instead of blindly relying on a default profile.

Another option is not setting the default profile to local in the production artifact and requiring explicit configuration. Choose the policy according to deployment requirements.

## 33. Cases where many profiles should not be used

Profiles are helpful, but should not become an uncontrolled combinatorial option system. For example:

~~~text
prod,cloud,redis,metrics,secure,fast-cache,async-mail,
feature-x,feature-y,feature-z,...
~~~

When too many profiles control small choices, the number of combinations to test grows rapidly, and bean conditions can overlap in confusing ways.

Instead:

- Use profiles to choose the **primary runtime context** or a major configuration group.
- Use `@ConfigurationProperties` to bind values and validation.
- Use `@ConditionalOnProperty` for independent features/capabilities.
- Use profile groups for common, managed combinations.
- Use a runtime feature flag system if features must change without restarting.

This division keeps code clearer and reduces bugs that "only happen with one special profile combination".

## 34. Quick troubleshooting table

| Symptom | Check first |
|---|---|
| No profile enabled yet `@Profile("default")` runs | That is Spring's default fallback |
| No profile enabled yet `@Profile("local")` runs | `spring.profiles.default` might be `local` |
| `prod` is active yet default bean does not run | Default is not added on top of active profiles |
| Active profile differs from YAML | Command line, environment, system property, or higher-precedence source |
| `getActiveProfiles()` returns empty even though local config applies | Local may be the default profile, not active |
| `application-prod.yml` not loaded | Location, filename, active profile, or Config Data precedence |
| `@Profile("prod")` does not create bean | Package scan, import, or other conditions |
| Two implementations registered together | Multiple profiles active or bean missing a condition |
| Boot reports invalid profile property | `spring.profiles.active/default/include/group` in the wrong document |
| Changed active profile at runtime yet bean did not change | Context already parsed configuration and created beans |
| Tests accidentally use production config | Check `@ActiveProfiles` and test property sources |
| One profile has varying configs | Determine which property source wins and document/import order |

## 35. Project profile configuration checklist

1. **Define meaningful profile names.** For example `local`, `test`, `staging`, `prod`.
2. **Decide policy when no active profile is set.** Use `default`, change to `local`, use `none`, or fail fast.
3. **Place shared configuration in `application.yml`.** Avoid duplicating properties that do not vary across environments.
4. **Place differences in `application-{profile}.yml` or on-profile documents.**
5. **Do not place `spring.profiles.active/default` in profile-specific files.**
6. **Do not place `spring.profiles.include/group` in profile-activated documents.**
7. **Prefer choosing the production profile from deployment**, not hard-coding it in source.
8. **Check the possibility of multiple profiles active simultaneously.** Avoid same-type/same-name bean collisions and confusing property overrides.
9. **Use `@Profile` at the configuration layer.** Do not scatter environment name checks in business logic.
10. **Do not treat profiles as a security boundary.** Credentials, network policies, and validation are still essential.
11. **Write tests for main profiles and fallbacks.** Especially test missing active profiles.
12. **Observe active and default profiles in startup logs.** Do not log secrets.
13. **Verify property source precedence.** A single YAML file does not represent the entire runtime configuration.
14. **Do not change profiles after startup and expect the object graph to update automatically.**
15. **Document profile groups and deployment rules** so team members use consistent configuration.

## Conclusion

`spring.profiles.active` selects which profiles are activated when Spring Boot starts. If the active profile list is empty, Spring uses the **default profile**; the default name is usually `default` and can be changed via `spring.profiles.default`. The default profile is not automatically added to the active profiles list, and `getActiveProfiles()` can still be empty when fallback configuration is taking effect.

Profiles govern both Config Data loading like `application-prod.yml` and `@Profile` bean registration. Active profiles can be selected via shared configuration files, command line, JVM system properties, environment variables, or startup APIs. When multiple sources declare the same key, **property source precedence** determines the effective value; when you need to add profiles, use `spring.profiles.include`, `spring.profiles.group`, or `SpringApplication.setAdditionalProfiles` for their intended purposes.

The key practical point is placing profile-selecting properties in a **non-profile-specific document**, avoiding treating `@Profile("default")` as a fallback bean regardless of environment, and checking actual active/default profiles rather than guessing from one file. Designing clearly for missing active profiles, production, and tests helps the same Spring Boot application run reliably across multiple environments without modifying source code.
