# Type Inference for Lambdas and Method References in Java Generics

## Learning Objectives

Lambda expressions and method references allow passing behavior into a method without verbose anonymous class declarations. However, when combined with Java Generics, the type of a lambda cannot be understood merely by looking at `s -> s.length()`. The compiler needs a **target type**, typically a *functional interface*, to determine parameter types, result type, matching overloads, and related constraints.

After this lesson, you will be able to:

- Explain **target typing**, **functional interface**, single abstract method (*SAM*), and **poly expression**.
- Distinguish the inferred type for lambda parameters from the generic type inferred when calling a method that accepts a lambda.
- Use `Function<T,R>`, `Predicate<T>`, `Supplier<T>`, `Consumer<T>`, `Comparator<T>`, `UnaryOperator<T>`, and `BinaryOperator<T>` in the right contexts.
- Write static, bound instance, unbound instance (receiver as first parameter), and constructor method references.
- Understand why the same method reference can resolve to different overloads under different target types.
- Resolve errors like `lambda expression needs an explicit target-type`, `reference to ... is ambiguous`, incompatible type inference, and using `var` in lambdas.
- Read and verify Java 17+ examples using `javac`/`java` instead of guessing output.

## 1. Foundation: the functional interface defines the lambda's contract

A lambda requires a **functional interface as its target**. For example:

```java
@FunctionalInterface
interface Converter<S, R> {
    R convert(S input);
}
```

With `Converter<String,Integer>`, the compiler knows the lambda parameter is `String` and the return value must be compatible with `Integer`:

```java
Converter<String, Integer> length = text -> text.length();
Integer count = length.convert("Java"); // 4
```

`String.length()` returns `int`, which is boxed to `Integer`. If the target is `Converter<Integer,Integer>`, the body `text.length()` will not compile because `Integer` has no such method.

**The focus of this lesson is target typing/inference**: the compiler infers a lambda's type from **where the expression is used**, not by guessing an independent type for the lambda. Standard interfaces like `Function`, `Predicate`, `Supplier`, `Consumer`, `Comparator`, and `Callable` are distinct target sources; each has a SAM with its own parameter count, return type, and checked exceptions. A functional interface may still have default/static methods, and `@FunctionalInterface` helps the compiler verify the declaration's validity.

Later sections analyze type inference when lambdas/method references participate in **generic method calls** and how ambiguous overloads are resolved; that is a distinct skill beyond memorizing the table of standard interfaces.

## 2. Target typing: working backward from the call site to the expression

Java treats lambdas and method references as **poly expressions** in appropriate contexts: their types depend on where they are used.

Example:

```java
Function<String, Integer> length = s -> s.length();
```

The compiler knows:

1. The expression is on the right-hand side of an assignment to `Function<String,Integer>`.
2. The SAM `Function.apply` takes String and returns Integer.
3. Therefore `s` is inferred as `String`.
4. `s.length()` returns `int`, which can be boxed to `Integer`.
5. The lambda is valid for the target type.

The same expression with an incompatible target type:

```java
// DOES NOT COMPILE:
// Function<Integer, Integer> length = s -> s.length();
```

The reason is `s` now has type Integer, which has no `length()` method.

**Target types commonly come from:** declarations and assignments, method invocation arguments, return statements inside methods returning a functional interface, casts to a functional interface, conditional expressions in targeted contexts, and other situations specified by the JLS.

Example of a target from a method call:

```java
List<Integer> lengths =
        List.of("A", "Java").stream()
            .map(String::length)
            .toList();
```

The compiler uses the generic signature of `Stream.map` and the call context to infer that `String::length` converts String to Integer (the `int` result is boxed). Java 17 supports `Stream.toList()`; the result is unmodifiable per this API's contract.

**Without a target type, lambdas and method references cannot carry a standalone type like an ordinary object.**

## 3. Why is `var fn = s -> s.length()` invalid?

Since Java 10, `var` lets the compiler infer a local variable's type from its initializer expression:

```java
var number = 42;              // int
var text = "hello";           // String
var names = List.of("A");     // List<String>
```

However, a lambda does not provide a target functional interface when initializing a variable with `var`:

**File `UntypedLambda.java` — intentionally does not compile:**

```java
class UntypedLambda {
    void test() {
        var operation = s -> s.length();
    }
}
```

Command:

```bash
javac --release 17 UntypedLambda.java
```

Verified key message:

```text
cannot infer type for local variable operation
(lambda expression needs an explicit target-type)
```

Similarly for method references:

**File `UntypedMethodReference.java` — intentionally does not compile:**

```java
class UntypedMethodReference {
    void test() {
        var operation = String::trim;
    }
}
```

Compilation yields the error:

```text
cannot infer type for local variable operation
(method reference needs an explicit target-type)
```

How to fix: provide a functional interface on the declaration side or an explicit cast.

```java
Function<String, Integer> length = s -> s.length();
Function<String, String> trim = String::trim;
```

If you really want `var` for a variable holding a lambda, you must supply a target type in the initializer expression via a cast or a strongly typed method call:

```java
var operation =
        (java.util.function.Function<String, Integer>) (s -> s.length());
```

This style is longer and usually less readable than declaring `Function<String,Integer>` directly. `var` is useful elsewhere, but **does not solve the lack of a target type for lambdas/method references**.

## 4. `var` in a lambda parameter list is a different matter

Java 11 allows writing `var` on lambda **parameters**:

```java
Function<String, Integer> a = (var s) -> s.length();
Function<String, Integer> b = (s) -> s.length();
Function<String, Integer> c = s -> s.length();
```

All three expressions take String and return Integer because the target type is `Function<String,Integer>`. Writing `var s` inside a lambda **does not** eliminate the lambda's need for a target type.

One use case for `var` on lambda parameters is enabling annotations on parameters when needed:

```java
// Syntax illustration assuming @MyAnnotation is applicable to PARAMETER:
Function<String, Integer> f =
        (@MyAnnotation var s) -> s.length();
```

You cannot copy this annotation snippet alone to compile without defining `MyAnnotation`. It is purely a syntactic illustration.

### Do not mix `var` and implicit parameters

**File `MixedVarLambdaParameters.java` — intentionally does not compile:**

```java
import java.util.function.BiFunction;

class MixedVarLambdaParameters {
    void test() {
        BiFunction<String, String, String> f =
                (var a, b) -> a + b;
    }
}
```

`javac --release 17` reports:

```text
invalid lambda parameter declaration
(cannot mix 'var' and implicitly-typed parameters)
```

Fix:

```java
BiFunction<String, String, String> f =
        (var a, var b) -> a + b;
```

Or:

```java
BiFunction<String, String, String> f =
        (a, b) -> a + b;
```

Both are valid when placed inside a method with `BiFunction` imported. The rule unifies parameter declaration style within a single lambda: do not arbitrarily mix `var` declarations with implicit or other explicit parameter types.

## 5. Generic type inference when a lambda is a method argument

More importantly, type inference does not happen only inside the lambda. Consider a generic API:

```java
static <T, R> List<R> transform(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

This method appears in the complete program in section 7 and requires importing `List`, `ArrayList`, and `Function`.

Call:

```java
List<Integer> sizes =
        transform(List.of("A", "Java"), String::length);
```

The compiler coordinates multiple constraints:

1. `source` has String elements, so T matches String under subtype/wildcard rules.
2. `String::length` is a method reference needing target `Function<? super T,? extends R>`.
3. `String.length()` returns `int`, which can be boxed to Integer.
4. The resulting expression is assigned to `List<Integer>`, providing additional context to infer R.
5. Hence the program obtains an Integer list with values `1` and `4`.

This is an example of **joint inference**: inferring type arguments of a generic method and checking lambda/reference compatibility interacting through compiler *constraints*. You do not need to write all type arguments explicitly in ordinary calls.

If you need to make intent explicit or the compiler does not infer as desired, you can specify type arguments:

```java
List<Integer> sizes =
        LambdaInferenceDemo.<String, Integer>transform(
                List.of("A", "Java"), String::length);
```

This snippet belongs to the `LambdaInferenceDemo` class context in section 7. Explicit type arguments should be used when they genuinely improve correctness or readability, not as a mandatory style for every generic method.

### Why use `? super T` on mapper?

`Function<? super T, ? extends R>` is more flexible than `Function<T,R>` according to producer/consumer needs:

- The mapper **consumes** an object T, so it can accept a supertype of T.
- The mapper **produces** a result compatible with R, so it can return a subtype of R.

This is a practical application of **PECS (Producer Extends, Consumer Super)**. It lets the API accept many forms of Function while maintaining type-safe relationships.

String example:

```java
List<String> upper = transform(
        List.of(" a ", " b "),
        LambdaInferenceDemo::normalize);
