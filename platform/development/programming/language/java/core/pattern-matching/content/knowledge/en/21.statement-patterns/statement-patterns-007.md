# Early Return After Matching in Java Pattern Matching

**Early return after matching** is a technique for exiting a method as soon as a **pattern** confirms that the input value belongs to a case to be handled, or when a pattern **does not match** and the method cannot continue. This technique is especially useful when handling an `Object` with multiple runtime types, validating input data, deconstructing a `record`, or avoiding nested `else` branches.

In the topic **Java Core Pattern Matching → Patterns in Statements**, two forms should be distinguished:

1. **Match succeeds, then return immediately**: `if (value instanceof String text) { return ...; }`.
2. **Match fails, then return early (guard clause)**: `if (!(value instanceof String text)) { return ...; }`, then continue using `text` in the rest of the method.

Since **Java 16**, pattern matching with `instanceof` has been a standard feature (JEP 394). **Record patterns** and **pattern matching for switch** became standard features in **Java 21** (JEP 440, JEP 441). The complete examples below use **Java 21 or later**, without requiring preview features to be enabled.

## 1. Returning Immediately When an `instanceof` Pattern Matches

A type pattern has the syntax `value instanceof Type variable`. If `value` is an object of a matching `Type`, Java binds the value to `variable` in the matched branch.

```java
// Illustrative snippet: 'value' is already declared as Object.
if (value instanceof String text) {
    return "Text: " + text.trim();
}
if (value instanceof Integer number) {
    return "Number: " + number;
}
return "Unsupported";
```

Execution order:

- Java checks `value instanceof String text`. If true, `text` has type `String`; the method returns the first result **immediately**. The checks below do not run.
- If it does not match `String`, Java tries `Integer number`. If true, it returns the second result.
- If neither matches, the final `return "Unsupported";` statement executes.

Compared to `if/else if/else`, early return branches make it clear that each handled case **terminates the method**, so there is no need to wrap the remaining code in `else`. This approach should only be applied when ending early matches the business logic.

**Note:** `instanceof` returns `false` when the input value is `null`. Therefore, with `value == null`, both patterns above do not match and execution reaches the final branch.

## 2. Guard Clause: Return When Not Matching, Use the Variable Afterward

A very useful pattern is to **negate `instanceof`**, return in the failure branch, and then write the main flow at the same indentation level:

```java
// Snippet inside a method returning String.
// 'value' has type Object.
if (!(value instanceof String text)) {
    return "Not a string";
}

// Valid: to reach here, the String text pattern must have matched.
return "Length: " + text.length();
```

Why is `text` still usable **after** the `if` statement?

- If the pattern **does not match**, the condition `!(...)` is true and the `if` branch executes `return`, terminating the method.
- If execution flow **continues past** the `if` statement, that proves `value instanceof String text` matched.
- The compiler applies **flow scoping**: the pattern variable `text` is considered in scope at locations where the program proves it has been bound.

This is not "a variable accessible everywhere after `instanceof`." Scope depends on **control flow**.

### Why `return` in the Non-Matching Branch Matters

The following snippet **does not compile**:

```java
// WRONG: illustrates scope error; 'value' is Object.
if (!(value instanceof String text)) {
    System.out.println("Not a string");
}
return text.length(); // There is an execution path reaching here even if the pattern did not match.
```

The `if` branch can finish normally, so `text` is not guaranteed to have been assigned. Replacing it with `return` or `throw` in the non-matching branch eliminates the invalid path:

```java
// Valid snippet inside a method returning int.
if (!(value instanceof String text)) {
    throw new IllegalArgumentException("String required");
}
return text.length();
```

Use `return` if a non-match is a normal business result; use `throw` when a non-match violates the input contract and the caller should receive an exception. Choose based on the method's API, not habit.

## 3. Combining a Match with a Condition Using `&&`

A pattern variable can be used immediately in the subsequent condition of the **short-circuit AND** operator:

```java
// Snippet: 'input' has type Object.
if (input instanceof String text && !text.isBlank()) {
    return "Valid text: " + text.trim();
}
return "Empty or not text";
```

Java only evaluates `!text.isBlank()` when `input instanceof String text` is already true. On the right-hand side of `&&`, `text` definitely exists and has type `String`.

For `||`, you cannot reference the variable like this:

```java
// WRONG: Java does not guarantee text is created when the right-hand side is evaluated.
if (input instanceof String text || text.isBlank()) {
    return "Invalid";
}
```

When the left-hand side of `||` is false, the right-hand side is evaluated, which is precisely the case where the pattern **did not match**. The compiler reports an error because `text` is not in scope on the right-hand side.

To reject blank strings and keep the variable afterward, you can write:

```java
// Snippet inside a method returning String.
if (!(input instanceof String text) || text.isBlank()) {
    return "Invalid text";
}
return "Valid: " + text;
```

In this conditional expression, the left branch is `!(input instanceof String text)`. When the right-hand side `text.isBlank()` is evaluated, the negation was false, meaning the original pattern **matched**; therefore `text` is allowed to be referenced. If the entire condition is false, the method continues with a non-blank `String`. This negated scenario illustrates that **scope depends on the logic of the condition**, not mechanically on the `&&` or `||` symbol.

### Avoiding Unnecessary Duplicate `null` Checks

`if (input instanceof String text)` already excludes `input == null` for the success branch. Therefore, inside this branch, you do not need `if (input != null)` just to confirm the outermost value. However, if you deconstruct a `record` that has a reference component, that component **can still be `null`** and needs to be handled separately.

## 4. Early Return After Matching a Record Pattern

Record patterns help check an object's structure and extract components into variables. With Java 21+:

```java
record Item(String sku, int quantity) {}
record Order(String id, Object detail) {}
```

One processing style is to accept only an `Order` object whose `detail` is actually an `Item`:

```java
// Snippet: 'raw' is Object, inside a method returning String.
if (!(raw instanceof Order(var id, Item(var sku, var quantity)))) {
    return "Invalid order shape";
}

if (id == null || id.isBlank()) {
    return "Missing order id";
}
if (sku == null || sku.isBlank()) {
    return "Missing SKU for " + id;
}
if (quantity <= 0) {
    return "Invalid quantity for " + id;
}
return "Accepted " + id + " / " + sku + " x" + quantity;
```

**Explanation of the matching mechanism:**

- `Order(var id, ...)` requires `raw` to be a non-`null` `Order`. `var id` extracts the `id` component into a variable of type `String`.
- `Item(var sku, var quantity)` further deconstructs the `detail` component. Because `detail` is declared as `Object`, the nested record pattern also checks at runtime that it is an `Item`.
- If `raw == null`, is not an `Order`, or `detail == null`/is not an `Item`, **the entire pattern does not match**, and the guard branch returns `"Invalid order shape"`.
- When execution reaches the `if` statements below, the compiler knows that `id`, `sku`, and `quantity` have been bound. `quantity` has type `int`, while `id` and `sku` have type `String` but may contain `null`.
- Each guard clause checks a single requirement and `return`s immediately on error. If all guards pass, the data satisfies the checked conditions.

When a component is extracted only with `var`, matching **does not automatically guarantee the component is non-`null`**. That is why `id == null` and `sku == null` must be checked before calling `isBlank()`. Thanks to the short-circuiting `||` operator, `isBlank()` only runs when the variable is non-`null`.

This differs from `if (raw instanceof Order(var id, Item(var sku, var quantity))) { return ...; }`: the positive match style fits when you only need to handle the matched case and return immediately; the negated style fits when you want validation steps **to continue after the guard** without nesting multiple `if` levels.

## 5. Returning Inside a `switch` Statement with Patterns

Since Java 21, `switch` can use type patterns and `when` guards. Inside a **switch statement**, the selected branch can execute `return` to terminate the **enclosing method**:

```java
// Snippet inside a method returning String.
switch (value) {
    case String text when text.isBlank() -> {
        return "Blank text";
    }
    case String text -> {
        return "Text length " + text.length();
    }
    case Integer n when n >= 0 -> {
        return "Nonnegative " + n;
    }
    case Integer n -> {
        return "Negative " + n;
    }
    case null -> {
        return "Null";
    }
    default -> {
        return "Other";
    }
}
```

In each branch:

- The type pattern checks the type of `value` and declares the pattern variable within the branch's scope.
- The `when` guard is only evaluated when the corresponding pattern has matched.
- `return` terminates the **method**, not merely exiting the `switch`. There is no execution of subsequent cases after the method has returned.
- Order matters: `case String text when text.isBlank()` precedes `case String text` to avoid being shadowed by the general branch (**dominated case**); the same applies to `Integer`.
- `case null` handles a `null` selector. `default` handles other types.

