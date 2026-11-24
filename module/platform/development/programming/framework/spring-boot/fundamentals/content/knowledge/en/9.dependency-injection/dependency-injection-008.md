# ObjectProvider for On-Demand Bean Retrieval or Choosing Among Multiple Candidates

In Spring, constructor injection is the right way to declare dependencies that a bean needs immediately when created. However, there are situations where an application only needs a bean **when actually performing a specific operation**, where a bean might not exist in certain configurations, or where multiple implementations satisfy an interface and one must be selected at runtime.

`ObjectProvider<T>` addresses these scenarios by providing a bean lookup handle from the Spring container. You can receive the provider in a constructor and invoke it when you need to retrieve a bean, check whether a bean is available, or iterate over multiple candidates. A provider defers dependency resolution; it **does not create beans by itself**, does not replace the container, and does not by default create a new instance on every call.

## 1. What Is ObjectProvider?

`ObjectProvider<T>` belongs to the Spring Framework, in the package:

~~~java
import org.springframework.beans.factory.ObjectProvider;
~~~

It extends `ObjectFactory<T>` and adds useful operations for looking up dependencies in a `BeanFactory`:

- Retrieve a bean when needed via `getObject()`.
- Retrieve a bean if present, or receive `null` when absent via `getIfAvailable()`.
- Retrieve a bean when there is a unique matching candidate via `getIfUnique()`.
- Execute an action if a bean is available or if a unique candidate exists.
- Iterate over beans of the same type using `stream()` and `orderedStream()`.

You can visualize it like this:

~~~text
Spring creates ReportService
        |
        | constructor injection
        v
ObjectProvider<ReportExporter>
        |
        | no need to retrieve exporter yet at this point
        |
        +---- when the user requests an export
                    |
                    v
              provider.getObject()
                    |
                    v
              Spring BeanFactory
                    |
             finds matching candidate
                    |
             returns bean or throws error
~~~

The key point is that the constructor receives the **provider** right when the bean is created. Searching for and retrieving `ReportExporter` happens only when code invokes a method on the provider. Thus, an optional dependency might never even be requested during the lifecycle of the bean that holds it.

`ObjectProvider` is not exclusive to Spring Boot. It is a Spring Framework API, so it works in both plain Spring applications and Spring Boot applications.

## 2. Why Not Inject the Dependency Directly?

Suppose an application has a feature that sends reports via email. Some environments configure mail, while others only generate reports for download.

If injected directly:

~~~java
@Service
public class ReportService {
    private final EmailSender emailSender;

    public ReportService(EmailSender emailSender) {
        this.emailSender = emailSender;
    }
}
~~~

Spring must resolve `EmailSender` when creating `ReportService`. If no matching bean exists, the context may fail to start. That is unsuitable when email is an optional feature.

You can use `ObjectProvider`:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ObjectProvider<EmailSender> emailSenders;

    public ReportService(ObjectProvider<EmailSender> emailSenders) {
        this.emailSenders = emailSenders;
    }

    public void sendByEmail(String address, byte[] report) {
        EmailSender sender = emailSenders.getIfAvailable();
        if (sender == null) {
            throw new IllegalStateException(
                    "Email delivery is not configured");
        }
        sender.send(address, report);
    }
}
~~~

When creating `ReportService`, Spring can supply the provider even if no `EmailSender` bean currently exists. Only when `sendByEmail` is called does the code ask the provider to look up the bean. If none exists, `getIfAvailable()` returns `null` and the application handles it according to its policy.

This example assumes `EmailSender` is a bean type in the application. In a real project, we could use an interface like `ReportDeliveryChannel` so the service depends on a contract rather than a concrete implementation.

## 3. Important Lookup Methods

### 3.1. `getObject()` — Require a bean

~~~java
ReportExporter exporter = exporters.getObject();
~~~

`getObject()` asks Spring to resolve a bean matching type `T` and any qualifiers on the injection point. Common error behavior:

- No matching bean found: throws `NoSuchBeanDefinitionException`.
- Multiple candidates exist and none can be uniquely selected: throws `NoUniqueBeanDefinitionException`.
- A unique candidate exists, or one candidate is prioritized by dependency resolution rules: returns that bean.

This is the right choice when the current operation **requires the dependency**. Injecting a provider does not mean the underlying dependency is always optional; calling `getObject()` can still fail if configuration is missing or ambiguous.

`ObjectProvider` also has an overload `getObject(Object... args)` to pass explicit arguments when creating a bean via a factory method that accepts arguments, commonly useful for prototype beans. Use it only when the bean is defined to accept those arguments; you cannot pass arbitrary arguments to just any bean.

