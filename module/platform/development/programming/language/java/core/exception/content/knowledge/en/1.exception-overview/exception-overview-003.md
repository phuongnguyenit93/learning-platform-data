# Why Use Exceptions Instead of Error Codes or Special Values in Java?

In a method call, we need to distinguish a **valid business result** from **the inability to perform the operation as promised**. If every failure is represented by a number such as `-1`, a string such as `"ERROR"`, or `null`, the caller may mistake an error signal for valid data. Exceptions give Java a **separate error-handling flow**: a method returns a value when it succeeds; when an issue occurs, it `throw`s an exception so that the responsible party at the appropriate layer can handle it.

Exceptions are not the right choice for *every* case where there is no result. The deciding factor is: **is it a normal outcome under the method's contract, or a failure condition that needs to be handled?**

## 1. Problems with Error Codes and Special Values

Suppose a method converts a string into an integer temperature. A temperature of `-1` is completely valid. If the method returns `-1` when the string cannot be converted, the two situations become indistinguishable:

- `parse("-1")` succeeds with the value `-1`.
- `parse("abc")` fails but also returns `-1`.

A special value (sentinel value) is only safe when it is **excluded by contract from the entire valid value domain**, and every caller knows to check for it. Other approaches also have limitations:

- `null`: can mean either "no data" or "an error occurred"; forgetting to check it can also cause a `NullPointerException` far away from the origin.
- `false`: suitable for simple yes/no questions, but cannot explain *why* an operation failed.
- Status codes `0`/`1`/`2`: force callers to check the code and store the result or error details elsewhere; if a check is forgotten, errors can be hidden.
- A value like `"ERROR"`: can collide with valid data, depends on string conventions, and is hard to check via the type system.

**Error codes are not always wrong.** An explicit result type containing both status and data (for example, a custom `Result<T, E>`), or status codes in the HTTP protocol, are still very useful. The problem mainly lies in **error codes or sentinels that lack semantics, are easily ignored, or collide with valid data**.

## 2. What Do Exceptions Solve?

### Separating the Success Flow from the Failure Flow

The signature `int parse(String text)` means that on success, an `int` will be obtained. If the content is invalid, the method can `throw NumberFormatException`; it does not need to "reserve" an `int` value as an error marker. Callers use `try`/`catch` when they have a way to recover or translate the error into an appropriate message.

### Preserving Diagnostic Information

An exception object has a **specific type**, a **message**, a **stack trace**, and optionally a **root cause** (`cause`). For example, you can distinguish `NumberFormatException` (the string is not a number), `IOException` (read/write failure), and `IllegalArgumentException` (an argument violates a condition).

When translating errors between layers, you can preserve the original cause: `throw new IllegalStateException("Không tải được cấu hình", cause);`. As a result, outer layers can display a concise message while diagnostic logs still retain the original error. A lone `-1` code carries no equivalent information.

### Propagating Errors to Where They Are Handled

If method A calls B, B calls C, and C cannot complete, an exception can propagate from C through B to A without B having to manually check and return an error code after every call. When `throw`n, **the remaining statements on the normal execution path are skipped** until a matching `catch` is found; `finally` blocks and resource closing via `try-with-resources` are still processed according to language rules.

This lets library layers focus on detecting errors, while the UI/API layer decides how to respond to the user. However, throwing an exception **does not automatically undo** every change made earlier; transaction rollbacks or compensating actions still require separate mechanisms.

### Enforcing Explicit Error Contracts in Certain Cases

Java distinguishes:

- **Checked exceptions** such as `IOException`: calls may force the programmer to handle them with `catch` or declare `throws`. This is a compiler-checked rule, not a guarantee that the error is handled properly.
- **Unchecked exceptions** such as `NumberFormatException` and `IllegalArgumentException` (subclasses of `RuntimeException`): not required to be declared or caught at compile time; suitable for many precondition violations or malformed input cases.
- **`Error`** such as `OutOfMemoryError`: generally indicates a serious environment/runtime failure; applications should not treat these as normal business exceptions to catch and continue from.

## 3. Java 17+ Example: Same `-1`, Two Meanings

