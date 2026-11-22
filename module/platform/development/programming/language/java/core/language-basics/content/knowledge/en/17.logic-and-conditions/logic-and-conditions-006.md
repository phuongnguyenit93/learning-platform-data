# De Morgan's Laws and Simplifying Conditions in Java

> **Java core — language-basics / Logic and conditions**  
> **Environment:** JDK 17+, a standalone Java file, no external libraries needed.  
> **Goal:** Correctly transform negations of AND/OR, read truth tables, and write clearer conditions without breaking logic or short-circuit evaluation order.

## 1. The Two De Morgan's Laws

Given two `boolean` expressions `P` and `Q`:

~~~text
!(P && Q)  is equivalent to  !P || !Q
!(P || Q)  is equivalent to  !P && !Q
~~~

**Rule:** When pushing the negation `!` inside parentheses, **flip AND to OR or vice versa**, and **negate each side**.

~~~java
boolean p = true;
boolean q = false;

boolean a = !(p && q); // true.
boolean b = !p || !q;  // true: equivalent to a.

boolean c = !(p || q); // false.
boolean d = !p && !q;  // false: equivalent to c.
~~~

Do not negate only each operand while keeping the same operator:

~~~java
// Logically WRONG:
// !(p && q)  is NOT equivalent to  !p && !q.
// !(p || q)  is NOT equivalent to  !p || !q.
~~~

For example, `!(p && q)` means **"not both true"**; this is equivalent to **"at least one side is false"**, not "both are false".

## 2. Proof via Truth Table

| `P` | `Q` | `!(P AND Q)` | `!P OR !Q` | `!(P OR Q)` | `!P AND !Q` |
| --- | --- | --- | --- | --- | --- |
| false | false | true | true | true | true |
| false | true | true | true | false | false |
| true | false | true | true | false | false |
| true | true | false | false | false | false |

Both columns in each pair are always equal for every combination of `P`/`Q`. This is the basis for rewriting expressions without **changing the boolean result**.

This extends to multiple conditions:

~~~java
// Negating that all three conditions are true:
boolean denied = !(p && q && r);
// Equivalent:
boolean denied2 = !p || !q || !r;

// Negating that at least one condition is true:
boolean none = !(p || q || r);
// Equivalent:
boolean none2 = !p && !q && !r;
~~~

In the extended snippet, `p`, `q`, and `r` are previously declared boolean variables. Do not forget **parentheses** when combining with other conditions; `!` has higher precedence than `&&` and `||`.

## 3. Applying to Business Conditions and Range Checks

For example, a person is **denied** when they do not simultaneously meet the age requirement and hold a ticket:

~~~java
int age = 20;
boolean hasTicket = false;

boolean denied = !(age >= 18 && hasTicket);
boolean deniedSimplified = age < 18 || !hasTicket;
// Both are true in this example.
~~~

The second form reads more naturally: **underage OR no ticket**.

For `int x`, the condition for lying within the closed interval from 0 to 100:

~~~java
boolean inRange = x >= 0 && x <= 100;
boolean outOfRange = !(x >= 0 && x <= 100);
boolean simpler = x < 0 || x > 100;
~~~

When `x` is an integer type, `outOfRange` and `simpler` are equivalent. Conversely, to negate an "outside the range" condition, apply De Morgan's law:

~~~java
boolean inRangeAgain = !(x < 0 || x > 100);
// For int, equivalent to x >= 0 && x <= 100.
~~~

**Note:** Transforming `!(x >= 0)` into `x < 0` is always equivalent only for **integer types** or when `NaN` has already been ruled out for floating-point types. See section 6.

## 4. `null` Guards and Readable Conditions

De Morgan's laws help express invalid-data cases:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank();
boolean invalid = !(name != null && !name.isBlank());

// Rewritten via De Morgan:
boolean invalidSimplified = name == null || name.isBlank();
~~~

If `name == null`, the right side `name.isBlank()` in the last expression **does not run** thanks to short-circuit `||`. `invalid` and `invalidSimplified` are both true; `valid` is false.

This form still **keeps the guard condition ahead of** the operation that could throw `NullPointerException`. Avoid reordering it into:

~~~java
// UNSAFE when name == null:
// boolean broken = name.isBlank() || name == null;
~~~

