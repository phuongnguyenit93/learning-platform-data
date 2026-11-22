# Using Fakes, Stubs, or Mocks via Interfaces in Java

## 1. Why Use Interfaces in Testing?

A class often needs to collaborate with an external component: a repository, a payment gateway, a notification service, a system clock, or a remote API. If the business class directly creates a concrete implementation inside a method, replacing that component during testing will be harder.

An interface creates a small contract between the consumer and the provider. The business class depends on the contract, not on a concrete implementation class. When running the application, a real implementation can be passed in; in testing, a test double suited to the test's goal can be passed in.

A **test double** is the general term for an object that replaces a real dependency in testing. Fakes, stubs, and mocks are all types of test doubles, but they are used for different purposes:

- **Stub** returns predetermined answers to control the input scenario and focus on checking the outcome of the code under test.
- **Fake** is a simple yet working implementation. A common example is a repository that stores data in memory instead of a real database.
- **Mock** focuses on recording or verifying interactions: which methods are called, with which arguments, how many times, or in what order. Mocking frameworks can automatically configure and verify those expectations.
- **Spy** is a related option: it records interactions, typically by wrapping another implementation, and can allow calls to continue running the real behavior.

Naming conventions may vary slightly across development teams and frameworks. The important point is to choose a test double based on what needs to be proven, not just on its name.

## 2. Designing a Substitution Point via an Interface

This example has an interface named **PriceCatalog**, which provides product prices by code. **CheckoutService** receives that interface through its constructor and uses it to calculate the total price. The business class does not need to know whether prices come from an in-memory map, a stub, a mock, or a real service.

The relationship can be visualized as follows:

~~~text
Test or application
        |
        v
  CheckoutService
        |
        v
   PriceCatalog
    /    |     \
   v     v      v
  Stub  Fake   Mock
~~~

This is constructor dependency injection: the dependency is passed in from the outside rather than being hardcoded inside **CheckoutService**. Because **PriceCatalog** has only a single abstract method, it is also a functional interface and can be implemented with a lambda when appropriate.

## 3. Complete Example with Java 17+

The example runs standalone, without requiring external testing libraries. The program uses the same **CheckoutService** with three different test doubles: a stub, a fake, and a mock that records calls.

Create the file **Main.java** with the following content:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class Main {
    @FunctionalInterface
    interface PriceCatalog {
        int priceInCents(String sku);
    }

    static final class CheckoutService {
        private final PriceCatalog catalog;

        CheckoutService(PriceCatalog catalog) {
            this.catalog = Objects.requireNonNull(catalog, "catalog");
        }

        int totalInCents(String sku, int quantity) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            int unitPrice = catalog.priceInCents(sku);
            if (unitPrice < 0) {
                throw new IllegalStateException("price must not be negative");
            }
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    // Stub: always returns a predetermined price.
    static final class StubPriceCatalog implements PriceCatalog {
        private final int fixedPrice;

        StubPriceCatalog(int fixedPrice) {
            if (fixedPrice < 0) {
                throw new IllegalArgumentException("price must not be negative");
            }
            this.fixedPrice = fixedPrice;
        }

        @Override
        public int priceInCents(String sku) {
            return fixedPrice;
        }
    }

    // Fake: a small, working in-memory catalog.
    static final class FakePriceCatalog implements PriceCatalog {
        private final Map<String, Integer> prices;

        FakePriceCatalog(Map<String, Integer> prices) {
            this.prices = Map.copyOf(prices);
        }

        @Override
        public int priceInCents(String sku) {
            Integer price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException("Unknown SKU: " + sku);
            }
            return price;
        }
    }

    // Mock: returns a controlled value and records interactions for verification.
    static final class MockPriceCatalog implements PriceCatalog {
        private final int fixedPrice;
        private final List<String> requestedSkus = new ArrayList<>();

        MockPriceCatalog(int fixedPrice) {
            if (fixedPrice < 0) {
                throw new IllegalArgumentException("price must not be negative");
            }
            this.fixedPrice = fixedPrice;
        }

        @Override
        public int priceInCents(String sku) {
            requestedSkus.add(sku);
            return fixedPrice;
        }

        List<String> requestedSkus() {
            return List.copyOf(requestedSkus);
        }
    }

    public static void main(String[] args) {
        CheckoutService stubService =
                new CheckoutService(new StubPriceCatalog(250));
        int stubTotal = stubService.totalInCents("BOOK", 3);
        if (stubTotal != 750) {
            throw new AssertionError("Unexpected stub total: " + stubTotal);
        }

        FakePriceCatalog fakeCatalog = new FakePriceCatalog(
                Map.of("BOOK", 250, "PEN", 75));
        CheckoutService fakeService = new CheckoutService(fakeCatalog);
        int fakeTotal = fakeService.totalInCents("BOOK", 2)
                + fakeService.totalInCents("PEN", 1);
        if (fakeTotal != 575) {
            throw new AssertionError("Unexpected fake total: " + fakeTotal);
        }

        MockPriceCatalog mockCatalog = new MockPriceCatalog(250);
        CheckoutService mockService = new CheckoutService(mockCatalog);
        int mockTotal = mockService.totalInCents("BOOK", 2);
        if (mockTotal != 500
                || !mockCatalog.requestedSkus().equals(List.of("BOOK"))) {
            throw new AssertionError("Unexpected mock interaction");
        }

        System.out.println("Stub total: " + stubTotal + " cents");
        System.out.println("Fake total: " + fakeTotal + " cents");
        System.out.println("Mock total: " + mockTotal + " cents");
        System.out.println("Mock calls: " + mockCatalog.requestedSkus());
    }
}
~~~