```

`normalize(String)` returns String, and R is inferred to match `List<String>`. The runnable code in section 7 prints `upper=[A, B]`.

### Inferring lambda results from the target

Another generic method:

```java
static <T> T choose(T first, T second, BinaryOperator<T> chooser) {
    return chooser.apply(first, second);
}
```

Call:

```java
String longest = choose("AB", "C",
        (a, b) -> a.length() >= b.length() ? a : b);
```

The compiler determines a and b are String via T, then checks that the conditional expression returns String, compatible with `BinaryOperator<String>`. There is no need to write `(String a, String b)` when the target is already clear.

## 6. Method reference kinds and how they are inferred

A method reference does not invoke a method immediately. It creates an expression that gains concrete meaning only when the compiler knows the target functional interface.

| Kind | Example | Meaning under a matching target |
| --- | --- | --- |
| Static method | `Integer::parseInt` | Takes String, returns int/Integer per target. |
| Unbound instance method | `String::length` | Receiver is first argument; takes String and calls `length()`. |
| Bound instance method | `"An"::equals` | Receiver `"An"` is fixed; takes one argument to compare. |
| Another bound instance method | `"pre-"::concat` | Takes suffix and concatenates onto fixed receiver. |
| Constructor | `ArrayList::new` | Creates ArrayList matching constructor signature. |
| Constructor with argument | `Member::new` | Takes String and creates Member. |
| Generic static method | `LambdaInferenceDemo::<String>identity` | Selects explicit type argument for generic method. |

### 6.1. Static method reference

`Integer::parseInt` is a method reference to static overloads. When assigned:

```java
Function<String, Integer> parse = Integer::parseInt;
```

the target has one String input and Integer result, so the compiler picks the compatible method (e.g., `parseInt(String)` returning int, which is boxed).

A reference to an overloaded method like `String::valueOf` also needs a target to select the invocation:

```java
Function<Integer, String> toStringValue = String::valueOf;
String text = toStringValue.apply(9);
```

`String` has many `valueOf` overloads. The target type constrains parameter count and types. Do not claim that every overloaded method reference always selects a unique overload from the method name alone; the compiler evaluates signatures and context, and sometimes reports ambiguity.

### 6.2. Unbound instance method

`String::trim` in:

```java
Function<String, String> trim = String::trim;
```

means taking a String as **receiver** and calling `receiver.trim()`. This is a `ReferenceType::instanceMethod` method reference. With `String::length`, `Function<String,Integer>` also works even though `length()` has no explicit parameters; the input String is the receiver.

For the same reason:

```java
Function<Member, String> readName = Member::name;
```

uses the record accessor `Member.name()`; the sole argument is a Member instance.

### 6.3. Bound instance method

With:

```java
Predicate<String> isAn = "An"::equals;
Function<String, String> addPrefix = "pre-"::concat;
```

the receiver is already determined by the expression before `::`. The functional interface only supplies the remaining arguments. `isAn.test("An")` returns true; `addPrefix.apply("fix")` returns `"pre-fix"`.

Do not confuse the two forms:

- `String::trim`: the receiver is passed as a parameter of Function.
- `someString::trim`: the receiver already exists; fits a zero-argument target like `Supplier<String>`.

An advanced note: the receiver expression in a bound method reference is evaluated when creating the reference, so if obtaining the receiver has side effects, when that side effect occurs can differ from a lambda that defers evaluating the receiver until invocation. Thus not every method reference can be mechanically replaced by a lambda without checking semantics.

### 6.4. Constructor reference

`ArrayList::new` is also a poly expression needing a target:

```java
Supplier<ArrayList<String>> listFactory = ArrayList::new;
ArrayList<String> result = listFactory.get();
```

The `Supplier` target requires a no-arg constructor. With `Function<Integer,ArrayList<String>>`, the compiler can select the constructor taking initial capacity based on matching signature; both are written `ArrayList::new`, yet the contexts differ.

In the section 7 program, `Member::new` is a constructor reference creating a Member record from a String:

```java
Function<String, Member> memberFactory = Member::new;
Member person = memberFactory.apply("An");
```

A method reference is not “coercing a class into a Function” at runtime; the compiler synthesizes an implementation compatible with the target functional interface.

### 6.5. Generic method references and explicit type arguments

A generic method:

```java
static <T> T identity(T value) {
    return value;
}
```

can be used as:

```java
Function<String,String> id = LambdaInferenceDemo::identity;
```

or with an explicit type argument:

```java
Function<String,String> id =
        LambdaInferenceDemo::<String>identity;
