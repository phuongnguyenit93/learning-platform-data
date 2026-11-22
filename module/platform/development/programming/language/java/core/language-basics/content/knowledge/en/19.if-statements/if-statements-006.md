# Boundary Conditions and Branch Evaluation Order — Java 17+

## 1. Goal

In Java, `if`, `else if`, and `else` select a branch based on a `boolean` condition. Two common sources of bugs are:

1. **Wrong boundary conditions**: writing `>` instead of `>=`, missing endpoints, or accepting out-of-range data.
2. **Wrong branch order**: a broader condition placed earlier captures values that should have reached a more specific branch later.

~~~java
int score = 90;
if (score >= 90) {
    System.out.println("A");
} else if (score >= 70) {
    System.out.println("B");
} else {
    System.out.println("C");
}
~~~

**Expected stdout:**

~~~text
A
~~~

When `score == 90`, the `score >= 90` branch is true and runs first; the `else if` and `else` branches **are not evaluated or executed**.

In this lesson, you learn how to specify domains, order conditions clearly, validate values, avoid shadowed branches, and build boundary tests in Java 17+.

## 2. Branch order is part of boundary conditions

An `if / else if / else` chain checks conditions **from top to bottom** and stops at the first true branch. That means branch order and comparison operators **work together** to determine the range of values each branch actually receives:

~~~java
if (score >= 90) {
    grade = "A";
} else if (score >= 70) {
    grade = "B"; // Receives only 70..89 when score is a valid int.
} else {
    grade = "C"; // Receives below 70 within the valid domain.
}
~~~

Not every expression is evaluated: with `score=95`, the condition for branch B is not checked. If you move `>=70` ahead, branch A can become unreachable even though the syntax remains valid.

This lesson focuses on **domains, boundary points, and shadowed branches**. Details on independent versus exclusive `if` statements belong to the previous lesson; therefore, when reviewing a chain, prefer mapping out the **effective range** of each branch rather than merely counting how many branches run.


## 3. Closed and open boundaries: `<`, `<=`, `>`, `>=`

Before writing code, determine **whether a value equal to the boundary itself should be accepted**.

| Description | Java condition | Exact boundary behavior |
|---|---|---|
| Greater than 18 | `age > 18` | 18 is excluded |
| At least 18 years old | `age >= 18` | 18 is included |
| Under 65 | `age < 65` | 65 is excluded |
| At most 65 | `age <= 65` | 65 is included |
| Closed interval 18 to 65 | `age >= 18 && age <= 65` | Includes 18 and 65 |
| Half-open interval 0 to `length` | `index >= 0 && index < length` | Includes 0, excludes `length` |

Example:

~~~java
int age = 18;
boolean adult = age >= 18;
System.out.println(adult); // true
~~~

Java **does not allow writing** `18 <= age <= 65`. Use two boolean expressions joined with `&&`:

~~~java
boolean eligible = age >= 18 && age <= 65;
~~~

Values just outside the domain must also be tested; they frequently reveal *off-by-one* bugs.

## 4. Order branches from specific to broad conditions

Suppose the requirement is:

- Age 65 and over: `SENIOR`.
- Age 18 to under 65: `ADULT`.
- Under 18: `MINOR`.

**Wrong order:**

~~~java
if (age >= 18) {
    group = "ADULT";
} else if (age >= 65) {
    group = "SENIOR"; // Never selected for age >= 65
} else {
    group = "MINOR";
}
~~~

With `age = 70`, the first branch is already true. The condition `age >= 65` is **logically shadowed** even though it is syntactically valid. The compiler is not required to report an error in this case.

**Correct order:**

~~~java
if (age >= 65) {
    group = "SENIOR";
} else if (age >= 18) {
    group = "ADULT";
} else {
    group = "MINOR";
}
~~~

Because by the time execution reaches the second branch `age >= 65` has already been ruled out, `age >= 18` there implicitly denotes the interval `[18, 65)`.

If a classification policy has overlapping conditions with **different priorities** (for instance, an emergency status must override a normal status), state those priorities explicitly before ordering the branches instead of applying a mechanical sorting rule.

