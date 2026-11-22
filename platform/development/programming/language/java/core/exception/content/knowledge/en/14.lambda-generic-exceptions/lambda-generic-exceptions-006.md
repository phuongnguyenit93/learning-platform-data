# Generic Methods with a Type Parameter Extending `Throwable` in Java

## 1. The Problem Statement

Java allows declaring a **type parameter** in a generic method with an upper bound of `Throwable`:

```java
static <E extends Throwable> void propagate(E failure) throws E {
    throw failure;
}
```

Here, `E` is not the name of a concrete exception class. It is a **type parameter** inferred or specified when the method is called. The condition `E extends Throwable` ensures that every actual type used in place of `E` is `Throwable` or one of its subclasses, so the object can be thrown with `throw` and appear in the `throws E` clause.

Some situations where this feature is needed: a helper that wants to propagate the **exact exception type** of the caller; a functional interface whose method throws a checked exception; a generic callback API that wants to forward exceptions without forcing every caller to handle an overly broad `Exception`.

However, because `E` is a type variable, Java has important limitations: you cannot `catch (E e)`, you cannot `new E()`, and the checked exception checking system must rely on **type bounds and inference context**. Generic `throws E` should not be used merely as a trick to "bypass" checked exceptions.

Objectives:

- Distinguish between `<E extends Throwable>`, `throws E`, and a `throw expression`.
- Understand the meaning of `Throwable`, `Exception`, `RuntimeException`, and specific subtype bounds.
- Create generic methods that preserve the exception type when propagating, with checked and unchecked examples.
- Build a functional interface with an exception type parameter so lambdas can throw checked exceptions.
- Determine the `try/catch` or `throws` obligation at the caller through the inferred/specified generic type.
- Understand why `catch (E e)` and `new E()` are invalid.
- Know how to construct exceptions via a factory instead of instantiating directly from a type variable.
- Grasp the limitations when generic methods are overridden, functional interface methods are specialized, and when using standard `Runnable`/`Function`.
- Recognize the risks of *sneaky throw*, unchecked casts, and type parameter inference in `throws`.

All complete programs below are designed for **Java 17+**, with `javac`/`java` commands and exact `stdout` outputs. Non-standalone snippets and intentionally invalid examples are clearly marked.

## 2. Reading Generic `throws` Syntax Correctly

Consider:

```java
public static <E extends Throwable> void rethrow(E error) throws E {
    throw error;
}
```

Let us break it down into its components:

| Syntax | Meaning |
| --- | --- |
| `<E extends Throwable>` | Declares type parameter `E` with upper bound `Throwable` |
| `E error` | Method parameter whose static type is the type variable `E` |
| `throws E` | Declares that the method can propagate an exception of type `E` |
| `throw error;` | Executes throwing the **object** referenced by the variable `error` |

The `extends` keyword in a **type parameter bound** allows selecting appropriate subclasses of `Throwable`. It is **not** a `throw` statement and does not mean "catch every throwable".

For example, when the caller passes a variable with static type `IOException`:

```java
java.io.IOException failure = new java.io.IOException("disk failed");
rethrow(failure);
```

This is a snippet placed inside an appropriate method. The compiler can infer `E = IOException` in the call above. Therefore, the call carries the checked exception obligation of `IOException`: it must be caught or declared if in a context that requires it.

If the caller passes `new IllegalArgumentException(...)`, the propagated exception type is unchecked; writing `throws` at the caller is not required.

### Important: An upper bound does not turn the object into a new `Throwable`

`rethrow(E error)` throws the **exact same object** it receives, without creating another exception. Fields such as message, cause, stack trace, and suppressed exceptions currently on that object are preserved. The type parameter is purely a compile-time type-checking tool.

## 3. `Throwable`, `Exception`, and `RuntimeException` in Generic Bounds

A simplified type tree:

```text
Throwable
├── Error                       [unchecked]
│   └── AssertionError
└── Exception
    ├── IOException             [checked]
    │   └── FileNotFoundException
    ├── SQLException            [checked]
    └── RuntimeException        [unchecked]
        ├── IllegalArgumentException
        └── IllegalStateException
```

This is not the entire Java hierarchy, only the types needed to understand bounds.

Generic declarations:

```java
static <E extends Throwable> void a(E failure) throws E {
    throw failure;
}

static <E extends Exception> void b(E failure) throws E {
    throw failure;
}

static <E extends RuntimeException> void c(E failure) throws E {
    throw failure;
}

static <E extends java.io.IOException> void d(E failure) throws E {
    throw failure;
}
```

These are **four valid illustrative methods**, placed in a Java class. They do not have the same type scope:

- `E extends Throwable` allows `IOException`, `RuntimeException`, `Error`, or `Throwable` itself and appropriate subclasses.
- `E extends Exception` excludes the `Error` branch, but **still includes** checked exceptions and subclasses of `RuntimeException`.
- `E extends RuntimeException` restricts to the unchecked branch, so exceptions of type `E` do not create a checked exception obligation at the caller.
- `E extends IOException` restricts to checked I/O types, such as `IOException` and `FileNotFoundException`.

**Do not infer that "every `E extends Exception` is checked".** `RuntimeException` is a subclass of `Exception` yet is unchecked.

Similarly, **`E extends Throwable` does not force every call to catch `Throwable`**. The obligation can be more specific when `E` is inferred or explicitly specified; if the static type at the call site is indeed `Throwable`, the caller may have to handle/declare that broad scope.

