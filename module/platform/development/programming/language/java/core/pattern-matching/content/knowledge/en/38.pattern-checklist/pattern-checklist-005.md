# Exhaustiveness and Sealed Types Checklist in Java 21

## 1. Purpose of the Checklist

When using **pattern matching for `switch`**, a program must answer an important question: **“Does every valid value of the selector type have a handling path?”** In Java 21, the compiler can check the *exhaustiveness* of a `switch expression` and `switch statements` that have pattern/null labels. With **sealed types** and **enums**, this check is especially useful because the compiler knows the declared type branches or constants.

This lesson belongs to the **Checklist pattern** group, focusing on the **Exhaustiveness and Sealed Types Checklist**. The goal is not just to remember to “add enough cases,” but to learn how to review a set of branches according to the language's logic: which subtypes are permitted, which cases cover those subtypes, whether a guard can evaluate to false, how `null` is handled, whether a broader branch dominates a narrower one, and what happens as the data model evolves.

After this lesson, you will be able to:

- Distinguish between a *sealed hierarchy* (a controlled set of direct subtypes) and *switch exhaustiveness* (a specific property of each individual switch).
- Identify sufficient branches for a `sealed interface` with multiple `record`s, for an `enum`, and for a `non-sealed` branch.
- Recognize that **a guarded case does not necessarily cover the entire subtype**; a fallback is needed when the guard can evaluate to false.
- Avoid overusing `default`, which hides compile-time signals when adding new subtypes.
- Check **null selectors**, **nulls in nested records**, and **nulls in leaf components** as three separate scenarios.
- Distinguish between *non-exhaustive* errors, *dominated case* errors, syntax errors, and business logic bugs even when the code compiles.
- Use a self-contained Java 21 program, a set of intentionally failing compiler test cases, and a practical checklist before merging pull requests.

**Version:** Java 21 and later. Sealed classes/interfaces became standard in Java 17 (JEP 409); record patterns and pattern matching for `switch` became standard in Java 21 (JEP 440, JEP 441). The demonstration program uses `javac --release 21`, without needing `--enable-preview`.

## 2. Foundation: `sealed` Does Not Mean “Automatically Exhaustive”

Consider the command hierarchy:

```java
sealed interface Command permits Open, Fund, Close {}

record Open(String id) implements Command {}
record Fund(String id, int cents) implements Command {}
record Close(String id, String reason) implements Command {}
```

The declarations above are in the same illustrative scope; Section 6 places them inside a complete class for easy execution.

What `sealed interface Command` means:

- It specifies that the **direct permitted subtypes** are `Open`, `Fund`, and `Close`.
- The records above are implicitly `final` and cannot be arbitrarily subclassed.
- The compiler can use this subtype graph to determine whether a `switch` has a handling path for every non-null `Command`.
- `sealed` **does not automatically validate the internal data**. `new Open(null)` is a type-valid `Open` object, even though business logic might reject a null ID.
- `sealed` **does not automatically handle a null selector** and does not automatically write the correct logic for each subtype.

A simple `switch expression`:

```java
static String kind(Command command) {
    return switch (command) {
        case Open open -> "OPEN";
        case Fund fund -> "FUND";
        case Close close -> "CLOSE";
    };
}
```

Three type patterns cover the three existing non-null `Command` types. **No `default` is needed just for exhaustiveness.** However, calling `kind(null)` on a version without `case null` can throw a `NullPointerException`; type exhaustiveness **does not automatically establish a policy for null**.

In the complete example, we will include `case null` to express an explicit policy.

### 2.1. `sealed` Enforces Direct Boundaries, It Does Not Magically Close the Entire Codebase

A direct permitted subtype of a sealed hierarchy must follow the appropriate modifier rules, such as `final`, `sealed`, or `non-sealed`. If a branch is **`non-sealed`**, subclasses of that branch can extend it further. In that case, `case NonSealedType value` covers objects of subclasses of `NonSealedType`, whereas a case that only handles specific leaf subclasses may fail to cover the entire open branch.

**First checklist item:** read the `sealed ... permits ...` definition and its direct subtypes; do not infer the set of subtypes solely from the `case`s currently present in the switch.

## 3. Quick Checklist: 12 Questions Before Reviewing a Switch

| # | What to verify | Why it matters |
|---|---|---|
| 1 | What is the selector's **static type**? | Exhaustiveness is evaluated based on the selector type and its corresponding rules, not just a single tested object |
| 2 | Is that type an `enum`, `sealed`, an open type, or generic? | Coverage rules differ |
| 3 | If `sealed`, what are **all the direct permitted subtypes**? | Avoids missing a subtype, especially a rarely used branch |
| 4 | Is each subtype `sealed`, `final`, or `non-sealed`? | A `non-sealed` branch can have many subclasses |
| 5 | Does each subtype have a case **broad enough** to cover all of it? | A guard can evaluate to false; record deconstruction can fail |
| 6 | Is there any guarded case missing a fallback for the same subtype? | A pattern match does not mean the guard is true |
| 7 | Does a general case appear before a narrower case? | The compiler may report a `dominated case label` |
| 8 | Is `null` handled explicitly or rejected by contract? | A plain `default` does not replace `case null` |
| 9 | Does a nested record pattern have a nullable record component? | A null nested record can cause deep patterns not to match |
| 10 | Does a `default` hide a missing subtype/enum constant? | Can lose the benefit of exhaustive checking when the model changes |
| 11 | Are there tests for guard true/false, null, and boundary values for each subtype? | The compiler does not prove business conditions are correct |
| 12 | When a new subtype is added, does the build/CI report missing handling? | Ensures the evolution contract of the sealed hierarchy is maintained |

