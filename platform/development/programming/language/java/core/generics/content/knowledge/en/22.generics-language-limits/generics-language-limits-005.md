# Distinguishing Types in `catch` from Type Parameters Used in `throws` in Java Generics

## 1. Core question: why is `throws E` valid while `catch (E e)` is invalid?

A generic method in Java can declare an **exception type parameter** in its `throws` clause:

~~~java
static <E extends Exception> void relay(E problem) throws E {
    throw problem;
}
~~~

This declaration is **valid**: the compiler knows `E` is a subtype of `Exception` and uses `throws E` to describe the contract of exception types that the caller must handle or redeclare.

However, the following method is **invalid**:

~~~java
static <E extends Exception> void incorrect(E problem) throws E {
    try {
        throw problem;
    } catch (E caught) {   // Compilation error: E is a type variable.
        System.out.println(caught);
    }
}
~~~

These are not two equivalent uses of `E`:

- `throws E` belongs to **the compile-time checked-exception analysis system**. It expresses an exception type constrained by a type parameter; the compiler can verify call sites using the inferred type.
- `catch (E caught)` demands **an exception type that can be used directly to select a handler at runtime**. Java does not accept a type variable as the exception type in a `catch` parameter, because type argument information is generally removed by **type erasure**.
- `catch (IOException caught)` or `catch (Exception caught)` is valid, because those names are **concrete exception classes** with a class identity that the runtime can use to determine a matching handler.
- Exception classes cannot themselves declare generic type parameters: `class ErrorData<T> extends Exception` is also invalid.

The crux of the lesson: **`throws` and `catch` serve different roles in the language**. `throws E` does not promise that the JVM can generate a catch branch operating on `E` after erasure.

## 2. Rules for `throws` and `catch`

### 2.1. `throws` describes exceptions that may exit a method

A familiar example:

~~~java
static void readFile() throws java.io.IOException {
    // May throw IOException.
}
~~~

A method declaration may list:
- An exception class name such as `IOException`.
- Multiple exception class types separated by commas.
- A **type variable** if its upper bound is compatible with `Throwable`, e.g. `<E extends Exception> ... throws E`.

Java distinguishes **checked exceptions** such as `IOException` and `SQLException` from **unchecked exceptions** (e.g., `RuntimeException`, `Error`, and their subtypes). For checked exceptions, the caller must normally catch them or propagate a `throws` declaration.

### 2.2. `catch` selects a handler by exception class

~~~java
try {
    doWork();
} catch (java.io.IOException problem) {
    // Handle IOException and its subclasses.
}
~~~

At runtime, the thrown exception object is matched against the exception classes in `catch` clauses in order; the first matching branch is selected. That relies on **runtime class/subclass** relationships, not on a caller's generic type argument.

For example:

~~~java
try {
    doWork();
} catch (java.io.IOException | java.sql.SQLException problem) {
    // Multi-catch: handle either of the two exception classes.
}
~~~

This is **multi-catch**. The `|` operator lists concrete exception classes permitted by Java's rules, not a general syntax for catching an arbitrary `E`.

### 2.3. Summary of differences

| Characteristic | `throws E` | `catch (E e)` |
| --- | --- | --- |
| Role | Compile-time checked-exception contract. | Selects an exception handler at runtime. |
| Can `E` be a type variable? | Permitted when properly bounded by `Throwable`. | Not permitted. |
| Is a concrete exception class needed as a catch token? | Not necessarily in source; erasure applies when emitting descriptors. | Yes: the catch parameter must use a valid exception class, not a type variable. |
| Involves type inference? | Yes; callers can infer `E` and the compiler determines checked-exception obligations. | No catching by inferred type argument. |
| Valid example | `<E extends Exception> void f() throws E`. | `catch (IOException ex)` or `catch (Exception ex)`. |

**Note:** `throws E` is not a guarantee that "each invocation has only one exception class stored inside `E` at runtime". It is a generic signature for type checking, whereas the actual exception object still carries its own runtime class.

## 3. Why does Java forbid `catch (E e)`?

Consider:

~~~java
static <E extends Exception> void handle(E value) throws E {
    try {
        throw value;
    } catch (E problem) {
        System.out.println(problem.getMessage());
    }
}
~~~

With `E extends Exception`, the erasure of `E` is `Exception`. If the compiler allowed `catch(E)` and simply translated it to `catch(Exception)`, it would catch **every `Exception` matching the bound**, not just the specific class the caller bound to `E`.

