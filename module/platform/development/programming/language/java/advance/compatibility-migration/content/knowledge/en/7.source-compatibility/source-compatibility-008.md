# New Methods in Interfaces and Conflicts with Implementing Classes

Interfaces are a key part of Java API contracts. A library may publish an interface for other applications to implement; over time, the library needs to add new behavior. However, adding a method to an interface can affect existing classes implementing that interface, including classes in other projects outside the development team's control.

Since Java 8, interfaces can declare `default` methods with a default body. This allows libraries to add certain behaviors without forcing every implementing class to rewrite immediately. This mechanism aids API evolution, yet can still conflict with existing methods in a class, methods inherited from a superclass, or default methods from another interface.

To evaluate interface changes safely, distinguish abstract, default, static, and private methods; understand method selection rules when inheriting from multiple sources; and check source compatibility, binary compatibility, and runtime behavioral changes.

## 1. How Can Adding a Method to an Interface Affect Code?

Suppose the library initially publishes:

```java
public interface PaymentGateway {
    Payment charge(Order order);
}
```

An application implements the interface:

```java
public class BankPaymentGateway implements PaymentGateway {
    @Override
    public Payment charge(Order order) {
        // Send payment request to the bank.
        return Payment.approved(order);
    }
}
```

After a while, the library wants to add refund capability. If it merely adds an abstract method:

```java
public interface PaymentGateway {
    Payment charge(Order order);
    Payment refund(Payment payment);
}
```

`BankPaymentGateway` does not have `refund`. When recompiling source code, the concrete class no longer satisfies the full interface contract and the compiler reports an error unless the class is declared `abstract` or implements the new method.

If the library adds a method with a default body:

```java
public interface PaymentGateway {
    Payment charge(Order order);

    default Payment refund(Payment payment) {
        throw new UnsupportedOperationException("Refund is not supported");
    }
}
```

Old implementing classes can keep compiling without immediately adding the method. When no matching method exists in the class or a more specific interface, calls to `refund` use the default body.

However, the example above also highlights a design issue: a refund call can fail when the implementation does not support it. Default methods only provide fallback behavior; they cannot fabricate business capabilities that an implementing class lacks.

## 2. Types of Methods in Interfaces

### 2.1. Abstract Methods

Abstract methods declare only a signature, with no method body:

```java
public interface Repository<T> {
    T findById(long id);
}
```

Concrete classes implementing the interface must supply a matching body unless the method is inherited from a superclass or another implementation satisfying the contract.

Adding an abstract method to a public interface increases obligations on implementations upon recompilation. This is a source-incompatible change for concrete classes not yet implementing the new method.

### 2.2. Default Methods

Default methods exist since Java 8. They are declared with the `default` keyword and must have a method body:

```java
public interface Identifiable {
    String id();

    default boolean hasId() {
        return id() != null && !id().isBlank();
    }
}
```

Implementing classes only need to supply `id()`. If they do not override `hasId()`, the class inherits the default behavior. Default methods can call the interface's abstract methods, enabling shared behavior built on data supplied by implementations.

Default methods are commonly used to add utilities derivable from existing contracts. If new behavior requires dedicated state, database access, network communication, or a business decision the interface cannot know, consider a different API instead of placing an assumed default method.

### 2.3. Static Methods

Interfaces can declare static methods since Java 8:

```java
public interface Identifiers {
    static boolean isValid(String value) {
        return value != null && !value.isBlank();
    }
}
```

Static methods are called through the interface name:

```java
boolean valid = Identifiers.isValid("ORD-100");
```

Static methods on an interface are not inherited as instance methods by implementing classes or subinterfaces. Thus, adding static methods usually creates no new implementation obligations for existing classes.

### 2.4. Private Methods

Since Java 9, interfaces can have private instance methods and private static methods to share logic among default/static methods:

```java
public interface AuditView {
    default String summary(String actor) {
        return normalize(actor) + " performed an action";
    }

    private String normalize(String actor) {
        return actor == null ? "unknown" : actor.trim();
    }
}
```