Compile and run in the directory containing the file:

~~~text
javac Main.java
java Main
~~~

Exact stdout:

~~~text
Stub total: 750 cents
Fake total: 575 cents
Mock total: 500 cents
Mock calls: [BOOK]
~~~

If there is a compilation error or a check condition fails, the program will terminate with an error instead of silently printing a success result.

## 4. Reading Each Test Double in the Example

### Stub: Controlling the Answer

**StubPriceCatalog** always returns the price configured at initialization. In the example, the price is set to 250 cents, so buying three units produces 750 cents. The goal is to test the calculation of **CheckoutService** without depending on external data.

Stubs are especially useful when you need to simulate a specific scenario, such as a price of 0, a nonexistent record, an empty result, or an error from a dependency. Design a stub to clearly express the scenario under test; avoid turning it into an overly complex simulation system.

### Fake: Simple but Real Behavior

**FakePriceCatalog** stores prices in a **Map**. It performs lookups by product code and reports an error when a code is not in the catalog. This is a working implementation that is simpler than the real system, because it does not require connecting to a database or a remote service.

Fakes are useful when you need to test multiple interactions with structured data without wanting to depend on infrastructure. Other examples include an in-memory repository, a simple queue, or a simulated filesystem. A fake needs to preserve the important rules that the test relies on; if the fake's behavior differs too much from the real system, tests can create a false sense of security.

### Mock: Checking Interactions

**MockPriceCatalog** both returns a fixed price and records the requested product code. The test verifies two things: the total price is 500 cents and the list of calls equals **["BOOK"]**.

The difference does not lie in whether the mock returns a price; it lies in the test actively verifying interactions. In real projects, a mock can help verify that a payment gateway is called exactly once, a notification is sent to the right recipient, or a dependency is called with the right arguments.

The hand-written mock in the example only performs simple call recording. It illustrates the idea and does not fully replace the features of mocking frameworks, such as configuring expectations, verifying call counts, call order, or simulating exceptions.

## 5. Choosing the Right Type Based on the Testing Goal

| What You Want to Test | Typically Suitable Choice | Reason |
| --- | --- | --- |
| Total calculation formula with a known price | Stub | The input result is controlled |
| Processing flow over a small, consistent dataset | Fake | Provides sufficiently realistic behavior without infrastructure |
| A dependency must be called with the right arguments or number of times | Mock | Interaction is part of the contract to be verified |
| Integration with a real database, network, or service | Integration test with the real dependency or a dedicated test environment | Test doubles do not prove that the real integration works properly |

