# Extracting Interfaces for Substitutability, Avoiding Pass-Through Layers Without a Role

In a Spring Boot application, it is very easy to create an interface for every class:

```java
public interface OrderService {
    Order findById(String id);
}
```

```java
@Service
public class OrderServiceImpl implements OrderService {

    @Override
    public Order findById(String id) {
        // ...
    }
}
```

This approach is not syntactically wrong and sometimes fits an architecture. However, if the interface merely duplicates every public method of a single implementation, the application has only one implementation, there is no need for substitution, and there is no independent boundary to protect, that abstraction may only increase the number of files and names to track.

Conversely, when a use case must support multiple payment providers, when the application must migrate from one storage system to another, or when a component needs to be replaced by a fake in tests, an interface can create a **meaningful substitutable contract**. The client then depends on what it needs, while the implementation can change without forcing the client to know internal details.

This lesson focuses on **extracting interfaces based on real substitutability needs**, identifying who needs the contract, what behaviors the contract should contain, and when an intermediate layer that merely forwards calls should be removed. The goal is to establish boundaries that make change easier while keeping the design simple enough for readers to follow the business flow.

> An interface is valuable when it expresses a contract that a client needs and allows an implementation decision to vary independently. An interface that merely copies a class's method names does not create that value by itself.

## 1. An Interface Is a Contract, Not a Mandatory Ritual for Every Class

A Java interface describes the operations a type can provide:

```java
public interface InventoryReader {
    int availableQuantity(String sku);
}
```

An implementation commits to fulfilling the contract:

```java
@Component
public class JpaInventoryReader implements InventoryReader {

    private final InventoryRepository repository;

    public JpaInventoryReader(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public int availableQuantity(String sku) {
        return repository.findBySku(sku)
                .map(InventoryEntity::getAvailableQuantity)
                .orElse(0);
    }
}
```

A client can use the contract:

```java
@Service
public class CheckoutService {

    private final InventoryReader inventory;

    public CheckoutService(InventoryReader inventory) {
        this.inventory = inventory;
    }

    public boolean canCheckout(String sku, int quantity) {
        return inventory.availableQuantity(sku) >= quantity;
    }
}
```

`CheckoutService` only needs to know how to query available quantity. It does not need to know whether the data comes from JPA, a REST API, a cache, or another source.

### 1.1. What Does an Interface Provide?

A well-designed interface can:

- Name a business capability or integration port.
- Restrict what clients are allowed to ask for.
- Allow multiple implementations to conform to a single contract.
- Separate business policy from infrastructure details.
- Create a seam for testing with fakes or stubs.
- Allow swapping implementations without modifying clients.
- Help a module publish a small, stable API.

However, an interface does not automatically:

- Make code easier to test if tests still require heavy real infrastructure.
- Make an application flexible if there is only one implementation and no reason to substitute it.
- Reduce coupling if the interface exposes every detail of the implementation.
- Make a system adhere to Dependency Inversion simply because another file exists.
- Guarantee that two implementations behave identically.

### 1.2. A Class Is Also a Valid Dependency Type

Java allows clients to depend directly on a class:

```java
@Service
public class OrderApplicationService {

    private final OrderCalculator calculator;

    public OrderApplicationService(OrderCalculator calculator) {
        this.calculator = calculator;
    }
}
```

If `OrderCalculator` is pure, stable logic with no need for substitution and no need to create a module boundary, constructor injection directly on the class can be a simpler and clearer design.

There is no universal architectural rule requiring every `@Service` to have an interface of the same name.

## 2. Start from Client Needs

Before creating an interface, ask:

1. What tasks does the client actually need to perform?
2. Which implementation decisions might change independently?
3. Are there multiple execution sources or environments requiring different behaviors?
4. Is swapping implementations a concrete requirement, or merely a vague assumption?
5. If the implementation changes, would the client have to change?
6. Can the interface be named in the business/client's language?

For example, a payment use case might need:

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
    void capture(String paymentReference);
    void refund(String paymentReference, Money amount);
}
```

The application may use one provider in local environments, another provider in production, or a fake in tests. This is a real substitutability need.

### 2.1. Design Around Capabilities the Client Uses

If a client only needs to look up inventory, it should not have to inject an interface exposing every administrative operation:

```java
public interface InventoryManager {
    int availableQuantity(String sku);
    void reserve(String sku, int quantity);
    void release(String reservationId);
    void importStock(StockImport importData);
    void correctStock(StockCorrection correction);
    void deleteWarehouse(String warehouseId);
}
```

A `CheckoutService` only needs `availableQuantity` and `reserve`. An overly broad interface forces clients to depend on many unrelated capabilities.

You can split contracts by role:

```java
public interface InventoryAvailability {
    int availableQuantity(String sku);
}
```

```java
public interface StockReservation {
    Reservation reserve(String sku, int quantity);
    void release(String reservationId);
}
```

One implementation can implement both:

```java
@Component
public class WarehouseInventory
        implements InventoryAvailability, StockReservation {
    // ...
}
```

This is an application of the Interface Segregation Principle: clients depend only on the methods they need.

### 2.2. Do Not Extract an Interface Just to Have Another File

If a class has only one method `calculate()` and every client needs that exact class, a duplicate interface may fail to create a meaningful boundary:

```java
public interface TaxCalculator {
    BigDecimal calculate(Order order);
}
```

```java
@Component
public class TaxCalculatorImpl implements TaxCalculator {
    // A single implementation, no independent contract
}
```

If there is no need for substitution, no module boundary, and no concrete testing benefit, you can use it directly:

```java
@Component
public class TaxCalculator {

