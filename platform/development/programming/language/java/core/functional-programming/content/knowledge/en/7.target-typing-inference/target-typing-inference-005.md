# Generic Type Inference When Passing Lambdas to Java Methods

## 1. The Problem: Why Can Lambda Parameter Types Be Omitted?

When calling a *generic method*, Java usually infers type parameters such as `T` and `R` automatically instead of forcing the caller to write `<String, Integer>` explicitly. When an argument is a lambda expression, the compiler must also determine **the types of the lambda parameters** and **the return type of the lambda body**. These two tasks support each other.

Consider the method:

```java
static <T, R> R convert(T input, Function<T, R> converter) {
    return converter.apply(input);
}
```

This is an illustrative method that must be placed inside a class with `java.util.function.Function` imported. At the call site:

```java
int length = convert("Java", text -> text.length());
```

The compiler infers `T` from the argument `"Java"` (type `String`). Consequently, the lambda has a *target type* matching `Function<String, R>`, which causes `text` to be understood as `String`. The body `text.length()` produces `int`, compatible with the reference type `Integer` via boxing; the result can be assigned to `int length` via unboxing. In this example, `R` is inferred as `Integer`, and the result is `4`.

Crucially: **a lambda is not compiled as a standalone function and then typed later**. It is a *poly expression*: its validity and parameter inference depend on the target type of its context.

Lesson goals: understand the type-inference flow when passing lambdas into generic methods; write proper constraints with `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, and `Supplier<T>`; grasp the role of expected return types, wildcards, method references, and how to handle compiler errors.

## 2. Three Sources of Constraints During Type Inference

For the signature `<T, R> R convert(T input, Function<T, R> converter)`, the compiler does not guess arbitrarily. It solves compatibility constraints from multiple positions.

| Constraint source | Example | Effect |
| --- | --- | --- |
| Ordinary argument | `convert("Java", ...)` | Constrains `T` by the type of `"Java"` |
| Functional parameter | `Function<T,R>` | Provides the target type to check lambda parameters |
| Lambda body | `text -> text.length()` | Checks that `length()` is valid on `String`, constrains `R` from the result |
| Result context | `Integer n = convert(...)` | Places compatibility requirements on the call's return type |
| Other arguments | `combine(3, 4, (a,b) -> a+b)` | Constrains the same `T` across both arguments and the lambda |

A single constraint does not always yield a unique type immediately. Java resolves constraints according to *type inference* rules (JLS §18), accounting for boxing/unboxing, subtyping, and expression compatibility. The resulting types are determined by the entire call, not solely by one argument or the operation inside the lambda.

Practical rule of thumb: **read the method signature → inspect the explicitly typed arguments → determine the lambda's target type → check the body → match the result type**.

## 3. The Lambda's Target Type Comes from the Generic Parameter

A lambda such as `s -> s.length()` does not state on its own what type `s` has. When passed into the `Function<T,R>` parameter of `convert`, the context supplies the appropriate target type.

```java
static <T, R> R convert(T input, Function<T, R> fn) {
    return fn.apply(input);
}

