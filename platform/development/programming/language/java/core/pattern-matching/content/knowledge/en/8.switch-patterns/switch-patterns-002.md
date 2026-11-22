# Pattern Matching in Switch Expressions (Java 21)

## 1. Why combine pattern matching with switch expressions?

When a reference-type variable can hold multiple kinds of objects, the traditional approach is usually an `if / else if` chain combined with `instanceof`. Each branch checks the type, casts (if using the older syntax), and then returns the corresponding result. As the number of branches grows, the code easily becomes verbose and it becomes harder to see whether all cases have been handled.

**Pattern matching in a `switch expression`** allows placing *type patterns* directly in `case` labels. Each branch both checks the type and can bind a variable of that exact type and **produce a value** for the entire `switch`. Combined with `when`, `case null`, record patterns, and `sealed` types, this style is especially useful for data classification and transformation problems with multiple variants.

For example, an input can be a `String`, an `Integer`, or another type:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

This is an **illustrative method placed inside a class**, using the standard syntax of **Java 21 and later**. The value of the selected branch is the value of the `switch expression`; the `return` keyword returns that result from the method.

Goals of this lesson: write syntactically valid `switch expressions` with patterns, understand case selection order and pattern variable scope, handle guards/null, prove *exhaustiveness*, distinguish `->` from `yield`, and know when this style is more appropriate than `if/else` or polymorphism.

## 2. Prerequisites and Java version

Before studying this, you should understand `instanceof`, how reference types work, `null`, traditional `switch`, and basic **switch expressions**. `switch expressions` became standard in Java 14; **pattern matching for `switch`** (type patterns, `when`, handling `null` in a pattern matching context) became standard in Java 21. **Record patterns** also became standard in Java 21.

| Feature | Java 17 | Java 21 |
| --- | --- | --- |
| `switch expression` with constant/enum labels and the `->` operator | Yes | Yes |
| `instanceof String text` | Yes | Yes |
| `case String text -> ...` in `switch` | Not yet standard | Yes |
| `case String s when ...` | Not yet standard | Yes |
| `case null` in pattern `switch` | Not yet standard | Yes |
| `case Point(int x, int y)` | Not yet standard | Yes |
| `sealed` interface/class | Yes | Yes |

The main examples in this lesson use **Java 21** and do not require `--enable-preview`. If you use a newer JDK but the project targets Java 17, `--release 17` still will not allow compiling Java 21 pattern `switch` syntax. Avoid taking an example that uses a preview feature from another version and assuming it is stable Java 21 syntax.

Check the environment:

```bash
java -version
javac -version
```

For standalone examples, use `javac --release 21 FileName.java` to ensure you do not accidentally depend on newer language features.

## 3. Syntax and semantics of a switch expression

Common structure:

```java
ResultType result = switch (selector) {
    case TypeA a -> expressionA;
    case TypeB b when conditionUsingB -> expressionB;
    case TypeB b -> expressionC;
    case null -> expressionForNull;
    default -> fallbackExpression;
};
```

This snippet is a **syntax template**, not standalone compilable Java: `ResultType`, `TypeA`, `TypeB`, and the expressions only represent actual types and logic.

Components to understand:

- `selector` is the expression evaluated to choose a branch; in Java 21, its type must belong to the types valid for `switch`. For examples that classify multiple object types, `Object` or an interface is a natural choice.
- `case String text` is a **type pattern**: if the selector matches `String`, it binds the pattern variable `text` of type `String`.
- `when` is a **guard**: a boolean expression checked after the pattern has matched; a false guard causes the search for a matching branch to continue.
- `->` marks the branch body. With an expression on the right-hand side, the result of that expression becomes the result of the `switch expression`.
- `case null` handles `null` input explicitly.
- `default` handles the remaining inputs in the corresponding context.
- The semicolon `;` after `}` belongs to the statement containing the `switch expression` (for example, an assignment or `return`).

**Switch expression vs. switch statement:** an expression always evaluates to **a single result** and must have valid paths that produce a result or throw an exception; a statement is typically used to perform actions and does not necessarily return a value. Do not confuse the two forms just because both are written `switch (...)`.

### Comparison with an if/else chain

