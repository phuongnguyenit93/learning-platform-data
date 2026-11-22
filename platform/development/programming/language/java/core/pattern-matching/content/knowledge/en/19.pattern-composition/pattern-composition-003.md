# Combining Patterns with Guards in Java 21+

## 1. How Does a Guard Add Conditions to a Pattern?

A **pattern** answers the question "does the value have the expected type/structure, and what data can be extracted from it?". A **guard** adds a Boolean condition that is evaluated only **after the pattern matches successfully**. These two steps let you write branching logic based on both data structure and business constraints.

For example, consider a record representing coordinates:

```java
record Point(int x, int y) {}
```

To classify a point in the first quadrant, you must check both its **type/structure** and its **coordinate values**:

```java
String result = switch (value) {
    case Point(int x, int y) when x > 0 && y > 0 -> "Quadrant I";
    case Point(int x, int y) -> "Other point";
    case null -> "Missing";
    default -> "Unknown";
};
```

- `Point(int x, int y)` is a **record pattern**: it matches a `Point` and extracts the two components `x` and `y`.
- `when x > 0 && y > 0` is a **guard**: the coordinates are checked only when the pattern matches.
- When the guard is false, the `switch` continues evaluating the subsequent branches, such as the general `Point(...)` branch.
- `case null` and `default` play different roles: the null branch handles a null selector, while `default` handles the remaining values.

*Pattern matching for switch* and the `when` syntax became official in **Java 21** (JEP 441). Record patterns also became official in **Java 21** (JEP 440). The examples use JDK 21+ and do not require `--enable-preview`. Java 17 does not support these official `switch` pattern/record pattern syntaxes.

## 2. Two Ways to Combine Patterns with Conditions

### 2.1. `when` in `switch`

Basic syntax:

```java
switch (selector) {
    case SomeType variable when booleanCondition -> ...;
    case SomeType variable -> ...;
    default -> ...;
}
```

With a record pattern:

```java
switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 -> "Origin";
    case Point(int x, int y) when x > 0 && y > 0 -> "Quadrant I";
    case Point(int x, int y) -> "Another point";
    default -> "Other";
}
```

`when` appears after the pattern in a `case` label, before `->` (or `:` if using the traditional statement form). The expression following `when` must have type `boolean` and can access the bound pattern variables `x` and `y`.

If the pattern does not match, the guard is **not evaluated**. If the pattern matches but the guard returns `false`, the branch is not selected and the `switch` evaluates the next label. If the guard throws an exception, the exception propagates; Java does not treat that as a normal match failure.

**Do not write `when` in `instanceof` syntax.** `when` is a guard syntax reserved for pattern labels in `switch`.

### 2.2. `&&` When Using `instanceof`

For `if`, combine pattern matching with the short-circuit AND operator:

```java
static boolean inQuadrantI(Object value) {
    return value instanceof Point(int x, int y)
            && x > 0
            && y > 0;
}
```

The right-hand side of `&&` is evaluated only if `instanceof Point(...)` succeeds. Java knows `x` and `y` are definitely assigned in the remainder of the condition, so these variables are in valid scope.

You can chain multiple conditions:

```java
if (value instanceof Point(int x, int y)
        && x >= 0
        && y >= 0
        && x + y <= 100) {
    System.out.println("Point inside allowed region");
}
```

Note: the sum `x + y` is `int` addition and can overflow for very large values. When writing sensitive arithmetic boundary conditions, consider casting to `long`: `(long) x + y <= 100`.

**Syntax difference:** with `switch`, use `case Point(...) when condition`; with `if`, use `if (value instanceof Point(...) && condition)`.

## 3. Complete Java Example: Type Pattern, Record Pattern, Nested Pattern, and Sealed Hierarchy

The example below illustrates three levels of composition: checking coordinate data, checking a **nested record pattern** for a rectangle, and branching over a **sealed interface**. Save it to **`GuardedPatternDemo.java`**.

