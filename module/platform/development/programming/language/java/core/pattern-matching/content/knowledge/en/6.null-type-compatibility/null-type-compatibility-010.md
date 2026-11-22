# Designing Explicit Null-Handling Branches in Java Pattern Matching

## 1. Why Must You Design a Separate Null Branch?

In a Java application, a reference-type variable can hold an object or the value `null`. When using pattern matching to branch, the question is not only “what type does the object have?” but also **“if there is no object, what should the program do?”**. If you do not design the `null` branch from the start, the same input can be misinterpreted as an “unsupported type,” confusing data errors with missing-data cases, or causing an unexpected `NullPointerException`.

For example, when displaying a message:

- `null` may mean no message has been received yet;
- `""` or `"   "` is a string message that is empty in content;
- an integer is real data, just of a different type;
- an object of an unsupported type is also real data.

These four states are **not synonymous**. Grouping all of them into `default` or a single `else` can make business logic hard to test and report the wrong errors.

**Goal of this lesson:** define the `null` contract at input/output boundaries, create dedicated branches for `null` in `if/else` and `switch`, order guarded branches safely, handle `null` inside a `record`, and thoroughly test all execution paths.

## 2. Java Foundations: Patterns That Do and Do Not Match Null

Two important cases have different rules:

| Situation | Behavior | Design Implication |
| --- | --- | --- |
| `value instanceof String text` | When `value == null`, the result is `false`; the variable `text` is not bound | A separate `null` check branch is needed if you want to distinguish “no value” from “not a String” |
| `switch (value)` with patterns in Java 21 | Can declare `case null` to handle `null` directly | Separate `case null` when `null` is an allowed input |
| `switch` missing a `case null` branch | With a `null` input, it throws `NullPointerException` before entering normal branches, even when `default` is present | `default` is not a fallback branch for `null` |
| `case String text` | The pattern variable `text` of a type pattern is only in scope when the type pattern matches; this branch does not replace `case null` | You can call methods on `text` in a guard because the pattern has already matched |
| A `record` object with a `null` component | The `record` object itself can be non-null while an internal component is `null` | You must consider **two levels of missing data**: the outer object and the inner field |

Do not infer from the `instanceof` rule that every `switch` automatically ignores `null`. Nor should you infer that `case null` guarantees an object's components are non-null. These cases must have their own contracts and tests.

**Version milestones:** `instanceof` type patterns became official in Java 16 (and are stable in Java 17); pattern matching for `switch`, `case null`, and the type patterns/guards in this lesson use official Java 21 syntax. For `--release 17` projects, handle `null` before `switch` and use `if`/`instanceof`; do not copy Java 21 `case` syntax into Java 17.

## 3. Decide the Meaning of Null Before Writing Code

An explicit `null`-handling branch answers three questions:

1. **Is the input allowed to be `null`?** If yes, what is the expected behavior? If no, validate at the boundary and report errors consistently.
2. **Which state does `null` represent?** For example, not yet provided, not found, deselected, or a programming bug. Do not assume all of them mean the same thing.
3. **What must the result be distinguished from?** Do you need to separate `null` from an empty string, an object of another type, an invalid data state, and a system error?

A small design table helps avoid oversights:

| Example Input | State | Suggested Handling |
| --- | --- | --- |
| `null` | No input object | Return `MISSING` or reject at the boundary, depending on the contract |
| `""` / `"   "` | Has a string, but lacks content | Return `EMPTY_TEXT` or an empty-data error |
| `"Java"` | Valid string | Process the content |
| `42` | Valid integer | Process as an integer if supported |
| `2.5` in an API supporting only `String`/`Integer` | Unsupported type | Return `UNSUPPORTED` or a data-type error |

In a real API, choose a result representation tied to the business domain (an enum, a result type, or an intentional exception), not necessarily strings as in learning examples. What matters is that **each branch has a single, unambiguous meaning**.

## 4. The Simplest Pattern in Java 17: Check Null Before instanceof

When you need to classify an `Object` by type, place the explicit `null` branch **before** the type-pattern branches.

```java
public class ExplicitNullIf17 {

    static String route(Object input) {
        if (input == null) {
            return "MISSING";
        }

        if (input instanceof String text) {
            if (text.isBlank()) {
                return "EMPTY_TEXT";
            }
            return "TEXT: " + text.strip();
        }

        if (input instanceof Integer number) {
            return "INT: " + number;
        }

        return "UNSUPPORTED";
    }

    public static void main(String[] args) {
        System.out.println(route(null));
        System.out.println(route(" "));
        System.out.println(route(" Java "));
        System.out.println(route(42));
        System.out.println(route(2.5));
    }
}
```

