# Name Scope in Blocks, Loops, and Methods — Java 17+

> **Java core — language-basics / Scope and Initialization**  
> **Objective:** Determine where a variable/parameter name can be used, why a loop variable name cannot be used outside the loop, when a name can be reused, and distinguish **name scope** from **definite assignment**.

## 1. What is name scope?

*Scope* is **the region of source code in which a name declaration is in effect to refer to that entity**. For a local variable declared in a statement block, the normal scope extends from the declaration position to the end of the enclosing block; it does not automatically extend beyond the closing brace `}`.

~~~java
static void example() {
    int outer = 10;
    {
        int inner = 5;
        System.out.println(outer + inner); // 15: both names are visible.
    }
    System.out.println(outer); // 10.
    // System.out.println(inner); // COMPILE ERROR: inner is out of scope.
}
~~~

Braces `{ ... }` can open a block in a method, an `if` branch, a loop body, or `try`. Scope rules restrict where a name can be used; they do **not** mean the object referenced by a variable is necessarily destroyed as soon as execution leaves the block.

Three useful questions when encountering a `cannot find symbol` error:

1. Has the name been declared **before the usage site** and within the visible region?
2. Is the name a **local variable**, **parameter**, **loop variable**, or **class/object field**?
3. If the name is visible, has the variable been **definitely assigned** before being read?

## 2. Statement blocks `{ }`: outer variables are visible inside, inner variables cannot escape outside

~~~java
int total = 0;

if (total == 0) {
    int adjustment = 3;
    total += adjustment; // Can modify total from the outer block.
}
System.out.println(total); // 3.
// System.out.println(adjustment); // ERROR: adjustment is out of scope.
~~~

Within a block, a local variable's name is in scope from **its declaration** onward, not from the beginning of the block:

~~~java
{
    // System.out.println(score); // ERROR: score has not been declared yet.
    int score = 8;
    System.out.println(score); // Valid.
}
~~~

Two **non-overlapping** blocks can redeclare the same name:

~~~java
{
    int temp = 7;
    System.out.println(temp);
}
{
    int temp = 8; // Valid: the previous temp is out of scope.
    System.out.println(temp);
}
~~~

However, Java **does not allow redeclaring a local variable with the same name in overlapping scopes**, even in a nested block:

~~~java
// DOES NOT COMPILE:
// int count = 1;
// {
//     int count = 2; // Outer name count is still in effect.
// }
~~~

This is an important difference from *field shadowing* by a local variable, which is covered in Section 6.

## 3. Variables in a standard `for` loop

A variable declared in the **initialization** part of `for` can be used in the condition, update, and loop body; it is no longer in effect after the `for` statement:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("i=" + i);
}
// System.out.println(i); // COMPILE ERROR: i is out of scope.
~~~

The same variable name can be reused in two independent, sequential `for` loops:

~~~java
for (int i = 0; i < 2; i++) {
    System.out.print(i); // 01.
}
for (int i = 2; i < 4; i++) {
    System.out.print(i); // 23.
}
~~~

However, you cannot declare `int i` in a `for` loop inside the body of another `for` loop while the outer loop's `i` is still in scope:

~~~java
// DOES NOT COMPILE:
// for (int i = 0; i < 2; i++) {
//     for (int i = 0; i < 3; i++) { } // i is declared twice.
// }
~~~

For nested iteration, use different names such as `row` and `column`. If you declare the variable **before** the loop, it belongs to the enclosing block's scope, so it can be read after the loop:

~~~java
int i = 0;
for (; i < 3; i++) {
    // The body can use i.
}
System.out.println(i); // 3: i was declared outside the for loop.
~~~

## 4. Enhanced `for` and variables declared in the loop body

With an enhanced `for`, the element variable `element` is declared in the loop header and used in the loop **body**:

~~~java
for (String word : new String[] {"A", "B"}) {
    System.out.println(word);
}
// System.out.println(word); // ERROR: word does not exist here.
~~~

The source expression to the right of `:` **cannot use the newly declared element variable** as an already-existing name. On each iteration, this variable receives the corresponding element value. If the source contains a reference type, the received value is a **reference copy**, which does not extend scope outside the loop.

