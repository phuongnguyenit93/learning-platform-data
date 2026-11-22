# Scope of Pattern Variables in `when` (Java 21)

## 1. The Core Question: Which Variables Actually Exist in a Guard?

In Java 21, `switch` can use a *type pattern* or a *record pattern* in a `case` label, accompanied by an additional `when` condition (*guard*). For example:

```java
static String classify(Object input) {
    return switch (input) {
        case String text when text.isBlank() -> "blank";
        case String text -> "text: " + text;
        case null -> "missing";
        default -> "other";
    };
}
```

This is a Java 21 method placed inside a class. `String text` declares the **pattern variable `text`**; only if the selector matches `String` does Java evaluate `text.isBlank()`. Therefore, **`text` can be used inside the `when` expression** and in the expression to the right of `->` in the corresponding branch. If the guard is false, that branch is not selected, and the runtime continues checking other matching labels.

More importantly: a guard itself can contain an `instanceof` operation that declares a *new pattern variable*, and that new variable can also be used in the case body when the guard is **definitely true**. This scope is based on the **definitely matched** rule, not solely on the position of curly braces.

Goals of this lesson:

- Distinguish between variables declared **in the case pattern** and variables declared **inside the guard**.
- Know which variables are in scope in `when`, in the `case ->` body, in `yield` blocks, and in a `switch statement`.
- Understand how `&&`, `||`, negation, and true/false execution paths affect which variables are brought into scope.
- Avoid name collisions, using variables across different cases, reassigning variables referenced by a guard, and dereferencing nullable values.
- Write examples that run with official Java 21, without relying on preview features.

**Version:** `instanceof` type patterns became official in Java 16; pattern matching for `switch` and `when` guards became official in **Java 21** (JEP 441). Record patterns also became official in Java 21 (JEP 440). The programs in this lesson are compiled with `javac --release 21`.

## 2. Three Steps of a Case with `when`

Read the following statement in exact order:

```java
case String text when text.length() >= 4 -> "long: " + text;
```

This is an **illustrative label/branch body**, which needs to be placed inside a `switch` with a compatible selector. Execution flow:

1. Java checks whether the selector **matches the pattern `String text`**. If not, the case is skipped; `text` is not bound for this branch.
2. If it matches, Java has `text` of type `String`, and then **evaluates `when text.length() >= 4`**. The guard only runs after the variable has been bound.
3. If the guard is `true`, Java selects the branch and executes the body `"long: " + text`; `text` remains in scope there. If the guard is `false`, the branch is not selected; Java continues checking the remaining labels.

Conceptual model:

```text
Selector
   |
   v
Matches pattern in case?
   |-- No --> try next case
   |
  Yes --> variables declared by the pattern are bound
   |
   v
Evaluate when (guard)
   |-- false --> try next case
   |
  true --> execute case body (with definitely matched variables)
```

This is a flow diagram, not Java syntax. The diagram does not depict exceptions: if the pattern or guard throws an exception, the `switch` completes abruptly and **does not automatically fall through to the next case**.

### Underlying Language Rules

The Java Language Specification (JLS 21) §6.3.3 specifies:

- A pattern variable declared in a **case pattern** is *definitely matched* in the **guard** of that same case.
- A **guard** can introduce additional pattern variables if the guard expression introduces them when **its result is true**.
- Variables introduced by a case label are *definitely matched* in the corresponding **switch rule body**, including the expression after `->`, a block, or a `throw` statement (JLS §6.3.1.6 and §6.3.2.6).

That is why Java allows using `text` in both `when` and the branch body, while prohibiting arbitrary use of it in other cases.

## 3. Variables Declared in the Case Pattern: Usable in `when` and the Branch Body

### Type Pattern

```java
static String describe(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text when text.length() > 6 -> "long: " + text;
        case String text -> "short: " + text;
        case Integer number -> "number: " + number;
        case null -> "missing";
        default -> "other";
    };
}
```

Notable points:

- Each `case String text` **declares a separate variable**. Reusing the same name `text` in independent switch rules is valid; it is not a single variable passed across multiple cases.
- `text` in the guard is guaranteed to be a `String` object, so `isBlank()` and `length()` can be called without casting.
- The guard of the second case is only evaluated if the first case was not selected and the second case's pattern matches. A long `String` consisting solely of whitespace will enter the `blank` case.
- `Integer number` only provides the variable `number` for the integer case; `text` cannot be referenced there.
- `case null` and `default` **do not introduce** the pattern variable `text`.