## 4. Complete Program: Rethrowing the Exact Type Passed

Create the file **`GenericRethrowDemo.java`**:

```java
import java.io.IOException;

public class GenericRethrowDemo {
    static <E extends Throwable> void rethrow(E failure) throws E {
        throw failure;
    }

    public static void main(String[] args) {
        IOException io = new IOException("disk offline");

        try {
            rethrow(io);
        } catch (IOException failure) {
            System.out.println("checked=" + failure.getMessage());
        }

        try {
            rethrow(new IllegalArgumentException("bad argument"));
        } catch (IllegalArgumentException failure) {
            System.out.println("unchecked=" + failure.getMessage());
        }

        try {
            rethrow(new AssertionError("broken invariant"));
        } catch (AssertionError failure) {
            System.out.println("error=" + failure.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac GenericRethrowDemo.java
java GenericRethrowDemo
```

`stdout`:

```text
checked=disk offline
unchecked=bad argument
error=broken invariant
```

Analysis:

1. The call `rethrow(io)` has an argument of type `IOException`, so the matching generic type is this checked exception. `catch (IOException)` handles it.
2. `IllegalArgumentException` is unchecked, still thrown as that exact object, and does not require declaring `throws`.
3. `AssertionError` also belongs to `Throwable` but via the `Error` branch and is unchecked. The example intentionally catches it in `main` to illustrate the type; normal applications **should not treat every Error as recoverable**.

The `rethrow` method does not create a new exception, does not turn checked into unchecked, and does not change the root cause. It simply allows a generic method to declare an error type tied to the type parameter of the call itself.

### The static type of the argument affects the handling obligation

If a variable is declared as `Throwable` even though at runtime it holds an `IOException`:

```java
Throwable failure = new java.io.IOException("disk");
rethrow(failure);
```

This is a snippet. The compiler sees that the type argument can be `Throwable`, so the calling context must handle/declare a type compatible with `Throwable`, unless another valid inference context applies. Java does not definitively infer `IOException` based solely on a runtime object.

To preserve specific checked exception information when an API needs it, do not arbitrarily change every parameter to `Throwable`. The generic contract depends on **the compile-time expression type**.

## 5. Why Is `throws E` Needed If `E extends Throwable` Is Already Present?

The type bound only proves that `E` is a throwable type; it **does not automatically declare** that the method will propagate a checked exception outward. The following code example **intentionally does not compile**:

```java
static <E extends Throwable> void broken(E failure) {
    throw failure; // The compiler may require declaring/catching E.
}
```

Because `E` could be `IOException` or another checked `Throwable`, the method cannot ignore the obligation. It must declare:

```java
static <E extends Throwable> void valid(E failure) throws E {
    throw failure;
}
```

If replaced with `E extends RuntimeException`, the thrown exception is unchecked:

```java
static <E extends RuntimeException> void validUnchecked(E failure) {
    throw failure;
}
```

This is a valid example of a tighter bound, where `throws E` is not required. Even so, you can write `throws E` to document the API; it does not turn an unchecked exception into a checked one.

### `throws E` and `throws Throwable` are not always equivalent

`throws Throwable` advertises a very broad type to every caller. `throws E` can provide a precise link between the exception type of a parameter or callback and the caller's responsibility. This is the major value of generic exception types: **not unnecessarily widening the error contract**.

However, when `E` is only bounded by `Throwable` and cannot be narrowly inferred, the compiler may still have to check a broad exception type. Generics do not guarantee the contract is always narrow; the choice of type argument and API signature is what determines it.

## 6. Lambdas with Checked Exceptions: A Suitable Functional Interface Is Needed

Common Java functional interfaces such as `Runnable` or `java.util.function.Function<T,R>` **do not declare checked exceptions** in their abstract methods. Therefore, you cannot directly throw an unhandled `IOException` from a lambda body assigned to `Runnable`:

```java
Runnable task = () -> {
    throw new java.io.IOException("cannot read"); // DOES NOT COMPILE.
};
```

This is an **intentionally non-compiling** example. `Runnable.run()` does not have `throws IOException`.

A proper design solution is to declare **your application's own functional interface** with an exception type parameter:

```java
@FunctionalInterface
interface ThrowingAction<E extends Throwable> {
    void run() throws E;
}
```

Then create a generic method that invokes the callback:

```java
static <E extends Throwable> void execute(ThrowingAction<E> action)
        throws E {
    action.run();
}
```

These two declarations are valid. They maintain the relationship:

```text
ThrowingAction<IOException>
          |
          v
execute(action) throws IOException
          |
          v
caller catch IOException / throws IOException
```

The type `E` does not always have to be `Throwable`; if the API only needs checked/unchecked types under `Exception` and does not want to accept `Error` as a design choice, you can choose `E extends Exception`.

## 7. Complete Program: Lambda Throwing `IOException` via a Generic Helper

Create the file **`GenericLambdaThrowsDemo.java`**:

```java
import java.io.IOException;

public class GenericLambdaThrowsDemo {
    @FunctionalInterface
    interface ThrowingSupplier<R, E extends Throwable> {
        R get() throws E;
    }

    static <R, E extends Throwable> R supply(
            ThrowingSupplier<R, E> supplier) throws E {
        return supplier.get();
    }

    public static void main(String[] args) {
        ThrowingSupplier<String, IOException> failingRead = () -> {
            throw new IOException("read failed");
        };

        ThrowingSupplier<String, IOException> successfulRead =
                () -> "data";

        try {
            System.out.println(supply(failingRead));
        } catch (IOException failure) {
            System.out.println("failure=" + failure.getMessage());
        }

        try {
            System.out.println("success=" + supply(successfulRead));
        } catch (IOException failure) {
            System.out.println("unexpected IO");
        }
    }
}
```

```bash
javac GenericLambdaThrowsDemo.java
java GenericLambdaThrowsDemo
```

`stdout`:

```text
failure=read failed
success=data
```

To make the output and inference clear, the variables `failingRead` and `successfulRead` are **explicitly typed** as `ThrowingSupplier<String, IOException>`.

Explanation:

- `R` represents the return data type of the lambda (`String`).
- `E` represents the **exception type** the lambda is allowed to propagate (`IOException`).
- `ThrowingSupplier.get()` declares `throws E`, so the lambda body can throw `IOException`.
- `supply` declares `throws E` and propagates the error without casting it to `Exception`.
- The caller knows the context is `IOException` and can write `catch (IOException)`.
- Even the succeeding lambda has an **interface type** that allows `IOException`, so a call through that type must satisfy the checked exception contract. The compiler does not skip the obligation just because the current lambda only executes `return "data"`.

### Can the helper be called directly with a lambda?

You can write:

```java
String value = GenericLambdaThrowsDemo.supply(() -> "ok");
```

This is an illustrative snippet in an appropriate context. With a direct lambda, Java can use the target context and inference constraints to choose type arguments. When you want the error contract to be readable and stable across refactors, **explicitly typed variables** or type witnesses (`ClassName.<R,E>method(...)`) may be better than relying solely on subtle inference.

You should not assume Java will always infer the exact checked exception type you expect in every complex lambda expression; verify with the compiler on the actual signature.

## 8. Generic Functions Accepting Multiple Actions and Preserving the Same Error Type

You can reuse a single type parameter for multiple callbacks sharing the same contract:

```java
@FunctionalInterface
interface Step<E extends Exception> {
    void run() throws E;
}

static <E extends Exception> void runTwo(Step<E> first, Step<E> second)
        throws E {
    first.run();
    second.run();
}
```

This is a valid declaration snippet. `E extends Exception` is appropriate when the API wants to focus on the exception group rather than `Error`. If both steps have type `Step<IOException>`, the caller only has to handle `IOException`.

However, two steps with **two different checked exception branches** can force the inference of a single shared `E` to choose a sufficiently broad supertype (such as `Exception`) or fail to fit a specific context. When an API truly needs to keep the two types independent, declare **two exception type parameters**:

```java
static <E1 extends Exception, E2 extends Exception> void runTwoDifferent(
        Step<E1> first, Step<E2> second)
        throws E1, E2 {
    first.run();
    second.run();
}
```

This is a valid method snippet (with `Step` already defined). It clearly expresses: the first step is allowed to throw `E1`, and the second step is allowed to throw `E2`. Generics can express the **relationship** between exceptions in callbacks and exceptions of the helper, but you must choose the number of type parameters that accurately reflects the contract.

### Runnable program: two independent checked exception types

Create the file **`TwoGenericExceptionsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class TwoGenericExceptionsDemo {
    @FunctionalInterface
    interface Step<E extends Exception> {
        void run() throws E;
    }

    static <E1 extends Exception, E2 extends Exception> void runBoth(
            Step<E1> first, Step<E2> second) throws E1, E2 {
        first.run();
        second.run();
    }

    public static void main(String[] args) {
        Step<IOException> read = () -> {
            System.out.println("read");
        };

        Step<SQLException> query = () -> {
            throw new SQLException("query failed");
        };

        try {
            runBoth(read, query);
        } catch (IOException failure) {
            System.out.println("IO=" + failure.getMessage());
        } catch (SQLException failure) {
            System.out.println("SQL=" + failure.getMessage());
        }
    }
}
```

```bash
javac TwoGenericExceptionsDemo.java
java TwoGenericExceptionsDemo
```

`stdout`:

```text
read
SQL=query failed
```

`runBoth` does not catch or alter the error types. It propagates `E1` and `E2` outward. When `read` succeeds and then `query` throws `SQLException`, the caller receives the exact SQL type. If `read` fails with `IOException`, the `query` step will **not run**, unless the method is specifically designed to catch/coordinate it.

This pattern is useful when a callback library has multiple steps that **genuinely need separate error types**. Do not collapse them into `throws Exception` if generics can describe the contract accurately without making the API overly difficult to use.

## 9. The Bound `E extends Throwable` Still Obeys Checked Exception Checking

`throws E` is not an exemption from compile-time checking. If the caller has a concrete type argument `IOException`, the caller must handle that checked exception.

Example:

```java
static <E extends Throwable> void fail(E failure) throws E {
    throw failure;
}

static void caller() {
    fail(new java.io.IOException("disk")); // ERROR: missing catch/throws.
}
```

This is a snippet that **intentionally does not compile** when placed in a class: `caller()` neither catches nor declares `IOException`.

Fix it with:

```java
static void caller() throws java.io.IOException {
    fail(new java.io.IOException("disk"));
}
```

or:

```java
static void caller() {
    try {
        fail(new java.io.IOException("disk"));
    } catch (java.io.IOException failure) {
        System.out.println(failure.getMessage());
    }
}
```

Both fixes are valid method snippets if placed alongside the definition of `fail` above.

### Where are checked exceptions in a lambda checked?

For a lambda, the compiler checks the lambda body against **the abstract method of the functional interface** and its corresponding `throws` clause. When the interface does not declare a checked exception, throwing `IOException` is invalid. When the interface declares `throws E` with an appropriate type, the lambda can throw `IOException`, while the caller of the generic helper must satisfy the inferred `throws E` contract.

This explains why merely writing:

```java
static <E extends Throwable> void invoke(Runnable task) throws E {
    task.run();
}
```

does not make `Runnable` automatically allow checked exceptions in lambdas. `Runnable.run()` still **does not declare checked exceptions**. Writing generic `throws E` on the **helper method** does not alter the functional method signature of `Runnable`. This is a syntactically valid method snippet, but it **does not grant checked exception capability to Runnable**.

## 10. Cannot `catch (E e)`: A Type Variable Is Not a Valid Catch Type

The following snippet **intentionally does not compile**:

```java
static <E extends Throwable> void badCatch(E value) {
    try {
        throw value;
    } catch (E failure) { // ERROR: cannot catch using a type variable.
        System.out.println(failure.getMessage());
    }
}
```

Java does not allow using a type variable `E` as the parameter type in `catch`. The reason relates to type erasure and the rule that catch must use an exception type suitable at runtime; a generic type parameter cannot be used in this position like a concrete exception class.

**Do not confuse:** `throws E` is valid; `catch (E e)` is invalid. `throws` is a compile-time checking contract, whereas `catch` must have an exception type for the runtime matching mechanism.

### Valid ways to handle it

If you want to forward the error as-is, you do not need `catch`:

```java
static <E extends Throwable> void passThrough(E error) throws E {
    throw error;
}
```

If you need to catch a general error to add context, you can catch a valid concrete type (`Exception` or `Throwable`) and must **rethrow/wrap in a way compatible with the method's checked exceptions**:

```java
static <E extends Throwable> void traceAndPass(
        ThrowingAction<E> action) throws E {
    action.run();
}
```

This is a method snippet using `ThrowingAction` from the previous section, showing how you do not need to catch just to propagate an error. If you want to handle an error of **a specific type**, use a concrete exception class at a boundary that knows that type, such as `catch (IOException e)` when there is a corresponding path throwing IOException.

### `instanceof E` is also invalid

`E` has no runtime class token to use directly with `instanceof`:

```java
static <E extends Throwable> boolean isExpected(Throwable failure) {
    return failure instanceof E; // COMPILE ERROR.
}
```

If you need to check the runtime type of `E`, the API can accept **`Class<E>`**:

```java
static <E extends Throwable> boolean isExpected(
        Throwable failure, Class<E> expected) {
    return expected.isInstance(failure);
}
```

This is a valid method. `Class<E>` carries the concrete class token into runtime, whereas a plain type parameter `E` is erased.

## 11. Cannot `new E()`: Use an Exception Factory

A generic type parameter cannot be instantiated directly:

```java
static <E extends Throwable> E create() {
    return new E(); // COMPILE ERROR.
}
```

The reason is not merely "Java dislikes generics". With `E`, the compiler does not know which constructors exist, and `E` is a type variable subject to erasure at runtime. Even knowing `E extends Throwable`, it cannot be inferred that every subtype has a no-arg constructor or a `(String)` constructor.

If an API needs to **create** an exception of a type chosen by the caller, accept an appropriate factory, such as `Function<String,E>`.

### Runnable program: creating exceptions via a factory

Create the file **`GenericExceptionFactoryDemo.java`**:

```java
import java.io.IOException;
import java.util.function.Function;

public class GenericExceptionFactoryDemo {
    static class ValidationException extends Exception {
        ValidationException(String message) {
            super(message);
        }
    }

    static <E extends Exception> void requirePositive(
            int value, Function<String, E> errorFactory) throws E {
        if (value <= 0) {
            throw errorFactory.apply("value must be positive");
        }
    }

    public static void main(String[] args) {
        try {
            requirePositive(0, ValidationException::new);
        } catch (ValidationException failure) {
            System.out.println("validation=" + failure.getMessage());
        }

        try {
            requirePositive(-1, IOException::new);
        } catch (IOException failure) {
            System.out.println("IO=" + failure.getMessage());
        }

        try {
            requirePositive(5, ValidationException::new);
            System.out.println("positive accepted");
        } catch (ValidationException failure) {
            System.out.println("unexpected validation error");
        }
    }
}
```

```bash
javac GenericExceptionFactoryDemo.java
java GenericExceptionFactoryDemo
```

`stdout`:

```text
validation=value must be positive
IO=value must be positive
positive accepted
```

Explanation:

- `E extends Exception` is the exception type created by the factory.
- `Function<String,E>` takes a message and creates a concrete `E`; the method references `ValidationException::new` and `IOException::new` supply the corresponding constructors.
- The generic method only knows `E`, yet it can `throw` the object returned by the factory thanks to `throws E`.
- The caller catches the exception type **corresponding to the typed factory**.
- Choosing `IOException` for a validation error is only an example of type capability, **not a design recommendation**: in applications, choose an exception type that accurately reflects the nature of the error.

