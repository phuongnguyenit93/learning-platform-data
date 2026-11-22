# Lambda Syntax Structure in Java: Parameters, `->` Arrow, and Body

## 1. What is a lambda and how do you read its syntax?

A lambda expression is a way to provide the implementation of the **single abstract method** in a functional interface, usually more concisely than an anonymous class. A lambda has three components:

```text
(parameter_list) -> expression
(parameter_list) -> { statements }
```

- **Left of `->`** describes the number and names of parameters; you can declare types explicitly, let the compiler infer types, or use `var` (Java 11+).
- **The `->` arrow** separates the parameter list from the body. It is neither a comparison operator nor a `return` statement.
- **Right of `->`** is a single expression (*expression body*) or a block of statements (*block body*) enclosed in `{ ... }`.

For example, `(left, right) -> left + right` specifies the behavior of adding two arguments, but does not yet fully determine their types. Java needs a **target type** such as `BinaryOperator<Integer>` or `IntBinaryOperator` to check the parameter types and return type. A lambda does not have an independent type of its own that can be assigned unconditionally.

Learning objectives: write lambdas with 0, 1, or multiple parameters; know when parentheses are needed; understand type inference and `var`; distinguish expression bodies from block bodies, `return` syntax, how target types work, and how to fix common compilation errors.

## 2. Parameter list syntax

| Case | Syntax | Example target type | Meaning |
| --- | --- | --- | --- |
| No parameters | `() -> 42` | `Supplier<Integer>` | Requires empty parentheses |
| One parameter with inferred type | `s -> s.length()` | `Function<String, Integer>` | Parentheses can be omitted |
| One parameter with inferred type, with parentheses | `(s) -> s.length()` | `Function<String, Integer>` | Equivalent to the form above |
| One parameter with explicit type | `(String s) -> s.length()` | `Function<String, Integer>` | Parentheses are required |
| One parameter with `var` | `(var s) -> s.length()` | `Function<String, Integer>` | Java 11+, parentheses are required |
| Two parameters with inferred types | `(a, b) -> a + b` | `BinaryOperator<Integer>` | Two names separated by a comma |
| Two parameters with explicit types | `(int a, int b) -> a + b` | `IntBinaryOperator` | Each parameter has an explicit type |
| Two parameters using `var` | `(var a, var b) -> a + b` | `BinaryOperator<Integer>` | Each parameter uses `var` |

Rules to remember:

1. **No parameters:** always write `()`; you cannot write `-> 42`.
2. **One parameter with an inferred type and only a name:** you can write `x -> x + 1` or `(x) -> x + 1`.
3. **One parameter with an explicit type, `var`, `final`, or an annotation:** you must write parentheses `(...)`.
4. **Two or more parameters:** must always be placed inside `(...)`, separated by commas.
5. **Within a single parameter list, keep the declaration form consistent:** either all inferred, or all explicitly typed, or all using `var`.

Example when `java.util.function.Function` has been imported:

```java
Function<String, Integer> a = s -> s.length();
Function<String, Integer> b = (s) -> s.length();
Function<String, Integer> c = (String s) -> s.length();
Function<String, Integer> d = (var s) -> s.length();
```

These are illustrative statements to place inside a method body. All four `s` parameters have type `String` as determined by the target type. With `var`, Java still performs static type checking and relies on the target type; `var` does not turn a lambda into a dynamically typed function.

The following snippet is **intentionally invalid syntax** and should not be put into a runnable program:

```text
(int a, b) -> a + b        // Mixing explicit type declaration with an inferred parameter
(var a, b) -> a + b        // Mixing var with an inferred parameter
(var a, int b) -> a + b    // Mixing var with an explicit type
int x -> x * x            // Explicit type but missing parentheses
```

Rewrite them respectively as `(a, b)`, `(int a, int b)`, `(var a, var b)`, or `(int x)` according to the appropriate target type.

## 3. The `->` arrow and the role of the target type

Read `parameters -> body` as "take these parameters and execute that body." The `->` arrow **does not invoke the function immediately**. For example:

```java
Runnable task = () -> System.out.println("Chạy");
task.run();
```