## 5. Domain specification for a grading system

Suppose `score` must be from **0 to 100** with four levels:

| Score | Label | Condition |
|---|---|---|
| Outside `[0,100]` | `INVALID` | `score < 0 \|\| score > 100` |
| `[90,100]` | `A` | `score >= 90`, after validation |
| `[70,90)` | `B` | `score >= 70`, after A is false |
| `[50,70)` | `C` | `score >= 50`, after A/B are false |
| `[0,50)` | `D` | `else` |

~~~java
static String grade(int score) {
    if (score < 0 || score > 100) {
        return "INVALID";
    }
    if (score >= 90) {
        return "A";
    } else if (score >= 70) {
        return "B";
    } else if (score >= 50) {
        return "C";
    } else {
        return "D";
    }
}
~~~

**Notable characteristics:**

- Validates the domain **before classifying**, so `score = 101` is not mistaken for A.
- Checks thresholds in descending order `90 → 70 → 50`; higher thresholds are not shadowed by broader branches.
- `score = 90` is A, `score = 70` is B, `score = 50` is C.
- `score = 0` is D, `score = 100` is A.
- No need to repeat `score < 90` in branch B because branch A has already failed.

For out-of-range data, another system might **throw `IllegalArgumentException`** instead of returning `INVALID`. Choose according to the API contract; do not silently “clamp” values into 0–100 unless requested by callers.

## 6. Boundary test table — test three points per threshold

For integer scores, test at minimum just below, right at, and just above each threshold, plus the overall domain boundaries:

| `score` | Expected | Purpose |
|---:|---|---|
| -1 | `INVALID` | Below domain |
| 0 | `D` | Valid lower bound |
| 49 | `D` | Just below 50 |
| 50 | `C` | Right at 50 |
| 51 | `C` | Just above 50 |
| 69 | `C` | Just below 70 |
| 70 | `B` | Right at 70 |
| 71 | `B` | Just above 70 |
| 89 | `B` | Just below 90 |
| 90 | `A` | Right at 90 |
| 91 | `A` | Just above 90 |
| 100 | `A` | Valid upper bound |
| 101 | `INVALID` | Above domain |

Key point: testing only an “in-between” value like 75 is **insufficient** to detect misusing `>`/`>=`.

If the data type is `long` and the boundary is near `Long.MIN_VALUE`/`Long.MAX_VALUE`, **do not mechanically compute `min - 1` or `max + 1`** because that can overflow. Use test values that are validly representable in that type.

## 7. Watch out when conditions overlap or fail to cover the domain

With two conditions:

~~~java
if (value >= 10) {
    label = "TEN_OR_MORE";
} else if (value >= 20) {
    label = "TWENTY_OR_MORE"; // Shadowed
}
~~~

The second branch receives no values because every number `>=20` already matches the first branch.

Conversely, if `else` or a threshold is missing:

~~~java
String label = "UNKNOWN";
if (value < 0) {
    label = "NEGATIVE";
} else if (value > 0) {
    label = "POSITIVE";
}
// value == 0 => stays UNKNOWN
~~~

This may be **intentional** if `UNKNOWN` is a valid state, or a bug if every number must be classified. Map out the domain and decide whether **exhaustive** coverage is required.

For conditions that are not monotonic thresholds (such as `isAdmin`, `isSuspended`, `age >= 18`), **establish explicit rule priorities** rather than sorting by numeric magnitude by default.

## 8. Braces keep boundary conditions attached to the right branch

With nested `if` statements, an unbraced `else` can bind to the nearest `if` missing an `else`, even if the reader assumes it belongs to the outer branch. This can **break boundary checks** because the fallback ends up attached to a different condition:

~~~java
if (validRange) {
    if (score >= 90) {
        System.out.println("A");
    }
} else {
    System.out.println("INVALID");
}
~~~

Here `else` belongs to `if (validRange)`, so every **out-of-range** score is marked INVALID. To report a lower grade for valid scores, add an `else` **inside** the `validRange` block or use a validated classification chain like `grade(int)` in the main program.

Do not let brace ambiguity invert the meaning of your boundary table; the `dangling else` rule and syntactic variants are covered thoroughly in their own lesson.


