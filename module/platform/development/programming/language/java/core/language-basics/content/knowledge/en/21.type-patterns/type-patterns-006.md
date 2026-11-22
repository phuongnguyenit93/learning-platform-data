# Guard Conditions `when` and Pattern Label Order — Java 17+

## 1. Nature of This Lesson and Version Notes

When using **pattern matching in `switch`**, you can select a branch based on **data type** and add a **guard condition** (*guard*) to accept a pattern only when it satisfies an additional constraint. Common syntax:

~~~java
// Java 21 or later: stable switch pattern matching.
case String text when text.length() >= 5 -> ...
~~~

Meaning: first the selector must match the pattern `String text`; **only then** does Java evaluate `text.length() >= 5`. If the guard is false, Java continues searching subsequent case labels.

**Distinguishing versions is crucial:**

| JDK | Status and Syntax |
|---|---|
| Java 17 | Pattern matching for `instanceof` is **stable**; pattern matching for `switch` is **preview** (JEP 406), and the preview guard uses `case String s && condition`, **with no `when` syntax** |
| Java 21+ | Pattern matching for `switch` is **stable** (JEP 441); write `case String s when condition -> ...`, no preview needed |

Therefore, **`case ... when ...` cannot be compiled with `javac --release 17`**. This lesson includes two complete programs:

1. **JDK 17+**: uses `instanceof` patterns combined with `if/else` and `&&`, expressing the same logic and verifiable on Java 17.
2. **JDK 21+**: directly uses `switch` with `when`, matching the exact syntax asked about.

Do not use Java 21 syntax in snippets marked as running on JDK 17.

## 2. `when` Checks a Condition After the Pattern Matches

Java 21 example:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s when s.length() >= 5 -> "LONG_TEXT";
        case String s -> "SHORT_TEXT";
        default -> "OTHER";
    };
}
~~~

Flow for `value = "example"`:

1. Does not match `case null`.
2. Matches type `String` on the label with `s.isBlank()`, but the guard is false.
3. Moves to the next label: matches `String` and `s.length() >= 5` is true.
4. Selects `"LONG_TEXT"`; **does not evaluate** the labels below.

If `value = 42`, Java does not call `s.isBlank()` or `s.length()`, because the pattern `String s` does not match. The pattern variable `s` is in scope for the **guard** and the **body of the selected branch**, and does not exist unconditionally across all cases.

~~~mermaid
flowchart TD
    A["Evaluate selector once"] --> B{"First label pattern matches?"}
    B -- "No" --> F["Try next label"]
    B -- "Yes" --> C{"Has when and guard is true?"}
    C -- "No" --> F
    C -- "Yes / no guard" --> D["Select branch and execute branch body"]
    F --> B
    D --> E["Exit switch rule/expression"]
~~~

The diagram illustrates the general principle; when a guard is false, Java **does not execute the branch body** even though the pattern type matched.

## 3. `when` Must Accompany an Appropriate Pattern Label

Valid examples in Java 21:

~~~java
case String text when !text.isBlank() -> "TEXT"
case Integer number when number > 0 -> "POSITIVE_INTEGER"
~~~

Expressions after `when` must be **`boolean`** conditions (or a `Boolean` value that can be unboxed), and are checked by language rules like an ordinary conditional expression.

**Do not attach `when` to a constant label in the same way:**

~~~java
// Not valid Java 21 guarded pattern syntax:
// case 10 when someBoolean -> "TEN";
~~~

If you need an extra check on the value 10, you can use a type pattern with a guard (when contextually appropriate), or better yet use `if` if the logic is just comparing a number and an extra condition.

A guard can combine multiple conditions:

~~~java
case String text when !text.isBlank()
        && text.length() <= 20 -> "VALID_TEXT"
~~~

Inside the guard, `text` is already known to be a **non-null** String, though methods called in the guard can still have side effects or throw exceptions if they do other work. Prefer short, pure, and easily testable guards.

## 4. Pattern Label Order Affects the Result

Two guards can **both be true** for a single value. The first matching branch in label order is selected.

~~~java
return switch (value) {
    case String s when s.startsWith("A") -> "STARTS_A";
    case String s when s.length() >= 5 -> "LONG";
    case String s -> "OTHER_STRING";
    default -> "NOT_STRING";
};
~~~

