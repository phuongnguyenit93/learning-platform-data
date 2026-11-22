# Combining Records, Enums, and Interfaces to Model a Data Domain

When modeling a business domain, we often need to represent data, constrain valid values, and define behaviors that multiple types can provide in common. In Java 17+, **record**, **enum**, and **interface** handle three different tasks and can work together in the same model.

- **Record** is suited for data with defined components, such as an order line or an order. Java automatically generates accessors, equals, hashCode, and toString; a record is also a final type.
- **Enum** represents a finite, named set of values known at compile time, such as an order status or a shipping method. Each enum constant can carry data and implement its own behavior.
- **Interface** describes a capability or contract that multiple types can implement. A record or enum can implement multiple interfaces to be used through the same abstract type.

Do not use a single one of these three constructs for every purpose. Choose based on the nature of the data and business rules, and combine them when those responsibilities intersect.

## 1. Separating Data, Sets of Choices, and Contracts

Suppose an application needs to model an online order.

| Component | Role in the business domain |
|---|---|
| OrderLine (record) | Item code, quantity, unit price; computes its own line amount |
| Order (record) | Order ID, order lines, shipping method, and status |
| ShippingMethod (enum) | Set of supported shipping methods, each with a fee and estimated time |
| OrderStatus (enum) | Set of valid statuses and state transition rules |
| LineAmount (interface) | Contract for an object that can compute a line amount |
| Labeled (interface) | Contract providing a display label for multiple business domain types |

This model has two benefits. First, records group related data into a clear value. Second, enums keep bounded choices in one place and can attach behavior to each choice. Interfaces allow callers to work with the capability an object provides instead of depending on a concrete class.

## 2. Complete Example Running on Java 17+

Save all of the following code to the file **OrderDomainDemo.java**. The supporting interfaces, records, and enums are declared at the top level with package scope; the public class OrderDomainDemo is the entry point of the program.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

interface Labeled {
    String label();
}

interface LineAmount {
    BigDecimal amount();
}

record OrderLine(String sku, int quantity, BigDecimal unitPrice)
        implements LineAmount {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }
    }

    @Override
    public BigDecimal amount() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

enum ShippingMethod implements Labeled {
    STANDARD("Standard", new BigDecimal("3.50"), 5),
    EXPRESS("Express", new BigDecimal("9.00"), 2);

    private final String label;
    private final BigDecimal fee;
    private final int deliveryDays;

    ShippingMethod(String label, BigDecimal fee, int deliveryDays) {
        this.label = label;
        this.fee = fee;
        this.deliveryDays = deliveryDays;
    }

    @Override
    public String label() {
        return label;
    }

    public BigDecimal fee() {
        return fee;
    }

    public int deliveryDays() {
        return deliveryDays;
    }
}

enum OrderStatus implements Labeled {
    DRAFT("Draft"),
    PAID("Paid"),
    SHIPPED("Shipped"),
    CANCELLED("Cancelled");

    private final String label;

    OrderStatus(String label) {
        this.label = label;
    }

    @Override
    public String label() {
        return label;
    }

    public boolean canTransitionTo(OrderStatus next) {
        Objects.requireNonNull(next, "next");

        return switch (this) {
            case DRAFT -> next == PAID || next == CANCELLED;
            case PAID -> next == SHIPPED || next == CANCELLED;
            case SHIPPED, CANCELLED -> false;
        };
    }
}

