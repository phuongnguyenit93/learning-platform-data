# Creating Exception Objects with Constructors in Java

In Java, exceptions are **objects**. Before an exception can be thrown with the `throw` statement, the program needs a reference to an object of a class that inherits from `Throwable`. The most common way is to call a **constructor** with the `new` operator:

~~~java
throw new IllegalArgumentException("Tuổi phải lớn hơn hoặc bằng 0");
~~~

This statement consists of **two distinct actions**:

1. `new IllegalArgumentException("...")` creates an exception object, passing the message to the constructor.
2. `throw` throws the reference to that object, interrupting normal execution flow and starting the search for a matching `catch`.

You can create the object first and throw it later; creating the object alone **does not trigger exception control flow**. This lesson explains exception class constructors, how to pass a message and cause, how to define custom exceptions, and common mistakes when using `throw new`.

## 1. Exceptions Are Objects Inheriting from `Throwable`

Simplified hierarchy:

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    └── java.lang.Exception
        ├── java.io.IOException
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            └── java.lang.NullPointerException
~~~

These classes own or inherit state and behavior such as:

- `getMessage()`: retrieves the message describing the error.
- `getCause()`: retrieves the linked root exception/cause, if any.
- `getStackTrace()` and `printStackTrace()`: used for diagnosing where the stack trace was created/recorded.
- `getSuppressed()`: retrieves suppressed exceptions, such as when closing resources in try-with-resources.

The constructor is where the program **initializes** this object. The constructor does not determine whether an exception is checked or unchecked: that depends on the **class type** of the object. For example:

- `new IOException("...")` creates a checked exception.
- `new IllegalArgumentException("...")` creates an unchecked exception.
- Both can be stored in a variable, passed to a method, or thrown with `throw`.

For a `Throwable` class, `new` does not automatically mean `throw`.

## 2. Distinguishing Creating an Exception from Throwing an Exception

`new IllegalArgumentException("x")` creates an exception object and **does not automatically propagate the error to the caller**; `throw new IllegalArgumentException("x");` both creates and throws it. If you already have a variable `e` compatible with `Throwable`, `throw e;` throws the referenced object without calling a new constructor. `throws IOException` in a method signature only describes the possibility of a checked exception escaping; it does not create or throw an object.

```java
IllegalArgumentException ex = new IllegalArgumentException("Sai");
System.out.println(ex.getMessage()); // Still runs normally.
throw ex; // Begins transferring control via exception.
```

This is a snippet inside a method. Creating `new IOException(...)` also does not automatically trigger the `catch-or-declare` requirement if there is no path that actually throws the checked exception. The focus of this lesson is **constructors, message, cause, and super(...)**; the detailed mechanics of `new` versus `throw` are covered in the lesson comparing the two operations.

## 3. Common Constructor Forms

Standard exception classes may provide one or more of the following constructor forms. **Not every exception class has all of these forms**; you must check the API of the specific type.

### No-argument constructor

~~~java
RuntimeException issue = new RuntimeException();
~~~

In this example, `issue.getMessage()` is `null` because no message was passed in. Some classes also provide a no-argument constructor, but you should not assume every class has one.

### Constructor accepting a message: `(String message)`

~~~java
IllegalArgumentException issue =
        new IllegalArgumentException("age phải >= 0");
~~~

The message is typically stored to be returned via `getMessage()`. The message should clearly state **which condition was not met**, enough for someone reading the logs to understand the context:

- Useful: `"age phải nằm trong khoảng 0..150"`.
- Hard to diagnose: `"Lỗi"` or `"Có vấn đề"`.

The message is diagnostic data, not a good choice for control flow via string comparison; the text may change or be localized.

### Constructor accepting a cause: `(Throwable cause)`

~~~java
IllegalStateException issue =
        new IllegalStateException(
                new java.io.IOException("Không đọc được cấu hình"));
~~~

This example uses the built-in `IllegalStateException(Throwable)` constructor. `issue.getCause()` returns the `IOException` object that was passed in. With this form of constructor inherited by design from `Throwable`, the new exception's message is typically generated from `cause.toString()` if the cause is non-`null`. That message does not necessarily describe enough context at a higher layer.

### Constructor accepting both a message and a cause: `(String message, Throwable cause)`

~~~java
java.io.IOException lowLevel =
        new java.io.IOException("Tệp không tồn tại");

IllegalStateException issue =
        new IllegalStateException(
                "Không thể khởi tạo ứng dụng", lowLevel);
~~~

When converting exception types between layers, this constructor form is usually the most useful:

- `issue.getMessage()` returns `"Không thể khởi tạo ứng dụng"`.
- `issue.getCause() == lowLevel` is `true`.
- The higher-level exception explains **which operation failed**; the cause preserves the original information for investigation.

If you only call `new IllegalStateException("Không thể khởi tạo ứng dụng")` when wrapping a low-level error, the cause link is lost unless it is set separately in a valid way.

### Which constructors are actually available?

The examples above use constructors that exist on `RuntimeException`, `IllegalStateException`, `IOException`, and `IllegalArgumentException` in Java 17+. A specific class might only support a few forms or require special parameters. For example:

~~~java
NumberFormatException bad =
        new NumberFormatException("Không phải số nguyên");
~~~

The `NumberFormatException(String)` constructor is valid; however, you cannot assume this class has a `NumberFormatException(String, Throwable)` constructor just because some parent classes have a similar constructor. **Constructors are not inherited** like regular methods. Always check the constructor signatures of the exact class you want to instantiate.

## 4. Choosing Message and Cause to Preserve Error Information

Suppose an application converts a configuration string to an integer:

~~~java
static int parsePort(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Cổng không phải số nguyên: " + raw, cause);
    }
}
~~~

This is an **illustrative method**, not a standalone program. When the input cannot be parsed, `Integer.parseInt` throws `NumberFormatException`. The `catch` block creates a new `IllegalArgumentException` object with:

- A message indicating which input is invalid in the network port context.
- The cause being the original `NumberFormatException`.

Because `NumberFormatException` is also a subclass of `IllegalArgumentException`, wrapping the exception here is mainly to **add context**, not to change the checked/unchecked branch. Consider whether the calling layer needs to know the error was translated; do not catch and wrap every exception without a reason.

### Do not use the message to simulate a cause

A less useful example:

~~~java
throw new IllegalStateException(
        "Không đọc được cấu hình: " + original.getMessage());
~~~

If `original` is a real exception variable in scope, this snippet only copies part of the text; `getCause()` on the new exception remains `null`. Instead:

~~~java
throw new IllegalStateException(
        "Không đọc được cấu hình", original);
~~~

These are two **illustrative lines in a context with an `original` variable**, not a complete program. The constructor accepting a cause preserves a structured link to the original exception.

### Be careful with sensitive data

Messages may appear in logs, stack traces, or error responses if the application is loosely configured. Avoid putting passwords, tokens, credentials, or the full contents of private documents into error strings. Only record necessary and safe information, such as parameter names, operation codes, or sanitized identifiers.

## 5. Standalone Runnable Java 17+ Program

The example below illustrates four important points:

1. A constructor creates the object before throwing.
2. `throw new` invokes the constructor directly at the point of failure.
3. A custom exception accepts both a message and a cause.
4. `getMessage()` and `getCause()` yield accurate, verifiable results.

Create the file **`ExceptionConstructorDemo.java`**:

~~~java
public class ExceptionConstructorDemo {

    static class ConfigurationException extends Exception {
        ConfigurationException(String message) {
            super(message);
        }

        ConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        IllegalArgumentException prepared =
                new IllegalArgumentException("Tên không được trống");

        System.out.println("Tạo trước: " + prepared.getMessage());

        try {
            throw prepared;
        } catch (IllegalArgumentException e) {
            System.out.println("Bắt sau: " + e.getMessage());
            System.out.println("Cùng đối tượng: " + (e == prepared));
        }

        try {
            System.out.println("Cổng: " + readPort("abc"));
        } catch (ConfigurationException e) {
            System.out.println("Lỗi cấu hình: " + e.getMessage());
            System.out.println(
                    "Cause: " + e.getCause().getClass().getSimpleName());
        }

        try {
            System.out.println("Cổng: " + readPort("70000"));
        } catch (ConfigurationException e) {
            System.out.println("Lỗi cấu hình: " + e.getMessage());
            System.out.println("Cause: " + e.getCause());
        }

        System.out.println("Cổng: " + readPortOrDefault("8080", 80));
        System.out.println("Cổng mặc định: " + readPortOrDefault("abc", 80));
    }

    static int readPort(String raw) throws ConfigurationException {
        final int port;
        try {
            port = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new ConfigurationException(
                    "Cổng không phải số nguyên: " + raw, cause);
        }

        if (port < 1 || port > 65535) {
            throw new ConfigurationException(
                    "Cổng phải nằm trong khoảng 1..65535");
        }

        return port;
    }

