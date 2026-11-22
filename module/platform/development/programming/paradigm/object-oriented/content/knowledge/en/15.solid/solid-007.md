# Distinguishing Dependency Inversion (DIP) from Dependency Injection (DI)

> **Topic:** OOP → SOLID. These concepts often appear together in Java/Spring but answer **two different questions**: *What should source code depend on?* (DIP) and *How are dependency objects supplied?* (DI).

## 1. Defining the Concepts Precisely

The **Dependency Inversion Principle (DIP)** is the **D** in SOLID. Robert C. Martin describes two main ideas:

1. **High-level modules** (business rules/policies) should not directly depend on **low-level modules** (databases, email, HTTP clients, payment gateways). Both should depend on **abstractions**.
2. **Abstractions should not depend on implementation details; implementation details should depend on abstractions**.

**Dependency Injection (DI)** is a technique for supplying dependencies to an object externally, commonly through a **constructor**, **setter**, or container-managed mechanism. The object need not create dependencies using `new` inside its business logic.

For example, a `CheckoutService` must charge an order. DIP suggests that the service should know the `PaymentGateway` business contract rather than a concrete `BankSdkClient`. DI is the act of passing a `PaymentGateway` implementation into the `CheckoutService` constructor during application assembly.

| Aspect | DIP: Dependency Inversion Principle | DI: Dependency Injection |
|---|---|---|
| Nature | Principle of **architecture and source-code dependency direction** | Technique for **object creation and assembly** |
| Main question | "Who may depend on whom?" | "Where does the dependency come from?" |
| Direct goal | Keep business logic independent of infrastructure details for easier substitution and maintenance | Stop consuming classes from instantiating their own dependencies |
| Common tools | Interfaces/abstract classes, module boundaries, ports/adapters | Constructor injection, setter injection, factories, DI containers |
| Is Spring required? | No | No; `new CheckoutService(gateway)` is also DI |
| What does it guarantee on its own? | Architectural guidance; package/module dependencies must also be checked | A dependency comes from outside; **DIP is not automatically satisfied** |

**DIP is not the same as DI**. DI conveniently supports a DIP-oriented design, but an application using DI may still depend directly on concrete implementations.

## 2. The Underlying Problem: Business Logic Knows Too Much Infrastructure

The following snippet hardwires the payment gateway choice into the use case:

~~~java
// Minh họa thiết kế bị phụ thuộc vào lớp cụ thể
final class TightlyCoupledCheckoutService {
    private final DemoBankAdapter bank = new DemoBankAdapter();

    String checkout(String orderId, long amountVnd) {
        // Trong ví dụ rút gọn, bỏ qua bước kiểm tra đầu vào.
        return bank.charge(orderId, amountVnd);
    }
}
~~~

Suppose `DemoBankAdapter` wraps a real bank SDK. Switching providers, testing without real API calls, or using different adapters across environments can force changes to `TightlyCoupledCheckoutService`. Business code is influenced by the technical choice of "which adapter to use."

Replacing `new` with a constructor **that accepts `DemoBankAdapter` itself** achieves DI only:

~~~java
final class CheckoutWithDiButWithoutDip {
    private final DemoBankAdapter bank;

    CheckoutWithDiButWithoutDip(DemoBankAdapter bank) {
        this.bank = bank; // Được truyền từ bên ngoài: có DI.
    }

    String checkout(String orderId, long amountVnd) {
        return bank.charge(orderId, amountVnd);
    }
}
~~~

Despite constructor injection, the declared type remains `DemoBankAdapter`. The business module still depends on a concrete infrastructure class, so DIP's objective has not been achieved.

## 3. Correct Design: Depend on a Business-Defined Contract

Define the abstraction around the use case's need: "charge a VND amount for an order ID and receive a transaction ID." A concrete adapter then implements that contract.

~~~mermaid
flowchart TB
    subgraph Business["Nghiệp vụ / application"]
        S["CheckoutService (high-level policy)"]
        P["PaymentGateway (port/interface)"]
        S -->|"tham chiếu kiểu"| P
    end

    subgraph Infrastructure["Hạ tầng"]
        A["DemoBankAdapter (low-level detail)"]
    end

    A -->|"implements"| P

    subgraph Bootstrap["Lắp ghép khi khởi động"]
        C["Main / Spring configuration"]
    end

    C -.->|"tạo và truyền dependency"| S
    C -.->|"tạo instance"| A
~~~

