# Adding an abstract method and its impact on existing implementation classes

## Objectives

When a library adds an abstract method (`abstract method`) to a published interface, existing implementation classes may fail to recompile without a corresponding implementation. This lesson focuses on how to reproduce the error, the conditions under which old bytecode continues to run or throws `AbstractMethodError`, and how to choose an appropriate approach to extending the contract. You need to test source recompilation, linking old bytecode, and actual behavior separately.

## 1. Example of a change that causes a compilation error

Suppose the initial version of a library provides the following interface:

```java
public interface ReportSink {
    void write(String text);
}
```

An application implements the interface:

```java
public final class FileReportSink implements ReportSink {
    @Override
    public void write(String text) {
        System.out.println(text);
    }
}
```

Both pieces of code compile. Later, the library author decides to add the `flush()` operation to `ReportSink`:

```java
public interface ReportSink {
    void write(String text);
    void flush();
}
```

When recompiling `FileReportSink` against the new interface, the compiler reports an error because the concrete class has not yet implemented `flush()`. The direct fix is to add the method:

```java
@Override
public void flush() {
    // Flush buffered data to the storage destination.
}
```

The body above only illustrates the shape of the method; in a real implementation, its body must fulfill the storage contract properly. If a class cannot provide that behavior, adding a mandatory abstract method may be a sign that the API needs a different design.

An abstract class implementing `ReportSink` does not have to implement `flush()` yet and will still compile, because that class does not promise direct object instantiation. However, the concrete classes below it will still need a suitable implementation before objects can be instantiated.

## 2. Source compatibility and binary compatibility

Adding an abstract method to an interface has two effects that need to be distinguished.

| Situation | Typical outcome |
|---|---|
| Recompiling an existing concrete class against the new interface | Compilation error if the class lacks the new method and does not inherit a suitable implementation |
| Running old bytecode without calling the new method | Usually still runs; the new method has not been used |
| Calling the new method on an instance of an old class without an implementation | May throw `AbstractMethodError` at runtime |
| A subclass already has a public method compatible with the new signature | That method may satisfy the contract according to Java rules; semantics still need to be checked |
| Using a new default implementation (`default method`) | Usually preserves source and binary compatibility better, but conflicts and behavioral changes must be considered |

According to Java's binary compatibility rules, adding an abstract method to an interface does not necessarily cause all previously compiled bytecode to stop running immediately. An existing program can continue running if the execution path does not require the new method. However, if new code invokes that method on an old implementation class that lacks a suitable implementation, the JVM may throw `AbstractMethodError`.

Therefore, **“old bytecode can still start up” does not mean “the API change is safe in all cases”**. A library with many third-party interface implementations should treat adding an abstract method as a change carrying both source compatibility risks and runtime error risks.

## 3. Adding a default method to provide default behavior

Since Java 8, an interface can declare a default method using the `default` keyword. This method has a body, so existing implementation classes can inherit that behavior without being forced to rewrite immediately.

The complete example below simulates an API that has evolved to add an optional capability. The old version of `LegacyNotifier` only implements `send()`; the new interface provides a default behavior for `supportsScheduling()`.

Save the content to the file `InterfaceEvolutionDemo.java`:

```java
public class InterfaceEvolutionDemo {
    public static void main(String[] args) {
        Notifier notifier = new LegacyNotifier();

        notifier.send("deploy complete");
        System.out.println("supports scheduling: "
                + notifier.supportsScheduling());
    }
}

interface Notifier {
    void send(String message);

    default boolean supportsScheduling() {
        return false;
    }
}

final class LegacyNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("sent: " + message);
    }
}
```

Compile and run with Java 17 or later:

```text
javac -encoding UTF-8 InterfaceEvolutionDemo.java
java InterfaceEvolutionDemo
```

Expected output:

```text
sent: deploy complete
supports scheduling: false
```

The `LegacyNotifier` class does not declare `supportsScheduling()`, yet it remains a valid concrete implementation because the interface provides a default body. When a notifier type actually supports scheduling, that class can override the method and return `true`.