    public BigDecimal calculate(Order order) {
        // ...
    }
}
```

When requirements change and multiple tax policies become necessary, you can extract an interface then. Creating abstractions once a clear reason exists usually leads to better names and scopes than pre-generating every interface from a template.

## 3. What Is a "Substitutability Need"?

Substitutability does not necessarily mean switching vendors tomorrow. It can be a current requirement or an existing independent boundary.

### 3.1. Multiple Providers or Strategies

Examples:

- Paying by card vs. e-wallet.
- Sending notifications via email, SMS, or push.
- Storing files on local disk vs. object storage.
- Calculating prices under retail vs. wholesale policies.
- Selecting routing algorithms by order type.

The implementations serve the same client need while differing in how they carry it out.

### 3.2. Differences Across Environments

An application may use:

| Environment | Implementation |
| --- | --- |
| Unit test | Fake repository or stub gateway |
| Local development | Simulated or sandbox adapter |
| Staging | Sandbox provider |
| Production | Real provider |

When implementations must be chosen by profile, property, or composition root, an interface is a useful boundary.

### 3.3. Separating Domain from Infrastructure

The domain should not depend on JPA entities, HTTP clients, or a vendor's SDK simply to express core business rules.

For example, the domain needs to store orders:

```java
public interface OrderStore {
    Optional<Order> find(OrderId id);
    void save(Order order);
}
```

JPA adapter:

```java
@Repository
public class JpaOrderStore implements OrderStore {

    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderStore(
            SpringDataOrderRepository repository,
            OrderMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> find(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }
}
```

The domain/application layer depends on `OrderStore`. The adapter depends on Spring Data/JPA and fulfills that contract.

### 3.4. Tests Need to Swap a Collaborator with Side Effects

A use case that transfers money should not call a real payment provider in unit tests. A gateway interface allows replacing it with a fake that records requests and returns deterministic results.

This is a practical testing need. However, not every class needs an interface just so Mockito can mock it; tests can also use concrete classes, fake objects, or integration tests depending on the goal.

### 3.5. Modules with Stable APIs and Changing Implementations

A module may wish to expose a small contract to other modules while keeping database schemas, SDKs, or frameworks internal to the implementation.

An interface helps when it is an actively maintained boundary. If the interface simply sits next to the class in the same package without protecting any decision that varies, its value may be low.

## 4. Which Side Should Own the Interface?

An important question is **who defines the contract**.

If `CheckoutService` needs inventory lookup capability, the contract can reside in the module/application layer using that capability:

```text
checkout/
  application/
    CheckoutService.java
    InventoryAvailability.java

inventory/
  adapter/
    JpaInventoryAvailability.java
```

`CheckoutService` depends on `InventoryAvailability`; the adapter supplies the implementation.

This applies Dependency Inversion: high-level policy defines the abstraction it needs, and low-level details implement that abstraction.

### 4.1. Consumer-Owned Interfaces

Suppose a library provides:

```java
public class VendorCustomerClient {
    public VendorCustomer fetchCustomer(String externalId) {
        // ...
    }
}
```

The application only needs:

```java
public interface CustomerDirectory {
    Optional<CustomerProfile> find(CustomerId id);
}
```

An adapter translates between the two models:

```java
@Component
public class VendorCustomerDirectory implements CustomerDirectory {

    private final VendorCustomerClient client;
    private final CustomerMapper mapper;

    public VendorCustomerDirectory(
            VendorCustomerClient client,
            CustomerMapper mapper) {
        this.client = client;
        this.mapper = mapper;
    }

    @Override
    public Optional<CustomerProfile> find(CustomerId id) {
        VendorCustomer external =
                client.fetchCustomer(id.value());

        return Optional.ofNullable(external)
                .map(mapper::toProfile);
    }
}
```

Business clients never have to know about `VendorCustomer`, the SDK, or vendor-specific exception types.

### 4.2. When Should the Providing Module Own the Interface?

The consumer does not always have to own the interface. If a module genuinely exposes a stable public API for multiple clients, the interface can belong to that module.

What matters is not the absolute file location, but that:

- The contract expresses the right responsibility.
- Dependencies between modules flow in the intended direction.
- The contract does not leak unnecessary implementation details.
- There is a clear owner responsible for evolving the API.

### 4.3. Do Not Put Every Interface into an `interfaces` Directory

A package holding dozens of generic interfaces strips away context:

```text
interfaces/
  ServiceInterface.java
  RepositoryInterface.java
  ClientInterface.java
```

Instead, name interfaces after capabilities and group them with the module that uses them:

```text
checkout/
  application/
    InventoryAvailability.java

payment/
  application/
    PaymentGateway.java
```

Package and interface names should help readers understand which decision the contract serves.

## 5. Dependency Inversion Principle and Interfaces

The Dependency Inversion Principle (DIP) is commonly stated in two parts:

1. High-level modules should not depend directly on low-level modules; both should depend on abstractions.
2. Abstractions should not depend on details; details should depend on abstractions.

### 5.1. Depending Directly on an Implementation

```java
@Service
public class CheckoutService {

    private final StripePaymentClient stripe;

    public CheckoutService(StripePaymentClient stripe) {
        this.stripe = stripe;
    }
}
```

The checkout use case knows a specific provider. Switching to another provider may require editing checkout code.

### 5.2. Depending on an Abstraction

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
```

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

```java
@Component
public class StripePaymentGateway implements PaymentGateway {
    // Provider integration
}
```

```java
@Component
public class SandboxPaymentGateway implements PaymentGateway {
    // Sandbox integration
}
```

`CheckoutService` does not know which provider is selected. Spring wiring decides the implementation.

### 5.3. Having an Interface Does Not Automatically Mean DIP Is Applied

Example:

```java
public interface StripePaymentService {
    void charge();
}
```

```java
public class StripePaymentServiceImpl
        implements StripePaymentService {
}
```

If the interface still carries vendor-specific names and concepts, the client still depends on the implementation decision. The abstraction may change the reference type without actually inverting the dependency.

A contract like `PaymentGateway` or `PaymentAuthorization` usually expresses the application's need better if that is what the client actually requires.

### 5.4. Not Every Interface Represents DIP

An interface can simply be an internal API without representing an architectural boundary. DIP is about **dependency direction and abstraction ownership**, not the count of interfaces in a project.

## 6. Interface Segregation Principle: Small Role-Based Contracts

The Interface Segregation Principle (ISP) advises that clients should not be forced to depend on methods they do not use.

### 6.1. Overly Broad Interface

```java
public interface UserManagement {
    User find(UserId id);
    void create(User user);
    void update(User user);
    void delete(UserId id);
    void exportAll();
    void resetPassword(UserId id);
    void lock(UserId id);
}
```

A service that only reads profiles ends up depending on a contract that includes deletion and administrative operations.

### 6.2. Splitting by Client Role

```java
public interface UserReader {
    Optional<UserProfile> find(UserId id);
}
```

```java
public interface UserWriter {
    void save(User user);
}
```

```java
public interface UserAdministration {
    void lock(UserId id);
    void resetPassword(UserId id);
}
```

A single implementation can implement multiple interfaces, while each client injects only the role it needs.

### 6.3. Small Interfaces Do Not Mean One Interface per Method

Over-splitting also has costs:

```java
public interface UserFinder {
    User find(UserId id);
}

public interface UserSaver {
    void save(User user);
}

public interface UserDeleter {
    void delete(UserId id);
}
```

If all clients use the same set of operations and those operations evolve together, splitting each method into a separate interface fragments the design.

Split when client groups have different permissions, substitutability needs, or rates of change. Keep operations together when they form a cohesive contract.

## 7. What Is a Pass-Through Wrapper Without a Role?

An intermediate layer is often called a pass-through wrapper when it simply forwards calls to another object without adding behavior, protecting an abstraction, or managing a distinct boundary.

Example:

```java
@Service
public class OrderService {

    private final OrderServiceImpl delegate;

    public OrderService(OrderServiceImpl delegate) {
        this.delegate = delegate;
    }

    public Order findById(String id) {
        return delegate.findById(id);
    }

    public void save(Order order) {
        delegate.save(order);
    }
}
```

If `OrderService` simply forwards every method to `OrderServiceImpl`, the outer layer adds no:

- Business rules.
- Transaction boundary.
- Authorization.
- Mapping or validation.
- Caching.
- Retry policy.
- Coordination across multiple collaborators.
- Meaningful independent contract.

It merely forces readers to step through an extra file to find the real logic.

### 7.1. Why Do Pass-Through Wrappers Incur Costs?

- Add an extra hop when reading stack traces.
- Add constructors and dependency wiring.
- Create one more place to rename methods.
- Can introduce circular call chains.
- Mislead readers into thinking an important abstraction exists when none does.
- Obscure which class actually owns the business behavior.

### 7.2. Not Every Delegate Is Pointless

An intermediate class can have a genuine role if it:

- Translates domain models to external models.
- Enforces authorization or validation.
- Selects an implementation based on policy.
- Coordinates multiple collaborators.
- Establishes a transaction boundary.
- Manages retries, timeouts, and fallbacks.
- Translates exceptions.
- Keeps a contract stable in front of a changing SDK.

Names like `Adapter`, `Facade`, `Decorator`, or `Service` do not prove a class has value by themselves. Look at what it actually does.

## 8. Example: Removing a Pass-Through Layer

### 8.1. Design with Two Duplicated Layers

```text
OrderController
      |
      v
OrderService
      |
      v
OrderServiceImpl
      |
      v
OrderRepository
```

Code:

```java
public interface OrderService {
    Order findById(String id);
}
```

```java
@Service
public class OrderServiceImpl implements OrderService {

    private final OrderRepository repository;

    public OrderServiceImpl(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Order findById(String id) {
        return repository.findById(id).orElseThrow();
    }
}
```

If another class also named `OrderService` simply delegates to an implementation, determine which layer truly owns the responsibility. There is no need to maintain two classes just to have an interface and implementation with matching names.

### 8.2. A Direct Service Class

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order findById(String id) {
        return repository.findById(id).orElseThrow();
    }
}
```

If there is no independent substitutable contract for `OrderService`, this can be a cleaner design.

### 8.3. Interfaces at the Data Boundary Can Still Make Sense

You do not need to eliminate every interface. `OrderRepository` can be a useful abstraction if it represents a persistence port needed by the application/domain, while the JPA implementation acts as an adapter.

A design might look like:

```text
OrderController
      |
      v