**Key check question:** “If a new subtype is added tomorrow, do I want the compiler to force updating the handler, or do I intentionally want that subtype to go to a fallback?” If you want the compiler to remind you, you should generally **not add a general `default`** in a closed-domain switch.

## 4. Three Layers of Coverage: Type, Record Pattern, and Guard

Example of a command classification handler:

```java
return switch (command) {
    case null -> "NULL_COMMAND";

    case Open(var id) when hasText(id) -> "OPEN:" + id;
    case Open ignored -> "REJECT_OPEN";

    case Fund(var id, var cents)
            when hasText(id) && cents > 0
            -> "FUND:" + id + ":" + cents;
    case Fund ignored -> "REJECT_FUND";

    case Close(var id, var reason)
            when hasText(id) && hasText(reason)
            -> "CLOSE:" + id + ":" + reason;
    case Close ignored -> "REJECT_CLOSE";
};
```

This is a snippet inside a method that has a `command` variable and a `hasText` helper; the runnable program is in Section 6.

Distinguish the three layers:

1. **Type coverage:** includes `Open`, `Fund`, `Close` — the three direct subtypes.
2. **Pattern coverage:** each `case Open(var id)` matches a non-null `Open` record and binds the `id` component. A reference-type component can be null when bound with `var` in a record pattern.
3. **Guard coverage:** `when hasText(id)` can evaluate to false. Therefore, a guarded `Open` is **not** sufficient for all `Open` instances. The unguarded `case Open ignored` branch guarantees handling the remainder.

If you only have:

```java
case Fund(var id, var cents) when cents > 0 -> "POSITIVE";
```

then `Fund` with `cents == 0` or negative values still exists. The guard is false, so the branch is not selected. For a `switch expression` that only has this `Fund` branch and no other branch covering the remainder, the compiler will report **non-exhaustive**.

### 4.1. Special Case: `when true`

Do not memorize the false rule “no guarded case can ever be exhaustive.” In Java 21, a constant guard `when true` can be treated as equivalent to an unguarded pattern when checking coverage:

```java
class WhenTrueCheck {
    sealed interface Job permits Run {}
    record Run(int count) implements Job {}

    static String code(Job job) {
        return switch (job) {
            case Run(var count) when true -> "RUN";
        };
    }
}
```

**The snippet above is accepted by `javac --release 21`.** However, `when true` does not improve clarity; in code reviews, an unguarded branch is usually easier to understand. For business conditions like `count > 0`, never assume a guard will always be true.

### 4.2. Rules for Reviewing Guarded Branches

For every `case Subtype(...) when condition`, ask:

- Are there any values of the subtype that make `condition == false`?
- If so, which **subsequent** branch receives those values?
- If the condition uses `&&`/`||`, are null guards safe and parentheses placed correctly?
- Are there boundary values like `0`, `-1`, or blank strings that expose the fallback?
- If two guarded cases can both be true, does their priority order match the contract?

The compiler can detect certain branches dominated by type relationships, but it does not fully verify the business logic of complex boolean expressions.

## 5. Null: Exhaustive Does Not Mean Null-Safe

### 5.1. Null Selector in a Switch

In a Java 21 pattern switch, a null selector requires an explicit policy if you want to avoid a `NullPointerException`. For example:

```java
case null -> "NULL_COMMAND";
```

A plain `default` **does not automatically replace `case null`**. This differs from `value instanceof Open open`, which returns false if `value == null`.

In the enum example of the runnable program, `phase(null)` **throws a `NullPointerException`** because that enum `switch` has no null branch. The demonstration code even catches that exact exception to print it to stdout. Thus, the compiler allows an enum switch to be exhaustive over all enum constants without requiring a null branch.

### 5.2. A Null Nested Record Causes Deep Patterns to Fail

Suppose:

```java
record Envelope(String trace, Command command) {}
```

and a switch containing:

```java
case Envelope(var trace, Open(var id)) -> "NESTED_OPEN:" + id;
case Envelope(var trace, Fund(var id, var cents))
        -> "NESTED_FUND:" + cents;
case Envelope(var trace, Close(var id, var reason))
        -> "NESTED_CLOSE:" + reason;
case Envelope ignored -> "NESTED_MISSING";
```

Given `new Envelope("e1", null)`, the root `Envelope` is **non-null**, but the `Command` component is null, so the nested patterns `Open(...)`, `Fund(...)`, and `Close(...)` **all fail to match**. The `Envelope ignored` branch will handle it.

Thus, **even though all three subtypes of `Command` are listed**, a deep record switch may still need a fallback because of a **nullable nested component**. You must not infer that “I wrote all subtypes, so every nested record is guaranteed to match.”

### 5.3. A Null Leaf Component Can Still Match

Given:

```java
new Envelope("e2", new Open(null))
```

