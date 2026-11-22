# Why don't interfaces have constructors and instance fields in Java?

## 1. Interfaces declare behavior, classes own state

An interface describes the operations that an object must provide. It does not define how to construct a concrete instance and does not declare instance fields. Constructors, per-instance state, and the initialization process belong to the implementing class or record.

```java
interface Account {
    String id();
    int balance();
    void deposit(int amount);

    String CURRENCY = "VND";
}

final class Wallet implements Account {
    private final String id;
    private int balance;

    Wallet(String id, int initialBalance) {
        this.id = id;
        this.balance = initialBalance;
    }

    @Override
    public String id() {
        return id;
    }

    @Override
    public int balance() {
        return balance;
    }

    @Override
    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }
}

public class Main {
    public static void main(String[] args) {
        Account first = new Wallet("A", 100);
        Account second = new Wallet("B", 5);
        first.deposit(25);
        System.out.println(first.id() + ": " + first.balance());
        System.out.println(second.id() + ": " + second.balance());
        System.out.println(Account.CURRENCY);
    }
}
```

Output:

```text
A: 125
B: 5
VND
```

`Wallet` has a constructor and the instance fields `id` and `balance`. The two wallet objects maintain separate state; depositing money into A does not change B's balance. The `first` and `second` variables use the `Account` interface type at the call site, but the actual objects are still `Wallet`.

## 2. Why don't interfaces have constructors?

A constructor initializes an instance of a concrete class and participates in the class's `this(...)` / `super(...)` call chain. An interface is not a class that can be instantiated directly, so declaring a constructor in an interface is invalid:

```java
interface Service {
    Service() {} // Invalid Java syntax
    void run();
}
```

`new Service()` is also invalid. In contrast, the `new Service() { ... }` syntax can create an anonymous class that implements `Service`; the constructor belongs to the anonymous class creation mechanism, not to the interface. A lambda can also provide an implementation for a functional interface.

An abstract class differs in that it is still a class in the inheritance chain: even though it cannot be instantiated directly with `new`, it can declare constructors and instance fields to share state with subclasses.

## 3. Why aren't interface fields instance fields?

Every field declared directly in an interface is implicitly `public static final`. Therefore:

```java
interface HttpSettings {
    int DEFAULT_PORT = 8080;
}
```

is equivalent to the explicit declaration `public static final int DEFAULT_PORT = 8080;`. The field belongs to the interface type, rather than being a copy for each object. Interface fields must be initialized and cannot be reassigned.

`final` prevents reassignment of the reference variable or value, but it does not necessarily make the referenced object immutable. For example, a `public static final List<String> NAMES` field can still point to a mutable list; callers can modify the contents of the list. Therefore, interface fields should not be used to expose shared mutable state.

## 4. Methods with a body do not mean an interface has state

Since Java 8, an interface can contain `default` and `static` methods; since Java 9, it can contain `private` helper methods. These methods can call other methods of the contract, use local variables, and handle logic. They do not create instance fields for each object.

```java
interface Named {
    String name();

    default String displayName() {
        return name().trim();
    }
}
```

`displayName()` retrieves data through `name()`, which is determined by the implementation. If you need a counter, a cache, or mutable state specific to each object, store it in the implementing class or a component owned by that class.

## 5. Choosing the right mechanism

| Need | Choice |
| --- | --- |
| Multiple different types declare the same behavior | Interface |
| Each object needs its own fields and a constructor that validates data | Implementing class/record |
| Multiple subclasses need shared fields, constructors, and base code | An abstract class can be used |
| Want a utility method called via the type name | A static method is suitable |
| Want to share short instance logic without shared state | A default method can be used |

**Self-check:** Can `int count = 0;` declared directly in an interface be incremented with `count++` in a default method? No; that field is implicitly `final`. Declare the state in the implementing class and expose the operations through the interface.
