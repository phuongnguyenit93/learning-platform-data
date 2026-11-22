# Moving Behavior to the Responsible Object in Java OOP

## 1. The Problem: Data Lives in One Class, Behavior in Another

In object-oriented programming, objects should be responsible for behavior directly related to the state and rules they own. A warning sign appears when class A repeatedly retrieves class B's data and performs calculations or decisions that naturally belong to B.

For example, a checkout service iterates over order lines, retrieves unit prices and quantities, multiplies them, adds totals, and applies an order discount. It knows too much about the order's internal structure.

This code smell is commonly called **Feature Envy**: a method is excessively interested in another object's data. A suitable refactoring is often **Move Method — relocating behavior to the object that owns the relevant information and rules**. Sometimes a large method must first be split into smaller behaviors that can move to different objects.

The goals are:
- Move line amount calculations to **OrderLine**, which knows the unit price and quantity.
- Move the total and fixed order-level discount rule to **Order**, which owns the line items and discount information.
- Keep payment-gateway calls in **CheckoutService**, whose responsibility is coordinating external interactions.
- Preserve results, errors, and tested contracts throughout the refactoring.

**There is no rule that "every method must live in the class storing the data."** Place behavior according to domain responsibility, cohesion, coupling, and expected changes.

## 2. Examining the Design Before Refactoring

The following simplified example uses two legacy-style data classes. All pricing logic lives in a service:

~~~java
import java.util.List;

record LegacyLine(String sku, long priceVnd, int quantity) {}

record LegacyOrder(
        String id,
        boolean vip,
        List<LegacyLine> lines) {}

final class LegacyCheckoutService {
    long calculatePayable(LegacyOrder order) {
        long subtotal = 0;

        for (LegacyLine line : order.lines()) {
            subtotal += line.priceVnd() * line.quantity();
        }

        if (order.vip()) {
            return subtotal - subtotal / 10;
        }
        return subtotal;
    }
}
~~~

This intentionally simplified code illustrates responsibility placement; it does not yet validate data or detect overflow. The example rule grants VIP customers **10% of the subtotal** as a discount, rounded down to whole VND.

The issue is not loop syntax. LegacyCheckoutService knows how to price line items, sum an order, and apply discounts. When OrderLine changes its calculation or the order gains a rule, the service must change even though its primary role should be checkout coordination.

A common symptom is a chain of data queries:

~~~text
service → order.lines() → line.priceVnd()
                        → line.quantity()
                        → tính toán ngoài đối tượng dữ liệu
~~~

Desired design:

~~~text
CheckoutService → Order.payableVnd()
                      ├── Order.subtotalVnd()
                      │      └── OrderLine.subtotalVnd()
                      └── Quy tắc giảm giá của đơn
~~~

The difference is that the caller asks **the object to do its own work** instead of retrieving its data and doing that work itself. This is often described by *Tell, Don't Ask*.

## 3. Identifying the Right Owner for Behavior

| Behavior | Appropriate owner | Why |
| --- | --- | --- |
| Multiply unit price by quantity | OrderLine | Both data fields and line-item invariants live there |
| Sum order lines | Order | Order owns the list of OrderLine objects |
| Calculate amount due under the order's fixed VIP discount | Order | The rule is tied to the order's VIP state in this example |
| Invoke a payment API | CheckoutService / PaymentGateway | Side effects belong to process coordination and infrastructure |
| Export an invoice as PDF or JSON | Formatter / Presenter / Serializer | External representation is distinct from pricing rules |
| Calculate campaign/coupon discounts with complex variations | A dedicated DiscountPolicy or PricingService | Those rules have lifecycles and data sources independent of Order |

**Key question:** Which object needs the least external knowledge while owning enough information and responsibility to perform the behavior correctly? If behavior spans several aggregates or performs I/O, a domain/application service may be more appropriate than an entity method.