Save the file as `ExplicitNullIf17.java` and run it with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 ExplicitNullIf17.java
java ExplicitNullIf17
```

Exact output:

```text
MISSING
EMPTY_TEXT
TEXT: Java
INT: 42
UNSUPPORTED
```

**Why is this approach safe and easy to understand?**

- The `input == null` branch has its own meaning; it is not blended into “type did not match.”
- After the early return, every subsequent path has a non-null input.
- In `input instanceof String text`, the variable `text` exists only on the matched path. `text.isBlank()` is safe because `text` cannot be `null` in this type pattern.
- `text.isBlank()` is checked before normal string processing; a whitespace-only string is not displayed as a string with content.
- `return "UNSUPPORTED"` is reserved for objects not of a supported type; it does not carry the meaning “missing object.”

If you omit the first branch:

```java
static String routeWithoutNullBranch(Object input) {
    if (input instanceof String text) {
        return text;
    }
    return "UNSUPPORTED";
}
```

The method returns `UNSUPPORTED` for `null` because `instanceof` does not match. This **does not throw an exception on its own**, but it only makes sense if the contract intentionally treats `null` and an unsupported type as the same state. Most situations requiring input diagnostics are clearer when separated.

### Should You Call a Method on the Input Before Checking?

Do not write:

```java
// WRONG for null safety when input can be null:
if (input.toString().isBlank()) {
    return "EMPTY_TEXT";
}
```

When `input` is `null`, calling `toString()` throws `NullPointerException` before you have a chance to classify it. To check for a string type, use `instanceof String text` and then call `text.isBlank()`; if the contract accepts `null`, consider a dedicated branch first.

## 5. Java 21: `case null` in `switch` Must Be Explicit

For the same classification problem, Java 21 can use a `switch` expression:

```java
static String route(Object input) {
    return switch (input) {
        case null -> "MISSING";
        case String text when text.isBlank() -> "EMPTY_TEXT";
        case String text -> "TEXT: " + text.strip();
        case Integer number -> "INT: " + number;
        default -> "UNSUPPORTED";
    };
}
```

This is an **illustrative method** placed inside a class and requires Java 21 or later.

**How to read the branch order:**

1. `case null` separates the case where there is no input object.
2. `case String text when text.isBlank()` matches strings and selects this branch only if the string is empty or contains only whitespace.
3. `case String text` handles the remaining strings. The general `String` branch must come after the guarded branch.
4. `case Integer number` handles boxed integers.
5. `default` covers the remaining values that do not match the cases above.

`when` is evaluated only after **the type pattern has matched**. Therefore, `text.isBlank()` here will never receive a null `String`. If the data can have `null` **inside** an object matched by a pattern, you must check the component separately, as shown in Section 7.

### Why Is `default` Not `case null`?

Consider the following code:

```java
static String unsafe(Object value) {
    return switch (value) {
        case String s -> "TEXT";
        default -> "OTHER";
    };
}
```

If you call `unsafe(null)`, Java 21 throws `NullPointerException`; it does **not** return `"OTHER"`. `default` serves the remaining non-null values, not as a substitute for `case null`. If you want to handle `null` as a result value, intentionally include `case null` in the `switch`.

In Java 17, if you use a traditional `switch` with a nullable reference-type selector, you also need a `null` pre-check outside; the `case String s` and `case null` pattern syntax shown here is official in Java 21.

## 6. Place `default`, `null`, and Guards According to Their Meaning

A common mistake is thinking that having `default` means “everything is covered.” Check these three points separately:

**First, `null` and a different type are two distinct states.** If missing data must be reported clearly, always write a `null` branch or an equivalent pre-check.

**Second, guards must not be used to hide invalid data.** For example:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "MISSING";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT";
        default -> "UNSUPPORTED";
    };
}
```

The snippet above is an illustrative Java 21 method. The two `String` branches express two different situations; `default` is for unsupported types. If the general `case String s` branch is placed before the guard, the guarded case after it is dominated and the compiler will reject it.

**Third, guards must be safe with nullable data fields.** A guard like `obj.field().isBlank()` can fail when `field()` returns `null`, even though `obj` itself is non-null. Check the nullable field first before calling methods on it.

