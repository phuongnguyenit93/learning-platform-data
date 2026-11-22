# Parameter Types, Return Types, and the `throws` Clause of Functional Methods

## Objectives

When working with a **functional interface** in Java, you need to understand the signature of its **functional method**: what parameters it accepts, what return type it produces, and what checked exceptions it can throw. These three parts determine where a lambda or method reference can be used, how the compiler infers types, and how callers must handle errors.

After this lesson, you will be able to:

- Accurately read the **function descriptor** of a functional interface, including its parameter list, return type, and `throws` clause.
- Distinguish the types declared in the interface from the concrete types a lambda/method reference receives from its **target type**.
- Choose among `Function`, `Consumer`, `Predicate`, `Supplier`, `BiFunction`, `ToIntFunction`, and custom functional interfaces.
- Write lambdas with matching parameters and return values, and recognize compile errors related to types or `return` paths.
- Understand why checked exceptions must be compatible with the functional method's `throws` clause; know how to declare, catch, or convert exceptions without altering semantics.
- Verify runnable Java 17 examples and explain cases that do not compile.

## 1. Functional Methods and Function Descriptors

A **functional interface** is an interface with exactly one abstract method in terms of its SAM (*single abstract method*) contract. `default` methods, `static` methods, and abstract methods matching `public` methods of `Object` do not increase the number of abstract methods that must be implemented. The `@FunctionalInterface` annotation helps the compiler verify this condition, though it is not required for an interface to be considered functional.

Example:

```java
@FunctionalInterface
interface Converter {
    String convert(String input, int repeat) throws java.io.IOException;

    default boolean isReady() {
        return true;
    }
}
```

The functional method is `convert(String, int)`. The **function descriptor** describes the corresponding callable contract:

```text
(String input, int repeat) -> String
                              throws IOException
Parameters: String, int
Result: String
Allowed checked exception: IOException
```

Each component plays a distinct role:

1. **The parameter list** specifies the number, order, and types of values passed when the function is invoked. The names `input` and `repeat` are only declaration names and do not make function types different.
2. **The return type** specifies the value the lambda must produce. `void` means no value is returned for the caller to use.
3. **The `throws` clause** specifies the exceptions allowed to escape that Java requires to be checked at compile time. Unchecked exceptions (`RuntimeException`, `Error`, and their subclasses) can still occur even if not listed in `throws`.

A method signature in the narrow Java sense includes the name and parameter types, excluding the return type and `throws`. In this lesson, we examine **the three components of the function descriptor**, without confusing the JLS “method signature” with the full function type description.

## 2. Parameter Types Determine What the Lambda Receives

Consider three interfaces:

```java
@FunctionalInterface
interface UnaryText {
    String apply(String text);
}

@FunctionalInterface
interface TextAndCount {
    String apply(String text, int count);
}

@FunctionalInterface
interface NoArgument {
    String get();
}
```

All three are functional interfaces, but lambdas cannot be swapped between them because the parameter counts differ:

```java
UnaryText trim = text -> text.trim();
TextAndCount repeat = (text, count) -> text.repeat(count);
NoArgument greeting = () -> "Hello";
```

Parameter types are guided by the **target type** on the left-hand side of the assignment (or the parameter type of a method receiving the lambda). For instance, `text -> text.trim()` does not have an independent `Function` type on its own; it is compatible with a functional interface whose method takes a `String` and returns a suitable value. With `UnaryText`, `text` is inferred as `String`.

Java allows two ways to declare lambda parameters:

```java
UnaryText a = text -> text.trim();               // String inferred
UnaryText b = (String text) -> text.trim();      // explicit declaration
TextAndCount c = (text, count) -> text.repeat(count);
TextAndCount d = (var text, var count) -> text.repeat(count);
```

With multiple parameters, parentheses are required. Within a single lambda parameter list, **do not mix** inferred parameters, explicit types, and `var` arbitrarily; for example, `(var x, int n) -> ...` is invalid. Using `var` for lambda parameters has been supported since Java 11, including when annotations are needed on parameters and applied consistently to all parameters.

Parameter types are not automatically “coerced to whatever the lambda wants”. For example:

```java
// DOES NOT COMPILE: left is String, cannot be an operand of numeric +.
UnaryText invalid = left -> left + 1; // This expression ACTUALLY compiles,
// because "+" with String is string concatenation; result "abc1", not numeric addition.
```

Recognizing type errors accurately is crucial: `String + 1` is valid because of string concatenation. A genuinely non-compiling example is:

```java
// Does not compile: cannot convert String to int.
java.util.function.IntUnaryOperator wrong = (String x) -> x.length();
```

