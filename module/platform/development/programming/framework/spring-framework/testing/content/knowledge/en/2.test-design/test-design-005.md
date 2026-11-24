# Verifying Results, State, and Side Effects

A test is valuable when it proves behavior that users or other components can observe. For an operation in a Spring application, that behavior typically has three aspects: **the returned result**, **the state after the operation**, and **the side effects produced**. Good test design starts by deciding which parts belong to the operation's contract, then choosing the right observation point and test level to verify them.

For example, when transferring money between two accounts, checking only that the method returns a `TransferReceipt` is not enough. We also need to know whether both account balances changed accurately, and whether a `TransferCompleted` event was published with the right amount. Conversely, when input is invalid, the contract may require throwing an exception, leaving balances unchanged, and emitting no notification. These assertions describe external behavior independent of how the class is internally split into methods.

## 1. Three Aspects to Observe

### 1.1. Result

The result is the value or signal returned directly to the caller. Depending on the layer under test, the result can be:

- A service's return value, such as `TransferReceipt`, `Optional`, a list, or a processing status.
- An exception thrown on failure, including the exact exception type and details needed to distinguish the cause.
- An HTTP response from a controller: status, headers, JSON body, cookies, or redirect.
- An asynchronous result such as `CompletableFuture`, `Mono`, or `Flux`, including emitted values, errors, and stream completion.

Do not check only that a result is non-`null` or threw no exception. Check properties that express the contract: identifiers, status, amounts, stable error details, HTTP status, and key response fields.

```java
@Test
void returnsReceiptForSuccessfulTransfer() {
    TransferReceipt receipt = transferService.transfer(1L, 2L, new BigDecimal("30.00"));

    assertThat(receipt).isNotNull();
    assertThat(receipt.transferId()).isNotBlank();
    assertThat(receipt.amount()).isEqualByComparingTo("30.00");
    assertThat(receipt.status()).isEqualTo(TransferStatus.COMPLETED);
}
```

The example above illustrates checking the business result. If the service also modifies data or calls other systems, add those assertions at the appropriate observation points; a valid return value does not automatically prove everything else worked.

### 1.2. State

State is the data that persists after the operation completes. It can reside in:

- Domain objects manipulated in memory.
- The database, including records, relationships, default values, and constraints.
- Caches, sessions, or other application-managed storage.
- Workflow state, such as an order moving from `PENDING` to `PAID`.

When checking state, read the data back through the interface a real consumer uses. In unit tests, you can inspect objects after calling the service or use an in-memory fake repository. In persistence tests, read the record back from the repository after synchronizing with the database.

Calling `verify(repository).save(entity)` only proves the code asked the repository to save the object. It does not prove SQL succeeded, mappings are right, data reached the database, or database constraints were satisfied. When the goal is proving data was persisted, verify state reloaded from the persistence layer.

### 1.3. Side Effects

Side effects are actions outside the primary return value and state produced by the operation. Examples include:

- Sending emails or SMS messages.
- Calling a payment gateway, shipping service, or third-party API.
- Publishing an application event or sending a message to a broker.
- Writing files, updating caches, creating audit logs, or firing webhooks.
- Scheduling a background job.

Side effects can be a critical part of the contract. When an order is confirmed, the system may be required to publish `OrderConfirmed`; when payment is declined, the system must not send a shipping request. Tests must therefore verify both required actions and forbidden actions in each scenario.

Not every internal call is a side effect worth testing. Which private helper a service calls, how many times it invokes a mapper, or how it decomposes an algorithm are usually implementation details. Focus on boundaries meaningful to external systems or users.

## 2. Selecting Assertions According to the Contract

Before writing assertions, describe the behavior using three questions:

1. **Result:** What does the caller receive, or which error must it receive?
2. **State:** Which data changes, and which data must remain unchanged?
3. **Side effects:** Which external components must be called, with what data, and which components must never be called?

You do not have to force every test to assert all three aspects. A parser test may need only the result. A repository test focuses on persisted state. A payment-orchestrating service may need to check result, state changes, and payment gateway calls. Choose assertions matching a meaningful scenario, avoiding cramming unrelated behaviors into one test.

| Operation type | Result to check | State to check | Side effects to check |
|---|---|---|---|
| Pure calculation | Return value and rounding rules | Usually none | Usually none |
| Domain-updating service | Business DTO/result or exception | Domain fields changed or preserved | Events, gateways, or ports called when in contract |
| Repository | Saved/loaded entity and persistence errors | Records, relations, constraints after flush and reload | Usually not tested here |
| REST controller | HTTP status, headers, body | Can be checked via service/repository in integration tests | Collaborators usually mocked in web slice |
| Message consumer | Ack/nack or processing outcome | Business state after message | Downstream messages, retries, or dead-lettering when in contract |

