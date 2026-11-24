# Distinguishing the Configuration Parsing Phase from the Bean Registration Phase in Spring Boot

> **Context:** Spring Boot — auto-configuration, **Condition Mechanism** group. This lesson explains the difference between when Spring **parses a configuration class** and when Spring **registers a bean definition**, clarifying when a condition can block an entire configuration class, when it only blocks a single bean, why `@ConditionalOnBean`/`@ConditionalOnMissingBean` must inspect already known beans, and how to write tests confirming that behavior. The complete example uses Java 17, Maven, and Spring Boot 3.5.7.

## 1. The Short Answer

During Spring ApplicationContext initialization, there are at least three **distinct** events:

1. **Configuration parsing:** Spring reads configuration sources, identifies `@Configuration`, `@Import`, `@ComponentScan`, nested configurations, and conditions that can decide whether **to continue parsing a configuration class**.
2. **Bean definition registration:** Spring turns information from configuration classes and `@Bean` methods into bean definitions inside the bean factory. Conditions that need to see **already registered bean definitions** can be evaluated at this stage.
3. **Bean instance instantiation:** Spring calls factory methods or constructors to create objects, inject dependencies, and run lifecycle callbacks. For non-lazy singletons, this typically occurs during context refresh, **after** most configuration reading and bean definition registration work is done.

The first two phases are our main subject. **Registering a bean definition does not mean creating a bean instance.** A bean definition can exist even before the object is instantiated; an `@AutoConfiguration` class can be evaluated yet ultimately register no application beans because its conditions do not match.

Spring Framework allows a condition to declare its appropriate timing via `ConfigurationCondition.ConfigurationPhase`, which has two values:

- `PARSE_CONFIGURATION`: applies while parsing the configuration class.
- `REGISTER_BEAN`: applies when registering the bean definition.

This pair of values does not replace the full `ApplicationContext` lifecycle; these are **two condition evaluation timings during configuration processing**.

## 2. Why Separate the Two Phases?

Suppose a library provides a default:

```java
@Bean
@ConditionalOnMissingBean(MessagePort.class)
public DefaultMessagePort defaultMessagePort() {
    return new DefaultMessagePort();
}
```

This is an **illustrative snippet**; `MessagePort`, `DefaultMessagePort`, and a configuration class must be defined for it to run. To decide whether to register the `defaultMessagePort` bean, Spring Boot must know whether any bean of type `MessagePort` already exists.

Right when Spring first reads a configuration class, all bean definitions declared by the application may not have been processed yet. If "missing bean" were checked too early, Spring might wrongly conclude there is no user bean yet and register a duplicate default.

Conversely, a condition checking the presence of an API on the classpath, such as `@ConditionalOnClass(name="com.vendor.sdk.Client")`, can often eliminate a configuration class early without waiting for bean definitions to be registered. Eliminating early avoids deeply processing configurations tied to an absent library.

This is why you cannot say every `@Conditional` "runs at the same time".

## 3. Configuration Pipeline Overview

The diagram below is a conceptual model; Spring has multiple passes and auxiliary processors depending on bean sources, such as registry post-processors, component scanning, and import selectors.

```text
SpringApplication.run(...)
         |
         v
Create Environment, prepare ApplicationContext
         |
         v
Read application configuration sources
         |
         v
ConfigurationClassPostProcessor
         |
         +-- ConfigurationClassParser
         |      |
         |      +-- identify configuration classes / @Import / @ComponentScan
         |      +-- evaluate PARSE_CONFIGURATION conditions where applicable
         |      +-- exclude configurations ineligible for further parsing
         |      +-- select/read imported auto-configurations
         |
         +-- ConfigurationClassBeanDefinitionReader
                |
                +-- evaluate REGISTER_BEAN conditions where applicable
                +-- register bean definitions from classes / @Bean methods
                +-- bean conditions can inspect known definitions
         |
         v
BeanFactoryPostProcessor / BeanPostProcessor and other steps
         |
         v
Instantiate singletons, inject dependencies, lifecycle, runners...
```

