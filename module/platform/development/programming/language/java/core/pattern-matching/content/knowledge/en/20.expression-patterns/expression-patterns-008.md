# Pattern Expressions in Lambdas

**Scope:** Java Core Pattern Matching — Patterns in Expressions. This article uses the stable syntax of **Java 21 and later**: type patterns in `instanceof`, record patterns (JEP 440), and pattern matching for `switch` (JEP 441). Record patterns and pattern `switch` do not require `--enable-preview` as of Java 21.

## 1. What does a pattern expression in a lambda mean?

A **lambda expression** provides a concise implementation for a functional interface, such as `Predicate<T>` returning `boolean` or `Function<T, R>` taking `T` and returning `R`. A lambda can use an expression as its body or a statement block with `return`.

A **pattern** describes the condition for a value to match a type/shape and, if it matches, binds variables. Java 21 allows using patterns in expressions such as `instanceof` or `switch` `case` labels; those expressions can appear **directly inside a lambda body**.

For example, a record representing a coordinate:

~~~java
record Point(int x, int y) {}
~~~

From a list of generic-typed values, we want to keep only the Points in the first quadrant:

~~~java
Predicate<Object> inFirstQuadrant = value ->
        value instanceof Point(int x, int y) && x > 0 && y > 0;
~~~

Here the lambda:

1. Receives the argument `value` because the target type is `Predicate<Object>`.
2. Checks whether `value` matches the record pattern `Point(int x, int y)`.
3. If it matches, extracts the two components into the variables `x`, `y`.
4. Thanks to the **short-circuit** mechanism of `&&`, `x > 0 && y > 0` is only checked when the pattern has matched.
5. Returns a `boolean` for `Predicate.test(value)` to use.

**Patterns do not replace lambdas.** A lambda is a way to pass behavior, while a pattern is a way to test and extract data *inside that behavior*. We are not creating a new kind of "lambda pattern parameter".

## 2. Three common ways to use patterns in a lambda body

### 2.1. Lambda with an `instanceof` expression body

When you only need to return true/false, use `Predicate` and a boolean expression:

~~~java
// Illustration snippet: Point is the record declared in section 1.
Predicate<Object> positivePoint = candidate ->
        candidate instanceof Point(int x, int y)
        && x > 0
        && y > 0;
~~~

The entire expression after `->` is the return value of the lambda. There is no need to write the `return` keyword. The `&&` condition clearly expresses the rule: it must be a Point record, and both coordinates must be positive.

If you only check the type and do not need to extract components, you can also write `candidate -> candidate instanceof Point`. A record pattern is useful when you need to use the components directly.

### 2.2. Lambda with a statement block body

When multiple processing steps or custom error messages are needed, use a block lambda:

~~~java
Function<Object, String> describePoint = candidate -> {
    if (candidate instanceof Point(int x, int y)) {
        return "Point(" + x + "," + y + ")";
    }
    return "Not a Point";
};
~~~

Because `Function<Object, String>` must return a `String`, every normal execution path in the block must have a return value. The pattern variables `x`, `y` are only available in the region of code where the match is proven, such as inside the `if` branch in this example.

### 2.3. Lambda with a `switch` expression body

A `switch` expression returns a value, so it can be placed after the `->` of a lambda:

~~~java
Function<Object, String> classify = value -> switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 -> "origin";
    case Point(int x, int y) -> "point";
    case null -> "null";
    default -> "other";
};
~~~

The first branch with `when` matches only a Point at the origin; the second Point branch covers the remaining Points. The `null` and `default` branches handle values outside those two groups. With a selector of type `Object`, the Point branches do not cover all other types, so the example needs a fallback case.

**Watch out for the semicolon:** with `Function<...> f = value -> switch (value) { ... };`, the final `;` terminates the lambda assignment. Each `case ... ->` branch in the `switch` expression yields a value whose type is compatible with the lambda's return type.

## 3. Complete Java 21 program: Predicate, Function, and Stream

The example below shows pattern expressions working in lambdas in practice, including nested records, guards, null, stream filtering, and `mapMulti`.

