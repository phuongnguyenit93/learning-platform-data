# Type Patterns in `switch` `case` Labels

> **Module:** Java Core Pattern Matching → Switch pattern. This lesson uses **Java 21+**, the first version where *pattern matching for switch* is a standard feature and does not require `--enable-preview`. In Java 17–20, this feature was in preview with changing syntax and rules; do not copy Java 21 examples directly to compile with `--release 17`.

## Learning Objectives

After this lesson, you will be able to:

- Read and write `case String text ->` and `case Integer number ->` labels in a `switch` statement or expression.
- Identify the **selector** (the value being matched), the **type pattern** (the type to test + the bound variable), and the **static type** of the pattern variable.
- Explain the evaluation order of `case` labels, `when` guards, branch-level variable scoping, the `null` case, and when the compiler reports a **dominated case** or **non-exhaustive switch**.
- Order patterns from specific to general, include a branch to handle all remaining types, and verify the code with JDK 21.

## 1. What is a type pattern in a `case`?

A **type pattern** has the structure:

~~~text
TypeName variableName
~~~

For example, `String text` or `Integer number`. When placed after the `case` keyword in a `switch`, the pattern is tested against **the value of the selector expression**:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Text: " + text.toUpperCase();
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
~~~

This is a **demonstration method snippet** placed inside a class; it is not a standalone program. In this snippet:

- `value` is the **selector expression** of the `switch`; its static type is `Object`.
- `case String text` is a **case label containing a type pattern**. When the runtime value is a `String`, it matches and creates the variable `text` with static type `String`.
- `case Integer number` handles a runtime value compatible with `Integer`; the variable `number` has static type `Integer`.
- `default` handles **non-`null` values** that did not match any preceding pattern. `null` must be handled separately if it can occur; see section 5.
- `->` denotes the modern arrow branch syntax: in a switch expression, the expression on the right-hand side is used as the **result value**.

Compare with `instanceof`:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Both use the type pattern `String text`, but `instanceof` returns the result of the type test in a condition; `switch` selects **one of several `case` labels** to execute. Inside the `case`, you do not need to write `(String) value` because the variable `text` already has the right type.

## 2. In what order does the runtime select a `case` label?

A helpful mental model for pattern `switch` in Java 21:

1. **Evaluate the selector once** to obtain the value (`switch (value)`).
2. Examine the `case` labels in source-code order, from top to bottom, according to the switch matching rules.
3. For a `case T variable` label, check whether the selector value is **compatible with type `T`**. If it matches, the variable `variable` is initialized.
4. If there is a `when` guard, evaluate the guard **only after the pattern matches**. If the guard returns `false`, try the next matching label.
5. Select the matched branch (or `default` when applicable), then execute the branch body. With the `->` syntax, there is no *fall-through* from one branch to the next.
6. If the selector is `null`, the special handling rules in section 5 apply before treating it like a normal object.

Example:

~~~java
static String inspect(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> "empty string";
        case String s -> "string with length " + s.length();
        case Number n -> "number " + n;
        default -> "other object";
    };
}
~~~

- For `"Java"`: the first `String s` pattern matches, but `s.isEmpty()` is `false`; the next `String s` branch is selected.
- For `""`: the first pattern matches and the guard is `true`; the method returns `"empty string"`.
- For `Integer.valueOf(5)`: does not match `String`, but matches `Number` (because `Integer extends Number`).
- For `new Object()`: `default` is selected.

**Key point:** `case String s` can appear multiple times when one branch has a guard and a subsequent branch handles the remaining values of the same type not accepted by the guard. The two pattern variables `s` are in separate branches, so there is no name conflict.

## 3. The static type of the selector determines which patterns are valid

Just like `instanceof`, the compiler checks the **applicability of a type pattern** based on the static type of the selector; the runtime determines whether the value actually matches.

~~~java
static String classify(CharSequence sequence) {
    return switch (sequence) {
        case String s -> "String length=" + s.length();
        case StringBuilder b -> "builder length=" + b.length();
        default -> "another sequence";
    };
}
~~~

`sequence` has static type `CharSequence`. Both `String` and `StringBuilder` implement `CharSequence`, so the compiler can accept those two type patterns. A `StringBuilder` value matches the second label; a `String` matches the first label. `default` handles other `CharSequence` implementations.

Conversely, the following code **intentionally does not compile**:

~~~java
static String broken(Integer value) {
    return switch (value) {
        case String text -> "text"; // ERROR: incompatible type String.
        default -> "other";
    };
}
~~~

