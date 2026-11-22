# Testing Each Branch with an Input Case Table in Java

> **Java core — language-basics / if branching**  
> **Environment:** JDK 17+, single standalone Java file, no external libraries.  
> **Goal:** Turn `if / else if / else` branches into an **input–expected output case table**, test boundaries and overlapping conditions, run automated verification, and recognize the limits of testing only a few random values.

## 1. Why is a branch test table needed?

An `if / else if / else` chain has multiple paths. Running one convenient value, such as only `score = 95`, **does not prove** that the other branches work properly.

A repeatable approach:

1. Read conditions in their exact **order** and identify which branches can be selected.
2. Write each **input**, **expected branch**, and **expected result** into a table.
3. Pick at least one case entering **each branch**, including `else` and invalid-data handling paths.
4. Add data **just below, right at, and just above** meaningful thresholds.
5. Run the program, compare **actual** against **expected**, and report FAIL on mismatch.

**Note:** A manually designed table is a set of *test cases*, not an automatic proof that every possible input is correct. A good table makes missing branches obvious; stricter testing also considers condition combinations, errors, null, and state mutations.

## 2. Example: grading via an exclusive chain

Business rule: score must be in `0..100`; labels are `A` (≥90), `B` (≥75), `C` (≥50), `D` (rest).

~~~java
static String classifyScore(int score) {
    if (score < 0 || score > 100) {
        return "INVALID";
    } else if (score >= 90) {
        return "A";
    } else if (score >= 75) {
        return "B";
    } else if (score >= 50) {
        return "C";
    } else {
        return "D";
    }
}
~~~

Java selects only the **first true branch** in the chain. Therefore, check higher thresholds before lower ones: checking `score >= 50` before `score >= 90` would misclassify a score of 95 as C.

Branches to observe: `INVALID`, `A`, `B`, `C`, `D`. Specifically, the first condition `score < 0 || score > 100` has **two distinct reasons** why a value is invalid: too low or too high. Test both so you do not miss a bug occurring on only one side.

## 3. Test case table and near-boundary values

| Input `score` | Expected branch | Expected | Selection reason |
| ---: | --- | --- | --- |
| -1 | Invalid | `INVALID` | Below 0 threshold |
| 0 | `else` | `D` | Valid lower bound |
| 49 | `else` | `D` | Just below 50 |
| 50 | `score >= 50` | `C` | Right at 50 |
| 74 | `score >= 50` | `C` | Just below 75 |
| 75 | `score >= 75` | `B` | Right at 75 |
| 89 | `score >= 75` | `B` | Just below 90 |
| 90 | `score >= 90` | `A` | Right at 90 |
| 100 | `score >= 90` | `A` | Valid upper bound |
| 101 | Invalid | `INVALID` | Above 100 threshold |

The table covers **all five output branches** and key boundaries. In particular, for `score == 50`, `score >= 50` must be true; for `score == 49`, it must be false. This pair detects accidentally changing `>=` to `>`.

For the `score < 0 || score > 100` check, `score = -1` makes the left side true so the right side does not run due to short-circuiting; `score = 101` makes the left side false and the right side true. The two cases test different paths through the compound condition.

**You do not necessarily need to list every score 0..100** to test boundaries, though full-range testing or case generation can be added when higher assurance is required.

## 4. Tables for multiple independent `if` statements differ from `else if` chains

With two flags `review` and `urgent`, **both actions may need to run**:

~~~java
StringBuilder actions = new StringBuilder();
if (review) {
    actions.append("REVIEW");
}
if (urgent) {
    if (actions.length() > 0) actions.append("+");
    actions.append("URGENT");
}
String result = actions.length() == 0 ? "NONE" : actions.toString();
~~~

Cases that must be tested:

| `review` | `urgent` | Expected | Executed branches |
| --- | --- | --- | --- |
| false | false | `NONE` | No branch |
| true | false | `REVIEW` | First `if` only |
| false | true | `URGENT` | Second `if` only |
| true | true | `REVIEW+URGENT` | **Both `if` statements** |

If `if (urgent)` is accidentally replaced with `else if (urgent)`, the `true, true` case will miss `URGENT`. This is why a **combination table of conditions** matters more than testing each flag alone.

With an exclusive `if/else if/else` chain, on the other hand, the table should verify that **only one branch** executes and conditions after the chosen branch are not evaluated.

## 5. Distinguishing branch coverage from boundary-value testing

| Technique | Question to answer | Example |
| --- | --- | --- |
| Output branch coverage | Has every `if/else if/else` branch been taken at least once? | Outputs `INVALID`, `A`, `B`, `C`, `D` |
| Boundary value testing | Are `<`, `<=`, `>`, `>=` exact at boundaries? | 49/50, 74/75, 89/90 |
| Condition combinations | Are simultaneous true/false combinations overlooked? | Both flags true/true |
| Compound conditions | Has each cause making a compound condition true/false been tested? | Scores `-1` and `101` |
| Exceptional/edge values | How are out-of-range, null, or invalid states handled? | `score=-1`, `score=101` |

**Branch coverage alone is not enough to guarantee correctness.** For example, a test can enter branch B with score 80, yet miss an off-by-one bug at boundary 75. High coverage also does not replace checking against **business requirements**.

When conditions depend on order or have side effects, build a table showing **which expressions get evaluated**; do not assume every `else if` runs. For `null`, design inputs with and without data, checking guards before calling methods.

## 6. Self-verifying Java 17+ program for input case tables

Create the file **IfBranchCaseTableDemo.java**:

~~~java
public final class IfBranchCaseTableDemo {
    private record ScoreCase(int input, String expected) {}
    private record FlagCase(boolean review, boolean urgent, String expected) {}