~~~mermaid
classDiagram
    class OrderLine {
        -String sku
        -long unitPriceVnd
        -int quantity
        +subtotalVnd() long
    }
    class Order {
        -String id
        -boolean vip
        -List~OrderLine~ lines
        +subtotalVnd() long
        +payableVnd() long
    }
    class CheckoutService {
        -PaymentGateway gateway
        +checkout(Order) boolean
    }
    class PaymentGateway {
        <<interface>>
        +charge(String, long) boolean
    }
    Order "1" *-- "1..*" OrderLine
    CheckoutService --> Order : yêu cầu số tiền
    CheckoutService --> PaymentGateway : yêu cầu thanh toán
~~~

Here, Order–OrderLine expresses ownership in the domain model. Order retains an immutable copy of the list so callers cannot modify its contents through the list supplied to the constructor.

## 4. After Refactoring: Runnable Java 17 Example

The example uses JDK 17, Maven, and JUnit 5. Each public class belongs in its own file.

~~~text
move-behavior-oop/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── OrderLine.java
    │   ├── Order.java
    │   ├── PaymentGateway.java
    │   ├── CheckoutService.java
    │   └── Main.java
    └── test/java/vn/example/
        ├── OrderTest.java
        └── CheckoutServiceTest.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>move-behavior-oop</artifactId>
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

### 4.2. Move Line-Item Calculations into OrderLine

**src/main/java/vn/example/OrderLine.java**

~~~java
package vn.example;

/** Một dòng hàng có số lượng dương và đơn giá không âm. */
public record OrderLine(String sku, long unitPriceVnd, int quantity) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }

    /** Thành tiền theo VND; báo lỗi nếu vượt miền long. */
    public long subtotalVnd() {
        return Math.multiplyExact(unitPriceVnd, (long) quantity);
    }
}
~~~

Important details:

- The record preserves immutable state (record components are final).
- The quantity > 0 and unitPriceVnd >= 0 rules are enforced when creating a line item.
- OrderLine answers "what is this line item's amount?" without another class fetching its fields and multiplying them.
- Math.multiplyExact throws ArithmeticException when a product exceeds the long range; ordinary multiplication can silently wrap into positive or negative values.

We allow a unit price of 0 for complimentary items; this is **a contract choice** in the example, not a universal rule.

### 4.3. Move Totals and the VIP Rule into Order

**src/main/java/vn/example/Order.java**

~~~java
package vn.example;

import java.util.List;
import java.util.Objects;

public final class Order {
    private final String id;
    private final boolean vip;
    private final List<OrderLine> lines;

    public Order(String id, boolean vip, List<OrderLine> lines) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("order must have lines");
        }

        this.id = id;
        this.vip = vip;
        // Tạo snapshot bất biến; List.copyOf cũng từ chối phần tử null.
        this.lines = List.copyOf(lines);
    }

    public String id() {
        return id;
    }

    public long subtotalVnd() {
        long result = 0L;
        for (OrderLine line : lines) {
            result = Math.addExact(result, line.subtotalVnd());
        }
        return result;
    }

    /** VIP giảm 10%; tiền giảm làm tròn xuống VND. */
    public long payableVnd() {
        long subtotal = subtotalVnd();
        long discount = vip ? subtotal / 10 : 0L;
        return subtotal - discount;
    }
}
~~~

Order coordinates its line items to determine **its own value**. CheckoutService does not need a publicly exposed lines list to iterate. Before adding getters that expose internal state, consider their purpose: query APIs for display can be legitimate, but they should not encourage duplicating pricing rules in other classes.

In payableVnd(), integer division rounds the discount down. For a subtotal of 99 VND, VIP discount is 9 VND, leaving 90 VND due. If business rules adopt different rounding, tests should explicitly cover the change.

### 4.4. Keep Coordination in CheckoutService

**src/main/java/vn/example/PaymentGateway.java**

~~~java
package vn.example;

@FunctionalInterface
public interface PaymentGateway {
    /** true nếu chấp nhận thanh toán, false nếu từ chối. */
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/vn/example/CheckoutService.java**

~~~java
package vn.example;

import java.util.Objects;

public final class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    public boolean checkout(Order order) {
        Objects.requireNonNull(order, "order");
        return gateway.charge(order.id(), order.payableVnd());
    }
}
~~~

