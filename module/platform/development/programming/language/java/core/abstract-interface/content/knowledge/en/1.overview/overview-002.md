# Distinguishing Abstraction from Encapsulation and Inheritance in Java

## Objectives

After this lesson, you will be able to accurately explain three principles that often appear together in object-oriented programming (OOP):

- **Abstraction:** defines *what capabilities an object provides* and hides implementation details that users do not need to know.
- **Encapsulation:** manages *who can access or modify internal state, and how*, in order to protect the object's rules.
- **Inheritance:** builds one type based on another, receiving permitted inherited members and forming a subtype–supertype relationship.

They can work together in the same design, but they solve three different problems. Java has `interface`, `abstract class`, access levels, and `extends`/`implements` to realize them; you should not equate a single keyword with an entire principle.

## 1. Quick Comparison

| Aspect | Abstraction | Encapsulation | Inheritance |
|---|---|---|---|
| Key question | "What is this object used for?" | "How are internal state and rules protected?" | "How does this type relate to another type?" |
| Focuses on | Observable contracts/capabilities, omitting non-essential details | Access boundaries, controlled modification, and data invariants | The *is-a* relationship, behavior reuse, type substitutability |
| Common Java tools | `interface`, `abstract class`, intentional public methods | `private`, state-controlling APIs, immutability, defensive copies | `extends`, `implements`, `super`, `@Override` |
| Example | `PaymentMethod.pay(amount)` describes the payment operation | `Wallet` keeps `balance` `private` and only deducts money through validity checks | `GiftWallet extends Wallet` |
| What does it not guarantee? | Having a good contract does not guarantee that state is well protected | Protected data does not guarantee a sufficiently simple API or a supertype | Having a supertype does not guarantee a well-abstracted API or safe encapsulation |

**How to remember:** abstraction chooses what *to expose*; encapsulation controls what *is allowed to be acted upon*; inheritance establishes a *subtype-to-supertype* relationship. "Hiding details" appears in both abstraction and encapsulation, but the purpose is different.

## 2. Abstraction: Working Through Contracts

Suppose a payment system has gift wallets, bank cards, and external payment gateways. The order-processing part only needs to know that a payment method takes an amount and returns a result. It does not need to know how to call the bank API, how to check limits, or how the balance is stored.

```java
interface PaymentMethod {
    String pay(int amount);
}
```

`PaymentMethod` is a **behavioral contract**: callers depend on `pay` rather than a specific implementation class. Different classes can implement the contract in their own ways; the calling side does not need to change just because the payment algorithm changes.

The core point of abstraction **is not simply having an `interface`**. A regular class with a small, clear API can also provide a useful abstraction. Conversely, an `interface` that exposes dozens of internal details can still be a poorly designed abstraction.

In Java, common choices include:

- **`interface`:** expresses a role/capability for multiple classes that do not share a direct superclass to conform to. Besides abstract methods, modern Java allows `default`, `static`, and some `private` methods in an interface; fields declared in an interface are `public static final` constants.
- **`abstract class`:** expresses an incomplete base class that can both specify abstract methods and share state, constructors, and common implementations. An `abstract` class cannot be instantiated directly.

When designing a good abstraction, clearly state the meaning of parameters, results, error cases, and rules that callers can expect. Merely declaring method names without specifying expected behavior leaves the contract ambiguous.

## 3. Encapsulation: Protecting State and Rules

A wallet has a non-negative balance. If `public int balance` is declared, any code can write `wallet.balance = -999;` and break that rule. Encapsulation places state behind an access boundary and only allows changes through validated operations.

```java
private int balance;

public int getBalance() {
    return balance;
}

protected boolean deduct(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("Số tiền phải dương");
    }
    if (amount > balance) {
        return false;
    }
    balance -= amount;
    return true;
}
```

*This snippet illustrates members inside a class and is not a standalone Java program.* The complete runnable example in Section 5 has similar members.

What matters is not simply writing `private` and automatically generating getters/setters for every field:

- If there is a public `setBalance(int value)` that allows arbitrary values, state can still be modified improperly even though the field is `private`.
- There is no need to expose every field as a getter. Provide only the operations that the business domain actually needs, such as `deposit` or `withdraw`.
- For mutable objects such as `List` or `Date`, returning an internal reference directly via a getter can leak modification rights; consider a defensive copy or an unmodifiable view, depending on the contract.
- Immutable state often helps reduce the bug surface, but you must also ensure that internally referenced objects cannot be unintentionally modified from the outside.