## 9. Evaluation order can affect side effects and exceptions

~~~java
static boolean check(String name, boolean answer) {
    System.out.println("checked " + name);
    return answer;
}
~~~

~~~java
if (check("first", false)) {
    System.out.println("first branch");
} else if (check("second", true)) {
    System.out.println("second branch");
} else if (check("third", true)) {
    System.out.println("third branch");
}
~~~

**Expected stdout:**

~~~text
checked first
checked second
second branch
~~~

The `third` branch **is not checked** because the second branch is already true. Hence, reordering branches does not always only change the output label: it can change **which methods get called, which side effects occur, or which exceptions are thrown**.

Recommendation: ordinary classification conditions should be **pure and free of state mutations**. If logging or multi-field validation is needed, separate those steps explicitly.

### Guards with `&&` and `||`

~~~java
int[] numbers = {10, 20, 30};
int index = 2;

if (numbers != null
        && index >= 0
        && index < numbers.length) {
    System.out.println(numbers[index]); // 30
}
~~~

Guards on the left precede operations that might fail. `&&` stops immediately when encountering false. Using boolean `&` or placing the element access before the guards can throw `NullPointerException` / `ArrayIndexOutOfBoundsException`.

## 10. `double` boundaries: represented values and tolerance policy

When checking a floating-point threshold, `>=` and `<=` compare the **represented `double` value**, without automatically applying any tolerance:

~~~java
double computed = 0.1 + 0.2;

System.out.println(computed);        // 0.30000000000000004
System.out.println(computed <= 0.3); // false
~~~

If business rules specify tolerance acceptance, define the threshold based on **units and requirements**. Do not arbitrarily loosen a strict boundary just to make a test pass.

For `NaN`, all ordering comparisons `<`, `<=`, `>`, `>=` evaluate to false. Thus, if inputs must be finite:

~~~java
static boolean isValidRatio(double ratio) {
    return Double.isFinite(ratio)
            && ratio >= 0.0
            && ratio <= 1.0;
}
~~~

**Do not use** `if (ratio < 0 || ratio > 1)` as the sole check to reject invalid data: `NaN` satisfies neither side and can slip through.

## 11. Writing readable and testable code

Some guidelines:

1. **Name thresholds** when they carry business meaning: `PASS_MARK`, `SENIOR_AGE`, `FREE_SHIPPING_FROM`.
2. **Reject out-of-range values first**, then classify.
3. When checking descending/ascending thresholds, keep order consistent and ensure earlier branches do not shadow later ones.
4. If rules **have priorities**, put higher-priority rules first and document why.
5. **Avoid mutating variables inside conditions**, such as `if (index++ < length)`, if later branches still use them.
6. Use **braces** and **boundary test tables** to prevent off-by-one or dangling else bugs.
7. Test **results** and, if conditions have side effects, also **operation order**.

There is no need to force every classification into a long nested `?:` conditional expression. A clear `if/else if` chain is usually better when there are three or more branches, input checks, or exception handling.

## 12. Standalone runnable Java 17 program

Save with exact filename **`IfBoundaryBranchOrderDemo.java`**:

~~~java
public final class IfBoundaryBranchOrderDemo {
    private IfBoundaryBranchOrderDemo() {}

    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "INVALID";
        }
        if (score >= 90) {
            return "A";
        } else if (score >= 70) {
            return "B";
        } else if (score >= 50) {
            return "C";
        }
        return "D";
    }

    static String ageGroup(int age) {
        if (age >= 65) {
            return "SENIOR";
        } else if (age >= 18) {
            return "ADULT";
        }
        return "MINOR";
    }

    static String wrongAgeGroup(int age) {
        if (age >= 18) {
            return "ADULT";
        } else if (age >= 65) {
            return "SENIOR";
        }
        return "MINOR";
    }

    static int shippingFee(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        if (amount >= 500_000) {
            return 0;
        } else if (amount >= 200_000) {
            return 15_000;
        }
        return 30_000;
    }

    static String elementOrError(int[] values, int index) {
        if (values == null || index < 0 || index >= values.length) {
            return "OUT_OF_RANGE";
        }
        return Integer.toString(values[index]);
    }

    static boolean check(String name, boolean answer) {
        System.out.println("checked " + name);
        return answer;
    }

    public static void main(String[] args) {
        int[] testScores = {-1, 0, 49, 50, 69, 70, 89, 90, 100, 101};
        for (int score : testScores) {
            System.out.println("score " + score + "=" + grade(score));
        }

        System.out.println("age 17=" + ageGroup(17));
        System.out.println("age 18=" + ageGroup(18));
        System.out.println("age 65=" + ageGroup(65));
        System.out.println("wrong age 70=" + wrongAgeGroup(70));
        System.out.println("right age 70=" + ageGroup(70));

        System.out.println("fee 199999=" + shippingFee(199_999));
        System.out.println("fee 200000=" + shippingFee(200_000));
        System.out.println("fee 499999=" + shippingFee(499_999));
        System.out.println("fee 500000=" + shippingFee(500_000));

        int[] values = {10, 20, 30};
        System.out.println("index -1=" + elementOrError(values, -1));
        System.out.println("index 0=" + elementOrError(values, 0));
        System.out.println("index 2=" + elementOrError(values, 2));
        System.out.println("index 3=" + elementOrError(values, 3));
        System.out.println("index null=" + elementOrError(null, 0));

        double sum = 0.1 + 0.2;
        System.out.println("double sum=" + sum);
        System.out.println("double at most 0.3=" + (sum <= 0.3));
        System.out.println("NaN valid ratio=" + isValidRatio(Double.NaN));

        if (check("first", false)) {
            System.out.println("chosen=first");
        } else if (check("second", true)) {
            System.out.println("chosen=second");
        } else if (check("third", true)) {
            System.out.println("chosen=third");
        } else {
            System.out.println("chosen=else");
        }

        Boolean permission = null;
        if (Boolean.TRUE.equals(permission)) {
            System.out.println("permission=ALLOWED");
        } else {
            System.out.println("permission=DENIED");
        }
    }

    static boolean isValidRatio(double ratio) {
        return Double.isFinite(ratio)
                && ratio >= 0.0
                && ratio <= 1.0;
    }
}
~~~

**Requirements:** JDK 17+, terminal in the directory containing the file; standard JDK only.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IfBoundaryBranchOrderDemo.java
java -cp . IfBoundaryBranchOrderDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IfBoundaryBranchOrderDemo.java
java -cp . IfBoundaryBranchOrderDemo
~~~

**Exact expected stdout:**

~~~text
score -1=INVALID
score 0=D
score 49=D
score 50=C
score 69=C
score 70=B
score 89=B
score 90=A
score 100=A
score 101=INVALID
age 17=MINOR
age 18=ADULT
age 65=SENIOR
wrong age 70=ADULT
right age 70=SENIOR
fee 199999=30000
fee 200000=15000
fee 499999=15000
fee 500000=0
index -1=OUT_OF_RANGE
index 0=10
index 2=30
index 3=OUT_OF_RANGE
index null=OUT_OF_RANGE
double sum=0.30000000000000004
double at most 0.3=false
NaN valid ratio=false
checked first
checked second
chosen=second
permission=DENIED
~~~

Quick explanation:

- `score 50`, `70`, `90` enter the group starting **right at the threshold** thanks to `>=`.
- `wrong age 70=ADULT` shows that the broader `age >= 18` branch shadowed `age >= 65`.
- Shipping fees drop right at 200,000 and 500,000, not before the thresholds.
- Index 3 equals `values.length` and is therefore rejected.
- `0.1+0.2` exceeds the literal `0.3` by a small binary rounding error, and `NaN` is rejected by the finiteness check.
- Only `checked first` and `checked second` run; the third condition is never called.
- `Boolean.TRUE.equals(null)` evaluates to false without unboxing null.

