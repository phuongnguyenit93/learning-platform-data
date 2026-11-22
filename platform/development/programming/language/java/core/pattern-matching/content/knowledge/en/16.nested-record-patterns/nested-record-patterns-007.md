# Variable Scope in Nested Patterns (Java 21+)

## 1. Why understand pattern variable scope?

When matching a *nested record pattern*, Java can create multiple **pattern variables** with a single expression. However, these variables can only be used on execution paths where the compiler knows for certain that **the pattern has matched**. This is **flow scoping**, which differs from how an ordinary local variable remains in scope throughout the block after its declaration.

Consider two data types:

~~~java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
~~~

With:

~~~java
Object input = new Segment(new Point(1, 2), new Point(6, 8));

if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))) {
    System.out.println(ex - sx); // 5
}
~~~

- `Segment(...)` is the outermost record pattern.
- The two `Point(...)` are **nested record patterns**, each receiving the `start` or `end` component of `Segment`.
- `sx`, `sy`, `ex`, `ey` are four **pattern variables** declared by the `int` component patterns inside the two `Point` patterns.
- The variables can only be used inside the `if` branch when **both the `Segment` pattern and both `Point` patterns match**.

The names `sx`, `sy` do not need to match the record's `x`, `y` names: Java matches components **by declaration position**, not by pattern variable name. Record patterns were standardized in Java **21**, so the examples in this article use JDK 21+.

## 2. A nested pattern succeeds only when all sub-patterns match

The following expression must check the outermost record and all relevant component values:

~~~java
input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))
~~~

If `input` is `null`, is not a `Segment`, or is a `Segment` whose `start` or `end` is `null`, the corresponding `Point(...)` patterns will not match; the entire record pattern fails. No valid execution path is allowed to use `sx`, `sy`, `ex`, `ey` when the outermost pattern has not matched completely.

Conversely, when the entire pattern matches, Java knows all four variables have appropriate values and types. With `Point(var sx, var sy)`, the inferred type of `sx` and `sy` is still `int` because the record components have type `int`. The `var` keyword here does not create a dynamic type.

Note: this is **variable usage scope**, not the lifetime of the record or the data the variable refers to. The record value can still be held in another variable after the `if` block ends; pattern variable names follow their own scoping rules.

## 3. Inside an `if` condition: the true branch has the variables, the false branch does not

~~~java
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))) {
    int dx = ex - sx;           // VALID: the pattern has matched
    System.out.println(dx);
} else {
    System.out.println("Không khớp");
    // System.out.println(sx);  // ERROR: sx is not in scope in the else branch
}
// System.out.println(ex);      // ERROR: the pattern variables are no longer in scope here
~~~

This is an **illustrative snippet** using `input` and the two record types defined above. The lines marked “ERROR” illustrate usage that does not compile; they are placed in comments so they do not affect valid code.

Reason: the `else` branch may be taken because the object is not a `Segment` or because a nested `Point` pattern did not match. Java cannot guarantee that `sx` and `ex` have been assigned on that path.

Do not assume that every name declared inside the parentheses of a record pattern remains in scope until the end of the method. **The position of the pattern expression and the control-flow paths** determine where that name is valid.

## 4. The `&&` operator: variables can be used on the right-hand side and in the true branch

Java evaluates `a && b` from left to right and only evaluates `b` when `a` is true. Therefore, if `a` successfully tests a nested record pattern, the pattern variables can be used in `b`:

~~~java
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))
        && ex > sx) {
    System.out.println("Độ dịch chuyển ngang: " + (ex - sx));
}
~~~

`ex` and `sx` are valid in `ex > sx` because Java only reaches the right-hand side after the pattern on the left has matched. When run with `input` from the first example, the program prints `Độ dịch chuyển ngang: 5`.

Multiple variables from nested levels can be used simultaneously:

~~~java
if (input instanceof Segment(
        Point(var sx, var sy),
        Point(var ex, var ey))
        && ex > sx
        && ey > sy) {
    System.out.println("Đi sang phải và lên trên");
}
~~~

Both additional conditions are evaluated only when the record pattern matches. The `if` branch runs only when the pattern matches and all accompanying conditions are true.

Do not mechanically replace `&&` with `||`:

~~~java
// WRONG, does not compile: if the pattern on the left fails,
// ex and sx are not guaranteed to be assigned on the right-hand side.
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))
        || ex > sx) {
    System.out.println("...");
}
~~~

With `||`, the right-hand side is evaluated when the left-hand side is **false**, at the exact moment when we do not know whether the pattern variables have been assigned. This snippet only serves to point out the error and is **not included in the runnable program** in the later section.

## 5. Negation `!` and early-exit conditions

