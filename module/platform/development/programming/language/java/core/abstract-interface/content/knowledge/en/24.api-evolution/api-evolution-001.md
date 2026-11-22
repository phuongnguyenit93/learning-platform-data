# Java 8 milestone for default, static methods, and functional interfaces

Java 8 expanded the capabilities of interfaces in three important directions: **default methods** allow an interface to provide default behavior, **static methods** place utility functions associated with the interface itself, and **functional interfaces** create a target type for lambda expressions and method references. These changes enable Java libraries to evolve their APIs while still supporting many older implementation classes.

An interface still describes a contract. Default methods add an implementation that can be shared; static methods are operations invoked through the interface name; a functional interface is an interface with one abstract method suitable for representing an action.

## 1. Why did Java 8 need to extend interfaces?

Before Java 8, interfaces primarily declared abstract methods and constants. When a library wanted to add a method to an interface already implemented by many classes, those classes might have to add the new implementation. Changing a widely used contract was therefore very costly.

Java 8 added default methods so that an interface can provide a body for a new method. Implementation classes can use the default behavior immediately or override it when needed. Java 8 also added static methods to group utility functions in the exact place that owns the API, while introducing lambda expressions and the Stream API, which rely heavily on functional interfaces.

Example of the three kinds of methods in the same interface:

~~~java
interface TextRule {
    String apply(String text); // abstract method

    default String bracket(String text) {
        return "[" + apply(text) + "]";
    }

    static TextRule trim() {
        return String::trim;
    }
}
~~~

`apply` defines the action that each implementation must provide. `bracket` is shared behavior based on `apply`. `trim` is a static utility function that creates a `TextRule` responsible for removing leading and trailing whitespace from a string.

An interface can contain abstract, default, and static methods together. Having additional default or static methods **does not automatically make an interface non-functional**.

## 2. Default methods: default behavior in the contract

A default method is an interface method with the `default` keyword and a body. Implementation classes are not required to override this method. If not overridden, calls can use the default implementation.

~~~java
interface Printable {
    void print(String text);

    default void printLine(String text) {
        print(text);
        System.out.println();
    }
}
~~~

An implementation class only needs to provide `print`:

~~~java
class ConsolePrinter implements Printable {
    @Override
    public void print(String text) {
        System.out.print(text);
    }
}
~~~

When calling `new ConsolePrinter().printLine("Hello")`, the default method calls `print` on the same object, so the `ConsolePrinter.print` implementation is used. A default method can call other methods of the interface and can be overridden by implementation classes.

A default method does not give an interface its own instance state. Interfaces do not have regular instance fields; fields declared in an interface are `public static final` constants. If behavior requires per-object state, a concrete class or an abstract class is usually more appropriate.

### Method selection rules when multiple implementations exist

When a class inherits behavior from a superclass and interfaces, Java applies the resolution rules:

1. **A concrete method of a class wins over a default method from an interface.** If a superclass already has a compatible instance method, the class method takes precedence.
2. **A more specific interface wins over a parent interface.** If `Child` extends `Parent` and both define a default with the same signature, `Child`'s default takes precedence.
3. **Two interfaces with no inheritance relationship defining defaults with matching signatures cause a conflict.** The implementation class must override that method to decide the behavior.
4. Inside the override, the default implementation can be explicitly called with `InterfaceName.super.methodName()` when appropriate.

Example of a conflict:

~~~java
interface HasCode {
    default String code() {
        return "A";
    }
}

interface HasName {
    default String code() {
        return "B";
    }
}

class Item implements HasCode, HasName {
    @Override
    public String code() {
        return HasCode.super.code() + "-" + HasName.super.code();
    }
}
~~~

If `Item` does not override `code`, the compiler reports an error because it cannot automatically choose between the two default methods. The implementation above deliberately combines both behaviors, so `new Item().code()` returns `"A-B"`.

A default method can also be redeclared as abstract by a subinterface to require concrete implementations to provide the behavior. Therefore, when designing an API, you need to consider both interface inheritance relationships and the methods that implementation classes already have.

## 3. Static methods in interfaces

A static method is declared with the `static` keyword and has a body. It belongs to the interface, so it is called using the interface name:

~~~java
interface NumberTools {
    static boolean isEven(int number) {
        return number % 2 == 0;
    }
}

boolean result = NumberTools.isEven(8);
~~~

Static methods are useful for placing object-creation functions, check functions, or related utilities directly in the interface's API. Users do not have to look for a separate utility class if that behavior belongs to the interface.

Unlike default methods, an interface's static method **is not inherited as an instance method** by implementation classes or subinterfaces, and does not participate in polymorphic dispatch. Call `NumberTools.isEven(8)`, not `instance.isEven(8)`. A static method with the same name in an implementation class is a separate static method and does not override the interface's static method.

Static methods in an interface also cannot be called with `InterfaceName.super`. The `InterfaceName.super.method()` syntax is meant for selecting a default instance implementation.

## 4. Functional interfaces: one abstract method, many possibilities

A functional interface is an interface with exactly one abstract method suitable as the target of a lambda expression or method reference. The `@FunctionalInterface` annotation is not required for an interface to be a functional interface, but it should be used so the compiler checks the design intent.

~~~java
@FunctionalInterface
interface TextRule {
    String apply(String text);

    default String bracket(String text) {
        return "[" + apply(text) + "]";
    }

    static TextRule trim() {
        return String::trim;
    }
}
~~~

`TextRule` remains a functional interface even with an added default method and a static method, because only `apply` is an abstract method requiring implementation. A lambda such as `text -> text.trim()` can create an object matching the `TextRule` target type.

Common standard functional interfaces in `java.util.function`:

| Interface | Abstract method | Purpose |
|---|---|---|
| `Predicate<T>` | `boolean test(T value)` | Checks a condition and returns true/false. |
| `Function<T, R>` | `R apply(T value)` | Converts one value into another value. |
| `Consumer<T>` | `void accept(T value)` | Accepts a value and performs an action. |
| `Supplier<T>` | `T get()` | Supplies a value without taking any parameters. |
| `UnaryOperator<T>` | `T apply(T value)` | Transforms a value and returns the same type. |
| `BinaryOperator<T>` | `T apply(T left, T right)` | Combines two values of the same type to produce a value of the same type. |

Java 8 also provides variants for primitive types, such as `IntPredicate`, `IntFunction<R>`, and `ToIntFunction<T>`, which help reduce boxing/unboxing in certain cases.

An interface can still be a functional interface while declaring default and static methods. Compatible abstract methods inherited from multiple parent interfaces can represent the same logical signature; the key criterion is that the final abstract contract has one functional method, rather than simply counting declaration lines across the entire inheritance hierarchy. `@FunctionalInterface` helps detect when a change accidentally breaks this condition.

## 5. Runnable Java 17+ example

Save the code below to `Java8InterfaceEvolution.java`. The code uses Java 8+ syntax and runs on JDK 17.

~~~java
@FunctionalInterface
interface TextRule {
    String apply(String text);

    default String bracket(String text) {
        return "[" + apply(text) + "]";
    }

    static TextRule trim() {
        return String::trim;
    }
}

interface HasCode {
    default String code() {
        return "A";
    }
}

interface HasName {
    default String code() {
        return "B";
    }
}

class Item implements HasCode, HasName {
    @Override
    public String code() {
        return HasCode.super.code() + "-" + HasName.super.code();
    }
}

public class Java8InterfaceEvolution {
    public static void main(String[] args) {
        TextRule trim = TextRule.trim();
        TextRule upper = text -> text.toUpperCase(java.util.Locale.ROOT);

        System.out.println("trim=" + trim.apply("  Java  "));
        System.out.println("bracket=" + trim.bracket("  Java  "));
        System.out.println("upper=" + upper.apply("java 8"));
        System.out.println("default=" + upper.bracket("java"));
        System.out.println("conflict=" + new Item().code());
    }
}
~~~

Compile and run:

~~~text
javac Java8InterfaceEvolution.java
java Java8InterfaceEvolution
~~~

Expected output:

~~~text
trim=Java
bracket=[Java]
upper=JAVA 8
default=[JAVA]
conflict=A-B
~~~

