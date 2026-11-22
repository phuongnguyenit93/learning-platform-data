# Exhaustive switch expression and missing case errors in Java Pattern Matching

## 1. Mental model: an expression must produce a result for every possibility

In Java, `switch` can be used as an **expression** (switch expression): the entire `switch (...) { ... }` construct evaluates to a value to assign to a variable or return from a method.

```java
enum Stage { NEW, ACTIVE, DONE }

static String label(Stage stage) {
    return switch (stage) {
        case NEW -> "new";
        case ACTIVE -> "active";
        case DONE -> "done";
    };
}
```

Here, the compiler sees that every `Stage` value has a branch: `NEW`, `ACTIVE`, or `DONE`. Therefore, the `switch` is **exhaustive** (covering all possibilities of the input type under consideration). Every time the `switch` expression runs normally with a valid `Stage` value, it has a branch to compute a result.

If `case DONE` is omitted, the program **does not compile**: for `Stage.DONE`, the expression would not know what to return. This is the meaning of a "missing case" error.

```text
Stage
 ├── NEW       ──> "new"
 ├── ACTIVE    ──> "active"
 └── DONE      ──> "done"
                    ↓
           Sufficient branches for type Stage
```

Since Java 21, **pattern matching for switch** (JEP 441) allows `case` labels with type patterns and record patterns, so coverage no longer comes only from listing `enum` constants. The compiler can also prove that all permitted subtypes of a `sealed` hierarchy have handling branches.

**Key point:** exhaustiveness is a property checked **based on the static type and the structure of the cases at compile time**, not by running a few test datasets without error. It also does not automatically mean "null-safe" or "all business conditions have been checked."

## 2. Why does a switch expression need to be exhaustive?

Consider the assignment:

```java
String message = switch (stage) {
    case NEW -> "Received";
    case ACTIVE -> "Processing";
    case DONE -> "Completed";
};
```

`switch` on the right-hand side of `=` is an expression. Java needs to be certain that this expression can complete with a value or throw an exception, and must never fall into a state where "no case executes" when receiving a value from the set the compiler must cover.

Unlike the expression:

```java
int score = switch (stage) {
    case NEW -> 0;
    case ACTIVE -> 50;
    case DONE -> 100;
};
```

A traditional `switch statement` only executes statements:

```java
switch (stage) {
    case NEW -> System.out.println("Received");
    case ACTIVE -> System.out.println("Processing");
    // Omitting DONE in a traditional statement can still compile.
}
```

If a branch is missing, the traditional statement form can simply do nothing for that value. However, **Java 21 requires an enhanced switch statement to be exhaustive**: a switch statement that uses pattern `case`s or `case null`, or switches over extended types outside the traditional group, must also have complete coverage. You should not apply the remark "statements do not need to be exhaustive" to all modern switch statements.

| Form | Must be exhaustive? | Meaning |
| --- | --- | --- |
| `switch` expression | **Required** | The expression must produce a result or complete abruptly; no branch may be missing |
| Traditional switch statement on `int`, `String`, `enum`, without pattern/null cases | **Not required** | There can be inputs that execute no branch |
| Enhanced switch statement (Java 21, with pattern/null cases or an extended-type selector) | **Required** | Must not silently skip a valid case |
| `if / else if` | No equivalent general exhaustiveness mechanism | The author must design an appropriate final branch |

A `switch expression` can use arrow rules `->` or colon label groups and `yield`. `yield` produces a value out of a switch expression:

```java
int score = switch (stage) {
    case NEW -> 0;
    case ACTIVE -> {
        int progress = 50;
        yield progress;
    }
    case DONE -> 100;
};
```

This is an illustrative snippet, assuming `Stage` and the variable `stage` are already declared. Use `yield` inside a block when a branch must execute multiple statements before producing a result. With the `->` syntax, fall-through to the next branch does not occur as it does with traditional `case:` label groups.

## 3. How does Java decide "enough cases"?

According to the Java Language Specification 21, a switch block is considered exhaustive if there is a way to cover the entire **selector type**. Common ways include:

1. Having a `default` branch (or a `case null, default` label).
2. For an `enum`, listing all enum constants of the selector type, without necessarily having `default`.
3. For a `sealed` type, unguarded patterns that can cover all permitted subtypes, examined according to the known inheritance hierarchy.
4. Having a type pattern that matches **unconditionally for the selector type**, such as `case Object obj` for a selector of type `Object` (for non-`null` values).
5. For record patterns, the compiler examines the component possibilities and the coverage of the pattern set; a deep record pattern that only matches a few sub-shapes cannot by itself be considered sufficient for all inputs.

`default` is an easy general-purpose escape hatch, but it is not always the best choice. With `enum` and `sealed`, intentionally omitting `default` lets the compiler remind you when a new value or subtype is added and needs handling.

You must distinguish **two questions**:

- **Type coverage:** for every **non-`null`** value of the selector, is there a matching branch?
- **`null` handling:** if the selector expression is `null`, is there a matching `case null`? If not, `switch` typically throws `NullPointerException`, even when the switch is proven exhaustive with respect to the type.

Example of a general pattern:

```java
Object value = 17;

String result = switch (value) {
    case Object anything -> "Value: " + anything;
};
```

This code is accepted because the pattern `Object anything` covers non-`null` objects of type `Object`. However, passing `null` as the selector still causes `NullPointerException` if there is no `case null`.

## 4. Missing an enum value error

Given:

```java
enum Status { NEW, RUNNING, DONE }
```

The following snippet is **intentionally non-compiling**:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        // Missing case DONE.
    };
}
```

Common error from `javac`:

```text
the switch expression does not cover all possible input values
```

The compiler does not ask "does the current test data ever encounter DONE?". It sees that `Status` declares three constants and the expression only covers two of them. Even if the application today only produces `NEW` or `RUNNING`, the code must still compile validly for the `Status` type.

**Fix 1 — List all enum constants**, allowing the compiler to warn when the enum is extended:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        case DONE -> "Done";
    };
}
```

**Fix 2 — Use `default`** when the business logic genuinely wants to group the remaining values:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW -> "New";
        case RUNNING -> "Running";
        default -> "Other";
    };
}
```

Fix 2 is valid, but if `CANCELLED` is later added to the enum, `default` can silently return `"Other"` instead of forcing the maintainer to decide how to represent the new status. For business domain models with a closed set of values, it is usually better to list all values explicitly so you get warned on expansion.

You do not need a separate branch for every **distinct result**: multiple enum constants can share a single `case` label or produce the same result. What is required is that the possibilities of the selector type are covered.

## 5. Missing a type in a sealed hierarchy

In Java, `sealed` restricts which classes/records/interfaces can directly implement or extend a type. This is the basis for the compiler to prove that a `switch` over that hierarchy has sufficient type branches.

```java
sealed interface Event permits Created, Cancelled, Paid {}

record Created(String orderId) implements Event {}
record Cancelled(String orderId, String reason) implements Event {}
record Paid(String orderId, int amount) implements Event {}
```

An expression **missing a case**:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created " + id;
        case Cancelled(var id, var reason) -> "Cancelled " + id;
        // Missing Paid.
    };
}
```

Compilation fails because `Paid` is also a permitted subtype of `Event`. Fix it by adding:

```java
case Paid(var id, var amount) -> "Paid " + id + " = " + amount;
```

This additional `case` is part of the previous switch, not a standalone Java statement. Once `Created`, `Cancelled`, and `Paid` are all present, the compiler proves the switch is exhaustive even without `default`.

**When is it impossible to enumerate everything?** If the hierarchy contains a `non-sealed` branch or the selector type is an open interface that can receive additional implementations, the set of values is no longer completely closed on that branch. In that case, a general pattern or an appropriate `default` is needed. With `sealed`, you should read the entire hierarchy carefully, not just the classes you commonly see in test data.

### Risk when the hierarchy changes

When adding a permitted subtype, **recompiling** a switch without `default` can detect the missing branch, helping update business logic alongside the model. If components are compiled at different times and the hierarchy changes after the switch code was compiled, an unexpected case at runtime can lead to `MatchException`. Therefore, compile-time exhaustiveness is a guarantee based on the **type version the compiler saw**, and does not replace managing binary compatibility, packaging, and synchronized deployment.

