# Conditions Are Evaluated When Building the Context, Not as Per-Call Self-Updating Switches

## 1. Main Idea: Spring Selects Beans When Building the ApplicationContext

Annotations such as **@Conditional**, **@ConditionalOnProperty**, **@ConditionalOnClass**, **@ConditionalOnBean**, and **@ConditionalOnMissingBean** are used by Spring/Spring Boot to decide **which configuration classes or bean definitions enter the ApplicationContext** during configuration parsing and registration.

**They do not turn into switches that are re-evaluated every time the application invokes a method on a bean.**

If **demo.feature.enabled=false** when Spring evaluates a `@Bean` method carrying **@ConditionalOnProperty(havingValue="true")**, that bean's definition is skipped. After the application has finished starting up, changing the value in **Environment** to true **does not automatically re-add** the skipped definition. Likewise, if the bean was registered at startup with the property set to true, changing the property to false afterward **does not automatically remove or destroy the bean**.

We must distinguish:

- **Currently readable configuration**: the value of `Environment` or property sources at a given moment.
- **Condition evaluation**: decisions made while building configurations and bean definitions.
- **Bean definition**: the container's blueprint describing how to create the bean, its scope, dependencies, and other traits.
- **Bean instance**: the actual object created according to Spring's lifecycle.
- **Runtime method call**: when business code invokes a method on an existing instance or proxy.

Only the final layer happens on each regular invocation. Reading conditions during context-build phases does not make them runtime listeners.

### Minimal Example

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
FeatureClient featureClient() {
    return () -> "ready";
}
~~~

This is an illustrative snippet; compiling requires the `FeatureClient` class and Spring imports inside a configuration class. This snippet says: **register the FeatureClient bean when the condition passes while processing `@Bean`**. It does not say: "every time `FeatureClient.call()` is invoked, re-read the property and create/destroy the bean".

## 2. When Are Conditions Evaluated?

A typical Spring Boot startup sequence:

~~~text
SpringApplication.run(...)
        |
        v
Prepare Environment and PropertySources
        |
        v
Initialize ApplicationContext
        |
        v
Read @Configuration, @Import, auto-configuration candidates
        |
        v
Evaluate appropriate conditions during
configuration parsing and bean definition registration
        |
        v
Register BeanDefinitions of selected branches
        |
        v
Process BeanFactory, post-processors, inject dependencies
and instantiate required eager singletons
        |
        v
Context refresh completes
        |
        v
ApplicationRunner and business operations
        |
        +--> Call bean methods
        +--> Can read Environment
        +--> Does not automatically re-evaluate conditions on every method call
~~~

This diagram explains the phases, not an exact replica of every internal method of Spring Framework. A condition may be evaluated in the **PARSE_CONFIGURATION** or **REGISTER_BEAN** phase, and an implementation may be queried multiple times by the framework while processing metadata. Therefore, do not rigidly assert that "every condition always runs strictly once".

What remains architecturally stable is that **@Conditional decides container structure during configuration processing steps**, rather than watching properties like a runtime toggle.

### 2.1. Why Is @ConditionalOnBean Sensitive to Ordering?

**@ConditionalOnBean** and **@ConditionalOnMissingBean** rely on the bean state already processed by Spring at the moment the condition is checked. For that reason Spring Boot processes auto-configurations after user-declared configurations, and provides before/after ordering between auto-configurations when needed.

Once the application has started, Spring **does not maintain a continuous watcher** that re-evaluates all earlier `@ConditionalOnMissingBean` annotations every time a bean is added or removed. By default, it is a **definition registration** decision.

### 2.2. Class-Level Conditions Differ from Method-Level Conditions

Class-level example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "demo.mail",
    name = "enabled",
    havingValue = "true"
)
class MailConfiguration {

    @Bean
    MailSender mailSender() {
        return new MailSender();
    }
}
~~~

This example uses a hypothetical `MailSender` type, not complete source code. A condition on a class can skip the entire configuration branch, whereas a condition on an individual `@Bean` method can exclude just that method. Regardless of which level it sits at, the annotation is not automatically re-evaluated each time a client sends an email.

## 3. What Does @ConditionalOnProperty Read?

Example:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

Spring Boot checks the key **demo.feature.enabled** from **Environment** at evaluation time. With `havingValue` set to true, the property must match the value true; **matchIfMissing=false** means if the property is absent, the condition fails.

