# IntFunction, ToIntFunction, and distinguishing conversion directions in Java

## 1. Core idea: the interface name tells you the data direction

In the `java.util.function` package, **`IntFunction<R>` and `ToIntFunction<T>` are both functional interfaces**, but they perform transformations in **two opposite directions**:

- **`IntFunction<R>`**: takes a **primitive `int`** and returns a value of type **`R`** (a reference type).
- **`ToIntFunction<T>`**: takes a value of type **`T`** (a reference type) and returns a **primitive `int`**.

Written in notation:

~~~text
IntFunction<R>:    int  ──apply(int)──────► R
ToIntFunction<T>:  T    ──applyAsInt(T)───► int
~~~

The **`Int` prefix** in `IntFunction` indicates that the **input type** is specialized to `int`. The **`ToInt` prefix** in `ToIntFunction` indicates that the **output type** is `int`.

This is an important naming convention when learning functional programming in Java. Do not guess the meaning just because both contain `Int`: read the **single abstract method (SAM) signature** first.

## 2. Exact signatures and how to invoke them

The two interfaces can be pictured via the following simplified declarations:

~~~java
// Illustrating signatures from java.util.function; do not redeclare
// these standard interfaces in your program.
@FunctionalInterface
public interface IntFunction<R> {
    R apply(int value);
}

@FunctionalInterface
public interface ToIntFunction<T> {
    int applyAsInt(T value);
}
~~~

Comparison table:

| Criterion | `IntFunction<R>` | `ToIntFunction<T>` |
|---|---|---|
| SAM | `R apply(int value)` | `int applyAsInt(T value)` |
| Input type | Primitive `int` | `T` is a reference type |
| Output type | `R` is a reference type | Primitive `int` |
| Generic parameter represents | Result `R` | Input `T` |
| Examples | `int → String`, `int → String[]` | `String → int`, `Product → int` |
| Typical APIs | `IntStream.mapToObj`, `Stream.toArray` | `Stream.mapToInt`, `Comparator.comparingInt` |
| Invocation method | `f.apply(5)` | `f.applyAsInt("Java")` |

Pay special attention:

1. `IntFunction<R>` **is not** `Function<Integer, R>`. Both can express converting a number to `R`, but `IntFunction` accepts a primitive `int` directly, whereas `Function<Integer, R>` accepts a boxed `Integer`.
2. `ToIntFunction<T>` **is not** `Function<T, Integer>`. `ToIntFunction` returns a primitive `int`, whereas `Function<T, Integer>` returns an `Integer` object.
3. For generic `R` or `T`, you cannot write `IntFunction<int>` or `ToIntFunction<int>`: Java generic type arguments must be **reference types**. `IntFunction<Integer>` is valid, but then the `int` output is represented via `Integer`, meaning boxing can occur.
4. The two SAMs have **different names**. Confusing `apply` with `applyAsInt` is a common compile error.

## 3. Simple example: converting `int` to `String` and `String` to `int`

~~~java
import java.util.function.IntFunction;
import java.util.function.ToIntFunction;

class Example {
    void demonstrate() {
        IntFunction<String> toLabel = number -> "ID-" + number;
        ToIntFunction<String> length = String::length;

        String label = toLabel.apply(12);       // "ID-12"
        int count = length.applyAsInt("Java");   // 4
    }
}
~~~

This is an **illustrative snippet**: the class compiles, but has no `main` to run standalone.

Analysis:

- `number -> "ID-" + number` is assigned to `IntFunction<String>`: the lambda's input is inferred as `int`; its output is `String`.
- `String::length` fits `ToIntFunction<String>`: a `String` object is the input and the `length()` value is `int`.
- `toLabel.apply(12)` and `length.applyAsInt("Java")` use the exact SAM name of each interface.
- A lambda does not decide its own type: the target type `IntFunction<String>` or `ToIntFunction<String>` determines the contract the lambda/method reference must satisfy.

Side by side for easy recall:

~~~text
number ── IntFunction<String> ──► "ID-12"
"Java" ── ToIntFunction<String> ──► 4
~~~

## 4. Complete program: both conversion directions in data processing

Save as `ConversionDirectionDemo.java` (JDK 17+):

~~~java
import java.util.List;
import java.util.function.IntFunction;
import java.util.function.ToIntFunction;
import java.util.stream.IntStream;

public class ConversionDirectionDemo {
    record Item(String name, int price, int quantity) {}

