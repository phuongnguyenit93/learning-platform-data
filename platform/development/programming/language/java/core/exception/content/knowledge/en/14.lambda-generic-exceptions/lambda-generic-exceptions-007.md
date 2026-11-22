# Limitations of `catch` with Type Parameters in Java Generics and Lambdas

In Java, **generic type parameters** such as `T`, `E`, or `X` allow defining methods and classes that work across multiple types. Specifically for exception handling, there is an easily misunderstood limitation: **Java allows declaring `throws E` when `E extends Throwable`, but does not allow writing `catch (E e)` if `E` is a type parameter**.

This is not a difference in parentheses or naming. `throws E` describes a checked exception contract for the compiler, whereas `catch` is a **runtime exception type filter during handling**; a generic type parameter cannot be used as the parameter type of a catch clause.

Intentionally invalid example:

~~~java
static <E extends Exception> void wrong(ThrowingTask<E> task) {
    try {
        task.run();
    } catch (E e) { // DOES NOT COMPILE.
        System.out.println(e.getMessage());
    }
}
~~~

In this snippet, `ThrowingTask<E>` is assumed to be a functional interface with `void run() throws E`. Even though `E extends Exception`, using `E` as the type in `catch` is still invalid.

The basic fix is to **catch a concrete exception type** such as `IOException` or an appropriate superclass such as `Exception`, or let the exception propagate via `throws E`. If you need to identify an error type represented by a type parameter at runtime, passing a **class token `Class<E>`** and checking with `isInstance`/`cast` is a better-controlled approach.

This lesson belongs to Java Core – Exception, in the context of **Lambdas and generics**. It focuses on the `catch` rule with type variables, type erasure, checked exceptions in generic functional interfaces, limitations of generic exception classes, and Java 17+ coding solutions.

## 1. Recap: What Is a Generic Type Parameter?

Example of a generic method:

~~~java
static <T> T identity(T value) {
    return value;
}
~~~

Here `T` is a **type parameter** declared by the method. The caller can invoke `identity("Hello")` or `identity(42)`, and the compiler checks the corresponding value type.

For exceptions, you can bound the type parameter:

~~~java
static <E extends Exception> void fail(E exception) throws E {
    throw exception;
}
~~~

This is a **valid** Java method inside a class. `E` represents a subtype of `Exception`; `throws E` is allowed, and `throw exception;` is also allowed.

Usage example:

~~~java
try {
    fail(new java.io.IOException("disk unavailable"));
} catch (java.io.IOException e) {
    System.out.println(e.getMessage());
}
~~~

At the caller, the exception type used in `catch` is **`IOException` — a concrete class**. We do not write `catch(E e)` in the generic method.

**Rule pairs to distinguish:**

| Construct | Can type variable `E` be used? |
| --- | --- |
| `<E extends Exception>` | Yes, declares a type parameter with an upper bound |
| `void run() throws E` | Yes, when `E` has a bound compatible with `Throwable` |
| `throw exception;`, with a variable of type `E` | Yes |
| `catch (E e)` | **No** |
| `catch (IOException e)` | Yes, if other checked/reachability rules are satisfied |
| `catch (Exception e)` | Yes, if valid with the corresponding `try` |
| `catch (IOException | SQLException e)` | Possible, when the alternatives are valid |
| `catch (E | IOException e)` | **No**, because `E` is still a type variable |

A type variable, whether named `ExceptionType`, `E`, or `IOExceptionLike`, remains a **type variable** and does not turn into a class declaration that can serve as a catch type.

## 2. What Type Does Java Use to Select `catch`?

When a `Throwable` is thrown, the JVM searches for a handler whose scope matches the type of the **actual exception object**. A typical catch clause:

~~~java
try {
    readFile();
} catch (java.io.IOException e) {
    System.out.println("I/O problem");
} catch (Exception e) {
    System.out.println("Another exception");
}
~~~

This is an illustrative snippet; `readFile()` is a method that can throw `IOException`. If an `IOException` is thrown, the first handler with type `IOException` receives it. The broader `Exception` handler is placed afterward.

`catch` requires a valid exception type to determine the matching condition. **A generic type parameter does not represent a distinct class at runtime.** Therefore, the compiler forbids using a type variable as a catch parameter type, even when it has an upper bound of `Exception` or `IOException`.

A common mistake:

~~~java
static <E extends java.io.IOException> void invalidCatch(
        ThrowingTask<E> task) {
    try {
        task.run();
    } catch (E e) { // Compile-time error.
        System.out.println(e.getMessage());
    }
}
~~~

Even though `E extends IOException`, the identifier `E` still represents **a type variable**, not the `IOException` class. The upper bound restricts the range of `E`, but **does not allow `catch(E)`**.

## 3. Type Erasure and the Design Rationale Behind This Limitation

