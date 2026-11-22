# Reading Case Order Top-to-Bottom in Java Switch Patterns

## 1. How to read a switch with patterns

In Java, **switch** takes a selector expression (**selector**) and determines the **case** label that applies to that expression's value. With **pattern matching for switch** (a standard feature since **Java 21**), a label can check a **type**, bind a **pattern variable**, and add an extra condition using **when**.

To read a switch pattern, answer these questions in order:

1. **What is the selector's value, and is it null?** The selector expression is evaluated to obtain a value used for branch selection.
2. **Which cases can apply?** For a non-null value, examine the case labels in order within the switch block; the type pattern must match the value, and the **when** guard (if present) must evaluate to true.
3. **Which label is the first match?** That is the selected label; subsequent matching labels are not selected.
4. **How does the selected label execute?** An arrow branch (**->**) executes the right-hand side without falling through to the next branch; a colon-style branch can have **fall-through** if it does not terminate properly.

Java 21 example:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "blank";
        case String text -> "text:" + text.strip();
        case Integer number -> "integer:" + number;
        default -> "other";
    };
}
~~~

When **value = "   "**, the program selects **case String text when text.isBlank()**. With **value = " Java "**, the guarded case is not satisfied, so it continues to **case String text**. With **value = 7** (boxed into an **Integer** when passed through the **Object** parameter), the **Integer** case applies. With **null**, **case null** handles it separately.

**Version scope:** Java 17 already supported **instanceof String text**, but **case String text** and the **when** guard in switch are only standard syntax starting in **Java 21**. The switch pattern examples run on JDK 21+, not Java 17.

## 2. Which labels are considered a match?

