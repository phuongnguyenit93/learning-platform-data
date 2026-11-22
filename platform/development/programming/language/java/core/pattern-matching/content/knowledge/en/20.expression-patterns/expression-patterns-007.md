# Using Pattern Expressions in `return` (Java 21)

## 1. Objectives and Scope

In Java, **`return`** returns the result of an expression whose type is compatible with the declared return type. Pattern matching lets an expression determine whether a value matches an expected type or structure and, if it does, extract pattern variables for processing. Combining these two mechanisms allows you to write concise, readable methods with minimal manual casting.

This lesson explains how to use pattern matching **inside return expressions** through three main forms:

1. `return value instanceof Type variable;` or `return value instanceof Record(...);` to return a `boolean` result.
2. `return condition ? resultIfMatched : resultIfNotMatched;` and `return pattern && additionalCondition;` to compute a value based on pattern variables within their valid scope.
3. `return switch (value) { case Pattern -> result; ... };` to return a result based on multiple patterns, record patterns, and `when` clauses.

In addition, there is the **guard clause**: using `if` with a pattern, returning early when it does not match, and continuing to process the pattern variable afterward.

After this lesson, you will understand how to perform type checks, **flow scoping** of pattern variables, `null` handling, exhaustiveness of `switch` branches, the difference between `return` and `yield`, and how to avoid compilation errors when combining `&&`/`||`.

**Version requirements:** Type patterns for `instanceof` have been a standard feature since Java 16 (JEP 394). Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) became standard features in **Java 21**. The complete examples below compile with `javac --release 21`, without needing `--enable-preview`.

## 2. Returning the `boolean` of Pattern Matching Directly

The `instanceof` operator evaluates to a `boolean` value, so it can be used directly in a method returning `boolean`:

```java
static boolean isText(Object value) {
    return value instanceof String;
}
```

In practice, a type pattern lets you both check the type and bind a variable to apply additional constraints:

```java
static boolean isNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

If `value` is not a `String` (including `null`), the `instanceof` side returns `false`; because `&&` short-circuits, `text.isBlank()` does not run. If `value` matches `String`, `text` is bound and the call is safe.

For a record with multiple components, you can validate them directly in the `return` expression:

```java
record User(String name, int age) {}

static boolean isAdult(Object value) {
    return value instanceof User(var name, var age)
            && name != null
            && !name.isBlank()
            && age >= 18;
}
```

**Explanation:** `User(var name, var age)` checks that the object is a `User` and extracts both components via accessors. With `var name`, a `null` value can still be bound, so checking `name != null` is necessary before calling `isBlank()`. If you use `User(String name, int age)`, a `null` `name` component causes the nested type pattern `String name` not to match; this is the practical difference between `var` and a type pattern.

Case table:

| Input | `isAdult` |
| --- | --- |
| `new User("An", 21)` | `true` |
| `new User("An", 16)` | `false` |
| `new User("", 30)` | `false` |
| `new User(null, 30)` | `false` |
| `null` or a non-`User` object | `false` |

A **pattern** is not a standalone value that can be returned directly. For example, `return String s;` makes no sense; the expression must be `value instanceof String s`, a valid boolean combination, a ternary operator, or a `switch` expression.

## 3. Combining Negated Expressions in `return`

When a rule needs to identify an **invalid** case, you can negate the match:

```java
static boolean invalidUser(Object value) {
    return !(value instanceof User(var name, var age))
            || name == null
            || name.isBlank()
            || age < 18;
}
```

This pattern is valid with respect to pattern variable scope thanks to `||`:

- If `!(...)` is true, the object does not match `User`; the expression returns `true` immediately, and the remaining operands do not run.
- If `!(...)` is false, the `User` match succeeded; `name` and `age` exist and can be read in the right-hand operands.
- When `name == null` is true, `name.isBlank()` is skipped, avoiding a `NullPointerException`.

This is equivalent in intent to the `!isAdult(value)` rule in the example above, while clearly demonstrating **flow scoping** when negating a pattern.

Avoid the following two incorrect forms:

```java
// Invalid: the right-hand side of || can execute when the String pattern fails.
return value instanceof String text || text.isBlank();

