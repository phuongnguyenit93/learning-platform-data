# Verifying Invocation Counts and Important Interactions

In unit tests using Mockito, we often replace collaborators with mocks to control responses and observe how the component under test communicates with them. `when(...).thenReturn(...)` sets up mock behavior; `verify(...)` confirms that an interaction occurred with the expected arguments and invocation count. These two operations serve distinct purposes: stubbing prepares conditions for the scenario, while verification checks the interaction contract after the action executes.

Not every internal call needs verification. Verify interactions that are meaningful to the service's external behavior: saving data, sending a request to a gateway, publishing an event, sending email, or refraining from calling a collaborator when preconditions fail. If a test asserts too many implementation details such as helper call order, field read counts, or every mock call, it easily breaks when code is refactored even though behavior remains right.

## 1. Distinguishing stubbing from verification

A mock can be both configured to return results and inspected after execution. For example, a service needs to find accounts and then save a transfer:

```java
@ExtendWith(MockitoExtension.class)
class TransferServiceTest {
    @Mock
    private AccountRepository accounts;

    @Mock
    private TransferRepository transfers;

    @InjectMocks
    private TransferService service;

    @Test
    void storesTransferForExistingAccounts() {
        Account source = new Account(1L, new BigDecimal("100.00"));
        Account target = new Account(2L, new BigDecimal("20.00"));
        when(accounts.findById(1L)).thenReturn(Optional.of(source));
        when(accounts.findById(2L)).thenReturn(Optional.of(target));

        service.transfer(1L, 2L, new BigDecimal("30.00"));

        verify(transfers).save(any(Transfer.class));
    }
}
```

In this example:

- `when(...).thenReturn(...)` is stubbing: it specifies what data the mock repository returns when called by the service.
- `verify(transfers).save(...)` is verification: it confirms the service requested saving a transfer.
- `@InjectMocks` instructs Mockito to construct the service and inject matching mocks into its constructor or fields according to Mockito's mechanism.

Default verification requires the method to be called exactly once. Therefore, `verify(transfers).save(...)` is equivalent to `verify(transfers, times(1)).save(...)`.

An important point is that verifying a mock only proves the interaction was sent to the mock. It does not prove the database wrote the data, the transaction committed, or an external system processed the request. Those behaviors require integration-level tests with real components or a compatible environment.

## 2. Verifying invocation counts

Mockito provides invocation-count modes through `VerificationMode`.

| Syntax | Meaning |
|---|---|
| `verify(mock).method()` | Called exactly once |
| `verify(mock, times(3)).method()` | Called exactly three times |
| `verify(mock, never()).method()` | Never called |
| `verify(mock, times(0)).method()` | Equivalent to `never()` |
| `verify(mock, atLeast(2)).method()` | Called at least twice |
| `verify(mock, atMost(4)).method()` | Called at most four times |
| `verify(mock, atLeastOnce()).method()` | Called at least once |

Example of a service sending notifications to each recipient:

```java
@Test
void sendsOneNotificationForEachRecipient() {
    notificationService.notifyAll(List.of("a@example.test", "b@example.test"));

    verify(sender, times(2)).send(any(Notification.class));
}
```

If the contract requires sending only one confirmation email, verify exactly once:

```java
verify(emailSender, times(1)).send(any(Email.class));
```

Since once is the default, you can write the shorthand `verify(emailSender).send(any(Email.class))`. Use `times(1)` when you want to emphasize the count or place it alongside `times(0)` or `times(2)` cases.

### 2.1. Verifying non-invocation with `never()`

Failure branches often need to prove a side effect did not happen. For example, if balance is insufficient, the service must not send a payment request:

```java
@Test
void doesNotRequestPaymentWhenBalanceIsInsufficient() {
    when(accounts.findById(1L)).thenReturn(Optional.of(accountWithBalance("10.00")));

    assertThatThrownBy(() -> service.pay(1L, new BigDecimal("30.00")))
            .isInstanceOf(InsufficientFundsException.class);

    verify(paymentGateway, never()).charge(any(PaymentRequest.class));
}
```

