# Identifying Checked Exceptions and Unchecked Exceptions — Java 17+

## 1. Two Exception Groups Differ in Compiler Rules

In Java, an **exception** represents an abnormal condition during execution: invalid data, unavailable resources, a state that does not allow an operation, and so on. Java divides throwable types into **checked** and **unchecked** based on the **class hierarchy**, rather than on "severity" or message content.

- **Checked exception:** when a statement can produce a checked type, the calling code must **catch** or **declare (`throws`)** the exception according to compiler rules.
- **Unchecked exception:** the compiler **does not require** the caller to catch or declare `throws`; however, the exception can still be thrown at runtime, produces a stack trace, and can be caught when appropriate.

~~~java
// IOException is checked: must be handled or declared.
static String load(String key) throws java.io.IOException {
    if (key.isBlank()) {
        throw new java.io.IOException("empty key");
    }
    return key;
}

// IllegalArgumentException is unchecked.
static int requirePositive(int n) {
    if (n <= 0) {
        throw new IllegalArgumentException("n must be positive");
    }
    return n;
}
~~~

**Note:** `throws` does not make a method throw an exception automatically. It **declares the possibility of an exception escaping** the method; `throw` is what actually throws a specific exception object.

## 2. Identifying from the Inheritance Tree

In Java 17, types that can be thrown with `throw` must belong to `Throwable` (or a subclass).

~~~text
java.lang.Throwable
├── java.lang.Error                  [unchecked]
│   ├── VirtualMachineError         [unchecked]
│   │   ├── StackOverflowError      [unchecked]
│   │   └── OutOfMemoryError        [unchecked]
│   └── AssertionError              [unchecked]
└── java.lang.Exception
    ├── IOException                 [checked]
    ├── SQLException                [checked]
    ├── InterruptedException        [checked]
    ├── ClassNotFoundException      [checked]
    └── RuntimeException            [unchecked]
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        ├── NullPointerException
        ├── ArithmeticException
        └── IndexOutOfBoundsException
            └── ArrayIndexOutOfBoundsException
~~~

Classification rules by base class:

| Inherits From | Group | Compiler Obligation |
|---|---|---|
| `Exception` but **not** under `RuntimeException` | **Checked exception** | Must catch or declare (`throws`) if the exception can escape |
| `RuntimeException` and all subclasses | **Unchecked exception** | Catch/declare not required |
| `Error` and all subclasses | **Unchecked exception classes** | Catch/declare not required, though generally should not be treated as recoverable business errors |
| `Throwable` directly or subclasses outside `Error`/`RuntimeException` branches | **Checked** per Java rules | Catch or declare if it can escape |

**Important distinction:** the phrase "unchecked exception classes" in the Java specification includes the `Error` branch as well. In everyday discussion, developers often refer to the `RuntimeException` branch as "unchecked exceptions" and talk about "Errors" separately. `Error` is **not** a subclass of `RuntimeException`.

A custom class extending `Exception` (not via `RuntimeException`) is checked; extending `RuntimeException` is unchecked.

## 3. Common Identification Examples

| Exception Type | Group | Typical Situation |
|---|---|---|
| `java.io.IOException` | Checked | Reading/writing I/O data fails |
| `java.sql.SQLException` | Checked | A JDBC operation encounters an error |
| `java.lang.ClassNotFoundException` | Checked | Loading a class by name cannot find the class |
| `java.lang.InterruptedException` | Checked | Thread is interrupted while waiting/sleeping |
| `java.text.ParseException` | Checked | A string-parsing API declares a parse error |
| `java.lang.NumberFormatException` | Unchecked | String cannot be parsed into a number via `Integer.parseInt` |
| `java.lang.NullPointerException` | Unchecked | Using a `null` reference in an operation requiring an object |
| `java.lang.IllegalArgumentException` | Unchecked | Argument violates an API rule |
| `java.lang.IllegalStateException` | Unchecked | Object state does not permit the behavior |
| `java.lang.ArrayIndexOutOfBoundsException` | Unchecked | Accessing an index outside array bounds |
| `java.lang.StackOverflowError` | Unchecked (Error) | Stack space exhausted by nested calls |

