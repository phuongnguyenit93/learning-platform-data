# Classes with too many responsibilities (God Class): recognizing and refactoring them correctly

> **Topic:** OOP → Design Pitfalls → Classes with too many responsibilities.  
> **Objective:** Understand why a class can become a maintenance bottleneck, distinguish a "long class" from a "class with too many responsibilities," identify warning signs through reasons to change and cohesion among methods, and refactor into well-defined parts in Java while preserving business behavior.

## 1. What does "a class with too many responsibilities" mean?

**God Class** (sometimes called *Blob*, *Large Class*, or *Bloaters* in code-smell taxonomies) describes a design smell: one class combines too many concerns that should be able to change, be tested, and evolve relatively independently. It may know too much about the rest of the system, hold a large amount of unrelated state, and channel every change through itself.

For example, an `OrderManager` might simultaneously:

- validate order data;
- calculate prices, taxes, and discounts;
- persist orders to a database;
- call a payment gateway;
- send notification emails;
- generate invoice PDFs;
- format data for a REST API.

Changing a tax formula, switching database management systems, or updating an email template may all require editing the same `OrderManager.java` file. Changes arising for **different reasons** collide within one class.

The central question is not "how many lines are too many?" **A 500-line class implementing one highly cohesive algorithm can be reasonable**, while a 100-line class that calculates taxes, sends emails, and makes HTTP calls may already have too many responsibilities.

A practical criterion is the **reason to change**: must the class change because of multiple business decisions or the needs of different groups of people or parts of the system?

## 2. Why does this design arise?

Initially, to deliver a feature quickly, developers often put validation, calculations, persistence, and notifications into one method. When new requirements arrive, they add another `if` branch or dependency to the same class because "everything related to orders is already here."

Over time, the class becomes a central repository of knowledge:

~~~mermaid
flowchart LR
    C["OrderManager"]
    C --> V["Validation"]
    C --> P["Pricing / Tax"]
    C --> D["Database"]
    C --> M["Email / SMS"]
    C --> F["PDF / CSV"]
    C --> A["API response"]
    C --> T["Payment gateway"]
~~~

These responsibilities all concern **orders**, but they do not necessarily share the same **reason to change**. A common business domain name such as `Order` does not prove they belong in the same class.

Common causes include missing module boundaries, reluctance to add classes, copy-paste, direct dependencies on frameworks or SDKs, tight deadlines, and too few tests to refactor safely.

### Distinguishing the terms

| Term | Main concern | Relationship to God Class |
|---|---|---|
| **God Class / Blob** | Knows and does too much, often with broad impact | A typical example of a class with too many responsibilities |
| **Large Class** | Large size: many lines, fields, or methods | A warning sign worth investigating, **not sufficient** for a diagnosis |
| **Low Cohesion** | Fields/methods do not serve a consistent shared purpose | Fairly strong evidence when combined with multiple reasons to change |
| **High Coupling** | Depends directly on many other classes or modules | Widens the impact of changes |
| **SRP violation** | One module serves multiple independent actors/reasons to change | The design-principle interpretation behind many God Classes |
| **Anemic Domain Model** | Domain objects have little business behavior; services hold most logic | May coexist with a God Service, but is a different issue |

A long class is **not necessarily** a God Class. Conversely, a very short "manager" class that forwards dozens of requests to different APIs may still be a hub with excessively broad dependencies.

## 3. Warning signs in code and change history

Inspect the source code and ask:

| Sign | Example | Consequence |
|---|---|---|
| Many reasons to edit the same file | Tax, SQL, and email changes all modify `OrderManager` | Merge conflicts, difficult reviews, and regressions that are hard to isolate |
| Fields form distinct clusters | `dbConnection`, `mailClient`, `pdfWriter`, `taxRate` | The class's state may not serve a common purpose |
| Methods do not share data | `sendEmail()` does not use data from `calculateTax()` | Low cohesion |
| An inflated public API | `createOrder`, `exportCsv`, `resetPassword`, `syncWarehouse` | Clients must see capabilities they do not need |
| Branches mixed with side effects | Price calculations interleaved with DB and HTTP calls | Slow tests and failures that are difficult to reproduce |
| Difficult setup in unit tests | Testing arithmetic requires DB/mail/SDK configuration | Responsibilities have not been isolated |
| Small changes have a wide impact | Updating an email template breaks pricing tests | Weak boundaries between concerns |

The strongest sign is often **repeated unrelated changes touching the same class**. During an audit, inspect change history, actual use cases, and the dependency graph; avoid judging solely by names such as `*Manager` or `*Service`.

