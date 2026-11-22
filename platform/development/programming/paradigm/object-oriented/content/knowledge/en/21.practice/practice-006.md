# Identifying design flaws in Java OOP

## 1. Exercise objectives

A program may **compile and produce correct results for a few inputs** while its design remains hard to extend, hard to test, and error-prone when requirements change. Conversely, lengthy code or many conditional statements do not automatically indicate poor design.

In this exercise, act as a code reviewer: inspect Java, identify suspicious design choices, explain consequences, assess their impact, suggest appropriate improvements, and write tests to protect behavior.

Expected learning outcomes:

- Distinguish **behavioral defects (bugs)**, **code smells**, **contract violations**, and **acceptable design trade-offs**.
- Recognize common OOP problems: exposed data, too many responsibilities, direct coupling to implementations, incorrect inheritance relationships, duplicate logic, type-based conditionals, global state, and unsafe money arithmetic.
- Cite concrete evidence from code instead of merely labeling something a "SOLID violation".
- Refactor an example into objects with clear responsibilities.
- Write JUnit tests proving that business logic still works after refactoring.

**Assessment principle:** Do not stop at "this violates SRP". Identify **which lines**, **what could fail**, **which changes make it fragile**, **how to improve it**, and **which tests verify the improvement**.

## 2. A process for identifying design flaws

When reviewing a class, ask these questions in order:

1. **What are its responsibilities?** How many independent reasons could force it to change?
2. **Who owns the state?** Can outside code bypass invariants when modifying data?
3. **What does it depend on?** Interfaces or concrete implementations? Does it create HTTP clients, repositories, clocks, or files itself?
4. **Where are the rules?** Does an object manage its own data, or does another class read getters and compute on its behalf?
5. **Is polymorphism used appropriately?** Is there a chain of if/instanceof checks selecting behaviors by object type?
6. **Are there hidden dependencies?** Static mutable state, global singletons, call order, or system time?
7. **What behavior is actually wrong?** Overflow, inconsistent state, missing validation, or failure-branch bugs?
8. **Is the fix worth its complexity?** A simple class does not need four interfaces merely to add numbers.

### Distinguishing severity

| Assessment | What it means | Example |
| --- | --- | --- |
| Confirmed bug | A specific case violates the contract | A long amount overflows into a negative value |
| Design risk | May not cause bugs today but makes changes difficult | Business class directly instantiates an HTTP adapter |
| Code smell | A reason to investigate, not a conclusive defect | Long method, many switches, numerous parameters |
| Intentional trade-off | A simple choice with explicit scope and limits | A small class instead of an unnecessary hierarchy |

There is no rule that "more than 20 lines is wrong" or "every if must become polymorphism". Evaluate responsibilities, change requirements, and evidence.

## 3. Exercise 1 — Read the code and find problems

Suppose a sales application contains the following Java. It is **deliberately flawed code for analysis**, lacking sufficient validation and financial safeguards.

~~~java
import java.util.List;

interface Gateway {
    boolean charge(String orderId, long amountVnd);
}

final class ConsoleGateway implements Gateway {
    @Override
    public boolean charge(String orderId, long amountVnd) {
        System.out.println("Charge " + orderId + ": " + amountVnd);
        return true;
    }
}

final class CheckoutManager {
    // Tất cả đối tượng CheckoutManager cùng dùng chung biến này.
    static long totalPaidVnd = 0;

    boolean checkout(
            String orderId,
            List<long[]> items,
            boolean vip) {

        long amount = 0;

        for (long[] item : items) {
            // item[0] = đơn giá; item[1] = số lượng
            amount += item[0] * item[1];
        }

        if (vip) {
            amount = amount - amount / 10;
        }

        if (amount <= 0) {
            return false;
        }

        Gateway gateway = new ConsoleGateway();
        boolean accepted = gateway.charge(orderId, amount);

        if (accepted) {
            totalPaidVnd += amount;
        }
        return accepted;
    }
}
~~~

### Your task before viewing the solution

