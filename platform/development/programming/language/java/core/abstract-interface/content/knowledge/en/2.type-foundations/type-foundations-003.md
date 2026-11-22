# Type Inheritance, Code Inheritance, and State Inheritance in Java

The term “inheritance” is often used for three different concepts: **type relationship** (an object can be used through a supertype), **code reuse** (receiving an existing implementation), and **state inheritance** (an instance contains fields defined by a superclass). Distinguishing the three aspects helps decide whether to use `extends`, `implements`, a `default` method, or composition.

## 1. The Three Mechanisms Are Not Synonymous

| Aspect | Question | Typical Mechanism | Limitation |
|---|---|---|---|
| **Type inheritance** | Can a value be used where a supertype is expected? | `class extends`, `class implements`, `interface extends` | Having a subtype relationship does not mean receiving all code or state. |
| **Code inheritance** | Which implementations can be reused? | Superclass concrete methods; interface `default` methods | Not every method is inherited or can be overridden. |
| **State inheritance** | Which instance fields belong to the object? | Instance fields in the `extends` chain | Interfaces do not provide instance fields; `static` fields are not per-object state. |

A declaration can combine multiple aspects:

- `SavingsAccount extends Account`: a subtype relationship; can inherit concrete methods and contains state defined by `Account`.
- `SavingsAccount implements Named`: creates a type relationship with `Named`; can receive an applicable `default` method, but does not receive instance state from the interface.
- `interface Auditable extends Named`: extends the contract and can inherit `default` methods; still has no instance state.
- An `abstract class` can contain fields, constructors, concrete methods, and abstract methods; each member has its own rules.

Java allows only one direct superclass per class, but a class can implement multiple interfaces. Multiple type contracts do not mean multiple stateful superclasses.

## 2. Type Inheritance: Through Which Contracts Can an Object Be Substituted?

For example, `SavingsAccount extends Account` and `Account implements Named`:

```java
SavingsAccount savings = new SavingsAccount("Lan", 100);
Account asAccount = savings;
Named asNamed = savings;
```

Variables with different declared types can still reference **the same object**. Upcasting does not create a copy. The declared type restricts which API can be called; the implementation of an overridden instance method is selected based on the runtime object. The article **Supertype and Subtype Relationships** covers subtypes, LSP, generics, and choosing types for APIs separately.

A type relationship verified by the compiler does not by itself guarantee business behavior. If a subclass breaks the superclass's guarantees, code using the supertype can still fail. Design contracts around behavior that every implementation can fulfill, not just around the name `extends`.

## 3. Code Inheritance: Concrete Methods, Abstract Methods, and Default Methods

A superclass can provide a common algorithm through concrete methods; a subclass can use them directly or override eligible instance methods. Abstract methods only define the parts that subclasses must complete. Constructors are not inherited.

Interfaces can also reuse code through `default` methods:

```java
interface Named {
    String name();

    default String description() {
        return "Định danh: " + name();
    }
}
```

A class that `implements Named` receives the `name()` contract and can use `description()` without duplicating code. The call to `name()` inside the default method dispatches to the object's implementation. This does **not** turn the interface into a stateful superclass.

Rules to remember:

1. `@Override` helps the compiler verify that a method actually overrides; the implementation must not reduce visibility and must conform to return type/checked exception rules.
2. `final` methods cannot be overridden; `static` methods are hidden according to the declared type; `private` methods of a superclass are not overridden by subclasses.
3. `super.method()` calls the superclass implementation when valid; it does not create a second parent object.
4. If two unrelated interfaces provide `default` methods with the same signature, the concrete class usually must override it to choose the behavior. A matching concrete instance method from a superclass takes precedence according to Java's rules. The article **Single Class Inheritance and Multiple Interface Inheritance** goes into depth on these conflict cases.

## 4. State Inheritance: Superclass Fields Reside in the Same Object

A `SavingsAccount` can hold the state declared by `Account`, such as `owner` and `balance`, alongside the subclass's own state. These are parts of **a single instance**, not two independently nested parent/child objects.

```java
abstract class Account {
    private final String owner;
    private long balance;

    protected Account(String owner, long initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư ban đầu âm");
        }
        this.owner = owner;
        this.balance = initialBalance;
    }

    public final String owner() {
        return owner;
    }

    protected final void add(long amount) {
        balance += amount;
    }

    public long balance() {
        return balance;
    }
}
```

- A `private` field still belongs to the state of the subclass object, but subclass code cannot access it directly by field name. The superclass can control operations through methods.
- `protected` grants subclasses access according to Java's rules, but a `protected` mutable field makes it easy for subclasses to break invariants. Prefer `private` fields with a controlled API.
- A `static` field belongs to the class, not as a copy in each object. A field with the same name in a subclass creates **field hiding**, meaning two separate fields, not overriding.
- A `final` reference field cannot be reassigned after initialization, but the object it points to can still be mutable.

Do not infer that a `private` field “disappears” from the child object: it remains part of the state managed by the superclass; only direct access is restricted.

## 5. A Java 17+ Example Combining All Three Mechanisms

