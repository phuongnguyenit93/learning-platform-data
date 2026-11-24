# Assertions for Values, Collections, and Exceptions

In JUnit Jupiter, assertions are statements that let a test verify whether actual results meet expectations. A test can run to completion without any assertions, but in that case it has not proven the behavior under test. Choosing the right assertion helps the test clearly express the source code's contract, detect failures at the exact point of deviation, and provide enough information to diagnose causes when failures occur.

JUnit Jupiter provides methods in the org.junit.jupiter.api.Assertions class. Common methods include assertEquals for values, assertArrayEquals and assertIterableEquals for array or iterable data, assertAll to group multiple conditions, assertThrows to verify exceptions, and assertDoesNotThrow to verify an operation completes normally. These assertions work in pure Java unit tests as well as tests running with Spring TestContext.

## 1. Structure of a Test with Clear Assertions

A test typically has three parts:

1. **Arrange:** prepare objects, input data, and initial state.
2. **Act:** invoke the exact behavior under test.
3. **Assert:** compare actual results against expectations.

Example, an order status transition policy:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}

public class OrderStatusPolicy {
    public OrderStatus afterPayment(OrderStatus current) {
        if (current != OrderStatus.NEW) {
            throw new IllegalStateException(
                    "Only a new order can be paid");
        }
        return OrderStatus.PAID;
    }
}
~~~

The test shows the three distinct parts:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class OrderStatusPolicyTest {
    @Test
    void changesANewOrderToPaid() {
        // Arrange
        OrderStatusPolicy policy = new OrderStatusPolicy();

        // Act
        OrderStatus result = policy.afterPayment(OrderStatus.NEW);

        // Assert
        assertEquals(OrderStatus.PAID, result);
    }
}
~~~

For assertions that take expected and actual arguments, pass the expected value first and the actual value second. This convention keeps JUnit failure messages easy to read: what the test expected and what the program actually returned. An assertion should verify something meaningful about public behavior, avoiding implementation details that are not part of the class's contract.

Test names should also state the condition and outcome clearly, such as changesANewOrderToPaid or rejectsPaymentForAnAlreadyPaidOrder. When a test fails, readers can identify its intent before looking at the test body.

## 2. Verifying Single Values and Object State

### Comparing with equals

assertEquals(expected, actual) checks whether two values are equal according to the data type's equals semantics. It suits strings, integers, enums, records, value objects, and domain objects that properly implement equals.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
~~~

Static imports are normally written individually in real tests; a value-checking example can look like this:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class CustomerTest {
    @Test
    void createsCustomerWithTheRequestedIdentity() {
        Customer customer = new Customer("C-100", "Lan");

        assertNotNull(customer);
        assertEquals("C-100", customer.id());
        assertEquals("Lan", customer.name());
    }
}

record Customer(String id, String name) {
}
~~~

A record automatically generates equals and hashCode based on its components. Thus, two Customer instances with the same id and name are considered equal by value, even though they are two separate instances.

If an object type does not implement equals according to the intended content, assertEquals may not verify what you meant to verify. In that case, assert its public properties or implement equals according to domain semantics if the type is genuinely a value object.

### Distinguishing Equality from Same Instance

assertEquals checks value equality; assertSame checks whether two references point to the exact same instance. assertNotSame confirms two references do not point to the same instance.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;

class IdentityAssertionTest {
    @Test
    void distinguishesValueEqualityFromObjectIdentity() {
        Customer first = new Customer("C-100", "Lan");
        Customer second = new Customer("C-100", "Lan");

        assertEquals(first, second);
        assertNotSame(first, second);
        assertSame(first, first);
    }
}
~~~

In most business tests, value equality is what needs verification. assertSame is useful when identity is part of the contract, such as a cache that must return the exact stored instance or a factory intentionally returning a singleton. Do not use assertSame merely because two objects happen to be held in the same variable.

### Checking Null and Booleans

JUnit provides assertNull, assertNotNull, assertTrue, and assertFalse:

~~~java
assertNull(result);
assertNotNull(customer);
assertTrue(account.isActive());
assertFalse(account.isLocked());
~~~

Use the assertion that directly describes the condition. For instance, assertNotNull(customer) shows more clearly that the test expects an object to exist than assertTrue(customer != null). When verifying a returned boolean value, assertTrue or assertFalse keeps failure messages aligned with intent.

If you need to access properties of a potentially null result, assert existence before dereferencing. Otherwise, the test may abort with a NullPointerException and obscure useful assertion messages:

~~~java
Customer customer = customerService.find("C-100");

assertNotNull(customer, "Customer should be found");
assertEquals("Lan", customer.name());
~~~

### Checking the Type of a Result

assertInstanceOf verifies that a value is of the expected type and returns the checked value cast to that type. It is useful when an API returns a supertype or interface, yet the test needs to inspect a concrete implementation that is part of the contract.

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ResultTypeTest {
    @Test
    void returnsTheExpectedResultVariant() {
        Object result = "completed";

        String value = assertInstanceOf(String.class, result);

        assertEquals("completed", value);
    }
}
~~~

Do not assert a concrete implementation type if API callers are only promised an interface or supertype. In that situation, testing behavior through the shared contract keeps tests resilient when implementations change.

## 3. Comparing Numbers and Precision-Sensitive Values

### Integers and Exact Numeric Types

For integers, longs, and numeric types with stable equals semantics, assertEquals can be used directly:

~~~java
assertEquals(3, cart.itemCount());
assertEquals(125L, invoice.totalInCents());
~~~

With BigDecimal, remember that equals considers both value and scale. Therefore, new BigDecimal("10.0") does not equal new BigDecimal("10.00") via equals, even though compareTo returns 0. If the business rule only cares about numeric value, express that explicitly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class MoneyCalculationTest {
    @Test
    void comparesDecimalAmountsByNumericValue() {
        BigDecimal expected = new BigDecimal("10.00");
        BigDecimal actual = new BigDecimal("10.0");

        assertEquals(0, expected.compareTo(actual));
    }
}
~~~

In this example, assertEquals(0, compareTo(...)) is sufficient; there is no need to add assertTrue for the same condition. When writing real tests, pick one expression to avoid redundant checks. If scale is part of the persistence or formatting contract, assertEquals on BigDecimal is more appropriate.

### Floating-Point Numbers and Delta

Results of float or double calculations can exhibit binary representation rounding error. Consequently, exact equality comparison with assertEquals(expected, actual) is often unsuitable for floating-point computation results. Use the overload with a delta:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GeometryTest {
    @Test
    void calculatesTheDiagonal() {
        double diagonal = Math.sqrt(2.0);

        assertEquals(1.41421356, diagonal, 0.00000001);
    }
}
~~~

The delta is the maximum acceptable difference between expected and actual values. Choose the delta based on required business precision, unit of measurement, and data scale. Too large a delta can allow real bugs to pass; too small a delta can cause tests to fail on negligible rounding error.

Avoid copying an arbitrary delta across every calculation. For instance, a tolerance of 0.01 might make sense for a measurement near 1, yet be unsuitable for a ratio calculation or a very small quantity. For monetary values, prefer BigDecimal with explicitly defined rounding rules instead of relying on double.

## 4. Verifying Arrays and Collections

Collection-like data has several aspects: element count, values, order, membership, and key-value mappings. Pick the assertion matching the exact aspect to verify.

### Arrays with assertArrayEquals

assertArrayEquals compares array elements in order. It supports both primitive arrays and object arrays:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import org.junit.jupiter.api.Test;

class CsvParserTest {
    @Test
    void splitsColumnsInTheirOriginalOrder() {
        String[] columns = {"id", "name", "status"};

        assertArrayEquals(
                new String[] {"id", "name", "status"},
                columns);
    }

    @Test
    void calculatesMonthlyTotals() {
        int[] totals = {10, 20, 30};

        assertArrayEquals(new int[] {10, 20, 30}, totals);
    }
}
~~~

