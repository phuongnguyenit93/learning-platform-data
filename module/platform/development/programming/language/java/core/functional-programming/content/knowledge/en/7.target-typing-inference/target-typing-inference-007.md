# Overloading Methods That Accept Lambdas and Ambiguous Calls in Java

## 1. The Problem: One Lambda, Multiple Overloads That All Seem to Match

Java allows **method overloading**: multiple methods with the same name but different parameter lists. When an argument is an ordinary value with an explicit type, the compiler usually selects an overload based on the argument's type and compatibility rules. With a **lambda**, selection can be more complex because a lambda is a **poly expression**: it needs a functional interface **target type** before it can be fully type-checked.

Example of two overloads accepting two unrelated interfaces:

~~~java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class Example {
    static void choose(Supplier<String> supplier) {}
    static void choose(Callable<String> callable) {}

    void demonstrate() {
        // COMPILE ERROR: both overloads can accept () -> "hello".
        // choose(() -> "hello");
    }
}
~~~

Both `Supplier<String>` and `Callable<String>` have an abstract method taking **no arguments and returning `String`**. When calling `choose(() -> "hello")`, the lambda is compatible with both and neither overload is uniquely preferred; `javac` reports *reference to choose is ambiguous*.

**Key takeaway:** a lambda does not have a standalone type like `String` or `int` for the compiler to always know in advance which overload a call must pick. The compiler examines the candidate methods, the functional interface signatures, lambda compatibility, and then applies the **most specific method** selection rules. If there is no single best method, the call is ambiguous and rejected **at compile time**.

This lesson analyzes how overload selection works, why two interfaces of the same "shape" easily cause ambiguity, when the lambda body helps disambiguate, and how to write clear APIs and call sites.

## 2. Three Concepts to Keep Separate

| Concept | Meaning | Example |
| --- | --- | --- |
| **Overloading** | Multiple methods with the same name but different parameter lists | `run(Runnable)` and `run(Supplier<Integer>)` |
| **Functional interface** | An interface meeting the single abstract method contract to serve as a target type | `Supplier<T>`, `Callable<T>`, `Function<T,R>` |
| **Target typing** | The context determining which functional interface a lambda/method reference must match | `Supplier<String> x = () -> "ok";` |

A lambda is not an instance of `Function`, `Supplier`, or `Callable` before the target type is known. The same syntax can be used with different compatible interfaces:

~~~java
java.util.function.Supplier<String> supplier = () -> "ok";
java.util.concurrent.Callable<String> callable = () -> "ok";
~~~

Both declarations are valid; they create values with **different declared types**. In an overloaded call, passing `() -> "ok"` directly provides no variable declaration to state which kind is wanted.

### 2.1. Differing Only by Parameter Names Is Not Overloading

Two methods with the exact same name and parameter type list cannot coexist merely because parameter names differ:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
// void use(Supplier<String> first) {}
// void use(Supplier<String> second) {}
~~~

Similarly, you cannot merely change generic type arguments to create two overloads with the same erasure:

~~~java
// INTENTIONALLY DOES NOT COMPILE DUE TO NAME CLASH AFTER TYPE ERASURE:
// void use(Supplier<String> supplier) {}
// void use(Supplier<Integer> supplier) {}
~~~

Use two separate method names, a clearly distinguishing argument, or change the design if two different behaviors are needed. **Invalid overload declarations** are different from **two valid overloads where a call is ambiguous**.

## 3. Conceptual Order of Compiler Method Selection

In practical terms, picture four steps:

1. **Identify potentially applicable overloads:** method name, accessibility, argument count, arity/varargs, and related type conditions.
2. **Check lambda compatibility against each candidate target type:** lambda parameter count, parameter types if explicitly declared, whether the lambda body fits a `void` or value return, and other type conditions.
3. **Select the most specific overload per JLS rules:** one overload can take precedence over another because its parameter type is a subtype or due to special rules for functional target types in certain contexts.
4. **If there is no unique best candidate:** report an *ambiguous method call* error, requiring the author to clarify.

This is an explanatory model; the exact algorithm in JLS §15.12 consists of phases for finding applicable methods and checking *most-specific*, with specific details for overloads, generics, varargs, and poly expressions. Do not treat the outline above as a custom algorithm replacing the specification.

**Specifically:** the compiler does not "test-run the lambda" to see what it returns. It analyzes syntax, types, and expression constraints; which overload is called is decided **before the program runs**.

## 4. The Classic Ambiguity: `Supplier` and `Callable`

These two interfaces both take **zero arguments** and return a result, but have different API meanings:

- `Supplier<T>` has `T get()`, declaring no general checked exception.
- `Callable<V>` has `V call() throws Exception`, commonly used for tasks producing a result in an execution environment.

With two overloads like these:

~~~java
static String source(java.util.function.Supplier<String> supplier) {
    return "Supplier=" + supplier.get();
}

static String source(java.util.concurrent.Callable<String> callable)
        throws Exception {
    return "Callable=" + callable.call();
}
~~~

The following call **intentionally fails to compile**:

~~~java
// System.out.println(source(() -> "hello"));
// ERROR: both source(Supplier<String>) and source(Callable<String>) match.
~~~

You cannot rely on `Callable.call()` declaring `throws Exception` to claim the compiler must prefer `Supplier`. When the lambda throws no checked exceptions, both are still applicable.

### 4.1. Fix 1: Cast the Lambda at the Call Site

~~~java
System.out.println(source(
        (java.util.function.Supplier<String>) () -> "hello"));

System.out.println(source(
        (java.util.concurrent.Callable<String>) () -> "hello"));
~~~

Then the compiler knows the exact target type to use. This cast **does not convert an already-created object to a random interface**; it supplies the target type for checking and converting the lambda.

### 4.2. Fix 2: Declare a Typed Variable First

~~~java
java.util.function.Supplier<String> supplier = () -> "hello";
java.util.concurrent.Callable<String> callable = () -> "hello";

System.out.println(source(supplier));
System.out.println(source(callable));
~~~

The variable type is a clear signal, useful when the callback is reused or needs a domain name.

### 4.3. Fix 3: Name Methods by Contract

If you control the API design and the two overloads genuinely mean different things, separate names such as `fromSupplier(...)` and `fromCallable(...)` can spare every caller from casting while making the checked-exception contract clearer. This is usually the most readable option for public APIs that frequently accept lambdas.

## 5. Value-Returning vs. `void` Lambdas: Avoid Jumping to Conclusions from `->`

An important case is overloading with `Consumer<T>` and `Function<T,R>`:

~~~java
static String transform(java.util.function.Consumer<String> action) {
    action.accept("abcd");
    return "Consumer";
}

static String transform(java.util.function.Function<String, Integer> mapper) {
    return "Function=" + mapper.apply("abcd");
}
~~~

The following **ambiguous** call was verified with Java 17:

~~~java
// COMPILE ERROR: both overloads are compatible.
// transform(s -> s.length());
~~~

Because `s.length()` is a **method invocation expression**, it belongs to the *statement expression* category. Java allows an expression-bodied lambda containing a statement expression to be interpreted under a `void` contract, even when the method call itself returns a value. At the same time, it is also compatible with a value-returning functional interface.

**Therefore, never assert** "`s -> s.length()` returns `int`, so the compiler will definitely choose `Function`." In this overload pair, both `Consumer<String>` and `Function<String,Integer>` are compatible and there is no unique choice.

Conversely, an arithmetic expression that is not a *statement expression* does not automatically become a `void`-compatible body. Compatibility also depends on context; use a block when you want to be explicit.

### 5.1. Disambiguating with a Block Body

When the body has a `return expression;`, it expresses a result for a non-`void` functional interface:

~~~java
System.out.println(transform((String s) -> {
    return s.length();
}));
// Function=4
~~~

When the body executes a statement and completes normally, it matches a `void` contract:

~~~java
System.out.println(transform((String s) -> {
    s.length();
}));
// Consumer
~~~

The second snippet is only for **testing overload rules**, since calling `length()` and discarding the result is not a meaningful business operation. In real code, use a clear action such as logging, recording, or calling a `void`-returning method.

### 5.2. Disambiguating with a Cast or Variable

~~~java
System.out.println(transform(
        (java.util.function.Function<String,Integer>) s -> s.length()));
// Function=4

System.out.println(transform(
        (java.util.function.Consumer<String>) s -> s.length()));
// Consumer
~~~

In the `Consumer` line, the `int` value from `String.length()` is discarded under statement-expression semantics. Both **compile** in Java 17. If the real intent is to compute length, the `Function` or `ToIntFunction<String>` version (if the API accepts it) is clearer.

## 6. Non-Ambiguous Cases: The Lambda Shape Fits Only One Overload

Having multiple overloads that accept functional interfaces does not always mean ambiguity.

For example:

~~~java
static String action(Runnable work) {
    work.run();
    return "Runnable";
}

static String action(java.util.function.Supplier<Integer> supplier) {
    return "Supplier=" + supplier.get();
}
~~~

Calls:

~~~java
System.out.println(action(() -> 42)); 
// Supplier=42

System.out.println(action(() -> System.out.print("run ")));
// Prints "run " then "Runnable".
~~~

**Explanation:**

- `() -> 42` has a numeric literal as its expression body, which is **not** a statement expression. It fits a value-returning function and does not fit `Runnable.run(): void`.
- `() -> System.out.print("run ")` calls a method that actually returns `void`. It fits `Runnable` and does not return an `Integer` for `Supplier<Integer>`.
- These outcomes are due to **body shape and target types**, not because the compiler prefers one interface name by default.

For block lambdas, look at whether all execution paths return a value. A body like `{ return 42; }` is compatible with a value-returning function; a body like `{ System.out.println("x"); }` completes normally and is compatible with a `void` function. Bodies with more complex expressions/statements follow the specific rules of JLS §15.27.2; you cannot just count `return` statements and guess.

## 7. Most Specific: When One Interface Is a Subtype of Another

Sometimes both overloads can accept the lambda, yet Java still has a unique choice.

For example:

~~~java
static String prefer(java.util.function.Function<String, String> f) {
    return "Function";
}

static String prefer(java.util.function.UnaryOperator<String> f) {
    return "UnaryOperator";
}
~~~

`UnaryOperator<String>` extends `Function<String,String>`. When called:

~~~java
System.out.println(prefer(s -> s.trim()));
// UnaryOperator
~~~

The compiler selects the overload taking `UnaryOperator<String>` because that parameter type is **more specific** than `Function<String,String>` in the inheritance hierarchy. This differs from `Supplier` and `Callable`: those two interfaces have no subtyping relationship to break the tie.

**Note:** "more specific" is a concept defined by the overload specification, not merely "this interface extends that interface." The JLS has additional rules for most-specific functional interfaces, especially involving primitive/reference return types, explicit/implicit lambdas, and generics. For tricky cases, verify with `javac --release 17` or the project's exact `javac` version.

## 8. Implicit Lambdas, Explicitly Typed Lambdas, Method References, and Inference

### 8.1. Writing Explicit Parameter Types Can Add Constraints

For example, `x -> ...` does not have a concrete type for `x` when target typing begins. With `(String x) -> ...`, the `String` type written in the lambda rules out overloads that require a different parameter type.

However, **writing explicit parameter types is not a cure-all for every ambiguous call**. In the `Supplier<String>` and `Callable<String>` example, the lambda takes no parameters; writing `() -> "x"` adds no information to distinguish the two interfaces. With two overloads that both take `String` and can handle the body, writing `(String s) -> s.length()` is still not enough.

### 8.2. Method References Are Also Checked Against the Target Type

The syntax `String::trim` does not decide on its own whether it is `Function<String,String>` or `Consumer<String>`; each API context can have its own selection rules. **Do not assume from a lambda overload outcome that every method reference behaves identically.**

For this exact overload pair:

~~~java
static String pick(java.util.function.Consumer<String> action) {
    return "Consumer";
}

static String pick(java.util.function.Function<String, String> mapper) {
    return "Function";
}
~~~

In Java 17, calling `pick(String::trim)` **compiles** and selects the `Function<String,String>` overload (returning `"Function"`). This is an example showing that *exact method references* and most-specific rules do not always behave identically to lambda expressions like `s -> s.trim()`. Check each signature pair and each call form.

### 8.3. A Lambda Without a Target Type Cannot Be Assigned to `var`

~~~java
// COMPILE ERROR: no target type for the lambda.
// var task = () -> "hello";
~~~

Use an explicit functional interface type:

~~~java
java.util.function.Supplier<String> task = () -> "hello";
~~~

Or cast when passing the lambda into an overload. The cast operator is not only for "casting a result" at runtime; it can specify the target functional interface before the compiler checks the lambda.

### 8.4. The Return Type of an Overloaded Method Is Not Always Enough to Pick an Overload

Do not assume the type of the variable receiving the result will pick an overload by its return type. Java does not allow overloading **by return type alone**; in most ordinary overloaded calls, resolution is based first on argument types and shapes. Generic/poly-expression contexts have specific inference interactions, but you should not rely on result assignment to fix an ambiguous lambda once the compiler reports ambiguity.

## 9. Complete Java 17 Program with Verified Output

Create the file **OverloadDemo.java**. The ambiguous calls are shown separately in Section 10 as **intentionally non-compiling** code; this program contains only valid calls so it can run standalone.

~~~java
import java.util.concurrent.Callable;
import java.util.function.*;

