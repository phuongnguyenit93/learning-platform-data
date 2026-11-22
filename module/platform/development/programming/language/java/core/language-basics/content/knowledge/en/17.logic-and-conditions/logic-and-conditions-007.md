# Ternary Operator `?:` and Evaluating Only the Selected Branch — Java 17+

**The conditional operator `?:`** (*conditional operator*, commonly called the *ternary operator*) selects **one of two result expressions** based on the value of a `boolean` condition.

~~~java
int score = 85;
String level = score >= 80 ? "Good" : "Needs improvement";
// level = "Good".
~~~

Syntax:

~~~text
condition ? expressionIfTrue : expressionIfFalse
    (1)            (2)                 (3)
~~~

- **(1) Condition** is evaluated first and must have type `boolean` or an unboxable `Boolean`.
- **(2) True branch** is evaluated only when the condition returns true.
- **(3) False branch** is evaluated only when the condition returns false.
- **The unselected branch does NOT run**: no method calls, no side effects, and no exceptions thrown from that branch.

For example, `boolean premium = true; int fee = premium ? 0 : 30_000;` assigns 0 to `fee` without needing a verbose `if/else` block.

## 1. Evaluation Rules and Result Table

| Condition | Branch evaluated | Branch skipped | Value of entire expression |
| --- | --- | --- | --- |
| `true` | After `?` | After `:` | Value of the true branch |
| `false` | After `:` | After `?` | Value of the false branch |
| `Boolean null` | None | Both | Throws `NullPointerException` when unboxing condition |
| Condition itself throws an exception | None | Both | Expression terminates abruptly with the exception |

Flow diagram:

~~~mermaid
flowchart TD
    A["Evaluate condition"] --> B{"Is condition true?"}
    B -- "Yes" --> C["Evaluate only branch after ?"]
    B -- "No" --> D["Evaluate only branch after :"]
    C --> E["Value of ?: expression"]
    D --> E
~~~

**Important difference from method calls:** `choose(condition, positive(), negative())` evaluates **both arguments** `positive()` and `negative()` before invoking `choose`. In contrast, `condition ? positive() : negative()` evaluates only **one** of the two branch expressions.

## 2. Standalone Java 17+ Demo with Expected Stdout

Create a UTF-8 file named **`TernaryBranchDemo.java`**:

~~~java
public class TernaryBranchDemo {
    static boolean test(String label, boolean result) {
        System.out.println("test=" + label);
        return result;
    }

    static int mark(String label, int value) {
        System.out.println("eval=" + label);
        return value;
    }

    static int fail() {
        System.out.println("eval=failing");
        throw new IllegalStateException("boom");
    }

