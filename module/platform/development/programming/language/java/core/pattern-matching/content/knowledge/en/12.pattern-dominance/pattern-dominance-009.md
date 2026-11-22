# Splitting Patterns to Avoid Confusing Dominance in Java `switch`

## 1. The problem: an overly broad branch shadows a specific branch

In pattern matching for `switch`, **dominance** occurs when a preceding `case` label can match all values that a subsequent `case` label can match. If a later branch is placed to handle a specific case separately, yet it never has a chance to be selected, Java reports a compile-time error.

The following example is **intentionally wrong** (assuming `value` has type `Object`):

```java
return switch (value) {
    case CharSequence chars -> "Text-like";
    case String text -> "String";
    default -> "Other";
};
```

Every `String` implements `CharSequence`. Therefore, if a value matches `case String text`, it has already matched the preceding `case CharSequence chars`. The Java 21 compiler reports an error similar to **“this case label is dominated by a preceding case label”**.

To avoid confusing dominance, **split** groups of values into cases with clear intent: place special cases before general cases; place branches with a `when` guard before unguarded branches; use a shared method for duplicated logic instead of trying to merge every pattern into a single label.

This lesson uses **Java 21**: record patterns and pattern matching for `switch` are standard features in Java 21. The `case Record(...)` and `when` examples below do not require `--enable-preview` when compiled with `javac --release 21`.

## 2. Why does the compiler reject it even when the program seems to have all `case`s?

The compiler's job is not just checking whether the `case` list is long or short. It checks **type relationships**, **pattern structure**, **guards**, branch order, and **exhaustiveness**.

Two important concepts:

- **Dominance:** is any `case` label shadowed by a preceding label, leaving that label with no way to be selected?
- **Exhaustiveness:** does the set of labels cover the values allowed by the type system, for `switch` forms that are required to be exhaustive?

A `switch` can be exhaustive and still fail due to dominance. Adding `default` also **cannot fix** a label that is already shadowed by a preceding branch.

**Dominance is not a variable-naming issue.** Two different rules are allowed to share the same pattern variable name if their scopes do not overlap. The issue lies in **which values a pattern can match** and **the order in which labels are placed**.

In addition, reordering cases can change program behavior. Therefore, proper refactoring must be based on **business intent** rather than simply moving lines around until the compiler stops reporting errors.

## 3. Case 1: supertype before subtype

### Writing style that causes dominance

```java
// Placed in a method with Object value.
// INTENTIONALLY WRONG: Does not compile in Java 21.
return switch (value) {
    case CharSequence sequence -> "SEQUENCE";
    case String text -> "STRING"; // This branch is dominated.
    default -> "OTHER";
};
```

`String` is a subtype of `CharSequence`. The `String` branch cannot run when an unguarded `CharSequence` branch comes before it.

### Valid and clear way to split

```java
return switch (value) {
    case String text -> "STRING:" + text;
    case CharSequence sequence ->
        "SEQUENCE:" + sequence.length();
    default -> "OTHER";
};
```

This order means:

1. If the value is a `String`, handle it specifically in the first branch.
2. If it is not a `String` but is still a `CharSequence`, handle it in the second branch; for example, `StringBuilder`.
3. The remaining types are routed to `default`.

For a `null` selector, a regular `default` in a pattern `switch` **does not handle `null` automatically**. If the requirement is not to throw `NullPointerException`, add `case null`.

**When should the subtype branch be removed?** If every `CharSequence` needs the exact same behavior, you can keep only `case CharSequence sequence`. There is no need to create a `String` case if there is no separate handling policy. Conversely, if the application only supports `String` and `StringBuilder`, a general `CharSequence` branch might **accept too many types**; in that case, keep two separate cases and have both call a shared helper.