You do not need to force every `switch` to have a `default` at all costs. With a closed type hierarchy using `sealed`, sometimes the better choice is to list all permitted variants so the compiler can verify exhaustiveness. The `null` branch remains independent of that.

## 7. Two Levels of Null: Outer Object and Data Inside a Record

Suppose a request has the following variants:

- `Text(String value)` holds text content; the `value` component can be `null` if the object is constructed that way.
- `Count(int amount)` holds a quantity.
- `Ping()` represents a signal carrying no data.
- The `Request` value itself can also be `null`.

Both a `null` `Request` and a `null` inside `Text` must be handled; they describe **two different states**.

Complete Java 21 example:

```java
public class ExplicitNullSwitch21 {

    sealed interface Request permits Text, Count, Ping {}

    record Text(String value) implements Request {}
    record Count(int amount) implements Request {}
    record Ping() implements Request {}

    static String handle(Request request) {
        return switch (request) {
            case null -> "MISSING_REQUEST";

            case Text t when t.value() == null ->
                    "MISSING_TEXT";

            case Text t when t.value().isBlank() ->
                    "EMPTY_TEXT";

            case Text t ->
                    "TEXT: " + t.value().strip();

            case Count c ->
                    "COUNT: " + c.amount();

            case Ping p ->
                    "PING";
        };
    }

    public static void main(String[] args) {
        System.out.println(handle(null));
        System.out.println(handle(new Text(null)));
        System.out.println(handle(new Text(" ")));
        System.out.println(handle(new Text(" Java ")));
        System.out.println(handle(new Count(7)));
        System.out.println(handle(new Ping()));
    }
}
```

Save the file as `ExplicitNullSwitch21.java` and run it:

```bash
javac -encoding UTF-8 --release 21 ExplicitNullSwitch21.java
java ExplicitNullSwitch21
```

Exact output:

```text
MISSING_REQUEST
MISSING_TEXT
EMPTY_TEXT
TEXT: Java
COUNT: 7
PING
```

**Key analysis:**

- `case null` catches the situation where the `request` variable does not point to an object.
- `case Text t` only matches a `Text` object; it **does not automatically guarantee** that `t.value()` is non-null.
- The first guard `t.value() == null` handles the missing component. Thanks to that, the next branch can safely call `t.value().isBlank()` when the value is already non-null; if the first guard was not taken, `t.value()` on this same `Text` object in this example is non-null.
- The unguarded `case Text t` at the end handles the remainder of the `Text` variant.
- Every permitted subtype of `Request` (`Text`, `Count`, `Ping`) has a covering branch; with `sealed`, the compiler can verify exhaustiveness without needing `default`. The `case null` branch provides dedicated handling for a `null` outer reference.

The example uses a `record` model to make the cases easy to see. In a real system, if `Text.value` is not allowed to be `null`, you should reject creating `Text(null)` right in the constructor instead of pushing a `MISSING_TEXT` branch down to every call site.

### When Do You Need to Check Null Inside a Nested Pattern?

Java 21 supports record patterns to extract components directly, such as `Text(String value)`. However, to express a **nullable contract** clearly and avoid misunderstanding nested pattern-matching rules, the example above keeps `Text t` and then checks `t.value()`. This helps readers clearly distinguish a `null` at the outer layer from a `null` in the inner data.

With multi-level nested record patterns, you must also consider the possibility that a reference component is `null` and choose appropriate branches according to each component type pattern's matching rules. Do not replace explicit null design with the assumption that “nested patterns automatically check all nulls.”

## 8. When to Accept Null, and When to Reject It?

Not every method needs a `case null`. The right choice depends on the **input contract**.

### Option A — Null Is a Valid State

For example, the user has not selected an item yet. The method should have a well-defined result:

```java
static String display(Object value) {
    if (value == null) {
        return "Chưa chọn";
    }
    if (value instanceof String text) {
        return text;
    }
    return "Không hỗ trợ";
}
```

This is an illustrative Java 17 method. It returns a clear value when `null` is accepted as a business case.

### Option B — Null Violates the Contract

For example, an order-processing method requires a mandatory parameter. Instead of returning an ambiguous result or trying to branch across multiple layers, validate immediately upon receipt:

```java
import java.util.Objects;

public class RequiredInput {
    static String normalize(String text) {
        Objects.requireNonNull(text, "text is required");
        return text.strip();
    }
}
```

The snippet above compiles with Java 17. `Objects.requireNonNull` throws `NullPointerException` with the chosen message when given `null`. This is **intentional behavior at the contract boundary**, unlike accidentally calling `text.strip()` on `null`.