Private methods are used solely inside the interface. Implementing classes do not inherit and cannot override them. They are implementation details of the interface, not a new method that implementations must supply.

## 3. Source Compatibility and Binary Compatibility

When evolving a public interface, distinguish two concepts:

- **Source compatibility:** whether old source code still recompiles against the new interface version.
- **Binary compatibility:** whether previously compiled class files continue linking and running against the new interface version along existing usage paths.

These two concepts are not identical. A class file may still be loaded by the JVM, yet a call to a new method lacking an implementation can fail at execution time.

| Interface change | When recompiling old implementations | With previously compiled class files |
|---|---|---|
| Add abstract instance method | Concrete classes usually must implement it; otherwise compile fails. | Old class files may still load, yet calls to the new method can throw `AbstractMethodError`. |
| Add default instance method | Usually still compiles if no signature/inheritance conflict exists. | Usually binary compatible; exceptions exist when default-method conflicts arise. |
| Add static method | Creates no implementation obligation for classes. | Does not alter the set of instance methods classes must provide. |
| Add private method | Creates no implementation obligation for classes. | Internal interface detail; not an inherited method. |

Therefore, default methods are an important tool for evolving interfaces, yet not an absolute guarantee that every change is compatible. Consider other interfaces implemented by classes, existing superclasses, and method signatures across the entire system.

## 4. Resolution Rules When a Class Has Multiple Methods with the Same Signature

Java has rules determining which implementation is used when a class receives the same method signature from multiple sources. The most important rules are:

1. A matching instance method declared or inherited from the class hierarchy takes precedence over an interface default method.
2. Among interfaces in an inheritance relationship, a default method from a more specific interface beats one from a parent interface.
3. If two independent interfaces provide conflicting default methods, the concrete class must override to resolve it.
4. If a subinterface redeclares the method as abstract, it cancels the inherited default method; concrete classes implementing the subinterface must supply an implementation.

These rules are often summarized as: classes win over interfaces; more specific interfaces win over parent interfaces; two defaults from independent interfaces must be resolved explicitly.

## 5. Class Methods Win Over Default Methods

Suppose an interface provides a default method:

```java
public interface Printable {
    default String format() {
        return "formatted by Printable";
    }
}
```

A superclass already has a method with the same signature:

```java
public class BaseDocument {
    public String format() {
        return "formatted by BaseDocument";
    }
}
```

A subclass both extends the superclass and implements the interface:

```java
public class Invoice extends BaseDocument implements Printable {
}
```

When calling:

```java
Invoice invoice = new Invoice();
System.out.println(invoice.format());
```

the output is:

```text
formatted by BaseDocument
```

The method inherited from `BaseDocument` takes precedence. `Printable`'s default method does not replace the implementation from the class hierarchy.

### 5.1. Superclass Has an Abstract Method

The class-wins-over-interface rule also matters when a superclass declares an abstract method:

```java
public abstract class BaseTask {
    public abstract void execute();
}

public interface Executable {
    default void execute() {
        System.out.println("Default execution");
    }
}

public abstract class ScheduledTask extends BaseTask
        implements Executable {
}
```

`ScheduledTask` must still be abstract because the abstract method inherited from `BaseTask` dominates. The interface's default method does not automatically fill in the superclass's abstract method slot. A concrete subclass must implement `execute()`:

```java
public class DailyTask extends ScheduledTask {
    @Override
    public void execute() {
        System.out.println("Run daily task");
    }
}
```

### 5.2. Access Modifiers of Existing Methods

A method fulfilling an interface's instance method must satisfy public visibility. If a superclass has a method with the same signature that is only `protected` or package-private, a subclass cannot use that method to satisfy the interface's public contract. Upon recompilation, the compiler may report an error about weaker access privileges.

Similarly, a static method in a class cannot substitute for an instance method required by an interface. When adding a default method to an old interface, inspect methods with matching names and parameters in superclasses as well, not just methods written directly in implementing classes.