The exception assertion verifies the failure-branch outcome; `never()` checks the forbidden side-effect boundary. This is an important interaction because if the gateway were still called, the system might trigger a wrong charge even though the service threw an exception.

`never()` should be applied to the specific method or collaborator that the contract forbids calling. Do not default to checking zero interactions across all mocks if the service is still permitted to read data, write logs, or emit metrics.

### 2.2. Are `atLeast` and `atMost` truly necessary?

These modes are helpful when the invocation count is a valid range. For example, an algorithm might attempt reading a cache once or twice depending on conditions, but must not exceed a limit. However, if business rules require sending a message exactly once, `atLeastOnce()` is too weak: code that sends duplicates will still pass the test.

Choose the mode closest to the contract:

- Use `times(n)` when an exact invocation count is a requirement.
- Use `never()` when an action is forbidden in the scenario.
- Use `atLeast` or `atMost` when the contract genuinely permits a range of counts.
- Avoid verifying call counts merely because the current implementation iterates over a data structure in a specific way.

## 3. Verifying passed arguments

Confirming that a method was called is not enough if the passed data matters. For instance, a service might call `paymentGateway.charge(...)` exactly once yet pass the wrong amount, currency, or order ID.

Mockito supports passing values directly, argument matchers, and `ArgumentCaptor`.

### 3.1. Direct argument comparison

If the data type has an appropriate `equals` and the expected value is clear, pass it directly:

```java
verify(repository).findById(42L);
verify(sender).send(new Email("a@example.test", "Order confirmed"));
```

Mockito compares arguments using the object's equality semantics, typically `equals`. For DTOs or value objects, make sure `equals` reflects the data to compare. If a class does not define value equality, use a captor or matcher to inspect key fields.

### 3.2. Using argument matchers

Mockito includes common matchers such as `any()`, `anyString()`, `eq(...)`, `isNull()`, `notNull()`, `argThat(...)`, and primitive matchers.

```java
verify(repository).findById(eq(42L));
verify(sender).send(any(Email.class));
verify(auditLog).record(argThat(event ->
        event.type() == AuditType.PAYMENT_COMPLETED));
```

Matchers are useful when only part of an argument matters. However, if you use a matcher for one argument in a multi-parameter call, the remaining arguments must also be expressed with matchers:

```java
verify(client).charge(eq("order-42"), any(BigDecimal.class), eq("VND"));
```

Do not mix matchers with literal values in the same verification call:

```java
// Incorrect: one argument uses a matcher, the rest are literals.
verify(client).charge(eq("order-42"), new BigDecimal("30.00"), "VND");

// Correct: every argument uses a matcher.
verify(client).charge(
        eq("order-42"), eq(new BigDecimal("30.00")), eq("VND"));
```

For primitive types, use the matching primitive matcher such as `anyInt()` or `eq(3)`. `any()` cannot directly substitute for a primitive in all situations because the generic matcher returns a reference value; use the right primitive matcher to avoid unboxing errors.

### 3.3. Using `ArgumentCaptor`

When you need to check multiple fields of an object passed to a mock, `ArgumentCaptor` helps collect the argument:

```java
@Captor
private ArgumentCaptor<PaymentRequest> requestCaptor;

@Test
void sendsPaymentRequestWithExpectedDetails() {
    service.pay(new Order("order-42", new BigDecimal("30.00")));

    verify(paymentGateway).charge(requestCaptor.capture());

    PaymentRequest request = requestCaptor.getValue();
    assertThat(request.orderId()).isEqualTo("order-42");
    assertThat(request.amount()).isEqualByComparingTo("30.00");
    assertThat(request.currency()).isEqualTo("VND");
}
```

`@Captor` is initialized when the test runs with `MockitoExtension`. If not using the extension, create the captor with `ArgumentCaptor.forClass(PaymentRequest.class)`.