CheckoutService retains one clear responsibility: coordinating payment. It contains no multiplication, subtotal loops, or VIP branches. In unit tests, a different PaymentGateway implementation can be injected instead of a real payment integration.

**src/main/java/vn/example/Main.java**

~~~java
package vn.example;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        Order order = new Order(
                "DH-100",
                true,
                List.of(
                        new OrderLine("BOOK", 100_000, 2),
                        new OrderLine("PEN", 30_000, 1)));

        PaymentGateway demoGateway = (id, amount) -> {
            System.out.println(
                    "Payment request: " + id + " = " + amount + " VND");
            return true;
        };

        CheckoutService service = new CheckoutService(demoGateway);

        System.out.println("Subtotal: " + order.subtotalVnd());
        System.out.println("Payable: " + order.payableVnd());
        System.out.println("Accepted: " + service.checkout(order));
    }
}
~~~

Run from the project directory:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.Main
~~~

Expected output:

~~~text
Subtotal: 230000
Payable: 207000
Payment request: DH-100 = 207000 VND
Accepted: true
~~~

In the demo, PaymentGateway only prints information and returns true; it does not perform a real payment. Order determines the amount payable, while the coordinator communicates only with the payment gateway.

## 5. Writing Tests to Protect Behavior When Moving Methods

True refactoring preserves externally observable behavior under **the chosen contract**. Before moving code in an existing project, establish characterization tests for current values and branches. Object-level and workflow-level tests must continue passing after the move.

**src/test/java/vn/example/OrderTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderTest {
    @Test
    void subtotalComesFromOrderLines() {
        Order order = new Order("O-1", false, List.of(
                new OrderLine("A", 100_000, 2),
                new OrderLine("B", 30_000, 1)));

        assertEquals(230_000L, order.subtotalVnd());
        assertEquals(230_000L, order.payableVnd());
    }

    @Test
    void vipDiscountIsAppliedOnceAtOrderLevel() {
        Order order = new Order("O-2", true, List.of(
                new OrderLine("A", 100_000, 2),
                new OrderLine("B", 30_000, 1)));

        assertEquals(230_000L, order.subtotalVnd());
        assertEquals(207_000L, order.payableVnd());
    }

    @Test
    void fractionalDiscountIsRoundedDownInVnd() {
        Order order = new Order("O-3", true, List.of(
                new OrderLine("A", 99, 1)));

        assertEquals(99L, order.subtotalVnd());
        assertEquals(90L, order.payableVnd());
    }

    @Test
    void orderDoesNotChangeWhenInputListChanges() {
        List<OrderLine> input = new ArrayList<>();
        input.add(new OrderLine("A", 100, 1));

        Order order = new Order("O-4", false, input);
        input.add(new OrderLine("B", 200, 1));

        assertEquals(100L, order.payableVnd());
    }

    @Test
    void validatesItsOwnInvariants() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", -1, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", 10, 0));
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine(" ", 10, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new Order("O-5", false, List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> new Order("", false,
                        List.of(new OrderLine("X", 1, 1))));
    }

    @Test
    void rejectsOverflowInsteadOfSilentlyWrapping() {
        OrderLine line = new OrderLine("X", Long.MAX_VALUE, 2);
        assertThrows(ArithmeticException.class, line::subtotalVnd);

        Order order = new Order("O-6", false, List.of(
                new OrderLine("A", Long.MAX_VALUE, 1),
                new OrderLine("B", 1, 1)));

        assertThrows(ArithmeticException.class, order::subtotalVnd);
    }
}
~~~

