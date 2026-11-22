# Enum switch and fixed value sets: writing an exhaustive `switch`

> **Module:** Java Core Pattern Matching → Exhaustive switch. Focus: **exhaustiveness** when a `switch` receives a value of an `enum` — an enumerated type with a finite set of constants determined by its type declaration. The main examples use **Java 21**; the core principles of `switch expression` and `enum` also apply to many earlier JDKs. Code marked **ERROR** is an intentional example that does not compile.

## Learning Objectives

After this lesson, you can:

- Explain why the compiler knows **all enum constants** and can prove that a `switch expression` covers all of those values.
- Write a `switch` with `case NEW -> ...`, combine multiple constants in one `case`, and distinguish an **enum constant label** from a **type pattern**.
- Understand why a `switch expression` on an enum can **omit `default`** when every constant is listed, whereas a traditional `switch statement` can be valid even when branches are missing.
- Explain the role of `default`, `case null`, changes to the enum set over time, and the impact of recompilation.
- Design state handling clearly, avoiding missed new states or using `ordinal()` in place of business meaning.

## 1. An Enum Is a Finite Set of Constants by Declaration

In Java, an `enum` defines a type with **explicitly declared constant objects**. For example:

~~~java
enum OrderState {
    NEW,
    PROCESSING,
    DONE
}
~~~

In this version of the source code, the set of non-null enum values is:

~~~text
{ NEW, PROCESSING, DONE }
~~~

A variable declared as `OrderState state` can reference one of the three constants above, or hold `null` because an enum is a **reference type**.

~~~java
OrderState state = OrderState.PROCESSING;
boolean isDone = state == OrderState.DONE; // false
~~~

This is illustrative code placed inside an appropriate class/method; it is not a standalone program.

**Useful characteristics of enums in a switch:**

- The compiler reads the `OrderState` declaration and knows the **constant names** that can exist at compile time.
- Each constant is a singleton object of its enum within its class loader; comparing constants of the same enum with `==` is natural.
- You cannot write a class extending `OrderState` and arbitrarily create additional constants outside the enum declaration.
- A finite set of constants in one version **does not mean it is forever immutable across library versions**: developers can edit the enum declaration and add `CANCELLED` later.

It is this finite-value-set characteristic that allows Java to check **exhaustiveness** statically, rather than needing to know every individual runtime object.

## 2. `case` Syntax for Enums: Constant Labels, Not Pattern Variables

With a selector of type `OrderState`:

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

`case NEW`, `case PROCESSING`, and `case DONE` are **enum constant labels**. They compare the selector against the **specified enum constant**. They **do not declare a new variable**, unlike:

~~~java
case String text -> text.toUpperCase(); // Type pattern if the selector is compatible.
~~~

The type pattern `String text` creates the variable `text`; the constant label `case NEW` simply selects an already-named value.

### Combining Multiple Enum Constants

When multiple states share the same behavior:

~~~java
static String phase(OrderState state) {
    return switch (state) {
        case NEW, PROCESSING -> "open";
        case DONE -> "closed";
    };
}
~~~

A `case NEW, PROCESSING` label represents **two enum constants**. For coverage, the compiler counts both `NEW` and `PROCESSING`; combined with `DONE`, every constant of `OrderState` has appeared.

Using a comma in the same `case` label **is not fall-through**. With the `->` syntax, only the selected branch executes, and no `break` is needed. The older label-grouping syntax `case NEW: case PROCESSING:` also exists, but writing with `->` is clearer and reduces fall-through bugs.

### Constant Labels Must Belong to a Compatible Type

If the selector has type `OrderState`, you cannot use a constant from an incompatible enum or a nonexistent name:

~~~java
enum OrderState { NEW, PROCESSING, DONE }

// ERROR: No constant CANCELLED is declared in OrderState.
static String broken(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
        case CANCELLED -> "cancelled"; // ERROR.
    };
}
~~~

