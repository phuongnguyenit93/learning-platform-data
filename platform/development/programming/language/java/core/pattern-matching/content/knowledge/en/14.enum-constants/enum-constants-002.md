# Qualified Enum Constants in Java 21

## 1. Concept and Goals

In Java, an `enum` type defines a finite set of values, where each value is an **enum constant**. For example:

```java
enum Phase {
    NEW, RUNNING, DONE
}
```

The values have full names `Phase.NEW`, `Phase.RUNNING`, `Phase.DONE`. When writing both the **enum type name** and the **constant name**, it is called a **qualified enum constant**:

```java
Phase.NEW
```

In a `case` label:

```java
case Phase.NEW -> "new";
```

this label selects the exact `NEW` constant of the `Phase` enum, not any string or object with a similar name.

**Notable new feature in Java 21:** pattern matching for `switch` (JEP 441) allows using **qualified enum constants** in case labels, even when the static type of the selector expression is not that enum itself, as long as the enum constant has a type compatible with the selector. This allows a switch on `Object` or an interface to accept constants belonging to different enums.

This lesson focuses on syntax, why a qualifier is needed, valid/invalid cases, how to combine with type patterns, case ordering, exhaustiveness, `null`, and runnable Java 21 examples.

**Version:** uses **JDK 21+** with standard Java 21 syntax, without preview features. Java 17 and earlier versions have different rules for enum labels in traditional switch statements; this distinction should be kept in mind when maintaining code.

## 2. Qualified and Unqualified: Two Ways to Write an Enum Constant

Given the `Phase` enum:

- `NEW` is an **unqualified enum constant name** — only the constant name.
- `Phase.NEW` is a **qualified enum constant name** — the type name accompanied by the constant name.

When the selector has type `Phase`, a classic switch is usually written as:

```java
static String phaseName(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
    };
}
```

This snippet is placed inside a class containing the `Phase` declaration; the `case NEW` syntax has been valid since Java versions prior to Java 21. Because the selector already has static type `Phase`, the compiler knows which enum the constant `NEW` belongs to.

Starting in **Java 21**, we can explicitly write the enum name in the same scenario:

```java
static String phaseName21(Phase phase) {
    return switch (phase) {
        case Phase.NEW -> "new";
        case Phase.RUNNING -> "running";
        case Phase.DONE -> "done";
    };
}
```

Both approaches return the same result for `Phase` values. Java 21 accepts the qualified form in a switch on an enum, and also supports it with wider selector types.

**Important compatibility note:** in Java 17, `case Phase.NEW` in a switch with a `Phase` selector is rejected by the compiler with a message requiring the *unqualified name* of the enum constant. If you must compile with Java 17, use `case NEW` in a traditional switch on that enum itself. Do not confuse stable Java 21 syntax with syntax supported across all versions.

## 3. Why Is a Qualified Constant Needed When the Selector Is Object?

Consider passing data through an API that accepts `Object`:

```java
Object event = Phase.NEW;
```

If you write `switch (event)` in Java 21, the compiler only knows the static type of the selector is `Object`; it does not have a single enum from which to infer which type `NEW` belongs to.

The correct way to write this for an enum constant is:

```java
static String inspect(Object event) {
    return switch (event) {
        case Phase.NEW -> "new phase";
        case Phase.DONE -> "finished phase";
        case Phase phase -> "another phase: " + phase;
        default -> "not a Phase";
    };
}
```

Meaning:

1. `case Phase.NEW`: matches only the exact constant object `Phase.NEW`.
2. `case Phase.DONE`: matches only the constant `Phase.DONE`.
3. `case Phase phase`: this is a **type pattern**, matching the remaining `Phase` values and declaring a variable `phase` of static type `Phase`.
4. `default`: handles objects that do not match the preceding three branches, except for `null` rules which must be considered separately.

With `inspect(Phase.RUNNING)`, the result is `"another phase: RUNNING"`. With `inspect("NEW")`, the result is `"not a Phase"` — the string `"NEW"` is not automatically converted to `Phase.NEW`.

