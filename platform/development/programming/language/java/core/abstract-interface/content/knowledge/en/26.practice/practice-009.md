# Comparing a Lambda with an Anonymous Class in the Same Problem

Both lambda expressions and anonymous classes allow providing an inline implementation for a target type in Java. When working with a functional interface, both can perform the same task and produce the same result. The differences lie in syntax, the scope of the this keyword, the ability to declare dedicated state, and the kinds of interfaces each approach can implement.

This lesson compares both approaches on the same problem of checking whether a string has content, and then uses a short example to clarify the difference regarding this. The complete examples use Java 17; lambdas and functional interfaces have been available since Java 8.

## 1. Common Problem: Validating a String

Suppose a program needs a rule to determine whether a string has a usable value. The rule returns true when the string is non-null and neither empty nor whitespace-only. Java provides the built-in functional interface Predicate&lt;T&gt; with the abstract method test(T), which is well suited for this problem.

You can implement the same rule using a lambda:

~~~java
Predicate<String> validator =
        text -> text != null && !text.isBlank();
~~~

Or using an anonymous class:

~~~java
Predicate<String> validator = new Predicate<String>() {
    @Override
    public boolean test(String text) {
        return text != null && !text.isBlank();
    }
};
~~~

Both variables have the type Predicate&lt;String&gt;, so the client calls validator.test(text) in the exact same way. The lambda shortens the syntax surrounding the method; the anonymous class explicitly represents an unnamed class implementing the interface and overriding the test method.

## 2. Complete Program for Comparison

Save the following code as the file LambdaVsAnonymousDemo.java:

~~~java
import java.util.function.Predicate;

public class LambdaVsAnonymousDemo {
    private final String name = "outer";

    public static void main(String[] args) {
        Predicate<String> lambdaValidator =
                text -> text != null && !text.isBlank();

        Predicate<String> anonymousValidator = new Predicate<>() {
            @Override
            public boolean test(String text) {
                return text != null && !text.isBlank();
            }
        };

        String[] samples = {"Java", "", "   "};
        for (String sample : samples) {
            System.out.println("'" + sample + "' -> lambda="
                    + lambdaValidator.test(sample) + ", anonymous="
                    + anonymousValidator.test(sample));
        }

        new LambdaVsAnonymousDemo().compareThis();
    }

    private void compareThis() {
        Runnable lambda =
                () -> System.out.println("lambda this=" + this.name);

        Runnable anonymous = new Runnable() {
            private final String name = "anonymous";

            @Override
            public void run() {
                System.out.println("anonymous this=" + this.name);
                System.out.println("outer via qualified this="
                        + LambdaVsAnonymousDemo.this.name);
            }
        };

        lambda.run();
        anonymous.run();
    }
}
~~~

Compile and run:

~~~text
javac LambdaVsAnonymousDemo.java
java LambdaVsAnonymousDemo
~~~

Exact stdout output:

~~~text
'Java' -> lambda=true, anonymous=true
'' -> lambda=false, anonymous=false
'   ' -> lambda=false, anonymous=false
lambda this=outer
anonymous this=anonymous
outer via qualified this=outer
~~~

The first three lines show that both approaches implement the same rule and produce identical results for a string with content, an empty string, and a whitespace-only string. The last three lines illustrate an important semantic difference: the lambda uses the this of the enclosing object, whereas this inside an anonymous class points to that anonymous object itself.

In the example, the syntax new Predicate<>() uses the diamond operator with an anonymous class, which has been supported since Java 9. If compatibility with Java 8 is required, write new Predicate&lt;String&gt;() with the full type argument.

## 3. Differences in Syntax and Target Type

A lambda has the general form consisting of a parameter list, an arrow, and an expression body or block body. When the parameter types can be inferred from the target type, explicit type declarations are usually unnecessary.

~~~java
Predicate<String> hasText = text -> !text.isBlank();
Predicate<String> hasTextExplicit =
        (String text) -> !text.isBlank();
~~~

An anonymous class uses a new expression to declare an unnamed class and simultaneously create an instance of it. Its body can declare fields, methods, and initializer blocks, while the required methods of the interface must be implemented with the exact signatures.

Both require an appropriate type context. A lambda can only be used when the target type is a functional interface: an interface with exactly one abstract method according to Java rules, after accounting for methods corresponding to public methods of Object as well as default or static methods. The @FunctionalInterface annotation is not required, but it helps the compiler report an error if the interface no longer satisfies the condition.

An anonymous class can implement an interface that is not a functional interface, because it can define implementations for multiple abstract methods. It can also extend a concrete class and override that class's methods. A lambda cannot directly replace these cases.

For example, the following interface has two abstract methods:

~~~java
interface AuditAction {
    void record(String event);
    void flush();
}
~~~

An anonymous class can provide both methods:

~~~java
AuditAction action = new AuditAction() {
    @Override
    public void record(String event) {
        System.out.println("record: " + event);
    }

    @Override
    public void flush() {
        System.out.println("flush");
    }
};
~~~

You cannot write a single lambda to implement AuditAction, because there is no single abstract method serving as the target function contract. If an API is designed to accept a lambda, create a functional interface with one primary operation and separate other responsibilities into appropriate APIs.

## 4. Differences in this and Name Scope

A lambda does not create a new this scope. When a lambda body references this, it refers to the object of the enclosing class. This makes it natural for a lambda to read fields or call methods of the outer object.

