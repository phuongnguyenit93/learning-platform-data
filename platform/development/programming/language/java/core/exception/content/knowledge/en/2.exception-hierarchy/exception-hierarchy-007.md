# Parent Type, Child Type Relationships, and `catch` Selection in Java

When an exception is thrown, Java does not find a `catch` block by comparing **the exception name in the message**. The JVM evaluates **the actual runtime type of the exception object** and its inheritance relationship with the type declared in each `catch` branch. A branch that catches a parent type can also catch exceptions of its child types. Therefore, the `catch` order, the `try` scope, and the handling layer determine how an error is handled.

This lesson focuses on three questions:

1. Which exceptions are **parent/child** types in Java's type system?
2. If the same error matches multiple `catch` types, **which branch does Java choose**?
3. When designing APIs and organizing handling layers, should you catch a **specific type** or a **general type**?

## 1. Exception Hierarchy You Need to Know

Exceptions and serious errors in Java all belong to the `java.lang.Throwable` hierarchy. An important part of the tree:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    │   ├── AssertionError
    │   ├── LinkageError
    │   └── VirtualMachineError
    │       └── OutOfMemoryError
    └── java.lang.Exception
        ├── java.io.IOException
        │   ├── java.io.FileNotFoundException
        │   └── java.io.EOFException
        ├── java.sql.SQLException
        ├── java.lang.InterruptedException
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            ├── java.lang.NullPointerException
            └── java.lang.IndexOutOfBoundsException
                └── java.lang.ArrayIndexOutOfBoundsException