When a case has a false guard, its variable is not "retained" for use in the next case. Each case is a separate match with its own declaration.

### Record Pattern and Multiple Component Variables

Suppose we have:

```java
record Point(int x, int y) {}
```

In `switch (value)` with a compatible selector type:

```java
case Point(int x, int y) when x == y -> "diagonal: " + x;
case Point(int x, int y) -> "point: " + x + "," + y;
```

`x` and `y` are declared from **component type patterns** inside the record pattern. They are already bound when the guard `x == y` runs and remain usable in the selected case body. `Point(2, 5)` fails the first guard and enters the next general `Point` case.

If record patterns are nested, variables from valid component patterns are also usable in the guard and branch body, provided naming and type rules are met. Not every pair of parentheses `(...)` creates a Java variable scope; how far a variable remains in effect still follows pattern scope rules.

## 4. Variables Declared Directly Inside `when` Using `instanceof`

This is the most easily overlooked point: **`when` does not only read variables from the pattern on the left; it can declare additional pattern variables using `instanceof`**.

For example, suppose we have:

```java
record Payload(Object data) {}
```

A valid branch:

```java
case Payload payload
        when payload.data() instanceof String text
             && !text.isBlank()
        -> "payload-text:" + text.strip();
```

In this label there are **two declaration sources**:

| Name | Where is it declared? | Where is it in scope? |
| --- | --- | --- |
| `payload` | Outer pattern `Payload payload` | In the guard and the selected case body |
| `text` | `payload.data() instanceof String text` inside the guard | On the right-hand side of `&&` and in the case body when the guard is true |

Execution flow with `new Payload(" Java ")`:

1. The selector matches `Payload payload`.
2. The guard checks `payload.data() instanceof String text`; if it succeeds, `text` is `" Java "`.
3. Because the `&&` operator only evaluates the right-hand side when the left-hand side is true, `text` is already bound when `!text.isBlank()` runs.
4. The guard is true: Java runs the branch body, so `text.strip()` is valid and returns `"Java"`.

With `new Payload(42)`, `instanceof String` is false; the right-hand side of `&&` does not run and this branch is not selected. The same applies to `new Payload(null)`. No `text` variable is used on the non-matching path.

**Rule point:** A guard of the form `a instanceof Type t && conditionUsingT` introduces `t` **when the entire guard is true**. By JLS §6.3.3, `t` is in scope in the case body. This is a concrete application of *flow scoping*, not Java "automatically exporting every variable from a guard".

### Declaring Different Types Across Separate Guards

```java
case Payload p when p.data() instanceof String text ->
        "string:" + text;
case Payload p when p.data() instanceof Integer n ->
        "integer:" + n;
case Payload p ->
        "other-payload";
```

Each guard matches the `data` field itself and introduces its own variable (`text` or `n`). The unguarded `Payload p` case at the end is a fallback branch for remaining payloads. The name `p` in each label refers to an independent variable.

## 5. Why `&&` Is Valid While `||` Usually Is Not

Consider the following:

```java
case Payload p when p.data() instanceof String text
                    && text.length() >= 3
        -> "ok:" + text;
```

This is a **valid illustrative case**: `&&` has *short-circuit* behavior. When reaching `text.length()`, the left-hand expression must be true, so `text` already has a value. When the entire guard is true, `text` is also definitely matched for use in the body.

Conversely:

```java
// INTENTIONALLY INVALID: text is not guaranteed to be bound on the right side of ||.
case Payload p when p.data() instanceof String text
                    || text.isEmpty()
        -> "invalid";
```

The right-hand side of `||` runs when the left-hand side is **false**. In that case, `text` was never introduced along the true branch of `instanceof`, so calling `text.isEmpty()` is invalid with respect to variable scope.

Even if the right-hand side does not use `text`, the guard can still be true when the first pattern is false:

```java
// INTENTIONALLY INVALID if the body needs text: allowAny can be true when instanceof is false.
case Payload p when p.data() instanceof String text || allowAny
        -> "text:" + text;
```

