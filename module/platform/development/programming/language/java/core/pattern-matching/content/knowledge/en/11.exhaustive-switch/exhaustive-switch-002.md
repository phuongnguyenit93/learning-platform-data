# Exhaustiveness in Java switch expressions

## 1. What is exhaustiveness and why does it matter?

**Exhaustiveness** means that a **switch** block has enough **case** labels to handle every value that the static type of the selector expression (**selector**) can take, according to the compiler's rules. For a **switch expression**—an expression that evaluates to a result—this is a **compile-time requirement**: every valid execution path must produce a value via a branch or complete abruptly by throwing an exception, never silently "return nothing."

A simple example with an enum:

~~~java
enum Signal { RED, YELLOW, GREEN }

static String guidance(Signal signal) {
    return switch (signal) {
        case RED -> "stop";
        case YELLOW -> "slow";
        case GREEN -> "go";
    };
}
~~~

If the **Signal** enum at compile time has only these three constants, the compiler knows all three have been listed, so **default is not needed**. If you omit **case GREEN**, the switch expression will not compile because it does not cover the entire set of valid enum values.

Conversely, with a selector of type **Object**, there can be many concrete types. The following snippet is an **intentionally invalid** example:

~~~java
static String incomplete(Object input) {
    return switch (input) {
        case String text -> "string";
        case Integer number -> "integer";
        // ERROR: the Object selector still has many uncovered types
    };
}
~~~

**default** or an appropriate general pattern branch is the usual way to make a switch exhaustive when the selector is **Object**. **Exhaustiveness is determined primarily by the static type and the case structure**, not by a few values that happen to appear at runtime.

**Java version:** switch expressions have been standard since **Java 14**; **pattern matching for switch** along with **case Type variable**, **when**, and the sealed pattern rules in this article were standardized in **Java 21**. The complete example below uses **JDK 21+**, without enabling preview features.

## 2. Ways to make a switch expression exhaustive

In Java 21, common approaches include:

| Selector type | How to ensure exhaustiveness | Notes |
| --- | --- | --- |
| **enum E** | List all enum constants, or add **default** | Can leverage the compiler when the enum grows |
| **Object** or open types | Have **default**, or an unguarded type pattern covering the source type | Listing only a few subtypes is usually not enough |
| **sealed interface/class** | Unguarded type patterns covering all permitted subtypes | **default** is not necessarily required |
| A specific reference type, e.g. **String** | Have an unguarded pattern covering every non-null String, or **default** | Handling null is a separate concern |
| Patterns with **when** | Need an additional branch covering the values that the guard might reject | An arbitrary guard does not automatically cover the entire type |

For sealed types, the compiler analyzes the **permits** list and subtype relationships to determine whether the branches are complete. For enums, the compiler checks the list of constants. For an open selector type like **Object**, a **default** branch is usually clearer than guessing possible types.

Do not interpret the table as "you just need many cases." Five overly specific cases can still miss a type; two cases can be sufficient when they cover the exact two subtypes of a sealed interface.

### Exhaustive does not mean every branch is always reachable

A switch selects **one applicable branch** according to the case rules; it does not execute all branches. Exhaustiveness checking ensures there is an appropriate branch for every valid value, whereas **dominance** checking detects a later label that is shadowed by an earlier label. The two checks are separate concerns.

## 3. Complete Java 21 example: enum, sealed hierarchy, and Object

Save the file **ExhaustivenessDemo.java**:

~~~java
public class ExhaustivenessDemo {
    enum Signal { RED, YELLOW, GREEN }

    sealed interface Expr permits Literal, Add, Negate {}

    record Literal(int value) implements Expr {}
    record Add(Expr left, Expr right) implements Expr {}
    record Negate(Expr inner) implements Expr {}

    static String guidance(Signal signal) {
        return switch (signal) {
            case RED -> "stop";
            case YELLOW -> "slow";
            case GREEN -> "go";
        };
    }