    public static void main(String[] args) {
        IntFunction<String> label = n -> "ID-" + n;
        ToIntFunction<String> length = String::length;

        List<Item> items = List.of(
                new Item("Pen", 5, 3),
                new Item("Book", 20, 2)
        );

        ToIntFunction<Item> lineTotal =
                item -> Math.multiplyExact(item.price(), item.quantity());

        System.out.println(label.apply(7));
        System.out.println(length.applyAsInt("Java"));
        System.out.println(IntStream.rangeClosed(1, 3)
                .mapToObj(label)
                .toList());
        System.out.println(items.stream()
                .mapToInt(lineTotal)
                .sum());
    }
}
~~~

Compile and run:

~~~bash
javac ConversionDirectionDemo.java
java ConversionDirectionDemo
~~~

Stdout:

~~~text
ID-7
4
[ID-1, ID-2, ID-3]
55
~~~

**Trace the output along the data flow:**

1. `label.apply(7)` takes primitive `7` and returns `"ID-7"`. This is the **`int → String`** direction.
2. `length.applyAsInt("Java")` takes a `String` object and returns primitive `4`. This is the **`String → int`** direction.
3. `IntStream.rangeClosed(1, 3)` generates values `1`, `2`, `3`; `mapToObj(label)` turns each `int` into a `String`; `toList()` produces `[ID-1, ID-2, ID-3]`.
4. `items.stream()` is a `Stream<Item>`; `mapToInt(lineTotal)` converts each `Item` into an `int` line total; `sum()` yields `5 × 3 + 20 × 2 = 55`.
5. `Math.multiplyExact` demonstrates detecting overflow in multiplication. Addition in `IntStream.sum()` can still overflow `int` if the sum exceeds the range; real currency requires an appropriate unit and arithmetic model.

Within the same program, **`IntFunction` sits at the boundary stepping out of a primitive stream**, while **`ToIntFunction` sits at the boundary stepping into a primitive stream**.

## 5. Connecting with the Stream API: `mapToObj` and `mapToInt`

Two important signatures:

~~~java
// Simplified signatures from the Stream API, not redeclared code.
<R> java.util.stream.Stream<R> mapToObj(
        java.util.function.IntFunction<? extends R> mapper);

java.util.stream.IntStream mapToInt(
        java.util.function.ToIntFunction<? super T> mapper);
~~~

The first signature belongs to **`IntStream`**, and the second belongs to **`Stream<T>`**. The above is illustrative notation, not a standalone compilable Java file because the enclosing generic class declarations are omitted.

### 5.1. From `IntStream` to `Stream<R>`

~~~java
java.util.stream.Stream<String> names =
        java.util.stream.IntStream.of(2, 4, 6)
                .mapToObj(n -> "N" + n);
~~~

The source consists of primitive `int`s; the mapper takes `int` and returns `String`. Therefore `mapToObj` requires **`IntFunction<? extends R>`**, where `R` is `String`.

### 5.2. From `Stream<T>` to `IntStream`

~~~java
java.util.stream.IntStream lengths =
        java.util.stream.Stream.of("a", "bbb", "cc")
                .mapToInt(String::length);
~~~

The source consists of `String` objects; the mapper takes `String` and returns `int`. Therefore `mapToInt` requires **`ToIntFunction<? super T>`**, where `T` is `String`.

**How should you read the wildcards?** `? extends R` lets `mapToObj` accept a mapper that produces a subtype of `R`; `? super T` lets `mapToInt` accept a mapper that accepts `T` or a supertype of `T`. This follows the *producer extends, consumer super* (PECS) principle, applied here to the function's result and parameter positions.

### 5.3. Avoid confusing with `map`

`IntStream.map` does **not** take `IntFunction<R>`; it requires **`IntUnaryOperator`** with signature `int applyAsInt(int)` because both input and output are primitive `int`.

~~~java
java.util.stream.IntStream doubled =
        java.util.stream.IntStream.of(1, 2, 3)
                .map(n -> n * 2); // IntUnaryOperator: int -> int.
~~~

Conversely, `Stream<T>.map` takes `Function<? super T, ? extends R>` and produces `Stream<R>`. When you need a primitive `int` result, `mapToInt` is usually more suitable, especially if you subsequently use `sum()`, `average()`, or `max()`.

## 6. `IntFunction` is also used as an array generator

A particularly common use of `IntFunction<A[]>` is the overload:

~~~java
<A> A[] toArray(java.util.function.IntFunction<A[]> generator);
~~~

This is the simplified signature of `Stream.toArray(IntFunction<A[]>)`: the argument passed to the generator function is **the array size to allocate** (primitive `int`); the function returns an array `A[]` (an array is a reference type). Thus the API requires `IntFunction<A[]>`, not `ToIntFunction<A[]>`.

Save as `ArrayGeneratorDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.function.IntFunction;

public class ArrayGeneratorDemo {
    public static void main(String[] args) {
        IntFunction<String[]> newStringArray = String[]::new;

        String[] words = List.of("A", "BB", "CCC")
                .stream()
                .toArray(newStringArray);

        IntFunction<int[]> newIntArray = int[]::new;
        int[] zeros = newIntArray.apply(3);

        System.out.println(Arrays.toString(words));
        System.out.println(words.length);
        System.out.println(Arrays.toString(zeros));
    }
}
~~~

Compile and run:

~~~bash
javac ArrayGeneratorDemo.java
java ArrayGeneratorDemo
~~~

Stdout:

~~~text
[A, BB, CCC]
3
[0, 0, 0]
~~~

**Why does `String[]::new` fit?** It represents the behavior of taking an `int` length and creating a `String[]`. `int[]::new` is also a function `int → int[]`, not `int → int`: **an `int[]` array is an object**, distinct from the primitive `int` type. Hence `IntFunction<int[]>` is valid while `IntFunction<int>` is invalid.

If a generator receives a negative size, array creation can throw `NegativeArraySizeException`. When using `Stream.toArray`, the API is responsible for supplying the size it needs; users should still avoid creating generators with side effects depending on external state.

## 7. Distinguishing from `Function`, `IntUnaryOperator`, and similarly named variants

| Contract | SAM | Conversion direction | When appropriate |
|---|---|---|---|
| `Function<T,R>` | `R apply(T)` | Object → object | Converting from one reference type to another |
| `IntFunction<R>` | `R apply(int)` | `int` → object | Converting from primitive `int` to a label, array, or object |
| `ToIntFunction<T>` | `int applyAsInt(T)` | Object → `int` | Extracting length, quantity, weight, or integer code |
| `IntUnaryOperator` | `int applyAsInt(int)` | `int` → `int` | Transforming one `int` into another `int` |
| `IntPredicate` | `boolean test(int)` | `int` → `boolean` | Checking a condition on an `int` |
| `IntConsumer` | `void accept(int)` | `int` → `void` | Accepting an `int` to perform a task |
| `IntSupplier` | `int getAsInt()` | No arguments → `int` | Supplying a primitive `int` |
| `IntBinaryOperator` | `int applyAsInt(int,int)` | Two `int`s → `int` | Combining two integers |
| `ToLongFunction<T>` | `long applyAsLong(T)` | Object → `long` | Extracting a 64-bit integer value |
| `IntToLongFunction` | `long applyAsLong(int)` | `int` → `long` | Converting from primitive `int` to primitive `long` |

Types that accept or return primitives are designed to avoid unnecessary boxing/unboxing at call **boundaries**, but that does not mean the lambda itself is automatically faster in every situation. Always consider actual cost, data size, and code readability.

If you need **`int → int`**, choose `IntUnaryOperator` over `IntFunction<Integer>`: the latter returns an `Integer` object and can incur boxing. If you need **`String → int`**, choose `ToIntFunction<String>` over `Function<String,Integer>` when the result is processed as a primitive in numeric pipelines.

### Example of boxing and target types

~~~java
// Illustrative code snippet, not a standalone runnable program.
java.util.function.IntFunction<Integer> boxedOutput = n -> n + 1;
java.util.function.ToIntFunction<Integer> boxedInput = n -> n + 1;
java.util.function.IntUnaryOperator bothPrimitive = n -> n + 1;
~~~

- `boxedOutput.apply(3)` takes a primitive `int`, but **returns `Integer`**, so boxing conversion occurs on the result when needed.
- `boxedInput.applyAsInt(3)` has its parameter declared as `Integer`; the literal `3` must be boxed to `Integer` before the call, and then the lambda uses that number in addition.
- `bothPrimitive.applyAsInt(3)` takes and returns primitive `int`, requiring no wrapper type at the call boundary.

The JVM has optimizations such as wrapper caching and escape analysis in specific scenarios; do not guess the number of allocated objects just by looking at an expression. What matters is **the type contract** of each functional interface.

## 8. Combining both directions into a pipeline

Sometimes you need to extract an `int` from an object and then use that number to build another object:

~~~text
T --ToIntFunction<T>--> int --IntFunction<R>--> R
~~~

For example, `String → int length → String label`. You can write a higher-order method to combine both contracts.

Save as `FunctionPipelineDemo.java`:

~~~java
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.ToIntFunction;

public class FunctionPipelineDemo {
    static <T, R> Function<T, R> viaInt(
            ToIntFunction<? super T> extractor,
            IntFunction<? extends R> formatter) {
        return value -> formatter.apply(extractor.applyAsInt(value));
    }

    public static void main(String[] args) {
        Function<String, String> describeLength =
                viaInt(String::length, n -> "length=" + n);

        ToIntFunction<String> parseAge = Integer::parseInt;
        IntFunction<String> ageGroup =
                n -> n >= 18 ? "adult" : "minor";

        Function<String, String> describeAge = viaInt(parseAge, ageGroup);

        System.out.println(describeLength.apply("lambda"));
        System.out.println(describeAge.apply("21"));
        System.out.println(describeAge.apply("15"));
    }
}
~~~

Compile and run:

~~~bash
javac FunctionPipelineDemo.java
java FunctionPipelineDemo
~~~

Stdout:

~~~text
length=6
adult
minor
~~~

**Step-by-step reading:**

1. `String::length` is a `ToIntFunction<String>` when used in `viaInt`; it takes `String` and returns `int`.
2. `n -> "length=" + n` is an `IntFunction<String>`; it takes `int` and returns `String`.
3. `viaInt` composes the two steps into `Function<String,String>`, reflecting that **both the initial input type and final result type are reference types**.
4. In the second example, `Integer::parseInt` provides the `String → int` direction. `ageGroup` provides the `int → String` direction.
5. Order matters: `formatter.apply(extractor.applyAsInt(value))`. Reversing the order would fail the signatures here.

For strings that are not valid integers (e.g., `"abc"`), `Integer.parseInt` throws `NumberFormatException`. Real applications must validate or handle input data; functional interfaces do not manage exceptions automatically. This example illustrates composition, not production age-verification logic.

### Can you call `andThen` directly?

`Function<T,R>` provides `compose`/`andThen`, but **`IntFunction<R>` and `ToIntFunction<T>` do not declare `andThen`/`compose` like `Function`**. In the example above, we combine them with a new lambda and return `Function<T,R>`. This keeps the intermediate step's input/output as primitive `int` inside the function's logic, even though the resulting `Function<T,R>` has reference types at both ends.

## 9. Cases that commonly cause compile errors

### 9.1. Choosing the wrong direction

~~~java
// WRONG: IntFunction<String> must take int, not String.
// java.util.function.IntFunction<String> wrong = s -> s.toUpperCase();

// RIGHT: parameter is int, result is String.
java.util.function.IntFunction<String> label = n -> "N" + n;
~~~

The wrong line is commented out for illustration. Because `s` is inferred as `int`, it has no `toUpperCase()` method. If you need `String → String`, use `Function<String,String>`.

### 9.2. Using an incompatible return type

~~~java
// WRONG: ToIntFunction<String> must return int.
// java.util.function.ToIntFunction<String> wrong = s -> "length=" + s.length();

// RIGHT:
java.util.function.ToIntFunction<String> length = String::length;
~~~

`ToIntFunction` requires an `int` result, not a descriptive string. If you want a descriptive string, use `Function<String,String>` or combine `ToIntFunction` with `IntFunction<String>`.

### 9.3. Wrong SAM method

~~~java
java.util.function.IntFunction<String> show = n -> "value=" + n;
java.util.function.ToIntFunction<String> size = String::length;

// RIGHT:
String a = show.apply(5);
int b = size.applyAsInt("hi");

// WRONG:
// show.applyAsInt(5);
// size.apply("hi");
~~~

The method name belongs to the interface, independent of variable names or lambda body.

### 9.4. Using a primitive in a generic type argument

~~~java
// WRONG: generics do not accept primitive types.
// IntFunction<int> invalid = n -> n + 1;

// RIGHT when you need int -> int:
java.util.function.IntUnaryOperator increment = n -> n + 1;

// Valid, but boxed output:
java.util.function.IntFunction<Integer> boxed = n -> n + 1;
~~~

Similarly, `ToIntFunction<int>` is invalid; if you want `int → int`, use `IntUnaryOperator`.

### 9.5. Misusing with Stream

~~~java
// WRONG: Stream<String>.mapToInt does not accept IntFunction.
// Stream.of("a", "bb").mapToInt(n -> "ID-" + n);

// RIGHT:
int count = java.util.stream.Stream.of("a", "bb")
        .mapToInt(String::length)
        .sum();
~~~

`mapToInt` takes **an element of `Stream<String>`** and turns it into an `int`. In the example above, the total length is `1 + 2 = 3`. Check the Stream's source type and desired output Stream type before picking a function.

## 10. Notes on null, data types, and safety

- **`int` has no `null`.** `IntFunction<R>` always receives an `int` value. However, `R` is a reference type so `apply` can return `null` if the implementation allows it.
- **`ToIntFunction<T>` has a reference input.** Callers can pass `null` (if the API does not prevent it), and a lambda like `String::length` will throw `NullPointerException`. Define your null policy at the boundary.
- **An `int` result cannot be `null`.** `ToIntFunction<T>.applyAsInt` always returns an `int` when completing normally; it can still throw unchecked exceptions such as `NumberFormatException`.
- **Finite numeric range.** If extracting monetary totals, quantities, or lengths into `int`, check ranges and overflow. Switch to `ToLongFunction<T>` and `mapToLong` when a larger `long` range is needed.
- **Do not assume lambdas are pure.** Even though `IntFunction` and `ToIntFunction` state input/output types clearly, a lambda body can still read mutable variables or cause side effects.
- **Stream is not required.** Both interfaces are reusable behavior types in any method accepting a callback, not only `Stream`.

## 11. Quick selection guide by problem statement

Try phrasing the requirement as "from ... to ..." and follow the table:

| Requirement | Direction | Choose |
|---|---|---|
| From an `int` sequence number create a `String` label | `int → String` | `IntFunction<String>` |
| From an `int` size create a `String[]` | `int → String[]` | `IntFunction<String[]>` |
| From a `Student` object get an `int` score | `Student → int` | `ToIntFunction<Student>` |
| From a `String` get its `int` length | `String → int` | `ToIntFunction<String>` |
| From an `int` compute the next `int` | `int → int` | `IntUnaryOperator` |
| From a `String` produce a boxed `Integer` | `String → Integer` | `Function<String,Integer>` (or `ToIntFunction<String>` if `int` is needed) |
| From an `int` determine true/false | `int → boolean` | `IntPredicate` |
| From a `String` convert to another `String` | `String → String` | `Function<String,String>` |

The selection rule does not require guessing from lambda names. Look at **the source parameter type, required result type, and SAM signature**; then decide whether to use primitive or boxed types.

## 12. Self-check questions

1. How do `IntFunction<String>` and `ToIntFunction<String>` differ in parameter and return value?
2. Why does `IntStream.mapToObj` need `IntFunction` while `Stream<String>.mapToInt` needs `ToIntFunction<String>`?
3. `String[]::new` takes an `int` size and returns `String[]`. Which interface does it match? Is an array primitive or reference?
4. If you need `int → int`, why does `IntUnaryOperator` express the contract better than `IntFunction<Integer>`?
5. Which method reference can express a `ToIntFunction<String>` that takes `"42"` and returns `42`?
6. Does `ToIntFunction<String>` guarantee not throwing `NumberFormatException` when given `"abc"`?
7. When combining `String → int → String`, which two interfaces handle the two legs, and what is the final type of the entire transformation?

**Summary answers:** (1) `IntFunction<String>: int → String`; `ToIntFunction<String>: String → int`. (2) Because the mapper input type is `int` in `IntStream`, whereas the required output type is `int` in `Stream<String>`. (3) `IntFunction<String[]>`; an array is an object/reference type. (4) Because both parameter and result are primitive `int`, reducing boxing needs. (5) `Integer::parseInt`. (6) No: the parser can throw an exception for invalid strings. (7) `ToIntFunction<String>` then `IntFunction<String>`; once combined, it can be represented by `Function<String,String>`.

**Key takeaway:** `IntFunction<R>` means **from `int` to `R`** (stepping **out** of primitive `int`), whereas `ToIntFunction<T>` means **from `T` to `int`** (stepping **into** primitive `int`). This is a difference in **conversion direction**, SAM method, and API choice—not just a naming difference.
