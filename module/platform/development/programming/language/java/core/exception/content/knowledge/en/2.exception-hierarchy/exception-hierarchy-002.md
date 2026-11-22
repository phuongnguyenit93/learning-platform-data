# Exception and RuntimeException in Java

Both `Exception` and `RuntimeException` belong to Java's exception system, but they differ in **compiler checking rules** and in how they are declared and handled when a method can fail. Understanding their inheritance relationship helps you read API signatures, place `try/catch` blocks in the right locations, and choose the appropriate exception type when designing Java code.

## 1. Position in the `Throwable` Hierarchy

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    └── java.lang.Exception
        ├── java.io.IOException
        ├── java.text.ParseException
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            ├── java.lang.IndexOutOfBoundsException
            └── java.lang.NullPointerException
~~~

- `Throwable` is the root type of Java objects that can be thrown with `throw` and caught with `catch`.
- `Exception` is a direct subclass of `Throwable`, representing abnormal conditions that an application may need to handle or propagate.
- `RuntimeException` **extends `Exception`**. Therefore, every `RuntimeException` is also an `Exception`, but not every `Exception` is a `RuntimeException`.
- `Error` is a separate branch of `Throwable`, not under `Exception`. Most applications do not actively recover from serious system errors such as `OutOfMemoryError`.

The diagram above shows only **a few representative classes**, not the entire hierarchy. The `RuntimeException` and `Error` branches belong to the *unchecked* group; the remaining `Exception` classes belong to the *checked* group.

## 2. The Most Important Difference: Checked vs. Unchecked

| Criterion | `Exception` not in the `RuntimeException` branch | `RuntimeException` and its subclasses |
| --- | --- | --- |
| Classification | Checked exception | Unchecked exception |
| Examples | `IOException`, `ParseException`, `Exception` directly | `IllegalArgumentException`, `NullPointerException`, `NumberFormatException` |
| What does the compiler require? | Must **catch** or **declare** exceptions that may occur | Not required to catch or declare |
| Can `throws` be declared? | Yes; usually required if not handled internally | Yes, but optional |
| Does it disappear automatically at runtime? | No; propagates if unhandled | No; also propagates if unhandled |
| Can it be caught by `catch (Exception e)`? | Yes | Yes, because it is a subclass of `Exception` |

In Java, the term *checked* refers to checking rules **at compile time**. It does not guarantee that the exception is lightweight or always recoverable. Conversely, *unchecked* does not mean the exception is ignored: if thrown without a matching catch block, the exception still exits the current call stack.

Important note: the `Exception` class itself is **checked** whenever that type appears in a checked position, such as `throw new Exception(...)` or a `throws Exception` signature. Only the `RuntimeException` branch (and its subclasses) is exempt from this rule.

## 3. Compilation and Propagation Mechanism

When code calls a method that can throw a checked exception, it must choose one of two options:

1. **Handle it here** with an appropriate `try/catch`.
2. **Pass responsibility to the caller** using `throws` in the method declaration.

For example, the following signature indicates that the caller must account for `IOException`:

~~~java
static String loadText(java.nio.file.Path path) throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

This is an **illustrative method declaration snippet**, not a standalone program. If you call `loadText(path)` inside a method that neither declares `throws IOException` nor catches the exception, the code will not compile. The `throws` clause **does not throw** an exception; it describes the checked exceptions that may exit the method. The `throw` statement is what directly throws an exception object.

For unchecked exceptions, the compiler does not require `catch` or `throws`:

~~~java
static void requireNonNegative(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("value phải >= 0");
    }
}
~~~

This is also an **illustrative method snippet**. `IllegalArgumentException` is still actually thrown when `value < 0`. It propagates up the call stack until it encounters a `catch` that accepts a matching type, or becomes an uncaught exception for the executing thread. Writing `throws IllegalArgumentException` is still valid if useful for API documentation, but it is not required.

When a method declares a **broad checked type**, such as `throws Exception`, callers must normally handle or declare that type, even if a specific implementation usually only throws an unchecked subclass. Compilation rules are based on the type contract visible to the calling code.

## 4. Standalone Runnable Java 17+ Example

The example below places checked and unchecked exceptions side by side, while also illustrating how to preserve the original cause when translating exceptions.

