# Diagnosing Ambiguous Default, Return Type, and Erasure Errors

## 1. Identifying the Three Error Categories

- **Ambiguous default:** multiple unrelated interfaces provide the same `default` method, making the compiler unable to choose an implementation automatically.
- **Incompatible return types:** declarations have the same name and parameter list, yet require return types that cannot be satisfied simultaneously.
- **Erasure/name clash:** declarations differ in generic parameters, yet have the same signature after type erasure.

These are compile-time errors. You need to inspect inherited contracts, signatures after substituting type parameters, covariance rules, and type erasure rather than only looking at the call line causing the error.

## 2. Ambiguous Default Method

Since Java 8, an interface can provide a body for a `default` method. If a class implements two unrelated interfaces and both define the same default method, the class receives two equal candidates and must resolve the conflict.

Example that intentionally does not compile:

```java
interface Left {
    default void ping() { System.out.println("Left"); }
}
interface Right {
    default void ping() { System.out.println("Right"); }
}
class Broken implements Left, Right {
    // Compile error: inherits unrelated defaults for ping()
}
```

### Fix: Explicit Override

The class can define the method itself and then call one or both default bodies via `InterfaceName.super.method()`:

```java
class Combined implements Left, Right {
    @Override
    public void ping() {
        Left.super.ping();
        Right.super.ping();
        System.out.println("Combined");
    }
}
```

`Left.super.ping()` and `Right.super.ping()` invoke the respective default implementations. Call only one side if that is the desired behavior; calling both may repeat side effects.

### Precedence Rules

1. A matching instance method inherited from a superclass generally takes precedence over an interface default. However, an abstract declaration in the superclass can force a concrete class to provide an implementation.
2. If a subinterface overrides the default, the definition in the more specific interface is used.
3. Two unrelated defaults require the concrete class to override the method to resolve the conflict.
4. A subinterface can redeclare the method as abstract, forcing implementing classes to provide a body.

Do not confuse a default conflict with overloading. Overloads have different parameter lists; this error appears when the same signature is inherited from multiple interfaces.

## 3. Incompatible Return Types

### Return Type Does Not Create an Overload

Java does not allow declaring two methods that differ only in return type:

```java
class ReturnOnly {
    int value() { return 1; }
    // Compile error: same name and parameters, different return type
    String value() { return "one"; }
}
```

The method name and parameter list distinguish overloads; the compiler does not choose an overload based on the return type.

### Covariant Return

The reference return type of an overriding method can be a subtype of the type in the contract:

```java
interface NumberSource { Number value(); }
interface IntegerSource { Integer value(); }

final class CountSource implements NumberSource, IntegerSource {
    @Override
    public Integer value() { return 42; }
}
```

The snippet above is valid because `Integer` is a subtype of `Number`. If two interfaces require `String value()` and `Integer value()`, no return type satisfies both unrelated reference types simultaneously. You cannot declare two methods to distinguish them by return type; you need to redesign the API or split the contracts.

For primitive types such as `int` and `long`, there is no covariance. You cannot use `int` to override a method returning `long` simply because a numeric conversion exists.

### Generic Return Type

When reading generic API errors, substitute the type parameters into the declaration before comparing. If `Source<T>` has `T value()` and is used as `Source<String>`, the type after substitution is `String`. The override must satisfy the substituted contract and the return-type-substitutability rules.

## 4. Type Erasure and Name Clash

Java generics are primarily implemented using **type erasure**. Type parameters are erased or replaced with their bounds; a `T` without an explicit bound is usually erased to `Object`. Generic metadata may remain for reflection to read, but bytecode signatures follow erasure rules.

Both `List<String>` and `List<Integer>` have `List` as their erasure. You cannot overload solely by these generic arguments:

```java
import java.util.List;
class Handler {
    void handle(List<String> values) { }
    // Compile error: same erasure as the method above
    void handle(List<Integer> values) { }
}
```

The compiler cannot distinguish two JVM methods by the `String` or `Integer` type inside `List`, because those type parameters do not produce two distinct erased signatures.

A name clash can also occur when two declarations have the same signature after erasure but do not form a valid override relationship. A related case is attempting to implement the same generic interface twice with two different type parameters, such as `Repository<String>` and `Repository<Integer>`; Java does not allow a class to inherit the same generic interface in two incompatible ways.

### How to Resolve

- Rename the method if the two operations differ in meaning.
- Use a single generic method such as `<T> void handle(List<T> values)` if the operation is the same for all `T`.
- Use wrappers such as `StringBatch` and `IntegerBatch` if two separate overloads are needed.
- Fix the generic hierarchy so that the class inherits the same generic contract in only one consistent way.
- Do not fix a name clash merely by changing the return type or parameter variable names; they do not change erasure.

