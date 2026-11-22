# Record Pattern Dominated by Another Pattern (Dominance) in Java 21+

## 1. Understanding "Dominance" in a Pattern Switch

When using a **record pattern** in a `switch`, a branch can become **unreachable** if a preceding branch already covers all values that the later branch could match. Java calls this relationship **dominance**: a case label *dominated* by a preceding case label causes a **compile-time error**, rather than silently becoming dead code.

Java 21 example:

```java
record Point(int x, int y) {}

static String invalid(Object value) {
    return switch (value) {
        case Point point -> "some point";
        case Point(int x, int y) -> "point components"; // Error: dominated
        default -> "other";
    };
}
```

In the example above, `case Point point` is a **type pattern** that matches every non-`null` `Point` object. `case Point(int x, int y)` is a **record pattern**, which can also only match a `Point` object. Every object that could reach the record pattern branch has already been handled by the first branch, so the compiler rejects the later branch with an error along the lines of **“this case label is dominated by a preceding case label”**.

Key topics in this article:

- A record pattern can be dominated by a **broader type pattern** or by **another record pattern with wider component patterns**.
- Dominance also considers the **nested structure** of record patterns.
- `when` guards affect whether a preceding branch is guaranteed to cover a following branch.
- Selector `null` and record component `null` must be considered separately.
- Knowing the rules helps order branches from **specific** to **general** without losing clarity.

**Version:** Record patterns were standardized in **Java 21 (JEP 440)**; pattern matching for switch was standardized in **Java 21 (JEP 441)**. All examples use stable JDK 21+ syntax, without needing `--enable-preview`.

## 2. What Is a Record Pattern and What Can It Match?

A record pattern both checks the record type and deconstructs (extracts) its components to match their corresponding patterns.

```java
record Parcel(Object value) {}

Object input = new Parcel("Java");

String description = switch (input) {
    case Parcel(String text) -> "text:" + text;
    case Parcel(var other) -> "other:" + other;
    default -> "not a Parcel";
};
```

`Parcel(String text)` matches only when the selector is a `Parcel` and the `value` component matches the pattern `String text`. `Parcel(var other)` is broader: it matches the remaining `Parcel` instances and infers `other` to be of type `Object` from the `Parcel.value()` component.

With `new Parcel("Java")`, the result is `"text:Java"`. With `new Parcel(10)`, the `Parcel(var other)` branch is selected.

A record pattern is **not** an `equals()` call, nor is it a new constructor syntax. It checks the record type, retrieves component values via accessors, and then applies the inner patterns. The variables `text` and `other` belong to the scope of the matching branch, not fields added to the record.

A record can contain another record, in which case the syntax can be nested:

```java
record Point(int x, int y) {}
record Frame(Point point, Object tag) {}

// Nested pattern illustration:
case Frame(Point(var x, var y), String label) -> "...";
```

When checking dominance, the compiler examines not only the `Frame` name, but also the generality of the inner component patterns.

## 3. Case 1: A Preceding Type Pattern Dominates a Record Pattern

A **type pattern** that covers the entire record type can dominate a record pattern of that same type.

Example that **does not compile**:

```java
record Parcel(Object value) {}

static String wrong(Object input) {
    return switch (input) {
        case Parcel parcel -> "any Parcel";
        case Parcel(String text) -> "text:" + text; // Dominated
        default -> "other";
    };
}
```

Explanation:

1. The `Parcel parcel` branch matches every non-`null` `Parcel` selector, whether `value` is a string, number, object, or `null`.
2. The `Parcel(String text)` branch is a **subset** of `Parcel` instances: it additionally requires the component to match `String`.
3. If a value matches the later branch, it is guaranteed to have already matched the preceding branch. The compiler reports that the later branch is dominated.

The fix is to **put the specialized pattern first**, followed by the fallback type pattern:

```java
static String correct(Object input) {
    return switch (input) {
        case Parcel(String text) -> "text:" + text;
        case Parcel parcel -> "other Parcel";
        default -> "not a Parcel";
    };
}
```

