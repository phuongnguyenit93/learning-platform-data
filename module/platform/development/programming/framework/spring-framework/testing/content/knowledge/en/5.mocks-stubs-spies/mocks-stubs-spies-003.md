# Creating Mockito Mocks and Stubbing Return Values

Mockito helps a test control the dependencies of the class under test. We can create a mock object from an interface or class, specify the result it returns when receiving a particular call, and pass that mock into the service via its constructor. As a result, unit tests can focus on service logic without calling a database, HTTP API, payment system, or external service.

Within the Mock, Stub, and Spy techniques, creating a mock and declaring return data is the step of setting up behavior for a collaborator. A mock is a fake object created by Mockito; a stub is the response behavior configured on a mock; a spy is an object wrapping a real implementation that calls real behavior by default. Understanding these three concepts clearly helps pick the right way to isolate dependencies and avoid writing tests overly coupled to implementation details.

## 1. How do mock, stub, and spy differ?

These terms often appear together but describe different aspects:

| Concept | Meaning | When to use |
|---|---|---|
| Mock | A fake object created by Mockito whose behavior can be configured and calls verified | When you need to replace a collaborator or verify a meaningful interaction |
| Stub | Behavior configured to return data, throw an exception, or produce a result | When logic needs a test-controlled dependency input |
| Spy | An object created from a real implementation; methods usually call real behavior unless stubbed | When you need to observe or selectively override part of a real object's behavior |
| Fake | A simple implementation written by the test author that can fulfill part of the real contract | When you need a working collaborator, such as an in-memory repository |

A mock can be configured with multiple stubs. Thus, mock refers to the created object, while stub refers to that object's configured behavior. A spy can be stubbed like a mock, but the important difference is that unstubbed methods of a spy can still execute real code.

For example, when testing a reservation service, we do not want the test to read inventory counts from the database. We create a mock for the inventory query port and declare that a specific SKU has eight units left. The service receives that data and decides whether it can reserve.

## 2. Preparing a dependency for mocking

You should define dependency boundaries with an interface that has a clear contract. The following example describes an inventory query port:

~~~java
import java.util.Optional;

public interface InventoryGateway {
    Optional<Integer> availableUnits(String sku);
}
~~~

The business service receives this port via its constructor:

~~~java
import java.util.Objects;

public class ReservationPolicy {
    private final InventoryGateway inventoryGateway;

    public ReservationPolicy(InventoryGateway inventoryGateway) {
        this.inventoryGateway = Objects.requireNonNull(inventoryGateway);
    }

    public boolean canReserve(String sku, int requestedQuantity) {
        if (requestedQuantity <= 0) {
            throw new IllegalArgumentException(
                    "Requested quantity must be positive");
        }

        return inventoryGateway.availableUnits(sku)
                .map(available -> available >= requestedQuantity)
                .orElse(false);
    }
}
~~~

In the real application, a bean may implement InventoryGateway using JDBC, JPA, or HTTP. In unit tests, Mockito provides a fake implementation. ReservationPolicy does not need to know where the data comes from; it only works against the availableUnits contract.

This is an important benefit of Dependency Injection: a test can instantiate the service directly and pass in the exact dependency to control. There is no need to start a Spring ApplicationContext just to test the reservation condition.

## 3. Creating a mock with Mockito.mock()

The most direct way is calling Mockito.mock() with the type to mock:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.Optional;

class ManualMockExample {
    void createMock() {
        InventoryGateway inventoryGateway =
                mock(InventoryGateway.class);

        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(8));

        ReservationPolicy policy =
                new ReservationPolicy(inventoryGateway);

        boolean canReserve = policy.canReserve("SKU-01", 5);
    }
}
~~~

Calling mock(InventoryGateway.class) asks Mockito to create an object of type InventoryGateway. When availableUnits is invoked, Mockito intercepts the call and uses the configured behavior. Calling when(...).thenReturn(...) sets the result for the call with argument SKU-01.

The steps can be read in order:

1. Create a mock from the dependency type.
2. Declare the desired result for a specific call.
3. Pass the mock into the constructor of the object under test.
4. Invoke the public behavior of the object under test.
5. Verify the outcome or required interaction.

