# Disallowing Generic Classes That Extend `Throwable` in Java

## Learning objectives

In Java, a class can extend `Exception`, `RuntimeException`, or `Error` to represent errors. However, **a generic class cannot be a direct or indirect subclass of `java.lang.Throwable`**. This means ideas such as `class ProcessingException<T> extends Exception` or `class Failure<T> extends RuntimeException` are rejected by the Java compiler.

This is a language limitation, not a matter of "not knowing the right syntax". Type erasure prevents generic type arguments from being distinguished at runtime as distinct exception types for the `catch` mechanism.

After this lesson, you will be able to:

- Identify **invalid** generic exception declarations, including indirect inheritance paths from `Throwable`.
- Understand the role of **type erasure** and runtime exception matching.
- Distinguish **prohibited generic exception classes** from **valid generic methods declaring `throws E`**.
- Write `<E extends Exception> void propagate(E error) throws E` properly.
- Explain why you cannot use a type parameter `E` as the type of a `catch (E ex)` parameter, even when `E extends Exception`.
- Design alternatives: **non-generic** exceptions with typed properties, **generic data holders** independent of `Throwable`, or generic methods/functional interfaces with an exception type parameter.
- Read `javac` warnings/errors, distinguish checked and unchecked exceptions, and avoid misconceptions about the JVM.

The Java 17+ programs in this lesson have been compiled and tested. Snippets marked **invalid** are intentional samples to demonstrate compiler errors, not files meant to run successfully.

## 1. The exact Java rule

The key rule is:

> A generic class cannot be a subclass of `Throwable`, whether directly or through intermediate classes.

All of the following types are invalid:

```java
// DOES NOT COMPILE:
class GenericChecked<T> extends Exception {}

class GenericUnchecked<T> extends RuntimeException {}

class GenericError<T> extends Error {}

class PlainProblem extends Exception {}
class GenericIndirect<T> extends PlainProblem {}
```

`PlainProblem` in the example is an ordinary exception and **is allowed**. The error lies in `GenericIndirect<T>`: because it has a type parameter `T` and extends `PlainProblem`, which is a subclass of `Exception` → `Throwable`.

Java does not make this valid by changing `Exception` to `RuntimeException`:

- `Exception` is a subclass of `Throwable`.
- `RuntimeException` is a subclass of `Exception`.
- `Error` is a subclass of `Throwable`.
- Every subclass of the above types is ultimately a subclass of `Throwable`.

Running `javac` on these cases reports **`a generic class may not extend java.lang.Throwable`**. Java makes no special exception for "generic unchecked exceptions"; checked exceptions, runtime exceptions, and errors are all bound by the same generic-class limit.

## 2. Three easily confused concepts

| Declaration / construct | Valid? | Explanation |
| --- | --- | --- |
| `class ParseException extends Exception` | Yes | Non-generic exception class |
| `class ParseException<T> extends Exception` | **No** | Generic class is a subclass of `Throwable` |
| `class ParseException<T> extends RuntimeException` | **No** | `RuntimeException` still inherits from `Throwable` |
| `class Child<T> extends ParseException` | **No** | Generic subclass indirectly extends `Throwable` |
| `record ErrorData<T>(T value) {}` | Yes | This record does **not** extend `Throwable` |
| `interface Result<T> {}` | Yes | Normal generic interface, not an exception class |
| `<E extends Exception> void run(E e) throws E` | Yes | Generic **method** using a type variable in `throws` |
| `<E extends Exception> void run(E e) { catch (E x) {} }` | **No** | Type variable cannot be used as a catch parameter type |
| `class ParseException extends Exception` with a generic method | Yes | The **class** is non-generic; only the method is generic |
| Constructor `<T> ParseException(T data)` in a non-generic exception | Yes | A generic constructor does not make the class generic |

In short: **what is forbidden is combining "a class with a type parameter" and "being a subclass of `Throwable`"**. Java still permits generics in many error-handling contexts as long as that rule is not violated.

## 3. Why does Java forbid generic exception classes?

Java generics are primarily implemented through **type erasure**: parameterizations of the same generic class, such as `Box<String>` and `Box<Integer>`, do not produce two separate runtime classes per type argument.

