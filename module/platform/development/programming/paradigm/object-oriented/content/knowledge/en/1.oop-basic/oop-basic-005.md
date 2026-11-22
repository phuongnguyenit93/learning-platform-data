# Encapsulation, Abstraction, Inheritance, and Polymorphism in OOP

The four concepts of **encapsulation, abstraction, inheritance, and polymorphism** are often called the “four pillars of object-oriented programming.” But memorizing names and definitions is insufficient: you need to understand **how they help design software, how they relate, and when to use them**.

Consider a store where a customer has a cart worth 500.000 VND. The store can offer either **a 10% discount** or **a fixed discount of 80.000 VND**. The system must keep the cart valid, calculate totals correctly, and allow new discount policies with minimal changes to checkout code.

This lesson uses that problem to explain all four concepts. No prior Spring Boot knowledge is required; the Java code can run directly.

## 1. Overview: Four Concepts Address Four Different Questions

| Concept | Question it addresses | Store example |
| --- | --- | --- |
| **Encapsulation** | Who may read or modify state, and through which paths, to keep data valid? | A cart validates quantities itself and prevents outsiders from directly modifying its order-line list. |
| **Abstraction** | *Which capabilities* must object users know, and *which details* can they ignore? | Checkout only needs to ask for the discount amount, without knowing each promotion's algorithm. |
| **Inheritance** | Which specialized type can reasonably reuse and extend a parent type? | Percentage and fixed-amount discounts are both kinds of discount policies. |
| **Polymorphism** | Why can the same call behave differently depending on the actual object? | `discountFor(500000)` returns 50.000 for a 10% policy, but 80.000 for a fixed-amount policy. |

They **are not four steps to execute in sequence**, and every class need not use all four. An immutable class can exhibit excellent encapsulation without inheriting from another domain class. An application can use abstraction and polymorphism through interfaces with little need for deep class hierarchies.

## 2. Encapsulation: An Object Protects Its Own State

Suppose you implement a cart as follows:

~~~java
class Cart {
    public List<String> items = new ArrayList<>();
}
~~~

Any code holding a `Cart` reference can modify `items` directly. If the system needs a rule such as “items with negative quantities cannot be added,” this class has no reliable enforcement point. Callers can accidentally corrupt the data even without intending to.

Encapsulated design means **placing data and the behaviors that operate on it within the same responsibility boundary**, then controlling how state can be accessed and changed.

~~~java
final class Cart {
    private final List<String> items = new ArrayList<>();

    public void addItem(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        items.add(sku);
    }

    public List<String> viewItems() {
        return List.copyOf(items);
    }
}
~~~

Here:

- `items` is internal state held by `Cart`; external code cannot directly add to or remove from its internal list.
- `addItem()` is **a controlled modification path**: it validates input before updating.
- `viewItems()` returns an unmodifiable snapshot of the list that rejects operations such as `add`/`clear`. Consequently, callers cannot modify the original list through the returned reference.

**Encapsulation does not simply mean adding `private` and generating getters/setters for every field.** If `setQuantity(-5)` accepts an invalid value, the business rule is still unprotected. Behaviors such as `addItem()`, `removeItem()`, or `confirm()` are often more meaningful than generic setters because they express valid operations.

### Protecting Invariants

A cart might enforce these rules:

- Product codes must not be blank.
- Every order-line quantity must be greater than 0.
- Unit prices must not be negative.
- Totals must be calculated from valid order lines.

A well-designed operation **checks conditions before changing state** and rejects invalid input without leaving the cart partially updated.

Notice that `private final List` prevents reassignment of the `items` variable, but the `ArrayList` itself remains mutable through `add()`. Therefore, **`final` does not mean the list's contents are immutable**, and `private` does not prevent bugs within the class's own methods. Proper encapsulation requires access controls, suitable operations, and rule validation.

**When is it useful?** When state has constraints, changes from many locations could introduce inconsistencies, or you want to maintain logic without editing every caller.

