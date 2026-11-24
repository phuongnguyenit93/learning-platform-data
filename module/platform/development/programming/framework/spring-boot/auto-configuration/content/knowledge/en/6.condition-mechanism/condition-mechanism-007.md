# ConfigurationCondition: Distinguishing PARSE_CONFIGURATION and REGISTER_BEAN in Spring Boot

## 1. The Problem: Not Every Condition Should Be Evaluated at the Same Time

Spring Boot auto-configuration relies heavily on `@Conditional...` annotations. They decide **whether a configuration class or a bean is eligible to be registered into the Spring container**. Yet "when is the condition evaluated?" is an important question, because before the container finishes building, the information available at each stage is not the same.

Distinguish two cases:

1. **Checking environment or conditions determinable early.** For example: does a property enable the feature, or does a dependent class exist on the classpath? We want to know before Spring deeply parses an ineligible configuration.
2. **Checking whether a bean definition has already been registered.** For example: has the user already supplied a `PaymentGateway`, so auto-configuration can decide whether to create a default? This must wait until relevant configurations have been parsed and appropriate bean definitions processed.

Spring Framework expresses this distinction through the interface:

```java
org.springframework.context.annotation.ConfigurationCondition
```

It extends `Condition` and adds `getConfigurationPhase()` to choose the **evaluation phase**. The `ConfigurationCondition.ConfigurationPhase` enum has two values:

- `PARSE_CONFIGURATION`: evaluated when **parsing the `@Configuration` class**.
- `REGISTER_BEAN`: evaluated when **registering beans** (after configuration classes have been parsed).

This is a **lifecycle mechanism for constructing bean definitions**. It does **not** correspond to "before constructor" and "after constructor", is not two runtime phases of the application, and is not a bean priority level.

## 2. Going from `Condition` to `ConfigurationCondition`

### 2.1. `@Conditional` Connects Annotations to Check Logic

In Spring Framework, `@Conditional` accepts one or more classes implementing `Condition`:

```java
@Conditional(SomeCondition.class)
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    // @Bean ...
}
```

This is an illustrative code snippet, not a standalone compilable program: `SomeCondition` must be defined.

The basic contract of `Condition`:

```java
public interface Condition {
    boolean matches(ConditionContext context,
                    AnnotatedTypeMetadata metadata);
}
```

When `matches(...)` returns `true`, that condition **matches**. When it returns `false`, the configuration element carrying `@Conditional` is not eligible to be registered in the applicable context. If there are multiple conditions, all must be satisfied.

Two important parameters:

- `ConditionContext` provides access to `Environment`, `BeanDefinitionRegistry`, `ConfigurableListableBeanFactory` (when available), `ResourceLoader`, and `ClassLoader`. Availability/usability depends on evaluation **timing**.
- `AnnotatedTypeMetadata` provides **metadata** of the annotated class or method. You can read attributes from the annotation via the metadata API without needing to create a bean.

A plain `Condition` has no method returning a specific phase. To specify that a condition is evaluated only at the appropriate moment for a `@Configuration` class, implement `ConfigurationCondition`.

### 2.2. The Additional Contract of `ConfigurationCondition`

Conceptually:

```java
public interface ConfigurationCondition extends Condition {
    ConfigurationPhase getConfigurationPhase();
}
```

`ConfigurationPhase` is a nested enum inside `ConfigurationCondition`; it has the two values from section 1.

Syntactically valid skeleton example when implementing it:

```java
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

final class SampleCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context, AnnotatedTypeMetadata metadata) {
        return true;
    }
}
```

The snippet above is an **illustrative class**; it needs to be placed in an appropriate Java file/package and should not be used as a business condition since `matches` is always true. Even so, the two methods clearly show: `getConfigurationPhase` chooses **when to evaluate**, `matches` decides **whether it matches**.

