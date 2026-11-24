# Selecting Candidates by Type and Handling Multiple Matching Beans

In Spring, you often declare a dependency using a Java type and let the container inject the matching implementation:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

This works simply when there is only one bean matching the **PaymentGateway** type in the ApplicationContext. However, a real-world application may integrate multiple payment gateways: domestic payments, international cards, e-wallets, or a fake implementation used in testing. When multiple beans satisfy the same dependency type, Spring needs to determine which bean gets injected.

This topic explains how Spring **finds candidates by type**, how to narrow down and select candidates using **@Qualifier** and **@Primary**, how to inject multiple implementations at once, and how to troubleshoot errors when there are no matching beans or too many matching beans.

## 1. How does Spring find beans by type?

Suppose there is an interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
~~~

And an implementation:

~~~java
@Component
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Call the bank transfer service.
        return PaymentResult.accepted();
    }
}
~~~

When a constructor requires **PaymentGateway**, Spring looks for a bean whose type is compatible with that type. The **BankTransferGateway** bean can be used because it implements the **PaymentGateway** interface.

~~~text
Injection point:
PaymentGateway
       │
       ▼
Spring searches for beans with a compatible type
       │
       ▼
BankTransferGateway implements PaymentGateway
       │
       ▼
Inject bean into constructor
~~~

This is **type-based dependency injection**. The service code depends on an abstraction, while the container decides the concrete implementation based on the registered beans and their associated metadata.

### The bean must be present in the ApplicationContext

A class implementing an interface does not automatically become a bean just because the Java type relationship exists. It must be registered through an appropriate mechanism, for example:

- Component scanning with **@Component**, **@Service**, **@Repository**, or a corresponding stereotype.
- A **@Bean** factory method in a **@Configuration** class.
- Auto-configuration or another bean registration mechanism.

If the implementation is not yet on the runtime classpath, has not been scanned, is not declared, or is excluded by configuration conditions, Spring cannot inject it.

### An example with two candidates

~~~java
@Component
public class CardPaymentGateway implements PaymentGateway {
    // Handle card payment.
}

@Component
public class BankTransferGateway implements PaymentGateway {
    // Handle bank transfer.
}
~~~

At this point, both beans match a dependency of type **PaymentGateway**. If the service still declares:

~~~java
public CheckoutService(PaymentGateway paymentGateway) {
    this.paymentGateway = paymentGateway;
}
~~~

Spring cannot automatically infer whether the application wants to use card or bank transfer. Without appropriate metadata or selection rules, bean instantiation can fail with a **NoUniqueBeanDefinitionException** error (often displayed with the message *expected single matching bean but found 2*).

## 2. Type matching rules and generic types

Spring finds candidates based on the type of the injection point and the type declared by the bean. Inheritance/interface relationships are taken into account; a bean of a class implementing an interface can satisfy a dependency declared with that interface.

For example:

~~~java
public interface MessageSender {
    void send(String message);
}

@Component
public class EmailSender implements MessageSender {
    public void send(String message) {
        // Send email.
    }
}
~~~

A dependency of type **MessageSender** can receive the **EmailSender** bean. Conversely, a dependency of type **EmailSender** requires a concrete bean compatible with **EmailSender**; another implementation of **MessageSender** does not satisfy it just because it implements the same interface.

### Generic types can also help distinguish candidates

Spring can use generic information retained in bean declarations and injection points to narrow down candidates:

~~~java
public interface Store<T> {
    void save(T value);
}
~~~

Two implementations:

~~~java
@Component
public class StringStore implements Store<String> {

    public void save(String value) {
        // Save string.
    }
}

@Component
public class IntegerStore implements Store<Integer> {

    public void save(Integer value) {
        // Save integer.
    }
}
~~~

Injection point:

~~~java
@Service
public class TextImportService {

    private final Store<String> store;

    public TextImportService(Store<String> store) {
        this.store = store;
    }
}
~~~

In cases where Spring preserves generic metadata as shown above, **Store<String>** can be distinguished from **Store<Integer>**. This is a useful way to reuse the same abstraction across multiple data types.

However, if you use a raw type:

~~~java
private final Store store;
~~~