For `"AppleTree"`, both of the first two guards are true, yet the result is `"STARTS_A"` because that label comes first. For `"Mexico"`, the first guard is false and the second is true, yielding `"LONG"`.

**Advice:** place **higher-priority or more specific** conditions first. Write a rule table when multiple guards overlap:

| Input | `startsWith("A")` | `length >= 5` | Selected Label |
|---|---|---|---|
| `"AppleTree"` | true | true | `STARTS_A` (first) |
| `"Alex"` | true | false | `STARTS_A` |
| `"Mexico"` | false | true | `LONG` |
| `"Go"` | false | false | `OTHER_STRING` |
| `42` | String guard not evaluated | Not evaluated | `NOT_STRING` |

Changing the order of two guarded labels can **change the result**, even when the program still compiles cleanly.

## 5. Dominance: The Compiler Detects Shadowed Labels

An unguarded broad-type label can cover all values of a narrower label placed after it. For example, `CharSequence` includes `String`, so the following order does not compile on Java 21:

~~~java
// case CharSequence cs -> "SEQUENCE";
// case String s -> "STRING"; // Dominated.
~~~

Swap the order to `case String s` and then `case CharSequence cs` to keep both paths. For the same pattern type, placing `case String s -> ...` before `case String s when s.length() >= 5 -> ...` also shadows the guarded label; put guarded labels before the general label.

Between **two arbitrary guards**, the compiler usually cannot deduce every implication relationship between conditions. Two guards that can both be true still compile, and **order determines the result** as shown in Section 4. The section on coverage/exhaustiveness in this chapter analyzes dominated labels and when `default` is needed in greater depth.

## 6. Distinguishing a False Guard from a Type Mismatch

Suppose:

~~~java
return switch (value) {
    case Integer n when n < 0 -> "NEGATIVE_INT";
    case Integer n -> "OTHER_INT";
    case Number n -> "OTHER_NUMBER";
    default -> "OTHER";
};
~~~

- `Integer.valueOf(-2)`: matches Integer, guard `n < 0` is true → `NEGATIVE_INT`.
- `Integer.valueOf(0)`: matches Integer but guard is false → tries the next Integer label → `OTHER_INT`.
- `Double.valueOf(2.5)`: **does not match** the Integer pattern → matches `Number` → `OTHER_NUMBER`.
- `"Go"`: matches neither Integer nor Number → `OTHER`.

The `Integer n` pattern guarantees `n` is non-null and an `Integer` when the guard is evaluated, so `n < 0` can safely unbox for comparison in this case.

**Do not confuse** "guard false" with "selector has the wrong type": both lead to trying subsequent labels, but whether the guard is evaluated differs.

## 7. `null` Requires Its Own Label or a Guard Before the Switch

With Java 21 switch pattern matching, you can write:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    case String s -> "TEXT";
    default -> "OTHER";
};
~~~

Do not assume `default` automatically handles `null` in every form of switch. If a switch has no label handling null appropriately, a null selector can cause a `NullPointerException`.

In stable Java 17, pattern matching for `switch` is not yet a stable feature; a clear approach is to check `if (value == null)` first and then use `instanceof`.

**Note:** an ordinary `String s` pattern does not match null, so `s.isBlank()` does not run for null. Avoid placing null-handling logic inside the String branch body expecting it to run when the selector is null.

## 8. Connection to Java 17 Flow Scoping and `instanceof`

In Java 17, stable pattern matching for `instanceof` can express the equivalent conditions:

~~~java
static String classify17(Object value) {
    if (value == null) return "NULL";
    if (value instanceof String s && s.isBlank()) return "BLANK";
    if (value instanceof String s && s.length() >= 5) return "LONG_TEXT";
    if (value instanceof String s) return "SHORT_TEXT";
    return "OTHER";
}
~~~

In `value instanceof String s && s.length() >= 5`, the right-hand side of `&&` runs only when the pattern matches. This is **flow scoping**, meaning the compiler allows using `s` only where it can prove the pattern matched.

Java 17 **does not need** `when` to teach the rule of placing guards after a type check.

**Two differences:**

- An `if` chain may repeat the `instanceof` check; Java 21 switch expresses multiple pattern labels over the same selector.
- Java 21 enforces **dominance** on pattern label order in switch; if an unguarded broad pattern precedes a subpattern, the error can be caught at compile time. With `if`, a broad condition placed first is usually a logic bug without a compiler warning.

