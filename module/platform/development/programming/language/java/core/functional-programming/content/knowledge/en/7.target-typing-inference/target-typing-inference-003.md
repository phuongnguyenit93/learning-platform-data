# Checking Parameter and Return Type Compatibility of a Lambda in Java

## 1. Goal: Does the Lambda Match the Contract Required at the Use Site?

In Java, a lambda expression such as `x -> x * 2` **does not carry an independent function type on its own**. It is checked within a *target type* context: the type of the assigned variable, the parameter of the method being called, the return type, or the type of a cast. The target type must be a valid **functional interface**.

A functional interface has one functional abstract method (*single abstract method*, SAM). Its *function descriptor* specifies the number of parameters, the type of each parameter, the return type, and any checked exceptions that may be thrown. Java compares the lambda expression against that descriptor to determine whether the lambda is **compatible**.

For example:

~~~java
java.util.function.IntUnaryOperator square = x -> x * x;
java.util.function.Predicate<String> nonEmpty = text -> !text.isEmpty();
java.util.function.Consumer<String> print = text -> System.out.println(text);
~~~

These three statements are valid when placed inside a method. However, the same lambda syntax cannot be assigned arbitrarily to any interface: `square` requires `int → int`, `nonEmpty` requires `String → boolean`, and `print` requires `String → void`.

**Core verification flow:** (1) find the target type; (2) find the SAM; (3) check **parameter count and types**; (4) check **body form and result type**; (5) check **checked exceptions**, accessibility, and related constraints.

## 2. Identify the Target Type and SAM Signature First

Some familiar interfaces in `java.util.function`:

| Functional interface | SAM | Parameter types | Return type |
|---|---|---|---|
| `Runnable` | `void run()` | 0 parameters | `void` |
| `Supplier<T>` | `T get()` | 0 parameters | `T` |
| `Consumer<T>` | `void accept(T value)` | 1 `T` parameter | `void` |
| `Predicate<T>` | `boolean test(T value)` | 1 `T` parameter | `boolean` |
| `Function<T,R>` | `R apply(T value)` | 1 `T` parameter | `R` |
| `BiFunction<T,U,R>` | `R apply(T t,U u)` | 2 parameters | `R` |
| `IntUnaryOperator` | `int applyAsInt(int x)` | 1 `int` | `int` |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | 1 `T` | `int` |

For example, `Function<String,Integer> f = text -> text.length();` has target type `Function<String,Integer>`. Its descriptor is `Integer apply(String)`. The compiler infers that `text` has type `String`; the `length()` method returns `int`, which is **boxed** into `Integer` to match the return type.

Conversely, `ToIntFunction<String> f = text -> text.length();` has descriptor `int applyAsInt(String)` and receives `int` directly, with no boxing needed on the result.

An interface with multiple `default` or `static` methods can still be a functional interface if, under the language rules, only one abstract contract remains as its SAM. You should not determine the SAM by simply counting every method that appears in the source file.

## 3. First Condition: Parameter Count Must Match

**The number of lambda parameters must equal the number of parameters in the descriptor.** There is no mechanism to automatically drop or add parameters.

~~~java
Runnable ready = () -> System.out.println("ready");
java.util.function.Function<String, Integer> length =
        text -> text.length();
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (a, b) -> a + b;
~~~

The examples above are valid because they have **0, 1, and 2** parameters respectively, matching the SAM.

The following cases are **intentionally invalid** (do not put them in a runnable file):

~~~java
// INVALID: Runnable.run() takes no parameters.
// Runnable wrong = x -> System.out.println(x);

// INVALID: Function.apply(T) takes only one parameter.
// Function<String,Integer> wrong = (a,b) -> a.length() + b.length();

// INVALID: BiFunction.apply(T,U) takes two parameters.
// BiFunction<Integer,Integer,Integer> wrong = x -> x + 1;
~~~

Parentheses are syntactic and do not change the parameter count: `x -> ...` and `(x) -> ...` both have exactly one parameter; `() -> ...` has zero parameters; `(a,b) -> ...` has two parameters.

## 4. Second Condition: Parameter Types Must Match the Descriptor

### 4.1. Unannotated Parameters: Java Infers Them from the Target Type

~~~java
java.util.function.Function<String, Integer> size =
        text -> text.length();
java.util.function.BiFunction<String, Integer, String> repeat =
        (text, count) -> text.repeat(count);
~~~

In `size`, `text` is `String`. In `repeat`, `text` is `String` and `count` is `Integer`; when calling `String.repeat(int)`, `count` is unboxed to `int`.