The names `ConfigurationClassPostProcessor`, `ConfigurationClassParser`, and `ConfigurationClassBeanDefinitionReader` belong to Spring Framework's configuration processing mechanism; they explain the origin of the two-phase distinction. Do not treat the diagram as an absolute ordering guarantee for every bean/extension type or every Spring version.

### What to Understand About "Parse"

Configuration parsing is not merely reading the text of a Java file. Java classes are already compiled; Spring uses annotation/class metadata to discover configurations, imports, scans, and conditions. A condition in the parsing phase can cause Spring **not to continue processing** the contents of a given configuration class.

### What to Understand About "Register"

Registering a bean definition does not necessarily execute the business code inside the `@Bean` method right then. Spring can record the method name, return type, and other metadata to invoke the method when an instance is needed. Therefore, bean-based conditions must rely on available definitions/metadata and cannot assume every bean already has an instance.

### What to Understand About "Instantiate"

Although many singletons are created during refresh, a bean marked `@Lazy` can be created later. Prototype scope creates instances on demand. Hence "registration" and "instantiation" must not be collapsed into a single step.

## 4. What Does the ConfigurationCondition API Say Exactly?

Spring Framework provides the interface:

```java
org.springframework.context.annotation.ConfigurationCondition
```

It extends the `Condition` interface and adds the method:

```java
ConfigurationPhase getConfigurationPhase();
```

This is a **condensed signature**, not a standalone Java class. The nested enum inside the interface has values `PARSE_CONFIGURATION` and `REGISTER_BEAN`.

When a condition implements `ConfigurationCondition`, it declares **the phase in which Spring should evaluate that condition**. The `matches(ConditionContext, AnnotatedTypeMetadata)` method still decides whether the condition is true or false.

Condensed syntax example:

```java
public final class ParseGate implements ConfigurationCondition {
    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return true;
    }
}
```

This is a **fragment**; Spring imports must be added. The complete class appears in the hands-on section.

**Important:** `@Conditional` itself only lists condition classes; **it does not specify a phase**. The phase can come from the condition implementing `ConfigurationCondition`. Conditions that only implement `Condition` do not carry such an explicit phase constraint; Spring evaluates them at appropriate processing points.

### A Phase Is Not Bean Instance Order

A `REGISTER_BEAN` condition does not mean "runs after singletons are created". It only designates the **bean definition** processing stage. A `PARSE_CONFIGURATION` condition may exclude a configuration early, which does not mean the Java class is deleted from the classpath.

## 5. Connection to Spring Boot Conditions

Spring Boot's convenience annotations build on top of the `@Conditional` infrastructure:

| Annotation / condition | Information read | Key takeaway |
| --- | --- | --- |
| `@ConditionalOnClass` | Classpath / class metadata | Can filter out configurations early when dependent APIs are absent; suitable on configuration classes. |
| `@ConditionalOnMissingClass` | Absence of classes | Similar classpath condition group; no bean instance required. |
| `@ConditionalOnBean` | Known bean definitions / bean types | Depends on matching beans already being processed when the condition runs. |
| `@ConditionalOnMissingBean` | Absence of matching beans at evaluation time | Used for defaults with a **back-off** mechanism, especially in auto-configuration. |
| `@ConditionalOnSingleCandidate` | Matching bean candidate set | Usually needs to inspect already registered bean definitions. |
| `@ConditionalOnProperty` | `Environment` / properties | Can be applied on classes or methods; do not automatically assign every property condition to a single immutable phase. |
| `@Profile` | Active profiles | Blocks definitions by profile; does not create beans and then delete them at runtime. |

In Spring Boot, classpath-based conditions and bean-based conditions do not necessarily run at the same processing time. Specifically:

- Class conditions like `@ConditionalOnClass` suit deciding **whether to consider a configuration requiring a certain SDK**.
- Bean-based conditions like `@ConditionalOnBean` and `@ConditionalOnMissingBean` require the presence (or absence) of **already processed bean definitions**; Boot documentation warns that these conditions only see beans processed up to that point.
- A condition on a **configuration class** can affect all bean definitions inside; a condition on a **`@Bean` method** mainly affects that method's bean.
- Do not mechanically equate annotation placement with phase: phase is determined by **the condition type and processing infrastructure**. In the example below, phases are declared explicitly to demonstrate without ambiguity.

