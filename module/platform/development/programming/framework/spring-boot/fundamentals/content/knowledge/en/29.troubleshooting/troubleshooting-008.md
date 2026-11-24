# BeanNotOfRequiredTypeException and Actual Proxy Types

A Spring bean may be declared using a concrete Java class, yet the object returned by the container at runtime **does not necessarily have that exact class**. Spring may wrap a bean in a proxy to apply transactions, security, caching, async execution, aspects, or scopes. Consequently, when code requests a specific implementation class while Spring returns a proxy implementing only an interface, the application can fail with:

~~~text
org.springframework.beans.factory.BeanNotOfRequiredTypeException:
Bean named 'paymentService' is expected to be of type
'com.example.payment.PaymentServiceImpl' but was actually of type
'jdk.proxy2.$Proxy...'
~~~

This message indicates that a bean with the requested name exists, yet **the runtime type of the object is not assignable to the type requested by the caller**.

This lesson **Spring Boot Fundamentals → Troubleshooting → BeanNotOfRequiredTypeException and Actual Proxy Types** explains what this exception signifies, why JDK dynamic proxies and CGLIB proxies produce different runtime types, the impact of AOP features, how to diagnose target classes and proxy classes, and how to choose appropriate injection contracts and proxy strategies.

## 1. Understanding BeanNotOfRequiredTypeException Messages

Suppose an application defines a service:

~~~java
package com.example.payment;

public class PaymentServiceImpl {
    public void pay() {
        // Process payment.
    }
}
~~~

Code looks up the bean by name with a required type:

~~~java
PaymentServiceImpl service =
        applicationContext.getBean(
                "paymentService",
                PaymentServiceImpl.class
        );
~~~

This call asks Spring for the bean named `paymentService` and ensures the returned object is assignable to `PaymentServiceImpl`.

In Java terms, the check corresponds to:

~~~java
PaymentServiceImpl.class.isInstance(bean)
~~~

If the actual bean is a proxy implementing only the `PaymentService` interface, that condition is false. Spring cannot cast that proxy object to `PaymentServiceImpl`, so it throws `BeanNotOfRequiredTypeException`.

| Component | Meaning |
|---|---|
| Bean name | Requested bean name, e.g., `paymentService` |
| Required type | Type the caller expects to receive, e.g., `PaymentServiceImpl` |
| Actual type | Runtime class of the object Spring actually returns, e.g., `jdk.proxy2.$Proxy...` |

**The exception does not necessarily mean the bean is missing.** It usually means Spring found an object under that name, yet the object does not satisfy the requested type.

### 1.1. Error Example with a JDK Proxy

Define an interface and implementation:

~~~java
package com.example.payment;

public interface PaymentService {
    void pay();
}
~~~

~~~java
package com.example.payment;

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {
        // Process payment.
    }
}
~~~

When Spring creates a JDK dynamic proxy, the returned object may have a runtime type like `jdk.proxy2.$Proxy42`.

The proxy implements `PaymentService`, yet it is not a subclass of `PaymentServiceImpl`.

Therefore:

~~~java
PaymentService service =
        applicationContext.getBean(
                "paymentService",
                PaymentService.class
        );
~~~

succeeds, whereas:

~~~java
PaymentServiceImpl service =
        applicationContext.getBean(
                "paymentService",
                PaymentServiceImpl.class
        );
~~~

can throw `BeanNotOfRequiredTypeException`.

This is a classic example of **the target's declared class differing from the proxy's runtime type**.

## 2. What Is a Proxy and Why Does Spring Create Proxies?

A proxy is an object placed in front of another object to control or augment behavior when methods are invoked.

In Spring, proxies typically handle cross-cutting concerns outside core business logic:

- Opening and committing/rolling back transactions.
- Checking access permissions.
- Reading and writing caches.
- Executing methods asynchronously.
- Applying logging, tracing, or profiling via aspects.
- Enforcing bean scopes such as request/session scope in certain models.

The call flow looks like:

~~~text
Caller
  |
  v
Spring proxy
  |
  +-- Check permissions
  +-- Begin transaction
  +-- Run interceptors/aspects
  |
  v
Target object
  |
  v
Result or exception
  |
  v
Proxy completes interceptors
  |
  v
Caller receives result
~~~

Callers generally only need the contract exposed by the bean. The proxy orchestrates work before and after delegating to the target.

**A proxy is not a copy of the target object.** It is a separate object that may have a different runtime class, and whether it can be cast to the target implementation depends on the proxy type.

### 2.1. Example with @Transactional

~~~java
@Service
public class PaymentServiceImpl implements PaymentService {

    @Override
    @Transactional
    public void pay() {
        // Database operations inside transaction.
    }
}
~~~

When transaction management is enabled, Spring can create a proxy to intercept calls to `pay()`, start a transaction before invoking the target, and commit or roll back afterward.

Callers injecting the bean from the container receive the **managed proxy**, not necessarily the raw `new PaymentServiceImpl()` instance.

### 2.2. Not Every Bean Is Proxied

A bean is proxied only when a mechanism requires it, such as:

- Matching advisors/aspects exist.
- Annotations handled by proxy-based infrastructure are present.
- The bean resides in a scope requiring a scoped proxy.
- A post-processor or framework feature wraps it in a proxy.

If no mechanism needs to proxy a bean, the returned object may be a direct instance of the implementation class.

Do not look at a class annotated with `@Service` and assume it must be a JDK proxy or a CGLIB proxy. Inspect the actual runtime object.

## 3. Two Common Proxy Types: JDK Dynamic Proxies and CGLIB

Spring AOP typically uses one of two strategies:

1. **JDK dynamic proxy:** generates a proxy object implementing interfaces.
2. **CGLIB class-based proxy:** generates a proxy subclass extending the target class and overriding interceptable methods.

| Characteristic | JDK Dynamic Proxy | CGLIB Proxy |
|---|---|---|
| Mechanism | Implements interfaces | Subclasses target class |
| Runtime type | Class such as `$Proxy...` | Class such as `TargetClass$$SpringCGLIB$$...` |
| Assignable to target's implemented interfaces | Yes | Yes, inherits interfaces |
| Assignable to concrete target class | No | Usually yes, since proxy is a subclass |
| Final target class | Can proxy interface even if implementation is final | Cannot subclass a final class |
| Final methods | Interface calls can still be intercepted via proxy | Final methods cannot be overridden for interception |
| No interface | Not applicable | Works if class can be subclassed |
| Main constraint | Must have interfaces to expose | Class/methods must be overridable |

