# proxyBeanMethods=false and Providing Dependencies via @Bean Parameters in Spring Boot Auto-configuration

## 1. Core Idea: Container-Managed Beans vs. Ordinary Java Method Calls

In Spring, a method annotated with `@Bean` is a **factory method** for the container to register and create a bean. If a second `@Bean` method needs the bean provided by the first method, the reliable approach is to **receive the dependency as a parameter**:

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {

    @Bean
    Engine engine() {
        return new Engine("default");
    }

    @Bean
    Vehicle vehicle(Engine engine) {
        return new Vehicle(engine);
    }
}
```

The `Engine` and `Vehicle` classes above are illustrative types without definitions, so the snippet **is not a standalone runnable program**. The key point: `vehicle(Engine engine)` receives the exact `Engine` resolved by the **Spring container**. You do not need—and should not write—`vehicle() { return new Vehicle(engine()); }` just to "reuse" a `@Bean` method.

With `@Configuration(proxyBeanMethods = false)`, calling `engine()` directly from regular Java code runs the body of `engine()` as an ordinary Java method call. If the method body creates `new Engine(...)`, the direct call can create **an extra object outside the bean definition contract**; it is not guaranteed to return the singleton bean managed by the container.

This principle is especially important for **Spring Boot auto-configuration**: in Spring Boot 3.3.x, `@AutoConfiguration` is meta-annotated with `@Configuration(proxyBeanMethods = false)`. Auto-configuration is designed to declare independent factory methods, while relationships between beans are passed through Spring DI.

This lesson explains the interception mechanism, the difference between **"calling a method"** and **"asking Spring to inject a bean"**, a runnable example with Java 17+ and Spring Boot, and common mistakes when building auto-configurations.

## 2. What Exactly Does `proxyBeanMethods` Control?

The `@Configuration` annotation in Spring Framework has a `proxyBeanMethods` attribute:

- `@Configuration` or `@Configuration(proxyBeanMethods = true)`: **full** mode, the default value of `@Configuration`. Spring creates a CGLIB-enhanced subclass to **intercept eligible calls to `@Bean` methods** on the Spring-managed configuration object. This supports *inter-bean method references* and scope behavior—for example, calling the same singleton `@Bean` from another `@Bean` method can return the container-managed object.
- `@Configuration(proxyBeanMethods = false)`: **lite** mode for `@Bean` methods. The container still registers and invokes the factory methods when creating beans, but **direct Java calls from one method to another `@Bean` method are not intercepted by Spring to look up a bean**.
- `@AutoConfiguration` in Spring Boot 3.3.x: this annotation already carries `@Configuration(proxyBeanMethods = false)`; it is a configuration type imported by Boot's auto-config mechanism and does not support expectations of direct inter-bean method interception.

**Setting false does not disable bean registration, does not disable dependency injection, does not change the default singleton scope, and does not disable conditions like `@ConditionalOnMissingBean`.** It only avoids a specific kind of proxy/enhancement meant for **calls to `@Bean` methods on the configuration class**.

### 2.1. Visual Comparison

| Operation | `proxyBeanMethods=true` | `proxyBeanMethods=false` |
| --- | --- | --- |
| Spring recognizes `@Bean` methods in a valid configuration class | Yes | Yes |
| Spring calls the factory method to create the bean | Yes | Yes |
| Spring can inject beans via factory method parameters | Yes | Yes |
| Calling `config.engine()` on a **Spring-managed configuration bean**, under normal circumstances | Call is CGLIB-intercepted and can return the bean per scope | Executes ordinary Java method body; does not look up bean from context |
| Dependency reference style `vehicle(engine())` | Can work via interception in full mode | Risks creating extra objects, bypassing lookup and conditions |
| `final` configuration class / `@Bean` method | CGLIB enhancement has limitations since it cannot override | Does not need that enhancement |
| Suitable for Boot 3.x custom auto-configuration | Not an assumption you should rely on | Is the exact mode of `@AutoConfiguration` |

Keep the condition **"Spring-managed configuration bean"** in mind for the `true` column: if you manually do `new FeatureConfiguration()` and call `engine()`, it is still an ordinary Java object and does not automatically have the context's CGLIB enhancement. Moreover, interception and its outcome depend on scope, lifecycle, and calling context; do not overgeneralize to "`true` turns every method call everywhere into a bean lookup".

### 2.2. Why Does Full Mode Use CGLIB?

To intercept an ordinary Java call such as `engine()`, Spring must be able to alter method execution behavior on the configuration object. In full mode, Spring uses a dynamic subclass to override the necessary methods and check the container before deciding whether to return an existing bean or run the creation logic.

This approach requires the class/methods to be subclassable/overridable, so a full configuration class or factory methods needing interception cannot arbitrarily be `final`. Lite mode does not need to generate that subclass for bean method calls, fitting configurations that do not use cross-method references.

**Do not confuse this with application-bean AOP.** `proxyBeanMethods=false` refers to enhancement of the **configuration class**, not that beans it creates can never be AOP-proxied (e.g., by `@Transactional` or applicable aspects).

## 3. Spring Boot's `@AutoConfiguration` Defaults to Lite Mode

In Spring Boot 3.3.13, the `@AutoConfiguration` annotation definition includes:

```java
// Conceptual excerpt of the annotation, not complete source code:
@Configuration(proxyBeanMethods = false)
public @interface AutoConfiguration {
    // before, after, beforeName, afterName ...
}
```

An auto-config class, for example:

```java
@AutoConfiguration
public class GatewayAutoConfiguration {

