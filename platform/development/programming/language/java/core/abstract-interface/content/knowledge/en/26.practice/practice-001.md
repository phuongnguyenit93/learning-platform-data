# Building a Payment Contract with Multiple Implementations

A checkout system may allow payment by cash, card, or e-wallet. Each payment method has its own process, but the rest of the application still needs a uniform way to request a payment and receive a result. In Java, we can use an interface as a **payment contract**, then write multiple classes that implement that contract.

This practice exercise builds a runnable Java 17+ example. The payment classes only simulate results to illustrate the design; they do not connect to banks, e-wallets, or perform real transactions.

## 1. Define the Contract Before Writing the Classes

First, identify what every payment method must provide:

- Have a name that the UI or logs can display.
- Accept a valid payment request.
- Return a result with a uniform structure, including the order ID, amount, status, and message.
- Represent business outcomes such as approved, declined, or pending.
- Have a consistent way to report technical errors when the payment process cannot be completed.

A contract includes both method signatures and their meaning. Having the same names and parameter types is not enough: every implementing class must also follow the rules that callers rely on.

In this example, we use three data types:

- `PaymentRequest`: input data, requiring a non-empty order ID and an amount greater than 0.
- `PaymentResult`: uniform result for every payment method.
- `PaymentMethod`: interface specifying the name and payment operation.

## 2. Create the PaymentMethod Interface

~~~java
import java.util.Objects;

enum PaymentStatus {
    APPROVED,
    DECLINED,
    PENDING
}

record PaymentRequest(String orderId, long amountVnd) {
    PaymentRequest {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

record PaymentResult(
        String orderId,
        String method,
        long amountVnd,
        PaymentStatus status,
        String message) {
    PaymentResult {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(method, "method");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(message, "message");
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

final class PaymentException extends Exception {
    PaymentException(String message) {
        super(message);
    }

    PaymentException(String message, Throwable cause) {
        super(message, cause);
    }
}

interface PaymentMethod {
    String name();

    PaymentResult pay(PaymentRequest request) throws PaymentException;
}
~~~

This is the data and contract declaration. `PaymentStatus` distinguishes business outcomes; `PaymentException` is for technical errors that the method cannot handle locally. A declined transaction is a normal business outcome, so it can be represented with `DECLINED` instead of treating all such cases as program errors.

The `PaymentMethod` contract sets the following rules:

1. The caller provides a valid `PaymentRequest` that is not `null`.
2. `pay` returns a `PaymentResult` that is not `null`, associated with the exact requested order ID and amount.
3. `APPROVED`, `DECLINED`, and `PENDING` are business statuses with distinct meanings; `PENDING` must not be treated as a successful payment.
4. Technical errors can be reported via `PaymentException`; all implementations should maintain a consistent error policy.
5. `name()` returns a non-empty name that can be used for display or logging.

These semantic rules are just as important as the Java signatures. They make it unnecessary for a class using `PaymentMethod` to know how each implementation works internally.

## 3. Create Multiple Implementations

Each class below fulfills the same contract but provides its own name and message. In the example, all results are simulated.

~~~java
import java.util.Objects;

final class CashPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Cash";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(
            request.orderId(),
            name(),
            request.amountVnd(),
            PaymentStatus.APPROVED,
            "Cash payment simulated"
        );
    }
}

final class CardPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(
            request.orderId(),
            name(),
            request.amountVnd(),
            PaymentStatus.APPROVED,
            "Card payment simulated"
        );
    }
}

final class EWalletPayment implements PaymentMethod {
    @Override
    public String name() {
        return "E-wallet";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(
            request.orderId(),
            name(),
            request.amountVnd(),
            PaymentStatus.APPROVED,
            "E-wallet payment simulated"
        );
    }
}
~~~

All three classes use `implements PaymentMethod` and provide the required methods. Calling code can work with the `PaymentMethod` type without depending on concrete class names.

This simulated example does not check card limits, wallet balances, or bank confirmations. In a real system, each implementation will call a provider or handle its own process, while adhering to the same input, output, and error contract.

## 4. Make the Checkout Service Depend on the Interface