OrderService
      |
      v
OrderStore (port)
      ^
      |
JpaOrderStore (adapter)
      |
      v
Spring Data Repository
```

The difference: `OrderStore` expresses the persistence boundary needed by the service. It does not merely mirror `OrderService`.

## 9. Distinguishing Meaningful Interfaces from Redundant Interfaces

| Criterion | Meaningful Interface | Redundant Interface |
| --- | --- | --- |
| Name | Expresses capability/contract | Often just appends `Service`, `Impl` |
| Owner | A client/module requires the contract | Unclear who needs it |
| Methods | Only operations the client needs | Copies the entire class API |
| Implementations | Multiple reasonable implementations can exist | Single implementation, no independent seam |
| Substitution | Concrete substitution scenario | Only vague "might change later" assumption |
| Dependencies | Reduces coupling to details | Client still depends on implementation concepts |
| Testing | Provides a valuable test seam | Only adds a mock type without improving test boundaries |
| Evolution | Contract evolves with client needs | Interface and class always change together |

This is not a rigid checklist. A single-implementation interface can still be very valuable if it serves as a stable boundary between modules or between domain and infrastructure.

## 10. Full Example: PaymentGateway with Multiple Implementations

An application needs to process payments through different providers depending on the environment.

### 10.1. Domain Types

```java
package com.example.payment.domain;

import java.math.BigDecimal;

public record Money(BigDecimal amount, String currency) {
}
```

```java
package com.example.payment.domain;

public record PaymentRequest(
        String orderReference,
        Money amount
) {
}
```

```java
package com.example.payment.domain;

public record PaymentResult(
        String providerReference,
        PaymentStatus status
) {
}
```

```java
package com.example.payment.domain;

public enum PaymentStatus {
    AUTHORIZED,
    DECLINED,
    PENDING
}
```

### 10.2. Contract Needed by the Use Case

```java
package com.example.payment.application;

import com.example.payment.domain.PaymentRequest;
import com.example.payment.domain.PaymentResult;

public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
```

This contract belongs to the application's language. It contains no `StripeChargeRequest`, `VendorTransactionResponse`, or SDK-specific exceptions.

### 10.3. Use Case Depending on the Abstraction

```java
package com.example.payment.application;

import com.example.payment.domain.PaymentRequest;
import com.example.payment.domain.PaymentResult;
import org.springframework.stereotype.Service;

@Service
public class AuthorizePayment {

    private final PaymentGateway gateway;

    public AuthorizePayment(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult execute(PaymentRequest request) {
        if (request.amount().amount().signum() <= 0) {
            throw new IllegalArgumentException(
                    "Payment amount must be positive"
            );
        }

        return gateway.authorize(request);
    }
}
```

### 10.4. Provider Adapter

```java
package com.example.payment.adapter.partner;

import com.example.payment.application.PaymentGateway;
import com.example.payment.domain.PaymentRequest;
import com.example.payment.domain.PaymentResult;
import com.example.payment.domain.PaymentStatus;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("production")
public class PartnerPaymentGateway implements PaymentGateway {

    private final PartnerClient client;

    public PartnerPaymentGateway(PartnerClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        PartnerResponse response = client.authorize(
                new PartnerRequest(
                        request.orderReference(),
                        request.amount().amount(),
                        request.amount().currency()
                )
        );

        PaymentStatus status = switch (response.status()) {
            case "APPROVED" -> PaymentStatus.AUTHORIZED;
            case "PENDING" -> PaymentStatus.PENDING;
            default -> PaymentStatus.DECLINED;
        };

        return new PaymentResult(response.reference(), status);
    }
}
```

`PartnerClient`, `PartnerRequest`, and `PartnerResponse` are illustrative types from an integration SDK. The adapter translates between the application's contract and the provider's API.

### 10.5. Sandbox Adapter

```java
@Component
@Profile("local")
public class SandboxPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        return new PaymentResult(
                "sandbox-" + request.orderReference(),
                PaymentStatus.AUTHORIZED
        );
    }
}
```

### 10.6. Spring Selects the Implementation

With the `local` profile:

```bash
java -jar app.jar --spring.profiles.active=local
```

With the `production` profile:

```bash
java -jar app.jar --spring.profiles.active=production
```

The application must ensure only one matching `PaymentGateway` exists in each environment. If no profile is active or two implementations are registered simultaneously, constructor injection can fail due to a missing or ambiguous bean.

### 10.7. What Does the Interface Help With Here?

- `AuthorizePayment` does not need edits when the provider changes.
- Provider-specific types are contained inside the adapter.
- Sandbox and production implement the same contract.
- Unit tests can supply a fake gateway.
- Implementation selection is expressed at the configuration boundary.

This is a concrete substitutability need, so the interface provides real value.

## 11. Interfaces Do Not Guarantee Equivalent Behavior Across Implementations

Two classes implementing the same interface can still differ in:

- Retry rules.
- Timeouts.
- Idempotency.
- Error mapping.
- Data consistency.
- Side effects.
- Conditions for returning `null` or empty.
- Result precision.

Example:

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
```

If implementation A throws `PaymentDeclinedException` when declined while implementation B returns `null`, clients must know each implementation and the contract loses value.

### 11.1. Contracts Must Also Describe Semantics

A contract should clarify:

- Which statuses `PaymentResult` represents.
- Whether a decline is a normal result or an exception.
- Whether timeouts can occur.
- Whether a request can be safely retried.
- Whether provider references are unique.
- Where currency and amount are validated.

You do not need to document every detail in Javadoc, but critical behaviors must be agreed upon and tested.

### 11.2. Contract Tests for Multiple Implementations

You can create a shared test suite:

```java
abstract class PaymentGatewayContractTest {

    protected abstract PaymentGateway gateway();

    @Test
    void returnsAResultForAnApprovedRequest() {
        PaymentResult result = gateway().authorize(
                new PaymentRequest(
                        "order-100",
                        new Money(new BigDecimal("100.00"), "USD")
                )
        );

        assertThat(result).isNotNull();
        assertThat(result.status())
                .isIn(PaymentStatus.AUTHORIZED,
                      PaymentStatus.PENDING,
                      PaymentStatus.DECLINED);
    }
}
```

This is only a skeleton; a valuable contract test requires fixtures or a provider sandbox with deterministic outcomes. A test should not accept every status and treat that as verifying business semantics. Write concrete tests matching expected outcomes and how each adapter simulates them.

## 12. Test Seams Do Not Require Interfaces for Every Class

A common reason cited for creating an interface is "to make mocking easier." This can be valid when swapping a collaborator is an important part of testing, but it is not an absolute rule.

### 12.1. Fake via Interface

```java
class FakePaymentGateway implements PaymentGateway {

    private PaymentResult nextResult;
    private PaymentRequest lastRequest;

    void returnNext(PaymentResult result) {
        this.nextResult = result;
    }

    PaymentRequest lastRequest() {
        return lastRequest;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        lastRequest = request;
        return nextResult;
    }
}
```

This fake has clear behavior and can test the use case without calling a real provider.

### 12.2. Using Mockito

```java
@ExtendWith(MockitoExtension.class)
class AuthorizePaymentTest {

    @Mock
    PaymentGateway gateway;

    @InjectMocks
    AuthorizePayment authorizePayment;

    @Test
    void delegatesAuthorizationToGateway() {
        PaymentRequest request = new PaymentRequest(
                "order-1",
                new Money(new BigDecimal("50.00"), "USD")
        );

        PaymentResult expected = new PaymentResult(
                "pay-1",
                PaymentStatus.AUTHORIZED
        );

        when(gateway.authorize(request)).thenReturn(expected);

        PaymentResult actual = authorizePayment.execute(request);

        assertThat(actual).isEqualTo(expected);
        verify(gateway).authorize(request);
    }
}
```

### 12.3. Testing Classes Directly Is Fine Too

If an `OrderCalculator` is pure logic, tests can instantiate it directly:

```java
class OrderCalculatorTest {

    private final OrderCalculator calculator =
            new OrderCalculator();

    @Test
    void calculatesDiscount() {
        // Assert calculation result
    }
}
```

There is no need for an `OrderCalculatorInterface` just to test a pure class with no side effects.

### 12.4. Prefer Behavior Tests Over Mock Structure

A test that merely verifies method A calls method B can lock down implementation structure. When code is refactored without changing behavior, the test still fails.

Identify what the test needs to prove:

- A business outcome?
- An important side effect?
- A provider contract?
- A mandatory interaction?

Choose fakes, mocks, integration tests, or direct construction based on that question.

## 13. Spring Dependency Injection with Interfaces

Spring can inject an implementation by interface if exactly one matching bean exists.

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

### 13.1. Single Implementation

```java
@Component
public class DefaultPaymentGateway implements PaymentGateway {
}
```

Spring can inject `DefaultPaymentGateway` into a constructor requesting `PaymentGateway`.

### 13.2. Multiple Implementations

If there are:

```java
@Component
class CardGateway implements PaymentGateway {
}

@Component
class WalletGateway implements PaymentGateway {
}
```

a constructor requiring a single bean can encounter `NoUniqueBeanDefinitionException`.

Use `@Qualifier`:

```java
public CheckoutService(
        @Qualifier("cardGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Or `@Primary` if one implementation is the appropriate default choice.

### 13.3. Profiles

```java
@Component
@Profile("local")
class FakePaymentGateway implements PaymentGateway {
}
```

```java
@Component
@Profile("production")
class RealPaymentGateway implements PaymentGateway {
}
```

You must verify which profile is active in each environment. Interfaces do not choose implementations by themselves.

### 13.4. Conditional Beans

```java
@Bean
@ConditionalOnProperty(
        name = "payment.provider",
        havingValue = "partner"
)
PaymentGateway partnerGateway(PartnerClient client) {
    return new PartnerPaymentGateway(client);
}
```

If the condition does not match and no fallback bean exists, a client with a required injection will fail. This behavior must be designed and tested, not assumed to be solved by the interface.

## 14. Adapters Have a Different Role Than Pass-Through Wrappers

An adapter shields clients from an external system's contract by performing genuine translation.

### 14.1. Pass-Through

```java
public class CustomerService {

    private final VendorCustomerService vendor;

    public Customer get(String id) {
        return vendor.get(id);
    }
}
```

If the method just delegates `get()` to `get()` and returns the exact same object, this class may not establish an abstraction.

### 14.2. Adapter with Mapping

```java
public class CustomerDirectoryAdapter
        implements CustomerDirectory {

    private final VendorCustomerService vendor;
    private final CustomerMapper mapper;

    @Override
    public Optional<CustomerProfile> find(CustomerId id) {
        VendorCustomer response = vendor.get(id.value());

        return Optional.ofNullable(response)
                .map(mapper::toDomainProfile);
    }
}
```

This adapter:

- Translates the application ID into the provider ID.
- Translates the vendor model into the domain model.
- Isolates external data types.
- Can normalize errors or retries at the proper boundary.

This is an intermediate layer with a clear responsibility.

### 14.3. Adapters Do Not Need Their Own Separate Interface

If `CustomerDirectoryAdapter` already implements `CustomerDirectory`, there is no need to also create:

```java
public interface CustomerDirectoryAdapter {
    Optional<CustomerProfile> find(CustomerId id);
}
```

An interface mirroring the adapter class usually adds no new contract. Clients should depend on `CustomerDirectory`.

## 15. Decorators: Intermediate Layers That Add Behavior

A decorator wraps an implementation of the same contract to add behavior without modifying the original implementation.

Caching example:

```java
public class CachingCustomerDirectory
        implements CustomerDirectory {

    private final CustomerDirectory delegate;
    private final CustomerCache cache;

    public CachingCustomerDirectory(
            CustomerDirectory delegate,
            CustomerCache cache) {
        this.delegate = delegate;
        this.cache = cache;
    }

    @Override
    public Optional<CustomerProfile> find(CustomerId id) {
        return cache.get(id)
                .or(() -> {
                    Optional<CustomerProfile> result =
                            delegate.find(id);
                    result.ifPresent(profile -> cache.put(id, profile));
                    return result;
                });
    }
}
```

This class does not merely forward calls: it adds a caching policy. Still, consider cache invalidation, freshness, and concurrency; do not add a decorator unless required.

### 15.1. Logging Decorator

A decorator can measure timing or record metrics without altering the contract:

```java
public class ObservedPaymentGateway implements PaymentGateway {

