# Higher-Order Functions in Java: Accepting or Returning Functions

## 1. Objectives and Core Idea

A **higher-order function** is a function that has at least one of two characteristics: **accepting a function as an argument** or **returning a function**. As a result, we can separate the fixed processing logic from the behavior that varies by situation.

In Java, methods do not have a separate "free function" type like in some other languages. Instead, you pass or return an object whose type is a **functional interface**: an interface with exactly one abstract method, such as `Function<T, R>` or `Predicate<T>`. Lambda expressions (`x -> ...`) and method references (`String::length`) help create values that match such an interface.

After this lesson, you can:
- Identify higher-order methods and distinguish them from regular method calls.
- Write methods that accept `Function`, `Predicate`, or other appropriate functional interfaces.
- Write methods that return lambdas, and understand captured variables and when the function is executed.
- Compose functions using `compose` and `andThen`, use generic types properly, and avoid common pitfalls.

## 2. Why Do We Need Higher-Order Functions?

Suppose a program needs to process many lists: sometimes converting strings to their lengths, sometimes normalizing text, and sometimes selecting elements based on a condition. If each variation has an almost identical loop, the code repeats the traversal structure and becomes hard to extend.

Higher-order functions allow you to **keep the traversal mechanism unchanged and turn the rule into a parameter**:

- Fixed part: retrieving each element and collecting the results.
- Variable part: transforming elements with `Function` or checking conditions with `Predicate`.
- The call site decides the rule using a lambda, a method reference, or an object implementing the functional interface.

This is the foundation of `Stream.map`, `Stream.filter`, `Optional.map`, `Comparator.comparing`, and many modern Java APIs. Those APIs **accept behavior** to execute at the time they are designed to.

## 3. How Does Java Represent "Functions as Values"?

| Interface in `java.util.function` | Primary Method | Meaning |
| --- | --- | --- |
| `Function<T, R>` | `R apply(T value)` | One input, produces one result |
| `UnaryOperator<T>` | `T apply(T value)` | Special case of `Function<T, T>` |
| `Predicate<T>` | `boolean test(T value)` | Checks a condition |
| `Consumer<T>` | `void accept(T value)` | Accepts a value and performs an action |
| `Supplier<T>` | `T get()` | Supplies a value, takes no arguments |
| `BiFunction<T, U, R>` | `R apply(T first, U second)` | Two inputs, one result |
| `IntUnaryOperator` | `int applyAsInt(int value)` | Specialized variant for `int`, avoiding boxing |

A lambda must have a **target type** that is a functional interface:

```java
Function<String, Integer> length = text -> text.length();
Predicate<String> nonBlank = text -> !text.isBlank();

int size = length.apply("Java");       // 4
boolean ok = nonBlank.test(" Java ");  // true
```

The snippet above illustrates expressions placed inside the body of an existing method; you can add `import java.util.function.Function;` and `import java.util.function.Predicate;` to use them. **Creating** `length` does not invoke `text.length()` yet: the behavior executes when `apply` is called. A lambda is not automatically a pure function; it can still read/write state or cause side effects.

You can also declare your own interface with `@FunctionalInterface` when a specialized contract is needed. However, prefer standard interfaces when they already express the inputs and outputs accurately.

## 4. Accepting Functions as Parameters: A Runnable Program

The example below has two higher-order methods:

- `map` **accepts** a `Function` transformation rule and applies it to every element.
- `filter` **accepts** a `Predicate` condition and keeps elements that satisfy the condition.

