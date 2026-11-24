# BeanCreationException Caused by Constructor, Init, or Dependency Failures

When Spring Boot starts, the Spring container creates beans following the dependency graph and executes multiple lifecycle steps. If a bean cannot be instantiated, a dependency cannot be resolved, or an initialization callback throws an exception, bean creation can fail with `BeanCreationException` or a related specialized exception.

The message at the top of the stack trace usually only states **which bean could not be created**. The actual cause often lies deeper:

- The constructor threw an exception while validating configuration or opening a resource.
- Constructor injection could not find a matching bean.
- Multiple beans of the same type exist without selecting which bean to use.
- Another dependency failed inside its constructor or init callback.
- `@PostConstruct`, `afterPropertiesSet()`, or a custom init method threw an exception.
- A property could not be converted to the target bound type.
- The bean depends on an inactive configuration/profile.
- An unresolvable dependency cycle exists.
- A `@Bean` factory method returned `null`, threw an exception, or created an invalid object.

To resolve it properly, do not stop at the line `Error creating bean with name ...`. Trace the **exception chain down to the root cause**, identify the first failing bean, and pinpoint the lifecycle phase where the error occurred.

## 1. What Does `BeanCreationException` Indicate?

`BeanCreationException` is a Spring BeanFactory exception indicating the container could not create or configure a requested bean.

Illustrative message:

```text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService':
Injection of autowired dependencies failed
```

This message states that `orderService` failed while Spring processed dependency injection. However, it does not yet say which specific dependency broke or why.

A stack trace might continue:

```text
BeanCreationException: Error creating bean with name 'orderService'
  ...
Caused by: UnsatisfiedDependencyException:
  Error creating bean with name 'paymentGateway'
  ...
Caused by: BeanCreationException:
  Error creating bean with name 'paymentClient'
  ...
Caused by: IllegalStateException:
  Missing endpoint configuration
```

In this example, `orderService` is simply the first bean the container reported at one layer. The meaningful root cause lies in `paymentClient` and ultimately `Missing endpoint configuration`.

### 1.1. Outer Exceptions vs. Inner Causes

| Exception | Common Meaning |
| --- | --- |
| `BeanCreationException` | A bean could not be created or initialized |
| `UnsatisfiedDependencyException` | A bean's dependency could not be satisfied |
| `BeanInstantiationException` | Spring could not instantiate the class or invoke the factory method as requested |
| `NoSuchBeanDefinitionException` | No matching bean available to resolve |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist without identifying a single unique bean |
| `BeanCurrentlyInCreationException` | A bean currently under creation was requested in an unresolvable way, usually a circular dependency |
| `BeanDefinitionStoreException` | Problem reading, parsing, or registering bean definitions |
| `BeanNotOfRequiredTypeException` | A bean was found, yet the object does not match the required type |
| `BindException` / `ConfigurationPropertiesBindException` | Property binding failed |

Some of the exceptions above may appear inside the cause chain of `BeanCreationException`; others may appear directly at a higher level depending on timing and code path.

### 1.2. Do Not Search Only for `BeanCreationException`

When debugging, read:

1. The first bean name Spring reports failing to create.
2. The message describing the failing phase or operation.
3. Subsequent `Caused by` entries.
4. The deepest exception carrying a concrete technical reason.
5. The first stack trace line belonging to your application package or a library you control.

The root cause is not always the deepest exception by count. Some lower exceptions are merely technical wrappers; pick the exception explaining **why the operation failed**.

## 2. Bean Lifecycle: Where Can Failures Occur?

A typical singleton bean goes through these general steps:

```text
BeanDefinition registered
          |
          v
Resolve constructor and dependencies
          |
          v
Instantiate object (invoke constructor)
          |
          v
Populate properties / field / setter injection
          |
          v
Aware callbacks
          |
          v
BeanPostProcessor: before initialization
          |
          v
Initialization callbacks
  - @PostConstruct
  - InitializingBean.afterPropertiesSet()
  - custom init method
          |
          v
BeanPostProcessor: after initialization
          |
          v
Expose bean reference to clients
```

This is a general model for an ordinary bean. Factory beans, lazy initialization, proxy creators, early references, scoped beans, and extension points can complicate details.

### 2.1. Failure Before Constructor Runs

With constructor injection, Spring must resolve dependencies before invoking the constructor of the bean being created.

```java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

If no matching `PaymentGateway` bean exists, Spring cannot invoke `OrderService`'s constructor because it cannot supply the argument.

### 2.2. Failure Inside Constructor

```java
@Service
public class PaymentGateway {

    public PaymentGateway() {
        throw new IllegalStateException("Cannot initialize gateway");
    }
}
```

Spring instantiates the class, yet the constructor throws an exception. The bean cannot be created successfully.

### 2.3. Failure After Constructor

```java
@Component
public class SearchIndexClient {

    @PostConstruct
    void initialize() {
        throw new IllegalStateException("Index is unavailable");
    }
}
```

The constructor completes successfully, yet the `@PostConstruct` callback fails. Spring does not treat the bean as successfully initialized.

### 2.4. Failure Inside a BeanPostProcessor

A `BeanPostProcessor` processes beans before or after initialization. If the processor's logic throws an exception, bean creation also fails.

When the stack trace leads to a custom post-processor, check:

- Which beans does the processor apply to?
- Does it make wrong assumptions about runtime types?
- Does it request dependencies too early?
- Does it handle proxies or factory beans properly?

## 3. Constructor Failures Caused by Internal Code

Constructors should primarily accept dependencies and set initial state. Operations with side effects, network dependencies, or potentially long waits generally do not belong directly in constructors.

### 3.1. Example: Constructor Opening a Remote Connection

```java
@Component
public class PartnerClient {

    private final PartnerConnection connection;

    public PartnerClient() {
        this.connection = PartnerConnection.connect(
                "https://partner.example.test"
        );
    }
}
```

If the partner is unreachable, the constructor throws an exception. Consequently, the application context fails to complete startup.

### 3.2. Constructors Doing Too Much

A constructor like the following is hard to diagnose:

```java
public ReportService(
        DataSource dataSource,
        HttpClient httpClient,
        Clock clock) {

    this.dataSource = dataSource;
    this.httpClient = httpClient;
    this.clock = clock;

    validateRemoteAccount();
    preloadAllReports();
    startBackgroundPolling();
}
```

It simultaneously accepts dependencies, makes network calls, queries large datasets, and starts background work. Any single failure turns into a bean creation error.

Separate responsibilities:

- Constructors only store dependencies.
- Static configuration and validation happen through typed configuration.
- Mandatory warm-up lives in a dedicated lifecycle step with timeouts and a readiness policy.
- Background jobs use Spring-managed executors/workers.
- Resources are closed via proper destroy lifecycle hooks.

### 3.3. Keep Constructors Simple

```java
@Service
public class ReportService {

    private final ReportRepository repository;
    private final PartnerClient partnerClient;

    public ReportService(
            ReportRepository repository,
            PartnerClient partnerClient) {
        this.repository = repository;
        this.partnerClient = partnerClient;
    }
}
```

Constructor injection makes dependencies explicit and allows `final` fields. Business checks or remote operations can run in dedicated methods with proper error handling.

### 3.4. When Must Startup Verify Remote Dependencies?

Some applications must verify database/schema or infrastructure services before accepting traffic. Warm-up/validation can occur in a startup lifecycle step, provided you define:

- Timeouts for network/database calls.
- Contextual failure messages without secrets.
- Clear decisions on which errors must fail startup.
- Clear decisions on which errors should only cause readiness to reject traffic.
- No infinite retries during startup.

Not every optional dependency should prevent the entire application from starting.

## 4. Dependency Injection Failures

Constructor injection makes dependency graphs readable:

```java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

If Spring cannot find a matching bean, startup fails before `CheckoutService` is instantiated.

### 4.1. No Matching Bean

Example:

```java
public interface PaymentGateway {
    void charge(String orderId);
}
```

Without a registered implementation:

```java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway paymentGateway) {
    }
}
```

Spring reports:

```text
No qualifying bean of type 'PaymentGateway' available
```

Check:

- Was an implementation created?
- Is its package covered by component scanning?
- Does the class carry the right stereotype annotation?
- Is the `@Bean` factory method in a loaded configuration?
- Did a profile/condition exclude the bean unintentionally?
- Is a runtime module/dependency missing?

### 4.2. Component Scan Does Not Cover the Package

Example:

```text
com.example.app
  ├── Application.java
  └── order
      └── OrderService.java

com.example.payment
  └── PaymentGatewayImpl.java
```

If `Application.java` uses `@SpringBootApplication` in `com.example.app`, default component scanning covers that package and its subpackages. `com.example.payment` is a sibling package and is not scanned.

Intentional fix:

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.app",
        "com.example.payment"
    }
)
public class Application {
}
```

Or place the application class in a root package matching the module layout.

Do not broaden component scanning across every library package indiscriminately; that can register unintended beans.

### 4.3. Conditional Bean Was Not Created

```java
@Configuration
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
        name = "payment.provider",
        havingValue = "partner"
    )
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

If `payment.provider` does not equal `partner`, this bean is not registered.

A service constructor requiring `PaymentGateway` will fail unless an alternative bean exists.

Check:

- Was the property actually loaded?
- Did another config source override it?
- Do the condition's key name and value match?
- Is there a default implementation for this environment?

### 4.4. Profile Not Activated

```java
@Service
@Profile("production")
public class ProductionPaymentGateway implements PaymentGateway {
}
```

If the app runs without the `production` profile, this bean is not registered.

A mandatory dependency on `PaymentGateway` therefore remains unsatisfied.

Run:

```bash
java -jar app.jar --spring.profiles.active=production
```

or configure the profile via the environment's appropriate source.

Do not change a dependency to optional just to mask a misconfigured production profile.

## 5. Multiple Beans of the Same Type

Another error:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
```

Example:

```java
@Service
public class CardPaymentGateway implements PaymentGateway {
}
```

```java
@Service
public class WalletPaymentGateway implements PaymentGateway {
}
```

Client:

```java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway gateway) {
    }
}
```

Spring finds two matching candidates and cannot pick one.

### 5.1. Using `@Qualifier`

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("cardPaymentGateway")
            PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Default qualifier names often derive from the bean name, typically camelCase class name when registered by component scanning.

### 5.2. Using `@Primary`

```java
@Service
@Primary
public class CardPaymentGateway implements PaymentGateway {
}
```

`@Primary` marks a preferred bean when resolving a single dependency by type with multiple candidates.

### 5.3. Selecting Beans by Business Rules

If gateway choice depends on request data, do not inject one bean expecting `@Primary` to cover every case.

Inject multiple implementations:

```java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentGateway gatewayFor(String provider) {
        PaymentGateway gateway = gateways.get(provider);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment provider"
            );
        }
        return gateway;
    }
}
```

In production code, use normalized provider keys and proper error handling. Never pass unvalidated raw user input directly as a bean name.

## 6. Failures in `@PostConstruct`

`@PostConstruct` marks an initialization method called after dependency injection completes and before the bean is considered ready.

### 6.1. Example of a Failing Init Method

```java
@Component
public class CurrencyCatalog {

    @PostConstruct
    void load() {
        if (!catalogFileExists()) {
            throw new IllegalStateException(
                    "Currency catalog is missing"
            );
        }
    }

    private boolean catalogFileExists() {
        return false;
    }
}
```

If the callback throws an exception, Spring cannot finish creating `currencyCatalog`.

Other beans depending on it also fail in a chain.

### 6.2. Why Does One Bean's Exception Break Multiple Beans?

Suppose:

```text
CheckoutController
       |
       v
CheckoutService
       |
       v
CurrencyCatalog
       |
       v
@PostConstruct throws
```

Spring reports the error on `CurrencyCatalog`, and dependent beans like `CheckoutService` or the controller cannot be created either. Stack traces may have multiple wrappers; locate the first failing bean instead of editing every upstream bean one by one.

### 6.3. Do Not Use `@PostConstruct` for Long or Unbounded Work

Avoid:

```java
@PostConstruct
void initialize() {
    while (true) {
        pollPartner();
    }
}
```

The context can never finish refreshing because the method never returns.

`@PostConstruct` fits brief, synchronous, bounded initialization tied directly to the bean's own state.

If long-running work is needed:

- Use a runner or well-designed lifecycle component.
- Enforce timeouts.
- Update readiness if the instance cannot serve yet.
- Keep background workers out of constructors/init callbacks.

### 6.4. Do Not Assume All Dependencies Are Ready for Everything

Inside `@PostConstruct`, dependencies have been injected, yet other components may not have finished their lifecycle as expected. Do not call back into another bean to trigger system-wide workflows while the context is still initializing.

Avoid circular dependencies across initialization callbacks.

## 7. `InitializingBean.afterPropertiesSet()`

Spring supports the interface:

```java
org.springframework.beans.factory.InitializingBean
```

Example:

```java
@Component
public class SearchClient implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Validate internal state after properties are injected
    }
}
```

If `afterPropertiesSet()` throws an exception, bean initialization fails.

### 7.1. Comparing the Three Init Mechanisms

| Mechanism | Declaration | When Suitable |
| --- | --- | --- |
| `@PostConstruct` | Method annotation | Brief callback tied to the bean |
| `InitializingBean` | Implement `afterPropertiesSet()` | Classes accepting Spring lifecycle API coupling |
| Custom init method | `@Bean(initMethod = "initialize")` | External classes or declaring lifecycle in configuration |

### 7.2. Custom Init Method

```java
@Configuration(proxyBeanMethods = false)
public class SearchConfiguration {