## 13. Common mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Using `score > 90` when 90 belongs to A | Misses exact boundary | `score >= 90` |
| Placing `score >= 50` before `score >= 90` | Value 90 is captured by C first | Order thresholds properly |
| Using `else if` for two properties that both must report | Only the first true branch runs | Use two independent `if` statements |
| Using multiple `if` statements when only one label is wanted | Can run multiple branches | Use an `else if` chain |
| Not validating `score > 100` | Score 101 is treated as A | Check domain first |
| Using `index <= array.length` | Off-by-one, potential access error | `index < array.length` |
| Writing `18 <= age <= 65` | Invalid in Java | `age >= 18 && age <= 65` |
| Assuming `else` belongs to the outer `if` arbitrarily | Dangling else binds to nearest if | Use `{ }` |
| Reordering conditions with side effects | Changes method call order/runtime errors | Separate side effects, preserve order |
| Assuming `double` compares boundaries like exact decimals | Precision discrepancies | Choose model/tolerance per requirements |
| Checking only `ratio < 0 \|\| ratio > 1` | `NaN` can slip through | `Double.isFinite(ratio)` |
| Computing `max+1` near `Integer.MAX_VALUE` for tests | Overflow | Use validly representable test values |
| Testing only mid-range values | Misses bugs at both ends | Test below/at/above thresholds |

## 14. Exercises with answers

### Exercise A — classify from high to low thresholds

Requirement: `score >= 80` → GOOD, `score >= 50` → PASS, otherwise → FAIL.

~~~java
String label;
if (score >= 80) {
    label = "GOOD";
} else if (score >= 50) {
    label = "PASS";
} else {
    label = "FAIL";
}
~~~

**Boundary answers:** 49 → FAIL; 50 → PASS; 79 → PASS; 80 → GOOD. If there is a separate valid domain (e.g., 0–100), validate first.

### Exercise B — why is `age >= 18` before `age >= 65` wrong?

**Answer:** ages 65 and over already satisfy `age >= 18`, so the later senior branch is never checked. Put `age >= 65` first.

### Exercise C — two `if` statements or `else if`?

Want to print **both** `positive` and `even` for the number 4:

~~~java
if (number > 0) System.out.println("positive");
if (number % 2 == 0) System.out.println("even");
~~~

**Answer:** two independent `if` statements are needed because both conditions can be true at once. Using `else if` would print only `positive`.

### Exercise D — checking array index

An array has three elements; what are the valid indices?

**Answer:** `0`, `1`, `2`; condition `index >= 0 && index < 3`. Indices -1 and 3 are both rejected.

### Exercise E — branch execution order

~~~java
if (check("A", false)) {
    System.out.println("A");
} else if (check("B", true)) {
    System.out.println("B");
} else if (check("C", true)) {
    System.out.println("C");
}
~~~

**Answer:**

~~~text
checked A
checked B
B
~~~

Method `check` is from the full program. `check("C", true)` is not called.

## 15. Checklist and conclusion

- [ ] Clearly define the valid domain and exact behavior at each boundary.
- [ ] Use `>`/`>=`, `<`/`<=` according to specification.
- [ ] Understand that `if/else if/else` checks top-to-bottom and stops at the **first true branch**.
- [ ] Distinguish an `else if` chain from multiple independent `if` statements.
- [ ] Order broad/narrow conditions or business priorities so necessary branches are not shadowed.
- [ ] Validate out-of-range values before classifying.
- [ ] Build a test table at **below/at/above** each threshold, including both overall domain bounds.
- [ ] Never write chained comparisons like `min <= value <= max` in Java.
- [ ] Use `{ }` to avoid dangling else.
- [ ] Do not overlook the effect of branch order on side effects and exceptions.
- [ ] Place `&&`/`||` guards in the right order before potentially failing accesses.
- [ ] Watch out for `double` at boundaries, NaN, and overflow when testing extreme integer values.
- [ ] Run `IfBoundaryBranchOrderDemo.java` with Java 17+ and compare against exact stdout.

**Conclusion:** Writing `if` correctly is not just crafting expressions that return true/false; you must also **define boundaries**, **prioritize branches**, **cover the data domain**, and **test values near thresholds**. With an `else if` chain, order itself is part of the business logic. Placing conditions deliberately and testing at boundaries prevents both *off-by-one* bugs and shadowed branches.