`getValue()` returns the most recently captured argument. If the method was called multiple times and you need to inspect all of them, use `getAllValues()`:

```java
verify(sender, times(3)).send(emailCaptor.capture());

assertThat(emailCaptor.getAllValues())
        .extracting(Email::recipient)
        .containsExactly("a@example.test", "b@example.test", "c@example.test");
```

Checking order in the list above makes sense if sending order is part of the contract. If emails can be sent in any order, use an order-independent assertion such as `containsExactlyInAnyOrder`.

### 3.4. Captor or `argThat`?

Both approaches can inspect argument contents, but they fit different goals:

- Use `argThat` when the condition is short, focused, and only needs to confirm a matching call.
- Use `ArgumentCaptor` when you need to read multiple properties, run several assertions, or reuse the captured value.
- Use literal arguments when equality already expresses the full contract.

Do not capture just to check one simple value. Conversely, a long `argThat` lambda packed with conditions is hard to read and diagnose on failure; a captor is usually clearer in that case.

## 4. Verifying ordered interactions with `InOrder`

Some flows treat interaction ordering as part of the contract. For example, a service must save a transfer before publishing a completion event. Mockito provides `InOrder`:

```java
@Test
void savesTransferBeforePublishingCompletionEvent() {
    service.transfer(command);

    InOrder order = inOrder(transfers, eventPublisher);
    order.verify(transfers).save(any(Transfer.class));
    order.verify(eventPublisher).publishEvent(any(TransferCompleted.class));
}
```

`InOrder` verifies that interactions occurred in the specified relative order. Other interactions not included in the verification chain may still happen between them. If you want to verify all relevant interactions in sequence, verify each needed step.

Only use `InOrder` when ordering matters. For instance, if a service calls two independent repositories and order does not affect the outcome, verifying order couples the test to the implementation. A refactoring that swaps query order could break the test even though behavior remains correct.

With transactions and events, be especially careful. A service calling `publishEvent` after `save` does not prove the transaction committed before listeners ran. If the requirement is that events are processed only after commit, test `@TransactionalEventListener` and transaction boundaries in a Spring integration test.

## 5. Checking forbidden or unexpected interactions

Mockito provides two commonly used APIs:

```java
verifyNoInteractions(mock);
verifyNoMoreInteractions(mock1, mock2);
```

`verifyNoInteractions(mock)` confirms the mock received zero calls. `verifyNoMoreInteractions(...)` confirms no unverified interactions remain on the passed mocks.

For example, invalid input must be rejected before calling the gateway:

```java
@Test
void rejectsInvalidAmountWithoutCallingGateway() {
    assertThatThrownBy(() -> service.pay(BigDecimal.ZERO))
            .isInstanceOf(InvalidAmountException.class);

    verifyNoInteractions(paymentGateway);
}
```

This is an appropriate assertion if the contract requires the gateway to be completely untouched in this case.

### 5.1. Using `verifyNoMoreInteractions` selectively

Another example:

```java
service.findCustomer(42L);

verify(customers).findById(42L);
verifyNoMoreInteractions(customers);
```

This test states that the service was only allowed to perform the verified operation on the `customers` mock. However, if the service later adds a cache lookup, metric, or another valid operation on the same mock, the test fails even though the external contract did not change.

Therefore:

- Use `verifyNoInteractions` when zero interactions is an explicit requirement.
- Use `verifyNoMoreInteractions` when forbidding additional interactions is important to the scenario.
- Do not automatically append `verifyNoMoreInteractions` after every verify.
- Avoid using it to force tests to mirror the service's entire internal structure.

If only one specific action is forbidden, `verify(mock, never()).specificMethod(...)` usually expresses intent more accurately than forbidding all interactions.

## 6. Verifying retries and repeated calls

When a service implements retries, the call count may be part of the operational contract. For example, a client is allowed at most three attempts before reporting failure:

```java
@Test
void retriesRemoteCallAtMostThreeTimes() {
    when(remoteClient.fetch("item-42"))
            .thenThrow(new TemporaryRemoteException())
            .thenThrow(new TemporaryRemoteException())
            .thenReturn(new RemoteItem("item-42"));

    RemoteItem item = service.fetchWithRetry("item-42");

    assertThat(item.id()).isEqualTo("item-42");
    verify(remoteClient, times(3)).fetch("item-42");
}
```

This scenario verifies that the service retried twice after failures and succeeded on the third attempt. Another test should cover the case where all three attempts fail and the service throws the appropriate error.

Do not assert on retry counts if the count is unspecified and may change due to a circuit breaker, timeout, or backoff policy. In that case, verify final outcomes, state, and key side effects. If the attempt count is a requirement, verify the exact count instead of just using `atLeastOnce()`.

With asynchronous retries, calls might not have happened yet at assertion time. Wait on a completion condition with a timeout or synchronize via a future/latch. Do not use fixed sleeps to guess when the next call will run.

## 7. Verifying asynchronous interactions

A service might submit tasks to an executor, publish events with `@Async` listeners, or call a background client. In such cases, the test cannot assume all interactions finished immediately when the initial method returns.

Mockito offers `timeout` and `after` to wait during verification:

```java
verify(notificationSender, timeout(1_000))
        .send(any(Notification.class));
```

`timeout(1_000)` waits up to one second for the expected interaction to occur; once satisfied, verification can finish early. This is a way to check a simple asynchronous interaction, though you should not use arbitrarily large timeouts to mask missing synchronization in tests.

`after(...)` waits for the full specified duration before evaluating invocation counts:

```java
verify(notificationSender, after(500).never())
        .send(any(Notification.class));
```

This can be used when confirming an interaction did not occur within an observation window, though the test will wait the entire duration. Nor does it prove the action will never occur after the wait ends.

For complex asynchronous flows, prefer synchronizing through the application's own mechanisms:

- Wait for `CompletableFuture` completion with `get` or `join` using an appropriate timeout.
- Use a `CountDownLatch` in a test observer to wait until listeners finish processing.
- Use a controllable executor or test scheduler when verifying scheduling order and timing.
- Once synchronized, use standard `verify` to check interactions.

Example:

```java
@Test
void sendsNotificationAfterBackgroundTaskCompletes() throws Exception {
    CompletableFuture<Void> task = service.notifyAsync(command);

    task.get(2, TimeUnit.SECONDS);

    verify(notificationSender).send(any(Notification.class));
}
```

This example assumes the future completes only after the service finishes calling the notification sender. If the future only indicates that the task was queued, wait for an actual processing signal from the worker or listener.

## 8. Spies and interaction verification

Mocks simulate an entire object. Spies wrap a real object and invoke real methods by default when called unless the test stubs a specific method. Thus, spies can be verified just like mocks:

```java
List<String> names = new ArrayList<>();
List<String> spyNames = spy(names);

spyNames.add("Lan");

verify(spyNames).add("Lan");
assertThat(names).containsExactly("Lan");
```

Spies are useful when observing an interaction on a real object or overriding part of behavior in special cases. However, they also make tests more coupled to implementation. If one method calls another method on the same object, verification may observe that internal call; consider whether that interaction is truly a contract worth testing.

### 8.1. Be careful when stubbing spies

With mocks, `when(mock.method()).thenReturn(value)` normally does not run real logic. With spies, the expression inside `when(...)` can invoke the real method during stub setup. If the real method accesses files, databases, networks, or throws errors due to unready state, the test may trigger side effects before the main action runs.

With spies, use `doReturn(...).when(spy).method(...)` when you want to avoid calling the real method while stubbing:

```java
List<String> spyNames = spy(new ArrayList<>());

doReturn(10).when(spyNames).size();

assertThat(spyNames.size()).isEqualTo(10);
verify(spyNames).size();
```