This is a **switch statement**, so `default` is not strictly required just to make the switch statement exhaustive. However, if a method has a non-`void` return type and relies solely on `return` inside the switch, you must ensure every execution path ends with a valid value or provide a `return` after the switch for unhandled cases.

### Difference Between `return` and `yield`

A `switch expression` produces **a value**. A block branch of a switch expression uses `yield` to supply the value for the expression:

```java
// Snippet: 'value' has type Object.
return switch (value) {
    case String text -> text.trim();
    case Integer n -> n.toString();
    case null -> "No data";
    default -> "Other";
};
```

Here, `return` **wraps the entire switch expression**, returning its final result from the method. If a branch of a switch expression needs multiple statements, use a block `-> { ... yield expression; }` to provide the result. Do not confuse `yield` (producing a value for a switch expression) with `return` (exiting a method).

Example:

```java
// Snippet: 'value' has type Object.
return switch (value) {
    case String text -> {
        String normalized = text.trim();
        yield normalized.isEmpty() ? "(blank)" : normalized;
    }
    case null -> "(null)";
    default -> "(other)";
};
```

To avoid confusion about control flow, use **direct `return` inside a switch statement** when each case wants to end the method, or use **`return switch` expression** when all cases together produce a single result.

## 6. Complete Java 21+ Example: Match, Guard Clause, Switch

Create the file **`EarlyReturnAfterMatchDemo.java`**:

```java
public class EarlyReturnAfterMatchDemo {
    record Item(String sku, int quantity) {}
    record Order(String id, Object detail) {}

    static String describe(Object value) {
        if (value instanceof String text) {
            return "Text: " + text.trim();
        }
        if (value instanceof Integer number) {
            return "Number: " + number;
        }
        if (value == null) {
            return "No input";
        }
        return "Unsupported: " + value.getClass().getSimpleName();
    }

    static String validate(Object raw) {
        if (!(raw instanceof Order(var id, Item(var sku, var quantity)))) {
            return "Invalid order shape";
        }
        if (id == null || id.isBlank()) {
            return "Missing order id";
        }
        if (sku == null || sku.isBlank()) {
            return "Missing SKU for " + id;
        }
        if (quantity <= 0) {
            return "Invalid quantity for " + id;
        }
        return "Accepted " + id + " / " + sku + " x" + quantity;
    }

    static String classify(Object value) {
        switch (value) {
            case String text when text.isBlank() -> {
                return "Blank text";
            }
            case String text -> {
                return "Text length " + text.length();
            }
            case Integer n when n >= 0 -> {
                return "Nonnegative " + n;
            }
            case Integer n -> {
                return "Negative " + n;
            }
            case null -> {
                return "Null";
            }
            default -> {
                return "Other";
            }
        }
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java  "));
        System.out.println(describe(12));
        System.out.println(describe(null));
        System.out.println(describe(2.5));
        System.out.println(validate(new Order("O-1", new Item("SKU-7", 3))));
        System.out.println(validate(new Order("O-2", new Item("SKU-8", 0))));
        System.out.println(validate(new Order("O-3", null)));
        System.out.println(validate(new Order("  ", new Item("SKU-9", 1))));
        System.out.println(validate(new Order("O-4", new Item(null, 1))));
        System.out.println(validate("x"));
        System.out.println(classify("  "));
        System.out.println(classify("abc"));
        System.out.println(classify(0));
        System.out.println(classify(-2));
        System.out.println(classify(null));
        System.out.println(classify(1.5));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac -encoding UTF-8 EarlyReturnAfterMatchDemo.java
java EarlyReturnAfterMatchDemo
```

Exact output:

```text
Text: Java
Number: 12
No input
Unsupported: Double
Accepted O-1 / SKU-7 x3
Invalid quantity for O-2
Invalid order shape
Missing order id
Missing SKU for O-4
Invalid order shape
Blank text
Text length 3
Nonnegative 0
Negative -2
Null
Other
```

**Analysis of representative cases:**