## 3. Abstraction: Expose Capabilities, Hide Unnecessary Details

For the discount problem, checkout code only needs to know that a policy can:

> Accept a subtotal before discounts and return a valid discount amount.

It does not need to know whether the policy uses a percentage, a fixed amount, or a more complex calculation. We can describe the **contract** using an interface:

~~~java
interface DiscountPolicy {
    BigDecimal discountFor(BigDecimal subtotal);
}
~~~

The checkout function can work with `DiscountPolicy`:

~~~java
BigDecimal amountToPay(BigDecimal subtotal, DiscountPolicy policy) {
    return subtotal.subtract(policy.discountFor(subtotal));
}
~~~

The main idea is **separating “what must be done” from “how it is implemented.”** Callers know the behavior's name, parameters, return type, and expected rules; they do not need to inspect each policy's internal algorithm.

Abstraction also appears when we use `Cart.addItem()` without caring whether the class stores data in an `ArrayList`, an array, or another structure. Thus, **abstraction involves designing and selecting what to expose**, not just using `abstract class` or `interface` syntax.

**Do not confuse abstraction with encapsulation:**

| Perspective | Encapsulation | Abstraction |
| --- | --- | --- |
| Focus | Control access to and changes of internal state. | Expose only the capabilities/details users need. |
| Question | “Who may modify data, and under which rules?” | “What does the caller need to know to use the object?” |
| Example | `Cart` does not expose mutable `items`. | `CheckoutService` only knows `DiscountPolicy.discountFor()`. |
| Common Java tools | `private`, domain methods, immutable views, validation. | Interfaces, abstract classes, public methods with clear contracts. |

A well-designed object often **abstracts what callers need while encapsulating internal details that require protection**. The two concepts complement rather than replace one another.

### A Contract Is More Than a Method Name

For `discountFor(subtotal)`, the contract must specify that the input subtotal is nonnegative, the output discount is nonnegative and no greater than the subtotal, and the policy must not arbitrarily modify the cart. Interface syntax alone cannot enforce these conditions. The design must express them through code, validation, contract documentation, and appropriate tests.

## 4. Inheritance: Building a Sound Parent–Child Relationship

Inheritance lets a subclass acquire accessible members and behaviors from a parent class and add or change behavior while respecting its contract. In Java, `extends` expresses class inheritance.

~~~java
abstract class DiscountPolicy {
    public abstract BigDecimal discountFor(BigDecimal subtotal);
}

final class PercentageDiscount extends DiscountPolicy {
    private final int percent;

    PercentageDiscount(int percent) {
        this.percent = percent;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.valueOf(percent))
                       .divide(BigDecimal.valueOf(100));
    }
}
~~~

`PercentageDiscount` is a kind of `DiscountPolicy`: anywhere a discount policy is required, a `PercentageDiscount` object can be used, provided it respects the rules promised by `DiscountPolicy`.

Inheritance commonly serves two purposes:

1. **Subtyping:** `PercentageDiscount` can be used wherever `DiscountPolicy` is required.
2. **Shared implementation:** the parent class can provide shared logic while subclasses implement only the differences.

Similar code in two classes does not automatically justify `extends`. For example, `ReportService` and `EmailService` both having a `log()` method does not mean one “is a kind of” the other. Instead, they could share the functionality through a collaborating object.

### Some Java Rules to Remember

| Syntax/concept | Meaning |
| --- | --- |
| `class B extends A` | `B` inherits from **one** parent class `A` (Java does not allow a class to extend multiple classes directly). |
| `@Override` | Marks a subclass method that overrides an overridable parent method; the compiler helps detect incorrect signatures. |
| `super(...)` | Calls an appropriate parent-class constructor from a subclass constructor. |
| `super.method()` | Invokes the parent implementation when needed, provided the method is accessible. |
| `protected` | Permits access within the same package and from subclasses under Java's rules; use carefully because it increases the dependency surface. |
| `final class` | Prevents other classes from extending the class. |
| `final method` | Prevents subclasses from overriding the method. |

