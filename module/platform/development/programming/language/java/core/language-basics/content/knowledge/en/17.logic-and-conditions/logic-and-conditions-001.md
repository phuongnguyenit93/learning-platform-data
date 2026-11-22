# `&&`, `||`, and `!` in Boolean Expressions — Java 17+

In Java, these three logical operators combine or negate **`boolean` expressions** to produce a `boolean` result:

- `a && b` (*conditional AND*): true when **both** conditions are true; if `a` is false, **`b` is not evaluated**.
- `a || b` (*conditional OR*): true when **at least one** condition is true; if `a` is true, **`b` is not evaluated**.
- `!a` (*logical complement/NOT*): inverts the logical value, turning `true` into `false` and vice versa.

~~~java
boolean loggedIn = true;
boolean isAdmin = false;

boolean canManage = loggedIn && isAdmin; // false.
boolean canView = loggedIn || isAdmin;   // true.
boolean guest = !loggedIn;              // false.
~~~

**Important:** `&&` and `||` are **short-circuit** operators. The right-hand side runs only if the result cannot yet be determined from the left-hand side. This affects both **correctness** and **side effects** in expressions.

## 1. Truth Table

| `a` | `b` | `a && b` | `a || b` | `!a` |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

How to remember:

- **AND `&&`**: "all conditions must be true".
- **OR `||`**: "only one condition needs to be true".
- **NOT `!`**: "the condition is not true"; `!!a` has the same boolean value as `a` when evaluated normally.

Access control example:

~~~java
boolean hasPermission = true;
boolean suspended = false;
boolean allowed = hasPermission && !suspended; // true.
~~~

The subject must have permission **and** not be suspended. `!suspended` applies only to `suspended`; giving variables clear names helps avoid negating the wrong thing.

## 2. Runnable Java 17+ Program

Create a UTF-8 file named **`BooleanLogicDemo.java`**:

~~~java
public class BooleanLogicDemo {
    static boolean mark(String name, boolean result) {
        System.out.println("eval=" + name);
        return result;
    }