Negation can invert which branch is guaranteed to match. A very useful technique is a **guard clause**: exiting the method immediately when the pattern does not match.

~~~java
static int horizontalDistanceOrMinusOne(Object input) {
    if (!(input instanceof Segment(
            Point(int sx, int sy),
            Point(int ex, int ey)))) {
        return -1;
    }

    // Reaching here, the non-matching branch has already returned,
    // so the compiler knows the pattern must have matched.
    return ex - sx;
}
~~~

This is an **illustrative method** placed inside a class that declares `Point` and `Segment`. Unlike the first `if` example, `sx` and `ex` **remain usable after the `if` block**, because every path reaching `return ex - sx` has the record pattern condition satisfied. If the method did not exit in the non-matching branch, this guarantee could not be inferred.

Negation can also be validly combined with `||`:

~~~java
static int positiveDistanceOrMinusOne(Object input) {
    if (!(input instanceof Segment(
            Point(int sx, int sy),
            Point(int ex, int ey)))
            || ex <= sx) {
        return -1;
    }
    return ex - sx;
}
~~~

Here, the right-hand side `ex <= sx` is evaluated only when the negated condition on the left is **false**, meaning the record pattern **has matched**. Therefore, `ex` and `sx` are in scope on the right-hand side. After the `if`, paths that did not match or had `ex <= sx` have already returned `-1`.

Do not confuse “having `!` makes the variable disappear” with the actual rule: Java analyzes **the paths that make the condition true or false**, including the possibility of exiting the function early.

## 6. Nested patterns in `switch`: per-branch variables

When using record patterns in `switch`, the nested variables are in scope for **the corresponding `case` branch**, including its `when` guard expression and the body of that branch:

~~~java
static String describe(Object input) {
    return switch (input) {
        case Segment(Point(var sx, var sy), Point(var ex, var ey))
                when ex > sx ->
                "right: " + (ex - sx);
        case Segment(Point(var sx, var sy), Point(var ex, var ey)) ->
                "not right: " + (ex - sx);
        case null -> "null input";
        default -> "other";
    };
}
~~~

- In the first branch, the variables `sx` and `ex` have been created by the `Segment(... Point(...), Point(...))` pattern. Therefore, the `when ex > sx` condition can reference them.
- If `when` is false, `switch` can try the next branch. The second branch has **its own declarations of `sx`, `sy`, `ex`, `ey`**, and does not use the variables created from the first branch.
- After exiting `switch`, those pattern variables cannot be used in statements outside `switch` simply by their names.
- `case null` handles **the value `input == null` itself**. A `Segment` with `end == null` will not match the two `Point(...)` patterns, and in this example falls through to `default` to return `"other"`.

You can repeat pattern variable names across **two different `case` branches** as shown in the example because the declarations belong to different scopes. However, **you cannot declare duplicate names within the same pattern** (for example, using `sx` for both components of `Point`).

When you need to pass destructured values outside `switch`, return a result from a `switch expression`, call a processing method in each branch, or assign to a variable declared in an outer scope. Do not rely on the pattern variable names of a single `case`.

## 7. Complete Java 21 program

Create the file `NestedPatternScopeDemo.java`:

~~~java
public class NestedPatternScopeDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static int horizontalDistanceOrMinusOne(Object input) {
        if (!(input instanceof Segment(
                Point(int startX, var startY),
                Point(int endX, var endY)))) {
            return -1;
        }
        return endX - startX;
    }

    static String describe(Object input) {
        return switch (input) {
            case Segment(Point(var sx, var sy), Point(var ex, var ey))
                    when ex > sx -> "right: " + (ex - sx);
            case Segment(Point(var sx, var sy), Point(var ex, var ey)) ->
                    "not right: " + (ex - sx);
            case null -> "null input";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object candidate = new Segment(
                new Point(1, 2),
                new Point(6, 8)
        );

        if (candidate instanceof Segment(
                Point(var sx, var sy),
                Point(var ex, var ey))
                && ex > sx) {
            System.out.println("start=" + sx + "," + sy);
            System.out.println("end=" + ex + "," + ey);
        }

        System.out.println(horizontalDistanceOrMinusOne(candidate));
        System.out.println(horizontalDistanceOrMinusOne(
                new Segment(new Point(4, 4), null)));

        System.out.println(describe(candidate));
        System.out.println(describe(new Segment(
                new Point(9, 1),
                new Point(3, 1))));
        System.out.println(describe(null));
    }
}
~~~

Compile and run with JDK 21+ (no `--enable-preview` required):

~~~bash
javac --release 21 NestedPatternScopeDemo.java
java NestedPatternScopeDemo
~~~