### `Object` can also shadow every subtype

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Object any -> "OBJECT";
    case Integer number -> "INTEGER";
};
```

`case Object any` matches every non-`null` object. The `Integer` branch after it has no effect. To handle integers separately, move `case Integer number` to the front and use `default` at the end for the remaining data. `case null` has a different role from `case Object` and must be considered separately.

## 4. Case 2: general record pattern shadows a pattern with `when`

Declaration:

```java
record Point(int x, int y) {}
```

A **wrong** way to write it:

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Point(int x, int y) -> "ANY_POINT";
    case Point(int x, int y) when x == y ->
        "DIAGONAL";
    default -> "OTHER";
};
```

The first record pattern has no guard and matches every matching `Point`. The later branch only wants to accept a subset — points with `x == y` — but that subset has already been claimed by the branch above.

**How to fix:**

```java
return switch (value) {
    case Point(int x, int y) when x == y ->
        "DIAGONAL:" + x;
    case Point(int x, int y) ->
        "POINT:" + x + "," + y;
    default -> "OTHER";
};
```

In the first branch, `Point(...)` must match first, and only then is the guard `x == y` evaluated. For `Point(2,2)`, the guard is true and the first branch is selected. For `Point(2,3)`, the guard is false, so Java evaluates the unguarded `Point(...)` branch below.

**Useful template:**

```text
case Type(components...) when specific_condition -> specific_handling
case Type(components...)                         -> remaining_handling
```

This is an **illustrative skeleton**, not standalone Java syntax to paste into a file. The **specific → general** order makes the fallback for the same type clear.

### The compiler does not prove arbitrary logical relationships between guards

Do not assume the compiler deduces that any two `when` expressions are mutually exclusive. A guard can call a method, have side effects, or depend on runtime data. If the goal is to handle all values of a type, adding **one unguarded case** at the end of the group is usually easier to understand than complex guards that the reader must manually prove cover everything.

Example:

```java
case String text when text.isBlank() -> "BLANK";
case String text -> "TEXT:" + text;
```

The two cases are two separate branches; reusing the name `text` is valid. The second `case String text` handles strings that do not satisfy the first branch's guard.

## 5. Case 3: nested records need a specific branch before the fallback

When a record contains another record:

```java
record Point(int x, int y) {}
record Pair(Point point) {}
```

If you need to recognize a `Pair` containing the origin `Point(0,0)`, you should not put `case Pair(var point)` first:

```java
// INTENTIONALLY WRONG, the later branch is dominated:
return switch (value) {
    case Pair(var point) -> "ANY_PAIR";
    case Pair(Point(int x, int y))
            when x == 0 && y == 0 ->
        "ORIGIN";
    default -> "OTHER";
};
```

`case Pair(var point)` is an all-encompassing pattern for the `point` component; it already matches `Pair` instances containing the origin, so the later branch cannot be selected.

Valid split version:

```java
return switch (value) {
    case Pair(Point(int x, int y))
            when x == 0 && y == 0 ->
        "ORIGIN";

    case Pair(var point) ->
        point == null ? "PAIR_MISSING" : "PAIR_OTHER";

    case null, default ->
        "NOT_PAIR";
};
```

Meaning of each case:

- `Pair(new Point(0,0))`: nested record branch with guard, result `ORIGIN`.
- `Pair(new Point(3,4))`: nested record matches, but the guard is false; the `Pair(var point)` branch acts as the fallback, result `PAIR_OTHER`.
- `Pair(null)`: the nested pattern `Point(...)` **does not match `null`**, whereas the component pattern `var point` in Java 21 can bind `null`; result `PAIR_MISSING`.
- The selector itself is `null` or not a `Pair`: `case null, default`, result `NOT_PAIR`.

**Note on `null`:** `var point` at the record component position is an unconditional pattern for the component type, so it can receive `null` here. This does not mean `null instanceof Point p` is true; an `instanceof` expression with a `null` operand still returns `false`. Check `point != null` before calling accessors if the fallback can receive a record containing a null component.

