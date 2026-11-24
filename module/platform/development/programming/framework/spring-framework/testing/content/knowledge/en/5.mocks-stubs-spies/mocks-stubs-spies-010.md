# Avoiding Brittle Tests That Verify Every Internal Call

Mocks, stubs, and spies help control a unit's collaborators during testing. However, being able to verify a call does not mean you should verify it. If a test checks every internal method, every helper call, and the entire execution sequence, the test becomes tightly coupled to how the code happens to be written today.

When a team renames a method, merges two calculation steps, extracts a helper into a separate bean, or changes how collaborators coordinate while external behavior stays the same, such tests can fail even though the product still works properly. This is the **brittle test** phenomenon caused by asserting too many implementation details.

The goal of a unit test is to protect behavior and meaningful contracts. Verify outcomes observable to callers, produced state, and interactions with real impact at the unit's boundary. Only verify internal calls when the interaction itself is part of the requirement to protect.

## 1. Distinguishing behavior from implementation

Suppose a service creates orders. Callers care about things like:

- Valid orders are created with the accurate total amount.
- Orders are saved with the right status.
- Payment is requested for the right amount and order ID.
- When payment is declined, the order is not marked paid.

Callers generally do not care how many helpers the service called, which method computed the subtotal, or whether a mapper ran before or after a utility function if those differences do not change the contract.

For example, the service might be implemented like this:

~~~java
public OrderResult createOrder(CreateOrderCommand command) {
    var cart = cartLoader.load(command.cartId());
    var subtotal = subtotalCalculator.calculate(cart);
    var discount = discountCalculator.calculate(cart, subtotal);
    var total = subtotal.subtract(discount);
    var order = orderMapper.toOrder(command, total);

    orderRepository.save(order);
    eventPublisher.publish(new OrderCreatedEvent(order.getId()));

    return OrderResult.from(order);
}
~~~

Another version could consolidate pricing into one object:

~~~java
public OrderResult createOrder(CreateOrderCommand command) {
    var cart = cartLoader.load(command.cartId());
    var quote = pricingService.quote(cart);
    var order = orderFactory.create(command, quote);

    orderRepository.save(order);
    eventPublisher.publish(new OrderCreatedEvent(order.getId()));

    return OrderResult.from(order);
}
~~~

If both implementations create the same order, save the same state, and publish the same event per contract, business tests should not fail just because subtotalCalculator and discountCalculator were replaced by pricingService.

The difference can be illustrated as follows:

~~~text
Behavior testing:
Input -> call public function -> observe output/state/effects

Implementation-detail testing:
Input -> verify helper A -> verify helper B -> verify helper C
      -> verify exact order of every call -> check output
~~~

The second style is occasionally necessary, but applying it to every call turns the test into a mirror of the code's structure. Whenever code structure changes, the test has to change even though behavior did not.

## 2. Mocks, stubs, and spies have different roles

These terms are often used together but describe different purposes.

### Stub: providing predefined answers

A stub lets a test control a dependency's response. It returns data or raises scripted errors so the test can focus on the behavior of the object under test.

Example with Mockito:

~~~java
when(inventoryClient.availableQuantity("SKU-1"))
        .thenReturn(10);
~~~

The test states that when the service asks for the stock quantity of SKU-1, the dependency returns 10. Configuring the response does not imply you must verify that call afterward.

Stubs are useful when:

- Simulating data from a repository or API.
- Testing success and failure branches.
- Producing repeatable timeouts, exceptions, or empty results.
- Removing dependencies on databases, networks, or external systems.

### Mock: providing answers and recording interactions

A mock is often configured to return values while also recording which methods were called, arguments, call counts, and interaction order. Tests can use verify to confirm an interaction occurred.

~~~java
when(paymentGateway.charge(any()))
        .thenReturn(PaymentResult.approved("payment-42"));

var result = orderService.createOrder(command);

verify(paymentGateway).charge(any());
~~~

Mocks are valuable when the interaction itself needs protection, such as ensuring a payment request is sent to the payment gateway. But if a test verifies every mock call just because Mockito allows it, the test becomes tied to implementation structure.

### Spy: wrapping a real object and tracking partial interactions

A spy normally wraps a real object. Unstubbed methods still run real logic, while the test can track or override responses of specific methods.

~~~java
var formatter = spy(new InvoiceFormatter());

doReturn("TEST-INVOICE")
        .when(formatter)
        .generateReference(any());