## 6. Default Method From a More Specific Interface

If an interface extends another interface and overrides a default method, the implementation from the child interface takes precedence:

```java
public interface Logger {
    default void log(String message) {
        System.out.println("LOG: " + message);
    }
}

public interface StructuredLogger extends Logger {
    @Override
    default void log(String message) {
        System.out.println("[structured] " + message);
    }
}

public class FileLogger implements Logger, StructuredLogger {
}
```

`StructuredLogger` is a subinterface of `Logger`, so its default method is more specific. `FileLogger` uses the implementation from `StructuredLogger`:

```java
new FileLogger().log("Application started");
```

Output:

```text
[structured] Application started
```

No override is needed in `FileLogger` because only one most-specific default method is inherited.

## 7. Conflicts Between Two Independent Default Methods

The most common conflict occurs when a class implements two independent interfaces that both provide a default method with the same signature:

```java
public interface JsonExporter {
    default String export() {
        return "JSON";
    }
}

public interface XmlExporter {
    default String export() {
        return "XML";
    }
}

public class ReportExporter implements JsonExporter, XmlExporter {
}
```

`ReportExporter` cannot automatically pick one implementation. At compile time, Java reports an error because two default methods are both inheritable and neither interface is more specific than the other.

### 7.1. Override to Define Custom Behavior

The clearest solution is overriding the method in the class:

```java
public class ReportExporter implements JsonExporter, XmlExporter {
    @Override
    public String export() {
        return "CUSTOM REPORT";
    }
}
```

The class's implementation has higher priority than interface default methods.

### 7.2. Selecting One Default Method via `InterfaceName.super`

To reuse one or more default bodies, call them directly:

```java
public class JsonReportExporter implements JsonExporter, XmlExporter {
    @Override
    public String export() {
        return JsonExporter.super.export();
    }
}
```

Or combine both behaviors:

```java
public class CombinedReportExporter implements JsonExporter, XmlExporter {
    @Override
    public String export() {
        return JsonExporter.super.export()
                + " + " + XmlExporter.super.export();
    }
}
```

`InterfaceName.super.method()` is the syntax to invoke a default method from an appropriate direct superinterface. It is not syntax for calling static methods and cannot be used to invoke an arbitrary interface that is not a direct superinterface.

## 8. Subinterfaces Can Cancel Default Methods

A subinterface can redeclare a parent interface's method as abstract:

```java
public interface DefaultCloseable {
    default void closeResource() {
        System.out.println("Default close");
    }
}

public interface ManagedResource extends DefaultCloseable {
    @Override
    void closeResource();
}
```

`ManagedResource` provides no default body. It requires concrete implementations to define `closeResource()` themselves:

```java
public class DatabaseResource implements ManagedResource {
    @Override
    public void closeResource() {
        System.out.println("Close database connection");
    }
}
```

If a concrete class does not implement this method, the compiler reports an error. This technique is useful when a child interface wants to tighten a contract where the parent interface supplied overly broad default behavior.

## 9. Method Signature Conflicts With Old Implementing Classes

When adding a method to a public interface, risk does not come only from other default methods. An old class may have already declared a method with the same name and parameters for its own purpose.

### 9.1. Existing Method Accidentally Becomes the Implementation

Suppose a class already has:

```java
public class LegacyCache {
    public boolean isEmpty() {
        return size() == 0;
    }

    public int size() {
        return 0;
    }
}
```

Later the interface is added:

```java
public interface CacheView {
    default boolean isEmpty() {
        return size() == 0;
    }

    int size();
}
```

The class implements both:

```java
public class LegacyCache implements CacheView {
    public boolean isEmpty() {
        return size() == 0;
    }

    public int size() {
        return 0;
    }
}
```

The public `isEmpty()` method already present in the class is selected instead of the default method. This case usually compiles without requiring edits to the class, yet calls through the interface will follow the class's method.

