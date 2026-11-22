# `if`, `else`, and `else if` Chain Syntax — Java 17+

`if` is a **conditional branching** statement: the program evaluates a `boolean` expression and runs only the matching block. You can write a single `if`, add an `else` branch, or chain cases with `else if`.

~~~java
int age = 20;

if (age >= 18) {
    System.out.println("Adult");
} else {
    System.out.println("Minor");
}
~~~

In this example, the condition `age >= 18` is `true`, so only the first branch runs. There is no automatic fall-through into the `else` branch.

## 1. Three fundamental syntactic forms

### Form 1 — `if` only

~~~java
int quantity = 3;

if (quantity > 0) {
    System.out.println("In stock");
}
~~~

If the condition is false, the block is skipped; the program continues at the statement after `if`. **`else` is optional**.

### Form 2 — `if / else`

~~~java
int balance = 50;

if (balance >= 100) {
    System.out.println("Sufficient funds");
} else {
    System.out.println("Insufficient funds");
}
~~~

Chooses **one of two** blocks. `else` has no condition of its own: it is selected when the `if` condition is false.

### Form 3 — `if / else if / else` chain

~~~java
int score = 83;

if (score >= 90) {
    System.out.println("A");
} else if (score >= 75) {
    System.out.println("B");
} else if (score >= 60) {
    System.out.println("C");
} else {
    System.out.println("D");
}
~~~

Java evaluates the conditions **from top to bottom**. When it encounters the first true condition, it runs the corresponding branch and **skips all remaining branches**. The final `else` is the default branch and can be omitted if not needed.

**`else if` is not a separate compound keyword:** syntactically, it is an `else` followed by an `if` statement; writing them inline forms a multi-case chain.

## 2. Branch selection flowchart

~~~mermaid
flowchart TD
    Start["Start"] --> C1{"Condition 1?"}
    C1 -- true --> B1["Run if branch"]
    C1 -- false --> C2{"Condition 2?"}
    C2 -- true --> B2["Run else if branch"]
    C2 -- false --> B3["Run else (if present)"]
    B1 --> End["Statement after chain"]
    B2 --> End
    B3 --> End
~~~

The diagram illustrates one `else if`. You can add more `else if` branches in the same way; the rule remains **the first true branch wins**.

| Structure | Conditions evaluated | Branches that can run in a single pass |
| --- | --- | --- |
| `if (c) {...}` | One condition | 0 or 1 |
| `if (c) {...} else {...}` | One condition | Exactly 1 if the condition completes normally |
| `if (a) {...} else if (b) {...} else {...}` | `a` then `b` sequentially when needed | Exactly 1 if `else` is present and no exception occurs |
| Two independent `if` statements | Each statement has its own condition | Both may run |

If an exception is thrown while evaluating a condition, the chain does not complete along the normal path; the table above assumes conditions evaluate successfully.

## 3. Compilable and runnable Java 17+ program

This example focuses on the three syntactic forms just covered. Techniques such as nullable `Boolean`, independent `if` statements, blocks, and guard clauses are practiced separately in subsequent lessons.

Create a UTF-8 file named **`IfElseChainDemo.java`**:

~~~java
public class IfElseChainDemo {
    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "invalid";
        }
        if (score >= 90) {
            return "A";
        } else if (score >= 75) {
            return "B";
        } else if (score >= 60) {
            return "C";
        } else {
            return "D";
        }
    }

    public static void main(String[] args) {
        System.out.println("== if ==");
        int stock = 3;
        if (stock > 0) {
            System.out.println("stock=available");
        }

        System.out.println("== if / else ==");
        int age = 20;
        if (age >= 18) {
            System.out.println("age=adult");
        } else {
            System.out.println("age=minor");
        }

        System.out.println("== else if ==");
        for (int score : new int[] {95, 75, 60, 59, -1, 101}) {
            System.out.println(score + "=" + grade(score));
        }
        System.out.println("end");
    }
}
~~~

In the directory containing the file, use **JDK 17 or later** with PowerShell or Bash:

~~~bash
javac -encoding UTF-8 IfElseChainDemo.java
java IfElseChainDemo
~~~

**Exact expected stdout** of the command `java IfElseChainDemo`:

~~~text
== if ==
stock=available
== if / else ==
age=adult
== else if ==
95=A
75=B
60=C
59=D
-1=invalid
101=invalid
end
~~~

All three forms can run independently. `grade` also validates out-of-range scores before classifying, preventing invalid inputs from being assigned a grade label.

## 4. `if` condition: boolean, not truthiness

Java only accepts conditional expressions of type `boolean` or `Boolean` that can be **unboxed**. Numbers, strings, or objects are not automatically converted to true/false:

~~~java
int count = 3;
if (count > 0) {
    System.out.println("has items");
}
// if (count) { } // Compile error: int is not boolean.
~~~

A `Boolean` variable can be null; `if (nullableFlag)` will throw `NullPointerException` during unboxing if its value is null. To accept only true, use `Boolean.TRUE.equals(nullableFlag)`; with `String`, guarding with `s != null && !s.isBlank()` avoids calling methods on null.

Be careful with `if (flag = true)`: this is a **boolean assignment**, which compiles and causes the branch to run rather than being a pure check. Nullable `Boolean`, unboxing, conditional expressions, and short-circuiting are explained in depth in the dedicated `boolean/Boolean` lesson.


## 5. First true branch wins: order conditions intentionally

For scores from 0 to 100, you must check **narrower/higher thresholds** before broader/lower ones:

~~~java
if (score >= 90) {
    level = "A";
} else if (score >= 75) {
    level = "B";
} else if (score >= 60) {
    level = "C";
} else {
    level = "D";
}
~~~

If reversed to `if (score >= 60) ... else if (score >= 90)`, a score of 95 enters the first branch and is misclassified. In the main program, `grade` also checks `score < 0 || score > 100` before grading.

When defining classification rules, determine the valid domain, **priority branches**, and exact boundary values. The boundary conditions lesson builds a test table right below, at, and above thresholds and analyzes shadowed branches.


## 6. Multiple independent `if` statements can all run

~~~java
int value = 5;
if (value > 0) {
    System.out.println("positive");
}
if (value < 10) {
    System.out.println("below ten");
}
~~~

Both conditions are true, so both lines are printed. If you change the second `if` to `else if`, it is **not evaluated** after the first branch runs. Use multiple `if` statements when multiple actions are needed together; use a single `else if` chain when choosing only **one** action/label.

This rule also affects **whether subsequent conditions are evaluated**, especially if they contain method calls with side effects. The dedicated lesson comparing independent `if` statements and exclusive chains analyzes behavior tables, cumulative alerts, and execution traces of both approaches.


## 7. Braces define the exact branch body

~~~java
boolean authorized = false;
if (authorized)
    System.out.println("authorized");
System.out.println("always"); // Always runs.
~~~

When omitting `{}`, only **a single statement** immediately following the condition belongs to the `if` body; indentation does not change syntax. With nested `if` statements, `else` binds to the nearest `if` that does not yet have an `else`:

~~~java
if (outer) {
    if (inner) {
        System.out.println("inner true");
    } else {
        System.out.println("inner false");
    }
}
~~~

Use braces even when there is only one statement to protect scope and prevent bugs when code is added later. Do not place an extra `;` after `if (condition)`, because `;` can become an **empty statement**, making the `if` body empty. Two dedicated lessons on blocks and `dangling else` cover variable scope, `else` pairing rules, and logic-bug examples in detail.


## 8. Early `return` for conclusive cases

A method can **return immediately** once the result is known, avoiding nesting every case into multiple branches:

~~~java
static String sign(int n) {
    if (n > 0) {
        return "positive";
    }
    if (n < 0) {
        return "negative";
    }
    return "zero";
}
~~~

The two `if` statements here do not need `else if` because `return` exits the method in the chosen branch. However, if the earlier branch does **not `return`/`throw`**, replacing `else if` with an independent `if` can change behavior. Use guard clauses when you need to reject invalid cases or exit early before the main processing path; the guard clause lesson dives into ordering, exceptions, loops, and resource cleanup.


## 9. Common mistakes

| Misconception | Correct understanding |
| --- | --- |
| “`if (1)` is valid because 1 means true.” | Java requires `boolean`; there is no truthiness for numbers |
| “`else` is mandatory after every `if`.” | `else` is optional |
| “Every `else if` is executed to find all true branches.” | Only checks up to the **first true branch** |
| “Two consecutive `if` statements are the same as `if / else if`.” | Two independent `if` statements can both run |
| “Condition order does not matter.” | A broad condition placed first can shadow specific conditions |
| “`if (flag = true)` is equivalent to checking flag.” | It is an assignment to true, which can introduce a bug |
| “`Boolean null` is automatically treated as false.” | Unboxing null causes `NullPointerException` |
| “If braces are omitted, all indented lines belong to `if`.” | Only **one statement** immediately after the condition |
| “`else` always binds to the outermost `if`.” | Binds to the nearest `if` without an `else` |
| “`if (condition);` has a conditional block after it.” | The `;` turns the `if` body into an empty statement |

## 10. Self-check exercises

1. `int x = 7; if (x > 5) {...} else {...}` runs which branch?  
   *Answer:* The `if` branch.
2. `int x = 5; if (x > 0) {...} if (x < 10) {...}` can run how many branches?  
   *Answer:* Both.
3. With `score = 95`, why does `if (score >= 60) ... else if (score >= 90) ...` fail the classification intent?  
   *Answer:* The `>= 60` branch is already true, so `>= 90` is never evaluated.
4. Does `if (0)` compile?  
   *Answer:* No; the condition must have a boolean type.
5. What happens at runtime for `Boolean b = null; if (b) {...}`?  
   *Answer:* Throws `NullPointerException` due to unboxing.
6. What does `if (n > 0);` do?  
   *Answer:* The condition is evaluated, but the body is an **empty statement**.
7. With two nested `if` statements without braces, which branch does `else` bind to?  
   *Answer:* The nearest `if` that does not yet have an `else`.
8. Can an `else if` chain end without an `else`?  
   *Answer:* Yes; if no branch is true, no block runs.

## Checklist

- [ ] Write `if (booleanCondition) { ... }` correctly.
- [ ] Know that `else` is optional and `else if` appends cases in order.
- [ ] Understand that **only the first true branch** in a chain runs.
- [ ] Distinguish multiple independent `if` statements from an `else if` chain.
- [ ] Check `boolean` types, nullable wrappers, and short-circuiting conditions.
- [ ] Place specific conditions before broad conditions when they overlap.
- [ ] Always prefer braces to avoid `dangling else` bugs and misleading indentation.
- [ ] Do not accidentally add `;` right after `if (...)` or use assignment `=` instead of a check.

**Conclusion:** `if`, `else`, and `else if` chains are Java's core branching tools. Reading **boolean conditions**, **evaluation order**, **brace scope**, and **branch relationships** accurately helps prevent logic bugs that the compiler will not necessarily catch.