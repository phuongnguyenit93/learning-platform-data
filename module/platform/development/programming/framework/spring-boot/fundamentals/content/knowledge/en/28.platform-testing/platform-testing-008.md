# Testing Auto-Configuration That Backs Off When a User Provides a Bean

Spring Boot stands out for its **auto-configuration**: the framework can automatically register common beans based on existing dependencies and configuration. However, automatic does not mean rigid. If an application explicitly provides a bean fulfilling the role an auto-configuration intends to create, the default configuration should usually **back off**—stepping aside without creating a competing bean.

This is a key contract when developing libraries, starters, or testing Spring Boot integration modules:

- **No application-provided bean:** auto-configuration creates a default bean so the application works out of the box.
- **Matching custom bean exists:** auto-configuration yields control to the application.
- **Another condition is not met:** the default bean may also be skipped, though the cause is not necessarily back-off due to a user bean.

A good test suite must prove **both main branches** and distinguish them from cases where the bean is omitted for other reasons. This lesson builds complete examples using **@ConditionalOnMissingBean**, **@AutoConfiguration**, **ApplicationContextRunner**, and **AutoConfigurations.of**, showing how to inspect the bean registry and avoid common pitfalls involving types, bean names, processing order, and parent contexts.

## 1. What does back-off mean in auto-configuration?

Suppose a library provides notification sending capabilities. By default, the library wants to register a `MessageSender` bean:

~~~text
Spring Boot application
        │
        ▼
Auto-configuration selected
        │
        ▼
Suitable MessageSender bean already exists?
        │
    ┌───┴────┐
    │        │
   No       Yes
    │        │
    ▼        ▼
Create     Back off:
default    do not create
bean       default bean
    │        │
    └───┬────┘
        ▼
Application uses MessageSender
~~~

Back-off does not mean Spring Boot creates a bean and then deletes it. Typically, **the bean registration condition is evaluated first**, and if the condition is not satisfied, the default bean definition is never registered along that branch.

Example:

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

The condition states: **register `defaultMessageSender` only if no bean matching `MessageSender` already exists in the appropriate search scope**.

If the application itself declares:

~~~java
@Bean
MessageSender myMessageSender() {
    return new CustomMessageSender();
}
~~~

then the default bean must yield in a properly organized auto-configuration.

### 1.1. Back-off is not @Primary

Suppose auto-configuration always creates `DefaultMessageSender` and the application creates `CustomMessageSender` marked with `@Primary`.

Both beans still exist:

~~~text
MessageSender beans:
- defaultMessageSender
- myMessageSender (@Primary)
~~~

`@Primary` only helps **select one bean** when injecting a single-value dependency; it **does not make the default bean disappear**. Code injecting `List<MessageSender>` still receives both, and beans referencing another name or qualifier can still see the default.

Thus, back-off is **conditional bean registration**, whereas `@Primary` is **candidate selection at injection time**.

### 1.2. Back-off is not bean overriding

Bean overriding happens when a bean definition with the same name is redefined according to container rules. Modern Spring Boot typically does not enable bean-definition overriding by name indiscriminately.

In a proper back-off design:

- There is no need to enable **spring.main.allow-bean-definition-overriding=true**.
- There is no need to register two beans with the same name and let the custom one overwrite the default.
- There is no need to catch duplicate-definition errors after startup.

Instead, auto-configuration **omits the default** when the missing-bean condition fails.

## 2. Role of @ConditionalOnMissingBean

Core annotation:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean
~~~

It can be placed on a `@Bean` method or a configuration class when registration needs to be conditional.

Example:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
@Bean
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

This condition is evaluated against bean definition metadata Spring knows at processing time. It **does not inspect an external database**, invoke `send()`, or compare business logic contents.

### 2.1. Checking by type, name, or other criteria

Common forms:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

Checks for the absence of a bean of type `MessageSender` per the condition's matching rules.

~~~java
@ConditionalOnMissingBean(name = "messageSender")
~~~

Checks for the absence of a bean with the given name.

~~~java
@ConditionalOnMissingBean(annotation = MyMarker.class)
~~~

Checks for the absence of a bean carrying the specified annotation per condition rules.

When combining criteria, understand they produce different contracts. **Bean names are not bean types**, and an application may supply the same type under any bean name.

For instance, a user bean named **myMessageSender** still has type `MessageSender`. Checking by `name="messageSender"` would not recognize it as a replacement, whereas checking by type `MessageSender.class` backs off as intended.

### 2.2. When no type is specified on the @Bean method

On a `@Bean` method:

~~~java
@Bean
@ConditionalOnMissingBean
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Spring Boot can infer the type to check from the **return type of the `@Bean` method**.

Even so, writing it explicitly:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

often helps readers immediately understand the back-off contract, especially in a starter exposing an interface users are encouraged to customize.

### 2.3. Why does the @Bean return type matter?

Suppose the application declares:

~~~java
@Bean
Object customBean() {
    return new CustomMessageSender();
}
~~~

Even though the runtime instance is `CustomMessageSender`, the bean definition may only expose return type **Object** while conditions are evaluated. The framework might not yet know it is a `MessageSender` when deciding whether to register the default bean.

That is why declaring a specific, accurate return type is important:

~~~java
@Bean
MessageSender customMessageSender() {
    return new CustomMessageSender();
}
~~~

When developing auto-configuration, **bean definition metadata at condition evaluation time** matters more than the runtime object you expect to be instantiated later.

## 3. Why is this annotation especially suited to auto-configuration?

Spring Boot documentation and practice emphasize that conditions like **@ConditionalOnBean** and **@ConditionalOnMissingBean** depend on bean definitions **already processed at the time of evaluation**.

Placing them in an ordinary `@Configuration` class without appropriate ordering can make results depend on whichever class happens to be processed first.

Example of a default configuration living inside the app:

~~~java
@Configuration(proxyBeanMethods = false)
class DefaultSenderConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

If this configuration is processed **before** a user configuration defining `MessageSender`, the condition may fail to see the user bean definition as expected.

### 3.1. Boot orders auto-configuration after user configuration

Auto-configurations are processed by Spring Boot through its import mechanism with ordering rules that generally **defer to user bean definitions**.

This is the design intent behind `@AutoConfiguration` and missing-bean conditions:

~~~text
User configuration / component scanning
                │
                ▼
Spring knows the bean definitions supplied by the application
                │
                ▼
Auto-configuration is processed
                │
                ▼
@ConditionalOnMissingBean has enough information to back off
~~~

This diagram is a conceptual model; Spring startup involves multiple registration and condition evaluation phases. The key takeaway is not to scatter missing-bean conditions arbitrarily on early-imported configuration classes expecting them to always back off.

### 3.2. Auto-configuration ordering also matters

Two auto-configurations may both participate in creating related beans. Spring Boot supports ordering metadata such as:

~~~java
@AutoConfiguration(after = SomeOtherAutoConfiguration.class)
~~~

or before/after names where appropriate.

Ordering ensures conditions see bean definitions intended to be registered by earlier auto-configurations. It **does not replace** dependency injection or govern runtime initialization order of all bean instances.

When testing back-off, emulate how Spring Boot imports auto-configurations instead of creating `new` instances or calling `@Bean` methods manually.

## 4. Running example: a notification starter

Let's build an illustrative module with a public interface `MessageSender` and a library-provided default implementation.

Logical structure:

~~~text
com.example.messaging/
├── MessageSender.java
├── DefaultMessageSender.java
└── autoconfigure/
    └── MessageSenderAutoConfiguration.java

com.example.demo/
├── DemoApplication.java
└── CustomMessageSenderConfiguration.java
~~~

Because this is learning material, these packages can live in one project for experimentation. In a real starter, the API, auto-configuration, and consumer application are typically separate modules or artifacts.

### 4.1. Interface used by the application

~~~java
package com.example.messaging;

public interface MessageSender {
    String send(String recipient, String message);
}
~~~

The example returns a `String` so tests run cleanly without networking or external services.

### 4.2. Default implementation

~~~java
package com.example.messaging;

public final class DefaultMessageSender
        implements MessageSender {

    @Override
    public String send(String recipient, String message) {
        return "default:" + recipient + ":" + message;
    }
}
~~~

This class does not carry `@Component`. It is created by auto-configuration so default registration is controlled in one clear place.

### 4.3. Auto-configuration with back-off condition

~~~java
package com.example.messaging.autoconfigure;

import com.example.messaging.DefaultMessageSender;
import com.example.messaging.MessageSender;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

Explanation:

- **@AutoConfiguration** marks this as an auto-configuration class.
- **@Bean** declares the factory method creating `MessageSender`.
- **@ConditionalOnMissingBean(MessageSender.class)** requires no matching `MessageSender` bean already exists.
- **DefaultMessageSender** is simply the fallback implementation selected when needed.

In a real Spring Boot starter, the auto-configuration must be registered for Boot discovery, such as via the Boot 3 auto-configuration imports file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example contents:

~~~text
com.example.messaging.autoconfigure.MessageSenderAutoConfiguration
~~~

When the library is on a Spring Boot application's classpath and properly registered, Boot can import this auto-configuration.

In the unit-style tests below, we use **AutoConfigurations.of** to pass the auto-configuration class directly into the test context, **without** packaging a starter or creating an imports file just to test conditions.

### 4.4. Implementation provided by the application

~~~java
package com.example.demo;

import com.example.messaging.MessageSender;

public final class CustomMessageSender
        implements MessageSender {

    @Override
    public String send(String recipient, String message) {
        return "custom:" + recipient + ":" + message;
    }
}
~~~

And user configuration:

~~~java
package com.example.demo;

import com.example.messaging.MessageSender;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomMessageSenderConfiguration {

    @Bean
    MessageSender customMessageSender() {
        return new CustomMessageSender();
    }
}
~~~

Here the bean name **customMessageSender** differs from **defaultMessageSender**. We intentionally chose a different name to prove the condition **backs off by type**, rather than colliding on the same bean name.

### 4.5. Application consuming the interface

~~~java
package com.example.demo;

import com.example.messaging.MessageSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final MessageSender sender;

    public NotificationService(MessageSender sender) {
        this.sender = sender;
    }

    public String notifyRecipient(String recipient) {
        return sender.send(recipient, "Hello");
    }
}
~~~

`NotificationService` does not need to know whether it receives the default or custom implementation. The auto-configuration contract ensures an eligible `MessageSender` exists **if the application has not supplied its own**.

## 5. What is ApplicationContextRunner?

**ApplicationContextRunner** is a test utility provided by Spring Boot to boot a small `ApplicationContext` customizable with configuration classes, auto-configuration imports, property values, and beans.

Import:

~~~java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
~~~

It fits auto-configuration testing well because:

- No web server needs to run.
- No full application needs to boot via `@SpringBootTest`.
- Each **run** creates a clearly scoped context and closes it once the callback completes.
- Tests easily construct scenarios **with or without a user-defined bean**.
- Both successful startup and startup failures can be observed.
- It pairs with **AutoConfigurations.of(...)** to import the exact auto-configurations under test.

Diagram of a test:

~~~text
ApplicationContextRunner
     │
     ├── withConfiguration(AutoConfigurations.of(...))
     ├── withUserConfiguration(...) [if testing custom bean]
     ├── withPropertyValues(...)    [if needed]
     └── run(context -> assertions)
                            │
                            ▼
                 Create test context
                            │
                            ▼
                 Evaluate conditional beans
                            │
                            ▼
                 Assert beans created / omitted
                            │
                            ▼
                    Close test context
~~~

### 5.1. Dependencies for testing

In a Spring Boot application using Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The test starter typically supplies JUnit Jupiter, AssertJ, and `spring-boot-test`. Examples here assume the project manages dependency versions compatible with the Spring Boot version in use.

If an auto-configuration module is standalone without `spring-boot-starter-test`, add compatible test dependencies including **spring-boot-test**, JUnit Jupiter, and AssertJ.

### 5.2. How does AutoConfigurations.of differ from withUserConfiguration?

Example:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                MessageSenderAutoConfiguration.class))
        .withUserConfiguration(
                CustomMessageSenderConfiguration.class);
~~~

The two methods represent two distinct roles:

- **withConfiguration(AutoConfigurations.of(...))**: adds auto-configurations into the context using Spring Boot's test support mechanism.
- **withUserConfiguration(...)**: adds user-supplied application configurations into the context.

This distinction lets tests emulate the intended design: user beans take precedence over starter defaults.

In real environments, auto-configurations are discovered via the library's imports list. In the context runner, they are declared directly to keep tests focused and fast.

## 6. Test branch A: default is created when no custom bean exists

This is the first foundational test.

~~~java
package com.example.messaging.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.messaging.DefaultMessageSender;
import com.example.messaging.MessageSender;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MessageSenderAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MessageSenderAutoConfiguration.class));

    @Test
    void createsDefaultSenderWhenNoUserBeanExists() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(MessageSender.class);
            assertThat(context).hasBean("defaultMessageSender");

            MessageSender sender =
                    context.getBean(MessageSender.class);

            assertThat(sender)
                    .isInstanceOf(DefaultMessageSender.class);

            assertThat(sender.send("customer-1", "hello"))
                    .isEqualTo("default:customer-1:hello");
        });
    }
}
~~~

What does this test prove?

1. The context started cleanly.
2. There is **exactly one** `MessageSender` bean visible to the test.
3. The default bean named **defaultMessageSender** exists.
4. The bean resolved by type is `DefaultMessageSender`.
5. Basic implementation behavior works as expected.

Points (1)–(4) are the heart of auto-configuration testing. Point (5) is an extra sanity check; complex messaging behavior belongs in the implementation's own unit tests.

### 6.1. Why is asserting hasSingleBean important?

Writing only:

~~~java
assertThat(context).hasBean("defaultMessageSender");
~~~

proves that bean name exists, yet leaves open whether another `MessageSender` was also registered unintentionally.

For a single-candidate fallback contract:

~~~java
assertThat(context).hasSingleBean(MessageSender.class);
~~~

catches cases where too many beans of the same type exist in the test context.

### 6.2. Do not check only that the ApplicationContext did not fail

A non-failing context can still **have zero `MessageSender` beans** if another condition excluded the auto-configuration.

~~~java
assertThat(context).hasNotFailed();
~~~

is necessary, not sufficient. Checking presence and type of the default bean verifies the actual goal.

## 7. Test branch B: default backs off when a custom bean exists

This is the **most important** test in this lesson.

Starting from the previous runner, add the user configuration:

~~~java
@Test
void backsOffWhenUserProvidesMessageSender() {
    contextRunner
            .withUserConfiguration(
                    CustomMessageSenderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasSingleBean(MessageSender.class);

                assertThat(context)
                        .hasBean("customMessageSender");
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");

                MessageSender sender =
                        context.getBean(MessageSender.class);

                assertThat(sender)
                        .isInstanceOf(CustomMessageSender.class);

                assertThat(sender.send("customer-1", "hello"))
                        .isEqualTo("custom:customer-1:hello");
            });
}
~~~

Remember to import the two demo classes into the test:

~~~java
import com.example.demo.CustomMessageSender;
import com.example.demo.CustomMessageSenderConfiguration;
~~~

Expected outcome:

~~~text
Context:
  customMessageSender   -> CustomMessageSender

Absent:
  defaultMessageSender  -> DefaultMessageSender

MessageSender beans count = 1
~~~

### 7.1. Three core assertions

On the back-off branch, prove at minimum:

~~~java
assertThat(context).hasSingleBean(MessageSender.class);
assertThat(context).hasBean("customMessageSender");
assertThat(context).doesNotHaveBean("defaultMessageSender");
~~~

Why all three?

- Custom bean exists → user configuration actually entered the test.
- Default bean does not exist → auto-configuration backed off.
- Exactly one `MessageSender` → no duplicate candidates causing ambiguity.

If you only check that `CustomMessageSender` can be injected, the test could still pass in a context containing **both custom and default** if `@Primary` or `@Qualifier` masked the duplication.

### 7.2. Proving back-off by type rather than by name

In the example, the custom bean is named **customMessageSender**, completely different from **defaultMessageSender**. Therefore:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

must back off based on the `MessageSender` type. The result cannot be explained away as a custom bean overwriting a bean of the same name.

This is a vital trait in starter design: applications must not be forced to use the library's internal default bean name just to supply an implementation.

### 7.3. Do not instantiate the custom bean with new outside Spring

For example:

~~~java
MessageSender sender = new CustomMessageSender();
~~~

merely creates a Java object in a local variable. It **does not become a bean in the ApplicationContext**, and therefore cannot cause `@ConditionalOnMissingBean` to back off.

A valid test must register the bean through Spring, such as:

- `@Bean` inside a user configuration.
- `withBean(...)` on `ApplicationContextRunner`.
- Explicitly configured component scanning.
- An equivalent bean registration mechanism.

## 8. A concise testing alternative: withBean

When you do not need a separate `@Configuration` class, `ApplicationContextRunner` can register a bean directly:

~~~java
@Test
void backsOffForProgrammaticallyRegisteredUserBean() {
    contextRunner
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(
                        MessageSender.class);

                assertThat(context.getBean(
                        MessageSender.class))
                        .isInstanceOf(
                                CustomMessageSender.class);

                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
            });
}
~~~

**withBean** registers a single user-defined bean with a test-controlled type and instance supplier.

Advantages:

- Minimal boilerplate.
- Focused on bean presence vs. absence.
- No need to define a separate test configuration class for every variant.

However, **withUserConfiguration** remains necessary when verifying how real applications declare `@Bean` methods, qualifiers, bean names, scopes, or configuration-class conditions.

### 8.1. Should you pick withBean or withUserConfiguration?

| Testing need | Typically suitable approach |
|---|---|
| Just need one user bean of the same type | `withBean(MessageSender.class, ...)` |
| Want to prove a user `@Bean` method triggers back-off | `withUserConfiguration(...)` |
| Want to test multiple interacting `@Bean` methods | `withUserConfiguration(...)` |
| Want to verify real declared bean names or qualifiers | `withUserConfiguration(...)` |
| Want to plug in a simple fake instance | `withBean(...)` |
| Want to simulate a realistic multi-config app | `withUserConfiguration(...)` with context runner |

Both approaches register beans in the test context; the key is verifying **the default is absent** when the custom bean is present.

## 9. A minimal yet meaningful test suite

You can place the two tests side by side so maintainers immediately see the contract:

~~~java
package com.example.messaging.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.CustomMessageSender;
import com.example.messaging.DefaultMessageSender;
import com.example.messaging.MessageSender;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MessageSenderBackOffTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            MessageSenderAutoConfiguration.class));

    @Test
    void registersDefaultIfNothingIsProvided() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(MessageSender.class);
            assertThat(context.getBean(MessageSender.class))
                    .isInstanceOf(DefaultMessageSender.class);
        });
    }

    @Test
    void backsOffWhenUserProvidesBean() {
        runner.withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            MessageSender.class);
                    assertThat(context.getBean(
                            MessageSender.class))
                            .isInstanceOf(
                                    CustomMessageSender.class);
                    assertThat(context)
                            .doesNotHaveBean(
                                    "defaultMessageSender");
                });
    }
}
~~~

If you had to pick one mandatory pair of tests for every auto-configuration using `@ConditionalOnMissingBean`, this is the highest-value pair:

**Default exists when no user bean is provided; default disappears when a user bean is provided.**

It verifies runtime behavior rather than merely checking that an annotation exists in source code.

## 10. What happens if two user beans share the same type?

Suppose the application registers:

~~~java
@Configuration(proxyBeanMethods = false)
public class TwoSendersConfiguration {

    @Bean
    MessageSender primaryBusinessSender() {
        return new CustomMessageSender();
    }

    @Bean
    MessageSender secondaryBusinessSender() {
        return new AnotherMessageSender();
    }
}
~~~

`AnotherMessageSender` is another application-supplied implementation of `MessageSender`.

The condition:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

still backs off, because **a `MessageSender` bean already exists**. Yet the application now has **two user beans**; injecting a single `MessageSender` without a qualifier can fail due to ambiguity.

A test focused on the condition can verify:

~~~java
@Test
void backsOffEvenWhenMultipleUserSendersExist() {
    contextRunner
            .withUserConfiguration(
                    TwoSendersConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
                assertThat(context.getBeansOfType(
                        MessageSender.class)).hasSize(2);
            });
}
~~~

This test assumes the context does not include a consumer requiring injection of a single `MessageSender`. If `NotificationService` from the initial example is scanned or imported and injects an unqualified `MessageSender`, the context will fail due to ambiguity.

### 10.1. Back-off does not guarantee only one user bean exists

These two statements differ:

- "The library creates no default when the app has a `MessageSender`" — the back-off contract.
- "The application always has exactly one `MessageSender`" — a separate overall contract that may require extra constraints.

Do not treat `@ConditionalOnMissingBean` as a uniqueness validator for all user-registered beans.

### 10.2. Distinguish from @ConditionalOnSingleCandidate

Spring Boot also provides:

~~~java
@ConditionalOnSingleCandidate(MessageSender.class)
~~~

This condition serves scenarios where a configuration wants to register a dependent bean only when a single candidate can be chosen per condition rules—such as a single bean or an eligible primary candidate.

That addresses a different need from **@ConditionalOnMissingBean**:

- `MissingBean`: registers a default **when no suitable candidate exists yet**.
- `SingleCandidate`: registers a dependent component **when a single candidate can be resolved**.

A large auto-configuration may use both conditions on different `@Bean` methods, yet they are not direct substitutes for each other.

## 11. Bean names and bean types lead to different branches

Suppose the user bean is:

~~~java
@Bean("customSender")
MessageSender sender() {
    return new CustomMessageSender();
}
~~~

A condition by type:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

backs off because a `MessageSender` already exists.

However, a condition by name:

~~~java
@ConditionalOnMissingBean(name = "defaultMessageSender")
~~~

does not back off, because the context has no bean named **defaultMessageSender**. The auto-configuration will create a second `MessageSender`, resulting in two beans of the same type.

### 11.1. Test proving a type-based contract

User configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class NamedCustomSenderConfiguration {

    @Bean("senderChosenByApplication")
    MessageSender chosenSender() {
        return new CustomMessageSender();
    }
}
~~~

Test:

~~~java
@Test
void doesNotRequireUserBeanToHaveDefaultName() {
    contextRunner
            .withUserConfiguration(
                    NamedCustomSenderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasBean("senderChosenByApplication");
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
                assertThat(context)
                        .hasSingleBean(MessageSender.class);
            });
}
~~~

This is a valuable test when authoring a public starter, since users should not have to know internal default bean names just to supply their own implementation.

### 11.2. When is name-based back-off useful?

Checking by name makes sense when the contract truly revolves around **a specific identifying bean name**—for instance, an integration accessed by bean name rather than a broad shared type.

However, for most interface-based SPIs, type-based back-off expresses "the user supplied an implementation" much more accurately.

### 11.3. @Bean method names can affect bean names

When no name is specified:

~~~java
@Bean
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

the bean name defaults to the method name **defaultMessageSender**.

Renaming the method requires updating tests that hardcode the bean name, even though type-based behavior is unchanged. Therefore:

- Use **hasSingleBean(type)** and **isInstanceOf** for type contracts.
- Use **doesNotHaveBean(name)** when proving the default definition itself was omitted.

Both assertion forms complement each other rather than always replacing one another.

## 12. Why must a user @Bean return type be specific?

This is a surprising pitfall when moving from unit tests to auto-configuration.

User defines:

~~~java
@Bean
Object customSender() {
    return new CustomMessageSender();
}
~~~

Auto-configuration defines:

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

At the moment the condition is evaluated, Spring may only know the custom bean has declared type **Object** from its signature. If the instance has not yet been created, metadata may not prove it is a `MessageSender`.

Possible consequences:

1. `@ConditionalOnMissingBean(MessageSender.class)` evaluates as matching.
2. `defaultMessageSender` gets registered.
3. Later `customSender` instantiates `CustomMessageSender`.
4. `ApplicationContext` ends up with two `MessageSender`-capable objects, or exhibits unexpected lookup/candidate-detection behavior.

### 12.1. Better way to write it

~~~java
@Bean
MessageSender customSender() {
    return new CustomMessageSender();
}
~~~

Or:

~~~java
@Bean
CustomMessageSender customSender() {
    return new CustomMessageSender();
}
~~~

If `CustomMessageSender` implements `MessageSender`, the concrete return type also lets the container infer assignability.

### 12.2. Testing takeaway

A test using:

~~~java
.withBean(MessageSender.class, CustomMessageSender::new)
~~~

registers the type explicitly and therefore passes. Yet if the real application uses a factory method declaring return type `Object`, behavior may not be equivalent.

Thus, if a starter must support **how real applications declare user beans**, include at least one test using **withUserConfiguration** and a `@Bean` signature representative of your documented integration style.

### 12.3. FactoryBean, generic containers, and complex type inference

In Spring, some beans are created via `FactoryBean`, proxies, or generic wrappers. Type information may be incomplete at condition evaluation time.

Spring Boot provides advanced attributes on `@ConditionalOnMissingBean`, such as **parameterizedContainer** or **ignored** types.

Those are tools for specialized contracts. Unless specifically required, start with simple interface-based conditions and write tests proving replacement behavior.

## 13. Bean definition existence differs from bean instantiation

`@ConditionalOnMissingBean` generally inspects **bean definitions and type metadata** known to Spring. It does not require the user bean to have finished all initialization logic.