1. `describe("  Java  ")` matches `String text` and returns `"Text: Java"` after `trim()`. The `Integer` branch and subsequent statements do not run.
2. `describe(12)` does not match `String`, but matches `Integer number`, and returns immediately. When passing `12` to an `Object` parameter, Java uses autoboxing into `Integer`.
3. `describe(null)` does not match any type pattern and is handled by `if (value == null)`. `describe(2.5)` receives a `Double` object and falls into the fallback branch; there `value` is guaranteed non-`null` thanks to the preceding guard.
4. `validate(new Order("O-1", new Item("SKU-7", 3)))` matches the nested record pattern, passes all guards, and returns `Accepted`.
5. `Order("O-2", Item("SKU-8", 0))` matches the structure but is rejected by the `quantity <= 0` guard. `Order("O-3", null)` does not match the nested record pattern, so it returns `Invalid order shape`.
6. When `id` is a whitespace-only string or `sku` is `null`, the appropriate guard clause returns a message before these values are used.
7. `classify` uses a `switch statement` with type patterns, `when`, `case null`, and direct returns. The guard/general branch pairs properly cover cases of the same type.

## 7. Variable Scope and Control Flow Semantics to Remember

### `return` Exits the Method

`return expression;` returns a value and terminates the **currently executing method invocation**. It does not merely "exit the `if` branch" to continue running the statement after the branch. For `void` methods, the valid early return form is `return;` without an expression:

```java
// Snippet inside a void log(Object input) method.
if (!(input instanceof String text)) {
    return; // Nothing to log.
}
System.out.println(text);
```

Inside a lambda, `return` (where allowed in a block lambda) terminates **that lambda**, not automatically the enclosing method that invokes the lambda. Therefore, callback/lambda `return` statements should not be used to replace method-level guard clauses when you need to stop the entire process.

### A Pattern Variable Exists Only When Proven to Have Matched

| Context | Can the variable be used? | Reason |
| --- | --- | --- |
| Inside `if (x instanceof String s) { ... }` | Yes | Branch only runs when the pattern matches |
| Right-hand side of `&&` in `x instanceof String s && s.length() > 0` | Yes | Short-circuiting guarantees the left-hand side is true |
| After `if (!(x instanceof String s)) return ...;` | Yes | If execution continues, the original pattern definitely matched |
| After `if (!(x instanceof String s)) println(...);` | Not guaranteed; usually a compile error if referencing `s` | The non-matching branch can still continue |
| In the `when` guard and body of `case String s` | Yes | The pattern has already matched before the guard and body |
| In another case branch or outside the switch | No | The variable is not in scope in those places |

### Pattern Matching Does Not Replace Business Validation

`input instanceof Order(var id, Item(var sku, var quantity))` guarantees the type structure and extracts components, but **does not automatically guarantee** that `id` is valid, `sku` is non-`null`, `quantity` is positive, or other business rules hold. Those conditions must be checked separately.

If a method returns early, important cleanup that is properly structured still needs to execute. For example, when using try-with-resources, resources are closed upon exiting the scope, even on `return`; avoid writing business logic that depends on a subsequent statement that could be skipped by an early return.

## 8. Comparing Approaches and Selection Criteria

| Approach | When to use | Key notes |
| --- | --- | --- |
| `if (x instanceof T v) return result;` | Handle only the matched case and exit | Multiple pattern branches can be stacked sequentially |
| `if (!(x instanceof T v)) return fallback;` | Input must match, and the remaining code is the main flow | Variable `v` can remain in scope below via flow scoping |
| `if (x instanceof T v && guard(v)) return result;` | Return only for a subtype and a valid condition | Guard runs only when matched |
| `switch (x) { case T v -> { return ...; } ... }` | Multiple types need separate handling in the same method | Specific guards before general cases; consider `null`/`default` |
| `return switch (x) { case T v -> ...; ... };` | All branches together produce a single value | Switch expression must be exhaustive; blocks use `yield` |

Guard clauses make code easier to read when preconditions can be checked quickly before the main processing. However, **avoid having too many scattered returns** if the method must perform a mandatory final step for every case (such as updating transaction state, auditing, or recording statistics). In that situation, consider extracting steps into smaller methods or consolidating the execution flow in an appropriate place.

## 9. Common Mistakes