Encapsulation protects an **invariant**: something that must always hold true for an object at valid observation points, such as `balance >= 0`. It also allows changing internal storage without forcing calling code to change when the API is kept stable.

## 4. Inheritance: Subtype–Supertype Relationships

In Java, `class GiftWallet extends Wallet` states that `GiftWallet` is a kind of `Wallet`. The subtype can use accessible members from the superclass and override overridable methods to specialize behavior.

- `extends` between classes creates a class inheritance relationship; a class has only **one direct superclass**.
- `implements` allows a class to implement **multiple interfaces**, forming a subtype relationship under interface contracts. An interface can also `extends` multiple other interfaces.
- `super(...)` calls a superclass constructor. Constructors are not inherited like methods; `private` members of the superclass do not become members directly accessible from the subclass.
- `@Override` helps the compiler check that the override has the matching signature. `final` methods cannot be overridden; `static` methods can be hidden (*hiding*) and do not participate in polymorphic overriding like instance methods.

Inheritance is appropriate when the **is-a** relationship truly holds and a subtype instance can be used wherever the supertype is required while still satisfying the published contract. This is the idea behind the Liskov Substitution Principle (LSP). For example, a subclass that makes `pay` arbitrarily reject all valid amounts contrary to the supertype's commitment can violate the contract, even though the Java syntax is valid.

**Do not choose inheritance just to reuse a few lines of code.** If the true relationship is **has-a** (having or using a component), consider composition: a `CheckoutService` *holds a reference to* a `PaymentMethod` to use payment functionality, rather than `extends PaymentMethod`. Composition generally reduces dependence on superclass details and makes replacing collaborators easier.

## 5. Complete Java 17 Example: All Three Principles in One Program

Save the entire following snippet into a file named **`ConceptsDemo.java`**. The code is standalone and uses integers as a hypothetical currency unit to focus on OOP; real-world monetary systems require a more accurate model, transaction policies, and appropriate concurrency handling.

```java
interface PaymentMethod {
    String pay(int amount);
}

abstract class Wallet implements PaymentMethod {
    private int balance;

    protected Wallet(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư đầu phải không âm");
        }
        this.balance = initialBalance;
    }

    public final int getBalance() {
        return balance;
    }

    protected final boolean deduct(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        if (amount > balance) {
            return false;
        }
        balance -= amount;
        return true;
    }
}

final class GiftWallet extends Wallet {
    GiftWallet(int initialBalance) {
        super(initialBalance);
    }

    @Override
    public String pay(int amount) {
        return deduct(amount)
                ? "Đã thanh toán " + amount
                : "Không đủ số dư";
    }
}

public class ConceptsDemo {
    public static void main(String[] args) {
        GiftWallet wallet = new GiftWallet(100);
        PaymentMethod method = wallet;

        System.out.println(method.pay(40));
        System.out.println("Số dư còn lại: " + wallet.getBalance());
        System.out.println(method.pay(100));
        System.out.println("Số dư còn lại: " + wallet.getBalance());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 ConceptsDemo.java
java ConceptsDemo
```

Expected output on stdout:

```text
Đã thanh toán 40
Số dư còn lại: 60
Không đủ số dư
Số dư còn lại: 60
```

**Design breakdown:**

1. **Abstraction:** `PaymentMethod` specifies the `pay` capability that callers use. The variable `PaymentMethod method` does not need to know the internal deduction algorithm. The call `method.pay(40)` is dispatched to `GiftWallet`'s implementation at runtime.
2. **Encapsulation:** `Wallet.balance` is `private`; external code cannot assign to it directly. The constructor rejects negative balances; `deduct` rejects non-positive amounts and prevents the balance from dropping below 0. `getBalance` allows read-only access. `protected final deduct` lets subclasses use the validated operation without directly modifying the private field themselves.
3. **Inheritance:** `GiftWallet extends Wallet` receives the accessible balance-management behavior from the superclass, calls `super(initialBalance)`, and implements `pay`. Because `Wallet implements PaymentMethod`, a `GiftWallet` object can also be used wherever a `PaymentMethod` is needed.
4. **Polymorphism, a related concept:** a variable declared with the interface type `PaymentMethod` references an actual `GiftWallet` object; Java selects the corresponding overridden instance method at runtime. Polymorphism is often enabled by abstraction and subtype relationships, but it is not synonymous with the three principles above.

The line `method.pay(100)` returns "Không đủ số dư" ("Insufficient balance") because only 60 remains. After the failed call, the balance is still 60. This is a demonstration of controlling state changes through encapsulation. The sample example does not handle multiple threads and is not intended as a complete e-wallet model.

