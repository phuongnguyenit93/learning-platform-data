# `throw` to Signal Errors and `throws` to Declare Possible Exceptions (Java 17+)

## 1. Distinguish Them Right from the Start

Java uses two easily confused keywords:

- **`throw`** is a **statement** that actually throws an exception object at the current point of execution, usually when invalid data or state is detected.
- **`throws`** appears in a **method or constructor declaration**, listing the exception types that may be propagated out to the caller. It does not throw, catch, or handle exceptions on its own.

Syntax example:

```java
static int requirePositive(int value) throws IllegalArgumentException {
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}
```

Here, `throw new IllegalArgumentException(...)` creates and throws the exception when the condition is true. The `throws IllegalArgumentException` clause only declares the possibility; because this is an **unchecked exception**, declaring `throws` is **optional**. In projects, `throws` is usually omitted for unchecked exceptions unless it helps express the API contract. The example above is an illustrative method, not a standalone program with `main`.

| Criterion | `throw` | `throws` |
| --- | --- | --- |
| Placement | Inside a method body, constructor, or block that can contain statements | After the parameter list of a method/constructor, before the body or `;` |
| Role | Throws an object of a `Throwable` type | Declares one or more exception **types** that may arise |
| Common form | `throw new IOException("...");` | `void read() throws IOException` |
| Effect on control flow | Stops normal execution at the throw point and searches for a matching handler | Does not create an exception and does not alter control flow by itself |
| Relation to checked exceptions | Throwing a checked exception must be caught or validly declared in the enclosing context | Allows a method to propagate checked exceptions to its caller |

Do not write `throws new IOException(...)` or `throw IOException` to throw a new instance: you must use `throw new IOException(...)`. Do not use `throws` in place of `catch` when the business requirement is to handle the error directly inside the method.

## 2. How Is an Exception Thrown?

When execution reaches `throw exceptionObject;`:

1. The expression is evaluated; the thrown object must belong to a subtype of `java.lang.Throwable`.
2. Normal control flow of the current code block stops; subsequent statements on that branch do not run.
3. Java searches for a compatible `catch` block in enclosing `try` statements. If none exists, the exception propagates up the call stack to the calling method.
4. Appropriate `finally` blocks and `try-with-resources` resource closing still execute according to language rules when exiting scopes.
5. If the exception goes unhandled all the way to the top of the thread, the thread's uncaught exception handler may print the stack trace; the program or corresponding thread terminates abnormally.

Example:

```java
if (balance < amount) {
    throw new IllegalStateException("insufficient balance");
}
```

This line **actually executes** if the `if` branch is true. It is not merely a note saying an error could happen. `IllegalStateException` is an unchecked exception; Java rules do not require putting `throws IllegalStateException` on the method signature.

The statement `throw null;` can compile in a valid context, but at runtime it causes a `NullPointerException`; it should not be used. Do not throw values that do not inherit from `Throwable`, such as a string `"error"` or number `123`.

## 3. Why Is `throws` Required for Checked Exceptions?

`throws` matters most when a method can let a **checked exception** escape: for example `IOException` or a custom exception that `extends Exception`. If it is not handled with `catch`, the method must declare an appropriate `throws`. For `RuntimeException`, `Error`, and their subclasses (**unchecked**), the compiler does not require `throws`.

| Example | Group | Obligation When the Exception Can Escape |
| --- | --- | --- |
| `IOException`, `InvalidScoreException extends Exception` | Checked | Catch or declare `throws` |
| `IllegalArgumentException`, `NumberFormatException` | Unchecked | Can be thrown without declaring |
| `StackOverflowError` | Unchecked Error | No need to declare; do not use as a business error |

This does not mean checked exceptions always occur or unchecked exceptions are always programmer bugs. The next lesson analyzes the `Throwable` hierarchy, concrete classes, and how to choose contracts. In this lesson, clearly distinguish **`throw` (throwing an object at runtime)** from **`throws` (listing exception types in a signature)**.


## 4. Complete Example: Throwing a Checked Exception Yourself and Declaring `throws`

This example parses a score from a string. If it is not an integer or is outside the range 0 to 100, the method will **`throw`** a custom-defined exception. Because `InvalidScoreException extends Exception`, the method must declare **`throws InvalidScoreException`**, and `main` uses `catch` to handle each input.

Create a file named **`ThrowThrowsDemo.java`**:

```java
public class ThrowThrowsDemo {
    static int parseScore(String text) throws InvalidScoreException {
        final int score;
        try {
            score = Integer.parseInt(text);
        } catch (NumberFormatException cause) {
            throw new InvalidScoreException("invalid integer: " + text, cause);
        }

        if (score < 0 || score > 100) {
            throw new InvalidScoreException("score out of range: " + score);
        }
        return score;
    }

    public static void main(String[] args) {
        String[] inputs = {"95", "150", "abc"};

        for (String input : inputs) {
            try {
                System.out.println(input + " => " + parseScore(input));
            } catch (InvalidScoreException ex) {
                System.out.println(input + " => " + ex.getMessage());
            }
        }
    }
}

class InvalidScoreException extends Exception {
    InvalidScoreException(String message) {
        super(message);
    }

    InvalidScoreException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Run from the directory containing the file (JDK 17+, PowerShell, CMD, bash). Create the `out` directory if it does not exist yet:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out ThrowThrowsDemo.java
java -cp out ThrowThrowsDemo
```

**Exact stdout of the program:**

```text
95 => 95
150 => score out of range: 150
abc => invalid integer: abc
```

Flow explanation:

- For `95`, `parseScore` returns `95` without throwing an exception.
- For `150`, the range check condition is true; `throw new InvalidScoreException(...)` transfers control to the `catch` in `main`. `return score;` does not execute for that call.
- For `abc`, `Integer.parseInt` throws `NumberFormatException` (unchecked); `catch` converts it into `InvalidScoreException` (checked) and passes the **original cause** via `super(message, cause)`.
- `throws InvalidScoreException` in the signature informs callers of their obligation to catch or declare the checked exception. The `throw` statements themselves are what make the exceptions happen.
- The `for` loop continues after each `catch`, so all three lines are printed.

`InvalidScoreException` is a non-`public` top-level class in the same file, which is valid because the file has only one `public` top-level type (`ThrowThrowsDemo`). If you make the exception `public class InvalidScoreException`, it must be placed in its own file `InvalidScoreException.java`.

## 5. Unchecked Exceptions: Using `throw` Without Needing `throws`

For API preconditions, `IllegalArgumentException` is often appropriate. Create **`UncheckedDemo.java`**:

```java
public class UncheckedDemo {
    static int percentage(int part, int total) {
        if (total <= 0) {
            throw new IllegalArgumentException("total must be positive");
        }
        if (part < 0 || part > total) {
            throw new IllegalArgumentException("part out of range");
        }
        return part * 100 / total;
    }

    public static void main(String[] args) {
        System.out.println("percent=" + percentage(3, 4));

        try {
            System.out.println(percentage(2, 0));
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

Compile and run:

```sh
javac -encoding UTF-8 --release 17 -d out UncheckedDemo.java
java -cp out UncheckedDemo
```

Output:

```text
percent=75
error=total must be positive
```

There is no `throws IllegalArgumentException` on `percentage`, yet the program is completely valid. The caller can catch this exception when a useful recovery strategy exists; catching it is not a compilation requirement. In production code, be mindful of percentage calculations with large integers because `part * 100` can overflow `int`; the example here uses small numbers to illustrate the exception mechanism.

## 6. Caller Catches or Declares to Propagate a Checked Exception

Suppose a method executes `throw new java.io.IOException(...)`. For a checked exception, there are two valid options in the caller:

**Option A — catch to handle locally:**

```java
try {
    readData();
} catch (java.io.IOException ex) {
    System.out.println("Read failed: " + ex.getMessage());
}
```

**Option B — declare `throws` to pass handling responsibility up to the next caller:**

```java
static void relay() throws java.io.IOException {
    readData();
}
```

The two snippets above only illustrate method bodies; to run standalone, `readData()` and an enclosing context must be defined. `throws` does not wrap the exception in a `try/catch`, so if no handler exists along the call chain, the exception continues propagating upward.

A **complete, runnable** example demonstrating propagation: create `PropagationDemo.java`:

```java
import java.io.IOException;

public class PropagationDemo {
    static String readData() throws IOException {
        throw new IOException("sample read failure");
    }

    static String relay() throws IOException {
        return readData();
    }

