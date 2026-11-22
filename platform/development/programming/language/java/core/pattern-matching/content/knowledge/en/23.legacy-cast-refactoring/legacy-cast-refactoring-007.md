# Preserving Behavior When Changing Syntax: Refactoring Legacy Casts to Java Pattern Matching

## 1. The Goal of Refactoring: Change How It Is Written, Not How the Program Behaves

Legacy Java code often checks a type with `instanceof` and then performs a *cast* to access members of the subtype:

```java
if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.strip());
}
```

Since **Java 16 (JEP 394)**, *pattern matching for instanceof* has been a standard feature. You can write:

```java
if (input instanceof String text) {
    System.out.println(text.strip());
}
```

Both snippets check whether `input` is an instance compatible with `String`; if so, the code inside the branch uses a variable of type `String`. Removing the redundant cast makes the code shorter and easier to read.

However, the requirement of a **behavior-preserving refactor** is not merely “it compiles” or “testing with a string object gives the same result.” We must preserve everything the legacy code guaranteed or made observable:

- Which branch is selected for the same input, including `null` and subtypes.
- Return values, mutated data, and objects passed to other methods.
- The order and number of calls to methods with side effects (fetching data, incrementing counters, logging, writing to a database, emitting events).
- Exception throwing, exception types, and when errors occur when this is part of the observable contract.
- Condition evaluation order, short-circuiting, and variable scope.
- Semantics determined by static types: overload resolution, generic types, and compile-time checkability.

**Rule:** only replace the check-and-cast syntax when you have sufficient basis to prove that **the same value is checked, the same branch is executed, and the body still does the same work**. If you want to fix a historical bug at the same time, separate it into an intentional behavior change and test it separately.

## 2. The Basic Transformation and Assumptions to Preserve

### Before: check the type, then cast the exact same variable

```java
static String legacy(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.strip();
    }
    return "not a string";
}
```

### After: a type pattern binds the checked variable directly

```java
static String modern(Object input) {
    if (input instanceof String text) {
        return text.strip();
    }
    return "not a string";
}
```

The two methods above have the same behavior for typical input values:

| Input | Before | After | Why |
| --- | --- | --- | --- |
| `" Java "` | `"Java"` | `"Java"` | `instanceof String` matches, uses the same string |
| `""` | `""` | `""` | Same `strip()` operation |
| `Integer.valueOf(7)` | `"not a string"` | `"not a string"` | Does not match `String` |
| `null` | `"not a string"` | `"not a string"` | `null instanceof String` is `false` |

With the syntax `input instanceof String text`, the name `text` can only be used where the compiler can determine that the pattern matched. The `instanceof` condition does not blindly cast and hope the cast succeeds; it performs the type check and creates the variable when appropriate.

Prerequisites for a simple replacement:

1. `input` is **the same expression/value** at the check step and the cast step.
2. No operation replaces the value of `input` between the two steps.
3. The removed cast has the same target type as the pattern, e.g., both are `String`.
4. The remaining statements, their order, and the `else` structure are unchanged.
5. There is no dependency on a same-named variable declaration in a scope that causes a conflict or changes overload resolution.

If any condition does not hold, analyze the behavior separately instead of applying a bulk find-and-replace.

## 3. Complete Program: Correct Refactoring and Counterexamples That Change Behavior

Save the program below to **`BehaviorPreservingPatternsDemo.java`**. All code uses **Java 17** syntax with no preview features required; the results are verified in Java 17 compilation mode.

