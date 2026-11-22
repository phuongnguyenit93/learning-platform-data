# Flow Branch Testing with Boundary Data in Java Pattern Matching

**Flow branch testing** is a test-case design technique based on **the different execution paths of a program**: true/false conditions, `if/else` branches, `switch case`, `when` guards, fallbacks, and `null`-handling cases. **Boundary-value testing** complements this with values immediately before, right at, and immediately after a condition's boundary, because this is where `<`/`<=`, `>`/`>=`, or branch-ordering bugs are most likely to appear.

When Java uses **pattern matching**, a test case must address both questions:

1. **Does the pattern match?** For example, is the selector a `Score`, `Message`, or `Batch`; is a nested record a non-`null` `Score`?
2. **After the pattern matches, does the additional condition hold?** For example, `n < 0`, `n == 100`, `text.isBlank()`, or the guard `when a == b`.

These two steps determine which branch is actually executed. Testing only a few "happy" cases often misses critical paths.

**Version:** The main program uses `record`, `sealed interface`, record patterns, and pattern matching for `switch` on **Java 21+**. `record` has been stable since Java 16 and `sealed` since Java 17; record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have been stable since Java 21. The program has been compiled with `javac --release 21` without needing preview features enabled.

## 1. Distinguishing Branch Testing and Boundary-Value Testing

Suppose business logic classifies a score:

```java
if (n < 0) {
    return "NEGATIVE";
}
if (n == 0) {
    return "ZERO";
}
if (n == 100) {
    return "MAX";
}
if (n > 100) {
    return "OVER_LIMIT";
}
return "IN_RANGE";
```

The classification consists of five **branch outcomes**: negative, zero, exactly 100, over 100, and 1–99. Testing only `n = 50` proves a single branch; it cannot detect bugs in the other four branches.

To test conditions at risk of wrong comparison operators, we typically choose boundary triples:

| Boundary | Before boundary | At boundary | After boundary | Why is it needed? |
| --- | ---: | ---: | ---: | --- |
| `0` | `-1` | `0` | `1` | Distinguishes negative, zero, and positive |
| `100` | `99` | `100` | `101` | Distinguishes in-range, exact maximum, and over-limit |

In addition, `Integer.MIN_VALUE` and `Integer.MAX_VALUE` help verify the two extremes of the `int` domain. Extreme values do not replace the `-1/0/1` or `99/100/101` triples; each group serves a different purpose.

**Branch outcome coverage** is the observation of the defined classification outcomes. **Branch coverage** measured by tools like JaCoCo is a different concept: it tracks instrumented control-flow edges or decision outcomes. Do not claim "100% branch coverage" merely because all result strings were observed. In the program in section 7, we verify **13 outcome labels** and 20 data rows, but we do not assume that equals JaCoCo's coverage metric.

## 2. Domain Model for Testing Multiple Patterns and Flow Branches

We use a closed model with three input forms:

```java
sealed interface Input permits Message, Score, Batch {}

record Message(String text) implements Input {}
record Score(int points) implements Input {}
record Batch(Score first, Score second) implements Input {}
```

Meaning:

- `Message` has a `String text` component, allowing tests for `null`, empty strings, whitespace-only strings, or strings with content.
- `Score` holds an integer `points`, suited for testing numeric boundaries.
- `Batch` holds two `Score` values, used to test **nested record patterns** and the fallback branch when a child record is `null`.
- `Input` is `sealed` and records are `final` by default. The compiler knows the permitted set of types, so a `switch expression` can be exhaustive without needing a `default` that hides new subtypes.

In this lesson, `Batch` **intentionally does not forbid `null` components** so we can test the path when a child record is missing. If a real domain requires both components to always be non-`null`, enforce that invariant in the constructor; in that case, input tests like `Batch(null, ...)` should become **tests that the constructor throws an exception** rather than classification-branch tests.

## 3. A Switch with Multiple Branches and Guards

Using Java 21:

```java
static String classify(Input input) {
    return switch (input) {
        case null -> "NULL_SELECTOR";

        case Message(var text) when text == null -> "MISSING_TEXT";
        case Message(var text) when text.isBlank() -> "BLANK_TEXT";
        case Message(var text) when text.length() == 1 -> "ONE_CHAR";
        case Message(var text) -> "TEXT";

        case Score(int n) when n < 0 -> "NEGATIVE";
        case Score(int n) when n == 0 -> "ZERO";
        case Score(int n) when n == 100 -> "MAX";
        case Score(int n) when n > 100 -> "OVER_LIMIT";
        case Score(var n) -> "IN_RANGE";

        case Batch(Score(int a), Score(int b)) when a == b ->
                "EQUAL_BATCH";
        case Batch(Score(var a), Score(var b)) -> "DIFFERENT_BATCH";
        case Batch(var first, var second) -> "INCOMPLETE_BATCH";
    };
}
```

