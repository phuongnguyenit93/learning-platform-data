# Super Call Chain and Passing Required Data During Java Object Initialization

When creating a subclass object, Java must run the constructor chain of its parent classes. Each layer is responsible for initializing the data that layer owns. This is especially useful with an abstract class: an abstract class cannot be instantiated directly, yet its constructor still runs when a concrete subclass is created.

This lesson focuses on **super(...)**, **this(...)**, and requiring subclasses to pass all necessary data to the superclass. Details about field initializer order belong to the lesson “Initialization Order of Fields, Initializer Blocks, and Constructors”; the risk of calling an overridden method in a constructor is analyzed separately in a dedicated lesson.

## 1. Tracing the Constructor Chain

~~~text
Object
  ↑
Entity (abstract class)
  ↑
Account
  ↑
PremiumAccount
~~~

When creating `new PremiumAccount(...)`, each constructor only calls its direct superclass. PremiumAccount calls Account, Account calls Entity, and the chain continues to Object. These are multiple calls on **one object**, not multiple nested parent objects.

Interfaces do not have constructors and do not add a layer to this chain, even though a class can implement multiple interfaces.

## 2. Required Data Is Not Inferred Automatically

In Java 17, if the superclass only declares `Base(String code)`, no compiler-generated default constructor `Base()` exists. The subclass constructor at the end of the `this(...)` chain must call a valid, accessible superclass overload using `super(code)`; the compiler does not automatically fill in the missing data.

A `Child(String code)` signature requires the caller to provide an argument at the syntactic level, while the `Base` constructor is where values such as null or an empty string are validated. When normalizing arguments for `super(...)`, parameters, constants, or static helpers can be used; do not rely on instance fields of the object being initialized. The full example in the next section shows how the superclass owns validation while the subclass only supplies the data.

## 3. Requiring Subclasses to Pass Data to an Abstract Class

An abstract class often owns common fields such as an identifier or owner. A parameterized constructor forces the subclass to pass data as soon as the object is created; the superclass checks the data itself and establishes its invariants.

Save the runnable example to **Main.java**:

~~~java
import java.util.Objects;

public class Main {
    interface Auditable {
        String auditLabel();
    }

    static abstract class AccountRecord {
        private final String id;
        private final String owner;

        protected AccountRecord(String id, String owner) {
            this.id = requireNonBlank(id, "id");
            this.owner = requireNonBlank(owner, "owner");
            System.out.println("AccountRecord constructed");
        }

        private static String requireNonBlank(String value, String field) {
            Objects.requireNonNull(value, field + " must not be null");
            if (value.isBlank()) {
                throw new IllegalArgumentException(field + " must not be blank");
            }
            return value;
        }

        public final String id() {
            return id;
        }

        public final String owner() {
            return owner;
        }

        public abstract String summary();
    }

    static final class PremiumAccount extends AccountRecord
            implements Auditable {
        private final String tier;

        PremiumAccount(String id, String owner, String tier) {
            super(id, owner);
            this.tier = Objects.requireNonNull(tier, "tier");
            System.out.println("PremiumAccount constructed");
        }

        @Override
        public String summary() {
            return id() + " | " + owner() + " | " + tier;
        }

        @Override
        public String auditLabel() {
            return id() + "/" + tier;
        }
    }

