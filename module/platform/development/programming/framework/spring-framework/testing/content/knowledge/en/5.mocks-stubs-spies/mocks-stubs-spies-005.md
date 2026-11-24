# Argument Matchers and Exact Input Data

When testing a service whose dependencies are replaced with mocks, the outcome of a call depends on how the mock recognizes its arguments. Mockito lets you specify exact input data using concrete values, or use *argument matchers* to describe conditions an argument must satisfy.

Choosing the right matching strategy helps tests clearly express the contract between components: which customer ID, amount, status, or object attributes the service passed to its dependency. If a matcher is too broad, the test may pass even when the service sends wrong data. If a matcher is too strict, the test may fail because of a detail unrelated to the behavior under test.

## 1. How does Mockito match arguments?

When stubbing a mock, Mockito needs to know which calls receive the configured result. When verifying, Mockito needs to know which calls count as having occurred.

If you pass a regular value, Mockito matches arguments using equality comparison, fundamentally based on the object's `equals()` method:

```java
when(customerRepository.findByEmail("lan@example.test"))
        .thenReturn(Optional.of(customer));

verify(customerRepository).findByEmail("lan@example.test");
```

In this example, the stub applies only when the service calls `findByEmail` with a string equal to `"lan@example.test"`. The verify statement likewise confirms a call with an equivalent value took place.

This works well when the input value is an important part of the behavior under test. Readers immediately see the expected email address.

For custom objects, `equals()` and `hashCode()` determine equality. If a class does not implement `equals()`, `Object`'s default comparison is typically identity comparison. Therefore, two objects with identical attributes may not be treated as equal. Understand how domain classes define equality before relying on it in stubbing or verification.

## 2. When do you need an argument matcher?

An argument matcher describes a condition for an argument to be accepted. Instead of requiring a value to equal a specific object, the test can express:

- The argument is any string.
- The argument is not `null`.
- The argument equals a specified value.
- The argument is the exact prepared instance.
- The object has an attribute or combination of attributes satisfying a condition.
- The argument satisfies a test-defined rule.

For example, a service may instantiate a new search criteria object on every repository call. The test only cares that the filter has status `ACTIVE` and the first page:

```java
when(customerRepository.search(argThat(criteria ->
        criteria != null
                && criteria.status() == CustomerStatus.ACTIVE
                && criteria.page() == 0
))).thenReturn(List.of(customer));
```

This matcher allows the `criteria` object to be a fresh instance as long as the key attributes are correct. This verifies input data by meaning rather than depending on whether the service reuses the same object instance.

Do not use matchers just to shorten a test. Choose a matcher when it expresses a meaningful condition that a concrete value cannot convey clearly or is hard to construct beforehand.

## 3. Commonly used matchers

Mockito provides matchers in `ArgumentMatchers`. Typically, tests use static imports for conciseness.

| Matcher | Condition |
|---|---|
| `any()` | Accepts any value, including `null` |
| `any(Class)` | Accepts an object of the specified type; does not match `null` |
| `anyString()`, `anyInt()`, `anyLong()` | Accepts a value of the corresponding type; typed matchers do not accept `null` |
| `eq(value)` | Argument equals the specified value by equality |
| `same(value)` | Argument must be the exact same object instance |
| `isNull()` | Argument must be `null` |
| `notNull()` | Argument must not be `null` |
| `nullable(Class)` | Accepts `null` or an object of the specified type |
| `argThat(matcher)` | Custom predicate condition |
| `aryEq(array)` | Compares array contents using an array matcher |

### any() and any(Class)

`any()` is useful when the argument value is outside the scope under test:

```java
when(notificationClient.send(any()))
        .thenReturn(SendResult.accepted());
```

This stub applies to any argument value, including `null`. Because such a matcher is broad, it cannot prove the service sent the right notification content.

When you need to restrict by type:

```java
when(notificationClient.send(any(Notification.class)))
        .thenReturn(SendResult.accepted());
```

`any(Notification.class)` only matches an object of type `Notification` and does not match `null`. If `null` is also acceptable, you can use `nullable(Notification.class)` or `isNull()` depending on the test's intent.

Typed matchers such as `anyString()`, `anyInt()`, and `anyLong()` also follow specific type rules. They do not imply accepting `null` for reference types.

### eq(value): still checking an exact value

`eq(value)` is commonly used when a call has multiple arguments and you need to combine an exact value with another matcher:

```java
verify(paymentGateway).charge(
        eq("ORDER-42"),
        any(BigDecimal.class)
);
```

Here the order ID must equal `"ORDER-42"`, while the amount only needs to be a `BigDecimal` object. If the amount is also part of what must be protected, use `eq(expectedAmount)` instead of a broad matcher.

### same(value): checking the same object instance

`same(value)` checks identity: the passed argument must be the exact instance provided.