Because the selector has static type `Integer`, a type pattern testing for `String` is not applicable under Java's rules. The compiler prevents a meaningless match from being written into the source code.

### Type patterns use reference types in Java 21

When you want to distinguish boxed values in a selector of type `Object`, write:

~~~java
static String kind(Object value) {
    return switch (value) {
        case Integer n -> "Integer";
        case Long n -> "Long";
        default -> "Different type";
    };
}
~~~

This is a **demonstration snippet inside a class**. In Java 21, do not use `case int n` or `case long n` in place of the wrapper patterns in the example above: patterns on primitive types are not yet a standard Java 21 feature. This is a language-version limitation, separate from the fact that `int` values can appear as constants in traditional numeric `switch` statements.

**No manual casting:** After `case Integer n`, you can use `n.intValue()`, `n + 1`, etc.; there is no need for `(Integer) value`. The type of `n` is established by the pattern.

## 4. Pattern variables live in their guard and corresponding branch

A type pattern **declares a variable** when it matches, and the compiler applies **flow scoping** to restrict where it can be used.

~~~java
static String title(Object input) {
    return switch (input) {
        case String text when !text.isBlank() ->
                "title=" + text.trim();
        case String text ->
                "empty or blank";
        default ->
                "not text";
    };
}
~~~

- Inside the guard `when !text.isBlank()`, the variable `text` has already been created from `String text` and is guaranteed to have type `String`.
- In the expression on the right-hand side of `->`, that branch's `text` is also valid.
- The `text` variable from the first branch **cannot be used outside the branch** to handle `default` or after the `switch` statement.
- The next `case String text` branch can declare **another `text` variable**, because the two case arms are separate.
- If you use `case Integer number` in another branch, it has its own name and type.

The `case Type variable -> ...` syntax also works in a **switch statement**:

~~~java
static void print(Object input) {
    switch (input) {
        case String text -> System.out.println(text.length());
        case Integer number -> System.out.println(number + 1);
        default -> System.out.println("other");
    }
}
~~~

The difference here is that a statement performs side effects and does not return a value from the `switch`, whereas a switch expression `return switch (...) { ... };` must produce a value on every branch.

### Colon (`:`) labels and why `->` should be preferred when learning patterns

Java 21 still supports writing `case String text:` in a switch statement, but the scoping and **fall-through** rules for labels carrying pattern variables can cause the compiler to reject the program if an execution path risks entering a branch where the pattern variable has not been initialized.

Examples using `->` per branch, as in this lesson, make it clear which variable belongs to which branch and avoid the risk of falling through between labels. If you must read `:`-style code, check the control flow into the label, `break`/`yield` usage, and variable scope before making changes.

## 5. `null`: `default` does not catch `null` automatically

For Java 21 pattern switches, `null` must be handled intentionally:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "null value";
        case String s -> "string=" + s;
        default -> "other";
    };
}
~~~

`case null` is a **special label**, not a type pattern. It handles a `null` selector before regular type patterns are considered. If `case null` is omitted, a pattern switch with a `null` selector normally throws `NullPointerException`; **`default` does not catch `null`**.

The following example **compiles**, but will throw `NullPointerException` when `null` is passed:

~~~java
static String withoutNullCase(Object value) {
    return switch (value) {
        case String s -> "string";
        default -> "default";
    };
}

// withoutNullCase(null) -> NullPointerException.
~~~

If you want to use a single branch for both remaining objects and `null`, Java 21 syntax allows:

~~~java
static String withCombinedDefault(Object value) {
    return switch (value) {
        case String s -> "string";
        case null, default -> "other or null";
    };
}
~~~

**Distinction:** `case String s` does not match `null`. `case null` only catches `null`; `case null, default` combines the `null` case and all remaining cases into one branch without introducing a new pattern variable.

## 6. Dominance: a general label must not shadow a specific label after it

**Dominance** is a compiler rule that prevents a `case` label from becoming unreachable because **every value it handles** is already covered by an earlier label.

The following code **intentionally does not compile**:

~~~java
static String brokenOrder(Object value) {
    return switch (value) {
        case CharSequence seq -> "character sequence";
        case String text -> "string"; // ERROR: dominated by the preceding branch.
        default -> "other";
    };
}
~~~

Because `String implements CharSequence`, every `String` object matches `CharSequence`; the `String` branch placed afterward can never be selected.

**Fix by placing the specific branch first:**

~~~java
static String correctOrder(Object value) {
    return switch (value) {
        case String text -> "string=" + text;
        case CharSequence seq -> "other sequence=" + seq.length();
        default -> "other";
    };
}
~~~

