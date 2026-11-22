# `getMessage()`, `getLocalizedMessage()`, and `toString()` on `Throwable` Objects in Java

When an exception occurs in Java, three methods of `Throwable` are commonly used to explain the error: `getMessage()`, `getLocalizedMessage()`, and `toString()`. They are related, yet **not synonymous**, and none of them returns the full stack trace on its own.

- **`getMessage()`** returns the **detail message** of the exception object as a `String`; the result can be `null`.
- **`getLocalizedMessage()`** is designed to support **localized messages**. With the default `Throwable` implementation, it simply calls `getMessage()`, so **there is no automatic language translation**.
- **`toString()`** in the default `Throwable` implementation produces a **short description with the exception class name**, typically `class-name: localized-message`. If the localized message is `null`, it returns only the class name.

This article explains the exact meaning, return values, how these methods interact under inheritance/overriding, the difference between a message and a cause/stack trace, and how to use them in logging, multi-language applications, and exception handling. Complete examples target Java 17 or later.

## 1. `Throwable` Is the Base Class of Exception Objects

A simplified view of the Java hierarchy looks like this:

```text
java.lang.Throwable
├── java.lang.Error
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        └── ...
```

Every exception and error that can be thrown under Java's exception system belongs to the `Throwable` branch. Therefore, the three methods we are studying appear in subclasses such as `IOException`, `IllegalArgumentException`, or `IllegalStateException`.

A `Throwable` object also has other important data and methods:

| Component | Question Answered |
| --- | --- |
| `getClass()` | What is the actual runtime type of the object? |
| `getMessage()` | What is the detail message of the error? |
| `getLocalizedMessage()` | Is there a localized message for the error? |
| `toString()` | What is the short description consisting of the error type and localized message? |
| `getCause()` | What is the underlying cause exception attached to the current error? |
| `getSuppressed()` | What secondary exceptions were retained, such as during cleanup? |
| `getStackTrace()` | Which stack frames were recorded for the exception? |
| `printStackTrace()` | How to print the stack trace along with cause/suppressed relationships? |

**A message is not an exception.** A message is just `String` data describing the error. An exception object also has a type, cause relationships, a stack trace, suppressed exceptions, and other characteristics.

## 2. `getMessage()`: The Detail Message

`Throwable.getMessage()` has the conceptual signature:

```java
public String getMessage()
```

The method returns the detail string associated with the exception. Many constructors allow you to pass a message:

```java
IllegalArgumentException error =
        new IllegalArgumentException("Số lượng phải dương");

String message = error.getMessage();
// message == "Số lượng phải dương"
```

This is an **illustrative code snippet**, not a standalone program. The message is typically stored at object creation time, though subclasses may override `getMessage()` with custom behavior. Therefore, you should not assume every subclass constructs its message internally in the same way.

A message should usually answer: which operation violated a contract, which parameter/state was invalid, or what failed. For example:

```java
throw new IllegalArgumentException(
        "quantity phải lớn hơn 0: " + quantity);
```

This is an **illustrative statement** within a scope that has a `quantity` variable. A contextual message is more useful than overly generic messages like `"error"`, but strictly avoid concatenating passwords, tokens, personal data, or sensitive content into messages.

**Important:** `getMessage()` can return `null`, especially when the object is created using a constructor that does not provide a detail message. A `null` result does not mean "no error occurred"; the exception object still exists.

## 3. `getLocalizedMessage()`: Not an Automatic Translation API

`Throwable.getLocalizedMessage()` also has a `String` return type:

```java
public String getLocalizedMessage()
```

In the default `Throwable` implementation, this method **returns the result of `getMessage()`**. Java does not automatically take an English sentence and translate it into Vietnamese based on `Locale.getDefault()`.

For example, if you create:

```java
Exception e = new Exception("Connection failed");
```

then according to the default `Throwable` implementation:

- `e.getMessage()` is `"Connection failed"`.
- `e.getLocalizedMessage()` is also `"Connection failed"`, regardless of whether you expect a Vietnamese UI.
- To return a language-localized string, a **subclass must proactively override** the method, or a presentation layer must translate it through a mechanism such as `ResourceBundle`.

