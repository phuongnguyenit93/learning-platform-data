# Tracking Execution Order and Intermediate Types in Function Composition in Java

## 1. Goal and mental model

Function composition turns multiple small processing steps into a reusable function. To read a function chain correctly, always answer **two independent questions**:

1. **Which step runs first, and which runs next?** The method names `andThen` and `compose` determine the order when the function is called, not merely the order in which variable names appear in the expression.
2. **What is the output type of each step, and what type does the next step accept?** The Java compiler checks compatibility between these types when building the function chain.

For example, with three transformations:

```text
A --f--> B --g--> C --h--> D
```

If `f` is `Function<A, B>`, `g` is `Function<B, C>`, and `h` is `Function<C, D>`, then `f.andThen(g).andThen(h)` has type `Function<A, D>`. When calling `apply(a)`:

```text
a (A)
  │ f.apply(a)
  ▼
b (B)
  │ g.apply(b)
  ▼
c (C)
  │ h.apply(c)
  ▼
d (D)
```

Note: an expression that **creates a composed function** does not mean all steps have executed. With `Function`'s default methods, the chain runs when `apply` is called on the composed function. Therefore, distinguish between **pipeline creation time** and **pipeline execution time**.

## 2. `andThen`: run the current function first, the next function after

Given:

```java
Function<A, B> f = /* ... */;
Function<B, C> g = /* ... */;

Function<A, C> pipeline = f.andThen(g);
```

This is **illustrative code for generic types**, not a standalone Java program; `A`, `B`, `C` are hypothetical types.

Rule:

```text
f.andThen(g).apply(a) = g.apply(f.apply(a))
                         ^ runs second
                 ^ runs first
```

- `f` accepts `A`, returns `B`.
- `g` accepts the `B` result of `f`, returns `C`.
- The whole chain accepts `A`, returns `C`.
- With multiple steps, `f.andThen(g).andThen(h)` executes in the order `f → g → h`.

In the actual API, `Function<T, R>.andThen` has parameter type `Function<? super R, ? extends V>` and returns `Function<T, V>`. That allows the next step to accept a **supertype** of `R`, and its result to be an appropriate **subtype** of `V`; the two generic declarations do not have to be written character-for-character identically.

## 3. `compose`: run the argument function first, then the current function

Given:

```java
Function<A, B> f = /* ... */;
Function<B, C> g = /* ... */;

Function<A, C> pipeline = g.compose(f);
```

This is also a **type illustration snippet**, not a standalone compilable file.

Rule:

```text
g.compose(f).apply(a) = g.apply(f.apply(a))
                          ^ runs second
                  ^ runs first
```

In other words:

- `f.andThen(g)`: "execute `f`, **then** `g`".
- `g.compose(f)`: "before executing `g`, execute `f`".

The two representations are equivalent in call order and value passing if `f` and `g` are fixed, but **there is no need to compare the identity of the two composed function objects** to conclude they are behaviorally equivalent.

| Expression | Execution order when calling `apply(x)` | Overall type |
| --- | --- | --- |
| `f.andThen(g)` | `f` → `g` | `A → C` |
| `g.compose(f)` | `f` → `g` | `A → C` |
| `f.andThen(g).andThen(h)` | `f` → `g` → `h` | `A → D` |
| `h.compose(g).compose(f)` | `f` → `g` → `h` | `A → D` |

When multiple steps are combined, the reliable way to read them is to draw data arrows from the **first input** to the **final output**, instead of trying to guess the order from nested parentheses.

## 4. Runnable Java 17+ example: logging each step and inspecting intermediate types

Create `FunctionOrderDemo.java`:

```java
import java.util.function.Function;

public class FunctionOrderDemo {
    static String normalize(String raw) {
        System.out.println("1.normalize: [" + raw + "]");
        return raw.trim();
    }

    static Integer parse(String digits) {
        System.out.println("2.parse: [" + digits + "]");
        return Integer.parseInt(digits);
    }

    static String describe(Integer number) {
        System.out.println("3.describe: " + number);
        return "double=" + (number * 2);
    }

    public static void main(String[] args) {
        Function<String, String> normalize = FunctionOrderDemo::normalize;
        Function<String, Integer> parse = FunctionOrderDemo::parse;
        Function<Integer, String> describe = FunctionOrderDemo::describe;

        // Build the chain: normalize/parse/describe have not run yet.
        Function<String, String> pipeline =
                normalize.andThen(parse).andThen(describe);

        System.out.println("Before apply");
        System.out.println(pipeline.apply(" 21 "));

        // Same data direction when written with compose:
        Function<String, Integer> firstTwo = parse.compose(normalize);
        System.out.println("Compose:");
        System.out.println(firstTwo.apply(" 7 "));
    }
}
```

Compile and run:

```bash
javac FunctionOrderDemo.java
java FunctionOrderDemo
```

Expected output:

```text
Before apply
1.normalize: [ 21 ]
2.parse: [21]
3.describe: 21
double=42
Compose:
1.normalize: [ 7 ]
2.parse: [7]
7
```

Analysis of the first call:

| Step | Function | Input value and type | Output value and type |
| --- | --- | --- | --- |
| 1 | `normalize` | `" 21 "` — `String` | `"21"` — `String` |
| 2 | `parse` | `"21"` — `String` | `21` — `Integer` |
| 3 | `describe` | `21` — `Integer` | `"double=42"` — `String` |

The type of the entire chain is `Function<String, String>`, **yet there is an intermediate value of type `Integer`**. Do not infer from the overall input/output types that every internal step also only processes `String`.

The line `Before apply` appears before the function logs, proving that creating `pipeline` does not run the transformations. In `System.out.println(pipeline.apply(...))`, the argument `pipeline.apply(...)` is evaluated first, so the logs of each stage appear before the result line `double=42`. With `parse.compose(normalize)`, the logs also show that `normalize` runs before `parse`.

## 5. Type analysis using function signatures

When a pipeline is complex, write a table of data types before writing code. For example, converting from input data to a receipt:

```text
String --parse--> Integer --price--> Long --format--> String
```

With:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Long> price = quantity -> quantity * 10L;
Function<Long, String> format = total -> "Total: " + total;

Function<String, String> receipt =
        parse.andThen(price).andThen(format);
```

This is a snippet located **inside a method or initializer block** that imports `java.util.function.Function`. Each output/input pair is validly connected: `Integer → Integer` and `Long → Long`. For example, `receipt.apply("3")` returns `"Total: 30"`.

The `andThen` method also supports compatibility via supertype–subtype relationships:

```java
Function<String, String> trim = String::trim;
Function<CharSequence, Integer> count = CharSequence::length;
Function<String, Integer> trimmedLength = trim.andThen(count);
```

When `trim` returns `String`, the `count` step can accept `CharSequence`, because `String implements CharSequence`. This is a valid connection, even though the declared generic types differ.

In contrast, the following chain is **type-incorrect**:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<String, String> upper = String::toUpperCase;

// Does not compile: parse returns Integer, upper accepts String.
Function<String, String> wrong = parse.andThen(upper);
```

This is an **intentional counterexample that does not compile**. The fix depends on the problem: if you want to uppercase before parsing, both the business meaning and conversion types must be reconsidered; if you want to format the numeric result after parsing, the next step must accept `Integer` (or an appropriate supertype):

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Number, String> label = n -> "number=" + n;
Function<String, String> correct = parse.andThen(label);
```

Here `Number` is a supertype of `Integer`. The compiler guarantees signature compatibility; **it does not prove** that every input string can be parsed. `"abc"` can still cause `NumberFormatException` at runtime.

## 6. Difference between type inference during composition and runtime types

In Java, `Function<T,R>` is a generic functional interface. When building a chain, the compiler infers type parameters based on the target type, the signatures of `compose`/`andThen`, and the declarations of the component functions. This is **static checking**.

At runtime, due to *type erasure*, generic types do not become full type tags for every step at runtime. You can debug using values, stage-level logging, and explicit type declarations, but you should not rely on `function.getClass()` or try to recover all generic parameters from a lambda object to determine the pipeline.

A good habit when encountering hard-to-read compiler errors:

1. Assign each transformation to a `Function<Input, Output>` variable with concrete types.
2. Write out the data arrows and check **output type of previous step → input type of next step**.
3. Chain two steps at a time, assigning to a variable with the expected type.
4. Only after types and behavior are correct, simplify into a single expression.

Example:

```java
Function<String, String> clean = String::trim;
Function<String, Integer> toNumber = Integer::parseInt;
Function<String, Integer> cleanNumber = clean.andThen(toNumber);
```

Explicit declarations can help distinguish type inference errors from ordering logic errors. For a lambda expression placed directly inside `andThen`, the parameter type is inferred from the output of the previous stage; if not clear enough, write the input type such as `(Integer n) -> n * 2` or put the lambda into a `Function<Integer, Integer>` variable.

## 7. Tracking a pipeline with a typed logging wrapper

When you do not want to put `println` directly inside each business function, you can wrap a function with a tracing function that **preserves the `A → B` signature**. Create `TracePipelineDemo.java`:

```java
import java.util.function.Function;

