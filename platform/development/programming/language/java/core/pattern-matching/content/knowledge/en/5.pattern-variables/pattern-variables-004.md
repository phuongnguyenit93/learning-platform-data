# Pattern variable: Must not shadow an in-scope variable

> **Scope:** Java Core Pattern Matching → Pattern variable. This lesson uses **Java 17+**, focusing on `instanceof` with a type pattern (`instanceof String text`). Snippets annotated with **ERROR** intentionally do not compile and are for analysis only; the complete runnable program is in section 8.

## Objectives

After this lesson, you will be able to:

- Explain **name collision**, **shadowing**, and the **scope** of a pattern variable.
- Predict why a declaration like `instanceof String name` can be rejected by the compiler when `name` is already a local variable, parameter, or pattern variable still in scope.
- Recognize **flow scoping**: the scope of a pattern variable depends on control flow; it may end after an `if` branch or continue after a guard clause.
- Distinguish between cases where **colliding with a local variable is disallowed** and cases where **shadowing a field is allowed**.
- Rewrite code with clear variable names, safely reuse names in non-overlapping branches, and resolve related compilation errors.

## 1. Core rule: a pattern variable is a flow-scoped local variable

Java 17 example:

~~~java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length()); // text is a String and is already initialized.
}
~~~

`String text` declares a **pattern variable** named `text`. When `input` matches `String`, this variable is initialized and used where the compiler proves the match result is `true`.

**Important rule:** Java **does not allow a pattern variable to be declared with the same name as a local variable currently in scope**, including another pattern variable. The rules for method parameters, lambda parameters, and `catch` parameters also prevent redeclaring a variable with the same name in those respective scopes. This is a **compile-time error**; it does not depend on runtime values and cannot be fixed by casting.

The following example **intentionally does not compile**:

~~~java
static void broken(Object input) {
    String text = "đã tồn tại";

    if (input instanceof String text) { // ERROR: text is already declared.
        System.out.println(text);
    }
}
~~~

`text` on the first line is a local variable; its scope is still in effect at the `if` statement. If the pattern were allowed to declare another `text`, the two variables could not be distinguished by a simple name. The compiler rejects it.

**How to fix:** give the pattern variable a different name or change the design to use the existing variable:

~~~java
static void fixed(Object input) {
    String fallbackText = "mặc định";

    if (input instanceof String matchedText) {
        System.out.println(matchedText);
    } else {
        System.out.println(fallbackText);
    }
}
~~~

The name `matchedText` clearly expresses that the variable is created **when the match succeeds**. There is no need to cast `input` to `String` again.

## 2. Kinds of in-scope names that cannot be redeclared

### 2.1. Colliding with a local variable in an enclosing block

~~~java
static void brokenLocal(Object value) {
    String name = "outer";

    {
        if (value instanceof String name) { // ERROR: name is already in scope.
            System.out.println(name);
        }
    }
}
~~~

**Note:** Adding an extra `{ ... }` block **does not** allow redeclaring the name of a local variable from an enclosing block. This rule differs from some languages that allow arbitrary local shadowing in nested blocks.

Fix: `if (value instanceof String matchedName) { ... }`.

### 2.2. Colliding with a method parameter

~~~java
static void brokenParameter(Object value) {
    if (value instanceof String value) { // ERROR: value is a method parameter.
        System.out.println(value);
    }
}
~~~

The parameter `value` already carries that name in the method body. Whether the object is actually a `String` does not change the error. Write:

~~~java
static void fixedParameter(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }
}
~~~

This is also why you should not default to giving a pattern variable **the same name as the target expression**. For example, `input instanceof String input` causes a name collision if `input` is an in-scope parameter or local variable.

### 2.3. Colliding with a `catch` parameter or a variable in a lambda

The snippets below **intentionally do not compile**:

~~~java
static void brokenCatch(Object input) {
    try {
        throw new IllegalStateException("demo");
    } catch (IllegalStateException error) {
        if (input instanceof String error) { // ERROR: error is a catch parameter.
            System.out.println(error);
        }
    }
}
~~~

~~~java
static void brokenLambda(Object input) {
    String name = "outer";

    Runnable task = () -> {
        if (input instanceof String name) { // ERROR: name from enclosing block.
            System.out.println(name);
        }
    };
}
~~~

A lambda does not create a "completely new namespace" to redeclare a local variable still alive in an enclosing block. Use `matchedName` or another unused name. The same applies to lambda parameters: do not redeclare a parameter name inside the lambda body.

### 2.4. Colliding with an in-scope pattern variable

~~~java
static void brokenNested(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println(text);

        if (second instanceof String text) { // ERROR: text from outer if is still in scope.
            System.out.println(text);
        }
    }
}
~~~