A helpful phrasing is **Given – When – Then**:

- **Given:** set up initial data and state.
- **When:** execute a single scenario action.
- **Then:** verify result, post-action state, and relevant side effects.

Test names should state the condition and expected behavior, such as `rejectsTransferWhenBalanceIsInsufficient` or `createsOrderAndPublishesConfirmationEvent`. Readers can grasp the intent without reading the entire test body.

## 3. Verifying Results and Exceptions with JUnit

JUnit 5 provides foundational assertions such as `assertEquals`, `assertThrows`, and `assertAll`. In projects using AssertJ, assertions such as `assertThat`, `isEqualByComparingTo`, and `extracting` express conditions clearly.

For `BigDecimal`, compare values by business semantics. `BigDecimal.equals` compares scale too, so `10.0` and `10.00` are not equal under `equals`. AssertJ provides `isEqualByComparingTo` to compare numeric value regardless of scale.

```java
@Test
void rejectsTransferWhenAmountIsNotPositive() {
    assertThatThrownBy(() -> transferService.transfer(
            1L, 2L, new BigDecimal("0.00")))
        .isInstanceOf(InvalidTransferAmountException.class)
        .hasMessageContaining("greater than zero");
}
```

Bind only to stable message fragments required by the contract. If messages are localized or vary with inputs, checking the entire string makes tests fragile even when behavior remains right. In such cases, checking exception type, error codes, or error properties is more meaningful.

When multiple conditions describe a single outcome, `assertAll` reports all failures in one run:

```java
assertAll(
    () -> assertThat(receipt.transferId()).isNotBlank(),
    () -> assertThat(receipt.amount()).isEqualByComparingTo("30.00"),
    () -> assertThat(receipt.status()).isEqualTo(TransferStatus.COMPLETED)
);
```

Do not use `assertAll` to pack independent behaviors into one large test. If a success case and failure case have different setups, split them into two tests so each has one clear failure reason.

## 4. Verifying State in Service Tests

A service unit test often uses Mockito to replace collaborators and a small fake to observe state. When a service mutates domain objects, inspect those objects directly. When verifying repository-interacting logic, use a fake repository or mock suited to the test's goal.

The example below assumes `TransferService` loads two accounts, debits the source, credits the target, saves both, and publishes an event. Domain APIs and type names may differ in real applications; what matters is picking the observation point.

```java
@ExtendWith(MockitoExtension.class)
class TransferServiceTest {
    @Mock
    private AccountRepository accounts;

    @Mock
    private ApplicationEventPublisher events;

    @InjectMocks
    private TransferService transferService;

    @Test
    void transfersMoneyAndUpdatesBothBalances() {
        Account source = Account.open(1L, new BigDecimal("100.00"));
        Account target = Account.open(2L, new BigDecimal("20.00"));
        when(accounts.findById(1L)).thenReturn(Optional.of(source));
        when(accounts.findById(2L)).thenReturn(Optional.of(target));

        TransferReceipt receipt = transferService.transfer(
                1L, 2L, new BigDecimal("30.00"));

        assertThat(receipt.status()).isEqualTo(TransferStatus.COMPLETED);
        assertThat(source.balance()).isEqualByComparingTo("70.00");
        assertThat(target.balance()).isEqualByComparingTo("50.00");
    }
}
```

These assertions verify the result and in-memory state of both aggregates. They do not yet prove data was written to the database. If the test goal includes persistence, add a separate repository or integration test that writes, flushes, clears the persistence context, and reloads.

For failure scenarios, compare before and after states. For example, when balance is insufficient, both balances must stay unchanged. This is an important assertion because a service might throw the right exception after already mutating one object before detecting the error.

```java
@Test
void keepsBalancesUnchangedWhenSourceHasInsufficientFunds() {
    Account source = Account.open(1L, new BigDecimal("10.00"));
    Account target = Account.open(2L, new BigDecimal("20.00"));
    when(accounts.findById(1L)).thenReturn(Optional.of(source));
    when(accounts.findById(2L)).thenReturn(Optional.of(target));

    assertThatThrownBy(() -> transferService.transfer(
            1L, 2L, new BigDecimal("30.00")))
        .isInstanceOf(InsufficientFundsException.class);

    assertThat(source.balance()).isEqualByComparingTo("10.00");
    assertThat(target.balance()).isEqualByComparingTo("20.00");
}
```

