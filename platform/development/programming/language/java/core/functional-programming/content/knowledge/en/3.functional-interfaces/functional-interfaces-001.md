# Functional Interfaces and Single Abstract Methods in Java

## 1. What Is a Functional Interface?

A **functional interface** is an `interface` that has exactly **one abstract method that must be implemented** (*single abstract method*, often abbreviated as **SAM**) according to Java's method-counting rules. That method defines the signature that a lambda expression or method reference must implement.

A functional interface can have multiple `default`, `static`, and `private` methods with bodies, as well as declarations matching `public` methods of `Object`. Those methods do not introduce an additional SAM. `@FunctionalInterface` is an annotation that asks the compiler to verify the contract; it is **not a mandatory requirement** for an interface to be eligible for a lambda.

Short example:

~~~java
@FunctionalInterface
interface TextMapper {
    String map(String text);  // Single abstract method (SAM).

    default String mapInBrackets(String text) {
        return "[" + map(text) + "]";
    }
}
~~~

`map(String)` is the SAM. The `mapInBrackets` method has a body, so it does not count as a second abstract method. Therefore, `TextMapper mapper = s -> s.toUpperCase();` is valid in the target-type context of `TextMapper`.

**Significance:** a functional interface provides an explicit type contract for behavior that can be passed into methods, stored in variables, returned from methods, and combined with APIs such as Stream. A lambda is a **way of implementing** that contract, not the definition of the functional interface itself.

## 2. What Counts as a “Single Abstract Method”?

Consider the common forms of declarations:

| Member in the interface | Counted as a SAM? | Reason |
|---|---|---|
| `String convert(String s);` | **Yes** | Method without a body, requiring an implementation |
| `default String label() { return "x"; }` | No | Already has a default implementation |
| `static int version() { return 1; }` | No | Belongs to the interface itself, not an instance operation to implement |
| `private String helper() { return "x"; }` | No | Helper method with a body, allowed since Java 9 |
| `boolean equals(Object other);` | No, when equivalent to the `public Object.equals` declaration | `Object` methods are excluded from SAM counting by Java rules |
| Two abstract declarations with different signatures | Usually invalid | There is no longer a single abstract behavior |

**Subtlety regarding inheritance:** Java evaluates the set of abstract methods after accounting for inheritance, overriding, and signature compatibility. There can be multiple abstract *declarations* that still represent only one functional contract if those declarations are compatible and are satisfied together by a single method. Therefore, “one SAM” does not mean the source file must literally contain only one semicolon after a method declaration.

An interface that contains only `default` and `static` methods **without a SAM** is not a functional interface. Similarly, an interface that only redeclares `equals(Object)` without another abstract method does not become a functional interface either.

### 2.1. Why Are `Object.equals`, `hashCode`, and `toString` Treated Specially?

Every Java object participates in the `Object` contract. Abstract declarations in an interface whose signatures correspond to `public` methods of `Object`, such as `equals(Object)`, `hashCode()`, and `toString()`, are **not counted** when determining the SAM.

Example:

~~~java
@FunctionalInterface
interface IdentifiedAction {
    void perform();
    boolean equals(Object other);
    int hashCode();
    String toString();
}
~~~

The declaration above is valid: `perform()` is the behavior that the lambda must supply. The lambda does not take separate responsibility for the three `Object` methods. This mechanism also explains why `Comparator<T>` remains a functional interface even though it declares `equals(Object)`: the SAM of `Comparator` is `compare(T, T)`.

Be careful: you cannot use `default` in an interface to override a `public` method of `Object` such as `default String toString()`; the compiler rejects such a declaration.

### 2.2. Inheritance Does Not Necessarily Add Another SAM

Valid illustrative example:

~~~java
interface BaseAction {
    void run();
}

@FunctionalInterface
interface NamedAction extends BaseAction {
    @Override
    void run();

    default String name() {
        return "action";
    }
}
~~~