```java
import java.util.Locale;

public class BehaviorPreservingPatternsDemo {
    // Traditional version: instanceof + cast.
    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return text.isBlank() ? "text:blank" : "text:" + text.strip();
        }
        if (input instanceof Number) {
            Number number = (Number) input;
            return "number:" + number.intValue();
        }
        return "other";
    }

    // Preserves branch order, operations, and result values.
    static String modern(Object input) {
        if (input instanceof String text) {
            return text.isBlank() ? "text:blank" : "text:" + text.strip();
        }
        if (input instanceof Number number) {
            return "number:" + number.intValue();
        }
        return "other";
    }

    // Legacy guard: non-matching branch returns early.
    static String legacyGuard(Object value) {
        if (!(value instanceof String)) return "not-string";
        String text = (String) value;
        if (text.isBlank()) return "empty";
        return "upper:" + text.toUpperCase(Locale.ROOT);
    }

    // Flow scoping: text remains usable after the return branch.
    static String modernGuard(Object value) {
        if (!(value instanceof String text)) return "not-string";
        if (text.isBlank()) return "empty";
        return "upper:" + text.toUpperCase(Locale.ROOT);
    }

    // Source with side effects: the first and second reads return different types.
    static int reads;
    static Object changingRead() {
        reads++;
        return reads == 1 ? "ok" : Integer.valueOf(9);
    }

    // Legacy actually calls changingRead() twice.
    static String duplicateRead() {
        if (changingRead() instanceof String) {
            String text = (String) changingRead();
            return text;
        }
        return "not-text";
    }

    // Syntax-changed version calls changingRead() only once!
    static String singleRead() {
        if (changingRead() instanceof String text) return text;
        return "not-text";
    }

    // An unchecked cast differs from an instanceof pattern.
    static void demonstrateCast(Object input) {
        try {
            String text = (String) input;
            System.out.println("direct-cast:" + (text == null ? "null" : text));
        } catch (ClassCastException ex) {
            System.out.println("direct-cast:ClassCastException");
        }

        if (input instanceof String text) {
            System.out.println("pattern:" + text);
        } else {
            System.out.println("pattern:non-string");
        }
    }

    public static void main(String[] args) {
        Object[] samples = { " Java ", "", 17, 3.9, null, new Object() };
        for (Object value : samples) {
            String before = legacy(value);
            String after = modern(value);
            System.out.println("same=" + before.equals(after) + " -> " + after);
        }

        System.out.println("guards=" +
                legacyGuard("ok").equals(modernGuard("ok")) +
                " -> " + modernGuard("ok"));
        System.out.println("guards=" +
                legacyGuard("").equals(modernGuard("")) +
                " -> " + modernGuard(""));
        System.out.println("guards=" +
                legacyGuard(null).equals(modernGuard(null)) +
                " -> " + modernGuard(null));

        reads = 0;
        try {
            System.out.println(duplicateRead());
        } catch (ClassCastException ex) {
            System.out.println("legacy-duplicate:ClassCastException reads=" + reads);
        }

        reads = 0;
        System.out.println("pattern-single:" + singleRead() + " reads=" + reads);

        demonstrateCast(5);
        demonstrateCast(null);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 BehaviorPreservingPatternsDemo.java
java BehaviorPreservingPatternsDemo
```

**Exact output:**

```text
same=true -> text:Java
same=true -> text:blank
same=true -> number:17
same=true -> number:3
same=true -> other
same=true -> other
guards=true -> upper:OK
guards=true -> empty
guards=true -> not-string
legacy-duplicate:ClassCastException reads=2
pattern-single:ok reads=1
direct-cast:ClassCastException
pattern:non-string
direct-cast:null
pattern:non-string
```

### Meaning of Each Group of Results

- The six `same=true` lines show that `legacy` and `modern` preserve the result values for strings, empty strings, integers, floating-point numbers, `null`, and other objects. For `Double.valueOf(3.9)`, both call `intValue()`, producing `3`.
- The three `guards=true` lines show that `if (!(value instanceof String text)) return ...;` preserves the logic of a negated check combined with early return.
- `legacy-duplicate:ClassCastException reads=2` versus `pattern-single:ok reads=1` is a **counterexample**: merely changing the syntax altered the number of method calls and the exception outcome. You must not claim the two versions are equivalent.
- The last two pairs of lines distinguish a **direct cast** from an **instanceof pattern**. For an integer, casting to `String` throws `ClassCastException`; the pattern does not match. For `null`, casting a reference to `String` produces `null`, whereas the pattern does not match.

This example intentionally separates **valid conditional replacements** from **cases that change semantics**, rather than treating every “before/after” pair as equivalent by default.

## 4. The Biggest Trap: Expression Evaluation Count and Side Effects

Be careful when the object is obtained from a method call rather than a stable local variable.

### Before: the expression may be called twice

```java
if (repository.findNext() instanceof String) {
    String text = (String) repository.findNext();
    consume(text);
}
```