The assignment creates a value that implements the `Runnable` interface. Only when `task.run()` is called does the body execute. This snippet is placed inside a Java method body.

A lambda needs a functional interface as its target type, for example:

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();
```

Here, the functional method `apply(String)` returns `Integer`; the compiler infers `text` as `String` and automatically boxes the `int` result of `length()`. The target type can also come from a method parameter, a return value, or a cast expression.

```java
static void execute(Runnable task) {
    task.run();
}

// Inside the body of another method:
execute(() -> System.out.println("done"));
```

The final call is valid because `execute` accepts `Runnable`. Meanwhile, the following snippet is intentionally invalid:

```text
var f = x -> x + 1;   // No target type to infer the functional type
```

Even though `var` can be used when declaring local variables, it cannot infer a functional interface on its own from a standalone lambda. The correct way, when you need to process integers:

```java
java.util.function.IntUnaryOperator f = x -> x + 1;
```

Be careful with **overloading**: two methods with the same name accepting different functional interfaces can make a lambda call ambiguous. You can declare a lambda variable with an explicit target type or cast it to the desired contract.

## 4. Expression body

The right side of `->` can be **a single expression**:

```java
Function<Integer, Integer> square = x -> x * x;
Predicate<String> nonEmpty = s -> !s.isEmpty();
Runnable greet = () -> System.out.println("Hi");
```

These examples require `import java.util.function.Function;` and `import java.util.function.Predicate;`, placed inside a method body. The `;` at the end of each variable declaration terminates the **outer Java statement**; it does not belong to the lambda expression itself.

When the functional method has a return value, the result of the expression is used as the lambda's result. Therefore:

```text
x -> x * x            // Valid for a target type that takes a number and returns a number
x -> return x * x;    // Invalid: return is a statement, not an expression
```

For a functional method returning `void` (such as `Runnable.run` or `Consumer.accept`), an expression body must be a **statement expression** (*statement expression*), such as a method call, assignment, increment/decrement, or object creation. `() -> System.out.println("Hi")` fits `Runnable`. However, `() -> 1 + 2` does not fit `Runnable`: pure addition is not a statement expression.

Do not confuse **the return value of an expression** with the `return` statement. The expression `n -> n * 2` does not need `return` because the body consists solely of an expression.

## 5. Block body

When you need multiple statements, local variable declarations, branching, or logging, put the body inside `{ ... }`:

```java
Function<Integer, Integer> square = x -> {
    int result = x * x;
    return result;
};