### 3.1. JDK Dynamic Proxy

~~~java
public interface ReportService {
    void generate();
}

public class ReportServiceImpl implements ReportService {
    @Override
    public void generate() {
        // Generate report.
    }
}
~~~

A JDK proxy implements `ReportService`:

~~~text
ReportService
      ^
      |
jdk.proxy2.$Proxy42
      |
      +-- invocation handler
                |
                v
          ReportServiceImpl
~~~

Yet the proxy does not extend `ReportServiceImpl`:

~~~java
Object proxy = /* JDK proxy */;

System.out.println(proxy instanceof ReportService);
// true

System.out.println(proxy instanceof ReportServiceImpl);
// false
~~~

This is the direct reason lookups by concrete implementation fail.

### 3.2. CGLIB Class-Based Proxy

With CGLIB, Spring generates a subclass of the implementation:

~~~text
ReportServiceImpl
       ^
       |
ReportServiceImpl$$SpringCGLIB$$0
       |
       +-- method interception
                |
                v
          target object
~~~

Because the proxy is a subclass:

~~~java
Object proxy = /* CGLIB proxy */;

System.out.println(proxy instanceof ReportServiceImpl);
// true
~~~

This allows lookups or injection by concrete class to work in cases where JDK proxies would be incompatible.

However, CGLIB does not eliminate every type limitation. It cannot extend `final` classes, nor override `final` methods to apply interception. `private` methods are also not overridden by subclass proxying.

## 4. Target Class, Proxy Class, and Required Type

Suppose code declares:

~~~java
@Service
public class InvoiceService implements InvoiceOperations {

    @Override
    public void issueInvoice() {
        // Business logic.
    }
}
~~~

The target object has class `com.example.invoice.InvoiceService`. Yet once Spring applies AOP, the returned object may be:

~~~text
jdk.proxy2.$Proxy57
~~~

or:

~~~text
com.example.invoice.InvoiceService$$SpringCGLIB$$0
~~~

Distinguish:

- **Declared type:** type declared on a field, parameter, or method return type.
- **Target class:** class of the object holding the business logic behind the proxy.
- **Proxy class:** runtime class of the object the caller receives from Spring.
- **Exposed interfaces:** interfaces advertised by the proxy to callers.
- **Required type:** type requested by the caller during lookup or injection.

A proxy represents a target class without being that target class. Avoid using `bean.getClass()` to infer the business class directly when beans may be proxied.

## 5. Injecting Implementation Instead of Interface

Design:

~~~java
public interface OrderOperations {
    void createOrder();
}
~~~

~~~java
@Service
public class OrderService implements OrderOperations {

    @Override
    @Transactional
    public void createOrder() {
        // Save order.
    }
}
~~~

Consumer injects the interface:

~~~java
@Service
public class CheckoutFacade {

    private final OrderOperations orderOperations;

    public CheckoutFacade(OrderOperations orderOperations) {
        this.orderOperations = orderOperations;
    }
}
~~~

This suits JDK proxies because the proxy exposes the `OrderOperations` interface.

Conversely:

~~~java
@Service
public class CheckoutFacade {

    private final OrderService orderService;

    public CheckoutFacade(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

If the bean is created as a JDK proxy exposing only `OrderOperations`, a consumer requesting `OrderService` is incompatible.

Depending on dependency resolution paths and bean metadata, startup failures may report either no matching candidate or an incompatible actual type. The core point remains: **the caller requests a concrete class while the exposed object is not an instance of that class**.

### 5.1. Why Is Injecting Interfaces Usually Better?

Injecting interfaces helps:

- Callers depend on contracts rather than implementations.
- Implementations can be swapped without modifying consumers.
- Compatibility with JDK dynamic proxies.
- Tests easily substitute fakes or mocks.
- Limits caller access to internal target details.
- Reduces coupling between modules.

~~~java
public interface PaymentOperations {
    PaymentResult pay(PaymentCommand command);
}
~~~

~~~java
@Service
public class PaymentService implements PaymentOperations {
    @Override
    public PaymentResult pay(PaymentCommand command) {
        // ...
    }
}
~~~

~~~java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }
}
~~~

The consumer knows only `PaymentOperations`. Spring can supply either a target or a proxy as long as the object satisfies the interface.

You do not need to create an interface for every class just to dodge exceptions. Interfaces are valuable when expressing contracts, boundaries, or substitutability. For internal classes needing no abstraction, class-based proxies can also work within their constraints.

## 6. Lookup by Bean Name and Required Type

An API prone to surfacing this exception is:

~~~java
<T> T getBean(String name, Class<T> requiredType)
~~~

Example:

~~~java
PaymentService service =
        context.getBean("paymentService", PaymentService.class);
~~~

Spring locates the bean by name and checks whether the returned object is assignable to `requiredType`.

| Call | Meaning |
|---|---|
| `getBean("paymentService")` | Retrieves the object by name, returning `Object` |
| `getBean("paymentService", PaymentService.class)` | Retrieves by name and requires compatibility with the interface |
| `getBean("paymentService", PaymentServiceImpl.class)` | Retrieves by name and requires compatibility with the implementation |

For a JDK proxy exposing `PaymentService`, interface lookup works; concrete implementation lookup fails.

A diagnostic snippet:

~~~java
Object bean = context.getBean("paymentService");

System.out.println(bean.getClass().getName());

PaymentService contract =
        context.getBean("paymentService", PaymentService.class);
~~~

If output shows `jdk.proxy2.$Proxy...`, that indicates the object is a JDK dynamic proxy. Next, inspect the interfaces exposed by the proxy and the underlying target class.

Do not try to fix it with a cast:

~~~java
PaymentServiceImpl implementation =
        (PaymentServiceImpl) context.getBean("paymentService");
~~~

If the object is a JDK proxy, casting throws `ClassCastException`. Casting cannot turn a proxy object into a subclass of the target.

