# Blocks and the Risks of Omitting Braces in Java

> **Java core — language-basics / if branching**  
> **Requirements:** Java 17+, single standalone Java file, standard library only.  
> **Goal:** Understand that `if`/`else` controls **a single statement** or **a statement block `{ ... }`**; identify bugs from omitting braces, misleading indentation, misplaced `else`, and stray semicolons. Know how to write clear, maintainable, and testable branches.

## 1. A single statement vs. a block

Basic `if` syntax:

~~~java
if (condition) {
    // Statements belonging to the if branch.
}
~~~

`condition` must have type `boolean` (or `Boolean` that can be unboxed). A **block** `{ ... }` is treated by Java as **a single block statement**, capable of containing multiple sub-statements.

Java allows omitting braces when the `if` body is just **one statement**:

~~~java
boolean ready = true;
if (ready)
    System.out.println("READY");
~~~

However, when two operations depend on `ready`, you must use a block:

~~~java
if (ready) {
    System.out.println("READY");
    System.out.println("AUDITED");
}
~~~

Braces determine **branch membership scope**, whereas spaces and indentation only help human readers. Java does not use indentation levels to group statements like some other languages.

## 2. Classic bug: indentation makes both lines look inside `if`

This snippet is syntactically valid but can violate business logic:

~~~java
boolean authorized = false;
if (authorized)
    System.out.println("Access granted");
    System.out.println("Sensitive action"); // ALWAYS runs.
~~~

Java interprets it as:

~~~java
if (authorized) {
    System.out.println("Access granted");
}
System.out.println("Sensitive action");
~~~

The statement printing `"Sensitive action"` **is outside** the `if`, even though it is indented to the same level as the first statement. When `authorized == false`, that statement **still runs**.

Safe fix:

~~~java
if (authorized) {
    System.out.println("Access granted");
    System.out.println("Sensitive action");
}
~~~

**Maintenance risk:** Initially there may be only one line after `if`, so the program works. A maintainer adds a second line with the same indentation and forgets `{}`, causing the new line to run unconditionally. These bugs are especially severe if the `if` body performs authentication, deducts money, deletes data, or mutates state.

## 3. Braces change how nested `if` statements pair up

When writing nested `if` statements without braces, `else` belongs to the nearest `if` that does not yet have an `else` (*dangling else*), regardless of indentation:

~~~java
if (isMember)
    if (hasTicket)
        System.out.println("Enter");
    else
        System.out.println("No ticket");
~~~

If `isMember` is false, **nothing is printed**; `else` belongs to `if (hasTicket)`, and the entire inner `if` is skipped. To attach `else` to the outer `if`, you must close **the body block of the outer `if`** before `else`:

~~~java
if (isMember) {
    if (hasTicket) {
        System.out.println("Enter");
    }
} else {
    System.out.println("Not a member");
}
~~~

With `isMember=false`, the second snippet prints `Not a member`. These are **two different behaviors**, not merely two formatting styles. This lesson emphasizes that **braced blocks determine scope**; the next lesson thoroughly analyzes `else` binding rules, double nested `else`, case tables, and evaluation order.


## 4. A stray `;` can create an empty branch

A standalone `;` is an **empty statement**. Therefore:

~~~java
int attempts = 0;
if (false); // The ; is the entire if body: does nothing.
attempts++;
System.out.println(attempts); // 1
~~~

`attempts++` is **outside** the `if` and runs even though the condition is false. A `;` after `if (condition)` is usually a typo.

**Correct:**

~~~java
if (allowed) {
    performAction();
}
~~~

**Wrong relative to intent:**

~~~java
if (allowed); // Empty if branch.
{
    performAction(); // Standalone block, still runs.
}
~~~

Use a formatter and lint/static analysis to detect unusual empty `if` bodies; semantic review is still required because the program **compiles normally**.

## 5. Braces also create variable scope

Inside a block, you can declare local variables used only within that block:

~~~java
int total = 0;
if (true) {
    int increment = 7;
    total += increment;
}
System.out.println(total); // 7
// System.out.println(increment); // COMPILE ERROR: out of scope.
~~~

Braces limit the region where **a local variable can be referred to by that name in code** (lexical scope); it does not mean every object created in the block is immediately destroyed when the block ends. With `if` and `else`, each block can have its own local variables.

Pay attention to **definite assignment** when assigning values inside branches:

~~~java
int discount;
if (eligible) {
    discount = 10;
} else {
    discount = 0;
}
System.out.println(discount); // Valid: both branches assign it.
~~~

If you only assign `discount` inside `if` without an `else`, and then read `discount`, the compiler may report that the variable might not have been initialized along all paths. Braces make paths visible, but **do not replace Java's assignment flow analysis**.

## 6. Guidelines for choosing a style