When a nested pattern becomes too complex, an alternative design is to **only** use `case Pair(var point) -> classifyPoint(point)`, and let the helper distinguish the origin, other points, and `null`. There is no need to keep both the nested case and the helper; choose the approach that expresses the intent more clearly.

## 6. Complete Java 21 program

File **`DominanceRefactorDemo.java`**:

```java
public class DominanceRefactorDemo {
    sealed interface Event permits TextEvent, CountEvent, Done {}

    record TextEvent(String value) implements Event {}
    record CountEvent(int value) implements Event {}
    record Done() implements Event {}

    record Point(int x, int y) {}
    record Pair(Point point) {}

    static String describe(Event event) {
        return switch (event) {
            case null -> "NULL";

            case TextEvent(String text)
                    when text != null && text.isBlank() ->
                "BLANK";

            case TextEvent(String text) ->
                "TEXT:" + text;

            case CountEvent(int count) when count < 0 ->
                "NEGATIVE:" + count;

            case CountEvent(int count) ->
                "COUNT:" + count;

            case Done() ->
                "DONE";
        };
    }

    static String describeObject(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text -> "STRING:" + text.toUpperCase();
            case CharSequence chars ->
                "SEQUENCE:" + chars.length();
            default -> "OTHER";
        };
    }

    static String describePair(Object value) {
        return switch (value) {
            case Pair(Point(int x, int y))
                    when x == 0 && y == 0 ->
                "ORIGIN";

            case Pair(var point) ->
                point == null ? "PAIR_MISSING" : "PAIR_OTHER";

            case null, default ->
                "NOT_PAIR";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new TextEvent("  "),
            new TextEvent("ok"),
            new TextEvent(null),
            new CountEvent(-2),
            new CountEvent(3),
            new Done(),
            null
        };

        for (Event event : events) {
            System.out.println(describe(event));
        }

        System.out.println(describeObject("hi"));
        System.out.println(describeObject(new StringBuilder("hello")));
        System.out.println(describeObject(4));

        System.out.println(describePair(new Pair(new Point(0, 0))));
        System.out.println(describePair(new Pair(new Point(3, 4))));
        System.out.println(describePair(new Pair(null)));
        System.out.println(describePair(null));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 DominanceRefactorDemo.java
java DominanceRefactorDemo
```

Stdout:

```text
BLANK
TEXT:ok
TEXT:null
NEGATIVE:-2
COUNT:3
DONE
NULL
STRING:HI
SEQUENCE:5
OTHER
ORIGIN
PAIR_OTHER
PAIR_MISSING
NOT_PAIR
```

### Reading the output by group

**`describe(Event)` group:** `Event` is a `sealed interface` with three permitted record types. The guarded `TextEvent` branch accepts blank strings, and the unguarded `TextEvent` branch handles the remaining cases. `TextEvent(null)` goes to the fallback: a direct component type pattern `String text` can bind `null` in a Java 21 record pattern, so string concatenation produces `TEXT:null`. The guarded `CountEvent` branch separates negative numbers from the rest. `Done()` is handled separately. Because all permitted subtypes are covered, the `switch` expression is exhaustive without `default`. `case null` handles a null selector explicitly.

**`describeObject(Object)` group:** `String` is matched before `CharSequence`, so `"hi"` prints `STRING:HI`; `StringBuilder("hello")` is not a `String` but is a `CharSequence`, printing `SEQUENCE:5`. The number `4` is autoboxed to `Integer` when calling the method accepting `Object`; it does not match the two branches above and returns `OTHER`.

**`describePair(Object)` group:** `Pair(Point(0,0))` gets `ORIGIN`; `Pair(Point(3,4))` gets `PAIR_OTHER`; `Pair(null)` gets `PAIR_MISSING`. A `null` selector enters `case null, default` and gets `NOT_PAIR`.

The example not only reorders the cases, but also **cleanly separates three roles**: special handling by guard, fallback for the same type, and fallback for other types.

## 7. When different patterns need the same logic, split the cases but share a helper

