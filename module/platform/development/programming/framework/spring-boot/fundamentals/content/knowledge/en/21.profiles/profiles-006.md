# Profile expressions with AND, OR, NOT

Spring Boot uses **profiles** to select configuration and beans by environment or runtime role: development, testing, staging, production, local, cloud, worker, and so on. Sometimes a bean should only be created when multiple profiles are active together; in other cases, only one of them needs to be active, or you need to ensure a profile is not present.

Spring Framework supports **profile expressions** with three operators:

- **AND: `&`** — all component conditions must be true.
- **OR: `|`** — at least one component condition must be true.
- **NOT: `!`** — negates a profile name or a group of conditions.

Parentheses `(...)` group conditions and are especially important when combining AND with OR.

Examples of standalone expressions:

```java
@Profile("dev & cloud")
@Profile("dev | test")
@Profile("!prod")
@Profile("(dev | staging) & cloud")
```

The four lines above are syntax examples, **not four annotations to stack together on one class**. This lesson analyzes the meaning of each operator, handling multiple active profiles, `@Profile` on classes/methods, profile-based YAML documents, and testing.

## 1. What is a Profile?

A profile is a logical name whose active status Spring `Environment` tracks. For example:

```text
dev
test
staging
prod
local
cloud
metrics
worker
```

An application can activate multiple names simultaneously. Configuration:

```properties
spring.profiles.active=dev,cloud
```

means both `dev` and `cloud` are active.

It can be set from the command line:

```bash
java -jar app.jar --spring.profiles.active=dev,cloud
```

Or an environment variable:

```text
SPRING_PROFILES_ACTIVE=dev,cloud
```

In the base configuration section of `application.yml`:

```yaml
spring:
  profiles:
    active: dev,cloud
```

**Distinguish two operations:** `spring.profiles.active` selects the **set of profile names**; `@Profile("dev & cloud")` evaluates a **logical expression** against that set. A comma in the active profile list is not equivalent to the OR operator in the annotation.

Declare active profiles in a valid startup configuration source. Spring Boot does not allow certain properties such as `spring.profiles.active` inside configuration documents already conditioned with `spring.config.activate.on-profile` or in profile-specific files to activate additional profiles in that manner.

## 2. @Profile controls bean registration

`@Profile` belongs to Spring Framework:

```java
import org.springframework.context.annotation.Profile;
```

Spring only registers the corresponding bean definition when the profile condition is satisfied. The annotation is used on component/configuration classes or `@Bean` methods.

Example on a component:

```java
@Component
@Profile("dev")
public class DevelopmentAuditService implements AuditService {

    @Override
    public void record(String message) {
        System.out.println("DEV AUDIT: " + message);
    }
}
```

When `dev` is not active, this component is not registered via component scan.

Example on a configuration class:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionConfiguration {

    @Bean
    public AuditClient auditClient() {
        return new RemoteAuditClient();
    }
}
```

If `prod` is not active, the configuration above does not provide the `auditClient` bean.

Example on a method:

```java
@Configuration(proxyBeanMethods = false)
public class AuditConfiguration {

    @Bean
    @Profile("dev")
    public AuditClient devAuditClient() {
        return new InMemoryAuditClient();
    }

    @Bean
    @Profile("prod")
    public AuditClient prodAuditClient() {
        return new RemoteAuditClient();
    }
}
```

Each method has its own condition. Remember that both `dev` and `prod` can be activated together; then two beans of the same type can coexist and cause ambiguity if an injection point requires a single `AuditClient`.

**@Profile does not re-run per HTTP request.** It is evaluated while building the application context.

## 3. Profile expression syntax differs from SpEL and Java

Profile expressions have their own grammar, not SpEL or Java expressions.

Use:

```java
@Profile("dev & cloud")
@Profile("dev | test")
@Profile("!prod")
```

Do not use Java syntax:

```java
@Profile("dev && cloud")
@Profile("dev || test")
```

Nor SpEL:

```java
@Profile("#{dev && cloud}")
```

Those forms do not express valid profile expression syntax. The `#{...}` form is for SpEL in contexts supporting evaluation such as `@Value`, not for declaring `@Profile`.

Reference table:

| Intent | Expression |
|---|---|
| Only dev | `dev` |
| Both dev and cloud | `dev & cloud` |
| Dev or test | `dev | test` |
| Not prod | `!prod` |
| Dev or staging, and must be cloud | `(dev | staging) & cloud` |
| Neither prod nor staging | `!prod & !staging` |
| Not in the prod/staging group | `!(prod | staging)` |

## 4. AND: the & operator

AND is true when **all component conditions are true**.

```java
@Component
@Profile("dev & cloud")
public class CloudDevelopmentInspector {
}
```

Truth table:

| Active profiles | dev active? | cloud active? | `dev & cloud` |
|---|---:|---:|---:|
| Unspecified | No | No | False |
| `dev` | Yes | No | False |
| `cloud` | No | Yes | False |
| `dev,cloud` | Yes | Yes | True |
| `dev,cloud,test` | Yes | Yes | True |
| `prod,cloud` | No | Yes | False |

AND does not require **only** those two names to be in the context. If `dev` and `cloud` are active together with `test`, the expression `dev & cloud` is still true.

Example of a metrics configuration that applies only to production on cloud infrastructure:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod & cloud")
public class ProductionCloudMetricsConfiguration {

    @Bean
    public MetricsExporter metricsExporter() {
        return new CloudMetricsExporter();
    }
}
```

Before adding AND, make sure the profiles represent truly independent dimensions; for example, `prod` describes the environment and `cloud` describes the runtime platform.

## 5. OR: the | operator

OR is true when **at least one component condition is true**.

```java
@Component
@Profile("dev | test")
public class FakePaymentGateway implements PaymentGateway {
    // Implementation used for development and testing environments.
}
```

| Active profiles | `dev | test` |
|---|---:|
| Unspecified | False |
| `dev` | True |
| `test` | True |
| `dev,test` | True |
| `prod` | False |
| `prod,test` | True |

The last row is important: when `prod` and `test` are active together, OR is still true because `test` is active. Spring does not assume `prod` and `test` are mutually exclusive.

If the intent is "dev or test, but strictly never when prod is active", write:

```java
@Profile("(dev | test) & !prod")
```

This condition has both an OR group and an explicit NOT condition.

## 6. NOT: the ! operator

NOT inverts the evaluation result of a profile name or an entire group.

```java
@Component
@Profile("!prod")
public class NonProductionBanner {
}
```

| Active profiles | `!prod` |
|---|---:|
| Unspecified | True |
| `dev` | True |
| `test` | True |
| `staging` | True |
| `prod` | False |
| `prod,cloud` | False |
| `prod,dev` | False |

**NOT does not mean dev.** `!prod` is true for every active profile set that does not contain `prod`, even when the application has no active profile specified.

Compare:

```java
@Profile("dev")
```

matches only when dev is active. Whereas:

```java
@Profile("!prod")
```

has a much broader scope.

### 6.1. Negating a group

```java
@Profile("!(prod | staging)")
```

True when neither prod nor staging is active. By De Morgan's laws:

```text
!(prod | staging)  <=>  !prod & !staging