## 7. @Qualifier and @Primary Cannot Fix Runtime Type Errors

`@Qualifier` picks a matching bean among multiple candidates. `@Primary` prioritizes one candidate when multiple beans match.

Example:

~~~java
@Autowired
@Qualifier("paymentService")
private PaymentOperations payments;
~~~

This selects the bean named `paymentService` under the `PaymentOperations` contract.

However, if you write:

~~~java
@Autowired
@Qualifier("paymentService")
private PaymentServiceImpl payments;
~~~

`@Qualifier` only selects the candidate by identifier. It **does not turn a JDK proxy into a `PaymentServiceImpl`**.

Similarly, `@Primary` does not change a proxy's runtime class. If the chosen bean remains a JDK proxy incompatible with the concrete type, the type error persists.

Answer both questions separately: did you select the right bean, and is the exposed object actually assignable to the required type?

## 8. @Bean Factory Methods and Declared Return Types

Another source of confusion is the declared return type of `@Bean` methods.

~~~java
@Bean
PaymentOperations paymentService() {
    return new PaymentService();
}
~~~

Spring sees the declared return type `PaymentOperations`. That suffices to match lookups by interface, yet may not provide enough metadata to predict the concrete implementation before the bean is instantiated.

If code elsewhere requests `PaymentService`, candidate matching can fail even before AOP proxies come into play.

Declaring a concrete return type gives Spring richer metadata:

~~~java
@Bean
PaymentService paymentService() {
    return new PaymentService();
}
~~~

Yet if Spring subsequently wraps that bean in a JDK proxy, the runtime object may still expose only the interface.

Therefore:

- `@Bean` return types affect pre-instantiation type prediction.
- Proxy strategy governs the runtime object type exposed.
- The two issues are related yet distinct.

A stable design generally has consumers depend on interfaces while factory methods declare return types carrying enough metadata for actual needs.
## 21. @Async and Proxies: Runtime Type Is Not the Only Concern

§@Async§ typically uses proxies to dispatch method calls to an executor.

~~~java
public interface ReportOperations {
    CompletableFuture<String> generate();
}
~~~

~~~java
@Service
public class ReportService implements ReportOperations {

    @Override
    @Async
    public CompletableFuture<String> generate() {
        return CompletableFuture.completedFuture("done");
    }
}
~~~

Consumers should inject the interface:

~~~java
@Service
public class ReportControllerFacade {

    private final ReportOperations reports;

    public ReportControllerFacade(ReportOperations reports) {
        this.reports = reports;
    }
}
~~~

If the proxy is a JDK dynamic proxy, injecting §ReportService§ may be incompatible.

Additionally, §@Async§ has proxy-mode limitations:

- Only calls from another bean through the proxy are intercepted normally.
- Self-invocation within the same instance does not run asynchronously.
- Called methods must conform to proxy and executor rules.
- Exceptions in async methods propagate through futures or async handlers rather than synchronously to callers.

When diagnosing, separate two questions: **is the caller receiving the right proxy type** and **does the invocation actually pass through the proxy**.

## 22. @Transactional: Do Not Unwrap the Target to Call Methods Directly

A common misguided workaround is extracting the target object from the proxy to invoke it directly:

~~~java
PaymentServiceImpl target =
        (PaymentServiceImpl) AopProxyUtils.getSingletonTarget(bean);
~~~

or using test utilities to unwrap targets.

Doing so bypasses the interceptor chain:

- Transactions do not open as expected.
- Security advice is skipped.
- Caching stops working.
- Metrics/tracing advice is bypassed.
- Callers become coupled to internal implementations.

In production code, call through the proxy contract provided by the container:

~~~java
PaymentOperations payments =
        context.getBean(PaymentOperations.class);

payments.pay();
~~~

If you need to test pure target logic, unit test the implementation directly or test with fake dependencies. Never turn proxy unwrapping into a normal service access pattern.

## 23. Diagnosing by Stack Trace and Required/Actual Types

When encountering the exception, read these three values first:

1. **Bean name:** which bean is being resolved?
2. **Required type:** which type did the caller ask for?
3. **Actual type:** what runtime class does the returned object have?

Example:

~~~text
Bean named 'orderService'
is expected to be of type
'com.example.orders.OrderService'
but was actually of type
'jdk.proxy2.$Proxy81'
~~~

You can reason:

- Bean §orderService§ exists.
- The caller requested §OrderService§.
- The actual object is a JDK proxy.
- You need to inspect which interfaces the proxy implements.
- If §OrderService§ is an implementation class and the proxy exposes only an interface, requesting the concrete type is incompatible.

Next, find the lookup site:

~~~java
context.getBean("orderService", OrderService.class);
~~~

or injection:

~~~java
@Autowired
private OrderService orderService;
~~~

or an API indirectly requesting beans by name/type.

Locate **where the type is requested**, not only where the class is defined. The exception surfaces at the bean lookup boundary, while the design cause may lie in proxy configuration or injection contracts.

## 24. Step-by-Step Diagnostic Workflow

### Step 1 — Read the Actual Type in the Exception

If it is §jdk.proxy...§, inspect the interfaces exposed by the proxy. If it is §$$SpringCGLIB$$§, check the target class and subclassing constraints. If it is an unrelated class, check bean registration.

### Step 2 — Identify the Required Type

Determine whether code asks for an implementation class, an interface, or a supertype.

### Step 3 — Identify How the Bean Is Retrieved

Look for:

- §getBean(name, requiredType)§.
- §@Autowired§ or constructor injection.
- §@Resource(name)§.
- §ObjectProvider<T>§ or §Provider<T>§.
- Factory methods, scoped proxies, or FactoryBeans.
- Test override configurations.

### Step 4 — Verify Whether a Proxy Was Created

Use §AopUtils.isAopProxy§, §isJdkDynamicProxy§, §isCglibProxy§, and §getTargetClass§.

### Step 5 — Identify Which Advisor Proxied the Bean

Look for §@Transactional§, §@Async§, §@Cacheable§, §@PreAuthorize§, custom aspects, and post-processors.

### Step 6 — Compare Environments

If the error happens only in production or one profile, compare:

- §spring.aop.proxy-target-class§.
- Transaction/async/security configurations.
- Dependencies and versions.
- Profile-specific bean definitions.
- Custom BeanPostProcessors.
- Test overrides or mock configurations.

### Step 7 — Fix at the Contract or Proxy Strategy

Prefer depending on the appropriate interface. If a concrete type is genuinely required, consider class-based proxies and verify the target class can be subclassed.

### Step 8 — Add a Regression Test

Write a context test with matching advisors/proxies asserting the consumer can inject/invoke the expected contract.

Do not tweak a property and declare victory; tests must prove **the application's actual access path** works.

## 25. Example: Fixing a Consumer Injecting an Implementation

### Problematic Code

~~~java
public interface CustomerService {
    Customer findById(long id);
}
~~~

~~~java
@Service
public class CustomerServiceImpl implements CustomerService {

    @Override
    @Transactional(readOnly = true)
    public Customer findById(long id) {
        // Query customer.
        return null;
    }
}
~~~

~~~java
@Service
public class CustomerControllerFacade {

    private final CustomerServiceImpl service;

    public CustomerControllerFacade(CustomerServiceImpl service) {
        this.service = service;
    }
}
~~~

If Spring exposes the bean via a JDK proxy implementing only §CustomerService§, a consumer requesting §CustomerServiceImpl§ is incompatible.

### Fix Using the Interface

~~~java
@Service
public class CustomerControllerFacade {

    private final CustomerService service;

    public CustomerControllerFacade(CustomerService service) {
        this.service = service;
    }
}
~~~

No changes to §CustomerServiceImpl§ logic are needed. The caller uses the contract, and Spring can provide either the target or a compatible proxy.

### Why Is This Usually the Better Choice?

The consumer does not need to know whether transactions are applied by a proxy, an aspect, or another implementation. It only needs an object fulfilling §CustomerService§.

That is a design benefit, not just a workaround for the exception.

## 26. When Is a Class-Based Proxy a Reasonable Choice?

Sometimes a project lacks a separate interface for a bean or must expose a concrete class due to design constraints.

In that case, consider:

~~~properties
spring.aop.proxy-target-class=true
~~~

Or the specific configuration for the AOP/transaction mechanism in use.

Before choosing it, verify:

- The target class is not final.
- Methods needing interception are not final/private/static.
- You do not rely on self-invocation to trigger advice.
- Proxy classes can be generated in the runtime/module environment.
- Changing the strategy does not negatively impact other beans.
- The consumer genuinely needs the concrete type rather than unnecessarily coupling to an implementation.

Class-based proxies do not expose the raw target object directly; callers still interact with a proxy subclass. The subclass simply happens to be assignable to the target class.

## 27. Do Not Confuse AOP Proxies with @Configuration Proxies

Spring uses CGLIB to subclass §@Configuration§ classes to intercept calls between §@Bean§ methods when §proxyBeanMethods=true§.

Example:

~~~java
@Configuration
public class AppConfiguration {

    @Bean
    FirstService firstService() {
        return new FirstService();
    }

    @Bean
    SecondService secondService() {
        return new SecondService(firstService());
    }
}
~~~

In full configuration mode, Spring intercepts the §firstService()§ call to return the managed singleton bean instead of creating a new instance.

This is a **configuration class proxy**, distinct from AOP proxies wrapping services for transactions/security.

When configuring:

~~~java
@Configuration(proxyBeanMethods = false)
~~~

interception between §@Bean§ methods is disabled; do not call another §@Bean§ method directly expecting it to return the container-managed singleton. Instead, inject dependencies via factory method parameters:

~~~java
@Bean
SecondService secondService(FirstService firstService) {
    return new SecondService(firstService);
}
~~~

Do not see §$$SpringCGLIB$$§ in a class name and assume every CGLIB proxy comes from §@Transactional§. Identify the bean type and proxy purpose.

## 28. Common Bad Fixes

| Fix | Why It May Be Wrong |
|---|---|
| Casting a JDK proxy to the implementation | The object is not an instance of the implementation |
| Turning on CGLIB globally immediately | Hits final classes/methods and affects many beans |
| Adding §@Primary§ | Only prioritizes candidates; does not change proxy type |
| Adding §@Qualifier§ | Only selects a bean; does not convert a proxy into the target class |
| Removing §@Transactional§ | Strips required transactional behavior |
| Unwrapping the target in production | Bypasses interceptors and breaks container contracts |
| Comparing §bean.getClass()§ against the implementation class | Proxy classes differ even when the bean works properly |
| Using reflection to access target fields | Couples to internals and breaks easily |
| Creating §new PaymentServiceImpl()§ in consumers | Bypasses Spring DI, proxies, transactions, and lifecycle |
| Renaming beans randomly | Does not solve mismatch between required type and actual type |
| Disabling AOP globally | Disables transactions, security, caching, or async |

Identify the actual cause before changing configuration.

## 29. Writing Regression Tests for Proxy Contracts

A good regression test reproduces the mechanism causing the failure.

For example, using §ProxyFactory§ to build a JDK proxy and verify:

~~~java
@Test
void jdkProxyExposesInterfaceButNotImplementation() {
    GreetingService target = new GreetingService();

    ProxyFactory factory = new ProxyFactory();
    factory.setTarget(target);
    factory.setInterfaces(GreetingOperations.class);
    factory.setProxyTargetClass(false);

    Object proxy = factory.getProxy();

    assertTrue(proxy instanceof GreetingOperations);
    assertFalse(proxy instanceof GreetingService);
}
~~~

You can then assert interface lookup succeeds and implementation lookup fails using §DefaultListableBeanFactory§:

~~~java
@Test
void typedLookupRejectsIncompatibleProxy() {
    GreetingService target = new GreetingService();

    ProxyFactory factory = new ProxyFactory();
    factory.setTarget(target);
    factory.setInterfaces(GreetingOperations.class);
    factory.setProxyTargetClass(false);

    Object proxy = factory.getProxy();

    DefaultListableBeanFactory beanFactory =
            new DefaultListableBeanFactory();

    beanFactory.registerSingleton("greeting", proxy);

    assertNotNull(
            beanFactory.getBean(
                    "greeting",
                    GreetingOperations.class)
    );

    assertThrows(
            BeanNotOfRequiredTypeException.class,
            () -> beanFactory.getBean(
                    "greeting",
                    GreetingService.class)
    );
}
~~~