Meanwhile, JVM exception handling relies on **the runtime class of the thrown object** and matching it against exception types in the exception handler table. Imagine if this syntax were allowed:

```java
// HYPOTHETICAL: Java does NOT actually allow declaring this type.
class Problem<T> extends Exception {}

// Further HYPOTHESIS, if two variants could be thrown:
// catch (Problem<String> ex) { ... }
// catch (Problem<Integer> ex) { ... }
```

In source code, `Problem<String>` and `Problem<Integer>` have different type arguments. Yet under Java's standard erasure mechanism, the runtime class would still just be `Problem`, not two distinct classes whose type arguments the JVM can distinguish.

Therefore, a `catch` mechanism branching on `<String>` versus `<Integer>` **cannot rely on erased generic arguments**. The language prevents the issue cleanly at declaration time: **it forbids defining a generic class that extends `Throwable`**.

### Scope of this explanation

Do not misinterpret this as "the JVM cannot hold an exception object containing generic data". A **non-generic** exception can still hold objects of various types in fields, or reference a **generic data holder**. What Java forbids is a **`Throwable` subclass** itself declaring a type parameter list.

At the same time, this is **a Java compilation rule**; inspecting bytecode manually or checking runtime metadata will not turn invalid source declarations into valid ones. Do not hunt for a "cast trick" to sneak past `javac`: the right solution is a different API design.

## 4. Testing the compiler: five intentional errors

Create the following file **`InvalidGenericExceptions.java`** to **observe errors**, not to run:

```java
class PlainProblem extends Exception {}

class GenericCheckedProblem<T> extends Exception {}

class GenericRuntimeProblem<T> extends RuntimeException {}

class GenericIndirectProblem<T> extends PlainProblem {}

class GenericErrorProblem<T> extends Error {}

class CatchProblem {
    static <E extends Exception> void catchTypeVariable(E error) {
        try {
            throw error;
        } catch (E caught) {
            System.out.println(caught);
        }
    }
}
```

Run:

```bash
javac InvalidGenericExceptions.java
```

**Verified key diagnostics from the Java compiler:**

```text
error: a generic class may not extend java.lang.Throwable
error: a generic class may not extend java.lang.Throwable
error: a generic class may not extend java.lang.Throwable
error: a generic class may not extend java.lang.Throwable
error: unexpected type
  required: class
  found:    type parameter E
5 errors
```

The order matches the four generic class declarations followed by `catch (E caught)` at the end. File paths, line numbers, and compiler notes may vary by JDK version; the essence is:

1. `GenericCheckedProblem<T>`: generic + `Exception`.
2. `GenericRuntimeProblem<T>`: generic + `RuntimeException`.
3. `GenericIndirectProblem<T>`: generic + `PlainProblem` → `Exception`.
4. `GenericErrorProblem<T>`: generic + `Error`.
5. `catch (E caught)`: `E` is a type parameter, not a class allowed in a catch clause.

**Important:** `PlainProblem extends Exception` is a valid declaration; it is not the cause of any of the five errors.

### Why is `catch (E e)` rejected?

`E extends Exception` states that `E` is bounded by `Exception`; it **does not** turn `E` into a concrete class such as `IOException.class` that a runtime catch handler can match under Java source semantics.

A catch clause requires an **appropriate exception class type**, disallowing a type variable as the catch parameter type. If you need to catch an exception inside a generic method, catch an appropriate exception class, or design the generic method to **propagate** the exception via `throws E`, as shown next.

## 5. Generic `throws E` is valid

This is the most easily misunderstood point of the lesson.

**You cannot write a generic exception class:**

```java
// Invalid:
class MyException<T> extends Exception {}
```

**But you can write a generic method with a type variable in `throws`:**

```java
static <E extends Exception> void propagate(E error) throws E {
    throw error;
}
```

Here `E` is a **method type parameter**, bounded by `Exception`. The method accepts an exception object with a real runtime class, and throws **that exact exception object** via `throw error`. It does not create a new generic exception class.

Conceptual usage example:

```java
try {
    propagate(new java.io.IOException("disk offline"));
} catch (java.io.IOException ex) {
    System.out.println(ex.getMessage());
}
```