In a `for`/`while` body, a newly declared variable can only be used in that body or an appropriate nested block:

~~~java
int sum = 0;
for (int n = 1; n <= 3; n++) {
    int part = n * 2;
    sum += part;
}
// System.out.println(part); // ERROR: part is inside the loop body.
// System.out.println(n);    // ERROR: n belongs to the for scope.
System.out.println(sum); // 12: sum is declared outside.
~~~

If you need a result after iterating, declare the result variable in an **enclosing** block, like `sum`, and update it inside the loop. Avoid trying to read a temporary variable declared only inside the loop body.

## 5. `while`, `if`, and method parameters

A local variable created in a `while` body has scope restricted to that body; a control variable declared outside remains visible after the loop:

~~~java
int turn = 0;
while (turn < 2) {
    int step = turn + 10;
    System.out.println(step); // 10 then 11.
    turn++;
}
// System.out.println(step); // ERROR: out of scope.
System.out.println(turn); // 2.
~~~

In `if`/`else`, a variable declared **inside a branch** is visible only in that branch. If a shared result is needed, declare the variable in the enclosing block and assign it in the branches:

~~~java
static int choose(boolean flag) {
    int result;
    if (flag) {
        result = 1;
    } else {
        result = 2;
    }
    return result; // Both branches assigned it.
}
~~~

Formal parameters of a method have scope throughout **that method's body**, including nested blocks inside it; they do not appear in the caller or other methods:

~~~java
static String format(int input) {
    String prefix = "P";
    return prefix + input;
}
// In another method, you cannot directly use the names input or prefix.
~~~

You cannot declare `int input` in a nested block of `format` itself because the parameter name `input` is still in effect. Different methods can use the same parameter names without conflict.

## 6. Object fields and name *shadowing*

The scope of a **field** differs from local scope: in an instance method, a parameter or local variable is allowed to have the same name as a field. In that case, the short name selects the closer variable, while `this.count` refers specifically to the object's field:

~~~java
class Counter {
    private int count = 100;
    void show() {
        int count = 3;
        System.out.println(count);      // 3: local
        System.out.println(this.count); // 100: instance field
    }
}
~~~

For a `static` field, write `ClassName.field` to distinguish it from a local with the same name; in a `static` method there is no `this`. Overlapping **local-local** declarations are still forbidden, even though a local matching a field name is valid. The lesson on *parameters/local variables shadowing fields* examines the self-assignment bug `value = value;` and how to fix it in detail.

## 7. Scope differs from *definite assignment* and data lifetime

A name can be **visible**, yet **reading the local variable is still disallowed** if Java cannot prove it has been assigned a value:

~~~java
// DOES NOT COMPILE:
// static int bad(boolean condition) {
//     int result;
//     if (condition) {
//         result = 1;
//     }
//     return result; // Path condition=false leaves it unassigned.
// }
~~~

In the `choose` example in Section 5, both `if` and `else` branches assign `result` before `return`, so it compiles successfully.

| Concept | Question to answer |
| --- | --- |
| **Scope** | Can the declared **name** be referenced at this location? |
| **Definite assignment** | Before **reading the local variable's value**, have all paths to this point assigned it? |
| **Lifetime** | How long does the associated value, memory slot, or object continue to exist? |

Each invocation of a regular method creates its own call context for parameters and local variables. If a reference to an object is returned, that object **can continue to exist** after the local variable name goes out of scope; garbage collection timing is not determined solely by a closing brace `}`.

`final` prevents reassigning a variable after it has been assigned according to Java rules, but it **does not extend scope** and does not by itself make a mutable object immutable. Pattern variables in `instanceof`/`switch` have their own control-flow-based scoping rules; simple block rules should not be applied mechanically to them.

## 8. Standalone Java 17+ program

Create the file **ScopeBlocksDemo.java**:

~~~java
public final class ScopeBlocksDemo {
    private static int shared = 50;
    private int count = 100;

    private static int increment(int number) {
        int result = number + 1;
        return result;
    }

    private static String format(int input) {
        String prefix = "P";
        return prefix + input;
    }

    private static int choose(boolean flag) {
        int result;
        if (flag) {
            result = 1;
        } else {
            result = 2;
        }
        return result;
    }