Example:

~~~java
@Bean
@Lazy
MessageSender customMessageSender() {
    return new CustomMessageSender();
}
~~~

Once the `@Bean` definition is registered and its type is exposed, auto-configuration backs off even though the instance is marked lazy and has not yet been instantiated.

### 13.1. Do not test by counting constructor calls and concluding about definitions

Suppose a test counts how many times the `DefaultMessageSender` constructor ran. Seeing `0` does not guarantee the default bean definition is absent: it could simply be a lazy bean not yet created.

To prove back-off:

~~~java
assertThat(context).doesNotHaveBean("defaultMessageSender");
~~~

or inspect the bean definitions/bean names directly. Observing instantiation counts is only a secondary signal.

### 13.2. Scope does not automatically cause a bean to be ignored

A prototype bean or scoped proxy can still participate in condition evaluation according to Spring's metadata and matching rules. Do not assume "only singletons trigger auto-configuration back-off."

For complex types or scopes, build a test context with the exact style of user bean your library intends to support.

## 14. Distinguishing back-off from other conditions

Real auto-configurations rarely rely on `@ConditionalOnMissingBean` alone.

Example:

~~~java
@AutoConfiguration
public class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.message",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

Remember to import:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
~~~

Here two conditions participate together:

- The feature is enabled or the property is absent with `matchIfMissing=true`.
- No `MessageSender` bean exists yet.

### 14.1. Scenario matrix

| Feature enabled? | User MessageSender? | Default MessageSender? | Reason |
|---|---|---|---|
| Undeclared, `matchIfMissing=true` | No | Yes | Default is allowed to register |
| `true` | No | Yes | All conditions match |
| `true` | Yes | No | Back-off due to user bean |
| `false` | No | No | Feature disabled, **not** back-off |
| `false` | Yes | No | Feature disabled; user bean still exists if registered independently |

If a test checks only that the default is absent, it fails to distinguish **because a user bean exists** from **because the feature was disabled**. Build scenarios and assertions for each branch.

### 14.2. Testing feature disabled

~~~java
@Test
void doesNotCreateDefaultWhenFeatureIsDisabled() {
    contextRunner
            .withPropertyValues(
                    "acme.message.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(MessageSender.class);
            });
}
~~~

This tests a **feature condition**, not back-off. It ensures that when a back-off test fails, the team does not confuse the cause with the enable/disable property.

### 14.3. Testing that user beans remain when auto-config is disabled

~~~java
@Test
void userBeanIsIndependentOfDefaultFeatureFlag() {
    contextRunner
            .withPropertyValues(
                    "acme.message.enabled=false")
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .hasSingleBean(MessageSender.class);
                assertThat(context.getBean(
                        MessageSender.class))
                        .isInstanceOf(
                                CustomMessageSender.class);
                assertThat(context)
                        .doesNotHaveBean("defaultMessageSender");
            });
}
~~~

If business rules require disabling the feature to disable **user implementations as well**, the system-wide condition design must differ. A `@ConditionalOnProperty` on the library's default bean does not automatically remove independently registered user beans.

## 15. Back-off and parent ApplicationContexts

Simple applications usually have one primary `ApplicationContext`. Yet Spring can organize **parent/child contexts**, such as in certain web, integration, or advanced test architectures.

Then "does a bean already exist?" requires a scope:

- Check only the current `ApplicationContext`?
- Or also check ancestor contexts?

**@ConditionalOnMissingBean** supports a **search** attribute with the `SearchStrategy` enum.

~~~java
import org.springframework.boot.autoconfigure.condition.SearchStrategy;

@ConditionalOnMissingBean(
        value = MessageSender.class,
        search = SearchStrategy.CURRENT)
~~~

With `search=CURRENT`, the condition checks only the context currently being processed and does not treat parent contexts as supplying matching candidates.

With `search=ALL` (the typical default), the condition considers beans from ancestor contexts as well.

### 15.1. Why does search scope matter?

Suppose:

~~~text
Parent ApplicationContext
  └── customMessageSender : MessageSender

Child ApplicationContext
  └── MessageSenderAutoConfiguration
~~~

If the child auto-configuration is allowed to inspect the parent, it backs off so the child resolves the parent's bean during type lookup.

If the condition inspects only the current context, the child registers **defaultMessageSender** as well. Then the overall hierarchy contains both the parent's custom bean and the child's default.

Which behavior to choose depends on your library's API contract. Neither `search=CURRENT` nor `search=ALL` is universally better.

### 15.2. Testing back-off when the parent holds a bean

`ApplicationContextRunner` supports configuring a parent context.

~~~java
@Test
void backsOffWhenParentContextHasSender() {
    new ApplicationContextRunner()
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(parent -> {

                new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(
                                        MessageSenderAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasNotFailed();
                            assertThat(child)
                                    .doesNotHaveBean(
                                            "defaultMessageSender");

                            MessageSender resolved =
                                    child.getBean(MessageSender.class);

                            assertThat(resolved)
                                    .isInstanceOf(
                                            CustomMessageSender.class);
                        });
            });
}
~~~

This tests the auto-configuration under the **default search strategy** considering parent contexts per contract.

Note: a child context can see a parent bean on type lookup, which does not mean the bean is registered **locally** inside the child. When testing context boundaries, distinguish "bean resolved through hierarchy" from "child owns the bean definition."

### 15.3. Testing search=CURRENT

Another auto-configuration might write:

~~~java
@AutoConfiguration
public class ChildOnlyMessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(
            value = MessageSender.class,
            search = SearchStrategy.CURRENT)
    MessageSender childDefaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

In a parent/child scenario, the child will not treat a `MessageSender` in the parent as matching under `search=CURRENT`.

A test can verify:

~~~java
@Test
void currentSearchCreatesChildBeanDespiteParentBean() {
    new ApplicationContextRunner()
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(parent -> {

                new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(
                                        ChildOnlyMessageAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasNotFailed();
                            assertThat(child)
                                    .hasBean(
                                            "childDefaultMessageSender");
                        });
            });
}
~~~

This test focuses on **the local child bean**. If you want to observe all beans in both contexts separately, inspect parent and child individually or read bean definitions directly from each bean factory rather than conflating them with hierarchical lookups.

## 16. Back-off and auto-configuration ordering

Suppose a library has two auto-configurations:

~~~text
SharedSenderAutoConfiguration
MessageSenderAutoConfiguration
~~~

Both can involve `MessageSender`. If `MessageSenderAutoConfiguration` evaluates `@ConditionalOnMissingBean` before `SharedSenderAutoConfiguration` registers its bean, the result may diverge from the intended design.

### 16.1. Using after to express bean definition dependencies

~~~java
@AutoConfiguration(
        after = SharedSenderAutoConfiguration.class)
public class MessageSenderAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }
}
~~~

This requests that the auto-configuration be evaluated after `SharedSenderAutoConfiguration` per Boot's ordering rules whenever both participate.

### 16.2. Ordering does not govern all bean creation

Distinguish between:

- **Bean definition registration order**: affects conditions such as `@ConditionalOnMissingBean`.
- **Bean instantiation/dependency order**: governed by dependency injection, `@DependsOn`, lazy initialization, and container lifecycle.

Adding `@AutoConfiguration(after=...)` primarily controls **auto-configuration processing order**, not replacing a service's declared constructor dependencies.

### 16.3. Tests should import all interacting auto-configurations

If `MessageSenderAutoConfiguration`'s condition depends on a bean created by another auto-configuration, running only:

~~~java
AutoConfigurations.of(MessageSenderAutoConfiguration.class)
~~~

can miss key interactions.

Instead, build the runner with:

~~~java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                SharedSenderAutoConfiguration.class,
                MessageSenderAutoConfiguration.class));
~~~

This tests ordering and back-off between related auto-configurations in the same scenario.

You do not need to import all of `spring-boot-autoconfigure` when the question concerns only two classes: the smaller and more targeted the context, the clearer the explanation.

## 17. @ConditionalOnClass and back-off

In real starters, an auto-configuration may also depend on a library being present on the classpath.

Conceptual example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.messaging.VendorClient")
public class VendorMessagingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender vendorMessageSender() {
        // Create adapter from vendor library when classpath is valid.
        return new DefaultMessageSender();
    }
}
~~~

Here the class condition requires the matching vendor dependency. If the class is missing from the classpath, the entire auto-configuration is skipped.

### 17.1. Do not conclude back-off occurred merely because the default bean is absent

Suppose the test:

~~~java
assertThat(context)
        .doesNotHaveBean("vendorMessageSender");
~~~