```

This is **a part of the tree**, not every exception type in Java. From the diagram:

- `Throwable` is the common parent type; `Exception` and `Error` are two separate child branches.
- `IOException` is the parent of `FileNotFoundException`; a handler declaring `IOException` can catch `FileNotFoundException`.
- `IllegalArgumentException` is the parent of `NumberFormatException`; a handler declaring `IllegalArgumentException` can catch `NumberFormatException`.
- `Exception` is an indirect parent of `RuntimeException`, but **is not the parent of `Error`**.
- `RuntimeException` and its subclasses are generally **unchecked exceptions**. `Error` and its subclasses are also unchecked according to Java's rules, but they should not be treated as normal business errors to catch and recover from.
- Exception classes that belong to `Exception` but **do not** belong to `RuntimeException`, such as `IOException`, are **checked exceptions**: the compiler usually forces calling code to either `catch` them or declare `throws`.

This parent/child relationship is a **class inheritance (`extends`)** relationship, not based on similar names. For example, `NumberFormatException` extends `IllegalArgumentException`, even though the two names appear to describe different causes.

## 2. Type-Matching Rule: `catch (Parent ex)` Catches Child Objects

Suppose at runtime there is an object:

```java
NumberFormatException ex = new NumberFormatException("abc");
```

That object is simultaneously compatible with the reference types `NumberFormatException`, `IllegalArgumentException`, `RuntimeException`, `Exception`, `Throwable`, and `Object`. In a `catch` clause, the parameter type must be `Throwable` or one of its subclasses, so you cannot write `catch (Object ex)`.

If a `try` block contains:

```java
try {
    Integer.parseInt("abc");
} catch (IllegalArgumentException ex) {
    System.out.println("Bắt bằng kiểu cha");
}
```

then the program prints:

```text
Bắt bằng kiểu cha
```

`Integer.parseInt("abc")` throws `NumberFormatException`, and `NumberFormatException` **is an** `IllegalArgumentException`. Therefore, the branch declaring the parent type matches. These snippets are examples that can be placed inside a method body, not standalone program files.

This relationship can be expressed as follows:

- When the exception object is a **child** of the `catch` type, the handler can catch it.
- When the `catch` type is a **child** of the thrown parent-type exception object, that handler **does not** catch the parent object just because they belong to the same family.
- When two types lie on **two branches with no inheritance relationship between them**, a handler for one type does not automatically catch the other. For example, `IOException` does not catch `NumberFormatException`.

**The runtime type is what determines the match when thrown:** even if a reference has a declared type of `Exception`, if the actual object is `NumberFormatException`, the most appropriate handler in a valid `catch` chain is still a handler capable of catching `NumberFormatException`.

## 3. Order of `catch` Branches: Specific First, General Later

An exception can be compatible with multiple types—for example, `FileNotFoundException` is also an `IOException` and an `Exception`. However, when multiple `catch` branches apply to **the same `try` block**, Java evaluates them **in top-to-bottom order**. The first matching branch is the one that handles it. Therefore:

```java
try {
    // May throw FileNotFoundException or another IOException.
} catch (java.io.FileNotFoundException ex) {
    // Handle the file-not-found case specifically.
} catch (java.io.IOException ex) {
    // Handle the remaining IOExceptions.
}
```

This is an illustrative structure (the `try` part needs an actual I/O operation to take effect).

If reversed:

```java
try {
    // May throw IOException.
} catch (java.io.IOException ex) {
    // Also catches FileNotFoundException.
} catch (java.io.FileNotFoundException ex) {
    // Unreachable: compile error.
}
```

The snippet above **intentionally does not compile**: `FileNotFoundException` is already completely covered by the preceding `IOException` handler. The same happens when placing `catch (IllegalArgumentException)` before `catch (NumberFormatException)`.

**Practical rule:** within the same `catch` chain, place child exception classes before parent classes. Sibling branches that do not inherit from each other, such as `NumberFormatException` and another subclass of `IllegalArgumentException`, do not require a specific relative order due to inheritance; order them for readability.

The `catch` order is not an automatic competition to find the "most specific" type. Java ensures you do not place a shadowed handler later, and then executes handlers in the order they are written.

## 4. Runnable Java 17+ Example: Choosing the Right Branch by Hierarchy

Save the following complete program as **`CatchHierarchyDemo.java`**.

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchHierarchyDemo {

    // Business exception is a subclass of IllegalArgumentException.
    static class InvalidQuantityException extends IllegalArgumentException {
        InvalidQuantityException(String message) {
            super(message);
        }
    }

    static void execute(String scenario) throws IOException {
        switch (scenario) {
            case "quantity" ->
                    throw new InvalidQuantityException("quantity <= 0");
            case "format" ->
                    throw new NumberFormatException("abc");
            case "argument" ->
                    throw new IllegalArgumentException("invalid argument");
            case "file" ->
                    throw new FileNotFoundException("config.txt");
            case "io" ->
                    throw new IOException("broken stream");
            default ->
                    System.out.println("execute: OK");
        }
    }

    static void handle(String scenario) {
        System.out.println("CASE " + scenario);
        try {
            execute(scenario);
            System.out.println("after execute");
        } catch (InvalidQuantityException ex) {
            System.out.println("catch InvalidQuantityException: "
                    + ex.getMessage());
        } catch (NumberFormatException ex) {
            System.out.println("catch NumberFormatException: "
                    + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println("catch IllegalArgumentException: "
                    + ex.getMessage());
        } catch (FileNotFoundException ex) {
            System.out.println("catch FileNotFoundException: "
                    + ex.getMessage());
        } catch (IOException ex) {
            System.out.println("catch IOException: "
                    + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
    }

    public static void main(String[] args) {
        for (String scenario : new String[] {
                "ok", "quantity", "format", "argument", "file", "io"
        }) {
            handle(scenario);
        }
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 CatchHierarchyDemo.java
java CatchHierarchyDemo
```

**Exact stdout**:

```text
CASE ok
execute: OK
after execute
finally
CASE quantity
catch InvalidQuantityException: quantity <= 0
finally
CASE format
catch NumberFormatException: abc
finally
CASE argument
catch IllegalArgumentException: invalid argument
finally
CASE file
catch FileNotFoundException: config.txt
finally
CASE io
catch IOException: broken stream
finally
```

### Reading the Results by Inheritance Relationship

| Scenario | Thrown object type | Parent types that could also catch it | Actual `catch` selected |
| --- | --- | --- | --- |
| `ok` | No exception | Not applicable | None; runs `after execute` |
| `quantity` | `InvalidQuantityException` | `IllegalArgumentException`, `RuntimeException`, `Exception` | `InvalidQuantityException` |
| `format` | `NumberFormatException` | `IllegalArgumentException`, `RuntimeException`, `Exception` | `NumberFormatException` |
| `argument` | `IllegalArgumentException` | `RuntimeException`, `Exception` | `IllegalArgumentException` |
| `file` | `FileNotFoundException` | `IOException`, `Exception` | `FileNotFoundException` |
| `io` | `IOException` | `Exception`, `Throwable` | `IOException` |

Important notes:

1. For `quantity`, `InvalidQuantityException` extends `IllegalArgumentException`; if you remove the `catch (InvalidQuantityException)` branch, the `catch (IllegalArgumentException)` branch will handle that error.
2. For `format`, `NumberFormatException` also extends `IllegalArgumentException`, but is handled separately because the child handler comes first.
3. For `file`, `FileNotFoundException` is a specialized `IOException`. A separate handler can display a "file not found" message; the `IOException` handler after it is for other I/O errors.
4. For `io`, the `FileNotFoundException` handler **cannot** catch a plain `IOException` object just because they belong to the same inheritance tree.
5. `finally` runs after every scenario in this program. When an exception occurs, the `after execute` line does not run because the `execute` call did not complete normally.

The program intentionally `throw`s exceptions so that the output does not depend on real files, the operating system, or internal JDK message formatting.

## 5. Handler Lookup Order: Innermost `try` Block First, Then Caller

The type hierarchy is only half of the rule. The JVM first looks at **the handler active at the throw site**. If there are nested `try-catch` blocks, a broad handler in the inner block can handle the error **before** a specific handler in the outer block sees it.

Illustrative example, placed inside a method body:

```java
try {
    try {
        throw new NumberFormatException("x");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner: IllegalArgumentException");
    }
} catch (NumberFormatException ex) {
    System.out.println("outer: NumberFormatException");
}
```

Output:

```text
inner: IllegalArgumentException
```

Even though the outer `catch` has a more specific type, the exception was already caught by **the inner handler** and was not rethrown. The JVM does not skip an inner handler to search for a child-type handler in an outer layer. This also means an overly broad `catch (Exception)` in a lower layer can hide the opportunity for specialized handling in the caller.

If you change the inner `catch` block to `catch (IllegalArgumentException ex) { throw ex; }`, the exception continues propagating outward. Then, the outer block's `NumberFormatException` handler can catch the original object. In this case, no new exception object is created; `throw ex` is a rethrow operation.

### View from the Call Stack

```text
main()
  └─ controller()
       └─ service()
            └─ repository()
                 └─ throw FileNotFoundException
                      ↓
            service(): no catch
                      ↓
       controller(): catch(IOException)
                      ↓
                 handle and stop propagation
```

The `IOException` handler in the controller can catch `FileNotFoundException` because of the parent/child relationship. If `service` had already caught it with `catch (Exception)` and did not rethrow it, `controller` would not receive the exception, even if `controller` has a handler for `FileNotFoundException`.

## 6. Difference Between Catching `Exception`, `RuntimeException`, and `Throwable`

The following branches have very different coverage:

| Handler | Can catch | Does not catch |
| --- | --- | --- |
| `catch (NumberFormatException ex)` | `NumberFormatException` and its subclasses, if any | Plain `IllegalArgumentException`, `IOException` |
| `catch (IllegalArgumentException ex)` | `IllegalArgumentException` and its subclasses, including `NumberFormatException` | `IOException`, `IllegalStateException` |
| `catch (RuntimeException ex)` | Exceptions belonging to `RuntimeException` | `IOException` and other checked exceptions; `Error` |
| `catch (IOException ex)` | `IOException` and its subclasses such as `FileNotFoundException` | `RuntimeException`, `Error` |
| `catch (Exception ex)` | Checked exceptions belonging to `Exception` as well as `RuntimeException`s | `Error` types |
| `catch (Throwable ex)` | Both `Exception` and `Error` and every subclass of `Throwable` | No `Throwable` object is outside this type's scope |

**You should not catch `Throwable` by default** in business processing flows. It can catch `OutOfMemoryError` and `LinkageError`—conditions under which the application may no longer be in a safe state to continue. `catch (Exception)` is sometimes useful at a task boundary to log errors, but in lower layers it is usually too broad and risks masking programming bugs.

It is also important to distinguish:

- `catch (RuntimeException)` **does not** catch `IOException` just because both are thrown with `throw`.
- `catch (Exception)` **does** catch `NullPointerException` because `NullPointerException` is a descendant of `RuntimeException` → `Exception`.
- `catch (Exception)` **does not** catch `OutOfMemoryError`; `Error` does not extend `Exception`.
- Runtime exceptions caused by programming errors can propagate without a `throws` declaration, but that does not strip them of their inheritance relationships.

## 7. Multi-catch: Catching Multiple Sibling Types in One Handler

Since Java 7, you can use `|` when multiple exceptions need the same handling:

```java
try {
    // Operation that may throw IOException or NumberFormatException.
} catch (java.io.IOException | NumberFormatException ex) {
    System.out.println("Không hoàn thành thao tác: "
            + ex.getClass().getSimpleName());
}
```