One reason a `switch` becomes hard to read is repeating the same processing across multiple branches. Instead of using an overly broad supertype pattern or cramming incompatible variables into a single case, separate **identifying the data type** from **executing the processing**:

```java
static String normalize(CharSequence value) {
    return value.toString().strip();
}

static String read(Object value) {
    return switch (value) {
        case String text -> normalize(text);
        case StringBuilder builder -> normalize(builder);
        case null, default -> "UNSUPPORTED";
    };
}
```

These two methods are **illustrative snippets placed in the same Java 21+ class**, not a standalone program file.

- The `String` and `StringBuilder` branches accept the two supported types.
- Both call `normalize(CharSequence)` because both satisfy the `CharSequence` interface.
- Another `CharSequence` implementation is not automatically accepted, because we chose to accept only two specific types.

If you truly want to support **every** `CharSequence`, a single `case CharSequence chars -> normalize(chars)` is enough. Conversely, if business rules only allow two classes, replacing them with a supertype case would **widen the valid input set**, which is not an equivalent refactor.

A common mistake:

```java
// INTENTIONALLY WRONG in Java 21:
case String text, Integer number -> shared();
```

Java 21 does not support writing multiple type patterns that declare variables like this in a single label. Moreover, when one pattern matches, the other pattern's variable is not guaranteed to be bound. Use two independent cases instead:

```java
case String text -> common(text);
case Integer number -> common(number);
```

Here `common(Object)` is the corresponding helper declared in the enclosing class. When branches share the same responsibility, a **shared helper** is safer and clearer than trying to force different types into the same scope.

## 8. Dominance differs from scope and exhaustiveness

| Issue | Nature | Example | Appropriate fix |
| --- | --- | --- | --- |
| **Dominance** | A preceding case covers a later case | `CharSequence` before `String` | Specific case first, or remove the redundant case |
| **Scope/binding** | Pattern variable does not exist on the current path | Using `text` from a `String` case inside an `Integer` case | Keep the variable in its own rule; pass it to a helper |
| **Exhaustiveness** | The set of cases does not handle all possible types | `switch (Object)` with only `String` | Add missing cases, `default`, or an appropriate general pattern |
| **Guard logic** | A `when` condition partitions one type into multiple parts | `case String s when s.isBlank()` | Guarded case first, unguarded case after |
| **Null policy** | Selector or component can be null | `Pair(null)` differs from a `null` selector | Handle each nullable position explicitly |

**An exhaustive `switch` can still fail due to dominance.** For instance, `case CharSequence` before `case String`, plus `default`, does not make the `String` branch valid again.

**A `switch` without dominance errors can still be non-exhaustive.** If you remove `default` from a `switch` expression on `Object`, objects that are not among the listed types still have no handling branch.

**Duplicate variable names are not dominance.** With two independent rules `case String value -> ...` and `case Integer value -> ...`, using the same name `value` can be valid because the scopes of the two pattern variables do not overlap. You must examine type relationships and label order, not just compare variable names.

## 9. Common refactoring mistakes

### Reordering without considering intent

Changing `case CharSequence` then `case String` to `case String` then `case CharSequence` fixes dominance, but also changes **which branch handles `String`**. Confirm that this is actually what you want. If both do the exact same thing, removing the redundant case may be cleaner.

### Using `default` as a way to hide errors

Adding `default -> "Unknown"` does not fix a dominated branch. With a sealed hierarchy or a closed enum, adding `default` can also prevent future subtype/constant additions from forcing case-by-case logic updates. If you want the compiler to remind you to handle new states, list the specific cases without adding an arbitrary fallback.

### Treating `when` as an annotation with no runtime behavior

Guards are **evaluated at runtime** after the pattern part has matched. Example:

```java
case String text when auditAndAccept(text) -> handle(text);
case String text -> fallback(text);
```

These are **two illustrative labels** that only run when the corresponding methods exist. If `auditAndAccept` has side effects, changing the order or moving the guard can change the call count and the result. Do not fix dominance by carelessly copying or moving guards. Pure, clearly named guards are easier to test.