`NamedAction` redeclares the exact inherited `run()` contract; it does not create a different abstract function. Conversely, adding `void stop();` to `NamedAction` would cause this interface to no longer be a functional interface. The compiler will report an error because `@FunctionalInterface` requires a single SAM.

## 3. Complete Program: One SAM, Multiple Method Kinds

Save the following code as `FunctionalInterfaceDemo.java`:

~~~java
import java.util.Locale;

@FunctionalInterface
interface TextAction {
    String apply(String input); // Single SAM.

    // Matches a public Object method: not counted as a SAM.
    boolean equals(Object other);

    default String surround(String input) {
        return "[" + apply(input) + "]";
    }

    default String normalized(String input) {
        return apply(clean(input));
    }

    static TextAction identity() {
        return input -> input;
    }

    private static String clean(String input) {
        return input.trim();
    }
}

public class FunctionalInterfaceDemo {
    public static void main(String[] args) {
        TextAction upper = text -> text.toUpperCase(Locale.ROOT);
        TextAction trim = String::trim;

        System.out.println(upper.apply("java"));
        System.out.println(upper.surround("lambda"));
        System.out.println(upper.normalized("  hello  "));
        System.out.println(trim.apply("  JDK  "));
        System.out.println(TextAction.identity().apply("same"));
    }
}
~~~

With JDK 17 or later, run:

~~~bash
javac FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
~~~

Output:

~~~text
JAVA
[LAMBDA]
HELLO
JDK
same
~~~

Explanation of each part:

1. `TextAction.apply(String)` is the abstract method that the lambda and method reference must implement; the return type is `String`.
2. `upper` uses a lambda to convert a string to uppercase. `Locale.ROOT` makes the demonstration independent of the machine's default locale.
3. `trim` uses the method reference `String::trim`; Java matches it against the SAM `String apply(String)`. With one `String` argument, the corresponding operation invokes `trim()` on that argument.
4. `surround` and `normalized` are `default` methods that call back into the SAM `apply`. The same interface can have multiple default methods to provide reusable behavior.
5. `identity` is a `static` method that creates and returns a new `TextAction`; this method is not implemented by the caller's lambda.
6. `clean` is a `private static` method used inside the interface; it has a body and is not a SAM.
7. `equals(Object)` is a declaration matching `Object`, so it does not increase the SAM count to two.

`@FunctionalInterface` here helps catch changes that break the SAM contract early. If you add `String reverse(String text);` without providing a `default` body, `TextAction` is no longer valid and the code fails to compile.

## 4. Lambdas Require a *Target Type*

A lambda in Java **does not have an independent type of its own**; it needs a context that determines a functional interface. A lambda expression can appear in positions such as an assignment, a method argument, a return statement from a method, or an explicit cast.

~~~java
java.util.function.Function<String, Integer> length = s -> s.length();

java.util.function.Predicate<String> nonBlank =
        s -> s != null && !s.isBlank();

java.util.function.Consumer<String> print =
        text -> System.out.println(text);
~~~

The three examples above are **illustrative snippets placed inside a method**. The target types determine the number of parameters, parameter types, and return type:

- `Function<String, Integer>` has the SAM `Integer apply(String value)`. The lambda takes a `String` and returns an `Integer` (in the example, `int` is boxed).
- `Predicate<String>` has the SAM `boolean test(String value)`; the result must be compatible with `boolean`.
- `Consumer<String>` has the SAM `void accept(String value)`; it only performs an action and requires no return value.

A lambda such as `s -> s.length()` **cannot stand alone** in `var f = s -> s.length();`, because `var` must infer the type from the initializer expression and a lambda does not provide enough target type information in this case.

When calling an overloaded method that accepts multiple kinds of functional interfaces, the target type can also become ambiguous:

~~~java
// Snippet illustrating two overloads.
static void use(java.util.function.Supplier<String> supplier) {}
static void use(java.util.concurrent.Callable<String> callable) {}

// use(() -> "ok");  // Error: cannot select an overload from the lambda alone.
use((java.util.function.Supplier<String>) () -> "ok");
~~~