### "One responsibility" does not mean "one method"

According to the **Single Responsibility Principle (SRP)**, a module should have one coherent reason to change. A `PriceCalculator` can still provide `calculateSubtotal`, `calculateDiscount`, and `calculateTax` if they all belong to the **pricing policy** and really do change together.

Conversely, splitting a 100-line method into 10 private methods **does not, by itself, fix a God Class** if that class still handles payment calculations, SQL, and SMTP.

## 4. A design smell: everything in one class

The following is an **intentionally flawed example** of an ordering application:

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record Item(String sku, int quantity, BigDecimal unitPrice) {}

final class AllInOneOrderService {
    private final Map<String, BigDecimal> fakeDatabase = new HashMap<>();

    String placeOrder(
            String orderId, String email, List<Item> items) {

        // 1. Validate input.
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing order ID");
        }

        // 2. Calculate price.
        BigDecimal total = BigDecimal.ZERO;
        for (Item item : items) {
            total = total.add(item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())));
        }

        // 3. Persist (giả lập).
        fakeDatabase.put(orderId, total);

        // 4. Notify (giả lập).
        System.out.println("[DEMO MAIL] " + email + ": " + orderId);

        // 5. Format text for a caller.
        return "Order " + orderId + " total = " + total;
    }
}
~~~

This snippet illustrates a *code smell*; it is **not a production implementation**. It does not validate `items`, quantities, unit prices, duplicate order IDs, or notification failures. These omissions also illustrate the problem: the more concerns one function handles, the easier it is to overlook contracts at the boundaries.

Suppose email must be replaced with SMS. We would have to edit the class containing the pricing formula. Replacing `HashMap` with JPA would again modify that class. To unit-test the price of two items without sending a notification, the test would have to avoid the side effect.

We could add many private methods, but **the reasons to change would still coexist in `AllInOneOrderService`**.

## 5. Redesign: split along responsibility boundaries

One refactoring approach is to keep a relatively thin **orchestrating use case** and put independent policies and integrations in the appropriate places:

~~~mermaid
flowchart TD
    UI["Caller / Controller"] --> UC["PlaceOrderUseCase"]
    UC --> PR["PriceCalculator"]
    UC --> REPO["OrderRepository (port)"]
    UC --> NOTI["OrderNotifier (port)"]
    MEMORY["InMemoryOrderRepository"] -.->|"implements"| REPO
    MAIL["ConsoleOrderNotifier"] -.->|"implements"| NOTI
    DB["Adapter DB thật sau này"] -.->|"implements"| REPO
~~~

This separation has a concrete purpose:

- **`PriceCalculator`:** calculates amounts from order items without knowing about the database or email recipient.
- **`OrderRepository`:** defines a contract for saving order results; an adapter decides where to persist them.
- **`OrderNotifier`:** defines a notification contract; an adapter chooses email, SMS, or demo logging.
- **`PlaceOrderUseCase`:** owns the **order-placement workflow**: accept a valid request → calculate the amount → create the result → request persistence → request notification.
- **Composition root:** creates and connects objects; this is where knowledge of infrastructure implementations belongs.

**Note:** Calling several collaborators does not automatically make a use case a God Class. **Orchestrating the steps of one use case** can be **one cohesive responsibility**. Problems arise when the use case itself contains SQL logic, pricing rules, SMTP, PDF generation, and numerous unrelated use cases.

## 6. Complete, standalone Java 17 example

This example uses monetary amounts with two decimal places to make calculations easy to follow; in a real application, **rounding rules and currency units** must follow business requirements. The adapters simulate in-memory/console operations; they do not send real email or write to a real database.

