# Precedence Rules and Method Conflict Resolution Table in Java

## Objective

When Java looks up a method, there are two questions to separate: **which signature** the compiler chooses among callable overloads, and **which implementation** is executed at runtime due to inheritance or overriding. With interfaces, `default` methods inherited from multiple interfaces also need to be handled.

This article summarizes common precedence rules, how to read compilation errors due to conflicts, and how to resolve them clearly in Java 17+.

## 1. Distinguishing Overload, Override, and Default Methods

- **Overload:** multiple methods with the same name but different parameter lists. The compiler selects the appropriate overload based on the declared types of the expressions and type conversion rules.
- **Override:** a subclass provides an implementation for an overridable instance method of a superclass or interface. When called through a reference, the implementation is selected according to the actual type of the object at runtime.
- **Default method:** an instance method with a body declared in an interface using the `default` keyword. An implementing class can inherit this method unless a precedence rule or conflict forces the class to provide a different implementation.
- **Abstract method:** declares a contract without a body. A concrete class must fulfill all remaining abstract methods; an abstract class may continue to leave them to its subclasses.

These concepts work together but do not replace one another. Java must first determine the appropriate call by type and signature at compile time; then, for polymorphic instance methods, the JVM invokes the appropriate overridden implementation on the actual object.

## 2. Precedence Rules Table for Method Inheritance

| Scenario | Rule | How to Handle |
|---|---|---|
| Class has a matching instance method | The class method takes precedence over the interface's default method | Use the class method; override it in the class if different behavior is needed |
| Superclass has a matching instance method | The method inherited from the superclass wins over the interface's default method | No need to re-implement if the superclass method satisfies the contract |
| Superclass declares an abstract method with the same signature | The declaration in the class hierarchy remains in effect; the interface default does not automatically replace that abstract contract | The concrete class must override it and provide a method body |
| Sub-interface overrides a parent interface's default | The default from the more specific sub-interface is selected | Inherit the sub-interface's default or override it in the class |
| Two interfaces with no parent-child relationship both provide a default with the same signature | Neither default automatically wins over the other interface's | The implementing class must override it and resolve the conflict |
| Multiple interfaces only declare the same abstract method with compatible return types | A single matching implementation can satisfy all of those contracts | Provide a single public method |
| One default and one abstract method with the same signature from two independent interfaces | The implementing class does not automatically select the default; the compiler requires the class to resolve the conflict | Override with a compatible public method; if appropriate, call the default via `InterfaceName.super.method()` |
| Interface static method | Not inherited or overridden like instance methods | Call using the interface name, for example `SomeInterface.utility()` |

This table covers instance methods and Java contracts. Signatures must be compatible, access levels cannot be reduced when overriding, and return types must satisfy Java's overriding rules. If two declarations with the same name and parameters have incompatible return types, this cannot be fixed simply by choosing a default; the design must be changed so that the contracts are compatible.

## 3. Overload Selection Rules at Compile Time

For overloaded methods with the same name, Java selects an applicable method according to the phases of method invocation:

1. **Strict invocation conversion:** considers conversions such as type matching and primitive/reference widening, without using boxing or unboxing.
2. **Loose invocation conversion:** if the previous phase yields no matching method, also considers conversions that allow boxing/unboxing.
3. **Varargs:** if a matching method still has not been found, considers methods with variable-arity parameters.

Java selects the most specific applicable method in the first phase that has valid candidates. This is why an overload taking a wider reference type may be selected before an overload that requires boxing, depending on the argument type and signature. If no method matches or if there are multiple choices where none can be determined to be the most specific, the call results in a compilation error.

For example, given `print(Object)` and `print(String)`, the call `print("hi")` selects `print(String)` because `String` is more specific than `Object`. Given `print(String)` and `print(Integer)`, the call `print(null)` is ambiguous because both reference types accept `null` and neither type is more specific than the other. This can be resolved with an explicit cast, such as `print((String) null)`, if that matches the intent.

