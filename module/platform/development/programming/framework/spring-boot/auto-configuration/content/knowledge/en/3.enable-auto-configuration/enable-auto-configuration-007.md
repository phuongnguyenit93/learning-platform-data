# User Configuration and When Default Configuration Is Evaluated in Spring Boot

## 1. The Problem: How Does Spring Boot Know When to Back Off?

Spring Boot provides **auto-configuration** so applications can use infrastructure components without having to write every `@Configuration` and `@Bean` manually. Yet when a developer has already declared a suitable bean, many auto-configurations will **back off** instead of registering the default bean.

For example: Boot can create an appropriate `DataSource` when JDBC and relevant settings are present; if the application has already supplied a `DataSource` in a way compatible with the auto-configuration's conditions, the default configuration may not be registered. This rule is commonly expressed via `@ConditionalOnMissingBean`.

Three questions must be answered separately:

1. **What is user configuration?** `@Configuration` classes, `@Bean` methods, components, and bean definitions supplied by the application, including conditional beans.
2. **When does Boot evaluate default configuration?** During configuration processing and bean definition registration, auto-configuration is evaluated after ordinary bean definitions declared by the application.
3. **What does "evaluated after" mean?** Conditions can recognize an existing bean definition and decide not to register the default bean; it **does not mean** the application's bean was already instantiated before the default bean.

Learning goal of this lesson: read scenarios where "the application declares a bean → auto-config backs off", identify the limits of `@ConditionalOnMissingBean`, and avoid confusing **bean definition registration** with **bean instance creation**.

## 2. How Is User Configuration Recognized?

"User configuration" in this context is not just `application.properties`. It also includes **bean definitions** provided by the application.

### 2.1. Common Sources

| Source | Example | Significance for Auto-Configuration |
| --- | --- | --- |
| Application `@Configuration` class | `@Configuration class AppConfig` | `@Bean` methods are processed into bean definitions |
| `@Bean` method | `@Bean MessageFormatter customFormatter()` | Can cause `@ConditionalOnMissingBean(MessageFormatter.class)` not to match |
| Component scanning | `@Service class BillingService` | Can register a bean of that type before auto-config evaluates conditions |
| `@Import` and programmatic registration | `@Import(OtherConfig.class)`, registrar | Can supply definitions, though **registration phase** in the lifecycle must be checked |
| Environment-based configuration | `@Profile("prod")`, `@ConditionalOnProperty` | Determines whether the application's bean is registered in the current environment |

In the example below, "user bean" means a **bean declared by the application**, while "default bean" means a **bean from auto-configuration when conditions permit**. They typically implement the same interface or provide the same kind of service.

Note: A property such as `demo.custom=true` **does not create a bean by itself**. In the example, the property merely makes `@ConditionalOnProperty` on the application's `@Bean` method match; **the `@Bean` method itself** is the source that registers the bean.

### 2.2. Bean Definition vs. Bean Instance

Spring's `ApplicationContext` holds metadata and instructions on how to create beans. Given:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
```

Spring can know the **name**, **return type**, and **creation recipe** of the `paymentGateway` bean beforehand from its bean definition, while the `paymentGateway()` method **has not yet been called to create the actual object**.

This snippet is illustrative only, not a self-running program: `PaymentGateway` and `StripePaymentGateway` are hypothetical application types.

Therefore, the condition "does a matching bean already exist?" is normally a check on **known bean definitions**, not an operation forcing Spring to instantiate every bean just to compare.

## 3. When Auto-Configuration Is Evaluated: After Application Definitions

`@SpringBootApplication` enables `@EnableAutoConfiguration` alongside component scanning and Spring configuration. In Spring Boot 3.x, auto-configuration candidates are published via the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

At startup, Spring processes configuration classes, component scans, imports configurations, and registers bean definitions; the `DeferredImportSelector` mechanism used by auto-configuration ensures it is evaluated after ordinary application configuration.

The key point is that **Spring Boot ensures auto-configuration is applied after user-declared bean definitions have been added**, so bean-aware conditions inside auto-config can rely on those definitions. This is the foundation for *back-off* behavior.

Visualize the **logical** sequence as follows:

```text
@SpringBootApplication
         |
         v