    private final PaymentGateway delegate;
    private final MeterRegistry meterRegistry;

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            return delegate.authorize(request);
        } finally {
            sample.stop(
                    meterRegistry.timer("payment.authorize.duration")
            );
        }
    }
}
```

This example illustrates the idea; in Spring, AOP or client instrumentation may already provide metrics. Do not create a decorator just to duplicate an existing observability mechanism.

## 16. Facades and Orchestration Also Have a Role

A facade can expose a simpler API over a group of complex subsystems.

For example, checkout needs to:

- Read the shopping cart.
- Check inventory availability.
- Calculate the total amount.
- Authorize payment.
- Create the order.

A `CheckoutService` coordinates collaborators with real responsibilities:

```java
@Service
public class CheckoutService {

    private final CartReader carts;
    private final InventoryAvailability inventory;
    private final PriceCalculator pricing;
    private final PaymentGateway payments;
    private final OrderStore orders;

    public CheckoutService(
            CartReader carts,
            InventoryAvailability inventory,
            PriceCalculator pricing,
            PaymentGateway payments,
            OrderStore orders) {
        this.carts = carts;
        this.inventory = inventory;
        this.pricing = pricing;
        this.payments = payments;
        this.orders = orders;
    }

    public OrderResult checkout(CustomerId customerId) {
        Cart cart = carts.load(customerId);
        inventory.requireAvailable(cart.items());
        Money total = pricing.calculate(cart);
        PaymentResult payment =
                payments.authorize(
                        new PaymentRequest(cart.reference(), total)
                );

        return orders.create(cart, total, payment);
    }
}
```

`CheckoutService` is not a pass-through wrapper because it owns use-case orchestration. Still, there is no need to automatically create a `CheckoutService` interface if there is no corresponding client boundary or substitution requirement.

## 17. When an Interface Becomes Too Broad an Abstraction

An interface may start reasonably and gradually bloat:

```java
public interface FileStorage {
    void upload(...);
    byte[] download(...);
    void delete(...);
    void archive(...);
    void restore(...);
    void generatePublicUrl(...);
    void scanForMalware(...);
    void changeRetention(...);
    void listAllBuckets(...);
}
```

A client that only needs to upload files ends up depending on restore, retention, and bucket management capabilities.

### 17.1. Split by Client Capabilities

```java
public interface FileUploader {
    StoredFile upload(FileContent content);
}
```

```java
public interface FileReader {
    InputStream open(StoredFileId id);
}
```

```java
public interface FileRetentionManager {
    void archive(StoredFileId id);
    void restore(StoredFileId id);
}
```

### 17.2. Yet Avoid One Interface per Method

If all operations belong to one contract used together by the same clients, over-splitting complicates DI and forces clients to inject many dependencies.

Ask:

- Do the methods share the same reason to change?
- Does the same client need them?
- Do they have different permissions or lifecycles?
- Does any implementation only fulfill part of the contract?

Split by role and reason to change, not by method count.

## 18. Interfaces vs. Abstract Classes: Choose by Nature

Interfaces usually fit when defining a capability that classes outside a shared inheritance hierarchy can implement.

Abstract classes fit when sharing:

- Common state.
- Constructors with logic.
- Protected helper methods.
- Partial implementations.
- Template methods with a fixed execution sequence.

Example:

```java
public abstract class AbstractFileImporter {

    public final ImportResult importFile(Path path) {
        validate(path);
        List<Row> rows = readRows(path);
        return persist(rows);
    }

    protected abstract List<Row> readRows(Path path);

    protected abstract ImportResult persist(List<Row> rows);

    private void validate(Path path) {
        if (!Files.isReadable(path)) {
            throw new IllegalArgumentException(
                    "Input file is not readable"
            );
        }
    }
}
```

Importers share an algorithm while differing in how they read and persist. This can be a valid reason to use an abstract class.

### 18.1. Combining Interfaces and Abstract Classes

```java
public interface FileImporter {
    ImportResult importFile(Path path);
}
```

```java
public abstract class AbstractFileImporter
        implements FileImporter {
    // Template implementation
}
```

The interface is the contract for clients; the abstract class is a way to reuse implementation. You do not need both if there is only a single simple class.

### 18.2. Java Allows Only One Superclass

If a class needs to fulfill multiple independent capabilities, interfaces allow:

```java
class CloudFileAdapter
        implements FileReader, FileUploader, FileArchiver {
}
```

This does not mean stuffing every capability into one huge class. Consider cohesion and ownership.

## 19. Default Methods and Contract Evolution

Java interfaces can contain `default` methods:

```java
public interface NotificationSender {

    void send(Notification notification);

    default void sendAll(List<Notification> notifications) {
        for (Notification notification : notifications) {
            send(notification);
        }
    }
}
```

A default method can add shared behavior without forcing every implementation to rewrite it.

### 19.1. Do Not Use Default Methods to Hide Incompatible Behavior

If a new method requires semantics that older implementations cannot properly fulfill, a fake or no-op default implementation can render the contract meaningless.

Example:

```java
default void refund(String paymentReference) {
    // Do nothing
}
```

A payment gateway that does not support refunds yet silently ignores the call can cause severe business errors.

Instead:

- Extract a separate capability if not every provider supports it.
- Return a result/exception representing unsupported behavior.
- Or make refund a mandatory part of the contract and require every implementation to conform.

### 19.2. Public Interfaces Are APIs That Require Management

Changing an interface's method signatures can impact all implementations and clients. Do not treat interfaces as maintenance-free files.

If a contract is shared across multiple modules, consider backward compatibility, versioning, and rollout strategy.

## 20. Interfaces for Repositories in Spring Data

Spring Data JPA already provides repository abstractions:

```java
public interface SpringDataOrderRepository
        extends JpaRepository<OrderEntity, Long> {
}
```

You do not need an extra duplicate interface just to rename it:

```java
public interface OrderRepository
        extends SpringDataOrderRepository {
}
```

unless `OrderRepository` serves as an independent domain/application contract or adds meaningful behavior.

### 20.1. Separating Persistence Ports from Spring Data

If the application/domain should not depend on Spring Data:

```java
public interface OrderStore {
    Optional<Order> find(OrderId id);
    void save(Order order);
}
```

Adapter:

```java
@Repository
public class JpaOrderStore implements OrderStore {

    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderStore(
            SpringDataOrderRepository repository,
            OrderMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> find(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }
}
```

This abstraction has a clear purpose: the domain model and persistence model are separated, and Spring Data is not exposed in the application contract.

### 20.2. Not Every Application Needs Separate Ports for Every Repository

If a project is a simple CRUD service, the team accepts Spring Data as part of the application architecture, and there is no requirement to swap persistence boundaries, using Spring Data repositories directly can be sufficient.

Adding a port/adapter pair for every repository carries mapping and boilerplate costs. Decide based on architectural goals and genuine substitutability needs.

## 21. Interfaces and External SDKs

A vendor SDK typically comes with its own classes, exceptions, and models. Do not let those types spread throughout the business layer if you may need to change providers.

### 21.1. Direct Coupling

```java
@Service
public class ShipmentService {