Java also supports **interface inheritance**: `interface B extends A`; a class can `implements` multiple interfaces. **Implementing an interface** is not the same as inheriting a superclass's state, although it also establishes a type relationship and supports polymorphism.

### “Is a Kind Of” Is Not Enough: Substitutability Matters

A sound subclass must preserve the expectations of code using the parent type. If the parent promises a discount between 0 and the subtotal, the child should not return a negative value or one exceeding the subtotal. This is the intuition behind the **Liskov Substitution Principle (LSP)**: substituting a child type for its parent must not break the contract.

Therefore, consider inheritance when **the type relationship is meaningful and the subclass's behavior satisfies the parent's contract**. If you merely want to combine functionality, **composition** (holding and delegating to another object) is often more flexible.

## 5. Polymorphism: Same Call, Different Implementations

Consider two policies applied to the same subtotal of 500.000 VND:

- `PercentageDiscount(10)`: a discount of 50.000; the customer pays **450.000 VND**.
- `FixedDiscount(80000)`: a discount of 80.000; the customer pays **420.000 VND**.

Checkout code does not need an `if/else` chain asking “What kind of discount is this?” It simply asks the policy object to perform its behavior.

~~~java
DiscountPolicy policy = new PercentageDiscount(10);
BigDecimal first = policy.discountFor(new BigDecimal("500000"));

policy = new FixedDiscount(new BigDecimal("80000"));
BigDecimal second = policy.discountFor(new BigDecimal("500000"));
~~~

This is **runtime polymorphism** based on **method overriding**: the same call through type `DiscountPolicy` selects the implementation associated with the actual object type.

Java also supports **method overloading**: methods with the same name but different parameter lists.

~~~java
void print(String text) { /* ... */ }
void print(int value) { /* ... */ }
~~~

Overloads are selected primarily from **expression types and applicable signatures at compile time**; this differs from runtime dispatch of overridden methods. Distinguishing these mechanisms avoids the misconception that methods sharing a name always demonstrate the same kind of polymorphism.

**An important limitation:** `static` methods are not overridden via the dynamic dispatch used for instance methods; a subclass static method with the same name/signature performs *method hiding*. `private` methods likewise cannot be overridden by subclasses like accessible instance methods.

### How Does Polymorphism Support Extension?

When a new `SeasonalDiscount` appears, the application can add another class/implementation while `CheckoutService` continues calling `discountFor()`. This reduces code tied to individual concrete types. However, if each policy addition still requires editing an if/else chain inside the service, the benefit is limited.

## 6. Complete Java Example: All Four Concepts Working Together

To see them together, we use an abstract parent class `DiscountPolicy` with **shared validation logic**, two subclasses with their own algorithms, and a `Cart` that keeps its item list valid. The following code runs on **Java 17+** from one `Main.java` file and contains only one public class.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

// Một dòng hàng bất biến (record, Java 16+).
record CartLine(String sku, int quantity, BigDecimal unitPrice) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid cart line");
        }
    }

    BigDecimal total() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

// ENCAPSULATION: Cart quản lý cách thay đổi dữ liệu của mình.
final class Cart {
    private final List<CartLine> lines = new ArrayList<>();

    void addItem(String sku, int quantity, BigDecimal unitPrice) {
        // Validation chạy trước khi List bị thay đổi.
        lines.add(new CartLine(sku, quantity, unitPrice));
    }

    List<CartLine> viewItems() {
        return List.copyOf(lines);
    }

    BigDecimal subtotal() {
        return lines.stream()
                .map(CartLine::total)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}

// ABSTRACTION: một hợp đồng cho mọi chính sách giảm giá.
// INHERITANCE: có thể dùng lại bước validation chung.
abstract class DiscountPolicy {
    // final: mọi subclass đều phải đi qua bước kiểm tra này.
    final BigDecimal discountFor(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        BigDecimal discount = calculateDiscount(subtotal);

        if (discount == null || discount.signum() < 0
                || discount.compareTo(subtotal) > 0) {
            throw new IllegalStateException("Invalid discount");
        }
        return discount;
    }

