# Syntax, Naming, and Purpose of Interfaces in Java

## 1. An Interface Describes a Behavioral Contract

An `interface` is a Java type that declares the operations an object can provide. It allows calling code to work with an object's **capabilities** without having to depend on a concrete class. For example, a payment system only needs to know how to call `pay`; cash, card, or bank transfer can implement that behavior in their own way.

```java
interface PaymentMethod {
    String pay(int amount);
}

final class CashPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "Cash: " + amount;
    }
}

public class Main {
    public static void main(String[] args) {
        PaymentMethod payment = new CashPayment();
        System.out.println(payment.pay(150));
    }
}
```

Save as `Main.java`, compile, and run with JDK 17+:

```bash
javac Main.java
java Main
```

Output:

```text
Cash: 150
```

The variable `payment` has the declared type `PaymentMethod`, while the actual object is `CashPayment`. When `pay` is called, Java executes that object's implementation. The type contract is checked by the compiler; business semantics such as "payment succeeded" still need to be implemented and tested.

## 2. Syntax and Naming

Basic syntax:

```java
public interface PaymentMethod {
    String pay(int amount);
}
```

- `interface` is the type declaration keyword.
- `PaymentMethod` is the type name; Java conventions use **PascalCase** for class and interface names.
- `String pay(int amount);` is the declared method. The semicolon indicates that this is a declaration without a method body.
- `public` allows code in other packages to reference the type when the relevant access conditions are met. If the modifier is omitted on a top-level interface, the type becomes package-private; the lesson on access will explain this in more detail.

Interface names should express a role or capability, such as `Runnable`, `Comparable<T>`, `Closeable`, `MessageSender`, or `PriceCalculator`. Avoid vague names like `CommonInterface` if they do not indicate what contract is provided. Method names are usually verbs or phrases describing behavior; constants are usually written in `UPPER_SNAKE_CASE`.

## 3. When Are Interfaces Useful?

Interfaces are useful when:

1. Multiple classes provide the same capability but implement it in different ways.
2. A consuming component should depend on a stable contract rather than creating a concrete implementation itself.
3. An implementation needs to be substituted in tests, for example passing a fake sender to verify that a message is sent.
4. A class needs to take on multiple independent roles, such as being both printable and saveable.

There is no need to create an interface for every class. If there is not yet a substitution boundary or a useful contract, an intermediate interface only increases the number of types and files to manage.

## 4. Quick Comparison with Classes and Abstract Classes

| Mechanism | Focus | Constructors and instance state | Inheritance relationship |
| --- | --- | --- | --- |
| Concrete class | Provides implementation and creates objects | Can have both | One direct superclass |
| Abstract class | Shares implementation or state with subclasses | Can have constructors and instance fields | One direct superclass |
| Interface | Declares a contract and polymorphic type | No constructors or instance fields | A class can implement multiple interfaces |

Modern interfaces can also contain `default`, `static`, and `private` methods, so not every method is abstract. The following lessons analyze reference types, access control, `extends`, `implements`, state restrictions, member types, and annotation interfaces.

## 5. Common Mistakes

- Using `new PaymentMethod()`: an interface cannot be instantiated directly; create an implementation.
- Changing the signature in the class, for example `pay(String)` instead of `pay(int)`: this is not an implementation of the declared method.
- Reducing the access level when implementing a public interface method: the implementation must keep `public` access.
- Creating an interface merely to mirror a class without a need for a contract or substitution: consider whether that abstraction makes the design clearer.

**Self-check:** If both `CardPayment` and `CashPayment` implement `PaymentMethod`, does a component that accepts a parameter of type `PaymentMethod` need to know the names of those two classes? No; it only needs to call the operations declared by the contract.
