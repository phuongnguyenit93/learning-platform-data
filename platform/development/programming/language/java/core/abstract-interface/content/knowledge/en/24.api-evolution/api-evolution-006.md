# Adding default methods and the risk of inheritance conflicts

Since Java 8, an interface can declare a **default method**: an instance method with a default implementation body. This feature helps extend an interface contract with shared behavior without requiring every implementing class to write the new method on its own immediately.

However, a class can implement multiple interfaces, and an interface can inherit from multiple other interfaces. When those sources provide default methods with equivalent signatures, Java needs to determine which implementation is used. Without clear precedence rules, a program can encounter conflicts at compile time; adding a default method to an API that is already in use can also expose a conflict that did not exist previously.

## 1. What is a default method?

A default method is an instance method declared with the `default` keyword in an interface. This method has a body and is `public` by default. It differs from a `static` method of an interface: a static method is invoked via the interface name and is not inherited by implementing classes like an instance method.

```java
interface Identifiable {
    String id();

    default boolean hasId() {
        return id() != null && !id().isBlank();
    }
}
```

A class implementing `Identifiable` only needs to provide `id()`; it can use `hasId()` right away or override this method if the contract allows it and there is a valid reason.

Default methods are useful when:

- A small behavior has a common meaning for most or all implementations of the interface.
- The API needs to be extended without forcing all older implementing classes to add a new abstract method.
- The default behavior can be accurately expressed in terms of operations already present in the contract.

A default method should not be added just to avoid writing code. The default behavior must be semantically correct for the implementations that the interface represents.

## 2. Which default method does Java choose?

When multiple types provide methods with the same signature, consider the following main rules in order.

### 2.1. Instance methods from a class win over interface default methods

If the class or a superclass provides a matching instance method, that method takes precedence over the default method. This preserves Java's class inheritance model.

```java
interface Greeting {
    default String greet() {
        return "Greeting";
    }
}

class BaseGreeter {
    public String greet() {
        return "BaseGreeter";
    }
}

class ClassWinsGreeter extends BaseGreeter implements Greeting {
}
```

Calling `new ClassWinsGreeter().greet()` returns `"BaseGreeter"`. The class does not need to override the method just to resolve the default method of `Greeting`.

This rule does not mean that any methods with the same name can replace one another: the signature, return type, and accessibility must still be compatible according to Java rules. Static methods also do not participate in this instance overriding mechanism.

### 2.2. A more specific interface wins over a parent interface

If a subinterface overrides a default method of a superinterface, the implementation from the more specific subinterface takes precedence.

```java
interface GeneralGreeting {
    default String greet() {
        return "General";
    }
}

interface FormalGreeting extends GeneralGreeting {
    @Override
    default String greet() {
        return "Formal";
    }
}

class FormalGreeter implements FormalGreeting {
}
```

`FormalGreeter` uses `FormalGreeting.greet()` and receives `"Formal"`. This is not a conflict between two independent defaults: the inheritance relationship clearly indicates which method is more specific.

### 2.3. Two unrelated interfaces both declaring a default cause a conflict

If two interfaces with no inheritance relationship provide default methods with the same signature, Java does not automatically choose the interface written first, listed first, or with a particular name. The concrete class needs to override the method and specify the desired behavior.

```java
interface LeftGreeting {
    default String greet() {
        return "Left";
    }
}

interface RightGreeting {
    default String greet() {
        return "Right";
    }
}

// Does not compile if the greet() override is omitted:
// class BrokenGreeter implements LeftGreeting, RightGreeting { }

class ResolvedGreeter implements LeftGreeting, RightGreeting {
    @Override
    public String greet() {
        return LeftGreeting.super.greet()
                + " + "
                + RightGreeting.super.greet();
    }
}
```

The syntax `LeftGreeting.super.greet()` directly calls the default implementation of a direct superinterface. It is useful when both implementations make sense and the class wants to combine them. If the two behaviors cannot be sensibly combined, write a separate implementation instead of calling both just to make the compiler stop reporting an error.

A class or interface that combines conflicting interfaces must resolve the conflict explicitly. Do not rely on the order in which interface names are listed to predict the result.

## 3. Complete runnable example

Save the following code in the file `DefaultMethodConflictDemo.java`. The example demonstrates all three rules: a more specific subinterface, a class method winning over a default, and a class actively resolving two unrelated defaults.

```java
interface Greeting {
    default String greet() { return "Greeting"; }
}

interface FormalGreeting extends Greeting {
    @Override
    default String greet() { return "FormalGreeting"; }
}

class SpecificGreeting implements FormalGreeting { }

class BaseGreeter {
    public String greet() { return "BaseGreeter"; }
}

class ClassWinsGreeter extends BaseGreeter implements Greeting { }

interface LeftGreeting {
    default String greet() { return "Left"; }
}

interface RightGreeting {
    default String greet() { return "Right"; }
}

class ResolvedGreeter implements LeftGreeting, RightGreeting {
    @Override
    public String greet() {
        return LeftGreeting.super.greet() + " + " + RightGreeting.super.greet();
    }
}

public class DefaultMethodConflictDemo {
    public static void main(String[] args) {
        System.out.println(new SpecificGreeting().greet());
        System.out.println(new ClassWinsGreeter().greet());
        System.out.println(new ResolvedGreeter().greet());
    }
}
```

Compile and run with JDK 17 or later:

```text
javac -encoding UTF-8 DefaultMethodConflictDemo.java
java DefaultMethodConflictDemo
```

Expected output:

