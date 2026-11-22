# Constructors Supporting `message` and `cause` When Designing Custom Exceptions in Java

When creating a custom exception class, extending `Exception` or `RuntimeException` is only the first step. To help callers understand **what failed** and operators trace the **original technical cause**, an exception should provide a constructor that accepts both **message** and **cause**:

```java
public DataLoadException(String message, Throwable cause) {
    super(message, cause);
}
```

The two parameters serve different purposes: `message` explains the error in the context of the **layer reporting the failure**, while `cause` references the **`Throwable` object that caused the operation to fail**. By preserving both, the program can add context at each layer without losing the stack trace, exception type, or suppressed exceptions of the original error.

This article focuses on designing constructors for custom exceptions in Java 17+, common overloads, passing `super(...)`, the difference between `message` and `cause`, checked/unchecked exceptions, `null`, `initCause()`, preserving diagnostics across layers, and common implementation mistakes.

## 1. `message` and `cause` Are Not the Same Thing

`Throwable` provides two fundamental diagnostic properties:

| Property | Read API | Meaning | Example |
| --- | --- | --- | --- |
| *Detail message* | `getMessage()` | Error description of the **current exception object** | `Cannot load customer profile` |
| *Cause* | `getCause()` | The previous exception object that directly contributed to causing the current exception | `IOException("disk unavailable")` |
| Stack trace | `getStackTrace()` / `printStackTrace()` | Trace of where the error information was recorded | Frame in repository/service |
| Suppressed exceptions | `getSuppressed()` | Secondary errors retained, typically occurring when closing resources | `IOException("close failed")` |

Simulated error chain example:

```text
DataLoadException("Cannot load customer profile")   ← service-layer message
    |
    +-- cause: IOException("disk unavailable")      ← cause at the I/O layer
                     |
                     +-- stack trace: file read operation
```

The `IOException` remains **a separate object**: it does not turn into `DataLoadException`. A constructor that accepts `cause` only creates a **causal link**, allowing callers of `getCause()` and stack trace printers to navigate from the business-level error back to the infrastructure error.

**A message does not automatically replace the cause.** Writing `super("Cannot load: " + ex.getMessage())` may give the reader a descriptive sentence, but `getCause()` on the new exception remains `null` and the link to the `ex` object is lost.

## 2. Choosing a Superclass: Checked or Unchecked?

A custom exception typically extends one of two classes:

- **`Exception`** (not extending `RuntimeException`): checked exception. If a method can allow this error to escape, Java generally requires the caller to handle it with `catch` or declare an appropriate `throws` clause.
- **`RuntimeException`**: unchecked exception. Does not require declaring `throws` to compile, but can and usually should still use `cause` to preserve the original error.

Signature examples:

```java
class DataLoadException extends Exception {
    DataLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}

class ServiceFailureException extends RuntimeException {
    ServiceFailureException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

These are two valid illustrative classes without a standalone `main`. Both types have the same constructor, but their **contract with the caller** differs. Do not choose checked or unchecked just to write less `try-catch` code; base the decision on recoverability, the API contract, and the module's design rules.

You should not create an ordinary business exception using `extends Error`. The `Error` hierarchy represents conditions that applications are generally not expected to recover from in the normal way.

## 3. Four Common Constructors of a Custom Exception

An exception can provide four overloads, corresponding to the common ways objects are created in Java:

```java
public class DataLoadException extends Exception {
    public DataLoadException() {
        super();
    }

    public DataLoadException(String message) {
        super(message);
    }

    public DataLoadException(String message, Throwable cause) {
        super(message, cause);
    }

