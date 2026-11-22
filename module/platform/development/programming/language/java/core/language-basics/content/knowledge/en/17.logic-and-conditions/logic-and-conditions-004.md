# `&`, `|`, and `^` When Applied to `boolean` — Java 17+

In Java, the operators `&`, `|`, and `^` can combine **two `boolean` values**. Their results also have type `boolean`:

- `a & b`: **AND** — true only when **both** are true.
- `a | b`: **OR** — true when **at least one** operand is true.
- `a ^ b`: **XOR** (*exclusive OR*) — true when **exactly one** of the two operands is true.

**Key takeaway:** with boolean operands, **both sides** of `&`, `|`, and `^` are evaluated if evaluating the left side completes normally—they are **not short-circuiting** like `&&` and `||`.

~~~java
boolean a = true;
boolean b = false;

System.out.println(a & b); // false.
System.out.println(a | b); // true.
System.out.println(a ^ b); // true.
~~~

Do not confuse the single-character forms `&`/`|` with the double-character forms `&&`/`||`. They can produce the **same logical result** while **differing in subexpression execution**, which matters greatly when method calls, `null`, or exceptions are involved.

## 1. Full Truth Table

| `a` | `b` | `a & b` (AND) | `a \| b` (OR) | `a ^ b` (XOR) |
| --- | --- | --- | --- | --- |
| false | false | false | false | false |
| false | true | false | true | true |
| true | false | false | true | true |
| true | true | true | true | false |

**Meaning of XOR:** only **one** condition is allowed to be true, not "one or both".

~~~java
boolean hasPassword = true;
boolean hasOneTimeCode = false;
boolean exactlyOneMethod = hasPassword ^ hasOneTimeCode; // true.

boolean bothMethods = true ^ true; // false.
~~~

With two boolean operands, `a ^ b` yields the same **value** as `a != b`, though `^` can express the XOR intent more clearly in certain situations. It does **not** mean exponentiation. Java does not use `^` to compute `2^3 = 8`; floating-point exponentiation can use `Math.pow(2, 3)`.

## 2. Java 17+ Program Run Directly via CLI

Create a UTF-8 file named **`EagerBooleanOperatorsDemo.java`**:

~~~java
public class EagerBooleanOperatorsDemo {
    static boolean mark(String label, boolean value) {
        System.out.println("eval=" + label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("== truth table ==");
        System.out.println("FF=" + (false & false)
                + "," + (false | false) + "," + (false ^ false));
        System.out.println("FT=" + (false & true)
                + "," + (false | true) + "," + (false ^ true));
        System.out.println("TF=" + (true & false)
                + "," + (true | false) + "," + (true ^ false));
        System.out.println("TT=" + (true & true)
                + "," + (true | true) + "," + (true ^ true));

        System.out.println("== eager evaluation ==");
        boolean eagerAnd = mark("and-left", false)
                & mark("and-right", true);
        System.out.println("eagerAnd=" + eagerAnd);

        boolean eagerOr = mark("or-left", true)
                | mark("or-right", false);
        System.out.println("eagerOr=" + eagerOr);

        boolean xor = mark("xor-left", true)
                ^ mark("xor-right", false);
        System.out.println("xor=" + xor);

        System.out.println("== short circuit ==");
        boolean shortAnd = mark("short-and-left", false)
                && mark("short-and-skipped", true);
        System.out.println("shortAnd=" + shortAnd);

        boolean shortOr = mark("short-or-left", true)
                || mark("short-or-skipped", false);
        System.out.println("shortOr=" + shortOr);

        System.out.println("== precedence ==");
        boolean p = true;
        boolean q = false;
        boolean r = false;
        System.out.println("ungrouped=" + (p | q & r));
        System.out.println("grouped=" + ((p | q) & r));
        System.out.println("notBeforeAnd=" + (!q & p));

        System.out.println("== guard conditions ==");
        String text = null;
        boolean safeText = text != null && !text.isBlank();
        System.out.println("safeText=" + safeText);
        try {
            boolean unsafeText = text != null & !text.isBlank();
            System.out.println("unexpectedText=" + unsafeText);
        } catch (NullPointerException ex) {
            System.out.println("eagerNull=NullPointerException");
        }

        int divisor = 0;
        boolean safeDivide = divisor == 0 || 12 / divisor > 3;
        System.out.println("safeDivide=" + safeDivide);
        try {
            boolean unsafeDivide = divisor == 0 | 12 / divisor > 3;
            System.out.println("unexpectedDivide=" + unsafeDivide);
        } catch (ArithmeticException ex) {
            System.out.println("eagerDivide=ArithmeticException");
        }

        System.out.println("== wrappers and toggle ==");
        Boolean missing = null;
        try {
            boolean unused = true ^ missing;
            System.out.println("unexpectedWrapper=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("xorNull=NullPointerException");
        }

        boolean enabled = false;
        enabled ^= true;
        System.out.println("toggleOne=" + enabled);
        enabled ^= true;
        System.out.println("toggleTwo=" + enabled);
        System.out.println("xorVsNotEqual="
                + ((true ^ false) == (true != false)));

        System.out.println("integerBitwiseXor="
                + (0b1010 ^ 0b1100));
    }
}
~~~

Run on **JDK 17 or later** in PowerShell (Windows) or Bash (Linux/macOS), in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 EagerBooleanOperatorsDemo.java
java EagerBooleanOperatorsDemo
~~~

**Exact expected stdout** of the `java EagerBooleanOperatorsDemo` command alone:

~~~text
== truth table ==
FF=false,false,false
FT=false,true,true
TF=false,true,true
TT=true,true,false
== eager evaluation ==
eval=and-left
eval=and-right
eagerAnd=false
eval=or-left
eval=or-right
eagerOr=true
eval=xor-left
eval=xor-right
xor=true
== short circuit ==
eval=short-and-left
shortAnd=false
eval=short-or-left
shortOr=true
== precedence ==
ungrouped=true
grouped=false
notBeforeAnd=true
== guard conditions ==
safeText=false
eagerNull=NullPointerException
safeDivide=true
eagerDivide=ArithmeticException
== wrappers and toggle ==
xorNull=NullPointerException
toggleOne=true
toggleTwo=false
xorVsNotEqual=true
integerBitwiseXor=6
~~~

The `java -version` and `javac -version` commands show the machine's version info and are not part of the fixed expected stdout block. The `mark` method only helps observe evaluation order; in real code, avoid hiding side effects inside conditions.

## 3. `&` and `&&`: Same AND, Different Evaluation

Both expressions produce the AND result on booleans:

~~~java
boolean a = false;
boolean b = true;

System.out.println(a & b);  // false.
System.out.println(a && b); // false.
~~~

The difference is **whether the right-hand operand is evaluated**.

~~~java
boolean eager = mark("L", false) & mark("R", true);
// Prints eval=L, then eval=R; eager=false.

boolean shortCircuit = mark("L", false) && mark("R", true);
// Prints only eval=L; shortCircuit=false.
~~~

With `&`, if the left expression completes normally, Java still evaluates the right expression even when the left value is false. With `&&`, when the left side is false, the right side does not run.

This can change **logs**, **state**, **API calls**, or **exceptions**, even though the final boolean value is identical.

## 4. `|` and `||`: Same OR, Different Short-Circuiting

~~~java
boolean eager = mark("L", true) | mark("R", false);
// Prints both eval=L and eval=R, eager=true.

boolean shortCircuit = mark("L", true) || mark("R", false);
// Prints only eval=L, shortCircuit=true.
~~~

With `|`, the right-hand operand is still evaluated when the left side is true. With `||`, a true left side already decides the result, so the right side is skipped.

| Left-side condition | `a & b` | `a && b` | `a \| b` | `a || b` |
| --- | --- | --- | --- | --- |
| `a == false` | Evaluates `b` | Skips `b` | Evaluates `b` | Evaluates `b` |
| `a == true` | Evaluates `b` | Evaluates `b` | Evaluates `b` | Skips `b` |

**By default**, use `&&`/`||` for ordinary conditions, especially guard conditions. Only choose `&`/`|` on booleans when evaluating **both** is genuinely required and has been carefully considered.

## 5. `^`: XOR and Both Sides Are Always Evaluated

For booleans, `a ^ b` is true when **exactly one** of the two conditions is true. There is no `^^` operator form in Java.

~~~java
System.out.println(false ^ false); // false.
System.out.println(false ^ true);  // true.
System.out.println(true ^ false);  // true.
System.out.println(true ^ true);   // false.
~~~

`^` always evaluates both operands if the left side completes normally:

~~~java
boolean different = mark("first", true) ^ mark("second", false);
// Prints eval=first, eval=second; different=true.
~~~

A typical use case is checking **exactly one choice**:

~~~java
boolean choseEmail = true;
boolean chosePhone = false;
boolean exactlyOne = choseEmail ^ chosePhone; // true.
~~~

If you want to allow **at least one** choice, use `||` instead of `^`. If you want **both** present, use `&&`.

For two boolean values, `a ^ b` and `a != b` produce the same result. When operands have side effects, both `^` and `!=` evaluate both operands according to Java's rules. However, writing `^` can help readers recognize the "exactly one" concept more clearly.

## 6. Do Not Use `&` or `|` as a Null Guard

Because the right-hand side is always evaluated, using `&` can cause a `NullPointerException`:

~~~java
String name = null;

// Safe: the right side is skipped if name is null.
boolean safe = name != null && !name.isBlank();

// Dangerous:
// boolean wrong = name != null & !name.isBlank();
// Throws NullPointerException.
~~~

Similarly for integer division by 0:

~~~java
int divisor = 0;

// Safe: a true left side causes || to skip the division.
boolean safe = divisor == 0 || 12 / divisor > 3;

// Dangerous:
// boolean wrong = divisor == 0 | 12 / divisor > 3;
// Throws ArithmeticException.
~~~

This is a difference in **evaluation flow**, not in "truth-table correctness". When the second operand can throw an exception, `&`/`|` may fail to return a normal boolean result.

**Concurrency note:** a guard reading a value and an expression accessing the same shared data can be affected by another thread. `&&` itself does not replace synchronization or snapshotting if the program has concurrently mutating data.

## 7. `Boolean` Wrapper and Unboxing

All three operators accept primitive `boolean` expressions or `Boolean` values that can **unbox** to `boolean`.

~~~java
Boolean enabled = Boolean.TRUE;
boolean result = enabled ^ false; // true.
~~~

However, if the wrapper holds `null`, unboxing causes a `NullPointerException`:

~~~java
Boolean missing = null;
// boolean result = true ^ missing; // Throws NullPointerException.
~~~

Do not implicitly assume `Boolean null` is false. Define the business policy explicitly; when you want only `Boolean.TRUE` to count as true:

~~~java
Boolean flag = null;
boolean isEnabled = Boolean.TRUE.equals(flag); // false.
~~~

With `&&`/`||`, a right side containing a null wrapper **can be skipped via short-circuiting**, though if evaluation reaches it and unboxes null, it still throws an exception.

## 8. Precedence and Parentheses

Among the related logical operators, the precedence order from highest to lowest is:

| Relative precedence | Operator |
| --- | --- |
| High | `!` |
| Next | `&` |
| Next | `^` |
| Next | `\|` |
| Next | `&&` |
| Lower | `||` |

Because `&` has higher precedence than `|`:

~~~java
boolean p = true;
boolean q = false;
boolean r = false;

boolean ungrouped = p | q & r;   // true: p | (q & r).
boolean grouped = (p | q) & r;   // false.
~~~

**Precedence determines grouping**, not reversing operand evaluation order. Expressions with multiple operators should use parentheses to state intent clearly rather than forcing readers to memorize every precedence level.

For example, `!a & b` groups as `(!a) & b`, whereas `!(a & b)` negates the entire AND result — these are two different conditions.

## 9. Distinguishing Boolean Logic from Bitwise Operations on Integers

`&`, `|`, and `^` are also supported in Java on **integer types** to manipulate individual bits. The compiler decides which operation to use based on **operand types**.

~~~java
boolean logical = true ^ false; // true, boolean XOR.
int bitwise = 0b1010 ^ 0b1100;  // 0b0110 = 6.
~~~

If both operands are integers, `^` performs bitwise XOR; if both are booleans, `^` performs logical XOR. With boolean operands, `&` and `|` do not turn into integer operations and return `boolean`.

- `&&` and `||` **apply only to booleans**.
- `&`, `|`, and `^` apply to **booleans or suitable integer types**.
- Java does not convert 0 to false or non-zero numbers to true; thus `1 && 2` and `!0` are both invalid.
- `^` is not exponentiation; `Math.pow(...)` is a separate API for floating-point numbers.

### Compound assignment on booleans

Java also has `&=`, `|=`, and `^=`. Example:

~~~java
boolean enabled = false;
enabled ^= true;  // true: toggle.
enabled ^= true;  // false: toggle once again.
~~~

`x ^= true` is one way to flip a `boolean`, though `x = !x` is usually clearer when the sole intent is negating a state. For a complex left-hand expression, compound assignment evaluates the left-hand side once; do not blindly rewrite it into a normal assignment that reads a side-effecting left-hand side twice.

## 10. Common Pitfalls

| Misconception | Correct understanding |
| --- | --- |
| "`&` and `&&` are identical on booleans." | Same truth table, but `&` **does not short-circuit** |
| "`|` and `||` both skip the right side when the left side is true." | Only `||` skips it |
| "`^` is true if at least one condition is true." | `^` is true when **exactly one** condition is true |
| "`^` is integer exponentiation." | `^` is boolean/bitwise XOR |
| "`false & risky()` is safe because the result is already false." | `risky()` is still evaluated |
| "`true | risky()` does not need to run risky." | The right side still runs |
| "`Boolean null` is automatically treated as false." | Unboxing null causes `NullPointerException` |
| "`a | b & c` always groups as `(a | b) & c`." | Actually `a | (b & c)` |
| "Using `&` instead of `&&` works as a null guard." | Can crash due to evaluating the right side |

## 11. Self-Check Exercises

1. What do `true & false`, `true | false`, and `true ^ false` yield?  
   *Answer:* false, true, true.
2. What do `true ^ true` and `false ^ false` yield?  
   *Answer:* Both false.
3. Does `false & check()` evaluate `check()`?  
   *Answer:* Yes if the left side completes normally; the AND result is still false if `check()` returns normally.
4. Does `false && check()` evaluate `check()`?  
   *Answer:* No.
5. How does `true | check()` differ from `true || check()`?  
   *Answer:* `|` evaluates `check()`, while `||` skips it.
6. Given `String s = null`, why is `s != null & !s.isBlank()` unsafe?  
   *Answer:* `&` still evaluates the `isBlank()` call on null.
7. What value does `true | false & false` evaluate to?  
   *Answer:* true, because `&` has higher precedence than `|`.
8. What happens in `Boolean b = null; boolean x = true ^ b;`?  
   *Answer:* Throws `NullPointerException` during unboxing.
9. In `boolean x = false; x ^= true; x ^= true;`, what is the final value of `x`?  
   *Answer:* false.

## Checklist

- [ ] Know that `&` is AND, `|` is OR, and `^` is XOR for booleans.
- [ ] Remember `^` is true only when **exactly one** operand is true.
- [ ] Understand that `&`, `|`, and `^` **evaluate both sides**, without short-circuiting.
- [ ] Distinguish them from `&&` and `||`, especially regarding null guards and exceptions.
- [ ] Watch out for null `Boolean` values throwing `NullPointerException` on unboxing.
- [ ] Know precedence order: `!`, then `&`, `^`, `|`, `&&`, `||`.
- [ ] Distinguish boolean operators from integer bitwise operators.
- [ ] Do not use XOR as exponentiation or ordinary OR.

**Conclusion:** In Java `boolean` expressions, `&`, `|`, and `^` perform AND, OR, and XOR respectively. The core point is that they are **non-short-circuiting**, unlike `&&`/`||`. Choose the right operator based on **condition semantics** and **whether the right side must be evaluated** to avoid subtle bugs with side effects, nulls, and exceptions.
