# Lambdas Require a Functional Interface Target Type

## Objectives

A lambda expression in Java represents a piece of behavior that can be passed around, but **a lambda expression does not have a standalone class or interface type of its own**. To compile, Java requires a **target type** that is a suitable functional interface. The compiler relies on the target type to determine the number of parameters, parameter types, return type, and allowed exceptions of the lambda.

After this lesson, you will:

- Recognize a functional interface and the **function descriptor** of its single abstract method (SAM).
- Understand why `s -> s.length()` cannot stand alone or be assigned directly to `Object`, yet can be assigned to `Function<String,Integer>`.
- Identify the target type across assignments, method arguments, `return` statements, casts, and other contexts.
- Explain the role of generics and how lambdas participate in type inference when using Streams or other APIs.
- Distinguish target typing from the type of a `var` variable, and distinguish errors involving parameters, return values, and checked exceptions.
- Compile and run Java 17 examples, and independently determine target types in new scenarios.

## 1. A Functional Interface Is the Type Contract of a Lambda

A **functional interface** is an interface with exactly one abstract method according to Java's SAM rules. The `@FunctionalInterface` annotation helps the compiler check this condition, though it is not required for an interface to qualify. `default` and `static` methods do not count as abstract methods. Abstract methods corresponding to `public` methods of `Object` also do not turn an interface into one with multiple SAMs.

For example:

```java
@FunctionalInterface
interface TextRule {
    boolean matches(String text);

    default TextRule negateRule() {
        return value -> !matches(value);
    }
}
```

Here, `matches` is the single functional method. It defines the **function descriptor**:

```text
(String) -> boolean
```

This means an implementation must accept exactly one `String` and produce a `boolean` result; for example:

```java
TextRule nonBlank = text -> !text.isBlank();
```

When assigning the lambda to `TextRule`, the compiler checks the body against `TextRule`'s descriptor. The lambda is converted into an object that can be invoked via the `matches` method:

```java
boolean ok = nonBlank.matches("Java"); // true
```

A lambda may be implemented at runtime using the JVM's own mechanism; you should not assume it is equivalent to a fixed anonymous class in terms of identity or structure. What matters in design is the **functional interface contract**.

In the standard library, common targets include:

| Interface | SAM Method | Function Descriptor |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | `(T) -> boolean` |
| `Function<T,R>` | `R apply(T value)` | `(T) -> R` |
| `Consumer<T>` | `void accept(T value)` | `(T) -> void` |
| `Supplier<T>` | `T get()` | `() -> T` |
| `UnaryOperator<T>` | `T apply(T value)` | `(T) -> T` |
| `BiFunction<T,U,R>` | `R apply(T a,U b)` | `(T,U) -> R` |
| `Runnable` | `void run()` | `() -> void` |
| `Callable<T>` | `T call() throws Exception` | `() -> T throws Exception` |

`Runnable` belongs to `java.lang`, `Callable` belongs to `java.util.concurrent`, while `Predicate`, `Function`, `Supplier`, `Consumer`, and their variants belong to `java.util.function`. There are many other SAM types; what matters is the **number and types of parameters, return value, and exceptions**, rather than just the interface name.

## 2. Why Does a Lambda Need a Target Type?

Consider:

```java
// Invalid: no target type for inference.
var f = text -> text.length();
```

`var` can infer the type of a local variable from an initializer that has a well-defined type, but **it cannot infer a functional interface on its own for a standalone lambda**. Changing it to `(String text) -> text.length()` still does not make `var f = ...` valid: even when parameter types are declared, a lambda still needs a concrete functional interface target.

Similarly:

```java
// Invalid: Object is not a functional interface.
Object f = text -> text.length();
```

`Object` is a common superclass, but it has no SAM to indicate which method the lambda implements. Java also does not allow writing `(text -> text.length()).toString()` as if a lambda were a value that already has an independent type.

The right way is to provide a target type:

```java
java.util.function.Function<String,Integer> length =
        text -> text.length();

int size = length.apply("Java"); // 4
```

