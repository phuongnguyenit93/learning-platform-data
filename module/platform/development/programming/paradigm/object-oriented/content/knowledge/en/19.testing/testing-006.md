# Fakes, Stubs, Mocks, and Collaborators in OOP Testing (Java)

## 1. Context: Why Replace Collaborating Objects?

An OOP object rarely works alone. For example, **CheckoutService** processes orders by collaborating with:
- **Inventory**: checking and decrementing stock.
- **PaymentGateway**: requesting payment.
- **ReceiptSender**: sending receipts to customers.

These three components are **collaborators** of CheckoutService. In production, they may access a database, payment processor, or email service. If tests of CheckoutService's business logic call those services directly, results may depend on networks, data, transaction fees, and environment configuration.

A **test double** replaces a collaborator during testing. Supply it to the **SUT — System Under Test** through a constructor or method to control scenarios and observe behavior.

~~~mermaid
flowchart LR
    T["Bài kiểm thử"] --> S["CheckoutService (SUT)"]
    S --> I["Inventory interface"]
    S --> P["PaymentGateway interface"]
    S --> R["ReceiptSender interface"]
    I -. "trong test" .-> F["FakeInventory"]
    P -. "trong test" .-> ST["StubPaymentGateway"]
    R -. "trong test" .-> M["MockReceiptSender"]
~~~

The key distinction: **collaborator** describes a dependency's design role; **fake/stub/mock** describes the purpose of its test replacement. A collaborator may be real in integration tests, fake in unit tests, or mocked to verify interactions.

## 2. Distinguishing Fakes, Stubs, Mocks, Spies, and Dummies

| Type | Characteristic | When to Use | Example |
|---|---|---|---|
| **Dummy** | Passed only to satisfy a parameter; the test never uses it | Required but irrelevant argument | Empty Logger object in a test path that does not log |
| **Stub** | Returns predetermined values/results for calls | Control indirect inputs to the SUT | PaymentGateway always returns **true** or **false** |
| **Fake** | Simplified but working implementation, often using in-memory storage | Verify state without real infrastructure | RAM-based Map inventory supporting reads and stock decrements |
| **Mock** | Records and/or verifies how the SUT invoked a collaborator | Assert requested external effects | Verify ReceiptSender was called exactly **once**, with the right recipient and amount |
| **Spy** | Observes calls to a real or wrapped object, potentially preserving real behavior | Observe interactions while retaining the original implementation | Spy wraps an in-memory repository and counts calls |

**Classify by purpose, not class names or frameworks.** An object created through Mockito.mock(...) can supply configured values (**stubbing**) and be checked through verify(...) (**mock-style verification**). A fake can also record call history and act as a spy. In classical terminology, **stubs control state/outputs**, while **mocks assert expected interactions**.

Two common ways to assert outcomes:
- **State verification:** after checkout succeeds, inventory falls from 3 to 1.
- **Interaction verification:** a receipt is requested exactly once with the correct orderId, email, and total amount.

Not every test needs mocks. Verifying results or observable state is often less coupled to implementation than checking every internal call.

## 3. Complete Runnable Java Example Without Test Libraries

