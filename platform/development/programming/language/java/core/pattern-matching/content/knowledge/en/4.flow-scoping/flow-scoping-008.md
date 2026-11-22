# Variable Scope in Java's Conditional Expression (? : Operator)

## 1. Why can a variable still be out of scope even after a type check?

Pattern matching lets you check a type and bind a name to the value in a single expression:

~~~java
value instanceof String text
~~~

If the check matches, `text` is a variable of type `String`. However, that **does not mean `text` exists everywhere after its declaration**. Java uses *flow scoping*: the compiler analyzes the execution paths a program can take to determine where a pattern variable is guaranteed to be bound to a value (*definitely matched*).

This topic focuses on the **conditional expression** using the ternary operator `? :`:

~~~java
condition ? expressionWhenTrue : expressionWhenFalse
~~~

When `condition` is true, Java evaluates the branch after `?`; when false, Java evaluates the branch after `:`. If `condition` contains an `instanceof` pattern, which branch can use the pattern variable depends on whether that branch **definitely corresponds to a successful match**.

After this lesson, you will be able to:

- Explain when a variable declared in the condition of `? :` can be used in the true branch and the false branch.
- Determine pattern variable scope when the condition includes negation `!`, `&&`, or `||`.
- Understand why a complete `? :` expression **does not bring** a pattern variable out into the next statement, even if the expression evaluates to `boolean`.
- Distinguish runtime match checks from compile-time scope analysis.
- Write clear, safe Java 17+ code and recognize typical compile-time errors.

## 2. Core rules of the expression a ? b : c

For a conditional expression:

~~~java
a ? b : c
~~~

Java applies two rules for pattern variables:

1. A pattern variable **introduced by `a` when true** is guaranteed to be matched in **`b`**.
2. A pattern variable **introduced by `a` when false** is guaranteed to be matched in **`c`**.

This does not mean every expression in branch `b` or `c` can use every variable that appears in `a`. You must determine **the exact true/false state in which the pattern was matched**.

Execution flow diagram:

~~~text
        a (condition)
         /         \
       true        false
        |            |
        v            v
        b            c
   uses variables  uses variables
   matched when    matched when
   a == true       a == false
        \            /
         \          /
       result of the whole expression
       (does not bring pattern variables
        into the outer scope)
~~~

**A very important third rule:** the entire `a ? b : c` expression itself **does not introduce pattern variables when true or when false**. Even if both `b` and `c` return `boolean`, Java does not infer that a variable declared in `a` will definitely exist in a statement outside the conditional expression.

