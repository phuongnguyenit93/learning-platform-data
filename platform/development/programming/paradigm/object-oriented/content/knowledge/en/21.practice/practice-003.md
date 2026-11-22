# Payment interfaces and polymorphism in Java OOP

## Objectives

Build a store payment feature with three options: **card**, **bank transfer**, and **e-wallet**. Each method has its own rules, while the order processor need not know the details of each type.

This exercise covers:

- **Interface:** define a shared PaymentMethod contract.
- **Runtime polymorphism:** invoke the same pay method on objects with different runtime types.
- **Encapsulation:** keep card, bank, and wallet state inside their respective classes.
- **Composition and constructor injection:** supply PaymentProcessor with a PaymentMethod from outside.
- **Testing:** verify fees, payment amounts, rejected transactions, and balance state.

This is an entirely in-memory **simulation**. It neither performs actual financial transactions nor uses real card information or bank connections.

## 1. Exercise requirements

Each transaction has a nonblank order ID and a positive whole-number amount in VND. The fee schedules are exercise assumptions only.

| Method | Success condition | Fee | Decline condition |
|---|---|---|---|
| CardPayment | Card active; amount within per-transaction limit | 2% of amount, rounded down to VND | Card blocked or limit exceeded |
| BankTransferPayment | Amount within per-transaction limit | 5.000 VND | Limit exceeded |
| EWalletPayment | Wallet balance at least equals order amount | 0 VND | Insufficient wallet funds |

A PaymentResult includes the order ID, method name, SUCCESS/DECLINED status, original amount, fee, amount paid, and message.

**Invariants to preserve:**

1. A declined transaction must never be recorded as successful; its fee and total paid are 0.
2. A wallet balance decreases only after a successful payment, by exactly the paid amount.
3. Invalid input data must be detected before any payment behavior executes.
4. PaymentProcessor must not distinguish the three payment classes with if, switch, or instanceof.

## 2. Decomposing the object model

~~~mermaid
classDiagram
    class PaymentMethod {
        <<interface>>
        +label() String
        +pay(request) PaymentResult
    }
    class CardPayment {
        -active boolean
        -limit long
        +pay(request) PaymentResult
    }
    class BankTransferPayment {
        -bankName String
        -limit long
        +pay(request) PaymentResult
    }
    class EWalletPayment {
        -balance long
        +pay(request) PaymentResult
        +balanceVnd() long
    }
    class PaymentProcessor {
        -method PaymentMethod
        +process(request) PaymentResult
    }
    PaymentMethod <|.. CardPayment
    PaymentMethod <|.. BankTransferPayment
    PaymentMethod <|.. EWalletPayment
    PaymentProcessor --> PaymentMethod
~~~

**PaymentMethod** specifies shared behavior without requiring implementations to have identical fields. PaymentProcessor coordinates calls; each implementation determines its own approval rules, fees, and state changes.

## 3. Complete Java 11 solution

Create **PaymentPolymorphismDemo.java**. The program runs with JDK 11 or later, without Spring, Maven, or external libraries.

~~~java
import java.util.List;
import java.util.Objects;

public class PaymentPolymorphismDemo {
    enum Status {
        SUCCESS, DECLINED
    }

    static final class PaymentRequest {
        final String orderId;
        final long amountVnd;

        PaymentRequest(String orderId, long amountVnd) {
            if (orderId == null || orderId.isBlank()
                    || amountVnd <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            this.orderId = orderId;
            this.amountVnd = amountVnd;
        }
    }

    static final class PaymentResult {
        final String orderId;
        final String method;
        final Status status;
        final long originalAmountVnd;
        final long feeVnd;
        final long totalPaidVnd;
        final String message;

        private PaymentResult(String orderId, String method,
                Status status, long originalAmountVnd, long feeVnd,
                long totalPaidVnd, String message) {
            this.orderId = orderId;
            this.method = method;
            this.status = status;
            this.originalAmountVnd = originalAmountVnd;
            this.feeVnd = feeVnd;
            this.totalPaidVnd = totalPaidVnd;
            this.message = message;
        }

