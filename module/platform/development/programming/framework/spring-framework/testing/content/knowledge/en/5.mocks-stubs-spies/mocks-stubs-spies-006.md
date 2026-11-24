# ArgumentCaptor for Inspecting Sent Data

When testing with Mockito, sometimes what matters is not only whether a dependency was called, but also the data that the object under test sent to that dependency. For example, a service might receive an order creation request, normalize the customer name, calculate the total, and send an event to another component. We need to confirm the event contains the right order ID, customer, and calculated amount.

Mockito's `ArgumentCaptor` captures arguments passed to a mock during interaction verification. After capturing, the test can read that value and assert on individual attributes. This technique is especially useful when an argument is a DTO, command, event, or multi-field object where comparing the whole object does not clearly express what needs checking.

## 1. What problem does ArgumentCaptor solve?

Suppose a service calls a notification gateway:

```java
notificationGateway.send("customer-42", confirmation);
```

A simple assertion can confirm the gateway was called:

```java
verify(notificationGateway).send(anyString(), any(Confirmation.class));
```

However, this assertion does not tell whether the service sent to the right recipient or with the right confirmation content. We could write a matcher to compare the entire argument, but when an object has many properties, matchers easily become long and hard to read.

With `ArgumentCaptor`, the test asks Mockito to record the argument during verification, then inspects its value:

```java
ArgumentCaptor<Confirmation> captor =
        ArgumentCaptor.forClass(Confirmation.class);

verify(notificationGateway).send(eq("customer-42"), captor.capture());

Confirmation sent = captor.getValue();
assertEquals("ORD-100", sent.orderNumber());
assertEquals(new BigDecimal("125.00"), sent.total());
```

Here `verify(...)` confirms the interaction and `capture()` marks the argument slot to capture. `getValue()` returns the captured object so the test can inspect its contents.

## 2. How ArgumentCaptor works

`ArgumentCaptor` is an object holding argument values captured by Mockito during verification. It does not invoke methods by itself, generate input data, or replace a mock or stub.

The basic flow has three steps:

1. Create a captor with the argument type to capture.
2. Execute the behavior of the object under test so the mock receives the call.
3. Call `verify(mock).method(captor.capture())`, then read values via `getValue()` or `getAllValues()`.

Minimal example:

```java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class MessageServiceTest {

    @Test
    void capturesMessagePassedToGateway() {
        MessageGateway gateway = mock(MessageGateway.class);
        MessageService service = new MessageService(gateway);

        service.notifyCustomer("Lan");

        ArgumentCaptor<String> captor =
                ArgumentCaptor.forClass(String.class);

        verify(gateway).send(captor.capture());

        assertEquals("Hello, Lan", captor.getValue());
    }
}

interface MessageGateway {
    void send(String message);
}

class MessageService {
    private final MessageGateway gateway;

    MessageService(MessageGateway gateway) {
        this.gateway = gateway;
    }

    void notifyCustomer(String name) {
        gateway.send("Hello, " + name);
    }
}
```

The captor is created after the service call in the example to make clear it does not participate in business processing. In practice, creating the captor before or after the call both work; what matters is that `capture()` is used inside the corresponding verify operation.

## 3. Inspecting a sent DTO or event

ArgumentCaptor is often most valuable when the argument is an object with multiple fields. We can verify the exact data the service sends across the boundary between two components.

Suppose a service creates an order and publishes an event:

```java
import java.math.BigDecimal;

record OrderCreatedEvent(
        String orderId,
        String customerId,
        BigDecimal total
) {
}

interface OrderEventPublisher {
    void publish(OrderCreatedEvent event);
}

class OrderApplicationService {
    private final OrderEventPublisher publisher;

    OrderApplicationService(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    void completeOrder(String orderId, String customerId, BigDecimal total) {
        OrderCreatedEvent event = new OrderCreatedEvent(
                orderId,
                customerId,
                total
        );
        publisher.publish(event);
    }
}
```

The test can capture the event and verify each field:

```java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class OrderApplicationServiceTest {

    @Test
    void publishesEventWithOrderData() {
        OrderEventPublisher publisher = mock(OrderEventPublisher.class);
        OrderApplicationService service =
                new OrderApplicationService(publisher);

        service.completeOrder(
                "ORD-100",
                "CUS-42",
                new BigDecimal("125.00")
        );

        ArgumentCaptor<OrderCreatedEvent> eventCaptor =
                ArgumentCaptor.forClass(OrderCreatedEvent.class);

        verify(publisher).publish(eventCaptor.capture());

        OrderCreatedEvent event = eventCaptor.getValue();
        assertEquals("ORD-100", event.orderId());
        assertEquals("CUS-42", event.customerId());
        assertEquals(new BigDecimal("125.00"), event.total());
    }
}
```