~~~

Spies can help when you need to preserve most real behavior while isolating one hard-to-control piece. However, spies easily create tests coupled to how an object calls its own methods. If a refactoring alters internal calls, spy tests can fail even when public results remain right.

### Fakes are also an option

A fake is a simple yet working implementation used in tests instead of the real system. For instance, InMemoryOrderRepository can store objects in a Map to test services without a database.

Fakes can stay closer to the contract than overly detailed mock configurations. They are especially helpful when many tests share the same type of dependency and want to reduce expectations on individual calls.

| Test double | Primary role | Example |
|---|---|---|
| Stub | Provides predefined responses | Inventory API returns 10 |
| Mock | Records and verifies interactions | Payment gateway receives charge command |
| Spy | Tracks a real object, can override part of behavior | Spy formatter and stub reference-generation method |
| Fake | Simple working implementation | In-memory repository |

In Mockito, a single mock object can be both stubbed and verified. Therefore, stub and mock can also denote roles of a test double in a specific test rather than completely distinct object classes.

## 3. Why does verifying every internal call make tests brittle?

### 3.1. Tests become coupled to current structure

Suppose a test verifies:

~~~java
verify(cartLoader).load("cart-1");
verify(subtotalCalculator).calculate(cart);
verify(discountCalculator).calculate(cart, subtotal);
verify(orderMapper).toOrder(command, total);
verify(orderRepository).save(any());
verify(eventPublisher).publish(any());
~~~

The test protects six calls. Yet business requirements may only require protecting three things: the order has the right total, is saved, and publishes an event upon successful creation.

If the team replaces the two calculators with PricingService, the test turns red because two interactions vanished and a new one appeared. The business result is still right, yet the test must be updated to match the new structure.

A valuable test should permit implementation changes as long as the protected contract holds.

### 3.2. Tests mirror code instead of checking outcomes

If production code runs:

~~~java
var subtotal = subtotalCalculator.calculate(cart);
var discount = discountCalculator.calculate(cart, subtotal);
var total = subtotal.subtract(discount);
~~~

and the test merely verifies those three calls in sequence, the test nearly restates how the code runs. It does not necessarily prove the final total was used properly when saving the order.

All three calls could happen while the service passes the wrong total to the repository. A test verifying only calls would still pass if it fails to check meaningful arguments or final outcomes.

Prefer asserting on outcomes or saved data. When an interaction is an important side effect, verify the arguments of that side effect.

### 3.3. Even safe refactorings break tests

The following changes preserve behavior yet break tests that assert internal details:

- Merging two helper methods into one method.
- Extracting logic into a new collaborator.
- Replacing a loop with the Stream API.
- Precomputing a value instead of computing it right before use.
- Reordering independent operations.
- Swapping one implementation for an equivalent implementation.
- Moving processing from a service into a domain object.

If tests fail after a behavior-preserving refactoring, the team wastes time distinguishing product bugs from broken test expectations. Tests overly sensitive to implementation erode confidence during refactoring.

### 3.4. Tests can lock code into poor designs

When every internal call is verified, restructuring becomes expensive. Developers may hesitate to split classes, rename methods, or consolidate responsibilities because dozens of tests would need fixing.

Tests should protect stable requirements. They should not turn every code-organization decision into an immutable contract.

## 4. Example: from a test verifying every helper to a test verifying behavior

Suppose OrderService receives an order creation request, calculates pricing, and calls the payment gateway. After successful payment, the service saves the order and returns the result.

~~~java
public class OrderService {

    private final PricingService pricingService;
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            PricingService pricingService,
            PaymentGateway paymentGateway,
            OrderRepository orderRepository
    ) {
        this.pricingService = pricingService;
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public OrderResult createOrder(CreateOrderCommand command) {
        var quote = pricingService.quote(command.items());

        var payment = paymentGateway.charge(
                new PaymentCommand(command.customerId(), quote.total())
        );

        if (!payment.approved()) {
            return OrderResult.paymentRejected();
        }

        var order = Order.create(command, quote, payment.reference());
        var saved = orderRepository.save(order);

        return OrderResult.created(saved.getId(), saved.total());
    }
}
~~~

Types are illustrative models; constructor and method names should be adapted to your application.