For object arrays, element comparison uses element equality semantics; for nested arrays, JUnit supports comparing multidimensional array structures. If order is not part of the contract, convert the data to an appropriate collection type and compare using that type's semantics rather than assertArrayEquals.

### Iterables with assertIterableEquals

assertIterableEquals compares two Iterable objects by iterated elements and iteration order. The two objects may have different implementation types, such as a List and another Iterable, yet still be equal if the corresponding element sequences match.

~~~java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SearchResultTest {
    @Test
    void returnsMatchingIdsInTheRequestedOrder() {
        Iterable<String> actual =
                new ArrayList<>(List.of("P-10", "P-20", "P-30"));

        assertIterableEquals(
                List.of("P-10", "P-20", "P-30"),
                actual);
    }
}
~~~

Order is part of the comparison. If actual contains the right elements in a different order, the assertion fails. This fits search results with priority ordering, lists of processing steps, or sorted data.

Be careful with single-use Iterables or ones backed by a Stream. A Stream is a single-consumption source; do not reuse it across multiple assertions as if it were a re-iterable collection. If you need to verify multiple aspects, collect the result into a List once and run assertions on that List.

### List, Set, and Map

For standard collections, assertEquals is often sufficient because List, Set, and Map define their own equals rules:

- List compares size, elements, and order.
- Set compares elements using set semantics, independent of iteration order.
- Map compares key-value mappings, independent of iteration order.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class CollectionEqualityTest {
    @Test
    void comparesListIncludingItsOrder() {
        List<String> actual = List.of("A", "B", "C");

        assertEquals(List.of("A", "B", "C"), actual);
    }

    @Test
    void comparesSetWithoutDependingOnIterationOrder() {
        Set<String> actual = Set.of("A", "B", "C");

        assertEquals(Set.of("C", "A", "B"), actual);
    }

    @Test
    void comparesMapByKeyValueMappings() {
        Map<String, Integer> actual =
                Map.of("new", 2, "paid", 5);

        assertEquals(
                Map.of("paid", 5, "new", 2),
                actual);
    }
}
~~~

Do not convert every collection into a Set merely to make tests easier. If order carries business meaning, discarding order can hide sorting bugs. Conversely, if a result is defined as an unordered set, compare using Set so the test does not depend on implementation order.

### Checking That Required Elements Are Present

Sometimes a test only needs to confirm that a collection contains a specific element:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

assertTrue(actual.contains("ADMIN"));
~~~

If you need to confirm that multiple required elements are all present, containsAll can be used:

~~~java
assertTrue(actual.containsAll(Set.of("READ", "WRITE")));
~~~

Contains checks only verify presence; they do not guarantee the collection has no extra elements. If the contract requires an exact match of elements, use assertEquals with the expected Set. If missing and unexpected elements need to be reported clearly, comparing two full sets typically gives clearer output than several separate contains assertions.

JUnit Jupiter does not define separate core assertions for every collection library or every contains/hasSize query. You can combine standard assertions with Java collection APIs. If a project already uses an assertion library such as AssertJ, you can use its API per project conventions; distinguish them from JUnit Jupiter's Assertions.

### Checking a Map by Key and Value

If a test needs to focus on a specific mapping, check the key and value according to intent:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

Map<String, Integer> quantities = Map.of("book", 2, "pen", 5);

assertTrue(quantities.containsKey("book"));
assertEquals(2, quantities.get("book"));
~~~

When a key might be absent, get returns null if there is no mapping and can also return null if the Map permits null values. If distinguishing those two cases matters, check containsKey before checking the value.

## 5. Grouping Multiple Conditions with assertAll

assertAll accepts multiple Executables and runs all assertions in the group, then reports a composite failure if one or more assertions fail. It is helpful when independent conditions describe parts of the same result.

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class CustomerProfileTest {
    @Test
    void returnsTheExpectedProfile() {
        Customer customer =
                new Customer("C-100", "Lan");

        assertAll("customer profile",
                () -> assertNotNull(customer),
                () -> assertEquals("C-100", customer.id()),
                () -> assertEquals("Lan", customer.name()));
    }
}