**This snippet is an illustrative method:** it must be placed inside a class where the records are declared. The standalone program in section 7 contains all declarations in full.

### Case Ordering Is Part of the Test Requirements

Placing a **broad** pattern before a **narrow** case does not only cause the wrong branch to be selected—in many cases Java will **fail to compile** due to a dominance error. In the method above:

1. `Message(var text) when text == null` precedes any call to `text.isBlank()` to avoid dereferencing `null`.
2. The unguarded `Message(var text)` appears **after** the guarded branches; it catches the remaining `Message` values.
3. `Score(var n)` comes last in the `Score` group because it matches every non-`null` `Score`, including boundary scores.
4. `Batch(Score(...), Score(...))` requires both child records to exist. The final branch `Batch(var first, var second)` covers `Batch` instances with one or both child components equal to `null`.
5. `case null` handles a `null` **selector `input`**; `case Message(var text) when text == null` handles an **existing Message object** whose `text` component is `null`. The two cases are completely different.

Java checks dominance and exhaustiveness at compile time. A runtime test suite does not replace the compiler's rules, but it helps verify **business priority order** and guards near boundaries.

## 4. Testing True/False Guards and Flow Scoping

Flow analysis determines when a pattern variable can be validly used. For example:

```java
static String scoreWithIf(Object value) {
    if (!(value instanceof Score score)) {
        return "NOT_SCORE";
    }

    int n = score.points();
    if (n < 0) return "NEGATIVE";
    if (n == 0) return "ZERO";
    if (n == 100) return "MAX";
    if (n > 100) return "OVER_LIMIT";
    return "IN_RANGE";
}
```

In `if (!(value instanceof Score score))`:

- If the value is `null` or not a `Score`, the match fails and the method returns `NOT_SCORE`.
- If it does not return, the compiler knows `Score score` is definitely bound; `score.points()` is valid in subsequent statements thanks to **definite matching/flow scoping**.
- The conditions `n < 0`, `n == 0`, `n == 100`, and `n > 100` create distinct execution paths.

This method intentionally returns the **same results** as the `case Score(...)` group in `classify`. This allows us to write **differential tests** comparing two implementations on the same data table. This is a useful supplement, but it cannot replace determining expected results independently from the specification: if both algorithms share the same bug, they can still produce matching outputs.

### Testing Compound Conditions

```java
if (value instanceof Score score && score.points() > 100) {
    System.out.println("Over limit");
}
```

The right-hand side of `&&` is only evaluated when the type pattern on the left-hand side has matched. When testing, include: `value == null`, wrong type, `Score(100)`, and `Score(101)`. They exercise the paths **no match**, **no match**, **match with false guard**, and **match with true guard**, respectively.

For negated conditions and `||`, short-circuit evaluation also affects the execution path: `!(value instanceof Score score) || score.points() > 100` is valid because `score` is only used on the right-hand side when the negated left-hand side is false. When building tests, verify both short-circuit paths.

## 5. Test Case Tables for Boundary Values

The following tables are written **before running the program** and serve as an *expected oracle*: each input is manually mapped to a specified outcome.

### Null Selector and Strings

| Test case | Input | Expected | Boundary/branch |
| --- | --- | --- | --- |
| selector-null | `null` | `NULL_SELECTOR` | Null selector value |
| text-null | `new Message(null)` | `MISSING_TEXT` | Null record component |
| text-empty | `new Message("")` | `BLANK_TEXT` | Empty string |
| text-spaces | `new Message(" \t")` | `BLANK_TEXT` | Whitespace only |
| text-one | `new Message("X")` | `ONE_CHAR` | Length equals 1 |
| text-two | `new Message("AB")` | `TEXT` | Length equals 2 |
| text-unicode | `new Message("á")` | `ONE_CHAR` | One UTF-16 unit |

