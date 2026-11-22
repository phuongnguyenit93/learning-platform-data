# Unchecked Exceptions in Java: `RuntimeException`, `Error`, and Their Subclasses

Java divides throwable objects (`Throwable`) into two groups according to **the compiler's exception-checking rules**: *checked exceptions* and *unchecked exceptions*. **Unchecked exceptions** consist of `RuntimeException`, `Error`, and all subclasses of these two types. When calling a method that may throw an unchecked exception, the Java compiler **does not require** the caller to write `try/catch` or declare `throws` for that exception.

The term "unchecked" refers only to **the obligation to declare or catch an exception at compile time**. It does **not** mean that the JVM ignores the exception, that the program will definitely continue running, that the exception is not serious, or that Java cannot detect certain issues early. When an unchecked exception is actually thrown, it still uses the full `Throwable` mechanism: interrupting the normal execution path, propagating up the call stack, being matched against an appropriate `catch`, and carrying a message, cause, and stack trace.

The most important takeaway of this lesson: both are unchecked, yet **`RuntimeException` is typically tied to application operations or state**, whereas **`Error` typically represents a serious problem in the runtime environment, class linkage, or internal invariants**. How they are handled usually differs and cannot be decided solely from the word "unchecked".

## 1. Where Does Unchecked Sit in the Hierarchy?

A simplified diagram, not listing the entire Java API:

```text
java.lang.Throwable
├── java.lang.Error                              ← unchecked
│   ├── VirtualMachineError
│   │   ├── OutOfMemoryError
│   │   └── StackOverflowError
│   ├── LinkageError
│   │   ├── NoClassDefFoundError
│   │   └── ExceptionInInitializerError
│   └── AssertionError
└── java.lang.Exception                          ← checked (this type itself)
    ├── IOException                              ← checked
    ├── ReflectiveOperationException             ← checked
    └── RuntimeException                         ← unchecked
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        ├── NullPointerException
        ├── IndexOutOfBoundsException
        │   ├── ArrayIndexOutOfBoundsException
        │   └── StringIndexOutOfBoundsException
        ├── ArithmeticException
        ├── ClassCastException
        └── UnsupportedOperationException
```

The example names in the diagram are real Java classes. A subclass of `RuntimeException` still belongs to the `Exception` branch, but **is no longer a checked exception**. Similarly, every subclass of `Error` belongs to the unchecked group.

According to the rules of the Java language, checked exceptions are subclasses of `Throwable` that **do not** belong to the `RuntimeException` branch or the `Error` branch. Therefore, `Exception` is a checked type, while `RuntimeException` is unchecked. Saying "every `Exception` is checked" is incorrect.

| Branch | Checked or unchecked? | What the compiler requires at the call site | Typical response |
| --- | --- | --- | --- |
| `IOException` | Checked | Catch or declare if the method may throw it | Decide to recover, use a fallback, or propagate the error |
| `RuntimeException` and its subclasses | Unchecked | Not required to catch/declare | Validate preconditions, state, and data; catch selectively at the appropriate layer |
| `Error` and its subclasses | Unchecked | Not required to catch/declare | Prioritize investigating/fixing the environment or program; usually not handled as a business branch |
| `Exception` | Checked | Catch or declare if an expression may throw this type | Do not equate it with `RuntimeException` alone |

**Terminology distinction:** a "compile error" is `javac` rejecting source code; a "runtime error" is a problem at runtime; whereas the Java class `Error` is **a specific branch of `Throwable`**. Not every runtime error is an `Error` object. A `NullPointerException`, for example, is a `RuntimeException`.

## 2. Why Is `RuntimeException` Not Mandatorily Checked at Compile Time?

Many errors detected at runtime depend on values or state that the compiler cannot know from a call site: whether an argument is `null`, whether an array index is within bounds, whether input data can be parsed into a number, or whether an object is in a permitted state.

For example, the call `Integer.parseInt(text)` is type-valid because the argument is a `String`. Java cannot guarantee that every actual value of `text` represents a valid integer. The API may throw `NumberFormatException` (a subclass of `IllegalArgumentException`, and thus `RuntimeException`), yet every call site of `parseInt` is not forced to have a `catch`.