!(dev & cloud)     <=>  !dev | !cloud
```

Choose the most readable form. To exclude specific environments, negating a group is often clearer than a scattered chain of negations.

## 7. Parentheses and combining AND/OR

Do not mix `&` and `|` **in the same expression without grouping parentheses**.

Invalid example:

```java
@Profile("dev & cloud | test")
```

The expression above could be interpreted with two different intents:

```java
@Profile("(dev & cloud) | test")
```

or:

```java
@Profile("dev & (cloud | test)")
```

Both forms are valid, but their outcomes differ.

| Active profiles | `(dev & cloud) | test` | `dev & (cloud | test)` |
|---|---:|---:|
| `dev` | False | False |
| `test` | True | False |
| `dev,test` | True | True |
| `dev,cloud` | True | True |
| `cloud,test` | True | False |
| `prod` | False | False |

With the first expression, `test` alone is enough. With the second expression, `dev` is always a required condition.

Therefore, **whenever both AND and OR are present, always use parentheses to express intent**, rather than assuming precedence rules like in Java.

## 8. Multi-level expressions

You can write:

```java
@Profile("(dev | staging) & cloud & !maintenance")
```

Meaning:

1. `dev` **or** `staging` is active.
2. `cloud` is active.
3. `maintenance` is **not** active.

Another example:

```java
@Profile("prod & !(maintenance | readonly)")
```

The bean applies only when prod is active and neither maintenance nor readonly is active.

If active profiles are `prod,maintenance`, the second expression is false. If active profiles are `prod,cloud`, the expression is true.

It is possible to write a contradictory condition:

```java
@Profile("prod & !prod")
```

No set of active profiles will make this condition true. Spring does not prioritize one part of a condition over the rest; the entire logical expression determines the outcome.

## 9. @Profile accepts an array: elements are ORed

A very important feature: `@Profile` can accept multiple expression strings.

```java
@Profile({"dev", "test"})
```

The meaning is **dev or test** is active, not both.

Compare:

| Syntax | Meaning |
|---|---|
| `@Profile("dev & test")` | Both active |
| `@Profile("dev | test")` | At least one active |
| `@Profile({"dev", "test"})` | At least one active |
| `@Profile({"dev & cloud", "test"})` | (dev and cloud) or test |

With multiple expressions:

```java
@Profile({
    "prod & cloud",
    "staging & cloud"
})
```

is equivalent in intent to:

```java
@Profile("(prod | staging) & cloud")
```

The array form fits when you want to split conditional branches into readable strings. The single-expression form fits when branches share a common condition.

### 9.1. Do not confuse the two separators

`spring.profiles.active=dev,cloud` activates **both** dev and cloud.

`@Profile({"dev", "cloud"})` is the condition **dev or cloud**.

One sets the active set; the other evaluates an expression. This is the root of many profile usage bugs.

## 10. Comprehensive evaluation table

Consider the expressions:

- E1 = `dev & cloud`.
- E2 = `dev | staging`.
- E3 = `!prod`.
- E4 = `(dev | staging) & cloud`.
- E5 = `prod & !cloud`.

| Active profiles | E1 | E2 | E3 | E4 | E5 |
|---|---:|---:|---:|---:|---:|
| Unspecified | False | False | True | False | False |
| `dev` | False | True | True | False | False |
| `dev,cloud` | True | True | True | True | False |
| `prod` | False | False | False | False | True |
| `prod,cloud` | False | False | False | False | False |
| `staging,cloud` | False | True | True | True | False |

Evaluation steps:

1. Determine the effective active profiles set.
2. Determine whether each profile name in the expression is true or false.
3. Apply NOT to the corresponding operand.
4. Evaluate parenthesized groups.
5. Apply AND/OR according to the declared structure.
6. Register the bean if the condition is true **and** other bean/configuration conditions are also satisfied.

The table only determines the profile condition; it does not guarantee the bean definitely exists. The component must still be within scan/import scope and all dependencies must be valid.

## 11. Complete example: selecting exactly one implementation

Suppose an application wants to use a "remote" gateway when running production on cloud, and a "local" gateway in all other cases.

Interface:

```java
package com.example.notification;

public interface NotificationGateway {
    String channel();
}
```

Configuration:

```java
package com.example.notification;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NotificationGatewayConfiguration {

    @Bean
    @Profile("prod & cloud")
    public NotificationGateway remoteGateway() {
        return () -> "remote";
    }

    @Bean
    @Profile("!(prod & cloud)")
    public NotificationGateway localGateway() {
        return () -> "local";
    }
}
```

`NotificationGateway` is a functional interface, so lambdas can be used as in the example.

Consuming service:

```java
package com.example.notification;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final NotificationGateway gateway;

    public NotificationService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    public String selectedChannel() {
        return gateway.channel();
    }
}
```

Results:

| Active profiles | Bean created from configuration | Channel value |
|---|---|---|
| `dev` | `localGateway` | `local` |
| `test` | `localGateway` | `local` |
| `prod` | `localGateway` | `local` |
| `cloud` | `localGateway` | `local` |
| `prod,cloud` | `remoteGateway` | `remote` |
| `prod,cloud,metrics` | `remoteGateway` | `remote` |

The two expressions `prod & cloud` and `!(prod & cloud)` are negations of each other. Therefore, for this pair of `@Bean` methods, exactly one method is applied by profile condition each time a context is created.

The example simulates implementation selection; the lambdas do not perform real message sending. With a real gateway, URLs, credentials, and timeouts still require independent configuration/validation.

### Why avoid writing two overlapping conditions?

For example:

```java
@Bean
@Profile("prod")
NotificationGateway prodGateway() { /* ... */ }

