# NoUniqueBeanDefinitionException: Multiple Candidates Without a Selection Rule

Spring usually injects dependencies by **data type**. When a constructor requires `PaymentGateway`, the container locates beans assignable to that type and selects a matching candidate. However, when the context contains multiple beans satisfying the requirement without a disambiguation rule, Spring cannot guess which bean the application wants.

The result is typically `NoUniqueBeanDefinitionException`, sometimes wrapped inside `UnsatisfiedDependencyException` in startup error messages.

Example with two implementations:

~~~java
public interface PaymentGateway {
    void charge(long amount);
}
~~~

~~~java
@Component
public class StripePaymentGateway implements PaymentGateway {
    @Override
    public void charge(long amount) {
        // Call Stripe.
    }
}
~~~

~~~java
@Component
public class BankPaymentGateway implements PaymentGateway {
    @Override
    public void charge(long amount) {
        // Call bank payment gateway.
    }
}
~~~

A service requiring a single bean:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

If both implementations are registered without a qualifier, primary marker, or other appropriate selection rule, Spring does not know whether to inject `StripePaymentGateway` or `BankPaymentGateway`.

**This is a dependency selection error when multiple candidates exist**, not necessarily a bean creation error or a duplicate bean name error. The right fix depends on design intent: pick a default bean, specify a qualifier, inject all candidates, or fix bean registration.

## 1. Understanding the Exception and Error Message

`NoUniqueBeanDefinitionException` belongs to Spring Beans. It occurs when an operation expects a single bean by type/name or lookup criteria, yet multiple candidates match.

A typical message:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.example.PaymentGateway' available:
expected single matching bean but found 2:
stripePaymentGateway,bankPaymentGateway
~~~

The bean names in the message are a vital clue. They reveal which candidates Spring found.

During startup, the exception may appear inside an error chain:

~~~text
ApplicationContext failed to start
  |
  v
UnsatisfiedDependencyException
  |
  v
NoUniqueBeanDefinitionException
  |
  v
PaymentGateway candidates:
  - stripePaymentGateway
  - bankPaymentGateway
~~~

`UnsatisfiedDependencyException` usually identifies which bean's dependency could not be satisfied. The root cause `NoUniqueBeanDefinitionException` explains specifically that multiple matching beans exist.

### Distinguishing Similar Errors

| Exception | Meaning | Example |
|---|---|---|
| `NoSuchBeanDefinitionException` | No matching bean found | No bean implements `PaymentGateway` |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist when a single bean is required | Stripe and Bank gateways exist; constructor takes a single gateway |
| `UnsatisfiedDependencyException` | Could not resolve a dependency while creating a bean | `CheckoutService` constructor could not be supplied its dependency |
| `BeanDefinitionOverrideException` | A bean definition with a duplicate name is registered while overriding is disabled | Two configurations declare bean name `paymentGateway` |

Note: `NoUniqueBeanDefinitionException` is a form of non-unique bean lookup error and inherits from `NoSuchBeanDefinitionException`. When inspecting logs, look for the deepest exception and the list of candidate names rather than reading only the first line.

## 2. Why Does Spring Find Multiple Beans?

Beans can be registered from multiple sources:

- `@Component`, `@Service`, `@Repository`, or `@Controller` discovered by component scanning.
- `@Bean` methods in a `@Configuration` class.
- `@Import` of a configuration class or component.
- Auto-configuration from a Spring Boot starter.
- Test configuration such as `@MockBean` (in corresponding Spring Boot versions) or custom test beans.
- An integration module registering a default interface implementation.

Example where two registration mechanisms both appear:

~~~java
@Component
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
~~~

Both beans are candidates for `PaymentGateway`. This may be completely intentional when an application supports multiple providers. The error occurs only when an injection point requires a single bean without specifying a choice.

### 2.1. Two Differently Named Beans Are Not a Duplicate Bean Name

Example:

- `stripePaymentGateway`
- `bankPaymentGateway`

These are two separate bean definitions with distinct names. Spring allows them to coexist.

If two configuration classes both declare bean name `paymentGateway`, that is a duplicate name / bean definition override issue instead. Do not handle `NoUniqueBeanDefinitionException` by enabling bean overriding; the two problems have different causes.

### 2.2. Overly Broad Component Scanning