A subtle point: when a subclass overrides `getMessage()` without overriding `getLocalizedMessage()`, the default `getLocalizedMessage()` calls `getMessage()` via Java polymorphism, so it reflects the value from that override. When a subclass overrides `getLocalizedMessage()` separately, the two methods can return **different** strings.

Localization is a **contract designed by the class or library**; you cannot infer solely from the name `getLocalizedMessage` that every exception is translated.

## 4. `toString()`: Class Name with Localized Message

According to the standard `Throwable` implementation, the result of `toString()` is formed from:

1. The **full runtime class name** of the object, i.e., `getClass().getName()`.
2. If `getLocalizedMessage()` is not `null`, append `": "` and the localized message.
3. If the localized message is `null`, return only the class name.

You can visualize the logic as follows (this is **illustrative code**, not a library implementation snippet to copy):

```java
String className = getClass().getName();
String localized = getLocalizedMessage();
return localized == null
        ? className
        : className + ": " + localized;
```

Example with `IllegalArgumentException` in the `java.lang` package:

```java
IllegalArgumentException e =
        new IllegalArgumentException("Sai tham số");

System.out.println(e.getMessage());
// Sai tham số

System.out.println(e.toString());
// java.lang.IllegalArgumentException: Sai tham số
```

These are **illustrative statements** inside a method, without `main`. When you pass an exception directly to `System.out.println(e)`, Java invokes the object-to-string conversion mechanism, which typically uses `toString()`.

**Do not confuse the class name in `toString()` with `getClass().getSimpleName()`.** `Throwable.toString()` uses the name returned by `getClass().getName()` in the standard implementation, which usually includes the package. For nested classes, the binary name may contain the `$` character; for classes inside a package, the package name also appears.

If a **subclass overrides `toString()`**, the result may differ from the default formula. The examples and rules in this article refer to the default `Throwable` implementation unless an override is explicitly noted.

## 5. Complete Example: Comparing the Three Methods and `null` Messages

Save the program as **`ThrowableMessagesDemo.java`**:

```java
public class ThrowableMessagesDemo {
    public static void main(String[] args) {
        Throwable withMessage =
                new IllegalArgumentException("Số lượng phải dương");

        System.out.println("message: " + withMessage.getMessage());
        System.out.println("localized: "
                + withMessage.getLocalizedMessage());
        System.out.println("toString: " + withMessage.toString());

        Throwable noMessage = new IllegalArgumentException();

        System.out.println("null message: "
                + (noMessage.getMessage() == null));
        System.out.println("null localized: "
                + (noMessage.getLocalizedMessage() == null));
        System.out.println("toString null: " + noMessage.toString());
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 --release 17 ThrowableMessagesDemo.java
java ThrowableMessagesDemo
```

**Exact stdout** on a UTF-8 console:

```text
message: Số lượng phải dương
localized: Số lượng phải dương
toString: java.lang.IllegalArgumentException: Số lượng phải dương
null message: true
null localized: true
toString null: java.lang.IllegalArgumentException
```

Explanation: both objects have the same runtime type `IllegalArgumentException` but different detail messages. When a message is present, `toString()` concatenates the class name and the message; when the message is `null`, the default version returns only the class name. Both are still real exception objects.

This is also why you must not assume you can call `e.getMessage().length()` without checking for `null`: the very method inspecting the message could cause the program to throw a new `NullPointerException` if the code dereferences a `null` result.

## 6. Distinguishing Between a `null` Message and an Empty String

`null` and `""` are two different values:

- **`null`**: there is no `String` detail message object.
- **`""`**: there is a `String` object, but its length is 0.

In the standard implementation, `Throwable.toString()` checks **`localizedMessage == null`**, not whether the string is empty. Therefore, if the message is `""`, the result still contains `": "` even though no characters follow it.

Save **`EmptyMessageDemo.java`**:

```java
public class EmptyMessageDemo {
    public static void main(String[] args) {
        Throwable noMessage = new IllegalStateException();
        Throwable emptyMessage = new IllegalStateException("");

        System.out.println("Null? "
                + (noMessage.getMessage() == null));
        System.out.println("Empty? "
                + emptyMessage.getMessage().isEmpty());
        System.out.println("Null toString: " + noMessage);
        System.out.println("Empty suffix: "
                + emptyMessage.toString().endsWith(": "));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 EmptyMessageDemo.java
java EmptyMessageDemo
```

**Exact stdout:**

```text
Null? true
Empty? true
Null toString: java.lang.IllegalStateException
Empty suffix: true
```

The last line uses `endsWith(": ")` instead of directly printing a trailing space that is hard to see. That approach accurately confirms `toString()`'s formula for an empty string.

When designing an API, you should distinguish between "no message" and "a message was provided but is empty" if the contract requires it. When displaying to users, both cases usually need a clearly defined fallback.

## 7. Quick Comparison Table

| Question | `getMessage()` | `getLocalizedMessage()` | `toString()` |
| --- | --- | --- | --- |
| Return type | `String` | `String` | `String` |
| Default content | Detail message | Calls `getMessage()` | Class name, optionally plus `": "` and localized message |
| Can it return `null`? | Yes | Yes | In standard `Throwable`, no |
| Automatically includes exception class name? | Not by default | Not by default | Yes |
| Automatically provides stack frames? | No | No | No |
| Automatically includes `getCause()`? | Generally no | Generally no | Generally no |
| Automatically translates by `Locale`? | No | Not by default | No; uses the existing localized message |
| Can it change via subclass override? | Yes | Yes | Yes |
| Best suited for | Technical message per contract | Localized message when supported by the class | Short description to identify the type and message |

This table describes **default behavior**; it does not guarantee that every subclass overriding these three methods preserves the exact same formula. When using an exception from a third-party library, read its API documentation if you need absolute precision about its message.

## 8. True Localization: Overriding `getLocalizedMessage()`

A custom exception class can keep a **stable technical message** via `getMessage()`, while returning a Vietnamese or English message via `getLocalizedMessage()`.

Save as **`LocalizedMessageDemo.java`**. The file contains one `public` class with `main` and one package-private class in the same file:

```java
import java.util.Locale;

class LocalizedProblem extends Exception {
    private final Locale locale;

    LocalizedProblem(Locale locale) {
        super("Missing configuration");
        this.locale = locale;
    }

    @Override
    public String getLocalizedMessage() {
        if ("vi".equals(locale.getLanguage())) {
            return "Thiếu cấu hình";
        }
        return getMessage();
    }
}

public class LocalizedMessageDemo {
    public static void main(String[] args) {
        LocalizedProblem vi =
                new LocalizedProblem(Locale.forLanguageTag("vi-VN"));
        LocalizedProblem en =
                new LocalizedProblem(Locale.ENGLISH);

        System.out.println("VI message: " + vi.getMessage());
        System.out.println("VI localized: " + vi.getLocalizedMessage());
        System.out.println("VI toString: " + vi.toString());
        System.out.println("EN localized: " + en.getLocalizedMessage());
        System.out.println("EN toString: " + en.toString());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 LocalizedMessageDemo.java
java LocalizedMessageDemo
```

**Exact stdout:**

```text
VI message: Missing configuration
VI localized: Thiếu cấu hình
VI toString: LocalizedProblem: Thiếu cấu hình
EN localized: Missing configuration
EN toString: LocalizedProblem: Missing configuration
```

Key takeaways:

- `super("Missing configuration")` sets the technical message of the exception.
- `getMessage()` is not overridden, so it still returns `"Missing configuration"`.
- `getLocalizedMessage()` is overridden and selects a message based on the `Locale` passed to the constructor.
- **`toString()` calls `getLocalizedMessage()` by default**, so the same class can produce a Vietnamese or English description depending on the object.
- `LocalizedProblem` is in the default package, so the class name in the output is `LocalizedProblem`. If placed in the `com.example` package, the default `toString()` would include the package name.

