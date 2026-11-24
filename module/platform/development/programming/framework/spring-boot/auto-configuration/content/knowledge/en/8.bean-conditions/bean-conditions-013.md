# Placing Conditions at the Class Level vs. Individual `@Bean` Methods to Control Back-Off Granularity in Spring Boot

## 1. What Does "Back Off" Mean?

In Spring Boot, auto-configuration provides default beans so applications work quickly out of the box, yet must usually **back off** when the application has already declared a suitable bean. The common mechanism is `@ConditionalOnMissingBean`: register the annotated configuration or bean only when **no bean matching the criteria exists yet** in the `BeanFactory` at the time Spring evaluates the condition.

"Backing off" here means **not registering the default bean in the first place**, which is different from overriding an existing bean definition. It also differs from `@Primary`: `@Primary` only prioritizes a bean during dependency injection when multiple candidates exist, without removing the default bean.

The key question: if an auto-configuration creates **multiple beans**, and the user wants to customize one of them, should the remaining default beans still exist? **Where you place the annotation determines the blast radius.**

## 2. Mechanism by Condition Placement

### 2.1. Placing on the Configuration Class: A Single Gate for the Entire Configuration

```java
@AutoConfiguration
@ConditionalOnMissingBean(NotificationSender.class)
public class NotificationAutoConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

Here, Spring evaluates the condition against the **`NotificationAutoConfiguration` class**. If an application-defined `NotificationSender` already exists, the configuration class is not registered; neither `notificationSender()` **nor** `retryPolicy()` contributes a bean. Even though `RetryPolicy` is not directly tied to the sender, it is still excluded by the shared gate.

A class-level condition must **explicitly specify its criteria**, such as `@ConditionalOnMissingBean(NotificationSender.class)`, because there is no `@Bean` method return type to infer from. A class-level condition does not automatically check individually for every bean type that the class might create.

This technique fits when **the entire group of beans is an indivisible functional unit**, and a user-provided bean is considered a replacement for the whole group. If beans can be customized independently, a shared gate is usually too coarse.

### 2.2. Placing on Each `@Bean`: Independent Back-Off

```java
@AutoConfiguration
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

Now each method has its own condition:

- If the application defines `NotificationSender`, **only** the default sender bean backs off.
- If the application has not defined `RetryPolicy`, the default retry bean **is still registered**.
- If the application supplies `RetryPolicy` without a sender, the default sender still works.

The `@Configuration`/`@AutoConfiguration` class can still be registered even if some `@Bean` methods are skipped. This is usually the right choice when building a starter with **multiple independent extension points**.

With `@ConditionalOnMissingBean` placed directly on a `@Bean` method, if `value`, `type`, `name`, or `annotation` is omitted, Spring Boot defaults to using the **declared return type** of the method for matching. Writing the type explicitly as in the example makes the intent clearer, especially when APIs separate interfaces and implementations.

### 2.3. Comparing Concrete Scenarios

Suppose the auto-configuration provides two defaults: `NotificationSender` and `RetryPolicy`; the class-level condition checks only for the absence of `NotificationSender`.

| Beans Declared by the Application | Class-Level Condition on `NotificationSender` | Separate Conditions on Two `@Bean` Methods |
| --- | --- | --- |
| No beans declared | Both default sender and retry exist | Both default sender and retry exist |
| Only custom sender | Both defaults skipped; **no default retry remains** | Default sender skipped; **default retry still exists** |
| Only custom retry | Configuration still runs and can create **a second default retry** because the class gate does not check `RetryPolicy` | Default sender exists; custom retry is used |
| Both custom sender and custom retry | Entire configuration backs off | Each corresponding default backs off |

The third row highlights an easy-to-miss design flaw: `@ConditionalOnMissingBean(NotificationSender.class)` on the class **does not guarantee** a default `RetryPolicy` bean will back off. If two beans of the same type have different names, the application can end up with two candidates and hit ambiguity errors when injecting by type.

## 3. Runnable Spring Boot 3.3.x / Java 17+ Example

The example uses a small Maven application. Package `demo.app` is the application's component-scan package; package `demo.autoconfigure` lies outside component-scan scope and is properly loaded by Spring Boot via `AutoConfiguration.imports`. Initially, the application defines a custom sender without providing its own retry policy.

