# Shared Fields and State of Subclasses in Abstract Classes (Java)

## 1. Objectives and Meaning of Inherited State

An abstract class (`abstract class`) in Java can define **instance fields** that all subclasses use, along with constructors, data validation rules, and unified processing methods. For example, `SavingsAccount` and `CheckingAccount` are two types of accounts; both have an owner and a balance, even though their withdrawal policies differ.

After this lesson, you should be able to distinguish:

- **Shared in structure and behavior:** the superclass declares the fields and methods once, and subclasses inherit them.
- **Per-object:** each `new SavingsAccount(...)` or `new CheckingAccount(...)` has an instance state copy belonging to **that object itself**. Increasing the balance of one account does not increase the balance of another account.
- **Truly shared across objects:** a `static` field belongs to the declaring class, not as a separate copy for each object.

`abstract` does not forbid the superclass from owning fields, initializing data, or writing concrete methods. It only forbids directly creating an instance of the abstract class and allows declaring abstract methods. A concrete subclass will complete the missing behavior.

## 2. When Should You Place Fields in the Superclass?

Place data in the superclass when that data exists with the **same meaning** across every subclass in the hierarchy, and can share the same validation or management logic. Keep data separate in a subclass if only that subclass needs it.

| Data | Where should it be placed? | Explanation |
| --- | --- | --- |
| `owner` (account owner) | `Account` | Every account has an owner |
| `balanceCents` (balance in cents) | `Account` | All are subject to the balance update rules |
| `freeWithdrawals` (number of free withdrawals) | `SavingsAccount` | Only used by savings accounts |
| Total account statistics | Separate management component, when appropriate | Not state belonging to a single account |

Simple rule: **only a field that every subclass must have**, with the same contract and invariant, is a good candidate to move up to the superclass. If you add a new subclass and that field has no meaning for it, revisit the inheritance structure.

## 3. Complete Java 17 Example: Superclass Maintains the Invariant, Subclasses Add Specific Rules

The example uses `long` to store **cents** instead of using `double` to represent money. Both account types inherit the same `owner` and `balanceCents`; the superclass is responsible for preventing a negative balance, while each subclass decides its own withdrawal policy.

Create the file **`Demo.java`**:

```java
public class Demo {
    public static void main(String[] args) {
        SavingsAccount savings = new SavingsAccount("An", 10_000, 2);
        CheckingAccount checking = new CheckingAccount("Bình", 20_000);

        savings.deposit(5_000);
        savings.withdraw(2_000);
        checking.withdraw(2_000);

        Account account = savings; // Same object, superclass-typed reference.

        System.out.println("Savings: " + savings.balanceCents()
                + " cents; free withdrawals: " + savings.freeWithdrawals());
        System.out.println("Checking: " + checking.balanceCents() + " cents");
        System.out.println("Account reference: " + account.owner()
                + " / " + account.balanceCents() + " cents");
    }
}

abstract class Account {
    private final String owner;
    private long balanceCents;

    protected Account(String owner, long openingCents) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner is required");
        }
        if (openingCents < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.owner = owner;
        this.balanceCents = openingCents;
    }

    public final String owner() {
        return owner;
    }

    public final long balanceCents() {
        return balanceCents;
    }

    public final void deposit(long cents) {
        if (cents <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balanceCents = Math.addExact(balanceCents, cents);
    }

    // Operation for subclasses to use, always checks the invariant.
    protected final void debit(long cents) {
        if (cents <= 0 || cents > balanceCents) {
            throw new IllegalArgumentException("invalid debit");
        }
        balanceCents -= cents;
    }

    public abstract void withdraw(long cents);
}

final class SavingsAccount extends Account {
    private int freeWithdrawals;

    SavingsAccount(String owner, long openingCents, int freeWithdrawals) {
        super(owner, openingCents);
        if (freeWithdrawals < 0) {
            throw new IllegalArgumentException("negative withdrawal quota");
        }
        this.freeWithdrawals = freeWithdrawals;
    }

    @Override
    public void withdraw(long cents) {
        if (freeWithdrawals == 0) {
            throw new IllegalStateException("no free withdrawals left");
        }
        debit(cents); // Only decrement the count after deducting funds succeeds.
        freeWithdrawals--;
    }

    public int freeWithdrawals() {
        return freeWithdrawals;
    }
}

final class CheckingAccount extends Account {
    CheckingAccount(String owner, long openingCents) {
        super(owner, openingCents);
    }

    @Override
    public void withdraw(long cents) {
        if (cents <= 0) {
            throw new IllegalArgumentException("withdrawal must be positive");
        }
        debit(Math.addExact(cents, 100)); // Charge an additional fee of 100 cents.
    }
}
```

Compile and run (JDK 17+):

```bash
javac Demo.java
java Demo
```

Exact output:

