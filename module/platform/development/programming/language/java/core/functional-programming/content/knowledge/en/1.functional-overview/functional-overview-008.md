# Learning Path for Functional Programming in Java and Required Foundational Knowledge

## 1. Objectives and Scope

**Functional programming (FP)** is a way of organizing programs around creating, combining, and applying functions to data. Instead of focusing on a sequence of commands that mutate state, we typically describe *how input data is transformed into a result*. Java is a multi-paradigm language: you can use functional thinking alongside object-oriented programming, loops, and traditional APIs. Using lambdas or Streams **does not automatically** make a piece of code a pure function.

This article is a **learning map** for the Java Core – functional-programming module: knowing what to prepare, in what order to learn, how to practice, and how to self-check. After this learning path, learners should be able to:

- Identify inputs, outputs, mutable state, and side effects of a processing operation.
- Read, write, and choose the right functional interface, lambda, and method reference.
- Implement data transformation pipelines with Streams, understanding when a Stream executes.
- Use `Optional` and function composition within an appropriate scope.
- Weigh readability, cost, errors, and safety when applying FP in real-world Java.

No prior experience with Haskell, Scala, or specialized functional programming libraries is required to get started.

## 2. Foundational Knowledge Before Starting

| Knowledge | Why it is needed | Self-check |
| --- | --- | --- |
| Variables, primitive and reference types; operators, `if`, `for` | Read filter conditions, transformations, distinguish values from objects | Filter a list of even numbers using a loop |
| Methods, parameters, return values, variable scope | Understand a function as a transformation with inputs/outputs | Write `int square(int x)` |
| Class, object, interface, basic inheritance | A functional interface is still an interface; lambdas have a target type | Declare an interface with one abstract method |
| Generics `List<T>`, `Map<K,V>`, parameterized types | `Stream<T>`, `Function<T,R>`, and `collect` results depend on generics | Write a method taking `List<String>` |
| Collections, `equals`, `hashCode`, element order | Streams often process collections; comparison and sorting require proper semantics | Sort a list, remove elements by condition |
| Checked/unchecked exceptions and `null` | Lambdas have limitations handling checked exceptions; `Optional` models potential absence | Distinguish `throw` and `throws`, check `null` |
| Reading Javadoc, running `javac`/`java`, using an IDE/debugger | Self-verify API signatures, data types, and actual behavior | Compile and run a Java class |

**Starting point:** if you still struggle when writing loops to manipulate a `List`, review methods, generics, and Collections before moving on to Streams. If you are already solid on those parts, you can start right away with functional interfaces and lambdas. The standalone runnable examples below use **JDK 17 or later**.

## 3. Core Mindset: Functions, Data, and Side Effects

A processing operation should be examined through three questions:

1. **What are the input and output?** For example, `priceWithTax(price)` takes a price and returns the price after tax.
2. **Does the result depend only on the input?** A pure function returns the same result for the same input and produces no observable side effects.
3. **Is anything modified externally?** Writing to a file, calling an API, updating a global variable, modifying a shared collection, or printing to the screen can all be side effects.

Illustrative example (methods inside a class, not a standalone program):

~~~java
static int doubleValue(int value) {
    return value * 2;          // Pure: does not modify external state
}

static int total = 0;
static void addToTotal(int value) {
    total += value;            // Has side effect: modifies shared variable
}
~~~

Prefer separating **pure computation** from **I/O and orchestration** when making code easy to test. Immutability reduces the risk of data being changed unintentionally; `String` and `record` support data modeling, and `List.of(...)` creates a structurally unmodifiable list. However, an unmodifiable `List` can still contain objects with mutable state. **Do not confuse a `final` reference or an unmodifiable list with deep immutability.**

Common mental model:

~~~text
Input data → filter → map → group/aggregate → result
                     ↘ side effects managed at program boundaries
~~~

Not every operation needs to be written in FP: stateful algorithms, resource-handling code, loop-optimized sections, or concise logic may be clearer in an imperative style.

## 4. Learning Path in Dependency Order

### Stage 1 — Separating Transformations from State

**Learn:** parameters/return values; pure vs. impure functions; copying vs. mutating in place; why shared state makes testing hard.

**Practice:** from a list of prices, create a list of discounted prices without modifying the input list. Write a separate function to compute the new price. Verify that calling it twice with the same input produces the same result.

**Mastered when:** you can pinpoint exactly which part computes and which part prints, saves data, or mutates objects.