| Property when building context | Condition on @Bean passes? | Bean definition of that method |
| --- | --- | --- |
| true | Yes | May be registered if other conditions also pass |
| false | No | Skipped |
| Absent | No | Skipped |
| Value other than true | No | Skipped |

The table only describes one condition on one `@Bean`; a bean of the same type could still be registered by another source, and an auto-configuration class could still be excluded.

**What matters is timing**: the current property after startup can differ from the property the condition saw at registration time.

### 3.1. Property Sources Can Change; the Bean Graph Does Not Automatically Change

Suppose Spring sees the property as false and skips `FeatureClient`. After refresh, code adds a high-precedence **MapPropertySource** containing **demo.feature.enabled=true**. At that point:

- **Environment.getProperty("demo.feature.enabled")** can return true.
- A service that calls **Environment.getProperty(...)** itself on each operation can return a different result.
- **ObjectProvider<FeatureClient>** still cannot find the bean, because **@ConditionalOnProperty** does not automatically re-register a `BeanDefinition` that was skipped.

Conversely, if `FeatureClient` was registered when the property was true, changing `Environment` to false **does not automatically remove** `FeatureClient`.

### 3.2. Does Editing application.properties Make a Difference?

Changing the contents of an **application.properties** file while the process is running **does not mean** Spring Boot automatically re-reads the file and refreshes the context. File data is normally loaded into `Environment` at startup. Applying changes requires a supported reload mechanism or starting a new context/application; and a reload mechanism does not necessarily re-run every bean's condition.

The hands-on lab below **deliberately modifies `Environment` in memory** to observe both layers. It does **not** assume `application.properties` hot-reloads automatically.

## 4. Runnable Example with Java 21 and Spring Boot 3.3.13

Goal: within the same Spring Boot process, change the `Environment` value **after refresh**, and observe that bean presence/absence does not update automatically.

We write:

1. **FeatureClient**: an interface for which auto-configuration can create a bean.
2. **FeatureAutoConfiguration**: has `@Bean FeatureClient` annotated with **@ConditionalOnProperty**.
3. **RuntimeGate**: always exists; its method reads `Environment` **on every call**.
4. **DemoApplication**: after startup completes, uses **ApplicationRunner** to change the property in `Environment` and print before/after results.

Structure:

~~~text
condition-lifecycle-demo/
├── pom.xml
└── src/main/
    ├── java/dev/course/
    │   ├── api/FeatureClient.java
    │   ├── autoconfig/FeatureAutoConfiguration.java
    │   └── app/
    │       ├── RuntimeGate.java
    │       └── DemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The application class is in package **dev.course.app**. Auto-configuration belongs to package **dev.course.autoconfig**, which lies outside the app's default component scan scope, so the auto-configuration class enters the application via the imports file rather than being picked up accidentally by component scan.

### 4.1. pom.xml

~~~xml
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
    <groupId>dev.course</groupId>
    <artifactId>condition-lifecycle-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
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
~~~

The base starter suffices for a context example without a web server. No network connection is needed when running the JAR after dependencies have been downloaded and built.

### 4.2. FeatureClient.java

**src/main/java/dev/course/api/FeatureClient.java**

~~~java
package dev.course.api;

@FunctionalInterface
public interface FeatureClient {
    String call();
}
~~~

`FeatureClient` does not read `Environment` itself. It is solely the API of the conditionally registered bean.

### 4.3. FeatureAutoConfiguration.java

**src/main/java/dev/course/autoconfig/FeatureAutoConfiguration.java**

~~~java
package dev.course.autoconfig;

import dev.course.api.FeatureClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    FeatureClient featureClient() {
        return () -> "ready";
    }
}
~~~

When the property is true during context construction, Spring registers the `BeanDefinition` of `FeatureClient` from this method. When false, the definition is skipped. **After the context has refreshed, there is no logic in the code above to create/destroy the bean when the property changes.**

### 4.4. Registering the Candidate via AutoConfiguration.imports

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.course.autoconfig.FeatureAutoConfiguration
~~~

In Spring Boot 3.x, the imports file is how a library publishes auto-configuration candidates. Having `@AutoConfiguration` on source code without an appropriate discovery mechanism does not automatically ensure Boot imports a class outside component scan.

### 4.5. RuntimeGate.java: Reading Environment on Every Call

**src/main/java/dev/course/app/RuntimeGate.java**

~~~java
package dev.course.app;

import org.springframework.core.env.Environment;

public final class RuntimeGate {
    private final Environment environment;