An anonymous class has its own object scope. Inside a method of an anonymous class, this refers to the anonymous instance. To access the enclosing object, you can use the syntax OuterClass.this, where OuterClass is the name of the enclosing class.

In the program above:

- The lambda prints lambda this=outer because this.name is a field of LambdaVsAnonymousDemo.
- The anonymous class declares its own name field with the value anonymous; therefore, this.name inside run() accesses the field of the anonymous class.
- LambdaVsAnonymousDemo.this.name explicitly accesses the name field of the outer object.

This is a semantic difference, not just a difference in line count. When converting an anonymous class to a lambda or vice versa, check every reference to this, super, fields with the same name, and method calls. A mechanical conversion can change behavior if the original code relied on the anonymous class's this object.

## 5. State, Fields, and Additional Methods

An anonymous class can declare instance fields, initializer blocks, and additional methods. The example above declares a dedicated name field inside the anonymous class. These members belong to the anonymous instance and can be used by its methods.

A lambda does not declare a new class in source syntax, so it cannot contain instance field declarations or its own member methods like the body of an anonymous class. If you need state with its own lifecycle, multiple related operations, or an API with multiple methods, consider an anonymous class, a named class, or a dedicated class.

A lambda can still read local variables in the enclosing scope, provided they are final or effectively final. This capture rule also applies to anonymous classes. Effectively final means the variable is assigned once and is not reassigned afterward.

~~~java
String prefix = "event: ";
Predicate<String> hasPrefix =
        text -> text != null && text.startsWith(prefix);
~~~

This example is valid because prefix is not reassigned. If the program assigns a different value to prefix after creating the lambda, the code will not compile. For both lambdas and anonymous classes, when state needs to change over time, it is usually better to encapsulate the state in an object with a clear responsibility rather than trying to mutate a captured local variable.

## 6. When Should You Use Each Approach?

Prefer a lambda when representing a simple action through a functional interface, such as Predicate, Function, Consumer, Supplier, Comparator, or an application-defined functional interface. A lambda helps focus on the logic to be performed and reduces implementation syntax.

An anonymous class is suitable when you need to implement multiple abstract methods, add dedicated state, override multiple behaviors, or use an unnamed class as a subtype of a concrete class. It can also help clarify structure when the implementation is more complex than a short expression.

| Criterion | Lambda | Anonymous class |
|---|---|---|
| Target type | Must be a functional interface | Can be a regular interface or an extendable class |
| Number of methods to implement | One functional method | Can implement multiple methods |
| Syntax | Usually concise; parameter types can be inferred | Explicit with new and a class body |
| this | this of the enclosing scope | this of the anonymous instance |
| Instance fields and additional methods | Cannot be declared directly in the lambda body | Can be declared inside the anonymous class |
| Local variable capture | Variable must be final or effectively final | Same rule |
| Best suited for | An action or transformation | An implementation with multiple members or dedicated state |

You should not conclude that a lambda is always faster or always uses less memory than an anonymous class. The runtime implementation and JVM optimizations depend on context; the choice should be based on the API contract, correctness, readability, and actual measurement if performance is a concern.

## 7. Common Mistakes When Converting

- **Using a lambda for an interface with multiple abstract methods:** there is no single functional method for the lambda to implement. Use an anonymous class or redesign the API.
- **Forgetting to check this:** a lambda uses the this of the enclosing class, whereas an anonymous class has its own this. Check this references and matching field names.
- **Reassigning a captured variable:** a local variable used in a lambda or an anonymous class must be final or effectively final.
- **Omitting parts of the method body:** when converting an anonymous class to a lambda, preserve the logic, conditions, order of side effects, and exception handling.
- **Assuming the two approaches are always equivalent:** they may achieve the same result in a simple problem, but they differ in this scope, class members, and target type.
- **Using an anonymous class when a lambda is clear enough:** for a simple operation, verbose class syntax can obscure the main logic.
- **Using a lambda when an object with multiple responsibilities is needed:** if there are multiple methods, dedicated state, or complex behavior, a named class may be easier to test and maintain.

## 8. Comparison and Testing Process

When converting a piece of code from an anonymous class to a lambda or vice versa, follow this process:

1. Identify the target type and the method that the client actually calls.
2. Write both implementations with the same input conditions, logic, and expected results.
3. Run both on normal cases, empty inputs, null if the API allows it, and meaningful edge cases.
4. Compare side effects, exceptions, method invocation order, and variable capture.
5. Pay special attention to checking this, fields with the same name, and inherited methods.
6. Compile with the target Java version to catch unsupported syntax or APIs.

In the string validation example, both implementations return the same results for the three tested inputs. The this example shows why comparing based solely on the output of a simple problem is not enough to conclude that the two constructs are always interchangeable.

## 9. Practice Exercises

1. Replace Predicate&lt;String&gt; with a custom functional interface that has the method boolean isValid(String text). Write both a lambda and an anonymous class, then test them with the same dataset.
2. Create an interface with two abstract methods. Implement it using an anonymous class and explain why a single lambda cannot be used directly.
3. Add a captured local variable to both implementations. Verify that reassigning that variable after declaration causes a compilation error.
4. Inside an anonymous class, declare a field with the same name as a field in the outer class. Compare this.field with OuterClass.this.field.
5. Convert an existing anonymous class to a lambda and list the differences that need to be checked before accepting the change.

Choosing the right approach starts with the contract that the client needs: if it is a single operation of a functional interface, a lambda is usually the concise and clear choice; if multiple methods, dedicated state, or an independent this object scope is required, an anonymous class or a named class expresses the intent more accurately.
