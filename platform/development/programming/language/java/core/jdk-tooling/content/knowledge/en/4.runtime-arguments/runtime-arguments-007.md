# Assertion Options in Java

## 1. What is an Assertion?

An **assertion** is a statement used to check a developer's assumption about the internal state or logic of a program. An assertion expresses a condition that, at that point of execution, the developer believes must always be true.

In Java, an assertion is written using the `assert` keyword. When assertions are enabled and the condition is false, the JVM throws `AssertionError`. When assertions are disabled, the assertion statement has no effect: neither the condition expression nor the message expression is evaluated.

Assertions are commonly useful for:

- Checking the invariant of an object or data structure.
- Verifying internal conditions that an algorithm needs to maintain.
- Checking assumptions in logic branches that the developer considers unreachable.
- Detecting programming bugs early during development and testing.

For example, a balanced-tree algorithm might assume that the heights of two subtrees do not differ beyond a certain limit. An assertion helps detect when an update operation breaks that invariant.

Assertions are part of the Java language. An **assertion option** is a JVM startup option that decides which `assert` statements are enabled or disabled.

## 2. assert Syntax

Java has two forms of the assertion statement:

```java
assert condition;
assert condition : detailMessage;
```

Where:

- `condition` must have type `boolean` or `Boolean`.
- `detailMessage` is an expression that evaluates to a value, used as diagnostic information when the condition is false. This expression must not have type `void`.
- If the condition is true, the statement completes normally.
- If the condition is false and assertions are enabled, the JVM throws `AssertionError`. If a message is provided, the value of the message expression is converted into the error's detail message.
- If assertions are disabled, neither expression in the statement is executed.

Example:

```java
int itemCount = 12;
assert itemCount >= 0;
assert itemCount <= 100 : "itemCount is out of expected range: " + itemCount;
```

The form with a message is especially useful when you need to know which value caused the assumption to fail. The message is evaluated when the condition is false, so there is no need to build the diagnostic string when the condition is true.

### 2.1. A Failed Assertion Produces an AssertionError

`AssertionError` is a subclass of `Error`, not a subclass of `Exception`. It indicates that an assumption in the program no longer holds true.

Example:

```java
int remainingBytes = 4;
assert remainingBytes == 0 : "Unexpected bytes remaining: " + remainingBytes;
```

If assertions are enabled, the program throws `AssertionError` with the corresponding diagnostic information. The stack trace typically points to the file and line of code containing the failed assertion.

Assertions should not be used as a normal error-handling mechanism, nor should `AssertionError` be caught to continue as if invalid input were a recoverable situation. Assertions usually indicate a logic bug or a violation of an internal assumption that needs investigation.

## 3. Assertions Are Disabled by Default

By default, `assert` statements in Java are disabled when an application starts. Therefore, simply writing:

```java
assert balance >= 0;
```

does not mean the condition will always be checked when the application runs.

To check assertions, you must enable them using a Java launcher option. This enabling or disabling happens at JVM startup, not via a statement in source code.

This allows development teams to enable checks in development or test environments, while choosing whether to enable or disable them in other environments depending on operational needs.

## 4. Important Assertion Options

Common options for the `java` command:

| Option | Meaning |
|---|---|
| `-ea` or `-enableassertions` | Enables assertions for application classes; the no-argument form does not apply to system classes |
| `-da` or `-disableassertions` | Disables assertions for application classes; the no-argument form does not apply to system classes |
| `-ea:com.example...` | Enables assertions in package `com.example` and its subpackages |
| `-da:com.example...` | Disables assertions in package `com.example` and its subpackages |
| `-ea:com.example.Checks` | Enables assertions specifically in class `com.example.Checks` |
| `-da:com.example.LegacyParser` | Disables assertions specifically in class `com.example.LegacyParser` |
| `-esa` or `-enablesystemassertions` | Enables assertions in system classes |
| `-dsa` or `-disablesystemassertions` | Disables assertions in system classes |

Key points to remember:

- `-ea` is short for `-enableassertions`.
- `-da` is short for `-disableassertions`.
- In its no-argument form, `-ea` enables assertions in application classes; system classes require the separate `-esa` option.
- `-da` without arguments disables assertions in application classes; `-dsa` controls assertions in system classes.
- The three dots `...` at the end of a package name are syntax indicating the package and all of its subpackages. It is not the `*` wildcard.
- A class name must be a fully qualified class name, including the package if the class belongs to one.
- Multiple options can be combined in the same command. The JVM processes them in order before loading classes, so a specific option appearing later can override an earlier one for overlapping scopes.

### 4.1. Enabling Assertions for All Application Classes

```bash
java -ea -cp out com.example.Main
```

This command enables assertions in the application classes run by the JVM. System classes are not enabled by the no-argument `-ea` form alone.

If running the application from a JAR:

```bash
java -ea -jar app.jar
```

### 4.2. Enabling Assertions for a Package

```bash
java -ea:com.example... -cp out com.example.Main
```

This scope includes classes in package `com.example` and subpackages such as `com.example.service` or `com.example.internal`.

If you only want to enable assertions in a single class:

```bash
java -ea:com.example.Checks -cp out com.example.Main
```