    private final VendorShippingClient client;

    public ShipmentService(VendorShippingClient client) {
        this.client = client;
    }

    public VendorShipmentResponse createShipment(
            VendorShipmentRequest request) {
        return client.createShipment(request);
    }
}
```

The application service depends directly on vendor request/response types.

### 21.2. Application-Owned Contract

```java
public interface ShipmentProvider {
    ShipmentResult create(ShipmentRequest request);
}
```

Adapter translating types:

```java
@Component
public class VendorShipmentProvider implements ShipmentProvider {

    private final VendorShippingClient client;

    @Override
    public ShipmentResult create(ShipmentRequest request) {
        VendorShipmentResponse response =
                client.createShipment(
                        new VendorShipmentRequest(
                                request.destination(),
                                request.packageWeight()
                        )
                );

        return new ShipmentResult(
                response.trackingCode(),
                response.estimatedDelivery()
        );
    }
}
```

If the SDK changes tomorrow, most changes stay inside the adapter. This is a valuable boundary.

### 21.3. Do Not Wrap an SDK Just to Rename It

If the adapter merely calls:

```java
return client.createShipment(request);
```

and all types remain vendor types, it does not shield the application from the SDK. Check whether there is any reason to keep that class.

## 22. Naming Interfaces by Capability and Business Language

Good names state what the client can do:

```text
PaymentGateway
CustomerDirectory
InventoryAvailability
OrderStore
NotificationSender
ExchangeRateProvider
FileUploader
Clock
```

Unclear names:

```text
IPaymentService
PaymentServiceInterface
PaymentServiceContractV2
BasePaymentService
CommonService
GenericRepository
```

Not every name containing `Service` is wrong. What matters is whether the name expresses capability and responsibility rather than merely stating that it is an interface.

### 22.1. Avoid the `I` Suffix If Conventions Do Not Require It

Java typically uses:

```java
PaymentGateway
PartnerPaymentGateway
```

rather than:

```java
IPaymentGateway
PaymentGatewayImpl
```

The implementation name can reflect the provider or implementation approach. If there is only one implementation and no disambiguation is needed, the class can carry the capability name without an `Impl` suffix.

### 22.2. Method Names in the Client's Language

If the client needs to look up a customer profile, `find(CustomerId)` or `lookup(CustomerId)` may be more appropriate than a vendor-specific method like `fetchCustomerByExternalSystemCode()`.

The contract should reflect the language of the module that owns it.

## 23. Splitting Interfaces by Reason to Change

One way to determine contract scope is to check which methods share the same reason to change.

Example:

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
    PaymentResult capture(CaptureRequest request);
    RefundResult refund(RefundRequest request);
}
```

If one client only authorizes, another client manages refunds, and one provider does not support refunds, splitting may be warranted:

```java
public interface PaymentAuthorizer {
    PaymentResult authorize(PaymentRequest request);
}
```

```java
public interface PaymentCapturer {
    PaymentResult capture(CaptureRequest request);
}
```

```java
public interface PaymentRefunder {
    RefundResult refund(RefundRequest request);
}
```

However, if every client executes the same payment lifecycle and every provider must support all three steps, a unified `PaymentGateway` may be clearer.

**The number of interfaces should reflect independent roles and reasons to change**, not mechanically mirror method or class counts.

## 24. Interfaces and Transaction Boundaries

An interface does not create transactions by itself. `@Transactional` and the transaction manager govern transaction behavior as configured.

Example:

```java
public interface OrderStore {
    void save(Order order);
}
```

```java
@Service
public class PlaceOrder {

    private final OrderStore orders;

    public PlaceOrder(OrderStore orders) {
        this.orders = orders;
    }

    @Transactional
    public void execute(Order order) {
        orders.save(order);
    }
}
```

`PlaceOrder` is the application service owning the transaction boundary. `OrderStore` is the persistence contract.

There is no need for a `TransactionalOrderService` class that merely forwards calls to `PlaceOrder` if it adds no policy or boundary.

### 24.1. Avoid Letting Adapters Decide the Transaction for an Entire Use Case

If a use case needs to write multiple aggregates/repositories in the same transaction, placing the transaction boundary where the use case is orchestrated is usually clearer than scattering `@Transactional` across every adapter.

Ultimately, however, transaction boundaries depend on architecture, framework, and consistency requirements. Interfaces help define dependency points; they do not dictate transaction semantics.

## 25. Interfaces and Spring AOP Proxies

Spring AOP can use JDK dynamic proxies or class-based proxies depending on configuration and context.

### 25.1. JDK Proxies

JDK dynamic proxies are interface-based. Clients injecting by interface can receive the appropriate proxy:

```java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

If a bean is exposed via a JDK proxy, injecting the concrete implementation class can cause type mismatches.

### 25.2. CGLIB/Class-Based Proxies

Class-based proxies are created via subclassing where supported, making them assignable to concrete classes. However, `final` classes or methods have limitations with subclass proxies.

### 25.3. Interfaces Are Not Just for Avoiding Proxy Errors

Interfaces should be designed around business contracts or boundaries. Injecting by interface generally aligns well with JDK proxies, but you should not invent meaningless interfaces solely to avoid a cast error.

## 26. Configuring Implementations in Spring

### 26.1. A Single Default Implementation

```java
@Component
public class JpaOrderStore implements OrderStore {
}
```

Client:

```java
public OrderService(OrderStore orderStore) {
    this.orderStore = orderStore;
}
```

### 26.2. Selecting by Qualifier

```java
@Component("primaryOrderStore")
public class JpaOrderStore implements OrderStore {
}
```

```java
@Component("archiveOrderStore")
public class ArchiveOrderStore implements OrderStore {
}
```

Client:

```java
public OrderQueryService(
        @Qualifier("archiveOrderStore") OrderStore store) {
    this.store = store;
}
```

### 26.3. Selecting by Profile

```java
@Component
@Profile("test")
public class InMemoryOrderStore implements OrderStore {
}
```

```java
@Component
@Profile("production")
public class JpaOrderStore implements OrderStore {
}
```

### 26.4. Selecting via Configuration

For complex selection logic, define beans in a configuration class:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "payment.provider",
            havingValue = "sandbox"
    )
    PaymentGateway sandboxGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Ensure only one matching implementation is registered or that selection is unambiguous when multiple beans exist.

## 27. When to Start with a Class and Extract an Interface Later

A practical choice is not to create abstractions before knowing which boundary needs protection.

### 27.1. Starting Simple

```java
@Service
public class DiscountCalculator {

