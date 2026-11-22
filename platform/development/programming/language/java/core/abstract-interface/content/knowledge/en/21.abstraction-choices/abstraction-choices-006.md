# Liskov Substitution Principle and Contract Invariants

## Objectives

The Liskov Substitution Principle (LSP) states that an object of a subtype must be usable wherever a program expects the supertype while preserving the promised behavior. It is part of the SOLID principles and is often expressed by the idea: if `S` is a subtype of `T`, an object of `T` can be replaced with an object of `S` without breaking the correctness of the program.

In Java, an `extends` or `implements` relationship only proves a type relationship at the syntactic level. It does not by itself prove LSP. A class can compile successfully while still violating the behavioral contract that the superclass or interface promised to callers.

## 1. What Does a Behavioral Contract Include?

The contract of a method or type describes what callers are allowed to assume and what the method must guarantee.

- **Precondition:** an input condition that the caller must satisfy before calling the method.
- **Postcondition:** a result or state condition that the method commits to after successful execution.
- **Invariant:** a condition that must always hold true for the object at the points specified by the contract, especially before and after public operations.
- **History constraint:** a limit on allowed state changes over time; a subtype must not produce state transition sequences that the supertype's contract forbids.
- **Error behavior:** the exceptions and error conditions that callers may encounter when using valid inputs.

LSP requires a subtype to respect the supertype's contract. A useful way to remember this is:

1. A subtype must not strengthen preconditions: every input valid for the supertype must still be accepted by the subtype.
2. A subtype must not weaken postconditions: every guarantee of the supertype must still hold when the actual object is of the subtype.
3. A subtype must preserve the invariants that the supertype publicly commits to. A subtype may have additional invariants of its own, but maintaining them must not break the supertype's contract.
4. A subtype must respect the state transitions that users of the supertype are allowed to rely on.
5. For valid inputs, a subtype should not introduce new failures that cause a call that was valid under the supertype's contract to fail.

For example, if the supertype's contract allows calling a method with any non-negative integer, the subtype cannot arbitrarily add a requirement that the value must be less than 100. That is strengthening a precondition. If the supertype promises that a successful operation will return a non-empty list, the subtype cannot return an empty list in a similar case. That is weakening a postcondition.

## 2. Classic Example: Are a Rectangle and a Square Substitutable?

Mathematically, a square is a special rectangle. However, an "is-a" relationship in the domain model is not enough to determine an inheritance relationship in a program. Consider a rectangle class whose width and height can be changed independently.

This class's contract clearly states that `setWidth` only changes the width, while the height remains unchanged. A square class that inherits from it typically tries to ensure that the width always equals the height by overriding both setters. That maintains the square's invariant, but breaks the rectangle's promise.

Save the following code to the file `LiskovContractDemo.java`:

```java
public class LiskovContractDemo {
    public static void main(String[] args) {
        MutableRectangle rectangle = new MutableRectangle(4, 5);
        MutableRectangle squareAsRectangle = new MutableSquare(4);

        checkWidthSetterContract(rectangle);
        checkWidthSetterContract(squareAsRectangle);

        Shape rectangleShape = new RectangleShape(4, 5);
        Shape squareShape = new SquareShape(4);
        System.out.println("Shape model: rectangle area="
                + rectangleShape.area() + ", square area=" + squareShape.area());
    }

    // The Rectangle contract specifies that setWidth does not change the height.
    private static void checkWidthSetterContract(MutableRectangle rectangle) {
        int heightBefore = rectangle.getHeight();
        rectangle.setWidth(10);
        int expectedArea = 10 * heightBefore;

        System.out.printf("%s: expected area=%d, actual area=%d%n",
                rectangle.getClass().getSimpleName(), expectedArea, rectangle.area());
    }

    static class MutableRectangle {
        private int width;
        private int height;

        MutableRectangle(int width, int height) {
            this.width = width;
            this.height = height;
        }

        public void setWidth(int width) {
            this.width = width;
        }

        public void setHeight(int height) {
            this.height = height;
        }

        public int getWidth() {
            return width;
        }

        public int getHeight() {
            return height;
        }

        public int area() {
            return width * height;
        }
    }

    static final class MutableSquare extends MutableRectangle {
        MutableSquare(int side) {
            super(side, side);
        }

        @Override
        public void setWidth(int width) {
            super.setWidth(width);
            super.setHeight(width);
        }

        @Override
        public void setHeight(int height) {
            super.setHeight(height);
            super.setWidth(height);
        }
    }

    interface Shape {
        int area();
    }

    record RectangleShape(int width, int height) implements Shape {
        RectangleShape {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("Dimensions must be non-negative");
            }
        }

        @Override
        public int area() {
            return width * height;
        }
    }

    record SquareShape(int side) implements Shape {
        SquareShape {
            if (side < 0) {
                throw new IllegalArgumentException("Side must be non-negative");
            }
        }

        @Override
        public int area() {
            return side * side;
        }
    }
}
```