## 9. `when` Differs from an `if` Placed Inside a Case

A guarded label:

~~~java
case String s when s.length() >= 5 -> "LONG_TEXT"
~~~

is selected only when **both the String type and the guard** succeed.

Whereas if you write:

~~~java
case String s -> {
    if (s.length() >= 5) {
        yield "LONG_TEXT";
    }
    yield "SHORT_TEXT";
}
~~~

then **every String** selects the `case String s` label; later case labels will have no chance to handle that String. A `when` guard is therefore not merely shorthand for an `if` inside a case: a false guard means **continue trying other labels**.

Use `when` when failing the condition should hand selection off to another case. Use `if` inside the case body when you intentionally chose that label and want further processing **inside**.

## 10. `switch` Expressions, Statements, and Completeness

Guarded patterns work both when writing a switch **expression** that returns a value and a switch **statement** that performs actions, using the appropriate syntax.

A Java 21 switch expression needs branches covering all selectors. For `Object`, a clear approach is providing `default` and handling null according to policy:

~~~java
String kind = switch (value) {
    case null -> "NULL";
    case String s when !s.isBlank() -> "TEXT";
    case String s -> "BLANK";
    default -> "OTHER";
};
~~~

An arbitrary guard cannot be assumed to always be true to replace a catch-all branch, because `when` can evaluate to false.

**Do not write `case String s when ...` after `case String s`**, because the unguarded general label shadows the guarded label.

If a branch needs multiple statements, use a block `-> { ... yield result; }` in a switch expression; `yield` provides the **value of the switch expression**, and does not replace `when`.

## 11. Guards with Side Effects: Observable Order

In Java 21:

~~~java
static boolean trace(String text) {
    System.out.println("guard:" + text);
    return text.length() > 2;
}

static String choose(Object value) {
    return switch (value) {
        case String s when trace(s) -> "MATCH";
        case null -> "NO_MATCH";
        default -> "NO_MATCH";
    };
}
~~~

- `choose(42)`: **does not call** `trace`, because the String pattern does not match.
- `choose("Go")`: calls `trace("Go")`, guard is false and falls through to default.
- `choose("Java")`: calls `trace("Java")`, guard is true and returns MATCH.

If multiple guarded labels have side effects, **reordering labels can change both side effects and results**. Therefore, avoid calling state-mutating methods inside guards; keep only the necessary boolean condition.

If a guard throws an exception, that is not treated as a false result: the exception propagates along the exception-handling path. Do not expect switch to silently try the next label after an exception.

## 12. Standalone Program on JDK 17+

The file **`PatternGuardOrderDemo17.java`** uses `instanceof` patterns and `if`; it contains no `when` syntax, so it **compiles on Java 17 and newer JDKs**.

~~~java
public final class PatternGuardOrderDemo17 {
    private PatternGuardOrderDemo17() {}

    static String describe(Object value) {
        if (value == null) return "NULL";
        if (value instanceof String s && s.isBlank()) return "BLANK";
        if (value instanceof String s && s.length() >= 5) {
            return "LONG_TEXT:" + s.strip();
        }
        if (value instanceof String s) return "TEXT:" + s;
        if (value instanceof Integer n && n < 0) return "NEGATIVE_INT";
        if (value instanceof Integer n) return "INT:" + n;
        if (value instanceof Number n) {
            return "NUMBER:" + n.getClass().getSimpleName();
        }
        return "OTHER";
    }

    static String priority(Object value) {
        if (value instanceof String s && s.startsWith("A")) {
            return "STARTS_A";
        }
        if (value instanceof String s && s.length() >= 5) return "LONG";
        if (value instanceof String) return "OTHER_STRING";
        return "NOT_STRING";
    }

    static boolean traced(String name, boolean allowed) {
        System.out.println("guard called:" + name);
        return allowed;
    }

    static String trace(Object value) {
        if (value instanceof String s && traced(s, s.length() > 2)) {
            return "MATCH";
        }
        return "NO_MATCH";
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", " example ", "Go",
            Integer.valueOf(-2), Integer.valueOf(0),
            Double.valueOf(2.5), Boolean.TRUE
        };
        for (Object value : inputs) {
            System.out.println("describe=" + describe(value));
        }

        System.out.println("priority Alex=" + priority("Alex"));
        System.out.println("priority AppleTree=" + priority("AppleTree"));
        System.out.println("priority Mexico=" + priority("Mexico"));
        System.out.println("priority Go=" + priority("Go"));
        System.out.println("priority null=" + priority(null));

