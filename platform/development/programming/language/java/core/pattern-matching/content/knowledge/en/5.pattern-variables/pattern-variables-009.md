# Pattern variables in switch statement groups

## 1. What is a statement group and why does variable scope matter?

In Java, `switch` can be written using arrow labels (`case ... ->`) or colon labels (`case ... :`). With the **colon** syntax, a `case` label precedes a sequence of statements; the consecutive sequence of statements associated with that label is called a *switch-labeled statement group* (often shortened to *switch statement group*).

Since **Java 21**, pattern matching in `switch` is a standard feature, no longer requiring `--enable-preview`. A label such as:

~~~java
case String text:
    System.out.println(text.length());
    break;
~~~

both checks whether the selector value matches the `String` type and declares the **pattern variable** `text`. The key rule is that this variable is guaranteed to be *definitely matched* in **the statements belonging to that exact `case String text` statement group**. It does not automatically exist in another group or after the entire `switch`.

This article helps you:

- Distinguish a `case ... :` statement group from a `case ... ->` switch rule.
- Determine exactly where a pattern variable declared at a `case` label or inside a statement within the group can be used.
- Understand the effect of `when`, label ordering, `break`, and `return` on pattern variables.
- Explain why Java **forbids fall-through into a `case` that declares a pattern variable**.
- Distinguish a valid group with multiple constant labels from an invalid group with multiple labels containing pattern variable declarations.
- Handle `null`, `default`, compilation errors, and write maintainable code.

## 2. Shape and boundaries of a switch-labeled statement group

Consider the colon form:

~~~java
switch (value) {
    case String text:
        System.out.println(text.length());
        System.out.println(text.toUpperCase());
        break;

    case Number number:
        System.out.println(number.intValue());
        break;

    default:
        System.out.println("Other");
}
~~~

This is an **illustrative snippet placed inside a method** with `Object value`; the snippet itself is not a standalone program. The three groups are: the statements following `case String text:` up to the next label; the statements after `case Number number:` up to `default:`; and the statements of `default:`.

When `value` matches `String text`, Java binds the variable `text` of type `String`. Both calls `text.length()` and `text.toUpperCase()` belong to this group, so they are valid. In the `case Number number:` group, the variable `number` has type `Number`; the variable `text` from the previous group is no longer in scope.

**The colon does not automatically terminate execution flow.** If a group does not end with `break`, `return`, `throw`, or another control transfer, execution can continue into the statements of the following group (*fall-through*). This rule both affects execution flow and creates safety boundaries for pattern variables.

For comparison, the arrow-form switch rule:

~~~java
switch (value) {
    case String text -> System.out.println(text.length());
    case Number number -> System.out.println(number.intValue());
    default -> System.out.println("Other");
}
~~~

does not fall through to the next rule. The pattern variable `text` is only usable in the guard (if any) and the code attached to the corresponding rule. **The focus of this article is the colon syntax and statement groups**.

## 3. Scope rules according to the Java Language Specification

Java 21 JLS §6.3.2.6 specifies two cases directly related to switch statement groups:

1. **Variable introduced by a switch label:** A pattern variable introduced by a `case` label is *definitely matched* in **all statements of the corresponding switch-labeled statement group**.
2. **Variable introduced by a statement inside a group:** If a statement `S` inside a group introduces a pattern variable, that variable is *definitely matched* in the statements **following `S` within that same group**, when the flow scoping rules of `S` are satisfied.

JLS §6.3.3 also specifies that a pattern variable declared in a case pattern is in scope in the `when` guard expression of that case label. The guard is evaluated only after the pattern has matched.

You can remember this with the following diagram:

~~~text
switch (selector) {
    case String s when !s.isBlank():  <-- s can be used in when
        statementA(s);               <-- s can be used
        statementB(s);               <-- s can be used
        break;
    case Number n:                    <-- NEW statement group
        statementC(n);               <-- n can be used, s is not in scope
        break;
    default:                          <-- NEW statement group
        statementD();                 <-- neither s nor n
}
                                      <-- outside switch, s/n cannot be used