Java substitutes `T = String` and `R = Integer` in `Function<T,R>`, so the concrete descriptor is `(String) -> Integer`. The lambda receives `text` of type `String` (allowing `length()` to be called), and the primitive `int` result can be boxed to `Integer`.

Writing the parameter type explicitly is also valid:

```java
java.util.function.Function<String,Integer> length =
        (String text) -> text.length();
```

Both forms have the same target. This is called **target typing**: type-checking an expression based on the context that expects a specific type, rather than trying to infer a standalone type from the expression before knowing where it is used.

## 3. Poly Expressions and Contexts That Provide a Target Type

A lambda is a kind of **poly expression** in Java. When placed in a position that supports target typing, it can be checked against an expected functional interface.

### 3.1. Assignment to a Variable or Field

```java
java.util.function.Predicate<String> startsWithJ =
        text -> text.startsWith("J");

java.util.function.Function<String,Integer> size =
        text -> text.length();

java.util.function.Supplier<String> greeting =
        () -> "Xin chào";
```

Each type on the left-hand side gives the compiler a different descriptor. `startsWithJ` must return `boolean`; `size` must return `Integer`; `greeting` takes no parameters and returns `String`. The same `->` arrow syntax is used, yet the contracts are completely different.

In the case of a class field:

```java
class PriceService {
    private final java.util.function.IntUnaryOperator tax =
            amount -> amount + 10;
}
```

The field type `IntUnaryOperator` is the target `(int) -> int`. Making the field `final` does not change the source of type inference; `final` here only restricts reassigning the field.

### 3.2. Arguments Passed to a Method

Consider the API:

```java
static String decorate(
        String text,
        java.util.function.UnaryOperator<String> action) {
    return "[" + action.apply(text) + "]";
}
```

When called:

```java
String result = decorate("java", s -> s.toUpperCase());
```

The type of the second parameter is `UnaryOperator<String>`, a subtype of `Function<String,String>`. The descriptor `(String) -> String` tells the compiler that `s` is a `String`, even when the lambda is not stored in a separate variable. The result here is `"[JAVA]"`.

**There is no need to write `(String s)` just so the compiler can find the target**, because the signature of `decorate` already provides that target.

### 3.3. Return Value from a Method

```java
static java.util.function.Supplier<String> greetingFactory() {
    return () -> "Xin chào";
}
```

The method declares a return type of `Supplier<String>`, so the lambda expression in `return` receives the descriptor `() -> String`. The caller receives a `Supplier` and only executes the body when calling `get()`:

```java
String message = greetingFactory().get();
```

Placing a lambda in `return` does not turn the lambda itself into a `String` value; it returns **an object implementing the functional interface**, after which `get()` is called to obtain the string.

### 3.4. Casts and Contexts with an Explicit Target

Sometimes you need to specify the functional interface in a cast expression:

```java
Object value = (java.util.function.Function<String,Integer>)
        text -> text.length();
```

The cast provides the target `Function<String,Integer>` for the lambda; the result of the cast expression can then be assigned to `Object`. This is completely different from `Object value = text -> text.length()`, which is invalid.

You can also assign through a suitable intersection type, for instance when a lambda value must simultaneously satisfy a functional interface and a marker interface:

```java
Runnable serializableTask =
        (Runnable & java.io.Serializable) () -> {};
```

This example has a target intersection consisting of `Runnable` (with SAM `run()`) and the marker interface `Serializable` (with no abstract methods). However, **being serializable at the type level does not automatically guarantee a safe long-term serialization design for lambdas**; only use this when specifically required and when you understand the risks of implementation changes.

### 3.5. Conditional Expressions

The branches of a conditional expression can receive a target type from the surrounding context:

```java
boolean excited = true;
java.util.function.Supplier<String> message =
        excited ? () -> "Wow!" : () -> "Hello";
```

Here both lambdas receive the target `Supplier<String>` through the assignment context, so both have the descriptor `() -> String`. If you omit the target and ask the compiler to infer a standalone type from the two lambdas, there may not be enough information; when needed, declare an intermediate variable with an explicit functional interface.

## 4. The Target Type Guides Both Parameter Types and Return Type

