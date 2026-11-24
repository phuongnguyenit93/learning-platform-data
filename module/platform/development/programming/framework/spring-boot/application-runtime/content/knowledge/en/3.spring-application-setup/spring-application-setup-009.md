# Bean Definition Overriding and Circular Dependency Policies in Spring Boot

## 1. Why Do These Two Policies Matter When Configuring SpringApplication?

`SpringApplication` starts the `ApplicationContext`, prepares the `Environment`, loads configuration, registers `BeanDefinition`s, and creates required beans. Two errors commonly surface during this process: **two definitions sharing the same name** and **two or more beans requiring each other in a dependency cycle**. They differ in root cause, detection timing, and how to fix them.

Spring Boot provides two dedicated properties in the `spring.main` group:

| Property | Default in Spring Boot 2.6+, 3.x, and 4.x | What Does It Control? |
| --- | --- | --- |
| `spring.main.allow-bean-definition-overriding` | `false` | Whether registering a new `BeanDefinition` with the same **name** as an existing definition is permitted |
| `spring.main.allow-circular-references` | `false` | Whether the container is allowed to **attempt** resolving circular references while creating beans |

The first flag was set to `false` by default in Spring Boot 2.1; the second flag's default changed to `false` in Spring Boot 2.6. Older versions may behave differently, so always verify against the actual version in use. The proper configuration is normally to **keep both set to `false`** and fix duplicate names or dependency design whenever startup fails.

~~~yaml
# src/main/resources/application.yaml
spring:
  main:
    allow-bean-definition-overriding: false
    allow-circular-references: false
~~~

These are two `SpringApplication`/bean factory settings applied during startup; they are **not** flags that retroactively alter rules after beans have already been created. Putting them into YAML makes the policy explicit, even though declaring them is unnecessary since those are already the default values.

## 2. Bean Definition Overriding: A Conflict by Name, Not by Type

Spring manages bean definitions inside a registry, typically `DefaultListableBeanFactory`. Each definition has a **bean name** used for registration. Common registration sources include `@Component`/`@Service`/`@Repository`, `@Bean` inside `@Configuration` classes, XML configuration, or programmatic registration. For an unnamed `@Bean`, the default name is usually the method name; for component scanning, the default name is usually derived from the class name.

**Bean definition overriding** occurs when another definition is registered under a name that is already taken. When disallowed by policy, registration fails, typically with `BeanDefinitionOverrideException`. When permitted, a later definition can replace an earlier one, making the outcome depend on registration order or configuration layout. Avoid relying on that order to pick a business strategy.

### Example of a Bean Name Conflict

Consider a Spring Boot project with root package `com.example.override`; the following three files reside in this package.

**`src/main/java/com/example/override/OverrideApplication.java`**