Having a class name ending in `Exception` **does not guarantee checked**: `NumberFormatException` is still unchecked. Conversely, errors such as `OutOfMemoryError` are not business exceptions even though they do not require `throws`.

Not every "data parsing" operation throws a checked exception: `Integer.parseInt("abc")` throws **unchecked `NumberFormatException`**. Always check the **exact API signature and exception class** rather than guessing from context.

## 4. Checked: Catch or Declare (`throws`)

Suppose `Files.readString(Path.of("settings.txt"))` can throw `IOException` (checked). The following method is **deliberately invalid code to illustrate a compile-time error**:

~~~java
// DOES NOT COMPILE as written:
static String readWrong() {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("settings.txt"));
}
~~~

Because checked `IOException` can escape, the compiler requires handling. There are two main approaches:

**A. Declare propagation:**

~~~java
static String readFile() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("settings.txt"));
}
~~~

Callers of `readFile()` must continue to **catch or declare**, up to an appropriate handling boundary. `throws IOException` **does not read the file for you**, does not catch anything on its own, and does not guarantee the operation will fail at runtime.

**B. Catch the exception where it should be handled:**

~~~java
static String readOrDefault() {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of("settings.txt"));
    } catch (java.io.IOException ex) {
        return "DEFAULT";
    }
}
~~~

When the file does not exist or cannot be read, the catch branch returns a fallback value. The snippet above illustrates an API **interacting with the filesystem**, not the deterministic stdout example in section 9. In the complete program, we throw an exception explicitly so results are identical across machines.

**Do not return `DEFAULT` unconditionally in every application**: if no valid default exists, add context and propagate the error or handle it appropriately. Do not swallow errors to hide business failures.

## 5. Unchecked: Compiler Does Not Enforce Catch/Declare

~~~java
static int parseAge(String text) {
    int age = Integer.parseInt(text); // Can throw NumberFormatException.
    if (age < 0) {
        throw new IllegalArgumentException("age cannot be negative");
    }
    return age;
}
~~~

This method **does not need** `throws NumberFormatException` or `throws IllegalArgumentException`. However:

- `parseAge("20")` returns `20`.
- `parseAge("abc")` throws `NumberFormatException`.
- `parseAge("-2")` throws `IllegalArgumentException` due to rule validation.

Callers can still catch unchecked exceptions if an error is an expected outcome from untrusted data:

~~~java
try {
    int age = parseAge("abc");
    System.out.println(age);
} catch (NumberFormatException ex) {
    System.out.println("invalid number");
}
~~~

**Exact stdout:**

~~~text
invalid number
~~~

**Unchecked does not mean "safe to ignore."** An uncaught unchecked error can also terminate the running thread and be reported by the default handler with a stack trace.

A method **is allowed to declare** `throws IllegalArgumentException` to document its contract, though this is not required by the compiler. For bugs like `NullPointerException`, you should usually fix the root cause rather than just adding a generic catch.

## 6. Distinguishing `throw`, `throws`, `try`, and `catch`

| Syntax | Role | Example |
|---|---|---|
| `throw` | Throws a specific `Throwable` object | `throw new IOException("failed");` |
| `throws` | Declares exceptions that may exit a method/constructor | `void load() throws IOException` |
| `try` | Marks an execution block that may raise errors | `try { load(); }` |
| `catch` | Handles exception types matching the branch | `catch (IOException ex) { ... }` |
| `finally` | Cleanup block that normally runs when leaving try/catch | `finally { ... }` |

Note that Java code must have imports or use fully qualified names for `IOException`. A self-contained syntax example:

~~~java
import java.io.IOException;

class Reader {
    static void run() throws IOException {
        throw new IOException("failed");
    }
}
~~~

For checked exceptions, the compiler checks **catch-or-declare** along control-flow paths that can escape. It does not require every method in a project to have `throws`, nor does it force catching all unchecked branches.