~~~

`statementA(s)`, `statementB(s)`, and the names in the diagram only illustrate positions; they are not built-in APIs. Syntax with `when` and pattern `switch` is stable since Java 21.

**Scope is a compile-time property of the source code**. The fact that execution at runtime might pass into the next label does not cause a variable from the previous group to extend its scope into the next group.

## 4. Runnable program: declaring and using pattern variables in each group

Save the following complete program as `SwitchGroupScopeDemo.java`:

~~~java
public class SwitchGroupScopeDemo {
    static String describe(Object value) {
        StringBuilder out = new StringBuilder();
        switch (value) {
            case null:
                out.append("NULL");
                break;
            case String s when s.isBlank():
                out.append("BLANK");
                break;
            case String s:
                int length = s.length();
                out.append("STRING length=").append(length);
                out.append(", upper=").append(s.toUpperCase());
                break;
            case Number n:
                out.append("NUMBER ").append(n.intValue());
                break;
            default:
                out.append("OTHER");
        }
        return out.toString();
    }

    static String laterStatements(Object value) {
        switch (value) {
            case CharSequence seq:
                if (!(seq instanceof String text)) {
                    return "NOT_STRING_CHAR_SEQUENCE";
                }
                String normalized = text.trim().toUpperCase();
                return "TEXT " + normalized;
            default:
                return "OTHER";
        }
    }

    static String fallthroughDefault(Object value) {
        StringBuilder out = new StringBuilder();
        switch (value) {
            case String s:
                out.append("S=").append(s).append("|");
            default:
                out.append("DEFAULT");
        }
        return out.toString();
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  "));
        System.out.println(describe("Java"));
        System.out.println(describe(12));
        System.out.println(describe(new Object()));
        System.out.println(laterStatements("  hi "));
        System.out.println(laterStatements(new StringBuilder("hi")));
        System.out.println(laterStatements(42));
        System.out.println(fallthroughDefault("x"));
        System.out.println(fallthroughDefault(42));
    }
}
~~~

Using JDK 21 or later, run from the directory containing the file:

~~~bash
javac --release 21 SwitchGroupScopeDemo.java
java SwitchGroupScopeDemo
~~~

Exact output:

~~~text
NULL
BLANK
STRING length=4, upper=JAVA
NUMBER 12
OTHER
TEXT HI
NOT_STRING_CHAR_SEQUENCE
OTHER
S=x|DEFAULT
DEFAULT
~~~

The three methods in the program illustrate three distinct points: scope at a `case` label with a guard; scope of a variable introduced by a statement **inside** a group; and fall-through from a group with a pattern to `default`.

### 4.1. Two String cases can reuse the same name s

In `describe`:

~~~java
case String s when s.isBlank():
    out.append("BLANK");
    break;
case String s:
    int length = s.length();
    out.append("STRING length=").append(length);
    out.append(", upper=").append(s.toUpperCase());
    break;
~~~

The two declarations of `s` are in **two different statement groups**, so this Java 21 program compiles. Each `s` is only in scope within the guard (if any) and the group of its own corresponding label.

In the first group, `s` is used in `when s.isBlank()`. When the guard returns `true`, the program handles the blank string and executes `break`. If the value is `"Java"`, the `String` pattern matches but the `isBlank()` guard is false; Java continues checking the next `case String s:` label and runs that group.

**Order is very important:** if you place the unguarded `case String s:` first, it will cover the guarded `String` case after it, leading to a *dominated case* error. Place more specific conditional labels before general labels.

### 4.2. Pattern variables have a definite type in the group's statements

In `case String s:`, the expressions `s.length()` and `s.toUpperCase()` are both valid: `s` has static type `String` because the pattern has been matched. In `case Number n:`, `n` has type `Number` and `n.intValue()` can be called. Java does not narrow the type of `n` to `Integer` just because the sample input is `12`.