record Customer(String id, String name) {
}
~~~

If one assertion inside assertAll fails, the remaining independent assertions still execute. JUnit collects the failures and reports them together in a composite failure. This lets readers see multiple mismatched properties in a single test run rather than fixing one failure at a time and re-running.

Only group truly independent conditions. If a later condition depends on an earlier condition being valid, separate them to avoid cascading errors or a NullPointerException hiding the root cause:

~~~java
Customer customer = customerService.find("C-100");
assertNotNull(customer);

assertAll("customer fields",
        () -> assertEquals("C-100", customer.id()),
        () -> assertEquals("Lan", customer.name()));
~~~

Here assertNotNull stands outside because the inner assertions need to access customer. If customer is null, the test stops with a direct message. Independent properties are then grouped together.

assertAll also has overloads accepting a Stream or Collection of Executables. Use those overloads when checks are generated from iterative data, while avoiding groups so large that it becomes hard to tell which assertion corresponds to which element. Headings or per-item messages can be added to keep output readable.

## 6. Writing Helpful Failure Messages

Many assertions have an overload taking a message. This message is shown when the assertion fails and should explain the business meaning of the condition:

~~~java
assertEquals(
        OrderStatus.PAID,
        actualStatus,
        "A successful payment should mark the order as PAID");
~~~

JUnit also supports Supplier<String> so the message is built only if the assertion fails:

~~~java
assertEquals(
        expectedTotal,
        actualTotal,
        () -> "Unexpected total for order " + orderId);
~~~

A Supplier is useful when building the message is expensive or requires data formatting. You do not need it for every simple assertion; a plain string literal is easier to read when no significant work is needed to construct the message.

Avoid generic messages like "test failed" or verbatim repetition of the assertion. A good message adds context that expected and actual alone cannot show, such as an order ID, currency, or business condition being verified.

## 7. Verifying Exceptions with assertThrows

Exceptions are often part of a contract when inputs are invalid, resources do not exist, or an operation is disallowed in the current state. assertThrows verifies that a block of code throws an exception of the expected type and returns the exception instance itself for further inspection.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderStatusPolicyExceptionTest {
    @Test
    void rejectsPaymentForAnAlreadyPaidOrder() {
        OrderStatusPolicy policy = new OrderStatusPolicy();

        IllegalStateException exception = assertThrows(
                IllegalStateException.class,
                () -> policy.afterPayment(OrderStatus.PAID));

        assertEquals(
                "Only a new order can be paid",
                exception.getMessage());
    }
}
~~~

assertThrows accepts exceptions of the exact expected type or any subtype of it. For example, if the test passes RuntimeException.class, an IllegalStateException also passes the assertion because IllegalStateException extends RuntimeException. Therefore, choose the most specific exception type promised by the public contract.

Avoid catching overly broad types such as Exception or Throwable when the behavior under test is IllegalArgumentException. An unexpected programming error could accidentally make the test pass when the expected type is too broad. A specific exception type ensures the test detects when source code changes to throw a different kind of error.

### Put Only the Action Under Test Inside the Lambda

The second argument to assertThrows is an Executable, so the code that may throw must be inside the lambda:

~~~java
IllegalArgumentException exception = assertThrows(
        IllegalArgumentException.class,
        () -> pricePolicy.calculate(null));
~~~

Do not invoke the method before passing the result into assertThrows:

~~~java
// Wrong: the call may throw an exception before assertThrows executes.
// assertThrows(IllegalArgumentException.class, pricePolicy.calculate(null));
~~~

Keep the lambda short and include only the operation expected to fail. If unrelated operations are placed inside the same lambda, the test might pass because a different operation threw an exception, even though the primary behavior did not throw as expected.

For example, when verifying that an update operation rejects an invalid value, prepare the object outside the lambda and invoke only update inside the lambda. That clarifies the exact boundary where the exception occurs.

### Inspecting the Message and Cause