@Bean
@Profile("cloud")
NotificationGateway cloudGateway() { /* ... */ }
```

When `prod,cloud` are active together, both methods can supply beans of the same type. If a service injects a `NotificationGateway` without a suitable `@Qualifier` or `@Primary`, `NoUniqueBeanDefinitionException` can occur.

To pick a single implementation, design mutually exclusive conditions or deliberate DI rules.

## 12. @Profile on a class and on a @Bean method

When placed on a configuration class:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod & cloud")
public class ProductionCloudConfiguration {

    @Bean
    public ExportClient exportClient() {
        return new CloudExportClient();
    }

    @Bean
    public ExportMonitor exportMonitor() {
        return new ExportMonitor();
    }
}
```

the condition applies to the entire configuration. If not satisfied, the beans above are not registered from this class.

When placed on `@Bean` methods:

```java
@Configuration(proxyBeanMethods = false)
public class ExportConfiguration {

    @Bean
    @Profile("prod & cloud")
    public ExportClient remoteExportClient() {
        return new CloudExportClient();
    }

    @Bean
    @Profile("dev | test")
    public ExportClient fakeExportClient() {
        return new FakeExportClient();
    }
}
```

each method has its own condition.

If both the class and a method inside have `@Profile`, then both conditions must be true:

```java
@Configuration(proxyBeanMethods = false)
@Profile("cloud")
public class CloudConfiguration {

    @Bean
    @Profile("prod")
    public CloudClient productionClient() {
        return new CloudClient();
    }
}
```

The `productionClient` bean can only be registered when both `cloud` and `prod` are active.

Avoid creating multiple overloaded `@Bean` methods with the same name and different `@Profile` annotations to branch: overload selection has its own limitations. Naming factory methods/beans clearly is easier to maintain.

## 13. Default profile and NOT

When no active profile is declared, Spring uses **default profiles** to evaluate conditions. The default name is usually `default`.

For example:

```java
@Bean
@Profile("default")
public Clock defaultClock() {
    return Clock.systemUTC();
}
```

If there are no active profiles and the effective default profile is `default`, this bean can be registered.

When the `dev` profile is explicitly activated, Spring does not automatically keep `default` as an active profile just because it carries the default name.

### Distinguishing two conditions

```java
@Profile("default")
```

checks the profile name `default`.

```java
@Profile("!prod")
```

checks that `prod` is not active.

When `dev` is active, the `!prod` expression is still true, whereas `default` is normally no longer used as the fallback profile. These are two different conditions.

You can change the default profile:

```properties
spring.profiles.default=local
```

When there is no explicit active profile, the name `local` can be used as the effective default profile. When designing, distinguish "default profile" from a broad negation condition.

## 14. Profile expressions in application.yml

Spring Boot also supports conditional activation of a configuration document using `spring.config.activate.on-profile`.

Example of two YAML documents separated by `---`:

```yaml
app:
  report:
    storage: local
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  report:
    storage: remote
    timeout: 30s
```

Meaning:

- The first document provides base values.
- The second document is activated only when both `prod` and `cloud` are active.
- Properties in the second document can override base values according to config data ordering rules.

OR example:

```yaml
---
spring:
  config:
    activate:
      on-profile: "staging | prod"

app:
  diagnostics:
    include-build-info: true
```

Combined example:

```yaml
---
spring:
  config:
    activate:
      on-profile: "(dev | staging) & cloud & !maintenance"

app:
  sample-data:
    enabled: true
```

Different mechanisms:

| Mechanism | Role |
|---|---|
| `spring.profiles.active` | Specifies the set of active profiles |
| `spring.config.activate.on-profile` | Decides whether to load a configuration document |
| `@Profile(...)` | Decides bean/configuration registration |

A config document being loaded does not mean a bean is guaranteed to be created. Beans also depend on component scanning, auto-configuration, and other conditions.

In older Boot versions, YAML had a different way to declare profile-specific sections. For modern Spring Boot projects, `spring.config.activate.on-profile` is the right choice for making a config document conditional.

## 15. Combining @Profile with @ConditionalOnProperty

Profile expressions concern the **set of profiles**, while property conditions concern **configuration property values**.

For example:

```java
@Configuration(proxyBeanMethods = false)
@Profile("(dev | staging) & cloud")
@ConditionalOnProperty(
    prefix = "feature.report",
    name = "enabled",
    havingValue = "true"
)
public class ReportConfiguration {

    @Bean
    public ReportClient reportClient() {
        return new ReportClient();
    }
}
```

The configuration is applied only if:

1. Either dev or staging is present.
2. Cloud is present.
3. `feature.report.enabled` is true according to the property condition.

Visualize it as:

```text
(dev | staging) & cloud
           │
           ▼
     Profile condition
           │
          AND
           │
           ▼
feature.report.enabled=true
           │
           ▼
    ReportConfiguration
```

If you only want to toggle a feature independently of environment, `@ConditionalOnProperty` is usually better than creating another profile just to act as a feature flag.

## 16. When to use profiles vs. properties?

| Need | Sensible mechanism |
|---|---|
| Choose implementation for dev/test/prod | Profile |
| Create bean only when both prod and cloud are active | Profile expression AND |
| Use fake integration in dev or test | Profile expression OR |
| Do not create bean when prod is active | Profile expression NOT |
| Toggle a feature via a config flag | `@ConditionalOnProperty` |
| Choose provider by value `payment.provider=stripe` | Property condition or typed configuration |
| Change selection immediately at runtime | Dynamic configuration mechanism |
| Control access to resources | Real authentication and authorization |

**Do not use profiles as a security boundary.** For example, `@Profile("!prod")` could allow a bean to appear in a production deployment where the `prod` profile name was forgotten. Dangerous endpoints still need protection via authorization policies independent of profiles.

## 17. Evaluating expressions in code with Environment

If you need to evaluate a profile expression in code, Spring Framework provides the `Profiles.of(...)` and `Environment.acceptsProfiles(...)` APIs.

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

@Component
public class DeploymentInspector {

    private final Environment environment;

    public DeploymentInspector(Environment environment) {
        this.environment = environment;
    }

    public boolean enableCloudDiagnostics() {
        return environment.acceptsProfiles(
                Profiles.of("(dev | staging) & cloud")
        );
    }
}
```

You can use:

```java
Profiles condition = Profiles.of("dev & !prod");
boolean matches = environment.acceptsProfiles(condition);
```

In addition:

- `environment.getActiveProfiles()` returns the array of profile names declared active.
- `environment.getDefaultProfiles()` returns default profile names.
- If the active profile array is empty, `Profiles` evaluation can still rely on effective default profiles.

However, do not overuse manual profile checks across many methods. If the goal is choosing an implementation for an interface, using `@Profile` combined with dependency injection is usually clearer.

## 18. Testing expressions with @ActiveProfiles

Spring Test provides `@ActiveProfiles` to activate specific profiles in the test application context.

Example testing the gateway from Section 11:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles({"prod", "cloud"})
class RemoteGatewayTest {

    @Autowired
    NotificationGateway gateway;

    @Test
    void selectsRemoteGateway() {
        assertEquals("remote", gateway.channel());
    }
}
```

When both prod and cloud are active, the configuration selects `remoteGateway`.

Another test:

```java
@SpringBootTest
@ActiveProfiles("dev")
class LocalGatewayTest {

    @Autowired
    NotificationGateway gateway;

    @Test
    void selectsLocalGateway() {
        assertEquals("local", gateway.channel());
    }
}
```

Place the two tests in separate files/classes and ensure the application configuration actually scans/imports `NotificationGatewayConfiguration`.

**Syntax difference:** `@ActiveProfiles({"prod", "cloud"})` specifies two active names. `@Profile("prod & cloud")` is an expression checking both. Never treat the string `"prod & cloud"` as an active profile name.

### 18.1. Unit testing logic directly with MockEnvironment

When you only want to test an expression without booting the application:

```java
import org.junit.jupiter.api.Test;
import org.springframework.core.env.Profiles;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.*;

class ProfileExpressionTest {

    @Test
    void matchesOnlyWhenBothAreActive() {
        MockEnvironment env = new MockEnvironment();
        env.setActiveProfiles("prod", "cloud");

        assertTrue(env.acceptsProfiles(
                Profiles.of("prod & cloud")
        ));

        assertFalse(env.acceptsProfiles(
                Profiles.of("dev & cloud")
        ));
    }
}
```

This example uses Spring Test and JUnit. Standalone expression tests like this are convenient for writing a matrix of active profiles.