    @Bean(initMethod = "initialize", destroyMethod = "close")
    public SearchClient searchClient() {
        return new SearchClient();
    }
}
```

`SearchClient` here is a hypothetical class with `initialize()` and `close()`.

If `initialize()` throws an exception, the bean fails creation and context refresh aborts.

### 7.3. Order of Initialization Callbacks

In the standard bean lifecycle, Spring invokes supported init callbacks in order:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Declared custom init method.

BeanPostProcessors wrap these steps with before/after initialization callbacks.

Avoid defining the same cleanup/init operation in multiple hooks unnecessarily. Repeated initialization can create duplicate connections or threads.

## 8. Property Binding and Invalid Configuration Types

A bean can fail when Spring binds configuration.

Example:

```java
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        int retryCount
) {
}
```

With config:

```yaml
payment:
  endpoint: "not-a-valid-uri"
  timeout: "many seconds"
  retry-count: "three"
```

Spring cannot convert some values to the target types. Depending on where binding occurs, you may see `BindException`, `ConfigurationPropertiesBindException`, or an exception wrapped inside bean creation errors.

### 8.1. Checking Values and Data Types

Valid example:

```yaml
payment:
  endpoint: "https://payments.example.test"
  timeout: 5s
  retry-count: 3
```

Spring Boot supports conversion for many common types such as `Duration`, `DataSize`, `URI`, and scalar types.

### 8.2. Enabling Validation on Configuration Properties

```java
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(0) @Max(5) int retryCount
) {
}
```

This example requires the validation dependency and imports `jakarta.validation.constraints.*`, `org.springframework.validation.annotation.Validated`.

When validation fails, startup fails fast with a clear message instead of waiting until the first request to uncover invalid configuration.

### 8.3. Missing Required Properties

With `@Value`:

```java
@Value("${payment.endpoint}")
private URI endpoint;
```

If the property is absent and has no default, placeholder resolution fails during bean creation.

If the property is mandatory, a clear startup failure is desirable. If optional, express that via a default or an appropriate type.

### 8.4. Do Not Use Defaults to Mask Missing Production Config

Example:

```java
@Value("${payment.endpoint:http://localhost:8080}")
```

A local default can let production start cleanly while calling the wrong endpoint.

Provide defaults only when safe and semantically valid. For mandatory endpoints/secrets, fail fast with a clear message that does not leak secrets.

## 9. `@Bean` Factory Method Failures

Not every bean is created via a `@Component` class constructor. A bean can be produced by a `@Bean` method.

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    public PartnerClient partnerClient(
            PartnerProperties properties) {

        if (properties.endpoint() == null) {
            throw new IllegalStateException(
                    "Partner endpoint is required"
            );
        }

        return PartnerClient.connect(properties.endpoint());
    }
}
```

If the method throws an exception, Spring cannot create the `partnerClient` bean.

### 9.1. Factory Method Depending on Other Beans

```java
@Bean
public ReportService reportService(
        ReportRepository repository,
        Clock clock) {
    return new ReportService(repository, clock);
}
```

If `ReportRepository` or `Clock` fails to resolve, the factory method cannot run.

### 9.2. Do Not Return Null

A normal `@Bean` factory method should return a valid bean instance. Returning `null` causes unintended behavior or leaves clients without an expected bean.

If an optional integration does not exist, use conditions to skip registering the bean, or use an explicit abstraction representing absence. Never return `null` to simulate an optional dependency without a contract.

### 9.3. FactoryBean Has Its Own Lifecycle

`FactoryBean<T>` is Spring's abstraction for a factory creating an object exposed as a bean. If the factory itself or `getObject()` fails, errors surface when Spring creates or retrieves the factory's product.

When a stack trace shows `FactoryBean`, distinguish:

- The factory bean object itself.
- The product object created by the factory.
- When the product is created (eager/lazy).

Do not assume the factory class is the object clients receive.

## 10. Circular Dependencies

A frustrating bean creation error is a dependency cycle:

```text
OrderService -> PaymentService -> OrderService
```

Example:

```java
@Service
public class OrderService {

    public OrderService(PaymentService paymentService) {
    }
}
```

```java
@Service
public class PaymentService {

    public PaymentService(OrderService orderService) {
    }
}
```

To create `OrderService`, Spring needs `PaymentService`; to create `PaymentService`, Spring needs the half-created `OrderService`.

### 10.1. Constructor Cycles Are Usually Unresolvable

With pure constructor injection, Spring cannot construct the first object because neither has a completed instance to supply to the other's constructor.

The error appears as:

```text
BeanCurrentlyInCreationException
```

or a circular reference message during startup failure.

### 10.2. Setter/Field Cycles May Work in Some Setups

Spring Framework has an early singleton reference mechanism for certain circular dependencies between singleton beans not involving constructor cycles. However, this depends on bean types, proxies/post-processors, and configuration.

Spring Boot 2.6+ disallows circular references by default in new application setups unless re-enabled via the corresponding property.

Do not rely on enabling circular references as a long-term architectural fix.

### 10.3. Redesign to Eliminate the Cycle

Replace:

```text
OrderService <----> PaymentService
```

with an orchestrating component:

```text
OrderWorkflow
   |       |
   v       v
OrderService  PaymentService
```

Example:

```java
@Service
public class OrderWorkflow {

    private final OrderService orders;
    private final PaymentService payments;

    public OrderWorkflow(
            OrderService orders,
            PaymentService payments) {
        this.orders = orders;
        this.payments = payments;
    }

    public void checkout(String orderId) {
        orders.validate(orderId);
        payments.charge(orderId);
        orders.markPaid(orderId);
    }
}
```

The two services no longer depend on each other. The orchestrator makes the use-case sequence explicit.

### 10.4. `@Lazy` Defers Resolution Without Fixing Design

```java
public PaymentService(@Lazy OrderService orderService) {
    this.orderService = orderService;
}
```

`@Lazy` at an injection point creates a proxy/lazy reference and can break initialization cycles in some cases.

Yet it may merely delay the error until the first method call, or leave the underlying business dependency cycle intact.

Use it only when lazy resolution is an intentional part of the design, not as a blanket dodge for circular dependencies.

## 11. Optional Dependencies: Distinguishing True Optionality from Mandatory Dependencies

When an integration is genuinely optional, there are clean ways to express optionality.

### 11.1. `ObjectProvider<T>`

```java
@Service
public class NotificationService {

    private final ObjectProvider<PushGateway> pushGatewayProvider;

    public NotificationService(
            ObjectProvider<PushGateway> pushGatewayProvider) {
        this.pushGatewayProvider = pushGatewayProvider;
    }

    public void notifyUser(String userRef) {
        PushGateway gateway =
                pushGatewayProvider.getIfAvailable();

        if (gateway != null) {
            gateway.send(userRef);
        }
    }
}
```

`ObjectProvider` resolves dependencies at usage time and handles absent beans via clear APIs.

If multiple beans exist without a selection rule, certain resolution methods still throw ambiguity errors.

### 11.2. `Optional<T>`

```java
public NotificationService(Optional<PushGateway> pushGateway) {
    this.pushGateway = pushGateway;
}
```

This expresses a potentially absent dependency in Spring-supported contexts.

### 11.3. `@Autowired(required = false)`

Field or setter injection can be marked optional:

```java
@Autowired(required = false)
public void setPushGateway(PushGateway pushGateway) {
    this.pushGateway = pushGateway;
}
```

However, optional fields leave objects missing collaborators and defer errors until methods execute. Constructor injection with `Optional` or `ObjectProvider` usually states intent more clearly.

### 11.4. Do Not Make Mandatory Dependencies Optional Just to Pass Startup

If the application cannot process checkouts without a payment gateway, that dependency must remain mandatory—or readiness must reject traffic until the gateway is ready.

Never use `getIfAvailable()` to silently skip payments just to avoid `BeanCreationException`.

## 12. Proxy and Post-Processing Failures

Beans may be proxied by Spring AOP or other infrastructure mechanisms. Proxy creation typically happens during bean post-processing.

Common errors:

- Target class cannot be subclassed under a class-based proxy strategy.
- Final classes/methods are incompatible with subclass proxying.
- An advisor or custom `BeanPostProcessor` throws an exception.
- Code depends on a concrete class while the bean is exposed via a JDK proxy.
- A bean is accessed prematurely before proxying finishes.

### 12.1. Final Classes and CGLIB

```java
@Service
public final class PaymentService {
}
```

If configuration requests a class-based proxy for this bean, Spring cannot subclass a final class normally.

Options include removing `final`, defining an interface and using interface proxies, or reviewing AOP requirements.

### 12.2. BeanPostProcessor Accessing Beans Too Early

A custom post-processor should avoid calling `getBean()` arbitrarily while processing bean definitions. Eagerly instantiating beans too early can cause other bean post-processors to miss them or skew lifecycles.

If you see a warning like:

```text
Bean ... is not eligible for getting processed by all BeanPostProcessors
```

inspect how the post-processor and its dependencies are declared and whether beans are being instantiated prematurely.

### 12.3. Do Not Force-Cast Proxies to Implementations

If a bean is exposed via a JDK proxy, code like:

```java
PaymentService service =
        (PaymentService) applicationContext.getBean("paymentService");
```

throws `ClassCastException`.

Inject via business interfaces or adjust proxy strategy appropriately. Never cast as a bean creation workaround.

## 13. Distinguishing Bean Creation Errors from Post-Startup Errors

Not every exception occurring after the application runs is a `BeanCreationException`.

| Stage | Example | Issue Group |
| --- | --- | --- |
| Reading bean definitions | Configuration parsing error | Configuration/definition failure |
| Resolving constructor args | Missing or ambiguous dependency | Dependency resolution |
| Instantiating | Constructor/factory method throws | Bean instantiation |
| Populating properties | Injection/conversion failure | Dependency/property population |
| Init callbacks | `@PostConstruct` throws | Initialization |
| Post-startup request handling | Service method throws | Runtime business failure |
| Closing context | Destroy callback throws | Shutdown/cleanup failure |

### 13.1. Runtime Method Exceptions Do Not Become BeanCreationException

Example:

```java
@Service
public class OrderService {

    public void submit() {
        throw new IllegalStateException("Order rejected");
    }
}
```

If `submit()` is invoked only after context creation succeeds, the exception is a method execution failure, not a bean creation failure.

### 13.2. Lazy Beans Can Delay Creation Errors

With:

```java
@Lazy
@Component
public class ReportEngine {

    public ReportEngine() {
        throw new IllegalStateException("Invalid report engine");
    }
}
```

Spring defers creating the bean until first requested. The application starts cleanly and fails only when the bean is first resolved.

This does not turn a constructor bug into a runtime method error; it simply shifts when bean creation occurs.

### 13.3. Lazy Initialization Can Hide Bugs from Startup Smoke Tests

If a deployment checks only startup logs, uncreated lazy beans can hide constructor/init failures.

If a core bean must be valid before receiving traffic, consider keeping it non-lazy or adding a readiness/warm-up check that proactively resolves and validates required beans.

Do not force every bean to initialize eagerly just to bloat a health check; pick the truly essential components.

## 14. Reading Stack Traces Systematically

When encountering:

```text
Application run failed
  BeanCreationException: Error creating bean with name 'checkoutController'
    UnsatisfiedDependencyException:
      Error creating bean with name 'checkoutService'
        BeanCreationException:
          Error creating bean with name 'paymentGateway'
            IllegalStateException: Missing provider endpoint
```

Proceed as follows:

### Step 1 — Find the Last Exception with a Concrete Message

Here:

```text
IllegalStateException: Missing provider endpoint
```

### Step 2 — Identify the Bean Owning the Failure

Here:

```text
paymentGateway
```

### Step 3 — Identify the Phase

If the stack points to a constructor or factory method, check instantiation. If it points to `@PostConstruct` or `afterPropertiesSet`, check init callbacks.

### Step 4 — Check Data/Configuration Sources

Was the endpoint property loaded? Is the profile right? Are environment variable names right? Did another source override it?

### Step 5 — Check the Dependency Graph

Which beans request `paymentGateway`? Did an earlier bean fail before it?

### Step 6 — Fix the Root Cause

Do not modify `checkoutController` if the controller is merely higher up the dependency chain.

### Step 7 — Rerun a Small Verification Test

Create a minimal context test for the failing configuration/bean, or an appropriate integration test. You do not always need to run the entire system when you can isolate the failure.

## 15. Complete Example: Constructor Fails Due to Missing Property

### 15.1. Interface and Client

```java
public interface PartnerGateway {
    void submit(String operationRef);
}
```

```java
@Component
public class HttpPartnerGateway implements PartnerGateway {

    private final URI endpoint;

    public HttpPartnerGateway(
            @Value("${partner.endpoint}") URI endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public void submit(String operationRef) {
        // Call partner using an appropriate HTTP client
    }
}
```

If `partner.endpoint` is absent from Environment or cannot convert to `URI`, Spring fails when resolving constructor arguments.

### 15.2. Service Depending on Gateway

```java
@Service
public class PartnerSubmissionService {

    private final PartnerGateway gateway;

    public PartnerSubmissionService(PartnerGateway gateway) {
        this.gateway = gateway;
    }
}
```

When the gateway cannot be created, this service fails too. Upstream beans continue failing along the dependency chain.

### 15.3. Proper Configuration

`application.yml`:

```yaml
partner:
  endpoint: "https://partner.example.test/api"
```

Or pass via command line:

```bash
java -jar app.jar --partner.endpoint=https://partner.example.test/api
```

Or via environment variable using relaxed binding:

```text
PARTNER_ENDPOINT=https://partner.example.test/api
```

### 15.4. Do Not Leak Secrets in Errors

If an endpoint URL includes credentials or tokens, never put the raw URI into an exception message:

```java
throw new IllegalStateException(
        "Cannot connect to " + endpoint
);
```

Replace with safe details:

```java
throw new IllegalStateException(
        "Partner endpoint configuration is invalid"
);
```

If diagnostics are needed, log a normalized provider identifier and failure code—never print tokens or URLs containing secrets.

## 16. Complete Example: `@PostConstruct` Fails While Preloading Data

Suppose a service needs a currency lookup table:

```java
@Service
public class CurrencyService {

    private final CurrencyRepository repository;
    private Map<String, Currency> currencies;

    public CurrencyService(CurrencyRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void initialize() {
        currencies = repository.findAll()
                .stream()
                .collect(Collectors.toUnmodifiableMap(
                        Currency::code,
                        Function.identity()
                ));
    }
}
```

Possible causes of init failure:

- Database cannot connect.
- Schema has not been migrated.
- Repository query throws an exception.
- Two currencies share the same code, causing the collector to throw a duplicate key error.
- Mapping returns a null code.
- A huge dataset exceeds memory or startup time limits.

### 16.1. Separate Technical Causes from Preload Logic

If the currency table is mandatory data, clarify:

- Must the entire table be preloaded?
- Can it be queried on demand?
- Should duplicate keys be checked before publishing the map?
- Should startup fail if the dataset is empty?
- Is there an appropriate database timeout?

### 16.2. Avoid Half-Initialized Object State

Do not populate shared fields incrementally before preloading succeeds. Build a local variable first:

```java
@PostConstruct
void initialize() {
    Map<String, Currency> loaded =
            repository.findAll()
                    .stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Currency::code,
                            Function.identity()
                    ));

    this.currencies = loaded;
}
```

Publish the result only after map construction succeeds. If the method throws, the bean is never exposed as a finished instance.

### 16.3. When Should Preloading Be a Runner?

If preloading is a heavy startup step needing progress logs or readiness control, an `ApplicationRunner`/startup coordinator may fit better than `@PostConstruct`.

However, runners execute after context refresh; beans have already been constructed and injected. If the data is required before serving requests, block traffic until the runner finishes and readiness flips cleanly.

## 17. Checking Component Scan and Bean Registration

A missing bean does not necessarily mean its own constructor failed.

### 17.1. `@SpringBootApplication`

This annotation combines several features, including component scanning from the package containing the application class.

Example:

```java
package com.example;

@SpringBootApplication
public class Application {
}
```

Subpackages such as `com.example.order` and `com.example.payment` fall within the default scan scope.

### 17.2. Beans Declared via `@Bean`

```java
@Configuration
public class GatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

If the configuration class is not scanned or imported, the factory method is never registered.

### 17.3. Use `@Import` When Modules Should Register Explicitly

```java
@Configuration
@Import(PaymentConfiguration.class)
public class ApplicationModules {
}
```

This expresses module configuration explicitly.

### 17.4. Investigate Auto-Configuration Conditions

If the bean comes from Spring Boot auto-configuration or a starter:

- Is the starter dependency on the runtime classpath?
- Was the auto-configuration excluded?
- Do property conditions match?
- Did a user bean cause auto-configuration to back off?

Run:

```bash
java -jar app.jar --debug
```

to inspect the Conditions Evaluation Report where applicable. The report explains auto-configuration conditions; it does not replace reading the root cause of `BeanCreationException`.

## 18. Dependency Graph: Finding the First Broken Bean

A failure in a leaf bean can cause many upstream beans to fail.

Example:

```text
OrderController
      |
      v
CheckoutService
   /       \
  v         v
Payment   Inventory
Gateway   Client
  |
  v
PaymentProperties
  |
  v
Invalid endpoint
```

If `PaymentProperties` fails to bind:

- `PaymentGateway` cannot be created.
- `CheckoutService` cannot inject the gateway.
- `OrderController` cannot inject the checkout service.

Spring may report one or more exceptions across layers. Fixing the controller solves nothing.

### 18.1. Identifying the Root Bean

Reading the stack:

```text
Error creating bean with name 'orderController'
  ...
Caused by: Error creating bean with name 'checkoutService'
  ...
Caused by: Error creating bean with name 'paymentGateway'
  ...
Caused by: Failed to bind properties under 'payment.endpoint'
```

Inspect `payment.endpoint` first.

### 18.2. Successful Bean Creation Does Not Guarantee Healthy Runtime Dependencies

A constructor can build an HTTP client object without opening a connection yet. The context starts cleanly, yet the first API call times out.

That is a runtime dependency failure, not a bean creation error. If connectivity must be checked before taking traffic, add a dedicated validation/readiness check.

## 19. Optional Beans and Environment-Specific Conditions

An integration used only in production can be scoped by profile:

```java
@Configuration
@Profile("production")
public class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
```

In tests, supply a fake implementation:

```java
@TestConfiguration
public class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

If profiles and test configurations do not line up, dependencies go missing.

### 19.1. Prevent Test Configurations from Leaking into Production

Never leave test implementations inside packages covered by production component scanning without explicit conditions. Keep `@TestConfiguration` in test sources and import as needed.

### 19.2. Property Conditions

`@ConditionalOnProperty` fits features/integrations toggled via configuration. However, services with mandatory dependencies must align with those condition states.

You can:

- Provide a default implementation.
- Use a genuine optional abstraction.
- Load the dependent service only in profiles providing the gateway.
- Fail startup explicitly when an environment requires the gateway yet config is missing.

## 20. Do Not Hide `BeanCreationException` with Overly Broad Catch Blocks

Avoid:

```java
try {
    SpringApplication.run(Application.class, args);
} catch (Exception ex) {
    System.out.println("Application started");
}
```

This reports success even when context startup failed.

### 20.1. If Custom Exit Behavior Is Needed

```java
public static void main(String[] args) {
    try {
        SpringApplication.run(Application.class, args);
    } catch (Exception ex) {
        // Log an appropriate startup failure message
        throw ex;
    }
}
```

Usually, letting the exception propagate to the launcher/process supervisor preserves proper failure semantics.

If a batch app needs structured exit codes, use `ExitCodeGenerator` or `SpringApplication.exit(...)` after context creation succeeds. Never turn a startup failure into exit code 0.

### 20.2. Do Not Log the Same Stack Trace at Every Layer

Logging and rethrowing the same exception across multiple layers creates duplicate stack traces. Pick one boundary responsible for full error logging; let other layers add safe context or propagate.

## 21. Diagnosing Startup Failures with Spring Boot

### 21.1. Read the Complete Startup Log

Do not copy only the last 3 lines. The initiating failure may appear ahead of trailing wrapper exceptions.

Record:

- Active profiles.
- Bean name.
- Constructor/factory/init method.
- Problematic property key.
- `Caused by` chain.
- First line of application code.

### 21.2. Use `--debug` When Investigating Auto-Configuration

```bash
java -jar app.jar --debug
```

Spring Boot prints the Conditions Evaluation Report showing which auto-configurations matched or did not match.

This is especially helpful when beans originate from starters, conditional configs, or auto-configuration.

### 21.3. Do Not Dump All Property Sources

`Environment` can hold passwords, tokens, or URLs with credentials. Never print the entire `Environment`, `System.getProperties()`, or sensitive config objects just to find one missing property.

Inspect non-sensitive keys safely:

```java
log.info(
        "payment configuration present={}",
        environment.containsProperty("payment.endpoint")
);
```

If logging a value is necessary, log only after confirming it is non-sensitive and permitted in logs.

### 21.4. Actuator Conditions and ConfigProps

In secured environments, Actuator exposes diagnostic endpoints such as:

```text
/actuator/conditions
/actuator/configprops
```

Exact endpoints depend on Actuator version and exposure settings. Never use them to expose configuration publicly to the Internet.

### 21.5. Do Not Use Health Endpoints to Find Startup Root Causes

If the context failed to start, the health endpoint cannot serve like a ready application anyway. Check process logs, exit codes, container events, and startup exceptions.

## 22. Controlled Testing of Bean Creation

When a bean fails at startup, isolate it with a small test context instead of always booting the entire application.

### 22.1. Testing Constructor Injection

```java
class CheckoutServiceTest {

    @Test
    void createsServiceWithPaymentGateway() {
        PaymentGateway gateway = mock(PaymentGateway.class);

        CheckoutService service =
                new CheckoutService(gateway);

        assertThat(service).isNotNull();
    }
}
```

This unit test checks the plain Java constructor. It does not prove Spring component scanning or bean registration works.

### 22.2. Testing a Minimal Spring Context

```java
class PaymentConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PaymentConfiguration.class);

    @Test
    void createsGatewayWhenPropertyIsPresent() {
        contextRunner
                .withPropertyValues(
                        "payment.provider=partner",
                        "payment.endpoint=https://partner.example.test"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                });
    }
}
```

This assumes `PaymentConfiguration` declares the bean using those properties with matching test dependencies.

`ApplicationContextRunner` is great for testing conditional auto-configuration or small bean groups.

### 22.3. Testing Property Binding

Verify:

- Valid values bind cleanly.
- Invalid types fail context startup.
- Validation constraints are enforced.
- Default values apply only where intended.

### 22.4. Testing Init Callbacks

Create a test bean with `@PostConstruct`, pass mock dependencies, and confirm the callback runs inside the context.

If the callback throws, assert the context runner records a failure rather than treating startup as successful.

### 22.5. Testing Circular Dependencies

You do not need a massive integration test. Put two mutually constructor-dependent beans into a small context and assert startup failure. Then extract orchestration into a third bean and verify the context starts cleanly.

## 23. Real-World Scenarios and Resolution Paths

| Symptom | Common Cause | Resolution Path |
| --- | --- | --- |
| `No qualifying bean` | Bean not scanned/imported/conditioned | Check packages, configuration, profiles |
| `expected single matching bean but found 2` | Multiple implementations exist | `@Qualifier`, `@Primary`, or router |
| `BeanInstantiationException` | Constructor/factory method threw | Check cause and instantiation code |
| `Failed to bind properties` | Wrong type or missing property | Check config sources and typed binding |
| `@PostConstruct` failed | Preload/validation/resource error | Split init, timeouts, clarify mandatory data |
| `BeanCurrentlyInCreationException` | Circular dependency | Redesign dependency graph |
| Fails only in `prod` profile | Different profile beans or config sources | Verify active profiles and conditions |
| Fails only when lazy bean is used | Deferred bean creation | Resolve/test critical beans before traffic |
| CGLIB proxy creation fails | Final class/method or type constraint | Review proxy strategy and class design |
| Factory method throws exception | Invalid resource/configuration | Check method and arguments |
| Context fails after `Started ...` log | Post-log runner or lifecycle step failed | Check runner failure and ready event |
| App boots yet first request fails | Lazy dependency or runtime error | Check resolution timing and request trace |

## 24. Workflow for Handling `BeanCreationException`

An actionable workflow:

```text
Application startup failed
          |
          v
Find the first reported bean name
          |
          v
Read the entire Caused by chain
          |
          v
Identify the lifecycle phase
          |
          +--> Constructor / factory method
          |
          +--> Dependency resolution
          |
          +--> Property binding
          |
          +--> Init callback / post-processor
          |
          v
Find the root cause in code/config/dependencies
          |
          v
Fix the actual cause
          |
          v
Write a small reproduction test
          |
          v
Restart and verify context readiness
```

### Step 1 — Gather the Right Error

Capture the full stack trace from the failed startup, including all `Caused by` entries and relevant preceding logs.

### Step 2 — Find the Root Bean

Distinguish the first bean Spring mentioned from the deeper bean that actually failed.

### Step 3 — Classify the Phase

Constructor, dependency resolution, property binding, initialization callback, post-processor, or factory method?

### Step 4 — Check Configuration and Dependency Graph

Check profiles, conditions, component scan, qualifiers, primary markers, and property sources.

### Step 5 — Fix the Root Cause

Do not add `@Lazy`, optional injection, or catch blocks if they merely defer or hide the bug.

### Step 6 — Reproduce in a Small Test

Use unit tests for pure logic, `ApplicationContextRunner` for small configurations, or `@SpringBootTest` for integrations needing the full context.

### Step 7 — Confirm Successful Startup

Verify context refresh, runners, ready events, and health/readiness per deployment requirements. A single `Started ...` log line is not enough if downstream runners can still fail.

## 25. Anti-Patterns to Avoid

### 25.1. Unbounded I/O in Constructors

Constructors making HTTP calls, loading large files, querying whole tables, or blocking on queues make startup unpredictable.

### 25.2. Infinite Workers in `@PostConstruct`

An init method that never returns prevents the context from finishing refresh.

### 25.3. Catching and Ignoring Exceptions

```java
@PostConstruct
void init() {
    try {
        connect();
    } catch (Exception ex) {
        // Ignore
    }
}
```

The bean may be marked initialized despite broken internal state. If recoverable, model degraded state and readiness explicitly; if unusable, fail startup clearly.

### 25.4. Using `@Lazy` to Hide Errors

Lazy initialization only changes when a bean is created. It never fixes broken constructors, properties, or dependencies.

### 25.5. Using `@Autowired(required=false)` for Mandatory Dependencies

This creates objects missing collaborators and triggers `NullPointerException` after startup.

### 25.6. Enabling Circular References to Avoid Refactoring

It may let some setups boot, yet preserves tangled dependency graphs that break easily when proxies/post-processors change.

### 25.7. Printing Full Configuration to Debug

Risks leaking passwords, tokens, and connection strings. Check individual non-sensitive properties safely.

### 25.8. Fixing Upstream Beans Instead of the Root Bean

The controller is not the cause if a downstream payment gateway lacks its endpoint.

## 26. Practice Exercises

### Exercise 1 — Reading an Exception Chain

Given:

```text
BeanCreationException: Error creating bean with name 'orderController'
  Caused by: UnsatisfiedDependencyException:
    Error creating bean with name 'orderService'
      Caused by: BeanCreationException:
        Error creating bean with name 'paymentGateway'
          Caused by: IllegalStateException:
            Missing payment endpoint
```