## 6. Three Independent Principles That Can Work Together

**Abstraction without encapsulation:** a class implementing `PaymentMethod` may still expose `public int balance`. Callers have a payment contract, yet are still allowed to corrupt the state. The existence of an interface does not automatically lock down internal fields.

**Encapsulation without inheritance:** a `final Counter` class holding `private int count` and providing `increment()` and `getCount()` can be well encapsulated without defining any subclasses of its own. Every Java class has a relationship with `Object`, but this encapsulated design does not depend on creating a business inheritance hierarchy.

**Inheritance with weak abstraction:** a subclass may `extends` a superclass that exposes too many unrelated operations. Reusing code does not automatically turn an API into a clear contract.

**All three combined:** an interface describes what users need; a base class holds and controls state; a specialized class extends the behavior of the base class. This is a reasonable organization *when* a subtype relationship truly exists. Not every problem necessarily needs all three techniques.

## 7. How to Decide During Design

| Scenario | Prioritize thinking about | Why |
|---|---|---|
| Multiple ways to send notifications, but the caller only needs `send(message)` | Abstraction through an appropriate contract | The caller does not depend on SMTP, HTTP, or a specific mechanism |
| Balance, age, or order status must obey rules | Encapsulation and state-transition APIs | Prevents external code from putting the object into an invalid state |
| `SavingsAccount` is truly an `Account` under the stated contract | Inheritance with LSP verification | The subtype can be used wherever the supertype is required |
| `Car` uses `Engine` | Composition | A car **has** an engine; it **is** not an engine |
| Multiple classes only share a few utility functions | Composition or helper service | Avoids forcing an artificial subtype relationship |

An effective practical workflow: (1) identify the capabilities external code needs to use; (2) identify which state, rules, and data must be protected; (3) only finally decide whether there is a genuine subtype relationship or whether objects should be composed. These steps serve design, not a mandatory rule to be applied mechanically to every program.

## 8. Common Misconceptions

**"Abstraction = `abstract class`, encapsulation = `private`, inheritance = `extends`."** These are only some of the syntactic tools. Abstraction can come from an interface or the public API of a regular class; encapsulation requires controlling behavior and invariants; subtype relationships also arise via `implements`.

**"Abstraction and encapsulation both hide details, so they are the same."** Abstraction decides *how users view and use capabilities*; encapsulation controls *access rights, how state is modified, and how invariants are preserved*. An API can be simple yet expose mutable state, or protect state carefully yet still have a cumbersome API.

**"`private` fields + getters/setters for everything is good encapsulation."** Unvalidated public setters can negate the benefits. Prefer actions with business meaning and validate conditions before making changes.

**"Inheritance is always better than composition because of code reuse."** Inheritance binds the subtype to the supertype's contract and behavior. When you only need to use another object's functionality, composition is usually more reasonable.

**"Overriding is just rewriting a method with the same name."** Overriding requires the right signature and Java's constraints; more importantly, the new behavior must preserve the contract that users of the supertype are entitled to expect. You should use `@Override` to catch mistakes at compile time.

**"Interfaces only have abstract methods, and abstract classes only have abstract methods."** False in modern Java: interfaces can have `default`/`static` methods and `private` helper methods; abstract classes can contain data, constructors, and implemented methods.

## 9. Self-Check

1. A `BankAccount` has `private balance` yet allows `setBalance(-500)`. Is that sufficient for good encapsulation? **No**: the state is not protected by validity rules.
2. `OrderService` accepts a `PaymentMethod` parameter instead of `GiftWallet`. Which principle stands out? **Abstraction**: depending on a shared contract; polymorphism allows multiple implementations.
3. `Cat extends Animal` to reuse and specialize `makeSound()` behavior. Which relationship is being used? **Inheritance**; you need to check whether every `Cat` satisfies the `Animal` contract.
4. Does `Car extends Engine` just to call `start()` make sense? **No**: the actual relationship is *has-a*, so consider having `Car` hold an `Engine` object.
5. Is it possible to design a well-encapsulated class without creating a separate interface or abstract class? **Yes**: keep state private, provide controlled operations, and maintain invariants.

**Key takeaway when reading Java code:** look at the **API/contract** to identify abstraction; look at **state, access permissions, and invariant checks** to evaluate encapsulation; look at **`extends`/`implements` relationships and substitutability** to evaluate inheritance/subtyping.