A lambda with a similar-looking body can be valid with different targets, as long as it matches the descriptor.

```java
java.util.function.Predicate<String> hasFour =
        text -> text.length() >= 4;

java.util.function.Function<String,Boolean> boxedHasFour =
        text -> text.length() >= 4;
```

Same body, but one target returns a primitive `boolean` and the other returns the wrapper `Boolean`. The compiler can perform boxing when checking return-type compatibility.

On the other hand:

```java
// Invalid: Function<Object,Integer> gives text the type Object,
// and Object has no length() method.
java.util.function.Function<Object,Integer> wrong =
        text -> text.length();
```

Naming the parameter `text` does not make the compiler treat it as a `String`. The target gives it the type `Object`, so the body is rejected.

You can write explicit parameter types, but they must match the function descriptor:

```java
// Valid.
java.util.function.IntUnaryOperator twice =
        (int value) -> value * 2;

// Invalid: target expects int, lambda explicitly declares String.
java.util.function.IntUnaryOperator wrong =
        (String value) -> value.length();
```

The target also determines the return type. For example:

```java
// Invalid: Predicate<String> requires boolean, not int.
java.util.function.Predicate<String> invalid =
        text -> text.length();

// Valid.
java.util.function.Predicate<String> valid =
        text -> text.length() > 0;
```

You cannot look only at the parameters to decide whether a lambda is compatible. You must check **the entire function descriptor**.

### Value-Compatible and Void-Compatible

An expression body that is a *statement expression*, such as a method invocation, can be compatible with a `void`-returning context when the result value is discarded:

```java
java.util.function.Function<String,Integer> getLength =
        text -> text.length();

java.util.function.Consumer<String> ignoreLength =
        text -> text.length();
```

Both examples **are valid**: the call `text.length()` is a statement expression, so with `Consumer` the call can be executed and its result discarded. However, if the application semantics require keeping the length, you should use `Function` or `ToIntFunction` and avoid `Consumer`, which discards a useful value.

Conversely, when a lambda is written with a block body, the rules for `return` become clearer:

```java
java.util.function.Function<String,Integer> length = text -> {
    return text.length();
};

java.util.function.Consumer<String> print = text -> {
    System.out.println(text);
};
```

If a block intended for `Function` has a path that completes normally without returning a value, it will fail to compile. If a block intended for `Consumer` uses `return text.length();`, it is incompatible with the `void` return type.

## 5. Target Type and Lambda Parameter Syntax

Once the target is known, there are three ways to declare parameters:

```java
java.util.function.Function<String,Integer> inferred =
        text -> text.length();

java.util.function.Function<String,Integer> explicit =
        (String text) -> text.length();

java.util.function.Function<String,Integer> usingVar =
        (var text) -> text.length();
```

With the target `Function<String,Integer>`, all three receive a `String` and produce the same result. The syntax using `var` in lambda parameters has been available since Java 11. It is **different** from `var fn = text -> text.length()`, where `var` is used in a local variable declaration and does not provide a target.

Key rules:

- A lambda with no parameters uses `() -> expression`.
- A single implicitly typed parameter can be written `text -> expression` or `(text) -> expression`.
- A single parameter with an **explicit type** or `var` requires parentheses: `(String text)`, `(var text)`.
- Two or more parameters always require parentheses, for example `(a,b) -> a + b`.
- Do not mix implicit types, explicit types, and `var` in the same parameter list: `(var a, int b)` and `(String a, b)` are both invalid.
- An explicitly declared type must be compatible with the descriptor; `(Integer x)` is not treated as identical to `(int x)` in a lambda parameter declaration.

For example:

```java
@FunctionalInterface
interface Formatter {
    String format(String text, int times);
}

Formatter repeat = (text, times) -> text.repeat(times);
Formatter same = (String text, int times) -> text.repeat(times);
Formatter alsoSame = (var text, var times) -> text.repeat(times);
```

All three use the descriptor `(String,int) -> String`. They do not change the interface contract, only how the parameters are written.

## 6. How Do Generic Methods and Streams Provide a Target?

When a generic API accepts a function, the lambda's target type is determined from the type constraints involving the entire call.