record Order(
        String id,
        List<OrderLine> lines,
        ShippingMethod shippingMethod,
        OrderStatus status
) implements Labeled {
    public Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(shippingMethod, "shippingMethod");
        Objects.requireNonNull(status, "status");

        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }

        // Make a defensive, unmodifiable copy of the supplied list.
        lines = List.copyOf(lines);
    }

    public BigDecimal subtotal() {
        return lines.stream()
                .map(OrderLine::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public BigDecimal total() {
        return subtotal().add(shippingMethod.fee());
    }

    @Override
    public String label() {
        return id + " - " + status.label();
    }

    public Order withStatus(OrderStatus next) {
        if (!status.canTransitionTo(next)) {
            throw new IllegalStateException(
                    "Cannot transition from " + status + " to " + next);
        }

        // Records are immutable values: return a new Order with the new status.
        return new Order(id, lines, shippingMethod, next);
    }
}

public class OrderDomainDemo {
    public static void main(String[] args) {
        Order order = new Order(
                "ORD-1001",
                List.of(
                        new OrderLine("BOOK-JAVA", 2, new BigDecimal("19.90")),
                        new OrderLine("MUG", 1, new BigDecimal("8.50"))
                ),
                ShippingMethod.EXPRESS,
                OrderStatus.PAID
        );

        System.out.println("Order: " + order.label());
        System.out.println("Items: " + order.lines().size());
        System.out.println("Subtotal: " + order.subtotal().setScale(2));
        System.out.println("Shipping: " + order.shippingMethod().label()
                + " (" + order.shippingMethod().deliveryDays()
                + " days) = " + order.shippingMethod().fee().setScale(2));
        System.out.println("Total: " + order.total().setScale(2));
        System.out.println("Transition: "
                + order.withStatus(OrderStatus.SHIPPED).label());

        List<Labeled> labels = List.of(
                order.status(),
                order.shippingMethod(),
                order
        );
        System.out.println("Labels through interface:");
        for (Labeled value : labels) {
            System.out.println("- " + value.label());
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac OrderDomainDemo.java
java OrderDomainDemo
~~~

Expected output:

~~~text
Order: ORD-1001 - Paid
Items: 2
Subtotal: 48.30
Shipping: Express (2 days) = 9.00
Total: 57.30
Transition: ORD-1001 - Shipped
Labels through interface:
- Paid
- Express
- ORD-1001 - Paid
~~~

## 3. Why Do These Types Work Together?

### Records Hold Data and Protect Basic Invariants

OrderLine groups an item code, quantity, and unit price into a single value. A compact constructor allows validating input data without rewriting all field assignments. Once the constructor finishes, the record components cannot be reassigned; Java automatically provides accessors such as sku(), quantity(), and unitPrice().

Order contains a list of order lines, a shipping method, and a status. List.copyOf creates an unmodifiable copy of the input list, so the caller cannot modify the original list and thereby change the contents of Order. This is **shallow immutability**: if a record holds a mutable object without copying or protecting it, the internal state can still be modified. In this example, OrderLine is also a record and BigDecimal is immutable, so the order line data is suited to that usage.

Records do not automatically check every business rule. The constructors in the example check the order ID, quantity, unit price, and empty list. Rules that depend on stored data, the current user, or external systems generally need to be checked in the appropriate business layer.

### Enums Represent Finite Choices and Attach Behavior to Choices

ShippingMethod has two predefined constants: STANDARD and EXPRESS. Each constant has a label, a fee, and an estimated number of delivery days. When adding a new shipping method, we add the constant and its associated values in one place instead of passing free-form strings like "express" throughout the application.

OrderStatus is also a finite set of states. The canTransitionTo method centralizes the state transition rules: an order in DRAFT can transition to PAID or CANCELLED; an order in PAID can transition to SHIPPED or CANCELLED; SHIPPED and CANCELLED are terminal states in this illustrative model. Order.withStatus uses that rule to reject invalid transitions and return a new Order when the transition is valid.

These are example rules to illustrate modeling, not a workflow suited to every system. Real-world business logic may require additional states, payment conditions, user permissions, concurrency control, and storing state transition history.

### Interfaces Describe Shared Capabilities

LineAmount requires only a single method, amount(). OrderLine implements this contract by multiplying the unit price by the quantity. Code that computes the total can call amount() without needing to know how each kind of order line calculates its amount.

Labeled requires label(). OrderStatus, ShippingMethod, and Order all implement that interface. Because of this, the program can place objects of different types into a List&lt;Labeled&gt; and process them all in the same way. This is polymorphism: the calling code relies on a shared contract, while the method that executes depends on the actual object type.

An interface does not store object state like a record does. It primarily defines the operations that an implementing type commits to providing. Records and enums still hold the data, while interfaces allow those types to be used through a stable contract.

## 4. Limitations to Keep in Mind

- **Records are final.** You cannot create a subclass of Order or OrderLine. If you need a type hierarchy, consider an interface or another more suitable design.
- **Enums cannot extend arbitrary business domain classes.** Every enum already extends java.lang.Enum, though it can implement one or more interfaces. Use an enum when the set of choices is truly finite and controlled.
- **Interfaces do not guarantee that every rule is implemented correctly.** An interface guarantees that an implementing type provides the declared methods; the correctness of the implementation still needs to be designed and tested.
- **Records do not automatically create deep copies.** Reference components can still point to mutable objects. Use immutable types or defensive copying when you need to ensure data does not change.
- **Do not use double for exact monetary calculations.** The example uses BigDecimal and constructs values from decimal strings. Real-world systems also need to define currency units, rounding rules, taxes, discounts, and how monetary amounts are stored.
- **Do not let enums become the place for all logic.** Behavior directly tied to a finite choice is usually reasonable; complex workflows that depend on multiple services should be placed in the appropriate business component.

## 5. How to Decide in a New Model

1. Identify what data forms a clearly structured value. If the value primarily consists of defined components and does not need its own mutable identity, consider a record.
2. Identify whether the choices form a finite, stable set. If so, an enum helps avoid arbitrary strings and centralizes the data or behavior associated with each choice.
3. Identify which operations multiple types need to provide. If callers only need to know about that capability, express it with an interface.
4. Place invariant checks where values are created; place state transition rules in the model or business service that has enough information to decide.
5. Test both valid and invalid paths: invalid input data, forbidden state transitions, totals, and polymorphic behavior through interfaces.

Combining them properly makes the data domain model easier to read: records clarify the data, enums constrain known choices, and interfaces allow multiple types to provide a common behavior. Each construct has its own responsibility, making it easier to identify where edits are needed when business changes occur.
