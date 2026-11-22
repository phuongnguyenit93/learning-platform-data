# Duplicate Local Variable Names in Nested Blocks and Invalid Declarations — Java 17+

## 1. Core rule

The **scope** of a local variable determines the region of code where its name can be used. In Java, once a local variable is already in scope, **you cannot declare another local variable with the same name in a nested inner block**. Java reports a compile error, even if the programmer intends for the inner variable to "shadow" the outer variable.

~~~java
static void invalid() {
    int count = 10;
    {
        // int count = 20; // COMPILE ERROR: count is already declared.
        System.out.println(count); // Valid: uses count from the outer block.
    }
}
~~~

This differs from **a local variable or parameter shadowing a class field**; the field can still be accessed via `this.field` or `ClassName.field`.

**Distinction to remember:** using the same name in two blocks with **non-overlapping scopes** can be valid; using the same name in two **nested blocks while the outer variable is still in scope** is not.

## 2. Valid and invalid cases

| Situation | Valid? | Explanation |
|---|---|---|
| `int x=1; int x=2;` in the same block | **No** | Duplicate local variable declaration |
| Declaring `x` in an inner block while the outer block's `x` is in scope | **No** | Java forbids redeclaring a local variable in overlapping scopes |
| Reusing `x` in two sibling blocks | **Yes** | Two separate scopes |
| Declaring `x` after a block containing another `x` has ended | **Yes** | The previous scope does not extend outside the block |
| Parameter `x`, then declaring `int x` in the method body or an inner block | **No** | Conflicts with the parameter still in scope |
| Local variable `name` with the same name as field `name` | **Yes** | Local variable shadows the field |
| Parameter `name` with the same name as field `name` | **Yes** | Use `this.name` to access the instance field |
| Two sequential `for (int i=...)` loops | **Yes** | The first loop's `i` goes out of scope before the next loop |
| Declaring `int i` inside the body of a `for (int i=...)` loop | **No** | The outer loop's `i` is still in scope |
| Lambda declaring a parameter with the same name as an enclosing local in scope | **No** | A lambda parameter cannot duplicate an enclosing local variable |

**Terminology note:** *shadowing* of a field by a local is valid; redeclaring an in-scope local in an inner block is not a shadowing mechanism permitted by Java.

## 3. Two independent blocks are allowed to use the same name

~~~java
static void siblings() {
    {
        int value = 1;
        System.out.println("first=" + value);
    }

    {
        int value = 2;
        System.out.println("second=" + value);
    }

    int value = 3;
    System.out.println("after=" + value);
}
~~~

**Exact stdout when calling `siblings()`:**

~~~text
first=1
second=2
after=3
~~~

Each `value` is declared after the `value` in the previous block **has gone out of scope**. There are never three variables with the same name coexisting in an overlapping declaration region.

Conversely:

~~~java
// DOES NOT COMPILE if uncommented:
static void duplicate() {
    int value = 1;
    // int value = 2; // Duplicate name in the same block.
    {
        // int value = 3; // Conflicts with local in the outer block.
    }
}
~~~

**Reassignment** is completely different from **redeclaration**:

~~~java
int value = 1;
value = 2; // Valid: updates the existing variable.
~~~

## 4. Parameters and `for` counter variables also have scope

A method parameter can be read in the method body and its inner blocks. You cannot declare a local variable with the same name there:

~~~java
static void process(int total) {
    // int total = 0; // Error: conflicts with parameter.
    {
        // int total = 5; // Also an error.
        System.out.println(total);
    }
}
~~~

For the `for` loop:

~~~java
for (int i = 0; i < 2; i++) {
    System.out.println("loopA=" + i);
    // int i = 99; // Error: i from for is in scope.
}

for (int i = 2; i < 4; i++) {
    System.out.println("loopB=" + i);
}
~~~

**Exact stdout:**

~~~text
loopA=0
loopA=1
loopB=2
loopB=3
~~~

The name `i` can be reused because the first `for` loop has ended the **scope region of its `i` declaration**. However, if you declare `int i = 10;` in a block enclosing both loops, declaring `for (int i = ...)` inside is forbidden.

## 5. Field shadowing is a different case

A local/parameter having the same name as a **field** is valid, because a field is not a local of the method's enclosing block:

~~~java
class Person {
    private String name = "FIELD";
    void print(String name) {
        System.out.println(name);      // Parameter
        System.out.println(this.name); // Field
    }
}
~~~

In a `static` context, use the class name to refer to a shadowed `static` field. This is completely different from redeclaring a local/parameter in a nested block with overlapping scope; the lesson on field shadowing goes into detail on updating the right field.

## 6. Duplicate name declaration differs from definite assignment errors

~~~java
static int choose(boolean flag) {
    int result;
    if (flag) result = 1;
    else result = 2;
    return result; // Assigned on both paths to return.
}
~~~

Here there is only **one** variable `result` and no duplicate declaration. If you remove `else`, the error when reading `result` is *definite assignment*, because the `false` branch might leave it unassigned; this is a different check from checking duplicate overlapping declarations.

## 7. Lambdas: do not declare a parameter with the same name as an enclosing local

~~~java
static void lambdaExample() {
    int bonus = 3;
    java.util.function.IntUnaryOperator plusBonus =
            number -> number + bonus;

    System.out.println("lambda=" + plusBonus.applyAsInt(4));
}
~~~

**Exact stdout:**

~~~text
lambda=7
~~~

If you used `bonus -> bonus + 1` as the lambda parameter right here, the parameter name `bonus` would conflict with the enclosing local `bonus` and be invalid.

A local variable **captured** by a lambda must be `final` or *effectively final* (not reassigned after initialization). This is another requirement in addition to the duplicate-name rule:

~~~java
// int bonus = 3;
// bonus++;
// IntUnaryOperator op = x -> x + bonus; // Invalid: bonus is not effectively final.
~~~

## 8. Complete Java 17+ program

Save as the exact file **`LocalScopeNameDemo.java`**:

~~~java
public final class LocalScopeNameDemo {
    private String name = "FIELD";
    private static String label = "STATIC_FIELD";

    private static void nestedBlock() {
        int count = 10;
        {
            int increment = 5;
            System.out.println("nested total=" + (count + increment));
            // int count = 20; // Invalid.
        }
        System.out.println("outer count=" + count);
    }

    private static void siblingBlocks() {
        {
            int value = 1;
            System.out.println("first=" + value);
        }
        {
            int value = 2;
            System.out.println("second=" + value);
        }
        int value = 3;
        System.out.println("after=" + value);
    }

    private static void consecutiveLoops() {
        for (int i = 0; i < 2; i++) {
            System.out.println("loopA=" + i);
        }
        for (int i = 2; i < 4; i++) {
            System.out.println("loopB=" + i);
        }
    }

    private void showFields(String name) {
        System.out.println("parameter=" + name);
        System.out.println("instance field=" + this.name);
        String label = "LOCAL";
        System.out.println("local label=" + label);
        System.out.println("static field=" + LocalScopeNameDemo.label);
    }

    private static int initialized(boolean flag) {
        int result;
        if (flag) {
            result = 1;
        } else {
            result = 2;
        }
        return result;
    }

    private static void lambdaExample() {
        int bonus = 3;
        java.util.function.IntUnaryOperator add =
                value -> value + bonus;
        System.out.println("lambda=" + add.applyAsInt(4));
    }

    public static void main(String[] args) {
        nestedBlock();
        siblingBlocks();
        consecutiveLoops();
        new LocalScopeNameDemo().showFields("PARAMETER");
        System.out.println("assigned true=" + initialized(true));
        System.out.println("assigned false=" + initialized(false));
        lambdaExample();
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 LocalScopeNameDemo.java
java -cp . LocalScopeNameDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\LocalScopeNameDemo.java
java -cp . LocalScopeNameDemo
~~~

### Exact expected stdout

~~~text
nested total=15
outer count=10
first=1
second=2
after=3
loopA=0
loopA=1
loopB=2
loopB=3
parameter=PARAMETER
instance field=FIELD
local label=LOCAL
static field=STATIC_FIELD
assigned true=1
assigned false=2
lambda=7
~~~

**Explanation:** the inner block reads `count` from the outer block without redeclaring it; three non-overlapping blocks reuse the name `value`; two sequential `for` loops reuse `i`. Parameter `name` shadows the instance field, distinguished via `this.name`; local `label` shadows the static field, distinguished via the class name.

## 9. Common errors and exercises

| Mistake | Cause | Fix |
|---|---|---|
| `int x=1;` then `int x=2;` | Duplicate local name in the same block | Assign `x=2;` or rename |
| Declaring `int x` in an inner block while outer local `x` is in effect | Overlapping scopes | Use the existing variable, or pick a new name |
| Declaring a local with the same name as a parameter | Parameter is still in scope | Rename the local |
| Declaring a local with the same name as the `for` counter inside the `for` body | Loop `i` is still in effect | Use the existing index |
| Thinking a local matching a field name is always forbidden | Fields can be shadowed by locals | Use `this.field` or `ClassName.field` when needed |
| Using a variable after leaving its declaration block | Name is out of scope | Declare in an appropriate enclosing block |
| Using a local not assigned on all paths | Definite assignment not satisfied | Assign on all paths |
| Lambda parameter matching an enclosing local | Duplicate name declaration | Rename the lambda parameter |
| Lambda capturing a reassigned local | Not effectively final | Do not reassign, or change how state is stored |

**Exercise A.** Which snippet is valid?

~~~java
{
    int n = 1;
}
{
    int n = 2;
}
~~~

**Answer:** valid, because the two scopes are separate.

**Exercise B.** Why is this snippet invalid?

~~~java
int n = 1;
{
    // int n = 2;
}
~~~

**Answer:** outer `n` is still in scope in the inner block, so local `n` cannot be declared again there.

**Exercise C.** Given instance field `name` and parameter `name`, how do you access the field? **`this.name`**.

**Exercise D.** With `int result;` followed by assigning `result` only inside `if (flag)`, can it be used after `if`? **Not guaranteed**; if `flag == false`, the variable is uninitialized. It must be assigned in an `else` branch or before `if`.

## 10. Checklist and conclusion

- [ ] Know that a local variable's name scope starts from its declaration in the corresponding block.
- [ ] Do not declare duplicate local names in the same block or inner blocks with overlapping scopes.
- [ ] Reuse names in two sequential non-overlapping blocks when appropriate.
- [ ] Distinguish redeclaration from reassignment.
- [ ] Understand that parameters and `for` variables also have their own scopes.
- [ ] Distinguish valid **field** shadowing from forbidden **local** redeclaration.
- [ ] Use `this.field` or `ClassName.field` to access shadowed fields.
- [ ] Distinguish duplicate-name errors from definite assignment errors.
- [ ] Remember a lambda parameter must not duplicate an enclosing local.
- [ ] Run `LocalScopeNameDemo.java` with Java 17+ and compare against exact stdout.

**Conclusion:** Java does not allow declaring a new local variable or parameter with the **same name as a local currently in an enclosing scope**. Names can be reused once the previous scope has ended, and locals/parameters can **shadow class fields**. Accurately identifying each name's scope prevents compile errors and helps choose readable names.
