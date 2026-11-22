# Zero-Parameter, Single-Parameter, and Multi-Parameter Lambdas in Java

A lambda expression is a concise syntax for providing the implementation of the **single abstract method** of a functional interface. The `->` arrow separates the **parameter list** and the **lambda body**:

```java
(parameters) -> expression
(parameters) -> { statements; }
```

These are two **general syntax patterns**, not two standalone Java programs to compile. A lambda requires a **target type** context; the compiler relies on that interface's functional method to check the number of parameters, parameter types, and return type.

Common forms include:
- **Zero parameters:** `() -> ...` used when the task takes no input data.
- **One parameter:** `x -> ...` or `(x) -> ...` when the compiler infers the type.
- **Multiple parameters:** `(a, b) -> ...`, `(a, b, c) -> ...`, requiring parentheses.

After this lesson, you will be able to write all three forms, understand how to use parentheses/explicit types/`var`, use expression bodies and block bodies, and check whether a lambda matches a functional interface.

## 1. Syntax rules table by parameter count

| Parameter count | Inferred-type form | Explicit-type form | Example functional interface |
| --- | --- | --- | --- |
| 0 | `() -> 42` | No parameters to annotate with types | `Supplier<Integer>` |
| 1 | `x -> x * 2` or `(x) -> x * 2` | `(Integer x) -> x * 2` | `Function<Integer,Integer>` |
| 2 | `(a, b) -> a + b` | `(int a, int b) -> a + b` | `IntBinaryOperator` |
| 3 | `(a, b, c) -> a + b + c` | `(int a, int b, int c) -> a + b + c` | Custom-defined interface |

**Mandatory rules:**

1. A **0-parameter** list must be written as `()`. The form `-> 42` is missing the parameter section and is invalid.
2. With **exactly 1 parameter**, parentheses can be omitted only when the parameter name has no explicit type and does not use `var`. Both `x -> x * 2` and `(x) -> x * 2` are valid.
3. With **2 or more parameters**, always enclose the entire list in parentheses: `(a, b) -> ...`. The form `a, b -> ...` is a syntax error.
4. When declaring types explicitly, you must declare a type for **every parameter**: `(String left, String right)`, not `(String left, right)`.
5. `var` can be used in a lambda parameter list starting from Java 11, but if used, **all parameters must use `var`**. Forms like `(var a, b)` or `(var a, int b)` are invalid.
6. A lambda can have either an **expression** body or a **block** body. The return rules must match the functional method.

The number of lambda parameters is different from the number of *generic type parameters* of the interface. For example, `Function<T,R>` has two type parameters `T` and `R`, but its functional method `R apply(T value)` takes only **one argument**.

## 2. Zero-parameter lambdas: `() -> ...`

The zero-parameter form is used when an operation needs no input. Two typical interfaces are:

- `Runnable` in `java.lang`: functional method `void run()` takes no arguments and returns no result.
- `Supplier<T>` in `java.util.function`: functional method `T get()` takes no arguments and returns a result of type `T`.

Illustrative example (placed inside a method, with `import java.util.function.Supplier;`):

```java
Runnable printHello = () -> System.out.println("Xin chào");
Supplier<Integer> answer = () -> 42;

printHello.run();
int value = answer.get();  // 42
```

**Creating a lambda does not immediately execute the lambda body.** `printHello` only executes when `run()` is called; `answer` produces a value when `get()` is called. Depending on the implementation, each call may repeat the work, because `Supplier` does not automatically cache results.

When the body consists of multiple statements, use a block:

```java
Supplier<String> code = () -> {
    String prefix = "ID-";
    return prefix + 100;
};
```

Here `get()` returns `"ID-100"`. For `Runnable`, an empty body `() -> { }` is also a valid lambda because `run()` returns `void`.

## 3. Single-parameter lambdas: `x -> ...`

The single-parameter form is common in Stream processing, condition checking, data transformation, and callbacks:

```java
Function<String, Integer> length = text -> text.length();
Predicate<Integer> positive = n -> n > 0;
Consumer<String> printer = text -> System.out.println(text);
```

This is a code snippet requiring the corresponding imports from `java.util.function`.

- `Function<String,Integer>` has functional method `Integer apply(String input)`, so the compiler infers `text` as `String`.
- `Predicate<Integer>` has `boolean test(Integer input)`, so `n > 0` produces a `boolean` result.
- `Consumer<String>` has `void accept(String input)`, so the lambda is used to perform an action without returning a result.

Valid and equivalent ways to write **one parameter**:

```java
Function<String, Integer> a = text -> text.length();
Function<String, Integer> b = (text) -> text.length();
Function<String, Integer> c = (String text) -> text.length();
Function<String, Integer> d = (var text) -> text.length();
```