Note that `String.isBlank()` returns `true` for empty strings and strings containing only code points that Java considers whitespace. Meanwhile, `String.length()` counts **UTF-16 code units**, not the number of user-perceived graphemes. For example, an emoji character may occupy two code units and be handled differently from `"á"` in the test suite. If the product contract requires counting characters by code point or grapheme, the calculation and test oracle must both be updated, not just the input.

### Numeric Values Near Boundaries

| Test case | Input | Expected | Role |
| --- | --- | --- | --- |
| score-min | `new Score(Integer.MIN_VALUE)` | `NEGATIVE` | `int` minimum |
| score-minus-one | `new Score(-1)` | `NEGATIVE` | Immediately before 0 |
| score-zero | `new Score(0)` | `ZERO` | Exactly 0 |
| score-one | `new Score(1)` | `IN_RANGE` | Immediately after 0 |
| score-99 | `new Score(99)` | `IN_RANGE` | Immediately before 100 |
| score-100 | `new Score(100)` | `MAX` | Exactly 100 |
| score-101 | `new Score(101)` | `OVER_LIMIT` | Immediately after 100 |
| score-max | `new Score(Integer.MAX_VALUE)` | `OVER_LIMIT` | `int` maximum |

At the `100` mark, testing `99/100/101` distinguishes `n == 100` from `n > 100`. Do not test only `n = 200` and conclude that the boundary has been properly checked.

### Child Records and Nested Patterns

| Test case | Input | Expected |
| --- | --- | --- |
| batch-equal | `new Batch(new Score(1), new Score(1))` | `EQUAL_BATCH` |
| batch-different | `new Batch(new Score(1), new Score(2))` | `DIFFERENT_BATCH` |
| batch-left-null | `new Batch(null, new Score(2))` | `INCOMPLETE_BATCH` |
| batch-right-null | `new Batch(new Score(2), null)` | `INCOMPLETE_BATCH` |
| batch-both-null | `new Batch(null, null)` | `INCOMPLETE_BATCH` |

The first two rows both match the structure `Batch(Score(...), Score(...))` but differ on the `a == b` guard. The last three rows verify that the nested record pattern **does not match a null child object**, while `Batch(var first, var second)` still matches the outer record and allows null reference components.

Total: **7 selector/string cases + 8 numeric cases + 5 batch cases = 20 cases**. This test suite intentionally includes cases that share an outcome label, because two inputs with the same expected result can still uncover different bugs.

## 6. Principles for Writing Assertions and Measuring Coverage

A test case should not just print results. It must **compare the actual result against the expected value** and fail if they differ:

```java
static void check(String label, String expected, String actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                label + ": expected=" + expected + ", actual=" + actual);
    }
}
```

When using *table-driven testing*, each row has three pieces of information: case name, input, and expected output. A loop iterates through each row and calls `check(...)`. If an assertion fails, the program terminates with an `AssertionError` and a message identifying which test failed.

### Outcome Labels vs. % Coverage

In this example, we can collect `Set<String> outcomes` from the run results and compare it against the set of **13 required outcome labels**. Doing so confirms that every **outcome category defined by the specification** was observed.

However:

- A single outcome label can be produced via multiple different conditions or paths.
- A path where `when` fails and falls through to the next case is still a distinct path that counting labels does not necessarily capture.
- Java tools such as JaCoCo measure **instruction, line, and branch coverage** at the instrumented bytecode level. For pattern switches, the bytecode generated by the Java compiler may differ from how we count labels.
- **High coverage does not guarantee correct assertions.** If a test only invokes a method without comparing against an independent oracle, a covered branch can still be semantically wrong.

You should combine: **a clear test oracle + boundary cases + outcome-category tracking + tool-based coverage measurement**. Where possible, add mutation testing to evaluate the strength of the test suite.

## 7. Complete, Verified Java 21 Program

