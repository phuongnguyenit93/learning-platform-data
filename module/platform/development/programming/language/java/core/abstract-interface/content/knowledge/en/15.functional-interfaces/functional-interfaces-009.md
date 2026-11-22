# Limitations with Sealed Interfaces and Generic Functional Methods

This lesson focuses on two mechanisms that are often confused when designing Java APIs: `sealed interface` for restricting a type hierarchy, and an abstract method with generic type parameters in a functional-style interface. The examples use Java 17 or later; the section on pattern matching for `switch` requires Java 21 or later.

## 1. Distinguishing the Two Goals

- A **sealed interface** specifies which types are permitted to directly implement the interface. It helps model a bounded set of variants, such as a success or failure result.
- A **functional interface** provides a functional contract so that a lambda or method reference can be passed. This contract needs an abstract method compatible with Java's representation of functions.
- A **generic interface** can accept type parameters at the interface level, for example `Converter<S, T>`. Once a concrete type such as `Converter<String, Integer>` is chosen, the functional method has clear input and output types.
- A **generic method** declares type parameters directly on the method, for example `<T> T identity(T value)`. This case has limitations when using lambdas, because a lambda cannot declare the type parameters of the target method.

These mechanisms solve different problems. An interface can be generic and use lambdas very naturally; a sealed interface can be generic; however, a sealed interface should not be used as a target type for a lambda, and an abstract method that declares its own type parameters cannot be implemented with a regular lambda.

## 2. Rules for Sealed Interfaces

A sealed interface uses the `sealed` keyword and typically lists the types permitted to implement it directly using `permits`.

~~~java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String message) implements Outcome<T> {
}
~~~

In the example, `Outcome<T>` allows only `Success` and `Failure` to implement it directly. Records are implicitly `final`, so they satisfy the rule for direct subtypes of a sealed type. The `permits` list uses type names without writing type parameters such as `Success<T>`.

Important rules:

1. Every direct subtype listed in `permits` must actually extend or implement that sealed type.
2. If the sealed type is in a named module, its direct subtypes must belong to the same module. If it is not in a named module, they must belong to the same package.
3. Every direct subtype must declare `final`, `sealed`, or `non-sealed`. Records are already final, so there is no need to add `final`.
4. `final` closes the inheritance branch at that type. `sealed` continues to restrict subtypes at the next level. `non-sealed` reopens that branch so that further subtypes can be derived.
5. `permits` can be omitted if the compiler can infer the list of subtypes from declarations within the same compilation unit. When the types are in different files, declare `permits` explicitly.
6. A sealed type restricts direct inheritance relationships; it does not automatically validate data or guarantee that every branch handles business logic correctly.

A sealed interface can have type parameters. Whether a type is sealed or not controls the class/type hierarchy; generics control the type relationships between values and the API. These two mechanisms complement each other.

## 3. Generic Functional Interfaces Can Use Lambdas

The approach that usually fits best is to place type parameters at the interface level, while the abstract method does not declare its own separate type parameters.

~~~java
@FunctionalInterface
interface Converter<S, T> {
    T convert(S source);
}

class ConverterDemo {
    public static void main(String[] args) {
        Converter<String, Integer> length = String::length;
        System.out.println(length.convert("Java"));
    }
}
~~~

Compile and run commands:

~~~text
javac ConverterDemo.java
java ConverterDemo
~~~

Output:

~~~text
4
~~~

With `Converter<String, Integer>`, the compiler determines that the method must be compatible with a `String` input and an `Integer` output. `String::length` returns `int`, which is boxed into `Integer`, so this method reference is compatible.

A lambda also works:

~~~java
Converter<String, Integer> length = text -> text.length();
~~~

If the compiler cannot infer parameter types due to overloading or a complex context, you can declare the types explicitly, for example `(String text) -> text.length()`.

## 4. Limitations of Abstract Methods That Declare Their Own Generic Types

Consider an interface with an abstract method that declares `<T>` directly on the method:

~~~java
interface UniversalIdentity {
    <T> T identity(T value);
}

final class Identity implements UniversalIdentity {
    @Override
    public <T> T identity(T value) {
        return value;
    }
}
~~~

The `Identity` class is valid because its method redeclares the type parameter `<T>` and works for any type T. However, this implementation cannot be replaced with a regular lambda:

~~~java
UniversalIdentity identity = value -> value; // Does not compile
~~~

The compiler rejects the lambda because the target method has a generic descriptor: the method itself declares a type parameter. Lambda syntax provides no place to declare the type parameters of the target method. A lambda cannot assume that the type of `value` is just a single fixed type; the contract requires the method to work for every T.

This is an important distinction:

- `Converter<String, Integer>` fixes the types for a specific use, so a lambda can match `String -> Integer`.
- `<T> T identity(T value)` requires a method with its own type parameter and must preserve the type relationship for every T. Implement it using a concrete class or an anonymous class instead of a lambda.
- Having an interface with exactly one abstract method does not automatically mean that any lambda expression can implement that method; the method's descriptor must also be compatible with lambdas.