In this example, `TextRule.trim()` is a static method called through the interface name. The return value is a functional interface, so it can be assigned to a `TextRule` variable. `String::trim` is a method reference compatible with the `apply(String)` method. The `bracket` method is a default method and calls `apply` on the current implementation; with `upper`, the result is therefore converted to uppercase before being placed inside brackets. `Item.code()` resolves the conflict by explicitly calling the default method of each parent interface.

## 6. How Java 8 applied these ideas in the standard library

Java 8 APIs clearly illustrate the roles of default and static methods:

- `Comparator.comparing(...)` is a static method that creates a comparator based on a key-extraction function.
- `Predicate.and(...)`, `Predicate.or(...)`, and `Predicate.negate()` are default methods that combine or negate conditions.
- `Function.andThen(...)` and `Function.compose(...)` are default methods that compose transformations.
- `Collection.removeIf(...)` is a default method that allows removing elements that satisfy a predicate.
- `Map.computeIfAbsent(...)` is a default method that supports computing and storing a value when the key does not yet have a suitable mapped value.

Example using the standard API:

~~~java
import java.util.List;
import java.util.function.Predicate;

List<String> names = List.of("An", "Binh", "Chi");
Predicate<String> startsWithB = name -> name.startsWith("B");
Predicate<String> longEnough = name -> name.length() >= 3;

List<String> selected = names.stream()
        .filter(startsWithB.and(longEnough))
        .toList();
~~~

With JDK 17, `selected` contains `"Binh"`. This example shows that functional interfaces help express conditions with lambdas, while the `and` default method allows combining two conditions without creating a separate combiner class.

These APIs also help evolve libraries in a compatible way: convenient operations can be added to an interface with a default implementation provided. However, adding a default method still requires evaluating the impact on implementation classes and other interfaces in the inheritance hierarchy.

## 7. Compatibility and limitations

Default methods reduce the need to force every implementation class to add code when an interface is extended, but they do not guarantee that every change is safe:

- **Adding an abstract method:** implementation classes may need to add a method body; older source code may no longer compile.
- **Adding a default method:** usually easier to keep compatible, but can create conflicts with defaults from other interfaces or alter behavior that a class previously inherited.
- **Adding a static method:** does not require implementation classes to add a body, but its name and usage should be considered carefully to avoid confusion with existing APIs.
- **Changing the behavioral contract:** even if the code still compiles, a new default method can change the result when called on older implementations.

Default methods are not a mechanism to completely replace abstract classes. If instance state, constructors, or shared state between methods are needed, an abstract class may be more suitable. An interface is well suited for describing a capability that many unrelated classes can implement together; a default method provides shared behavior when that behavior truly makes sense for the contract.

## 8. Common mistakes

- **Assuming a functional interface can declare only one method in total:** incorrect. An interface can have multiple default and static methods, but only one functional abstract method.
- **Forgetting `@Override` when resolving a default conflict:** the implementation class must provide a compatible instance method to eliminate the conflict; using the annotation helps the compiler verify the signature.
- **Calling a static method through an instance variable:** a static method belongs to the interface name, for example `NumberTools.isEven(8)`.
- **Assuming an interface's static method is inherited or overridden:** an interface's static method does not have polymorphic dispatch through implementation classes.
- **Using `InterfaceName.super.method()` for static methods:** this syntax only selects an instance default method.
- **Adding a default method without reviewing other interfaces:** a class implementing multiple interfaces may encounter same-signature conflicts.
- **Assuming `@FunctionalInterface` is a mandatory requirement to use a lambda:** the annotation only confirms intent and requests compiler verification; what matters is whether the target type satisfies the functional interface rules.

## 9. Interface design checklist

1. Is the new method truly a reasonable default behavior for every implementation? If not, consider an abstract method or a separate API.
2. Does another interface that implementation classes commonly use at the same time define a default with the same signature?
3. Does the static method truly belong to the interface's API, such as a factory function or related helper?
4. If the interface is used as a target type for lambdas, does it keep exactly one functional abstract method?
5. Can test examples be written for older implementation classes and for multiple-interface inheritance scenarios to detect behavior changes?

When used for their intended purposes, Java 8's three capabilities complement one another: default methods help extend contracts with shared behavior, static methods group utilities into the right API, and functional interfaces provide the type shape for lambdas, method references, and data-processing pipelines.