Overloads are selected at compile time based on the expression types. Overriding of instance methods is then resolved based on the actual object. Therefore, a reference variable of a superclass type can still invoke an overridden implementation in a subclass, but it cannot invoke an overload that exists only in the subclass if that overload is not available through the variable's declared type.

## 4. Handling Default Conflicts Between Interfaces

Suppose two independent interfaces both define `default String route()`. A class implementing both cannot let the compiler choose one arbitrarily. The class must override `route()`. Inside the overriding method, you can directly call the default of a direct parent interface using the syntax `InterfaceName.super.method()`.

Example:

~~~java
interface FastRoute {
    default String route() {
        return "fast";
    }
}

interface SafeRoute {
    default String route() {
        return "safe";
    }
}

class ChosenRoute implements FastRoute, SafeRoute {
    @Override
    public String route() {
        return FastRoute.super.route() + "+" + SafeRoute.super.route();
    }
}
~~~

`ChosenRoute` defines explicit behavior by combining both defaults. If you only want to use one of the two, the body can return `FastRoute.super.route()` or `SafeRoute.super.route()`. Calling via `InterfaceName.super` is only valid in an appropriate interface inheritance context; the interface name used must be a direct interface that the class implements.

If a sub-interface extends a parent interface and provides a default with the same signature, the default in the sub-interface is the more specific method. If the sub-interface intentionally redeclares that method as abstract, it can drop the inherited default from the sub-interface's contract; a concrete class implementing the sub-interface must provide the method body.

### Default and Abstract Methods from Two Different Interfaces

Do not apply a "default always satisfies abstract" rule to two **independent** interfaces. In the following example, `NameResolver` must override `label()` itself even though `DefaultName` already has a method body:

~~~java
interface AbstractName {
    String label();
}

interface DefaultName {
    default String label() {
        return "default";
    }
}

class NameResolver implements AbstractName, DefaultName {
    @Override
    public String label() {
        return DefaultName.super.label();
    }
}
~~~

If the override is removed from `NameResolver`, the code will not compile because the methods with the same signature cannot be resolved. A different case is when a **sub-interface** provides a default to override an inherited abstract declaration; in that case, a concrete class can use that default:

~~~java
interface BaseName {
    String label();
}

interface ChildName extends BaseName {
    @Override
    default String label() {
        return "child";
    }
}

class UsesChildName implements ChildName {
}
~~~

Distinguish the inheritance relationship of the interfaces before concluding that a default method has already satisfied an abstract contract.

## 5. Matching Abstract Methods and Return Types

Two interfaces can declare the same abstract method. If the signature and return types are compatible, one public method in a class can implement both contracts:

~~~java
interface HasCode {
    String code();
}

interface HasIdentifier {
    String code();
}

class RecordCode implements HasCode, HasIdentifier {
    @Override
    public String code() {
        return "C-17";
    }
}
~~~

There is no need to write two methods just because there are two interfaces. When called through a variable of type `HasCode` or `HasIdentifier`, both calls execute the same `RecordCode.code()` implementation.

Return types need to be considered carefully. For overridden instance methods, primitive return types must match; reference types can use a compatible subtype according to covariant return rules. If two interfaces require return types that cannot both be satisfied simultaneously, the class cannot produce a valid implementation by declaring two methods that differ only in return type, because return types do not create separate overloads.

## 6. Complete Runnable Example in Java 17+

The following example illustrates four rules: a superclass method takes precedence over an interface default; a sub-interface's default takes precedence over a parent's default; a conflict between two independent defaults must be resolved; and a single implementation can satisfy two abstract contracts. Finally, the overload/override example shows the difference between selection at compile time and invoking the implementation at runtime.

Save the entire code into `Main.java`:

~~~java
interface Named {
    default String label() {
        return "interface";
    }
}

class BaseLabel {
    public String label() {
        return "class";
    }
}

class ClassWins extends BaseLabel implements Named {
}

interface GeneralMode {
    default String mode() {
        return "general";
    }
}

interface SpecificMode extends GeneralMode {
    @Override
    default String mode() {
        return "specific";
    }
}

class MostSpecificWins implements SpecificMode {
}

interface FastRoute {
    default String route() {
        return "fast";
    }
}