Key file layout:

```text
pom.xml
src/main/java/demo/api/NotificationSender.java
src/main/java/demo/api/RetryPolicy.java
src/main/java/demo/autoconfigure/NotificationAutoConfiguration.java
src/main/java/demo/app/DemoApplication.java
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**`pom.xml`**

```xml
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
    <groupId>demo</groupId>
    <artifactId>bean-condition-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

**`src/main/java/demo/api/NotificationSender.java`**

```java
package demo.api;

public interface NotificationSender {
    String send(String message);
}
```

**`src/main/java/demo/api/RetryPolicy.java`**

```java
package demo.api;

public record RetryPolicy(int maxAttempts) {
}
```

**`src/main/java/demo/autoconfigure/NotificationAutoConfiguration.java`** — **per-bean** back-off version:

```java
package demo.autoconfigure;

import demo.api.NotificationSender;
import demo.api.RetryPolicy;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
demo.autoconfigure.NotificationAutoConfiguration
```

This name must match the fully qualified auto-configuration class name. In Spring Boot 3.x, this is the mechanism for declaring auto-configuration candidates in a library/starter. Do not use component scanning to auto-detect auto-configuration classes.

**`src/main/java/demo/app/DemoApplication.java`**

```java
package demo.app;

import demo.api.NotificationSender;
import demo.api.RetryPolicy;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    public NotificationSender userSender() {
        return message -> "user:" + message;
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {
            NotificationSender sender =
                    context.getBean(NotificationSender.class);
            Map<String, RetryPolicy> policies =
                    context.getBeansOfType(RetryPolicy.class);

            String retry = policies.isEmpty()
                    ? "none"
                    : Integer.toString(
                            policies.values().iterator().next().maxAttempts());

            System.out.println("sender=" + sender.send("ping"));
            System.out.println("retry=" + retry);
        }
    }
}
```

Build and run from the directory containing `pom.xml` (with JDK 17+ and Maven):

```bash
mvn -q -DskipTests package
java -jar target/bean-condition-demo-0.0.1-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

**Expected stdout for the per-`@Bean` condition version:**

```text
sender=user:ping
retry=3
```

Explanation: the application's `userSender()` registers a `NotificationSender`, so the default `notificationSender()` condition does not match. However, there is no `RetryPolicy` yet, so the default `retryPolicy()` is still registered with `maxAttempts = 3`.

### Try Moving the Condition to the Class Level

Replace the **entire content** of `NotificationAutoConfiguration.java` with the following version; keep all other files unchanged:

```java
package demo.autoconfigure;

import demo.api.NotificationSender;
import demo.api.RetryPolicy;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnMissingBean(NotificationSender.class)
public class NotificationAutoConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return message -> "default:" + message;
    }

    @Bean
    public RetryPolicy retryPolicy() {
        return new RetryPolicy(3);
    }
}
```

Re-run the two build/run commands above. **Expected stdout:**

```text
sender=user:ping
retry=none
```

The application-provided sender still works. But because the class-level condition did not match, `NotificationAutoConfiguration` contributes **no** beans at all, including `RetryPolicy`; the application no longer has a default retry policy.

Try removing `userSender()` from `DemoApplication` and rebuilding: with no custom sender, **both placement approaches** provide the default sender and retry policy. The output then is `sender=default:ping` and `retry=3`. This shows that the main difference emerges when users customize only **part** of the default suite.

## 4. Choosing Condition Placement by Customization Boundary

**Choose a class-level condition** when multiple beans form **a group that should not exist separately**. For example, an adapter whose entire configuration depends on the presence of a library: `@ConditionalOnClass(VendorClient.class)` can be placed on a dedicated configuration class so the group loads only when the dependency is present. A feature flag can also serve as a shared gate:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.notification",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class NotificationAutoConfiguration {
    // Default @Bean methods, where each bean can still have its own condition.
}
```

The snippet above only illustrates a shared gate; rather than using this class directly alongside the runnable example class, **combine the class-level annotation** with the `@Bean` methods shown earlier. The class-level gate answers "is the feature enabled?", while the method-level condition answers "has the user already provided this bean?". When both levels carry conditions, a bean is registered only if **all relevant conditions match**.