When `input` is `new Parcel("Java")`, it returns `"text:Java"`. With `new Parcel(10)`, it returns `"other Parcel"`. With `42`, it returns `"not a Parcel"`.

A type pattern **of a supertype** can also dominate a specific record pattern. Since every Java record extends `java.lang.Record`, the following snippet also fails to compile:

```java
static String wrongAncestor(Object input) {
    return switch (input) {
        case Record record -> "some record";
        case Parcel(String text) -> "specific Parcel"; // Dominated
        default -> "other";
    };
}
```

When you need to handle a specific record type separately, place the record pattern branch before `case Record record` or `case Object obj`.

## 4. Case 2: A General Record Pattern Dominates a Specific Record Pattern

Dominance also occurs **between two record patterns of the same record**.

Suppose:

```java
record Parcel(Object value) {}
```

This snippet is **invalid**:

```java
static String wrong(Object input) {
    return switch (input) {
        case Parcel(var any) -> "some Parcel";
        case Parcel(String text) -> "String Parcel"; // Dominated
        default -> "other";
    };
}
```

Because the `value` component has a declared type of `Object`, the `var any` pattern in `Parcel(var any)` can accept any component value. Therefore, all `Parcel` instances that `Parcel(String text)` could match are already covered by the first branch.

A similar case:

```java
static String alsoWrong(Object input) {
    return switch (input) {
        case Parcel(Number number) -> "number";
        case Parcel(Integer integer) -> "integer"; // Dominated
        default -> "other";
    };
}
```

Here, `Integer` is a subtype of `Number`. Any `Integer` component that matches the second pattern already matches `Number number` in the first pattern. The `Parcel(Integer integer)` label is dominated.

**Easy-to-remember mental model:** when a preceding record pattern specifies the same record with **broader** (or equivalent) **component patterns** than a later pattern, it can dominate the later pattern.

| Preceding branch | Following branch | Result on Java 21 |
| --- | --- | --- |
| `case Parcel parcel` | `case Parcel(String s)` | Following branch is dominated |
| `case Record record` | `case Parcel(String s)` | Following branch is dominated |
| `case Parcel(var v)` | `case Parcel(String s)` | Following branch is dominated |
| `case Parcel(Number n)` | `case Parcel(Integer i)` | Following branch is dominated |
| `case Parcel(String s)` | `case Parcel(var v)` | Valid: following branch handles remaining components |
| `case Parcel(String s) when condition` | `case Parcel(String s)` | Valid with a dynamic guard: cases remain where the guard is false |

The table above considers branches in the same switch with a suitable selector, such as `Object`. Do not infer that Java has a general solver for arbitrary logical relationships between guard expressions; dominance rules are specifically defined in the language.

## 5. Case 3: Dominance Propagates into Nested Record Patterns

With multi-level records:

```java
record Point(int x, int y) {}
record Frame(Point point, Object tag) {}
```

A broad branch like the following can shadow a branch requiring `tag` to be a `String`:

```java
static String invalidNested(Object input) {
    return switch (input) {
        case Frame(Point(var x, var y), var tag) -> "frame";
        case Frame(Point(var x, var y), String name) -> "named"; // Dominated
        default -> "other";
    };
}
```

In the first branch, `Point(var x, var y)` deconstructs a `Point`. Both `x` and `y` are inferred as `int` because `Point` declares two `int` components. The `tag` component is matched with `var` and is not restricted to `String`.

The second branch has the same pattern for `point` but additionally requires `tag` to match `String name`. Thus, every value that matches the later branch also matches the first branch. The compiler reports dominance.

The fix:

```java
static String correctNested(Object input) {
    return switch (input) {
        case Frame(Point(var x, var y), String name) ->
                "named:" + name;
        case Frame(Point(var x, var y), var tag) ->
                "other tag:" + tag;
        case Frame(var point, var tag) ->
                "other point:" + point;
        default -> "not Frame";
    };
}
```

