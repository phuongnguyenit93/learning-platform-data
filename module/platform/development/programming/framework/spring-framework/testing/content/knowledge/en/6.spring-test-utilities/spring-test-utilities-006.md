# AopTestUtils for Unwrapping Targets When Verifying Mocks Behind Proxies

Spring AOP often wraps a bean in a proxy to apply behaviors such as transactions, security, caching, or logging. Consequently, the object injected into a test can be a proxy rather than the actual instance executing the logic. If the instance inside the proxy is a Mockito mock or spy, verifying interactions directly on the proxy variable sometimes targets the wrong object rather than the one Mockito manages.

Spring Test provides `AopTestUtils` to access the target object behind a Spring AOP proxy. In tests, this utility is helpful when you need to obtain the mock or spy sitting inside a proxy to verify calls with Mockito. Use it deliberately: the action under test should still pass through the proxy so Spring's advice runs; unwrapping the target is primarily for observation and verification.

## 1. Why can a Spring bean be a proxy?

Spring AOP applies additional behavior by placing a proxy around a bean. When another component calls the bean through the proxy, the proxy can run advice before or after forwarding the call to the target object.

For example, a transactional service:

```java
@Service
@Transactional
public class OrderService {

    public void confirm(String orderId) {
        // Update order status
    }
}
```

When transaction management is enabled, the bean retrieved from the Spring `ApplicationContext` may be a proxy. Calling `confirm()` goes through the proxy so Spring starts a transaction, invokes the target's logic, and commits or rolls back the transaction depending on the outcome.

The relationship can be pictured as follows:

```text
Test or bean calls OrderService
             |
             v
      Spring AOP proxy
             |
             | applies advice
             | (transaction, security, ...)
             v
        Target object
             |
             v
       Business logic
```

Therefore, the variable injected into a test may reference a proxy. This is normal and part of how Spring delivers AOP features.

Spring AOP can use a JDK dynamic proxy or a CGLIB proxy depending on configuration and bean type. Both serve to route calls through a proxy layer before reaching the target. Tests should not assume a bean is always a direct instance of its implementation class.

## 2. The problem when a mock or spy sits behind a proxy

Mockito provides `verify()`, `when()`, `doReturn()`, and other APIs for working with mocks or spies. These APIs require the exact object Mockito created or manages.

Suppose a bean is configured as a spy, and Spring AOP creates a proxy around it to apply advice. The test receives the bean from the context and calls:

```java
verify(orderService).calculateTotal("ORDER-42");
```

If `orderService` is a Spring AOP proxy while the Mockito spy sits inside as the target, Mockito may throw `NotAMockException` because the proxy passed by the test is not a mock/spy managed by Mockito.

The issue lies at the object boundary:

- **Proxy:** the object Spring exposes to consumers; it coordinates calls through advice.
- **Target:** the object executing logic behind the proxy.
- **Mock/spy:** the object created or wrapped by Mockito to control and observe calls.

In some setups, the target itself may be a Mockito spy. In that case, the test needs to unwrap the target to verify interactions on the right instance.

Not every proxy contains a Mockito mock or spy. An AOP proxy may simply wrap a regular bean. Before calling `verify()`, confirm whether the test target was actually configured as a mock/spy.

## 3. What is AopTestUtils?

`AopTestUtils` is a utility in Spring Test, located in the package:

```java
org.springframework.test.util.AopTestUtils
```

It provides static methods to retrieve the target object from a Spring AOP proxy:

| Method | Behavior |
|---|---|
| `getTargetObject(candidate)` | Gets the target behind one outer proxy layer |
| `getUltimateTargetObject(candidate)` | Continues unwrapping nested Spring AOP proxies to return the ultimate accessible target |

If the passed object is not a Spring AOP proxy, the utility returns that object itself. Thus, test code can call the utility wherever target access is needed without manually checking each proxy type.

### getTargetObject()

Use `getTargetObject()` when you need the target directly behind the current proxy layer:

```java
OrderService target =
        AopTestUtils.getTargetObject(orderService);
```

This method unwraps one outer proxy layer. If the returned target is still another Spring AOP proxy, it may not yet be the final object.

### getUltimateTargetObject()

Use `getUltimateTargetObject()` when multiple nested proxy layers may exist and the test needs the ultimate target:

```java
OrderService target =
        AopTestUtils.getUltimateTargetObject(orderService);
```

This method keeps unwrapping targets across nested Spring AOP proxies. It is usually the right choice when locating a Mockito spy deep inside a proxy chain.

Both methods are testing APIs. They do not change how beans are registered in the Spring context, do not turn a target into a mock, and do not create spies on their own.

## 4. Example: unwrapping a spy inside a proxy to verify

Suppose the application has a `PaymentGateway` replaced by a Mockito spy in a test. That bean is also wrapped by Spring AOP with a proxy to apply advice.

The test injects the beans via the Spring context and calls a service that uses the gateway:

```java
@SpringBootTest
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @SpyBean
    private PaymentGateway paymentGateway;

    @Test
    void sendsPaymentThroughGateway() {
        Order order = new Order(
                "ORDER-42",
                new BigDecimal("120000")
        );

        checkoutService.checkout(order);

        PaymentGateway target =
                AopTestUtils.getUltimateTargetObject(paymentGateway);

        verify(target).charge(
                eq("ORDER-42"),
                eq(new BigDecimal("120000"))
        );
    }
}
```

This example assumes:

- `CheckoutService` uses `PaymentGateway` to submit payment requests.
- Spring Boot's `@SpyBean` wraps or replaces the gateway bean with a spy so tests can observe calls while preserving real behavior per the spy configuration.
- The injected bean may additionally be wrapped by Spring AOP.
- `AopTestUtils.getUltimateTargetObject()` retrieves the target so Mockito verifies the actual spy.

The call `checkoutService.checkout(order)` still executes through the Spring-managed bean. The test only retrieves the target after the action finishes to verify the arguments passed. This preserves advice behavior along the real call path while allowing interaction checks on the target.

In a project without Spring Boot, you can configure a spy using Mockito in test configuration or an equivalent bean-replacement mechanism. The core requirement remains that the unwrapped target must be an object managed by Mockito.

## 5. Checking whether the target is actually a mock or spy

Do not assume every target is a Mockito object. You can use `Mockito.mockingDetails()` to inspect its status before verifying:

```java
Object target =
        AopTestUtils.getUltimateTargetObject(paymentGateway);

assertTrue(
        Mockito.mockingDetails(target).isSpy(),
        "payment gateway target should be a Mockito spy"
);
```

Mockito also provides `isMock()` to determine whether an object is managed by Mockito. A spy is also a form of mock in Mockito's model, yet `isSpy()` clearly distinguishes the kind of object being observed.

If the target is not a mock or spy, `verify(target)` fails with `NotAMockException`. When that happens, inspect how the test replaces the bean, the proxy structure, and the object the test injects.

You can assign to a typed variable if you are certain the target has that implementation or interface type:

```java
PaymentGateway target =
        AopTestUtils.getUltimateTargetObject(paymentGateway);
```

If the target type cannot be known at compile time, receive the result as `Object`, verify its type, and cast after confirming compatibility. Do not cast blindly just because the injected proxy variable has an interface type.

## 6. Nested proxies and choosing the method

A bean may pass through several proxy layers during configuration. For instance, an integration layer may wrap a bean to apply one set of behaviors while another proxy is created by AOP.

Illustration:

```text
Test
 |
 v
Proxy A
 |
 v
Proxy B
 |
 v
Mockito spy
 |
 v
Real logic
```

If you use `getTargetObject()`, the result may be Proxy B. The test still does not have the Mockito spy to verify. Using `getUltimateTargetObject()` keeps unwrapping nested Spring AOP proxy layers.

Selection rule:

- Known to have only one Spring AOP proxy layer and need the immediate target: `getTargetObject()`.
- May have nested proxies or you do not control the proxy stack: `getUltimateTargetObject()`.
- Object is not a Spring AOP proxy: no unwrapping needed; the utility returns the candidate.

Note that this utility works with Spring AOP proxies and the target source those proxies expose. It is not a general-purpose tool for stripping every wrapper, decorator, dynamic proxy created by other libraries, or arbitrary outer wrapper. If a target source exposes targets in a special way or the target cannot be accessed normally, unwrapping may not yield the expected result and can throw an error.

## 7. Why calls must still go through the proxy

The purpose of AopTestUtils is to help tests observe the target. It does not mean tests should call the target directly to execute the behavior under test.

For example, with a `@Transactional` service:

Suppose in this test the bean's target has also been configured as a Mockito spy, such as via `@SpyBean` or an equivalent test configuration.

```java
OrderService target =
        AopTestUtils.getUltimateTargetObject(orderService);

// Do not use target to replace calling through the Spring bean:
target.confirm("ORDER-42");
```

Calling the target directly bypasses the proxy. Consequently, transaction advice or other advice attached to the proxy may not execute. That changes the conditions under which the application actually runs.

When the target is a spy and interactions need to be verified, structure the test like this:

```java
// Act: call the Spring-managed bean
orderService.confirm("ORDER-42");

// Assert: unwrap target to verify interactions if needed
OrderService target =
        AopTestUtils.getUltimateTargetObject(orderService);

verify(target).confirm("ORDER-42");
```

In this example, the business call goes through the proxy. Unwrapping the target happens only in the verification step. If the test needs to confirm that transaction, security, or caching advice works, observe outcomes at the appropriate boundary or check state produced by the advice; merely verifying that the target method was called does not prove the advice worked properly.

## 8. AopTestUtils does not replace ArgumentCaptor or matchers

AopTestUtils answers **which object to pass to Mockito** when the target sits behind a proxy. It does not decide how arguments are matched.

After retrieving the target, tests still use standard Mockito tools:

- Concrete values or `eq(expected)` when exact data must be verified.
- `argThat(...)` when checking a predicate on an argument.
- `ArgumentCaptor` when capturing the actual argument to inspect multiple fields.
- `same(expected)` when object identity is what matters.

Example using a captor on the target:

```java
PaymentGateway target =
        AopTestUtils.getUltimateTargetObject(paymentGateway);

checkoutService.checkout(order);

ArgumentCaptor<PaymentRequest> captor =
        ArgumentCaptor.forClass(PaymentRequest.class);

verify(target).charge(captor.capture());

PaymentRequest actual = captor.getValue();
assertEquals("ORDER-42", actual.orderId());
assertEquals(new BigDecimal("120000"), actual.amount());
```

Here AopTestUtils retrieves the right spy; ArgumentCaptor captures the submitted request; assertions verify the request payload. Each tool solves a distinct part of the test.

## 9. When should you use AopTestUtils?

AopTestUtils is useful in specific scenarios:

- A bean in the Spring context is an AOP proxy while the mock or spy to verify sits at the target.
- A bean has multiple nested Spring AOP proxy layers.
- The test needs to verify whether a target is actually a Mockito mock/spy.
- You need target access to inspect state or calls that the proxy does not expose directly through Mockito APIs.

Do not use it by default for every bean in tests. If a bean is not a proxy, or Mockito can verify the injected object directly, calling AopTestUtils adds little value.

Nor should you use target access to check internal details when the bean's public behavior already proves the requirement. The more a test depends on proxy and target structure, the more fragile it becomes when AOP configuration changes even though application behavior stays the same.

## 10. Important limitations and caveats

### Only unwraps Spring AOP proxies

AopTestUtils is designed for Spring AOP proxies. If an object is a wrapper from another library, a Java dynamic proxy not created by Spring AOP, a custom decorator, or another container proxy, the utility does not guarantee finding the inner object.

### TargetSource can affect accessibility

Spring AOP uses `TargetSource` to supply targets. With typical target sources, tests can unwrap the target for verification. With special target source configurations, targets may be created or selected per access. In those cases, do not assume unwrapping always returns a stable instance or the same instance as a previous call.

If a target source cannot supply a target in the way the utility expects, unwrapping may fail. Read the exception and inspect the proxy configuration instead of continuing to cast or verify an uncertain object.

### Does not alter advice ordering

AopTestUtils does not alter advice ordering, disable transactions, or modify the proxy. It only provides access to the target for testing purposes. Invoking methods directly on the target can still bypass advice as explained earlier.

### Be careful with mutable targets

If you unwrap a target and mutate its state directly in a test, the test may bypass rules the application normally enforces through the proxy. Use the target primarily for observation or verification. When setting up data, prefer public APIs, fixtures, or test mechanisms suited to the test scope.

### Do not include in production code

AopTestUtils belongs to Spring Test and is designed for test code. Do not use it in production services or business logic to reach implementations inside proxies. If the application needs a specific object or behavior, design suitable dependencies and APIs instead of relying on proxy internals.

## 11. Troubleshooting verification failures behind proxies

| Symptom | Possible cause | Resolution |
|---|---|---|
| `NotAMockException` when calling `verify(bean)` | Bean variable is a Spring AOP proxy, Mockito spy is at target | Unwrap target with `getUltimateTargetObject()`, then check `mockingDetails()` |
| Target after `getTargetObject()` is still not a mock | Multiple proxy layers exist | Try `getUltimateTargetObject()` |
| Casting target fails | Target does not have the type the test assumed | Check the actual runtime type and bean configuration |
| No interactions verified | Test called wrong bean, call bypassed spy, or behavior did not run | Trace the dependency path and confirm the spy is registered in the context |
| Error during unwrap | Target source or proxy does not expose target in a supported way | Inspect proxy type, target source, and root cause of the exception |
| Advice does not run in test | Test invoked target directly instead of proxy | Trigger the action through the bean injected from the Spring context |

When encountering `NotAMockException`, do not immediately conclude that Mockito does not support Spring AOP. First determine which object is the proxy and which is the mock/spy. Then check whether the target returned by AopTestUtils is actually managed by Mockito.

## 12. Workflow for using it in a test

You can structure a test in this sequence:

1. **Prepare the Spring context:** declare the AOP configuration and beans under test.
2. **Prepare the mock or spy:** use the appropriate test mechanism to replace or wrap the dependency to observe.
3. **Inject beans via Spring:** hold the references the application actually uses.
4. **Execute the action through the proxy bean:** call the service or controller along the normal path.
5. **Unwrap the target when needed:** use `getTargetObject()` or `getUltimateTargetObject()` depending on proxy depth.
6. **Confirm the target is a mock/spy:** use `Mockito.mockingDetails()` if the structure is uncertain.
7. **Verify or capture:** check interactions and input data according to the contract being protected.

This sequence preserves both goals: the application runs through the Spring-managed bean so proxies function, and Mockito verifies the exact mock/spy at the target when proxy wrapping makes the outer reference non-mock.

AopTestUtils is a small but helpful tool when testing Spring beans wrapped by AOP proxies. Understanding proxies, targets, and Mockito objects avoids verifying the wrong instance while keeping the real execution path through Spring intact. Only unwrap the target when needed for verification or observation; the business action under test should still go through the Spring-provided bean.