Inside the outer `if` block, `text` is already a valid pattern variable name. A pattern nested inside that block cannot declare **another `text`**.

Fix: keep `text` for the first object and use `secondText` for the second object:

~~~java
static void fixedNested(Object first, Object second) {
    if (first instanceof String firstText) {
        if (second instanceof String secondText) {
            System.out.println(firstText + " / " + secondText);
        }
    }
}
~~~

## 3. Scope is not simply the position of curly braces

A pattern variable has **flow scoping**: the compiler infers the execution points at which the pattern is guaranteed to have matched. Determining **whether a variable is in scope** must be based on control flow, not merely textual proximity or a pair of `{ }`.

### 3.1. Normal `if` scope

~~~java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // Valid.
    }

    String text = "new local"; // Valid: pattern text from if is out of scope.
    System.out.println(text);
}
~~~

With this `if`, the pattern `text` is in scope in the true branch; after the `if`, the compiler cannot be certain that `input` matched. Therefore, the name `text` can be used for a new local declaration at that point.

### 3.2. Guard clause: scope continues after `if`

~~~java
static int readLength(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }

    return text.length(); // Valid: all paths reaching here have matched.
}
~~~

This is how Java avoids having to cast `input` again. However, precisely because `text` **is still in scope**, the following snippet **intentionally does not compile**:

~~~java
static int brokenGuard(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }

    String text = "other"; // ERROR: pattern text is still in scope.
    return text.length();
}
~~~

Because the failure branch ends with `return`, the statements below can only execute when the pattern succeeds. If the failure branch `throw`s an exception, the same reasoning applies.

### 3.3. The `&&` operator allows using the variable, not redeclaring it

~~~java
static boolean longText(Object input) {
    return input instanceof String text && text.length() >= 4;
}
~~~

When Java evaluates the right-hand side of `&&`, the left-hand side has already returned `true`, so `text` can be used. However, you must not exploit the right-hand side to create another variable with the **same name**:

~~~java
static boolean brokenAnd(Object first, Object second) {
    return first instanceof String text
        && second instanceof String text; // ERROR: name text is redeclared.
}
~~~

Fix: `first instanceof String firstText && second instanceof String secondText`. From there, both `firstText` and `secondText` can be used simultaneously in subsequent expressions of the true branch.

### 3.4. Duplicate names on both sides of `||` can still be rejected

The following snippet **intentionally does not compile**:

~~~java
static boolean brokenOr(Object first, Object second) {
    return (first instanceof String text)
        || (second instanceof String text); // ERROR: two bindings with the same name.
}
~~~

Even though `||` can short-circuit and one of the two matches may succeed, attempting to create two pattern variables with the **same name** in an `||` expression causes a conflict when determining the binding. Do not assume that because "only one side runs", the name can be reused.

If the goal is only to check whether at least one is a string, no pattern variable is needed:

~~~java
static boolean anyString(Object first, Object second) {
    return first instanceof String || second instanceof String;
}
~~~

If you want to access the matched string, handle the two branches independently with separate names or an appropriate `if / else if` structure.

## 4. When can a pattern variable name be reused?

**Having two patterns with the same name in a method is not always an error.** What determines validity is whether their scopes overlap or whether expression-combining rules forbid bindings with the same name.

### 4.1. Two independent `if` statements: valid

~~~java
static void printTwo(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println("first=" + text);
    }

    if (second instanceof String text) {
        System.out.println("second=" + text);
    }
}
~~~

`text` from the first `if` is only in scope in the first match branch; it is **no longer** in scope at the second `if`. Each declaration is a separate pattern variable. This is illustrated in the JLS with multiple patterns having the same name in non-overlapping branches.

### 4.2. Two mutually exclusive branches: valid

~~~java
static void printEither(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println("first=" + text);
    } else if (second instanceof String text) {
        System.out.println("second=" + text);
    }
}
~~~

In the `else if` branch, the pattern `text` from the first branch is no longer in scope. The two declarations with the same name are therefore valid.

### 4.3. After the scope ends: valid

~~~java
static void printAfter(Object value) {
    if (value instanceof String name) {
        System.out.println(name);
    }

    String name = "fallback"; // Valid in this normal if case.
    System.out.println(name);
}
~~~

Compare this with the guard clause in section 3.2: when `return` keeps the pattern alive after the `if`, declaring `String name` at the same position is no longer valid.

**Practical rule:** If you need to use two values at the same time, give them two different names (`firstText`, `secondText`). If the branches are independent and their scopes do not overlap, reusing a short name (`text`) can be valid and readable.

## 5. Important exception: a pattern variable may shadow a field name

The lesson title must be understood accurately according to Java's rules: **forbidding shadowing an in-scope local variable** does not mean forbidding a pattern variable **with the same name as a field** of the class.