Save as **`ResponsibilityDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

// Value object: quy tắc hợp lệ của một mặt hàng.
record OrderItem(String sku, int quantity, BigDecimal unitPrice) {
    OrderItem {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (!sku.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid sku");
        }
        if (quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "Invalid quantity or price");
        }

        try {
            unitPrice = unitPrice.setScale(
                    2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Unit price has fractions below 0.01", ex);
        }
    }
}

// Dữ liệu đầu vào của một use case.
record PlaceOrderRequest(
        String orderId,
        String customerEmail,
        List<OrderItem> items) {
    PlaceOrderRequest {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerEmail, "customerEmail");
        Objects.requireNonNull(items, "items");

        if (!orderId.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid order ID");
        }
        if (customerEmail.isBlank()) {
            throw new IllegalArgumentException("Missing email");
        }
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty order");
        }
    }
}

record OrderReceipt(String orderId, BigDecimal total) {}

// Chính sách tính tiền: không biết lưu trữ hoặc thông báo.
final class PriceCalculator {
    BigDecimal calculate(List<OrderItem> items) {
        Objects.requireNonNull(items, "items");

        BigDecimal total = BigDecimal.ZERO.setScale(2);
        for (OrderItem item : items) {
            total = total.add(item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())));
        }
        return total;
    }
}

// Hai port mô tả những việc use case cần.
interface OrderRepository {
    void save(OrderReceipt receipt);
}

interface OrderNotifier {
    void orderPlaced(String customerEmail, OrderReceipt receipt);
}

// Use case: giữ trình tự nghiệp vụ, không chứa công thức/SDK.
final class PlaceOrderUseCase {
    private final PriceCalculator calculator;
    private final OrderRepository repository;
    private final OrderNotifier notifier;

    PlaceOrderUseCase(
            PriceCalculator calculator,
            OrderRepository repository,
            OrderNotifier notifier) {
        this.calculator = Objects.requireNonNull(
                calculator, "calculator");
        this.repository = Objects.requireNonNull(
                repository, "repository");
        this.notifier = Objects.requireNonNull(
                notifier, "notifier");
    }

    OrderReceipt execute(PlaceOrderRequest request) {
        Objects.requireNonNull(request, "request");

        BigDecimal total = calculator.calculate(request.items());
        OrderReceipt receipt = new OrderReceipt(
                request.orderId(), total);

        // Quy trình có thứ tự rõ, mỗi dependency sở hữu một việc.
        repository.save(receipt);
        notifier.orderPlaced(request.customerEmail(), receipt);
        return receipt;
    }
}

// Adapter lưu tại bộ nhớ, minh họa — không thread-safe.
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, OrderReceipt> storage = new HashMap<>();

    @Override
    public void save(OrderReceipt receipt) {
        Objects.requireNonNull(receipt, "receipt");

        if (storage.putIfAbsent(receipt.orderId(), receipt) != null) {
            throw new IllegalStateException("Duplicate order ID");
        }
    }

    OrderReceipt findRequired(String id) {
        OrderReceipt found = storage.get(id);
        if (found == null) {
            throw new IllegalArgumentException("Order not found");
        }
        return found;
    }
}

// Adapter mô phỏng gửi thông báo, không in email của khách hàng.
final class ConsoleOrderNotifier implements OrderNotifier {
    @Override
    public void orderPlaced(
            String customerEmail, OrderReceipt receipt) {
        Objects.requireNonNull(customerEmail, "customerEmail");
        System.out.printf(
                "[DEMO] Created %s, total=%s%n",
                receipt.orderId(),
                receipt.total().toPlainString());
    }
}

public class ResponsibilityDemo {
    public static void main(String[] args) {
        var repository = new InMemoryOrderRepository();
        var notifier = new ConsoleOrderNotifier();

        var useCase = new PlaceOrderUseCase(
                new PriceCalculator(),
                repository,
                notifier);

        var request = new PlaceOrderRequest(
                "ORD-42",
                "customer@example.com",
                List.of(
                        new OrderItem(
                                "SKU-1", 2, new BigDecimal("50.00")),
                        new OrderItem(
                                "SKU-2", 1, new BigDecimal("25.50"))
                ));

        OrderReceipt receipt = useCase.execute(request);

        System.out.println("Receipt: " + receipt);
        System.out.println("Saved: "
                + repository.findRequired("ORD-42").total());
    }
}
~~~

Compile and run:

~~~bash
javac ResponsibilityDemo.java
java ResponsibilityDemo
~~~

Expected output:

~~~text
[DEMO] Created ORD-42, total=125.50
Receipt: OrderReceipt[orderId=ORD-42, total=125.50]
Saved: 125.50
~~~

The example uses Java 17 `record` types to represent value data and simple boundaries; **records do not automatically enforce all invariants**, so constructors check the required conditions. `List.copyOf` creates a structural snapshot of the list and rejects null elements; `OrderItem` is a record whose components are immutable, so the example contains no state-mutable elements.

Several demo decisions are intentionally limited in scope:

- `customerEmail` is checked only for nonblank content; this is **not complete email validation**. Real systems need separate validation and verification policies.
- `InMemoryOrderRepository` does not persist to disk, is not thread-safe, and has no transaction support.
- `ConsoleOrderNotifier` **does not send email**. It only simulates a side effect to demonstrate the boundary.
- `OrderReceipt` is a simple use-case result; an application with order, payment, and shipping states needs an appropriate domain model.
- Name classes and modules so dependencies point toward stable contracts. Not every implementation needs an interface if no replacement is required.

### Before and after refactoring: what actually changes?

| System change | With everything in `AllInOneOrderService` | After refactoring |
|---|---|---|
| Change the pricing formula | Edit the same class that handles DB/email | Update `PriceCalculator` and pricing tests |
| Change the persistence mechanism | Edit DB access logic inside a business class | Replace the `OrderRepository` adapter |
| Switch from email to SMS | Edit notification logic inside the business class | Replace the `OrderNotifier` adapter |
| Validate an invalid order item | Validation is buried in a large function | Express the invariant in `OrderItem` |
| Change workflow order: persist before notifying | Side effects are easy to interleave | The order is explicit in `PlaceOrderUseCase.execute` |
| Unit-test the pricing formula alone | DB/mail setup may get in the way | Directly create `new PriceCalculator()` |

**Key point:** Refactoring is **more than splitting files**. We must establish boundaries where *each part owns a decision* and other parts interact with it through clear contracts.

## 7. Class responsibilities versus use-case responsibilities

At this point, you might ask: "`PlaceOrderUseCase` calls three dependencies, so does it have too many responsibilities?"

**Not necessarily.** Placing an order **is itself a workflow** involving pricing, persistence, and notification. A use case may be responsible for executing **one ordered business scenario**, while each collaborator handles a specialized detail.

However, if `PlaceOrderUseCase` also acquires `cancelOrder`, `refund`, `generateMonthlyReport`, `syncWarehouse`, `createPromoCampaign`, and dozens of unrelated state fields, it may be turning into a **God Service**. Examine whether these requirements have the same reason to change or belong to different workflows.

Do not interpret SRP as a mechanical rule such as "one method per class," "at most 100 lines per class," or "at most three dependencies per method." These are heuristics, not definitions of responsibility.

### What behavior should a domain object retain?

Removing every behavior from entities can produce an *anemic domain model*, where all constraints and state changes are pushed into other services. For example, a `BankAccount` can enforce valid withdrawal rules itself because that is **a responsibility closely tied to the account's state**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

final class BankAccount {
    private BigDecimal balance;

    BankAccount(BigDecimal initial) {
        Objects.requireNonNull(initial);
        if (initial.signum() < 0) {
            throw new IllegalArgumentException("Negative initial balance");
        }
        this.balance = initial;
    }

    void withdraw(BigDecimal amount) {
        Objects.requireNonNull(amount);
        if (amount.signum() <= 0 || amount.compareTo(balance) > 0) {
            throw new IllegalArgumentException("Invalid withdrawal");
        }
        balance = balance.subtract(amount);
    }

    BigDecimal balance() {
        return balance;
    }
}
~~~

This is **appropriate behavior inside a domain object**, not evidence of a class doing too much. `BankAccount` would become suspicious if it started invoking SMTP, generating CSV reports, or knowing the database connection password.

## 8. Common mistakes when refactoring a God Class

### 8.1. Splitting classes but only forwarding calls

Example that does not solve the problem:

~~~java
class OrderFacade {
    private final LegacyOrderManager manager = new LegacyOrderManager();

    void saveOrder() {
        manager.doEverything();
    }
}
~~~

A well-named wrapper does not separate policy from side effects if `LegacyOrderManager` still does everything. Identify **which logic actually changes ownership** and inspect dependencies afterward.

### 8.2. Splitting so finely that the business workflow becomes hard to read

If each pricing step becomes a separate class (`AddItemService`, `MultiplyQuantityService`, `RoundTotalService`...) without its own reason to change, the extra abstractions can make code harder to follow. Group steps that serve the same purpose in a cohesive object.

### 8.3. Moving everything into a static "Utils" class

~~~java
OrderUtils.validate(...);
OrderUtils.calculate(...);
OrderUtils.save(...);
OrderUtils.sendMail(...);
~~~

Renaming `OrderManager` to `OrderUtils` still concentrates responsibilities and may even make dependency injection or side-effect testing harder. `static` methods are suitable for small pure functions, but "utils" should not become a dumping ground for every policy and adapter.

### 8.4. Creating an interface for every class

An interface with exactly one implementation does not automatically add value unless it separates stable and changing boundaries or helps testing. `PriceCalculator` in this example is an ordinary class because its pricing logic can be tested directly and does not yet need multiple algorithms. `OrderRepository` and `OrderNotifier` are meaningful abstractions because they prevent the use case from depending on a particular persistence or notification mechanism.

### 8.5. Overlooking transaction boundaries while moving code

For example, consider these sequential calls:

~~~java
repository.save(receipt);
notifier.orderPlaced(email, receipt);
~~~

If `save` succeeds and `orderPlaced` throws an exception, **the order has been saved but the notification has not been sent**. Splitting classes does not automatically solve atomicity, retries, or idempotency.

In a real system, a **transactional outbox** can persist the order and an event to be published in the same database transaction, after which a worker publishes the event with retry and duplicate-handling capabilities. The details depend on consistency requirements; do not assume a DB transaction can encompass email or every HTTP side effect.

Similarly, if pricing depends on mutable data, establish which price-list/tax-rate version applies when the order is created so refactoring does not change the result.

## 9. Testing for safe refactoring

Before changing a large class, identify **which behavior must be preserved**. For legacy code without tests, *characterization tests* can capture existing behavior and lock down rules that must remain stable; then write isolated tests for extracted components.

The following example uses JUnit Jupiter 5 and classes from `ResponsibilityDemo.java`. Place it in `ResponsibilityDemoTest.java` in the same package, add the `org.junit.jupiter:junit-jupiter` dependency and an appropriate test runner:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class ResponsibilityDemoTest {
    @Test
    void priceIsIndependentOfDatabaseAndNotification() {
        var calculator = new PriceCalculator();

        BigDecimal total = calculator.calculate(List.of(
                new OrderItem("SKU-1", 2, new BigDecimal("50.00")),
                new OrderItem("SKU-2", 1, new BigDecimal("25.50"))
        ));

        assertEquals(new BigDecimal("125.50"), total);
    }

    @Test
    void useCasePersistsBeforeNotifying() {
        var events = new ArrayList<String>();

        OrderRepository repository = receipt ->
                events.add("saved:" + receipt.orderId());

        OrderNotifier notifier = (email, receipt) ->
                events.add("notified:" + receipt.orderId());

        var useCase = new PlaceOrderUseCase(
                new PriceCalculator(), repository, notifier);

        var request = new PlaceOrderRequest(
                "ORD-42",
                "customer@example.com",
                List.of(new OrderItem(
                        "SKU-1", 1, new BigDecimal("10.00"))));

        var receipt = useCase.execute(request);

        assertEquals(new BigDecimal("10.00"), receipt.total());
        assertEquals(List.of(
                "saved:ORD-42",
                "notified:ORD-42"
        ), events);
    }

    @Test
    void notificationDoesNotRunWhenPersistenceFails() {
        AtomicInteger notifications = new AtomicInteger();

        OrderRepository brokenRepository = receipt -> {
            throw new IllegalStateException("Storage failure");
        };
        OrderNotifier notifier = (email, receipt) ->
                notifications.incrementAndGet();

        var useCase = new PlaceOrderUseCase(
                new PriceCalculator(), brokenRepository, notifier);

        var request = new PlaceOrderRequest(
                "ORD-99",
                "customer@example.com",
                List.of(new OrderItem(
                        "SKU-1", 1, new BigDecimal("10.00"))));

        assertThrows(IllegalStateException.class,
                () -> useCase.execute(request));
        assertEquals(0, notifications.get());
    }

    @Test
    void invalidQuantityIsRejectedBeforeUseCase() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderItem(
                        "SKU-1", 0, new BigDecimal("10.00")));
    }
}
~~~

**What these tests demonstrate:**

- `PriceCalculator` is tested **without** mocking a database or email.
- The orchestration test confirms the **order**: persistence is requested before notification.
- If the repository fails, the notifier has not been called, making workflow errors easier to detect.
- `OrderItem` invariants are tested where the value object is created.

These tests do not demonstrate that actual persistence or email delivery works. Adapters using JDBC/JPA/HTTP/SMTP need integration tests at the corresponding boundaries. Changes to transaction handling also require tests for retries, race conditions, duplicate notifications, and idempotency requirements.

## 10. Step-by-step refactoring to reduce the risk of behavior changes

A practical process for a large class already running in production:

1. **Identify features and clients:** Who calls which methods? Where do the data and side effects go? Flag high-risk rules (money, state, authorization, transactions).
2. **Capture current behavior:** Use characterization tests or integration tests for important flows; distinguish bugs that need separate fixes from behavior clients currently depend on.
3. **Group reasons to change:** Pricing, persistence, notification, validation, presentation, etc.; confirm the groupings through dependencies and field usage rather than class names.
4. **Extract pure logic first:** Move deterministic calculations (pure logic) into independently tested classes/methods. This is less risky than moving transactions or network calls.
5. **Separate communication ports from the use case:** Define `OrderRepository` and `OrderNotifier` around the caller's needs; add an adapter for old code when necessary.
6. **Move side effects carefully:** Preserve operation order, failure conditions, and retry policies defined by the contract; avoid sending duplicate notifications.
7. **Reduce the old class:** Leave it with only its genuine use-case responsibility or migrate callers to the new API; remove old paths when no one uses them.
8. **Verify changes:** Run appropriate module/unit/integration tests, compare business results, and inspect logs and queries. Optimize performance only when evidence supports it.

Safe refactoring usually consists of **many small, reviewable changes** instead of rewriting a thousand-line class at once. If API compatibility is required, a temporary forwarding adapter can remain until callers migrate, with a plan to remove it.

### Workflow diagram after extraction

~~~mermaid
sequenceDiagram
    actor Client
    participant U as PlaceOrderUseCase
    participant P as PriceCalculator
    participant R as OrderRepository
    participant N as OrderNotifier
    Client->>U: execute(request)
    U->>P: calculate(items)
    P-->>U: total
    U->>R: save(receipt)
    R-->>U: hoàn tất
    U->>N: orderPlaced(email, receipt)
    N-->>U: hoàn tất
    U-->>Client: receipt
    Note over U,N: Nếu notify lỗi sau save, cần chính sách nhất quán/retry riêng
~~~

## 11. When is splitting a class NOT necessary?

Signs that you **should retain** a class include:

- All methods genuinely support one cohesive invariant/algorithm and change under the same policy.
- Splitting it would only create more forwarding objects without reducing coupling or making tests easier.
- The component is a value object or aggregate whose business rules surround the same state.
- The problem is small, the algorithm is clear, and no real variation axis exists yet; refactoring offers too little benefit.
- A class has many methods because it implements a complete protocol, yet retains a clear responsibility boundary.

Do not decide based only on **LOC (lines of code), method count, cyclomatic complexity, or the name `Manager`**. Those help identify areas worth investigating; design decisions should consider cohesion, coupling, reasons to change, testability, and business impact.

## 12. Practice exercise: extracting classes from UserManager

Consider this hypothetical class:

~~~java
class UserManager {
    void register(String email, String password) { /* ... */ }
    boolean authenticate(String email, String password) { /* ... */ }
    void sendWelcomeEmail(String email) { /* ... */ }
    String exportUserCsv() { /* ... */ }
    void cleanupInactiveUsers() { /* ... */ }
}
~~~

Do not immediately turn five methods into five classes. Analyze:

- Which policies govern registration and authentication, and might they need to be separated?
- What security boundaries are required for password hashing, passwords, and sessions/tokens?
- Are email and CSV business responsibilities or system adapters?
- Should deleting inactive users be a separate batch job with different transaction/audit requirements?
- Which actors or requirement groups cause `UserManager` to change?

**Task:** Draw the relationship diagram after extraction, create interfaces only at replaceable boundaries, choose appropriate use-case names, and write at least three tests: invalid registration data, successful user persistence, and email failure after saving. Explicitly define the business policy for email failures (is registration still successful? are retries/an outbox used?).

### Self-check questions

1. Why is a "class with many lines" only a warning sign rather than proof of a God Class?
2. What does it reveal about reasons to change if both SQL and discount formulas require editing `OrderManager`?
3. Does splitting one large method into 10 private methods automatically ensure SRP?
4. Is `PlaceOrderUseCase` necessarily a God Class because it calls three dependencies? Why?
5. Why avoid moving both balance validation and withdrawals out of `BankAccount` when the invariant belongs to the account?
6. How do interfaces and DI help when switching database/mail adapters? Do they automatically solve transaction handling?
7. Why does `repository.save` succeeding while `notifier.orderPlaced` fails require a separate policy?
8. When should refactoring stop to avoid creating dozens of forwarding classes without real responsibilities?

**Conclusion:** A class with too many responsibilities tightly couples independent decisions, so changing one concern affects many others. Effective refactoring means **finding real change boundaries**, placing logic and side effects where they belong, keeping use-case orchestration cohesive, and relying on tests and business contracts to preserve results. **Class count is not a quality metric**; the ability to understand, change, and verify behavior is what matters.