This test isolates the bean factory and proxy contract. In a real application, also add context-level tests for actual AOP configuration to confirm the intended advisors and proxy strategy apply.

### Consumer Tests Should Inject the Contract

~~~java
@SpringBootTest
class CheckoutFacadeTest {

    @Autowired
    CheckoutFacade checkoutFacade;

    @Autowired
    PaymentOperations paymentOperations;

    @Test
    void injectsProxyThroughInterface() {
        assertNotNull(checkoutFacade);
        assertNotNull(paymentOperations);
    }
}
~~~

If the goal is proving transaction advice executes, test transactional behavior as well rather than only asserting bean injection.

## 30. Debugging in Debuggers and Logs

When inspecting a bean object at a breakpoint, check:

~~~java
bean.getClass().getName()
~~~

Then:

~~~java
AopUtils.isAopProxy(bean)
AopUtils.isJdkDynamicProxy(bean)
AopUtils.isCglibProxy(bean)
AopUtils.getTargetClass(bean)
~~~

Controlled diagnostic logging:

~~~java
log.debug(
        "Resolved bean name={} runtimeType={} targetType={} jdkProxy={} cglibProxy={}",
        beanName,
        bean.getClass().getName(),
        AopUtils.getTargetClass(bean).getName(),
        AopUtils.isJdkDynamicProxy(bean),
        AopUtils.isCglibProxy(bean)
);
~~~

Avoid logging full objects or internal target state. Class names are usually sufficient for investigating proxy strategy.

To inspect interfaces:

~~~java
Class<?>[] interfaces = bean.getClass().getInterfaces();

for (Class<?> contract : interfaces) {
    log.debug("Exposed interface={}", contract.getName());
}
~~~

Note that class-based proxies may inherit interfaces from the target; for a full contract list, inspect the superclass hierarchy as well.

## 31. BeanNotOfRequiredTypeException vs. Similar Exceptions

| Exception | Primary Meaning |
|---|---|
| §BeanNotOfRequiredTypeException§ | Bean under that name produced an object incompatible with required type |
| §NoSuchBeanDefinitionException§ | No matching bean definition/candidate found |
| §NoUniqueBeanDefinitionException§ | Multiple candidates exist without a unique selection |
| §BeanCreationException§ | Error occurred during bean creation |
| §UnsatisfiedDependencyException§ | Dependency could not be resolved or injected |
| §ClassCastException§ | Java code manually cast an object to an incompatible type |
| §NoSuchMethodException§ | Reflection could not find the requested method |

During startup, one exception can wrap another. For instance, §UnsatisfiedDependencyException§ may contain an underlying §BeanNotOfRequiredTypeException§.

When reading stack traces, locate the **root cause** and the first line of application code requesting the bean.

Do not read only the outermost exception and tweak configuration randomly.

## 32. Beans Implementing Multiple Interfaces

An implementation may implement multiple interfaces:

~~~java
public class AccountService
        implements AccountOperations, AuditOperations {
    // ...
}
~~~

A JDK proxy can expose both interfaces if both are included in the proxy configuration.

Callers can then inject:

~~~java
AccountOperations accounts;
~~~

or:

~~~java
AuditOperations audit;
~~~

However, if the proxy is created with only §AccountOperations§, a caller requesting §AuditOperations§ remains incompatible even though the target class implements it.

Therefore, with JDK proxies, **do not check only which interfaces the target class implements; check which interfaces the proxy actually exposes**.

If an advisor or proxy factory is configured with a restricted interface set, that set dictates which contracts callers can use.

## 33. Nested Proxies and Target Classes

In applications with extensive infrastructure, a bean may pass through multiple proxy or wrapper layers. For example, security, transaction, or custom instrumentation proxies may combine or wrap across layers depending on configuration.

In such cases:

- §bean.getClass()§ shows only the outermost class.
- §AopUtils.getTargetClass(bean)§ helps determine the target class recognized by Spring.
- §AopProxyUtils.ultimateTargetClass(bean)§ helps determine the ultimate target class in supported scenarios.
- Obtaining the actual target object may be restricted by proxies, scopes, or target sources.

Do not write production logic that depends on successfully unwrapping every proxy layer. Proxies are container implementation details; the stable contract should be the interface or class the bean commits to exposing.

## 34. Design Principles to Prevent Future Errors

1. **Inject by contract:** prefer interfaces when beans are exposed via interfaces.
2. **Do not cast to target:** avoid casting proxies to implementations.
3. **Create beans via the container:** never manually §new§ services in consumers.
4. **Keep factory method types clear:** declare return types reflecting contracts and needed metadata.
5. **Know your proxy strategy:** know whether the project uses JDK or class-based proxies.
6. **Respect CGLIB limits:** final classes/methods and self-invocation.
7. **Do not use qualifiers to fix mismatches:** qualifiers only pick candidates.
8. **Test real wiring:** verify actual contexts and proxies when features rely on AOP.
9. **Do not hardcode runtime proxy class names in tests:** use §AopUtils§.
10. **Preserve AOP behavior:** never remove transactions/security/caching just to avoid exceptions.
11. **Identify advisors:** know which annotations or post-processors create proxies.
12. **Distinguish AOP proxies from scoped/configuration proxies:** they serve different purposes.

## 35. Practice Exercises

### Exercise 1: Reproducing a JDK Proxy

Create interface §GreetingOperations§ and class §GreetingService§ implementing it.

Use §ProxyFactory§:

~~~java
factory.setTarget(new GreetingService());
factory.setInterfaces(GreetingOperations.class);
factory.setProxyTargetClass(false);
~~~

Check:

- Is the proxy an instance of §GreetingOperations§?
- Is the proxy an instance of §GreetingService§?
- Which class does §bean.getClass()§ return?

**Goal:** directly observe why target class and proxy class differ.

### Exercise 2: Reproducing BeanNotOfRequiredTypeException

Register the JDK proxy in §DefaultListableBeanFactory§ under the name §greeting§.

Try:

~~~java
beanFactory.getBean("greeting", GreetingOperations.class);
~~~

Then:

~~~java
beanFactory.getBean("greeting", GreetingService.class);
~~~

