# Function.compose() and Function.andThen() in Java

## 1. Function composition mindset: the output of the previous function is the input of the next

In functional programming, **function composition** allows combining small transformations into a larger transformation. Instead of calling multiple nested functions, Java provides two default methods on `java.util.function.Function<T,R>`:

- `andThen(after)`: executes the **current function first**, then executes `after`.
- `compose(before)`: executes the **`before` function first**, then executes the current function.

For example, let `f(x) = x + 3` and `g(x) = 2 * x`. With input `5`:

```text
f.andThen(g): 5 -> f -> 8 -> g -> 16
f.compose(g): 5 -> g -> 10 -> f -> 13
```

The two results are **different**. If there is only one thing to remember, it is: **the order in which functions are written in code does not always mean the execution order**. `compose` calls the argument first, whereas `andThen` calls the receiver object first.

In Java, `Function<T,R>` is a functional interface with the abstract method `R apply(T value)`. Lambdas, method references, and an object implementing `Function` can all be composed this way. The result of composition is also a `Function`, which can be stored, passed along, or invoked via `apply`.

## 2. API signatures and type rules

The primary method of `Function<T,R>`:

```java
R apply(T value);
```

The two composition methods (conceptual signatures accurate to the Java generic API):

```java
default <V> Function<T, V> andThen(
        Function<? super R, ? extends V> after);

default <V> Function<V, R> compose(
        Function<? super V, ? extends T> before);
```

These are **reference signatures for reading types**, not a standalone class to copy and compile; the implementation already exists in the standard library.

Suppose `f` has type `Function<T,R>`:

| Call | Passed-in function | Resulting function | Processing order |
| --- | --- | --- | --- |
| `f.andThen(g)` | `g: R → V` or a wider input type, output compatible with `V` | `Function<T,V>` | `g(f(x))` |
| `f.compose(g)` | `g: V → T` or a wider input type, output compatible with `T` | `Function<V,R>` | `f(g(x))` |

The wildcard forms `? super` for the input type and `? extends` for the output type allow the API to accept compatible functions according to supertype/subtype relationships. This is why one should not state that the two types must match down to every generic parameter.

When solving exercises, write out the type chain like this:

```text
String --trim--> String --parse--> Integer --label--> String
```

Each subsequent arrow is only valid when **the result type of the previous function matches the parameter type of the next function**. Java checks this at compile time, without waiting for `apply`.

## 3. andThen(): reading forward from left to right

Suppose two functions:

```java
Function<Integer, Integer> addThree = x -> x + 3;
Function<Integer, Integer> doubleIt = x -> x * 2;
```

These two statements are inside a method with `import java.util.function.Function;`. When writing:

```java
Function<Integer, Integer> result = addThree.andThen(doubleIt);
System.out.println(result.apply(5)); // 16
```

Execution order:

1. `addThree.apply(5)` gives `8`.
2. `doubleIt.apply(8)` gives `16`.
3. `result.apply(5)` returns `16`.

Therefore `addThree.andThen(doubleIt)` is equivalent in transformation to `x -> doubleIt.apply(addThree.apply(x))`, ignoring differences in function objects and unrelated error handling.

The keyword `then` in `andThen` suggests "**do the current task, then do the next task**". This is especially convenient for chained preprocessing/validation/conversion/formatting steps.

## 4. compose(): reading the argument function first

Still using the two functions above:

```java
Function<Integer, Integer> result = addThree.compose(doubleIt);
System.out.println(result.apply(5)); // 13
```

Execution:

1. `doubleIt.apply(5)` gives `10`.
2. `addThree.apply(10)` gives `13`.
3. `result.apply(5)` returns `13`.

`addThree.compose(doubleIt)` is equivalent to `x -> addThree.apply(doubleIt.apply(x))`.

Common point of confusion: the usual method-reading style `addThree.compose(...)` makes beginners think `addThree` runs first because it stands to the left of the dot. However, in `compose`, **the function passed into `before` runs first**.

For two type-compatible functions `f` and `g`:

```text
f.andThen(g)  = g ∘ f
f.compose(g)  = f ∘ g
f.andThen(g)  = g.compose(f)
```

The symbol `∘` is the mathematical composition notation. The equalities here describe the result of applying the same input to pure functions; in applications with side effects, **the order of side effects** must also be considered, not just the final value.

