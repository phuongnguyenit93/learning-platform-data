# Bean Definition Overriding and the Limits of Using It to Resolve Conflicts

In Spring Boot, an application can declare beans using `@Component`, `@Service`, `@Configuration` with `@Bean`, or receive beans from auto-configuration and integrated libraries. When these paths share **a single bean name**, Spring can encounter a conflict right at the **bean definition registration** step. The **bean definition overriding** mechanism decides whether an existing definition may be replaced by a later-registered definition.

At first glance, enabling overriding can look like the fastest way to make an application start. However, without knowing where the two definitions come from, allowing overrides easily hides configuration bugs, swaps out the actual implementation, and makes behavior depend on registration order. This lesson clearly explains **what overriding is, when it occurs, what happens if you enable it, and the limits of this approach** in a Spring Boot application.

## 1. Recap: `BeanDefinition` and Bean Name

`BeanDefinition` is **metadata** stored by the Spring IoC container so it knows how to create and manage a bean. This metadata can hold the class name, factory method, scope, lazy status, init/destroy callbacks, and dependency injection details.

Example:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    public String createInvoice() {
        return "Created";
    }
}
```

When `InvoiceService`'s package lies within the component scan scope, Spring can register a bean definition with the default name `invoiceService`. Only later does the container create the instance when needed.

Another approach:

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean("appClock")
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Here `appClock` is the **bean name**; `Clock` is the bean **type**; `appClock()` is the **factory method**. These three pieces of information are distinct. You can have multiple beans of type `Clock` with different names. Conversely, if two definitions try to register under the same name `appClock` in the same registry, Spring must decide whether to allow replacing the earlier definition.

### 1.1. Bean Definition vs. Bean Instance

```text
@Bean / @Component declaration
           |
           v
   BeanDefinition Registry
      "appClock" -> metadata
           |
           v
     BeanFactory creates bean
           |
           v
   Managed Clock object
```

**Overriding happens at the registration definition level**; it does not mean Java method overriding with `@Override`, nor does it mean two objects are merged automatically. If Spring already rejected the duplicate definition name, the application can fail before the corresponding object is ever instantiated.

### 1.2. Where Do Bean Names Usually Come From?

| Declaration style | Typical bean name |
| --- | --- |
| `@Service` on `EmailService` | `emailService` if no explicit name is given |
| `@Component("fastParser")` | `fastParser` |
| `@Bean` on `Clock systemClock()` | `systemClock` if no name is specified |
| `@Bean("appClock")` on `Clock systemClock()` | `appClock` |
| Framework/auto-configuration setup | Name defined by the configuration or framework |

Default component naming rules have exceptions per JavaBeans rules; when analyzing an issue, check the **actual bean name** in logs instead of guessing solely from the class name.

## 2. What Is Bean Definition Overriding?

In Spring, the bean definition registry maps **bean name** to **bean definition**. When a name already holds a definition and another definition attempts to register under the same name, conceptually there are two options:

```text
Register bean definition A: name = "appClock"
                     |
                     v
          Registry["appClock"] = A
                     |
Register bean definition B: name = "appClock"
                     |
                     v
        Does name already exist in registry?
                     |
          +----------+----------+
          |                     |
   Overriding = false    Overriding = true
          |                     |
          v                     v
     Report conflict      Replace definition A with B
       / fail             under the same bean name
```

**Bean definition overriding** is allowing a newly registered definition to replace an existing definition **with the same bean name inside the same bean factory/registry**. When permitted, the later-registered definition can replace the earlier one.

This has several consequences:

1. The two definitions do not become two differently named beans; the registry keeps the later definition under that same name.
2. Which object gets used later depends on which definition remains active and how the bean is instantiated.
3. Configuration processing order, component scanning order, and integrated libraries can affect which definition is registered last.
4. Allowing overriding does not guarantee every name collision across every scan/registration mechanism will pass quietly: separate checks can happen before or outside registry replacement.

### 2.1. Concrete Example: Two `@Bean` Methods with the Same Name

Consider a Spring Boot application with the layout:

```text
src/main/java/com/example/demo/
├── DemoApplication.java
└── config/
    ├── UtcClockConfiguration.java
    └── LocalClockConfiguration.java
