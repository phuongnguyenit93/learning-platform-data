# Forgetting to Handle `null` When Using Pattern Matching in Java 21+

## 1. Why Is This a Common Pitfall?

Pattern matching makes type checking and data deconstruction in Java more concise, but it **does not automatically guarantee that every reference value is non-`null`**. A common mistake is seeing a variable declared by a pattern and immediately calling methods on it, or assuming that `default` in a `switch` will also handle `null` input.

Three situations behave differently:

1. **`instanceof` with a `null` selector**: the expression evaluates to `false`; the `if` body does not run.
2. **`switch` with a `null` selector and no matching null-handling branch**: normally throws `NullPointerException`; it does **not** fall into `default`.
3. **A `null` component value inside a record pattern**: whether it matches depends on **the kind of component pattern and the static type of the component**. In particular, an *unconditional* pattern can match even a `null` component.

This third difference is very easy to overlook. For example, in Java 21:

~~~java
record TypedText(String text) {}

Object input = new TypedText(null);
if (input instanceof TypedText(String text)) {
    System.out.println(text == null); // true
}
~~~

`TypedText(String text)` is a record pattern. The component of `TypedText` already has static type `String`, so `String text` in this position is an **unconditional pattern**; it can match even when the component is `null`. Therefore, you must not infer that **every type pattern excludes `null` in every position**.

Goal of this article: distinguish `null` **in the selector**, `null` **in a record component**, and `null` **in the domain model**; choose an intentional handling strategy, keep conditions safe, and test edge cases.

This article uses **Java 21+** to demonstrate type patterns, record patterns, and pattern matching in `switch`. These features do not require `--enable-preview` on JDK 21.

## 2. `null` in `instanceof`: A Type Check, Not a Cast

With an ordinary type pattern:

~~~java
Object maybeName = null;

if (maybeName instanceof String name) {
    System.out.println(name.toUpperCase());
} else {
    System.out.println("not a String");
}
~~~

Output:

~~~text
not a String
~~~

An outermost `null` value causes `instanceof String name` to return `false`. Because the `if` body only executes when the pattern matches, the variable `name` can be used as a valid `String` in the true branch; Java does not dereference `maybeName` before checking.

This differs from the following snippet:

~~~java
// UNSAFE if maybeName == null:
String name = (String) maybeName; // Casting null can succeed: name is still null
System.out.println(name.toUpperCase()); // NullPointerException
~~~

Casting a `null` reference to `String` does not turn the value into an actual string. Therefore, replacing `instanceof` with a cast and omitting the null check can change behavior or cause a runtime error.

**Remember:** `if (obj instanceof SomeType x)` is a type check that matches a **non-null** selector value. It does not prove that reference fields **inside** `obj` are also non-null.

## 3. `null` in `switch`: `default` Does Not Replace `case null`

Consider a classification method:

~~~java
static String unsafeSwitch(Object input) {
    return switch (input) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

For `unsafeSwitch("abc")`, the result is `"text:abc"`. For `unsafeSwitch(42)`, the result is `"other"`. However, **`unsafeSwitch(null)` throws `NullPointerException`**. In a Java 21 pattern switch, `default` is not a branch for a `null` selector.

How to handle it when **`null` is accepted input**:

~~~java
static String safeSwitch(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

Now `safeSwitch(null)` returns `"missing"`. If the business logic does not allow `null` input, you can also **explicitly reject it**:

~~~java
static String rejectNull(Object input) {
    java.util.Objects.requireNonNull(input, "input");
    return switch (input) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

Both approaches are intentional: the first has a **null-handling branch**; the second has a **non-null contract** with a specific message. Avoid accidentally letting an exception surface just because an edge case was forgotten.

Even when a `switch` expression over a `sealed interface` or `enum` already covers all subtypes or enum constants, being **exhaustive over non-null values** does not mean it automatically handles `null`. When designing an API, always decide whether `null` is a valid input, an invalid input, or a "no data yet" state.

## 4. Record Patterns and the Difference Between Two Kinds of Component Patterns

A record can hold a `null` reference if it does not validate it in its constructor:

~~~java
record TypedText(String text) {}
record BroadText(Object text) {}
~~~

Consider three matches:

~~~java
Object typed = new TypedText(null);
Object broad = new BroadText(null);
Object actualText = new BroadText("hello");

System.out.println(typed instanceof TypedText(String s));     // true
System.out.println(broad instanceof BroadText(String s));     // false
System.out.println(actualText instanceof BroadText(String s)); // true
~~~

**Why are they different?**

- In `TypedText`, the component is **declared with type `String`**. The subpattern `String s` is *unconditional* for a component of that static type; it can accept a `null` value.
- In `BroadText`, the component is **declared with type `Object`**. The subpattern `String s` must check the runtime type: `null` is not a `String` value matched conditionally; therefore it does not match.
- When `BroadText` holds the string `"hello"`, the subpattern `String s` matches.

This is not a compiler bug. It is the pattern semantics at **record component position**, where the condition "unconditional with respect to the static type" applies.

For `var`:

~~~java
Object typed = new TypedText(null);

if (typed instanceof TypedText(var text)) {
    // text has static type String, but its value can be null.
    System.out.println(text == null); // true
}
~~~

`var` infers the type from the component; it **does not** perform non-null validation automatically. If you plan to call `text.isBlank()`, you need to check `text != null` or rely on validation already enforced by the constructor.

### Nested Record Patterns: `null` at Each Level

~~~java
record User(String name) {}
record Transfer(User sender, String reference, int amount) {}
~~~

Two different inputs:

~~~java
Object missingSender = new Transfer(null, "REF-7", 3);
Object missingName = new Transfer(new User(null), "REF-7", 3);
~~~

With the pattern `Transfer(User(var name), var reference, var amount)`:

- `missingSender` does **not** match the nested pattern `User(...)` because that position requires an actual `User` object, not `null`.
- `missingName` has a structurally valid `User` as `sender`; `var name` can receive `null` from the record's `name` component.
- If `reference == null`, `var reference` can still receive `null`. The pattern does not automatically filter out this missing value.
- If the outermost selector is `null`, `instanceof Transfer(...)` still returns `false`.

**General rule:** identify where `null` can appear, the static type of each component, and the subpattern at each level. You cannot mechanically apply a blanket rule like "record patterns skip all nulls."

## 5. Combining `&&` to Guard Access

A simple way to avoid `NullPointerException` is to use **short-circuit evaluation**:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank();
System.out.println(valid); // false
~~~

Java evaluates `&&` from left to right. When `name != null` is false, `name.isBlank()` is **not called**.

**Avoid reversing the order:**

~~~java
// Can throw NullPointerException when name == null:
boolean unsafe = !name.isBlank() && name != null;
~~~

The same applies to a record pattern variable on the right-hand side:

~~~java
Object input = new User(null);

boolean valid =
        input instanceof User(var name)
        && name != null
        && !name.isBlank();
~~~

The variable `name` is valid to use in the subsequent operands of `&&` because the preceding pattern matched. The guard `name != null` must be placed **before** the `isBlank()` call. Note: `User(var name)` can match even when the inner name is `null`, so this null check is not redundant.

Do not arbitrarily replace `&&` with `||`:

~~~java
// INTENTIONALLY WRONG: if the pattern does not match, the right-hand side may still need to run,
// but name is not in valid scope.
if (input instanceof User(var name) || name.isBlank()) {
    // ...
}
~~~

This is an **intentionally non-compiling snippet** to illustrate *flow scoping*, not code run in the program in Section 9. Beyond variable scoping, the `||` operator also has a completely different business meaning from `&&`, so they cannot be swapped just to shorten a statement.

## 6. Using `when` in `switch` Without Dereferencing `null`

Starting in Java 21, `when` is a pattern guard in `switch`. Example:

~~~java
static String classify(Object input) {
    return switch (input) {
        case null -> "null-input";

        case Transfer(User(var name), var reference, var amount)
                when name != null && !name.isBlank()
                    && reference != null && !reference.isBlank()
                    && amount > 0 ->
                "accepted:" + name + ":" + reference;

        case Transfer(var sender, var reference, var amount) ->
                "rejected-transfer";

        case User(var name) when name != null && !name.isBlank() ->
                "user:" + name;

        case User(var name) -> "unnamed-user";

        default -> "other";
    };
}
~~~

This method is logically self-contained but requires the `record User` and `Transfer` declared above; the complete program is in Section 9.

Reading each branch:

1. `case null` handles a `null` **outermost selector**, preventing an unintended `NullPointerException`.
2. The pattern `Transfer(User(var name), ...)` checks structure at two levels. When `sender` is `null`, this branch does not match. When `sender` is a `User` with `name == null`, the structural pattern can match, but the **guard** rejects it.
3. The guard `name != null && !name.isBlank()` protects the method call. The same applies to `reference`.
4. The branch `case Transfer(var sender, var reference, var amount)` comes **after** the guarded branch, catching every `Transfer` that failed the acceptance criteria, including `sender == null`.
5. The two `User` branches show that a `User` record with a `null` or blank name is still a `User` by type, just invalid under the "named" labeling rule.
6. `default` handles a **non-null** selector that does not belong to either record type under consideration, such as an ordinary string.

Note when refactoring: if you move the general `Transfer(...)` branch before the specific `when`-guarded branch, the specific branch can become *dominated* and Java will reject it. Ordering from specific to general matters for both type checking and behavior.

`when` does not replace enforcing invariants where objects are created. It is a check at the **use site**, useful when input may be raw or unvalidated data.

## 7. Domain Model Solution: Preventing Invalid Object Creation

If the application has decided that a `User` must **never** be allowed to have `name == null` or a blank name, enforce that in the constructor instead of relying on every caller to remember to check.

~~~java
record ValidatedUser(String name) {
    ValidatedUser {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name");
        }
    }
}
~~~

With this record:

~~~java
ValidatedUser a = new ValidatedUser("Lan"); // Valid
// new ValidatedUser(null);                 // Throws IllegalArgumentException
// new ValidatedUser("  ");                 // Throws IllegalArgumentException
~~~

This snippet illustrates constructor validation. When objects are created through normal paths and the invariant is maintained, processing code can **rely on the domain contract** instead of repeating null checks everywhere.

However:

- Java does not treat `String` as non-null by default. Having a field of type `String` is **not enough** to exclude `null`.
- Records are only *shallowly immutable*; components referencing mutable objects need additional design and protection so invariants cannot be broken after the constructor runs.
- At external data boundaries (JSON, DTOs, database rows, message queues), a **validation and conversion** step into valid domain objects is still needed.
- If `null` has business meaning ("unknown", "not provided"), model it explicitly with a subtype, state, or appropriate design choice. Do not try to hide `null` by skipping checks in processing code.
- `Objects.requireNonNull(x, "field")` is useful when you want to **explicitly reject `null`**, but it intentionally throws `NullPointerException`; if the API uses a custom validation exception, choose the exception according to the contract.

**Only rely on an invariant when you know for sure where it is enforced.** If you cannot verify the source of the guarantee, keeping a guard at the use site is safer and easier to review.

## 8. Principles for Handling `null` by Position

| Position of `null` value | What typically happens | Solution |
| --- | --- | --- |
| Selector in `obj instanceof Type x` | Evaluates to `false` | Use an `else` branch or an appropriate rejection rule |
| Selector in a pattern `switch` | Can throw `NullPointerException` when `null` is unhandled | Add `case null` or fail fast with `requireNonNull` |
| Reference component matched by `var x` | `x` can still receive `null` | Check `x != null` before calling methods |
| `String`-typed component matched by unconditional `String x` pattern | Can match even when `null` | Do not infer `x != null` from this syntax alone |
| `Object`-typed component matched by `String x` | Conditional pattern does not match if component is `null` | Distinguish from unconditional patterns |
| Nested record `User(...)` receiving a `null` `sender` component | Nested record pattern does not match | Have a fallback branch or domain-level null check |
| Guard `when x != null && x.is...()` | Dereference only runs when non-null | Preserve short-circuit order |
| Return value from a function that may be `null` | Downstream caller may hit NPE | Express the contract, check it, or change the result model |

**Do not equate "pattern did not match" with "invalid data."** For example, a `Transfer` missing a `sender` may be an invalid object in your domain, yet in Java it still has type `Transfer` if the constructor allows it. Pattern matching does not replace business validation.

## 9. Complete Java 21 Program: 18 Test Cases

Create the file **`NullPatternPitfallsDemo.java`** with the following code. Null cases are tested as realistic input data; the snippet that triggers `NullPointerException` is caught **intentionally to demonstrate the behavior**, rather than letting the whole program crash abruptly.

~~~java
public class NullPatternPitfallsDemo {
    record User(String name) {}
    record Transfer(User sender, String reference, int amount) {}
    record TypedText(String text) {}
    record BroadText(Object text) {}
    record TestCase(String name, Object input, String expected) {}

    private static int passed = 0;

    static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        passed++;
        System.out.println("PASS " + name);
    }

    static String classify(Object input) {
        return switch (input) {
            case null -> "null-input";
            case Transfer(User(var name), var reference, var amount)
                    when name != null && !name.isBlank()
                        && reference != null && !reference.isBlank()
                        && amount > 0 ->
                    "accepted:" + name + ":" + reference;
            case Transfer(var sender, var reference, var amount) ->
                    "rejected-transfer";
            case User(var name) when name != null && !name.isBlank() ->
                    "user:" + name;
            case User(var name) -> "unnamed-user";
            default -> "other";
        };
    }

    static String unsafeSwitch(Object input) {
        return switch (input) {
            case String text -> "text:" + text;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        TestCase[] samples = {
            new TestCase("accepted",
                    new Transfer(new User("Lan"), "REF-7", 3),
                    "accepted:Lan:REF-7"),
            new TestCase("null-sender",
                    new Transfer(null, "REF-7", 3),
                    "rejected-transfer"),
            new TestCase("null-name",
                    new Transfer(new User(null), "REF-7", 3),
                    "rejected-transfer"),
            new TestCase("blank-name",
                    new Transfer(new User("  "), "REF-7", 3),
                    "rejected-transfer"),
            new TestCase("null-reference",
                    new Transfer(new User("Lan"), null, 3),
                    "rejected-transfer"),
            new TestCase("blank-reference",
                    new Transfer(new User("Lan"), " ", 3),
                    "rejected-transfer"),
            new TestCase("zero-amount",
                    new Transfer(new User("Lan"), "REF-7", 0),
                    "rejected-transfer"),
            new TestCase("negative-amount",
                    new Transfer(new User("Lan"), "REF-7", -2),
                    "rejected-transfer"),
            new TestCase("user-name",
                    new User("Minh"), "user:Minh"),
            new TestCase("user-null-name",
                    new User(null), "unnamed-user"),
            new TestCase("user-blank-name",
                    new User(" "), "unnamed-user"),
            new TestCase("top-level-null", null, "null-input"),
            new TestCase("other-type", "hello", "other")
        };

        for (TestCase sample : samples) {
            check(sample.name(),
                    classify(sample.input()).equals(sample.expected()));
        }

        Object missing = null;
        check("instanceof-null-is-false",
                !(missing instanceof String text));

        Object typed = new TypedText(null);
        check("unconditional-component-matches-null",
                typed instanceof TypedText(String text) && text == null);

        Object broad = new BroadText(null);
        check("conditional-component-rejects-null",
                !(broad instanceof BroadText(String text)));

        check("unsafe-switch-nonnull",
                unsafeSwitch("abc").equals("text:abc"));

        try {
            unsafeSwitch(null);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            check("switch-default-does-not-handle-null", true);
        }

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Run with **JDK 21+**:

~~~bash
javac --release 21 NullPatternPitfallsDemo.java
java NullPatternPitfallsDemo
~~~

**Expected output:**

~~~text
PASS accepted
PASS null-sender
PASS null-name
PASS blank-name
PASS null-reference
PASS blank-reference
PASS zero-amount
PASS negative-amount
PASS user-name
PASS user-null-name
PASS user-blank-name
PASS top-level-null
PASS other-type
PASS instanceof-null-is-false
PASS unconditional-component-matches-null
PASS conditional-component-rejects-null
PASS unsafe-switch-nonnull
PASS switch-default-does-not-handle-null
ALL PASSED: 18
~~~

### Understanding the Edge Cases

- **`top-level-null`**: the `switch` has `case null`, so it returns the `"null-input"` label as contracted.
- **`null-sender`**: the nested pattern `User(...)` fails when `sender` is `null`; the broader `Transfer(...)` branch classifies it as rejected instead of throwing an exception.
- **`null-name`, `null-reference`**: the record exists and the pattern variables can receive `null`; the `!= null` guard filters them out before `isBlank()` is called.
- **`user-null-name`**: `User` is an existing record, but its name was not validated in the constructor; the fallback branch handles a `null` name.
- **`unconditional-component-matches-null`**: the `String text` component of `TypedText` can match `null` in a record pattern; this is a case that is very easy to misunderstand.
- **`conditional-component-rejects-null`**: the `Object`-declared component of `BroadText` does not match `String text` if the value is `null`.
- **`instanceof-null-is-false`**: with a `null` outermost selector, `instanceof` directly returns `false`.
- **`switch-default-does-not-handle-null`**: calling `unsafeSwitch(null)` throws `NullPointerException`; the test catches the exact exception type and treats it as expected behavior, not as a recommended way to handle `null`.

The `check` function throws `AssertionError` as soon as an expectation fails. The line `ALL PASSED: 18` only appears when all checks succeed.

## 10. Regression Testing: Don't Only Test the Happy Path

When modifying pattern-matching code, build a test matrix by **`null` position**, not only by object type:

| Test case | What to observe |
| --- | --- |
| Outermost `null` input to `instanceof` | Does not match, no NPE |
| Outermost `null` input to `switch` | Enters `case null` or rejects per contract |
| Outer record of right type but nested record is `null` | Nested pattern branch does not match; fallback handles it properly |
| Nested record exists but `String` component is `null` | Guard/invariant protects dereference |
| Record with blank string `"  "` | Handled per business rules; distinguish blank from `null` |
| `Object`-typed component holding `null` | Do not confuse with unconditional `String`-typed component |
| Right type but zero or negative amount | Business guard rejects, unrelated to `instanceof` |
| Completely different object type | Selects appropriate `default`/fallback |
| Pattern `switch` already exhaustive over subtypes | Still consider `null` selector separately |
| Refactoring `&&` or `when` | Do not call methods before the null-guard condition |

In automated test suites, give each case a clear name. When receiving JSON, APIs, or DTOs from external sources, test missing fields, fields with `null` values, blank strings, and missing nested objects; they may take different execution paths.

## 11. Mistakes to Avoid When Reading and Editing Code

**Mistake 1 — Treating `default` as a null-handling branch.** In a pattern `switch`, `default` is not responsible for catching a `null` selector automatically. Add `case null` or reject early per contract.

**Mistake 2 — Assuming a type pattern inside a record always excludes `null`.** `TypedText(String text)` with a static `String` component can match `null`. Do not call `text.length()` without a null check or a trustworthy invariant.

**Mistake 3 — Assuming `var` means non-null.** `var` infers the type; it does not check whether the value is non-null. A pattern variable with static type `String` can still hold `null` in positions allowed by pattern semantics.

**Mistake 4 — Dereferencing before checking for `null`.** `name.isBlank() && name != null` is the wrong order. `name != null && !name.isBlank()` avoids NPE via short-circuiting.

**Mistake 5 — Treating a `null` nested record the same as a `null` child component.** A nested `User(...)` pattern requires a `User` record to exist; an existing `User` containing `name == null` is a different situation. Write separate tests for each level.

**Mistake 6 — Omitting a fallback branch for a record that is type-valid but fails validation.** A pattern branch with `when` does not match if the guard is false; you must decide where the value goes next, especially in a `switch`.

**Mistake 7 — Believing the compiler enforces business invariants.** Java knows types and variable scopes; it does not automatically know that every created `User` has a name. Constructors/factories and validation must define domain constraints.

**Mistake 8 — Silently turning every `null` into an empty string.** `null` may mean "not provided", "unknown", or a data error. Replacing all of them with `""` can mask bugs and corrupt data.

**Mistake 9 — Adding `Objects.requireNonNull` without checking the contract.** This approach is appropriate when `null` is a programming error; it is not appropriate if the API needs to return "not found" or take a business branch for missing data.

**Mistake 10 — Changing a record constructor without re-running tests.** If you just added validation forbidding `null` names, older tests using `new User(null)` will need to be updated for the new model. Check both data creation sites and pattern usage sites together.

## 12. Code Review Checklist

Before approving a change that uses `instanceof`, record patterns, or pattern `switch`, check:

1. Can the selector be `null`? If so, does the code handle it according to contract?
2. Is `instanceof` distinguished from pattern `switch` regarding a `null` selector?
3. Can reference-typed record components be `null`, even when the pattern writes `String x` or `var x`?
4. Are there nested records that could be `null`? Where do non-matching cases go?
5. In `&&`/`when`, does the `!= null` guard appear before any risky method call?
6. If a null check is omitted, have you located the **enforced invariant** in the constructor/factory?
7. Is there a `case` branch after a guarded pattern to handle data that fails the condition?
8. Do the exception types and messages on `null` match the API contract?
9. Do tests cover outermost `null`, per-component `null`, blank strings, boundary numbers, and other types?
10. Are `null` cases explained with comments where they are genuinely non-obvious, rather than restating syntax?

### Self-Practice Exercises

- Replace `case null -> "null-input"` in `classify` by rejecting the input via `Objects.requireNonNull`. Rewrite the test expectations according to the new contract.
- Remove `name != null` from the guard and re-run `null-name`. Explain why `NullPointerException` can be thrown if `isBlank()` is called on `null`.
- Add a compact constructor to `User` to reject `null`/blank names; update the tests to match where the error occurs.
- Compare `TypedText(String text)` with `BroadText(String text)` when the component is `null`; explain the role of the **component's static type**.
- Write a `switch` over a `sealed interface` covering all subtypes without `case null`, then test with a `null` selector to verify that type exhaustiveness does not automatically handle `null`.

**Remember:** Pattern matching reduces casts and makes data structure easier to read, but it is not a general-purpose null filter. **`instanceof` directly on `null` returns `false`; pattern `switch` must handle a `null` selector explicitly; a record component can receive `null` even when the pattern variable has type `String`.** Combining short-circuit guards, constructor validation, and level-by-level tests helps avoid `NullPointerException` without obscuring domain meaning.
