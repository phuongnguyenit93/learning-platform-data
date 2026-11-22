# Choosing Class Responsibilities Before Choosing Fields and Methods in Java

## 1. The Most Important Mindset

When starting to write Java, it is very easy to follow this sequence: come up with a class name → add a few fields → generate getters/setters → add methods to use those fields. This approach can produce a syntactically valid class that **has no clear reason to exist**, or pushes business rules outside the object that owns the data.

A generally better design order is:

1. Understand the **business problem and outcome** that the software must produce.
2. Identify **responsibilities**: who knows what, who gets to decide what, and who coordinates with whom.
3. Find **change boundaries**, *cohesion*, *coupling*, and data ownership.
4. Choose the **class/interface/record/service** suited to that responsibility.
5. From the responsibilities, determine the **invariants**, the minimum state to retain, and the behavior to expose.
6. **Last of all**, design fields, constructors, methods, access modifiers, and tests.

For example, if a shopping cart needs to “add a product with a valid quantity and calculate the total,” you should first ask **who protects the quantity**, **where the price lives**, **who owns the line items**, and **who decides the final price**, before immediately creating fields like `name`, `count`, `total` or methods like `setCount()`, `setTotal()`.

> **Principle:** A class is a place that brings together **data and behavior serving a meaningful responsibility**; it is not merely a bag of fields or a random list of methods.

This content belongs to the Java Core – Class/Object module, focusing on practical object-oriented design. Standalone examples include file names, `javac`/`java` commands for Java 17+, and deterministic output. Code snippets intended only for discussion are explicitly marked as illustrative.

## 2. What Is a “Class Responsibility” Really?

A responsibility is **an obligation of an object or software component** toward the system. It can be:

- **Knowing** a meaningful piece of state: an account knows its own balance.
- **Protecting invariants**: a line item's quantity must be greater than 0.
- **Performing behavior**: a shopping cart adds/removes products and calculates the total.
- **Making policy-based decisions**: a fee calculator determines surcharges based on a strategy.
- **Coordinating**: an application service receives requests, calls domain objects, and persists the results.
- **Integrating**: a repository accesses storage; a gateway sends messages to an external system.
- **Representing values**: a Money, Address, or DateRange checks validity and carries value semantics.

A useful question:

> “If this responsibility is performed incorrectly, **which object/component** must be modified because it is the natural owner of the rule?”

For instance, if a negative item quantity slips into an Order, that is usually an issue in the class representing the item/order or the item creation/addition behavior, rather than something that should rely on every caller remembering to check it themselves.

### Responsibilities Differ from Technical Operations

“Having a `setX` method,” “having a field `x`,” or “having a getter” are not good business descriptions. “Maintaining a non-negative balance,” “calculating the amount payable,” and “ensuring a submitted order cannot be modified” are verifiable responsibilities.

## 3. Start from Use Cases, Not from a Field Diagram

Suppose the requirement is:

> “A buyer can add products to the cart; the quantity must be positive. The cart displays the total amount. Upon checkout, the system records the order and sends a confirmation notification.”

Before writing Java, break it down into decision groups:

| Business Question | Candidate Responsibility |
| --- | --- |
| How is a product identified? | ProductId/Product |
| Is the unit price valid? | Money or product pricing representation |
| What quantity must a line item have? | CartLine/Cart |
| Who owns the cart lines? | ShoppingCart |
| Who calculates the total from the lines? | ShoppingCart or PriceCalculator, depending on pricing rules |
| Who saves the order to the database? | OrderRepository |
| Who sends email/SMS? | NotificationGateway |
| Who coordinates checkout across multiple components? | CheckoutService |
| Who formats HTML/JSON? | Presentation/serializer component |

This is a **candidate list**, not a mandatory decision to create nine classes. In a small exercise, a few responsibilities may reasonably live together; in a large system, they should be separated by **genuinely different reasons to change**.

Do not choose the number of classes based on the number of nouns in the specification. Look for responsibilities that need protection, reuse, or independent change.

## 4. Ask About “Reasons to Change” to Identify Boundaries

The Single Responsibility Principle (SRP) is often explained as: a class should have **one cohesive reason to change**. It should not be interpreted mechanically to mean that a class may only have one method or one operation.

For example:

- The rule “quantity must be positive” changes due to the sales domain.
- Invoice formatting changes due to UI requirements.
- Email sending changes due to the service provider.
- Database schema changes due to the database.
- The VAT formula changes due to tax policy.

If a class simultaneously guards quantity, writes SQL, generates HTML, and sends SMTP, it is subject to **multiple unrelated kinds of change**.

### Signs a Class Has Too Broad a Responsibility

- When modifying the UI, you have to modify the domain class.
- When changing the database, you have to modify the total-price logic.
- Unit testing a small rule requires opening a real network connection or database.
- The constructor requires many dependencies that do not share the same goal.
- Methods use nearly disjoint groups of fields.
- A reader cannot describe the class in a single clear sentence.

However, **multiple methods supporting the same invariant** can still belong to a class with a sound responsibility.

## 5. Anti-Example: One Class Doing Everything

This is an **illustrative code snippet** of a hard-to-maintain design; it has no actual services to run:

```java
class OrderManager {
    String customerEmail;
    java.util.List<String> productIds;
    int[] quantities;

    void validateQuantities() { /* domain rules */ }
    int computePrice() { /* pricing */ return 0; }
    void saveJdbc() { /* database */ }
    void sendSmtp() { /* network */ }
    String renderHtml() { /* presentation */ return ""; }
}
```

The problems:

1. A single object handles **business rules, persistence, network, and UI formatting**.
2. Multiple fields can easily be put into an inconsistent state: the product IDs list and quantities can have mismatched element counts.
3. `computePrice()` returns an integer without making the currency unit clear.
4. Tests have difficulty isolating behavior; changing one provider affects the main class.
5. It is unclear who owns the lifecycle of the connection/email client.
6. Whenever a new feature appears, every developer tends to add more to OrderManager.

**The fix is not simply renaming it** to `OrderService`. You need to draw boundaries around “who knows,” “who decides,” and “who persists/sends,” then move state and behavior to their proper owners.

## 6. Small Version: An Object Maintaining Exactly One Invariant

Start with a simple requirement: an order line has an **item name**, a **non-negative unit price**, and a **positive quantity**; the subtotal is calculated from those two values.

Create **`OrderLineResponsibilityDemo.java`**:

```java
import java.util.Objects;

final class OrderLine {
    private final String item;
    private final int unitPrice;
    private final int quantity;

    OrderLine(String item, int unitPrice, int quantity) {
        this.item = Objects.requireNonNull(item);
        if (item.isBlank()) {
            throw new IllegalArgumentException("blank item");
        }
        if (unitPrice < 0) {
            throw new IllegalArgumentException("negative price");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("invalid quantity");
        }
        this.unitPrice = unitPrice;
        this.quantity = quantity;
    }

    String item() {
        return item;
    }

    int quantity() {
        return quantity;
    }

    int subtotal() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}

public class OrderLineResponsibilityDemo {
    public static void main(String[] args) {
        OrderLine line = new OrderLine("Notebook", 12, 3);

        System.out.println(line.item());
        System.out.println(line.quantity());
        System.out.println(line.subtotal());
    }
}
```

```bash
javac OrderLineResponsibilityDemo.java
java OrderLineResponsibilityDemo
```

```text
Notebook
3
36
```

### Why Is This a Clear Responsibility?

`OrderLine` has a clear meaning: **representing a valid order line and providing the value calculated from that line**. The fields exist because they are needed to fulfill that responsibility, not because of anticipating lots of getters/setters.

- `item`: the identity/label of the line.
- `unitPrice`: the price used when calculating the subtotal.
- `quantity`: the number of units.
- `subtotal()`: behavior consistent with the state.
- Constructor: the boundary ensuring the object cannot be created in an invalid state.

The example uses integers as the smallest currency unit for instructional purposes; a real system needs to specify currency, overflow handling, and pricing policy. `Math.multiplyExact` helps avoid silent integer overflow.

## 7. Why Not Create `setQuantity()` Just Because There Is a quantity Field?

If all fields have public setters, a caller can put the object into an invalid state:

```java
// line.setQuantity(-100);
// line.setUnitPrice(-5);
```

These are illustrative calls to setters that **do not exist** in the OrderLine design above.

If the business logic **allows changing the quantity**, add meaningful behavior and enforce constraints:

```java
void changeQuantity(int nextQuantity) {
    if (nextQuantity <= 0) {
        throw new IllegalArgumentException("invalid quantity");
    }
    this.quantity = nextQuantity;
}
```

This is a **method snippet** for a version of OrderLine whose quantity field is **non-final**. Do not insert it verbatim into the previous class because the previous class is intentionally immutable.

**Questions before adding a setter:** “Who is allowed to change it? When can it be changed? Is it still allowed after payment? Does changing one field require updating other fields?” The answers determine the **method semantics and state model**, not an IDE generator.

## 8. Responsibilities Lead to Invariants, and Invariants Lead to Fields

One way to write down a design:

```text
Responsibility:
  "The cart owns the order lines and calculates the total"

Invariants:
  "No line with quantity <= 0"
  "Do not expose the mutable internal collection"
  "Total = sum of line subtotals"

Minimum state:
  List<OrderLine> lines

Methods:
  addLine(...)
  total()
  lines() returns a snapshot
```

This diagram is a **model**, not runnable Java.

If the total can be calculated from lines at any time, there is no need to store a `cachedTotal` field. Storing derived values should only be done when there is a proven performance need and a consistent invalidation mechanism.

### Avoid Duplicate State

If you have `List<OrderLine>` along with both `int itemCount` and `int total`, every change to lines must also synchronize two additional fields. This increases the number of invariants that must be maintained. Starting from the minimum state is usually easier to get right.

## 9. Complete Program: Cart Is the Owner of lines

Create **`ShoppingCartResponsibilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record CartLine(String item, int unitPrice, int quantity) {
    CartLine {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("item");
        }
        if (unitPrice < 0 || quantity <= 0) {
            throw new IllegalArgumentException("price/quantity");
        }
    }

    int subtotal() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}

final class ShoppingCart {
    private final List<CartLine> lines = new ArrayList<>();

    void add(String item, int unitPrice, int quantity) {
        lines.add(new CartLine(item, unitPrice, quantity));
    }

    int total() {
        int result = 0;
        for (CartLine line : lines) {
            result = Math.addExact(result, line.subtotal());
        }
        return result;
    }

    List<CartLine> lines() {
        return List.copyOf(lines);
    }
}

public class ShoppingCartResponsibilityDemo {
    public static void main(String[] args) {
        ShoppingCart cart = new ShoppingCart();
        cart.add("Pen", 3, 2);
        cart.add("Book", 10, 1);

        System.out.println(cart.total());
        System.out.println(cart.lines().size());

        try {
            cart.lines().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot cannot be cleared");
        }

        System.out.println(cart.lines().size());
    }
}
```

```bash
javac ShoppingCartResponsibilityDemo.java
java ShoppingCartResponsibilityDemo
```

```text
16
2
snapshot cannot be cleared
2
```

**Separation of responsibilities:**

- `CartLine` represents a valid line item and calculates its own subtotal.
- `ShoppingCart` owns the collection, adds lines, and calculates the total from the lines.
- Callers cannot directly modify the internal list through the accessor because `List.copyOf` returns an unmodifiable collection.
- The CartLine record has primitive/String components, so it does not hold any mutable element requiring a deep defensive copy.
- `Math.addExact`/`multiplyExact` prevents the example from silently overflowing.

**Limitations:** This is a simple cart with no currency, taxes, promotions, inventory reservations, or concurrent updates. Do not try to cram every policy into CartLine before an actual use case exists.

## 10. Owner Boundary: Who Gets to Protect the Data?

Suppose Cart has the field:

```java
private final List<CartLine> lines = new ArrayList<>();
```

If it returns the reference directly:

```java
List<CartLine> lines() {
    return lines;
}
```

the caller can `clear()`, `add(null)`, or make modifications that Cart has not validated. That causes the responsibility “Cart maintains valid lines” to no longer belong to Cart.

**A criterion for choosing fields/methods:** If a class owns a collection's invariant, it must also own the **mutation path**. The API can allow reading a snapshot/copy or an unmodifiable view depending on the contract, but do not expose mutable internals if the class needs to control its state.

### Distinguishing a Snapshot from a View

`List.copyOf(lines)` gives an unmodifiable snapshot structure at the time of the call. `Collections.unmodifiableList(lines)` returns a view that prevents callers from mutating through the view, but **still reflects subsequent changes to the original list**.

Choose based on the API semantics: do you need a snapshot at the moment of the call, or do you want a read-only observation of the current state?

## 11. Cohesion: Do the Methods Serve the Same Goal?

A class has good cohesion when its members contribute to serving a consistent responsibility.

For example, a `TemperatureRange` might have:

- `contains(value)`
- `overlaps(other)`
- `span()`
- `lower()/upper()`

Even though there are four methods, they all relate to the temperature range and share the same min/max invariants.

Conversely, adding `sendEmail()` to TemperatureRange changes the class's reason to exist: sending email belongs to an infrastructure/notification concern, not to the representation of a temperature range.

### “One Responsibility” Does Not Mean “Only One Method”

The ShoppingCart class can have `add`, `remove`, `clear`, `total`, `itemCount`, and other reasonable business behaviors while remaining cohesive, because they all serve the cart's state and lifecycle.

You should not split it into `CartAddManager`, `CartRemoveManager`, and `CartCountManager` just to give each class a single method. That is **over-fragmentation**: increasing the number of components and coupling without creating genuine responsibility boundaries.

## 12. Coupling: Why Should You Consider Dependencies?

**Coupling** is the degree to which one class knows about and depends on other classes. A domain class that depends directly on JDBC, SMTP, and an HTTP controller framework will be hard to change and hard to test.

Example with high coupling:

```java
class Invoice {
    void saveToDatabase() {
        // JDBC details
    }

    void sendByEmail() {
        // SMTP details
    }
}
```

This is a **design illustration**, not a complete implementation.

When the email provider changes, Invoice must be modified; when the database changes, Invoice must also be modified. Infrastructure changes should not alter the responsibility “an invoice represents the amount payable.”

### One Way to Draw Boundaries

- `Invoice`: knows the invoice's data and value rules.
- `InvoiceRepository`: the contract for retrieving/persisting an Invoice.
- `NotificationSender`: the contract for sending notifications.
- `CheckoutService`: coordinates the workflow using the invoice/repository/sender.

**Avoid extremes:** For a small script that only prints one result, there is no need to create multiple interfaces and services. Separate them when reasons to change, tests, or deployment boundaries truly add value.

## 13. Program: Separating Pricing Logic from Notification

Create **`SeparationOfResponsibilitiesDemo.java`**:

```java
import java.util.List;

record Line(String name, int price, int quantity) {
    Line {
        if (price < 0 || quantity <= 0) {
            throw new IllegalArgumentException("line");
        }
    }

    int amount() {
        return Math.multiplyExact(price, quantity);
    }
}

final class Invoice {
    private final List<Line> lines;

    Invoice(List<Line> lines) {
        this.lines = List.copyOf(lines);
    }

    int total() {
        int sum = 0;
        for (Line line : lines) {
            sum = Math.addExact(sum, line.amount());
        }
        return sum;
    }
}

interface ReceiptSender {
    void send(int total);
}

final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void send(int total) {
        System.out.println("receipt:" + total);
    }
}

final class CheckoutService {
    private final ReceiptSender sender;

    CheckoutService(ReceiptSender sender) {
        this.sender = sender;
    }

    void checkout(Invoice invoice) {
        int total = invoice.total();
        sender.send(total);
    }
}

public class SeparationOfResponsibilitiesDemo {
    public static void main(String[] args) {
        Invoice invoice = new Invoice(List.of(
                new Line("Notebook", 8, 2),
                new Line("Pen", 2, 3)
        ));

        CheckoutService checkout =
                new CheckoutService(new ConsoleReceiptSender());

        checkout.checkout(invoice);
        System.out.println(invoice.total());
    }
}
```

```bash
javac SeparationOfResponsibilitiesDemo.java
java SeparationOfResponsibilitiesDemo
```

```text
receipt:22
22
```

**Explanation:**

- `Line` decides the amount of a single line.
- `Invoice` decides the total across the lines.
- `ReceiptSender` is an interface that only specifies **sending a receipt**, without knowing how Invoice is calculated.
- `ConsoleReceiptSender` uses the console as a demo adapter in place of email/HTTP.
- `CheckoutService` coordinates obtaining the total and delegating sending to the sender.
- Changing the sending mechanism does not require modifying Invoice or Line.

