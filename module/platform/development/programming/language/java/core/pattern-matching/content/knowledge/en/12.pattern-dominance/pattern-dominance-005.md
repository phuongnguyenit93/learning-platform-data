# How Does a Guard Affect Dominance in Java Pattern Matching?

In Java 21+, a `switch` `case` label can contain a **pattern** and a **`when` guard** condition:

```java
case String text when text.length() >= 5 -> "long string";
```

A guard affects **dominance** (the dominance relationship between `case` labels) in a very specific way: **a pattern with a non-constant-true guard may not cover all values matched by the underlying pattern**, because the guard can evaluate to `false`. Therefore, Java generally allows cases of the same type, or a narrower-typed case after a **guarded** broader-typed pattern, to handle cases where the guard does not hold.

Conversely, an **unguarded** pattern or one protected by a guard that is a **constant expression `true`** is still considered by the compiler to fully cover the values of that pattern when checking dominance. A completely covered subsequent case will cause a **compile-time error**, regardless of how simple or complex the runtime code of the preceding case appears.

> **Core rule:** When checking dominance, Java distinguishes between *whether a pattern can match* and *whether the case is guaranteed to apply after the pattern matches*. A regular guard can be false; a constant `true` guard is the exception treated as unguarded. The compiler does not prove arbitrary boolean conditions to eliminate cases.

This article focuses on **dominance of pattern case labels in `switch`** and its direct relationship with `when` guards, including compile-time mechanics, runtime behavior, case ordering, exhaustiveness, and common mistakes. The `when` syntax in `switch` was standardized in **Java 21**; the runnable examples below require JDK 21+.

## 1. What Is Dominance?

A preceding `case` label **dominates** a subsequent `case` label if, according to the static rules of the language, the subsequent label is covered by the preceding label to the extent that it has no chance of ever being selected. Java uses **dominance checking** at compile time to prevent pattern cases from being shadowed due to incorrect ordering.

**Invalid** example (uncomment lines to test in a Java 21+ `switch`):

```java
// static String bad(Object value) {
//     return switch (value) {
//         case CharSequence seq -> "any sequence";
//         case String text -> "a string"; // ERROR: dominated by the preceding CharSequence case
//         default -> "other";
//     };
// }
```

`String` implements `CharSequence`; every non-`null` `String` object matches the `CharSequence seq` pattern above. The subsequent `case String text` branch can never be selected in that order.

The fix is to **place the specific case before the broad case**:

```java
static String good(Object value) {
    return switch (value) {
        case String text -> "a string";
        case CharSequence seq -> "other sequence";
        default -> "other";
    };
}
```

This is an **illustrative method**, assumed to be placed inside a Java 21+ class. If `value` is a `StringBuilder`, it enters the `CharSequence` case. If `value` is a `String`, it enters the `String` case first.

**Not every case following another case that can match the same values is dominated.** The focus is on whether the preceding case **is guaranteed to cover** the cases of the following one according to compile-time rules. A `when` guard changes this evaluation.

## 2. `when` Turns a Pattern Label into a Conditional Label

Compare the two forms:

```java
case CharSequence seq -> "any sequence";
```

and

```java
case CharSequence seq when seq.length() >= 5 -> "long sequence";
```

In the first form, if a non-`null` `CharSequence` object matches, the case can be selected immediately (assuming no preceding label applied).

In the second form, the type pattern `CharSequence seq` must match **and** the expression `seq.length() >= 5` must evaluate to `true`. If the value is the string `"Go"`, the pattern can match, but the guard is `false`; this case is **not selected**. Java has a valid reason to keep other cases handling `String` or `CharSequence` afterward.

Therefore, the following pair is **valid**, even though the broad pattern comes first:

```java
static String classify(Object value) {
    return switch (value) {
        case CharSequence seq when seq.length() >= 5 -> "long sequence";
        case String text -> "string: " + text;
        case CharSequence seq -> "other sequence";
        default -> "other";
    };
}
```

Scenarios:

- `"Spring"`: matches `CharSequence` and the guard is true, so `long sequence` is selected immediately.
- `"Go"`: matches `CharSequence` but the guard is false; the next `case String text` branch is selected.
- `new StringBuilder("ok")`: fails the guard, is not a `String`; handled by the unguarded `CharSequence` branch below.
- An `Integer`: matches neither `CharSequence` nor `String`; `default` is selected.

**Note:** a guard allows a narrower subsequent case to exist, but does not guarantee that the narrower case will always be selected. For `"Spring"`, the guarded broad case still **wins selection first** because the guard succeeds. If you want `String` to always take priority over other `CharSequence` types, you must reorder or adjust the cases to match your intent.

## 3. Quick Rule Table: Guarded or Not, Dominance or Not?

| Labels in order | Result | Why |
| --- | --- | --- |
| `case CharSequence cs -> ...; case String s -> ...;` | **Compile-time error** | Unguarded `CharSequence` pattern covers `String` |
| `case CharSequence cs when cs.length() > 3 -> ...; case String s -> ...;` | **Valid** | Guard can be `false`, so `String` case still has a chance to run |
| `case String s -> ...; case String t when t.isBlank() -> ...;` | **Compile-time error** | Preceding unguarded `String` already covers all `String` values |
| `case String s when s.isBlank() -> ...; case String t -> ...;` | **Valid** | When the guard is false, the subsequent `String` case handles the remainder |
| `case String s when true -> ...; case String t -> ...;` | **Compile-time error** | Constant `true` guard is treated as equivalent to unguarded for dominance |
| `case String s when false -> ...;` | **Compile-time error** | Guard is a constant expression with value `false`, which is forbidden by Java |
| `case String s when s.isBlank() -> ...; case String t when t.isBlank() -> ...;` | **Valid for dominance** | The compiler does not prove that arbitrary predicates overlap; in practice, the second branch may be unreachable with a pure predicate |

The pairs above are **illustrative syntax snippets**, not complete Java programs. To run them, place them inside a `switch` with an appropriate selector type and remaining cases; for a `switch` expression, exhaustiveness must be ensured.

A key takeaway: dominance is a **static compiler check**, not merely measuring whether a test dataset ever flows into a given case.

## 4. Distinguishing Compile-Time Dominance from Runtime Case Selection

A case with a regular guard involves the following steps:

1. **Evaluate the selector** of the `switch` to obtain the value to branch on.
2. **Test the pattern** of the case label according to branch selection rules.
3. If the pattern does not match, the guard is **not evaluated**.
4. If the pattern matches, **bind pattern variables** such as `seq` or `text`.
5. **Evaluate the `when` guard**: if `true`, the case is selected; if `false`, continue checking subsequent case labels according to `switch` semantics.
6. If the guard throws an exception, the exception **propagates**; it is not treated as `false` and does not fall through to `default`.

```text
                     COMPILE TIME
            Check dominance between case labels
       +------------------------------------+
       | unguarded or constant true guard:  |
       | can dominate subsequent patterns   |
       | regular guard: can be false        |
       +------------------------------------+
                          |
                          v
                       RUNTIME
                  Evaluate selector
                          |
                          v
                    Try pattern
                      /      \
                 no match    match
                    |          |
                    |          v
                    |     bind variables
                    |          |
                    |          v
                    |     evaluate when
                    |       /      \
                    |   true       false
                    |     |          |
                    v     v          v
             other case select   other case
                         case
```

At compile time, Java does not need to know whether runtime data is `"Java"` or `"Spring"` to detect an unguarded `case CharSequence` placed before `case String`. At runtime, Java evaluates the result of `seq.length() > 3` for a specific value.

These two layers are related, but they are **not the same algorithm**.

## 5. Complete Example: Guarded and Unguarded Patterns of the Same Type

Save the file **`DominanceRulesDemo.java`**, compile and run with Java 21+:

```java
public class DominanceRulesDemo {
    static String classify(Object input) {
        return switch (input) {
            case String s when s.isBlank() -> "blank";
            case String s when s.length() >= 5 -> "long:" + s;
            case String s -> "short:" + s;

            case CharSequence cs when cs.length() >= 5 ->
                    "long-other-sequence";
            case CharSequence cs -> "other-sequence";

            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("  "));
        System.out.println(classify("Java"));
        System.out.println(classify("Spring"));
        System.out.println(classify(new StringBuilder("hello")));
        System.out.println(classify(new StringBuilder("go")));
        System.out.println(classify(5));
        System.out.println(classify(null));
    }
}
```

```bash
javac DominanceRulesDemo.java
java DominanceRulesDemo
```

Exact output:

```text
blank
short:Java
long:Spring
long-other-sequence
other-sequence
other
null
```

**Explanation of each group:**

- The two guarded `String` cases stand **before** the unguarded `String` case. They describe blank strings and sufficiently long strings; if neither guard holds, the final `String` case in the group receives the remaining strings.
- The unguarded `case String s -> ...` branch covers every `String` and stands **before** `case CharSequence cs ...`: this is valid because `CharSequence` also includes other types, such as `StringBuilder`. The subsequent `CharSequence` case is not dominated by `String`.
- The guarded `CharSequence` case must precede the unguarded `CharSequence` case. If reversed, the guarded case of the same type afterward would be dominated.
- `Integer 5` is not a `CharSequence`, so `default` is selected.
- `null` is handled separately by `case null`. `default` **does not automatically catch a `null` selector** in Java 21.

**Takeaway:** ordering from **specialized guarded → remaining unguarded** is usually a clear way to organize cases that share the same type pattern. With this order, the compiler accepts it and runtime selects the branch based on actual conditions.

## 6. Complete Example: Guarded Broad Pattern Before Narrow Pattern

Save the file **`StrictGuardOrdering.java`**:

```java
public class StrictGuardOrdering {
    static String classify(Object input) {
        return switch (input) {
            case CharSequence cs when cs.length() >= 5 -> "long-cs";
            case String s -> "string:" + s;
            case CharSequence cs -> "remaining-cs";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Spring"));
        System.out.println(classify("Go"));
        System.out.println(classify(new StringBuilder("small")));
    }
}
```

```bash
javac StrictGuardOrdering.java
java StrictGuardOrdering
```

Output:

```text
long-cs
string:Go
long-cs
```

Here:

- `"Spring"` is a `String` and also a `CharSequence`; the guard of the first broad case is true, so **the `String` branch below does not run**.
- `"Go"` is also a `CharSequence`, but the first guard is false, so Java tries the `String` branch and returns `string:Go`.
- `StringBuilder("small")` is a `CharSequence` of length 5, passes the first guard immediately, and returns `long-cs`.

This class demonstrates that **a guarded broad pattern can precede a narrow pattern without causing a dominance error**, yet it still **prioritizes the broad branch** for values that satisfy the guard. If the business requirement is that every `String` must enter the `String` case, you should write the `String` case before checking the guarded `CharSequence`, or adjust the conditions.

## 7. Constant `true` Guard: An Important Exception

The statement:

```java
case String s when true -> "string";
```

looks like a guarded pattern because it has the `when` keyword. However, **`true` is a constant expression with value `true`**, so in **dominance checking**, Java treats the pattern as **unguarded**.

The following snippet **does not compile**:

```java
// static String bad(Object input) {
//     return switch (input) {
//         case String s when true -> "any-string";
//         case String s when s.length() > 3 -> "long-string"; // Dominated
//         default -> "other";
//     };
// }
```

Logically, the first case already accepts every non-`null` string; the second case never gets a chance. Java recognizes this via the rule for constant-true guards.

Not just the literal `true`: expressions that the compiler considers a **constant expression with value `true`** must also be understood under the same rule. Do not add `when true` intending to "turn an unguarded pattern into a guarded pattern" to bypass dominance errors.

For a type pattern covering the entire selector type domain, a constant `true` guard can also make the `switch` have an **unconditional pattern**. The following example **does not compile**:

```java
// static String invalid(Object input) {
//     return switch (input) {
//         case Object obj when true -> "object";
//         default -> "other"; // ERROR: unconditional pattern + default
//     };
// }
```

Remove the redundant `default` branch or revise the classification structure; `when true` is not a way to disable dominance checking.

## 8. Constant `false` Guard: Not a Way to Create a "Never-Executed" Case

The statement:

```java
// INVALID:
// case String s when false -> "unreachable";
```

is rejected by the compiler because the guard is a **constant expression with value `false`**. It should not be used to keep temporary code around or to experiment with altering dominance. If a case no longer applies, delete it or rewrite the business rule.

A non-constant guard that always returns `false` according to the author's intuition **does not mean the compiler will prove it**. For example, `when isNeverEligible(s)` might be a method, and the compiler generally does not analyze the logic of that entire method to eliminate the case. Thus, dominance does not replace business logic review or actual testing.

## 9. The Compiler Does Not Prove Every Logical Relationship Between Guards

Consider:

```java
static String classify(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "first";
        case String s when s.isBlank() -> "second";
        case String s -> "otherwise";
        default -> "not a string";
    };
}
```

In Java 21+, this snippet **compiles**: the compiler does not treat the two `s.isBlank()` calls as a static proof that the second case is dominated. With an immutable `String` and a pure `isBlank()` predicate, if the first branch did not apply because it returned `false`, the second branch will also return `false`; if it returned `true`, the first branch already took it. The `"second"` branch therefore has no practical effect in this example.

This is **not a compiler bug**: dominance rules only check relationships specified by the language and do not require deducing equivalence between arbitrary boolean expressions. With stateful guards or side effects, two evaluations of an expression could even yield different results.

Similarly:

```java
case Integer n when n >= 90 -> "A";
case Integer n when n >= 60 -> "PASS";
case Integer n -> "FAIL";
```

The first two guards have **overlapping** value ranges. Java allows this because both can be true or only one can be true; if both are true, the first matching case is selected. Here `95` gets `A`, and `75` gets `PASS`. If the order of the two guards is swapped, `95` would be classified as `PASS`. The compiler does not automatically sort by the "specificity" of boolean conditions.

**Practical rule:** treat guards as conditions with priority ordering; test boundary points and overlapping regions rather than relying on dominance to catch all redundant or misordered logic.

## 10. Complete Example: Overlapping Guards Without Dominance Errors

Save **`ScoreGuardDemo.java`** (Java 21+):

```java
public class ScoreGuardDemo {
    static String band(Object value) {
        return switch (value) {
            case null -> "missing";
            case Integer n when n >= 90 -> "excellent";
            case Integer n when n >= 60 -> "passed";
            case Integer n -> "failed";
            default -> "not-an-integer";
        };
    }

    public static void main(String[] args) {
        System.out.println(band(95));
        System.out.println(band(75));
        System.out.println(band(50));
        System.out.println(band(null));
        System.out.println(band("95"));
    }
}
```

```bash
javac ScoreGuardDemo.java
java ScoreGuardDemo
```

Output:

```text
excellent
passed
failed
missing
not-an-integer
```

- `95` satisfies both `n >= 90` and `n >= 60`, but **the first guarded case** is selected.
- `75` fails `>= 90` but satisfies `>= 60`, so the second case is selected.
- `50` satisfies neither guard, yet is still an `Integer`, so it is handled by the unguarded `case Integer n` branch.
- `null` has its own label; the string `"95"` does not match `Integer`, so `default` is used.

If `case Integer n -> "failed"` is placed **before** the guarded `Integer` cases, the compiler will report dominance. If the order of the two guards `>= 60` and `>= 90` is swapped, the compiler **will not necessarily report an error**, yet the output for `95` will change. This clearly distinguishes between a **static dominance error** and a **business classification bug**.

## 11. Guards and Exhaustiveness Are Related but Distinct