## 6. Why doesn't a guarded pattern cover an entire type on its own?

Java 21 allows adding `when` to constrain a condition:

```java
case Paid(var id, var amount) when amount > 0 -> "Positive payment";
```

This is **not** a branch covering the entire `Paid` type, because `amount` can be 0 or less than 0. The following example is **intentionally non-compiling**:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) when amount > 0 -> "Positive payment";
        // Paid(0) and Paid(-1) have no branch.
    };
}
```

Add an unguarded `Paid` pattern to handle the remainder:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) when amount > 0 -> "Positive payment";
        case Paid(var id, var amount) -> "Non-positive payment";
    };
}
```

Order matters greatly: the narrower branch with `when` comes before the broader unguarded branch. If the broad pattern is placed first, it can shadow the narrow branch (*dominated case*) and lead to a compile error or an unreachable branch.

Regarding **exhaustiveness**, branches with data-dependent guards are generally not counted as full coverage branches. Java 21 has a technical exception where a constant `true` guard can be treated equivalently to no guard; this does not change the practical advice: whenever a business condition can be false, provide a branch to handle the remainder.

## 7. Nested record patterns can miss valid data

A record pattern not only checks the outer record type but also requires the inner component patterns to match. For example:

```java
record Wrapper(Event event) {}
```

The following snippet is **not exhaustive**:

```java
static String classify(Wrapper wrapper) {
    return switch (wrapper) {
        case Wrapper(Created(var id)) -> "Wrapped created " + id;
    };
}
```

`Wrapper` can hold `Cancelled`, `Paid`, or even `event == null`. The pattern `Wrapper(Created(...))` only accepts a subset of `Wrapper` values. A non-`null` `Wrapper` whose `event` component is `null` will **not match** the nested record pattern `Created(...)`.

Fix it by placing the specific pattern first and adding a pattern that accepts all remaining components:

```java
static String classify(Wrapper wrapper) {
    return switch (wrapper) {
        case Wrapper(Created(var id)) -> "Wrapped created " + id;
        case Wrapper(var other) -> "Another wrapper: " + other;
    };
}
```

The pattern `Wrapper(var other)` handles other `Wrapper` instances, including the case where the `event` component is `null`. It does **not** automatically handle a `wrapper == null` selector; to accept that, add a separate `case null`.

When deconstructing multiple levels, check each node that could be `null` or change shape. If business logic needs to know the exact reason data is missing, you can replace a deep pattern with multiple specific cases or keep an intermediate record to inspect.

## 8. Open selector types: need a general branch

If the selector is `Object`, Java cannot infer that only a few application classes exist. The example below is intentionally non-compiling:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "Text: " + s;
        case Integer i -> "Number: " + i;
        // Could still be Boolean, Long, List, or many other types.
    };
}
```

One way to fix it:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "No value";
        case String s -> "Text: " + s;
        case Integer i -> "Number: " + i;
        default -> "Other object";
    };
}
```

`default` resolves any non-`null` value that has not matched earlier patterns; `case null` provides explicit behavior for a `null` input. If you do not need to separate `null`, `default` alone is still enough for the switch to be **type-exhaustive**, though a `null` selector will normally throw `NullPointerException`.

Another option uses a general type pattern:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "Text: " + s;
        case Integer i -> "Number: " + i;
        case Object any -> "Other object: " + any;
    };
}
```

The pattern `Object any` covers any non-`null` object. Do not place it before the `String` or `Integer` patterns: a general pattern placed first will dominate the specific patterns.

## 9. Exhaustive does not mean null-safe

An easy-to-confuse case:

```java
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) -> "Paid";
    };
}
```

This switch is exhaustive for non-`null` `Event` instances, but `describe(null)` will throw `NullPointerException`. `null` is an **absent reference value**, not another `Event` implementation that the compiler forces you to list in the exhaustiveness proof.

If the API allows `null` input, write it explicitly:

```java
static String describe(Event event) {
    return switch (event) {
        case null -> "No event";
        case Created(var id) -> "Created";
        case Cancelled(var id, var reason) -> "Cancelled";
        case Paid(var id, var amount) -> "Paid";
    };
}
```

Both versions are type-exhaustive; only the second version has a branch handling `null`. If the API contract forbids `null`, you can also check at the start of the method with `Objects.requireNonNull(event)` for a clear error, or let the switch throw NPE. Choose a consistent contract for your application.

## 10. Complete, runnable example for Java 21+

The program below combines an enum, sealed interface, record patterns, guards, `case null`, an open selector type, and nested record patterns. Save it to **`ExhaustiveSwitchDemo.java`**.

```java
public class ExhaustiveSwitchDemo {
    enum Stage { NEW, ACTIVE, DONE }

