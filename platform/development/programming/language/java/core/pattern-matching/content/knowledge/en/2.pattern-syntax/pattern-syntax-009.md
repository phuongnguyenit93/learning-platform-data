# How Pattern Matching Differs from Statement Execution in Java

## 1. Two Different Things: Matching a Pattern and Executing Statements

In Java, **pattern matching** answers the question: "Does this value match the declared pattern; and if it matches, which variables are extracted?" **Statement execution** is when the program actually runs statements such as variable assignments, method calls, printing results, `return`, or `throw` according to the control flow.

Java 17 example:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Here there are three roles to distinguish:

1. `String text` is a **type pattern**: it describes the type to match and the variable name that receives the value when matched.
2. `value instanceof String text` is a **pattern-testing expression**: it evaluates `value`, checks its runtime type; when it matches, it binds `text`, and the expression evaluates to `true`.
3. `if (...) { ... }` is a **control-flow statement**: only when the condition is `true` does Java execute the `System.out.println(...)` statement in the body branch.

**A pattern matching does not mean any statement is automatically executed.** A pattern does not contain an action to "print", "call a service", or "save data". The action lies in the `if` body, a `switch` branch, or another statement written by the developer.

The example above assumes `value` has already been declared in the scope enclosing the snippet. If `value` is not a `String` or is `null`, the `instanceof` condition is `false` and the print statement does not run.

## 2. A Pattern Is Used Inside an Expression; a Statement Decides What Will Run

### A Pattern Is Not a Standalone Statement

In Java 17, a type pattern such as `String text` is not itself a statement. The valid check structure is:

```java
boolean hasText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

This is a **logically complete method placed inside a class**. `instanceof` and `&&` produce a Boolean value for the `return` statement to return. If `value` is an empty string or all whitespace, the pattern `String text` can match, yet *the entire condition* still evaluates to `false` because `!text.isBlank()` is false.

Conversely, the following line is not a valid expression statement in Java:

```java
value instanceof String text; // Compile error: not a statement
```

The reason is that a type-comparison expression does not belong to the group of expressions allowed to stand alone as a Java expression statement. Placing it where a Boolean expression is expected—such as an `if` condition, the `&&` operator, a Boolean assignment, or `return`—is what makes it syntactically valid.

### Testing a Pattern and Executing the `if` Body Are Two Steps

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println("Đủ dài: " + text);
} else {
    System.out.println("Không thỏa điều kiện");
}
```

There are **three distinct cases**:

- If `value` is `"java"`, the pattern matches and the length condition is true: the first branch runs.
- If `value` is `"hi"`, the pattern **still matches**, but the length condition is false: `else` runs.
- If `value` is `42` or `null`, the pattern does not match: the right-hand side of `&&` is not evaluated; `else` runs.

Therefore, do not treat "the pattern match succeeded" and "the `if` body ran" as synonymous when the condition also contains other checks.

## 3. A Runnable Java 17 Program: Observing Step by Step

Create the file `PatternMatchingVsExecution.java`:

```java
public class PatternMatchingVsExecution {
    private static int reads = 0;

    static Object read(Object input) {
        reads++;
        System.out.println("read " + reads);
        return input;
    }

    static void inspect(Object input) {
        boolean typeMatch = input instanceof String;
        System.out.println("typeMatch=" + typeMatch);

        if (read(input) instanceof String text && text.length() >= 4) {
            System.out.println("THEN " + text.toUpperCase());
        } else {
            System.out.println("ELSE");
        }
    }

    public static void main(String[] args) {
        inspect("java");
        inspect("hi");
        inspect(7);
        inspect(null);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac PatternMatchingVsExecution.java
java PatternMatchingVsExecution
```

Exact stdout:

```text
typeMatch=true
read 1
THEN JAVA
typeMatch=true
read 2
ELSE
typeMatch=false
read 3
ELSE
typeMatch=false
read 4
ELSE
```

Explanation:

- `typeMatch` only records the result of the type check. It does not determine the `THEN` or `ELSE` statement because the subsequent `if` statement also has a length condition.
- `read(input)` is a **method call** and actually executes the statements inside `read` (incrementing the counter, printing `read N`). The expression on the left-hand side of `instanceof` is evaluated once per `inspect` call.
- After `read` returns, `instanceof String text` checks the returned object. Only when it matches can `text` be used on the right-hand side of `&&`.
- For `"hi"`, `typeMatch=true` proves the type check succeeded, but the `THEN` statement is not executed because `text.length() >= 4` is false.
- For `7` and `null`, the type check fails. Thanks to short-circuit evaluation of `&&`, Java does not attempt to call `length()` on an unbound variable.

**Note on side effects:** the type-checking pattern itself does not call `println`, but **the expression supplying the value to the pattern can have side effects**; here `read(input)` runs before the pattern check. Additional check expressions (for example, a method call in `&&`) can also have side effects. You should not claim that "a pattern-matching expression never has side effects" when the operand itself or surrounding conditions can execute code.

## 4. Flow Scoping: Variables Are Only Usable on Paths Where the Match Succeeded

Pattern matching does more than shorten casts. The Java compiler also tracks **the locations where pattern matching has definitely succeeded**.

### Valid: `&&`

```java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.charAt(0));
}
```

When Java evaluates the right-hand side of `&&`, the left-hand side is already `true`. The variable `text` is definitely bound to a `String` value, so it is allowed to be used.

### Invalid: `||` as follows

```java
if (value instanceof String text || text.isEmpty()) {
    System.out.println("X");
}
```

This snippet **does not compile**: the right-hand side of `||` is evaluated when the left-hand side is `false`; on that path, the pattern did not match, so `text` is not in scope to be used.

### Valid: the Non-Matching Branch Ends with `return`

```java
static int safeLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

If control reaches `return text.length()`, the non-matching branch has already terminated. The compiler proves that `text` has been bound. Therefore, this code is valid in Java 17.

Compare this with a regular variable declaration:

```java
String text = (String) value;
System.out.println(text.length());
```

Here, the cast and declaration are parts of a **variable declaration statement** executed when control flow reaches it. If `value` is an `Integer`, the cast can throw a `ClassCastException`. With `if (value instanceof String text)`, the type check and variable binding belong to the conditional expression, so the `if` body only runs when it has matched.

## 5. Pattern Matching in `switch`: Select a Branch First, Then Execute

Starting in **Java 21**, pattern matching for `switch` is a standard feature. Here the distinction is even clearer:

- `case String text` is the pattern used to **determine which case matches**.
- `when ...` (if present) is a guard condition that must be satisfied after the type pattern has matched.
- The part to the right of `->` is the **action of the selected branch**. In a `switch` statement, that can be a method-call statement or a block of statements.

Java 21 example, placed in the file `PatternSwitchVsExecution.java`:

```java
public class PatternSwitchVsExecution {
    static void describe(Object value) {
        switch (value) {
            case null ->
                System.out.println("NULL");
            case String text when text.isBlank() ->
                System.out.println("BLANK");
            case String text ->
                System.out.println("STRING " + text.length());
            case Integer number ->
                System.out.println("INT " + number);
            default ->
                System.out.println("OTHER");
        }
    }

