# Expression Body and Block Body in Java Lambdas

## 1. Learning objectives

A lambda expression provides an implementation of the **single abstract method** (SAM) of a functional interface. The part to the right of the `->` arrow is called the **lambda body**. Java allows writing the body in two main forms:

- **Expression body:** a single expression, written concisely, without curly braces and without `return`.
- **Block body:** a `{ ... }` block consisting of statements; it can declare variables, branch, handle exceptions, and use `return` according to the SAM's return type.

These are two syntactic forms for the same lambda concept, **not two different kinds of functional interfaces**. Choose the form based on the work to be done, readability, and the parameter/return value contract.

After this lesson, learners should be able to write and convert between both body forms; determine when `return`, `;`, and curly braces are needed; explain the difference between value-returning lambdas and `void` lambdas; and identify common compilation errors.

Standalone examples use **JDK 17 or later**.

## 2. General structure of a lambda expression

General syntax:

~~~java
(parameters) -> expression

(parameters) -> {
    statements
}
~~~

These are **syntax patterns**, not two standalone Java statements. The left side of `->` is the parameter list and the right side is the body. Parameter types, valid return types, and the ability to throw checked exceptions are determined by the **functional interface serving as the target type**, such as `Function<Integer,Integer>` or `Consumer<String>`.

Example with `java.util.function.Function`:

~~~java
Function<Integer, Integer> square = number -> number * number;
~~~

`Function<Integer,Integer>` has the SAM `Integer apply(Integer value)`. The compiler understands `number` as an `Integer`; the expression `number * number` performs the necessary unboxing and then boxing to return a result matching `Integer`.

Writing the same logic as a block body:

~~~java
Function<Integer, Integer> square = number -> {
    int result = number * number;
    return result;
};
~~~

The two illustrative examples are placed **separately** in a context where `java.util.function.Function` is imported; do not declare two `square` variables in the same scope in an actual program.

Easily confused tokens:

| Component | Meaning |
| --- | --- |
| `->` | Separates lambda parameters and body |
| `{ ... }` | Starts/ends a block body |
| `return expression;` | Returns a value from a block body when the SAM requires a result |
| `return;` | Exits a `void`-compatible block body |
| `;` after the entire lambda | Terminates the variable declaration/assignment statement or enclosing call according to the surrounding syntax |
| `;` inside the block | Terminates each Java statement inside the block |

**Key point:** the semicolon after `}` in `Function<Integer,Integer> f = x -> { return x + 1; };` terminates the **variable declaration**, whereas the `;` after `return x + 1` terminates the **`return` statement**.

## 3. Expression body: concise when a single expression suffices

### 3.1. Writing without `{ }` and without `return`

The following examples are all expression bodies:

~~~java
Function<Integer, Integer> doubleIt = n -> n * 2;
Predicate<String> nonEmpty = text -> !text.isEmpty();
Supplier<String> greeting = () -> "Xin chào";
Comparator<Integer> ascending = (a, b) -> Integer.compare(a, b);
Consumer<String> print = text -> System.out.println(text);
~~~

These are **declarations inside a method** after importing `java.util.function.*` and `java.util.Comparator`. Each right-hand side of `->` contains exactly **one expression**:

- `n * 2` is an arithmetic expression; its value is the result of `Function.apply`.
- `!text.isEmpty()` returns `boolean`, matching the SAM `Predicate.test`.
- `"Xin chào"` is a constant expression, matching `Supplier.get`.
- `Integer.compare(a, b)` returns `int`, matching `Comparator.compare`.
- `System.out.println(text)` is a `void` method call, matching `Consumer.accept`.

In an expression body, **do not write** `return`. For example, `n -> return n * 2;` is a syntax error. If you want to use `return`, you must switch to a block body.

### 3.2. Ternary conditionals and method calls

An expression body is not limited to simple arithmetic; it can be a conditional expression or another method call:

~~~java
Function<Integer, String> classification =
        n -> n >= 0 ? "không âm" : "âm";

Function<String, Integer> length =
        text -> text == null ? 0 : text.length();
~~~

Conditional `?:` expressions are still **a single expression**. Prefer this style when both branches are short and their meaning is clear. If there are many branches, multiple processing steps, or error checks, a block body is usually easier to follow.

### 3.3. The return type cannot be guessed from `->` alone