The compiler checks this **before the program runs**. Do not confuse enum labels with strings: `case "NEW"` cannot replace `case NEW` when the selector has an enum type.

## 3. What Does `Exhaustive switch` Mean?

A `switch` is considered **exhaustive** when its labels cover every value in the selector type's value set according to language rules, or when it has `default` as a fallback branch.

For `OrderState`:

| Enum constant | Handling label |
| --- | --- |
| `NEW` | `case NEW` |
| `PROCESSING` | `case PROCESSING` |
| `DONE` | `case DONE` |

Having all three ⇒ the set of enum labels **covers the entire enum**. If a constant is missing without `default`, a **switch expression** is rejected by the compiler.

A complete method-level example:

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

**It is valid without `default`.** The Java 21 compiler can prove that every non-null `OrderState` value matches a label. Oracle's documentation describes that the compiler provides an implicit default branch for an exhaustive enum switch expression. You do not have to guess at missed states yourself.

### Intentional Non-Compiling Example

~~~java
static String incomplete(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        // ERROR: DONE remains without a handling label.
    };
}
~~~

This is a **compile-time error**, not a runtime error thrown only when `DONE` is encountered. A `switch expression` must produce a value or throw an exception for every branch considered, so the compiler does not allow a valid enum value to fall out of the `switch` without a result.

**The best fix when business logic needs to distinguish each state:** add `case DONE -> "done";`. Sometimes adding `default` is an intentional choice, but it changes the compiler's ability to remind you when the enum is extended (see Section 6).

## 4. `switch expression` Differs from a Traditional `switch statement`

This is the most common source of misunderstanding when learning exhaustiveness.

### 4.1. A `Switch expression` Must Be Exhaustive

A `Switch expression` has the form:

~~~java
String description = switch (state) {
    case NEW -> "new";
    case PROCESSING -> "working";
    case DONE -> "finished";
};
~~~

It returns a value assigned to `description`, and **must have a way to produce a value or throw** in every case required by the compiler. A branch with a block uses `yield` to return a result:

~~~java
String description = switch (state) {
    case NEW -> "new";
    case PROCESSING -> {
        String message = "working";
        yield message;
    }
    case DONE -> "finished";
};
~~~

In this example, the set of enum labels is exhaustive, so `default` is not needed. Do not use `break "value"` to return a result: `yield` is the mechanism for a switch expression when a branch has a block.

### 4.2. A Basic `Switch statement` on an Enum Can Be **Non**-Exhaustive

A **valid** example even in Java 21:

~~~java
static void logOnlyNew(OrderState state) {
    switch (state) {
        case NEW -> System.out.println("new order");
    }
}
~~~

If `state == DONE` or `state == PROCESSING`, no label applies, and **a basic switch statement completes without doing anything**. There is no compile error just for omitting the two constants.

The reason is **compatibility with older Java**. According to JLS 21 `14.11`, a switch statement that uses only enum constant labels and has no pattern or null label is a **basic switch statement**; it is not required to be exhaustive like a switch expression.

**Practical consequence:** Do not assume the arrow syntax `->` automatically makes every switch statement exhaustive. The requirement does not come from the arrow, but from the **kind of switch** and the labels used.

### 4.3. An `Enhanced switch statement` in Java 21 Must Be Exhaustive

In Java 21, a switch statement becomes **enhanced** if it uses a case pattern or `case null`, or if the selector has a type not supported by a traditional switch. An enhanced switch statement **must be exhaustive**.

The following example **intentionally does not compile**:

~~~java
static void brokenNullAware(OrderState state) {
    switch (state) {
        case null -> System.out.println("missing");
        case NEW -> System.out.println("new");
        // ERROR: enhanced switch statement does not cover PROCESSING, DONE.
    }
}
~~~

Here, simply adding `case null` puts the switch statement into the enhanced category; omitting `PROCESSING` and `DONE` is no longer ignored as in a basic enum switch statement.

**Fix:** add the missing enum branches or add an appropriate `default`.