Read application config + component scan + @Import
         |
         v
Register application bean definitions
         |
         v
Evaluate auto-configuration candidates and conditions
         |                               |
         | matching bean exists          | no matching bean yet
         v                               v
  Auto-config backs off           Register default bean definition
         \                               /
          \                             /
           v                           v
             Final set of bean definitions
                         |
                         v
           Instantiate beans and wire dependencies (DI)
                         |
                         v
                 Application runs
```

The diagram separates decisions; it does **not** portray every Spring Framework callback as a rigid linear list. Certain conditions may be checked in different configuration processing phases. Auto-configuration may be **discovered** from the imports file early; **evaluating conditions and registering bean definitions** is a separate matter.

**Do not infer:** "user configuration always instantiates bean instances first"; "every bean registered programmatically later is visible to auto-config from the start"; or "registering later means overwriting the user's definition".

## 4. The Most Important Condition: `@ConditionalOnMissingBean`

Spring Boot commonly uses:

```java
@Bean
@ConditionalOnMissingBean(MessageFormatter.class)
MessageFormatter defaultMessageFormatter() {
    return target -> "DEFAULT: " + target;
}
```

This is an illustrative snippet inside an auto-configuration class. It says: **register this bean only if conditions show there is no matching `MessageFormatter` bean** within the search scope.

If the class/method has other conditions such as `@ConditionalOnClass` or `@ConditionalOnProperty`, all relevant conditions must also be satisfied.

### 4.1. Conditions Rely on What Has Been Processed

Spring Boot documentation notes that `@ConditionalOnBean` and `@ConditionalOnMissingBean` depend on bean definitions **already processed up to the point of evaluation**. Therefore, the recommended safe usage is placing them in **auto-configurations**, where deferred imports ensure application bean definitions are processed first.

Typical example:

```java
// Application declares:
@Bean
MessageFormatter userMessageFormatter() {
    return target -> "CUSTOM: " + target;
}

// Auto-configuration provides default:
@Bean
@ConditionalOnMissingBean(MessageFormatter.class)
MessageFormatter defaultMessageFormatter() {
    return target -> "DEFAULT: " + target;
}
```

Expected outcome when both configurations are properly registered: Spring sees the definition of `userMessageFormatter` and **does not register** `defaultMessageFormatter`. It does not need to execute `userMessageFormatter()` first to know it should back off.

If this same condition were scattered across ordinary `@Configuration` classes, configuration processing order could make results unpredictable: at the moment the condition runs, the other bean might **not be registered yet**.

### 4.2. Bean-Type Conditions vs. Bean-Name Conditions Differ

| Condition Form | What Must Be Absent | Example |
| --- | --- | --- |
| `@ConditionalOnMissingBean(MessageFormatter.class)` | Bean of matching type `MessageFormatter` | Regardless of the default bean name |
| `@ConditionalOnMissingBean(name = "messageFormatter")` | Bean with **name** `messageFormatter` | Another bean with the same interface yet a different name does not necessarily fail this condition |
| `@ConditionalOnBean(MessageFormatter.class)` | Requires a `MessageFormatter` bean already exists | Suits configurations depending on another bean |
| `@ConditionalOnClass(SomeLibrary.class)` | Class on classpath, **not a bean** | Having a dependency does not imply having a bean |
| `@ConditionalOnProperty(prefix = "demo", name = "enabled", havingValue = "true")` | Property matching expected value | Enable/disable feature via Environment |

Do not mix up **class name**, **bean name**, **bean type**, and **property name**. Auto-configuration backs off only if its **specific condition** matches what the application has provided.

### 4.3. Return Type of `@Bean` Matters

Bean-type conditions typically rely on the **type metadata** of the bean definition. When declaring a factory method, specify a sufficiently concrete return type:

```java
// Has specific type metadata, supporting bean-type conditions:
@Bean
FastCache fastCache() {
    return new FastCache();
}