The checkout class does not need to know whether cash, card, or an e-wallet is being used. It only needs a `PaymentMethod`.

~~~java
import java.util.Objects;

final class CheckoutService {
    private final PaymentMethod paymentMethod;

    CheckoutService(PaymentMethod paymentMethod) {
        this.paymentMethod =
            Objects.requireNonNull(paymentMethod, "paymentMethod");
    }

    PaymentResult checkout(PaymentRequest request)
            throws PaymentException {
        Objects.requireNonNull(request, "request");
        return paymentMethod.pay(request);
    }
}
~~~

Passing the implementation through the constructor is called **dependency injection**. `CheckoutService` does not create `new CardPayment()` internally, so the caller can choose the appropriate payment method when instantiating the service.

This design also applies the principle of depending on an abstraction: checkout relies on a stable contract, while payment details live in separate classes. When bank transfer needs to be added, we can create `BankTransferPayment implements PaymentMethod` without modifying the checkout logic, as long as the new class adheres to the contract.

## 5. Complete Runnable Program

Save all of the above declarations together with the `main` snippet below into a file named **PaymentContractDemo.java**. To avoid duplicate declarations, when combining them into a complete file, keep the imports once at the top of the file and place all supporting types together with the public class in the same file.

~~~java
import java.util.List;
import java.util.Objects;

enum PaymentStatus {
    APPROVED,
    DECLINED,
    PENDING
}

record PaymentRequest(String orderId, long amountVnd) {
    PaymentRequest {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

record PaymentResult(
        String orderId,
        String method,
        long amountVnd,
        PaymentStatus status,
        String message) {
    PaymentResult {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(method, "method");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(message, "message");
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

final class PaymentException extends Exception {
    PaymentException(String message) {
        super(message);
    }

    PaymentException(String message, Throwable cause) {
        super(message, cause);
    }
}

interface PaymentMethod {
    String name();

    PaymentResult pay(PaymentRequest request) throws PaymentException;
}

final class CashPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Cash";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(request.orderId(), name(),
            request.amountVnd(), PaymentStatus.APPROVED,
            "Cash payment simulated");
    }
}

final class CardPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(request.orderId(), name(),
            request.amountVnd(), PaymentStatus.APPROVED,
            "Card payment simulated");
    }
}

final class EWalletPayment implements PaymentMethod {
    @Override
    public String name() {
        return "E-wallet";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(request.orderId(), name(),
            request.amountVnd(), PaymentStatus.APPROVED,
            "E-wallet payment simulated");
    }
}

final class CheckoutService {
    private final PaymentMethod paymentMethod;

    CheckoutService(PaymentMethod paymentMethod) {
        this.paymentMethod =
            Objects.requireNonNull(paymentMethod, "paymentMethod");
    }

    PaymentResult checkout(PaymentRequest request)
            throws PaymentException {
        Objects.requireNonNull(request, "request");
        return paymentMethod.pay(request);
    }
}