    static int readPortOrDefault(String raw, int fallback) {
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}
~~~

Compile and run:

~~~bash
javac ExceptionConstructorDemo.java
java ExceptionConstructorDemo
~~~

Expected stdout:

~~~text
Tạo trước: Tên không được trống
Bắt sau: Tên không được trống
Cùng đối tượng: true
Lỗi cấu hình: Cổng không phải số nguyên: abc
Cause: NumberFormatException
Lỗi cấu hình: Cổng phải nằm trong khoảng 1..65535
Cause: null
Cổng: 8080
Cổng mặc định: 80
~~~

**Explanation:**

- `prepared` is created via `new IllegalArgumentException(...)` and only then thrown with `throw prepared;`. The comparison `e == prepared` evaluates to `true` because the `catch` block receives the **same object reference** that was thrown; `throw` does not automatically create a copy.
- `readPort("abc")` encounters a string parsing error. The `ConfigurationException(String, Throwable)` constructor calls `super(message, cause)` and thus preserves the `NumberFormatException`; therefore, the printed cause class name is `NumberFormatException`.
- `readPort("70000")` parses into a number successfully but violates the valid range. The exception is created by the message-only constructor; `getCause()` is `null`.
- `readPortOrDefault` illustrates handling at a layer that has a fallback value: `Integer.parseInt("abc")` throws an unchecked exception, and the method chooses to return `80`. This method only checks whether the string can be parsed as a number and **does not validate the port range 1..65535**; in a real API, additional validation must be added if required by the contract.
- `ConfigurationException` is a checked exception because it extends `Exception` and is not in the `RuntimeException` branch; calls to `readPort` are placed in corresponding `try/catch` blocks.

Separating `new` and `throw` makes the boundary clear: **the constructor defines the exception's data; `throw` transfers control to the exception-handling mechanism**.

## 6. Constructors of Custom Exceptions

When standard exceptions do not adequately express the meaning of an error in your application domain, you can declare your own exception class. Two common choices:

### Custom checked exception

~~~java
public class ImportException extends Exception {
    public ImportException(String message) {
        super(message);
    }

    public ImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is the **contents of a standalone class** if placed in `ImportException.java`. This type is checked, so a method throwing it must catch or declare it according to Java's rules:

~~~java
static void importData() throws ImportException {
    throw new ImportException("Dữ liệu nhập thiếu trường bắt buộc");
}
~~~

This illustrative method needs to be inside a Java class. If import errors can be handled in a structured way by the caller, a checked type can help the API contract require callers to consider the failure.

### Custom unchecked exception

~~~java
public class InvalidOrderStateException extends RuntimeException {
    public InvalidOrderStateException(String message) {
        super(message);
    }