Similarly, Java methods can very frequently encounter errors such as `NullPointerException`; if all of them had to declare or catch checked exceptions, method signatures and call flows would become overly cumbersome without making the code proportionally safer.

**Not being mandatorily checked is different from not being checkable by tools.** Compilers, IDEs, static analysis, tests, and `null`-checking tools can detect part of the risk before running; it is just that Java's `catch-or-declare` rule does not apply to these types.

Nor should "unchecked" be understood as synonymous with a bug: some APIs intentionally use `IllegalArgumentException` to signal that the caller violated a contract; some exceptions may come from external data. However, if the same situation is a common business branch, an explicit result type may be easier to use than throwing an exception.

## 3. Example: Accurately Checking Which Branch Is Unchecked

Save the following code as `ExceptionHierarchyDemo.java`. The program uses Java's type-inheritance relationship to check which types belong to the `RuntimeException` or `Error` branch.

```java
import java.io.IOException;

public class ExceptionHierarchyDemo {
    static void inspect(Class<? extends Throwable> type) {
        boolean runtime = RuntimeException.class.isAssignableFrom(type);
        boolean error = Error.class.isAssignableFrom(type);
        boolean unchecked = runtime || error;

        System.out.println(type.getSimpleName()
                + " | unchecked=" + unchecked
                + " | runtime=" + runtime
                + " | error=" + error);
    }

    public static void main(String[] args) {
        inspect(IOException.class);
        inspect(Exception.class);
        inspect(NumberFormatException.class);
        inspect(NullPointerException.class);
        inspect(OutOfMemoryError.class);
        inspect(AssertionError.class);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac --release 17 ExceptionHierarchyDemo.java
java ExceptionHierarchyDemo
```

**Exact stdout:**

```text
IOException | unchecked=false | runtime=false | error=false
Exception | unchecked=false | runtime=false | error=false
NumberFormatException | unchecked=true | runtime=true | error=false
NullPointerException | unchecked=true | runtime=true | error=false
OutOfMemoryError | unchecked=true | runtime=false | error=true
AssertionError | unchecked=true | runtime=false | error=true
```

`Class.isAssignableFrom` returns `true` when the `Class` object on the left represents a supertype or the exact same type as the `Class` object passed in. Therefore, `RuntimeException.class.isAssignableFrom(NumberFormatException.class)` is `true`; this relationship is determined by the inheritance hierarchy, independent of class names or message contents.

The example does not create or throw `OutOfMemoryError`: it only **inspects type relationships**, which is safe and predictable.

## 4. Common `RuntimeException` Types

`RuntimeException` represents many situations that occur while an application or library is running. Java and the standard library provide a range of specific subclasses to communicate the nature of the problem:

| Type | Typical situation | Handling approach |
| --- | --- | --- |
| `NullPointerException` | Dereferencing a `null` reference, invalid method call/field access | Fix the cause of `null`, clarify input and state contracts |
| `IllegalArgumentException` | Caller passes an argument violating the contract | Check preconditions and the API contract |
| `NumberFormatException` | `Integer.parseInt("abc")` cannot convert to an integer | Validate text data, report an appropriate input error |
| `IllegalStateException` | Operation requested when the object is in a disallowed state | Review state flow, timing, and call sequence |
| `IndexOutOfBoundsException` | Accessing an out-of-range index of a string/list | Check bounds and data size |
| `ArrayIndexOutOfBoundsException` | Accessing a non-existent position in an array | Use the boundary `0 <= i < array.length` |
| `ArithmeticException` | For example `int x = 10 / 0;` in integer arithmetic | Check the divisor, handle input conditions |
| `ClassCastException` | Casting a reference to an incompatible type at runtime | Design types properly and check types when needed |
| `UnsupportedOperationException` | Operation not supported by a specific collection or API | Choose an operation/implementation that satisfies the contract |

Important notes:

- `NumberFormatException` **extends** `IllegalArgumentException`; `ArrayIndexOutOfBoundsException` **extends** `IndexOutOfBoundsException`. The order of `catch` branches must respect this relationship.
- `ArithmeticException` does not mean every Java arithmetic operation checks for all numerical errors: integer division by `0` throws an exception, but normal integer overflow does not automatically throw an exception; floating-point division under IEEE 754 has its own behavior (e.g., `Infinity` or `NaN`).
- `NullPointerException` may be generated by the JVM itself or thrown explicitly by code (e.g., using `Objects.requireNonNull`). How well the location and message are identified depends on how the error arises.
- `UnsupportedOperationException` is unchecked; not every collection supports every modification operation. For example, `List.of(1, 2).add(3)` will throw `UnsupportedOperationException`.
- Other exceptions in the Java ecosystem can also belong to the unchecked group; the list here is meant to identify the most important cases.

### User Error or Programmer Error?

An exception such as `NumberFormatException` may occur because a user types letters into a numeric field. The interface layer can catch the error and return a **normal** validation message. However, if internal code itself mis-parses a configuration that was already validated, it may be a bug or a system data error.

Classify based on **the contract of the operation** and the data source, not just the exception name. You should not turn every "invalid user input" case into a chain of unchecked exceptions propagating across the entire system if the application already has clear validation branches.

## 5. How Are Unchecked Exceptions Thrown, Propagated, and Caught?

The propagation mechanism is no different from checked exceptions. When `throw` is executed, subsequent statements on that execution path are skipped; the JVM searches for a compatible `catch` in the current `try` block and then in outer calling methods.

Because unchecked exceptions do not require `throws`, **the absence of `throws` does not prove a method will not fail**. For example:

```java
static int parseQuantity(String text) {
    int quantity = Integer.parseInt(text);
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }
    return quantity;
}
```

This is an illustrative method snippet, not a standalone program. The method does not declare `throws NumberFormatException` or `throws IllegalArgumentException` and still compiles validly; the caller can still receive the exception at runtime.

You **can** declare `throws IllegalArgumentException` to document the contract:

```java
static int parseQuantity(String text) throws IllegalArgumentException {
    return Integer.parseInt(text);
}
```

This is also just an illustrative method. That declaration **does not require** the caller to catch or redeclare it. And `throws` does not "enable" throwing the exception: unchecked exceptions can already occur even if the signature does not list them.

### Complete Runnable Example with Multiple Branches

Save as `UncheckedFlowDemo.java`:

```java
public class UncheckedFlowDemo {
    static int parsePositive(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        return value;
    }

    static int price(int quantity, boolean available) {
        if (!available) {
            throw new IllegalStateException("Bộ tính giá chưa sẵn sàng");
        }
        return quantity * 20;
    }

    public static void main(String[] args) {
        String[] texts = {"2", "abc", "0", "3"};
        boolean[] available = {true, true, true, false};

        for (int i = 0; i < texts.length; i++) {
            String input = texts[i];

            try {
                int quantity = parsePositive(input);
                System.out.println(input + " -> " + price(quantity, available[i]));
            } catch (NumberFormatException e) {
                System.out.println(input + " -> không phải số nguyên");
            } catch (IllegalArgumentException e) {
                System.out.println(input + " -> " + e.getMessage());
            } catch (IllegalStateException e) {
                System.out.println(input + " -> " + e.getMessage());
            }
        }
        System.out.println("Hoàn tất vòng lặp");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 UncheckedFlowDemo.java
java UncheckedFlowDemo
```

**Exact stdout** on a UTF-8 console:

```text
2 -> 40
abc -> không phải số nguyên
0 -> Số lượng phải lớn hơn 0
3 -> Bộ tính giá chưa sẵn sàng
Hoàn tất vòng lặp
```

Explanation: the input `"2"` follows the success path. `"abc"` causes `parseInt` to throw `NumberFormatException`. `"0"` parses as a number successfully, and then the application's condition throws `IllegalArgumentException`. `"3"` passes parsing, but `price` throws `IllegalStateException` due to the unavailable state. All three exceptions are handled by the appropriate `catch` blocks; the loop can continue.

The first two `catch` branches illustrate the principle of **catching subclasses before superclasses**: `NumberFormatException` is a subclass of `IllegalArgumentException`. Reversing the order of the two branches would cause a compile error because the subsequent `NumberFormatException` catch branch becomes unreachable.