By the time execution reaches the `CharSequence` branch, all `String` values have already been handled; only `StringBuilder` or other implementations remain.

### Guards and dominance

The following code **intentionally fails to compile**:

~~~java
static String brokenGuardOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

An **unguarded** `case String s` branch above already handles all `String` values. Therefore, placing a guarded branch after it is meaningless.

The correct way:

~~~java
static String correctGuardOrder(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "other string";
        default -> "not a string";
    };
}
~~~

For a guard with a general condition, the compiler cannot assume it is always true. Thus, a narrower guarded branch can precede a general branch of the same type. A guard with a constant `true` condition is treated specially by the language when determining dominance.

**Best practice:** order from **specific type → broader type → default**, and place guarded special-case branches before unguarded branches of the same type.

## 7. Exhaustiveness: what cases must a pattern switch cover?

A **switch expression** must have a way to produce a result for every value in the valid type set of the selector. For an **enhanced switch statement** with type patterns in Java 21, the exhaustiveness requirement also applies. Unlike some traditional switch statements that only use constants, a pattern switch missing a matching branch can cause a compilation error.

The following code **intentionally does not compile**:

~~~java
static String incomplete(Object value) {
    return switch (value) {
        case String text -> text;
        // ERROR: countless other Object types are not handled.
    };
}
~~~

Fix with `default`:

~~~java
static String complete(Object value) {
    return switch (value) {
        case String text -> text;
        default -> "not text";
    };
}
~~~

Another fix using a type pattern that **covers all non-null objects**:

~~~java
static String completeWithType(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String=" + text;
        case Object any -> "Object=" + any.getClass().getSimpleName();
    };
}
~~~

- `case Object any` is a pattern that covers every **non-null** value assignable to `Object`. No `default` is needed.
- `case null` is still required if the intended behavior is to handle `null` without throwing an exception. Exhaustiveness for non-null reference values and `null` handling are two separate concerns.
- Do not place `case Object any` before `case String text`: the `String` branch would be dominated.
- Do not add `default` **after** `case Object any` when the selector type is `Object`: the general branch already covers all remaining normal values, and the compiler may reject a redundant branch.

### `sealed` types: the compiler can infer exhaustive cases

Java 21 can examine the permitted subclasses of a `sealed` type to determine whether a switch is exhaustive. This example is **independent of the program in section 9**, placed inside a class as follows:

~~~java
public class SealedCaseExample {
    sealed interface Shape permits Circle, Square {}
    record Circle(int radius) implements Shape {}
    record Square(int edge) implements Shape {}

    static String label(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle=" + c.radius();
            case Square s -> "square=" + s.edge();
        };
    }

    public static void main(String[] args) {
        System.out.println(label(new Circle(3)));
    }
}
~~~

Compile and run:

~~~bash
javac --release 21 SealedCaseExample.java
java SealedCaseExample
~~~

**Stdout:**

~~~text
circle=3
~~~

No `default` is needed because all permitted subclasses `Circle` and `Square` already have branches. This is an example of exhaustiveness based on the **type system**, not a runtime trick. If `null` must be handled by your business logic, add `case null`; without this label, a `null` value does not automatically match a `Shape` branch.

## 8. Forms that are not equivalent

| Syntax | Is it a type pattern? | Meaning |
| --- | --- | --- |
| `case String text ->` | **Yes** | If the selector is a `String`, bind `text` of type `String` |
| `case Integer n ->` | **Yes** | Matches wrapper `Integer` and binds `n` |
| `case String s when s.isBlank() ->` | **Yes, with a guard** | Matches `String` first, then checks the condition |
| `case null ->` | No | Catches the `null` value separately |
| `default ->` | No | Catches unmatched non-null values |
| `case null, default ->` | No | Combines the `null` and `default` labels |
| `case "READY" ->` | No | String constant label in allowed selector contexts |
| `case Point(int x, int y) ->` | Not a **simple type pattern** | This is a **record pattern**, which deconstructs a record; a separate topic |
| `case int n ->` | Invalid in standard Java 21 | Do not confuse with `case 1 ->`, a constant label in a numeric switch |

**You cannot arbitrarily combine multiple type patterns with different bindings** into one label like `case String s, Integer i ->` and assume both `s` and `i` are always initialized. Java 21 has rules governing fall-through and pattern bindings; the clearest approach is to use separate case arms:

~~~java
static String separate(Object input) {
    return switch (input) {
        case String s -> "String " + s;
        case Integer i -> "Integer " + i;
        default -> "Other";
    };
}
~~~

