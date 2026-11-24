# Avoid Using Dependency Injection as the Sole Proof That Business Logic Is Correct

Dependency Injection (DI) lets Spring supply the required dependencies to a bean. When the `ApplicationContext` starts successfully, we have evidence that Spring read the configuration, created the required beans, and resolved the dependency relationships within that context.

However, **being able to inject dependencies does not mean the application's business logic is correct**. A service can receive all its repositories, policies, and gateways yet still miscalculate money, apply the wrong rules, mishandle state, or trigger unintended side effects. DI proves that components can be wired together; behavioral testing proves that those components do what the system requires.

In Spring Framework Testing, three questions must be clearly distinguished:

1. Does Spring create and wire the right beans?
2. Does a service enforce the right business rules for given inputs and state?
3. Do real components collaborate properly across databases, transactions, proxies, or external communication?

Each question requires appropriate evidence and test scope. A context test can answer the first question, but it does not automatically answer the remaining two.

## 1. What does DI prove?

Suppose an application has a money transfer service:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferPolicy transferPolicy;

    public TransferService(
            AccountRepository accountRepository,
            TransferPolicy transferPolicy) {
        this.accountRepository = accountRepository;
        this.transferPolicy = transferPolicy;
    }

    public TransferReceipt transfer(
            String sourceId,
            String destinationId,
            BigDecimal amount) {
        // Transfer rules and repository coordination.
    }
}
~~~

When Spring successfully instantiates `TransferService`, it shows that the container found matching dependencies to pass into the constructor under the active configuration.

A context test can verify that the bean exists:

~~~java
@SpringBootTest
class TransferServiceContextTest {

    @Autowired
    private TransferService transferService;

    @Test
    void createsTransferServiceBean() {
        assertNotNull(transferService);
    }
}
~~~

This test is useful as a smoke test for context startup. It can catch errors such as:

- No bean matches the `AccountRepository` type.
- Multiple beans share the same type without a clear selection.
- A constructor dependency is missing.
- A configuration class was not loaded.
- Component scanning missed the service.
- A bean depends on configuration or a resource that prevents the `ApplicationContext` from starting.

That is evidence about configuration and wiring. The test has not called `transfer()`, has not checked balances, has not verified which account was debited, and has not verified whether the transaction was saved properly.

### What DI does not prove

Successful injection does not prove:

- The service applies the right business rules.
- Return values are accurate for the input data.
- Exceptions are thrown properly in invalid scenarios.
- Repositories execute queries accurately or persist data properly.
- The selected bean is the right implementation from a business standpoint.
- Transactions roll back when a step fails.
- Events or requests sent to another system carry the right payload.
- Unauthorized side effects were prevented.

For instance, Spring may successfully inject a `DiscountPolicy` bean, yet that policy might apply the wrong discount rate. Likewise, `OrderService` may receive the right `OrderRepository` yet still save orders in `PAID` status when the specification requires `PENDING`.

**Successful context startup is a configuration precondition, not a verdict on business correctness.**

## 2. Distinguishing three layers of evidence

A Spring test suite usually needs different layers of evidence:

| Layer of evidence | Question | Common testing approach |
|---|---|---|
| Wiring/configuration | Which beans are created and which dependencies are injected? | Context test, `@SpringJUnitConfig`, `@SpringBootTest` |
| Business behavior | What do public methods return, which conditions do they reject, and what effects do they produce? | Unit tests with JUnit Jupiter and test doubles |
| Integration behavior | How do real beans, proxies, databases, and external integrations work together? | Integration tests with Spring context and suitable infrastructure |

These layers complement one another. Unit tests can verify fee calculation rules without Spring. Context tests can verify that services and policies are configured as beans. Integration tests can verify that transactions and real repositories work together.

Do not substitute the outcome of one layer for evidence from another.

### Example with money transfer

Suppose the business contract specifies:

- The transfer amount must be greater than 0.
- Both source and destination accounts must exist.
- The source account must have sufficient balance.
- The destination account is credited with the exact amount.
- The source account is debited by the exact amount.
- The transaction is recorded with status `COMPLETED`.
- If recording the transaction fails within a transaction, balance changes must roll back.

Each guarantee carries different risks:

- Constructor injection could fail due to a missing `AccountRepository`.
- The service could debit twice or miscalculate balances.
- The repository could save the wrong transaction status.
- The transaction might not roll back when saving the transaction record fails.

A context test that only checks bean creation will not detect those business and persistence bugs.

## 3. Why isn't contextLoads() enough?

A common test in Spring Boot projects looks like:

~~~java
@SpringBootTest
class ApplicationContextTest {

    @Test
    void contextLoads() {
    }
}
~~~

This test asks Spring to start the `ApplicationContext`. If the context starts, the test passes. This is a useful check for overall configuration, yet the test method triggers no specific business behavior.

For example, the test can still pass when:

- `DiscountService` returns the wrong discount amount.
- `TransferService` skips balance checks.
- A mapper translates an entity status incorrectly.
- A controller returns HTTP 200 instead of HTTP 201.
- A repository query filters on the wrong condition.
- An event contains the wrong customer ID.
- A service saves data before checking authorization.

None of these bugs necessarily stop the `ApplicationContext` from starting. Beans can be instantiated completely cleanly while the logic inside them remains broken.

Keep `contextLoads()` if you want a smoke test for application startup. At the same time, write behavioral tests with concrete assertions for critical rules.

### Context startup test and behavior test

~~~java
@SpringBootTest
class TransferServiceTest {

    @Autowired
    private TransferService transferService;

    @Test
    void contextLoads() {
        assertNotNull(transferService);
    }

    @Test
    void transfersFundsAccordingToBusinessRules() {
        // Needs account state setup,
        // trigger transfer, and verify balances/results.
    }
}
~~~

The first method only verifies that the bean can be injected. Only the second method begins testing behavior. If you want to verify business logic through the real service in the context, you must prepare data, call public methods, and assert meaningful outcomes.

## 4. Testing business rules through public methods

Unit tests should call the service's public API like a real caller. The test sets up initial state, invokes the method, and checks observable outcomes.

The example below illustrates a `TransferService` independent of the Spring container:

~~~java
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferPolicy transferPolicy;

    public TransferService(
            AccountRepository accountRepository,
            TransferPolicy transferPolicy) {
        this.accountRepository = accountRepository;
        this.transferPolicy = transferPolicy;
    }

    public TransferReceipt transfer(
            String sourceId,
            String destinationId,
            BigDecimal amount) {

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Transfer amount must be positive");
        }

        Account source = accountRepository.findById(sourceId)
                .orElseThrow(() ->
                        new AccountNotFoundException(sourceId));

        Account destination = accountRepository
                .findById(destinationId)
                .orElseThrow(() ->
                        new AccountNotFoundException(destinationId));

        transferPolicy.checkAllowed(source, destination, amount);

        source.debit(amount);
        destination.credit(amount);

        accountRepository.save(source);
        accountRepository.save(destination);

        return new TransferReceipt(
                sourceId,
                destinationId,
                amount,
                TransferStatus.COMPLETED);
    }
}
~~~

The domain interfaces and types are illustrated as follows:

~~~java
public interface AccountRepository {
    Optional<Account> findById(String accountId);

    Account save(Account account);
}

public interface TransferPolicy {
    void checkAllowed(
            Account source,
            Account destination,
            BigDecimal amount);
}

public record TransferReceipt(
        String sourceId,
        String destinationId,
        BigDecimal amount,
        TransferStatus status) {
}

public enum TransferStatus {
    COMPLETED
}
~~~

The example assumes `Account` has `debit` and `credit` methods enforcing balance rules. It also assumes `TransferPolicy` throws a domain exception when a transfer is disallowed.

To test service rules, you can instantiate `TransferService` directly via its constructor. There is no need to boot Spring just to confirm that the amount must be positive or that transferred amounts are computed accurately.

## 5. Using unit tests to prove behavior, not just bean existence

Mockito lets you control dependency outputs to drive the service into each business branch. Tests can assert the receipt, the required balance updates, and prevented side effects.

Example testing a successful transfer:

~~~java
@ExtendWith(MockitoExtension.class)
class TransferServiceUnitTest {

    @Mock
    private AccountRepository accountRepository;

    @Mock
    private TransferPolicy transferPolicy;

    @InjectMocks
    private TransferService transferService;