The example uses `available` as a technical state ("the price calculator is initialized"). A common business rejection scenario, such as **out of stock**, should preferably be designed as a stateful result rather than being lumped into `IllegalStateException`.

## 6. `Error` Is Also Unchecked, but It Is Not a Business Error

`Error` is a direct child branch of `Throwable`, **separate from the `Exception` branch**. `Error` and its subclasses are unchecked: the compiler does not require the caller to write `catch` or `throws`. However, unlike many `RuntimeException`s used to signal invalid arguments or state, `Error` is usually tied to serious issues in the runtime environment, class loading, or program invariants.

| `Error` family | Examples | Interpretation and handling limits |
| --- | --- | --- |
| `VirtualMachineError` | `OutOfMemoryError`, `StackOverflowError` | May indicate insufficient memory/stack or faulty recursion; being able to catch it does not mean safe recovery |
| `LinkageError` | `NoClassDefFoundError`, `ExceptionInInitializerError` | May relate to dependencies, classpath, or class initialization; the root cause must be found and fixed |
| `AssertionError` | Violated assertion | May be thrown intentionally by code or tests; does **not** necessarily mean the JVM is corrupted |

An `OutOfMemoryError` does not have only a single `Java heap space` cause: the message may indicate heap, metaspace, or other resource limits depending on the JVM. With `StackOverflowError`, you usually have to fix recursion depth/termination conditions; catching the error must not be treated as a fix for the algorithm. With `NoClassDefFoundError`, do not equate it with the checked `ClassNotFoundException`.

**The core point of unchecked exceptions:** having no requirement to catch/declare at *compile time* does not mean the error is ignored at *runtime*. Deep operational details of `VirtualMachineError` do not change this classification rule.

## 7. Catching `Throwable` Can Swallow `Error` as Well

`catch (Exception)` covers checked exceptions under `Exception` **and** all `RuntimeException`s, but **does not** catch `Error`. `catch (Throwable)` is broader: it can catch both `OutOfMemoryError` and `LinkageError`. Therefore, business code should not catch `Throwable` and silently return success.

```java
// Anti-pattern: illustrative calls within an application context.
try {
    runTask();
} catch (Throwable ignored) {
    // Very dangerous: also swallows Error.
}
```

Broad catching can only make sense at special boundaries, such as a test runner or diagnostic infrastructure with a clear policy for logging, isolating, and rethrowing. When you know how to handle a specific failure, catch **the specific exception type**. Do not use `catch (Throwable)` as a substitute for cleanup: `try-with-resources` or `finally` are more appropriate for preserving resource lifecycles in normal Java execution flows.

## 8. Creating Custom Unchecked Exceptions When the Contract Truly Needs Them

In some APIs, an abnormal condition has its own specific meaning and the caller needs to catch it precisely by type. You can create a subclass of `RuntimeException`:

```java
public class CustomUncheckedDemo {
    static class InvalidTransitionException extends RuntimeException {
        InvalidTransitionException(String message) {
            super(message);
        }
    }

    enum State {
        CREATED, SHIPPED
    }

    static void ship(State state) {
        if (state != State.CREATED) {
            throw new InvalidTransitionException(
                    "Chỉ được gửi đơn ở trạng thái CREATED");
        }
        System.out.println("Đã gửi đơn");
    }

    public static void main(String[] args) {
        ship(State.CREATED);
        try {
            ship(State.SHIPPED);
        } catch (InvalidTransitionException e) {
            System.out.println(e.getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CustomUncheckedDemo.java
java CustomUncheckedDemo
```

**Exact stdout** with UTF-8:

```text
Đã gửi đơn
Chỉ được gửi đơn ở trạng thái CREATED
```

`InvalidTransitionException` extends `RuntimeException`, so it is also unchecked; `ship` does not need to declare `throws`. The caller can still catch the exact type to handle it.

However, it is not always necessary to use an exception for every order state. If "cannot ship because the order has already been shipped" is a normal case that the system needs to report to the user, returning a result value like `ALREADY_SHIPPED` may be clearer. A custom exception is more appropriate when an operation is called in violation of an API's preconditions/invariants and the current flow must be stopped.