This test verifies the data crossing the publisher boundary. It can catch mis-mapping `customerId`, passing the wrong order ID, or miscalculating the total before publishing the event.

If the object defines `equals()` according to the value contract and the entire payload needs comparison, `verify(publisher).publish(expectedEvent)` can be used directly. A captor fits better when checking specific attributes, wanting assertions with clear messages, or analyzing multiple arguments sent across calls.

## 4. Capturing multiple arguments in the same call

A method may take multiple parameters. You can create one captor for each slot to inspect:

```java
interface EmailGateway {
    void send(String recipient, String subject, String body);
}

@Test
void capturesRecipientSubjectAndBody() {
    EmailGateway gateway = mock(EmailGateway.class);
    EmailService service = new EmailService(gateway);

    service.sendWelcome("lan@example.com", "Lan");

    ArgumentCaptor<String> recipientCaptor =
            ArgumentCaptor.forClass(String.class);
    ArgumentCaptor<String> subjectCaptor =
            ArgumentCaptor.forClass(String.class);
    ArgumentCaptor<String> bodyCaptor =
            ArgumentCaptor.forClass(String.class);

    verify(gateway).send(
            recipientCaptor.capture(),
            subjectCaptor.capture(),
            bodyCaptor.capture()
    );

    assertEquals("lan@example.com", recipientCaptor.getValue());
    assertEquals("Welcome", subjectCaptor.getValue());
    assertEquals("Hello, Lan", bodyCaptor.getValue());
}
```

The example assumes `EmailService` constructs the subject and body and then calls the gateway. The captors are placed in the matching parameter positions in the `verify` call, so each captor collects its corresponding value. If one parameter does not need inspection, a suitable matcher can be used for that slot, such as `anyString()` or `eq(...)`.

When combining matchers and captors in the same verify call, Mockito requires arguments to be expressed consistently using matchers. `capture()` itself acts as a matcher. Therefore, if using a fixed value for another parameter, use `eq("value")` instead of passing a raw literal:

```java
verify(gateway).send(
        eq("lan@example.com"),
        subjectCaptor.capture(),
        bodyCaptor.capture()
);
```

This rule avoids `InvalidUseOfMatchersException` when mixing matchers with raw values in the same call.

## 5. Capturing multiple calls with getAllValues()

If a mock is called multiple times and the test needs to verify all sent data, use `getAllValues()`.

For example, a service sends a notification to each recipient:

```java
interface NotificationGateway {
    void send(String recipient, String message);
}

class CampaignService {
    private final NotificationGateway gateway;

    CampaignService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    void sendCampaign(List<String> recipients) {
        for (String recipient : recipients) {
            gateway.send(recipient, "New announcement");
        }
    }
}
```

The test captures both calls:

```java
@Test
void sendsMessageToEveryRecipientInOrder() {
    NotificationGateway gateway = mock(NotificationGateway.class);
    CampaignService service = new CampaignService(gateway);

    service.sendCampaign(List.of("lan@example.com", "minh@example.com"));

    ArgumentCaptor<String> recipientCaptor =
            ArgumentCaptor.forClass(String.class);
    ArgumentCaptor<String> messageCaptor =
            ArgumentCaptor.forClass(String.class);

    verify(gateway, times(2)).send(
            recipientCaptor.capture(),
            messageCaptor.capture()
    );

    assertEquals(
            List.of("lan@example.com", "minh@example.com"),
            recipientCaptor.getAllValues()
    );
    assertEquals(
            List.of("New announcement", "New announcement"),
            messageCaptor.getAllValues()
    );
}
```

`getAllValues()` returns a list of captured arguments in the order of verified calls. `times(2)` makes explicit that the test expects exactly two sends. Using only default `verify(gateway)` checks for one call; extra calls would cause verification to fail.

Two commonly used methods:

| Method | Result |
|---|---|
| `getValue()` | The last captured value; useful when there is only one call or when only the last call matters |
| `getAllValues()` | List of all captured values across the verified calls |

When capturing multiple calls, `getValue()` does not represent the full history. If sending order is part of the contract, inspect the list from `getAllValues()` or use `InOrder` to verify interaction order explicitly.

## 6. Using @Captor in JUnit Jupiter

Instead of calling `ArgumentCaptor.forClass(...)` inside every test, you can declare a field with the `@Captor` annotation. Mockito initializes the captor when the test runs via `MockitoExtension` or the matching annotation initialization mechanism.

