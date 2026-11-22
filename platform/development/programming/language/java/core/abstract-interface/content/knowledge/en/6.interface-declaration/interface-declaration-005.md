# A Class Implementing One or More Interfaces Using implements

## 1. Syntax in a Class Declaration

A class uses `implements` to commit to implementing one or more interfaces. If the class also inherits from a superclass, `extends` must come before `implements`:

```java
interface Printable {
    void print();
}

interface Storable {
    void save();
}

class DocumentBase {
    protected String prefix() {
        return "DOC";
    }
}

final class Report extends DocumentBase implements Printable, Storable {
    @Override
    public void print() {
        System.out.println(prefix() + " printed");
    }

    @Override
    public void save() {
        System.out.println(prefix() + " saved");
    }
}

public class Main {
    public static void main(String[] args) {
        Printable item = new Report();
        item.print();
    }
}
```

Output:

```text
DOC printed
```

The correct syntax is `class Report extends DocumentBase implements Printable, Storable`. A class has only one direct superclass, but it can implement multiple interfaces. Between interfaces, use `extends`.

## 2. Responsibilities of a Concrete Class

A class not declared `abstract` must provide valid implementations for the abstract methods it receives from its interfaces and superclass. Not every method necessarily has to be written directly in the class with `implements`: a suitable implementation can be inherited from a superclass or from a default method.

For example, given `interface Validator { boolean valid(String value); }`, the method `boolean valid(Object value)` does not implement `valid(String)` because it has a different parameter type. The method `protected boolean valid(String value)` is also invalid for implementing a public method of the interface. Using `@Override` helps the compiler catch common signature errors.

Other Java rules still apply: the return type must be compatible, the access level must not be reduced, and the implementation cannot add checked exceptions contrary to the original contract. If the class cannot yet fulfill the contract, it can be declared `abstract` and left for a concrete subclass to complete.

## 3. Interfaces as Types for Polymorphism

```java
interface Sender {
    void send(String message);
}

final class ConsoleSender implements Sender {
    @Override
    public void send(String message) {
        System.out.println("console: " + message);
    }
}

final class AlertService {
    private final Sender sender;

    AlertService(Sender sender) {
        this.sender = sender;
    }

    void alert(String message) {
        sender.send(message);
    }
}

public class Main {
    public static void main(String[] args) {
        AlertService service = new AlertService(new ConsoleSender());
        service.alert("Order received");
    }
}
```

Output:

```text
console: Order received
```

`AlertService` depends on the `Sender` contract. A different implementation can be passed in without changing the logic that calls `alert`. This is also the foundation of dependency injection and passing a fake implementation in tests.

The compiler checks calls against the declared type `Sender`; at runtime, the JVM dispatches `send` to the implementation of the actual object. If you frequently cast to a concrete class to call methods specific to it, check whether the current contract is missing required behavior or can be split into smaller interfaces.

## 4. Inheriting Implementations and Default Methods

If `Vehicle implements Movable`, then `ElectricVehicle extends Vehicle` is also `Movable` even without repeating the `implements Movable` clause. The subclass can use the inherited implementation or override it.

`default` methods can be used without being overridden. If multiple interfaces provide conflicting default methods with the same signature, the class must resolve the conflict according to Java's inheritance rules; the lesson on `extends` covers how to use `InterfaceName.super.method()` and how to redeclare an abstract method.

## 5. Common Mistakes

| Mistake | Correct Approach |
| --- | --- |
| `class A implements I1 implements I2` | `class A implements I1, I2` |
| `class A implements I extends Base` | `class A extends Base implements I` |
| Concrete class missing an abstract method | Implement the missing method, inherit a valid implementation, or declare the class abstract. |
| Implementation reducing the access level | Keep `public` when implementing a public method of the interface. |
| Assuming a variable of interface type can call every method of the implementation | Call through the members of the reference type, or design an appropriate contract. |
| Creating an interface for every class out of habit | Create one only when the contract provides practical benefits. |

**Self-check:** If `Report` implements both `Printable` and `Storable`, can a variable `Printable p = new Report()` call `p.save()` directly? No; `save()` does not belong to the reference type `Printable`, even though the actual object is also `Storable`.