    public static void main(String[] args) {
        boolean premium = true;
        int fee = premium ? 0 : 30_000;
        System.out.println("fee=" + fee);

        boolean accepted = false;
        String status = accepted ? "accepted" : "rejected";
        System.out.println("status=" + status);

        System.out.println("== selected branch ==");
        int first = test("condition-true", true)
                ? mark("true-branch", 10)
                : mark("skipped-false-branch", 20);
        System.out.println("first=" + first);

        int second = test("condition-false", false)
                ? mark("skipped-true-branch", 30)
                : mark("false-branch", 40);
        System.out.println("second=" + second);

        System.out.println("== exception behavior ==");
        int safeTrue = true ? mark("safe-true", 5) : fail();
        System.out.println("safeTrue=" + safeTrue);

        int safeFalse = false ? fail() : mark("safe-false", 6);
        System.out.println("safeFalse=" + safeFalse);

        try {
            int unused = true ? fail() : mark("never", 99);
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("== types and null ==");
        var mixedNumeric = true ? 1 : 2.5;
        System.out.println("mixedNumeric=" + mixedNumeric);

        String optionalText = false ? "text" : null;
        System.out.println("nullResult=" + (optionalText == null));

        Integer missingNumber = null;
        int safeNumber = true ? 7 : missingNumber;
        System.out.println("safeNumber=" + safeNumber);

        Boolean missingCondition = null;
        try {
            String unexpected = missingCondition ? "yes" : "no";
            System.out.println("unexpected=" + unexpected);
        } catch (NullPointerException ex) {
            System.out.println("nullCondition=NullPointerException");
        }

        System.out.println("== nesting and state ==");
        boolean mainRoute = false;
        boolean backupRoute = true;
        String route = mainRoute
                ? "main"
                : backupRoute ? "backup" : "off";
        System.out.println("route=" + route);

        int counter = 0;
        int choice = (++counter == 1) ? 8 : 9;
        System.out.println("choice=" + choice + ",counter=" + counter);

        int visits = 0;
        int onlyOne = false
                ? (visits += 10)
                : (visits += 1);
        System.out.println("onlyOne=" + onlyOne + ",visits=" + visits);

        double nan = Double.NaN;
        String nanResult = nan > 0.0 ? "positive" : "not-positive";
        System.out.println("nanResult=" + nanResult);

        System.out.println("== grouping ==");
        int grouped = (true ? 2 : 3) + 4;
        System.out.println("grouped=" + grouped);
        boolean allowed = true || false;
        String access = allowed ? "allow" : "deny";
        System.out.println("access=" + access);
    }
}
~~~

Requires **JDK 17 or later**; open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 TernaryBranchDemo.java
java TernaryBranchDemo
~~~

**Exact expected stdout** from the `java TernaryBranchDemo` command alone:

~~~text
fee=0
status=rejected
== selected branch ==
test=condition-true
eval=true-branch
first=10
test=condition-false
eval=false-branch
second=40
== exception behavior ==
eval=safe-true
safeTrue=5
eval=safe-false
safeFalse=6
eval=failing
caught=boom
== types and null ==
mixedNumeric=1.0
nullResult=true
safeNumber=7
nullCondition=NullPointerException
== nesting and state ==
route=backup
choice=8,counter=1
onlyOne=1,visits=1
nanResult=not-positive
== grouping ==
grouped=6
access=allow
~~~

The `java -version` and `javac -version` commands produce machine-dependent output and are not part of the fixed stdout block. This example has been verified against Java 17 semantics; you can use the commands above to compile and verify it yourself.

## 3. Why Is Only One Branch Evaluated?

~~~java
int value = true ? mark("YES", 1) : mark("NO", 2);
~~~

When the condition is true, the program only calls `mark("YES", 1)`, takes the value 1, and finishes. There is no call to `mark("NO", 2)`.

This is especially important for **side effects**:

~~~java
int count = 0;
int value = false ? (count += 10) : (count += 1);
// value = 1, count = 1; the +10 branch does not run at all.
~~~

And for **exceptions**:

~~~java
int result = true ? 5 : (10 / 0);
// The division in the unselected branch is not evaluated.
~~~

To demonstrate runtime safety, the division expression in the example above can be replaced by dividing by a variable holding 0; Java still skips that branch. If the **selected branch** throws an exception, the entire `?:` expression terminates abruptly and produces no normal value. If the **condition itself** throws an exception, neither branch has been evaluated yet.

Do not rely on a skipped branch to perform mandatory work. If an operation must run regardless of the condition, place it in a separate statement **before or after** the expression.

## 4. Both Branches Affect the Result Type

Even though only one branch runs, the **compiler still checks both branches to determine the type** of `?:`. When mixing numeric values, the selected branch may be converted to a common type:

~~~java
var mixed = true ? 1 : 2.5;       // double, value 1.0
String note = false ? "text" : null; // null reference
Integer missing = null;
int safe = true ? 7 : missing;    // 7; does not unbox the skipped branch
~~~

If a null `Integer` branch is selected in an `int`/`Integer` numeric pair, unboxing can throw `NullPointerException`; a null `Boolean` condition also fails before selecting a branch. For reference branches, the target type of an assignment can sometimes affect type checking too. Those promotion rules, `byte`/`short` constants, boxing, and target typing are analyzed with dedicated examples in the lesson **Result Type of Conditional Expressions and Possible Conversions**.

## 5. Precedence, Associativity, and Nested Ternaries

`?:` has **lower** precedence than many arithmetic, comparison, and `&&`/`||` logical operators, but **higher** precedence than assignment `=`.

~~~java
int score = 80;
String rank = score >= 75 && score < 90 ? "good" : "other";
// Condition: (score >= 75 && score < 90).
~~~

Parentheses often make the code's intent clearer:

~~~java
String rank = (score >= 75 && score < 90)
        ? "good" : "other";
~~~

**The conditional operator is right-associative** when nested:

~~~java
String route = mainRoute ? "main"
        : backupRoute ? "backup" : "off";
~~~

It is grouped equivalently to:

~~~java
String route = mainRoute
        ? "main"
        : (backupRoute ? "backup" : "off");
~~~

Only when `mainRoute` is false is the `backupRoute` condition evaluated. If `mainRoute` is true, the entire right-hand ternary is skipped. With three or more nesting levels, **`if/else if/else` is usually more readable**.

## 6. When to Use `?:` vs. `if/else`?

Use `?:` for a **short, clear value selection**:

~~~java
int max = a > b ? a : b;
String label = enabled ? "ON" : "OFF";
~~~

If the goal involves multiple statements, logging, state updates, or catching exceptions, use `if/else`:

~~~java
String label;
if (enabled) {
    label = "ON";
} else {
    label = "OFF";
}
~~~

Key differences to remember:

| Feature | `?:` | `if/else` |
| --- | --- | --- |
| Construct | **Expression** producing a value | Control-flow **statement** |
| Best suited for | Selecting one short result | Multiple actions, multiple branches, or error handling |
| Evaluation | Only the selected branch | Only the matching block executes |
| Two value branches | Must obey conditional-expression typing rules | Each branch can contain different statements |
| Calling `void` methods in both branches | Invalid as the two result expressions of `?:` | Completely valid inside both blocks |

**Common syntax mistake:** `?:` is not a *statement expression* that can stand alone as a statement `condition ? f() : g();`. If you only want to call one of two methods, use `if/else`; if you want to choose a **value** to assign or pass to a method, `?:` is appropriate.

## 7. How Does `?:` Compare to `&&`/`||` Short-Circuiting?

All three mechanisms can **skip evaluating part of an expression**, but they serve different purposes:

| Construct | Skipped part | Result type |
| --- | --- | --- |
| `a && b` | Skips `b` when `a` is false | `boolean` |
| `a \|\| b` | Skips `b` when `a` is true | `boolean` |
| `cond ? x : y` | Skips **one of the two** branches `x`, `y` | Depends on both branch types and context |

Example choosing between two methods with **return values**:

~~~java
int result = valid ? calculateFast() : calculateFallback();
~~~

When `valid` is true, only `calculateFast()` is called; when false, only `calculateFallback()` is called. These two example methods are illustrative and must be declared in an actual program; the runnable program in section 2 uses the fully defined `mark` and `fail` methods.

Do not replace this with `choose(valid, calculateFast(), calculateFallback())` if you want to preserve branch-skipping behavior: Java evaluates call arguments left to right, meaning **both calculation methods** would run before `choose` receives the values.

## 8. Common Mistakes

| Misconception | Reality |
| --- | --- |
| "`?:` always runs both branches and then picks a result." | Only the selected branch is evaluated |
| "If the skipped branch would throw an exception, the ternary still fails." | The unselected branch is not executed |
| "`Boolean null` is interpreted as false." | Unboxing null in the condition throws `NullPointerException` |
| "A ternary's type is always the type of the executed branch." | The type is decided at compile time, considering both branches and context |
| "`true ? 1 : 2.5` has type int because 1 is selected." | The result has type `double` and value `1.0` |
| "`a ? b : c ? d : e` always groups from the left." | `?:` is right-associative |
| "Very long ternaries are easier to read than `if/else`." | Multiple nesting levels are usually hard to inspect |
| "`?:` can be used for two `void` calls as a statement." | No; use `if/else` |
| "Creating `choose(flag, first(), second())` has the same lazy evaluation." | Wrong; both arguments are evaluated |

## 9. Self-Check Exercises

1. What value does `int x = true ? 10 : 20;` give `x`?  
   *Answer:* 10.
2. What string does `boolean ok = false; String s = ok ? "Y" : "N";` produce?  
   *Answer:* `"N"`.
3. Does `int n = true ? 5 : (10 / 0);` perform the division?  
   *Answer:* No; the third branch is skipped.
4. In `var x = true ? 1 : 2.5;`, what are the type and value of `x`?  
   *Answer:* `double`, `1.0`.
5. What happens in `Boolean flag = null; int n = flag ? 1 : 2;`?  
   *Answer:* Throws `NullPointerException` when evaluating the condition.
6. What string does `boolean a = false, b = true; String s = a ? "A" : b ? "B" : "C";` produce?  
   *Answer:* `"B"`.
7. If the unselected branch increments a counter variable, does that variable change?  
   *Answer:* No.
8. When you need to call one of two `void` methods with lengthy logic, what should you use?  
   *Answer:* `if/else`.

## Checklist

- [ ] Know the syntax `condition ? trueExpr : falseExpr` and that the condition type is boolean.
- [ ] Remember **only one result branch is evaluated** after the condition.
- [ ] Know that the condition or the selected branch can throw an exception; the unselected branch does not run.
- [ ] Understand that the whole expression's type is determined at compile time, independent of the actual runtime branch.
- [ ] Watch out for null `Boolean` conditions and unboxing of numeric wrapper branches.
- [ ] Understand `?:` is right-associative and add parentheses when nesting.
- [ ] Use `?:` for short value selection, and `if/else` for complex control flow.
- [ ] Do not confuse `?:` with a method call that receives both precomputed results.

**Conclusion:** `?:` provides a concise way to express choosing between two values, but its most important trait is **evaluating only the selected branch**. Once you also understand **expression typing**, **null**, **exceptions**, and **nested grouping**, you can use the ternary operator accurately and readably in Java 17+.