```java
public class GuardedPatternDemo {
    record Point(int x, int y) {}

    record Rectangle(Point start, Point end) {}

    sealed interface Action permits Transfer, Cancel {}

    record Transfer(String account, int amount) implements Action {}

    record Cancel(String account) implements Action {}

    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == 0 && y == 0 ->
                    "Origin";

            case Point(int x, int y) when x > 0 && y > 0 ->
                    "Quadrant I";

            // After the guarded branches comes the fallback Point branch covering the rest.
            case Point(int x, int y) ->
                    "Other point: " + x + "," + y;

            // Two Point records nested inside Rectangle.
            case Rectangle(
                    Point(int x1, int y1),
                    Point(int x2, int y2))
                    when x2 > x1 && y2 > y1 ->
                    "Area: " + ((x2 - x1) * (y2 - y1));

            // Covers any Rectangle that does not match the pattern/guard above.
            case Rectangle(var from, var to) ->
                    "Invalid rectangle";

            case null -> "Missing";
            default -> "Unknown";
        };
    }

    static String handle(Action action) {
        return switch (action) {
            case Transfer(String account, int amount)
                    when amount >= 100 ->
                    "Large transfer: " + account;

            case Transfer(String account, int amount)
                    when amount > 0 ->
                    "Small transfer: " + account;

            // An unguarded branch is needed to handle the remaining Transfer cases.
            case Transfer(String account, int amount) ->
                    "Rejected transfer: " + account;

            case Cancel(String account) ->
                    "Cancel: " + account;

            case null -> "No action";
        };
    }

    static boolean inQuadrantI(Object value) {
        return value instanceof Point(int x, int y)
                && x > 0 && y > 0;
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(3, 4)));
        System.out.println(describe(new Point(-1, 4)));

        System.out.println(describe(new Rectangle(
                new Point(0, 0), new Point(5, 4))));

        System.out.println(describe(new Rectangle(
                null, new Point(5, 4))));

        System.out.println(describe(null));
        System.out.println(describe("hello"));

        System.out.println(handle(new Transfer("A", 150)));
        System.out.println(handle(new Transfer("B", 30)));
        System.out.println(handle(new Transfer("C", 0)));
        System.out.println(handle(new Cancel("D")));
        System.out.println(handle(null));

        System.out.println(inQuadrantI(new Point(2, 3)));
        System.out.println(inQuadrantI("bad"));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 GuardedPatternDemo.java
java GuardedPatternDemo
```

Stdout output:

```text
Origin
Quadrant I
Other point: -1,4
Area: 20
Invalid rectangle
Missing
Unknown
Large transfer: A
Small transfer: B
Rejected transfer: C
Cancel: D
No action
true
false
```

**Key points explained:**

1. `new Point(0, 0)` matches the first record pattern, and then the guard `x == 0 && y == 0` evaluates to true; the `Origin` branch is selected.
2. `new Point(3, 4)` fails the first guard but passes `x > 0 && y > 0`; the result is `Quadrant I`.
3. `new Point(-1, 4)` fails both guards but still matches the unguarded `Point(...)`; the result is `Other point: -1,4`.
4. `Rectangle(Point(...), Point(...))` deconstructs components across two levels. The guard uses all four coordinate variables to validate the rectangle assuming `start` is the top-left corner and `end` has both coordinates larger.
5. `Rectangle(null, new Point(5, 4))` does not match `Rectangle(Point(...), Point(...))` because `start` is null. The broader `Rectangle(var from, var to)` branch catches this object and prints `Invalid rectangle`.
6. `Action` is a sealed interface permitting only `Transfer` and `Cancel`. `handle` covers both variants (including `Transfer` instances that fail the guards) and the null case; no `default` is needed.
7. `inQuadrantI` shows that pattern variables can be used immediately in a Boolean expression with `&&`.

The example computes area using `int` to stay focused on pattern matching. In real applications, you should validate value ranges and watch out for overflow during subtraction/multiplication; consider `long` or checking bounds first.

## 4. Branch Ordering, Domination, and Fallback Branches

### 4.1. Specific/Guarded Patterns Should Come Before General Branches

Consider a valid ordering:

```java
return switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 -> "Origin";
    case Point(int x, int y) when x > 0 && y > 0 -> "Quadrant I";
    case Point(int x, int y) -> "Other point";
    default -> "Other";
};
```