If you prefer `IllegalArgumentException` or a domain error object instead, establish a consistent application convention; do not mix error types across branches without reason.

### Option C — Null May Occur, but Return a Different Representation

For example, a lookup method might not find a record. The API can consider `Optional<T>` for present/absent results where appropriate. `Optional` does not automatically eliminate `null` from external systems; you still have to convert at the boundary and handle empty or malformed data cases separately.

Replacing every reference with `Optional` is not the goal either. What needs to be consistent is that callers **know in advance** when a result may be absent and how to handle it.

## 9. Error-Prone Conditional Patterns

### Pitfall 1 — Checking Null After Dereferencing

```java
// WRONG: method called before checking.
if (name.isBlank() || name == null) {
    System.out.println("missing");
}
```

When `name == null`, calling `isBlank()` throws `NullPointerException` before the right-hand side runs. Swap the order:

```java
if (name == null || name.isBlank()) {
    System.out.println("missing");
}
```

This is **null-safe** because `||` only evaluates the right-hand side when needed, but it **merges** `null` and an empty string into one state. Only use this combined form if the business logic genuinely treats both cases as equivalent.

### Pitfall 2 — Assuming a Non-Matching `instanceof` Means Null

```java
if (value instanceof String s) {
    return "STRING";
}
return "MISSING"; // Wrong meaning if value is an Integer or another object.
```

This is an illustrative method snippet. The `String` pattern may fail to match because of `null` **or** because of another type. Check `value == null` separately if `MISSING` is meant only for `null`.

### Pitfall 3 — Assuming `default` in `switch` Catches Null

```java
// Java 21: if value == null, switch still throws NPE.
return switch (value) {
    case String s -> "STRING";
    default -> "OTHER";
};
```

This is an illustrative expression inside a method. Add `case null -> "MISSING";` if `null` is allowed and needs to be handled.

### Pitfall 4 — Accessing a Nullable Component in a Guard

```java
// Dangerous if t.value() can be null:
case Text t when t.value().isBlank() -> "EMPTY"
```

This is **an illustrative case** (not a standalone program). The solution is to check `t.value() == null` first, or design `Text` so it does not accept a `null` component.

### Pitfall 5 — Merging Null, Whitespace Strings, and Unsupported Types

Using the same `"UNKNOWN"` branch makes troubleshooting difficult: you cannot tell whether the input was missing, valid data lacked content, or a developer forgot to add a new case. Only merge them if the business contract truly has one shared outcome; otherwise, use distinct results or error types.

### Pitfall 6 — Returning a Placeholder for Null and Forgetting the Error Path

A branch like `if (value == null) return "";` may prevent an NPE, but it leads callers to interpret `""` as valid empty data. Design return values that accurately represent the state, add tests, and document the API.

## 10. Workflow for Designing Null Branches in a Method

A practical approach before writing `if` or `switch`:

1. **List the input states.** Start with `null` for the outer value, then supported object types, and finally unsupported types.
2. **Decide whether `null` is valid.** If invalid, reject at the start of the method/boundary. If valid, add a dedicated branch with a clear result.
3. **Separate type conditions from data conditions.** `instanceof String s` resolves the type; `s.isBlank()` resolves the content state. For nested data, check component nullability before calling its methods.
4. **Order specific branches before general ones.** In `switch`, a guarded case must precede an unguarded general case of the same type if both could apply.
5. **Review exhaustiveness.** With open types like `Object`, define a policy for unsupported types; with `sealed`, leverage the compiler's exhaustiveness check.
6. **Test each state individually.** At minimum, cover outer `null`, component `null` if allowed, empty value, valid value, and another type/variant.

After writing, read the code from top to bottom like a decision table: for each input, is there exactly one expected path? Is anything dereferenced before non-null is guaranteed? Is any `default` or `else` branch absorbing two unrelated meanings?

## 11. Minimum Test Case Suite

For `ExplicitNullIf17` and `ExplicitNullSwitch21` above, you can use the following table as a test contract:

| Case | Input | Expected Result |
| --- | --- | --- |
| Java 17 — missing input | `route(null)` | `MISSING` |
| Java 17 — whitespace-only string | `route(" ")` | `EMPTY_TEXT` |
| Java 17 — valid string with leading/trailing spaces | `route(" Java ")` | `TEXT: Java` |
| Java 17 — integer | `route(42)` | `INT: 42` |
| Java 17 — unsupported floating-point number | `route(2.5)` | `UNSUPPORTED` |
| Java 21 — null for the entire request | `handle(null)` | `MISSING_REQUEST` |
| Java 21 — request with a null component | `handle(new Text(null))` | `MISSING_TEXT` |
| Java 21 — whitespace-only component | `handle(new Text(" "))` | `EMPTY_TEXT` |
| Java 21 — valid text component | `handle(new Text(" Java "))` | `TEXT: Java` |
| Java 21 — Count variant | `handle(new Count(7))` | `COUNT: 7` |
| Java 21 — Ping variant | `handle(new Ping())` | `PING` |

Beyond happy-path runs, test design changes:

- If you add a new subtype to `permits` without adding a covering branch in a `switch` that has no `default`, the compiler reports that the `switch` expression is not exhaustive. That is a helpful signal to update the logic.
- If you remove `case Text t when t.value() == null`, the `new Text(null)` case can cause an NPE in the `isBlank()` check branch. This shows that **component `null`** must be handled explicitly.
- If you remove `case null` from the `Request` `switch` and still call `handle(null)`, the program no longer produces the expected `MISSING_REQUEST` behavior.

Distinguish **business-result testing** from **programming-error testing**: if the contract forbids `null`, the test should verify that the method rejects the input with the specified error; do not catch the error and silently return fake data.

## 12. Practice Exercises

**Exercise 1 — Java 17 input classification.** Write a method `summarize(Object input)` supporting `String` and `Integer`. Requirements: `null` returns `"NO_INPUT"`, blank strings return `"BLANK"`, normal strings return the `strip()`ped content, integers return `"NUMBER: n"`, and other types return `"UNSUPPORTED_TYPE"`. Use `instanceof` patterns without manual casting.

**Exercise 2 — Convert to a Java 21 `switch`.** Convert the same method into a `switch` expression with `case null`, two `String` cases (one guarded), `Integer`, and `default`. Try swapping the order of the two `String` cases and observe the dominance error.

**Exercise 3 — Outer null and inner record null.** Create `sealed interface Command permits Write, Read`, `record Write(String text) implements Command`, and `record Read(int id) implements Command`. Define distinct behavior for a `null` `Command`, `Write(null)`, `Write("")`, and `Read(1)`. Write a `switch` expression and test all four paths; only call `isBlank()` when the component is known to be non-null.

**Exercise 4 — Redesign the contract.** In Exercise 3, change the rule so that `Write.text` **can never be null**. Enforce this check in a compact constructor using `Objects.requireNonNull(text, "text")`. Consider whether the `MISSING_TEXT` branch is still needed; distinguish an object-construction error from the “no command” case.

**Exercise 5 — Code quality review.** Pick a real piece of code that has a `default` returning `"Unknown"`. List the states being lumped together, design meaningful result names, and write corresponding test cases. Explain when keeping a single shared branch is a reasonable decision.

## 13. Knowledge Self-Check

1. Why is `input instanceof String text` `false` when the input is `null`, and why does that not mean `else` only receives `null`?
2. In a Java 21 `switch` expression, does `default` match a `null` selector when `case null` is absent?
3. Why is `case String s when s.isBlank()` null-safe at the input level, whereas `case Text t when t.value().isBlank()` may not be safe?
4. How does `null` for the entire `Text` differ in meaning from `null` for `Text.value`?
5. When should you return a `MISSING` value, and when should you reject immediately with `Objects.requireNonNull`?
6. Why does an exhaustive `switch` over a `sealed` type hierarchy still need a decision on how to handle a `null` selector?
7. Does your test suite separate missing data, empty data, valid data, and unsupported types?

If you can answer these questions and accurately explain every line of output from both programs, you have a solid foundation for designing explicit `null`-handling branches in Java code that uses pattern matching.

## 14. Official References for Further Reading

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): type-pattern matching conditions and variable scoping in `instanceof`.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `case null`, guards, dominance, exhaustiveness, and handling a `null` selector.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns, components, and matching rules.
- [Java Language Specification, Java SE 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): `switch` statement rules and related cases.
- [Java Language Specification, Java SE 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): `switch` expressions and exhaustiveness requirements.
- [Java SE 21 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): validating required parameters.

Apply these practices according to **the Java version your source code is actually compiled with**. With Java 17, start with a `null` pre-check and `instanceof`; with Java 21, take advantage of `case null` in `switch` when the contract allows missing input.
