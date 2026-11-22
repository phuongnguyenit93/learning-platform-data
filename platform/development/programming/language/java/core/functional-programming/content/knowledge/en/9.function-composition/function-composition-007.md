# Currying and Partial Application Using Lambdas in Java

## 1. Problem and goals

A function accepting two or more arguments can be structured in multiple ways. In Java, learners are used to writing:

~~~java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;
int result = add.apply(2, 3); // 5
~~~

If we frequently need to add a fixed number, or pre-configure a calculation and reuse it many times with data arriving later, passing all arguments on every call is not always convenient. Two related techniques are:

- **Currying:** transforming a multi-argument function into a **chain of functions**, where each function accepts one argument and returns the next function, until enough data is received to compute the result.
- **Partial application:** **fixing one or more arguments** of a multi-argument calculation, creating a new function that only awaits the remaining arguments.

The two techniques are close but **not synonymous**. Currying is a structural transformation of a function's signature, whereas partial application is the operation of creating a specialized function by fixing parameters. Currying can help perform partial application, but partial application can be done directly from a `BiFunction` without currying.

In the Java core – functional programming module, we will use **lambdas**, functional interfaces in `java.util.function`, and generics to build these two techniques without external libraries.

After this lesson, you should be able to:

1. Explain the difference between `(A, B) -> R` and `A -> (B -> R)`.
2. Write nested lambdas, invoke them in stages, and store an intermediate function.
3. Fix the left or right argument of a `BiFunction<A,B,R>`.
4. Convert a `BiFunction` to curried form and back when needed.
5. Use `Function.compose`/`andThen` with a partially applied function.
6. Recognize capture, `final`/effectively final, generics, side effects, `null`, exceptions, and performance concerns.
7. Run and test a standalone Java 17 example.

## 2. Data type model: from multiple inputs to a function chain

### 2.1. A normal two-argument function

In Java, `BiFunction<A,B,R>` describes a transformation accepting two arguments and returning one result:

~~~java
BiFunction<Integer, Integer, Integer> multiply =
        (price, quantity) -> price * quantity;

int total = multiply.apply(120, 3); // 360
~~~

Visualizing the signature:

~~~text
BiFunction<A, B, R> : (A, B) -> R
                             |
                             v
                           result
~~~

`multiply` is not a curried function: it requires both arguments in **a single** `apply` call. The snippets in this section are example declarations inside a method with `import java.util.function.*`.

### 2.2. A curried function

A two-argument function after currying has the form:

~~~java
Function<Integer, Function<Integer, Integer>> curriedMultiply =
        price -> quantity -> price * quantity;
~~~

The syntax `price -> quantity -> price * quantity` is parsed as:

~~~java
price -> (quantity -> price * quantity)
~~~

Not a subtraction operator; the inner arrow `->` returns **a second lambda**. Full type:

~~~text
Function<A, Function<B, R>>
    A ----> Function<B, R>
                 B ----> R
~~~

How to call it:

~~~java
int total = curriedMultiply.apply(120).apply(3); // 360
~~~

- `curriedMultiply.apply(120)` returns a function object of type `Function<Integer,Integer>`. At this step `quantity` is not needed yet.
- The returned function **remembers** the `price` value through lambda capture.
- Calling `apply(3)` on the remaining function executes the multiplication and returns `360`.

Writing it across multiple lines often helps readability:

~~~java
Function<Integer, Integer> price120 =
        curriedMultiply.apply(120);

int threeItems = price120.apply(3); // 360
int fiveItems = price120.apply(5);  // 600
~~~

This is an example of **currying combined with partial application**: the curried structure allows pre-applying `price = 120` and reusing it with multiple `quantity` values.

### 2.3. Three curried arguments

Example of adding three numbers:

~~~java
Function<Integer,
        Function<Integer,
                Function<Integer, Integer>>> addThree =
        a -> b -> c -> a + b + c;

int sum = addThree.apply(2).apply(3).apply(4); // 9
~~~

You can fix `a` or both `a` and `b` step by step:

~~~java
Function<Integer, Function<Integer, Integer>> add2 =
        addThree.apply(2);