Example with JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class OrderEventTest {

    @Mock
    private OrderEventPublisher publisher;

    @Captor
    private ArgumentCaptor<OrderCreatedEvent> eventCaptor;

    @Test
    void capturesPublishedEvent() {
        publisher.publish(new OrderCreatedEvent(
                "ORD-200",
                "CUS-77",
                new BigDecimal("80.00")
        ));

        verify(publisher).publish(eventCaptor.capture());

        assertEquals("ORD-200", eventCaptor.getValue().orderId());
        assertEquals("CUS-77", eventCaptor.getValue().customerId());
    }
}
```

`@Captor` is merely metadata for Mockito to initialize the captor; the annotation itself will not initialize the field if the test does not enable annotation processing. With JUnit Jupiter, `@ExtendWith(MockitoExtension.class)` is the standard approach. If not using the extension, you can create the captor inside the method or initialize annotations with `MockitoAnnotations.openMocks(this)` and close the returned handle appropriately after the test.

Another pattern is using `@Captor` alongside `@Mock` in a test class with `MockitoExtension`. This centralizes test dependency declarations, reduces manual initialization, and improves readability when there are multiple mocks/captors.

## 7. Capturing arguments when testing Spring controllers or services

ArgumentCaptor is also useful in web-layer tests. For instance, a controller receives an HTTP request, transforms the data into a command, and calls a service. `@WebMvcTest` can mock the service and a captor helps verify the command the controller sent.

Suppose we have a command and service:

```java
record RegisterCustomerCommand(String email, String displayName) {
}

interface CustomerApplicationService {
    void register(RegisterCustomerCommand command);
}
```

Controller:

```java
@RestController
@RequestMapping("/customers")
class CustomerController {

    private final CustomerApplicationService service;

    CustomerController(CustomerApplicationService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<Void> register(@RequestBody RegisterCustomerRequest request) {
        service.register(new RegisterCustomerCommand(
                request.email().trim().toLowerCase(),
                request.displayName().trim()
        ));
        return ResponseEntity.accepted().build();
    }
}
```

A web test can send JSON, assert the response, and capture the command:

```java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private CustomerApplicationService service;