### Stage 2 — Functional Interfaces and Lambdas

**Learn:** an interface with only **one abstract method** (SAM) is a valid target type for a lambda; `@FunctionalInterface` lets the compiler check the constraint. `default` methods, `static` methods, and methods from `Object` do not turn an interface into multiple SAMs. Syntax `x -> x + 1`, `(a, b) -> a + b`, block lambdas with `return`.

Commonly used types in `java.util.function`:

| Type | Meaning | When to choose |
| --- | --- | --- |
| `Predicate<T>` | `T -> boolean` | Filtering or checking a condition |
| `Function<T,R>` | `T -> R` | Transforming a value to another type |
| `UnaryOperator<T>` | `T -> T` | Transforming while keeping the same type |
| `Consumer<T>` | `T -> void` | Performing an operation with side effects |
| `Supplier<T>` | `() -> T` | Providing a value when called |
| `BiFunction<T,U,R>` | Two arguments produce one result | Combining two values |
| `Comparator<T>` | Comparing two values | Sorting or choosing an order |

Example snippet usable inside a method (with `import java.util.function.*;`):

~~~java
Predicate<String> hasText = s -> s != null && !s.isBlank();
Function<String, Integer> length = String::length;

boolean valid = hasText.test("Java");  // true
int count = length.apply("Java");      // 4
~~~

**Important distinction:** a lambda is **not** a standalone untyped method; the compiler infers its type from the *target type*. A lambda only captures `final` or *effectively final* local variables; referenced objects can still be mutated (which does not make the operation concurrency-safe).

**Mastered when:** you can convert simple anonymous classes into lambdas, explain the input/output of `Predicate` and `Function`, and know when a custom interface is needed.

### Stage 3 — Method References and Function Composition

**Learn:** `Type::staticMethod`, `object::instanceMethod`, `Type::instanceMethod`, `Type::new`. Use a method reference only when it preserves semantics and improves readability. Learn `Function.compose`, `Function.andThen`, `Predicate.and`, `or`, and `negate`.

~~~java
Function<String, String> trim = String::trim;
Function<String, String> upper = String::toUpperCase;
Function<String, String> normalize = trim.andThen(upper);

String result = normalize.apply("  java  "); // "JAVA"
~~~

`trim.andThen(upper)` means **trim first, then upper**; `trim.compose(upper)` runs in the reverse order. Consider `null` and input validity rather than assuming every processing chain is safe.

**Mastered when:** you can express a small pipeline using named functions without overusing hard-to-read nested lambdas.

### Stage 4 — Stream API: Pipeline Data Processing

**Learn:** creating streams from collections; intermediate operations `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`; terminal operations `toList`, `forEach`, `count`, `reduce`, `collect`, `findFirst`, `anyMatch`. Learn primitive streams `IntStream`, `LongStream`, `DoubleStream` for convenient sum/average calculations and avoiding boxing when appropriate.

Pipelines are **lazy**: most intermediate operations only execute when a terminal operation is encountered. A consumed stream **cannot be reused**. A stream is not a data store, and calling `stream()` does not automatically copy the source collection. Understand *encounter order*, sorting order, short-circuiting, and side effects.

~~~java
List<String> names = List.of("An", "Bình", "Anh");
List<String> result = names.stream()
        .filter(name -> name.startsWith("A"))
        .sorted()
        .toList(); // ["An", "Anh"] in String comparison order
~~~

**Mastered when:** you can read the `Stream<T>` type after each step, know which operations return a new stream vs. a result, and know when a loop is more appropriate.

### Stage 5 — Data Aggregation and Optional

**Learn:** `Collectors.groupingBy`, `partitioningBy`, `mapping`, `counting`, `summingInt`, `toMap` (must have a duplicate-key handling strategy), `joining`. Distinguish `reduce`, which aggregates into a single value, from `collect`, which accumulates into a result container.

`Optional<T>` represents a value that **may or may not be present**. Prefer `map`, `flatMap`, `filter`, `ifPresent`, `orElseGet`, `orElseThrow` in appropriate situations. `Optional` does not replace every use of `null`, and is generally more suitable for **return values** than for fields or arbitrary parameters. `orElse(value)` evaluates its argument eagerly; `orElseGet(supplier)` only invokes the supplier when the Optional is empty.

~~~java
String displayName = Optional.ofNullable(rawName)
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .orElse("Khách");
~~~

The snippet above assumes `rawName` is a nullable `String` variable; the code is a fragment placed inside a method with appropriate imports.