public class TracePipelineDemo {
    static <A, B> Function<A, B> trace(
            String name, Function<A, B> step) {
        return input -> {
            System.out.println(name + " input=" + input);
            B output = step.apply(input);
            System.out.println(name + " output=" + output);
            return output;
        };
    }

    public static void main(String[] args) {
        Function<String, String> trim =
                trace("trim", String::trim);
        Function<String, Integer> length =
                trace("length", String::length);

        Function<String, Integer> flow = trim.andThen(length);
        System.out.println("result=" + flow.apply("  Java  "));
    }
}
```

Run:

```bash
javac TracePipelineDemo.java
java TracePipelineDemo
```

Output:

```text
trim input=  Java  
trim output=Java
length input=Java
length output=4
result=4
```

The `trace` method accepts `Function<A,B>` and returns `Function<A,B>`, so adding logging **does not break the type chain**. We observe the intermediate value `"Java"`, then `4`. In a real environment, use a logger instead of `System.out`, attach clear stage names, do not log sensitive data, and only enable appropriate log levels. This wrapper adds logging side effects and execution overhead; logging should not be treated as a condition for pipeline correctness.

If you need to know the runtime type of an intermediate value, only check where truly necessary, handle `null`, and understand that `getClass()` reflects the class of the **value**, and cannot recover the generic signature of the entire pipeline. The data-flow types are primarily described by the `Function<A,B>` declarations at compile time.

## 8. Execution order also determines side effects, errors, and `null` values

Composing functions using `Function`'s default methods executes stages in the chosen sequence. Therefore:

- If the first stage logs, mutates state, or performs I/O, the side effect occurs before the next stage.
- If the previous stage throws an exception, the next stage is not called; the exception propagates to the caller of `apply` if no custom handling code is present.
- If the previous stage returns `null`, the next stage **may** receive `null`; whether it runs or throws an exception depends on the definition of the next stage. There is no automatic mechanism to skip `null`.
- Passing a `null` argument to `andThen(null)` or `compose(null)` is rejected with `NullPointerException` when creating the composition according to `Function`'s default methods. This differs from a valid stage returning `null` at runtime.
- Steps that hold state or call external services make order directly affect the result; do not arbitrarily change `f.andThen(g)` to `g.andThen(f)` just because both handle the same data type.

For example, with `Function<String, Integer> parse = Integer::parseInt;` and `Function<Integer, Integer> doubleValue = n -> n * 2;`, the expression `parse.andThen(doubleValue).apply("x")` throws `NumberFormatException` at the `parse` step; `doubleValue` has not run.

Having well-typed generics does not mean there are no runtime errors. Some transformations also require contracts on order and invertibility; for instance, after converting a string to a number, you cannot restore the exact original whitespace solely by an inverse transformation.

## 9. Distinguishing from other functional interface compositions

Not every method named `andThen` passes intermediate results according to the `Function<A,B>` rule:

| API | Order/characteristic | Data flow |
| --- | --- | --- |
| `Function.andThen` | Run current function then next function | Output of previous function is input of next function |
| `Function.compose` | Run `before` function then current function | Output of `before` function goes into current function |
| `Consumer.andThen` | Run first consumer then second | Both receive the **same argument**, no result passed because `accept` returns `void` |
| `Predicate.and` | Evaluate second condition only when first is `true` | Has **short-circuiting**, does not always run both |
| `Predicate.or` | Evaluate second condition only when first is `false` | Has **short-circuiting** |
| `BiFunction.andThen` | Call two-argument function first then transform result | `(T,U) → R → V` |

Intentional example of short-circuiting:

```java
Predicate<String> nonNull = value -> value != null;
Predicate<String> atLeastThree = value -> value.length() >= 3;
Predicate<String> valid = nonNull.and(atLeastThree);

