# Adapter Pattern in Java: Integrating Different Interfaces

**Category:** OOP → Design Patterns  
**Topic:** Adapter and integrating different interfaces

## 1. The Problem: Two Systems Do the Same Job but Speak Different “Languages”

Your application has standardized payments through a `PaymentGateway` interface with explicit request and result objects. The business then needs to integrate a legacy payment SDK:

- The application sends amounts as `BigDecimal` in USD; the legacy SDK expects `long` in **cents**.
- The application calls `charge(PaymentRequest)`; the legacy SDK calls `execute(String merchantRef, long amountInCents)`.
- The application needs `APPROVED` or `DECLINED` results; the SDK returns string codes `"00"`, `"05"`, `"91"`.
- Rewriting all of `CheckoutService` to depend on the legacy SDK would couple business functionality to that provider.

**Adapter** inserts an intermediary class that converts the interface provided by the existing SDK (*Adaptee*) into the interface expected by the application (*Target*). The consumer (*Client*) continues using `Target`. The `Adapter` class converts calls, parameters, responses, and errors within the defined contract.

### Adapter Pattern Participants

| Role | In this example | Responsibility |
|---|---|---|
| **Client** | `CheckoutService` | Invokes payment operations through a unified interface |
| **Target** | `PaymentGateway` | Contract understood by the client: `charge(PaymentRequest)` |
| **Adaptee** | `LegacyPaymentApi` / `LegacyPaymentSdk` | Legacy API with its own signatures and data conventions |
| **Adapter** | `LegacyPaymentAdapter` | Implements `PaymentGateway` and delegates to the converted legacy API |

~~~mermaid
classDiagram
    direction LR
    class PaymentGateway {
        <<interface>>
        +charge(PaymentRequest) PaymentReceipt
    }
    class LegacyPaymentApi {
        <<interface>>
        +execute(String, long) LegacyReply
    }
    class CheckoutService {
        -PaymentGateway gateway
        +checkout(PaymentRequest) String
    }
    class LegacyPaymentAdapter {
        -LegacyPaymentApi legacy
        +charge(PaymentRequest) PaymentReceipt
    }
    class LegacyPaymentSdk {
        +execute(String, long) LegacyReply
    }
    CheckoutService --> PaymentGateway : uses
    LegacyPaymentAdapter ..|> PaymentGateway : implements
    LegacyPaymentAdapter --> LegacyPaymentApi : delegates
    LegacyPaymentSdk ..|> LegacyPaymentApi : implements
~~~

> This is an **Object Adapter**: it holds a reference to the wrapped object through *composition*. An adapter class does not have to inherit from the SDK class.

## 2. Define the Contract Before Writing the Adapter

Agree on data semantics before converting anything. In this learning example:

1. `PaymentRequest` represents only transactions in **USD**, with positive amounts exactly representable in cents within the `long` range, and a nonblank order ID. Invalid data is rejected at request construction.
2. `PaymentGateway.charge` accepts a valid request. For a definitive provider response, it returns a `PaymentReceipt` with `APPROVED` or `DECLINED` status.
3. The SDK code `"00"` means approved, `"05"` means declined, and `"91"` means the result is temporarily unknown. **These codes are simulated conventions for the example only**, not universal codes for real SDKs.
4. Missing replies, unknown codes, and infrastructure failures must surface as explicit errors. Do not turn an unknown outcome into `DECLINED` or `APPROVED`.
5. Clients never access `LegacyReply`, internal error codes, or SDK-specific methods.

In production, consult the provider's official documentation to verify monetary units, final statuses, rounding rules, timeout limits, and idempotency requirements. **An Adapter cannot manufacture guarantees absent from the external service**.

## 3. Java 17+: Complete Standalone Example

Save all the code in **`AdapterDemo.java`**. The SDK below is only a **simulated stub** for learning design; it neither transfers funds nor connects to a real service.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

// ====== API mà nghiệp vụ của ứng dụng mong đợi (Target) ======

enum PaymentStatus {
    APPROVED,
    DECLINED
}

record PaymentRequest(String orderId, BigDecimal amountUsd) {
    PaymentRequest {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountUsd == null) {
            throw new IllegalArgumentException("amountUsd is required");
        }