Function<Integer, Integer> add2And3 = add2.apply(3);
int result = add2And3.apply(4); // 9
~~~

This form demonstrates the principle, but in Java long nested types easily make code hard to read. For business APIs, using classes, records, clearly named methods, or `BiFunction` may be more sensible.

## 3. Currying and partial application: where do they differ?

| Criterion | Currying | Partial application |
| --- | --- | --- |
| Direct goal | Turn a multi-input function into a chain of single-input functions | Create a new function by fixing some inputs |
| Typical input | Function `(A,B) -> R` | A multi-parameter function and some known values |
| Typical output | `A -> (B -> R)` | A function awaiting the unfixed parameters |
| Requires changing structure to nested functions? | Yes, by definition of currying | No |
| Can the second parameter be fixed first? | For `A -> (B -> R)`, the natural order is `A` first; extra transformation is needed to fix `B` first | Yes, if an appropriate function is created |
| Suitable Java tools | Nested lambdas, `Function<A,Function<B,R>>` | Lambda closures, `BiFunction`, `bindFirst`/`bindSecond` helpers |

An example of **direct partial application without currying**:

~~~java
BiFunction<Integer, Integer, Integer> subtract =
        (a, b) -> a - b;

// Fix a = 10, awaiting b.
Function<Integer, Integer> fromTen =
        b -> subtract.apply(10, b);

System.out.println(fromTen.apply(3)); // 7
~~~

An example of fixing **the second argument**:

~~~java
// Fix b = 10, awaiting a.
Function<Integer, Integer> minusTen =
        a -> subtract.apply(a, 10);

System.out.println(minusTen.apply(3)); // -7
~~~

Because subtraction is not commutative, the two ways of fixing arguments yield different results. Parameter order is part of the business contract; when naming functions, make clear **which parameter was fixed**.

**Section takeaway:** every step of calling a curried function with fewer arguments than the original can be viewed as producing a partially applied form; however, partial application can be performed from any suitable function using a closure, without converting to curried form.

## 4. Building `bindFirst` and `bindSecond` with generics

We can write two reusable helpers for any `BiFunction<A,B,R>`.

### 4.1. Fixing the first parameter

~~~java
static <A, B, R> Function<B, R> bindFirst(
        BiFunction<A, B, R> function, A fixedA) {
    Objects.requireNonNull(function, "function");
    return b -> function.apply(fixedA, b);
}
~~~

This is a **method to be placed inside a class** with `java.util.function.BiFunction`, `Function`, and `java.util.Objects` imported.

Type meaning:

~~~text
Before: (A, B) -> R
bindFirst(function, fixedA)
After:      B  -> R
~~~

Example:

~~~java
BiFunction<Integer, Integer, Integer> multiply =
        (a, b) -> a * b;

Function<Integer, Integer> triple =
        bindFirst(multiply, 3);

int result = triple.apply(7); // 21
~~~

The value `3` is held in the closure. The new lambda only needs to accept `b` and invoke the original calculation.

### 4.2. Fixing the second parameter

~~~java
static <A, B, R> Function<A, R> bindSecond(
        BiFunction<A, B, R> function, B fixedB) {
    Objects.requireNonNull(function, "function");
    return a -> function.apply(a, fixedB);
}
~~~

Type meaning:

~~~text
Before: (A, B) -> R
bindSecond(function, fixedB)
After:  A     -> R
~~~

Example:

~~~java
BiFunction<String, String, String> join =
        (prefix, value) -> prefix + value;

Function<String, String> addSuffix =
        bindSecond(join, "-done");

String result = addSuffix.apply("task"); // task-done
~~~

**Why use generics?** If you define the helper only for `Integer`, you would have to rewrite it for `String` or other objects. The three type parameters `A`, `B`, `R` let the compiler check combinations without raw types and unsafe casts.

These helpers use `Objects.requireNonNull` to reject a `null` `function` immediately when creating the function. They **do not automatically reject** `null` for `fixedA` or `fixedB`; that depends on the contract of the underlying calculation. If the original lambda does not handle `null`, an error may only occur when `apply` is called on the returned function.

### 4.3. Guide to reading a nested generic type