Mockito.mock() is suitable when a mock is only needed at one spot in a test. If a test class has multiple test methods sharing a mock, the @Mock annotation usually keeps declarations cleaner and easier to read.

## 4. Creating a mock with the @Mock annotation

Mockito provides the @Mock annotation to declare mock fields. With JUnit Jupiter, the common approach is enabling MockitoExtension:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ReservationPolicyTest {
    @Mock
    private InventoryGateway inventoryGateway;

    private ReservationPolicy policy;

    @BeforeEach
    void setUp() {
        policy = new ReservationPolicy(inventoryGateway);
    }

    @Test
    void allowsReservationWhenEnoughUnitsAreAvailable() {
        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(8));

        assertTrue(policy.canReserve("SKU-01", 5));
    }

    @Test
    void rejectsReservationWhenAvailableUnitsAreInsufficient() {
        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(3));

        assertFalse(policy.canReserve("SKU-01", 5));
    }

    @Test
    void rejectsReservationWhenInventoryIsUnknown() {
        when(inventoryGateway.availableUnits("SKU-01"))
                .thenReturn(Optional.empty());

        assertFalse(policy.canReserve("SKU-01", 5));
    }
}
~~~

MockitoExtension initializes fields with Mockito annotations before each test and manages their lifecycle. Therefore, there is no need to manually call MockitoAnnotations.openMocks(this) in this example.

Each test configures data suited to its scenario. The sufficient-stock test uses Optional.of(8), the insufficient-stock test uses Optional.of(3), and the not-found test uses Optional.empty(). The same service is tested across multiple dependency states without changing the real implementation.

If you do not use MockitoExtension, the @Mock annotation will not initialize automatically just because JUnit sees it. You can use MockitoAnnotations.openMocks(this) in setup, though you must manage closing the returned resource. With JUnit Jupiter, MockitoExtension is usually simpler and more consistent.

### @Mock is not a Spring bean

@Mock creates a Mockito object within the test scope. This annotation by itself does not register the object in the Spring ApplicationContext and does not replace a bean managed by Spring.

Therefore, unit tests typically instantiate services directly via constructors and pass mocks in. If an integration test needs to replace a bean in the Spring context, use the appropriate mock bean mechanism of the Spring Boot testing setup in use. These two needs differ: one creates an object to test isolated logic, while the other replaces a component in the application's bean graph.

## 5. Declaring return data with when().thenReturn()

Mockito's most common stubbing pattern is:

~~~java
when(mock.someMethod(arguments))
        .thenReturn(value);
~~~

The when(...) part specifies the call to configure. The thenReturn(...) part supplies the result the mock will return when receiving a matching call.

For example:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8));
~~~

When ReservationPolicy calls availableUnits("SKU-01"), the mock returns an Optional containing 8. If the test calls it with a different SKU that has no matching configuration, Mockito uses the default value for the return type.

A call can be configured with multiple distinct results. This is useful when testing behavior that depends on consecutive reads:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(
                Optional.of(8),
                Optional.of(5),
                Optional.empty());
~~~

Subsequent calls receive the first, second, and third results in sequence. Once all declared results are exhausted, Mockito continues returning the last result in the chain. You can chain multiple thenReturn() calls if you want to make each step explicit:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8))
        .thenReturn(Optional.of(5))
        .thenReturn(Optional.empty());
~~~

Do not use result chaining just to make tests more complex. Use it when the invocation count and changing results over time are part of the scenario under test, such as a first read seeing stock available while a later read does not.

## 6. Declaring results for multiple arguments

Mockito can stub a call based on exact argument values:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8));

when(inventoryGateway.availableUnits("SKU-02"))
        .thenReturn(Optional.of(2));
~~~

Two calls with different arguments receive two different results. This is usually the clearest approach when a test has a small set of known inputs.

When you do not want to depend on a specific value, you can use an argument matcher:

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

when(inventoryGateway.availableUnits(anyString()))
        .thenReturn(Optional.of(4));
~~~