    public Money calculate(Cart cart) {
        // Discount rules
    }
}
```

At this point:

- There is one discount policy.
- There is no external provider.
- The logic is pure and easy to test directly.
- No client needs to swap implementations.

A direct class can be sufficient.

### 27.2. When Extension Requirements Arrive

Later there are:

- Per-tenant policies.
- Loyalty program policies.
- Per-market policies.

You can extract:

```java
public interface DiscountPolicy {
    Money calculate(Cart cart);
}
```

Implementations:

```java
@Component
public class RetailDiscountPolicy implements DiscountPolicy {
}
```

```java
@Component
public class LoyaltyDiscountPolicy implements DiscountPolicy {
}
```

Now the interface is designed around behaviors and substitution points that are clearly understood.

### 27.3. Not Every Change Requires an Interface

If you are only adding a small `if` branch inside a calculator and have no need for independent strategy selection, a strategy interface can be overkill.

Evaluate the real rate of change and complexity before adding another abstraction.

## 28. Decision Questions Before Extracting an Interface

Use these questions in design reviews:

### Question 1 — Is there a specific client needing the abstraction?

If no client uses the interface besides its own implementation, re-examine why it exists.

### Question 2 — Is there an implementation decision that needs isolation?

For example, a vendor, storage engine, transport, algorithm, or policy that can vary independently.

### Question 3 — Does the contract belong to the client's language?

An interface named `StripeClientFacade` may still couple the business layer to Stripe.

### Question 4 — Do the methods share the same role?

If clients only use part of a large interface, consider splitting according to ISP.

### Question 5 — Can implementations adhere to the same semantics?

If two implementations return values with different meanings or have differing side effects, the contract needs clarification.

### Question 6 — Does the intermediate layer add behavior?

If it merely forwards every method, consider removing it.

### Question 7 — Is the cost of the abstraction worthwhile?

Interfaces, adapters, mappers, configuration, and contract tests all have costs. They can be worthwhile at critical boundaries, but do not need to be applied to every class.

## 29. Anti-patterns to Recognize

### 29.1. Template Interfaces for Every Service

```text
CustomerService
CustomerServiceImpl
OrderService
OrderServiceImpl
ProductService
ProductServiceImpl
```

If the interfaces merely mirror the implementations, remove the unnecessary layer and keep the service classes directly.

### 29.2. Overly Generic Interface Names

```java
public interface BaseService<T> {
    T process(T value);
}
```

A generic abstraction without concrete semantics can make it difficult for clients to understand actual behavior.

Generic interfaces are useful when a genuine shared contract exists, not for grouping methods that happen to share a signature.

### 29.3. Adapters That Do Not Translate Anything

```java
public Order find(String id) {
    return delegate.find(id);
}
```

If it adds neither behavior nor a boundary, this class may be a pass-through.

### 29.4. Interfaces Exposing Framework Types

```java
public interface OrderService {
    ResponseEntity<OrderEntity> process(
            HttpServletRequest request
    );
}
```

The application/domain contract becomes tied to Spring MVC, Servlet, and persistence entities. Clients cannot use it independently.

Isolate HTTP concerns in the controller and keep business contracts using appropriate data types.

### 29.5. Grouping Methods into an Interface Just Because "Every Implementation Has Them"

Two classes both having a `save()` method does not mean they implement the same contract. One saves files while the other saves orders; putting both under a shared `SaveService` strips meaning from the abstraction.

### 29.6. Adding an Interface While Still Exposing the Implementation Type

```java
private final StripePaymentGateway gateway;
```

If the client still injects the concrete class, the new interface provides no benefit to that client.

### 29.7. Creating an Interface and Still Checking the Implementation with `instanceof`

```java
if (gateway instanceof StripePaymentGateway) {
    // ...
}
```

The client still knows provider details. If behavior must vary, bring that capability into the contract or use an appropriate strategy instead of checking concrete classes.

### 29.8. Interfaces Existing Solely to Mock Everything

Mocking every class couples tests to internal structure and creates brittle interaction tests. Use interfaces where they serve as meaningful seams, not as an end in themselves.

## 30. Safely Refactoring Away a Pass-Through Wrapper

Suppose currently:

```text
Controller
   |
   v
OrderFacade
   |
   v
OrderService
   |
   v
Repository
```

`OrderFacade` simply calls `OrderService` with the same arguments and returns the same result.

### Step 1 — Confirm There Is No Hidden Behavior

Check for:

- Transaction annotations.
- Security annotations.
- Caching.
- Validation.
- Meaningful metrics/logging.
- Mapping.
- Retry/timeout.
- Event publication.
- Contracts used by other modules.

A class that looks like a pass-through may still carry behavior via annotations or proxies.

### Step 2 — Identify the Owner of the Use Case

If `OrderService` is where the business work happens, the controller can inject the service directly.

### Step 3 — Update Clients

```java
@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }
}
```

### Step 4 — Remove the Wrapper Once No Clients Remain

Only after confirming no other beans, modules, or APIs depend on it.

### Step 5 — Keep Real Boundaries

Do not delete `OrderStore` or `PaymentGateway` if they still protect a replaceable infrastructure decision.

### Step 6 — Test Critical Behavior

Run tests for the relevant controller/service contracts. Do not refactor every interface wholesale just because one wrapper was found to be redundant.

## 31. Module Boundaries and Package Design

A simple organization:

```text
com.example.shop
├── checkout
│   ├── application
│   │   ├── CheckoutService.java
│   │   └── InventoryAvailability.java
│   └── web
│       └── CheckoutController.java
├── inventory
│   └── adapter
│       └── JpaInventoryAvailability.java
└── payment
    ├── application
    │   └── PaymentGateway.java
    └── adapter
        ├── PartnerPaymentGateway.java
        └── SandboxPaymentGateway.java
```

In this example, `checkout.application` defines the `InventoryAvailability` requirement; the inventory adapter fulfills the contract. `payment.application` defines `PaymentGateway`; provider adapters implement the contract.

### 31.1. Not Every Project Must Use `port` and `adapter` Packages

You can organize as:

```text
checkout/
  port/
  service/
```

or:

```text
checkout/
  application/
  infrastructure/
```

What matters is that dependency direction is visible and package names help readers understand boundaries.

### 31.2. Avoid Package Cycles

If:

```text
application -> adapter
adapter -> application
```

and `application` imports vendor/JPA classes directly, the boundary has leaked.

In ports-and-adapters, adapters depend on application contracts; the application does not need to import adapter implementations.

### 31.3. Interfaces Do Not Replace Module Architecture

An interface in the same package does not automatically create a module boundary. If you want to enforce dependency direction, use module structures, build modules, or appropriate architecture tests.

## 32. Designing Contracts for Easy Implementation Replacement

A well-substitutable contract cares about:

### 32.1. Stable Data Types

Prefer domain/application types:

```java
PaymentRequest
PaymentResult
Money
PaymentReference
```

Avoid exposing:

```java
StripeRequest
JpaOrderEntity
HttpServletRequest
ResponseEntity
```

when clients have no reason to depend on those types.

### 32.2. Consistent Exception Semantics

An adapter can translate vendor exceptions into application exceptions:

```java
public class PaymentUnavailableException
        extends RuntimeException {

    public PaymentUnavailableException(String message) {
        super(message);
    }
}
```

Adapter:

```java
try {
    return client.authorize(request);
} catch (PartnerTimeoutException ex) {
    throw new PaymentUnavailableException(
            "Payment provider is unavailable"
    );
}
```

Do not include tokens, raw requests, or credentials in exception messages.

### 32.3. Timeout and Retry Semantics

If one implementation retries 5 times while another does not retry, clients will experience different latencies and side effects.

Retry decisions should live in one place with clear ownership and be reflected in the contract/operation policy.

### 32.4. Idempotency

A payment authorization may be retried due to a timeout. The contract must specify how idempotency keys or references prevent duplicate charges.

An interface specifying method signatures alone is not enough to guarantee idempotency. Behavior must be documented and tested.

### 32.5. Null and Optional

Avoid letting implementations arbitrarily return `null` or empty with different meanings.

Choose an explicit contract:

```java
Optional<CustomerProfile> find(CustomerId id);
```

or:

```java
CustomerProfile get(CustomerId id);
```

and clearly define what happens when not found.

## 33. Evaluating a Design Example

Consider this code:

```java
public interface EmailService {
    void send(String to, String subject, String body);
}
```

```java
@Service
public class EmailServiceImpl implements EmailService {