Compare:

~~~java
Function<String, Integer> count = text -> text.length();
Consumer<String> log = text -> System.out.println(text);
~~~

With `Function`, `apply` returns `Integer`, so the expression must produce a compatible value. With `Consumer`, `accept` returns `void`, so the lambda performs an action. **Concise syntax does not determine the return type; the functional interface determines the contract**.

A lambda without a clear target type usually cannot be inferred, for example:

~~~java
// Invalid: missing target type for the lambda.
var action = x -> x + 1;
~~~

Fix by providing a target type:

~~~java
Function<Integer, Integer> action = x -> x + 1;
~~~

The invalid examples in this lesson are only for syntax analysis and **must not be included in a runnable program**.

## 4. Block body: multiple statements and control flow

### 4.1. Using a `{ ... }` block and declaring local variables

When intermediate steps are needed:

~~~java
Function<String, String> normalize = raw -> {
    String value = raw == null ? "" : raw.trim();
    String upper = value.toUpperCase(java.util.Locale.ROOT);
    return upper;
};
~~~

A block body can declare variables, call methods, and return a result. The variables `value` and `upper` live within the lambda block's scope, helping to name business steps.

### 4.2. For a value-returning SAM: normal paths must return a result

A block for `Function<T,R>` must return a value compatible with `R` on every path that can complete normally; a path may terminate with an exception instead of `return`. Valid example:

~~~java
Function<Integer, String> sign = n -> {
    if (n < 0) {
        return "âm";
    }
    if (n == 0) {
        return "không";
    }
    return "dương";
};
~~~

An **invalid** example because there is a branch that does not return a value:

~~~java
Function<Integer, Integer> absolute = n -> {
    if (n < 0) {
        return -n;
    }
    // Missing return when n >= 0
};
~~~

Fix by adding `return n;` at the end of the block. Java checks return paths during compilation, without waiting for runtime to hit the failing case.

### 4.3. For a `void` SAM: do not return a value

Example for `Consumer<String>`:

~~~java
Consumer<String> printIfPresent = text -> {
    if (text == null || text.isBlank()) {
        return; // Exit early from the void lambda.
    }
    System.out.println(text.trim());
};
~~~

`return;` has no expression after it, fitting `void`. Writing `return text;` in the block of `Consumer.accept` is a compile error. You can omit `return;` when the block naturally runs to the end and completes normally.

With `Runnable` or `Consumer`, the block often consists only of statements like logging, saving data, or sending events. Not returning a result **does not mean side effects are safe or advisable in every case**.

### 4.4. Block body and the `throw` statement

If an input error occurs, you can throw an exception:

~~~java
Function<Integer, Integer> safeReciprocal = n -> {
    if (n == 0) {
        throw new IllegalArgumentException("n must not be zero");
    }
    return 100 / n;
};
~~~

The `throw` statement terminates the path with an exception and does not require a `return` value for that branch. Other cases must still return a result compatible with the target type. If the lambda has a checked exception, it must match the SAM's `throws` declaration or be handled, just like regular Java methods.

## 5. Distinguishing `void` and value-returning expressions

This is the most easily confused detail: **an expression body is compatible with a `void` SAM when the expression belongs to the *statement expression* group** in Java syntax. This group includes method calls, assignments, prefix or postfix increment/decrement, and object creation expressions using `new`. A value produced by some expressions can still be **discarded** in a `void` context.

Valid example:

~~~java
List<String> names = new ArrayList<>();

// List.add returns boolean; Consumer.accept returns void.
// The boolean value of add(...) is ignored.
Consumer<String> addName = name -> names.add(name);

addName.accept("An");
~~~

The code above requires importing `java.util.List`, `java.util.ArrayList`, and `java.util.function.Consumer`, placed inside a method. It is valid because `names.add(name)` is a **method invocation expression**, which is also a statement expression. Do not assume that every value-returning expression can be used for `Consumer`.

Invalid example:

~~~java
// Not a statement expression, cannot be the body of a void lambda.
Consumer<Integer> wrong = n -> n + 1;
~~~

Fix depending on **intent**:

~~~java
// If you need the new numeric result:
Function<Integer, Integer> plusOne = n -> n + 1;

// If you need to perform a print action:
Consumer<Integer> printPlusOne = n -> System.out.println(n + 1);
~~~

