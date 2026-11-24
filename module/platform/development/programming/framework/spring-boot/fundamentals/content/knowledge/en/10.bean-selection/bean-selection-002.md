# @Qualifier and Identifying Dependency Groups

In Spring, an interface can have multiple implementations coexisting within the same application context. For example, an application might send notifications via email, SMS, or console output; read data from an in-memory cache or a distributed cache; or call a sandbox payment service or a live payment gateway. When a service simply declares that it needs a bean by its interface type, Spring may not know which implementation to choose.

**`@Qualifier` helps narrow down the set of matching beans by a meaningful label or criterion.** It is commonly used alongside constructor injection to specify the exact dependency a component requires. Qualifiers can also be used to group multiple beans sharing the same role and inject the entire group into a collection.

In the **Bean Selection** chapter of *Spring Boot Fundamentals*, three concepts should be distinguished:

- **Bean type:** the class or interface type that the bean provides.
- **Bean name:** the identifier name of the bean in the Spring container.
- **Qualifier:** metadata used to describe or filter matching candidates at an injection point.

These three concepts can be related, but they are not synonymous. Understanding them accurately helps avoid multiple-bean-of-same-type errors while organizing dependency groups by function, environment, or characteristics needed by the application.

## 1. Why does Spring need qualifiers?

Suppose there is a notification sending contract:

```java
package com.example.notification;

public interface NotificationSender {
    void send(String recipient, String message);
}
```

The application has two implementations:

```java
package com.example.notification;

import org.springframework.stereotype.Component;

@Component
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("Email to " + recipient + ": " + message);
    }
}
```

```java
package com.example.notification;

import org.springframework.stereotype.Component;

@Component
public class SmsNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}
```

Suppose both classes are within the component scan scope. Spring will register two beans sharing the same `NotificationSender` interface type. Now a service requires:

```java
@Service
public class RegistrationService {

    private final NotificationSender sender;

    public RegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

The constructor has a dependency of type `NotificationSender`, but there are two equally matching candidates in the context. Without additional metadata or selection rules, Spring cannot uniquely pick one and may report `NoUniqueBeanDefinitionException` during bean creation.

This does not mean Spring does not support multiple implementations. Multiple implementations are completely valid. The problem only arises when **a single injection point requires a unique bean, yet more than one candidate remains**.

## 2. How does @Qualifier help select a bean?

Spring provides the annotation:

```java
import org.springframework.beans.factory.annotation.Qualifier;
```

We can attach a qualifier at the injection point:

```java
@Service
public class RegistrationService {

    private final NotificationSender sender;