    private final SmtpClient smtpClient;

    public EmailServiceImpl(SmtpClient smtpClient) {
        this.smtpClient = smtpClient;
    }

    @Override
    public void send(String to, String subject, String body) {
        smtpClient.send(to, subject, body);
    }
}
```

Should the interface be kept?

**Keep** if:

- The application has SMTP, a provider API, and a fake sender.
- Multiple modules need a notification-sending contract.
- You want to isolate vendor/transport from the application.
- A test seam is needed for a side effect.

**Consider removing** if:

- There is only a single email-sending class.
- The interface and implementation always change together.
- There is no module boundary to protect.
- The interface defines no semantics beyond forwarding method names.
- There is no realistic plan or need for another implementation.

A better option for many applications is turning the contract into a capability:

```java
public interface NotificationSender {
    void send(Notification notification);
}
```

This name expresses a broader need than SMTP. However, only do this if the application truly treats email as one form of notification and the contract shares common semantics.

## 34. Practice Exercises

### Exercise 1 — Classify Abstractions

For each pair `X` and `XImpl`, determine:

- Is there a concrete client using the interface?
- Is an alternative implementation required?
- Does the interface add semantics beyond method signatures?
- Should the interface be kept or replaced by using the class directly?

Write down the reasoning for each decision.

### Exercise 2 — Design PaymentGateway

A payment application supports production and sandbox providers.

Design:

- `PaymentRequest`.
- `PaymentResult`.
- `PaymentGateway`.
- Two adapters.
- Spring configuration selecting by profile.

Explain why the application service should not depend on the provider SDK.

### Exercise 3 — Split an Interface Using ISP

A `UserManagement` interface has eight methods for reading, writing, deleting, and administering accounts.

Create smaller contracts based on client roles. Avoid creating a separate interface for every method if those methods share the same clients and reasons to change.

### Exercise 4 — Identify a Pass-Through Wrapper

Given an `OrderFacade` class that merely forwards every method to `OrderService`.

Check for annotations, transactions, security, mapping, or metrics that might provide hidden behavior. If none exist, propose removing the wrapper.

### Exercise 5 — A Genuine Adapter

Create `CustomerDirectory` and an adapter for a simulated SDK returning `VendorCustomer`.

Map to `CustomerProfile`, translate vendor exceptions into application exceptions, and avoid exposing vendor types to clients.

### Exercise 6 — Fake Implementation

Write `FakePaymentGateway` for unit tests of `AuthorizePayment`.

Have the fake record requests and return deterministic results. Write tests verifying use case behavior without calling a real provider.

### Exercise 7 — Contract Tests

Write a suite of contract tests running against both the sandbox adapter and fake adapter to verify shared semantics:

- Approved authorization result.
- Declined result.
- Timeout/unavailable.
- Idempotency behavior if required by the contract.

Do not allow every result to pass without asserting the expected outcome.

### Exercise 8 — Interface or Abstract Class?

There are three importers: CSV, JSON, and XML. They share validation, error handling, and persistence workflows, while differing in how they read files.

Propose a contract interface, abstract base class, or combination. Explain the responsibility of each abstraction.

### Exercise 9 — Interface for Repositories

A CRUD project uses only Spring Data JPA. Present two options:

1. Inject Spring Data repositories directly.
2. Create domain `OrderStore` and a JPA adapter.

Discuss trade-offs regarding coupling, mapping, testing, and persistence substitutability.

### Exercise 10 — Conditional Implementations

Create two implementations of the same interface selected via `@ConditionalOnProperty`.

Test missing property, invalid value, and both beans being registered simultaneously.

### Exercise 11 — Remove Redundant Interfaces

Refactor a `TaxCalculator` and `TaxCalculatorImpl` pair that has only one implementation and no independent client boundary.

Preserve behavior, point clients to the class directly, and delete the redundant abstraction if no other consumers exist.

### Exercise 12 — Valuable Decorators

Create `CachingCustomerDirectory` wrapping `CustomerDirectory`.

Define the added behavior, invalidation strategy, and tests for cache hit/miss. Explain how this decorator differs from a pass-through wrapper.

### Exercise 13 — Contract Semantics

Two `FileStorage` implementations differ: one returns `null` when not found, while the other throws an exception.

Redesign the contract so behavior is consistent and write shared tests.

### Exercise 14 — Dependency Direction

Draw the dependency graph of an application containing `CheckoutService`, `PaymentGateway`, and `PartnerPaymentAdapter`.

Ensure the application layer does not import the SDK or adapter implementation. Explain the dependency direction under DIP.

### Exercise 15 — Decide Based on Change Requirements

A `ExchangeRateCalculator` class currently has only one algorithm. Later the product might need to fetch exchange rates from multiple sources.

Decide whether to create an interface immediately. If yes, specify the client and contract. If not yet, explain the right time to extract the abstraction.

### Exercise 16 — Design Review

Review a module containing:

```text
OrderController
OrderFacade
OrderFacadeImpl
OrderService
OrderServiceImpl
OrderManager
OrderManagerImpl
OrderRepository
OrderRepositoryImpl
```

Do not delete every interface blindly. Identify which classes hold behavior, which interfaces protect boundaries, which adapters perform real translation, and which layers merely forward calls.

## 35. Key Takeaways

Extract an interface when **a client needs a stable contract** and an implementation decision must vary independently: multiple providers, multiple strategies, persistence/network boundaries, module APIs, or a meaningful test seam. Name contracts after the capabilities clients need, keep method sets focused, and define consistent semantics across implementations.

Interfaces are not mandatory for every service. If a simple class has one implementation, no boundary to protect, and no concrete substitutability need, using the class directly is usually clearer. Do not create `XService`/`XServiceImpl` out of habit when the interface merely mirrors every method.

An intermediate layer that only forwards calls to a delegate without adding behavior, mapping, policy, lifecycle, or an independent abstraction is usually a pass-through wrapper and can be removed. Conversely, adapters, decorators, facades, or application services with genuine orchestration responsibilities retain real value even though they invoke other collaborators.

**Good design is not measured by interface count.** It is measured by clients depending on exactly what they need, details being changeable at appropriate boundaries, and every class having an easily explainable role.
