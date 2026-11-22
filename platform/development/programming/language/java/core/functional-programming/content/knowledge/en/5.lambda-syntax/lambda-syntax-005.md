# Declaring Lambda Parameter Types Explicitly or Letting Java Infer Them

## Objectives

Lambdas in Java allow declaring parameter types directly or letting the compiler infer them from the **target functional interface** (*target type*). Concise writing does not mean parameters have no types: Java still checks types at compile time.

After this lesson, you will be able to:

- Distinguish lambdas with **explicit parameter types**, **inferred types**, and using `var` for parameters.
- Identify valid syntax for lambdas with 0, 1, or multiple parameters.
- Explain how the compiler obtains types from assignments, method arguments, generic methods, and other target typing contexts.
- Choose an appropriate declaration style and handle errors caused by mixing styles or mismatched types.
- Understand variable name scoping, limitations of captured variables, and the impact of primitives, generics, and overloaded methods.
- Compile/run Java 17 examples and self-check common scenarios.

## 1. A lambda has no standalone type without a target context

Java is a statically typed language. A lambda expresses behavior, but to type-check that expression, the compiler needs to know the **functional interface** it will implement. An interface with a single abstract method (SAM) provides a function descriptor consisting of the parameter types and count, the result type, and the allowed checked exceptions.

Example:

```java
import java.util.function.Function;

Function<String, Integer> length = text -> text.length();
```

`Function<T,R>` has the method `R apply(T value)`. Substituting `T = String` and `R = Integer`, the descriptor of `length` is:

```text
(String) -> Integer
```

Therefore, in `text -> text.length()`, the parameter `text` is understood as `String`; `String.length()` returns `int` and can be boxed to `Integer`. The author does not need to write `String` in the lambda because the target type already provides the necessary information.

Importantly: **a lambda is a poly expression**. You cannot write:

```java
// Does not compile: a lambda needs a target functional interface.
var length = text -> text.length();
```

Even if you write `(String text) -> text.length()` in place of the lambda above, `var` for a **local variable** still does not provide a target functional interface on its own for a bare lambda. `var` used to infer local variable types and `var` used in a **lambda parameter list** are two syntaxes with different roles.

When placed in a context providing a valid target type, a lambda can implement an interface without creating an anonymous class:

```java
// Both expressions below can be assigned to the same target type.
Function<String, Integer> inferred = text -> text.length();
Function<String, Integer> explicit =
        (String text) -> text.length();
```

Both variables have the descriptor `(String) -> Integer`. Writing types explicitly changes the syntax and can improve clarity, but does not alter the contract of `Function.apply`.

## 2. Three ways to write lambda parameters

### 2.1. Letting Java infer types

```java
Function<String, Integer> length = text -> text.length();
Function<String, Integer> alsoLength = (text) -> text.length();

java.util.function.BiFunction<Integer, Integer, Integer> add =
        (a, b) -> a + b;
```

These are **implicitly typed lambda parameters**: Java takes each parameter's type from the function descriptor.

- With **one parameter** of inferred type, parentheses can be omitted: `text -> ...`.
- With **multiple parameters**, parentheses are required: `(a, b) -> ...`.
- With **no parameters**, `()` is required, for example `() -> "Hello"`.

The inferred types in the example are `String`, `String`, and two `Integer`s (unboxed when performing addition if needed). Just because a parameter is written concisely does not mean it has type `Object` or is a dynamic variable.

### 2.2. Writing parameter types explicitly

```java
Function<String, Integer> length = (String text) -> text.length();

java.util.function.BiFunction<Integer, Integer, Integer> add =
        (Integer a, Integer b) -> a + b;

java.util.function.IntBinaryOperator sum =
        (int a, int b) -> a + b;
```

These are **explicitly typed lambda parameters**. This style can be beneficial when a lambda is long or hard to read, when clarifying the difference between primitives and wrappers, or when analyzing compatibility with a target type.

When writing types, **parentheses must be used** even for a single parameter: `(String text) -> ...` is valid; `String text -> ...` is invalid. Each parameter is declared with a type compatible with the descriptor; you cannot arbitrarily change `String` to `Object` if the target requires `String`.

An incorrect case:

```java
// Does not compile: IntUnaryOperator has descriptor (int) -> int,
// but the lambda declares a String parameter.
java.util.function.IntUnaryOperator wrong =
        (String number) -> number.length();
```

Fix:

```java
java.util.function.IntUnaryOperator doubleValue =
        (int number) -> number * 2;
```

### 2.3. Using var for lambda parameters — Java 11+

Since Java 11, you can write:

```java
Function<String, Integer> length = (var text) -> text.length();

java.util.function.BiFunction<String, Integer, String> repeat =
        (var text, var times) -> text.repeat(times);
```

Here, `var` tells the compiler to **infer parameter types from the target descriptor**. In the example above, `text` has type `String` and `times` has type `Integer`. `var` does not mean "any type" or automatically convert parameters to `Object`.

`var` requires parentheses: `(var text) -> ...` is valid; `var text -> ...` is invalid. A notable benefit of the `var` form is that annotations can be attached to parameters while still letting the compiler infer types, provided the annotation has a suitable target:

```java
Function<String, String> normalize =
        (@Deprecated var text) -> text.trim();
```

`@Deprecated` here only illustrates annotation syntax on a parameter, not a typical business reason to mark a parameter deprecated. In real applications, use semantically appropriate annotations (such as nullability annotations supported by project tooling). There is no need for `var` when there is no clear reason; writing implicitly `text -> ...` is usually shorter.

## 3. Rule: all parameters must be consistent

Within the same lambda, Java does not allow arbitrarily mixing the three styles: implicit parameters, explicitly declared types, and `var`.

| Syntax | Result | Reason |
| --- | --- | --- |
| `(a, b) -> a + b` | Valid with an appropriate two-number target | Both parameters are implicit |
| `(int a, int b) -> a + b` | Valid with target `(int,int) -> int` | Both parameters are explicit |
| `(var a, var b) -> a + b` | Valid with an appropriate numeric target, Java 11+ | Both use `var` |
| `(int a, b) -> a + b` | Invalid | Mixing explicit type with implicit |
| `(var a, int b) -> a + b` | Invalid | Mixing `var` with explicit type |
| `(a, var b) -> a + b` | Invalid | Mixing implicit with `var` |
| `(String s) -> s.trim()` | Valid with target `(String) -> String` | Right type, has parentheses |
| `String s -> s.trim()` | Invalid | Missing parentheses when a type is declared |

Note that this table addresses **syntax** and compatibility with the stated target type. If the target differs or the operation makes no sense for the inferred types, a syntactically valid lambda may still fail to compile.

Practice: if a two-parameter lambda is written `(a, b)` and you want to clarify types, change **both** to `(String a, int b)` (when matching the descriptor), or `(var a, var b)` in Java 11+, instead of changing only one parameter.

## 4. How the target type provides parameter types

The compiler takes type information from the **context where the lambda is used**, not solely from the lambda body.

### 4.1. Assignment to a variable or field

```java
java.util.function.Predicate<String> nonBlank =
        s -> !s.isBlank();

java.util.function.Consumer<String> print =
        s -> System.out.println(s);
```

`Predicate<String>` gives `s` type `String` and requires returning `boolean`. `Consumer<String>` also gives the parameter type `String` but has descriptor `(String) -> void`; the body prints a message and returns no usable value.

### 4.2. Argument of a method

Suppose there is a method:

```java
static String applyTo(
        String input,
        java.util.function.UnaryOperator<String> action) {
    return action.apply(input);
}
```

When calling:

```java
String cleaned = applyTo("  Java  ", text -> text.trim());
```

The second parameter of `applyTo` has type `UnaryOperator<String>` with descriptor `(String) -> String`. Therefore, the lambda's `text` is inferred as `String` right inside the call expression. No intermediate lambda variable needs to be defined.

### 4.3. Generic APIs and type argument inference

```java
static <T, R> R transform(
        T input,
        java.util.function.Function<T, R> mapper) {
    return mapper.apply(input);
}
```

Calling:

```java
int size = transform("Lambda", value -> value.length());
```

The first argument `"Lambda"` helps determine `T` as `String`. The lambda's `Function<T,R>` target along with result type constraints help infer an appropriate `R`; `value` is understood as `String`, allowing `length()` to be called. Here the call returns an `Integer`/`int` value compatible with assigning to `int` via unboxing when needed.

Actual generic method type inference follows multiple constraints; do not view it as the compiler merely reading a single variable on the left. When the compiler lacks sufficient context, specify type arguments explicitly, create an intermediate variable with a target type, or write parameter types explicitly.

### 4.4. Stream context

```java
java.util.List<Integer> lengths =
        java.util.List.of("Java", "Go", "")
                .stream()
                .map(text -> text.length())
                .toList();
```

The Stream source has `String` elements, so `Stream.map(Function<? super String, ? extends R>)` gives the compiler the context that `text` is `String` and the expression returning `int` can become an `Integer` element. The result is `[4, 2, 0]`. Using Streams does not bypass type checking, even when writing lambdas without explicit types.

## 5. Implicitly typed parameters do not mean Object