```java
Notification notification = new Notification("ORDER-42");

notificationClient.send(notification);

verify(notificationClient).send(same(notification));
```

This matcher fits when identity matters, such as a mutable object that must be forwarded intact across a boundary. If only equal content is needed, using `eq(notification)` or an attribute-checking matcher better expresses the goal.

### isNull(), notNull(), and nullable()

These matchers express nullability rules clearly:

```java
verify(customerRepository).findByEmail(isNull());
verify(auditClient).publish(notNull());
verify(profileClient).update(nullable(Profile.class));
```

Using explicit null matchers shows readers that nullability is checked intentionally. Do not use `any()` if the test genuinely needs to prove an argument is non-null.

## 4. Important rule: if a matcher is used, every argument must use a matcher

When a call has multiple parameters, if a matcher is used for one parameter, the remaining parameters must also be expressed with matchers. Never mix matchers with raw literal values in the same stub or verify call.

Incorrect example:

```java
verify(orderRepository).find("ORDER-42", anyBoolean());
```

The call above mixes a string literal with the `anyBoolean()` matcher. Mockito reports an invalid matcher usage error.

Correct approach:

```java
verify(orderRepository).find(eq("ORDER-42"), anyBoolean());
```

Similarly when stubbing:

```java
when(reportClient.export(
        eq("CSV"),
        any(ExportOptions.class)
)).thenReturn(report);
```

If all parameters are exact values, pass them directly without matchers:

```java
when(orderRepository.find("ORDER-42", true))
        .thenReturn(Optional.of(order));
```

There is no need to wrap every literal in `eq()`. Only use matchers when you need to combine an exact condition with another condition or express a custom rule.

## 5. Using matchers with primitive types

Primitive types such as `int`, `long`, and `boolean` have corresponding matchers:

- `anyInt()`
- `anyLong()`
- `anyBoolean()`
- `anyDouble()`
- `anyFloat()`
- `anyShort()`
- `anyByte()`
- `charThat(...)`, `intThat(...)`, `longThat(...)` for custom typed conditions

Example:

```java
verify(rateLimiter).consume(eq("CUSTOMER-42"), anyInt());
```

For methods accepting primitives, use the matching primitive matcher. Avoid using `argThat(...)` returning a boxed reference value and letting Java auto-unbox it to a primitive; the matcher may return a dummy `null`, causing a `NullPointerException` before Mockito finishes recording the matcher.

If you need a custom condition for `int`, use `intThat`:

```java
verify(rateLimiter).consume(
        eq("CUSTOMER-42"),
        intThat(value -> value > 0 && value <= 10)
);
```

The condition above confirms the consumed quantity is between 1 and 10. It clearly expresses the input contract rather than accepting any integer.

## 6. Writing custom conditions with argThat

`argThat` takes an `ArgumentMatcher` or lambda expression to inspect an argument. This is suitable when confirming part of an object's structure or business rules.

For example, a service sends an order creation command to a repository. The test wants to verify the customer and line-item count without caring about creation timestamp:

```java
verify(orderRepository).save(argThat(command ->
        command != null
                && command.customerId().equals("CUSTOMER-42")
                && command.lines().size() == 2
));
```

The matcher focuses on decisive properties. If the creation time comes from a clock or current timestamp, the test does not depend on that value.

### Naming complex conditions

If a lambda is long, extract it into a descriptive variable or helper method:

```java
ArgumentMatcher<CreateOrderCommand> validCommandForCustomer =
        command -> command != null
                && command.customerId().equals("CUSTOMER-42")
                && command.lines().size() == 2;

verify(orderRepository).save(argThat(validCommandForCustomer));
```

Or:

```java
private boolean isExpectedCommand(CreateOrderCommand command) {
    return command != null
            && command.customerId().equals("CUSTOMER-42")
            && command.lines().size() == 2;
}
```

When a matcher has multiple conditions, its name should describe the meaning of the entire condition. Avoid writing a multi-line lambda with scattered unnamed values.

### Avoiding NullPointerException in matchers

The inspected argument may be `null`, so a custom matcher must handle null if null is not the expected condition:

```java
argThat(command ->
        command != null
                && "CUSTOMER-42".equals(command.customerId())
);
```

Putting a constant or literal on the left side of `equals` avoids calling a method on a null value. If null is the condition being tested, use `isNull()` to express it clearly.

## 7. Exact value, equality, and identity

The following three checks have different meanings:

| Check | What is verified | When to use |
|---|---|---|
| Literal value or `eq(value)` | Argument equals expected by equality | Value or content is the contract |
| `same(value)` | Argument is the exact expected instance | Object identity matters |
| `argThat(...)` | Argument satisfies a custom condition | Only a subset of attributes or rules matters |

Example with an address object:

```java
Address expected = new Address("12 Nguyen Hue", "HCMC");

verify(customerRepository).updateAddress(eq(expected));
```

This only works as content comparison if `Address.equals()` is implemented appropriately. If the class does not override `equals()`, two separate objects with the same data may not be considered equal.

If the goal is to verify the service passes the exact instance:

```java
verify(customerRepository).updateAddress(same(expected));
```

If the goal is only to verify the city:

```java
verify(customerRepository).updateAddress(argThat(address ->
        address != null && "HCMC".equals(address.getCity())
));
```

Choose based on the component's contract. Do not check identity when the application only requires content equivalence; nor should you check only a single property when the entire value is critical data to protect.

## 8. Using ArgumentCaptor when you need to inspect arguments

Matchers answer the question "does the argument satisfy a condition?". When you need to retain the actual argument to inspect multiple attributes after the call, use `ArgumentCaptor`.

Example:

```java
@Captor
ArgumentCaptor<CreateOrderCommand> commandCaptor;

@Test
void sendsExpectedCommandToRepository() {
    orderService.createOrder("CUSTOMER-42");

    verify(orderRepository).save(commandCaptor.capture());

    CreateOrderCommand actual = commandCaptor.getValue();

    assertEquals("CUSTOMER-42", actual.customerId());
    assertEquals(1, actual.lines().size());
}
```

The captor captures the object passed to the verified call. The test can then use standard assertions to inspect its fields.

Distinguishing the two tools:

- **Argument matcher** determines which calls match during stubbing or verification.
- **ArgumentCaptor** records the actual argument so the test can inspect it after the call occurs.

For a simple condition, `argThat` is usually concise. When inspecting multiple fields or reusing the actual object across several assertions, a captor can be clearer.

Do not use a captor just to assert a simple value when `eq(expected)` already expresses it fully. A captor adds a capture step and an intermediate variable, so use it only when retaining the argument adds value.

## 9. Checking exact input data in stub and verify

Suppose a service constructs a payment request from an order ID and total amount:

```java
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    PaymentResult checkout(Order order) {
        PaymentRequest request = new PaymentRequest(
                order.getId(),
                order.getTotal()
        );

        return paymentGateway.charge(request);
    }
}
```

The test can confirm the gateway receives the right request:

```java
@Test
void sendsExpectedPaymentRequest() {
    Order order = new Order(
            "ORDER-42",
            new BigDecimal("120000")
    );

    when(paymentGateway.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved());

    checkoutService.checkout(order);

    verify(paymentGateway).charge(argThat(request ->
            request != null
                    && "ORDER-42".equals(request.orderId())
                    && new BigDecimal("120000").equals(request.amount())
    ));
}
```

The stub uses `any(PaymentRequest.class)` because the test needs the gateway to return a controlled result so the service finishes. Verification uses a more specific matcher to confirm the outgoing request has the right order ID and amount.

Note: a broad matcher in a stub does not replace assertions on input data. If you only stub without verifying or capturing arguments, the test may miss that the service built a wrong request.

If `PaymentRequest` is a record or class whose `equals()` matches all fields to check, you can build an expected object and use `eq(expectedRequest)`. That makes the code shorter:

```java
PaymentRequest expected = new PaymentRequest(
        "ORDER-42",
        new BigDecimal("120000")
);

verify(paymentGateway).charge(eq(expected));
```

Using equality is only reliable when the semantics of `equals()` match what the test wants to verify.

## 10. Matchers in stubs can be too broad

A stub using `any()` is often convenient:

```java
when(customerRepository.findByEmail(anyString()))
        .thenReturn(Optional.of(customer));
```

But if the service must look up the exact email of the current customer, a broad matcher does not prove that. The service could mistakenly pass `"other@example.test"` and the stub would still return the same customer.

To check the input contract, stub with a concrete value:

```java
when(customerRepository.findByEmail("lan@example.test"))
        .thenReturn(Optional.of(customer));
```

Or explicitly verify the call:

```java
verify(customerRepository).findByEmail(eq("lan@example.test"));
```

How to choose depends on the goal:

- Use a broad matcher when the argument is unrelated to the behavior under test.
- Use a concrete value when the exact input is part of the contract.
- Use a custom matcher when only a set of attributes or conditions needs verification.

There is no need to verify every call on every mock. Only confirm interactions when meaningful to behavior. If a test only cares about the service's public result, assertions on the result may suffice; over-verifying internal details makes tests brittle when implementation changes while behavior does not.

## 11. Matchers must only be used in a Mockito context

Methods such as `any()`, `eq()`, and `argThat()` do not create normal expected objects. They register a matcher in Mockito's internal state and return a dummy value to satisfy Java's type signature.

Therefore, do not store a matcher's return value in a variable and use it as real data:

```java
// Do not use it this way
String email = anyString();
```

Nor should you use matchers outside stubbing or verification calls:

```java
// Not how to prepare test data
Customer customer = new Customer(anyString());
```

Create fixture data with real values:

```java
String email = "lan@example.test";
Customer customer = new Customer(email);
```

Then use matchers where Mockito needs to match:

```java
verify(customerRepository).findByEmail(eq(email));
```

Separating real data from matchers keeps code readable: fixtures build objects with concrete values; matchers describe how Mockito recognizes calls.

## 12. Special cases: collections, arrays, and varargs

Java collections typically implement `equals()` based on element content and order. Thus, an expected collection can be used for comparison:

```java
List<String> expectedRoles = List.of("ADMIN", "EDITOR");

verify(roleRepository).saveAll(eq(expectedRoles));
```

If order is not part of the contract, `List` equality may be too strict. In that case, use a custom matcher to verify membership or convert data to a structure matching the business rule.

Java arrays have different equality behavior from collections: an array's default `equals()` does not compare element contents as expected. Mockito provides the `aryEq(expectedArray)` matcher to compare contents:

```java
verify(binaryClient).send(aryEq(new byte[] { 1, 2, 3 }));
```

For methods accepting varargs, pay attention to the actual parameter type and the Mockito version in use. If you want to verify the entire varargs array, use a matcher suitable for the array type; if you want to check individual elements, you can capture or write a matcher for the collected data. Do not assume `any()` always means the same thing for a single vararg element versus the whole varargs array.

## 13. Common mistakes when using matchers

| Mistake | Why it is a problem | How to fix |
|---|---|---|
| Mixing literals with matchers in the same call | Mockito cannot consistently interpret arguments | Wrap literals with `eq()` |
| Using `any()` when an exact value is needed | Stub or verify is too broad | Use literals, `eq()`, or `argThat()` |
| Assuming `any(Class)` accepts null | Stub fails to match when argument is null | Use `isNull()` or `nullable(Class)` |
| Using reference matchers for primitives | Can hit `null` unboxing | Use `anyInt()`, `intThat()`, and corresponding primitive matchers |
| Using `same()` when only equality is needed | Test depends unnecessarily on identity | Use `eq()` or attribute-based matchers |
| Long and hard-to-read `argThat` | Conditions are buried in complex lambdas | Extract a descriptively named matcher |
| Calling methods on null arguments inside matchers | Matcher throws `NullPointerException` | Check null first or use explicit null matchers |
| Using matchers as fixture data | Return value of a matcher is only a dummy value | Create real data with constructors or factories |
| Broad stubbing followed by skipping verification | Fails to detect service passing wrong arguments | Verify important inputs via verify/captor |

Another mistake is verifying interactions in excessive detail that are not part of the component's contract. For example, if a test only needs to prove a customer gets the right result, checking every internal call couples the test to the service's current structure. Prefer verifying exact inputs at boundaries where those data values matter.

## 14. Choosing matchers by goal

You can start by determining the required precision:

1. **The input value is a contract to protect:** pass a literal or use `eq(expected)`.
2. **Only need to confirm the type and do not care about content:** use `any(Type.class)`.
3. **Only need to confirm non-null:** use `notNull()`.
4. **Null is an expected value:** use `isNull()` or `nullable(Type.class)` depending on the case.
5. **Need the exact same object instance:** use `same(expected)`.
6. **Need to check a rule on part of the data:** use `argThat()` or the matching primitive matcher.
7. **Need to inspect and assert multiple properties of the actual argument:** use `ArgumentCaptor`.

A clear test usually uses as few matchers as possible while still expressing the condition accurately. Concrete values make expectations clear; broad matchers should appear only where input details do not matter.

## 15. Connection to Mock, Stub, and Spy

Argument matchers are used in stubbing and verification operations with mocks. During stubbing, matchers determine which calls receive the configured return value or behavior. During verification, matchers determine which calls qualify as having occurred.

With spies, Mockito wraps a real object and can observe or override part of its methods' behavior. Matchers can still be used in `verify(spy)` to inspect call arguments. However, stubbing on spies requires care because writing `when(spy.method(...))` can invoke the real method during setup. For methods with side effects, `doReturn(...).when(spy).method(...)` is usually safer.

Example verifying a spy receives the right data:

```java
List<String> values = spy(new ArrayList<>());

values.add("spring");

verify(values).add(eq("spring"));
```

The matcher confirms the argument to the `add` call equals the string `"spring"`. This is an interaction check on the spy; list data is still handled by the real object.

When working with mocks, stubs, and spies, keep the goal clear: stubs control dependency outcomes, verify confirms meaningful interactions, and matchers describe argument-matching conditions. Choosing the right level of precision helps tests catch wrong data without coupling to unnecessary implementation details.