`Function.apply` itself does not declare checked exceptions. If **creating the object inside the factory** needs to throw a checked exception, you must design a functional interface with a suitable `throws` contract instead of assuming `Function` will automatically propagate checked exceptions.

## 12. Type Erasure and Limitations of Generic Exception Classes

Java supports **a type variable as a type in `throws`**, but **does not** allow declaring a generic class as a subclass of `Throwable`. An example that **intentionally does not compile**:

```java
class GenericFailure<T> extends Exception {
    // ERROR: a generic class cannot be a subclass of Throwable.
}
```

Therefore, you cannot design a generic exception carrying a type parameter such as `GenericFailure<String>` and then catch it with `catch (GenericFailure<String> e)`. This is a language limitation.

More **valid** structures:

```java
class RequestFailure extends Exception {
    RequestFailure(String message) {
        super(message);
    }
}

class ResponseFailure extends Exception {
    ResponseFailure(String message) {
        super(message);
    }
}
```

Or place generics on the **operating method/interface**, not on the exception class:

```java
interface ThrowingOperation<R, E extends Throwable> {
    R execute() throws E;
}
```

These are all valid illustrative classes/interfaces. Exceptions are represented by concrete classes, while generic type parameters describe **the kind of error an operation can throw**.

### Why not `E.class`?

`E.class` is invalid because `E` is a type variable, not a class name known at compile time like `IOException.class`. If you need a runtime class, the caller passes `Class<E>`; if you need to create an exception, the caller passes a factory; if you need to wrap an exception, preserve the actual cause object.

## 13. Specializing Generic Interfaces and Overriding Methods

A generic exception type can be placed on an interface so implementing classes declare an appropriate checked exception:

```java
interface Operation<E extends Exception> {
    void run() throws E;
}
```

When using `Operation<IOException>`, the contract means `run() throws IOException`. An implementation can keep `IOException`, narrow it to a subclass (such as `FileNotFoundException`), or declare no checked exception. It cannot arbitrarily add a checked `SQLException` because that is incompatible with the `IOException` of the specialized interface.

### Runnable program: override narrowing generic `throws`

Create the file **`GenericOverrideThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class GenericOverrideThrowsDemo {
    interface Operation<E extends Exception> {
        void run() throws E;
    }

    static class FileOperation implements Operation<IOException> {
        @Override
        public void run() throws FileNotFoundException {
            throw new FileNotFoundException("missing.txt");
        }
    }

    public static void main(String[] args) {
        Operation<IOException> abstractView = new FileOperation();

        try {
            abstractView.run();
        } catch (IOException failure) {
            System.out.println("type="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac GenericOverrideThrowsDemo.java
java GenericOverrideThrowsDemo
```

`stdout`:

```text
type=FileNotFoundException
```

Explanation:

- `Operation<IOException>` is a generic contract with a concrete error type.
- `FileOperation.run()` only throws `FileNotFoundException`, a subtype of `IOException`, so the override is valid.
- The caller uses the static type `Operation<IOException>`, so it catches `IOException`.
- The runtime object is still `FileNotFoundException`, caught by the `IOException` handler through inheritance.

**Do not confuse generic throws with an override being allowed to widen checked exceptions.** Once the interface is specialized, standard checked exception rules for overriding still apply.

## 14. Why Don't `Runnable` and `Function` Automatically Benefit from `throws E`?

`java.lang.Runnable.run()` is declared as:

```java
void run();
```

`java.util.function.Function<T,R>.apply(T)` also declares no checked exceptions. Consequently, an implementing class or lambda assigned to these interfaces **cannot declare new checked exceptions** for the functional method.

Invalid:

```java
Runnable task = () -> {
    throw new java.io.IOException("disk failed");
};
```

Valid when **handled in place**:

```java
Runnable task = () -> {
    try {
        operationThatThrowsIOException();
    } catch (java.io.IOException original) {
        throw new IllegalStateException("task failed", original);
    }
};
```

This is an **illustrative lambda snippet** and requires defining `operationThatThrowsIOException()`. Choosing an unchecked wrapper with a `cause` is an API decision; it does not mean the error has been recovered from.

Another solution is **not using `Runnable`/`Function` at boundaries that need checked exceptions**, and instead defining `ThrowingAction<E>` or `ThrowingSupplier<R,E>` with `throws E`.

### Can `ThrowingAction` be converted to `Runnable`?

You can **adapt** it with a wrapper that deliberately handles or translates the exception type. However, you cannot arbitrarily cast an object implementing `ThrowingAction` to `Runnable` just because both interfaces have a method named `run`; they are two independent interfaces.

If an adapter converts a checked exception into an unchecked one, preserve the cause and document the contract clearly. If API users must be aware of and recover from checked exceptions, provide a callback API capable of `throws E` from the start.

## 15. The *Sneaky Throw* Technique: Understanding It to Avoid Misuse

Generic `throws E` can be exploited to throw a checked exception without the caller **being required to declare it** in the usual way. This is commonly called *sneaky throw*.

A **runnable example, but not recommended for normal API design**:

Create the file **`SneakyThrowDemo.java`**:

```java
import java.io.IOException;

public class SneakyThrowDemo {
    @SuppressWarnings("unchecked")
    static <E extends Throwable> void sneaky(Throwable failure) throws E {
        throw (E) failure;
    }

    public static void main(String[] args) {
        try {
            SneakyThrowDemo.<RuntimeException>sneaky(
                    new IOException("checked failure"));
        } catch (Throwable failure) {
            System.out.println(
                    failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());
        }
    }
}
```