    private static String classifyScore(int score) {
        if (score < 0 || score > 100) {
            return "INVALID";
        } else if (score >= 90) {
            return "A";
        } else if (score >= 75) {
            return "B";
        } else if (score >= 50) {
            return "C";
        } else {
            return "D";
        }
    }

    private static String actions(boolean review, boolean urgent) {
        StringBuilder result = new StringBuilder();
        if (review) {
            result.append("REVIEW");
        }
        if (urgent) {
            if (result.length() > 0) {
                result.append("+");
            }
            result.append("URGENT");
        }
        return result.length() == 0 ? "NONE" : result.toString();
    }

    public static void main(String[] args) {
        ScoreCase[] scores = {
            new ScoreCase(-1, "INVALID"),
            new ScoreCase(0, "D"),
            new ScoreCase(49, "D"),
            new ScoreCase(50, "C"),
            new ScoreCase(74, "C"),
            new ScoreCase(75, "B"),
            new ScoreCase(89, "B"),
            new ScoreCase(90, "A"),
            new ScoreCase(100, "A"),
            new ScoreCase(101, "INVALID")
        };

        int scorePassed = 0;
        for (ScoreCase test : scores) {
            String actual = classifyScore(test.input());
            boolean passed = test.expected().equals(actual);
            if (passed) scorePassed++;
            System.out.println("score=" + test.input()
                    + ",expected=" + test.expected()
                    + ",actual=" + actual
                    + ",status=" + (passed ? "PASS" : "FAIL"));
        }
        System.out.println("scoreTests=" + scorePassed + "/" + scores.length);

        FlagCase[] flags = {
            new FlagCase(false, false, "NONE"),
            new FlagCase(true, false, "REVIEW"),
            new FlagCase(false, true, "URGENT"),
            new FlagCase(true, true, "REVIEW+URGENT")
        };

        int flagsPassed = 0;
        for (FlagCase test : flags) {
            String actual = actions(test.review(), test.urgent());
            boolean passed = test.expected().equals(actual);
            if (passed) flagsPassed++;
            System.out.println("review=" + test.review()
                    + ",urgent=" + test.urgent()
                    + ",expected=" + test.expected()
                    + ",actual=" + actual
                    + ",status=" + (passed ? "PASS" : "FAIL"));
        }
        System.out.println("flagTests=" + flagsPassed + "/" + flags.length);

        if (scorePassed != scores.length || flagsPassed != flags.length) {
            throw new AssertionError("At least one case failed");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 IfBranchCaseTableDemo.java
java IfBranchCaseTableDemo
~~~

**Exact expected stdout:**

~~~text
score=-1,expected=INVALID,actual=INVALID,status=PASS
score=0,expected=D,actual=D,status=PASS
score=49,expected=D,actual=D,status=PASS
score=50,expected=C,actual=C,status=PASS
score=74,expected=C,actual=C,status=PASS
score=75,expected=B,actual=B,status=PASS
score=89,expected=B,actual=B,status=PASS
score=90,expected=A,actual=A,status=PASS
score=100,expected=A,actual=A,status=PASS
score=101,expected=INVALID,actual=INVALID,status=PASS
scoreTests=10/10
review=false,urgent=false,expected=NONE,actual=NONE,status=PASS
review=true,urgent=false,expected=REVIEW,actual=REVIEW,status=PASS
review=false,urgent=true,expected=URGENT,actual=URGENT,status=PASS
review=true,urgent=true,expected=REVIEW+URGENT,actual=REVIEW+URGENT,status=PASS
flagTests=4/4
~~~

The demo uses `record` available in Java 17 to declare each row of test data; the test separates **expected** from **actual** and compares them with `equals`. If a logic change makes the two values mismatch, the program prints `FAIL` and throws `AssertionError` after running through the table.

Expected values must be derived from the **specification**, not mechanically copied from the current output of the function under test; otherwise tests can always PASS even when the code violates requirements.

## 7. Checklist before concluding branches are tested

- Have all selectable branches, including `else`, been given at least one test?
- Does every threshold have tests right **below / at / above** it?
- Do compound `&&`/`||` conditions have tests for deciding outcomes on both left and right sides?
- Do multiple independent `if` statements have a test when **both are true**?
- Do invalid, null, empty, or out-of-range cases have clear expected results?
- Does each row compare expected against actual and **fail on mismatch**?
- After reordering branches or changing operators, are existing tests re-run?

For higher confidence, combine case tables with automated testing frameworks like JUnit when a project uses one; the example in this lesson needs only JDK 17 and a self-checking `main` program.

## 8. Practice exercises

**Exercise 1.** Build an input table for `if (x < 0) ... else if (x == 0) ... else ...`. Choose at least `-1`, `0`, and `1`, recording the exact branch and expected result.

**Exercise 2.** In `classifyScore`, intentionally change `score >= 75` to `score > 75`. Which row in the table is expected to FAIL? Why?

**Exercise 3.** Swap the order of the two branches `score >= 90` and `score >= 50`. Which input row catches the wrong first-branch selection bug?

**Exercise 4.** With two independent `if` statements for `review` and `urgent`, explain why all four combinations are needed. What happens if the second `if` is changed to `else if`?

**Exercise 5.** Add a special requirement for `score == 100` (e.g., label `PERFECT`) and update both code and test table: where must the new branch be placed so that it gets selected?

### Key takeaway

**Branch testing starts with a table: input → expected branch → expected result.** Every branch needs a test case; thresholds need near-boundary tests; overlapping conditions and multiple independent `if` statements need combination tests. Checking expected vs. actual is only meaningful when expected values are determined independently of the code under test.