anyString() matches non-null strings. With any() or type-based matchers, pay attention to the rule for combining arguments:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

interface MessageGateway {
    boolean publish(String channel, Message message);
}

record Message(String body) {
}

class MessageGatewayStubbingExample {
    void configure() {
        MessageGateway messageGateway = mock(MessageGateway.class);

        when(messageGateway.publish(
                anyString(),
                any(Message.class)))
                .thenReturn(true);
    }
}
~~~

If a matcher is used for one argument of a call, all remaining arguments in that same call must also be expressed using matchers. Do not mix a raw value with a matcher:

Suppose the variable messageGateway has already been created inside configure() as in the example above. The following call is invalid because only the second argument uses a matcher:

~~~java
// Incorrect: one argument is a raw value, the other argument is a matcher.
when(messageGateway.publish(
        "orders",
        any(Message.class)))
        .thenReturn(true);
~~~

If you need to fix one argument and use a matcher for another, use eq():

Inside the same configure() method, you can write a valid call as follows:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

when(messageGateway.publish(
        eq("orders"),
        any(Message.class)))
        .thenReturn(true);
~~~

Matchers are only meaningful inside stubbing or verification. Do not call any() or eq() as regular data in business code. If you need to match a null value, use isNull() instead of assuming anyString() or any(Class) will match null.

## 7. Declaring exceptions with thenThrow()

Not every dependency returns successful data. Tests often need to simulate timeouts, connection errors, or business errors to verify that the service handles them properly.

For methods with a return value, you can use thenThrow():

~~~java
class InventoryUnavailableException extends RuntimeException {
    InventoryUnavailableException(String message) {
        super(message);
    }
}
~~~

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenThrow(new InventoryUnavailableException(
                "Inventory service is unavailable"));
~~~

The test can confirm that the error is propagated or converted by the service into an appropriate business result:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;

class ReservationPolicyFailureTest {
    @Test
    void propagatesInventoryFailure() {
        InventoryGateway gateway = mock(InventoryGateway.class);
        ReservationPolicy policy = new ReservationPolicy(gateway);

        when(gateway.availableUnits("SKU-01"))
                .thenThrow(new InventoryUnavailableException(
                        "Inventory service is unavailable"));

        assertThrows(
                InventoryUnavailableException.class,
                () -> policy.canReserve("SKU-01", 1));
    }
}
~~~

If using a checked exception, the stubbed method must declare or allow that exception according to Java rules. For runtime exceptions, there is no need to declare throws in the method signature.

When you want one call to return normally and the next call to throw an error, you can combine results in a chain:

~~~java
when(inventoryGateway.availableUnits("SKU-01"))
        .thenReturn(Optional.of(8))
        .thenThrow(new InventoryUnavailableException(
                "Inventory service is unavailable"));
~~~

This is useful when simulating an error arising after a successful read, though it should only be used if that call sequence reflects a real scenario the service must handle.

## 8. Stubbing void methods

Void methods have no return value, so when(...).thenReturn(...) cannot be used. Mockito provides the do...when(...) API family to configure behavior:

~~~java
doThrow(new NotificationException("Gateway failed"))
        .when(notificationGateway)
        .send("orders", message);
~~~

The snippet above simulates notification delivery failure by throwing an exception when notificationGateway receives a send call with the specified arguments.

A complete test can check how the service reacts:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;

interface NotificationGateway {
    void send(String channel, Message message);
}

class NotificationException extends RuntimeException {
    NotificationException(String message) {
        super(message);
    }
}

class NotificationService {
    private final NotificationGateway gateway;

    NotificationService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    void notifyOrderCreated(Message message) {
        gateway.send("orders", message);
    }
}

class NotificationServiceTest {
    @Test
    void propagatesFailureWhenSendingNotification() {
        NotificationGateway gateway =
                mock(NotificationGateway.class);
        NotificationService service =
                new NotificationService(gateway);
        Message message = new Message("Order created");

        doThrow(new NotificationException("Gateway failed"))
                .when(gateway)
                .send("orders", message);

        assertThrows(
                NotificationException.class,
                () -> service.notifyOrderCreated(message));
    }
}
~~~