The last statement uses a cast to specify the functional interface explicitly. Each interface individually is valid; the error here comes from **overload resolution**, not from a missing SAM. The snippets in this section need to be placed inside proper class/method declarations and are not standalone runnable files.

## 5. Standard Functional Interfaces to Recognize

Instead of creating a new interface for every lambda, Java already provides many commonly used contracts.

| Standard type | SAM | Used when |
|---|---|---|
| `Runnable` | `void run()` | Performing work that returns no result |
| `Callable<V>` | `V call() throws Exception` | Work that returns a result and may throw a checked exception |
| `Supplier<T>` | `T get()` | Supplying or generating a value |
| `Consumer<T>` | `void accept(T value)` | Accepting a value and performing an action |
| `Function<T, R>` | `R apply(T value)` | Transforming a value of type `T` to `R` |
| `Predicate<T>` | `boolean test(T value)` | Testing a condition |
| `UnaryOperator<T>` | `T apply(T value)` | Transforming a value while keeping the same type |
| `BinaryOperator<T>` | `T apply(T a, T b)` | Combining two values of the same type into one value |
| `BiFunction<T, U, R>` | `R apply(T a, U b)` | Transforming from two inputs |
| `Comparator<T>` | `int compare(T a, T b)` | Defining the ordering of two values |

Some method names like `Function.apply`, `Predicate.test`, and `Consumer.accept` are easy to confuse because they can all take one parameter. Distinguish them by their **input/output contract** and actual purpose.

Specialized variants such as `IntPredicate`, `IntConsumer`, `IntUnaryOperator`, `ToIntFunction<T>`, and `LongSupplier` help work with primitive types and avoid unnecessary boxing/unboxing in many situations. This optimization matters when processing many elements or hot code paths; there is no need to choose a primitive type just because a lambda expression is used.

### Complete Example Using Multiple Standard Types

Save the file `StandardSamDemo.java`:

~~~java
import java.util.List;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Function;

public class StandardSamDemo {
    public static void main(String[] args) {
        IntUnaryOperator doubleIt = x -> x * 2;
        IntUnaryOperator plusThree = x -> x + 3;
        System.out.println(doubleIt.andThen(plusThree).applyAsInt(4));

        Predicate<String> hasText = s -> s != null && !s.isBlank();
        System.out.println(hasText.test(" "));

        Function<String, Integer> length = String::length;
        System.out.println(length.apply("Java"));

        List<String> words = List.of("aaa", "b", "cc");
        System.out.println(words.stream()
                .sorted((a, b) -> Integer.compare(a.length(), b.length()))
                .toList());
    }
}
~~~

Run:

~~~bash
javac StandardSamDemo.java
java StandardSamDemo
~~~

Output:

~~~text
11
false
4
[b, cc, aaa]
~~~

- `IntUnaryOperator.andThen` is a `default` method that provides a way to compose two transformations without adding another SAM; for `4`: doubling gives `8`, then adding `3` gives `11`.
- `Predicate.test` evaluates a string containing only spaces as `false`.
- `String::length` is assigned to `Function<String, Integer>`; `length()` returns `int`, and the result is boxed into `Integer` according to the contract.
- The `sorted` method takes `Comparator<? super String>`; the lambda has two parameters and returns a negative/0/positive number to indicate ordering by length.

## 6. Why Should the `@FunctionalInterface` Annotation Be Used?

If an interface has exactly one SAM, Java allows assigning a lambda **even without the annotation**. However, `@FunctionalInterface` should be applied when the author **intentionally exposes a functional contract**:

~~~java
@FunctionalInterface
interface PriceRule {
    long calculate(long base);
}
~~~

The annotation is a compile-time check constraint. For example, if you edit the interface above to add `long tax(long base);` as an abstract method, the compiler reports that `PriceRule` is no longer a functional interface. This is useful because code already using `PriceRule` as a lambda target type depends on that SAM property.

The annotation **does not** make code run faster, does not generate methods, does not enforce purity, and does not forbid `default`/`static` methods. An interface is a functional interface based on the language definition; the annotation merely states the intent and asks the compiler to verify that intent.