~~~java
package com.example.override;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OverrideApplication {
    public static void main(String[] args) {
        SpringApplication.run(OverrideApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/override/LocalConfig.java`**

~~~java
package com.example.override;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LocalConfig {
    @Bean("deliveryMode")
    String localDeliveryMode() {
        return "local";
    }
}
~~~

**`src/main/java/com/example/override/RemoteConfig.java`**

~~~java
package com.example.override;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RemoteConfig {
    @Bean("deliveryMode")
    String remoteDeliveryMode() {
        return "remote";
    }
}
~~~

Two differently named methods both register `deliveryMode`. When Spring Boot loads both configurations and the default policy disables overriding, the application fails to complete startup; logs typically state that bean `deliveryMode` is already defined and overriding is disabled. The error does not come from both returning `String`, but from **duplicate bean names**. If `spring.main.allow-bean-definition-overriding=true` is set, the application may get past the duplicate-name error; however, you should not assume the winning bean is guaranteed to be `"local"` or `"remote"` without controlling registration and testing.

A similar conflict can arise when two distinct `@Service("billingService")` classes exist, or when a `@Component("gateway")` class and a `@Bean("gateway")` method coexist. Also distinguish special-case framework handling between `@Bean` and component scanning within the same configuration; do not extrapolate from one special case that all duplicate-name definitions are allowed.

### Three Commonly Confused Concepts

1. **Duplicate bean name:** two definitions attempt to register the same identifier. The overriding policy governs this case.
2. **Multiple beans of the same type:** `EmailSender` and `SmsSender` both implement `MessageSender` with **two different names**. They are allowed to coexist; when injecting a single `MessageSender`, Spring may report `NoUniqueBeanDefinitionException` if a single candidate cannot be determined.
3. **Method overriding in Java:** `@Override` on a method is a Java language feature; it has nothing to do with bean definition overriding.

`@Qualifier` and `@Primary` solve **selecting a bean when injecting by type**; they do not make two definitions with the same name valid. `@Order` orders components in certain contexts such as lists/chains, and is likewise not a fix for definition conflicts.

### Fixing the Conflict Properly

If two implementations are genuinely needed, **give them two different names**, inject with a qualifier, or designate a default candidate with `@Primary`. For example:

~~~java
public interface MessageSender {
    void send(String text);
}
~~~

~~~java
import org.springframework.stereotype.Component;

@Component("emailSender")
public class EmailSender implements MessageSender {
    @Override
    public void send(String text) {
        System.out.println("EMAIL: " + text);
    }
}
~~~

~~~java
import org.springframework.stereotype.Component;

@Component("smsSender")
public class SmsSender implements MessageSender {
    @Override
    public void send(String text) {
        System.out.println("SMS: " + text);
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final MessageSender sender;

    public NotificationService(@Qualifier("emailSender") MessageSender sender) {
        this.sender = sender;
    }

    public void notifyUser(String message) {
        sender.send(message);
    }
}
~~~

The snippets above illustrate the design: place each type in an appropriate file and package and import `MessageSender` in a real project. In the example, `@Qualifier("emailSender")` selects the exact bean for the constructor parameter; it is not used to allow two beans with the same name.

If only one configuration should be active per environment, use `@Profile` or `@ConditionalOnProperty` to register only the matching configuration. Test cases where no profile is active or multiple profiles are active simultaneously: if both definitions still get registered with the same name, the conflict still happens. In auto-configuration, many default beans are declared conditionally with `@ConditionalOnMissingBean` so they automatically **back off** when the user provides a suitable bean. That is conditional selection, **different** from allowing a later definition to override an earlier one.

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return text -> System.out.println("DEFAULT: " + text);
}
~~~

The snippet above describes logic in an auto-configuration-style conditional configuration; it must be positioned properly in configuration processing (typically after application beans). Do not sprinkle `@ConditionalOnMissingBean` arbitrarily across peer configurations and assume the result is order-independent.

## 3. Circular Dependencies: A Conflict in the Initialization Graph

A bean can depend on another bean via constructor, setter, or field injection. If following dependencies leads back to the bean currently being created, you have a **circular dependency**.

~~~mermaid
flowchart LR
  A["OrderService"] -->|"constructor"| B["PaymentService"]
  B -->|"constructor"| C["RiskService"]
  C -->|"constructor"| A
~~~

A cycle does not have to involve only two beans. A chain `A → B → C → A` is also a cycle. This structure usually indicates two responsibilities are too tightly coupled or callback logic has not been separated from initialization.

### Example of Constructor Injection That Cannot Be Resolved Automatically

The following two classes are discovered by Spring via component scanning:

**`src/main/java/com/example/cycle/PricingService.java`**

~~~java
package com.example.cycle;

import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final PromotionService promotionService;

    public PricingService(PromotionService promotionService) {
        this.promotionService = promotionService;
    }
}
~~~

**`src/main/java/com/example/cycle/PromotionService.java`**

~~~java
package com.example.cycle;

import org.springframework.stereotype.Service;

@Service
public class PromotionService {
    private final PricingService pricingService;

    public PromotionService(PricingService pricingService) {
        this.pricingService = pricingService;
    }
}
~~~

To create `PricingService`, `PromotionService` must already exist; to create `PromotionService`, `PricingService` must already exist. Neither bean can finish its constructor first. Spring typically reports a creation-chain failure with `BeanCurrentlyInCreationException` as the core cause (possibly wrapped by `UnsatisfiedDependencyException`). **Even with `spring.main.allow-circular-references=true` enabled, this constructor-to-constructor cycle still cannot be resolved automatically**.

### Why Does Setter Injection Sometimes Differ from Constructor Injection?

In cases where a singleton can receive dependencies after object instantiation, Spring Framework historically supported **early references**: the container could instantiate A, expose an early reference to help construct B, and then finish assigning properties and completing the lifecycle. That only works under specific configurations and conditions; proxies/AOP, differing scopes, factory methods, or initialization-time operations can make the cycle unresolvable. Seeing an object before its initialization finishes is also a source of hard-to-reproduce bugs.

Therefore, `allow-circular-references=true` means **"attempt to resolve supported cycles"**, not "every cycle is valid". Starting with 2.6, Spring Boot blocks cycles by default instead of implicitly relying on early references.

The two registration and initialization policies are completely distinct: enabling bean overriding does not resolve an A ↔ B cycle; enabling circular references does not resolve duplicate bean name errors.

## 4. Sustainable Fix: Reversing Dependency Direction

Suppose `PricingService` needs to calculate discounts, while `PromotionService` calls back into `PricingService` to fetch order details. Identify what the real shared capability is: a **discount calculation policy** does not need to know about all of `PricingService`. Extract an interface and make dependencies unidirectional.

~~~mermaid
flowchart LR
  A["PricingService"] --> B["DiscountPolicy"]
  C["FixedDiscountPolicy"] -.implements.-> B
  D["Promotion workflow"] --> A
~~~

A business cycle can be split into a higher-level orchestration step, communicating via events or callbacks only when truly necessary. Avoid creating two services that both depend directly on each other and call each other through constructors.

### Complete Java 17+ Spring Boot Example Without Any Cycle

Create a Maven project from Spring Initializr, choosing Java 17 or newer, the **Spring Boot Starter** dependency (no Web or Actuator needed for a bean lifecycle example), and package `com.example.policy`. Place these four files under `src/main/java/com/example/policy/`.

**`PolicyApplication.java`**

~~~java
package com.example.policy;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PolicyApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PricingService pricing) {
        return args -> System.out.println(
            "TOTAL=" + pricing.priceAfterDiscount(100)
        );
    }
}
~~~

**`DiscountPolicy.java`**

~~~java
package com.example.policy;

public interface DiscountPolicy {
    int discountFor(int originalPrice);
}
~~~

**`FixedDiscountPolicy.java`**

~~~java
package com.example.policy;

import org.springframework.stereotype.Component;

@Component
public class FixedDiscountPolicy implements DiscountPolicy {
    @Override
    public int discountFor(int originalPrice) {
        return 10;
    }
}
~~~

**`PricingService.java`**

~~~java
package com.example.policy;

import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final DiscountPolicy discountPolicy;

    public PricingService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }

    public int priceAfterDiscount(int originalPrice) {
        return Math.max(0, originalPrice -
            discountPolicy.discountFor(originalPrice));
    }
}
~~~

Run in the directory containing the `pom.xml` generated by Spring Initializr:

~~~bash
mvn spring-boot:run
~~~

Alongside Spring Boot's startup info, the program prints one line produced by `CommandLineRunner`:

~~~text
TOTAL=90
~~~

Explanation: `FixedDiscountPolicy` implements `DiscountPolicy` and does not need `PricingService`; `PricingService` only needs the discount policy; `CommandLineRunner` receives the already-created service and then executes. The graph has no back edges. Both flags in `spring.main` remain at their default `false`, yet the application starts cleanly. The formula here illustrates dependency injection; real systems need proper currency rules and validation beyond simple integers.

A real project should have a context startup test to catch cycles and bean collisions, plus dedicated unit tests for discount logic; the example above focuses on bean lifecycle and requires no HTTP controller.

## 5. Deferral and Compatibility Measures: Use with Caution

When immediate refactoring is not possible, several mechanisms defer dependency lookup. They have different semantics and must not be mistaken for thorough architectural fixes.

### `@Lazy` at the Injection Point

~~~java
@Service
class ReportService {
    private final ExportService exportService;

    ReportService(@Lazy ExportService exportService) {
        this.exportService = exportService;
    }
}

@Service
class ExportService {
    private final ReportService reportService;

    ExportService(ReportService reportService) {
        this.reportService = reportService;
    }
}
~~~

The snippet above requires importing `org.springframework.context.annotation.Lazy` and `org.springframework.stereotype.Service`. `@Lazy` on a constructor parameter tells Spring to inject a **lazy-lookup proxy** for `ExportService`; this can allow creating `ReportService` without constructing the real `ExportService` bean yet. However, if a constructor, `@PostConstruct`, or an early call dereferences the proxy, the failure can still happen. Even after startup succeeds, two services calling each other without a termination condition still cause infinite business recursion. Breaking the dependency cycle remains the preferred choice.

### `ObjectProvider<T>`

~~~java
import org.springframework.beans.factory.ObjectProvider;

@Service
class JobCoordinator {
    private final ObjectProvider<JobHandler> handlerProvider;

    JobCoordinator(ObjectProvider<JobHandler> handlerProvider) {
        this.handlerProvider = handlerProvider;
    }

    void execute() {
        handlerProvider.getObject().handle();
    }
}
~~~

A provider defers lookup until `getObject()` is called and is useful for optional dependencies or lazy lookups. If `JobHandler` in turn needs `JobCoordinator`, you must ensure the handler is only retrieved after the context and related beans are ready. A provider does not eliminate a circular relationship at the design level.

### Re-enabling Cycle Support as a Transitional Step

~~~yaml
spring:
  main:
    allow-circular-references: true
~~~

Or pass via CLI at startup:

~~~bash
java -jar target/app.jar --spring.main.allow-circular-references=true
~~~

Depending on the cycle type, this can help a legacy system using setter/field injection start up during refactoring. It does **not** fix constructor injection cycles, gives no guarantees with AOP/proxies, and does not replace startup/test verification. Avoid letting a transitional workaround become permanent production configuration.

### Changes That Do Not Fix the Root Cause

- `spring.main.lazy-initialization=true` may push the error to when the bean is used; it does not eliminate a dependency cycle.
- `@DependsOn` controls initialization order and cannot resolve a cycle where each bean truly needs the other to finish constructing; circular `depends-on` configurations can even trigger more explicit errors.
- Turning constructor injection into field injection just to get past startup can hide bidirectional coupling and make testing harder.
- Calling `ApplicationContext.getBean(...)` anywhere to bypass declaring dependencies can turn a clear error into a hard-to-trace service locator.
- `@Configuration(proxyBeanMethods=false)` adjusts proxying of `@Bean` methods within a configuration class; it does not fix duplicate bean names or service dependency cycles.

## 6. Setting Policies via SpringApplication and External Configuration

These flags belong to startup configuration. They can be controlled via properties:

~~~properties
# src/main/resources/application.properties
spring.main.allow-bean-definition-overriding=false
spring.main.allow-circular-references=false
~~~

Or set via `SpringApplication` before `run(...)`:

~~~java
package com.example.policy;

import org.springframework.boot.SpringApplication;

public final class ExplicitPolicyLauncher {
    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(PolicyApplication.class);
        app.setAllowBeanDefinitionOverriding(false);
        app.setAllowCircularReferences(false);
        app.run(args);
    }
}
~~~

This is an **alternative launcher** for the same `PolicyApplication` in section 4; there is no need to run both `main` methods simultaneously. Spring Boot also supports the corresponding setters on `SpringApplicationBuilder`. Values are evaluated when creating the context, so do not mutate flags from an already-initialized bean and expect the container to redo earlier registration/initialization.

Example with CLI arguments:

~~~bash
java -jar target/app.jar \
  --spring.main.allow-bean-definition-overriding=false \
  --spring.main.allow-circular-references=false
~~~

The command above illustrates **syntax**; replace `target/app.jar` with your actual artifact path. On Windows PowerShell, put the command on one line or use PowerShell's line continuation character instead of Bash's `\`.

With external configuration, sources such as command-line arguments can override values in `application.yaml` following standard `PropertySource` precedence. Therefore, when environments behave differently, inspect the actual runtime arguments, environment variables, and profile config data. A plain Spring Framework container may have different defaults; do not extrapolate `SpringApplication` policies from raw `DefaultListableBeanFactory` defaults.

## 7. Root-Cause Diagnosis Procedure When Startup Fails

### A. Duplicate Bean Definition

Common symptom:

~~~text
... BeanDefinitionOverrideException ...
... bean 'deliveryMode' ... already defined ...
... overriding is disabled ...
~~~

Exact wording varies by Spring Boot version, class names, and configuration ordering. Investigation steps:

1. Read the **bean name** in the error, e.g., `deliveryMode`.
2. Inspect the two definition sources pointed out by the log: `@Bean` method, component scan, `@Import`, library configuration.
3. Determine whether two implementations actually need to coexist or only one configuration is valid for the current profile.
4. Prefer renaming/adding qualifiers, removing duplicate registrations, or applying explicit registration conditions.
5. If using `@ConditionalOnMissingBean`, check auto-configuration ordering and existing conditions.
6. Only consider enabling overriding as a specifically justified exception, backed by tests verifying the actual active bean.

**Distinguishing sign:** two different classes of the same type with different names usually lead to candidate selection (`NoUniqueBeanDefinitionException`), not `BeanDefinitionOverrideException`.

### B. Dependency Cycle

Common symptom is a chain of bean names in the log showing arrows/a loop, or cause `BeanCurrentlyInCreationException`:

~~~text
pricingService -> promotionService -> pricingService
~~~

Investigation steps:

1. Identify the edges of the cycle from constructor, setter, or field injection.
2. Check which methods need to call upward from a lower layer to a higher layer.
3. Distinguish **constructor** cycles from cycles where properties can be set after construction; both should be fixed structurally.
4. Extract shared responsibilities into an independent interface/service, or move coordination to an orchestration layer with strictly one-way dependencies.
5. Add context startup tests and business call-path tests; startup succeeding does not prove there is no runtime recursion.
6. If using a temporary deferral measure, document the dereference point, initialization safety, and the plan to eliminate the cycle.

**Distinguishing sign:** renaming a bean or adding `@Qualifier` can pick the right dependency, yet cannot eliminate an A → B → A graph if constructors still require each other.

### C. App Fails Only on Deploy While Running Locally Works

Check these differences: active profiles, enabled modules/dependencies, scanned/imported `@Configuration` classes, CLI properties or environment variables, and lazy/eager bean creation state. Two profiles active together can enable two configurations assumed to be mutually exclusive. A service only used at runtime can cause a hidden cycle to surface after startup when lazy resolution is used.

## 8. Quick Decision Table

| Scenario | Primary Symptom | Preferred Solution | What Not to Confuse |
| --- | --- | --- | --- |
| Two `@Bean("cacheClient")` from different sources | `BeanDefinitionOverrideException` | Register only one bean conditionally or give distinct names | `@Primary` does not fix duplicate names |
| Two implementations of the same interface, different names | `NoUniqueBeanDefinitionException` on injection | `@Qualifier`, `@Primary`, or inject a collection when appropriate | No need to enable bean overriding |
| A's constructor needs B, B's constructor needs A | Uncreatable cycle | Redesign dependency direction | `allow-circular-references=true` does not cure constructor cycles |
| A and B use bidirectional setter/field injection | Cycle blocked by Boot during bean creation | Refactor; as a transition, can try the circular flag | Allowing cycle resolution attempts does not guarantee all cases |
| Startup passes after adding `@Lazy`/provider | Error may shift to usage time | Inspect the call graph again and actually break the cycle | Passing startup does not mean call recursion is safe |
| Starter's default bean "does not appear" | Auto-config condition not met | Read the condition evaluation report | Auto-config back-off differs from definition overriding |
| Two configs meant for separate environments | Duplicate bean when profiles combine | `@Profile`/`@ConditionalOnProperty` with profile matrix tests | Multiple profiles can be active simultaneously |

## 9. Structural Principles for Application Design

- Use **constructor injection** for mandatory dependencies: missing beans or dependency cycles surface early, and objects hold required dependencies immediately upon creation.
- Name beans intentionally when multiple implementations of the same type exist; select candidates explicitly at injection points.
- Keep layers with explainable dependency direction: API/controller → application service → domain policy/repository/gateway; do not let lower layers constructor-inject higher-layer services to call backward.
- Separate concerns among **bean registration**, **candidate selection on injection**, and **object initialization**. Each failure category has its own investigation path.
- Keep `allow-bean-definition-overriding=false` and `allow-circular-references=false` in standard operational configs; if a compatibility exception exists, document the rationale and test specifically.
- When upgrading Spring Boot versions, read release notes regarding bean initialization policies, because an application that started under old defaults may expose duplicate names or dependency cycles after upgrading.

## 10. Knowledge Self-Check

**Question 1.** Two beans `emailSender` and `smsSender` both implement `MessageSender`. Do you need to enable `allow-bean-definition-overriding`? **No**, because their names differ. When injecting a single `MessageSender`, you need to handle candidate selection.

**Question 2.** Two different `@Bean` methods both declare the name `metricsClient`. Does adding `@Primary` to one method fix the error? **No**, the error is duplicate-name registration, not injection priority.

**Question 3.** Two services inject each other via constructors. Will setting `spring.main.allow-circular-references=true` guarantee it runs? **No**, constructor-to-constructor cycles cannot complete on their own.

**Question 4.** Adding `@Lazy` to one dependency edge lets startup succeed. Can the cycle be considered eliminated? **Not yet**, it only defers lookup; dereferencing the proxy too early or reciprocal call logic can still fail.

**Question 5.** A starter does not create a default bean because the user already declared a bean of the same type. Is this always bean definition overriding? **No**, auto-configuration can use `@ConditionalOnMissingBean` to avoid registering the default bean in the first place.

### Official Documentation

- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): the two keys `spring.main.allow-bean-definition-overriding` and `spring.main.allow-circular-references` along with their default values.
- [Spring Boot — SpringApplication API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/SpringApplication.html): `setAllowBeanDefinitionOverriding` and `setAllowCircularReferences`.
- [Spring Framework — Bean Overview / Overriding Beans](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean identifiers and definition overriding.
- [Spring Framework — Dependency Injection / Circular Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): analysis of cycles in constructor injection.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): conditional default bean mechanisms.
- [Spring Boot 2.6 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.6-Release-Notes): default change for circular references.