Do not create subclasses of `Error` to represent validation errors, out-of-stock conditions, or declined transactions. Doing so misleads readers about the severity and bypasses normal `Exception`-handling boundaries.

When you need to create an exception from another cause, provide a constructor for both message and cause:

```java
// Illustrates a type definition; does not contain main.
class ConfigurationRuntimeException extends RuntimeException {
    ConfigurationRuntimeException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Preserving `cause` helps diagnose the root error. Only convert a checked exception into an unchecked one when the current layer's contract allows it and the calling layer knows how to respond; avoid wrapping solely to bypass checked-exception rules.

## 9. Where Do Checked and Unchecked Differ in Source Code?

Consider two illustrative methods:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FileAndInput {
    static String load(Path path) throws IOException {
        return Files.readString(path);
    }

    static int parse(String text) {
        return Integer.parseInt(text);
    }
}
```

This code is a valid Java class, though it has no `main` method. `load` may throw `IOException`, so it declares `throws IOException`; a caller that is not inside an appropriate `catch` or does not propagate `throws` will get a compile error when calling it. `parse` may throw `NumberFormatException`, yet it is not required to declare it and the caller is not forced to catch it.

Two things are commonly misunderstood:

1. If `parse` voluntarily adds `throws NumberFormatException` to its signature, **the type is still unchecked**; the compile-time obligation at the caller does not change.
2. If a method declares `throws Exception`, the caller must satisfy the catch/declare obligation for **the checked type `Exception`** announced in the signature, even if internally it sometimes only throws an unchecked exception. The declared contract carries its own meaning.

### Method Overriding and `throws`

The overriding rule for checked exceptions: an overriding method generally cannot add a checked exception broader than what the parent method allows. However, unchecked exceptions are not restricted by this rule.

Valid Java code example:

```java
class ParentWorker {
    void execute() {
        // Contract has no checked exceptions.
    }
}

class ChildWorker extends ParentWorker {
    @Override
    void execute() throws IllegalStateException {
        throw new IllegalStateException("Chưa khởi tạo");
    }
}
```

This is an illustrative class without `main`. `IllegalStateException` is unchecked, so the overriding signature is valid. If replaced with `throws IOException`, this code will not compile because it declares a new checked exception that the parent method does not allow.

## 10. Designing `RuntimeException` Handling at the Right Layer

The layer that detects an error and the layer that decides the response may be different:

1. **Library/API layer:** validate arguments and invariants, throw `IllegalArgumentException` or `IllegalStateException` when a contract is violated; choose a specific type and a useful message.
2. **Request-handling layer:** validate user data, convert parse errors into structured messages when those are expected cases. Do not expose stack traces to users.
3. **Business layer:** return domain statuses for valid rejection branches; keep technical/invariant errors separate.
4. **Application boundary:** log the root cause, classify the response, abort the request, or mark the job as failed according to policy.

For an HTTP API, returning `400` for invalid input, `409` for a business conflict, or `500` for an internal error is **an API contract choice**, not an automatic Java rule. The same `IllegalArgumentException` can originate from user input or an internal bug; returning `400` based solely on the class name can mask programming errors.

**Do not use unchecked exceptions as a shortcut for every problem.** If a library throws `IOException`, replacing it with `RuntimeException` does not magically create a recovery strategy. Only translate types when an appropriate abstraction boundary is needed, and preserve the original cause via `cause`.

**Do not log the exact same full exception at every layer**, as that creates duplicate log entries; choose a place with sufficient context, keep the necessary stack trace/cause, and do not leak passwords, tokens, or sensitive data.

## 11. Common Pitfalls

