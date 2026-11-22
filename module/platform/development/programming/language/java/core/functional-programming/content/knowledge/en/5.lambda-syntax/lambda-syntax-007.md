# `void`-Returning Lambdas and Statement Expressions in Java

## 1. The core issue to understand

In Java, a lambda does not carry an independent type of its own such as "function returning void" or "function returning a number." The **target type**—a *functional interface*—determines the parameter types and return type that the lambda must satisfy. When the interface's single abstract method returns `void`, the lambda body can be:

- **Expression body**: a *statement expression* (an expression allowed to stand alone as a Java statement), such as calling `System.out.println(...)`, `list.add(...)`, an assignment, or incrementing a variable.
- **Block body**: a `{ ... }` block compatible with `void` semantics; any `return` statements that appear must have the form `return;`, carrying no value.

A common point of confusion: **a method called inside a lambda may return a value, but that value is allowed to be discarded when the target type returns `void`**. Thus `value -> list.add(value)` is valid for `Consumer<String>` even though `List.add` returns `boolean`.

Conversely, `value -> value + "!"` is **not** valid for `Consumer<String>`: pure string concatenation is not a *statement expression*. To return that string, use `Function<String, String>`; to perform an action, call a method or write a block.

### Why does this matter?

It explains how to write concise code when passing lambdas to `Runnable`, `Consumer<T>`, `forEach`, callbacks, and event handlers; helps read compiler error messages accurately when a lambda has a `return` statement; and prevents confusing "a function performing an action" with "a function computing a result." This is a Java language syntax rule, not specific to the Stream API.

## 2. Two common groups of functional interfaces

| Interface | Abstract method | Result type | Lambda example |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | `void` | `() -> System.out.println("Run")` |
| `Consumer<T>` | `void accept(T value)` | `void` | `s -> System.out.println(s)` |
| `BiConsumer<T,U>` | `void accept(T left, U right)` | `void` | `(a, b) -> System.out.println(a + b)` |
| `Function<T,R>` | `R apply(T value)` | `R` | `s -> s.length()` with `R = Integer` |
| `Supplier<T>` | `T get()` | `T` | `() -> "READY"` |
| `Predicate<T>` | `boolean test(T value)` | `boolean` | `s -> s.isBlank()` |

`Runnable` belongs to `java.lang`; the remaining interfaces in the table belong to `java.util.function`. `Runnable` takes no input; `Consumer<T>` takes one input and returns `void`; `BiConsumer<T,U>` takes two inputs and returns `void`.

Example:

```java
Runnable task = () -> System.out.println("Run");
Consumer<String> printer = text -> System.out.println(text);
Function<String, Integer> length = text -> text.length();

task.run();                // Run
printer.accept("Java");    // Java
System.out.println(length.apply("Java")); // 4
```

These are statements to place inside a method or `jshell`; `java.util.function.Consumer` and `java.util.function.Function` must be imported. When invoked, `task.run()` and `printer.accept(...)` do not return a result to assign to a variable; `length.apply(...)` returns `Integer`.

## 3. Expression lambdas: why can some expressions be used with `void`?

Expression lambda structure:

```java
(parameters) -> expression
```

Java defines a **void-compatible expression lambda** as a lambda whose expression body is a **statement expression**. That is an expression that Java's grammar allows to be written as an *expression statement* by appending `;`.

Kinds of statement expressions according to Java grammar:

| Kind | Example standing alone as a statement | Notes |
| --- | --- | --- |
| Assignment | `state[0] = 5;` | The value of the assignment expression can be ignored |
| Prefix increment/decrement | `state[0]++;` written as `++state[0];` | Performs the change before/after returning the value |
| Postfix increment/decrement | `state[0]++;` or `state[0]--;` | The returned value does not have to be used |
| Method invocation | `list.add("A");`, `text.trim();`, `System.out.println(text);` | The result, if any, is allowed to be ignored |
| Object creation with `new` | `new StringBuilder("A");` | Can create an object without using the resulting reference |

The table includes both prefix and postfix `++`/`--`. For lambdas, other Java rules must also be obeyed—most importantly, you cannot reassign a captured local variable if that variable would no longer be *effectively final*. A field or an array element can be used for increment/decrement examples, though doing so requires considering mutable state and thread safety.