```text
FormalGreeting
BaseGreeter
Left + Right
```

The output shows that Java does not randomly pick a default method: it prioritizes the more specific declaration in the interface hierarchy, prioritizes a class's instance method, and requires explicit resolution when two unrelated defaults conflict.

## 4. Why can adding a default method still break an API?

Suppose the first version of a library has interfaces `Auditable` and `Displayable`, neither of which declares `label()`. A client class can implement both without any issue.

In a later version, the library adds a default `label()` to `Auditable`. If another version of the library or an interface that the client class uses also provides a default `label()` in `Displayable`, the class may run into a conflict between two unrelated defaults. Upon recompilation, the code may fail to compile until the class overrides the method to choose a behavior.

This means that:

- Adding a default method usually places less burden on implementing classes than adding a new abstract method.
- “Having a default body” is not synonymous with “always compatible across every hierarchy”.
- A new method can collide with a default method from another interface or with an existing method in client classes.
- Library changes need to be tested against realistic interface combinations, not just with a simple implementing class.

When releasing a shared library, both source compatibility and binary compatibility must be considered. Previously compiled combinations should not be assumed to be safe in every case after an interface changes; test the supported implementation configurations and verify runtime behavior when multiple library versions are involved.

## 5. Conflict resolution process

When the compiler reports that a class inherits unrelated defaults with the same signature, follow this sequence:

1. **Identify the exact conflicting signature.** Check the method name, parameters, return type, and the interfaces that the class directly implements or inherits.
2. **Look for inheritance relationships between the interfaces.** If one declaration comes from a more specific subinterface, that may be a case already covered by a precedence rule.
3. **Check the superclass.** See whether there is a compatible instance method in the class or superclass; class methods generally take precedence over defaults.
4. **Decide on the desired contract.** Choose one default, combine the implementations if meaningful, or write custom behavior.
5. **Override explicitly at the appropriate place.** For a concrete class, use a public method with a compatible signature. If designing a unified subinterface, redefine the default in that interface so that all subclasses receive a consistent decision.
6. **Compile and test.** Check direct implementing classes, classes using a base class, and different interface combinations.

Example when you only want to choose one side:

```java
class LeftOnlyGreeter implements LeftGreeting, RightGreeting {
    @Override
    public String greet() {
        return LeftGreeting.super.greet();
    }
}
```

It is not mandatory to call `InterfaceName.super`. A new implementation can return a different value, as long as it still satisfies the method's public contract.

## 6. Designing safer default methods

### Keep methods small and based on the existing contract

A default method should usually compose existing public methods, provide a convenience query, or perform a simple behavior. Avoid creating a default whose meaning is only valid for a few implementing classes.

### Be careful with common names and signatures

Generic names such as `close()`, `name()`, `id()`, or `toString()` can appear across many hierarchies. Clear method names and consistent contracts help reduce the risk of collision, although signature conflicts cannot be eliminated completely.

### Do not use default methods in place of object state

Interfaces do not have per-object instance fields. If a behavior requires its own state, constructors, invariants, or a complex underlying algorithm, consider an abstract class or a collaborator object. Default methods should be kept at a level appropriate for an interface contract.

### Pay attention to built-in Object methods

A default method cannot provide a replacement implementation for public instance methods of `java.lang.Object` such as `toString()`, `equals(Object)`, or `hashCode()` in a way that overrides them from an interface. If an API requires a contract for those behaviors, design and test them at the implementing-class level.

### Do not turn overriding into a mere formality

When resolving a conflict, you should not just call an arbitrary default simply because it makes compilation succeed. Determine the behavior that callers can rely on and verify that the new result still conforms to the interface's contract.

## 7. Default methods and API compatibility

Before adding a default method to a published interface, consider the following questions:

- Is the method meaningful for all implementations or only a group of implementations?
- Is there a method with the same signature in a parent interface, an independent interface, or a client class?
- If two defaults conflict, where should the responsibility for unifying the behavior lie: in a more specialized interface or in a concrete class?
- Can the default behavior be implemented using existing methods without changing their semantics?
- Does the test suite cover multiple interfaces implemented together, a superclass containing a method with a matching signature, and the supported library configurations?

If not all implementations have a reasonable default behavior, a new abstract method or a separate extension interface may express the contract better. If the default method is truly shared behavior, document its conditions, results, and potential conflicts.

## 8. Common misconceptions

- **Assuming the interface listed first will win:** the declaration order in the `implements` clause does not resolve conflicts.
- **Assuming every default wins over class methods:** a compatible instance method in the class or superclass takes precedence.
- **Confusing default methods with static methods:** static methods are invoked via the interface name and are not inherited like default instance methods.
- **Assuming adding a default method is always safe:** conflicts can arise with other interfaces or with client class structures.
- **Calling `InterfaceName.super` from any interface:** this syntax only works with an appropriate direct superinterface; it is not an arbitrary lookup mechanism for any interface in the inheritance hierarchy.
- **Testing only a single implementing class:** conflicts often only appear when multiple interfaces are combined in the same type.

## 9. Summary

Default methods help evolve interfaces by adding built-in behavior, yet implementation selection still follows Java's inheritance rules. Class instance methods take precedence over defaults; a declaration in a more specific subinterface takes precedence over a declaration in a parent interface; two unrelated defaults with the same signature must be resolved explicitly.

When evolving an API, treat a default method as a contract change that needs evaluation, not as an automatic guarantee of compatibility. Clearly define the default behavior, check interface hierarchies that may be combined, write intentional overrides, and run tests on key implementation configurations before releasing.