// Invalid: the right-hand side of && only executes when the String pattern fails.
return !(value instanceof String text) && text.isBlank();
```

The two lines above are **intentional compilation error examples**, placed in the context of a method returning `boolean`. You cannot use the variable `text` in a position where the compiler has not guaranteed that the pattern matched.

Rule comparison:

| `return` Expression | Valid? | Reason |
| --- | --- | --- |
| `return obj instanceof String s && !s.isBlank();` | Yes | `s` is in scope when the right-hand side is evaluated |
| `return !(obj instanceof String s) &#124;&#124; s.isBlank();` | Yes | The right-hand side runs when the negation is false, meaning the match succeeded |
| `return obj instanceof String s &#124;&#124; s.isBlank();` | No | The right-hand side runs when the match fails |
| `return !(obj instanceof String s) && s.isBlank();` | No | The right-hand side runs when the match fails |

## 4. Using Patterns in a Ternary Operator to Return a Value

The conditional operator `condition ? trueExpression : falseExpression` is an **expression**, so it can follow `return`:

```java
static String uppercase(Object value) {
    return value instanceof String text
            ? text.toUpperCase(java.util.Locale.ROOT)
            : "not a string";
}
```

In the `?` branch, the pattern `String text` has definitely matched, so `text.toUpperCase(...)` can be called. The `:` branch handles all non-`String` values, including `null`, without casting.

Record patterns work similarly:

```java
record Point(int x, int y) {}

static String pointLabel(Object value) {
    return value instanceof Point(var x, var y)
            ? "point=" + x + "," + y
            : "not a point";
}
```

For `new Point(2, 5)`, the method returns `"point=2,5"`. For `"hello"`, the result is `"not a point"`.

Both the `?` and `:` branches must produce results compatible with the method's return type; in the examples above, both are `String`. If you need to check multiple cases or nest multiple ternary operators, a `switch` expression is usually easier to read and maintain.

### Do Not Overuse Nested Ternaries

Something like `return a ? x : b ? y : z;` can be valid, but when expressions contain multiple record patterns and conditions, it is easy to get the order wrong or hard to reason about `null`. Use `switch` when you genuinely have multiple branches for different data shapes.

## 5. Guard Clauses: Combining `return` with Flow Scoping

Sometimes a negated condition helps handle the failure case right at the start of a method:

```java
static String labelOrMissing(Object value) {
    if (!(value instanceof String label)) {
        return "missing";
    }
    return "label=" + label.trim();
}
```

Key point: the variable `label` **remains in scope after the `if` statement**. The reason is that if the negated branch is true, the method has already returned; every execution path reaching the final `return` proves that `value instanceof String label` succeeded.

Checking a record:

```java
static String nonNegativePoint(Object value) {
    if (!(value instanceof Point(var x, var y))) {
        return "not a point";
    }
    if (x < 0 || y < 0) {
        return "negative coordinate";
    }
    return x + "," + y;
}
```

This is a standalone method assuming `Point` is declared as in the example above. It distinguishes **not matching the record** from **matching the record but failing data constraints**. `Point(-1, 2)` still matches `Point(var x, var y)`; it is only rejected at the coordinate check.

With an `if` that does not exit early, the pattern variable is not automatically in scope after both branches:

```java
if (!(value instanceof String label)) {
    System.out.println("not string");
} else {
    System.out.println(label.length()); // valid in else
}
// Here you cannot unconditionally use label if the if branch continues.
```

**Rule:** Pattern variable scope depends on execution paths along which the compiler can prove the pattern matched, not on the textual position of the `return` keyword.

## 6. Returning the Result of a `switch` Expression Directly

Java 21 allows `switch` to be an expression that produces a value. Pattern matching combined with record patterns makes writing a method that returns a `String` clear and concise:

```java
static String describe(Object value) {
    return switch (value) {
        case Point(var x, var y) when x == y -> "diagonal=" + x;
        case Point(var x, var y) -> "point=" + x + "," + y;
        case String s when !s.isBlank() -> "text=" + s.trim();
        case String s -> "blank string";
        case null -> "null";
        default -> "other";
    };
}
```

Key points to note:

1. `return switch (...) { ... };` is a `return` statement wrapping a **switch expression**. The `;` terminates the statement.
2. Each branch using `->` produces a `String` value compatible with the return type.
3. `case Point(var x, var y)` both checks the record and extracts its components.
4. `when x == y` is a guard condition, evaluated after `Point` has matched. The more specific `Point` branch is placed before the general one.
5. `case String s when !s.isBlank()` checks for a non-empty/non-whitespace-only string; then `case String s` covers the remaining strings.
6. `case null` handles a `null` input; without this branch, switching on a `null` reference can throw a `NullPointerException`. `default` does not automatically handle `null`.
7. `default` makes the expression exhaustive for objects of types other than those listed.