### Quick Comparison Table

| Situation in Java 21 | Exhaustive required? | If an enum constant is missing and there is no `default` |
| --- | --- | --- |
| `return switch (enumValue) { ... };` | **Yes** | Compile error |
| `switch (enumValue) { case NEW -> ...; }` with constant labels only | **Not required** | Compiles; unmatched values ⇒ do nothing |
| `switch (enumValue) { case null -> ...; case NEW -> ...; }` | **Yes** | Compile error |
| Switch statement with a pattern label | **Yes** | Must have appropriate type coverage/default |
| Enum switch expression with `default` | **Can be covered via default** | Valid, but new enums may fall into default |

**Conclusion:** When you want the compiler to enforce checking every enum state, prefer a **switch expression without `default`** and list all existing constants.

## 5. `null` Is a Separate Case, Not an Enum Constant

An enum variable is a reference, so:

~~~java
OrderState state = null; // Valid at the type level.
~~~

`null` is **not** `NEW`, `PROCESSING`, or `DONE`. Therefore, a switch expression that lists all three constants can still throw `NullPointerException` if the selector is `null` and there is no null-handling label.

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}

// label(null) -> NullPointerException in Java 21.
~~~

### Explicit Null Handling (Java 21+)

~~~java
static String safeLabel(OrderState state) {
    return switch (state) {
        case null -> "missing";
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

`case null` is officially supported in Java 21; it catches a null value before selecting an enum case. **No `default` is needed** because all constants are listed exhaustively and null is handled separately.

**Important:** `default` alone does not automatically catch null:

~~~java
static String misleading(OrderState state) {
    return switch (state) {
        case DONE -> "done";
        default -> "not done";
    };
}

// misleading(null) -> NullPointerException, does NOT return "not done".
~~~

If you want to combine null and the remaining cases intentionally, Java 21 allows `case null, default -> ...`. However, keeping `case null` separate is usually clearer when missing data is an error or a distinct business state.

### When Should You Reject Null?

If the enum is a required business parameter, you can validate it at the API boundary:

~~~java
static String requireState(OrderState state) {
    java.util.Objects.requireNonNull(state, "state");
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

Now `null` is rejected with a clear message right at the boundary, while the switch focuses on the valid enum set. Choose **handle null** or **reject null** according to the API contract; do not leave it to accidental default behavior.

## 6. What Happens When a New Enum Constant Is Added?

Initially:

~~~java
enum OrderState {
    NEW, PROCESSING, DONE
}
~~~

After a new requirement, the product adds:

~~~java
enum OrderState {
    NEW, PROCESSING, DONE, CANCELLED
}
~~~

There are three situations to distinguish.

### 6.1. Recompiling Code That Uses a Switch Expression **Without `default`**

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

When the compiler sees the enum declaration **now containing `CANCELLED`**, it reports `switch expression does not cover all possible input values` or an equivalent message. At that point, the missing branch is a **useful compile error**, forcing developers to answer the question: how should a cancelled state be handled?

Fix:

~~~java
case CANCELLED -> "cancelled";
~~~

The line above is an **illustrative label** that must be placed in a switch expression in the proper context.

### 6.2. With `default` Already Present: Code May Keep Compiling Without Warning

~~~java
static String labelWithDefault(OrderState state) {
    return switch (state) {
        case DONE -> "done";
        default -> "other";
    };
}
~~~

After the enum adds `CANCELLED`, the compiler still sees `default`, so the expression remains exhaustive. The new value goes to `"other"`. This may be the **desired behavior** when all unknown states share the same handling, but it is a risk if business logic requires a dedicated branch for the cancelled state.

**Practical rule:** If each enum state has its own distinct meaning, avoid a generic `default`; let the compiler report when the enum evolves. If a fallback is truly part of the business contract, use `default`, **test the new state**, and document the intent clearly.

### 6.3. Replacing the Compiled Enum **Without** Recompiling the Old Switch Code

This is the **binary evolution** problem: one module compiled a switch expression when the enum had only three constants, but at runtime it receives the enum from an updated library that has a new constant.

According to JLS Java 21, if a **switch expression** was considered exhaustive at compile time but encounters a value at runtime that **does not match any case label**, it throws **`MatchException`** (assuming no default branch catches the new value). If the selector is null without a null label, the corresponding semantics is `NullPointerException`.

Distinguish:

- **Recompiling together with the new enum source:** the compiler has the chance to report the missing `CANCELLED`.
- **Updating only the enum/library and running old bytecode:** the compiler is not re-run on the switch code; a runtime path with no matching label can occur and throw `MatchException` under Java 21 semantics.
- **A basic switch statement with a missing branch:** if no label matches, it can **skip execution** instead of producing a result, per JLS `14.11.3`.

Never assume an application is automatically safe against enum changes across independently deployed modules. When upgrading a library containing an enum, recompile dependent code and run tests covering all branches.

## 7. Enum Switch and Pattern Switch Coverage

### 7.1. The Set of Enum Constants Is One Way to Prove Exhaustiveness

With a selector of type `OrderState`, the three labels `case NEW`, `case PROCESSING`, `case DONE` are sufficient to cover the enum. This is **enum constant coverage**, no type pattern required.

### 7.2. A Pattern Switch on a Wider Selector Has a Different Problem

For example, a selector of type `Object` could hold `OrderState`, `String`, `Integer`, or any type:

~~~java
static String describeAny(Object input) {
    return switch (input) {
        case OrderState state -> "order state: " + state.name();
        case String text -> "text: " + text;
        default -> "other";
    };
}
~~~

Here `case OrderState state` is a **type pattern**. It checks whether the runtime object is of enum type `OrderState`, then binds `state`. It **does not** enumerate individual enum constants. `default` is required for `Object` types that do not match the two type patterns above (or an equivalent catch-all branch).

If you need to handle **each constant** after confirming `OrderState`, you can nest a switch expression on the `state` variable:

~~~java
static String describeAny(Object input) {
    return switch (input) {
        case OrderState state -> switch (state) {
            case NEW -> "new";
            case PROCESSING -> "processing";
            case DONE -> "done";
        };
        default -> "not an OrderState";
    };
}
~~~

This is an example of two-level checking:

- Outer switch: **reference type** of `Object`.
- Inner switch: **finite constant set** of the enum.

Do not confuse `case OrderState state` (type pattern) with `case NEW` (enum constant label).

### 7.3. An Enum Is Closed by Declaration, but External Data Contracts May Exist

If a state is received from HTTP/JSON/database as the string `"NEW"`, that is a **String**, not an `OrderState` yet. Convert the data into the enum at the system boundary using an appropriate API, validate invalid cases, and only then pass the enum into the switch.

~~~java
static OrderState parseState(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("state is required");
    }
    try {
        return OrderState.valueOf(raw);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException("Unknown state: " + raw, ex);
    }
}
~~~

`Enum.valueOf` requires the **exact constant name**, case-sensitive; an invalid string causes `IllegalArgumentException`. Do not use `ordinal()` to encode long-lived business states: inserting or reordering constants can change the ordinal of existing values.

The methods in Section 7 are **illustrative code** placed in a class containing the `OrderState` enum; they are not a standalone program. Section 9 provides a runnable example.

## 8. How to Design Maintainable Enum Switches

### 8.1. List Every Constant When Each State Needs Separate Handling

~~~java
static String action(OrderState state) {
    return switch (state) {
        case NEW -> "validate";
        case PROCESSING -> "monitor";
        case DONE -> "archive";
    };
}
~~~

This code forces the development team to handle new enum constants upon recompilation. **Do not add `default -> "unknown"` just to silence a compile-time error** when the business logic has not actually defined how to handle a new constant.

### 8.2. Group Branches When It Matches Business Meaning

~~~java
static boolean isOpen(OrderState state) {
    return switch (state) {
        case NEW, PROCESSING -> true;
        case DONE -> false;
    };
}
~~~

`NEW` and `PROCESSING` are grouped because both represent an open state, not merely to shorten the code. If `CANCELLED` is added later, the compiler will require deciding whether `CANCELLED` is open or closed.

### 8.3. When a Branch Is Truly an Error Condition, Use `throw`

~~~java
static int progressPercent(OrderState state) {
    return switch (state) {
        case NEW -> 0;
        case PROCESSING -> 50;
        case DONE -> 100;
    };
}
~~~

If in another variant a state is forbidden at the call site, a specific branch can `throw new IllegalStateException("...")` instead of producing a value. A branch completing abruptly via `throw` is still valid handling in a switch expression; just ensure **every constant is covered**.

### 8.4. Do Not Force a Switch for Every Enum

If many states share a stable property, consider putting the behavior directly on the enum or using a mapping structure with its own coverage check. A `switch expression` is especially suitable when what you want is for **the compiler to enforce a decision for each state**, visible right at the call site.

### 8.5. Tests Do Not Replace Exhaustiveness Checks

Testing over `OrderState.values()` is useful:

~~~java
for (OrderState state : OrderState.values()) {
    System.out.println(state + " => " + action(state));
}
~~~

`values()` returns an array of the declared constants at runtime. A test like this can catch logic bugs within each branch, but **the compiler** is what detects a missing branch in a switch expression as soon as the code is compiled against a new enum. Both are needed for critical systems.

## 9. Complete Runnable Java 21 Program

Save the file **`EnumExhaustiveDemo.java`**:

~~~java
public class EnumExhaustiveDemo {

    enum OrderState {
        NEW, PROCESSING, DONE
    }

    // Exhaustive enum switch expression: no default needed.
    static String describe(OrderState state) {
        return switch (state) {
            case NEW -> "new";
            case PROCESSING -> "processing";
            case DONE -> "done";
        };
    }

    // Group constants with the same meaning.
    static String phase(OrderState state) {
        return switch (state) {
            case NEW, PROCESSING -> "open";
            case DONE -> "closed";
        };
    }

    // With default: states other than DONE use a shared result.
    static String fallback(OrderState state) {
        return switch (state) {
            case DONE -> "done";
            default -> "not done";
        };
    }

    // Java 21: explicit null handling.
    static String nullSafe(OrderState state) {
        return switch (state) {
            case null -> "missing";
            case NEW -> "new";
            case PROCESSING, DONE -> "existing";
        };
    }

    // Basic switch statement: not required to be exhaustive.
    static void statement(OrderState state) {
        switch (state) {
            case NEW -> System.out.println("statement: NEW");
        }
    }

    public static void main(String[] args) {
        for (OrderState state : OrderState.values()) {
            System.out.println(
                    state + " => " + describe(state) + ", " + phase(state)
            );
        }

        System.out.println("fallback=" + fallback(OrderState.PROCESSING));
        System.out.println("null=" + nullSafe(null));

        statement(OrderState.DONE);
        System.out.println("statement: after DONE");
        statement(OrderState.NEW);

        try {
            describe(null);
        } catch (NullPointerException ex) {
            System.out.println("without null: NPE");
        }
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac --release 21 EnumExhaustiveDemo.java
java EnumExhaustiveDemo
~~~

**Exact stdout:**

~~~text
NEW => new, open
PROCESSING => processing, open
DONE => done, closed
fallback=not done
null=missing
statement: after DONE
statement: NEW
without null: NPE
~~~

**Output explanation:**

1. The `OrderState.values()` loop iterates through the three constants in declaration order; each constant is handled by the exhaustive `describe` and `phase` switch expressions.
2. `fallback(PROCESSING)` returns `not done` because only `DONE` has its own branch; `default` receives `PROCESSING`.
3. `nullSafe(null)` returns `missing` because it has `case null`.
4. `statement(DONE)` **prints nothing** because the basic switch statement has no `DONE` label. Therefore, right after the first lines, only `statement: after DONE` appears.
5. `statement(NEW)` prints `statement: NEW`.
6. `describe(null)` throws `NullPointerException`, which is caught in the demo and turned into the line `without null: NPE`. Even though `describe` has all three enum cases, it does not automatically handle null.

### Three Intentionally Broken Snippets to Test the Compiler

**Missing enum constant in a switch expression**:

~~~java
static String incomplete(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        // ERROR: missing DONE and no default.
    };
}
~~~

**Missing label in an enhanced switch statement with `case null`**:

~~~java
static void incompleteEnhanced(OrderState state) {
    switch (state) {
        case null -> System.out.println("null");
        case NEW -> System.out.println("new");
        // ERROR: PROCESSING and DONE remain.
    }
}
~~~

**Duplicate enum constant in a switch**:

~~~java
static String duplicate(OrderState state) {
    return switch (state) {
        case NEW -> "a";
        case NEW -> "b"; // ERROR: duplicate case label.
        case PROCESSING -> "c";
        case DONE -> "d";
    };
}
~~~

These three methods are only meant to demonstrate **compile errors** in a class with the `OrderState` enum; do not copy them into the demo class if you want to keep a runnable version.

## 10. Common Mistakes and Fixes

| Misconception/error | What is true in Java 21 | How to fix |
| --- | --- | --- |
| “An enum switch is always exhaustive.” | Only certain forms require it; a basic switch statement can omit branches | Use a switch expression for compiler checking or list branches yourself |
| “A switch expression must have default to be valid.” | For an enum, covering all constants requires **no default** | List every constant |
| “Default catches null.” | `null` does not automatically enter `default` | Use `case null` or validate at the API boundary |
| “Having default is safer against new enums.” | Default can **hide** the addition of a state that needs dedicated handling | Omit default if you want the compiler to report new constants |
| “Combining `case NEW, PROCESSING` skips one branch.” | Grouping still counts both constants | Group only when the business logic is identical |
| “All enum labels are type patterns.” | `case NEW` is a constant label; `case OrderState state` is a type pattern | Distinguish constant labels from bound variables |
| “Use `case "NEW"` for an OrderState selector.” | Strings are a different type from the enum | Use `case NEW` |
| “With `case null`, a switch statement can still omit enum constants.” | `case null` makes it enhanced and requires exhaustiveness | Add all missing constants or default |
| “The compiler will automatically warn when an enum library changes at runtime.” | Without recompilation, no new compile-time diagnostics can occur | Recompile dependent modules and run tests |
| “`ordinal()` is a stable state code.” | Constant order can change when editing the enum | Store an explicit business code or constant name per contract |
| “No matching case always throws an error.” | A basic statement can complete normally; an expression has a runtime exception path when a label is missing | Understand which kind of switch you are using |

## 11. Pre-Merge Review Checklist for Enum Switches

1. **Identify the selector type:** is it actually `OrderState` or `Object/String`? Do not apply enum constant coverage reasoning to an overly broad selector.
2. **List the declared constants:** `NEW`, `PROCESSING`, `DONE`. Note whether null can appear per the API contract.
3. **Identify the switch kind:** expression, basic statement, or enhanced statement? From that, determine whether exhaustiveness is required.
4. **Match the labels:** does every constant appear in a `case` (including grouped cases)? Are there any repeated/duplicate labels?
5. **Evaluate `default`:** is a fallback genuinely desired, or does it mask the need to handle new constants?
6. **Specify null behavior:** use `case null` in Java 21 or validate input at the boundary. Do not rely on default.
7. **Check enum/library changes:** have clients been recompiled and tested after adding new constants?
8. **Test the outcomes:** test every state via `values()`, test null if the API permits it, and test behavior on invalid source data.

## 12. Self-Check Exercises

**Question 1.** Given `enum Color { RED, GREEN, BLUE }`, does the switch expression below compile? Why?

~~~java
return switch (color) {
    case RED -> "R";
    case GREEN -> "G";
};
~~~

**Question 2.** With the same `Color` enum, does a **switch statement** containing only `case RED -> println("red");` compile? If `color == BLUE`, what happens?

**Question 3.** What label needs to be added so that the switch expression in Question 1 is exhaustive **without default**?

**Question 4.** If a `YELLOW` constant is added and you recompile a switch expression that previously listed all three constants without `default`, what happens?

**Question 5.** What if that switch expression had `default -> "other"` from the start when `YELLOW` is added? Pros and cons?

**Question 6.** Does `case RED, GREEN -> "warm"` count as covering both constants? Is it a type pattern?

**Question 7.** An enum switch expression covers all cases, but `null` is passed. What value does it return if there is no `case null`?

**Question 8.** A switch statement has `case null`, handles only `RED`, has no `default`, and omits `GREEN`, `BLUE`. Is it still a basic switch statement? What does the compiler say?

**Question 9.** Distinguish `case Color c -> ...` and `case RED -> ...` in terms of selector type and variable binding.

**Question 10.** Why can an enum switch expression that was exhaustive at compile time encounter `MatchException` after updating only the library containing the enum without recompiling the switch code?

**Question 11.** When an enum adds the `CANCELLED` constant, why is storing state using `ordinal()` or assuming ordinals never change dangerous?

**Question 12.** With the business rule “`NEW` and `PROCESSING` are open; `DONE` is closed”, write a switch expression returning `boolean` without default and suggest a test for each constant.

### Suggested Answers

1. **No.** `BLUE` is missing, and a switch expression must be exhaustive.
2. **Yes.** A basic switch statement on an enum is not required to be exhaustive; for `BLUE`, it finishes without printing any line.
3. Add `case BLUE -> "B";`.
4. The compiler sees the added `YELLOW` and reports that the switch expression is not exhaustive, forcing the branch to be updated.
5. It still compiles, and `YELLOW` goes to `default`. Helpful if a fallback is genuinely wanted, but it removes the warning that forces handling the new state.
6. **Yes**, it covers `RED` and `GREEN`; this is an **enum constant label list**, not a type pattern.
7. **Throws `NullPointerException`** in Java 21 if there is no appropriate null handling.
8. No. `case null` makes the statement **enhanced**, so the compiler requires exhaustiveness; missing `GREEN` and `BLUE` causes an error.
9. `case Color c` is a **type pattern**, typically used when the selector has a broader type like `Object`, creating variable `c`; `case RED` matches an enum constant when the selector has a compatible enum type, without binding a variable.
10. The switch bytecode was compiled against the old constant set; a new constant with no label at runtime leaves the switch expression unable to select a branch and can throw `MatchException` per JLS 21. The client must be recompiled.
11. `ordinal()` reflects the constant's position in the declaration; inserting or reordering constants can change the numbers of other constants. Use the name or a business code with a clear contract.
12. For example, `return switch(state) { case NEW, PROCESSING -> true; case DONE -> false; };`. Test all three values or loop over `Color.values()`/`OrderState.values()` corresponding to the enum used.

## Official References

- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): enum sets, exhaustiveness of switch expressions, switch statements, and grouping cases.
- [Java Language Specification 21 — `14.11.1.1 Exhaustive Switch Blocks`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): enum coverage rules; when every enum constant is listed, no default is needed.
- [Java Language Specification 21 — `14.11.2 The Switch Block of a switch Statement`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2): distinguishing enhanced/basic switch statements and exhaustiveness requirements.
- [Java Language Specification 21 — `14.11.3 Execution of a switch Statement`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): if no label matches, a basic statement can complete normally.
- [Java Language Specification 21 — `15.28 Switch Expressions`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): branch selection; `MatchException` or `NullPointerException` when no label applies.
- [Java Language Specification 21 — `8.9 Enum Classes`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9): the enum model and the set of enum constants.