        System.out.println("trace int=" + trace(7));
        System.out.println("trace Go=" + trace("Go"));
        System.out.println("trace Java=" + trace("Java"));
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 PatternGuardOrderDemo17.java
java -cp . PatternGuardOrderDemo17
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\PatternGuardOrderDemo17.java
java -cp . PatternGuardOrderDemo17
~~~

### Exact expected stdout on JDK 17+

~~~text
describe=NULL
describe=BLANK
describe=LONG_TEXT:example
describe=TEXT:Go
describe=NEGATIVE_INT
describe=INT:0
describe=NUMBER:Double
describe=OTHER
priority Alex=STARTS_A
priority AppleTree=STARTS_A
priority Mexico=LONG
priority Go=OTHER_STRING
priority null=NOT_STRING
trace int=NO_MATCH
guard called:Go
trace Go=NO_MATCH
guard called:Java
trace Java=MATCH
~~~

**Explanation:** `trace(7)` does not call the guard; `trace("Go")` calls the guard and returns false; `trace("Java")` calls the guard and returns true. The ordered `if` branches express the same logic as `when`-guarded labels in Java 21.

## 13. Program Using Actual `when` on JDK 21+

File **`PatternWhenDemo21.java`** (JDK 21 or later, preview disabled):

~~~java
public final class PatternWhenDemo21 {
    private PatternWhenDemo21() {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG_TEXT:" + s.strip();
            case String s -> "TEXT:" + s;
            case Integer n when n < 0 -> "NEGATIVE_INT";
            case Integer n -> "INT:" + n;
            case Number n -> "NUMBER:" + n.getClass().getSimpleName();
            default -> "OTHER";
        };
    }

    static String priority(Object value) {
        return switch (value) {
            case null -> "NOT_STRING";
            case String s when s.startsWith("A") -> "STARTS_A";
            case String s when s.length() >= 5 -> "LONG";
            case String s -> "OTHER_STRING";
            default -> "NOT_STRING";
        };
    }

    static boolean traced(String name, boolean allowed) {
        System.out.println("guard called:" + name);
        return allowed;
    }

    static String trace(Object value) {
        return switch (value) {
            case null -> "NO_MATCH";
            case String s when traced(s, s.length() > 2) -> "MATCH";
            default -> "NO_MATCH";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", " example ", "Go",
            Integer.valueOf(-2), Integer.valueOf(0),
            Double.valueOf(2.5), Boolean.TRUE
        };
        for (Object value : inputs) {
            System.out.println("describe=" + describe(value));
        }

        System.out.println("priority Alex=" + priority("Alex"));
        System.out.println("priority AppleTree=" + priority("AppleTree"));
        System.out.println("priority Mexico=" + priority("Mexico"));
        System.out.println("priority Go=" + priority("Go"));
        System.out.println("priority null=" + priority(null));

        System.out.println("trace int=" + trace(7));
        System.out.println("trace Go=" + trace("Go"));
        System.out.println("trace Java=" + trace("Java"));
    }
}
~~~

**Bash (Linux/macOS), JDK 21+:**

~~~bash
javac --release 21 -encoding UTF-8 PatternWhenDemo21.java
java -cp . PatternWhenDemo21
~~~

**PowerShell (Windows), JDK 21+:**

~~~powershell
javac --release 21 -encoding UTF-8 .\PatternWhenDemo21.java
java -cp . PatternWhenDemo21
~~~

**Exact expected stdout:** identical to **all 18 lines** of the JDK 17 example in Section 12, from `describe=NULL` through `trace Java=MATCH`. Both examples apply the **same rule order**, differing only in syntactic expression.