### Brittle test: verifying every call and ordering

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceBrittleTest {

    @Mock
    PricingService pricingService;

    @Mock
    PaymentGateway paymentGateway;

    @Mock
    OrderRepository orderRepository;

    @InjectMocks
    OrderService orderService;

    @Test
    void shouldCreateOrder() {
        var command = sampleCommand();
        var quote = new PriceQuote(new BigDecimal("250000"));
        var payment = PaymentResult.approved("PAY-1");

        when(pricingService.quote(command.items())).thenReturn(quote);
        when(paymentGateway.charge(any())).thenReturn(payment);
        when(orderRepository.save(any())).thenAnswer(
                invocation -> invocation.getArgument(0)
        );

        orderService.createOrder(command);

        var order = inOrder(
                pricingService,
                paymentGateway,
                orderRepository
        );

        order.verify(pricingService).quote(command.items());
        order.verify(paymentGateway).charge(any());
        order.verify(orderRepository).save(any());

        verifyNoMoreInteractions(
                pricingService,
                paymentGateway,
                orderRepository
        );
    }
}
~~~

This test is not completely useless: it verifies a concrete interaction sequence. However, it has flaws:

- Does not check that the returned OrderResult has the right order ID and total.
- Does not check that the argument sent to the payment gateway has the right amount.
- Does not check that the saved order has the right status and data.
- Enforces the order of every collaborator even though some ordering may not be a requirement.
- verifyNoMoreInteractions causes adding even a harmless internal call to break the test.

If the service later adopts an OrderFactory or moves part of the logic into a domain object, the test must be rewritten even though users receive the exact same outcome.

### More resilient test: checking outcomes and side-effect contracts

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    PricingService pricingService;

    @Mock
    PaymentGateway paymentGateway;

    @Mock
    OrderRepository orderRepository;

    @InjectMocks
    OrderService orderService;

    @Test
    void shouldCreateAndPersistOrderAfterApprovedPayment() {
        var command = sampleCommand();
        var quote = new PriceQuote(new BigDecimal("250000"));

        when(pricingService.quote(command.items())).thenReturn(quote);
        when(paymentGateway.charge(any())).thenReturn(
                PaymentResult.approved("PAY-1")
        );
        when(orderRepository.save(any())).thenAnswer(
                invocation -> invocation.getArgument(0)
        );

        var result = orderService.createOrder(command);

        assertEquals(OrderStatus.CREATED, result.status());
        assertEquals(new BigDecimal("250000"), result.total());

        var paymentCaptor = ArgumentCaptor.forClass(PaymentCommand.class);
        verify(paymentGateway).charge(paymentCaptor.capture());
        assertEquals(command.customerId(), paymentCaptor.getValue().customerId());
        assertEquals(
                new BigDecimal("250000"),
                paymentCaptor.getValue().amount()
        );

        var orderCaptor = ArgumentCaptor.forClass(Order.class);
        verify(orderRepository).save(orderCaptor.capture());
        assertEquals(OrderStatus.PAID, orderCaptor.getValue().status());
        assertEquals(
                new BigDecimal("250000"),
                orderCaptor.getValue().total()
        );
    }
}
~~~

The new test focuses on:

- The result returned by the service.
- The amount and customer sent to the payment gateway.
- The order saved with the right status and total.

The test still verifies two key interactions: charging payment and saving the order. These interactions lie at boundaries with external impact and belong to the feature's contract. The test does not force the service to invoke each internal helper in a fixed sequence.

In this example, PricingService is stubbed to provide a price quote. The test does not need to verify that PricingService was called exactly once if that is not a requirement. If avoiding repeated price lookups matters for cost or consistency, write a dedicated test for that contract with a clear rationale.

## 5. When is verifying an interaction justified?

Not every verify is bad. An interaction should be verified when it is meaningful to observable behavior or a collaborator's contract.

### 5.1. Required side effects

Some behaviors cannot be inferred solely from return values:

- Sending email or SMS.
- Calling a payment gateway.
- Publishing an event to a message broker.
- Sending a command to a shipping system.
- Writing a mandatory audit log.
- Invalidating cache after updating data.
- Calling an external API to fulfill a business action.

For example, if requirements state that an OrderCreated event must be published after creating an order successfully, the test can verify that eventPublisher receives the right event:

~~~java
verify(eventPublisher).publishEvent(
        argThat(event ->
                event instanceof OrderCreatedEvent created
                && created.orderId().equals(orderId)
        )
);
~~~

What needs protecting is that the right event is emitted at the system's public boundary. The test does not need to verify every helper called to assemble that event.

