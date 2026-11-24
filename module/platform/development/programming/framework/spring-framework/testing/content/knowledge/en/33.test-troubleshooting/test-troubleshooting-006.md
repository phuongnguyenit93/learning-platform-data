# Spy Behind an AOP Proxy and Verifying the Wrong Object

When testing a Spring bean with a Mockito spy, a common bug is invoking the right bean in the ApplicationContext yet calling `verify()` on a different object. This issue easily happens when the bean is wrapped by a Spring AOP proxy, when the test creates its own separate spy, or when multiple beans share the same type.

Mockito can only verify mock/spy objects that it manages. An ordinary Spring AOP proxy is not automatically a Mockito spy. Conversely, a Mockito spy may sit inside an AOP proxy. Therefore, you need to understand which object is injected into the test, which object receives the call, and which object is actually the Mockito spy.

This lesson focuses on diagnosing bean identity, distinguishing proxies from targets, picking the right reference for `verify()`, and avoiding altering AOP behavior during testing.

## 1. Why Can `verify` Target the Wrong Object?

Suppose an application has a service:

~~~java
@Service
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void pay(String orderId) {
        gateway.charge(orderId);
    }
}
~~~

The test wants to verify that `PaymentGateway.charge()` was called:

~~~java
paymentService.pay("ORDER-42");
verify(paymentGateway).charge("ORDER-42");
~~~

The assertion is only valid if the `paymentGateway` variable passed to `verify` is the exact Mockito spy that received the call. If that variable is a separate mock/spy created manually by the test, or a Spring proxy that is not a Mockito spy, Mockito cannot verify the expected interaction.

Common scenarios:

- The test uses `@Spy` to create a separate object, while the service in the ApplicationContext still injects the original bean.
- The test calls a bean fetched from Spring yet verifies an instance created with `new`.
- Spring AOP wraps the target with a proxy, while the test verifies either the proxy or a non-spy target.
- Multiple beans implement the same interface; the test spies one bean, but the service injects another due to a qualifier or `@Primary`.
- The test unwraps the target object to invoke it directly, inadvertently bypassing the proxy and its advices.

Common error message:

~~~text
org.mockito.exceptions.misusing.NotAMockException:
Argument passed to verify() is not a mock!
~~~

This message means the object passed to `verify(...)` is not a Mockito mock or spy. It does not mean the service never called the method; first, locate the right reference.

## 2. Distinguishing Bean, Target, AOP Proxy, and Mockito Spy

In Spring, a bean can be wrapped by multiple layers of objects:

~~~text
Injected test field / reference
              |
              v
      Spring AOP proxy
      (transaction, security,
       cache, retry, ...)
              |
              v
       Mockito spy target
              |
              v
        Real bean instance
~~~

This is a typical structure when an AOP proxy delegates to a target that is a Mockito spy. The actual structure can differ depending on when the bean is post-processed and how the spy is registered:

- The Mockito spy may be the outer object wrapping the proxy.
- The Spring AOP proxy may sit outside the Mockito spy.
- A bean may not be AOP-proxied at all.
- Multiple proxies may be nested.

Key terms:

| Component | Meaning |
|---|---|
| Bean reference | The object Spring returns when retrieving a bean from ApplicationContext or injecting into a field. |
| Target object | The instance executing the real logic behind an AOP proxy. |
| AOP proxy | The intermediary object applying advice before/after calling the target. |
| Mockito spy | An object whose interactions Mockito tracks while delegating to real calls by default. |
| Injected spy | The spy reference registered and injected into the test by Spring Test; it may still sit inside another proxy. |

Do not assume that `bean`, `proxy`, `target`, and `spy` are always the exact same object. They may share the same declared type or delegate to the same instance, yet differ in identity and role.

## 3. What Are AOP Proxies Created For?

Spring AOP uses proxies to apply cross-cutting concerns such as:

- `@Transactional`: transaction management.
- `@Cacheable`: reading/writing caches.
- `@PreAuthorize`: access control checks.
- `@Retryable`: retrying failed invocations.
- Custom aspects: logging, metrics, auditing, or tracing.

Example:

~~~java
@Service
class OrderService {

