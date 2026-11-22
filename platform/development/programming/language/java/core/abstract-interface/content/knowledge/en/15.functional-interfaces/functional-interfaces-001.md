# Functional Interfaces and the Single Function Contract in Java

A **functional interface** is an interface that has a single functional abstract method according to Java's rules. This contract specifies what parameters a behavior needs to accept and what result it produces; a lambda expression or method reference can provide the implementation for it.

## 1. How Is a Contract Used?

For example, a contract for adding two integers can be described by an interface:

```java
@FunctionalInterface
interface IntOperation {
    int apply(int left, int right);
}

public class FunctionalInterfaceConceptDemo {
    public static void main(String[] args) {
        IntOperation add = (left, right) -> left + right;
        System.out.println(add.apply(3, 4));
    }
}
```

Save this as `FunctionalInterfaceConceptDemo.java`, then compile and run:

```bash
javac FunctionalInterfaceConceptDemo.java
java FunctionalInterfaceConceptDemo
```

Output:

```text
7
```

The variable type `IntOperation` is the **target type** of the lambda. Because of the `apply(int, int)` signature, the compiler knows the lambda must accept two integers and return a result compatible with `int`. The lambda provides the behavior for the contract; it does not create additional methods or change the interface declaration.

## 2. “One Method” Does Not Mean Only One Declaration Line

When determining a functional interface, Java examines declared and inherited abstract methods along with signature rules:

- Independent abstract methods such as `read()` and `write(String)` create two different obligations. A single lambda cannot implement both.
- Inherited abstract declarations with equivalent signatures and compatible return types can together represent a single functional contract.
- `default`, `static`, and `private` methods with bodies do not create additional abstract obligations.
- An abstract method corresponding to a public instance method of `Object`, such as `equals(Object)`, is handled under specific rules and does not by itself create an additional SAM.
- A `sealed interface` cannot serve as a target type for a lambda, even if it declares only one abstract method.

The lessons on interface inheritance, `Object` methods, method types, and `sealed interface` limitations go into detail on each case. The point to remember here is that the compiler determines **a valid functional contract**, rather than simply counting lines with the `abstract` keyword.

The following example has two independent abstract contracts, so it is not a functional interface:

```java
interface ReadWrite {
    String read();
    void write(String value);
}
```

This interface is still valid in Java and can be implemented by a concrete class. However, a single lambda cannot be used to provide both `read()` and `write(String)` at the same time.

## 3. The Role of `@FunctionalInterface`

Place `@FunctionalInterface` on an interface to instruct the compiler to check that design intent. The annotation is optional: an interface that satisfies Java's rules can still serve as a lambda target type even without the annotation. When the annotation is present, changes that make the interface no longer functional are caught at compile time.

The annotation does not create behavior on its own, does not generate a body for the abstract method, and does not prove that the lambda's algorithm is correct. The next lesson focuses on how the compiler checks the annotation and how it helps protect an API when it is modified.

## 4. When Should You Use a Functional Interface?

Use a functional interface when an API needs to accept a single behavior, such as a comparison rule, a filtering condition, a transformation, a callback, or a task. For common behaviors, prefer standard types such as `Predicate<T>`, `Function<T,R>`, or `Runnable` when the signature fits. Create a custom interface when the business domain, parameters, or exception contract need to be expressed more clearly.

Before choosing a type, identify what inputs the behavior needs, what the result should be, and which API will call it. If an interface requires multiple independent abstract behaviors, use a regular interface or split the responsibilities into separate contracts.

## 5. Self-Check

1. Why does `IntOperation add = (a, b) -> a + b;` compile?  
   **Answer:** `IntOperation` provides the target type and specifies two `int` parameters and an `int` result.

2. Can an interface with one `default` method and one abstract method be a functional interface?  
   **Answer:** Yes. The default method already has a body, so it does not create an additional abstract obligation.

3. Why can't `ReadWrite` be implemented with a single lambda?  
   **Answer:** It has two independent abstract methods that require two implementations.

**Remember:** A functional interface defines a function contract that a lambda or method reference can implement. Consider Java's signature and inheritance rules, then choose a target type that accurately expresses the behavior the API needs to accept.