Record at least six observations using this template:

| Location | Observable symptom | Consequence or failure scenario | Proposal | Proving test |
| --- | --- | --- | --- | --- |
| Example: new ConsoleGateway() | Direct dependency on an implementation | Unit tests always invoke the demo adapter; difficult to simulate declines | Inject Gateway through the constructor | Fake Gateway returns false; verify no payment is recorded |

Answer the following questions:

- Are "unit price" and "quantity" sufficiently clear in List<long[]>? What happens if an element contains just one number?
- Are long multiplications/additions checked for overflow?
- If a customer has two different orders, can the method easily reuse pricing rules?
- Which responsibility belongs to **order business logic**, which to **payment orchestration**, and which to **sales recording**?
- If another payment gateway is added, must CheckoutManager change?
- If two tests run in parallel, is totalPaidVnd reliable state?
- How does the program handle items = null, null elements, negative quantities, or blank order IDs?
- Must every code fragment be replaced with a design pattern?

### Suggested answers with reasoning

| Problem | Nature | Why it matters | Fix |
| --- | --- | --- | --- |
| List<long[]> and indices 0, 1 | Primitive Obsession / opaque data | Easy to confuse price and quantity; order-line invariants missing | Create OrderLine with named fields and validation |
| amount computed in CheckoutManager | Mixed responsibilities / possible Feature Envy | Payment service must know pricing internals | Move line calculations into OrderLine and totals into Order |
| amount += item[0] * item[1] | **Reproducible potential bug** on overflow | Java long silently overflows by default | Math.multiplyExact and Math.addExact |
| new ConsoleGateway() | Coupling to implementation | Tests cannot control gateway results | Constructor injection with Gateway |
| static long totalPaidVnd | Shared mutable state | Instances and tests interfere; updates are unsynchronized | Separate repository/ledger with clear lifecycle and consistency controls |
| Missing input validation | Invariants are unprotected | May cause NPE, ArrayIndexOutOfBoundsException, or incorrect values | Constructor/value-object validation |
| One method calculates prices, calls gateway, and aggregates sales | Multiple reasons to change (SRP) | A price-policy change also modifies payment flow | Separate Order, CheckoutService, and SalesLedger |
| Returning false for amount <= 0 | Unclear contract | Invalid data is conflated with declined payments | Distinguish validation exceptions from gateway declines |

An overflow problem can be illustrated independently:

~~~java
long wrong = Long.MAX_VALUE + 1;
System.out.println(wrong); // -9223372036854775808

Math.addExact(Long.MAX_VALUE, 1); // ArithmeticException
~~~

**Note: Not every code smell is a bug.** static can be appropriate for immutable constants. Here the risk is using **static mutable** state to store transactions. Likewise, a class named Manager is not necessarily poorly designed; inspect what it does.

## 4. Exercise 2 — Refactor by OOP responsibilities

Proposed separation:

- **OrderLine / Order:** own data and money-calculation rules.
- **PaymentGateway:** contract for submitting payment requests; implementations can be exchanged in tests.
- **SalesLedger:** contract for recording accepted payments.
- **CheckoutService:** orchestrate without calculating order totals manually or owning global sales state.

~~~mermaid
classDiagram
    class OrderLine {
      +String sku
      +long unitPriceVnd
      +int quantity
      +subtotalVnd() long
    }
    class Order {
      -String orderId
      -List~OrderLine~ lines
      -boolean vip
      +payableVnd() long
      +id() String
    }
    class PaymentGateway {
      <<interface>>
      +charge(orderId, amountVnd) boolean
    }
    class SalesLedger {
      <<interface>>
      +recordPaid(orderId, amountVnd) void
    }
    class CheckoutService {
      -PaymentGateway gateway
      -SalesLedger ledger
      +checkout(order) boolean
    }
    Order "1" *-- "1..*" OrderLine
    CheckoutService --> Order
    CheckoutService --> PaymentGateway
    CheckoutService --> SalesLedger
~~~