| Situation | Recommended action |
| --- | --- |
| `if` currently has only one statement | Still use `{ ... }` to make future additions safe |
| Nested `if` with `if / else` | Use blocks and clear indentation to avoid *dangling else* |
| Suspicious `;` right after a condition | Check whether an empty statement was created accidentally |
| Branch guarding sensitive operations | Put all guarded operations inside the same block |
| Local variable needed only for one branch | Declare it inside that branch's block |
| Adding/editing statements in legacy braceless code | Verify control scope before and after editing |

**Practical recommendation:** Always write braces for `if`, `else if`, and `else` even when there is only a single statement. Java does not enforce this rule, but it makes intent explicit and helps prevent bugs when adding lines. Auto-format code to spot suspicious indentation; write tests for both true and false branches.

## 7. Standalone runnable Java 17+ program

Create the file **IfBlocksDemo.java**:

~~~java
public final class IfBlocksDemo {
    private static void withoutBraces(boolean authorized) {
        if (authorized)
            System.out.println("unguardedProtected");
            System.out.println("unguardedAlways");
    }

    private static void withBraces(boolean authorized) {
        if (authorized) {
            System.out.println("guardedProtected");
            System.out.println("guardedAudit");
        }
        System.out.println("guardedAfter");
    }

    private static String danglingElse(boolean member, boolean ticket) {
        if (member)
            if (ticket)
                return "ENTER";
            else
                return "NO_TICKET";
        return "NO_BRANCH";
    }

    private static String outerElse(boolean member, boolean ticket) {
        if (member) {
            if (ticket) {
                return "ENTER";
            }
        } else {
            return "NOT_MEMBER";
        }
        return "NO_TICKET";
    }

    public static void main(String[] args) {
        System.out.println("authorized=false");
        withoutBraces(false);
        withBraces(false);

        System.out.println("authorized=true");
        withoutBraces(true);
        withBraces(true);

        System.out.println("danglingFalseTrue=" + danglingElse(false, true));
        System.out.println("danglingTrueFalse=" + danglingElse(true, false));
        System.out.println("danglingTrueTrue=" + danglingElse(true, true));

        System.out.println("outerFalseTrue=" + outerElse(false, true));
        System.out.println("outerTrueFalse=" + outerElse(true, false));
        System.out.println("outerTrueTrue=" + outerElse(true, true));

        int attempts = 0;
        if (false);
        attempts++;
        System.out.println("emptyStatementAttempts=" + attempts);

        int total = 0;
        if (true) {
            int increment = 7;
            total += increment;
        }
        System.out.println("blockScopeTotal=" + total);

        boolean eligible = false;
        int discount;
        if (eligible) {
            discount = 10;
        } else {
            discount = 0;
        }
        System.out.println("discount=" + discount);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 IfBlocksDemo.java
java IfBlocksDemo
~~~

**Exact expected stdout:**

~~~text
authorized=false
unguardedAlways
guardedAfter
authorized=true
unguardedProtected
unguardedAlways
guardedProtected
guardedAudit
guardedAfter
danglingFalseTrue=NO_BRANCH
danglingTrueFalse=NO_TICKET
danglingTrueTrue=ENTER
outerFalseTrue=NOT_MEMBER
outerTrueFalse=NO_TICKET
outerTrueTrue=ENTER
emptyStatementAttempts=1
blockScopeTotal=7
discount=0
~~~

`unguardedAlways` appears **even when authorized=false** despite looking inside the `if`; `guardedAudit` appears only when true. `danglingFalseTrue=NO_BRANCH` differs from `outerFalseTrue=NOT_MEMBER` because `else` belongs to different `if` statements. `emptyStatementAttempts=1` shows that `;` creates an empty body.

## 8. Practice exercises

**Exercise 1.** Predict the output for `boolean active = false; if (active) System.out.println("A"); System.out.println("B");`. Add braces so that both A and B are printed only when `active` is true.

**Exercise 2.** Write `if (member) if (ticket) enter(); else reject();` with braces so that `else` definitely belongs to `if (member)`; explain the difference when `member=false`.

**Exercise 3.** Explain the meaning of `if (enabled); doWork();` and fix it so `doWork()` runs only when `enabled` is true.

**Exercise 4.** Declare `int amount` inside an `if` block. Try using it outside the block and explain the scope error; write a valid way to store the result for later use.

**Exercise 5.** Create an `if/else` that assigns a variable in both branches, then try removing the assignment in the `else` branch. Why does Java forbid reading a local variable that might not have been assigned?

### Key takeaway

**Without `{}`, `if`/`else` controls only a single statement; indentation does not determine execution flow.** `else` binds to the nearest `if` without an `else`, and a stray `;` can make an `if` body empty. Use braces consistently to guard operations, clarify variable scope, and prevent subtle bugs during edits.