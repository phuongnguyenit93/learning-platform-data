# Fully Implementing Missing Abstract Methods in Java

A **concrete** Java class must have a valid implementation for every abstract instance method still in effect from the superclasses and interfaces it inherits. The implementation can be declared directly in the class or inherited from a suitable superclass. If the class still has unresolved abstract obligations, it must remain an abstract class; otherwise, the compiler rejects the class declaration.

This lesson focuses on how to identify missing obligations and choose the right place to complete them. Specialized rules on accessibility, inherited methods, multiple interfaces, and return types are analyzed in depth in the following lessons in the same chapter.

## 1. Distinguishing Abstract Methods from Methods with a Body

An abstract method declares only a signature and does not provide an execution body. A concrete method has a body and can be called when an object executes it.

The following example is a complete Java 17 program, saved in **Main.java**:

~~~java
public class Main {
    abstract static class Shape {
        abstract double area();
    }

    static final class Circle extends Shape {
        private final double radius;

        Circle(double radius) {
            this.radius = radius;
        }

        @Override
        double area() {
            return Math.PI * radius * radius;
        }
    }

    public static void main(String[] args) {
        System.out.printf("%.2f%n", new Circle(2).area());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac Main.java
java Main
~~~

Output:

~~~text
12.57
~~~

**Circle** is a concrete class because it has implemented the **area()** method that it inherits. If you remove this method while keeping **Circle** as a concrete class, the code will not compile. If **Circle** still does not know how to calculate the area because it is only an intermediate step in the hierarchy, you can declare **abstract class Circle** so that a subclass completes it later.

## 2. Where Do Implementation Obligations Come From?

When checking a concrete class, examine the entire hierarchy rather than looking only at the methods written directly in the class:

- Abstract methods declared in a superclass that still lack a concrete implementation.
- Abstract methods required directly or indirectly by interfaces.
- Obligations left behind across one or more intermediate abstract classes.
- Methods with the same name that actually have different signatures; they do not automatically fulfill one another's obligations.

An abstract class may implement some, all, or none of the abstract methods. The **abstract** keyword allows a class to defer obligations; it does not make those obligations disappear. Before a class can be instantiated with **new**, all missing abstract methods must be resolved.

Not every interface method creates a new implementation obligation. A **default** method already has a body and is usually inherited; a **static** or **private** interface method does not substitute for an abstract instance method. Fields, constructors, and an overloaded method with different parameters also cannot substitute for a missing abstract signature.

## 3. Compilation Errors and How to Fix Them

The snippet below is intentionally written incorrectly: **HtmlContent** is a concrete class, yet it has not implemented **render()**.

~~~java
abstract class Content {
    abstract String render();
}

class HtmlContent extends Content {
    // No render() yet, so this concrete class is invalid.
}
~~~

There are two ways to fix this depending on the design intent.

**Approach A — the class already has enough functionality to create objects:** implement the missing method.

~~~java
class HtmlContent extends Content {
    @Override
    String render() {
        return "<p>Hello</p>";
    }
}
~~~

**Approach B — the class is only an intermediate layer:** declare that class as abstract and let a subsequent concrete class complete the method.

~~~java
abstract class HtmlContent extends Content {
    // Shared state and behavior can be added here.
}

final class WelcomePage extends HtmlContent {
    @Override
    String render() {
        return "<p>Welcome</p>";
    }
}
~~~

These are alternative approaches; do not place two declarations with the same name in the same package to compile.

## 4. Process for Finding Missing Methods

When you encounter an error meaning “class is not abstract and does not override an abstract method”, check in the following order:

1. Identify the class mentioned in the error and confirm whether that class is intended to be concrete.
2. Read the **extends** and **implements** declarations, then list the abstract methods that the class receives from the hierarchy.
3. For each method, find an existing concrete implementation or one that needs to be written. You are not required to duplicate a method that is already validly inherited.
4. Compare the exact name, parameter types, return type, accessibility, and checked exceptions. If you need to implement a regular interface method, that method must be public.
5. Use **@Override** on the new method so the compiler detects mistakes in writing the signature. If the class still has unresolved obligations, implement additional methods or keep the class abstract.
6. After the code compiles, check whether the body accurately implements the meaning of the contract. Having no compiler errors only proves type validity.

## 5. Misconceptions to Avoid

- **Having a method with the same name does not necessarily mean overriding.** Adding or changing parameter types can create an overload and leave the original abstract method behind.
- **Not every concrete class has to write every method itself.** An inherited concrete implementation may already satisfy the contract.
- **Declaring abstract is not a design flaw in itself.** This is a valid way to divide responsibilities across multiple inheritance layers.
- **Do not use a dummy body to mask an obligation.** A method that only throws UnsupportedOperationException may allow the class to compile, yet it still fails to provide the behavior callers expect.
- **Do not confuse default methods with abstract methods.** A default method has a body, but conflicts between default methods may still require explicit resolution.

## 6. Self-Check

**Question 1.** Interface **Printer** declares **print()** and **close()**. Abstract class **BasePrinter** has implemented **close()**. What must concrete class **ConsolePrinter** inheriting **BasePrinter** do?

**Answer:** implement **print()**, unless another valid implementation is inherited. There is no need to rewrite **close()**.

**Question 2.** Can an abstract class that has already implemented every abstract method continue to be declared abstract?

**Answer:** yes. The abstract keyword can still indicate that the class is used only as a base class and is not to be instantiated directly.

**Question 3.** Why does adding a method with the same name but taking different parameters not resolve a missing abstract method error?

**Answer:** because that is an overload; the signature that needs to be implemented is still missing.

**Remember:** a concrete class must fulfill every abstract method obligation still in effect. Identify the correct signature and the entire inheritance chain before adding a method, then verify behavioral correctness separately.