**Difference from a `switch` statement:** a `switch` expression has a **result** and must be exhaustive over all possible cases for the selector type. All branches must also yield values of a compatible type. A `switch` statement may simply perform side effects without producing a value for `return`.

Usage example:

```java
System.out.println(describe(new Point(3, 3))); // diagonal=3
System.out.println(describe(new Point(2, 4))); // point=2,4
System.out.println(describe(" hello "));        // text=hello
System.out.println(describe(null));             // null
```

## 7. Pattern `switch` with a `sealed` Type: Exhaustive Without `default`

When the input has a sealed type with explicitly declared subtypes, the compiler can verify exhaustiveness based on the list of permitted subclasses:

```java
sealed interface Message permits Text, Location, Unknown {}

record Text(String value) implements Message {}
record Location(int x, int y) implements Message {}
record Unknown() implements Message {}

static String classify(Message message) {
    return switch (message) {
        case null -> "null message";
        case Text(var text) when text != null && !text.isBlank() ->
                "text=" + text.trim();
        case Text(var text) -> "empty text";
        case Location(var x, var y) -> "location=" + x + "," + y;
        case Unknown u -> "unknown";
    };
}
```

In the case above, the `Text`, `Location`, and `Unknown` branches cover all subtypes of `Message`. The subsequent `case Text(var text)` covers both `Text(null)` and blank strings. `case null` has its own meaning; `null` is **not** a subtype of `Message`.

Omitting `default` is still valid because the compiler proves that the `switch` expression covers every permitted type. If you later change the set of subtypes in the sealed hierarchy, the source code must be recompiled and rechecked to maintain exhaustiveness. In compiled Java programs, mismatches caused by changing a hierarchy between compilations can cause runtime errors; keep deployed components on the same version.

The advantage of not arbitrarily adding `default` for a sealed hierarchy is that the compiler can report missing branches when the type system changes, rather than silently routing new objects into a `default` branch.

## 8. When a Branch Needs Multiple Statements: Use `yield`

A switch expression branch can use a `{ ... }` block to compute a value and then **`yield`**:

```java
static String explain(Object value) {
    return switch (value) {
        case Point(var x, var y) when x < 0 || y < 0 -> {
            String field = x < 0 ? "x" : "y";
            yield "negative " + field;
        }
        case Point(var x, var y) -> "valid point";
        case null -> "null";
        default -> "other";
    };
}
```

In the block branch, `yield "negative " + field;` provides **the value of the switch expression**. Once the `switch` expression finishes, the outer `return` returns that value from the method.

Do not write `return` **inside a switch expression block** as a replacement for `yield`:

```java
// INTENTIONALLY INVALID — does not compile.
return switch (value) {
    case String s -> { return s.trim(); }
    default -> "other";
};
```

The example above illustrates the error `attempt to return out of a switch expression`. The correct way is:

```java
return switch (value) {
    case String s -> {
        String normalized = s.trim();
        yield normalized;
    }
    default -> "other";
};
```

A short expression-style branch can be written as `case String s -> s.trim();`. Only use a block and `yield` when multiple computation steps, local variables, or extra checks genuinely make the code clearer.

## 9. Complete Example Running on Java 21

Create the file **`ReturnPatternDemo.java`**. This program exercises `instanceof`/record patterns in `return`, the ternary operator, guard clauses, and `switch` expressions with `when` and `yield`.

