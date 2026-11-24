# How to Stub and Verify When a Spy Sits Behind a Proxy

In a Spring application, a bean injected into a test may be an AOP proxy rather than the direct business instance. If the target behind the proxy is a Mockito spy, the test is working with two different layers: the Spring proxy controls advice such as transactions, security, or logging; the spy records invocations and enables Mockito stubbing.

To stub and verify correctly, identify which object is the proxy and which object is actually the spy. Typically, use the injected proxy to invoke the behavior under test, and unwrap the target spy with `AopTestUtils` to configure stubs and verify invocations. This keeps real calls flowing through Spring advice while Mockito observes the exact target.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish a Spring AOP proxy from a Mockito spy.
- Describe the call path when a spy sits behind a proxy.
- Retrieve the target object from a proxy using `AopTestUtils`.
- Use `doReturn`, `doThrow`, and `doAnswer` to stub a spy without calling the real method during setup.
- Verify invocations on the exact Mockito spy.
- Invoke through the proxy so Spring advice still executes.
- Distinguish errors when verifying a proxy from errors when verifying a target.
- Understand the impact of JDK dynamic proxies, CGLIB, self-invocation, and bean scopes.
- Use `@MockitoSpyBean` or your project version's corresponding annotation to spy on a bean in a Spring context.

## 1. Two Different Mechanisms: Spring AOP Proxy and Mockito Spy

A Spring AOP proxy and a Mockito spy can both sit in front of an object, yet they solve two different problems.

**A Spring AOP proxy** intercepts method calls to run advice before, after, or around the target call. Features such as `@Transactional`, `@Cacheable`, method security, and custom aspects typically work through proxies.

**A Mockito spy** is a test double backed by a real object. Unless stubbed, the spy normally calls the real implementation. Mockito can record invocations, replace return values of specific methods, or throw exceptions as configured by the test.

When a spy sits behind a Spring proxy, the structure typically looks like this:

~~~mermaid
flowchart LR
    T["Test"] --> P["Spring AOP proxy"]
    P --> A["Advice chain"]
    A --> S["Mockito spy (target)"]
    S --> R["Real implementation"]
~~~

Calls from the test go through the proxy, the advice chain, and then to the spy. If the method is unstubbed, the spy calls the real implementation. If the method is stubbed, the spy returns the configured result.

The two objects have distinct roles:

| Object | Role | Common Operation |
|---|---|---|
| Spring AOP proxy | Ensures calls pass through advice | Invoke the method under test |
| Mockito spy at target | Records invocations and applies stubs | Stubbing and verifying |
| Real implementation | Original business logic | Invoked when the spy has no matching stub |

Do not assume that the object injected into the test is itself the Mockito spy. For an AOP-advised bean, that object may be a Spring proxy wrapping the spy target.

## 2. Why Retrieve the Target from the Proxy?

Suppose a service has a transaction:

~~~java
@Service
public class InventoryService {

    @Transactional(readOnly = true)
    public int available(String sku) {
        // Read inventory quantity from the data source.
        return 10;
    }
}
~~~

When Spring applies transaction advice, the injected bean is usually a proxy. The test receives a reference of type `InventoryService`, yet the runtime instance may be a JDK dynamic proxy or a CGLIB proxy.

If the test wants to configure the Mockito spy sitting at the target, it needs a reference to that target itself. Spring provides the `AopTestUtils` utility in the package:

~~~java
import org.springframework.test.util.AopTestUtils;
~~~

Two useful methods:

- `AopTestUtils.getTargetObject(proxy)`: retrieves the immediate target of one proxy layer.
- `AopTestUtils.getUltimateTargetObject(proxy)`: walks through nested proxies to retrieve the final target.

Example:

~~~java
InventoryService target =
    AopTestUtils.getUltimateTargetObject(inventoryService);
~~~

If the target is a Mockito spy, you can confirm it with:

~~~java
assertTrue(Mockito.mockingDetails(target).isSpy());
~~~

If the result is `false`, do not continue calling `when` or `verify` on that object as if it were a spy. Check how the bean was replaced, whether the spy annotation was applied, and which object Mockito actually manages.

`getUltimateTargetObject` fits proxies with a stable target source, which is common for singleton beans. With a scoped proxy or a target source that creates targets dynamically per call, unwrapping the target once may not represent the target used on another request. Understand the bean's scope before holding a target reference for stubbing or verification.

## 3. Stubbing a Spy with `doReturn` to Avoid Calling the Real Method

With a Mockito spy, the syntax:

~~~java
when(spy.available("SKU-1")).thenReturn(3);
~~~

can invoke the real implementation of `available` during stub setup. This may trigger database queries, HTTP calls, logging, or side effects before the test even starts the behavior under test.

When the spy sits behind a proxy, the issue is even more pronounced: calling the method through the proxy for stubbing can send the call through advice before reaching the target spy. Transactions or side effects could happen during configuration.