~~~java
class FieldExample {
    private String label = "FIELD";

    void print(Object input) {
        if (input instanceof String label) {
            System.out.println(label);      // Pattern variable.
            System.out.println(this.label); // Object field.
        }
    }
}
~~~

This code is **valid**. Inside the match branch, the simple name `label` refers to the pattern variable; `this.label` still accesses the field. For a `static` field, you can use the class name: `ClassName.fieldName`.

Distinguish the two cases:

| Existing variable named `label` | New pattern `instanceof String label` | Explanation |
| --- | --- | --- |
| Method parameter in the same method body | **Compile-time error** | Parameter name collides within the active scope |
| Local variable in an enclosing block | **Compile-time error** | Cannot shadow an in-scope local variable |
| Another in-scope pattern variable | **Compile-time error** | Duplicate binding within the active region |
| Class field, with no local/parameter of the same name | **Valid** | Pattern variable shadows the field name in its branch; use `this.label` to access the field |
| Pattern variable from an independent `if` whose scope has ended | **Valid** | Two separate scopes |

**On design:** Although shadowing a field is allowed, choosing a distinct pattern name (`matchedLabel`) is usually easier to maintain. When intentionally reusing the name, you must be clear that `label` and `this.label` are **two different variables**.

## 6. Why does the compiler reject it at compile time?

The compiler needs to bind every simple name in an expression to **a single valid and unambiguous declaration**, while ensuring a pattern variable is only used when the match succeeds. Java applies:

1. **Name declaration rules:** an in-scope parameter/local variable/pattern variable cannot be redeclared with the same name under the rules of JLS `6.4.
2. **Flow-based pattern variable introduction rules:** `instanceof String text` brings the variable into scope at points where the match condition is proven to be `true` (JLS `6.3).
3. **Logical expression and branching rules:** `&&`, `||`, `!`, `if`, and guard clauses determine where a binding is in use and where a duplicate declaration becomes an error.

Because the error lies in **source code and scope**, changing the value of `input` from `String` to `Integer`, or replacing `null` with a string, does not fix a colliding name. Do not confuse this with `ClassCastException`, which is a runtime exception caused by an invalid cast.

Messages from `javac` typically take the form *variable ... is already defined* or report a redefined binding. Exact wording may vary across JDK versions; check both the location underlined by the compiler and the declarations in scope.

## 7. Systematic way to fix the error

When you see an error with a pattern variable name, follow this sequence:

1. **Find declarations with the same name** among parameters, locals, pattern variables, and catch/lambda parameters in the method and enclosing blocks. For example, `String text = ...` appearing before `instanceof String text`.
2. **Analyze flow scope:** does the pattern come from a normal `if` and live only in the true branch? Or does a guard `if (!(o instanceof String text)) return;` keep it alive afterward? Are there `&&` / `||` or nested `if`s?
3. **Rename the conflicting binding** so it reflects the data source: `matchedText`, `outerText`, `innerText`, `leftValue`, `rightValue`. Update all usages of that binding at the same time.
4. **Keep the pattern instead of redundant casts:** after `if (o instanceof String matchedText)`, use `matchedText` directly. There is no need for `(String) o`.
5. **If the conflict is with a field**, decide whether reusing the name is truly necessary. Use `this.field` or choose a clearer pattern name.
6. **Recompile** and test with matching, non-matching, and `null` values to verify the control flow.

Example of fixing a nested pattern:

~~~java
// Wrong: both patterns share the name text in overlapping scopes.
if (left instanceof String text) {
    if (right instanceof String text) { // ERROR
        System.out.println(text);
    }
}

// Right: name according to the source object.
if (left instanceof String leftText) {
    if (right instanceof String rightText) {
        System.out.println(leftText + ", " + rightText);
    }
}
~~~

This is **illustrative code placed inside a method** with parameters `Object left, Object right`; it is not a standalone Java file. Do not copy both the "Wrong" and "Right" snippets into the same method and expect the compiler to accept it.

## 8. Complete program running on Java 17+

Save the following snippet as **`PatternScopeDemo.java`**:

~~~java
public class PatternScopeDemo {
    private final String label = "FIELD";

    void print(Object first, Object second) {
        // Valid: pattern variable shadows the field label.
        if (first instanceof String label) {
            System.out.println("local=" + label + ", field=" + this.label);
        }

        // Valid: the name label from the previous if is out of scope.
        if (second instanceof String label) {
            System.out.println("second=" + label);
        }

        // Valid: text is in scope on the right-hand side of && when the match succeeds.
        if (first instanceof String text && !text.isBlank()) {
            System.out.println("length=" + text.length());
        }

        // Valid: matched remains in scope after the guard clause.
        if (!(second instanceof String matched)) {
            System.out.println("not string");
            return;
        }

        System.out.println("after guard=" + matched.toUpperCase());
    }