This article uses a simple `if` condition so the output is easy to verify. Real multi-language applications usually need **message keys**, `ResourceBundle` or a translation management system, language fallbacks, and parameterization policies rather than hard-coding strings inside exception classes.

## 9. When Should You Use `ResourceBundle`?

`ResourceBundle` helps look up strings by `Locale` from separately managed resource files. One possible design approach is:

```java
// Illustrates the idea inside a method.
String template = bundle.getString("error.config.missing");
String localized = String.format(locale, template, configName);
```

This is an **illustrative snippet**, assuming `bundle`, `locale`, and `configName` are already defined. No translation files are included, so do not treat this as a standalone runnable program.

Another option is to keep the exception containing only a **stable error code and structured parameters**, and let the presentation layer use `ResourceBundle` to render the message in the user's language. This is useful in a web server handling many requests in different languages: the technical exception does not have to decide the final display language.

Keep in mind:

1. **Do not rely on the global `Locale.getDefault()` for all requests** if each request has its own locale; changing the global locale can cause requests to interfere with one another.
2. If you store `Locale` in the exception, consider which layer creates the exception and who decides the language.
3. User-facing messages should be reviewed for clarity and security, not merely translated.
4. Technical messages in logs and localized messages for the UI may differ intentionally.
5. Do not parse program behavior by matching translated text, because languages and wording can change.

**`getLocalizedMessage()` is a built-in extension point; not every application is required to override it.** If your API separates translation from exceptions, that can still be a good design.

## 10. Inheritance and Overriding: Call Order Matters

According to the standard `Throwable` code:

```text
getMessage()
      ▲
      │ mặc định
getLocalizedMessage()
      ▲
      │ được gọi trong công thức mặc định
toString()
```

This diagram illustrates the **call relationship in the default implementation**, not the class inheritance hierarchy.

Cases:

- **Nothing overridden**: `getLocalizedMessage()` equals `getMessage()`; `toString()` combines the class name with the localized message if it is not `null`.
- **Override `getMessage()` but not `getLocalizedMessage()`**: the default localized message usually reflects the new value from `getMessage()`.
- **Override `getLocalizedMessage()`**: the default `toString()` uses the new localized message, even if it differs from the technical detail message.
- **Override `toString()`**: the string format can change completely; other code should not assume the default formula still applies.
- **Override `getLocalizedMessage()` to return `null`**: the default `toString()` returns only the class name, even when `getMessage()` is not `null`.

You can verify the last case with a custom class, though you should avoid overriding methods just to hide errors without a clear design reason. An exception with a good technical message whose `toString()` omits the message can leave logs missing important information.

An important technical point: `toString()` and `getLocalizedMessage()` may be called from logging code or from code constructing error notifications. Therefore, overrides should be **simple, never throw new errors, and perform no heavy I/O**. If translation fails while diagnosing another exception, the program may lose additional critical information.

## 11. `getCause()` Is Not Automatically Included in `getMessage()`

An exception can **wrap a cause**. That does not mean the outer exception's message automatically combines all messages in the cause chain. For example:

```java
IOException original = new IOException("Không đọc được tệp");
IllegalStateException wrapper =
        new IllegalStateException("Không thể khởi tạo", original);
```

These are illustrative declarations, requiring `import java.io.IOException`. With the `IllegalStateException(String, Throwable)` constructor:

- `wrapper.getMessage()` is `"Không thể khởi tạo"`.
- `wrapper.getCause()` points to `original`.
- `wrapper.toString()` by default is `"java.lang.IllegalStateException: Không thể khởi tạo"`.
- `original.getMessage()` is `"Không đọc được tệp"`.

The wrapper's message and the cause are **two separate pieces of data**. For a complete explanation, inspect `getCause()` or print/collect the structured stack trace. Also, do not wrap errors using `new RuntimeException(e.getMessage())` if your goal is to preserve the cause; that does not pass the original object as the cause.

## 12. Complete Example: Cause and Wrapper Message

Save as **`CauseAndMessageDemo.java`**:

```java
import java.io.IOException;

public class CauseAndMessageDemo {
    public static void main(String[] args) {
        IOException root =
                new IOException("Không đọc được tệp");
        IllegalStateException wrapper =
                new IllegalStateException("Không thể khởi tạo", root);

        System.out.println("Wrapper message: "
                + wrapper.getMessage());
        System.out.println("Wrapper localized: "
                + wrapper.getLocalizedMessage());
        System.out.println("Wrapper toString: "
                + wrapper.toString());
        System.out.println("Cause type: "
                + wrapper.getCause().getClass().getSimpleName());
        System.out.println("Cause message: "
                + wrapper.getCause().getMessage());

        RuntimeException derived = new RuntimeException(root);
        System.out.println("Cause-only constructor: "
                + derived.getMessage().equals(root.toString()));
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CauseAndMessageDemo.java
java CauseAndMessageDemo
```

**Exact stdout:**

```text
Wrapper message: Không thể khởi tạo
Wrapper localized: Không thể khởi tạo
Wrapper toString: java.lang.IllegalStateException: Không thể khởi tạo
Cause type: IOException
Cause message: Không đọc được tệp
Cause-only constructor: true
```

The last line illustrates an **important constructor variant**: `new RuntimeException(root)` uses `root.toString()` as the detail message of the new exception (when the cause is not `null`). Thus, a wrapper's message sometimes **contains the cause's type name and message**, but that is specific constructor behavior, **not** because `getMessage()` automatically traverses all causes.

Comparison:

| Constructor | Wrapper Message |
| --- | --- |
| `new RuntimeException("Tầng dịch vụ thất bại", cause)` | The passed string: `"Tầng dịch vụ thất bại"` |
| `new RuntimeException(cause)` | `cause.toString()`, if `cause` is not `null` |
| `new RuntimeException()` | Usually `null` with the default constructor |
| `new RuntimeException("Tầng dịch vụ thất bại")` | The passed string, with no automatic cause |

When designing an API, it is usually more useful to pass **a message for the current layer along with the cause** via the `(String, Throwable)` constructor: it expresses both the failing operation and preserves the cause object for diagnosis.

## 13. `getSuppressed()` Is a List of Secondary Errors, Not Part of the Message

Since Java 7, `Throwable` can hold **suppressed exceptions**, which commonly occur when an error happens inside a `try-with-resources` body and then `close()` also fails. These errors are not automatically appended to `getMessage()` or `toString()` of the primary exception.

For example, save **`SuppressedMessageDemo.java`**:

```java
public class SuppressedMessageDemo {
    public static void main(String[] args) {
        IllegalStateException main =
                new IllegalStateException("Lỗi xử lý");
        main.addSuppressed(
                new IllegalArgumentException("Lỗi cleanup"));

        System.out.println("Message: " + main.getMessage());
        System.out.println("toString: " + main.toString());
        System.out.println("Số suppressed: "
                + main.getSuppressed().length);
        System.out.println("Suppressed message: "
                + main.getSuppressed()[0].getMessage());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 SuppressedMessageDemo.java
java SuppressedMessageDemo
```

**Exact stdout:**

```text
Message: Lỗi xử lý
toString: java.lang.IllegalStateException: Lỗi xử lý
Số suppressed: 1
Suppressed message: Lỗi cleanup
```

The message `"Lỗi cleanup"` only appears when reading `getSuppressed()[0].getMessage()` directly; `main.getMessage()` and `main.toString()` do not list it automatically. When writing structured logging, do not just store a single `e.toString()` string and assume you have preserved the cause and suppressed exceptions.

The example deliberately adds one suppressed exception so there is exactly one element; real code must check the array length and not assume every exception has suppressed exceptions.

## 14. How Does `toString()` Differ from `printStackTrace()`?

This is a very common point of confusion:

- **`e.getMessage()`**: a detail `String`, possibly `null`.
- **`e.getLocalizedMessage()`**: a localized `String` if supported by the class, possibly `null`.
- **`e.toString()`**: a short descriptive `String` (by default: class name and localized message).
- **`e.printStackTrace()`**: **performs an action to print** the error information and stack trace; the method returns `void` and does not return a string for you to assign.