Use `doReturn(...).when(spy)...` to set up a stub without calling the real method:

~~~java
doReturn(3)
    .when(targetSpy)
    .available("SKU-1");
~~~

Other do-style forms:

~~~java
doThrow(new IllegalStateException("Inventory unavailable"))
    .when(targetSpy)
    .refresh();

doNothing()
    .when(targetSpy)
    .clearCache();

doAnswer(invocation -> {
    String sku = invocation.getArgument(0);
    return sku.equals("SKU-1") ? 3 : 0;
}).when(targetSpy).available(anyString());
~~~

Choose the stubbing style based on the behavior to simulate:

| Syntax | Purpose |
|---|---|
| `doReturn(value)` | Return a predetermined value |
| `doThrow(exception)` | Throw an exception |
| `doNothing()` | Do nothing for a void method |
| `doAnswer(answer)` | Compute a result from the invocation |
| `doCallRealMethod()` | Instruct the spy to call the real implementation for that method |

With spies, `doReturn` is usually the easiest option to control when the real method has side effects or when the target sits behind a proxy.

## 4. Complete Example with ProxyFactory and a Mockito Spy

We can illustrate the mechanism without starting a full application by creating a Spring AOP proxy directly. This example shows the test stubbing the target spy while invoking the method through the proxy.

Interface and implementation:

~~~java
public interface InventoryService {
    int available(String sku);
}

public class DefaultInventoryService implements InventoryService {