        // Không chấp nhận đơn vị nhỏ hơn 1 cent hoặc giá trị
        // không biểu diễn vừa trong long.
        try {
            long cents = amountUsd.movePointRight(2).longValueExact();
            if (cents <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "amount must be an exact cent value within long range", ex);
        }
    }
}

record PaymentReceipt(PaymentStatus status, String reference) {
    PaymentReceipt {
        Objects.requireNonNull(status, "status");
        if (status == PaymentStatus.APPROVED &&
                (reference == null || reference.isBlank())) {
            throw new IllegalArgumentException(
                    "approved payment needs provider reference");
        }
    }
}

interface PaymentGateway {
    /**
     * Nhận PaymentRequest hợp lệ, trả APPROVED hoặc DECLINED
     * khi phản hồi đã xác định.
     *
     * @throws GatewayUnavailableException nếu chưa xác định
     *         được kết quả từ nhà cung cấp
     * @throws ProviderProtocolException nếu phản hồi phá hợp đồng
     */
    PaymentReceipt charge(PaymentRequest request);
}

final class GatewayUnavailableException extends RuntimeException {
    GatewayUnavailableException(String message) {
        super(message);
    }
}

final class ProviderProtocolException extends RuntimeException {
    ProviderProtocolException(String message) {
        super(message);
    }
}

// ====== API của SDK cũ (Adaptee) ======

record LegacyReply(String code, String transactionId) {}

interface LegacyPaymentApi {
    // Nhận cents (long), trả mã giao thức riêng.
    LegacyReply execute(String merchantRef, long amountInCents);
}

// Stub mô phỏng SDK thực tế. "00" là thành công theo quy ước demo.
final class LegacyPaymentSdk implements LegacyPaymentApi {
    @Override
    public LegacyReply execute(String merchantRef, long amountInCents) {
        return new LegacyReply("00", "LEGACY-" + merchantRef);
    }
}

// ====== Adapter: bọc SDK cũ, cung cấp API mới ======

final class LegacyPaymentAdapter implements PaymentGateway {
    private final LegacyPaymentApi legacy;

    LegacyPaymentAdapter(LegacyPaymentApi legacy) {
        this.legacy = Objects.requireNonNull(legacy, "legacy");
    }

    @Override
    public PaymentReceipt charge(PaymentRequest request) {
        Objects.requireNonNull(request, "request");

        // Request đã kiểm tra cent chính xác ngay khi khởi tạo.
        long cents = request.amountUsd()
                            .movePointRight(2)
                            .longValueExact();

        LegacyReply reply = legacy.execute(request.orderId(), cents);

        if (reply == null || reply.code() == null) {
            throw new ProviderProtocolException(
                    "legacy provider returned an invalid reply");
        }

        return switch (reply.code()) {
            case "00" -> {
                if (reply.transactionId() == null ||
                        reply.transactionId().isBlank()) {
                    throw new ProviderProtocolException(
                            "approved reply has no transaction id");
                }
                yield new PaymentReceipt(
                        PaymentStatus.APPROVED, reply.transactionId());
            }
            case "05" -> new PaymentReceipt(
                    PaymentStatus.DECLINED, reply.transactionId());
            case "91" -> throw new GatewayUnavailableException(
                    "provider result is not confirmed; reconcile first");
            default -> throw new ProviderProtocolException(
                    "unknown provider code: " + reply.code());
        };
    }
}

// ====== Client: không biết tên SDK, mã lỗi hoặc đơn vị cents ======

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    String checkout(PaymentRequest request) {
        PaymentReceipt receipt = gateway.charge(request);

        return switch (receipt.status()) {
            case APPROVED -> "Paid: " + receipt.reference();
            case DECLINED -> "Payment declined";
        };
    }
}