**Choose conditions on individual `@Bean` methods** when users are allowed to replace individual components such as sender, cache, policy, serializer, or client while still keeping the other default components. This is the back-off style best suited for extensible starters and auto-configurations.

**Combine both levels** when you need a true shared gate (classpath, property, web environment…) alongside independent fallbacks. Do not place a missing-bean condition at the class level merely for convenience across multiple beans with different roles.

## 5. Common Pitfalls and How to Verify

1. **Confusing back-off with override:** `@ConditionalOnMissingBean` keeps the default bean from **being registered** when a matching bean already exists. `spring.main.allow-bean-definition-overriding` controls whether multiple bean definitions with the same name override one another; enabling it is no substitute for proper condition design. `@Primary` only affects selection during bean injection.

2. **Placing the condition too broadly:** If you only want to customize the sender while keeping retry, do not lock the whole class with `@ConditionalOnMissingBean(NotificationSender.class)`. Use a separate condition per default, and test "override A only," "override B only," and "override both."

3. **Using the wrong criterion kind:** `@ConditionalOnMissingBean(NotificationSender.class)` checks **by bean type**, not by method name. `@ConditionalOnMissingBean(name = "notificationSender")` checks only the name. A bean named `customSender` by the user that still has type `NotificationSender` causes the **type-based** condition not to match; a **name-based** condition may still match. Pick type or name according to the actual extension contract.

4. **Inferring type from overly generic `@Bean` signatures:** On a method, `@ConditionalOnMissingBean` without arguments infers the checked type from the **declared return type**. A method declared to return `Object` hides crucial type info. Declare a meaningful return type or specify `value`/`type` explicitly. On a class, always specify the missing-bean criteria explicitly.

5. **Forgetting bean registration order:** `@ConditionalOnBean` and `@ConditionalOnMissingBean` evaluate against **bean definitions processed up to that point**, not every bean that will appear later. Place them in auto-configurations because Spring Boot processes auto-configurations after user configurations. If a condition depends on a bean provided by **another auto-configuration**, declare proper ordering, e.g., `@AutoConfiguration(after = OtherAutoConfiguration.class)`; this order controls definition registration, **not instance creation order**.

6. **Assuming a bean exists just because the Java class exists:** `@ConditionalOnClass` checks the classpath, whereas `@ConditionalOnBean` checks beans in the context. Having the `NotificationSender` class on the classpath does not mean a `NotificationSender` bean already exists. If a condition needs a library class that may be absent, place `@ConditionalOnClass` on an isolated `@Configuration` class to avoid loading missing classpath types from `@Bean` signatures.

7. **Ambiguity errors from multiple beans of the same type:** Type-based `@ConditionalOnMissingBean` only prevents the default from registering when it sees a matching bean. With a mis-scoped condition, two differently named beans of the same type can coexist, leading to `NoUniqueBeanDefinitionException` when injecting a single bean without a qualifier. Fix the condition and extension points rather than using `@Primary` to mask a design flaw.

When results differ from expectations, run the application with `--debug` to view the **Condition Evaluation Report**, or use `ApplicationContextRunner` in tests to check various combinations of user-supplied beans. In tests, assert both **the default beans that were skipped** and **the default beans that must remain**.

## 6. Quick Rules of Thumb

- **One custom bean should replace the whole group:** consider `@ConditionalOnMissingBean(TargetType.class)` at the **class level**, only when excluding the whole group is intentional.
- **Each bean is customized independently:** place `@ConditionalOnMissingBean(ThatBeanType.class)` on **each `@Bean` method**.
- **Need an on/off switch for the entire feature:** put the broad condition on the **class** (e.g., `@ConditionalOnProperty`), then put missing-bean conditions on **each independent default**.
- **Dependencies exist between auto-configurations:** control registration order and write tests with user beans present and absent.

The most important self-check question: **"If the user supplies bean A, do I really want beans B, C, and D to all disappear as well?"** If the answer is **no**, keep the back-off condition on each `@Bean` method.

## Official References

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): `@AutoConfiguration` mechanism, bean conditions, processing order, and `AutoConfiguration.imports` declaration.
- [Spring Boot API — `@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): matching rules and type inference from `@Bean` methods.
