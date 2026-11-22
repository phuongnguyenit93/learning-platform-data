# Using `assert` to Check Internal Assumptions and Enabling with `-ea` (Java 17+)

## 1. What Is `assert`?

`assert` is a Java statement used to check an **assumption the programmer believes must always hold true** if the program is working properly. It is especially useful for detecting violations of invariants, algorithm postconditions, or internal states that should be impossible by design.

If checks are **enabled** and the condition is false, Java throws `java.lang.AssertionError`. If the condition is true, the program proceeds. In most standard Java applications, assertions are **disabled by default at runtime**, so `assert` statements are skipped unless enabled with a JVM option such as `-ea` (*enable assertions*).

Conceptual example:

```java
assert index >= 0 : "negative internal index: " + index;
```

This is appropriate if `index` is an **internal** value derived from an algorithm that is guaranteed to be non-negative. It is **not appropriate** as the sole input validation layer for an `index` parameter sent by a user, because when assertions are disabled, the check does not run.

**Distinction:** `assert` is a Java language statement, not JUnit's `assertEquals` method and not `throw new IllegalArgumentException(...)`. Assertion methods in testing frameworks operate via the framework's own mechanisms.

## 2. Syntax and Evaluation Mechanism

Java has two syntax forms:

```java
assert booleanExpression;
assert booleanExpression : detailExpression;
```

- `booleanExpression` must evaluate to `boolean` or `Boolean` (unboxable). For instance, `assert count >= 0;` is valid, whereas `assert count;` is invalid if `count` is an `int`.
- `detailExpression` is an expression that yields a value (it must not be a call to a `void` method); that value is used to construct the `AssertionError` detail message. It does not mean a `println` statement is always executed.
- When assertions are **enabled**: Java evaluates the condition; if `false`, it evaluates the expression after `:` (if present) and throws `AssertionError` with that detail.
- When assertions are **disabled**: neither the condition nor the detail expression is **evaluated**. Therefore, never put side effects inside an assertion.
- If the condition is a `Boolean` with value `null`, unboxing while evaluating the assertion can throw `NullPointerException`. Avoid using a nullable value directly as the condition.

In Java 17, `assert` is a keyword and cannot be used as a method or variable name. The statement is checked for syntax and types **at compile time**, even when assertions will be disabled at runtime.

Example when assertions are enabled:

```java
int count = 2;
assert count >= 0;                        // true: continues
assert count % 2 != 0 : "count is even"; // false: throws AssertionError with message
```

This is an **illustrative snippet**, not a standalone program file; the full runnable example follows in the next section.

## 3. Complete Example: Seeing the Difference With and Without `-ea`

Create a file named **`AssertDemo.java`**:

```java
public class AssertDemo {
    private static int halfEven(int number) {
        assert number % 2 == 0 : "even input required: " + number;
        return number / 2;
    }

    public static void main(String[] args) {
        System.out.println("enabled=" + AssertDemo.class.desiredAssertionStatus());
        System.out.println("half(8)=" + halfEven(8));

        try {
            System.out.println("half(5)=" + halfEven(5));
        } catch (AssertionError error) {
            System.out.println("caught=" + error.getClass().getSimpleName());
            System.out.println("detail=" + error.getMessage());
        }
    }
}
```