When calling `propagate` with `IOException`, the compiler preserves the checked-exception information for the caller. `catch (IOException ex)` uses a **real exception class**, which is valid; it is not `catch (E ex)`.

The rule applies more broadly: a type parameter in `throws E` can be used when `E` is appropriately bounded by `Throwable` or a suitable subclass, such as `<E extends Exception>`. Throwing and catching real objects at runtime still follows the `Throwable` hierarchy.

## 6. Java 17 program: generic method propagating checked exceptions

Create the file **`ExceptionGenericsDemo.java`**:

```java
import java.io.IOException;

public class ExceptionGenericsDemo {
    static final class DataException extends Exception {
        private static final long serialVersionUID = 1L;
        private final String field;

        DataException(String field, String message, Throwable cause) {
            super(message, cause);
            this.field = field;
        }

        String field() { return field; }
    }

    @FunctionalInterface
    interface ThrowingSupplier<T, E extends Exception> {
        T get() throws E;
    }

    static <T, E extends Exception> T execute(ThrowingSupplier<T, E> work)
            throws E {
        return work.get();
    }

    static <E extends Exception> void propagate(E error) throws E {
        throw error;
    }

    static int parseAge(String input) throws DataException {
        try {
            int age = Integer.parseInt(input);
            if (age < 0) throw new NumberFormatException("negative");
            return age;
        } catch (NumberFormatException ex) {
            throw new DataException("age", "Invalid age: " + input, ex);
        }
    }

    public static void main(String[] args) {
        try {
            int age = execute(() -> parseAge("21"));
            System.out.println("age: " + age);
        } catch (DataException ex) {
            System.out.println("unexpected: " + ex.getMessage());
        }

        try {
            execute(() -> parseAge("bad"));
        } catch (DataException ex) {
            System.out.println("checked: " + ex.field()
                    + " / " + ex.getMessage());
            System.out.println("cause: "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            propagate(new IOException("disk offline"));
        } catch (IOException ex) {
            System.out.println("propagated: " + ex.getMessage());
        }
    }
}
```

Save the file matching the public class name and run:

```bash
javac -Xlint:all ExceptionGenericsDemo.java
java ExceptionGenericsDemo
```

**Verified stdout:**

```text
age: 21
checked: age / Invalid age: bad
cause: NumberFormatException
propagated: disk offline
```

This program compiled cleanly under `-Xlint:all` **with zero warnings** in the tested Java 17 environment.

### Explaining the structure

**`DataException extends Exception` is non-generic.** It is an ordinary checked exception class with a `String field` attribute describing the invalid data field. `serialVersionUID` is declared because exceptions can be serialized under `Serializable`, keeping the example free of `[serial]` warnings under `-Xlint:all`.

**`ThrowingSupplier<T, E extends Exception>` is a valid generic interface.** It does not extend `Throwable`. Type parameter `T` represents the result and `E` represents the checked exception type the call may throw.

**`execute(ThrowingSupplier<T,E>) throws E` is a valid generic method.** The compiler can infer `T` from the result type and `E` from the callback's checked-exception contract. The method body calls `work.get()` and lets errors propagate without wrapping the exception in a generic subclass.

**`propagate(E error) throws E` throws a provided exception object.** With `IOException`, the caller can catch that exception type by its real class. There is no constructor of a generic exception here.

**`parseAge` converts a parse failure into `DataException`.** It preserves the `NumberFormatException` cause via `super(message, cause)`. This is a standard checked-exception pattern requiring no `DataException<T>`.

### Checked and unchecked in the example

`DataException` and `IOException` are checked exceptions: callers must catch them or declare an appropriate `throws`. `NumberFormatException` is an unchecked exception (a subclass of `RuntimeException`); here it is caught and wrapped into `DataException` to provide a clear contract for the parsing API.

The prohibition on generic classes extending `Throwable` applies to **both** `RuntimeException` and `Error`; unchecked exceptions are not exempt from the generic exception class ban.

## 7. Why is a generic interface with an exception type argument a good alternative?

A utility handling multiple error types often needs:

- **A result type**: `T`.
- **A throwable checked exception type**: `E`.
- A way to reuse logic without catching everything as `Exception` or `RuntimeException`.

You can define:

```java
@FunctionalInterface
interface ThrowingTask<T, E extends Exception> {
    T run() throws E;
}
```