**src/test/java/vn/example/CheckoutServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void passesComputedAmountToGatewayExactlyOnce() {
        List<String> calls = new ArrayList<>();
        PaymentGateway gateway = (id, amount) -> {
            calls.add(id + ":" + amount);
            return true;
        };

        Order order = new Order("DH-100", true, List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)));

        CheckoutService service = new CheckoutService(gateway);

        assertTrue(service.checkout(order));
        assertEquals(List.of("DH-100:207000"), calls);
    }

    @Test
    void preservesPaymentRejection() {
        List<Long> charged = new ArrayList<>();
        PaymentGateway gateway = (id, amount) -> {
            charged.add(amount);
            return false;
        };

        Order order = new Order("DH-101", false, List.of(
                new OrderLine("PEN", 30_000, 2)));

        assertFalse(new CheckoutService(gateway).checkout(order));
        assertEquals(List.of(60_000L), charged);
    }

    @Test
    void nullOrderIsRejectedBeforeCallingGateway() {
        List<String> calls = new ArrayList<>();
        PaymentGateway gateway = (id, amount) -> {
            calls.add(id);
            return true;
        };

        CheckoutService service = new CheckoutService(gateway);

        assertThrows(NullPointerException.class,
                () -> service.checkout(null));
        assertTrue(calls.isEmpty());
    }
}
~~~

These are **9 @Test methods** (6 for Order and 3 for CheckoutService). With the Maven structure above, the suite is expected to run 9 tests without failures/errors.

Order-level tests show that responsibilities moved to the right place and calculations remain correct. CheckoutService tests confirm that the external workflow still uses the right amount and order ID and avoids gateway calls in invalid cases. Tests need no access to Order's private fields.

| Test | Responsibility verified | Possible defect detected |
| --- | --- | --- |
| subtotalComesFromOrderLines | Order sums amounts from OrderLine | Missing a line or multiplying by the wrong quantity |
| vipDiscountIsAppliedOnceAtOrderLevel | Apply the 10% discount once to the whole order | Duplicate discount or wrong scope |
| fractionalDiscountIsRoundedDownInVnd | Preserve contractual rounding | A 1 VND boundary error |
| orderDoesNotChangeWhenInputListChanges | Encapsulation and immutable snapshots | External changes modifying the order |
| validatesItsOwnInvariants | Invariants enforced by the data owner | Invalid data reaching later workflow stages |
| rejectsOverflowInsteadOfSilentlyWrapping | Overflow-checked calculations | Negative line amounts from overflow |
| passesComputedAmountToGatewayExactlyOnce | Preserve coordination after refactoring | Sending an old amount or invoking the gateway repeatedly |
| preservesPaymentRejection | Preserve result semantics | Changing false into true |
| nullOrderIsRejectedBeforeCallingGateway | Avoid side effects for null input | Calling dependencies with invalid data |

## 6. Safe Refactoring Steps in an Existing System

Use small, verifiable changes:

1. **Locate the behavior.** Find methods that read many fields on another object. Determine which data drives their calculations/decisions and whether they perform I/O.
2. **Establish the old contract.** Write or preserve tests for normal cases, boundaries, errors, rounding, and important callers. For monetary calculations, test overflow and currency units.
3. **Create a method on the target object.** Start with OrderLine.subtotalVnd(), letting the old method delegate to it so each move can be verified.
4. **Move aggregation logic.** Add Order.subtotalVnd() and then Order.payableVnd(). Remove pricing calculations from the coordinator.
5. **Update callers.** Have CheckoutService ask order.payableVnd() instead of iterating over order.lines() and checking VIP state.
6. **Test each step.** Preserve results, interaction counts, exceptions, and rounding rules throughout the move.
7. **Retire old entry points.** For public APIs, temporarily retain a delegating adapter during migration; remove duplicate calculations once callers have migrated and compatibility no longer requires them. For private APIs, delete them after confirming there are no callers.
8. **Reassess the design.** Check coupling, cohesion, object lifecycles, data mutation ownership, and whether the target method really understands the business rule.

Prefer incremental steps over moving a large code block at once. Java IDEs support *Move Instance Method*, but automated tools do not fully understand business boundaries: tests and API review remain necessary.

~~~mermaid
flowchart TD
    A["Phát hiện Feature Envy"] --> B["Xác định dữ liệu và chủ sở hữu quy tắc"]
    B --> C["Chốt test hành vi hiện tại"]
    C --> D["Chuyển phép tính nhỏ vào OrderLine"]
    D --> E["Chuyển tổng hợp vào Order"]
    E --> F["Đổi CheckoutService thành điều phối"]
    F --> G["Chạy test và rà soát caller"]
    G --> H{"Giữ hợp đồng?"}
    H -->|Không| I["Sửa sai lệch, kiểm tra biên"]
    I --> G
    H -->|Có| J["Dọn phương thức trùng và kết thúc"]