This illustrative snippet requires Java 11+ (because of `var` in a lambda), and runs inside a method body when `import java.util.function.Function;` is present. With an explicit type `String` or `var`, parentheses are mandatory. `var` here is **static** type inference, not dynamic typing; the compiler still infers `text` as `String`.

Example with primitives:

```java
java.util.function.IntUnaryOperator doubling = n -> n * 2;
int result = doubling.applyAsInt(7); // 14
```

`IntUnaryOperator` takes and returns a primitive `int`, avoiding the boxing/unboxing of `Function<Integer,Integer>`.

## 4. Multi-parameter lambdas: `(a, b, ...) -> ...`

For two parameters, Java provides several standard interfaces:

```java
BiFunction<Integer, Integer, Integer> sum = (a, b) -> a + b;
BiPredicate<String, String> sameLength =
        (left, right) -> left.length() == right.length();
Comparator<String> byLength =
        (left, right) -> Integer.compare(left.length(), right.length());
```

The illustrative snippet requires `java.util.function.BiFunction`, `java.util.function.BiPredicate`, and `java.util.Comparator`.

- `BiFunction<T,U,R>` takes two values and returns `R`.
- `BiPredicate<T,U>` takes two values and returns `boolean`.
- `Comparator<T>` takes two values of the same type and returns a negative/0/positive `int` to describe ordering.

Examples with explicit types:

```java
BiFunction<String, String, String> join =
        (String first, String second) -> first + " " + second;

java.util.function.IntBinaryOperator max =
        (int x, int y) -> x >= y ? x : y;
```

An interface is allowed to have a functional method with **three or more parameters**. The JDK does not provide a general `TriFunction` in the `java.util.function` package, so if a problem needs this contract, you can define it yourself:

```java
@FunctionalInterface
interface TriFunction<A, B, C, R> {
    R apply(A first, B second, C third);
}
```

Then inside a method:

```java
TriFunction<Integer, Integer, Integer, Integer> sumThree =
        (a, b, c) -> a + b + c;
int total = sumThree.apply(1, 2, 3); // 6
```

The two snippets above are **related code fragments**: the interface is declared at the top level, and the assignment is placed inside a method. A functional interface still has only **one abstract method**, even if that method takes three arguments.

## 5. Complete program for 0, 1, and 2 parameters

Save as **`LambdaArityDemo.java`**:

```java
import java.util.Comparator;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

@FunctionalInterface
interface NameTag {
    String apply(String name, String topic);
}

public class LambdaArityDemo {
    public static void main(String[] args) {
        // 0 parameters: () parentheses are required.
        Runnable greeting = () -> System.out.println("Không tham số: xin chào");
        Supplier<Integer> answer = () -> 42;
        greeting.run();
        System.out.println("Giá trị: " + answer.get());

        // 1 parameter: parentheses can be omitted if the type is inferred.
        Predicate<String> hasText = text -> text != null && !text.isBlank();
        Function<String, Integer> length = (String text) -> text.length();
        System.out.println("Một tham số: " + hasText.test("Java"));
        System.out.println("Độ dài Lambda: " + length.apply("Lambda"));

        // 2 parameters: parentheses around the list are required.
        BiFunction<Integer, Integer, Integer> sum = (a, b) -> a + b;
        Comparator<String> byLength =
                (left, right) -> Integer.compare(left.length(), right.length());
        NameTag tag = (String name, String topic) -> name + " học " + topic;
        System.out.println("Tổng: " + sum.apply(3, 4));
        System.out.println("So sánh: " + byLength.compare("go", "hello"));
        System.out.println("Nhãn: " + tag.apply("Lan", "Java"));
    }
}
```

Using JDK 17 or later, in the directory containing the file:

```bash
javac -encoding UTF-8 LambdaArityDemo.java
java LambdaArityDemo
```

**Exact stdout:**

```text
Không tham số: xin chào
Giá trị: 42
Một tham số: true
Độ dài Lambda: 6
Tổng: 7
So sánh: -1
Nhãn: Lan học Java
```

`Runnable` is automatically imported from `java.lang`; no separate import is needed. `NameTag` is an interface in the same file without `public`, so it can be compiled alongside `public class LambdaArityDemo`. The entire example illustrates that the parameter count must match the target type's functional method, whether using type inference or writing types explicitly.

## 6. Expression body and block body

Parameter syntax and body syntax are two independent choices.

### 6.1. Expression body

```java
Function<Integer, Integer> square = n -> n * n;
Predicate<String> hasJ = text -> text.contains("J");
Consumer<String> print = text -> System.out.println(text);
```