**Business limitations:** This is not a real checkout yet: it does not handle payments, transactions, retries, persisting orders, or failure semantics. Separating classes **does not automatically** solve consistency when sending an email fails.

## 14. Entity, Value Object, Service: Common Roles

Not every class is an entity or a “manager.” When choosing responsibilities, identify **conceptual roles**:

| Role | Primary Responsibility | Examples |
| --- | --- | --- |
| Entity | Maintains identity, lifecycle, and related rules | Customer, Order |
| Value object | Represents a value with validation/value semantics | Money, DateRange |
| Domain service | Executes domain rules involving multiple objects that do not naturally belong to a single entity | PricingPolicy, TransferPolicy |
| Application service | Coordinates use cases, transactions, and repository/gateway calls | CheckoutService |
| Repository | Retrieves/persists aggregates according to a contract | OrderRepository |
| Adapter/gateway | Communicates over HTTP/DB/email/file | EmailSender, JdbcOrderRepository |
| Controller/UI | Receives input, builds responses, and converts DTOs | CheckoutController |
| DTO/record | Transports data according to a contract | CheckoutRequest, Receipt |
| Utility | Pure algorithms with no identity or lifecycle | Checksums, ParsingHelpers |

These are **architectural suggestions**, not a requirement that every Java application must use these exact layers. A role is chosen for its responsibility, not for a “Service/Manager/Util” suffix.

## 15. When to Use `record` Instead of a Regular Class?

Java 17 records fit **data carriers** with simple value-oriented semantics:

```java
record Coordinate(int x, int y) {}
record CustomerId(String value) {}
```

A record automatically generates the canonical constructor/accessors/equals/hashCode/toString based on its components (unless customized). It is great for IDs, coordinates, and suitable request/response messages.

However, the first question is still responsibility:

- Does this object only need to **carry a value**, or does it have a long-lived identity?
- Does an invariant need to be checked in the constructor?
- Do components contain mutable arrays/lists that require defensive copying?
- Does it need state/lifecycle changes?
- Is equality by value or by identity?

**Do not choose a record just to avoid writing boilerplate** if the object needs mutable identity and a clear lifecycle. Conversely, do not write a mutable class with public setters for a value object that should be immutable.

## 16. Value Object Example: A Valid Number Range

Create **`RangeValueObjectDemo.java`**:

```java
record IntRange(int min, int max) {
    IntRange {
        if (min > max) {
            throw new IllegalArgumentException(
                    "min greater than max");
        }
    }

    boolean contains(int value) {
        return min <= value && value <= max;
    }

    int length() {
        return Math.subtractExact(max, min);
    }
}

public class RangeValueObjectDemo {
    public static void main(String[] args) {
        IntRange range = new IntRange(2, 8);

        System.out.println(range.contains(5));
        System.out.println(range.contains(9));
        System.out.println(range.length());
        System.out.println(new IntRange(2, 8).equals(range));
    }
}
```

```bash
javac RangeValueObjectDemo.java
java RangeValueObjectDemo
```

```text
true
false
6
true
```

The class/record is created because **the range concept has its own meaning**, not because the two fields `min` and `max` happen to appear together. It maintains the `min <= max` invariant and provides directly related behavior.

### Question to Clarify Semantics

`length()` in the example is the **difference max - min**, not the count of integers in the closed interval (the number of elements would be max-min+1, which could overflow). The method name and business definition must agree; a method name does not decide semantics on its own.

## 17. Designing Money: A Responsibility Larger Than a Primitive

Money typically carries **an amount and a currency**; adding two different currencies is invalid without a policy-based conversion. A `double price` field alone can hardly protect against that.

Create **`MoneyResponsibilityDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    Money add(Money other) {
        Objects.requireNonNull(other);
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    Money multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity");
        }
        return new Money(
                amount.multiply(BigDecimal.valueOf(quantity)),
                currency);
    }
}

public class MoneyResponsibilityDemo {
    public static void main(String[] args) {
        Currency vnd = Currency.getInstance("VND");
        Money price = new Money(new BigDecimal("10000"), vnd);

        Money total = price.multiply(3);
        Money shipping =
                new Money(new BigDecimal("5000"), vnd);

        System.out.println(total.add(shipping).amount());
        System.out.println(total.currency().getCurrencyCode());
    }
}
```

```bash
javac MoneyResponsibilityDemo.java
java MoneyResponsibilityDemo
```

```text
35000
VND
```

### Why Do Responsibilities Determine Methods?

`Money` is responsible for performing operations that **preserve the currency invariant**. The `add` method rejects different currencies. A `sendEmail()` or `saveJdbc()` method does not serve this responsibility.

**Limitations:** The example does not automatically apply a rounding scale or a non-negative constraint; a real monetary policy must decide those rules. `BigDecimal` is suitable for decimal arithmetic, but it cannot replace domain decisions regarding conversion/tax/rounding.

## 18. Who Owns the Behavior? Place Methods Close to the Data They Protect

Consider the rule “do not allow withdrawing more than the balance.” There are two approaches:

**Error-prone design:**

```java
// account.setBalance(account.getBalance() - amount);
```

If callers modify the balance directly, every call site must remember to check it, and races can also occur under concurrent updates.

**Responsibility-driven design:**

```java
account.withdraw(amount);
```

Account manages the invariant and can use a clearly defined operation.

### Complete Example

Create **`AccountResponsibilityDemo.java`**:

```java
final class Account {
    private int balance;

    Account(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("opening");
        }
        balance = openingBalance;
    }

    void deposit(int amount) {
        requirePositive(amount);
        balance = Math.addExact(balance, amount);
    }

    void withdraw(int amount) {
        requirePositive(amount);
        if (amount > balance) {
            throw new IllegalArgumentException(
                    "insufficient balance");
        }
        balance -= amount;
    }

    int balance() {
        return balance;
    }

    private static void requirePositive(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
    }
}

public class AccountResponsibilityDemo {
    public static void main(String[] args) {
        Account account = new Account(100);
        account.deposit(50);
        account.withdraw(20);

        System.out.println(account.balance());

        try {
            account.withdraw(200);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(account.balance());
    }
}
```

```bash
javac AccountResponsibilityDemo.java
java AccountResponsibilityDemo
```

```text
130
insufficient balance
130
```

`Account` has no public setter for balance, because its responsibility is **maintaining a valid balance through business behavior**. On a failed withdraw, the method does not mutate state before throwing an exception; the account still has a balance of 130.

**Scope:** This example is single-threaded and uses integer units. In real banking, synchronization, durable transactions, and a money type/currency policy are needed. Good class design is a necessary condition, not an ACID database by itself.

## 19. When a Responsibility Spans Two Objects, Do Not Force One Object to Do Everything

“Transferring money from A to B” involves **two accounts** and requires **consistency across both**. An Account can be responsible for valid withdrawals/deposits, while the transfer operation may belong to a service/aggregate authorized to coordinate atomicity.

Illustrative snippet:

```java
class TransferService {
    void transfer(Account from, Account to, int amount) {
        // Check business rules, coordinate withdrawal/deposit,
        // transaction/rollback according to the storage model.
    }
}
```

**Not a safe transfer implementation yet.** If `from.withdraw` succeeds and then `to.deposit` fails, the system can be left modified on only one side. Simply splitting the responsibility into TransferService **does not** automatically create an atomic transaction; you must choose a storage/transaction boundary and failure handling.

### Ownership Questions

- Account knows each account's invariants.
- Transfer orchestration is responsible for **the overall cross-account change**.
- The repository/transaction manager is responsible for persistence/concurrency.
- The notification service sends notifications after the transaction completes according to the appropriate workflow.

What matters is **identifying responsibilities first**, and only then choosing fields and methods; do not cram SQL transactions into Account just because Account has a balance.

## 20. Distinguishing Entities and Value Objects via Identity/Lifecycle

A `Customer` entity can change its email while keeping the same CustomerId. An `EmailAddress` value object can be replaced with another value; there is no need to maintain a separate entity identity for the email address.

| Question | Entity | Value object |
| --- | --- | --- |
| Does the object have an identity independent of state? | Usually yes | Usually no |
| Does it have a state-transition lifecycle? | Possibly | Usually represents an immutable value |
| Expected equality? | By ID/domain identity | By value components |
| What are the fields? | State needed for invariants/lifecycle | Components defining the value |
| What are the methods? | Entity commands/queries | Validation/value operations |
| Use a record? | Usually consider a class | A record is often appropriate |