    public RuntimeGate(Environment environment) {
        this.environment = environment;
    }

    public String state() {
        boolean enabled = environment.getProperty(
            "demo.feature.enabled", Boolean.class, false);
        return enabled ? "ON" : "OFF";
    }
}
~~~

`RuntimeGate` differs from `FeatureClient`: the **state()** method always queries `Environment` again. If `Environment` actually changes, the result of a later method call can differ. However, the `RuntimeGate` class does **not** make Spring re-run `FeatureClient`'s `@ConditionalOnProperty`.

### 4.6. DemoApplication.java: Modifying a PropertySource After Refresh

**src/main/java/dev/course/app/DemoApplication.java**

~~~java
package dev.course.app;

import java.util.HashMap;
import java.util.Map;

import dev.course.api.FeatureClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RuntimeGate runtimeGate(Environment environment) {
        return new RuntimeGate(environment);
    }

    @Bean
    ApplicationRunner compare(
            ObjectProvider<FeatureClient> clients,
            ConfigurableEnvironment environment,
            RuntimeGate gate) {

        return args -> {
            boolean before = environment.getProperty(
                "demo.feature.enabled", Boolean.class, false);

            System.out.println("property.before=" + before);
            System.out.println("bean.before=" +
                (clients.getIfAvailable() != null));
            System.out.println("gate.before=" + gate.state());

            Map<String, Object> overrides = new HashMap<>();
            overrides.put(
                "demo.feature.enabled",
                Boolean.toString(!before));

            environment.getPropertySources().addFirst(
                new MapPropertySource("late-override", overrides));

            System.out.println("property.after=" +
                environment.getProperty(
                    "demo.feature.enabled", Boolean.class, false));
            System.out.println("bean.after=" +
                (clients.getIfAvailable() != null));
            System.out.println("gate.after=" + gate.state());
        };
    }
}
~~~

**Notes on runnability:**

- **ApplicationRunner** executes after Spring has already refreshed the context. Thus when the runner adds `MapPropertySource`, Spring has already decided which bean definitions belong to the `ApplicationContext`.
- **MapPropertySource** is added via **addFirst**, giving it higher precedence than older property sources. That lets the test intentionally flip false to true or true to false.
- **ObjectProvider.getIfAvailable()** returns the bean if present, or null if absent. It can instantiate a lazy bean if its definition already exists, but it does not register a skipped definition.
- The **state()** method is called before and after the change; it demonstrates genuine runtime lookup.
- There is no context rebuild API, no `BeanDefinition` removal, and no singleton bean deletion. Every change stays inside `Environment`.

### 4.7. application.properties

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
demo.feature.enabled=false
~~~

The property defaults to false. It can be overridden via command-line arguments when **starting a new process**. The logging lines merely keep the program's stdout clean.

### 4.8. Build

In the **condition-lifecycle-demo** directory:

~~~bash
mvn -q -DskipTests package
~~~

Requires JDK 21 and Maven 3.9+. After building successfully, **target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar** will be produced.

### 4.9. Run A: Startup False Then Change Environment to True

~~~bash
java -jar target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

Six lines printed by `ApplicationRunner`:

~~~text
property.before=false
bean.before=false
gate.before=OFF
property.after=true
bean.after=false
gate.after=ON
~~~

Explanation:

1. When building the context, `Environment` had **demo.feature.enabled=false**, so the conditional `@Bean` method was not registered.
2. The runner reads property false, finds no `FeatureClient` bean, and `RuntimeGate` reports `OFF`.
3. The runner adds a new property source with value true; `Environment` and `RuntimeGate` see true/`ON`.
4. **`FeatureClient` is still absent.** The condition skipped during the earlier build step does not rerun automatically to register the bean.

### 4.10. Run B: Startup True Then Change Environment to False

Start a **new process**:

~~~bash
java -jar target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true
~~~

Six lines printed by `ApplicationRunner`:

~~~text
property.before=true
bean.before=true
gate.before=ON
property.after=false
bean.after=true
gate.after=OFF
~~~

Explanation:

1. Before Spring evaluates conditions, the command-line argument **--demo.feature.enabled=true** takes effect and allows `FeatureClient` to be registered.
2. After refresh, the runner changes `Environment` to false and `RuntimeGate` reports `OFF`.
3. **`FeatureClient` still exists.** Spring does not automatically remove a bean because `Environment` changed after the bean definition was processed.

### 4.11. Comparison Results