### Confusing a record's `null` component with a `null` selector

A `null` selector does not automatically match the record pattern `Pair(...)`; a `Pair(null)` record has a non-`null` `Pair` object as the selector, but contains a null component. The fallback branch must be designed for the actual **null position**, especially with nested patterns.

### Merging processing logic and classification logic into one overly broad case

Putting all actions inside `case Object obj` and writing `if` statements manually may compile, but it diminishes the benefit of pattern `switch` — letting the compiler recognize clear type branches. Consider keeping specific cases and extracting only the shared action.

### Overusing nested patterns

A nested pattern with many levels `RecordA(RecordB(RecordC(...)))` and multiple guards can be hard to maintain. If conditions get too deep, split out an outer record case and call a method to handle the component. **Clarity matters more than the fewest lines.**

## 10. Checklist before refactoring a `switch`

1. **Check the selector's static type.** `Object`, interface, record, enum, or sealed type? This is the basis for reasoning about which case covers which.
2. **Write down the expected value set for each case.** For example, `String` is a subset of `CharSequence`; the guard `x == y` is a subset of all `Point`s.
3. **Identify which cases are truly special.** If there is no separate action, remove the redundant branch instead of keeping it.
4. **Put specific branches first.** For type hierarchies: subtype before supertype. For the same record: guarded before unguarded fallback. For nested records: specific structure before catch-all deconstruction.
5. **Move shared logic into a helper.** Multiple cases can call the same method without declaring multiple variables in one label.
6. **Handle `null` intentionally.** Distinguish between a `null` selector and a `null` record component.
7. **Check exhaustiveness.** After splitting or removing cases, the `switch` expression/enhanced statement must still cover the required values.
8. **Compile with the right version and run edge cases.** For this lesson's examples: `javac --release 21`. Test subtype, supertype, true/false guards, and both forms of `null`.

Not every long switch needs more cases. Sometimes **removing a redundant branch** is the best fix.

## 11. Self-check exercises

**Exercise A — Type relationship.** Does the following snippet compile in Java 21?

```java
return switch (value) {
    case Number n -> "Number";
    case Integer i -> "Integer";
    default -> "Other";
};
```

**Answer:** No. `Integer` is a subtype of `Number`, so the `Integer` case is dominated. If integers need separate handling, place `case Integer i` before `case Number n`. Otherwise, the `Integer` case can be removed.

**Exercise B — Guard.** Given `record Point(int x, int y) {}`, where does `Point(2,3)` go?

```java
return switch (value) {
    case Point(int x, int y) when x == y -> "Diagonal";
    case Point(int x, int y) -> "Other point";
    default -> "Other type";
};
```

**Answer:** The `Other point` branch. The record pattern of the first branch matches, but the guard is false. This structure has no dominance error because the guarded branch precedes the fallback.

**Exercise C — Record with a null component.** Does `new Pair(null)` match `case Pair(Point(int x, int y))`? Does it match `case Pair(var point)`?

**Answer:** It does not match the nested pattern `Point(...)`, but it matches the fallback `Pair(var point)` in Java 21, with `point == null`. If you need to read properties of the point, you must guard against the null case.

**Exercise D — Business boundary.** Only `String` and `StringBuilder` are supported. Should the two branches be replaced with `case CharSequence chars` to make the code shorter?

**Answer:** No, unless requirements have expanded to all `CharSequence` implementations. Two specific cases calling a shared helper avoid duplicating logic while preserving the type boundary.

**Key takeaway:** Splitting patterns effectively means giving each `case` an easy-to-understand range of matched values: **specific first, general later, clear fallback, shared logic in a helper**. This avoids dominance, reduces confusion about pattern variables, and eases maintenance when the hierarchy changes.

## Official documentation

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.11, Switch Statements](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — §14.30, Patterns](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-14.html#jls-14.30).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).