`IntUnaryOperator` has the descriptor `(int) -> int`, so the lambda parameter cannot be declared as `String`. Instead:

```java
java.util.function.IntUnaryOperator twice = x -> x * 2;
```

Note: the snippets in this section are **illustrative snippets that must be placed in a valid declaration context**; lines marked as not compiling are solely for error recognition and must not be pasted verbatim into a runnable program.

### Generics and Concrete Types at the Use Site

A generic functional interface:

```java
@FunctionalInterface
interface Mapper<T, R> {
    R map(T value);
}

Mapper<String, Integer> length = String::length;
Mapper<Integer, String> asText = String::valueOf;
```

When substituting `T = String`, `R = Integer`, the descriptor of `length` is `(String) -> Integer`. For `asText`, the descriptor is `(Integer) -> String`. It is the same `Mapper<T,R>` definition, but each **parameterized type** creates a concrete type context for the lambda/method reference.

`Function<T,R>` in the standard library already serves this purpose; use a custom interface when domain naming or `throws` needs to be clearer. Generic types are invariant by default: `Function<Object,String>` is not automatically a subtype of `Function<String,String>` just because `String` is a subtype of `Object`; when designing APIs, you can use wildcards with appropriate variance.

## 3. Return Type: Values, `void`, and `return` Rules

In the descriptor `(T) -> R`, `R` is the return type. For an expression lambda, the expression must be compatible with that type. For a block-bodied lambda, normal completion branches and `return` statements must satisfy the return type rules.

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();

java.util.function.Predicate<String> nonBlank =
        text -> !text.isBlank();

java.util.function.Consumer<String> print =
        text -> System.out.println(text);

java.util.function.Supplier<String> defaultName =
        () -> "Guest";
```

The descriptors are respectively:

| Functional interface | Parameters | Return |
| --- | --- | --- |
| `Function<String,Integer>` | `String` | `Integer` |
| `Predicate<String>` | `String` | `boolean` |
| `Consumer<String>` | `String` | `void` |
| `Supplier<String>` | none | `String` |

Because `Integer` is a wrapper type, `text.length()` returning `int` is **boxed** into `Integer` when needed; when processing large amounts of numeric data, you can choose `ToIntFunction<String>` with descriptor `(String) -> int` to reduce boxing. Conversely, a lambda returning `String` can be used in a descriptor returning `CharSequence` thanks to return-type compatibility.

Example of a block body with an explicit return:

```java
java.util.function.Function<String, Integer> safeLength = text -> {
    if (text == null) {
        return 0;
    }
    return text.length();
};
```

If the descriptor returns `Integer`/`int`, every branch by which execution can reach the end of the block must return a compatible value or complete abruptly by throwing an exception. Error:

```java
// Does not compile: a branch can finish without a return.
java.util.function.Function<String, Integer> invalid = text -> {
    if (text.isEmpty()) {
        return 0;
    }
};
```

Whereas for `void`, a lambda block can execute statements and finish without returning a value:

```java
java.util.function.Consumer<String> printer = text -> {
    System.out.println(text);
    return; // valid, though not required
};
```

The compiler distinguishes **value-compatible** (returns a value) and **void-compatible** (compatible with a `void` function) for lambda blocks. An expression lambda that is a *statement expression*, such as `System.out.println(text)` or `list.add(value)`, can be used in a `void` context. Do not force every value-returning computation into a `Consumer` just because of that: if the caller needs the result, choose `Function` or a value-returning interface.

### Method References and Return Types

`String::length` can adapt to `Function<String,Integer>` because calling `length()` returns `int` and Java can box it to `Integer`. `"abc"::length` is a receiver-bound method reference, matching `Supplier<Integer>` with no parameters.

Pay attention to the difference between an object-bound reference and a `Type::instanceMethod` reference: in the second form, the first parameter is usually the receiver of the method call. A method reference is compatible only when the parameter count, argument types, return type, and `throws` satisfy the target contract.

## 4. The `throws` Clause of the Functional Method

Java divides exceptions into:

- **Checked exceptions**: subclasses of `Throwable` that are not `RuntimeException`/`Error` (and not in their corresponding unchecked hierarchies). The compiler requires catching or declaring them when they can be thrown, such as `IOException` or `SQLException`.
- **Unchecked exceptions**: `RuntimeException`, `Error`, and their subclasses. Not required to be declared in `throws`, though developers still need to decide how to handle them appropriately.

Consider:

```java
@FunctionalInterface
interface TextReader {
    String read(String input) throws java.io.IOException;
}
```

The descriptor is `(String) -> String throws IOException`. You can assign to it a lambda or method reference that may throw `IOException` or a **subclass** checked exception of `IOException`:

```java
TextReader reader = input -> {
    if (input.isBlank()) {
        throw new java.io.IOException("empty");
    }
    return input.trim();
};
```

A lambda that **throws no checked exceptions at all** is also compatible with a descriptor that permits `IOException`:

```java
TextReader uppercase = input -> input.toUpperCase(java.util.Locale.ROOT);
```

However, if the lambda or referenced method can throw a checked exception not permitted by the function descriptor, the assignment is a **compile error**:

```java
// Does not compile if readFile declares throws IOException:
java.util.function.Function<String, String> invalid =
        path -> readFile(path);