| Misconception | Correct understanding |
| --- | --- |
| "Unchecked means the JVM does not detect it." | The JVM still throws the exception; there is only no `catch-or-declare` obligation in the compiler. |
| "Every subclass of `Exception` is checked." | `RuntimeException` and its subclasses are unchecked. |
| "`RuntimeException` and `Error` should be caught the same way." | Both are unchecked, but `Error` usually indicates a very serious problem where continuing safely is difficult. |
| "No `throws` means the method throws no exceptions." | Unchecked exceptions can occur without being declared. |
| "Adding `throws RuntimeException` forces the caller to catch it." | No; unchecked types are still not subject to the mandatory catch/declare rule. |
| "`catch (Exception e)` catches `OutOfMemoryError`." | No, because `Error` is outside the `Exception` branch. |
| "Catch `Throwable` so the application can never crash." | It can swallow serious errors and attempt to continue when the JVM state is unsafe. |
| "`NoClassDefFoundError` and `ClassNotFoundException` are the same kind." | One is an unchecked `Error`, the other is a checked `Exception`. |
| "`assert` replaces all validation." | Assertions can be disabled; do not use them to validate untrusted data. |
| "Every user error is a bug." | Parse exceptions can be converted into expected validation results at the appropriate boundary. |
| "`Error` means a compile error." | `Error` is a Java class, whereas a compile error is a compiler diagnostic. |
| "Catching an exception and ignoring it means it is handled." | It can lose the cause, return a bogus result, and leave state corrupted going forward. |

## 12. Practice Questions and Scenarios

**1. Is `NumberFormatException` checked?**  
No. It is a subclass of `IllegalArgumentException`, which in turn extends `RuntimeException`.

**2. Does `NullPointerException` need to be declared in `throws` for every method that could throw it?**  
No. You can document the contract with comments or clear API design, but the compiler does not require declaring unchecked exceptions.

**3. Is `IOException` unchecked because it sometimes happens at runtime?**  
No. "Checked/unchecked" is determined by the `Throwable` hierarchy, not when it occurs: `IOException` is checked.

**4. Is it valid to put `catch (IllegalArgumentException e)` before `catch (NumberFormatException e)`?**  
No, if both are consecutive branches of the same `try` in that order. The branch for the subclass is unreachable because the superclass already catches it.

**5. Why should you not use `catch (Error e)` for every operation?**  
Because many `Error`s signal platform failures, such as the JVM running out of memory or class linkage errors. Catching them does not fix the root cause and may continue execution in a broken state.

**6. Does `assert condition` always check `condition`?**  
No. Whether assertions execute depends on enable/disable configuration (`-ea` and corresponding options). Therefore, do not replace input validation or security checks with assertions.

**7. Is a class-not-found failure when calling `Class.forName` always a `NoClassDefFoundError`?**  
No. `Class.forName` can throw the checked `ClassNotFoundException`; `NoClassDefFoundError` is a different error in the `LinkageError` branch.

**8. When an order's state is already SHIPPED, is it mandatory to throw a custom unchecked exception?**  
No. You can use a normal domain result or an exception depending on the contract and the meaning of calling in an invalid state.

**9. Can you just remove `throws IOException` from a file-reading method to turn it into unchecked?**  
No. If it still calls an API with checked `IOException` without handling it, the method will not compile. Changing the contract requires catching and handling/converting it intentionally.

**10. Will an uncaught unchecked exception terminate the entire JVM in every case?**  
No. It propagates to a `catch` or handling boundary; if it escapes a thread, that thread may terminate while other threads remain alive. A simple console application may terminate when an exception escapes `main`.

## 13. Self-Check Before Choosing How to Handle

When you see an error, determine three things in order:

- **Which branch does it belong to?** `RuntimeException`, `Error`, or another checked exception? The hierarchy determines the compiler's obligation.
- **What is the cause and scope of impact?** Bad input, violated contract, invalid state, missing library, JVM resource exhaustion, or a broken invariant?
- **Can the current layer handle it safely?** If yes, catch the right type and provide a meaningful response/recovery. If not, let the error propagate to a boundary with an appropriate policy; for many `Error`s, the root cause must be fixed and the ability to continue operating must be re-evaluated.

**Remember:** `RuntimeException` and `Error` are both **unchecked**, because Java does not require callers to catch or declare them. The difference in meaning and recoverability is the basis for choosing how to handle them. Reading the hierarchy accurately helps avoid conflating bad input data with JVM errors, avoids overly broad catches, and helps design APIs with clear contracts.