    @Test
    void transfersRequestedAmountBetweenExistingAccounts() {
        Account source = new Account(
                "A-1", new BigDecimal("100.00"));
        Account destination = new Account(
                "B-2", new BigDecimal("40.00"));

        when(accountRepository.findById("A-1"))
                .thenReturn(Optional.of(source));
        when(accountRepository.findById("B-2"))
                .thenReturn(Optional.of(destination));

        TransferReceipt receipt = transferService.transfer(
                "A-1", "B-2", new BigDecimal("25.00"));

        assertAll(
                () -> assertEquals(
                        TransferStatus.COMPLETED, receipt.status()),
                () -> assertEquals(
                        new BigDecimal("25.00"), receipt.amount()),
                () -> assertEquals(
                        new BigDecimal("75.00"), source.balance()),
                () -> assertEquals(
                        new BigDecimal("65.00"), destination.balance())
        );

        verify(accountRepository).save(source);
        verify(accountRepository).save(destination);
    }
}
~~~

This test verifies behavior via the public `transfer()` method. It asserts the resulting balances and the receipt returned to the caller. Working constructor injection on the service is merely how the test builds the object; the primary evidence is the business outcome.

In real tests, ensure `Account` has appropriate equality or accessors matching your assertions. This example uses a mocked repository to isolate service logic, so it does not prove that data was persisted to a database.

### Testing invalid input

~~~java
@Test
void rejectsNonPositiveAmountWithoutChangingAccounts() {
    assertThrows(
            IllegalArgumentException.class,
            () -> transferService.transfer(
                    "A-1", "B-2", BigDecimal.ZERO)
    );

    verify(accountRepository, never()).save(any(Account.class));
}
~~~

This assertion confirms the service rejects a zero amount and does not attempt to save accounts. If the contract also forbids looking up accounts when the amount is invalid, you can verify the repository was not called; only add that assertion when validation order is a guaranteed contract.

### Testing non-existent account

~~~java
@Test
void rejectsTransferWhenSourceAccountDoesNotExist() {
    when(accountRepository.findById("missing"))
            .thenReturn(Optional.empty());

    assertThrows(
            AccountNotFoundException.class,
            () -> transferService.transfer(
                    "missing", "B-2", new BigDecimal("10.00"))
    );

    verify(accountRepository, never()).save(any(Account.class));
}
~~~

This test verifies the exception type returned to the caller and that the service performs no save operation when the source account does not exist.

### Testing policy rejection

~~~java
@Test
void doesNotSaveAccountsWhenTransferPolicyRejectsRequest() {
    Account source = new Account(
            "A-1", new BigDecimal("100.00"));
    Account destination = new Account(
            "B-2", new BigDecimal("40.00"));

    when(accountRepository.findById("A-1"))
            .thenReturn(Optional.of(source));
    when(accountRepository.findById("B-2"))
            .thenReturn(Optional.of(destination));

    doThrow(new TransferNotAllowedException())
            .when(transferPolicy)
            .checkAllowed(source, destination, new BigDecimal("25.00"));

    assertThrows(
            TransferNotAllowedException.class,
            () -> transferService.transfer(
                    "A-1", "B-2", new BigDecimal("25.00"))
    );

    verify(accountRepository, never()).save(any(Account.class));
}
~~~

The test verifies that the policy is consulted to decide whether the transfer is permitted and that the service does not save accounts when the policy rejects it. It still does not verify that the real `TransferPolicy` implementation enforces all rules. That policy needs its own unit tests or inclusion in an appropriate integration test.

## 6. Using a separate context test to verify DI/wiring

Once unit tests cover business logic, you can write a small test confirming Spring creates and wires the beans as expected.

Example test configuration using an in-memory fake repository and a real policy:

~~~java
@Configuration
class TransferTestConfiguration {

    @Bean
    AccountRepository accountRepository() {
        return new InMemoryAccountRepository();
    }

    @Bean
    TransferPolicy transferPolicy() {
        return new StandardTransferPolicy();
    }

    @Bean
    TransferService transferService(
            AccountRepository accountRepository,
            TransferPolicy transferPolicy) {
        return new TransferService(
                accountRepository, transferPolicy);
    }
}
~~~