    public static void main(String[] args) {
        describe("abc");
        describe("");
        describe(12);
        describe(null);
        describe(1.5);
    }
}
```

Commands to run with **JDK 21 or later**:

```bash
javac PatternSwitchVsExecution.java
java PatternSwitchVsExecution
```

Stdout:

```text
STRING 3
BLANK
INT 12
NULL
OTHER
```

For an empty string, the pattern `String text` matches; the guard `text.isBlank()` is true, so the `BLANK` branch runs. For `"abc"`, the guard is false, so Java moves on to check `case String text` and runs `STRING 3`. Both branches contain a `String` type pattern, yet **only one branch is executed** because `switch` decides the branch and the `->` syntax does not fall through.

Case order matters: placing `case String text ->` (without a guard) before `case String text when text.isBlank() ->` would shadow the guarded case and cause a compile error because the case is dominated. `case null` is handled separately; by contrast, `null instanceof String text` is always `false`.

**Version distinction:** pattern matching for `instanceof` became standard in **Java 16**; the `if` examples above use Java 17. The `case String text` and `when` syntax in `switch` can only be used directly as shown with **Java 21 or later**. Do not compile this `switch` example as-is with a Java 17 `javac` in normal mode.

## 6. Comparison Table of the Two Concepts

| Aspect | Pattern matching | Statement execution |
| --- | --- | --- |
| Role | Tests a value against a pattern; binds variables if it matches | Runs a statement or block of statements when control flow reaches it |
| Examples | `value instanceof String text`; `case String text` | `if (...) { println(...); }`; `return`; `switch` branch body |
| Direct result | For `instanceof`: `true`/`false` and variable binding; for `switch`: the pattern helps select a case | Can call methods, mutate state, print to the screen, return a value, or throw an exception |
| When it does not match | Does not bind pattern variables for that path | The statement in the corresponding branch may not run; `else` or another case may run |
| Variable scope | Depends on paths where the compiler proves the match succeeded | Normally declared variables follow block scope and definite assignment rules |
| Independence | A pattern requires a syntactic context such as `instanceof` or a `case` label | A statement is an executable construct allowed by Java in statement positions |
| Side effects | The type check/variable binding itself does not require an external-effect statement; the input expression or guard may have side effects | Depends on the specific action: may or may not have side effects |

**Note:** `switch` also has a *switch expression* form, in which the selected branch produces a value (possibly using `yield` in a block branch). Even when the result is an expression value rather than a print statement, the pattern still only determines the matching condition; the behavior of the branch is determined by the `switch` construct.

## 7. Misconceptions to Avoid

1. **"If the match succeeds, the `if` body always runs."** False when the condition has `&&`, a guard, or additional checks. The match can be true while the overall condition is still false.
2. **"`String text` is a standalone cast statement that runs on its own."** False. It is a pattern appearing in an allowed context; `text` can only be used on paths where the match succeeded. It is not a separate cast statement.
3. **"Pattern matching automatically calls the corresponding handler method."** False. Calls to `println`, file writes, or business logic must be written in the selected statement or expression.
4. **"Every expression involving pattern matching has no side effects."** False if the operand is a method call, or if a guard condition contains a call with side effects. Those expressions must be evaluated under normal Java execution rules.
5. **"Pattern matching is like regex or a script-execution mechanism."** No. `instanceof String text` is a **type pattern** based on object type; it does not interpret strings as regex and does not create arbitrary execution flows.
6. **"`null` is treated as matching every reference type."** False for `instanceof`. Pattern `switch` in Java 21 can have a separate `case null`.
7. **"Using a pattern means faster execution."** There is no general speed guarantee. The main benefit of the syntax is expressing type checks, variable bindings, and scope more clearly; actual performance depends on the code and the JVM.

## 8. How to Think When Reading or Writing Code

When encountering a snippet with a pattern, read it in this order:

1. **Which value is evaluated?** For example, `read(input)` is called before the type check.
2. **What condition does the pattern test?** For example, `String text` matches when the value is an object compatible with `String` and is not `null`.
3. **When it matches, which variables are usable where?** Determine scope based on flow scoping, `&&`, and control branches.
4. **What else does the overall condition or guard require?** A successful match does not guarantee the entire condition is true.
5. **Which action does the `if`/`switch` construct select?** Only from here can you determine which statements actually run and whether there are side effects.

Self-check example:

```java
Object value = "hi";
if (value instanceof String text && text.length() > 3) {
    System.out.println("A");
} else {
    System.out.println("B");
}
```

The result is `B`. `String text` **matched**, but the condition `text.length() > 3` is false, so **the statement in the `else` branch is executed**. This is the core difference between **pattern matching** and **statement execution** in Java.