Similarly, `default` does not introduce any pattern variable. If the selector does not match the preceding labels, this group runs and returns `OTHER`.

## 5. Pattern variable introduced by a statement inside a group

A case pattern can create its own variable; statements **inside the group** can also introduce a new pattern variable via `instanceof` and flow scoping.

The following snippet is taken from the `laterStatements` method that ran successfully:

~~~java
case CharSequence seq:
    if (!(seq instanceof String text)) {
        return "NOT_STRING_CHAR_SEQUENCE";
    }
    String normalized = text.trim().toUpperCase();
    return "TEXT " + normalized;
~~~

Reasoning flow:

1. `case CharSequence seq:` is only selected when the selector is a non-null `CharSequence`, so `seq` can be used in the group.
2. `!(seq instanceof String text)` is true if `seq` is not a `String`. In that case, the method executes `return` immediately.
3. If execution reaches the line declaring `normalized`, the non-matching branch has exited. The remaining path **must have matched `String text`**, so `text` can be used in subsequent statements within the same group.
4. With `new StringBuilder("hi")`, the `CharSequence seq` pattern matches but `String text` does not, so it returns `NOT_STRING_CHAR_SEQUENCE`. With `"  hi "`, the result is `TEXT HI`.

**Do not confuse** this with thinking every variable declared in an `if` statement is in scope below it. The early exit condition (`return` in the non-matching branch) is what proves `text` can appear in subsequent statements.

If the group ends and execution moves to another `case` label, neither `seq` from the label nor `text` introduced inside the group is automatically usable in the next group.

## 6. Fall-through: execution can pass through another label without carrying pattern variable scope

The colon form of `switch` has traditional *fall-through*: if the code in a group completes normally, execution continues into the statements after the next label.

Tested valid example:

~~~java
static String fallthroughDefault(Object value) {
    StringBuilder out = new StringBuilder();
    switch (value) {
        case String s:
            out.append("S=").append(s).append("|");
        default:
            out.append("DEFAULT");
    }
    return out.toString();
}
~~~

If the input is `"x"`, the result is `S=x|DEFAULT`: Java enters `case String s`, executes `append`, and then continues running the statement in `default` because there is no `break`. If the input is `42`, it goes straight to `default`, resulting in `DEFAULT`.

In the `default` group, the variable `s` is **not in scope**. The following code **intentionally does not compile**:

~~~java
static void invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println(s);
        default:
            System.out.println(s); // ERROR: s does not belong to the default group
    }
}
~~~

This can be surprising: when runtime falls through from the `String` label to `default`, the `String` object is actually still there, yet **the scope of the name `s` still ends at the group boundary**. Java does not analyze scope based on a specific runtime path.

When using pattern variables, it is good practice to end groups with an explicit `break`, `return`, or `throw` so readers can easily control the flow; the arrow syntax `->` is also a good choice when fall-through is not needed.

## 7. Java forbids fall-through INTO a case that declares a pattern variable

A more dangerous error would be allowing execution to pass from a previous group into a subsequent group whose label declares a pattern variable. Then the code in the subsequent group could read a variable that was never initialized from the pattern.

The following snippet **intentionally does not compile** on Java 21:

~~~java
static void invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println("S:" + s); // missing break
        case Integer i:
            System.out.println("I:" + i);
            break;
        default:
            break;
    }
}
~~~

If allowed, the input `"Java"` would match `case String s` and could continue into `case Integer i`, even though the `Integer i` pattern **never matched**. Therefore, `javac --release 21` reports an error such as:

~~~text
error: illegal fall-through to a pattern
(the previous case label is missing a break)
~~~

Java places this restriction at the **pattern label**: in a statement-group switch block, if the statement immediately preceding a `case` label that declares a pattern variable **can complete normally**, that label is not allowed to be a fall-through target from the previous group.