    sealed interface Event permits Created, Cancelled, Paid {}
    record Created(String orderId) implements Event {}
    record Cancelled(String orderId, String reason) implements Event {}
    record Paid(String orderId, int amount) implements Event {}
    record Wrapper(Event event) {}

    // Exhaustive because all three enum constants are listed.
    static String stageName(Stage stage) {
        return switch (stage) {
            case NEW -> "new";
            case ACTIVE -> "active";
            case DONE -> "done";
        };
    }

    // Exhaustive thanks to all permitted subtypes of Event.
    static String describe(Event event) {
        return switch (event) {
            case Created(var id) -> "created:" + id;
            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
            case Paid(var id, var amount) ->
                    "paid:" + id + ":" + amount;
        };
    }

    // Allowing null is a separate API decision.
    static String withNull(Event event) {
        return switch (event) {
            case null -> "missing event";
            case Created(var id) -> "created:" + id;
            case Cancelled(var id, var reason) -> "cancelled:" + id;
            case Paid(var id, var amount) -> "paid:" + amount;
        };
    }

    // Guard only covers amount > 0; a remaining Paid case is needed.
    static String guarded(Event event) {
        return switch (event) {
            case Paid(var id, var amount) when amount > 0 ->
                    "positive:" + amount;
            case Paid(var id, var amount) ->
                    "non-positive:" + amount;
            case Created(var id) -> "created:" + id;
            case Cancelled(var id, var reason) -> "cancelled:" + id;
        };
    }

    // Object is an open type; default handles unlisted types.
    static String inspect(Object value) {
        return switch (value) {
            case String s -> "text:" + s;
            case Integer number -> "int:" + number;
            case null -> "null";
            default -> "other";
        };
    }

    // Specific pattern goes first, broader record pattern goes after.
    static String nested(Wrapper value) {
        return switch (value) {
            case Wrapper(Created(var id)) -> "wrapped-created:" + id;
            case Wrapper(var other) -> "wrapped-other:" + other;
        };
    }

