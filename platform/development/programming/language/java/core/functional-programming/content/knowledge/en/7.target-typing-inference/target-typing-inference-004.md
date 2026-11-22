# Why `var` Cannot Infer the Type of a Standalone Lambda

In Java, `var` in a **local variable declaration** requires the compiler to infer a concrete type from the **initializer expression**. However, a lambda such as `s -> s.length()` has no standalone type for the compiler to read immediately: it is a **poly expression**, which requires a **target type** that is a functional interface. Therefore, the following statement is **intentionally invalid**:

```java
var length = (String s) -> s.length(); // COMPILE error
```

Writing `String s` only specifies the lambda's parameter type; it **does not specify which functional interface the lambda implements**. In Java, a signature like `String -> int` is not a generic function type automatically synthesized by the language. Many functional interfaces can match the same lambda, such as `Function<String, Integer>` or an application-defined interface.

The most common and clearest fix is to declare the functional interface on the left-hand side:

```java
java.util.function.Function<String, Integer> length = s -> s.length();
```

Here the compiler knows `Function<String,Integer>` is the target type, so it checks and interprets the lambda according to `Integer apply(String value)`. This lesson explains why `var` cannot resolve a direct lambda on its own, when `var` can still be used, and how to distinguish it from `var` in a **lambda parameter list**.

## 1. Two Different Mechanisms: Local-Variable Type Inference and Target Typing

### Local-Variable Type Inference with `var`

Since Java 10, you can write:

```java
var count = 42;                         // int
var text = "Java";                      // String
var names = java.util.List.of("A");    // List<String>
```

In these lines, the expression on the right already has a determined type: the literal `42` is `int`, the string literal is `String`, and `List.of("A")` returns a list whose element type is inferred as `String`. The compiler uses those types to declare the variables. `var` **does not mean dynamic typing**; the local type is decided at compile time and does not change afterward.

The snippet above is an **illustrative code fragment** that must sit inside a method or block; do not place `var` declarations directly at class field level.

### Target Typing with Lambdas

A lambda has the form:

```java
(parameters) -> expression
(parameters) -> { statements; }
```

This is a **syntax template**, not a standalone program. A lambda can be an implementation of **a functional method**, but it must know which contract to implement. For example:

```java
java.util.function.Predicate<String> notEmpty =
        s -> s != null && !s.isEmpty();
```

The target type `Predicate<String>` tells the compiler the input is `String` and the result must be `boolean`, corresponding to `boolean test(String value)`. Without a target type, the compiler has no basis for choosing an appropriate functional object type.

**Mechanism summary:** `var` needs an already-typed initializer to infer from; a lambda needs an external target type to determine its contract. When writing `var f = s -> ...`, neither side supplies the target type, so the compiler reports an error.

## 2. Why Knowing Parameter Types or Return Type Is Still Not Enough

Consider the following interfaces:

```java
@FunctionalInterface
interface NameLength {
    int getLength(String value);
}

@FunctionalInterface
interface OtherLength {
    int measure(String value);
}
```

These are valid top-level declarations in Java; the functional method names differ, yet both have the same structure of one `String` parameter and an `int` result. The lambda:

```java
(String s) -> s.length()
```

**can match both target types**. There is no rule that automatically picks `NameLength` or `OtherLength` just because the parameter is explicitly written as `String`. A lambda does not predefine a class or a compiler-generated named function type.

Therefore, both of the following local declarations are **intentionally invalid**:

```java
var first = s -> s.length();
var second = (String s) -> s.length();
```

The `second` declaration still lacks a target type even though the parameter type is known. The body returning an `int` also does not resolve which interface to pick. In a target context like `Function<String,Integer>`, Java can even box `int` to `Integer`, making the set of compatible interfaces for the same lambda even broader.

When using an explicit target type, both of the following are valid:

```java
NameLength first = (String s) -> s.length();
OtherLength second = (String s) -> s.length();
```

The two variables receive objects compatible with **two different interfaces**, even though the lambda body is identical. Both `first.getLength("Java")` and `second.measure("Java")` evaluate to `4`.

