# Cohesion within a class in Java OOP

> **Goal:** Understand cohesion; assess whether a class's data and behavior support one responsibility; recognize overloaded classes; and refactor into well-defined boundaries without excessive fragmentation.

## 1. What is cohesion?

**Class cohesion** describes how closely the fields, methods, and rules **within one class** serve one meaningful purpose. A class has **high cohesion** when its members form a coherent concept and tend to change for related business reasons.

For example:

- `Cart` holds line items, validates quantities, and calculates item totals: all these behaviors concern shopping-cart state → typically **high** cohesion.
- `CartManager` calculates prices, writes to databases, emails users, logs sign-ins, exports CSV reports, and checks permissions: these behaviors change for unrelated reasons → typically **low** cohesion.

Ask yourself: **“How would I describe this class in one clear sentence without the word ‘and’?”** This is a heuristic, not a mechanical standard. A use-case coordinator may combine several steps to accomplish **one** business goal and remain cohesive as long as it does not embed implementation details for each step.

**Cohesion does not mean “few methods” or “every method reads the same field.”** A class with only 2 unrelated methods still has low cohesion. A class with many operations around the same domain concept can have high cohesion.

## 2. Distinguishing cohesion from coupling

| Criterion | Cohesion – within a component | Coupling – between components |
|---|---|---|
| Main question | Do the parts **within one class** closely serve the same responsibility? | How much must this class know or assume about other classes? |
| Scope of observation | Fields, methods, invariants, reasons to change | Constructor dependencies, APIs, types, method calls, shared state |
| Typical design goal | **High**: coherent responsibility | **Low enough**: minimal dependencies, stable interfaces |
| Warning sign | One class handles unrelated tasks | Changing one class forces changes across many others |
| Common improvement | Extract Class; move behavior to its owner | Dependency Inversion, interfaces/ports, limited APIs |

These qualities are **distinct** but related. Splitting a class into smaller ones may increase local cohesion while adding dependencies; a good design balances both.

~~~mermaid
flowchart LR
    subgraph Low["Lớp đa trách nhiệm"]
        direction TB
        X[AccountManager]
        X1[Login]
        X2[Export CSV]
        X3[Send email]
        X4[Compute billing]
    end
    subgraph High["Các trách nhiệm rõ ràng"]
        direction TB
        A[AuthenticationService]
        B[CsvReportExporter]
        C[NotificationGateway]
        D[BillingCalculator]
    end
    Low -. tách trách nhiệm .-> High
~~~

The diagram illustrates the goal of **grouping behaviors that change together with their proper owner**, not “one class per method.”

## 3. Signs of low cohesion

1. **Overly generic names:** `Manager`, `Helper`, `Processor`, or `Util` with responsibilities spanning unrelated domains.
2. **Method groups use separate sets of fields:** `sendEmail()` only uses SMTP configuration, `calculateTax()` only uses taxRate, and `saveOrder()` only uses a JDBC connection.
3. **Multiple independent reasons to change:** a discount policy, email vendor, or database schema update all require modifying the same class/file.
4. **Mixed error categories in one class:** network exceptions, input validation, pricing rules, and serialization are interwoven in a large method.
5. **Hard to test independently:** testing a pure computation requires starting a database, HTTP client, or SMTP service.
6. **A constructor with too many dependencies unrelated to one task:** a signal worth investigating, not a definitive verdict.
7. **Features frequently change the same class while sharing little context:** increases merge conflicts and spreads changes.

Importantly, **do not infer low cohesion from a long method alone**. A long method may harm readability or complexity while the class still has one responsibility. Conversely, splitting a large method into ten small methods in the same class does not fix mixed responsibilities.

## 4. Before refactoring: one class handles too much

The simple example below can compile in a Java 17 project as `LegacyCheckoutService.java`. It highlights three groups of work: **calculating amounts**, **persistence**, and **sending notifications**.

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record Line(String sku, int quantity, BigDecimal unitPrice) {}