If you put the **unguarded** `case Point(int x, int y)` first, all subsequent `Point(...) when ...` branches are covered by it, creating a **dominated case label** that the compiler will reject. A branch with a non-constant-true guard like `x > 0` only covers part of the value space, so other branches can still handle the rest.

Similarly, with a type pattern:

```java
case String s when s.isBlank() -> "Blank string";
case String s -> "Non-blank string";
```

The unguarded `String s` branch should come after the blank-string check. If `s` is blank, the first branch is chosen; otherwise, the second branch is chosen.

### 4.2. Guards Alone Do Not Make a `switch` Exhaustive

If you only write:

```java
// Incomplete idea for all Points:
// case Point(int x, int y) when x > 0 -> ...
```

this branch does not handle `Point(0, y)` or points with `x < 0`. For a `switch` expression, the compiler requires the branches to cover the entire relevant domain. Add a general `Point` branch, or a `default`/other branches appropriate for the input type.

With the **sealed hierarchy** in the example, the guarded `Transfer` branches **do not replace** an unguarded `Transfer` branch because `amount` can be 0 or negative. By adding an unguarded `case Transfer(...)` and `case Cancel(...)`, the compiler can verify that every variant permitted by the sealed interface is handled.

### 4.3. A `false` Guard Differs from `break` or Fall-Through

If a pattern matches and `when` evaluates to `false`, **none of the statements in that branch's body are executed**; the search for a matching branch continues. This is not the `fall-through` of the old colon-style `switch`. With `case ... ->`, each branch represents a separate outcome.

## 5. Pattern Variable Scope and Short-Circuiting

A pattern variable can only be used where the compiler can prove the corresponding pattern has matched:

```java
if (candidate instanceof Point(int x, int y)
        && x > 0
        && y > 0) {
    System.out.println("Accepted: " + x + "," + y);
}
```

If `candidate` is a string or null, `instanceof` returns `false`; the right-hand side of `&&` does not run. The variables `x` and `y` are allowed to appear in the condition after `&&` and inside the `if` body.

**Incorrectly using `||` to reference pattern variables where the pattern may not have matched:**

```java
// Does not compile:
// if (candidate instanceof Point(int x, int y) || x > 0) {
//     System.out.println(y);
// }
```

When the left-hand side is `false`, the right-hand side of `||` executes, but `x` and `y` have never been assigned. You need to split the condition or use `&&` appropriately.

In `switch`, the variables `x` and `y` of `case Point(int x, int y) when ...` are in scope in **that branch's guard and body**. Variables declared by one branch cannot automatically be used in other `case` branches.

If a condition becomes long, you can extract the logic into a Boolean method:

```java
static boolean validPoint(int x, int y) {
    return x >= 0 && y >= 0;
}

// In switch:
case Point(int x, int y) when validPoint(x, y) -> "Valid";
```

This helps name the business rule and makes it easy to unit test independently. Calling a method in a guard **does not change the rules**: the guard still runs only after the pattern matches.

## 6. Guards with Nested Record Patterns and `null`

When multiple records are nested, every pattern level must match before Java evaluates the guard. For example:

```java
record Point(int x, int y) {}
record Rectangle(Point start, Point end) {}

// Idea for checking based on structure and coordinates:
case Rectangle(
        Point(int x1, int y1),
        Point(int x2, int y2))
        when x2 > x1 && y2 > y1 ->
        "Valid rectangle";
```

If `start` or `end` is null, the inner `Point(...)` pattern does not match. Therefore, the guard using `x1`, `y1`, `x2`, `y2` is **not evaluated**. A general `case Rectangle(var start, var end)` branch can handle a record with null components because `var` in a component position matches the corresponding type.

There are three cases to distinguish:

| Value | What happens? |
| --- | --- |
| `value == null` | Does not match `Rectangle(...)` or `Point(...)`; in `switch`, it can be handled with `case null`. |
| `new Rectangle(null, new Point(2, 3))` | The nested pattern `Rectangle(Point(...), Point(...))` does not match; the guard does not run. |
| `new Rectangle(new Point(0, 0), new Point(2, 3))` | Both `Point(...)` patterns match, and then the guard checks the coordinate ordering. |