This is a **generic interface**, not a generic exception class; completely valid. When writing:

```java
static <T, E extends Exception> T runTask(ThrowingTask<T, E> task)
        throws E {
    return task.run();
}
```

the generic information lets the compiler enforce the checked-exception contract on the caller. There is no need for `TaskException<T>`.

**Understand the limit, though:** this is not a mechanism for catching by type argument. A method accepting `ThrowingTask<String, IOException>` still throws a runtime `IOException` object; callers handle it with `catch(IOException ex)` on the concrete class, not with a handler for "the callback's `E`".

This pattern is useful when writing APIs supporting I/O callbacks, parsing, file operations, or checked-exception adapters. If the API needs extra business context, keep that context in a **non-generic exception class** or in a separate **generic result/data class**.

## 8. Alternative design: non-generic exception, generic data

Problem: you want a record-processing error carrying typed information—such as an HTTP status code, error code, or payload object. You should not create `OperationException<T> extends Exception`.

Instead:

1. A **non-generic** exception class describes the error identity and stable fields.
2. A **generic record/class independent of `Throwable`** can represent domain data.
3. A generic method can accept `Class<T>` to inspect an object when extracting typed data `T` is genuinely needed.

Create the file **`ExceptionContextDemo.java`**:

```java
public class ExceptionContextDemo {
    record FailureData<T>(String code, T payload) {}

    static final class OperationException extends Exception {
        private static final long serialVersionUID = 1L;
        private final String code;
        private final int status;

        OperationException(String message, String code, int status) {
            super(message);
            this.code = code;
            this.status = status;
        }

        FailureData<Integer> detail() {
            return new FailureData<>(code, status);
        }

        <T> T statusAs(Class<T> expected) {
            return expected.cast(status);
        }
    }

    static void load() throws OperationException {
        throw new OperationException("Not found", "NOT_FOUND", 404);
    }

    public static void main(String[] args) {
        try {
            load();
        } catch (OperationException ex) {
            System.out.println("error type: "
                    + ex.getClass().getSimpleName());
            System.out.println("detail: " + ex.detail());
            System.out.println("status: " + ex.statusAs(Integer.class));

            try {
                ex.statusAs(String.class);
            } catch (ClassCastException cast) {
                System.out.println("wrong status type: "
                        + cast.getClass().getSimpleName());
            }
        }
    }
}
```

Compile and run:

```bash
javac -Xlint:all ExceptionContextDemo.java
java ExceptionContextDemo
```

**Verified stdout:**

```text
error type: OperationException
detail: FailureData[code=NOT_FOUND, payload=404]
status: 404
wrong status type: ClassCastException
```

This program also passed `javac -Xlint:all` **with no warnings**.

### Why is it valid?

`OperationException` has no type parameter on its class declaration, so it is allowed to `extends Exception`.

`FailureData<T>` is an **ordinary generic record**. It is not a subclass of `Throwable`; having the record carry a status number and error code is plain data, not a generic exception.

`detail(): FailureData<Integer>` is merely **a method return type** inside a non-generic exception class. The method returns an ordinary generic object; Java does not forbid a `Throwable` subclass from having methods returning generic types.

`<T> T statusAs(Class<T> expected)` is a **generic instance method** of a non-generic exception class. It is allowed to use type parameter `T`; `Class.cast` checks converting `status` (boxed as `Integer`) to the runtime type requested by the caller. When called with `String.class`, the cast fails with `ClassCastException`, showing that a generic method cannot turn a mismatched type into a valid one.

### Production-level design

If context needs to store arbitrary objects inside an exception, you must address **serialization**, type bounds, ownership, and information security. Every `Throwable` participates in serialization; a field referencing a non-serializable payload can cause serializing the exception to fail. Here the example stores `String` and `int` directly on the exception, and constructs `FailureData<Integer>` **on demand** instead of storing a generic object of unknown serializability.

In practice, prefer an exception class with error code, message, cause, and necessary domain attributes; use a separate generic result/data type when you need to carry typed results or errors explicitly without relying on exception dispatch.

## 9. Generic constructors inside non-generic exceptions remain valid

Another case proves that the restriction applies only to **class declarations**.