For example, the same source method could be called with `E = IOException` or `E = SQLException`, yet the JVM has no handler table distinguishing those two type arguments per generic invocation. A type variable does not become a specialized runtime class per call.

Consequently, Java requires catch types to be **concrete exception classes**. A compilable alternative:

~~~java
static <E extends Exception> void handle(E value) throws E {
    try {
        throw value;
    } catch (Exception problem) {
        System.out.println(problem.getMessage());
    }
}
~~~

This snippet is valid, yet **`catch(Exception)` catches by `Exception`**, not by `E`. If the goal is specifically handling `IOException`, you can write `catch(IOException)` when the compiler determines that exception type can be thrown and the code satisfies exception analysis.

**The specific diagnostic in javac 17** for `catch(E problem)` looks like:

~~~text
error: unexpected type
required: class
found:    type parameter E
~~~

The key point in the diagnostic: the compiler requires a **class**, rejecting a **type parameter** in that position.

## 4. Validity conditions for `E` in `throws`

A type variable appearing in a `throws` clause must have an appropriate bound: it must represent a subtype of `Throwable`.

For example:

~~~java
static <E extends Exception> void pass(E problem) throws E {
    throw problem;
}
~~~

Valid; `E` is a subtype of `Exception`, and therefore also a subtype of `Throwable`.

A broader variant:

~~~java
static <E extends Throwable> void passAnything(E problem) throws E {
    throw problem;
}
~~~

Valid; it can represent checked exceptions, unchecked exceptions, or `Error` depending on the invocation. However, using `Throwable` in public APIs often produces an overly broad contract; most applications should prefer `Exception` or a specific checked exception unless there is a clear reason.

By contrast, the following is invalid:

~~~java
// static <E> void bad() throws E { }
// E defaults to bound Object, not guaranteed to be Throwable.
~~~

Similarly, type variables bounded by `Object`, `Serializable`, or a domain interface cannot appear in `throws` unless the compiler can prove they are subtypes of `Throwable`.

### Once the type variable is erased, what effect does `throws` still have?

Java erases the type parameter `E extends Exception` to its bound `Exception` wherever type erasure applies. Yet the compiler uses the generic signature and type inference at **the caller's source code** to determine the corresponding checked exception.

As a result:
- Callers of the generic method can be checked against `IOException` or a concrete exception type.
- At runtime, the actual `IOException` object is still delivered when thrown.
- No dynamic `catch(E)` is ever generated.

## 5. Simple example: a generic method that "rethrows with the right type"

This is a valid method:

~~~java
static <E extends Exception> void relay(E problem) throws E {
    throw problem;
}
~~~

Call site:

~~~java
try {
    relay(new java.io.IOException("network"));
} catch (java.io.IOException problem) {
    System.out.println(problem.getMessage());
}
~~~

At the invocation site, the compiler infers `E = IOException`, so the caller handles it with `catch(IOException)`. At runtime, the `IOException` is received as the exact thrown object.

This is **not** an example of `catch(E)`. The caller catches **`IOException`**, a real exception class, while `E` appears only in the generic method's signature.

If the caller neither catches nor redeclares the appropriate checked exception, the compiler reports:

~~~text
unreported exception IOException; must be caught or declared to be thrown
~~~

That is the compile-time effect of the `throws E` contract.

## 6. Generic functional interfaces with their own exception type

A more practical scenario is passing an action along with the checked exception type it is permitted to throw:

~~~java
@FunctionalInterface
interface CheckedAction<E extends Exception> {
    void run() throws E;
}
~~~

Adapter example:

~~~java
static <E extends Exception> void execute(CheckedAction<E> action) throws E {
    action.run();
}
~~~

Properties:

- `CheckedAction<E>` keeps `E` as a generic parameter of the functional contract.
- `run() throws E` allows implementations to throw a checked exception of type `E`.
- `execute(...) throws E` forwards the contract without catching the exception.
- Callers can bind `CheckedAction<IOException>` and catch `IOException` specifically.

Usage snippet:

~~~java
CheckedAction<java.io.IOException> action =
        () -> { throw new java.io.IOException("read failed"); };

try {
    execute(action);
} catch (java.io.IOException problem) {
    System.out.println(problem.getMessage()); // read failed.
}
~~~