A `switch` expression must be **exhaustive**: the compiler must prove that every value in the normal domain is handled according to Java's rules. A guard can evaluate to `false`, so **a regular guard is not enough to be considered guaranteed coverage**.

The following example **does not compile** (Java 21+):

```java
// static String bad(Object value) {
//     return switch (value) {
//         case null -> "null";
//         case Object obj when obj != null -> "object";
//     };
// }
```

A developer might argue: "If it is not null, then `obj != null` is always true." However, the guard `obj != null` **is not a constant expression `true`**, and Java does not prove this to turn the guarded branch into an unconditional pattern for exhaustiveness purposes. The compiler reports missing coverage.

There are two ways to fix this:

**Approach A — Add `default` for the case the compiler cannot prove:**

```java
static String good(Object value) {
    return switch (value) {
        case null -> "null";
        case Object obj when obj != null -> "object";
        default -> "fallback";
    };
}
```

For any normal non-`null` `Object` value, the guard is true and returns `"object"`. `default` here satisfies the static coverage requirement.

**Approach B — Remove the redundant guard and make the type pattern truly unconditional:**

```java
static String simpler(Object value) {
    return switch (value) {
        case null -> "null";
        case Object obj -> "object";
    };
}
```

`case Object obj` covers non-`null` objects; `case null` covers `null`. No `default` is needed.

**Special nuance:** if you use `case Object obj when true`, the compiler treats the constant-true guard as unguarded and can prove coverage just like Approach B. However, Approach B is more concise and expresses intent more clearly.

Do not equate "my code is always true at runtime" with "the compiler treats the case as unconditional when checking dominance/exhaustiveness."

## 12. Impact of Dominance on `default` and `case null`

Dominance is primarily about **one case label shadowing another** under compiler rules. Two special labels must be considered separately:

- **`case null`** receives the `null` selector. Type patterns such as `String s` or `Object obj` **do not match `null`**, regardless of what guard protects them.
- **`default`** receives remaining values when no label applies according to `switch` rules. In Java 21, `default` **does not automatically handle a `null` selector**; if `case null` is missing, a `null` selector results in a `NullPointerException`.

Valid example:

```java
static String inspect(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when !s.isBlank() -> "nonblank string";
        case String s -> "other string";
        default -> "not a string";
    };
}
```

A `String` case with a regular guard placed before an unguarded `String` case is a common arrangement. However, if an **unconditional pattern for the entire selector** is used, a separate `default` must not be added (as illustrated with `case Object obj`).

Not every statement with `default` is "safer": `default` can hide a new type case that should be handled explicitly, or `default` itself may be forbidden due to an unconditional pattern. Weigh this based on exhaustiveness and the extensibility of your domain.

## 13. Relation to Record Patterns and Generic Patterns

In Java 21, a record pattern can also be accompanied by a guard. Illustrative example:

```java
record Order(String category, int total) {}

static String route(Object value) {
    return switch (value) {
        case Order(String category, int total) when total >= 100 ->
                "priority:" + category;
        case Order(var category, var total) ->
                "standard:" + category;
        case null -> "missing";
        default -> "unsupported";
    };
}
```

This is a **Java 21+ illustrative method snippet** with `Order` declared in the same compilation environment; it is not a standalone program.

The guard `total >= 100` makes the first branch **apply only when the record pattern has matched and the total meets the condition**. The subsequent record pattern branch handles the remaining records, according to the actual scope of the pattern.

Note also: `String category` in the component pattern requires the component to be non-`null` and of the right type; `var category` can bind a `null` component. Therefore, the two record patterns above are **not identical even without the guard**. To reason accurately about dominance, you must consider **the relationship between the entire patterns** (including component patterns), rather than looking only at the record name and the `when` condition.

In real-world applications, the safe approach is to put cases with detailed conditions before broader cases, compile to catch dominance errors, and test cases where a record component does not match or has a `null` value.

## 14. When Will the Compiler Report an Error, and When Must You Write Tests?