Java generics primarily work through **type erasure**. In many runtime contexts, type parameters are erased, and there is no separate runtime class version for each type argument combination such as `Box<String>` or `Box<Integer>`.

In conceptual explanations, a type variable `E extends Exception` is often erased to its corresponding upper bound `Exception`. However, **this does not mean the compiler will automatically accept `catch (E e)` and replace it with `catch (Exception e)`**. The language forbids type variables in catch clauses at compile time.

Why? Suppose a method is called with `E = IOException` in one call and `E = SQLException` in another. If `catch(E)` were treated as filtering **exactly `E`**, the runtime would need to know which type argument is being used. Type erasure does not automatically generate different handlers per instantiation of a generic method.

Therefore, to catch an exception type at runtime, you need a **well-defined exception type**, or a **class token** passed as data:

~~~java
Class<java.io.IOException> expected = java.io.IOException.class;

Exception e = new java.io.IOException("disk failed");
System.out.println(expected.isInstance(e)); // true
~~~

`Class.isInstance` checks the actual runtime type of the object without pretending that the type parameter was preserved for the JVM to create a dynamic catch clause.

### Type erasure does not explain the entire rule in one sentence

It is more accurate to understand it as follows:

1. Java's `catch` has its own language requirements regarding the **type** of the catch parameter.
2. **A type variable cannot be used as the type of a catch parameter**, even if its bound is an exception class.
3. Type erasure explains why a generic type argument does not automatically become an independent runtime class filter.
4. When dynamic matching is needed, you do it **inside a valid handler** or in normal code, using a token/reflection with a clear contract.

You should not simply say "generics cannot be used with `catch` at all." A generic method can **throw a generic checked exception using `throws E`**, and a lambda can represent a checked exception type in a generic functional interface.

## 4. `throws E` Is Completely Valid When `E` Has an Appropriate Bound

Example:

~~~java
@FunctionalInterface
interface ThrowingAction<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void execute(
        ThrowingAction<E> action) throws E {
    action.run();
}
~~~

These are two valid illustrative declarations when placed inside a class, with the interface in an appropriate scope.

Key points:

- `E` must have a bound making it a subtype of `Throwable` (here `Exception` is chosen to represent common exceptions).
- `ThrowingAction<E>.run()` can declare `throws E`.
- `execute(...)` can propagate `E` using `throws E`.
- The caller is checked by the compiler for checked exceptions according to the inferred type.

Caller:

~~~java
try {
    execute(() -> {
        throw new java.io.IOException("Cannot read");
    });
} catch (java.io.IOException e) {
    System.out.println("Caught: " + e.getMessage());
}
~~~

In this example, the compiler can infer an appropriate checked exception type from the lambda and generic method context. To keep tutorial examples easy to read and avoid relying on type inference in complex situations, you can also **explicitly declare** the variable:

~~~java
ThrowingAction<java.io.IOException> ioTask =
        () -> { throw new java.io.IOException("Cannot read"); };

try {
    execute(ioTask);
} catch (java.io.IOException e) {
    System.out.println("Caught: " + e.getMessage());
}
~~~

Here, `throws E` allows propagating the checked `IOException`; **no `catch(E)` is declared**.

### Why doesn't `throws E` conflict with type erasure?

`throws E` is part of static type checking and generic declaration metadata. It does not require the JVM to create a separate runtime handler based on the type argument.

By contrast, `catch (E e)` places `E` directly into the **exception-handling condition**. That is the operation Java does not allow with a type variable.

## 5. Using a Concrete Class Type Instead of `E`

If a generic method only needs to handle **any `IOException` or subtype** and the bound is `IOException`, you can catch `IOException` directly:

~~~java
@FunctionalInterface
interface ReaderTask<E extends java.io.IOException> {
    String read() throws E;
}

static <E extends java.io.IOException> String withFallback(
        ReaderTask<E> task) {
    try {
        return task.read();
    } catch (java.io.IOException e) {
        return "fallback";
    }
}
~~~

This is valid code when placed inside a Java class. `E` can be `IOException` or a subtype; `catch(IOException)` catches those subtypes. There is no reason to write `catch(E)`.

However, changing `catch(E)` to `catch(Exception)` is not always a good decision. A broad handler can also catch `RuntimeException`s caused by programming bugs or abnormal states. You should consider the exact scope of errors you actually intend to handle.

### Catching by upper bound: valid, but potentially too broad

Example:

~~~java
static <E extends Exception> void inspect(
        ThrowingAction<E> action) {
    try {
        action.run();
    } catch (Exception caught) {
        System.out.println(caught.getClass().getSimpleName());
    }
}
~~~

This is valid Java code. It receives any `Exception` that can escape from the `try` block, including unchecked `RuntimeException`s.