    public InvalidOrderStateException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is the **contents of a standalone class** if saved in `InvalidOrderStateException.java`. This exception is not required to be declared with `throws` or caught by the caller because it extends `RuntimeException`.

There is no rule that "custom exceptions must always be checked" or "all business errors are unchecked." Choose the type based on the contract, the caller's ability to handle it, and API design conventions.

### Why do subclass constructors call `super(...)`?

Subclass constructors **do not automatically inherit constructors** from the superclass. When you write `super(message)` or `super(message, cause)`, you pass the data to `Throwable`'s initialization mechanism through the corresponding superclass.

If a custom exception class writes a constructor like:

~~~java
public MyException(String message) {
    // Does not call super(message).
}
~~~

then if the superclass has a matching no-argument constructor and the code compiles, Java implicitly calls `super()`. The `message` string is **not automatically assigned** to `Throwable`'s message state, so `getMessage()` will typically return `null`. To use a constructor like this example, `MyException` must be validly declared with a superclass that has the corresponding constructor; this snippet only illustrates the difference of calling `super`.

You should not create a redundant `message` field just to "fix" the issue above. Prefer `super(message)` to maintain consistent behavior with Java's exception-handling APIs.

## 7. Cause, `initCause`, and Cause Chains

Exception classes built on `Throwable` can hold a **cause chain**:

~~~text
IllegalStateException: Không thể khởi tạo ứng dụng
└── caused by IOException: Không đọc được cấu hình
    └── caused by FileNotFoundException: Thiếu file cấu hình
~~~

The diagram above illustrates the concept of `getCause()` links, not a verbatim stack trace printed by the JVM.

Normally, prefer the constructor that accepts a cause:

~~~java
throw new IllegalStateException(
        "Không thể khởi tạo ứng dụng", original);
~~~

If a class does not have a constructor accepting a cause but allows setting the cause after creation, `Throwable.initCause(Throwable)` can assign the cause **once**:

~~~java
Exception wrapper = new Exception("Không thể xử lý");
wrapper.initCause(new java.io.IOException("Kết nối bị ngắt"));
~~~

The two statements above are valid when placed inside a Java method. However:

- `initCause` cannot be called successfully multiple times on the same object; calling it again throws `IllegalStateException`.
- An exception cannot be set as its own cause.
- If the constructor has already **initialized the cause** (even if `null` was passed to a constructor accepting a cause), `initCause` cannot replace it.
- When a class has a constructor accepting `Throwable` or `(String, Throwable)`, use it directly instead of `initCause`.

**Cause** and **suppressed exceptions** are two different mechanisms. Cause describes the causal relationship that led to the outer exception; suppressed exceptions can hold additional errors that occurred during cleanup, especially with try-with-resources. Do not use `addSuppressed` as an arbitrary substitute for cause.

## 8. When Is the Stack Trace Created?

By default, `Throwable` constructors typically record the stack trace at the time the object is **instantiated**, via the superclass's stack trace population mechanism. Therefore:

~~~java
RuntimeException ex = new RuntimeException("Ví dụ");
// You can inspect ex.getStackTrace() here, even before throwing.
~~~

This is an illustrative snippet; having a stack trace does not mean the exception has been thrown or logged. Calling `new RuntimeException(...)` usually already creates the diagnostic information.

Several important situations:

- If you create an exception in one place and throw it in another, the object's stack trace typically reflects the **instantiation site**.
- Rethrowing the **same object** with `throw e;` does not automatically create a brand-new stack trace at the rethrow site.
- Stack trace recording can be customized—for example, `Throwable`/`Exception`/`RuntimeException` constructors have a `writableStackTrace` option for special cases; you should not disable stack traces if error investigation is needed.
- Avoid reusing the same exception object for multiple independent incidents; the stack trace and cause may no longer accurately reflect the context of each occurrence.
- Manually calling `fillInStackTrace()` can update the object's trace, but it alters diagnostic information; most applications do not need to do this manually.

Specifically, *message*, *cause*, and *stack trace* are three separate things: the message explains the error content; the cause links the origin; the stack trace helps locate the call path at the recording point.

## 9. Constructors and Checked Exceptions: Classification Does Not Depend on Parameters

These two statements:

~~~java
new java.io.IOException("Không đọc được");
new IllegalStateException("Đối tượng chưa sẵn sàng");
~~~

both only **create objects**. When thrown:

~~~java
static void checkedExample() throws java.io.IOException {
    throw new java.io.IOException("Không đọc được");
}

static void uncheckedExample() {
    throw new IllegalStateException("Đối tượng chưa sẵn sàng");
}
~~~

These are two illustrative methods. `checkedExample` declares `throws IOException` because `IOException` is checked; `uncheckedExample` is not forced to declare it because `IllegalStateException` is unchecked.

Changing the constructor from `(String)` to `(String, Throwable)` **does not turn** a checked exception into an unchecked one or vice versa. That is a property of the **exception class**, determined by its inheritance relationship with `RuntimeException` and `Error`.

## 10. Common Mistakes When Creating Exceptions

### Forgetting `throw`

~~~java
if (age < 0) {
    new IllegalArgumentException("age không được âm");
}
~~~

This is a **counterexample**: the program creates the object and discards it; it does not throw an exception. The correct way:

~~~java
if (age < 0) {
    throw new IllegalArgumentException("age không được âm");
}
~~~

Both snippets assume the `age` variable already exists and are inside a method.

### Using a nonexistent constructor

Not every exception type has all four standard overloads. Constructors are not inherited, so `new SomeException("message", cause)` is only valid when **the `SomeException` class actually declares the corresponding constructor**. For custom classes, define the overloads and call `super` appropriately.

### Losing the cause when translating exceptions

~~~java
catch (java.io.IOException e) {
    throw new IllegalStateException("Không tải được dữ liệu");
}
~~~

The illustrative snippet above loses the cause link. When appropriate, write:

~~~java
catch (java.io.IOException e) {
    throw new IllegalStateException("Không tải được dữ liệu", e);
}
~~~

These are **illustrative `catch` blocks** attached to a `try` that can actually throw `IOException`. Preserving the cause makes the `Caused by` relationship readable when printing the stack trace.

### Using an overly generic exception

~~~java
throw new RuntimeException("Sai");
~~~

This statement is valid but vague. If an input parameter is invalid, `IllegalArgumentException` with a specific message is usually more helpful. If an operation is invalid due to the object's state, consider `IllegalStateException`. Choose a type matching the contract instead of always using `Exception` or `RuntimeException`.

### Putting secrets in the message

The message should provide useful context, not be a place to copy tokens, passwords, or private data. Reading logs is also part of an application's security model.

### Creating an exception once and throwing it repeatedly without control

Each new incident should generally have its own exception object to accurately reflect its context and cause. Reusing the same object across multiple locations can cause confusion regarding the stack trace, cause, and incident history, especially across multiple threads.

### Confusing the cause with the type of the thrown exception

~~~java
RuntimeException wrapper =
        new IllegalStateException(
                "Lỗi miền", new java.io.IOException("Lỗi I/O"));
throw wrapper;
~~~

This snippet throws an `IllegalStateException`. `catch (IOException e)` will **not** automatically catch it, even though `getCause()` returns an `IOException`. Handlers match the type of the exception currently being propagated. To handle the root cause, an appropriate layer can inspect `getCause()` or design the API differently.

### Calling `initCause` after a constructor that already initialized the cause

~~~java
Exception e = new Exception("Lỗi", null);
e.initCause(new java.io.IOException("Nguyên nhân mới"));
~~~

This is a **counterexample**: the `Exception(String, Throwable)` constructor has already initialized the cause state even though the argument is `null`. The subsequent `initCause` call throws `IllegalStateException`. Avoid two-step initialization when a constructor accepting a cause is already available.

## 11. Criteria for Choosing the Right Constructor

| Need | Common Choice | Purpose |
| --- | --- | --- |
| New error, direct description | `new IllegalArgumentException("...")` | Provides a message for the violated condition |
| Translating from a low-level exception | `new IllegalStateException("...", cause)` | Preserves the cause and adds context |
| Already have an exception object | `throw e;` | Continues throwing the same object when the contract allows |
| Custom checked exception API | Class `extends Exception` with `super(message, cause)` | Callers must address catch/throws obligations |
| Custom unchecked exception API | Class `extends RuntimeException` with `super(message, cause)` | Represents an error without catch/declare obligations |
| Need to store a structured error code | Custom constructor accepting `code` and forwarding message/cause via `super` | Machines handle by stable code; readers view the message |

If a custom error class needs an error code field, you can write:

~~~java
public final class ValidationException extends RuntimeException {
    private final String code;