When modifying or simplifying conditions, the goal is not just fewer characters, but **expressing business rules accurately, keeping code maintainable, and protecting dependent conditions**.

## 5. Short-Circuiting and Side Effects When Applying De Morgan's Laws

In Java, `&&` skips the right side if the left side is false; `||` skips the right side if the left side is true. The two De Morgan transformations below preserve **evaluation order P then Q** and the exact same condition for skipping Q:

~~~java
!(P && Q)  →  !P || !Q
!(P || Q)  →  !P && !Q
~~~

With identical `P`/`Q` expressions on both sides and no other interleaved operations, both the result and which side is evaluated remain unchanged under short-circuit rules.

~~~java
StringBuilder log = new StringBuilder();
boolean result = !(mark(log, "F", false)
        && mark(log, "X", true));
// result=true, log="F": does not call mark(..., "X", ...).
~~~

The rewritten form `!mark(log, "F", false) || !mark(log, "X", true)` also does not call branch X.

**Do not arbitrarily reorder, duplicate, or remove an expression with side effects**: e.g., `readValue()`, `i++`, a logging statement, or a state-updating call. Other algebraic transformations beyond De Morgan's laws might share the same truth table while changing how many times subexpressions run.

Additionally, boolean `&` and `|` **do not short-circuit**. De Morgan's laws also have logical formulas for them, but switching `&&`/`||` to single-character operators can cause a previously skipped right-hand side to run.

## 6. Watch Out When Flipping Relational Operators with `double`/`float`

You often see transformations like:

~~~text
!(x < 10)   →   x >= 10
!(x >= 0)   →   x < 0
~~~

For **`int`/`long`**, these are equivalent. However, for `double` or `float`, `NaN` makes direct operator flipping **no longer equivalent**:

~~~java
double x = Double.NaN;

boolean negatedLess = !(x < 10.0); // true.
boolean greaterOrEqual = x >= 10.0; // false.

boolean negatedRange = !(x >= 0.0 && x <= 100.0); // true.
boolean outsideByComparisons = x < 0.0 || x > 100.0; // false.
~~~

The relational operators `<`, `<=`, `>`, `>=` with `NaN` all evaluate to false, so negating a false relational comparison gives true. **De Morgan's laws still hold**; what is wrong is replacing `!(x >= 0)` with `x < 0` while forgetting `NaN`.

If business rules reject non-finite values, state that explicitly:

~~~java
double x = Double.NaN;
boolean valid = Double.isFinite(x) && x >= 0.0 && x <= 100.0;
boolean invalid = !valid;
// Can be written via De Morgan:
// !Double.isFinite(x) || !(x >= 0.0) || !(x <= 100.0)
~~~

With a nullable `Boolean`, negating `!flag` requires unboxing, which can throw `NullPointerException` if `flag == null`. Define the null-handling rule clearly before simplifying.

## 7. Standalone Java 17+ Program

Create the file **`DeMorganDemo.java`**:

~~~java
public final class DeMorganDemo {
    private static boolean mark(
            StringBuilder log, String label, boolean result) {
        log.append(label);
        return result;
    }