// Ví dụ để phân tích thiết kế; chưa có kiểm tra dữ liệu đầu vào.
final class LegacyCheckoutService {
    private final Map<String, BigDecimal> database = new HashMap<>();

    BigDecimal calculateTotal(List<Line> lines) {
        BigDecimal total = BigDecimal.ZERO;
        for (Line line : lines) {
            total = total.add(
                    line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity())));
        }
        return total;
    }

    void saveOrder(String orderId, BigDecimal amount) {
        database.put(orderId, amount);
    }

    void sendReceipt(String email, String orderId) {
        System.out.println("Send receipt to " + email + " for " + orderId);
    }

    void checkout(String orderId, String email, List<Line> lines) {
        BigDecimal total = calculateTotal(lines);
        saveOrder(orderId, total);
        sendReceipt(email, orderId);
    }
}
~~~

In this example, `database` is needed only for persistence; calculating totals and sending emails do not use it. Each group changes independently:

| Behavior group | When does it change? | Appropriate owner |
|---|---|---|
| `calculateTotal()` | Pricing rules, rounding, discounts | `Cart` or an appropriate domain pricing component |
| `saveOrder()` | Storage/database/schema changes | `OrderRepository` |
| `sendReceipt()` | Email provider/template changes | `ReceiptSender` |
| `checkout()` | Checkout workflow sequence and rules change | `CheckoutService` orchestrating the use case |

A single class must accommodate all four changes. That is a cohesion problem, **not merely a line-count problem**.

## 5. After refactoring: each class has a coherent responsibility

In the revised design:

- `Cart` protects **the item list and the rules for computing the total from existing lines**.
- `OrderRepository` defines a contract for **saving and finding orders**; the implementation chooses the storage mechanism.
- `ReceiptSender` defines a contract for **sending receipts**; the implementation chooses the delivery channel.
- `CheckoutService` **orchestrates a checkout use case** and delegates implementation details.

~~~mermaid
classDiagram
    direction LR
    class Cart {
        -List~CartLine~ lines
        +addLine(sku, quantity, unitPrice)
        +total() BigDecimal
        +snapshot() List
    }
    class CheckoutService {
        -OrderRepository repository
        -ReceiptSender sender
        +checkout(orderId, email, cart)
    }
    class OrderRepository {
        <<interface>>
        +save(Order)
        +findById(id) Optional
    }
    class ReceiptSender {
        <<interface>>
        +sendReceipt(Order, email)
    }
    class InMemoryOrderRepository
    class ConsoleReceiptSender
    CheckoutService --> Cart : dùng giá trị
    CheckoutService --> OrderRepository : lưu đơn
    CheckoutService --> ReceiptSender : thông báo
    InMemoryOrderRepository ..|> OrderRepository
    ConsoleReceiptSender ..|> ReceiptSender
~~~

