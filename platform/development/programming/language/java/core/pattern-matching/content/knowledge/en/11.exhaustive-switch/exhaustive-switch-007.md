# How the Compiler Checks Missing Branches in Exhaustive `switch` (Java Pattern Matching)

## 1. What is an exhaustive `switch`?

A `switch` is called **exhaustive** when its set of `case` labels is sufficient to handle **every input value allowed by the type system** according to Java's coverage rules. If a form of `switch` is required to be exhaustive and the compiler cannot prove this completeness, the code **will not compile**.

For example, with an `enum` having three constants:

```java
enum Light { RED, YELLOW, GREEN }

static String action(Light light) {
    return switch (light) {
        case RED -> "STOP";
        case YELLOW -> "WAIT";
        // Missing GREEN: the switch expression does not compile.
    };
}
```

This is **code illustrating an error**, not a compilable program. Because a `switch` expression must produce a result for every valid value of `Light`, the compiler determines that `GREEN` is missing and rejects it.

Conversely, the following complete version **is valid on Java 21**:

```java
static String action(Light light) {
    return switch (light) {
        case RED -> "STOP";
        case YELLOW -> "WAIT";
        case GREEN -> "GO";
    };
}
```

When all values of an `enum` are listed, a `switch` expression does not require `default`. This is especially useful: if a `BLUE` constant is added later and the code using `switch` is recompiled, the compiler can point out where the logic needs to be updated.

**Key takeaway:** exhaustiveness is determined **at compile time** based on the selector type and the `case` labels; not by running a few test inputs and inferring "there are no other branches."

## 2. Which forms of `switch` does the compiler check?

Not all `switch` statements have the same requirement.

| Construct | Must be exhaustive? | Example |
| --- | --- | --- |
| **`switch` expression** (uses the resulting value) | **Yes** | `String x = switch (value) { ... };` |
| **Enhanced `switch` statement** (Java 21: has pattern labels, `case null`, or forms classified as enhanced) | **Yes** | `switch (obj) { case String s -> ...; }` |
| **Traditional `switch` statement** with constant labels in traditional syntax | **Not necessarily** | `switch (light) { case RED: ...; break; }` |

**`switch` expression:** if there is no catch-all label and there are still uncovered types/constants, the compiler reports an error. A program cannot evaluate an expression that has a path producing no value.

**Enhanced `switch` statement:** Java 21 requires exhaustiveness even when no value is returned. Because patterns can be used for a selector of type `Object` or a `sealed` hierarchy, the compiler needs to ensure the set of labels covers all matching non-`null` values, according to language rules.

**Traditional `switch` statement:** branches may be omitted. If no label matches, the statement simply completes without executing a `case` branch, or executes surrounding logic as written by the programmer. This is permitted behavior under the traditional syntax, not a guarantee that all cases have been handled.

Example illustrating a valid traditional statement:

```java
static void showRed(Light light) {
    switch (light) {
        case RED:
            System.out.println("RED");
            break;
    }
}
```

When `light` is `GREEN` or `YELLOW`, this example prints nothing. There is no compile-time error about missing branches because this is a traditional `switch` statement.

In this article, examples with patterns are written for **Java 21**, where pattern matching for `switch` is a standard feature (JEP 441). No preview flag is needed for the Java 21 syntax shown.

## 3. How does the compiler infer completeness?

The compiler does not need to "guess" all runtime objects. It uses the **static type** of the expression in `switch (...)` and the rules regarding the set of values that can match:

1. **`default`** can cover **non-`null`** values not matched by earlier labels. This is the general solution when the selector is an open type like `Object`.
2. **All constants of an `enum`** form a closed set. If there is already a case for every constant, a `switch` expression can be exhaustive without `default`.
3. **Subtypes of a `sealed` type** declared in the `permits` clause form a controlled set of implementations. Appropriate patterns covering all permitted subtypes can make a `switch` exhaustive.
4. **A sufficiently general pattern** can cover all non-`null` values of the selector type. For example, `case Object obj -> ...` with an appropriate reference selector.
5. **Record patterns** can contribute to coverage analysis when the record structure and component patterns are appropriate; in this article, `case Literal(int n)` and `case Add(var left, var right)` are used as illustrations.
6. **`when` guards** with arbitrary conditions **are not assumed to always be true**. A guarded case does not by itself prove that all values of that pattern type are handled.