### 4.3. Enabling for a Package Then Disabling a Specific Class

You can combine `-ea` and `-da` to create a fine-grained scope:

```bash
java -ea:com.example... -da:com.example.LegacyParser -cp out com.example.Main
```

In this example, assertions are enabled for package `com.example` and its subpackages, and then disabled specifically for class `com.example.LegacyParser`. Option order matters because the JVM processes them in order before loading classes.

### 4.4. Enabling Assertions in System Classes

```bash
java -esa -jar app.jar
```

`-esa` enables assertions in system classes. This is typically used for diagnostics or when developing the JVM and platform libraries; ordinary applications usually only need `-ea` for their own classes.

## 5. Placement of Assertion Options in the java Command

An assertion option is a **JVM option**, so it must be placed before the main class name or before `-jar`.

Correct:

```bash
java -ea -cp out com.example.Main
java -ea -jar app.jar
```

Incorrect placement:

```bash
java -cp out com.example.Main -ea
```

In the last command, `-ea` appears after the main class name, so it is passed into `args[]` of the `main` method as an application argument. It does not enable assertions for the JVM.

Also do not pass `-ea` to the `javac` compilation command. Assertion options control runtime behavior; the compiler simply compiles Java code containing the `assert` keyword as normal.

When running with modules, the assertion option is also placed before the option specifying the main module, for example:

```bash
java -ea -m my.module/com.example.Main
```

## 6. Practical Example: Observing the Difference Between Enabled and Disabled Assertions

Create the file `src/com/example/AssertionDemo.java`:

```java
package com.example;

public class AssertionDemo {
    public static void main(String[] args) {
        int itemCount = -3;

        assert itemCount >= 0
                : "itemCount must be non-negative, actual=" + itemCount;

        System.out.println("itemCount=" + itemCount);
    }
}
```

Compile the program:

```bash
javac -d out src/com/example/AssertionDemo.java
```

### 6.1. Running with Assertions Disabled

```bash
java -cp out com.example.AssertionDemo
```

Output:

```text
itemCount=-3
```

The condition `itemCount >= 0` is not evaluated because assertions are disabled by default. The program continues to the `println` statement.

### 6.2. Running with Assertions Enabled

```bash
java -ea -cp out com.example.AssertionDemo
```

Main output:

```text
Exception in thread "main" java.lang.AssertionError: itemCount must be non-negative, actual=-3
```

The JVM throws `AssertionError` and terminates the current execution thread if the error is unhandled. The full stack trace also includes the line location in the Java file.

### 6.3. Testing with a True Condition

Change the value of `itemCount` to `3` and run again with `-ea`:

```text
itemCount=3
```

When the condition is true, the assertion is evaluated and the program continues normally.

## 7. Using Assertions to Check Invariants and Internal Assumptions

Assertions are effective when checking conditions that the program must maintain internally.

For example, a class managing a numeric range has the invariant that the start value is not greater than the end value:

```java
public class NumberRange {
    private int start;
    private int end;

    public NumberRange(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start must be <= end");
        }

        this.start = start;
        this.end = end;
        assert this.start <= this.end : "Invalid range state";
    }

    public int size() {
        assert start <= end : "Range invariant was broken";
        return end - start;
    }
}
```

The constructor uses `IllegalArgumentException` to reject invalid input data. The assertion after field assignment checks the internal invariant that the class must maintain. The `size` method re-checks the assumption before computing the result.

Some suitable use cases:

- Checking internal state after an update operation.
- Checking intermediate results of an algorithm.
- Checking relationships between variables that program logic must guarantee.
- Checking a code branch that is supposed to be unreachable.

Example of an unexpected branch:

```java
switch (status) {
    case READY -> start();
    case STOPPED -> stop();
    case PAUSED -> resume();
    default -> {
        assert false : "Unexpected status: " + status;
        throw new IllegalStateException("Unsupported status: " + status);
    }
}
```

Here, the exception is still thrown when assertions are disabled, so the program does not silently continue with an unsupported status. The assertion adds diagnostic information when enabled.

## 8. Things You Should Not Do with assert

### 8.1. Do Not Use assert to Validate Public Method Inputs

Do not write:

```java
public void transfer(Account target, int amount) {
    assert target != null;
    assert amount > 0;

    // Perform the money transfer
}
```

If assertions are disabled, those conditions are not checked. The public method's contract is therefore not guaranteed.

Use appropriate exceptions instead:

```java
import java.util.Objects;

public void transfer(Account target, int amount) {
    Objects.requireNonNull(target, "target must not be null");

    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    // Perform the money transfer
}
```

Public input validation must always run, regardless of whether the JVM has assertions enabled.

### 8.2. Do Not Put Side Effects in Assertion Expressions

Do not write:

```java
assert queue.remove(item);
```

When assertions are enabled, the item is removed from the queue. When assertions are disabled, the removal does not happen. The program therefore behaves differently depending on the JVM option.

Perform the operation first, then check the result:

```java
boolean removed = queue.remove(item);
assert removed : "Expected item to be present in queue";
```

The removal always occurs; the assertion only checks the assumption about the result.