passes, yet `VendorClient` is absent from the context. That proves `vendorMessageSender` does not exist; **it does not prove it backed off because of a user bean**.

To test back-off for a vendor integration:

1. Ensure the classpath condition is satisfied.
2. No user bean → vendor default is created.
3. User bean exists → vendor default is not created.
4. Classpath condition not satisfied → bean is omitted due to classpath, tested separately.

### 17.2. FilteredClassLoader for classpath conditions

Spring Boot Test provides **FilteredClassLoader** to simulate missing classes in a test context.

Structural example:

~~~java
import org.springframework.boot.test.context.FilteredClassLoader;

contextRunner
        .withClassLoader(new FilteredClassLoader(
                "com.vendor.messaging"))
        .run(context -> {
            // Verify auto-configuration requiring vendor
            // does not create bean when class is unavailable.
        });
~~~

This is a supplementary check for `@ConditionalOnClass`. It is unnecessary for pure-Java auto-configurations without optional dependencies.

When implementing classpath-sensitive auto-configurations, watch out for referencing optional classes directly in method signatures. Classpath conditions often belong on an outer configuration boundary to prevent class-loading failures before the condition can exclude the branch.

## 18. @ConditionalOnBean and dependent relationships

An auto-configuration can create Bean A by default and then create Bean B **only when Bean A or a user replacement exists**.

Example:

~~~java
public record MessageGateway(MessageSender sender) {
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class MessagingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }

    @Bean
    @ConditionalOnBean(MessageSender.class)
    @ConditionalOnMissingBean(MessageGateway.class)
    MessageGateway messageGateway(MessageSender sender) {
        return new MessageGateway(sender);
    }
}
~~~

In a design like this:

- If no `MessageSender` exists, the default branch creates `MessageSender`.
- If the user provided `MessageSender`, the default backs off.
- `MessageGateway` requires a resolvable `MessageSender`.
- If the user provides `MessageGateway`, the default gateway also backs off.

Remember: **@ConditionalOnBean** also relies on bean definitions processed up to evaluation time. When placing multiple interdependent conditional `@Bean` methods in one auto-configuration, design ordering and conditions carefully instead of relying on vague assumptions about method declaration order.

### 18.1. Test the entire replacement chain

A small integration check should confirm `MessageGateway` uses the **custom** `MessageSender`:

~~~java
@Test
void gatewayUsesUserProvidedSender() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    MessagingAutoConfiguration.class))
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        "defaultMessageSender");

                MessageGateway gateway =
                        context.getBean(MessageGateway.class);

                assertThat(gateway.sender())
                        .isInstanceOf(
                                CustomMessageSender.class);
            });
}
~~~

This goes deeper than basic back-off testing: not only did the default vanish, the dependent bean wired correctly to the user's replacement.

### 18.2. When multiple candidates exist, dependent beans can fail

If the application supplies two `MessageSender` beans, the factory method:

~~~java
MessageGateway messageGateway(MessageSender sender)
~~~

cannot choose a single candidate. If a starter must handle this scenario, design the selection contract explicitly using appropriate qualifiers/primaries or conditions like `@ConditionalOnSingleCandidate` in the right place.

**`MessageSender` backing off does not automatically guarantee `MessageGateway` succeeds.**

## 19. Condition Evaluation Report: knowing why a bean did not appear

When a default bean is absent, several hypotheses exist:

- `@ConditionalOnMissingBean` did not match because a user bean existed.
- `@ConditionalOnProperty` did not match because the feature was disabled.
- `@ConditionalOnClass` did not match because a dependency was missing.
- The configuration class was not imported into the test/application.
- Bean name/type differed from what the condition checked.

Spring Boot's **Condition Evaluation Report** reveals which conditions were evaluated and their outcomes.

### 19.1. Reading the report in ApplicationContextRunner

Usage example:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;

@Test
void printsConditionReportForDiagnosis() {
    contextRunner
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {

                ConditionEvaluationReport report =
                        ConditionEvaluationReport.get(
                                context.getSourceApplicationContext()
                                        .getBeanFactory());

                report.getConditionAndOutcomesBySource()
                        .forEach((source, outcomes) -> {
                            if (source.contains(
                                    "MessageSenderAutoConfiguration")) {

                                System.out.println(
                                        source + ": "
                                        + outcomes.isFullMatch());

                                outcomes.forEach(
                                        conditionAndOutcome ->
                                                System.out.println(
                                                        conditionAndOutcome
                                                                .getOutcome()
                                                                .getMessage()));
                            }
                        });
            });
}
~~~

This snippet illustrates inspecting the report during diagnosis, not the lesson's primary assertion style. Source names and condition message wording can vary across Spring Boot versions.

### 19.2. The report explains conditions; it does not replace bean assertions

A report showing a missing-bean condition did not match is very helpful diagnostic info, yet behavior tests should still assert:

~~~java
assertThat(context)
        .doesNotHaveBean("defaultMessageSender");
assertThat(context)
        .hasSingleBean(MessageSender.class);
~~~

Tests comparing exact condition message strings can break whenever Spring Boot rewords its logs even if behavior is unchanged.

Treat the condition report as an **explanatory diagnostic tool**, and the bean registry as the **final proof** of the back-off contract.

### 19.3. Expected entry missing from the report

If `MessageSenderAutoConfiguration` does not appear in the report, the test or app probably never imported or activated that configuration.

Check:

1. Does the context runner include **withConfiguration(AutoConfigurations.of(...))**?
2. Was the auto-configuration class excluded by a class-level condition before method conditions ran?
3. Was a different configuration imported instead?
4. When running the real app, is the library's **AutoConfiguration.imports** file in the right location with the right contents?

Never tweak condition annotations when the real issue is that the auto-configuration was never loaded.

## 20. Does @SpringBootTest replace ApplicationContextRunner?

**@SpringBootTest** can test an application closer to real runtime configuration. Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class UserOverrideIntegrationTests {

    @Autowired
    MessageSender sender;

    @Test
    void usesCustomSender() {
        assertThat(sender)
                .isInstanceOf(CustomMessageSender.class);
    }
}
~~~

This test is only valid if the application context is actually configured to include `CustomMessageSender` and the starter auto-configuration under test.

### 20.1. Limitation of injecting only one bean

If the custom bean has `@Primary`, `@Autowired MessageSender` still injects the custom bean **even when the default also exists**.

Therefore, asserting only:

~~~java
assertThat(sender)
        .isInstanceOf(CustomMessageSender.class);
~~~

does not prove the default backed off.

In an integration test, inject **ApplicationContext** or **ListableBeanFactory** and inspect bean count and names:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void defaultBeanWasNotRegistered() {
    assertThat(applicationContext
            .getBeansOfType(MessageSender.class))
            .hasSize(1);

    assertThat(applicationContext
            .containsBean("defaultMessageSender"))
            .isFalse();
}
~~~

In applications with parent contexts, remember that bean-lookup and bean-factory APIs can have different scopes. Choose the inspection API fitting your application's contract.

### 20.2. Why still prefer context runner for back-off?

| Criterion | ApplicationContextRunner | @SpringBootTest |
|---|---|---|
| Scope | Small context, explicit auto-configurations | Full application configs and dependencies |
| Typical speed | Fast, few side effects | Can be slower and open many resources |
| Setting up missing user bean | Easy | May require dedicated profiles/test configs |
| Setting up custom user bean | `withBean` / `withUserConfiguration` | `@TestConfiguration` / import / profile |
| Checking conditions and registry | Very well suited | Possible, yet many sources interfere |
| Verifying starter imports when packaged | Does not prove automatically | Better suited to integration smoke tests |
| Testing web/data integrations | Only when explicitly configured | Usually better suited |

**ApplicationContextRunner** is the primary choice for testing conditional auto-configuration registration. **@SpringBootTest** adds integration-level confidence when verifying import wiring, profiles, dependencies, or a full consumer application.

### 20.3. Context runner does not auto-scan every @Component

If the real application has:

~~~java
@Component
public class CustomMessageSender
        implements MessageSender {
    // ...
}
~~~

a bare `ApplicationContextRunner` does not automatically scan the application's packages merely because the class has `@Component`.

To test back-off, either:

- Register the component via an appropriate configuration or component scan.
- Or use **withBean(MessageSender.class, ...)** to simulate bean presence by type.

A test mistakenly assuming `@Component` is auto-discovered will create the default bean and mislead the author about `@ConditionalOnMissingBean`.

### 20.4. Integration tests verify imports metadata

In a real starter, an auto-configuration can pass context runner tests (where the test supplied the class manually) yet **fail to be auto-discovered by consumer apps** if the artifact's imports file is wrong.