Exact output:

~~~text
start=1,2
end=6,8
5
-1
right: 5
not right: -6
null input
~~~

Scope explanation:

1. The first `if` branch successfully matches `Segment(Point(...), Point(...))` and the condition `ex > sx` is true, so it prints both points.
2. `horizontalDistanceOrMinusOne(candidate)` returns `6 - 1 = 5`. The variables `startX`, `endX` remain in scope after the guard clause because the non-matching path has exited the function.
3. With `end == null`, the nested pattern `Point(int endX, var endY)` does not match, so the function returns `-1` without using any uncreated pattern variables.
4. The two `switch` branches share the same `sx`/`ex` names but have separate scopes. The `when ex > sx` condition leads to `"right: 5"` for the first segment; the opposite-direction segment takes the second branch `"not right: -6"`.
5. The `null` object matches `case null`. No record pattern variables are used in this branch.

This is a standalone program: the record declarations, methods, and `main` are all in the same file. The non-compiling examples from earlier sections are annotated separately and **do not appear** in this file.

## 8. Pattern variable scope quick reference table

| Location | Can `sx`, `ex` from the nested pattern be used? | Reason |
| --- | --- | --- |
| Body of `if (obj instanceof Segment(...))` | Yes | The true condition confirms the entire pattern matched. |
| `else` body of a non-negated `instanceof` condition | No | The false branch does not guarantee the pattern matched. |
| Right-hand side of `instanceof ... && ex > sx` | Yes | `&&` evaluates the right-hand side only when the left pattern is true. |
| Right-hand side of `instanceof ... || ex > sx` | No | `||` evaluates the right-hand side when the left pattern is false. |
| Right-hand side of `!(instanceof ...) || ex <= sx` | Yes | The negation being false means the `instanceof` pattern is true. |
| After `if (!(obj instanceof ...)) return;` | Yes, on the continuing path | The non-matching path has terminated. |
| `when` guard of `case Segment(...)` | Yes | The guard is evaluated after the pattern in `case` matches. |
| Expression after `->` of the same `case` | Yes | The branch has matched and satisfied the guard (if any). |
| Another `case` or after `switch` | Do not share that declaration | Each branch has its own scope. |

## 9. Common mistakes and fixes

**Mistake 1 — using a variable after a condition that can fail.**

~~~java
// WRONG illustration: if the pattern does not match, sx has no guaranteed value.
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))) {
    System.out.println("matched");
}
// System.out.println(sx); // ERROR if uncommented
~~~

**Fix:** move the logic using `sx` inside the `if` branch, or use a guard clause with `return`/`throw` on the non-matching path.

**Mistake 2 — confusing variables of outer and inner patterns.** `Segment` has `start` and `end` components of type `Point`; `sx` is created from the `x` component of the `Point` inside `start`. A multi-level nested record pattern does *not* automatically make variable names become fields or properties of the outer record.

**Mistake 3 — using the same name within one pattern.**

~~~java
// WRONG: declaring sx twice in the same pattern.
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int sx, int ey))) {
    // ...
}
~~~

**Fix:** give a unique name to each pattern variable coexisting in the same scope, such as `startX` and `endX`.

**Mistake 4 — thinking variables in a `when` guard are available in all `case`s.** When a branch fails its `when` guard, that branch's pattern variables are not carried over to the next branch; the next branch must declare its own pattern.

**Mistake 5 — overlooking `null` in a nested record.** `Segment(new Point(1, 2), null)` is a valid `Segment` object, but it does **not** match `Segment(Point(...), Point(...))` because `end` does not match the `Point` pattern. Only use pattern variables when the match succeeds; if the data allows `null`, a fallback handling path is needed.

**Mistake 6 — assuming `var` allows calling any method.** `var` infers the type from the **component declaration** (for example, `Point` returns `int`); that type is still checked by the compiler. `var` does not turn a variable into an arbitrary type based on the runtime value.

## 10. How to self-check a variable usage site

When looking at a complex nested record pattern, ask three questions:

1. **Where is the variable declared?** Point to the exact component pattern that creates that name, for example `Point(int sx, int sy)`.
2. **At the usage site, is it certain that the outermost pattern and all sub-patterns have matched?** Trace the actual paths of `if`, `&&`, `||`, negation, and guard clauses.
3. **Is it still inside the corresponding `case` branch?** With `switch`, the `when` guard and the body of that same branch can use the variables; other branches must have their own declarations.

**Remember:** Variable scope in nested patterns is determined by **control flow proving that the pattern matched**, not merely by the parentheses enclosing the declaration. Variables at multiple levels of a record pattern can only be used at points where Java is certain the overall match has succeeded.