    public static void main(String[] args) {
        boolean hasTicket = true;
        boolean adult = false;
        boolean blocked = false;

        System.out.println("and=" + (hasTicket && adult));
        System.out.println("or=" + (hasTicket || adult));
        System.out.println("not=" + (!blocked));
        System.out.println("combined="
                + (hasTicket && (adult || !blocked)));

        System.out.println("== truth table ==");
        System.out.println("FF=" + (false && false)
                + "," + (false || false));
        System.out.println("FT=" + (false && true)
                + "," + (false || true));
        System.out.println("TF=" + (true && false)
                + "," + (true || false));
        System.out.println("TT=" + (true && true)
                + "," + (true || true));

        System.out.println("== short circuit ==");
        boolean shortAnd = mark("and-left", false)
                && mark("and-right-skipped", true);
        System.out.println("shortAnd=" + shortAnd);

        boolean shortOr = mark("or-left", true)
                || mark("or-right-skipped", false);
        System.out.println("shortOr=" + shortOr);

        System.out.println("== eager alternatives ==");
        boolean eagerAnd = mark("eager-and-left", false)
                & mark("eager-and-right", true);
        System.out.println("eagerAnd=" + eagerAnd);

        boolean eagerOr = mark("eager-or-left", true)
                | mark("eager-or-right", false);
        System.out.println("eagerOr=" + eagerOr);

        System.out.println("== grouping ==");
        System.out.println("precedence="
                + (true || false && false));
        System.out.println("parenthesized="
                + ((true || false) && false));
        System.out.println("notAnd="
                + (!(true && false)));
        System.out.println("deMorganAnd="
                + ((!true) || (!false)));
        System.out.println("notOr="
                + (!(true || false)));
        System.out.println("deMorganOr="
                + ((!true) && (!false)));

        System.out.println("== guards ==");
        String name = null;
        boolean nonBlank = name != null && !name.isBlank();
        System.out.println("nonBlank=" + nonBlank);

        int divisor = 0;
        boolean safeDivision =
                divisor != 0 && 12 / divisor > 2;
        System.out.println("safeDivision=" + safeDivision);

        Boolean preference = null;
        System.out.println("nullableSafe="
                + Boolean.TRUE.equals(preference));
        try {
            boolean unsafe = !preference;
            System.out.println("unexpected=" + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("nullableNot=NullPointerException");
        }

        boolean access = hasTicket && (!blocked || adult);
        if (access) {
            System.out.println("access=allowed");
        } else {
            System.out.println("access=denied");
        }

        System.out.println("doubleNot=" + (!!hasTicket));
    }
}
~~~

Use **JDK 17 or later**. Open PowerShell or Bash in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 BooleanLogicDemo.java
java BooleanLogicDemo
~~~

**Exact expected stdout** of the `java BooleanLogicDemo` command alone:

~~~text
and=false
or=true
not=true
combined=true
== truth table ==
FF=false,false
FT=false,true
TF=false,true
TT=true,true
== short circuit ==
eval=and-left
shortAnd=false
eval=or-left
shortOr=true
== eager alternatives ==
eval=eager-and-left
eval=eager-and-right
eagerAnd=false
eval=eager-or-left
eval=eager-or-right
eagerOr=true
== grouping ==
precedence=true
parenthesized=false
notAnd=true
deMorganAnd=true
notOr=false
deMorganOr=false
== guards ==
nonBlank=false
safeDivision=false
nullableSafe=false
nullableNot=NullPointerException
access=allowed
doubleNot=true
~~~

The two commands `java -version` and `javac -version` display environment-dependent JDK information and are not part of the fixed stdout block above. The `mark(...)` methods are only used to print traces and observe execution order, and are **not** a recommended style for business conditions.

## 3. Short-Circuiting: Why Are Some Calls Skipped?

### `&&`: if the left side is false, there is no need to evaluate the right side

~~~java
boolean result = mark("A", false) && mark("B", true);
~~~

The call `mark("A", false)` returns false, so `result` is definitely false. Java **does not call** `mark("B", true)`. The line `eval=B` does not appear.

### `||`: if the left side is true, there is no need to evaluate the right side

~~~java
boolean result = mark("A", true) || mark("B", false);
~~~

The call `mark("A", true)` has already determined the result is true; `mark("B", false)` is not called.

If the right-hand side is evaluated, Java evaluates **the left-hand side first and then the right-hand side**, without arbitrarily swapping the two sides. In a chain `a && b && c`, operands are checked from left to right and stop at the first false; a chain `a || b || c` stops at the first true. This rule is especially important if a subexpression can throw an exception or affect state.

**Do not rely on side effects of the right-hand side** to perform required data updates:

~~~java
// Not recommended: updateCounter() may not be called.
// boolean ok = condition || updateCounter();
~~~

If an update is mandatory, put it in a standalone statement; use `&&`/`||` to describe conditions rather than hiding business operations.

## 4. `&&` vs. `&`, `||` vs. `|`

Java also has the `&` and `|` operators applicable to `boolean`. The logical result **matches the AND/OR truth table**, but differs in **operand evaluation**:

| With boolean operands | Logical result | Evaluates right side if left side already decides? |
| --- | --- | --- |
| `a && b` | AND | **No** if `a == false` |
| `a & b` | AND | **Yes** |
| `a || b` | OR | **No** if `a == true` |
| `a | b` | OR | **Yes** |

In the demo, `eagerAnd` and `eagerOr` both print two `eval=...` lines; the short-circuit operations only print the left-hand side.

`&` and `|` also mean **bitwise operations** on integer types, unlike `&&` and `||`: short-circuit logical operators **only accept boolean**, not integers as "truthy/falsy".

Unless there is a clear reason to force both boolean conditions to execute, prefer `&&` and `||` because they express combined conditions and avoid unnecessary operations.

## 5. Using Short-Circuit Conditions to Guard Dangerous Operations

### Avoiding `null` access

~~~java
String name = null;
boolean hasText = name != null && !name.isBlank(); // false.
~~~

A false left-hand side causes the call `name.isBlank()` to be **skipped**, so no `NullPointerException` occurs. Reversing the order is unsafe:

~~~java
// Wrong when name == null:
// boolean hasText = !name.isBlank() && name != null;
~~~

The *guard condition* must be placed **before** the expression that depends on it.

### Avoiding integer division by zero

~~~java
int divisor = 0;
boolean valid = divisor != 0 && (12 / divisor > 2); // false.
~~~

If the denominator is 0, Java does not evaluate the division afterward. For readability, parentheses can be added around the right-hand comparison.

This guard pattern is appropriate for **local variables that cannot change unexpectedly between the two checks**. When state is shared across multiple threads, proper synchronization or snapshot reading must be designed; do not assume two reads of a shared field form an atomic transaction.

### Handling nullable `Boolean`

~~~java
Boolean enabled = null;
// boolean disabled = !enabled; // Throws NullPointerException due to unboxing.
boolean enabledSafely = Boolean.TRUE.equals(enabled); // false.
~~~

`!` requires a `boolean`; if the operand is a `Boolean`, Java unboxes it. `null` cannot be unboxed to boolean and throws a `NullPointerException`. `Boolean.TRUE.equals(value)` is a clear check when you only want true for `Boolean.TRUE`.

## 6. Precedence: `!` before `&&` before `||`

Java groups the three operators in order of precedence:

1. `!`: negation.
2. `&&`: short-circuit AND.
3. `||`: short-circuit OR.

~~~java
boolean result = true || false && false; // true.
// Grouped as: true || (false && false).

boolean different = (true || false) && false; // false.
~~~

Parentheses in complex expressions are often worth using even when the compiler already knows the precedence, because they make **the condition's meaning clearer to readers**.

~~~java
boolean canEnter = hasTicket && (!blocked || adult);
~~~

This expresses requiring a ticket **and** (not blocked **or** adult). Removing the parentheses causes `hasTicket && !blocked || adult` to be grouped differently: an adult could bypass the ticket condition, altering the authorization intent.

**Precedence determines grouping**, it does not change evaluation order into "compute parenthesized subexpressions before all operands outside parentheses". In `a || (b && c)`, Java still evaluates `a` first; only when `a` is false does it need to evaluate `b && c`.

## 7. Negation `!` and De Morgan's Laws

`!` inverts a boolean:

~~~java
boolean ready = true;
boolean notReady = !ready; // false.
boolean stillReady = !!ready; // true.
~~~

When negating compound expressions, there are two important rules:

| Expression | Equivalent form |
| --- | --- |
| `!(a && b)` | `!a || !b` |
| `!(a || b)` | `!a && !b` |

These formulas apply to boolean expressions; they also preserve short-circuit behavior and left-to-right evaluation order when transformed properly. For example:

~~~java
boolean isAdult = false;
boolean hasGuardian = true;

boolean rejected = !(isAdult || hasGuardian); // false.
boolean equivalent = !isAdult && !hasGuardian; // false.
~~~

**Common mistake:** `!(a && b)` is **not** equivalent to `!a && !b`. When negating an entire condition, you must flip AND ↔ OR and negate **each operand**.

Additionally, `!` differs from `~`: `~` flips integer bits, whereas `!` negates a boolean. `!0` or `!1` is **invalid** in Java; Java does not treat 0 as false and non-zero numbers as true.

## 8. Combining Conditions in `if` and `while`

~~~java
int age = 20;
boolean hasIdentityCard = true;

if (age >= 18 && hasIdentityCard) {
    System.out.println("eligible");
}
~~~

Use `&&` to express conditions that must all be true together; use `||` for alternative options; use `!` to negate a condition:

~~~java
boolean expired = false;
boolean locked = false;
boolean needsRenewal = expired || locked; // false.
boolean usable = !needsRenewal;          // true.
~~~

They can also be used in `while`, but you must ensure the condition can eventually become false if the loop needs to terminate; short-circuiting **does not automatically guarantee** loop termination.

When a condition gets too long, extract parts into clearly named variables like `hasValidSession`, `hasPermission`, `isBlocked` to reduce stacked negations.

## 9. Common Mistakes

| Misconception | Correct understanding |
| --- | --- |
| "`&&` and `&` with booleans are completely identical." | The logical result is usually the same, but `&` **always evaluates** the right side if no exception occurs |
| "`||` always evaluates both sides." | No, the right side is skipped when the left side is true |
| "`!` negates a number like `!0`." | Type error; `!` requires a boolean |
| "`!a && !b` always equals `!(a && b)`." | Wrong; the correct form is `!a || !b` |
| "`true || false && false` is the same as `(true || false) && false`." | No; the results are true and false respectively |
| "`name != null && name.isBlank()` still calls the method when null." | No; the right side is skipped if null |
| "A null `Boolean` is automatically treated as false." | No; unboxing null throws `NullPointerException` |
| "You can rely on the right side of `&&` to always update a counter." | No; the right side might not be evaluated |
| "The order of AND conditions does not matter." | When exceptions/side effects exist, ordering and guards matter greatly |

## 10. Self-Check Exercises

1. What do `true && false`, `true || false`, and `!true` evaluate to?  
   *Answer:* false, true, false.
2. What does `true || false && false` equal? What if parentheses are added as `(true || false) && false`?  
   *Answer:* true and false.
3. In `false && expensive()`, is the `expensive()` method called?  
   *Answer:* No.
4. In `true | check()` with two boolean operands, is `check()` called?  
   *Answer:* Yes, if evaluation reaches the right-hand side normally.
5. With `String s = null`, does `s != null && !s.isBlank()` throw `NullPointerException`?  
   *Answer:* No; short-circuiting skips the right-hand side.
6. Rewrite `!(isAdmin || isOwner)` using De Morgan's law.  
   *Answer:* `!isAdmin && !isOwner`.
7. What does `Boolean flag = null; boolean b = !flag;` cause?  
   *Answer:* `NullPointerException` during unboxing.
8. Must be an adult **and** (have a ticket **or** have an invitation). Write the condition.  
   *Answer:* `isAdult && (hasTicket || hasInvitation)`.

## Checklist

- [ ] Distinguish `&&` (AND), `||` (OR), and `!` (NOT), all working on booleans.
- [ ] Understand that `&&`/`||` perform **short-circuit evaluation from left to right**.
- [ ] Know that boolean `&` and `|` are **not short-circuiting**.
- [ ] Place guard conditions before accessing nullable values or performing integer division.
- [ ] Remember precedence order: `!` then `&&` then `||`.
- [ ] Apply De Morgan's laws properly when negating compound conditions.
- [ ] Do not use numbers or Strings as booleans; check nullable `Boolean` values.
- [ ] Avoid relying on hidden side effects inside a logical expression.

**Conclusion:** `&&`, `||`, and `!` are the foundation of Java conditional expressions. To use them correctly, memorizing the truth table is not enough—you also need to understand **short-circuit evaluation**, **operator precedence**, **negating compound conditions**, and **null/exception risks**.
