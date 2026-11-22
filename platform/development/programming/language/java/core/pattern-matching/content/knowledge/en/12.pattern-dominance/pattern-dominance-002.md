# Why Must General Patterns Be Placed Later in a Java `switch`?

**Topic:** Java Core Pattern Matching → Dominance  
**Environment Requirements:** JDK 21 or later to use pattern matching for `switch` with the official JEP 441 syntax. Examples use `case Type variable` and `when` guards.

## 1. Short Answer

**A `case` with a general pattern, if placed earlier, can match all the values that a more specific `case` later needs to handle.** When the compiler proves this under the *dominance* rule, the later branch is considered unreachable/unselectable, and Java reports a **compile-time error** (*dominated case label*).

For example, `String` implements `CharSequence`. Therefore, every `String` is a `CharSequence`, but not every `CharSequence` is a `String`.

```java
// DOES NOT COMPILE on Java 21:
static String broken(Object input) {
    return switch (input) {
        case CharSequence chars -> "SEQUENCE";
        case String text -> "STRING"; // Error: dominated by the CharSequence case.
        default -> "OTHER";
    };
}
```

If `input` is `"Java"`, the first `CharSequence` branch already qualifies to accept it. The later `String` branch can never have a chance to handle a `String` value. Java detects this situation at compile time instead of waiting for the user to discover a "dead" branch at runtime.

**How to fix it:** place the specific branch first and the general branch later.

```java
static String fixed(Object input) {
    return switch (input) {
        case String text -> "STRING:" + text;
        case CharSequence chars -> "SEQUENCE:" + chars.length();
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Here `"Java"` selects `String`; `new StringBuilder("abc")` selects `CharSequence`; another object not belonging to either type goes to `default`; `null` is handled separately. This is an **illustrative method** that can be placed inside a Java 21 class.

## 2. Distinguishing "Check Order" and "Dominance"

When a `switch` has pattern labels that can potentially apply to the same value, label order helps determine which branch is selected. However, dominance is not just a stylistic guideline for writing clean code: Java has **static checking rules** to forbid a label from being completely shadowed by an earlier label.

- **Runtime match:** does a pattern match the specific value being tested at runtime?
- **Compile-time dominance:** given the type/pattern relationship, can the compiler conclude that an earlier label covers every value that a later label could select?
- **Consequence:** if a later label is dominated according to Java's rules, the entire `switch` is rejected at compile time, even before any actual tests are run.

A set model helps remember this:

```text
Number
  ├── Integer
  ├── Double
  ├── Long
  └── ...

CharSequence
  ├── String
  ├── StringBuilder
  └── StringBuffer