Hence a solid test suite often includes:

1. **Context runner tests**: prove behavior of each condition.
2. **Starter smoke/integration test**: verify the actual artifact and `AutoConfiguration.imports` discovery by Boot.
3. **Consumer integration test**: confirm user-defined beans take precedence inside a realistic application context when needed.

You do not need to run the entire application for every back-off variant.

## 21. Test patterns that look right but are misleading

### 21.1. Checking only that the custom bean is present

~~~java
assertThat(context)
        .hasBean("customMessageSender");
~~~

This passes even when `defaultMessageSender` was also created.

**Fix:** add assertions verifying the default is absent and the bean count matches.

### 21.2. Checking only that the default is absent

~~~java
assertThat(context)
        .doesNotHaveBean("defaultMessageSender");
~~~

This passes even if the auto-configuration was omitted, disabled, or failed a classpath condition.

**Fix:** assert the user bean exists and ensure the default appears on the no-user-bean branch in the same test suite.

### 21.3. Forgetting to import the auto-configuration under test

~~~java
new ApplicationContextRunner()
        .withBean(
                MessageSender.class,
                CustomMessageSender::new)
        .run(context -> {
            assertThat(context)
                    .doesNotHaveBean("defaultMessageSender");
        });
~~~

In a context that lacks `MessageSenderAutoConfiguration`, the default obviously never registers. The test says nothing about back-off.

**Fix:** make sure to include:

~~~java
.withConfiguration(
        AutoConfigurations.of(
                MessageSenderAutoConfiguration.class))
~~~

### 21.4. Calling @Bean methods manually

~~~java
MessageSenderAutoConfiguration config =
        new MessageSenderAutoConfiguration();
MessageSender sender = config.defaultMessageSender();
~~~

This simply calls a Java method. Spring never evaluates `@ConditionalOnMissingBean`, never registers bean definitions, and never runs auto-configuration lifecycle logic.

**Fix:** build an `ApplicationContext` and let Spring process the configuration class.

### 21.5. Mistaking @Primary for back-off

If a test only looks up by type:

~~~java
MessageSender sender =
        context.getBean(MessageSender.class);
~~~

and the custom bean carries `@Primary`, the lookup returns the custom bean even while the default still exists.

**Fix:** check both the registry count and the absence of the default bean.

### 21.6. Using a plain mock outside the context

~~~java
MessageSender fake = Mockito.mock(MessageSender.class);
~~~

The local variable `fake` does not automatically become a Spring bean. Conditions have no idea it exists.

**Fix:** register the mock as a bean in the test context when testing back-off; with context runner, use `withBean(MessageSender.class, () -> fake)`.

### 21.7. Confusing disabled-feature tests with back-off tests

With:

~~~java
.withPropertyValues("acme.message.enabled=false")
~~~

the default may be absent due to `ConditionalOnProperty`, not because of a user bean.

**Fix:** in back-off tests, keep all other conditions enabled so the auto-configuration can activate, varying only whether the user bean exists.

### 21.8. Assuming every bean instantiates immediately

A bean may be lazy or go through a factory/proxy. The constructor not having run does not mean the bean definition is absent.

**Fix:** assert bean definitions, names, and types per contract rather than counting constructor invocations.

### 21.9. Testing name collision instead of type replacement

If the user bean is given the exact name **defaultMessageSender**, you may be testing bean-name collision/overriding rather than type-based back-off.

**Fix:** intentionally give the custom bean a different name and verify `@ConditionalOnMissingBean(MessageSender.class)` still excludes the default.

## 22. Why not enable bean overriding to "fix" back-off?

Suppose after adding a custom bean, Spring reports:

~~~text
The bean 'messageSender' could not be registered.
A bean with that name has already been defined.
~~~

A hasty workaround is enabling:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

This alters Spring Boot's bean-definition overriding policy, yet it **does not prove** the auto-configuration is designed to back off.

Risks:

- Registration order can decide which bean wins.
- Configuration loses clarity.
- It can mask accidental duplicate registrations unrelated to user customization.
- Same-type beans with different names are not solved by name overriding.

For an extensible starter, the proper solution is usually:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

paired with a back-off test suite like the one shown here.

## 23. Back-off and the starter's public API

A well-designed starter tells users clearly:

- Which interfaces may they replace?
- Which bean type must they register?
- Is a specific bean name required?
- Will a default be created automatically if no custom bean exists?
- Does providing a custom bean disable the **entire integration** or only swap one component?
- Which classpath, property, or profile conditions still apply?

Example of a clear documented contract:

> If the application has not registered a `MessageSender` bean, the starter provides `DefaultMessageSender`. To customize, declare a bean implementing `MessageSender`; auto-configuration will not register the default bean.

A statement like that is far clearer than "can override config if needed." It pinpoints the extension point and back-off behavior that tests must protect.

### 23.1. Tests act as a compatibility contract

Suppose the library team refactors the annotation to:

~~~java
@ConditionalOnMissingBean(DefaultMessageSender.class)
~~~

instead of:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

This seemingly tiny change breaks the contract: users supply `CustomMessageSender`, not `DefaultMessageSender`, so the default still gets created.

An interface-based back-off test suite catches this regression immediately, even while the code compiles and the default-path test passes.

### 23.2. Scope abstractions accurately

If a starter allows multiple `NotificationSender` beans per channel or name, a missing-bean condition over the broad interface may be too coarse: supplying a custom email sender could unintentionally suppress the default SMS sender.

In that case, redesign the contract—for example:

- Split interfaces by role.
- Use intentional bean names or qualifiers.
- Split auto-configurations by module.
- Use custom configuration properties to select providers.

**`@ConditionalOnMissingBean` cannot automatically tell that "two beans share an interface yet serve different purposes."** Your API design determines which type or name constitutes a replacement.

## 24. Test matrix for an auto-configuration with back-off

As a starter grows, two basic tests may not suffice to guard interacting conditions.

An intentional test matrix:

| Scenario | Default bean | User bean | What to verify |
|---|---|---|---|
| Auto-config enabled, no user bean | Yes | No | Fallback works |
| Auto-config enabled, one matching user bean | No | Yes | Core back-off |
| User bean has different name from default | No | Yes | Type-based back-off |
| User bean declares concrete return type | No | Yes | Metadata suffices to match |
| User bean marked `@Lazy` | No | Yes | Based on definition, not awaiting instance |
| Two user beans of same type | No | Two | Back-off does not imply uniqueness |
| Property disables default | No | No | Distinguish other conditions from back-off |
| Property disabled, yet user defines bean | No | Yes | User bean independent of default condition |
| Parent context has user bean, `search=ALL` | No in child | Yes in parent | Proper hierarchy search scope |
| Parent has bean, `search=CURRENT` | Present in child | Yes in parent | Narrow search scope |
| Missing optional classpath dependency | No | Optional | Classpath condition tested separately |
| User supplies custom bean for downstream bean | No | Yes | Wiring uses the replacement |

Not every starter needs every row. If there is no parent context or optional dependency, skip those specialized tests.

**Core principle:** each test should vary **one major cause**, so when it fails, the team can distinguish type conditions, bean registration, profiles, classpath, and property conditions.

## 25. Organizing test classes for maintainability

Tests can be grouped by behavior:

~~~text
MessageSenderAutoConfigurationTests
  ├── defaultBeanIsRegistered
  ├── userBeanCausesBackOff
  ├── customBeanNameDoesNotMatter
  ├── disabledFeatureDoesNotRegisterDefault
  └── parentBeanIsConsidered

MessagingIntegrationTests
  ├── downstreamBeanUsesCustomSender
  └── starterIsImportedByConsumerApplication
~~~

An organizational pattern:

~~~java
class MessageSenderAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MessageSenderAutoConfiguration.class));

    @Test
    void defaultBeanIsRegistered() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(MessageSender.class);
            assertThat(context.getBean(MessageSender.class))
                    .isInstanceOf(DefaultMessageSender.class);
        });
    }

    @Test
    void userBeanCausesBackOff() {
        runner.withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(MessageSender.class);
                    assertThat(context.getBean(
                            MessageSender.class))
                            .isInstanceOf(CustomMessageSender.class);
                    assertThat(context)
                            .doesNotHaveBean("defaultMessageSender");
                });
    }
}
~~~

Each `run` call builds a fresh context. There is no need to write a single test that starts up, removes a bean, and registers another inside the same context to simulate back-off; conditions are already evaluated during bean definition registration.

### 25.1. Context runners compose cleanly without shared mutable state

The pattern:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MessageSenderAutoConfiguration.class));
~~~