// Too generic, may prevent type-based conditions
// from recognizing the bean at check time:
@Bean
Object fastCache() {
    return new FastCache();
}
```

These two methods are **two separate illustrative alternatives**, not to be placed together in one class due to identical names. `FastCache` is a hypothetical type. The issue is not the runtime type returned, but **the type Spring can infer from the factory method signature when evaluating conditions**. In interface-based APIs, the return type should also consider compatibility/contracts with actual conditions.

### 4.4. When Multiple Conditions Apply

An auto-configuration may require several conditions simultaneously:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.client.RemoteClient")
@ConditionalOnProperty(prefix = "feature.remote", name = "enabled",
        havingValue = "true")
class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteGateway.class)
    RemoteGateway remoteGateway() {
        // Illustrative code only; requires actual implementation and dependency.
        return new RemoteGateway();
    }
}
```

This code is **not a standalone compilable example**; `RemoteGateway` is an illustrative type. Takeaway: missing SDK class, disabled property, or an existing `RemoteGateway` can all prevent the default bean from **being registered**. You cannot look solely at `@ConditionalOnMissingBean` to explain the full cause.

## 5. Runnable Example: User Bean Beats Default Configuration

The following example uses **Java 17+**, Maven, and **Spring Boot 3.3.13**. It verifies two runs:

- When `demo.custom=false`: the application has not registered a user `MessageFormatter`; auto-config supplies the default bean.
- When `demo.custom=true`: the application's bean is registered; auto-config detects it and does not create the default.

### 5.1. Project Structure

```text
user-config-order-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   ├── MessageFormatter.java
    │   │   └── UserMessageConfiguration.java
    │   └── library/autoconfigure/
    │       └── MessageAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

We place the app in `com.example.app` and auto-config in `com.example.library.autoconfigure` so **auto-configuration is outside the default component scanning scope**. It is brought in only through the auto-config candidate list.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>user-config-order-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. `src/main/java/com/example/app/MessageFormatter.java`

```java
package com.example.app;

@FunctionalInterface
public interface MessageFormatter {
    String format(String target);
}
```

This is the **contract** provided by both the application and auto-config. A `@FunctionalInterface` annotation does not register a bean itself.

### 5.4. `src/main/java/com/example/app/UserMessageConfiguration.java`

```java
package com.example.app;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserMessageConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "custom",
            havingValue = "true")
    MessageFormatter userMessageFormatter() {
        return target -> "CUSTOM: " + target;
    }
}
```

The class sits under the root package `com.example.app`, so `@Configuration` is discovered by component scanning. When `demo.custom=true`, this method creates a **bean definition of type `MessageFormatter`**. When the property is false, the `userMessageFormatter` bean definition is not registered.

Do not think of these two states as Spring creating a bean and then deleting it. The condition is evaluated during configuration processing to decide **which definitions will be added to the container**.

### 5.5. `src/main/java/com/example/library/autoconfigure/MessageAutoConfiguration.java`

```java
package com.example.library.autoconfigure;

import com.example.app.MessageFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class MessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageFormatter.class)
    MessageFormatter defaultMessageFormatter() {
        return target -> "DEFAULT: " + target;
    }
}
```

The auto-configuration has a `@Bean` method of the same type, yet **registers it only** if the container has no matching `MessageFormatter` bean when the condition is evaluated.

In a real project, a starter should put the `MessageFormatter` contract in a shared API module rather than letting auto-config depend on the application's package. In this single-module exercise, keeping all files in one Maven project makes it easy to run and observe the mechanism.

### 5.6. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showResult(
            MessageFormatter formatter, ApplicationContext context) {
        return args -> {
            System.out.println("MESSAGE=" + formatter.format("Spring"));
            System.out.println("USER_BEAN="
                    + context.containsBean("userMessageFormatter"));
            System.out.println("DEFAULT_BEAN="
                    + context.containsBean("defaultMessageFormatter"));
        };
    }
}
```