Key point to understand: **a qualified enum constant does not check for a "matching name"**, but checks for a specific enum value. Each enum constant is a unique object of its respective enum. Two enums that both have a constant named `NEW` still own two different objects.

## 4. Two Enums with the Same Constant Name: Where Java 21 Clearly Shows Its Benefit

Let us model two independent workflows:

```java
sealed interface TaskState permits Download, Upload {}

enum Download implements TaskState {
    NEW, RUNNING, DONE
}

enum Upload implements TaskState {
    NEW, RUNNING, FAILED
}
```

Here, `Download.NEW` and `Upload.NEW` both have the name `NEW` but belong to **two separate enums**. Similarly, `Download.RUNNING` and `Upload.RUNNING` are two distinct values. Thanks to qualified enum constants, a switch on the `TaskState` interface can distinguish them accurately:

```java
static String stateName(TaskState value) {
    return switch (value) {
        case Download.NEW -> "download created";
        case Upload.NEW -> "upload created";
        case Download.RUNNING, Upload.RUNNING -> "running";
        case Download.DONE -> "download complete";
        case Upload.FAILED -> "upload failed";
        case null -> "missing";
    };
}
```

This snippet is inside a class with the enum/interface declarations above. The labels `case Download.NEW` and `case Upload.NEW` are completely separate. A branch consisting of **two constants** separated by a comma:

```java
case Download.RUNNING, Upload.RUNNING -> "running";
```

allows multiple enum values to lead to the same result, even if the two values belong to different enums, as long as the labels are valid for the selector type. Unlike type patterns, these enum constant labels do **not** create a binding variable.

This is one of the practical benefits of Java 21: writing a switch directly on a common interface, without having to convert enums to strings and compare constant names.

## 5. The Static Type of the Selector Determines Validity

A qualified enum constant in a case must still satisfy Java's type checking. It cannot be placed arbitrarily in any switch.

| Static type of selector | Case label | Java 21 conclusion |
| --- | --- | --- |
| `Phase` | `case NEW` | Valid, unqualified enum constant in a switch on the enum itself |
| `Phase` | `case Phase.NEW` | Valid, qualified enum constant |
| `Object` | `case Phase.NEW` | Valid, the selector can hold a `Phase` value |
| `TaskState` | `case Download.NEW` | Valid, `Download` implements `TaskState` |
| `TaskState` | `case Upload.FAILED` | Valid, `Upload` implements `TaskState` |
| `String` | `case Phase.NEW` | Invalid: type `Phase` is incompatible with selector `String` |
| `Download` | `case Upload.NEW` | Invalid: an `Upload` constant cannot be a `Download` value |

The clearest type error case:

```java
// Does not compile: switch on String, but the case is an enum constant.
// static String wrong(String text) {
//     return switch (text) {
//         case Phase.NEW -> "new";
//         default -> "other";
//     };
// }
```

This is a **compile-time error**, not a valid branch that simply never gets called at runtime. A `String` selector cannot hold a `Phase` constant. If the application input is the text `"NEW"`, handle it as a `String` or perform a checked conversion to the enum before switching.

When the selector has type `Object` or a common interface, the qualifier tells the compiler which enum to match against; however, type compatibility is still checked.

## 6. Complete Java 21 Example: Enum Constants from Two Workflows

Save the following code as **QualifiedEnumConstant21Demo.java**:

```java
public class QualifiedEnumConstant21Demo {
    sealed interface TaskState permits Download, Upload {}

    enum Download implements TaskState {
        NEW, RUNNING, DONE
    }

    enum Upload implements TaskState {
        NEW, RUNNING, FAILED
    }

    static String task(TaskState value) {
        return switch (value) {
            case null -> "missing";
            case Download.NEW -> "download:new";
            case Upload.NEW -> "upload:new";
            case Download.RUNNING, Upload.RUNNING -> "running";
            case Download.DONE -> "download:done";
            case Upload.FAILED -> "upload:failed";
        };
    }

    static String generic(Object value) {
        return switch (value) {
            case null -> "null";
            case Download.NEW -> "start-download";
            case Upload.NEW -> "start-upload";
            case Download d -> "download:" + d.name();
            case Upload u -> "upload:" + u.name();
            default -> "other";
        };
    }

    static String onlyDownload(Download value) {
        return switch (value) {
            case Download.NEW -> "new";
            case RUNNING -> "running";
            case DONE -> "done";
        };
    }

    public static void main(String[] args) {
        System.out.println(task(Download.NEW));
        System.out.println(task(Upload.NEW));
        System.out.println(task(Download.RUNNING));
        System.out.println(task(Upload.RUNNING));
        System.out.println(task(Download.DONE));
        System.out.println(task(Upload.FAILED));
        System.out.println(task(null));

        System.out.println(generic(Download.NEW));
        System.out.println(generic(Upload.NEW));
        System.out.println(generic(Upload.FAILED));
        System.out.println(generic("NEW"));
        System.out.println(generic(null));

        System.out.println(onlyDownload(Download.DONE));
    }
}
```

Compile and run:

```bash
javac QualifiedEnumConstant21Demo.java
java QualifiedEnumConstant21Demo
```

**Exact output:**

```text
download:new
upload:new
running
running
download:done
upload:failed
missing
start-download
start-upload
upload:FAILED
other
null
done
```

### Program Explanation

- `TaskState` is a **sealed interface**. Only the two enums `Download` and `Upload` are permitted to directly implement this interface.
- `task(TaskState value)` uses qualified enum constants to list **all six constants** belonging to the two enums. The `case null` branch handles absent data. The switch expression **does not need `default`** because the Java 21 compiler determines that the enum cases in this hierarchy are already covered.
- `case Download.RUNNING, Upload.RUNNING` demonstrates that two enum constants from different enums can share a single branch.
- `generic(Object value)` accepts the wide type `Object`. The two `NEW` constants are checked specifically before the type patterns `Download d` and `Upload u` handle the remaining constants.
- `generic(Upload.FAILED)` enters `case Upload u`, so it returns `"upload:FAILED"` via the `name()` method; it is not the string returned by the `task` branch.
- `generic("NEW")` returns `"other"` because `String` is not an enum. `generic(null)` returns `"null"` thanks to `case null`.
- `onlyDownload(Download value)` demonstrates that Java 21 allows **mixing qualified and unqualified labels** when the selector is already the `Download` enum.
- Both enums have the name `NEW`, but they are never confused, because each qualified label explicitly specifies the enum class that owns the constant.

When writing real programs, the `sealed interface` and enum declarations can be top-level types (placed in separate files or appropriate packages); they are nested inside the class in this example only to provide a single self-contained runnable file.

## 7. Exhaustiveness: Listing Enum Constants to Cover Possible Values

**Exhaustiveness** means the compiler proves that the switch has a branch for every valid value of the selector according to language rules.

### Switch on a single enum

```java
static String name(Download value) {
    return switch (value) {
        case Download.NEW -> "N";
        case Download.RUNNING -> "R";
        case Download.DONE -> "D";
    };
}
```

Because `Download` is declared with three constants `NEW`, `RUNNING`, `DONE` and all three have labels, the switch expression is exhaustive (for non-`null` values) and does not require `default`.

### Switch on a sealed interface implemented by enums

In the main program, `TaskState` only permits two enums to implement it, and the two enums have six constants in total. The Java 21 compiler can inspect the **set of constants of the permitted enums** to determine exhaustiveness in the example:

```java
return switch (value) {
    case null -> "missing";
    case Download.NEW -> "download:new";
    case Upload.NEW -> "upload:new";
    case Download.RUNNING, Upload.RUNNING -> "running";
    case Download.DONE -> "download:done";
    case Upload.FAILED -> "upload:failed";
};
```

It compiles without `default`. If `case Upload.FAILED` is removed and no other branch covers this value, the switch expression will fail exhaustiveness for that selector type.