| Observation | Context A: startup false | Context B: startup true |
| --- | --- | --- |
| Property when Spring selects beans | false | true |
| FeatureClient registered | No | Yes |
| Property after in-memory change | true | false |
| FeatureClient after change | Still absent | Still present |
| RuntimeGate.state() after change | ON | OFF |
| Condition auto-reruns after state() call? | No | No |

The expected outputs above are the lines printed by application code, excluding any lines added by the Java/Maven environment or external agents. Both runs create **two separate ApplicationContexts**, not one context refreshing itself via a property toggle.

## 5. Why Is a Condition Not Like a Runtime Feature Flag?

### 5.1. Conditions Shape the Bean Graph

Conditional annotations are well suited for deciding:

- Whether to create a default `DataSource`, `Client`, or `CacheManager`.
- Whether to apply servlet/reactive configuration based on classpath and application type.
- Whether to yield a default bean to user configuration.
- Whether to enable a library integration when startup properties permit.

These choices belong to **wiring** — how the container is assembled.

### 5.2. Runtime Flags Control Behavior on an Existing Bean

An application that needs to toggle behavior right between two HTTP requests can place logic in the execution path:

~~~java
public String process() {
    if (!environment.getProperty(
            "demo.feature.enabled", Boolean.class, false)) {
        return "SKIPPED";
    }
    return "PROCESSED";
}
~~~

This snippet illustrates a method inside a bean holding an **environment** field, not a standalone runnable class. The method actively reads the latest value each time it is called. It does **not** add or remove the definition of the bean containing that method.

If the environment uses a dedicated feature flag service, it can read snapshots, subscribe to updates, or cache per that service's contract. Yet update latency, cross-instance consistency, and concurrency must be designed intentionally.

### 5.3. Small Runtime Switch Using AtomicBoolean

A standalone Java state example (without a main method):

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class RuntimeSwitch {
    private final AtomicBoolean enabled = new AtomicBoolean(false);

    public void setEnabled(boolean next) {
        enabled.set(next);
    }

    public String handle() {
        return enabled.get() ? "RUN" : "SKIP";
    }
}
~~~

**AtomicBoolean** lets threads read/write the flag with clear memory visibility rules in the JVM, yet changing it also does not make Spring register or destroy beans. That is runtime logic owned by the application.

**Warning:** a runtime flag set to OFF does not necessarily stop connection pools, background threads, scheduled tasks, or resources a bean has already created. If you genuinely need to shut down a subsystem, you need dedicated lifecycle APIs, timeouts, cleanup, and concurrency tests.

## 6. Easily Misunderstood Cases

### 6.1. `@Lazy` Does Not Make Conditions Dynamic

~~~java
@Bean
@Lazy
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
FeatureClient lazyFeatureClient() {
    return () -> "lazy";
}
~~~

This is a snippet, not a standalone file. **@Lazy** can defer bean instance creation until needed. However, the **BeanDefinition** of `lazyFeatureClient` was already decided while building the context. If the property was true when deciding the definition and later became false before the bean was requested, the lazy bean can still be created from the registered definition. If the definition was skipped from the start, setting the property to true after startup does not add it automatically.

### 6.2. Prototype Does Not Re-Evaluate Conditions on Every `getBean`

~~~java
@Bean
@Scope("prototype")
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
FeatureClient newClient() {
    return () -> "prototype";
}
~~~

This is an illustrative snippet. Prototype scope changes **how many times an instance is created** from an existing bean definition. It does not turn `@ConditionalOnProperty` into a condition re-checked on every `getBean`.

### 6.3. `@Profile` Also Does Not Auto-Update the Bean Graph

**@Profile("dev")** is a condition selecting configurations/beans based on active profiles when Spring builds the context. Changing the active profiles list after refresh does not automatically create or delete `@Profile`-annotated beans. When you want a different bean graph per profile, initialize a new context with the right profile from the start.

### 6.4. `@ConditionalOnMissingBean` Is Not a Registry Listener

If a user bean already existed when auto-configuration was processed, the default with `@ConditionalOnMissingBean` is not registered. Later destroying a user bean or dynamically manipulating the registry does not make Spring automatically recreate the skipped default bean. Runtime registry manipulation is a separate advanced mechanism requiring careful lifecycle/dependency management.

### 6.5. `@Value` and `@ConfigurationProperties` Do Not Automatically Re-Read on Every Call

**@Value** is normally resolved/injected when Spring creates the bean. An injected field does not automatically query `Environment` on every call to your getter.

