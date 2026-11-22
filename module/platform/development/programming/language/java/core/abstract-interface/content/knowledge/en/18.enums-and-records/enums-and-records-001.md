# Enums Implementing Interfaces and Constant-Specific Behavior

## 1. Objectives

In Java, an enum represents a finite set of predefined values. An enum can implement one or more interfaces, so enum constants can be used wherever the program requires that interface type. When individual constants need different behavior, each constant can have its own class body to override methods.

A classic example is a set of operations: ADD adds, SUBTRACT subtracts, and MULTIPLY multiplies. They all follow the IntBinaryOperator contract, but the way they perform the operation differs.

After this lesson, you should know how to:

- Have an enum implement an interface and understand the contract the interface defines.
- Write constant-specific behavior using a constant-specific class body.
- Use an enum through an interface type to leverage polymorphism.
- Choose among constant-specific behavior, shared enum methods, and data passed through a constructor.
- Avoid common mistakes when designing enums with behavior.

## 2. How Do Enums and Interfaces Work Together?

An enum can declare interfaces after the enum name:

~~~java
enum Operation implements IntBinaryOperator {
    // Enum constants and enum body
}
~~~

The implements keyword has the same meaning as when a regular class implements an interface: the enum type provides the method contract of the interface. Each enum constant is an instance of the enum type, so that constant can be passed into a method that accepts the corresponding interface type.

There are two common implementation approaches:

1. **Shared behavior for all constants:** declare the method once in the enum body. The constants use the same processing logic, typically obtaining their own data from the constructor.
2. **Different behavior per constant:** place a class body immediately after the constant and override the method inside that body. For example, ADD and MULTIPLY share the same method signature but perform different calculations.

If the interface has an abstract method for which the enum does not provide a shared implementation, each constant must provide an appropriate implementation. You can declare an abstract method in the enum so that the compiler forces each constant to fulfill that contract.

An enum already has java.lang.Enum as its superclass; Java does not allow an enum to extend an arbitrary class in addition to that. An enum can still implement multiple interfaces, separating the contracts that it supports.

## 3. Runnable Example with Java 17+

Create a Main.java file with the following complete content. The example uses IntBinaryOperator from the standard library java.util.function, which has the method applyAsInt(int, int).

~~~java
import java.util.function.IntBinaryOperator;

enum Operation implements IntBinaryOperator {
    ADD("+") {
        @Override
        public int applyAsInt(int left, int right) {
            return left + right;
        }
    },
    SUBTRACT("-") {
        @Override
        public int applyAsInt(int left, int right) {
            return left - right;
        }
    },
    MULTIPLY("*") {
        @Override
        public int applyAsInt(int left, int right) {
            return left * right;
        }
    };

    private final String symbol;

    Operation(String symbol) {
        this.symbol = symbol;
    }

    public String symbol() {
        return symbol;
    }

    @Override
    public abstract int applyAsInt(int left, int right);
}

public class Main {
    public static void main(String[] args) {
        int left = 3;
        int right = 4;

        for (Operation operation : Operation.values()) {
            int result = operation.applyAsInt(left, right);
            System.out.println(
                operation.symbol() + " " + left + " and " + right + " = " + result
            );
        }

        IntBinaryOperator operation = Operation.MULTIPLY;
        System.out.println("Through interface: " + operation.applyAsInt(6, 7));
    }
}
~~~

Compile and run from the directory containing the file:

~~~text
javac Main.java
java Main
~~~

Exact stdout output:

~~~text
+ 3 and 4 = 7
- 3 and 4 = -1
* 3 and 4 = 12
Through interface: 42
~~~

### Reading the Example Part by Part

- enum Operation implements IntBinaryOperator declares an enum that supports the two-integer operation contract.
- ADD("+"), SUBTRACT("-"), and MULTIPLY("*") pass their symbols to the shared constructor. The symbol field is final, so the symbol is assigned when the enum instance is initialized and does not change afterward.
- Each constant has a class body and overrides applyAsInt. The method has the same name, parameters, and return type, yet Java invokes the implementation attached to the constant being used.
- The declaration public abstract int applyAsInt(...) explicitly states the contract that each constant must provide. If you add a new constant without the required override, the compiler will report an error.
- The loop uses Operation.values() to iterate over the constants in declaration order. For each constant, the applyAsInt call is dispatched to the corresponding implementation.
- The operation variable at the end has type IntBinaryOperator, yet it still accepts Operation.MULTIPLY. When calling through the interface, the program does not need to know the concrete enum type to use the operation contract.

This is a complete example that can be compiled directly. There is no need to create a custom interface because the example leverages a built-in interface in the JDK.

## 4. What Is a Constant-Specific Class Body?

The part inside the curly braces immediately following an enum constant is called a constant-specific class body. For example:

~~~java
ADD("+") {
    @Override
    public int applyAsInt(int left, int right) {
        return left + right;
    }
}
~~~

This body defines how the ADD constant implements the method. Constants that have their own body have their own concrete implementation class on the Java side; they are still constants of the same Operation enum, and can still be assigned to a variable of type Operation or an interface that the enum implements.