// In main:
Integer size = convert("Hello", s -> s.length());
```

When used in a class that imports `java.util.function.Function`, `s` in the lambda is understood as `String`. Java knows `String` has `length()`. The return type `Integer` is compatible with the boxed `int` value.

Contrast this with the following call:

```text
String wrong = convert("Java", s -> s.length());
```

This is an **intentionally non-compiling example** with the `convert` signature above: the lambda's result is the length `int`/boxed `Integer`, whereas the expected result is `String`. The compiler may report `inference variable R has incompatible bounds`.

Do not "fix" this by arbitrarily casting to `String`. Choose the right expected type (`Integer`, `int`) or change the transformation to return `String`.

## 4. Lambdas Do Not Have a Standalone Target Type

The following statements must be placed in a context that has a target type:

```java
Function<String, Integer> count = s -> s.length();
IntUnaryOperator increment = n -> n + 1;
```

To use these statements directly in a method, import `Function` and `IntUnaryOperator` from `java.util.function`.

Contrast:

```text
var count = s -> s.length(); // Invalid: no target type for the lambda
```

`var` is used for local variable type inference, but it cannot synthesize a functional interface type from a standalone lambda. However, **`var` can receive the result of a generic method call** if the method and arguments provide enough constraints:

```java
var size = convert("Java", s -> s.length());
```

In this case, the `convert` call has a signature that resolves the lambda and result; `var` simply receives the already-inferred type of the method invocation expression.

Also distinguish `(var s) -> s.length()` (using `var` in a lambda parameter list, Java 11+) from `var f = s -> ...` (inferring the type of a variable holding a lambda). The first form still requires a target type such as `Function<String,Integer>`.

## 5. Complete Java 17 Example: Various Generic Methods

Save the entire contents to `GenericLambdaInferenceDemo.java`:

```java
import java.util.*;
import java.util.function.*;

public class GenericLambdaInferenceDemo {
    static <T, R> R convert(T input, Function<T, R> fn) {
        return fn.apply(input);
    }