Identify:

- Which bean is reported outermost first?
- Which bean is the nearest error source?
- What is the root cause?
- Which config or code should be checked?

### Exercise 2 — Missing Constructor Dependency

Create `OrderService` needing `PaymentGateway` without registering an implementation.

Start the context and observe the error. Then add an implementation via `@Component` or `@Bean`.

Explain why the constructor cannot run before dependencies are resolved.

### Exercise 3 — Multiple Beans of the Same Type

Create `CardPaymentGateway` and `WalletPaymentGateway` both implementing `PaymentGateway`.

Inject the interface without a qualifier. Observe the ambiguity error, then try `@Primary` and `@Qualifier`.

### Exercise 4 — Component Scan

Place an implementation in a sibling package outside the application class's package.

Observe `NoSuchBeanDefinitionException`, then fix the package layout or `scanBasePackages`.

### Exercise 5 — Profiles and Conditions

Register one gateway with `@Profile("production")` and one with `@ConditionalOnProperty`.

Run under different profiles/properties. Record which beans exist and when consumer constructors fail to resolve dependencies.

### Exercise 6 — Constructor Throwing an Exception

Create a bean constructor validating an endpoint and throwing if invalid.

Inspect the cause chain. Then move validation to a `@Validated` configuration properties object for clearer startup messages.

### Exercise 7 — `@PostConstruct`

Create a bean loading a data list inside `@PostConstruct`. Have a mock repository throw an exception.

Observe context startup failure. Then explore moving preloading to a runner and readiness gate if loaded asynchronously.

### Exercise 8 — Custom Init Method

Create a class with `initialize()` and declare:

```java
@Bean(initMethod = "initialize")
```

Have the init method throw. Identify which Spring exception wraps it and confirm the bean is not exposed.

### Exercise 9 — `InitializingBean`

Implement `afterPropertiesSet()` and intentionally throw an exception. Compare with `@PostConstruct`.

### Exercise 10 — Invalid Property Binding Types

Create `@ConfigurationProperties` with `Duration`, `URI`, and `int`. Supply invalid values and observe binding exceptions.

Then add validation constraints so config errors fail early.

### Exercise 11 — Circular Constructor Injection

Create `OrderService -> PaymentService -> OrderService`.

Observe the circular dependency failure. Extract workflow orchestration into a third bean and verify the context starts cleanly.

### Exercise 12 — Optional Dependencies

Create an optional gateway and try `ObjectProvider`, `Optional`, and `@Autowired(required=false)`.

Analyze how each expresses absence and the risks if the dependency is actually mandatory.

### Exercise 13 — Lazy Beans

Mark a bean `@Lazy` and make its constructor throw.

Observe the context starting before the bean is requested. Then invoke the bean and note when the error surfaces.

### Exercise 14 — Factory Methods

Create a `@Bean` method checking endpoint config and throwing when missing.

Read the stack trace and identify which factory method failed.

### Exercise 15 — BeanPostProcessor

Write a small `BeanPostProcessor` targeting a specific bean. Intentionally throw in the callback to observe bean creation failure.

Explain why custom post-processors must minimize side effects and avoid resolving dependencies prematurely.

### Exercise 16 — Minimal Context Testing

Use `ApplicationContextRunner` to:

- Test property conditions.
- Test bean presence/absence.
- Test binding.
- Test context startup failure when a dependency is missing.

### Exercise 17 — Startup Logs and Ready Events

Create an `ApplicationRunner` that throws an exception. Observe startup logs, `ApplicationStartedEvent`, and `ApplicationReadyEvent`.

Explain why `Started ...` can appear in logs before the runner fails.

### Exercise 18 — Designing Startup Validation

A service needs a database and a partner API. Classify:

- Which conditions are mandatory to create beans?
- Which conditions must be verified before readiness?
- Which conditions only need retries during request handling?
- What are the timeout and failure policies for each?

Avoid putting every remote call in constructors or `@PostConstruct`.

## 27. Takeaways

`BeanCreationException` signals that Spring could not finish creating a bean, yet **the root cause may lie deep in the dependency graph**. Read the entire `Caused by` chain, identify the first bean that actually failed, and classify the lifecycle phase: dependency resolution, instantiation, property population, initialization callback, or bean post-processing.

Constructors should focus on accepting and storing dependencies. `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom init methods fit brief, synchronous, bounded initialization. Remote I/O, heavy preloads, or background work require dedicated lifecycles, timeouts, and readiness policies.

When a bean is missing, check component scan, `@Bean`, profiles, and conditions. When multiple beans exist, use qualifiers/primary or an appropriate router. When property binding fails, check configuration sources and data types. When circular dependencies appear, redesign the dependency graph instead of enabling circular references or masking the issue with `@Lazy`.

After fixing, reproduce with unit tests or small context tests, then confirm the full startup lifecycle completes. **An application is considered successfully started only once the context, mandatory runners, and contracted readiness checks all pass**, not simply because one log line was printed.
# BeanCreationException Caused by Constructor, Init, or Dependency Failures

When Spring Boot starts, Spring must instantiate a set of beans and wire them into an object graph. Controllers need services, services need repositories, repositories need a DataSource, and the DataSource needs a valid URL, driver, and credentials. If even one link cannot be initialized, upstream bean creation can fail in a cascade.

A familiar log error:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService':
Invocation of init method failed
~~~

This message indicates Spring could not finish creating the `orderService` bean. It is **not enough to conclude the root cause**. The real bug might be a constructor throwing an exception, a missing dependency, two matching beans, unbindable properties, a failing initialization method, or a lower bean in the dependency graph failing to initialize.

**`BeanCreationException` is a Spring container exception typically describing a failed bean creation.** It can wrap a more specific exception and include details about the bean, resource, or dependency involved. When diagnosing, start from the bean named in the message, follow the dependency chain, and locate the deepest meaningful **root cause**.

This lesson explains the bean creation lifecycle, constructor injection, dependency resolution, initialization callbacks, exception wrapping, circular dependencies, configuration and property binding, and an investigation workflow applicable to real Spring Boot applications.

## 1. What Is BeanCreationException?

`BeanCreationException` resides in package:

~~~java
org.springframework.beans.factory.BeanCreationException
~~~

It is a `BeansException` used by Spring when it cannot create a bean per the registered bean definition.

Example:

~~~java
@Service
public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }
}
~~~

If Spring finds no matching bean for `PaymentClient`, creating `OrderService` cannot finish. Spring may report `UnsatisfiedDependencyException` or `NoSuchBeanDefinitionException` in the cause chain, and wrap the failure in a container exception higher up.

Another example:

~~~java
@Component
public class CacheInitializer {

    @PostConstruct
    void initialize() {
        throw new IllegalStateException("Cache configuration is invalid");
    }
}
~~~

The bean is instantiated and injected with dependencies, yet `@PostConstruct` throws an exception. Spring cannot finish initialization, so bean creation fails and the exception is wrapped by the container.

### BeanCreationException Is Not Always an Error in the First Named Class

Suppose the log shows:

~~~text
Error creating bean with name 'orderController'
  Unsatisfied dependency expressed through constructor parameter 0
  Error creating bean with name 'orderService'
    Error creating bean with name 'paymentClient'
      Failed to bind properties
        Invalid URL: "ht!tp://..."
~~~

Read the chain as follows:

1. Spring is creating `orderController`.
2. The controller needs `orderService`, which is unavailable.
3. Spring attempts to create `orderService`.
4. The service needs `paymentClient`.
5. Creating the client fails because the URL property is invalid.

The first bean appearing in logs is often merely **where the error surfaced along the dependency chain**, not necessarily where the bug lives.

## 2. Bean Creation Lifecycle and Where Errors Arise

For an ordinary singleton bean, the general flow involves these steps:

~~~text
Spring needs bean
      |
      v
Find BeanDefinition
      |
      v
Select constructor / factory method
      |
      v
Instantiate object
      |
      v
Inject dependencies and populate properties
      |
      v
Aware callbacks
      |
      v
BeanPostProcessor: before initialization
      |
      v
Initialization callbacks
  - @PostConstruct
  - InitializingBean.afterPropertiesSet()
  - custom init method
      |
      v
BeanPostProcessor: after initialization
      |
      v
Bean ready for callers
~~~

This is an overview flow. Special extension points, scoped beans, FactoryBeans, and proxy creation can add or alter details.

| Stage | Example Failure |
|---|---|
| Reading bean definition | Class missing, invalid configuration |
| Resolving constructor | No suitable constructor found |
| Resolving dependencies | Missing bean, multiple beans of same type |
| Instantiating | Constructor throws exception |
| Populating properties | Setter/field injection or type conversion fails |
| Aware callbacks | Callback throws exception |
| Before-init processor | BeanPostProcessor fails |
| Initialization | `@PostConstruct` or `afterPropertiesSet()` throws exception |
| Custom init method | Method declared via `@Bean(initMethod=...)` fails |
| After-init processor | Proxy/processor fails to produce final bean |
| FactoryBean | Creating the factory or fetching its produced object fails |

### Distinguishing Instantiate from Initialize

- **Instantiate:** construct the Java object, typically via constructor or factory method.
- **Populate:** wire required dependencies and properties.
- **Initialize:** execute callbacks and processing before the bean enters normal use.

A successful constructor does not guarantee initialization succeeds. Completing dependency injection does not guarantee `@PostConstruct` succeeds.

## 3. Read the Exception Chain Instead of Only the First Line

A Spring stack trace often contains multiple exception layers. Example:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService':
Could not autowire field: private PaymentClient paymentClient

Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'PaymentClient' available
~~~

Key details to extract:

- **Bean being created:** `orderService`.
- **Dependency location:** field `paymentClient`.
- **Cause category:** `NoSuchBeanDefinitionException`.
- **Meaning:** the context contains no bean compatible with `PaymentClient` at resolution time.

Another example:

~~~text
BeanCreationException:
Error creating bean with name 'cacheInitializer':
Invocation of init method failed

Caused by: IllegalStateException:
Cache endpoint must be configured
~~~

Here dependencies may have been injected completely; the cause lies in initialization logic.

### Finding the Root Cause in an IDE

1. Open the logs from the start of the failed boot.
2. Locate the first `BeanCreationException`.
3. Read the bean name and Spring's described operation.
4. Walk down every `Caused by`.
5. Find the most specific exception whose message relates directly to the failure.
6. Match that exception's stack trace to the corresponding constructor, init callback, or dependency.

Do not copy `Error creating bean with name ...` and edit that bean by guesswork.

### The Deepest Root Cause Is Not Always the Most Actionable Cause

An error chain may terminate in a library `NullPointerException`, yet the design cause is that your application passed a null configuration. Read both the root cause and the context where the exception originated rather than blindly grabbing the bottom line of the stack trace.

## 4. Constructor Injection Failures

Constructor injection is the standard way to declare mandatory dependencies:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final TaxCalculator taxCalculator;

    public InvoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator
    ) {
        this.repository = repository;
        this.taxCalculator = taxCalculator;
    }
}
~~~

When creating `InvoiceService`, Spring must locate matching beans for both `InvoiceRepository` and `TaxCalculator`.

If a dependency is missing, the constructor cannot be called. Spring reports `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, or an enclosing container exception.

### Missing Bean Implementation

Interface:

~~~java
public interface TaxCalculator {
    BigDecimal calculate(BigDecimal amount);
}
~~~

No implementation registered:

~~~java
@Service
public class InvoiceService {

    public InvoiceService(TaxCalculator taxCalculator) {
        // ...
    }
}
~~~

The context cannot build `InvoiceService` without a matching `TaxCalculator` bean.

The fix is identifying the needed implementation and registering it properly:

~~~java
@Component
public class StandardTaxCalculator implements TaxCalculator {

    @Override
    public BigDecimal calculate(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.10"));
    }
}
~~~

Or register the bean via `@Configuration` and `@Bean` if the implementation comes from a library or needs factory logic.

### Class Has @Component Yet Is Still Not Found

A class annotated with `@Component` is not automatically registered. Check:

- Is its package inside component scan scope?
- Was the configuration class imported?
- Did a profile exclude the bean?
- Did conditions match?
- Was the bean excluded by a scan filter?
- Is the class actually on the runtime classpath?

Do not slap `@ComponentScan("com")` broadly just to silence the error. Overly broad scanning pulls in unintended beans and causes new conflicts.

## 5. No Matching Bean: NoSuchBeanDefinitionException

`NoSuchBeanDefinitionException` usually appears when Spring needs a bean by type or name yet finds no matching candidate.

Example:

~~~java
@Service
public class ReportService {

    private final ReportExporter exporter;

    public ReportService(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

Without a `ReportExporter` bean, the context cannot create `ReportService`.

### How to Investigate

1. Identify the type Spring is looking for.
2. Search for implementations in your project and dependencies.
3. Check whether an implementation is registered.
4. Check profile/property/classpath conditions.
5. Check whether configuration was imported/scanned.
6. If the dependency is optional, decide whether the bean should be skipped or context should fail.

### Optional Dependencies Must Be Designed Explicitly

When an integration is genuinely optional, use conditions:

~~~java
@AutoConfiguration
@ConditionalOnClass(RemoteReportClient.class)
public class RemoteReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "reports.remote",
            name = "enabled",
            havingValue = "true"
    )
    ReportExporter remoteReportExporter(
            RemoteReportClient client
    ) {
        return new RemoteReportExporter(client);
    }
}
~~~

Classes in this example are illustrative. When the optional library is absent, the integration configuration should not attempt to create beans depending on it.

If a dependency is mandatory, never silently ignore the error and let the app run missing functionality.