### Wide selectors like Object

If a `switch` accepts `Object`, you cannot just list the constants of two enums and consider every object handled. Besides those two enums, there are `String`, `Integer`, other classes, etc. Therefore, in `generic(Object value)`, the `default` branch is used to cover values other than those two enums.

**Note on type changes:** if you add a new enum constant or modify the sealed hierarchy, recompile the switch so the compiler checks exhaustiveness. Avoid mechanically adding `default` if you want the compiler to force updates when the state model changes.

## 8. Dominance and Duplicate Labels: Place Specific Constants Before Type Patterns

A qualified enum constant is a **specific** value. A type pattern like `case Download d` covers **every non-null Download constant**. Therefore, case order matters.

The following snippet is **wrong**:

```java
// Does not compile: Download.NEW is dominated by the preceding type pattern.
// static String wrong(Object value) {
//     return switch (value) {
//         case Download d -> "any Download";
//         case Download.NEW -> "just new"; // Dominated
//         default -> "other";
//     };
// }
```

The preceding `case Download d` branch would also accept `Download.NEW`, making the later case unreachable. The Java 21 compiler detects **dominance** and rejects the shadowed label.

Fix it by changing the order:

```java
static String right(Object value) {
    return switch (value) {
        case Download.NEW -> "specific new";
        case Download d -> "another Download";
        default -> "other";
    };
}
```

Similarly, if you write both `case NEW` and `case Download.NEW` in the same switch with a selector of type `Download` as two separate labels, both labels refer to **the exact same constant**. The compiler reports a **duplicate case label**. Adding a qualifier does not create a new constant.

Distinguish between these issues:

| Issue | Example | Reason |
| --- | --- | --- |
| Duplicate label | `case NEW` and `case Download.NEW` in the same switch on `Download` | Both represent the constant `Download.NEW` |
| Dominance | `case Download d` before `case Download.NEW` | The type pattern already covers the specific constant |
| Non-exhaustive | Only `case Download.NEW` when selector is `Object` | Other types/values are not handled |
| Type incompatibility | `case Download.NEW` with selector of type `String` | An enum constant cannot be a `String` |
| `null` error | Missing `case null` when selector receives `null` | Switching on a reference can throw `NullPointerException` |

With multiple `case` labels, place branches handling specific constants before general type patterns and avoid redeclaring the same constant.

## 9. Qualified Enum Constants vs. Patterns and `when` Guards

Compare the three forms:

```java
// An exact constant:
case Download.NEW -> "new";

// Any constant of Download, while also declaring a pattern variable:
case Download d -> "download:" + d.name();

// Only some Download values satisfying an additional condition:
case Download d when d == Download.RUNNING -> "downloading";
```

- `case Download.NEW` is a **constant label**; it does not declare a pattern variable.
- `case Download d` is a **type pattern** and creates the variable `d` of type `Download` upon matching.
- `case Download d when ...` is a **guarded pattern label**: after the type pattern matches, the boolean guard is evaluated.

Do not write directly:

```java
// Invalid guard syntax for an enum constant in Java 21:
// case Download.NEW when enabled -> "start now";
```

If you want to handle the `Download.NEW` constant only when a dynamic condition is true, you can use a type pattern with a guard, then fall back to the constant label:

```java
static String start(Object value, boolean enabled) {
    return switch (value) {
        case Download d when d == Download.NEW && enabled ->
                "start enabled";
        case Download.NEW -> "start disabled";
        case Download d -> "other download";
        default -> "other";
    };
}
```

This snippet is placed in a class with the `Download` declaration. The guard does not create a different enum constant and does not re-check the selector from scratch. With `Download.NEW` and `enabled == true`, the guarded branch is selected; when false, the subsequent `case Download.NEW` branch is selected.

If the condition only revolves around a specific constant and does not need a pattern, you can use `case Download.NEW -> enabled ? "start enabled" : "start disabled";` to keep the label simple.

## 10. Handling null: An Enum Constant Cannot Be null

