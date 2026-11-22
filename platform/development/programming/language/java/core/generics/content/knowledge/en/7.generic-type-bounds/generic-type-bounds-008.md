# `Throwable` Bounds in `throws` Clauses of Generic Methods (Java)

## 1. Objectives and Purpose

In Java, a generic method can declare a **type parameter representing the exception type** that the method may throw. Instead of declaring an overly broad exception such as `throws Exception`, you can write `throws E` to preserve the exception type information from an inner operation out to the call site.

After this lesson, you should understand:

- The condition for a type variable to be valid in `throws` and the differences among `Throwable`, `Exception`, and `RuntimeException`.
- How the compiler checks checked exceptions when `E` is a type variable.
- How to propagate exceptions through callbacks/lambdas using a generic method without forcing callers to handle an overly broad `Exception`.
- Why you cannot `catch (E e)` or create `Exception<T>` extending `Throwable`; and common pitfalls around type inference.

## 2. Foundational Java Rules

According to the Java Language Specification (JLS) §8.4.6, every type appearing in a `throws` clause must be an **exception class** or a **type variable that is a subtype of `Throwable`**. Therefore, the basic syntax is:

~~~java
static <E extends Throwable> void raise(E error) throws E {
    throw error;
}
~~~

In this declaration:

1. `<E extends Throwable>` declares a type parameter of the **method**, bounding `E` to types derived from `Throwable`.
2. Parameter `E error` requires the passed-in object to have a type compatible with `E`.
3. `throw error` throws the **actual object**; `throws E` declares that possibility to the compiler and callers.
4. `E` is determined via the argument, an explicit type argument, or the type inference context. `E` is not a new exception class.

More specific bounds can be used:

~~~java
static <E extends Exception> void perform(E error) throws E {
    throw error;
}

static <E extends java.io.IOException> void ioOnly(E error) throws E {
    throw error;
}
~~~

| Bound declaration | What `E` can represent | Practical meaning |
| --- | --- | --- |
| `E extends Throwable` | `Exception`, `Error`, and subclasses | Broadest; choose only when the API genuinely needs to propagate `Error` as well. |
| `E extends Exception` | Checked exceptions under `Exception` and `RuntimeException` | Usually suitable for callbacks that can fail. |
| `E extends IOException` | `IOException` and subclasses | Restricted to the I/O error family. |
| `E extends RuntimeException` | Runtime exceptions | Unchecked exceptions only; callers are not forced to declare/catch. |

**Checked vs. unchecked:** `RuntimeException` and its subclasses, as well as `Error` and its subclasses, are unchecked. Other subtypes of `Throwable` are checked; the compiler requires proving that they are caught or declared. Not every `E extends Exception` is checked, because `RuntimeException extends Exception`.

An unbounded type parameter implicitly extends `Object`, so `<E> void f() throws E` is **invalid**: the compiler cannot guarantee `E` is a subtype of `Throwable`. Likewise, `String`, `Object`, or non-exception parameterized types cannot appear in `throws`.

## 3. How Does `throws E` Propagate Checked Exceptions to the Caller?

Suppose we call:

~~~java
try {
    raise(new java.io.IOException("network unavailable"));
} catch (java.io.IOException ex) {
    System.out.println(ex.getMessage());
}
~~~

The compiler infers `E` from the `IOException` object. Because `IOException` is a checked exception, the call site must catch or declare it accordingly. The `throws E` clause does not make the exception unchecked and does not bypass checked-exception checking rules.

When the caller can specify `E` explicitly, it can also pass an explicit type argument, such as `GenericThrowsDemo.<IOException>raise(...)` if `raise` is declared in class `GenericThrowsDemo`. The type argument must satisfy the type bound and be compatible with the actual arguments.