A module might accidentally be scanned twice, or both implementations might be discovered across different packages. Determine whether both beans are genuinely needed.

If only one implementation is intended, fix scan/import scope or remove the extra registration. If both are intentional, keep them and specify how callers select among them.

## 3. Approach 1: @Primary to Choose a Default Bean

If the application has multiple implementations yet one is used **by default in most cases**, mark that bean with `@Primary`.

~~~java
@Component
@Primary
public class StripePaymentGateway implements PaymentGateway {

    @Override
    public void charge(long amount) {
        // Call Stripe.
    }
}
~~~

The other implementation requires no changes:

~~~java
@Component
public class BankPaymentGateway implements PaymentGateway {

    @Override
    public void charge(long amount) {
        // Call bank.
    }
}
~~~

The original constructor can now be resolved:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

When Spring needs a single dependency of type `PaymentGateway`, `StripePaymentGateway` takes priority because it is the primary candidate.

### 3.1. Placing @Primary on @Bean

You can annotate a bean factory method:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway defaultPaymentGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
~~~

`@Primary` can be placed on a component class or a bean definition method. When used on `@Bean`, the annotation applies to the bean registered by that method.

### 3.2. @Primary Does Not Remove Other Beans

After marking a primary bean:

- Both Stripe and Bank still exist in the context.
- You can still inject the Bank bean using a qualifier.
- You can still inject a list of all gateways.
- `@Primary` only breaks ties at injection points needing a single dependency without a more specific directive.

Do not interpret `@Primary` as "the only registered bean" or "other beans are disabled."

### 3.3. Only One Primary Should Exist per Candidate Set

If two beans of the same type are both marked `@Primary`, Spring still lacks a unique choice:

~~~java
@Component
@Primary
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
@Primary
class BankPaymentGateway implements PaymentGateway {
}
~~~

A constructor needing `PaymentGateway` will still fail because there are multiple equal primary candidates. Remove the extra primary or use qualifiers at injection points to express specific intent.

### 3.4. @Primary Does Not Affect Collection Injection

If a constructor requests:

~~~java
public PaymentCoordinator(List<PaymentGateway> gateways) {
    this.gateways = gateways;
}
~~~

Spring injects all matching beans into the list, including both primary and non-primary beans. `@Primary` does not restrict a collection to a single bean.

This matters when an application both has a default gateway and needs to list all gateways for runtime selection.

## 4. Approach 2: @Qualifier to Specify Which Bean to Inject