If the compiler does not have sufficient proof, it reports that the `switch` does not cover all possible values. The exact wording of the message and highlight location depend on the JDK/IDE; what matters is that **the error is caught before execution**.

**Exhaustive does not mean every value executes a branch:** a reference selector that is `null` still needs to be handled explicitly if you want to match it. A `switch` that is exhaustive over non-`null` values can still throw `NullPointerException` when the selector is `null`; `default` generally **does not** catch a `null` selector.

## 4. Complete Java 21 program: the compiler accepts a sufficient set of branches

Create the file **`CompilerExhaustiveSwitch.java`**:

```java
public class CompilerExhaustiveSwitch {
    sealed interface Expr permits Literal, Add, Negate {}

    record Literal(int value) implements Expr {}
    record Add(Expr left, Expr right) implements Expr {}
    record Negate(Expr inner) implements Expr {}

    enum Light { RED, YELLOW, GREEN }

    static int evaluate(Expr expr) {
        return switch (expr) {
            case Literal(int n) -> n;
            case Add(var left, var right) ->
                evaluate(left) + evaluate(right);
            case Negate(var inner) -> -evaluate(inner);
        };
    }

    static String action(Light light) {
        return switch (light) {
            case RED -> "STOP";
            case YELLOW -> "WAIT";
            case GREEN -> "GO";
        };
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.length() >= 4 ->
                "LONG:" + text;
            case String text -> "SHORT:" + text;
            case Integer number -> "INT:" + number;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Expr formula = new Add(
            new Literal(2),
            new Negate(new Literal(5))
        );

        System.out.println(evaluate(formula));
        System.out.println(evaluate(new Literal(8)));
        System.out.println(action(Light.GREEN));

        Object[] values = {
            "java", "hi", Integer.valueOf(7), null, 2.5
        };
        for (Object value : values) {
            System.out.println(describe(value));
        }

        try {
            evaluate(null);
        } catch (NullPointerException e) {
            System.out.println("NULL_EXPR");
        }
    }
}
```

Compile/run using **JDK 21 or later**, targeting Java 21 language level:

```bash
javac --release 21 CompilerExhaustiveSwitch.java
java CompilerExhaustiveSwitch
```

Exact stdout:

```text
-3
8
GO
LONG:java
SHORT:hi
INT:7
NULL
OTHER
NULL_EXPR
```

### Why does the program compile?

- `Expr` is a `sealed interface` permitting exactly three records: `Literal`, `Add`, `Negate`. The three record patterns in `evaluate` cover the forms of `Expr`. **No `default` is needed.**
- With `Add(var left, var right)`, `var` infers the component type as `Expr`. The `evaluate` method calls itself recursively for both sides; `Negate` negates the sign.
- `Light` has three constants and `action` lists all three. **No `default` is needed.**
- `describe(Object)` works on the open type `Object`, so it has `default` for non-`null` values that are neither `String` nor `Integer`. The `case null` branch catches a `null` selector.
- The two `String` branches in `describe` have a guarded case and an unguarded fallback. The second `String text` branch catches every string not selected by the first branch.
- `evaluate(null)` has an exhaustive `switch` over the subtypes of `Expr` but no `case null`, so it still throws `NullPointerException`; the `catch` in `main` prints `NULL_EXPR`.

This is an important demonstration: **the compiler proves coverage of type shapes; the compiler does not automatically guarantee that you have designed a `null`-handling policy or valid business data.**

## 5. Cases where the compiler detects missing branches

### A. `enum`: omitting a constant

The following code **intentionally fails on Java 21**:

```java
enum Status { NEW, RUNNING, DONE }

static String label(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        // Missing DONE and no default.
    };
}
```