Consumer<String> print = text -> {
    System.out.println("Nhận: " + text);
};
```

These are illustrative statements inside a method with `Function` and `Consumer` imported.

- For a SAM **with a return type**, a block body must `return` a suitable value when completing normally. In an `if/else`, the corresponding paths must satisfy the return requirement.
- For a SAM returning **`void`**, a block body simply performs work; you can use `return;` to exit early, but you cannot use `return value;`.
- `x -> { x * 2; }` is invalid because the multiplication `x * 2` is not a statement expression, and it also lacks a result if the target type is `Function<Integer, Integer>`.
- `x -> { x.toString(); }` has a valid statement, but if the target type returns `String`, it is still invalid because **`return` is missing**.

Example comparing two equivalent forms:

```java
java.util.function.IntUnaryOperator one = n -> n * 2;
java.util.function.IntUnaryOperator two = n -> {
    return n * 2;
};
```

With `IntUnaryOperator`, both take `int`, return `int`, and produce the same result for the same input. The block form uses an explicit `return`; the expression form does not need it.

## 6. Complete Java 17 example: multiple parameter styles and bodies

Save the entire program to the file `LambdaStructureDemo.java`:

```java
import java.util.Locale;
import java.util.function.BinaryOperator;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaStructureDemo {
    @FunctionalInterface
    interface Formatter {
        String format(String left, String right);
    }

    public static void main(String[] args) {
        Runnable sayHello = () -> System.out.println("hello");

        Function<String, Integer> length = s -> s.length();
        Function<String, String> normalize =
                (String s) -> s.strip().toUpperCase(Locale.ROOT);

        BinaryOperator<Integer> add = (left, right) -> left + right;
        Predicate<String> longName = (var name) -> name.length() >= 4;

        Function<Integer, Integer> squared = n -> {
            int result = n * n;
            return result;
        };

        Consumer<String> printUpper = word -> {
            System.out.println(word.toUpperCase(Locale.ROOT));
        };

        Formatter join = (left, right) -> left + ":" + right;

        sayHello.run();
        System.out.println(length.apply("Java"));
        System.out.println(normalize.apply("  java "));
        System.out.println(add.apply(3, 4));
        System.out.println(longName.test("Lambda"));
        System.out.println(squared.apply(5));
        printUpper.accept("syntax");
        System.out.println(join.format("A", "B"));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac --release 17 -encoding UTF-8 LambdaStructureDemo.java
java LambdaStructureDemo
```

Exact output:

```text
hello
4
JAVA
7
true
25
SYNTAX
A:B
```

**Explanation:**

1. `()->...` of `Runnable` takes no parameters; `sayHello.run()` triggers the lambda.
2. `s -> s.length()` infers the `String` parameter, omits parentheses, and the `int` result is boxed to `Integer` for `Function`.
3. `(String s) -> ...` declares the type explicitly, requiring parentheses; `strip()` removes leading and trailing whitespace, and `toUpperCase(Locale.ROOT)` converts to uppercase.
4. `(left, right) -> ...` takes two `Integer` parameters, allowing addition via unboxing/boxing.
5. `(var name) -> ...` uses `var` syntax for the parameter (Java 11+), receives `String` from `Predicate<String>`, and produces a `boolean` result.
6. `n -> { ... return result; }` has a block body, a local variable, and an explicit `return`.
7. `word -> { System.out.println(...); }` is a `void`-returning block body of `Consumer`.
8. `Formatter` shows that lambdas also work with user-defined functional interfaces; `format(String, String)` is the interface's SAM.

The `->` arrow only creates behavior matching the target type. The transformations appearing in the body do not execute at the time `sayHello`, `length`, or `normalize` are declared.

## 7. Explicit types, `var`, `final`, and primitive parameters

Explicit type syntax is very useful when you want to show the reader the exact data types:

```java
java.util.function.IntBinaryOperator add =
        (int a, int b) -> a + b;
java.util.function.Function<String, Integer> count =
        (final String text) -> text.length();
```

These are illustrative statements that need to be placed inside a method. `IntBinaryOperator` has two `int` parameters and an `int` result, avoiding `Integer` boxing; `final String text` prevents reassigning the `text` parameter inside the body, though it does not mean every referenced object is immutable.

If using `var`, write `var` for **all** parameters, for example `(var left, var right) -> left + right`. In a lambda, `var` still relies on the target type, so it does not accept arbitrary values outside the contract.

An interface like `Function<String, Integer>` takes only **one** argument, so it cannot be used for the lambda `(a, b) -> a + b`. If you need two arguments, use `BiFunction<A, B, R>`, `BinaryOperator<T>`, or a custom functional interface.

## 8. Name scope and variables captured by a lambda

Lambda parameters are local variables within the lambda body. You cannot declare two parameters with the same name in one lambda. You should not try to redeclare a local variable that already exists in the enclosing method scope; a lambda does not open an independent scope for name shadowing the way some nested classes can.

A lambda can reference an outer local variable if that variable is `final` or **effectively final** (never reassigned after initialization). Standalone example below:

```java
import java.util.function.IntUnaryOperator;

public class LambdaCaptureDemo {
    public static void main(String[] args) {
        int increment = 3;
        IntUnaryOperator add = n -> n + increment;

        System.out.println(add.applyAsInt(4));
        System.out.println(add.applyAsInt(10));
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 LambdaCaptureDemo.java
java LambdaCaptureDemo
```

Result:

```text
7
13
```

If you add `increment = 4;` after declaring the variable in the method, the compiler will not accept the lambda capturing `increment` because the variable is no longer effectively final. This rule does not automatically make stateful objects immutable or thread-safe.

## 9. Nested lambdas

The expression body of a lambda can itself be another lambda if the target type requires returning a functional interface:

```java
java.util.function.Function<Integer, java.util.function.IntUnaryOperator>
        makeAdder = amount -> number -> amount + number;
```

This is an illustrative statement placed inside a method body. `makeAdder.apply(3)` creates an `IntUnaryOperator`, and then `applyAsInt(4)` returns `7`. The outer lambda takes `amount`, and its body is the inner lambda taking `number`; the `->` syntax is used twice because there are two functions. Do not confuse creating a new function with performing the addition.

## 10. Common syntax or type errors

| Incorrect code/assumption | Problem | Fix |
| --- | --- | --- |
| `() -> 42` assigned to `Runnable` | A numeric literal is not a statement expression for a `void` SAM | Use `Supplier<Integer>` or a body that performs a `void` operation |
| `x -> return x * x;` | `return` cannot be an expression body | `x -> x * x` or `x -> { return x * x; }` |
| `x -> { x * 2; }` assigned to `Function<Integer, Integer>` | Multiplication is not a statement; missing result | `x -> x * 2` |
| `x -> { x.toString(); }` assigned to `Function<Integer, String>` | Has a call but does not return a result | `x -> { return x.toString(); }` |
| `() -> { return 1; }` assigned to `Runnable` | SAM returns `void`, cannot `return` a value | Choose `Supplier<Integer>` if a result is needed |
| `(a, b) -> a + b` assigned to `Function<Integer, Integer>` | `Function` only takes one argument | Use `BiFunction<Integer, Integer, Integer>` or `BinaryOperator<Integer>` |
| `var inc = x -> x + 1;` | No target type for the lambda | `IntUnaryOperator inc = x -> x + 1;` |
| `(var a, int b) -> a + b` | Mixing parameter declaration styles | Use `(var a, var b)` or `(int a, int b)` |
| Block body has `if` but is missing `return` in one branch | Does not satisfy the required SAM result | Ensure every path that can complete normally returns an appropriate value |
| Assuming a lambda runs immediately upon assignment | Assignment only creates the behavior | Call `run`, `apply`, `test`, `accept`, or another API that executes it |

## 11. Self-practice

**Exercise 1:** Separate the three parts of `Predicate<String> p = s -> s.length() >= 3;`. Answer: parameter `s` is inferred as `String`, the `->` arrow separates the two sides, and the body `s.length() >= 3` returns `boolean`.

**Exercise 2:** Rewrite `IntUnaryOperator doubleValue = n -> n * 2;` using a block body. Answer:

```java
IntUnaryOperator doubleValue = n -> {
    return n * 2;
};
```

The statement is inside a method that has imported `java.util.function.IntUnaryOperator`.

**Exercise 3:** Choose a target type for `(a, b) -> a.concat(b)` when both arguments are `String`. Answer: `BinaryOperator<String>` (two inputs of the same type, returning the same type). `Function<String, String>` is unsuitable because it has one parameter.

**Exercise 4:** Fix `Function<String, Integer> size = (String s) -> { s.length(); };`. Answer: change it to `(String s) -> { return s.length(); }` or `s -> s.length()`.

**Exercise 5:** When is `(var a, var b) -> a + b` valid? Answer: in Java 11+ when there is a compatible target type, such as `BinaryOperator<Integer>`; all parameters use `var` and their types are statically inferred.

## 12. Key takeaways

- A lambda has the structure **parameters → `->` arrow → body**.
- With **0 parameters**, write `()`; with **1 inferred-type parameter**, parentheses can be omitted; with **multiple parameters**, `(...)` is required.
- When using explicit types, `final`, or `var`, keep the parentheses; do not mix parameter declaration styles in the same lambda.
- An **expression body** is a single expression without `return`; a **block body** has `{ ... }` and uses `return` according to the SAM's return type.
- `var` in lambda parameters does not mean dynamic typing; a lambda requires a functional interface **target type**.
- A lambda only executes when its functional method is called; avoid confusing the time behavior is created with the time it runs.

Reference documentation: [Java Language Specification, §15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27) and [§9.8 Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).