## 6. Multiple Matching Beans: NoUniqueBeanDefinitionException

Another error occurs when Spring finds **more than one candidate** for a single dependency.

Example:

~~~java
public interface PaymentGateway {
    void charge(BigDecimal amount);
}
~~~

Two implementations:

~~~java
@Component
public class CardPaymentGateway implements PaymentGateway {
    @Override
    public void charge(BigDecimal amount) {
        // ...
    }
}
~~~

~~~java
@Component
public class WalletPaymentGateway implements PaymentGateway {
    @Override
    public void charge(BigDecimal amount) {
        // ...
    }
}
~~~

Consumer:

~~~java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway gateway) {
        // ...
    }
}
~~~

Spring has two candidates, yet the constructor does not state which bean to use. `NoUniqueBeanDefinitionException` appears and surfaces in the creation chain of `CheckoutService`.

### Option 1: @Primary

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

`@Primary` marks the preferred candidate when type-based injection has multiple matches.

### Option 2: @Qualifier

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("walletPaymentGateway")
            PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
~~~

`@Qualifier` specifies the exact candidate to use. This fits when a consumer has a specific requirement.

### Option 3: Inject All Implementations

If business logic genuinely chooses among multiple strategies, inject a collection:

~~~java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
~~~

The service then selects implementations according to an explicit policy.

Do not use `@Primary` just to paper over a multi-implementation design lacking a proper selection policy.

## 7. Multiple Constructors and @Autowired

Spring must decide which constructor to invoke to instantiate a bean.

A class with a single constructor usually does not need `@Autowired`:

~~~java
@Service
public class SearchService {

    private final SearchRepository repository;

    public SearchService(SearchRepository repository) {
        this.repository = repository;
    }
}
~~~

With multiple constructors, intent must be clear:

~~~java
@Component
public class ClientRegistry {

    private final RemoteClient client;

    @Autowired
    public ClientRegistry(RemoteClient client) {
        this.client = client;
    }

    public ClientRegistry() {
        this.client = new NoOpRemoteClient();
    }
}
~~~

When multiple constructors have parameters and varying required/optional settings, Spring's selection rules grow subtle. Annotate explicitly and avoid declaring multiple candidate constructors that cannot all be resolved.

### Constructor Ambiguity

Example:

~~~java
@Component
public class AmbiguousService {

    public AmbiguousService(FirstClient first) {
    }

    public AmbiguousService(SecondClient second) {
    }
}
~~~

Without an indication of which constructor to use, Spring may not know which one to pick.

A clearer design keeps a single explicit dependency constructor, or marks the intended constructor per Spring's contract.

### Lombok Can Generate Constructors Not Directly Visible in Source

Example:

~~~java
@Service
@RequiredArgsConstructor
public class CustomerService {
    private final CustomerRepository repository;
    private final EmailSender emailSender;
}
~~~

`@RequiredArgsConstructor` generates a constructor for final/required fields. If a class also declares manual constructors or other Lombok annotations, inspect the generated bytecode/source to see which constructors Spring actually sees.

When logs say parameter index 1 cannot be resolved, inspect the post-annotation-processing constructor rather than judging only from raw source lines.

## 8. Dependencies in @Bean Factory Methods

Not every bean is created via a `@Component` constructor. A `@Bean` method can also accept dependencies:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    RemoteClient remoteClient(
            HttpClient httpClient,
            RemoteClientProperties properties
    ) {
        return new RemoteClient(
                httpClient,
                properties.endpoint()
        );
    }
}
~~~

Spring must resolve the factory method's parameters before invoking it.

If `HttpClient` or `RemoteClientProperties` is missing, creating `remoteClient` fails. Logs point to the factory method, yet the underlying cause is still dependency resolution.

### Factory Method Throws an Exception

~~~java
@Bean
RemoteClient remoteClient(RemoteClientProperties properties) {
    URI endpoint = properties.endpoint();

    if (endpoint == null) {
        throw new IllegalStateException(
                "Remote endpoint is required"
        );
    }

    return new RemoteClient(endpoint);
}
~~~

Here dependencies resolved, yet the factory method threw an exception. Spring cannot complete bean creation.

### Place Validation at the Right Boundary

If `endpoint` is a mandatory property, use `@ConfigurationProperties` with validation to fail earlier with clearer messages instead of waiting for a factory method to throw a generic exception.

## 9. Constructors Throwing Exceptions Directly

A constructor can fail due to internal logic:

~~~java
@Component
public class CertificateProvider {

    private final Certificate certificate;

    public CertificateProvider() {
        try {
            this.certificate = loadCertificate();
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot load signing certificate",
                    ex
            );
        }
    }

    private Certificate loadCertificate() throws IOException {
        // Read file or parse certificate.
        return CertificateFactory.getInstance("X.509")
                .generateCertificate(
                        new ByteArrayInputStream(new byte[0])
                );
    }
}
~~~

This example deliberately illustrates a constructor capable of failing; empty certificate data is not a valid certificate.

Spring wraps instantiation failures with bean-descriptive exceptions such as `BeanInstantiationException` and `BeanCreationException` at the appropriate layers.

### Constructors Should Do Minimal Work

Constructors should mostly accept dependencies and assign required state:

~~~java
@Service
public class ReportService {

    private final ReportRepository repository;
    private final ReportFormatter formatter;

    public ReportService(
            ReportRepository repository,
            ReportFormatter formatter
    ) {
        this.repository = repository;
        this.formatter = formatter;
    }
}
~~~

Minimize network calls, large database queries, complex config file parsing, or spawning threads inside constructors. Such side effects make objects hard to instantiate in tests, hard to retry cleanly, and execute before container lifecycle management finishes.

If a resource must be opened at initialization, use an explicit lifecycle hook with matching cleanup.

## 10. @PostConstruct Failures

`@PostConstruct` is a callback invoked after dependency injection and appropriate bean preparation complete, before the bean enters normal use.

In Spring Boot 3 / Spring Framework 6, the import is typically:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Example:

~~~java
@Component
public class SearchIndexInitializer {

    private final SearchIndexClient client;

    public SearchIndexInitializer(SearchIndexClient client) {
        this.client = client;
    }

    @PostConstruct
    void initialize() {
        if (!client.isConfigured()) {
            throw new IllegalStateException(
                    "Search index client is not configured"
            );
        }
    }
}
~~~

If `initialize()` throws an exception, Spring cannot complete bean initialization. The failure usually prints details like:

~~~text
BeanCreationException:
Error creating bean with name 'searchIndexInitializer':
Invocation of init method failed
~~~

The root cause is the `IllegalStateException` thrown by your code.

### @PostConstruct Is Not Appropriate for All Long-Running Tasks

If a callback calls remote services or loads millions of records, startup can stall or fail outright when external services are briefly unavailable.

Decide explicitly:

- Is this resource strictly required before serving any requests?
- Can it be retried after startup?
- What timeout is needed?
- Should readiness stay unready during warm-up?
- If initialization fails, can already-opened resources be cleaned up?

Do not turn `@PostConstruct` into an entire startup workflow when tasks deserve their own lifecycle.

## 11. InitializingBean.afterPropertiesSet() Failures

Spring supports the interface:

~~~java
org.springframework.beans.factory.InitializingBean
~~~

Example:

~~~java
@Component
public class QueueConsumer implements InitializingBean {

    private final QueueClient queueClient;

    public QueueConsumer(QueueClient queueClient) {
        this.queueClient = queueClient;
    }

    @Override
    public void afterPropertiesSet() {
        if (!queueClient.isReady()) {
            throw new IllegalStateException(
                    "Queue client is not ready"
            );
        }
    }
}
~~~

`afterPropertiesSet()` runs during initialization after dependencies and properties are populated.

If it throws an exception, Spring treats bean initialization as failed and wraps it in `BeanCreationException`.

### @PostConstruct and InitializingBean Can Coexist

A bean can use multiple initialization callback types. In a standard lifecycle, Spring invokes them in order:

1. Methods annotated with `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init methods declared in the bean definition, e.g., `@Bean(initMethod = "initialize")`.

Afterward, post-init BeanPostProcessors continue processing the bean.

Never place non-idempotent side effects across multiple callbacks. For example, if both `@PostConstruct` and `afterPropertiesSet()` allocate an external resource, you may allocate it twice.

## 12. Custom Init Methods via @Bean(initMethod)

A configuration can declare:

~~~java
@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {

    @Bean(initMethod = "connect", destroyMethod = "close")
    StorageClient storageClient() {
        return new StorageClient();
    }
}
~~~

Class:

~~~java
public class StorageClient {

    public void connect() {
        // Open connection or prepare resources.
    }

    public void close() {
        // Release resources.
    }
}
~~~

If `connect()` throws an exception, creating `storageClient` fails.

### Reading the Right Bean Definition

Logs may say:

~~~text
Invocation of init method failed
~~~

When this appears, check:

- Which `@Bean` created the bean?
- Does the bean definition specify `initMethod`?
- Does the init method exist and can it be invoked?
- Which exception did the method throw?
- Which resources were already opened before the exception?

Do not assume every `init method failed` error comes from `@PostConstruct`. A custom init method could be the source.

## 13. Distinguishing the Three Init Callback Styles

| Approach | Declaration | Notes |
|---|---|---|
| `@PostConstruct` | Method annotation | Jakarta standard; handled by Spring lifecycle processor |
| `InitializingBean` | Implement `afterPropertiesSet()` | Bean couples directly to Spring API |
| `@Bean(initMethod = "...")` | Metadata on bean definition | Ideal for third-party classes or avoiding class edits |

Example where one bean defines all three:

~~~java
@Component
public class ResourceManager implements InitializingBean {

    @PostConstruct
    void prepare() {
        // First preparation step.
    }

    @Override
    public void afterPropertiesSet() {
        // Step after properties have been populated.
    }

    public void customStart() {
        // Can be configured as initMethod.
    }
}
~~~

You do not need all three. Pick one style matching your control over the class and project conventions.

### Spring Boot 2 vs. 3: Annotation Namespaces

- Spring Boot 3 builds on Jakarta EE 9+ and uses `jakarta.annotation.PostConstruct`.
- Older Spring Boot 2 used `javax.annotation.PostConstruct`, depending on version/dependencies.

Importing the wrong namespace can prevent infrastructure from recognizing the annotation.

## 14. Dependency Exists Yet Fails to Be Created Itself

Suppose:

~~~java
@Service
public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }
}
~~~

The `PaymentClient` bean is registered yet fails itself:

~~~java
@Component
public class PaymentClient {

    public PaymentClient(PaymentProperties properties) {
        if (properties.endpoint() == null) {
            throw new IllegalArgumentException(
                    "Payment endpoint is required"
            );
        }
    }
}
~~~

Error chain:

~~~text
OrderController
    |
    v
OrderService
    |
    v
PaymentClient
    |
    v
PaymentProperties / endpoint
    |
    v
IllegalArgumentException
~~~

Here `OrderService` is not the bean to fix. It simply failed to construct because its dependency `PaymentClient` could not finish.

### The Dependency Chain Principle

If bean A requires bean B and B fails creation, A's error is a **consequence**. Find the first bean in the chain with a concrete underlying cause, such as:

- Constructor exception.
- Init callback exception.
- Missing property.
- Conversion/binding failure.
- Dependency ambiguity.
- Circular reference.
- External resource failure.

Fixing that link usually allows the entire upstream chain to start.

## 15. @Value and Property Placeholder Failures

A bean can rely on properties via `@Value` or `Environment`. Example using `Environment` to show configuration lookup explicitly:

~~~java
@Component
public class PartnerClient {

    private final URI endpoint;

    public PartnerClient(Environment environment) {
        this.endpoint = URI.create(
                environment.getRequiredProperty("partner.api.endpoint")
        );
    }
}
~~~

If `partner.api.endpoint` is absent, `getRequiredProperty` throws because the mandatory property was not supplied. With `@Value`, an unresolved placeholder without a default also fails during bean creation.

Example configuration:

~~~yaml
partner:
  api:
    endpoint: https://partner.example.test
~~~

### Use Defaults When Defaults Are Truly Valid

For optional settings like timeouts, provide defaults via `@Value` placeholders or typed properties:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiSettings {

    private Duration timeout = Duration.ofSeconds(3);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Never put defaults on mandatory properties like production endpoints just so startup passes. A wrong default can silently connect production to the wrong environment or run unsafely.

### Type Conversion Can Also Fail

~~~properties
partner.api.timeout=three-seconds
~~~

If the target type is `Duration` and the converter cannot parse the string, injection/binding fails.

When investigating, distinguish:

- Property does not exist.
- Property exists yet is blank.
- Property exists yet has invalid format.
- Property was overridden by another source with a bad value.

## 16. @ConfigurationProperties Binding and Validation Failures

For multi-field configuration, use typed properties:

~~~java
@ConfigurationProperties(prefix = "partner.api")
@Validated
public class PartnerApiProperties {

    @NotNull
    private URI endpoint;

    @Min(1)
    private int maxAttempts = 3;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` per application layout.

If properties fail to bind or violate validation, the context fails while creating the properties bean. Downstream beans depending on those properties then fail as well.

### Invalid Configuration Example

~~~yaml
partner:
  api:
    endpoint: "not a uri"
    max-attempts: 0
~~~

This triggers a URI conversion failure or a `@Min(1)` constraint violation.

### Distinguish Bind Failure from Validation Failure

- **Bind failure:** source data cannot convert to the target Java type.
- **Validation failure:** data bound cleanly yet violated constraints.
- **Downstream bean creation failure:** services/clients cannot start because the properties bean is invalid.

Read the root cause and property name in the message to identify which group applies.

### Do Not Disable Validation Just to Boot the App

