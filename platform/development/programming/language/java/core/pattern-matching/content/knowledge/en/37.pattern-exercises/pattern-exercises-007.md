# Making `switch` Exhaustive in Java 21+: Comprehensive Practice

## 1. Lesson Objectives

When Java selects a branch using `switch`, the key question is: **is there a valid path for every value allowed by the selector type?** If not, the program may miss a subtype, an enum constant, or a case where a guard does not match.

**Exhaustiveness** means that the `case` labels are sufficient to handle all cases required by Java's **compile-time checking** rules. For a `switch expression`, this requirement is especially important because the expression must produce a result when it completes normally.

Java 21 officially supports:

- **Type patterns:** `case String s -> ...`.
- **Record patterns:** `case Create(var id) -> ...`; multiple components can be deconstructed in the same pattern.
- **Guarded patterns:** `case Create(var id) when id.isBlank() -> ...`.
- **Sealed hierarchy:** the compiler knows the set of permitted direct subtypes.
- **`case null`:** handles a null selector when the contract allows it.

**Expected outcomes:** after this lesson, you will be able to fix a non-exhaustive `switch`, avoid using `default` to mask missing cases on a sealed hierarchy, handle true/false guards, combine nested record patterns, and distinguish **compile-time exhaustiveness** from **runtime safety** when encountering null or mismatched data.

> Scope: Java 21 and later. `Pattern Matching for switch` (JEP 441) and `Record Patterns` (JEP 440) are standard features in Java 21; `--enable-preview` is not required.

## 2. Why Does the Compiler Require Exhaustiveness?

Example of an incomplete `switch expression`:

~~~java
static String label(Object value) {
    return switch (value) {
        case String s -> "String: " + s;
    };
}
~~~

The snippet above **does not compile** because `value` has static type `Object`: besides `String`, the value could be `Integer`, `Long`, any other object, or null. The compiler cannot prove that the switch will always produce a valid result.

A common diagnostic:

~~~text
error: the switch expression does not cover all possible input values
~~~

Fix it with a fallback case for other non-null values, while also deciding on the null policy:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "String: " + s;
        default -> "Kiểu khác";
    };
}
~~~

Now every value has a branch:

- `null` → `"NULL"`.
- Non-null String → `case String s`.
- Other objects → `default`.

**Important distinction:** `default` helps cover the remaining cases for exhaustiveness, but it **does not automatically catch a null selector**. Without `case null`, a `switch` on a reference selector can still throw `NullPointerException` at runtime, even if it compiles successfully and has `default`.

## 3. Choosing a Strategy Based on the Selector's Static Type

How you make a switch exhaustive depends on the **type of the selector expression**, not just the kinds of objects that appear in a single run.

| Selector type | Common way to achieve exhaustiveness | Points to note |
| --- | --- | --- |
| `Object` or open interface | `default` or a type pattern covering the remaining non-null cases | `null` has its own policy |
| `enum` | List all enum constants or use `default` | Listing all constants helps the compiler detect new enum constants |
| `sealed interface` | Cover every permitted subtype, avoiding `default` when appropriate | When a subtype is added, the switch can fail to compile as a reminder to update it |
| Record type | Have a covering record pattern, or a general type pattern for that record | Nested patterns may fail to match because of a null component |
| `String` type | Cover all String values with appropriate cases or `default` | Cases like `case "A"`, `case "B"` do not cover all Strings |
| Primitive `int` type | Specific constants together with `default` when all numbers cannot be covered by listing | `int` is non-null; boxed `Integer` can be null |

You should not use `default` out of habit for every type. On a **sealed hierarchy**, the major advantage of listing all subtypes is that the compiler reports when the domain model changes; an overly broad `default` can lose this signal.

## 4. Step 1 — Starting with a Sealed Hierarchy

Consider a hypothetical system with three action types:

~~~java
sealed interface Action permits Create, Adjust, Relocate {}

record Create(String id) implements Action {}
record Adjust(int delta) implements Action {}

record Point(int x, int y) {}
record Relocate(Point destination) implements Action {}
~~~

The three records `Create`, `Adjust`, and `Relocate` are the only permitted direct subtypes of `Action`. Records are inherently `final`, so no further subtypes can arise from them.

A **non-exhaustive** switch:

~~~java
static String describe(Action action) {
    return switch (action) {
        case Create(var id) -> "CREATE:" + id;
        case Adjust(var delta) -> "ADJUST:" + delta;
    };
}
~~~

The compiler may report:

~~~text
the switch expression does not cover all possible input values
~~~

Because `Relocate` is a valid subtype without a branch. The compiler does not care that the demo program has never instantiated `Relocate`. It looks at the **static type `Action` and the set of subtypes that can occur**.

**Proper fix:**

~~~java
static String describe(Action action) {
    return switch (action) {
        case Create(var id) -> "CREATE:" + id;
        case Adjust(var delta) -> "ADJUST:" + delta;
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

This switch now handles all three subtypes of `Action`. There is no need to add `default` just to silence the compiler. However, a **null selector** still needs its own policy if the method allows null; we will examine that in step 3.

## 5. Step 2 — A `when` Guard Does Not Replace a Covering Branch

Suppose we want to classify `Create` commands with a blank ID separately:

~~~java
// INTENTIONALLY NON-EXHAUSTIVE:
static String describe(Action action) {
    return switch (action) {
        case Create(var id) when id != null && !id.isBlank() ->
            "CREATE:" + id;
        case Adjust(var delta) -> "ADJUST:" + delta;
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

Even though there is a `case Create(...)`, it **is only selected when the guard is true**. For example, `new Create(null)` or `new Create("   ")` is still a `Create` instance, but the guard is false, so it does not match that case. Therefore, a **data-dependent guard** does not cover the entire subtype.

**Fix with an unguarded Create branch:**

~~~java
static String describe(Action action) {
    return switch (action) {
        case Create(var id) when id == null || id.isBlank() ->
            "CREATE_INVALID";
        case Create(var id) ->
            "CREATE:" + id;
        case Adjust(var delta) ->
            "ADJUST:" + delta;
        case Relocate(var destination) ->
            "RELOCATE";
    };
}
~~~

Now there are two paths for `Create`:

1. Guard is true → `CREATE_INVALID`.
2. Guard is false → general `Create` case → `CREATE:<id>`.

**Order matters:** the specific guarded branch comes before the unguarded branch. If you place the general `case Create(var id)` first, the `Create ... when ...` branch after it can be reported by the compiler as a **dominated case label**.

Similarly for `Adjust`:

~~~java
case Adjust(var delta) when delta == 0 -> "NO_CHANGE";
case Adjust(var delta) -> "ADJUST:" + delta;
~~~

The true guard only handles delta equal to 0; the unguarded branch is still needed to cover non-zero deltas.

**Note:** if the record constructor actively forbids null/blank IDs, some invalid branches might not occur at runtime with valid objects. Still, you should not rely on invariants outside the type system as an arbitrary substitute for compiler exhaustiveness; write the switch according to the data contract and avoid redundant cases when truly unnecessary.

## 6. Step 3 — Handling a Null Selector Intentionally

On a reference selector:

~~~java
static String typeOf(Action action) {
    return switch (action) {
        case Create(var id) -> "CREATE";
        case Adjust(var delta) -> "ADJUST";
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

The switch above **compiles successfully** because it covers all subtypes of `Action`. But:

~~~java
typeOf(null); // Runtime: NullPointerException
~~~

Do not conclude that "exhaustive means no more runtime exceptions." Compile-time exhaustiveness and null policy are **two separate concerns**.

### Policy A — null is an allowed state

~~~java
static String typeOf(Action action) {
    return switch (action) {
        case null -> "NULL_ACTION";
        case Create(var id) -> "CREATE";
        case Adjust(var delta) -> "ADJUST";
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

### Policy B — null is an API contract violation

~~~java
static String typeOf(Action action) {
    java.util.Objects.requireNonNull(action, "action");
    return switch (action) {
        case Create(var id) -> "CREATE";
        case Adjust(var delta) -> "ADJUST";
        case Relocate(var destination) -> "RELOCATE";
    };
}
~~~

`requireNonNull` throws an NPE with an intentional message right at the precondition. You can choose a different domain/application exception if null is invalid input that requires a business-level response.

**Avoid this misconception:** `default` does not replace `case null`. Even `case Object obj`, which is a very broad type pattern, does not handle a null selector when there is no `case null` label.

When you need to combine null and the remaining types in a switch on `Object`, Java 21 allows:

~~~java
static String onlyText(Object value) {
    return switch (value) {
        case String s -> s;
        case null, default -> "Không phải text hoặc null";
    };
}
~~~

Only combine them like this if null and other types **truly** have the same meaning. Use two separate branches when the domain needs to distinguish them.

## 7. Step 4 — Nested Record Patterns and the Difference Between Compile-Time Exhaustiveness and Runtime

Consider `Relocate` with component `Point destination`:

~~~java
record Point(int x, int y) {}
record Relocate(Point destination) implements Action {}
~~~

Suppose we want to extract the coordinates directly:

~~~java
case Relocate(Point(var x, var y)) ->
    "MOVE:" + x + "," + y;
~~~

However, an instance `new Relocate(null)` is still syntactically valid if the constructor does not reject null. In that case:

- The outer selector is a **non-null** `Relocate`.
- The `destination` component is null.
- The nested record pattern `Point(var x, var y)` **does not match null**.
- If there is no other matching case, the switch can encounter an unmatched situation at runtime.

### A Little-Known Trap: `MatchException`

Java 21 may **consider a nested record pattern exhaustive for type checking**, yet at runtime a null component still causes all such patterns not to match:

~~~java
record Point(int x) {}
sealed interface Target permits Move {}
record Move(Point point) implements Target {}

static String risky(Target value) {
    return switch (value) {
        case Move(Point(var x)) -> "X:" + x;
    };
}
~~~

The snippet above is accepted by the compiler as an exhaustive switch in Java 21, but:

~~~java
risky(new Move(null)); // Runtime: java.lang.MatchException
~~~

Reason: `Move(Point(var x))` does not match when the `point` component is null, even though the pattern is considered sufficient in structural exhaustiveness analysis. This illustrates the boundary between **syntactic/type exhaustiveness** and **runtime totality**. The Java 21 API documentation for `java.lang.MatchException` specifically mentions nested record patterns and null.

**Fix for real-world data:**

~~~java
static String safe(Target value) {
    return switch (value) {
        case null -> "NO_TARGET_ACTION";
        case Move(Point(var x)) -> "X:" + x;
        case Move(var point) -> "MISSING_POINT";
    };
}
~~~

`case Move(var point)` is a **general record pattern** placed after the nested branch; it can accept a null component reference, so it handles `new Move(null)`. `case null` handles a null selector separately.

**Alternative:** if the domain forbids a null Point, validate it immediately in the compact constructor of `Move` with `Objects.requireNonNull(point, "point")`. Then every validly constructed `Move` will have a Point; however, untrusted data, serializers, reflection, or binary schema changes still need to be considered in context.

**Review point:** do not just ask "does the compiler report it as exhaustive?", also ask "are nullable nested components handled by a general case or a reliable invariant?". Never conflate a null selector with a null component.

## 8. Step 5 — Exhaustive Enum Without `default`

Suppose:

~~~java
enum Traffic { RED, YELLOW, GREEN }
~~~

A complete switch expression:

~~~java
static String traffic(Traffic signal) {
    return switch (signal) {
        case RED -> "STOP";
        case YELLOW -> "CAUTION";
        case GREEN -> "GO";
    };
}
~~~

This is an approach **without `default`** because the compiler knows the currently declared enum constants. If `BLUE` is later added to `Traffic` and the source is recompiled, the compiler can flag the switch as missing a case so you can intentionally decide the new behavior.

If only `RED` and `GREEN` are present, omitting `YELLOW`:

~~~java
// INTENTIONALLY NON-EXHAUSTIVE:
return switch (signal) {
    case RED -> "STOP";
    case GREEN -> "GO";
};
~~~

Compile-time error because the switch expression does not cover all existing constants.

**Null is still separate:** `traffic(null)` throws `NullPointerException` if there is no `case null`, even though the enum switch lists all constants. You can add a null label if business logic allows it, or reject the input with a precondition.

**Compatibility when an enum changes:** as with sealed hierarchies, when classes are compiled separately or an enum changes between compile time and runtime, a switch considered exhaustive may encounter a value outside the known cases and throw `MatchException`. That is a binary compatibility concern to keep in mind, not a reason to unconditionally add `default` to every switch.

## 9. Step 6 — `Object` or Open Interface: Where `default` Has a Legitimate Role

With a selector of type `Object`, the compiler does not have a closed list of subtypes like `sealed Action`. You can write:

~~~java
static String classifyObject(Object value) {
    return switch (value) {
        case null -> "ANY_NULL";
        case Action action -> classify(action);
        case String text -> "TEXT:" + text;
        default -> "OTHER";
    };
}
~~~

In this example:

- `Action action` is a type pattern; for objects that are subtypes of `Action`, we delegate to a specialized `classify` switch.
- `String text` catches strings.
- `default` catches the remaining non-null objects.

**An option without `default`** is a final general type pattern:

~~~java
static String classifyAny(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "TEXT:" + text;
        case Object other -> "OBJECT:" + other.getClass().getSimpleName();
    };
}
~~~

`case Object other` covers the remaining non-null reference objects; `case null` handles null. If you put `case Object other` at the top, the more specific type patterns after it can be reported as **dominated**.

Choosing between `default` and a general type pattern depends on whether you need a **bound variable** of the supertype in the branch. Neither option inherently has better performance.

## 10. `switch expression`, `switch statement`, and "Enhanced" Cases

Two common forms of `switch`:

### `switch expression` — returns a value

~~~java
String text = switch (action) {
    case Create(var id) -> "CREATE";
    case Adjust(var delta) -> "ADJUST";
    case Relocate(var point) -> "RELOCATE";
};
~~~

A switch expression always needs to be exhaustive according to language rules; a block branch that returns a value uses `yield`:

~~~java
String text = switch (action) {
    case Create(var id) -> {
        String normalized = id == null ? "?" : id.strip();
        yield "CREATE:" + normalized;
    }
    case Adjust(var delta) -> "ADJUST:" + delta;
    case Relocate(var point) -> "RELOCATE";
};
~~~

### `switch statement` — performs an action

Since Java 21, an **enhanced switch statement** (for example, one with pattern labels or null) **must also be exhaustive**:

~~~java
static void printAction(Object action) {
    switch (action) {
        case null -> System.out.println("NULL");
        case String text -> System.out.println(text);
        default -> System.out.println("OTHER");
    }
}
~~~

Removing `default` in the switch statement above makes an enhanced switch statement with an `Object` selector and only String/null cases non-exhaustive.

**Distinction from a legacy switch statement:** a traditional switch statement on enum/int/String, without patterns or `case null` and not in enhanced form, can still be non-exhaustive for backward compatibility with older Java:

~~~java
enum Traffic { RED, YELLOW, GREEN }

static void printLegacy(Traffic signal) {
    switch (signal) {
        case RED -> System.out.println("STOP");
        case GREEN -> System.out.println("GO");
        // No YELLOW: a traditional switch statement
        // can still be accepted by the compiler.
    }
}
~~~

Do not infer from the permissiveness of a **legacy statement** that any **switch expression** or **enhanced statement** may also omit cases. See JLS Java 21 `14.11 to determine which cases require exhaustiveness.

## 11. Complete Java 21+ Practice Program

The following code combines these techniques: sealed hierarchy, record patterns, `when` with an unguarded fallback, nested record pattern, `case null`, exhaustive enum, and an `Object` selector with `default`.

Save to **`ExhaustiveSwitchPracticeDemo.java`**:

~~~java
public class ExhaustiveSwitchPracticeDemo {
    sealed interface Action permits Create, Adjust, Relocate {}

    record Create(String id) implements Action {}
    record Adjust(int delta) implements Action {}
    record Point(int x, int y) {}
    record Relocate(Point destination) implements Action {}

    enum Traffic { RED, YELLOW, GREEN }

    static String classify(Action action) {
        return switch (action) {
            case null -> "NULL_ACTION";

            case Create(var id) when id == null || id.isBlank() ->
                "CREATE_INVALID";

            case Create(var id) ->
                "CREATE:" + id;

            case Adjust(var delta) when delta == 0 ->
                "NO_CHANGE";

            case Adjust(var delta) ->
                "ADJUST:" + delta;

            case Relocate(Point(var x, var y)) when x == y ->
                "MOVE_DIAGONAL:" + x;

            case Relocate(Point(var x, var y)) ->
                "MOVE:" + x + "," + y;

            case Relocate(var destination) ->
                "MOVE_MISSING";
        };
    }

    static String traffic(Traffic signal) {
        return switch (signal) {
            case RED -> "STOP";
            case YELLOW -> "CAUTION";
            case GREEN -> "GO";
        };
    }

    static String classifyObject(Object value) {
        return switch (value) {
            case null -> "ANY_NULL";
            case Action action -> classify(action);
            case String text -> "TEXT:" + text;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify(new Create(null)));
        System.out.println(classify(new Create("   ")));
        System.out.println(classify(new Create("REQ-1")));
        System.out.println(classify(new Adjust(0)));
        System.out.println(classify(new Adjust(-2)));
        System.out.println(classify(
                new Relocate(new Point(3, 3))));
        System.out.println(classify(
                new Relocate(new Point(1, 4))));
        System.out.println(classify(new Relocate(null)));

        System.out.println(traffic(Traffic.RED));
        System.out.println(traffic(Traffic.YELLOW));
        System.out.println(traffic(Traffic.GREEN));

        System.out.println(classifyObject(
                new Create("REQ-2")));
        System.out.println(classifyObject("hello"));
        System.out.println(classifyObject(5));
        System.out.println(classifyObject(null));

        try {
            traffic(null);
        } catch (NullPointerException e) {
            System.out.println("TRAFFIC_NULL_NPE");
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 21 -encoding UTF-8 ExhaustiveSwitchPracticeDemo.java
java ExhaustiveSwitchPracticeDemo
~~~

**Exact stdout:**

~~~text
NULL_ACTION
CREATE_INVALID
CREATE_INVALID
CREATE:REQ-1
NO_CHANGE
ADJUST:-2
MOVE_DIAGONAL:3
MOVE:1,4
MOVE_MISSING
STOP
CAUTION
GO
CREATE:REQ-2
TEXT:hello
OTHER
ANY_NULL
TRAFFIC_NULL_NPE
~~~

### 11.1. Why Is This Program Exhaustive?

- `Action` has three permitted subtypes: `Create`, `Adjust`, and `Relocate`.
- The **unguarded** patterns `Create(var id)`, `Adjust(var delta)`, and `Relocate(var destination)` ensure there is always a branch for each non-null subtype.
- Cases with `when` **precede** the fallback of the same subtype; both true and false guards lead to a branch with a result.
- For `Relocate`, nested `Point(...)` matches a valid destination; fallback `Relocate(var destination)` handles a null component.
- `case null` handles a null `Action` selector according to the demo's contract.
- `Traffic` lists all three constants; even so, a null enum selector still throws NPE because `traffic` has no `case null`.
- `classifyObject` appropriately has `default` because the selector is `Object` and is not restricted to a closed hierarchy.

### 11.2. Why Not Add `default` to `classify`?

Because the `Action` hierarchy is closed and every subtype is listed. If `record Cancel(...) implements Action` is added later, having the compiler require updating `classify` is a **useful signal**, preventing a new action type from silently receiving a generic result like `"OTHER"`.

### 11.3. Why Does the Demo Allow a Null ID or Point?

To illustrate handling guards and nested fallbacks. A real domain model might use compact constructors:

~~~java
record Create(String id) implements Action {
    public Create {
        if (id == null || id.isBlank())
            throw new IllegalArgumentException("id rỗng");
        id = id.strip();
    }
}

record Relocate(Point destination) implements Action {
    public Relocate {
        java.util.Objects.requireNonNull(destination, "destination");
    }
}
~~~

These are **replacement** declarations for the corresponding records in the example; do not paste them into the same file as the existing `Create`/`Relocate` declarations because of duplicate names.

When constructors enforce invariants, many null inputs are rejected early. Still, you should understand both the compiler's exhaustiveness rules and runtime matching rules to design proper code reviews and tests.

## 12. Workflow for Fixing a Non-Exhaustive Switch

When you get the error:

~~~text
the switch expression does not cover all possible input values
~~~

Do not immediately insert `default -> null`. Work through it in order:

1. **Identify the selector type**: is it an enum, sealed interface, Object, or open interface?
2. **List the permitted cases**: enum constants or permitted subtypes; for Object, determine the general fallback branch.
3. **Inspect each case with `when`**: a true guard is not enough; is there an unguarded case or a sequence of cases that completely covers the false-guard case?
4. **Check nested record patterns**: can a null component or another nested type cause the pattern not to match?
5. **Decide the null selector policy**: `case null` or reject null at the boundary?
6. **Place specialized cases before general cases** to avoid dominance.
7. **Recompile** with the right language level, e.g. `javac --release 21`.
8. **Write tests for every execution path**: do not just verify that the compiler stops reporting errors.

Step-by-step fix examples:

~~~text
Broken A: missing Relocate
  -> add case Relocate(...)

Broken B: has Create when ..., no plain Create
  -> add unguarded case Create(...)

Broken C: only has Relocate(Point(...))
  -> add Relocate(var destination) if the component can be null

Broken D: default satisfies compilation, but null selector causes NPE
  -> add case null or reject null early

Broken E: general case placed before guarded case
  -> move the specialized case first
~~~

**Read the diagnostic accurately:** record pattern arity/type errors, dominance errors, and non-exhaustive errors are **distinct compile-time errors**. There is no single "add default" fix that applies to all of them.

## 13. Why Can `default -> null` or `default -> ""` Be Harmful?

A statement like:

~~~java
return switch (action) {
    case Create(var id) -> "CREATE";
    case Adjust(var delta) -> "ADJUST";
    default -> "";
};
~~~

looks easy to compile, but if `action` is `Relocate`, the caller receives an empty string without knowing there is an **unhandled** action type. If the system needs to report errors for unsupported cases, returning an empty string can also corrupt logs, metrics, or APIs.

More intentional options:

- **Closed sealed hierarchy:** list every subtype and leverage compiler exhaustiveness; avoid `default` if unnecessary.
- **Open type:** if other types cannot be handled, use `default -> throw new IllegalArgumentException("Unsupported action")` or an appropriate domain error type; avoid fake success responses.
- **Input with a type discriminator from JSON:** perform mapping/validation at the boundary before constructing subtypes, without losing information about unknown payload types.
- **Truly wanting a fallback:** define the fallback behavior in the contract and test with an object of an unhandled type.

Remember that `default` on a reference switch **does not catch null**; if you want a shared policy for null and the rest, use `case null, default -> ...` when Java 21 allows it and the contract truly treats them as equivalent.

## 14. Test Matrix: What Does the Compiler Guarantee vs. What Needs Runtime Testing?

| ID | Input | Expected path | Meaning |
| --- | --- | --- | --- |
| T1 | `null` passed to `classify` | `NULL_ACTION` | Null selector case |
| T2 | `Create(null)` | `CREATE_INVALID` | Guard true due to left side `id == null` |
| T3 | `Create("   ")` | `CREATE_INVALID` | Guard true due to `id.isBlank()` |
| T4 | `Create("REQ-1")` | `CREATE:REQ-1` | Guard false, Create fallback |
| T5 | `Adjust(0)` | `NO_CHANGE` | Adjust guard true |
| T6 | `Adjust(-2)` | `ADJUST:-2` | Adjust guard false |
| T7 | `Relocate(Point(3,3))` | `MOVE_DIAGONAL:3` | Nested record + guard true |
| T8 | `Relocate(Point(1,4))` | `MOVE:1,4` | Nested record + guard false |
| T9 | `Relocate(null)` | `MOVE_MISSING` | Nested pattern does not match, fallback receives null component |
| T10 | `Traffic.RED/YELLOW/GREEN` | STOP/CAUTION/GO | Enum constants covered |
| T11 | `Traffic` null selector | NPE per demo | Exhaustive does not mean null-safe |
| T12 | `Object` receives `Create("REQ-2")` | `CREATE:REQ-2` | Type pattern Action |
| T13 | `Object` receives String | `TEXT:hello` | Type pattern String |
| T14 | `Object` receives Integer | `OTHER` | Default |
| T15 | `Object` null selector | `ANY_NULL` | Null case in Object switch |

This matrix is **behavioral testing**, not JaCoCo branch coverage percentage. For guarded patterns, you must test both true and false conditions, especially when guards contain `&&` or `||`. Do not just count hitting each `case` label once and conclude every path is tested.

## 15. JUnit 5: Verifying Solution Correctness

The example can be turned into unit tests. The file below assumes the demo class is in the same package and the project already has the JUnit 5 dependency; this is **not a standalone Java program that can be run with `javac` alone without the JUnit classpath**.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ExhaustiveSwitchPracticeDemoTest {
    @Test
    void handlesNullAndCreateGuard() {
        assertEquals("NULL_ACTION",
                ExhaustiveSwitchPracticeDemo.classify(null));
        assertEquals("CREATE_INVALID",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Create(" ")));
        assertEquals("CREATE:REQ-1",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Create("REQ-1")));
    }

    @Test
    void handlesRelocateWithNullComponent() {
        assertEquals("MOVE_DIAGONAL:3",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Relocate(
                                new ExhaustiveSwitchPracticeDemo.Point(3, 3))));
        assertEquals("MOVE_MISSING",
                ExhaustiveSwitchPracticeDemo.classify(
                        new ExhaustiveSwitchPracticeDemo.Relocate(null)));
    }

    @Test
    void checksAllEnumConstantsAndNullPolicy() {
        for (var traffic : ExhaustiveSwitchPracticeDemo.Traffic.values()) {
            assertNotNull(ExhaustiveSwitchPracticeDemo.traffic(traffic));
        }
        assertThrows(NullPointerException.class,
                () -> ExhaustiveSwitchPracticeDemo.traffic(null));
    }
}
~~~

One test uses `Traffic.values()` to iterate over existing constants, but for critical domains you should still assert the **exact** value (STOP/CAUTION/GO), not just `assertNotNull`. If the contract changes, tests should reflect business rules, not merely ensure the code returns a string.

Test on the project's baseline JDK. When code uses Java 21 patterns, compile/tests must run with a compiler supporting `--release 21`; do not add `--enable-preview` for standard Java 21 record/switch patterns.

## 16. Common Mistakes When Making `switch` Exhaustive

| Mistake/Misconception | Cause | Fix |
| --- | --- | --- |
| Only having cases for some sealed subtypes | Compiler sees missing subtype | Add a case for that subtype |
| Having `when` without an unguarded fallback | False guard leaves a coverage gap | Add a general case for the same subtype |
| Placing a general case before a guarded case | Later branch is dominated | Order specific cases first |
| Using only a nested record pattern | Nullable component may fail to match even if compiler considers it exhaustive | Check invariants or add a record fallback |
| Seeing compilation succeed and assuming no exceptions | Null selector or `MatchException` can still occur | Test runtime, null/nested coverage |
| Assuming `default` catches null | Java handles null selectors separately | `case null` or reject null early |
| Always adding `default` to sealed switches | Hides newly added subtypes | Prefer listing subtypes completely |
| Using `case Object o` followed by smaller type patterns | Specific type patterns are dominated | Put the broad pattern last |
| Using a switch expression missing an enum constant | Not compile-time exhaustive | List all constants |
| Assuming every switch statement must be exhaustive | Legacy statements differ from enhanced statements | Distinguish per JLS Java 21 |
| Adding a case to compile but returning `null` for unsupported subtypes | Masks business bugs | Return a clear error or implement behavior |
| Equating case label count with branch coverage | C1 is bytecode-based; guards have multiple paths | Use a test matrix and coverage report |
| Not recompiling after adding a subtype/enum constant | Old binaries can encounter new values | Rebuild/redeploy together, run integration tests |

## 17. Practice Exercises by Level

### Exercise 1 — Find the Missing Subtype

~~~java
sealed interface Request permits CreateUser, DeleteUser, UpdateUser {}
record CreateUser(String id) implements Request {}
record DeleteUser(String id) implements Request {}
record UpdateUser(String id) implements Request {}

static String route(Request request) {
    return switch (request) {
        case CreateUser(var id) -> "CREATE";
        case DeleteUser(var id) -> "DELETE";
    };
}
~~~

Fix the switch so it is exhaustive **without using `default`**. If `record LockUser(...) implements Request` is added, what changes are needed in `permits` and the switch?

### Exercise 2 — True/False Guard

~~~java
case CreateUser(var id) when id != null && !id.isBlank() ->
    "CREATE:" + id;
~~~

Why is this branch alone not enough to cover every `CreateUser`? Add a branch to handle null or blank IDs and test at least two paths.

### Exercise 3 — Null Nested Record

~~~java
record Point(int x) {}
sealed interface Task permits Move {}
record Move(Point point) implements Task {}

return switch (task) {
    case Move(Point(var x)) -> "X:" + x;
};
~~~

Can the compiler accept the snippet above as exhaustive? When `new Move(null)` is passed, what can happen? Write a version that avoids `MatchException` using a fallback.

### Exercise 4 — Enum and Null

~~~java
enum Stage { NEW, ACTIVE, CLOSED }
~~~

Write a switch expression without `default` returning labels for all three constants. Try passing null: does the compiler protect against it automatically? Add null handling according to two different policies (allowing null and forbidding null).

### Exercise 5 — Enhanced Statement

With a selector of type `Object`, write a switch **statement** with only `case String s -> ...`. Why might Java 21 reject compiling it? Fix it to become an exhaustive enhanced switch statement while still not confusing `default` with null.

### Exercise 6 — Reviewing a Dangerous Default

A PR contains:

~~~java
return switch (request) {
    case CreateUser(var id) -> "OK";
    default -> "OK";
};
~~~

Explain why the code compiles yet does not guarantee that `DeleteUser`/`UpdateUser` are handled properly. Propose a way to handle it so the compiler reminds you when the hierarchy is extended.

### Answer Hints

~~~java
// Exercise 1: add the missing branch:
case UpdateUser(var id) -> "UPDATE";

// Exercise 2: specific branch first, covering branch second:
case CreateUser(var id) when id == null || id.isBlank() ->
    "INVALID_CREATE";
case CreateUser(var id) -> "CREATE:" + id;

// Exercise 3: nested first, fallback second:
case Move(Point(var x)) -> "X:" + x;
case Move(var point) -> "NO_POINT";

// Exercise 4:
return switch (stage) {
    case null -> "UNKNOWN";
    case NEW -> "Mới";
    case ACTIVE -> "Hoạt động";
    case CLOSED -> "Đã đóng";
};
~~~

The code fragments in the answer hints are **switch labels or switch body fragments**, not standalone top-level programs; place them into an appropriate method/class context to test with the compiler.

**Exercise 5:** an enhanced switch statement with pattern/null requires exhaustiveness; add `default` or a covering type pattern, and `case null` if you want to accept null validly. **Exercise 6:** remove `default -> "OK"`, handle each permitted subtype with its own case, and write tests for each behavior.

## 18. Pre-Merge Checklist

- [ ] Identified the **selector's static type** and possible subtypes/enum constants.
- [ ] `switch expression` and enhanced statement satisfy compiler exhaustiveness.
- [ ] Subtypes of a sealed hierarchy have explicit cases; `default` is not used to hide new subtypes unnecessarily.
- [ ] Patterns with `when` have a path handling **false** guard values.
- [ ] Specialized cases precede general cases; there is no dominance.
- [ ] Nullable nested record components are validated or have an appropriate fallback.
- [ ] `case null` or a non-null precondition expresses the selector policy.
- [ ] `default` is used properly when the selector is open/broad or a fallback is genuinely meaningful.
- [ ] Test cases exist for every business branch, true/false guards, null selector, null component, and other types.
- [ ] Compile-time exhaustiveness is not treated as a guarantee against runtime `MatchException`/NPE.
- [ ] Code is compiled and tested on the agreed JDK/source release; stdout, exceptions, and invariants are verified.
- [ ] Adding a new enum constant/subtype is accompanied by tests and updates to corresponding handlers.

## 19. Summary

**"Making switch exhaustive"** is not just adding `default` to get past the compiler:

1. For **enums** or **sealed hierarchies**, prefer covering **every constant/subtype** to preserve compile-time checking as the model evolves.
2. For **`when` guards**, remember that data-dependent guards can be false, so you need an unguarded branch or a combination of cases that truly covers everything.
3. For **nested record patterns**, consider null components and `MatchException` even when the compiler already accepts exhaustiveness.
4. For **null reference selectors**, explicitly choose `case null` or a rejecting precondition; `default` does not automatically catch null.
5. For **open selectors** like `Object`, `default` or a broad type pattern has a legitimate place.
6. Verify with **`javac` + test matrix + runtime assertions**, not just by counting cases.

### References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): exhaustive switch, patterns, guarded patterns, dominance, and null (Java 21).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): nested deconstruction and matching.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): permitted subtypes and closed models.
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JLS Java SE 21 `14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): enhanced statements and exhaustiveness.
- [JLS Java SE 21 `15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): rules for switch expressions.
- [Java SE 21 API — `MatchException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): runtime non-matching scenarios even when structurally exhaustive, including nullable nested record patterns.