`ApplicationRunner` runs only after the context has started successfully. The `MessageFormatter formatter` parameter illustrates DI by bean type; in both scenarios below there is **only one `MessageFormatter` bean**.

### 5.7. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
demo.custom=false
```

For this project, non-web mode ensures the example does not start a server waiting for requests.

### 5.8. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.library.autoconfigure.MessageAutoConfiguration
```

The path and file name must be exact. In Spring Boot 3.x, auto-configurations are declared using this file. Merely being on the classpath is not enough for Boot to scan auto-configs from an arbitrary package; the imports list is the officially supported candidate source.

### 5.9. Packaging and Running Scenario A — Using Default

In the directory containing `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/user-config-order-demo-1.0.0.jar
```

Lines printed by the example itself:

```text
MESSAGE=DEFAULT: Spring
USER_BEAN=false
DEFAULT_BEAN=true
```

**Explanation:** `demo.custom=false` does not satisfy `@ConditionalOnProperty(havingValue="true")`, so `userMessageFormatter` is not registered. When auto-configuration evaluates `@ConditionalOnMissingBean(MessageFormatter.class)`, it sees **no matching bean yet**, and therefore registers `defaultMessageFormatter`.

This is the meaning of **default**: used when the user has not provided a matching choice, not a bean "always created upfront" and then replaced afterward.

### 5.10. Running Scenario B — Application Provides Bean

Keep the same JAR and pass the setting via command line:

```bash
java -jar target/user-config-order-demo-1.0.0.jar --demo.custom=true
```

Lines printed by the example itself:

```text
MESSAGE=CUSTOM: Spring
USER_BEAN=true
DEFAULT_BEAN=false
```

**Explanation:**

1. The command-line property source is placed into `Environment` by Spring Boot with appropriate precedence, making `demo.custom=true`.
2. While processing application-declared configuration, the condition on `UserMessageConfiguration.userMessageFormatter()` matches, so the `userMessageFormatter` bean definition is registered.
3. When evaluating auto-config, `@ConditionalOnMissingBean(MessageFormatter.class)` **does not match** because a bean definition of type `MessageFormatter` is already visible.
4. Spring **does not register** the `defaultMessageFormatter` bean. When creating `ApplicationRunner`, DI supplies the user's bean.

Note that point 3 refers to **bean definitions**; it does not require the user bean to be instantiated before the condition is checked.

### 5.11. Observing Conditions in Logs

You can enable the condition report:

```bash
java -jar target/user-config-order-demo-1.0.0.jar --demo.custom=true --debug
```

Look for `MessageAutoConfiguration` or `defaultMessageFormatter` in the *Condition Evaluation Report*. When `demo.custom=true`, the missing-bean condition is logged as **did not match** because a `MessageFormatter` already exists; when the property is false, it matches. Exact line labels and wording may vary by Spring Boot version and logging configuration.

## 6. "Evaluated Later" Differs from "Instantiated Later": Three Time Layers

### 6.1. Phase 1 — Candidate Discovery

Boot discovers the list of auto-config class names from `AutoConfiguration.imports`. Having a candidate **listed in imports** only means Boot can consider it. The candidate may still be eliminated by filters/conditionals and create no beans.

### 6.2. Phase 2 — Condition Processing and Bean Definition Registration

Spring evaluates the relevant conditions and decides whether to put bean definitions into the context. For `@ConditionalOnMissingBean`, **already-processed definitions** are the deciding information.

Practical rules to apply:

- Application bean definitions are processed before auto-config, allowing auto-config to back off by bean type or bean name.
- If a bean is created only by **another auto-configuration**, a missing-bean condition may depend on **ordering between auto-configurations**.
- If a bean is registered **late via a special mechanism**, you cannot assume earlier conditions will see it.

This is why you should not scatter `@ConditionalOnMissingBean` arbitrarily across ordinary configuration classes to "resolve contention".

### 6.3. Phase 3 — Bean Instance Creation and Injection