Suppose `repository.findNext()` retrieves and removes an element from a queue. The first call is used for the check, and the second call retrieves **a different element**. It may have a different type; the first element may have been consumed without ever being processed. This is the behavior the legacy code *actually executes*, even if it is a bug.

### After: a type pattern evaluates the checked expression only once

```java
if (repository.findNext() instanceof String text) {
    consume(text);
}
```

The new code calls `findNext()` only once. This may be a **good bug fix**, but it is not a behavior-preserving refactor: the number of element fetches and the exception outcome have changed.

### How to Handle a Mutable Data Source Properly

First, clarify the **intended contract**, then separate retrieval from the check:

```java
Object candidate = repository.findNext();

if (candidate instanceof String) {
    String text = (String) candidate;
    consume(text);
}
```

Only after confirming that fetching **once** is the desired behavior and the version with `candidate` has been approved/tested should you apply the safe syntax change:

```java
Object candidate = repository.findNext();

if (candidate instanceof String text) {
    consume(text);
}
```

Both final blocks read `candidate` only once and do not mutate it between the check and the cast. **Do not silently treat switching from two reads to one read as behavior-preserving** without confirming the business requirement.

Apply the same rule to `iterator.next()`, `queue.poll()`, `stream`/cursor reads, clock reads, random generators, functions with counters, functions that query a database or call a service, and accessors that may mutate state.

## 5. Null, Casts, and Exceptions: Not Arbitrarily Interchangeable

### 5.1. Both `instanceof` and `instanceof pattern` do not match `null`

```java
Object input = null;

System.out.println(input instanceof String); // false
```

When `input == null`, both:

```java
if (input instanceof String) { /* ... */ }
```

and:

```java
if (input instanceof String text) { /* ... */ }
```

do not enter the branch. This is an important point of equivalence when replacing a **guard + cast structure**.

### 5.2. A direct cast to a reference type behaves differently

```java
Object input = null;
String text = (String) input; // Valid, text == null.
```

If rewritten as `if (input instanceof String text)`, the block will **not execute** for `null`. Meanwhile:

```java
Object input = Integer.valueOf(9);
String text = (String) input; // ClassCastException.
```

throws an exception instead of taking an `else` branch. Therefore, refactoring from a **direct cast** to a **type check + pattern** changes the contract for handling invalid types; it requires a separate decision and should not be treated as an equivalent syntax change.

### 5.3. Exceptions may be part of the observable contract

For an API that specifies invalid input types must throw `ClassCastException`, replacing it with `return null` or `"other"` causes callers to receive a different result and may break existing error-handling logic. Conversely, some code checks the type before casting specifically to **avoid** an exception; in those cases, a pattern is the natural choice.

When refactoring, explicitly list:
- For a non-matching value, does the method throw an error, return a fallback value, or do nothing?
- For `null`, is it a valid input or an error?
- Does the exception occur **before or after** logging, service calls, or state updates?
- Does any `catch` or `finally` block depend on the exception type or the order of side effects?

## 6. Preserving Branch Order When Types Have Inheritance Relationships

`instanceof` checks type compatibility, not just exact class name matching. Because `Integer` is a `Number`, changing branch order can cause a narrower branch to never be selected.

**Before: the `Integer` branch takes priority.**

```java
static String classify(Object value) {
    if (value instanceof Integer) {
        Integer n = (Integer) value;
        return "integer:" + n;
    }
    if (value instanceof Number) {
        Number n = (Number) value;
        return "number:" + n;
    }
    return "other";
}
```

**Correct after: only replace the cast, keep the order.**

```java
static String classify(Object value) {
    if (value instanceof Integer n) {
        return "integer:" + n;
    }
    if (value instanceof Number n) {
        return "number:" + n;
    }
    return "other";
}
```

**Wrong after: moving `Number` before `Integer`.**

```java
static String classify(Object value) {
    if (value instanceof Number n) {
        return "number:" + n; // Integer reaches here too.
    }
    if (value instanceof Integer n) {
        return "integer:" + n; // Never selected for Integer.
    }
    return "other";
}
```

For `Integer.valueOf(5)`, the correct version returns `integer:5`, while the wrong version returns `number:5`. Both compile, but the meaning has changed.

If you convert an `if` chain into a `switch` with type patterns (Java 21), you must also consider the **dominated case** rule: placing a broader branch before a narrower branch can cause a compiler error. Converting from `if` to `switch` is a broader design step than “removing redundant casts” and should be tested separately.