    public static void main(String[] args) {
        new PatternScopeDemo().print("hello", "world");
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 PatternScopeDemo.java
java PatternScopeDemo
~~~

**Exact stdout output:**

~~~text
local=hello, field=FIELD
second=world
length=5
after guard=WORLD
~~~

Explanation:

- `local=hello, field=FIELD`: pattern `label` receives `"hello"`, while `this.label` remains the field `"FIELD"`.
- `second=world`: declaring `label` in the next `if` is valid because the previous `label` pattern is out of scope.
- `length=5`: `text` is only used when `instanceof String` returns `true`, so `text.isBlank()` and `text.length()` are safe.
- `after guard=WORLD`: the non-matching branch for `second` returned; in what follows, `matched` is guaranteed to be a `String`.

If you pass `new PatternScopeDemo().print("hello", 42)`, the `second instanceof String label` branch does not execute, and the guard prints `not string` and returns. **No cast is needed**, nor is there any "duplicate variable name" error because the names are used within valid scopes.

## 9. Common misconceptions

- **"Every duplicate pattern name declaration in the same method is an error."** False: two independent `if` statements or two mutually exclusive branches can reuse the name.
- **"Just wrapping it in a new `{ }` pair lets you redeclare the same name."** False: a local/parameter from an enclosing block is still in scope inside the inner block.
- **"A pattern variable only lives in the initial `if` branch."** False: after a guard clause with an appropriate `return`/`throw`, the variable can remain in scope.
- **"The two sides of `||` don't run at the same time, so they can declare the same name."** False: the JLS forbids cases that create bindings with the same name across branches of `||`.
- **"Shadowing any kind of variable is forbidden, including fields."** False: you can shadow a field with a local/pattern variable and access the field using `this.field` or `ClassName.field`.
- **"The name collision error happens because the data doesn't match `instanceof`."** False: the name collision error occurs at compile time, even without running the program.
- **"Changing the pattern's type while keeping the same name resolves the conflict."** False: a colliding name `text` in scope is still an issue even if the pattern changes from `String` to `CharSequence`.
- **"You can fix it by manually casting everywhere."** Casting does not resolve a name collision; instead, rename the pattern or restructure the scopes validly.

## 10. Practice quiz

**Question 1:** Does the following snippet compile? Why or why not?

~~~java
static void test(Object input) {
    String result = "old";
    if (input instanceof String result) {
        System.out.println(result);
    }
}
~~~

**Question 2:** Why are the two `name` declarations valid here?

~~~java
static void test(Object a, Object b) {
    if (a instanceof String name) {
        System.out.println(name);
    }
    if (b instanceof String name) {
        System.out.println(name);
    }
}
~~~

**Question 3:** In the following snippet, can you also declare `String s = "new";` after the `if`?

~~~java
static void test(Object obj) {
    if (!(obj instanceof String s)) {
        throw new IllegalArgumentException();
    }
    // Declare String s = "new"; here?
}
~~~

**Question 4:** In `class Box { String value = "FIELD"; ... }`, if you write `if (obj instanceof String value)` in a method with no local/parameter named `value`, will the compiler accept it? What do `value` and `this.value` refer to?

**Question 5:** Consider `if (a instanceof String s && b instanceof String s)`. What is the error? Fix it so both strings can be used.

**Question 6:** Compare `if (a instanceof String s) ... else if (b instanceof String s) ...` and `(a instanceof String s) || (b instanceof String s)` regarding name collisions.

### Answers

1. **No**: the local variable `result` is already in scope when the pattern also declares `result`. Rename the pattern to `matchedResult`.
2. **Valid**: the scope of `name` in the first `if` ends before the second `if`. They are two distinct pattern variables.
3. **No**: the failure branch throws an exception, so `s` continues in scope afterward. Use a new name if you need another variable.
4. **Yes**: a pattern variable is allowed to shadow a field name; `value` is the matched string, and `this.value` is the object's field.
5. **Duplicate pattern name error** in `&&`. Fix it to `a instanceof String firstText && b instanceof String secondText` and use the variables in the `true` branch.
6. **`else if` can be valid** because the two branches do not overlap in scope; whereas the `||` expression declares two bindings named `s` and is rejected by the JLS.

## Official references

- [Java Language Specification 17 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): flow scoping of pattern variables, `instanceof`, `&&`, `||`, `if`, and guard clauses.
- [Java Language Specification 17 — `6.4 Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): prohibition on redeclaring an in-scope local name; `Test4`/`Test5` examples on pattern names.
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): pattern variable scope and `if`/`&&`/`!` examples.
- [Java Language Specification 17 — `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): meaning of patterns, declaring and assigning values to pattern variables.