Create the file **`GenericConstructorExample.java`**:

```java
public class GenericConstructorExample {
    static final class ReportException extends Exception {
        private static final long serialVersionUID = 1L;

        <T> ReportException(T value) {
            super("failure: " + value);
        }
    }

    public static void main(String[] args) {
        try {
            throw new ReportException(42);
        } catch (ReportException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Run:

```bash
javac -Xlint:all GenericConstructorExample.java
java GenericConstructorExample
```

Verified stdout:

```text
failure: 42
```

Here `<T>` belongs to **the constructor**, not the `ReportException` class. An instance `new ReportException(42)` still belongs to the normal runtime class `ReportException`. The constructor only uses `T` to accept a value generically and build a message; it does not preserve "`ReportException<Integer>`" as a runtime exception type.

You can write a simpler constructor accepting `Object` when generic-specific inference or constraints are unnecessary; a generic constructor does not provide stronger type safety when the argument is merely converted to a string.

## 10. Boundaries of `throw`, `throws E`, and `catch` when exception classes are non-generic

A **non-generic** exception class can still appear in an API that uses Generics:

```java
static <E extends Exception> void relay(E failure) throws E {
    throw failure;
}
```

This is an **illustrative method** to be placed inside a class. `throw failure` throws an **existing exception object**; `throws E` describes the checked-exception contract via a **method** type variable without declaring a generic subclass of `Throwable`. The caller can catch a real class, such as `catch (IOException ex)`, in an appropriate declaration/call context. You cannot write `catch (E ex)`, because a catch parameter must specify a valid exception class rather than a type variable.

Exact summary:

| Design | Valid? | Why |
|---|---|---|
| `class Failure extends Exception` | Yes | Non-generic exception class |
| `class Failure<T> extends Exception` | No | Generic subclass of `Throwable` |
| Method `<E extends Exception> ... throws E` | Yes | Generic contract on the method, not on an exception class |
| `catch (E ex)` | No | A handler cannot be identified by a type variable |
| `new E()` | No | A type variable does not provide a constructor |

**Scope of this lesson:** this rule governs **how exception classes are declared**. Advanced topics such as JVM catch handler selection, `Class<E>.isInstance`, precise rethrow, and type inference in `throws E` belong to separate analyses and cannot be "fixed" by making an exception class generic.

## 11. Inspecting bytecode with `javap`: generic methods are still erased

After compiling `ExceptionGenericsDemo.java`, run:

```bash
javap -s -p ExceptionGenericsDemo
javap -s -p 'ExceptionGenericsDemo$ThrowingSupplier'
```

**Verified** excerpt:

```text
static <T, E extends java.lang.Exception> T execute(
    ExceptionGenericsDemo$ThrowingSupplier<T, E>) throws E;
  descriptor: (LExceptionGenericsDemo$ThrowingSupplier;)Ljava/lang/Object;

static <E extends java.lang.Exception> void propagate(E) throws E;
  descriptor: (Ljava/lang/Exception;)V