This is an illustrative structure; the `try` part needs appropriate calls. The branches in a multi-catch must **not have a parent/child relationship with each other**, to avoid one type being shadowed by the other:

```java
// Wrong — intentionally does not compile:
catch (NumberFormatException | IllegalArgumentException ex) {
    // NumberFormatException is already an IllegalArgumentException.
}
```

The same reason applies when writing:

```java
// Wrong — intentionally does not compile:
catch (java.io.IOException | java.io.FileNotFoundException ex) {
    // FileNotFoundException is already an IOException.
}
```

In a multi-catch, the variable `ex` is **implicitly final** and cannot be reassigned to another exception. The static type used for operations on `ex` is inferred from the alternative types and their compatible type relationships; therefore, you should not assume you can call a method specific to only one branch without a type check.

Multi-catch is appropriate when multiple causes have **genuinely the same response**. If a number input error requires asking the user to fix it while a file error requires reporting an operational failure, use separate handlers.

## 8. How Do Checked and Unchecked Exceptions Affect `catch`?

The inheritance hierarchy and compile-time exception checking rules are related, but not identical.

### Checked Exceptions

For example, `IOException` and `FileNotFoundException` are checked exceptions. If a method calls an API that can throw `IOException`, it must catch or declare an appropriate type:

```java
static String load(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
```

This illustrative method is not standalone; the snippet does not depend on the presence of a specific file. The caller can do:

```java
try {
    String text = load(path);
    // Use text when reading succeeds.
} catch (java.io.IOException ex) {
    // Handle I/O errors and any subclasses thrown from load.
}
```

This call site needs to be in a scope that has a `path` variable of type `java.nio.file.Path`. `catch (IOException)` is sufficient for `FileNotFoundException` and subclasses of `IOException`. There is no need to `catch` every individual subclass just to satisfy the compiler.

### Unchecked Exceptions

`NumberFormatException`, `IllegalArgumentException`, and `IllegalStateException` are unchecked exceptions. A call can throw them without the calling method catching or declaring them. **If you want to handle them specifically, the parent/child rules for selecting a handler still apply identically.**

An API design is not necessarily better when every error is converted to `RuntimeException`. The checked/unchecked decision should be based on the API contract, recoverability, and how layers use errors—not merely to reduce the number of `throws` clauses.

### On Catching and Rethrowing

A `catch` block can rethrow the same object using `throw ex;` or wrap it in an appropriate exception type. For checked exceptions, the method signature must still satisfy the compiler's rules. In some cases, Java performs precise type analysis when rethrowing an unassigned `catch` variable (*precise rethrow*), but you should not rely on assuming every `catch (Exception ex) { throw ex; }` can arbitrarily declare a narrow checked type.

## 9. Creating Custom Exceptions: Choosing the Right Parent Type

When an application has a distinct error type that callers need to distinguish, you can create an exception extending an existing class:

```java
public class InvalidOrderException extends IllegalArgumentException {
    public InvalidOrderException(String message) {
        super(message);
    }

    public InvalidOrderException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is **a standalone class** if saved as `InvalidOrderException.java`; to use it in another program, place it in the same package or import it appropriately. Extending `IllegalArgumentException` makes sense if the error indicates that a call's argument is invalid. An internal state error (for example, submitting an order before it is initialized) may fit `IllegalStateException` better; an I/O error may fit `IOException` or its subclass.

Design decisions:

1. **Choose the parent by semantics:** do not extend `IllegalArgumentException` just to avoid a checked exception if the failure is inherently an external environment error.
2. **Preserve the root cause:** a constructor accepting `Throwable cause` helps preserve the original cause when translating exception types. Do not add constructors purely out of habit if the application does not use them.
3. **Leverage polymorphism:** a `catch (IllegalArgumentException)` handler automatically catches `InvalidOrderException`. If specific handling is needed, place `catch (InvalidOrderException)` first.
4. **Avoid overly deep hierarchies:** if multiple error cases only differ in message text and are handled the same way, one clear exception type may be enough.
5. **Document the contract:** document thrown exceptions with `@throws` in JavaDoc, especially when callers need to know which branches to recover from.

A Java class cannot `extends` two exception classes simultaneously. If you need to describe multiple characteristics of an error, consider exception fields/properties, the root cause, or a structured result type instead of a confusing inheritance tree.

## 10. Choosing a Handler by the Action Needed

Catching the most specific type is useful when each type leads to **a different action**, not just to print the class name:

```java
try {
    // Calls that process input and access data.
} catch (NumberFormatException ex) {
    // Report invalid number format: the user needs to fix the input.
} catch (IllegalArgumentException ex) {
    // Respond to invalid parameters according to the application contract.
} catch (java.io.FileNotFoundException ex) {
    // Handle or report a specific missing resource.
} catch (java.io.IOException ex) {
    // Report an I/O error or retry if policy permits.
}
```

This is an illustrative structure; the `try` block needs to contain actual operations that can throw the listed types. Not every API needs four branches like this. If a method can only throw one error type and all callers react the same way, adding multiple `catch` blocks brings no benefit.

Principles to avoid catching the wrong things:

- **Keep the `try` scope just right:** if you combine data parsing and business logic into one broad `try`, `catch (IllegalArgumentException)` may accidentally catch an exception caused by a programming bug in another step.
- **Do not catch and ignore:** `catch (Exception ignored) {}` hides errors and makes the caller think the operation succeeded.
- **Do not catch just to rethrow unchanged without adding value:** a `catch` containing only `throw ex;` is usually redundant, unless an intentional action like cleanup or logging is needed.
- **Only wrap errors when there is a reason:** converting `IOException` into `IllegalStateException` can make sense in an API that does not allow I/O recovery; when wrapping, pass `cause` so the trail is not lost.
- **Do not branch on message strings:** do not branch with `ex.getMessage().contains("file")`; messages can change, be localized, or contain incidental data.
- **Consider the outer layer's contract:** an API may map specific errors to appropriate HTTP status codes; a storage layer may keep `IOException` for the application layer to decide. This is a design decision—there is no single `catch` type right for every system.

## 11. Common Compile Errors and Conceptual Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Placing `catch (Exception)` before `catch (IOException)` | The child handler is shadowed | Move `IOException` before it or remove the redundant handler |
| Writing `catch (IOException | FileNotFoundException)` | The two alternatives have a parent/child relationship | Use `catch (IOException)` or split into separate branches |
| Assuming `catch (IOException)` catches `IllegalStateException` | The two types are on different branches | Choose the type based on the actual exception and handling policy |
| Thinking `catch (Exception)` also catches `Error` | `Error` is a sibling branch of `Exception` | Do not treat `Error` as a normal business error |
| Believing a "more specific" outer `catch` takes precedence | An inner `try-catch` can handle it first | Identify the active handling scope closest to the throw site |
| Lumping all errors into `catch (Throwable)` and returning success | Masks serious errors and creates an invalid state | Catch exceptions that have a meaningful handling action |
| Identifying errors using `getMessage()` | The message is not a type-classification contract | Use exception types, properties, or explicit result types |
| Creating many subclasses without distinct handling | Complicates the API with little benefit | Keep a minimal hierarchy based on semantics |

## 12. Self-Check Exercises

**Scenario A:** A method throws `NumberFormatException`. In the same `try`, there is only `catch (RuntimeException)`. Will it be caught?

**Yes.** `NumberFormatException` is a child of `IllegalArgumentException`, and `IllegalArgumentException` is a child of `RuntimeException`.

**Scenario B:** There is `catch (IOException)` followed by `catch (FileNotFoundException)`. Will it compile?

**No.** `FileNotFoundException` is a subclass of `IOException` and is already completely caught by the preceding branch.

**Scenario C:** An inner `try` catches `IllegalArgumentException` and finishes handling a `NumberFormatException` without rethrowing. Will `catch (NumberFormatException)` on the outer `try` run?

**No.** The exception was already handled in the inner scope, so it does not propagate outward.

**Scenario D:** With `catch (Exception)`, will an `OutOfMemoryError` be caught?

**No.** `OutOfMemoryError` extends `Error`, and `Error` does not extend `Exception`.

**Scenario E:** To share one message for file-reading and number-input errors, can you write `catch (IOException | NumberFormatException)`?

**Yes**, if both can occur in the `try` block under consideration. They have no parent/child relationship, and multi-catch allows sharing one handler.

**Scenario F:** You create `InvalidOrderException extends IllegalArgumentException`. If you delete the dedicated handler for `InvalidOrderException`, will the `IllegalArgumentException` handler after it catch it?

**Yes.** A parent handler catches child objects, provided the exception actually reaches it without being handled in an inner `try`.

**Takeaway:** Java selects `catch` using **the runtime type and inheritance relationship**, while following **the active handler scope and the order of branches within the same `try`**. Place specific handlers before parent handlers and only catch at the layer that has an appropriate handling action.