Spring creates non-lazy singletons during context refresh, resolving constructor dependencies, callbacks, and `@DependsOn` relationships.

**Auto-configuration ordering decides only the order of applying/registering bean definitions**, not the order of bean instance instantiation. Bean X declared in an auto-config appearing before auto-config Y may still have to wait for bean Y to be created first if X depends on Y.

Therefore, the idea that "the default bean is evaluated later = it is instantiated with `new` after every user bean" is inaccurate.

### 6.4. State Diagram for a Bean Type

```text
User bean definition of type T present at evaluation time?
                 |
           +-----+------+
           |            |
          Yes           No
           |            |
    @ConditionalOnMissingBean(T)
    does not match     matches (*)
           |            |
    Do not register  Register
    default T        default T
           |            |
           +-----+------+
                 |
         Instantiate and DI afterward
```

`(*)` assumes other conditions are also satisfied, such as `@ConditionalOnClass`, `@ConditionalOnProperty`, and environment conditions. The diagram does not imply the default bean is always created whenever no user bean exists.

## 7. Avoid Confusing Back-Off with Bean Overriding and Primary Selection

There are three distinct phenomena:

| Phenomenon | Description | Example |
| --- | --- | --- |
| **Conditional back-off** | Default **is not registered** when a matching user bean already exists | `@ConditionalOnMissingBean(MessageFormatter.class)` |
| **Bean definition overriding** | A later definition with the same **bean name** replaces an existing one, depending on container settings and policy | Bean name collision cases; Spring Boot disables overriding by default |
| **Candidate selection at injection** | Multiple beans coexist, yet DI picks one bean via qualifier or primary | `@Primary`, `@Qualifier` |

In the runnable example in section 5, `DEFAULT_BEAN=false` in scenario B is **back-off**. It is **not** the default bean being created and then overwritten by the user.

`@Primary` **does not make auto-config back off** if the auto-config condition ignores that bean's type/name. `@Primary` only helps choose one matching bean when multiple candidates exist during DI. If multiple beans implement the same interface and cannot be disambiguated, Spring can fail with *NoUniqueBeanDefinitionException*.

Spring Boot sets `spring.main.allow-bean-definition-overriding=false` by default across modern versions (including Boot 3.x). Do not enable this flag to patch duplicate bean definition errors before understanding the registration sources. Proper back-off is usually clearer and safer than overriding.

## 8. Two Mutually Dependent Auto-Configurations Need Ordering

Example: auto-config A registers `CacheClient`; auto-config B registers `CacheMetrics` **only if `CacheClient` exists**. If B is processed before A, `@ConditionalOnBean(CacheClient.class)` in B may not see A's bean definition.

In Spring Boot, you can specify ordering between auto-configs:

```java
@AutoConfiguration(after = CacheClientAutoConfiguration.class)
public class CacheMetricsAutoConfiguration {
    // Bean conditions are evaluated after related definitions from A.
}
```

This is only an **illustrative snippet**, as `CacheClientAutoConfiguration` and imports are not provided in this document. When you do not want a direct class reference, you can use `afterName = "com.example.CacheClientAutoConfiguration"` where appropriate.

Related tools in Boot 3.x include:

- `@AutoConfiguration(before = ...)` and `@AutoConfiguration(after = ...)`;
- `beforeName` and `afterName` when ordering is declared by class name;
- `@AutoConfigureBefore` / `@AutoConfigureAfter`;
- `@AutoConfigureOrder` for general auto-config ordering relationships.

**Limitation:** these options order **auto-config bean definitions**; they do not guarantee *instance creation* order. Use dependency injection and `@DependsOn` if the problem is genuinely bean creation order.

If two auto-configs both carry `@ConditionalOnMissingBean(CacheClient.class)` and both can produce a bean of the same type, the design must establish a clear **preferred default**. Auto-config ordering can decide which one is evaluated first; critical behavior should not rely on undeclared ordering.

## 9. Cases Requiring Caution