the generic information no longer helps distinguish candidates as clearly as before. When multiple compatible implementations exist, you may run into ambiguity again. You should declare the full generic type at the injection point and avoid raw types unless there is a special reason.

**Note:** generic matching depends on the type metadata that Spring can infer from bean definitions and classes. Factory methods returning raw types or complex generic structures may lose the information you expect; declare concrete, easily inferable return types.

## 3. @Primary: marking a preferred candidate

When a type has multiple implementations but most of the application should use one default implementation, you can mark that bean with **@Primary**.

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Handle card payment.
        return PaymentResult.accepted();
    }
}

@Component
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Handle bank transfer.
        return PaymentResult.accepted();
    }
}
~~~

The service does not need to know the implementation's name:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

When Spring needs to inject **a single PaymentGateway bean**, **CardPaymentGateway** is selected as the primary candidate among the matching candidates.

### @Primary does not remove the remaining beans

**BankTransferGateway** remains a bean in the ApplicationContext. It can still be injected using a qualifier, retrieved through a provider, or appear in collection injection.

You can visualize it as:

~~~text
PaymentGateway candidates
    ├── CardPaymentGateway       @Primary  ← selected by default for a single dependency
    └── BankTransferGateway                ← still exists
~~~

**@Primary** is priority metadata when choosing one candidate for a single dependency. It does not mean only one implementation remains active in the application.

### Where to place @Primary?

You can mark the component class:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
}
~~~

Or mark the **@Bean** method:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway defaultPaymentGateway() {
        return new CardPaymentGateway();
    }
}
~~~

You should not simultaneously register the same implementation via component scanning and another factory method if doing so creates two unintended beans. Establish one clear registration mechanism for each bean.

### What if there are multiple @Primary beans?

If multiple candidates are marked **@Primary** for the same type and injection point, Spring still does not have a unique primary candidate to choose. The result may be an error failing to determine a matching bean. Each single dependency needs a clear selection rule.

## 4. @Qualifier: specifying a matching bean group

**@Qualifier** helps narrow down the set of candidates by a label. For example, instead of always using the primary payment gateway, a service dedicated to handling bank transfers can specify a qualifier:

~~~java
@Component
@Qualifier("bankTransfer")
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        return PaymentResult.accepted();
    }
}
~~~

At the injection point:

~~~java
@Service
public class BankPayoutService {

    private final PaymentGateway paymentGateway;