```bash
javac SneakyThrowDemo.java
java SneakyThrowDemo
```

`stdout`:

```text
IOException: checked failure
```

**Technical explanation:**

1. The method accepts a parameter of static type `Throwable`, not `E`. Therefore, the compiler does not verify that the argument actually has type `E`.
2. Casting `(E) failure` is an **unchecked cast**, annotated with `@SuppressWarnings("unchecked")` to suppress the warning; this is not proof of type safety.
3. The call explicitly specifies `E = RuntimeException` via the type witness `<RuntimeException>`, making the `throws E` contract at the caller look unchecked.
4. At runtime, the **actual IOException object** is still thrown, without changing its type to RuntimeException.
5. `catch (Throwable)` is used in the example only to print a deterministic result.

Do not conclude that a checked exception has truly become unchecked. It is still an `IOException` at runtime; only **the type-checking mechanism at the call site** has been deprived of accurate information. This can break caller expectations, hinder maintainability, reduce the effectiveness of static analysis tools, and produce exceptions missing from the public API contract.

### Awkward situation with `catch (IOException)`

If a call is seen by the compiler as throwing only `RuntimeException`, a `catch (IOException)` handler solely for that call may be rejected by `javac` because **checked IOException is not known to be throwable there**. This means the caller loses the ability to handle the very error type that runtime can still produce.

Therefore, **do not use sneaky throw to replace `try/catch`, replace functional interface design, or hide errors from callers**. Only understand this mechanism when reading specialized library code where the author has a clear reason and contract.

### Type parameter inference in `throws`

The JLS describes special rules when inferring type variables that have an upper bound of `Throwable` and appear only in `throws` constraints. In situations lacking other constraints, the compiler may choose a suitable unchecked type (often `RuntimeException`) as the inference choice. This is why sneaky-throw-style APIs can exist.

Do not memorize an inference trick and apply it unconditionally to every generic signature. The inferred type also depends on method parameters, target types, lambdas, overloads, and other constraints. A safer pattern is to declare the **real** relationship between the callback, exception type, and caller, such as `ThrowingSupplier<R,E>`.

## 16. Type Erasure Does Not Erase the Real Exception Object

When compiling generics, much of the type parameter information is no longer present at runtime as an independent concrete type; this is **type erasure**. For example, the upper bound of `E extends Throwable` helps the compiler check and determine an appropriate representation, but `E` is not a new runtime class.

Therefore:

- If `throw failure;`, the actual object still carries a runtime class such as `IOException` or `FileNotFoundException`.
- The caller's `catch (IOException e)` mechanism still relies on the actual class of the throwable being propagated.
- `Class<E>` can help check a specific runtime class when the caller supplies a type token.
- Do not use `E.class` or `new E()`.
- Do not rely on unchecked casts to "assert" that a `Throwable` object is a subtype `E` chosen by the caller.

### Runtime type example with `Class<E>`

Create the file **`GenericThrowableClassTokenDemo.java`**:

```java
import java.io.IOException;

public class GenericThrowableClassTokenDemo {
    static <E extends Throwable> boolean matches(
            Throwable value, Class<E> expected) {
        return expected.isInstance(value);
    }

    public static void main(String[] args) {
        Throwable failure = new IOException("disk");

        System.out.println("IOException="
                + matches(failure, IOException.class));
        System.out.println("RuntimeException="
                + matches(failure, RuntimeException.class));
        System.out.println("Throwable="
                + matches(failure, Throwable.class));
    }
}
```

```bash
javac GenericThrowableClassTokenDemo.java
java GenericThrowableClassTokenDemo
```

`stdout`:

```text
IOException=true
RuntimeException=false
Throwable=true
```

`Class.isInstance` performs a runtime compatibility check. The generic method `matches` needs no cast and still preserves the `Class<E>` relationship with the type variable. Use this when an API genuinely needs to check an exception type specified by the caller; if you only need to propagate the exception, `throws E` and `throw e` are simpler.

## 17. Precise Rethrow and Generic `throws E`

Since Java 7, the compiler performs **precise rethrow** analysis for certain caught exception variables that are not reassigned. This allows a method to catch a broad type to observe an error while still declaring a narrow set of checked exceptions corresponding to the operations inside `try`.

Example:

```java
static <E extends Exception> void executeAndReport(
        ThrowingAction<E> action) throws E {
    try {
        action.run();
    } catch (Exception failure) {
        System.out.println("action failed: " + failure.getMessage());
        throw failure;
    }
}
```

This is an **illustrative method snippet** using the `ThrowingAction<E>` interface defined above. Because the `catch` parameter `failure` is not reassigned and the `try` body only propagates exceptions from `action.run()`, Java can apply precise rethrow analysis within the checked exception bounds of `E`.

However, distinguish between the two mechanisms:

1. **Generic `throws E`**: the static relationship between the callback's error type and the helper's error type.
2. **Precise rethrow**: compiler analysis of which checked exceptions can actually be thrown from the `try` block and the effectively final nature of the caught variable.

Writing `catch (Exception)` or `catch (Throwable)` does not automatically mean you can `throw` it back without declaring it; it depends on the signature, the calls inside `try`, and exception checking rules.