    public static void main(String[] args) {
        System.out.println(stageName(Stage.ACTIVE));
        System.out.println(describe(new Created("A1")));
        System.out.println(describe(new Paid("B2", 500)));
        System.out.println(guarded(new Paid("B2", 500)));
        System.out.println(guarded(new Paid("B2", 0)));
        System.out.println(withNull(null));
        System.out.println(inspect(42));
        System.out.println(nested(new Wrapper(new Created("C3"))));
        System.out.println(nested(new Wrapper(null)));

        try {
            describe(null);
        } catch (NullPointerException e) {
            System.out.println("NPE on null selector");
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 21 -encoding UTF-8 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo
```

Exact output:

```text
active
created:A1
paid:B2:500
positive:500
non-positive:0
missing event
int:42
wrapped-created:C3
wrapped-other:null
NPE on null selector
```

**Reading the output:** `stageName` demonstrates enum coverage; `describe` demonstrates coverage of all records permitted by the sealed interface; `guarded` has branches for both positive and non-positive amounts; `withNull` distinguishes `null` from `Event` types; `inspect` has `default` for an open type; `nested` demonstrates that a deep pattern needs a broader pattern to cover the remaining `Wrapper` shapes. The last line is printed by `catch` after an exhaustive switch encounters a `null` selector without `case null`.

## 11. Debugging workflow for "does not cover all possible input values"

When the compiler flags a switch expression as missing cases, check in order:

1. **Identify the static type of the selector** (the type of the expression inside `switch(...)`): `enum`, `sealed`, `Object`, `String`, a generic type, or an open interface? Do not infer from a few runtime data samples.
2. **If it is an enum:** list all constants. Check for newly added or renamed constants; do not forget cases that have never been executed in tests.
3. **If it is sealed:** inspect the entire permitted hierarchy in the declarations. For branches that are no longer closed, a general case is needed.
4. **If `when` is present:** ask whether the condition can be false. If so, add an unguarded case for the remainder. Do not treat a conditional pattern as equivalent to all values of that type.
5. **If using nested record patterns:** ask whether the inner record could be `null` or of another shape; add a general record pattern or branch level by level.
6. **If the selector is an open type:** add `default` or a type pattern covering the remainder; avoid placing a general case before specific cases.
7. **Handle `null` according to the method contract:** add `case null` if `null` is accepted; recognize that this is separate from fixing type exhaustiveness errors.
8. **Check the switch form:** switch expressions and enhanced switch statements must be exhaustive; traditional switch statements have backward-compatibility rules.
9. **Read errors other than exhaustiveness:** a branch might be shadowed (*dominated case*), a pattern variable might be out of scope, a guard might have the wrong type, or branch return types might be incompatible. Adding `default` will not fix these independent errors.

For the same compile error, the right fix may be adding a specific case, adding a branch for when a guard fails, or using a general branch. **Do not automatically add `default` to every switch** if the goal of the model is to force developers to handle every state when the business domain type is extended.

## 12. Self-check exercises

**Exercise 1 — Adding a state to an enum.** `enum Stage { NEW, ACTIVE, DONE }` and a switch expression lists all three constants. If `PAUSED` is added and recompiled without updating the switch, what happens? **Answer:** the switch is no longer exhaustive and the compiler reports missing cases if no branch covers `PAUSED`.

**Exercise 2 — Insufficient guard.** Given `Paid(int amount)`, why does `case Paid(var amount) when amount > 0` not cover `Paid`? **Answer:** `amount == 0` and `amount < 0` still remain. Add an unguarded `case Paid(var amount)` or a set of branches proven to cover everything.

**Exercise 3 — Null and exhaustiveness.** A switch on a sealed `Event` has all three cases but receives `null`. Is this a missing-case error at compile time? **Answer:** no; the compiler proves exhaustiveness for `Event` instances, while `null` without `case null` will result in `NullPointerException`.

**Exercise 4 — Nested record trap.** Does `Wrapper(Created(...))` handle all `Wrapper` values? **Answer:** no. The `event` component can be `Cancelled`, `Paid`, or `null`. You can add `Wrapper(var other)` afterward to cover the remainder.

**Exercise 5 — When to use default?** For a switch on a sealed `Event` with a closed set of records, what should you prefer when you want the compiler to remind you when a new event type is added? **Answer:** list the subtypes explicitly, avoiding `default` just to bypass the error. When the selector is `Object` and the intent is to handle any arbitrary object, `default` or a general pattern is the appropriate choice.

**Exercise 6 — Statement or expression?** Why can the traditional statement `switch(stage) { case NEW -> ...; }` compile while `return switch(stage) { case NEW -> ...; };` cannot? **Answer:** traditional statements retain the ability to be non-exhaustive for backward compatibility; expressions are required to cover every enum value.

## 13. Takeaways

- **Exhaustive** means the compiler proves the switch has an applicable branch for every possibility of the selector type (with `null` handling being a separate concern).
- **Enum:** list all constants or use a general branch.
- **Sealed:** cover all relevant subtypes; adding a new type can make old code fail with missing cases upon recompilation.
- **`when`:** a guard that can be false does not provide full-type coverage.
- **Record patterns:** deeply nested patterns can fail to match when an inner record is `null` or has the wrong shape; handle those cases if they can occur.
- **Open types:** `default` or a general pattern covers the remainder.
- **`case null`:** provides explicit behavior when the selector is `null`, independent of type exhaustiveness.

**Official documentation:** [Java Language Specification 21 — Exhaustive Switch Blocks (`14.11.1.1`)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1), [JLS 21 — switch expressions (`15.28`)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