This is very helpful when writing callback APIs, transaction wrappers, job runners, or utilities handling checked exceptions without forcing every caller into an overly broad `throws Exception`.

If multiple independent checked exception types exist, a single parameter `E` will not express all exception types as precisely as a signature listing multiple classes. When designing an API, weigh abstraction level, bounds, and handling strategy.

## 7. What if you want to catch exceptions at runtime according to `E`?

Java does not accept:

~~~java
// catch (E e) { ... } // Invalid.
~~~

However, a generic method can combine a **runtime class token** `Class<E>` with a concrete catch class:

~~~java
static <E extends Exception> void inspectThenRethrow(
        CheckedAction<E> action, Class<E> type) throws E {

    try {
        action.run();
    } catch (Exception actual) {
        if (type.isInstance(actual)) {
            System.out.println(
                    "caughtRuntime=" +
                    actual.getClass().getSimpleName()
            );
            throw type.cast(actual);
        }

        throw new IllegalStateException(
                "Unexpected exception", actual
        );
    }
}
~~~

Here:

1. `catch (Exception actual)` is a valid handler for the `Exception` class.
2. `type` is a **`Class<E>` token** provided by the caller, such as `IOException.class`.
3. `type.isInstance(actual)` checks whether the runtime exception object is compatible with the token's class.
4. `type.cast(actual)` performs a checked cast using the class token, yielding a value of source type `E`.
5. `throw type.cast(actual)` satisfies `throws E` in the method signature.
6. If the exception is incompatible, this example wraps it in an `IllegalStateException` instead of falsely casting it to `E`.

**Do not equate this with `catch(E)`:** the JVM still selects the `Exception` handler first; once inside the branch, the code explicitly inspects the runtime class. The token approach fits when you genuinely need to distinguish a dynamic exception type supplied by the caller.

### Why should incompatible exceptions be handled explicitly?

If a method blindly forces any `Exception` to `E` via an unchecked cast, runtime execution can violate the apparent contract and trigger a `ClassCastException` elsewhere. With a class token, the method can **verify the exact runtime class** or wrap/route other exceptions along a clear path.

In the example, `IllegalStateException` is an unchecked exception. A production API may pick a different policy, such as adding another type parameter or a result return type, provided the contract is explicitly documented. Never assume every caught `Exception` is an `E` merely because the action has `throws E`: another unchecked exception can still arise inside the implementation.

## 8. Complete, runnable Java 17+ program

Save the following file as **GenericExceptionDemo.java**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

public class GenericExceptionDemo {
    @FunctionalInterface
    interface CheckedAction<E extends Exception> {
        void run() throws E;
    }

    static <E extends Exception> void execute(
            CheckedAction<E> action) throws E {
        action.run();
    }

    static <E extends Exception> void relay(E problem) throws E {
        throw problem;
    }

    static <E extends Exception> void inspectThenRethrow(
            CheckedAction<E> action, Class<E> type) throws E {

        try {
            action.run();
        } catch (Exception actual) {
            if (type.isInstance(actual)) {
                System.out.println(
                        "caughtRuntime=" +
                        actual.getClass().getSimpleName()
                );
                throw type.cast(actual);
            }

            throw new IllegalStateException(
                    "Unexpected exception", actual
            );
        }
    }

    // Java 7+ precise rethrow; see Section 11.
    static void precise(boolean io) throws IOException, SQLException {
        try {
            if (io) {
                throw new IOException("disk");
            }
            throw new SQLException("database");
        } catch (Exception exception) {
            throw exception;
        }
    }

    public static void main(String[] args) {
        CheckedAction<IOException> ioAction = () -> {
            throw new IOException("read failed");
        };

        try {
            execute(ioAction);
        } catch (IOException problem) {
            System.out.println(
                    "execute=" + problem.getMessage()
            );
        }

        try {
            relay(new IOException("network"));
        } catch (IOException problem) {
            System.out.println(
                    "relay=" + problem.getMessage()
            );
        }

        try {
            inspectThenRethrow(
                    ioAction, IOException.class
            );
        } catch (IOException problem) {
            System.out.println(
                    "typedRethrow=" + problem.getMessage()
            );
        }

        try {
            precise(false);
        } catch (IOException | SQLException problem) {
            System.out.println(
                    "precise=" +
                    problem.getClass().getSimpleName()
            );
        }
    }
}
~~~