```java
static String withoutSwitch(Object input) {
    if (input == null) {
        return "missing";
    } else if (input instanceof String text) {
        return "text: " + text;
    } else if (input instanceof Integer number) {
        return "integer: " + number;
    }
    return "other";
}
```

The result is equivalent to the `switch` example at the beginning of the lesson for the listed cases. `if/else` is still good if you only need one or two branches or have conditions not tied to data types. A `switch expression` is clearer when the same selector is classified against multiple patterns to produce a single result.

## 4. Complete runnable example: multiple type patterns, guards, null, and default

Save **all** of the following code to `SwitchExpressionPatterns21.java`:

```java
import java.util.List;

public class SwitchExpressionPatterns21 {

    static String describe(Object value) {
        return switch (value) {
            case null -> "missing";

            case String text when text.isBlank() -> "blank";

            case String text -> "text: " + text.strip();

            case Integer number when number < 0 -> "negative: " + number;

            case Integer number -> "integer: " + number;

            case List<?> list -> "list: " + list.size();

            default -> "other: " + value.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("   "));
        System.out.println(describe("  Java  "));
        System.out.println(describe(-2));
        System.out.println(describe(5));
        System.out.println(describe(List.of("A", "B")));
        System.out.println(describe(1.5));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 --release 21 SwitchExpressionPatterns21.java
java SwitchExpressionPatterns21
```

Exact output:

```text
missing
blank
text: Java
negative: -2
integer: 5
list: 2
other: Double
```

**What happens on each call?**

1. `describe(null)` enters `case null`, without relying on `default`.
2. `"   "` is a `String` and satisfies `text.isBlank()`, so it returns `blank`.
3. `"  Java  "` is a `String` but the `isBlank()` guard is false; the next `String` branch returns the `strip()`ped string.
4. `-2` is autoboxed to `Integer`; the `number < 0` guard is true.
5. `5` is a non-negative `Integer`; it falls into the unguarded `Integer` branch.
6. `List.of("A", "B")` matches `List<?>`; the code only checks that **the object is a List**, without attempting to match each element.
7. `1.5` is autoboxed to `Double` and matches the `default` branch. Because the `null` branch is separate, calling `value.getClass()` in `default` in this example is safe.

`List<?>` is the valid choice for matching a list with an unknown type parameter. With an `Object` variable, writing `case List<String> list` is invalid because the generic `String` type information cannot be fully checked at runtime. To process `String` elements, you need to check each element or use a data type with a stronger contract.

## 5. Pattern variables and per-branch scope

In `case String text -> ...`, the variable `text` is only meaningful where the pattern has matched. With a `when` guard, the variable is also usable inside that condition:

```java
static String classify(Object value) {
    return switch (value) {
        case String text when text.length() >= 5 -> "long: " + text;
        case String text -> "short: " + text;
        case Integer number -> "integer: " + number;
        case null -> "null";
        default -> "other";
    };
}
```

This is an illustrative Java 21 method. `text` in the guard of the first case is already a `String` when `length()` is called. The name `text` appearing again in the second case is a pattern variable of **another case**, not a value retained from the first branch. A pattern variable in the `Integer` case does not automatically exist in the `String` case.

Because each `->` branch has its own control flow, this style has no *fall-through* into the next case body like traditional colon-style `switch` statements. Once a `->` branch is selected and completes, the `switch expression` completes with that branch's value.

Note: `when` is not an `if` that always runs before all patterns. **The pattern must match first**, and only then is the guard evaluated. If a guard has side effects, branch selection becomes hard to understand and hard to test; use pure, fast conditions that do not mutate state.

## 6. Case ordering and dominance errors

Java checks whether an earlier case **covers all** the values that a later case intends to accept. When that happens, the later case is *dominated* (shadowed) and is normally a compile-time error.

### Incorrect example: general branch before specific branch

```java
// INTENTIONALLY WRONG: the String case is already shadowed by the CharSequence case.
return switch (value) {
    case CharSequence sequence -> sequence.toString();
    case String text -> text; // Dominated.
    default -> "other";
};
```

This is an illustrative code snippet requiring a `value` variable inside a method. Because `String` implements `CharSequence`, the earlier branch can match every non-null `String` object, so the later branch has no chance of ever being selected.