Sometimes learners assume that writing `value -> value.length()` means `value` has an unknown type or defaults to `Object`. In reality, Java checks the called method based on the **type provided by the target**.

```java
java.util.function.Function<String, Integer> a =
        value -> value.length(); // valid

java.util.function.Function<Object, Integer> b =
        value -> value.length(); // does not compile: Object has no length()
```

The body is identical, but `value` in the first case is `String`, and in the second case is `Object`. The compiler does not guess `String` just because you wrote `length()`.

If you truly receive `Object` and need type-specific behavior, you must check and cast intentionally:

```java
java.util.function.Function<Object, Integer> describe = value -> {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
};
```

Pattern matching `instanceof` in the form `String text` works in Java 17. This is an input type design issue: declare the target `Function<String,Integer>` when the business logic truly only accepts strings, rather than weakening the contract to `Function<Object,Integer>`.

### Primitives, wrappers, and conversions

```java
java.util.function.IntUnaryOperator square = x -> x * x;
java.util.function.Function<Integer, Integer> boxed =
        x -> x * x;
```

In `IntUnaryOperator`, `x` is primitive `int`; in `Function<Integer,Integer>`, `x` is `Integer` unboxed during multiplication. Both can produce the same arithmetic result in normal cases, but their parameter types and boxing mechanisms differ. If `Integer` is `null`, unboxing can throw `NullPointerException`; primitives cannot represent `null`.

Explicit type declarations must match the descriptor:

```java
java.util.function.IntUnaryOperator a =
        (int x) -> x * x; // valid

java.util.function.Function<Integer, Integer> b =
        (Integer x) -> x * x; // valid

// Does not compile: target takes Integer, lambda declares int.
// The compiler does not treat (int x) and (Integer x) as the same
// explicit parameter declaration.
java.util.function.Function<Integer, Integer> wrong =
        (int x) -> x * x;
```

When optimizing primitive processing, choose `IntUnaryOperator`, `ToIntFunction<T>`, `IntPredicate`, or an appropriate primitive interface. Omitting explicit types does not eliminate boxing if the target is still `Function<Integer,Integer>`.

## 6. Method overloading and common inference pitfalls

Suppose a class has two overloads:

```java
@FunctionalInterface
interface TextToText {
    String map(String text);
}

@FunctionalInterface
interface TextToNumber {
    int map(String text);
}

static void execute(TextToText mapper) { /* ... */ }
static void execute(TextToNumber mapper) { /* ... */ }
```

When passing a lambda without a clear target, overload resolution may fail to select a single method:

```java
// May cause ambiguity in overload resolution.
execute(text -> text.length());
```

Do not expect adding `String` to the lambda parameter to resolve every ambiguity, because both descriptors take `String`. A clear and stable approach is to assign the lambda to a specific interface and then call the overload:

```java
TextToNumber lengthRule = text -> text.length();
execute(lengthRule);
```

For a similar lambda returning `String`, use `TextToText`. If an API has hard-to-distinguish overloads, you can use an explicit cast to the functional interface, though a named variable or an API with clearer method names is usually more readable.

Another mistake is thinking that writing `(String s) -> ...` always forces the compiler to pick whichever overload is desired. Parameter types are only **one part** of the descriptor; return types, body compatibility, and overall overload rules also play a role.

## 7. Parameter scope and captured variables

Lambda parameter names must be valid variable names; they cannot have the same name as a local variable already declared in the same enclosing scope under Java's rules.

```java
String text = "outside";

// Does not compile because the lambda parameter duplicates the local variable text.
java.util.function.Function<String, String> bad =
        text -> text.trim();
```

The fix is to rename the parameter:

```java
String text = "outside";
java.util.function.Function<String, String> good =
        value -> value.trim();
```

Name parameters `value`, `item`, `number` according to the data's meaning. Writing explicit types does not allow bypassing scoping rules.

A lambda can also **capture** a local variable from an outer scope when that variable is `final` or *effectively final*, meaning it is never reassigned after initialization:

```java
String prefix = "ID-";
java.util.function.Function<Integer, String> makeId =
        number -> prefix + number;

System.out.println(makeId.apply(7)); // ID-7
```

If you later assign `prefix = "NEW-"` in the same method, the compiler rejects the lambda capturing `prefix` because the variable is no longer effectively final. This rule applies whether the lambda parameter is written `number`, `(Integer number)`, or `(var number)`.

**Effectively final does not mean immutable data.** If you capture an `ArrayList` and add elements to it, the list reference may not change, but its contents do; this also creates side effects and may not be thread-safe in parallel execution. Type inference and immutability are two separate topics.