    public RegistrationService(
            @Qualifier("emailNotificationSender")
            NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

In the default component scan example, bean names are typically generated from class names with a lowercase first letter: `emailNotificationSender` and `smsNotificationSender`. `@Qualifier("emailNotificationSender")` asks Spring to choose a candidate whose qualifier matches that value; the bean name can be used as a fallback criterion during candidate lookup.

After adding the qualifier, the service receives the email bean. `RegistrationService` still depends on the `NotificationSender` interface, without needing to know how the concrete class is created.

### 2.1. Bean names can be set explicitly

Instead of relying on the default name, you can declare a bean name:

```java
@Component("emailSender")
public class EmailNotificationSender implements NotificationSender {
    // ...
}
```

The corresponding injection point:

```java
public RegistrationService(
        @Qualifier("emailSender") NotificationSender sender
) {
    this.sender = sender;
}
```

For beans created via Java configuration:

```java
@Configuration
class NotificationConfiguration {

    @Bean("emailSender")
    NotificationSender emailNotificationSender() {
        return new EmailNotificationSender();
    }
}
```

The bean name declared via `@Component("...")` or `@Bean("...")` is an identifier in the container. When a specific bean is needed, the qualifier value may match the bean name, but it should be clearly understood that **a qualifier is a candidate-filtering criterion; a bean name is an identifier**.

### 2.2. @Qualifier does not create a bean

Adding:

```java
@Qualifier("email")
NotificationSender sender
```

does not automatically create an `EmailNotificationSender`. Spring still requires a matching bean in the context. A qualifier only helps identify which bean among the already-registered candidates to choose.

Similarly, importing a Java class or adding a Maven/Gradle dependency only makes the class present on the classpath; it does not mean the class is registered as a bean and ready to inject.

## 3. Distinguishing bean name, type, and qualifier

| Concept | Answers the question | Example |
| --- | --- | --- |
| Type | What type does the bean provide? | `NotificationSender` |
| Bean name | Under what name is the bean registered? | `emailSender` |
| Qualifier | What characteristic/label does the bean have for candidate filtering? | `email`, `external`, `reliable` |

A bean can:

- Have a concrete type and multiple parent types/interfaces.
- Have a bean name in the context.
- Carry one or more meaningful qualifiers.

For example:

```java
@Component("smtpSender")
@Qualifier("external")
public class SmtpNotificationSender implements NotificationSender {
    // ...
}
```

The bean above has the name `smtpSender` and carries the qualifier `external`. These two pieces of information serve two different purposes:

- `@Qualifier("external")` describes a characteristic that is meaningful for how dependencies are selected.
- `@Component("smtpSender")` assigns a specific identifier name to the bean.

In large applications, using bean names as qualifiers everywhere can couple code to naming details. Meaningful qualifiers such as `external`, `transactional`, `regional`, or `readOnly` usually express intent better.

### 3.1. A qualifier value can match a bean name

In Spring's dependency resolution mechanism, the `@Qualifier` value is evaluated as a qualifier criterion; the bean name can also be considered as a fallback when applicable. Thus, for example, `@Qualifier("emailSender")` can select a bean named `emailSender` even when the class has no separate `@Qualifier("emailSender")` annotation.

However, one should not conclude that a qualifier is merely another syntax for referencing a bean by name. It can filter multiple beans carrying the same label and can be expressed using custom annotations with typed attributes.

## 4. How do @Primary and @Qualifier differ?

`@Primary` marks a bean as the preferred candidate when Spring needs to choose a single bean among multiple candidates of the same type. `@Qualifier` narrows candidates based on metadata at the injection point.

Example marking the email sender as the default choice:

```java
@Component
@Primary
public class EmailNotificationSender implements NotificationSender {
    // ...
}
```

A service that does not declare a qualifier:

```java
@Service
class DefaultRegistrationService {

    private final NotificationSender sender;

    DefaultRegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

If there is only one matching `@Primary` bean in the candidate set, Spring prefers that bean. Another service can explicitly specify SMS:

```java
@Service
class SecurityAlertService {

    private final NotificationSender sender;

    SecurityAlertService(
            @Qualifier("smsNotificationSender")
            NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

### 4.1. Comparison by purpose

| Criterion | `@Primary` | `@Qualifier` |
| --- | --- | --- |
| Role | Select the preferred default bean | Filter candidates by criteria |
| Common declaration site | On a component class or `@Bean` method | On the bean and/or injection point |
| When useful | Most injection points should use one default implementation | Individual injection points need a specific implementation/group |
| Can be used together? | Yes | Yes |
| Creates a new bean? | No | No |

You should not use `@Primary` to solve every multiple-bean case. If a service needs SMS as a functional requirement, a qualifier expresses the intent more clearly than changing the application-wide default bean.

### 4.2. A qualifier does not have to point to only one bean

A qualifier can match multiple beans. When injecting a single dependency, multiple candidates satisfying the condition can still cause ambiguity if there is no further distinguishing rule. However, when injecting a collection, having multiple beans share a qualifier is exactly what we want.

## 5. Using qualifiers to identify a dependency group

A common situation is when a service needs **all implementations belonging to the same group**.

For example, a system has several types of senders, but one flow needs to invoke every channel marked as capable of sending externally. We can attach the same qualifier to those beans:

```java
@Component
@Qualifier("external")
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Send email via external provider.
    }
}
```

```java
@Component
@Qualifier("external")
public class SmsNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Send SMS via external provider.
    }
}
```

Another sender only writes to the console for development:

```java
@Component
@Qualifier("local")
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("LOCAL: " + recipient + " - " + message);
    }
}
```

Now a service can receive the entire external group:

```java
@Service
public class ExternalBroadcastService {

    private final List<NotificationSender> senders;

    public ExternalBroadcastService(
            @Qualifier("external")
            List<NotificationSender> senders
    ) {
        this.senders = senders;
    }

    public void broadcast(String recipient, String message) {
        senders.forEach(sender -> sender.send(recipient, message));
    }
}
```

Spring finds beans whose type is compatible with `NotificationSender`, then uses the `external` qualifier to filter the candidate set for the collection. The result in this example is the email and SMS senders; the console sender carrying the `local` qualifier does not belong to the group.

This is an important meaning of qualifiers: **one label can represent a group of beans**, not necessarily a unique identifier.

### 5.1. Injecting List, Set, or Map

Spring can inject multiple beans by type:

```java
public NotificationCoordinator(List<NotificationSender> senders) {
    this.senders = senders;
}
```

With a qualifier:

```java
public NotificationCoordinator(
        @Qualifier("external")
        List<NotificationSender> senders
) {
    this.senders = senders;
}
```

Some common forms:

| Dependency type | Meaning |
| --- | --- |
| `List<NotificationSender>` | List of beans matching by type |
| `Set<NotificationSender>` | Set of beans matching by type |
| `Map<String, NotificationSender>` | Map of beans keyed by bean name with instance values |
| `@Qualifier("external") List<NotificationSender>` | List of beans of the same type matching the qualifier |
| `@Qualifier("external") Set<NotificationSender>` | Set of beans of the same type matching the qualifier |

For `Map<String, T>` injected in Spring's collection style, the key is normally the bean name and the value is the bean instance. A qualifier at the injection point can filter the set of beans before putting them into the collection.

If the collection is empty, check whether any matching beans have been registered, whether the qualifier on the bean and the qualifier at the injection point match, and whether profile/conditional rules exclude the beans from the context.

### 5.2. A dependency group is not a single bean

Do not use `@Primary` to represent a group. `@Primary` resolves priority for single-valued injection; a qualifier on a collection represents a group of beans sharing the same characteristic.

If an operation needs to run on every bean in a group, inject a collection. If only one default-selected implementation is needed, use `@Primary` or a single-target qualifier. Choose the structure based on the behavior the service actually needs.

## 6. Creating custom qualifiers with business meaning

Strings like `"external"` or `"local"` are easy to start with, but as a project grows, many qualifier strings can become duplicated, misspelled, or hard to locate where they are defined. Spring allows creating **custom qualifier annotations** by marking the annotation with `@Qualifier`.

For example, a regional notification sending system:

```java
package com.example.notification;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Region {
    String value();
}
```

`@Region` is a custom qualifier with a `value` attribute. It can be placed on component classes, `@Bean` methods, or suitable injection points.

Two implementations:

```java
@Component
@Region("asia")
public class AsiaEmailSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Send through email infrastructure dedicated to the Asia region.
    }
}
```

```java
@Component
@Region("europe")
public class EuropeEmailSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Send through email infrastructure dedicated to the Europe region.
    }
}
```

Injection point:

```java
@Service
public class RegionalNotificationService {

    private final NotificationSender sender;

    public RegionalNotificationService(
            @Region("asia") NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

Reading the constructor makes it clear that the service needs a `NotificationSender` for the Asia region. If the class is renamed to `AsiaMailAdapter` or the bean name changes, the regional qualifier can stay the same because it expresses a characteristic rather than a class name.

### 6.1. Custom qualifiers do not replace types

`@Region("asia")` is still used alongside the dependency type. If a class does not implement `NotificationSender` or is not a compatible bean, simply adding `@Region("asia")` does not turn it into a sender.

The filtering process can be understood in two ideas:

1. Identify beans whose type matches the injection point.
2. Keep those beans that satisfy the required qualifiers.

Therefore, qualifiers help classify implementations within the same role; they do not replace Java's type system.

## 7. Combining multiple qualifiers to describe multiple dimensions

A bean can be described across multiple characteristics. For example, an application has multiple notification channels across multiple regions:

| Implementation | Region | Channel |
| --- | --- | --- |
| `AsiaEmailSender` | Asia | Email |
| `AsiaSmsSender` | Asia | SMS |
| `EuropeEmailSender` | Europe | Email |
| `EuropeSmsSender` | Europe | SMS |

We can create the `Channel` qualifier:

```java
package com.example.notification;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Channel {
    String value();
}
```

Attach both qualifiers to the beans:

```java
@Component
@Region("asia")
@Channel("email")
public class AsiaEmailSender implements NotificationSender {
    // ...
}
```

```java
@Component
@Region("asia")
@Channel("sms")
public class AsiaSmsSender implements NotificationSender {
    // ...
}
```

```java
@Component
@Region("europe")
@Channel("email")
public class EuropeEmailSender implements NotificationSender {
    // ...
}
```

A service requiring email in Asia:

```java
@Service
public class AsiaEmailNotificationService {

    private final NotificationSender sender;

    public AsiaEmailNotificationService(
            @Region("asia")
            @Channel("email")
            NotificationSender sender
    ) {
        this.sender = sender;
    }
}
```

Spring must find a bean compatible with `NotificationSender` that satisfies both qualifier metadata entries. This is multidimensional identification: region and channel.

If a bean lacks a required qualifier, it is not a matching candidate for that injection point. When using multiple qualifiers, treat them as combined conditions; do not attach arbitrary metadata to beans and expect Spring to infer business meaning on its own.

### 7.1. Grouping along one dimension

We can also inject all senders in Asia:

```java
public AsiaBroadcastService(
        @Region("asia")
        List<NotificationSender> senders
) {
    this.senders = senders;
}
```

The result consists of `AsiaEmailSender` and `AsiaSmsSender`. If you want all email senders across all regions, use `@Channel("email") List<NotificationSender>`. If you want the exact intersection of Asia + email, combine both qualifiers.

## 8. Marker annotation qualifiers

Not every qualifier needs a value. Some characteristics only have two clear groups, such as persistent storage implementations or development-only implementations.

You can create a marker qualifier:

```java
package com.example.storage;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Persistent {
}
```

Attach it to the beans:

```java
@Component
@Persistent
public class PostgresCustomerStore implements CustomerStore {
    // ...
}
```

```java
@Component
@Persistent
public class MongoCustomerStore implements CustomerStore {
    // ...
}
```

Inject the group:

```java
@Service
public class CustomerBackupService {

    private final List<CustomerStore> persistentStores;

    public CustomerBackupService(
            @Persistent List<CustomerStore> persistentStores
    ) {
        this.persistentStores = persistentStores;
    }
}
```

In the example, `@Persistent` is metadata carrying application meaning. Implementations in the same group can be injected as a collection. If a service needs exactly one persistent store, there must be an additional selection rule or a more specific qualifier.

Marker qualifiers help avoid arbitrary strings and help IDEs find usages. However, you should not create a new annotation if there is only one injection point and one single bean; using a simple `@Qualifier("...")` may be enough.

## 9. Placing qualifiers on a class or a @Bean method?

Spring allows attaching qualifiers to component classes or bean methods.

### 9.1. Component-scanned class

```java
@Component
@Qualifier("fast")
public class InMemoryCache implements CacheStore {
    // ...
}
```

### 9.2. Bean created via @Bean

```java
@Configuration
class CacheConfiguration {

    @Bean
    @Qualifier("fast")
    CacheStore inMemoryCache() {
        return new InMemoryCache();
    }

    @Bean
    @Qualifier("durable")
    CacheStore redisCache() {
        return new RedisCacheStore();
    }
}
```

In the example, `InMemoryCache` and `RedisCacheStore` are hypothetical implementation classes. The qualifier attached to the `@Bean` method becomes metadata of the bean provided by that method.

Injection point:

```java
public CacheCoordinator(
        @Qualifier("durable") CacheStore cacheStore
) {
    this.cacheStore = cacheStore;
}
```

When a third-party class cannot have its annotations edited, configuring via a `@Bean` method lets you attach a qualifier to the bean without modifying that class's source code.

### 9.3. Avoid placing qualifiers in the wrong spot

If a class is created by a `@Bean` method, bean metadata is typically declared on the configuration method. Adding annotations on the implementation class is not always the clearest approach, especially when the same class is used to create multiple beans for different purposes.

Place the qualifier where it clearly shows which bean is being defined. When the same class creates two beans with two different configurations, qualifiers on individual `@Bean` methods are usually more readable than a fixed qualifier on the class.

## 10. Can @Qualifier be used with @Primary?

Yes. `@Primary` and `@Qualifier` work together during candidate selection.

For example:

```java
@Bean
@Primary
@Qualifier("default")
NotificationSender defaultSender() {
    return new EmailNotificationSender();
}

@Bean
@Qualifier("urgent")
NotificationSender urgentSender() {
    return new SmsNotificationSender();
}
```

Expected result:

- A `NotificationSender` injection point without a qualifier can receive the matching primary bean.
- An `@Qualifier("urgent") NotificationSender` injection point requests the bean with the `urgent` qualifier.
- An `@Qualifier("default") NotificationSender` injection point can select the bean marked with the `default` qualifier.

`@Primary` does not make a bean carry all qualifiers of other beans. It only marks priority when choosing a single bean among matching candidates.

If multiple beans carry `@Primary` or multiple beans still satisfy a qualifier for single injection, the criteria must be made more specific. Do not rely on scan order or file order to guess which bean is chosen.

## 11. @Qualifier and runtime bean selection

A very important point: **qualifiers are used when Spring resolves dependencies**, usually during bean creation or when retrieving dependencies through container mechanisms. They do not automatically reselect implementations per request.

Suppose an application has both email and SMS:

```java
@Service
class NotificationService {

    private final NotificationSender sender;

    NotificationService(@Qualifier("email") NotificationSender sender) {
        this.sender = sender;
    }
}
```

This service is wired with the email bean. If a request needs to send SMS, the fixed qualifier on the constructor will not automatically switch to SMS for that request.

If selection depends on runtime data, such as a request containing `channel=email` or `channel=sms`, inject the set of implementations and choose according to application rules:

```java
@Service
public class DynamicNotificationService {

    private final Map<String, NotificationSender> senders;

    public DynamicNotificationService(
            Map<String, NotificationSender> senders
    ) {
        this.senders = senders;
    }

    public void send(
            String channel,
            String recipient,
            String message
    ) {
        NotificationSender sender = senders.get(channel + "Sender");
        if (sender == null) {
            throw new IllegalArgumentException(
                    "Unsupported notification channel: " + channel
            );
        }
        sender.send(recipient, message);
    }
}
```

This is a simple example illustrating runtime selection; key names must be managed consistently with bean names and require explicit validation. In larger systems, you can use a registry/factory with a clear API instead of concatenating bean name strings in the service.

Another option is to inject `List<NotificationSender>` and build a map based on a property exposed by each implementation. This avoids forcing business logic to know Spring bean names.

### 11.1. When to use qualifiers, and when to use strategy/factory?

| Need | Suitable approach |
| --- | --- |
| Service always uses email sender | Constructor injection with `@Qualifier("email")` |
| Service needs all external senders | `@Qualifier("external") List<NotificationSender>` |
| Request decides email or SMS | Inject sender collection and select via factory/strategy |
| System has one default sender | `@Primary` |
| An optional module is only enabled in dev | Profile/condition configuration, optionally combined with qualifiers if multiple candidates exist |

Do not use qualifiers as a dynamic business router. They handle wiring, whereas decisions based on requests or customer data should be expressed in application logic.

## 12. How does @Qualifier differ from @Profile and @Conditional?

These three mechanisms often appear near each other in bean configuration, but they answer different questions:

| Mechanism | Question |
| --- | --- |
| `@Qualifier` | Among already-registered beans matching by type, which bean or group matches the injection point? |
| `@Profile` | Is this configuration or bean registered in the active profile? |
| `@Conditional...` | Is this configuration or bean registered when a specific condition is satisfied? |

For example:

```java
@Configuration
@Profile("dev")
class DevNotificationConfiguration {

    @Bean
    @Qualifier("local")
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }
}
```

The bean above is only provided when the `dev` profile matches. Once it is registered, the `local` qualifier can be used to select the bean at an injection point. A qualifier does not activate a profile, and a profile does not automatically replace distinguishing between multiple beans of the same type.

If a service requires `@Qualifier("local")` but the application runs with the `prod` profile so the local bean is not created, Spring may fail to find a matching candidate. This is a different error from having multiple beans with the same qualifier.

## 13. Ordering of dependency groups

When injecting `List<T>` or an array of beans, processing order sometimes matters. For example, a chain of validators or processors may need to run in a deterministic sequence.

Spring supports `@Order` or the `Ordered` interface in appropriate collection injection scenarios:

```java
@Component
@Order(10)
class FirstNotificationProcessor implements NotificationProcessor {
    // ...
}

@Component
@Order(20)
class SecondNotificationProcessor implements NotificationProcessor {
    // ...
}
```

When injected:

```java
public NotificationPipeline(List<NotificationProcessor> processors) {
    this.processors = processors;
}
```

`@Order` helps determine priority order in collections that Spring sorts using order metadata. Smaller numbers generally have precedence over larger numbers.

Distinguish between:

- `@Qualifier` selects the candidate set by characteristic.
- `@Order` sorts candidates in scenarios that support ordering.
- `@Primary` prioritizes one candidate for a single dependency.

`@Order` does not replace qualifiers and is not a command guaranteeing bean initialization order. If processing order affects business logic, express and test it explicitly.

## 14. Common mistakes when using qualifiers

### 14.1. No bean satisfies the qualifier

For example:

```java
public PaymentService(
        @Qualifier("card") PaymentGateway gateway
) {
    this.gateway = gateway;
}
```

If the context has no bean of type `PaymentGateway` carrying a matching qualifier or corresponding fallback bean name, Spring cannot resolve the dependency. Possible causes:

- The implementation is not registered.
- The bean is outside component scan and has not been imported/configured.
- The qualifier value is misspelled or has different metadata.
- The bean was excluded by `@Profile` or a condition.
- The implementation resides in a module missing from the classpath.

### 14.2. Multiple beans satisfy the qualifier at a single injection point

If both email and SMS senders carry the `external` qualifier, the injection point:

```java
@Qualifier("external") NotificationSender sender
```

can still be ambiguous because two candidates match. If you want both, inject `List<NotificationSender>`. If you want one bean, you need a more specific criterion such as `@Channel("email")`, or an appropriate default choice.

### 14.3. Qualifier on bean and injection point do not match

For example, the bean has `@Qualifier("external")` while the constructor requests `@Qualifier("remote")`. Without other matching metadata, the bean will not be selected. Do not confuse qualifier values with free-form descriptive names; they are criteria that must be consistent on both sides.

### 14.4. Using bean names instead of qualifier meaning everywhere

If services use `@Qualifier("smtpNotificationSender")`, renaming the class/bean can force changes in many places. If what the service needs is the "email channel," using a meaningful qualifier like `email` can be more stable than the implementation name.

### 14.5. Using qualifiers to mask a design lacking a proper contract

If multiple classes share a type but each has a different API, adding qualifiers does not make them interchangeable implementations. Design an appropriate interface first, then use qualifiers to classify beans that truly share the same role.

### 14.6. Mixing multiple selection mechanisms without understanding precedence

`@Primary`, qualifiers, bean names, and other metadata can all participate in dependency resolution. If many overlapping rules exist, code becomes hard to predict. Use direct criteria at the injection point and keep configuration consistent, avoiding reliance on fallback behavior when unnecessary.

## 15. How to investigate bean selection errors in Spring Boot

When an application fails to start because a dependency has multiple or zero candidates, read the error message in order:

1. **Which bean is being created?** Identify the failing service, controller, or configuration.
2. **Which dependency is being requested?** Read the type on the constructor/field/method parameter.
3. **Are there qualifiers at the injection point?** Note all qualifiers and their values.
4. **Which beans of the same type are registered?** Look for components, `@Bean` methods, imported configurations, and relevant auto-configurations.
5. **Does the bean metadata match?** Check qualifiers on the class or bean method.
6. **Is any profile/condition excluding the bean?** Check the environment and configuration conditions.
7. **Do multiple beans match?** Choose a specific qualifier, collection, or primary depending on actual needs.

Common error patterns:

| Symptom | Possible meaning | Investigation direction |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | No matching bean found | Check type, scan, import, qualifier, profile |
| `NoUniqueBeanDefinitionException` | Multiple matching beans for a single dependency | Check `@Primary`, qualifier, and bean name |
| `UnsatisfiedDependencyException` | Spring cannot supply a dependency for the bean being created | Read nested causes to find the root error |
| Empty collection | No bean satisfies type/qualifier in the context | Check bean registration and group metadata |
| Wrong implementation used | Another candidate was chosen by metadata/priority | Check qualifier, primary, bean name, and configuration |

Do not just add `@Primary` to make the application start without verifying that the implementation meets requirements. An application that starts successfully but uses the wrong payment gateway or notification system is still a functional bug.

## 16. Designing maintainable qualifiers

### 16.1. Use labels describing roles or characteristics

Names like `external`, `persistent`, `readOnly`, or `regional` generally express more stable meaning than class names. Qualifiers should help readers understand **why a service needs that bean**.

### 16.2. Avoid creating too many overlapping qualifiers

If an application has `remote`, `external`, and `thirdParty` without clear distinctions, developers will not know which label to use. Standardize vocabulary within a module and document when a qualifier represents a specific policy.

### 16.3. Choose custom annotations when metadata is reused repeatedly

If a qualifier has multiple dimensions, is used across multiple modules, or carries clear domain meaning, a custom annotation with attributes gives IDE refactoring support and reduces string errors.

### 16.4. Do not turn qualifiers into dynamic business configuration

Qualifiers are resolved at wiring time. If selection must depend on per-request data, build an injected factory, strategy resolver, or registry. Do not create multiple qualified beans and expect Spring to automatically swap beans for a singleton service per request.

### 16.5. Use qualifiers only when type alone is insufficient

If a type has only one bean, adding a qualifier adds little value. Qualifiers are useful when there are multiple implementations, multiple groups, or explicit selection is needed.

## 17. Practice exercises

### Exercise 1 – Selecting the right implementation

Given two beans `EmailNotificationSender` and `SmsNotificationSender` implementing `NotificationSender`:

1. Attach qualifiers `email` and `sms` to the two beans.
2. Create `RegistrationService` receiving the email bean via constructor.
3. Create `SecurityAlertService` receiving the SMS bean via constructor.
4. Explain why both services can use the same interface while receiving different implementations.

**Hint:** the type remains `NotificationSender`; the qualifier on each constructor narrows down candidates by purpose.

### Exercise 2 – Injecting a whole group

Create three `NotificationSender` beans:

- Email sender carrying qualifier `external`.
- SMS sender carrying qualifier `external`.
- Console sender carrying qualifier `local`.

Write `ExternalBroadcastService` accepting `@Qualifier("external") List<NotificationSender>` and invoke all senders in the list. Explain why sharing a qualifier does not cause an ambiguity error for a collection the way it does for single-bean injection.

### Exercise 3 – Creating custom qualifiers

Create two annotations `@Region` and `@Channel`, each having a `String value()` attribute and meta-annotated with `@Qualifier`. Register Asia/Europe beans for Email/SMS and inject specifically the Asia Email bean.

Try injecting `@Region("asia") List<NotificationSender>` and `@Channel("email") List<NotificationSender>` to observe how qualifiers filter groups.

### Exercise 4 – Distinguishing @Primary and @Qualifier

Mark the email sender as `@Primary`. Then:

- Inject `NotificationSender` without a qualifier.
- Inject `@Qualifier("sms") NotificationSender`.
- Inject `@Qualifier("external") List<NotificationSender>`.

Explain why the three injection points can receive different sets of beans.

### Exercise 5 – Per-request selection

A REST request has a `channel` field taking values `email` or `sms`. Design a service that can choose a sender at runtime using `Map<String, NotificationSender>` or a registry. Compare that design with putting a fixed `@Qualifier("email")` on the constructor.

**Hint:** a fixed qualifier is a wiring-time choice; a map/registry allows application logic to select based on runtime data.

## 18. Key takeaways about @Qualifier

`@Qualifier` is Spring's tool for **describing and filtering bean candidates during dependency resolution**. It is especially useful when multiple beans share the same type but differ in role, channel, region, environment, or characteristics.

Key principles:

- Spring checks type first, then uses qualifiers and bean selection rules to determine matching candidates.
- Bean name is an identifier in the container; qualifier is candidate-filtering metadata. A qualifier value may match a bean name as a fallback, but the two concepts should not be conflated.
- `@Primary` designates a preferred default candidate; `@Qualifier` expresses specific criteria at the injection point.
- The same qualifier can be attached to multiple beans to form a group; inject `List<T>` or `Set<T>` when the entire group is needed.
- Custom qualifier annotations help express multidimensional metadata and avoid relying on scattered strings.
- Qualifiers do not register beans, add dependencies to the classpath, or replace profiles/conditions.
- Qualifiers solve wiring; implementation selection based on runtime data requires an appropriate factory, strategy, or registry.

When encountering multiple beans of the same type, ask: **does the service need a default bean, a specific implementation, or an entire group of beans?** The answer will guide you between `@Primary`, a single-target `@Qualifier`, a custom qualifier, or collection injection. This organizes dependencies cleanly, making the Spring context easier to understand and the Spring Boot application easier to scale.
