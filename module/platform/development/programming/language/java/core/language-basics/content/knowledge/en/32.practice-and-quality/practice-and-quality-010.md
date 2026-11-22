# Common Mistakes Summary and Core Java Foundations Self-Assessment Rubric

Knowing Java syntax is only the first step. Foundational mastery shows in your ability to predict how a program runs, spot compile-time, runtime, and logic errors, explain root causes, and verify fixes. This lesson systematizes common mistakes when learning **Java 17+ (language-basics)** and provides a concrete self-assessment rubric you can practice independently.

## 1. Distinguishing three error types before fixing

| Type | Symptoms | Examples | Approach |
| --- | --- | --- | --- |
| **Compile-time error** | `javac` reports an error; no valid executable program exists yet | Missing `;`, type mismatch, calling a nonexistent method, undeclared variable | Read the line/column and the first error message; fix the cause and recompile |
| **Runtime error** | Compiles cleanly, but an execution path throws an exception or terminates abnormally | `NullPointerException`, `ArrayIndexOutOfBoundsException`, `NumberFormatException` | Read the exception type and stack trace; inspect actual data and trace the execution path |
| **Logic error** | Program finishes running, yet produces the wrong result | Integer division when decimals are needed, `<` instead of `<=`, sum overflowing `int` | Write expected output, test boundary values, compare results and trace variables |

There are also **design/maintainability flaws**: vague names, overly long methods, duplicated rules, mixed responsibilities, or inconsistent error handling. They may not cause wrong output immediately, yet they increase the risk of bugs during changes.

When debugging a failure, trace **input → condition/expression → actual result → expected result**. Avoid changing multiple places at once without knowing which change fixed the problem.

## 2. Common mistakes by topic area

### 2.1. JDK, source files, and running programs

- Confusing **JDK** with **JRE**: compiling needs `javac` from the JDK; `java` runs the program. Check versions of both.
- Filename not matching the top-level `public` class: `public class Hello` must live in `Hello.java`; Java identifiers are case-sensitive.
- Wrong entry point: for standard programs, the entry method is `public static void main(String[] args)`; missing `static` or wrong signature prevents the JVM from recognizing it.
- Calling `java Hello.java` and `java Hello` are **two different mechanisms**. `java Hello` runs the compiled class; `java Hello.java` runs a single-file source directly on JDKs supporting source-file mode.
- Wrong `package` or classpath: if the file declares `package demo;`, compile from the source root with `javac -d out demo/Hello.java` and run `java -cp out demo.Hello`, not `java Hello`.

Standalone example (no `package` declaration) saved in `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 Hello.java
java Hello
```

Stdout:

```text
Hello Java
```

If you get "cannot find symbol," changing the run path won't help: that is usually a **compile-time** error because a name or type was not recognized. If you get "Could not find or load main class," check the class name, current directory, package, and classpath.

### 2.2. Data types, expressions, and conversions

| Mistake | What actually happens | How to fix or check |
| --- | --- | --- |
| Expecting `5 / 2` to equal `2.5` | Integer division between two `int`s produces `2` | `5 / 2.0` or `(double) 5 / 2` |
| `double ratio = a / b;` with `int a, b` | Integer division happens **before** assigning to `double` | Cast before dividing: `(double) a / b` |
| Casting to `long` after multiplying two `int`s | The product may already have overflowed `int` | `(long) a * b` or `Math.multiplyExact` to detect overflow |
| Confusing `=` and `==` | `=` assigns, `==` compares values for primitives | Write clear conditions; avoid assignments inside conditions |
| Misreading `&&`/`||` precedence | `&&` has higher precedence than `||` | Add parentheses to express intent and test branches |
| Using `&` instead of `&&` on booleans | `&` evaluates both sides; `&&` short-circuits | For null guards, use `s != null && ...` |
| Thinking `final` makes an entire object immutable | `final` prevents reassigning the variable/reference, not mutating object state | Distinguish `final` from immutable objects |
| Thinking `var` is dynamic typing | `var` infers a static type for a local variable with an initializer | Later assignments must still match the inferred type |

For instance, `(long) (a * b)` can still fail because the `int` product is computed inside parentheses before casting. For currency calculations with fractional units, define rules for units and rounding; `double` is not inherently suitable for exact decimal results.

### 2.3. Branching, loops, and scope

- **Off-by-one errors:** an array of length `n` has indices `0` through `n - 1`. Use `i < array.length` when traversing an array, never `i <= array.length`.
- **Missing curly braces:** indentation does not define block scope; after an `if` without `{}`, only one statement belongs to the branch.
- **Loop condition never makes progress toward termination:** forgetting to update a counter, or updating the wrong control variable.
- **Turning independent `if`s into `if/else if` without checking semantics:** separate `if`s can both execute, whereas an `else if` chain runs at most one branch.
- **Forgetting `break` in legacy `switch`:** execution falls through into subsequent `case` blocks; Java 17's `case X ->` syntax avoids this fall-through.
- **Wrong inclusive/exclusive boundary:** `score >= 50` differs from `score > 50`; always test `49`, `50`, and `51`.