~~~

## 7. Connections to OOP Principles

**Encapsulation.** An object can protect invariants by operating on data it owns. Callers need not know whether line items are stored in an ArrayList, immutable structure, or lazy-loaded collection.

**High Cohesion.** Line amounts are calculated beside unit prices and quantities. Order totals belong with the complete order. Related changes tend to remain localized in the appropriate class.

**Low Coupling.** CheckoutService depends only on Order's concise business API—id() and payableVnd()—rather than individual line-item getters and VIP rules. Moving many lines to another object without reducing how much data callers must inspect does not meaningfully reduce coupling.

**Single Responsibility Principle (SRP).** Changes to line-item values belong to OrderLine, basic order-total rules belong to Order, and payment-workflow changes belong to CheckoutService. SRP does not mean one method per class.

**Information Expert (a GRASP principle).** Assign responsibility to an object with the information needed to perform it. This guides method placement but must be balanced against transaction, security, authorization, performance, and domain boundaries.

**Tell, Don't Ask.** Invoke meaningful behavior such as order.payableVnd() rather than retrieving all data and inferring the result. However, query APIs for UIs, reports, or serialization are legitimate; not every getter is a code smell.

## 8. When Should You NOT Move a Method?

| Situation | Why not move it hastily? | Alternative |
| --- | --- | --- |
| Behavior uses several peer domain objects | No natural single owner for the entire rule | Dedicated domain service / policy |
| Algorithm depends on network APIs, databases, or email | An entity would acquire I/O dependencies and complicate transactions | Application service or adapter |
| Promotional rules change frequently and require multiple strategies | Packing every condition into Order makes the class bloated | DiscountPolicy / Strategy |
| Screen formatting or file export | Domain objects become coupled to presentation | Presenter / formatter |
| Moving causes circular dependencies | Cohesion may decrease and comprehension worsen | Extract a collaborator or revisit boundaries |
| A method reads extensive data from two large aggregates | May over-fetch data or violate transaction boundaries | Query service, domain service, or dedicated DTO |
| Logic genuinely depends on source-object state | Moving it makes the destination depend back on the source | Keep it at the source or extract a smaller component |

A practical rule: **move behavior that shares a reason to change, not every method that happens to use many getters**.

For example, if discounts depend on campaign codes across multiple systems, moving all campaign logic into Order would couple it to coupon APIs. A better choice may be for PricingPolicy to calculate the discount, Order to maintain order invariants, and CheckoutService to coordinate the necessary steps.

## 9. Extension Exercises

**Exercise 1 — Find misplaced behavior.** Suppose ReportService iterates over OrderLine objects to count products. Distinguish two needs:
- For the total quantity in **one order**, consider Order.totalQuantity().
- For the total quantity sold **over a period across multiple orders**, a report/query service may be the right owner.

**Exercise 2 — Refactor a cart.** Create CartItem(price, quantity) and Cart(items). Initially, CartService calculates totals; then move per-line calculations into CartItem and aggregation into Cart. Test empty carts, invalid quantities, overflow, and modifications to the supplied list.

**Exercise 3 — Changing discount policies.** Add a DiscountPolicy interface with a method that calculates discounts. Design Order to aggregate amounts while a dedicated object handles discount policy. Specify which policy is supplied at construction or pricing time, and avoid storing prices that become stale.

**Exercise 4 — API migration.** If another module still calls PriceService.calculatePayable(order), temporarily retain the old method delegating to order.payableVnd(), mark it deprecated when appropriate, migrate callers, and remove it once compatibility impact is checked.

**Self-assessment:** After refactoring, behavior primarily belongs to the object whose data it uses; coordinators know fewer internal details; tests preserve external behavior; and no new circular dependencies or domain-object I/O coupling appear.
