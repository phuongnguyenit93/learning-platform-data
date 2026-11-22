# Compile-Time Errors, Runtime Errors, and Logic Errors in Java

## 1. Three Error Types Differ in When and How They Are Detected

When writing a Java program, not every error is detected at the same stage.

| Type | Typically Detected When | Characteristic Sign | Example |
| --- | --- | --- | --- |
| **Compile-time error** | When `javac` checks the source code | Compilation fails; source code violates Java syntax, name, or type rules | `int x = "abc";` |
| **Runtime error/failure** | When the program starts or is executing | Program may throw an exception, encounter a JVM error, or terminate abnormally | Integer division by 0, out-of-bounds array access |
| **Logic error** | When checking behavior, running tests, or comparing against requirements | Program may compile and run without reporting errors, yet produce **wrong results** | Computing average as `a + b / 2` instead of `(a + b) / 2.0` |

This is a **classification for learning purposes** and does not mean every bug belongs to only one group. For example, a logic error can lead to a runtime exception on a specific input; a runtime error about a missing library may only appear when the JVM attempts to load the related class.

Basic workflow for a Java file:

```text
Source code (.java)
    |
    v
javac compiles and checks
    |--- Invalid ---------> Compile-time error (need to fix code)
    |
    v
Bytecode (.class)
    |
    v
JVM loads classes, launches, executes
    |--- Exception/error -> Runtime failure
    |
    v
Program result
    |--- Violates reqs ---> Logic error (tests/verification)
    |
    v
Result meets verified requirements
```

Having no error messages **does not prove** the algorithm is correct. You need to verify outputs, data states, and edge cases.

## 2. Compile-Time Errors: `javac` Rejects the Source Code

Compile-time errors occur when a program violates rules that the Java compiler must enforce. Common categories:

1. **Syntax:** missing `;`, missing parentheses/braces, or misplaced keywords.
2. **Names and scope:** referencing an undeclared variable, using a variable out of scope, calling a nonexistent method.
3. **Data types:** assigning a `String` to an `int`, passing an argument of the wrong type, returning the wrong type.
4. **Definite assignment before reading:** reading an uninitialized local variable (*definite assignment*).
5. **Checked exceptions:** failing to catch or declare `throws` for a checked exception that may arise.
6. **Class/file/access rules:** file name not matching the `public` top-level type name, unauthorized member access.

The examples below are **deliberately invalid lines; do not include them in the runnable program in section 5**:

```java
// Wrong type:
int age = "18"; // incompatible types: String cannot be converted to int

// Wrong name:
System.out.println(missingValue); // cannot find symbol if the name has not been declared

// Reading an unassigned local variable:
int score;
System.out.println(score); // variable score might not have been initialized

// Syntax error:
// int count = 5 // missing semicolon
```

How to fix depends on intent:

```java
int age = 18; // Use an int literal

int missingValue = 7;
System.out.println(missingValue);

int score = 0;
System.out.println(score);
```

The snippets above illustrate code inside a method body, not standalone runnable files. Note: `Integer.parseInt("18")` is one way to convert a string to a number if the real data is text, but if the content is not a valid number, the method may throw `NumberFormatException` **at runtime**. Converting strings to numbers therefore requires data validation rules.

### Checked Exception Case

When calling an API that declares a checked exception, the compiler forces the code to handle the exception or declare it to pass responsibility to the caller:

```java
import java.nio.file.Files;
import java.nio.file.Path;

class FileExample {
    static String readText() throws java.io.IOException {
        return Files.readString(Path.of("missing.txt"));
    }
}
```

`throws java.io.IOException` makes the example **compile validly**. However, if the file does not exist, calling `Files.readString` can still throw `NoSuchFileException` at runtime. **The compiler checks how exceptions are handled, not whether the runtime environment has the required files or a working network.**

### How to Read Compile-Time Errors

Run `javac -encoding UTF-8 Example.java` and read the diagnostics on the error stream (stderr). Information usually includes the file name, line number, position, and descriptions such as `cannot find symbol`, `incompatible types`, or `';' expected`. Diagnostic text can vary by JDK version, so you should not treat every compile error message as a fixed stdout string. Fix the **first meaningful error** and recompile: one missing brace or bad declaration can trigger many cascading errors on subsequent lines.

## 3. Runtime Errors: The Program Compiles but Does Not Execute as Expected

Many errors only surface when the JVM encounters a **specific value** or a **specific environmental condition**.

| Situation | Typical Java Behavior |
| --- | --- |
| `12 / 0` with integer division | `ArithmeticException` when executing the division |
| Reading `arr[arr.length]` | `ArrayIndexOutOfBoundsException` |
| Calling a method through a `null` reference | `NullPointerException` |
| `Integer.parseInt("abc")` | `NumberFormatException` |
| Opening a nonexistent file | Typically `NoSuchFileException` when using `Files.readString` |
| Casting an object to an incompatible reference type | `ClassCastException` |
| Running out of allocatable memory | May throw `OutOfMemoryError` |