    private void demonstrate() {
        int count = 3;
        System.out.println("localCount=" + count);
        System.out.println("fieldCount=" + this.count);

        {
            int inside = 5;
            System.out.println("inside=" + inside);
        }

        {
            int temp = 7;
            System.out.println("siblingA=" + temp);
        }
        {
            int temp = 8;
            System.out.println("siblingB=" + temp);
        }

        for (int i = 0; i < 3; i++) {
            System.out.println("forIndex=" + i);
        }

        for (String item : new String[] {"A", "B"}) {
            System.out.println("item=" + item);
        }

        int total = 0;
        for (int i = 1; i <= 3; i++) {
            int part = i * 2;
            total += part;
        }
        System.out.println("total=" + total);

        int turn = 0;
        while (turn < 2) {
            int step = turn + 10;
            System.out.println("whileStep=" + step);
            turn++;
        }
        System.out.println("afterWhile=" + turn);
    }

    public static void main(String[] args) {
        ScopeBlocksDemo demo = new ScopeBlocksDemo();
        demo.demonstrate();

        System.out.println("methodOne=" + increment(5));
        System.out.println("methodTwo=" + increment(10));
        System.out.println("format=" + format(4));
        System.out.println("assignedTrue=" + choose(true));
        System.out.println("assignedFalse=" + choose(false));

        int shared = 9;
        System.out.println("localShared=" + shared);
        System.out.println("fieldShared=" + ScopeBlocksDemo.shared);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ScopeBlocksDemo.java
java ScopeBlocksDemo
~~~

**Exact expected stdout:**

~~~text
localCount=3
fieldCount=100
inside=5
siblingA=7
siblingB=8
forIndex=0
forIndex=1
forIndex=2
item=A
item=B
total=12
whileStep=10
whileStep=11
afterWhile=2
methodOne=6
methodTwo=11
format=P4
assignedTrue=1
assignedFalse=2
localShared=9
fieldShared=50
~~~

The `siblingA`/`siblingB` lines demonstrate that names can be reused in two non-overlapping blocks; `forIndex` and `item` exist only inside their respective loops; `total` can be printed after the loop because it was declared outside; `localCount`/`fieldCount` demonstrate field shadowing.

## 9. Checklist and exercises

| Situation | Check / resolution |
| --- | --- |
| `cannot find symbol` for a name just declared in a block | Has the name gone past `}` or not yet reached its declaration? |
| Want to use a result after `for` | Declare the result variable outside `for` and update it inside |
| Two sequential `for (int i...)` loops | Valid if the scopes of the two `i` variables do not overlap |
| Nested `for` loops with the same name `i` | Invalid; rename the inner loop variable |
| Declaring a local with the same name as an outer local/parameter still in scope | Invalid in overlapping regions |
| Local with the same name as a field | Valid but shadows; consider `this.field` or `ClassName.field` |
| Variable is declared but not guaranteed to be assigned | Check *definite assignment* on every path |
| Returning an object and leaving a block | The object may still exist via an external reference |

**Exercise 1.** Declare `int sum = 0` outside a `for` loop and `int term` inside. Compute the sum of squares from 1 to 4, then print `sum`. Why can't `term` be printed after the loop?

**Exercise 2.** Write two sequential `for (int i...)` loops, then try declaring a loop with the same name `i` nested inside the first loop. Predict the compile error.

**Exercise 3.** Create two consecutive blocks that both declare `String message`. Then try nesting them to see when duplicate naming is forbidden.

**Exercise 4.** Write a method taking parameter `int count` in a class with field `count`. Print the parameter value, the field, and a local in a nested block; compare the scopes of the names.

**Exercise 5.** Write a method `int choose(boolean flag)` using a variable `result` declared before `if`. Try removing the `else` branch to observe the *definite assignment* rule.

### Key Takeaway

**Scope determines where a name can be used, which does not mean a variable is already assigned or an object is destroyed when the block ends.** Variables declared in `{ }`/loop bodies cannot be used outside their region; `for` variables declared in the initialization part also go out of scope after the loop. Parameters are in effect within the method body. Locals with the same name cannot have overlapping scopes, but a local can shadow a field, with the field accessed via `this` or the appropriate class name.