With `new Frame(new Point(2, 3), "A")`, the first branch matches. With `new Frame(new Point(2, 3), 7)`, the second branch matches. With `new Frame(null, "A")`, the `Point(var x, var y)` pattern does **not** match because the `point` component is `null`; the final `Frame(var point, var tag)` branch can handle it.

This is why, when designing nested record patterns, you must examine the **actual match paths of each component**, not just the outermost record name.

## 6. Selector Null vs. Component Null

Distinguish between two cases:

- **Null selector:** `switch ((Object) null)` requires a `case null` branch if you want to handle null values. `default` does not automatically catch `null` in a Java 21 pattern switch; if a null branch is missing, the switch typically throws a `NullPointerException`.
- **Non-null record selector with a null component:** `new Parcel(null)` is still a `Parcel` and can match record patterns depending on how the component pattern is declared.

Important example, verified with Java 21:

```java
static String show(Object input) {
    return switch (input) {
        case Parcel(String s) -> "text:" + s;
        case Parcel(var value) -> "other:" + value;
        default -> "not Parcel";
    };
}
```

With `new Parcel(null)`, the `Parcel(String s)` branch does **not** match: the component has declared type `Object`, and the `null` value does not match the `String s` type pattern in this context. The `Parcel(var value)` branch receives `null` and returns `"other:null"`.