public class PaymentContractDemo {
    public static void main(String[] args) throws PaymentException {
        List<PaymentMethod> methods = List.of(
            new CashPayment(),
            new CardPayment(),
            new EWalletPayment()
        );

        for (int i = 0; i < methods.size(); i++) {
            PaymentMethod method = methods.get(i);
            PaymentRequest request =
                new PaymentRequest("DEMO-" + (i + 1), 150_000L);
            CheckoutService checkout = new CheckoutService(method);
            PaymentResult result = checkout.checkout(request);

            System.out.printf(
                "%s | %s | %d | %s | %s%n",
                result.orderId(),
                result.method(),
                result.amountVnd(),
                result.status(),
                result.message()
            );
        }
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac PaymentContractDemo.java
java PaymentContractDemo
~~~

Output:

~~~text
DEMO-1 | Cash | 150000 | APPROVED | Cash payment simulated
DEMO-2 | Card | 150000 | APPROVED | Card payment simulated
DEMO-3 | E-wallet | 150000 | APPROVED | E-wallet payment simulated
~~~

Three separate demo orders are created to compare the three implementations. This is only a simulation; a real-world application must not try multiple methods sequentially on the same order in a way that could cause multiple charges.

**Note on assembling the example:** Sections 2–4 illustrate individual parts to explain the design; Section 5 is the complete standalone file. Only compile a version of `PaymentContractDemo.java` in which each type is declared exactly once.

## 6. Why Is a Contract Better Than Scattered if/else Branches?

An initial implementation might check the payment type in multiple places:

~~~java
if (methodType.equals("CASH")) {
    // Handle cash
} else if (methodType.equals("CARD")) {
    // Handle card
} else if (methodType.equals("WALLET")) {
    // Handle wallet
}
~~~

When a new method is added, these branches may have to be updated in many locations. If each branch has different result or error rules, maintenance becomes harder.

With `PaymentMethod`, the payment-calling logic only needs to call `paymentMethod.pay(request)`. Choosing the implementation is the responsibility of application configuration, a factory, or an orchestration layer. Do not remove all business conditionals: validation conditions, risk limits, and permission to use the method may still be necessary. The goal is to centralize each method's specific behavior within its corresponding implementation.

## 7. How to Verify That an Implementation Complies with the Contract

When writing a new class such as `BankTransferPayment`, check the following:

- The method name is non-empty and meaningful.
- Valid input is handled according to the published rules.
- The result is not `null` and contains the exact requested order ID and amount.
- `APPROVED`, `DECLINED`, and `PENDING` are used with their proper meanings; do not report success without confirmation.
- Technical errors follow the defined exception policy.
- Do not alter the shared contract with unexpected behavior, such as returning a different amount without explicitly documented fee rules.
- Calling code does not need to cast to a concrete class to use the promised behavior.

A useful test is to run the same contract test suite against every implementation. You can use JUnit to test cases for valid input, invalid input, declined outcomes, and provider failures. When testing errors, distinguish between caller input errors and technical errors arising during processing.

## 8. Extending to Real-World Payments

The demo example keeps the result simple to focus on the interface. A real-world payment integration typically needs the following additional concepts:

- **Provider transaction ID:** for reconciliation and inquiry support.
- **Idempotency key:** so that retrying a request after a timeout does not create duplicate transactions. A plain order ID alone is only sufficient when both the provider and your design guarantee uniqueness for each payment.
- **Pending status:** the provider may have received the request but does not yet have a final result. In that case, you need to query or receive a webhook; you should not convert `PENDING` to `APPROVED` on your own.
- **Timeouts and network errors:** a timeout does not prove that a transaction failed; the system needs to verify the status before deciding to retry.
- **Security:** do not log sensitive card data, protect authentication credentials, and comply with the provider's security requirements.
- **Fees and currency:** if each method calculates fees differently, the contract must clearly define the requested amount, fee, total charged amount, and currency.

When these requirements arise, extend `PaymentRequest` and `PaymentResult` deliberately, then update the contract and all implementations. Do not let each class interpret a data field with a different meaning.

## 9. Common Design Mistakes

- **Putting per-method logic inside CheckoutService:** makes the service depend on details and forces modifications whenever a payment method is added. Let implementations carry out their specific behavior through the interface.
- **Creating an interface with only names and no clear contract:** method signatures must be accompanied by the semantics of inputs, outputs, and errors.
- **Allowing implementations to return inconsistent results:** for example, one class returns `null`, while another returns a result missing the order ID. Callers will have to write many defensive branches and can no longer trust the contract.
- **Using exceptions for every declined case:** a payment decline can be a normal business outcome; distinguish it from technical errors.
- **Treating PENDING as success:** an undetermined result does not mean the money has been collected.
- **Using the same order to test all real payment methods:** can lead to multiple charges. Use separate test orders or a sandbox environment.
- **Assuming an interface guarantees correctness on its own:** the compiler checks signatures, whereas business rules still need to be expressed through documentation, tests, and implementation.

The core takeaway of this practice exercise is to define a stable contract for the payment operation, implement the contract with multiple independent classes, and have the checkout service work through the interface type. When adding a new method, we can add an implementation while keeping the common calling pattern and the guarantees that the entire system relies on.