The block form makes the boundary clearer:

~~~java
Consumer<Integer> printBlock = n -> {
    int result = n + 1;
    System.out.println(result);
};
~~~

### Rules table by SAM type

| Target type | Expression body | Block body | Notes |
| --- | --- | --- | --- |
| `Function<Integer,Integer>` | `n -> n * 2` | `n -> { return n * 2; }` | Must provide a valid `Integer` value |
| `Predicate<Integer>` | `n -> n > 0` | `n -> { return n > 0; }` | Returns `boolean` |
| `Supplier<String>` | `() -> "ok"` | `() -> { return "ok"; }` | No parameters, has a result |
| `Consumer<String>` | `s -> System.out.println(s)` | `s -> { System.out.println(s); }` | Performs an action, returns `void` |
| `Runnable` | `() -> System.out.println("go")` | `() -> { System.out.println("go"); }` | No parameters, returns `void` |

Distinguish between a **void-compatible block** and a **value-compatible block**:

- For a `void`-returning SAM, the block can complete normally or use `return;`, but cannot have `return expression;`.
- For a value-returning SAM, the block cannot have a path that completes normally without a value; every `return` statement must carry an expression of the right type.
- A block that only throws an exception on every path (no `return` and does not complete normally) can be compatible with both forms, though this is a special case. Do not use it to infer that `return;` and `return value;` are interchangeable.

## 6. Complete Java 17 program: the same logic in both body forms