Example rules:
- An order contains at least one line; unit prices and quantities are positive; order and product IDs are nonblank.
- The amount is the sum of unit price × quantity for each line.
- VIP customers receive a 10% discount on totals, rounded down to VND using integer division.
- Record payments when the gateway returns true; do not record when it returns false.
- Overflow during calculation must stop execution before payment requests are submitted.

### 4.1. Runnable Java 17 + Maven + JUnit 5 project

~~~text
design-review-lab/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── OrderLine.java
    │   ├── Order.java
    │   ├── PaymentGateway.java
    │   ├── SalesLedger.java
    │   ├── CheckoutService.java
    │   └── Demo.java
    └── test/java/example/
        └── DesignReviewTest.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>design-review-lab</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/OrderLine.java**

~~~java
package example;

public record OrderLine(String sku, long unitPriceVnd, int quantity) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (unitPriceVnd <= 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                    "Price and quantity must be positive");
        }
    }

    public long subtotalVnd() {
        return Math.multiplyExact(unitPriceVnd, (long) quantity);
    }
}
~~~

**src/main/java/example/Order.java**

~~~java
package example;

import java.util.List;
import java.util.Objects;

public final class Order {
    private final String id;
    private final List<OrderLine> lines;
    private final boolean vip;

    public Order(String id, List<OrderLine> lines, boolean vip) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must have lines");
        }
        this.id = id;
        this.lines = List.copyOf(lines);
        this.vip = vip;
    }

    public String id() {
        return id;
    }

    public long payableVnd() {
        long subtotal = 0;
        for (OrderLine line : lines) {
            subtotal = Math.addExact(subtotal, line.subtotalVnd());
        }
        long discount = vip ? subtotal / 10 : 0;
        return subtotal - discount;
    }
}
~~~

**src/main/java/example/PaymentGateway.java**

~~~java
package example;

@FunctionalInterface
public interface PaymentGateway {
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/example/SalesLedger.java**

~~~java
package example;

@FunctionalInterface
public interface SalesLedger {
    void recordPaid(String orderId, long amountVnd);
}
~~~

**src/main/java/example/CheckoutService.java**

~~~java
package example;

import java.util.Objects;

public final class CheckoutService {
    private final PaymentGateway gateway;
    private final SalesLedger ledger;

    public CheckoutService(PaymentGateway gateway, SalesLedger ledger) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.ledger = Objects.requireNonNull(ledger, "ledger");
    }

    public boolean checkout(Order order) {
        Objects.requireNonNull(order, "order");

        // Tính trước khi gọi phụ thuộc có tác dụng phụ.
        long amount = order.payableVnd();

        boolean approved = gateway.charge(order.id(), amount);
        if (approved) {
            ledger.recordPaid(order.id(), amount);
        }
        return approved;
    }
}
~~~

**src/main/java/example/Demo.java**

~~~java
package example;

import java.util.List;

public final class Demo {
    public static void main(String[] args) {
        Order order = new Order("DH-101", List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)), true);

        PaymentGateway gateway = (id, amount) -> {
            System.out.println("Charge " + id + ": " + amount);
            return true; // Adapter minh họa, không thu tiền thật.
        };

        SalesLedger ledger = (id, amount) ->
                System.out.println("Recorded " + id + ": " + amount);

        CheckoutService checkout = new CheckoutService(gateway, ledger);

        System.out.println("Payable: " + order.payableVnd());
        System.out.println("Accepted: " + checkout.checkout(order));
    }
}
~~~

From the directory containing pom.xml, run:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes example.Demo
~~~

Expected output:

~~~text
Payable: 207000
Charge DH-101: 207000
Recorded DH-101: 207000
Accepted: true
~~~

These interfaces separate **pricing**, **gateway calls**, and **recording**. In production, failures after a charge succeeds but before the ledger is updated require durable transactions, reconciliation/idempotency, or a transactional outbox; separating classes alone cannot guarantee distributed consistency.

## 5. Exercise 3 — Write tests that demonstrate improvements