Create the file `ExceptionDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ExceptionDemo {
    public static void main(String[] args) {
        try {
            System.out.println("Dòng đầu: " + readFirstLine("Java\nException"));
        } catch (IOException e) {
            System.out.println("Không đọc được dòng đầu");
        }

        for (String input : new String[] {"20", "abc", "-1"}) {
            try {
                System.out.println("Tuổi hợp lệ: " + parseAge(input));
            } catch (IllegalArgumentException e) {
                System.out.println("Input '" + input + "': " + e.getMessage());
                if (e.getCause() != null) {
                    System.out.println(
                            "Nguyên nhân: " + e.getCause().getClass().getSimpleName());
                }
            }
        }
    }

    // readLine() has the signature throws IOException: a checked exception.
    static String readFirstLine(String text) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(text))) {
            return reader.readLine();
        }
    }

    // IllegalArgumentException is unchecked: "throws" is not required.
    static int parseAge(String input) {
        final int age;
        try {
            age = Integer.parseInt(input);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("phải là số nguyên", e);
        }

        if (age < 0) {
            throw new IllegalArgumentException("không được âm");
        }
        return age;
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac ExceptionDemo.java
java ExceptionDemo
~~~

Expected output:

~~~text
Dòng đầu: Java
Tuổi hợp lệ: 20
Input 'abc': phải là số nguyên
Nguyên nhân: NumberFormatException
Input '-1': không được âm
~~~

**Point-by-point explanation:**

- `BufferedReader.readLine()` declares `throws IOException`. The `readFirstLine` method chooses to **propagate** it using `throws IOException`; `main` chooses to **catch** `IOException`. The data resides in a `StringReader`, so the I/O error branch is not triggered in this run, yet the API contract must still be satisfied at compile time.
- `Integer.parseInt("abc")` throws `NumberFormatException`, a subclass of `IllegalArgumentException` and `RuntimeException`. Declaring `throws` is not needed for `parseAge`.
- When converting a number-parsing error into a business-meaningful parameter error, `new IllegalArgumentException("phải là số nguyên", e)` preserves the original exception in `getCause()`. This ensures diagnostics can still trace the root cause.
- The value `-1` is a syntactically valid integer, but invalid according to the method's rules; the program explicitly throws `IllegalArgumentException`. This case has no `cause` because it is not translated from a lower-level error.
- `catch (IllegalArgumentException e)` catches both `NumberFormatException` directly and `IllegalArgumentException` due to the inheritance relationship. The code does not swallow the exception silently: it displays handling results appropriate for the example.

The `try (resource) { ... }` syntax is **try-with-resources**: `BufferedReader` is closed automatically after leaving the block. It does not replace the obligation to handle checked exceptions if the resource's methods may declare exceptions.

## 5. Choosing Exception Types When Writing APIs

There is no absolute rule that every external error must be checked, or that every programming error must be unchecked. Determine the **method's contract** and the practical action the caller can take.

| Situation | Common choice | Reasoning |
| --- | --- | --- |
| Reading files, opening I/O streams that can fail | `IOException` (checked) | The caller can try another path, report the error, or propagate it |
| Argument violates method preconditions | `IllegalArgumentException` (unchecked) | The caller needs to fix the input value |
| Object state does not permit the operation | `IllegalStateException` (unchecked) | The sequence of operations or state needs to be corrected |
| Accessing a `null` object against expectations | `NullPointerException` (unchecked) | Usually a contract/logic issue; the root cause needs to be addressed |
| String cannot be converted to a number | `NumberFormatException` (unchecked) | Validate data, display a message, or translate into an appropriate domain error |

When **there is a concrete recovery action**, catch the exception at the layer that understands the error. When it cannot be resolved, let the exception propagate according to the API contract. For checked exceptions, propagate via `throws` or translate to an appropriate type and **preserve the cause** when needed. For unchecked exceptions, prioritize fixing the root cause or validating input data rather than wrapping every statement in `try/catch`.

A checked exception should only be declared as broadly as necessary: `throws IOException` tells the caller much more than `throws Exception`. Conversely, if an API chooses a checked exception, implementations and callers must adhere to that contract; you should not arbitrarily convert everything to `RuntimeException` just to eliminate `throws` declarations.

## 6. Exception-Catching Rules Related to Inheritance

### Catch from Specific to General Types

~~~java
try {
    // Call an operation that may throw IOException or RuntimeException.
} catch (java.io.IOException e) {
    // Handle I/O error.
} catch (RuntimeException e) {
    // Handle unchecked error appropriate at this layer.
} catch (Exception e) {
    // Remaining Exceptions, if any.
}
~~~

This is an **illustrative structure**, not a standalone program. When applied to real code, `catch` blocks for checked exceptions must match the exceptions that the `try` block can actually throw. Every subsequent catch branch must still be able to accept a type different from the preceding branches.

Because `RuntimeException extends Exception`, placing `catch (Exception e)` **before** `catch (RuntimeException e)` makes the latter branch unreachable and causes a compilation error. `catch (Exception e)` catches both checked and unchecked exceptions under the `Exception` branch, but does **not** catch `Error`.

You can use multi-catch with types that have no inheritance relationship, such as `catch (IOException | IllegalArgumentException e)`, provided the checked types are appropriately declared within the `try` block. You cannot write `catch (Exception | RuntimeException e)` because the two types have a parent–child relationship.

### Catch or Propagate?

- **Catch** if the code knows how to handle it: translate the message into user-facing context, use a defined fallback, or abort an operation at the right layer.
- **Propagate** if the current layer lacks the information to recover. For checked exceptions, declare `throws` with the exact type; for unchecked exceptions, they can propagate on their own.
- **Translate the exception type** when needed to reflect a higher-layer contract; pass the old exception as the `cause` to preserve traceability.

Do not catch `Exception` or `Throwable` everywhere just to keep the program running: doing so can mask logic bugs, lose failure states, or accidentally intercept handling meant for a higher layer. Certain boundaries such as task dispatchers or request-entry layers may intentionally have general handling, but they require a clear error policy.

## 7. Common Misconceptions

**“`RuntimeException` does not belong to `Exception`.”** False. It directly extends `Exception`; therefore `catch (Exception e)` can catch `RuntimeException`.

**“`Exception` is always checked.”** To be precise: `Exception` itself and its subclasses **not in the `RuntimeException` branch** are checked. Exceptions under `RuntimeException` are unchecked even though they still have an `is-a Exception` relationship.

**“Unchecked exceptions will not crash the program.”** False. Having no compile-time requirement does not mean the exception is automatically handled. If uncaught, it can terminate the running thread and be reported by the runtime or framework depending on the context.

**“Every checked exception is recoverable, and every runtime exception is a programming bug.”** Not necessarily. `IOException` can encounter issues that cannot be resolved on the spot; `NumberFormatException` can also be invalid user input for which the application intentionally reports a friendly error.

**“Writing `throws` means the exception has been handled.”** False. `throws` declares the possibility of propagation; `try/catch` is what creates a handling point. `throw` is the statement that raises a specific exception.

**“Catching `Exception` catches every `Throwable`.”** False. `Error` belongs to a parallel branch. You should not catch all `Throwable` without a specific reason and policy.

**“Converting to `RuntimeException` is enough; no need to keep the original exception.”** Bad for diagnostics. When wrapping a lower-level error, prefer a constructor that accepts `cause`, such as `new IllegalStateException("Không nạp được cấu hình", e)`.

## 8. Self-Check Questions

1. Why must `IOException` usually be caught or declared, while `NumberFormatException` does not? Point out the inheritance branch that determines this rule.
2. If a method declares `throws Exception`, can the caller omit both `catch` and `throws` because the method currently only throws `IllegalArgumentException`?
3. Does `catch (Exception e)` catch `NullPointerException` and `OutOfMemoryError`? Explain using the class hierarchy.
4. In the `parseAge` example, why should `NumberFormatException` be passed into the constructor of `IllegalArgumentException`?
5. When a file-reading method cannot recover on the spot, would you catch and ignore the error or declare `throws IOException` for the caller?

**Short answers:** (1) `IOException` is checked, while `NumberFormatException` lies under `RuntimeException`; (2) no, the `throws Exception` contract is still checked; (3) it catches `NullPointerException`, not `OutOfMemoryError`; (4) to preserve the cause for diagnostics; (5) propagate `IOException` if the caller has the proper context to decide.

**Key takeaway:** The core distinction is *checked versus unchecked* at compile time. `RuntimeException` is still an `Exception`, and both types can propagate at runtime; choose where to handle them based on recoverability and the API contract.