**Do not turn this table into a language rule:** Java has no `entity` keyword, and many valid designs exist. Roles are a way of reasoning about the domain to choose an abstraction.

## 21. Moving from Responsibilities to a Minimal Public API

For OrderLine earlier in this article, the public-facing API might only need:

```java
int subtotal();
int quantity();
String item();
```

There is no need to generate `setItem`, `setQuantity`, `setSubtotal`, or `getEverythingAsMap` by default.

**Principle of least access:** Keep fields `private` and only expose the necessary behavior. A class may use package-private methods in exercises for brevity; a public library API must carefully consider clear contracts and module boundaries.

Every public method is a promise:

- What constitutes valid input?
- Which exceptions can it throw?
- Does the object state change?
- Does it return an alias to mutable internals?
- What about thread safety?
- Is backward compatibility preserved when the method changes?

A small, expressive API is usually easier to maintain than a sprawling set of setters/getters.

## 22. Choosing Methods by Asking “What Does the User of the Class Want to Do?”

Instead of listing direct CRUD operations for every field:

```java
order.setStatus("PAID");
order.setPaidAt(time);
```

derive the behavior:

```java
order.markPaid(time);
```

These are **illustrative code snippets**. The `markPaid` method can check:

- Does the current status allow payment?
- Is the timestamp valid?
- Does it prevent a second update?
- Which fields must change in sync?

The class responsible for **transition invariants** should own the state-transition method. If status is modified through multiple separate setters, a caller could forget to update paidAt or transition from a disallowed state.

## 23. Example of a State Transition with Clear Responsibility

Create **`OrderLifecycleResponsibilityDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID, CANCELLED
}

final class Order {
    private OrderStatus status = OrderStatus.NEW;

    void pay() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                    "only NEW order can be paid");
        }
        status = OrderStatus.PAID;
    }

    void cancel() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                    "only NEW order can be cancelled");
        }
        status = OrderStatus.CANCELLED;
    }

    OrderStatus status() {
        return status;
    }
}

public class OrderLifecycleResponsibilityDemo {
    public static void main(String[] args) {
        Order order = new Order();

        order.pay();
        System.out.println(order.status());

        try {
            order.cancel();
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(order.status());
    }
}
```

```bash
javac OrderLifecycleResponsibilityDemo.java
java OrderLifecycleResponsibilityDemo
```

```text
PAID
only NEW order can be cancelled
PAID
```

**Why the Order class exists:** To manage an order and its valid transitions. Its fields and methods are derived from the responsibility of **disallowing invalid states**, not from a desire to have a mutable enum property.

**Do not confuse this:** A status enum does not describe all business workflows; in a real system there are also payment IDs, payment timestamps, idempotency, refunds, persistence transactions, and synchronization. Only add state when requirements clarify the responsibility.

## 24. Avoiding an “Anemic Domain Model” Thoughtfully

An *anemic domain model* typically refers to a design style where entities mainly have fields and getters/setters, while all business rules are pushed out to services that manipulate state directly.

Example of the risk:

```java
class OrderData {
    public int amount;
    public String status;
}

class OrderLogic {
    void pay(OrderData order) {
        order.status = "PAID";
    }
}
```

These two classes are only **illustrative snippets**. They allow callers to change `status` to any arbitrary string; there is no clear owner protecting the state transition.

However, **not every thin DTO is wrong**: a request/response record that simply carries data across a boundary can have a completely valid responsibility. Distinguish between:

- DTO: its purpose is **data transport**.
- Domain object: its purpose may include **maintaining invariants and business behavior**.

Do not force a DTO to contain domain business logic; nor turn a domain entity into a mutable data bag if it needs to protect its own rules.

## 25. Dividing Responsibilities by Change, Not by a “One Class per Method” Technique

If multiple methods share the same fields and protect the same invariant, splitting too finely will increase coupling:

```text
CartAddService → CartStateHolder
CartRemoveService → CartStateHolder
CartTotalService → CartStateHolder
CartValidator → CartStateHolder
```

This model may force CartStateHolder to expose a mutable collection so multiple helpers can coordinate, weakening encapsulation.

A single `ShoppingCart` class with `add/remove/total` can be **more cohesive**. Conversely, an independent `NotificationSender` serving network I/O has its own reason to change, so it should be separated from Cart.

### A Pragmatic Question

“If there is a cart bug, will a developer fix it in one place that holds the complete knowledge, or have to trace through a dozen small classes? If the email provider changes, does Cart have to be modified?”

These two questions help strike a balance between avoiding a **God Object** and avoiding **overengineering**.

## 26. A “God Class” Often Starts with a Vague Responsibility

Names like `Manager`, `Helper`, `Utils`, and `Processor` are not wrong by themselves, but they easily become dumping grounds for arbitrary operations without a clear one-sentence contract.

For example, an `ApplicationManager` that manages user auth, pricing, sending email, databases, PDFs, logging, and caches does not have a focused area of change.

**Responsibility naming filter:**

- Can you express “Class X is responsible for Y” without using “and many other things”?
- Do the methods share the same domain vocabulary?
- Is there a group of fields used almost exclusively by a separate subset of methods?
- If a requirement changes, is the code region to modify clearly bounded?
- Do the class's dependencies accurately reflect its role?

There is no need to force a fixed suffix pattern; choose a name that expresses an explainable concept or role.

## 27. Choosing Collaborators Instead of Cramming All Logic into One Class

A large responsibility may require collaboration:

```text
CheckoutService
   ├── ShoppingCart       (state and item invariants)
   ├── PricePolicy        (pricing rules)
   ├── OrderRepository    (persistence)
   └── ReceiptSender      (notification)
```

This is a conceptual diagram.

`CheckoutService` is responsible for **workflow orchestration**, without needing to know SQL columns or SMTP headers. It can depend on interfaces representing capabilities rather than concrete classes.

**Avoid creating unnecessary bidirectional dependencies** such as `Cart → CheckoutService → Cart` or `Order → EmailSender → Order` if that muddies ownership. Each edge should have a business reason.

## 28. An Interface Should Only Appear When There Is a Useful Contract

Do not create `IUserService` and `UserServiceImpl` for every class just to “follow standards.” An interface has value when:

- There are, or are expected to be, **multiple implementations with reasonable semantics**.
- Callers need a mock/fake adapter via a stable contract.
- The boundary between domain/application and infrastructure requires dependency inversion.
- A plugin extension point is exposed externally.
- The API wants to express a capability independent of any concrete class.

For a value object like `Money`, a `MoneyInterface` interface usually adds no value if there are no variants/contracts to abstract.

**Choose abstractions based on responsibility and need for change**, not on a desired class count.

## 29. Dependency Injection Example Without a Framework

Create **`InjectedPolicyDemo.java`**:

```java
interface ShippingCost {
    int costFor(int itemCount);
}

final class FlatShipping implements ShippingCost {
    @Override
    public int costFor(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException("item count");
        }
        return itemCount == 0 ? 0 : 15;
    }
}

final class FreeShipping implements ShippingCost {
    @Override
    public int costFor(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException("item count");
        }
        return 0;
    }
}

final class OrderQuote {
    private final ShippingCost shipping;

    OrderQuote(ShippingCost shipping) {
        this.shipping = java.util.Objects.requireNonNull(
                shipping);
    }

    int total(int goodsAmount, int itemCount) {
        if (goodsAmount < 0) {
            throw new IllegalArgumentException("goods amount");
        }
        return Math.addExact(goodsAmount,
                shipping.costFor(itemCount));
    }
}

public class InjectedPolicyDemo {
    public static void main(String[] args) {
        OrderQuote standard =
                new OrderQuote(new FlatShipping());
        OrderQuote promoted =
                new OrderQuote(new FreeShipping());

        System.out.println(standard.total(100, 2));
        System.out.println(promoted.total(100, 2));
    }
}
```

```bash
javac InjectedPolicyDemo.java
java InjectedPolicyDemo
```

```text
115
100
```

`OrderQuote` is responsible for **generating a quote with shipping**, and `ShippingCost` is responsible for **selecting the fee policy**. These two concerns can change independently, so the interface/injection has a clear reason.

You do not need Spring or an injection framework to achieve responsibility separation. Constructor injection and a regular Java 17 interface are enough for this example.