Read from the inside out:

- `BiFunction<A,B,R>`: given both `A` and `B`, produces `R`.
- `Function<B,R>`: only needs `B` to produce `R`.
- `Function<A,Function<B,R>>`: needs `A` to create a new function, then needs `B` to produce `R`.

Try to understand the meaning by the number of missing inputs, rather than looking at `<`/`>` brackets as an unreadable string of characters.

## 5. Writing `curry` and `uncurry` helpers

When you need to convert function shapes, you can define:

~~~java
static <A, B, R> Function<A, Function<B, R>> curry(
        BiFunction<A, B, R> function) {
    Objects.requireNonNull(function, "function");
    return a -> b -> function.apply(a, b);
}

static <A, B, R> BiFunction<A, B, R> uncurry(
        Function<A, Function<B, R>> function) {
    Objects.requireNonNull(function, "function");
    return (a, b) -> function.apply(a).apply(b);
}
~~~

The two methods above are **illustrative code inside a class** with appropriate imports. Usage:

~~~java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;

Function<Integer, Function<Integer, Integer>> curried =
        curry(add);

Function<Integer, Integer> addTen = curried.apply(10);
System.out.println(addTen.apply(5)); // 15

BiFunction<Integer, Integer, Integer> originalShape =
        uncurry(curried);
System.out.println(originalShape.apply(10, 5)); // 15
~~~

### Points to understand about behavior preservation

For a **pure function** — same input, same result, no observable side effects — `uncurry(curry(f))` yields the same result as `f` on compatible inputs. However, for functions with side effects, `null`, exceptions, or steps returning functions with side effects, the timing/frequency of running steps can make observable equivalence more complex.

For example, `curry(function)` above **only creates a wrapper**; calling `function.apply(a,b)` happens once both `a` and `b` are received. With a custom curried implementation, logic in the outer function `a -> { ... }` can run right on the first `apply(a)` call, before `b` is available. This affects logs, timing, expensive computations, and exceptions.

Understand that **nested functions are not automatically completely lazy**. The function-creation step can do work; in a lambda whose body is only an expression returning another lambda, the first step usually has not performed the final calculation yet.

## 6. Closures and variable capture rules

### 6.1. Why does the new function "remember" the argument?

~~~java
int fee = 5;

Function<Integer, Integer> addFee =
        price -> price + fee;
~~~

`fee` is a local variable captured by the lambda; it must be `final` or **effectively final**. Later `addFee.apply(100)` returns `105`. If you add `fee = 7;` in the same scope, code using `fee` inside the lambda will not compile.

With partial application:

~~~java
static Function<Integer, Integer> plus(int fixed) {
    return value -> fixed + value;
}
~~~

The parameter `fixed` is also captured. If `fixed` is not reassigned, the returned lambda is valid and can continue using the value after the `plus` method finishes.

### 6.2. Capturing a reference does not freeze the object

~~~java
StringBuilder prefix = new StringBuilder("old-");
Function<String, String> label =
        value -> prefix + value;

prefix.replace(0, prefix.length(), "new-");
System.out.println(label.apply("item")); // new-item
~~~

The example needs to be placed inside a method. `prefix` is not reassigned so it is effectively final, but the `StringBuilder` object is mutable. The function reads the **current state** of the builder. This semantics differs from fixing an immutable string:

~~~java
String fixedPrefix = prefix.toString();
Function<String, String> stableLabel =
        value -> fixedPrefix + value;
~~~

This creates a snapshot of the **string** at the time `stableLabel` is created, as long as `fixedPrefix` is not reassigned. When using the `bindFirst` helper with a mutable object argument, the held value is a **reference**, not a deep copy of the object.

### 6.3. Fields and shared mutable state

The effectively final rule applies to captured locals/parameters; it does not make captured fields or objects immutable. A lambda can update the state of an external object if the API allows it; if the function is shared across threads, race conditions and memory visibility must be considered independently of capture rules.

For predictable functions, prefer capturing immutable data or appropriate snapshots, and avoid mutating objects closed over in a closure unless truly necessary.

## 7. Complete Java 17 example: pricing, adding fees, and labeling