interface SafeRoute {
    default String route() {
        return "safe";
    }
}

class ChosenRoute implements FastRoute, SafeRoute {
    @Override
    public String route() {
        return FastRoute.super.route() + "+" + SafeRoute.super.route();
    }
}

interface HasCode {
    String code();
}

interface HasIdentifier {
    String code();
}

class RecordCode implements HasCode, HasIdentifier {
    @Override
    public String code() {
        return "C-17";
    }
}

class Formatter {
    String show(Object value) {
        return "Object";
    }

    String show(String value) {
        return "String";
    }
}

class CustomFormatter extends Formatter {
    @Override
    String show(String value) {
        return "CustomString";
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println(new ClassWins().label());
        System.out.println(new MostSpecificWins().mode());
        System.out.println(new ChosenRoute().route());

        RecordCode record = new RecordCode();
        HasCode codeView = record;
        HasIdentifier idView = record;
        System.out.println(codeView.code());
        System.out.println(idView.code());

        Formatter formatter = new CustomFormatter();
        System.out.println(formatter.show("hello"));
        System.out.println(formatter.show((Object) "hello"));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac Main.java
java Main
~~~

Exact standard output:

~~~text
class
specific
fast+safe
C-17
C-17
CustomString
Object
~~~

Output explanation:

1. `ClassWins.label()` inherits the public method from `BaseLabel`; that method takes precedence over the default `Named.label()`.
2. `MostSpecificWins.mode()` uses the default `SpecificMode.mode()`, because this interface extends and overrides the default of `GeneralMode`.
3. `ChosenRoute.route()` resolves the conflict by explicitly calling both defaults.
4. `RecordCode.code()` satisfies two interfaces with the same abstract contract, so both interface variables print `C-17`.
5. For `formatter.show("hello")`, the argument type is `String`, so the compiler selects the `show(String)` overload. The actual object is `CustomFormatter`, so the overridden implementation prints `CustomString`.
6. For `formatter.show((Object) "hello")`, the argument expression type is `Object`, so the `show(Object)` overload is selected. `CustomFormatter` does not override this overload, so the inherited method prints `Object`.

## 7. Commonly Confused Cases

- **Thinking that whichever interface is listed first in `implements` wins:** listing order does not determine default selection. Conflicts between independent defaults must be resolved by overriding.
- **Thinking that every method with the same name is an overload:** overloading requires different parameter lists. Overriding replaces the implementation of an inherited method with a compatible signature.
- **Thinking that the actual type of the object determines overloading:** the actual type determines the overridden implementation; overloading is selected based on expression types and accessible methods at compile time.
- **Forgetting the default in a sub-interface:** a more specific default in a sub-interface wins over a default inherited from a parent interface.
- **Assuming a default always replaces a superclass abstract method:** an abstract declaration inherited from a superclass can still force a concrete class to implement that method.
- **Trying to use return types to create overloads:** methods that differ only in return type do not form valid overloads.
- **Calling a static method through an object as if it were polymorphic dispatch:** interface static methods must be called via the interface name and do not participate in instance overriding.

## 8. Diagnostic Workflow for Compilation Errors

1. Identify whether the call involves overloading, overriding, default inheritance, or an abstract contract.
2. Note the declared type of the receiver variable and the type of each argument; use them to check applicable overloads.
3. Check the superclass first, then see whether interfaces provide a default with the same signature.
4. With multiple defaults, check the parent-child relationship between the interfaces. If the competing defaults come from independent interfaces, override and choose the desired behavior.
5. Check the access level, return type, parameters, and checked exceptions of the overriding method.
6. Recompile and run a minimal example to confirm the result. When needed, explicitly cast arguments to distinguish which overload is being selected.

## Key Takeaways

Overloading is resolved at compile time; overriding is selected according to the actual object at runtime. In inheritance, instance methods from the class hierarchy take precedence over interface defaults; a sub-interface's default wins over a parent's default; independent defaults with the same signature must be explicitly resolved by the implementing class. Matching abstract contracts can share a single implementation if their signatures and return types are compatible.
