# Breaking Down a Problem into Input, Process, and Output (Java 17+)

## 1. Goal: Understand the problem before writing code

When you receive a requirement in natural language, do not start by immediately writing `Scanner`, `if`, or loops. First, answer three questions following the **Input – Process – Output (IPO)** model:

1. **Input:** What values does the program need to know, where do they come from, and what are their data types, units, bounds, and validity conditions?
2. **Process:** What validations, transformations, calculations, and business rules must be applied, and in what order?
3. **Output:** What must the program return or display, in what format, how do we know the result is correct, and how should it respond when the input is invalid?

IPO analysis turns a vague problem statement into an **implementable and testable contract**. In Java, the three parts usually correspond to reading parameters/input, one or more processing methods, and then displaying or returning the result.

```text
User requirement
      |
      v
Input: data + validity conditions
      |
      v
Process: validate -> calculate -> decide
      |
      v
Output: success result OR error message
      |
      v
Verify against defined test cases
```

This model fits console exercises, calculation methods, file processing, APIs, and larger programs. **IPO is an analysis approach**, not a syntax feature or a built-in data type in Java.

## 2. Analyzing a concrete problem

**Sample problem:** *Read the scores of three subjects. Each score is in the range from 0 to 10. Calculate the arithmetic average. Conclude PASS if the average score is at least 5.0 **and** all three scores are 4.0 or above; otherwise, FAIL. If the data is invalid, report an error instead of computing the result.*

From this problem statement, build a table:

| Component | Analysis | Implementation decision |
| --- | --- | --- |
| Input | Three scores `score1`, `score2`, `score3` | Use `double` to accept fractional scores |
| Valid domain | Each score is finite and `0 <= score <= 10` | Validate before calculating |
| Process – formula | `average = (score1 + score2 + score3) / 3.0` | Divide by `3.0` to express floating-point division |
| Process – condition | `average >= 5.0` **and** all three scores `>= 4.0` | Use `&&` across the four conditions |
| Success output | Average with two decimal places and `PASS`/`FAIL` | `printf(Locale.ROOT, "%.2f")` and status message |
| Error output | No conclusion if a score is missing or invalid | Specific message on the first invalid field |
| Near-threshold rule | Compare the **unrounded** average score | Only format to two decimal places when displaying |

Why check `Double.isFinite()`? `Double.parseDouble("NaN")` and `Double.parseDouble("Infinity")` can produce special `double` values that are not valid scores. Checking only with comparisons against `0` and `10` is not enough for `NaN`, because all ordering comparisons with `NaN` evaluate to `false`.

### Clarifying ambiguous requirements

In a real project, you should clarify cases that the problem statement does not specify:

- Are negative scores, scores above 10, empty values, or `NaN` values allowed? This example specifies **no**.
- Is there a limit on the number of decimal places in the input? This example places **no** specific limit, as long as the number is valid within the range.
- When the average score is `4.999...`, should the comparison happen before or after rounding? This example compares the **computed value**; rounding is for printing only.
- When one field is entered incorrectly, should the program prompt again or report an error and stop? This example **reports an error and terminates**.
- Is input read from keyboard, file, `main` arguments, or an API? This console example reads **three lines**, representing the three scores in order.

These choices belong to the **contract of the sample problem**, not a universal default rule for all grading applications.

## 3. Separating input from processing

A good habit is to clearly separate **how data is received** from **the calculation rules**. For instance, the same average calculation can be called from a console program, a test, or an API.

Draw the boundaries:

- **Input layer:** reads three strings; checks that data is present, parses numbers; rejects invalid values. `Scanner` and `Double.parseDouble` belong here.
- **Process layer:** receives only three already-validated numbers; calculates the average and decides PASS/FAIL. This layer does not need to know how the user entered the data.
- **Output layer:** receives the processing result and prints it in the agreed format. Do not recompute business formulas inside `println` statements.

This separation prevents bugs from getting tangled together: if `abc` is not handled properly, inspect Input; if scores 4, 5, 6 are marked FAIL, inspect Process; if `5,00` is printed instead of `5.00`, inspect Output/locale.

## 4. Turning IPO into an algorithm

Before coding, you can write Java-independent **pseudocode**:

```text
Read score1, score2, score3 (one score per line).
For each score:
    If there is no line -> report missing data and stop.
    If it cannot be parsed as a floating-point number -> report invalid format and stop.
    If it is not finite or outside [0, 10] -> report out of range and stop.

average = (score1 + score2 + score3) / 3.0
passed = average >= 5.0
         AND score1 >= 4.0
         AND score2 >= 4.0
         AND score3 >= 4.0

Print the average score with 2 decimal places.
Print PASS if passed, otherwise print FAIL.
```

Pseudocode helps verify the sequence before writing syntax: **validate → calculate → decide → present**. If you calculate before knowing whether the data is valid, the program may pass meaningless values into processing or accidentally announce a wrong result.

In Java, the condition is written as:

```java
boolean passed = average >= 5.0
        && score1 >= 4.0
        && score2 >= 4.0
        && score3 >= 4.0;
```

This is an illustrative expression snippet and must be placed where those variables are already declared. The `&&` operator means **and**, unlike `||` (or). If you mistakenly replace it with `||`, a student with a low score in one subject could still be marked PASS.

## 5. Complete Java 17+ program

Create the file **`GradeReport.java`**:

```java
import java.util.Locale;
import java.util.Scanner;

public class GradeReport {
    record Result(double average, boolean passed) {}

    static double readScore(Scanner scanner, String label) {
        if (!scanner.hasNextLine()) {
            throw new IllegalArgumentException("missing " + label);
        }

        String text = scanner.nextLine().trim();
        final double value;

        try {
            value = Double.parseDouble(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("invalid " + label);
        }

        if (!Double.isFinite(value) || value < 0 || value > 10) {
            throw new IllegalArgumentException("out of range " + label);
        }
        return value;
    }

    static Result evaluate(double first, double second, double third) {
        double average = (first + second + third) / 3.0;
        boolean passed = average >= 5.0
                && first >= 4.0
                && second >= 4.0
                && third >= 4.0;
        return new Result(average, passed);
    }

    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            try {
                System.out.println("Score 1:");
                double first = readScore(scanner, "score1");

                System.out.println("Score 2:");
                double second = readScore(scanner, "score2");

                System.out.println("Score 3:");
                double third = readScore(scanner, "score3");

                Result result = evaluate(first, second, third);
                System.out.printf(Locale.ROOT,
                        "Average: %.2f%n", result.average());
                System.out.println("Result: "
                        + (result.passed() ? "PASS" : "FAIL"));
            } catch (IllegalArgumentException ex) {
                System.out.println("Error: " + ex.getMessage());
            }
        }
    }
}
```

`record Result` is stable syntax in Java 17. It groups the two logical results `average` and `passed`, and automatically provides the accessors `average()` and `passed()`. For a simple exercise, a record may not be strictly necessary; however, a result object helps separate data from presentation.

**Role of each method:**

- `readScore(...)` belongs to **Input**. It reads one line, parses a `double`, and checks for finiteness and score range; invalid input throws `IllegalArgumentException`.
- `evaluate(...)` belongs to **Process**. It neither reads from the console nor prints anything; given three valid scores, it returns a `Result`.
- `main(...)` coordinates the steps and belongs to **Output** in its last two print statements. If it catches an input error, it prints `Error: ...` and terminates.

`Double.parseDouble` uses the decimal dot according to Java syntax, **not the machine's display locale**. `Locale.ROOT` is used only when printing the result to ensure a decimal dot in the sample output.

### Compiling and running