### Case with a Compile Error

~~~java
// Error illustration: do not put this in the same runnable example file.
@FunctionalInterface
interface InvalidService {
    void start();
    void stop();
}
~~~

Because `start()` and `stop()` are two abstract behaviors with different signatures, there is no single SAM. Removing `@FunctionalInterface` would allow defining a regular interface, but it **does not** turn it into a target type for lambdas.

Another invalid case:

~~~java
// Error illustration: this interface has no SAM.
@FunctionalInterface
interface DefaultsOnly {
    default void execute() {}
    static void version() {}
}
~~~

Do not count the number of methods written in a file or the number of `;` characters. Determine accurately which method remains as the **abstract contract** that an implementer must provide.

## 7. Details That Help Understand the SAM Contract Correctly

### 7.1. The Lambda Must Match Parameters and Return Type

The SAM determines the number of parameters; a lambda can be written as `(a, b) -> ...` or `a -> ...` depending on the count. For a SAM returning `void`, the lambda body must be compatible with a `void` context; for a SAM returning a value, the expression or return branches must match the result type.

~~~java
Runnable task = () -> System.out.println("done");
java.util.function.BinaryOperator<Integer> sum = (a, b) -> a + b;
java.util.function.Predicate<Integer> even = x -> x % 2 == 0;
~~~

`Runnable` has no parameters; `BinaryOperator<Integer>` has two parameters and returns `Integer`; `Predicate<Integer>` has one parameter and returns `boolean`. These examples are snippets to place inside a method.

### 7.2. Checked Exceptions Are Part of the SAM Contract

If the abstract method declares `throws IOException`, the lambda may throw a corresponding `IOException`; if the SAM does not declare a compatible checked exception, you cannot arbitrarily let it escape the lambda without handling it.

~~~java
@FunctionalInterface
interface ReaderAction {
    String read(String path) throws java.io.IOException;
}
~~~

`ReaderAction loader = path -> java.nio.file.Files.readString(java.nio.file.Path.of(path));` can be valid because `read` declares `throws IOException`. Conversely, you cannot directly assign that lambda to `Function<String, String>` if the lambda lets the checked exception `IOException` escape unhandled. This is a difference in the **method contract**, not in lambda syntax.

### 7.3. Captured Variables Must Be `final` or Effectively Final

A lambda is allowed to use local variables from the enclosing scope when those variables are `final` or **effectively final** (not reassigned after initialization).

~~~java
int factor = 3;
java.util.function.IntUnaryOperator multiply = x -> x * factor;
~~~

If you later reassign `factor = 4;` in the same method, the lambda is no longer valid because `factor` is not effectively final. However, that **does not mean** the captured object is always immutable:

~~~java
java.util.List<String> captured = new java.util.ArrayList<>();
java.util.function.Consumer<String> addItem = item -> captured.add(item);
~~~

The variable `captured` is not reassigned; the lambda still mutates the contents of the list. Being able to assign a lambda to a functional interface does not automatically guarantee purity, thread-safety, or absence of side effects.

### 7.4. Understanding Inheritance, Generics, and Intersecting Interfaces

- A functional interface can be declared with generics, for example `interface Mapper<T, R> { R map(T value); }`. The type `Mapper<String, Integer>` defines a SAM taking `String` and returning `Integer`.
- A subinterface inheriting a single abstract contract can continue to be a functional interface; additional `default` methods are still permitted.
- If multiple abstract methods are inherited with matching signatures and compatible return types, Java can treat them as representing a single contract together. Incompatible signatures or return types can make the interface invalid or no longer a functional interface.
- Do not predict validity merely from the number of lines in an `interface`; let `@FunctionalInterface` and the compiler verify complex inheritance cases.

### 7.5. Lambdas Differ from Anonymous Classes in `this` Context

A lambda does not create its own `this` scope the way an anonymous class does. Inside a lambda, `this` (if valid) refers to the enclosing object; inside an anonymous class, `this` refers to the anonymous class instance. A lambda also does not create a separate subclass for the interface like writing `new SomeInterface() { ... }`. When code needs per-behavior instance state, a concrete implementation class or anonymous class may express the intent more clearly.