## 6. Runnable Example: One Gate at Parse Phase, One Gate at Register Phase

We build a Spring Boot application with one auto-configuration class. It declares:

- `@Conditional(ParseGate.class)` **on the class** with phase `PARSE_CONFIGURATION`: if property `demo.phase.parse.enabled=false`, the configuration class is blocked early.
- `@Conditional(RegisterGate.class)` **on the `@Bean` method** with phase `REGISTER_BEAN`: the class may have been parsed, yet the default bean is not registered if property `demo.phase.register.enabled=false`.
- `@ConditionalOnMissingBean(MessagePort.class)` on the same method: the default is registered only when the application has not already supplied an equivalent `MessagePort` bean.

The example intentionally creates **hand-written conditions with explicit phases** to separate the two stages. It does not claim all built-in Spring Boot conditions use these exact classes/gates.

### 6.1. Project Structure

```text
configuration-phases-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/phase/
    │   │   ├── api/MessagePort.java
    │   │   ├── autoconfigure/DefaultMessagePort.java
    │   │   ├── autoconfigure/ParseGate.java
    │   │   ├── autoconfigure/RegisterGate.java
    │   │   ├── autoconfigure/PhaseAutoConfiguration.java
    │   │   └── app/PhaseApplication.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/dev/example/phase/check/
        ├── PhaseAutoConfigurationTest.java
        └── PhaseApplicationTest.java
```

The application class is in `dev.example.phase.app`. The auto-configuration lives in a separate package branch and is loaded via the imports file, independent of application component scanning.

### 6.2. Maven POM

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>configuration-phases-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

There is no web server or database in the demo, keeping the focus on Spring's configuration lifecycle.

### 6.3. Defining the Bean Contract

`src/main/java/dev/example/phase/api/MessagePort.java`:

```java
package dev.example.phase.api;

@FunctionalInterface
public interface MessagePort {
    String message();
}
```

Default bean at `src/main/java/dev/example/phase/autoconfigure/DefaultMessagePort.java`:

```java
package dev.example.phase.autoconfigure;

import dev.example.phase.api.MessagePort;

public final class DefaultMessagePort implements MessagePort {
    @Override
    public String message() {
        return "from-default";
    }
}
```

Do not use `@Component` because the bean will be registered conditionally with `@Bean`.

### 6.4. Condition at the Parse Phase

`src/main/java/dev/example/phase/autoconfigure/ParseGate.java`:

```java
package dev.example.phase.autoconfigure;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class ParseGate implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment().getProperty(
            "demo.phase.parse.enabled",
            Boolean.class,
            true
        );
    }
}
```

When `demo.phase.parse.enabled=false`, the condition does not match during the parsing phase, so Spring does not continue processing the annotated configuration. It **does not create a bean and then delete that bean**.

The third argument to `getProperty` is default `true`, so omitting the property allows the configuration. Production practice should check for typos or invalid boolean values according to application policy.

### 6.5. Condition at the Registration Phase

`src/main/java/dev/example/phase/autoconfigure/RegisterGate.java`:

```java
package dev.example.phase.autoconfigure;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class RegisterGate implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment().getProperty(
            "demo.phase.register.enabled",
            Boolean.class,
            true
        );
    }
}
```

Here, `matches(...)` checks a property in the same way as `ParseGate`, but the **evaluation timing** differs due to `getConfigurationPhase()`. The two conditions are intentionally split into two classes to illustrate the design.

### 6.6. Auto-Configuration Class Combining Both Phases

`src/main/java/dev/example/phase/autoconfigure/PhaseAutoConfiguration.java`:

```java
package dev.example.phase.autoconfigure;

import dev.example.phase.api.MessagePort;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(ParseGate.class)
public class PhaseAutoConfiguration {

    @Bean
    @Conditional(RegisterGate.class)
    @ConditionalOnMissingBean(MessagePort.class)
    public DefaultMessagePort defaultMessagePort() {
        return new DefaultMessagePort();
    }
}
```

**Reading in order of meaning:**

1. Spring Boot learns about `PhaseAutoConfiguration` because the imports file lists this class.
2. During configuration processing, `ParseGate` must allow the class to proceed.
3. During bean method registration, `RegisterGate` must allow `defaultMessagePort` to be registered.
4. `@ConditionalOnMissingBean(MessagePort.class)` only allows the default if a suitable `MessagePort` bean does not already exist in the evaluation context.
5. If all three conditions match, Spring registers the bean definition with signature `DefaultMessagePort`, and only then does the container create the instance per lifecycle.

**Distinguish annotation scope:** If `ParseGate` at class level fails to match, no method inside this class is processed along that path. If only `RegisterGate` on the method fails to match, the class is still a parsed configuration; another `@Bean` method without that gate could still contribute a bean.

### 6.7. Registering the Auto-Configuration Candidate

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Exact content:

```text
dev.example.phase.autoconfigure.PhaseAutoConfiguration
```

Put the imports file under `src/main/resources` so Maven packages it onto the runtime classpath. Do not add an application `@ComponentScan` over the `autoconfigure` package; the goal is to test the true auto-configuration path.

### 6.8. Application Runnable from the Command Line

`src/main/java/dev/example/phase/app/PhaseApplication.java`:

```java
package dev.example.phase.app;

import dev.example.phase.api.MessagePort;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class PhaseApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(PhaseApplication.class, args)) {

            MessagePort port =
                context.getBeanProvider(MessagePort.class).getIfAvailable();

            System.out.println("port.present=" + (port != null));
            System.out.println(
                "port.message=" + (port == null ? "none" : port.message())
            );
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

Two lines printed by the program (ignoring startup logs):

```text
port.present=true
port.message=from-default
```

At this point, both parse gate and register gate default to `true`, and no other `MessagePort` bean exists, so the default bean appears.

### 6.9. Disabling at the Parse Phase

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.phase.parse.enabled=false
```

Two lines printed by the application:

```text
port.present=false
port.message=none
```

**Explanation:** `ParseGate` fails to match right during parsing of `PhaseAutoConfiguration`. The configuration class does not contribute its `@Bean` method to the bean definition creation process along this branch.

### 6.10. Disabling at the Registration Phase

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.phase.register.enabled=false
```

Two lines printed by the application:

```text
port.present=false
port.message=none
```

Same result — **no bean** — yet a different cause: the auto-configuration class may have been parsed, while the `defaultMessagePort` method was prevented from registering when the `REGISTER_BEAN` condition failed to match.

**Do not use the absence of a bean to infer which phase blocked it.** You must know where the condition was placed and/or inspect condition outcomes when debugging.

## 7. Detailed Comparison Table of the Two Phases

| Criterion | PARSE_CONFIGURATION | REGISTER_BEAN |
| --- | --- | --- |
| Primary goal | Decide whether to continue parsing a configuration class | Decide whether to register the corresponding bean definition |
| Typical available information | Annotation metadata, classpath, environment, and current configuration sources | Configuration metadata plus bean definitions registered up to that point |
| Example in the demo | `@Conditional(ParseGate.class)` on `PhaseAutoConfiguration` | `@Conditional(RegisterGate.class)` on `defaultMessagePort()` |
| When condition is false | Skips parsing the associated configuration class | Does not register the guarded bean definition |
| Bean instance created beforehand? | Not the meaning of the phase | Not the meaning of the phase |
| Safe to read bean definitions? | Should not assume all user beans are already available | Can use known bean definition info; does not include beans appearing later |
| Use cases | Reject a configuration early when prerequisites fail | Conditions depending on registered beans or specific `@Bean` method rules |

The `@ConditionalOnProperty` condition can be attached to both classes and methods. It uses `Environment`; this lesson does not claim a property annotation always belongs to a single fixed phase. For custom conditions, the proper way to request a specific phase is to implement `ConfigurationCondition`.

## 8. Deep Dive: Why Do Bean-Based Conditions Still Depend on Order?

Consider two auto-configurations:

```java
@AutoConfiguration
class ProviderAutoConfiguration {
    @Bean
    MessagePort messagePort() {
        return () -> "provider";
    }
}