Compile and run with a JDK supporting Java 17:

~~~bash
javac --release 17 -Xlint:all GenericExceptionDemo.java
java GenericExceptionDemo
~~~

**Exact stdout:**

~~~text
execute=read failed
relay=network
caughtRuntime=IOException
typedRethrow=read failed
precise=SQLException
~~~

This program is designed to avoid raw types or unchecked casts. It demonstrates how the exception type in `throws E` remains meaningful to the caller while runtime handlers are written with **valid exception classes**.

### Explaining each output line

- `execute=read failed`: `CheckedAction<IOException>` preserves the `IOException` contract; the caller catches `IOException` normally.
- `relay=network`: `relay` throws the `IOException` object itself, and the caller catches it with the `IOException` class.
- `caughtRuntime=IOException`: inside `inspectThenRethrow`, `catch(Exception)` catches the object, the `IOException.class` token confirms the matching runtime type, and the class name is printed.
- `typedRethrow=read failed`: the method rethrows the same exception matching the `throws E` signature; the caller handles `IOException`.
- `precise=SQLException`: the `precise(false)` branch throws `SQLException`, and the multi-catch handler matches the class and prints its name.

Each line illustrates how **static checked-exception contracts**, **runtime exception classes**, and **catch handlers** cooperate without needing `catch(E)`.

## 9. Intentionally invalid cases: verifying with `javac`

The following snippet is **not** runnable code. Save it separately as **InvalidGenericExceptions.java** if you want to inspect the compiler diagnostics:

~~~java
class InvalidGenericExceptions {
    static <E extends Exception> void bad(E input) throws E {
        try {
            throw input;
        } catch (E exception) {  // Invalid: E is a type variable.
            System.out.println(exception);
        }
    }
}

class GenericProblem<T> extends Exception {
    // Invalid: generic class extends Throwable.
}

class GenericRuntimeProblem<T> extends RuntimeException {
    // Also invalid.
}
~~~

Compile to observe the errors:

~~~bash
javac --release 17 InvalidGenericExceptions.java
~~~

Key diagnostics:

~~~text
error: unexpected type
required: class
found:    type parameter E

error: a generic class may not extend java.lang.Throwable
~~~

The compiler reports an error for `catch(E)` and for each generic class extending `Throwable`. The reason does not depend on whether the class extends `Throwable` directly or indirectly via `Exception`/`RuntimeException`: **you cannot declare a generic subclass of `Throwable`**.

Do not mix files containing intentionally invalid code with `GenericExceptionDemo.java` when compiling and running the complete program.

## 10. Why is catching by type argument infeasible even when the method knows `E`?

A common confusion is thinking that **an exception object having a concrete runtime class** means the compiler can turn **type variable `E`** into a dedicated exception handler. With `<E extends Exception>`, `E` belongs to the compile-time generic contract; the same method may be called in contexts inferring `E = IOException` or `E = SQLException`. The JVM does not generate a new handler per type argument.

Therefore the following snippet **intentionally does not compile**:

~~~java
static <E extends Exception> void bad(E failure) throws E {
    try {
        throw failure;
    } catch (E caught) { // Type variable is not a valid catch parameter type.
        System.out.println(caught);
    }
}
~~~

Use `catch (Exception actual)` or a concrete exception class when you want to **catch errors**, then inspect `Class<E> token` using `token.isInstance(actual)` or `token.cast(actual)` under a clear contract. Yet a runtime token **does not make** the syntax `catch(E)` valid.

Java also forbids **generic subclasses of `Throwable`** (even under `RuntimeException`), so you cannot "work around" this with a `GenericError<E>` to distinguish handlers by type argument. A non-generic exception class can still have generic methods, constructors, or payload wrappers.

**Key takeaway here:** `throws E` is used by the compiler to track checked exceptions across calls; the JVM's `catch` uses runtime exception classes. The two mechanisms perform different duties, even though both belong to error handling.

## 11. Precise rethrow: `catch(Exception)` while keeping a narrow checked exception set

One feature easily confused with `throws E` is **precise rethrow analysis**, introduced in Java 7.

~~~java
static void precise(boolean io)
        throws java.io.IOException, java.sql.SQLException {

    try {
        if (io) {
            throw new java.io.IOException("disk");
        }
        throw new java.sql.SQLException("database");
    } catch (Exception exception) {
        throw exception;
    }
}
~~~