If you do not need to add logs/context, **do not catch just to rethrow**: simply write `action.run();` for a clearer contract and to avoid duplicate logging.

### `throws E` does not guarantee preserving the stack trace if you wrap incorrectly

`throw original;` propagates the same throwable object, whereas:

```java
throw new IllegalStateException("failed", original);
```

creates a new object and keeps `original` as the `cause`. Both are valid approaches depending on the API boundary, but they have **different meanings**. Do not just copy `original.getMessage()`, as you may lose the stack trace/cause/suppressed exceptions of the original error.

## 18. Common Compile-Time Errors

| Code / situation | Valid? | Reason |
| --- | --- | --- |
| `<E extends Throwable> void run(E e) throws E { throw e; }` | Yes | E is a throwable and is declared in throws |
| `<E extends Throwable> void run(E e) { throw e; }` | **No**, in general | May propagate a checked E without catch/throws |
| `<E extends RuntimeException> void run(E e) { throw e; }` | Yes | E is restricted to the unchecked branch |
| `catch (E e)` when E is a type variable | **No** | A type variable is not a valid catch type |
| `new E()` | **No** | Cannot instantiate directly from a type parameter |
| `value instanceof E` | **No** | A type variable is not a runtime reifiable type |
| `E.class` | **No** | No class literal exists for a type variable |
| `class Failure<E> extends Exception` | **No** | A generic class cannot be a subclass of Throwable |
| `class Failure extends Exception` | Yes | Non-generic exception class |
| `ThrowingAction<IOException> action = () -> { throw new IOException(); };` | Yes | Functional method declares throws E = IOException |
| `Runnable action = () -> { throw new IOException(); };` | **No** | Runnable.run() does not declare checked exceptions |
| `static <E extends Throwable> void run(ThrowingAction<E> a) throws E` | Yes with matching method body | Generic callback preserves the error contract |
| `Operation<IOException>` implemented with `throws FileNotFoundException` | Yes | Override narrows the checked type |
| `Operation<IOException>` implemented with `throws SQLException` | **No** | Override adds a checked exception from another branch |
| `<RuntimeException>sneaky(new IOException())` | Possible via unchecked cast | Technique that hides the contract, not recommended |

The rows are **abbreviated syntax snippets**, not complete programs. The table examines core generic/exception semantics; classes, interfaces, methods, and access modifiers must still be declared appropriately.

## 19. API Design: Choosing `E extends Throwable` or `E extends Exception`?

When designing a library, choose a bound narrow enough for your needs.

### `E extends Throwable`

Appropriate if you want to model callbacks/operations that can propagate **any Throwable subtype**, including `Error`. However, this is a very broad scope. Do not choose it merely because it "looks general" if callers and application handling policies have no reason to advertise `Error` in the type contract.

### `E extends Exception`

Appropriate if the API mainly deals with application exceptions and business/I/O checked exceptions. It still accepts `RuntimeException`, but does not accept `Error` via the type argument `E`. Unchecked `Error` can still occur in practice; this bound is not a mechanism that prevents the JVM from throwing Errors.

### `E extends IOException` or a specific domain exception

Useful when a helper only serves one error family and callers need to know clear limits. Choose a bound broader than `IOException` if the API genuinely must handle checked exceptions from different branches.

### When is a **generic exception type not needed**?

If an API only calls a fixed operation that always declares `IOException`, a plain signature:

```java
static String read() throws java.io.IOException {
    return "data";
}
```

may be easier to understand than creating a contrived `<E extends Throwable>`. Generic exception types are valuable when there is **a real relationship between the caller/callback's type argument and the propagated error**, not when a method simply wants to dodge a specific checked exception.

### Do not overuse multiple type parameters

An API with `<R,T,E1,E2,E3>` can be very hard to read. Use it when a multi-error contract genuinely needs distinction; if the complexity outweighs the benefit, consider a domain exception type with a proper cause or an operation/result object design. Do not use `throws Exception` just to skip error design, yet do not force every simple helper into a complex generic framework.

## 20. Common Misconceptions

**"`E extends Throwable` means every `E` is a checked exception."** False. `RuntimeException` and `Error` are unchecked.

**"`throws E` means the caller must always catch `Throwable`."** False. If `E` is inferred/specified as `IOException`, the caller only needs the corresponding checked contract.

**"With generic `throws E`, a lambda assigned to `Runnable` is allowed to throw IOException."** False. A lambda must obey the `throws` clause of the abstract method in the target functional interface.

**"`<E extends Throwable>` is a new exception type at runtime."** False. It is a type parameter with an upper bound, subject to type erasure.

**"You can `catch (E failure)` because E extends Throwable."** False. Java forbids type variables as catch types.

**"You can create an exception with `new E()`."** False. Pass a factory or a class token along with a controlled creation mechanism.

**"Both exception classes have a (String) constructor so the compiler knows how to instantiate E."** False. Constructors are not inferred across all subtypes of a bound; a concrete factory is required.

**"A generic exception class `MyException<T> extends Exception` is normal."** False. Java forbids generic subclasses of `Throwable`.

**"`ThrowingSupplier<R,E>` completely replaces `Function<T,R>` with nothing changed."** No. They have different functional method contracts and cannot be substituted/cast arbitrarily.

**"`throws E` allows an overriding method to add any checked exception."** False. Once the type argument is specialized, checked exception overriding rules still apply.

