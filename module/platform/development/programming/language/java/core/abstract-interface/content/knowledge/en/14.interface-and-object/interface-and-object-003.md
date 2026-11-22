# Why Is an Interface Not Allowed to Define a Default Method Replacing an Object Method?

Java allows interfaces to provide default methods to add shared behavior. However, an interface is not allowed to declare a default method with a signature override-equivalent to **any non-private method of java.lang.Object**. Familiar cases are toString(), equals(Object), and hashCode(); the scope of the rule is not limited to these three public methods.

## 1. Examples That Do Not Compile

~~~java
interface BadDisplay {
    default String toString() {
        return "custom display";
    }
}
~~~

~~~java
interface BadIdentity {
    default boolean equals(Object other) {
        return true;
    }

    default int hashCode() {
        return 1;
    }
}
~~~

Both declarations are invalid. Changing the method body or adding @Override does not fix the error. The rule also applies to signatures override-equivalent to other non-private methods of Object, including protected clone(). Some public methods such as getClass(), wait(), and notify() are also final, so concrete classes are not allowed to override them either.

## 2. Why Does This Restriction Exist?

Every Java class inherits directly or indirectly from Object. If an interface could provide a default implementation replacing these foundational methods, the meaning of the method would be unclear: the class behavior from Object or a superclass still takes precedence in the method resolution mechanism. Prohibiting the declaration prevents an API from promising a default implementation that a class cannot use like a normal override.

In particular, equals and hashCode affect equality and hash-based collections. Their policies need to match the data and identity of the concrete class. toString also often depends on the state or diagnostic purposes of each class. A general default in an interface cannot safely impose those semantics on every implementation.

## 3. An Abstract Declaration Differs from a Default Implementation

An interface can still declare a compatible abstract signature. It expresses a contract, but does not provide a method body:

~~~java
interface NamedObject {
    String name();
    String toString();

    default String description() {
        return name() + " | " + toString();
    }
}

final class Product implements NamedObject {
    private final String name;

    Product(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public String toString() {
        return "Product[" + name + "]";
    }
}
~~~

NamedObject.description() is valid because description is a new method, even though the method body calls toString(). Product provides a concrete implementation for toString(). A class can also inherit Object.toString() if that implementation satisfies the interface signature and the default semantics are sufficient.

## 4. “Class wins” Does Not Allow a Default toString()

The rule that class methods take precedence over default methods applies to valid conflicts. It does not make a default toString() valid; that declaration is rejected before implementation resolution.

~~~java
interface Greeter {
    default String greet() {
        return "Interface";
    }
}

class BaseGreeter {
    public String greet() {
        return "Base class";
    }
}

final class ActualGreeter extends BaseGreeter implements Greeter {
}

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new ActualGreeter();
        System.out.println(greeter.greet());
    }
}
~~~

Output:

~~~text
Base class
~~~

The example uses greet(), an ordinary method not restricted by the Object rule. BaseGreeter's implementation is selected. Do not infer from this example that Java allows declaring a default method with the same signature as toString(), equals(Object), or hashCode().

## 5. How to Design Properly

- If you want to share default behavior, use a separate method name such as description(), displayLabel(), or describe().
- If an interface needs to explicitly state an Object signature, it can declare a compatible abstract method, but without adding a default body.
- If you need a data-based equals/hashCode/toString policy, implement or override them in a concrete class.
- If you need a public copy API, do not try to use a default clone(); declare a public method with a clear contract.

Self-check:
- Can abstract String toString() be declared in an interface? Yes, if the signature is compatible.
- Can default int hashCode() be declared? No.
- Does the rule apply only to the three common public methods? No; the rule covers non-private methods of Object.