For the `Status` type, the compiler knows the constant `DONE` is not yet covered. The proper fix when each constant needs separate handling is to add:

```java
case DONE -> "Done";
```

The line above is **the label added to the `switch`**, not a standalone program.

You could add `default -> "Other"` to achieve exhaustiveness, but then future enum changes might be caught by the fallback branch without the compiler forcing you to review the logic. For business logic requiring each enum constant to be distinguished, listing all constants explicitly is usually safer.

### B. `sealed` hierarchy: omitting a permitted subtype

Suppose:

```java
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Shape {}
```

This expression is **not exhaustive**:

```java
static int size(Shape shape) {
    return switch (shape) {
        case Circle(int radius) -> radius * radius;
        // Missing Square.
    };
}
```

The compiler knows `Square` is a permitted subtype of `Shape`, so it reports that the `switch` is missing a branch. The fix is to add `case Square(int side) -> side * side;` or reorganize the cases to cover `Square`.

**Sealed does not mean all data has a predetermined shape at runtime if you compile/link different modules separately:** permitted classes across the corresponding type hierarchy must be considered. Nevertheless, sealed lets the compiler know the valid subtypes **in the type at compile time** and clearly points out missing branches when the hierarchy is modified and recompiled.

### C. Open-type selector: missing `default` or general pattern

With selector `Object value`:

```java
static String textOnly(Object value) {
    return switch (value) {
        case String text -> "S:" + text;
        case Integer number -> "I:" + number;
        // Could be Double, Boolean, another Object...
    };
}
```

The code above **intentionally does not compile**. The `Object` type has countless other value types; the compiler cannot conclude that `String` and `Integer` cover everything. Fix it with:

```java
static String textOnly(Object value) {
    return switch (value) {
        case String text -> "S:" + text;
        case Integer number -> "I:" + number;
        default -> "Other";
    };
}
```

This is exhaustive for non-`null` objects. If you want to return `"Null"` when the selector is `null`, add `case null -> "Null";` or combine `case null, default -> "Other";` as needed.

### D. Enhanced `switch` statement: missing branch even without returning a value

Example **intentionally failing in Java 21**:

```java
static void print(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
        // Missing all non-String objects.
    }
}
```

This is an **enhanced switch statement** because it has a pattern label. Java 21 requires exhaustiveness, so the compiler rejects it. Add `default -> {}` for a no-op branch, or handle each required type. When the input can be `null`, consider adding `case null` if you do not want a `NullPointerException` thrown.

Do not confuse this with the traditional `switch` statement example having a single enum branch in section 2: one case does not require exhaustiveness; the other does.

## 6. A `when` guard does not by itself cover an entire type

Consider a `sealed` hierarchy with `Circle` and `Square` as in the previous section:

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius > 0 ->
            "Positive circle";
        case Square(int side) -> "Square";
    };
}
```

This **does not compile** because a `Circle(0)` or `Circle(-2)` can still be created with the record defined above. The pattern `Circle(int radius)` matches, but the guard `radius > 0` is false. Thus, there is still a missing handling path for `Circle`.

An exhaustive version is:

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius > 0 ->
            "Positive circle";
        case Circle(int radius) ->
            "Non-positive circle";
        case Square(int side) -> "Square";
    };
}
```

The unguarded `Circle` branch placed afterward ensures the remaining `Circle` values are still matched. You can use `default` when appropriate, but explicit cases help present all forms clearly.

### Guards and branch order

The compiler also checks **dominance** (an earlier branch covering a later branch). For example:

```java
// Intentional error: the later branch is dominated.
return switch (shape) {
    case Circle(int radius) -> "Any circle";
    case Circle(int radius) when radius > 0 ->
        "Positive circle";
    case Square(int side) -> "Square";
};
```

Even though the type set is covered, the guarded branch afterward never has a chance to be selected because the unguarded `Circle` branch before it catches every `Circle` value. Fix this by placing **the specific guarded case first**, followed by the unguarded case.

**Two different checks:**
- *Exhaustiveness* asks: is there any value that is not handled?
- *Dominance* asks: is there any label shadowed by an earlier label such that it can never be selected?