```java
static <T,R> R convert(
        T value,
        java.util.function.Function<T,R> mapper) {
    return mapper.apply(value);
}
```

A valid call:

```java
int size = convert("Lambda", text -> text.length());
```

The argument `"Lambda"` helps the compiler infer `T` to match `String`. The lambda is checked against the target `Function<T,R>` after considering the constraints, and `text.length()` contributes to determining the result type `R`. The result is `6`.

Generic type inference involves multiple steps and constraints (such as wildcards, expected result types, or overloads), so you should not reduce every case to a rule like "Java always infers from the variable on the left." If the compiler cannot find consistent types, you can extract the lambda into a `Function<String,Integer>` variable, add a type witness to the generic method, or adjust the API.

In a Stream:

```java
java.util.List<Integer> lengths =
        java.util.List.of("A", "BB", "CCC")
                .stream()
                .map(String::length)
                .toList();
```

`Stream<String>.map` accepts a `Function<? super String,? extends R>`. The referenced method `String::length` produces an `int`, which can be boxed to `Integer`; the final result is `[1, 2, 3]`. You could also write `.map(s -> s.length())` with the same inference context.

When you want to avoid boxing:

```java
int sum = java.util.List.of("A", "BB", "CCC")
        .stream()
        .mapToInt(String::length)
        .sum(); // 6
```

`mapToInt` has the target `ToIntFunction<? super String>` with a descriptor returning `int`. Choosing the target API affects both the result type and subsequent operations.

## 7. Ambiguity When Overloads Have Multiple Targets

A lambda is not permanently bound to a single functional interface before the compiler examines a call; if a method name has multiple overloads taking different functional interfaces, **ambiguity** can occur.

Illustrative example:

```java
@FunctionalInterface
interface TextRule {
    boolean check(String value);
}

@FunctionalInterface
interface TextMapper {
    String map(String value);
}

static void run(TextRule rule) { /* ... */ }
static void run(TextMapper mapper) { /* ... */ }
```

Both interfaces take a `String` but return different types. For a lambda whose body matches only one interface, the compiler can choose the appropriate overload based on overload resolution rules and lambda compatibility. However, the compiler cannot always pick a unique one: pairs of functional interfaces with similar descriptors, complex generics, or a lambda expression compatible with both can lead to `reference to run is ambiguous`.

Ways to clarify intent:

```java
TextRule rule = s -> s.startsWith("J");
run(rule);

run((TextRule) s -> s.startsWith("J"));
```

The `rule` variable or the `(TextRule)` cast supplies a concrete target. When designing a public API, avoid multiple overloads that differ only in hard-to-distinguish functional interfaces; instead, use clear method names like `filterBy` and `mapWith`.

**Distinguish the lambda's target from the return type of the enclosing method.** Java does not pick an overload solely from "the left-hand side of the assignment is `String`" in every situation; overload resolution rules and lambda applicability checks must be evaluated according to the Java specification. When in doubt, write a minimal example and compile it to see the actual error.

## 8. Exceptions and Limitations of the Target Type

A function descriptor can specify allowed checked exceptions. Two interfaces can take and return the same types while having different exception contracts:

```java
@FunctionalInterface
interface CheckedReader {
    String read(String path) throws java.io.IOException;
}
```

If a method exists:

```java
// Illustrates the signature; an actual method needs a body.
static String load(String path) throws java.io.IOException;
```

The following lambda is compatible with `CheckedReader`:

```java
CheckedReader reader = path -> load(path);
```

But it is not compatible with `Function<String,String>`:

```java
// Does not compile because Function.apply does not declare IOException.
java.util.function.Function<String,String> reader =
        path -> load(path);
```

Having `main throws Exception` outside does not alter the contract of `Function.apply`. You must catch the exception inside the lambda, convert it to an unchecked exception according to an intentional policy, or define a target functional interface with a matching `throws` clause.

The snippets in this section **only illustrate signatures and compatibility**; they are not a standalone Java program (since `load` has no actual body).

## 9. Complete Java 17 Example