If a service must use a specific implementation, `@Qualifier` expresses intent more cleanly than changing the application-wide primary.

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("bankPaymentGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Spring narrows the candidate set by qualifier. Here, the dependency receives the bean matching `bankPaymentGateway`.

A component's default bean name is usually its class name with a lowercase initial letter, so `BankPaymentGateway` typically gets `bankPaymentGateway`. If the bean name was customized, use the exact registered name.

### 4.1. @Qualifier on Component Classes

You can attach meaningful qualifiers to implementations:

~~~java
@Component
@Qualifier("bank")
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Qualifier("card")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Injection:

~~~java
@Service
public class BankTransferService {

    private final PaymentGateway gateway;

    public BankTransferService(
            @Qualifier("bank") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

`bank` and `card` are qualifier labels. Naming by role or capability is usually clearer than depending directly on implementation class names.

### 4.2. @Qualifier on @Bean Methods

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
~~~

Services can request `@Qualifier("card")` or `@Qualifier("bank")`.

### 4.3. Qualifiers Do Not Have to Be Bean Names

`@Qualifier` values are commonly used as labels to filter candidates. Bean names can participate as a matching fallback, yet large systems should avoid coupling everywhere to internal bean names.

For example, multiple beans may share the qualifier `"external"` if they belong to the same group. In that case, the qualifier expresses a trait, and multiple candidates may remain in that group; another criterion is still needed if an injection point expects a single bean.

### 4.4. How Do @Primary and @Qualifier Interact?

- `@Qualifier` filters candidates by matching label/criteria.
- `@Primary` selects the default candidate among the remaining candidates when a single bean is required.
- If a qualifier matches no beans, Spring cannot satisfy the dependency.
- If a qualifier matches multiple beans with no tie-breaker, ambiguity remains.

When a service specifically needs the Bank gateway, `@Qualifier("bank")` states intent directly. Do not mark Bank as primary just to fix one injection point if other services should still default to Stripe.

## 5. Creating Custom Qualifier Annotations

In systems with many gateway types, string literals can be repeated and become hard to refactor. Spring lets you define custom qualifier annotations.

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Qualifier
public @interface BankChannel {
}
~~~

Registering the implementation:

~~~java
@Component
@BankChannel
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Injection:

~~~java
@Service
public class BankTransferService {

    private final PaymentGateway gateway;

    public BankTransferService(@BankChannel PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Custom qualifiers make dependency meaning explicit in code and avoid string typos. Qualifiers with attributes can also express capability or tenant categories according to application conventions.

Example annotation with an attribute:

~~~java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface PaymentChannel {
    String value();
}
~~~

~~~java
@Component
@PaymentChannel("bank")
class BankPaymentGateway implements PaymentGateway {
}
~~~

~~~java
public CheckoutService(
        @PaymentChannel("bank") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom qualifiers do not create new beans; they only supply metadata so Spring can filter registered beans.

## 6. Approach 3: @Resource When Injecting by Name

`@Autowired` generally resolves dependencies by type, then uses qualifiers/primary to pick one. `@Resource` has semantics oriented around **bean name**.

Example in Spring Boot 3:

~~~java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @Resource(name = "bankPaymentGateway")
    private PaymentGateway gateway;
}
~~~

In Spring Boot 2 lines using the legacy Java EE namespace, the import was typically `javax.annotation.Resource`, requiring the corresponding annotations dependency if the JDK omitted it.

`@Resource(name = "...")` explicitly states that the field/property requires the bean with that name. This is useful when bean names are an intentional part of wiring.

### 6.1. How @Resource Differs from @Qualifier

| Mechanism | Focus |
|---|---|
| `@Autowired` | Looks up dependency by type |
| `@Autowired + @Qualifier` | Looks up by type, then filters by qualifier |
| `@Primary` | Marks the preferred candidate for a single dependency |
| `@Resource(name = "...")` | Requests a bean by its explicit name |

Do not convert all constructor injection to field injection just to use `@Resource`. For mandatory dependencies, constructor injection makes dependencies explicit and simplifies testing. Use `@Resource` on setters or fields when it fits the existing architecture.

## 7. Parameter Name Matching: Parameter Names Can Help Select Beans

In certain cases, Spring can use **constructor/method parameter names** as a fallback to distinguish candidates if the parameter name matches a bean name.

Example:

~~~java
@Component("stripeGateway")
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component("bankGateway")
class BankPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Service
class CheckoutService {

    private final PaymentGateway bankGateway;

    CheckoutService(PaymentGateway bankGateway) {
        this.bankGateway = bankGateway;
    }
}
~~~

When parameter name metadata is preserved in bytecode and resolution conditions apply, Spring can use the name `bankGateway` to pick the matching bean.

### 7.1. Parameter Name Metadata Is Required

In modern Spring lines, parameter name matching depends on parameter metadata preserved at compile time; in Java, this usually requires the `-parameters` compiler option.

Gradle Java:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Maven compiler plugin:

~~~xml
<configuration>
    <parameters>true</parameters>
</configuration>
~~~

Depending on Spring version and build setup, matching behavior and fallback order can vary. Treat this as a convenience fallback, **never a replacement for explicit qualifiers on architecturally significant dependencies**.

### 7.2. Why Not Rely Solely on Parameter Names?

Renaming a variable or parameter during refactoring can silently change which bean gets selected. If a dependency must be the Bank gateway by business requirement, `@Qualifier("bank")` or a custom qualifier states intent far more safely.

Parameter names work as a simple fallback, not as the sole wiring contract for an application with multiple implementations.

## 8. Spring Framework 6.2+: @Fallback

Starting in Spring Framework 6.2 (used in corresponding modern Spring Boot releases, such as Boot 3.4+), the `@Fallback` annotation marks fallback beans.

Example:

~~~java
import org.springframework.context.annotation.Fallback;
import org.springframework.stereotype.Component;

@Component
@Fallback
public class NoopNotificationSender implements NotificationSender {

    @Override
    public void send(String message) {
        // Do not send for real; fallback implementation.
    }
}
~~~

Regular implementation:

~~~java
@Component
public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String message) {
        // Send email.
    }
}
~~~

When a non-fallback candidate exists alongside fallback candidates, the regular bean is preferred for a single dependency. Fallback beans remain registered and can still be injected via qualifiers or retrieved via collections.

### 8.1. @Fallback vs. @Primary

| Annotation | Meaning |
|---|---|
| `@Primary` | Marks a bean as preferred among candidates |
| `@Fallback` | Marks a bean as a fallback, yielding to regular candidates |
| `@Qualifier` | Filters candidates by specific label/metadata |

Avoid conflictingly placing both `@Primary` and `@Fallback` on the same bean. If all candidates are fallback beans and multiple beans of the same type still exist, an explicit selection rule is still required.

`@Fallback` does not exist in older Spring Framework versions. If your project runs Spring Boot 3.3 or earlier or a Framework version without it, use `@Primary`/`@Qualifier` appropriate to your version instead of copying an unavailable import.

## 9. @Order Does Not Resolve Ambiguity for a Single Dependency

A common misconception is annotating:

~~~java
@Component
@Order(1)
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
@Order(2)
class BankPaymentGateway implements PaymentGateway {
}
~~~

and expecting Spring to pick Stripe when a constructor asks for:

~~~java
CheckoutService(PaymentGateway gateway) {
}
~~~

`@Order` primarily controls bean ordering in collection/array/stream injection points or ordered processing mechanisms. It is **not the standard way to pick a single bean** for a single dependency.

For a default, use `@Primary`. For a specific implementation, use `@Qualifier`. For all implementations in order, inject a collection and use `@Order`.

Example:

~~~java
@Service
class PaymentCoordinator {

    private final List<PaymentGateway> gateways;

    PaymentCoordinator(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
~~~

Beans annotated with `@Order` are sorted in that list accordingly.

## 10. Approach 4: Inject All Candidates via List, Set, or Array

If the application genuinely needs multiple implementations, do not force Spring to pick one bean. Request a collection:

~~~java
@Service
public class PaymentCoordinator {

    private final List<PaymentGateway> gateways;

    public PaymentCoordinator(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public void chargeAll(long amount) {
        for (PaymentGateway gateway : gateways) {
            gateway.charge(amount);
        }
    }
}
~~~

Spring injects all beans matching `PaymentGateway` into the collection.

Common forms:

~~~java
PaymentCoordinator(List<PaymentGateway> gateways)
~~~

~~~java
PaymentCoordinator(Set<PaymentGateway> gateways)
~~~

~~~java
PaymentCoordinator(PaymentGateway[] gateways)
~~~

Collection injection does not require a unique bean, avoiding single-dependency ambiguity.

### 10.1. Injecting a Map Using Bean Names as Keys

~~~java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentGateway getGateway(String name) {
        PaymentGateway gateway = gateways.get(name);

        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unknown payment gateway: " + name);
        }

        return gateway;
    }
}
~~~

With map injection, keys are typically bean names and values are bean instances—for example `stripePaymentGateway` or `bankPaymentGateway`.

Never allow HTTP clients to pass arbitrary bean names directly into a map lookup without an allowlist/authorization. Bean names are internal application details, not a public API or access-control mechanism.

### 10.2. Selecting by Business Key Instead of Bean Name

If runtime needs to select a gateway by payment method, design the interface:

~~~java
public interface PaymentGateway {
    PaymentMethod supports();
    void charge(long amount);
}
~~~

Then build a registry from the bean list:

~~~java
@Component
public class PaymentGatewayRegistry {

    private final Map<PaymentMethod, PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> candidates) {
        this.gateways = candidates.stream()
                .collect(Collectors.toUnmodifiableMap(
                        PaymentGateway::supports,
                        Function.identity()
                ));
    }

    public PaymentGateway get(PaymentMethod method) {
        PaymentGateway gateway = gateways.get(method);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment method: " + method);
        }
        return gateway;
    }
}
~~~

This intentionally shifts from "Spring picks one bean at startup" to "the application chooses an implementation by business key at runtime." If two gateways declare the same `PaymentMethod`, `toUnmodifiableMap` fails when creating the registry—signaling a duplicate business mapping that should be fixed rather than hidden.

## 11. Approach 5: ObjectProvider When Selection or Access Needs Deferral

`ObjectProvider<T>` lets you query beans on demand instead of injecting a single instance directly in the constructor.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OptionalReportService {

    private final ObjectProvider<ReportExporter> exporters;

    public OptionalReportService(
            ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void exportIfAvailable() {
        ReportExporter exporter = exporters.getIfAvailable();

        if (exporter != null) {
            exporter.export();
        }
    }
}
~~~

Useful APIs:

| API | General Behavior |
|---|---|
| `getObject()` | Retrieves the bean; fails if a unique bean cannot be resolved |
| `getIfAvailable()` | Returns null if no bean exists; still throws if multiple indistinguishable candidates exist |
| `getIfUnique()` | Returns the bean if one unique selectable candidate exists; returns null if none or non-unique |
| `stream()` | Iterates over candidates |
| `orderedStream()` | Iterates over candidates in order per ordering rules |

`ObjectProvider` does not resolve ambiguity by guessing. It provides APIs for the application to decide behavior when zero or multiple candidates exist.

### 11.1. Optional Is Not a Way to Choose Among Multiple Beans

Example:

~~~java
public CheckoutService(Optional<PaymentGateway> gateway) {
}
~~~

`Optional<PaymentGateway>` models a dependency that may be absent. If two matching beans exist with no selection rule, `Optional` does not turn them into a single bean; ambiguity still occurs.

Use `Optional` for optionality, `ObjectProvider` for flexible lookup, and `@Qualifier`/`@Primary` for bean selection.

## 12. Using Generic Types to Distinguish Beans Sharing a Raw Interface

Spring can use generic type metadata to narrow candidates.

Example:

~~~java
public interface MessageHandler<T> {
    void handle(T message);
}
~~~

~~~java
@Component
class OrderMessageHandler implements MessageHandler<OrderMessage> {
    @Override
    public void handle(OrderMessage message) {
    }
}
~~~

~~~java
@Component
class InvoiceMessageHandler implements MessageHandler<InvoiceMessage> {
    @Override
    public void handle(InvoiceMessage message) {
    }
}
~~~

Requested dependency:

~~~java
@Service
class OrderProcessor {

    private final MessageHandler<OrderMessage> handler;

    OrderProcessor(MessageHandler<OrderMessage> handler) {
        this.handler = handler;
    }
}
~~~

Spring can use generic metadata to select `OrderMessageHandler` over `InvoiceMessageHandler`, provided generic types are preserved and resolvable from bean definitions/classes.

This acts as a **generic qualifier**. It is handy when an interface is parameterized by handled data type, such as `Repository<User>` and `Repository<Order>`.

However, if generics are erased or unresolvable due to raw types, factory methods, or complex inheritance structures, filtering may not work as expected. In such cases, declare more concrete return types or use explicit qualifiers.

## 13. When Should You Fix Bean Registration Instead of Adding Qualifiers?

Not every ambiguity should be solved by adding `@Primary` or `@Qualifier`. First determine why multiple beans exist.

### Case A: Only One Implementation Is Needed

If the application uses only one gateway, yet both a component and a configuration register the same implementation or an unneeded one, remove the redundant registration.

Bad design example:

~~~java
@Component
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }
}
~~~

The same Stripe logic is registered twice under two bean names. Unless two separate instances are genuinely required, keep only one registration mechanism.

### Case B: Both Implementations Are Valid

If the application genuinely supports multiple providers, keep both. Use qualifiers or a registry to choose as needed.

### Case C: Starter Default Bean Collides with User Bean

A starter should provide a conditional default implementation:

~~~java
@AutoConfiguration
public class PaymentAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

If the application provides a `PaymentGateway` bean, the default auto-configuration backs off per condition.

However, if the application actively registers **two** `PaymentGateway` beans, the "missing bean" condition no longer holds; the default bean is skipped, yet the application's own two beans remain and a single injection still hits ambiguity.

`@ConditionalOnMissingBean` prevents creating an unnecessary default; it **does not pick among multiple beans declared by the application**.

### Case D: Multiple Profiles or Config Imports Cause Duplicate Registrations

Check `@Profile`, `@ConditionalOnProperty`, `@Import`, and component scanning. Each implementation should only be registered in environments where it belongs.

Do not use profiles to mask an error if production genuinely needs two implementations. Profiles activate configurations per environment, not per injection point.

## 14. Bean Name, Qualifier, and Primary: Choosing by Intent

Suppose an application has two gateways:

~~~java
@Component("cardGateway")
@Qualifier("external")
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component("bankGateway")
@Qualifier("domestic")
class BankPaymentGateway implements PaymentGateway {
}
~~~

Service needing the domestic gateway:

~~~java
@Service
class DomesticCheckoutService {

    private final PaymentGateway gateway;

    DomesticCheckoutService(
            @Qualifier("domestic") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Service needing the external gateway:

~~~java
@Service
class InternationalCheckoutService {

    private final PaymentGateway gateway;

    InternationalCheckoutService(
            @Qualifier("external") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Another service can inject all:

~~~java
@Service
class PaymentDiagnostics {

    PaymentDiagnostics(List<PaymentGateway> gateways) {
        // Observe or coordinate all implementations.
    }
}
~~~

This structure clearly communicates:

- Bean name is the registration identifier in the container.
- Qualifier is the role-based selection label.
- Primary is the default when a single bean is needed.
- Collection is how to retrieve multiple candidates.

Never pick one of these mechanisms solely because it gets startup working. Choose based on the service's contract.

## 15. Constructor Injection Catches Ambiguity Early

Constructor injection is generally recommended for mandatory dependencies:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

If Spring cannot resolve the dependency, the context fails right at bean creation instead of creating the service with an uninjected field.

With a single constructor, Spring usually does not require `@Autowired` on the constructor:

~~~java
@Service
class CheckoutService {

    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

If multiple constructors exist, review constructor selection rules and annotations. Regardless of whether you use field, setter, or constructor injection, **multiple candidates for a single dependency still need disambiguation**.

### 15.1. Do Not Use @Autowired(required = false) to Mask Ambiguity

~~~java
@Autowired(required = false)
private PaymentGateway gateway;
~~~

`required=false` allows a dependency to be absent in some scenarios. It is not a rule for choosing between two beans of the same type. If multiple indistinguishable candidates exist, ambiguity must still be resolved.

## 16. Diagnosing from Exceptions: Read Candidate Names First

When the application reports:

~~~text
expected single matching bean but found 3:
stripePaymentGateway,bankPaymentGateway,mockPaymentGateway
~~~

Trace these names:

1. Find the class or method declaring each bean.
2. Determine whether each bean comes from `@Component`, `@Bean`, `@Import`, or auto-configuration.
3. Check whether each bean actually needs to exist in the current profile.
4. Determine whether the injection point needs one bean or all of them.
5. Apply qualifiers/primary/registry or remove redundant registrations.

A bean name may be a `@Bean` method name, a component name, or a custom name. Never assume every bean is named after its class.

### 16.1. Using ApplicationContext to List Beans by Type

In a test or diagnostics snippet with context access:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentGateway.class);

for (String name : names) {
    System.out.println(name);
}
~~~

To inspect bean instances by type:

~~~java
Map<String, PaymentGateway> candidates =
        applicationContext.getBeansOfType(PaymentGateway.class);
~~~

These APIs confirm which candidates exist in the container. Avoid logging entire objects or sensitive bean fields.

### 16.2. Actuator beans Endpoint

If Actuator is installed and the `beans` endpoint is exposed under appropriate security policy, it helps inspect bean names and context ownership.

Never expose diagnostics endpoints publicly on the Internet just to debug ambiguity. Prefer tests, internal logs, or protected development environments.

### 16.3. Condition Evaluation Report

For auto-configurations, running with `--debug` prints the Condition Evaluation Report showing which configurations matched or backed off.

The report explains why an auto-configuration created or skipped a bean. It does not itself resolve ambiguity among user-registered beans.

## 17. Testing Bean Selection with ApplicationContextRunner

A small integration test verifies that `@Primary` and `@Qualifier` wire as expected.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

class PaymentGatewayWiringTest {

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {

        @Bean
        @Primary
        PaymentGateway stripeGateway() {
            return new StripePaymentGateway();
        }

        @Bean
        @Qualifier("bank")
        PaymentGateway bankGateway() {
            return new BankPaymentGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void primaryGatewayIsInjectedByDefault() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();

            CheckoutService service =
                    context.getBean(CheckoutService.class);

            assertThat(service.gateway())
                    .isInstanceOf(StripePaymentGateway.class);
        });
    }
}
~~~

This example assumes `CheckoutService` exposes a `gateway()` accessor for testing and both implementations can be instantiated in tests. You can assert on observable behavior instead if you prefer not to expose accessors solely for tests.

### 17.1. Testing Specific Qualifiers

~~~java
@Bean
BankTransferService bankTransferService(
        @Qualifier("bank") PaymentGateway gateway) {
    return new BankTransferService(gateway);
}
~~~

Then assert the injected bean is `BankPaymentGateway`.

### 17.2. Testing Remaining Ambiguity

You can omit `@Primary` and declare a service requiring a single `PaymentGateway`. The test context should fail with `NoUniqueBeanDefinitionException` as the root cause.

~~~java
runner.run(context -> {
    assertThat(context).hasFailed();
    assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(
                    NoUniqueBeanDefinitionException.class);
});
~~~

This tests wiring configuration directly. Do not rely solely on plain Java constructor unit tests because constructors can instantiate objects without passing through the Spring container.

## 18. Testing Collection Injection

If a service requires all implementations:

~~~java
@Service
public class GatewayRegistry {

    private final List<PaymentGateway> gateways;

    public GatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public int size() {
        return gateways.size();
    }
}
~~~

Test:

~~~java
@Test
void injectsAllPaymentGateways() {
    runner.run(context -> {
        assertThat(context).hasNotFailed();

        GatewayRegistry registry =
                context.getBean(GatewayRegistry.class);

        assertThat(registry.size()).isEqualTo(2);
    });
}
~~~

This test verifies the application asks for multiple candidates rather than a single unique candidate.

If ordering matters, annotate implementations with `@Order` or use an ordering mechanism and assert the order. Never rely on incidental component scan order.

## 19. Special Scenarios

### 19.1. Two Beans with the Same Name but Different Types

Bean names are unique within a bean registry under registration rules. If two configurations declare the same name, an override error or override behavior occurs depending on settings. That is distinct from having two differently named beans of the same type.

### 19.2. Parent-Child ApplicationContext

In a context hierarchy, child contexts can see beans from parent contexts per lookup rules. If the same type appears across multiple contexts, dependency resolution involves local candidates and ancestor candidates. Inspect the specific context creating the bean and the lookup API rather than simply counting beans across the whole JVM.

If multiple child contexts declare an implementation, they do not automatically see sibling beans. Parents also do not look down into children. Candidate counting must therefore account for the context hierarchy.

### 19.3. Conditionally Created Beans

A bean may appear only when a property or classpath condition holds:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "provider",
        havingValue = "bank"
)
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
~~~

If multiple conditions match simultaneously, multiple implementations appear. Check active profiles and property sources whenever candidate lists differ across local/test/production.

### 19.4. Tests Adding Mock Beans

Tests may register mocks to replace real beans while keeping real implementations in the context, resulting in two candidates. When using mock bean mechanisms for your Spring Boot version, verify whether the mock **replaces** the bean with the right name/type or registers an extra bean.

Test slices and test contexts import different configurations, so candidate lists may differ from production.

## 20. Workflow for Resolving NoUniqueBeanDefinitionException

When encountering the error, follow this sequence:

~~~text
NoUniqueBeanDefinitionException
          |
          v
Read type and candidate names in message
          |
          v
Locate where each bean is registered
          |
          v
Are multiple implementations meant to coexist?
          |
      +---+---+
      |       |
     No      Yes
      |       |
      v       v
Remove extra  Does injection need one bean
registration? or all beans?
              |
          +---+---+
          |       |
         One     Many
          |       |
          v       v
     @Primary /   List / Set / Map /
     @Qualifier  ObjectProvider / Registry
          |
          v
Write integration test confirming wiring
          |
          v
Rerun app in the right profile/context
~~~

### Diagnostic Checklist

- Read the root cause, not only the outer wrapper exception.
- Record all candidate names.
- Locate each bean definition and its registration source.
- Check component scan, `@Import`, `@Bean`, and auto-configuration.
- Determine whether the injection point truly needs one bean or many.
- If one default bean, choose `@Primary` or `@Fallback` per version.
- If one specific implementation, use `@Qualifier` or `@Resource(name=...)`.
- If runtime selection is needed, inject a collection and build a registry by business key.
- Check profiles/conditions and context hierarchy.
- Write a context test verifying the expected implementation is injected.

## 21. Fixes to Avoid

**Enabling bean definition overriding to fix ambiguity.** Overriding addresses duplicate bean names, whereas NoUnique is usually caused by differently named beans matching the same type. Enabling override creates no dependency selection rule.

**Renaming classes until Spring finds only one bean.** Class names are not a type-based dependency selection tool. If both implementations remain scanned, both remain candidates.

**Marking every implementation with @Primary.** With multiple primaries, the problem remains unsolved. Mark only one intentional default or use qualifiers.

**Using @Order to select a single bean.** Ordering is mainly for collections/ordered processing; it does not replace `@Primary` or `@Qualifier`.

**Using Optional to hide the error.** Optional models an absent dependency, not choosing one bean among multiple candidates.

**Catching the exception and picking the first bean arbitrarily.** Candidate order is not a business contract. The first element can shift when adding dependencies or refactoring packages.

**Using @Lazy to hide ambiguity.** Lazy defers instantiation/resolution without establishing a stable selection rule. The error may simply surface later when the bean is used.

**Scattering ApplicationContext.getBean(type) across business code.** That pushes wiring errors from startup to runtime and hides dependencies. When dynamic lookup is needed, build a dedicated bean registry with explicit business keys.

## 22. Choosing the Right Mechanism by Intent

| Design Intent | Suitable Mechanism |
|---|---|
| One default implementation for a single dependency | `@Primary` |
| A fallback bean when no regular implementation exists | `@Fallback` (Spring Framework 6.2+) |
| A service needing a specific implementation | `@Qualifier` or custom qualifier |
| Selecting a bean by exact name | `@Resource(name = "...")` or name lookup in infrastructure code |
| Retrieving all implementations | `List<T>`, `Set<T>`, or `T[]` |
| Retrieving all and looking up by bean name | `Map<String, T>` |
| Selecting an implementation by business key at runtime | Inject collection and build a registry |
| Dependency may be absent or needs deferred lookup | `ObjectProvider<T>` / `Optional<T>` per semantics |
| Distinguishing implementations by generic type | Generic injection when metadata is resolvable |
| Starter providing a default bean | `@ConditionalOnMissingBean` |
| Bean appearing unintentionally | Fix component scan, imports, profiles, or registration conditions |

## 23. Key Takeaways

1. `NoUniqueBeanDefinitionException` means Spring found multiple matching beans when a single unique bean was required.
2. Read candidate names in the exception to locate registration sources.
3. `@Primary` selects a default candidate; it does not remove the other beans.
4. `@Qualifier` or custom qualifiers express which implementation a specific dependency requires.
5. `@Resource(name = "...")` fits when wiring explicitly by bean name.
6. Parameter name matching can serve as a fallback under compatible versions/compile setups; never substitute it for qualifiers on critical contracts.
7. `@Fallback` is available from Spring Framework 6.2; check your version before using it.
8. `@Order` sorts collections; it is not the standard way to select a single dependency.
9. When all implementations are needed, inject a collection; when runtime business selection is needed, build a registry keyed by business keys.
10. `Optional` does not resolve ambiguity; `ObjectProvider` provides lookup APIs yet still requires handling non-unique cases.
11. `@ConditionalOnMissingBean` lets auto-configuration back off when the application supplies a bean, but does not disambiguate multiple application-registered beans.
12. Constructor injection and integration tests catch wiring errors at startup.
13. Distinguish multiple-candidate errors from duplicate bean name errors; never enable overriding to mask dependency selection bugs.
14. Choose mechanisms by intent: default, specific, all candidates, or runtime selection.

**Conclusion:** `NoUniqueBeanDefinitionException` does not mean Spring failed to instantiate a bean; it means the container found multiple candidates without enough information to pick one reliably. Decide clearly whether the service needs a default bean, a specific implementation, or all implementations. Use `@Primary` for defaults, `@Qualifier` for role-based selection, collections/registries for multiple strategies, and fix bean registration if redundant implementations exist. When dependency intent is explicit in code and verified with context tests, ambiguity errors become easy to diagnose and less likely to recur.