    @Bean
    Backend defaultBackend() {
        return new Backend("default");
    }

    @Bean
    Gateway gateway(Backend backend) {
        return new Gateway(backend);
    }
}
```

Here `@AutoConfiguration` **does not need `@Configuration(proxyBeanMethods=false)` added explicitly**. The annotation's default behavior is already suitable.

Why did Spring Boot choose this?

1. Auto-config classes typically declare **conditional default beans**, such as `@ConditionalOnMissingBean`, to back off for user configuration.
2. Each `@Bean` should describe a factory with clear inputs; factory dependencies should appear as **`@Bean` parameters**, resolved by the container.
3. There is no need to call another `@Bean` via CGLIB just to pass a dependency into a factory, avoiding the cost and constraints of that enhancement.
4. When dependencies are resolved from the context, the factory respects application-provided beans, scopes, qualifiers, and appropriate proxies.

These points **do not guarantee a fixed performance gain for every application**. The primary value is a clear contract and factory organization, especially when bean creation conditions vary depending on the classpath and user configuration.

## 4. Passing Dependencies via `@Bean` Parameters

Core syntax:

```java
@Bean
Gateway gateway(Backend backend) {
    return new Gateway(backend);
}
```

Spring treats the `Backend backend` parameter as a dependency to resolve **from the BeanFactory**, similar in spirit to constructor injection. When creating the `gateway` bean, the container:

1. Identifies the matching `Backend` bean present in the context or creatable from a bean definition.
2. Resolves candidates by type and applicable DI rules: `@Qualifier`, `@Primary`, parameter name when sufficient metadata is present, etc.
3. Supplies the **container-managed dependency object** to the factory method.
4. Takes the `Gateway` object returned by the method and applies the `gateway` bean's lifecycle and scope.

`@Autowired` is not needed on `@Bean` parameters. If a required `Backend` is missing, startup can fail due to an unsatisfied dependency; if multiple unresolvable candidates exist, DI can also fail.

### 4.1. Passing Multiple Dependencies

```java
@Bean
ReportService reportService(ReportRepository repository,
                            Clock clock,
                            MeterRegistry metrics) {
    return new ReportService(repository, clock, metrics);
}
```

This is **illustrative code, not standalone compilable** because the types are not declared/imported. Spring resolves each parameter individually, regardless of whether they come from auto-config, component scan, or application-declared `@Bean`s.

A dependency passed into the constructor of the returned object differs from calling `reportRepository()` on another `@Bean` method in the same configuration. The `repository` parameter has gone through container bean resolution; a direct method call has not.

### 4.2. Resolving Multiple Candidates

If the context has two `Backend` beans, you can specify a qualifier:

```java
@Bean
Gateway gateway(@Qualifier("primaryBackend") Backend backend) {
    return new Gateway(backend);
}
```

This is an illustrative snippet; it requires `org.springframework.beans.factory.annotation.Qualifier` and a corresponding `primaryBackend` bean. If there is only one candidate, no qualifier is needed. If you want a default among candidates, `@Primary` on a bean is another tool. Do not assume that "a parameter whose name matches a bean name" always beats all resolution rules.

### 4.3. Optional Dependencies and Deferred Retrieval

When bean creation depends on the presence of an optional library or bean, auto-configuration usually checks `@ConditionalOnClass`, `@ConditionalOnBean`, or related conditions. If a factory still needs on-demand access to a bean, `ObjectProvider<T>` can fit:

```java
@Bean
Inspector inspector(ObjectProvider<Backend> backends) {
    return new Inspector(backends.getIfAvailable());
}
```

This is also an illustrative snippet (`Inspector` is not declared). `getIfAvailable()` can return `null` when no bean exists; the implementation must handle that. Use optional access only when business logic genuinely allows a missing dependency. For required dependencies, a direct parameter of type `Backend` is clearer and catches errors earlier.

## 5. Complete Example: Back-off Still Works Properly with `@Bean` Parameters

The example runs with **Java 17+**, Maven, and **Spring Boot 3.3.13**. We will test two scenarios:

- `demo.custom=false`: no user `Backend` bean exists; auto-config supplies the default, and `Gateway` receives that default via its factory parameter.
- `demo.custom=true`: the application defines its own `Backend` bean; auto-config backs off per `@ConditionalOnMissingBean`; `Gateway` receives the user bean. Both states produce `SAME_INSTANCE=true`.

Key point: if auto-config directly called `backend()` from `gateway()`, this consistency would break when `proxyBeanMethods=false`.

### 5.1. Project Structure

```text
lite-bean-methods-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/
    │   │   ├── Backend.java
    │   │   └── Gateway.java
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   └── UserBackendConfiguration.java
    │   └── autoconfig/
    │       └── GatewayAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Intentionally place the main class in `com.example.app` and auto-config in `com.example.autoconfig`: auto-config is discovered via the imports file, **not** because it is a subpackage under the application's component scanning.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>lite-bean-methods-demo</artifactId>
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