Here the catch parameter has type **`Exception`**, not type variable `E`. However, the compiler analyzes:
- Inside the `try` block, only `IOException` or `SQLException` can arise.
- The catch parameter `exception` is not reassigned (effectively final).
- `throw exception` inside the `catch` block can be precisely typed according to the exception types from the `try` block.

Thus the method can still declare `throws IOException, SQLException` without declaring a broad `throws Exception`.

This is completely different from allowing `catch(E)`. Precise rethrow is a **compile-time exception-type analysis rule**, not runtime catching by a generic type argument.

### The effectively final condition is crucial

If you reassign the catch parameter and then throw it, the compiler may no longer narrow the type via precise rethrow and must consider the broader declared `Exception` type. In that case, a method declaring only `throws IOException, SQLException` may cease to compile.

Therefore, when catching to log and rethrow, keep the catch parameter unassigned:

~~~java
try {
    riskyOperation();
} catch (Exception problem) {
    log(problem);
    throw problem;
}
~~~

The snippet above is an **illustrative fragment**, requiring `riskyOperation()` and `log(...)` in a real program; the exact exception rules still depend on the checked exceptions known from the `try` block.

## 12. Can multi-catch replace `catch(E)`?

Multi-catch:

~~~java
try {
    work();
} catch (java.io.IOException | java.sql.SQLException problem) {
    System.out.println(problem.getMessage());
}
~~~

can handle multiple concrete exception classes in a single handler.

Yet it **does not** mean "catch a generic type union `E`". The following remains invalid:

~~~java
// catch (E | IOException problem) { }
// E is a type variable and cannot be used as a catch type.
~~~

In multi-catch, the exception alternatives must be valid exception classes; no alternative may be a subtype of another in the same multi-catch, and the multi-catch variable is implicitly final.

If you need shared logic for several exception classes, you can:
- Use multi-catch when the list of classes is finite and known.
- Catch an appropriate superclass and branch with `instanceof`.
- Use a class token if the target exception class is supplied at runtime.
- Let the exception propagate via `throws E` if the method does not need to handle it.

Choose a solution based on runtime handling goals and compile-time contracts, not merely on whether a type parameter appears in the signature.

## 13. Overriding, checked exceptions, and generic `throws`

When overriding a method, Java does not allow a subclass to arbitrarily widen the set of **checked exceptions** permitted to escape compared to the supertype contract.

For example:

~~~java
class BaseJob {
    void run() throws java.io.IOException {
    }
}

class SpecificJob extends BaseJob {
    @Override
    void run() throws java.io.FileNotFoundException {
    }
}
~~~

Valid because `FileNotFoundException` is a subtype of `IOException`.

Conversely, an override trying to add `SQLException` to a method contracted as `throws IOException` is invalid if that checked exception is not permitted by overriding rules.

For generic methods with `throws E`, the compiler also checks the relationship between the inherited signature and the overriding method after appropriate type substitutions. `throws E` does not allow an implementation to ignore the exception contract of an interface or base class.

**Practical meaning:** `throws E` is a way to model checked-exception contracts, not an escape hatch allowing subclasses to throw arbitrary extra checked exceptions.

## 14. Type inference with `throws E`: do not confuse it with runtime catching

When calling:

~~~java
static <E extends Exception> void relay(E problem) throws E {
    throw problem;
}

relay(new java.io.IOException("network"));
~~~

type inference determines `E` from the argument expression. For the checked exception `IOException`, the caller must handle it appropriately.

However, if you pass a variable with a broader static type:

~~~java
Exception general = new java.io.IOException("network");
relay(general);
~~~

the compiler infers `E` as `Exception` from the static type of `general`, even though the actual object is an `IOException`. The **compile-time contract becomes broader**; the caller must catch `Exception` or declare it accordingly.

At runtime, the original `IOException` object is still thrown. This is the clearest example separating:
- **Static type and type inference of `E`** in `throws`.
- **Actual runtime class of the exception object**.
- **Catch handler** used by the caller.

Never assume the compiler infers `E` from the runtime class of an object stored in a broader variable `Exception general`.

### Why isn't generic `throws` a recommended "sneaky throw" API?

You may encounter techniques combining generic type inference and unchecked casts to bypass checked-exception rules. They are unnecessary for understanding the difference between `throws E` and `catch(E)`, and they make API contracts unpredictable.