Save the complete program in the file **LambdaPatternDemo.java**:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    public static void main(String[] args) {
        List<Object> values = List.of(
                new Point(2, 3),
                new Point(-1, 5),
                new Segment(new Point(1, 2), new Point(3, 4)),
                new Segment(new Point(0, 0), null),
                "other");

        Predicate<Object> positivePoint = value ->
                value instanceof Point(int x, int y) && x > 0 && y > 0;

        Function<Object, String> describe = value -> switch (value) {
            case Point(int x, int y) when x > 0 && y > 0 ->
                    "positive point: " + x + "," + y;
            case Point(int x, int y) ->
                    "point: " + x + "," + y;
            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "segment: " + x1 + "," + y1 + " -> " + x2 + "," + y2;
            case Segment(var start, var end) ->
                    "incomplete segment";
            case null -> "null value";
            default -> "unknown";
        };

        System.out.println(values.stream()
                .filter(positivePoint)
                .map(describe)
                .toList());

        values.forEach(value -> System.out.println(describe.apply(value)));
        System.out.println(describe.apply(null));

        List<Integer> totals = values.stream()
                .<Integer>mapMulti((value, downstream) -> {
                    if (value instanceof Point(int x, int y)) {
                        downstream.accept(x + y);
                    }
                })
                .toList();
        System.out.println(totals);
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac LambdaPatternDemo.java
java LambdaPatternDemo
~~~

Output:

~~~text
[positive point: 2,3]
positive point: 2,3
point: -1,5
segment: 1,2 -> 3,4
incomplete segment
unknown
null value
[5, 4]
~~~

**Part-by-part explanation:**

- `positivePoint` is a lambda bound to `Predicate<Object>`; it returns true only for `Point(2, 3)`. `Point(-1, 5)` does not satisfy `x > 0`.
- `describe` is a lambda returning `String` using a `switch` expression. The two Point branches illustrate combining a record pattern with a guard; the branch with `when` comes before the branch covering all Points.
- `Segment(Point(...), Point(...))` requires **both points** to be present. A Segment with `end = null` does not match that nested branch, but it matches `Segment(var start, var end)`, so it receives `incomplete segment`.
- `case null` must be written explicitly if you want to handle a null selector in pattern-matching `switch`; `default` handles other kinds of values such as `String`.
- `values.stream().filter(positivePoint).map(describe).toList()` uses one lambda to filter and one lambda to produce descriptions; the result contains only the Point element with both coordinates positive.
- `mapMulti` places the recognition and coordinate extraction **in the same lambda**. Only Points are converted into the sum `x + y`, which are 5 and 4 respectively; other elements emit no values.

The example uses `List.of(...)` with non-null list elements; the null selector is tested separately via `describe.apply(null)` because **List.of does not allow null elements**. Components inside a record can still be null if the constructor allows it, such as `end` in the second Segment.

## 4. Flow scoping: why can a pattern variable be used after `&&`?

Java does not allow arbitrarily using variables declared in a pattern everywhere. The compiler applies **flow scoping**: a variable is only in scope in regions where the execution path proves the pattern has matched.

The following lambda expression is valid:

~~~java
Predicate<Object> rightHalf = value ->
        value instanceof Point(int x, int y) && x > 0;
~~~

In `A && B`, Java evaluates `B` only if `A` is true. Therefore, when evaluating `x > 0`, the pattern `Point(int x, int y)` has already matched and `x` exists.

Conversely, the following snippet **does not compile**:

~~~java
// WRONG: when the left-hand side is false, x is not bound yet.
Predicate<Object> invalid = value ->
        value instanceof Point(int x, int y) || x > 0;
~~~

With `A || B`, the right-hand side is evaluated when the left-hand side is false, so `x` is not guaranteed to exist. Do not change `&&` to `||` just because they look syntactically similar; the condition semantics and variable scopes are different.

In a block lambda, an `if` branch is a clear way to control scope:

~~~java
Function<Object, Integer> sumIfPoint = value -> {
    if (value instanceof Point(int x, int y)) {
        return x + y;
    }
    return 0;
};
~~~

If the rejecting branch ends with `return`, the pattern variables can be in scope on the subsequent lines according to flow scoping rules. However, an example that uses the variables *only inside the matching branch* is usually easier for beginners to understand.

The variables `x` and `y` are local variables for each lambda invocation, not shared storage across calls.

## 5. Pattern variables do not cross lambda boundaries in a Stream

A very common misconception: **a pattern variable declared inside one lambda does not automatically appear in the next lambda**.

The following example tries to use `x` in the `map` lambda and is **invalid code**:

~~~java
// WRONG: x only belongs to the lambda inside filter.
values.stream()
        .filter(v -> v instanceof Point(int x, int y))
        .map(v -> x + y);
~~~

In a pipeline, `filter` decides whether to keep or discard **the element**, rather than emitting bound pattern variables. The lambda passed to `map` has its own scope; `x` is not declared there.

There are three sensible ways to handle this, depending on your requirements:

1. **Separate behavior:** use a `Predicate<Object>` to select the right elements and a `Function<Object, String>` to classify elements as in the main program. Each lambda uses the appropriate pattern within its own scope.
2. **Keep all matching and transformation in one lambda:** use `mapMulti` when you want to emit zero, one, or several results per element. The example in the main program only calls `downstream.accept(x + y)` when the Point pattern matches.
3. **Pass the transformed value out of the lambda:** use `map` to create a result object/record with the needed data, and then subsequent steps process that object. This approach is suitable when the pipeline has many more steps.

Do not expect flow scoping to extend across independent lambda arguments. Pipeline design should clearly express what element is passed from one step to the next.

## 6. Lambda parameters and patterns are two different concepts

Declare a simple lambda:

~~~java
Function<Object, String> label = candidate -> {
    if (candidate instanceof Point(int x, int y)) {
        return x + ":" + y;
    }
    return "other";
};
~~~

`candidate` is the **lambda parameter**; `Point(int x, int y)` is the **record pattern inside the body**.

In Java 21, you cannot directly destructure a lambda parameter like this:

~~~java
// WRONG: Java 21 does not support a record pattern as a lambda formal parameter.
Function<Point, Integer> invalid = (Point(int x, int y)) -> x + y;
~~~

The right way is to accept a parameter of the appropriate type and use accessors or pattern checks in the body. With `Function<Point, Integer>`, the most concise way is usually:

~~~java
Function<Point, Integer> total = point -> point.x() + point.y();
~~~

Since the parameter is already typed as Point, a pattern is not always needed. **Pattern expressions are most valuable when a lambda receives a generic type, a supertype with multiple variants, or a record structure that needs to be deconstructed.**

## 7. Combining type patterns, record patterns, and `switch` in lambdas

Different kinds of patterns are useful in different situations:

| Case | Example in lambda body | Purpose |
| --- | --- | --- |
| Only need type recognition | `v instanceof Point` | Check whether the object is of type Point |
| Need to keep the object after checking | `v instanceof Point point` | Use the object itself via the variable `point` |
| Need two components of a record | `v instanceof Point(int x, int y)` | Extract data right at the condition |
| Need a nested record structure | `v instanceof Segment(Point(int x1, int y1), Point(int x2, int y2))` | Match only when both components are Points |
| Need multiple branches returning a value | `v -> switch (v) { ... }` | Use patterns in the cases of a switch expression |
| Have an extra condition after matching a case | `case Point(int x, int y) when x > 0 -> ...` | Combine matching with an additional condition |

In `instanceof`, additional conditions usually use `&&`. The `when` keyword is the syntax for a **case guard in switch**, not a standalone operator to replace `&&` in an `instanceof` expression.

With sealed types and an exhaustive `switch`, a lambda returning the result of a switch expression may not need `default` when the cases fully cover the subtypes and selector. With the `Object` selector in this example, `default` is necessary to handle types other than Point or Segment.

## 8. Null, case ordering, and error-prone conditions

**Null selector in `instanceof`:** the expression `value instanceof Point(int x, int y)` returns false when value is null. Pattern variables are not bound.

**Null sub-record:** the nested pattern `Segment(Point(...), Point(...))` will not match if start or end is null. A pattern `Segment(var start, var end)` can still match Segment and bind the null value to the reference variable.

**Null leaf component:** a record pattern does not implicitly validate contents or guarantee that every reference component is non-null. If data may be missing, use an explicit condition before calling methods on it.

**Switch ordering:** a broad case for Point placed before a guarded Point case can shadow the later branch. Put branches with specific conditions first, followed by general branches.

**Variable scope:** `x` in one case cannot be used in another case unless that case has a corresponding binding. Variables with the same name in independent branches do not share values.

**Block lambda with a result:** for `Function`, do not write a block that only has an `if` returning in the true branch and leaves the false branch empty; ensure every normal path returns the right type.

## 9. On performance, side effects, and choosing how to write it

Pattern matching in lambdas has no performance magic: it helps place type conditions and the needed data close to where they are processed. In a stream, how many elements are traversed, whether intermediate objects are created, and the computations inside determine most of the cost. Measure with appropriate tools if performance is truly a requirement.

Lambdas used in `filter` and `map` should be easy to reason about, ideally avoiding side effects when unnecessary. External variables captured by a lambda must be **final** or **effectively final**; local pattern variables inside a lambda are not constrained by reassigning an external captured variable.

Do not nest too many record patterns and guards on a single line just to reduce the number of statements. If the data is deep or business rules are long, move the logic into a named method:

~~~java
// Illustration: assumes Point has already been declared.
static boolean isFirstQuadrant(Point point) {
    return point.x() > 0 && point.y() > 0;
}

// The lambda focuses on the type and calls the named rule.
Predicate<Object> filter = value ->
        value instanceof Point point && isFirstQuadrant(point);
~~~

When an object has many complex processing branches, you can also extract the `switch` expression into a method that takes a clear target type and then pass a method reference to `map`. The goal is for each lambda to express an easily recognizable responsibility.

## 10. Common mistakes and checklist

Common mistakes when putting patterns into lambdas include: declaring a record pattern directly as a lambda formal parameter; using a pattern variable on the right side of `||` when the left side can be false; assuming a variable created in `filter` is in scope in `map`; using `when` outside `switch case`; putting a general case before a guarded case; forgetting a null selector; expecting a null sub-record to match a nested record pattern; or forgetting `return` on one path of a block lambda.

Before finalizing your code, check yourself:

- Does the lambda's target type (`Predicate`, `Function`, etc.) match the parameters and return value?
- Is the pattern actually used in the lambda **body**, and is it more beneficial than simple accessors?
- Is every pattern variable accessed only where the compiler proves the match has succeeded?
- With `&&`, `||`, and guards, do the short-circuit conditions have the intended meaning?
- If using streams, are the elements passed through the steps and the data extracted at each step clearly distinguished?
- Have the switch cases considered null, non-matching nested patterns, and priority order?
- Have you tested valid inputs, wrong types, boundary values, and null?

**Remember:** a lambda expresses the action being passed; a pattern helps that action check **the right kind of data** and extract **the exact components needed**. Use `instanceof` for simple predicates, a `switch` expression when classifying multiple cases, and keep matching and transformation logic in one lambda when you need to use the pattern variables immediately.