**Not statement expressions**: literal `42`, bare variable reference `value`, addition operator `a + b`, comparison `a > b`, logical operations, conditional expression `condition ? left : right`. These expressions can return a value and fit a functional interface needing a value, but they are not suitable as an *expression body* for a `void`-returning interface.

### Value-returning calls still fit `void`

```java
List<String> names = new ArrayList<>();

Consumer<String> addName = name -> names.add(name);
Consumer<String> trimButIgnore = name -> name.trim();

addName.accept("Lan");
trimButIgnore.accept("  Lan  ");
System.out.println(names); // [Lan]
```

Both lambdas compile: `names.add(name)` is a method invocation returning `boolean` and `name.trim()` is a method invocation returning `String`. Because the target type is `Consumer<String>`, **the return value is ignored**.

However, `trimButIgnore` is practically useless: `String` is immutable, so `trim()` returns a different string that nobody uses. If you want to transform a string into new data, use:

```java
Function<String, String> trim = String::trim;
String cleaned = trim.apply("  Lan  "); // "Lan"
```

This is the difference between **syntactically valid** and **meaningful in business logic**.

### Expressions that are invalid for `void`

The following snippets intentionally illustrate **compilation errors**; do not place them in a runnable program:

```java
// INVALID: just addition, not a statement expression.
Consumer<Integer> bad1 = x -> x + 1;

// INVALID: just a variable reference, not a statement expression.
Consumer<String> bad2 = x -> x;

// INVALID: a literal is not a statement expression.
Runnable bad3 = () -> 42;
```

Fix according to intent:

```java
Function<Integer, Integer> plusOne = x -> x + 1;
Consumer<Integer> printNext = x -> System.out.println(x + 1);
Runnable print42 = () -> System.out.println(42);
```

On the `printNext` line, the addition appears **inside the argument of a method call**, while the entire lambda body is `System.out.println(...)`, which is a valid method invocation acting as a statement expression.

## 4. Block lambdas: how do `return;` and `return expression;` differ?

For a block lambda, we use the syntax:

```java
(parameters) -> {
    statement1;
    statement2;
}
```

When the target method returns `void`, the block must be **void-compatible**: every `return` statement inside the block (if any) must be `return;`. The block can complete normally without needing a `return`.

```java
Consumer<String> greet = name -> {
    if (name.isBlank()) {
        return; // Valid: exits early, returns no value.
    }
    System.out.println("Hello, " + name);
};

greet.accept("Lan"); // Hello, Lan
greet.accept("");    // Prints nothing
```

Conversely, when the target type requires a result such as `Function<String,Integer>`, the block must generally `return` the right type for every path that can complete normally:

```java
Function<String, Integer> count = text -> {
    String cleaned = text.trim();
    return cleaned.length();
};
System.out.println(count.apply(" Java ")); // 4
```

Invalid examples:

```java
// INVALID: Consumer has a void result, does not allow returning a value.
Consumer<String> bad = text -> {
    return text.length();
};

// INVALID: Function requires Integer, but the block ends without returning.
Function<String, Integer> alsoBad = text -> {
    text.length();
};
```

If a lambda returns a value without needing a block, an expression body can be written concisely as `text -> text.length()`. If a block has conditionals, ensure all necessary branches return a result, throw an exception, or do not complete normally; never leave a path that can finish without `return`.

### Notes on void-compatible and value-compatible

Java distinguishes two concepts when checking a **block lambda**:

- **Void-compatible block**: all `return`s (if any) are `return;`.
- **Value-compatible block**: the block cannot complete normally, and every `return` (if any) returns an expression.

For example, `x -> { return x.length(); }` matches `Function<String,Integer>`. `x -> { System.out.println(x); }` matches `Consumer<String>` and does not match `Function<String,Integer>` because it returns no value. For a block that **only throws an exception** such as `() -> { throw new IllegalStateException(); }`, both compatibility checks can be satisfied; this matters when the compiler selects an overload.

For an **expression lambda**, a value-producing expression such as a call like `String::trim` can both serve as the result of `Function` and be treated as a statement expression for `Consumer`. Therefore, you cannot infer the target type solely from the method name called in the lambda body; you must look at the assignment context or the method parameter receiving the lambda.

## 5. Complete Java 17 example: Consumer, Runnable, and Function