If the goal is simply to create a conversion function whose input and output types are chosen when declaring the variable, prefer type parameters at the interface level. Only use a generic method when each call needs to choose an independent type T on its own.

## 5. Why You Should Separate Sealed Models from Lambda Callbacks

A sealed interface is suitable for representing known domain variants. A lambda, by contrast, needs a target type that can be implemented by a class generated by the compiler/runtime; that implementation class cannot be listed beforehand in a `permits` list. Therefore, do not design a sealed interface as the target for a lambda or method reference.

A suitable design pattern is to make the callback a regular functional interface, while the result returned by the callback can be a sealed interface:

~~~java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String message) implements Outcome<T> {
}

@FunctionalInterface
interface Parser<T> {
    Outcome<T> parse(String input);
}
~~~

Here, `Parser<T>` can accept a lambda because `Parser` itself is not sealed. The function's result is still restricted to the two forms `Success<T>` and `Failure<T>`. This design cleanly separates two responsibilities: the callback can be swapped flexibly, while the result variants are controlled.

## 6. Complete Java Example

Save the following snippet as `OutcomeDemo.java`. All types are in the same compilation unit so the `permits` list is clear.

~~~java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String message) implements Outcome<T> {
}

@FunctionalInterface
interface Parser<T> {
    Outcome<T> parse(String input);
}

interface UniversalIdentity {
    <T> T identity(T value);
}

final class Identity implements UniversalIdentity {
    @Override
    public <T> T identity(T value) {
        return value;
    }
}

public class OutcomeDemo {
    public static void main(String[] args) {
        Parser<Integer> parser = text -> {
            try {
                return new Success<>(Integer.parseInt(text));
            } catch (NumberFormatException ex) {
                return new Failure<>("Not an integer: " + text);
            }
        };

        System.out.println(parser.parse("42"));
        System.out.println(parser.parse("x"));

        UniversalIdentity identity = new Identity();
        String word = identity.identity("Java");
        Integer number = identity.identity(17);
        System.out.println(word + " " + number);
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac OutcomeDemo.java
java OutcomeDemo
~~~

Exact stdout output:

~~~text
Success[value=42]
Failure[message=Not an integer: x]
Java 17
~~~

The example illustrates three things at once: `Outcome<T>` restricts the possible result forms; `Parser<Integer>` is a generic functional interface that a lambda can implement; `UniversalIdentity` holds a generic method and requires an implementation class with an explicit `<T>` declaration.

## 7. Generics, Type Erasure, and Pattern Matching

Generic type parameters are primarily checked at compile time. After type erasure, you cannot rely on the runtime to distinguish all generic type arguments. For example, checking `instanceof Success<String>` is generally invalid because `Success<String>` is not a type that can be fully checked at runtime. You can check the general form using `instanceof Success<?> success`, then handle the value according to the types the API permits.

The invariance of generics must also be kept in mind: `Outcome<Integer>` is not an `Outcome<Number>`, even though `Integer` is a subtype of `Number`. When an API needs to accept multiple subtypes, consider wildcards such as `Outcome<? extends Number>` in accordance with the direction in which data is read or written.

Starting in Java 21, pattern matching for `switch` can leverage sealed hierarchies so that the compiler checks branch exhaustiveness. Exhaustiveness checking depends on the selector type, the permitted subtypes, and the patterns; when a hierarchy involves generics or a `non-sealed` branch, carefully verify the pattern types instead of assuming the compiler will always infer every case. A sealed hierarchy also does not replace runtime error handling or input data validation.

## 8. Common Mistakes and How to Choose a Design

| Scenario | Cause | Resolution |
|---|---|---|
| Adding a new implementing type but forgetting to update `permits` | The new type is not yet in the permitted subtype set | Update the list and check the subtype's modifier |
| Direct subtype without `final`, `sealed`, or `non-sealed` | Violates the sealed hierarchy rules | Explicitly choose whether the branch is closed or open for extension |
| Assigning a lambda to a sealed interface | A sealed type is not suitable as a lambda target type | Create a functional interface that is not sealed for the callback |
| Writing a lambda for an abstract method `<T> T apply(T value)` | The target method declares its own type parameter | Use an implementing class or redesign the type parameter at the interface level |
| Using `instanceof` with `Success<String>` | Parameterized generic type is not reifiable at runtime | Check `Success<?>` and handle it according to a type-safe contract |
| Treating `Outcome<Integer>` as a subtype of `Outcome<Number>` | Java generics are invariant | Use appropriate wildcards when the API needs to accept a family of types |
| Using `non-sealed` while still assuming the entire subtree is closed | `non-sealed` allows extending the branch | Treat that branch as an extension point and design handling accordingly |

Quick selection rules:

- Choose a **sealed interface** when the data domain has a controlled set of direct variants.
- Choose a **generic functional interface** when you want to pass lambdas and have the input/output types determined by the interface's type parameters.
- Choose a **generic method** when each call must work with a type T inferred by the call itself; if that method is an abstract method, do not assume it can be implemented with a lambda.
- Combine both mechanisms by having a callback that is not sealed return a sealed result when you need both flexibility in execution and restrictions on the result forms.