    static int evaluate(Expr expression) {
        return switch (expression) {
            case Literal literal -> literal.value();
            case Add add ->
                    evaluate(add.left()) + evaluate(add.right());
            case Negate negate -> -evaluate(negate.inner());
        };
    }

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text.strip();
            case Number number -> "number:" + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(guidance(Signal.RED));
        System.out.println(guidance(Signal.GREEN));

        Expr value = new Add(
                new Literal(2),
                new Negate(new Literal(5))
        );
        System.out.println(evaluate(value));

        System.out.println(describe(" hi "));
        System.out.println(describe("  "));
        System.out.println(describe(42));
        System.out.println(describe(null));
        System.out.println(describe(new Object()));
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac -encoding UTF-8 ExhaustivenessDemo.java
java ExhaustivenessDemo
~~~

Exact output:

~~~text
stop
go
-3
text:hi
blank
number:42
null
other
~~~

**Analysis:**

1. **guidance** is an exhaustive switch expression because all three constants **RED**, **YELLOW**, and **GREEN** are listed.
2. **Expr** is a **sealed interface** that permits only the three records **Literal**, **Add**, and **Negate**. Each record is a concrete subtype, so the three cases in **evaluate** cover all non-null **Expr** objects.
3. The expression **Add(Literal(2), Negate(Literal(5)))** is evaluated recursively: **2 + (-5) = -3**.
4. **describe** takes **Object**, so the three specific case kinds still do not cover every object; **default** completes the set of branches for the remaining types.
5. **case String text when text.isBlank()** matches blank strings, while the following **case String text** covers the remaining strings. **when** by itself does not make all Strings covered.
6. **case null** explicitly handles the null value to return the string **"null"**; this is a separate business decision from the standard exhaustiveness requirement.

The **javac** command in the example only requires JDK 21; **--enable-preview** is not needed.

## 4. Why are sealed types more useful than a broad default?

With a sealed hierarchy, the set of permitted direct subtypes is a contract that can be analyzed at compile time:

~~~java
sealed interface PaymentResult
        permits Accepted, Declined {}

record Accepted(String receipt) implements PaymentResult {}
record Declined(String reason) implements PaymentResult {}
~~~

The snippet above is **illustrative declaration code** and needs to be placed in a valid source file. A switch expression for this result type can omit default:

~~~java
static String summary(PaymentResult result) {
    return switch (result) {
        case Accepted ok -> "accepted:" + ok.receipt();
        case Declined no -> "declined:" + no.reason();
    };
}
~~~

If **permits** is later extended with a **Pending** subtype, the compiler will point out that the switch is no longer exhaustive when recompiling the code. This is a major maintainability benefit: places that need updating are detected immediately when the data model changes.

If you always include **default -> "unknown"**, the switch remains exhaustive and the program will usually still compile after adding a subtype; however, the new branch may be swallowed into the fallback without prompting the developer to consider how to handle it. When you want to guarantee that logic gets updated when a subtype is added, **consider omitting default** on an already exhaustively covered sealed hierarchy.

A **permitted subtype** can be declared **final**, **sealed**, or **non-sealed** according to language rules. When a **case SomePermittedType x** branch covers that subtype, instances of subclasses of that type are also handled by that branch. Therefore, coverage checking depends on type relationships, not merely comparing class names as strings.

## 5. Default: a general coverage solution that can hide omissions

If all subtypes are not known at compile time, **default** is a reasonable choice:

~~~java
static String label(Object input) {
    return switch (input) {
        case String text -> "string:" + text;
        case Number number -> "number:" + number;
        default -> "other";
    };
}
~~~

This is an **illustrative Java 21+ method**. The compiler knows **default** catches objects that do not match earlier cases. However, remember: **default is not synonymous with case null**. If the selector is null and there is no case handling null, the switch typically throws **NullPointerException** instead of returning **"other"**.

With enums, a **default** can also negate the benefit of the compiler reminding the author to add handling for a newly added constant. Choose default if the application genuinely has a "handle all remaining values the same way" rule, not merely to mask coverage errors.

## 6. The when guard and exhaustiveness: accepting a type does not mean accepting every value

Suppose business logic only processes positive integers:

~~~java
// Intentionally invalid: not exhaustive for an Object selector.
static String positiveOnly(Object value) {
    return switch (value) {
        case Integer number when number > 0 -> "positive";
    };
}
~~~

Besides types other than **Integer**, even the values **0** and **-1** do not match the guard. You must add branches for values not accepted by the guard, for example:

~~~java
static String classifyNumber(Object value) {
    return switch (value) {
        case Integer number when number > 0 -> "positive";
        case Integer number -> "zero-or-negative";
        case null -> "missing";
        default -> "not-an-integer";
    };
}
~~~

**when** is evaluated only after the pattern has matched, so the variable **number** safely has type **Integer** in the expression **number > 0**. When the guard evaluates to false, the switch evaluates the subsequent cases.

**Case order matters.** If you place **case Integer number -> ...** before **case Integer number when number > 0 -> ...**, the general case shadows the specific branch; the compiler may report a **dominated case** error.

### Why guards do not contribute to proving type coverage

The Java 21 compiler does not treat an arbitrary **when** guard as proof that it is always true for every value. When you want type-based exhaustiveness, you need an unguarded pattern label covering the remaining values or an appropriate **default**.

For example, **case String s when s.length() >= 0** may appear always true for a String, but it should not be used in place of an unguarded **case String s** to prove exhaustiveness. Write an unguarded branch when you want the compiler to see direct coverage.

## 7. Is null part of an exhaustive switch expression?

**A very common point of confusion:** a switch expression that has enough cases for every **non-null** value of a sealed interface or enum can still **compile without a case null**. However, if **null** is passed to the selector at runtime, that switch will throw **NullPointerException** when no null label applies.

Example using the complete program above:

~~~java
// Illustrative snippet; do not put in main unless you want an exception thrown.
Expr value = null;
System.out.println(evaluate(value)); // NullPointerException
~~~

The **Literal**, **Add**, and **Negate** branches are still considered by the compiler to exhaustively cover the subtypes of **Expr**, yet none of those branches handle null.

If the API allows null and needs a normal result, add:

~~~java
// Snippet returning a switch expression inside a method taking Expr expression:
return switch (expression) {
    case null -> 0;
    case Literal literal -> literal.value();
    case Add add -> evaluate(add.left()) + evaluate(add.right());
    case Negate negate -> -evaluate(negate.inner());
};
~~~

This is illustrative code that can be used when placed in the same class as the type declarations and the **evaluate** method in the Java 21 example. Returning **0** for null is just an example policy; real business logic might require an exception or a different value.

In short, **compile-time exhaustiveness is not a promise that every runtime value, especially null, will produce a normal result**. Two questions must be checked separately: *are there enough branches for the subtypes?* and *is null a valid input?*

## 8. Switch expressions and switch statements do not share the same historical rules

On Java 21:

- **Every switch expression** must be exhaustive.
- **Enhanced switch statements** (for example, statements using pattern cases, null cases, or reference-type selectors outside the classic switch group) must also be exhaustive.
- **Legacy switch statements** that only use constants/enums in traditional syntax are not required to be exhaustive for backward compatibility; if no case matches, they can simply do nothing.

Example of a valid legacy statement even with missing cases:

~~~java
static void printSignal(Signal signal) {
    switch (signal) {
        case RED -> System.out.println("stop");
        // Missing YELLOW, GREEN: a legacy statement can still compile.
    }
}
~~~

Meanwhile, a corresponding **switch expression** missing **YELLOW** and **GREEN** will be rejected by the compiler.

Do not assume that because an older switch statement can omit branches, a switch expression can too. The two forms have different coverage obligations, especially starting in Java 21 where enhanced statements require exhaustiveness.

## 9. Every path in a branch must produce a value or throw

Case coverage is **one requirement**; the selected branch must still obey the semantics of a switch expression.

An arrow branch can return an expression:

~~~java
static String sizeLabel(Object value) {
    return switch (value) {
        case String s -> "length:" + s.length();
        default -> "other";
    };
}
~~~

When a branch needs multiple statements, use **yield** to supply the result of the switch expression:

~~~java
static String normalized(Object value) {
    return switch (value) {
        case String s -> {
            String clean = s.strip();
            yield clean.isEmpty() ? "(blank)" : clean;
        }
        default -> "(other)";
    };
}
~~~

These are **illustrative Java 21+ methods**, not standalone files. A switch expression block that has a path completing normally without an appropriate **yield**/throw will not compile. **yield** produces the result of the switch expression branch, unlike **return** which exits the method.

With traditional colon cases, you can also write a switch expression using **yield**, but you must check fall-through and every execution path. For readability and fewer mistakes, the examples in this article prefer **case ... ->**.

## 10. Common pitfalls

**Pitfall 1 — assuming default covers null:** default catches unlisted types/values, but it does not replace **case null**. You must handle null separately if the contract requires it.

**Pitfall 2 — omitting default on an Object selector:** checking only String and Number cannot be exhaustive for Object; there must be a default or a pattern covering the remaining types.

**Pitfall 3 — adding default to a sealed switch just to silence errors:** a broad default lets new subtypes silently fall into generic behavior. Leverage the compiler to check the subtype list when explicit updates are needed.

**Pitfall 4 — having only cases with when:** a guard condition can evaluate to false, so you still need an unguarded case for the remainder or another branch to ensure coverage.

**Pitfall 5 — forgetting pattern variable scope:** a variable declared in **case Literal literal** can only be used where that label has matched, not arbitrarily in other cases.

**Pitfall 6 — confusing dominance with exhaustiveness:** an overly general case placed early can make a later branch unreachable; conversely, missing a subtype makes the switch non-exhaustive. Both need to be checked when modifying cases.

**Pitfall 7 — thinking a switch expression can never throw:** exhaustiveness only checks case coverage; code inside a branch can still throw an exception, and an unhandled null can cause an NPE.

**Pitfall 8 — using Java 21 switch patterns on Java 17:** Java 17 has instanceof patterns and switch expressions for traditional types, but it does not have standard Java 21 switch patterns with **when**.

**Pitfall 9 — thinking exhaustive means no testing is needed:** the compiler does not verify all business constraints or mathematical results. For instance, **Add** and **Negate** in an expression could hold null in their components if callers allow it; in that case, an error can occur inside the handling branch even when all cases are covered.

## 11. Compilation and review checklist

Before accepting a switch expression, check the following:

1. Identify the **static type of the selector**. For enum/sealed types, is the full list of cases determined from the current type declaration?
2. List the **cases** and verify that the **unguarded** group covers the source type; if it is an open selector, is there a sensible default?
3. If **when** is used, identify which values can fail the guard and which case receives them.
4. Check **dominance**, especially ensuring specific subtypes appear before a general parent pattern that could shadow them.
5. Determine whether **null** is valid. If so, there must be a **case null** or explicit handling before the switch.
6. Ensure every branch, when selected, produces a value via an expression/**yield** or explicitly throws an exception.
7. If using a sealed hierarchy, consider avoiding **default** so the compiler reports when a new subtype is added.
8. Compile with **javac** on the target JDK and run tests for each subtype, true/false guard branches, null, and the fallback branch.
9. When changing a schema or dependency version, **recompile** the module containing the switch to verify exhaustiveness against the updated type definitions.
10. Distinguish normal results from exceptions that can occur at runtime; do not infer that exhaustive = never throws.

## 12. Official references

- [JLS Java SE 21 §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): coverage conditions, enum, sealed, and default.
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): requirement for expressions to yield a value and exhaustiveness.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): case patterns, null, guards, dominance, and sealed types.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): history and semantics of switch expressions.

**Conclusion:** A switch expression must cover all possibilities that the compiler can recognize. With **enums** and **sealed hierarchies**, Java 21 can prove exhaustiveness from specific cases alone without needing default; with open types like Object, default is usually the appropriate choice. Exhaustiveness does not replace null handling, guard checks, or business logic testing, but it turns certain branching omissions into compile-time errors right from the start.