This can cause surprises if the old method shares the signature yet carries different semantics from the new method the library intended to provide. Therefore, when choosing names for new default methods, API authors should consider common names external implementations may already use.

### 9.2. Same Name With Different Parameters Is an Overload

Two methods merely sharing a name do not necessarily conflict. Example:

```java
public interface MessageSource {
    default String getMessage(String key) {
        return key;
    }
}

public class CustomMessageSource implements MessageSource {
    public String getMessage(String key, String locale) {
        return key + "@" + locale;
    }
}
```

`getMessage(String)` and `getMessage(String, String)` have different parameter lists, so they are two overloads. The class method does not override the default method.

In Java, a method signature is determined primarily by name and parameter types after applying generic/erasure rules; return type is not used to distinguish overloads. When methods share a signature, return types must be compatible under overriding and return-type-substitutability rules.

### 9.3. Different Return Types

Suppose a new interface adds:

```java
public interface Versioned {
    default Number version() {
        return 1;
    }
}
```

An old class might already have a method `public String version()`. When that class implements the interface, the two methods share the same name and empty parameter list yet have incompatible return types. Java does not allow using return types to create two overloaded methods with the same signature; compilation may fail.

If the class method's return type is a valid subtype of the interface's return type, that can be a covariant return and the class method can override the interface method. For example, `Integer` is a subtype of `Number`.

### 9.4. Generic Erasure and Name Clashes

Generic types undergo erasure when generating bytecode. Two signatures that look different in source code can become identical after erasure, causing name clashes or override errors.

For example, two independent interfaces declare:

```java
import java.util.List;

public interface StringBatch {
    default void process(List<String> values) {
    }
}

public interface IntegerBatch {
    default void process(List<Integer> values) {
    }
}
```

After type erasure, both have the form `process(List)`. A class implementing both can hit a name clash or inheritance conflict. You cannot solve this merely by writing two methods differing by generic arguments, because at the bytecode level the type parameters are erased.

When designing interfaces with generic methods, inspect erasure as well as interfaces that implementations may combine.

## 10. Conflicts With Checked Exceptions

Overriding methods must obey the checked exception rules of the overridden method. If a new interface adds a default method declaring no checked exceptions while a class already has a method with the same signature declaring a broader checked exception, source recompilation can fail.

Example:

```java
import java.io.IOException;

public interface ResourceView {
    default String describe() {
        return "resource";
    }
}

public class LegacyResource implements ResourceView {
    public String describe() throws IOException {
        return "legacy resource";
    }
}
```

The class method cannot override the interface method by adding checked exception `IOException` that the interface does not allow. You must change the signature, rename the new method, or design the API so it does not conflict with old implementations.

Unchecked exceptions like `RuntimeException` are not bound by this checked-exception rule, yet behavior still needs documentation to avoid unexpected contract changes.

## 11. Conflicts When Adding Defaults to Two Already Co-Implemented Interfaces

An important binary compatibility case arises when a class already implements two independent interfaces, and later both interfaces are upgraded to add a default method with the same signature.

Suppose the old version:

```java
public interface Readable {
    String read();
}

public interface Writable {
    void write(String value);
}

public class LegacyDevice implements Readable, Writable {
    @Override
    public String read() {
        return "data";
    }

    @Override
    public void write(String value) {
    }
}
```

In a later version, both interfaces gain:

```java
public interface Readable {
    String read();

    default void reset() {
        System.out.println("Reset reader");
    }
}

public interface Writable {
    void write(String value);

    default void reset() {
        System.out.println("Reset writer");
    }
}
```

The previously compiled `LegacyDevice` class file may still load in the JVM alongside the new interfaces, yet if `reset()` is called without a concrete implementation in the class, the JVM can detect two maximally-specific default methods and throw `IncompatibleClassChangeError`. When recompiling source, the compiler reports a conflict and requires the class to override `reset()`.

This is why adding default methods is usually binary-compatible yet still carries important exceptions. Before releasing a new interface, consider combinations of interfaces implementations might co-implement, especially in public API libraries.