By default, the no-argument `printStackTrace()` prints to the **standard error stream** (`System.err`), including the exception description line and the stack frames; it can also display cause and suppressed exceptions. Line numbers, paths, formatting, and frame order may vary by environment, build setup, and JVM, so no fixed stdout output is attached to stack trace printing examples.

Example:

```java
try {
    throw new IllegalStateException("Lỗi xử lý");
} catch (IllegalStateException e) {
    System.out.println(e.toString()); // Single line on stdout.
    e.printStackTrace();              // Multiple lines on stderr.
}
```

This is an **illustrative block** that can be placed inside `main`. Because stdout and stderr can be buffered/interleaved by the terminal, the order in which they appear on screen is not a reliable contract for testing when the two streams are separate.

If you need the trace as a string for a special purpose, you can print it into a `StringWriter` via a `PrintWriter`, but modern logging libraries usually let you pass the `Throwable` object directly, which is better than formatting stack traces manually.

## 15. Why Logging Only `getMessage()` Is Usually Not Enough

Suppose two different exception types share the same message `"invalid input"`. If the log only records the message, you do not know whether the error was a `NumberFormatException`, an `IllegalArgumentException`, or a custom application type.

Conversely, logging only `toString()` includes the type name but still **lacks stack frames or cause/suppressed information**. When investigating technical bugs, that data is often more important than a single descriptive line.

Typically, you need:

1. **Exception type** and operation context.
2. **Message** with sufficiently useful content, without exposing sensitive data.
3. **Stack trace** when the error requires diagnosing the call path.
4. **Cause** when exceptions are wrapped across layers.
5. **Suppressed exceptions** if cleanup or multiple resources also failed.
6. **Correlation/request ID or stable error code**, rather than inferring from free-form wording.

Framework example for a logging API that supports `Throwable`:

```java
// Pseudocode, depending on the logging library API in use:
logger.error("Không thể xử lý request {}", requestId, e);
```

This is **pseudocode**, not a standalone runnable Java example. Depending on the library and specific overload, how you pass `Throwable` may differ; read the documentation of the actual logging API you use.

**Do not use the message as a key for business logic**, for example `if (e.getMessage().contains("not found"))`. A change in wording or language will break the logic. Use the exception type, a structured error code, or an explicit business result type instead.

## 16. Using Messages in the User Interface

A message written for developers may not be suitable for direct display to end users. For example:

```java
throw new IllegalStateException(
        "DB_CONN_02: connection pool exhausted, host=db.internal");
```

This is an **illustrative statement**. The message contains system details; passing `e.getMessage()` directly to the UI can leak implementation information. Even `e.getLocalizedMessage()` is not guaranteed to be safe if the class was not designed for the user interface.

The proper design is to separate:

- **Technical information** for observability and debugging: exception type, message, stack trace, cause, suppressed exceptions.
- **Stable error codes** so the application can decide response types, tests, APIs, and support workflows.
- **User messages** authored and localized for the request's or user's locale, after reviewing for security.

Some domain exceptions can carry their own `errorCode` and parameters, rather than forcing the UI to parse `toString()`. When an API needs to return a message to users, prefer a layer that understands locale, permissions, and context rather than exposing raw exception strings by default.

## 17. Special Case: Messages Can Be Generated by the JVM

Not every exception is created with an explicit message constructor in application code. For example, a `NullPointerException` can be thrown by the JVM when the program dereferences `null`.

In modern JVM versions, **some JVM-generated `NullPointerException`s** may include a more detailed diagnostic message (often called *helpful NullPointerExceptions*) to pinpoint which expression was `null`. However, that **depends on the JVM version, configuration, and how the error was created**—it is not a fixed contract for every `NullPointerException`.

Therefore:

- Do not assume that every `NullPointerException` has `getMessage() != null`.
- Do not compare exact JVM message text as a stable "error code".
- Do not rely on variable names or wording in the message to make recovery decisions.
- When you need a specific message for an API precondition, check it explicitly and define your own contract.