```text
Savings: 13000 cents; free withdrawals: 1
Checking: 17900 cents
Account reference: An / 13000 cents
```

**How to read the example:**

- `SavingsAccount` starts with 10,000 cents, deposits 5,000, and withdraws 2,000 ⇒ 13,000; the 2-withdrawal quota decreases to 1.
- `CheckingAccount` starts with 20,000, withdraws 2,000 plus a fee of 100 ⇒ 17,900. The two objects do not share a single balance field.
- `Account account = savings` does not create a new account; it is **another reference to the same object** `savings`. Therefore, `account.balanceCents()` sees 13,000.
- The `Account` class manages the `private long balanceCents` field. Subclasses do not assign to it directly, and instead call `debit()`; the validation logic remains consistent.
- `owner` is a `final` field of each instance; `freeWithdrawals` is a field specific to the subclass, without forcing checking accounts to own it.
- `withdraw()` is declared abstract in the superclass and implemented in each subclass. This method is the **varying behavior**, while the balance-protection operation is the **shared behavior**.

This is an example of state design and inheritance. Real-world monetary systems additionally require atomic transactions, persistence, and concurrency control; the code above should not be treated as a complete banking transaction solution.

## 4. Why Prefer `private` Fields in Abstract Classes?

A subclass inherits **the data stored inside the object**, even when subclass code cannot directly access a `private` field of the superclass. You can grant permission to **perform behavior** through methods, rather than letting subclasses modify data arbitrarily.

| Modifier | Who can read/modify the field directly? | Recommendation |
| --- | --- | --- |
| `private` | Code within the declaring class; subclasses use the superclass API | Recommended by default for mutable state and invariants that need protection |
| No modifier (*package-private*) | Code in the same package | Use when you genuinely want to share within the package |
| `protected` | Same package and subclasses according to Java's `protected` rules | Use judiciously; mutable fields are easily modified incorrectly |
| `public` | Any code permitted to access the class | Rarely appropriate for mutable instance fields |

**Do not mistakenly think `protected` means "only subclasses can access it".** Classes in the same package also have access; subclasses in a different package are still subject to restrictions on the receiver expression of the access. Placing `private` fields and `protected final` methods usually makes it easier to preserve invariants.

In the example:

- `private final String owner`: the reference can only be assigned during initialization; `String` is an immutable type.
- `private long balanceCents`: the data is mutable, but every update path stays under `Account`'s control.
- `public final void deposit(...)`: subclasses cannot override it to bypass validation; `Math.addExact` catches `long` overflow during addition.
- `protected final void debit(...)`: subclasses can request a valid debit operation without altering the validation algorithm.
- `public abstract void withdraw(...)`: a concrete subclass must provide an implementation, if it does not inherit a suitable concrete implementation.

**Note on `final`:** `final` on a reference field only forbids reassigning the reference; it does not freeze the referenced object. For example, `final List<String> tags` still allows `tags.add("new")` when the list is mutable. For fields holding a `List`, `Map`, or mutable object in the superclass, consider `List.copyOf(...)`, defensive copies, and controlled update methods. Avoid returning internal mutable data structures directly through getters.

## 5. Constructors and State Initialization Timing

The abstract superclass constructor runs during subclass object creation, typically via `super(...)`, to set up the part of the state owned by the superclass. Instance fields start with default values; superclass initialization and constructor complete before the subclass's initializers and constructor body complete.

Avoid calling overridable instance methods from a superclass constructor: Java still dispatches to the subclass when the subclass's fields may not yet have been assigned their expected values. When designing a class that maintains invariants, the constructor should validate and assign the data managed by that class itself; detailed constructor examples and rules are covered in the lesson on constructors.

## 6. Field Hiding: Fields Are **Not** Overridden Like Methods

If a subclass declares a field with the same name as a field in the superclass, the new field **hides** the old field name; it does not replace the old field. Both fields still exist. When accessing a field, Java uses the **declared type of the reference expression**; when calling an overridden instance method, Java dispatches based on the **actual type of the object**.

Save the following standalone code as **`FieldHidingDemo.java`**:

```java
public class FieldHidingDemo {
    public static void main(String[] args) {
        Parent child = new Child();

        System.out.println(child.label);
        System.out.println(child.getLabel());
    }
}

class Parent {
    String label = "parent";

    String getLabel() {
        return label;
    }
}

class Child extends Parent {
    String label = "child";

    @Override
    String getLabel() {
        return label;
    }
}
```

```bash
javac FieldHidingDemo.java
java FieldHidingDemo
```

Output:

```text
parent
child
```

`child.label` selects the field in `Parent` because the variable `child` has type `Parent`. `child.getLabel()` calls the overridden method in `Child` because the actual object is `Child`.