Do not mistake `ConfigurationCondition` for a new annotation to place directly on a class. It is a **Java interface** implemented by a class; the annotation placed on configuration classes remains `@Conditional(...)` or Spring Boot's composed annotations.

## 3. The Two Phases According to Spring Framework Javadoc

| Characteristic | `PARSE_CONFIGURATION` | `REGISTER_BEAN` |
| --- | --- | --- |
| Primary timing | When Spring **parses** a `@Configuration` class | When Spring **registers** a regular bean definition, after parsing |
| Question to ask | "Should this configuration enter the configuration tree?" | "Given processed definitions, should this bean be added?" |
| Suitable data | `Environment`, classpath, metadata/configuration-independent facts | `BeanDefinitionRegistry`, presence of already processed bean definitions |
| If unmatched on config class | The config class can be excluded right at the parse step | Does not block the class's **parse step**; can prevent registering corresponding beans/config afterward |
| Conceptual example | Toggle an entire integration by property or classpath | Back off based on a bean the application already supplied |
| Not synonymous with | Creating singletons early | Running constructors, dependency injection, or ApplicationRunner |

Javadoc of `PARSE_CONFIGURATION`: the condition should be evaluated when a `@Configuration` class is parsed; if it does not match **at that point**, the configuration class is not added to the parsing process.

Javadoc of `REGISTER_BEAN`: the condition should be evaluated when adding a regular (non-`@Configuration`) bean; this condition **does not prevent configuration parsing**, and at evaluation time `@Configuration` classes have already been parsed.

**Important nuance:** do not infer that every bean in the application has already been **instantiated** at `REGISTER_BEAN`, or that the registry already includes every bean that later extensions will register. "Config classes parsed" and "all bean instances exist" are two different events. For bean-dependent conditions, Spring Boot cautions that only bean definitions **processed up to the time of evaluation** are visible.

### 3.1. Mental Diagram (Not the Entire Internal Lifecycle)

```text
@SpringBootApplication / @Configuration / auto-config candidates
                         |
                         v
             Parse configuration metadata
                         |
          PARSE_CONFIGURATION conditions
                  /             \
              false             true
               |                 |
         Skip config       Continue parsing
                               |
                               v
                   Determine bean definitions
                               |
                 REGISTER_BEAN conditions
                        /             \
                    false             true
                     |                 |
            Do not add bean      Add bean definition
                     \                 /
                      \               /
                       v             v
                      BeanFactory / Bean registry
                                |
                                v
                   Create bean instances, DI,
                  post-processing and run app
```

The diagram depicts **two logical decision gates**. Do not treat it as a rigid linear sequence for every implementation, because Spring also involves component scanning, imports, registry post-processors, nested conditions, scoped beans, and Boot's own optimization steps.

### 3.2. Choosing the Phase Based on Input Data

A check that only reads `Environment` can be safe in the parse phase. Conversely, checking "does the container already have bean X?" is usually **unsuitable** for the parse phase because many bean definitions have not yet been added to the registry.

Example of **what not to do**:

```java
@Override
public ConfigurationPhase getConfigurationPhase() {
    return ConfigurationPhase.PARSE_CONFIGURATION;
}

@Override
public boolean matches(ConditionContext context,
                       AnnotatedTypeMetadata metadata) {
    return context.getBeanFactory() != null
            && context.getBeanFactory().containsBean("userGateway");
}
```

This snippet intentionally places a bean lookup in **too early a phase**, not a standalone runnable condition. At parse time, `userGateway` may not have been registered or even created yet. The condition risks returning false even though the application ends up having the corresponding bean.

If the real goal is to check for a bean, usually use `@ConditionalOnBean` or `@ConditionalOnMissingBean` provided by Boot, or a condition with an appropriate phase at the registration step. Do not write manual conditions to duplicate a capability already built into Boot.

## 4. Connection to Familiar Spring Boot Conditions

### 4.1. Classpath-Based Conditions