### 5.2. Invocation counts are part of the requirement

Sometimes the exact invocation count genuinely matters:

- Never charge twice for the same request.
- Never send duplicate emails during retries.
- Emit only one event when status transitions from PENDING to PAID.
- Do not call the fee-calculation service if the order is invalid.

In those cases, verifying call counts is valuable:

~~~java
verify(paymentGateway, times(1)).charge(any());
~~~

However, Mockito's default verify without a times argument also means exactly once:

~~~java
verify(paymentGateway).charge(any());
~~~

Use times(2), never(), or atLeastOnce() when a specific count needs expressing. Do not add times(1) just to make the statement longer.

### 5.3. Interaction ordering has business significance

Some orderings are real contracts:

- Check permissions before reading sensitive data.
- Reserve inventory before confirming an order.
- Confirm payment before marking an order paid.
- Record success status after an external operation completes.

If swapping order would break business rules, the test can use InOrder to verify just that portion of the sequence.

~~~java
InOrder order = inOrder(inventoryService, paymentGateway);

order.verify(inventoryService).reserve(orderId);
order.verify(paymentGateway).charge(any());
~~~

Verify ordering only between interactions with causal or business requirements. Never use InOrder to lock down every call in a method, especially independent steps that could run in another order.

### 5.4. Refraining from interactions when preconditions fail

For example, an invalid order must be rejected before sending payment:

~~~java
@Test
void shouldNotChargeWhenOrderIsInvalid() {
    when(orderValidator.isValid(any())).thenReturn(false);

    var result = orderService.createOrder(invalidCommand());

    assertEquals(OrderStatus.REJECTED, result.status());
    verifyNoInteractions(paymentGateway);
}
~~~

Here, not calling the payment gateway is a key requirement. Asserting on the outcome alongside verifyNoInteractions at the payment boundary protects it.

Limit verifyNoInteractions to the collaborator whose side effect must be prevented. You do not have to demand that every mock in the test receive zero calls.

## 6. When should you avoid verifying calls?

Avoid verify when an interaction is merely a detail helping organize code in a particular way.

For example, if a service calls a pure helper to normalize strings, business tests usually only need to check the output string. Whether the helper was called once or twice does not matter if it does not affect behavior.

Cases that typically do not need verification:

- Private methods or internal helpers of the object under test.
- Getters that only read values from an object.
- Pure transformation functions with no side effects.
- An internal collaborator existing solely to split up code.
- Order of independent steps not mandated by business rules.
- Calls whose effects are already fully verified through outputs or state.
- Interactions verified solely because a mock already happened to be created.

If a test needs to verify a private method, you can usually test that behavior through the public method calling it. If private logic is complex enough to require standalone testing, consider extracting that responsibility into a collaborator with a clear contract. Class extraction should reflect real responsibilities, not merely exist so every helper can be mocked.

## 7. Using ArgumentCaptor to verify meaningful data

Sometimes what matters is not whether a call happened, but whether the data passed across the boundary is right.

For example, a service sends a payment command. Instead of only writing:

~~~java
verify(paymentGateway).charge(any());
~~~

capture the argument to inspect important fields:

~~~java
var captor = ArgumentCaptor.forClass(PaymentCommand.class);

verify(paymentGateway).charge(captor.capture());

var paymentCommand = captor.getValue();

assertEquals("customer-1", paymentCommand.customerId());
assertEquals(new BigDecimal("250000"), paymentCommand.amount());
~~~

This verifies the data contract received by the collaborator.

There is no need to capture every argument or assert every field unrelated to the behavior being protected. Focus on values with business significance: customer ID, amount, currency, idempotency key, order ID, or status.

If the object defines equals per an appropriate contract, you can verify directly:

~~~java
verify(paymentGateway).charge(
        new PaymentCommand(
                "customer-1",
                new BigDecimal("250000")
        )
);
~~~

If the object contains timestamps, random IDs, or auto-generated fields, ArgumentCaptor combined with selective assertions is usually easier to read.

## 8. Be cautious with verifyNoMoreInteractions

Mockito provides verifyNoMoreInteractions to confirm no other unverified interactions remain on a mock.

~~~java
verify(paymentGateway).charge(any());
verifyNoMoreInteractions(paymentGateway);
~~~

This statement can be helpful when the contract requires the mock to be interacted with only in a bounded set of ways. However, placing verifyNoMoreInteractions on every mock in every test makes tests highly sensitive to implementation changes.