The intentional fix:

~~~java
case String s:
    System.out.println("S:" + s);
    break;
case Integer i:
    System.out.println("I:" + i);
    break;
~~~

These are two separate groups; a `String` input cannot accidentally execute code intended only for `Integer`. Arbitrarily wrapping statements in curly braces does not substitute for properly terminating control flow before the next pattern label.

Key distinction:

- **Fall-through from a pattern group into a `default` that declares no variables:** can be valid as in section 6; however, `s` is not in scope in `default`.
- **Fall-through into a `case Integer i` label that declares a pattern variable:** blocked by a compilation error because `i` could be uninitialized.

## 8. A statement group with multiple labels: when is it valid?

Java allows multiple `case` labels to lead to the same statements in the normal model, provided the labels obey language rules.

The complete program below runs on Java 21:

~~~java
public class SwitchGroupConstantsDemo {
    static String status(String value) {
        switch (value) {
            case "on":
            case "enable":
                return "ENABLED";
            case "off", "disable":
                return "DISABLED";
            case null, default:
                return "UNKNOWN";
        }
    }

    public static void main(String[] args) {
        System.out.println(status("on"));
        System.out.println(status("enable"));
        System.out.println(status("disable"));
        System.out.println(status(null));
        System.out.println(status("maybe"));
    }
}
~~~

~~~bash
javac --release 21 SwitchGroupConstantsDemo.java
java SwitchGroupConstantsDemo
~~~

Output:

~~~text
ENABLED
ENABLED
DISABLED
UNKNOWN
UNKNOWN
~~~

The `"on"` and `"enable"` labels both lead to one group where **no pattern variables need to be initialized**. The syntax `case "off", "disable":` also only groups constant labels, and `case null, default:` is a special valid combination in Java 21.

**Conversely, when a statement group has a case pattern label that declares one or more variables, Java does not allow a statement to be associated with more than one switch label.** The following styles **intentionally do not compile**:

~~~java
// Example A: multiple consecutive labels leading to one group
switch (value) {
    case String s:
    case Integer i:
        System.out.println("mixed");
        break;
    default:
        break;
}
~~~

~~~java
// Example B: multiple case patterns in the same case label
switch (value) {
    case String s, Integer i:
        System.out.println("mixed");
        break;
    default:
        break;
}
~~~

With `Object value`, both snippets above are rejected by `javac --release 21`, with errors in the `illegal fall-through from a pattern` / `illegal fall-through to a pattern` category.

Reason: if the selector matches `String` but not `Integer` (or vice versa), one of the variables `s` or `i` would not be initialized, while shared statements cannot treat all variables as *definitely matched*.

**Workaround:** separate each pattern into its own group and handle it in its corresponding scope. If you genuinely want to share an algorithm, extract the common processing into a method that takes a parameter converted to a valid common type:

~~~java
case String s:
    System.out.println(describeValue(s));
    break;
case Integer i:
    System.out.println(describeValue(i));
    break;
~~~

`describeValue(...)` here is an **illustrative method that you must define yourself**; the snippet is not a standalone program. This organization shares logic without violating pattern variable scope.

## 9. Subsequent groups and code outside switch cannot use variables from a previous group

Even when each group is explicitly terminated with `break`, a pattern variable still belongs only to the group that declares it.

Example that **intentionally does not compile**:

~~~java
static void invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println(s);
            break;
        case Number n:
            System.out.println(s); // ERROR: s does not exist in this group
            break;
        default:
            break;
    }
}
~~~

`s` is declared and guaranteed to be matched in the `String` group; the `Number` group does not have `s`. Therefore, the compiler reports `cannot find symbol: variable s`.

The same applies outside the entire switch:

~~~java
static int invalid(Object value) {
    switch (value) {
        case String s:
            System.out.println(s);
            break;
        default:
            break;
    }
    return s.length(); // ERROR: s is out of scope after switch
}
~~~