**Complete Java 17+ code in one file, `CohesionDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

// 1) Value object: một dòng hàng hợp lệ.
record CartLine(String sku, int quantity, BigDecimal unitPrice) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid cart line");
        }
    }

    BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

// 2) Domain object: quản lý trạng thái và invariant của giỏ hàng.
final class Cart {
    private final List<CartLine> lines = new ArrayList<>();

    void addLine(String sku, int quantity, BigDecimal unitPrice) {
        lines.add(new CartLine(sku, quantity, unitPrice));
    }

    List<CartLine> snapshot() {
        return List.copyOf(lines);
    }

    BigDecimal total() {
        return lines.stream()
                .map(CartLine::subtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    boolean isEmpty() {
        return lines.isEmpty();
    }
}

// 3) Dữ liệu đơn hàng đã đặt, bất biến.
record Order(String id, List<CartLine> lines, BigDecimal total) {
    Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(total, "total");
        if (id.isBlank() || lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid order");
        }
        lines = List.copyOf(lines);
    }
}

// 4) Hợp đồng hạ tầng lưu trữ.
interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(String id);
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}

// 5) Hợp đồng thông báo.
interface ReceiptSender {
    void sendReceipt(Order order, String email);
}

final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void sendReceipt(Order order, String email) {
        System.out.printf("Receipt %s: %s -> %s%n",
                order.id(), order.total(), email);
    }
}

// 6) Application service: điều phối use case checkout.
final class CheckoutService {
    private final OrderRepository repository;
    private final ReceiptSender receiptSender;

    CheckoutService(OrderRepository repository, ReceiptSender receiptSender) {
        this.repository = Objects.requireNonNull(repository, "repository");
        this.receiptSender = Objects.requireNonNull(receiptSender, "receiptSender");
    }

    Order checkout(String id, String email, Cart cart) {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(email, "email");
        Objects.requireNonNull(cart, "cart");

        if (id.isBlank() || email.isBlank() || cart.isEmpty()) {
            throw new IllegalArgumentException("Invalid checkout");
        }

        Order order = new Order(id, cart.snapshot(), cart.total());
        repository.save(order);
        receiptSender.sendReceipt(order, email);
        return order;
    }
}

public class CohesionDemo {
    public static void main(String[] args) {
        Cart cart = new Cart();
        cart.addLine("JAVA-BOOK", 2, new BigDecimal("125000"));
        cart.addLine("NOTEBOOK", 1, new BigDecimal("30000"));

        OrderRepository repository = new InMemoryOrderRepository();
        ReceiptSender sender = new ConsoleReceiptSender();
        CheckoutService service = new CheckoutService(repository, sender);

        Order order = service.checkout(
                "ORD-42", "user@example.com", cart);

        System.out.println(order.total());                 // 280000
        System.out.println(repository.findById("ORD-42").isPresent()); // true
    }
}
~~~

Run:

~~~bash
javac CohesionDemo.java
java CohesionDemo
~~~

Illustrative output:

~~~text
Receipt ORD-42: 280000 -> user@example.com
280000
true
~~~

**Why is cohesion better?** `Cart` methods focus on shopping-cart state; `OrderRepository` handles persistence; `ReceiptSender` handles notifications. `CheckoutService` still uses both storage and messaging, but **its single goal** is to carry out checkout in sequence: prepare order data → save → request receipt delivery. Coordinating multiple steps does not imply low cohesion.

**Example limitations:** `ConsoleReceiptSender` only prints to the console; it sends no real email. The code focuses on class design and does not ensure atomicity across the database and notification infrastructure. A real system must define behavior if email delivery fails after an order is saved, considering transactions, retry/idempotency, or an outbox. If the cart can change concurrently between `snapshot()` and `total()`, the two values may disagree; use a consistent snapshot or restrict cart modifications to one thread during its lifecycle.

## 6. How does cohesion relate to SRP?

The **Single Responsibility Principle (SRP)** is often explained as “a class should have one reason to change,” more precisely **one primary group of business stakeholders/change needs**. Cohesion describes internal coherence; SRP is a principle about **responsibility boundaries and reasons for change**.

They are related but not identical:

- `Cart` has `addLine()`, `isEmpty()`, and `total()`: multiple operations that collectively protect cart rules.
- `CheckoutService` calls the repository and receipt sender: it coordinates **one** use case without implementing SQL or SMTP itself.
- If tax calculations become complex, vary across jurisdictions, or require multiple policy versions, consider extracting `TaxPolicy`/`PricingService`. If the cart simply sums existing line subtotals, however, `Cart.total()` is appropriate.
- Split classes by **real reasons to change**, not one class per method.

A helpful review question: **“If the pricing team changes tax rules, must we edit the receipt sender or order repository?”** If so, responsibility boundaries may be mixed.

## 7. Cohesion levels in design: a thinking tool

Some references classify program cohesion from weak to strong. These labels are traditionally taught at the **module or function** level; for **OOP classes**, use them as a qualitative analytical aid rather than an absolute standardized scoring scale.

| Cohesion type | Meaning | Java example | Assessment |
|---|---|---|---|
| **Coincidental** – accidental | Groups unrelated tasks | `MiscUtils` contains `sendEmail()`, `hashPassword()`, and `formatMoney()` | Usually very weak |
| **Logical** – technical grouping | Similar operations selected for unrelated purposes using a control flag | `Handler.process(type)` switches among email/SMS/CSV export | Often worth splitting |
| **Temporal** – same time | Tasks run together at startup/shutdown | `StartupTasks` opens a cache, runs migrations, and prints a banner | May be appropriate at the orchestration point |
| **Procedural** – ordered steps | Operations grouped because they execute in sequence | `Workflow` runs validate → save → notify | Can be cohesive for a single use case |
| **Communicational** – shared data | Methods work on the same domain data | `Cart` adds lines, computes totals, and checks for emptiness | Often good when domain-aligned |
| **Sequential** – output feeds next step | A parse → normalize → validate pipeline | `ImportPipeline` processes a record | May fit or require strategy extraction |
| **Functional** – one well-defined function | Component devoted to computing taxes under a consistent policy | `TaxCalculator` | Usually very strong |

**Do not score a class solely by the cohesion-category name:** An `ApplicationBootstrap` intentionally performs startup tasks and fits at the *composition root*. A `CheckoutService` intentionally runs three steps in order and can fit one use case. Problems arise when coordinators also embed algorithms belonging to separate responsibilities.

## 8. How to evaluate a class's cohesion

Use a **method × field** matrix (for example, 6 methods and 4 fields) to identify responsibility clusters. This is not a complete formula: pure methods that access no fields may still contribute to one coherent concept.

Consider a class with four unrelated fields: `orders`, `smtpClient`, `taxRate`, and `csvFormat`.

| Method | orders | smtpClient | taxRate | csvFormat |
|---|:---:|:---:|:---:|:---:|
| `saveOrder()` | ✓ | | | |
| `findOrder()` | ✓ | | | |
| `sendReceipt()` | | ✓ | | |
| `calculateTax()` | | | ✓ | |
| `exportCsv()` | | | | ✓ |

The matrix shows **disconnected clusters**: two methods concern order storage, one email, one tax, and one file export. This strongly suggests several independent responsibilities.

By contrast, for `Cart`:

| Method | lines / CartLine | Cart rules |
|---|:---:|:---:|
| `addLine()` | ✓ | validates data |
| `isEmpty()` | ✓ | prevents checkout with an empty cart |
| `total()` | ✓ | computes line totals |
| `snapshot()` | ✓ | avoids exposing mutable state |

All these operations protect the same domain object.

**Assess cohesion by meaning**, not just field overlap. For example, `validateEmail()` may read no fields yet fit a value object `EmailAddress` because it enforces that value's invariant.

### LCOM and other metrics

`LCOM` (*Lack of Cohesion of Methods*) is a family of metrics for **how little methods cohere**. Definitions include LCOM1, LCOM2, LCOM3, and LCOM4, and they **can produce different values** for the same class. Some variants measure shared field usage, while others use connectivity graphs between methods.

Key points:

- **The metric name alone is insufficient**: when reporting “LCOM = 3”, specify the variant/tool and calculation method.
- In some variants, a high LCOM indicates poor cohesion; there is no universal threshold suitable for every project.
- Static utilities, immutable value objects, inherited classes, delegation-heavy classes, DTOs, and framework adapters may yield metrics that misrepresent business meaning.
- Methods that access fields indirectly through getters/helpers may be interpreted differently by static metrics.
- Metrics help **identify classes for review**, not replace understanding of responsibilities and reasons to change.

Combine numerical indicators such as public-method count, number of fields/dependencies, Git change history, method complexity, and test duration when useful. But do not split a class merely to improve the numbers.

## 9. Refactoring low cohesion into high cohesion

~~~mermaid
flowchart TD
    A[Chọn lớp thường xuyên thay đổi] --> B[Liệt kê method, field, caller, thay đổi]
    B --> C[Nhóm theo mục tiêu và invariant]
    C --> D{Có nhóm trách nhiệm tách biệt?}
    D -->|Không| E[Giữ lớp, cải thiện tên hoặc method nếu cần]
    D -->|Có| F[Chọn owner mới: domain/service/adapter]
    F --> G[Extract Class hoặc Move Method]
    G --> H[Cập nhật caller và DI]
    H --> I[Chạy test và kiểm tra hành vi]
    I --> J{Ổn định API và invariant?}
    J -->|Chưa| F
    J -->|Có| K[Đánh giá lại cohesion và coupling]
~~~

**Proceed safely in stages:**

1. **Read the existing contract:** public methods, exceptions, side effects, thread safety, transactions, processing order, and how callers use the class.
2. **Map responsibilities:** instead of line counts, group methods/fields by use case and by “who requests changes to this functionality?”
3. **Identify invariants:** which data must change together to remain valid? Keep that data close to the behavior enforcing its invariants. Do not arbitrarily separate `Cart.lines` from `Cart.addLine()` and let callers modify the list.
4. **Create appropriately named classes:** for example, `ReceiptSender`, `OrderRepository`, and `PricePolicy`; favor small, stable APIs.
5. **Move logic before removing old entry points:** use `Extract Class`/`Move Method`. During migration, carefully maintained compatible adapters/delegation may help when many callers still depend on the previous API.
6. **Inject dependencies via constructors:** supports isolated testing and makes required collaborators explicit. But **do not introduce an interface for every class** without substitution or architectural-boundary needs.
7. **Run business and appropriate integration tests:** check database/email failures, rollbacks, calculated amounts, timing/latency, and API compatibility.
8. **Review system-wide effects:** has the refactor introduced tangled dependencies or scattered business rules? If so, reconsider the boundaries.

A typical failed refactor moves each method into its own service, after which simple operations traverse 8 services. Individual classes may look “highly cohesive,” but coupling rises and business flows become harder to understand. Group by **concepts and invariants**, not file size.

## 10. Testing the new design

Tests should verify **behavior and interaction boundaries**. For `CohesionDemo.java`, use JUnit Jupiter 5.

**`CohesionDemoTest.java`** (in the same package to access package-private classes):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

class CohesionDemoTest {
    @Test
    void cartOwnsItsPricingInvariant() {
        Cart cart = new Cart();

        cart.addLine("JAVA-BOOK", 2, new BigDecimal("125000"));
        cart.addLine("NOTEBOOK", 1, new BigDecimal("30000"));

        assertEquals(0, new BigDecimal("280000").compareTo(cart.total()));
        assertEquals(2, cart.snapshot().size());
        assertThrows(IllegalArgumentException.class,
                () -> cart.addLine("BAD", 0, BigDecimal.ONE));
        assertThrows(UnsupportedOperationException.class,
                () -> cart.snapshot().clear());
    }

    @Test
    void checkoutSavesThenSendsReceiptOnce() {
        List<String> calls = new ArrayList<>();

        OrderRepository repository = new OrderRepository() {
            @Override
            public void save(Order order) {
                calls.add("save:" + order.id());
            }

            @Override
            public Optional<Order> findById(String id) {
                return Optional.empty();
            }
        };

        ReceiptSender sender = (order, email) ->
                calls.add("send:" + order.id() + ":" + email);

        CheckoutService service = new CheckoutService(repository, sender);
        Cart cart = new Cart();
        cart.addLine("BOOK", 1, new BigDecimal("50000"));

        Order order = service.checkout("O-1", "a@example.com", cart);

        assertEquals(0, new BigDecimal("50000").compareTo(order.total()));
        assertEquals(List.of("save:O-1", "send:O-1:a@example.com"), calls);
    }

    @Test
    void invalidCheckoutDoesNotCallCollaborators() {
        List<String> calls = new ArrayList<>();
        OrderRepository repository = new OrderRepository() {
            public void save(Order order) { calls.add("saved"); }
            public Optional<Order> findById(String id) {
                return Optional.empty();
            }
        };
        ReceiptSender sender = (order, email) -> calls.add("sent");
        CheckoutService service = new CheckoutService(repository, sender);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("O-2", "a@example.com", new Cart()));
        assertTrue(calls.isEmpty());
    }
}
~~~

**What does this test prove?**

- `Cart` enforces positive quantities, prevents callers from modifying its list through the snapshot, and correctly calculates totals.
- `CheckoutService` coordinates the correct sequence, invokes collaborators only through injected contracts, and avoids calling them on invalid input.
- No database or email service must be started to test the calculations.

**What does this test not prove?** It does not establish correct transactions, durable persistence, or successful delivery of real emails. Integration tests against actual repositories/gateways or suitable test environments are still required. A test checking only “the class has 3 fields” or “the method is called calculateTotal” does not establish cohesion; those are implementation details.

## 11. Cases where splitting classes mechanically is unhelpful

| Scenario | Why cohesion may still be good | What to watch for |
|---|---|---|
| **Aggregate/domain entity** with many behaviors | Behaviors protect the same state and invariants | Do not turn the domain into an anemic model |
| **Application service / coordinator** calling many dependencies | All dependencies serve **one use case** | Does it embed too many infrastructure algorithms? |
| **Value object** with factory, parse, validate, and normalize methods | One concept with immutable data | Avoid “utils” mixing different value types |
| **Controller** with multiple related endpoints | One resource or bounded context | Avoid mixing business logic with HTTP mapping |
| **Adapter** supporting many operations on the same API | One integration boundary | Avoid leaking implementations directly into the domain |
| **Startup/composition root** building many objects | Main responsibility is assembling the application | Keep wiring here; do not embed business rules |

For example, `Money` can support addition, subtraction, multiplication, and basic conversions/formatting; multiple methods alone do not imply it should be split. But converting currencies at real-time exchange rates should generally involve a separate collaborator rather than forcing an immutable value object to call HTTP.

## 12. Cohesion, performance, thread safety, and data

High cohesion often isolates changes, but **does not itself guarantee** performance, thread safety, or prevention of data loss:

- The example `Cart` uses a mutable `ArrayList` and is not thread-safe. That may be acceptable for a session cart modified by only one thread at a time. If concurrent requests modify the same cart, synchronization or immutable design is needed.
- Moving persistence into a separate repository class does not automatically make database transactions atomic. The transaction boundary belongs at the use case or another appropriate layer, depending on framework and business rules.
- If totals are repeatedly calculated over a large collection, caching and invalidating the result when `addLine()` is invoked may help. Optimize based on measurements without breaking invariants merely to reduce code size.
- `BigDecimal` is used for money to avoid binary floating-point inaccuracies of `double`; real applications also need agreed currency, scale, and rounding policies.

**Good class design balances multiple goals:** high cohesion, managed coupling, protected invariants, readable APIs, and complexity appropriate to the problem.

## 13. Exercise: improving UserManager cohesion

Consider this hypothetical class API:

~~~java
class UserManager {
    void register(String email, String password) { /* ... */ }
    boolean verifyPassword(String email, String password) { /* ... */ }
    void exportAllUsersToCsv(String path) { /* ... */ }
    void emailMonthlyNewsletter() { /* ... */ }
    long calculateRevenueForMonth(int year, int month) { /* ... */ }
}
~~~

**Task:** Group methods by source of change; propose classes such as `RegistrationService`, `PasswordVerifier`, `UserReportExporter`, `NewsletterService`, and `RevenueReportService` **only if** those boundaries truly fit the domain. Sketch the dependency diagram; do not let every class point back to `UserManager` as a disguised “god service.”

Write at least the following tests:

1. Valid registration and password verification according to the rules.
2. CSV export does not depend on SMTP; sending newsletters does not require opening a CSV file.
3. Revenue rule changes do not alter registration or authentication logic.
4. The coordinating use case can still run from a clear composition root without circular dependencies.

**Self-assessment:** Can you briefly explain each new class's responsibility in one sentence? Do methods and state that enforce an invariant stay with the same owner? Can you easily trace a use case's path through its collaborators?

---

**Remember:** *High cohesion* means members of a class **jointly serve one meaningful responsibility**, so business changes are easier to isolate and test independently. Evaluate cohesion by **semantics, invariants, and reasons to change**, not just class names, method counts, field counts, or LCOM scores.