When properties guard endpoints, timeouts, pool sizes, or resource limits, validation is valuable fail-fast protection. Fix the bad configuration rather than deleting constraints to hide errors.

## 17. Type Conversion Errors During Dependency Injection

Example:

~~~java
@Component
public class RetryPolicy {

    public RetryPolicy(
            @Value("retry.max-attempts") int maxAttempts
    ) {
        // Illustrates target parameter type; real config uses a placeholder.
    }
}
~~~

With configuration:

~~~properties
retry.max-attempts=lots
~~~

Spring cannot convert `"lots"` to `int`. Bean creation fails while resolving constructor arguments/properties.

Error messages typically state the property name or unconvertible value. Check:

- Target type.
- Highest-precedence property source.
- Value syntax.
- Whether custom converters/formatters are registered.
- Whether test/runtime classpaths share the same conversion infrastructure.

For complex configuration, `@ConfigurationProperties` centralizes metadata, binding, and validation far better than scattering `@Value` across constructors.

## 18. Beans Depending on External Resources at Initialization

Some beans connect to databases, message brokers, object stores, or remote APIs right at creation:

~~~java
@Component
public class PartnerConnection {

    private final PartnerClient client;

    public PartnerConnection(PartnerClient client) {
        this.client = client;
    }

    @PostConstruct
    void connect() {
        client.ping();
    }
}
~~~

If the partner is under maintenance, DNS fails, TLS certificates are invalid, or credentials are wrong, the callback throws and aborts Spring context startup.

### Should Startup Fail When External Services Are Unavailable?

This is an operational decision, not merely a coding question.

Failing startup makes sense if the service cannot handle any requests without the partner. Yet if the integration can retry or is optional, failing the entire application harms resilience.

Consider:

- Creating the client without connecting inside the constructor.
- Checking connectivity via health/readiness logic.
- Using bounded retries with backoff.
- Reporting readiness as unready until mandatory dependencies respond.
- Isolating optional integrations from core beans.
- Enforcing explicit timeouts and circuit breakers.

Never allow a startup callback to block indefinitely waiting on a remote service.

### Do Not Swallow Exceptions and Pretend Startup Succeeded

~~~java
@PostConstruct
void connect() {
    try {
        client.connect();
    } catch (Exception ex) {
        log.warn("Partner connection failed", ex);
    }
}
~~~

This lets the context finish starting while leaving the bean unusable. When requests arrive and fail later, debugging becomes far harder.

If adopting a degraded mode, model that state explicitly with health indicators and clear request behavior. Never merely log a warning and move on.

## 19. Circular Dependencies and BeanCurrentlyInCreationException

Another tricky failure occurs when two or more beans depend on each other in a cycle.

~~~text
OrderService -> InventoryService
      ^               |
      |               v
      +----------- StockService
~~~

Constructor injection example:

~~~java
@Service
public class OrderService {

    public OrderService(InventoryService inventoryService) {
    }
}
~~~

~~~java
@Service
public class InventoryService {

    public InventoryService(OrderService orderService) {
    }
}
~~~

Spring needs `OrderService` to construct `InventoryService`, yet needs `InventoryService` to construct `OrderService`. With constructor cycles, neither object exists in a complete state to hand to the other.

This manifests via `BeanCurrentlyInCreationException` and nested `BeanCreationException` chains.

### Spring Boot Disallows Circular References by Default

In modern Spring Boot versions, circular references are prohibited by default. As a result, setter/field cycles that previously survived via early references in older Spring setups fail under Boot's defaults.

Do not turn on `spring.main.allow-circular-references=true` as a first fix. It hides questionable coupling and complicates lifecycles and proxies.

### Better Fix: Separate Responsibilities

Instead of:

~~~text
OrderService <----> InventoryService
~~~

introduce an orchestrating service:

~~~text
OrderApplicationService
       |           |
       v           v
OrderService  InventoryService
~~~

Or extract a small shared abstraction needed by both without reverse dependencies.

### Use Events When Appropriate

When one service merely notifies that a domain action occurred, application events reduce coupling:

~~~java
public record OrderPlacedEvent(UUID orderId) {}
~~~

Another component handles the event:

~~~java
@Component
public class InventoryEventHandler {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        // Reserve stock.
    }
}
~~~

This is a design choice, not a universal substitute for every dependency. If transactional consistency or durable delivery is required, consider transaction-bound events or messaging/outbox patterns.

## 20. @Lazy Defers Dependencies Without Fixing Design

`@Lazy` on a bean or injection point defers creating/resolving a dependency via a proxy in supported scenarios.

Example:

~~~java
@Service
public class ReportService {

    private final ExpensiveReportEngine engine;

    public ReportService(@Lazy ExpensiveReportEngine engine) {
        this.engine = engine;
    }
}
~~~

If the engine is not needed immediately, it instantiates when the proxy is first used.

However:

- When the lazy bean is finally used, initialization errors still occur.
- The design-level dependency cycle remains.
- Failures shift from startup into runtime request paths.
- Deferred beans can keep health/readiness from reflecting real capability.

Use `@Lazy` when deferred initialization makes sense, never to conceal a broken mandatory dependency.

## 21. @DependsOn Is Not Dependency Injection

`@DependsOn` specifies creation/destruction ordering between beans when side-effect order matters.

Example:

~~~java
@Component
public class SearchIndexer {
}

@Component
@DependsOn("searchIndexer")
public class SearchWarmup {
}
~~~

Spring ensures the named bean initializes before the dependent bean per container rules.

However, `@DependsOn` **does not supply a dependency reference** for constructors and does not solve circular constructor injection.

If `SearchWarmup` actually calls `SearchIndexer`, inject it via constructor. Real dependencies let Spring infer ordering and manage lifecycles naturally.

## 22. BeanFactoryPostProcessor or BeanPostProcessor Failures

Spring provides extension points running while processing bean definitions or instantiating beans:

- `BeanFactoryPostProcessor` inspects or modifies bean factory metadata before regular application beans instantiate.
- `BeanPostProcessor` processes objects before/after initialization.
- Auto-configuration and framework infrastructure register processors of their own.

If a processor fails, multiple beans may fail creation or context refresh aborts.

Example:

~~~java
@Component
public class InvalidBeanPostProcessor
        implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName
    ) {
        if ("orderService".equals(beanName)) {
            throw new IllegalStateException(
                    "Order service cannot be initialized"
            );
        }

        return bean;
    }
}
~~~

This example throws intentionally for illustration. In practice, processors fail due to reflection, proxy generation, metadata errors, or bean handling bugs.

### Diagnosing Processors

- Find the bean name cited in the message.
- Check whether the exception occurred before or after init callbacks.
- Identify which processor was handling the bean.
- Inspect processor ordering and dependencies.
- If the processor belongs to a third-party library, check version compatibility and auto-configuration conditions.

Do not mistake an exception thrown by a BeanPostProcessor for an exception inside the target bean's constructor.

## 23. FactoryBean: Factory Created Successfully yet Product Fails

`FactoryBean` is an abstraction allowing Spring to retrieve objects produced by a factory bean.

Conceptual example:

~~~java
public class ReportClientFactory
        implements FactoryBean<ReportClient> {

    @Override
    public ReportClient getObject() {
        return new ReportClient(loadConfiguration());
    }

    @Override
    public Class<?> getObjectType() {
        return ReportClient.class;
    }
}
~~~

Distinguish two layers:

1. Spring instantiates `ReportClientFactory`.
2. Spring asks the factory for `ReportClient`.

The factory bean itself may instantiate cleanly while `getObject()` throws an exception. Then the bean requested by the application cannot be supplied, and container errors appear as `BeanCreationException` or factory-related exceptions.

### Read Both Bean Names and FactoryBean Contracts

When seeing `FactoryBean` in errors, check:

- FactoryBean constructor.
- `getObject()`.
- `getObjectType()`.
- Dependencies required by the factory.
- Configuration used to construct the product.
- Whether creation is cached or repeated per scope.

Do not debug only the factory class and overlook the product it builds.

## 24. @Configuration Classes and @Bean Method Failures

A `@Configuration` class is itself a bean and can fail creation. Common causes:

- Configuration class constructor cannot resolve dependencies.
- A `@Bean` factory method throws an exception.
- A bean method returns null illegally.
- The class is proxied yet has method signatures incompatible with configuration proxying.
- A condition registers the configuration unexpectedly.
- A static initializer on the class throws.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway(
            PaymentProperties properties
    ) {
        if (properties.endpoint() == null) {
            throw new IllegalStateException(
                    "Payment endpoint must be configured"
            );
        }

        return new HttpPaymentGateway(properties.endpoint());
    }
}
~~~

If the endpoint is missing, failure triggers when Spring invokes the factory method.

### Distinguish Direct Method Calls from Bean Lifecycle

In `proxyBeanMethods = false` mode, do not call another `@Bean` method directly expecting the container-managed singleton. Declare dependencies as factory method parameters instead:

~~~java
@Bean
PaymentFacade paymentFacade(PaymentGateway paymentGateway) {
    return new PaymentFacade(paymentGateway);
}
~~~

This keeps the dependency graph explicit and matches lite configuration mode.

## 25. Static Initializers and Class Loading Errors

Java classes execute static initializers before Spring invokes constructors:

~~~java
public class CryptoRegistry {

    static {
        if (System.getenv("CRYPTO_HOME") == null) {
            throw new IllegalStateException(
                    "CRYPTO_HOME is required"
            );
        }
    }
}
~~~

When the class loads/initializes, the exception wraps into `ExceptionInInitializerError` or another class initialization failure. Spring then cannot instantiate beans using that class.

### Signs to Check

- `ExceptionInInitializerError`.
- `NoClassDefFoundError` on subsequent accesses.
- `ClassNotFoundException`.
- Static field initialization or native library loading errors.

Do not inspect only constructors. If the class could not initialize, its constructor never even ran.

### Do Not Read Runtime Secrets in Static Initializers

Environment values differ across developer machines, CI, and production. Static initialization timing also varies across JVM runs, tests, and native executables. Pass configuration into beans via Environment/ConfigurationProperties and validate at clear lifecycle boundaries.

## 26. Profiles or Conditions Making Dependencies Disappear

A service may require a bean registered only under another profile:

~~~java
@Component
@Profile("prod")
public class ProductionPaymentGateway
        implements PaymentGateway {
}
~~~

While the service has no condition:

~~~java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway gateway) {
    }
}
~~~

When running with the `dev` profile and no alternative `PaymentGateway` bean exists, the context fails.

### Questions to Check

- Which profile is active?
- Is a default profile active?
- Does the bean implementation match the profile?
- Do property conditions match?
- Is an optional dependency missing?
- Is an intentional fallback bean needed?

### Do Not Create Arbitrary Production Fallbacks

If `dev` needs a fake gateway, define a `dev` bean explicitly. If production needs a real gateway, enforce required production configuration. Never put a shared no-op implementation everywhere just to pass startup if real transactions could silently be skipped.

## 27. Auto-Configuration Back-Off and Duplicate Bean Errors

Spring Boot auto-configurations typically supply a default bean when the application has not provided a custom one:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

If user configuration already defines a matching `PaymentGateway` bean, auto-configuration backs off conditionally.

When conditions/ordering misalign or custom beans are not yet visible during evaluation, the app can encounter:

- Multiple beans of the same type.
- Default bean still created despite a custom bean.
- Injection ambiguity.
- Bean definition override conflicts depending on names and override policy.

### Distinguish Creation Errors from Registration Errors

- **Registration conflict:** Spring cannot register a bean definition under current naming/override rules.
- **Creation failure:** the bean definition exists, yet the object fails creation/initialization.
- **Injection ambiguity:** multiple valid beans satisfy a dependency without a preferred candidate.

All three can appear in the same startup log, yet require different fixes.

## 28. Bean Scopes and Creation Timing

Singletons are typically created at context refresh unless lazy. Prototypes are created whenever requested. Scoped beans instantiate when their scope is active, such as request scope.

Consequently, the exact same constructor error surfaces at different times:

- Eager singleton: usually during startup.
- Lazy singleton: on first access.
- Prototype: on every instance creation.
- Request-scoped: on the first matching request.

### Successful Context Startup Does Not Prove Every Bean Can Be Created

If a bean is lazy-initialized or reached only on a specific runtime branch, the context can start cleanly even though that bean fails on first invocation.

For critical integrations, test real instantiation or add appropriate health/readiness checks instead of only verifying that the process started.

## 29. BeanCreationException in Test Contexts

A Spring test can fail before any test method executes:

~~~java
@SpringBootTest
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrder() {
        // ...
    }
}
~~~

If any bean in the full application context fails creation, Spring Test cannot inject test dependencies and reports a context load failure.

### Reading Test Failures

- Check which context type the test class requests.
- Locate the first context load failure.
- Find the failing bean and root cause.
- Check test property sources, active profiles, and mocks.
- Check whether a bean tries to reach an external service.

### Use Narrow Tests When Only Testing Configuration

For a small auto-configuration, `ApplicationContextRunner` isolates it cleanly:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(MyConfiguration.class)
        .withPropertyValues("demo.feature.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(MyFeature.class);
        });
~~~

When the context fails, callbacks can assert `context.hasFailed()` and `context.getStartupFailure()`. This helps verify intentional failures or conditions without booting the whole app.

### Narrow Tests Do Not Replace Full Application Tests

To prove the whole application starts with production-like profiles and database configuration, you still need a broader integration test. A lightweight runner only proves the subset of configuration passed into it.

## 30. Using ApplicationContextRunner to Test Startup Failures

Example configuration needing a dependency:

~~~java
@Configuration(proxyBeanMethods = false)
class RequiredClientConfiguration {

    @Bean
    ReportService reportService(RequiredClient client) {
        return new ReportService(client);
    }
}
~~~