The `doThrow`, `doAnswer`, and `doNothing` variants can also be used with spies. Only stub the necessary methods and keep the rest running for real so the test does not lose its purpose.

### 8.2. Do not use spies to test private methods

Mockito verifies calls through interceptable methods on mocks/spies; it is not a tool for testing private methods. If a private method holds complex business logic needing dedicated tests, consider extracting that responsibility into a collaborator with a clear API. If the logic is purely an implementation detail, verify outcomes of public methods instead of widening visibility just for tests.

## 9. Strict stubbing and unused stubs

When using `MockitoExtension`, strict stubbing helps detect unused stubs or configurations that do not match actual calls. This is valuable because a test might set up wrong data while still taking an unexpected branch.

```java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {
    @Mock
    CustomerRepository customers;

    @InjectMocks
    CustomerService service;

    @Test
    void findsCustomerById() {
        when(customers.findById(42L))
                .thenReturn(Optional.of(new Customer(42L, "Lan")));

        Customer customer = service.findById(42L);

        assertThat(customer.name()).isEqualTo("Lan");
        verify(customers).findById(42L);
    }
}
```

If a stub is declared but the service never calls it, inspect the test: there may be redundant setup, wrong parameters, or code taking another branch. Do not rush to disable strictness for the whole class to silence warnings.

If a stub is only used in certain scenarios, place it directly inside the tests that need it. When an optional stub is genuinely needed, Mockito offers `lenient()`, though it should be used intentionally and scoped narrowly.

## 10. Which interactions are worth verifying?

A practical rule is verifying interactions that cross meaningful boundaries or determine business behavior. For example:

| Scenario | Interaction worth verifying | What not to hardcode |
|---|---|---|
| Order creation | Repository saves order with right data; event published per contract | Call counts of internal helpers or mappers |
| Payment failure | Gateway is not called if input error is caught beforehand | Every repository read if not part of the contract |
| Email sending | Recipient, content, or template to use | Order of internal formatting steps |
| API retries | Attempt count if retry limit is a requirement | Log/metric calls that do not affect behavior |
| Domain event publishing | Exact event type and payload | How the service constructs the event object internally |
| Cache | Writing or invalidating cache if that is guaranteed behavior | Every cache read if implementation may change |

Ask yourself: if this interaction were removed, would users or another component observe wrong behavior? If yes, it is likely an important assertion. If it could only be noticed by reading the class's internal structure, the assertion is probably too tight.

## 11. Common verification mistakes

### Verifying before the action finishes

If an interaction happens asynchronously, verifying right after calling the service can run before the worker executes. Synchronize with a future, latch, or bounded wait mechanism before verifying.

### Checking only counts while ignoring payloads

`verify(gateway).charge(any())` does not prove the amount, currency, or order ID are right. Capture the argument or use matchers expressing key properties.

### Using `atLeastOnce()` for an exactly-once requirement

The test still passes if code sends duplicates. Use `times(1)` or default verify when the exact count is part of the contract.

### Overusing `verifyNoMoreInteractions`

It locks the test to a list of every known interaction. A new valid interaction can break the test. Use it only when zero extra interactions is genuinely a requirement.

### Verifying unnecessary ordering

`InOrder` can couple tests to implementation details. Verify ordering only when changing order alters outcomes or violates the contract.

### Reaching for a captor too early

For a simple argument with proper equality, passing it directly is usually easier to read. Use a captor when checking multiple fields or multiple calls.

### Confusing mock verification with confirming external systems

Verifying a repository mock only proves the service called the repository. It does not prove the database committed. Verifying an event publisher only proves the event reached the publisher; it does not prove listeners or brokers finished processing.

### Stubbing a spy with `when` and triggering real code

On a spy, the stub expression can run the real method. Use `doReturn`, `doThrow`, or the appropriate `do...when` API to avoid unintended side effects.

## 12. Workflow for writing clear verifications