    @Transactional
    public void placeOrder(String orderId) {
        // Record the order.
    }
}
~~~

When another bean calls `orderService.placeOrder(...)` through the Spring-injected reference, the call goes through the proxy. The proxy runs transaction advice before invoking the target.

Diagram:

~~~text
Controller
    |
    | orderService.placeOrder(...)
    v
Spring AOP proxy
    |
    | start transaction
    v
OrderService target
    |
    | execute logic
    v
Spring AOP proxy
    |
    | commit / rollback transaction
    v
Controller receives result
~~~

The proxy is the object Spring uses to intercept calls. It is not automatically a Mockito spy. If a test wants to verify interactions, it must find the actual Mockito spy reference within this structure.

## 4. JDK Dynamic Proxy vs. CGLIB Proxy

Spring AOP can create proxies in two common ways:

| Proxy type | Characteristics | Testing note |
|---|---|---|
| JDK dynamic proxy | The proxy implements the target's interfaces. | Injecting by interface is usually safe; casting the proxy to the implementation class can fail. |
| CGLIB proxy | The proxy is a generated subclass of the target class. | The reference may look like the implementation type, yet it is still not the original target instance. |

Example of a service with an interface:

~~~java
public interface OrderOperations {
    void placeOrder(String orderId);
}

@Service
class OrderService implements OrderOperations {

    @Override
    @Transactional
    public void placeOrder(String orderId) {
        // Record the order.
    }
}
~~~

If Spring uses a JDK dynamic proxy, the reference implements `OrderOperations` rather than `OrderService`. Therefore, tests should inject by interface when the bean contract is an interface:

~~~java
@Autowired
OrderOperations orderOperations;
~~~

Do not cast arbitrarily:

~~~java
OrderService service = (OrderService) applicationContext.getBean(OrderOperations.class);
~~~

The cast above can fail when the bean is a JDK proxy.

## 5. Using a Spring-Managed Spy Instead of Creating a Separate Spy

If you need to observe a bean that actually lives in the ApplicationContext, use Spring Test's spy bean mechanism.

With Spring Framework 6.2 and later, you can use `@MockitoSpyBean`:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class OrderServiceTests {

    @MockitoSpyBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderService orderService;

    @Test
    void callsPaymentGateway() {
        orderService.pay("ORDER-42");

        verify(paymentGateway).charge("ORDER-42");
    }
}
~~~

`@MockitoSpyBean` tells Spring Test to wrap the existing bean with a Mockito spy and inject that spy into the test field. When multiple candidates share the same type, use `@Qualifier` or the bean name to select the right candidate.

Example:

~~~java
@MockitoSpyBean
@Qualifier("primaryPaymentGateway")
PaymentGateway paymentGateway;
~~~

In older Spring Boot versions, projects may be using `@SpyBean`:

~~~java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpyBean
PaymentGateway paymentGateway;
~~~

`@SpyBean` was deprecated in Spring Boot 3.4 in favor of Spring Framework's `@MockitoSpyBean`. Use the annotation available in your project's version; do not upgrade dependencies just to change an annotation in a single test.

A spy bean calls the real implementation unless a method is stubbed. Therefore, the test must prepare any database, network, or dependencies used by the real method, or stub the needed methods using spy-safe syntax.

## 6. Why Are `@Spy` and `@MockitoSpyBean` Not Equivalent?

Mockito's `@Spy` creates a spy for an object within the test's own scope:

~~~java
@ExtendWith(MockitoExtension.class)
class LocalSpyTests {

    @Spy
    PaymentGateway paymentGateway = new PaymentGatewayImpl();

    @InjectMocks
    PaymentService paymentService;
}
~~~

This is a pure Mockito unit test. Mockito creates objects and injects dependencies into the instance it manages. The test does not automatically replace beans in a Spring ApplicationContext.

Conversely:

~~~java
@SpringBootTest
class SpringSpyTests {

    @MockitoSpyBean
    PaymentGateway paymentGateway;

    @Autowired
    PaymentService paymentService;
}
~~~

Here, Spring builds the ApplicationContext and Spring Test replaces the bean with a spy managed inside the context. The service created by Spring receives its dependency per the context's bean configuration.