**Solid arrows** indicate source/type dependencies: `CheckoutService → PaymentGateway ← DemoBankAdapter`. **Dashed arrows** indicate object assembly, where both interfaces and implementations may be known. At runtime, calls still flow from `CheckoutService` to the banking implementation through the interface: inverting source dependencies **does not mean** reversing runtime call direction.

### 3.1. Standalone Java 17 Example (Without Spring)

Create `DipDiDemo.java`:

~~~java
import java.util.Objects;

/**
 * Port do use case định nghĩa.
 *
 * Hợp đồng:
 * - orderId khác null và không rỗng;
 * - amountVnd > 0;
 * - trả về mã giao dịch khác null, không rỗng nếu thu thành công;
 * - lỗi thanh toán được báo bằng exception phù hợp chính sách ứng dụng.
 */
interface PaymentGateway {
    String charge(String orderId, long amountVnd);
}

/** Kết quả của use case. */
record Receipt(String orderId, long amountVnd, String transactionId) {}

/**
 * Chính sách nghiệp vụ: chỉ biết port; không phụ thuộc SDK ngân hàng.
 */
final class CheckoutService {
    private final PaymentGateway paymentGateway;

    // Constructor injection: dependency là bắt buộc.
    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = Objects.requireNonNull(
                paymentGateway, "paymentGateway");
    }

    Receipt checkout(String orderId, long amountVnd) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }

        String transactionId = paymentGateway.charge(orderId, amountVnd);
        if (transactionId == null || transactionId.isBlank()) {
            throw new IllegalStateException("Gateway returned invalid transaction ID");
        }

        return new Receipt(orderId, amountVnd, transactionId);
    }
}

/**
 * Adapter DEMO để mô phỏng ngân hàng; không chuyển tiền thật.
 * Khi tích hợp thực, lớp hạ tầng này sẽ bọc SDK/API của nhà cung cấp.
 */
final class DemoBankAdapter implements PaymentGateway {
    @Override
    public String charge(String orderId, long amountVnd) {
        System.out.printf(
                "[DEMO] Thu %d VND cho đơn %s%n", amountVnd, orderId);
        return "TX-DEMO-" + orderId;
    }
}

public class DipDiDemo {
    public static void main(String[] args) {
        // Composition root: chỉ tại đây chọn implementation cụ thể.
        PaymentGateway gateway = new DemoBankAdapter();

        // DI thủ công, không cần Spring.
        CheckoutService checkout = new CheckoutService(gateway);

        Receipt receipt = checkout.checkout("ORD-001", 150_000L);
        System.out.println(receipt);
    }
}
~~~

Run:

~~~bash
javac DipDiDemo.java
java DipDiDemo
~~~

Illustrative output:

~~~text
[DEMO] Thu 150000 VND cho đơn ORD-001
Receipt[orderId=ORD-001, amountVnd=150000, transactionId=TX-DEMO-ORD-001]
~~~

Here, the constructor receiving `PaymentGateway` is **DI**. Having `CheckoutService` refer only to `PaymentGateway` while `DemoBankAdapter implements PaymentGateway` expresses **DIP**. `DipDiDemo.main` is the **composition root**, selecting an adapter and supplying it to the use case.

The example uses `long` for whole VND amounts to focus on dependencies. For multiple currencies, fractions, exchange rates, or rounding, design an appropriate money value object (`BigDecimal`/minor units + currency) rather than using `double` for monetary amounts.

### 3.2. Replace Implementations Without Editing the Use Case

For example, a development environment may require a fake adapter to avoid real transactions:

~~~java
final class LocalFakePaymentGateway implements PaymentGateway {
    @Override
    public String charge(String orderId, long amountVnd) {
        return "LOCAL-" + orderId;
    }
}

// Ở composition root:
PaymentGateway gateway = new LocalFakePaymentGateway();
CheckoutService checkout = new CheckoutService(gateway);
~~~

Now `CheckoutService` contains no `if (gateway instanceof ...)` and need not know whether the current adapter is a bank, sandbox, or fake. Every implementation must honor the `PaymentGateway` contract (for example, not returning an empty transaction ID on success). DIP creates the substitution point; safe substitution requires a clear interface contract.

**Important boundary:** If `PaymentGateway` returns `BankSdkPaymentResponse` or requires callers to pass `BankSdkRequest`, the abstraction leaks banking details. Even if the service names only an interface, the business module must still know SDK types. Prefer business-owned types (`Receipt`, `PaymentId`, `PaymentRequest`, etc.) and perform conversions in the adapter.

## 4. DI with Spring: The Framework Assembles Objects, DIP Remains a Design Choice