Create the file **`LambdaBodiesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaBodiesDemo {
    public static void main(String[] args) {
        // Expression body: the expression result becomes the return value.
        Function<Integer, Integer> square = n -> n * n;

        // Block body: must return because Function.apply does not return void.
        Function<Integer, Integer> squareBlock = n -> {
            int result = n * n;
            return result;
        };

        // Multiple paths with explicit return values.
        Predicate<String> hasText = text -> {
            if (text == null) {
                return false;
            }
            return !text.isBlank();
        };

        // Consumer: expression body calls a void method.
        Consumer<String> greet =
                text -> System.out.println("Hi " + text);

        // Consumer: block body consists of multiple statements.
        Consumer<String> greetBlock = text -> {
            String clean = text.trim();
            System.out.println("Hi " + clean);
        };

        // Runnable takes no parameters and returns no value.
        Runnable announce = () -> System.out.println("Ready");
        Runnable announceBlock = () -> {
            System.out.println("Ready");
        };

        // List.add returns boolean, but the call can discard the result
        // when used as the expression body of a Consumer.
        List<String> names = new ArrayList<>(List.of("An"));
        Consumer<List<String>> append = list -> list.add("Binh");

        System.out.println(square.apply(5));
        System.out.println(squareBlock.apply(5));
        System.out.println(hasText.test(" "));
        System.out.println(hasText.test(" Java "));
        greet.accept("Mai");
        greetBlock.accept("  Mai  ");
        announce.run();
        announceBlock.run();
        append.accept(names);
        System.out.println(names);
    }
}
~~~

In a terminal with JDK 17 or later:

~~~bash
javac -encoding UTF-8 LambdaBodiesDemo.java
java LambdaBodiesDemo
~~~

**Exact stdout:**

~~~text
25
25
false
true
Hi Mai
Hi Mai
Ready
Ready
[An, Binh]
~~~

Explanation:

1. Both `square` and `squareBlock` multiply `5 * 5`, so both print `25`. The block form requires `return`, while the expression form does not write `return`.
2. `hasText.test(" ")` returns `false` because the string contains only whitespace; `hasText.test(" Java ")` returns `true`.
3. Both `Consumer`s produce the same greeting; one calls `println` directly, while the other normalizes first.
4. Both `Runnable`s print `Ready`. The blocks complete normally because the `run` method returns `void`.
5. `append` uses the call `list.add("Binh")` as a valid expression body for `Consumer<List<String>>`; the boolean result of `add` is ignored. The list is modified, so it prints `[An, Binh]`.

The example intentionally includes a side effect to illustrate `void` compatibility; in real data design, mutating a collection outside a pipeline by default is not a safe choice, especially with parallel processing.

## 7. Common syntax and compilation errors

### 7.1. Adding `return` to an expression body

~~~java
// Invalid: return is only a statement inside a block.
Function<Integer, Integer> f = n -> return n * 2;
~~~

Fix to `n -> n * 2` or `n -> { return n * 2; }`.

### 7.2. Using curly braces but forgetting `return`

~~~java
// Invalid: this is a block, Function requires returning a result.
Function<Integer, Integer> f = n -> { n * 2; };
~~~

Besides missing `return`, a standalone addition/multiplication `n * 2;` is also not a valid *statement expression*. Fix:

~~~java
Function<Integer, Integer> f = n -> {
    return n * 2;
};
~~~

### 7.3. Misplacing semicolons

~~~java
// Valid:
Function<Integer, Integer> a = n -> n + 1;
Function<Integer, Integer> b = n -> { return n + 1; };

// Invalid: the ; becomes a misplaced part in the expression body.
Function<Integer, Integer> c = n -> n + 1;;
~~~

On line `c`, the **second `;`** is a separate empty statement if placed where a statement is allowed; it does not necessarily cause a compile error. However, it is redundant syntax and is not a way to express a two-statement lambda body. When using a block, the `;` inside belongs to each statement. When using an expression, only one `;` is needed to terminate the variable declaration.

### 7.4. Returning a value from `Consumer`

~~~java
// Invalid: Consumer.accept returns void.
Consumer<String> consumer = s -> { return s; };
~~~

Fix to `s -> { System.out.println(s); }` if the goal is an action, or `Function<String,String>` if you want to transform the string and receive a result.

### 7.5. Not returning on every branch of `Function`

~~~java
// Invalid: n = 0 reaches the end of the block without returning.
Function<Integer, Integer> f = n -> {
    if (n > 0) {
        return n;
    }
};
~~~

Add `return 0;` or implement full conditional branches.

### 7.6. Using multiple statements without a block

~~~java
// Invalid: missing { } for two separate statements.
Consumer<String> action = s -> System.out.println(s); System.out.println("done");
~~~

The line above can be parsed by Java as **two statements outside the lambda** if inside a method: `action` only prints `s`, while `println("done")` runs immediately when execution reaches the next statement. It does not create a Consumer with two actions. Fix the intent:

~~~java
Consumer<String> action = s -> {
    System.out.println(s);
    System.out.println("done");
};
~~~

### 7.7. Shadowing variable names in scope

Variables declared in a lambda block are local variables and do not create an independent namespace that allows redeclaring a local variable that already exists in the enclosing scope. For example:

~~~java
int count = 10;
// Invalid: cannot declare a new local count inside the lambda block.
Runnable r = () -> {
    int count = 5;
    System.out.println(count);
};
~~~

Rename the variable inside the lambda or reorganize the scope. Outer variables used by a lambda must be `final` or **effectively final**; you cannot increment `count++` on a captured local variable from inside a lambda.

### 7.8. Ignoring checked exceptions

Both expression bodies and block bodies must obey the SAM's `throws` clause. Switching from an expression body to a block body does not automatically allow throwing `IOException` through `Consumer.accept`. For calls with checked exceptions, handle them with `try/catch` or choose a functional interface with a matching exception contract. Avoid swallowing errors just to make code compile.

## 8. When to choose an expression body vs. a block body?

| Situation | Usually suitable form | Reason |
| --- | --- | --- |
| Single-step calculation/transformation | Expression | Short, result is immediately visible |
| Simple conditional predicate | Expression | Few branches, easy to verify |
| Calling a `void` method | Expression | Concise when the method name is clear |
| Has intermediate variables to name | Block | Makes processing steps explicit |
| Has multiple `if`/`switch` branches or error checks | Block | Clear control flow and return handling |
| Has `try/catch` or multiple intentional side effects | Block | Easy to see error handling and order |
| Lambda is too long or nested | Extract into a separate method | Reduces cognitive load, easy to test |

Example of equivalent conversion:

~~~java
Function<String, Integer> lengthA =
        text -> text == null ? 0 : text.trim().length();

Function<String, Integer> lengthB = text -> {
    if (text == null) {
        return 0;
    }
    String trimmed = text.trim();
    return trimmed.length();
};
~~~

Both return `0` for `null` and `4` for `" Java "`. The expression version is concise; the block version makes it easy to add checks, logs, or debugger breakpoints. Do not automatically turn every short lambda into a block, nor force all complex logic into a single expression.

### Debugging tips

With a block, you can place a breakpoint on a variable declaration line or a `return` branch to inspect intermediate values. If an expression body is hard to debug, temporarily convert it to a block or extract the logic into a named method. When side effects are present, consider execution order and exceptions, especially if the lambda is passed to a parallel Stream.

## 9. Self-practice exercises and suggested answers

**Exercise 1 — Write both forms for the same logic.** Create a `Function<Integer,Integer>` that increments a number by 1 using an expression body and a block body. Test with `5`; the result must be `6`.

Hint:

~~~java
Function<Integer, Integer> shortForm = n -> n + 1;
Function<Integer, Integer> longForm = n -> {
    return n + 1;
};
~~~

**Exercise 2 — Multi-branch condition.** Write a `Function<Integer,String>` that classifies scores: below 5 is `"Fail"`, from 5 to below 8 is `"Pass"`, and the rest is `"Excellent"`. Use a block body and ensure all branches return a result. Test with `4`, `6`, `9`.

**Exercise 3 — Early-exit Consumer.** Write a `Consumer<String>` that only prints when the string is non-`null` and non-empty after trimming whitespace. Use `return;` to skip invalid input. Explain why `return value;` is invalid.

**Exercise 4 — Identify errors.** What should each snippet below be replaced with?

~~~java
// A: missing return in a value-returning block.
Function<Integer, Integer> a = n -> { n + 1; };

// B: void block returning a value.
Consumer<String> b = text -> { return text; };

// C: addition is not a statement expression for a void SAM.
Consumer<Integer> c = n -> n + 1;
~~~

Suggested answers: A uses `return n + 1;`; B performs an action like `System.out.println(text);` or changes to `Function`; C changes to `Function<Integer,Integer>` if a result is needed, or a `Consumer` calling `println` if an action is needed.

**Exercise 5 — Distinguish execution timing.** Write `Runnable r = () -> { System.out.println("go"); };` and a line `System.out.println("now");` right after the declaration. Predict the output before and after `r.run()`. Solution: declaring the lambda does not run the body; the output is `now`, and only after calling `run` does `go` appear.

**Exercise 6 — Verified conversion.** Create a `Predicate<String>` checking whether a name has at least three characters after `trim`. Write it in expression and block forms, testing `null`, `"  An "`, `"  Hoa  "`. Without handling `null`, the expression may throw `NullPointerException`; both versions must have the same contract.

## 10. Checklist before finalizing a lambda

1. **What is the target type?** Which parameters does the SAM take, what type does it return, and does it declare checked exceptions?
2. **Is a single expression enough?** If yes, an expression body is usually the most concise.
3. **Are there multiple statements or branches?** If yes, use `{ ... }`.
4. **Does the SAM return a value?** With a block, every path that completes normally must have a `return expression;` of the right type.
5. **Does the SAM return `void`?** Do not return a value; if an early exit is needed, use `return;`.
6. **Is an expression body a statement expression when the SAM is `void`?** Pure addition `n + 1` is not enough; method calls like `println` or `list.add` can be valid.
7. **Are `;` semicolons in the right places?** After statements inside a block, and after the entire declaration; do not write `return` outside a block.
8. **Have `null`, exceptions, shared mutable state, and captured variables been considered?** Valid syntax does not guarantee the program is safe or business-correct.
9. **Have edge cases been tested and outputs verified?** Do not test only favorable data.

## 11. Summary

An **expression body** (`x -> expression`) is suitable when the behavior can be expressed as a single expression. If the SAM has a result, the expression's value is used as the result; if the SAM returns `void`, the expression must fit a *statement expression* context. Do not write `return` in an expression body.

A **block body** (`x -> { statements; }`) allows multiple statements and clear control flow. For a value-returning SAM, ensure valid paths return a value or throw an exception; for a `void`-returning SAM, only `return;` without a value is valid. Both forms rely on the functional interface contract and follow Java's rules on variable scope, exceptions, data types, and side effects.

For exact syntax reference, see the Java Language Specification **`15.27 Lambda Expressions`**, especially **`15.27.2 Lambda Body`** and **`15.27.3 Type of a Lambda Expression`**, along with the Javadoc for `java.util.function.Function`, `Consumer`, `Predicate`, and `Supplier`.