If you combine `@Spy` with `@SpringBootTest` without explicit integration wiring, the test can end up with two objects:

~~~text
Spring ApplicationContext
  PaymentService ---> Real PaymentGateway

Test field
  @Spy PaymentGateway ---> a separate instance
~~~

The service calls the real gateway, while the test verifies the separate spy. The spy records no invocations because it is not inside the service's dependency graph.

Practical rule:

- Pure Mockito unit tests: use `@Mock`, `@Spy`, `@InjectMocks`.
- Spring integration tests: use `@MockitoSpyBean` or the version-compatible annotation to spy a bean in the context.
- Do not create another `Mockito.spy(...)` for the same dependency assuming Spring beans will automatically use it.

## 7. Diagnosing Which Object Is Actually the Spy

When encountering `NotAMockException`, do not guess which object is the spy. Inspect each reference.

Mockito provides:

~~~java
Mockito.mockingDetails(object).isSpy()
Mockito.mockingDetails(object).isMock()
~~~

Spring provides:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.test.util.AopTestUtils;
~~~

`AopUtils.isAopProxy(object)` tells whether a reference is a Spring AOP proxy. `AopTestUtils.getUltimateTargetObject(object)` can unwrap nested Spring AOP proxies to obtain the ultimate target.

Diagnostic example:

~~~java
Object bean = applicationContext.getBean(PaymentGateway.class);
Object target = AopTestUtils.getUltimateTargetObject(bean);

System.out.println("bean is AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("bean is Mockito spy: "
    + Mockito.mockingDetails(bean).isSpy());
System.out.println("target is Mockito spy: "
    + Mockito.mockingDetails(target).isSpy());
~~~

The output helps identify which layer holds the Mockito spy. Do not print full objects or sensitive information in production logs; this snippet is strictly for test diagnostics.

Interpretation table:

| Is bean reference an AOP proxy? | Is bean reference a spy? | Is ultimate target a spy? | Reference to check for `verify` |
|---|---|---|---|
| No | Yes | Possibly the bean itself | The bean reference. |
| Yes | Yes | Not necessarily | The bean reference if `mockingDetails(bean).isSpy()` is true. |
| Yes | No | Yes | The ultimate target, if that is the Mockito spy. |
| Yes | No | No | No Mockito spy found; check how the spy was registered and which dependency was injected. |
| No | No | No | The object is not a Mockito spy; calling `verify()` on it throws `NotAMockException`. |

Important point: `getUltimateTargetObject()` only locates the target behind Spring AOP proxies. Do not call it mechanically and always verify the target. If the Mockito spy sits outside the proxy, the ultimate target may be the real object rather than the spy.

## 8. Verifying on the Right Reference

Suppose the test confirms the injected bean reference is the Mockito spy:

~~~java
orderService.placeOrder("ORDER-42");

verify(paymentGateway, times(1)).charge("ORDER-42");
~~~

If `paymentGateway` is an AOP proxy and the spy sits at the target, retrieve the target and verify it is a spy first:

~~~java
PaymentGateway target =
    AopTestUtils.getUltimateTargetObject(paymentGateway);

assertThat(Mockito.mockingDetails(target).isSpy()).isTrue();
verify(target).charge("ORDER-42");
~~~

The example above is only suitable when the ultimate target is genuinely the Mockito spy. If `isSpy()` returns false, do not proceed to verify that object. Go back to the bean override setup and determine which layer holds the spy.

You can write a diagnostic helper in the test:

~~~java
static <T> T findSpyReference(T bean, Class<T> type) {
    if (Mockito.mockingDetails(bean).isSpy()) {
        return bean;
    }

    Object target = AopTestUtils.getUltimateTargetObject(bean);
    if (type.isInstance(target)
            && Mockito.mockingDetails(target).isSpy()) {
        return type.cast(target);
    }

    throw new AssertionError("No Mockito spy found in bean/proxy chain");
}
~~~

Usage:

~~~java
PaymentGateway spy = findSpyReference(paymentGateway, PaymentGateway.class);
verify(spy).charge("ORDER-42");
~~~