| Mistake | Why | How to fix |
| --- | --- | --- |
| Accessing `text` after `if (x instanceof String text) { ... }` when a non-matching path exists | The variable may not be bound | Use it inside the matching branch, or negate the pattern and return on non-match |
| `if (!(x instanceof String text))` branch only logs, then `text` is used below | Logging does not guarantee exiting the method | Use `return`/`throw` or reorganize control flow |
| Reading `text` on the right-hand side of `x instanceof String text || ...` | `text` is not in scope when the left-hand side is false | Use conditional logic whose short-circuiting guarantees a match, such as `&&` |
| Assuming `instanceof` matches `null` | Type patterns do not match `null` | Add a `null`-handling branch when needed |
| Assuming `var sku` from a record pattern is always non-`null` | Reference components can be `null` | Check `sku == null` before calling methods on it |
| Skipping validation steps after a record pattern matches | Matching only proves structure/type, not business validity | Add corresponding guard clauses |
| Placing `case String s` before `case String s when s.isBlank()` | The broader case shadows the guarded case, causing a Java dominance error | Place the specific guarded case first |
| Confusing `return` with `break` or `yield` | The three statements have different control-flow roles | `return` exits the method; `yield` produces a switch expression result; `break` exits the corresponding switch statement/loop |
| Writing multiple `return` branches while forgetting business cleanup | Statements after `return` do not execute | Design clear exit paths, use scope/try-with-resources, or extract appropriate methods |
| Using record patterns on Java 17 without preview enabled | Record patterns are not standard in Java 17 | Use Java 21+ or use only `instanceof` type patterns |

## 10. Practice Exercises

Given two records:

```java
record Customer(String id, String email) {}
record Envelope(Object payload) {}
```

**Exercise 1.** Write a method that returns `"Not a customer"` if `input` is not a `Customer`. If it matches, use `id` and `email` after the guard to return `id + ": " + email`.

**Answer:**

```java
// Snippet inside a class containing the declared records.
static String customerLabel(Object input) {
    if (!(input instanceof Customer(var id, var email))) {
        return "Not a customer";
    }
    return id + ": " + email;
}
```

The match condition here does not check whether `email` is non-`null`; if business rules require a valid email, it must be validated separately.

**Exercise 2.** Given `Object raw`, accept only an `Envelope` whose payload is a non-blank `String`. Return `"Invalid"` if invalid; otherwise return the trimmed string.

**Answer:**

```java
static String normalized(Object raw) {
    if (!(raw instanceof Envelope(String text)) || text.isBlank()) {
        return "Invalid";
    }
    return text.trim();
}
```

If `raw` is not an `Envelope` or the payload is not a non-`null` `String`, the left-hand side of `||` is true and the right-hand side does not execute. If the pattern matches, the compiler allows using `text` in `text.isBlank()` and after the guard statement.

**Exercise 3.** Write a `switch statement` in the method `static String category(Object value)`: a blank string returns `"Blank"`, another string returns `"Text"`, an `Integer` returns `"Integer"`, `null` returns `"Null"`, and all other cases return `"Other"`.

**Answer:**

```java
static String category(Object value) {
    switch (value) {
        case String s when s.isBlank() -> { return "Blank"; }
        case String s -> { return "Text"; }
        case Integer n -> { return "Integer"; }
        case null -> { return "Null"; }
        default -> { return "Other"; }
    }
}
```

The guarded branch must come before the broader `String` branch. Each branch `return`s directly, so no additional `return` is needed after the switch.

**Exercise 4.** Why can't this snippet use `text` after the `if`?

```java
if (!(input instanceof String text)) {
    System.out.println("Invalid");
}
System.out.println(text);
```

**Answer:** The non-matching path still continues after printing the log, so `text` may not be declared in a valid scope. Add `return;` (in a `void` method) or `throw` in the error branch, or move printing `text` into the matching branch.

## 11. Summary and References

- **Positive match + return**: when a pattern matches, immediately use the bound variables and terminate the method.
- **Negative guard + return**: when a pattern does not match, stop early; subsequent code can use the pattern variable thanks to flow scoping rules.
- With `&&`, a subsequent guard can use the matched pattern's variable; with a negated pattern combined with `||`, the variable can only be used when the condition's logic proves the original pattern matched.
- Nested record patterns allow extracting multiple components, but only prove structural/type conditions; check `null` and business rules separately.
- In a `switch statement`, `return` inside a branch terminates the method. In a `switch expression`, branches produce a value via an expression or `yield`; `return switch (...)` returns the result of the entire expression.
- Choose early return to reduce nesting and clarify exit points, while ensuring necessary final steps remain safely designed.

Official documentation: [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