Save the following program as `InheritanceKindsDemo.java`:

```java
public class InheritanceKindsDemo {
    interface Named {
        String name();

        default String description() {
            return "Định danh: " + name();
        }
    }

    static abstract class Account implements Named {
        private final String owner;
        private long balance;

        protected Account(String owner, long initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Số dư ban đầu âm");
            }
            this.owner = owner;
            this.balance = initialBalance;
        }

        @Override
        public final String name() {
            return owner;
        }

        protected final void add(long amount) {
            balance += amount;
        }

        protected abstract String kind();

        public String summary() {
            return kind() + " | " + description() + " | số dư=" + balance;
        }
    }

    static final class SavingsAccount extends Account {
        SavingsAccount(String owner, long initialBalance) {
            super(owner, initialBalance);
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }
            add(amount);
        }

        @Override
        protected String kind() {
            return "Tiết kiệm";
        }
    }

    public static void main(String[] args) {
        SavingsAccount savings = new SavingsAccount("Lan", 100);
        Account asAccount = savings;
        Named asNamed = savings;

        System.out.println(asNamed.description());
        System.out.println(asAccount.summary());
        savings.deposit(50);
        System.out.println(asAccount.summary());
        System.out.println(asNamed == asAccount);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 InheritanceKindsDemo.java
java InheritanceKindsDemo
```

Stdout:

```text
Định danh: Lan
Tiết kiệm | Định danh: Lan | số dư=100
Tiết kiệm | Định danh: Lan | số dư=150
true
```

In the example:

- `SavingsAccount extends Account` establishes a subtype relationship, receives the `summary()` method, and holds the `owner`/`balance` state in the same instance.
- `Account implements Named`; `name()` fulfills the interface contract and `description()` is code inherited from the default method.
- `summary()` calls `kind()`, which is implemented by the subclass; the common algorithm remains in the superclass.
- `add()` controls balance updates instead of letting the subclass modify the field directly.
- `asNamed == asAccount` prints `true`: two references of different types point to the same object.

This is an example of the mechanisms, not a complete financial model: real systems need to handle overflow, concurrency, and appropriate currency types.

## 6. One Object, Multiple Views of State

With the classes in `InheritanceKindsDemo` from section 5, the following snippet can be placed in `main`:

```java
SavingsAccount savings = new SavingsAccount("Lan", 100);
Account asAccount = savings;
savings.deposit(50);
System.out.println(asAccount.summary());
// Tiết kiệm | Định danh: Lan | số dư=150
```

`asAccount` and `savings` point to the same object; updating `balance` through the subclass is visible to the superclass's `summary()`. The common algorithm of `summary()` is inherited, while the `kind()` call inside it dispatches to `SavingsAccount`'s implementation.

If a subclass declares a field with **the same name** as in the superclass, they are two different fields (field hiding); field access does not dynamically dispatch like an overridden method. Avoid relying on hiding to change behavior; encapsulate state using `private` fields and controlled methods instead. The article **Reference Types and Actual Object Types** separately illustrates the field hiding case.

## 7. Constructors and Initialization Order

Constructors are not inherited. When instantiating a subclass, Java initializes state along the superclass chain before completing the subclass's initializers/constructor. A subclass constructor calls `super(...)` to select an appropriate superclass constructor; if the superclass has no available no-argument constructor, the default call is insufficient and the subclass must explicitly call an appropriate constructor.

Avoid calling overridable methods from a superclass constructor. Dynamic dispatch can enter the subclass when the subclass's fields are not yet fully initialized, leading to unpredictable results or breaking invariants.

## 8. Choosing Inheritance or Composition?

| Need | Typically Suitable Choice |
|---|---|
| A family of objects sharing state, constructors, and invariants | An `abstract class` or a superclass designed to be stable |
| Classes from different families needing the same contract | An `interface` |
| Wanting to share small default behavior that does not depend on instance state | A `default` method when it makes sense |
| An object “has-a” component or needs to swap implementations independently | Composition/delegation |
| Need to preserve data invariants | `private` fields and controlled methods |

Do not use `extends` just to save a few lines. A `Car` having an `Engine` fits composition better than `Car extends Engine`; delegation allows swapping the component without locking the class into a semantically inappropriate superclass.

## 9. Self-Check

1. A class implements an interface with an abstract method and implements that method itself: is there type inheritance? **Yes**; it does not receive an implementation from the abstract method or instance state from the interface.
2. An interface has a default method: what does an implementing class receive? **A type relationship and implementation reuse**, when no override/conflict takes precedence; it does not receive instance state.
3. Does a subclass not directly accessing a superclass's `private` field mean the field does not belong to the object? **No**; the field is still part of the object's state, just encapsulated by the superclass.
4. When should composition be used? When a “has-a/uses-a component” relationship fits better than “is-a”, or when behavior needs to vary independently.

**Remember:** type inheritance is about substitutability, code inheritance is about reusable implementations, and state inheritance is about instance data defined by a superclass. `extends class` typically combines these mechanisms; `implements interface` creates a type relationship and sometimes reuses default code, but does not provide instance state.