If the goal is only to handle a specific group of errors, use a narrower upper bound, specialized overloads, or an explicit class token. Do not catch `Exception` and assume that **every caught object** belongs to some subtype `E`.

## 6. Using `Class<E>` to Check a Specific Subtype When Truly Needed

Suppose we write a generic utility that accepts a task and wants to apply a fallback only when the exception matches a **class passed by the caller**.

A clear approach:

~~~java
static <E extends Exception> boolean matches(
        Throwable caught, Class<E> expectedType) {
    return expectedType.isInstance(caught);
}
~~~

This is a valid Java method. `Class<E>` carries runtime class information; `isInstance` performs the check. If you need to obtain a variable of type `E` after checking:

~~~java
static <E extends Exception> E castIfMatches(
        Throwable caught, Class<E> expectedType) {
    if (!expectedType.isInstance(caught)) {
        return null;
    }
    return expectedType.cast(caught);
}
~~~

You should not write an unchecked cast `(E) caught` without checking, because type erasure causes the compiler to issue an unchecked cast warning and correctness depends on runtime data.

### Advantages of a class token

- The caller explicitly specifies the desired error type, such as `IOException.class`.
- `expectedType.isInstance(caught)` checks the actual object type at runtime.
- `expectedType.cast(caught)` performs a checked cast against the token.
- No invalid `catch(E)` is needed.

### Limitations and responsibilities

- `Class<E>` only represents a runtime class; **it does not turn a type variable into a catch type**.
- A caller can pass an overly broad class like `Exception.class` and receive more error types than intended.
- If you want to match only the exact class, use `caught.getClass() == expectedType`, not `isInstance`. However, in exception handling you usually want to accept subtypes as well, so `isInstance` is generally more appropriate.
- If there are multiple checked exception types, a single `Class<E>` does not represent a complete multi-error contract; a dedicated API design is needed.
- Knowing that an exception "matched" only tells you the **error type**; it does not automatically decide whether a retry/fallback is business-safe.

## 7. A Complete Standalone Java 17+ Program

Create the file **`GenericCatchLimitDemo.java`**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

public class GenericCatchLimitDemo {

    @FunctionalInterface
    interface ThrowingSupplier<T, E extends Exception> {
        T get() throws E;
    }

    @FunctionalInterface
    interface ThrowingAction<E extends Exception> {
        void run() throws E;
    }

    static <T, E extends Exception> T execute(
            ThrowingSupplier<T, E> supplier) throws E {
        return supplier.get();
    }

    static <E extends Exception> void executeAction(
            ThrowingAction<E> action) throws E {
        action.run();
    }

    static <T, E extends Exception> T fallbackOnType(
            ThrowingSupplier<T, E> supplier,
            Class<E> expectedType,
            T fallback) {
        try {
            return supplier.get();
        } catch (Exception caught) {
            if (expectedType.isInstance(caught)) {
                E typed = expectedType.cast(caught);
                System.out.println(
                        "matched=" + typed.getClass().getSimpleName()
                                + ": " + typed.getMessage());
                return fallback;
            }
            if (caught instanceof RuntimeException runtime) {
                throw runtime;
            }
            throw new IllegalStateException(
                    "Unexpected checked exception", caught);
        }
    }

    static <E extends IOException> String catchBound(
            ThrowingSupplier<String, E> supplier) {
        try {
            return supplier.get();
        } catch (IOException e) {
            System.out.println("bound=" + e.getMessage());
            return "bound-fallback";
        }
    }

