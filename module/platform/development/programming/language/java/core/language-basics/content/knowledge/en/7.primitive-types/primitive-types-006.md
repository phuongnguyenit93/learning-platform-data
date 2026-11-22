# `boolean` Has Only `true` and `false` in Java

> **Java core — language-basics / Primitive Types**  
> **Environment:** JDK 17 or later, no external libraries required.  
> **Goal:** Understand the two values of primitive `boolean`, how to form conditional expressions, logical operators, and *short-circuiting*; distinguish `boolean` from `Boolean`, which can be `null`.

## 1. The `boolean` Type Represents True or False Conditions

In Java, `boolean` is a **primitive type** that has only **two valid values**:

- `true`: true.
- `false`: false.

~~~java
boolean isReady = true;
boolean isClosed = false;
isReady = false; // Valid: the new value is still boolean.
~~~

The two words `true` and `false` are **boolean literals** in Java source code. They are not the strings `"true"`/`"false"`, and Java **does not** treat the number `1` as true or `0` as false.

~~~java
// Intentionally INVALID lines, do not put into a runnable program:
// boolean ok = 1;       // int cannot be assigned to boolean.
// boolean no = 0;       // int is not implicitly converted to boolean.
// boolean text = "true"; // String is different from boolean.
// boolean missing = null; // primitive boolean does not accept null.
~~~

A `boolean` variable cannot hold a third value such as "unknown." When an undetermined state is needed, use the reference type `Boolean`, which can hold `null`, and handle that state explicitly.

## 2. Expressions Returning `boolean`

The results of comparisons and logical operations typically have type `boolean`:

~~~java
int age = 20;
boolean adult = age >= 18;       // true
boolean exactly20 = age == 20;  // true
boolean notAdult = !adult;      // false
boolean eligible = adult && exactly20; // true
~~~

Commonly used operations:

| Category | Operator | Example and result |
| --- | --- | --- |
| Negation | `!` | `!true` → `false` |
| Short-circuit AND | `&&` | `true && false` → `false` |
| Short-circuit OR | `\|\|` | `true \|\| false` → `true` |
| Logical XOR | `^` | `true ^ false` → `true` |
| Equality/inequality | `==`, `!=` | `true == false` → `false` |
| Numeric comparison | `<`, `<=`, `>`, `>=` | `5 > 3` → `true` |

Simple truth table:

| `a` | `b` | `a && b` | `a \|\| b` | `a ^ b` |
| --- | --- | --- | --- | --- |
| false | false | false | false | false |
| false | true | false | true | true |
| true | false | false | true | true |
| true | true | true | true | false |

The operators `&&`, `||`, and `!` require operands suitable for a boolean context. Java does not allow adding two boolean values or using `<`/`>` operators to compare the order of `true` and `false`.

## 3. `if` and `while` Conditions Must Be `boolean`

Java requires **conditional expressions** to actually have type `boolean` (or `Boolean` that can unbox to boolean):

~~~java
int quantity = 3;

if (quantity > 0) {
    System.out.println("Co hang");
}
~~~

The output is `Co hang`. Do not write `if (quantity)` as in languages that treat any non-zero number as true:

~~~java
// if (quantity) { } // Wrong: quantity is int, not boolean.
// if (1) { }        // Wrong: numeric literal 1 is not a boolean condition.
~~~

**Readability tip:** When a variable `active` is already a `boolean`, writing `if (active)` or `if (!active)` is usually clearer than `if (active == true)` or `if (active == false)`.

## 4. `&&`/`||` Short-Circuit; `&`/`|` Do Not Short-Circuit

With `a && b`, if `a` is `false`, Java **does not evaluate `b`**: the result is already guaranteed to be false. With `a || b`, if `a` is `true`, Java **does not evaluate `b`**: the result is already guaranteed to be true. That is *short-circuiting*.

Conversely, when the operands are boolean, `&` and `|` **evaluate both sides**. `^` also does not short-circuit. This difference is especially important if the right-hand side calls a method with side effects or one that can throw an exception.

Safe example when a reference might be `null`:

~~~java
String name = null;
boolean nonEmpty = name != null && !name.isEmpty();
System.out.println(nonEmpty); // false, does not call name.isEmpty().
~~~

Do not replace `&&` with `&` in that case: the right-hand side would still be evaluated and cause a `NullPointerException`.

## 5. Runnable Java 17+ Program

Create the file **BooleanDemo.java**:

~~~java
public final class BooleanDemo {
    private static boolean sharedFlag;
    private static int checks;

    private static boolean probe() {
        checks++;
        return true;
    }