the nested `Open(var id)` **matches** because the `Open` object exists and `var id` can bind null. The string `"NESTED_OPEN:" + id` becomes `NESTED_OPEN:null`. If business rules disallow a null ID, a separate validation guard is needed — exhaustiveness does not prove data validity.

**The null checklist has three separate checkboxes:** null selector, null nested record, and null leaf component. These positions have different semantics.

## 6. Complete Java 21 Program with Automated Checks

Create the file **`ExhaustivenessChecklistDemo.java`**. The code requires no dependencies outside the JDK. The program demonstrates:

- A sealed hierarchy consisting of three record commands.
- `route` with guarded cases and per-subtype fallbacks.
- `kind` classifying subtypes with type patterns.
- `nested` deconstructing a record containing a `Command` with a fallback for a null nested component.
- A `Phase` enum with a switch expression covering all three constants.
- Assertions comparing against independent expected values.

```java
import java.util.Objects;

public class ExhaustivenessChecklistDemo {
    sealed interface Command permits Open, Fund, Close {}
    record Open(String id) implements Command {}
    record Fund(String id, int cents) implements Command {}
    record Close(String id, String reason) implements Command {}
    record Envelope(String trace, Command command) {}
    enum Phase { NEW, RUNNING, DONE }

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static String route(Command command) {
        return switch (command) {
            case null -> "NULL_COMMAND";
            case Open(var id) when hasText(id) -> "OPEN:" + id;
            case Open ignored -> "REJECT_OPEN";
            case Fund(var id, var cents)
                    when hasText(id) && cents > 0 -> "FUND:" + id + ":" + cents;
            case Fund ignored -> "REJECT_FUND";
            case Close(var id, var reason)
                    when hasText(id) && hasText(reason)
                    -> "CLOSE:" + id + ":" + reason;
            case Close ignored -> "REJECT_CLOSE";
        };
    }

    static String kind(Command command) {
        return switch (command) {
            case null -> "NONE";
            case Open open -> "OPEN";
            case Fund fund -> "FUND";
            case Close close -> "CLOSE";
        };
    }

    static String nested(Envelope envelope) {
        return switch (envelope) {
            case null -> "NULL_ENVELOPE";
            case Envelope(var trace, Open(var id)) -> "NESTED_OPEN:" + id;
            case Envelope(var trace, Fund(var id, var cents))
                    -> "NESTED_FUND:" + cents;
            case Envelope(var trace, Close(var id, var reason))
                    -> "NESTED_CLOSE:" + reason;
            case Envelope ignored -> "NESTED_MISSING";
        };
    }

    static String phase(Phase value) {
        return switch (value) {
            case NEW -> "NEW";
            case RUNNING -> "RUNNING";
            case DONE -> "DONE";
        };
    }

    static void check(String label, Command command,
                      String expectedResult, String expectedKind) {
        String result = route(command);
        String actualKind = kind(command);
        if (!Objects.equals(expectedResult, result)
                || !Objects.equals(expectedKind, actualKind)) {
            throw new AssertionError(label + " result=" + result
                    + " kind=" + actualKind);
        }
        System.out.println(label + " => " + result + " | kind=" + actualKind);
    }

    static void checkNested(String label, Envelope envelope, String expected) {
        String result = nested(envelope);
        if (!Objects.equals(result, expected)) {
            throw new AssertionError(label + " expected=" + expected
                    + ", actual=" + result);
        }
        System.out.println(label + " => " + result);
    }

    public static void main(String[] args) {
        check("null command", null, "NULL_COMMAND", "NONE");
        check("open good", new Open("O1"), "OPEN:O1", "OPEN");
        check("open null id", new Open(null), "REJECT_OPEN", "OPEN");
        check("open blank id", new Open(" "), "REJECT_OPEN", "OPEN");
        check("open spaced id", new Open(" O2 "), "OPEN: O2 ", "OPEN");
        check("fund positive", new Fund("F1", 1), "FUND:F1:1", "FUND");
        check("fund large", new Fund("F2", 500), "FUND:F2:500", "FUND");
        check("fund zero", new Fund("F3", 0), "REJECT_FUND", "FUND");
        check("fund negative", new Fund("F4", -1), "REJECT_FUND", "FUND");
        check("fund null id", new Fund(null, 20), "REJECT_FUND", "FUND");
        check("fund blank id", new Fund("", 20), "REJECT_FUND", "FUND");
        check("close good", new Close("C1", "done"),
                "CLOSE:C1:done", "CLOSE");
        check("close null reason", new Close("C2", null),
                "REJECT_CLOSE", "CLOSE");
        check("close blank reason", new Close("C3", " "),
                "REJECT_CLOSE", "CLOSE");
        check("close null id", new Close(null, "done"),
                "REJECT_CLOSE", "CLOSE");
        check("close blank id", new Close("", "done"),
                "REJECT_CLOSE", "CLOSE");

        checkNested("null envelope", null, "NULL_ENVELOPE");
        checkNested("nested null command", new Envelope("e1", null),
                "NESTED_MISSING");
        checkNested("nested open", new Envelope("e2", new Open("O1")),
                "NESTED_OPEN:O1");
        checkNested("nested open null leaf",
                new Envelope("e3", new Open(null)), "NESTED_OPEN:null");
        checkNested("nested fund", new Envelope(null, new Fund("F1", 1)),
                "NESTED_FUND:1");
        checkNested("nested close", new Envelope("e5",
                new Close("C1", null)), "NESTED_CLOSE:null");

        for (Phase p : Phase.values()) {
            System.out.println("phase " + p + " => " + phase(p));
        }
        try {
            phase(null);
            throw new AssertionError("Expected NPE for null enum selector");
        } catch (NullPointerException expected) {
            System.out.println("phase null => NullPointerException");
        }
    }
}
```