### 8.3. Do Not Use assert for Security Protection

Do not use assertions as the sole check layer for access permissions, authentication, untrusted data, or safety conditions. Security checks must always be executed and must have clear behavior upon failure.

### 8.4. Do Not Rely on assert to Create Required Data

Do not place initialization or state-updating calls inside an assertion condition. Because the statement can be skipped entirely, the required data might never be created or updated.

### 8.5. Do Not Confuse AssertionError with Business Exceptions

`AssertionError` typically indicates an error in the developer's assumptions. Business situations such as insufficient balance, invalid input data, or a missing resource should be represented by appropriate exceptions or explicit business results.

## 9. Assertion Options in IDEs and Build Tools

When running Java from an IDE or build tool, the JVM is not necessarily launched with the exact command you type in a terminal. You need to place the assertion option in the configuration section meant for the JVM.

| Tool | Common Location |
|---|---|
| IntelliJ IDEA | Run/Debug Configuration → VM options |
| Eclipse | Run Configurations → Arguments → VM arguments |
| Visual Studio Code | `vmArgs` field in the Java launch configuration |
| Direct `java` command | Place `-ea` before the main class name or `-jar` |
| Maven/Gradle test runner | Configure the test process JVM according to the plugin or task in use |

For example, a launch configuration in VS Code can use the `vmArgs` field:

```json
{
  "type": "java",
  "name": "Run with assertions",
  "request": "launch",
  "mainClass": "com.example.AssertionDemo",
  "vmArgs": "-ea"
}
```

If you put `-ea` in program arguments instead of VM options, assertions will not be enabled. When debugging an issue that only appears in assertion mode, check the run configuration of the IDE and the test process separately.

## 10. How Are Java assert and JUnit Assertions Different?

These two concepts have similar names, but their mechanisms are different:

| Criterion | Java `assert` | JUnit Assertions |
|---|---|---|
| Nature | A keyword and statement of the Java language | Methods of a testing library |
| Enable/Disable | Depends on the JVM's assertion status | Called like normal test methods |
| On failure | Throws `AssertionError` | The test framework records a test failure, typically via an assertion error |
| Scope | Assumptions and invariants in program code | Verifying expected test outcomes |
| JVM assertions disabled | Java `assert` statements do not execute | JUnit calls such as `assertEquals` still run |

JUnit example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

`assertEquals` is a JUnit method, not Java's `assert` statement. It is still executed according to the test framework's mechanism, regardless of whether `-ea` is passed.

In real projects, use JUnit Assertions to verify test results; use Java `assert` to express internal program assumptions.

## 11. Common Mistakes When Using Assertion Options

| Symptom | Cause | Solution |
|---|---|---|
| Assertion is false but program keeps running | JVM has not enabled assertions | Add `-ea` to VM options |
| `-ea` is set but has no effect | Placed after the main class name or in program arguments | Move `-ea` before the class name or `-jar` |
| A class in a package does not check assertions | Option scope does not include that package or class | Use `-ea:com.example...` or the fully qualified class name |
| One class does not check while the package is enabled | A specific `-da` option overrides the broader scope | Check the order of options and their applicable scopes |
| Assertions run in terminal but not in IDE | IDE uses a separate JVM configuration | Check VM options in Run/Debug Configuration |
| Application behavior changes when assertions are enabled | Assertion expression has side effects | Move the side-effect operation outside the `assert` statement |
| Public method lets invalid data through | Using `assert` to validate public parameters | Use exceptions or validation that always executes |

You can quickly test by creating an assertion that is guaranteed to fail:

```java
assert false : "Assertion option check";
```

Then run the program once without `-ea` and once with `-ea`. If configured properly, the run with assertions enabled will throw `AssertionError`.

## 12. Practice and Verification Workflow

When you need to verify assertion options in a project:

1. Find the `assert` statements in the source code and determine whether they check invariants or input data.
2. Check how the application is launched: terminal, IDE, Maven, Gradle, or container.
3. Place `-ea` in the JVM options of the right process.
4. If a smaller scope is needed, use `-ea:package...` or `-ea:fully.qualified.Class`.
5. Create a scenario that makes the condition false to confirm `AssertionError` appears.
6. Run again with assertions disabled to understand which statements are skipped.
7. Remove side effects from assertion expressions and use exceptions for mandatory conditions.
8. Document the run configuration in docs or team settings if assertions are part of the testing workflow.

## 13. Summary

Assertions are a tool for checking assumptions and invariants in Java programs. Because `assert` statements can be disabled at runtime, you need to understand how to control them with assertion options:

- `-ea` enables assertions in application classes.
- `-da` disables assertions in application classes.
- `-ea:package...` or `-ea:ClassName` limits the enabled scope.
- `-da:package...` or `-da:ClassName` limits the disabled scope.
- `-esa` and `-dsa` control assertions in system classes.
- JVM options must appear before the main class name or `-jar`.
- Do not use assertions for side effects, public method input validation, or security protection.
- Java `assert` is different from JUnit assertion methods.

When used for its intended purpose, assertions help detect faulty assumptions during development and testing, while providing useful information to track down the root cause of logic bugs.