You should not write two fields with the same meaning in a superclass and subclass expecting to "override state". Even if the superclass field is `private` and subclass code is allowed to have its own field with the same name, doing so still creates two storage locations that can conflict. Define one field where it properly belongs, and extend behavior using methods.

## 7. `static` Fields Do Not Represent Per-Object State

Regular instance fields belong to each individual object; two separately created accounts have two separate balances. In contrast, a `static` field belongs to the declaring class and is shared across instances. Therefore, do not use `static` for balances or per-object business state.

Similarly, `static` methods do not participate in dynamic dispatch like instance methods, and mutable `static` state requires concurrency considerations. Detailed rules for `static`, `final`, and `private`, including hiding and encapsulation, are covered in the lesson on members and modifiers.

## 8. Protecting Shared Invariants and Extensibility

An **invariant** is a condition that must always hold true for a valid object state. In `Account`, the rule `balanceCents >= 0` is enforced by the constructor, `deposit()`, and `debit()`.

Preferred design practices:

- The superclass constructor rejects invalid data **at object creation time**.
- Update methods validate inputs before modifying state.
- Subclasses invoke superclass-controlled behavior, avoiding direct assignment to mutable superclass fields.
- If multiple fields are modified, determine the ordering so that an exception does not leave a partial state. For example, `SavingsAccount` only decrements `freeWithdrawals` after `debit()` succeeds.
- If a new requirement changes a fundamental invariant (such as allowing an account to overdraw), redesign the superclass contract consistently instead of creating shortcuts to modify data in subclasses.

For mutable objects used by multiple threads, `private`, `final` on methods, or getters **do not automatically guarantee thread safety**. Two threads can read the same old value and overwrite each other. `volatile` ensures threads see updates to the marked field, but read–compute–write increment/decrement operations do not automatically become atomic. Depending on the usage model, appropriate synchronization, locking, or atomic update mechanisms are needed. This is an additional concern when sharing objects; field inheritance by itself does not provide any synchronization mechanism.

## 9. Inheritance, Interfaces, and Composition

- Use an **abstract class** when subclasses truly have an *is-a* relationship, sharing **instance state**, invariants, and behavior, while still having extension points that subclasses must implement.
- Use an **interface** to describe a shared contract, especially when classes are not in the same hierarchy or need to implement multiple contracts. A Java interface does not have instance fields for each implementation to inherit; fields declared in an interface are implicitly `public static final`.
- Use **composition** when the shared part is a pluggable capability/component rather than a stable is-a relationship. For example, `FeePolicy` can be an object held by `Account` to vary fee calculation without creating a subclass for every policy combination.

Do not push a field up to the superclass simply because "classes have duplicate code". Ask whether that field carries the same meaning, lifecycle, and invariant across all subclasses.

## 10. Common Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Declaring `static` for each object's balance | All instances see the same single balance | Use an instance field |
| Leaving a mutable field `protected` for any subclass to modify | Subclasses can break the invariant | Keep it `private`, expose controlled methods |
| Moving a field needed by only one subclass up to the superclass | Other subclasses carry meaningless state | Keep the field in the specific subclass |
| Hiding a field with a same-named declaration | Creates two independent fields that easily get out of sync | Store the field in one place; use methods to customize |
| Superclass constructor calling an overridden method | Reads uninitialized subclass state | Do not dispatch open methods in constructors |
| Returning a mutable collection directly from a getter | External code modifies state bypassing validation | Use defensive copies and validated update APIs |
| Thinking a `final` reference makes the object immutable | The mutable object can still be modified | Protect the referenced object |
| Sharing a mutable object across multiple threads without synchronization | Lost updates, corrupted data | Use a synchronization mechanism suited to the business logic |

## 11. Self-Check and Application

**Exercise:** Add `StudentAccount`, where each object has a `schoolId` and a free transaction quota.

1. Where should `schoolId` be placed? **`StudentAccount`**, because other accounts do not have a school ID.
2. Where should `balanceCents` be placed? **`Account`**, because it is shared data and a shared invariant.
3. Should a subclass modify `balanceCents` directly? **No**; call the update behavior protected by the superclass.
4. Do two `StudentAccount` objects share a single balance? **No**, unless you intentionally design another shared state source; regular instance fields belong to each individual object.
5. If `Account a = new StudentAccount(...)`, where does `a.owner()` return state from? **From that very `StudentAccount` object** that `a` points to, which stores the inherited `Account` portion.
6. If fee calculation depends on multiple policies that vary independently of the account type, what should be used? **Consider composition**, for example a `FeePolicy` attached to the account.

**Key takeaway:** An abstract class is where you define **shared fields and shared state protection mechanisms**; each subclass object still owns **its own instance state copy**. Place fields according to their domain meaning, prefer `private` encapsulation, initialize via `super(...)`, and allow subclasses to customize **behavior**, not arbitrarily break invariants.