## 5. Complete Java 17 example and exact output

Save the following content as `FunctionCompositionDemo.java`:

```java
import java.util.function.Function;

public class FunctionCompositionDemo {
    public static void main(String[] args) {
        Function<Integer, Integer> addThree = x -> x + 3;
        Function<Integer, Integer> doubleIt = x -> x * 2;

        System.out.println(addThree.andThen(doubleIt).apply(5));
        System.out.println(addThree.compose(doubleIt).apply(5));

        Function<String, String> trim = String::trim;
        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, String> label = n -> "value=" + n;
        Function<String, String> pipeline = trim.andThen(parse).andThen(label);
        System.out.println(pipeline.apply(" 21 "));

        Function<String, Integer> afterParse = addThree.compose(parse);
        Function<String, Integer> afterParseAlternative = parse.andThen(addThree);
        System.out.println(afterParse.apply("21"));
        System.out.println(afterParseAlternative.apply("21"));

        Function<CharSequence, String> asString = CharSequence::toString;
        Function<String, Integer> length = String::length;
        Function<CharSequence, Integer> lengthOfText = length.compose(asString);
        System.out.println(lengthOfText.apply(new StringBuilder("abc")));

        Function<Integer, Integer> identity = Function.identity();
        System.out.println(identity.andThen(addThree).apply(5));

        StringBuilder trace = new StringBuilder();
        Function<Integer, Integer> f = x -> {
            trace.append("f ");
            return x + 1;
        };
        Function<Integer, Integer> g = x -> {
            trace.append("g ");
            return x * 3;
        };
        Function<Integer, Integer> firstF = f.andThen(g);
        System.out.println("before=" + trace);
        System.out.println(firstF.apply(2));
        System.out.println("order=" + trace);
        trace.setLength(0);
        System.out.println(f.compose(g).apply(2));
        System.out.println("order=" + trace);

        Function<Number, Double> scale = n -> n.doubleValue() * 1.5;
        Function<String, Double> parseAndScale = scale.compose(Integer::valueOf);
        System.out.println(parseAndScale.apply("4"));

        Function<Integer, Number> widen = n -> n;
        Function<Integer, String> wideThenLabel = widen.andThen(n -> "n=" + n);
        System.out.println(wideThenLabel.apply(7));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 FunctionCompositionDemo.java
java FunctionCompositionDemo
```

Output:

```text
16
13
value=21
24
24
3
8
before=
9
order=f g 
7
order=g f 
6.0
n=7
```

**Note:** in the two lines `order=f g ` and `order=g f `, there is a trailing space because the program uses `trace.append("f ")`/`trace.append("g ")`. This is the actual result tested with `javac --release 17`, not an assumption.

Key parts of the program:

- `addThree.andThen(doubleIt)` returns `16`; `addThree.compose(doubleIt)` returns `13`.
- `trim.andThen(parse).andThen(label)` converts a string with whitespace into the label string `value=21`.
- `addThree.compose(parse)` and `parse.andThen(addThree)` give the same result `24`: different ways of writing it, but the execution order is **parse first, add after** in both cases.
- `length.compose(asString)` demonstrates composing functions with multiple data types, accepting `CharSequence` and returning `Integer`.
- `Function.identity()` preserves the input value, so chaining `addThree` on input `5` returns `8`.
- The two logging functions `f` and `g` show that **creating the composed function does not run the bodies yet**, and when `apply` is called, the order is confirmed by `StringBuilder`.
- The `scale.compose(Integer::valueOf)` and `widen.andThen(...)` parts show the use of supertype/subtype and wildcards in the API signatures.

This example is written to run standalone on Java 17+, without external libraries.

## 6. Practical processing chain: trim → parse → label

A small pipeline typically consists of three steps:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = n -> "value=" + n;

Function<String, String> pipeline =
        trim.andThen(parse).andThen(label);
```

The declarations are placed inside a method that has imported `Function`.

Type analysis:

| Stage | Input type | Output type |
| --- | --- | --- |
| `trim` | `String` | `String` |
| `parse` | `String` | `Integer` (from boxed `int`) |
| `label` | `Integer` | `String` |
| `pipeline` | `String` | `String` |

Calling `pipeline.apply(" 21 ")` sequentially produces `"21"`, `21`, `"value=21"`.

Read the `andThen` chain as a **left → right** pipeline, convenient when an input must pass through multiple steps.

Equivalent written with `compose`:

```java
Function<String, String> samePipeline =
        label.compose(parse).compose(trim);