```

Startup class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

First definition:

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UtcClockConfiguration {

    @Bean("appClock")
    public Clock utcClock() {
        return Clock.systemUTC();
    }
}
```

Second definition:

```java
package com.example.demo.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LocalClockConfiguration {

    @Bean("appClock")
    public Clock localClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Both configuration classes sit under the root package `com.example.demo`, so Spring component scan can discover both. Each class declares a `@Bean` method, yet **both specify the bean name `appClock`**.

With bean definition overriding disabled, registration may fail with an error like:

```text
BeanDefinitionOverrideException:
Invalid bean definition with name 'appClock' ...
Cannot register bean definition ... since there is already ...
```

Exact wording and display format depend on the Spring Boot / Spring Framework version. The key point is the **duplicate bean name**; the fact that both factory methods return `Clock` objects does not resolve the collision.

## 3. Spring Boot's Default and How to Enable Overriding

In modern Spring Boot releases since Spring Boot 2.1, **bean definition overriding is disabled by default**. Spring Boot intentionally surfaces name collisions early instead of silently picking one definition based on registration order.

To allow replacement, you can configure `src/main/resources/application.properties`:

```properties
spring.main.allow-bean-definition-overriding=true
```

Or in `application.yml`:

```yaml
spring:
  main:
    allow-bean-definition-overriding: true
```

Pick **one** configuration format matching your project; do not duplicate both. This property affects how Spring Boot configures the bean factory at startup.

### 3.1. Configuring Programmatically in Java

You can also set it on `SpringApplication` before running:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setAllowBeanDefinitionOverriding(true);
        application.run(args);
    }
}
```

At the Spring Framework level, `DefaultListableBeanFactory` also provides a setting for allowing bean definition overriding. For typical Spring Boot apps, configuring via `spring.main...` or `SpringApplication` is easier to read.

### 3.2. What Happens with the Two-`Clock` Example?

When overriding is enabled, both definitions can be processed during registration, yet the name `appClock` ends up mapped solely to whichever definition was kept last. For example:

```text
Order Case 1:

1. UtcClockConfiguration registers "appClock"
2. LocalClockConfiguration registers "appClock"
3. Definition from LocalClockConfiguration replaces the earlier one

Order Case 2:

1. LocalClockConfiguration registers "appClock"
2. UtcClockConfiguration registers "appClock"
3. Definition from UtcClockConfiguration replaces the earlier one
```

**Do not assume one class always wins** based on scan order or configuration discovery order. Within a specific run, the outcome may appear consistent, yet registration order should never become an undocumented business rule.

This example shows the obvious risk: `Clock.systemUTC()` and `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` behave differently across time zones when used with time APIs. The application can still start while applying the wrong time-zone rule.

### 3.3. Do Not Confuse This Property with `@Primary`

```properties
spring.main.allow-bean-definition-overriding=true
```

does not mean Spring automatically marks a bean as primary. This property addresses **duplicate-name registration**. `@Primary`, `@Qualifier`, and bean selection mechanisms address **picking one bean among multiple candidates matching a type** during dependency injection.

## 4. Two Conflicts to Distinguish Before Fixing

A dependency injection error and a bean definition overriding error can both fall under "duplicate bean" discussions, yet their causes and fixes are completely different.

### 4.1. Conflict with **the same name**: bean definition overriding

```java
@Configuration
class FirstConfig {
    @Bean("clock")
    Clock firstClock() {
        return Clock.systemUTC();
    }
}

@Configuration
class SecondConfig {
    @Bean("clock")
    Clock secondClock() {
        return Clock.systemDefaultZone();
    }
}
```