These rules are specified in the *Java Language Specification* (JLS) `6.3.1.4, applicable to Java 17 and later versions.

## 3. Pattern matches when the condition is true: variable is in scope in the ? branch

A common example:

~~~java
String result = value instanceof String text
    ? text.toUpperCase()
    : "Not a String";
~~~

This is **illustrative code placed inside a method**, where `value` has static type `Object`.

- `value instanceof String text` **introduces `text` when the condition is true**.
- The `? text.toUpperCase()` branch only runs after the check succeeds, so `text` has type `String` and is valid to use.
- The `: "Not a String"` branch handles non-matching values (including `null`); `text` is **not** in scope in this branch.
- After the `? :` expression finishes, you cannot use `text` in the next statement just because it was declared in the condition.

A symmetric example that **intentionally does not compile**:

~~~java
static String invalid(Object value) {
    return value instanceof String text
        ? text.toUpperCase()
        : text.toLowerCase(); // ERROR: text does not exist in the false branch
}
~~~

In the false branch, `value` could be an `Integer` or `null`. Java cannot allow reading `text` because no `String` value was bound.

To use a similar result in both branches, compute that value **after** checking/normalizing along a valid path, or use a regular local variable with an appropriate scope; do not try to pull a pattern variable into a non-matching branch.

## 4. With !, the branch where the variable is in scope flips

The negation operator `!` flips the truth value of the condition; therefore, it also flips the state in which the variable is guaranteed to be matched.

~~~java
String result = !(value instanceof String text)
    ? "Not a String"
    : text.toUpperCase();
~~~

How to read it:

- `value instanceof String text` matches when the value is a `String`.
- `!(value instanceof String text)` is **true** when `value` is not a `String`. In that case, the `?` branch runs and **cannot** use `text`.
- The negated condition being **false** means the original `instanceof` matched. Therefore, the `:` branch can use `text`.

Quick reference table:

| Condition before ? | Branch that can use the pattern variable | Why? |
| --- | --- | --- |
| `value instanceof String text` | Branch after `?` | Condition being true proves `String` matched |
| `!(value instanceof String text)` | Branch after `:` | Condition being false proves the inner `instanceof` is true |

Read “variable introduced when the expression is true/false” according to the *value of the whole condition*, rather than just looking at the variable name on the left-hand side of the operator.

## 5. Runnable example: ternary forms in a single program

Save the following code as `ConditionalScopeDemo.java`. This is a complete program using **Java 17+**, with no preview features required.

~~~java
public class ConditionalScopeDemo {
    static String describe(Object value) {
        return value instanceof String text
            ? "String length=" + text.length()
            : "Other";
    }

    static String normalize(Object value) {
        return !(value instanceof String text)
            ? "Not text"
            : text.isBlank() ? "Blank" : text.trim().toUpperCase();
    }

    static String filtered(Object value) {
        return value instanceof String text && text.length() >= 3
            ? "Long:" + text
            : "Other";
    }

    static String validate(Object value) {
        return !(value instanceof String text) || text.isBlank()
            ? "Invalid"
            : "Valid:" + text.trim();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(42));
        System.out.println(describe(null));
        System.out.println(normalize(123));
        System.out.println(normalize("   "));
        System.out.println(normalize("  Java  "));
        System.out.println(filtered("Java"));
        System.out.println(filtered("Hi"));
        System.out.println(filtered(13));
        System.out.println(validate(null));
        System.out.println(validate(" "));
        System.out.println(validate(" hi "));
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 17 ConditionalScopeDemo.java
java ConditionalScopeDemo
~~~

Exact output:

~~~text
String length=4
Other
Other
Not text
Blank
JAVA
Long:Java
Other
Other
Invalid
Invalid
Valid:hi
~~~

Method-by-method explanation:

**`describe`:** When `value instanceof String text` is true, the `?` branch reads `text.length()`. For `42` and `null`, the pattern does not match, resulting in `Other`.

**`normalize`:** The condition has `!`, so the `:` branch is the path where `value` is proven to be a `String`. Inside this branch there is a **nested** conditional expression: `text.isBlank() ? "Blank" : text.trim().toUpperCase()`. In both branches of the nested expression, `text` is already in scope from the outer branch; therefore both `text.isBlank()` and `text.trim()` are valid. A whitespace-only string produces `Blank`; `"  Java  "` produces `JAVA`.

**`filtered`:** The condition is `value instanceof String text && text.length() >= 3`. `&&` only evaluates the right-hand operand when the left-hand operand is true. Thus `text` is safely used right inside the right-hand side of `&&`; the entire condition being true also guarantees a match, allowing `text` to be used in the `?` branch.

**`validate`:** The condition is `!(value instanceof String text) || text.isBlank()`. `||` only evaluates the right-hand operand when the left-hand side is false; if the left-hand side is false, `value instanceof String text` has matched. The `:` branch only runs when the entire condition is false, meaning the value must be a **non-blank** `String`, so `text.trim()` can be used.

## 6. When conditions combine && and ||, trace the short-circuit flow

Thinking “anything to the right of a pattern can use the variable” is not accurate enough. The real question is **whether any execution path can reach that point without the pattern having matched**.

### 6.1. The && operator

~~~java
value instanceof String text && text.length() > 3
~~~

The right-hand side `text.length() > 3` only runs if `instanceof` is true; thus `text` is valid on the right-hand side.

Used with a ternary:

~~~java
String answer = value instanceof String text && text.length() > 3
    ? text.toUpperCase()
    : "Other";
~~~

The `?` branch can use `text`, because the entire condition being true requires `instanceof` to be true.

However, you **must not** assume that the `:` branch can also use `text`. The entire condition can be false right at the `instanceof` check (for example `value = 123`), or false after `text.length() > 3` is checked (for example `value = "Hi"`). The `:` branch does not guarantee `text` was matched.

### 6.2. The || operator

Using negation before `||`:

~~~java
!(value instanceof String text) || text.isBlank()
~~~

If the left-hand side is true, the whole expression is immediately true and the right-hand side does not run; `text` is not bound. If the left-hand side is false, `instanceof` was true and the right-hand side is allowed to read `text`.

With a ternary:

~~~java
String answer = !(value instanceof String text) || text.isBlank()
    ? "Invalid"
    : text.trim();
~~~

The `:` branch is valid because **the entire condition being false** means:
- `!(value instanceof String text)` is false, so `text` is definitely bound;
- `text.isBlank()` is false, so we can process a non-blank string.

Compare with intentionally invalid code:

~~~java
static boolean invalid(Object value) {
    return value instanceof String text || text.isBlank();
}
~~~

The right-hand side of `||` runs when `instanceof` is **false**; at that point `text` does not exist. The compiler rejects the expression instead of waiting for a runtime error.

### 6.3. Quick decision table

| Condition expression `a` | State guaranteeing `text` is matched | Ternary branch using `text` |
| --- | --- | --- |
| `value instanceof String text` | `a == true` | `?` |
| `!(value instanceof String text)` | `a == false` | `:` |
| `value instanceof String text && text.length() > 3` | `a == true` | `?` |
| `!(value instanceof String text) || text.isBlank()` | `a == false` | `:` |

This interpretation is based on *definitely matched*, not on guessing about a specific input.

## 7. A ternary does not keep a pattern variable in scope outside the expression

This is where conditional expressions differ from flow analysis in certain forms of `if` statements.

The snippet below **intentionally does not compile**:

~~~java
static int invalid(Object value) {
    boolean ok = value instanceof String text
        ? !text.isBlank()
        : false;
    return text.length(); // ERROR: text is outside the scope of ? :
}
~~~

Even though `ok == true` only happens for a non-blank `String`, the variable name `text` **does not exist** at the `return` statement. The compiler does not turn a computed `boolean` value into proof that a pattern variable from a previous expression remains in scope.

Another variant that also **intentionally does not compile**:

~~~java
static String invalid(Object value) {
    if (value instanceof String text ? !text.isBlank() : false) {
        return text.toUpperCase(); // ERROR: text is not in the if-body
    }
    return "Other";
}
~~~

Even when the overall `if` condition is `true`, the construct `a ? b : c` does not **introduce** `text` when true or when false under JLS rules. Therefore, the `if` statement does not receive this variable for use in its body.

If you need to use the variable in an `if`, you can write it more cleanly and correctly:

~~~java
static String corrected(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return text.toUpperCase();
    }
    return "Other";
}
~~~

Here `&&` introduces `text` when the condition is true, and `if` allows using the variable in the true branch.

If you only need to return a value from the `? :` operator, use the variable **directly in the appropriate branch**:

~~~java
static String correctedWithTernary(Object value) {
    return value instanceof String text
        ? text.toUpperCase()
        : "Other";
}
~~~

In both corrected examples, no manual casting is needed.

## 8. Nested conditional expressions and associativity

The conditional operator `? :` associates **from right to left**. The following example is typically parsed as:

~~~java
a ? b : c ? d : e
// equivalent grouping:
// a ? b : (c ? d : e)
~~~

If a pattern is declared in the condition of the **outer** expression, you can use it in the outer expression's branch as long as the path guarantees it is matched. An inner nested expression does not automatically cause the variable to go out of scope.

An example already used in the runnable program in section 5:

~~~java
return !(value instanceof String text)
    ? "Not text"
    : text.isBlank() ? "Blank" : text.trim().toUpperCase();
~~~

A clearer way to read it when there are multiple levels is to add parentheses:

~~~java
return !(value instanceof String text)
    ? "Not text"
    : (text.isBlank() ? "Blank" : text.trim().toUpperCase());
~~~

This is a snippet inside a method with return type `String` and parameter `Object value`, not a standalone Java program.

Patterns inside parentheses still preserve the true/false variable introduction rules. However, parentheses only **group operations**; they do not turn a false branch into a matched branch and do not extend a variable's scope outside the conditional expression.

For multi-level ternaries, especially when `!`, `&&`, and `||` are combined, consider rewriting them as `if/else` so readers can clearly see the execution paths and matching conditions. Readability matters more than reducing line count.

## 9. Compile-time and runtime answer different questions

Suppose `value` has declared type `Object`. With the condition `value instanceof String text`:

- The compiler knows that **when the expression is true**, `text` has type `String`. Thus, in the true branch, `text.length()` is type-safe.
- The compiler does not need to know in advance whether `value` will be `"Java"`, `42`, or `null`.
- At runtime, the `instanceof` check determines whether the expression is true or false based on the actual value.
- `null` makes `instanceof String text` false, so the false branch is chosen and `text` has no value to use.
- Being “definitely matched” is a path analysis of the **Java expression**, not a promise that external data always has the expected type.

Only one of the two branches `?` and `:` of a conditional expression is evaluated at runtime. This explains why using the variable in the matched branch is safe, yet **scope** is still decided ahead of time by the compiler.

Another mistake is thinking that if a ternary produces a `String` result, the pattern variable named `text` becomes that result. That is not the case:

~~~java
String result = value instanceof String text
    ? text
    : "fallback";
~~~

The variable `result` is a **regular local variable** holding the result of the chosen branch and has scope according to its declaration. The pattern variable `text` only exists at the locations allowed by flow scoping inside the expression, not in every statement that reads `result`.

## 10. Common mistakes

1. **Using the variable in the branch opposite to the match state.** With `value instanceof String text`, only the true branch can use `text`. With `!(value instanceof String text)`, only the false branch can use it.
2. **Using the pattern variable after the `? :` operator.** The entire ternary expression does not introduce a pattern variable into subsequent code, even if the result has type `boolean`.
3. **Assuming `||` works like `&&`.** `x instanceof String s && s.length() > 0` is valid; `x instanceof String s || s.length() > 0` is invalid because the right-hand side runs when the pattern did not match.
4. **Using the variable in the false branch of `&&`.** There are multiple reasons the whole condition can be false; you cannot infer that `instanceof` matched.
5. **Confusing it with normal local variable scope.** Pattern variable scope depends on control flow, not just curly braces `{}`.
6. **Forgetting `null`.** `null` does not match `instanceof String s`; if you follow flow scoping properly, only the matching branch can access `s`.
7. **Cramming multiple nested ternaries together.** Expressions with multiple `? :` operators are very hard to verify for scope and evaluation order; convert them to `if/else` when appropriate.
8. **Reading a non-compiling example as runnable code.** The snippets marked “ERROR” in this lesson intentionally illustrate compile-time errors; only `ConditionalScopeDemo.java` is a complete program with run commands and stdout in section 5.

## 11. Self-practice and answers

### Exercise 1 — Predict where the variable can be used

~~~java
String label = value instanceof String s
    ? "length=" + s.length()
    : "not string";
~~~

**Question:** Can `s` be used in the `:` branch? If the value is `null`, which branch runs?

**Answer:** `s` cannot be used in the `:` branch. For `null`, `instanceof` is false, so the `"not string"` branch is chosen.

### Exercise 2 — Negated condition

~~~java
String label = !(value instanceof String s)
    ? "unknown"
    : s.trim();
~~~

**Question:** Why is `s.trim()` valid even though it is in the `:` branch?

**Answer:** The entire negated condition being false means `value instanceof String s` is true. Therefore `s` is definitely bound.

### Exercise 3 — Spot the bug with ||

~~~java
String label = value instanceof String s || s.length() > 0
    ? "yes"
    : "no";
~~~

**Question:** Does the snippet above compile? What is a reasonable way to write it if you only need to confirm the value is a non-empty string?

**Answer:** It does not compile because `s` is not bound on the right-hand side of `||`. You can change it to:

~~~java
String label = value instanceof String s && !s.isEmpty()
    ? "yes"
    : "no";
~~~

### Exercise 4 — Boolean ternary inside an if

~~~java
if (value instanceof String s ? s.length() >= 2 : false) {
    System.out.println(s);
}
~~~

**Question:** Why cannot `s` be used inside the `if` block?

**Answer:** The `? :` expression does not introduce `s` when the whole expression is true. To use `s` in the `if` body, replace the condition with:

~~~java
if (value instanceof String s && s.length() >= 2) {
    System.out.println(s);
}
~~~

### Exercise 5 — Execution output

For the `normalize` method in the main program, determine the output for inputs `null`, `"   "`, and `"  Java  "`.

**Answer:** Respectively `Not text`, `Blank`, and `JAVA`. The `instanceof` check filters out `null` before any `String` method calls; the remaining branch processes the type-checked string.

## 12. Key takeaways

In `a ? b : c`, rely only on **paths that have proven the pattern matched** to use the variable:

- `a` introduces the variable when **true** ⇒ use in `b`.
- `a` introduces the variable when **false** ⇒ use in `c`.
- **The entire `a ? b : c` does not introduce pattern variables outside the expression.**

When you encounter tricky code, ask yourself: “To reach this point, was Java forced to go through a successful pattern match?” If the answer is not certain, do not use the variable there; restructure the condition for clarity.

### References

- Java SE 17 JLS `6.3.1.4 — Conditional Operator `? :`, scope rules for pattern variables: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1.4
- Java SE 21 JLS `6.3.1 — Scope for Pattern Variables in Expressions (`&&`, `||`, `!`, `? :`): https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1
- Java SE 21 JLS `15.25 — Conditional Operator: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.25