`@ConditionalOnClass` checks whether a class is on the classpath:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
class ExternalClientAutoConfiguration {
    // ...
}
```

This is an illustrative snippet. Classpath information is typically useful **before parsing or loading optional configurations**. Spring Boot has a mechanism to filter class-based conditions early using metadata; hence class-based conditions are a natural example of a parse-phase concern.

Do not claim every class-based condition is evaluated strictly once or through a single method; Boot can also optimize at the candidate-filtering stage. What matters is **the ability to evaluate early when relying only on classpath/metadata**.

### 4.2. Bean-Definition-Based Conditions

`@ConditionalOnMissingBean` needs to know which beans have already been declared:

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultGateway() {
    return new InMemoryPaymentGateway();
}
```

This is an illustrative snippet; the `PaymentGateway` and `InMemoryPaymentGateway` types must be defined in the project. Spring Boot uses `OnBeanCondition` with **phase `REGISTER_BEAN`** for the group of conditions that check beans.

Boot documentation warns: `@ConditionalOnBean` and `@ConditionalOnMissingBean` only know about definitions processed up to evaluation time. Therefore they are recommended for use **in auto-configuration**, so user-declared configurations are processed first and defaults can yield.

Here is why:
- Choosing a phase is **not changing priority/`@Order`**.
- `REGISTER_BEAN` does not automatically guarantee two arbitrary auto-configurations are evaluated in your preferred order; `@AutoConfiguration(after = ...)` or `afterName` is still needed if auto-config B's condition depends on definitions from auto-config A.
- If a bean is added late by a custom mechanism, an already evaluated condition does not automatically "re-evaluate" to remove/replace an already registered bean.

### 4.3. Place the Condition on Class or Method?

`@Conditional` can be attached to a configuration class or a `@Bean` method. Yet **the phase requested by the condition must be compatible with its placement**.

| Placement | Reasonable interpretation |
| --- | --- |
| `@Conditional(ParseGateCondition.class)` on `@Configuration` class | Decides whether to parse the entire class |
| `@Conditional(RegisterGateCondition.class)` on `@Configuration` class | Allows the class to be parsed, then decides registration in the appropriate phase |
| `@Conditional(RegisterGateCondition.class)` on `@Bean` method | Checks when registering the factory bean |
| `@Conditional(ParseGateCondition.class)` on `@Bean` method | Not the right way to block parsing the whole class; risks the condition not running as you expect |
| `@ConditionalOnMissingBean` on auto-config or method | Uses logic about beans currently being registered, so definition order matters |

When the goal is "exclude an entire unneeded configuration right from the start", put the parse condition **on the configuration class**. When the goal is "if a user bean exists, do not create the default", put the bean-related condition in the appropriate auto-configuration, usually on the `@Bean` method.

### 4.4. Is Plain `Condition` the Same as `ConfigurationCondition`?

No. `Condition` only specifies `matches`; `ConfigurationCondition` also specifies the phase when the condition applies to `@Configuration`. A custom `Condition` that does not implement `ConfigurationCondition` provides no explicit phase choice, and Spring may evaluate it at various points during configuration processing. Do not write code assuming `matches` is guaranteed to run only once.

## 5. Complete Maven Example: Writing Two Custom ConfigurationConditions

The following example uses **Java 17+**, **Spring Boot 3.3.13**, and Maven. Two conditions are placed on **two auto-configuration classes**:

- `ParseGateCondition` runs only at `PARSE_CONFIGURATION`, reads `demo.parse-enabled`, and decides whether `ParseCheckedAutoConfiguration` proceeds through parsing.
- `RegistryGateCondition` runs only at `REGISTER_BEAN`, checking whether the registry already contains a **bean definition named `userMarker`**. This condition illustrates using **bean registration** information without calling `getBean(...)` to create bean instances.
- `DemoApplication` declares `userMarker` according to `demo.marker-enabled`. Since auto-config is processed after application configuration, `RegistryGateCondition` observes the application's bean definition in the normal scenario.
- The runner prints whether the two beans `parseProof` and `registerProof` actually exist. We run four property combinations to clearly distinguish the two phases.