```

`Integer` is a subset of `Number`; `String` is a subset of `CharSequence`. Placing the subset case **before** the superset case allows specialized handling without being shadowed.

This is a **partial coverage relationship**, not a requirement to sort *all* cases by some global "generality." `Integer` and `String` have no subtype relationship with each other, so the relative order of those two branches can be chosen based on readability and business requirements.

## 3. Two Basic Dominance Examples

### 3.1. `Number` Shadows `Integer`

```java
// DOES NOT COMPILE:
return switch (value) {
    case Number number -> "Number";
    case Integer integer -> "Integer"; // Shadowed by the Number case.
    default -> "Other";
};
```

Assume `value` has static type `Object`. Every non-null `Integer` object matches `Number`; therefore, the later `Integer` branch is dominated.

Fix:

```java
return switch (value) {
    case Integer integer -> "Integer:" + integer;
    case Number number -> "Number:" + number;
    case null -> "Null";
    default -> "Other";
};
```

Illustrative results:

| Input | Selected Branch | Reason |
| --- | --- | --- |
| `42` | `Integer` | Narrower pattern comes first |
| `3.14` | `Number` | `Double` is a `Number`, not an `Integer` |
| `"42"` | `default` | It is a `String`, not a `Number` |
| `null` | `case null` | Does not match a top-level type pattern |

### 3.2. `CharSequence` Shadows `String`

```java
// DOES NOT COMPILE:
case CharSequence chars -> chars.length();
case String text -> text.length(); // Dominated.
```

Fix:

```java
case String text -> text.length();
case CharSequence chars -> chars.length();
```

When `input` is `new StringBuilder("abc")`, the `String` branch does not match, but the `CharSequence` branch matches. Thus both the concrete subtype and other types belonging to the shared interface are handled.

**Do not confuse this with method overload resolution:** `switch` does not automatically prioritize "the most specific pattern" regardless of where it appears. You must organize labels validly; the compiler forbids certain orderings that create dominated branches.

## 4. Match-All Type Pattern: `Object` and Selector Type

When the selector is declared as `Object`, the type pattern `case Object obj` covers **non-null objects**. If placed at the beginning, many specific type branches after it will be dominated:

```java
// DOES NOT COMPILE:
return switch (input) {
    case Object obj -> "OBJECT";
    case String text -> "STRING"; // Can never be selected.
};
```

An *unconditional* pattern for the selector type can also make the `switch` exhaustive for non-null values, similar to the coverage effect of a fallback branch. Therefore, you cannot arbitrarily add both `case Object obj` and `default` to have two match-all branches: the language enforces rules against duplicate/dominated match-all labels.

Write the intent more clearly:

```java
static String category(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "STRING";
        case Number n -> "NUMBER";
        case Object other -> "OTHER_OBJECT";
    };
}
```

This example lists two specialized types first and then places `Object` last to handle all remaining non-null objects. The `case null` branch is still needed separately: **`null` is not an instance of `Object`** and does not match the top-level type pattern `Object other`.

In some problems, `default` is a shorter choice than `case Object other`. If you do not need the `other` variable, `default` often expresses the meaning "unlisted cases" more clearly.

## 5. `when` Guards Are an Important Exception to Ordering Rules

A pattern with a broader type appearing earlier is not always an error. With a label **that has a guard which is not always true**, Java only selects it if it both matches the pattern and satisfies the `when` condition.

Common pattern:

```java
case String text when text.isBlank() -> "BLANK";
case String text -> "NON_BLANK";
```

The first branch accepts blank strings; when `text.isBlank()` returns `false`, the `switch` can continue to the general `String` branch. The compiler allows this order because the guard prevents the first branch from covering all strings.

Reversing them is an error:

```java
// DOES NOT COMPILE:
case String text -> "ANY_STRING";
case String text when text.isBlank() -> "BLANK"; // Dominated.
```

The unguarded `String` branch already accepts every non-null `String`, leaving no value domain for the later branch to handle.

You can also use a guard on a supertype before a subtype, **if the guard can actually be false**:

```java
case Number n when n.doubleValue() < 0 -> "NEGATIVE_NUMBER";
case Integer i -> "NONNEGATIVE_INTEGER";
case Number n -> "OTHER_NUMBER";
```

This structure is conceptually valid and has clear **business priority**: all negative numbers (including `Integer`) are classified first; next, the remaining `Integer` values are handled; finally, other `Number` values. In a program, you should write tests for `-1`, `0`, `1`, `-1.5`, and `1.5` to prove the intent.

**JLS detail:** a guard with the constant value `true` is treated as *unguarded* in dominance rules. Therefore:

```java
// DOES NOT COMPILE:
case String s when true -> "ALL_STRINGS";
case String s -> "STRING"; // Still dominated.
```

Do not assume the compiler understands arbitrary `when` expressions like a mathematical theorem prover. The compiler follows language rules on guarded/unguarded patterns and pattern relationships, rather than "solving general logic problems" to deduce every data domain.

## 6. Be Careful with Constants and Enum Constants

Dominance does not only occur between two type patterns. A constant label can also be completely covered by an earlier type pattern.

Example with a selector of type `Integer`:

```java
// DOES NOT COMPILE:
return switch (number) {
    case Integer n -> "ANY_INTEGER";
    case 0 -> "ZERO"; // Constant 0 is dominated by the preceding Integer pattern.
};
```

To handle `0` separately, place the constant label `case 0` before the general type label `case Integer n` (and handle `null` if the API requires it):

```java
return switch (number) {
    case null -> "NULL";
    case 0 -> "ZERO";
    case Integer n -> "OTHER_INTEGER";
};
```

The snippets above are **illustrative method bodies** inside a method with an appropriate `Integer number`. With `enum`, a type pattern covering the enum type can also shadow enum constant labels placed after it; similarly, place the specialized case before the general case if you truly want both.

Placing constants before type patterns aligns with the idea of "specific values first, general type groups later."

## 7. Record Patterns and Sealed Hierarchies Also Require Thinking About Coverage

Record patterns can deconstruct components:

```java
record Point(int x, int y) {}
```

Placing a general type pattern of the same record before a specific record pattern can cause the later label to be dominated:

```java
// DOES NOT COMPILE in switch(Object input):
case Point point -> "POINT";
case Point(int x, int y) -> "POINT_COMPONENTS"; // Dominated.
```

Reason: every object that matches the record pattern `Point(int x, int y)` is a `Point`, so the earlier `case Point point` label already covers them.

Reverse the order if you want deconstruction first:

```java
case Point(int x, int y) -> "AT:" + x + "," + y;
case Point p -> "POINT";
```

However, if the record pattern already covers every non-null instance of that `Point`, the later `case Point p` branch may still be considered dominated. **Do not treat "reversing the order" as an automatic fix for every pair of patterns:** you must examine the exact value domain each pattern can match. For a `record Point(int x, int y)` with only two primitive components, the record pattern `Point(int x, int y)` can accept every non-null instance of `Point`; in this design, **choose one representation** instead of trying to keep two equivalent cases.

With a sealed hierarchy, you should list the specialized subtypes so the compiler checks exhaustiveness:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}
```