Test:

~~~java
@Test
void failsWhenRequiredClientIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    RequiredClientConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

If needed, assert the root cause:

~~~java
assertThat(context.getStartupFailure())
        .hasRootCauseInstanceOf(
                NoSuchBeanDefinitionException.class
        );
~~~

This tests the contract that the dependency is truly mandatory. If an integration is optional, test that the context still starts without registering the integration bean.

## 31. Spring Boot's FailureAnalyzer

Spring Boot uses **FailureAnalyzer** to turn common startup failures into clearer guidance.

When context startup fails, Boot can:

1. Receive the original exception.
2. Locate a matching analyzer.
3. Produce an analysis result with description/action.
4. Print guidance helping developers identify cause and remedy.

Examples of errors with built-in analyzers or specialized reports:

- Port already in use.
- Bean definition/constructor injection failures.
- Invalid configuration properties.
- Logging system startup failures.
- Common auto-configuration errors.

Not every custom exception has a FailureAnalyzer. When no analyzer matches, stack traces remain the primary diagnostic source.

### Do Not Ignore Description and Action

When Boot prints:

~~~text
APPLICATION FAILED TO START

Description:
...

Action:
...
~~~

read both sections. Description states which condition failed; Action often indicates exact configuration changes needed.

Do not read only the final line `Application run failed`.

## 32. Enabling Debug for the Condition Evaluation Report

If you suspect a bean is missing due to auto-configuration conditions, run:

~~~bash
java -jar store-service.jar --debug
~~~

Or configure:

~~~properties
debug=true
~~~

Spring Boot prints the **Condition Evaluation Report**, showing which auto-configurations matched or failed to match and why.

### What Questions Does the Debug Report Answer?

- Which auto-configurations were applied?
- Did classpath conditions match?
- Did properties hold matching values?
- Did existing beans cause auto-configuration to back off?
- Why was a configuration skipped?

### Debug Does Not Replace Stack Traces

The condition report explains bean registration. If a constructor already ran and threw an exception, read the stack trace to inspect constructor/init logic.

### Watch Out for Sensitive Data

Debug logs contain extra configuration and environment details. Do not leave verbose logging enabled indefinitely in production without controlling exposure of endpoints, properties, and internal metadata.

## 33. Enabling Bean Factory Logging When Needed

When a failure is hard to pinpoint, temporarily raise log levels on relevant Spring packages in development:

~~~yaml
logging:
  level:
    org.springframework.beans.factory: DEBUG
    org.springframework.context: DEBUG
    org.springframework.boot.autoconfigure: DEBUG
~~~

This reveals bean creation, dependency resolution, and condition evaluation in greater detail.

Do not enable `TRACE` across all of Spring in production without assessing log volume and sensitive data exposure.

### Keep Scope Narrow

When suspecting auto-configuration:

~~~yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
~~~

When suspecting bean lifecycles:

~~~yaml
logging:
  level:
    org.springframework.beans.factory.support: DEBUG
~~~

Exact logger names and output depend on version. Enable only for a focused investigation, then restore normal levels.

## 34. Diagnostic Workflow from Logs to Source Code

A repeatable workflow:

~~~text
Application fails to start
          |
          v
Find the first BeanCreationException
          |
          v
Note the bean name being created
          |
          v
Read the failing operation description
          |
          v
Trace the dependency chain
          |
          +--> Constructor?
          |
          +--> Missing/ambiguous dependency?
          |
          +--> Property binding/conversion?
          |
          +--> @PostConstruct/init method?
          |
          +--> External resource?
          |
          +--> Circular dependency?
          |
          +--> BeanPostProcessor/FactoryBean?
          |
          v
Cross-reference profiles, conditions, classpath
          |
          v
Fix the right source and rerun matching tests
~~~

### Step 1: Identify the Bean Name

For example, `orderService`. Locate the class/configuration registering it:

- `@Component`/`@Service`.
- `@Bean` method.
- Auto-configuration.
- FactoryBean.
- Imported configuration.

### Step 2: Identify What Spring Was Doing

Common descriptions:

- `Error creating bean with name ...`.
- `Unsatisfied dependency expressed through constructor parameter ...`.
- `Invocation of init method failed`.
- `Failed to bind properties under ...`.
- `FactoryBean threw exception on object creation`.

Each description points to a different phase.

### Step 3: Find the Root Cause

Read all `Caused by` entries rather than stopping at the first exception. Match the root cause to the source code or configuration cited in the message.

### Step 4: Verify the Environment

Check:

- Active/default profiles.
- Runtime properties and precedence.
- Dependencies on the runtime classpath.
- Bean conditions.
- External endpoints/credentials.
- Environment variables and secret mounts.
- Framework/library versions.

### Step 5: Fix and Verify

After fixing, run tests suited to the error scope:

- Unit tests for pure constructor/init logic.
- ApplicationContextRunner for conditional configurations.
- Spring context tests for wiring.
- Integration tests for real databases/HTTP/brokers.
- Smoke tests for the packaged artifact.

You do not need a full integration suite for a simple property typo, nor should pure unit tests be used to claim full application auto-configuration works.

## 35. Example: Reading a Complete Dependency Chain

Suppose the log shows:

~~~text
Error creating bean with name 'invoiceController'
  Unsatisfied dependency expressed through constructor parameter 0

Caused by: Error creating bean with name 'invoiceService'
  Unsatisfied dependency expressed through constructor parameter 1

Caused by: Error creating bean with name 'taxClient'
  Invocation of init method failed

Caused by: IllegalStateException:
  Tax endpoint must use HTTPS
~~~

Reading from outside in:

| Bean | Role | Status |
|---|---|---|
| `invoiceController` | Needs InvoiceService | Failed due to dependency |
| `invoiceService` | Needs taxClient at parameter 1 | Failed due to dependency |
| `taxClient` | Init method checks endpoint | Init failed |
| `IllegalStateException` | Specific cause | URL does not use HTTPS |

The true bug lies in the endpoint configuration or validation logic of `taxClient`. Editing the controller solves nothing.

Invalid configuration example:

~~~yaml
tax:
  endpoint: http://tax.internal
~~~

Valid configuration per example contract:

~~~yaml
tax:
  endpoint: https://tax.internal
~~~

If development actually requires HTTP, express that policy explicitly per profile rather than forcing HTTPS in every environment blindly.

## 36. Distinguishing Spring Errors from Underlying Library Errors

A constructor may invoke an external library:

~~~java
public SearchClient(SearchSettings settings) {
    this.delegate = ThirdPartyClient.create(settings.url());
}
~~~

If the library throws `IllegalArgumentException` or `LinkageError`, Spring wraps that exception inside bean creation errors.

Determine:

- Did invalid configuration parameters cause it?
- Are dependency versions incompatible?
- Is a class missing?
- Did a native library fail to load?
- Are TLS/provider/security settings wrong?
- Does the library expect a missing system property?

Never assume Spring container has a bug simply because the outer exception is in `org.springframework.beans.factory`.

### NoClassDefFoundError and ClassNotFoundException

These two point to class loading problems:

- `ClassNotFoundException` usually happens when code requests a class by name and fails to find it.
- `NoClassDefFoundError` occurs when the JVM lacks a needed class definition or the class previously failed initialization.

Check the runtime dependency graph, scopes, and artifact versions before editing bean wiring.

## 37. Database Errors in Init Callbacks

Example:

~~~java
@Component
public class SchemaVerifier {

    private final JdbcTemplate jdbcTemplate;

    public SchemaVerifier(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostConstruct
    void verify() {
        jdbcTemplate.queryForObject(
                "select 1",
                Integer.class
        );
    }
}
~~~

If the database is not ready yet, bean init fails and context startup aborts.

### Should You Query the Database in @PostConstruct?

There is no single universal answer. If the application strictly requires database connectivity to serve requests, failing fast can make sense. Yet if the dependency is recoverable, synchronous startup checks can trigger orchestrator restart loops.

Options:

- Use health indicators/readiness to report dependency status.
- Use bounded retries with backoff.
- Separate schema migrations from bean constructors/init.
- Ensure migrations run once with concurrency control.
- Keep readiness unready while mandatory dependencies are down.

### Startup and Readiness Are Two Distinct Milestones

A process can finish constructing its context before it is ready to serve traffic. Conversely, putting every dependency check inside init callbacks can crash the context before the orchestrator can even observe readiness.

Align health/lifecycle design with your container orchestration platform.

## 38. Do Not Use Catch-All Blocks to Mask BeanCreationException

An anti-pattern is catching all exceptions in constructors/init and continuing:

~~~java
@PostConstruct
void initialize() {
    try {
        loadRequiredConfiguration();
    } catch (Exception ex) {
        log.error("Initialization failed", ex);
    }
}
~~~

The bean appears initialized even though critical invariants were never established.

If the failure renders the bean incapable of honoring its contract, fail startup explicitly or transition the app into an intentionally designed degraded state.

### If Degraded Mode Is Needed

Represent state explicitly:

~~~java
@Component
public class PartnerAvailability {

    private volatile boolean available;

    public boolean isAvailable() {
        return available;
    }

    public void markAvailable() {
        available = true;
    }

    public void markUnavailable() {
        available = false;
    }
}
~~~

Another workflow can retry and update status; health indicators/consumers must honor that status explicitly. This is only an illustrative model; real applications require proper synchronization and lifecycle management.

Never treat a warning log as proof the application handled an error.

## 39. Side Effects That Already Occurred Before Bean Creation Failed

Suppose an init callback:

1. Creates a queue on a remote broker.
2. Opens a connection.
3. Loads configuration.
4. Step 3 fails.

Spring closes already-created singleton beans per context shutdown, yet **does not automatically roll back external side effects**. A created remote queue remains; an outbound request cannot be undone automatically.

### Designing Init Hooks for Cleanup

- Open resources in reverse-closable order.
- When init fails partway, clean up already-opened resources as needed.
- Prefer idempotent operations where possible.
- Avoid running large business transactions inside initialization callbacks.
- Let destruction callbacks close resources owned by the bean.

### Startup Failure Is Not a System-Wide Transaction

ApplicationContext is a container lifecycle, not a distributed transaction. Never assume constructors/init callbacks roll back like a database transaction.

## 40. Shutdown Callbacks During Startup Failures

When context refresh fails, Spring cleans up singletons already created/registered during refresh. Fully initialized beans can have their destruction callbacks invoked.

However:

- Partially created beans may lack full lifecycle registration for automatic cleanup.
- Side effects outside the Spring container do not roll back automatically.
- Manually spawned threads can survive if unmanaged.
- Force-killed processes do not guarantee shutdown callbacks execute.

Therefore, constructor/init code must manage resources deliberately. Do not rely on assuming "if the bean fails creation, Spring cleans up everything automatically."

## 41. Constructors Should Avoid Fetching Other Beans via ApplicationContext

A hard-to-maintain pattern:

~~~java
@Component
public class OrderService implements ApplicationContextAware {

    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.context = context;
    }

    public void execute() {
        PaymentClient client =
                context.getBean(PaymentClient.class);
        // ...
    }
}
~~~

This hides dependencies from the constructor and pushes bean creation errors later into method execution.

Prefer constructor injection:

~~~java
@Service
public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    public void execute() {
        paymentClient.pay();
    }
}
~~~

Mandatory dependencies become clear right when the context creates the bean. If missing, Spring fails fast and logs point to the constructor parameter.

Accessing `ApplicationContext` directly makes sense in specialized infrastructure/extension cases, not as a default way to avoid declaring dependencies.

## 42. @Autowired(required=false), Optional, and ObjectProvider

A genuinely optional dependency can be expressed clearly.

### Optional

~~~java
@Service
public class NotificationService {

    private final Optional<PushSender> pushSender;

    public NotificationService(Optional<PushSender> pushSender) {
        this.pushSender = pushSender;
    }
}
~~~

When no `PushSender` exists, `Optional` is empty.

### ObjectProvider

~~~java
@Service
public class ReportService {

    private final ObjectProvider<ReportExporter> exporters;

    public ReportService(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void export() {
        ReportExporter exporter = exporters.getIfAvailable();
        if (exporter == null) {
            // Handle missing optional exporter.
            return;
        }

        exporter.export();
    }
}
~~~

`ObjectProvider` supports on-demand dependency resolution and options like fetching an available candidate.

### Do Not Make Mandatory Dependencies Optional to Hide Errors

If the application cannot run without `PaymentGateway`, changing it to `Optional<PaymentGateway>` and skipping when empty pushes failures later and makes bugs harder to trace.

Use optional injection only when domain requirements genuinely permit the dependency to be absent.

## 43. @Lazy and Errors Delayed Until Runtime

A lazy bean may not instantiate at context startup. That lets the app boot even though the bean fails later.

Example:

~~~java
@Service
@Lazy
public class ExternalCatalogClient {

    public ExternalCatalogClient(CatalogSettings settings) {
        validate(settings);
    }
}
~~~

When the first request accesses `ExternalCatalogClient`, Spring creates the bean and throws `BeanCreationException` right then.

### Why Does This Matter?

Seeing `BeanCreationException` in logs minutes after startup does not mean Spring restarted or initial context startup failed. A lazy/scoped bean may simply have been created on first request access.

Check timestamps, threads, request/job contexts, and bean scopes to tell whether failure happened at startup or runtime.

## 44. Bean Scopes and Proxies Can Also Cause Creation Errors

Scopes like request/session or custom scopes require an active scope context. Accessing a scoped bean outside a request context without an appropriate proxy triggers scope errors.

Example:

~~~java
@Component
@RequestScope
public class RequestMetadata {