**Demo scope:** two custom conditions help teach the mechanism. In production code, simple property/bean checks should prefer built-in `@ConditionalOnProperty` and `@ConditionalOnBean`, unless you truly need specialized logic.

### 5.1. Project Structure

```text
configuration-condition-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   └── UserMarker.java
    │   └── autoconfig/
    │       ├── ParseGateCondition.java
    │       ├── RegistryGateCondition.java
    │       ├── ParseCheckedAutoConfiguration.java
    │       └── RegisterCheckedAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

The app is in `com.example.app`, while auto-config is in `com.example.autoconfig`: the auto-config package **lies outside the app's default component scanning scope**. The auto-config classes are found by Boot via the imports file rather than component scan.

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
    <artifactId>configuration-condition-demo</artifactId>
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

### 5.3. `src/main/java/com/example/app/UserMarker.java`

```java
package com.example.app;

public record UserMarker(String source) {
}
```

`UserMarker` is a Java 17 record. It exists to distinguish **defining a bean** from **creating an object instance**. The demo checks `containsBeanDefinition` by name without touching the record instance inside the custom condition.

### 5.4. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "marker-enabled",
            havingValue = "true",
            matchIfMissing = true)
    UserMarker userMarker() {
        return new UserMarker("application");
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            System.out.println("USER_MARKER="
                    + context.containsBean("userMarker"));
            System.out.println("PARSE_PROOF="
                    + context.containsBean("parseProof"));
            System.out.println("REGISTER_PROOF="
                    + context.containsBean("registerProof"));
        };
    }
}
```

The `userMarker()` method is registered when `demo.marker-enabled=true` or the property is absent, due to `matchIfMissing=true`. The runner does not require receiving `UserMarker`, so the app can still start when this bean is absent.

**Do not treat `@ConditionalOnProperty` as the custom `ConfigurationCondition` example**: it merely helps the app toggle the marker's existence. The two custom implementations are in the next two files.

### 5.5. `src/main/java/com/example/autoconfig/ParseGateCondition.java`

```java
package com.example.autoconfig;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class ParseGateCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context, AnnotatedTypeMetadata metadata) {
        return Boolean.parseBoolean(
                context.getEnvironment()
                       .getProperty("demo.parse-enabled", "false"));
    }
}
```

The condition reads `Environment`, independent of the bean registry. If the property is `true`, `matches` returns true. If false or absent, it returns false.

Choosing `PARSE_CONFIGURATION` fits because we want to decide whether **the entire configuration class** should participate in parsing, and the required information is already available early enough.

**Note on boolean parsing:** `Boolean.parseBoolean` returns true for the string `"true"` (case-insensitive); any other value returns false. This is a convention of **the demo**, not every property condition expression supported by Spring Boot.

### 5.6. `src/main/java/com/example/autoconfig/RegistryGateCondition.java`

```java
package com.example.autoconfig;

import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class RegistryGateCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context, AnnotatedTypeMetadata metadata) {
        ConfigurableListableBeanFactory factory = context.getBeanFactory();
        return factory != null
                && factory.containsBeanDefinition("userMarker");
    }
}
```

The key point is not whether `UserMarker` has an instance yet. `containsBeanDefinition("userMarker")` only checks **bean definition metadata by name** at evaluation time. It does not invoke `userMarker()` and does not trigger bean creation.

At `REGISTER_BEAN`, Spring Framework has already parsed configuration classes; in auto-configuration, bean definitions from the app have usually already been processed so this check observes the marker in the demo.

**Design limitation:** this code only checks **the exact bean name `userMarker` in the current BeanFactory**. It is not a complete replica of `@ConditionalOnBean(UserMarker.class)`: Boot's built-in condition supports type matching, parent/child contexts, bean annotations, and many other options. In real libraries, prefer built-in conditions when sufficient.