Here, **each branch owns its own pattern variable**. You can use the same name in independent branches, such as `case String value ->` and `case Integer value ->`, though naming variables after their types (`text`, `number`) often makes code easier to read.

## 9. Complete Java 21 example: type patterns, guards, and `null`

Save the entire code to **`SwitchTypeCaseExample.java`**:

~~~java
public class SwitchTypeCaseExample {

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank text";
            case String s -> "text: " + s.toUpperCase();
            case Integer n when n > 0 -> "positive int: " + n;
            case Integer n -> "int: " + n;
            case Number n -> "number: " + n;
            default -> "other";
        };
    }

    static String classify(CharSequence cs) {
        return switch (cs) {
            case null -> "null";
            case String s -> "String length=" + s.length();
            case StringBuilder b -> "builder length=" + b.length();
            default -> "another sequence";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe("  "));
        System.out.println(describe(7));
        System.out.println(describe(-2));
        System.out.println(describe(2.5));
        System.out.println(describe(new Object()));
        System.out.println(describe(null));
        System.out.println(classify(new StringBuilder("abc")));
    }
}
~~~

Compile and run with **JDK 21+** using Java 21 source mode:

~~~bash
javac --release 21 SwitchTypeCaseExample.java
java SwitchTypeCaseExample
~~~

**Exact stdout:**

~~~text
text: JAVA
blank text
positive int: 7
int: -2
number: 2.5
other
null
builder length=3
~~~

Explanation:

1. `"Java"` matches `String`; the `isBlank()` guard is false, so it enters the second `String s` branch. `s` has type `String`, so `toUpperCase()` can be called.
2. `"  "` (two spaces) matches the guard `String s when s.isBlank()`, printing `blank text`.
3. `7`, when passed to an `Object` parameter, is autoboxed to `Integer`; the guard `n > 0` is true, so it prints `positive int: 7`.
4. `-2` still matches `Integer`, but the guard `n > 0` is false; the next `Integer n` branch prints `int: -2`.
5. `2.5` is a `Double`, which is a `Number`, so it prints `number: 2.5`.
6. `new Object()` does not match any of the specific type patterns and goes to `default`.
7. `null` is handled explicitly via `case null`; no `NullPointerException` is thrown.
8. `new StringBuilder("abc")` has runtime type `StringBuilder` and selector `cs` has static type `CharSequence`, so the `StringBuilder b` branch prints `builder length=3`.

**When using as a standalone program:** keep the file name and public class name matching. This snippet does not require `--enable-preview` when compiled for Java 21 as instructed.

## 10. Common errors and how to fix them

### Error 1 — Placing a general branch before a specific branch

~~~java
return switch (value) {
    case Number n -> "number";
    case Integer i -> "integer"; // ERROR: Integer is already a subtype of Number.
    default -> "other";
};
~~~

**Fix:** handle `Integer` before `Number`.

### Error 2 — Placing an unguarded branch before a guarded branch of the same type

~~~java
return switch (value) {
    case String s -> "any string";
    case String s when s.length() > 10 -> "long"; // ERROR: dominated.
    default -> "other";
};
~~~

**Fix:** place `case String s when s.length() > 10` before `case String s`.

### Error 3 — Forgetting exhaustiveness

~~~java
return switch (value) {
    case String s -> s;
};
~~~

If `value` has static type `Object`, the compiler rejects it because many other types remain. **Fix:** add `default` or a pattern covering the entire set of values for the selector's type.

### Error 4 — Assuming `default` always handles `null`

~~~java
return switch (value) {
    case String s -> s;
    default -> "other";
};
~~~

**When `value == null`:** normally throws `NullPointerException` in Java 21. **Fix:** add `case null` if `null` is a valid input.

### Error 5 — Using a pattern variable outside its matching branch

~~~java
switch (value) {
    case String s -> System.out.println(s.length());
    default -> System.out.println("other");
}
System.out.println(s); // ERROR: s is not in scope here.
~~~

**Fix:** use `s` inside the branch where it is bound, or extract the value you want to keep into another variable using a value-returning switch expression.

### Error 6 — Using a type that is not applicable to the selector

~~~java
Integer number = 3;
return switch (number) {
    case String s -> "string"; // ERROR: incompatible types.
    default -> "other";
};
~~~

**Fix:** choose a pattern with a valid type relationship, or change the input type if you genuinely need to handle multiple types.

### Error 7 — Confusing Java versions and old preview syntax