This helper handles only the two most common cases: the bean reference itself is the spy, or the ultimate target is the spy. For custom proxies or multiple non-Spring-AOP wrapper layers, investigate separately; do not treat the helper as a universal unwrapper for every kind of proxy.

## 9. Do Not Call the Target Directly to Execute the Behavior Under Test

`AopTestUtils.getUltimateTargetObject()` is useful for verifying interactions on a spy behind a proxy. However, do not use the unwrapped target to execute the primary action in a test when you want AOP active:

~~~java
// May bypass transaction/security/cache advice.
PaymentService target =
    AopTestUtils.getUltimateTargetObject(orderService);
target.placeOrder("ORDER-42");
~~~

The call above goes straight to the target, bypassing the outer proxy. When the test goal is to verify the behavior of a Spring bean as used in the application, invoke the reference injected from the context:

~~~java
orderService.placeOrder("ORDER-42");
~~~

Only afterward should you use the appropriate spy reference to verify interactions. Separate the two responsibilities:

- **Executing behavior:** invoke the bean via its Spring-managed reference so advice runs.
- **Observing interactions:** verify the actual Mockito spy located in the bean/proxy chain.

## 10. Use `doReturn` When Stubbing a Spy

A spy calls real methods by default. Therefore, the following syntax can execute the real method while declaring the stub:

~~~java
when(paymentGateway.balance("ACCOUNT-1"))
    .thenReturn(new BigDecimal("100.00"));
~~~

If the real method accesses the network, database, or causes side effects, the test can fail right during setup. With spies, you should generally use `doReturn(...).when(...)`:

~~~java
doReturn(new BigDecimal("100.00"))
    .when(paymentGateway)
    .balance("ACCOUNT-1");
~~~

Useful `do...` forms:

~~~java
doReturn(value).when(spy).method();
doThrow(exception).when(spy).method();
doNothing().when(spy).voidMethod();
doAnswer(invocation -> result).when(spy).method();
~~~

`doReturn` avoids calling the real method during stub setup. After setup, calls through the spy return the configured stubbed value.

Stub only the methods you need to control. Over-stubbing can prevent the test from verifying the real behavior it was originally meant to test.

## 11. Verifying Call Counts, Arguments, and Order

Once you have the right spy reference, Mockito supports its familiar verification options:

~~~java
verify(paymentGateway).charge("ORDER-42");
verify(paymentGateway, times(1)).charge("ORDER-42");
verify(paymentGateway, never()).refund("ORDER-42");
verify(paymentGateway, atLeastOnce()).healthCheck();
~~~

Checking arguments:

~~~java
ArgumentCaptor<PaymentRequest> captor =
    ArgumentCaptor.forClass(PaymentRequest.class);

verify(paymentGateway).charge(captor.capture());

assertThat(captor.getValue().orderId()).isEqualTo("ORDER-42");
~~~

Checking call order between two collaborators:

~~~java
InOrder inOrder = inOrder(tokenClient, orderClient);

inOrder.verify(tokenClient).getToken();
inOrder.verify(orderClient).submit(any(OrderRequest.class));
~~~

`InOrder` also requires references to be Mockito mocks or spies. If a variable passed to `inOrder(...)` is merely an AOP proxy and not a spy, Mockito cannot track it.

Do not overuse `verifyNoMoreInteractions()`. That assertion can couple tests to auxiliary calls outside the core contract, making tests brittle when implementations change.

## 12. Multiple Beans of the Same Type: Spy the Exact Bean the Service Uses

Another cause of verifying the wrong object is having multiple beans implement the same interface:

~~~java
@Component("cardGateway")
class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("bankGateway")
class BankPaymentGateway implements PaymentGateway {
    // ...
}
~~~

The service chooses its bean with a qualifier:

~~~java
@Service
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(@Qualifier("bankGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

The test must spy the matching bean as well:

~~~java
@MockitoSpyBean
@Qualifier("bankGateway")
PaymentGateway bankGateway;
~~~

If the test spies `cardGateway` while the service invokes `bankGateway`, verifying on the card spy will see no interactions. This is not a Mockito bug; the test targeted the wrong collaborator.

When multiple candidates exist, use explicit qualifiers or bean names. Do not rely on scan order or assume `@Primary` is identical across all test configurations.

## 13. AOP and Self-Invocation

Spring AOP proxies only apply advice to calls that pass through the proxy. If a method inside the target calls another method on the same instance via `this`, that internal call does not pass through the proxy.

Example:

~~~java
@Service
class ReportService {

    public void generate() {
        this.writeAuditRecord();
    }

    @Transactional
    public void writeAuditRecord() {
        // Record audit.
    }
}
~~~

When `generate()` is called via the proxy, the proxy can apply advice to `generate()`. However, `this.writeAuditRecord()` occurs inside the target and never re-enters the proxy. Consequently, transaction advice on `writeAuditRecord()` is not triggered by that self-invocation.

This is an AOP interception issue, distinct from Mockito spy identity:

- A spy may record that a method was called on the spied object.
- AOP advice only executes when the call passes through the proxy.
- A passing `verify` does not prove that transaction, security, or cache advice ran.

If you need to test the transaction of `writeAuditRecord()`, call the method from outside through the bean proxy or extract that business logic into another injected bean. Do not treat `verify(spy).writeAuditRecord()` as proof that `@Transactional` was applied.

## 14. Verifying Whether AOP Actually Worked

If the test's goal is to confirm that advice was activated, assert the effect produced by the advice instead of merely verifying method invocations.

For example, with transactions, you can check whether a transaction is active inside a collaborator:

~~~java
@Component
class TransactionProbe {

    boolean wasTransactionActive;

    void record() {
        wasTransactionActive =
            TransactionSynchronizationManager.isActualTransactionActive();
    }
}
~~~

Service:

~~~java
@Service
class TransferService {

    private final TransactionProbe probe;

    TransferService(TransactionProbe probe) {
        this.probe = probe;
    }

    @Transactional
    public void transfer() {
        probe.record();
    }
}
~~~

The test can invoke the bean from the context and assert:

~~~java
transferService.transfer();
assertThat(transactionProbe.wasTransactionActive).isTrue();
~~~

This example illustrates checking transaction state. In real tests, a transaction manager and matching transaction configuration must be present.

Similarly:

- For caching, check the cache entry or the actual invocation count of the underlying collaborator.
- For security, verify access control through the proxy and 401/403 outcomes.
- For retry, verify collaborator invocation counts and the post-retry result.
- For custom aspects, check the side effect or metric emitted by the aspect.

Spies and AOP can coexist in one test, but be clear about whether the test is asserting an interaction or asserting advice execution.

## 15. A Complete Example with `@MockitoSpyBean`

Suppose a service calls a real gateway:

~~~java
public interface PaymentGateway {
    void charge(String orderId);
}

@Component
class RemotePaymentGateway implements PaymentGateway {

    @Override
    public void charge(String orderId) {
        // Call the payment system.
    }
}

@Service
class CheckoutService {

    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void checkout(String orderId) {
        gateway.charge(orderId);
    }
}
~~~

Spring test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;

@SpringBootTest
class CheckoutServiceTests {

    @MockitoSpyBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void delegatesChargeToSpringManagedGatewaySpy() {
        checkoutService.checkout("ORDER-42");

        verify(paymentGateway, times(1)).charge("ORDER-42");
    }
}
~~~

Spring injects the spy into the context's dependency graph. The test calls the Spring-managed `CheckoutService`, then verifies the spy reference injected into the test.

If `PaymentGateway` has multiple beans, add `@Qualifier` on the spy field. If the gateway is also wrapped by an AOP proxy, check `AopUtils.isAopProxy(...)` and `Mockito.mockingDetails(...).isSpy()` before deciding whether unwrapping the target is needed for verification.

## 16. Common Symptoms and Resolution Guide

| Symptom | Possible cause | Resolution |
|---|---|---|
| `NotAMockException` | Verifying an ordinary object or a non-spy AOP proxy. | Check `mockingDetails(...).isSpy()`; locate the right spy reference. |
| `verify` sees no invocations | The service uses a different instance from the spy in the test. | Use a Spring-managed spy and verify qualifier/bean name. |
| Verifying the target fails | The spy wraps the outside of the proxy, so the unwrapped target is not a spy. | Check both the bean reference and ultimate target; verify whichever has `isSpy() == true`. |
| Casting proxy to implementation fails | Spring uses a JDK dynamic proxy. | Inject and interact through the interface. |
| Stubbing a spy still runs the real method during setup | Used `when(spy.method()).thenReturn(...)`. | Use `doReturn(...).when(spy).method(...)`. |
| Method verification succeeds yet transaction did not run | Self-invocation bypassed the proxy. | Call via the proxy from another bean or move the method to a collaborator. |
| Verifying the wrong implementation | Multiple beans share the interface. | Use `@Qualifier` or the exact bean name. |
| Test passes alone but fails in the suite | Spy/resource or context is improperly shared or reset. | Check scope, context cache, and reset lifecycle. |

## 17. Resetting Spies and State Between Tests

Spring Test spy beans are normally reset according to the test lifecycle of the bean override mechanism. With `@MockitoSpyBean`, the default reset mode is after each test method. If using the legacy Spring Boot annotation, check its reset attribute and behavior for your Boot version.

Do not hold onto references to unwrapped targets or spies across multiple test methods if the framework resets or replaces beans. Obtain references from the context/test injection within the appropriate test scope.

If a test has multiple phases and needs to retain invocations for later verification, do not reset the spy before verifying. If you need to clear invocation history between two phases, use Mockito's reset APIs intentionally, keeping in mind that `reset` also clears stubbing:

~~~java
clearInvocations(paymentGateway); // Clear invocation history, keep stubbing.
reset(paymentGateway);            // Clear both stubbing and invocation history.
~~~

Only use manual reset when a test genuinely needs multiple phases on the same spy. Normally, each test method should be independent and let Spring Test manage resets.

## 18. Diagnostic Workflow When `verify` Fails

When encountering verification errors on an AOP-proxied bean:

1. **Identify the bean the service actually injects.** Check the constructor, qualifiers, `@Primary`, and bean name.
2. **Take the reference from ApplicationContext or the test field.** Avoid creating extra objects with `new` or `Mockito.spy(...)` outside the context.
3. **Check for a proxy.** Use `AopUtils.isAopProxy(bean)` to see whether the reference is a Spring AOP proxy.
4. **Check for a Mockito spy.** Use `Mockito.mockingDetails(bean).isSpy()` on the reference being verified.
5. **If the reference is an AOP proxy and not a spy, check the ultimate target.** Only verify the target if `mockingDetails(target).isSpy()` returns true.
6. **Execute behavior through the bean proxy.** Do not call the target directly when advice must run.
7. **Verify the right spy reference.** Use `times`, `never`, argument matchers, or captors according to the contract being verified.
8. **If you need to verify AOP advice, check the advice's effect.** Spy interactions do not prove transaction, security, or cache advice executed.

Keep diagnostic snippets inside tests or remove them once the root cause is found. Do not add internal logging or proxy unwrapping in production code just to make Mockito verification easier.

## 19. Tool Selection Guidelines

| Goal | Approach |
|---|---|
| Unit test a class without Spring | Mockito `@Mock`, `@Spy`, `@InjectMocks`. |
| Observe a collaborator in ApplicationContext | `@MockitoSpyBean` or `@SpyBean` on older Boot versions. |
| Verify the selected bean when multiple implementations exist | Spy the exact bean using qualifier or bean name. |
| Diagnose a Spring proxy | `AopUtils.isAopProxy`, `AopTestUtils.getUltimateTargetObject`. |
| Check whether an object is a Mockito spy | `Mockito.mockingDetails(object).isSpy()`. |
| Verify a method was called | `verify()` on the Mockito spy itself. |
| Verify transaction/cache/security advice | Assert the side effect or state created by the advice. |

When working with Spring AOP, never treat the proxy, target, and Mockito spy as the exact same object. Identify which reference the service uses and which reference is actually the spy before calling `verify()`. Execute behavior through the Spring-managed proxy to preserve AOP; only unwrap the target for observation after confirming that target is the Mockito spy. This approach avoids `NotAMockException`, verifying the wrong instance, and tests that pass without testing the bean actually running in the application.