Test using that configuration:

~~~java
@SpringJUnitConfig(TransferTestConfiguration.class)
class TransferServiceWiringTest {

    @Autowired
    private TransferService transferService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void createsServiceWithConfiguredCollaborators() {
        assertNotNull(transferService);
        assertNotNull(accountRepository);
    }
}
~~~

This test confirms the small context can create the service and repository. If the goal is solely wiring, that is appropriate evidence.

You can extend the test to invoke `transfer` with data prepared in `InMemoryAccountRepository` and check the results. Doing so simultaneously verifies the service works with the selected configuration and fake repository. It still does not prove that the production repository implementation or real database works.

### Do not let mocks replace the very bean under verification

Suppose the risk is that Spring picks the wrong `TransferPolicy` due to `@Primary` or `@Qualifier`. If a test uses `@MockitoBean` to replace `TransferPolicy`, it removes the real implementation from the context. The test might pass even while production configuration selects the wrong policy.

When testing wiring or bean selection:

- Keep the real bean that is the subject of risk.
- Load the profiles and properties matching the scenario.
- Inspect the injected implementation or trigger implementation-specific behavior.
- Mock only dependencies outside the risk scope.

When testing controller mappings where the service is out of scope, mocking the service makes sense. When testing that the service itself is injected with the real policy, replacing the policy with a mock destroys the needed evidence.

## 7. Distinguishing @InjectMocks from Spring Dependency Injection

Both Mockito and Spring can instantiate objects with dependencies, yet they work via two completely different mechanisms.

### Mockito's @InjectMocks

~~~java
@ExtendWith(MockitoExtension.class)
class InvoiceServiceTest {

    @Mock
    private InvoiceRepository invoiceRepository;

    @InjectMocks
    private InvoiceService invoiceService;
}
~~~

Mockito attempts to instantiate `InvoiceService` and pass matching mocks into its constructor, setters, or fields according to Mockito's rules. It does not start an `ApplicationContext`, run component scanning, apply Spring AOP proxies, or verify production bean configuration.

This is a convenient mechanism for unit testing.

### Spring's @Autowired

~~~java
@SpringJUnitConfig(InvoiceTestConfiguration.class)
class InvoiceServiceContextTest {

    @Autowired
    private InvoiceService invoiceService;
}
~~~

Spring creates an `ApplicationContext`, registers beans according to configuration, resolves dependencies, and manages bean lifecycles. If configuration involves transactions or AOP, Spring can supply the corresponding proxies.

This is the right mechanism for testing wiring and container-dependent behaviors.

### Comparison

| Aspect | Mockito `@InjectMocks` | Spring `@Autowired` |
|---|---|---|
| Object creation mechanism | Mockito | Spring container |
| Requires `ApplicationContext` | No | Yes |
| Component scan/configuration | No | Yes, per configuration |
| Applies Spring AOP proxies | No | Yes, if configuration requires |
| Tests bean selection/profiles | No | Yes |
| Primary purpose | Logic unit tests | Context/wiring/integration tests |

Do not use a passing unit test with `@InjectMocks` to conclude that Spring DI is configured properly. Likewise, do not use successful `@Autowired` injection to conclude that business logic is correct.

## 8. Verifying bean selection: @Primary, @Qualifier, and profiles

A wiring bug can occur even while the context still starts: Spring picks an implementation that is type-compatible yet wrong for the environment or business purpose.

For example, suppose there are two policies:

~~~java
@Component
@Primary
class StandardTransferPolicy implements TransferPolicy {
    // Regular money transfer rules.
}

@Component
class RestrictedTransferPolicy implements TransferPolicy {
    // Rules for restricted accounts.
}
~~~

If a service simply injects `TransferPolicy`, Spring uses the bean marked `@Primary`. The context starts successfully, yet that does not prove the chosen implementation fits each flow's requirements.

You can use `@Qualifier` to specify the dependency explicitly:

~~~java
public TransferService(
        AccountRepository accountRepository,
        @Qualifier("standardTransferPolicy")
        TransferPolicy transferPolicy) {
    this.accountRepository = accountRepository;
    this.transferPolicy = transferPolicy;
}
~~~

If the implementation is selected by profile:

~~~java
@Configuration
@Profile("test")
class TestTransferConfiguration {