A subtlety regarding **unconditional patterns** (patterns that match unconditionally for the component's type): for `record Parcel(Object value)`, `Parcel(Object v)` can also match a `null` component when used as a component pattern in Java 21, because `Object v` is an unconditional type pattern for a component of static type `Object`. Therefore, **you cannot simply conclude that every component pattern with a type name excludes null**.

```java
// With record Parcel(Object value):
case Parcel(Object v) -> "value:" + v;
```

The branch above can handle `new Parcel(null)`. When ordering branches, the compiler also considers the type relationship of component patterns; placing `case Parcel(Object v)` before `case Parcel(String s)` will cause the later branch to be dominated.

**Safe rule:** check selector `null` separately, and pay attention to the declared component type and the difference between a specific pattern (`String s`) and an unconditional pattern (`Object v`, or `var v` in the corresponding context). Do not bake false assumptions about null into branch ordering.

## 7. Complete Runnable Java 21 Program

Save the following code as **DominatedRecordPatternDemo.java**:

```java
public class DominatedRecordPatternDemo {
    record Parcel(Object value) {}
    record Point(int x, int y) {}
    record Frame(Point point, Object tag) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";
            case Parcel(String s) when s.startsWith("#") ->
                    "tag:" + s.substring(1);
            case Parcel(Integer n) -> "count:" + n;
            case Parcel(String s) -> "text:" + s;
            case Parcel(var v) -> "other:" + String.valueOf(v);
            default -> "not-parcel";
        };
    }

    static String nested(Object input) {
        return switch (input) {
            case Frame(Point(var x, var y), String label) ->
                    "labeled:" + label + "@" + x + "," + y;
            case Frame(Point(var x, var y), var tag) ->
                    "frame:" + x + "," + y + ":" + tag;
            case Frame(var point, var tag) ->
                    "remaining-frame:" + point + ":" + tag;
            default -> "not-frame";
        };
    }

    static String wideType(Object input) {
        return switch (input) {
            case Parcel(String s) -> "string-parcel";
            case Parcel parcel -> "parcel";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Parcel("#A")));
        System.out.println(describe(new Parcel("hello")));
        System.out.println(describe(new Parcel(7)));
        System.out.println(describe(new Parcel(null)));
        System.out.println(describe(new Parcel(3.5)));
        System.out.println(describe("x"));
        System.out.println(describe(null));

        System.out.println(nested(
                new Frame(new Point(2, 3), "A")));
        System.out.println(nested(
                new Frame(new Point(4, 5), 7)));
        System.out.println(nested(new Frame(null, "z")));

        System.out.println(wideType(new Parcel("hi")));
        System.out.println(wideType(new Parcel(9)));
    }
}
```

Compile and run:

```bash
javac DominatedRecordPatternDemo.java
java DominatedRecordPatternDemo
```

**Exact output:**

```text
tag:A
text:hello
count:7
other:null
other:3.5
not-parcel
null
labeled:A@2,3
frame:4,5:7
remaining-frame:null:z
string-parcel
parcel
```

### Branch Selection Flow Analysis

1. `new Parcel("#A")` matches `Parcel(String s)` and the guard `startsWith("#")` is true, so it returns `"tag:A"`.
2. `new Parcel("hello")` matches `Parcel(String s)` but the first branch's guard is false; the `Integer` pattern does not match either. The unguarded `Parcel(String s)` branch below is selected.
3. `new Parcel(7)` matches `Parcel(Integer n)`; it does not fall through to the `Parcel(var v)` branch at the end of the group.
4. `new Parcel(null)` does not match `Parcel(String s)` or `Parcel(Integer n)`, but it matches `Parcel(var v)`, so it prints `other:null`.
5. `new Parcel(3.5)` has a component of runtime type `Double`, which does not match `String`/`Integer` and falls into `var`.
6. The string `"x"` is not a `Parcel`, so it enters `default`. The `null` selector has its own `case null` branch.
7. For `Frame(Point(2,3), "A")`, the most specific nested record pattern branch matches, printing `labeled:A@2,3`.
8. For `Frame(Point(4,5), 7)`, the branch requiring `String label` does not match; the branch with `var tag` is selected.
9. For `Frame(null, "z")`, both branches requiring a `Point(...)` component fail to match; the broader `Frame(var point, var tag)` branch handles it and prints `remaining-frame:null:z`.
10. `wideType` places `Parcel(String s)` before `Parcel parcel` so there is no dominance; strings take the first branch and numbers take the second.

This is how to read and design a switch following **“specialized patterns first, fallback patterns later”**, taking into account the components inside a record.

## 8. Effect of `when` Guards on Dominance

A preceding record pattern may have a guard:

```java
static String guarded(Object input) {
    return switch (input) {
        case Parcel(var value) when value != null ->
                "non-null Parcel";
        case Parcel(String text) -> "text:" + text;
        case Parcel(var value) -> "remaining Parcel";
        default -> "other";
    };
}
```

The snippet above **compiles on Java 21**. Because the first branch has the dynamic condition `when value != null`, the compiler does not treat it as an unconditional pattern covering every `Parcel` value; for example, `new Parcel(null)` makes the guard false. Subsequent branches can still be declared.

However, for any non-null `String` component, the guard `value != null` is already true, so the `Parcel(String text)` branch **will never be selected in practice** under this logic. The compiler does not prove every relationship between dynamic guards and patterns. Therefore:

- **A compiler-reported dominance error** and **a branch unreachable due to business logic** are two related issues, but not identical.
- Do not rely on the compiler to catch every case where “the first guard is always true for all values of a later branch.”
- Place `Parcel(String text)` before the broad guard if you genuinely want to handle strings separately.

### The `when true` Guard

This snippet is **invalid**:

```java
static String invalidGuard(Object input) {
    return switch (input) {
        case Parcel(var value) when true -> "all Parcel";
        case Parcel(String text) -> "String Parcel"; // Dominated
        default -> "other";
    };
}
```

`when true` is a constant-true guard, so to the compiler it can create dominance just like an unguarded pattern. If you want to check a real condition, write a dynamic guard and clearly decide which branch should take priority. `when false` is a constant-false guard and is rejected by the compiler because no value can ever select that branch.

### Guards That Throw Exceptions

A guard is evaluated after the pattern matches. If the guard calls a method that throws an exception, Java **does not treat the exception as a false guard** to continue to later branches. The exception propagates as usual. Avoid guards with unpredictable side effects or unchecked access to nullable components.

## 9. Dominance Is Different from Exhaustiveness

**Dominance** asks: “Is a later case label completely shadowed by a preceding case label?”

**Exhaustiveness** asks: “Are all branches together sufficient to handle every valid selector value required by `switch`?”

These are two distinct problems.

Example with an `Object` selector:

```java
static String incomplete(Object input) {
    return switch (input) {
        case Parcel(String s) -> "text";
        case Parcel(Integer n) -> "number";
        // Missing branches for other types: non-exhaustive error.
    };
}
```

There is no dominance between the two branches above, because `String` and `Integer` are different types; however, the switch expression is still **not exhaustive** for all `Object` values.

Add a `default` branch or an appropriate covering pattern:

```java
static String complete(Object input) {
    return switch (input) {
        case Parcel(String s) -> "text";
        case Parcel(Integer n) -> "number";
        case Parcel(var v) -> "other Parcel";
        default -> "other";
    };
}
```

The specific branches come before the broad record branch, so they are not dominated; `default` handles non-`Parcel` objects (excluding `null` if there is no `case null` in Java 21).

A switch expression on a `Parcel` selector can be made exhaustive with a record pattern whose components are unconditional, or with a general type pattern for `Parcel`, while still keeping selector `null` in mind. Saying a switch is “exhaustive” does not mean `null` is handled according to business requirements.

## 10. Checklist for Auditing Dominated Record Patterns

When the compiler reports `this case label is dominated by a preceding case label`, you can check in order:

1. **Identify the selector type**: Is it `Object`, `Parcel`, an interface, a sealed type, or some supertype? The selector type determines which case labels are valid.
2. **Inspect preceding type patterns**: Is there a `case Parcel p`, `case Record r`, `case Object o`, or supertype pattern covering the record you want to handle?
3. **Compare record patterns of the same type**: Does `Parcel(var v)` appear before `Parcel(String s)`? Does `Parcel(Number n)` appear before `Parcel(Integer i)`?
4. **Drill down into nested components**: Does a preceding pattern like `Frame(Point(var x, var y), var tag)` cover `Frame(Point(var x, var y), String label)`?
5. **Check guards**: Does a preceding branch have a dynamic `when` or `when true`? Even with a dynamic guard, the compiler allowing multiple branches does not guarantee the business-logic order is right.
6. **Check `null`**: `case null` is for the selector; a nullable record component can cause a nested pattern to fail or still match an unconditional pattern.
7. **Reorder by specificity**: Move branches with specific component structures/types earlier, and broad `var`/type patterns later.
8. **Verify exhaustiveness after fixing**: Ensure the switch still has branches for other values, especially when the selector has a broad type like `Object`.

Not every dominance error should be fixed by adding `default`. `default` does not make a dominated case valid; you need to change the **order or pattern conditions**.

## 11. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Two record patterns of the same record are duplicates.” | Patterns for the same record can differ in component conditions; for example, `Parcel(String s)` and `Parcel(Integer i)` do not dominate each other. |
| “Only type patterns cause dominance.” | A record pattern with broad components, such as `Parcel(var v)`, can also dominate a more specific record pattern. |
| “Checking the outermost record type is enough.” | You must examine component patterns and nested record levels. |
| “`case Parcel(var v)` is the same as `case Parcel(String s)`.” | `var` is much broader; it accepts non-`String` components as well as `null` in this example. |
| “Putting the broad branch first saves matching work.” | It can cause specialized branches after it to become dominated or never selected. |
| “The compiler analyzes all logic in dynamic guards.” | The compiler does not prove every relationship between dynamic guards; code may compile while a later branch never runs on real data. |
| “If `Parcel(String s)` does not match `Parcel(null)`, then no component type pattern matches null.” | Unconditional patterns for the corresponding component type, such as `Object v` for `Parcel(Object value)`, can match null. |
| “`default` handles any null selector.” | In a Java 21 pattern switch, a separate `case null` is needed if null is accepted. |
| “Removing a dominated case makes the switch complete.” | After fixing dominance, you still need to check exhaustiveness. |
| “Dominance is a runtime error.” | It is a **compile-time** error caused by the relationship between case labels; invalid code does not compile. |

## 12. Self-Check Exercises

### Exercise 1 — Identify the Dominated Branch

Given:

```java
record Box(Object item) {}

static String classify(Object input) {
    return switch (input) {
        case Box(Number n) -> "number";
        case Box(Integer n) -> "integer";
        case Box(String s) -> "string";
        default -> "other";
    };
}
```

**Question:** Which branch does not compile and why?

**Answer:** `case Box(Integer n)` is dominated by the preceding `case Box(Number n)`, because `Integer extends Number`. `case Box(String s)` is not dominated by `Box(Number n)` because `String` is not a subtype of `Number`. Fix it by moving `Box(Integer n)` before `Box(Number n)`.

### Exercise 2 — Strings, Null, and Fallback

Given:

```java
record Box(Object item) {}

static String label(Object input) {
    return switch (input) {
        case Box(String text) -> "string";
        case Box(var item) -> "other";
        default -> "not-box";
    };
}
```

**Answer:** `label(new Box("A"))` returns `"string"`; `label(new Box(7))` returns `"other"`; `label(new Box(null))` also returns `"other"`. `var` catches the null component, whereas `String text` here does not match null.

### Exercise 3 — Fix a Nested Record Pattern

Given:

```java
record Point(int x, int y) {}
record Frame(Point point, Object tag) {}

static String wrong(Object input) {
    return switch (input) {
        case Frame(Point(var x, var y), var tag) -> "frame";
        case Frame(Point(var x, var y), String label) -> "labeled";
        default -> "other";
    };
}
```

**Answer:** The `Frame(..., String label)` branch is dominated because `var tag` in the first branch covers `String` as well. Swap the order of the two branches. When `point` is `null`, neither branch requiring `Point(...)` matches; add `case Frame(var point, var tag)` if you need to accept all remaining `Frame` instances.

### Exercise 4 — Can a Guard Save the Later Branch?

```java
record Box(Object item) {}

static String route(Object input) {
    return switch (input) {
        case Box(var item) when item != null -> "non-null";
        case Box(String text) -> "string";
        case Box(var item) -> "remaining";
        default -> "other";
    };
}
```

**Answer:** The snippet above compiles on Java 21 because the first branch has a dynamic guard. However, for any `Box` containing a non-null `String`, the first guard is already true, so `Box(String text)` is never selected in practice. Move `Box(String text)` first if strings need special handling. For `Box(null)`, the first guard is false and the final `Box(var item)` branch receives the value.

### Exercise 5 — Distinguish Compile-Time from Runtime

Why does `case Parcel p` before `case Parcel(String s)` cause a compiler error, whereas `case Parcel(String s)` before `case Parcel p` is valid?

**Answer:** The type pattern `Parcel p` covers all `Parcel` values that the specialized record pattern can match; the later record pattern branch becomes unreachable. When the order is reversed, `Parcel(String s)` matches only a subset of `Parcel` instances; the later `Parcel p` branch can still receive `Parcel` instances containing numbers, null, or other component types. This is a property of the set of matched values, not a change in the record's runtime type.

## 13. Takeaways

**A record pattern is dominated when a preceding case label already covers every case that the later record pattern can match.** In Java 21, dominance can come from a type pattern of the record itself or a supertype, a record pattern of the same type with broader components, or a broader nested record pattern.

The way to avoid this error is to **place specific patterns before general patterns**, evaluate guard overlap, and check selector `null` separately from component `null`. Beyond dominance, always check **exhaustiveness** to ensure the switch still handles all other cases.

Official references:

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — Switch Statements, including dominance (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — Patterns (§14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