### 3.2. `getIfAvailable()` — Return bean if present, otherwise null

~~~java
EmailSender sender = emailSenders.getIfAvailable();
if (sender != null) {
    sender.send(address, report);
}
~~~

This method expresses that the dependency may not exist. If no matching candidate exists, the result is `null`. If multiple candidates exist and Spring cannot identify a single matching bean, the call can still throw `NoUniqueBeanDefinitionException`.

You can provide a fallback supplier:

~~~java
EmailSender sender = emailSenders.getIfAvailable(
        () -> EmailSender.disabled()
);
~~~

The supplier is invoked only when no matching bean exists. The example assumes `EmailSender.disabled()` is an application-defined factory method. This fallback value **is not automatically registered as a Spring bean**; it is simply the value returned to the caller.

### 3.3. `getIfUnique()` — Retrieve only if a unique candidate exists

~~~java
PaymentGateway gateway = gateways.getIfUnique();
if (gateway == null) {
    // No candidate exists or no single unique candidate can be determined.
}
~~~

This method is useful when the application accepts having no default choice. If one candidate is uniquely determined by Spring's dependency resolution rules, the provider returns that bean; if no candidates exist or multiple equal candidates make selection ambiguous, the result is `null`.

You can pass a default supplier:

~~~java
PaymentGateway gateway = gateways.getIfUnique(
        () -> PaymentGateway.manualReview()
);
~~~

When multiple implementations exist without a unique winner, the supplier can provide a fallback policy. This example assumes the interface defines the corresponding static factory method.

### 3.4. `ifAvailable(...)` and `ifUnique(...)` — Perform conditional actions

Instead of retrieving the bean and checking for null yourself:

~~~java
EmailSender sender = emailSenders.getIfAvailable();
if (sender != null) {
    sender.send(address, report);
}
~~~

you can write:

~~~java
emailSenders.ifAvailable(
        sender -> sender.send(address, report)
);
~~~

Similarly:

~~~java
gateways.ifUnique(
        gateway -> gateway.authorize(payment)
);
~~~

The consumer callback runs only when the provider finds a bean meeting the respective condition. These methods express optional behavior cleanly, especially for short callbacks.

Note: if multiple unresolvable candidates exist, `ifAvailable` does not mean "pick any random bean"; it can still throw a non-unique error. `ifUnique` fits when you want to skip the action if there is no single clear choice.

## 4. Comparing getObject, getIfAvailable, and getIfUnique

| Method | No bean exists | One matching bean exists | Multiple unresolvable beans |
|---|---|---|---|
| `getObject()` | Throws not-found exception | Returns bean | Throws non-unique exception |
| `getIfAvailable()` | Returns `null` | Returns bean | Can throw non-unique exception |
| `getIfUnique()` | Returns `null` | Returns bean | Returns `null` if no unique candidate |

In all three cases, Spring's bean selection rules still apply, including qualifiers and prioritized candidates. Thus, "multiple beans of the same type" is not always an unresolvable situation: `@Primary` or qualifiers can help identify the candidate.

Choose the method based on business policy:

- Bean is required: `getObject()`.
- Skip or handle optionally when absent: `getIfAvailable()`.
- Proceed only when a clear unique choice exists: `getIfUnique()`.

## 5. Retrieving Multiple Candidates with stream and orderedStream

When multiple implementations of the same type exist and the application needs to inspect all of them, do not call `getObject()` hoping Spring picks one at random. `ObjectProvider` provides two ways to iterate:

- `stream()`: streams all bean instances matching the provider's type and qualifiers.
- `orderedStream()`: streams matching beans ordered according to Spring's `Ordered` rules.

Example:

~~~java
import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ExportCoordinator {
    private final ObjectProvider<ReportExporter> exporters;

    public ExportCoordinator(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public List<String> supportedFormats() {
        return exporters.orderedStream()
                .map(ReportExporter::format)
                .toList();
    }
}
~~~

Suppose the implementations are:

~~~java
public interface ReportExporter {
    String format();
    byte[] export(Report report);
}
~~~

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
class PdfReportExporter implements ReportExporter {
    public String format() {
        return "pdf";
    }

    public byte[] export(Report report) {
        return new byte[0];
    }
}
~~~

~~~java
@Component
@Order(20)
class CsvReportExporter implements ReportExporter {
    public String format() {
        return "csv";
    }

    public byte[] export(Report report) {
        return new byte[0];
    }
}
~~~

`orderedStream()` sorts according to Spring's ordering rules, which may come from `Ordered`, `@Order`, or compatible ordering metadata. In this example, PDF comes before CSV. If using `stream()`, do not rely on iteration order to represent business priority.

### 5.1. Selecting an implementation based on business input

A provider can supply the set of candidates, and the service then selects based on request data:

~~~java
@Service
public class ExportCoordinator {
    private final ObjectProvider<ReportExporter> exporters;

    public ExportCoordinator(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public byte[] export(Report report, String requestedFormat) {
        ReportExporter exporter = exporters.orderedStream()
                .filter(candidate ->
                        candidate.format().equalsIgnoreCase(requestedFormat))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unsupported format: " + requestedFormat));

        return exporter.export(report);
    }
}
~~~

In this example, the service iterates over exporters and selects the implementation matching the format requested by the user. If multiple exporters declare the same format, Spring's ordering determines the first candidate; if that is not the desired policy, check for duplicate formats and report a configuration error instead of silently picking one implementation.

`stream()` and `orderedStream()` can instantiate bean instances as the stream is traversed, depending on scope and bean state. They are not purely metadata queries.

## 6. Combining ObjectProvider with @Qualifier

Suppose two beans implement `PaymentGateway`:

~~~java
public interface PaymentGateway {
    String providerName();
    void charge(long amount);
}
~~~

~~~java
@Component("cardGateway")
class CardPaymentGateway implements PaymentGateway {
    public String providerName() {
        return "card";
    }

    public void charge(long amount) {
        // Call card payment gateway.
    }
}
~~~

~~~java
@Component("bankGateway")
class BankPaymentGateway implements PaymentGateway {
    public String providerName() {
        return "bank";
    }

    public void charge(long amount) {
        // Call bank payment gateway.
    }
}
~~~

If a service is only allowed to use the card gateway, you can constrain the provider right at the injection point:

~~~java
@Service
public class CardCheckoutService {
    private final ObjectProvider<PaymentGateway> cardGateways;

    public CardCheckoutService(
            @Qualifier("cardGateway")
            ObjectProvider<PaymentGateway> cardGateways) {
        this.cardGateways = cardGateways;
    }

    public void checkout(long amount) {
        cardGateways.getObject().charge(amount);
    }
}
~~~

`@Qualifier("cardGateway")` applies to the provider's dependency resolution, so lookups through the provider honor that qualifier. If the bean does not exist, `getObject()` still throws an error; if optionality is intended, consider `getIfAvailable()`.

A qualifier can also be a custom annotation rather than a bean name string. This is useful when classifying beans by role such as "primary region," "external provider," or "read-only repository," while bean names remain technical identifiers.

## 7. ObjectProvider and @Primary When Multiple Beans Exist

`@Primary` marks a bean as the preferred candidate when Spring needs to pick one typed dependency and multiple matching candidates exist:

~~~java
@Primary
@Component("defaultGateway")
class DefaultPaymentGateway implements PaymentGateway {
    // ...
}
~~~

If the provider has no specific qualifier, `getObject()` or `getIfAvailable()` can resolve to the primary candidate per dependency resolution rules. `getIfUnique()` can also return the candidate considered unique under those rules.

However, `@Primary` **does not remove the remaining beans from the container**. When calling `stream()` or `orderedStream()`, the provider still returns all matching candidates, including non-primary beans. Primary helps choose a single dependency; it is not a filter for lists.

If the application has multiple implementations and the choice depends on request, tenant, document type, or business state, using `stream()` to select by explicit rules is usually better than relying on a fixed primary bean.

## 8. ObjectProvider and Bean Scope

`ObjectProvider` defers lookup, yet **the target bean's scope still determines which instance is returned**.

### 8.1. Singleton

Singleton is the default scope. If `ReportExporter` is a singleton, multiple calls:

~~~java
ReportExporter first = exporters.getObject();
ReportExporter second = exporters.getObject();
~~~

usually return the exact same singleton instance (within the same bean factory/context).

### 8.2. Prototype

If the target bean is a prototype:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class TemporaryReportBuilder {
    // State used only for a single report build.
}
~~~

A singleton bean can inject `ObjectProvider<TemporaryReportBuilder>` and call `getObject()` each time it needs a new builder:

~~~java
@Service
class ReportJobService {
    private final ObjectProvider<TemporaryReportBuilder> builders;

    ReportJobService(
            ObjectProvider<TemporaryReportBuilder> builders) {
        this.builders = builders;
    }

    void createReport() {
        TemporaryReportBuilder builder = builders.getObject();
        // Use builder for this execution.
    }
}
~~~

Each prototype lookup normally produces a new instance. This is an important use case for providers: if a prototype is injected directly into a singleton, the dependency is resolved when the singleton is created and the singleton retains that single instance; a provider lets you request a prototype instance per invocation.

Spring does not manage the full destruction lifecycle of prototypes the way it does for singletons. If a prototype holds resources that must be closed, your code is responsible for releasing them appropriately.

### 8.3. Request/session scope and other scopes

For request- or session-scoped beans, a provider can defer lookup until the operation occurs within the corresponding scope. However, that scope must be active. Calling the provider from a background thread with no request context, for example, can result in a scope-not-active error.

A provider does not create a request context on its own and does not turn a request-scoped bean into a singleton. Always understand the target bean's scope and where the provider is invoked.

## 9. Distinguishing ObjectProvider from Optional, ObjectFactory, @Lazy, and Collection Injection

These tools solve related needs but differ in resolution timing and flexibility.

| Mechanism | Primary purpose | When dependency is obtained |
|---|---|---|
| Direct injection `T` | Required dependency | When creating the consuming bean |
| `Optional<T>` | Dependency may be absent | When Spring resolves the injection point |
| `ObjectFactory<T>` | Simple factory/lookup to retrieve an object | When calling `getObject()` |
| `ObjectProvider<T>` | Flexible lookup: required, optional, unique, multiple candidates | When calling a provider method |
| `@Lazy` on dependency | Defer initialization/lookup via a proxy | When the proxy is first used |
| Inject `List<T>` or `Map<String,T>` | Receive all matching candidates | When creating the consuming bean |

### 9.1. `Optional<T>`

~~~java
public ReportService(Optional<EmailSender> emailSender) {
    this.emailSender = emailSender.orElse(null);
}
~~~

`Optional` explicitly states the presence/absence of a dependency at initialization time. It fits when the application decides once when creating the bean. However, it does not provide an API to re-query on demand, iterate multiple candidates, or pass factory arguments like `ObjectProvider`.

### 9.2. `ObjectFactory<T>`

~~~java
public ReportService(ObjectFactory<ReportExporter> exporters) {
    this.exporters = exporters;
}
~~~

`ObjectFactory<T>` is a simpler abstraction primarily providing `getObject()`. Use it when you only need to defer lookup. If you need `getIfAvailable`, `getIfUnique`, or streaming candidates, `ObjectProvider` is more suitable.

### 9.3. `@Lazy`

~~~java
public ReportService(@Lazy ReportExporter exporter) {
    this.exporter = exporter;
}
~~~

`@Lazy` at an injection point typically causes Spring to supply a proxy that defers resolving the target until the proxy is used. It helps keep the direct dependency API, yet does not offer the same selection/optional/multi-bean operations as a provider. Using a proxy also has implications for object identity, delayed error reporting, and scope interactions.

### 9.4. Collection injection

~~~java
public ExportCoordinator(List<ReportExporter> exporters) {
    this.exporters = exporters;
}
~~~

Collection injection fits when the bean needs **the entire list of candidates immediately upon creation**. If you only need the list when a user triggers an operation or want to avoid creating/initializing dependencies until needed, a provider stream may be a better fit.

## 10. Complete Example: Choosing a Plugin by Request Type

Suppose an application has multiple file processors:

~~~java
public interface DocumentProcessor {
    boolean supports(String extension);
    void process(byte[] content);
}
~~~

Registered implementations:

~~~java
@Component
@Order(10)
class PdfProcessor implements DocumentProcessor {
    public boolean supports(String extension) {
        return "pdf".equalsIgnoreCase(extension);
    }

    public void process(byte[] content) {
        // Process PDF.
    }
}
~~~

~~~java
@Component
@Order(20)
class CsvProcessor implements DocumentProcessor {
    public boolean supports(String extension) {
        return "csv".equalsIgnoreCase(extension);
    }

    public void process(byte[] content) {
        // Process CSV.
    }
}
~~~

The service does not need to know all implementations upfront:

~~~java
@Service
public class DocumentProcessingService {
    private final ObjectProvider<DocumentProcessor> processors;

    public DocumentProcessingService(
            ObjectProvider<DocumentProcessor> processors) {
        this.processors = processors;
    }

    public void process(String extension, byte[] content) {
        DocumentProcessor processor = processors.orderedStream()
                .filter(candidate -> candidate.supports(extension))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "No processor for: " + extension));

        processor.process(content);
    }
}
~~~