## 3. Direct `var` Declarations with Lambdas That Are Rejected

The following snippets **intentionally fail to compile**:

```java
// No target type for a zero-parameter lambda.
var task = () -> System.out.println("run");

// No target type for a single-parameter lambda.
var mapper = text -> text.length();

// Specifying the parameter type still does not supply a target interface.
var mapper2 = (String text) -> text.length();

// Using var in the lambda parameter also does not create a target interface.
var mapper3 = (var text) -> text.length();

// Two parameters have the exact same problem.
var adder = (int left, int right) -> left + right;
```

Depending on the context and compiler version, the message typically states that **lambda expression needs an explicit target type** or that the variable's type cannot be inferred from the lambda. The core issue is not missing parentheses or missing parameter types, but **the absence of a functional interface target type**.

Standalone method references follow the same rule:

```java
// INVALID: a method reference also needs a target type.
var length = String::length;
```

`String::length` can match `Function<String,Integer>`, a custom interface with an equivalent method, or other compatible functional contexts. Without a target type, the compiler cannot choose one on its own.

## 4. Right Way #1: Declare the Functional Interface Directly

The most readable and generally recommended approach:

```java
java.util.function.Supplier<String> greeting = () -> "Hello";
java.util.function.Predicate<String> hasText =
        text -> text != null && !text.isBlank();
java.util.function.Function<String, Integer> length =
        text -> text.length();
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (a, b) -> a + b;
```

This is an illustrative snippet that can be placed inside a method.

| Target Interface | Functional Method | Lambda Form |
| --- | --- | --- |
| `Runnable` | `void run()` | `() -> System.out.println("run")` |
| `Supplier<T>` | `T get()` | `() -> value` |
| `Predicate<T>` | `boolean test(T value)` | `x -> condition` |
| `Consumer<T>` | `void accept(T value)` | `x -> action(x)` |
| `Function<T,R>` | `R apply(T value)` | `x -> transform(x)` |
| `BiFunction<T,U,R>` | `R apply(T x, U y)` | `(x, y) -> combine(x,y)` |

The table shows **illustrative templates**; the functions `condition`, `action`, `transform`, and `combine` do not exist unless the application declares them. Choose the interface that reflects the actual meaning of the operation; do not pick a type merely because its signature "looks similar" while ignoring the API semantics.

## 5. Right Way #2: `var` Receives an Already-Typed Functional Variable

`var` can certainly **hold a lambda through a value that already has a type**:

```java
java.util.function.Function<String, Integer> declared =
        text -> text.length();

var inferred = declared; // Function<String, Integer>
int size = inferred.apply("Java"); // 4
```

When reaching `var inferred = declared`, the initializer `declared` has the clear type `Function<String,Integer>`. The compiler only infers the type for **the new variable from an already-typed variable expression**, without needing to find a target type for a standalone lambda.

Similarly, if a factory method has an explicit functional interface return type:

```java
static java.util.function.Predicate<String> nonBlankRule() {
    return text -> text != null && !text.isBlank();
}

// In another method:
var rule = nonBlankRule(); // Predicate<String>
boolean result = rule.test("Java"); // true
```

These are two **contextually paired snippets**: `nonBlankRule` is a static method in a class, while the `var rule` assignment is in the calling method. The lambda in `return` has a target type because of the **declared return type** of `nonBlankRule`. When the caller uses `var`, `nonBlankRule()` is already a call with a known return type.

## 6. Right Way #3: Cast the Lambda to a Functional Interface

If there is a reason to keep `var` on the left, you can supply the target type with a cast **right on the initializer expression**:

```java
var length = (java.util.function.Function<String, Integer>)
        (text -> text.length());

var supply = (java.util.function.Supplier<String>) () -> "ready";
```

The cast explicitly states the target type for the lambda, so `var` can infer from the type of **the entire cast expression**.

However, this style is usually longer and harder to read than:

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();
```

Use a cast when you need to disambiguate an overload or clarify the contract on a specific expression; do not treat it as a way to force `var` to infer a lambda on its own. The actual target type is still provided by you.

The same applies to method references:

```java
var length = (java.util.function.Function<String, Integer>)
        String::length;