    @Override
    public int available(String sku) {
        // Real implementation in the application may query a repository.
        return 10;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;

import java.util.concurrent.atomic.AtomicInteger;

import org.aopalliance.intercept.MethodInterceptor;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.test.util.AopTestUtils;

class InventoryProxySpyTest {

    @Test
    void stubsAndVerifiesTargetSpyThroughSpringProxy() {
        InventoryService targetSpy =
            Mockito.spy(new DefaultInventoryService());

        AtomicInteger adviceCalls = new AtomicInteger();

        ProxyFactory factory = new ProxyFactory();
        factory.setTarget(targetSpy);
        factory.setInterfaces(InventoryService.class);
        factory.addAdvice((MethodInterceptor) invocation -> {
            adviceCalls.incrementAndGet();
            return invocation.proceed();
        });

        InventoryService proxy =
            (InventoryService) factory.getProxy();

        InventoryService unwrapped =
            AopTestUtils.getUltimateTargetObject(proxy);

        assertSame(targetSpy, unwrapped);
        assertTrue(Mockito.mockingDetails(unwrapped).isSpy());

        doReturn(3)
            .when(unwrapped)
            .available("SKU-1");

        int result = proxy.available("SKU-1");

        assertEquals(3, result);
        verify(unwrapped).available("SKU-1");
        assertEquals(1, adviceCalls.get());
    }
}
~~~

Flow of the test:

1. Mockito creates a spy from the real implementation.
2. `ProxyFactory` sets the spy as the target and builds a Spring AOP proxy.
3. `AopTestUtils.getUltimateTargetObject(proxy)` returns the target spy.
4. `doReturn` configures a return value on the target without calling the real method.
5. The test calls `proxy.available(...)`, so advice still runs.
6. The proxy forwards the call to the target spy; the spy returns the stubbed value and records the invocation.
7. The test verifies the target spy and checks that the advice was invoked.

This example demonstrates a key principle: use the target to configure and observe Mockito, and use the proxy to execute the application path.

## 5. Applying This in Spring Tests with `@MockitoSpyBean`

In Spring Framework 6.2 and later, you can use `@MockitoSpyBean` to have Spring create a spy from an existing bean in the context. Example:

~~~java
@SpringBootTest
class InventoryServiceIntegrationTest {

    @MockitoSpyBean
    InventoryService inventoryService;

    @Test
    void stubsTargetAndInvokesThroughAopProxy() {
        InventoryService target =
            AopTestUtils.getUltimateTargetObject(inventoryService);

        assertTrue(Mockito.mockingDetails(target).isSpy());

        doReturn(3)
            .when(target)
            .available("SKU-1");

        int result = inventoryService.available("SKU-1");

        assertEquals(3, result);
        verify(target).available("SKU-1");
    }
}
~~~

In this example, `inventoryService` is the reference supplied by Spring to the test. If the bean is AOP-proxied, unwrap the ultimate target and confirm that the target is indeed a Mockito spy.

In older Spring Boot projects, you may see `@SpyBean` from `org.springframework.boot.test.mock.mockito`. The supported annotation and behavior depend on the project's Spring Boot/Spring Framework version. Use the annotation available in your current dependencies; do not add two spy mechanisms simultaneously for the same bean.

If the context has multiple beans of the same type, identify the bean explicitly via qualifier or bean name. The spy must be applied to the exact bean the service uses. If the service receives a different implementation, stubbing an unused bean will not affect the outcome.

## 6. Verify on the Target Spy, Do Not Assume Proxy Verification

Mockito `verify` requires a mock or spy managed by Mockito. A Spring AOP proxy by itself is not necessarily a Mockito spy.

If you call:

~~~java
verify(inventoryService).available("SKU-1");
~~~

and `inventoryService` is solely a Spring AOP proxy, Mockito may throw `NotAMockException`. In a structure where a proxy wraps a spy, verify the target:

~~~java
InventoryService target =
    AopTestUtils.getUltimateTargetObject(inventoryService);

verify(target).available("SKU-1");
~~~

You can inspect the object before verifying:

~~~java
assertTrue(Mockito.mockingDetails(target).isSpy());
verify(target).available("SKU-1");
~~~

Do not assume every proxy is unverifiable. In some configurations, the injected object may itself be the Mockito spy or a proxy configured to support target interaction. The reliable way is checking the actual object with `Mockito.mockingDetails(...)` and unwrapping the target when the spy sits behind a Spring AOP proxy.

If you need to confirm that advice ran, verifying the target spy is not enough. The spy records method calls at the target; it does not prove a transaction committed or security advice rejected a request. Verify the advice's effect with dedicated assertions, such as transaction state, audit events, or security outcomes.

## 7. Stubbing and Verifying Void Methods

For `void` methods, use `doNothing`, `doThrow`, or `doAnswer` on the target spy.

Example:

~~~java
public interface InventoryService {
    void refresh(String sku);
}
~~~

Configure without calling the real method during stubbing:

~~~java
doNothing()
    .when(target)
    .refresh("SKU-1");
~~~

Then invoke through the proxy:

~~~java
proxy.refresh("SKU-1");

verify(target).refresh("SKU-1");
~~~

If you want to simulate an error:

~~~java
doThrow(new IllegalStateException("Refresh failed"))
    .when(target)
    .refresh("SKU-1");

assertThrows(
    IllegalStateException.class,
    () -> proxy.refresh("SKU-1")
);

verify(target).refresh("SKU-1");
~~~

If the `void` method actually needs to execute in the test, do not stub it. Call through the proxy and verify the invocation or expected side effect. Stub only when intentionally altering real behavior at a specific point.

## 8. Distinguishing Stubbing via Proxy from Stubbing the Target Directly

The two call approaches can produce different outcomes:

~~~java
// Configure the target spy directly:
doReturn(3).when(targetSpy).available("SKU-1");

// Execute through the Spring proxy:
int result = serviceProxy.available("SKU-1");
~~~

When configuring the target directly, the test does not pass through Spring advice. This is desirable during stubbing because we are only configuring Mockito behavior.

When executing through the proxy, advice runs before the call reaches the target spy. This is the required path if the test wants to preserve transactions, caching, security, or aspects.

If you invoke the target directly to test behavior:

~~~java
int result = targetSpy.available("SKU-1");
~~~

then Spring AOP advice does not run. The test checks only the Mockito spy and the implementation behind it.

Therefore, separate the two purposes clearly:

| Phase | Object to Use | Reason |
|---|---|---|
| Stubbing | Target spy | Configures the right Mockito object |
| Executing AOP-advised behavior | Spring proxy | Keeps advice in the call chain |
| Verifying target invocations | Target spy | Mockito records calls at the spy |
| Verifying advice effects | Advice outcome or state | Proves the AOP portion actually executed |

## 9. How Do JDK Dynamic Proxies and CGLIB Affect This?

Spring AOP typically uses one of two proxy types:

- **JDK dynamic proxy:** the proxy implements the target's interfaces. Consumers typically interact through an interface.
- **CGLIB proxy:** the proxy is a subclass of the target class and overrides proxiable methods.

The proxy type does not change the principle of unwrapping the target spy, but it affects reference types and which methods can be intercepted.

With a JDK proxy, inject and invoke through the interface:

~~~java
@Autowired
InventoryService inventoryService;
~~~

Do not cast a JDK proxy object to a concrete implementation class:

~~~java
DefaultInventoryService service =
    (DefaultInventoryService) inventoryService;
~~~

This cast can fail because the proxy only implements the interface.

With CGLIB, the proxy is a subclass of the target class, yet that still does not make the proxy object a Mockito spy. Inspect the target with `AopTestUtils` and Mockito mocking details rather than inferring from the runtime class.

Spring AOP proxies also have limits on which methods are intercepted. A JDK proxy only handles calls through the interface; CGLIB cannot override `final` or `private` methods. If a method is outside the proxy's scope, tests may hit the implementation without running the expected advice.

## 10. Self-Invocation and Internal Calls

Spring AOP is proxy-based. An external call passing through the proxy can trigger advice. However, if a method on the target calls another method on `this`, that internal call does not pass back through the proxy.

Example:

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        validateOrder();
    }