The snippet below **illustrates code inside a method**, not a standalone program:

```java
for (int i = 0; i < numbers.length; i++) {
    System.out.println(numbers[i]);
}

if (score >= 50) {
    System.out.println("PASS");
} else {
    System.out.println("FAIL");
}
```

When reading conditions, identify exact boundary values and check whether any branch is unreachable because earlier conditions already cover the domain.

### 2.4. Strings, arrays, null, and references

- `==` compares **primitive values** or **whether two references point to the same object**; to compare `String` content, use `equals`. `"Java" == new String("Java")` normally evaluates to `false` even though both strings have the same characters.
- `String` is immutable: `text.trim()`, `text.strip()`, and `text.replace(...)` return **new strings**; reassign or pass the returned value to keep the result.
- `null`, empty string `""`, and blank string `"   "` are not synonymous. `isEmpty()` checks for length 0; `isBlank()` checks for empty or whitespace-only per Java's rules.
- Guard against `null` before calling methods: `name != null && !name.isBlank()` is safe due to short-circuiting; reversing the order causes `NullPointerException`.
- Arrays use the `.length` field; `String` uses the `.length()` method. `String.length()` counts UTF-16 code units, which does not always equal user-perceived character count.
- Assigning `int[] copy = original;` creates a **reference alias**, not a copy of the elements. Use `original.clone()` or `Arrays.copyOf` for an independent 1D array copy.
- Java always passes arguments **by value**; for objects, the passed value is a copy of the reference. Hence a method can mutate the target object's state, yet reassigning the parameter variable does not change the caller's reference.

A subtle trap in string concatenation is left-to-right evaluation; inside a method context:

```java
System.out.println(1 + 2 + "3");  // 33
System.out.println("3" + 1 + 2);  // 312
```

Before predicting stdout, inspect the type and evaluation order of **each operand**, rather than reading the whole expression as numeric addition.

### 2.5. Methods, exceptions, and code quality

- Confusing parameters with arguments, or ignoring return values from methods that do not mutate the original object.
- Confusing `static` members with instance members. A `static` method has no `this` reference and cannot access instance fields directly without an object.
- Failing to validate data before `Integer.parseInt`, array indexing, or integer division by `0`. Exceptions are not valid business results.
- Catching `Exception` and silently ignoring it or returning `0` makes invalid data look like success; distinguish input errors from programming bugs, report clearly, and let callers handle appropriately.
- Using `a`, `tmp`, `x` for business variables, repeating magic numbers like `86400000`, or writing overly long methods hides rules. Prefer `timeoutMillis`, `MILLIS_PER_DAY`, and small single-purpose methods.
- Writing tests only for happy-path inputs. Include `null`, empty strings, negative numbers, both sides of bounds, invalid formats, large values, and error branches.

## 3. Java 17+ program for self-checking foundational traps

The program below runs 9 independent, clearly named checks. If any check fails, `AssertionError` fails the run immediately; therefore **you do not need `-ea`**. Save as `FoundationSelfCheck.java` with no `package` declaration:

```java
public final class FoundationSelfCheck {
    private static final int PASS_SCORE = 50;
    private static final int MAX_SCORE = 100;
    private static int passed;

    private FoundationSelfCheck() {
    }

    public static void main(String[] args) {
        check("integer division", 5 / 2 == 2 && 5 / 2.0 == 2.5);

        String separateObject = new String("Java");
        check("string equality", "Java".equals(separateObject));

        String originalText = " Java ";
        String strippedText = originalText.strip();
        check("string immutability",
                originalText.equals(" Java ") && strippedText.equals("Java"));

        int[] numbers = {1, 2, 3};
        int sum = 0;
        for (int i = 0; i < numbers.length; i++) {
            sum += numbers[i];
        }
        check("loop bounds", sum == 6);

        check("boundary scores",
                grade(49).equals("FAIL")
                        && grade(50).equals("PASS")
                        && grade(100).equals("PASS"));

        check("empty and null",
                !hasName(null) && !hasName("") && !hasName("   ")
                        && hasName(" Linh "));

        int[] originalArray = {3};
        int[] alias = originalArray;
        alias[0] = 4;
        check("reference alias", originalArray[0] == 4);

        check("integer overflow", detectsOverflow());
        check("invalid score", rejectsScore(-1) && rejectsScore(101));

        System.out.println("Summary: " + passed + "/9 PASS");
    }

    private static String grade(int score) {
        if (score < 0 || score > MAX_SCORE) {
            throw new IllegalArgumentException("score out of range");
        }
        return score >= PASS_SCORE ? "PASS" : "FAIL";
    }

    private static boolean hasName(String name) {
        return name != null && !name.isBlank();
    }

    private static boolean detectsOverflow() {
        try {
            Math.multiplyExact(Integer.MAX_VALUE, 2);
            return false;
        } catch (ArithmeticException exception) {
            return true;
        }
    }

    private static boolean rejectsScore(int score) {
        try {
            grade(score);
            return false;
        } catch (IllegalArgumentException exception) {
            return "score out of range".equals(exception.getMessage());
        }
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name + ": FAIL");
        }
        passed++;
        System.out.println(name + ": PASS");
    }
}
```