Suppose `allowAny` is an already declared boolean variable. If `allowAny` is true, the entire guard is true even though `text` is not guaranteed to have a value. Therefore `text` is not considered definitely matched in the case body.

**How to fix:** Separate the cases, or write an `&&` condition that only uses the variable after the pattern has matched.

### Negation Reverses the Matching Condition

```java
// INTENTIONALLY INVALID: when !(...) is true, the String pattern did not match.
case Payload p when !(p.data() instanceof String text)
        -> "not text:" + text;
```

In this branch, `text` cannot be guaranteed to have a value when the guard is true. To describe a type that is not `String`, there is no need to declare a variable inside the negated condition:

```java
case Payload p when !(p.data() instanceof String)
        -> "not a string";
```

If you need to use `text`, place the handling in the successful `instanceof String text` branch instead of the negated branch.

## 6. Scope in `switch` Expressions, `yield` Blocks, and `switch` Statements

### 6.1. `->` Branch Returning an Expression

```java
static String label(Object value) {
    return switch (value) {
        case String s when s.startsWith("A") -> "A:" + s;
        case String s -> "text:" + s;
        case null -> "missing";
        default -> "other";
    };
}
```

In each branch, `s` only lives within the region allowed by pattern scope: the corresponding guard and rule body. There is no shared `s` declaration after `};`.

### 6.2. `->` Branch Using a Block and `yield`

```java
static String normalize(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> {
            String cleaned = s.strip();
            yield "clean:" + cleaned;
        }
        case String s -> "blank";
        case null -> "missing";
        default -> "other";
    };
}
```

The variable `s` is usable inside the `{ ... }` block of the selected rule; `cleaned` is a **new local variable** belonging only to that block. `yield` returns the value of the `switch expression`. Using `return` instead of `yield` in this block is incorrect for this role.

### 6.3. `switch` Statement

Java 21 also supports pattern matching in a `switch statement`:

```java
static void print(Object input) {
    switch (input) {
        case String s when s.isBlank() ->
                System.out.println("blank");
        case String s ->
                System.out.println("text:" + s);
        case null ->
                System.out.println("missing");
        default ->
                System.out.println("other");
    }
}
```

For each switch rule, the pattern variable is in scope in the **statement or block** belonging to that rule. When the first branch is selected, `s` is usable in both the guard and the `println` call, but cannot be used in statements of other cases or after the entire `switch`.

**Note on colon labels (`case ...:`):** The JLS also defines scope for *switch labeled statement groups*. However, multiple shared labels, *fall-through* flow, and variables only being assigned when a pattern matches create constraints that are hard to read; prefer `->` for learning examples and type-specific independent handling.

## 7. Boundaries That Cannot Be Crossed: Other Cases, `default`, `null`, After `switch`

A variable declared by a case is **not** a method variable declared for all branches.

Intentionally invalid example:

```java
static String wrong(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case Integer n -> text;  // INVALID: text does not belong to the Integer case.
        default -> "other";
    };
}
```

When the selector is an integer, `text` was never bound for this case. Fix: use `n` in the `Integer` case or a result value that does not require `text`.

Another invalid example:

```java
static String wrongAfter(Object value) {
    String answer = switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text -> text;
        default -> "other";
    };
    return text; // INVALID: no text is introduced after the switch.
}
```

The local variable `answer` (assigned from the `switch` result) is the valid variable afterward. The pattern variable `text` is only for the relevant branches.

For `case null` and `default`, no variable from `case String text` automatically appears. In Java 21, `case null` handles null input; `default` in a regular pattern switch does not automatically handle null. Without an appropriate null-handling branch, a null selector can lead to a `NullPointerException` before a regular case body is selected.

## 8. The `final` / Effectively Final Requirement for Variables Referenced by a Guard

This is an **important restriction in Java 21**: according to JLS §14.11.1, **any local variable, method parameter, or exception parameter used in a guard that is not declared by the guard itself** must be `final` or *effectively final*.

This also applies to **a pattern variable declared by the case pattern** when that variable is referenced by the guard.

### Valid Example: Only Reading the Case Variable in the Guard