**Mastered when:** you can aggregate real-world data, clearly explain the result type, and explain behavior when elements are absent.

### Stage 6 — Correctness, Testing, and Reasonable Optimization

**Learn:** testing pure functions with input/output tables and empty, duplicate, `null`, and boundary cases; reading stack traces in lambdas; how checked exceptions interact with SAMs. Do not swallow exceptions just to fit a lambda signature.

Understand that `parallelStream()` **is not guaranteed to be faster** and can make code incorrect if it mutates shared mutable state. Consider whether data is large enough, splitting/merging overhead, ordering, associativity of reduction, shared state, and benchmarking. With parallel `reduce`, the combiner operator must satisfy associativity (*associative*) and have a proper identity value (*identity*). Avoid using `forEach` to update a shared `ArrayList` from a parallel stream.

**Mastered when:** you can prove an approach is correct and readable before considering performance, and you test edge cases rather than only happy-path data.

## 5. Complete Example: Moving from a Loop to a Pipeline

Problem: from a list of products, keep only products that are **available** with a price **at most 200,000 VND**, output the list of names in alphabetical order, and calculate the total price. The two implementations below produce the same result; the second emphasizes data transformations.

Create the file **`LearningPathDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Predicate;

public class LearningPathDemo {
    record Product(String name, int price, boolean available) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Sách Java", 250_000, true),
                new Product("Bút", 20_000, true),
                new Product("Sách SQL", 180_000, true),
                new Product("Sách cũ", 100_000, false)
        );

        // Approach 1: imperative; explicitly states each update.
        List<String> imperativeNames = new ArrayList<>();
        int imperativeTotal = 0;
        for (Product product : products) {
            if (product.available() && product.price() <= 200_000) {
                imperativeNames.add(product.name());
                imperativeTotal += product.price();
            }
        }
        Collections.sort(imperativeNames);

        // Approach 2: describes criteria and transformations.
        Predicate<Product> eligible =
                p -> p.available() && p.price() <= 200_000;

        List<String> functionalNames = products.stream()
                .filter(eligible)
                .map(Product::name)
                .sorted()
                .toList();

        int functionalTotal = products.stream()
                .filter(eligible)
                .mapToInt(Product::price)
                .sum();

        System.out.println(functionalNames);
        System.out.println(functionalTotal);
        System.out.println(imperativeNames.equals(functionalNames)
                && imperativeTotal == functionalTotal);
    }
}
~~~

Run with JDK 17+ in a UTF-8-capable terminal:

~~~bash
javac -encoding UTF-8 LearningPathDemo.java
java LearningPathDemo
~~~

Expected output:

~~~text
[Bút, Sách SQL]
200000
true
~~~

**Step-by-step reading:** `filter(eligible)` keeps eligible products; `map(Product::name)` extracts only the name; `sorted()` sorts the names; `toList()` terminates the pipeline and produces a list that cannot be modified via `add/remove` per the `Stream.toList()` API contract. The other pipeline uses `mapToInt` to turn prices into an `int` stream and `sum` to aggregate. The two pipelines traverse the data twice; in a small problem, clarity matters more than micro-optimization. When processing large data or sources with high access cost, you can consider collecting results in a single pass with an appropriate collector or a clear loop. Do not assume pipelines are always faster.

**Why do we still need to understand the imperative approach?** Both approaches have clear semantics; use a loop when you must maintain multiple interrelated states, handle intentional early exits, or when a stream description makes the code hard to follow. Choose the approach that is easiest for your development team to verify.

## 6. Common Mistakes to Learn to Spot Early

| Mistake/Misconception | Harm | How to handle |
| --- | --- | --- |
| Assuming lambdas are always pure functions | Hidden side effects make behavior unpredictable | Audit state being read/written externally |
| Using `map` just to call `println` | Turns a transformation step into a side-effect operation | Isolate logging at boundaries; use `forEach` when a side effect is intended |
| Forgetting the terminal operation | No transformation occurs because the pipeline stays lazy | Specify a terminal step such as `toList` or `count` |
| Reusing the same `Stream` | May throw `IllegalStateException` | Create a new stream from the source when a new pass is needed |
| Calling `Optional.get()` without checking | `NoSuchElementException` when empty | Use `orElseThrow`/`orElseGet` or handle absence explicitly |
| Calling `toMap` when keys may duplicate | `IllegalStateException` due to duplicate key | Choose a merge function matching the semantics |
| Modifying the source collection inside a pipeline | Can cause errors and destroy predictability | Avoid mutating the source while a stream is traversing; create a new result |
| Updating a shared variable in `parallelStream` | Race conditions, unstable results | Use an appropriate reduction/collector and verify |
| Confusing `==` with `equals` on objects | Incorrect filtering/comparison | Use type-appropriate value comparison; consider `Objects.equals` |
| Overusing overly long stream chains | Hard to debug and hard to explain types | Name predicates/functions or extract methods, use a loop when clearer |

## 7. Suggested Practice Plan

This is a **learning sequence**, not a fixed time commitment. Only move to the next stage when you can explain the results you produce.

| Session | Focus exercise | Proof of completion |
| --- | --- | --- |
| 1 — Foundations | Rewrite a price calculation function without mutating parameters/external variables; review `List<T>` | Calling twice with the same input returns the same value |
| 2 — Lambdas | Write a `Predicate<Integer>` checking positive numbers, a `Function<String,Integer>` getting string length | Can explain target type and effectively final |
| 3 — Function composition | Normalize names with `trim` then uppercase; combine two predicates | Distinguish `andThen`/`compose` order |
| 4 — Basic Streams | Filter even numbers, square, sort, take 5 elements | State the exact data type through each operation |
| 5 — Advanced Streams | `flatMap` nested lists; group transactions by category; handle duplicate keys | Cross-check results with a loop |
| 6 — Optional and errors | Handle potentially empty names; add edge cases | Never call `get` unconditionally |
| 7 — Capstone exercise | Complete a product/order list report | Working program, correct stdout, tested with empty data |
| 8 — Review, verification | Compare loop/stream; examine boxing, side effects, and parallel | Explain choices clearly, no premature gut-feeling optimization |

**Progressive self-practice exercises:**

1. Given a `List<Integer>`, compute the sum of squares of even numbers using a loop, then rewrite it with `mapToInt` and `sum`. Test an empty list (sum is 0), negative numbers, and large values; consider `int` overflow.
2. Given a `List<String>` with duplicate names/empty strings, produce a list of non-empty, deduplicated, sorted names. Test the `null` case separately: `List.of` cannot contain `null`, so define a clear input data contract.
3. Given transactions with `category` and `amount`, compute the total amount per category using `Collectors.groupingBy` combined with `summingInt`. Compare the result with a loop.
4. Write a method returning `Optional<Product>` to find the first product matching a condition. Write tests for both present and absent cases.
5. Try using a side effect inside `map`, then explain why it is hard to test; fix it into a pure transformation and place the write/print operation at the end.

### How to Test Practice Exercises

- Start with small data whose result can be computed by hand, then add empty data, non-matching items, duplicate elements, and boundary values.
- Use `equals` to compare results between the loop version and the stream version when both share the same ordering requirement; avoid comparing by `==` reference.
- When floating-point numbers are involved, consider precision errors; when summing monetary values, consider `long` or `BigDecimal` depending on the domain. Do not round arbitrarily.
- If you modify code to run in parallel, re-verify correctness and only measure performance on representative data/scenarios.

## 8. Self-Assessment Criteria and Next Steps

You are ready to dive into the specialized topics of the module when you can answer on your own:

- How does `Function<T,R>` differ from `Predicate<T>`, `Consumer<T>`, and `Supplier<T>`?
- Why must local variables captured by a lambda be effectively final? Does that protect every object from mutation?
- How does a `filter → map → collect` pipeline differ from a loop? When does the pipeline actually execute?
- How does `map` differ from `flatMap`? Do `Stream.toList()` and `Collectors.toList()` guarantee the same mutability? (**No**: `Stream.toList()` returns an unmodifiable list; `Collectors.toList()` makes no guarantee about the list type or mutability.)
- Why should `Optional.get()` not be used arbitrarily? How do `orElse` and `orElseGet` differ when computing a default value?
- When does computation with side effects cause bugs, especially in parallel streams?
- Can you explain with concrete data why the chosen approach is correct, clear, and easy to test?

**Next reading direction:** progress sequentially from Java functional interfaces and lambdas/method references to the Stream API, collectors/reduction, Optional, pure function design, and performance/concurrency limits. Use the Javadoc of `java.util.function`, `java.util.stream`, and `java.util.Optional` as your reference for API signatures and contracts. The goal is to know *when* the functional paradigm makes code easier to understand, safer, and more testable, while still flexibly using other Java constructs when appropriate.