Explain the difference based on assignability checks.

### Exercise 3: Fixing Injection

A consumer injects:

~~~java
private final PaymentServiceImpl paymentService;
~~~

while the bean is exposed as a JDK proxy implementing §PaymentOperations§.

Update the consumer to inject §PaymentOperations§ and explain why this fix requires no changes to the target implementation.

### Exercise 4: Comparing CGLIB

Recreate the proxy with:

~~~java
factory.setProxyTargetClass(true);
~~~

Check §instanceof GreetingService§. Then mark the target class §final§ and observe class-based proxy creation failing.

### Exercise 5: Distinguishing Proxy Errors from Bean Name Errors

Create a bean named §paymentService§ whose factory method returns a §String§. Call §getBean("paymentService", PaymentOperations.class)§.

Explain why the actual type §String§ indicates a bean registration mistake rather than a JDK proxy issue.

### Exercise 6: Observing Runtime Beans in Spring Boot

Create a service with an interface and enable an advisor such as transactions or an aspect. Inject the bean by interface, then print:

~~~java
AopUtils.isAopProxy(bean)
AopUtils.isJdkDynamicProxy(bean)
AopUtils.isCglibProxy(bean)
AopUtils.getTargetClass(bean)
~~~

Change proxy configuration in a test environment and observe the runtime types. Do not rely on fixed names like §$Proxy42§ as they are unstable.

## 36. Checklist for Investigating a Real Failure

When facing §BeanNotOfRequiredTypeException§, answer in order:

- Which bean name appears in the exception?
- Is the required type an interface or a concrete class?
- Is the actual runtime type a JDK proxy, CGLIB proxy, or another class?
- What is the actual target class?
- Which interfaces does the proxy expose?
- Does the bean have §@Transactional§, §@Async§, §@Cacheable§, security annotations, or custom aspects?
- Does the consumer inject by interface or implementation?
- Was the bean created via §@Component§, §@Bean§, or §FactoryBean§?
- Which profile is active?
- Are there bean overrides, aliases, or test mocks?
- Is §spring.aop.proxy-target-class§ overridden?
- Is the target class final, or are intercepted methods final/private?
- Is self-invocation preventing advice from running?
- Can the consumer be updated to depend on the contract?
- Does the regression test reproduce the real proxy strategy?

You do not need to tweak every setting. Accurate answers for required type, actual type, and bean registration usually narrow down the cause.

## Conclusion

§BeanNotOfRequiredTypeException§ occurs when a bean is requested by name yet the object Spring returns is **incompatible with the type requested by the caller**. A frequent cause is Spring AOP wrapping an implementation in a **JDK dynamic proxy**, which exposes interfaces without extending the concrete target class.

Distinguish:

- **Target class:** the class holding business logic.
- **Proxy class:** the runtime class received by callers.
- **Required type:** the type callers attempt to inject or look up.
- **Exposed interface:** the contract the proxy actually supports.

JDK proxies align with interface-oriented designs; CGLIB creates subclasses compatible with concrete classes yet constrained by final classes/methods and self-invocation. Features like transactions, async, caching, security, and scoped proxies all influence the exposed object type.

When diagnosing, read the bean name, required type, and actual type from the exception; use §AopUtils§ to inspect proxies; check bean registration and injection paths. **Prefer having consumers depend on interfaces exposed by proxies**, switching to class-based proxies only with clear justification and when target classes satisfy constraints. Never cast proxies, unwrap targets in business code, or disable AOP merely to silence exceptions.

Understanding runtime proxy types fixes errors at their root while preserving vital behaviors Spring wraps around beans such as transactions, security, and caching.
+## 9. Spring Features That Can Create Proxies

§BeanNotOfRequiredTypeException§ is not limited to §@Transactional§. These features can also create proxies:

| Feature | Proxy Purpose | Things to Note |
|---|---|---|
| §@Transactional§ | Transaction boundary | Inject via interface when using JDK proxies |
| §@Async§ | Dispatch calls to an executor | Self-invocation may bypass the proxy |
| §@Cacheable§ | Read/write cache around methods | Do not force beans to target class unnecessarily |
| §@PreAuthorize§ | Method permission checks | Proxy must expose the right contract |
| Custom §@Aspect§ | Logging, metrics, auditing | Advisors can cause beans to be wrapped |
| Scoped proxy | Represents shorter-lived scoped beans | Proxy has its own type; targets resolve per scope |
| Method validation | Applies validation via interceptors | Object type may be a proxy |

If a bean has multiple advisors simultaneously, Spring usually combines them in a single proxy chain. Callers still interact with the exposed proxy object.

## 10. JDK Proxies Can Work with Final Target Classes

An important point: JDK proxies do not need to extend the target class. They only implement interfaces.

~~~java
public interface PaymentOperations {
    void pay();
}
~~~

~~~java
public final class PaymentService implements PaymentOperations {
    @Override
    public void pay() {
        // ...
    }
}
~~~

A JDK proxy can still implement §PaymentOperations§ and delegate to the final §PaymentService§ instance.

However, CGLIB needs to create a subclass:

~~~text
PaymentService$$SpringCGLIB$$0 extends PaymentService
~~~

If §PaymentService§ is final, that cannot happen. CGLIB cannot subclass a final class.

Thus, if a project enables class-based proxies and encounters errors with final classes, options include:

- Using JDK proxies via interfaces.
- Removing §final§ if design permits and subclass proxying is intended.
- Moving the intercepted behavior to another proxyable bean.
- Choosing another suitable interception mechanism.

Do not remove §final§ everywhere without understanding why the class was designed as immutable or final.

## 11. CGLIB Limitations: final, private, and Self-Invocation

CGLIB proxies rely on subclassing and method overriding. Consequently:

- Final classes cannot be subclassed.
- Final methods cannot be overridden for interception.
- Private methods cannot be overridden this way.
- Static methods are not instance methods overridden by proxies.
- Self-invocation typically bypasses the proxy.

Example:

~~~java
@Service
public class BillingService {

    public void createInvoice() {
        calculateTax();
    }

    @Transactional
    public void calculateTax() {
        // ...
    }
}
~~~