    // Phần khác nhau để lớp con triển khai.
    protected abstract BigDecimal calculateDiscount(BigDecimal subtotal);
}

// INHERITANCE: chính sách phần trăm là một DiscountPolicy.
final class PercentageDiscount extends DiscountPolicy {
    private final int percent;

    PercentageDiscount(int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Percent must be 0..100");
        }
        this.percent = percent;
    }

    @Override
    protected BigDecimal calculateDiscount(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.valueOf(percent))
                .divide(BigDecimal.valueOf(100));
    }
}

// INHERITANCE: chính sách giảm số tiền cố định.
final class FixedDiscount extends DiscountPolicy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Negative discount amount");
        }
        this.amount = amount;
    }

    @Override
    protected BigDecimal calculateDiscount(BigDecimal subtotal) {
        // Không cho phép giảm vượt tổng tiền.
        return amount.min(subtotal);
    }
}

// POLYMORPHISM: service làm việc với kiểu cha thay vì loại cụ thể.
final class CheckoutService {
    BigDecimal amountToPay(Cart cart, DiscountPolicy policy) {
        Objects.requireNonNull(cart, "cart");
        Objects.requireNonNull(policy, "policy");

        BigDecimal subtotal = cart.subtotal();
        return subtotal.subtract(policy.discountFor(subtotal));
    }
}