public class AdapterDemo {
    public static void main(String[] args) {
        LegacyPaymentApi oldSdk = new LegacyPaymentSdk();
        PaymentGateway gateway = new LegacyPaymentAdapter(oldSdk);
        CheckoutService checkout = new CheckoutService(gateway);

        PaymentRequest order = new PaymentRequest(
                "ORDER-1001", new BigDecimal("12.34"));

        System.out.println(checkout.checkout(order));
        // Paid: LEGACY-ORDER-1001
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac AdapterDemo.java
java AdapterDemo
~~~

**Actual Data Flow in the Example:**

~~~mermaid
sequenceDiagram
    participant C as CheckoutService
    participant A as LegacyPaymentAdapter
    participant L as LegacyPaymentApi
    C->>A: charge(ORDER-1001, USD 12.34)
    Note over A: BigDecimal 12.34 → long 1234 cents
    A->>L: execute("ORDER-1001", 1234)
    L-->>A: LegacyReply("00", "LEGACY-ORDER-1001")
    Note over A: "00" → APPROVED
    A-->>C: PaymentReceipt(APPROVED, reference)
~~~

`CheckoutService` depends only on `PaymentGateway`. If the application later switches SDKs, developers can supply another `PaymentGateway` implementation and change startup/dependency-injection configuration. Checkout business logic need not understand the legacy SDK protocol.

### Why Use `BigDecimal` and `longValueExact()`?

Payments require exact amounts. With `new BigDecimal("12.34")`:

`12.34 USD × 100 = 1234 cents`

The expression `movePointRight(2).longValueExact()` does not round automatically: `12.345` is rejected because it cannot be represented as an integer number of cents. This is a **data-contract decision**; if rounding is actually required, its mode and location must be specified explicitly rather than arbitrarily calling `doubleValue()` and casting to `long`.

## 4. What Does an Adapter Actually Convert?

| Difference | Application side | Legacy SDK side | Conversion in adapter |
|---|---|---|---|
| Signature | `charge(PaymentRequest)` | `execute(String,long)` | Extracts request data and delegates |
| Monetary unit | `BigDecimal` USD | `long` cents | Multiplies by 100 with exact conversion |
| Output | `PaymentReceipt` | `LegacyReply` | Creates a domain result type |
| Outcome | `APPROVED` / `DECLINED` | `"00"` / `"05"` | Maps agreed-upon codes |
| Unknown outcome | Integration-domain error | `"91"` | Throws `GatewayUnavailableException` |
| Protocol-invalid response | Integration-domain error | `null` / unknown code | Throws `ProviderProtocolException` |
| Dependency | `PaymentGateway` | `LegacyPaymentApi` | The SDK appears only in the composition root and adapter |

Remember that **`DECLINED` is a definitive business result**; a network failure, timeout, or unknown status does not mean “the customer was declined.” Distinguishing these cases prevents incorrect notifications or reckless payment retries.

## 5. Test at the Correct Integration Boundary

To test the adapter without a real network, the example exposes `LegacyPaymentApi` as an interface replaceable with a lambda. The `LegacyPaymentAdapterTest.java` file below uses JUnit Jupiter 5 (requiring the JUnit Jupiter dependency and JUnit test-runner configuration in Maven or Gradle). Put the test in the same package as the demo; both are shown in the default package for brevity in this single-file Java example.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class LegacyPaymentAdapterTest {

    @Test
    void convertsAmountToCentsWithoutRounding() {
        AtomicLong receivedCents = new AtomicLong(-1L);

        LegacyPaymentApi fake = (ref, cents) -> {
            assertEquals("ORDER-42", ref);
            receivedCents.set(cents);
            return new LegacyReply("00", "TX-1");
        };

        PaymentGateway gateway = new LegacyPaymentAdapter(fake);
        PaymentReceipt result = gateway.charge(
                new PaymentRequest("ORDER-42", new BigDecimal("12.34")));

        assertEquals(1234L, receivedCents.get());
        assertEquals(PaymentStatus.APPROVED, result.status());
        assertEquals("TX-1", result.reference());
    }

    @Test
    void declinedIsAResultRatherThanProviderOutage() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("05", null));

        PaymentReceipt result = gateway.charge(
                new PaymentRequest("ORDER-43", new BigDecimal("2.00")));

        assertEquals(PaymentStatus.DECLINED, result.status());
    }