An error with a `null` message still has an exception type and a stack trace (depending on how it was created), so other diagnostic methods that do not rely on the message remain valuable.

## 18. Should You Override `toString()`?

You can override `toString()` on a custom exception class because it is inherited from `Object` and `Throwable` provides its own implementation. However, changing the format should have a clear reason:

```java
class TaggedException extends RuntimeException {
    private final String code;

    TaggedException(String code, String message) {
        super(message);
        this.code = code;
    }

    @Override
    public String toString() {
        return code + ": " + getMessage();
    }
}
```

This is an **illustrative class without `main`**. If you create `new TaggedException("E100", "Thiếu cấu hình")`, this class's `toString()` returns `"E100: Thiếu cấu hình"` instead of the runtime class name per `Throwable`'s formula.

Changing `toString()` can omit the class name in logs or stack trace headers; monitoring tools may rely on the standard structure. If the goal is to add an error code, it is usually better to keep the error code in a **field + getter** (`getCode()`) so logging/response systems can use it in a structured way without redefining `toString()` too far from its expected contract.

Similarly, overriding `getLocalizedMessage()` should not perform network I/O or access environments that could fail just to build a diagnostic string. If the formatter throws another exception while handling the original error, observability becomes unreliable.

## 19. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`getMessage()` always returns a string." | It returns type `String`, but **can be `null`**. |
| "`getLocalizedMessage()` automatically translates according to the OS language." | By default, `Throwable` only calls `getMessage()`; a custom override or localization mechanism is required. |
| "`getMessage()` and `toString()` are the same." | By default, `toString()` prepends the runtime class name and uses the localized message. |
| "`toString()` always returns `getMessage()`." | With default `Throwable`, `toString()` uses **`getLocalizedMessage()`**. |
| "`toString()` contains the full stack trace." | No; it is only a short description. |
| "`getMessage()` always contains cause information." | No; the cause is separate data, except in specific constructors/overrides that build the message from the cause. |
| "`getSuppressed()` automatically appears in `toString()`." | No; the suppressed list is separate and is typically displayed by `printStackTrace()`. |
| "`printStackTrace()` returns a String." | No, it returns `void` and prints information to a stream. |
| "A null message means the exception is harmless." | No; the error type and execution path still need to be handled per the contract. |
| "An empty message is the same as a null message to `toString()`." | No. An empty string still causes `toString()` to append `": "`. |
| "You can catch/handle errors by matching message content." | Fragile due to localization, wording, and versions; use exception types or structured error codes. |
| "`getLocalizedMessage()` is definitely safe for end users." | No; the message may contain internal details and may not even be translated. |
| "The class name in `toString()` is always `getSimpleName()`." | The default `Throwable` implementation uses `getClass().getName()`. |
| "A subclass cannot change these results." | Methods can be overridden; check the specific class contract. |

## 20. Practice Scenarios and Answers

**Q1.** What does `new IllegalArgumentException("Sai tham số").getMessage()` return?  
**Answer:** `"Sai tham số"`.

**Q2.** For the same exception above, what does the default `toString()` return?  
**Answer:** `"java.lang.IllegalArgumentException: Sai tham số"`, because the class is in `java.lang` and the default localized message equals the message.

**Q3.** Is `new IllegalArgumentException().getMessage()` always an empty string?  
**Answer:** No. With this class's no-arg constructor, the message is `null`.

**Q4.** With a `null` message, does the default `Throwable.toString()` append `": "`?  
**Answer:** No. It returns only the class name.

**Q5.** With a `""` message, does the default `toString()` append `": "`?  
**Answer:** Yes, because an empty string is **not** `null`.

**Q6.** If a subclass overrides `getLocalizedMessage()` to return `"Không tìm thấy tệp"` without overriding `toString()`, which value does `toString()` use?  
**Answer:** It uses the localized message from that override and the runtime class name; it does not necessarily use the original detail message.