Problem: process some order codes. Operations include *saving codes to a list*, *logging*, *validating input*, *transforming data*, and *generating a report*. The example intentionally shows the difference between a lambda performing a side effect and a lambda returning a result.

Create the file **`VoidLambdaDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class VoidLambdaDemo {
    @FunctionalInterface
    interface Action {
        void run();
    }

    static void execute(Action action) {
        action.run();
    }

    public static void main(String[] args) {
        List<String> history = new ArrayList<>();

        // List.add returns boolean, but Consumer.accept returns void.
        Consumer<String> save = value -> history.add(value);
        Consumer<String> log =
                value -> System.out.println("Saved: " + value);

        // Two Consumers executed in exact order.
        save.andThen(log).accept("A01");

        // Runnable: calls a print method (returns void).
        Runnable count =
                () -> System.out.println("Count: " + history.size());
        count.run();

        // Block lambda returning void and having return; is valid.
        Action insertThenLog = () -> {
            history.add("A02");
            System.out.println("Inserted: " + history.size());
            return;
        };
        execute(insertThenLog);

        // return; only stops the Consumer's action, returns no data.
        Consumer<String> verify = value -> {
            if (value.isBlank()) {
                System.out.println("Skipped blank");
                return;
            }
            System.out.println("Checked: " + value);
        };

        verify.accept("");
        verify.accept("BOOK");

        // Function with an explicit result, independent of history.
        Function<String, String> normalize =
                value -> value.trim().toUpperCase(Locale.ROOT);
        System.out.println("Mapped: " + normalize.apply("  book  "));

        // Method invocation history.set returns String, but the result is discarded.
        Runnable changeFirst = () -> history.set(0, "A01*");
        changeFirst.run();
        System.out.println("History: " + history);

        // map transforms data; collect gathers results; does not mutate the source.
        String joined = Stream.of("pen", "book")
                .map(value -> value.toUpperCase(Locale.ROOT))
                .collect(Collectors.joining(","));
        System.out.println("Joined: " + joined);
    }
}
```

Compile and run:

```bash
javac --release 17 VoidLambdaDemo.java
java VoidLambdaDemo
```

**Deterministic stdout of the program:**

```text
Saved: A01
Count: 1
Inserted: 2
Skipped blank
Checked: BOOK
Mapped: BOOK
History: [A01*, A02]
Joined: PEN,BOOK
```

Output explanation:

1. `save.andThen(log).accept("A01")` calls `save` first to add `"A01"` to `history`, and only then calls `log` to print. `List.add` returns `true`/`false` per the collection contract, but `Consumer` does not retain that value.
2. `count.run()` prints size 1. The contents of `history` are observed when `run()` executes, not when the lambda is created.
3. `insertThenLog` adds `"A02"`, prints size 2, and then `return;` exits the block. No value is returned.
4. `verify.accept("")` prints "Skipped blank" and exits immediately; `verify.accept("BOOK")` prints the check line normally.
5. `normalize.apply("  book  ")` returns `"BOOK"` because `trim` strips leading/trailing whitespace and `toUpperCase(Locale.ROOT)` converts to uppercase. Using `Locale.ROOT` avoids depending on the machine's default locale configuration.
6. `history.set(0, "A01*")` returns the old element `"A01"`, but `Runnable` ignores that value; the final list is `[A01*, A02]`.
7. `Stream.map(...)` returns `"PEN"` and `"BOOK"`, and `Collectors.joining(",")` joins them into `"PEN,BOOK"`.

All operations on `history` run sequentially in a single thread in this example. `ArrayList` is not inherently safe for concurrent updates; do not assume `history` can be used directly from multiple callbacks running in parallel.

## 6. `Consumer.andThen` and `void`-returning action chains

`Consumer<T>` provides the default method `andThen(Consumer<? super T> after)`, allowing you to create a new `Consumer` that performs two actions in order.

```java
Consumer<String> first =
        text -> System.out.println("first: " + text);
Consumer<String> second =
        text -> System.out.println("second: " + text);

Consumer<String> chain = first.andThen(second);
chain.accept("A");
// first: A
// second: A
```

Do not confuse this with `Function.andThen(...)`:

- `Consumer.andThen` chains **two actions**, each receiving the same input value and returning `void`.
- `Function.andThen` chains **two transformations**, passing the first function's result as input to the second.