Fix by ordering **specific first, general last**:

```java
return switch (value) {
    case String text -> "String: " + text;
    case CharSequence sequence -> "Other text: " + sequence;
    default -> "other";
};
```

This is also an illustrative expression inside a method and assumes the selector has an appropriate type, such as a non-null `Object value`. For inputs that can be `null`, design a separate `case null` as in the complete examples.

### Incorrect example: guarded case placed after an unguarded case of the same type

```java
// INTENTIONALLY WRONG: the first case already matches every non-null String.
return switch (value) {
    case String text -> "any text";
    case String text when text.isBlank() -> "blank"; // Dominated.
    default -> "other";
};
```

Fix by placing the guarded branch first:

```java
return switch (value) {
    case String text when text.isBlank() -> "blank";
    case String text -> "any text";
    default -> "other";
};
```

In general, the compiler **does not prove subsumption relationships between arbitrary guard expressions**; do not rely on complex guard ordering without writing tests. A maintainable rule is: special cases with guards first, catch-all branches of the same type last.

## 7. Handling null accurately in switch expressions

A dangerous misconception is thinking that `default` includes `null`. For a typical pattern `switch` in Java 21, if the selector is `null` without an appropriate `null`-handling branch, Java throws `NullPointerException`; `default` does not automatically accept `null`.

```java
static String unsafe(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

This is an illustrative Java 21 method: `unsafe(null)` throws `NullPointerException`, rather than returning `other`. Use an explicit branch when `null` is a valid input:

```java
static String safe(Object value) {
    return switch (value) {
        case null -> "no input";
        case String text -> "text: " + text;
        default -> "other";
    };
}
```

If `null` **violates the input contract**, you can reject it explicitly:

```java
static String requireInput(Object value) {
    return switch (value) {
        case null -> throw new IllegalArgumentException("value is required");
        case String text -> text;
        default -> "unsupported";
    };
}
```

The three examples above are standalone methods that can be placed in a Java 21 class. `throw` is valid in a `->` branch and makes clear that this path **does not return a result value** because it intentionally reports an error.

You should distinguish `null` from blank strings and unsupported types: `null` is the absence of an object, `"  "` is still a `String` object, and `Double` is an existing object of a different type. These cases do not necessarily share the same business handling.

## 8. Value-producing branches: ->, blocks, and yield

In a `switch expression`, a `->` branch can be:

- **An expression**, in which case the expression's value becomes the result of the `switch`.
- **A block** `{ ... }`, inside which `yield value;` is used to return a value for the `switch expression`.
- **A `throw` statement**, when this branch needs to throw an exception.

Example using a block:

```java
static String summary(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> {
            String normalized = text.strip();
            int length = normalized.length();
            yield "length: " + length;
        }
        default -> "other";
    };
}
```

This is a syntactically complete method that can be placed in a Java 21 class. Calling `summary("  Java  ")` returns `"length: 4"`.

**Why not use `return` inside the block?** In a `switch expression`, `yield` provides the value for the enclosing `switch` expression. `return` is an operation that returns from the **method**, not a replacement for `yield` here. If a block has a path that completes normally without providing an appropriate value, the compiler will reject it.

`yield` is not how you return a value from a regular `switch statement`. When you want to produce a value and assign it to a variable or return it from a method, prefer a `switch expression` and `yield` in the right place.

### Comparison with the colon form

Java also allows `switch expressions` using colon-style statement groups `case ...:`, using `yield` to produce a value. However, with pattern matching and independent branches, the `->` form is usually easier to read and less prone to fall-through bugs. Do not mix different case label styles within the same `switch` block.

## 9. Exhaustiveness: a switch expression must cover all possible cases

A `switch expression` must not allow a valid input to fall past all branches without a result. The compiler enforces **exhaustiveness** checking. With an `Object` selector or an open type domain, the simple way is to have `default` handle the rest:

```java
static String openWorld(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> s;
        case Integer i -> i.toString();
        default -> "unsupported";
    };
}
```

`Object` types other than `String` and `Integer` can still appear; `default` makes the expression exhaustive. The `null` branch has its own independent meaning.

With a **sealed interface/class**, Java knows the set of permitted subtypes. If you list all variants completely, a `switch expression` can be exhaustive **without needing `default`**. This is useful because when a new variant is added, the compiler can point out where handling must be updated.

### Complete example: sealed + record pattern + switch expression

Save all of the following content to `ExhaustiveSwitchExample21.java`:

```java
public class ExhaustiveSwitchExample21 {