with each test calling:

~~~java
runner.withBean(MessageSender.class,
        CustomMessageSender::new).run(...);
~~~

is a clean way to isolate scenarios. Avoid keeping a running `ApplicationContext` as a shared field and mutating its bean definitions across tests, since you would no longer be testing initial bootstrapping.

### 25.2. Avoid test fixtures with unintended side effects

In auto-configuration tests, a default bean should never send real emails, hit production endpoints, build schemas, or open external sockets solely to test conditions.

If an implementation triggers side effects at creation time, tests can:

- Supply a mock/stub external client.
- Point configuration properties to a fake endpoint.
- Separate bean construction logic from executing external operations.
- Inspect bean definitions without invoking risky business operations.

The goal of back-off testing is **the bean selection contract**, not performing real side effects.

## 26. When an application lets users customize multiple beans

A starter may provide multiple roles:

~~~text
MessageSender
MessageTemplateResolver
MessageAuditSink
~~~

Each role can have its own default:

~~~java
@AutoConfiguration
public class MessagingDefaultsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageSender.class)
    MessageSender defaultMessageSender() {
        return new DefaultMessageSender();
    }

    @Bean
    @ConditionalOnMissingBean(MessageTemplateResolver.class)
    MessageTemplateResolver defaultTemplateResolver() {
        return new DefaultTemplateResolver();
    }

    @Bean
    @ConditionalOnMissingBean(MessageAuditSink.class)
    MessageAuditSink defaultAuditSink() {
        return new DefaultAuditSink();
    }
}
~~~

These are illustrative interfaces and implementations, not Spring Boot classes.

If the user replaces only `MessageSender`, the expected state is:

~~~text
MessageSender:           custom
MessageTemplateResolver: default
MessageAuditSink:        default
~~~

A helpful test:

~~~java
@Test
void customizingSenderDoesNotDisableOtherDefaults() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    MessagingDefaultsAutoConfiguration.class))
            .withBean(
                    MessageSender.class,
                    CustomMessageSender::new)
            .run(context -> {
                assertThat(context).hasNotFailed();

                assertThat(context.getBean(
                        MessageSender.class))
                        .isInstanceOf(
                                CustomMessageSender.class);

                assertThat(context)
                        .doesNotHaveBean(
                                "defaultMessageSender");
                assertThat(context)
                        .hasSingleBean(
                                MessageTemplateResolver.class);
                assertThat(context)
                        .hasSingleBean(
                                MessageAuditSink.class);
            });
}
~~~

This test guards against a classic design bug: placing `@ConditionalOnMissingBean(MessageSender.class)` **at the auto-configuration class level**, causing the entire group of defaults to be skipped when the user only replaces one component.

### 26.1. Class-level vs. @Bean method-level conditions have different scopes

Class-level example:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(MessageSender.class)
public class MessagingDefaultsAutoConfiguration {
    // Multiple @Bean methods.
}
~~~

If the user supplies `MessageSender`, **the entire auto-configuration class** is skipped, including other beans the user never replaced.

Conversely, placing the condition on each `@Bean` method lets each default back off independently.

This is a primary reason to **place conditions at the level matching the replacement contract**.

### 26.2. When should a condition sit at class level?

When the entire group of beans genuinely must toggle together as a unit, such as:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.messaging",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class MessagingAutoConfiguration {
    // ...
}
~~~

Here the feature-enabled condition governs the whole module, while `@ConditionalOnMissingBean` for each extension point sits on individual `@Bean` methods.

There is no rule forcing every condition onto `@Bean`; pick the scope matching desired behavior and test each branch.

## 27. Integrating with Spring Boot Actuator for diagnostics

In a running application, Spring Boot Actuator offers helpful inspection endpoints:

| Endpoint | Usefulness when investigating back-off |
|---|---|
| **/actuator/beans** | Verify which default and custom beans actually reside in `ApplicationContext`. |
| **/actuator/conditions** | Read recorded auto-configuration condition outcomes. |
| **/actuator/configprops** | Inspect configuration properties beans influencing defaults. |
| **/actuator/env** | Inspect feature flag values and property sources. |

These endpoints are not necessarily exposed over HTTP by default. Because they reveal internal metadata, apply proper authentication, authorization, and redaction/exposure policies.

### 27.1. Do not use Actuator as a substitute for automated tests

Actuator reports **the state of one running instance**. `ApplicationContextRunner` tests guard the **auto-configuration contract** across code changes.

If a developer accidentally changes:

~~~java
@ConditionalOnMissingBean(MessageSender.class)
~~~

to:

~~~java
@ConditionalOnMissingBean(DefaultMessageSender.class)
~~~

an interface-based back-off test suite catches the break immediately in the pipeline instead of waiting until someone inspects a deployed instance.

### 27.2. Conditions report must be interpreted accurately

A non-matching missing-bean condition is the **expected outcome** when a user provides a bean. Do not mistake every negative match in the report for a Spring Boot error.

Conversely, a positive match for a missing-bean condition shows the default will register **provided all other conditions also match**. Always cross-check against the bean registry.

## 28. Debugging when a back-off test fails

### 28.1. Custom bean registered, yet default still exists

Check:

1. Does `@ConditionalOnMissingBean` specify the right interface type?
2. Does the user `@Bean` method declare a specific enough return type?
3. Is the bean in the same context or a parent context matching the search strategy?
4. Is auto-configuration processed after user configuration?
5. Are multiple auto-configurations creating `MessageSender`?
6. Is there a name/type match difference across conditions?

If the condition checks **DefaultMessageSender.class** while the user supplies **CustomMessageSender**, consider switching to the interface type `MessageSender.class` per contract.

### 28.2. No default bean even without a custom bean

Check:

1. Was the auto-configuration imported?
2. Is a `@ConditionalOnProperty` evaluating to false?
3. Was `@ConditionalOnClass` skipped due to a missing dependency?
4. Is a parent context supplying `MessageSender`?
5. Did a test fixture or another auto-configuration register a bean of the same type?
6. Was the `@Bean` method excluded by a class-level condition?

Do not rush to blame `@ConditionalOnMissingBean` when another condition may be blocking the bean.

### 28.3. Context startup test fails due to multiple candidates

If you see:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
~~~

either the auto-configuration failed to back off, or the user registered multiple beans of the same type.

Check with a test context omitting single-value consumers to inspect all `MessageSender` beans, then determine:

- Is there an unintended default?
- Did the user register two candidates?
- Is `@Primary`/`@Qualifier` missing, or is `@ConditionalOnSingleCandidate` needed?

`@Primary` can resolve an intentional injection ambiguity, **not substitute for back-off verification**.

### 28.4. withBean test passes, yet real app still creates the default

Possible causes:

- The real app did not register the user class via component scan or import.
- The app's `@Bean` factory declares an overly broad return type such as `Object`.
- The starter is imported differently than in tests.
- Production profile/property conditions differ from tests.
- Auto-configuration ordering or parent context differs.

Add a test using **withUserConfiguration** matching the production signature, or an integration test representative of how users actually integrate.

### 28.5. Expected condition report entry is missing

If the auto-configuration class/method name does not appear in the report:

- Verify the runner includes `AutoConfigurations.of` with the right class.
- Verify the class carries `@AutoConfiguration` or is imported appropriately.
- Check whether a class-level condition excluded evaluation before reaching methods.
- For a real starter, check `AutoConfiguration.imports`.

If a `@Bean` method is never processed by Spring, its `@ConditionalOnMissingBean` is never evaluated either.

### 28.6. Back-off passes in context runner, yet differs in @SpringBootTest

The context runner contains only beans/configurations explicitly added by the test. `@SpringBootTest` can load additional:

- Component scanning.
- Configuration properties.
- Other auto-configurations.
- Test replacements/mocks.
- Profile-specific beans.
- Parent contexts or framework beans.

Thus integration tests may contain different candidates. Avoid dumping every auto-configuration into the context runner just to "look more like `@SpringBootTest`" right away; identify which extra bean altered the result and construct a controlled integration scenario.

## 29. Common misconceptions

**"Back-off means Spring creates the default and then the custom bean overwrites it."**  
No. With proper conditional registration, the default bean definition is never registered when the condition fails.

**"@Primary is also a way to make the default back off."**  
No. `@Primary` selects a candidate during dependency injection; it does not remove the default bean from the context.

**"Enabling bean overriding solves every starter issue."**  
No. Bean overriding by name differs from condition-based back-off by type. Enabling overriding can mask design flaws.

**"A custom object created with new is visible to @ConditionalOnMissingBean."**  
No. The object must be registered as a Spring bean within the matching scope.

