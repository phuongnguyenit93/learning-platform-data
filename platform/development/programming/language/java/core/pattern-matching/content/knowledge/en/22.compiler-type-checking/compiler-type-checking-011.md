# Using the Compiler as a Design Tool in Java Pattern Matching

**The compiler does more than check syntax to generate bytecode.** In Java—especially when using **sealed types**, **records**, and **pattern matching**—compilation errors also serve as signals to refine the **data model, number of business cases, type boundaries, and control flow**. Instead of only asking “does this code run yet?”, you can design your code so the compiler forces you to answer: “Have all permitted types been handled?”, “Which branch shadows which?”, “Is this variable guaranteed to be bound?”, and “Does the return value have the right type?”.

This lesson belongs to **Java Core Pattern Matching → Compiler and type checking**, focusing on how to leverage the compiler as a **design feedback loop** (compiler-guided design), with runnable examples on **Java 21 and later**. All features used are finalized: sealed classes (Java 17, JEP 409), record patterns (Java 21, JEP 440), and pattern matching for `switch` (Java 21, JEP 441).

## 1. What Does “Using the Compiler as a Design Tool” Mean?

A sound design approach turns key assumptions of the problem into **type rules that the compiler can verify**, rather than leaving them only in comments. For example:

- If a request has only three accepted forms, model it with a **`sealed interface`** and three permitted subtypes.
- If each form carries fixed data, model it with a **`record`** using specific component types.
- If every form must be handled, use an **exhaustive `switch expression`**, preferring **not to add an unconditional `default`** when the type is a sealed hierarchy that is already fully covered.
- If a branch is only valid when a value has a certain type, use a **type pattern** or **record pattern** so the compiler tracks variable types and scopes.
- If conditions of the same type must be handled differently, use a **`when` guard**, order the branches clearly, and let the compiler check dominance.

As a result, when you extend the model or change how cases are handled, compilation errors can appear **right at the code locations that need review**.

**A limitation to understand clearly:** the compiler checks properties that can be inferred from **the source code and the type system**. It cannot by itself prove that a customer name is non-empty, an age is legal, access permissions are valid, JSON data conforms to an API contract, or the entire business logic is correct.

## 2. Starting from the Model: `sealed interface` + `record`

Suppose the system accepts only three request forms:

```java
// Java 21+ snippet, can be declared in an appropriate scope.
sealed interface Request permits Create, Delete, Ping {}

record Profile(String name, int age) {}

record Create(Profile profile, String source) implements Request {}

record Delete(String userId) implements Request {}

record Ping() implements Request {}
```

This design tells the compiler:

1. `Request` is a **sealed interface**: direct implementing classes must be in the set allowed by the `permits` clause.
2. `Create`, `Delete`, and `Ping` are distinct data types, rather than stuffing all data into a single generic object with a string `type` field and many optional fields.
3. Each record has an explicit component list: the compiler knows `Create.profile()` returns `Profile`, while `Delete.userId()` returns `String`.
4. When handling a variable of static type `Request`, the compiler knows the set of permitted variants and can check `switch` exhaustiveness.

Why does this matter more than a `"CREATE"`/`"DELETE"`/`"PING"` string? Strings are an open set of values at compile time; the compiler does not know every text value that might appear. A `sealed` type establishes a clearer **contract of variants**.

Not every problem needs a sealed hierarchy. For a simple set of constants that carry no distinct data, an `enum` may be more appropriate. Sealed + record is useful when each variant has a **different data structure** and requires branching by type.

## 3. Letting the Compiler Catch Missing `switch` Branches

Consider an incomplete `switch expression`:

```java
// INTENTIONALLY WRONG: snippet inside a method returning String.
// Variable 'request' has type Request per the declarations above.
return switch (request) {
    case Create(var profile, var source) -> "create";
    case Delete(var userId) -> "delete";
    case null -> "missing";
};
```

The compiler rejects this because the expression does not cover the `Ping` case. A `switch expression` must be **exhaustive**: every possible input value must have a branch that produces a result or completes abruptly in a valid way.

Fix it by adding:

```java
// Correct illustration (replaces the incomplete switch above).
return switch (request) {
    case Create(var profile, var source) -> "create";
    case Delete(var userId) -> "delete";
    case Ping() -> "ping";
    case null -> "missing";
};
```

Here, **no `default` is needed** because all valid variants of `Request` are covered. `case null` handles a `null` selector separately; record patterns do not match a `null` object.

### Updating the Model Prompts Updates at Call Sites