        static PaymentResult success(
                PaymentRequest request, String method, long fee) {
            if (fee < 0) {
                throw new IllegalArgumentException("Negative fee");
            }
            long total = Math.addExact(request.amountVnd, fee);
            return new PaymentResult(
                    request.orderId, method, Status.SUCCESS,
                    request.amountVnd, fee, total, "Approved");
        }

        static PaymentResult declined(
                PaymentRequest request, String method, String reason) {
            return new PaymentResult(
                    request.orderId, method, Status.DECLINED,
                    request.amountVnd, 0L, 0L, reason);
        }

        @Override
        public String toString() {
            return orderId + " | " + method + " | " + status
                    + " | fee=" + feeVnd
                    + " | paid=" + totalPaidVnd
                    + " | " + message;
        }
    }

    // Hợp đồng chung để thay thế đa hình.
    interface PaymentMethod {
        String label();
        PaymentResult pay(PaymentRequest request);
    }

    // Trả 2% làm tròn xuống; tránh nhân trực tiếp số lớn * 2.
    private static long cardFee(long amount) {
        long base = Math.multiplyExact(amount / 100L, 2L);
        long fraction = (amount % 100L) * 2L / 100L;
        return Math.addExact(base, fraction);
    }

    static final class CardPayment implements PaymentMethod {
        private final boolean active;
        private final long limit;

        CardPayment(boolean active, long limit) {
            if (limit <= 0) {
                throw new IllegalArgumentException("Invalid card limit");
            }
            this.active = active;
            this.limit = limit;
        }

        @Override
        public String label() {
            return "CARD";
        }

        @Override
        public PaymentResult pay(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            if (!active) {
                return PaymentResult.declined(
                        request, label(), "Inactive card");
            }
            if (request.amountVnd > limit) {
                return PaymentResult.declined(
                        request, label(), "Card limit exceeded");
            }
            return PaymentResult.success(
                    request, label(), cardFee(request.amountVnd));
        }
    }

    static final class BankTransferPayment implements PaymentMethod {
        private final String bankName;
        private final long limit;

        BankTransferPayment(String bankName, long limit) {
            if (bankName == null || bankName.isBlank() || limit <= 0) {
                throw new IllegalArgumentException("Invalid bank");
            }
            this.bankName = bankName;
            this.limit = limit;
        }

        @Override
        public String label() {
            return "BANK(" + bankName + ")";
        }

        @Override
        public PaymentResult pay(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            if (request.amountVnd > limit) {
                return PaymentResult.declined(
                        request, label(), "Transfer limit exceeded");
            }
            return PaymentResult.success(request, label(), 5_000L);
        }
    }

    static final class EWalletPayment implements PaymentMethod {
        private long balance;

        EWalletPayment(long initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Negative balance");
            }
            this.balance = initialBalance;
        }

        long balanceVnd() {
            return balance;
        }

        @Override
        public String label() {
            return "E_WALLET";
        }

        @Override
        public PaymentResult pay(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            if (balance < request.amountVnd) {
                return PaymentResult.declined(
                        request, label(), "Insufficient balance");
            }
            // Chỉ thay đổi trạng thái sau khi kết quả hợp lệ.
            PaymentResult result =
                    PaymentResult.success(request, label(), 0L);
            balance -= request.amountVnd;
            return result;
        }
    }

    // Không kiểm tra kiểu cụ thể: dynamic dispatch ở method.pay.
    static final class PaymentProcessor {
        private final PaymentMethod method;

        PaymentProcessor(PaymentMethod method) {
            this.method = Objects.requireNonNull(method, "method");
        }

        PaymentResult process(PaymentRequest request) {
            Objects.requireNonNull(request, "request");
            return method.pay(request);
        }
    }

    private static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    private static void expectSuccess(PaymentResult result,
                                      long fee, long paid) {
        check(result.status == Status.SUCCESS, "Must succeed");
        check(result.feeVnd == fee, "Wrong fee");
        check(result.totalPaidVnd == paid, "Wrong total");
    }

    private static void expectDeclined(PaymentResult result) {
        check(result.status == Status.DECLINED, "Must decline");
        check(result.feeVnd == 0L, "Declined fee must be zero");
        check(result.totalPaidVnd == 0L,
                "Declined paid amount must be zero");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected invalid argument");
    }