    @Bean
    TransferPolicy transferPolicy() {
        return new PermissiveTransferPolicy();
    }
}
~~~

A context test should activate the profile under test and verify the right bean is created. Yet if the policy has business rules, tests for that policy's behavior are still needed.

There are two distinct kinds of assertions:

- **Bean selection assertion:** which implementation did Spring inject?
- **Behavior assertion:** how does that implementation handle business scenarios?

Both may be needed when risk spans both configuration and policy logic.

## 9. Constructor injection clarifies dependencies, yet does not prove correct logic

Constructor injection is generally recommended because:

- Required dependencies are expressed directly in the constructor.
- `final` fields can be used.
- Objects are hard to instantiate missing dependencies.
- Unit tests can instantiate the object directly.
- Dependency graphs are easy to read and verify.

Example:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway paymentGateway;
    private final PaymentRepository paymentRepository;

    public PaymentService(
            PaymentGateway paymentGateway,
            PaymentRepository paymentRepository) {
        this.paymentGateway = paymentGateway;
        this.paymentRepository = paymentRepository;
    }
}
~~~

However, constructor injection only guarantees that the object receives the required references when constructed. It does not guarantee that:

- The gateway charges the right amount.
- The service sends the right currency.
- The service handles timeouts properly.
- The repository saves the right status.
- The service skips calling the gateway on invalid requests.

Those guarantees require behavioral tests through public methods.

### Field injection does not make business logic automatically right either

~~~java
@Service
public class PaymentService {

    @Autowired
    private PaymentGateway paymentGateway;
}
~~~

Field injection makes plain unit tests harder to instantiate because dependencies are not passed via the constructor. Yet even when Spring successfully injects the field, payment logic still needs tests with explicit inputs and outcomes.

Test quality comes from the evidence a test gathers, not from which DI annotation a class uses.

## 10. When do @Transactional and proxies need testing?

A service may be annotated with:

~~~java
@Service
public class TransferService {

    @Transactional
    public TransferReceipt transfer(...) {
        // Update multiple records.
    }
}
~~~

When Spring manages the bean and transaction infrastructure is configured, calls going through the proxy can open a transaction. If a test instantiates the object directly:

~~~java
TransferService service =
        new TransferService(accountRepository, transferPolicy);
~~~

then `@Transactional` is not automatically enforced. Unit tests can still verify calculation logic and collaborator calls, but they cannot prove transaction rollback.

To test transactions:

- Load a Spring context with a transaction manager.
- Use appropriate test repositories and database.
- Call the service bean injected from the context, through its proxy.
- Trigger a scenario where one write succeeds and a later step fails.
- Inspect data after the transaction to confirm rollback or commit per contract.

Example test skeleton:

~~~java
@SpringBootTest
class TransferTransactionTest {

    @Autowired
    private TransferService transferService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void rollsBackBalanceChangesWhenTransferRecordCannotBeSaved() {
        // Prepare accounts in the test database.
        // Trigger failure condition when saving transfer record.
        // Call transferService through the Spring-injected bean.
        // Re-read accounts after the transaction and verify old balances.
    }
}
~~~

This is a different goal from confirming the `TransferService` bean exists. Loading the context alone does not trigger a transaction. Calling the method through the proxy and checking database state is what produces evidence for transactional behavior.

Note that a test method annotated with `@Transactional` itself can cause the test's transaction to wrap the service call. Understand propagation, commit/rollback, and test transaction boundaries so you do not inadvertently mask the behavior you want to verify. For tests needing to verify data after the service commits or rolls back, you may need to control the test transaction and read data in a separate transaction or after the appropriate transaction completes.

## 11. Verifying Spring configuration and business logic with two separate tests

Suppose `PaymentService` depends on a `PaymentGateway` selected via the `payment.provider` property.

You can separate the two goals:

### Configuration test for gateway selection

~~~java
@SpringBootTest(properties = "payment.provider=stub")
class PaymentGatewayConfigurationTest {

    @Autowired
    private PaymentGateway paymentGateway;

    @Test
    void selectsStubGatewayForTestProvider() {
        assertInstanceOf(
                StubPaymentGateway.class,
                paymentGateway);
    }
}
~~~