If `switch (Shape shape)` already has `case Shape s` before `case Circle c`, `Circle` is shadowed. If there are only two subtypes `Circle` and `Rectangle`, often neither `case Shape s` nor `default` is needed anymore: the unguarded subtype cases can make the `switch` exhaustive, and the compiler will warn if a new subtype is missing later.

## 8. `default`, `case null`, and Label Order

`default` is a fallback label for values that do not match other cases. It is not a type pattern requiring a type check; do not confuse *dominance between patterns* with "you must always have default at the very end because of that."

With a nullable input:

```java
static String status(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "STRING";
        case Number n -> "NUMBER";
        default -> "OTHER";
    };
}
```

Key points to remember:

- `case null` handles a `null` selector; a standalone `default` does **not** automatically catch `null` in Java 21.
- `case null, default -> "OTHER"` is a special syntax allowed when business logic treats `null` and the remaining values the same way.
- For an open selector type like `Object`, `default` usually helps make a `switch` expression exhaustive.
- For an enum or closed sealed hierarchy where cases already provide full coverage, `default` may not be necessary. Omitting `default` when appropriate lets the compiler detect newly added unhandled cases.
- If there is already a *match-all* pattern for the selector, do not add a second match-all label. Moving `default` around randomly is no substitute for coverage analysis.

## 9. Java 21 Practice Program: Verifying Case Order

This is a standalone runnable program with tests for **subtype before supertype**, **guarded before unguarded**, **separate null**, and a **sealed hierarchy** without `default`.

Create the file **`GeneralPatternOrderDemo.java`**:

```java
public class GeneralPatternOrderDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String classify(Object input) {
        return switch (input) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s -> "STRING:" + s.length();
            case Integer n when n < 0 -> "NEGATIVE_INT:" + n;
            case Integer n -> "INTEGER:" + n;
            case Number n -> "NUMBER:" + n.getClass().getSimpleName();
            case CharSequence seq -> "CHARSEQ:" + seq.length();
            default -> "OTHER:" + input.getClass().getSimpleName();
        };
    }

    static String draw(Shape shape) {
        return switch (shape) {
            case null -> "NO_SHAPE";
            case Circle c when c.radius() < 0 -> "INVALID_CIRCLE";
            case Circle c -> "CIRCLE:" + c.radius();
            case Rectangle r ->
                    "RECTANGLE:" + r.width() + "x" + r.height();
        };
    }

    static void check(String name, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + " actual=" + actual);
        }
        System.out.println(name + "=" + actual);
    }

    public static void main(String[] args) {
        check("null", classify(null), "NULL");
        check("blank", classify("  "), "BLANK");
        check("string", classify("Java"), "STRING:4");
        check("negative", classify(-3), "NEGATIVE_INT:-3");
        check("zero", classify(0), "INTEGER:0");
        check("double", classify(2.5), "NUMBER:Double");
        check("builder", classify(new StringBuilder("abc")), "CHARSEQ:3");
        check("boolean", classify(true), "OTHER:Boolean");

        check("no-shape", draw(null), "NO_SHAPE");
        check("bad-circle", draw(new Circle(-1)), "INVALID_CIRCLE");
        check("circle", draw(new Circle(4)), "CIRCLE:4");
        check("rectangle", draw(new Rectangle(2, 5)), "RECTANGLE:2x5");

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 GeneralPatternOrderDemo.java
java GeneralPatternOrderDemo
```