```

And from the interface:

```text
interface ExceptionGenericsDemo$ThrowingSupplier<T, E extends java.lang.Exception> {
  public abstract T get() throws E;
    descriptor: ()Ljava/lang/Object;
}
```

Lines showing `<T, E extends Exception>` come from generic metadata that `javap` displays. However, JVM descriptors use erasure:

- Unbounded `T` is erased to `Object`.
- `E extends Exception` in **a method type-parameter position** is erased to `Exception`.
- `ThrowingSupplier<T,E>` is represented by the runtime interface `ThrowingSupplier`, with no separate class variants per type argument.

**Point to distinguish:** descriptors do not "bring back" generic exception classes. `throws E` remains a checked-exception contract declaration in source; the runtime object thrown is a real exception such as `IOException` or `DataException`.

With `javap -v`, you can inspect the generic `Signature` and attributes related to declared exceptions. Never treat descriptors as evidence that the JVM has catch handlers distinguishing `Exception<String>` and `Exception<Integer>`; such generic exception types cannot validly exist in Java source.

## 12. Checked vs unchecked exceptions make no exception to the rule

| Group | Examples | Compile-time handling | Allowed to have a generic subclass? |
| --- | --- | --- | --- |
| Checked exception | `Exception`, `IOException`, `DataException` | Requires appropriate catch/throws | **No** |
| Unchecked exception | `RuntimeException`, `IllegalArgumentException` | No mandatory catch/throws | **No** |
| Error | `Error`, `AssertionError` | No mandatory catch/throws | **No** |

The fact that unchecked exceptions propagate without being declared in `throws` is **unrelated** to the rule forbidding generic subclasses of `Throwable`.

For example:

```java
// Neither COMPILES:
class RetryException<T> extends RuntimeException {}
class BrokenSystemError<T> extends Error {}
```

They are still generic classes under the `Throwable` inheritance hierarchy.

Proper replacement:

```java
class RetryException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    RetryException(String message) { super(message); }
}
```

If you want to carry typed information about the retried task, place it in a generic result wrapper that does not extend `Throwable`, or expose appropriate fields/methods with a clear runtime contract.

## 13. Common misconceptions

**Misconception 1 — "Nothing related to exceptions can be genericized."** False. Generic methods with `throws E`, generic functional interfaces, and generic data holders are all valid. Only **a generic class that is a `Throwable` subclass** is forbidden.

**Misconception 2 — "Replacing `Exception` with `RuntimeException` fixes the error."** False. `RuntimeException` is still a subclass of `Throwable`, so `class X<T> extends RuntimeException` is still rejected.

**Misconception 3 — "Indirect inheritance bypasses the limit."** False. `class X<T> extends NonGenericException` is also invalid if `NonGenericException` descends from `Throwable`.

**Misconception 4 — "`throws E` is forbidden just like `catch (E)`."** False. These are two different syntactic positions and two different rules. `throws E` is valid when properly bounded; `catch (E)` is invalid.

**Misconception 5 — "`E extends Exception` turns `E` into a real class at runtime."** False. `E` remains a type variable. When called with `IOException`, the actual object is an `IOException`, yet `E` does not become a class literal usable in a catch clause.

**Misconception 6 — "Having `<T>` on a constructor makes the whole exception class generic."** False. A generic constructor can live inside a **non-generic** exception class, like `ReportException` in Section 9.

**Misconception 7 — "Casts or reflection can force `GenericException<T>` to become valid."** False in Java source. Runtime reflection does not alter class-declaration rules enforced by the compiler.

**Misconception 8 — "A generic result record is an exception."** `FailureData<T>` is just a data object. It does not automatically substitute for `try/catch`; to use exception flow, throw a non-generic `Throwable` object or use an explicit result-returning API.

**Misconception 9 — "An exception with an `Object` field safely holds anything."** If data comes from untrusted sources, validation or a type token is still needed. Moreover, `Throwable` interacts with serialization, so fields holding non-serializable objects must be designed carefully.

**Misconception 10 — "Because of type erasure, a generic method with `throws E` is useless."** False. The compiler still enforces the generic contract on callbacks and callers, making generic `throws` highly useful despite erased bytecode types.

## 14. In real API design, which approach should you choose?

### You want to distinguish business error kinds with `catch`

Use appropriate **non-generic exception classes** such as `ValidationException`, `DataException`, and `NotFoundException`. Each has its own runtime class, matching how the JVM dispatches exception handlers.

### You want an exception with an error code and context

Add fields/methods to a **non-generic exception class**. Preserve causes with `Throwable cause`, e.g., `super(message, cause)`. For polymorphic payloads, consider serialized form, a `Class<T>` token, or explicit validation.

### You want a helper supporting multiple checked exception types

Use a method `<T, E extends Exception> T execute(ThrowingSupplier<T,E> action) throws E`. This preserves checked-exception information at source level without creating a generic `Throwable` subclass.

### You want compile-time typed result/error data

Use a **generic result wrapper** independent of `Throwable`, such as `record Result<T>(T value, String errorCode)`, or a dedicated sealed hierarchy representing success/failure states. This fits when errors are data inspected by callers rather than thrown exceptions.

### You want to pass an exception into a utility

Accept a variable `E extends Exception` or an appropriate `Supplier<? extends E>`; throw a real exception object. Never attempt `new E()` or `catch (E)`.

## 15. Exercises with answers

### Exercise 1 — Four declarations

Consider:

```java
class A extends Exception {}
class B<T> extends Exception {}
class C<T> extends RuntimeException {}
class D<T> extends A {}
```

**Question:** which classes are valid?

**Answer:** only `A` is valid. `B` and `C` are directly generic under `Throwable`; `D` is indirectly generic under `Throwable`.

### Exercise 2 — Generic method vs generic class

```java
static <E extends Exception> void send(E error) throws E {
    throw error;
}
```

**Question:** why is this method valid while `class EBox<E> extends Exception` is invalid?

**Answer:** the type variable `E` belongs to the generic method to describe the type of exception object passed and thrown; the method does not define a generic class under `Throwable`. `EBox<E>` directly defines a generic exception class, which is forbidden.

### Exercise 3 — Catching `E`

Given `<E extends IOException> void handle(E e)`, can you write `catch(E ex)`?

**Answer:** no. Even with a specific bound, a type variable is not a catchable exception class in a catch parameter. You can catch `IOException` where consistent with the try block and checked-exception rules, or propagate via `throws E`.

### Exercise 4 — Choosing a design

An application wants to report a `NotFound` error with status code `404` and typed detail metadata.

**Guided answer:** create a **non-generic** `NotFoundException extends Exception`/`RuntimeException`, storing appropriate `code`, `status`, `message`, and `cause`; if a typed data structure is needed, create a separate `FailureData<Integer>`. Do not write `NotFoundException<Integer> extends Exception`.

### Exercise 5 — Reading bytecode

What is the erased parameter type of `<E extends Exception> void propagate(E error) throws E`?

**Answer:** `Exception`, because `E`'s upper bound is `Exception`; typical JVM descriptor `(Ljava/lang/Exception;)V`.

### Exercise 6 — Constructor with `<T>`

```java
class ReportException extends Exception {
    <T> ReportException(T value) { super(String.valueOf(value)); }
}
```

**Question:** is this forbidden by the generic `Throwable` subclass rule?

**Answer:** no. The `ReportException` class is non-generic; only the constructor is a generic member. Do not mistake a constructor having `T` for the JVM creating a separate `ReportException<String>` class.

### Exercise 7 — Checked exception contract

Why is `ThrowingSupplier<T,E extends Exception>` useful?

**Answer:** it lets you describe both the result type `T` and the checked exception type `E` in a single call, enabling callers to catch or declare the specific error type when the compiler infers `E`.

### Exercise 8 — Turning errors into data

If an API does not need `throw/catch` and instead wants callers to inspect whether an error occurred, what is suitable?

**Answer:** a generic result type or sealed result hierarchy that does **not** extend `Throwable`. Generic classes like `Result<T>` can hold typed payloads without violating exception-hierarchy rules.

## 16. Checklist to remember

When designing exceptions or generic utilities in Java:

- [ ] If a class has `<T>`, it must **not** be a direct or indirect subclass of `Throwable`.
- [ ] Never write `class X<T> extends Exception`, `RuntimeException`, or `Error`.
- [ ] When catching by error kind is needed, use **concrete non-generic exception classes**.
- [ ] Distinguish forbidden `catch(E)` from potentially valid `throws E`.
- [ ] When `throw error` uses a type variable, ensure proper bounds and `throws` declarations.
- [ ] For typed callbacks, use a generic interface like `ThrowingSupplier<T,E>`.
- [ ] For typed context, use a generic data class/record independent of `Throwable`.
- [ ] When storing data inside an exception, consider `cause`, serialization, and runtime type checks.
- [ ] If using a generic method inside an exception class, ensure **the class itself remains non-generic**.
- [ ] Verify examples with `javac`, compare outputs carefully, and never bypass compiler errors with unchecked casts.

## Conclusion

**Java does not allow declaring a generic class that extends `Throwable`, directly or indirectly**, so `class MyException<T> extends Exception` and `class MyRuntimeException<T> extends RuntimeException` are both invalid. This is a language limit tied to type erasure and exception matching by runtime class.

Nevertheless, **generics still have a strong place in error-handling design**: generic methods with `throws E`, generic callback interfaces, generic constructors in non-generic exceptions, and generic data holders all work well. Keep exception classes non-generic so `throw/catch` remains clear, and place type parameters on the APIs and data structures that truly need them.