In `main`, you can also write `public static void main(String[] args) throws IOException` to forward errors. This compiles, but does not by itself provide a recovery policy or user-friendly messaging.

## 7. `catch` Must Respect Inheritance Relationships and Order

`NumberFormatException` is a subclass of `IllegalArgumentException`. When catching multiple related types, put the **specific type first** and the **general type later**:

~~~java
try {
    Integer.parseInt("bad");
} catch (NumberFormatException ex) {
    System.out.println("invalid digits");
} catch (IllegalArgumentException ex) {
    System.out.println("other illegal argument");
}
~~~

**Exact stdout:**

~~~text
invalid digits
~~~

Swapping the two catch blocks would make the `NumberFormatException` branch **unreachable**, because `IllegalArgumentException` already catches all of its subclasses. The compiler reports an error.

`catch (Exception ex)` can catch checked and unchecked exceptions under the `Exception` branch, but **does not catch `Error`**. `catch (Throwable ex)` catches even more broadly and is usually unsuitable for ordinary business handling. Only use broad catches at boundaries with a clear policy (logging, translation, ensuring cleanup), without hiding hard-to-recover system errors.

Sometimes Java reports "exception is never thrown in body of corresponding try statement" when catching a checked exception that cannot arise from the `try` body according to compiler analysis. Do not add "just-in-case" checked catches everywhere when no API throws that type.

## 8. Checked Does Not Mean Always Recoverable

An exception is classified by **class type**, not by how easy it is to handle.

- **Checked `IOException`:** can be caused by a missing file, insufficient permissions, or I/O failure. You can retry, fall back, or propagate depending on the situation.
- **Unchecked `IllegalArgumentException`:** can be caught at an input boundary to inform the user of an invalid value.
- **Unchecked `NullPointerException`:** often indicates a logic/contract bug in code; effective handling may mean preventing null early.
- **`Error`:** in many cases indicates a VM/resource issue (such as `StackOverflowError` and `OutOfMemoryError`), so `catch (Error)` should not be treated as a default solution.

When designing APIs:

- Choose **checked** for conditions the caller is required to handle or explicitly decide to propagate.
- Choose **unchecked** for contract violations, programming mistakes, or scenarios the API designs as runtime exceptions.
- Not all libraries make the same choices; always read **method signatures, Javadocs, and contract documentation**.

A method declaring `throws IOException` is not guaranteed **to throw** an exception on every call; it only states that it **can escape** per the contract, and the compiler enforces checking.

## 9. Standalone Runnable Java 17+ Example

Create a file named exactly **`CheckedUncheckedDemo.java`**:

~~~java
import java.io.IOException;

public final class CheckedUncheckedDemo {
    private CheckedUncheckedDemo() {}

    static String loadFromSource(String key) throws IOException {
        if (key == null || key.isBlank()) {
            throw new IOException("missing configuration key");
        }
        return "value-" + key.strip();
    }

    // Declare propagation of checked IOException.
    static String prepare(String key) throws IOException {
        return loadFromSource(key) + "!";
    }

    // Catch checked exception at a boundary with an appropriate fallback.
    static String loadOrDefault(String key) {
        try {
            return prepare(key);
        } catch (IOException ex) {
            return "DEFAULT";
        }
    }

    // Unchecked: throws declaration not required.
    static int parseAge(String raw) {
        int age = Integer.parseInt(raw);
        if (age < 0) {
            throw new IllegalArgumentException("age cannot be negative");
        }
        return age;
    }