## 8. When Should You Define Your Own Functional Interface?

**Prefer standard types** when the contract simply matches `Function`, `Predicate`, `Consumer`, `Supplier`, etc. For instance, an operation converting a string to a number can use `Function<String, Integer>`; creating `interface StringToNumber { int convert(String s); }` just to pass a lambda is usually unnecessary.

**Define a custom SAM interface** when domain naming, checked exceptions, special signatures, or supporting `default` methods make the contract clearer:

~~~java
@FunctionalInterface
interface RetryDecision {
    boolean shouldRetry(int attempt, Throwable failure);
}
~~~

The name `RetryDecision` and parameters `attempt`, `failure` describe the meaning more clearly than a generic `BiPredicate<Integer, Throwable>`. You can pass a lambda `(attempt, failure) -> attempt < 3`, while the actual retry decision logic must still align with business policies, limits, and real error types. This interface is a **behavioral contract**; whether the decision is pure depends on the implementation.

In public APIs, a specialized interface also makes it easy to add related `default` methods while preserving the SAM. However, changing the SAM signature can break existing lambdas and method references using that API; consider compatibility when releasing libraries.

## 9. Common Mistakes When Learning Functional Interfaces

1. **Assuming `@FunctionalInterface` is required to use a lambda.** In reality, the interface only needs to satisfy the SAM rule. The annotation helps protect intent.
2. **Assuming there can only be one method in total.** `default`, `static`, and `private` methods with bodies are not counted; certain `Object`-equivalent methods are not counted either.
3. **Assuming two abstract declarations always mean two SAMs.** If they form a single contract under overriding rules, it may still be a functional interface. For complex inheritance, rely on the compiler.
4. **Adding a new abstract method to an API already used with lambdas.** This breaks the SAM property and causes compile errors at call sites.
5. **Confusing the functional type with the lambda.** The target type is the functional interface; the lambda provides the implementation of the SAM.
6. **Confusing a method reference with a different kind of API.** `String::trim` is not a functional interface; it is an expression referencing a method that is assigned based on a compatible target type.
7. **Ignoring the SAM's checked exceptions.** A lambda performing I/O may need an interface declaring `throws`, or must handle the error itself.
8. **Guessing the lambda type in every expression.** Overloads with multiple possible target types can be ambiguous; use a typed variable or an explicit cast.
9. **Assuming a lambda is inherently pure and safe to run in parallel.** A lambda can still mutate captured data or perform I/O; that is a behavioral concern, not a criterion for defining a SAM.

## 10. Checklist and Self-Check Questions

When you see an interface intended for use with lambdas, ask yourself:

- After accounting for inheritance and excluding non-counted methods, **which SAM** is the actual contract?
- What are the parameter count/types, return type, and `throws` clause of the SAM?
- Which `default` methods can support common operations while keeping a single SAM?
- Should `@FunctionalInterface` be added to safeguard the contract during maintenance?
- Is a standard type already expressive enough, or is a dedicated domain name needed?
- Does the lambda or method reference at the use site match the target type, and are there any side effects to note?

**Mini-exercise:** State whether each of the following interfaces can accept a lambda, and explain why:

~~~java
interface A {
    void execute();
}

interface B {
    void execute();
    default void reset() {}
}

interface C {
    void execute();
    int status();
}

interface D {
    String toString();
    int hashCode();
    void execute();
}
~~~

**Answer:** `A` has the SAM `execute()`; `B` also has the SAM `execute()` because `reset()` is `default`; `C` has two distinct abstract methods so it cannot accept a lambda; `D` has the SAM `execute()` because `toString()` and `hashCode()` match `public` methods of `Object` and are not counted.

**Takeaway:** A functional interface is identified by its **single abstract contract after applying the language rules**, not by the number of methods visible in the source file. `@FunctionalInterface` confirms intent, while a lambda/method reference supplies behavior for the SAM in a target-type context.