Later, the business introduces a `Suspend` request form. If you update the `Request` declaration to add `Suspend` to the `permits` list and define the corresponding record, any `switch expression` without `default` that has not yet handled `Suspend` will **no longer be exhaustive when recompiled**. This is very useful design feedback:

- The type definition records the new variant.
- The compiler points out every handling site that must cover the new variant.
- The developer modifying the code must decide what behavior `Suspend` should have at each handling point, rather than letting it silently fall into an “other” branch.

Conversely, if you put `default -> "other";` from the start, when a new variant is added the compiler may **not warn** that logic for the new type has not been designed yet. Therefore, **prefer an exhaustive switch without `default` for a sealed hierarchy when appropriate**; still use `default` when you genuinely want a fallback policy for an open set of types.

Do not treat the promise “sealed always has three types” as permanent: when source code changes and is recompiled, **the set of permitted subtypes has changed**; handling branches need to be reviewed.

## 4. The Compiler Checks Exhaustiveness, Not Business Validation

A `record` describes data shape; **it does not automatically enforce validity rules**. For example:

```java
new Profile(null, -10)
new Delete("   ")
new Create(null, "app")
```

These objects can still be constructed if the record does not enforce constraints in its constructor. The compiler knows the type of each component, but cannot infer that “a name must contain characters” or “an age must meet a threshold”.

Therefore, you can combine **nested record patterns** with a **`when` guard**:

```java
// Snippet inside switch (request).
case Create(Profile(var name, var age), var source)
        when name != null && !name.isBlank() && age >= 18 ->
        "Create: " + name + " via " + source;

case Create(var profile, var source) ->
        "Invalid create";
```

The two branches have different roles:

- The first branch matches a `Create` whose `profile` is a non-`null` `Profile`, while also checking that `name` is not null/blank and `age >= 18`.
- The second branch covers the remaining `Create` cases: `profile` is `null`, the name is invalid, the age is below the threshold, or any case that fails the guard.
- If `profile == null`, the `Create(Profile(...), ...)` branch **does not match**, whereas `Create(var profile, ...)` can still match; `var profile` may receive `null`.
- The condition `name != null && !name.isBlank()` uses short-circuit evaluation so `isBlank()` is not called on `null`.

**The compiler guarantees** that `name`, `age`, and `source` are bound with the right types in the matched branch, and it can check whether pattern ordering is valid. **The compiler does not guarantee** that a profile has valid business data if you omit the guards.

In a real system, you can also place invariants in a record’s **compact canonical constructor** so invalid objects are rejected upon creation. If you choose that approach, consider the data deserialization contract and how errors are reported to callers. Even then, the compiler does not invent invariants on its own; the designer must declare them.

## 5. The Compiler Catches Dominance and Unreachable Branches

Suppose the selector has type `Object`. The following snippet **does not compile**:

```java
// INTENTIONALLY WRONG: String branch is dominated by the supertype pattern.
String label = switch (input) {
    case CharSequence seq -> "text-like";
    case String text -> "string";
    case null -> "missing";
    default -> "other";
};
```

`String` implements `CharSequence`. Thus, every value matching `String text` is already captured by the preceding `case CharSequence seq`, making the `String` branch unreachable. The compiler detects a **dominated case label**.

The correct ordering is **narrower branches before broader branches**:

```java
// Valid snippet with Object input.
String label = switch (input) {
    case String text -> "string";
    case CharSequence seq -> "text-like";
    case null -> "missing";
    default -> "other";
};
```

Similarly, with two branches of the same type:

```java
// INTENTIONALLY WRONG: unguarded String precedes the guarded one.
String label = switch (input) {
    case String text -> "text";
    case String text when text.isBlank() -> "blank";
    case null -> "missing";
    default -> "other";
};
```

You must place the `when text.isBlank()` branch before the general `String` branch. **A dominance error is a design signal**: you have ordered conditions incorrectly or one branch has become redundant.

The compiler cannot determine every mathematical relationship between arbitrary guards. For instance, whether two distinct business conditions overlap still requires design and testing. Therefore, do not assume “compiles successfully” means the guards classify all data correctly.

## 6. Flow Scoping: The Compiler Helps Design Control Flow

Pattern variables are only in scope where the compiler can prove the pattern has matched. For example:

```java
// Snippet inside a method returning int.
if (!(input instanceof String text)) {
    return -1;
}
return text.length();
```

Here, if `input` is not a `String`, the method returns immediately. Any execution path reaching `return text.length()` must have passed the matching branch, so `text` is considered **definitely matched** at that point.

By contrast, the following **does not compile**:

```java
// INTENTIONALLY WRONG: the non-matching branch can still fall through.
if (!(input instanceof String text)) {
    System.out.println("Not text");
}
return text.length(); // 'text' is not definitely bound.
```

The compiler cannot guarantee that `text` exists along the non-matching path. This is why **guard clauses + early return** both reduce nesting and clearly express the preconditions of the main logic.

With compound conditions:

```java
// Valid: the right-hand side of && only runs when the pattern has matched.
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

`text` can be used on the right-hand side of `&&`. However, replacing it with `input instanceof String text || text.isBlank()` is invalid, because the right-hand side of `||` runs precisely when the pattern **did not match**. The compiler prevents accessing an unbound variable on that path.

Treat scoping errors as a design question: *“Which path allows unverified data to still be used?”* Sometimes the right answer is not adding a cast, but **reorganizing control flow**.

## 7. The Compiler Protects the Result Type of a `switch expression`

Pattern matching in `switch` can appear in an expression whose result must be compatible with a target type:

```java
// Valid snippet with Request request.
int priority = switch (request) {
    case Create(var profile, var source) -> 3;
    case Delete(var userId) -> 2;
    case Ping() -> 0;
    case null -> -1;
};
```

All branches yield a value of type `int`; the compiler checks that the entire expression can produce an `int`. If you replace `case Ping() -> 0;` with `case Ping() -> "none";`, the expression is no longer compatible with `int` and will be rejected.

For multi-statement branches, use `yield` to produce a value:

```java
// Valid snippet, part of a switch expression returning int.
case Create(var profile, var source) -> {
    int base = 3;
    int score = source == null ? base : base + 1;
    yield score;
}
```

This is **a sample branch** and must be placed inside an appropriate `switch expression`. `yield` supplies a value for the expression; `return` (when inside a method) exits the method. The two statements cannot be substituted for each other arbitrarily.

The compiler checks that a block branch produces a value or completes abruptly as required. It does not prove that a `3`/`4` scoring scale is right for the product; the scoring scale is a business choice that must be tested.

## 8. Notes on Generic Types, `null`, and Runtime Types

The compiler can block certain **unsafe** generic checks, but it cannot recover all type information removed by **type erasure**.

```java
record Box<T>(T value) {}

// INTENTIONALLY WRONG when input has type Object.
if (input instanceof Box<String>(var text)) {
    System.out.println(text);
}
```

With `Object input`, checking `Box<String>` directly requires a generic type-argument check that cannot be performed safely at runtime. One way that compiles on Java 21+ is to check the record itself with a wildcard and **the component value**:

```java
// Valid snippet with Object input.
if (input instanceof Box<?>(String text)) {
    System.out.println(text.toUpperCase());
}
```

This pattern states that `input` is a `Box` whose **component currently holds a non-`null` `String`**; it does not prove that the object’s original type argument was strictly `Box<String>`. A `Box<CharSequence>` holding a `String` can still match.

Design takeaway: a type error can indicate that an API boundary is too wide (everything passes through `Object`), prompting you to consider more precise static types, a sealed hierarchy, or validating data at the boundary. **Do not use raw types, unchecked casts, or add `default` just to silence errors** without understanding the root cause.

### The Compiler and `null`

- Type patterns `case String s` and record patterns `case Create(...)` do not match a `null` selector.
- A `switch` over a reference selector that can receive `null` needs explicit handling if `null` is a valid case; `default` does not automatically replace a `case null` policy.
- A record pattern with a `var field` component can still bind a **`null` reference component**.
- In general, the Java compiler does not perform comprehensive nullness checking for all references. Validation, testing, or additional analysis tools are needed when nullness matters.

## 9. Complete Example: Designing for Compiler Support

Create the file **`CompilerDrivenDesignDemo.java`**:

```java
public class CompilerDrivenDesignDemo {
    sealed interface Request permits Create, Delete, Ping {}

    record Profile(String name, int age) {}

    record Create(Profile profile, String source) implements Request {}

    record Delete(String userId) implements Request {}

    record Ping() implements Request {}

    static String handle(Request request) {
        return switch (request) {
            case Create(Profile(var name, var age), var source)
                    when name != null && !name.isBlank() && age >= 18 ->
                    "Create: " + name + " via " + source;

            case Create(var profile, var source) ->
                    "Invalid create";

            case Delete(var userId)
                    when userId != null && !userId.isBlank() ->
                    "Delete: " + userId;

            case Delete(var userId) ->
                    "Invalid delete";

            case Ping() -> "Pong";

            case null -> "Missing request";
        };
    }