In this example, `spring-boot-starter` is enough to build a Spring Boot application that runs a runner. No Web starter, database, or external services are needed.

### 5.3. `src/main/java/com/example/api/Backend.java`

```java
package com.example.api;

public record Backend(String id) {
}
```

Uses a Java 17 record to hold immutable data. `id` lets you see which factory created the backend: `"default"` from auto-config or `"user"` from the application.

### 5.4. `src/main/java/com/example/api/Gateway.java`

```java
package com.example.api;

public record Gateway(Backend backend) {
    public String send(String value) {
        return backend.id() + ":" + value;
    }
}
```

The `Gateway` record depends on `Backend`. It is not a bean merely because it has a `backend` field; the bean is registered by a `@Bean` factory below.

### 5.5. `src/main/java/com/example/autoconfig/GatewayAutoConfiguration.java`

```java
package com.example.autoconfig;

import com.example.api.Backend;
import com.example.api.Gateway;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Backend.class)
    Backend backend() {
        return new Backend("default");
    }

    @Bean
    @ConditionalOnMissingBean(Gateway.class)
    Gateway gateway(Backend backend) {
        return new Gateway(backend);
    }
}
```

**Two details decide success:**

1. `@AutoConfiguration` is already equivalent to a `@Configuration(proxyBeanMethods=false)` class in Spring Boot 3.3.x. Do not write code relying on interception between the two factory methods.
2. `Gateway gateway(Backend backend)` **does not call `backend()`**. Spring decides which `Backend` bean exists; if the application already has a user bean, the factory receives that exact user bean.