With regular mocks, void methods do nothing by default. Thus, doNothing() is usually unnecessary. This API can be useful when configuring a spy to suppress the real behavior of a void method, or when you want to express an empty behavior explicitly in a test.

## 9. Generating dynamic return data with thenAnswer()

thenReturn() is suitable when the result is known in advance. When the result must be computed from input arguments, use thenAnswer():

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import java.util.Locale;
import org.mockito.Mockito;

interface CodeNormalizer {
    String normalize(String input);
}

class CodeNormalizerStubbingExample {
    void configure() {
        CodeNormalizer codeNormalizer =
                Mockito.mock(CodeNormalizer.class);

        when(codeNormalizer.normalize(anyString()))
                .thenAnswer(invocation -> {
                    String input = invocation.getArgument(0);
                    return input.trim().toUpperCase(Locale.ROOT);
                });
    }
}
~~~

Answer receives information about the call through invocation. The test retrieves arguments using getArgument(index), computes the result, and returns it. This approach allows a single configuration to handle multiple input values.

You can use thenAnswer() when you need:

- A result that depends on the call's arguments.
- A callback to execute during the test.
- A new return object created per call.
- To simulate a rule-based response rather than a fixed value.

However, if the result is simply a known value, thenReturn() is easier to read. Avoid turning every stub into an Answer because test logic can become complex and hard to distinguish from production logic.

## 10. Using doReturn() when working with spies

With regular mocks, when(mock.method()).thenReturn(value) is the preferred declaration style. With a spy, the call inside when(...) can execute the real method during configuration.

For example, an empty list wrapped as a spy:

~~~java
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.List;

List<String> values = spy(new ArrayList<>());

when(values.get(0)).thenReturn("sample");
~~~

When evaluating values.get(0) inside when(...), ArrayList's real method is called. Because the list does not yet have an element at index 0, the setup statement can throw IndexOutOfBoundsException before thenReturn() is applied.

In that situation, use doReturn(...).when(spy).method(...):

~~~java
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.spy;

import java.util.ArrayList;
import java.util.List;

List<String> values = spy(new ArrayList<>());

doReturn("sample").when(values).get(0);
~~~

doReturn() sets up the result without invoking the real method during configuration. Mockito also provides doThrow(), doAnswer(), and doNothing() in the same do...when(...) API family.

Do not choose a spy merely because it seems more convenient than a mock. A spy retains the object's real behavior, so tests can accidentally access files, networks, databases, or external state. When you need to isolate a collaborator, a mock or fake is usually clearer. A spy is suited when the intent is to keep most real behavior and selectively override a method.

## 11. Default values when unstubbed

A mock does not execute the logic of the original class or interface on its own. If a call is not configured, Mockito uses its default answer. Depending on the return type, the default result can be null, false, numeric 0, or an empty value for certain common types.

For example, if a test forgets to configure a method returning an object, a null result can cause the service to throw NullPointerException on a later line. This error sometimes misleads readers into thinking the service logic is broken, whereas the cause is that the test failed to declare the needed dependency data.

Stub the calls that affect the behavior under test. There is no need to stub every method on a mock if the service does not call them or their default results do not affect the scenario. Configuring too much unrelated behavior makes tests verbose and brittle when code changes.

## 12. Combining stubbing with verification

Stubbing specifies how a mock responds. Verification confirms whether a call occurred. These two operations are related but serve different purposes.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class ReservationPolicyVerificationTest {
    @Test
    void queriesTheRequestedSku() {
        InventoryGateway gateway = mock(InventoryGateway.class);
        ReservationPolicy policy = new ReservationPolicy(gateway);

        when(gateway.availableUnits("SKU-01"))
                .thenReturn(Optional.of(8));

        assertTrue(policy.canReserve("SKU-01", 5));

        verify(gateway).availableUnits("SKU-01");
    }
}
~~~

The test both sets up return data and confirms that the service queried the right SKU. Verification is valuable when the call is part of the contract to check, such as sending notifications, writing audit logs, or calling a service exactly once.