Save the entire following example as **`ExceptionVsErrorCodeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.OptionalInt;

public class ExceptionVsErrorCodeDemo {
    // Legacy approach: -1 is both a valid temperature and an error signal.
    static int parseLegacy(String text) {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            return -1;
        }
    }

    // Exception approach: on success, always returns the parsed number.
    // If malformed, NumberFormatException propagates to the caller.
    static int parseStrict(String text) {
        return Integer.parseInt(text);
    }

    // Not finding a match is a normal case, so OptionalInt is used.
    static OptionalInt firstEvenAbove(int[] values, int threshold) {
        return Arrays.stream(values)
                .filter(value -> value > threshold && value % 2 == 0)
                .findFirst();
    }

    // I/O can fail: declare a checked exception.
    static String readConfiguration(Path file) throws IOException {
        return Files.readString(file);
    }

    public static void main(String[] args) {
        System.out.println("Cũ, hợp lệ -1: " + parseLegacy("-1"));
        System.out.println("Cũ, nhập sai: " + parseLegacy("abc"));

        System.out.println("Ngoại lệ, hợp lệ -1: " + parseStrict("-1"));
        try {
            parseStrict("abc");
        } catch (NumberFormatException ex) {
            System.out.println(
                    "Ngoại lệ, nhập sai: " + ex.getClass().getSimpleName());
        }

        OptionalInt found = firstEvenAbove(new int[] {1, 3, 4}, 4);
        System.out.println("Không thấy số chẵn > 4: " + found.isEmpty());
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac -encoding UTF-8 ExceptionVsErrorCodeDemo.java
java ExceptionVsErrorCodeDemo
```

Expected output:

```text
Cũ, hợp lệ -1: -1
Cũ, nhập sai: -1
Ngoại lệ, hợp lệ -1: -1
Ngoại lệ, nhập sai: NumberFormatException
Không thấy số chẵn > 4: true
```

**Analysis:**

1. Both "Cũ" lines return the same `-1`, so the caller cannot tell whether the operation succeeded or failed. This flaw cannot be fixed merely by checking `result == -1`, because `-1` is valid data.
2. With `parseStrict`, `-1` is preserved as data; the string `"abc"` produces `NumberFormatException` and enters the `catch` branch. We only print the exception type name so the output does not depend on stack trace details.
3. Finding an even number greater than 4 in an array is a search operation that **may yield no result**. `OptionalInt.empty()` represents this clearly without throwing an exception. `isEmpty()` returns `true`.
4. `readConfiguration` illustrates the **checked exception** contract of file reading. It is not called in `main`, so the example does not depend on whether a file exists. If a caller uses this method, the caller must handle or declare `IOException`.

## 4. Comparing API Design Options

| Representation | Use When | Considerations |
| --- | --- | --- |
| Normal value (`int`, `String`, object) | Success produces a valid result | Do not use a valid value as an error code |
| `boolean` or status enum | Yes/no outcomes are routine and provide enough information | Status meanings must be clearly specified |
| `Optional<T>` / `OptionalInt` | "Not found" is an expected outcome | Do not use to hide I/O or system errors; `Optional` itself carries no failure reason |
| Explicit result such as `Result<T, E>` | Expected failures have multiple types and callers need to handle them as data | Java 17 has no standard `Result<T, E>` type in the core library; you must define your own or use a suitable library |
| Specific exception | The operation contract cannot be fulfilled, a precondition is violated, or a failure must propagate to a handling layer | Choose the right type, document it, and handle it at the right boundary |
| External protocol/API error code | HTTP, C/native conventions, devices, legacy systems | Convert to explicit Java types at the integration layer when appropriate |

Guiding example: searching for products by filter can return an empty list; looking up a nonexistent record can return `Optional.empty()` if the contract allows absence; however, failing to read the database due to a lost connection is a **failure**, and should not be disguised as "record not found".

Similarly, malformed form data can be collected by a validation system as multiple field errors for the user to fix at once. An exception can still be used at the data conversion boundary, but you should not throw and catch exceptions for every routine validation branch when an explicit validation result is clearer.

## 5. Using Exceptions Responsibly

### Throw Where Detected, Handle Where Action Can Be Taken

A method should validate preconditions and throw the exception type that accurately represents the violation—for example, `IllegalArgumentException` for a negative argument in an operation requiring a positive number. Lower layers usually **do not know** how to display messages to the user; outer layers can translate exceptions into UI messages, HTTP responses, controlled retries, or operational alerts.