Both definitions share the name `clock`. If overriding is disallowed, registration can fail **even before any service asks to inject `Clock`**. The error occurs in the **registry**, prior to resolving any specific service's injection point.

### 4.2. Conflict with **same type but different names**: dependency injection ambiguity

```java
@Configuration
class ClockConfiguration {
    @Bean("utcClock")
    Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean("localClock")
    Clock localClock() {
        return Clock.systemDefaultZone();
    }
}
```

Here there are **two valid bean names**. There is no bean definition override collision. However, upon injection:

```java
@Service
class ReportService {
    ReportService(Clock clock) {
        // Spring needs to know which Clock to use
    }
}
```

Spring may fail with an error such as:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
utcClock, localClock
```

In cases where Spring can rely on qualifiers, parameter names, or other candidate selection rules, it may sometimes resolve a single candidate; still, do not treat parameter-name matching as your sole configuration contract. For clarity, specify the bean with `@Qualifier` or mark a default with `@Primary`.

**Enabling bean definition overriding will not fix this conflict**, because no two bean definitions share the same name to override.

### 4.3. Error Comparison Table

| Situation | Primary issue | Proper fix |
| --- | --- | --- |
| Two `@Bean("appClock")` in the same context | Duplicate bean name at registration | Rename, remove redundant definition, or use explicit conditions |
| Two `Clock` beans named `utcClock` and `localClock` injected by type | Multiple candidates of the same type | `@Qualifier`, `@Primary`, or adjust design |
| Required bean to inject does not exist | No matching candidate | Check package scan, profiles, conditions, dependencies, and config |
| Bean got swapped for another implementation after enabling overriding | Later definition overwrote earlier one | Locate both definitions sharing the name and establish the true owner |
| Two components share default name across different packages | Name collision from naming/scanning | Assign explicit names, narrow scan, or select which component to register |

Some conflicts arising during **component scanning** may be rejected by the scanner's compatibility checks before standard registry replacement runs. Thus, `allow-bean-definition-overriding=true` is not a magic switch guaranteed to silence every duplicate-name error.

## 5. Why Using Overriding to "Patch" Conflicts Has Limits

### 5.1. Masks Naming Errors or Duplicate Configuration

Suppose two internal libraries both register a bean named `tokenProvider`, each issuing tokens differently. If overriding is enabled, the application may silently keep just one definition without clarifying who owns that name. Later, a dependency bump or configuration ordering change can alter runtime behavior with no visible change at the injection site.

A better solution is **purposeful naming** like `internalTokenProvider` and `partnerTokenProvider`, then injecting the intended one via qualifiers or distinct interfaces.

### 5.2. Depends on Registration Order

Which definition gets registered last can depend on:

- Processing order of configuration classes.
- Component scan scope and discovered class list.
- Active conditions or profiles.
- Registration mechanisms provided by libraries and auto-configurations.
- How the application is launched across environments.

Never use "whichever class scans last wins" as an implementation selection strategy. When conditional choice is needed, express that condition explicitly in configuration.

### 5.3. Can Swap in the Wrong Type or Behavior

Two bean definitions sharing a name do not even have to share the same type or scope. For instance, `cacheClient` could be replaced from a Redis-backed implementation with a local in-memory one. Code unaware of implementation details might keep running, while code relying on Redis's distributed guarantees silently breaks.

If two definitions have incompatible types, dependency injection may simply turn a "duplicate bean name" error into a "no bean of required type" or bean creation failure. Enabling overriding **does not verify behavioral equivalence** between two bean definitions.

### 5.4. `@Primary` and `@Qualifier` Cannot Fix Duplicate Bean Names

`@Primary` helps choose among **multiple surviving beans** of the same type. If two definitions share the name `appClock` and the registry disallows overriding, registration fails before `@Primary` is ever evaluated.

`@Qualifier` works similarly: it selects the desired bean at injection time, yet **cannot fix colliding names on the bean definitions themselves**.

### 5.5. Does Not Make Two Same-Named Versions Available Together

When one definition overrides another, you do not somehow get both implementations to pick from. If the application needs both, register them under **different names** or design a clearly identified set of beans.

### 5.6. Does Not Solve Conflicts in Other Layers

Overriding does not resolve:

- `NoUniqueBeanDefinitionException` caused by multiple beans of the same type.
- `NoSuchBeanDefinitionException` caused by a missing dependency bean.
- `BeanCurrentlyInCreationException` caused by circular dependencies.
- Classpath errors such as `ClassNotFoundException` or `NoSuchMethodError`.
- Package scanning, profile, or conditional configuration mismatches.
- Duplicate HTTP routes, duplicate mappings, or infrastructure conflicts outside the bean definition registry.

Proper root-cause analysis avoids toggling an unrelated property when troubleshooting.

## 6. Fixing Conflicts with Explicit Design

### 6.1. Assign Distinct Bean Names

Rewrite the Section 2 example as:

```java
package com.example.demo.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean("utcClock")
    public Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean("businessClock")
    public Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Now both definitions register cleanly because their names are distinct. A business service needing the business clock can choose it:

```java
package com.example.demo.service;

import java.time.Clock;
import java.time.LocalDate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BillingService {
    private final Clock clock;

    public BillingService(@Qualifier("businessClock") Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

`@Qualifier("businessClock")` tells readers exactly which bean is used. When multiple implementations serve distinct roles, distinct names are a clean choice.

### 6.2. Use `@Primary` When a Default Choice Is Needed

In the same configuration:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {
    @Bean("utcClock")
    public Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean("businessClock")
    @Primary
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

When injecting `Clock` without a qualifier, `businessClock` becomes the preferred candidate if no conflicting selection rule applies. If you want `utcClock`, use `@Qualifier("utcClock")`.

This illustrates **choosing between two differently named beans**. `@Primary` is not a bean definition overriding mechanism.

### 6.3. Create Beans Only When Configuration Conditions Match

If an application needs **only one implementation per environment**, use `@Profile` or conditional configuration to prevent registering both beans at once.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean("appClock")
    @Profile("dev")
    Clock devClock() {
        return Clock.systemDefaultZone();
    }

    @Bean("appClock")
    @Profile("prod")
    Clock prodClock() {
        return Clock.systemUTC();
    }
}
```

When exactly one of `dev` or `prod` is active, only the matching definition is registered. **If both profiles are active simultaneously**, the two same-named definitions can still collide; if neither is active, the `appClock` bean may be missing. That is why conditions must cover all supported application states cleanly.

Activate a profile via configuration:

```properties
spring.profiles.active=dev
```

In multi-environment deployments, the active profile is usually passed via environment variables or launch arguments rather than hardcoded to production in source code.

Another option is `@ConditionalOnProperty`, for example:

```java
@Configuration(proxyBeanMethods = false)
public class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditWriter auditWriter() {
        return new ConsoleAuditWriter();
    }
}
```

This snippet assumes `AuditWriter` and `ConsoleAuditWriter` are defined in the project and Spring Boot's `@ConditionalOnProperty` support is present. This condition controls **whether to register or skip** the bean based on `audit.enabled`, rather than allowing same-named overrides.

### 6.4. Remove Redundant Definitions or Narrow Scan Scope

If the same component is registered through two independent paths, see if one path can be removed. For example:

```java
@Component
public class MetricsPublisher {
}
```

alongside:

```java
@Configuration
public class MetricsConfiguration {
    @Bean("metricsPublisher")
    public MetricsPublisher metricsPublisher() {
        return new MetricsPublisher();
    }
}
```

Both aim to register a bean named `metricsPublisher`. Unless there is a specific reason to keep both, choose **one registration approach**. Keep `@Bean` when you need a special constructor or factory method; use `@Component` when standard scanning suffices.