### 18.2. Testing conflicting multi-profile cases

If code has `@Profile("dev | test")`, testing with `@ActiveProfiles({"prod", "test"})` can still cause the bean to match. This is valid logical behavior, though it might not match business intent.

Test cases where multiple profiles are active together, rather than testing only single names in isolation.

## 19. Debugging when a bean does not appear

If you expect a bean to be present yet the context does not register it, check in order:

1. **Is the class scanned/imported?** A matching profile does not create a bean if the class is not a bean candidate.
2. **What are the active profile names?** Check startup logs and Environment.
3. **Is the default profile being used?** Cases with no active profiles easily cause confusion.
4. **Are multiple profiles active simultaneously?** A NOT can become false when another name is added.
5. **Does the expression have proper parentheses?** AND/OR must be grouped clearly.
6. **Is `@Profile` on the class or method?** It may be subject to conditions at multiple levels.
7. **Are there other conditions?** Property/classpath/bean conditions also take effect.
8. **Are there multiple beans of the same type?** A DI error might stem from two OR branches matching at once.
9. **Is the config document activated?** Missing properties because a YAML document did not match the profile can also cause errors.
10. **Does the test profile differ from the deployment profile?** Results in tests do not guarantee identical production behavior.

### 19.1. Printing effective profile names for diagnosis

```java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ProfileDiagnosticsConfiguration {

    @Bean
    ApplicationRunner logProfiles(Environment environment) {
        return args -> {
            System.out.println(
                "Active profiles: "
                    + Arrays.toString(environment.getActiveProfiles())
            );
            System.out.println(
                "Default profiles: "
                    + Arrays.toString(environment.getDefaultProfiles())
            );
        };
    }
}
```

This example is for learning/debugging. Never print the entire environment into production logs because it may contain secrets.

You can run:

```bash
java -jar app.jar --debug
```

to receive a condition evaluation report useful for auto-configuration. Profile conditions on application components may not be displayed fully in the same auto-configuration report format; in that case, use tests and inspect bean definitions directly.

If using Spring Boot Actuator, `/actuator/beans` and `/actuator/conditions` can also be helpful when enabled and properly secured.

## 20. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| `dev & cloud` does not match when only dev is enabled | AND requires both names. | Enable cloud or revise expression intent. |
| `@Profile({"dev","cloud"})` matches when only dev is enabled | Arrays use OR. | Use `@Profile("dev & cloud")` for AND. |
| `dev & cloud | test` reports an error | Mixed AND/OR without parentheses. | Use `(dev & cloud) | test` or `dev & (cloud | test)`. |
| `!prod` matches when no active profile is set | Prod is not active so NOT is true. | Use a positive expression like `dev` if only dev is wanted. |
| `dev | test` matches in prod | `test` is also active. | Use `(dev | test) & !prod` if prod must be excluded. |
| `@Profile("default")` does not match when dev is enabled | Default profile is not active alongside under default fallback rules. | Understand default profiles and pick the right condition. |
| Bean still absent even though expression is true | Class not scanned or another condition fails. | Check registration and conditions. |
| Multiple beans of the same type appear | Overlapping expressions when multiple profiles are active. | Design mutually exclusive conditions, or use `@Qualifier`/`@Primary`. |
| Changing profile at runtime does not change beans | Profile conditions are evaluated when building the context. | Restart context or use another runtime mechanism. |
| Using `&&`, `||`, `#{...}` | Confusing profile expressions with Java/SpEL. | Use `&`, `|`, `!`, `(...)`. |
| Activating profiles from a profile-specific YAML document | Placed `spring.profiles.active` in an invalid config data context. | Configure active profiles in a valid startup source. |

## 21. Designing maintainable profiles

### 21.1. Separate names by meaning

For example:

- Environments: `dev`, `test`, `staging`, `prod`.
- Infrastructure: `local`, `cloud`.
- Roles: `worker`, `web`.
- Add-on capabilities: `metrics`, `tracing`.

These naming groups are only conventions. Spring does not prevent `dev` and `prod` from being active together. If that is an invalid state for your system, add validation or deployment rules.

### 21.2. Prefer positive conditions when possible

`@Profile("dev | test")` is usually clearer and tighter than `@Profile("!prod")` if a feature is meant only for dev/test. Negated conditions can accidentally activate in new profiles like demo/training.