@AutoConfiguration(after = ProviderAutoConfiguration.class)
@ConditionalOnBean(MessagePort.class)
class ConsumerAutoConfiguration {
    @Bean
    MessageMonitor messageMonitor(MessagePort port) {
        return new MessageMonitor(port);
    }
}
```

**These are illustrative fragments**; `MessagePort`, `MessageMonitor`, imports, and Java imports must be defined to run independently.

Conditions like `@ConditionalOnBean` cannot "see into the future": they can only inspect beans already processed at the moment the condition runs. If the consumer configuration is evaluated before the provider definition, the condition may fail to match even though a `MessagePort` bean will exist by the end of startup.

Spring Boot provides ordering metadata via `@AutoConfiguration(after=...)`, `before`, `afterName`, `beforeName`, and corresponding ordering annotations. Ordering guarantees **configuration processing order**, not instance creation order.

### Why Use `@ConditionalOnMissingBean` in Auto-Configuration?

In the standard Spring Boot flow, bean definitions explicitly declared by the application are processed before auto-configuration. When Spring Boot evaluates `@ConditionalOnMissingBean(MessagePort.class)` inside auto-configuration, it has the opportunity to recognize the declared user bean and **yield**.

For example, if the application has:

```java
@Configuration(proxyBeanMethods = false)
class UserConfiguration {
    @Bean
    MessagePort userMessagePort() {
        return () -> "user";
    }
}
```

This is a fragment separate from the lab code (omitting package/imports). Once the user bean is registered, the auto-configuration's default can back off. That condition **does not delete any existing bean**; it prevents registering the default bean definition from the start.

Scattering `@ConditionalOnMissingBean` indiscriminately in regular configurations can cause surprises if another configuration is registered later. That is why Boot documentation specifically recommends using these bean conditions inside auto-configuration.

## 9. Testing Both Phases and Back-Off

`ApplicationContextRunner` builds a lightweight context to test condition branches without running the full application. The following tests run with the Maven POM above.

File `src/test/java/dev/example/phase/check/PhaseAutoConfigurationTest.java`:

```java
package dev.example.phase.check;