    sealed interface Expr permits Literal, Add {}

    record Literal(int value) implements Expr {}

    record Add(Expr left, Expr right) implements Expr {}

    static int evaluate(Expr expr) {
        return switch (expr) {
            case null ->
                    throw new IllegalArgumentException("expr is required");

            case Literal(int value) ->
                    value;

            case Add(Expr left, Expr right) ->
                    evaluate(left) + evaluate(right);
        };
    }

    public static void main(String[] args) {
        Expr expression = new Add(new Literal(2), new Literal(3));
        System.out.println(evaluate(expression));
        System.out.println(evaluate(new Literal(-5)));

        try {
            evaluate(null);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 21 ExhaustiveSwitchExample21.java
java ExhaustiveSwitchExample21
```

Exact output:

```text
5
-5
expr is required
```

**Explanation:**

- `Expr` is a `sealed` interface that permits only two direct subtypes: `Literal` and `Add`.
- `case Literal(int value)` is a record pattern: it matches the `Literal` record and declares the component variable `value`.
- `case Add(Expr left, Expr right)` extracts two components of type `Expr` for recursive evaluation.
- The two cases above cover the variants permitted by `Expr`. `case null` makes the input contract explicit and intentionally throws an error.
- There is no `default`: if you later modify the model to add `Multiply` as a permitted subtype, the compiler can force you to update the `switch` expression for the new variant.

The program allows creating `new Add(null, new Literal(1))` because the record does not automatically block a null component. When recursion reaches `evaluate(null)`, the `case null` branch throws the defined error. If the model **does not accept null components**, a better approach is to check in `Add`'s constructor (for example using `Objects.requireNonNull`) to enforce the invariant when data is created. Pattern matching does not automatically solve nullable contracts for every nested structure.

**Guards and exhaustiveness:** A branch `case Literal(int v) when v > 0` only handles part of the `Literal` values. If a branch covering the rest (such as `case Literal(int v)`) is missing, the compiler may consider the `switch expression` not exhaustive. Do not use a guard as a substitute for handling the remaining cases.

## 10. When is a switch expression appropriate, and when is it not?

| Situation | Reasonable choice |
| --- | --- |
| A single input value is classified by multiple types and needs to return one result | Pattern matching in a `switch expression` |
| Only a single short type condition | `if (value instanceof Type x)` may be simpler |
| A branch has sub-rules (blank, negative, overdue...) | Type pattern + `when`; place special cases before the general case |
| Closed set of variants, want the compiler to detect missing branches when extending | `sealed` + exhaustive `switch expression` |
| Data is a record and components are needed for computation | Record pattern in `case` |
| Multiple places in the project repeat the same type-based `switch` to invoke object behavior | Consider moving behavior to an interface/polymorphic method |
| Primary task is performing multiple side effects with no unified result | `switch statement` or extracting methods may be more appropriate |

Do not force all logic into a `switch expression` just for brevity. If many cases are long, repeat calculations, or have many side effects, consider extracting the processing into named methods. The value returned by each branch should have the same meaning in the business domain.

## 11. Common mistakes

### Mistake 1: using pattern switch when still targeting Java 17

`case String s -> ...` in the lesson's examples is standard Java 21 syntax. Java 17 projects can use `instanceof String s` or `switch expressions` on constants/enums, but do not yet have these pattern cases as a standard feature.

### Mistake 2: general case shadowing a special case

Placing `case CharSequence cs` before `case String s`, or placing an unguarded `case String s` before `case String s when ...`, leads to a dominance error. Order narrower-scope cases first.

### Mistake 3: thinking default automatically handles null

In a typical pattern switch, a `null` selector does not enter `default` like another data type. Write `case null` if `null` is accepted, or explicitly throw an error at the boundary.

### Mistake 4: forgetting expression exhaustiveness

A `switch expression` on `Object` cannot only have a case for `String` if other types can still appear. You need `default` or another valid way to cover all cases. With a `sealed` type, the compiler can prove all subtypes are covered.

### Mistake 5: block not yielding a value

`case String s -> { System.out.println(s); }` cannot be a normally-completing branch of a value-returning `switch expression` because the block lacks `yield`. If the goal is to log and return the string, use `yield s;` after the print statement or separate the side effect beforehand.

### Mistake 6: confusing a guard variable with a variable declared outside

In `case String s when s.isBlank()`, `s` is present because the type pattern matched. It does not automatically exist in every case or after the entire expression.

### Mistake 7: incorrect generic matching

`case List<String> xs` on an `Object` selector cannot check the type parameter at runtime; replace it with `case List<?> xs`, and then check elements according to your contract.

### Mistake 8: thinking pattern matching always replaces polymorphism

For objects that own independent behavior, an interface with a shared method often lets you add variants without modifying many scattered `switch` statements. Pattern `switch` shines when **expressing the set of handling branches in one place is what you intentionally want to model**.

### Mistake 9: guards with side effects

`when` may be evaluated while searching for a matching case. Conditions with side effects or that depend on mutable state easily make logic hard to verify; prefer pure, readable guards.

## 12. Practice exercises with test cases

**Exercise 1 — Data classifier:** Create `describe(Object x)` using a `switch expression` supporting `null`, blank strings, normal strings, negative integers, non-negative integers, `List<?>`, and other types. Use the inputs from `SwitchExpressionPatterns21`, and predict each line before running.

**Exercise 2 — Writing a block branch with yield:** Convert the regular `String` branch into a block. Compute `normalized` once, add a calculation such as string length, and use `yield` to return the result. Explain why `return` is not used inside this block.

**Exercise 3 — Detecting dominance:** Try moving `case CharSequence cs` before `case String s`. Record the compile error, explain the type relationship, and then fix the order.

**Exercise 4 — Distinguishing null and unsupported types:** Remove `case null` from a switch that has `default` and call it with `null`. Observe the behavior and fix it according to a `MISSING_INPUT` contract.

**Exercise 5 — Closed type hierarchy:** Extend `Expr` in the example to `Literal`, `Add`, `Multiply`. Add `record Multiply(Expr left, Expr right) implements Expr` and update `permits`/cases as needed. Observe the error before adding the new case, then implement multiplication.

**Exercise 6 — Checking nullable components:** Try `evaluate(new Add(null, new Literal(2)))` and explain why the method rejects it. Then add a non-null check in the record constructor to prevent creating invalid state from the start.

### Suggested test case table

| Input | Expected result | Handling branch |
| --- | --- | --- |
| `null` | `missing` | `case null` |
| `"   "` | `blank` | `String` with `isBlank` guard |
| `"  Java  "` | `text: Java` | Regular `String` |
| `-2` | `negative: -2` | `Integer` with guard |
| `5` | `integer: 5` | Regular `Integer` |
| `List.of("A", "B")` | `list: 2` | `List<?>` |
| `1.5` | `other: Double` | `default` |
| `new Add(new Literal(2), new Literal(3))` | `5` | Record patterns `Add` and `Literal` |
| `new Literal(-5)` | `-5` | Record pattern `Literal` |
| `evaluate(null)` in the sealed example | Throws `IllegalArgumentException("expr is required")` | `case null -> throw` |

**Self-assessment:** You should be able to explain which inputs each case accepts, why guards are checked after matching the pattern, the placement and meaning of `case null`, the conditions for a switch expression to be exhaustive, when to use `yield`, and why a sealed hierarchy helps detect missing branches.

## 13. Authoritative references

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type patterns, `when` guards, `null`, dominance, and exhaustiveness in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): matching record components, including nested record patterns.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): foundations of type patterns and pattern variables.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): `switch` as an expression, the `->` arrow, values, and `yield`.
- [Java Language Specification, Java SE 21 — Switch Expressions `15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): formal rules for switch expressions.
- [Java Language Specification, Java SE 21 — Switch Statements `14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): rules for case labels, matching, dominance, and handling in switch.

You should practice on **JDK 21 or later**, recompile with `--release 21`, deliberately trigger compile errors for dominance/missing branches, and add tests before applying this in a project.