### 5.7. `src/main/java/com/example/autoconfig/ParseCheckedAutoConfiguration.java`

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(ParseGateCondition.class)
public class ParseCheckedAutoConfiguration {

    @Bean
    String parseProof() {
        return "parsed";
    }
}
```

`@Conditional(ParseGateCondition.class)` sits **on the class**, not on the `@Bean` method. If the property is off, the parse condition is false so this configuration does not proceed to contribute the `parseProof` bean. If the property is on, the class is eligible for parsing and the bean definition can be registered.

`@AutoConfiguration` in Boot 3.3 implies `@Configuration(proxyBeanMethods=false)`. The code has no cross-calls between `@Bean` methods, so it fits cleanly.

### 5.8. `src/main/java/com/example/autoconfig/RegisterCheckedAutoConfiguration.java`

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration(after = ParseCheckedAutoConfiguration.class)
@Conditional(RegistryGateCondition.class)
public class RegisterCheckedAutoConfiguration {

    @Bean
    String registerProof() {
        return "registered";
    }
}
```

`@Conditional(RegistryGateCondition.class)` is also on the **class**, yet requests `REGISTER_BEAN`:

- It does not stop Spring from **parsing the class** in the first phase.
- When bean definition registration arrives, `RegistryGateCondition` checks whether the registry already contains `userMarker`.
- Without the marker, the `registerProof` bean is not registered; with it, that bean is allowed to register.

`@AutoConfiguration(after = ParseCheckedAutoConfiguration.class)` merely illustrates ordering between two auto-configs; **it is not required to check `userMarker`** in the demo because the marker comes from application configuration. Do not confuse `after` with bean instance initialization order.

### 5.9. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.parse-enabled=false
demo.marker-enabled=true
```

`demo.parse-enabled` and `demo.marker-enabled` are properties **of the demo**, not standard Spring Boot configuration names. `spring.main.web-application-type=none` lets the runner execute and the app exit; `logging.level.root=OFF` keeps output less noisy.

### 5.10. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.autoconfig.ParseCheckedAutoConfiguration
com.example.autoconfig.RegisterCheckedAutoConfiguration
```

This lists **two auto-config candidates** in Spring Boot 3.x. Class names must be exact and the file must be packaged onto the runtime classpath; merely having `@AutoConfiguration` on a class does not replace publishing the candidate in the imports file.

### 5.11. Compiling and Running Four Cases

From the directory containing `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/configuration-condition-demo-1.0.0.jar
```

**Case A — default:** `demo.parse-enabled=false`, `demo.marker-enabled=true`:

```text
USER_MARKER=true
PARSE_PROOF=false
REGISTER_PROOF=true
```

- Parse condition false: no `parseProof`.
- Bean definition `userMarker` present: register condition true, `registerProof` exists.

**Case B — enable parse condition:**

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --demo.parse-enabled=true
```

Stdout from the runner:

```text
USER_MARKER=true
PARSE_PROOF=true
REGISTER_PROOF=true
```

- Class parsing is permitted because the property is true.
- Register condition stays true because the marker has a definition.

**Case C — disable marker:**

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --demo.marker-enabled=false
```

Stdout:

```text
USER_MARKER=false
PARSE_PROOF=false
REGISTER_PROOF=false
```

- Parse gate stays false per the default property.
- No `userMarker` bean definition exists, so the register gate is false.