```java
import java.util.Locale;

public class ReturnPatternDemo {
    record User(String name, int age) {}
    record Point(int x, int y) {}

    sealed interface Message permits Text, Location, Unknown {}
    record Text(String value) implements Message {}
    record Location(int x, int y) implements Message {}
    record Unknown() implements Message {}

    static boolean isAdult(Object value) {
        return value instanceof User(var name, var age)
                && name != null && !name.isBlank() && age >= 18;
    }

    static boolean invalidUser(Object value) {
        return !(value instanceof User(var name, var age))
                || name == null || name.isBlank() || age < 18;
    }

    static String pointLabel(Object value) {
        return value instanceof Point(var x, var y)
                ? "point=" + x + "," + y
                : "not a point";
    }

    static String uppercase(Object value) {
        return value instanceof String text
                ? text.toUpperCase(Locale.ROOT)
                : "not a string";
    }

    static String labelOrMissing(Object value) {
        if (!(value instanceof String label)) {
            return "missing";
        }
        return "label=" + label.trim();
    }

    static String describe(Object value) {
        return switch (value) {
            case Point(var x, var y) when x == y -> "diagonal=" + x;
            case Point(var x, var y) -> "point=" + x + "," + y;
            case String s when !s.isBlank() -> "text=" + s.trim();
            case String s -> "blank string";
            case null -> "null";
            default -> "other";
        };
    }

    static String classify(Message message) {
        return switch (message) {
            case null -> "null message";
            case Text(var text) when text != null && !text.isBlank() ->
                    "text=" + text.trim();
            case Text(var text) -> "empty text";
            case Location(var x, var y) -> "location=" + x + "," + y;
            case Unknown u -> "unknown";
        };
    }

    static String explain(Object value) {
        return switch (value) {
            case Point(var x, var y) when x < 0 || y < 0 -> {
                String field = x < 0 ? "x" : "y";
                yield "negative " + field;
            }
            case Point(var x, var y) -> "valid point";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println("adult=" + isAdult(new User("An", 21)));
        System.out.println("adult=" + isAdult(new User(null, 30)));
        System.out.println("invalid=" + invalidUser(null));
        System.out.println("invalid=" + invalidUser(new User("Binh", 20)));
        System.out.println(pointLabel(new Point(2, 5)));
        System.out.println(pointLabel("plain text"));
        System.out.println(uppercase("java"));
        System.out.println(uppercase(10));
        System.out.println(labelOrMissing("  ID-7  "));
        System.out.println(labelOrMissing(null));
        System.out.println(describe(new Point(3, 3)));
        System.out.println(describe(new Point(2, 4)));
        System.out.println(describe(" hello "));
        System.out.println(describe(""));
        System.out.println(describe(null));
        System.out.println(classify(new Text(" Hello ")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Location(7, 8)));
        System.out.println(classify(new Unknown()));
        System.out.println(classify(null));
        System.out.println(explain(new Point(-1, 4)));
        System.out.println(explain(new Point(1, 4)));
    }
}
```

Run in the directory containing the file with **JDK 21 or later**:

```bash
javac --release 21 ReturnPatternDemo.java
java ReturnPatternDemo
```

**Expected output (stdout):**

```text
adult=true
adult=false
invalid=true
invalid=false
point=2,5
not a point
JAVA
not a string
label=ID-7
missing
diagonal=3
point=2,4
text=hello
blank string
null
text=Hello
empty text
location=7,8
unknown
null message
negative x
valid point
```

Verification notes:

- The two `isAdult` calls differ on the `name != null` component check; `return` short-circuits safely.
- `invalidUser(null)` returns `true` immediately at `!(instanceof ...)`, so unbound pattern variables are never read.
- `pointLabel` and `uppercase` use the ternary operator: the `?` branch runs only if the pattern matches.
- `labelOrMissing` demonstrates that a pattern variable remains in scope after an `if` statement that returns when the match fails.
- `describe` places specific branches before general ones; `null` is handled explicitly.
- `classify` demonstrates that a sealed hierarchy can use an exhaustive `return switch` without `default`; `Text(" Hello ")` and `Text(null)` take different branches.
- `explain` uses `yield` inside a block branch to produce the value returned from the method.

## 10. Scope, Type Safety, and Code Readability

### 10.1. Pattern Variables Are Not Like Variables Declared at the Top of a Method

`String s` in `value instanceof String s` is a **pattern variable**. Its scope is open only along paths where the compiler determines the match succeeded. When `return` has multiple operators, check the short-circuit logic instead of guessing based on position on the same line.

To keep code readable, each return expression should express a clear rule. For example, if validation has too many conditions, consider guard clauses with distinct errors, or helper methods such as `isValidName(...)` and `isAllowedAge(...)` instead of an overly long `&&` chain.

### 10.2. `null` and a `null` Record Component Are Two Different Cases

- `null instanceof User(var name, var age)` returns `false` because the outer object is `null`.
- `new User(null, 30) instanceof User(var name, var age)` can match; `name` is bound to `null`.
- `new User(null, 30) instanceof User(String name, int age)` does not match on the `String name` component because a type pattern does not match `null`.
- In a `switch` expression, `case null` handles a `null` selector object. The pattern `Text(var text)` can match a `Text` record whose `text` component is `null`.