If a component belongs to a module that should not run in the current application, adjusting scan scope, profiles, or imports fixes the root cause rather than enabling overriding application-wide.

## 7. `@ConditionalOnMissingBean`: How Auto-Configuration Yields Control

One feature making Spring Boot flexible is that **auto-configuration can "back off" when the application declares a matching bean itself**.

Example of a library default configuration:

```java
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockDefaultsConfiguration {

    @Bean("appClock")
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

The application can provide its own:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean("appClock")
    public Clock appClock() {
        return Clock.systemDefaultZone();
    }
}
```

In a **properly ordered auto-configuration flow**, Spring Boot processes application-declared beans first and evaluates auto-configuration conditions afterward. When a matching `Clock` bean already exists, the default `appClock` is skipped. Thus the application customizes behavior by supplying a bean, **without needing overriding enabled**.

Still, understand two subtleties:

1. `@ConditionalOnMissingBean` evaluates bean definitions **already processed at the moment the condition is checked**. If placed arbitrarily on two unordered user configurations, you cannot assume it always sees definitions registered later.
2. `@ConditionalOnMissingBean(Clock.class)` checks **type**; `@ConditionalOnMissingBean(name = "appClock")` checks **name**. These two checks are not equivalent, especially when an application has multiple same-type beans with different names.

For libraries or starters, use the auto-configuration mechanisms supported by your Spring Boot version and design conditions carefully. In regular applications, prefer **a single authoritative owner** for declaring business beans.

### 7.1. `@ConditionalOnMissingBean` Is Not "Absolute Collision Immunity"

If bean A is registered while the condition still holds, and another configuration appears later with the same name, a collision can still occur. Conditions inspect the registry only at evaluation time; they do not retroactively cancel earlier decisions when a new bean arrives later.

In Spring Boot's own auto-configurations, ordering, conditions, and scan boundaries are coordinated to avoid this; apply the same care when writing custom configurations.

## 8. When Can Overriding Be Used Intentionally?

While it should not be turned on to "mask" accidental bugs, overriding has legitimate niche use cases:

- A legacy system already relies on a well-defined **name-based bean replacement contract** maintained temporarily during migration.
- An integration framework has explicit bean registration rules where the overridden definition and its owner are well documented.
- A tightly controlled test or migration setup where the final definition per name can be verified.

Before enabling it, make sure you can state **which bean name is replaced, both definition sources, why replacement is needed, and what enforces registration order**. If you cannot answer those, resolve the conflict through renaming, conditions, bean selection, or removing redundant definitions.

### 8.1. Why Is This Especially Risky in Production?

Enabling overriding via the property applies **application-wide, not just to one conflicting bean**. Another change in the codebase or a dependency upgrade could accidentally introduce a new name collision that gets silently overwritten instead of failing fast.

Such bugs easily slip past code review and surface only in another environment with different active profiles or updated dependencies. In production, Spring Boot's fail-fast default catches duplicate-name configuration errors early.

### 8.2. Should Tests Rely on Overriding?

A test needing to replace a real bean with a fake or mock does not necessarily have to enable global overriding. You can:

- Use the **test bean mocking / test bean overriding** utilities supported by your Spring Test or Spring Boot version.
- Provide a `@Primary` bean for tests when two differently named beans fit the test setup.
- Use `@Profile("test")` with configuration so only one implementation registers.
- Slice the test context down to only the required configurations.

Bean mocking support in Spring Test/Boot evolves across versions; follow the API of your project's version. Do not treat a test passing with `spring.main.allow-bean-definition-overriding=true` as proof that the application's bean architecture is sound.

## 9. Distinguishing "Overriding" Across Different Spring Layers

The word *override* appears in many places, referring to different mechanisms:

| Phenomenon | Nature | Uses `spring.main.allow-bean-definition-overriding`? |
| --- | --- | --- |
| Java `@Override` | Subclass method implements/overrides inherited method | No |
| Two bean definitions with the same name in one registry | Duplicate name registration | Can be directly affected |
| `@Primary` | Selects preferred candidate for type-based injection | No |
| `@Qualifier` | Narrows or specifies injection candidate | No |
| `@ConditionalOnMissingBean` | Configuration applies only when no matching bean exists | Not an overriding mechanism |
| Child `ApplicationContext` has a bean with the same name as parent context | Child bean can shadow parent bean during child lookup | Not same-registry overriding |
| CLI Spring property overrides `application.properties` | Property source precedence | No |
| Test replacement/mocking | Replaces a bean within a test context | Depends on test API; distinct from global overriding |

For example, if a child context has a bean named `clock` and the parent context also has a bean named `clock`, the child lookup finding its own bean does not delete or replace the parent's definition. The two contexts have separate registries.

## 10. Diagnosing a Bean Definition Overriding Error

When the application fails to start and logs show `BeanDefinitionOverrideException`, instead of immediately enabling the override property, locate the **two definitions competing for the same bean name**.

### 10.1. Read the Bean Name and Both Sources in the Error

The message typically provides:

```text
Bean name: appClock
New definition: ... LocalClockConfiguration ...
Existing definition: ... UtcClockConfiguration ...
```

Class names, resource paths, or factory methods can be formatted differently across versions. Look for lines containing `Cannot register bean definition`, `already`, or the failure analysis section to see **which definition appeared first and which second** in that run.

### 10.2. Search for Declarations Using the Same Name

In your IDE, search across the project for declarations like:

```java
@Bean("appClock")
@Bean(name = "appClock")
@Component("appClock")
@Service("appClock")
```

Do not search only for the literal bean name string in Java files: a definition can come from XML, auto-configuration, or an external library. For default-named beans, also inspect **`@Bean` method names** and **component names derived from class names**.

### 10.3. Check Scan Scope and Imported Configurations

Verify:

1. Which package holds the `@SpringBootApplication` class and whether `scanBasePackages` is configured.
2. Whether a `@Configuration` class is scanned multiple times or imported from multiple sources.
3. Whether profiles, conditions, or module configs register the same bean name together.
4. Whether newly added dependencies/starters introduce additional default configurations.

Seeing the same class through multiple mechanisms does **not always** create two definitions: Spring includes deduplication checks where appropriate. When an actual error occurs, use the source details in the exception to trace each definition path.

### 10.4. Inspect Definitions When the Application Starts

In a running context, you can inspect metadata:

```java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;

ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

ConfigurableListableBeanFactory factory = context.getBeanFactory();
BeanDefinition definition = factory.getBeanDefinition("appClock");

System.out.println("Bean class: " + definition.getBeanClassName());
System.out.println("Factory method: " + definition.getFactoryMethodName());
System.out.println("Resource: " + definition.getResourceDescription());
System.out.println("Bean type: " + context.getBean("appClock").getClass().getName());
```

This is an illustrative snippet to place in `main()` or a diagnostic spot, assuming `DemoApplication` is the startup class and `appClock` exists. For `@Bean`-defined beans, `getBeanClassName()` may be `null` because the definition uses a **factory method** rather than declaring a bean class directly. `getResourceDescription()` is also not always populated.

If the application fails before context creation completes, `getBeanDefinition(...)` cannot run. In that case, rely on the startup exception, configuration source details, and logs.

### 10.5. Use the Conditions Report When Auto-Configuration Is Involved

When Spring Boot auto-configuration is involved, launch with:

```text
--debug
```

or set:

```properties
debug=true
```

Spring Boot prints the **Conditions Evaluation Report**, showing which auto-configurations applied or were skipped and why. This report helps analyze conditions like `@ConditionalOnMissingBean`, though it does not replace reading the exception naming the colliding bean.

### 10.6. Choosing a Fix by Root Cause