An **exception** is an object describing an abnormal condition during execution; many exceptions are subtypes of `Exception` or `RuntimeException`. More serious JVM errors are typically represented by subtypes of `Error`, such as `OutOfMemoryError`. Both branches belong to `Throwable`, but **you should not catch `Error` to continue normal operation** as if it were simple bad input data.

Distinguishing **checked exceptions** and **unchecked exceptions**:

- `IOException` is a checked exception: the compiler generally requires `try/catch` or `throws`.
- `ArithmeticException`, `NullPointerException`, `NumberFormatException` are unchecked exceptions under `RuntimeException`: you do not need to declare `throws` to compile, yet they can still occur at runtime.
- `Error` and its subclasses are also unchecked under exception-checking rules, but they usually represent more severe situations and are not business errors to handle with a regular `catch`.

Some startup failures are not necessarily errors thrown from the `main` body. For example, running `java MissingClass` when no matching class exists on the classpath can cause the launcher to report that the main class could not be found or loaded. When diagnosing, distinguish **code compilation** issues from **runtime classpath/module path configuration** issues.

### When an Exception Is Uncaught

When an exception is not handled along the current call path, it propagates backward through the callers. If it reaches the top of the execution thread unhandled, the JVM typically writes the exception details and **stack trace** to stderr. A stack trace helps identify the exception type, where it was thrown, and the method call chain. Do not swallow exceptions with an empty `catch` block: doing so can hide the root cause.

Using `try/catch` **does not fix faulty logic**; it only defines how to handle an abnormal situation. For instance, an out-of-bounds index access should be fixed in the loop condition, rather than using `catch (ArrayIndexOutOfBoundsException)` to mask a programming mistake.

## 4. Logic Errors: Valid Code That Runs but Produces the Wrong Answer

This is often the hardest error type to spot because the program can terminate normally.

### Wrong Operator Precedence

```java
int a = 8;
int b = 4;
int wrong = a + b / 2;         // 10 because division is performed first
double correct = (a + b) / 2.0; // 6.0
```

`wrong` has the value `10`, not the average `6`. The bug throws no exception and is not rejected by `javac`.

### Integer Division Truncating the Fractional Part

```java
int total = 5;
int count = 2;
double wrong = total / count;   // 2.0: int division executes first
double correct = total / 2.0;   // 2.5: double-precision division
```

Even though the target variable is `double`, the expression `total / count` is still integer division when both operands have type `int`. If you want the fractional part, at least one operand must have an appropriate floating-point type.

### Boundary Conditions and Wrong Conditions

```java
int[] values = {10, 20, 30};
int sum = 0;
for (int i = 0; i < values.length - 1; i++) {
    sum += values[i];
}
// sum == 30, whereas the full sum of all three elements should be 60.
```

The loop above runs validly but omits the last element. Another condition like `i <= values.length` can cause a **runtime exception** because it attempts to access the element at index `values.length` (out of bounds).

With `boolean`, the statement `if (enabled = true)` can **compile validly** because an assignment evaluates to a `boolean` value, yet it both mutates `enabled` and forces the condition to `true`. To test the value, use `if (enabled)` or an appropriate comparison.

Logic errors can also come from misunderstanding requirements (for example, "at least 18 years old" coded as `age > 18`), wrong units of measurement, integer overflow, sorting in the wrong direction, or assuming data is never empty/null.

## 5. Standalone Java 17+ Program to Observe Runtime Error and Logic Error Groups

Create a file named **`ErrorKindsDemo.java`**:

```java
public class ErrorKindsDemo {
    static int wrongAverage(int a, int b) {
        return a + b / 2; // Logic error: missing parentheses
    }

    static double correctAverage(int a, int b) {
        return (a + b) / 2.0;
    }

    public static void main(String[] args) {
        int a = 8;
        int b = 4;

        int wrong = wrongAverage(a, b);
        double correct = correctAverage(a, b);
        System.out.println("Trung binh sai: " + wrong);
        System.out.println("Trung binh dung: " + correct);

        int divisor = 0;
        try {
            int quotient = 12 / divisor;
            System.out.println(quotient);
        } catch (ArithmeticException ex) {
            System.out.println("Loi chia: " + ex.getClass().getSimpleName());
        }

        int[] values = {3, 5};
        try {
            System.out.println(values[2]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("Loi chi so: " + ex.getClass().getSimpleName());
        }

        try {
            int parsed = Integer.parseInt("abc");
            System.out.println(parsed);
        } catch (NumberFormatException ex) {
            System.out.println("Loi chuyen so: " + ex.getClass().getSimpleName());
        }

        int total = 5;
        int count = 2;
        System.out.println("Chia nguyen sai: " + (double) (total / count));
        System.out.println("Chia thuc dung: " + (total / (double) count));

        System.out.println("Chuong trinh tiep tuc.");
    }
}
```