When a new Spring-discovered implementation is added, the service can use it without changing its constructor or a static dependency list. This is a simple way to build a **plugin-style architecture** using Spring beans.

In applications requiring high determinism, check for both zero matching processors and multiple processors claiming the same extension. You can require exactly one processor per extension or define explicit priority rules. Never let accidental registration order drive business behavior.

## 11. Things to Keep in Mind When Using ObjectProvider

**A provider does not make a dependency optional from a business standpoint.** If code calls `getObject()` when the bean does not exist, an error still occurs. Decide explicitly whether to fall back, skip, or report an error to the user.

**A provider does not create new instances by itself.** Singletons remain singletons; to get a new instance per call, the target bean needs an appropriate scope like prototype.

**A provider does not turn blocking operations into non-blocking ones.** If the target bean invokes JDBC/JPA or performs synchronous I/O, calling it through a provider is still blocking.

**A provider does not guarantee selecting beans by arbitrary names.** Use qualifiers, primary, or stream filtering logic to express selection criteria.

**Avoid overusing it as a service locator.** If a class takes a dozen providers and looks up all kinds of beans itself, dependency relationships become hard to see and test. Use providers for dependencies that genuinely need deferred lookup, optionality, or multiple candidates; core dependencies should still be injected directly.

**Watch out for late-surfacing errors.** A missing dependency might not fail context startup if the provider has not yet been called. Test code paths that invoke the provider, especially across different profiles or deployment configurations.