### 6.1. How to Run

```bash
javac --release 21 ExhaustivenessChecklistDemo.java
java ExhaustivenessChecklistDemo
```

**Directly verified stdout:**

```text
null command => NULL_COMMAND | kind=NONE
open good => OPEN:O1 | kind=OPEN
open null id => REJECT_OPEN | kind=OPEN
open blank id => REJECT_OPEN | kind=OPEN
open spaced id => OPEN: O2  | kind=OPEN
fund positive => FUND:F1:1 | kind=FUND
fund large => FUND:F2:500 | kind=FUND
fund zero => REJECT_FUND | kind=FUND
fund negative => REJECT_FUND | kind=FUND
fund null id => REJECT_FUND | kind=FUND
fund blank id => REJECT_FUND | kind=FUND
close good => CLOSE:C1:done | kind=CLOSE
close null reason => REJECT_CLOSE | kind=CLOSE
close blank reason => REJECT_CLOSE | kind=CLOSE
close null id => REJECT_CLOSE | kind=CLOSE
close blank id => REJECT_CLOSE | kind=CLOSE
null envelope => NULL_ENVELOPE
nested null command => NESTED_MISSING
nested open => NESTED_OPEN:O1
nested open null leaf => NESTED_OPEN:null
nested fund => NESTED_FUND:1
nested close => NESTED_CLOSE:null
phase NEW => NEW
phase RUNNING => RUNNING
phase DONE => DONE
phase null => NullPointerException
```

**Verification results:** 16 command cases (each checking both `route` and `kind`), 6 `Envelope` record cases, 3 non-null enum cases, and 1 null enum case intentionally catching the exception. A total of **26 output lines** were printed. The program compiled successfully with `javac --release 21` and ran without any unexpected `AssertionError`.

Note the `Open(" O2 ")` case: the `hasText` helper only checks non-null and non-blank; it **does not trim**. Therefore, the output preserves the spaces in the ID. If the domain requires ID normalization, add that rule at the boundary and update the tests rather than assuming `isBlank()` normalizes strings.

### 6.2. What Does This Program Prove?

- The existing case branches are accepted by the compiler as exhaustive for the three sealed subtypes.
- Guarded cases that evaluate to false fall through to the fallback for the same subtype.
- A null selector is handled explicitly when `case null` is present.
- A null nested `Command` is handled by the `Envelope` fallback.
- A null leaf component can be bound, and a guard can reject it according to policy.
- An enum switch has enough constants to compile, yet can still throw an NPE on a null selector.
- The test suite has fixed expected values, helping detect behavioral differences if someone reorders branches or removes a guard.

The example suite **does not prove** that all data types from external APIs are valid, or that swapping precompiled classpaths will be safe; code reviews and regression tests are still required in real projects.

## 7. Five Representative Compiler Errors for Missing Exhaustiveness or Wrong Ordering

The samples below **intentionally do not compile**. Save each snippet to the exact specified filename and run them separately; **do not place them together with the program from Section 6**. All five cases have been verified to be rejected by `javac --release 21`.

### 7.1. Missing a Direct Subtype

File **`MissingSubtype.java`**:

```java
class MissingSubtype {
    sealed interface Command permits Open, Close {}
    record Open() implements Command {}
    record Close() implements Command {}

    static String route(Command command) {
        return switch (command) {
            case Open open -> "OPEN";
        };
    }
}
```

Compile:

```bash
javac --release 21 MissingSubtype.java
```

**Why does it fail?** The `Command` set includes both `Open` and `Close`, but the switch expression only has `Open`. There is no handling path for `Close`. **Fix:** add `case Close close -> "CLOSE";` according to the contract, rather than rushing to add `default`.

### 7.2. Guarded Case Only

File **`GuardOnly.java`**:

```java
class GuardOnly {
    sealed interface Command permits Fund {}
    record Fund(int cents) implements Command {}

    static String route(Command command) {
        return switch (command) {
            case Fund(var cents) when cents > 0 -> "POSITIVE";
        };
    }
}
```

Compile:

```bash
javac --release 21 GuardOnly.java
```

**Why does it fail?** `Fund(-1)` and `Fund(0)` are valid `Fund` values in Java, but the guard `cents > 0` is false. The switch does not cover them. **Fix:** add `case Fund ignored -> "NOT_POSITIVE";` after the guarded branch.

Do not replace the logic with `when true` just to achieve exhaustiveness, because that defeats the requirement to accept only positive numbers.

### 7.3. Broad Branch Dominates Two Narrow Branches

File **`DominatedCase.java`**:

```java
class DominatedCase {
    sealed interface Command permits Open, Close {}
    record Open() implements Command {}
    record Close() implements Command {}

    static String route(Command command) {
        return switch (command) {
            case Command any -> "ANY";
            case Open open -> "OPEN";
            case Close close -> "CLOSE";
        };
    }
}
```

Compile:

```bash
javac --release 21 DominatedCase.java
```

**Why does it fail?** `case Command any` already matches every non-null `Command`. The subsequent `Open`/`Close` branches are **dominated**. **Fix:** place the specific subtypes first; remove the general branch if it is no longer needed.

### 7.4. Missing an Enum Constant

File **`MissingEnumConstant.java`**:

```java
class MissingEnumConstant {
    enum Phase { NEW, RUNNING, DONE }

    static String route(Phase phase) {
        return switch (phase) {
            case NEW -> "NEW";
            case RUNNING -> "RUNNING";
        };
    }
}
```

Compile:

```bash
javac --release 21 MissingEnumConstant.java
```

**Why does it fail?** The `DONE` constant is missing. In an enum switch expression, listing all constants enables compiler checking. If you add `default`, missing `DONE` will no longer be reported at compile time. You should add `case DONE -> "DONE";`.

### 7.5. Forgetting a `non-sealed` Branch

File **`MissingNonSealed.java`**:

```java
class MissingNonSealed {
    sealed interface Signal permits Known, Extension {}
    record Known() implements Signal {}
    non-sealed static class Extension implements Signal {}

    static String route(Signal signal) {
        return switch (signal) {
            case Known known -> "KNOWN";
        };
    }
}
```

Compile:

```bash
javac --release 21 MissingNonSealed.java
```

**Why does it fail?** `Signal` has two direct permitted subtypes: `Known` and `Extension`. `Extension` is `non-sealed`, can have other subclasses, and this branch is completely unhandled. **Fix:** add a case for `Extension` or design a clear fallback according to the domain.

**Common takeaway:** compile-time errors cannot be fixed by runtime tests. You must fix the branch set or the type model first, and then test behavior.

## 8. `non-sealed`: How to Cover an Open Branch?

A sealed hierarchy can be open at one branch:

```java
sealed interface Signal permits Known, Extension {}
record Known() implements Signal {}
non-sealed class Extension implements Signal {}
```

This means every `Signal` is directly a `Known` or an `Extension`; however, objects of subclasses of `Extension` are also `Extension`s. Therefore, the branch:

```java
case Extension extension -> "EXTENSION";
```

can cover both `Extension` and its subclasses.

### Standalone Verification Program

Create the file **`NonSealedCoverageDemo.java`**:

```java
public class NonSealedCoverageDemo {
    sealed interface Signal permits Known, Extension {}
    record Known() implements Signal {}
    non-sealed static class Extension implements Signal {}
    static final class ExtensionChild extends Extension {}

    static String route(Signal signal) {
        return switch (signal) {
            case Known known -> "KNOWN";
            case Extension extension -> "EXTENSION";
        };
    }

    public static void main(String[] args) {
        System.out.println("known => " + route(new Known()));
        System.out.println("extension => " + route(new Extension()));
        System.out.println("extension child => " + route(new ExtensionChild()));
    }
}
```

Compile/run:

```bash
javac --release 21 NonSealedCoverageDemo.java
java NonSealedCoverageDemo
```

**Verified stdout:**

```text
known => KNOWN
extension => EXTENSION
extension child => EXTENSION
```

This is a point to highlight in reviews: **`sealed`** constrains **direct** subtypes; when a branch is `non-sealed`, the set of indirect subtypes can be open, yet a type pattern right at that branch can still cover all descendants.

If you only list a few specific subclasses of `Extension` without a case covering `Extension` itself, the compiler does not have enough basis to confirm that all current and future `Extension` instances are handled.

## 9. Enum Switches: How to Keep the Exhaustiveness Advantage When Adding Constants

Given:

```java
enum Phase { NEW, RUNNING, DONE }
```

An exhaustive switch expression:

```java
static String label(Phase phase) {
    return switch (phase) {
        case NEW -> "NEW";
        case RUNNING -> "RUNNING";
        case DONE -> "DONE";
    };
}
```

If the enum source is updated with `PAUSED` and you **recompile** the entire module containing this switch, the compiler will require updating the handler. That helps avoid an ambiguous “unknown” branch for a new valid state.

### When Is `default` Appropriate?

`default` is not strictly forbidden. For selectors of an open type (e.g., `Object`) or domains that require a general fallback for unrecognized values, `default` can make sense. Express that decision with meaningful names/results and dedicated tests.

However, for an enum/sealed type **controlled by the same module**, if the goal is to **force updating handlers when new states are added**, you should not use a generic default such as:

```java
default -> "UNKNOWN";
```

A `default` can let the build continue succeeding even though nobody has decided how to handle `PAUSED`.

### Difference Between Compile-Time and Deployment

Exhaustiveness is checked using **type information at compile time**. A system deploying JARs compiled at different times may face binary compatibility or runtime behavior risks when variants change. Do not treat exhaustiveness checking as a guarantee that all runtime/classpath combinations will run correctly. Rebuild, run regression tests, and control versions of co-evolving modules.