For instance, a metrics counter or tracing collaborator call is added to the service. If a test is checking order totals and statuses, metrics are not behavior that test needs to protect. verifyNoMoreInteractions can turn the test red because a secondary detail was added.

Some guidelines:

- Only use verifyNoMoreInteractions when the absence of extra interactions is part of the contract.
- Do not use it as a default step after every verify.
- Do not verify every mock in a test just to reach a "no unverified interactions" state.
- Prefer verifying critical side effects and output results.
- If a collaborator is expected not to be called, use verifyNoInteractions on that specific collaborator.

## 9. How can spies couple tests to internal calls?

Spies are often handy for observing a real object, yet they carry a greater risk of brittle tests than mocks at boundaries.

Example:

~~~java
class InvoiceService {

    public Invoice create(Order order) {
        var reference = generateReference(order);
        return new Invoice(reference, order.total());
    }

    String generateReference(Order order) {
        return "INV-" + order.id();
    }
}
~~~

Test using a spy:

~~~java
@Test
void shouldUseGeneratedReference() {
    var service = spy(new InvoiceService());
    doReturn("INV-TEST").when(service).generateReference(any());

    var invoice = service.create(sampleOrder());

    assertEquals("INV-TEST", invoice.reference());
    verify(service).generateReference(any());
}
~~~

This test locks down that create must call generateReference on the same object. If the code later switches to a ReferenceGenerator collaborator or computes the reference differently, the test may fail even though the invoice still has a valid reference per contract.

Points to remember when using spies:

- Spies usually run real methods if unstubbed.
- Writing when(spy.method()).thenReturn(value) can invoke the real method during stubbing.
- You can use doReturn(value).when(spy).method() to avoid invoking the real method while configuring stubs.
- Spying on objects with side effects can accidentally touch files, networks, databases, or real state.
- Verifying internal calls on a spy couples the test to how the object implements itself.

Prefer mocking collaborators at external boundaries and checking public outcomes of the object under test. Only use spies for specific reasons, such as needing to keep most real behavior while replacing an operation that is hard to reproduce.

If an internal method needs independent testing, consider whether it is truly a separate responsibility. A collaborator with a clear contract can be unit-tested on its own without tracking private calls or self-invocations.

## 10. Avoid mocking too deeply in the dependency chain

A test might mock every component:

~~~text
OrderService
    |
    +-- Mock CartLoader
    +-- Mock PricingService
    +-- Mock TaxService
    +-- Mock DiscountService
    +-- Mock OrderMapper
    +-- Mock OrderRepository
    +-- Mock EventPublisher
    +-- Mock Clock
~~~

If the test only configures and verifies every call, it turns into an imitation of the implementation. Changing any link in the chain can force updating the test.

Define the boundary of the unit under test:

- The main object is real code.
- External dependencies can be replaced with stubs or mocks to control effects.
- Pure logic and simple internal collaborators can stay real.
- Boundary side effects like payment, event publishing, or persistence must be verified per contract.
- If a complex dependency can be replaced with a simple working fake, a fake can make the test more readable.

Mocking too deeply can also strip value from the test: if every collaborator is configured to return expected results, the test can pass even if real coordination between them is broken. Important boundaries need integration tests to verify real components working together.

## 11. Examples of choosing appropriate assertions

| Scenario | Preferred assertion | Is verify needed? |
|---|---|---|
| Order total calculation function | Compare returned total amount | No need to verify per-line helpers |
| Service transitioning order status | Assert final state | Verify only meaningful side effects |
| Service calling payment gateway | Assert result and PaymentCommand | Yes, because it is a side effect |
| Service saving an order | Assert saved data or save argument | Can verify repository boundary |
| Name normalization function | Compare output string | No need to verify internal calls |
| Emitting event after order completion | Assert status and published event | Yes, because events are an integration contract |
| Not charging when order is invalid | Assert rejected status | Can verifyNoInteractions(paymentGateway) |
| Two operations required in business order | Assert outcome and required order | Use InOrder for just the two relevant interactions |
| A private helper is called | Assert public outcome | Do not mock/verify private methods |

This table is a selection guide, not a rigid rule. Evaluate what the test needs to prove and the boundaries of the feature.

## 12. Designing tests with Given - When - Then

The Given - When - Then structure keeps tests focused on preconditions, action, and outcomes:

~~~java
@Test
void shouldRejectOrderWhenPaymentIsDeclined() {
    // Given
    var command = sampleCommand();
    when(paymentGateway.charge(any()))
            .thenReturn(PaymentResult.declined());

    // When
    var result = orderService.createOrder(command);

    // Then
    assertEquals(OrderStatus.PAYMENT_REJECTED, result.status());
    verify(orderRepository, never()).save(any());
}
~~~

In this example:

- Given sets up data and dependency responses.
- When invokes one public behavior of the service.
- Then checks business outcomes and confirms no order-saving side effect occurred.

There is no need to add verify for every collaborator appearing in Given. A test should read like a short business scenario, not an inventory checklist of calls.

Name tests to describe outcomes or rules:

- shouldRejectOrderWhenPaymentIsDeclined
- shouldNotChargeWhenCartIsEmpty
- shouldPublishOrderCreatedEventAfterSuccessfulPayment
- shouldPreserveOrderTotalWhenDiscountIsZero

Avoid names that only describe implementation, such as shouldCallCalculatorThenMapperThenRepository. Good test names tell readers what behavior is protected even when internal code is refactored.

## 13. Practicing with Spring and Mockito

In Spring applications, pure unit tests can use MockitoExtension and instantiate services directly:

~~~java
@ExtendWith(MockitoExtension.class)
class NotificationServiceTest {

    @Mock
    private MailGateway mailGateway;

    @Mock
    private WelcomeMessageFactory messageFactory;

    @InjectMocks
    private NotificationService notificationService;

    @Test
    void shouldSendWelcomeMessageToCustomer() {
        var customer = new Customer("c-1", "user@example.test");
        var message = new MailMessage(
                "Welcome",
                "Hello",
                customer.email()
        );

        when(messageFactory.create(customer)).thenReturn(message);

        notificationService.sendWelcome(customer);

        verify(mailGateway).send(message);
    }
}
~~~

This test stubs messageFactory to produce a deterministic message, then verifies the email-sending side effect. If the service changes how subject or body are built while still sending the right MailMessage, the test does not need to know which helper was called.

When testing a Spring MVC slice or context, you can replace beans at outer boundaries with mocks. In Spring Boot 3.3, @MockBean is a common choice:

~~~java
@WebMvcTest(NotificationController.class)
class NotificationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private NotificationService notificationService;

    @Test
    void shouldReturnAcceptedWhenNotificationIsRequested() throws Exception {
        mockMvc.perform(post("/api/notifications/welcome/c-1"))
                .andExpect(status().isAccepted());

        verify(notificationService).sendWelcome(
                argThat(customer -> customer.id().equals("c-1"))
        );
    }
}
~~~

Here the controller test verifies the contract between the HTTP endpoint and the service. Calling the service is part of the controller's responsibility of forwarding requests to the use case. The test does not need to verify every internal call inside NotificationService; that belongs to the service's own tests.

Avoid using mock beans to replace every service, repository, and application component in one test and calling it an integration test. When all key components are mocked, the test only proves how one layer orchestrates mocks.

## 14. Decision checklist before adding verify

Before adding a verify statement, ask yourself:

1. Is this interaction a side effect or contract that callers care about?
2. If implementation changes while preserving the result, should the test stay green?
3. Can the interaction be checked more clearly via the return value or persisted state?
4. Do the arguments or call count have business meaning, or do they merely reflect current code organization?
5. Is this ordering mandated by business rules, or is it just the current order inside the method?
6. If this verify were removed, would the test still protect the critical requirement?
7. If the test fails, does the failure message point to wrong behavior or merely state that a helper was not called?

If an interaction is irrelevant to the contract and outcomes are already sufficiently checked, verify is usually unnecessary. If it is a critical side effect, verify the right interaction type, right data, and right count where needed.

## 15. Conclusion

Mocks, stubs, and spies are tools for controlling dependencies and observing interactions. They make tests reliable when applied at the right boundaries, yet they can make tests brittle when every internal call becomes an expectation.

Start from public behavior and business questions. Use stubs to provide controlled responses, mocks to verify side effects or interaction contracts, and spies cautiously when you genuinely need to keep most real behavior. Prefer assertions on outputs, state, and data crossing boundaries. Check invocation counts or ordering only when they are meaningful.

A good test lets the team evolve implementation while keeping protected requirements intact. When tests focus on behavior instead of individual internal steps, they become a safety net for refactoring rather than a barrier every time code is improved.