With Spring, dependencies can be configured as beans. This example uses **the Java classes from section 3.1** in the same package with the `spring-context` dependency:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CheckoutConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new DemoBankAdapter();
    }

    @Bean
    CheckoutService checkoutService(PaymentGateway gateway) {
        // Spring cấp đúng bean PaymentGateway qua method parameter.
        return new CheckoutService(gateway);
    }
}
~~~

Spring creates `DemoBankAdapter`, injects that bean into `CheckoutService`, and manages its lifecycle. `@Autowired` is unnecessary here because a `@Bean` method parameter is used; when a `@Service` has **one constructor**, Spring typically selects it for injection automatically.

When integrating a real bank, the `PaymentGateway` bean can be replaced with another adapter (and its dependencies configured), provided exactly one bean matches or `@Qualifier`/`@Primary` selects among implementations. Declaring multiple beans of the same type without resolution rules can trigger an ambiguity error during Spring startup.

**Avoid confusion:** `@Autowired`, `@Inject`, `@Component`, and `@Bean` do not automatically turn an SDK-dependent design into DIP. The following example uses DI but remains tightly coupled:

~~~java
// Đây là DI, nhưng service vẫn phụ thuộc class hạ tầng cụ thể:
final class CoupledCheckout {
    private final DemoBankAdapter bank;

    CoupledCheckout(DemoBankAdapter bank) {
        this.bank = bank;
    }
}
~~~

In a multimodule project, place `PaymentGateway` in the appropriate application/business module. Infrastructure depends inward on the interface's module, while business code does not import infrastructure. Bootstrap or Spring configuration may reference both to connect them. Check **module diagrams and build dependencies**, not just constructor signatures.

## 5. Easier Testing Through Abstractions and DI

Testing `CheckoutService` logic does not require starting Spring, connecting to a network or database, or invoking a payment gateway. Create a fake recording call counts and run tests with JUnit Jupiter (JUnit 5).

File `CheckoutServiceTest.java` (in the same package as the demo):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void validOrderUsesInjectedGateway() {
        AtomicInteger calls = new AtomicInteger();

        PaymentGateway fake = (orderId, amountVnd) -> {
            assertEquals("ORD-123", orderId);
            assertEquals(150_000L, amountVnd);
            calls.incrementAndGet();
            return "FAKE-TX-123";
        };

        CheckoutService service = new CheckoutService(fake);
        Receipt receipt = service.checkout("ORD-123", 150_000L);

        assertEquals("FAKE-TX-123", receipt.transactionId());
        assertEquals(150_000L, receipt.amountVnd());
        assertEquals(1, calls.get());
    }

    @Test
    void invalidOrderIsRejectedBeforeExternalCall() {
        AtomicInteger calls = new AtomicInteger();
        PaymentGateway fake = (id, amountVnd) -> {
            calls.incrementAndGet();
            return "unexpected";
        };
        CheckoutService service = new CheckoutService(fake);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("ORD-123", 0));
        assertThrows(IllegalArgumentException.class,
                () -> service.checkout(" ", 100));

        assertEquals(0, calls.get());
    }

    @Test
    void malformedGatewayReplyIsDetected() {
        CheckoutService service =
                new CheckoutService((id, amountVnd) -> "");

        assertThrows(IllegalStateException.class,
                () -> service.checkout("ORD-123", 100));
    }
}
~~~

These three tests verify input rules, interactions through abstractions, and protection against adapters violating contracts. They do not prove that an HTTP/SDK adapter really works; real adapters still need integration tests with a sandbox or controlled test environment.

An important advantage of **constructor injection** is that required dependencies are explicit at construction; a `final` field prevents subsequent reference reassignment. Tests can assemble fake adapters transparently.

## 6. DI Approaches and Appropriate Choices

| Dependency-supply method | Short example | When appropriate | Considerations |
|---|---|---|---|
| **Constructor injection** | `new CheckoutService(gateway)` | Required dependencies; usually the preferred default | Too many constructor parameters may indicate excessive class responsibilities |
| **Setter injection** | `service.setGateway(gateway)` | Optional dependencies or post-construction reconfiguration | Partially initialized states may exist and require management |
| **Field injection** | `@Autowired private PaymentGateway gateway;` | Legacy Spring code or special circumstances | Required dependencies are less visible; plain Java object creation is harder |
| **DI container** | `@Bean`, `@Service`, `@Autowired` | Applications needing bean configuration and lifecycle management | Assembly infrastructure does not replace abstraction design |

Beyond constructor/setter/field injection, **method parameter injection** fits dependencies or strategies used by one call rather than throughout an object's lifetime. Not every method input belongs in a constructor field.