A `default` should only be added when the library can define a reasonable common behavior for all implementations that do not override it. Do not create a dummy body just to make code compile, such as always returning success when the operation is not actually supported. A wrong default can preserve source compatibility while breaking behavioral compatibility.

## 4. Risks of replacing an abstract method with a default method

A default method with a body can still conflict with a method having the same signature from an independent interface. For example, if both `Printable` and `Exportable` provide `default String format()`, the class `Document implements Printable, Exportable` must override `format()` to determine the behavior; the compiler does not choose based on the order in which interfaces are listed. A compatible instance method already present in the class or a superclass may take precedence, but its meaning might not match the new contract.

Check the interfaces and classes that clients commonly combine, including implementations outside the repository. When there is no default behavior that is valid for every implementation, a separate capability interface is more honest than providing a dummy body. Detailed resolution rules and conflict experiments are covered in the dedicated lesson on default methods.

## 5. When should you choose each API evolution approach?

| Need | Usually suitable option | Rationale |
|---|---|---|
| Every implementation must provide a new core capability | Add an abstract method, accompanied by a clear migration plan | The new contract genuinely requires all implementations to support that behavior |
| There is a valid default behavior for most implementations | Add a default method | Existing classes can continue working without having to override immediately |
| Only certain types of implementations have the new capability | Create a separate capability interface, such as `SchedulableNotifier` | Avoids forcing all existing implementations to pretend they have the new capability |
| Want to provide a utility that does not need new polymorphic state | Consider a `static` method or a utility class | Does not force every implementation class to change |
| There is a new contract significantly different from the old one | Create a new abstraction or a conversion adapter | Clarifies compatibility boundaries and helps clients migrate intentionally |

For example, instead of forcing all notifiers to support scheduled execution, you can declare:

```java
interface SchedulableNotifier extends Notifier {
    void schedule(String message, java.time.Instant when);
}
```

Only notifiers that genuinely support scheduled execution implement `SchedulableNotifier`. Clients can check for that capability using the interface type or directly request the appropriate service type. This approach keeps the base interface stable when the new feature only makes sense for a subset of implementations.

A `static` method on an interface belongs to the interface itself and is not an instance method that implementing classes must implement. A `private` method on an interface (available since Java 9) helps share logic internally across default methods; it does not create a new requirement for implementing classes.

## 6. A safer process for changing an interface

1. **Define the new contract:** clearly document what the method is for, valid inputs, results, errors, and effects on state.
2. **Inventory implementers:** find all classes in the same repository, modules, plugins, and known external implementations.
3. **Choose the method type:** use an abstract method when all implementations must fulfill it; use a default method when there is a valid default behavior; use a separate capability interface when only some implementations support it.
4. **Evaluate all three types of compatibility:** test recompiling existing source code, test running previously compiled bytecode, and check whether existing behavior changes.
5. **Test missing-implementation cases:** especially if clients can upgrade the library independently of upgrading the application.
6. **Write migration guidance:** if requiring the new method to be implemented cannot be avoided, publish implementation examples, the timing of the change, and errors that may occur.
7. **Check for default method conflicts:** test classes that combine multiple interfaces and verify that the selected behavior matches the contract.

Do not simply run tests within the library's repository and conclude that the change is safe. The internal test suite may have updated all implementation classes at the same time, while users of the library still have legacy classes externally.

## Key Takeaways

- Adding an abstract method to an interface typically prevents the source code of existing concrete classes from compiling upon recompilation until an appropriate implementation is provided.
- Old bytecode may still run if the new method is not called; calling a method that lacks an implementation can lead to `AbstractMethodError`.
- Default methods are a useful tool when there is a valid default behavior, but you must check for signature conflicts and behavioral changes.
- If the new capability applies only to certain implementations, a separate capability interface usually expresses the contract better than forcing every class to implement a new abstract method.
- Evaluate source, binary, and behavioral compatibility separately before releasing a new API version.