`@ConditionalOnMissingBean(Backend.class)` backs off when the user has a bean of the same type. `@ConditionalOnMissingBean(Gateway.class)` also allows the application to replace `Gateway` if needed.

### 5.6. `src/main/java/com/example/app/UserBackendConfiguration.java`

```java
package com.example.app;

import com.example.api.Backend;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserBackendConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "custom", havingValue = "true")
    Backend customBackend() {
        return new Backend("user");
    }
}
```

This is configuration **declared by the application**. It also uses `proxyBeanMethods=false` because there is no reason to cross-call `@Bean` methods. When `demo.custom=true`, the `customBackend` bean is registered before auto-config evaluates the missing-bean condition. When false, that user bean does not exist.

The parameter of `gateway(Backend backend)` in the auto-config class does not need to know whether the bean is named `customBackend` or `backend`. It only depends on the **type** `Backend`; there is one matching candidate in each scenario.

### 5.7. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.api.Backend;
import com.example.api.Gateway;
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
    ApplicationRunner report(
            Backend backend, Gateway gateway, ApplicationContext context) {
        return args -> {
            System.out.println("BACKEND=" + backend.id());
            System.out.println("GATEWAY_BACKEND=" + gateway.backend().id());
            System.out.println("SAME_INSTANCE=" + (backend == gateway.backend()));
            System.out.println("AUTO_BACKEND_BEAN=" + context.containsBean("backend"));
            System.out.println("USER_BACKEND_BEAN="
                    + context.containsBean("customBackend"));
            System.out.println("MESSAGE=" + gateway.send("hello"));
        };
    }
}
```

The runner is invoked by Spring once the context is ready. The container injects `Backend` and `Gateway` into the `report(...)` factory method. The line `backend == gateway.backend()` checks **identity**, not just comparing ID strings: the exact same managed backend was injected into both places.

### 5.8. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.custom=false
```

`spring.main.web-application-type=none` makes the example run and exit. `logging.level.root=OFF` reduces Spring logs to make the output easier to read; this property does not affect bean conditions.