From the directory containing the file (JDK 17+; works on PowerShell, CMD, bash), create the `out` directory if it does not exist, then compile:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out AssertDemo.java
```

### Normal Run: Assertions Disabled

```sh
java -cp out AssertDemo
```

**Exact stdout** when no extra assertion-enabling option is set:

```text
enabled=false
half(8)=4
half(5)=2
```

`halfEven(5)` returns `2` due to integer division because the `assert` statement is not executed. The example intentionally passes an odd number to show why **you must not use `assert` for mandatory data validation**.

### Run with `-ea`: Assertions Enabled

```sh
java -ea -cp out AssertDemo
```

**Exact stdout:**

```text
enabled=true
half(8)=4
caught=AssertionError
detail=even input required: 5
```

The call with `8` satisfies the condition and returns `4`. The call with `5` throws `AssertionError`, so `System.out.println("half(5)=" + ...)` does not print a value line. The `catch (AssertionError)` block here is used **only to display deterministic output for learners**; in real applications, a failed assertion indicates a programming bug that must be fixed rather than caught to pretend normal execution continues.

`AssertDemo.class.desiredAssertionStatus()` reports the configured assertion status for the class; when run with the standard Java launcher in this example, it matches the actual assertion state. In programs with custom class loaders that adjust assertion status, do not treat this method as a business error-checking mechanism.

**Command note:** `-ea` is a runtime option for **`java`**, not an option for `javac`. You do not need to recompile between the two runs; a single `.class` file exhibits both behaviors due to different JVM settings.

## 4. Enabling/Disabling Assertions by Class and Package

Common options with `java`:

| Option | Effect |
| --- | --- |
| `-ea` or `-enableassertions` | Enables assertions for regular application classes per JVM default scope |
| `-da` or `-disableassertions` | Disables assertions for classes in the corresponding scope |
| `-ea:lesson.AssertDemo` | Enables for a single class with fully qualified name `lesson.AssertDemo` |
| `-ea:lesson...` | Enables for package `lesson` and its subpackages |
| `-da:lesson.Legacy` | Disables for a specific class |
| `-esa` or `-enablesystemassertions` | Enables assertions in system classes; usually unnecessary for beginner programs |

Class and package names in the argument must match the **actual fully qualified names**. For instance, `AssertDemo` in section 3 is in the unnamed package, so enable it specifically with `-ea:AssertDemo` rather than `-ea:lesson.AssertDemo`.

Enable/disable flags can be combined to configure by class/package; when doing so, follow the Java launcher rules and test against the actual launched program. Place options **before the class name containing `main`** or before `-jar` when running a JAR:

```sh
java -ea -cp out AssertDemo
java -ea:AssertDemo -cp out AssertDemo
java -da -cp out AssertDemo
```

These commands use the `AssertDemo.class` compiled in section 3. Do not write `java -cp out AssertDemo -ea` expecting the JVM to process `-ea`: placed after the class name, it is merely passed as an argument to `main(String[] args)`.

### Dedicated Package Example

Create **`src/lesson/InvariantDemo.java`**:

```java
package lesson;

import java.util.Arrays;

public class InvariantDemo {
    private static boolean isSorted(int[] values) {
        for (int i = 1; i < values.length; i++) {
            if (values[i - 1] > values[i]) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        int[] values = {3, 1, 2};
        Arrays.sort(values);
        assert isSorted(values) : "sorting postcondition failed";

        System.out.println("enabled=" + InvariantDemo.class.desiredAssertionStatus());
        System.out.println("sorted=" + Arrays.toString(values));
    }
}
```

Compile and run:

```sh
javac -encoding UTF-8 --release 17 -d out src/lesson/InvariantDemo.java
java -cp out lesson.InvariantDemo
java -ea:lesson.InvariantDemo -cp out lesson.InvariantDemo
```

**Stdout of the first run (assertions disabled):**

```text
enabled=false
sorted=[1, 2, 3]
```

**Stdout of the second run (enabled for that exact class):**

```text
enabled=true
sorted=[1, 2, 3]
```

This example shows the proper place for `assert`: checking an **internal postcondition** after sorting. You do not use an assertion to decide whether to sort, because the algorithm must still work correctly when assertions are disabled.

## 5. Do Not Put Side Effects in Assertions

The code below compiles validly, yet **is a pattern to avoid**:

```java
assert ++counter > 0;
```

If assertions are disabled, `counter` does not increment; if enabled, `counter` increments. Program state changes solely because `-ea` was added.

To see the difference, create **`SideEffectDemo.java`**:

```java
public class SideEffectDemo {
    public static void main(String[] args) {
        int counter = 0;
        assert ++counter == 1 : "unexpected counter";
        System.out.println("counter=" + counter);
    }
}
```

```sh
javac -encoding UTF-8 --release 17 -d out SideEffectDemo.java
java -cp out SideEffectDemo
java -ea -cp out SideEffectDemo
```

The two runs produce the following outputs respectively:

Without `-ea`:

```text
counter=0
```

With `-ea`:

```text
counter=1
```

**Correct style:** perform important updates outside `assert`, and then check only an expression that **does not mutate state**:

```java
counter++;
assert counter == 1 : "unexpected counter";
```

This fix illustrates code in a scope where `counter` exists. Even in the `detailExpression` after `:`, do not perform file writes, data updates, or side-effecting calls: that expression is evaluated only when assertions are enabled **and the condition is false**.

## 6. When to Use `assert` vs. When to Use `if` and `throw`

| Purpose | Approach |
| --- | --- |
| Guarding **public API** preconditions where caller-supplied arguments may be invalid | `if` + `throw new IllegalArgumentException(...)` or `Objects.requireNonNull(...)` |
| Validating external data: requests, files, DB, CLI, network | Always-on checks with explicit error handling; do not substitute `assert` |
| Checking internal invariants that must hold if the code has no bugs | `assert condition : detail;` |
| Checking internal algorithm postconditions to catch bugs during development | `assert postcondition;` |
| Verifying results with JUnit in automated tests | Use JUnit/test framework assertions per test contract |

**Illustrative comparison** (the methods below must be placed in an appropriate class; not a standalone file):

```java
// External input: checks must run even when assertions are disabled.
public static int positive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}