If you need to use the result outside `switch`, assign it to a variable **declared before the switch** and only read that variable once it holds a valid value, or extract it into a method that returns the result like `describe` in the complete program. This cleanly separates pattern variable scope from normal result variable scope.

Conversely, the **same name** such as `s` can appear in two independent groups (for example, two `case String s` cases with different guards in section 4). Having the same name does not mean it is a single variable spanning across groups.

## 10. Scope of when guards, null, and other labels

### Guards are evaluated after the pattern matches

In the label:

~~~java
case String s when s.length() > 3:
    System.out.println(s.toUpperCase());
    break;
~~~

`s` is immediately usable in `when`; the guard only runs when the `String s` pattern matches. If the guard is not satisfied, this label is not selected and Java evaluates subsequent labels.

Place a specific guarded pattern **before** a broader unguarded pattern. For example, `case String s:` before `case String s when s.length() > 3:` will cause the second label to be *dominated*, resulting in a compilation error.

### Null needs its own branch

In `switch (value)` with a reference-type selector, `case String s` does not match `null`. You can use `case null:` like `describe` in the main example, or `case null, default:` when you want to combine two cases without pattern variables like `SwitchGroupConstantsDemo`.

The following combination **intentionally does not compile** in Java 21:

~~~java
case null, String s:
    System.out.println(s);
    break;
~~~

This is an *invalid case label combination*: you cannot combine `null` with a type pattern declaring `s` like this. `null` does not produce a `String` object to bind to `s`.

If you switch on a `null` reference without an appropriate `null`-handling label, Java may throw `NullPointerException` before running the groups. `default` alone does not automatically handle `null` in a pattern switch.

### Java versions

- `instanceof` type patterns have been stable since Java 16 and work in Java 17.
- `case String s:` in pattern matching for `switch` is only stable from **Java 21**. In Java 17, pattern `switch` was still a preview feature and did not have the exact same language contract as Java 21.
- All complete programs in this article were tested with `javac --release 21`, without `--enable-preview`. Do not run these Java 21 examples directly with `--release 17`.

## 11. Quick comparison: colon-form vs arrow-form

| Criterion | Switch statement group `case ... :` | Switch rule `case ... ->` |
| --- | --- | --- |
| Where can pattern variables be used? | Statements in the **label's group**; guard if any | Guard and the rule's expression/block/`throw` |
| Can execution continue into another label's code? | Can *fall-through* if flow is not stopped; however, Java forbids entering a label that declares a pattern variable under the conditions in section 7 | No fall-through |
| Is `break` needed? | Usually needed if you do not want fall-through; `return`/`throw` can also end flow | No `break` needed to prevent fall-through |
| Multiple labels sharing code? | Valid in cases such as multiple constant labels; cannot use multiple labels when the group has a label declaring a pattern variable | Has its own label-combining rules; avoid combining patterns that declare different variables |
| When to use? | When traditional statement style or multiple statements with explicit control flow are needed | Usually more readable for simple branching without needing fall-through |

The point to remember is that **a pattern variable must be definitely initialized on every path that can reach its point of use**, so Java does not allow jumping into a statement group with a variable declaration via another label.

## 12. Common mistakes and how to avoid them

1. **Forgetting `break` before a `case` that declares a pattern variable.** Can lead to an `illegal fall-through to a pattern` error; end the preceding group with `break`, `return`, or `throw`.
2. **Assuming a variable from a previous group can be used in `default` because runtime fell through to it.** Scope ends at the group; reading a variable out of scope is rejected.
3. **Combining multiple case patterns with different variables into one group.** Java forbids this because the variables cannot be definitely initialized from all labels.
4. **Placing a broad case before a guarded case.** The specific label may be *dominated*.
5. **Reading a variable in another group or after the switch.** Return the result or store the data in a result variable with an appropriate scope.
6. **Thinking `when` checks the condition before the pattern.** The guard is evaluated only after the pattern matches; that is why the pattern variable is safe to use in the guard.
7. **Confusing `:` and `->` syntax.** Arrow switch rules do not fall through, whereas colon statement groups have fall-through behavior and its corresponding safety restrictions.
8. **Forgetting to handle `null`.** Type patterns do not match null; explicitly decide on `case null` or handle null before the switch if needed.
9. **Using the wrong JDK.** Compile with Java 21+ for stable pattern `switch`.
10. **Seeing the same name `s` in two groups and thinking it is a single variable.** The declarations have different scopes, even though the names are identical.