In application code, prefer declaring accurate checked exceptions or using clear abstractions like `CheckedAction<E>`. Do not use exception-typing tricks to hide checked exceptions from callers when they need to know about and handle them.

## 15. What can and cannot a `Class<E>` token solve?

Given:

~~~java
static <E extends Exception> boolean matches(
        Exception problem, Class<E> type) {
    return type.isInstance(problem);
}
~~~

The caller can query:

~~~java
boolean io = matches(
        new java.io.IOException("disk"),
        java.io.IOException.class
); // true.
~~~

This is **valid runtime class matching**. It checks the exception object directly against the class token.

However, a class token **does not change `catch` syntax**:
- You cannot write `catch(type)`.
- You cannot write `catch(E problem)` merely because you hold `Class<E>`.
- Runtime handlers are still declared using exception classes like `Exception` or `IOException`.
- Only after catching a broader class can you use `type.isInstance(...)` inside to distinguish cases.

If you need to handle several specific checked exception types without catching overly broad `Exception`, design the API with multiple concrete catch clauses or split the logic at the caller. Dynamic tokens do not replace all forms of checked-exception analysis.

## 16. When can an unchecked exception still slip past `E`?

The method:

~~~java
static <E extends Exception> void execute(
        CheckedAction<E> action) throws E {
    action.run();
}
~~~

preserves the checked-exception contract of `E`. Yet the callback body can still throw a `NullPointerException`, `IllegalArgumentException`, or another `RuntimeException` subclass.

Such unchecked exceptions **do not have to be declared in `throws`**. Therefore, claiming that `execute(...) throws E` "can only ever throw `E` and no other exception" is false.

That is why `inspectThenRethrow` in the example must decide what to do when `catch(Exception)` catches an exception that does not match the class token. It must not blindly cast it to `E`.

Similarly, `Error` is not a subtype of `Exception`, so `catch(Exception)` does not catch `Error`. If an API specifically needs to handle broad `Throwable`, that is a separate decision with major implications for fatal errors; avoid mechanically catching `Throwable`.

## 17. Common mistakes when reviewing Java Generics and exceptions

### Mistake A — Seeing `throws E` and writing `catch(E)`

~~~java
// <E extends Exception> ... throws E
// catch (E e) { } // Rejected by the compiler.
~~~

**Fix:** Catch a real exception class; or let the exception propagate via `throws E`.

### Mistake B — Turning an exception subclass into a generic class

~~~java
// class Failure<T> extends RuntimeException {} // Invalid.
~~~

**Fix:** Use a non-generic exception class, attach payloads via `Object` or controlled wrappers, and keep generic typing at the appropriate API layer.

### Mistake C — Thinking the bound `E extends Exception` makes `E` reifiable

A type variable does not become a catchable runtime class. The runtime object has a concrete class, while `E` in the generic signature remains subject to erasure.

### Mistake D — Using `catch(Exception)` and assuming everything caught is `E`

Unchecked exceptions incompatible with token `E` may occur. Use `Class<E>.isInstance` or another policy instead of an unchecked cast.

### Mistake E — Confusing multi-catch with generic catching

`catch(IOException | SQLException ex)` uses two concrete classes. It does not accept a type parameter representing a union.

### Mistake F — Declaring `throws Exception` when the method only throws `IOException`

An unnecessarily broad `throws Exception` contract burdens callers. Use `throws IOException`, or `throws E` when `E` genuinely models a typed callback.

### Mistake G — Reassigning a catch parameter while expecting precise rethrow to keep narrowing

Precise rethrow depends on exception analysis and the catch parameter being effectively final. Do not break that condition if you want to retain a narrow `throws` signature.

### Mistake H — Adding `@SuppressWarnings` to an unchecked exception cast without understanding the cause

Suppressing warnings does not change the runtime exception class or guarantee the object really is an `E`. If dynamic checking is needed, use an appropriate runtime class token.

## 18. Decision workflow for choosing a solution

When designing exception-handling methods in a generic API:

1. **Do you need to handle the exception or only forward it?** If only forwarding, consider `throws E` to preserve the callback's checked-exception contract.
2. **Is the checked exception type fixed?** If it is a known `IOException`/`SQLException`, declaring it directly is usually clearer than a generic `E`.
3. **Are you planning to write `catch(E)`?** Change the design: Java does not accept type variables in `catch`.
4. **Does runtime code need to distinguish exception classes dynamically?** Accept a `Class<E>`, catch an appropriate class, and use `isInstance`/`cast`.
5. **Is a generic exception class necessary?** You cannot make a generic class subclass `Throwable`; move generic information into another wrapper/API class.
6. **Are you catching broadly to log and rethrow?** Check precise rethrow rules and keep the catch parameter effectively final.
7. **Could you accidentally catch `RuntimeException`/`Error`?** Document explicit policies for checked, unchecked, and fatal errors.
8. **Are you overriding a method?** Keep the checked-exception contract compatible with the supertype.
9. **Are you relying on generic inference for `E`?** Remember inference uses the static type at the call site, not the runtime class of an exception stored in a wider variable.
10. **Verify with `javac` targeting your source release**, such as `javac --release 17`, and test both valid and invalid examples to see where the compiler requires real exception classes.

## 19. Self-check questions

**Question 1.** Why is `static <E extends Exception> void f() throws E` allowed while `catch(E e)` is not?

**Answer:** `throws E` is a compile-time checked-exception contract; `catch` requires a runtime exception class. `E` is an erased type variable and cannot directly identify a handler.

**Question 2.** Can `E extends Throwable` be used in `throws E`?

**Answer:** Yes. `E` is guaranteed to be a subtype of `Throwable`. However, such a broad contract covers `Error` and unchecked exceptions, so use it according to specific needs.

**Question 3.** Can you write `class Failure<T> extends Exception`?

**Answer:** No. Java forbids generic classes from subclassing `Throwable`, either directly or indirectly.

**Question 4.** Does a method taking `CheckedAction<IOException>` and declaring `throws E` force callers to use `catch(E)`?

**Answer:** No. Callers handle it with `catch(IOException)` or redeclare `IOException`. `E` is substituted with the type argument at compile time, while `catch` still uses the real exception class.

**Question 5.** How can runtime code check whether an exception is compatible with `IOException.class`?

**Answer:** Catch using a valid exception class first, then call `IOException.class.isInstance(actual)` and, if needed, `IOException.class.cast(actual)`. This does not make `catch(E)` valid.

**Question 6.** How does precise rethrow relate to `catch(Exception)`?

**Answer:** If the `try` block throws only compiler-analyzed checked exceptions and the catch parameter is never reassigned, `throw exception` can retain narrower checked exception types than `Exception` in the `throws` clause. It is not generic catching.

**Question 7.** With `Exception e = new IOException("disk"); relay(e);`, what type does the compiler infer for `E`?

**Answer:** It infers `E` from the static type `Exception` of the expression `e`, even though the runtime object is an `IOException`. The caller must handle checked exceptions according to that broader static contract.

**Question 8.** Does `throws E` guarantee that `NullPointerException` cannot occur?

**Answer:** No. `RuntimeException` and other unchecked exceptions can still be thrown without being declared in `throws`.

**Question 9.** Why is multi-catch `catch(IOException | SQLException ex)` valid while `catch(E | IOException ex)` is invalid?

**Answer:** Multi-catch requires all alternatives to be valid exception classes; `E` is a type variable and cannot be used as a catch type.

**Question 10.** If you simply need to pass a callback throwing checked `IOException` through a generic utility, what should you choose?

**Answer:** An interface such as `CheckedAction<E extends Exception>` and a utility `<E extends Exception> void execute(CheckedAction<E>) throws E` preserve checked-exception typing without needing `catch(E)` or widening to `throws Exception`.

## 20. Takeaways

**`throws E` and `catch(E)` are asymmetric in Java Generics.**

- `throws E` is valid when `E` is bounded as a subtype of `Throwable`, because the compiler can analyze the checked-exception contract via generic type inference.
- `catch(E e)` is invalid: handlers require a concrete runtime exception class, not an erased type variable.
- Generic exception classes such as `class Failure<T> extends Exception` are also invalid.
- When you need to catch and then inspect exceptions dynamically, use a valid catch class together with a `Class<E>` token and `isInstance`/`cast`.
- Precise rethrow, multi-catch, and generic `throws` are **distinct** features solving different problems.

The design principle is to distinguish **the static checked-exception type at the call site**, **the runtime class of the exception object**, and **the class written in the catch handler**. Understanding these three layers lets you write flexible generic APIs while respecting Java's exception-handling rules.