    public static void main(String[] args) {
        boolean enabled = true;
        boolean blocked = false;
        boolean allowed = enabled && !blocked;

        System.out.println("allowed=" + allowed);
        System.out.println("notAllowed=" + !allowed);
        System.out.println("comparison=" + (5 > 3));

        if (allowed) {
            System.out.println("branch=entered");
        }

        boolean skipAnd = false && probe();
        boolean skipOr = true || probe();
        System.out.println("shortCircuit=" + skipAnd + ","
                + skipOr + ",checks=" + checks);

        boolean eagerAnd = false & probe();
        System.out.println("eagerAnd=" + eagerAnd + ",checks=" + checks);
        System.out.println("xor=" + (true ^ false));

        boolean[] flags = new boolean[2];
        System.out.println("fieldDefault=" + sharedFlag);
        System.out.println("arrayDefault=" + flags[0]);

        Boolean unknown = null;
        System.out.println("wrapperNull=" + (unknown == null));
        System.out.println("parseTrue=" + Boolean.parseBoolean("TrUe"));
        System.out.println("parseOne=" + Boolean.parseBoolean("1"));
    }
}
~~~

Run from the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 BooleanDemo.java
java BooleanDemo
~~~

**Exact expected output:**

~~~text
allowed=true
notAllowed=false
comparison=true
branch=entered
shortCircuit=false,true,checks=0
eagerAnd=false,checks=1
xor=true
fieldDefault=false
arrayDefault=false
wrapperNull=true
parseTrue=true
parseOne=false
~~~

Explanation: `enabled && !blocked` yields true. Both calls to `probe()` in `false && ...` and `true || ...` are skipped, so `checks` remains 0; `false & probe()` **still calls `probe()`**, making `checks` equal 1 even though the AND result is false. New `boolean` arrays and fields are initialized by default to false. `Boolean.parseBoolean("TrUe")` accepts the string case-insensitively; the string `"1"` is **not** interpreted as true.

## 6. How Does `boolean` Differ from `Boolean`?

| Criterion | `boolean` | `Boolean` |
| --- | --- | --- |
| Nature | Primitive type | Reference wrapper class |
| Value of an assigned variable | `true` or `false` | `Boolean.TRUE`, `Boolean.FALSE`, or `null` |
| Uninitialized field | `false` | `null` |
| Element of a new array | `false` in `boolean[]` | `null` in `Boolean[]` |
| Used as a condition | Directly | Java unboxes to `boolean`; if `null`, can throw `NullPointerException` |

Do not confuse "fields have defaults" with **unassigned local variables**. For example, `boolean ready; System.out.println(ready);` inside a method is invalid because `ready` is not *definitely assigned*. Once a local variable is assigned, it can still only hold true/false.

For string input, `Boolean.parseBoolean(text)` returns true only when `text` equals `"true"` (case-insensitive); other strings, including `"1"`, `"yes"`, or `null`, return false. If you need to report an error on invalid input, **validate the input yourself** rather than assuming every value parsed as false means the user chose false.

## 7. Common Mistakes and Exercises

| Mistake | Correct understanding |
| --- | --- |
| `boolean b = 1;` | Java does not implicitly convert numbers to boolean |
| `if (number)` with `number` of type `int` | Must write a boolean expression, e.g., `number != 0` |
| `boolean b = "false";` | A string differs from the literal `false` |
| `Boolean b = null; if (b) { ... }` | Auto-unboxing `null` can throw `NullPointerException` |
| Replacing `&&` with `&` when null-guarding | `&` still evaluates the right-hand side |
| Mistaking `Boolean.parseBoolean("yes")` for true | The result is false |

**Exercise 1.** Predict `!false`, `true && false`, `true || false`, and `true ^ true`. Explain using the truth table.

**Exercise 2.** Create a variable `int amount = 0;` and a variable `boolean hasAmount = amount > 0;`. Try putting `amount` directly into an `if` condition to observe the compile error.

**Exercise 3.** In `BooleanDemo.java`, change `false && probe()` to `true && probe()`, then predict `checks` right after the two short-circuit expressions and after the `&` expression.

**Exercise 4.** Write a check for `String value = null;` using `value != null && !value.isBlank()`. Predict what happens if `&` is used instead of `&&`.

**Exercise 5.** Create `Boolean unknown = null;` and try `Boolean.TRUE.equals(unknown)` to compare safely without unboxing a null value.

### Key Takeaways

**`boolean` only has `true` and `false`; Java has no rule that "0 is false, non-zero is true."** Comparisons produce booleans, `if`/`while` require boolean conditions, and `&&`/`||` short-circuit. `Boolean` is a **reference wrapper** that can hold `null`, so do not equate it with primitive `boolean`.