A `switch` can have sufficient coverage and still fail to compile due to dominance.

## 7. Record patterns and coverage capability

A record pattern directly declares the data structure to match. In the complete program in section 4:

```java
case Literal(int n) -> n;
case Add(var left, var right) -> evaluate(left) + evaluate(right);
case Negate(var inner) -> -evaluate(inner);
```

These three patterns respectively cover the three permitted records of `Expr`. The component patterns `int n` and `var left/right/inner` have types matching the record declarations, so they do not leave an unmatched form of `Literal`, `Add`, or `Negate` just because of ordinary component values.

However, **not every nested record pattern automatically covers all values of the outer record**. For example, with:

```java
record Point(int x, int y) {}
record Container(Point point) {}
```

If you write:

```java
case Container(Point(int x, int y)) -> "Has point";
```

this label only matches when the inner `point` component matches the `Point(...)` record pattern. If `point` is `null`, the nested record pattern does not match. An additional case, a more suitable component pattern, or `default` may be needed depending on the selector type and business requirements.

**Note on `null` values inside a record:** the pattern `var p` (a form of unconditional component type pattern) can match a `null` component of a record in Java 21, whereas a nested record pattern `Point(...)` does not match `null`. Do not assume that every component pattern has the same null-matching capability.

In addition, **exhaustiveness is only a static structural check**. If `Add.left()` returns `null`, the `Add(var left, var right)` branch can still be selected, but `evaluate(left)` may throw `NullPointerException`. That is a data contract and runtime issue, not a missing subtype in the `switch`.

## 8. `null`: exhaustive does not mean null-safe

This is a very important distinction:

```java
record Box(int number) {}

static String show(Box box) {
    return switch (box) {
        case Box(int number) -> "Box:" + number;
    };
}
```

This expression can be proven exhaustive by the compiler for **non-`null`** values of type `Box`; it has no `case null`. Calling `show(null)` can still throw `NullPointerException`.

To handle `null` as a specific value:

```java
static String show(Box box) {
    return switch (box) {
        case null -> "Missing";
        case Box(int number) -> "Box:" + number;
    };
}
```

With an `Object` selector:

```java
static String show(Object value) {
    return switch (value) {
        case String text -> "Text:" + text;
        case null, default -> "Other";
    };
}
```

The `case null, default` branch handles a `null` selector **and** objects that do not match `String`. If you do not want to combine these two, write `case null` and `default` separately.

Do not assume a rule like "whenever there is `default`, `null` is definitely handled." For Java 21 pattern `switch`, a plain `default` does not automatically catch `null`.

## 9. Compile-time checks differ from runtime safety

The compiler can prove a `switch` is exhaustive **at compile time**, yet the program can still encounter exceptions at runtime:

- **`null` selector:** if `case null` is missing, the program can throw `NullPointerException` when evaluating the `switch`.
- **Invalid data inside a record:** the record pattern matches, but the branch action can fail due to negative numbers, `null` components, division by zero, failed API calls, etc.
- **Type changes across builds:** when an enum/sealed hierarchy is modified and previously compiled classes still run against the new definition without consistent recompilation, a `switch` considered exhaustive in the old build may encounter a new value with no branch. In Java 21, the case where no label applies at runtime can result in `MatchException` (different from `NullPointerException` for a null selector).

Therefore, **exhaustiveness is not a guarantee that "this method will never throw an exception."** It is a guarantee of **label coverage according to the type system** at compile time, with additional runtime rules.

### When should you use `default`?

Consider the following:

- For **open** selector types like `Object`: `default` is usually necessary, unless a general pattern already covers the remaining values.
- For **enums/sealed hierarchies with a closed set of cases**: usually **do not add `default`** when the goal is to have the compiler remind you to update logic if a new state/subtype is added. Exceptions exist: business requirements may want a generic fallback behavior.
- For `when` labels that only match a subset of values: an appropriate unguarded case or `default` is needed.
- For inputs that can be `null`: decide on an explicit policy for `null`; do not use `default` as an implicit substitute.