From the directory containing `GradeReport.java`, create the `out` directory if it does not exist yet:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out GradeReport.java
java -cp out GradeReport
```

You can run this in PowerShell, CMD, or bash with JDK 17+. When the program asks `Score 1:`, enter `7.0` and press Enter; next `6.5`, then `8.0`, one score per line.

**Input data:**

```text
7.0
6.5
8.0
```

**Exact stdout printed by the program** (excluding keyboard characters echoed by the terminal itself):

```text
Score 1:
Score 2:
Score 3:
Average: 7.17
Result: PASS
```

The average is `(7.0 + 6.5 + 8.0) / 3 = 7.1666...`, formatted as `7.17`. All three scores are at least `4.0`, and the average is at least `5.0`, so the conclusion is PASS.

If you want to run with fixed input, save the three lines above into `sample.txt`, then:

- Linux/macOS or Windows CMD: `java -cp out GradeReport < sample.txt`.
- Windows PowerShell: `Get-Content -LiteralPath sample.txt | java -cp out GradeReport`.

A successful `javac` command normally produces no stdout; the expected output above comes from the `java` command. For PowerShell or terminals with different encoding settings, this example uses ASCII strings for labels to avoid display differences.

## 6. Using a trace table to verify formulas and conditions

A simple technique is to write a **trace table**: given concrete input, compute each intermediate value before running the program.

| Input `(s1, s2, s3)` | Unrounded average | All scores `>= 4`? | Average `>= 5`? | Conclusion |
| --- | ---: | --- | --- | --- |
| `(7.0, 6.5, 8.0)` | `7.1666...` | Yes | Yes | PASS |
| `(4, 5, 6)` | `5.0` | Yes | Yes | PASS |
| `(3.5, 9, 9)` | `7.1666...` | No | Yes | FAIL |
| `(0, 0, 0)` | `0.0` | No | No | FAIL |
| `(10, 10, 10)` | `10.0` | Yes | Yes | PASS |
| `(4, 4, 7)` | `5.0` | Yes | Yes | PASS |

This table helps catch mistakes such as using `||` instead of `&&`, forgetting to divide by 3, or forgetting to check each individual subject. In particular, the `(3.5, 9, 9)` case proves that **a high average can still result in FAIL** if one subject is below `4.0`.

### Checking boundaries and invalid input

Invalid data must stop before the processing step:

| Case | Expected result |
| --- | --- |
| Scores `0`, `4`, `5`, `10` | All are valid individual scores |
| Score `-0.1` or `10.1` | `out of range` |
| `abc` or blank line | `invalid` |
| `NaN` or `Infinity` | `out of range` because not finite |
| Missing next score line upon hitting EOF | `missing` |
| More than three lines | The sample program only reads three lines per its contract; extra data is not processed |

Example run with **input**:

```text
3.5
9
9
```

**Exact stdout:**

```text
Score 1:
Score 2:
Score 3:
Average: 7.17
Result: FAIL
```

Example with **input** consisting of just one line `abc`:

```text
abc
```

**Exact stdout:**

```text
Score 1:
Error: invalid score1
```

These are **different** test inputs, each used in a separate run; do not combine all of them into a single run if you want to match the outputs above.

## 7. Separating calculation logic for easier testing

The benefit of the `evaluate` method is that you can test the logic without simulating keyboard input or matching prompts. Below is another standalone program runnable on Java 17+ that focuses on testing **Process**.

Create the file **`GradeLogicTest.java`**:

```java
public class GradeLogicTest {
    static void check(double a, double b, double c,
                      boolean expectedPass) {
        GradeReport.Result result = GradeReport.evaluate(a, b, c);

        if (result.passed() != expectedPass) {
            throw new AssertionError("wrong decision");
        }

        System.out.println("passed=" + result.passed());
    }