    public static void main(String[] args) {
        PremiumAccount account =
                new PremiumAccount("P-100", "Linh", "GOLD");
        System.out.println(account.summary());
        System.out.println("Audit: " + account.auditLabel());

        try {
            new PremiumAccount("", "Linh", "GOLD");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac Main.java
java Main
~~~

Stdout:

~~~text
AccountRecord constructed
PremiumAccount constructed
P-100 | Linh | GOLD
Audit: P-100/GOLD
id must not be blank
~~~

What to observe:

1. AccountRecord is abstract, yet its constructor still runs via `super(id, owner)`.
2. AccountRecord owns and validates id and owner, then stores them in private final fields. PremiumAccount cannot assign those fields directly.
3. Auditable is only a behavioral contract; this interface has no constructor and does not participate in the super chain.
4. Only after the parent constructor returns does the PremiumAccount constructor proceed to assign tier.
5. If id is empty, the parent constructor throws an exception and the PremiumAccount constructor does not reach the second print line. The constructor signature enforces supplying arguments; the validation logic enforces that the values are actually valid.

Constructors should limit external side effects. If the subclass also has its own data that may be invalid, overall initialization can still fail after the superclass has run; so do not send messages, register callbacks, or publish this during construction.

## 4. Using this(...) to Avoid Duplicate Checks

`this(args)` calls another constructor in the same class. A primary constructor can centralize validation and field assignment, while a shorter overload provides default values:

~~~java
public class TicketDemo {
    static class Base {
        Base(String owner) {
            System.out.println("Base(" + owner + ")");
        }
    }

    static class Ticket extends Base {
        private final int quantity;

        Ticket(int quantity) {
            this("guest", quantity);
            System.out.println("Ticket shortcut");
        }

        Ticket(String owner, int quantity) {
            super(owner);
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            this.quantity = quantity;
            System.out.println("Ticket(" + owner + ", " + this.quantity + ")");
        }
    }

    public static void main(String[] args) {
        new Ticket(2);
    }
}
~~~

Stdout:

~~~text
Base(guest)
Ticket(guest, 2)
Ticket shortcut
~~~

The chain is Ticket(int) → Ticket(String, int) → Base(String), then returns to the remainder of Ticket(int). This is still one Ticket object; the class initializers do not run twice. In Java 17, a this(...) or super(...) call must come first in a constructor, and a constructor cannot place both calls directly there.

## 5. Splitting Responsibilities Across Multiple Layers

~~~java
abstract class BaseEntity {
    private final String id;

    protected BaseEntity(String id) {
        this.id = java.util.Objects.requireNonNull(id, "id");
    }

    public final String id() {
        return id;
    }
}

abstract class OwnedEntity extends BaseEntity {
    private final String owner;

    protected OwnedEntity(String id, String owner) {
        super(id);
        this.owner = java.util.Objects.requireNonNull(owner, "owner");
    }

    public final String owner() {
        return owner;
    }
}

final class Document extends OwnedEntity {
    private final String title;

    Document(String id, String owner, String title) {
        super(id, owner);
        this.title = java.util.Objects.requireNonNull(title, "title");
    }

    public String description() {
        return id() + ": " + title + " (" + owner() + ")";
    }
}
~~~

These are valid declarations, with no main method. When creating a Document, BaseEntity owns id, OwnedEntity owns owner, and Document owns title. Each constructor validates the data managed by its own layer. If a system needs too many classes just to pass a few fields, consider composition instead of adding inheritance layers.

## 6. Boundaries of Constructor Calls

In Java 17, arguments to `super(...)` cannot rely on the instance state of the uninitialized object. You can use constructor parameters or static helpers to normalize/validate:

~~~java
class Parent {
    Parent(String id) {}
}

class Child extends Parent {
    Child(String input) {
        super(java.util.Objects.requireNonNull(input, "input").trim());
    }
}
~~~

This snippet is valid. If input is null, Objects.requireNonNull throws an exception before the parent constructor is called. You should not hide complex logic inside argument expressions; only use this approach when it makes the constructor clearer.

If the superclass constructor declares a checked exception, a subclass calling `super(...)` must declare an appropriate exception in `throws`; Java 17 does not allow wrapping a `super(...)` call in a `try/catch` inside the subclass constructor. The caller can catch the exception when calling `new Child(...)`. You also need to check the accessibility of the parent constructor: `private` or package-private constructors may not be callable from the subclass's location.

## 7. Common Mistakes and Self-Check

| Situation | How to Understand or Fix |
| --- | --- |
| Compiler reports that the implicit super constructor does not exist | Write `super(args)` with the matching signature or declare an appropriate parent constructor. |
| Subclass forgets to pass required id/owner | Include the data in constructor parameters and call super(...) explicitly. |
| Overloads duplicate validation logic | Choose one primary constructor and have other overloads call this(...). |
| A parent's private field is assigned from the subclass | Let the superclass assign its own field through its constructor. |
| Parent constructor calls a subclass hook | Avoid polymorphic logic when the subclass is not ready yet; see the lesson on overridable methods in constructors. |
| Only validating in the constructor but not in update APIs | Protect invariants even after object creation. |

**Question 1.** An abstract class only has Parent(String id). Is Child() {} valid?  
**Answer:** No, because Java 17 implicitly inserts super(), but Parent() does not exist.

**Question 2.** Does a class implementing three interfaces run three constructor chains?  
**Answer:** No. Interfaces do not have constructors; the extends chain has one direct superclass at each layer.

**Question 3.** Where should id be validated if id is the responsibility of the abstract superclass?  
**Answer:** In the superclass constructor that takes id, then stored in an encapsulated field; the subclass must call super(id).