Java does **not** infer types by guessing "if the variable is named `text`, it must be a string"; the SAM itself decides that. If the target type is `Function<Integer,Integer>`, the expression `text -> text.length()` is invalid because `text` has type `Integer` and has no `length()` method.

### 4.2. Explicitly Typed Parameters: Must Match the Descriptor Type Exactly

~~~java
java.util.function.Function<String, Integer> good =
        (String text) -> text.length();

java.util.function.IntUnaryOperator twice =
        (int n) -> n * 2;
~~~

These are valid. When declaring lambda parameter types explicitly, each type must **match** the corresponding parameter type in the descriptor after the target type is determined; you cannot substitute a subtype, supertype, or wrapper just because a conversion would exist during a normal method call.

~~~java
// INVALID: descriptor requires Number, not Integer.
// Function<Number,String> wrong = (Integer n) -> n.toString();

// INVALID: IntUnaryOperator descriptor requires int, not Integer.
// IntUnaryOperator wrong = (Integer n) -> n + 1;
~~~

If you need to process a `Number` passed in, use `(Number n) -> ...` or `n -> ...` with `Function<Number,...>`. If you want `Integer`, declare the target type as `Function<Integer,...>` accordingly. In Java, object subtyping flexibility **does not allow arbitrarily changing an explicitly declared parameter type in a lambda**.

### 4.3. `var` Parameters Still Get Their Types from the Descriptor

Since Java 11, you can write:

~~~java
java.util.function.BiFunction<String, Integer, String> repeat =
        (var text, var times) -> text.repeat(times);
~~~

`text` is `String` and `times` is `Integer` according to the SAM; `var` does not mean both have the same type. If one parameter is declared with `var`, **all** parameters in the same list must use `var`; `(var text, times)` and `(var text, Integer times)` are invalid. For a single parameter, parentheses are required: `(var text) -> ...`, not `var text -> ...`.

`var` in a lambda also does not create a target type on its own: `var f = x -> x;` is invalid because the lambda expression is not yet bound to a specific functional interface.

## 5. Third Condition: Is the Lambda Body Compatible with the Return Type?

You must distinguish **`void`** from a **value-returning type**. Java checks both the body form (*expression body* vs. *block body*) and the types of the returned expressions.

### 5.1. Value-Returning SAM: The Expression Must Be Compatible with the Return Type

~~~java
java.util.function.Function<String, Integer> length =
        text -> text.length();

java.util.function.Predicate<String> longerThanThree =
        text -> text.length() > 3;

java.util.function.Function<Integer, String> tag =
        number -> "N-" + number;
~~~

- `length` returns `int`, which is boxed to `Integer` as required by `Function<String,Integer>`.
- `longerThanThree` returns `boolean` per the descriptor of `Predicate<String>`.
- `tag` returns `String` per `Function<Integer,String>`.

Invalid examples:

~~~java
// INVALID: Predicate<String>.test must return boolean.
// Predicate<String> wrong = text -> text.length();

// INVALID: Function<String,String>.apply must return String.
// Function<String,String> wrong = text -> System.out.println(text);

// INVALID: Function<String,Integer> requires Integer, not String.
// Function<String,Integer> wrong = text -> "length=" + text.length();
~~~

With `Predicate`, a non-zero number is not implicitly treated as `true` as in some other languages. With `Function<String,String>`, `System.out.println` returns `void` and therefore cannot produce the required `String` value.

### 5.2. Value-Returning `{ ... }` Block: Every Branch Must Have a Valid `return`

~~~java
java.util.function.Function<Integer, String> grade = score -> {
    if (score >= 80) {
        return "high";
    }
    return "normal";
};
~~~

A lambda block with a `String` return type must return a compatible value whenever it completes along a normal execution path. If any branch reaches the end of the block without returning a value or throwing an exception, the compiler rejects it.

~~~java
// INVALID: there is a path that does not return String.
// Function<Integer,String> wrong = score -> {
//     if (score >= 80) return "high";
// };
~~~

When using a *block body*, the `;` after `return` belongs to the Java statement; the `;` after `}` terminates the lambda assignment statement. Do not confuse writing `{ System.out.println(x); }` with producing a return value.

### 5.3. `void`-Returning SAM: Statement Expression or `void`-Compatible Block

~~~java
java.util.function.Consumer<String> show =
        text -> System.out.println(text);

java.util.function.Consumer<String> showAgain = text -> {
    System.out.println(text);
    return;
};
~~~