    public DataLoadException(Throwable cause) {
        super(cause);
    }
}
```

This is a **valid class file** if saved as `DataLoadException.java`; it does not contain `main()`. Each overload has a distinct role:

| Constructor | Typical usage | `getMessage()` | `getCause()` |
| --- | --- | --- | --- |
| `DataLoadException()` | Simple error with no detailed context | `null` | `null` |
| `DataLoadException(String message)` | Reporting a new standalone error | The `message` string | `null` |
| `DataLoadException(String message, Throwable cause)` | Translating an exception at a layer boundary, adding context | The exact `message` string passed | The exact `cause` object |
| `DataLoadException(Throwable cause)` | Wrapper that essentially only wraps the cause | `cause == null ? null : cause.toString()` | The exact `cause` object |

All four overloads may not be needed if the API only has one or two clear ways to construct the error. However, when publishing a library for multiple consumers, providing meaningful overloads saves callers from having to attach `cause` late or build messages awkwardly.

**Note:** The `DataLoadException(Throwable cause)` constructor does not create a new business message. By the `Exception(Throwable cause)` contract, the message is derived from `cause.toString()`. If you need to display meaningful context, the `(String, Throwable)` overload is usually preferred.

## 4. Java 17+ Program: Verifying Each Overload Exactly

Save as `ConstructorOverloadsDemo.java`:

```java
import java.io.IOException;

public class ConstructorOverloadsDemo {
    static class DomainException extends Exception {
        DomainException() {
            super();
        }

        DomainException(String message) {
            super(message);
        }

        DomainException(String message, Throwable cause) {
            super(message, cause);
        }

        DomainException(Throwable cause) {
            super(cause);
        }
    }