In Java 21, guards use `when`, for example `case String s when s.length() > 3 ->`. Some older preview examples used `&&` in guarded labels; do not copy those directly into Java 21. If you use JDK 17 to compile Java 21 code, you will encounter version or preview errors. Compile with `javac --release 21` on JDK 21+.

### Error 8 — Treating a type pattern as a cast usable everywhere

`case String s` only creates the variable `s` when its corresponding branch matches. It does not change the static type of the selector `value` (which is `Object`), nor does it allow another branch to use `s`. To work with a properly typed variable in another branch, you need a separate pattern/binding.

## 11. Step-by-step process for analyzing a pattern switch

When reading a `switch` with type patterns, follow this order:

1. **Read the selector:** `switch (expression)`; what is the static type of the expression, and can it be `null`?
2. **Read each label:** `case T variable`, `case null`, constant, or `default`? Which labels are type patterns?
3. **Check type compatibility:** can the selector be downcast to the pattern type? An `Integer` cannot be used as a `String`.
4. **Evaluate order and guards:** which branch can match first? Is there a `when` guard narrowing a case? Does a general branch shadow a narrower one?
5. **Check exhaustiveness and `null`:** do all valid types have a handling path? If `null` is allowed, is there a `case null`?
6. **Check flow scoping:** is the pattern variable declared and used in the right guard/arm? Are there redundant casts or out-of-scope accesses?
7. **Predict stdout for runtime values** by tracing through each case in exact order and condition.

## 12. Exercises and answers

**Question 1.** Given `Object x = "abc";` and `switch (x)` with `case String s -> s.length()`, what is the static type of `s`? Do you need to cast `x` before calling `s.length()`?

**Question 2.** Why does placing `case CharSequence cs` before `case String s` cause the compiler to reject the second branch? How do you fix it?

**Question 3.** Given `Object x = "";`, what do the following labels return and why?

~~~java
case String s when s.isEmpty() -> "empty";
case String s -> "non-empty";
default -> "other";
~~~

**Question 4.** If you move `case String s -> "non-empty"` before the guarded branch in Question 3, how does the compiler handle it?

**Question 5.** Given `switch (value)` on a selector of type `Object` with `case String s` and `default`, which branch is entered when `null` is passed in Java 21?

**Question 6.** Why is `return switch (value) { case Integer i -> "number"; };` invalid when `value` is `Object`? Name two valid ways to handle it.

**Question 7.** Can two labels `case String value ->` and `case Integer value ->` in separate arms reuse the name `value`? Can that pattern variable be used after the `switch`?

**Question 8.** `StringBuilder` implements `CharSequence`. Given a `CharSequence` selector holding `new StringBuilder("ab")`, is `case String s` or `case StringBuilder b` selected if they are placed in that order?

**Question 9.** Why is the type pattern `case Integer n` different from the constant label `case 1`? Is `case int n` standard Java 21 syntax?

**Question 10.** Given a `sealed Shape permits Circle, Square` type, why can a switch with only `case Circle c` and `case Square s` be exhaustive without `default`? Does that automatically make `null` match one of the labels?

### Answers

1. `s` has type `String` from the pattern; no cast is needed.
2. `CharSequence` covers every `String`, so the second branch is dominated. Place `String` before `CharSequence`.
3. Returns `"empty"`: the `String` type matches and the guard `isEmpty()` is `true`.
4. The guarded branch is shadowed; the compiler reports a dominated case.
5. Neither—not `default`; without `case null`, a pattern switch normally throws `NullPointerException`.
6. Not exhaustive because many other `Object` types exist. Add `default`, or add a pattern covering the remaining types (e.g., `case Object o`) in a valid order.
7. Yes, two independent case arms have separate scopes; that pattern variable cannot be used outside the `switch`.
8. `case String s` does not match `StringBuilder`; `case StringBuilder b` is selected.
9. `Integer n` checks the **runtime type and binds a variable**; `case 1` compares a constant value in a valid switch. Primitive type patterns like `case int n` are not yet a standard Java 21 feature.
10. The compiler knows the permitted subtypes of the sealed type and both `Circle` and `Square` are covered. `null` is still a separate case; to handle `null`, use `case null`.

## Official sources for reference

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): type patterns, guards, null, dominance, exhaustiveness, and examples.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): scope of the standard feature in JDK 21 and changes from preview.
- [Java Language Specification 21, `14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): case labels, pattern switch, dominance, exhaustiveness.
- [Java Language Specification 21, `15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): branch selection, exhaustiveness checking, and switch expression values.
- [Java Language Specification 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns and matching mechanics.
- [Java Language Specification 21, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): scope of pattern variables.