    static void multiCatch(boolean io) {
        try {
            if (io) {
                throw new IOException("read error");
            }
            throw new SQLException("query error");
        } catch (IOException | SQLException e) {
            System.out.println(
                    "multi=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== generic throws ==");
        ThrowingSupplier<String, IOException> ioSupplier =
                () -> { throw new IOException("disk offline"); };

        try {
            execute(ioSupplier);
        } catch (IOException e) {
            System.out.println("caught=" + e.getMessage());
        }

        System.out.println("== generic lambda ==");
        ThrowingAction<SQLException> sqlAction =
                () -> { throw new SQLException("database offline"); };
        try {
            executeAction(sqlAction);
        } catch (SQLException e) {
            System.out.println("action=" + e.getMessage());
        }

        System.out.println("== class token ==");
        String recovered = fallbackOnType(
                ioSupplier, IOException.class, "default");
        System.out.println("result=" + recovered);

        System.out.println("== successful supplier ==");
        ThrowingSupplier<String, IOException> ok =
                () -> "ready";
        System.out.println(
                "result=" + fallbackOnType(
                        ok, IOException.class, "default"));

        System.out.println("== subtype bound ==");
        System.out.println("result=" + catchBound(ioSupplier));

        System.out.println("== runtime mismatch ==");
        ThrowingSupplier<String, IOException> runtimeTask =
                () -> { throw new IllegalArgumentException("bad state"); };
        try {
            fallbackOnType(
                    runtimeTask, IOException.class, "default");
        } catch (IllegalArgumentException e) {
            System.out.println("not-matched=" + e.getMessage());
        }

        System.out.println("== multi-catch classes ==");
        multiCatch(true);
        multiCatch(false);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac GenericCatchLimitDemo.java
java GenericCatchLimitDemo
~~~

**Deterministic stdout:**

~~~text
== generic throws ==
caught=disk offline
== generic lambda ==
action=database offline
== class token ==
matched=IOException: disk offline
result=default
== successful supplier ==
result=ready
== subtype bound ==
bound=disk offline
result=bound-fallback
== runtime mismatch ==
not-matched=bad state
== multi-catch classes ==
multi=IOException: read error
multi=SQLException: query error
~~~

### Analyzing `generic throws`

`ThrowingSupplier<String, IOException>` is a lambda that can throw checked `IOException`. The `execute` method declares `throws E`, so it can propagate this error. The caller uses `catch (IOException e)` — a **concrete** exception type.

There is no `catch (E e)` in `execute`. The genericity lies in the **contract of the method and functional interface**, not in the catch type.

### Analyzing `generic lambda`

`ThrowingAction<SQLException>` has an abstract method `void run() throws SQLException` after applying the type argument. The lambda throws `SQLException` and the caller catches `SQLException`.

This shows that generic type parameters in `throws` remain very useful for organizing tasks that throw checked exceptions, even though `catch` cannot use type parameters.

### Analyzing `class token`

`fallbackOnType` catches with `catch(Exception)`, then calls `expectedType.isInstance(caught)`. With the token `IOException.class`, the actual exception is an `IOException`, so the check succeeds, `Class.cast` is valid, and the method returns `"default"`.

**Note:** the broad handler has a clear policy: when the error is a `RuntimeException` that does not match the token, it **rethrows** rather than masking the error with a default value; when a checked exception other than the token appears, the code wraps it in `IllegalStateException` preserving the cause. This policy illustrates how to avoid swallowing unexpected errors, rather than prescribing that every library must handle them identically.

### Analyzing `catchBound`

`E extends IOException`, so if the task throws checked `E`, `catch(IOException)` covers it. This approach is simpler than a class token when all errors the method wants to handle belong to a single known exception family.

### Analyzing `runtime mismatch`

A lambda declared with `E = IOException` can still throw an unchecked `IllegalArgumentException` because unchecked exceptions do not need to appear in `throws`. `catch(Exception)` catches it, but `IOException.class.isInstance(...)` is false. The code does not turn that error into a fallback; it rethrows it, and the caller catches the exact `IllegalArgumentException`.

### Analyzing multi-catch

`catch (IOException | SQLException e)` is valid because both are concrete exception classes and neither is a subtype of the other. The compiler still knows how to select the catch type used to filter the handler.

**You cannot replace either alternative with `E`**, even if `E` has a bound such as `Exception` or `IOException`.

## 8. Non-Compiling Counterexample: `catch(E e)` in a Generic Method

Consider:

~~~java
interface Task<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void handle(Task<E> task) {
    try {
        task.run();
    } catch (E e) {
        System.out.println(e.getMessage());
    }
}
~~~

**This is an intentionally non-compiling counterexample**; do not copy it into a runnable program. The parameter `e` in `catch` has type `E`, which is a **type variable**. The compiler rejects it even though `E extends Exception`.

It can be fixed according to your intent:

**Option A — Do not handle it here:**

~~~java
static <E extends Exception> void propagate(Task<E> task) throws E {
    task.run();
}
~~~

**Option B — Handle the entire `Exception` group with a specific policy:**

~~~java
static <E extends Exception> void logAndWrap(Task<E> task) {
    try {
        task.run();
    } catch (Exception e) {
        throw new IllegalStateException("Task failed", e);
    }
}
~~~

**Option C — Narrow the bound to a known family:**

~~~java
static <E extends IOException> void handleIO(
        ThrowingAction<E> task) {
    try {
        task.run();
    } catch (IOException e) {
        System.out.println("I/O: " + e.getMessage());
    }
}
~~~

Examples A/B assume `Task` exists, and Option C assumes `ThrowingAction` declares `throws E` as in the main program. The essence of the three approaches:

- A preserves the **checked contract `throws E`**.
- B intentionally converts the error into an unchecked wrapper **preserving the cause**.
- C handles a specific known exception class via the upper bound.

You should not mechanically turn `catch(E)` into `catch(Throwable)`. Catching `Error` as well significantly changes the handler's responsibility and can mask serious failures if the code simply logs and continues.

## 9. Multi-Catch and Type Parameters

Java 7+ supports multi-catch:

~~~java
try {
    perform();
} catch (IOException | SQLException e) {
    log(e);
}
~~~

This is an **illustrative snippet** where `perform` can throw two checked exception types and `log` is an appropriate method.

The alternatives such as `IOException` and `SQLException` must be valid exception types. Other multi-catch rules still apply: for example, you cannot combine two alternatives that have a subtype relationship, such as `IOException | Exception`.

A type variable cannot be an alternative:

~~~java
static <E extends Exception> void invalidMulti(
        ThrowingAction<E> task) throws E {
    try {
        task.run();
    } catch (E | RuntimeException e) { // DOES NOT COMPILE.
        System.out.println(e);
    }
}
~~~

This code is **intentionally invalid**. The `E` alternative is still a type variable and is invalid as a catch type. Adding `RuntimeException` does not change the rule.

### The type of a multi-catch variable is not a generic type parameter

For example, `catch (IOException | SQLException e)` gives `e` a type inferred by the compiler according to union catch rules (a common supertype suitable for accessing shared members). That is not equivalent to declaring a type variable `E` and selecting a specific subtype per call.

A multi-catch parameter is considered **implicitly final** within its scope; you cannot reassign `e`. This is a separate rule from forbidding `catch(E)` and the two compilation causes should not be confused.

## 10. A Generic Class Extending `Throwable` Is Also Invalid

Java has a related limitation: **you cannot create a generic class that is a subtype of `Throwable`**.

Counterexample:

~~~java
class TypedFailure<T> extends Exception {
    private final T value;

    TypedFailure(T value) {
        this.value = value;
    }
}
~~~

**The code above does not compile** because a generic class cannot be a subtype of `Throwable`. This holds even when the class extends `Exception` or `RuntimeException` instead of `Throwable` directly.

You cannot use `TypedFailure<String>` and `TypedFailure<Integer>` as two distinct exception types to catch at runtime, because type parameter information is not represented as distinct exception classes at runtime.

### Solution: non-generic exception, generic handling methods are allowed

Example:

~~~java
final class ValidationFailure extends Exception {
    private final String field;

    ValidationFailure(String field, String message) {
        super(message);
        this.field = field;
    }

    String field() {
        return field;
    }
}

static <T> T validateNotNull(T value)
        throws ValidationFailure {
    if (value == null) {
        throw new ValidationFailure(
                "value", "value must not be null");
    }
    return value;
}
~~~

These declarations can be placed inside a Java class. `ValidationFailure` is not generic; the `validateNotNull` method still has type parameter `T`, preserving the return value type on success.

If structured error data is needed, use an error code, enum, field name, or appropriate metadata instead of a generic type argument on the exception class itself.

### What about an exception with generic methods?

A **non-generic exception class** can still define regular generic methods, as long as they follow Java rules. What is forbidden is **an exception class itself having type parameters**, such as `MyException<T> extends Exception` — not every use of generics in exception-related code.

## 11. Lambdas and Checked Exceptions: The Target Type Is the Contract

A lambda does not carry an independent `throws` signature on its own. Its checked exception rules depend on the **functional interface** used as the target type.

For example, `java.util.function.Function<T,R>` has the method:

~~~java
R apply(T value);
~~~

It does not declare `throws IOException`. Therefore, the following snippet **does not compile** when `Files.readString` can throw checked `IOException`:

~~~java
java.util.function.Function<String, String> readText =
        path -> java.nio.file.Files.readString(
                java.nio.file.Path.of(path));
~~~

You can solve this in three ways depending on the contract.

### Approach A — Catch and convert to an unchecked wrapper

~~~java
java.util.function.Function<String, String> readText =
        path -> {
            try {
                return java.nio.file.Files.readString(
                        java.nio.file.Path.of(path));
            } catch (IOException cause) {
                throw new java.io.UncheckedIOException(
                        "Cannot read file", cause);
            }
        };
~~~

This illustrative snippet requires importing `IOException` or using its fully qualified name. `UncheckedIOException` is a standard unchecked exception that can hold `IOException` as its cause.

This approach fits when the API accepting `Function` does not allow checked exceptions to escape and the caller is designed to handle unchecked wrappers.

### Approach B — Use a functional interface with `throws E`

~~~java
@FunctionalInterface
interface CheckedFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
~~~

Caller:

~~~java
CheckedFunction<String, String, IOException> readText =
        path -> java.nio.file.Files.readString(
                java.nio.file.Path.of(path));
~~~

The lambda can throw checked `IOException` because `apply` on the target type declares `throws E` and `E` is chosen as `IOException`. A method using it can declare `throws E` accordingly.

### Approach C — Use a different API that models failure as a result

If "unable to read" is an expected branch that the caller must always handle, consider a two-state `Result` type or an API that provides a controlled fallback.

There is no single choice for every project. What matters is the **exception contract of the functional interface**, not assuming "lambdas do not support checked exceptions."

### Connection to `catch(E)`

Even when the target type has `throws E`:

~~~java
static <T, R, E extends Exception> R applyChecked(
        CheckedFunction<T, R, E> fn, T input) throws E {
    return fn.apply(input);
}
~~~

this is valid code. However, if the method wants to catch the error itself:

~~~java
static <T, R, E extends Exception> R broken(
        CheckedFunction<T, R, E> fn, T input) {
    try {
        return fn.apply(input);
    } catch (E e) { // Invalid.
        return null;
    }
}
~~~

The `catch(E)` limitation still applies. A type variable works in the `throws` clause, but not as the type of a catch parameter.

## 12. Distinguishing Overloads, Subtypes, and Tokens in Error-Handling APIs

Suppose a library has two handling strategies:

- One method that only handles `IOException`.
- One method that only handles `SQLException`.

Sometimes **specialized overloads** make an API easier to understand than a complex generic handler.

~~~java
static String fromIO(ThrowingSupplier<String, IOException> fn) {
    try {
        return fn.get();
    } catch (IOException e) {
        return "I/O fallback";
    }
}
~~~

A SQL API can use a dedicated functional interface and method for SQL. However, due to type erasure, **you cannot assume two overloads differing only by `ThrowingSupplier<String, IOException>` and `ThrowingSupplier<String, SQLException>` will have distinct runtime signatures**: they share the same raw type and can cause a *name clash* when the method name is the same.

Use clear method names, distinct interfaces, or an extra distinguishing parameter if overloading is truly needed.

### A token does not enable a typed catch by itself

Even when a method accepts `Class<E> expectedType`, this snippet is still invalid:

~~~java
static <E extends Exception> void wrongTokenCatch(
        Class<E> expectedType, ThrowingAction<E> task) {
    try {
        task.run();
    } catch (E e) { // Still a compile error.
        System.out.println(e);
    }
}
~~~

`Class<E>` only helps with **dynamic checking after catching with a valid type**. It does not change the syntax or type-checking rules of `catch`.

## 13. Broad Catches Can Mask Programming Errors

Suppose generic code does:

~~~java
static <E extends Exception> String unsafeFallback(
        ThrowingSupplier<String, E> supplier) {
    try {
        return supplier.get();
    } catch (Exception ignored) {
        return "default";
    }
}
~~~

This is a valid method, but **should only be applied when a fallback policy for every `Exception` is valid**. Because `RuntimeException extends Exception`, errors like `NullPointerException` or `IllegalArgumentException` are also swallowed.

When an error should only be recovered if it matches an expected class, use:

- `catch(IOException)` when the contract is already narrowed to I/O; or
- `Class<E>.isInstance` along with a clear policy for non-matching errors.

Do not infer that **because `E extends Exception`, every caught `Exception` is of type `E`**. A lambda can throw unchecked exceptions not listed in `throws E`.

## 14. Why Shouldn't You Use `(E) e` Casts Indiscriminately?

Suppose:

~~~java
static <E extends Exception> E unsafeCast(Exception e) {
    return (E) e;
}
~~~

This is a counterexample that may compile with an **unchecked cast warning** depending on compiler context. Because of type erasure, the cast statement does not guarantee checking the desired type argument at that point.

A caller might think it is receiving an `IOException`, while the actual object is another `Exception` subtype. The failure might only surface later when the value is cast again at the use site.

A safer approach:

~~~java
static <E extends Exception> E checkedCast(
        Exception e, Class<E> expectedType) {
    return expectedType.cast(e);
}
~~~

`Class.cast` checks the runtime class and throws `ClassCastException` if the object does not match. If you want to avoid throwing on mismatch, check `isInstance` first.

**You should not use reflection everywhere just to replace generic exception handling.** If only one group of errors is handled, `catch(IOException)` or `catch(SQLException)` is usually simpler.

## 15. Does `E extends Throwable` Differ from `E extends Exception`?

You can declare:

~~~java
static <E extends Throwable> void throwAny(E failure) throws E {
    throw failure;
}
~~~

This is valid Java. The type parameter `E` has bound `Throwable`, so it can be used in `throws` and `throw`.

However:

~~~java
static <E extends Throwable> void cannotCatchE(
        E failure) {
    try {
        throw failure;
    } catch (E caught) { // DOES NOT COMPILE.
        System.out.println(caught);
    }
}
~~~

Still invalid. Widening the bound from `Exception` to `Throwable` does not make `catch(E)` valid.

Furthermore, `catch(Throwable)` will also catch objects in the `Error` branch. That is a broad responsibility requiring a very specific policy if used at runtime/framework boundaries. In ordinary business code, catching `Exception` or a narrower class is usually more appropriate.

### `E extends RuntimeException` does not save `catch(E)` either

~~~java
static <E extends RuntimeException> void bad(
        E failure) {
    try {
        throw failure;
    } catch (E e) { // Still a compile-time error.
        System.out.println(e);
    }
}
~~~

Even though `E` is guaranteed to be unchecked, it is still a type variable. **Checked/unchecked is orthogonal to the type requirement of a catch parameter**; you cannot use one rule to erase the other.

## 16. Generic Methods Can Accurately Describe the Caller's Checked Exceptions

Example of a two-step processing chain where both steps declare they may throw `E`:

~~~java
@FunctionalInterface
interface CheckedStep<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void runBoth(
        CheckedStep<E> first,
        CheckedStep<E> second) throws E {
    first.run();
    second.run();
}
~~~

This is valid code. In the case where the caller uses `CheckedStep<IOException>` for both steps, `runBoth` can throw checked `IOException` by contract.

However, if the two steps have two different checked exception types, forcing both into a single `E` can lose specific static type information or force inferring a common supertype. You can design two type parameters:

~~~java
static <E1 extends Exception, E2 extends Exception>
void runTwoKinds(
        CheckedStep<E1> first,
        CheckedStep<E2> second) throws E1, E2 {
    first.run();
    second.run();
}
~~~

This snippet is valid. The caller must handle the corresponding checked exceptions based on usage.

Key point: **generic `throws` is very flexible**, but when you want to catch inside this method itself, you still must use a valid catch type, such as `catch(IOException)` when the class is known in advance, `catch(Exception)` when policy allows, or a custom-designed dynamic checking mechanism.

## 17. Common Compilation Errors to Recognize

### 17.1. `catch(E e)`

~~~java
static <E extends Exception> void f(ThrowingAction<E> action) {
    try {
        action.run();
    } catch (E e) { }
}
~~~

Invalid because the **catch parameter type is a type variable**.

### 17.2. `catch(E | IOException e)`

~~~java
static <E extends Exception> void f(ThrowingAction<E> action) {
    try {
        action.run();
    } catch (E | IOException e) { }
}
~~~

Invalid because `E` cannot be used as a multi-catch alternative.

### 17.3. `class Problem<T> extends Exception`

~~~java
class Problem<T> extends Exception {
}
~~~

Invalid because **a generic class cannot be a subtype of `Throwable`**.

### 17.4. `new E()`

~~~java
static <E extends Exception> E make() {
    return new E();
}
~~~

Invalid because an instance cannot be created directly from a type variable.

### 17.5. `instanceof E`

~~~java
static <E extends Exception> boolean matches(
        Throwable thrown) {
    return thrown instanceof E;
}
~~~

Invalid because a type variable is not a reifiable runtime type suitable for an `instanceof` check.

Errors 17.4 and 17.5 are not specific to `catch`, but stem from the same misconception: assuming the compiler has an independent runtime class object corresponding to the type variable `E`.

### 17.6. Lambda throwing a checked exception into standard `Function`

~~~java
java.util.function.Function<String, String> read =
        path -> java.nio.file.Files.readString(
                java.nio.file.Path.of(path));
~~~

Invalid because `Function.apply` does not have a checked `throws IOException`.

### 17.7. Multi-catch of two types with a subtype relationship

~~~java
try {
    something();
} catch (IOException | Exception e) {
    System.out.println(e);
}
~~~

Invalid because `IOException` is a subtype of `Exception`. This is a **different** rule from type variables, but often appears when learners try to replace `catch(E)` with an overly broad union.

## 18. FAQ on Handling Type Parameters and Exceptions

**Q: Can I use `catch (T e)` if `T extends IOException`?**  
No. `T` is still a type variable; catch `IOException` if you want to handle the entire I/O family.

**Q: Can I use `catch (E e)` if the method accepts `Class<E>`?**  
No. The token only helps check **inside a valid catch** or normal handling code.

**Q: Does `throws E` require `E extends Exception`?**  
Not necessarily; an upper bound of `Throwable` or an appropriate subtype also works. For example, `<E extends Throwable> ... throws E` is valid.

**Q: Why is `catch (Exception e)` valid while `catch (E e)` is not?**  
`Exception` is an exception class that can be used for a handler. `E` is a type variable, which is forbidden as a catch parameter type.

**Q: Can a generic class declare a method that throws a type parameter?**  
Yes, if the type parameter has an appropriate bound. For example, a generic functional interface with `E extends Exception` can have `run() throws E`.

**Q: Does Java have generic exception classes like `MyException<T>`?**  
No, if that class extends `Throwable` directly or indirectly. Use a non-generic exception class, and keep metadata or use generic methods externally.

**Q: Does `IOException.class` also match subtypes like `FileNotFoundException`?**  
Yes, if you use `Class.isInstance`; this is the check corresponding to the subtype relationship at runtime.

**Q: What about using `getClass() == expectedType`?**  
It matches only the **exact** class, not subtypes. Choose the behavior according to your contract.

**Q: Should I always catch `Exception` and then check `Class<E>`?**  
No. If the class to handle is already known, catching a concrete type is easier to read, has clearer responsibility, and carries less risk.

**Q: Can a lambda declared as `ThrowingSupplier<T,IOException>` still throw `NullPointerException`?**  
Yes. Unchecked exceptions are not restricted to the checked `throws IOException`. Therefore, a broad handler should not assume every caught error is an `IOException`.

**Q: Does `catch(Throwable)` solve this limitation?**  
Syntactically it is a valid handler, but its scope is very broad, including `Error`. It is not equivalent to catching `E` specifically and should not be the default replacement.

**Q: Why should the cause be preserved when wrapping errors in a generic helper?**  
So you do not lose the original error information and stack trace. Use the constructor `new IllegalStateException("...", caught)`, rather than only concatenating `caught.getMessage()` into a string.

## 19. Knowledge Check

1. Why is `catch (E e)` invalid when `E extends Exception`?
2. Is `throws E` valid with `E extends Exception`?
3. Is `throw error;` with a variable `error` of type `E extends Exception` valid?
4. Does `catch (IOException e)` catch a subtype of `IOException`?
5. If `E extends IOException`, can you use `catch(E)`?
6. Can `catch (Exception e)` in a generic method also catch unchecked `RuntimeException`s?
7. Why is type erasure related to not being able to use `E` as a catch type?
8. Which two operations does `Class<E>` provide for safe checking and casting?
9. Does `Class.isInstance` accept subclasses?
10. Why shouldn't you always return a fallback after any `Exception`?
11. Is a declaration of the form `<E extends Throwable> void f() throws E` valid?
12. Why does `class MyException<T> extends Exception` not compile?
13. Can a type parameter be used in the `throws` clause of a generic functional interface?
14. Does standard `Function<T,R>` allow a lambda to throw a checked `IOException` out?
15. If you want a lambda to throw a checked `IOException`, how should you change the target interface?
16. Is `catch (IOException | SQLException e)` valid when both errors can be thrown?
17. Why is `catch (IOException | Exception e)` invalid?
18. Why is `catch (E | IOException e)` invalid?
19. Can a `ThrowingSupplier<String,IOException>` throw an unchecked `IllegalArgumentException`?
20. Does `catch(Throwable)` mean the same thing as `catch(E)`?
21. Does `(E) exception` reliably check the runtime type argument?
22. When should you prefer catching a concrete class over using a token?
23. Is `throws E1, E2` in a method with two bounded type parameters valid?
24. Can a non-generic exception class be thrown from a generic method?
25. If you only need to log an error and rethrow/propagate it, do you necessarily have to write a generic catch yourself?

### Suggested Answers

1. Because a type variable cannot be used as the parameter type of a catch clause.
2. Yes.
3. Yes.
4. Yes.
5. No; use `catch(IOException)` if appropriate.
6. Yes.
7. Generic type arguments do not create separate runtime handler classes for each instantiation.
8. `isInstance` and `cast`.
9. Yes.
10. Because it can mask programming/unchecked errors or errors that have no safe fallback.
11. Yes, within a valid declaration structure.
12. A generic class cannot extend `Throwable` directly or indirectly.
13. Yes, for example `void run() throws E`.
14. No; `Function.apply` does not declare checked exceptions.
15. Use a custom interface with `throws E`, or catch and wrap according to the contract.
16. Yes.
17. Because the two alternatives have a subtype relationship.
18. Because `E` is a type variable.
19. Yes, unchecked exceptions are not required to be declared.
20. No; `Throwable` catches errors outside the scope of `E`, including `Error`.
21. No; it may only be an unchecked cast due to type erasure.
22. When the error type is already known at the site where the handler is written.
23. Yes, with appropriate bounds and checked exception handling at the caller.
24. Yes.
25. No; you can use `throws E` and let the caller handle it, or catch a concrete type when needed.

## 20. Key Takeaways

**In Java Generics, `throws E` is allowed while `catch (E e)` is forbidden if `E` is a type parameter.** Upper bounds such as `E extends Exception`, `E extends IOException`, or `E extends RuntimeException` do not turn `E` into a valid catch type. Use `catch` with a **concrete exception class** when the error family is known, use `throws E` to preserve the checked exception contract of a generic method or functional interface, and only use `Class<E>.isInstance/cast` when you genuinely need to match a caller-specified error type at runtime. Also avoid defining generic exception classes that extend `Throwable`; keep exception types non-generic and place flexibility in methods or interfaces.