**Mind scopes and resources.** Prototype or request-scoped beans have specific lifecycle requirements. Obtaining a bean does not mean all resources it holds are automatically released.

## 12. Testing and Verifying Code That Uses ObjectProvider

When testing a service that uses a provider, cover the lookup policy rather than merely checking that the constructor runs.

For example, a Spring context test can verify the case where the provider has no optional bean:

~~~java
@Configuration
class OptionalSenderTestConfiguration {
    @Bean
    ReportService reportService(ObjectProvider<EmailSender> senders) {
        return new ReportService(senders);
    }
}
~~~

If the application needs to confirm multiple implementations are discovered, you can start a context with test beans and assert `orderedStream()` returns the expected candidates. When testing plugin selection logic, test all of:

- Exactly one implementation supports the requested format.
- No implementation supports it.
- Multiple implementations support it and duplicate-handling policy is enforced.
- Qualifiers or primary work when selecting a single bean.
- Provider accessing a prototype produces instances according to the expected scope.

In plain unit tests, you can mock `ObjectProvider<T>` to verify which method the service calls. However, mocks do not prove that the Spring container actually resolves beans according to qualifiers, primary, and scopes as expected. Those rules require at least one integration test with an application context.

When diagnosing runtime errors, distinguish:

| Symptom | Cause to investigate |
|---|---|
| `NoSuchBeanDefinitionException` from `getObject()` | No matching bean exists, bean excluded by profile/condition, or package not scanned |
| `NoUniqueBeanDefinitionException` | Multiple candidates not resolved by qualifier/primary |
| Provider returns `null` | Using `getIfAvailable`/`getIfUnique` and no candidate meets the condition |
| Fetching a prototype still returns old state | Target bean may still be singleton, or code cached the retrieved instance |
| Request-scoped bean reports scope inactive | Lookup happened outside a valid request/session context |

## 13. Choosing the Right API for Each Scenario

| Need | Suitable choice |
|---|---|
| Bean is mandatory and needed immediately | Inject `T` directly |
| Bean may not exist; only need to decide at initialization | `Optional<T>` |
| Bean may not exist; only check when performing an operation | `ObjectProvider<T>.getIfAvailable()` |
| Must obtain a bean at runtime | `ObjectProvider<T>.getObject()` |
| Proceed only if one clear candidate exists | `ObjectProvider<T>.getIfUnique()` |
| Iterate over multiple implementations | `stream()` or `orderedStream()` |
| Only need to defer a simple factory lookup | `ObjectFactory<T>` |
| Want a lazy proxy for a single dependency | `@Lazy` |
| Need all implementations immediately when creating the bean | Inject `List<T>`/`Map<String,T>` |

In a Spring Boot application, `ObjectProvider` is especially useful when building extensible modules, profile-based optional integrations, strategy plugins, or working with prototype beans from a singleton. Use the right method for the business semantics: `getObject()` for required dependencies, `getIfAvailable()` for optional dependencies, `getIfUnique()` for unambiguous selection, and `orderedStream()` when inspecting multiple implementations in Spring's order.

Once you understand that a provider is simply a **controlled bean lookup gateway**, you can organize dependencies flexibly while keeping object creation, scopes, qualifiers, and bean lifecycles managed by the Spring container.