**Standard output:**

```text
null=NULL
blank=BLANK
string=STRING:4
negative=NEGATIVE_INT:-3
zero=INTEGER:0
double=NUMBER:Double
builder=CHARSEQ:3
boolean=OTHER:Boolean
no-shape=NO_SHAPE
bad-circle=INVALID_CIRCLE
circle=CIRCLE:4
rectangle=RECTANGLE:2x5
ALL CHECKS PASSED
```

### Why Does Each Line Matter?

1. `null`: does not match the type patterns, enters the `case null` branch.
2. `"  "`: matches `String` with the `isBlank()` guard; because this branch precedes the general `String` branch, it returns `BLANK`.
3. `"Java"`: the blank guard is false, continues to `case String s`, returns `STRING:4`. It is also a `CharSequence`, but the `String` branch has priority.
4. `-3`: matches `Integer` with the negative guard; `0`: negative guard is false, matches the general `Integer` branch.
5. `2.5`: `Double` is a `Number` but not an `Integer`, so it enters `Number`.
6. `new StringBuilder("abc")`: not a `String`, but implements `CharSequence`, returns `CHARSEQ:3`.
7. `true`: `Boolean` does not belong to the type patterns above, enters `default`.
8. `draw` checks null, `Circle` with negative radius, remaining `Circle`, and `Rectangle`. Both subtypes of the sealed `Shape` are covered, so `default` is not needed.

The `check` method throws an `AssertionError` if any expected result differs from the actual one. The final line `ALL CHECKS PASSED` only appears when all 12 preceding checks pass. This is a **Java SE self-test**, requiring no external test library. The program uses official Java 21 features without preview syntax.

## 10. Test Matrix to Catch Ordering Bugs

| Input | Expected Case | Why Test It |
| --- | --- | --- |
| `"Java"` | General `String` | Proves `String` is handled specifically rather than falling into `CharSequence` |
| `new StringBuilder("abc")` | `CharSequence` | Proves the supertype branch still accepts non-`String` subtypes |
| `-3` | Guarded `Integer` | Verifies the guard actually gets a chance to run |
| `0` | General `Integer` | Verifies a false guard does not lose the type branch |
| `2.5` | `Number` | Verifies the supertype branch accepts other numeric types |
| `true` | `default` | Verifies the fallback for unlisted types |
| `null` | `case null` | Avoids confusing `Object` or `default` with null-handling policy |
| `new Circle(-1)` | Guarded `Circle` | Verifies the special case of the subtype |
| `new Circle(4)` | General `Circle` | Verifies the remaining scope of the subtype |
| `new Rectangle(2,5)` | `Rectangle` | Verifies exhaustiveness of the sealed hierarchy |

To catch errors right at compile time, proactively test **a reversed pair of cases** in a separate example (without modifying the working program) and read the message `this case label is dominated by a preceding case label`. This is a compiler error and cannot be "runtime tested" because an erroneous program cannot compile.

## 11. Distinguishing Dominance and Exhaustiveness

These are two very different questions:

- **Dominance:** is any later `case` covered by an earlier branch to the extent that it can never be selected?
- **Exhaustiveness:** do the valid labels together cover all values that the `switch` is required to handle?

A `switch` can be **exhaustive yet have invalid dominance**, for example `case Number n` before `case Integer i`, followed by `default`: overall it looks like it has "enough branches" but still fails to compile because the `Integer` label is dominated.

A `switch` can also **have no dominance errors yet lack exhaustiveness**, for example `switch (Object)` with only `case String` and `case Integer`, without a branch covering the rest. When it is a `switch` expression, the compiler requires adding the necessary labels.

A sealed set like `Shape` allows the compiler to prove `Circle` and `Rectangle` are sufficient. If you want to add `record Triangle(...) implements Shape`, you must add it to `permits` and update the related exhaustive `switch` statements when recompiling. Because there is no `default` absorbing new subtypes, important business domains are less likely to miss handling branches.

## 12. How to Organize `case` Labels for Maintainability

When encountering a new `switch` with multiple data types, follow this process:

1. **List the domain of the selector:** `Object`, an interface, a sealed hierarchy, an enum, or a concrete type?
2. **Identify subtype relationships:** explicitly note `String <: CharSequence`, `Integer <: Number`, `Circle <: Shape`. Only compare actual coverage relationships—do not "guess" which type sounds general.
3. **Prioritize specialized situations:** constants, guard conditions, or subtypes when distinct behavior is needed.
4. **Place general patterns afterward:** supertypes or an unguarded branch of the same type.
5. **Finally design the remainder:** `default`, a match-all pattern, or exhaustive enum/sealed cases. Do not add two match-all branches.
6. **Handle null according to the contract:** `case null`, `case null, default`, or rejecting the input.
7. **Compile before running tests:** dominance errors are static errors; runtime tests only make sense after all patterns are valid.
8. **Test both narrow and broad branches:** `Integer` + `Double`; `String` + `StringBuilder`; guard true + guard false.

This does not mean "every `switch` must have cases in the exact same order"—it is a layout that **aligns with coverage relationships and business priorities**.

## 13. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "The compiler will automatically pick the most specific pattern regardless of position." | `switch` follows label and dominance rules; a shadowed specific branch can cause a compile error. |
| "`case Number n` accepts `Integer` and `Double`, so placing it before `Integer` is fine." | The later `Integer` is dominated if the preceding `Number` branch has no restricting guard. |
| "Putting all narrow patterns at the top is always enough." | You must consider guards, record patterns, null, match-all, and exhaustiveness; two patterns with the same match domain cannot coexist just by swapping their order. |
| "`when` is always treated as a restricting branch." | A constant `true` guard is treated as unguarded in dominance rules; a guard does not automatically eliminate errors. |
| "`null` will be accepted by `case Object o`." | A top-level type pattern `Object o` does not match null. |
| "`default` solves all dominance errors." | `default` helps cover the remainder but cannot rescue a dominated case. |
| "`case String s` lets you use `s` outside the switch too." | A pattern variable is only in scope where Java confirms it has matched. |
| "Dominance is always determined by test inputs." | It is a compile-time rule. Tests only verify that valid branches handle business logic correctly. |
| "Any interfaces with unrelated names can never overlap." | Two interfaces can be implemented by the same class; you must analyze match possibilities and type relationships, not just names. |
| "Only `case ->` has dominance." | Pattern case label rules also apply when using the colon form `case ...:`; the arrow just makes control flow clearer. |

## 14. Practice Exercises

1. Write a `switch(Object)` accepting `String`, `CharSequence`, and `default`. Intentionally place `CharSequence` before `String` and record the compiler message. Fix the order, then test `"abc"` and `new StringBuilder("abc")`.
2. Write a `Number` / `Integer` version. Test `42`, `3.14`, and `null`, then explain why `Integer` must come before `Number` if there is no restricting guard.
3. Place `case String s when s.length() > 3` before `case String s`. Test strings of length `3`, `4`, and `5`. Then swap the two branches to observe the dominance error.
4. Try `case Number n when n.doubleValue() < 0` before `case Integer i`, then `case Number n`. Test both negative and positive integers to confirm the guard is broad but not a match-all branch.
5. With `record Point(int x, int y)`, try the two labels `case Point p` and `case Point(int x, int y)`; predict the dominance error. Fix it by choosing one pattern suited to your purpose instead of keeping two branches with overlapping domains.
6. Use `sealed interface Shape` with `Circle` and `Rectangle` as in the sample program. Intentionally place `case Shape s` before `case Circle c`; compile and read the error. Return to the specific subtype cases.
7. Add `case Object obj` to a switch that already has `default` and analyze the match-all rule. Redesign it so only one appropriate catch-all branch remains.
8. Write unit tests distinguishing `null` behavior from `default`, and test `Integer` / `Double` / `String` / `StringBuilder`.
9. Show an exhaustive `switch` that has a dominance error and a `switch` with no dominance error that lacks exhaustiveness. Explain the two different compiler messages.

**Completion criteria:** be able to explain why an unguarded supertype pattern shadows a subtype pattern, know when a guard changes priority, distinguish `case null` / `default` / match-all, and build a Java 21 `switch` that both compiles and has tests for both specific and general branches.

**Official references:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch, Pattern Label Dominance](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — `switch` labels and dominance (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — Pattern matching and dominance (§14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
