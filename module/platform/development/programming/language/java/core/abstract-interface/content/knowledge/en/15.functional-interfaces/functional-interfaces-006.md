# Lambda expression as a way to provide an implementation

A lambda expression is syntax introduced by Java starting in Java 8 to pass a piece of behavior where an object of a **functional interface** type is needed. A lambda is often a concise way to provide the body for that interface's single abstract method.

A lambda does not create an independent data type on its own. The compiler determines the target type from the context, such as an assigned variable, a method parameter, or a cast. Therefore, a lambda is valid only when the context determines the corresponding functional interface.

## 1. Functional interfaces are the foundation of lambdas

A functional interface is an interface with exactly one abstract method according to Java's rules. This method is also called a **SAM** (*Single Abstract Method*). A lambda provides the implementation for that method.

~~~java
@FunctionalInterface
interface Greeter {
    String greet(String name);
}
~~~

An implementation can be provided using a lambda:

~~~java
Greeter greeter = name -> "Xin chào, " + name;
System.out.println(greeter.greet("An"));
~~~

Output:

~~~text
Xin chào, An
~~~

The **@FunctionalInterface** annotation is not required to use a lambda, but it should be used because the compiler will report an error if the interface no longer satisfies the functional interface rules. An interface can still declare **default** and **static** methods; they do not increase the number of abstract methods. Inherited abstract methods with the same signature can also be considered a single method. Methods corresponding to public methods of **Object**, such as **equals(Object)**, do not increase the number of SAM methods.

An interface with two independent abstract methods cannot be implemented by a single lambda:

~~~java
interface InvalidHandler {
    void start();
    void stop();
}

// Invalid:
// InvalidHandler handler = () -> System.out.println("run");
~~~

If both behaviors are needed, redesign the interface or use a full implementing class.

## 2. Syntax and how to read lambdas

Common forms:

~~~java
() -> doSomething()
value -> value * 2
(left, right) -> left + right
(String value) -> value.trim()
(value) -> {
    String normalized = value.trim();
    return normalized.toUpperCase();
}
~~~

Reading rules:

- The part on the left of **->** is the parameter list; the part on the right is an expression or a block of statements.
- When there are no parameters, use **()**.
- With a single parameter whose type is inferred, the parentheses can be omitted: **value -> ...**.
- When there are multiple parameters, place them in parentheses and separate them with commas.
- Parameter types can be specified explicitly, but if types are specified, they must be written consistently for the parameters in the same list.
- When the lambda body is an expression, the expression's value is returned if the method has a return type. With a block body **{ ... }**, **return** must be used when the method needs to return a value; the block of a **void** method does not return a value.
- Parameter types are usually inferred from the target type, so there is no need to repeat the types unless it makes the code clearer.

For example, the following two forms can be equivalent when the target type is already **Function&lt;Integer, Integer&gt;**:

~~~java
Function<Integer, Integer> doubled = value -> value * 2;
Function<Integer, Integer> alsoDoubled = (Integer value) -> value * 2;
~~~

The compiler cannot infer the target type if a lambda is written standing alone. For instance, **var f = value -> value + 1;** is invalid because there is no target type from which to infer the lambda's type. Declare the functional interface type explicitly or provide the lambda in a context where the type is already determined.

## 3. Complete program: defining a custom interface and using a built-in interface

Create the file **LambdaAsImplementationDemo.java**:

~~~java
import java.util.Locale;
import java.util.function.Predicate;

public class LambdaAsImplementationDemo {
    @FunctionalInterface
    interface TextFormatter {
        String format(String value);
    }