These three lines are an illustrative snippet with imports `Function`, `Predicate`, `Consumer`. In the first two lines, the value of the expression becomes the functional method's result. The last line uses a `println` call compatible with a `void`-returning method. Do not use the `return` keyword in an expression body; for example, `n -> return n * n` is invalid syntax.

### 6.2. Block body

```java
Function<Integer, String> sign = n -> {
    if (n < 0) {
        return "âm";
    }
    if (n == 0) {
        return "không";
    }
    return "dương";
};

Consumer<String> log = value -> {
    System.out.println("Bắt đầu");
    System.out.println(value);
};
```

A block body requires `{ ... }`; when returning a value, use `return expression;` and ensure all paths that complete normally return a result. For a `void`-returning method, you must not use `return value;`; you can use `return;` to exit the lambda early.

| Target type | Valid example | Invalid example |
| --- | --- | --- |
| `Supplier<Integer>` | `() -> 42` or `() -> { return 42; }` | `() -> { System.out.println("x"); }` |
| `Runnable` | `() -> System.out.println("x")` or `() -> { }` | `() -> { return 42; }` |
| `Predicate<String>` | `s -> s.isBlank()` or `s -> { return s.isBlank(); }` | `s -> { System.out.println(s); }` |

A **statement expression** such as a method call can fit an expression body of a `void`-returning lambda; however, an expression that is just a numeric literal `42` cannot. Thus `Runnable r = () -> 42;` is **invalid**, even though Java allows ignoring the return value of certain methods called as statements.

## 7. Explicit parameter types and var since Java 11

Type inference relies on the functional interface:

```java
java.util.function.BiFunction<Integer, Integer, Integer> multiply =
        (x, y) -> x * y;
```

You can replace the parameter section with `(Integer x, Integer y)` or `(var x, var y)`. These forms have the same target type and same logic, but should not be written simultaneously in the same scope with the same variable name `multiply`.

**Invalid forms (intentionally fail to compile):**

```java
// INVALID: mixing var with an inferred-type parameter
(var x, y) -> x + y

// INVALID: mixing explicit type and inferred type
(Integer x, y) -> x + y

// INVALID: mixing var with an explicit type
(var x, Integer y) -> x + y

// INVALID: has a type but missing parentheses for one parameter
String s -> s.length()

// INVALID: two parameters but missing parentheses
x, y -> x + y
```

A lambda with inferred types can use short variable names when the context is clear; for longer business logic, use meaningful names like `candidate`, `left`, `right`. Declaring types explicitly is helpful when you need to clarify types or support annotations on parameters.

## 8. Java 17 program: var, block body, and captured variables

Save as **`LambdaBodyDemo.java`**:

```java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;

public class LambdaBodyDemo {
    public static void main(String[] args) {
        Function<Integer, Integer> square = n -> n * n;
        System.out.println("Bình phương: " + square.apply(5));

        Function<Integer, String> classify = n -> {
            if (n < 0) {
                return "âm";
            }
            if (n == 0) {
                return "không";
            }
            return "dương";
        };
        System.out.println("Phân loại: " + classify.apply(-1));

        Predicate<String> notNull = (var text) -> text != null;
        System.out.println("Không null: " + notNull.test("Java"));

        IntBinaryOperator max = (var x, var y) -> x >= y ? x : y;
        System.out.println("Lớn nhất: " + max.applyAsInt(5, 8));

        int bonus = 5; // effectively final
        IntUnaryOperator addBonus = n -> n + bonus;
        System.out.println("Cộng thêm: " + addBonus.applyAsInt(7));

        Consumer<String> print = text -> System.out.println("Nhận: " + text);
        print.accept("Lambda");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 LambdaBodyDemo.java
java LambdaBodyDemo
```

**Exact stdout:**

```text
Bình phương: 25
Phân loại: âm
Không null: true
Lớn nhất: 8
Cộng thêm: 12
Nhận: Lambda
```

`IntBinaryOperator` has functional method `int applyAsInt(int left, int right)`; the compiler infers `var x` and `var y` as `int`. The local variable `bonus` referenced by the lambda must be `final` or **effectively final**, meaning it is not reassigned after initialization. A lambda can capture a mutable object, but that does not make the object immutable.

## 9. Target type and method calls

A lambda has no standalone type outside of context. It needs a matching functional interface in an assignment, argument passing, or cast:

```java
java.util.function.Supplier<Integer> makeAnswer = () -> 42;
Runnable print = () -> System.out.println("OK");
```

These two lines are valid illustrations placed inside a method. The form `Runnable wrong = () -> 42;` is **invalid**, because `run()` does not accept a result and the literal `42` is not a valid statement expression.

When passing a lambda as an argument, the compiler infers the target type from the method receiving the argument:

```java
static void execute(Runnable action) {
    action.run();
}

// Inside a method:
execute(() -> System.out.println("Đang chạy"));
```

These are two code fragments: declaring `execute` in a class, then calling it in another method. If multiple overloads accept functional interfaces that are equally compatible, the compiler may report an **ambiguous method call**; use an explicit target type or an intentional cast instead of guessing that the compiler will always pick the desired overload.

If the functional method does not declare checked exceptions, the lambda also cannot let the corresponding checked exceptions escape unhandled. For example, `Runnable.run()` does not declare `IOException`, so when calling file APIs with checked exceptions inside a lambda, you need to handle them or choose an appropriate contract.

## 10. Scope, return, and common mistakes

1. **Duplicate parameter names:** `(x, x) -> x` is invalid syntax.
2. **Shadowing enclosing local variables:** if the method already has a local variable `count`, you cannot name a lambda parameter `count` in the same scope.
3. **Reassigned captured variable:** a lambda cannot reference a local variable that is not effectively final; compute the new value in another variable or adjust the design.
4. **Misunderstanding `return`:** `return` inside a lambda block body exits the lambda invocation, not the enclosing method.
5. **Confusing `this`:** inside a lambda in an instance method, `this` refers to the enclosing instance; it does not create its own `this` like an anonymous class.
6. **Forgetting to call the functional method:** `Function<String,Integer> f = s -> s.length();` uses `f.apply("abc")`, not `f("abc")`.
7. **Wrong parentheses:** with two parameters write `(a,b)`, with one typed parameter you must write `(String s)`, with 0 parameters write `()`.
8. **Mixing declaration styles:** `(var a, b)`, `(int a, b)`, `(var a, int b)` are all invalid.
9. **Confusing type parameters and parameter count:** `BiFunction<T,U,R>` has three generic arguments, but the lambda takes two arguments.
10. **Choosing the wrong body:** `n -> n + 1` is an expression body; `n -> { return n + 1; }` is a block body. Do not write `n -> { n + 1; }` for `Function<Integer,Integer>`.
11. **Incompatible return:** a `void`-returning method does not accept `return 5;`; a value-returning method needs a matching result branch.
12. **Swapping parameter order:** the compiler checks types according to the functional method's order; two parameters of the same type can pass compilation but cause business logic bugs if their roles are swapped.

## 11. Quick selection by problem

| Problem | Lambda form | Typical target type |
| --- | --- | --- |
| Run an action | `() -> doWork()` | `Runnable` |
| Defer creating a result | `() -> createValue()` | `Supplier<T>` |
| Transform one input | `value -> transform(value)` | `Function<T,R>` |
| Check a condition | `item -> item.isValid()` | `Predicate<T>` |
| Process a value without returning a result | `item -> print(item)` | `Consumer<T>` |
| Combine two inputs | `(a, b) -> combine(a,b)` | `BiFunction<T,U,R>` |
| Compare two values | `(a, b) -> compare(a,b)` | `Comparator<T>` |
| Take three inputs | `(a,b,c) -> calculate(a,b,c)` | Custom functional interface |

Names like `doWork`, `createValue`, `transform`, and similar in the table are **example names**; they must be defined in actual code. When a lambda only forwards to an existing method, sometimes a **method reference** such as `String::length` is clearer. Regardless of the syntax chosen, the target type and functional method still determine the contract.

## 12. Self-check

**Question 1.** Write a zero-parameter lambda returning the string `"ready"`:

```java
java.util.function.Supplier<String> ready = () -> "ready";
```

**Question 2.** Why can `Predicate<String> longName = name -> name.length() > 5;` omit parentheses?

Because there is only **one parameter with an inferred type**. If writing the type explicitly, you must write `(String name)`.

**Question 3.** How do you fix `a, b -> a + b`?

Write `(a, b) -> a + b` and place it in a context with a compatible two-parameter target type.

**Question 4.** How do the two lambdas `n -> n * 2` and `n -> { return n * 2; }` differ?

With a compatible target type like `Function<Integer,Integer>`, they produce the same result; one uses an expression body, and the other uses a block body with `return`.

**Question 5.** Is `(var x, int y) -> x + y` valid with a target type taking two `int`s?

**No.** You cannot mix `var` and an explicit type. Choose `(var x, var y)` or `(int x, int y)`.

**Question 6.** Can a functional interface with a method taking three parameters use a lambda?

**Yes.** "Functional" means having **one functional method**, and that method can take three or more arguments.

**Key takeaway:** When reading or writing Java lambdas, identify the **number of parameters**, **use of parentheses/types**, **expression body or block body**, and **signature of the functional method in the target type**. Satisfying all four ensures the lambda compiles and executes as intended.