## 8. Complete Java 17 example

The following program produces the same result with all three parameter declaration styles of `Function<String,Integer>`. It also demonstrates two-parameter lambdas, target typing via a method accepting a function, generic methods, Streams, and a `void`-returning interface.

Create the file **`LambdaParameterTypesDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.UnaryOperator;

public class LambdaParameterTypesDemo {
    @FunctionalInterface
    interface Formatter {
        String repeat(String text, int times);
    }

    static String applyTo(String value, UnaryOperator<String> action) {
        return action.apply(value);
    }

    static <T, R> R transform(T input, Function<T, R> action) {
        return action.apply(input);
    }

    public static void main(String[] args) {
        Function<String, Integer> inferred = text -> text.length();
        Function<String, Integer> explicit =
                (String text) -> text.length();
        Function<String, Integer> withVar =
                (var text) -> text.length();

        Formatter repetition =
                (String text, int count) -> text.repeat(count);
        BiFunction<String, Integer, String> upper =
                (text, times) ->
                        text.toUpperCase(Locale.ROOT).repeat(times);

        Predicate<String> nonBlank = text -> !text.isBlank();
        Consumer<String> show = (String text) ->
                System.out.println("Consumer: " + text);

        List<Integer> lengths = List.of("Java", "Go", "")
                .stream()
                .map(s -> s.length())
                .toList();

        String trimmed = applyTo("  Java  ", value -> value.trim());
        int genericSize = transform("Lambda", String::length);

        System.out.println("Suy luận: " + inferred.apply("Java"));
        System.out.println("Tường minh: " + explicit.apply("Java"));
        System.out.println("var: " + withVar.apply("Java"));
        System.out.println("Hai tham số: " + repetition.repeat("Hi", 2));
        System.out.println("BiFunction: " + upper.apply("java", 2));
        System.out.println("Predicate: " + nonBlank.test(""));
        System.out.println("Stream: " + lengths);
        System.out.println("Từ lời gọi: " + trimmed);
        System.out.println("Generic: " + genericSize);
        show.accept("OK");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LambdaParameterTypesDemo.java
java LambdaParameterTypesDemo
```

**Output:**

```text
Suy luận: 4
Tường minh: 4
var: 4
Hai tham số: HiHi
BiFunction: JAVAJAVA
Predicate: false
Stream: [4, 2, 0]
Từ lời gọi: Java
Generic: 6
Consumer: OK
```

**Why is the output like this?**

- `inferred`, `explicit`, and `withVar` all implement `Function<String,Integer>`, so all take `String` and return the length as `Integer`. `"Java".length()` is `4`.
- `Formatter.repeat` takes `String` and `int`. The parameter pair is declared explicitly, and `"Hi".repeat(2)` returns `"HiHi"`.
- `BiFunction` takes `String` and `Integer`; `"java"` becomes `"JAVA"` using `Locale.ROOT` and repeats twice, yielding `"JAVAJAVA"`.
- `Predicate<String>` has result type `boolean`; an empty string does not satisfy `!text.isBlank()`, so it prints `false`.
- The Stream from three strings produces lengths `4`, `2`, `0`; `toList()` returns a list in encounter order in this sequential pipeline.
- `applyTo` declares parameter `UnaryOperator<String>`, so the lambda `value -> value.trim()` infers `value` as `String`; the result is `"Java"`.
- `transform` uses generics `T,R`; with `"Lambda"` and `String::length`, `genericSize` is `6`.
- `Consumer<String>` returns no result, only printing `Consumer: OK`.

All lambdas in the program have an **explicit target type in the appropriate position**; inference for each lambda relies on the API contract, even when generic types are only determined during call checking.

## 9. How to read compiler errors and fix the right issue

**Parenthesis syntax error.** Writing `String text -> text.trim()` causes a parser error; fix to `(String text) -> text.trim()` or `text -> text.trim()`.

**Mixing types with `var` or implicit types.** `(String text, count)` and `(var text, int count)` are invalid; fix consistently to one of the three styles `(text, count)`, `(String text, int count)`, or `(var text, var count)`.

**Wrong parameter type compared to descriptor.** `IntUnaryOperator op = (String x) -> x.length()` is invalid because the target takes `int`; change to `(int x) -> x * 2` or choose `Function<String,Integer>` according to the goal.

**Assuming the compiler infers from calls in the body.** `Function<Object,Integer> f = x -> x.length()` does not compile; `Object` has no `length()` method. Fix the target type to `Function<String,Integer>` if the business logic only accepts strings.

**No target type.** `var fn = x -> x + 1` is invalid because the compiler does not yet know the target interface. Declare `IntUnaryOperator fn = x -> x + 1` or create a custom interface when needed.