**Q7.** Why does changing `Locale.getDefault()` not make every exception automatically translate its message?  
**Answer:** Because the default `getLocalizedMessage()` implementation only calls `getMessage()`; there is no automatic translation mechanism.

**Q8.** A wrapper has an `IOException` as its cause. Does `getMessage()` automatically print the entire cause?  
**Answer:** Generally no. Constructors taking `(String, Throwable)` usually keep their own message; the cause is accessed via `getCause()`. Some cause-only constructors set the message to `cause.toString()`, but that is constructor-specific behavior.

**Q9.** Does `e.toString()` print `getSuppressed()`?  
**Answer:** Not in the default `Throwable` implementation. Use `getSuppressed()` or a stack trace printing mechanism that supports suppressed exceptions.

**Q10.** Why shouldn't you use `e.getMessage().contains("not found")` to decide which errors can be retried?  
**Answer:** A message is text that can change or be translated, not a stable error code. Use the exception type, an error code, or a return result contract instead.

**Q11.** To log a technical error for investigation, is `getMessage()` alone enough?  
**Answer:** Usually no. Consider the error type, stack trace, cause, and suppressed exceptions, along with appropriate context.

**Q12.** Can `Throwable.getLocalizedMessage()` return `null` when `getMessage()` is not `null`?  
**Answer:** Yes, if a subclass deliberately overrides it to return `null`. In that case, the default `Throwable.toString()` will return only the class name.

**Q13.** If a subclass overrides `toString()`, is the class name + localized message formula still guaranteed to hold?  
**Answer:** No; a subclass can define a different format.

**Q14.** Is `System.out.println(e)` (where `e` is a `Throwable`) the same as `e.printStackTrace()`?  
**Answer:** No. `println(e)` prints a short string representation, whereas `printStackTrace()` prints stack frames, potentially along with cause/suppressed exceptions.

## 21. Checklist When Writing and Using Exception Messages

Before finalizing code that handles `Throwable`, check:

1. **Can it be `null`?** Do not call `e.getMessage().trim()` or `.length()` directly without checking for `null`.
2. **Do you need a technical or localized message?** Do not assume `getLocalizedMessage()` is already translated.
3. **Do you need the error type?** Choose `getClass()` or `toString()` depending on your purpose; avoid parsing the class name from text if possible.
4. **Do you need the root cause?** Use `getCause()` and preserve the cause when wrapping.
5. **Could there be cleanup errors?** Check `getSuppressed()` when appropriate.
6. **Do you need the stack trace?** Use a logger that accepts `Throwable`, or `getStackTrace()`/`printStackTrace()` depending on context.
7. **Does it expose internal data?** Review messages before logging and especially before returning them to the UI.
8. **Are you relying on message text to make decisions?** Switch to structured error codes or exception types.
9. **Does a custom class override `getMessage()`, `getLocalizedMessage()`, or `toString()`?** Verify the interactions among them, especially that `toString()` uses the localized message.
10. **Did you test `null` messages, empty strings, and localized variants?** Small differences like these can break formatters or logs.
11. **Do you need to support multiple locales concurrently?** Avoid relying on the global locale; consider translating at the presentation layer.
12. **Do tests compare stack traces verbatim?** Avoid depending on line numbers and JVM formatting; assert on structured components whenever possible.

## 22. Summary

`getMessage()`, `getLocalizedMessage()`, and `toString()` all return **strings describing an exception**, but they have different contracts:

- **`getMessage()`** is the detail message, which can be `null`.
- **`getLocalizedMessage()`** is an extension point for localized content, calling `getMessage()` by default.
- **`toString()`** by default combines the **runtime class name** with the **localized message** if not `null`, but does **not** include stack frames, cause, or suppressed exceptions.

When you need to diagnose a root cause, do not stop at the string. Inspect the **exception type, `getCause()`, `getSuppressed()`, and the stack trace**. When responding to users, use reviewed messages, stable error codes, and an appropriate localization mechanism. Understanding the differences between these three methods helps you handle errors in a way that is both accurate in Java and practical for maintenance and operations.