Checking initial and final states lets tests express business-level atomicity clearly: failed operations leave no partial mutations in domain objects. If the application also relies on database transactions, persistence tests must verify rollback at the proper transaction boundary.

## 5. Verifying Side Effects with Mockito

Mockito lets you verify a collaborator was called, how many times, and with what arguments. Use `ArgumentCaptor` when inspecting event payloads or outbound requests.

```java
@Test
void publishesTransferCompletedEventWithTheTransferredAmount() {
    Account source = Account.open(1L, new BigDecimal("100.00"));
    Account target = Account.open(2L, new BigDecimal("20.00"));
    when(accounts.findById(1L)).thenReturn(Optional.of(source));
    when(accounts.findById(2L)).thenReturn(Optional.of(target));

    transferService.transfer(1L, 2L, new BigDecimal("30.00"));

    ArgumentCaptor<TransferCompleted> eventCaptor =
            ArgumentCaptor.forClass(TransferCompleted.class);
    verify(events).publishEvent(eventCaptor.capture());
    assertThat(eventCaptor.getValue().amount())
            .isEqualByComparingTo("30.00");
    assertThat(eventCaptor.getValue().sourceAccountId()).isEqualTo(1L);
    assertThat(eventCaptor.getValue().targetAccountId()).isEqualTo(2L);
}
```

When a failure scenario forbids sending notifications, verify that boundary:

```java
verify(events, never()).publishEvent(any(TransferCompleted.class));
```

Or if the event publisher serves only this behavior in the test:

```java
verifyNoInteractions(events);
```

Pick the narrowest assertion matching the contract. Calling `verifyNoInteractions` on a multi-purpose mock can make tests brittle when the system adds another legitimate interaction. Similarly, avoid adding `verifyNoMoreInteractions` to every mock by default; that tends to lock tests to call order and internal structure.

Distinguish three levels of evidence clearly:

1. `verify(events).publishEvent(...)` proves the service called the Spring event publisher.
2. Testing the listener inside an ApplicationContext proves the listener receives and handles the event under running configuration.
3. Integration testing with a real broker or compatible environment proves messages are sent/received over messaging infrastructure.

One level does not automatically prove the next. For instance, confirming `publishEvent` was called does not prove the listener finished, an email was sent, or a broker persisted the message.

## 6. Verifying Persisted Data with Spring Test

With JPA, `@DataJpaTest` creates a test slice focused on repositories and persistence configuration. Tests typically run in a managed transaction that rolls back afterward. This isolates data, yet introduces a common pitfall: a newly saved entity may still reside in the persistence context, so reading it back does not prove data was written to and reloaded from the database.

To exercise SQL execution and mapping, flush and clear the persistence context before reloading:

```java
@DataJpaTest
class AccountRepositoryTest {
    @Autowired
    private AccountRepository accounts;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void persistsAndReloadsAccountBalance() {
        Account saved = accounts.save(
                Account.open(null, new BigDecimal("70.00")));

        entityManager.flush();
        Long accountId = saved.id();
        entityManager.clear();

        Account reloaded = accounts.findById(accountId).orElseThrow();

        assertThat(reloaded.balance()).isEqualByComparingTo("70.00");
    }
}
```

`flush()` pushes pending changes to the database within the current transaction. `clear()` detaches managed entities from the persistence context, forcing the next read to reload from the database. This catches mapping, type, SQL, and constraint defects that inspecting objects right after `save()` can miss.

However, flush is not equivalent to commit. A test transaction rolled back after the test still does not prove behavior that depends on an actual commit. If you need to test commit boundaries, transaction propagation, post-commit triggers, or post-commit handlers, design tests with real transaction boundaries—such as driving work with `TransactionTemplate` and asserting data from a separate transaction after the first commits.

When testing rollback, run operations inside a rollback-capable transaction, trigger the failure at the target point, then read data from a fresh transaction to verify final state. Avoid reading in the same persistence context because cached entities can skew results.

## 7. Verifying HTTP Responses with MockMvc and WebTestClient

At the web layer, the outcome is typically an HTTP response. `MockMvc` fits testing Spring MVC without starting a real HTTP server. A web slice with `@WebMvcTest` focuses on controllers, binding, validation, exception handlers, serialization, and web configuration.