After assertThrows returns the exception, you can verify its message, cause, or domain properties exposed by the exception:

~~~java
import java.math.BigDecimal;

IllegalArgumentException exception = assertThrows(
        IllegalArgumentException.class,
        () -> discountPolicy.apply(new BigDecimal("-5")));

assertEquals("Discount cannot be negative", exception.getMessage());
~~~

Only assert the message when the message itself is part of the contract relied upon by callers or operators. If the message is merely an internal detail, comparing the entire string can make the test brittle when wording is improved for clarity. Where appropriate, assert the exception type, a stable error code, or structured fields instead of full prose.

If the exception wraps another cause, you can verify the cause:

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

RuntimeException exception = assertThrows(
        RuntimeException.class,
        () -> service.performOperation());

assertInstanceOf(IllegalStateException.class, exception.getCause());
~~~

Verify the cause when preserving the underlying cause is required behavior, such as an adapter translating a technical exception into an application exception while keeping the cause for diagnostics. Do not depend on deep cause chain structures if they are not part of the contract.

### Distinguishing assertThrows and assertDoesNotThrow

assertDoesNotThrow verifies that a block of code completes without throwing an exception. For value-returning expressions, it returns that value so further assertions can be made:

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;

String normalized = assertDoesNotThrow(
        () -> usernamePolicy.normalize(" Lan "));

assertEquals("lan", normalized);
~~~

If no return value is needed, it can be used with a void operation:

~~~java
assertDoesNotThrow(() -> service.refreshCache());
~~~

Normally, a test completing without throwing an exception already proves the operation succeeded. assertDoesNotThrow is helpful when a test wants to express explicitly that valid input must not throw, or when capturing a return value from a ThrowingSupplier. There is no need to wrap every method call in assertDoesNotThrow, as doing so makes tests longer without adding information.

## 8. Combining Assertions in Business Logic Tests

A fuller example demonstrates combining value, collection, and exception checks in the same policy class:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class AccessPolicy {
    public List<String> permissionsFor(String role) {
        return switch (role) {
            case "ADMIN" -> List.of("READ", "WRITE", "DELETE");
            case "EDITOR" -> List.of("READ", "WRITE");
            case "VIEWER" -> List.of("READ");
            default -> throw new IllegalArgumentException(
                    "Unknown role: " + role);
        };
    }
}

class AccessPolicyTest {
    private final AccessPolicy policy = new AccessPolicy();

    @Test
    void grantsTheExpectedPermissionsToAnEditor() {
        List<String> permissions = policy.permissionsFor("EDITOR");

        assertIterableEquals(
                List.of("READ", "WRITE"),
                permissions);
    }

    @Test
    void rejectsAnUnknownRole() {
        IllegalArgumentException exception = assertThrows(
                IllegalArgumentException.class,
                () -> policy.permissionsFor("GUEST"));

        assertEquals("Unknown role: GUEST", exception.getMessage());
    }
}
~~~

The first test verifies both the values and the order of permissions granted to a role. The second test verifies the exception type and message for an unsupported role. Each test focuses on a single behavior so when a failure occurs, the cause is easy to pinpoint.

If permission order has no meaning in the contract, return and compare a Set instead of using a List. Data types chosen in production code and assertions in tests should both express the true semantics of the data.

## 9. Common Mistakes When Writing Assertions

### Swapping expected and actual

JUnit normally accepts two values of the same type, so swapping their order does not fail compilation, yet failure messages become confusing. Keep the expected-first, actual-second convention:

~~~java
assertEquals(expectedName, actualName);
~~~

### Using assertEquals When assertSame Is Needed

Two objects can be equal by value without being the same instance. Clarify whether the contract specifies content or identity before choosing the assertion.

### Comparing doubles Without a Delta

Floating-point calculation results can differ slightly due to binary representation. Use a delta matching business precision, and prefer BigDecimal for financial decimals requiring clear rounding rules.

### Ignoring Order or Unintentionally Requiring Order