When §createInvoice()§ calls §calculateTax()§ via §this.calculateTax()§, the internal call bypasses the outer proxy. Transaction advice on the internal method will not apply as expected in proxy mode.

A cleaner design moves the intercepted part into another bean:

~~~java
@Service
public class TaxService {

    @Transactional
    public void calculateTax() {
        // ...
    }
}
~~~

~~~java
@Service
public class BillingService {

    private final TaxService taxService;

    public BillingService(TaxService taxService) {
        this.taxService = taxService;
    }

    public void createInvoice() {
        taxService.calculateTax();
    }
}
~~~

Now the call passes through the injected §TaxService§ proxy bean from the container.

This is not directly §BeanNotOfRequiredTypeException§, yet often surfaces alongside it when developers change proxy strategies without understanding proxy boundaries.

## 12. Configuring proxy-target-class in Spring Boot

You can adjust the proxy strategy via property:

~~~properties
spring.aop.proxy-target-class=true
~~~

Setting §true§ requests class-based proxies within Spring Boot's AOP auto-configuration scope where applicable.

Setting §false§ allows JDK dynamic proxies when beans have suitable interfaces:

~~~properties
spring.aop.proxy-target-class=false
~~~

Spring Framework also provides annotation settings:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = true)
~~~

Transaction management has its own setting:

~~~java
@EnableTransactionManagement(proxyTargetClass = true)
~~~

Inspect the effective configuration because multiple AOP auto-proxy mechanisms in Spring can merge into a shared auto-proxy creator. Enabling class-based proxies in one place can influence proxy creation across multiple advisors.

### 12.1. Spring Boot's Default May Be Class-Based Proxies

In many standard Spring Boot configurations using AOP auto-configuration, §spring.aop.proxy-target-class§ defaults to §true§. Still, do not infer from that default that **every bean in the application is guaranteed to be a CGLIB proxy**:

- A bean may not need proxying.
- Separate AOP/transaction configurations may exist.
- Another framework or post-processor may be involved.
- Some beans use dedicated proxy strategies.
- Settings may be overridden by profiles, environment variables, or command-line args.

Check effective configuration and actual runtime classes.

### 12.2. Is Enabling CGLIB the Best Fix?

If the error occurred solely because a consumer injected the implementation while the bean was a JDK proxy, enabling class-based proxies lets concrete injection work when the class can be subclassed.

Yet this is not a universal fix:

- Final target classes cannot be proxied that way.
- Final methods are not intercepted.
- It can alter proxy types of other beans.
- It encourages tighter coupling to implementation classes.
- It does not fix a bean name pointing to the wrong bean.
- It does not fix wrong return types or unrelated dependencies.
- It does not fix self-invocation calls.

**Prefer updating injection contracts to match the interface exposed by the proxy.** Choose CGLIB only when there is a clear design reason to expose concrete classes.

## 13. Detecting Runtime Proxies in Code

Spring AOP provides utilities to inspect proxies.

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("paymentService");

Class<?> runtimeType = bean.getClass();

System.out.println("Runtime type: " + runtimeType.getName());
System.out.println("Is AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("Is JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("Is CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("Target class: " +
        AopUtils.getTargetClass(bean).getName());
~~~

Useful methods:

| API | Question Answered |
|---|---|
| §bean.getClass()§ | What is the runtime class of the object held by the caller? |
| §AopUtils.isAopProxy(bean)§ | Is the object a Spring AOP proxy? |
| §AopUtils.isJdkDynamicProxy(bean)§ | Is it a JDK dynamic proxy? |
| §AopUtils.isCglibProxy(bean)§ | Is it a CGLIB proxy? |
| §AopUtils.getTargetClass(bean)§ | What target class can Spring determine behind it? |

§getTargetClass()§ identifies the class behind the proxy, yet **does not mean the returned object has become an instance of the target class**.

Example:

~~~java
Object bean = context.getBean("paymentService");

System.out.println(bean instanceof PaymentService);
// true if the proxy exposes the interface

System.out.println(bean instanceof PaymentServiceImpl);
// false if this is a JDK proxy exposing only the interface
~~~

§AopUtils.getTargetClass(bean)§ can return §PaymentServiceImpl.class§ while §bean.getClass()§ remains §jdk.proxy2.$Proxy...§.

Those answer two different questions: what is the target class, and what runtime type is the proxy object.

## 14. Inspecting Interfaces Exposed by a Proxy

To diagnose a JDK proxy, inspect the runtime class's interfaces:

~~~java
Object bean = context.getBean("paymentService");

for (Class<?> type : bean.getClass().getInterfaces()) {
    System.out.println(type.getName());
}
~~~

For JDK dynamic proxies, the interface list generally represents the contract exposed by the proxy.

You can check directly:

~~~java
boolean supportsContract =
        PaymentOperations.class.isInstance(bean);
~~~

This assignability check is better than comparing runtime class names against implementation names.

Do not treat a CGLIB proxy's runtime interface list as its entire contract; a proxy subclass can inherit interfaces from the target class and superclasses.

## 15. Inspecting Bean Types Before and After Instantiation

Spring's BeanFactory offers helpful APIs:

~~~java
boolean matches =
        beanFactory.isTypeMatch(
                "paymentService",
                PaymentOperations.class
        );
~~~

~~~java
Class<?> predictedType =
        beanFactory.getType("paymentService");
~~~

~~~java
String[] names =
        beanFactory.getBeanNamesForType(
                PaymentOperations.class
        );
~~~

These reveal how Spring predicts or recognizes beans by type.

Keep in mind:

- §getType()§ may return a predicted type from the bean definition/factory method.
- The pre-creation predicted type can differ from the runtime class after post-processors wrap a proxy.
- §isTypeMatch()§ depends on metadata and factory/proxy type resolution.
- Not every FactoryBean or lazy bean exposes its full runtime type prior to creation.

Therefore, when investigating exceptions, compare **bean metadata** against **the actual object once retrieved**. Never rely solely on a single type-prediction API.

## 16. Reproducing the Exception with ProxyFactory

You can reproduce the difference between JDK proxies and target implementations using Spring AOP's §ProxyFactory§.

Interface:

~~~java
public interface GreetingOperations {
    String greet();
}
~~~

Implementation:

~~~java
public class GreetingService implements GreetingOperations {

    @Override
    public String greet() {
        return "Hello";
    }
}
~~~

Create JDK proxy:

~~~java
ProxyFactory factory = new ProxyFactory();
factory.setTarget(new GreetingService());
factory.setInterfaces(GreetingOperations.class);
factory.setProxyTargetClass(false);

Object proxy = factory.getProxy();
~~~

Verify:

~~~java
assertTrue(proxy instanceof GreetingOperations);
assertFalse(proxy instanceof GreetingService);
~~~

Then register the proxy in a bean factory:

~~~java
DefaultListableBeanFactory beanFactory =
        new DefaultListableBeanFactory();

beanFactory.registerSingleton("greetingService", proxy);

GreetingOperations operations =
        beanFactory.getBean(
                "greetingService",
                GreetingOperations.class
        );
~~~

Interface lookup matches the proxy type. Concrete class lookup:

~~~java
GreetingService implementation =
        beanFactory.getBean(
                "greetingService",
                GreetingService.class
        );
~~~

throws §BeanNotOfRequiredTypeException§.

This directly demonstrates the contract of §getBean(name, requiredType)§. When turning it into a real test, add imports for §ProxyFactory§, §DefaultListableBeanFactory§, and JUnit assertions.

### 16.1. Reproducing a CGLIB Proxy

Change:

~~~java
factory.setProxyTargetClass(true);
~~~

If the target class is not final and supports subclass proxying, the created object is assignable to §GreetingService§:

~~~java
assertTrue(proxy instanceof GreetingService);
assertTrue(proxy instanceof GreetingOperations);
~~~

This is the core distinction to observe when troubleshooting type errors.

## 17. Testing Proxies in a Spring Context

A context-level test confirms the bean is wrapped and its interface contract works.

~~~java
@SpringBootTest
class PaymentProxyTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    PaymentOperations paymentOperations;

    @Test
    void beanExposesPaymentContract() {
        Object bean = context.getBean("paymentService");

        assertTrue(AopUtils.isAopProxy(bean));
        assertTrue(bean instanceof PaymentOperations);
    }
}
~~~

