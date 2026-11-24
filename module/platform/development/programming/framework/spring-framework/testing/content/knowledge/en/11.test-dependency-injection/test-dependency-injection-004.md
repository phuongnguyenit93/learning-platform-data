# @Qualifier When Multiple Beans Share the Same Type

In a Spring application, multiple beans may implement the same interface or share the same class type. For example, a notification application might have `EmailSender` and `SmsSender` both implementing `MessageSender`; an application might have multiple `PaymentGateway` beans for different providers; or multiple `DataSource` beans for separate databases.

When Spring injects a dependency by type, selecting a bean is usually straightforward if only one matching bean exists. However, if multiple beans share the same type, Spring needs additional information to determine the right candidate. **@Qualifier** provides that information at the injection point. It narrows down the set of beans using a meaningful label, such as `email`, `sms`, `primary-database`, or `external-payment`.

In Spring testing, `@Qualifier` has two common roles:

- Selecting the right bean when a test needs to inject one of several beans of the same type.
- Verifying that the application configuration actually wires the right collaborator into the system under test (SUT).

Merely putting `@Qualifier` on a field of the test class is not enough to prove that the service is using the right bean. If the goal is to test wiring, the qualifier must be applied at the injection point of the SUT itself, and the test must observe behavior through the SUT.

## 1. Why do multiple beans of the same type cause ambiguity?

Suppose the application has an interface:

~~~java
public interface MessageSender {
    void send(String recipient, String message);
}
~~~

Two implementations:

~~~java
@Component
class EmailSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Send email via mail provider.
    }
}

@Component
class SmsSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Send SMS via SMS provider.
    }
}
~~~

A service that needs to send emails:

~~~java
@Service
class AccountNotificationService {
    private final MessageSender sender;

    AccountNotificationService(MessageSender sender) {
        this.sender = sender;
    }
}
~~~

If component scanning discovers both `EmailSender` and `SmsSender`, Spring sees two candidates matching the `MessageSender` type. The constructor provides no additional information to choose a specific implementation. Without a priority rule or another qualifier, bean creation can fail with `NoUniqueBeanDefinitionException`.

This is a wiring error that occurs when Spring creates the `ApplicationContext`. It is not an error discovered only when the service calls `send`. Therefore, if the test objective is to verify dependency injection configuration, the test must initialize a context containing the relevant beans and let Spring perform candidate selection.

## 2. @Qualifier resolves bean selection

You can attach a qualifier to both the bean definition and the injection point:

~~~java
@Component
@Qualifier("email")
class EmailSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Send email.
    }
}

@Component
@Qualifier("sms")
class SmsSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        // Send SMS.
    }
}
~~~

The service declares the qualifier it needs:

~~~java
@Service
class AccountNotificationService {
    private final MessageSender sender;

    AccountNotificationService(
            @Qualifier("email") MessageSender sender) {
        this.sender = sender;
    }
}
~~~

Spring first finds beans matching the dependency type, then uses the qualifier to narrow the candidate set. In this example, only `EmailSender` has the `email` qualifier, so it is injected into the constructor.

### 2.1. Where can @Qualifier be placed?

Qualifiers can appear in several locations depending on how beans are registered:

| Location | Example | Meaning |
| --- | --- | --- |
| Component class | `@Component` combined with `@Qualifier` | Attaches qualifier metadata to a bean discovered via component scan |
| `@Bean` method | `@Bean` combined with `@Qualifier` | Attaches qualifier metadata to a bean created via Java configuration |
| Constructor parameter | `@Qualifier` on parameter | Explicitly specifies the candidate to inject into the parameter |
| Field injection point | `@Autowired` and `@Qualifier` | Selects the bean for the field |
| Setter or method parameter | `@Qualifier` on parameter | Selects the bean for the corresponding injection point |
| Test field | `@Autowired` and `@Qualifier` | Selects the bean the test class wants to receive |

For new code, constructor injection is generally easier to read and test than field injection. Placing the qualifier on a constructor parameter makes both the required dependency and the implementation choice explicit right at object creation.

### 2.2. Using Java configuration with @Bean

You do not have to use component scanning to register multiple implementations. You can declare them explicitly:

~~~java
@Configuration
class MessageSenderConfiguration {

    @Bean
    @Qualifier("email")
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    @Qualifier("sms")
    MessageSender smsSender() {
        return new SmsSender();
    }
}
~~~

The qualifier on a `@Bean` method is attached to the corresponding bean definition. An injection point can select the bean by that qualifier:

~~~java
@Bean
AccountNotificationService accountNotificationService(
        @Qualifier("email") MessageSender sender) {
    return new AccountNotificationService(sender);
}
~~~

With Java configuration, the `@Bean` method name is also the default bean name if no other name is declared. For example, `emailSender` is the bean name; `email` is the qualifier metadata. The two concepts can share the same value, but they are not synonymous.

## 3. How does @Qualifier differ from @Primary?

`@Primary` marks a bean to be preferred when Spring needs to choose one candidate for a single-valued dependency and multiple beans share the same type. `@Qualifier` narrows the candidate set based on metadata at the injection point.

Example:

~~~java
@Configuration
class SenderConfiguration {

    @Bean
    @Primary
    MessageSender emailSender() {
        return new EmailSender();
    }

    @Bean
    MessageSender smsSender() {
        return new SmsSender();
    }
}
~~~

With injection that has no qualifier:

~~~java
AccountNotificationService(MessageSender sender) {
    this.sender = sender;
}
~~~

`EmailSender` is preferred because it has `@Primary`.

If the injection point specifies:

~~~java
AccountNotificationService(
        @Qualifier("sms") MessageSender sender) {
    this.sender = sender;
}
~~~

Spring selects the bean matching the `sms` qualifier. `@Primary` on `EmailSender` does not make `EmailSender` override a non-matching qualifier.

| Criterion | @Qualifier | @Primary |
| --- | --- | --- |
| Purpose | Narrow candidates by label | Mark the preferred default candidate |
| Selection scope | Tied to the injection point and bean metadata | Tied to the bean definition |
| When multiple candidates exist | Selects the group of beans matching the qualifier | Prefers the primary bean when a single bean is needed |
| Can be used together? | Yes | Yes |
| Collection injection | Can filter a collection by qualifier | Does not exclude non-primary beans from collections |

Do not use `@Primary` to mask a dependency that actually needs clear business differentiation. If a service specifically needs email, declaring the `email` qualifier communicates the intent better than a global default choice.

## 4. A qualifier is not just a bean name

A common misconception is viewing `@Qualifier("emailSender")` as just another way to reference a bean name. Spring can use the bean name as a fallback when matching qualifiers, but a qualifier's primary purpose is to serve as a semantic label for filtering candidates.

For example, you can declare a bean name different from its qualifier:

~~~java
@Bean("smtpClient")
@Qualifier("email")
MessageSender outboundEmailSender() {
    return new EmailSender();
}
~~~

Injection point:

~~~java
NotificationService(@Qualifier("email") MessageSender sender) {
    // ...
}
~~~

Here:

- The bean name is `smtpClient`.
- The qualifier value is `email`.
- The dependency requires a `MessageSender` carrying the `email` qualifier.

Naming qualifiers by role or purpose usually makes configuration easier to understand. For instance, a system may have several email-sending beans of different kinds: `transactional`, `marketing`, or `audit`. Using a `transactional` qualifier describes the bean's role better than an implementation class name.

### 4.1. When to use @Resource?

`@Resource` is typically used when you want to inject a resource by a specific name. `@Qualifier` combined with `@Autowired` still starts from the dependency type and then uses the qualifier to filter candidates.

| Scenario | Usually appropriate choice |
| --- | --- |
| Select an implementation by role/semantics | `@Autowired` combined with `@Qualifier` |
| Select an exact resource by name | `@Resource(name = "...")` |
| Select a default bean among multiple implementations | `@Primary` |
| Inject all matching implementations | `List`, `Set`, array, or `Map` by type |

Do not choose annotations purely out of habit. Express clearly whether a dependency needs a bean by role, by name, or by a default rule.

## 5. Multiple qualifiers and custom qualifiers

A dependency sometimes needs multiple attributes to be distinguished. For example, a system may have several `PaymentGateway` beans and need to choose the gateway serving the `external` role in the `eu` region.

You can apply multiple qualifier metadata annotations:

~~~java
@Bean
@Qualifier("external")
@Region("eu")
PaymentGateway europeanExternalGateway() {
    return new EuropeanPaymentGateway();
}
~~~

The injection point requires the matching metadata:

~~~java
PaymentService(
        @Qualifier("external") @Region("eu")
        PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Qualifiers are combined to narrow candidates. The bean must satisfy all qualifier conditions requested by the injection point.

### 5.1. Creating a custom qualifier annotation

If a label is used in many places, you can create a dedicated annotation meta-annotated with `@Qualifier`.

~~~java
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.METHOD,
    ElementType.TYPE,
    ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Region {
    String value();
}
~~~

Registering beans:

~~~java
@Bean
@Region("eu")
PaymentGateway europeanGateway() {
    return new EuropeanPaymentGateway();
}

@Bean
@Region("us")
PaymentGateway americanGateway() {
    return new AmericanPaymentGateway();
}
~~~

Injecting a bean:

~~~java
PaymentService(@Region("eu") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom qualifiers help code express domain language and avoid scattering arbitrary strings across many places. If the annotation has multiple attributes, Spring can use those attributes during qualifier matching.

Do not create a custom qualifier for every single bean. A new annotation is only useful when it represents a stable and meaningful classification in the configuration.

## 6. @Qualifier with collection injection

When injecting a `List` or `Set` of a type, Spring normally provides all beans matching that type. `@Qualifier` at the injection point can filter the collection by qualifier.

Example:

~~~java
@Component
@Qualifier("internal")
class InternalPaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("external")
class StripePaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("external")
class AdyenPaymentGateway implements PaymentGateway {
    // ...
}
~~~

A service receiving all external gateways:

~~~java
class ExternalPaymentRouter {
    private final List<PaymentGateway> gateways;

    ExternalPaymentRouter(
            @Qualifier("external") List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }
}
~~~

The list contains only beans carrying the `external` qualifier. This is an important difference from `@Primary`: `@Primary` does not mean non-primary beans are excluded from collection injection.

Spring also supports injecting a `Map` where the key is the bean name and the value is the bean instance:

~~~java
class PaymentGatewayRegistry {
    private final Map<String, PaymentGateway> gateways;

    PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }
}
~~~

In this case, the `Map` represents beans keyed by name. If filtering by a qualifier group is needed, you can place a qualifier on the appropriate collection injection point.

## 7. Qualifiers and generic types

Generic types can also help Spring distinguish certain dependencies. For example:

~~~java
interface Store<T> {
    void save(T value);
}

class StringStore implements Store<String> {
    public void save(String value) {
    }
}

class IntegerStore implements Store<Integer> {
    public void save(Integer value) {
    }
}
~~~

An injection point for `Store<String>` can be distinguished from `Store<Integer>` thanks to generic type metadata. If multiple `Store<String>` beans coexist, a qualifier may still be necessary to specify the desired role or implementation.

Do not rely on class names or bean registration order to select an implementation. Declare types and qualifiers clearly enough so configuration does not depend on scan order or file order.

## 8. Testing @Qualifier with Spring TestContext

Qualifier tests should verify that Spring actually creates the beans and selects the right candidate. You can use `@SpringJUnitConfig` to load a small context without starting the entire application.

### 8.1. Creating a test configuration with two beans of the same type

Suppose there is a service:

~~~java
class NotificationService {
    private final MessageSender sender;

    NotificationService(
            @Qualifier("email") MessageSender sender) {
        this.sender = sender;
    }

    void notify(String recipient, String message) {
        sender.send(recipient, message);
    }
}
~~~

Test configuration:

~~~java
@Configuration
class NotificationTestConfiguration {

    @Bean
    @Qualifier("email")
    MessageSender emailSender() {
        return Mockito.mock(MessageSender.class);
    }

    @Bean
    @Qualifier("sms")
    MessageSender smsSender() {
        return Mockito.mock(MessageSender.class);
    }

    @Bean
    NotificationService notificationService(
            @Qualifier("email") MessageSender sender) {
        return new NotificationService(sender);
    }
}
~~~

Here, two beans of the same type `MessageSender` are registered in the same `ApplicationContext`. The `NotificationService` constructor requires the `email` qualifier. Spring must select the right bean when creating `NotificationService`.

### 8.2. Verifying the bean injected into the SUT

~~~java
@SpringJUnitConfig(NotificationTestConfiguration.class)
class NotificationQualifierTest {

    @Autowired
    NotificationService notificationService;

    @Autowired
    @Qualifier("email")
    MessageSender emailSender;

    @Autowired
    @Qualifier("sms")
    MessageSender smsSender;

    @Test
    void injects_email_sender_into_notification_service() {
        notificationService.notify("user@example.com", "Welcome");

        Mockito.verify(emailSender)
            .send("user@example.com", "Welcome");
        Mockito.verifyNoInteractions(smsSender);
    }
}
~~~

This test verifies both layers:

1. `@Qualifier` on the test fields injects `emailSender` and `smsSender` individually so the test can observe them.
2. `@Qualifier` on the `NotificationService` constructor determines which bean is injected into the SUT.

If you only write:

~~~java
@Autowired
@Qualifier("email")
MessageSender emailSender;
~~~

then the test only proves that the test class received the `email` bean. It does not prove that another service is also wired to the `email` bean. To test service wiring, you must inject the actual service and invoke its behavior as in the example above.

### 8.3. Testing ambiguity when a qualifier is missing

You can write a minimal configuration test to verify that two beans of the same type cause a failure if a single-valued dependency has neither a qualifier nor `@Primary`. However, testing context initialization exceptions should be done deliberately because context failures typically occur before test methods run.

In most suites, a configuration test succeeding with the right qualifier already proves the required wiring. If you want to guard the fail-fast behavior of the configuration, use a separate context or an `ApplicationContextRunner` in the Spring Boot ecosystem to confirm the context fails to start when candidates are ambiguous.

Do not break the main test suite by intentionally registering a failing context in a shared configuration.

## 9. Testing @Qualifier in Spring Boot

With a Spring Boot application, you can use `@SpringBootTest` when you want to verify bean wiring in the full application context:

~~~java
@SpringBootTest
class NotificationServiceIntegrationTest {

    @Autowired
    NotificationService notificationService;

    @Autowired
    @Qualifier("email")
    MessageSender emailSender;

    @Test
    void uses_email_sender_for_account_notifications() {
        notificationService.notify("user@example.com", "Welcome");

        // Assertion matching the implementation or test adapter.
    }
}
~~~

If the email sender calls an external system, do not send real emails just to test the qualifier. Replace the external adapter with a mock, fake, or simulated server, while keeping the bean wiring of `NotificationService` and the injection point under test intact.

In Spring Boot Test, `@MockBean` can replace a bean in the `ApplicationContext` with a Mockito mock. When multiple beans share the same type, clearly specify the bean to replace by name or qualifier appropriate to the version in use. The crucial point is that the replaced bean must be the exact collaborator the SUT receives; replacing a different implementation by mistake may prevent the test from controlling the desired behavior.

### 9.1. Do not let @Primary hide qualifier errors

Suppose a production service has a constructor requiring `@Qualifier("email")`. If the test configuration only registers a `@Primary` bean without registering the `email` qualifier, the test no longer verifies the original bean selection contract.

When the goal is to test `@Qualifier`, the test should preserve the same qualifier metadata as the application configuration or create test beans with the corresponding qualifiers. Do not add `@Primary` merely to make the context start if it masks an incorrect qualifier configuration.

### 9.2. Using @TestConfiguration to add test beans

Spring Boot lets you declare test-specific configuration using `@TestConfiguration`. You can use it to provide a fake adapter or a bean with an explicit qualifier:

~~~java
@TestConfiguration
class NotificationAdapterTestConfiguration {

    @Bean
    @Primary
    @Qualifier("email")
    MessageSender testEmailSender() {
        return new RecordingMessageSender();
    }
}
~~~

The example above illustrates how to declare a test bean. If the context already has a bean with the same name or qualifier, choose a replacement strategy compatible with the application configuration and active bean overriding settings. Do not rely on `@Primary` to bypass ambiguity if the goal is to test the qualifier itself.

## 10. Troubleshooting common errors

### NoUniqueBeanDefinitionException

This error occurs when Spring finds multiple matching beans for a single-valued dependency without a qualifier, `@Primary`, or other resolution rule to pick a single candidate.

How to resolve:

- Identify the beans of the same type in the context.
- Inspect the SUT's injection point.
- Add a meaningful qualifier to the bean definition and injection point if the business logic requires a specific implementation.
- Use `@Primary` if there genuinely is a sensible default implementation.
- If all implementations are needed, inject a collection instead of a single bean.

### NoSuchBeanDefinitionException

This error can appear when no bean matches the required type or qualifier. Check:

- Has the bean been registered?
- Does the qualifier value match the metadata?
- Is the bean excluded by a profile or condition?
- Did the test context load the right configuration class?
- Did a bean override in the test replace the right bean?

### Qualifier placed on the wrong side

Putting `@Qualifier` only on a test class field does not change how Spring injects dependencies into the service. The qualifier must appear on the SUT's constructor, field, or method parameter if the goal is to select a collaborator for the SUT.

### Confusing qualifier with bean name

A bean can have the bean name `smtpClient` and the qualifier `email`. Check the metadata and injection point instead of looking solely at the `@Bean` method name.

### Using @Primary when multiple beans are needed

`@Primary` only prioritizes a candidate for a single-valued dependency. If a service needs a list of implementations, inject a `List` or `Map` and use qualifiers to filter when appropriate.

### Test uses a mock yet SUT still calls the real implementation

The test may have mocked a bean of the same type, but not the bean selected by the qualifier. Determine the collaborator's bean name and qualifier, then verify that the mock actually receives the call from the SUT.

### Component scan creates unexpected extra beans

The test context may scan unnecessary implementations. Narrow component scanning, import configurations explicitly, or use an appropriate profile. Do not delete a bean just to make a test pass if that bean must exist in production.

## 11. Design considerations

### 11.1. Use role-based qualifiers

Qualifier names should represent roles, purposes, or configuration groups:

- `email`, `sms`.
- `primary-database`, `audit-database`.
- `external-payment`, `internal-payment`.
- `eu`, `us`.
- `transactional`, `marketing`.

Avoid names tied too tightly to a class or vendor when the role is what the application actually cares about. When an implementation changes, a role-based qualifier can remain stable.

### 11.2. Avoid redundant, meaningless qualifiers

If there is only one bean of that type in the entire context and no need for role-based selection, a qualifier may be unnecessary. Adding annotations to every dependency makes configuration verbose and increases maintenance overhead.

### 11.3. Do not rely on bean registration order

Do not use component scan order, `@Bean` method order, or classpath order to decide which implementation gets injected. Use qualifiers, `@Primary`, or collections with explicit ordering rules if order matters.

### 11.4. Split responsibilities instead of adding too many qualifiers

If an interface has dozens of implementations and every service must select via complex combinations of qualifiers, the abstraction may be too broad. Consider splitting the interface by capability or using a registry/router with clear responsibilities.

A qualifier is a bean selection tool, not a substitute for domain design.

## 12. Workflow for testing wiring with @Qualifier

You can apply the following workflow:

**Step 1 – List beans of the same type.** Identify interfaces or classes with multiple implementations in the context.

**Step 2 – Identify the SUT's role.** Clarify which implementation the SUT needs and why.

**Step 3 – Attach qualifier metadata.** Place qualifiers on bean definitions or custom qualifier annotations according to role.

**Step 4 – Place the qualifier at the SUT's injection point.** Prefer constructor parameters so dependencies are explicit.

**Step 5 – Create the test context.** Use `@SpringJUnitConfig` for a small context or `@SpringBootTest` when a full application context is needed.

**Step 6 – Inject candidates into the test when observation is needed.** Use `@Autowired` with `@Qualifier` to receive the exact beans the test needs to verify.

**Step 7 – Invoke behavior through the SUT.** Do not merely check that the test class can inject a bean.

**Step 8 – Verify the right collaborator was used.** Use a recording fake, observable output, or Mockito verification at an appropriate boundary.

**Step 9 – Test error configurations if needed.** Verify that ambiguity or a mismatched qualifier makes the context fail as expected in a separate test context.

**Step 10 – Ensure tests do not call external systems.** Replace external adapters with mocks/fakes or simulated servers while preserving the bean wiring under test.

## 13. Quick decision table

| Need | Choice |
| --- | --- |
| Single bean of that type | Injection by type is usually sufficient |
| Multiple beans, need one specific implementation | `@Qualifier` at the injection point |
| One default implementation for a single-valued dependency | `@Primary` |
| Need all implementations | Inject `List`, `Set`, or `Map` |
| Need to filter a group of beans in a collection | `@Qualifier` on the collection injection point |
| Need to distinguish by multiple stable attributes | Multiple qualifiers or custom qualifier |
| Test wants to inject each bean individually to observe | `@Autowired` with `@Qualifier` on test field/parameter |
| Test wants to prove SUT receives the right bean | Qualifier on the SUT's injection point and invoke through the SUT |
| Test wants to replace an external collaborator | Mock/fake the exact bean selected by the qualifier |

## Conclusion

`@Qualifier` helps Spring choose the right bean when multiple candidates share the same type by narrowing the bean set using meaningful metadata. It can be declared on components, `@Bean` methods, and injection points; custom qualifiers help express stable classification attributes. `@Primary` is suitable for selecting a default bean for a single-valued dependency, whereas `@Qualifier` clearly expresses which role a dependency requires. When injecting collections, qualifiers can filter the required group of beans.

In Spring Testing, distinguish which bean the test class receives from which bean is actually injected into the SUT. Create a context containing real candidates, place the qualifier on the SUT's constructor or injection point, invoke behavior through the SUT, and observe which collaborator is used. This testing approach protects dependency injection configuration without relying on class names, bean registration order, or a misplaced mock.