## 30. Choosing Fields by Asking “What Must Be Remembered Between Calls?”

A field should be added because the class has **state that needs to be retained across methods** or because it needs to hold a collaborator.

Ask for each candidate:

1. If this field is removed, can the responsibility still be fulfilled correctly?
2. Does the field store **source state** or merely a recalculated value?
3. Does the field belong to **this object** or should it live in another object?
4. Does the field need to change over time?
5. Can the field be derived from other fields?
6. Is there a mechanism to prevent invalid invariants when the field changes?
7. Is the field an external resource that needs to be closed?
8. Is it accidentally retaining a large object graph beyond its lifecycle?

For example, OrderLine's subtotal is calculated from `price × quantity`; storing `subtotal` as well can create redundant state. Conversely, order status is lifecycle state information and cannot always be inferred from the total amount.

### A Dependency Field Must Also Have a Responsibility

`private final Clock clock` can make sense if the class needs testable time. `private final List<RandomUtil> helpers` is hard to justify if the class has no directly related task.

## 31. A Constructor Is Not Just a Place to Assign Fields

A constructor can be used to:

- Specify required dependencies.
- Validate arguments before publishing the instance.
- Normalize the representation.
- Create defensive copies for mutable data if the object owns the state.
- Ensure the object starts in a valid state.

Things to avoid:

- Sending email/network I/O that does not belong to construction responsibility.
- Putting `this` into a global registry before invariants are complete.
- Calling overridable methods when subclass state is not yet initialized.
- Creating hidden database transactions if the class only represents a value.
- Allowing constructors with dozens of optional parameters without clarifying the domain.

**Good constructor design stems from invariants and required collaborators**, not from the number of fields the IDE wants to initialize.

## 32. Example of a Constructor Checking Conditions Before Mutating State

Create **`RegistrationResponsibilityDemo.java`**:

```java
import java.util.Objects;

final class Registration {
    private final String username;
    private final int age;

    Registration(String username, int age) {
        String checkedName =
                Objects.requireNonNull(username, "username")
                        .trim();

        if (checkedName.isEmpty()) {
            throw new IllegalArgumentException("username");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age");
        }

        this.username = checkedName;
        this.age = age;
    }

    String label() {
        return username + ":" + age;
    }
}

public class RegistrationResponsibilityDemo {
    public static void main(String[] args) {
        Registration a =
                new Registration("  Lan  ", 20);
        System.out.println(a.label());

        try {
            new Registration("   ", 21);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac RegistrationResponsibilityDemo.java
java RegistrationResponsibilityDemo
```

```text
Lan:20
username
```

The class is responsible for **maintaining a valid and normalized registration**. The constructor makes the invariant clear; there is no need to expose setters for username/age if requirements do not allow changes after creation.

Choose a trimming policy deliberately. For real usernames, normalization may involve different Unicode/case/security rules; the takeaway is that **the rule belongs where the data is owned**.

## 33. Choosing Methods That Return Data: Reducing the Risk of “Handing Over the House Keys”

If a class holds a mutable array:

```java
final class Measurements {
    private final int[] samples;

    Measurements(int[] samples) {
        this.samples = samples.clone();
    }

    int[] samples() {
        return samples.clone();
    }
}
```

This is an **illustrative valid declaration**: both the constructor and the accessor clone the primitive array, preventing external aliases from mutating state.

The responsibility “hold a snapshot of measurements” leads to:

- Input defensive copy.
- Output defensive copy.
- Not exposing `setSamples`.
- Defining a null policy (the snippet does not check for null yet; null will throw NullPointerException on clone).
- If equality by contents is needed, adding appropriate `equals/hashCode` semantics.

**Do not copy everything reflexively.** If a class represents a shared mutable buffer with its own contract, defensive copying may not be appropriate. What matters is **clear ownership and an API that upholds the right responsibility**.

## 34. Choosing to Place Behavior “Where There Is Enough Information”

A rule that uses only one object's state usually fits best on that object itself:

- `OrderLine.subtotal()` uses unitPrice and quantity.
- `IntRange.contains(value)` uses min and max.
- `Money.add(other)` checks for matching currency.

A use case involving multiple subsystems usually needs a coordinator:

- Checkout needs inventory, payment, and order persistence.
- Transfer needs two accounts and transaction semantics.
- Sending a receipt needs data + outbound notification.

**There is no formula stating “a method always belongs on the object with the most fields.”** Ask which object **owns the invariant**, who has enough information, and what will change together with the rule.

## 35. Do Not Put Business Rules in the UI Layer Just Because It Is Easy to Write

An HTTP controller can receive a request and validate **input format** such as counts or JSON structure, but important domain invariants should not live only in the controller:

```java
// Controller:
if (request.quantity() <= 0) {
    // HTTP 400
}
```

This code snippet illustrates validation at the boundary, but the domain class must also protect its own invariant if there are other callers from a CLI, batch job, or tests.

**Two validation layers can coexist:**

- Boundary validation → clear error messages and proper response formatting.
- Domain validation → prevents invalid domain state from existing even if a caller bypasses the controller.

Domain class responsibility cannot be replaced by an `if` in the UI.

## 36. Avoiding “Feature Envy”: Methods in Other Classes Digging Into Internal Fields

The symptom:

```java
int total = 0;
for (CartLine line : cart.getLines()) {
    total += line.getQuantity() * line.getUnitPrice();
}
```

This is an **illustrative snippet** using hypothetical getters. If multiple callers all calculate the total by digging into Cart fields, consider `cart.total()` to consolidate the logic and invariant in their natural home.

However, if the total depends on **tax, currency exchange, or promotion policy** outside Cart, a `QuoteCalculator` or service may be more appropriate; Cart does not need to absorb every policy variant.

**Balanced mindset:** Place behavior close to the state it protects, without making the object depend on every environmental policy.

## 37. One Responsibility May Need Multiple Methods, and One Method May Use Multiple Collaborators

Do not infer:

- 1 responsibility = 1 method.
- 1 class = 1 dependency.
- 1 use case = 1 class.
- 1 noun = 1 object.

For example, ShoppingCart has add/total/lines; all serve the responsibility of managing the cart. CheckoutService may have dependencies on Cart, Repository, and PaymentGateway; together they serve the orchestration of **one use case**, provided the class does not start containing pricing internals, SQL, and email templating.

**A good sign:** You can write tests for the class's behavior using inputs/outputs and fake collaborators without having to invoke the entire system.

## 38. Test from Responsibilities Before Testing Fields

For a class responsible for “not allowing withdrawals exceeding the balance,” tests should verify:

1. The initial balance is valid.
2. A valid deposit increases the balance.
3. A valid withdrawal decreases the balance.
4. A withdrawal exceeding the balance is rejected.
5. When an operation fails, the state remains correct.
6. Edge cases such as zero/negative amounts are handled.

You should not just test getters/setters with “set 5 then get 5,” because that does not prove any invariant.

### Runnable Self-Test for BankAccount

Create **`AccountResponsibilitySelfTest.java`**:

```java
final class BankAccount {
    private long cents;

    BankAccount(long initialCents) {
        if (initialCents < 0) {
            throw new IllegalArgumentException("initial");
        }
        cents = initialCents;
    }

    void deposit(long amount) {
        requirePositive(amount);
        cents = Math.addExact(cents, amount);
    }

    void withdraw(long amount) {
        requirePositive(amount);
        if (amount > cents) {
            throw new IllegalArgumentException("insufficient");
        }
        cents -= amount;
    }

    long balance() {
        return cents;
    }

    private static void requirePositive(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
    }
}

public class AccountResponsibilitySelfTest {
    static void check(boolean result, String label) {
        if (!result) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);

        account.deposit(30);
        check(account.balance() == 130, "deposit");

        account.withdraw(20);
        check(account.balance() == 110, "withdraw");

        try {
            account.withdraw(200);
            throw new AssertionError("missing rejection");
        } catch (IllegalArgumentException expected) {
            check(account.balance() == 110,
                    "state unchanged on failure");
        }

        System.out.println("account responsibility PASS");
    }
}
```

```bash
javac AccountResponsibilitySelfTest.java
java AccountResponsibilitySelfTest
```

```text
account responsibility PASS
```

`check` throws AssertionError directly without needing to enable `-ea`. The test demonstrates basic responsibility behavior, not thread safety or transactional persistence in a real bank.

## 39. Designing for Testing Does Not Require Creating an Interface for Every Class