The following example demonstrates target typing in four positions: target variable, method argument, return value, and generic method. It also shows that a lambda can implement different functional interfaces if it matches their descriptors.

Create the file **`LambdaTargetTypeDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.UnaryOperator;

public class LambdaTargetTypeDemo {
    @FunctionalInterface
    interface Formatter {
        String format(String text, int times);
    }

    static String decorate(String text, UnaryOperator<String> operation) {
        return "[" + operation.apply(text) + "]";
    }

    static <T, R> R convert(T value, Function<T, R> mapper) {
        return mapper.apply(value);
    }

    static Supplier<String> greetingFactory() {
        return () -> "Xin chào";
    }

    public static void main(String[] args) {
        Function<String, Integer> length = text -> text.length();
        Predicate<String> atLeastFour = text -> text.length() >= 4;
        Consumer<String> show = text ->
                System.out.println("Consumer: " + text);
        Formatter repeat = (text, times) -> text.repeat(times);
        UnaryOperator<String> upper = text ->
                text.toUpperCase(Locale.ROOT);

        Supplier<String> greeting = greetingFactory();
        String decorated = decorate("java", upper);
        int converted = convert("Lambda", String::length);
        List<Integer> lengths = List.of("A", "BB", "CCC")
                .stream().map(String::length).toList();

        System.out.println("Function: " + length.apply("Java"));
        System.out.println("Predicate: " + atLeastFour.test("Go"));
        System.out.println("Formatter: " + repeat.format("Hi", 2));
        System.out.println("Decorate: " + decorated);
        System.out.println("Generic: " + converted);
        System.out.println("Supplier: " + greeting.get());
        System.out.println("Stream: " + lengths);
        show.accept("Done");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LambdaTargetTypeDemo.java
java LambdaTargetTypeDemo
```

**Standard output** (run in a UTF-8 terminal to display Vietnamese diacritics properly):

```text
Function: 4
Predicate: false
Formatter: HiHi
Decorate: [JAVA]
Generic: 6
Supplier: Xin chào
Stream: [1, 2, 3]
Consumer: Done
```

Explanation:

1. `length` has the target `Function<String,Integer>`, so `text` is `String`, and `length()` returns `int`, which is boxed if needed; `"Java"` has length `4`.
2. `atLeastFour` has the target `Predicate<String>`, returning `boolean`. `"Go"` has length `2`, so the result is `false`.
3. `repeat` has the target `Formatter` with descriptor `(String,int) -> String`; `"Hi".repeat(2)` produces `"HiHi"`.
4. `upper` has the target `UnaryOperator<String>`, and `decorate` takes that exact type as its second parameter; `"java"` is uppercased and wrapped into `"[JAVA]"`.
5. `convert` is a generic method; the compiler infers the types from `"Lambda"`, the method reference `String::length`, and the result context, producing `6`.
6. `greetingFactory` provides the target `Supplier<String>` directly in its return type, so `() -> "Xin chào"` is valid in the `return` statement.
7. `Stream<String>.map` requires a mapper compatible with `Function`; `String::length` produces the list of lengths `[1, 2, 3]`.
8. `show` has the target `Consumer<String>`; the body prints `Consumer: Done` and has no return value to use.

The program is written completely in a single `public` class, the filename matches the class name, and it uses only APIs available in Java 17.

## 10. Common Mistakes

### 10.1. Using a Bare Lambda with `var` or `Object`

```java
// Invalid: missing functional interface target.
var action = () -> 42;
Object any = () -> 42;

// Valid:
java.util.function.Supplier<Integer> action = () -> 42;
Object any = (java.util.function.Supplier<Integer>) () -> 42;
```

The lines above are **contrasting snippets not meant to be used together in one program** because the names `action` and `any` are declared twice; the invalid lines only illustrate compilation errors.

### 10.2. Using a Class or Non-Functional Interface

```java
// Invalid because List does not have a single abstract method:
java.util.List<String> list = () -> "text";
```

An interface with multiple independent abstract methods cannot be a lambda target either. Use classes/records to model data, and use functional interfaces to model a SAM behavioral contract.