    public static void main(String[] args) {
        check(4, 5, 6, true);
        check(3.5, 9, 9, false);
        check(10, 10, 10, true);
    }
}
```

The `GradeLogicTest` class uses the `evaluate` method and `Result` record from `GradeReport` in the same **unnamed package**. Compile both files together:

```sh
javac -encoding UTF-8 --release 17 -d out GradeReport.java GradeLogicTest.java
java -cp out GradeLogicTest
```

**Exact stdout:**

```text
passed=true
passed=false
passed=true
```

If a case produces the wrong decision, `throw new AssertionError(...)` fails the test program right at that call. This is a minimal testing example using core Java; in a real project, you can use JUnit to organize many tests.

**Intentional limitation of the sample design:** `evaluate` assumes the three scores have already been validated by `readScore`. If a project exposes `evaluate` as a public API where other callers can pass arbitrary numbers, validation must be added inside `evaluate` itself or an input type with enforced invariants should be used. Every method must state its preconditions clearly.

## 8. Distinguishing functional and non-functional requirements

Beyond getting the formula right, problem analysis may require additional constraints:

| Requirement category | Example for the grading problem |
| --- | --- |
| **Functional** | Read three scores; calculate average; determine PASS/FAIL; report invalid input |
| **Correctness** | Compare thresholds using the unrounded average; all three scores must be `>= 4` |
| **Usability** | Clearly state which score number is being requested; give specific error messages |
| **Reliability** | Check EOF, infinite values, and `NaN`; do not throw unhandled exceptions on common bad inputs |
| **Testability** | Separate `evaluate` method; deterministic output for the same input |
| **Maintainability** | Names `readScore`, `evaluate`, `Result` express responsibility; formula is not duplicated |
| **Performance** | Three reads and a few arithmetic operations suffice; no complex data structures needed |

In this small problem, the algorithm's time complexity is **O(1)** and auxiliary memory for the calculation is **O(1)**, since only three fixed scores are considered. For data with many subjects, the requirement changes to reading an arbitrary count, which may need arrays, lists, or loops; that is **a different problem** requiring fresh analysis of input, conditions, and output.

## 9. Common mistakes in problem analysis

**Confusing input data with calculated results.** The average score is not an input if the problem only provides three subject scores; it is a value computed in Process.

**Ignoring units and valid domains.** For scores, `-1` or `15` is invalid even though it parses as a `double`. For currency or time problems, units matter even more: VND vs. USD, seconds vs. minutes, meters vs. centimeters cannot be mixed.

**Failing to distinguish successful parsing from valid data.** `Double.parseDouble("20")` succeeds, yet `20` is still outside the allowed score range.

**Missing boundary cases.** A solution often fails at scores right on the threshold (`4.0`, `5.0`), minimum/maximum values, empty strings, missing input, or very large numbers.

**Calculating directly inside a print statement.** If you put a long formula inside `System.out.println(...)`, it is hard to inspect intermediate values and reuse the logic. Extract it into well-named variables or methods.

**Choosing data types arbitrarily.** Fractional scores need floating-point numbers; product quantities use integers; currency accurate to the smallest unit should consider integers or `BigDecimal` depending on the contract, not `double` out of habit.

**Rounding too early.** If you only format `%.2f` when printing, the PASS/FAIL decision still relies on the unrounded value. For example, a near-threshold value might print as `5.00` while concluding FAIL when the true value is below `5.0`. If the user requires "round first, then evaluate," you must explicitly update the processing rule and corresponding tests.

**Leaving error output unspecified.** A program needs a contract for invalid inputs too. A cryptic stack trace is not an appropriate message for every interactive console program.

**Mixing Input/Process/Output in one overly long block.** Acceptable in a tiny exercise, but as it grows it becomes hard to swap the terminal for a file/API, hard to test the calculation, and easy to duplicate validation.

## 10. Applying IPO to another problem

Example requirement: *Read the length and width of a rectangle; calculate its area and perimeter.*

| Input | Process | Output |
| --- | --- | --- |
| Two positive numbers `length`, `width`, in the same unit (e.g., meters) | `area = length * width`, `perimeter = 2 * (length + width)` | Area (m²), perimeter (m), or invalid dimension error |

From this table, you can create test cases: `(2, 3)` gives area `6`, perimeter `10`; `(0, 3)` is invalid input if the contract requires both sides to be **greater than 0**; `(-2, 3)` is also invalid.

If the user enters dimensions in centimeters but wants the area in m², you must add a **unit conversion** step in Process. Merely renaming variables or appending `m²` in Output will not make the result right.

## 11. Pre-coding checklist

1. Can I describe **each input** with its name, type, unit, source, and valid domain?
2. Are there any ambiguous rules regarding rounding, thresholds, missing data, or extra data?
3. Have I written the **formulas, conditions, and processing order** as clear pseudocode or a diagram?
4. Have I specified both **success output and error output**?
5. Have I hand-calculated at least one normal case, one near-threshold case, and one invalid-data case?
6. Can **reading**, **processing**, and **printing/returning** be separated into blocks or methods with clear responsibilities?
7. Have I compiled with `javac`, run with `java`, and compared actual output against expected results?

**Remember:** Before choosing Java syntax, turn the requirement into **Input with a clear contract → Process with formulas and validation rules → Output that is verifiable**. Good analysis makes code shorter, easier to fix, and prevents many logic errors from the start.