public class Main {
    public static void main(String[] args) {
        Cart cart = new Cart();
        cart.addItem("BOOK", 2, new BigDecimal("200000"));
        cart.addItem("PEN", 1, new BigDecimal("100000"));
        System.out.println(cart.subtotal()); // 500000

        CheckoutService checkout = new CheckoutService();

        // Cùng lời gọi service, khác đối tượng chính sách thực tế.
        DiscountPolicy policy = new PercentageDiscount(10);
        System.out.println(checkout.amountToPay(cart, policy)); // 450000

        policy = new FixedDiscount(new BigDecimal("80000"));
        System.out.println(checkout.amountToPay(cart, policy)); // 420000

        // Trường hợp dữ liệu sai: từ chối, không thêm hàng.
        try {
            cart.addItem("ERROR", 0, new BigDecimal("1000"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid quantity");
        }
        System.out.println(cart.subtotal()); // Vẫn 500000

        // Danh sách trả về không thể sửa trực tiếp.
        try {
            cart.viewItems().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot modify cart through view");
        }
        System.out.println(cart.subtotal()); // Vẫn 500000

        // Giảm cố định lớn hơn subtotal vẫn cho số phải trả là 0.
        DiscountPolicy huge = new FixedDiscount(new BigDecimal("900000"));
        System.out.println(checkout.amountToPay(cart, huge)); // 0
    }
}
~~~

Run from the directory containing `Main.java`:

~~~bash
javac Main.java
java Main
~~~

Key output, in order:

~~~text
500000
450000
420000
Rejected invalid quantity
500000
Cannot modify cart through view
500000
0
~~~

### Reading the Program Through the Four Concepts

| Concept | Where it appears in the code | Why it matters |
| --- | --- | --- |
| **Encapsulation** | `Cart.lines` is `private`; `addItem()` validates through `CartLine`; `viewItems()` uses `List.copyOf`. | External code cannot directly change the internal list; invalid data is rejected before being added. |
| **Abstraction** | `CheckoutService` takes a `DiscountPolicy` parameter exposing `discountFor()`. | The service needs only the discount calculation contract, not the details of the formula. |
| **Inheritance** | `PercentageDiscount extends DiscountPolicy` and `FixedDiscount extends DiscountPolicy`. | Both subclasses are discount policies, share validation logic, and implement their own formulas. |
| **Polymorphism** | `policy.discountFor(subtotal)` calls the appropriate subclass's `calculateDiscount()`. | The checkout flow stays the same while discount calculations vary with the actual object. |

### Exactly What Happens When the Method Is Called?

Suppose `policy` is assigned `new PercentageDiscount(10)`:

1. `CheckoutService.amountToPay()` calculates `subtotal = 500000`.
2. It calls `policy.discountFor(subtotal)`.
3. Java executes the shared `discountFor()` method from parent class `DiscountPolicy` and validates that the subtotal is nonnegative.
4. Within that parent method, `calculateDiscount(subtotal)` is **dynamically dispatched** to the override in `PercentageDiscount`.
5. The discount is `50000`; the parent class validates and returns it.
6. The service calculates `500000 - 50000 = 450000`.

If `policy` refers to `new FixedDiscount(80000)`, the common steps are unchanged; only **step 4** uses the `FixedDiscount` formula. The amount payable is `420000`.

~~~mermaid
sequenceDiagram
    participant Main
    participant C as CheckoutService
    participant P as DiscountPolicy
    participant I as Chính sách thực tế
    Main->>C: amountToPay(cart, policy)
    C->>C: subtotal() = 500000
    C->>P: discountFor(500000)
    P->>P: Kiểm tra subtotal
    P->>I: calculateDiscount(500000)
    Note over I: Runtime chọn PercentageDiscount hoặc FixedDiscount
    I-->>P: 50000 hoặc 80000
    P->>P: Kiểm tra mức giảm hợp lệ
    P-->>C: Mức giảm
    C-->>Main: 450000 hoặc 420000
~~~

The diagram illustrates the logical flow. `DiscountPolicy` in the code is **the parent class of the runtime object itself**, not a separate second object created merely to forward the call. Java's dispatch selects the overridden method on the current object.

## 7. Why Use an Abstract Class Here? When Should You Use an Interface?

We saw a simpler interface example earlier, but the complete program uses an `abstract class` to enforce **shared validation rules**: every discount type must validate input and results. This is expressed using the **Template Method** pattern: `discountFor()` is `final`, while only `calculateDiscount()` can be overridden.

| Need | When an interface often fits | When an abstract class often fits |
| --- | --- | --- |
| Declare shared capabilities/contracts | Very suitable; multiple independent classes can implement it. | Possible, but forces subclasses into a class hierarchy. |
| Share instance state and constructors | Not designed for implementing classes' instance fields or constructors. | Can define shared state, constructors, and logic. |
| Share implementation code | Supports `default`/`static` methods where needed, with limitations. | Supports regular methods, `protected` helpers, and templates. |
| One class needs multiple roles | A class can implement multiple interfaces. | A class can directly extend only one class. |
| Ensure no subclass skips validation | A declaration of the contract alone usually cannot enforce the shared execution sequence. | A `final` method can call a `protected abstract` hook, as in this example. |

**Another option:** keep `DiscountPolicy` as an interface and use **composition** to separate the validation component or calculation strategy. An interface is not always better, and an abstract class is not inherently “more object-oriented.” Choose according to the contract, actual sharing needs, and necessary extension constraints.

## 8. Misconceptions That Make OOP Designs Hard to Understand

| Misconception | What to understand instead |
| --- | --- |
| “Encapsulation = private fields + full getters/setters.” | Encapsulation protects rules and limits ways to change state; unrestricted getters/setters can undermine that goal. |
| “Abstraction = using an abstract class.” | Abstraction means choosing the contract/details users need; ordinary classes also offer a level of abstraction. |
| “Inheritance enables reuse, so duplicate code means extends.” | Inheritance also commits to a type relationship and substitutability. Use composition when you only need to assemble functionality. |
| “Polymorphism = any two methods with the same name.” | Runtime polymorphism involves overriding and the actual object type; overload resolution follows different rules. |
| “You need inheritance to use polymorphism.” | Implementing interfaces also supports polymorphism without extending a shared domain superclass. |
| “A child can automatically override any parent method.” | `final`/`private` methods cannot be overridden; same-signature `static` methods are hidden, not overridden as instance methods. |
| “An abstract class always hides all implementation details.” | Abstract classes may contain extensive shared implementation; their level of abstraction depends on the public contract. |
| “Using all four pillars automatically makes a program safe.” | Real systems still require transactions, concurrency control, input validation, network-error handling, and data-boundary design. |

### A Counterexample: Inheriting Merely for Convenience

Suppose `Printer` and `InvoiceService` both need logging. Designing `InvoiceService extends Printer` merely to reuse `log()` is unreasonable: an invoice service **is not a kind of printer**. A better design gives `InvoiceService` **a `Logger` object** and lets it call that object's methods when needed.

~~~java
interface Logger {
    void info(String message);
}

final class InvoiceService {
    private final Logger logger;

    InvoiceService(Logger logger) {
        this.logger = logger;
    }

    void createInvoice() {
        logger.info("Invoice created");
    }
}
~~~

This demonstrates **composition and dependency injection** at a basic level. It also uses **abstraction** through `Logger` and allows **polymorphism** if there are several logging implementations, without inheriting from a domain superclass.

## 9. Check Your Understanding with Short Scenarios

**Question 1.** A class has `private int balance`, but `setBalance(-100)` is still accepted. Is that good encapsulation?

**Explanation:** No. Hiding a field from direct access is insufficient; a public method can still violate the “nonnegative balance” invariant unless its behavior is controlled.

**Question 2.** `CheckoutService` depends only on `DiscountPolicy` and does not import `PercentageDiscount`. What does this illustrate?

**Explanation:** Abstraction. The service relies on a contract and depends less on implementation details. With multiple implementations, this also enables polymorphism.

**Question 3.** `PercentageDiscount` extends `DiscountPolicy` but returns a discount of 700.000 on a subtotal of 500.000. What is wrong?

**Explanation:** It violates the contract that the discount must not exceed the subtotal; the complete program detects this using validation in the parent's `final` method.

**Question 4.** A `DiscountPolicy p` variable successively references a percentage policy and a fixed-amount policy, while the call remains `p.discountFor(subtotal)`. What is this?

**Explanation:** Polymorphism. The external call is the same; the overridden method executes according to the actual object type.

**Question 5.** Two classes share a `formatMoney()` method. Must you create a base class for them to inherit?

**Explanation:** No. A helper, service, or collaborating object may work. Introduce inheritance only when the child truly satisfies the parent's contract.

**Question 6.** Why does `viewItems()` in `Cart` return `List.copyOf(lines)`?

**Explanation:** To avoid exposing the internal mutable list through the return value. Note that if the list elements are mutable objects, modification through those elements still needs to be considered; here `CartLine` is a record containing immutable components.

**Question 7.** If you add a policy providing “15% off, capped at 100.000 VND,” what needs to change?

**Explanation:** You can create `CappedPercentageDiscount extends DiscountPolicy`, override `calculateDiscount()`, and leave `CheckoutService` unchanged. The discount must remain valid, and boundary inputs must be tested. In a larger system, configuration responsible for constructing or selecting policies may still need updates.

## 10. What Should You Ask When Designing an Object?

- **State and rules:** which data belongs to the object, and how can you ensure it is not modified incorrectly? → Think about **encapsulation**.
- **Contract:** what behaviors must users request without understanding internal algorithms? → Think about **abstraction**.
- **Type relationships:** do implementations genuinely have an “is a kind of” relationship, share a contract, and have reusable implementation? → Consider **inheritance**.
- **Behavior variations:** must multiple objects respond to the same call with different implementations? → Think about **polymorphism**.

In the store example, `Cart` protects data; `DiscountPolicy` defines the capabilities checkout needs; specialized discount classes inherit shared rules; and checkout invokes the same contract to obtain policy-specific results. The four concepts are useful when each addresses **a concrete design problem**, rather than when we try to force all four into every class.