Save to the file `HigherOrderDemo.java`:

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class HigherOrderDemo {
    static <T, R> List<R> map(
            List<T> items,
            Function<? super T, ? extends R> rule) {
        return items.stream().<R>map(rule).toList();
    }

    static <T> List<T> filter(
            List<T> items,
            Predicate<? super T> condition) {
        return items.stream().filter(condition).toList();
    }

    static Function<String, String> prefixWith(String prefix) {
        return value -> prefix + value;
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        System.out.println(map(names, String::length));
        System.out.println(filter(names, name -> name.length() >= 4));

        Function<String, String> label = prefixWith("Bạn: ");
        System.out.println(label.apply("Lan"));

        Function<String, String> trim = String::trim;
        Function<String, Integer> length = String::length;
        System.out.println(trim.andThen(length).apply("  Java  "));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac HigherOrderDemo.java
java HigherOrderDemo
```

Expected output:

```text
[2, 4, 3]
[Binh]
Bạn: Lan
4
```

**Execution flow analysis:**

1. `map(names, String::length)` passes the "measure length" behavior into the traversal method. `String::length` is a method reference to the received `String` object, equivalent to `name -> name.length()`.
2. `filter(names, name -> name.length() >= 4)` provides the filtering rule at the call site. Only `"Binh"` is at least four characters long.
3. `prefixWith("Bạn: ")` **returns a function**. The variable `label` holds the created function; only `label.apply("Lan")` runs the string concatenation.
4. `trim.andThen(length)` creates a composed function: first it trims leading/trailing whitespace, then it counts characters. `"Java"` has a length of four.

`Stream.toList()` has been available since Java 16 and returns an unmodifiable list. This example uses Java 17+ as stated.

## 5. Returning Functions: Creating Configured Behavior

Methods that return a functional interface are useful when you need to create a **pre-configured rule** and reuse it in multiple places. For example, from an addend, you can create an `int` transformation; or from any processing function, you can return a new function with a logging step.

Save to `FactoryDemo.java`:

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class FactoryDemo {
    static IntUnaryOperator add(int amount) {
        return number -> number + amount;
    }

    static <T, R> Function<T, R> logged(Function<T, R> operation) {
        return input -> {
            R result = operation.apply(input);
            System.out.println("Đã xử lý: " + input);
            return result;
        };
    }

    public static void main(String[] args) {
        IntUnaryOperator plusFive = add(5);
        System.out.println(plusFive.applyAsInt(7));

        Function<String, Integer> count = logged(String::length);
        System.out.println(count.apply("Java"));
    }
}
```

Run:

```bash
javac FactoryDemo.java
java FactoryDemo
```

Output:

```text
12
Đã xử lý: Java
4
```

`add(5)` returns a lambda that remembers `amount = 5`; later `plusFive.applyAsInt(7)` produces `12`. `logged` is special because it **both accepts a function and returns another function**: it wraps the original behavior with a logging step. You can use this idea to add logging, timing, access checks, or error handling, as long as there is a clear design for side effects.

**Scope of captured variables (closure):** a lambda can use parameters and local variables from outside its own scope. Captured local variables must be `final` or **effectively final** (not reassigned after initialization). For a local variable pointing to a mutable object, this constraint only forbids reassigning the reference variable; it does not make the object immutable.

```java
int increment = 3;
IntUnaryOperator plusThree = n -> n + increment;
// increment = 4; // If uncommented, the code will not compile.
```

This is an illustrative snippet inside a method body, with `IntUnaryOperator` already imported. When returning a lambda, there is no need to keep the stack frame of the method that created it: the captured values/references remain available through the created function object. Avoid capturing mutable state without synchronization when multiple threads use the function concurrently.

## 6. Composing Functions Instead of Repeating Logic

Given `f: A → B` and `g: B → C`, the composition `g(f(a))` transforms `A → C` without needing to create a new method for each combination.

With `Function`, there are two equivalent ways to write the same execution order:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Function<String, Integer> a = trim.andThen(length);
Function<String, Integer> b = length.compose(trim);

System.out.println(a.apply("  Java  ")); // 4
System.out.println(b.apply("  Java  ")); // 4
```

These statements are placed inside a method body and require importing `java.util.function.Function`.

- `f.andThen(g)`: runs `f` first, then `g`.
- `g.compose(f)`: runs `f` first, then `g`.
- `Predicate.and`, `Predicate.or`, `Predicate.negate`: combine conditions; `and` and `or` use short-circuit evaluation, so order can matter if a condition causes side effects.
- `Function.identity()`: the identity function `x -> x`, useful in transformation chains.

`Consumer.andThen` also chains two actions together but produces no return value. Do not use `andThen` as a way to hide side effects if execution order is an important business requirement.

Another pattern is **repeatedly applying the same behavior**:

```java
import java.util.function.IntUnaryOperator;

public class TwiceDemo {
    static int applyTwice(IntUnaryOperator operation, int value) {
        return operation.applyAsInt(operation.applyAsInt(value));
    }

    public static void main(String[] args) {
        System.out.println(applyTwice(n -> n + 3, 4));
    }
}
```

Running `javac TwiceDemo.java` then `java TwiceDemo` prints `10` because `4 → 7 → 10`. If you pass a function with side effects, those side effects also occur **twice**.

## 7. Multi-Parameter Functions and Creating Functions Step by Step

`BiFunction<A, B, R>` takes two inputs when calling `apply(a, b)`. Sometimes you want to fix one parameter first and receive the remaining parameter in a later call; this representation is commonly called **currying** (turning a multi-parameter function into a chain of single-parameter functions) or **partial application** when fixing a subset of arguments ahead of time.

```java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

public class CurryDemo {
    public static void main(String[] args) {
        BiFunction<Integer, Integer, Integer> add = Integer::sum;
        Function<Integer, IntUnaryOperator> addBy =
                amount -> number -> number + amount;

        System.out.println(add.apply(3, 4));
        IntUnaryOperator plusThree = addBy.apply(3);
        System.out.println(plusThree.applyAsInt(4));
    }
}
```

Run `javac CurryDemo.java` and `java CurryDemo`, and the result is two lines `7` and `7`. In this example, `addBy.apply(3)` **has not added to any specific number yet**: it creates a new function waiting for the second number.

Java does not automatically curry every method. The return type `Function<Integer, IntUnaryOperator>` and the nested lambdas must be declared explicitly, or you can use a library that provides an equivalent construct.

## 8. Choosing the Right Type and Understanding Generic Type Constraints

When writing an API that accepts a function, you should clearly expose its **role**:
- Returning data: `Function<T, R>`; same input/output type: `UnaryOperator<T>`.
- Deciding true/false: `Predicate<T>`, rather than `Function<T, Boolean>` unless there is a specific reason.
- Performing an action with no return value: `Consumer<T>`.
- Producing data on demand: `Supplier<T>`.
- Processing `int`, `long`, or `double` in performance-sensitive loops: consider specialized interfaces to reduce boxing.

In the `map` method above, the signature `Function<? super T, ? extends R>` is intentional:

- `? super T` allows the function to accept `T` **or a supertype** of `T` (the function "consumes" the input).
- `? extends R` allows the function to produce `R` **or a subtype** of `R` (the function "produces" the result).

For example, a `Function<Object, String>` can process `String` elements, and the `String` output can be used where a `CharSequence` is expected. This flexible declaration makes higher-order methods easier to reuse. Let the compiler infer types when possible; when a lambda has multiple possible interpretations, you can explicitly declare parameter types or the target variable.

## 9. Execution Timing, Side Effects, and Practical Limitations

**Distinguish creating a function from running a function.** `Function<String, Integer> f = String::length;` creates a behavior value, while `f.apply("Java")` invokes the computation. A higher-order method might call the function immediately, call it multiple times, store it for later use, or not call it at all; **the contract of the API accepting the function** determines that.

With Streams, intermediate operations such as `map` and `filter` typically execute **lazily**. They only run when there is a terminal operation such as `toList()`, `count()`, or `forEach(...)`, and may not process every element if the result can terminate early. Do not rely on side effects in `map` to guarantee execution counts or order if the pipeline changes.

**Pure functions** return the same result for the same input and produce no observable side effects; Java does not require lambdas to be pure. Pure, immutable functions that do not depend on shared state are usually easier to test and compose. Functions with side effects are still necessary for I/O and logging, but intent should be made clear (usually via `Consumer` or an appropriate method name).

Standard interfaces like `Function.apply` do not declare checked exceptions. If a behavior needs to throw a checked exception, you must handle it inside the lambda, deliberately convert it into an unchecked exception, or design a custom functional interface that declares `throws`. Do not silently swallow errors.

**`null` values:** `Function` does not check for `null` on your behalf by default. Passing `null` as a function argument, returning `null` as a result, or dereferencing a `null` input must all follow the designed contract and handling; `Objects.requireNonNull` can often be used at API boundaries.

**Performance:** a lambda does not mean creating a new thread. Passing a function is a mechanism for expressing behavior; sequential Streams still run on the calling thread. Lambdas that capture variables may require an object to store state; specialized functional interfaces avoid some primitive boxing overhead. Only optimize when you have reliable measurements.

## 10. Common Pitfalls

| Situation | Problem | How to Handle It |
| --- | --- | --- |
| Wanting to "pass a method" but passing `length.apply("Java")` | Passing the `int` **result**, not the behavior | Pass `String::length` or `s -> s.length()` |
| Writing a lambda without a suitable target type | Java does not know the behavior's signature | Declare `Function<String, Integer>` or a method parameter accepting a functional interface |
| Reassigning a local variable already captured by a lambda | Compilation error because it is no longer effectively final | Create a new variable/immutable value; do not use arrays or mutable objects just to bypass the rule |
| Confusing `compose` and `andThen` | Steps run in the wrong order | Read as `f.andThen(g)` = run f then g; `g.compose(f)` = run f then g |
| Using `Function` for a side-effect-only task | Output contract is misleading | Use `Consumer` when no result needs to be returned |
| Function writing to a shared list or variable inside a Stream | Unpredictable results, especially when running in parallel | Use stateless transformations and appropriate terminal operations/collectors |
| Assuming a returned function runs immediately | Mistaking execution timing or missing the invocation | Distinguish `Function` (behavior value) from `apply` (execution) |

## 11. When to Use and How to Self-Check

Higher-order functions are especially suitable when **the processing structure is the same but the rules change**: mapping and filtering data, configuring comparators, building validators, wrapping operations with logging, or creating functions from configuration parameters. For simple, one-off logic that does not need to pass behavior across an API boundary, a regular method may be easier to understand.

Try doing the following three exercises yourself:

1. Write `static <T> long countMatching(List<T> items, Predicate<? super T> rule)` to count elements that satisfy a condition. Test with `List.of(2, 5, 8, 11)` and `n -> n % 2 == 0`; the expected result is `2`.
2. Write `static UnaryOperator<String> appendSuffix(String suffix)` returning a lambda that appends a suffix. With suffix `"!"`, applying it to `"Java"` should yield `"Java!"`. Clearly identify which call creates the function and which call executes the function.
3. Use `Function.andThen` to compose the string normalization step `String::trim` and the uppercase step `String::toUpperCase`; test with `"  java  "` and explain why swapping the order of the two steps still gives `"JAVA"` in this case, whereas not all transformations can be reordered.

**Self-assessment question:** If a method has the signature `Function<Integer, Integer> makeAdder(int delta)` and returns `n -> n + delta`, which kind of higher-order function is it? It **returns a function**; this function object remembers `delta`, and the addition only happens when `apply` is called.

Key takeaway: in Java, a "higher-order function" is a way of organizing **behavior through functional interfaces**. A method that accepts behavior, returns behavior, or does both allows the fixed algorithm part and the variable rule part to be combined clearly, tested independently, and reused.