| Identified cause | Fix to consider |
| --- | --- |
| Two `@Bean` methods share a name due to copied config | Rename or remove the redundant definition |
| One `@Component` and one `@Bean` share a name | Pick one registration mechanism or separate names |
| Two implementations serve different roles | Assign distinct names, use qualifiers at injection points |
| Need one default implementation | Two distinct names + `@Primary` when appropriate |
| Need one implementation per environment | `@Profile`, `@ConditionalOnProperty`, or explicit conditions |
| Auto-configuration should yield to user bean | Design `@ConditionalOnMissingBean` and proper auto-configuration ordering |
| Component does not belong in the application | Adjust component scan, imports, or configuration conditions |
| Need to swap a bean in tests | Use the version-appropriate test configuration/mocking mechanism |

## 11. Practice Exercises

### Exercise 1 — Trigger an Override Error and Inspect the Message

Create a basic Spring Boot project with `DemoApplication` in `com.example.demo`. Add the two configuration classes both defining `@Bean("appClock")` from Section 2.

Start the application with default settings. Identify:

1. The contested bean name.
2. The names of both configuration classes and factory methods.
3. Whether the failure occurs during definition registration or when a controller uses `Clock`.

No web starter is needed to observe bean registration errors in this example.

### Exercise 2 — Enable Overriding and Explain the Outcome

Add to `application.properties`:

```properties
spring.main.allow-bean-definition-overriding=true
```

Restart and inspect the runtime `appClock` bean's type, time zone, and metadata source. Explain why the current run's outcome **is not a stable contract for choosing business time zones**.

After practicing, remove this property so you continue working with duplicate-name detection enabled.

### Exercise 3 — Fix Properly with Distinct Names and Qualifier

Rename the two bean definitions to `utcClock` and `businessClock`. Inject:

```java
public BillingService(@Qualifier("businessClock") Clock clock) {
    this.clock = clock;
}
```

Explain why two definitions of the same `Clock` type can coexist once their names differ. Next, try injecting without a qualifier to observe how Spring selects a candidate or reports ambiguity depending on configuration.

### Exercise 4 — Select a Bean with `@Primary`

Mark `businessClock` with `@Primary`, then inject `Clock` without a qualifier. Observe which implementation is chosen. Next, move `@Primary` to `utcClock` and compare. Why didn't this exercise need bean definition overriding?

### Exercise 5 — Simultaneously Active Profiles

Define two `@Bean("appClock")` methods with `@Profile("dev")` and `@Profile("prod")`. Launch sequentially with:

```properties
spring.profiles.active=dev
```

and:

```properties
spring.profiles.active=dev,prod
```

Predict what happens when both profiles are active while overriding is disabled. Fix the design so active profiles cannot accidentally produce two definitions with the same name.

### Exercise 6 — Classify Errors

Given three scenarios:

```text
A. Two different @Bean("emailSender") definitions registered together.
B. emailSenderA and emailSenderB exist, both of type Sender; constructor wants Sender.
C. Constructor wants Sender, but no Sender bean is registered.
```

Classify each into:

- Bean definition name collision.
- Multiple candidates by type.
- Missing candidate.

Propose the proper fix for each scenario and explain why enabling overriding alone cannot solve all three.

## 12. Takeaways When Designing Beans

**Bean definition overriding deals with registering duplicate *bean names* within a single registry.** When disabled, Spring Boot fails fast so you see the two conflicting definitions. When enabled, a later-registered definition can replace an earlier one, yet that does not clearly communicate which implementation business logic intends to use.

In most applications, the more maintainable path is **choosing clear bean names, limiting registration sources, using `@Qualifier`/`@Primary` to select among differently named beans, and using conditional configuration when only one implementation should exist**. For auto-configurations, rely on conditional mechanisms to yield to application-defined beans.

When encountering bean errors, ask in order: *Are two definitions sharing the same name? If not, are there multiple candidates of the same type? Or is there no candidate at all?* Answering those questions fixes the root cause rather than using `allow-bean-definition-overriding` to sweep conflicts under the rug.