Save the following file verbatim as **`FlowBranchBoundaryDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class FlowBranchBoundaryDemo {
    sealed interface Input permits Message, Score, Batch {}
    record Message(String text) implements Input {}
    record Score(int points) implements Input {}
    record Batch(Score first, Score second) implements Input {}
    record TestCase(String label, Input input, String expected) {}

    static String classify(Input input) {
        return switch (input) {
            case null -> "NULL_SELECTOR";
            case Message(var text) when text == null -> "MISSING_TEXT";
            case Message(var text) when text.isBlank() -> "BLANK_TEXT";
            case Message(var text) when text.length() == 1 -> "ONE_CHAR";
            case Message(var text) -> "TEXT";
            case Score(int n) when n < 0 -> "NEGATIVE";
            case Score(int n) when n == 0 -> "ZERO";
            case Score(int n) when n == 100 -> "MAX";
            case Score(int n) when n > 100 -> "OVER_LIMIT";
            case Score(var n) -> "IN_RANGE";
            case Batch(Score(int a), Score(int b)) when a == b -> "EQUAL_BATCH";
            case Batch(Score(var a), Score(var b)) -> "DIFFERENT_BATCH";
            case Batch(var first, var second) -> "INCOMPLETE_BATCH";
        };
    }

    static String scoreWithIf(Object value) {
        if (!(value instanceof Score score)) {
            return "NOT_SCORE";
        }
        int n = score.points();
        if (n < 0) return "NEGATIVE";
        if (n == 0) return "ZERO";
        if (n == 100) return "MAX";
        if (n > 100) return "OVER_LIMIT";
        return "IN_RANGE";
    }

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        TestCase[] matrix = {
            new TestCase("selector-null", null, "NULL_SELECTOR"),
            new TestCase("text-null", new Message(null), "MISSING_TEXT"),
            new TestCase("text-empty", new Message(""), "BLANK_TEXT"),
            new TestCase("text-spaces", new Message(" \t"), "BLANK_TEXT"),
            new TestCase("text-one", new Message("X"), "ONE_CHAR"),
            new TestCase("text-two", new Message("AB"), "TEXT"),
            new TestCase("text-unicode", new Message("á"), "ONE_CHAR"),
            new TestCase("score-min", new Score(Integer.MIN_VALUE), "NEGATIVE"),
            new TestCase("score-minus-one", new Score(-1), "NEGATIVE"),
            new TestCase("score-zero", new Score(0), "ZERO"),
            new TestCase("score-one", new Score(1), "IN_RANGE"),
            new TestCase("score-99", new Score(99), "IN_RANGE"),
            new TestCase("score-100", new Score(100), "MAX"),
            new TestCase("score-101", new Score(101), "OVER_LIMIT"),
            new TestCase("score-max", new Score(Integer.MAX_VALUE), "OVER_LIMIT"),
            new TestCase("batch-equal", new Batch(new Score(1), new Score(1)), "EQUAL_BATCH"),
            new TestCase("batch-different", new Batch(new Score(1), new Score(2)), "DIFFERENT_BATCH"),
            new TestCase("batch-left-null", new Batch(null, new Score(2)), "INCOMPLETE_BATCH"),
            new TestCase("batch-right-null", new Batch(new Score(2), null), "INCOMPLETE_BATCH"),
            new TestCase("batch-both-null", new Batch(null, null), "INCOMPLETE_BATCH")
        };

        Set<String> outcomes = new HashSet<>();
        int scoreChecks = 0;
        for (TestCase test : matrix) {
            String actual = classify(test.input());
            check(test.label(), test.expected(), actual);
            outcomes.add(actual);
            if (test.input() instanceof Score) {
                check("if-" + test.label(), test.expected(), scoreWithIf(test.input()));
                scoreChecks++;
            }
        }
        Set<String> required = Set.of(
            "NULL_SELECTOR", "MISSING_TEXT", "BLANK_TEXT", "ONE_CHAR", "TEXT",
            "NEGATIVE", "ZERO", "MAX", "OVER_LIMIT", "IN_RANGE",
            "EQUAL_BATCH", "DIFFERENT_BATCH", "INCOMPLETE_BATCH");
        if (!outcomes.equals(required)) {
            throw new AssertionError("branch outcomes mismatch: " + outcomes);
        }
        check("if-null", "NOT_SCORE", scoreWithIf(null));
        check("if-other-type", "NOT_SCORE", scoreWithIf(new Message("abc")));

        System.out.println("PASS matrix=" + matrix.length);
        System.out.println("PASS branch-outcomes=" + outcomes.size());
        System.out.println("PASS if-vs-switch=" + scoreChecks);
        System.out.println("PASS non-score-guards=2");
        System.out.println("example null=" + classify(null));
        System.out.println("example boundary=" + classify(new Score(100)));
        System.out.println("example nested-null=" + classify(new Batch(null, new Score(1))));
    }
}
```

Compile and run with **JDK 21 or newer**:

```bash
javac --release 21 -encoding UTF-8 FlowBranchBoundaryDemo.java
java FlowBranchBoundaryDemo
```

