# Non-Overridable Members and Non-Extendable Classes in Java

In Java, the `final` keyword can **lock down parts of an inheritance design**:

- Apply `final` to a **method** so subclasses cannot override (*override*) it.
- Apply `final` to a **class** so no other class can `extends` it.
- Apply `final` to a **variable or field** to prevent reassignment after valid initialization.

These three meanings all promote stability, but **they are not interchangeable**. In particular, a `final class` does not automatically make internal data immutable; a `final method` may still mutate state; and a `final field` does not make the referenced object immutable.

The goal is to understand exactly **what the compiler prohibits**, what remains possible, and how `final` protects rules that subclasses must not violate.

## 1. `final` Methods: Inheritable but Not Overridable

A `final` instance method can still be **called and inherited** by subclasses, but they **cannot provide a new overriding implementation with the same signature**.

~~~java
class Account {
    private String owner;

    Account(String owner) {
        this.owner = owner;
    }

    public final String getOwner() {
        return owner;
    }
}

class SavingsAccount extends Account {
    SavingsAccount(String owner) {
        super(owner);
    }

    // Không hợp lệ:
    // @Override
    // public String getOwner() {
    //     return "Người khác";
    // }
}
~~~

~~~java
SavingsAccount account = new SavingsAccount("An");
System.out.println(account.getOwner()); // An
~~~

Although `SavingsAccount` cannot **override** `getOwner()`, it can still use the inherited method. `final` prevents replacing the method implementation; it **does not** remove the method from the subclass API.

Comparison table:

| Action involving a superclass `final` method | Allowed? |
| --- | --- |
| Call it on a subclass object | Yes, when access permits |
| Inherit the implementation in a subclass | Yes, under Java inheritance rules |
| Override the same signature in a subclass | No |
| Add a different-parameter **overload** in the subclass | Yes |
| Let the `final` method mutate a field or call another method | Yes |
| Let the `final` method call an overridable hook | Yes, but design carefully |

**Overriding (override)** and **overloading (overload)** differ:

~~~java
class Parent {
    public final void send(String text) {
        System.out.println("Gửi: " + text);
    }
}

class Child extends Parent {
    // Overload: tham số khác, hoàn toàn hợp lệ.
    public void send(String text, int times) {
        for (int i = 0; i < times; i++) {
            send(text); // Gọi phương thức final kế thừa từ Parent.
        }
    }

    // LỖI nếu viết:
    // @Override
    // public void send(String text) { }
}
~~~

`send(String, int)` is another method with a different signature; it does not replace the `send(String)` implementation.

## 2. `final` Classes Cannot Be Superclasses

Given this declaration:

~~~java
final class Receipt {
    private final String code;

    Receipt(String code) {
        this.code = code;
    }

    String getCode() {
        return code;
    }
}
~~~

You can still instantiate it:

~~~java
Receipt receipt = new Receipt("RC-001");
System.out.println(receipt.getCode()); // RC-001
~~~

But cannot declare a subclass:

~~~java
// LỖI BIÊN DỊCH:
// class SpecialReceipt extends Receipt {
// }
~~~

A `final` class can itself `extends` a superclass and `implements` interfaces:

~~~java
interface Printable {
    void print();
}

class Document {
    String category() {
        return "Tài liệu";
    }
}

final class Invoice extends Document implements Printable {
    @Override
    public void print() {
        System.out.println(category() + ": hóa đơn");
    }
}
~~~

`Invoice` **inherits** from `Document` but **cannot be extended further**. So the claim that “final classes cannot participate in inheritance” is wrong: they may appear **at the end of a branch**.

Diagram:

~~~mermaid
classDiagram
    class Document {
        +category() String
    }
    class Printable {
        <<interface>>
        +print() void
    }
    class Invoice {
        <<final>>
        +print() void
    }
    Document <|-- Invoice
    Printable <|.. Invoice
~~~

`Invoice` remains usable through a `Document` or `Printable` reference. Marking it `final` does not remove polymorphism through its superclass or implemented interfaces.

## 3. Runnable Java Example: Locking Down a Workflow While Exposing Extension Points

Scenario: an application has multiple payment channels. Every request must validate the amount before processing through a specific channel and return transaction information in a consistent structure.

Design:

- `PaymentChannel` defines the caller-facing contract.
- `PaymentProcessor` is an **abstract** superclass with a **final** `process()` method to preserve the shared workflow.
- `charge()` is a `protected abstract` extension point implemented by subclasses for payment processing.
- `CardProcessor` is **final**: it implements card payments and prohibits further subclassing.
- `BankTransferProcessor` is another concrete class illustrating how several implementations share the workflow.

Save everything as `FinalInheritanceDemo.java` and run with **Java 11+**.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class FinalInheritanceDemo {

    interface PaymentChannel {
        Receipt process(BigDecimal amount);
    }

    static final class Receipt {
        private final String provider;
        private final BigDecimal amount;
        private final String transactionId;

        Receipt(String provider, BigDecimal amount, String transactionId) {
            this.provider = Objects.requireNonNull(provider);
            this.amount = Objects.requireNonNull(amount);
            this.transactionId = Objects.requireNonNull(transactionId);
        }

        String getProvider() {
            return provider;
        }

        BigDecimal getAmount() {
            return amount;
        }

        String getTransactionId() {
            return transactionId;
        }
    }

    static abstract class PaymentProcessor implements PaymentChannel {
        private final String provider;

        protected PaymentProcessor(String provider) {
            String checked = Objects.requireNonNull(provider).trim();
            if (checked.isEmpty()) {
                throw new IllegalArgumentException("Tên kênh không hợp lệ");
            }
            this.provider = checked;
        }

        // Template Method: lớp con không được bỏ qua quy trình kiểm tra.
        @Override
        public final Receipt process(BigDecimal amount) {
            Objects.requireNonNull(amount, "amount");

            if (amount.signum() <= 0) {
                throw new IllegalArgumentException(
                        "Số tiền phải lớn hơn 0");
            }

            String transactionId = Objects.requireNonNull(
                    charge(amount), "transactionId");
            if (transactionId.isBlank()) {
                throw new IllegalStateException("Thiếu mã giao dịch");
            }

            return new Receipt(provider, amount, transactionId);
        }

        // Mỗi lớp con phải định nghĩa cách xử lý riêng.
        protected abstract String charge(BigDecimal amount);
    }

    // Vừa kế thừa một lớp cha, vừa không cho kế thừa tiếp.
    static final class CardProcessor extends PaymentProcessor {
        CardProcessor() {
            super("CARD");
        }

        @Override
        protected String charge(BigDecimal amount) {
            System.out.println("Xử lý thẻ: " + amount.toPlainString());
            return "CARD-TX-001";
        }

        // Không hợp lệ nếu bỏ comment:
        // @Override
        // public Receipt process(BigDecimal amount) {
        //     return null;
        // }
    }

    static class BankTransferProcessor extends PaymentProcessor {
        BankTransferProcessor() {
            super("BANK");
        }

        @Override
        protected String charge(BigDecimal amount) {
            System.out.println("Chuyển khoản: " + amount.toPlainString());
            return "BANK-TX-002";
        }
    }

    public static void main(String[] args) {
        List<PaymentChannel> channels = List.of(
                new CardProcessor(), new BankTransferProcessor());

        for (PaymentChannel channel : channels) {
            Receipt receipt = channel.process(
                    new BigDecimal("150000"));

            System.out.println(
                    receipt.getProvider() + " -> "
                    + receipt.getTransactionId());
        }

        try {
            channels.get(0).process(BigDecimal.ZERO);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac FinalInheritanceDemo.java
java FinalInheritanceDemo
~~~

Output:

~~~text
Xử lý thẻ: 150000
CARD -> CARD-TX-001
Chuyển khoản: 150000
BANK -> BANK-TX-002
Từ chối: Số tiền phải lớn hơn 0
~~~

This example simulates payments using fixed strings and console output; it neither connects to a bank nor guarantees real transactions. It demonstrates inheritance rules and code protected by `final`.

### What Is Fixed, and What Can Be Extended?

| Component | Responsibility | Can subclasses override? |
| --- | --- | --- |
| `PaymentProcessor.process()` | Validates amount, calls `charge`, normalizes Receipt | **No**, because it is `final` |
| `PaymentProcessor.charge()` | Contract implemented by each payment channel | **Yes**, and concrete subclasses must implement it |
| `CardProcessor` | A concrete payment processor | No subclasses because the class is `final` |
| `BankTransferProcessor` | Another concrete processor | Can be subclassed because it is not `final` |
| `Receipt` | Transaction information produced after processing | Cannot be subclassed because the class is `final` |

**Important technical detail:** `process()` cannot be overridden, but its internal call to `charge(amount)` **still dispatches** to the runtime instance's implementation. Thus `final` locks down only `process`'s body, not all polymorphism in the class.

~~~mermaid
sequenceDiagram
    actor App
    participant P as PaymentProcessor.process() final
    participant C as CardProcessor.charge()
    App->>P: process(150000)
    P->>P: kiểm tra amount > 0
    P->>C: charge(150000)
    C-->>P: "CARD-TX-001"
    P->>P: new Receipt(...)
    P-->>App: Receipt
~~~

The diagram shows **the roles in one call on the same CardProcessor instance**: `PaymentProcessor.process()` is inherited code executing, while `CardProcessor.charge()` is dynamically dispatched code. No separate `PaymentProcessor` instance is created.

## 4. Why Mark a Method `final`?

Use `final` when a method embodies **a fixed superclass rule**, such as mandatory validation steps or an identifier representation that must not change.

Potential design benefits:

1. Prevent subclasses from skipping essential logic by overriding a method.
2. Signal that this API has a stable implementation across the inheritance hierarchy.
3. Preserve a shared workflow while permitting specialization through dedicated hooks.
4. Reduce the ways a subclass can violate part of the superclass contract.

However, `final` **is not an absolute security mechanism**. A subclass can still cause incorrect behavior if the superclass exposes other state-changing methods or overridable hooks with dangerous behavior. In the example, `charge()` might return a syntactically valid response without actually collecting money. Every extension point still needs a well-designed and verified contract.

Do not habitually make every method `final` and inadvertently prevent legitimate variations. Before locking down a method, identify a specific **business reason or design constraint**.

## 5. Why Make a Class `final`?

Use `final class` when the design should **prohibit further specialization through inheritance**:

- A value type with strict invariants, where subclassing could change expectations.
- A complete implementation that exposes no extension contract for subclasses.
- A utility or component intended to be **used or delegated to** rather than inherited.
- A type whose identity, equality, or internal rules are difficult to preserve if subclasses can freely change behavior.

The `Receipt` class above has no setters and uses immutable `String`/`BigDecimal` values in its fields. Together with constructor validation, this produces an **observably immutable state** in the example.

But distinguish the underlying reasons:

~~~java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int getValue() {
        return value;
    }
}
~~~

~~~java
Counter counter = new Counter();
counter.increment();
System.out.println(counter.getValue()); // 1
~~~

`Counter` is a `final` class **yet its instances are mutable**. Class-level `final` only prevents `extends Counter`; it does not prohibit updating `value`.

Similarly, a non-`final` class can still be designed to be immutable if all state is properly protected. Data immutability and inheritance restrictions are **separate design decisions**.

## 6. Three Commonly Confused Uses of `final`

| Location | Example | What is prohibited | What remains possible |
| --- | --- | --- | --- |
| Class | `final class Receipt` | Another class using `extends Receipt` | Creating instances, calling methods, changing state if permitted |
| Method | `public final void process()` | A subclass overriding the same signature | Calling it from subclasses, overloading with different parameters |
| Variable/field | `final List<String> items` | Reassigning `items` after assignment | `items.add(...)` if the list is mutable |

Example of `final` on a reference variable:

~~~java
import java.util.ArrayList;
import java.util.List;

final List<String> tags = new ArrayList<>();
tags.add("Java");       // Hợp lệ: cập nhật đối tượng List.
// tags = new ArrayList<>(); // Lỗi: không được gán lại biến final.
~~~

For primitive types:

~~~java
final int maxAttempts = 3;
// maxAttempts = 5; // Lỗi biên dịch.
~~~

For method parameters:

~~~java
void render(final String message) {
    // message = "Khác"; // Lỗi: gán lại tham số final.
    System.out.println(message);
}
~~~

For a field without a declaration initializer:

~~~java
class User {
    private final String id;

    User(String id) {
        this.id = id; // Gán một lần trong constructor.
    }
}
~~~

A `blank final field` must be assigned according to Java's initialization rules on every normally completing initialization path; it cannot be reassigned afterward. A `final` field referencing a mutable object does not freeze that object's internal state.

## 7. Which Members Cannot Be Overridden Even Without `final`?

Not every superclass member is a valid override point.

| Member | Truly overridable? | Explanation |
| --- | --- | --- |
| Instance method `public/protected`, neither final nor static | Usually yes | If access and signature rules are satisfied |
| Instance method `final` | No | Compiler prohibits overriding |
| Method `private` | No | Not inherited in a way that permits overriding |
| Method `static` | No | May be **hidden** by a subclass static method, subject to restrictions such as final |
| Constructor | No | Constructors are not inherited methods |
| Field, including `final field` | No | Fields can only be **hidden** by name, not dynamically overridden |

### `private` and `static` Do Not Mean Overriding

~~~java
class Parent {
    private void internal() {
        System.out.println("Parent internal");
    }

    static void info() {
        System.out.println("Parent info");
    }
}

class Child extends Parent {
    // Đây là phương thức MỚI, không override private method ở Parent.
    public void internal() {
        System.out.println("Child internal");
    }

    // Đây là static method hiding, không phải instance override.
    static void info() {
        System.out.println("Child info");
    }
}
~~~

~~~java
Parent p = new Child();
p.info();     // Parent info (static ràng buộc theo kiểu khai báo)
// p.internal(); // Không biên dịch: Parent.internal() là private.

Child c = new Child();
c.internal(); // Child internal
~~~

Invoke static methods through class names (`Parent.info()`, `Child.info()`) to avoid confusing them with dynamic polymorphism.

If the superclass declares `static final void info()`, the subclass cannot declare a same-signature static method to hide it. With `private final void internal()`, a subclass may still declare a separate same-named/same-signature method under access rules because that is **not overriding** the superclass private method.

### `abstract` and `final` Cannot Be Combined on the Same Class or Method

These keywords impose opposite requirements:

- An `abstract method` requires a subclass to supply an implementation.
- A `final method` prevents a subclass from supplying an implementation through overriding.
- An `abstract class` may require or allow subclasses to complete its behavior.
- A `final class` prevents any subclass from being declared.

Thus the following declarations are **invalid**:

~~~java
// abstract final class Impossible { }

// abstract class Base {
//     abstract final void execute();
// }
~~~

By contrast, an **abstract class may contain an implemented final method**—as shown by `PaymentProcessor.process()` in the runnable example.

## 8. What If Some Methods Must Be Fixed While Others Remain Extensible?

This is a common situation. Use a **non-final** superclass or an `abstract class`, then mark only the steps that must not be overridden:

~~~java
abstract class ImportJob {
    // Giữ nguyên quy trình.
    public final void run() {
        validate();
        parse();
        save();
    }

    private void validate() {
        System.out.println("Kiểm tra đầu vào chung");
    }

    protected abstract void parse();
    protected abstract void save();
}
~~~

~~~java
class CsvImportJob extends ImportJob {
    @Override
    protected void parse() {
        System.out.println("Đọc CSV");
    }

    @Override
    protected void save() {
        System.out.println("Lưu dữ liệu CSV");
    }
}
~~~

`ImportJob.run()` fixes the step sequence; subclasses specialize `parse()` and `save()`. This is a variation of the **Template Method** pattern.

Importantly, if `parse()` or `save()` throws or mutates invalid state, `final run()` **does not automatically undo** the changes. `final` controls **overriding permissions**; it does not replace error handling, transactions, or synchronization.

## 9. Design Alternatives to Marking a Class `final`

A `final` class enforces **no subclassing**, but sometimes you want **only selected subtypes** rather than unlimited extension.

Since **Java 17**, Java supports `sealed class`:

~~~java
// Ví dụ riêng cho Java 17+, không thuộc bản demo Java 11.
sealed class PaymentMethod permits Cash, Card {
}

final class Cash extends PaymentMethod {
}

final class Card extends PaymentMethod {
}
~~~

Comparison:

| Design | Who may inherit? |
| --- | --- |
| `class Base` (neither final nor sealed) | Classes satisfying accessibility and language rules |
| `final class Base` | No subclass |
| `sealed class Base permits A, B` | Only directly permitted classes; subclasses must declare `final`, `sealed`, or `non-sealed` as required |
| `abstract class Base` | May be subclassed, but the type itself cannot be instantiated directly with `new` |

Do not choose `sealed` merely to replace a keyword. It is useful for an intentionally **finite, well-defined set of variants**. The main runnable example in Section 3 requires only Java 11; this `sealed` example requires Java 17 or later.

For interchangeable behavior, **composition + interface** is worth considering: inject a strategy through a constructor instead of subclassing a `final` class. `final` does not prevent a class from **using** another object.

## 10. Common Compilation Errors and Incorrect Assumptions

| Scenario | Correct conclusion |
| --- | --- |
| `class B extends FinalA` when `FinalA` is a `final class` | Compilation error: cannot inherit |
| Overriding `public final void f()` in a subclass | Compilation error: cannot override |
| Constructing `new FinalA()` when the constructor is accessible | Valid |
| A `final` class implements an interface | Valid |
| An abstract class declares a `final` method | Valid |
| A method marked both `abstract` and `final` | Invalid |
| Overloading a `final method` with different parameters | Valid |
| Declaring `final List<T>` and invoking `add()` | May be valid when the list is mutable |
| Superclass `private` method and a same-named subclass method | Not an override |
| A same-named/signature subclass `static` method | Hiding if legal, not overriding |
| Using `final` to guarantee thread safety | Insufficient; access and mutation must be considered |
| “A final class is always immutable” | False: `Counter` is a counterexample |

### Useful Compilation Failures to Recognize

~~~java
final class Locked {
    void work() {}
}

// class CannotExtend extends Locked {} // ERROR

class Base {
    public final void execute() {}
}

class Derived extends Base {
    // @Override
    // public void execute() {} // ERROR

    // Overload vẫn được phép:
    public void execute(int count) {
        for (int i = 0; i < count; i++) {
            execute();
        }
    }
}
~~~

The failures arise from **compile-time type rules**, not because the JVM discovers incorrect subclass behavior at runtime. Adding `@Override` to intended legal overrides is good practice because the compiler verifies the signature.

## 11. When Should You Avoid `final`?

`final` should express a **design decision**. If an application needs third-party extensions of an API to support valid variations, locking down classes or methods too early can make that API awkward or force convoluted workarounds.

Warning signs include:

- Behavior genuinely needs to be overridden, but the superclass marks it `final` without offering hooks or another abstraction.
- New features frequently require interchangeable implementations through interfaces/strategies, yet dependencies are tied to concrete classes.
- Inheritance is used only to reuse a few utility lines even though the is-a relationship is invalid.
- You assume that marking something `final` automatically solves concurrency, security, immutability, or transaction problems.

A practical rule: **lock down what must remain stable; extend at points with clear contracts**. In domains needing flexible variation, prefer interfaces/composition or controlled hooks over freely overriding a whole workflow.

## 12. Self-Check

**Question 1.** Can a subclass invoke a `final` method?

**Answer:** Yes, when access permits. A subclass cannot **override** its implementation, but may **inherit and use** it.

**Question 2.** Is `final class Printer implements Printable` valid?

**Answer:** Yes. `final` prevents another class from using `extends Printer`, while `implements Printable` states that `Printer` fulfills the interface contract.

**Question 3.** In the payment example, why is `process()` `final` while `CardProcessor.charge()` is still invoked?

**Answer:** `process()` is inherited shared code and cannot be overridden. It invokes the `charge()` hook implemented by subclasses; Java dispatches that hook according to the object's runtime type.

**Question 4.** Does `final List<String> names = new ArrayList<>(); names.add("An");` compile?

**Answer:** Yes. There is no **reassignment** of `names`; calling `add` mutates the referenced list.

**Question 5.** Can a subclass override the superclass method `private void save()`?

**Answer:** No. Where permitted, a subclass may declare a separate same-named/signature method, but it does not override the superclass `private` method.

**Question 6.** Can a `final` class also be `abstract`?

**Answer:** No. `final` prevents subclassing, whereas `abstract` describes a type that cannot be directly instantiated and is designed for subclasses to complete or use.

**Question 7.** If the superclass must preserve `validate → execute → audit` while each subclass implements `execute` differently, where should `final` go?

**Answer:** Put `final` on the coordinating method and expose a `protected abstract` method or suitable hook for `execute`. Handle exceptions and state changes separately because `final` does not imply atomicity.

**Question 8.** To allow exactly three concrete subclasses to extend a class directly, what should you consider in Java 17+?

**Answer:** Consider `sealed class` with `permits`. Unlike `final class`, `sealed class` permits a specified set of subclasses under Java's rules.

**Remember:** A `final method` **prevents method overriding**, a `final class` **prevents subclassing**, and a `final field/variable` **prevents reassignment**. Using each at the right level preserves essential behavior while allowing deliberately designed extension points.