    static String review(Object input) {
        if (!(input instanceof Create(var profile, var source))) {
            return "Not create";
        }
        if (profile == null) {
            return "Missing profile";
        }
        return "Review " + profile.name() + " via " + source;
    }

    public static void main(String[] args) {
        System.out.println(handle(
                new Create(new Profile("Lan", 22), "web")));
        System.out.println(handle(
                new Create(new Profile("Minh", 16), "app")));
        System.out.println(handle(
                new Create(null, "app")));
        System.out.println(handle(new Delete("user-7")));
        System.out.println(handle(new Delete("  ")));
        System.out.println(handle(new Ping()));
        System.out.println(handle(null));

        System.out.println(review(
                new Create(new Profile("Lan", 22), "web")));
        System.out.println(review(new Create(null, "web")));
        System.out.println(review(new Ping()));
    }
}
```

Compile with JDK 21 or later, naming the file to match the `public class`:

```bash
javac --release 21 -encoding UTF-8 CompilerDrivenDesignDemo.java
java CompilerDrivenDesignDemo
```

Output:

```text
Create: Lan via web
Invalid create
Invalid create
Delete: user-7
Invalid delete
Pong
Missing request
Review Lan via web
Missing profile
Not create
```

### Analyzing the Guarantees Encoded in the Program

**1. Three variants of `Request`**

`sealed interface Request` and its implementing records form a type set known to the compiler. In `handle`, the `Create`, `Delete`, and `Ping` branches provide full coverage for every declared non-null `Request`, so no `default` is needed.

**2. Two-level validation in the `Create` branch**

`Create(Profile(var name, var age), var source)` is a nested record pattern. It matches when `Create.profile()` holds an actual `Profile`. The guard checks `name != null`, non-blank name, and `age >= 18`. The case `Create(null, "app")` does not pass the nested pattern, but the `Create(var profile, var source)` branch catches it and returns `"Invalid create"`.

**3. `Delete` branch with guard and fallback**

`Delete("user-7")` satisfies the guard. `Delete("  ")` matches the record pattern but fails `!userId.isBlank()`, so it is handled by the next `Delete` branch. The compiler verifies that the broader branch does not precede the narrower guarded branch.

**4. `Ping()` is a record with no components**

The pattern `case Ping()` matches the `Ping` record type without destructuring any data. If this branch is removed, the `switch expression` over `Request` no longer covers the entire type set.

**5. `review` uses flow scoping**

`!(input instanceof Create(var profile, var source))` is paired with `return` when it does not match. Consequently, `profile` and `source` are in scope outside the `if` on the success path. Because `profile` can still be `null`, the method checks it before calling `profile.name()`.

**6. Type contracts do not sanitize input automatically**

The program intentionally does not validate every rule on `source` or fields outside the scope of the example. That is where additional **validation and testing** are needed in a real system, rather than expecting the compiler to complete business logic on its own.

## 10. Step-by-Step Compiler-Guided Design Workflow

<escape>1.</escape> **Model the business domain.** Ask: which variants are allowed? What data does each variant carry? Use `enum`, `sealed interface/class`, `record`, or standard types according to actual needs.

<escape>2.</escape> **Write handling logic with explicit coverage.** For a sealed hierarchy, write a `switch expression` matching each variant and try **omitting `default`**. Let the compiler point out missing branches instead of writing a default branch that hides new cases.

<escape>3.</escape> **Compile early.** Use `javac` or your IDE. Read errors by asking “what information is the model missing?” before fixing them. For example: not exhaustive → a variant is missing; dominated → case ordering/meaning has an issue; variable not in scope → there is a path where the match is not proven.

<escape>4.</escape> **Fix structure, not just error messages.** If you frequently cast from `Object`, revisit the API types or data ingestion boundaries. If you have to write dozens of unrelated guards, consider splitting methods or lifting constraints into appropriate types/constructors.

<escape>5.</escape> **Test model changes.** Add a permitted subtype on a separate development branch, recompile, and see which exhaustive `switch` expressions need updating. If the compiler does not flag them, check whether a `default` branch is masking the new case.

<escape>6.</escape> **Use warnings to strengthen signals.** Depending on the project, you can enable `-Xlint:all` to inspect `javac` warnings and consider `-Werror` to fail the build on warnings. Use `--release 21` when you need to guarantee source/API compatibility with Java 21; avoid relying on newer syntax that only exists in the locally installed JDK.

<escape>7.</escape> **Combine with testing.** Run unit tests for business rules, boundary values, `null`, guards, authorization logic, I/O, and transactions. The compiler proves **type validity and control flow within its scope**, not that the program does what users expect.

Example command for projects using JDK 21+:

```bash
javac --release 21 -Xlint:all -encoding UTF-8 CompilerDrivenDesignDemo.java
java CompilerDrivenDesignDemo
```

You can add `-Werror` in CI once the team has addressed and actively manages relevant warnings; avoid enabling it unconditionally on a codebase with many uncategorized warnings.

## 11. Table of Compiler Errors as Design Signals

| Symptom | What is the compiler warning about? | What to review |
| --- | --- | --- |
| `switch expression does not cover all possible input values` or equivalent diagnostic | Not all possible types/cases are covered | Add the proper branch for each variant; review the sealed hierarchy |
| `case label is dominated` | An earlier case already covers a later case | Place narrower branches or specific guards first |
| `cannot find symbol` for a pattern variable outside a branch | The variable is not in a scope where the match is proven | Use flow scoping properly or reorganize guards/returns |
| `incompatible types` between a branch result and the target type | A branch produces a value that violates the result type contract | Unify result types; consider a clearer result type |
| Unchecked cast/conversion with generics | The compiler cannot prove type safety | Preserve generic information in the API; use wildcard + specific component pattern checks |
| Record pattern has the wrong number of components | The number of destructuring positions does not match the record structure | Specify all component patterns in the exact order |
| Missing `null` handling at runtime despite compiling | Nullness is not guaranteed solely by the standard Java type system | Define a `null` policy, add validation and tests |
| Code still compiles even though a new case falls into `default` | The fallback masked the impact of extending the model | Keep `default` only when a fallback is an intentional design choice |

Exact error messages may vary by JDK, error location, and syntax. The table above describes **categories of issues**, not exact word-for-word compiler output.

## 12. Practice Exercises and Verification Guide

Given the model:

```java
sealed interface Event permits Login, Logout {}
record Login(String username) implements Event {}
record Logout(String username) implements Event {}
```

**Exercise 1 — Exhaustiveness.** Write `String describe(Event event)` using a `switch expression` that returns `"login"` for `Login`, `"logout"` for `Logout`, and `"missing"` for `null`, **without `default`**.

**Answer:**

```java
static String describe(Event event) {
    return switch (event) {
        case Login(var username) -> "login";
        case Logout(var username) -> "logout";
        case null -> "missing";
    };
}
```

**Exercise 2 — Adding a variant.** Add `record Locked(String username) implements Event {}` to the permitted subtypes. If `describe` is not updated, what happens on recompilation?

**Answer:** The `switch expression` is no longer exhaustive, so the compiler requires handling `Locked`. If there were a `default` covering all remaining types, the error might not appear. This is why you avoid `default` when you want the compiler to prompt updates at every site handling new variants.

**Exercise 3 — Dominance.** Why is the following snippet wrong?

```java
// INTENTIONALLY WRONG with Object input.
String text = switch (input) {
    case Object obj -> "any";
    case String value -> "string";
};
```

**Answer:** The `Object obj` pattern covers every non-`null` value of type `String`, so `case String value` is dominated. In addition, the `null` selector must be considered separately: it is not handled automatically by a general type pattern. Reorder the branches so `String` comes before `Object` if that is what you need, and add `case null` when you want to support null.

**Exercise 4 — Flow scoping.** Write a guard clause for `Object input`: if it is not a `Login`, return `"Not login"`; if it is a `Login`, return `username` in uppercase, while handling `username == null` with `"No name"`.

**Answer:**

```java
static String loginLabel(Object input) {
    if (!(input instanceof Login(var username))) {
        return "Not login";
    }
    if (username == null) {
        return "No name";
    }
    return username.toUpperCase();
}
```

The compiler can prove `username` is bound after the guard clause; checking for `null` is the responsibility of business code.

## 13. Key Takeaways

- **Compiler-guided design** means proactively modeling key assumptions with types and control flow so the compiler can verify them.
- **Sealed hierarchies** declare the set of variants; **records** describe structured data; **pattern matching** handles variants by type and components.
- **Exhaustive `switch expression` without `default`** lets the compiler warn when a case is missing or when a sealed hierarchy is extended.
- **Dominance** catches shadowed branches; **flow scoping** catches places where a pattern variable is not definitely bound; **result typing** protects the output type.
- **The compiler does not replace validation and testing**: data can still be `null`, violate business rules, lack permissions, or fail external contracts even when the program compiles.
- A good workflow is **design types → write patterns and handlers → compile → read errors as design feedback → refine model/flow → test**.

Official references: [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Oracle — Pattern Matching for switch (Java 21)](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