If `first.accept(...)` throws an exception, `second` does not run. `andThen` does not automatically roll back side effects that already occurred; if data is saved and then an API call fails, design an appropriate error-handling/transaction mechanism.

## 7. Method references can also discard return values

The rule allowing a result to be ignored is not limited to lambda expressions. When the target type returns `void`, a **method reference** to a value-returning method can also fit:

```java
List<String> names = new ArrayList<>();
Consumer<String> addName = names::add;
addName.accept("An");

Consumer<String> discardTrimmedValue = String::trim;
discardTrimmedValue.accept("  An  ");

System.out.println(names); // [An]
```

`names::add` points to `List.add`, which returns boolean. `String::trim` points to a method returning String. Both can be used as `Consumer<String>`; the call result is discarded. `discardTrimmedValue` does not mutate the input string and produces no observable value, so it is a syntactically valid example that is rarely useful.

Conversely, if the goal is to produce a trimmed name, use `UnaryOperator<String> clean = String::trim;` or `Function<String,String> clean = String::trim;`, and receive the result from `apply`.

## 8. Distinguishing "returns no value" from "has no side effects"

These are two independent concepts:

- `void` means there is no **return value from the call**. A `void`-returning function is usually used for actions, but the keyword `void` itself does not guarantee the action is useful or has side effects.
- A **side effect** is an effect beyond the return value, such as mutating a list, writing a file, sending a request, updating a variable, or printing to the console. A value-returning function can still have side effects.

For example, `List.add` returns `boolean` while mutating the list; `String.trim` returns a new `String` without mutating the original string. Using `Consumer<String> c = s -> s.trim();` does not turn `String.trim` into an in-place string mutation.

In functional programming style, **computation and transformation** should usually return results via `Function`/`map`, while **necessary actions** should appear at clear boundaries such as `Consumer` or an orchestration layer. Do not exploit Java's allowance for discarding values to accidentally throw away an important business result.

### Do not manually update a shared accumulator in a parallel stream

The following snippet is unreliable if run in parallel:

```java
// Counterexample: put in a separate demo block; do not run together with main.
List<String> output = new ArrayList<>();
List.of("A", "B", "C").parallelStream()
        .forEach(value -> output.add(value));
```

`output.add(value)` is valid as a `void`-returning expression lambda, but multiple workers may update the same `ArrayList`, causing data races, missing elements, wrong ordering, or structural corruption. Valid syntax does not prove concurrency safety.

If the goal is to transform into a new list:

```java
List<String> output = List.of("A", "B", "C")
        .parallelStream()
        .map(value -> value.toLowerCase(Locale.ROOT))
        .toList();
```

Here `map` returns results and `toList()` collects them according to the Stream contract; the source list has encounter order, and the result preserves encounter order in this case. `Stream.toList()` produces a list that cannot be modified via `add`/`remove`. There is no need to manually mutate a shared collection inside a lambda.

If the goal is purely printing/logging, `forEach` can make sense, but `parallelStream().forEach(...)` does not guarantee execution order. Use `forEachOrdered` when encounter order must be preserved, and weigh the cost/side effects before parallelizing.

## 9. Local variable capture rules and shared state issues

A lambda is allowed to read a local variable from an outer scope only if that variable is `final` or **effectively final** (never reassigned after initialization):

```java
String prefix = "Order: ";
Consumer<String> log = id -> System.out.println(prefix + id);
log.accept("A01"); // Order: A01
```

The compiler rejects the following example:

```java
// INVALID: local variable counter is modified and is not effectively final.
int counter = 0;
Runnable increment = () -> counter++;
```

A holder, field, or `AtomicInteger` can be used when state genuinely needs to be updated, but should not be used merely to bypass lambda rules:

```java
int[] counter = {0};
Runnable increment = () -> counter[0]++;
increment.run();
System.out.println(counter[0]); // 1
```

This snippet compiles, but `counter[0]` is still mutable state, risking a data race if multiple threads update it. In Streams, use `count()` to count elements; `sum()`/`reduce()` to sum numbers; and `collect()`/`toList()` to collect elements. These aggregations express intent clearly and avoid managing a shared mutable accumulator manually.

## 10. Overloading cases and dual compatibility