This test verifies that configuration picks the `StubPaymentGateway` implementation under a specific property condition.

### Business logic test for PaymentService

~~~java
@ExtendWith(MockitoExtension.class)
class PaymentServiceTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Mock
    private PaymentRepository paymentRepository;

    @InjectMocks
    private PaymentService paymentService;

    @Test
    void recordsSuccessfulPayment() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new GatewayResult(true, "txn-42"));

        PaymentResult result = paymentService.pay(
                new PaymentRequest("order-7", new BigDecimal("50.00")));

        assertEquals(PaymentStatus.PAID, result.status());
        assertEquals("txn-42", result.transactionId());
    }
}
~~~

The first test verifies bean selection. The second test verifies how the service reacts to the gateway result. If you need to verify that the real gateway communicates properly with the provider, write a dedicated adapter/integration test.

Separating them gives each test a clear conclusion and avoids a large context test stuffed with mocks that obscure what is actually under test.

## 12. Checking that a bean exists is not the same as checking it is used properly

A test can verify that both service and repository exist:

~~~java
assertNotNull(transferService);
assertNotNull(accountRepository);
~~~

Yet if `TransferService` accidentally uses a different repository or an inappropriate policy, both assertions can still pass.

When specific wiring is a risk, verify the dependency selection result in one of these ways:

- Load a context containing only explicitly named beans and verify the injected implementation.
- Use qualifiers and check beans with the expected name/type.
- Invoke behavior distinctive to the real implementation.
- Check profile/property configurations selecting the right bean.
- Test the proxy if behavior depends on AOP.

There is no need to access private fields of a service via reflection just to verify every dependency. Prefer verifying the bean graph through configuration and observable behavior. If dependency selection cannot be observed via public behavior and is genuinely a configuration contract, you can verify the Spring-managed implementation bean by injecting that bean directly in a context test.

## 13. Do not let mocks hide DI bugs

Mocks are an isolation tool, yet they can also remove the very dependency that needs testing.

Example:

~~~java
@SpringBootTest
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private OrderRepository orderRepository;
}
~~~

In this test, Spring still creates `OrderService`, but the repository is replaced by a mock. That is useful if the goal is to test the service in-context with a controlled repository. However, the test does not confirm that the production `OrderRepository` is configured, connects to the database, or executes queries properly.

Ask yourself:

- Is the mocked bean within the risk scope?
- If that bean is misconfigured, would the test catch it?
- Is the mock replacing an out-of-scope dependency or the very component that needs verification?
- Does another test cover the real adapter or bean selection?

A slice test commonly mocks services because service logic is outside the controller's scope. A repository test should not mock the repository if queries are the target. A wiring test should not replace the bean under verification with a mock.

## 14. Choosing test scope by the question to answer

| Goal | Suitable test | What to observe |
|---|---|---|
| Verify a service computes accurately | Unit test instantiating service directly | Return values, exceptions |
| Verify a service rejects invalid input | Unit test with JUnit | Exceptions and prevented side effects |
| Verify a mock dependency receives right requests | Unit test with Mockito | Meaningful `ArgumentCaptor` or `verify` |
| Verify Spring creates beans and injects dependencies | `@SpringJUnitConfig` or small context test | Beans created and configured properly |
| Verify bean selection by profile/property | Spring context test | Actual implementation selected |
| Verify MVC mappings | `@WebMvcTest` | HTTP status, headers, body, model |
| Verify JPA mappings/queries | `@DataJpaTest` | Data in the test database |
| Verify transaction proxies | Spring integration test | Commit/rollback via transaction manager |
| Verify end-to-end application flow | `@SpringBootTest` | Results across multiple beans and real infrastructure |

If the goal is business logic, unit tests usually give the fastest and most direct evidence. If the goal is wiring, a context is required. If the goal is interaction between wiring and infrastructure, an integration test is required.

## 15. A complete example of the three test layers

Suppose a system has `DiscountService` using `DiscountPolicy` and `OrderRepository`.

### Business rule

Contract:

> VIP customers receive a 10% discount on eligible order amounts. Final total after discount cannot be negative. The order is saved with the final total.

Unit test verifying the outcome:

~~~java
@ExtendWith(MockitoExtension.class)
class DiscountServiceUnitTest {