**@ConfigurationProperties** is normally bound into an object during initialization. Afterward, editing files or property sources does not automatically rebind the object on every method call. If you want runtime rebinding, you need a purposefully designed/added mechanism rather than inferring it from plain annotation binding.

### 6.6. Modifying System Properties May Not Override a Higher-Precedence Source

Java's **System.setProperty** can alter one property source, yet `Environment` combines multiple sources by precedence order. If a higher-precedence source still holds the old value, **Environment.getProperty** may not reflect the updated system property.

The runnable example deliberately uses **addFirst(MapPropertySource)** to guarantee subsequent reads see the flipped value. Even when the new value is read, the bean graph structure still does not change on its own.

## 7. Restart, Refresh, and Multi-Instance Systems

### 7.1. Creating a New Context Evaluates Conditions for the New Context

To change the set of beans in an easily reasoned way, **restart the application** or **create a new ApplicationContext** with `Environment` properly configured. Spring then parses configurations and evaluates conditions for a fresh initialization pass.

Do not call **ConfigurableApplicationContext.refresh()** arbitrarily on an already running Boot context assuming it is a safe "rebuild bean graph" operation. Several context types do not support repeated refreshes that way; running dependencies also require cleanup and rollout.

### 7.2. Spring Cloud `@RefreshScope` Is a Different Mechanism

An application with appropriate Spring Cloud support can use **@RefreshScope** and refresh mechanisms to renew certain managed beans or values. However:

- This capability **is not enabled by default** with just a basic Spring Boot starter.
- Refreshing a group of beans is not equivalent to **re-registering/removing every `@ConditionalOnProperty` and every auto-configuration** as in starting a fresh context.
- You must review specific versions, contracts, endpoint security, lifecycles, and tests.

Therefore, do not jump from "there is `@RefreshScope` somewhere" to "every condition is a live switch per request".

### 7.3. Multiple Pods/Processes Mean Multiple Contexts

If a service has multiple instances, each JVM has its own `ApplicationContext`. Changing a property or runtime flag in one process does not automatically propagate to other processes. A real feature-flag system requires distribution/sync mechanisms and defined consistency guarantees. When changing the bean graph requires a restart, a controlled rolling restart is usually easier to manage than attempting dynamic registry edits.

## 8. Diagnostics: Distinguishing Current Properties from Startup Results

### 8.1. Condition Evaluation Report

With the example project, you can enable diagnostic logs via:

~~~bash
java -jar target/condition-lifecycle-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

Look for **FeatureAutoConfiguration** and **featureClient**. When started with property false, the `@Bean` condition is a negative match; when started with true, the condition can be a positive match. Report output varies by version and logging configuration.

**Important:** The Condition Evaluation Report describes the results of condition evaluations when building configurations. It is **not** a live truth table staying in sync with current properties if `Environment` was altered after refresh.

When using Actuator with proper exposure/security configuration, **/actuator/conditions** and **/actuator/beans** let you inspect conditions and beans currently known to the container. These endpoints do not trigger re-evaluation of all bean definitions.

### 8.2. Inspecting BeanDefinitions and Bean Instances

- **BeanFactory.containsBeanDefinition(name)** queries local definitions by name.
- **ApplicationContext.containsBean(name)** queries whether the container knows a bean by name, which can differ from local definition queries in some cases.
- **ObjectProvider.getIfAvailable()** retrieves the bean if a definition exists; sometimes fetching the bean initializes a lazy instance.
- **Condition report** helps explain why configuration branches were selected or skipped.
- **BeanCreationException** and stack traces help pinpoint instance creation errors after a definition was accepted.

Do not conflate these checks when debugging.

### 8.3. ApplicationContextRunner for Testing Conditions

For library auto-configuration code, **ApplicationContextRunner** from `spring-boot-test` is a useful tool for creating isolated contexts with different properties. You can test both startup-true and startup-false cases, asserting bean presence/absence as intended.

Conceptual example, **not a standalone test file**:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(FeatureAutoConfiguration.class))
    .withPropertyValues("demo.feature.enabled=false")
    .run(context ->
        assertThat(context).doesNotHaveBean(FeatureClient.class));
~~~

To run an actual test example, you need the **spring-boot-starter-test** dependency in test scope, imports, and a complete JUnit test class. The key lesson is that **each runner run builds a new context**, rather than modifying properties on an old context and expecting beans to appear automatically.