Compile and run with Java 17 or later:

```text
javac -encoding UTF-8 LiskovContractDemo.java
java LiskovContractDemo
```

Expected output:

```text
MutableRectangle: expected area=50, actual area=50
MutableSquare: expected area=40, actual area=100
Shape model: rectangle area=20, square area=16
```

When the argument is `MutableRectangle(4, 5)`, setting the width to 10 preserves the height of 5, so the area is 50. When passing `MutableSquare(4)` through the same `MutableRectangle` reference type, calling `setWidth(10)` also changes the height to 10; the area becomes 100 instead of 40 as the caller is allowed to expect under the superclass contract. The program still compiles, but the behavior violates LSP.

## 3. Redesigning with Behavioral Abstraction

If callers only need to know the area, not every shape should be required to have independent width and height setters. Describe the shared behavior with a `Shape` interface, and let rectangle and square be two separate types. The final part of the program above illustrates this approach: both types can be used through `Shape`, and the shared contract only requires providing the area.

This design preserves the distinct characteristics of each type:

- `RectangleShape` stores width and height independently.
- `SquareShape` stores a single side, so it cannot end up in a state with two different sides.
- Both satisfy the `area()` contract and do not need to pretend that their resizing operations have the same semantics.

Another solution is to use composition instead of inheritance if two classes need to share code but do not share the same behavioral contract. Inheritance should represent substitutability, not merely a way to reuse some fields or methods.

## 4. Supertype and Subtype Invariants

Invariants help define which state conditions must always hold true. For example, a bank account may require the account number to remain unchanged after creation; a set may require no duplicate elements; a square requires both sides to be equal.

When creating a subtype, check two groups of conditions:

- **Supertype invariants:** must still hold true for every subtype object used through the supertype. Guarantees that callers already rely on must not be lost.
- **Additional subtype invariants:** are allowed to be stricter, provided the subtype can maintain them without changing the behavior promised by the supertype.

A subtype-specific invariant can make inheritance impossible. In the example above, a square requires its width and height to be equal; the rectangle class allows those two values to change independently. When the same object must satisfy both contracts, the two requirements conflict. This is a sign that you should change the abstraction or model separate types through a smaller interface.

Invariants should not be confused with preconditions. An invariant describes the valid state of an object; a precondition describes what a caller must satisfy for a specific call. If a subtype rejects a call that the supertype accepts just to protect its own invariant, the inheritance design is likely wrong.

## 5. How to Evaluate an Inheritance Relationship in Java

For each subclass or class implementing an interface, ask yourself:

1. **Inputs:** Are there any inputs valid under the supertype's contract that the subtype rejects?
2. **Results:** Does the subtype return a weaker result, omit guarantees, or produce a different state from what callers were promised?
3. **State:** After a valid call, do the supertype's public invariants still hold?
4. **Operation sequences:** Is there any sequence of operations valid for the supertype that becomes invalid or produces unexpected results when using a subtype?
5. **Exceptions:** Does the subtype throw a new exception in cases where the supertype's contract promises success?
6. **Semantics:** Do the method names and the subtype's actual behavior still align with how callers understand the supertype's contract?

Java can check part of the overriding rules at the language level. For example, an overriding method cannot reduce access visibility, the return type can be compatible under covariance rules, and it cannot declare broader checked exceptions than those allowed by the overridden method. However, the compiler cannot prove that business-level preconditions, postconditions, and invariants have been preserved. Therefore, code compiling successfully is not enough to conclude that the design adheres to LSP.

## 6. Practices for Keeping Contracts Stable

- **Write clear contracts:** Javadoc should state input conditions, results, state effects, and important exceptions of public methods.
- **Keep interfaces small and focused:** include in an interface only the behaviors that every implementing type can provide with the same meaning.
- **Prefer immutability when appropriate:** immutable types generally carry less risk of violating history constraints because their state does not change after creation.
- **Use composition when contracts are incompatible:** sharing an implementation does not require sharing an inheritance relationship.
- **Test the contract:** run the same behavioral test suite against the base class and the implementing classes. Testing does not prove every case, but it can catch practical violations such as the rectangle/square example.
- **Test operation sequences:** do not only check a single isolated call; exercise the sequences of state changes that users of the supertype are allowed to perform.

## Key Takeaways

LSP is a behavioral principle: a subtype must uphold the commitments that callers are allowed to rely on when working with the supertype. Do not strengthen preconditions, do not weaken postconditions, and preserve invariants and valid state transitions. If a subclass must break its superclass's contract to maintain its own rules, consider using an interface representing shared behavior, splitting abstractions, or switching to composition instead of forcing an inheritance relationship.