    @Test
    void ambiguousProviderResultMustNotBeTreatedAsDeclined() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("91", null));

        assertThrows(GatewayUnavailableException.class,
                () -> gateway.charge(new PaymentRequest(
                        "ORDER-44", new BigDecimal("2.00"))));
    }

    @Test
    void unknownCodeDoesNotBecomeSuccess() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("??", null));

        assertThrows(ProviderProtocolException.class,
                () -> gateway.charge(new PaymentRequest(
                        "ORDER-45", new BigDecimal("2.00"))));
    }

    @Test
    void rejectsFractionalCentAtRequestBoundary() {
        assertThrows(IllegalArgumentException.class,
                () -> new PaymentRequest(
                        "ORDER-46", new BigDecimal("12.345")));
    }

    @Test
    void approvedReplyMustHaveTransactionReference() {
        PaymentGateway gateway = new LegacyPaymentAdapter(
                (ref, cents) -> new LegacyReply("00", ""));

        assertThrows(ProviderProtocolException.class,
                () -> gateway.charge(new PaymentRequest(
                        "ORDER-47", new BigDecimal("1.00"))));
    }
}
~~~

These tests verify **conversion and mapping rules**, not the correctness of the external SDK. Real integrations also need contract tests against API documentation, sandbox integration tests, and infrastructure scenarios: timeouts before/after the provider receives a request, duplicate responses, late webhooks, and API version changes.

### Avoiding Duplicate Charges After Network Failures

If an `execute` call times out, the application may not yet know whether funds were charged. Do not retry automatically merely because the adapter threw an exception: another attempt may create a second transaction.

The solution must be agreed at the system-design level: use **idempotency keys** when supported, persist transaction state and prevent duplicate processing, query/reconcile with the provider before retrying, and handle webhooks idempotently. In the example, `orderId` is merely the `merchantRef`; there is **no automatic duplicate-prevention guarantee** because the stub does not implement idempotency.

## 6. Object Adapter and Class Adapter

Two common Adapter variants are:

**Object Adapter (common in Java):** the Adapter *contains* an Adaptee object and calls its methods, as in the example:

~~~java
final class LegacyPaymentAdapter implements PaymentGateway {
    private final LegacyPaymentApi legacy;
    // ... chuyển đổi rồi gọi legacy.execute(...)
}
~~~

Advantages: less dependency on class hierarchies, the ability to wrap multiple implementations of an interface, easier substitution of fakes in tests, and compatibility with an SDK using a `final class` (provided it can be wrapped directly or through an appropriate wrapper).

**Class Adapter:** an Adapter inherits from the Adaptee class while implementing Target. In Java, `extends LegacyBaseSdk implements PaymentGateway` is possible if the SDK class permits inheritance. This is hard to use with `final`, couples the adapter more tightly to superclass details, and Java does not support multiple class inheritance. Thus **composition** is generally easier to maintain.

Example Class Adapter structure (a sketch that does not need to be added to the standalone demo):

~~~java
class LegacyBaseSdk {
    String oldOperation(String value) { return "old:" + value; }
}
interface NewApi {
    String run(String value);
}
class InheritanceAdapter extends LegacyBaseSdk implements NewApi {
    @Override public String run(String value) {
        return oldOperation(value);
    }
}
~~~

Whichever form is chosen, the defining feature of Adapter is **converting the old interface into the new one expected by the client**, rather than merely “having a wrapper class.”

## 7. How Does Adapter Differ from Similar Patterns?

| Pattern | Primary purpose | Recognition scenario |
|---|---|---|
| **Adapter** | Enable incompatible interfaces to work together | Domain uses `PaymentGateway`, SDK exposes `execute(ref,cents)` |
| **Facade** | Provide a simple entry point into a complex subsystem | One method combines several calls for payments, inventory, and shipping |
| **Decorator** | Add behavior while retaining the wrapped interface | Add logging/metrics/retry policies around a `PaymentGateway` |
| **Proxy** | Represent an object and control access to it | Lazy initialization, authorization, remote access |
| **Bridge** | Separate an abstraction from its implementation so both can vary independently | Mix multiple notification types and delivery channels flexibly |

Patterns can be composed: for example, a Decorator such as `MetricsPaymentGateway` can wrap `LegacyPaymentAdapter`, with `PaymentGateway` still exposed externally. Not every wrapper should be called an Adapter if its actual purpose is timing operations or controlling access.