// Value derived inside the algorithm: guards a programming assumption.
private static int internalHalf(int provenEven) {
    assert provenEven % 2 == 0 : "algorithm produced an odd value";
    return provenEven / 2;
}
```

If `provenEven` actually comes from unvalidated user input, an assertion is not enough to uphold the contract. What matters is the **origin and meaning of the data**, not just whether a method is `private` or `public`.

Using `assert false : "unreachable state";` to mark a logic branch that should be unreachable is a debugging technique. However, when assertions are disabled, that statement does nothing; therefore **never use `assert false` instead of `throw`** when the application must reject that state in all environments.

## 7. `AssertionError` Is Not a Normal Business Exception

`AssertionError` extends `Error`, and `Error` extends `Throwable`. It does **not** extend `Exception`. Therefore:

```java
try {
    assert false : "broken assumption";
} catch (Exception ex) {
    System.out.println("not caught");
}
```

This snippet does not catch `AssertionError` when assertions are enabled, because `catch (Exception)` does not match `Error`. When assertions are disabled, the `assert` statement is skipped and the `catch` does not run. This is not a complete program example; see section 3 for a runnable version that catches `AssertionError` for demonstration.

Do not use `catch (Throwable)` or `catch (AssertionError)` broadly to turn programming bugs into default results. When `AssertionError` occurs, the right action is usually to investigate the broken assumption, the input leading to that state, and the algorithm's execution path.

If `AssertionError` goes uncaught, the message/stack trace is printed by the JVM to standard error (*stderr*); stack trace content includes file names and line numbers that can vary. That is why the main example intentionally catches the error so learners observe **exact stdout** without depending on stack trace details.

## 8. Common Mistakes

1. **Forgetting `-ea`:** seeing no error and assuming the assertion ran. Check the JVM command line or IDE Run/Debug configuration.
2. **Using `assert` instead of validation:** when deployed with assertions off, invalid input slips through; use `if`/`throw` or an appropriate validation API.
3. **Having side effects in the expression:** updating variables, deleting files, or calling mutating APIs may happen in only one JVM mode.
4. **Confusing `-ea` with a compiler flag:** `javac` still parses and compiles the statement; `java -ea` controls checking at runtime.
5. **Placing `-ea` after the main class name:** the launcher passes it to `main` as a program argument.
6. **Using `assert` to report expected failures:** missing files, invalid JSON, and bad user input are normal operational situations, not necessarily internal bugs.
7. **Confusing it with JUnit assertions:** calls like `Assertions.assertEquals` are library APIs and do not need `-ea` for JUnit's test logic to execute.
8. **Assuming every Java class is enabled just by `-ea`:** configuration has class/package scopes, class loaders, and system class rules; verify which classes are actually affected when using selective flags.

## 9. Practice Checklist

Before adding an assertion, ask:

- Is this condition **guaranteed to hold if the algorithm has no bugs**, or is it external data that can legitimately be invalid?
- Are both the test expression and the detail expression **free of side effects**?
- When `-ea` is off, does the program still maintain all required behavior?
- If the condition fails, does the message show the key values/variables needed to find the bug?
- When running locally or testing, did I enable assertions for the classes or packages under test?
- After fixing a bug, was the program tested both **with** and **without `-ea`**?

### Self-Check

**1. Does `assert value > 0;` run by default in most Java applications?** No. Assertions must be enabled with `java -ea ...` or an equivalent configuration.

**2. When an assertion fails and is enabled, what does Java throw?** `AssertionError`, which is under `Error`, not `Exception`.

**3. Does `assert condition : detail;` always evaluate `detail`?** No. It is evaluated only when assertions are enabled and the condition is false.

**4. Can `assert` be used as a mandatory check for an entered monetary amount?** No. Use always-on validation that throws the appropriate exception type or returns an error result per the API contract.

**5. Do you need to change the `javac` command or recompile to enable assertions?** No. Just run the program with `java -ea ...` and ensure the target classes are enabled.

**Remember:** `assert` is a tool for catching **violations of internal assumptions**; `-ea` enables checking at **runtime**. The program must remain functionally correct even when assertions are disabled.