## 10. Switch Expressions, Enhanced Switch Statements, and Traditional Switches

In Java 21, avoid lumping all `switch` forms into a single simple rule “switch must always be exhaustive.”

### Switch Expression

```java
String result = switch (command) {
    case Open open -> "OPEN";
    case Fund fund -> "FUND";
    case Close close -> "CLOSE";
};
```

A switch expression must be exhaustive according to language rules. This example assumes the `command` variable has type `Command`.

### Enhanced Switch Statement Using Pattern Labels

```java
static void printCommand(Command command) {
    switch (command) {
        case Open open -> System.out.println("OPEN");
        case Fund fund -> System.out.println("FUND");
        case Close close -> System.out.println("CLOSE");
    }
}
```

This is an **enhanced switch statement** because it has pattern labels. Java 21 requires it to be exhaustive, even though it is a statement rather than an expression. Conversely, many legacy **traditional switch statements** with constant case labels are not always exhaustiveness-checked in the same way.

### Traditional Switch Statement

```java
static void printLevel(int level) {
    switch (level) {
        case 1:
            System.out.println("LOW");
            break;
        case 2:
            System.out.println("HIGH");
            break;
    }
}
```

This example illustrates allowing `level` values other than 1 or 2 to print nothing. To handle the entire integer domain, a fallback policy is needed; however, do not infer from this traditional switch statement compiling that **all pattern switches** can also omit branches.

**Review checklist:** clearly identify the kind of switch you are reading, the selector type, the case labels, and the corresponding exhaustiveness rules, rather than applying one default rule to all.

## 11. Table Distinguishing Compile-Time Checks and Behavioral Tests

| What to verify | Java 21 Compiler | Unit tests / code review |
|---|---|---|
| Is the pattern type valid? | Yes | Does not replace the compiler |
| Is the pattern variable scope correct? | Yes | Can help detect logic bugs |
| Is a case dominated? | Yes, per language rules | No runtime tests when code does not compile |
| Is a sealed subtype missing in a switch expression? | Yes | Behavioral tests needed after adding it |
| Can a guard be false in practice? | Analyzed only under specific language rules | **Must test business conditions** |
| Is an enum constant missing a case in a switch expression? | Yes | Must test each state |
| Does `null` cause an NPE or get handled explicitly? | Does not choose a policy for the developer by default | **Must test** |
| Is a null leaf component validated properly? | Compiler knows types, not domain policy | **Must test** |
| Does the `Open` branch actually return the right business result? | No | **Must test** |
| Are side effects like DB/events correct? | No | Integration tests, mocks/fakes, review |
| Does the build use the right version/module of new subtypes? | Requires accurate build configuration | CI/regression/deployment checks |

**Do not equate compile success with correct exhaustive behavior.** The compiler proves what is described by the type system and switch rules; it does not know that `Fund(0)` must be rejected or what error a `Close` with a blank reason should show.

## 12. Test Checklist to Protect Exhaustiveness Over Time

A regression test suite should include multiple categories:

1. **Each direct subtype:** at least one input of `Open`, `Fund`, and `Close`.
2. **Passing guards:** `Open` with non-blank ID, `Fund` with positive cents, `Close` with non-blank ID/reason.
3. **Failing guards:** null/blank ID, zero/negative cents, null/blank reason.
4. **Root null:** verify `case null` or the designed exception.
5. **Null nested record:** root `Envelope` with a null `Command` component.
6. **Null leaf:** `Envelope` containing `Open(null)`, with its own expected result.
7. **Enum constants:** every value from `Phase.values()` has the expected label.
8. **Null enum:** if the API can receive null, verify NPE or null handling per contract.
9. **New subtype:** update `permits` and confirm the build forces reviewing uncovered switches, then add cases/tests.
10. **`non-sealed` branch:** test both direct `Extension` and a subclass if the policy uses `case Extension`.
11. **Independent expected tests:** do not merely compare two implementations against each other because both could share the same bug.
12. **Clean CI rebuild:** run the build with the right source target and ensure all dependent modules are recompiled.