`Consumer<String>` has `void accept(String)`, so both lambdas above are valid. Inside a `void` block, `return;` is allowed, whereas `return text.length();` is incompatible because it attempts to return a value.

Conversely, for `Function<String,Integer>`, an empty `return;` does not satisfy the `Integer` return type.

### 5.4. Distinguishing *Statement Expressions* from Value Expressions

This is a detail that often surprises developers. An **expression body** that is a *statement expression* (such as a method invocation, assignment, increment/decrement, or object creation) can be compatible with a `void`-returning SAM **even if that expression produces a value**. The value is discarded.

~~~java
java.util.List<String> items = new java.util.ArrayList<>();

// List.add returns boolean; Consumer accepts it because this is a method invocation.
java.util.function.Consumer<String> addOnly = text -> items.add(text);

// Predicate receives the actual boolean value of List.add.
java.util.function.Predicate<String> addAndReport = text -> items.add(text);
~~~

These two examples are illustrative snippets, not a standalone runnable program. The body `items.add(text)` is a method invocation, which is a statement expression. With `Consumer`, the returned boolean is discarded; with `Predicate`, the boolean becomes the result. Both have the side effect of mutating the list, so they should not be used as examples of pure functions.

However, **not every value-producing expression is `void`-compatible**:

~~~java
// INVALID: an ordinary arithmetic expression is not a statement expression.
// Consumer<Integer> wrong = number -> number + 1;

// INVALID: a numeric literal is not a statement expression.
// Runnable wrong = () -> 42;
~~~

To perform work and discard the result, use a valid invocation or block statement. To receive a result, choose a functional interface whose SAM returns the corresponding value type.

### 5.5. JLS Terminology: *void-compatible* and *value-compatible*

For a **block lambda**:

- A block is **void-compatible** if every `return` statement in the block (if any) has only the form `return;`.
- A block is **value-compatible** if it cannot complete normally (*cannot complete normally*) and every `return` statement (if any) has the form `return expression;`.

A block containing only `throw new IllegalStateException();` can satisfy both criteria. Do not rely solely on seeing the `return` keyword; you must also consider whether control flow can reach the end of the block.

For an **expression lambda**: it is compatible with a `void`-returning target when the body is a statement expression; it is compatible with a value-returning target when the body is an expression whose type is compatible in an assignment context.

## 6. Complete Program: Checking Parameters and Return Types

Save as **`LambdaCompatibilityDemo.java`**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;

public class LambdaCompatibilityDemo {
    @FunctionalInterface
    interface Formatter {
        String format(int value);
    }

    static <T, R> R transform(T value, Function<? super T, ? extends R> rule) {
        return rule.apply(value);
    }