public class OverloadDemo {
    static String source(Supplier<String> job) {
        return "Supplier=" + job.get();
    }

    static String source(Callable<String> job) throws Exception {
        return "Callable=" + job.call();
    }

    static String action(Runnable run) {
        run.run();
        return "Runnable";
    }

    static String action(Supplier<Integer> get) {
        return "Supplier=" + get.get();
    }

    static String transform(Consumer<String> use) {
        use.accept("abcd");
        return "Consumer";
    }

    static String transform(Function<String,Integer> use) {
        return "Function=" + use.apply("abcd");
    }

    static String prefer(Function<String,String> f) {
        return "Function";
    }

    static String prefer(UnaryOperator<String> f) {
        return "UnaryOperator";
    }

    public static void main(String[] args) throws Exception {
        System.out.println(source((Supplier<String>) () -> "hello"));
        System.out.println(source((Callable<String>) () -> "hello"));
        System.out.println(action(() -> 42));
        System.out.println(action(() -> System.out.print("run ")));
        System.out.println(transform((String s) -> {
            return s.length();
        }));
        System.out.println(transform((String s) -> {
            s.length();
        }));
        System.out.println(prefer(s -> s.trim()));
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac --release 17 OverloadDemo.java
java OverloadDemo
~~~

Verified **exact** stdout:

~~~text
Supplier=hello
Callable=hello
Supplier=42
run Runnable
Function=4
Consumer
UnaryOperator
~~~

The line `run Runnable` appears because `System.out.print("run ")` does not add a newline, and then `System.out.println(action(...))` prints `Runnable` with a newline.

The remaining lines demonstrate:
- Casts distinguish the two `source` overloads.
- The literal body `42` selects `Supplier<Integer>`; the `void`-returning `print` body selects `Runnable`.
- A block with `return s.length();` selects `Function<String,Integer>`.
- A block that only calls `s.length();` and completes normally selects `Consumer<String>`.
- The `UnaryOperator<String>` overload is more specific than `Function<String,String>`.

## 10. Intentional Compile-Error Examples and Diagnosis

### 10.1. Two Unrelated Interfaces Both Accepting a No-Arg Lambda

Example file **AmbiguousSource.java** (intentionally erroneous):

~~~java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

class AmbiguousSource {
    static void pick(Supplier<String> s) {}
    static void pick(Callable<String> c) {}
    void bad() {
        pick(() -> "hello"); // ambiguous
    }
}
~~~

Compiling with `javac --release 17 AmbiguousSource.java` fails with the message: `reference to pick is ambiguous`, because both `pick(Supplier<String>)` and `pick(Callable<String>)` match.

### 10.2. A Method Invocation Expression Compatible with Both `void` and a Value

Example file **AmbiguousTransform.java** (intentionally erroneous):

~~~java
import java.util.function.*;

class AmbiguousTransform {
    static void pick(Consumer<String> c) {}
    static void pick(Function<String, Integer> f) {}
    void bad() {
        pick(s -> s.length()); // ambiguous
    }
}
~~~

Compiling with `javac --release 17 AmbiguousTransform.java` also fails with `reference to pick is ambiguous`. This is an easy-to-misunderstand case, because `String.length()` itself returns `int`, yet a method invocation expression is still a void-compatible body form.

**When you hit an error:** read all signatures listed by the compiler, inspect each parameter's SAM type, check whether the lambda body fits more than one type, and then disambiguate using a typed variable, a cast, a block, or an API redesign.

Do not try to "fix" it by randomly casting the lambda's result: `s -> (int) s.length()` can still be an expression-bodied lambda containing a cast expression rather than a statement expression; if you need to control overload selection intentionally, use an explicit form and verify with the compiler.

## 11. Guidelines for Designing APIs That Accept Multiple Callbacks

Overloading with functional interfaces is reasonable when the types represent genuinely distinct choices, but it easily causes trouble when unrelated interfaces share the same function descriptor.

**Prefer these approaches:**

1. **Name by function** when semantics differ: `executeTask(Callable<T>)` and `supplyValue(Supplier<T>)` are clearer than two nearly identical `run(...)` overloads.
2. **If keeping overloads, document unambiguous call-site examples**: casts or typed callback declarations.
3. **Avoid APIs that force frequent casts for common lambdas.** If every user has to write `(Supplier<T>) () -> ...`, that is often a sign the API name is hiding semantic differences.
4. **Do not create overloads differing only in generic type arguments with the same erasure.** Java does not allow declaration pairs like `use(Supplier<String>)` and `use(Supplier<Integer>)`.
5. **Consider checked exceptions and actual lifecycle.** `Callable<T>` can throw checked exceptions, while `Supplier<T>` by standard contract declares no checked exceptions; choosing the interface affects how callers handle errors.
6. **Test against the exact target Java version.** For complex lambda/overload cases, intuition is not enough; the compiler is the closest authority to your project's language version.

Naming callbacks clearly also matters:

~~~java
Supplier<String> defaultName = () -> "Guest";
Callable<String> queryName = () -> "Guest";
~~~

Even though both lambdas have the same body, clearly named and typed variables help reviewers see whether an immediate value is being supplied or a callable task is being represented.

## 12. Real-World Scenarios: Builders, Async APIs, and Stream Processing

Suppose an API provides both:
- A method to obtain a default value when needed.
- A method to run a task that may throw checked exceptions.

If both are named `execute(...)` and accept no-arg callbacks returning data, the shortest lambda call `execute(() -> compute())` easily becomes ambiguous. Two names like `supplyFallback(...)` and `callTask(...)` express the contracts clearly.

In the Stream API, calls rarely run into this issue because steps have distinct semantic names: `filter(Predicate)`, `map(Function)`, `forEach(Consumer)`. When writing similar APIs yourself, naming by operation helps limit overloads with identical SAM shapes.

For builders with multiple overloads like `onSuccess(Consumer<T>)` and `onSuccess(Function<T,R>)`, a callback like `x -> logAndReturn(x)` can be a value-returning statement expression, leading to hard-to-predict selection interactions. Splitting into names like `observeSuccess(...)` and `transformSuccess(...)` or requiring explicitly typed callbacks will help users more.

## 13. Checklist for Resolving Ambiguous Calls

When the compiler reports `reference to ... is ambiguous`:

1. **Read the overload signatures** listed by the compiler: how many arguments, parameter types, and subtype relationships between types.
2. **Inspect the function descriptor of each interface**: arity, parameter types, return type, checked exceptions.
3. **Inspect the lambda form:** expression body or block body; statement expression, literal, or block with `return`.
4. **Check the target type** of the lambda and validity against each candidate. Do not assume the lambda already has an independent type.
5. **Disambiguate intentionally:** cast the lambda to the desired interface, declare a typed callback variable, or write a block that makes `void`/value behavior explicit.
6. **If this is an API you design:** consider distinct method names rather than forcing many callers to write casts.
7. **Run `javac --release 17`** on a minimal example when it is hardest to determine, and only put results in documentation after verification.

## 14. Self-Check Questions

**Question 1.** Two overloads `accept(Supplier<String>)` and `accept(Callable<String>)` receive `accept(() -> "ok")`. What is the result?

**Answer:** ambiguous; the two types are unrelated by inheritance yet both are compatible with a no-arg lambda returning `String`. To select one, declare a type/cast or change the API.

**Question 2.** Why can both `Consumer<String>` and `Function<String,Integer>` match `s -> s.length()`?

**Answer:** `s.length()` is a method invocation statement expression so it can be a void-compatible body; at the same time it returns `int` and can be a value-compatible body.

**Question 3.** Given the overload pair `run(Runnable)` and `run(Supplier<Integer>)`, which does `run(() -> 10)` select?

**Answer:** `Supplier<Integer>`; the literal `10` is not a statement expression and therefore cannot form a void-compatible body.

**Question 4.** Given the overloads `choose(Function<String,String>)` and `choose(UnaryOperator<String>)`, why does `s -> s.trim()` have a single choice?

**Answer:** `UnaryOperator<String>` is a subtype of `Function<String,String>` and is therefore the more specific overload in this pair.

**Question 5.** Why does `var fn = () -> "hi";` not solve overload selection?

**Answer:** a lambda needs a target type; `var` does not provide a concrete functional interface to infer from this lambda initializer.

**Question 6.** An API has multiple callbacks named `execute` and the compiler frequently reports ambiguity; what should you do?

**Answer:** clarify the use cases with contract-based method names, or supply an explicit callback variable/cast at the call site; avoid forcing users to guess overloads.

## References

- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12).
- [JLS 17, §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27).
- [JLS 17, §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13).
- [JLS 17, §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).
- [JLS 17, §8.4.2 — Method Signature and Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2).

**Remember:** Overloading with lambdas requires evaluating **the target type of each functional interface**, **the shape and compatibility of the lambda**, and then applying **most-specific** rules. Two compatible overloads do not mean the compiler will guess the programmer's intent. When there is no unique candidate, use explicit types or design APIs with names that express their meaning, and verify tricky cases with the compiler.