    @Mock
    private DiscountPolicy discountPolicy;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private DiscountService discountService;

    @Test
    void appliesVipDiscountAndReturnsFinalTotal() {
        when(discountPolicy.rateFor("VIP"))
                .thenReturn(new BigDecimal("0.10"));

        when(orderRepository.save(any(Order.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        OrderResult result = discountService.checkout(
                new OrderRequest("VIP", new BigDecimal("100.00")));

        assertEquals(
                new BigDecimal("90.00"), result.finalTotal());
    }
}
~~~

This test verifies that the service applies the policy result and returns the right total given the configured dependency behavior. To verify that the real `DiscountPolicy` actually computes 10%, test the policy separately.

### DI/configuration

Context test verifying the right policy is selected:

~~~java
@SpringBootTest(properties = "discount.policy=standard")
class DiscountPolicyWiringTest {

    @Autowired
    private DiscountPolicy discountPolicy;

    @Test
    void wiresStandardDiscountPolicy() {
        assertInstanceOf(StandardDiscountPolicy.class, discountPolicy);
    }
}
~~~

This test does not check the discount rate. It only checks which bean implementation was selected.

### Integration behavior

An integration test can load the real service, policy, and repository, prepare an order in the test database, call `checkout`, and query back the persisted total. This test produces evidence that the beans collaborate and persistence works as required.

The three tests do not duplicate roles. Each test addresses a different risk.

## 16. Signs that a test is confusing DI with business logic

Review the test design if a test only contains assertions like:

- `assertNotNull(service)`.
- `assertNotNull(repository)`.
- `assertTrue(applicationContext.containsBean("someService"))`.
- `assertDoesNotThrow(() -> context.getBean(Service.class))`.
- `contextLoads()` with no business action.

These assertions are helpful in configuration checks, but they cannot replace tests with inputs, actions, and outcomes.

A behavioral test should include at least:

1. Initial state or input data.
2. A call to a public method or a real request.
3. Assertions on outcomes observable by the caller or system.
4. Assertions on prevented side effects if that is part of the contract.

Not every test needs to touch a database or use many mocks. Choose evidence proportional to the risk.

## 17. Practical workflow when writing tests for DI-managed beans

1. **Identify the risk:** are we testing wiring, business logic, or integration?
2. **Identify beans in scope:** which services, repositories, policies, controllers, or adapters must participate?
3. **Keep the components under verification real:** do not mock a bean the test needs to verify.
4. **Isolate out-of-scope parts:** use mocks or fakes for dependencies outside the risk.
5. **Choose scope:** unit test for logic only; context test for DI; integration test for proxies, databases, or real infrastructure.
6. **Trigger behavior:** call public methods or send requests across the appropriate boundary.
7. **Verify results:** check return values, exceptions, data state, or side effects.
8. **Evaluate the conclusion:** what did the test prove, and what remains outside its scope?

### Test goal template

~~~text
Risk:
[What could go wrong and its consequence]

Component to verify:
[Bean or business rule]

Dependencies that must be real:
[Beans, proxies, repositories, or adapters in scope]

Dependencies that can be replaced:
[Mocks/fakes outside scope]

Action:
[Public method or request]

Evidence:
[Return value, exception, state, HTTP response, database state]
~~~

Example:

~~~text
Risk:
Spring selects the wrong TransferPolicy for the test profile.

Component to verify:
Injected TransferPolicy bean.

Dependencies that must be real:
StandardTransferPolicy and profile configuration.

Dependencies that can be replaced:
External services unrelated to the policy.

Action:
Start context with the test profile and call policy via public API.

Evidence:
The selected bean is the expected implementation and a sample business scenario
produces the result according to the stated rule.
~~~

This template forces test authors to separate evidence of bean selection from evidence of bean behavior.

## Conclusion

Dependency Injection proves that Spring can supply and wire dependencies under the current configuration. It does not prove that services enforce the right business rules, repositories save accurate data, or transactions handle failures properly. Use context tests to verify wiring, unit tests to verify behavior through public APIs, and integration tests to verify proxies alongside real infrastructure. A trustworthy test suite collects evidence for each risk rather than relying solely on the `ApplicationContext` starting successfully.