    static <T, R> List<R> map(
            List<T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    static <T> List<T> filter(
            List<T> source,
            Predicate<? super T> test) {
        List<T> result = new ArrayList<>();
        for (T item : source) {
            if (test.test(item)) {
                result.add(item);
            }
        }
        return result;
    }

    static <T> T supply(Supplier<T> fn) {
        return fn.get();
    }

    static <T> T combine(T a, T b, BinaryOperator<T> fn) {
        return fn.apply(a, b);
    }

    static <T> void consume(T input, Consumer<? super T> fn) {
        fn.accept(input);
    }

    static <T, R> List<R> streamMap(
            List<T> source,
            Function<? super T, ? extends R> mapper) {
        return source.stream().<R>map(mapper).toList();
    }

    static <T> Function<T, String> describe(String prefix) {
        return item -> prefix + item;
    }

    static <T, U> Function<T, U> chain(Function<T, U> f) {
        return f;
    }

    public static void main(String[] args) {
        int len = convert("Java", s -> s.length());
        System.out.println(len);

        List<Integer> lengths =
                map(List.of("An", "Binh", "Chi"), s -> s.length());
        System.out.println(lengths);

        System.out.println(
                filter(List.of(2, 3, 4, 5), n -> n % 2 == 0));

        String label = supply(() -> "ready");
        System.out.println(label);

        int total = combine(3, 4, (x, y) -> x + y);
        System.out.println(total);

        consume("java",
                s -> System.out.println(s.toUpperCase(Locale.ROOT)));

        System.out.println(
                GenericLambdaInferenceDemo.<String, Integer>convert(
                        "Hello", s -> s.length()));

        List<Number> values = map(
                List.of(1, 2, 3), n -> n.doubleValue() + 0.5);
        System.out.println(values);

        System.out.println(
                streamMap(List.of("A", "BB"), String::length));

        Function<Integer, String> printer =
                GenericLambdaInferenceDemo.<Integer>describe("num=");
        System.out.println(printer.apply(5));

        System.out.println(
                chain((String s) -> s + "!").apply("Hi"));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 GenericLambdaInferenceDemo.java
java GenericLambdaInferenceDemo
```

Output:

```text
4
[2, 4, 3]
[2, 4]
ready
7
JAVA
5
[1.5, 2.5, 3.5]
[1, 2]
num=5
Hi!
```

Notable mechanisms in the program:

1. `convert("Java", s -> s.length())`: the `String` argument guides `T` inference, and the lambda determines the conversion to `Integer`.
2. `map(List.of(...), s -> s.length())`: the source elements guide `T=String`; the target `List<Integer>` and lambda result guide `R=Integer`.
3. `filter(List.of(...), n -> n % 2 == 0)`: `Predicate<? super T>` must return `boolean`; the source is `Integer`, and the resulting list still contains `Integer`.
4. `String label = supply(() -> "ready")`: the lambda takes no parameters; the `String` return type contributes to inferring `T`.
5. `combine(3,4,(x,y)->x+y)`: the two values and `BinaryOperator<T>` together constrain `T`, printing `7`.
6. `consume("java", s -> ...)`: `Consumer<? super T>` accepts data and returns `void`; `T` is inferred from the string argument.
7. `GenericLambdaInferenceDemo.<String, Integer>convert(...)`: a **type witness** (explicit type argument specification) lets you verify or clarify both type parameters. Normally Java can infer them automatically.
8. `List<Number> values = map(List.of(1,2,3), n -> n.doubleValue()+0.5)`: the output is `Double`, which is still compatible with `Number` because `Double` is a subtype of `Number`.
9. `streamMap(..., String::length)`: a method reference is a target-typed expression like a lambda, and `Stream`'s generic method needs an explicit output type in this implementation.
10. `GenericLambdaInferenceDemo.<Integer>describe("num=")`: here `T` **does not appear in the argument** `String prefix`; specifying `<Integer>` creates `Function<Integer,String>`.
11. `chain((String s) -> s + "!")`: the lambda parameter type `String` is written explicitly when passed to the generic method, allowing `T=String` and `U=String` to be inferred.

## 6. When Type `T` Appears Only Inside the Lambda

Consider the method:

```java
static <T> Function<T, String> describe(String prefix) {
    return item -> prefix + item;
}
```

This snippet illustrates a method definition inside a class that imports `Function`. `T` appears **only in the return type** `Function<T,String>`, not in the ordinary parameter `String prefix`. When used:

```java
Function<Integer, String> printer = describe("num=");
System.out.println(printer.apply(5)); // num=5
```

The assignment context helps infer `T=Integer`. If you want to avoid relying heavily on context, you can write:

```java
Function<Integer, String> printer = MyClass.<Integer>describe("num=");
```

This is illustrative; replace `MyClass` with the actual class containing the method (such as `GenericLambdaInferenceDemo` in the complete program). **Do not guess `T` from the string `"num="`**: it is configuration data, not a constraint on the returned function's input type.

Similarly, if a generic method takes `Function<T,R>` without any ordinary argument tied to `T`, the compiler may have to rely on **explicitly typed lambda parameters**, the result context, or other constraints. If constraints are insufficient, the inferred type may be too broad (such as `Object`) or cause an error when calling a method expecting a specific type.

## 7. Wildcards and Flexibility of Lambda-Accepting APIs

In the `map` example, the signature is:

```java
static <T, R> List<R> map(
        List<T> source,
        Function<? super T, ? extends R> mapper) {
    // Body processes elements and returns List<R>.
}
```

This is an **illustrative signature**, not standalone source code (the body is omitted here). Why use wildcards instead of always writing `Function<T,R>`?

- `? super T` on the input allows the function to handle `T` **or a supertype of `T`**. A function accepting `Object` can process `String` elements.
- `? extends R` on the output allows the function to produce `R` **or a subtype of `R`**. For example, a function returning `Double` can be used where `Number` results are desired.
- This declaration applies the **producer extends, consumer super (PECS)** principle at the function's input and output positions.

However, wildcards make inference and *wildcard capture* more complex. For example, in the main program:

```java
static <T, R> List<R> streamMap(
        List<T> source,
        Function<? super T, ? extends R> mapper) {
    return source.stream().<R>map(mapper).toList();
}
```

The form `.<R>map(mapper)` **explicitly specifies the type parameter of `Stream.map`**, forcing the stream's result type to be `R`. In this case, writing `source.stream().map(mapper).toList()` alone may cause the compiler to infer `List<capture of ? extends R>`, which cannot be assigned directly to `List<R>`. The code with `.<R>map(...)` was compiled with Java 17.

Another simple approach is using a loop and `result.add(mapper.apply(item))` like the `map` method in the main program. Avoid unsafe casts just to satisfy the compiler. When an API does not need wildcards, `Function<T,R>` is simpler; when flexibility is needed, check compiler behavior carefully.

## 8. Inference in Methods Accepting `Predicate`, `Consumer`, `Supplier`, and `BinaryOperator`

**`Predicate<T>`** is typically used when keeping the element type unchanged while varying the condition:

```java
static <T> List<T> filter(List<T> input, Predicate<? super T> predicate) {
    List<T> result = new ArrayList<>();
    for (T item : input) {
        if (predicate.test(item)) result.add(item);
    }
    return result;
}
```

This definition can be placed in a class with `java.util.List`, `java.util.ArrayList`, and `java.util.function.Predicate` imported. When calling `filter(List.of("An","Binh"), s -> s.length()>2)`, `T` comes from `List<String>` and the lambda must return `boolean`; the result contains `"Binh"`.

**`Consumer<T>`** returns `void`, so the lambda body can perform an action: `consume("java", s -> System.out.println(s))`. Here `T` is bound to `String`; `s` is `String`.

**`Supplier<T>`** takes no parameters, so `T` can come from the lambda expression's result and the receiving context: `String ready = supply(() -> "ready");`.

**`BinaryOperator<T>`** constrains both parameters and the result to the same type `T`: `combine(3,4,(a,b)->a+b)` has `T=Integer`. This is not always the right interface for two inputs of different types; when you need distinct `A`, `B`, and result `R`, use `BiFunction<A,B,R>`.

## 9. Generic Methods and Method References

Method references like `String::length` also require a target type, just like `s -> s.length()`:

```java
List<Integer> sizes = map(List.of("A", "BB"), String::length);
```

This illustrative statement sits inside a method that has `map` from Section 5 and imports `List`. The source type is `String`; `String::length` takes a `String` object and produces an `int` boxed to `Integer`, so the result is `[1, 2]`.

When referencing an **overloaded method** (multiple methods with the same name and different parameter lists), the target type also affects which overload the compiler selects. Some references/lambdas can only be fully checked after generic type parameters are inferred. Declare the functional signature explicitly when the compiler cannot pick the method you want.

## 10. Common Errors and How to Read Compiler Messages

### 10.1. Incompatible Return Type Bounds

```text
String wrong = convert("Java", s -> s.length());
```

With `convert(T,Function<T,R>)`, `R` must simultaneously match the length value (`Integer`) and the `String` context. Java 17 rejects this and may report `inference variable R has incompatible bounds`. Fix it as:

```java
Integer correct = convert("Java", s -> s.length());
```

### 10.2. Lambda Returns the Wrong Type for the Target `List`

```text
List<Integer> bad = map(
        List.of("a"), s -> s.toUpperCase());
```

The lambda produces `String` while the resulting list requires `Integer`. This is an intentionally non-compiling example. Fix it to `List<String> upper = map(List.of("a"), s -> s.toUpperCase());`, or keep `List<Integer>` and use `s -> s.length()`.

### 10.3. Ambiguous Overloads

If a class has two overloads:

```java
static void use(Function<String, Integer> f) { }
static void use(ToIntFunction<String> f) { }
```

Both method declarations are valid in a class that imports `Function` and `ToIntFunction`; however, the following call is **intentionally ambiguous**:

```text
use(s -> s.length());
```

Both target types can accept this lambda. To choose explicitly, use:

```java
use((ToIntFunction<String>) s -> s.length());
```

This snippet belongs inside a method body and requires the two overloads above. Do not assume generic inference can always resolve **every** overload; when multiple functional types match, Java may require a concrete target type.

### 10.4. Calling a Nonexistent Method on a Lambda Parameter

```text
consume(10, x -> x.nonexistent());
```

This snippet intentionally fails to compile because parameter `x` has no `nonexistent()` method. The type `T` inferred from `10` is `Integer`, which does not allow calling a nonexistent method. Check the target type and its API before modifying the generic declaration.

### 10.5. Overly General Target Type

When a lambda provides insufficient type information and the generic method has no arguments or return type constraining `T`, `T` may be inferred as a general type like `Object`. The fact that `Object` has `toString()` does not prove `T` is `String`. To avoid confusion, put concrete types in the signature, assign to a variable with a specific target type, write explicit lambda parameter types, or supply a type witness when needed.

## 11. Advanced Notes

**Type inference is not lambda execution:** the compiler analyzes **static types**, without running the body to inspect runtime values. If a lambda body has conditionals or multiple `return` branches, all paths must be compatible with the target type.

**Before inference, the compiler must determine call applicability:** not every detail of the body is used immediately to pick an overload; applicability depends on constraints and lambda shape. Therefore, overloaded calls with type-inferred lambdas may need an explicit target type.

**Generic types do not accept primitives directly:** `Function<int,int>` is invalid because generic type arguments must be reference types. Use `Function<Integer,Integer>` with boxing/unboxing, or `IntUnaryOperator` for `int → int`.

**Runtime behavior remains separate:** a lambda bound to `Function` executes only when `apply` is called or when the generic method invokes it. Inference of `T` and `R` happens at compile time.

**Do not overuse casts:** casting to a raw `Function` can hide errors and lead to `ClassCastException`. Prefer fixing signatures, clarifying target types, and preserving type safety.

## 12. Exercises with Answers

**Exercise 1.** Given `static <T,R> R convert(T x, Function<T,R> f)`, how does `Integer n = convert("hello", s -> s.length());` infer `T` and `R`?

Answer: `T` corresponds to `String` from `"hello"`; `s` is `String`; `length()` returns `int` compatible with `Integer`, so `R` is `Integer`. `n=5` if the method calls `f.apply(x)`.

**Exercise 2.** What constraint sources does `String s = supply(() -> "ok");` use when `supply` has signature `<T> T supply(Supplier<T> f)`?

Answer: the value returned from the lambda is `String` and the assignment context `String s` contributes to constraining `T`; there are no ordinary parameters.

**Exercise 3.** Can `map(List.of(1,2), n -> n.doubleValue())` be assigned to `List<Number>` if `map` uses `Function<? super T,? extends R>`?

Answer: **Yes**. The input is `Integer`, and the lambda returns `double` boxed to `Double`, which is a subtype of `Number`. The signature with `? extends R` supports this (and the result was verified in the main program).

**Exercise 4.** Why is `List<Integer> x = map(List.of("a"), s -> s.toUpperCase());` incorrect?

Answer: the lambda produces `String`, whereas the expected result is `Integer`. Change the result type to `List<String>` or use a lambda that computes length.

**Exercise 5.** When a method returns `Function<T,String>` and its ordinary parameters do not mention `T`, how can you explicitly request `T=Integer`?

Answer: assign the result to `Function<Integer,String>` or call `ClassName.<Integer>method(...)` using the actual class name, such as `GenericLambdaInferenceDemo.<Integer>describe("num=")`.

## 13. Summary

- Generic inference when passing lambdas is **a process of solving type constraints for the entire call**, combining ordinary arguments, functional interface target types, lambda bodies, and result contexts.
- Lambdas need a **target type**; unannotated parameters receive their types from the functional interface specialized by inference.
- `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>`, and `BinaryOperator<T>` give the compiler different input/output contracts.
- Wildcards `? super T` and `? extends R` increase reusability but sometimes require clearer inference guidance, such as `stream().<R>map(mapper)`.
- If the compiler reports `incompatible bounds`, `cannot infer type-variable`, `incompatible types`, or `reference is ambiguous`, trace the constraints back from the method signature instead of using raw casts to hide the error.
- Use a type witness `ClassName.<T,R>method(...)` or explicit lambda parameter types only when genuinely needed to help the compiler or reader.

Official references: [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html), [§15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27), [§15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12).