An enum constant is a constant object, so there is no `Download.null` enum constant. When the selector has a reference type, the `null` value is a separate case:

```java
static String optional(Object value) {
    return switch (value) {
        case null -> "missing";
        case Download.NEW -> "new";
        default -> "other";
    };
}
```

In Java 21, `case null` handles a null selector. Without this branch, `default` does not automatically catch null; switching on a reference may throw `NullPointerException` before executing any other branch.

Java 21 also allows the special combination `case null, default -> ...` when you want to handle null and all remaining values together; however, when null has a distinct business meaning, a separate `case null` label makes the code clearer.

A switch expression can be **exhaustive by type** and still throw `NullPointerException` when the selector is null. For example, `onlyDownload(null)` in the main program has no `case null` and will throw an NPE. That is expected behavior to understand, not a sign that an enum constant is missing.

## 11. When to Switch on One Enum vs. Multiple Enums in One Switch?

Prefer the simplest approach that fits the data type.

**Only one enum:** If the method accepts `Download`, switch directly on `Download` and list the constants. You can use qualified names for consistency with Java 21, though unqualified `case NEW` remains readable and compatible with older versions.

**Multiple enums in the same role:** If the business logic has two different enums that implement a common interface, Java 21 allows switching on the interface and using `Download.NEW`, `Upload.NEW` to handle each value accurately. This is the case where qualified constants most clearly demonstrate their value.

**Object-typed input:** When genuinely handling heterogeneous data, switch on `Object` and use enum-qualified case labels, type patterns, and `default` appropriately. However, if the API actually only allows `TaskState`, declare the parameter as `TaskState` instead of `Object` to gain compile-time checking.

**Input from strings, JSON, or files:** Parse/validate into an enum first, then switch. Do not use `case Download.NEW` to "automatically parse" a string `"NEW"`.

String conversion example:

```java
static Download parseDownload(String text) {
    return Download.valueOf(text);
}
```

`valueOf` only accepts the exact constant name of the enum, case-sensitively. For an invalid string, the method throws `IllegalArgumentException`; for `null`, it throws `NullPointerException`. An API receiving external data must define how to handle these errors or return a controlled error result.

For systems with multiple state categories, consider preserving clear semantics in the type system — `sealed interface TaskState` with two enums — rather than converting all states into strings and comparing them manually.

## 12. Common Mistakes and How to Fix Them

| Misconception or incorrect code | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `case Download.NEW` and compiling with Java 17. | Java 21's qualified enum case rules do not exist in stable Java 17. | Use JDK 21+, or `case NEW` with a `Download` selector on Java 17. |
| Writing `case NEW` in a switch on `Object` and expecting the compiler to pick the right enum. | `Object` does not specify which enum has the `NEW` constant. | Explicitly write `case Download.NEW` or `case Upload.NEW`. |
| Assuming two enums' `NEW` constants are the same value. | `Download.NEW` and `Upload.NEW` belong to two different enums. | Keep the qualifier and distinguish handling paths by enum type. |
| Confusing `case Download.NEW` with `case Download d`. | One is a specific constant; the other matches the entire type and declares a variable. | Choose the label based on the scope of values to handle. |
| Placing `case Download d` before `case Download.NEW`. | The type pattern covers the specific constant, causing dominance. | Place specialized constants before general type patterns. |
| Having both `case NEW` and `case Download.NEW` for one constant in the same switch. | Duplicate case label. | Keep only one label for that constant. |
| Placing `case Download.NEW` in a switch on `String`. | The selector type and enum constant are incompatible. | Convert the input to the proper enum type or switch on String. |
| Thinking every switch with enum constants is exhaustive. | Constants may be missing or the selector may have a wider type. | Consider the entire value set according to the selector's static type and add appropriate branches. |
| Writing `case Download.NEW when enabled`. | `when` is used with guarded patterns, not attached directly to constant labels like this. | Use `case Download d when d == Download.NEW && enabled` or a condition inside the case body. |
| Thinking `default` replaces `case null`. | Java 21's reference switch rules handle null separately. | Include `case null` when you want to accept null. |
| Comparing `"NEW"` with an enum constant in a switch. | A string is not an enum constant. | Parse/validate with `valueOf` or an appropriate API. |