**Important detail:** `throws E` only *declares the type of exception that may arise*. It does not automatically prove every `throw new IOException(...)` in the method body is valid when `E extends Exception`, because the caller could choose `E = java.sql.SQLException`. The method body must throw an object whose type is compatible with **every** valid assignment of `E`, or declare/catch the specific exception separately.

## 4. Runnable Example: Preserving Exact Checked Exception Types Through Callbacks

In the example below, `ThrowingSupplier<T, E>` can return `T` or throw `E`. The generic method `execute` preserves this contract; the lambda calls an operation that throws `IOException`, so the caller catches the specific `IOException`.

Save the file **GenericThrowsDemo.java**:

~~~java
import java.io.IOException;

public class GenericThrowsDemo {
    @FunctionalInterface
    interface ThrowingSupplier<T, E extends Exception> {
        T get() throws E;
    }

    static <T, E extends Exception> T execute(ThrowingSupplier<T, E> work) throws E {
        return work.get();
    }

    static String read(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("read failed");
        }
        return "OK";
    }

    public static void main(String[] args) {
        try {
            System.out.println("Result: " + execute(() -> read(false)));
            execute(() -> read(true));
        } catch (IOException ex) {
            System.out.println("Caught IOException: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac -encoding UTF-8 GenericThrowsDemo.java
java GenericThrowsDemo
~~~

Standard output:

~~~text
Result: OK
Caught IOException: read failed
~~~

Execution flow:

1. `read(false)` returns `"OK"`, so `execute` returns normally.
2. `read(true)` throws an `IOException`. `get() throws E` allows `execute` to propagate this error outward.
3. The compiler uses the lambda's constraint to infer the appropriate `E`; `catch (IOException ex)` handles the exact error in the example.
4. If this checked-exception handling is removed, the caller must declare `throws IOException` (or a compatible supertype), or compilation will fail.

Compared to an API writing only `static <T> T execute(Callable<T> work) throws Exception`, keeping type variable `E` lets callers work with a more specific checked exception type instead of having to handle broad `Exception`. Note that `java.util.concurrent.Callable.call()` is declared `throws Exception`; writing an interface with its own `E` is how you preserve the callback's exact exception contract.

## 5. Limitations to Remember

### 5.1. `E` must have a valid bound

The following declarations are invalid:

~~~java
// INVALID: E implicitly extends Object, not guaranteed to be Throwable.
static <E> void bad1() throws E {}

// INVALID: String does not extend Throwable.
static void bad2() throws String {}

// INVALID: T is just an arbitrary data type, cannot be used as an exception type.
static <T> void bad3(T value) throws T {}
~~~

The right approach is to declare a bound, such as `<E extends Exception>` or `<E extends Throwable>`, and ensure the method body obeys the contract.

### 5.2. You cannot catch with `catch (E e)`

The following snippet **does not compile**:

~~~java
static <E extends Exception> void broken(E error) {
    try {
        throw error;
    } catch (E ex) { // INVALID: cannot use a type variable as a catch type
        System.out.println(ex.getMessage());
    }
}
~~~

JLS §14.20 requires the exception type in `catch` to be a proper class type, not a type variable. You can catch a concrete class `catch (Exception ex)` or let the exception propagate via `throws E`. When catching broadly, keep in mind that catching `Exception` has broad scope and does not include `Error`.

### 5.3. You cannot create generic exception classes

The following declaration is **invalid**:

~~~java
// INVALID: a generic class cannot directly or indirectly extend Throwable.
class AppFailure<T> extends Exception {}
~~~

You can define a **non-generic** exception class and store extra information in fields with concrete types; or use a generic result object, such as `Result<T>`, if business logic needs to carry typed data.

### 5.4. You cannot arbitrarily instantiate `new E()` or throw an arbitrary subtype

~~~java
// INVALID: IOException is not necessarily a specific E.
static <E extends Exception> void brokenThrow() throws E {
    throw new java.io.IOException("read failed");
}

// INVALID: Java does not allow calling a type variable's constructor.
static <E extends Exception> void brokenNew() throws E {
    throw new E();
}
~~~

Use an `E` object passed in by the caller, invoke a callback declared `throws E`, or if it genuinely always throws `IOException`, declare `throws IOException` directly. Do not add generics to an API when there is no exception type information to thread through.

### 5.5. Checked exceptions when overriding remain restricted

Generics do not allow an overriding method to widen the set of checked exceptions beyond the parent class/interface method's contract. When overriding, the compiler still enforces the `throws` compatibility rules of JLS §8.4.8.3. If an interface does not permit throwing checked exceptions, you cannot make an override valid merely by adding `<E extends Exception> ... throws E`.

## 6. Be Careful with Type Inference and "Sneaky Throw"

Generic type inference has special rules for type variables appearing in `throws`. Per JLS §18.1.3 and §18.4, when no tighter constraint exists, the compiler may infer `RuntimeException` for an inference variable appearing in `throws` with compatible upper bounds. This is **not** a runtime conversion of an `IOException` into a `RuntimeException`.

A dangerous pattern is:

~~~java
@SuppressWarnings("unchecked")
static <E extends Throwable> void sneakyThrow(Throwable error) throws E {
    throw (E) error;
}
~~~

Here type `E` **does not appear in the input parameter**; the cast `(E) error` is unchecked. A call without an explicit type argument can be inferred with `E = RuntimeException`, while the actual object remains a checked exception (such as `IOException`) at runtime. This breaks checked-exception handling expectations at the call site; **it should not be used as a way to "bypass" checked exceptions in ordinary APIs**.

Compare with the safer version:

~~~java
static <E extends Throwable> void throwExact(E error) throws E {
    throw error;
}
~~~

With `throwExact(new IOException("failed"))`, the argument's type forces inference to reflect `IOException`. Do not guess inferred types by intuition when using lambdas or multiple error sources: check the method declaration, bounds, and compile errors at the call site.

## 7. When Should You Use `throws E`?

**Use it** when designing helpers that coordinate operations capable of throwing different checked exception types: callbacks, template methods, resource handling with custom contracts, or methods forwarding typed errors. A classic example is the pair `ThrowingSupplier<T, E>` and `execute(...) throws E`.

**Use `throws IOException`, `SQLException`, or a concrete error class** when the method has a fixed set of errors and does not need to preserve an exception type from a callback or generic argument. The more exact and simple the API, the easier it is to use.

**Avoid** bounding `E extends Throwable` when specifying business error handling: `Throwable` also includes `Error`, which usually indicates serious errors that applications should not catch to recover from. `E extends Exception` usually conveys intent better.

## 8. Check Your Understanding

1. Why doesn't `<E> void run() throws E` compile? **Because `E` implicitly has bound `Object`, which is not guaranteed to be a subtype of `Throwable`.**
2. Why is `<E extends Exception> void run(E e) throws E` valid? **Because `E` is guaranteed to belong to the `Throwable` hierarchy, and the method body can throw the object `e` itself.**
3. Does `throws E` allow `catch (E e)`? **No.** The two positions follow different syntax and type rules.
4. Can you declare `class Failure<T> extends Exception`? **No.** Generic classes cannot extend `Throwable` directly or indirectly.
5. Does generic `throws` eliminate the obligation to handle checked exceptions? **No.** When used properly, the compiler still checks checked exceptions after determining the appropriate type at the call site.

## References

- [JLS Java SE 17 §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): permits a type variable in `throws` if it is a subtype of `Throwable`.
- [JLS Java SE 17 §14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): forbids a type variable as the type in `catch`.
- [JLS Java SE 17 §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): inference rules, including `throws` bounds and choosing `RuntimeException` when appropriate.
- [Oracle Java Tutorials — Restrictions on Generics](https://docs.oracle.com/javase/tutorial/java/generics/restrictions.html): forbids generic classes from extending `Throwable`; illustrates valid `throws T`.