**"Sneaky throw has converted IOException into RuntimeException."** False. The runtime object is still IOException; the technique only prevents the caller from seeing the true checked contract.

**"`@SuppressWarnings("unchecked")` makes a cast type-safe."** False. It only hides the warning; it does not prove runtime compatibility.

**"If the current lambda throws no error, the caller can omit the checked handler even if the interface declares throws E."** False. Checking is based on the functional interface/type signature at the call site.

**"`getClass()` or `Class<E>` is always needed for generic rethrow."** No. Passing `E e` and `throw e` is sufficient if you are only forwarding the error type.

**"You can omit `throws E` when throwing E because the compiler sees the Throwable bound."** False when E can be checked. The bound proves throwability, not the exception declaration.

**"Catching and rethrowing always requires creating a new exception to preserve the stack trace."** False. `throw original;` preserves the old object; wrapping with a cause is a different operation.

## 21. Self-Check Exercises

### Exercise 1: Generic bound

```java
static <E extends Throwable> void fail(E e) throws E {
    throw e;
}
```

**Question:** Can `E` be `IOException`, `IllegalArgumentException`, `AssertionError`? **Answer:** All three satisfy the bound; checked/unchecked rules at the call site depend on the concrete type.

### Exercise 2: Omitting `throws E`

```java
static <E extends Throwable> void fail(E e) {
    throw e;
}
```

**Question:** Does it compile? **Answer:** Not in this form, because `E` can be a checked exception and the method neither catches nor declares it.

### Exercise 3: Lambda

```java
@FunctionalInterface
interface Action<E extends Exception> {
    void run() throws E;
}
```

**Question:** Can `Action<IOException>` use a lambda that throws `IOException`? **Answer:** Yes, provided `IOException` is imported or fully qualified and the lambda follows the interface contract.

### Exercise 4: Catching a type variable

```java
static <E extends Exception> void use(E e) {
    try {
        throw e;
    } catch (E caught) {
    }
}
```

**Question:** Is this catch valid? **Answer:** No; a type variable `E` cannot be used as the type of a `catch` parameter.

### Exercise 5: Generic exception class

```java
class ValidationFailure<T> extends Exception {
}
```

**Question:** Does it compile? **Answer:** No. A generic class cannot be a subclass of `Throwable`.

### Exercise 6: Runtime type

```java
static <E extends Throwable> boolean test(
        Throwable e, Class<E> expected) {
    return expected.isInstance(e);
}
```

**Question:** Does this method need `E.class`? **Answer:** No. The caller supplies the `Class<E>` token.

### Exercise 7: Rethrow via generics

If `ThrowingSupplier<String, IOException> s` throws `IOException`, does `supply(s) throws E` with `E=IOException` require the caller to catch/declare IOException? **Yes.**

### Exercise 8: Two error types

If callback A has `Step<IOException>` and callback B has `Step<SQLException>`, can the method `<E1 extends Exception,E2 extends Exception> runBoth(...) throws E1,E2` be used? **Yes.** The caller needs to handle both checked types if they can escape.

### Exercise 9: Sneaky throw

A method declares generic `throws E` but internally performs an unchecked cast from `Throwable` to `E`; the caller specifies `E=RuntimeException` and passes `IOException`. **What is the runtime exception object?** Still `IOException`. This is why it should not be used to hide checked exceptions.

### Exercise 10: Override

`interface Op<E extends Exception> { void run() throws E; }`. Can a class implementing `Op<IOException>` override `run() throws FileNotFoundException`? **Yes**, because a checked subtype is permitted.

### Exercise 11: Factory

Why is `<E extends Exception> E make() { return new E(); }` invalid, whereas accepting `Function<String,E> factory` and calling `factory.apply(message)` can work? Because generics do not know the real constructors of `E`, while the factory supplied by the caller provides the concrete instantiation operation.

### Exercise 12: `Exception` bound

Does `E extends Exception` accept `IllegalStateException`? **Yes**, because it is a subclass of `RuntimeException`, which extends `Exception`. Does it accept `AssertionError` as a type argument? **No**, because `Error` does not extend `Exception`.

## 22. Java 17 References

- [Java Language Specification 17 — 8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): allows appropriate type variables in `throws`.
- [Java Language Specification 17 — 11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception categories and catch/throws obligations.
- [Java Language Specification 17 — 18.4 Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.4): inference of type variables, including constraints involving `throws`.
- [Java Language Specification 17 — 15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): checking checked exceptions from lambda bodies against functional interfaces.
- [Java Language Specification 17 — 14.20 try/catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): exception catch types and handler selection rules.
- [Java Language Specification 17 — 8.1.2 Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.2): a generic class cannot be a subclass of Throwable.
- [Java Language Specification 17 — 8.4.8.3 Override Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exception restrictions when overriding methods.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): root class of the exception mechanism.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html) and [Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): functional methods that do not declare checked exceptions.
- [Java SE 17 API — Class.isInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isInstance(java.lang.Object)): checking runtime type using a class token.

**Key takeaway:** `<E extends Throwable>` allows a generic method to describe **exception type E** in parameters, callbacks, and `throws E`, enabling checked exceptions to be forwarded with a clear contract. However, a type variable does not replace a concrete exception class at runtime: no `catch (E)`, no `new E()`, no `E.class`. Use generic `throws` to **preserve the true type information of callbacks/callers**, not unchecked casts or *sneaky throw* to hide checked exceptions from API users.