Open a terminal in the folder containing the file, using **JDK 17 or later**. On Windows PowerShell/CMD or Linux/macOS:

```bash
javac -encoding UTF-8 ErrorKindsDemo.java
java ErrorKindsDemo
```

**Exact stdout** (successful compilation prints no message):

```text
Trung binh sai: 10
Trung binh dung: 6.0
Loi chia: ArithmeticException
Loi chi so: ArrayIndexOutOfBoundsException
Loi chuyen so: NumberFormatException
Chia nguyen sai: 2.0
Chia thuc dung: 2.5
Chuong trinh tiep tuc.
```

This snippet **deliberately omits code with compile-time errors** from the file so the program can run standalone. The three middle exceptions are caught right inside `main`, so they do not print a default stack trace, and the program continues. If you remove one `catch` block, the corresponding exception can cause the `main` execution path to terminate early. The two average and integer-division calculations illustrate logic errors, because the JVM cannot know on its own which business result is right.

You should not judge this code as "bug-free" just because stdout appears normally: the purpose of the example is to observe the difference between **silently wrong results** and **caught runtime exceptions**.

## 6. Process for Identifying and Fixing Errors

### Step 1 — Identify the Stage

- **`javac` fails:** focus on syntax errors, names, types, access modifiers, uninitialized variables, or unhandled checked exceptions.
- **Compiles cleanly, but fails at runtime with an error/exception:** read the stack trace, error line, input conditions, and environment state.
- **Runs to completion, but output is wrong:** reproduce the input, calculate the expected result by hand, and inspect the algorithm steps.

### Step 2 — Minimize the Example

Isolate the failing code into the smallest program that can reproduce the issue. Use simple input values and easily verifiable outputs. In Java, add `System.out.println` to inspect state while learning, or use an IDE debugger to set breakpoints, inspect variables, and step line by line.

### Step 3 — Test Both Boundaries and Abnormal Cases

Which cases to test depends on the problem: `0`, negative numbers, empty arrays, single-element arrays, `null`, invalid strings, very large values, nonexistent resources. For a method that computes an average, test `(8,4)`, `(5,2)`, two negative numbers, and values that could overflow on addition when using `int`.

### Step 4 — Write Tests with Concrete Expected Results

For example, a manual check inside `main`:

```java
double actual = (8 + 4) / 2.0;
double expected = 6.0;
if (Double.compare(actual, expected) != 0) {
    throw new AssertionError("Average mismatch");
}
```

If the expression is changed to `8 + 4 / 2.0`, the condition detects that `10.0` does not match `6.0`. For general floating-point arithmetic, you should usually compare within an appropriate **tolerance** rather than only checking exact `double` equality; this simple arithmetic example happens to produce an exact representable result.

You can organize tests with JUnit in real projects. Tests cannot prove the absolute absence of bugs for every possible input, but they help catch regressions when modifying code.

### Step 5 — Fix the Cause, Not Just the Symptom

If a loop misses an element, fix the condition; if data can be `null`, decide whether to allow `null` or check/reject it; if division by 0 occurs, determine the requirement for handling a zero divisor. Avoid empty `catch (Exception ex) { }` blocks or returning arbitrary default values, as they make bugs harder to diagnose.

## 7. Tools and Diagnostics Worth Knowing

| Tool/Practice | Purpose |
| --- | --- |
| `javac -encoding UTF-8 File.java` | Compile a Java file with the proper source encoding |
| `javac -Xlint:all File.java` | Enable additional supported compiler warnings |
| `java ClassName` | Execute a class with an appropriate `main` method |
| Breakpoints and debugger | Inspect variable values, call stack, and execution steps |
| Stack trace | Identify the location and call chain leading to an exception |
| Unit tests | Verify outputs/states against expected data |
| Contextual logging | Record useful information without hiding errors |

**Compiler warnings are not compile errors**: by default, many warnings still allow `.class` files to be generated. Nor can you claim that `javac -Xlint:all` will find every logic error. Distinguish stdout (program output) from stderr (which typically contains diagnostics), and note that exception messages may differ across JDK versions or environments.

## 8. Summary in Three Questions

1. **Won't compile?** Look at the compile-time errors and fix the code according to Java's syntax/type rules.
2. **Compiles, but fails when running?** Look at the exception, stack trace, input data, dependencies, and environment.
3. **Runs normally, but produces the wrong result?** Look at logic, specifications, operator precedence, loops, edge cases, and tests.

**Remember:** compile-time errors are blocked before execution; runtime errors occur during launch/execution; logic errors can remain silent even when the program finishes. A quality program must **compile cleanly, run reliably, and produce the expected results**.