import dev.example.phase.api.MessagePort;
import dev.example.phase.autoconfigure.DefaultMessagePort;
import dev.example.phase.autoconfigure.PhaseAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PhaseAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(PhaseAutoConfiguration.class)
            );

    @Test
    void registersDefaultWhenBothPhasesAllowIt() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(MessagePort.class);
            assertThat(context).hasSingleBean(DefaultMessagePort.class);
            assertThat(context.getBean(MessagePort.class).message())
                .isEqualTo("from-default");
        });
    }

    @Test
    void blocksConfigurationAtParsePhase() {
        runner.withPropertyValues("demo.phase.parse.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(MessagePort.class);
                assertThat(context).doesNotHaveBean(DefaultMessagePort.class);
            });
    }

    @Test
    void blocksDefaultBeanAtRegistrationPhase() {
        runner.withPropertyValues("demo.phase.register.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(MessagePort.class);
                assertThat(context).doesNotHaveBean(DefaultMessagePort.class);
            });
    }

    @Test
    void userBeanMakesMissingBeanConditionBackOff() {
        runner.withUserConfiguration(UserMessageConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(MessagePort.class);
                assertThat(context).doesNotHaveBean(DefaultMessagePort.class);
                assertThat(context.getBean(MessagePort.class).message())
                    .isEqualTo("from-user");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserMessageConfiguration {
        @Bean
        MessagePort userMessagePort() {
            return () -> "from-user";
        }
    }
}
```

The test configuration `UserMessageConfiguration` resides in package `dev.example.phase.check`, **outside the application's component scan tree** at `dev.example.phase.app`. It is registered solely by `withUserConfiguration(...)` when testing the back-off branch, avoiding accidental interference with other tests.

### Integration Test: Verifying the Imports Loading Path

File `src/test/java/dev/example/phase/check/PhaseApplicationTest.java`:

```java
package dev.example.phase.check;

import dev.example.phase.api.MessagePort;
import dev.example.phase.app.PhaseApplication;
import dev.example.phase.autoconfigure.DefaultMessagePort;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = PhaseApplication.class,
    properties = {
        "demo.phase.parse.enabled=true",
        "demo.phase.register.enabled=true"
    }
)
class PhaseApplicationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void importsConfigurationFromClasspathResource() {
        assertThat(context.getBean(MessagePort.class))
            .isInstanceOf(DefaultMessagePort.class);
        assertThat(context.containsBean("defaultMessagePort")).isTrue();
    }
}
```

Run:

```bash
mvn -q test
```

Expect **5 passing tests** with the files and source above: 4 `ApplicationContextRunner` tests and 1 `@SpringBootTest`. The fifth test does not use `AutoConfigurations.of(...)` to supply the configuration manually; it boots `PhaseApplication` to verify that `AutoConfiguration.imports` is actually used. The sample tests do not assert how many times Spring calls `matches(...)`, because that internal detail can vary by version.

**Important limitation:** The two tests resulting in "no MessagePort" at the parse and register phases **do not by themselves prove which phase ran**; phase is defined by `ConfigurationCondition.getConfigurationPhase()` and annotation placement. They verify the corresponding observable outcome. To deeply observe invocation timing, you can add logging inside `matches(...)` in a demo environment, without treating log line counts as a stable contract.

## 10. Class-Level Conditions vs. `@Bean` Method Conditions

Beyond phase, **annotation placement** also determines the scope of impact.

### Condition on the Class

```java
@Configuration(proxyBeanMethods = false)
@Conditional(FeaturePresentCondition.class)
class FeatureConfiguration {
    @Bean
    FeatureClient featureClient() {
        return new FeatureClient();
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

This is a fragment (`Feature...` types are undefined). If the class-level condition fails to match at its processing point, the entire configuration is not applied along this path; neither method inside contributes a bean definition.

### Condition on the Method

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    @Bean
    @Conditional(FeaturePresentCondition.class)
    FeatureClient featureClient() {
        return new FeatureClient();
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

Here the condition only guards `featureClient()`. If it does not match, `featureMetrics()` can still register its bean definition, subject to other conditions/dependencies. The example only illustrates scope; whether `featureMetrics()` instantiates successfully still depends on real code and dependencies.

**Do not put a `PARSE_CONFIGURATION` condition on a `@Bean` method and expect it to act identically to a class-level condition:** the parse phase is tied to analyzing configuration classes, whereas `@Bean` methods are primarily processed during definition registration. If you need to block an entire group of beans early, put the parse-phase condition on the configuration class or a nested configuration class.

## 11. Other Easily Confused Concepts: `@Conditional`, `@Profile`, `@Lazy`, and `@DependsOn`

| Mechanism | What does it decide? | Not synonymous with |
| --- | --- | --- |
| `@Conditional` / `ConfigurationCondition` | Whether to process the configuration or register the corresponding bean definition | Not an on-demand early/late bean instantiation mechanism. |
| `@Profile("dev")` | Definition is only registered when the profile matches | Does not create the bean and then delete it at runtime. |
| `@Lazy` | Delays instance creation in supported scenarios | Does not make the bean definition disappear. |
| `@DependsOn` | Initialization and destruction dependency ordering in applicable scenarios | Does not control the configuration parsing phase. |
| `@AutoConfiguration(after=...)` | Processing order among auto-configurations | Does not guarantee bean instances share the same order. |
| `@Order` / `@Priority` | Priority/ordering for mechanisms supporting these annotations | Not a general substitute for auto-configuration ordering. |

Specifically, if a `REGISTER_BEAN` condition returns false, it drops the related **bean definition**; `@Lazy` merely delays the **bean instance** while the definition stays in the context. Those are two different design layers.

## 12. Common Mistakes and How to Diagnose Them

### Mistake A — "If the auto-configuration class is on the classpath, every `@Bean` is guaranteed to exist"

Incorrect. The class might not be listed in `AutoConfiguration.imports`, might be excluded, or might have a parse/register phase condition that fails to match. Verify the configuration loading path before inspecting methods.

### Mistake B — "A missing bean means the method ran and returned null"

Normally, if `@Conditional` on a method fails to match, **the factory method is never called** and the bean definition is not registered. This differs from a method being called and returning `null` (which is a separate case). Do not return `null` to simulate a condition without understanding the semantics.

### Mistake C — "`@ConditionalOnBean` sees beans that a later configuration will register"

Conditions of this kind depend on bean definitions **already processed**; they do not see all future beans. Check condition placement, auto-configuration ordering, `@Bean` return types, and bean registration sources. If two auto-configurations depend on each other, use deliberate ordering.

### Mistake D — "I declared `@Bean` returning `Object`, yet a condition checking the concrete type must still find it"

Spring may only infer type `Object` from the signature before the instance is created. Declare a sufficiently specific return type when you want type-based conditions to detect the bean, or base the condition on the published abstraction.

### Mistake E — "I disabled the bean via a condition, yet the bean still exists"

Check whether the bean is registered through **another path**: component scan, `@Import`, user configuration, another auto-configuration, or a bean definition registrar. A condition on one definition source does not remove beans of the same type registered by another source.

### Mistake F — "Changing a property at runtime automatically reruns auto-configuration"

Conditions governing bean registration are evaluated during context construction. Changing a property on an already running context **does not automatically** trigger re-parsing/re-registering bean definitions. You need an intentional refresh/rebuild mechanism if a feature truly supports dynamic configuration.

### Mistake G — "`REGISTER_BEAN` runs after singletons are instantiated"

No. This is still the **bean definition** processing stage. Avoid network connections, heavy data reads, or side effects inside `Condition.matches(...)`. Conditions should be lightweight, deciding based on available metadata/environment/context.

### Mistake H — "Testing conditions with `@SpringBootTest` is always simplest"

An integration test can pull in many other beans/auto-configurations and obscure the root cause. For a specific auto-configuration, `ApplicationContextRunner` isolates the class, beans, properties, and condition outcomes. Then add an integration test to catch imports packaging and actual scanning issues.

### Mistake I — "`@ConditionalOnClass` on a `@Bean` method with an absent SDK type is always safe"

The class containing the method may have to be loaded/inspected before the method-level condition is evaluated, causing errors when the signature mentions an absent optional class. A safer pattern is usually a nested `@Configuration(proxyBeanMethods=false)` carrying `@ConditionalOnClass` at class level and containing the methods using that SDK type.

## 13. Debugging: Distinguishing Why Configurations and Beans Do Not Appear

Spring Boot provides a **Condition Evaluation Report** to trace conditions with positive/negative matches. Run the demo with:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

When using `demo.phase.parse.enabled=false`, class-level `ParseGate` does not match. When using `demo.phase.register.enabled=false`, the condition on the bean method does not match. When a user-provided `MessagePort` exists, `@ConditionalOnMissingBean` backs off. All three cases can result in **no default bean found**, yet for different reasons.

Beyond logs:

1. Check whether the auto-configuration class is listed in `AutoConfiguration.imports`.
2. Inspect properties from `Environment` and active profiles.
3. Check whether the condition is placed **on the class or on the method**.
4. Read the declared return type of `@Bean` and the bean name.
5. Read condition outcomes in the report rather than guessing from exceptions alone.
6. When needed, inspect the list of bean definitions with `ConfigurableListableBeanFactory`; it reflects what was registered, not a complete log of every condition invocation.

Actuator provides `conditions` and `beans` endpoints when its dependency is added, properly exposed, and secured with access control. Do not leave diagnostic endpoints wide open in production.

**Note on logging in custom conditions:** Conditions may be invoked more than once depending on processing; this lesson does not assume every class is checked only once. What matters is the check phase/location and its effect on bean definitions.

## 14. Design Rules for Conditions and Auto-Configuration

- **Classpath first, beans later:** When a library depends on an optional SDK, place classpath conditions at the class/nested configuration level to eliminate invalid configurations as early as appropriate.
- **Bean conditions in the right place:** Prefer `@ConditionalOnBean`/`@ConditionalOnMissingBean` in auto-configuration, once most user configurations have been evaluated.
- **Back-off is policy:** Clearly define which bean type/name users may override instead of writing ambiguous conditions.
- **Do not assume objects exist:** Conditions rely on metadata, environment, and registry appropriately; avoid side effects and premature initialization.
- **Clear condition scope:** Class-level conditions block multiple beans, method-level conditions block one bean; place them where they express the exact feature boundary.
- **Meaningful ordering:** If a consumer auto-configuration depends on bean definitions registered by a provider auto-configuration, use `after`/`before` when needed rather than relying on imports file line order.
- **Specific enough bean return types:** Method signatures help conditions resolve bean types without invoking factory methods.
- **Test every branch:** Include tests for failing class conditions, failing method conditions, user-bean back-off, and default success.
- **Separate the two API layers:** `@Conditional` decides registration; `@Lazy`/scope largely decides instantiation timing.
- **Diagnose with evidence:** Combine the condition report, bean definitions, classpath resources, and tests instead of looking solely at final bean counts.

## 15. Self-Check Questions

1. When `ConfigurationCondition.getConfigurationPhase()` returns `PARSE_CONFIGURATION`, when is the condition primarily evaluated? **During configuration class parsing**.
2. When it returns `REGISTER_BEAN`, does that mean the factory method has already run and returned an instance? **No**. It belongs to the bean definition processing stage.
3. Why can `@ConditionalOnMissingBean(MessagePort.class)` be order-dependent? **Because it only inspects bean definitions already processed at evaluation time**, without seeing future beans.
4. Do `@ConditionalOnClass` and `@ConditionalOnMissingBean` use the exact same kind of input information? **No**: one checks classpath/metadata, the other checks bean definitions.
5. If a class-level condition fails to match, are `@Bean` methods of that class processed as usual? **No**, along the blocked configuration path.
6. If a condition on one `@Bean` method fails to match, are beans from other methods in the same configuration necessarily excluded? **No**.
7. If a bean definition is registered, is the instance guaranteed to have been created? **No**; it may not have been instantiated yet or may be lazy/prototype.
8. Does `@Lazy` make Spring skip registering the bean definition? **No**; it primarily affects instance creation timing.
9. Both commands disabling the demo at parse/register phase print `port.present=false`. Can you use stdout to conclude they are in the same phase? **No**; identical output does not mean identical causes.
10. When you want a default bean to yield to a user bean, what should you do? **Use `@ConditionalOnMissingBean` appropriately in auto-configuration and test the back-off branch**.
11. When a type-based condition misses a bean even though an instance of the right class appears after startup, what should you check? **Declared return type, registration timing, proxies, and available bean definitions**.
12. To quickly test conditions and back-off in a lightweight context, which API fits? **`ApplicationContextRunner`**.

## Official Sources

- [Spring Framework API — ConfigurationCondition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): `getConfigurationPhase()` and parse/register distinction.
- [Spring Framework API — ConfigurationCondition.ConfigurationPhase](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): `PARSE_CONFIGURATION` and `REGISTER_BEAN`.
- [Spring Framework Reference — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): configuration classes and `@Bean`.
- [Spring Boot 3.5 API — ConditionalOnBean](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): matching based on processed bean definitions.
- [Spring Boot 3.5 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): back-off semantics and condition timing.
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): registration via imports, conditions, testing with `ApplicationContextRunner`, and ordering.
- [Spring Boot Reference — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): exclusions and Condition Evaluation Report.