This mechanism is polymorphism. Calling code only needs to know the method contract. Which implementation gets executed depends on the actual instance, so you do not have to write a switch statement everywhere to check whether the constant is ADD, SUBTRACT, or MULTIPLY.

It is not required that every constant have a body. If the enum provides a shared concrete method and only a few constants need different handling, you can let constants use the shared implementation and override only on the constants that need to differ. If the method is abstract, every constant must have an appropriate implementation.

## 5. When Should You Use Each Approach?

| Need | Appropriate Design Approach |
| --- | --- |
| All constants execute the same algorithm with different data | Use a constructor and final fields, then write a shared method in the enum |
| Behavior is an intrinsic part of each constant | Use a constant-specific class body to override the method |
| You want enum objects to be passed where a shared contract is accepted | Have the enum implement an interface and use it through the interface type |
| Multiple interfaces describe independent capabilities | Have the enum implement the required interfaces, as long as the design remains easy to understand |
| Logic belongs to the caller and is not core behavior of the enum | You can use a switch or an external handler class instead of stuffing all logic into the enum |

For example, if only a fixed fee rate differs, a constructor accepting the fee is usually simpler than writing a separate body for each constant. If each constant has its own algorithm, such as different rounding or calculation rules, a separate body expresses that more clearly.

Do not create an interface just to make the design look abstract. An interface is useful when you need a contract that can be used independently of a specific enum, or when multiple different types provide that same capability.

## 6. Boundary Between the Interface Contract and Abstract Methods

`IntBinaryOperator` defines the contract that calling code sees: `applyAsInt(int, int)`. `Operation` both implements that interface and declares the `abstract` method in the enum body to affirm that **each constant must provide its own algorithm**. In this example, ADD adds, SUBTRACT subtracts, and MULTIPLY multiplies, so there is no suitable shared algorithm.

If all constants differ only in data, the enum can implement the interface method once as a concrete method, instead of declaring an abstract method and creating a separate body for every constant. If only a few constants differ, use a shared method and override it only on the constants where necessary.

The main design takeaway of this lesson is that **an interface allows the caller to depend on a contract**, while a constant-specific class body determines how each constant fulfills that contract. The next lesson separately analyzes how abstract methods make the compiler verify each constant's responsibility.

## 7. Key Things to Remember About Lifecycle and State

Each enum constant is a single instance during the normal execution of the application. A constant's fields are shared by every place that references that constant. Therefore:

- Prefer private final fields for configuration data such as symbols, codes, or display names.
- Avoid storing data that varies per request, user, or invocation in mutable enum fields. Shared state can cause threads to interfere with one another.
- If a method only computes a result from its parameters, keeping it free of side effects makes it easier to test and safer for concurrent use.
- An enum constructor cannot be declared public or protected; constructors are normally left with default or private access.
- Constants are initialized as instances of the enum. Do not create constants using new Operation(...) from outside.

Enums also have utility methods such as values(), valueOf(String), and name(). valueOf looks up a constant by its exact identifier name, case-sensitively, and throws IllegalArgumentException if the name does not match. ordinal() returns the declaration position starting from 0; you should not use this position as a persisted code or business code because reordering constants will change ordinal values. If you need a stable code, declare a dedicated field such as code.

## 8. Common Mistakes and How to Handle Them

**Forgetting to implement a required method.** If an enum or constant does not provide the required implementation for an abstract method, the program will not compile. Keep method declarations clear and check all constants when adding a new value.

**Writing repetitive branching logic in multiple places.** If every call site checks the enum type with a switch to select an algorithm, consider moving the behavior into an enum method or a constant-specific class body. This groups related behavior in one place.

**Using a separate body when only data differs.** If constants differ only by a number or a label, using a constructor is usually shorter and easier to maintain. A separate body is appropriate when the algorithms truly differ.

**Trying to extend another class.** An enum already extends java.lang.Enum, so you cannot add an arbitrary superclass. If you need to share capabilities with other types, consider an interface or a collaborator object.

**Putting mutable state into an enum singleton.** A mutable field on an enum is shared across all callers. Pass data as parameters or create a dedicated object for per-request state.

**Using ordinal() as a business code.** This value depends on declaration order. Use an explicit, stable code field if you need to store or exchange data.

**Assuming an interface type loses polymorphic behavior.** When an interface variable references an enum constant, the method call still executes the constant's concrete implementation. That is the exact goal of combining an interface with constant-specific behavior.

## 9. Application Workflow

1. Identify the finite set of values and name the enum constants meaningfully.
2. Identify the contract that the values need to provide. If the contract can be used elsewhere, choose or define an appropriate interface.
3. If the constants differ only in data, declare final fields, a constructor, and a shared method.
4. If each constant has its own algorithm, write a constant-specific class body and override the necessary methods.
5. Use the enum through the enum type when enum-specific features are needed; use the interface type where only the contract is needed.
6. Compile with Java 17+, run the example, compare stdout against the expected output, and add tests for edge cases of the actual algorithm.
7. When adding a new constant, recheck all abstract methods, default behavior, and any places that convert data to or from the enum.

Good design ensures each constant expresses the behavior true to its meaning, while calling code depends only on a stable contract.