```

Because `Function<T,R>.apply(T)` declares no checked exceptions, `IOException` cannot arbitrarily escape from the body. `Function` has no `throws IOException` clause, even if the call site invoking `apply` is inside a `try/catch`. You must change the functional contract or catch/convert the exception **inside** the lambda.

**Distinguish three places where `throws` appears:**

1. `throws` on the **functional method** defines the checked exceptions the implementation is allowed to throw.
2. `throws` on the **method targeted by a method reference** determines whether the method reference is compatible with the target.
3. `throws` on the **method calling the functional interface** only helps the caller handle exceptions when invoking it; it does not make the target functional interface itself allow additional checked exceptions.

For example, even if `main() throws Exception`, `Function<String,String> fn = s -> readFile(s)` still fails to compile if `readFile` declares `throws IOException`. The fact that the caller can catch errors does not change the contract of `Function.apply`.

### What to Do When Checked Exceptions Are Needed?

There are three common approaches:

**(1) Create a functional interface declaring the checked exception.** Suitable when I/O is genuinely part of the contract and the caller must handle the error.

```java
@FunctionalInterface
interface CheckedFunction<T, R> {
    R apply(T input) throws java.io.IOException;
}
```

**(2) Catch the error at the lambda boundary.** Suitable when the API forces using `Function` and a valid recovery option exists; never silently swallow errors.

```java
// Illustration; readFile(String) is a method that may throw IOException.
java.util.function.Function<String, String> withFallback = path -> {
    try {
        return readFile(path);
    } catch (java.io.IOException e) {
        return "unavailable"; // only appropriate if fallback is a business rule
    }
};
```

**(3) Convert the checked exception to an unchecked exception** if the API layer does not support checked exceptions and that layer's contract accepts unchecked failures. Preserve the cause so diagnostics are not lost:

```java
java.util.function.Function<String, String> wrapping = path -> {
    try {
        return readFile(path);
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
};
```

Do not default to converting every `IOException` into a `RuntimeException` just to use Stream. Changing exception types affects callers, retry policies, error observability, and transactions. If possible, separate I/O before running a pure transformation pipeline.

## 5. Complete Java 17 Example, Compile and Run

The following program illustrates the three elements of a function descriptor, a valid lambda throwing no checked exceptions, a method reference to a method with `throws IOException`, and a generic functional interface with an exception type parameter.

Create the file **`FunctionalMethodSignatureDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.Locale;

public class FunctionalMethodSignatureDemo {
    @FunctionalInterface
    interface TextReader {
        String read(String input) throws IOException;
    }

    @FunctionalInterface
    interface Summary {
        String format(String label, int quantity);
    }

    @FunctionalInterface
    interface TextLength {
        int length(String input);
    }

    @FunctionalInterface
    interface CheckedMapper<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    static String firstLine(String value) throws IOException {
        if (value.isBlank()) {
            throw new IOException("blank input");
        }
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(value))) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        TextReader first = FunctionalMethodSignatureDemo::firstLine;
        TextReader upper = text -> text.toUpperCase(Locale.ROOT);
        Summary summary = (label, quantity) ->
                label + " x" + quantity;
        TextLength length = String::length;

        CheckedMapper<String, String, IOException> generic =
                FunctionalMethodSignatureDemo::firstLine;

        System.out.println("First: " + first.read("Java\nFunctional"));
        System.out.println("Upper: " + upper.read("Java"));
        System.out.println("Summary: " + summary.format("Book", 3));
        System.out.println("Length: " + length.length("Java"));
        System.out.println("Generic: " + generic.apply("One\nTwo"));

        try {
            first.read("  ");
        } catch (IOException e) {
            System.out.println("Error: " + e.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac FunctionalMethodSignatureDemo.java
java FunctionalMethodSignatureDemo
```

Output:

```text
First: Java
Upper: JAVA
Summary: Book x3
Length: 4
Generic: One
Error: blank input
```

**How to read the contracts and match the output:**

| Variable | Descriptor after type resolution | Implementation |
| --- | --- | --- |
| `first` | `(String) -> String throws IOException` | `FunctionalMethodSignatureDemo::firstLine` |
| `upper` | `(String) -> String throws IOException` | Lambda throwing no checked exceptions |
| `summary` | `(String,int) -> String` | Lambda taking two parameters |
| `length` | `(String) -> int` | Method reference `String::length` |
| `generic` | `(String) -> String throws IOException` | `CheckedMapper<String,String,IOException>` |

`firstLine` reads the first line from `StringReader` using `BufferedReader`. Because `readLine()` declares `throws IOException`, `firstLine` also declares `throws IOException`; the blank-input branch explicitly throws `IOException("blank input")`. The method reference `firstLine` matches the two functional interfaces that permit `IOException`. `main` declares `throws IOException` to allow successful calls without catching on each statement; the failing call is caught explicitly to print `Error: blank input`.

`String::length` takes `String` as the receiver and returns an `int`; it matches `TextLength`. `summary` takes two arguments and returns a `String`. The program shows that the **target type** of each variable governs the descriptor that the lambda/method reference must satisfy.

## 6. Inheriting Multiple Interfaces and Choosing the Descriptor

A functional interface does not have to *declare* only one method: it can inherit multiple abstract declarations that still represent the same method in SAM terms if the signatures satisfy override-equivalence rules and return-type conditions.

Example without exceptions:

```java
interface A {
    CharSequence name(String value);
}

interface B {
    String name(String value);
}

@FunctionalInterface
interface C extends A, B { }

C fn = value -> value.trim();
```

Because `String` is a subtype of `CharSequence`, the method returning `String` is compatible with the inherited contract; `C` has one functional method with descriptor taking `String` and returning `String`. Not every pair of return types is valid: if two return types cannot be reconciled under return-type-substitutability rules, the inheriting interface fails.

For **inherited `throws` clauses**, be especially careful. Do not assume you take the *union* of exceptions from all declarations and let the lambda throw all of them. The function type of the inheriting interface must obey the checked-exception constraints of the matching methods; allowed checked exceptions must be compatible with the contract of every method to be implemented. If the interface inherits declarations with conflicting checked exceptions, the descriptor's allowed checked-exception list may be **narrower** than each original declaration, or even allow no checked exceptions at all.

In API design, it is usually best to declare one interface with a clear descriptor and keep `throws` as narrow as reasonable. Do not build a complex interface hierarchy just to “combine” exception groups.

### Generic Descriptors and Lambda Limitations

Declarations with type parameters **at the interface level** are usually friendly to lambdas:

```java
@FunctionalInterface
interface Identity<T> {
    T apply(T value);
}

Identity<String> normalize = String::trim;
```

An interface can have a generic functional method at the **method level**, but a function descriptor carrying its own method-level type parameter has limitations when used as a target for lambda expressions. Do not assume every generic SAM declaration can be implemented with a lambda using the familiar syntax. When lambdas are needed, putting generics at the interface level like `Identity<T>` or `Function<T,R>` is usually simpler and easier to use.

## 7. Choosing the Right Standard Functional Interface

In `java.util.function`:

| Interface | Function descriptor | Used when |
| --- | --- | --- |
| `Runnable` (`java.lang`) | `() -> void` | Running a task with no result |
| `Supplier<T>` | `() -> T` | Providing or obtaining a value |
| `Consumer<T>` | `(T) -> void` | Performing an action with one value |
| `BiConsumer<T,U>` | `(T,U) -> void` | Action with two values |
| `Predicate<T>` | `(T) -> boolean` | Testing a condition |
| `Function<T,R>` | `(T) -> R` | Transforming one value |
| `BiFunction<T,U,R>` | `(T,U) -> R` | Transforming two values |
| `UnaryOperator<T>` | `(T) -> T` | Transforming where input and output types are the same |
| `BinaryOperator<T>` | `(T,T) -> T` | Combining two values of the same type |
| `ToIntFunction<T>` | `(T) -> int` | Computing an `int` without boxing |

`Runnable` is a historical functional interface in `java.lang`, not part of `java.util.function`. The common interfaces above generally do not declare checked exceptions on their functional methods; if an API needs to allow checked exceptions to escape, consider a dedicated contract.

A few short examples:

```java
java.util.function.Predicate<String> hasText = s -> !s.isBlank();
java.util.function.Function<String, Integer> size = String::length;
java.util.function.BiFunction<String, Integer, String> repeat =
        String::repeat;
java.util.function.ToIntFunction<String> primitiveLength =
        String::length;
```

The method reference `String::repeat` in the `BiFunction` example takes the `String` receiver as the first parameter and `int` as the second parameter; `String::length` fits returning `Integer` via boxing or `int` directly. It is the same Java syntax, but the target descriptor dictates how type checking works.

## 8. Common Compile Errors and How to Fix Them

**Wrong parameter count.** `Function<String,Integer>` takes one `String`; `(a,b) -> ...` does not fit. Switch to `BiFunction` when two inputs are genuinely needed, or group parameters into a meaningful value object.

**Wrong return type.** `Predicate<String> predicate = s -> s.length();` fails because `int` does not convert to `boolean` in Java. Write `s -> s.length() > 0`. With a `void` descriptor, do not write `return expression;` inside a lambda block.

**Missing `return` path.** A lambda block for `Function` must return a value along every normal completion path. Add `return` or extract conditions into a named method for easier review.

**Wrong checked exception.** `Function<Path,String>` does not allow a lambda to throw `IOException` out. Choose a checked functional interface, handle it inside the lambda, or redesign the I/O boundary. `main throws Exception` does not fix a descriptor mismatch.

**Confusing parameter order in method references.** `String::repeat` has a `String` receiver and an `int` parameter, so it does not fit `Function<Integer,String>`. Check types after binding the receiver; use an explicit lambda if a method reference is hard to read.

**Overly broad `throws Exception`.** Declaring `throws Exception` on every functional interface forces callers to handle more errors than necessary, obscuring the real contract. Prefer specific exceptions or purposefully designed exception hierarchies.

**Mixing up generic and primitive types.** `Function<String,Integer>` returns wrapper `Integer`, while `ToIntFunction<String>` returns primitive `int`. Boxing is often convenient, but in high-performance loops it can add unnecessary overhead.

**Using one interface for too many meanings.** Two operations with the same `(String) -> String` descriptor do not necessarily share the same business purpose. Interface/method names should reflect their role, especially in public APIs or when checked exceptions are involved.

## 9. Practice Exercises

1. Given `@FunctionalInterface interface PriceRule { long apply(int quantity, long unitPrice); }`. Write a lambda computing the total without discount and state the function descriptor.
2. Write a `Predicate<String>` that takes a `String`, returns `true` if it starts with `"J"`, and state the return type.
3. With `Function<String,Integer>`, why does `s -> { if (s.isEmpty()) return 0; }` fail? Rewrite it so every path returns a result.
4. Suppose `static String fetch(String key) throws IOException`. Why can `Function<String,String>` not directly accept `App::fetch`? Design the corresponding `CheckedFunction<String,String>`.
5. Explain the difference between `Function<String,Integer> len = String::length` and `Supplier<Integer> len = "abc"::length`.
6. Predict the stdout of the complete example before running it, then change `upper` to `text -> text.trim()`: does changing the body alter the `throws IOException` function descriptor?

**Hints:**

- (1) `(quantity, unitPrice) -> quantity * unitPrice`; descriptor `(int,long) -> long`; if overflow detection is needed, use `Math.multiplyExact(unitPrice, quantity)`.
- (2) `s -> s.startsWith("J")`; return type `boolean`.
- (3) There is a path that does not return a value; add `return s.length();` after `if`.
- (4) `Function.apply` has no `throws IOException`; design `String apply(String key) throws IOException`.
- (5) The first is an unbound method reference taking one `String`; the second is receiver-bound and takes no parameters.
- (6) Output is as listed; replacing the body with a lambda throwing no checked exceptions remains compatible with `TextReader`, and the descriptor still declares `throws IOException`.

## 10. Self-Check Before Assigning a Lambda or Method Reference

Read the target type and ask in order:

1. **How many parameters?** What are the order and types of each parameter? Are there generics to substitute with concrete types?
2. **What does it return?** `void` or a value? Is there boxing, unboxing, widening, or a subtype return type to consider?
3. **Which checked exceptions can be thrown?** Does the body or referenced method throw an exception broader than the allowed list?
4. **Where will the caller handle errors?** If using an interface that allows checked exceptions, the call site needs `try/catch` or `throws`; if converting to unchecked, are the reason and error policy clear?
5. **Does the interface name express business meaning?** Choose a standard interface for general transformations, and a custom interface when a clearer contract is required.

**Conclusion:** A functional interface in Java has a contract defined by its **parameter types, return type, and `throws` clause**. Lambdas and method references can only be used when compatible with the function descriptor provided by the target type. Understanding these three components helps you read compile errors accurately, use generics/primitives appropriately, and handle checked exceptions deliberately.