    @Transactional
    public void validateOrder() {
        // Validation logic.
    }
}
~~~

When a consumer calls `placeOrder()` through the proxy, Spring can intercept `placeOrder`. Yet the internal `this.validateOrder()` call inside the target does not re-enter the proxy, so transaction advice on `validateOrder` is not triggered by that internal call alone.

A Mockito spy may record certain internal calls depending on how the spy and method dispatch operate, but that does not prove Spring AOP advice ran. Check spy invocations and advice effects separately.

If advice must apply to a method, route the call through an appropriate bean/proxy or revisit the service design so the call naturally crosses a proxy boundary.

## 11. Issues with Scoped Proxies and Dynamic Targets

A singleton AOP proxy typically points to a stable target. With request scope, session scope, or prototype scope, the proxy may select different targets depending on context or invocation.

In that case, unwrapping the target once:

~~~java
Object target = AopTestUtils.getUltimateTargetObject(proxy);
~~~

does not guarantee the target used on the next request is the same instance. Holding onto one target spy in a test can cause stubbing and verification to miss invocations on the actual target.

Before using `AopTestUtils`, determine:

- Is the bean a singleton?
- Is the `TargetSource` stable?
- Does the proxy create targets per request or session?
- Is the test running inside the required scope?
- Is the unwrapped target still the instance used by the proxy on later calls?

For scoped beans, use an appropriate test scope and inspect the actual object within that scope. Avoid grabbing a target from one request and using it to verify another request.

## 12. Common Mistakes

- **Calling `verify` on a Spring proxy:** a proxy is not necessarily a Mockito spy. Unwrap the target with `AopTestUtils` and verify the Mockito-managed object.
- **Using `when(spy.method())` when the method has side effects:** Mockito may invoke the real implementation during setup. Use `doReturn`, `doThrow`, or the matching do-style API.
- **Stubbing through the proxy and accidentally running advice:** setup calls may pass through transactions, security, or aspects. Configure the target spy directly.
- **Calling the target instead of the proxy during execution:** the test bypasses Spring AOP advice. Call the proxied bean when testing the production path.
- **Assuming the spy and the proxy are the same object:** use `Mockito.mockingDetails` and `AopTestUtils` to identify each layer clearly.
- **Using `Mockito.spy` directly on a Spring proxy:** wrapping a proxy can alter how proxy and target behave. Prefer Spring's spy bean mechanism or intentionally spying on the target.
- **Casting a JDK proxy to an implementation class:** JDK proxies usually implement only interfaces. Inject and use the interface.
- **Verifying a spy and concluding a transaction ran:** an invocation on the target does not prove advice succeeded. Verify the advice's effect separately.
- **Ignoring self-invocation:** internal calls on the target usually do not return through the proxy, so advice may not run.
- **Unwrapping a target from a scoped proxy and holding it long-term:** the target can change across requests or scopes.
- **Spying on the wrong bean:** when multiple implementations exist, identify the exact bean via qualifier or bean name.
- **Stubbing a method not intercepted by the proxy:** check interfaces, method visibility, `final` modifiers, and proxy type.

## 13. Process for Stubbing and Verifying When a Spy Sits Behind a Proxy

When a test needs to spy on a bean with Spring AOP, follow this sequence:

1. Determine whether the injected bean is a Spring AOP proxy.
2. Identify how the bean is spied: `@MockitoSpyBean`, Spring Boot's spy annotation, or a custom Mockito configuration.
3. Unwrap the target using `AopTestUtils.getUltimateTargetObject(...)` when the target source is stable.
4. Use `Mockito.mockingDetails(target).isSpy()` to confirm the target is truly a spy.
5. Configure stubs on the target using `doReturn`, `doThrow`, `doNothing`, or `doAnswer`.
6. Invoke methods through the proxied bean so advice continues to run.
7. Verify invocations on the target spy.
8. Verify advice effects with separate assertions rather than inferring them from Mockito verification.
9. If the target spy is not found, check spy annotations, bean selection, and context configuration.
10. If the bean has a dynamic scope, resolve the target within the active scope and do not reuse an old target across invocations.

## Conclusion

When a Mockito spy sits behind a Spring AOP proxy, the two layers have distinct responsibilities. The proxy handles Spring advice; the spy at the target records invocations and applies stubs. Use `AopTestUtils.getUltimateTargetObject(...)` to unwrap the target when appropriate, configure the spy with `doReturn` or a matching do-style call, invoke behavior through the proxy, and verify on the target spy.

This separation lets tests control a method's outcome while keeping the call path through transactions, security, caching, or aspects. Inspect actual objects using Mockito and Spring utilities, especially when the project uses multiple proxy layers or dynamic bean scopes.