```java
@WebMvcTest(TransferController.class)
class TransferControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private TransferService transferService;

    @Test
    void returnsCreatedResponseForSuccessfulTransfer() throws Exception {
        when(transferService.transfer(anyLong(), anyLong(), any()))
                .thenReturn(new TransferReceipt(
                        "tr-42", new BigDecimal("30.00"),
                        TransferStatus.COMPLETED));

        mockMvc.perform(post("/api/transfers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sourceAccountId": 1,
                                  "targetAccountId": 2,
                                  "amount": 30.00
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(jsonPath("$.transferId").value("tr-42"))
                .andExpect(jsonPath("$.status").value("COMPLETED"));
    }
}
```

In a web slice, the service is mocked so the test focuses on the HTTP contract. This test does not prove the service updated the database. That responsibility belongs to service/repository integration tests. Nor should you test private controller helper calls; assert the response the client receives.

For Spring WebFlux applications, `WebTestClient` can test controllers or invoke endpoints in an integration environment. When verifying a `Flux` or `Mono`, assert emitted values, errors, and completion when they belong to the contract. Do not verify only the first element if an endpoint can return multiple elements or error after the first element.

## 8. Events, Transactions, and Asynchronous Processing

Spring application events are published and handled synchronously on the caller thread by default unless a listener is configured asynchronously. When using `@Async`, a message broker, or an executor, completion timing no longer coincides with the service returning.

Key distinctions:

- Testing event emission: mock `ApplicationEventPublisher` or observe events in the application context.
- Testing a listener: start an ApplicationContext with the real listener and assert the state the listener produces.
- Testing post-commit events: use a transaction that actually commits. Default test-managed transaction rollback can prevent `@TransactionalEventListener(phase = AFTER_COMMIT)` listeners from firing.
- Testing async tasks: synchronize on completion using `CountDownLatch`, `CompletableFuture`, or a bounded wait condition; do not use fixed `Thread.sleep` calls to guess completion time.

Example using a latch to wait for an async listener to finish:

```java
CountDownLatch handled = new CountDownLatch(1);

@Async
@EventListener
void onTransferCompleted(TransferCompleted event) {
    // Handle event inside listener.
    handled.countDown();
}

@Test
void eventuallyHandlesPublishedEvent() throws InterruptedException {
    eventPublisher.publishEvent(new TransferCompleted(/* test data */));

    assertThat(handled.await(2, TimeUnit.SECONDS)).isTrue();
}
```

This illustrates test synchronization mechanics; in real code, the listener is normally a separate bean and the latch sits in a test observer or injected collaborator. Timeouts must be generous enough for CI environments yet finite so tests do not hang. When a test times out, fail clearly rather than continuing assertions on incomplete state.

For retried tasks, define the contract for attempt count, retry conditions, and final state. Assert call count only when exact attempt count is a meaningful operational requirement; otherwise prioritize checking the final outcome and absence of duplicate side effects.

## 9. Verifying External Side Effects Outside the Application

For email, payment, shipping, or third-party APIs, unit tests should depend on an application-controlled port or interface. Mockito can verify requests are sent with the right data, while fakes can simulate stable responses. Never call real external services in unit tests because doing so ties tests to networks, credentials, costs, and external system state.

At the integration level, when verifying HTTP client behavior, serialization, timeouts, or retries against external services, use a mock server or controlled test environment. For databases, brokers, or caches, Testcontainers or equivalent test infrastructure can provide real services in isolation. Choose real infrastructure when the test question concerns protocol behavior or configuration that mocks cannot prove.

Common side-effect contracts:

- Successful payment: send one authorize request with the exact amount and currency.
- Declined payment: create no shipping request.
- Confirmed order: publish an event with the exact order ID and status.
- Repeated resource-creation request: send no duplicate notification when idempotency is guaranteed.
- Invalid data: call no gateway, emit no event, and write no business record.

When asserting "no side effects," define the exact scope. For example, a search command may be allowed to record a metric while forbidden from creating a payment transaction. Do not use a blanket assertion banning all interactions if the contract forbids only one specific action.

## 10. Choosing the Test Level in Spring

Each test level provides a distinct kind of evidence:

| Test level | Common Spring tools | Primary evidence |
|---|---|---|
| Unit test | JUnit 5, Mockito, custom fakes | Service/domain rules, return values, object state, port calls |
| Web slice | `@WebMvcTest`, `MockMvc` | Binding, validation, HTTP status, headers, body, exception mapping |
| Persistence slice | `@DataJpaTest` | Mapping, queries, SQL, constraints, database state |
| Integration test | `@SpringBootTest` with test dependencies | Bean wiring, transactions, event listeners, combined processing flows |
| End-to-end test | Application running in near-real environment | Behavior across HTTP, database, broker, and dependent system boundaries |

Do not use `@SpringBootTest` for every situation. Broader tests take longer and introduce more potential failure causes. Use the smallest level that still supplies the required evidence; expand only when what must be proved lies in configuration or collaboration across multiple components.

A service test with a mocked repository can prove the service asked to save data, but cannot prove the repository works. A repository test can prove mapping, but cannot prove a controller returns the right HTTP status. Dividing responsibilities this way keeps each test's target and failure signal clear.

## 11. Common Assertion Design Mistakes

### Checking Only the Return Value

A service might return a success receipt yet fail to persist data or publish a required event. Check state and side effects as well when they belong to the contract.

### Checking Only the `save` Call

Mockito verifies a call to the mock, not SQL, transactions, or final persisted data. Use repository or integration tests to verify persistence.

### Testing Implementation Instead of Behavior

Asserting internal helper call counts, externally meaningless step ordering, or private method names makes tests brittle during refactoring. Verify interactions only at meaningful boundaries.

### Checking Too Little on Failure Branches

A test checks the exception yet ignores mutated data or already-sent messages. For every important failure branch, assert preserved state and forbidden side effects.

### Reading Entities Immediately After Saving

The persistence context can return the same in-memory object. Flush and clear before reloading to exercise the database path.

### Waiting for Async Work with `Thread.sleep`

Fixed durations can be too short in CI or unnecessarily slow tests down. Use latches, futures, or bounded condition waits synchronized on actual completion events.

### Mocking Every Collaborator in Integration Tests

If every component is mocked, the test checks only how mocks are called and ceases to verify real wiring. Keep components under test real and substitute only external boundaries.

### Overly Broad or Overly Strict Assertions

`isNotNull()` rarely proves a business rule. Conversely, whole-object equality can tie tests to technical fields such as timestamps, generated IDs, or non-contract metadata. Pick the important fields and be clear why they matter.

## 12. Process for Designing a Trustworthy Test

When starting a scenario, follow these steps:

1. Write the relevant initial conditions: data, permissions, current state, and collaborator responses.
2. Invoke one public action on the component under test.
3. Check the direct result: return value, exception, or HTTP response.
4. Read post-action state at the right boundary to verify: object, fake repository, or database.
5. Check required side effects and forbidden side effects.
6. Ensure the test sets up its own data, has no order dependency, and uses timeouts for async processing.

Before finishing, ask yourself: if you delete the line of code performing the key change, which test fails? If the answer is "no test," you may only be testing the happy path without checking real outcomes. If a test fails only when renaming an internal helper, assertions may be coupled too tightly to implementation.

## 13. Example Scenario Matrix for a Transfer Operation

The matrix below helps identify needed assertions before writing tests. Not every row requires a separate test; assertions describing one scenario can be grouped.

| Scenario | Result | Final state | Side effects |
|---|---|---|---|
| Valid transfer | Returns `COMPLETED` receipt | Debits source, credits target by exact amount | Publishes one `TransferCompleted` with accurate payload |
| Zero or negative amount | Throws validation error | Balances unchanged | No gateway call or event published |
| Insufficient balance | Throws `InsufficientFundsException` | Both balances unchanged | No completion event published |
| Account not found | Throws appropriate not-found error | No partial transaction created | No completion event published |
| Repeated request with same idempotency key | Returns existing result per contract | No second transaction created | No duplicate payment request sent |

This matrix also uncovers missing contract coverage. For example, if a test checks only `COMPLETED` without verifying balances and events, a data-update bug or mispublished event can slip through.

## 14. Principles to Remember

- Return values show what the caller receives.
- State shows how data ends up.
- Side effects show which external boundaries the system affected.
- Verify only what belongs to the scenario's contract, at the test level capable of providing evidence.
- Mocks verify interactions; fakes support observing behavior; integration tests verify collaboration with real infrastructure.
- For persistence, clearly distinguish `save`, `flush`, and `commit`; for async processing, distinguish dispatching work and completing execution.

A well-designed test fails when critical behavior breaks while staying stable when internal structure is refactored. Use results, state, and side effects as three complementary lenses to thoroughly verify every operation's contract in a Spring application.