    public static void main(String[] args) {
        boolean p = true;
        boolean q = false;
        System.out.println("andNot=" + (!(p && q)));
        System.out.println("andDeMorgan=" + (!p || !q));
        System.out.println("orNot=" + (!(p || q)));
        System.out.println("orDeMorgan=" + (!p && !q));

        boolean allEquivalent = true;
        for (boolean a : new boolean[] {false, true}) {
            for (boolean b : new boolean[] {false, true}) {
                allEquivalent &= (!(a && b) == (!a || !b));
                allEquivalent &= (!(a || b) == (!a && !b));
            }
        }
        System.out.println("truthTableEquivalent=" + allEquivalent);

        int age = 20;
        boolean hasTicket = false;
        System.out.println("denied=" + (!(age >= 18 && hasTicket)));
        System.out.println("deniedSimplified=" + (age < 18 || !hasTicket));

        String name = null;
        System.out.println("nameValid="
                + (name != null && !name.isBlank()));
        System.out.println("nameInvalid="
                + (name == null || name.isBlank()));

        StringBuilder andOriginalLog = new StringBuilder();
        boolean originalAnd = !(mark(andOriginalLog, "F", false)
                && mark(andOriginalLog, "X", true));
        System.out.println("andOriginal=" + originalAnd
                + ",trace=" + andOriginalLog);

        StringBuilder andRewriteLog = new StringBuilder();
        boolean rewrittenAnd = !mark(andRewriteLog, "F", false)
                || !mark(andRewriteLog, "X", true);
        System.out.println("andRewrite=" + rewrittenAnd
                + ",trace=" + andRewriteLog);

        StringBuilder orOriginalLog = new StringBuilder();
        boolean originalOr = !(mark(orOriginalLog, "T", true)
                || mark(orOriginalLog, "Y", false));
        System.out.println("orOriginal=" + originalOr
                + ",trace=" + orOriginalLog);

        StringBuilder orRewriteLog = new StringBuilder();
        boolean rewrittenOr = !mark(orRewriteLog, "T", true)
                && !mark(orRewriteLog, "Y", false);
        System.out.println("orRewrite=" + rewrittenOr
                + ",trace=" + orRewriteLog);

        double nan = Double.NaN;
        System.out.println("nanNotLess=" + (!(nan < 10.0)));
        System.out.println("nanGreaterEqual=" + (nan >= 10.0));
        System.out.println("nanNegatedRange="
                + (!(nan >= 0.0 && nan <= 100.0)));
        System.out.println("nanOutsideComparisons="
                + (nan < 0.0 || nan > 100.0));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 DeMorganDemo.java
java DeMorganDemo
~~~

**Exact expected stdout:**

~~~text
andNot=true
andDeMorgan=true
orNot=false
orDeMorgan=false
truthTableEquivalent=true
denied=true
deniedSimplified=true
nameValid=false
nameInvalid=true
andOriginal=true,trace=F
andRewrite=true,trace=F
orOriginal=false,trace=T
orRewrite=false,trace=T
nanNotLess=true
nanGreaterEqual=false
nanNegatedRange=true
nanOutsideComparisons=false
~~~

`truthTableEquivalent=true` checks all four combinations of two boolean values. Both trace pairs prove that De Morgan rewriting **does not force a skipped branch to run**. The four `nan...` lines demonstrate the warning about flipping inequalities with `NaN`.

## 8. Simplification Workflow and Exercises

When encountering a condition with nested negations, follow this order:

1. **Identify the parenthesized group**: `!(P && Q)` or `!(P || Q)`?
2. **Flip the connective** (`&&` ↔ `||`) and **negate each operand**.
3. **Read it aloud in plain words**: "not both" → "at least one condition is false".
4. **Keep guards in their proper position** and do not change the order or call count of expressions with side effects.
5. **Check types and special values**, especially `double NaN`, `Boolean null`, and boundaries like 0, min, max.

| Original form | De Morgan form |
| --- | --- |
| `!(a && b)` | `!a \|\| !b` |
| `!(a \|\| b)` | `!a && !b` |
| `!(x >= 0 && x <= 10)` | `!(x >= 0) \|\| !(x <= 10)` |
| `!(obj != null && obj.ready())` | `obj == null \|\| !obj.ready()` |

**Exercise 1.** Rewrite `!(hasAccount && isActive)` using OR and two negations; state its meaning in plain English.

**Exercise 2.** Rewrite `!(isWeekend || isHoliday)` using AND; build a small truth table to verify.

**Exercise 3.** Given `int x = -1`, compare `!(x >= 0 && x <= 10)` with `x < 0 || x > 10`. Are the two expressions equivalent when `x` has type `int`?

**Exercise 4.** Given `String name = null`, why does `name == null || name.isBlank()` not throw an exception? Rewrite it as the negation of an AND.

**Exercise 5.** Why is `!(x < 10)` different from `x >= 10` when `double x = Double.NaN`? Does that difference invalidate De Morgan's laws?

### Key Takeaways

**De Morgan:** `!(P && Q) == (!P || !Q)` and `!(P || Q) == (!P && !Q)`. To push `!` inside parentheses, you must **flip AND ↔ OR** and **negate each condition**. In Java, prioritize readability, preserve safe short-circuiting, and watch out for `NaN` before flipping relational operators.