Do not verify every call just because Mockito supports it. If output results already capture the behavior under test, assertions are usually more resilient. A test verifying too many internal calls can fail after a refactoring even when the application's observable behavior remains correct.

## 13. Common mistakes when creating mocks and stubbing

### Forgetting to enable MockitoExtension

Declaring @Mock without initializing annotations leaves the mock field null. With JUnit Jupiter, add @ExtendWith(MockitoExtension.class) on the test class or use the corresponding Mockito initialization.

### Using mocks instead of value objects

Do not mock String, BigDecimal, DTOs, or simple value objects. Create real data for these types. Mocks are primarily for collaborators with behavior or external boundaries that the test needs to control.

### Stubbing one argument but calling with another

When availableUnits("SKU-01") is configured, a call to availableUnits("SKU-02") does not use that configuration. Decide whether the test needs exact argument matching or a general matcher. Only use broad matchers when multiple values truly share the same meaning for the scenario under test.

### Mixing matchers with raw values

When a call uses a matcher, every argument in that call must use a matcher. Combine eq() with any() to clearly express fixed and flexible arguments.

### Using when() on a spy and triggering real code early

When stubbing a spy, the expression inside when(...) can invoke the real method and cause side effects or exceptions. Use doReturn(), doThrow(), or doAnswer() when you need to avoid real execution during configuration.

### Stubbing too much behavior

Only configure calls needed for the scenario. Unused stubs make tests harder to read and hide changes in how the service collaborates. If a configuration is shared across multiple tests but only some tests need it, place the stub inside the respective test or organize setup appropriately.

### Treating mocks as replicas of the real system

Mockito does not verify that SQL, HTTP requests, or actual Spring configuration work properly. Mocks only return what the test configured. Behaviors depending on databases, transactions, serialization, or Spring wiring still require appropriate slice tests or integration tests.

## 14. Choosing a stubbing API

| Need | Commonly used API | Example |
|---|---|---|
| Return a fixed value | when(...).thenReturn(...) | A SKU has eight units |
| Return multiple values in sequence | thenReturn(value1, value2, ...) | First read succeeds, next read is out of stock |
| Throw an exception from a value-returning method | when(...).thenThrow(...) | Repository loses connection |
| Produce a result based on arguments | thenAnswer(...) | Normalize input string |
| Throw an exception from a void method | doThrow(...).when(...) | Notification delivery fails |
| Avoid calling the real method when stubbing a spy | doReturn(...).when(...) | Stub an index not yet present in a list |
| Match arguments flexibly | any(), anyString(), eq(), isNull() | Accept any non-null SKU |

When reading a Mockito test, you can recognize the basic structure: mock creation identifies replaced collaborators; stubbing specifies data or errors the collaborators supply; execution invokes the behavior of the class under test; assertions and verification confirm the required results.

## 15. Principles of use in Spring Framework Testing

- Use Mockito.mock() when creating a mock inline at one spot; use @Mock with MockitoExtension when the mock is a test class fixture.
- Prefer constructor injection to pass mocks into services. Tests can construct objects directly without needing a Spring context for pure logic.
- Use when(...).thenReturn(...) for fixed results on value-returning methods.
- Use thenThrow() to simulate errors; use doThrow() for void methods.
- Use argument matchers when multiple input values share the same meaning; combine matchers with eq() when keeping an argument fixed.
- Use thenAnswer() for results that genuinely depend on arguments or invocation timing.
- With spies, consider doReturn() so you do not accidentally invoke the real method during stubbing.
- Do not rely on mock default values if that result affects the behavior under test.
- Only verify interactions belonging to the contract under test; prefer assertions on observable outcomes.
- Remember that mocks only simulate configured behavior. Integration tests are needed to verify database, network, and Spring container wiring.

Creating mocks and stubbing return values allows testing a component in a controlled environment. By choosing the right collaborators, configuring accurate responses, and passing mocks through constructors, tests can verify both success and failure branches reliably. Mockito offers multiple APIs for different situations; choosing the simplest API that accurately expresses the behavior under test keeps tests readable and maintainable.