## 13. Self-check exercises

**Exercise 1 — Scope within a group**

Given `Object value = "Java";`:

~~~java
switch (value) {
    case String s:
        System.out.println(s.length());
        System.out.println(s.toUpperCase());
        break;
    default:
        System.out.println("Other");
}
~~~

Are both calls using `s` valid? What is printed?

**Answer:** Both are valid because they belong to the same `case String s` group. Prints `4` and `JAVA` on two lines.

**Exercise 2 — Missing break**

Given the code:

~~~java
switch (value) {
    case String s:
        System.out.println(s);
    case Integer n:
        System.out.println(n);
        break;
    default:
        break;
}
~~~

Why does it not compile?

**Answer:** The first group can complete normally and fall through into the label declaring `Integer n`, even though the actual value might not match `Integer`. Java forbids `illegal fall-through to a pattern`. Add `break` after `println(s)`.

**Exercise 3 — Scope from a statement inside a group**

In `case CharSequence seq:`, after the statement:

~~~java
if (!(seq instanceof String s)) {
    return "not string";
}
~~~

can `s.trim()` be used in the next statement within the same group?

**Answer:** Yes. If the check does not match, the method has already executed `return`; the remaining path definitely matches `String s`. This does not allow using `s` in another group.

**Exercise 4 — Combining labels**

Why can you write:

~~~java
case "on":
case "enable":
    return "enabled";
~~~

but cannot have `case String s:` and `case Integer i:` both lead into the same statement group?

**Answer:** Two constant labels do not introduce pattern variables. With two pattern labels, entering from one label would not guarantee that the variables declared in the other label have been assigned a value; Java forbids that combination.

**Exercise 5 — Fall-through to default**

Why does `fallthroughDefault("x")` in the main program return `S=x|DEFAULT`, yet `s` cannot be read inside `default`?

**Answer:** At runtime, execution continues into the statements after the new label when `break` is missing, but the scope of the name `s` belongs only to the `case String s` statement group. *Flow of execution* and *lexical/flow scope* are two different things.

## 14. Checklist for reviewing switch statement groups

Before finalizing a `case ... :` switch with pattern variables, check:

1. Which label declares each pattern variable, and does it have a `when` guard?
2. Is every place using the variable **inside its corresponding group**, or in subsequent statements of the same group after a pattern check that definitely succeeded?
3. Is each group clearly terminated to avoid unintended fall-through?
4. Can any statement fall through from a previous group into a label that declares a pattern variable?
5. Is any variable-declaring pattern label combined with another label in the same group?
6. Are any cases *dominated* by a broader pattern placed before them?
7. Do `null` and unmatched data types have appropriate handling paths?
8. Is the code compiled with Java 21+ when using patterns in `switch`?

**Remember:** a `case` label declaring a pattern variable creates matched variables for **that label's own statement group**. Java maintains safety by limiting variable scope and forbidding fall-through paths or label groupings that could leave a pattern variable unassigned.

### Specifications and references

- Java SE 21 JLS §6.3.2.6 — Scope for Pattern Variables in `switch` Statements: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.6
- Java SE 21 JLS §6.3.3 — Scope for Pattern Variables in `case` Labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3
- Java SE 21 JLS §14.11.1 — Switch Blocks, dominance and fall-through restrictions: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