### 10.3. `return switch` Must Be Exhaustive and Yield Compatible Types

If the selector has type `Object`, a few record cases cannot cover everything by default; `default` is usually required. If the selector is a sealed type, the compiler can verify the set of subtypes and require handling every branch when the hierarchy is extended. Add `null` handling when you want to return a result rather than throw `NullPointerException`.

Every branch returns the same kind of value compatible with the declared return type. In the example code, every branch of `describe`, `classify`, and `explain` produces a `String`; no branch just logs and forgets to produce a return value.

### 10.4. A Record Pattern Only Reads Structure; It Does Not Copy Values

When a return expression uses `record Box(List<String> items)` or a record containing an array, matching/deconstructing components does not automatically create a defensive copy or make the data immutable. If you return a `List` extracted from a pattern, the caller may receive the same mutable reference returned by the accessor. Decide on immutability policies in the data type design; only use `List.copyOf` when you want an unmodifiable snapshot of the container and understand that it is not a deep copy.

### 10.5. Return Values Should Be Consistent with the API Goal

If a method simply evaluates a predicate, returning a `boolean` with `instanceof`/`&&` can be cleaner than a long `if/else`. If the method needs several different return cases, a `switch` expression is usually a good fit. If validation requires detailed error messages, guard clauses help control errors, and multiple separate `return` statements can be clearer than one complex expression.

## 11. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using `s` on the right-hand side of `||` after `value instanceof String s` | The right-hand side only runs when the match fails | Use `&&` with a positive pattern, or negate the pattern and use `||` |
| Using `s` on the right-hand side of `&&` after `!(value instanceof String s)` | The right-hand side runs when the pattern fails | Change the logic to `!(...) &#124;&#124; ...` or a guard clause |
| Writing `return String s;` | A pattern is not a standalone return value | Return a boolean from `instanceof`, a ternary result, or a `switch` |
| Forgetting `null` in `return switch` | `null` does not match type/record patterns | Add `case null` when the API should handle `null` |
| Missing the final branch of a switch expression | A switch expression must be exhaustive | Add `default` when appropriate or list all subtypes of the sealed type |
| Placing a general pattern before a pattern with `when` | The specific branch can be dominated | Place specialized branches before general branches |
| Using `return` inside a `case -> { ... }` block of a switch expression | A switch expression block produces its value via `yield` | Use `yield expression;` |
| Assuming `User(var name, ...)` guarantees `name != null` | `var` can bind a `null` value | Check `name != null` before calling methods on it |
| Returning a mutable component extracted from a record directly | Record patterns do not copy or freeze references | Design defensive copies when needed |
| Using record patterns on JDK 17 and hitting syntax errors | Record patterns are only standard from JDK 21 | Compile and run on JDK 21+ |

## 12. Self-Check Questions

**1.** Why does `return value instanceof String s && !s.isBlank();` not throw a `NullPointerException` when `value == null`?  
*Answer:* `instanceof` returns `false`, so the right-hand side of `&&` is not evaluated.

**2.** Does the expression `return !(value instanceof String s) || s.isBlank();` compile?  
*Answer:* Yes. `s.isBlank()` only runs when the negation is false, meaning `String s` has matched.

**3.** Why is `return value instanceof String s || s.isBlank();` invalid?  
*Answer:* The right-hand side runs when `instanceof` is false, at which point `s` has no valid pattern value.

**4.** In `return value instanceof Point(var x, var y) ? x + y : -1;`, which branch is allowed to use `x` and `y`?  
*Answer:* The branch after `?` (the match-succeeded case); the branch after `:` cannot assume the pattern matched.

**5.** Why is `if (!(value instanceof String s)) return "missing"; return s.trim();` valid inside a method returning `String`?  
*Answer:* The non-matching branch exits early; the remainder only executes when `s` is bound.

**6.** When is `yield` needed in `return switch`?  
*Answer:* When a switch expression branch is a block and needs to supply the block's result to the switch expression. `yield` differs from `return` in its control scope.

**7.** Why can a sealed `Message` omit `default`?  
*Answer:* The compiler knows the permitted subtypes and can prove that all of them are handled by the cases.

**8.** Does `case Text(var value)` match `new Text(null)`?  
*Answer:* Yes. `var` can bind a `null` component, whereas a nested type pattern like `String value` does not match `null`.

## References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification SE 21 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Java Language Specification SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
