# Distinguishing @Primary, @Qualifier, and Preventing Bean Registration with Conditions

In Spring Boot, multiple beans implementing the same interface can coexist at the same time. Two questions must be distinguished:

- **Is the bean registered into the ApplicationContext?** This is a *bean registration* problem; `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and other conditions can prevent a bean definition from being registered.
- **When multiple beans already exist, which bean does Spring inject at a dependency point?** This is a *candidate selection* problem; `@Primary` and `@Qualifier` handle this situation.

For example, an application has `emailSender` and `smsSender`, both of type `MessageSender`. `@Primary` can make `emailSender` the default choice, while `@Qualifier` can select `smsSender` in a specific service. **Both beans still exist.** Conversely, `@ConditionalOnMissingBean` can prevent the default bean from being registered at all when the application has already provided its own bean.

## 1. Comparison Table

| Tool | Typical Usage Place | Timing / Effect | Removes Other Beans from Context? |
| --- | --- | --- | --- |
| **@Primary** (Spring Framework) | `@Bean` or `@Component` class | Prioritizes a candidate when injecting a **single-value** dependency by type | **No** |
| **@Qualifier** (Spring Framework) | Constructor, field, setter parameter; bean metadata | Narrows down candidates at a **specific injection point** | **No** |
| **@ConditionalOnMissingBean** (Spring Boot) | `@Bean` in auto-configuration | Registers a fallback bean **only when no matching bean exists yet** at condition evaluation time | Fallback bean is **not registered** if condition is false |
| **@ConditionalOnBean** (Spring Boot) | `@Bean` or configuration class | Registers only when dependent beans are already present | Can prevent the conditional bean |
| **@ConditionalOnProperty** (Spring Boot) | `@Bean` or configuration class | Registers only according to configuration property values | Can prevent the conditional bean |

**Core distinction:** `@Primary` and `@Qualifier` decide *which bean to pick* among available candidates; `@Conditional…` annotations decide *whether to put a bean definition into the context at all*.

## 2. Two Phases in the Spring Lifecycle

~~~text
Component scan, @Bean configurations, Spring Boot auto-configuration
    |
    v
Evaluate @Conditional... while processing bean definitions
    | true                         | false
    v                              v
Register bean definition           Skip that bean definition
    |
    v
Instantiate beans and resolve dependency injection
    |
    +-- @Qualifier: narrow eligible candidates at the injection point
    +-- @Primary: prioritize a candidate among eligible matches when one bean is needed
    v
Injection succeeds or fails with missing/ambiguous dependency error
~~~

This diagram focuses on the topic; Spring's autowiring mechanism also has other rules, such as dependency name and priority. However, **`@Primary` does not remove beans from the context**, **`@Qualifier` does not create or delete beans**, and registration conditions must be processed **before** the dependency can be injected.

## 3. @Primary: Default Candidate, Not a Bean-Disabling Mechanism

Place `@Primary` on a `@Bean` or a bean class to prioritize it when multiple eligible beans share the same type and a consumer requires only **one** dependency. If an injection point specifies a `@Qualifier` matching another bean, that specified bean can still be selected instead of the primary one.

- A single `@Primary` among matching candidates normally resolves ambiguity when injecting an interface.
- Two candidates both marked `@Primary` can still cause `NoUniqueBeanDefinitionException`.
- When injecting `List<MessageSender>`, `MessageSender[]`, or `Map<String, MessageSender>`, non-primary beans can still appear in the collection; `@Primary` does not filter them out.
- `@Primary` is not a way to avoid instantiating expensive beans, avoid duplicate bean names, or replace default auto-configuration back-off.

### Complete Runnable Example with Java 17+ and Spring Boot

Create a Maven project with the two files below. The example uses Spring Boot 3.3.5 and JDK 17 or higher.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bean-choice-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

**src/main/java/com/example/demo/BeanChoiceApplication.java**

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@SpringBootApplication
public class BeanChoiceApplication implements CommandLineRunner {
    private final MessageSender defaultSender;
    private final MessageSender selectedSms;

    public BeanChoiceApplication(
            MessageSender defaultSender,
            @Qualifier("smsSender") MessageSender selectedSms) {
        this.defaultSender = defaultSender;
        this.selectedSms = selectedSms;
    }

    public static void main(String[] args) {
        SpringApplication.run(BeanChoiceApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println("Default: " + defaultSender.send("Hello"));
        System.out.println("Qualified: " + selectedSms.send("Hello"));
    }
}

interface MessageSender {
    String send(String content);
}

@Configuration(proxyBeanMethods = false)
class SenderConfiguration {
    @Bean("emailSender")
    @Primary
    MessageSender emailSender() {
        return content -> "EMAIL -> " + content;
    }

    @Bean("smsSender")
    MessageSender smsSender() {
        return content -> "SMS -> " + content;
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Alongside startup logs, the two lines printed by the `run` method are:

~~~text
Default: EMAIL -> Hello
Qualified: SMS -> Hello
~~~

**Why?** The constructor requests two `MessageSender` beans. The `defaultSender` parameter has no qualifier; `emailSender` is the `@Primary` candidate so it is injected. The `selectedSms` parameter declares `@Qualifier("smsSender")`, picking the exact bean named `smsSender`, even though `emailSender` is marked primary. Both beans are created/registered. If you call `ApplicationContext.getBeansOfType(MessageSender.class)`, you can observe both names `emailSender` and `smsSender`.

**Try changing these to verify:**

1. Remove `@Primary` on `emailSender`: the `defaultSender` parameter becomes ambiguous between two beans of the same type; Spring usually throws `NoUniqueBeanDefinitionException` when starting the application.
2. Add `@Qualifier("emailSender")` directly to the `defaultSender` parameter: Spring explicitly chooses `emailSender` without needing `@Primary`.
3. Also add `@Primary` to `smsSender`: there are two primary candidates, so `@Primary` no longer picks a unique one for `defaultSender`.
4. Inject `List<MessageSender>`: both `emailSender` and `smsSender` are still candidate elements; `@Primary` does not restrict the list to only `emailSender`.

## 4. @Qualifier: Explicit Selection per Injection Point

For a service that must use SMS, place `@Qualifier` on the constructor parameter:

~~~java
public NotificationService(
        @Qualifier("smsSender") MessageSender sender) {
    this.sender = sender;
}
~~~

This is an **illustrative snippet inside a `NotificationService` class that already declares a `sender` field**, not a standalone Java file.

The string `"smsSender"` can match the bean name from `@Bean("smsSender")` or matching qualifier metadata. In large applications, you can create custom qualifier annotations to avoid scattering implementation name strings throughout the codebase. Constructor injection keeps dependencies explicit and easy to test.

**When `@Qualifier` and `@Primary` appear together:** `@Qualifier` narrows down the candidate set according to the injection point's requirement. If only one bean remains eligible, that bean is selected even if another bean carries `@Primary`. If multiple beans still satisfy the qualifier, `@Primary` can still be used **within the remaining candidate set**. Therefore, saying "`@Qualifier` always overrides `@Primary`" is inaccurate.

**Limitation:** `@Qualifier` does not prevent other implementations from being instantiated, is not a feature toggle, and does not fix whether a bean exists. If a bean was not registered due to a failing condition, `@Qualifier` cannot summon it either.

## 5. @ConditionalOnMissingBean: Creating a Fallback That the Application Can Replace

This is a key pattern in **Spring Boot Auto Configuration**. A library provides a default implementation; an application using the library can declare a custom implementation. The library should create the default **only when no matching implementation exists yet**.

The following code snippets belong to **separate files in the library and application**, not a single standalone Java program.

**In the library: AuditPort.java**

~~~java
package com.example.audit;

public interface AuditPort {
    String record(String event);
}
~~~

**In the library: AuditAutoConfiguration.java**

~~~java
package com.example.audit;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AuditAutoConfiguration {
    @Bean("defaultAuditPort")
    @ConditionalOnMissingBean(AuditPort.class)
    public AuditPort defaultAuditPort() {
        return event -> "DEFAULT: " + event;
    }
}
~~~

To have Spring Boot auto-load the auto-configuration in the library, add the file **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** with the content:

~~~text
com.example.audit.AuditAutoConfiguration
~~~

**In the consuming application: AuditCustomization.java (optional)**

~~~java
package com.example.app;

import com.example.audit.AuditPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditCustomization {
    @Bean("customAuditPort")
    public AuditPort customAuditPort() {
        return event -> "CUSTOM: " + event;
    }
}
~~~

The application must declare a dependency on the library; the `AuditCustomization` class must be within component-scan scope or imported. Spring Boot schedules auto-configuration **after** application-provided configurations, allowing the `@ConditionalOnMissingBean` condition to see the custom bean.

| Application Configuration State | When Evaluating @ConditionalOnMissingBean(AuditPort.class) | Resulting Bean |
| --- | --- | --- |
| No `AuditCustomization` declared | No matching `AuditPort` yet | Registers **defaultAuditPort** |
| `AuditCustomization` present | **customAuditPort** of type `AuditPort` already exists | **Does not register defaultAuditPort**; keeps `customAuditPort` |

The second case is completely different from `@Primary`: here **`defaultAuditPort` does not exist at all**; there is no situation where both default and custom are created and custom is picked at injection time.

### Notes on Ordering and Checked Types

- `@ConditionalOnMissingBean` belongs to **Spring Boot**, package `org.springframework.boot.autoconfigure.condition`.
- The condition is checked against bean definitions **already processed at that moment**. If placed arbitrarily on two ordinary configurations, results can depend on ordering; this is why the annotation fits best in auto-configurations that run after application configuration.
- When one auto-configuration depends on the outcome of another auto-configuration, you can declare ordering with `@AutoConfiguration(after = …)` or `@AutoConfiguration(before = …)`.
- If the library's contract is the `AuditPort` interface, use **`@ConditionalOnMissingBean(AuditPort.class)`** and return `AuditPort` in the `@Bean` method, rather than checking only a concrete implementation. Spring also supports conditions by `name` and adjusting parent/child context search scope when needed.
- Putting `@Primary` on `customAuditPort` **does not make `defaultAuditPort` vanish on its own** if the default bean lacks the right condition. Primary belongs to the injection phase; conditions belong to the registration phase.

## 6. Property-Based Conditions and Related Conditions

If the goal is to create a bean **only when a feature is enabled**, use `@ConditionalOnProperty`:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
AuditPort remoteAuditPort() {
    return event -> "REMOTE: " + event;
}
~~~

This is an **illustrative method inside a `@Configuration` class**, requiring the appropriate `ConditionalOnProperty`, `Bean`, and `AuditPort` imports.

~~~properties
feature.audit.enabled=true
~~~

When the property equals `true`, the `remoteAuditPort` bean is registered. When `false` or absent (`matchIfMissing = false`), that bean is **not** registered. If a service still injects this bean as a required dependency with no fallback, the application context can fail to start: turning off registration **does not automatically adapt** every place consuming the bean.

Some closely related conditions:

- **@ConditionalOnBean(X.class)**: registers only when a matching bean of type `X` is already seen.
- **@ConditionalOnClass(X.class)**: registers only when class `X` is on the classpath; suitable for optional integrations.
- **@ConditionalOnSingleCandidate(X.class)**: checks that there is a single matching candidate, or multiple candidates with one `@Primary` candidate under the appropriate conditions.
- **@Profile("prod")** from Spring Framework: registers beans/configurations according to active profiles.

All of these tools decide **whether to register a bean definition**, unlike `@Qualifier`/`@Primary` which select a bean at an injection point.

## 7. Making the Right Design Decision

| Desired Behavior | Appropriate Solution | Explanation |
| --- | --- | --- |
| Have both email and SMS; default to email | `@Primary` on `emailSender` | Both beans coexist; email is preferred for single-value injection by type |
| A specific service always uses SMS | `@Qualifier("smsSender")` on constructor | Local decision for one dependency |
| Library has a default `AuditPort`, application can supply another `AuditPort` | `@ConditionalOnMissingBean(AuditPort.class)` in auto-configuration | Default bean is not registered when a custom bean already exists |
| Register an integration only when feature is enabled | `@ConditionalOnProperty` | Condition based on `application.properties`/`yaml` |
| A service needs to run all implementations | Inject `List<Interface>` or `Map<String, Interface>` | Do not expect `@Primary` to filter the list |
| An implementation should not be instantiated at all in this environment | `@ConditionalOnProperty`, `@Profile`, or appropriate condition | Prevent registration from the start |

**Combined example:** `emailSender` is always registered and marked `@Primary`; `smsSender` is registered only when `feature.sms.enabled=true`. When the feature is enabled, `@Qualifier("smsSender")` picks SMS where needed. When the feature is disabled, a service that still requires `@Qualifier("smsSender")` can fail with a missing dependency error. You must also make the consumer conditional or design an explicit fallback. `@ConditionalOnProperty` does not automatically alter the consumer's constructor.

## 8. Common Mistakes and Diagnosis

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type, unable to choose a single eligible candidate | Specify `@Qualifier` at the injection point or `@Primary` for the default |
| Added `@Primary` yet the other bean is still created | `@Primary` does not block registration | Use an appropriate condition for the bean that should not exist |
| `@Qualifier("x")` cannot find the bean | Wrong name/qualifier or the bean was excluded by a condition | Check the bean name and registration conditions |
| `@ConditionalOnMissingBean` does not back off for custom bean | Wrong checked type or unsuitable configuration ordering | Check interface, `@Bean` return type, auto-configuration placement, and ordering |
| Two beans with duplicate **names** cause registration/override error | Name conflict, distinct from two beans sharing an interface | Use distinct names or fallback conditions; `@Primary` does not solve this |
| Disabling a bean via `@ConditionalOnProperty` breaks application startup | Consumer still requires a mandatory dependency | Provide a fallback or make the consumer conditional |
| Both candidates are `@Primary` | No single primary remains | Keep only one primary or use an explicit qualifier |

You can use **`ApplicationContext.getBeansOfType(MyInterface.class)`** to check the actual count/names of registered beans. For auto-configurations, enable Spring Boot's condition report (e.g., running the app with **`--debug`**) to see why conditions matched or did not match. When debugging, ask in order: **"Was the bean registered?"**, then **"Why did the injection point pick this bean?"**

## 9. Self-Check Questions

**1.** `A` and `B` share the same type; `A` has `@Primary`, and a constructor injects `@Qualifier("B")`. Which bean is chosen?  
**Answer:** `B` if bean `B` exists and matches the qualifier. `A` still exists in the context.

**2.** You want a library not to create a default implementation when the app already provides an implementation of the same interface. What do you use?  
**Answer:** `@ConditionalOnMissingBean(Interface.class)` in auto-configuration. `@Primary` does not prevent the default from being registered.

**3.** Does `List<Interface>` contain only the `@Primary` bean?  
**Answer:** No. `@Primary` primarily resolves single-value autowiring; other implementations can still appear in the collection.

**4.** Why can putting `@ConditionalOnMissingBean` in regular configuration be unstable?  
**Answer:** The condition is evaluated against bean definitions processed up to that point; configuration processing order can cause it not to see the custom bean yet.

**5.** A property disables SMS, yet a service still requires injecting `@Qualifier("smsSender")`. What can happen?  
**Answer:** If no matching bean exists, the dependency cannot be satisfied and Spring may fail on startup. Design the consumer and fallback accordingly.

**Remember:** `@Primary` = prioritize default candidate; `@Qualifier` = pick specific candidate at injection point; `@ConditionalOnMissingBean` = register default only when no matching bean exists yet; `@ConditionalOnProperty` = register only when property condition holds. Determine whether your problem is *registration* or *injection* before picking an annotation.