After refactoring, tests should verify **caller-observable behavior** and **side-effecting interactions**. CheckoutService itself need not be mocked.

**src/test/java/example/DesignReviewTest.java**

~~~java
package example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class DesignReviewTest {
    private Order regularOrder() {
        return new Order("DH-1", List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)), false);
    }

    @Test
    void lineOwnsItsSubtotal() {
        OrderLine line = new OrderLine("BOOK", 100_000, 2);
        assertEquals(200_000L, line.subtotalVnd());
    }

    @Test
    void orderOwnsPriceAndVipRule() {
        Order regular = regularOrder();
        Order vip = new Order("DH-2", List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)), true);

        assertEquals(230_000L, regular.payableVnd());
        assertEquals(207_000L, vip.payableVnd());
    }

    @Test
    void approvedPaymentIsRecordedExactlyOnce() {
        List<String> charges = new ArrayList<>();
        List<String> records = new ArrayList<>();

        PaymentGateway gateway = (id, amount) -> {
            charges.add(id + ":" + amount);
            return true;
        };
        SalesLedger ledger = (id, amount) ->
                records.add(id + ":" + amount);

        CheckoutService service = new CheckoutService(gateway, ledger);

        assertTrue(service.checkout(regularOrder()));
        assertEquals(List.of("DH-1:230000"), charges);
        assertEquals(List.of("DH-1:230000"), records);
    }

    @Test
    void rejectedPaymentMustNotBeRecorded() {
        AtomicInteger gatewayCalls = new AtomicInteger();
        AtomicInteger ledgerCalls = new AtomicInteger();

        PaymentGateway gateway = (id, amount) -> {
            gatewayCalls.incrementAndGet();
            return false;
        };
        SalesLedger ledger = (id, amount) ->
                ledgerCalls.incrementAndGet();

        CheckoutService service = new CheckoutService(gateway, ledger);

        assertFalse(service.checkout(regularOrder()));
        assertEquals(1, gatewayCalls.get());
        assertEquals(0, ledgerCalls.get());
    }

    @Test
    void invalidDataIsRejectedAtConstruction() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", -1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", 100, 0));
        assertThrows(IllegalArgumentException.class,
                () -> new Order(" ", List.of(
                        new OrderLine("X", 100, 1)), false));
        assertThrows(IllegalArgumentException.class,
                () -> new Order("O-1", List.of(), false));
    }

    @Test
    void overflowIsReportedBeforeCallingGateway() {
        Order huge = new Order("DH-HUGE", List.of(
                new OrderLine("X", Long.MAX_VALUE, 2)), false);

        AtomicInteger calls = new AtomicInteger();
        PaymentGateway gateway = (id, amount) -> {
            calls.incrementAndGet();
            return true;
        };
        SalesLedger ledger = (id, amount) ->
                fail("Ledger should not be called");

        CheckoutService service = new CheckoutService(gateway, ledger);

        assertThrows(ArithmeticException.class,
                () -> service.checkout(huge));
        assertEquals(0, calls.get());
    }

    @Test
    void inputListChangesCannotModifyOrder() {
        List<OrderLine> input = new ArrayList<>();
        input.add(new OrderLine("X", 100, 1));
        Order order = new Order("DH-3", input, false);

        input.add(new OrderLine("Y", 200, 1));

        assertEquals(100L, order.payableVnd());
    }
}
~~~

The example suite contains **7 @Test methods**. Running mvn test should complete with no failures when all listed files are copied correctly.

### Which code smells do these tests address?

| Test | Evidence provided |
| --- | --- |
| lineOwnsItsSubtotal | Each order-line calculation lives in the object owning the data |
| orderOwnsPriceAndVipRule | Pricing logic is not duplicated in CheckoutService |
| approvedPaymentIsRecordedExactlyOnce | Both dependencies receive correct data for an approved payment |
| rejectedPaymentMustNotBeRecorded | Gateway declines can be deliberately simulated |
| invalidDataIsRejectedAtConstruction | Invalid state is blocked when objects are created |
| overflowIsReportedBeforeCallingGateway | Arithmetic errors never produce invalid payment requests |
| inputListChangesCannotModifyOrder | External List changes cannot indirectly modify the object |