The following program combines two ways of fixing arguments, a curried function, and `andThen`. It is written **standalone, requiring no external libraries**.

Create **`CurryingDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.Function;

public class CurryingDemo {

    static <A, B, R> Function<B, R> bindFirst(
            BiFunction<A, B, R> fn, A a) {
        Objects.requireNonNull(fn, "fn");
        return b -> fn.apply(a, b);
    }

    static <A, B, R> Function<A, R> bindSecond(
            BiFunction<A, B, R> fn, B b) {
        Objects.requireNonNull(fn, "fn");
        return a -> fn.apply(a, b);
    }

    public static void main(String[] args) {
        // price * quantity
        BiFunction<Integer, Integer, Integer> multiply =
                (price, quantity) -> price * quantity;

        // Fix price=120, awaiting quantity.
        Function<Integer, Integer> fixedPrice =
                bindFirst(multiply, 120);

        // Fix quantity=3, awaiting price.
        Function<Integer, Integer> quantityThree =
                bindSecond(multiply, 3);

        // Currying: a -> (b -> a + b).
        Function<Integer, Function<Integer, Integer>> curriedAdd =
                a -> b -> a + b;

        Function<Integer, Integer> addFive =
                curriedAdd.apply(5);

        System.out.println(fixedPrice.apply(3));
        System.out.println(quantityThree.apply(90));
        System.out.println(addFive.apply(7));

        // First multiply by quantity 3, then add fixed fee 5.
        Function<Integer, Integer> pricedAndFee =
                quantityThree.andThen(addFive);
        System.out.println(pricedAndFee.apply(120));

        // A curried function with different input types.
        Function<String, Function<Integer, String>> label =
                prefix -> value -> prefix + value;
        System.out.println(label.apply("ID-").apply(42));

        // Mutable capture: stable reference, changing object.
        StringBuilder mutablePrefix = new StringBuilder("old-");
        Function<String, String> tag = text -> mutablePrefix + text;
        mutablePrefix.replace(
                0, mutablePrefix.length(), "new-");
        System.out.println(tag.apply("value"));
    }
}
~~~

Run on JDK 17+:

~~~bash
javac -encoding UTF-8 CurryingDemo.java
java CurryingDemo
~~~

**Exact stdout:**

~~~text
360
270
12
365
ID-42
new-value
~~~

Line-by-line explanation:

1. `fixedPrice.apply(3)` uses `120 * 3` and gives `360`.
2. `quantityThree.apply(90)` uses `90 * 3` and gives `270`.
3. `addFive.apply(7)` uses `5 + 7` and gives `12`.
4. `quantityThree.andThen(addFive)` takes input `120` → multiplies by `3` to get `360` → adds `5` to get `365`.
5. `label.apply("ID-")` creates a function remembering the prefix, then `apply(42)` produces `ID-42`.
6. `mutablePrefix` is captured as a reference to `StringBuilder`. After `replace`, `tag.apply("value")` reads the new state and prints `new-value`.

**Currency units:** the example uses `int` solely to teach function organization and composition order. In real payment products, you need clear models for monetary amounts, units, taxes/fees, rounding rules, overflow checks, and validation; do not assume `int` multiplication or fee addition as in the example is a complete financial design.

## 8. Combining with `compose` and `andThen`

A `Function<T,R>` in Java can be composed with `compose` or `andThen`:

- `f.andThen(g)`: accepts `x`, computes `f(x)` first, then passes the result to `g`.
- `f.compose(g)`: accepts `x`, computes `g(x)` first, then passes the result to `f`.

This is **function composition**, which differs in nature from currying. However, after partially applying arguments to obtain a single-input `Function`, they combine very conveniently:

~~~java
Function<Integer, Integer> timesThree = n -> n * 3;
Function<Integer, Integer> plusFive = n -> n + 5;

Function<Integer, Integer> firstMultiply =
        timesThree.andThen(plusFive);
Function<Integer, Integer> firstAdd =
        timesThree.compose(plusFive);

System.out.println(firstMultiply.apply(10)); // 35
System.out.println(firstAdd.apply(10));      // 45
~~~

Because `andThen`/`compose` pass **the result of the previous step** into the next step, they differ from partial application, which fixes **an available argument**. A workflow may need both: first fixing configuration, then composing transformations.

### Composition does not remove side effects

If the underlying functions log or mutate state, a composed function can trigger multiple side effects; a later step throwing an exception also does not undo changes from an earlier step. When order and transactions matter, do not treat function composition as a rollback mechanism.

If receiving multiple functions from configuration, consider calling `Objects.requireNonNull` for function objects that must not be `null`. `Function.andThen(null)` and `Function.compose(null)` will throw `NullPointerException` per the Javadoc contract.

## 9. When should you actually use them?

### 9.1. Creating specialized functions from configuration

Suppose an application needs to check the same rule against multiple thresholds:

~~~java
BiFunction<Integer, Integer, Boolean> isAtLeast =
        (minimum, value) -> value >= minimum;

Function<Integer, Boolean> atLeast18 =
        value -> isAtLeast.apply(18, value);
~~~

Then `atLeast18.apply(20)` is `true`. The configuration `minimum=18` is fixed, while tested values vary. You can use `Predicate<Integer>` for boolean results when the API design suits it; using `Function<Integer,Boolean>` is not mandatory.

### 9.2. Reusing transformations via callbacks

A `Function<String,String>` with a fixed prefix can be passed into `stream.map(...)`:

~~~java
String prefix = "USER-";
Function<String, String> withPrefix =
        value -> prefix + value;

List<String> names = List.of("A", "B");
List<String> labels = names.stream()
        .map(withPrefix)
        .toList();

System.out.println(labels); // [USER-A, USER-B]
~~~

This is a snippet inside a method importing `java.util.List`, `Function`. It illustrates direct partial application via lambda capture. For a simple single step like this, there is no need to force a `curry` helper into the design.

### 9.3. Using currying when logic is built in stages

When a function is configured in layers (e.g., tenant → locale → value), currying can produce an API like:

~~~java
Function<String, Function<String, Function<Integer, String>>> format =
        tenant -> locale -> value ->
                tenant + "/" + locale + ":" + value;

Function<Integer, String> forVietnam =
        format.apply("acme").apply("vi-VN");

System.out.println(forVietnam.apply(5)); // acme/vi-VN:5
~~~

This chain is readable if the application order reflects the configuration workflow. If there are too many layers or parameters can easily be swapped by mistake, a configuration record or class with named fields may be clearer.

### 9.4. No need to force every API into curried form

For rarely used operations, `BiFunction.apply(a,b)` can be simpler than `curried.apply(a).apply(b)`. If a calculation involves many named business fields, a `PricingContext` or `RequestOptions` record or a descriptively named method is usually easier to maintain than a deeply nested function chain.

Choose tools based on **reusability and code comprehensibility**, not just because the syntax looks "functional".

## 10. Common mistakes and limitations of the technique

| Mistake/confusion | Why it is wrong | How to fix |
| --- | --- | --- |
| Calling `curried.apply(a,b)` | `Function` only has single-input `apply` | Call `curried.apply(a).apply(b)` |
| Calling `BiFunction.apply(a).apply(b)` | `BiFunction` takes two inputs in one call | Use `apply(a,b)` or curry first |
| Thinking currying and partial application are the same | One transforms function shape; the other fixes arguments | Distinguish before/after signatures |
| Fixing the wrong parameter of subtraction | Parameter order matters | Choose clearly named `bindFirst`/`bindSecond` |
| Returning `R` by mistake when `Function<B,R>` is required | Wrong return type of the outer layer | Outer layer must return a lambda/function |
| Reassigning a captured local variable | Violates `final`/effectively final | Create a new configuration variable, pass parameters |
| Assuming a captured object is immutable | Closure can hold a mutable reference | Take a snapshot/design immutable types when needed |
| Using `null` without a contract | Helper and base calculation may throw at different times | Check and document the `null` policy |
| Using raw `Function` or arbitrary casts | Loses type safety, type conversion errors | Keep full generics |
| Expecting `andThen` to roll back when a later step fails | Composition has no transactions | Design error handling and transactions separately |
| Using long, deeply nested lambdas | Hard to read and debug | Extract methods, name them, use records/configs |
| Overusing primitive types via generics | `Integer`/`Long` incur boxing/unboxing | Consider `IntUnaryOperator`/`IntBinaryOperator` and measure when performance is required |
| Creating functions in a loop while mixing loop counters | Captured locals must be effectively final | Create a new local variable per iteration |
| Assuming currying is always lazy | Outer-layer function can execute immediately when called | Inspect logic at each layer and side-effect timing |

### 10.1. Input types, generic inference, and boxing

`Function<Integer,Integer>` uses `Integer` objects, which can cause boxing/unboxing when doing many primitive operations. If high performance is required and only `int` is used, consider `IntUnaryOperator` or `IntBinaryOperator`. However, primitive interfaces are not generic like `Function<A,Function<B,R>>`, so APIs may need specialized helpers.

The compiler usually infers `A`, `B`, `R` for `bindFirst`. If ambiguity arises due to overloads or generic constraints, extract `BiFunction` into an explicitly typed variable before calling the helper; do not patch it with raw types or unsafe casts.

### 10.2. Timing of error handling

With:

~~~java
Function<Integer, Integer> divideByTen =
        n -> 10 / n;

Function<Integer, Integer> fixed =
        bindFirst((Integer a, Integer b) -> a / b, 10);
~~~

Both functions above can be created successfully. If `apply(0)` is called, division will throw `ArithmeticException`. Binding one argument upfront does not automatically validate all future inputs. If fail-fast behavior for configuration is needed, validate values right in the factory/helper method.

### 10.3. Side effects create differences between styles

For pure logic, converting `(a,b)->r` into `a->b->r` preserves the corresponding result. But if a lambda layer logs, queries a database, generates timestamps, emits events, or mutates objects, calling layer by layer **can execute side effects at different times**. Business requirements must be identified and call counts tested, rather than assuming all styles are interchangeable.

### 10.4. Do not use as automatic caching

`Function<Integer,Integer> plusFive = curriedAdd.apply(5)` retains `5`, but **does not automatically remember results** for subsequent inputs. Calling `plusFive.apply(10)` multiple times will normally execute the corresponding calculation multiple times. Currying and partial application **are not memoization**; caching is a separate technique requiring its own key, lifecycle, memory, and concurrency design.

## 11. Testing results and function properties

### 11.1. Comparing original and curried forms

For a pure `BiFunction` like adding two numbers, you can write:

~~~java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;
Function<Integer, Function<Integer, Integer>> c =
        a -> b -> add.apply(a, b);

int a = 2;
int b = 3;
boolean same = add.apply(a, b).equals(c.apply(a).apply(b));
System.out.println(same); // true
~~~

This is code placed in a method with appropriate imports. Comparing on one pair of inputs does not prove correctness for all pairs; test negative values, `0`, `int` limits, overflow if required by the problem, and practical constraints.

### 11.2. Testing argument order

With `subtract(a,b) = a-b`, check:

~~~java
BiFunction<Integer, Integer, Integer> subtract =
        (a, b) -> a - b;

Function<Integer, Integer> fromTen =
        b -> subtract.apply(10, b);
Function<Integer, Integer> minusTen =
        a -> subtract.apply(a, 10);

System.out.println(fromTen.apply(3));  // 7
System.out.println(minusTen.apply(3)); // -7
~~~

If a generic helper has a bug swapping `a`/`b`, subtraction will expose the bug more easily than addition or multiplication. In tests, choosing a **non-commutative operation** is a useful way to verify binding order.

### 11.3. Testing side effects

If the original lambda has a counter or log, write tests asserting that the action happens **when the right layer is called**. Creating the function (factory), applying the first parameter, and calling the final function can be three distinct observable moments. With the `curry` implementation in Section 5, `function.apply(a,b)` only runs at the final layer; if custom logic is added to the outer layer, behavior changes.

## 12. Practice exercises

**Exercise 1 — Currying multiplication.** Create a `Function<Integer,Function<Integer,Integer>>` computing the product, create a multiply-by-`7` function, and call it with `8`. Expected result `56`. Rewrite it with `BiFunction<Integer,Integer,Integer>` to compare.

**Exercise 2 — Partial application without currying.** Given `BiFunction<Integer,Integer,Integer> subtract = (a,b)->a-b;`. Write two functions `minusTwoFromTen` and `minusTenFrom` by fixing different parameter positions. Check the outputs and name them to reflect the exact order.

**Exercise 3 — Generic helpers.** Write `bindFirst` and `bindSecond` yourself, test with `BiFunction<String,String,String>` for string concatenation and `BiFunction<Integer,Integer,Integer>` for multiplying two numbers. Explain the meaning of `Function<B,R>` in the signature of `bindFirst`.

**Exercise 4 — `curry`/`uncurry` conversion.** Write generic helpers following Section 5. Pick a pure function like addition and check the results of `original.apply(a,b)`, `curry(original).apply(a).apply(b)`, and `uncurry(curry(original)).apply(a,b)` on several pairs of numbers.

**Exercise 5 — Function composition.** Use `bindSecond(multiply,3)` to create a triple function, then use `andThen(n -> n+5)`. With `input=10`, the result should be `35`. Switch to `compose` to compute `3*(10+5)` and explain why it becomes `45`.

**Exercise 6 — Capturing a mutable object.** Use `StringBuilder` as a prefix for a lambda; modify the builder after creating the lambda and call it again. Switch to capturing an immutable `String` to compare. State clearly what is captured and why the results can differ.

**Exercise 7 — Creating a business API.** Write a factory `Function<Integer,Integer> priceWithTax(int taxPercent)` to compute price plus tax using your own illustrative rule. Check negative data, overflow, and rounding rules before using in production. Explain why the `taxPercent` input should be validated early.

**Exercise 8 — Identifying techniques.** Given `Function<String,String> prefix = s -> "ID-" + s;`, this is a specialized function with a fixed prefix, yet it does **not have** to be created from currying. Convert it into `prefix -> value -> prefix + value` form and point out when the partial application step occurs.

## 13. Self-check questions

1. **What is currying?** Turning a multi-input function into a chain of functions taking one input each.
2. **What is partial application?** Fixing part of the arguments to create a function awaiting the remaining arguments.
3. **Are the two techniques completely identical?** No. You can partially apply a `BiFunction` directly without currying.
4. **How is `Function<A,Function<B,R>>` called?** `apply(a).apply(b)`.
5. **How is `BiFunction<A,B,R>` called?** `apply(a,b)`.
6. **What type does `bindFirst` return?** `Function<B,R>` when fixing the argument of type `A`.
7. **What type does `bindSecond` return?** `Function<A,R>` when fixing the argument of type `B`.
8. **Does a bound function automatically cache all results?** No, there is no default memoization.
9. **What happens if a mutable `ArrayList`/`StringBuilder` is captured?** The lambda holds a reference; the object can continue changing, and results can depend on call timing.
10. **Is `andThen` currying?** No; it is composition, passing results between two transformations.
11. **Can the second argument of subtraction be pre-bound?** Yes, via a lambda or `bindSecond`; the order must not be arbitrarily reversed.
12. **Why test with a non-commutative function?** To detect fixing the wrong parameter position.

## 14. Summary and references

**Currying** reshapes `(A,B)->R` into `A -> (B -> R)`. **Partial application** chooses one or more fixed arguments to return a specialized function. In Java, we can use nested lambdas, `Function<A,Function<B,R>>`, `BiFunction<A,B,R>`, and `bindFirst`/`bindSecond` helpers. Once a single-input `Function` is obtained, it can be combined with `compose`/`andThen` to build pipelines.

To write reliable code, control parameter order, generic constraints, capture rules, `null`, exceptions, overflow, and side effects. For simple problems, a clear lambda or ordinary method is often better than a long curried chain. Use these techniques when they genuinely **help reuse behavior or separate configuration from runtime data**.

Official references: Java SE 17 Javadoc for `java.util.function.Function`, `BiFunction`, `IntUnaryOperator`, `IntBinaryOperator`; Java Language Specification `15.27 Lambda Expressions` and `4.12.4 final Variables`.