    public static void main(String[] args) {
        PaymentRequest order =
                new PaymentRequest("ORD-101", 200_000L);

        CardPayment card = new CardPayment(true, 500_000L);
        BankTransferPayment bank =
                new BankTransferPayment("ABC", 1_000_000L);
        EWalletPayment wallet = new EWalletPayment(250_000L);

        // Một kiểu interface, nhiều implementation thực tế.
        List<PaymentMethod> methods = List.of(card, bank, wallet);
        long[] fees = {4_000L, 5_000L, 0L};
        long[] totals = {204_000L, 205_000L, 200_000L};

        for (int i = 0; i < methods.size(); i++) {
            PaymentProcessor processor =
                    new PaymentProcessor(methods.get(i));
            PaymentResult result = processor.process(order);
            expectSuccess(result, fees[i], totals[i]);
            check(result.orderId.equals("ORD-101"), "Wrong order ID");
            check(result.originalAmountVnd == 200_000L,
                    "Wrong original amount");
            System.out.println(result);
        }

        // Đã chi 200.000 từ số dư 250.000.
        check(wallet.balanceVnd() == 50_000L, "Wrong balance");

        // Yêu cầu thêm 60.000 bị từ chối, không được trừ ví.
        PaymentResult rejected = new PaymentProcessor(wallet)
                .process(new PaymentRequest("ORD-102", 60_000L));
        expectDeclined(rejected);
        check(wallet.balanceVnd() == 50_000L,
                "Rejected transaction changed wallet balance");

        // Thẻ không hoạt động và chuyển khoản vượt hạn mức.
        expectDeclined(new PaymentProcessor(
                new CardPayment(false, 500_000L)).process(order));
        expectDeclined(new PaymentProcessor(
                new BankTransferPayment("ABC", 100_000L))
                .process(order));

        // Không được tạo đơn không hợp lệ.
        expectInvalid(() -> new PaymentRequest(" ", 10_000L));
        expectInvalid(() -> new PaymentRequest("ORD-103", 0L));
        expectInvalid(() -> new PaymentRequest(null, 1L));

        System.out.println("All payment polymorphism tests: PASS");
    }
}
~~~

Compile and run:

~~~bash
javac PaymentPolymorphismDemo.java
java PaymentPolymorphismDemo
~~~

Output when all conditions are met:

~~~text
ORD-101 | CARD | SUCCESS | fee=4000 | paid=204000 | Approved
ORD-101 | BANK(ABC) | SUCCESS | fee=5000 | paid=205000 | Approved
ORD-101 | E_WALLET | SUCCESS | fee=0 | paid=200000 | Approved
All payment polymorphism tests: PASS
~~~

The tests directly throw AssertionError, so they do not depend on enabling Java assertions. In a real project, these test cases can be migrated to JUnit 5.

## 4. How polymorphism works

Consider these two snippets:

~~~java
PaymentMethod method = new CardPayment(true, 500_000L);
PaymentResult a = new PaymentProcessor(method)
        .process(new PaymentRequest("A", 100_000L));

method = new EWalletPayment(300_000L);
PaymentResult b = new PaymentProcessor(method)
        .process(new PaymentRequest("B", 100_000L));
~~~

The variable method has the **declared** type PaymentMethod, but its referenced object is a CardPayment or EWalletPayment. When PaymentProcessor invokes method.pay(request), the JVM dispatches to the overridden implementation belonging to the runtime object. This is **runtime polymorphism**.

Implementations need not be internally identical. Cards check active status and limits, transfers check limits, and wallets check and change balances. The interface requires only **a common behavioral contract**, not shared fields or formulas.

Constructor injection makes PaymentProcessor depend on the contract. Adding a new payment method does not require changing the process logic.

## 5. Architecture before and after

Before applying polymorphism, beginners often put every branch in one method:

~~~java
// Minh họa anti-pattern, không phải đoạn chạy độc lập:
if (type.equals("CARD")) {
    // Kiểm tra hạn mức, tính 2%.
} else if (type.equals("BANK")) {
    // Kiểm tra hạn mức, cộng 5.000.
} else if (type.equals("WALLET")) {
    // Kiểm tra số dư, trừ tiền.
}
~~~