**"@ConditionalOnMissingBean always checks only the @Bean method's name."**  
No. It can check by type, name, annotation, and other criteria. On a `@Bean` method without explicit attributes, Boot infers the return type per supported rules.

**"A user bean implementing the interface is always recognized even if @Bean returns Object."**  
Not necessarily. Conditions rely on bean metadata available at evaluation time.

**"If the default is absent, it must have backed off because of a user bean."**  
No. The auto-configuration might not have been imported, or another classpath/property condition blocked it.

**"Testing only that the custom bean is in the context is enough."**  
No. The default could still coexist alongside the custom bean; assert that the default is absent and the candidate count matches.

**"Testing only that the default bean is absent is enough."**  
No. If you forgot to add the auto-configuration to the context, an absent default proves nothing about back-off.

**"withBean and withUserConfiguration are completely equivalent in every case."**  
No. `withBean` is handy for supplying a type; `withUserConfiguration` also exercises factory method signatures, names, scopes, conditions, and user config metadata.

**"It doesn't matter where @ConditionalOnMissingBean is placed; the result is always the same."**  
No. The condition depends on bean definitions already processed at evaluation time; auto-configuration ordering matters.

**"When two user beans exist, auto-config automatically picks the right one."**  
No. The missing-bean condition backs off, yet injection can still be ambiguous.

**"Parent beans are always ignored."**  
No. `SearchStrategy` controls search scope; the default typically checks parent contexts.

**"@ConditionalOnProperty false means user beans are also removed."**  
No. A condition on the default factory method does not automatically remove independently registered user beans.

**"In @SpringBootTest, merely injecting the custom type proves back-off."**  
No. A default could still exist while `@Primary` picks the custom bean.

**"If context runner tests pass, the starter is guaranteed to be discovered in consumer apps."**  
No. `AutoConfigurations.of` imports the class directly in tests; packaging and `AutoConfiguration.imports` require separate verification when needed.

**"Every negative match in the Condition Evaluation Report is an error."**  
No. A negative match on a missing-bean condition is the **expected behavior** when a user customizes the bean.

## 30. Workflow for building back-off tests for a new auto-configuration

When writing a starter or auto-configuration supporting custom beans, follow this workflow:

### Step 1 — Identify the extension point

Choose the public interface or type applications may replace, such as `MessageSender`.

Do not start by slapping a missing-bean condition onto arbitrary concrete classes. Decide the **user customization contract** first.

### Step 2 — Write the default @Bean method

~~~java
@Bean
@ConditionalOnMissingBean(MessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

If the auto-config also depends on classpath or properties, declare those conditions at the appropriate level.

### Step 3 — Create a context runner with the auto-configuration

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MessageSenderAutoConfiguration.class));
~~~

### Step 4 — Test the default path

Register no custom `MessageSender`. Assert the context starts cleanly, contains exactly one `MessageSender`, and uses `DefaultMessageSender`.

### Step 5 — Test the back-off path

Register a custom `MessageSender` via `withBean` or `withUserConfiguration`. Assert the custom bean exists, the default is absent, candidate count matches, and downstream wiring uses the custom bean.

### Step 6 — Test other conditions separately

If there are feature flags, classpath dependencies, profiles, or parent contexts, write separate tests for each. Never confuse a default absent due to a disabled feature with back-off caused by a custom bean.

### Step 7 — Test at the integration level when needed

When publishing a real starter, add a smoke test verifying the auto-configuration is discovered from the packaged artifact and a consumer application can supply a custom bean.

### Step 8 — Guard against regressions

Whenever changing interfaces, bean names, scopes, return types, condition placement, or auto-configuration ordering, keep default/back-off tests intact to protect user-facing behavior.

### Decision diagram

~~~text
Design default bean for starter
                │
                ▼
Identify user-replaceable type
                │
                ▼
@ConditionalOnMissingBean(type)
                │
                ▼
ApplicationContextRunner + AutoConfigurations.of
                │
          ┌─────┴─────┐
          │           │
       No user     User bean
        bean        present
          │           │
          ▼           ▼
     Default       No default
     present        present
          │           │
          └─────┬─────┘
                ▼
     Bean registry consistent?
                │
                ▼
   Test additional conditions if any
                │
                ▼
  Integration/packaging test when needed
~~~

## 31. Practice exercises

### Exercise 1 — Spot the wrong condition type

Auto-configuration:

~~~java
@Bean
@ConditionalOnMissingBean(DefaultMessageSender.class)
MessageSender defaultMessageSender() {
    return new DefaultMessageSender();
}
~~~

Application:

~~~java
@Bean
MessageSender customMessageSender() {
    return new CustomMessageSender();
}
~~~

**Question:** Why can two `MessageSender` beans end up in the context?

**Guidance:** The condition checks for absence of the **concrete type `DefaultMessageSender`**, not the public contract `MessageSender`. `CustomMessageSender` is not a `DefaultMessageSender`, so the default is still created.

**Contract-aligned fix:** use `@ConditionalOnMissingBean(MessageSender.class)`, then test the user-bean branch.

### Exercise 2 — Pick assertions sufficient to prove back-off

Test:

~~~java
runner.withBean(MessageSender.class,
                CustomMessageSender::new)
        .run(context -> {
            assertThat(context).hasNotFailed();
        });
~~~

**Question:** Which assertions are missing from this test?

**Guidance:** Verify exactly one `MessageSender` exists, the instance is the custom implementation, and `defaultMessageSender` does not exist. Asserting only startup success does not protect the extension contract.

### Exercise 3 — Distinguish feature disabled from user override

An auto-configuration has `@ConditionalOnProperty` and `@ConditionalOnMissingBean`. A test sets `acme.message.enabled=false` and sees the default is absent.

**Question:** Is concluding "back-off works" valid?

**Answer:** Not yet. The default may be absent solely because the feature is disabled. Enable the feature in the back-off case and supply a matching user bean, while keeping an independent disabled test.

### Exercise 4 — Try using a different name

Application registers:

~~~java
@Bean("myPreferredSender")
MessageSender sender() {
    return new CustomMessageSender();
}
~~~

**Question:** If the auto-config uses `@ConditionalOnMissingBean(MessageSender.class)`, should the default be created?

**Expected answer:** No. Even though `myPreferredSender` differs from `defaultMessageSender`, its type satisfies the replacement contract.

### Exercise 5 — Read two test outcomes

Results:

~~~text
Test A:
  DefaultMessageSender exists
  CustomMessageSender absent

Test B:
  DefaultMessageSender exists
  CustomMessageSender exists
~~~

**Question:** Which test shows a back-off failure?

**Guidance:** Assuming Test B genuinely registered a qualifying custom bean while other conditions allowed auto-configuration to run, the default remaining present violates the back-off contract. Inspect the condition type, bean metadata, ordering, and bean names.

### Exercise 6 — Parent context

Parent holds `CustomMessageSender`. Child imports `MessageSenderAutoConfiguration`. Tests show the child does not create the default.

**Question:** Why? If you want the child to always create its own default regardless of the parent bean, what should you inspect?

**Guided answer:** By default, the condition searches the context hierarchy and sees the parent bean. Check the `search` attribute on `@ConditionalOnMissingBean`, such as `SearchStrategy.CURRENT`, and test the intended scope.

## Core takeaways

**Back-off is the contract of yielding default bean creation to the application.** In Spring Boot, an auto-configuration can declare **@ConditionalOnMissingBean(MessageSender.class)** so it provides `DefaultMessageSender` only when no matching `MessageSender` bean exists. This differs completely from `@Primary` or bean overriding: the default bean definition is not registered when a custom bean satisfies the condition.

**Proper testing requires at least two branches.** With **ApplicationContextRunner** and **AutoConfigurations.of**, tests without a user bean must show the default is created. Tests with a user bean must confirm the custom bean exists, the default is absent, and candidate count is right. Use **withBean** to quickly supply a custom type or **withUserConfiguration** to test realistic `@Bean` signatures. Asserting only context startup success or only default absence is insufficient.

**Do not overlook conditions and processing order.** `@ConditionalOnMissingBean` relies on bean metadata present at evaluation time; return types, name/type matching, auto-configuration ordering, parent contexts, and other conditions all affect outcomes. Use the Condition Evaluation Report to diagnose causes and inspect the bean registry to verify behavior. When publishing a starter, add integration tests for the imports discovery mechanism as needed.

The ultimate goal is not merely "testing that `@ConditionalOnMissingBean` is annotated," but ensuring **applications can provide custom beans without Spring Boot creating competing defaults**, while still receiving convenient defaults whenever the application chooses not to supply one.