    public static void main(String[] args) {
        TextFormatter upper = value -> value.toUpperCase(Locale.ROOT);
        TextFormatter wrapped = value -> "[" + value + "]";

        System.out.println(upper.format("java"));
        System.out.println(wrapped.format("lambda"));

        Predicate<String> nonBlank =
                value -> value != null && !value.isBlank();

        System.out.println(nonBlank.test("hello"));
        System.out.println(nonBlank.test("   "));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac LambdaAsImplementationDemo.java
java LambdaAsImplementationDemo
~~~

Exact stdout output:

~~~text
JAVA
[lambda]
true
false
~~~

In the example above, the variables **upper** and **wrapped** have type **TextFormatter**; each lambda provides an implementation for the **format** method. The variable **nonBlank** has type **Predicate&lt;String&gt;**; the lambda provides an implementation for the **test** method, returning **true** or **false**. The condition check **value != null** must come before **value.isBlank()** to avoid calling a method on a null value. **String.isBlank()** has been available since Java 11.

## 4. Common functional interfaces in the Java library

| Interface | Abstract method | Common purpose |
|---|---|---|
| **Runnable** | **void run()** | Action with no parameters and no return value |
| **Supplier&lt;T&gt;** | **T get()** | Supplies a value |
| **Consumer&lt;T&gt;** | **void accept(T)** | Accepts and processes a value |
| **Function&lt;T, R&gt;** | **R apply(T)** | Transforms a value of type T into type R |
| **Predicate&lt;T&gt;** | **boolean test(T)** | Tests a condition |
| **UnaryOperator&lt;T&gt;** | **T apply(T)** | Accepts and returns the same type T |
| **BiFunction&lt;T, U, R&gt;** | **R apply(T, U)** | Combines two inputs to produce a result |
| **BinaryOperator&lt;T&gt;** | **T apply(T, T)** | Combines two values of the same type to produce a value of the same type |
| **Comparator&lt;T&gt;** | **int compare(T, T)** | Determines the comparison order of two objects |

The common interfaces above are in **java.lang** or **java.util.function**; **Comparator** belongs to **java.util**. These types allow APIs to accept behavior as a parameter instead of forcing callers to create a separate class for each case.

~~~java
Predicate<String> startsWithJ = text -> text.startsWith("J");
Function<String, Integer> length = text -> text.length();
Consumer<String> print = text -> System.out.println(text);
Supplier<String> defaultName = () -> "Guest";

System.out.println(startsWithJ.test("Java")); // true
System.out.println(length.apply("Java"));     // 4
print.accept(defaultName.get());              // Guest
~~~

The snippet above illustrates the syntax; when placing it in a program, you need to add the corresponding imports for **Predicate**, **Function**, **Consumer**, and **Supplier** from **java.util.function**.

## 5. Using lambdas as callbacks for APIs

A major benefit of lambdas is passing processing behavior into an API. For example, **List.sort** accepts a **Comparator**, while **forEach** accepts a **Consumer**.

Create the file **LambdaSortDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LambdaSortDemo {
    record Course(String name, int durationHours) {}

    public static void main(String[] args) {
        List<Course> courses = new ArrayList<>(List.of(
                new Course("Streams", 4),
                new Course("Lambda", 2),
                new Course("Generics", 3)
        ));

        courses.sort((left, right) ->
                Integer.compare(left.durationHours(), right.durationHours()));

        courses.forEach(course ->
                System.out.println(course.name() + ": " + course.durationHours()));
    }
}
~~~

Compile and run:

~~~bash
javac LambdaSortDemo.java
java LambdaSortDemo
~~~

Stdout output:

~~~text
Lambda: 2
Generics: 3
Streams: 4
~~~

The lambda passed to **sort** compares the durations of two courses; a negative number, zero, or a positive number indicates coming before, being equal, or coming after, respectively, according to the **Comparator** contract. The lambda passed to **forEach** prints each element. A lambda itself does not create threads or run asynchronously; the API invokes it when and how the API specifies.

## 6. Block lambda bodies and return values

Use an expression body when the behavior is concise. Use a block body when multiple steps, local variables, conditionals, or error handling are needed.

~~~java
import java.util.function.IntUnaryOperator;

IntUnaryOperator addTenPercent = price -> {
    int tax = Math.round(price * 0.1f);
    return price + tax;
};

System.out.println(addTenPercent.applyAsInt(100));
~~~

The result is **110**. This snippet illustrates an expression that can be placed inside a method; if you want to run it standalone, place the declaration and the print statement inside **main** of a Java class.

For a functional interface with a non-**void** return type, every execution branch of a block body must return an appropriate value. You cannot omit **return** simply because the lambda spans multiple lines. For an interface returning **void**, a block body can contain multiple statements, but it must not return a value.

## 7. Local variables used by a lambda

A lambda can read local variables in the enclosing scope if the variable is **final** or **effectively final**: the variable is assigned once and not reassigned afterward.

~~~java
int offset = 10;
IntUnaryOperator addOffset = value -> value + offset;
System.out.println(addOffset.applyAsInt(5)); // 15
~~~

The following example is invalid because **offset** is reassigned after being used in the lambda:

~~~java
int offset = 10;
IntUnaryOperator addOffset = value -> value + offset;
offset = 20; // Compile error: offset is no longer effectively final
~~~

This rule applies to captured local variables and method parameters. A lambda can still read or modify the state of an object that the variable references, if access allows; however, the immutability of the reference does not mean the referenced object is immutable. Be careful with shared state in multithreaded processing.

## 8. Scope of this and variable names

Inside a lambda, **this** refers to the enclosing object where the lambda is written. A lambda does not create an anonymous nested class with its own **this** object. This is an important difference from an anonymous class, where **this** inside the body normally refers to the anonymous class instance.

A lambda parameter cannot share the same name as a local variable already declared in the same enclosing scope. Choose meaningful parameter names and avoid shadowing variable names that make the code harder to read.

## 9. Exception checking

The SAM method type determines which checked exceptions the lambda body is allowed to throw. If the abstract method does not declare a checked exception, the lambda cannot directly throw that checked exception without handling or converting it. For example, **Runnable.run()** declares no checked exceptions, whereas **Callable.call()** can throw **Exception**.

When integrating an API that can throw exceptions, handle them in an appropriate place or define a functional interface with a suitable exception signature. You should not mechanically wrap every exception into a runtime exception, because doing so loses information about how callers need to handle errors.

## 10. Lambdas and method references

When a lambda only calls one method with the corresponding arguments, a **method reference** can express the same intent more concisely:

~~~java
Function<String, String> trimWithLambda = text -> text.trim();
Function<String, String> trimWithReference = String::trim;
~~~

Some forms of method references are **ClassName::staticMethod**, **object::instanceMethod**, and **ClassName::instanceMethod**. A method reference also requires a functional interface type as its target type; this is a related syntax that can replace a lambda when the signatures are compatible.

## 11. Lambdas vs. anonymous classes

A lambda is suitable when you need to provide a single behavior for a functional interface. It is concise, directly expresses the behavior passed to an API, and uses the **this** context of the enclosing class.

Anonymous classes remain useful when you need to declare multiple methods, override additional behavior, or need a subclass of an abstract class rather than implementing a functional interface. Not every anonymous class can be replaced by a lambda because a lambda only targets a functional interface.

You should not rely on two lambdas with the same body necessarily being equal or being the same instance; the identity of a lambda object is not guaranteed in that way. If you need to compare results, compare the outputs or domain data.

## 12. Common errors and how to fix them

- **Interface with multiple abstract methods:** only use a lambda when the target type is a functional interface; review the design and use **@FunctionalInterface** so the compiler checks it.
- **Missing target type:** declare the variable with a functional interface type, pass the lambda to a parameter with an explicit type, or cast it when truly necessary.
- **Mismatched parameter or return type:** match the lambda signature with the SAM method, including **void** and return types.
- **Missing return in a block body:** add **return** for every branch when the SAM method requires a result.
- **Reassigning a captured local variable:** keep the variable final/effectively final or redesign how data is passed.
- **Ambiguity when calling an overloaded method:** if multiple overloads accept functional interfaces with compatible shapes, the compiler may not be able to choose; provide explicit parameter types or cast to the appropriate target interface.
- **Assuming a lambda runs in parallel on its own:** a lambda only describes behavior; the execution thread is determined by the code that invokes the lambda.
- **Putting too much logic into a single lambda:** extract complex logic into a named method to make testing and maintenance easier.

## 13. Process for choosing and writing a lambda

1. Identify what behavior the API requires and find the API's functional interface parameter type.
2. Check the SAM signature: number of parameters, parameter types, return type, and declared exceptions.
3. Write a lambda matching that signature; let the compiler infer types when the context is already clear.
4. Choose an expression body for simple processing or a block body for multiple steps.
5. Check capture rules, name scoping, exceptions, and overloads that could cause ambiguity.
6. Run the example with representative inputs, verify stdout or the actual result, and keep the implementation clear enough to maintain.

Lambdas allow Java to pass behavior as a value through functional interfaces. Once you understand target types and SAM signatures, you can use lambdas to implement callbacks, filtering, mapping, sorting, and many other API operations without having to create a separate class for each small behavior.