    private String requestId;
}
~~~

A singleton should not directly hold a request-scoped instance created at startup. Use a scoped proxy or provider per appropriate design.

When errors report no active request scope, the issue is not a missing constructor dependency in the usual sense—it is a **lifecycle/scope mismatch**.

## 45. Dependency Versions and Classpath Causing Bean Creation Failures

A bean can fail due to incompatible external libraries:

- API class exists yet expected method/class is missing in the loaded version.
- Two versions of the same library coexist.
- Runtime scope excluded a dependency present at compile time.
- JNI/native library architecture mismatches.
- Framework starters pull unwanted auto-configurations.
- Jakarta/Javax namespace mismatch across versions.

Example errors:

~~~text
NoSuchMethodError
NoClassDefFoundError
AbstractMethodError
LinkageError
~~~

These can fire inside constructors or init callbacks and get wrapped in `BeanCreationException`.

### Inspecting the Dependency Tree

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Use dependency insight to see why a version was chosen:

~~~bash
./gradlew dependencyInsight \
  --dependency some-library \
  --configuration runtimeClasspath
~~~

Never randomly upgrade/downgrade all dependencies. Locate the mismatched artifact and version, check the BOM/Boot dependency management, and verify library compatibility matrices.

## 46. Difference Between NoSuchBeanDefinitionException and NoUniqueBeanDefinitionException

Both commonly occur during dependency resolution:

| Exception | Meaning |
|---|---|
| `NoSuchBeanDefinitionException` | No matching bean found |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist without a single unique candidate |

Example:

~~~java
public CheckoutService(PaymentGateway gateway) {
}
~~~

- Zero `PaymentGateway` beans → missing bean.
- Both `CardGateway` and `WalletGateway` without qualifier/primary → multiple beans.

The remedies differ completely. Adding another implementation in the second case makes matters worse.

## 47. BeanDefinitionOverrideException Is Not BeanCreationException

When two configurations register beans with the same name in a context where overriding is disallowed, Spring reports a bean definition conflict such as `BeanDefinitionOverrideException`.

This is a **definition registration** issue occurring before objects are created.

Example:

~~~java
@Configuration
class FirstConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new CardGateway();
    }
}
~~~

~~~java
@Configuration
class SecondConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new WalletGateway();
    }
}
~~~

Both methods share bean name `paymentGateway`. If both configurations load and overriding is off, the context fails while registering definitions.

Fixes:

- Use distinct bean names if both must coexist.
- Use profiles/conditions so only one registers.
- Use `@ConditionalOnMissingBean` for default auto-configurations.
- Use qualifiers/primary if multiple implementations are intentional.

Do not enable bean definition overriding globally to mask poorly understood conflicts.

## 48. Checking @ConditionalOnProperty and What Configuration Actually Loaded

A bean may not be created because of:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "feature.search",
        name = "enabled",
        havingValue = "true"
)
SearchService searchService() {
    return new SearchService();
}
~~~

Intended configuration:

~~~yaml
feature:
  search:
    enabled: true
~~~

Yet runtime may receive:

~~~text
FEATURE_SEARCH_ENABLED=false
~~~

from an environment variable or higher-precedence property source.

Then the condition does not match and the bean is skipped. Dependent services requiring `SearchService` then trigger bean creation failures.

### How to Investigate

- Check active profiles.
- Check effective property values.
- Check command-line args, system properties, and environment variables.
- Enable the condition evaluation report via `--debug`.
- Verify property spelling and value types.
- Confirm configuration files loaded from the expected locations.

Do not look only at `application.yml` in source and assume it reflects final runtime values.

## 49. When Should You Use ApplicationContextRunner?

When errors involve auto-configurations or conditions, a small test isolates them quickly:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(AuditConfiguration.class)
        .withPropertyValues("demo.audit.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

For auto-configuration:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        AuditAutoConfiguration.class
                )
        )
        .withPropertyValues("demo.audit.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

To assert context fails when a dependency is missing:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(RequiredClientConfiguration.class)
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
~~~

The runner excels at conditions and bean registration. When verifying full application startup with databases, messaging, and web servers, use broader integration tests.

## 50. Complete Example: Constructor, Dependency, and Init Callback

Suppose a notification service requires three things:

1. A `MessageTransport` bean.
2. A valid endpoint property.
3. Transport connecting cleanly when the service initializes.

Properties:

~~~java
@ConfigurationProperties(prefix = "notify")
@Validated
public class NotifyProperties {

    @NotNull
    private URI endpoint;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Transport:

~~~java
public interface MessageTransport {
    void connect(URI endpoint);
    void close();
}
~~~

Implementation:

~~~java
@Component
public class HttpMessageTransport implements MessageTransport {

    @Override
    public void connect(URI endpoint) {
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                    "Notification endpoint must use HTTPS"
            );
        }
    }

    @Override
    public void close() {
        // Close resources.
    }
}
~~~

Service:

~~~java
@Service
public class NotificationService {

    private final NotifyProperties properties;
    private final MessageTransport transport;

    public NotificationService(
            NotifyProperties properties,
            MessageTransport transport
    ) {
        this.properties = properties;
        this.transport = transport;
    }

    @PostConstruct
    void initialize() {
        transport.connect(properties.getEndpoint());
    }
}
~~~

Configuration:

~~~yaml
notify:
  endpoint: http://notify.internal
~~~

Startup fails in `@PostConstruct` because the endpoint uses HTTP instead of HTTPS per the example contract.

### Reading the Failure

- `NotifyProperties` binds cleanly because the URL is a valid URI.
- `MessageTransport` injects cleanly.
- `NotificationService` instantiates.
- `initialize()` invokes the transport.
- The transport throws `IllegalArgumentException`.
- Spring reports `BeanCreationException` for `notificationService`.

### Right Fix

~~~yaml
notify:
  endpoint: https://notify.internal
~~~

If development requires HTTP, define an explicit environment-aware policy and test it separately. Never strip validation just to erase the stack trace.

### Design Improvement If connect Makes Network Calls

If `connect` can block or rely on the network, avoid calling it inside `@PostConstruct`. Let transport construct a lightweight client at startup and use health/readiness or a managed startup workflow to check connectivity. Decide based on whether the service can safely operate while the partner is unavailable.

## 51. Testing Constructor/Init Logic Separately

When initialization logic can be extracted into plain Java classes, unit test it directly.

Validator example:

~~~java
public final class EndpointValidator {

    public void validate(URI endpoint) {
        if (endpoint == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                    "HTTPS endpoint is required"
            );
        }
    }
}
~~~

Unit test:

~~~java
@Test
void rejectsHttpEndpoint() {
    EndpointValidator validator = new EndpointValidator();

    assertThatThrownBy(() ->
            validator.validate(URI.create("http://example.test"))
    ).isInstanceOf(IllegalArgumentException.class);
}
~~~

This pure test verifies validation logic. It does not prove Spring calls `@PostConstruct` properly, so add a context test when verifying integration lifecycle.

### Testing Lifecycle via Context

~~~java
@Test
void contextFailsForInvalidEndpoint() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues(
                    "notify.endpoint=http://notify.internal"
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

This assumes `NotificationConfiguration` registers the required properties, transport, and service.

Passing test:

~~~java
@Test
void contextStartsForValidEndpoint() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues(
                    "notify.endpoint=https://notify.internal"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(
                        NotificationService.class
                );
            });
}
~~~

If `connect` performs real network calls, substitute a fake transport in tests to keep tests independent of external endpoints.

## 52. When Is @SpringBootTest Needed?

Use `@SpringBootTest` when testing broader scope, such as:

- Does the main application configuration start cleanly?
- Does component scanning locate the right beans?
- Do profiles and application configs load as in production?
- How do auto-configurations interact?
- Is database/messaging/web infrastructure wired properly?
- Does the full application bean lifecycle complete?

Example:

~~~java
@SpringBootTest
class ApplicationStartupTests {

    @Test
    void contextLoads() {
    }
}
~~~

This smoke test is useful yet slower and can fail for many reasons. When it fails, still read the root cause rather than blaming "the contextLoads test is broken."

### Combine Narrow and Broad Tests

- Unit tests: pure constructor/init logic.
- ApplicationContextRunner: narrow conditions and configurations.
- Spring context tests: wiring in a selective context.
- `@SpringBootTest`: application-wide integration.
- Container/native smoke tests: actual runtime artifacts.

Each layer answers a different question.

## 53. Quick Classification Table by Root Cause

| Root cause / exception | Meaning | First Thing to Check |
|---|---|---|
| `NoSuchBeanDefinitionException` | Missing bean | Component scan, profiles, conditions, config imports |
| `NoUniqueBeanDefinitionException` | Multiple matching beans | `@Primary`, `@Qualifier`, bean conditions |
| `BeanCurrentlyInCreationException` | Dependency cycle / bean mid-creation | Constructor graph and circular references |
| `BeanInstantiationException` | Could not instantiate | Constructor/factory method and underlying exception |
| `UnsatisfiedDependencyException` | Dependency unresolved | Cited parameter/field/method |
| `BindException` or binding error | Property unbindable | Property key, type, conversion, and source |
| `ConstraintViolationException` in binding path | Property violates validation | Constraint and runtime value |
| `ExceptionInInitializerError` | Static initialization failed | Static blocks/fields and environment |
| `NoClassDefFoundError` | Class missing or failed init | Runtime dependencies/versions/classpath |
| `NoSuchMethodError` | API/library version mismatch | Dependency tree and BOM |
| `IllegalStateException` from init | Init invariant violated | `@PostConstruct`, init method, state/config |
| `IOException` | File/resource/I/O failure | Path, permissions, mounts, content |
| `SQLException` | Database operation failed | URL, credentials, driver, schema/network |
| `BeanDefinitionOverrideException` | Bean definitions collide on name | Config imports, bean names, conditions |

Exceptions may be wrapped across multiple layers. Identify which exception is the direct cause and which merely reports the container error.

## 54. Misconceptions to Avoid

### "BeanCreationException means that bean's constructor has a bug"

False. The bean may have instantiated cleanly while a dependency, property population, init callback, or BeanPostProcessor failed.

### "The first bean in the log is the class to fix"

Not necessarily. The first bean may merely be a consumer unable to start because a deeper dependency failed.

### "Adding @Component fixes any missing bean"

Only when the class actually belongs in component scan and is not excluded by conditions. If no implementation exists, a profile mismatches, or a dependency is absent from the classpath, the annotation alone solves nothing.

### "Enabling allow-circular-references fixes the dependency graph"

It may allow certain setter/field cycles to pass, yet does not solve constructor cycles in general and leaves design coupling intact. Break the dependency cycle.

### "@Lazy makes broken beans disappear"

It merely delays instantiation and pushes the failure into runtime. It does not make a broken bean valid.

### "@DependsOn injects beans beforehand"

It controls ordering, does not replace constructor injection, and does not break dependency cycles.

### "Swallowing exceptions in @PostConstruct means the app started safely"

False. The bean may be left unusable. If adopting degraded mode, represent state and health/readiness explicitly.

### "Spring rolls back every side effect when context fails"

False. Container cleanup is not a distributed transaction. External side effects must be managed separately.

### "Successful context startup proves all beans are valid"

Not when lazy, prototype, scoped beans, or late runtime code paths exist.

## 55. Practical Diagnostic Checklist

When facing `BeanCreationException`, follow these steps:

1. **Read the entire startup failure.** Do not stop at the first or last line.
2. **Identify the bean name and failing operation.** Constructor, dependency, init, factory method, or processor?
3. **Trace every nested exception.** Record the specific root cause.
4. **Check dependency parameters.** Missing candidate or multiple candidates?
5. **Check constructors/factory methods.** Any throwing logic or ambiguous overloads?
6. **Check lifecycle callbacks.** What side effects do `@PostConstruct`, `afterPropertiesSet`, or custom init methods perform?
7. **Check properties.** Keys, precedence, conversion, validation, active profiles.
8. **Check conditions and auto-configuration.** Was a bean skipped or duplicated?
9. **Check circular dependencies.** Sketch the dependency graph if needed.
10. **Check external resources.** Database, broker, files, TLS, network, credentials, and timeouts.
11. **Check the runtime classpath.** Missing class, version conflict, wrong scope?
12. **Check bean scope/lazy behavior.** Did the error occur at startup or on first access?
13. **Enable debug/condition reports when justified.** Do not leave verbose logging on indefinitely.
14. **Fix the root cause.** Avoid catch-alls, broad scans, or enabling circular references to mask bugs.
15. **Run matching tests.** From unit tests to context runners or full integration tests.
16. **Check cleanup and side effects.** Ensure failed startups do not leave stray external resources behind.

## Conclusion

`BeanCreationException` signals that Spring could not finish creating a bean, yet it is usually just **a container-boundary wrapper message**. The true cause may live in a constructor, dependency resolution, factory method, property binding, initialization callback, BeanPostProcessor, FactoryBean, class loading, or an external service called during initialization.

Reliable diagnosis starts by reading the bean name and failure stage, tracing the `Caused by` chain, finding the concrete root cause, and cross-referencing the dependency graph and runtime configuration. `NoSuchBeanDefinitionException` points to missing candidates; `NoUniqueBeanDefinitionException` points to ambiguity; `BeanCurrentlyInCreationException` points to dependency cycles; and `Invocation of init method failed` points to `@PostConstruct`, `InitializingBean`, or custom init methods.

Constructors should declare mandatory dependencies and avoid heavy side effects. Init callbacks need timeouts, cleanup, and explicit fail-fast or degraded-mode policies. For configuration bugs, narrow tests with `ApplicationContextRunner` verify conditions and bean registration; for full application wiring or external resources, write matching integration tests.

By separating **bean creation errors, dependency errors, and root causes**, you avoid patching upstream controllers or services by mistake. Instead, you pinpoint the exact condition preventing Spring from assembling the object graph and restore startup verifiably.