**Case D — enable parse, disable marker:**

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --demo.parse-enabled=true --demo.marker-enabled=false
```

Stdout:

```text
USER_MARKER=false
PARSE_PROOF=true
REGISTER_PROOF=false
```

- One phase permits class parsing, while the other phase blocks bean registration of the other class.
- The two conditions are **independent**: changing one property does not automatically alter the outcome of the other condition.

Summary:

| parse-enabled | marker-enabled | `parseProof` | `registerProof` |
| --- | --- | --- | --- |
| false | true | Absent | Present |
| true | true | Present | Present |
| false | false | Absent | Absent |
| true | false | Present | Absent |

The rows above count only `ApplicationRunner` output, excluding environment logs. These are **results deduced from the demo source**; if you alter source, dependencies, properties, or bean names, re-verify by actually running it.

## 6. Things to Watch When Writing a Custom ConfigurationCondition

### 6.1. Conditions Must Have Minimal Side Effects

`matches(...)` should answer a check based on metadata, `Environment`, registry, or resources; it should not open database connections, spawn threads, call network APIs, write files, or manually register beans from inside a condition.

Do not call `context.getBeanFactory().getBean(SomeType.class)` just to check if a bean exists; it can **trigger bean instantiation** and disrupt the lifecycle. If you need information about definitions, use APIs like `containsBeanDefinition` where appropriate or use built-in Boot conditions.

### 6.2. Do Not Assume the Register Phase Knows "Everything"

`REGISTER_BEAN` happens while the registry is being constructed. Bean definitions **already processed** are observable, but definitions from other auto-configs or later extensions might not be present yet. Therefore:

- For **user beans**, auto-config generally has the advantage of being processed after application configuration.
- For **beans from auto-config A** that B depends on, consider `before/after` ordering.
- For **beans dynamically registered later**, a condition cannot see a future definition at the current point in time.
- For **parent contexts**, type-based search logic can differ from local `containsBeanDefinition`.

### 6.3. Class-Level Conditions Can Have a Wide Scope

When attaching `@Conditional` to `@Configuration`, Spring processes `@Bean` methods and related configuration declarations under that condition's effect. If only one factory bean needs its own condition, placing the condition **directly on the `@Bean` method** can be clearer.

Example:

```java
@AutoConfiguration
public class CacheAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheClient.class)
    CacheClient cacheClient() {
        return new DefaultCacheClient();
    }

    @Bean
    CacheMetrics cacheMetrics() {
        return new CacheMetrics();
    }
}
```

This is an **illustrative** snippet without declaring `CacheClient`, `DefaultCacheClient`, or `CacheMetrics`, so it is not a runnable project. If the missing-bean condition is on the `cacheClient()` method, `cacheMetrics()` is not disabled just because the user supplied `CacheClient`. If the condition were placed at class level, its scope of impact would be broader.

### 6.4. Do Not Use Phases to Fix Bean Instantiation Order

`PARSE_CONFIGURATION` and `REGISTER_BEAN` belong to the **bean definition construction** time. Bean instance creation order involves dependency injection, `@DependsOn`, scope, and lifecycle callbacks. `@AutoConfiguration(after = ...)` primarily controls the order of applying auto-configs and registering definitions, without guaranteeing constructor invocation order.

If bean A needs to use bean B, declare the dependency via constructor or `@Bean` parameter; do not tweak condition phases to create instance B earlier.

### 6.5. Do Not Use Phases as a Substitute for Property Conditions

If you only need "enable when `feature.enabled=true`", Spring Boot's `@ConditionalOnProperty` is usually simpler than writing a `ConfigurationCondition` yourself. Write a custom condition when you need specialized logic — such as checking complex metadata, multiple resources, or registry relationships not covered by built-in annotations.

### 6.6. Recording Condition Outcomes for Diagnostics

A custom class that only implements `ConfigurationCondition` may not produce detailed condition messages like standard Spring Boot conditions. For library-provided auto-configs, consider `SpringBootCondition` or integrating `ConditionMessage`/`ConditionOutcome` when useful reporting is needed. However, do not expand the implementation just to get logs in a basic phase-explanation example.

In the demo, checking three booleans in the runner observes **the result of bean registration**, not direct proof of how many times `matches` was invoked.

## 7. Common Mistakes

| Symptom | Mistake | Fix |
| --- | --- | --- |
| Bean-checking condition returns false even though context eventually has the bean | Evaluated too early in parse phase or auto-configs not ordered | Use `REGISTER_BEAN` when appropriate; check ordering and built-in bean conditions |
| `@Conditional` on `@Bean` does not block the whole class | Confusing method scope with class scope | To skip the whole configuration, place the parse condition on the class |
| `@Conditional` using a parse-phase `ConfigurationCondition` directly on a `@Bean` method | Phase incompatible with placement | Put parse conditions on the configuration class |
| Thinking `REGISTER_BEAN` means singletons are already created | Confusing definition with instance | Inspect `containsBeanDefinition`; avoid calling `getBean` inside conditions |
| Calling `context.getBeanFactory().getBean(...)` in a condition | Can trigger premature bean creation | Inspect metadata/definitions or use Boot conditions |
| Correct auto-config class yet never evaluated | Missing/wrong `AutoConfiguration.imports` or excluded | Check JAR, imports file, and exclusions |
| User bean of the same type exists yet custom condition checks a different name | Logic checks name rather than type | Switch to `@ConditionalOnBean(value=...)` or look up by proper type |
| Both conditions return true yet app still lacks the bean | May have other conditions, wrong package, bean creation error, or registration failure | Inspect context errors, candidates, and other conditions |
| Disabled parse gate yet expecting beans in the class to appear | Entire config was skipped at parse phase | Enable property or split unrelated beans to another config |
| Condition fails to match yet runs at different times after editing source | Misunderstanding phase and annotation placement | Identify `getConfigurationPhase`, `@Conditional` placement, and Spring processing timing |
| Marker name differs from expected | `containsBeanDefinition("userMarker")` checks **exact name** | Check `@Bean` name, aliases, and local/parent context |
| Custom condition calls external services, making startup slow/flaky | Condition has side effects | Keep conditions lightweight, based on metadata/environment/registry |

## 8. Diagnosing Conditions in Real Applications

If an auto-configuration does not create an expected bean, inspect in order:

1. **Candidate:** is the `@AutoConfiguration` class listed in the JAR's `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`? Is it excluded?
2. **Class-level conditions:** are classpath/property/web-mode requirements met? Did an early condition eliminate the whole configuration class?
3. **Method-level conditions:** does the default bean have `@ConditionalOnMissingBean` or `@ConditionalOnProperty` on its factory method?
4. **Bean definitions at evaluation time:** is the user bean registered, what return type does the method have, what is the bean name, and is there a profile or property excluding the method?
5. **Ordering:** is the auto-config evaluated after auto-configs that supply required dependency beans?
6. **Condition phase:** did a custom condition pick a phase matching the information it uses?
7. **Bean creation:** if conditions match yet startup still fails, check dependency resolution, circular dependencies, bean post-processing, and constructor exceptions.

Spring Boot supports `--debug` to print the *Condition Evaluation Report*. For the demo with root logging disabled, override it:

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --debug --logging.level.root=DEBUG
```