**Do not overinterpret tests:** These tests exercise business rules and in-memory orchestration. They do not verify real HTTP payment adapters or database ledgers, nor guarantee correct concurrent updates or distributed transactions.

## 6. Exercise 4 — Choose solutions for short code snippets

Identify the issue, impact, and fix before reading the hints. Depending on requirements, more than one solution may be reasonable.

### Scenario A — Objects with arbitrarily mutable state

~~~java
class Customer {
    public String email;
    public boolean active;
}

class CustomerService {
    void activate(Customer customer) {
        customer.active = true;
    }
}
~~~

**Question:** If activation requires a valid email, who enforces this invariant? How do public fields allow outside code to bypass validation?

**Hint:** Make fields private, add a validating constructor or email-setting method, and consider customer.activate() if the behavior genuinely belongs to Customer. Not every field needs a setter.

### Scenario B — Inheritance used only for code reuse

~~~java
class EmailSender {
    void sendEmail(String to, String message) {}
}

class OrderService extends EmailSender {
    void confirm(String address) {
        sendEmail(address, "Order confirmed");
    }
}
~~~

**Question:** Is "OrderService is a type of EmailSender" a valid relationship? Who must change if email delivery becomes SMS?

**Hint:** Compose a MessageSender interface; inject the message sender into OrderService through its constructor. Inheritance is not always wrong; the problem here is a meaningless classification relationship.

### Scenario C — A subtype violates its parent's contract

~~~java
class Bird {
    void fly() { System.out.println("Flying"); }
}
class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException();
    }
}
~~~

**Question:** Can a function accepting Bird and calling fly() safely receive Penguin?

**Hint:** Keep only genuinely common behaviors in Bird; extract Flyable for types that can fly. This indicates a Liskov Substitution Principle violation; fix the contract model instead of forcing Penguin to fly.

### Scenario D — Distinguishing object types with instanceof

~~~java
interface Discount {}
class VipDiscount implements Discount {}
class HolidayDiscount implements Discount {}

long discountAmount(Discount d, long subtotal) {
    if (d instanceof VipDiscount) {
        return subtotal / 10;
    }
    if (d instanceof HolidayDiscount) {
        return subtotal / 5;
    }
    return 0;
}
~~~

**Question:** When a discount type is added, how many instanceof branches must change? Should each strategy calculate its own discount?

**Hint:** If types share a varying behavior, declare an interface method: long discount(long subtotal), then implement it for each type. A simple switch over closed, stable inputs is not automatically a defect; assess extension frequency and who owns the rules.

### Scenario E — Hidden dependency on call order

~~~java
class ReportBuilder {
    private String title;

    void setTitle(String title) { this.title = title; }

    String render() {
        return title.toUpperCase();
    }
}
~~~

**Question:** What happens if a caller invokes render() before setTitle()? Does the design permit an invalid interim state?

**Hint:** Require title in the constructor and validate it before instantiation, or explicitly model and handle an "unset" state. Builders are not always wrong; they can help with many optional fields as long as build() validates invariants.

### Scenario F — Unnecessary abstraction

~~~java
interface AdditionStrategy {
    int add(int a, int b);
}

class StandardAddition implements AdditionStrategy {
    public int add(int a, int b) {
        return a + b;
    }
}
~~~

**Question:** When does this interface add value? If there are no alternate addition strategies or meaningful substitution boundaries, is the abstraction justified?

**Hint:** Simplify an interface that forces readers to open more files without delivering a tangible benefit. Excessive abstraction also increases maintenance costs.

## 7. Exercise 5 — Distinguish refactoring from behavioral changes

A **refactoring** change is generally expected to improve code structure while preserving behavior observable under the existing contract. Do not silently change business rules under the refactoring label.