    @Test
    void sendsNormalizedCommandToService() throws Exception {
        mockMvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "  LAN@EXAMPLE.COM ",
                                  "displayName": " Lan Nguyen "
                                }
                                """))
                .andExpect(status().isAccepted());

        ArgumentCaptor<RegisterCustomerCommand> captor =
                ArgumentCaptor.forClass(RegisterCustomerCommand.class);

        verify(service).register(captor.capture());

        assertEquals("lan@example.com", captor.getValue().email());
        assertEquals("Lan Nguyen", captor.getValue().displayName());
    }
}
```

The example assumes the project has `RegisterCustomerRequest`, `@WebMvcTest`, `MockMvc`, and appropriate Spring Test configuration. `@MockBean` is how mock beans are declared in many Spring Boot versions; in newer versions, projects may use the replacement annotation provided by Spring Boot. The key point is that the captor shows how the controller mapped the request into a command before calling the service.

There is no need to use ArgumentCaptor for every request. If you only need to confirm the service received an exact simple value, `verify(service).register(eq(expectedCommand))` can be more concise. Use a captor when reading and asserting individual fields makes the test's intent clearer.

## 8. ArgumentCaptor and other matchers

Mockito provides several ways to verify arguments. Choose the tool based on what needs to be expressed in the test.

| Approach | Suitable when | Example |
|---|---|---|
| Direct value | Argument can be compared clearly with `equals()` | `verify(repo).findById("42")` |
| `eq(...)` | Need to compare a specific value alongside other matchers | `verify(gateway).send(eq("ops"), any())` |
| `any(...)` | Only need to confirm the method was called with an argument of a given type | `verify(repo).save(any(Order.class))` |
| `argThat(...)` | Need to express a match condition inline at the verify call | `verify(repo).save(argThat(o -> o.total().signum() > 0))` |
| `ArgumentCaptor` | Need to extract the argument to check multiple fields or reuse across assertions | `verify(publisher).publish(captor.capture())` |

For example, if you only need to verify that a repository saves an order with a specific ID, direct comparison may fit. If you need to verify total amount, line items, and shipping address separately, a captor lets assertions state expectations specifically.

Both `argThat` and captors can check conditions on objects. The main difference is presentation: a matcher decides immediately whether the argument matches; a captor holds the argument so the test can inspect it afterward. Avoid using a captor just because it exists when a simple matcher already expresses the requirement fully.

## 9. Do not use captors as a default stubbing mechanism

ArgumentCaptor is designed primarily for verification. You may see examples using `capture()` inside `when(...)`, but that often makes test intent hard to understand and can cause errors to surface during stubbing rather than assertions.

Avoid writing code like this just to inspect arguments when the mock is called:

```java
ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
when(gateway.lookup(captor.capture())).thenReturn(result);
```

If you need to return results based on input arguments, use `thenAnswer(...)` or the `argThat(...)` matcher in stubbing. For example:

```java
when(gateway.lookup(argThat(key -> key.startsWith("CUS-"))))
        .thenReturn(customer);
```

After executing behavior, use a captor in `verify(...)` if you need to inspect the exact sent value. That way, stubbing describes the dependency's response while verification describes the interaction to confirm.

## 10. Mutable objects and capture timing

A captor stores a reference to the object passed into the mock. It does not automatically create a deep copy of the object at call time. If the service passes a mutable object and then continues mutating that same object after the call, the value read through the captor may reflect the mutated state.

Example:

```java
List<String> recipients = new ArrayList<>();
recipients.add("lan@example.com");

gateway.send(recipients);
recipients.add("minh@example.com");
```

If the gateway receives the same `recipients` reference, the captor may see the list after the second element was added. That does not prove whether the gateway received the initial snapshot or whether the service sent a two-element list from the start.

To avoid ambiguity:

- Prefer passing immutable objects or unmodifiable collections after creation.
- If the contract requires a snapshot at send time, make a copy before handing it off and verify that copy.
- If you need to verify the exact state at the moment of interaction for a mutable object, you can use `thenAnswer(...)` to record a copy when the mock receives the call.

Example recording a snapshot inside an answer:

```java
List<List<String>> snapshots = new ArrayList<>();

doAnswer(invocation -> {
    List<String> argument = invocation.getArgument(0);
    snapshots.add(List.copyOf(argument));
    return null;
}).when(gateway).send(anyList());
```

`List.copyOf(...)` creates an unmodifiable list with the current elements. This is a shallow snapshot; if inner elements are also mutable, copy them according to the application's data structures. For simple cases, using a standard captor remains the clearest choice.

## 11. Common mistakes when using ArgumentCaptor

### 11.1. Forgetting to call the method before verifying

A captor only collects arguments from interactions that occurred. If the service has not been executed or the code branch did not invoke the mock, `verify(...)` fails because no matching invocation is found.

### 11.2. Calling getValue() when there were multiple calls

`getValue()` returns the last captured value. If you need to check all sent data, use `getAllValues()` and verify the corresponding invocation count.

### 11.3. Declaring @Captor without initializing Mockito annotations

A field annotated with `@Captor` remains uninitialized without `MockitoExtension`, `MockitoAnnotations.openMocks(...)`, or an equivalent mechanism. Accessing that field can cause a `NullPointerException`.

### 11.4. Mixing matchers and literal values

When one argument uses `capture()` or another matcher, the remaining arguments in the same call must also use matching matchers. Use `eq(...)` for fixed values to avoid `InvalidUseOfMatchersException`.

### 11.5. Capturing the wrong type or wrong parameter position

The captor must match the method's parameter type and be placed in the right position in the verify call. With overloaded methods, check the signature Mockito resolves to ensure the captor collects the right parameter.

### 11.6. Using captors to check internal details outside the contract

If a test inspects every field of an internal object that does not affect public behavior, it can become fragile during refactoring. Only capture data at meaningful boundaries: commands sent to an application service, emitted events, requests sent to a gateway, or data passed to a repository when that is behavior worth protecting.

### 11.7. Confusing a captor with verifying persisted data

Capturing an argument sent to a repository only verifies the data the service passed to the repository. It does not prove the database stored the data successfully, how triggers behaved, or that a transaction committed. To test persistence, run appropriate integration tests and read back the stored state.

## 12. Practice designing tests with ArgumentCaptor

When deciding to use a captor, clearly identify the interaction boundary and key data to verify:

1. Select the mock representing the dependency called by the object under test.
2. Execute behavior through a public method of the object under test.
3. Verify the right method and invocation count using `verify(...)`, `times(...)`, or an appropriate verification mode.
4. Place `capture()` in the argument slots to observe.
5. Read `getValue()` for a single call or `getAllValues()` for multiple calls.
6. Assert on fields belonging to the interaction contract, such as identifiers, recipients, amounts, statuses, or event payloads.
7. Check for unwanted interactions if part of the requirement, while avoiding over-verifying implementation details.

For example, when testing a service that publishes an event after creating an order, the test can verify the event has the right `orderId`, `customerId`, and `total`, while confirming the publisher was called once. If input data is invalid, it can verify the publisher was never called. These assertions protect key behavior at the boundary between the service and the event-consuming system.

ArgumentCaptor lets a test see the actual data passed through a mock call. Combined properly with `verify`, it clarifies the mapping and data-forwarding responsibilities of a service or controller, supporting inspection of multi-field DTOs/events and repeated sends. Keep captors at meaningful boundaries, verify exact call counts, and keep in mind that a captor holds a reference to the sent object rather than creating a snapshot automatically.