## 13. Self-Practice Exercises and Answers

### Exercise 1 — Predict the Selected Branch

Given the `Download`, `Upload`, and `TaskState` declarations from the main program:

```java
TaskState a = Download.NEW;
TaskState b = Upload.NEW;
TaskState c = Upload.FAILED;
```

If we call `task(a)`, `task(b)`, and `task(c)`, what are the respective results?

**Answer:** `"download:new"`, `"upload:new"`, `"upload:failed"`. Just because they share the name `NEW` does not mean a single unqualified label can be used when the selector is `TaskState`.

### Exercise 2 — Identify the Compile-Time Error

Given:

```java
static String bad(Object value) {
    return switch (value) {
        case Download d -> "any download";
        case Download.NEW -> "just new";
        default -> "other";
    };
}
```

**Answer:** the `case Download.NEW` branch is **dominated** because every `Download` constant is already handled by the `case Download d` branch. Move `Download.NEW` before it if a specialized result is needed.

### Exercise 3 — Check Exhaustiveness

Suppose `TaskState` only permits the two enums `Download { NEW, RUNNING, DONE }` and `Upload { NEW, RUNNING, FAILED }`. The switch expression only lists:

```java
return switch (state) {
    case Download.NEW -> "download-new";
    case Download.RUNNING -> "download-running";
    case Download.DONE -> "download-done";
    case Upload.NEW -> "upload-new";
    case Upload.RUNNING -> "upload-running";
};
```

**Answer:** `Upload.FAILED` is missing. With a `TaskState` selector in this model, the compiler will not accept a non-exhaustive switch expression. Add `case Upload.FAILED -> "upload-failed";` or another branch that genuinely covers that case.

### Exercise 4 — Combine Constants with the Same State

Write a single `case` branch that handles `Download.RUNNING` and `Upload.RUNNING` and returns `"active"` for both.

**Answer:**

```java
case Download.RUNNING, Upload.RUNNING -> "active";
```

Both constants must be compatible with the switch selector's type; for example, a `TaskState` or `Object` selector is appropriate.

### Exercise 5 — Choose the Right Java Version

In Java 17, when switching on a `Download value` variable, do you use `case NEW` or `case Download.NEW`?

**Answer:** use `case NEW` (unqualified) in a traditional enum switch. In Java 21, both forms can be used with a `Download` selector. When the selector is `TaskState` or `Object` in Java 21, the qualified name clearly identifies which enum to check.

### Exercise 6 — Null and Strings

Why does `generic(null)` return `"null"` while `generic("NEW")` returns `"other"`?

**Answer:** `generic(null)` has a `case null` branch; the string `"NEW"` is neither `Download.NEW` nor `Upload.NEW` and does not match the type patterns of either enum, so it falls through to `default`.

## 14. Key Takeaways

A **qualified enum constant** is a constant name with its full enum type, such as `Download.NEW` or `Upload.NEW`. Java 21 allows using this form in pattern switch case labels to select the exact enum constant, even when the selector's static type is an interface or `Object`.

Points to remember:

1. **Java 21 expands enum case syntax:** with a selector already having an enum type, both `case NEW` and `case Download.NEW` are valid; Java 17 requires the unqualified form in classic enum switches.
2. **Qualifiers distinguish identity:** `Download.NEW` is not `Upload.NEW`, and it is not the string `"NEW"`.
3. **Constants differ from patterns:** `case Download.NEW` matches only one constant; `case Download d` matches any non-null `Download` constant and creates the variable `d`.
4. **Both order and type matter:** specialized constants should precede general patterns; enum constants must be compatible with the selector type.
5. **Do not forget exhaustiveness and null:** switch expressions must be exhaustive; `case null` handles absent values when needed, and `default` does not automatically replace null.

### Official Documentation

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — switch statement (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — switch expression (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