A **service locator** such as `GlobalContainer.get(PaymentGateway.class)` called from business logic lacks constructor injection's transparency: it hides dependencies and makes tests depend on global container state. If a container is used, access it at the assembly boundary and pass dependencies explicitly to business classes.

## 7. How Do DIP, DI, and IoC Differ?

**Inversion of Control (IoC)** is broader: an external component controls part of execution or object initialization, such as Spring invoking application code or a container managing object configuration and lifecycles.

**DI** is one way to implement IoC for dependency provision. **DIP** governs module dependency structure. These concepts are related but operate at different levels:

~~~mermaid
flowchart LR
    D["DIP: thiết kế hướng phụ thuộc"] -->|"tạo ra nhu cầu về port"| P["Abstraction / interface"]
    I["DI: lắp ghép đối tượng"] -->|"truyền implementation vào"| S["Service"]
    C["IoC container (tùy chọn)"] -->|"có thể thực hiện"| I
    P -->|"là kiểu dependency của"| S
~~~

A plain Java application can apply DIP with manual DI without an IoC container. Conversely, a system using Spring DI extensively can still violate DIP if business classes depend directly on adapters, framework classes, or SDK DTOs.

## 8. Misconceptions and Code-Review Checks

- **"Having an interface means DIP is satisfied":** Not necessarily. If the interface lives in infrastructure and forces business code to depend on that module, the build dependency direction is still wrong. The more stable layer should own the required abstraction, with module dependencies pointing correctly.
- **"Moving `new` into a constructor achieves DIP":** It definitely achieves DI, but check whether the constructor parameter is a business-owned abstraction or a concrete infrastructure implementation.
- **"DIP requires an interface for every class":** No. Value objects, domain entities, stable algorithms, or internal classes without multiple substitution needs may not require new abstractions. Create ports at genuinely volatile boundaries or where testing/module isolation warrants them.
- **"DIP means infrastructure code must never be called":** At runtime, services still call infrastructure adapters. **Type/module dependency direction** is inverted, not execution order.
- **"With Spring, dependencies no longer need management":** The container helps wire objects, but bean counts, lifecycles, dependency cycles, and thread safety for stateful singletons still matter.
- **"Importing SDK request/response types into business code is harmless":** This leaks details. Convert types in adapters and define use-case-owned contract data types.
- **"The more injection, the better":** A constructor with dozens of unrelated services may indicate a class with too many responsibilities. DI makes complexity visible; it does not remove it.

### Refactoring a Real-World Case

1. Identify the **policy/use case** to keep stable, such as order validation and payment requests.
2. Define the exact business **contract**: parameters, results, exceptions, and idempotency, retry, and timeout rules when required.
3. Define the **port** in the correct module/layer, avoiding provider-specific types and annotations in the API.
4. Write an **adapter** implementing the port, with DTO conversion, error mapping, and network interaction in infrastructure.
5. Use **constructor injection** to connect objects in `main` or Spring configuration.
6. Write **unit tests** for the use case using fake/mock ports and separate **integration tests** for adapters; inspect module dependencies to prevent business code from importing infrastructure.

A crucial real-world contract example: if a payment gateway may retry after a timeout, merely defining `charge` and replacing its implementation is insufficient. Clarify idempotency keys, uncertain transaction states, and retry policies. DIP isolates provider APIs; a correct contract makes provider substitution operationally safe.

## 9. Practice Exercise

Consider this design:

~~~java
class ReportService {
    private final SqlReportRepository repository = new SqlReportRepository();

    String loadReport(String id) {
        return repository.load(id);
    }
}
~~~

Refactor so `ReportService` uses a business-defined `ReportRepository` while `SqlReportRepository implements ReportRepository` resides in storage. Create an `InMemoryReportRepository` for database-free unit tests. Finally, compare:

- Passing `SqlReportRepository` through the constructor: DI is present, but business code still depends on the concrete type.
- Passing `ReportRepository` through the constructor: DI is present **and** the design follows DIP, provided module dependencies also point in the correct direction.

**Self-check:** When switching from SQL to in-memory storage, must `ReportService` be edited or import another repository type? If so, revisit interface placement, constructor signatures, and where construction logic resides.

---

**Key takeaway:** **DIP determines "which abstraction to depend on and in which direction"; DI determines "who supplies the concrete implementation."** DI can exist without DIP. Appropriately placed abstractions, constructor injection, and an explicit composition root make infrastructure changes, business testing, and architectural control easier in Java/Spring.