    public static void main(String[] args) {
        try {
            System.out.println(relay());
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

Run:

```sh
javac -encoding UTF-8 --release 17 -d out PropagationDemo.java
java -cp out PropagationDemo
```

Output:

```text
caught=sample read failure
```

The call chain is `main → relay → readData`. `readData` throws `IOException`; `relay` declares it to propagate it further; `main` catches it and prints the message. This is an intentionally created exception for demonstration, with no actual file I/O.

## 7. Common Compile-Time Errors When Using `throw`/`throws`

### 7.1. Throwing a Checked Exception Without Catching or Declaring It

The snippet below **deliberately fails to compile**:

```java
import java.io.IOException;

class InvalidChecked {
    static void load() {
        throw new IOException("cannot read");
    }
}
```

`javac` typically reports that `IOException` must be caught or declared to be thrown. You can fix the signature to:

```java
static void load() throws java.io.IOException {
    throw new java.io.IOException("cannot read");
}
```

This is an illustrative method; callers afterward still have to catch or declare the appropriate checked exception.

### 7.2. Caller Fails to Handle a Declared Exception

The snippet below is also **deliberately invalid**:

```java
static void caller() {
    relay(); // relay() declares throws IOException
}
```

If `relay()` is defined as in `PropagationDemo`, change it to `static void caller() throws IOException { relay(); }` (with `IOException` imported) or place the call inside `try/catch(IOException ex)`.

### 7.3. Declaring More Broadly Than Necessary

`throws Exception` can be valid, but it reduces clarity: callers do not know which error group to expect. Prefer specific exceptions such as `throws IOException` or `throws InvalidScoreException`. If multiple independent checked exceptions are needed, separate them with commas:

```java
void work() throws java.io.IOException, java.text.ParseException
```

This line only illustrates a **signature**; a complete method declaration needs a body `{ ... }` or a valid declaration inside an interface/abstract type.

### 7.4. Misunderstanding What `throws` Means

Declaring `throws IOException` **does not guarantee** that the method will throw `IOException` on every call. It only indicates that this exception is allowed to propagate through the signature. Conversely, reading a signature without seeing `throws RuntimeException` does not mean the code cannot encounter unchecked exceptions.

## 8. Preserving the Error Cause and Context

If you translate a low-level exception into an exception with business meaning, preserve the original cause:

```java
try {
    return Integer.parseInt(text);
} catch (NumberFormatException cause) {
    throw new InvalidScoreException("invalid integer: " + text, cause);
}
```

This snippet is taken from the `ThrowThrowsDemo` example; it depends on the defined `InvalidScoreException` class. Passing the cause to the constructor preserves `NumberFormatException` in `ex.getCause()`, aiding logging and debugging. Doing only `throw new InvalidScoreException("...")` without `cause` breaks the causal link. Writing `throw cause;` inside the `catch` block rethrows the exact caught object rather than converting it to a new checked exception type.

Do not hide errors with an empty `catch (Exception ex) { }` or return baseless default values. If a handler cannot properly handle the error, propagating an exception with an appropriate message and cause is usually better.

When throwing an exception after opening resources, use `try-with-resources` with types implementing `AutoCloseable` so resources are closed even when exceptions occur. Avoid `return`/`throw` from `finally` because it can obscure an earlier exception; in special cases, an exception thrown from `finally` can replace the exception that was propagating out.

## 9. Notes on Overridden Methods and Constructors

- An **overriding** method cannot add or broaden checked exceptions beyond what the overridden method's signature allows. For example, if a parent method declares no checked exceptions, the overriding method cannot add `throws IOException`. Unchecked exceptions are not restricted in the same way.
- Constructors can use `throws` to announce checked exceptions during initialization. Callers instantiating the object must catch or declare them.
- `main(String[] args)` can also declare `throws Exception`; this is convenient in small experiments, though an uncaught exception will terminate the program with a stack trace. Real applications generally need error handling at appropriate boundaries.

Example illustrating a constructor declaring a checked exception (not a standalone program):

```java
class ConnectionConfig {
    ConnectionConfig(String address) throws java.io.IOException {
        if (address == null || address.isBlank()) {
            throw new java.io.IOException("missing address");
        }
    }
}
```

When calling `new ConnectionConfig("")`, the exception originates from `throw`; `throws` on the constructor forces the caller to handle or propagate it.

## 10. Guidelines for Writing Clean Exception Code in Practice

1. **Detect invalid state in the right place:** use `throw new ...` with the appropriate exception type, message, and cause.
2. **Checked exceptions that may escape:** use `throws LoaiNgoaiLe` in the signature when not handling locally; let the caller decide the recovery policy.
3. **When handleable right at the call site:** use `try/catch` with meaningful action; test both success and failure branches.
4. **Do not use exceptions as normal control flow** for expected conditions that can be checked simply; validate inputs and use result-reporting APIs when the contract calls for them.
5. **Check thoroughly:** compile-time errors (`unreported exception`), exception propagation paths, messages, causes, and how resources are closed.

### Self-Check

- How do `throw` and `throws` differ? **`throw` throws an object at runtime; `throws` declares exception types in the signature.**
- What is required to throw `IOException` out of a method that has no `try/catch`? **Declare `throws IOException` (or an appropriate supertype) for valid compilation.**
- Is `throws` required when throwing `IllegalArgumentException`? **No**, because it is unchecked.
- Does merely adding `throws IOException` make the exception disappear? **No**. If it actually occurs, the exception propagates to callers until handled or left uncaught.
- Why preserve `cause` when throwing a different exception type? **To keep evidence of the original error** and help trace it.

**Remember:** `throw` is the act of signaling an error; `throws` is a contract stating which checked exceptions may exit according to the method contract. Using both accurately enables intentional error handling and preserves diagnostic information.