```

At runtime, `trim` still runs first, then `parse`, then `label`. The `compose` syntax reads **right → left** in terms of execution order. Both expressions produce a function that takes `String` and returns `String`.

Do not think of `compose` as *inverting* the result of a function. It **reverses the order of two transformations in how they are combined**, not computing an inverse function.

## 7. Composing Functions with different types

The strength of composition does not lie in `int → int` examples, but in the ability to transition across multiple types:

```java
Function<CharSequence, String> asString = CharSequence::toString;
Function<String, Integer> length = String::length;
Function<CharSequence, Integer> lengthOfText =
        length.compose(asString);
```

These are three illustrative statements in a method that has imported `Function`. `lengthOfText.apply(new StringBuilder("abc"))` returns `3`: `StringBuilder` implements `CharSequence`, `asString` turns it into `String`, and `length` returns `int` (boxed to `Integer`).

Instead of saying "two functions can be composed if they have the same type", check the **junction point**:

```text
asString: CharSequence -> String
length:   String       -> Integer

asString.andThen(length): CharSequence -> Integer
length.compose(asString): CharSequence -> Integer
```

The junction point is `String`, while the final input type and final output type **do not need to be the same**.

If composed in the opposite direction where input/output are incompatible, `javac` will reject it. Casting to raw `(Function)` to "bypass" the check usually just defers the error to runtime and loses type safety.

## 8. Wildcards and generics: why use ? super and ? extends?

The `andThen` signature has `Function<? super R, ? extends V>`. This carries two meanings:

1. `? super R` allows the next function to accept **`R` or a supertype of `R`**. If the previous function returns `Integer`, the next function can handle `Number` or `Object`.
2. `? extends V` allows the next function to produce **`V` or a subtype of `V`**. For example, a function returning `Double` can be handled in a context expecting `Number`.

Similarly, `compose` accepts `Function<? super V, ? extends T>`: the previous function must produce a value compatible with the **input `T`** of the current function.

Example:

```java
Function<Number, Double> scale = n -> n.doubleValue() * 1.5;
Function<String, Double> parseAndScale =
        scale.compose(Integer::valueOf);
```

`Integer::valueOf` creates an `Integer` from a string, and `Integer` is a subtype of `Number`; therefore it can be passed to `scale` which accepts `Number`. `parseAndScale.apply("4")` gives `6.0`.

An example with a general result type:

```java
Function<Integer, Number> widen = n -> n;
Function<Integer, String> wideThenLabel =
        widen.andThen(number -> "n=" + number);
```

Even though `widen` returns a declared type of `Number`, the lambda `number -> ...` still receives the appropriate target type. Read the generic signature of each method instead of assuming everything must be `Function<Integer,Integer>`.

**Note on `Integer` and `int`:** `Function<T,R>` uses reference types. Integer transformations may incur boxing/unboxing; if used on a hot path and only handling primitive types, consider specialized interfaces (`IntUnaryOperator`, `IntFunction`, `ToIntFunction`), but do not assume they have **both** `compose` and `andThen` methods like `Function`.

## 9. Function.identity() and the identity element of composition

`Function.identity()` returns a `Function<T,T>` with the behavior `x -> x`:

```java
Function<Integer, Integer> identity = Function.identity();
Function<Integer, Integer> addThree = x -> x + 3;