## 12. Precedence Order When Resolving Methods

The table below summarizes how Java handles common scenarios:

| Scenario | Outcome |
|---|---|
| Class has a public instance method with same signature as default method | The class method is used. |
| Superclass has a concrete instance method with same signature | Method inherited from superclass wins over default method. |
| Superclass has an abstract method with same signature | Concrete subclass still must implement the abstract method. |
| Subinterface overrides parent interface's default method | Default method of the more specific subinterface is inherited. |
| Two independent interfaces have default methods with same signature | Class must override to pick or combine behavior. |
| Subinterface redeclares method as abstract | Parent default method is canceled in subinterface contract; concrete class must implement. |
| Method shares name yet differs in parameter list | Usually an overload, not an override. |
| Method shares signature yet has incompatible return type | Compile error or type conflict; return type does not create a separate overload. |

## 13. How to Handle Conflicts When Upgrading Libraries

When a library adds methods to an interface, follow these steps:

1. **Inventory implementations.** Find every class in the repository implementing the interface and identify external implementations if any.
2. **Search for matching signatures.** Check class hierarchies, methods with matching name/parameters, return types, checked exceptions, generic erasure, and modifiers.
3. **Determine the new method type.** Choose abstract, default, static, or private according to the actual contract that needs publishing.
4. **Evaluate default behavior.** Default methods must produce reasonable outcomes for old implementations. Avoid returning dummy values or performing side effects implementations do not expect.
5. **Check combined interfaces.** An implementation may implement multiple interfaces from different libraries; check for the possibility of two default methods colliding in signature.
6. **Recompile clients.** Build dependent modules and projects with the new interface version to detect source conflicts.
7. **Test binary compatibility.** Run old class files with the new interface in a dedicated runtime test, especially if the library promises clients need not recompile.
8. **Test behavior.** Confirm calls via interface references, class references, and superclass references all dispatch to the right implementation.
9. **Publish migration notes.** Clearly state new methods, default behavior, potential conflicts, and how to override.

Do not check only the library's own repository. A public interface may be implemented by plugins, client applications, or modules outside the library author's control.

## 14. Designing Interfaces for Easier Evolution

### 14.1. Prefer Default Methods Derivable From Existing Contracts

A good default method typically uses already-existing methods to build a new convenience utility:

```java
public interface CollectionView<E> {
    int size();
    E get(int index);

    default boolean isEmpty() {
        return size() == 0;
    }
}
```

`isEmpty()` can be computed from `size()`, needing no new state. This is a relatively safe style of extension.

### 14.2. Avoid Overly Generic Method Names

Names like `close`, `reset`, `size`, `name`, `value`, `get`, `process` are likely already present in user classes. When adding a default method, consider name commonality and collision potential.

Method names clearly reflecting domain roles usually reduce collision risk and make APIs easier to read. However, a long name does not automatically guarantee safety; still check signatures and return types.

### 14.3. Do Not Use Default Methods to Simulate Non-Existent Capabilities

A default method like:

```java
default void deleteAll() {
    throw new UnsupportedOperationException();
}
```

may help keep source compatibility, yet callers may mistakenly assume every implementation supports deletion. If a capability is optional, express it clearly via a separate interface, a capability query, or an API returning a result indicating support status.

### 14.4. Keep Semantics Stable

A default method can be overridden, yet users often rely on documented behavior. Avoid changing default behavior between releases without clear reason. If a default method calls another abstract method, clearly specify requirements on that method's return value, exceptions, and side effects.

## 15. Testing Interface Evolution

A good test suite should include these cases:

| Case | Goal |
|---|---|
| Old implementation does not override default method | Confirm default behavior works. |
| Implementation has a method with matching signature | Confirm the class method is selected and semantics do not change unexpectedly. |
| Superclass has a method with matching signature | Confirm the class hierarchy takes precedence. |
| Two interfaces have conflicting default methods | Confirm compiler requires override and class handles it properly. |
| Subinterface supplies a more specific default | Confirm the most specific method is used. |
| Subinterface redeclares abstract | Confirm concrete implementation must provide the method. |
| Incompatible return type, checked exception, or generic erasure | Confirm errors are caught at compile time. |
| Old binary with new interface | Detect `AbstractMethodError` or `IncompatibleClassChangeError` in possible cases. |

### 15.1. Testing Implementations Inheriting Defaults

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class IdentifiableTest {
    @Test
    void usesDefaultHasIdImplementation() {
        Identifiable value = () -> "ID-100";

        assertEquals(true, value.hasId());
    }
}
```

The example uses a lambda because `Identifiable` has one abstract method. Default methods do not make an interface lose its functional property.

### 15.2. Testing Classes Overriding Defaults

```java
interface Greeting {
    default String message() {
        return "hello";
    }
}

class VietnameseGreeting implements Greeting {
    @Override
    public String message() {
        return "xin chao";
    }
}
```

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void classImplementationWins() {
        Greeting greeting = new VietnameseGreeting();
        assertEquals("xin chao", greeting.message());
    }
}
```

### 15.3. Testing Conflicts at Compile Time

A conflict between two default methods is a compile error. Keep a separate source fixture to confirm the new API actually requires clients to resolve the conflict:

```java
interface A {
    default void run() {
    }
}

interface B {
    default void run() {
    }
}

class Conflict implements A, B {
    // javac reports error: must override run().
}
```

Then add an explicit implementation:

```java
class Resolved implements A, B {
    @Override
    public void run() {
        A.super.run();
    }
}
```

## 16. Summary of Decisions When Adding Methods

| Need | Usually appropriate design direction |
|---|---|
| Require every implementation to provide new behavior | Add an abstract method in a change with a clear migration plan. |
| Can supply common behavior from existing API | Add a default method with safe semantics. |
| Utility function needing no instance | Add a static method and call via the interface name. |
| Shared internal logic across methods in the interface | Use private methods from Java 9. |
| Capability only some implementations possess | Consider a separate capability interface or an API expressing support status. |
| Need an incompatible contract change | Create a new interface/version or organize migration around a major release. |

## 17. Checklist Before Releasing a New Interface

- [ ] Identified which interfaces are published to external clients.
- [ ] Inventoried implementing classes and related superclasses.
- [ ] Searched for matching method names and parameters across the class hierarchy.
- [ ] Checked return types, checked exceptions, and generic erasure.
- [ ] Checked independent interfaces that implementations might co-implement.
- [ ] Chose the right abstract/default/static/private method kind.
- [ ] Default behavior has clear meaning and does not assume non-existent capabilities.
- [ ] Recompiled representative clients against the new interface.
- [ ] Tested old binaries with the new library if binary compatibility must be maintained.
- [ ] Tested call paths via both interface references and class references.
- [ ] Documented new behavior and conflict resolution steps in release notes.

## References

- [JLS 9 — Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html): rules for interface declaration, inheritance, and default methods.
- [JLS 8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8): rules for method overriding and inheritance in classes.
- [JLS 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html): binary compatibility impact of API changes.
- [JLS 15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): rules for method selection on invocation.
- [JEP 126 — Lambda Expressions & Virtual Extension Methods](https://openjdk.org/jeps/126): background on adding virtual extension/default methods in Java 8.
- [Java 8 Default Methods Tutorial](https://docs.oracle.com/javase/tutorial/java/IandI/defaultmethods.html): examples of default methods and inheritance conflicts.

## Conclusion

Adding a method to an interface is a contract change that requires examining both old implementing classes and other interfaces across the system. Abstract methods create new implementation obligations; default methods help extend APIs using existing behavior yet can conflict with class methods or other default methods; static and private methods impose no instance obligations on implementing classes. Mastering class/interface precedence order, resolving conflicts explicitly with overrides and `InterfaceName.super`, and testing both source and binary compatibility help Java APIs evolve safely.