**Do not assume `default` handles a null selector.** In pattern matching for `switch`, if the selector is null and there is no matching null branch, a `NullPointerException` is normally thrown. In the full runnable example, `case null` handles this explicitly.

**A guard itself can throw an exception:** an expression like `when name.length() > 3` can throw a `NullPointerException` if `name` is null and the preceding pattern allows a null component. If you use a nullable object/string in a guard, check for null:

```java
record Message(String content) {}

// With a String component, the variable s can be null.
case Message(var s) when s != null && !s.isBlank() ->
        "Non-blank message";
case Message(var s) -> "Empty or null message";
```

Guards should be simple, fast, and free of side effects so that branching stays predictable and readable.

## 7. Combining Multiple Business Conditions

Guards are ordinary Boolean expressions; you can use `&&`, `||`, comparisons, pure method calls, and variables bound by the pattern.

**Quantity classification example:**

```java
record Order(String customer, int quantity, boolean priority) {}

// The following labels illustrate part of a switch:
case Order(var customer, int quantity, boolean priority)
        when priority && quantity >= 10 ->
        "Large priority order";

case Order(var customer, int quantity, boolean priority)
        when priority ->
        "Priority order";

case Order(var customer, int quantity, boolean priority)
        when quantity > 0 ->
        "Regular order";

case Order(var customer, int quantity, boolean priority) ->
        "Invalid quantity";
```

Branches are ordered from the most specific condition to the remaining cases. Reusing the same variable names across labels does not mean they are the same variable; each label matches and binds its own data.

**Combining guards with sealed types:** you can classify each variant and then filter further by its data, like `Transfer` in the full example. If you add a new subtype to `permits`, recompile your exhaustive `switch` statements/expressions to find every place that needs to handle the new variant.

## 8. Common Mistakes

1. **Writing `when` in `instanceof`.** Wrong: `if (o instanceof Point(int x, int y) when x > 0)`. Right: `if (o instanceof Point(int x, int y) && x > 0)`.
2. **Placing an unguarded branch before a guarded branch.** The general branch can dominate the later branch, causing a compile-time error.
3. **Assuming a guard makes a `switch` exhaustive.** `case Point(...) when x > 0` does not cover the remaining `Point` values; add an unguarded branch or a fallback branch.
4. **Reading pattern variables where the pattern may not have matched.** Combining `||` with a variable declared only on the left-hand side usually violates flow scoping.
5. **Missing a null selector.** `default` does not automatically replace `case null` in pattern-matching `switch` constructs that need to handle null.
6. **Confusing a null selector with a null component.** `case null` handles the top-level selector; a nested null component requires a fallback pattern and/or an appropriate condition.
7. **Putting side effects in a guard.** Updating state, performing I/O, or mutating data inside `when` makes branch selection unpredictable and hard to test. Prefer pure Boolean conditions.
8. **Treating a guard like a cast.** A guard is evaluated after the pattern matches; only the pattern introduces variables of the matched type/structure. A guard cannot fix a malformed or incompatible record pattern.
9. **Using guard expressions that can throw.** For example, accessing `name.length()` when `name` is nullable or dividing when the divisor can be 0; add protective checks.

## 9. How to Choose in Real-World Code

- If you only need a single type/structure check and a simple condition, use `instanceof Pattern && condition` in an `if`.
- If you need to **classify multiple cases** based on the same selector, use `switch` with multiple `case Pattern when condition` branches and a fallback branch.
- If the data consists of nested records, nest the record patterns inside one another and use a guard for conditions involving the extracted components.
- If using a sealed hierarchy, verify that unguarded branches cover all variants for a `switch` expression.
- If business conditions are complex, move the logic into a clearly named method returning `boolean`, and test boundary values, nulls, and exceptions.

**Takeaway:** A pattern decides **which structure matches**; a guard decides **whether the values inside that structure satisfy a condition**. In `switch`, use `when` after the pattern; in `if`, use `&&` after `instanceof`. Always order branches by specificity, handle remaining cases, and check for null at the right level.

### References

- JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
- JEP 440 — Record Patterns (Java 21): https://openjdk.org/jeps/440
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