```java
static String safe(Object value) {
    int minLength = 3; // Not reassigned: effectively final.
    return switch (value) {
        case String text when text.length() >= minLength -> {
            String result = text.strip();
            yield "accepted:" + result;
        }
        case String text -> "too-short:" + text;
        case null -> "missing";
        default -> "other";
    };
}
```

Here, neither `text` (used in the guard) nor `minLength` (from outside) is reassigned. The variable `result` is a different local variable used to compute the value after the branch is selected.

### Invalid Example: Reassigning a Pattern Variable Used by a Guard

```java
// INTENTIONALLY INVALID: pattern variable s is referenced by the guard,
// yet reassigned in the same rule.
static String notEffectivelyFinal(Object value) {
    return switch (value) {
        case String s when s.length() > 2 -> {
            s = s.strip(); // INVALID under the guard's effectively final rule.
            yield s;
        }
        case String s -> s;
        default -> "other";
    };
}
```

Although pattern variables in general have **not been `final` by default** since Java 16, once referenced by a guard, the specific rule for guards can forbid reassignment as shown above. Do not conclude that "pattern variables are always final"; the difference lies in **whether the variable is used by a guard**.

Fix by creating a new variable:

```java
case String s when s.length() > 2 -> {
    String normalized = s.strip();
    yield normalized;
}
```

This is an illustrative case fragment for a `switch expression`. The same pattern applies to outer variables:

```java
int limit = 3;
// If limit is used in a guard and reassigned in the method,
// it is no longer effectively final.
```

If the programmer later writes `limit++` in the same method, a guard referencing `limit` may fail to compile. Use a constant or a final local value determined before entering the `switch`.

## 9. Other `when` Constraints Affecting Variable Usage

### The Guard Must Be `boolean` or `Boolean`

```java
// VALID:
case String text when text.length() > 0 -> "nonempty";

// INTENTIONALLY INVALID: length() returns int, not boolean.
case String text when text.length() -> "invalid";
```

If a guard returns `Boolean`, Java performs unboxing. A null `Boolean` value can throw a `NullPointerException` when unboxed; that does **not** mean the guard is false and jumps to another case.

Example avoiding null unboxing:

```java
// Safe boolean if check(t) may return a null Boolean:
case String text when Boolean.TRUE.equals(check(text)) -> "accepted";
```

`check(text)` is an **illustrative call** that must be defined in the class. If a guard depends on nullable data or methods with side effects, consider checking or restructuring the logic rather than letting unexpected exceptions occur during case selection.

### The Guard Must Follow a Case Pattern

```java
// INTENTIONALLY INVALID: when is not attached to a case pattern.
case 1 when enabled -> "one";
```

In Java 21, `when` is used to add a condition to a **pattern**, not a constant case. `when` is a contextual keyword in a case label; do not use the old preview `&&` syntax after a pattern:

```java
// INTENTIONALLY INVALID in stable Java 21 syntax:
case String s && s.isBlank() -> "blank";
```

Correct form:

```java
case String s when s.isBlank() -> "blank";
```

A guard that is a constant expression `false` is rejected at compile time; a constant `true` guard may be treated like an unguarded case in dominance checks, not as a special variable-scoping mechanism.

### Name Scope Still Checks for Conflicts

```java
static String naming(Object input) {
    String text = "outer";
    return switch (input) {
        case String text when text.isBlank() -> "blank"; // INVALID: duplicate name.
        default -> "other";
    };
}
```

This is an intentionally non-compiling example: a pattern variable cannot shadow a local variable that is already in scope in a conflicting scope. Choose a different name:

```java
case String candidate when candidate.isBlank() -> "blank";
```

Conversely, two separate `case String text` branches can redeclare the same name because switch rules have separate scopes. Avoid confusing **reusing a name in separate cases** with **redeclaring a name in the same scope**.

## 10. Case Ordering, Dominance, and the False-Guard Path