**Do not do this:** attempt to compile `PatternWhenDemo21.java` with `--release 17`; the Java 17 compiler does not understand the `when` syntax of switch patterns.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Proper Approach |
|---|---|---|
| Writing `case String s when ...` assuming it is stable in Java 17 | Java 17 does not support that syntax | JDK 21+ or Java 17 `if` + `instanceof` |
| Placing unguarded `String s` before `String s when ...` | Later label is dominated, compile error | Guarded labels first, general label after |
| Placing `CharSequence cs` before `String s` | Subsequent String label is dominated | Specific pattern first, broad pattern after |
| Two guards overlap and assuming order does not matter | Result changes depending on the first matching label | Define clear priority, test overlap regions |
| Thinking the guard runs even when the pattern does not match | Leads to false assumptions about NPE/side effects | Guard runs only after the pattern matches |
| Thinking a false guard ends the switch | Misses the fact that later labels are tried | Guard false → continue searching matching labels |
| Putting `when` after a constant label like a guarded pattern | Invalid syntax | Use a pattern or `if` |
| Using `default` expecting it to catch `null` without checking | Can throw NPE on a null selector | Add `case null` on JDK 21, or a null guard |
| Having only guarded cases with no catch-all label | Switch expression may lack coverage | Add a general case/`default` |
| Putting side effects inside a guard | Label order changes behavior | Use pure conditions, separate side effects |
| Thinking `when` equals an `if` inside the chosen branch | False guard tries other cases; inner `if` does not | Choose the intended semantics |
| Mixing `case:` and `case ->` syntax arbitrarily | Compile error | Choose one consistent label style |

## 15. Exercises with Answers

### Exercise A — Predicting guard priority

~~~java
// JDK 21+
String category = switch ("Apple") {
    case String s when s.startsWith("A") -> "A";
    case String s when s.length() >= 5 -> "LONG";
    default -> "OTHER";
};
System.out.println(category);
~~~

**Answer:** `A`. `"Apple"` satisfies both conditions, but the label placed first is selected.

### Exercise B — Finding a dominance error

~~~java
// JDK 21+, DOES NOT COMPILE:
// switch (value) {
//     case Number n -> "NUMBER";
//     case Integer i -> "INTEGER";
//     default -> "OTHER";
// }
~~~

**Answer:** the `Number n` pattern placed first already covers every `Integer`; `case Integer i` must be placed before `case Number n`.

### Exercise C — What happens when a guard is false?

~~~java
// JDK 21+
String result = switch ("Go") {
    case String s when s.length() >= 5 -> "LONG";
    case String s -> "SHORT";
    default -> "OTHER";
};
System.out.println(result);
~~~

**Answer:** `SHORT`. The String pattern matches in the first case, but the guard is false, so Java evaluates the general String case next.

### Exercise D — Writing a Java 17 equivalent

Desired: blank String → BLANK; non-blank String → TEXT; other types → OTHER.

**Answer:**

~~~java
static String categorize(Object value) {
    if (value instanceof String s && s.isBlank()) return "BLANK";
    if (value instanceof String) return "TEXT";
    return "OTHER";
}
~~~

No preview pattern switch is needed on Java 17.

### Exercise E — Null and guards

~~~java
// Java 21+
String label = switch ((Object) null) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    default -> "OTHER";
};
System.out.println(label);
~~~

**Answer:** `NULL`. The `case null` label handles null; the String guard is not called.

## 16. Checklist and Conclusion

- [ ] Know that `when` is a guard for switch pattern labels stable since JDK 21, **not Java 17 syntax**.
- [ ] Know that Java 17 can use `instanceof` patterns combined with `&&` and `if` to express the same conditions.
- [ ] Understand that a guard runs only after the type pattern matches; the pattern variable is usable in the guard and the branch.
- [ ] Understand that a false guard causes subsequent labels to be evaluated rather than running the current branch body.
- [ ] Know that guarded labels can overlap and the first matching label is chosen.
- [ ] Recognize dominance: an unguarded broad label before a narrower label can prevent code from compiling.
- [ ] Place specific and guarded pattern labels before unguarded catch-all labels.
- [ ] Handle null appropriately for the Java version; do not assume `default` accepts null.
- [ ] Understand how `when` differs from an `if` placed inside an already selected case.
- [ ] Ensure switch expressions have branches covering the data and a matching result type.
- [ ] Avoid side effects in guards, and test boundary values and overlapping conditions.
- [ ] Run `PatternGuardOrderDemo17.java` on JDK 17+ and `PatternWhenDemo21.java` on JDK 21+, then compare stdout.

**Conclusion:** The `when` guard allows adding a condition after a type pattern in Java 21+ switches. When the pattern matches but the guard is false, Java tries subsequent labels; thus, **pattern label order is part of the program's semantics**. An unguarded general pattern can *dominate* a narrower or guarded label placed after it and be rejected by the compiler. On Java 17, use `instanceof` patterns with `if`/`&&` to achieve the same logic without preview.