A value object like `Money` can be tested directly without mocking Money. A stateful `ShoppingCart` can be tested directly with CartLine.

An application service with external dependencies may need interfaces/fakes for testing.

Create **`CheckoutWithFakeDemo.java`**:

```java
interface OrderStore {
    void save(String id);
}

final class RecordingStore implements OrderStore {
    private String savedId;

    @Override
    public void save(String id) {
        savedId = id;
    }

    String savedId() {
        return savedId;
    }
}

final class Checkout {
    private final OrderStore store;

    Checkout(OrderStore store) {
        this.store = store;
    }

    void submit(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("order id");
        }
        store.save(orderId);
    }
}

public class CheckoutWithFakeDemo {
    public static void main(String[] args) {
        RecordingStore fake = new RecordingStore();
        Checkout checkout = new Checkout(fake);

        checkout.submit("ORD-5");
        System.out.println(fake.savedId());
    }
}
```

```bash
javac CheckoutWithFakeDemo.java
java CheckoutWithFakeDemo
```

```text
ORD-5
```

**Design point:** Checkout is responsible for validation/order submission orchestration; OrderStore is responsible for persistence. The fake RecordingStore allows testing without a database. The interface exists because **the boundary has multiple possible implementations**, not because every class is required to have an interface.

## 40. A Use Case Can Change: Class Design Must Adapt

For example, initially the total amount is simply the sum of the lines. A new requirement introduces VAT and discount codes.

There are two approaches:

1. If the rules are small, stable, and belong to the Cart domain, the Cart class can handle them itself after redesigning its invariants.
2. If policies vary by market, campaign, or tenant, extract a `PricingPolicy` that takes input from Cart and returns an appropriate quote.

**Do not prematurely choose 15 strategies when no actual variation exists yet.** However, also do not put a `calculateAllTaxesAndEmailAndExport` method inside ShoppingCart when requirements already indicate independent reasons to change.

### Change Matrix

| When a Requirement Changes | Where to Look First |
| --- | --- |
| Quantity must be greater than 0 | CartLine/Cart |
| Change how shipping is calculated | ShippingCost policy |
| Change email provider | ReceiptSender adapter |
| Change DB schema | OrderStore implementation |
| Change HTML invoice | Presentation/formatter |
| Add order status | Order lifecycle |
| Add currency policy | Money/pricing contract |
| Replace checkout web page | UI/controller |
| Add email sending retry | Notification workflow |
| Add country-specific tax | Tax/Pricing policy |

This matrix helps verify that responsibilities are placed properly: **changes for the same reason should be localized**, and unrelated changes should not ripple across multiple domain classes.

## 41. Pay Attention to Data Ownership When Passing Through Multiple Classes

A service receives a `List<CartLine>` from a controller. Who has the right to mutate the list? If Cart wants to keep a snapshot, the constructor must copy the list; if Order needs a price snapshot, it may need to copy the price fields into an OrderLine snapshot rather than holding a reference to a mutable CatalogProduct.

Design questions:

- Is the input mutable or immutable?
- Is the reference retained after the method returns?
- Who owns the passed-in object?
- Does the API return a view or a defensive copy?
- Can domain invariants be broken by external mutation?
- Is there a need to distinguish **live data** from a **historical snapshot**?

**Responsibility determines ownership**, and ownership determines field representation, constructor copying, and accessor behavior.

## 42. Turn Named Data into a Domain Type When There Is a Shared Invariant

A string can represent an email, product ID, currency code, file path, order status... If you only use `String` everywhere, it is easy to accidentally swap values with different meanings.

When validation or operations are repeated, consider a value object:

Create **`ProductIdResponsibilityDemo.java`**:

```java
record ProductId(String value) {
    ProductId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("product id");
        }
        value = value.trim();
    }
}

final class Product {
    private final ProductId id;
    private final String name;

    Product(ProductId id, String name) {
        this.id = java.util.Objects.requireNonNull(id);
        this.name = java.util.Objects.requireNonNull(name);
    }

    ProductId id() {
        return id;
    }

    String name() {
        return name;
    }
}

public class ProductIdResponsibilityDemo {
    public static void main(String[] args) {
        Product product =
                new Product(new ProductId("  SKU-7  "), "Pen");

        System.out.println(product.id().value());
        System.out.println(product.name());
    }
}
```

```bash
javac ProductIdResponsibilityDemo.java
java ProductIdResponsibilityDemo
```

```text
SKU-7
Pen
```

ProductId represents and protects **a valid product identifier**. Do not share a type with CustomerId just because both are Strings. However, there is no need to create a wrapper for every String if there is no worthwhile domain distinction; weigh clarity against complexity.

## 43. A Class Responsible for Reading Input Need Not Be Responsible for Storing Domain State

A CLI/HTTP controller can parse input and call a service:

```text
CLI/HTTP adapter:
  "Read request, parse, return protocol errors"

Application service:
  "Coordinate use cases"

Domain objects:
  "Maintain state and invariants"

Repository/gateway:
  "Storage and external system integration"
```

This is a guiding separation. Some small applications can simplify it. What matters is that **business rules are not hidden in a place that only applies to one interface**, if the system has multiple entry points.

If an application starts as a CLI and later adds a web API, a good domain model allows reusing logic without copy-pasting validation from the CLI to the controller.

## 44. Balancing SOLID Within the Scope of Java Core

Some relevant principles:

- **SRP:** a class does not take on unrelated reasons to change.
- **OCP:** design extension points as needed; it is not mandatory for every class to be open to inheritance.
- **LSP:** a subtype must preserve the base contract, if inheritance is chosen.
- **ISP:** small interfaces tied to a clear capability, without forcing clients to use methods they do not need.
- **DIP:** high-level policy can depend on abstractions at infrastructure boundaries.

However, at the outset, do not use acronyms as a substitute for thinking. For each class, state:

> “This class is responsible for ___; it must maintain the invariant ___; it collaborates with ___; changes to ___ should not force modifying it.”

Such a complete sentence is more useful than measuring the number of interfaces or methods against a mechanical standard.

## 45. When Do You Not Need to Create Another Class?

Not every operation demands a new type.

- A simple pure computation used once can be a private method.
- A temporary variable to improve readability does not need a class.
- A DTO with 2–3 fields and no complex invariants can be a small record.
- An operation tightly tied to Order can be a method of Order.
- A policy rule that changes separately may need an independent class/interface.
- A stateless set of operations can be a utility function/library if there is no worthwhile domain abstraction.

**Criteria:** Extract a class when there is a **clear responsibility, its own invariant, its own lifecycle, an independently changing policy, or a reasonable reuse/testing need**. Avoid both god classes and “a class per line.”

## 46. Code Review: Before and After Comparison

### Before: Data Bag with Unrestricted Getters/Setters

```java
class SubscriptionData {
    public String status;
    public int remainingDays;
}
```

A caller can write:

```java
subscription.status = "EXPIRED";
subscription.remainingDays = 365;
```

These are **illustrative snippets**; there is no guarantee that status and remainingDays stay synchronized.

### After: State Management Responsibility

One approach is:

```java
final class Subscription {
    private int remainingDays;

    Subscription(int remainingDays) {
        if (remainingDays < 0) {
            throw new IllegalArgumentException("days");
        }
        this.remainingDays = remainingDays;
    }

    void consumeDay() {
        if (remainingDays > 0) {
            remainingDays--;
        }
    }

    boolean expired() {
        return remainingDays == 0;
    }
}
```

The `expired` status is **derived** from remainingDays, rather than being a string field that can easily drift out of sync.

**However:** If the domain needs SUSPENDED/CANCELLED states that cannot be derived from days, a different state model is required. Do not try to eliminate a state field just to achieve “fewer fields.” Let **the business domain decide the representation**.

## 47. Runnable Program: Minimum State of Subscription

Create **`SubscriptionResponsibilityDemo.java`**:

```java
final class Subscription {
    private int remainingDays;

    Subscription(int remainingDays) {
        if (remainingDays < 0) {
            throw new IllegalArgumentException("days");
        }
        this.remainingDays = remainingDays;
    }

    void consumeDay() {
        if (remainingDays > 0) {
            remainingDays--;
        }
    }

    boolean expired() {
        return remainingDays == 0;
    }

    int remainingDays() {
        return remainingDays;
    }
}

public class SubscriptionResponsibilityDemo {
    public static void main(String[] args) {
        Subscription subscription = new Subscription(2);

        System.out.println(subscription.expired());
        subscription.consumeDay();
        subscription.consumeDay();
        subscription.consumeDay();

        System.out.println(subscription.remainingDays());
        System.out.println(subscription.expired());
    }
}
```