## 5. Compiler-Generated Bridge Methods

When a class implements a generic method with a concrete type, the compiler may generate a **bridge method** to preserve polymorphism after erasure. A bridge typically has the `bridge` and `synthetic` flags; developers should not write it manually.

For example, `Box<T>` declares `put(T value)`, while `StringBox implements Box<String>` implements `put(String value)`. After erasure, the contract has the form `put(Object)`, whereas the concrete class has `put(String)`. The compiler generates a `put(Object)` bridge so that calls through `Box` are properly forwarded to the concrete method.

```java
Box<String> box = new StringBox();
box.put("hello");
```

When using reflection, `Class.getDeclaredMethods()` may return both the source method and the bridge. Check `Method.isBridge()` and `Method.isSynthetic()` to distinguish them. Frameworks and bytecode analyzers should also keep this in mind.

## 6. Complete Java 17 Example

The following program illustrates how to resolve two default methods, covariant return types, and a compiler-generated bridge method. Save the entire code as `Main.java`:

```java
import java.lang.reflect.Method;
import java.util.Arrays;

public class Main {
    public static void main(String[] args) {
        new Combined().ping();
        System.out.println("covariant value = " + new TextProvider().value());

        Box<String> box = new StringBox();
        box.put("hello");

        boolean hasBridge = Arrays.stream(StringBox.class.getDeclaredMethods())
                .anyMatch(Method::isBridge);
        System.out.println("bridge method generated = " + hasBridge);
    }
}

interface Left {
    default void ping() { System.out.println("Left.ping"); }
}
interface Right {
    default void ping() { System.out.println("Right.ping"); }
}
final class Combined implements Left, Right {
    @Override
    public void ping() {
        Left.super.ping();
        Right.super.ping();
        System.out.println("Combined.ping");
    }
}

interface ValueProvider { Object value(); }
final class TextProvider implements ValueProvider {
    @Override
    public String value() { return "Java 17"; }
}

interface Box<T> { void put(T value); }
final class StringBox implements Box<String> {
    @Override
    public void put(String value) { System.out.println("stored: " + value); }
}
```

Compile and run using JDK 17 or later:

```text
javac --release 17 Main.java
java Main
```

Exact stdout:

```text
Left.ping
Right.ping
Combined.ping
covariant value = Java 17
stored: hello
bridge method generated = true
```

The bridge result is computed using `Method.isBridge()`, independent of the order in which reflection returns the methods.

## 7. Diagnostic Workflow

1. **Read the first error.** Record the class, method name, involved interfaces, and compiler phrases such as `inherits unrelated defaults`, `return type is incompatible`, `name clash`, or `same erasure`.
2. **Rewrite the signatures.** Write down the name and parameter types after substitution and erasure. Do not use the return type to distinguish overloads.
3. **Inspect the hierarchy.** Determine whether the method comes from a superclass, a more specific interface, or two unrelated interfaces.
4. **Check the return type.** See whether a reference subtype satisfies all contracts; distinguish covariance from primitive conversions.
5. **Compute erasure.** Replace type variables with their corresponding bounds and compare the signatures. If two methods end up with the same signature, rename them or redesign the API.
6. **Create a minimal example.** Keep the interfaces, superclass, and signatures causing the error; compile separately with `javac --release 17`.
7. **Re-run tests.** Test calls through both the concrete type and the interface/base type. For generic overrides, verify that polymorphism remains correct.

## 8. Quick Reference Table

| Compiler Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `inherits unrelated defaults` | Two unrelated interfaces have the same default | Override and choose the behavior; you can call `InterfaceName.super.method()` |
| `return type is incompatible` | Return type does not satisfy the override contract | Check covariance, substitution, and redesign the contract if needed |
| Two methods differ only in return type | Java does not overload by return type | Rename the method or change the type design |
| `name clash` / `same erasure` | Generic signatures collide after erasure | Rename or design a valid generic/wrapper API |
| `Method.isBridge() == true` | Compiler generates a bridge to preserve polymorphism | Usually no fix needed; filter out bridges when analyzing source methods |

## 9. Checklist

- Read the relevant interface and superclass declarations, not just the call line causing the error.
- Distinguished between default, abstract, and superclass-inherited methods.
- Checked return types according to compatibility rules, rather than relying on casts at the call site.
- Computed erasure before adding overloads for generic types.
- Understood that bridge methods are compiler-generated code and checked them with reflection when needed.
- Compiled and tested through the interface/base type after fixing.

When diagnosing this group of errors, start from the contracts and method signatures after inheritance, substitution, and erasure. That approach helps determine whether the error lies in a language conflict or in the API design.