## 10. How to check and fix "switch not exhaustive" errors

When encountering messages like "switch expression does not cover all possible input values" or "switch statement does not cover all possible input values", follow these steps:

1. **Identify the `switch` form:** expression, enhanced statement, or traditional statement?
2. **Check the static type of the selector:** `enum`, `sealed interface`, concrete record, or open type like `Object`?
3. **List all possible cases:** all enum constants, permitted subtypes, or unmatched types for an open selector.
4. **Check whether each `case` label truly covers the entire type:** a branch with `when` may only match a subset; a nested record pattern may have an unmatched component.
5. **Ensure no branch is dominated:** a general branch must not be placed before a specific branch that needs to run.
6. **Add a semantically meaningful case or fallback:** for enum/sealed, prefer adding the missing branch; for open types, consider `default`.
7. **Check `null` separately:** add `case null` if needed, rather than inferring it from `default`.
8. **Compile with the right project version:** `javac --release 21` or the equivalent setting in your IDE/build tool; avoid confusing preview features of other versions.

Do not "silence the error" by mechanically adding `default -> null` or `default -> 0`. If the missing case is an important business state, an arbitrary default value can cause silent bugs instead of being caught early.

## 11. Summary table

| Selector / design | Existing branches | Exhaustive in Java 21? | Things to watch out for |
| --- | --- | --- | --- |
| `enum Light {RED,YELLOW,GREEN}` | Only `RED`, `YELLOW` in a switch expression | No | Missing `GREEN` |
| Same enum | All three constants, no `default` | Yes | A `null` selector can still throw NPE |
| `sealed Expr` with three records | `Literal`, `Add`, `Negate` | Yes | Recursive actions must still handle valid data |
| `Object` | Only `String` and `Integer` | No | Many other types remain |
| `Object` | `String`, `Integer`, `default` | Yes for non-`null` values | `null` needs separate handling if you want to avoid NPE |
| `Shape` with `Circle` and `Square` | `Circle` with guard `radius > 0`, `Square` | No | `Circle` values not satisfying the guard are missed |
| Enhanced statement on `Object` | Only `case String s` | No | Enhanced switch statements also require exhaustiveness |
| Traditional statement on enum | Only `case RED: ... break;` | Not required | For other constants, it may do nothing |

## 12. Self-check exercises

**Exercise 1 — Adding a state to an Enum.** Given `enum Mode { AUTO, MANUAL }` and a switch expression with both branches. Later `PAUSED` is added and the project is recompiled. Without `default`, what happens?

**Answer:** The compiler sees `PAUSED` is not covered and forces the switch expression to be updated. This is a benefit of exhaustive `switch` for closed enums.

**Exercise 2 — Uncovered guard.** With `sealed interface Shape permits Circle, Square`, why are `case Circle(int r) when r > 0` together with `case Square(int s)` not enough?

**Answer:** `Circle(0)` and `Circle(-1)` are still valid according to the declaration. The guard can be false, so an unguarded `Circle` branch or an appropriate fallback must be added.

**Exercise 3 — Null.** With `Object x = null`, a switch expression having `case String s -> ...; default -> ...;` is exhaustive for non-`null` values. Is it guaranteed to enter `default`?

**Answer:** No. `null` is not automatically caught by a plain `default` in Java 21. To handle it, add `case null -> ...` or use `case null, default -> ...`.

**Exercise 4 — Traditional statement.** Why does `switch (light) { case RED: ...; break; }` compile even though the enum has three constants?

**Answer:** It is a traditional switch statement, which is not required to be exhaustive. If you need the compiler to check completeness, you can structure the logic as a switch expression, or explicitly cover all states.

**Remember:** **Exhaustiveness is the compiler's ability to prove that no type case remains uncovered by an appropriate label.** It is especially useful with enums and sealed hierarchies, but must be combined with an understanding of guards, record patterns, the `default` branch, `null` selectors, and the difference between a switch expression and a switch statement.

## Official references

- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.11: Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — §15.28: Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