```bash
javac SubscriptionResponsibilityDemo.java
java SubscriptionResponsibilityDemo
```

```text
false
0
true
```

There is no public setter or duplicate status field. The consumeDay method prevents remainingDays from becoming negative. This is an example of how the responsibility “manage remaining days and expiration status” leads directly to the minimum field and methods.

## 48. Refactoring by Responsibility: A Safe Process

When an existing class has grown very large, avoid rewriting the entire thing at once. You can follow these steps:

1. **List existing behaviors**, not just fields.
2. Write a description of the **responsibilities and invariants** that those behaviors fulfill.
3. Group members by reason to change, related data objects, and external dependencies.
4. Write regression tests for current observable behavior.
5. Choose one independent responsibility (for example, email rendering) to extract.
6. Keep contracts compatible or create adapters while refactoring.
7. Transfer ownership of state and methods so that no public mutable aliases remain.
8. Update callers step by step.
9. Check code flow when exceptions/concurrency occur.
10. Review whether the old class still has a clear responsibility; avoid a new class that only does meaningless forwarding.
11. Measure test complexity and coupling before/after the change.
12. Only optimize performance when there is evidence; refactoring can change allocations and interfaces.

**Do not refactor just because “the class is over 300 lines.”** Line count is a signal worth examining, but responsibility and cohesion are what decide.

## 49. Exercise 1: Choosing Responsibilities from a Room Booking Story

Requirement:

> A guest selects a room and stay dates; the system checks that the dates are valid, calculates the price based on a seasonal policy, confirms the booking, saves it to the DB, and sends an email.

Identify candidate responsibilities before writing fields.

### A Reasonable Solution

| Responsibility | Suggested Type |
| --- | --- |
| Valid check-in/check-out dates | `StayPeriod` value object |
| Booking identity and lifecycle | `Booking` entity |
| Price by season/room type | `PricingPolicy` |
| Confirmation coordination | `BookingService` |
| Saving the booking | `BookingRepository` |
| Sending confirmation | `ConfirmationSender` |
| Receiving HTTP and returning status | `BookingController` |

Not all classes are mandatory if the exercise is small. **Check question:** If you change the email provider, do you have to modify how room pricing is calculated? If the answer is “yes,” the responsibility boundaries may be wrong.

### Final State

`StayPeriod` can hold arrival/departure and check that departure is after arrival. `Booking` holds bookingId/status/period, and should not directly hold a JDBC connection just to “make saving convenient.”

## 50. Exercise 2: Before Choosing a `total` Field

A shopping cart has `List<CartLine>` and an `int total` field. Whenever adding/removing an item, the developer always has to update total. Ask:

- Can the total **be recalculated** easily from lines?
- Is total queried very frequently with large datasets?
- If total is cached, who invalidates it?
- When an update fails, do total and lines remain consistent?
- Are there time-dependent taxes/discounts or configurations outside Cart?

**Solution approach:** Start by calculating total from lines. Only add a cached total when there is a need and clear invariants/atomic updates are designed. A field should not be created just because “the screen needs to display total.”

## 51. Exercise 3: Placing Methods in the Right Location

Given the operations:

- `order.cancel()`
- `sendEmail(order)`
- `orderRepository.save(order)`
- `money.add(otherMoney)`
- `parseHttpRequest(body)`
- `shoppingCart.total()`

Assign them:

| Behavior | Typically Reasonable Owner | Reason |
| --- | --- | --- |
| Cancel an order if status permits | Order | State transition invariant |
| Send email | NotificationSender/Gateway | I/O and provider |
| Save order | OrderRepository | Persistence |
| Add money with the same currency | Money | Value invariant |
| Parse request | HTTP adapter/parser | External protocol |
| Calculate sum of lines | ShoppingCart | State data owned by Cart |

**Note:** Prices with special promotions/taxes may need a pricing service; you should not force every kind of total into Cart.

## 52. Exercise 4: Testing a Class Without Measuring Getters

Problem statement: `Ticket` has a maximum capacity; ticket sales must not exceed capacity. Design the responsibilities and then implement.

### Runnable Solution

Create **`TicketResponsibilityExercise.java`**:

```java
final class TicketInventory {
    private final int capacity;
    private int sold;

    TicketInventory(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity");
        }
        this.capacity = capacity;
    }

    void sell(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }
        if (quantity > capacity - sold) {
            throw new IllegalStateException("not enough seats");
        }
        sold += quantity;
    }

    int remaining() {
        return capacity - sold;
    }
}

public class TicketResponsibilityExercise {
    public static void main(String[] args) {
        TicketInventory inventory = new TicketInventory(5);

        inventory.sell(2);
        System.out.println(inventory.remaining());

        try {
            inventory.sell(4);
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(inventory.remaining());
    }
}
```

```bash
javac TicketResponsibilityExercise.java
java TicketResponsibilityExercise
```

```text
3
not enough seats
3
```

The responsibility of `TicketInventory` is to ensure `0 <= sold <= capacity`. Therefore, the needed fields are capacity/sold; the needed methods are sell/remaining and constructor validation. There is no need for public setters for sold/capacity.

**Scope:** This is a single-threaded example. Concurrent ticket sales require appropriate synchronization/transactions; you cannot rely on a non-atomic `if` across multiple threads or processes.

## 53. Self-Test: A Class Protecting Invariants Across Multiple Operations

Create **`InventoryInvariantSelfTest.java`**:

```java
final class Inventory {
    private final int capacity;
    private int used;

    Inventory(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity");
        }
        this.capacity = capacity;
    }

    void allocate(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        if (amount > capacity - used) {
            throw new IllegalStateException("full");
        }
        used += amount;
    }

    void release(int amount) {
        if (amount <= 0 || amount > used) {
            throw new IllegalArgumentException("release");
        }
        used -= amount;
    }

    int available() {
        return capacity - used;
    }
}

public class InventoryInvariantSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory(10);

        inventory.allocate(6);
        check(inventory.available() == 4, "allocate");

        inventory.release(2);
        check(inventory.available() == 6, "release");

        try {
            inventory.allocate(7);
            throw new AssertionError("expected full");
        } catch (IllegalStateException expected) {
            check(inventory.available() == 6,
                    "no partial update");
        }

        System.out.println("inventory invariant PASS");
    }
}
```

```bash
javac InventoryInvariantSelfTest.java
java InventoryInvariantSelfTest
```

```text
inventory invariant PASS
```

`Inventory` is responsible for ensuring the allocated amount does not exceed capacity and does not go negative. The tests verify behavior and invariants, not merely “whether fields have getters.” `check` throws AssertionError directly, so `-ea` is not required.

## 54. An Ordered Checklist Before Typing `class`

### A. Understand the Domain

- [ ] Can I express the use case as an observable outcome?
- [ ] Have I identified actors, inputs, outputs, and failure cases?
- [ ] Do I know which rules must never be violated?
- [ ] Have I distinguished source data, derived data, and external data?

### B. Identify Responsibilities

- [ ] Does each candidate class have a purpose that can be written in a single sentence?
- [ ] Do I know who owns each invariant?
- [ ] Can I describe the reason this class would have to change?
- [ ] Does the class avoid mixing domain rules with persistence/UI/I/O when they change independently?
- [ ] Have I avoided splitting a class just because a method is 10 lines long or a class has many methods?
- [ ] Have I avoided choosing the word `Manager` just because I could not identify a responsibility?

### C. Choose the Structure

- [ ] Have I considered entity, value object, service, repository, adapter, and DTO according to the domain?
- [ ] Is a class needed, or is a record sufficient?
- [ ] Is an interface genuinely needed, or does it just add boilerplate?
- [ ] Should composition be used instead of inheritance?
- [ ] Do dependencies cross the necessary boundaries?
- [ ] Who owns the lifecycle of external collaborators/resources?

### D. Only Then Design Members