This example assumes:

- A bean named §paymentService§ exists.
- The bean implements §PaymentOperations§.
- An aspect or transaction advisor actually causes the bean to be proxied.
- The test application context is configured appropriately.

Do not assert §isAopProxy()§ if the test configures no advisors; the bean will not be proxied and the assertion will fail as configured.

### Tests Should Not Hardcode Runtime Proxy Class Names

Do not write:

~~~java
assertEquals(
        "jdk.proxy2.$Proxy42",
        bean.getClass().getName()
);
~~~

Proxy names depend on the JVM, proxy creation order, runtime, and framework. Use instead:

~~~java
assertTrue(AopUtils.isJdkDynamicProxy(bean));
~~~

or:

~~~java
assertTrue(AopUtils.isCglibProxy(bean));
~~~

If the test targets consumer contracts, simply inject and invoke the interface.

## 18. Distinguishing Proxy Errors from Wrong-Bean Selection

Not every §BeanNotOfRequiredTypeException§ is caused by a JDK proxy.

Example with a mismatched bean:

~~~java
@Bean
Object paymentService() {
    return new String("not a payment service");
}
~~~

If bean name §paymentService§ is used to look up §PaymentOperations§, the actual object is a §String§. That is a bean configuration type error, not a proxy error.

Other causes:

- Duplicate bean names or aliases pointing to an unintended bean.
- A §@Bean§ factory method returning a different implementation.
- Profile configurations creating different beans across local and production.
- A §FactoryBean§ returning a product of an unexpected type.
- Test beans replacing production beans with mocks/fakes of the wrong contract.
- Bean definitions overridden by another configuration.
- Callers requesting a concrete class while the bean is exposed via a proxy.

| Symptom | Where to Investigate |
|---|---|
| Actual type is §jdk.proxy...§ | Check JDK proxy and exposed interfaces |
| Actual type contains §$$SpringCGLIB$$§ | Check class-based proxy and target class |
| Actual type is an unrelated class | Check bean name, alias, factory method, and profile |
| §getType()§ returns interface yet caller requests implementation | Check declared bean type and proxy strategy |
| Fails only in one profile | Compare bean definitions and config sources per profile |
| Fails only in tests | Check mock beans, §@TestConfiguration§, context caching |

**Never change proxy strategy before checking the actual type.** If the actual bean is the wrong object altogether, enabling CGLIB will not solve the cause.

## 19. FactoryBean and Exposed Objects

Spring's §FactoryBean<T>§ interface allows a factory to create objects exposed by the container as bean products.

General example:

~~~java
public class PaymentClientFactory
        implements FactoryBean<PaymentOperations> {

    @Override
    public PaymentOperations getObject() {
        return createClient();
    }

    @Override
    public Class<?> getObjectType() {
        return PaymentOperations.class;
    }
}
~~~

When retrieving by regular name, callers receive the FactoryBean's **product**. To fetch the factory itself, use the §&§ prefix convention:

~~~java
Object product = context.getBean("paymentClient");
Object factory = context.getBean("&paymentClient");
~~~

If callers confuse the product with the factory or vice versa, requested types will be incompatible.

During diagnosis, verify whether the bean name refers to a FactoryBean and which object the caller expects. Do not assume every actual type differing from a class is an AOP proxy.

## 20. Scoped Proxies Also Have Their Own Runtime Types

Some beans have scopes shorter than singleton, such as request scope in web apps. When a singleton needs a reference to a request-scoped bean, Spring uses a scoped proxy.

Example:

~~~java
@Component
@RequestScope
public class RequestContextData {

    public String requestId() {
        return "current-request";
    }
}
~~~

A singleton can inject §RequestContextData§ via a scoped proxy. The proxy outlives per-request target objects; each request resolves its own target.

The proxy may be interface-based or class-based depending on configuration and bean types.

Key points:

- The proxy is not the target object of one specific request.
- Do not store request-scoped targets outside the request lifecycle.
- Do not cast the proxy to an internal class not exposed by the proxy.
- In tests, an active web request scope is required when calling methods that access the target.

Scoped proxies are another reason §getClass()§ differs from the class the bean author might expect.