Consider:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s;
    default -> "other";
};
```

For `"Java"`, the `String` pattern in the first branch matches, but the guard `isBlank()` is **false**; Java continues to evaluate the second `String` branch. The second branch **declares a different variable `s`** and produces the result.

If the unguarded `String` case is placed first:

```java
// INTENTIONALLY INVALID due to dominance:
return switch (value) {
    case String s -> "any";
    case String s when s.isBlank() -> "blank";
    default -> "other";
};
```

The first case already covers every non-null `String`, dominating the guarded branch after it; Java rejects this at compile time. Practical rule: **specific guards first, general cases of the same type after**.

A guarded case only accepts a subset of the values matching the pattern. If a `switch expression` must be exhaustive, writing only:

```java
// INTENTIONALLY INVALID because it lacks handling for Strings that fail the guard
// and other types that may arrive.
return switch (value) {
    case String s when s.length() >= 3 -> "long";
};
```

is not enough; an appropriate catch-all branch is needed. With a selector of type `Object`, `default` is typically required, along with `case null` when explicit null handling is desired. With a `sealed` hierarchy, you can list all subtypes using unguarded cases so the compiler can verify exhaustiveness.

## 11. Complete Example 1: Scope in Type Patterns, Record Patterns, and Guards

Create the file **`WhenScopeDemo21.java`** with the following content:

```java
public class WhenScopeDemo21 {

    record Payload(Object data) {}
    record Point(int x, int y) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";

            case Payload p
                    when p.data() instanceof String text
                         && !text.isBlank() ->
                    "payload-text:" + text.strip();

            case Payload p
                    when p.data() instanceof Integer n
                         && n >= 0 ->
                    "payload-int:" + n;

            case Payload p -> "payload-other";

            case Point(int x, int y) when x == y ->
                    "diagonal:" + x;

            case Point(int x, int y) ->
                    "point:" + x + "," + y;

            case String s when s.isBlank() -> "blank";

            case String s -> "string:" + s.strip();

            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe(new Payload(" Java ")));
        System.out.println(describe(new Payload(7)));
        System.out.println(describe(new Payload(null)));
        System.out.println(describe(new Point(2, 2)));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe("  "));
        System.out.println(describe(" hi "));
        System.out.println(describe(1.5));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 --release 21 WhenScopeDemo21.java
java WhenScopeDemo21
```

Exact output:

```text
null
payload-text:Java
payload-int:7
payload-other
diagonal:2
point:2,5
blank
string:hi
unsupported
```

**Comparing each scope type:**

- `Payload p` declares a variable in the outer pattern; `p` is in scope in the guard and in the selected rule body.
- `instanceof String text` in the guard declares an additional `text`. Thanks to `&&`, `text` is in scope when checking `!text.isBlank()`, and when the guard is true, the rule body can also use `text.strip()`.
- Similarly, `Integer n` is in another guard, and `n` is usable when computing the result `payload-int:7`.
- `new Payload(null)` does not match `instanceof String` or `instanceof Integer`; it enters the unguarded `Payload p` branch without accidentally accessing an unbound variable.
- `Point(int x, int y)` declares `x` and `y` from the record pattern; both variables are already in scope in the guard `x == y`. In the next `Point` case, those two names are new declarations.
- `String s` in the two string cases are two independent pattern variables, usable in their respective guards and case bodies.
- `default` does not have access to `text`, `n`, `x`, `y`, or `s` from other cases.

## 12. Complete Example 2: Blocks, `yield`, and `switch` Statements

Create the file **`GuardScopeBlock21.java`**:

```java
public class GuardScopeBlock21 {

    record Box(Object content) {}

    static String show(Object value, int minLength) {
        return switch (value) {
            case Box box
                    when box.content() instanceof String text
                         && text.length() >= minLength -> {
                String normalized = text.strip();
                yield "accepted:" + normalized;
            }

            case Box box -> "rejected";
            case null -> "missing";
            default -> "unsupported";
        };
    }

    static void log(Object value) {
        switch (value) {
            case String name when name.isBlank() ->
                    System.out.println("blank");
            case String name ->
                    System.out.println("name:" + name);
            case null ->
                    System.out.println("missing");
            default ->
                    System.out.println("other");
        }
    }