**Exact stdout:**

```text
PASS matrix=20
PASS branch-outcomes=13
PASS if-vs-switch=8
PASS non-score-guards=2
example null=NULL_SELECTOR
example boundary=MAX
example nested-null=INCOMPLETE_BATCH
```

The `PASS` lines are printed **after the checks have actually completed**. They are not decorative messages:

1. `matrix=20`: all 20 cases compare `expected` against `actual` via `check(...)` with no `AssertionError`.
2. `branch-outcomes=13`: the observed outcome set matches the exact set of 13 expected labels.
3. `if-vs-switch=8`: all eight `Score` inputs pass through both `classify` and `scoreWithIf`; both must match that case's oracle.
4. `non-score-guards=2`: verifies the two `scoreWithIf` cases when the input is `null` and `Message`, both returning `NOT_SCORE`.
5. The last three lines show concrete examples of the null selector branch, the `100` boundary, and a `null` child record.

The program compiles and runs with `javac --release 21` and produced the exact seven stdout lines above. It has no dependency on JUnit, Maven, or external libraries; it is a minimal test harness for learning how to design a test-case matrix.

## 8. Migrating to JUnit and Coverage Reporting

In a real project, cases should be organized into clearly named unit tests. With **JUnit Jupiter (JUnit 5)**, the `Score` test suite can be converted into a parameterized test method:

```java
// Illustrative snippet for a test class with JUnit Jupiter on the classpath.
// Place inside a test class and add JUnit imports and the class containing Score/classify.
@org.junit.jupiter.params.ParameterizedTest
@org.junit.jupiter.params.provider.CsvSource({
    "-1,NEGATIVE",
    "0,ZERO",
    "1,IN_RANGE",
    "99,IN_RANGE",
    "100,MAX",
    "101,OVER_LIMIT"
})
void scoreBoundaryCases(int points, String expected) {
    org.junit.jupiter.api.Assertions.assertEquals(
        expected,
        FlowBranchBoundaryDemo.classify(
            new FlowBranchBoundaryDemo.Score(points)));
}
```

This snippet **is not a standalone Java file** and only works when the test code is placed in an appropriate package alongside `FlowBranchBoundaryDemo` with JUnit Jupiter `api` and `params` configured. Do not put the JUnit snippet above into the runnable file from section 7 without those dependencies. The core value here is defining an **independent expected outcome** and reusing a single test method across multiple boundary points.

If you use JaCoCo, treat the branch coverage percentage as a **secondary indicator**. Prioritize inspecting uncovered regions, adding cases for false/true guards and missing types or nulls, while keeping assertions intact so tests actually catch bugs. With switch pattern matching, compiler-generated bytecode may contain technical branches beyond the business branches in the source code.

### Using Mutation Testing to Check If Tests Can Catch Bugs

For example, if an accidental change turns `n < 0` into `n <= 0`, the `score-zero` test expects `ZERO` but receives `NEGATIVE`. If `n > 100` is changed to `n > 101`, the `score-101` test expects `OVER_LIMIT` but may fall into `IN_RANGE`.

The boundary cases `0` and `101` can detect both of those mutations. This illustrates why tests should do more than merely "execute through" the code.

Another mutation is changing the **guard order** or removing `case Message(var text) when text == null`. Then `Message(null)` can trigger a `NullPointerException` at `text.isBlank()` or produce the wrong result; the `text-null` test will catch it.

## 9. What Else Should Be Checked as the Domain Evolves?

- **Adding a subtype to the `sealed interface`:** if you add `record Flag(boolean enabled) implements Input`, the compiler may require an additional case for the `switch expression` to remain exhaustive. When adding that case, add test data for both `true/false` values if there is branching logic.
- **Changing boundary rules:** if the maximum changes from `100` to `120`, update the **business oracle first**, then update the `119/120/121` triple and the implementation. Avoid editing tests merely to mirror bugs in the implementation.
- **Enforcing invariants in constructors:** if `Batch` later forbids `null` components, the tests `batch-left-null`, `batch-right-null`, and `batch-both-null` must test constructor errors or use domain-valid inputs.
- **Changing types from `int` to `long`:** revisit extreme values and overflow risks. `Integer.MIN_VALUE` is no longer the minimum of `long`.
- **Measuring text length for UI purposes:** `String.length()` counts UTF-16 code units; if requirements differ, update the algorithm and corresponding Unicode test cases.
- **When handling exceptions:** a test expecting an exception must assert **the exact exception type and relevant policy**, not just confirm that "an error occurred." JUnit provides `assertThrows` for this.
- **Changing case order:** the compiler usually rejects dominated cases, but it does not catch every logical mistake across different guards. Maintain boundary and per-path tests.