## 7. Flow Scoping: Pattern Variable Scope Follows Execution Paths

A pattern variable is not like a variable declared everywhere; Java only allows using it in places where the compiler can prove the type check succeeded.

### 7.1. Inside an `if` branch

```java
if (value instanceof String text) {
    System.out.println(text.length()); // Valid.
}
// Cannot arbitrarily use text here if the pattern might not have matched.
```

### 7.2. Using `&&` for deeper checks

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.toUpperCase());
}
```

The right-hand side of `&&` only executes if the pattern on the left-hand side succeeded; therefore `text` can be used.

**Do not mechanically change to `||`:**

```java
// WRONG: text is not guaranteed to be bound on the right-hand side.
if (value instanceof String text || text.isBlank()) {
    System.out.println("check");
}
```

This example **intentionally does not compile**. If the goal is to accept non-string data **or** a blank string, rewrite the condition with the proper logic:

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("not a non-blank string");
}
```

Here, the right-hand side of `||` is only evaluated when the left-hand side is `false`, meaning `value instanceof String text` is `true`; at that point `text` is in valid scope.

### 7.3. Negated guard clause and early `return`

Legacy:

```java
if (!(value instanceof String)) {
    return "not-string";
}
String text = (String) value;
return text.strip();
```

Refactored:

```java
if (!(value instanceof String text)) {
    return "not-string";
}
return text.strip();
```

The new code is valid: after passing through a branch with `return` in a negated condition, the compiler knows the pattern matched on the remaining execution path. Conversely, if the negated branch **does not definitely terminate**, `text` will not be guaranteed to be in scope outside the `if`.

### 7.4. Avoid name collisions and unintended scope changes

If a variable named `text` already exists in the local scope, you cannot arbitrarily declare a pattern variable with the same name in a conflicting region. In addition, when replacing a block-declared variable with a variable bound in the condition, the visible scope may differ from the legacy version. Rename meaningfully, recompile, and keep the branches that need the variable intact instead of widening scope with extra casts.

## 8. Differences Between Runtime Types and Static Types

### 8.1. Overload resolution depends on the static type at the call site

Suppose there are two overloads:

```java
static void render(Object value) {
    System.out.println("generic");
}

static void render(String value) {
    System.out.println("text");
}
```

In legacy code:

```java
if (input instanceof String) {
    String text = (String) input;
    render(text);  // Selects render(String).
}
```

After refactoring:

```java
if (input instanceof String text) {
    render(text);  // Still selects render(String).
}
```

However, if you accidentally write `render(input)` while `input` has static type `Object`, the compiler may select `render(Object)`, even though the actual runtime object is a string. This is a behavior change **caused by passing a different variable**, not by pattern matching; the compiler still allows it.

### 8.2. Generic type erasure does not disappear on its own

Legacy code may use a raw cast or an unchecked cast:

```java
// Illustrates syntax with an unchecked warning.
java.util.List<String> names =
        (java.util.List<String>) unknown;
```

You cannot change it to:

```java
// WRONG: cannot check List<String> with instanceof when the type is non-reifiable.
if (unknown instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

Type arguments such as `String` in `List<String>` are not fully checked at runtime due to **type erasure**. You can use `List<?>` if the goal is to verify that the object is a list:

```java
if (unknown instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
```

However, `List<?>` **does not prove** that every element is a `String`. If business logic requires that guarantee, you must inspect the contents or use an API with a sufficiently strong type contract; do not assume the two snippets are equivalent.

### 8.3. `getClass()` checks and `instanceof` are not the same test

`obj.getClass() == Base.class` accepts only the **exact class** `Base` (and calling `getClass()` on `null` throws an NPE). `obj instanceof Base` also accepts **subclasses** of `Base`, and returns `false` for `null`. Do not replace an exact class comparison with an `instanceof Base base` pattern and claim behavior is unchanged.

### 8.4. Minor note on Java 17

For example:

```java
String text = "hello";
if (text instanceof String match) {
    System.out.println(match);
}
```

With **`--release 17`**, the pattern `instanceof String match` on an expression whose static type is already `String` may be rejected because it is an **unconditional pattern**, which Java 17 did not yet allow in `instanceof`. In **Java 21**, this case is supported. This is a difference between language versions, not a runtime change when the pattern matches.

In code targeting Java 17, if you already have a `String text` variable, you usually do not need to re-check `String` with a pattern. Check for `null` according to your contract and use `text` directly when appropriate. All runnable examples in Section 3 are Java 17 compatible.

## 9. Moving from Legacy `if` to `switch`/Record Patterns: Raise the Verification Bar

Refactoring `instanceof + cast` to `instanceof pattern` is usually a fairly local change. However, converting an `if` chain into **pattern matching for switch** (Java 21) or record deconstruction can introduce additional changes:

- **Null handling:** `if (x instanceof T)` simply skips `null`, whereas `switch (x)` with a reference selector typically throws `NullPointerException` when there is no matching `case null`.
- **Exhaustiveness:** switch expressions and enhanced switch statements must cover all inputs of the selector type; adding `default` or a catch-all pattern may change how unexpected cases are handled.
- **Ordering and dominance:** a general pattern can shadow a specific pattern below it; the compiler may report a dominated case.
- **Guards:** `case T t when predicate(t)` is not equivalent to an unconditional `case T t`. Values of `T` for which the predicate is false may fall through or be missed.
- **Record deconstruction:** `case Record(var a, var b)` can bind components, while nested record patterns may fail to match if a nested record is `null`.

Conceptual example:

```java
// Java 21; assumes input has type Object.
String label = switch (input) {
    case null -> "missing";
    case String text -> "text:" + text;
    case Number number -> "number:" + number;
    default -> "other";
};
```

This is an illustrative example, not a complete program. To evaluate whether behavior is preserved, you must compare against the **ordering and null/unknown policy** of the original `if/else` chain; you cannot rely solely on the new switch compiling successfully.

If the goal is to remove redundant casts in a high-risk system, **complete the local refactor first**, and only then consider restructuring to `switch`/record patterns as an independent change.

## 10. Step-by-Step Safe Refactoring Workflow

### Step 1: Capture current behavior

For the exact method you are about to modify, record representative inputs, corresponding outputs or exceptions, and important side effects. If there is logging or auditing, note the order. For data-reading calls, pay attention to execution count and whether the underlying data can mutate.

### Step 2: Identify syntax-only replacement patterns

Look for the structure:

```java
if (candidate instanceof Target) {
    Target typed = (Target) candidate;
    process(typed);
}
```

Only when `candidate` is stable from the check to the cast and `Target` is the same type should you replace it with:

```java
if (candidate instanceof Target typed) {
    process(typed);
}
```

Both snippets are **illustrative**: `Target` and `process` represent real types/methods in the application. Do not invent an `else`, `default`, or fallback value.

### Step 3: Change one site, then compile

Preserve:
- The order of `if/else if`, `&&`, `||` conditions, and negations.
- Method calls with the same arguments and the variable types passed to overloads.
- Contents of `else` branches, `return`/`throw`, logging, and `catch`/`finally`.
- Evaluation counts of expressions with side effects and related shared mutable state.

The compiler helps catch scope errors, variable name collisions, and mismatched types; it does **not** automatically prove that all business behavior remains intact.

### Step 4: Test before/after with the same input set

A minimum matrix:

| Data group | What to compare |
| --- | --- |
| Matching type | Branch, value, side effects |
| Non-matching type | Fallback or exception |
| `null` | Whether the branch runs, whether the exception changes |
| Subtype | Whether the narrow branch is selected in the right order |
| Empty string / boundary data | Whether guard conditions and handling are preserved |
| Source that mutates on each read | Evaluation count, value used |
| Generic/raw type | Compile/runtime compatibility, warnings |
| Overload | Whether the same signature is called |
| Service failure | Whether exception, log, and cleanup occur in the same order |

Do not just check that tests pass; verify that **assertions actually cover** both outputs and side effects, especially when refactoring from two method calls to one.

### Step 5: Separate intentional changes

If while changing syntax you discover that the original code reads a queue twice, performs an unexpected failing cast, or has the wrong branch order, you can fix it. However, label it as an intentional **behavior change**: update the contract/tests, document the impact, and do not mix it into a “syntax-only” claim.

## 11. Anti-Patterns to Avoid

1. **Replacing every `(Type) methodCall()` with a pattern on `methodCall()` without counting invocations.** This can change side effects and the data read.
2. **Dropping guard checks after obtaining a pattern variable.** A pattern proves the type; it does not prove a string is non-empty, a list is non-empty, or data satisfies business rules.
3. **Swapping branch order between a supertype and a subtype.** Cases with inheritance relationships will select a different branch.
4. **Turning a direct cast into an `if` with an arbitrary fallback.** This replaces `ClassCastException`/`null` with different behavior.
5. **Using `input` instead of the narrowed pattern variable.** This can easily change which overload is selected or lose subtype APIs.
6. **Using a pattern variable out of scope or colliding with an existing variable name.** The compiler will report an error; redesign the flow and naming.
7. **Treating `List<?>` as `List<String>`.** Generic type arguments are not checked that way at runtime.
8. **Bundling business logic fixes into a syntax refactor.** This makes before/after equivalence hard to verify; keep them in separate commits or separately tested changes.
9. **Relying on a newer compiler environment to validate Java 17 code.** Use `javac --release 17` if Java 17 must be supported; syntax accepted in Java 21 may be rejected in Java 17.
10. **Preserving outputs while forgetting exceptions and side effects.** Two versions may return the same string yet call an API a different number of times, log audits in a different order, or fail at a different point.

## 12. Practice Exercises and Answers

**Exercise 1 — Valid replacement.** Given `Object input`:

```java
if (input instanceof Number) {
    Number n = (Number) input;
    return n.intValue();
}
return -1;
```

Rewrite it without the cast. **Answer:**

```java
if (input instanceof Number n) {
    return n.intValue();
}
return -1;
```

The two snippets are equivalent when using the same `input` variable and not modifying other expressions/branches.

**Exercise 2 — Source with side effects.** `readNext()` returns successive elements from a queue. Why is `if (readNext() instanceof String) { String s = (String) readNext(); ... }` not equivalent to `if (readNext() instanceof String s) { ... }`? **Answer:** the legacy code reads up to two elements; the new code reads one element. This can change the value used, the queue state, and exceptions.

**Exercise 3 — Null.** Compare `String s = (String) null;` and `if (value instanceof String s)` when `value == null`. **Answer:** the cast is valid and `s == null`; the pattern does not match. Do not replace directly if the contract requires preserving this difference.

**Exercise 4 — Priority order.** Given `if (value instanceof Integer) ... else if (value instanceof Number) ...`. When converting to patterns, should `Number` be moved first? **Answer:** no, because `Integer` is also a `Number`; the selected branch would change.

**Exercise 5 — Flow scoping.** Is `if (obj instanceof String text || text.isBlank())` valid? **Answer:** no; on the right-hand side of `||`, `text` is not guaranteed to be assigned. If the goal is to accept a non-string value **or** a blank string, use `if (!(obj instanceof String text) || text.isBlank())`.

**Exercise 6 — Generics.** Can you replace the cast `(List<String>) value` with `value instanceof List<String> strings`? **Answer:** no, because `List<String>` is a generic type that cannot be fully checked at runtime. `List<?>` only checks the list structure and does not guarantee the elements are strings.

**Exercise 7 — Preserving error handling.** If legacy code intentionally throws `ClassCastException` for an invalid type, which approach is safer: arbitrarily returning `"unsupported"` or confirming the error contract before refactoring? **Answer:** confirm and preserve the error contract; switching to a fallback is new behavior that requires a separate decision and testing.

## 13. Key Takeaways

**Safe legacy cast refactoring** means converting `if (x instanceof T) { T t = (T) x; ... }` into `if (x instanceof T t) { ... }` **when the same value is checked and used, no side effects or mutations intervene, and the handling branches remain intact**. Pattern matching lets the compiler bind the type check to a properly typed variable, but it **does not automatically preserve** method invocation counts, branch order, `null` handling policies, exceptions, overload resolution, or generic contracts.

Verify with **small diffs + compiling with the right `--release` + regression tests** for both outputs and side effects, and separate out any intentional behavior changes.

**Official references:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Java Language Specification 17 — Type Comparison Operator instanceof (`15.20.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2), [Java Language Specification 17 — Patterns (`14.30)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30), [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441).