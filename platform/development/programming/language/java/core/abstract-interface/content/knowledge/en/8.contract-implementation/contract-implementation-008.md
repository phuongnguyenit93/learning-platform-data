# Java: Having the same methods is still not a subtype

In Java, **a class does not automatically become a subtype of an interface or another class simply because it has a method with the same name, parameters, and return type**. The subtype relationship must be established under the nominal type system (*nominal typing*) via `implements`, `extends`, or a declared inheritance relationship. This is the core point when **implementing a contract** with an interface.

After this lesson, you will be able to explain why code with matching methods still cannot be passed to an interface parameter, properly declare a subtype relationship, and use an adapter when an existing class cannot be modified.

## 1. Method signatures and subtype relationships are two different things

Consider two declarations:

```java
interface MessageSender {
    void send(String message);
}

final class ConsoleSender {
    public void send(String message) {
        System.out.println(message);
    }
}
```

`ConsoleSender` has a `send(String)` method matching the signature required by `MessageSender`. However, `ConsoleSender` **has not declared `implements MessageSender`**, so the compiler does not consider it a `MessageSender`.

- **Having a matching method** describes the ability to call a method on an object with a known type.
- **Being a subtype** describes a type relationship recognized by Java: an object of the subtype can be used wherever a supertype/interface is required.
- **Implementing a contract** has two parts: declaring participation in the contract (`implements`) and providing or inheriting the required abstract methods with valid implementations.

Java uses **nominal typing** for class and interface types: type identity along with declared inheritance relationships determines assignability and parameter passing. In the *structural typing* system of some other languages, member shape may be enough to satisfy a type; do not apply that reasoning to Java.

## 2. Example that does not compile despite having the same methods

Save the snippet below as `Main.java` to observe the intentional error:

```java
public class Main {
    interface MessageSender {
        void send(String message);
    }

    static final class ConsoleSender {
        public void send(String message) {
            System.out.println("Gửi: " + message);
        }
    }

    static void dispatch(MessageSender sender) {
        sender.send("xin chào");
    }

    public static void main(String[] args) {
        ConsoleSender sender = new ConsoleSender();
        dispatch(sender); // Compilation error: not a MessageSender
    }
}
```

Running `javac Main.java` will **fail to compile**. At the `dispatch(sender)` call, Java requires a value convertible to `MessageSender`, but the `ConsoleSender` type does not have the corresponding subtype relationship. The message typically means `ConsoleSender cannot be converted to MessageSender`; the exact formatting depends on the JDK.

The fact that the `send(String)` method is `public`, has the right name, and runs when calling `sender.send("...")` **does not replace** the `implements` declaration. Similarly, the assignment `MessageSender target = new ConsoleSender();` is also invalid.

## 3. Solution: declare `implements` and fulfill the contract

Modify `ConsoleSender` to formally declare the interface. This is a **standalone version that compiles and runs on Java 17+**:

```java
public class Main {
    interface MessageSender {
        void send(String message);
    }

    static final class ConsoleSender implements MessageSender {
        @Override
        public void send(String message) {
            System.out.println("Gửi: " + message);
        }
    }

    static void dispatch(MessageSender sender) {
        sender.send("xin chào");
    }

    public static void main(String[] args) {
        ConsoleSender concrete = new ConsoleSender();
        MessageSender abstraction = concrete; // Valid assignment
        dispatch(abstraction);
    }
}
```

Compile and run:

```bash
javac Main.java
java Main
```

Stdout output:

```text
Gửi: xin chào
```

At this point, `ConsoleSender implements MessageSender` establishes the subtype relationship, while `public void send(String)` satisfies the abstract method. `@Override` helps the compiler verify that the method actually overrides or implements a method from a supertype/interface; this annotation **does not create a subtype relationship on its own**. For a concrete class that declares `implements` without implementing all required abstract methods, Java reports a compilation error (or the class must be `abstract`).

The key point of polymorphism is that `dispatch` depends only on `MessageSender`. At runtime, the `sender.send(...)` call is dispatched to the implementation corresponding to the actual object. The caller does not need to know which class the object was created from, as long as its type satisfies the contract.

## 4. Relationships can be inherited without needing to repeat `implements`

A class can also become a subtype of an interface **indirectly** through a superclass or superinterface. The following example consists of illustrative declarations, which can be placed in the same Java file in an appropriate package:

```java
interface Sender {
    void send(String text);
}

class BaseSender implements Sender {
    @Override
    public void send(String text) {
        System.out.println(text);
    }
}

class LoggedSender extends BaseSender {
    // Inherits the Sender relationship and the send(String) implementation.
}
```

`LoggedSender` does not directly write `implements Sender`, but because `LoggedSender extends BaseSender` and `BaseSender implements Sender`, `LoggedSender` is still a `Sender`. The assignment `Sender s = new LoggedSender();` is valid. The subclass can inherit the matching implementing method or override it according to Java rules.

Similarly, when `interface Child extends Parent`, every concrete class implementing `Child` also has a subtype relationship with `Parent`. What determines this is still the **declared chain of type relationships**, not Java automatically matching method names.

## 5. When an old class cannot be modified: use an adapter

Sometimes you use an external library that has the method you need, but its class does not declare `implements` for the application's interface. You cannot pass that object directly to an API that accepts the interface. You can write an adapter to **forward the calls**, keeping the contract boundary clear.

A complete example with a *functional interface* (an interface with exactly one abstract method):

```java
public class AdapterExample {
    @FunctionalInterface
    interface Printer {
        void print(String text);
    }

    static final class LegacyPrinter {
        public void print(String text) {
            System.out.println("Legacy: " + text);
        }
    }

    static void printNotice(Printer printer) {
        printer.print("ready");
    }

    public static void main(String[] args) {
        LegacyPrinter legacy = new LegacyPrinter();

        // printNotice(legacy); // Invalid: missing subtype relationship.
        Printer adapter = legacy::print;
        printNotice(adapter);
    }
}
```

```bash
javac AdapterExample.java
java AdapterExample
```

Stdout:

```text
Legacy: ready
```

`legacy::print` is a **method reference** converted according to the *target type* `Printer` into an object that implements the abstract method of the functional interface. It **does not turn `LegacyPrinter` into a subtype of `Printer`**. For a non-functional interface, create an adapter class with `implements` and forward each required method.

This approach also explains why Java allows `Runnable task = () -> System.out.println("run");`: the lambda is converted to the target functional interface; Java does not automatically treat an arbitrary class with `run()` as a `Runnable`.

## 6. Declaring `implements` is not enough if the implementation is incorrect

Once the type relationship is declared, Java still checks method implementation rules. Cases that are easy to confuse:

| Case | Satisfies the interface's `void send(String)`? | Reason |
| --- | --- | --- |
| `public void send(String text)` | Yes | Signature and access level match. |
| `void send(String text)` (package-private) | No | Cannot reduce the `public` access level of the interface method. |
| `private void send(String text)` | No | A `private` method does not implement a `public` interface method. |
| `public void send(Object text)` | No | Different parameter type; this is an overload, not an override. |
| `public static void send(String text)` | No | A `static` method does not implement an instance method of the interface. |

For a contract with a return type, Java also checks return type compatibility (with the *covariant return* rule for reference types), declared checked exceptions, and other overriding rules. Simply seeing two identical method names can be misleading even after adding `implements`.

**Note:** An interface can contain `default` methods and inherit methods from superinterfaces; the implementing class does not necessarily have to rewrite all of them itself. Conversely, if the interface has an unsatisfied abstract method, a concrete class cannot ignore the contract.

## 7. Rules to check when using interfaces in APIs

When the compiler reports that a concrete type cannot be converted to an interface, check each item in order:

1. Does the class directly declare `implements InterfaceName`, or inherit that relationship via `extends`/a superinterface?
2. Are you passing an object of a class that has not declared the contract simply because it has methods with the same names?
3. If it already declares `implements`, do the signature, access level, return type, `static`/instance, and checked exceptions match? Use `@Override` so that it is checked early.
4. If the original class cannot be modified, can you declare an adapter that implements the interface and forwards the behavior, or use a lambda/method reference when the interface is a functional interface?

Do not rely on casting to "create" a relationship. A cast does not add `implements` to a class definition; a cast that is accepted syntactically can still cause a `ClassCastException` when the actual object does not belong to the target type.

**Remember:** In Java, *having the same set of methods* is an observation about API shape; *being a subtype and implementing the contract* is a declared type relationship verified by the compiler. It is that relationship that allows assigning to an interface variable, passing to an interface parameter, and using polymorphism safely.