## 10. Common Mistakes When Testing Flow Branches

1. **Testing only the happy path.** A single `Score(50)` input fails to exercise the negative, zero, max, and over-limit branches.
2. **Not testing values right at boundaries.** Having `Score(200)` without `99/100/101` easily misses comparison-operator bugs.
3. **Lumping all null cases together.** `classify(null)` and `classify(new Message(null))` take completely different branches; `Batch(null, new Score(1))` is a third distinct situation.
4. **Assuming a record pattern always excludes all nulls.** The outer `Batch` record must be non-null to match, but `var first` can bind a null component; the nested record pattern `Score(...)` does not match a null child record.
5. **Assuming pattern variables are always non-null at every level.** After `Message(var text)`, `text` can still be null; you must guard the call to `text.isBlank()` or enforce an invariant in the constructor.
6. **Testing a guarded branch without testing the false guard.** `a == b` needs both an equal pair and a different pair, not just an equal pair.
7. **Confusing expected results with actual execution results.** Writing `assertEquals(actual, actual)` or generating `expected` using the function under test makes the test worthless.
8. **Printing logs instead of asserting.** A `System.out.println(classify(input))` line only displays output; it does not fail the test when wrong.
9. **Counting labels and concluding branch coverage is sufficient.** Labels are business outcomes; use a coverage tool to evaluate actual branches and combine it with an oracle.
10. **Not testing negated type patterns and early returns.** The `if (!(value instanceof Score score)) return ...` pattern needs `null`, wrong-type, and matching-type inputs.
11. **Using a single set of cases containing only valid data.** If the application allows nullable components, test missing left, missing right, and missing both.
12. **Disabling exhaustiveness checks with an unconditional `default`.** With `sealed` types, it is usually better to let the compiler detect new subtypes without cases and add corresponding tests.
13. **Writing misordered cases and expecting unit tests to catch them at runtime.** Java may reject the code at compile time due to dominance; you must first have compilable source code.
14. **Running a Java 21 example under a Java 17 configuration.** Record patterns and pattern switches in this program require `--release 21` or higher; this is not a `--release 17` example.

## 11. Self-Check Exercises

**Question 1.** For the current numeric cases, if `n < 0` is changed to `n <= 0`, which case in the table catches the bug first? Why?

*Answer:* `score-zero`. The input `0` will enter `NEGATIVE` instead of `ZERO`. This is an example of a bug at the `0` boundary.

**Question 2.** Can `case Message(var text) when text == null` be replaced by `case null` to handle `Message(null)`?

*Answer:* No. `case null` handles a null `input` selector value; `Message(null)` is still a non-null record object. Only a guard or an appropriate data policy can handle a null `text` component.

**Question 3.** Which case will `new Batch(null, new Score(2))` enter if there is no constructor check forbidding null?

*Answer:* The final case `Batch(var first, var second)`, returning `INCOMPLETE_BATCH`, because the nested cases `Batch(Score(...), Score(...))` do not match when `first == null`.

**Question 4.** Why are `Score(99)`, `Score(100)`, and `Score(101)` more meaningful than `Score(150)` alone?

*Answer:* They sit immediately before/at/after the `100` boundary, making it easy to catch `>` turned into `>=` or a skipped boundary condition; `150` only proves a single value far above the threshold.

**Question 5.** If the program prints `PASS branch-outcomes=13`, can we conclude that JaCoCo will report 100% branch coverage?

*Answer:* No. The program only confirms that 13 business outcome labels were observed. The number of bytecode-level branches and guard paths may differ, so you must run a coverage tool to know the measured percentage.

**Question 6.** Why do we need to test `scoreWithIf(null)` and `scoreWithIf(new Message("abc"))`, even though `scoreWithIf` already uses `!(value instanceof Score score)`?

*Answer:* Both cases verify the same `NOT_SCORE` result from two different causes: a `null` selector and a wrong-type object. They help catch bugs if refactoring accidentally accesses the object before checking the type or mishandles null.

**Official References:** [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [JLS Java 21 `14.11 – switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11), [JLS Java 21 `14.30 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