When writing a unit test with mocks, follow this sequence:

1. Identify which collaborator acts as an observable boundary in the scenario.
2. Stub only the responses needed to guide the service into the target branch.
3. Invoke one public action on the component under test.
4. Assert on the return value or exception.
5. Verify required interactions: method, invocation count, and key arguments.
6. Verify forbidden interactions with `never()` or `verifyNoInteractions()` when required by the contract.
7. Only use `InOrder`, `verifyNoMoreInteractions`, or `timeout` when the test goal genuinely requires them.

A good test usually has few verifications, where each assertion clearly states what goes wrong if an interaction is skipped or sends wrong data. Test names should express the scenario, such as `doesNotChargeWhenAccountIsBlocked` or `publishesOrderCreatedAfterSavingOrder`.

## 13. Combined example: creating an order and publishing an event

An order creation service must save a record and publish an event containing the order's ID. If input data is invalid, the service must neither save nor publish an event.

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock
    private OrderRepository orders;

    @Mock
    private ApplicationEventPublisher events;

    @InjectMocks
    private OrderService service;

    @Test
    void savesOrderAndPublishesEventWithSavedId() {
        Order saved = new Order("order-42", "customer-7");
        when(orders.save(any(Order.class))).thenReturn(saved);

        Order result = service.create(new CreateOrderCommand("customer-7"));

        assertThat(result.id()).isEqualTo("order-42");

        ArgumentCaptor<Order> orderCaptor =
                ArgumentCaptor.forClass(Order.class);
        ArgumentCaptor<OrderCreated> eventCaptor =
                ArgumentCaptor.forClass(OrderCreated.class);

        InOrder order = inOrder(orders, events);
        order.verify(orders).save(orderCaptor.capture());
        order.verify(events).publishEvent(eventCaptor.capture());

        assertThat(orderCaptor.getValue().customerId()).isEqualTo("customer-7");
        assertThat(eventCaptor.getValue().orderId()).isEqualTo("order-42");
        verifyNoMoreInteractions(orders, events);
    }

    @Test
    void doesNotSaveOrPublishEventForInvalidCommand() {
        assertThatThrownBy(() -> service.create(new CreateOrderCommand("")))
                .isInstanceOf(InvalidOrderException.class);

        verifyNoInteractions(orders, events);
    }
}
```

In the success test, `InOrder` is used only because the example requirement mandates saving before publishing the event. If order is not part of the contract, each mock can be verified separately without `InOrder`. `verifyNoMoreInteractions` in the example states that these two collaborators must not receive additional interactions in this scenario; in real projects, keep this assertion only if that constraint is meaningful and stable.

The failure test verifies both the exception and the absence of side effects. If the service is still permitted to read data before detecting the error, replace `verifyNoInteractions` with narrower assertions such as `verify(orders, never()).save(...)` and `verify(events, never()).publishEvent(...)`.

## 14. Principles to remember

- Stub with `when(...).thenReturn(...)` to configure responses; verify to confirm interactions after the action.
- `verify(mock).method()` checks for exactly once by default; use `times`, `never`, `atLeast`, or `atMost` per the contract.
- Check payloads using direct arguments, matchers, or `ArgumentCaptor`; do not merely check that a method was called.
- Use `InOrder` when interaction ordering genuinely matters.
- `verifyNoInteractions` and `verifyNoMoreInteractions` have different scopes; avoid using them as default assertions on every mock.
- For asynchronous processing, synchronize via futures/latches or intentional timeouts before verifying.
- Spies invoke real methods by default; use `doReturn` or `do...when` APIs when stubbing without running real code.
- Interactions with a mock do not prove databases, listeners, or external systems completed their work.

Verification is most useful when it focuses on interaction contracts: which component must be called, with what data, how many times, and under which conditions it must not be called. Keeping assertions at meaningful boundaries helps tests catch real bugs while still allowing safe refactoring of internal structure.