```

Both the lambda and the method reference in these examples are checked against the functional method signature of the target interface.

## 7. Java 17 Program: Valid `var` After a Target Type Exists

Create the file **`LambdaVarInferenceDemo.java`**:

```java
import java.util.Comparator;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaVarInferenceDemo {
    static Predicate<String> hasTextRule() {
        return text -> text != null && !text.isBlank();
    }

    public static void main(String[] args) {
        // Target type is on the left-hand side.
        Function<String, Integer> length = text -> text.length();

        // var infers from an already clearly typed variable.
        var reused = length;

        // Target type is supplied by a cast.
        var plusOne = (Function<String, Integer>)
                (text -> text.length() + 1);

        // A zero-parameter lambda also needs a functional interface.
        var ready = (Supplier<String>) () -> "ready";

        // Method reference gets its target type from a cast.
        var sameIgnoreCase = (Comparator<String>)
                String::compareToIgnoreCase;

        // Method call with an explicit return type.
        var rule = hasTextRule();

        System.out.println("length=" + reused.apply("Java"));
        System.out.println("plusOne=" + plusOne.apply("Java"));
        System.out.println("ready=" + ready.get());
        System.out.println("sameIgnoreCase="
                + sameIgnoreCase.compare("java", "JAVA"));
        System.out.println("hasText=" + rule.test("Java"));
        System.out.println("blank=" + rule.test("   "));
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 LambdaVarInferenceDemo.java
java LambdaVarInferenceDemo
```

**Exact stdout:**

```text
length=4
plusOne=5
ready=ready
sameIgnoreCase=0
hasText=true
blank=false
```

Type-inference path for each variable:

1. `length` has the explicitly declared type `Function<String,Integer>`; the lambda is target-typed against `apply(String)`.
2. `reused` also has the type `Function<String,Integer>` because its initializer is the variable `length`.
3. `plusOne` gets the type `Function<String,Integer>` from the cast; the compiler checks that the lambda body returns `int`, which can be boxed to `Integer`.
4. `ready` gets the type `Supplier<String>` from the cast; creating the lambda does not yet execute the `"ready"` body.
5. `sameIgnoreCase` has the type `Comparator<String>`, so `String::compareToIgnoreCase` is interpreted as comparing two strings.
6. `rule` has the type `Predicate<String>` because `hasTextRule()` declares that interface as its return type.

**No line asks `var` to discover a functional interface from a standalone lambda or method reference.** The target type is either determined beforehand or stated directly in the cast expression.

## 8. `var` in Lambda Parameters Is a Different Matter

Since Java 11, Java allows `var` **inside a lambda parameter list**, for example:

```java
java.util.function.Function<String, String> normalize =
        (var text) -> text.trim().toUpperCase();
```

In this example, `var` is syntax for the **lambda parameter** `text`, and the compiler infers the type `String` **from the target type** `Function<String,String>`. This does not mean `var` can infer the type of the entire lambda on its own.

Two different positions:

| `var` Position | Question to Infer | Where Does Sufficient Information Come From? |
| --- | --- | --- |
| `var f = expression;` | What type does the local variable `f` have? | From the type of the initializer `expression`. |
| `Function<String,Integer> f = (var s) -> ...;` | What type does the lambda parameter `s` have? | From the functional method of the target type `Function<String,Integer>`. |

When using `var` in a multi-parameter lambda list, you must use it for **all parameters**:

```java
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (var a, var b) -> a + b;
```

The following forms are intentionally invalid:

```java
// INVALID: mixing var and an implicitly typed parameter.
(var a, b) -> a + b

// INVALID: mixing var and an explicit type.
(var a, Integer b) -> a + b

// INVALID: a var parameter must be inside parentheses.
var a -> a + 1

// INVALID: var for the parameter, but no target type for the lambda.
var f = (var a) -> a + 1;
```

Besides clarifying inferred types, `var` in lambda parameters allows placing annotations on parameters when the syntax and target type permit. `var` is still not a standalone Java type that can replace arbitrary data types.

## 9. Java 17 Program: `var` in Parameters with a Target Type

Create the file **`LambdaParameterVarDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaParameterVarDemo {
    public static void main(String[] args) {
        Function<String, String> normalize =
                (var text) -> text.trim().toUpperCase(Locale.ROOT);

        BiFunction<Integer, Integer, Integer> add =
                (var left, var right) -> left + right;

        Predicate<String> valid =
                (var text) -> text != null && !text.isBlank();

        // On the right-hand side is an already-typed Function variable.
        var sameNormalizer = normalize;

        System.out.println("normalize=" + sameNormalizer.apply(" java "));
        System.out.println("add=" + add.apply(2, 3));
        System.out.println("validNull=" + valid.test(null));
        System.out.println("validJava=" + valid.test("Java"));

        // map provides the target type for the method reference.
        var lengths = List.of("a", "java").stream()
                .map(String::length)
                .toList();

        System.out.println("lengths=" + lengths);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 LambdaParameterVarDemo.java
java LambdaParameterVarDemo
```

**Exact stdout:**

```text
normalize=JAVA
add=5
validNull=false
validJava=true
lengths=[1, 4]
```

In `normalize`, the target type `Function<String,String>` determines that `text` is `String`. In `add`, the target type `BiFunction<Integer,Integer,Integer>` determines that both parameters are `Integer`. Meanwhile, `List.of(...).stream().map(String::length)` is valid because `map` takes `Function<? super T,? extends R>` and thus supplies the target-type context for the method reference. The terminal `toList()` result has type `List<Integer>`, which `var lengths` infers.

## 10. Target Typing in Method Parameters, Returns, and Casts

A lambda can receive a target type from several contexts other than assignment:

**Passing to a method:**

```java
static int evaluate(java.util.function.Function<String, Integer> fn) {
    return fn.apply("Java");
}

// In the calling method:
int length = evaluate(s -> s.length()); // 4
```

These are **two illustrative code snippets**: `evaluate` is declared in a class, while the call is inside another method. The parameter `fn` has type `Function<String,Integer>`, so the lambda argument is checked against that target type.

**Returning from a method with a declared type:**

```java
static java.util.function.Supplier<String> makeGreeting() {
    return () -> "Xin chào";
}
```

The return type `Supplier<String>` provides the target type for the lambda. The caller can write `var supplier = makeGreeting();` because the call `makeGreeting()` has a known return type.

**Casting:**

```java
Object callback = (Runnable) () -> System.out.println("run");
```

The cast `(Runnable)` supplies the target type for the lambda. The variable `callback` is declared as `Object`, so to call `run()` elsewhere you must check/cast it back to `Runnable` appropriately. Creating a valid lambda and being able to invoke APIs through the reference variable's type are two separate matters.

## 11. Why Can't Java "Pick" an Interface by Signature?

Java uses **nominal types** for functional interfaces: a lambda is converted to the interface **specified in the context**, not to a generic `(T) -> R` structure synthesized by Java. Beyond the signature, an interface carries information such as:

- Name and contract semantics, for example `Predicate<T>` tests a condition whereas `Function<T,Boolean>` expresses a transformation to a `Boolean` wrapper.
- Checked exception rules in the functional method (for example `Runnable.run()` declares no checked exceptions, whereas `Callable<V>.call()` declares `throws Exception`).
- Additional `default`/`static` methods, such as `Predicate.and` and `Function.andThen`.
- Generic bounds, type parameters, return types, and compatibility rules.

Two interfaces whose abstract methods have the same signature are not necessarily interchangeable in API calls. You cannot assume that `(String s) -> s.length()` should automatically be `Function<String,Integer>` merely because that interface is familiar.

Consequence for overloaded methods: if two overloads accept different functional interfaces that are both compatible with a lambda, the call can become **ambiguous**. The compiler applies Java's overload resolution rules; when needed, you can specify the type with an explicitly declared variable or a cast. `var` does not resolve target-type ambiguity on its own.

## 12. Common Misconceptions and Errors

1. **"`var` can guess any type."** False. `var` infers from an already-typed initializer; it does not invent a functional interface for a lambda.
2. **"Writing the lambda parameter type is enough."** False. `var f = (String s) -> s.length();` still has no target type.
3. **"A lambda inherently has type `Function`."** False. It can match many functional interfaces; `Function` is only one option.
4. **"Method references do not need a target type."** False. `var f = String::length;` is also invalid.
5. **"`var` cannot be used with any lambda value."** False. `var f = existingFunction;`, `var f = factory();`, and `var f = (Function<String,Integer>) (s -> s.length());` all have clear type sources.
6. **"Using `(var x)` in a lambda infers the whole interface."** False. `var` in a lambda parameter list also needs a target type.
7. **"`var` is dynamic typing."** False. The local variable's type is statically inferred at compile time, unlike languages with runtime type changes.
8. **"If it compiles after a cast, that means `var` inferred the lambda."** False. The cast is what provides the target type.
9. **"You can mix `var` and parameter types in a lambda."** False. Parameters in the same list must be consistent according to Java's rules.
10. **"An inferred type means any API can accept it."** False. The variable's type determines which methods can be called; for example, `Object callback` has no `run()` until checked and cast.

## 13. Quick Decision Table

| Code | Valid? | Reason |
| --- | --- | --- |
| `var x = 42;` | Yes | The literal has type `int`. |
| `var f = () -> 42;` | No | The lambda has no target type. |
| `var f = (String s) -> s.length();` | No | Specifies parameter only, not the interface. |
| `var f = String::length;` | No | The method reference needs a target type. |
| `Supplier<Integer> f = () -> 42;` | Yes | The target type is declared. |
| `var f = (Supplier<Integer>) () -> 42;` | Yes | The cast supplies the target type. |
| `Function<String,Integer> f = s -> s.length(); var g = f;` | Yes | `g` infers from a typed variable. |
| `var f = makeSupplier();` | Yes if `makeSupplier()` has a known return type | The initializer is a typed call. |
| `Function<String,Integer> f = (var s) -> s.length();` | Yes in Java 11+ | `var s` uses the outer target type. |

With `var`, the other rules of local variable declarations must also be followed; for example, `var x;` is invalid because it lacks an initializer. The table focuses only on the relationship between `var`, lambdas, and target typing.

## 14. Self-Check

**Question 1.** Why does the following fail to compile, even though `String` is written explicitly?

```java
var f = (String s) -> s.toUpperCase();
```

**Answer:** There is no functional interface serving as the target type for the lambda. `String` is only the parameter type; it does not state which contract to implement.

**Question 2.** Rewrite the statement above so it is clear:

```java
java.util.function.Function<String, String> f =
        s -> s.toUpperCase();
```

This declares the target type `Function<String,String>`; the compiler infers parameter `s` as `String` and checks the return type.

**Question 3.** How can you keep `var` on the left-hand side?

```java
var f = (java.util.function.Function<String, String>)
        (s -> s.toUpperCase());
```

Valid because the cast supplies the target type; there is no standalone lambda inference.

**Question 4.** Is `Function<String,Integer> f = (var s) -> s.length();` valid?

**Yes** in Java 11+. `var` belongs to the lambda parameter and gets its type from the already-declared target type.

**Question 5.** Why is `var f = String::length;` invalid?

**Answer:** A method reference is a poly expression and needs a functional interface target. You can use `Function<String,Integer> f = String::length;`.

**Question 6.** Can `var f = factory();` receive a lambda value?

**Yes**, if `factory()` returns an object with a known functional interface type. `var` infers from the method's return type, rather than inferring directly from lambda syntax.

**Remember:** `var` on the left-hand side needs an **already-typed** initializer; standalone lambdas and method references need a **functional interface target type**. Declare the interface explicitly, use a factory returning the interface, or supply a target type via a cast when appropriate. `var` in **lambda parameters** is only syntax for inferring parameter types when a target type already exists.