    public static void main(String[] args) {
        System.out.println(show(new Box(" Java "), 4));
        System.out.println(show(new Box("go"), 4));
        System.out.println(show(new Box(null), 4));
        System.out.println(show(null, 4));
        System.out.println(show(42, 4));

        log("   ");
        log("Mai");
        log(null);
    }
}
```

Run commands:

```bash
javac -encoding UTF-8 --release 21 GuardScopeBlock21.java
java GuardScopeBlock21
```

Output:

```text
accepted:Java
rejected
rejected
missing
unsupported
blank
name:Mai
missing
```

Explanation:

- `box` is declared in the case pattern; `text` is declared **inside `when`** and introduced by the guard when true.
- `text` is valid in the block to the right of `->`; `normalized` is declared only within that block itself. `yield` returns a value for the `switch expression`, without declaring any outer variable.
- `minLength` is a method parameter referenced by the guard and **is not reassigned**. Therefore, it satisfies the effectively final requirement.
- If `Box` contains `null`, `instanceof String text` returns false, and the branch body with `text` does not run; the next `case Box box` branch produces `rejected`.
- In `log`, `name` belongs only to the corresponding guard and statement rule. The two `String name` branches remain two separate declarations. `case null` does not have `name`.

## 13. Typical Errors to Distinguish

| Situation | Reason | How to Fix |
| --- | --- | --- |
| `case String s when s.isBlank()` | **Valid**: `s` from the case pattern is usable in the guard | Keep as is if it matches business logic |
| `case Box b when b.content() instanceof String s && !s.isBlank() -> s` | **Valid**: `s` is declared in the guard when true and usable in the body | Keep as is if the selector and `Box` fit |
| `... instanceof String s || s.isBlank()` | `s` is not matched when the right side of `||` runs | Use `&&` or split into separate branches |
| `... instanceof String s || allowAny -> s` | The guard can be true via `allowAny` while `s` is unmatched | Do not use `s` in the body; split branches |
| `when !(x instanceof String s) -> s` | The guard is true when the pattern does not match | Remove the reference to `s` or handle the positive case |
| Using `s` in an `Integer` case | `s` from the `String` case is not in scope in another case | Declare/use variables belonging to the current branch |
| Using `s` after the entire `switch` | Pattern variables are not exported outside the case rule | Assign the `switch` result to a local variable |
| Reassigning `s` in a branch body with `when s...` | `s` is referenced by the guard, so it must be final/effectively final | Create a `normalized` variable; do not reassign `s` |
| Modifying an outer local variable referenced by a guard | Violates the effectively final requirement | Keep the variable unchanged or compute its value before the switch |
| `case String s when s.length()` | The guard returns `int`, not `boolean`/`Boolean` | Use a comparison, e.g., `s.length() > 0` |
| Guard returns `Boolean null` | Can throw an error during unboxing | Use a guaranteed boolean condition or `Boolean.TRUE.equals(...)` |
| `case 1 when ...` | `when` only goes with a case pattern | Use a type pattern + guard or handle the constant separately |
| General pattern before a guarded case | The later case may be dominated | Place specific guards before general cases |
| Guard dereferences a nullable field | The outer pattern does not prove components are non-null | Use `instanceof` / check for null first |

These are two **different** kinds of errors: the compiler catches scope/syntax/dominance errors; whereas a guard accessing nullable data or performing side effects can cause **runtime** errors.

## 14. Checklist for Designing Maintainable Guards

Before putting a `case` with `when` into a project, check yourself:

1. **Which variable is declared by the case pattern?** Underline that name; it will be available to the guard when the pattern matches.
2. **Does the guard declare an additional pattern variable via `instanceof`?** If so, verify that the variable is introduced when **the entire guard is true** before using it in the body.
3. **Do boolean operators guarantee the path?** With `&&`, the right-hand side receives the variable if the left-hand side matched; with `||` or negation, the same cannot be inferred.
4. **Are variables referenced by the guard final/effectively final?** Check both reassignments in the rule body and elsewhere in the declaration scope.
5. **Does the name conflict with an existing local variable?** Reusing a name in separate rules can be valid, but shadowing an already-in-scope variable is not.
6. **Does the guard dereference a nullable object?** Before calling `.length()` or `.isBlank()` on an accessor value, confirm null safety.
7. **Where does a false guard go?** There must be a branch handling the remaining cases of the type; a `switch expression` must be exhaustive.
8. **Are case labels ordered from specific to general?** Do not place a general unguarded case before a guarded case of the same type.
9. **Is the variable used in the right rule?** Do not reference a pattern variable from another branch or after the entire `switch`.
10. **Do tests cover null, guard true, guard false, other types, and record components?** Compare outputs against the contract.

Prefer short, pure (*side-effect-free*) and readable guards. For overly complex conditions, use a clearly named predicate method or separate business logic from the selection expression.

## 15. Exercises to Reinforce Pattern Variable Scope

**Exercise 1 — Valid region.** Consider:

```java
case String value when value.length() > 3 -> value.toUpperCase();
```

State where `value` is declared, why it is in scope in the guard, and why it is usable after `->`. If another case is added, can it reuse this case's exact variable?

**Exercise 2 — Declaring inside `when`.** Given `record Message(Object body) {}`, write a case using `when m.body() instanceof String content && !content.isBlank()` to return `content.strip()`. Add branches handling `Message` containing `Integer` and `null`; explain the scope of `content`.

**Exercise 3 — `&&` and `||`.** Try replacing `&&` in Exercise 2 with `||` and referencing `content` on the right-hand side and in the case body. Predict the compile error and explain which paths can be true when the pattern has not matched.

**Exercise 4 — Negation.** Write a separate case for a `Message` that does not contain a string. Use `!(m.body() instanceof String)` without trying to read an unbound pattern variable. Also write a case for a message containing a string.

**Exercise 5 — Effectively final.** Write `case String s when s.length() > 2 -> { s = s.strip(); yield s; }` and try compiling it. Fix it with `String cleaned = s.strip(); yield cleaned;`; explain why reassigning `s` as originally written is not allowed.

**Exercise 6 — Record pattern.** Create `record Range(int low, int high)`. Write `case Range(int low, int high) when low <= high -> ...` and a fallback `Range` case. Demonstrate where `low` and `high` are usable in the guard and in which rule body.

**Exercise 7 — Scope after `switch`.** Write a method accepting `Object` and using a `switch expression` to produce `String description`. After `switch`, use only `description`, without referencing case-specific pattern variables. Try typing a pattern variable name outside the `switch` to observe the compile error.

**Exercise 8 — Testing.** Run both complete programs. For `WhenScopeDemo21`, add `new Payload("")` and `new Payload(-1)` and predict which branch is selected. For `GuardScopeBlock21`, test `show(new Box("abc"), 3)` and `show(new Box("abc"), 4)`, distinguishing the results when the guard is true vs. false.

### Self-Assessment Questions

- At the moment `when` runs, what has Java already guaranteed about a pattern variable declared by the case?
- Under what condition can a variable introduced inside a guard be used in the case body?
- Why does `&&` support the scope of an `instanceof` pattern while `||` does not guarantee it?
- Does a false `when` cause a variable from the previous case to appear in the next case?
- Are two independent `case String s` labels two declarations or one shared variable?
- Can a variable that is not `final` by default still be forbidden from reassignment because a guard referenced it?
- How can record component variables be used in guards and rules?
- Do `->`-style `switch statement`s and `switch expression`s have similar pattern variable scope in their rule bodies?

If you can explain these questions and accurately identify which lines compile in the "intentionally invalid" snippets, you have mastered the core of **pattern variable scope in `when`**.

## 16. Official Documentation

- [JLS Java SE 21 — §6.3.3 Scope for Pattern Variables in case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3): variables from a pattern are in scope in the guard; variables introduced by a guard when true are brought into scope in the branch.
- [JLS Java SE 21 — §6.3.1.6 switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1.6): pattern variable scope in the switch rule body of an expression.
- [JLS Java SE 21 — §6.3.2.6 switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.6): pattern variable scope in a switch statement.
- [JLS Java SE 21 — §6.3.1.1 and §6.3.1.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1.1): flow scoping in `&&` and `||`.
- [JLS Java SE 21 — §14.11.1 Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): guard syntax, `boolean`/`Boolean` types, `final`/effectively final, and dominance checks.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): language design and official status of `when` in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): declaration and matching of record component variables.

In a learning environment, use `java -version` and `javac -version` to check your JDK, then compile examples with `javac --release 21`. When encountering scope errors, analyze **which paths guarantee that the pattern has matched**, rather than arbitrarily moving braces or redeclaring variables.