### 5.9. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.autoconfig.GatewayAutoConfiguration
```

In Spring Boot 3.x, this file publishes the auto-configuration candidate class. `@AutoConfiguration` placed on a valid class that is neither in imports nor imported by other means will not appear automatically from the annotation alone.

### 5.10. Running Case A: Auto-Config Supplies Default

In the directory containing `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/lite-bean-methods-demo-1.0.0.jar
```

Lines printed by `ApplicationRunner` itself (excluding Maven/JVM/environment messages):

```text
BACKEND=default
GATEWAY_BACKEND=default
SAME_INSTANCE=true
AUTO_BACKEND_BEAN=true
USER_BACKEND_BEAN=false
MESSAGE=default:hello
```

**Explanation:** `demo.custom=false` so `UserBackendConfiguration.customBackend` is not registered. The auto-config's missing-bean condition for `backend` matches, and Spring registers and creates `Backend("default")`. Then, when creating `Gateway`, it supplies **that exact managed bean** through the parameter. Because the default scope is singleton, identity is strictly equal.

### 5.11. Running Case B: Application Supplies Its Own Backend

Keep the same JAR and run:

```bash
java -jar target/lite-bean-methods-demo-1.0.0.jar --demo.custom=true
```

Program stdout:

```text
BACKEND=user
GATEWAY_BACKEND=user
SAME_INSTANCE=true
AUTO_BACKEND_BEAN=false
USER_BACKEND_BEAN=true
MESSAGE=user:hello
```

**Explanation:**

1. Command-line property `demo.custom=true` makes `@ConditionalOnProperty` on the user bean match.
2. Spring already has the `customBackend` bean definition of type `Backend` when evaluating auto-config.
3. `@ConditionalOnMissingBean(Backend.class)` in auto-config does not match, so the default bean named `backend` **is not registered**.
4. `Gateway gateway(Backend backend)` is still created because it **does not depend on calling `backend()`**. DI finds the existing `Backend` bean, which is `customBackend`.
5. The runner receives the same user bean, hence `SAME_INSTANCE=true` and `MESSAGE=user:hello`.

This is the practical benefit of using `@Bean` parameters in auto-config: **application configuration is respected** even when the default bean has backed off.

## 6. Classic Bug: Calling a `@Bean` Method Yourself When `proxyBeanMethods=false`

Suppose you modify only the `gateway` method in `GatewayAutoConfiguration` to:

```java
// Wrong when depending on a container-managed bean.
@Bean
@ConditionalOnMissingBean(Gateway.class)
Gateway gateway() {
    return new Gateway(backend());
}
```

The snippet above is an **illustrative alternative**, not to be kept alongside `gateway(Backend backend)` in the same configuration.

When `proxyBeanMethods=false`:

- `backend()` is called like a plain Java method: it executes `return new Backend("default")`.
- This call does not look up the `Backend` bean currently in the context; even when `@ConditionalOnMissingBean(Backend.class)` has prevented registering the default bean, the body of `backend()` can still be invoked directly.
- If `demo.custom=false`, the container has one managed `Backend("default")`, while `Gateway` holds **a different `Backend("default")` object**. The IDs are equal, but the identities differ: `SAME_INSTANCE=false`.
- If `demo.custom=true`, the container has `Backend("user")`, yet `Gateway` receives an instance created directly via `backend()` with ID `"default"`. The custom backend is ignored and identity is also wrong.

In two illustrative runs after replacing the method, the key fields become:

| Configuration | `BACKEND` provided by container | `GATEWAY_BACKEND` | `SAME_INSTANCE` |
| --- | --- | --- | --- |
| `demo.custom=false` | `default` | `default` | `false` |
| `demo.custom=true` | `user` | `default` | `false` |

**This is not Spring creating two singletons with the same name.** The object produced by the direct Java call `backend()` **is not** the container-managed `backend` bean. It can bypass lifecycle management steps, post-processing, and wrappers/proxies applied by the container to managed beans. Do not assume an out-of-container object has a bean's full lifecycle.

Fix it back to the proper method:

```java
@Bean
@ConditionalOnMissingBean(Gateway.class)
Gateway gateway(Backend backend) {
    return new Gateway(backend);
}
```

### 6.1. Why Is Switching to `proxyBeanMethods=true` Not the Right Fix?

In an ordinary `@Configuration` class, enabling full mode can make direct `@Bean` calls intercepted. However, **Spring Boot 3.3.x `@AutoConfiguration` defaults to false** and is designed around independent factory methods. The clean and durable fix is to let Spring inject dependencies via parameters.

Do not try to turn an auto-config class into a full-mode configuration just to keep code calling `backend()`. Doing so changes the design contract, reintroduces CGLIB constraints, and still obscures dependencies as well as back-off conditions.

## 7. Understanding Scope, Proxies, and Lifecycle Before Comparing Instances

The example above uses the **default singleton** scope: within one `ApplicationContext`, the same `Backend` bean definition normally returns the same managed instance. Therefore `==` identity is an appropriate proof.

With a `@Scope("prototype")` bean, Spring may create a new instance **each time the dependency is resolved**. In that case you cannot assume from two separate injections that they must be the same object. With request/session scope or a scoped proxy, the injected object may be a proxy representing the target for the current scope.

The points to hold onto are:

- **`@Bean` parameter**: goes through container resolution and respects scope/proxy/qualifier.
- **Direct Java call to a factory method**: runs the method body directly; does not automatically obey bean scope, condition, or lifecycle policies.
- **CGLIB of full `@Configuration`**: intercepts eligible *inter-bean calls*, not the same concept as AOP proxies on every service.
- **`@Bean` annotation**: describes how Spring registers a factory; does not turn every call you make to that method into a container operation.

Do not use `==` as a universal test for every scope. In the default example, it is valid because the beans involved are singletons without scoped proxies.

## 8. When to Use Other Approaches Instead of Plain Parameters

In auto-config, prefer factory method parameters for required dependencies. Certain situations call for other tools:

| Situation | Appropriate approach | Notes |
| --- | --- | --- |
| Exactly one bean by type | `@Bean Gateway gateway(Backend backend)` | Clear; Spring fails fast if missing |
| Multiple beans of the same type | `@Qualifier` or `@Primary` | Resolves ambiguity per business rules |
| Bean may be absent | `ObjectProvider<Backend>` or `Optional<Backend>` | Must design behavior when absent |
| Need to obtain the bean at time of use | `ObjectProvider<Backend>` | Each lookup still follows scope; do not assume it always returns a singleton |
| Need a list of multiple plugin/strategy beans | `List<Strategy>`, `Map<String, Strategy>` | Spring collects and orders them; inspect candidates |
| Dependency exists only when a library is present | `@ConditionalOnClass` and separate configuration | Safe way to avoid linking optional classes too early |
| User bean must replace default bean | `@ConditionalOnMissingBean` on default factory | Condition sees bean definitions already processed at evaluation time |

You can inject dependencies via the constructor of the **configuration class**, but direct parameters on `@Bean` keep **each factory self-describing its dependencies**. Do not force every case into one pattern; pick the simple option that fits the lifecycle and resolution rules.

## 9. Common Misconceptions and How to Diagnose Them

### 9.1. "`proxyBeanMethods=false` means `@Bean` does not work."

False. Spring still registers bean definitions from `@Bean` in valid configuration classes and calls the factory when creating beans. Only the interception behavior of **direct Java method calls** changes.

### 9.2. "I have a singleton bean, so calling `backend()` directly must return the singleton."

False in lite mode. Singleton is a policy of the **Spring bean definition**, not a policy automatically enforced on every Java call to a `@Bean` method.

### 9.3. "A `@Bean` factory can call another factory directly because they are in the same class."

This is the exact trap of `proxyBeanMethods=false`. Being in the same class does not turn a Java call into DI; move the dependency into a parameter.

### 9.4. "Because the user bean backed off the default, the default method no longer exists."

Inaccurate. The missing-bean condition prevents the **default's bean definition** from being added to the context. The Java method body still exists; if called directly, it can still run. This explains the failure scenario in section 6.

### 9.5. "Setting false removes all proxies in the application."

False. This is only CGLIB enhancement of the configuration class for `@Bean` method calls. Target beans can still be wrapped by AOP or scoped proxies when applicable.

### 9.6. "`@AutoConfiguration` needs `@Configuration(proxyBeanMethods=false)` added to work properly."

Unnecessary in Spring Boot 3.3.x: `@AutoConfiguration` is already meta-annotated with `@Configuration(proxyBeanMethods=false)`. Focus on designing independent factories and declaring dependencies clearly.

### 9.7. "Everything that works in full mode will automatically work in lite mode."

Not true if the design relies on **direct inter-bean method invocation**. Before switching a regular `@Configuration` from true to false, audit snippets like `return new Thing(otherBean())` and replace them with `Thing thing(OtherBean otherBean)` accordingly.

### 9.8. "Another bean of a different type is created later, so Spring cannot inject it."

Spring can resolve dependencies based on existing bean definitions and create needed beans in dependency order; factories do not need to be called in the order they appear in source files. Certain dependency cycles cannot be resolved automatically, especially with constructor injection, so redesign the relationship instead of calling methods directly to "bypass" DI.

### 9.9. "When a bean is missing, it must be `proxyBeanMethods=false`."

Insufficient evidence. Check whether the auto-configuration was discovered via `AutoConfiguration.imports`, whether `@Conditional...` matched, whether a user bean caused the default to back off, and the specific missing/multiple dependency message.

## 10. Auto-Configuration Self-Check Procedure

1. **Check the actual annotation:** is the class `@AutoConfiguration` or a regular `@Configuration`? Boot 3.3.x `@AutoConfiguration` is already in lite mode; `@Configuration` defaults to full mode unless stated otherwise.
2. **Scan the `@Bean` methods:** each method should read like an independent factory. Look for direct calls to another factory, such as `backend()` inside `gateway()`.
3. **Verify dependencies:** turn them into parameters like `gateway(Backend backend)` when you want the Spring-managed bean.
4. **Check conditions:** `@ConditionalOnMissingBean` on the default backend may not match when the user provides a backend. Ensure gateway still uses the user bean.
5. **Inspect bean definitions and names:** use `ApplicationContext.containsBean`, `getBean`, or test with `ApplicationContextRunner`; do not compare only a field like `id` while ignoring identity.
6. **Enable the condition report:** run the app with `--debug` if you need to see the *Condition Evaluation Report*, remembering to remove or override the demo's `logging.level.root=OFF` so condition output can appear.
7. **Check scopes:** singleton, prototype, or scoped proxies can make instance comparisons differ even when DI is valid.
8. **Test both default and user override:** like `demo.custom=false/true` in this lesson, because direct factory call bugs can be masked when both objects carry the value `"default"`.

Suggested command for the demo:

```bash
java -jar target/lite-bean-methods-demo-1.0.0.jar --demo.custom=true --debug --logging.level.root=DEBUG
```

Read the condition report to verify whether the default bean was applied or backed off. Do not rely on fixed log phrasing tied to a single Boot version; logs can vary by version and configuration.

## 11. Knowledge Check

**Question 1.** In Spring Boot 3.3.x, what state is `proxyBeanMethods` in for `@AutoConfiguration`?

**Answer:** It is meta-annotated with `@Configuration(proxyBeanMethods=false)`. Do not rely on direct inter-bean method interception.

**Question 2.** In lite mode, does calling `new Gateway(backend())` inside the `gateway()` factory method guarantee using the `Backend` bean from the context?

**Answer:** No. `backend()` is a direct Java call and can create a new object not managed by the container.

**Question 3.** Rewrite the safest factory if `Gateway` depends on `Backend`?

**Answer:**

```java
@Bean
Gateway gateway(Backend backend) {
    return new Gateway(backend);
}
```

The parameter is resolved by Spring from the container. This is an illustrative snippet inside a configuration class.

**Question 4.** If the user has `@Bean Backend customBackend()`, will an auto-config declaring `@ConditionalOnMissingBean(Backend.class)` create the default backend?

**Answer:** When used properly and the user bean has been processed at the time the condition is evaluated, the default **backs off**. The `gateway(Backend backend)` factory can still receive the custom backend.

**Question 5.** Why can `SAME_INSTANCE=false` happen even when both IDs are `default`?

**Answer:** One instance can be the context's singleton bean while the other was created by a direct `backend()` call. Identical data values do not mean the same object.

**Question 6.** Does `@Configuration(proxyBeanMethods=false)` prevent Spring from injecting `@Bean` arguments?

**Answer:** No. DI via `@Bean` parameters still works and is the recommended approach when a factory depends on another bean.

**Question 7.** Can using `@Primary` replace the need to pass dependencies via `@Bean` parameters?

**Answer:** No. `@Primary` helps the container pick a candidate when multiple matching beans exist. You still must request the dependency via a parameter/constructor or another container resolution mechanism.

**Question 8.** Does setting `proxyBeanMethods=false` turn off `@Transactional` proxies on services?

**Answer:** No. The two kinds of proxies serve different purposes.

## 12. References

- [Spring Boot 3.3.13 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): confirms `@AutoConfiguration` is meta-annotated with `@Configuration(proxyBeanMethods=false)`.
- [Spring Framework 6.1 — Configuration API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/annotation/Configuration.html): describes `proxyBeanMethods`, full/lite mode, CGLIB, and limits of method interception.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): registering auto-config, `@ConditionalOnMissingBean`, and testing user override scenarios.
- [Spring Framework — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html): differences between inter-bean references and properly supplying dependencies via DI.

**Takeaway:** Treat every `@Bean` method in an auto-configuration as **a factory invoked by the container**, and declare dependent beans via **factory parameters**. With `proxyBeanMethods=false`, writing `gateway(Backend backend)` preserves managed dependencies, respects user overrides, and avoids out-of-container objects created by direct `backend()` calls.