| Scenario | Can the compiler detect it? | Action |
| --- | --- | --- |
| Unguarded `CharSequence` before `String` | **Yes, dominance error** | Reorder or add business conditions to the broad branch if truly needed |
| Unguarded `String` before `String when ...` | **Yes, dominance error** | Place the guarded case first |
| `String when true` before `String` | **Yes, treated as unguarded** | Remove `when true` or change the design |
| `String when false` | **Yes, constant-false guard error** | Remove the inapplicable branch |
| Two guards with identical `isBlank()` predicate | **Not necessarily** | Code review and test to remove meaningless branch |
| Two overlapping guards `>= 90` and `>= 60` | **Not a dominance error by default** | Test thresholds and verify priority order |
| Guard throws an exception | **Not converted into a false guard** | Handle data/exceptions at the appropriate place |
| Regular guard on `Object` used instead of an unconditional pattern | **May cause non-exhaustive error** | Add remaining cases or remove the redundant guard |
| `case Object obj when true` alongside `default` | **Yes, unconditional pattern conflicts with default** | Remove `default` or change the structure |

**Do not try to "trick" the compiler with a non-constant guard** just so a shadowed branch can compile. If a condition can never be true in application logic, the compiler might not notice, yet it remains dead code or a hard-to-maintain bug.

## 15. Checklist for Reviewing Guards and Dominance

When reading a Java 21+ `switch` with multiple pattern cases:

1. **Note the selector type and the set of values that can arrive.** `Object`, `CharSequence`, sealed hierarchy, enum, record, or mixed data?
2. **Identify subtype/coverage relationships among patterns.** Which branch can match every value that another branch matches?
3. **Flag unguarded cases.** Place narrow patterns before broad ones or restructure rules when dominance is at risk.
4. **Flag guards that are constant `true`.** Do not treat them as regular guards when reasoning about dominance.
5. **Detect constant `false`.** Java rejects it at compile time; remove unselectable branches.
6. **Consider the possibility of a regular guard returning `false`.** That is why subsequent branches still have a chance to be selected.
7. **Check overlapping guards.** For a value satisfying multiple guards, which branch comes first and gets priority? Does it match business rules?
8. **Check exhaustiveness.** Do not use a non-constant guard that looks "always true" as a substitute for an unconditional pattern; add a fallback when needed.
9. **Check null handling.** Is there a `case null` if a `null` selector is valid? `default` does not accept `null` automatically.
10. **Check runtime behavior.** A guard can throw an exception, be expensive, or have side effects; test branch ordering and boundary points.
11. **Verify the Java version.** `when` in `switch` requires Java 21+; in Java 17, use `instanceof` with `if`/`&&` or an appropriate constant `switch`.
12. **Compile small examples.** For dominance, the compiler is an important source of truth; do not rely solely on reasoning from sample runtime values.

### Summary in Three Pairs

```java
// 1. WRONG: unguarded broad branch covers narrow branch.
// case CharSequence cs -> "any";
// case String s -> "string";

// 2. RIGHT: guard can be false, so the narrow branch still has a chance.
// case CharSequence cs when cs.length() > 3 -> "long";
// case String s -> "string";

// 3. WRONG: constant true is treated as unguarded for dominance.
// case String s when true -> "any";
// case String s when s.isBlank() -> "blank";
```

**Conclusion:** A `when` guard **narrows the effective applicability of a case**, so a guarded pattern with a non-constant-true condition generally **does not dominate** subsequent narrower or same-type patterns the way an unguarded pattern does. Specifically, **`when true`** is treated as unguarded for dominance, while **`when false`** is a compile-time error. Once static checks pass, **branch order and runtime guard results** decide which case is selected; the compiler does not prove every logical relationship between predicates for you.

## Official References

- [Oracle Java SE 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): guarded patterns, dominance, case ordering, and exhaustive switch.
- [Java Language Specification 21 — `14.11 Switch Statements](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-14.html#jls-14.11): label selection semantics, guards, and dominance relationships.
- [Java Language Specification 21 — `15.28 Switch Expressions](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-15.html#jls-15.28): exhaustiveness and results of `switch` expressions.