    public static void main(String[] args) {
        Formatter formatter = (int value) -> "id-" + value;
        BiFunction<String, Integer, String> repeat =
                (text, count) -> text.repeat(count);
        IntUnaryOperator square = (int n) -> n * n;
        Predicate<String> longText = (String s) -> s.length() >= 4;
        Function<String, Integer> length = text -> text.length();
        Consumer<String> report =
                text -> System.out.println("report:" + text);

        Function<Integer, String> band = score -> {
            if (score >= 80) {
                return "high";
            }
            return "normal";
        };

        System.out.println("formatter=" + formatter.format(7));
        System.out.println("repeat=" + repeat.apply("ha", 2));
        System.out.println("square=" + square.applyAsInt(3));
        System.out.println("longText=" + longText.test("Java"));
        System.out.println("length=" + length.apply("hello"));
        report.accept("ok");
        System.out.println("band=" + band.apply(85));
        System.out.println("generic=" + transform("abc", String::toUpperCase));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac LambdaCompatibilityDemo.java
java LambdaCompatibilityDemo
~~~

Expected stdout:

~~~text
formatter=id-7
repeat=haha
square=9
longText=true
length=5
report:ok
band=high
generic=ABC
~~~

**Checking each contract:**

1. `Formatter.format(int)` takes an `int` and returns `String`; `(int value) -> "id-" + value` matches one parameter and one `String` result.
2. `BiFunction<String,Integer,String>` requires two parameters of types `String` and `Integer`; `repeat` uses `String.repeat(int)`, so the second parameter is unboxed when called.
3. `IntUnaryOperator` takes and returns `int`; `(int n) -> n * n` has the exact parameter type.
4. `Predicate<String>` returns `boolean`; the condition `s.length() >= 4` satisfies this.
5. `Function<String,Integer>` allows boxing the `int` result of `s.length()` into `Integer`.
6. `Consumer<String>` returns `void`; the `println` call is a valid statement expression.
7. `band` has a block that returns `String` on both the above-threshold and below-threshold paths.
8. `transform` is a generic method accepting a `Function<? super T,? extends R>`. With `"abc"` and `String::toUpperCase`, both the input and output types are `String`. Generic type inference and lambda/method reference checking work together at the call site.

The results above are determined by the concrete code; this guide does not require any framework or library outside Java SE.

## 7. Complete Program: One Method Invocation Compatible with Two Return Types

The following example helps distinguish "a body that returns a value" from "a SAM that requires a return value."

Save as **`LambdaBodyDemo.java`**:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaBodyDemo {
    static boolean persist(String value) {
        System.out.println("saved:" + value);
        return value.length() > 1;
    }

    public static void main(String[] args) {
        Consumer<String> action = value -> persist(value);
        Function<String, Boolean> check = value -> persist(value);

        Predicate<Integer> even = number -> {
            if (number == null) {
                return false;
            }
            return number % 2 == 0;
        };

        action.accept("A");
        System.out.println("accepted=" + check.apply("AB"));
        System.out.println("even=" + even.test(4));
    }
}
~~~

Run:

~~~bash
javac LambdaBodyDemo.java
java LambdaBodyDemo
~~~

Stdout:

~~~text
saved:A
saved:AB
accepted=true
even=true
~~~

Explanation:

- `persist` returns `boolean`, but `Consumer<String>` has a `void`-returning SAM. The method invocation `persist(value)` is a statement expression, so the boolean result is **discarded** when calling `action.accept("A")`.
- `Function<String,Boolean>` has a SAM returning `Boolean`, so with `check`, the `boolean` result of `persist` is boxed and becomes the return value of `check.apply("AB")`.
- `Predicate<Integer>` requires returning `boolean`. The `even` block returns `boolean` on both branches, so it is compatible.
- `persist` prints to stdout, which is a side effect. A lambda being compatible with its target type **does not mean** it is pure or free of observable state changes.

Note that `Consumer<String> action = value -> value.length();` is also accepted because `value.length()` is a method invocation (a statement expression), even though the `int` value is discarded. Conversely, `value -> value.length() + 1` is not a statement expression and is therefore invalid for `Consumer`.

## 8. Boxing, Unboxing, Primitive Types, and `null`

When checking a lambda's result, Java allows conversions appropriate for an **assignment context**, including boxing/unboxing and certain numeric conversions.

~~~java
java.util.function.Function<String, Integer> boxed =
        text -> text.length();                 // int → Integer

java.util.function.ToIntFunction<String> primitive =
        text -> text.length();                 // int → int

java.util.function.Function<String, Long> widenedAndBoxed =
        text -> (long) text.length();          // long → Long
~~~

The key point is that **return compatibility** does not mean wrapper types are arbitrarily interchangeable. For example, an `int` does not automatically box to `Long`. In the third example, the `(long)` cast ensures the expression has type `long`, which is then boxed to `Long`.

For explicitly typed parameters, the rule is stricter: `(Integer n) -> ...` **does not** substitute for `(int n) -> ...` when the descriptor requires `int`. Conversely, when calling `Function<Integer,...>.apply(3)`, the method invocation can box the literal `3` to `Integer` under normal invocation rules. Do not confuse these two stages.

**`null` also deserves attention:**

- `Function<String,String> f = s -> null;` is valid because `String` is a reference type.
- `Function<String,Integer> f = s -> null;` also compiles; the reference result is `null`, and the caller must handle it.
- `ToIntFunction<String> f = s -> null;` is **invalid**: the `null` literal cannot directly be a primitive `int` result.
- If a lambda returns an `Integer` variable whose value is `null` and the SAM requires `int`, unboxing at runtime can throw `NullPointerException`. Successful compilation does not guarantee runtime safety.

## 9. Checked Exceptions Are Part of Compatibility Checking

A lambda cannot arbitrarily let a checked exception escape if the target type's SAM does not allow it.

~~~java
@FunctionalInterface
interface FileLoader {
    String load(String path) throws java.io.IOException;
}

FileLoader loader = path ->
        java.nio.file.Files.readString(java.nio.file.Path.of(path));
~~~

This is an **illustrative declaration snippet**, without `main`. It is valid because `FileLoader.load` declares `throws IOException`.

However, the following example is **intentionally invalid**:

~~~java
// Function.apply does not declare throws IOException.
// java.util.function.Function<String,String> invalid = path ->
//         java.nio.file.Files.readString(java.nio.file.Path.of(path));
~~~

The compiler requires handling or declaring the exception according to the SAM's contract. Adding `try/catch` inside the lambda, using a custom functional interface that permits the checked exception, or moving I/O to another layer are possible fixes depending on the problem. Do not misread this error as "parameter or return type incompatibility": it is an **additional checked-exception condition** in lambda compatibility checking.

## 10. Compatibility with Method Invocation Contexts and Overloads

A lambda can appear as a method argument, such as `list.sort((a,b) -> a.compareTo(b))` or `stream.map(x -> x.toString())`. In these cases, the API's parameter declaration supplies the target type for the lambda.

If a method has **multiple overloads** accepting different functional interfaces, a lambda may match multiple candidates; the compiler must apply additional overload selection rules. Sometimes no unique overload can be chosen.

Example of two overloads both taking a zero-parameter SAM returning `String`:

~~~java
// Illustrates intentional ambiguity when both overloads coexist.
static void execute(java.util.function.Supplier<String> task) {}
static void execute(java.util.concurrent.Callable<String> task) {}

// execute(() -> "ok"); // INVALID: cannot distinguish the overloads.
~~~

`Supplier<String>` and `Callable<String>` both have a 0-parameter SAM returning `String`; the difference in checked-exception capability does not by itself let `() -> "ok"` uniquely select one overload in the example above.

The simple fix is to specify an **explicit target type**:

~~~java
// Inside the same class containing the overloads above:
execute((java.util.function.Supplier<String>) () -> "ok");
~~~

Or assign the lambda to a typed `Supplier<String>` variable and pass that variable. Casting to the functional interface clarifies intent and lets the compiler re-check parameters/return values against the chosen interface.

**Note:** Not all overloads with lambdas are ambiguous. Parameter count, return type, parameter types, generic bounds, and *most specific* rules can help select a single overload. Read the API signature and compiler error message instead of guessing from the lambda's syntax.

## 11. Checking Lambdas with Generics and Wildcards

Consider the method:

~~~java
static <T, R> java.util.List<R> convert(
        java.util.List<T> items,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return items.stream().map(mapper).toList();
}
~~~

This is an **illustrative method snippet**, which can be placed in a class with `java.util.List` imported or using the fully qualified names shown above. When calling `convert(List.of("a", "bbb"), String::length)`, Java infers `T` from the `String` data source and infers the result type `R` to match `Integer` due to boxing the result of `length()`.

The wildcards serve these roles:

- `? super T` on the input type allows a mapper that accepts `T` or a supertype of `T`.
- `? extends R` on the output type allows a mapper that produces a value compatible with `R`, including a subtype of `R`.

This does not make an explicitly typed lambda `(Object x) -> ...` automatically compatible with **every** target type: final compatibility depends on the concrete descriptor after inference and the usage context.

For lambdas with unannotated parameters, the compiler typically relies on the target type to infer parameter types before checking the body. With complex overloads or generics, compile errors sometimes reflect multiple constraints at once: parameter count, bounds, return type, and accessibility.

## 12. When Is a Method Reference Compatible?

A method reference such as `String::length`, `Integer::parseInt`, or `System.out::println` also needs a functional interface target type. The SAM contract determines how the call is mapped, even though method reference inference and resolution have their own specific rules.

~~~java
java.util.function.ToIntFunction<String> length = String::length;
java.util.function.Function<String, Integer> parse = Integer::parseInt;
java.util.function.Consumer<String> print = System.out::println;
~~~

- `String::length` is compatible with `String → int`.
- `Integer::parseInt` accepts `String` and returns `int`, which is boxed when assigned to `Function<String,Integer>`.
- `System.out::println` resolves to the overload matching the `String` parameter and `void` result.

If a method reference's signature does not match the descriptor, switching from a lambda to a method reference will not fix the error. When debugging, try writing the equivalent explicit lambda and inspect the exact required parameters and return type.

## 13. Quick Error Reference: What Works and What Fails?

| Target type | Lambda | Verdict |
|---|---|---|
| `Runnable` | `() -> System.out.println("go")` | Valid: 0 parameters, statement expression |
| `Runnable` | `x -> System.out.println(x)` | Invalid: extra parameter |
| `Function<String,Integer>` | `s -> s.length()` | Valid: `String → Integer` via boxing |
| `Function<String,Integer>` | `s -> "x"` | Invalid: `String` result is incompatible with `Integer` |
| `Predicate<String>` | `s -> s.isEmpty()` | Valid: `boolean` result |
| `Predicate<String>` | `s -> s.length()` | Invalid: `int` result, not `boolean` |
| `Consumer<String>` | `s -> System.out.println(s)` | Valid: `void`-returning statement expression |
| `Consumer<String>` | `s -> s.length() + 1` | Invalid: arithmetic expression is not void-compatible |
| `IntUnaryOperator` | `(int n) -> n + 1` | Valid: `int → int` |
| `IntUnaryOperator` | `(Integer n) -> n + 1` | Invalid: explicit parameter type does not match `int` |
| `Supplier<String>` | `() -> "ok"` | Valid: 0 parameters, returns `String` |
| `Supplier<String>` | `() -> { System.out.println("ok"); }` | Invalid: does not return `String` |
| `Function<String,String>` | `s -> null` | Type-valid, but requires a `null` policy at runtime |

When you see an error at `->`, the root cause may lie in the **target type** inferred across multiple API layers. Rather than immediately rewriting every lambda, finding the descriptor and checking systematically usually pinpoints the cause faster.

## 14. Pre-Compilation Self-Check Workflow

A short, reliable checklist when reviewing code:

1. **Identify the target-typing context:** variable assignment, return, API call, or cast?
2. **Identify the functional interface:** does it have a valid SAM, and are there generics/wildcards to infer?
3. **Count the parameters:** 0, 1, 2, or more? Does it match the SAM's parameter count?
4. **Check each parameter's type:** implicit/`var` infers from the SAM; explicit must match the descriptor type exactly.
5. **Check the return type:** does the SAM return `void` or a value? Is the expression body compatible?
6. **If using a block:** is there a branch missing `return` or returning the wrong type? Are `return;` and `return expression;` mixed illegally?
7. **Consider valid type conversions:** are widening, boxing/unboxing, and `null` genuinely compatible?
8. **Consider checked exceptions:** does the lambda throw a checked exception beyond the SAM's contract?
9. **If overloaded/generic:** are multiple target types competing? Do you need a typed variable or cast to disambiguate?
10. **Run the compiler and tests:** compiler messages are the final authority; after compiling, test boundary values, `null`, exceptions, and side effects.

Checking SAM compatibility is **compile-time verification of types and lambda body structure**. It does not prove business logic correctness, nor does it automatically check for overflow, thread safety, side effects, or `null` values causing runtime exceptions.

## 15. Self-Check Questions

1. Which conversion makes `Function<String,Integer> f = s -> s.length();` valid?
2. Why is `IntUnaryOperator op = (Integer n) -> n + 1;` invalid, even though `Integer` can be unboxed to `int`?
3. Can `Consumer<String> c = s -> list.add(s);` be valid when `List.add` returns `boolean`? Explain in terms of *statement expressions*.
4. Is `Consumer<Integer> c = n -> n + 1;` valid?
5. A lambda block returning `String` has an `if` branch that returns `String`, while the remaining path falls through to the end of the block. How does the compiler handle this?
6. Why does `var f = s -> s.length();` not determine the lambda's type on its own?
7. If both `Supplier<String>` and `Callable<String>` are overloads, will `() -> "ok"` definitely select a single overload?
8. When the method reference `Integer::parseInt` is assigned to `Function<String,Integer>`, what are the parameter and return types?

**Answers:** (1) boxing `int → Integer`. (2) Because an explicit parameter type in a lambda must match the descriptor's `int`; this rule differs from argument conversions at call sites. (3) Yes, `add` is a method invocation / statement expression and the boolean value is discarded. (4) No, `n + 1` is not a statement expression usable with a `void`-returning SAM. (5) Invalid if there is a normal completion path that does not return the required result. (6) A lambda needs a functional interface target type. (7) No, the two overloads can cause ambiguity; supply a typed variable or cast. (8) `String → int`, with the result boxed to `Integer`.

## 16. Official Specification Sources

- [Java Language Specification SE 17, `15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): syntax, bodies, and rules for checking lambdas in target-type contexts.
- [JLS SE 17, `15.27.3 — Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): congruence of parameter count/types, void/value-compatible bodies, return types, and conversions.
- [JLS SE 17, `9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): defining functional interface types and descriptors.

**Remember:** When inspecting a lambda, do not guess types from `->` or variable names. Start from the **functional interface and SAM**; then compare **parameter count → parameter types → body form → return type → checked exceptions**. A lambda is valid when it matches the contract of a **concrete target type** in the Java context being compiled.