Consider these changes:

| Change | Pure refactor? | Why? |
| --- | --- | --- |
| Move line-price calculations to OrderLine while retaining results | Yes, if data, rounding, and reported errors remain unchanged | Only responsibility placement changes |
| Change VIP discount from 10% to 15% | No | Business rule changes |
| Replace ordinary addition with Math.addExact | Possibly a bug fix/contract tightening; not necessarily behavior-preserving on overflow | Previously, overflow returned a wrong number; now it throws |
| Make a public field private and remove its getter | Potential breaking change | Callers may no longer compile |
| Inject PaymentGateway through the constructor | Usually an internal refactor | But construction signatures change, so callers must be checked |
| Reorder side-effecting steps | Depends on the contract | May break business behavior even if final results look identical |

In this example, we **both refactor the structure and improve validation and overflow handling**. Therefore, explicitly describe the contract changes: invalid input is now rejected earlier, and overflow throws. Do not claim all before/after behavior is identical for every input.

Important tests to write before editing might include:
- Regular and VIP customers with valid monetary values.
- Accepted and declined gateway responses.
- Recorded payment amounts equal the amounts submitted to the gateway.
- Input-validation and arithmetic errors after agreeing on the desired behavior.
- Both cases with and without side effects.

## 8. Exercise 6 — Review new requirements before coding

Management requests three new features:
1. Apply campaign promotion codes.
2. Switch payment gateways between test and production environments.
3. Record successful and failed transaction history.

**Task:** For both the pre-refactor and post-refactor designs, propose where to make changes. Mark any existing class at risk of becoming a **God Object** if all new features are placed together.

One possible allocation:

| Requirement | Suitable class or component | Why? |
| --- | --- | --- |
| Independent promotional policy with multiple variations | Dedicated DiscountPolicy/PricingService | Rules change on a different schedule from Order's lifecycle |
| Environment-specific payment gateway | Composition root and PaymentGateway adapters | CheckoutService does not select implementations |
| Transaction history | TransactionRepository/PaymentRecorder | Storage and retrieval responsibilities stay separate from pricing |
| Validating each order line | OrderLine | Invariants belong to each line |
| Enforcing payment step order | CheckoutService or application service | This is use-case orchestration |

If a feature needs data from multiple aggregates or calls external services, do not force it into an entity simply to "follow OOP". Put it where responsibilities and change boundaries make sense.

## 9. Assessment rubric

Assess review quality using five criteria, each worth 0 to 2 points:

| Criterion | 0 points | 1 point | 2 points |
| --- | --- | --- | --- |
| Issue identification | Only vague comments | Identifies issue but not location | Pinpoints the code region and concrete symptom |
| Consequences | No example scenario | Vague risk | Gives failing input, change, or caller |
| Solution | Arbitrarily suggests design patterns | Right direction with unnecessary dependencies | Clear responsibility and balanced complexity |
| Testing | No tests | Happy path only | Includes happy path, boundaries, errors, and invariants |
| Change assessment | Calls every change refactoring | Recognizes some differences | Distinguishes API compatibility, bug fixes, and business changes |

Maximum score: **10 points**. High scores do not depend on the number of patterns used; simple code with clear reasoning usually outperforms adding classes merely to "satisfy SOLID".

### Checklist before completing the review

- [ ] Distinguish demonstrable bugs from code smells requiring judgment.
- [ ] Cite evidence in Java for every observation.
- [ ] Identify the correct owners of data and business rules.
- [ ] Avoid inheritance or interfaces when unnecessary.
- [ ] Test successful, declined, and error/boundary paths.
- [ ] Do not hide behavioral changes under the refactoring label.
- [ ] Assess impacts on callers and external systems.
- [ ] Weigh the cost of new classes/interfaces before extracting them.

**Learning outcome:** When you encounter a class that "works but is hard to maintain", you can turn that concern into evidence-backed technical findings, propose scoped improvements, and use tests to evaluate them. These are core OOP design-review skills.