// valid.test(null) == false and does not call atLeastThree.
// valid.test("Java") == true.
```

This is a snippet inside a method, requiring `import java.util.function.Predicate`. If the order is reversed to `atLeastThree.and(nonNull)`, calling `test(null)` will throw `NullPointerException` before the non-null check can run. With `Consumer.andThen`, the two actions are normally called sequentially, but if the first action throws an exception, the second action is not called.

In addition, a `Stream.map(...).filter(...)` pipeline uses **lazy evaluation** and may involve parallel processing; do not automatically apply the runtime timing and side-effect ordering model of `Function.andThen` to all Stream operations. In Streams, you must separately analyze the terminal operation, short-circuiting properties, and sequential/parallel characteristics.

## 10. Common mistakes and how to check

**Mistake 1 — Reading `compose` backwards.** When seeing `g.compose(f)`, immediately write `g(f(x))`; it becomes clear that `f` runs first.

**Mistake 2 — Looking only at the final type.** `Function<String,String>` can be `String → Integer → String`. Make a type table after each stage; do not assume all stages accept and return `String`.

**Mistake 3 — Connecting incompatible types and forcing a cast.** Raw casts or using raw `Function` types hide compiler guarantees and push errors to runtime. Fix the signatures and actual data direction of the steps.

**Mistake 4 — Thinking building the pipeline means it has run.** `Function<X,Y> combined = first.andThen(second);` only creates a composed function. Verify logs when calling `combined.apply(x)`.

**Mistake 5 — Ignoring the order of side effects.** For steps with I/O, state mutation, logging, or exceptions, changing the order can produce wrong results or prevent a step from running.

**Mistake 6 — Confusing `Function.andThen` with `Consumer`, `Predicate`, or `Stream`.** Each has its own rules for data passing, early stopping, and execution timing.

**Mistake 7 — Looking only at the lambda object when debugging.** `getClass()`, reference identity, and `toString()` of a lambda do not reveal the full intermediate types and execution order. Log at stage boundaries and keep type declarations clear.

## 11. Self-check exercise

Consider the following functions (snippet placed inside a method):

```java
Function<String, String> a = String::trim;
Function<String, Integer> b = String::length;
Function<Integer, Integer> c = n -> n + 10;

Function<String, Integer> result = c.compose(b).compose(a);
```

Answer before running:

1. With `result.apply("  ab  ")`, which function runs first?
2. What are the intermediate types after `a`, after `b`, and after `c`?
3. What is the final result?
4. Write the same pipeline using `andThen`.

Answer: sequence `a → b → c`; after `a` is `"ab"` of type `String`, after `b` is `2` of type `Integer`, after `c` is `12` of type `Integer`. The final result is `12`; the equivalent expression is `a.andThen(b).andThen(c)`, also of type `Function<String,Integer>`.

## 12. Practical rule of thumb

When reading or designing function composition, write out these two lines completely:

```text
Execution order: stage1 -> stage2 -> stage3
Type flow:       Input  -> Mid1   -> Mid2   -> Output
```

If you want function A to run before B, write `A.andThen(B)` or `B.compose(A)`. Check the signature of each connection, call `apply` when execution is needed, and use typed logging/wrappers to observe intermediate results. This helps distinguish **ordering** bugs, **compile-time type** bugs, and **data/runtime** bugs — three issues that often appear together when composing multiple functions.

**References:** Java SE API for `java.util.function.Function` (`compose`, `andThen`), `Consumer`, `Predicate`, and `BiFunction`; Java Language Specification on target typing and lambda expressions.