## 9. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`@ConditionalOnProperty` checks on every service call." | Conditions decide registration during configuration processing. |
| "Changing Environment to true makes skipped beans appear." | Environment can change; the bean graph does not rebuild automatically. |
| "Changing property to false auto-destroys singletons." | Registered singletons do not disappear because a property value changes. |
| "Spring Boot watches application.properties and rebuilds beans by default." | There is no such default mechanism. |
| "`@Lazy` checks `@Conditional` when creating the instance." | Lazy defers the instance; the definition was already decided. |
| "Prototype means the condition runs on every getBean." | Prototype creates a new instance from an existing definition. |
| "Adding `@Profile` after refresh activates the bean." | Profile conditions belong to context construction. |
| "`@ConfigurationProperties` auto-rebinds at all times." | Binding does not repeat on every business call. |
| "`@Value` is a continuous Environment lookup." | Values are typically injected during initialization. |
| "`@RefreshScope` means all Boot conditions are live." | It is an extension mechanism, not equivalent to re-evaluating all auto-configuration. |
| "The current condition report surely uses new runtime properties." | You must distinguish evaluation time from observation time. |
| "Runtime flag OFF automatically releases resources." | Processing behavior and resource lifecycle are two separate responsibilities. |

## 10. Self-Check Questions

**Q1.** Start up with **demo.feature.enabled=false**; after refresh, add a property source with true. Does `FeatureClient` appear automatically?

**Answer:** No. `featureClient`'s `BeanDefinition` was skipped when the condition did not pass. Changing `Environment` later does not trigger automatic re-registration.

**Q2.** Start up with property true; after refresh, change it to false. Is `FeatureClient` automatically removed?

**Answer:** No. Already registered beans remain unless the program uses a dedicated lifecycle/registry mechanism.

**Q3.** Why does the project print **property.after=true** and **bean.after=false** in the same run?

**Answer:** The new property was added to `Environment` after context refresh, yet Spring does not re-evaluate conditions to create previously skipped beans.

**Q4.** Why is **gate.after=ON** while `FeatureClient` is still absent?

**Answer:** `RuntimeGate` actively reads `Environment` on every call. The `FeatureClient` bean was decided by an annotation condition when the container was built.

**Q5.** If `@Lazy` is used on `FeatureClient`, and after startup the property changes to false before the first bean retrieval, does `@ConditionalOnProperty` run again?

**Answer:** No. `@Lazy` only changes instance creation timing; it does not turn the condition into a runtime switch.

**Q6.** Does requesting a prototype bean twice create two instances? Does the condition automatically run again on the second request?

**Answer:** Prototype usually creates a new instance per container request, yet the bean definition registration condition does not rerun on each `getBean`.

**Q7.** To change behavior for the next request, what should you use?

**Answer:** You can use a runtime gate/feature flag actively read in the execution path. If resources must be created/destroyed, you must also design a lifecycle manager, not just bean registration conditions.

**Q8.** To change the set of auto-configured beans by property without building a custom refresh mechanism, what is the simplest approach?

**Answer:** Restart the application or create a new context with the property set before the context is built.

## 11. Project Application Checklist

When using a condition or feature toggle, ask:

1. **Startup decision or runtime decision?** Startup wiring uses `@Conditional`; per-call behavior uses runtime checks.
2. **Changing the bean graph or only changing a method's execution path?** Those are two different needs.
3. **How are configuration sources updated?** File edits, remote config, `MapPropertySource`, and flag services each have their own mechanisms.
4. **Is multi-instance synchronization required?** One JVM does not represent the entire cluster.
5. **Do threads/connections/jobs need to stop?** A runtime flag OFF does not guarantee cleanup by itself.
6. **Have both startup-true and startup-false contexts been tested?** Create separate contexts for each case.
7. **Are you inspecting properties, the condition report, BeanDefinitions, or instances?** Each measurement speaks to a distinct layer.

### Summary

**`@ConditionalOnProperty` and similar conditions shape the Spring `ApplicationContext` structure when Spring parses/registers configurations, not as per-method-call self-updating switches.** An `Environment` can be modified intentionally after startup and business code actively re-reading it can observe new results. Yet that **does not automatically add or remove bean definitions already chosen during context construction**.

Use conditions to select beans/configurations at startup; use runtime feature flags or specialized lifecycle/update mechanisms when the goal is changing the behavior of an already running application.

### References

- Spring Framework, *Using the @Conditional Annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/conditional.html
- Spring Framework, **Condition** API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Condition.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, **@ConditionalOnProperty** API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