## 8. Integrating Multiple SDKs or API Versions

Suppose a second provider uses HTTP JSON instead of a Java SDK:

~~~text
CheckoutService
      |
      v
  PaymentGateway (hợp đồng chung)
      |                     |
      v                     v
LegacyPaymentAdapter    HttpPaymentAdapter
      |                     |
      v                     v
 LegacyPaymentApi        HTTP/JSON API
~~~

Each adapter encapsulates its own mappings while preserving the `PaymentGateway` contract. Adapter selection can be configured or injected, for example with Spring:

~~~java
// Phác họa wiring với Spring; cần có các bean tương ứng.
// @Bean
// PaymentGateway paymentGateway(LegacyPaymentApi legacyPaymentApi) {
//     return new LegacyPaymentAdapter(legacyPaymentApi);
// }
//
// @Service
// class CheckoutService {
//     CheckoutService(PaymentGateway gateway) { ... }
// }
~~~

If the system encounters two different interpretations of `DECLINED`, or one provider only supports “submit a request and await a callback,” revisit the **shared contract**. Do not pretend an asynchronous API always yields an immediate definitive result. As appropriate, separate capabilities, introduce `PENDING` as part of a revised contract and deliberately update clients, or design a specialized port for the asynchronous workflow.

An Adapter is often part of a DDD **Anti-Corruption Layer**: it keeps external terminology, models, states, and errors at the integration boundary rather than allowing them into the domain. An Anti-Corruption Layer can contain more than one adapter, however, including mapping, validation, translation, and client/repository components.

## 9. Design Mistakes to Avoid

1. **Returning `LegacyReply` directly to the domain.** Clients then still know codes `"00"` and `"05"`; the Adapter has not hidden the incompatibility.
2. **Scattering `if (provider == ...)` throughout business logic.** Each new provider bloats clients and increases inconsistent behavior. Use a clear contract with appropriate implementations.
3. **Casting money through `double` or rounding implicitly.** For example, `(long)(12.345 * 100)` silently discards fractional digits. Declare monetary rules first.
4. **Catching every exception and returning `DECLINED`.** Infrastructure failures and unknown statuses can cause incorrect reconciliation.
5. **Retrying after a timeout without checking idempotency.** Uncontrolled retries of side-effectful commands can duplicate payments.
6. **Creating an “adapter” that also handles orders, pricing, and inventory.** Protocol conversion belongs at the boundary; business rules belong in the appropriate layer.
7. **Ignoring data security.** Do not log card numbers, payment tokens, or secrets; implement TLS, authentication, and secret management as required by the real API.
8. **Assuming compatible signatures are enough.** If a second implementation returns different states, errors, or timing guarantees from the interface, it may violate legitimate client expectations.

## 10. Checklist for Applying Adapter in a Project

- [ ] The **Target** is an application-controlled contract with explicit inputs, outputs, and errors.
- [ ] The correct **Adaptee** (SDK/API to integrate) has been identified, and its official conventions reviewed.
- [ ] Units, data types, and states have explicit conversions without losing important information.
- [ ] External failures map to meaningful domain errors or states, without reporting false success.
- [ ] Clients depend on the application interface; the adapter isolates SDK details.
- [ ] Unit tests cover mappings and boundaries, and sandbox integration tests cover the external contract.
- [ ] Timeouts, reconciliation, retries, and idempotency are handled according to provider capabilities.
- [ ] Changing providers primarily affects adapters and connection configuration, without entering core business logic.

### Practice Exercise

Implement `HttpPaymentAdapter implements PaymentGateway` for a simulated API accepting JSON `{"order":"ORDER-1","amountMinor":1234}` and returning `{"state":"accepted","reference":"REMOTE-1"}`. Map `accepted → APPROVED`, `rejected → DECLINED`, and `pending →` an unresolved outcome according to **the chosen contract**. Use a fake HTTP client to test JSON mapping, parsing errors, timeouts, and missing transaction references. Verify that `CheckoutService` still does not need to change.

**Key point:** Adapter does not change how third-party systems work; it creates a **contract-based translation boundary**. Business logic speaks the application's language, while provider details stay in the integration layer.