There is no need to `catch` at every level. Only catch when you can **recover, add context, intentionally translate, or terminate the operation safely**.

### Preserve the Root Cause When Translating Exception Types

The following snippet is an **illustrative method** that needs to be placed inside a Java class with imports `java.io.IOException`, `java.nio.file.Files`, and `java.nio.file.Path`; it is not a standalone program:

```java
static String loadRequiredConfig(Path file) {
    try {
        return Files.readString(file);
    } catch (IOException cause) {
        throw new IllegalStateException(
                "Không thể tải cấu hình bắt buộc: " + file, cause);
    }
}
```

If the contract of the class you are designing allows callers to recover from I/O errors themselves, keeping `throws IOException` may make more sense than converting to `IllegalStateException`. Only translate the type when the current layer has enough context to decide.

### Close Resources Even When an Exception Occurs

When working with streams/files/connections, prefer `try-with-resources` for objects implementing `AutoCloseable`:

```java
static String readFirstLine(Path file) throws IOException {
    try (var reader = Files.newBufferedReader(file)) {
        return reader.readLine();
    }
}
```

This is an illustrative method snippet requiring imports `java.io.IOException`, `java.nio.file.Files`, and `java.nio.file.Path`. The reader is closed upon exiting the block, even if reading throws an exception. A `null` return from `readLine()` on an empty file is a **result defined by the API contract**, distinct from an `IOException` caused by a read error. When both the primary operation and the close operation throw exceptions, Java can record the close exception as a **suppressed exception**.

### Document and Categorize Consistently

Clearly document possible exceptions with JavaDoc (`@throws`), using messages that include helpful context without putting passwords, tokens, or sensitive data into errors. If there are multiple business failure types that need distinct handling, you can create custom exception types; do not create a new exception class just to rename an existing one that already expresses the error accurately.

## 6. Common Mistakes

- **Swallowing errors:** `catch (Exception e) { return null; }` turns a failure into an ambiguous result and loses context. Only provide a fallback value when it is an explicitly defined policy and the fallback data is genuinely safe.
- **Catching too broadly:** catching `Exception` or `Throwable` in every method hides programming bugs and may even catch system errors. Prefer specific exception types; do not catch `Error` to handle it like a business error.
- **Using exceptions for routine control flow:** accessing elements until an out-of-bounds error ends a loop, or throwing an exception whenever a normal search finds nothing, makes code hard to read and can incur stack trace construction overhead.
- **Losing the cause:** `throw new RuntimeException("Lỗi")` after catching `IOException` without passing `cause` reduces traceability.
- **Logging at every layer and rethrowing:** a single error can generate multiple duplicate log entries. Designate which layer is responsible for logging, adding context, or responding.
- **Lumping everything into one generic type:** using only `RuntimeException` with generic messages for invalid input, lost connections, and state violations prevents callers from distinguishing how to handle them.
- **Assuming exceptions replace data validation:** validating business requirements is still necessary. An exception signals failure; it does not by itself define what valid data is, nor does it automatically roll back side effects that have already occurred.

Regarding performance, **throwing and creating exceptions is generally more expensive than a simple conditional branch**, especially when constructing a stack trace; however, you should not avoid exceptions with error codes in every case purely for performance. Choose based on the API contract and measure if the failure path executes at high frequency.

## 7. Quick Selection Rules by Scenario

1. **Valid, but no value?** Return `Optional`, an empty collection, or an explicit status if that is a normal outcome. Example: a search that finds nothing.
2. **Parameter violates the contract?** Consider `IllegalArgumentException` or a specific exception type. Example: a parameter must be positive, but a negative number is passed.
3. **Operation cannot proceed due to an external resource?** Use an exception type that expresses the failure, such as `IOException`, and let the responsible layer handle or recover.
4. **Multiple expected errors need to be returned together or accumulated?** Consider a structured result type, especially for input validation.
5. **Communicating over HTTP or a native API that uses status codes?** Follow the protocol contract at that boundary and convert appropriately to Java's error model internally.

**Key takeaway:** return values should describe **successful outcomes**; exceptions should express that **the operation could not be completed as contracted** and carry information for handling/diagnosis. Status codes and `Optional` remain the right choice when that situation is a normal, explicitly modeled part of the API.