- [ ] Which fields are truly needed to fulfill the responsibility?
- [ ] Which fields can be derived and therefore do not need to be stored?
- [ ] Are fields `private` and immutable where appropriate?
- [ ] Does the constructor validate the required invariants properly?
- [ ] Do method names express business behavior?
- [ ] Does any public setter break invariants or ownership?
- [ ] Are references to mutable collections/arrays exposed externally?
- [ ] Does the failure path keep state consistent?
- [ ] Is the API clear on null policy, overflow, exceptions, and concurrency scope?
- [ ] Does every public method have a testable contract?

### E. Verify and Refine the Design

- [ ] Are tests derived from responsibilities rather than just getters/setters?
- [ ] Are there both success and failure examples?
- [ ] Can the class be tested without needing the entire system?
- [ ] Does changing the database/email provider force the domain model to change?
- [ ] When adding a new feature, will responsibilities expand sensibly or turn into a god class?
- [ ] Am I overengineering into dozens of classes with no clear purpose?
- [ ] Can I explain the design to someone else in domain language?

## 55. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Choosing fields before understanding the use case | State does not serve the domain | Write responsibilities/invariants first |
| A class with only default setters | Callers break valid state | Expose domain methods |
| God class doing SQL, email, UI, and pricing | High coupling, many reasons to change | Separate reasonable boundaries |
| Splitting a separate class for every method | Over-fragmentation | Group behaviors sharing an invariant |
| Public mutable list getter | Callers bypass validation | Snapshot/controlled methods |
| Storing a total field even when derived from lines | Data easily drifts out of sync | Derived method; cache only when a policy exists |
| Carelessly using `double` for money | Precision/currency issues | Money domain type |
| Validating only in the controller | Batch/CLI callers bypass domain rules | Domain invariants in domain objects |
| `saveToDatabase` method in a value object | Storage concern does not belong to a value | Repository/adapter |
| Interface for every class | Boilerplate, false abstraction | Interface when there is a contract/variation |
| Using inheritance for all reuse | Coupling/subtype contract hard to protect | Composition when appropriate |
| Using `static` to hold shared state | Unclear ownership/lifecycle | Scoped object or service with a policy |
| Constructor publishing `this` early | Partially initialized objects | Complete invariants before publication |
| Method returning mutable array internals | State modified outside control | Defensive copying/contract |
| Ignoring the failure path | Partial state, resource leaks | Atomic operations/cleanup |
| Letting a domain entity know HTTP/database details | Hard to test, technology changes cause domino effects | Separate adapters |
| Confusing a thin DTO with a domain object | Arbitrarily pushing logic across boundaries | Clarify each model's role |
| Creating classes solely from nouns | Too many meaningless structures | Look for behavior/ownership |
| Testing only getters/setters | Does not protect business invariants | Test success/failure/state |
| Insisting on creating a class just because a method is long | Easily fragments cohesion | Extract method/class by responsibility |
| Enforcing that a class must be under N lines | Metric does not reflect responsibility | Look at reasons to change and coupling |
| Not defining transactions between two entities | Partial updates can be wrong | Clear transaction boundary |
| Thinking private fields alone suffice for a valid domain | Private does not validate itself | Constructor/domain commands |

## 56. Review Questions with Answers

**1.** Why choose responsibilities before fields and methods?

*Because responsibilities determine which state must be retained, which invariants must be protected, and which behaviors belong to the class. Doing it in reverse easily produces mutable data bags or classes that do too much.*

**2.** Is a responsibility the same as a method name?

*No. A responsibility is a meaningful obligation such as managing a shopping cart and protecting quantity; methods are how that obligation is carried out.*

**3.** Does a class with seven methods violate SRP?

*Not by default. If those seven methods serve a single cohesive responsibility, it is still reasonable.*

**4.** Why can a public setter for `balance` be a weak design?

*Callers can bypass withdrawal/deposit rules and put balance into an invalid state.*

**5.** Where should the `withdraw` method live?

*Usually on Account, because Account owns the balance invariant.*

**6.** Who should handle transferring money between two Accounts?

*A component responsible for coordinating and ensuring transaction semantics; Account still maintains each individual account's invariants.*

**7.** When is a total field unnecessary?

*When total is a derived value from lines, cheap enough to recalculate, and easy to keep consistent.*

**8.** When might a cached total field be considered?

*When there is a real performance requirement, a proper update/invalidation policy, and tests ensuring the invariant.*

**9.** Why should Cart not expose its internal mutable List?

*Callers can modify state without Cart validating it.*

**10.** How does a domain model differ from a DTO?

*A domain model can hold invariants/behavior; a DTO primarily transports data according to a boundary contract.*

**11.** Is a record always suitable for entity identity/lifecycle?

*No; a record is usually suited to a value-oriented carrier, while a mutable entity may need a class with a clear lifecycle.*

**12.** Why can Money be a value object?

*It pairs an amount with a currency, checks compatibility, and defines arithmetic semantics.*

**13.** Why should Invoice not send SMTP directly?

*Sending notifications through a provider is an infrastructure responsibility that changes independently from the invoice's value.*

**14.** What is a Repository responsible for?

*Saving and retrieving data/domain aggregates through an appropriate contract.*

**15.** What role does an Application service play?

*Coordinating a use case and its collaborators, without necessarily owning every business rule.*

**16.** Why not create an interface for every class?

*An interface only adds value when there is a real contract/variation/boundary, not just to have another file.*

**17.** What does good cohesion mean?

*Members work together to serve a closely related goal/invariant.*

**18.** What consequences does high coupling cause?

*A single change ripples across many classes, making testing and swapping collaborators difficult.*

**19.** Can composition be used to avoid opening up inheritance?

*Yes. A final class can accept a strategy/interface to vary its behavior.*

**20.** Where should a constructor originate from?

*From required data/dependencies and invariants that must be protected when creating the object.*

**21.** If a class has multiple groups of methods that do not share state, what should be considered?

*It may be bundling multiple responsibilities; try grouping by reason to change and extracting an appropriate boundary.*

**22.** When should a class not be split?

*When the logic is small, serves a single existing responsibility, and extraction would only increase forwarding/coupling.*

**23.** Are a class's responsibilities related to access modifiers?

*Yes. A class that owns an invariant should restrict the paths through which outsiders can modify state.*

**24.** Why must we test when an operation fails?

*To verify that the object is not left in a partial state and that invariants still hold.*

**25.** Is a `static` field always wrong?

*No. It is wrong when ownership/lifecycle or sharing scope is inappropriate; static can be right for constants or shared services with a clear contract.*

**26.** Should classes be chosen according to the number of nouns in the requirements?

*No. You need to examine data, behavior, invariants, identity, and reasons to change.*

**27.** In the shopping cart example, how do CartLine and Cart divide responsibilities?

*CartLine maintains a valid line and calculates its subtotal; Cart owns the collection of lines and cart operations.*

**28.** Does business validation in the controller replace validation in the domain model?

*No, if domain invariants must hold across all entry points.*

**29.** Is the “one reason to change” table a mathematical law?

*No. It is a tool for reviewing responsibility boundaries by stakeholders/reasons, requiring judgment.*

**30.** What is the first question to answer before writing fields?

*“What must this object/class be responsible for protecting or performing, and why is it the natural owner of that responsibility?”*

## 57. References for Further Reading

- *The Java Language Specification, Java SE 17*: https://docs.oracle.com/javase/specs/jls/se17/html/index.html — rules for classes, objects, constructors, methods, and access control.
- *Java SE 17 API – `java.lang.Record`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html — record characteristics at the language/API level.
- *Java SE 17 API – `List.copyOf`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html — unmodifiable snapshot semantics.
- *Java SE 17 API – `Math.addExact` / `multiplyExact`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html — fail-fast on integer overflow.

Object-oriented design principle resources such as SRP and GRASP (*Information Expert*, *Creator*, *Controller*, *Low Coupling*, *High Cohesion*) can help systematize your thinking, but they do not replace analyzing the **actual use cases, invariants, and ownership** of the project.

---

**Final takeaway:** Do not start designing a Java class by asking “how many fields/getters/setters does this class have?” Start from **meaningful responsibilities**, the **invariants** that must never be violated, **who owns the state**, and **reasons to change**. From there, choose the class/record/interface/service, minimal fields, constructor validation, and methods expressing business behavior. Place operations close to the state and invariants they protect; separate persistence, presentation, and external I/O when they change independently; use collaboration/composition to prevent a class from taking on everything. **Do not go to extremes** by splitting every method into a class or creating an interface for every object. A good design lets you state clearly “what this class is responsible for and what it is not responsible for,” and lets you verify that with success tests, failure tests, and observable invariants.