`/actuator/conditions` also provides the report when Actuator is added and exposure is properly configured; do not expose this endpoint broadly to external traffic by default.

**Distinguish log messages:** "did not match" can be intended design behavior, not an error. A hand-written `ConfigurationCondition` may lack detailed explanations if it does not integrate Boot's reporting API.

## 9. Misconceptions to Eliminate

| Misconception | Why it is wrong |
| --- | --- |
| "PARSE and REGISTER are two timings for creating bean instances." | They belong to **configuration and bean definition processing**, not instance lifecycle. |
| "PARSE_CONFIGURATION can safely check all app beans." | During parsing, relevant definitions may not be registered yet. |
| "REGISTER_BEAN makes the condition re-evaluate every time a bean is used." | It concerns **definition registration**; it is not a runtime callback on every `getBean`. |
| "If a REGISTER condition is false, Spring never parsed the config class." | Register conditions do not block initial parsing; they take effect at registration. |
| "Implementing the custom Condition interface is enough without `@Conditional`." | A condition must be linked to an annotation/configuration element for Spring to evaluate it. |
| "Just having `getConfigurationPhase` return REGISTER guarantees auto-config B always sees A's beans." | You must consider auto-config ordering and whether A's beans were already processed. |
| "`@ConditionalOnClass` and `@ConditionalOnBean` check the same thing." | The first checks **Java class presence**, the second checks **beans** in the context. |
| "`@Conditional` on a method can replace a parse condition on a class." | Scope and phase differ; method-level does not block parsing the entire class. |
| "Calling `getBean()` in a condition is a harmless way to check." | It can instantiate beans prematurely, causing side effects and lifecycle issues. |
| "Every condition must return the same result on every call." | The context can differ across moments; design conditions with the right phase and no side effects. |