If refund or transaction-history code also repeats these branches, adding another method becomes even easier to overlook. After extraction, PaymentProcessor only calls:

~~~java
PaymentResult process(PaymentRequest request) {
    return method.pay(request);
}
~~~

~~~mermaid
sequenceDiagram
    participant Caller
    participant Processor as PaymentProcessor
    participant Method as PaymentMethod
    Caller->>Processor: process(request)
    Processor->>Method: pay(request)
    Note over Method: Runtime dispatch theo lớp thực tế
    Method-->>Processor: PaymentResult
    Processor-->>Caller: PaymentResult
~~~

The system can still use a factory or registry to convert an API choice (such as a CARD code) into a concrete object. **Selecting an implementation at object-creation boundaries** differs from embedding fee and state-change branches throughout payment call sites.

## 6. Minimum and extended tests

| Scenario | Expected result |
|---|---|
| Active card, limit 500.000, order 200.000 | SUCCESS, fee 4.000, total 204.000 |
| Inactive card | DECLINED, no recorded payment |
| Card exceeds limit | DECLINED |
| Bank limit 1.000.000, 200.000 order | SUCCESS, 5.000 fee |
| Bank limit 100.000, 200.000 order | DECLINED |
| Wallet with 250.000 pays 200.000 | SUCCESS, 50.000 remaining |
| Wallet with 50.000 attempts another 60.000 payment | DECLINED, balance remains 50.000 |
| Blank order ID, amount 0 or negative | IllegalArgumentException |
| Card payment of 199 VND | Fee is 3 VND (2% rounded down) |
| Adding a fee causes long overflow | ArithmeticException is raised; no success reported |

The sample program runs the main cases; the last two are additional exercises. Math.addExact and the cardFee formula already support explicit overflow and rounding tests.

## 7. Hands-on exercises

**Part A — Implement it yourself:** Using only the requirements and diagram, implement PaymentMethod, the three implementations, PaymentProcessor, and PaymentResult. Compare behavior with the reference solution.

**Part B — Add QRPayment:** Assume a QR fee of 1% and a per-payment limit of 2.000.000 VND. Implement PaymentMethod, add it to the list, and write tests without changing PaymentProcessor code.

**Part C — Fee policies:** If one payment type uses different rates for promotions, try introducing FeePolicy as a collaborator. Explain when this responsibility should be separated from PaymentMethod.

**Part D — Protect state:** Start with a wallet balance of 100.000 VND, pay 100.000 and then attempt another 1 VND. The first succeeds, the second is declined, and the ending balance is 0.

**Part E — Validate errors:** Add test cases for a card limit equal to the amount, an empty bank name, a negative initial balance, a negative card limit, and a null PaymentRequest.

## 8. Design mistakes to avoid

- **Using instanceof in the processor:** forfeits polymorphism because the processor depends on concrete classes again.
- **Moving switch into a utility class:** merely relocates conditions without assigning responsibilities to objects.
- **Debiting a wallet before payment success:** risks incorrect state changes when a payment is declined or an exception occurs.
- **Using double for money:** avoid floating-point rounding errors. This exercise uses whole VND with long and Math.addExact; consider BigDecimal for fractional units.
- **Returning only a boolean:** cannot explain status, fees, and failure reasons when applications need those details.
- **Assuming an interface guarantees payment safety:** this design lacks database transactions, idempotency, sensitive-data security, reconciliation, and webhook processing. Real systems address these concerns separately.
- **Creating an interface for every class:** abstract only where there is a meaningful shared contract. PaymentRequest/PaymentResult are data objects and need no multiple implementations simply to demonstrate polymorphism.

## 9. Self-assessment

1. Why can one PaymentMethod variable invoke different payment algorithms?
2. Why does CardPayment have an active field while BankTransferPayment does not need it?
3. When a new method is added, which class must be created, and which can remain unchanged?
4. Why must a declined wallet payment preserve its balance?
5. Must a switch that maps an input string to PaymentMethod necessarily be removed?
6. What distinguishes an interface, class inheritance, and composition in this example?

After completing the exercise, you should be able to explain that **an interface defines a contract**, **polymorphism selects behavior based on the runtime object**, and **composition** lets PaymentProcessor use that behavior without coupling to a concrete implementation.