A **value-producing expression lambda** that is a statement expression, such as the method call `s.trim()`, can be compatible with both a `void`-returning target method and a `String`-returning target method:

```java
Consumer<String> asAction = s -> s.trim();
Function<String, String> asMapping = s -> s.trim();
```

Both are valid, but `asAction` discards the trimmed result; `asMapping` keeps it. When two overloads accept different functional interfaces, overload selection also depends on *arity*, *target type*, *most specific* rules, and the lambda body's contents. A lambda consisting of a value-returning method call can cause an **ambiguous method call error** when multiple overloads match; do not just look at `->` and guess which overload will be chosen.

When an overloaded API is hard to read or causes errors, use an **explicitly typed variable** or a **target cast**:

```java
// Create variables with explicit target types:
Consumer<String> action = value -> System.out.println(value);
Function<String, String> convert = String::trim;

// If an API actually overloads Consumer and Function,
// passing action or convert helps select the right overload.
```

No custom overloaded methods are required to run `VoidLambdaDemo.java`; this section is a guideline for reading code and resolving compilation errors.

## 11. Common mistakes

| Code or assumption | Problem | Correct approach |
| --- | --- | --- |
| `Consumer<Integer> c = n -> n + 1;` | `n + 1` is not a statement expression | Use `Function<Integer,Integer>` or call a processing method |
| `Runnable r = () -> 10;` | Literal is not a statement expression | `Runnable r = () -> System.out.println(10);` |
| `Consumer<String> c = s -> { return s; };` | Block returns a value, target method returns void | Use `return;` or `Function` |
| `Function<String,Integer> f = s -> { s.length(); };` | Block completes normally without returning a result | `return s.length();` |
| `Consumer<String> c = s -> s.trim();` to "normalize" | Result of `trim()` is discarded | Use `Function<String,String>`/`UnaryOperator<String>` |
| `Runnable r = () -> localCounter++;` | Mutates a captured local variable, violating effectively final | Switch design to reduction, or state with clear ownership |
| `parallelStream().forEach(list::add)` | Can race when writing to a shared mutable list | Use `map(...).toList()` or an appropriate collector |
| Assuming `void` means "pure function" | `void` only describes the return value, does not forbid side effects | Evaluate the body and the state the function reads/writes |
| Assuming `andThen` automatically rolls back on error | Side effects of the earlier action are not rolled back | Design error handling/transactions per the problem |

Distinguish between **compiles**, **produces the desired result**, and **concurrency-safe**. These are three different questions.

## 12. Self-check exercises

1. For each lambda body below, determine whether it is a statement expression usable with `Runnable`/`Consumer`: `System.out.println("OK")`, `list.add("A")`, `x + 1`, `new StringBuilder("A")`, `state[0]++`, `x > 10`. Explain by expression kind.
2. Write a `Consumer<String>` that takes a string, prints `"empty"` and `return;`s if empty, otherwise prints uppercase. Create a block lambda with all required braces and semicolons.
3. Replace `Consumer<String> c = s -> s.trim();` with `Function<String,String>`. Use `apply("  book  ")` to get `"book"`.
4. Using `Consumer<String> log = System.out::println` and `Consumer<String> save = list::add`, create `save.andThen(log)` and call it with `"A01"`; explain the order of updating and printing.
5. Convert `Consumer<String> bad = s -> { return s.length(); };` into two valid versions: one that only prints the length, and one that returns the length via `Function<String,Integer>`.
6. Fix `Function<String,Integer> length = s -> { s.length(); };` so it compiles, and explain why the original is missing a return value.
7. Given `List.of("A","B","C")`, create a new list containing `"a","b","c"` without adding elements to an external `ArrayList` inside a lambda. Verify using `map(...).toList()`.
8. In `VoidLambdaDemo`, predict how stdout changes if `save.andThen(log)` is removed and only `log.accept("A01")` is called. Why does `Count` become 0 and why will `history.set(0, ...)` fail afterward? State how to avoid this hidden dependency.

**Key takeaway:** the functional interface's target type determines whether a lambda must return a value; a `void`-returning expression lambda needs a **statement expression**; a `void`-returning block lambda can use `return;` but not `return value;`; the result of a method invocation can be discarded when adapting to `void`. In data processing, use `Function` to produce new results and `Consumer` for intentional actions, while controlling side effects and shared mutable state.