### 21.3. Avoid long, hard-to-read expressions

An expression such as:

```java
@Profile("(dev | staging) & cloud & !maintenance")
```

is still fairly clear. When there are too many nested OR/AND groups, consider:

- Splitting configuration into smaller classes.
- Using properties that clearly describe a feature or provider.
- Using appropriate Spring Boot conditions.
- Writing tests across a profile matrix.
- Documenting deployment policy and bean ownership.

### 21.4. Do not treat profiles as security measures

Do not rely solely on `!prod` to guard administrative endpoints or fake clients that can corrupt data or perform dangerous operations. Profiles can be misconfigured; authorization, network policies, and credential boundaries must be enforced independently when needed.

## 22. Practice exercises

### Exercise A — Testing AND

Create a component:

```java
@Component
@Profile("dev & cloud")
public class CloudDevOnlyComponent {}
```

Run with active profiles `dev`, `cloud`, `dev,cloud`, and `dev,cloud,test`. Observe when the bean appears.

### Exercise B — OR and arrays

Compare `@Profile("dev | test")` with `@Profile({"dev", "test"})`. Try active sets `dev`, `test`, `dev,test`, and `prod`. Explain why both forms produce the same result.

### Exercise C — NOT and default

Create two separate beans, one with `@Profile("!prod")` and one with `@Profile("default")`. Try no active profile declared, `dev`, and `prod`. Compare the results.

### Exercise D — Parentheses

Evaluate the results of two expressions:

```text
(dev & cloud) | test
dev & (cloud | test)
```

with active profiles `dev`, `test`, `dev,test`, `cloud,test`, and `dev,cloud`.

### Exercise E — Selecting exactly one bean

Use interface `PaymentGateway` and two implementations. Put `prod & cloud` on the remote gateway and `!(prod & cloud)` on the local gateway. Test active sets to verify that two beans of the same type are never created from that pair.

### Exercise F — Profile-based YAML

Create a YAML document with `spring.config.activate.on-profile: "staging | prod"`. Set `app.diagnostics.mode` differently from the base document. Observe values with dev, staging, and prod.

### Exercise G — Unit testing expressions

Use `MockEnvironment` with `Profiles.of("(dev | staging) & cloud")`. Test `dev,cloud`, `staging,cloud`, `prod,cloud`, and `dev`.

### Exercise H — Fixing an ambiguous condition

A project has:

```java
@Profile("dev & cloud | staging")
```

Explain why it must be fixed and write two ways of grouping it with different meanings. Does an active set with only `staging` cause the bean to be registered in each form?

### Exercise I — Risk analysis

A sensitive bean is marked `@Profile("!prod")`. Analyze what happens if a production deployment fails to declare the `prod` profile and propose a protection layer independent of profiles.

## 23. Takeaways

1. **AND uses `&`**: all conditions must be true.
2. **OR uses `|`**: only one condition needs to be true.
3. **NOT uses `!`**: negates a profile or a group.
4. **Parentheses `(...)`** group expressions; when both AND and OR exist, group explicitly to avoid invalid syntax or misinterpretation.
5. **`@Profile({"dev", "test"})` is OR**, not AND.
6. Multiple profiles can be enabled simultaneously; names like dev/test/prod are not mutually exclusive on their own.
7. `!prod` does not mean `dev`, because NOT has a broad scope.
8. `default` is a fallback profile name, not a negation expression.
9. `@Profile` controls bean registration; `spring.config.activate.on-profile` controls config document activation.
10. `spring.profiles.active` specifies the active profiles set, not a place to write bean-selection expressions.
11. When you need to evaluate an expression in code, use `Environment.acceptsProfiles(Profiles.of(...))`.
12. In tests, `@ActiveProfiles({"prod", "cloud"})` activates two profiles; remember to test overlapping multi-profile cases too.
13. Profiles are evaluated when building the context; they are neither runtime feature toggles nor security mechanisms.
14. With multiple beans of the same type, design mutually exclusive expressions or explicit DI mechanisms.
15. When expressions grow long, consider splitting configurations or using property conditions with clearer business meaning.

**Core mindset:** first determine the set of active profiles, then evaluate `@Profile` as a logical expression over that set. AND, OR, NOT, and clear parentheses help Spring Boot register the right beans for each environment and runtime role.