    public static void main(String[] args) {
        IOException original = new IOException("disk offline");

        DomainException empty = new DomainException();
        DomainException messageOnly =
                new DomainException("cannot load profile");
        DomainException both =
                new DomainException("cannot load profile", original);
        DomainException causeOnly = new DomainException(original);

        System.out.println("emptyMessage=" + empty.getMessage());
        System.out.println("emptyCause=" + empty.getCause());

        System.out.println("messageOnly=" + messageOnly.getMessage());
        System.out.println("messageOnlyCause=" + messageOnly.getCause());

        System.out.println("bothMessage=" + both.getMessage());
        System.out.println("bothCauseIsOriginal="
                + (both.getCause() == original));

        System.out.println("causeOnlyMessage=" + causeOnly.getMessage());
        System.out.println("causeOnlyIsOriginal="
                + (causeOnly.getCause() == original));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 ConstructorOverloadsDemo.java
java ConstructorOverloadsDemo
```

Deterministic output:

```text
emptyMessage=null
emptyCause=null
messageOnly=cannot load profile
messageOnlyCause=null
bothMessage=cannot load profile
bothCauseIsOriginal=true
causeOnlyMessage=java.io.IOException: disk offline
causeOnlyIsOriginal=true
```

In the `(String, Throwable)` form, Java **does not automatically append** the message from `cause` into the wrapper's message. You explicitly decide on a meaningful description at the current layer. In the `(Throwable)` form, the default message is derived from `cause.toString()`, which includes the class name `java.io.IOException` and the cause's message in this example.

The `==` comparison proves that the wrapper holds a reference to **the exact original cause object**, rather than creating a copy of the `IOException`.

## 5. How to Write `super(message, cause)` Correctly

A constructor is where the exception object is initialized and must invoke the superclass constructor according to Java rules. In Java 17, an explicit `super(...)` or `this(...)` constructor invocation must be the first statement in the constructor.

Standard pattern:

```java
public ConfigLoadException(String message, Throwable cause) {
    super(message, cause);
}
```

The snippet above is an **illustrative constructor** of a `ConfigLoadException` class extending `Exception` or `RuntimeException` with a matching overload.

If you want to format the message before passing it to the superclass, you can use an expression in the argument:

```java
public ConfigLoadException(String key, Throwable cause) {
    super("Unable to load config key: " + key, cause);
}
```

In real API design, consider whether `key` might contain sensitive data before including it in messages and logs.

**Do not write**:

```java
public ConfigLoadException(String message, Throwable cause) {
    super(message);
    initCause(cause);
}
```

The code above may be valid in a class extending `Exception` if the cause has not been initialized yet, but it is unnecessarily roundabout: when `super(message, cause)` is available, use it directly. If `initCause` is called again elsewhere, the single-initialization contract for `cause` will be violated.

**In particular, never call both `super(message, cause)` and `initCause(cause)`:** the cause is already initialized by the two-parameter constructor; the additional call throws `IllegalStateException`.

## 6. `null` Cases and Cause Initialization State

There is a subtle distinction between constructors:

- `super(message)` creates an object whose cause is **not yet initialized**. `initCause(...)` may subsequently be called once.
- `super(message, null)` creates an object whose cause **has been initialized to `null`**. `initCause(...)` is **not** allowed to be called afterward.
- `super(cause)` accepts `null` validly, deriving the message as `null` if `cause` is `null`; the cause is still considered initialized.
- `getCause() == null` **does not tell you** whether the cause has been initialized or not.

| Creation form | Initial `getCause()` | Can `initCause(realCause)` be called later? |
| --- | --- | --- |
| `new Exception("message")` | `null` | Yes, once if not already used |
| `new Exception("message", null)` | `null` | No |
| `new Exception((Throwable) null)` | `null` | No |
| `new Exception("message", original)` | `original` | No |

Because both `String` and `Throwable` have single-parameter overloads, `new Exception(null)` can be **ambiguous at compile time**. When you genuinely need to pass `null`, use an explicit cast `(String) null` or `(Throwable) null`, or use the two-parameter constructor such as `new Exception("message", null)` to make the intent clear.

### Java 17+ Program: `null` Does Not Mean "Cause Uninitialized"

Save as `NullCauseConstructorDemo.java`:

```java
public class NullCauseConstructorDemo {
    static class SampleException extends Exception {
        SampleException(String message) {
            super(message);
        }

        SampleException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        SampleException messageOnly = new SampleException("one");
        messageOnly.initCause(new IllegalStateException("original"));
        System.out.println("firstLinked="
                + (messageOnly.getCause() instanceof IllegalStateException));

        SampleException explicitNull =
                new SampleException("two", null);
        System.out.println("nullCause=" + explicitNull.getCause());

        try {
            explicitNull.initCause(new IllegalStateException("late"));
        } catch (IllegalStateException ex) {
            System.out.println("initAgain="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 NullCauseConstructorDemo.java
java NullCauseConstructorDemo
```

Output:

```text
firstLinked=true
nullCause=null
initAgain=IllegalStateException
```

Do not build applications around freely attaching causes across multiple layers later. The clearest pattern is to construct the wrapper with the right message and cause at the moment the error is caught:

```java
throw new DataLoadException("Cannot load profile", original);
```

This is an illustrative snippet where `original` is a `Throwable` and `DataLoadException` has a `(String, Throwable)` constructor.

## 7. Checked Exceptions Across Layers: Putting Context in the Wrapper

Suppose the repository layer encounters an `IOException`, and the service layer wants to expose a checked business exception. A custom class with a `(String, Throwable)` constructor expresses the service-layer failure meaning without forcing callers to depend on infrastructure exceptions.

Save as `CheckedTranslationDemo.java`:

```java
import java.io.IOException;

public class CheckedTranslationDemo {
    static class ProfileLoadException extends Exception {
        ProfileLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository() throws IOException {
        throw new IOException("file read failed");
    }

    static String service() throws ProfileLoadException {
        try {
            return repository();
        } catch (IOException ex) {
            throw new ProfileLoadException(
                    "Could not load user profile", ex);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(service());
        } catch (ProfileLoadException ex) {
            System.out.println("type=" + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("causeMessage=" + ex.getCause().getMessage());
        }
        System.out.println("end");
    }
}
```

```bash
javac -encoding UTF-8 CheckedTranslationDemo.java
java CheckedTranslationDemo
```

Output:

```text
type=ProfileLoadException
message=Could not load user profile
causeType=IOException
causeMessage=file read failed
end
```

Mechanism:

1. `repository()` creates/throws `IOException`.
2. `service()` catches the infrastructure error and **creates a new object** `ProfileLoadException` with a business message.
3. The `super(message, cause)` constructor preserves `IOException` as the wrapper's cause.
4. Because `ProfileLoadException extends Exception`, `service()` declares `throws ProfileLoadException`. The `main()` layer catches that type.
5. `main()` can continue after `catch` because the error has been handled at the appropriate boundary.

**Not every layer should wrap the exception again.** If an intermediate layer adds no new context, propagating the existing exception can be better than creating multiple redundant wrapper layers.

## 8. Custom Unchecked Exceptions Also Need a Cause Constructor

Unchecked exceptions do not require `throws` at the call site, but preserving the cause is still very important. A configuration or service-state error may need to be represented by a domain-specific unchecked exception rather than exposing `IOException` to the business layer.

Save as `UncheckedTranslationDemo.java`:

```java
import java.io.IOException;

public class UncheckedTranslationDemo {
    static class ConfigurationFailure extends RuntimeException {
        ConfigurationFailure(String message) {
            super(message);
        }

        ConfigurationFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String loadConfig() throws IOException {
        throw new IOException("permission denied");
    }

    static String initializeService() {
        try {
            return loadConfig();
        } catch (IOException ex) {
            throw new ConfigurationFailure(
                    "Service configuration unavailable", ex);
        }
    }

    public static void main(String[] args) {
        try {
            initializeService();
        } catch (ConfigurationFailure ex) {
            System.out.println("unchecked="
                    + (ex instanceof RuntimeException));
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeIsIo="
                    + (ex.getCause() instanceof IOException));
        }
    }
}
```

```bash
javac -encoding UTF-8 UncheckedTranslationDemo.java
java UncheckedTranslationDemo
```

Output:

```text
unchecked=true
message=Service configuration unavailable
causeIsIo=true
```

`initializeService()` does not need `throws ConfigurationFailure` because it is an unchecked exception. This **does not mean** the exception cannot cause the program to terminate abruptly. Without a matching `catch`, it continues propagating according to Java's exception mechanism.

Choose unchecked only if the module contract genuinely intends to represent an error that callers are not forced to handle everywhere; do not automatically wrap every checked exception into an unchecked one just to bypass compiler rules.

## 9. `cause` Is a Reference to the Original Object, Not a Copy

When calling:

```java
IOException original = new IOException("disk offline");
DataLoadException wrapper =
        new DataLoadException("Cannot load profile", original);
```

the `wrapper.getCause()` object is **the exact `original` instance**. Java does not copy the message, stack trace, and suppressed exceptions into another `IOException` when using the `(String, Throwable)` constructor.

Consequences:

- `wrapper.getMessage()` describes the error at the wrapper layer; it is not the original error's message.
- `wrapper.getCause().getMessage()` describes the original error, if `getCause()` is non-`null`.
- `wrapper.getStackTrace()` typically records where the wrapper was created.
- `wrapper.getCause().getStackTrace()` typically records where the cause object was created or where its trace was updated.
- The cause's suppressed list **remains attached to the cause**, and is not automatically moved to the wrapper.

### Java 17+ Program: Preserving Suppressed Exceptions When Wrapping

Save as `SuppressedCauseDemo.java`:

```java
import java.io.IOException;

public class SuppressedCauseDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class DataLoadException extends Exception {
        DataLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws DataLoadException {
        try {
            repository();
        } catch (IOException ex) {
            throw new DataLoadException("Data access failed", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (DataLoadException ex) {
            Throwable cause = ex.getCause();

            System.out.println("wrapper=" + ex.getMessage());
            System.out.println("wrapperSuppressed="
                    + ex.getSuppressed().length);
            System.out.println("cause=" + cause.getMessage());
            System.out.println("causeSuppressed="
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedCauseDemo.java
java SuppressedCauseDemo
```

Output:

```text
wrapper=Data access failed
wrapperSuppressed=0
cause=read failed
causeSuppressed=close failed
```

The error from the `try` body is the primary `IOException`; the `close()` error is suppressed onto that same object. When the service creates `DataLoadException(..., ex)`, the wrapper **does not automatically copy** the cause's suppressed array. However, because the cause is preserved, the secondary error can still be accessed via `ex.getCause().getSuppressed()`.

When logging, pass the entire `Throwable` object to the logger so tools can print the message, trace, cause, and suppressed exceptions, rather than logging only `getMessage()` and losing these relationships.

## 10. Why You Shouldn't Only Accept `String message` and Concatenate the Original Error

A common pattern that loses information:

```java
catch (IOException ex) {
    throw new DataLoadException(
            "Unable to load: " + ex.getMessage());
}
```

This is an **illustrative snippet**, assuming `DataLoadException(String)` exists. Readers see descriptive text, but `getCause()` is `null` and there is no programmatic link left to `ex`.

Recommended approach:

```java
catch (IOException ex) {
    throw new DataLoadException(
            "Unable to load customer profile", ex);
}
```

The original exception still exists as the cause; if you genuinely want to include `ex`'s message in the human-readable description, you can, but consider log duplication and sensitive data.

Guidelines for messages:

- **Describe context at the current layer**: which operation failed and which domain object was affected.
- **Do not expose secrets**: avoid passwords, tokens, connection strings, or sensitive identifiers.
- **Do not replace the cause with the message**: the cause preserves the type, stack trace, and root-cause details.
- **Keep messages semantically stable** for log reading, but do not require business code to parse message text to determine error codes.

If callers must make decisions based on the error kind, provide a dedicated exception type, an error-code enum, or appropriately typed properties instead of trying to parse a `getMessage()` string.

## 11. `getMessage()` Differs from `toString()` and `printStackTrace()`

Do not confuse the diagnostic APIs:

| API | Main information |
| --- | --- |
| `getMessage()` | Only the detail message of the current object, may be `null` |
| `toString()` | Typically the exception class name and detail message if present |
| `getCause()` | The cause object or `null` |
| `printStackTrace()` | Diagnostic representation including the error object, frames, cause chain, and suppressed exceptions when present |
| `getSuppressed()` | Array of secondary exceptions belonging to that object itself |

A small comparison program, saved as `MessageDisplayDemo.java`:

```java
import java.io.IOException;

public class MessageDisplayDemo {
    static class ImportFailure extends Exception {
        ImportFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        IOException original = new IOException("invalid bytes");
        ImportFailure wrapper =
                new ImportFailure("Cannot import document", original);

        System.out.println("message=" + wrapper.getMessage());
        System.out.println("simpleType="
                + wrapper.getClass().getSimpleName());
        System.out.println("causeMessage="
                + wrapper.getCause().getMessage());
        System.out.println("causeType="
                + wrapper.getCause().getClass().getSimpleName());
    }
}
```

```bash
javac -encoding UTF-8 MessageDisplayDemo.java
java MessageDisplayDemo
```

Output:

```text
message=Cannot import document
simpleType=ImportFailure
causeMessage=invalid bytes
causeType=IOException
```

The example avoids comparing `printStackTrace()` verbatim because source line numbers, file names, and frame counts depend on where the code is compiled and run. Instead, it checks deterministic properties guaranteed by the API. If you need to print an actual trace, call `wrapper.printStackTrace()` where appropriate and remember that the no-arg overload writes to `System.err`.

## 12. Constructors with Business Fields: Storing Extra Data Without Dropping the Cause

Sometimes a message is not enough for handling code: for example, an exception may need to carry `resourceName` or `errorCode`. You can add immutable fields, while the constructor still passes `cause` to the superclass.

```java
public final class RecordValidationException extends Exception {
    private final String field;

    public RecordValidationException(
            String field, String message, Throwable cause) {
        super(message, cause);
        this.field = field;
    }

    public String getField() {
        return field;
    }
}
```

This is a **valid class** if saved in `RecordValidationException.java`; it has no `main()`. Callers can access:

```java
RecordValidationException failure =
        new RecordValidationException(
                "email", "Email validation failed", original);

System.out.println(failure.getField());
System.out.println(failure.getCause() == original);
```

This is an illustrative usage snippet where `original` is already defined as a `Throwable` in scope. Both the typed property and the cause are preserved separately.

If the error is simply due to invalid input, there may be no cause; there is no need to fabricate a dummy `Throwable` to fill it in. In that case, passing `null` to the `(String, Throwable)` overload is valid, or you can provide a `(String)` overload if the contract calls for it.

**A message should not be the sole data source** for decisions such as retries, HTTP status codes, failing fields, or remediation types. Values used in logic should be exposed through stable typed fields.

## 13. Mistakes in Constructor Chaining

You can use `this(...)` to reduce code duplication, but you must understand which constructor it selects.

Example:

```java
class ValidationFailure extends Exception {
    ValidationFailure(String message) {
        this(message, null);
    }

    ValidationFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is **valid code**. However, it is **not completely identical** to `ValidationFailure(String message) { super(message); }` with respect to cause state:

- With `this(message, null)`, the two-parameter constructor runs `super(message, null)` and **initializes the cause to `null`**.
- With `super(message)`, the cause is not yet initialized and `initCause(...)` may be called once afterward.

If the class is designed so that every cause must be decided at object creation time, calling `this(message, null)` can be an intentional choice. If you want to preserve the standard `Exception(String)` constructor semantics, write `super(message)` directly.

**Avoid calling both `super(...)` and `this(...)` in the same constructor**: syntactically, each constructor may have only one explicit constructor invocation. You cannot call both like ordinary methods.

### Example Error from Calling `initCause` After Using a Cause Constructor

```java
class WrongFailure extends Exception {
    WrongFailure(String message, Throwable cause) {
        super(message, cause);
        initCause(cause); // Reaching this line will throw IllegalStateException.
    }
}
```

This is **code that compiles but fails at runtime in the constructor**. Reason: `super(message, cause)` already initialized the cause; `initCause` does not allow a second initialization. Fix it by **removing `initCause(cause)`**.

Writing `super(message)` followed by `initCause(cause)` may work the first time, but it is verbose and easy to modify incorrectly; when the two-parameter overload exists, there is no clear advantage over `super(message, cause)`.

## 14. Several Limits to Check During Implementation

### 14.1. A Cause Cannot Be the Wrapper Object Itself

An exception cannot use itself as its cause via `initCause(this)`. This is rejected with `IllegalArgumentException`. When writing a constructor that takes `Throwable cause`, pass **an original exception object distinct from the wrapper being created**, and do not attempt to self-link the object to itself to retain a stack trace.

In practice, a normal `cause` parameter passed from `catch (Exception ex)` into `new DomainException(..., ex)` is a different object, so it is valid.

### 14.2. The Cause Can Be `null`

`super(message, null)` is valid: it means no cause is known or no specific exception caused the failure. However, it still initializes the cause **once**. Do not use `getCause() == null` to conclude that `initCause(...)` can be called again.

### 14.3. Do Not Create Cause Cycles or Meaningless Chains

Do not use `cause` to store a completely unrelated exception, or create reference cycles across multiple objects. Doing so makes stack traces hard to read and breaks the meaning of "caused this error". Secondary errors occurring during cleanup should be represented as suppressed exceptions in appropriate contexts rather than forcing everything into `cause`.

### 14.4. Do Not Disable Stack Traces Automatically

`Exception` and `RuntimeException` provide extended protected constructors supporting `enableSuppression` and `writableStackTrace`. These are advanced tools. Disabling stack traces or suppression can reduce critical diagnostic information; they should not be treated as the default for custom exceptions.

### 14.5. `serialVersionUID` Is a Separate Concern

Java exceptions extend `Throwable` and can participate in Java serialization. If a custom exception is part of a long-term serialization contract, consider `serialVersionUID` and version compatibility. However, this is a serialization design concern, **not a prerequisite for the `(String, Throwable)` constructor to work**.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Only writing `MyException(String message)` when the original cause must be propagated. | Cause is lost when translating errors. | Add `MyException(String, Throwable)` and call `super(message, cause)`. |
| Wrapping an error with `new MyException(ex.getMessage())`. | Only copies text, losing the link to `ex`. | Pass `ex` as `cause`. |
| Writing `super(cause)` even when a message for the current layer's context is needed. | Message is only `cause.toString()`. | Use `super("Context...", cause)`. |
| Calling `initCause()` after `super(message, cause)`. | `IllegalStateException` at runtime. | Do not call `initCause` again. |
| Treating `getCause() == null` as "cause has never been initialized". | May fail on a second initialization attempt. | Decide the cause in the constructor. |
| Using `new MyException(null)` when both `String` and `Throwable` overloads exist. | Ambiguous at compile time. | Use a cast or the explicit two-parameter overload. |
| Throwing `new MyException("failure", null)` in all cases even when an original exception exists. | The real cause is discarded. | Only use `null` when there is no appropriate cause. |
| Wrapping across multiple layers without adding new information. | Long chains, hard-to-read logs. | Only translate types when crossing a meaningful contract boundary. |
| Putting tokens, passwords, or sensitive information into the message. | Risk of leakage through logs/traces. | Keep messages contextual without secrets. |
| Checking only `getMessage()`, ignoring `cause` and `suppressed`. | Misses the technical root cause and close errors. | Log the `Throwable` object and inspect the chain when needed. |
| Using a checked exception but forgetting `throws` in the calling layer. | Fails to compile. | Declare an appropriate `throws` or handle it in `catch`. |
| Using unchecked for every error just to avoid declarations. | Error contract becomes unclear. | Choose checked/unchecked based on how callers handle it. |
| Defining a constructor with a different name from the class or adding a return type. | Not a valid constructor. | Constructor matches the class name and has no return type. |

## 16. Process for Designing a Custom Exception with Message and Cause

When building a new class, you can follow these steps:

1. **Define the error's meaning:** what event in the module should the error represent? Is an existing standard exception already suitable?
2. **Choose checked/unchecked:** is the caller expected to recover, and does the API need to enforce handling at compile time?
3. **Choose the necessary overloads:** at minimum `(String, Throwable)` if translating errors; add `(String)` if there are standalone errors without a cause.
4. **Call the right superclass constructor:** `super(message, cause)`, `super(message)`, or `super(cause)` respectively.
5. **Preserve context:** craft a message expressing the **operation at the current layer** rather than merely repeating the cause's message.
6. **Preserve the cause object:** pass the caught exception directly rather than creating a copy or substituting a string.
7. **Check `null`:** should a missing cause be allowed? If so, only pass `null` when there truly is no underlying error.
8. **Check the contract:** are checked exceptions properly declared with `throws` or handled with `catch`? Do overrides/interface implementations widen checked exceptions?
9. **Check diagnostics:** when logged, are the cause chain and suppressed exceptions of the original error still visible?
10. **Review information scope:** does the message expose sensitive data or make operations harder?

A small, transparent design is usually better than many constructors with inconsistent custom behavior. Only add business fields, error codes, or handling logic when there is a genuine need.

## 17. Self-Check

**Q1.** Why is `super(message, cause)` better than `super(message + cause.getMessage())` when translating exceptions?  
Because the first **preserves the cause object** along with its stack trace and supplementary details; the second only concatenates strings, loses the link, and risks an NPE if `cause` is `null`.

**Q2.** What message does the constructor `MyException(Throwable cause) { super(cause); }` produce?  
Typically `cause.toString()`, or `null` if `cause` is `null`, according to the superclass contract.

**Q3.** Is `new Exception("failed", null)` valid?  
**Yes.** A `null` cause is allowed and is considered initialized.

**Q4.** After `super(message, null)`, can you call `initCause(realCause)`?  
**No.** The cause has already been initialized by the two-parameter constructor.

**Q5.** Both `MyException(String)` and `MyException(Throwable)` constructors exist; will `new MyException(null)` always compile?  
**No.** The call can be ambiguous because `null` matches both `String` and `Throwable`, and the two types have no direct inheritance relationship.

**Q6.** Can a custom exception extending `RuntimeException` use a constructor that accepts a cause?  
**Yes.** The checked/unchecked distinction does not remove the chaining mechanism.

**Q7.** When a wrapper has a cause, are the cause's suppressed exceptions automatically copied onto the wrapper?  
**No.** They remain on the cause object; they can be read via `wrapper.getCause().getSuppressed()` when `cause` is non-`null`.

**Q8.** Why shouldn't you catch every exception and create `new MyException("error")` at every layer?  
Because it can lose the cause, repeat wrappers pointlessly, obscure responsibility boundaries, and make diagnostics harder.

**Q9.** Is a custom exception required to provide all four overloads?  
**No.** Only the overloads used by the contract are needed; `(String, Throwable)` is especially useful when translating errors.

**Q10.** Is an exception with a complete cause enough to guarantee safe, readable logs?  
**Not yet.** You still need contextual messages, control over sensitive information, and full chain rendering at the appropriate logging layer.

## Standard References

- [Java SE 21 API — `Throwable`: message, cause, `initCause()`, and stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html).
- [Java SE 21 API — `Exception`: constructors, `Exception(Throwable)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Exception.html).
- [Java SE 21 API — `RuntimeException`: constructors, checked/unchecked](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/RuntimeException.html).
- [JLS Java SE 21 — §11.1.1: Checked and Unchecked Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).
- [JLS Java SE 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).
- [JLS Java SE 21 — §8.8.7: Constructor Body](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.8.7).

**Key takeaway:** A good custom exception constructor does more than create a line of message: it preserves the cause with `super(message, cause)`, retains the original error information for tracing, and helps each layer express its own context. Choose overloads according to the API contract, handle `null` explicitly, and avoid losing the cause by copying only text.