The example uses Java 11 or newer in a single file, **CheckoutDemo.java**. Interfaces define collaborator contracts, while CheckoutService depends only on those interfaces. Three test doubles illustrate separate goals: an in-memory inventory fake, a payment-result stub, and a mock recording receipt requests.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class CheckoutDemo {
    // Hợp đồng của các collaborator
    interface Inventory {
        int available(String sku);
        void decrease(String sku, int quantity);
    }

    interface PaymentGateway {
        boolean charge(String orderId, long amountVnd);
    }

    interface ReceiptSender {
        void send(String email, String orderId, long amountVnd);
    }

    enum Result {
        SUCCESS, OUT_OF_STOCK, PAYMENT_DECLINED
    }

    // SUT: code nghiệp vụ, không biết test double đang được dùng
    static final class CheckoutService {
        private final Inventory inventory;
        private final PaymentGateway payments;
        private final ReceiptSender receipts;

        CheckoutService(Inventory inventory,
                        PaymentGateway payments,
                        ReceiptSender receipts) {
            this.inventory = Objects.requireNonNull(inventory);
            this.payments = Objects.requireNonNull(payments);
            this.receipts = Objects.requireNonNull(receipts);
        }

        Result checkout(String orderId, String sku, int quantity,
                        long unitPriceVnd, String email) {
            if (orderId == null || orderId.isBlank()
                    || sku == null || sku.isBlank()
                    || email == null || email.isBlank()
                    || quantity <= 0 || unitPriceVnd <= 0) {
                throw new IllegalArgumentException("Invalid checkout data");
            }

            if (inventory.available(sku) < quantity) {
                return Result.OUT_OF_STOCK;
            }

            long total = Math.multiplyExact(unitPriceVnd, (long) quantity);
            if (!payments.charge(orderId, total)) {
                return Result.PAYMENT_DECLINED;
            }

            inventory.decrease(sku, quantity);
            receipts.send(email, orderId, total);
            return Result.SUCCESS;
        }
    }

    // FAKE: có trạng thái và hành vi đọc/trừ tồn kho thực tế trong RAM
    static final class FakeInventory implements Inventory {
        private final Map<String, Integer> stock = new HashMap<>();

        void put(String sku, int quantity) {
            if (quantity < 0) {
                throw new IllegalArgumentException("Negative stock");
            }
            stock.put(sku, quantity);
        }

        @Override
        public int available(String sku) {
            return stock.getOrDefault(sku, 0);
        }

        @Override
        public void decrease(String sku, int quantity) {
            if (quantity <= 0 || available(sku) < quantity) {
                throw new IllegalStateException("Insufficient stock");
            }
            stock.put(sku, available(sku) - quantity);
        }
    }

    // STUB: điều khiển trước kết quả của cổng thanh toán
    static final class StubPaymentGateway implements PaymentGateway {
        private final boolean approved;

        StubPaymentGateway(boolean approved) {
            this.approved = approved;
        }

        @Override
        public boolean charge(String orderId, long amountVnd) {
            return approved;
        }
    }

    // MOCK thủ công: ghi nhận tương tác và cung cấp phương thức verify
    static final class MockReceiptSender implements ReceiptSender {
        private static final class Call {
            final String email;
            final String orderId;
            final long amountVnd;

            Call(String email, String orderId, long amountVnd) {
                this.email = email;
                this.orderId = orderId;
                this.amountVnd = amountVnd;
            }
        }

        private final List<Call> calls = new ArrayList<>();

        @Override
        public void send(String email, String orderId, long amountVnd) {
            calls.add(new Call(email, orderId, amountVnd));
        }

        void verifySentExactlyOnce(String email, String orderId,
                                   long amountVnd) {
            check(calls.size() == 1,
                    "Expected one receipt, got " + calls.size());

            Call actual = calls.get(0);
            check(Objects.equals(actual.email, email),
                    "Wrong receipt email");
            check(Objects.equals(actual.orderId, orderId),
                    "Wrong receipt orderId");
            check(actual.amountVnd == amountVnd,
                    "Wrong receipt amount");
        }

        void verifyNoCalls() {
            check(calls.isEmpty(), "No receipt should be sent");
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void successfulCheckout() {
        FakeInventory inventory = new FakeInventory();
        inventory.put("BOOK", 3);
        StubPaymentGateway payments = new StubPaymentGateway(true);
        MockReceiptSender receipts = new MockReceiptSender();

        CheckoutService service =
                new CheckoutService(inventory, payments, receipts);
        Result actual = service.checkout(
                "ORD-01", "BOOK", 2, 250_000L, "buyer@example.test");

        check(actual == Result.SUCCESS, "Checkout should succeed");
        check(inventory.available("BOOK") == 1,
                "Inventory should decrease from 3 to 1"); // state
        receipts.verifySentExactlyOnce(
                "buyer@example.test", "ORD-01", 500_000L); // interaction
    }

    private static void declinedPayment() {
        FakeInventory inventory = new FakeInventory();
        inventory.put("BOOK", 3);
        StubPaymentGateway payments = new StubPaymentGateway(false);
        MockReceiptSender receipts = new MockReceiptSender();

        CheckoutService service =
                new CheckoutService(inventory, payments, receipts);
        Result actual = service.checkout(
                "ORD-02", "BOOK", 2, 250_000L, "buyer@example.test");

        check(actual == Result.PAYMENT_DECLINED,
                "Payment should be declined");
        check(inventory.available("BOOK") == 3,
                "Declined payment must not reduce inventory");
        receipts.verifyNoCalls();
    }

    private static void insufficientStock() {
        FakeInventory inventory = new FakeInventory();
        inventory.put("BOOK", 1);
        StubPaymentGateway payments = new StubPaymentGateway(true);
        MockReceiptSender receipts = new MockReceiptSender();

        CheckoutService service =
                new CheckoutService(inventory, payments, receipts);
        Result actual = service.checkout(
                "ORD-03", "BOOK", 2, 250_000L, "buyer@example.test");

        check(actual == Result.OUT_OF_STOCK,
                "Insufficient stock should block checkout");
        check(inventory.available("BOOK") == 1,
                "Stock must remain unchanged");
        receipts.verifyNoCalls();
    }

    public static void main(String[] args) {
        successfulCheckout();
        declinedPayment();
        insufficientStock();
        System.out.println("3 scenarios PASS");
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac CheckoutDemo.java
java CheckoutDemo
~~~

Output when all three scenarios pass:

~~~text
3 scenarios PASS
~~~

Making one condition incorrect—for example, sending email before payment approval—causes the **declinedPayment** test to throw AssertionError. No real email, transaction, or database is invoked.

### What Is Being Verified

| Scenario | Payment Stub | Fake State After Call | Receipt Mock | Result |
|---|---|---|---|---|
| 3 items available, buy 2 | Approved | 1 remains | Exactly 1 call, 500.000 VND | SUCCESS |
| 3 items available, buy 2 | Declined | Still 3 | Not invoked | PAYMENT_DECLINED |
| Only 1 available, buy 2 | No payment decision needed | Still 1 | Not invoked | OUT_OF_STOCK |

In the out-of-stock scenario, checkout returns before requesting payment; the current test checks only inventory state and email. If the business requires **proof that the gateway is never called**, use a call-counting test double or Mockito.verifyNoInteractions(...), and assert it separately.

## 4. The Same Approach with JUnit 5 and Mockito

When a project already uses **JUnit Jupiter** and **Mockito**, you need not implement MockReceiptSender manually. The next example assumes CheckoutDemo from the previous section is in the same package and that the project declares JUnit Jupiter and Mockito test dependencies.

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class CheckoutServiceTest {
    @Test
    void successfulCheckoutReducesStockAndSendsReceipt() {
        CheckoutDemo.Inventory inventory =
                mock(CheckoutDemo.Inventory.class);
        CheckoutDemo.PaymentGateway gateway =
                mock(CheckoutDemo.PaymentGateway.class);
        CheckoutDemo.ReceiptSender sender =
                mock(CheckoutDemo.ReceiptSender.class);

        // STUBBING: thiết lập kết quả collaborator trả về
        when(inventory.available("BOOK")).thenReturn(3);
        when(gateway.charge("ORD-01", 500_000L)).thenReturn(true);

        var service = new CheckoutDemo.CheckoutService(
                inventory, gateway, sender);

        var result = service.checkout(
                "ORD-01", "BOOK", 2, 250_000L, "buyer@example.test");

        // Kiểm tra giá trị trả về của SUT
        assertEquals(CheckoutDemo.Result.SUCCESS, result);

        // MOCK-STYLE VERIFICATION: xác minh hiệu ứng cộng tác
        verify(inventory).decrease("BOOK", 2);
        verify(gateway).charge("ORD-01", 500_000L);
        verify(sender, times(1)).send(
                "buyer@example.test", "ORD-01", 500_000L);
        verifyNoMoreInteractions(sender);
    }

    @Test
    void outOfStockDoesNotChargeOrSendReceipt() {
        CheckoutDemo.Inventory inventory =
                mock(CheckoutDemo.Inventory.class);
        CheckoutDemo.PaymentGateway gateway =
                mock(CheckoutDemo.PaymentGateway.class);
        CheckoutDemo.ReceiptSender sender =
                mock(CheckoutDemo.ReceiptSender.class);

        when(inventory.available("BOOK")).thenReturn(1);

        var service = new CheckoutDemo.CheckoutService(
                inventory, gateway, sender);

        var result = service.checkout(
                "ORD-03", "BOOK", 2, 250_000L, "buyer@example.test");

        assertEquals(CheckoutDemo.Result.OUT_OF_STOCK, result);
        verify(inventory, never()).decrease(anyString(), anyInt());
        verifyNoInteractions(gateway, sender);
    }
}
~~~

Note: **verify(inventory).decrease(...) does not prove stock quantities actually changed**, because a default Mockito mock of Inventory stores no state. To verify remaining stock, use FakeInventory or an integration test with a real repository. This is the key distinction between **interactions** and **observable results**.

Common Mockito operations:
- **when(...).thenReturn(...)**: configures stub output.
- **verify(mock).method(...)**: asserts a matching invocation; defaults to exactly 1 call.
- **times(n)**, **never()**, **verifyNoInteractions(...)**: verify counts and absent calls.
- **ArgumentCaptor**: captures arguments for content assertions when needed.
- **spy(realObject)**: observes an object with real behavior; consider side effects and do not assume spies are always safe.

## 5. Designing Collaborators for Testability

### Depend on Contracts and Inject Dependencies Externally

~~~java
// Khó cô lập: tự tạo phụ thuộc trong hàm nghiệp vụ
// PaymentGateway gateway = new RealPaymentGateway(...);

// Dễ kiểm thử: nhận đối tượng thực thi interface từ constructor
CheckoutDemo.CheckoutService service =
        new CheckoutDemo.CheckoutService(inventory, gateway, sender);
~~~

This combines **dependency injection** with **programming to an interface**. The goal is not an interface for every class, but clear boundaries where behavior must be replaceable or controlled: data, time, networks, message queues, and external services.

### What Should Tests Verify?

1. **Business rules:** returned outcomes, inventory, amounts, and data validity.
2. **Business-significant interactions:** after successful payment, request the correct receipt; after failure, do not send it.
3. **Failure paths:** out of stock, payment declined, invalid input, and external failures.
4. **Component contracts:** does the fake honor assumptions of the real repository? Are method signatures and error cases consistent?

Do not verify every getter call, internal step ordering, or private structure merely because Mockito allows it. If behavior-preserving refactoring breaks many unit tests unnecessarily, those tests likely depend too closely on implementation details.

## 6. Common Mistakes and Fixes

| Mistake | Consequence | Better Approach |
|---|---|---|
| Mocking every object, even pure value objects | Long, unreadable tests brittle under refactoring | Use real instances for simple DTOs/value objects |
| Stubbing only default results and omitting failures | No coverage for declines, timeouts, or out-of-stock cases | Write explicit tests for important failure branches |
| Verifying repository calls and assuming persistence is correct | Confuses interactions with state | Use a stateful fake or integration tests |
| Fake ignores real storage constraints | Unit tests pass but production fails | Contract/integration tests for unique keys, transactions, and concurrency |
| Mocking internal details such as helper call counts | Tests tightly coupled to implementation | Verify outputs and externally visible effects |
| Spying on real side-effectful services | May unintentionally charge payments, send mail, or write to DB | Spy only on safe objects without unexpected side effects |
| Using unit-test doubles instead of all integration tests | Misses configuration, network, schema, or protocol failures | Add integration tests for adapters and important workflows |

**Intentional limitation of the example:** CheckoutService illustrates sequential logic. Real systems must handle consistency across payment, inventory, and receipts (transactions, idempotency, outbox/sagas, retries), and inventory contention under concurrent requests. The in-memory FakeInventory does not automatically simulate these properties. Test doubles isolate SUT responsibilities but do not replace integration/end-to-end testing.

## 7. Practice Exercises

- Add a **quantity = 0** scenario: expect IllegalArgumentException and no receipt; consider how to establish that no payment-gateway call occurred.
- Create **SpyPaymentGateway** around a StubPaymentGateway, count charge calls, and record orderId/amountVnd. Verify **0 charge calls** in the OUT_OF_STOCK case.
- Deliberately replace **inventory.decrease(sku, quantity)** with a subtraction of 1, then verify that the successful-case test detects the incorrect state.
- Add an integration test for a real Inventory implementation (if the project uses a database) and compare its contract with FakeInventory.

**Remember:** A Fake answers “how does state change?”; a Stub answers “what does the collaborator return?”; a Mock answers “how was the collaborator invoked?”. Choose a test double based on what must actually be established, keep the SUT dependent on clear contracts, and use integration tests for what replacements do not simulate.