System.out.println(identity.andThen(addThree).apply(5)); // 8
System.out.println(addThree.compose(identity).apply(5)); // 8
```

The statements are inside a method that has imported `Function`. Identity preserves the value, so for pure functions and compatible types:

```text
identity.andThen(f) = f
f.andThen(identity) = f
identity.compose(f) = f
f.compose(identity) = f
```

The equalities here mean **equivalence in value when applied**, not asserting that the Java object created by `andThen`/`compose` has the same identity (`==`) as `f`.

This property helps build processing chains incrementally. You can start from identity and append appropriate transformations, as long as you choose the right generic types and handle null/exceptions as needed.

## 10. Execution timing, side effects, and call order

When writing `Function<Integer,Integer> h = f.andThen(g);`, Java creates a composed function. **The bodies of `f` and `g` are not automatically called just by creating `h`**. They are called when `h.apply(x)` runs. This behavior matters if a lambda logs, updates state, or accesses external systems.

In a full program, with:

```java
StringBuilder trace = new StringBuilder();
Function<Integer,Integer> f = x -> {
    trace.append("f ");
    return x + 1;
};
Function<Integer,Integer> g = x -> {
    trace.append("g ");
    return x * 3;
};
```

The snippet belongs to a method body and has imported `Function`. After creating `f.andThen(g)`, `trace` is still empty. Calling `apply(2)` gives `9`, logging the order `f g `. Switching to `f.compose(g).apply(2)` gives `7`, logging `g f `.

Because the order **actually changes**, the two compositions are not commutative by default. They only produce the same result in special situations.

Also distinguish `Function.andThen` from `Stream.map`: a composed `Function` can be passed to a stream, but a stream is **lazy** with respect to intermediate operations. `stream.map(composed)` does not do work immediately; an appropriate terminal operation triggers processing according to the Stream mechanism.

For business data, prefer *pure functions*: do not overwrite shared state, do not depend on call timing, and return consistent results for the same input. This makes reusing and testing transformation chains easier. If there are side effects, the order must be explicitly considered.

## 11. Error handling, null, and exceptions

The two composition methods **do not automatically catch exceptions** thrown inside `apply`. For example:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<String, Integer> plusOne = parse.andThen(n -> n + 1);
```

These are illustrative statements placed in a method with `Function` imported. `plusOne.apply("7")` gives `8`, but `plusOne.apply("abc")` throws `NumberFormatException`; the error from `parse` propagates and the subsequent function **is not called** if the previous function fails.

Handling principles:

- **Validation before parsing:** when possible, place a data validation step before running the conversion function, or design a conversion function that returns a result type representing the error.
- **Wrap exceptions at appropriate boundaries:** call `apply` inside `try/catch` when a business-level response is needed; avoid silently swallowing errors.
- **Checked exceptions:** the `Function.apply` method does not declare `throws` for any checked exception, so its lambda cannot directly throw an unhandled checked exception. You can handle it inside the lambda or design a custom functional interface with `throws`.
- **Null `before` or `after` argument:** `compose(null)` and `andThen(null)` throw `NullPointerException` per the API contract. Do not confuse this with a function receiving a **null input value**: whether a null input is valid depends on the function body.
- **Null produced by a step:** the next step may encounter `NullPointerException` if it does not support null; `Function` does not automatically check or turn null into a default value.

Do not assume that `compose()` or `andThen()` have retry, rollback, error-skipping, or null-handling features on behalf of application code. They only orchestrate the order of function application.

## 12. Common compilation errors or misconceptions

| Misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| `f.andThen(g)` executes `g` first | `andThen` always calls the current function first | Read as `g(f(x))` |
| `f.compose(g)` executes `f` first | `compose` calls `before` first | Read as `f(g(x))` |
| The two compositions always give the same result | Function order may not be commutative | Test with an input like `5`, or verify with a unit test |
| Can only compose when all functions have the same `T` and `R` | Only requires type compatibility at the **junction point** | Write the type chain `A → B → C` |
| `Function<Integer,Integer> wrong = f.andThen(s -> s.length())` | `s` in the second lambda is `Integer`, which has no `length()` | Use a function that handles `Integer` or change the previous output |
| `Function<String,Integer> wrong = parse.compose((Integer n) -> n + 1)` | The `before` function produces `Integer`, but the expected input type is `String` | Use `parse.andThen(n -> n + 1)` |
| Creating a composed function runs all steps | Function bodies do not run until `apply` is called | Call `apply`, or pass the function to an executing API |
| `compose` inverts a function | Composition is different from an inverse function | Need a separate inverse function, if one exists |
| Use `Function` for all `void` behaviors | `Function<T,R>` has a result `R` | Look at `Consumer<T>`, `Runnable` if only performing an action |
| Every functional interface has `compose` and `andThen` like `Function` | Each functional interface's API has its own set of methods | Read the Javadoc: `Predicate` has `and`/`or`, `Consumer` has `andThen`, `BiFunction` has `andThen` |