**Wrong parameter count.** `BiFunction<String,Integer,String>` requires two parameters; the lambda `text -> text` has only one. Use `(text, times) -> text.repeat(times)`.

**Wrong result type.** `Predicate<String> p = s -> s.length()` is invalid because the descriptor requires `boolean`. Fix to `s -> s.length() > 0`; this is a result type error, even though the parameter was inferred correctly.

**Reassigned captured variable.** If a lambda uses `prefix` from an outer scope and the program later modifies `prefix`, the compiler disallows capturing it. Use a local variable that is not reassigned, or if mutable state is genuinely needed, design an explicit state-holding object.

**Checked exception.** `Function<Path,String>` does not declare `throws IOException` in `apply`; whether the lambda writes parameter types explicitly or implicitly, it cannot throw `IOException` out without handling it. Catch/convert the exception intentionally or use a custom functional interface with `throws`. Changing `path -> ...` to `(Path path) -> ...` does not solve this issue.

**Hard-to-resolve method overloads.** Assign the lambda to a variable with a specific interface type, or adjust the API design so callers see a clear target type. Do not rely entirely on inference when multiple overloads have very similar contracts.

## 10. When to be explicit and when to let Java infer?

| Situation | Suggestion | Reason |
| --- | --- | --- |
| `list.stream().map(item -> item.name())`, type clear from source | Implicit inference | Less repetition, still type-checked |
| Long two-parameter lambda, types easy to confuse | Consider explicit | Helps readers quickly understand order and data types |
| Target is a primitive functional interface | Either inferred or explicit works | Most important is choosing the right interface to avoid unintended boxing |
| Want to attach an annotation to a lambda parameter while inferring | Use `(var x)`, Java 11+ | Supports annotations on parameters with inference syntax |
| Overloads/generics make the target unclear | Create an intermediate variable with a clear type or adjust the API | Makes the target type more transparent |
| Fixing checked exception, result type, or capture errors | Fix the corresponding contract/logic | Merely adding parameter type names will not solve the error |

Practical principle: **let Java infer when the context already makes the type clear; write explicitly when it clarifies the contract or serves a specific syntactic need**. There is no need to force the entire project into a single presentation style, but follow a shared convention for readability.

## 11. Self-check exercises

1. Given `Function<String,Integer> f = text -> text.length();`. What is the actual type of `text`, even though it is not written in the lambda? Rewrite the same logic using explicit parameters and `var`.
2. Given `BiFunction<String,Integer,String> f`. Write a lambda that repeats a string `n` times using all three parameter declaration styles.
3. In `Function<Object,Integer> f = x -> x.length();`, why does the compiler report an error? Should you cast `x` to `String` inside the body or fix the target interface?
4. Classify the syntax of `(x, y) -> x + y`, `(int x, y) -> x + y`, `(var x, var y) -> x + y`, `(x, var y) -> x + y`. With a compatible target, which expressions are valid?
5. Why does `var f = (String s) -> s.trim();` not compile? How does local-variable `var` differ from `(var s)` in a lambda?
6. A method takes `UnaryOperator<String>`. How does the compiler know the type of parameter `s` in the call `process(s -> s.trim())`?
7. Given `String prefix = "ID-"; Function<Integer,String> f = n -> prefix + n;`. What happens if `prefix` is reassigned right afterward? Why?
8. In the runnable example, try rewriting `Formatter repetition` as `(text, count) -> text.repeat(count)`. Predict whether the result changes.

**Suggested answers:** (1) `String`; `(String text) -> text.length()`; `(var text) -> text.length()`. (2) `(s,n) -> s.repeat(n)`, `(String s,Integer n) -> s.repeat(n)`, `(var s,var n) -> s.repeat(n)`. (3) `Object` has no `length()`; fix the target to `Function<String,Integer>` if the actual input must be a String. (4) Valid: the first form and the form using two `var`s; the two mixed forms are invalid. (5) A lambda needs a target functional interface; `var` on the parameter does not replace the target. (6) From `UnaryOperator<String>`, which has descriptor `(String)->String`. (7) Not effectively final error. (8) Does not change because the target type and logic remain the same.

## Conclusion

In Java, declaring lambda parameter types **explicitly** (`(String text)`), **implicitly** (`text`), or using **`var`** (`(var text)`) must all be compatible with the same target functional interface. The compiler infers based on the target typing context, not by guessing types from the lambda syntax in isolation. Mastering parenthesis rules, consistency when declaring multiple parameters, and generic/primitive contracts helps write concise yet type-safe lambdas.