    static void assertReady(boolean ready) {
        if (!ready) {
            throw new IllegalStateException("service not ready");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("checked success=" + prepare(" config "));
        } catch (IOException ex) {
            System.out.println("checked unexpected failure");
        }

        System.out.println("checked fallback=" + loadOrDefault(""));

        try {
            prepare("");
        } catch (IOException ex) {
            System.out.println("checked caught="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        System.out.println("unchecked success=" + parseAge("20"));
        try {
            parseAge("abc");
        } catch (NumberFormatException ex) {
            System.out.println("unchecked parse="
                    + ex.getClass().getSimpleName());
        }

        try {
            parseAge("-2");
        } catch (IllegalArgumentException ex) {
            System.out.println("unchecked validation="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        try {
            assertReady(false);
        } catch (IllegalStateException ex) {
            System.out.println("unchecked state="
                    + ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }

        System.out.println("checked parent="
                + IOException.class.getSuperclass().getSimpleName());
        System.out.println("unchecked parent="
                + IllegalStateException.class.getSuperclass().getSimpleName());
        System.out.println("program continues=true");
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 CheckedUncheckedDemo.java
java -cp . CheckedUncheckedDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\CheckedUncheckedDemo.java
java -cp . CheckedUncheckedDemo
~~~

The example **does not access the filesystem**, network, or database; checked `IOException` is thrown directly in a controlled way. No Maven/Gradle, external libraries, or preview features are required.

### Exact expected stdout

~~~text
checked success=value-config!
checked fallback=DEFAULT
checked caught=IOException:missing configuration key
unchecked success=20
unchecked parse=NumberFormatException
unchecked validation=IllegalArgumentException:age cannot be negative
unchecked state=IllegalStateException:service not ready
checked parent=Exception
unchecked parent=RuntimeException
program continues=true
~~~

**Reading the output:**

1. With a valid key, `prepare(...)` returns a normal string even though the method **declares** `throws IOException`.
2. With an empty key, `loadFromSource(...)` throws checked `IOException`; `loadOrDefault(...)` catches it to return `DEFAULT`. Another call catches the error and prints type + message.
3. `parseAge("abc")` produces unchecked `NumberFormatException`; `parseAge("-2")` throws unchecked `IllegalArgumentException`. Both can still be caught normally.
4. `assertReady(false)` throws unchecked `IllegalStateException`.
5. The two `parent` lines show that `IOException` directly inherits from `Exception` and `IllegalStateException` directly inherits from `RuntimeException`.
6. Because the exceptions are handled intentionally, the program reaches `program continues=true`.

## 10. Defining Custom Checked and Unchecked Exceptions

A custom class is classified via its **superclass**, with no JVM registration required.

~~~java
// Standalone illustration within the same package scope:
class MissingRecordException extends Exception {
    MissingRecordException(String message) {
        super(message);
    }
}

class InvalidRecordStateException extends RuntimeException {
    InvalidRecordStateException(String message) {
        super(message);
    }
}
~~~

- `MissingRecordException extends Exception` → checked. Methods that can throw this type must follow catch/declare rules.
- `InvalidRecordStateException extends RuntimeException` → unchecked. The compiler does not force callers to catch/declare it.
- Both are still `Throwable`; both can carry a message/cause, print a stack trace, and be caught accordingly.

When wrapping an error to preserve the original cause, you can call a constructor like `new IOException("cannot load config", cause)`. Do not drop `cause` when translating exceptions if the system needs to diagnose the root source of failures.

## 11. `try-with-resources` Does Not Change Checked Exception Rules

Many I/O APIs require closing resources, for example:

~~~java
static String firstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

This is **illustrative method code**, not run in the environment-independent demo in section 9.

`try-with-resources` guarantees that the managed resource is closed when leaving the block, even on error, but reading or closing **can still throw checked `IOException`**. Therefore, the example declares `throws IOException` instead of assuming try-with-resources has "handled all errors."

When dealing with `InterruptedException` from `Thread.sleep(...)`, do not swallow the interruption signal. Depending on the contract, you can propagate `throws InterruptedException` or, when catching to restore state, restore the interrupt flag via `Thread.currentThread().interrupt()` as required by design.

## 12. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| A name ending in `Exception` must be checked | `RuntimeException` and its subclasses such as `NumberFormatException` are unchecked |
| Unchecked means never thrown at runtime | It can still be thrown and terminate a thread if unhandled |
| Checked means an error always occurs at runtime | The compiler requires handling/declaring the possibility; valid execution paths may not throw |
| `throws` throws an exception by itself | `throws` only declares; `throw` throws |
| Catching unchecked exceptions is invalid | You can catch them when appropriate; the compiler simply does not force you to |
| Seeing `Error` and thinking it is checked because it is not `RuntimeException` | `Error` subclasses are also unchecked under Java's classification |
| `catch (Exception)` also catches `OutOfMemoryError` | `Error` does not inherit from `Exception` |
| Adding `catch (IOException)` around every statement just in case | The compiler may reject catching a checked exception that cannot arise |
| Catching `IllegalArgumentException` followed by `NumberFormatException` | The later subclass branch is unreachable; reverse the order |
| `throws Exception` is always good design | Too broad, obscuring the specific exception contract; use appropriate types |
| Catching and leaving empty so the app won't crash | Can mask bugs; handle, log, or propagate intentionally |
| `finally` turns an exception into success | Cleanup is not the same as handling the cause |

## 13. Exercises with Answers

**A.** Classify `IOException`, `SQLException`, `IllegalStateException`, `NumberFormatException`, and `StackOverflowError`.

**Answer:** `IOException` and `SQLException` are **checked**; `IllegalStateException` and `NumberFormatException` are **unchecked RuntimeException**; `StackOverflowError` is an **unchecked Error**.

**B.** Why does calling `Files.readString(Path.of("a.txt"))` inside a method without catch or throws produce a compiler error?

**Answer:** because the API can throw checked `IOException`. The caller must catch it or add `throws IOException` (or a valid checked supertype) to the declaration.

**C.** When calling `Integer.parseInt("bad")`, do you need to declare `throws NumberFormatException`?

**Answer:** **No**, `NumberFormatException` sits under `RuntimeException`. The caller can catch it if invalid input is an expected scenario.

**D.** Is `class MyFailure extends Exception` checked or unchecked? What if it `extends RuntimeException`?

**Answer:** Directly `extends Exception` is **checked**, whereas `extends RuntimeException` is **unchecked**.

**E.** Why must `NumberFormatException` be caught before `IllegalArgumentException` if both have separate catch blocks?

**Answer:** because `NumberFormatException` is a subclass; catching the superclass first makes the subsequent subclass catch **unreachable**.

**F.** Does `catch (Exception ex)` catch `StackOverflowError`?

**Answer:** **No**, `StackOverflowError` inherits from `Error`, not `Exception`.

**G.** When a method declares `throws IOException` but receives valid data and encounters no errors, must it throw `IOException`?

**Answer:** **No**. `throws` only declares a possibility; for example, `prepare(" config ")` returns `value-config!`.

## 14. Checklist and Conclusion

- [ ] Identify checked vs. unchecked via the **`Throwable` hierarchy**, not by name or severity.
- [ ] Know that `Exception` (not under `RuntimeException`) is generally checked.
- [ ] Know that both the `RuntimeException` branch and the `Error` branch are unchecked by compiler rules.
- [ ] Read `throws IOException` in method signatures.
- [ ] Distinguish declaring `throws` from throwing with `throw`.
- [ ] Know the two ways to handle checked exceptions: `try-catch` or continuing to declare `throws`.
- [ ] Understand that unchecked exceptions can still be caught, though the compiler does not require catching them.
- [ ] Order `catch` blocks with specific types before general types.
- [ ] Do not confuse `catch (Exception)` with catching all `Throwable` types.
- [ ] Preserve cause/stack trace when propagating or wrapping errors that need diagnosis.
- [ ] Do not use try-with-resources as a reason to ignore checked I/O exceptions.
- [ ] Compile and run `CheckedUncheckedDemo.java` on JDK 17+ and verify exact stdout.

**Conclusion:** **Checked exceptions** require callers to **catch or declare** the potential exception per Java's compiler rules. **Unchecked** types belong to the `RuntimeException` or `Error` branches and carry no such compile-time obligation, yet still require sensible error-handling design. Inspect **inheritance types**, **API signatures**, and **application contracts** before deciding whether to catch, declare `throws`, or fix logic.