### 9.1. User Bean Exists Only Under a Profile/Condition

```java
@Bean
@Profile("production")
MessageFormatter prodFormatter() {
    return target -> "PROD: " + target;
}
```

When the `production` profile is inactive, that method **registers no bean definition**, so the default can match. Auto-config does not "see" beans from inactive profiles as active beans. The code above is an illustrative snippet inside an existing configuration class, not a standalone project.

### 9.2. User Has a Bean with the Same Name, Yet a Different Type

A condition checking `name = "reporter"` and a condition checking `value = Reporter.class` reach two different conclusions. A **name-based** condition does not look solely at the Java type, while a **type-based** condition does not look solely at the bean name. Always read each auto-config's exact condition.

### 9.3. Bean Defined Too Late

If an extension registers a bean after `@ConditionalOnMissingBean` has already been evaluated, that bean's presence does not travel back in time to cancel the earlier registration decision. Therefore, code creating beans through late customization must understand the lifecycle of `BeanDefinitionRegistryPostProcessor`, configuration processing, and auto-config, rather than assuming any bean eventually present in the context was visible from the start.

### 9.4. Bean Resides in a Parent Context

`@ConditionalOnBean` and `@ConditionalOnMissingBean` can inspect the `ApplicationContext` hierarchy. The `search` attribute controls scope, such as checking only the current context. If an application uses parent/child contexts, the default might not appear as you predict when looking only at local beans.

### 9.5. Using `@ConditionalOnMissingBean` on Regular Configuration Classes

In ordinary application configuration, definition insertion order may be insufficient to guarantee the condition sees every expected bean. Spring Boot recommends restricting these bean conditions mainly to **auto-configuration**, where application definitions are processed first. If the goal is default configuration for a library, build an official auto-config and register it via the imports file.

### 9.6. Automatically Scanning Auto-Config Classes

Do not annotate auto-config with `@Component` and place it inside component scanning "just to be safe". Auto-config is designed to be imported via Boot's mechanism; scanning it like an application component can alter ordering and condition behavior from the original design. Spring Boot documentation advises **not letting auto-config be picked up by component scanning**.

### 9.7. Changing a Property at Runtime Does Not Immediately Swap the Bean

Conditions for **registering beans** are typically evaluated when building/refreshing the context. Changing a value in a file or environment after the app is running **does not guarantee** the bean definition will be replaced immediately. Refresh/dynamic reconfiguration mechanisms, if needed, are a separate topic. The section 5 example required **restarting the application** with a different argument to observe the two configurations.

## 10. Debugging Workflow When a Default Bean Is Missing

Suppose you expect an auto-config bean yet do not see it. Follow this workflow:

1. **Find the candidate:** Check whether the auto-config class is actually in `AutoConfiguration.imports` of the right version dependency/JAR; is it excluded by `@SpringBootApplication(exclude=...)` or `spring.autoconfigure.exclude`?
2. **Read class-level conditions:** Is an SDK missing on the classpath, property wrong, web application type mismatched, resource missing, or profile wrong?
3. **Read `@Bean`-level conditions:** Is there a `@ConditionalOnMissingBean`? Does it check **type**, **name**, annotation, or parent/child context?
4. **List existing bean definitions:** Does the user already have a matching `@Bean` or component? Is the type declared in the method signature specific enough for Spring to recognize?
5. **Check ordering between auto-configs:** If the condition requires a bean from another auto-config, is ordering specified properly?
6. **Inspect the condition report:** Enable `--debug` to view the *Condition Evaluation Report*. A "did not match" outcome may be the exact right behavior, not a bug.
7. **Only then inspect DI:** Is a bean truly missing, or are there multiple beans, wrong `@Qualifier`, unexpected `@Primary`, or circular dependencies?

If `spring-boot-starter-actuator` is present and endpoints are appropriately configured for exposure, `/actuator/conditions` provides condition information. This endpoint is not open to all requests by default; avoid exposing sensitive diagnostic data publicly.

A quick pattern for reading failures:

- **Default absent, user bean exists:** usually intended back-off.
- **Both default and user bean exist:** check whether the condition checked **the right type/name**, or whether definitions were processed in an unexpected phase.
- **No bean exists at all:** inspect class/property conditions, imports, profiles, and whether the user bean was actually registered.
- **Context fails due to duplicate bean name:** that is a bean definition conflict; do not confuse it with `@ConditionalOnMissingBean` when conditions were not declared appropriately.
- **Multiple beans of the same type, injection fails:** this is a DI candidate selection issue, not necessarily auto-config failing to run.

## 11. Common Misconceptions

| Statement | Assessment | Explanation |
| --- | --- | --- |
| "Auto-config runs only after all application beans have been instantiated." | **False** | The key guarantee concerns **bean definition registration**, not instantiating objects first |
| "`@ConditionalOnMissingBean` checks every bean that will ever exist in the future." | **False** | The condition relies on bean definitions already processed up to the point of evaluation |
| "I declared a bean of the same type, so the default was created and then overwritten." | **Usually false** | If the default has a missing-bean condition, it may **not be registered from the start** |
| "Just putting `@Primary` stops auto-config from creating its bean." | **False** | Primary affects candidate selection during DI; back-off comes from registration conditions |
| "Two auto-configs need instance creation ordering, so use `after`." | **Wrong tool** | `after` mainly changes application/definition order; creation order depends on bean dependencies |
| "`@ConditionalOnMissingBean` is safe in any `@Configuration`." | **Not guaranteed** | Bean conditions are sensitive to definition processing order; Boot recommends using them in auto-config |
| "Being named in `AutoConfiguration.imports` guarantees the default bean will exist." | **False** | Imports lists candidates; conditions can still fail to match |
| "Changing `demo.custom` while the app runs automatically swaps default and user beans." | **Not by default** | Bean registration conditions are evaluated when building the context |

## 12. Practice Questions

**Question 1.** `@Bean MessageFormatter userFormatter()` is registered from user `@Configuration`. Auto-config has `@ConditionalOnMissingBean(MessageFormatter.class)`. Does auto-config create the default?

**Answer:** In normal configuration without special conditions, **no**. The missing-bean condition sees a definition of type `MessageFormatter` and backs off.

**Question 2.** Does `userFormatter()` have to be called before evaluating that condition?

**Answer:** **No**. Bean conditions inspect already-processed metadata/bean definitions, without needing to instantiate every object first.

**Question 3.** Why might Bean A supplied by auto-config X not be seen by `@ConditionalOnBean(A.class)` in auto-config Y?

**Answer:** Y may have been processed before definition A from X was registered. Check `before`/`after` relationships between auto-configurations and other conditions.

**Question 4.** If two beans of the same type still coexist, how does `@Primary` help?

**Answer:** It helps Spring pick a preferred candidate during DI, yet **does not prevent registering** the other bean.

**Question 5.** In the example, when `demo.custom=true`, why is `DEFAULT_BEAN=false`?

**Answer:** The user bean definition was registered first. When auto-config evaluated missing-bean, the condition failed so the default bean **was not added to the context**.

**Question 6.** If `spring.autoconfigure.exclude` excludes `MessageAutoConfiguration` while `demo.custom=false`, what happens to the example?

**Answer:** Neither user formatter nor default formatter exists; `ApplicationRunner` requires `MessageFormatter` and startup **fails due to a missing dependency**. Excluding an auto-config does not automatically create a replacement.

## 13. Reference Documentation

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): the default model and how user configuration replaces auto-configuration pieces.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): definition ordering, `@ConditionalOnMissingBean`, bean conditions, imports files, and testing auto-config.
- [Spring Boot — ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): condition semantics and evaluation scope based on processed bean definitions.

**Key takeaway:** Spring Boot tries to **give application configuration the first say**, then uses auto-configuration to fill in what is missing conditionally. "Before" and "after" here relate primarily to **evaluating and registering bean definitions**, not constructor execution or bean instantiation order.