    public BankPayoutService(
            @Qualifier("bankTransfer")
            PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

Spring first finds beans compatible with **PaymentGateway**, then uses the qualifier to pick the candidate with matching metadata. If the qualifier matches no bean, the dependency cannot be resolved.

### A qualifier does not have to be a bean name

The value in **@Qualifier("bankTransfer")** is generally understood as a qualifier label. It may match a bean name, but its primary meaning is a **label used to filter candidates**, not a requirement that the class have that exact name.

For example, you can use a qualifier based on environment or role:

~~~java
@Component
@Qualifier("external")
public class ExternalPaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("sandbox")
public class SandboxPaymentGateway implements PaymentGateway {
    // ...
}
~~~

A service can request **@Qualifier("sandbox")** without needing to know the concrete class name. This makes the intent of the injection point easier to read.

### Can @Qualifier be combined with @Primary?

**@Qualifier** filters the group of candidates by label; **@Primary** marks the preferred candidate within the remaining group when one bean needs to be chosen. Therefore, a qualifier can be used to select an implementation other than the default primary bean.

For example:

~~~java
@Component
@Primary
@Qualifier("card")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component
@Qualifier("bank")
public class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

A dependency without a qualifier prefers **CardPaymentGateway**. A dependency requesting **@Qualifier("bank")** selects **BankTransferGateway** if it is the only matching candidate for that qualifier.

### Can multiple qualifiers be used?

Qualifiers can be used to filter across multiple criteria when appropriate metadata is designed. For example, an application may want to choose an implementation that both belongs to the **external** group and supports the **vn** region. Spring supports custom qualifier annotations with attributes to express such metadata.

## 5. Creating custom qualifiers to avoid hard-to-manage strings

When an application has many integrations, strings like **"bankTransfer"**, **"sandbox"**, and **"production"** can be repeated in many places. You can define your own qualifier annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.beans.factory.annotation.Qualifier;

@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.TYPE,
    ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface BankPayment {
}
~~~

Mark the implementation:

~~~java
@Component
@BankPayment
public class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

And use it at the injection point:

~~~java
@Service
public class BankPayoutService {

    private final PaymentGateway gateway;

    public BankPayoutService(@BankPayment PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Custom qualifiers turn a technical label into a meaningful name within the integration domain. They also give IDEs better navigation and refactoring support compared to string literals.

### Qualifiers with attributes

When multiple dimensions of metadata are needed, you can define a qualifier annotation with attributes:

~~~java
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.TYPE,
    ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface PaymentRegion {
    String value();
}
~~~

Implementation:

~~~java
@Component
@PaymentRegion("VN")
public class VietnamPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Injection:

~~~java
public BankPayoutService(
        @PaymentRegion("VN") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Spring can use qualifier attributes to match metadata. When there are multiple criteria, you can combine qualifiers or design a dedicated annotation for a specific role.

## 6. Bean name and qualifier: do not confuse the two concepts

A bean usually has a name. With component scanning, the default name is typically generated from the class name according to bean naming rules; with **@Bean**, the default name is typically the factory method name.

For example:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankGateway() {
        return new BankTransferGateway();
    }
}
~~~

Here the bean names are **cardGateway** and **bankGateway**, respectively. You can use:

~~~java
public BankPayoutService(
        @Qualifier("bankGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Spring supports bean names as qualifier values when filtering candidates. However, in design, you should treat **bean name** as the bean's identity in the container, and **qualifier** as metadata expressing the kind/group of bean suitable for a dependency. The two values may coincide, but they do not have to.

If you change a bean name for structural reasons, a role-based qualifier can remain unchanged. This helps reduce business logic's coupling to factory method names or class names.

### How do @Autowired and @Resource differ?

Spring's **@Autowired** primarily resolves dependencies by type, and can then use qualifiers and metadata to select a candidate.

**@Resource** (from Jakarta Annotations) generally expresses looking up a dependency by name first; when needed, it can also use type to resolve according to the annotation's and environment's rules.

You should not choose **@Resource** merely to avoid multiple-bean errors without clarifying your intent. If the goal is "I need an implementation belonging to the bank group," **@Qualifier** or a custom qualifier usually expresses this better. If the goal is "I need a bean with a specific name," name-based injection may be appropriate, though it creates a direct coupling to the bean name.

## 7. Injecting multiple beans of the same type: List, Set, and Map

An application does not always want to select a single implementation. There are cases where you need to invoke **all** matching implementations.

For example, an application has multiple validators for an order:

~~~java
public interface OrderRule {
    void validate(Order order);
}
~~~

Implementations:

~~~java
@Component
public class StockRule implements OrderRule {
    public void validate(Order order) {
        // Check inventory.
    }
}

@Component
public class CreditRule implements OrderRule {
    public void validate(Order order) {
        // Check credit limit.
    }
}

@Component
public class AddressRule implements OrderRule {
    public void validate(Order order) {
        // Check shipping address.
    }
}
~~~

Service receiving a collection:

~~~java
@Service
public class OrderValidationService {

    private final List<OrderRule> rules;

    public OrderValidationService(List<OrderRule> rules) {
        this.rules = rules;
    }

    public void validate(Order order) {
        for (OrderRule rule : rules) {
            rule.validate(order);
        }
    }
}
~~~

Spring can inject all matching beans into **List<OrderRule>**. This solves the multiple-implementation problem by **collecting them**, rather than picking a single candidate.

### Collection injection and @Primary

An important point: **@Primary** primarily decides the candidate for a single dependency. When injecting **List<OrderRule>**, Spring still provides the collection of matching beans rather than putting only the primary bean into the list.

~~~text
List<OrderRule>
    ├── StockRule
    ├── CreditRule
    └── AddressRule
~~~

If collection injection has a qualifier, the qualifier can filter the collection down to the group of beans carrying the matching metadata.

### Collection ordering and @Order

If the execution order of rules matters, you can use **@Order**:

~~~java
@Component
@Order(10)
public class StockRule implements OrderRule {
    // ...
}

@Component
@Order(20)
public class CreditRule implements OrderRule {
    // ...
}
~~~

With ordered collection injection such as **List**, Spring can sort according to order metadata. Smaller order values have higher sorting priority. If business order is mandatory, express it explicitly and test it; do not rely on the accidental order of component scanning.

**@Order is not a way to select a single bean for a constructor parameter.** It primarily affects the ordering of collections/ordered streams. If you need a specific bean for a single dependency, use **@Primary**, **@Qualifier**, or another explicit selection rule.

### Injecting Map<String, T>

Spring can also inject a map where the key is the bean name and the value is the corresponding bean:

~~~java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentResult pay(
            String gatewayName,
            PaymentCommand command) {
        PaymentGateway gateway = gateways.get(gatewayName);

        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unsupported gateway: " + gatewayName);
        }

        return gateway.charge(command);
    }
}
~~~

This map makes selecting by bean name explicit. However, taking a gateway name from a user request and accessing the map directly can pose risks if the allowed list is not controlled. The application should map external input to a valid enum/identifier and check permissions before selecting an adapter.

## 8. ObjectProvider when you want to select a bean at the time it is needed

When an application does not want to inject a single bean directly and wants to defer retrieving the bean, Spring provides **ObjectProvider<T>**:

~~~java
@Service
public class OptionalReportService {

    private final ObjectProvider<ReportExporter> exporters;

    public OptionalReportService(
            ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void export(Report report) {
        ReportExporter exporter = exporters.getIfAvailable();
        if (exporter == null) {
            throw new IllegalStateException(
                    "Report exporter is not configured");
        }

        exporter.export(report);
    }
}
~~~

Some notable methods:

| API | Meaning |
|---|---|
| **getObject()** | Retrieves the bean; fails if a unique dependency cannot be resolved |
| **getIfAvailable()** | Returns the bean if present; returns null if absent; if multiple candidates cannot be uniquely selected, an error can still occur |
| **getIfUnique()** | Returns the bean if there is a unique candidate or one can be uniquely selected; returns null if absent or not uniquely determinable |
| **ifAvailable(Consumer)** | Executes the callback when a matching bean is available |
| **orderedStream()** | Retrieves matching beans as a stream taking order into account |

**ObjectProvider does not resolve ambiguity by guessing.** It provides an API for the application to decide when to retrieve the bean and how to handle absence/non-uniqueness.

If you need multiple implementations, you can use **orderedStream()** or collection injection. If you need a specific implementation by role, a qualifier is usually clearer.

## 9. No bean and multiple beans are two different errors

These two situations are often lumped together as "Spring failed to inject," but their causes are different.

### No matching bean

~~~text
Injection point: PaymentGateway
Candidates:      (none)
Result:          required dependency cannot be resolved
~~~

The message is usually related to **NoSuchBeanDefinitionException** or an enclosing bean creation error, for example:

~~~text
No qualifying bean of type 'PaymentGateway' available
~~~

Common causes:

- No implementation exists yet.
- The implementation has not been annotated with a stereotype or registered with **@Bean**.
- The implementation's package is outside component scan.
- The module/JAR containing the implementation is not on the runtime classpath.
- The bean is excluded by **@Profile**, **@Conditional**, or configuration conditions.
- The dependency type does not match, including generic types.

### Multiple matching beans

~~~text
Injection point: PaymentGateway
Candidates:
  - CardPaymentGateway
  - BankTransferGateway
Result:          cannot determine a single unique bean
~~~

The message is usually related to **NoUniqueBeanDefinitionException**:

~~~text
expected single matching bean but found 2
~~~

Common causes:

- Multiple implementations share the same type.
- One implementation is registered via both component scanning and **@Bean**.
- Multiple configurations create beans of the same type.
- A newly imported module introduces a second implementation.

How to resolve:

- Use **@Primary** if there is a default implementation.
- Use **@Qualifier** if each injection point needs a specific role.
- Use **List<T>**, **Map<String, T>**, or a provider if multiple implementations are needed.
- Remove duplicate bean registration if it is a configuration error.

## 10. Workflow for handling NoUniqueBeanDefinitionException

When you see an error reporting multiple beans of the same type, do not immediately add **@Primary** without understanding why they coexist. Trace through these steps:

**Step 1 — Identify the injection point.** Read which class, constructor, or method is requesting which type. For example, **PaymentGateway**.

**Step 2 — List the candidates.** Read the list of beans in the error message. Identify which beans come from component scan, which from **@Bean**, and which from auto-configuration or sub-modules.

**Step 3 — Determine the application's intent.** Does the application need a default implementation, a per-use-case implementation, or all implementations?

**Step 4 — Choose the appropriate mechanism.**

| Intent | Mechanism |
|---|---|
| One default bean for most injection points | **@Primary** |
| Different places need different implementations | **@Qualifier** or custom qualifier |
| Need to run all implementations | **List<T>**, **Set<T>**, array, or stream |
| Need access by bean name | **Map<String, T>** or provider with explicit selection |
| Bean only exists in certain environments | **@Profile**, **@Conditional**, and appropriate optional dependency |
| Unintentional duplicate bean registration | Fix registration source so only the needed bean is created |

**Step 5 — Verify runtime behavior.** Confirm the right implementation is injected, collection ordering is right if required, and no unwanted beans exist in the context.

## 11. @Primary, @Qualifier, and @Order do not replace one another

These three annotations are often confused:

| Annotation | Question it answers | Typical case |
|---|---|---|
| **@Primary** | Among matching candidates, which bean is the preferred choice for a single dependency? | Default payment gateway |
| **@Qualifier** | Which group/role of candidate does this injection point need? | Service requiring the bank gateway |
| **@Order** | In what order should beans in a collection/ordered processing be sorted? | Validation steps running in sequence |

For example:

~~~java
@Component
@Primary
public class CardGateway implements PaymentGateway {
}

@Component
@Qualifier("bank")
public class BankGateway implements PaymentGateway {
}

@Component
@Order(1)
public class StockRule implements OrderRule {
}
~~~

- **CheckoutService(PaymentGateway gateway)** can receive **CardGateway** because it is primary.
- **BankPayoutService(@Qualifier("bank") PaymentGateway gateway)** receives **BankGateway**.
- **OrderValidationService(List<OrderRule> rules)** receives multiple rules and their order can be controlled with **@Order**.

You should not use **@Order(1)** expecting Spring to choose that bean for a single parameter instead of **@Primary** or **@Qualifier**.

## 12. Choosing implementations by profile or configuration condition

Sometimes an application only wants to register one implementation depending on the environment. For example, the development environment uses a fake gateway; the production environment uses a real gateway.

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway sandboxGateway() {
        return new SandboxPaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway productionGateway() {
        return new ProductionPaymentGateway();
    }
}
~~~

When running with the **dev** profile, the sandbox bean is registered; with the **prod** profile, the production bean is registered. Make sure the profile is activated properly and no other implementation of the same type causes ambiguity.

In Spring Boot, conditions such as **@ConditionalOnProperty** or **@ConditionalOnMissingBean** are also commonly used in auto-configuration to select or provide default beans. They answer **which bean is registered in the context**, whereas **@Primary** and **@Qualifier** handle selecting among already-registered candidates.

Do not use profiles to represent individual customers or individual requests. Profiles are generally application-context-level configuration choices; per-request business selection should be handled inside services based on valid data and rules.

## 13. A complete example: default and qualifier-based selection

Suppose the application has two gateways:

~~~java
public interface PaymentGateway {
    String name();
}
~~~

Default implementation:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String name() {
        return "card";
    }
}
~~~

Bank transfer implementation:

~~~java
@Component
@Qualifier("bank")
public class BankTransferGateway implements PaymentGateway {

    @Override
    public String name() {
        return "bank";
    }
}
~~~

Service using the default gateway:

~~~java
@Service
public class DefaultCheckoutService {

    private final PaymentGateway gateway;

    public DefaultCheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String selectedGateway() {
        return gateway.name();
    }
}
~~~

Service dedicated to bank transfers:

~~~java
@Service
public class BankPayoutService {

    private final PaymentGateway gateway;

    public BankPayoutService(
            @Qualifier("bank") PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String selectedGateway() {
        return gateway.name();
    }
}
~~~

Result:

| Injection point | Injected bean |
|---|---|
| **DefaultCheckoutService(PaymentGateway)** | **CardPaymentGateway** |
| **BankPayoutService(@Qualifier("bank") PaymentGateway)** | **BankTransferGateway** |

Both beans exist in the ApplicationContext. The container does not remove the bank transfer implementation just because card is marked **@Primary**.

## 14. Additional rules when designing candidates

### Bean names should be stable and meaningful

When using **@Bean**, the method name usually becomes the default bean name. If other code depends on this name via a string qualifier, renaming the method can affect wiring. Custom qualifiers can express roles more stably.

### Do not overuse @Primary

If multiple services have different intents but all accidentally receive the primary implementation, a default bean can hide the fact that a service needs a specific role. For critical integrations, an explicit qualifier is usually easier to read.

### Do not use a collection if you only want to pick one bean

Injecting **List<PaymentGateway>** and taking the first element is a fragile selection approach if there is no clearly designed ordering rule. Using a qualifier or a registry/router with explicit rules is easier to understand.

### Be careful when changing dependencies in modules

Adding a new implementation to the classpath can turn an injection point that previously had only one candidate into an ambiguous one. Therefore, adding a bean is a change that can affect the startup of other modules, even without directly modifying the service that uses it.

### Distinguish bean candidates from per-request objects

Spring injects beans according to context and scope. A request carrying **paymentMethod = "bank"** does not automatically make the container choose a different bean for that individual request. If a service must route per request, inject a set of implementations or a router and let application logic pick the appropriate adapter based on validated input.

## 15. Practice observing how Spring selects beans

Create a Spring Boot project with the **Spring Context** dependency (or an appropriate Spring Boot starter), then add the **PaymentGateway** interface, two implementations, and a service like the example above.

Try each scenario:

1. **Only one implementation.** Start the context and observe constructor injection succeeding.
2. **Add a second implementation.** Remove qualifier and primary; observe the multiple-candidate error when creating the service.
3. **Mark one bean @Primary.** Restart; observe the service receiving the preferred bean.
4. **Use @Qualifier.** Create another service requesting the bank qualifier; confirm the two services receive two different implementations.
5. **Inject List<PaymentGateway>.** Observe both beans appearing in the collection, including the primary bean.
6. **Add @Order.** Inject a List and observe the sort order.
7. **Remove an implementation from the active profile.** Observe the difference between missing bean and multiple beans.
8. **Switch to a generic interface.** Try Store<String> and Store<Integer>, then try raw Store to see how generic metadata affects candidate selection.

When debugging, observe startup logs and exception messages. If Actuator or an appropriate bean inspection tool is available in the development environment, you can use it to see which beans are registered. Do not expose administrative bean information to unauthorized users in production environments.

## 16. Candidate selection mindset in real-world design

Before adding **@Primary** or **@Qualifier**, answer these questions:

- Does this dependency need **one default implementation**, **one implementation by role**, or **all implementations**?
- Are there multiple beans because the application intentionally supports multiple strategies, or because the same bean was registered twice?
- Does the selection belong to startup configuration or per-request business decisions?
- Do the type and generic type at the injection point sufficiently describe the intent?
- Should the qualifier be a simple label or a custom annotation with clear meaning?
- If the bean is absent, should the application fail fast, use a valid fallback, or skip a secondary feature?
- If a collection is ordered, is that order part of the business behavior and properly verified?

A good rule of thumb is **let the Java type express the contract, qualifier express the role, primary express the default choice, and collection express the need to use multiple implementations**.

## Conclusion

Spring typically finds matching beans by **dependency type**. When there is only one matching candidate, the container can inject it directly. When there are multiple candidates, the application must express its intent clearly:

- Use **@Primary** to mark the preferred bean for a single dependency.
- Use **@Qualifier** or a custom qualifier to select a bean by role.
- Use **List<T>**, **Set<T>**, an array, or **Map<String, T>** when multiple implementations are needed.
- Use **ObjectProvider<T>** when you need to access beans on demand and handle absence or non-uniqueness.
- Use **@Profile** or conditional configuration when you need to decide which beans are registered per environment.

When encountering errors, distinguish **no matching bean** from **multiple matching beans**. Check the classpath, component scan, registration conditions, and metadata before fixing. Bean selection is part of dependency design: Spring enforces the rules the application declares, while the application must determine which implementation truly fits each use case.