JUnit 5 example for one method of the Section 6 program (requires the JUnit dependency and placing the test in the same package):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ExhaustivenessChecklistTests {
    @Test
    void openWithNullIdGoesToSubtypeFallback() {
        var command = new ExhaustivenessChecklistDemo.Open(null);
        assertEquals("REJECT_OPEN",
                ExhaustivenessChecklistDemo.route(command));
    }

    @Test
    void fundAtZeroDoesNotPassGuard() {
        var command = new ExhaustivenessChecklistDemo.Fund("F3", 0);
        assertEquals("REJECT_FUND",
                ExhaustivenessChecklistDemo.route(command));
    }

    @Test
    void nullableNestedCommandHasExplicitFallback() {
        var envelope = new ExhaustivenessChecklistDemo.Envelope("e1", null);
        assertEquals("NESTED_MISSING",
                ExhaustivenessChecklistDemo.nested(envelope));
    }
}
```

This is an **illustrative JUnit 5 snippet**, not part of the code compiled with `javac --release 21` without framework classpath dependencies. The methods and records in the main program have package-private visibility, so the snippet must be in the same package. In a real codebase, separate the domain model and test fixtures appropriately.

A dynamic check using `Phase.values()` can detect new constants at runtime, but **do not write a loop without expected values**. If every new constant automatically falls into a default, a “does not throw an exception” test can pass without the domain having proper handling.

## 13. Pull Request Review Checklist: Pre-Merge Workflow

### Before Inspecting the Switch

- [ ] Confirm the JDK/source level supports Java 21 pattern switches and record patterns.
- [ ] Check the selector type: `Command`, `Object`, enum, or generic type.
- [ ] Open the `sealed ... permits ...` definition and note the direct subtypes.
- [ ] For each subtype, determine whether it is `final`, `sealed`, or `non-sealed`.
- [ ] Clarify whether a null selector is a valid input or an error.

### While Inspecting Each Case

- [ ] There is a branch for each subtype per policy, without relying on an ambiguous default.
- [ ] Guarded cases appear before the fallback for the same subtype.
- [ ] Guards that can evaluate to false are handled by a corresponding subsequent case.
- [ ] Nullable nested records have a fallback if needed.
- [ ] Nullable components are not dereferenced before being checked.
- [ ] No broad branch dominates a narrow branch; the compiler does not report dominance.
- [ ] Enum constants are exhaustively listed if exhaustive checking is desired.
- [ ] No new default was added merely to silence a compiler error.
- [ ] Switch expression branches return the right result type/behavior per contract.

### Before Merging

- [ ] Clean build with `javac --release 21` or equivalent build configuration.
- [ ] Unit tests cover all subtypes, guard true/false, null, and boundaries.
- [ ] Tests verify independent outputs, not just “runs without throwing.”
- [ ] Regression tests exist for new subtypes or new properties.
- [ ] When a sealed hierarchy changes in another module, CI rebuilds and runs consumer tests.
- [ ] Side effects of every branch and fallback have been reviewed.
- [ ] `default` is not forced merely due to a formatter or habit from legacy switches.

The goal of the checklist is to avoid **both extremes**: a switch that always has a `default` so nobody notices a missing new subtype; or a switch “without a `default`” that only has guarded cases and is therefore not actually exhaustive.

## 14. Common Pitfalls

### 14.1. “The sealed type has three subtypes, and I wrote three guarded cases, so that’s enough”

Not necessarily. A `Fund(cents=0)` may fail the `cents > 0` guard. You need an unguarded fallback or another expression covering the remaining `Fund` values. `GuardOnly.java` is rejected by the compiler for this exact reason.

### 14.2. “Adding a `default` is always safer”

`default` can be a reasonable policy for an open type set, but for sealed/enum types, it can suppress the signal to update cases when a new subtype/constant is added. “Green build” does not guarantee “fully reviewed logic.”

### 14.3. “Without `default`, null will automatically enter a subtype’s case”

No. A null root is not an object of any subtype. If the API wants to turn null into a specific message, add `case null`. The enum switch example confirmed that null can throw an NPE even when all three constants are present.

### 14.4. “I listed all nested record subtypes, so no fallback is needed”

A nested record component can be null. `Envelope("e1", null)` does not match the nested `Open`/`Fund`/`Close` patterns. An `Envelope` fallback is needed if you want to handle that case without throwing an error for having no matching case.

### 14.5. “The pattern matched, so every component is guaranteed non-null”

No. `Open(var id)` can bind `id == null`. Exhaustive matching does not mean validation. For business rules, you need a guard like `hasText(id)`.

### 14.6. “The compiler knows whether I want `Open` before `Fund` or `Fund` before `Close`”

The compiler knows typing/dominance rules; it does not know all business priorities. With multiple guards on the same subtype, two conditions can be true simultaneously. Case ordering is part of the policy that must be tested.

### 14.7. “Every switch statement must be exhaustive”

Incorrect. Distinguish between a traditional switch statement and an enhanced switch statement using pattern/null labels; Java 21 has separate rules. A switch expression must be exhaustive, whether the selector is an enum or a sealed type.

### 14.8. “`non-sealed` doesn’t matter because `sealed` already listed `Extension`”

A `non-sealed` branch can have many subclasses. A type pattern `Extension extension` typically covers subclasses as well; handling only a few specific subclasses is not enough to claim coverage of the entire branch.

### 14.9. “The compiler will point out a domain bug when a case returns the wrong label”

No. The compiler accepts `case Open open -> "CLOSE";` as long as the types are valid. Only behavioral tests and reviews catch labels that violate the contract.

### 14.10. “There’s no need to rebuild consumers when the model is extended”

When a sealed/enum type is modified in another module, un-rebuilt consumer sources will not go through the new exhaustiveness check. CI must ensure version-consistent checks across modules rather than relying on a stale local build.

## 15. Self-Check Exercises with Answers

### Exercise 1 — Adding a New Subtype

You extend:

```java
sealed interface Command permits Open, Fund, Close, Refund {}
record Refund(String id, int cents) implements Command {}
```

but do not update `route`. What happens when recompiling a switch expression without `default`?

**Answer:** The compiler will report non-exhaustive because `Refund` has no branch. You need to design `case Refund(...)` and tests for valid/invalid data; do not arbitrarily add `default` to hide missing logic.

### Exercise 2 — Guard Does Not Cover Zero

You only have:

```java
case Fund(var id, var cents) when cents > 0 -> "OK";
```

What result does `Fund(0)` get in a switch expression with no other case?

**Answer:** There is no branch for `Fund(0)`, so the switch expression cannot be considered exhaustive under standard rules. Adding `case Fund ignored -> "REJECT";` is one solution.

### Exercise 3 — `default` and Exhaustive Checking

An enum handler has three constants, but the author only lists two constants and adds `default`. Can the code compile? Will it force an update when a fourth constant is added?

**Answer:** It can compile thanks to `default`. When a new constant is added, `default` can continue receiving that value without forcing the author to update the branches. If the domain requires explicit handling for each constant, list all of them.

### Exercise 4 — Null Nested Component

Given `new Envelope("trace",null)`, do `Envelope(var trace, Open(...))`, `Envelope(...,Fund(...))`, and `Envelope(...,Close(...))` match?

**Answer:** No. The nested `Command` component is null, so it does not match any nested record pattern. An unguarded `Envelope` fallback catches it.

### Exercise 5 — Null Leaf Component

Given `new Envelope("trace",new Open(null))`, does `case Envelope(var trace,Open(var id))` match?

**Answer:** Yes; the `Open` record is non-null, and `var id` binds the null component. If a non-null ID is required, a separate guard is needed.

### Exercise 6 — `when true`

Can `case Run(var n) when true` be exhaustive on a sealed hierarchy containing only `Run`?

**Answer:** Yes, according to the Java 21 check in this lesson. However, you should write an unguarded case when there is no real condition so the code is easier to understand and avoids confusion.

### Exercise 7 — `non-sealed`

Is an `ExtensionChild` instance extending `Extension` caught by `case Extension e`?

**Answer:** Yes. A type pattern for `Extension` accepts subclasses too; the verification program in Section 8 printed `extension child => EXTENSION`.

### Exercise 8 — Null Enum

An enum switch expression already handles `NEW`/`RUNNING`/`DONE`. If `null` is passed, does it return `DONE` or a default?

**Answer:** Not automatically. In the example without a null branch, it throws `NullPointerException`; add a policy if `null` is an input that must be supported.

### Exercise 9 — Why Is a Dominated Error Different from Non-Exhaustive?

**Answer:** Dominance occurs when an earlier case already covers the values a later case is meant to handle, making the later case unreachable. Non-exhaustiveness occurs when there are still values in the selector's domain that are not covered. The two errors require different fixes.

### Exercise 10 — Code Has All Types Covered but Wrong Business Logic

`case Open`, `case Fund`, and `case Close` are all present; however, `Fund(-1)` enters the branch recording a successful payment. Does the compiler detect this?

**Answer:** No; in Java, `-1` is still a valid `int`. Add validation guards and test negative, zero, and positive values according to business policy.

## 16. Workflow for Using the Checklist in Real Projects

When opening a pull request that changes a sealed hierarchy, proceed step by step:

1. **Identify the type model change:** which subtypes were added/removed/changed, and are there `non-sealed` branches or nested hierarchies?
2. **Find all switch consumers:** in handlers, mapping, serialization, view layers, auditing, validation, and tests. Do not fix only the first switch that reports an error.
3. **Inspect each switch by selector type:** enum/sealed/generic/`Object`, statement or expression, with or without guards and nested records.
4. **Let the compiler do its work:** build with the right `--release`, without using `default` to dodge missing-case errors.
5. **Review fallbacks:** every subtype with guarded cases needs a branch receiving the remainder per policy; nested nulls need handling if they can occur.
6. **Review nulls:** do the root selector and nullable components have clear contracts?
7. **Add behavioral tests:** success, invalid, boundary, null, and event/state effects if any.
8. **Run clean CI:** recompile modules depending on the sealed/enum domain and run regression tests.
9. **Review intentional defaults:** `default` makes sense for open domains with a clear reason; avoid adding it automatically to closed domains.
10. **Check deployment compatibility:** services sharing protocols/domains may upgrade versions asynchronously; use contract tests and appropriate rollout strategies.

This checklist helps leverage a key advantage of Java 21: the compiler not only reads pattern syntax, but also assists in checking **the set of values that must be handled**. That does not replace business reviews, yet it significantly reduces the risk of forgetting a new subtype when sealed/enum structures are well managed.

## Conclusion

The **Exhaustiveness and Sealed Types Checklist** must go beyond asking “are there enough cases yet?” Start from the **selector type**, inspect the **`permits` hierarchy**, identify `final`/`sealed`/`non-sealed` branches, check **guards that can evaluate to false**, keep **same-subtype fallbacks** when needed, and then define policies for **null** and **nullable nested records**. Avoid unnecessary `default`s if the goal is for the compiler to catch new type changes, while distinguishing traditional switch statements from switch expressions and enhanced pattern switch statements.

The Java 21 program in this lesson shows three layers of verification working together: **javac** verifies syntax/types/dominance/exhaustiveness; **runtime tests** verify null, guards, and boundaries; and **reviews** decide the policy for each subtype. When these three layers are used in their proper roles, sealed hierarchies and pattern matching become tools that make code easy to extend while staying under control.

## Official References

- [JEP 409 — Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JLS Java SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 — Switch Expressions §15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JLS Java SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