### 10.3. Checking Only the Parameter Count and Forgetting the Return Type

```java
// Invalid: Predicate<String> requires boolean.
java.util.function.Predicate<String> invalid =
        s -> s.length();
```

Check the return type as well. Change it to `s -> s.length() > 0` if the goal is a condition, or use `Function<String,Integer>` if the goal is the length.

### 10.4. Writing Explicit Parameter Types with the Wrong Target

```java
// Invalid: IntUnaryOperator takes int, not String.
java.util.function.IntUnaryOperator wrong =
        (String s) -> s.length();
```

Writing an explicit type does not grant permission to change the target's descriptor. Change it to `(int n) -> n * 2` or choose an interface that actually accepts `String`.

### 10.5. Treating a Method Reference as a Standalone Function Type

A method reference, like a lambda, also typically requires a functional interface target:

```java
java.util.function.ToIntFunction<String> length =
        String::length;
```

This type has the descriptor `(String) -> int`. You cannot expect `var length = String::length;` to guess that it should be `ToIntFunction<String>` instead of other compatible functional interfaces.

### 10.6. Handling Checked Exceptions at the Wrong Layer

`Function<T,R>` does not have `throws IOException`; even if the outer calling method declares `throws IOException`, the lambda still cannot let that checked exception escape from `apply`. If you need that contract, create a `CheckedFunction<T,R>` interface or handle the exception inside the lambda according to a defined policy.

### 10.7. Assuming Lambdas Are Pure Functions by Default

A target type only guarantees the method contract; it **does not guarantee** the absence of side effects, immutability of state, or independence from the clock. `Supplier<Integer> next = counter::incrementAndGet` still has a side effect; `Consumer` is commonly used to perform an observable action. Evaluate the body and how the API uses it rather than assuming purity from the `->` syntax alone.

## 11. Practice Exercises

1. Given `Function<String,Integer> f = s -> s.length();`, state the target type and function descriptor, then rewrite the lambda using `(String s)` and `(var s)`.
2. Explain why `var f = s -> s.trim();` does not compile, even if changed to `var f = (String s) -> s.trim();`.
3. Given `static void run(Predicate<String> check)`, where does the compiler infer the type of `x` in `run(x -> x.startsWith("J"))` from?
4. With `Supplier<String> supplier = () -> "hi";`, if the body is changed to `s -> "hi"`, is the issue the number of parameters or the return type?
5. Write a `UnaryOperator<String>` that appends `"!"` to the end of a string and pass it to a method that accepts `UnaryOperator<String>`.
6. Explain why `Predicate<String> p = s -> s.length();` is invalid, even though `s` is a valid `String`.
7. Given `TextRule rule = text -> !text.isBlank();`, if another target accepts `Object`, what happens if the body still calls `isBlank()`?
8. Consider `Object x = (Supplier<String>) () -> "ready";`. What role does the cast play? Why does removing the cast cause an error?
9. Fix the error when `Function<Path,String>` receives a lambda calling a method that declares `throws IOException`.
10. In `Stream.of("a", "bb").map(s -> s.length()).toList()`, infer the input element type, the mapper result, and the resulting list element type.

**Answer Hints:** (1) `Function<String,Integer>`, descriptor `(String) -> Integer`. (2) A bare lambda has no functional interface target. (3) From the parameter of `run`: `Predicate<String>`. (4) `Supplier` requires 0 parameters. (5) `s -> s + "!"`. (6) `Predicate` needs `boolean`, while the body returns `int`. (7) With only `Object`, the compiler does not see `isBlank()`. (8) The cast provides the `Supplier<String>` target. (9) Catch/convert the exception per business rules or use a functional interface with `throws`. (10) `String` in, `int` can be boxed to `Integer`, resulting in `List<Integer>`.

## Conclusion

**A lambda in Java requires a functional interface as its target type** so the compiler can determine the function descriptor and check body compatibility. The target type can be supplied by an assignment, method argument, return type, cast, or other contexts that support target typing. Knowing how to identify the target before reading a lambda helps resolve inference errors, use generics/Streams accurately, and design APIs with clear behavioral contracts.