## 10. Self-Check Questions

**Q1.** Why does a condition that only checks `Environment` usually fit `PARSE_CONFIGURATION`?

**Answer:** Because properties/environment are ready relatively early and can be used to decide whether to parse the entire configuration class instead of waiting for the bean registry.

**Q2.** Why should checking `containsBeanDefinition("userMarker")` consider `REGISTER_BEAN`?

**Answer:** Because it needs to observe a bean definition added to the registry; during the parse phase it might not have been processed yet.

**Q3.** If `ParseGateCondition` is false on `ParseCheckedAutoConfiguration`, is the `parseProof` bean registered?

**Answer:** No, the configuration class does not proceed further with parsing along this branch.

**Q4.** If `RegistryGateCondition` is false on `RegisterCheckedAutoConfiguration`, can we conclude Spring never parsed this class?

**Answer:** No. The register phase does not block the parse step; it can prevent bean definitions from being registered afterward.

**Q5.** Does `getConfigurationPhase()` alter `@AutoConfiguration(after=...)`?

**Answer:** No. Phase chooses **what kind of evaluation timing** to use; `after` orders auto-configuration definitions relative to each other.

**Q6.** If the demo has `demo.parse-enabled=true` and `demo.marker-enabled=false`, what will the runner print?

**Answer:**

```text
USER_MARKER=false
PARSE_PROOF=true
REGISTER_PROOF=false
```

**Q7.** When the user has their own `PaymentGateway`, which Boot condition type should be used so the default backs off?

**Answer:** Usually `@ConditionalOnMissingBean(PaymentGateway.class)` in auto-config, rather than writing a custom `Condition` that looks up bean names manually.

**Q8.** Can a condition call an external HTTP API in `matches`?

**Answer:** You can write Java that does so, but **you should not**: it subjects startup to network side effects, is hard to test, and does not fit the lightweight role of configuration registration conditions.

## 11. References

- [Spring Framework 6.1 — ConfigurationCondition](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): interface, `getConfigurationPhase`, and the purpose of selecting evaluation timing.
- [Spring Framework 6.1 — ConfigurationCondition.ConfigurationPhase](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): definitions of `PARSE_CONFIGURATION` and `REGISTER_BEAN`, including class parsing vs. bean registration scope.
- [Spring Framework 6.1 — Conditional](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html): conditions attached to classes or `@Bean` methods.
- [Spring Boot 3.3 — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): the limitation "bean definitions processed up to evaluation time" and why it belongs in auto-config.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): imports file, class conditions, bean conditions, and ordering between auto-configs.

**Conclusion:** `PARSE_CONFIGURATION` decides **whether to carry a `@Configuration` class forward in the parsing process**, while `REGISTER_BEAN` decides **whether to add appropriate bean definitions after the parse step**. Choose the phase according to the kind of data the condition needs; when depending on bean presence, prefer Spring Boot's built-in conditions and always account for the order of processed bean definitions.