    public ValidationException(
            String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

This is a **standalone class** if saved in `ValidationException.java`. Usage:

~~~java
throw new ValidationException(
        "INVALID_AGE", "Tuổi không hợp lệ", originalCause);
~~~

This usage line is illustrative in a scope with an appropriate `originalCause` variable. The contract can check `getCode()` instead of comparing `getMessage()` strings, since the message may change.

## 12. Self-Check Questions

1. What is the difference between `new IllegalArgumentException("x")` and `throw new IllegalArgumentException("x");`?
2. If you create `new IOException("x")` without throwing it, are you required to declare `throws IOException`?
3. When do you use the `(String message, Throwable cause)` constructor instead of just `(String message)`?
4. Why should a custom exception class constructor call `super(message, cause)` when passed those two parameters?
5. Are constructors automatically inherited from `RuntimeException` to a subclass?
6. Will an `IllegalStateException` whose cause is an `IOException` be caught directly by `catch (IOException e)`?
7. Is a stack trace normally associated with the time the exception is created, or does it only appear for the first time upon `throw`?
8. What happens if you call `initCause` on an exception whose cause was already initialized by a constructor accepting `(String, Throwable)`?
9. Why should an API avoid having callers infer the error type by comparing message strings?
10. When should you create a custom exception class instead of using `IllegalArgumentException` or `IllegalStateException`?

**Summary answers:** (1) `new` creates the object, `throw` throws the object; (2) no, checked obligations arise when throwing or calling code that can throw; (3) when wrapping an error and needing to preserve the cause; (4) to initialize message/cause in `Throwable`; (5) no; (6) no, because the propagating object is `IllegalStateException`; (7) normally when the `Throwable` object is instantiated; (8) throws `IllegalStateException`; (9) because the message is not a stable machine-readable contract; (10) when specific error semantics, error codes, or a distinct API contract are needed.

**Remember:** **A constructor creates and initializes the data of an exception object; the `throw` statement initiates the exception propagation path.** Choose the appropriate overload to provide a useful message, preserve the cause when wrapping errors, and use the right checked/unchecked type according to the method's contract.