You do not need to mock every dependency. If a test only cares about the output, a stub or fake is usually simpler and easier to read. Mocks are especially useful when interaction with a dependency is itself the behavior under test, but verifying too many internal calls can make tests brittle: an implementation change that does not affect the outcome will still cause tests to fail.

## 6. Interfaces and Dependency Injection: Design Principles

- **Define the contract according to the consumer's needs.** An interface should be small and express the required capability, rather than copying the entire API of an external system.
- **Pass dependencies through the constructor.** Replacing implementations becomes explicit, and the object can store the dependency in a **private final** field.
- **Keep test doubles outside business logic.** **CheckoutService** only calls **PriceCatalog**; it does not need an **if** statement to distinguish whether it is running with a stub, fake, mock, or real implementation.
- **Isolate parts with side effects.** Network access, system time, files, and databases are often useful boundaries to extract into interfaces when substitution makes testing clearer.
- **Do not mechanically create an interface for every class.** If a small class has no need for substitution, does not sit at an important boundary, and does not need an independent contract, adding an interface may only increase complexity.
- **Avoid shared state between tests.** Each test should create new test doubles or explicitly reset state so that test execution order does not affect results.
- **Verify meaningful behavior.** Prefer outcomes and interactions that belong to the contract; do not lock tests into unimportant implementation details.

Dependency injection does not require a framework. In the example, constructing **CheckoutService** with a **StubPriceCatalog** is already constructor injection. A large application may use a container to assemble dependencies, but the design principles remain the same.

## 7. Limitations of Test Doubles

Test doubles help verify logic quickly and in a controlled way, but they do not prove that the real dependency works properly. A fake may not simulate all transactions, concurrency locks, or database constraints; a stub may omit real-world API errors; a mock may verify calls without verifying that the remote service actually handles the request properly.

Therefore, combine the appropriate levels of testing:

1. **Unit test:** tests the logic of a unit using a stub, fake, or mock when helpful.
2. **Integration test:** verifies that important components actually work together, such as a repository with a test database.
3. **Contract test or end-to-end test:** when needed, verifies the contract between systems or a complete business flow.

Not every project needs all levels at the same depth. Choose based on risk, cost, and the defects that each level can detect.

## 8. Common Mistakes

- **Calling every test double a mock.** Distinguish the goal: returning predetermined results, simulating simple realistic behavior, or verifying interactions.
- **Mocking too deeply into internal details.** Tests easily break during refactoring even when external behavior has not changed.
- **A fake that does not match the real contract.** When necessary, maintain a contract test suite to verify both the fake and the real implementation together.
- **Using a test double and assuming integration has been tested.** A stub does not test the real network, database, configuration, or access permissions.
- **Letting test doubles leak into production code.** Business code should depend on interfaces; choosing the implementation usually belongs in the application startup layer or test configuration.
- **Sharing a stateful mock across multiple tests.** Old call history can make results depend on execution order.
- **Checking interactions that have no business meaning.** Only verify a call when making that call is part of the requirement, not merely because you can record it.

## 9. Checklist Before Choosing a Test Double

1. Is the most important part of the test the return value, behavior over data, or interaction with a dependency?
2. Can a simple stub be used to isolate the scenario?
3. Would a small fake make the test easier to understand and be close enough to the contract being used?
4. Is there really a need to verify arguments, call counts, or interaction order to justify using a mock?
5. Do the necessary integration tests cover the differences that test doubles cannot simulate?
6. Does the interface create a useful boundary, or does it merely add an unnecessary layer of abstraction?

In summary, interfaces allow business code to depend on replaceable contracts. Stubs control answers, fakes provide a simplified yet working implementation, and mocks help verify interactions. Choose the simplest type that can prove the test's requirement, and do not mistake unit tests for proof of the entire integrated system.