A case label can be a constant, a type pattern, a pattern with **when**, or a **null**/**default** handler matching the selector. How the check works depends on the label kind:

| Label | Condition to apply | What to read |
| --- | --- | --- |
| **case "start"** (String selector) | String equals the constant **"start"** | This is a value match |
| **case String text** | Value is non-null and is a **String** | Variable **text** has static type **String** |
| **case String text when text.isBlank()** | Matches **String** and guard is true | The guard only runs after the pattern matches |
| **case Number number** | Value is a **Number** | May include **Integer**, **Double**, ... |
| **case null** | Selector value is **null** | Separates out the null case |
| **default** | No other label applies | Fallback branch for unclassified values |

For a **non-null** selector, the Java 21 specification describes finding the **first applicable case label**. For **null**, a separate rule checks **case null**. In reference-type switches like the examples here, if a null-handling label is missing, **switch(null)** can throw a **NullPointerException**; do not assume **default** acts as a replacement for **case null**.

**Priority is not automatically inferred from "stronger" or "weaker" types.** The source code and dominance rules determine valid ordering. The compiler prevents many unreachable labels, but the author must still place business-meaningful guards in the desired order.

## 3. Reading cases in order with a complete Java 21 example

Save the following code as **CaseOrderDemo.java**:

~~~java
public class CaseOrderDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.isBlank() -> "BLANK";
            case String text when text.length() >= 5 ->
                    "LONG:" + text.strip();
            case String text -> "SHORT:" + text;
            case Integer number when number >= 0 ->
                    "NONNEG:" + number;
            case Integer number -> "NEG:" + number;
            case Number number ->
                    "NUMBER:" + number.getClass().getSimpleName();
            case CharSequence chars -> "SEQUENCE:" + chars.length();
            default ->
                    "OTHER:" + value.getClass().getSimpleName();
        };
    }

    static String lengthFirst(Object value) {
        return switch (value) {
            case String text when text.length() >= 3 -> "LENGTH";
            case String text when text.isBlank() -> "BLANK";
            case String text -> "OTHER_STRING";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static String blankFirst(Object value) {
        return switch (value) {
            case String text when text.isBlank() -> "BLANK";
            case String text when text.length() >= 3 -> "LENGTH";
            case String text -> "OTHER_STRING";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
                null, "   ", " Java ", "hi", 7, -3, 2.5,
                new StringBuilder("abc"), new Object()
        };
        for (Object input : inputs) {
            System.out.println(classify(input));
        }

        System.out.println("length-first:" + lengthFirst("   "));
        System.out.println("blank-first:" + blankFirst("   "));
    }
}
~~~

Compile and run with **JDK 21 or later**:

~~~bash
javac -encoding UTF-8 CaseOrderDemo.java
java CaseOrderDemo
~~~

Output:

~~~text
NULL
BLANK
LONG:Java
SHORT:hi
NONNEG:7
NEG:-3
NUMBER:Double
SEQUENCE:3
OTHER:Object
length-first:LENGTH
blank-first:BLANK
~~~

Step-by-step trace of **classify**:

1. **null** is matched by **case null**. No type pattern needs to be checked.
2. The three-space string matches **String**, and the **isBlank()** guard is true, so it returns **BLANK**. The **length() >= 5** branch is not evaluated even though it is also a String.
3. **" Java "** matches **String**, the blank guard is false; its original length is **6**, so the **length() >= 5** case is true. Then **strip()** produces **"Java"**, yielding **LONG:Java**.
4. **"hi"** is not blank and has length less than 5, so it reaches the unguarded **case String text**, returning **SHORT:hi**.
5. **7** and **-3** are **Integer** values. The guarded case **number >= 0** matches **7**, while the next **Integer** case matches **-3**. Both are checked before the broader **Number** pattern.
6. **2.5** is a **Double**: it does not match either **Integer** case but is a **Number**, so it returns **NUMBER:Double**.
7. **StringBuilder("abc")** is not a **String**, **Integer**, or **Number**, but implements **CharSequence**, so it returns its length as **SEQUENCE:3**.
8. A plain **Object** instance does not match any of the listed patterns, so it falls into **default**.

This trace table helps separate **label-checking order** from **branch-body execution order**. With the **->** arrow, the selected branch completes the switch processing for that branch; it does not automatically run subsequent cases.

## 4. Multiple guards can be true simultaneously: the earlier case wins

Both **lengthFirst** and **blankFirst** in the program above receive the input **"   "** (three spaces). This value satisfies both conditions at the same time:

- **text.length() >= 3**: true, because there are three space characters.
- **text.isBlank()**: true, because all characters are whitespace.

In **lengthFirst**, the length case appears first, so the result is **LENGTH**; the **isBlank()** guard later on is not selected. In **blankFirst**, the blank case comes first, so the result is **BLANK**.

Notably, both orderings **compile cleanly on Java 21**. The compiler cannot treat arbitrary business conditions in **when** as value sets with easily provable inclusion relationships. Therefore, the order of two guards can change the result **without any compile-time error**.

Practical rule: write the case with the **highest-priority condition** first, followed by less specific cases; finally, put the unguarded type pattern for the remainder of the same type.

String classification example:

~~~java
// Illustrative labels inside a Java 21 switch:
case String text when text.isBlank() -> "blank";
case String text when text.length() >= 5 -> "long";
case String text -> "other string";
~~~

If business logic requires **all blank strings** to be recognized before long strings, the order above is appropriate. Before swapping the first two lines, check whether any input can satisfy both guards.

## 5. Dominance: a general case can shadow a specific case

**Dominance** is a compiler check to detect when a case label is completely covered by an earlier label. If no value can ever reach the later label, Java 21 rejects the code at compile time.

**Intentionally incorrect** example:

~~~java
// Incorrect: CharSequence comes first and covers every String.
static String wrong(Object value) {
    return switch (value) {
        case CharSequence chars -> "sequence";
        case String text -> "string"; // compile-time error
        default -> "other";
    };
}
~~~

**String** implements **CharSequence**. Every value that matches **case String text** also matches **case CharSequence chars** above it. Thus, the String label is dominated.

How to fix it:

~~~java
// Java 21+ illustrative code inside a valid class.
static String corrected(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence chars -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
~~~

**String** is matched first; non-String **CharSequence** objects (such as **StringBuilder**) are handled afterward.

A similar error occurs when placing an **unguarded** case before a case of the same type with **when**:

~~~java
// Incorrect: the earlier String case covers the guarded String case.
static String wrongGuard(Object value) {
    return switch (value) {
        case String text -> "any string";
        case String text when text.isBlank() -> "blank"; // compile-time error
        default -> "other";
    };
}
~~~

The correct approach is to place the specific guarded case first:

~~~java
static String correctGuard(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text -> "other string";
        case null -> "null";
        default -> "other";
    };
}
~~~

The methods in the snippets in this section are not standalone programs; the complete program with **main** is **CaseOrderDemo.java** in section 3.

**Distinguishing dominance from overlapping guards:** the compiler can prove that an unguarded **String** covers every guarded **String** case, but it cannot necessarily prove that two arbitrary **when** conditions cover each other. Just because two guards compile in either order does not mean swapping them preserves behavior.

## 6. When is a guard evaluated?

A guarded pattern case is processed in two steps:

1. The value must **match the pattern** first—for example, it must be a **String** so that the **text** variable of type **String** exists.
2. If it matches, Java then evaluates the **when** expression. If the guard is **true**, the case is selected. If the guard is **false**, selection continues to the next applicable label.

This makes it safe to use the pattern variable directly inside the guard:

~~~java
// Illustrative code inside a Java 21+ switch:
case String text when !text.isBlank() && text.length() >= 3 ->
        "accepted:" + text;
~~~

The guard does not call **text.isBlank()** on non-String objects. Inside the guard, the **&&** operator still short-circuits: if **!text.isBlank()** is false, the **text.length() >= 3** side does not run.

If a guard calls a method that throws an exception, branch selection is interrupted by the exception; **switch does not treat a throwing guard as false** to move on to the next case. Therefore, avoid using guards with complex side effects or dependencies on unpredictable state changes.

When debugging code, read each case by asking: **does the type match? → if yes, is when true? → if both are true, stop branch selection**. This is more accurate than seeing the word **case** and assuming every case body will execute.

## 7. Ordering with constant cases, case null, and default

**Constant cases** match specific values. The following example uses a switch with a **String** selector (JDK 21+):

~~~java
static String command(String value) {
    return switch (value) {
        case "start" -> "BEGIN";
        case "stop" -> "END";
        case null -> "NO_COMMAND";
        default -> "UNKNOWN";
    };
}
~~~

This is an illustrative method snippet; the **"start"** and **"stop"** cases are value labels, not type patterns. **Duplicate** constants in the same switch are a compile-time error; line order does not make the compiler accept duplicate labels.

For **null**, write **case null** explicitly if it is a valid input state. The specification has a separate rule for determining the null label, so do not assume that **null** will step through every type pattern from top to bottom like other objects. **default** is a fallback; place it at the end of the switch block so readers can follow easily.

Note on **case Object obj** or general patterns: broad patterns can shadow later labels or create unintended branch-selection rules. Do not use an overly broad label before handling all specific cases.

## 8. Selecting a case vs. classic switch fall-through

There are two separate phases:

- **Selection:** determining which case label applies.
- **Execution:** running the statements attached to that label according to the switch syntax in use.

In modern **->** syntax, execution never automatically continues into the body of the case below. With traditional **case ... :** syntax, after a label is selected, execution can **fall through** into the statements of subsequent cases if **break**, **return**, **throw**, or another proper terminating control flow is missing.

Example that runs even on **Java 17**:

~~~java
public class ClassicFallThroughDemo {
    static String oldStyle(int value) {
        StringBuilder out = new StringBuilder();
        switch (value) {
            case 1:
                out.append("one");
            case 2:
                out.append("-two");
                break;
            default:
                out.append("-other");
        }
        return out.toString();
    }

    public static void main(String[] args) {
        System.out.println(oldStyle(1));
        System.out.println(oldStyle(2));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassicFallThroughDemo.java
java ClassicFallThroughDemo
~~~

Output:

~~~text
one-two
-two
~~~

When **value = 1**, the **case 1** label is selected. Because there is no **break**, the program continues executing the statement in **case 2** **without re-checking** whether 1 equals 2. This is **execution fall-through**, which is distinct from finding the first matching case label. With **value = 2**, only the part from **case 2** to **break** runs.

When writing pattern matching in Java 21 switches, prefer **->** branches to avoid confusing selection with fall-through. Do not assume that "every colon case stops on its own," because that is false.

## 9. Exhaustiveness and sealed hierarchies

If the selector is a **sealed interface**, the compiler knows the permitted set of subtypes and checks whether a switch expression covers all necessary cases.

Java 21+ illustrative example:

~~~java
sealed interface Result permits Success, Failure {}

record Success(String message) implements Result {}
record Failure(int code) implements Result {}

static String render(Result result) {
    return switch (result) {
        case Success success -> "OK:" + success.message();
        case Failure failure -> "ERROR:" + failure.code();
    };
}
~~~

This snippet must be placed inside a valid class/source file context; it is a method and type example, not a program with **main**. All non-null subtypes are handled, so **default** is not needed. If the set of subtypes is expanded, recompiling may require adding cases.

**Exhaustiveness does not replace ordering rules.** If a subtype is shadowed by a broader pattern above it, the compiler can still report dominance; if a required subtype is missing, the compiler can report that the switch is not exhaustive. For null inputs, the example above has no **case null**, so handle it explicitly if the API contract allows null.

## 10. Code review checklist for reading switch patterns

When looking at a long switch, proceed in this order:

1. Identify the static type and possible runtime values of the **selector**. Specifically check whether null is valid.
2. Read **specific pattern labels and guards** from top to bottom. For each case, note the type-matching condition and the **when** condition.
3. Determine whether guards of the same type can **overlap**. If so, the earlier case determines business priority.
4. Check for **dominance**: a broad pattern like **CharSequence** placed before **String**, or an unguarded **String** case placed before **String ... when**, can prevent the code from compiling.
5. Locate the **unguarded** type pattern label that handles the remainder and check whether **default** makes sense.
6. Check **null** explicitly; do not conflate your assumptions about null with the pattern order for non-null objects.
7. Check whether branch syntax uses **->** or colons; for colons, check for **fall-through** risks.
8. If using a **switch expression** over a sealed hierarchy, verify compiler exhaustiveness checking and consider avoiding unnecessary defaults.
9. Test at least one value matching the first case, one value skipping the first guard to match a later case, one value satisfying multiple guards, one value matching no specific case, and null.
10. Compile with the project's target version: **Java 21+** for switch patterns and **when**; **Java 17** supports patterns in **instanceof** but not standard Java 21 switch patterns.

### Self-check exercises

**Scenario A:** There is **case String s when s.length() > 2** before **case String s when s.isBlank()**. For **"   "**, the first branch is selected because its length is 3; to prioritize blank strings, swap the two cases.

**Scenario B:** There is **case Number n** before **case Integer i**. Result? The Java 21 compiler reports that the Integer label is dominated, because every Integer is a Number. Place Integer before Number.

**Scenario C:** There is **case String s** before **case String s when s.startsWith("ID-")**. Result? The guarded label afterward is unreachable; place the guarded case first.

**Scenario D:** A switch uses **case 1:** then **case 2:** without a **break** in case 1. When the value is 1, the body of case 2 can still run due to fall-through; this does not mean the selector matched both constants.

**Scenario E:** A **switch expression** returns a result for every subtype of a sealed interface but omits **case null**. Does it automatically accept null? Do not assume so; if null is a supported input, include an appropriate handling branch.

## 11. References

- [Java Language Specification 21, §14.11.1.2 — Determining which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): how labels are selected and guards are evaluated.
- [Java Language Specification 21, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): dominance, label validity, and switch behavior.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch pattern design, null handling, when guards, and pattern ordering.
- [Java Language Specification 21, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): how switch expressions select branches and produce values.

**Conclusion:** Read switch patterns from top to bottom to find the **first applicable label** for a non-null value, considering both the type and the **when** guard. Overlapping guards that evaluate to true mean **case order determines the outcome**; broad patterns placed in the wrong position can trigger compiler **dominance** errors. After a label is selected, check whether the syntax uses **->** or **:** to know if there is a **fall-through** risk. Handling **null** and **default** explicitly ensures the selected branch matches the program contract.