```

Both are in the context of the `LambdaInferenceDemo` class. For straightforward methods, the compiler infers T from the target. Explicit type arguments are used when you want to lock T to a concrete type, when inference is ambiguous, or to clarify intent.

## 7. Complete Java 17 program

**File `LambdaInferenceDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaInferenceDemo {
    record Member(String name) {}

    static <T, R> List<R> transform(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    static <T> T choose(T first, T second, BinaryOperator<T> chooser) {
        return chooser.apply(first, second);
    }

    static <T> T identity(T value) {
        return value;
    }

    static String normalize(String s) {
        return s.trim().toUpperCase(Locale.ROOT);
    }

    static String format(Object o) {
        return "Object:" + o;
    }

    static String format(String s) {
        return "String:" + s;
    }

    static void dispatch(Supplier<String> value) {
        System.out.println("dispatch=" + value.get());
    }

    static void dispatch(Callable<String> value) throws Exception {
        System.out.println("callable=" + value.call());
    }

    public static void main(String[] args) {
        Function<String, Integer> length = s -> s.length();
        Function<String, Integer> lengthVar = (var s) -> s.length();
        Function<String, Integer> lengthRef = String::length;
        System.out.println("lengths="
                + length.apply("Java") + ","
                + lengthVar.apply("Hi") + ","
                + lengthRef.apply("A"));

        List<Integer> sizes = transform(List.of("A", "Java"), String::length);
        System.out.println("sizes=" + sizes);

        List<String> upper = transform(
                List.of(" a ", " b "), LambdaInferenceDemo::normalize);
        System.out.println("upper=" + upper);

        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, String> stringify = String::valueOf;
        System.out.println("parse=" + parse.apply("42")
                + ",valueOf=" + stringify.apply(9));

        Predicate<String> isAn = "An"::equals;
        Function<String, String> trim = String::trim;
        Function<String, String> prefix = "pre-"::concat;
        System.out.println("refs=" + isAn.test("An") + ","
                + trim.apply(" x ") + "," + prefix.apply("fix"));

        Supplier<ArrayList<String>> listFactory = ArrayList::new;
        Function<String, Member> memberFactory = Member::new;
        Function<Member, String> nameOf = Member::name;
        List<Member> members = listFactory.get().isEmpty()
                ? List.of(memberFactory.apply("Binh"), memberFactory.apply("An"))
                : List.of();
        List<Member> sorted = new ArrayList<>(members);
        sorted.sort(Comparator.comparing(Member::name));
        System.out.println("sorted=" + transform(sorted, nameOf));

        Function<String, String> selectOverload = LambdaInferenceDemo::format;
        System.out.println("overload=" + selectOverload.apply("x"));

        String longest = choose("AB", "C", (a, b) ->
                a.length() >= b.length() ? a : b);
        System.out.println("chosen=" + longest);

        System.out.println("identity="
                + transform(List.of("ok"),
                        LambdaInferenceDemo::<String>identity));

        dispatch((Supplier<String>) () -> "supplier");
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac --release 17 -Xlint:all LambdaInferenceDemo.java
java LambdaInferenceDemo
```

**Verified stdout:**

```text
lengths=4,2,1
sizes=[1, 4]
upper=[A, B]
parse=42,valueOf=9
refs=true,x,pre-fix
sorted=[An, Binh]
overload=String:x
chosen=AB
identity=[ok]
dispatch=supplier
```

`javac --release 17 -Xlint:all` compiled the program with zero warnings during verification.

### 7.1. Lambdas with implicit parameters and `var`

The three variables `length`, `lengthVar`, and `lengthRef` all satisfy `Function<String,Integer>` yet are expressed via an implicit lambda, a `var` lambda, and a method reference. The line `lengths=4,2,1` lets you compare all three calls.

### 7.2. Inference between `transform` and mapper

`sizes` holds Integer values from `String::length`. `upper` holds String values from `normalize`. Here the compiler combines method generics with the method reference's target type.

### 7.3. Static/bound/unbound references

`Integer::parseInt` and `String::valueOf` are static; `String::trim` is unbound instance; `"An"::equals` and `"pre-"::concat` are bound instance. The output `refs=true,x,pre-fix` shows they work according to target input/output types.

### 7.4. Constructor references and comparator

`ArrayList::new` supplies a new list. `Member::new` creates the record. `Member::name` reads the name. `Comparator.comparing(Member::name)` infers the key type and compares strings; the program sorts names into `[An, Binh]`.

### 7.5. Overloaded method references resolved by target

The class has both `format(Object)` and `format(String)`. When assigning `LambdaInferenceDemo::format` to `Function<String,String>`, the compiler picks the specific compatible overload, and the executed example outputs `String:x`. Method references share only the name, yet are not devoid of overload information: **the target signature** guides selection.

### 7.6. Explicit type arguments on generic method references

`LambdaInferenceDemo::<String>identity` explicitly specifies that the generic method `identity` is used with T=String. The `transform` call accepts this method reference and prints `identity=[ok]`.

## 8. Overloads accepting lambdas: why are they easily ambiguous?

One lambda can match multiple functional interfaces that have no subtype relationship. Example:

**File `AmbiguousLambdaOverload.java` — intentionally does not compile:**

```java
import java.util.function.Supplier;
import java.util.concurrent.Callable;

class AmbiguousLambdaOverload {
    static void choose(Supplier<String> callback) {}
    static void choose(Callable<String> callback) {}

    static void test() {
        choose(() -> "ok");
    }
}
```

Both `Supplier<String>` and `Callable<String>` take 0 parameters and return String. The lambda `() -> "ok"` matches both in shape and result, so the compiler cannot pick a unique overload.

Command:

```bash
javac --release 17 AmbiguousLambdaOverload.java
```

Verified primary error:

```text
reference to choose is ambiguous
both method choose(Supplier<String>) and method choose(Callable<String>) match
```

### Solution 1: explicitly typed variable

```java
Supplier<String> message = () -> "ok";
choose(message);
```

In the context of `AmbiguousLambdaOverload`, the type of `message` makes the compiler select the Supplier overload.

### Solution 2: cast to the target functional interface

```java
choose((Supplier<String>) () -> "ok");
```

This is how the runnable program in section 7 resolves the `dispatch` overload. Using a local cast can be reasonable if an API must keep both overloads, though it can also make calls harder to read.

### Solution 3: redesign API names or signatures

If two overloads perform different business tasks, naming them `chooseSupplier` and `chooseCallable` is clearer. In particular, never create overloads differing only between `Function<String,Integer>` and `Function<String,String>`: those two types share **the same erasure `Function`**, causing a `name clash` at declaration level before lambda resolution even runs.

**Note:** not every overload with functional interface parameters is ambiguous. The JLS has rules for determining a more specific method based on parameter types and lambda/method-reference shape. Conclude “ambiguous” only when the compiler genuinely cannot pick a unique candidate under overload resolution rules. The Supplier/Callable example above was compiled and confirmed to fail.

## 9. Examples that do not compile: understanding the real causes

### 9.1. Wrong explicit parameter type in a lambda

**File `WrongLambdaParam.java`:**

```java
import java.util.function.Function;

class WrongLambdaParam {
    Function<String, Integer> f = (Integer x) -> x + 1;
}
```

Error:

```text
incompatible types: incompatible parameter types in lambda expression
```

The target `Function<String,Integer>` requires a String parameter, yet the lambda explicitly declares Integer. Fixing only the lambda body is not enough: the parameter signature itself must be compatible with the target.

### 9.2. Missing target type for a method reference

`var operation = String::trim;` is rejected as shown in section 3. Fix by writing `Function<String,String> operation = String::trim;`.

### 9.3. Missing target type for a lambda

`var operation = s -> s.length();` is rejected. Fix by using an appropriately typed target functional interface.

### 9.4. Mixing `var` and implicit parameters

`(var a, b) -> a + b` is invalid. Write both parameters with `var` or neither with `var`.

### 9.5. Overload ambiguity

`choose(() -> "ok")` when both `choose(Supplier<String>)` and `choose(Callable<String>)` exist is ambiguous. Use a typed variable, a cast, or distinct API method names.

These failing files must be compiled **separately**, not placed into the passing `LambdaInferenceDemo.java` file while expecting the whole project to compile cleanly.

## 10. Other inference limits to keep in mind

### 10.1. Expression and block lambdas have result rules

With `Function<String,Integer>`, the lambda must provide an Integer-compatible value on every normal completion path per contract:

```java
Function<String, Integer> size = text -> {
    return text.length();
};
```

With `Consumer<String>`, the functional method returns void:

```java
Consumer<String> printer = text -> System.out.println(text);
```

`System.out.println(text)` is a method invocation compatible with a void-compatible expression lambda. When using a block body, distinguish blocks that perform a task without returning a value from blocks that return a value as required. Not every expression valid in a Function body can be used identically in Runnable/Consumer.

### 10.2. Variables outside a lambda must be final or effectively final

A lambda can read a local variable from an enclosing scope when that variable is not reassigned after initialization:

```java
String prefix = "ID-";
Function<String, String> addPrefix = value -> prefix + value;
System.out.println(addPrefix.apply("7")); // ID-7
```

If you later assign `prefix = "NEW-";` in the same scope, the compiler no longer allows capturing that variable. This is a restriction on captured local variables, not “broken type inference” or “generics disallowing mutation”.

For object fields, the rules differ from capturing local variables, though mutating shared state requires proper design and synchronization.

### 10.3. Checked exceptions must be SAM-compatible

`Function.apply` declares no checked exceptions. A lambda for Function cannot freely throw an uncaught and undeclared `IOException`. `Callable.call() throws Exception`, by contrast, permits checked exceptions under its contract.

Do not solve this by arbitrarily throwing unchecked exceptions when you can design an interface matching your needs or handle checked exceptions at the boundary.

### 10.4. Overload resolution is intertwined with target typing

When a lambda is passed as an argument to an overloaded call, the compiler must consider candidate methods, their parameter types, and lambda compatibility. Hence the process is neither simply “compute the lambda's type first and then pick a method” nor “pick a method by name first and then inspect the lambda”.

In practice, when a call becomes hard to infer, declaring a typed functional interface variable or splitting a generic call into two statements often improves both compiler diagnostics and readability.

### 10.5. Primitive specializations can avoid boxing

`Function<String,Integer>` returns Integer, whereas `String.length()` returns int. The compiler boxes int into Integer. If a high-throughput path needs optimization, you can use `ToIntFunction<String>`:

```java
java.util.function.ToIntFunction<String> length = String::length;
int n = length.applyAsInt("Java");
```

Similarly there are `IntUnaryOperator`, `IntPredicate`, and other specialized interfaces. Before optimizing, verify actual performance requirements; in most business code, the clearest form is preferred.

## 11. Checklist for debugging inference errors

If the compiler reports trouble inferring types for a lambda or method reference:

1. **Find the target type.** Does the destination variable, method parameter type, return type, or cast provide a functional interface?
2. **Check the SAM.** Is there a single functional method with matching arity, parameter types, result, and throws clause?
3. **Check lambda parameter types.** If implicit, what is the compiler inferring from the SAM? If explicit, does the declaration match the SAM?
4. **Trace generic constraints.** What constraints does a method taking `Function<? super T,? extends R>` get from source, mapper, and result target?
5. **Identify overload candidates.** Are there multiple SAMs of the same shape like Supplier/Callable? Are there overloaded methods sharing the name in a method reference?
6. **Try a typed intermediate variable.** Assign the lambda/reference to `Function<String,Integer>` or `Supplier<String>` and pass the variable to reduce ambiguity.
7. **Check `var`.** Never use `var x = lambda` without a target. `(var x) -> ...` still needs a functional interface target.
8. **Read the error message and location carefully.** `cannot infer`, `incompatible parameter types`, and `ambiguous reference` are different issues.
9. **Check boxing and checked exceptions.** An int/Integer result or exception declared on the SAM affects compatibility.
10. **Simplify the API before adding casts everywhere.** If callers need frequent casts to pick overloads, consider renaming/redesigning the API.

## 12. Summary table: lambda or method reference?

| Need | How to write it | Condition to understand |
| --- | --- | --- |
| Convert String to length | `s -> s.length()` | Needs a target such as Function<String,Integer>. |
| Concise receiver call | `String::length` | Unbound instance; String serves as first argument. |
| Trim a passed-in string | `String::trim` | Target Function<String,String>. |
| Compare against a fixed value | `"An"::equals` | Bound receiver; target e.g. Predicate<String>. |
| Parse a number | `Integer::parseInt` | Overloaded static; target determines matching signature. |
| Create a new list | `ArrayList::new` | Constructor target Supplier or corresponding Function. |
| Create Member from name | `Member::new` | Constructor signature matches String→Member. |
| Read Member's name | `Member::name` | Unbound instance; Member receiver is parameter. |
| Pass generic T to T | `ClassName::identity` | T inferred from target; explicit type arguments allowed. |
| Multi-step logic | `x -> { ...; return result; }` | Block-body lambda is often clearer than an awkward method reference. |
| Pick overload via explicit SAM | `(Supplier<String>) () -> "A"` | Cast only to resolve ambiguity; avoid overuse. |

Method references are typically concise when the behavior is **literally a single existing call**. Lambdas are more readable when there are conditions, error handling, multiple steps, or input/output transformations. There is no rule that method references are always better than lambdas.

## 13. Self-check exercises

### Exercise 1

Why does this line not compile?

```java
var length = s -> s.length();
```

**Answer:** A lambda needs a target functional interface. `var` requires an initializer whose type the compiler can infer directly, but a lambda has no standalone type. Use `Function<String,Integer> length = s -> s.length();`.

### Exercise 2

What does `Function<String,Integer> f = String::length;` mean?

**Answer:** When `f.apply(text)` is called, the input String acts as the receiver of `length()`. The int result is boxed to Integer per the target.

### Exercise 3

Is `"pre-"::concat` a bound or unbound instance reference?

**Answer:** Bound; the receiver `"pre-"` is already known, and the functional interface accepts the string suffix to append. `Function<String,String>` is an appropriate target.

### Exercise 4

Why can `ArrayList::new` be assigned to `Supplier<ArrayList<String>>`?

**Answer:** Supplier takes no parameters and must return ArrayList<String>. The compiler chooses ArrayList's no-arg constructor to match the target.

### Exercise 5

Why is `choose(() -> "ok")` ambiguous if there are two overloads accepting `Supplier<String>` and `Callable<String>`?

**Answer:** Both interfaces have a zero-parameter SAM returning String (Callable also permits checked exceptions). The lambda fits both and neither candidate is more specific enough for the compiler to pick. Use a typed Supplier variable or a cast.

### Exercise 6

Is `BiFunction<String,String,String> f = (var a,b) -> a+b` valid?

**Answer:** No. You cannot mix `var` parameters with implicit parameters. Change it to `(var a,var b)` or `(a,b)`.

### Exercise 7

Why can `transform(List.of("A","Java"),String::length)` produce a List of Integer?

**Answer:** The compiler uses the source's type argument, the mapper's target functional interface, `length`'s int return type, and the result context to infer T/R; int is boxed into Integer.

### Exercise 8

Where does `Function<String,Integer> f = (Integer x) -> x + 1` fail?

**Answer:** The explicit parameter type Integer is incompatible with String required by the SAM. The compiler reports incompatible parameter types in lambda expression.

### Exercise 9

Can an overloaded static method `format(Object)` and `format(String)` be referenced via `Function<String,String>`?

**Answer:** Yes, as in section 7's example. The compiler selects the compatible and more specific String overload; output is `String:x`.

### Exercise 10

Can a lambda in `Function<String,String>` call a method throwing an unhandled checked IOException?

**Answer:** No, if the checked exception is not declared/permitted by the SAM. You must catch it, convert it in a controlled way, or use a functional interface with a compatible throws clause.

### Exercise 11

Why can `String::trim` not be assigned directly to `var operation`, yet it works as an argument in `transform(..., String::trim)`?

**Answer:** In the `var` assignment there is no functional target type. In the `transform` call, the generic signature of the mapper parameter provides the target type for the method reference.

### Exercise 12

When should you use `ToIntFunction<String>` instead of `Function<String,Integer>`?

**Answer:** When specialized int handling is needed to avoid boxing in an API and there is a performance or primitive-clarity reason. Both are valid for `String::length` with the corresponding target.

## 14. Summary

**Type inference for lambdas and method references is a target-context-driven process.** The functional interface determines parameter and result types; generic methods add T/R relationships; overload resolution decides which method can accept the expression. Therefore, the same lambda can be valid or invalid depending on where it is used, and the same overloaded method reference can bind differently depending on the target.

Prefer explicitly declared functional interfaces, generic signatures that express proper producer/consumer relationships, and typed intermediate variables when inference is ambiguous. Use `var` on lambda parameters properly, but do not mistake that for eliminating the need for a target type. When a method reference only makes a statement harder to read, writing a clear lambda is a good choice.

**Remember:** Before asking “what type does this lambda have?”, ask **“which functional interface is the compiler checking this lambda against?”**.