From the folder containing `FoundationSelfCheck.java`, run on Windows PowerShell/CMD, macOS, or Linux with JDK 17+:

```bash
javac -encoding UTF-8 FoundationSelfCheck.java
java FoundationSelfCheck
```

**Exact** stdout:

```text
integer division: PASS
string equality: PASS
string immutability: PASS
loop bounds: PASS
boundary scores: PASS
empty and null: PASS
reference alias: PASS
integer overflow: PASS
invalid score: PASS
Summary: 9/9 PASS
```

The program demonstrates several common pitfalls: `"Java".equals(...)` compares contents, `strip()` returns a new string, loop bounds stay within valid indices, `null` is checked safely, two array variables can alias the same object, and `Math.multiplyExact` throws `ArithmeticException` when `int` multiplication overflows.

To test your understanding further, **make intentional mutations** in a copy: change `i < numbers.length` to `i <= numbers.length`, change `grade(50)` to `score > PASS_SCORE`, or remove `name != null &&`. Observe the resulting exception or failure message and explain why. Then restore the correct code. Never ship intentionally broken versions in real applications.

## 4. Foundational self-assessment rubric

Score each criterion on the same scale: **0 points** = cannot do it yet or only guessing; **1 point** = can do it with docs/hints but cannot fully explain why; **2 points** = can explain, write, and test examples correctly without hints. Maximum score is **24 points**.

| No. | Criterion | Practical evidence for self-grading |
| --- | --- | --- |
| 1 | JDK and program execution lifecycle | Compile/run with `javac` and `java`; explain `.java`/`.class` files, class names, `main`, packages |
| 2 | Syntax, naming conventions, and variable scope | Write valid Java classes and methods; distinguish locals, fields, and `static`; use meaningful names |
| 3 | Primitive types, reference types, and casting | Explain `int`/`long`/`double`/`boolean`/`String`; recognize widening/narrowing and data loss risks |
| 4 | Operators and precedence | Predict integer division, string concatenation, `&&`, `||`, increment/decrement; parenthesize intent clearly |
| 5 | Conditionals and boundary handling | Write `if/else`, `switch`, test values right below, on, and above thresholds |
| 6 | Loops and arrays | Traverse arrays without out-of-bounds errors, accumulate sums accurately, explain `break`/`continue` |
| 7 | Methods and parameter passing | Extract small methods, use parameters/returns properly; explain Java pass-by-value |
| 8 | Strings, null, and references | Use `equals`, `isBlank`, prevent NPEs, distinguish aliases from copies and `String` immutability |
| 9 | Handling invalid input | Distinguish invalid format from invalid range; verify intentional exceptions |
| 10 | Large numbers and type limits | Explain `int` overflow, promote to `long` before arithmetic, use `Math.multiplyExact` when needed |
| 11 | Reading errors and evidence-based debugging | Classify compile/runtime/logic bugs; rely on error output and reproducers instead of guessing |
| 12 | Code quality and basic testing | Format consistently, avoid magic numbers, predict stdout, and test at least one edge case |

**How to interpret the reference score:**

- **0–11/24:** strengthen core syntax and practice compiling/running small exercises independently. Pick the 0-point criteria and rebuild from scratch.
- **12–19/24:** you have a foundation with gaps. Focus on 0–1 point criteria; after every bug fix, add a test reproducing the old failure.
- **20–24/24:** ready for more complex practice exercises. Still validate your skills through self-written code and abnormal-input handling, not self-scores alone.

This scale is a **learning rubric**, not a certification or guarantee of professional competence. Scores mean something only when backed by runnable code and independent explanations.

## 5. Capstone practice exercise to verify mastery

**Self-practice prompt:** Write a Java program that reads (or simulates) a list of integer scores from `0` to `100`, classifies a score of `50` or higher as passing, and computes the passing count and pass rate. The program must handle empty lists and invalid data.

**Verifiable completion criteria:**

1. For `[49, 50, 100]`, the passing count must be `2` and the pass rate `2 / 3.0` (about `66.67%` when formatted to two decimal places). Do not let integer division yield `0` before converting to `double`.
2. For an empty list, never divide by `0`; return `0` per a stated contract or a "no data" state.
3. On `-1` or `101`, clearly reject/report the error; never silently clamp to `0` or `100`.
4. If parsing from strings, handle `null`, `""`, `"abc"`, and numbers outside `int` range.
5. Proper loop bounds, meaningful variable names, clean compile/run; at least 6 test cases covering normal, empty, just-below-boundary, exact-boundary, out-of-bounds, and invalid-format inputs.

Review afterward:

- Can I explain **why** each branch and operation produces its result?
- Can I distinguish compile-time errors, runtime errors, and wrong-output logic bugs?
- Did I test abnormal inputs and fix bugs using error messages/stack traces?
- Can I rerun all tests after changing a single line without checking everything purely by eye?

If any item is still shaky, turn that item into a small test case with **clear inputs and expected outputs**. Mastering Core Java starts with accurately explaining and verifying the behavior of small programs before scaling up complexity.