The two "wrong" code snippets in the table are **intentional counterexamples that do not compile**; they are not part of the sample program. `javac --release 17` was used to confirm the respective type-error cases.

## 13. Distinguishing related APIs

`Function<T,R>` describes a transformation step with **one input and one output**. Java has other interfaces with method names that are easy to confuse:

- `UnaryOperator<T>` extends `Function<T,T>`, so it can use the composition methods of `Function` (the declared return type of the composed methods is still `Function<...>`).
- `BiFunction<T,U,R>` accepts **two inputs** and has `andThen` to process the result, but does not have a corresponding `compose` like `Function`.
- `Consumer<T>` describes a `void` operation. `Consumer.andThen` chains **two consuming operations** in order, without producing a `T → R` transformation.
- `Predicate<T>` returns `boolean` and has `and`, `or`, `negate` to combine logical conditions. Do not equate `Predicate.and` with `Function.andThen`.
- Primitive-specialized interfaces such as `IntUnaryOperator` have their own APIs, e.g., `IntUnaryOperator.compose` and `IntUnaryOperator.andThen` for `int → int`; check the Javadoc of each interface instead of assuming the generic signatures are identical.

API selection rule: **want to transform from T to R**, choose `Function<T,R>`; **want an action that returns no result**, choose `Consumer<T>`; **want a true/false condition**, choose `Predicate<T>`. Only then look at the appropriate composition method.

## 14. Exercises and solutions

**Exercise 1 — Order.** Given `f(x)=x-2`, `g(x)=x*x`, `x=6`. Compute `f.andThen(g)` and `f.compose(g)`.

Answer: `f.andThen(g).apply(6)` gives `(6-2)^2=16`. `f.compose(g).apply(6)` gives `6^2-2=34`.

**Exercise 2 — Composing different types.** Given `trim: Function<String,String>`, `parse: Function<String,Integer>`, `doubleIt: Function<Integer,Integer>`. Create a function accepting `String` and returning `Integer` in the order trim → parse → double.

```java
Function<String, Integer> pipeline =
        trim.andThen(parse).andThen(doubleIt);
```

This is an illustrative statement for use in a method that has declared the three functions with the same names and imported `Function`. The equivalent written with `compose` is `doubleIt.compose(parse).compose(trim)` with the same type contract.

**Exercise 3 — Reading the return type.** What type does chaining `Function<String,Integer> parse` with `Function<Integer,String> label` using `andThen` produce?

Answer: `Function<String,String>`, because the input is still `String`, and the final output is `String`.

**Exercise 4 — Distinguishing side effects.** Given `f` logs `F`, `g` logs `G` to a log. In what order do `f.andThen(g).apply(x)` and `f.compose(g).apply(x)` log?

Answer: the first logs `FG`; the second logs `GF`, assuming both steps complete normally and no other step logs. Do not reorder execution for "optimization".

**Exercise 5 — Identifying errors.** Given `Function<String,Integer> parse = Integer::parseInt;`. Why is `parse.andThen(s -> s.trim())` invalid?

Answer: the parameter `s` of the second function has type `Integer`, so it does not have `trim()`. If you want to trim before parsing, write `parse.compose(String::trim)` or `((Function<String,String>) String::trim).andThen(parse)` in a clear type context.

**Exercise 6 — Identity.** With `Function<Integer,Integer> addThree = n -> n + 3;`, what is the value of `addThree.andThen(Function.identity()).apply(10)`?

Answer: `13`; identity does not alter the output of `addThree`.

## 15. Quick summary

1. **`f.andThen(g)` = `g(f(x))`**: calls `f` first, then `g`.
2. **`f.compose(g)` = `f(g(x))`**: calls `g` first, then `f`.
3. Functions only need **type compatibility at the junction point**; the initial input and final output do not need to match.
4. Both methods create a **new Function**; the function bodies are executed when `apply` is called.
5. `Function.identity()` is a value-preserving transformation, useful as the identity element in composition.
6. Side effects, null, and exceptions must still be handled per business logic; order matters and is observable.
7. When encountering generic errors, write out the input/output type chain of each step and then choose the appropriate `andThen` or `compose`.

Official documentation: [Java 17 `Function` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html), including `apply`, `compose`, `andThen`, `identity`; and [Java Language Specification §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).