assertIterableEquals and assertArrayEquals care about order. So does List. Standard Set and Map compare with order-independent semantics. Choose structures and assertions matching the contract rather than sorting data just to make a test pass.

### Checking Only Size

assertEquals(3, actual.size()) only confirms element count. A collection with three wrong elements still passes the test. If the contract requires specific values, compare the entire expected collection or inspect key elements.

### Putting Too Many Operations Inside assertThrows

A long lambda can catch an exception from preparation steps or a secondary call rather than the target behavior. Prepare beforehand, put only the operation under test inside the lambda, and assert the exception afterward.

### Catching Exceptions in Test Code and Ignoring Them

An empty try/catch or one that merely logs can let the test continue as if no error occurred. Use assertThrows when an exception is expected. If an exception is unexpected, let it fail the test or use assertDoesNotThrow when expressing the contract explicitly.

### Repeating Assertions for the Same Condition

Checking an expression with both assertEquals and assertTrue provides no additional proof. Pick the assertion that expresses the check most clearly and save other assertions for independent conditions.

### Over-Asserting Implementation Details

Tests that only verify a private method was called or an internal field holds a particular value become tightly coupled to class structure. Prefer asserting public outcomes, domain state, or contracted interactions with collaborators.

## 10. Organizing Assertions in Spring Projects

JUnit Jupiter assertions work independently of Spring. A service can be instantiated directly in a unit test and verified with Assertions without a Spring context. When a test needs to verify bean wiring, transactions, or Spring integration, the exact same assertions apply after the context initializes.

For example, with a service injected into a test by Spring:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(GreetingServiceContextTest.TestConfiguration.class)
class GreetingServiceContextTest {
    @Autowired
    GreetingService greetingService;

    @Test
    void createsGreetingThroughTheConfiguredBean() {
        assertNotNull(greetingService);
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfiguration {
        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}

class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

In this example, Spring is responsible for creating and injecting GreetingService; JUnit Jupiter is responsible for running the test and evaluating results. The two roles complement each other. If you only need to verify the greet logic, you can instantiate GreetingService directly without a context.

For Spring MVC, repository, or transaction tests, keep assertions close to what needs verification: response status and body, persisted data, transaction state, or translated exceptions. Do not merely assert that the context loads if the test's goal is a specific business behavior.

JUnit Jupiter allows statically importing assertion methods to keep code concise and readable. Some projects also use AssertJ or Hamcrest for a more expressive API, such as collection or string checks. Those libraries can coexist with JUnit Jupiter, but follow consistent project conventions. Do not mix multiple assertion styles in the same test without a clear reason.

## 11. Choosing an Assertion by the Question to Answer

| Test Question | Suitable Assertion | What to Watch For |
|---|---|---|
| Are two values equal? | assertEquals | Relies on the data type's equals |
| Are two variables the same instance? | assertSame / assertNotSame | Use only when identity is part of the contract |
| Is the result null? | assertNull / assertNotNull | Check before accessing properties |
| Is a boolean condition true or false? | assertTrue / assertFalse | Write conditions with business meaning |
| Is the result of the expected type? | assertInstanceOf | Avoid depending on non-public implementations |
| Do two arrays have identical elements in order? | assertArrayEquals | Compares both content and positions |
| Do two Iterables have the same sequence of elements? | assertIterableEquals | Iteration order must match |
| Are multiple independent properties all valid? | assertAll | Remaining assertions in the group still run if one fails |
| Which exception must an operation throw? | assertThrows | Pick a specific type and keep the lambda short |
| Must a valid operation complete normally? | assertDoesNotThrow | Use when this is the intent to express |
| Are two floats/doubles close within tolerance? | assertEquals with delta | Choose delta based on business requirements |

When writing a test, start from the question you need to answer and pick the matching assertion. Good assertions help readers understand the method's contract, produce informative failure outputs, and stay stable when implementation structure is refactored. With JUnit Jupiter, the built-in tools are enough to verify values, data structures, and exceptions clearly; what matters is using them in line with the semantics of the data and behavior under test.
