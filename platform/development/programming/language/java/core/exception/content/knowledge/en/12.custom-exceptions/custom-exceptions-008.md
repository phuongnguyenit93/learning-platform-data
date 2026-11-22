# Generic Limitation: `Throwable` Subclasses Cannot Have Type Parameters in Java

Java supports generic programming to write code that works with many data types, but imposes a special restriction on the exception hierarchy: **a generic class may not be a direct or indirect subclass of `java.lang.Throwable`**. Therefore, declarations such as `class MyException<T> extends Exception`, `class MyRuntimeException<T> extends RuntimeException`, and `class MyError<T> extends Error` all **fail to compile**.

This is a rule of the **Java Language Specification (JLS) §8.1.2**, not a missing-import error or an issue specific to a particular `javac` version. The exception-catching mechanism in Java/JVM relies on the **runtime exception class**, not on a generic parameter `<T>`, which is erased during compilation (*type erasure*).

Equally important: **what is forbidden is an exception class having type parameters**, not every use of generics related to exceptions. A **non-generic** exception class can still contain a `List<String>` field; a generic method can declare `throws E` where `E extends Throwable`; a `Result<T, E>` class can carry an exception. However, the type parameter `E` cannot be placed directly as the type in `catch (E ex)`.

This article presents the reason, valid/invalid syntax, common design caveats, how to preserve typed metadata, generic `throws`, errors when using `catch`, and alternative approaches applicable in Java 17+.

## 1. The Exact Rule in JLS §8.1.2

The JLS specifies that a **generic class** may not be a **direct or indirect subclass** of `Throwable`. A class is generic when **the class declaration itself** has a type parameter section, for example `class Box<T>` or `class Pair<K, V>`.

The following two forms **are both forbidden**:

```java
// INTENTIONALLY DOES NOT COMPILE:
class TypedException<T> extends Exception {
    TypedException(String message) {
        super(message);
    }
}

class TypedRuntimeFailure<T> extends RuntimeException {
    TypedRuntimeFailure(String message) {
        super(message);
    }
}
```

In both classes, the class declaration itself has `<T>` and the superclass is on the `Throwable` branch. `javac` typically reports an error to the effect of:

```text
a generic class may not extend java.lang.Throwable
```

The message may vary by JDK, but **the compile-time cause does not change**.

The restriction does not apply only to `Exception`:

| Declaration | Result | Reason |
| --- | --- | --- |
| `class GenericFailure<T> extends Throwable` | Invalid | Generic class directly extends `Throwable` |
| `class GenericFailure<T> extends Exception` | Invalid | Generic class indirectly extends `Throwable` |
| `class GenericFailure<T> extends RuntimeException` | Invalid | A runtime exception is still a `Throwable` |
| `class GenericFailure<T> extends Error` | Invalid | `Error` is a sub-branch of `Throwable` |
| `class InputFailure extends Exception` | Valid | Exception class **has no type parameters** |
| `class Box<T>` | Valid | This is not a subclass of `Throwable` |
| `class Outcome<T, E extends Exception>` | Valid when not extending `Throwable` | Generic class holds/transfers an exception, is not an exception itself |

**Note:** an exception class can use many generic types in its body and still **not be a generic class**. The criterion is whether that class declaration has a type parameter list `<...>` and whether it extends `Throwable`.

## 2. What Does “Indirect” Mean?

Suppose there is already a non-generic exception class:

```java
class ApplicationFailure extends RuntimeException {
    ApplicationFailure(String message) {
        super(message);
    }
}
```

This class is valid. However, the following inheritance **is invalid**:

```java
// INTENTIONALLY DOES NOT COMPILE:
class GenericServiceFailure<T> extends ApplicationFailure {
    GenericServiceFailure(String message) {
        super(message);
    }
}
```

The inheritance chain is actually:

```text
GenericServiceFailure<T>
        |
        extends
        v
ApplicationFailure
        |
        extends
        v
RuntimeException
        |
        extends
        v
Exception
        |
        extends
        v
Throwable
```

Even though `GenericServiceFailure<T>` **does not directly write** `extends Throwable`, it is still an indirect subclass. Therefore, the restriction still applies.

You cannot “bypass” the rule by placing an intermediate non-generic exception class in between. The condition applies to **the entire inheritance hierarchy of the generic class itself**, not just the superclass name appearing immediately after `extends`.

## 3. Why Does Java Forbid Generic Exception Classes?

### 3.1. Generics Have Their Type Parameters Erased at Runtime

Java primarily implements generics via **type erasure**. For example:

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

System.out.println(names.getClass() == numbers.getClass());
```

This is runnable code when placed inside a method. The result is `true` because both objects have the runtime class `ArrayList`; the type parameters `String` and `Integer` do not create two separate Java runtime classes.

For a *hypothetical* generic exception:

```java
// HYPOTHETICAL ONLY; GenericFailure<T> is forbidden by the JLS.
GenericFailure<String> a;
GenericFailure<Integer> b;
```

If Java allowed this kind of class, the two parameterizations would not become two separate runtime exception classes. The exception-handling mechanism could not rely on the generic parameter to distinguish them.

### 3.2. `catch` Selects the Exception Type by Runtime Class

Java selects the first `catch` branch compatible with **the runtime type of the thrown object**. The JVM uses class information in the bytecode's exception handler table; it does not have two independent handlers based solely on `T = String` or `T = Integer` of the same erased generic class.

Imagine the following code if a generic exception class were allowed:

```java
// INVALID HYPOTHETICAL — CANNOT COMPILE IN JAVA:
try {
    throw new GenericFailure<String>();
} catch (GenericFailure<String> ex) {
    System.out.println("String");
} catch (GenericFailure<Integer> ex) {
    System.out.println("Integer");
}
```

The example above is only used to **explain the impossibility of the design**, not syntax that can run by fixing a few characters. Both parameterizations would have the same runtime class; it is impossible to select a handler by `String` or `Integer` as if they were completely different exception types.

JLS §8.1.2 explicitly states the reason for the restriction is that **the JVM's `catch` mechanism only works with non-generic classes**. This is an official language constraint, not merely a coding-style recommendation.

## 4. Distinguishing Three Things Often Conflated

| Situation | Valid? | Explanation |
| --- | --- | --- |
| `class Failure<T> extends Exception` | **No** | The exception class itself is generic |
| `class Failure extends Exception { List<String> details; }` | **Yes** | Non-generic exception class, field uses a concrete generic type |
| `class Holder<T> { T data; Exception failure; }` | **Yes** | Generic class does not extend `Throwable` |
| `class Result<T, E extends Exception>` not extending `Throwable` | **Yes** | Parameter `E` represents the accompanying error type, not the type of `Result` |
| `static <E extends Exception> void relay(E ex) throws E` | **Yes** | Generic method uses a type variable in the `throws` clause |
| `catch (E ex)` with `E extends Exception` | **No** | A type variable cannot be used as the `catch` parameter type |
| `catch (IOException \| SQLException ex)` | **Yes** if `try` can throw these checked types | Multi-catch lists **concrete classes**, not type variables |
| `class Failure extends RuntimeException { <T> T detailAs(Class<T> type) ... }` | **Yes** | Generic method inside a non-generic exception class |

**The two words “generic” and “exception” appearing in the same file do not cause an error.** Only when a declaration violates a specific language rule, such as a **generic subclass of `Throwable`** or a **type variable in `catch`**, does the compiler reject it.

## 5. Proper Design: Non-Generic Custom Exception with Typed Metadata

Typically, the business information that needs to be carried with an exception is a **specific value**: the failing field name, a list of violations, an error code, or a task ID. There is no need to make the *exception class* itself generic.

Example:

```java
import java.util.List;

class ValidationFailure extends Exception {
    private final List<String> violations;

    ValidationFailure(String message, List<String> violations) {
        super(message);
        this.violations = List.copyOf(violations);
    }

    public List<String> getViolations() {
        return violations;
    }
}
```

This is a **valid class**, without a standalone `main()`. The `ValidationFailure` class has no type parameters, yet the `List<String>` field is still type-checked at compile time. `List.copyOf(...)` creates an unmodifiable copy against normal `List` operations, reducing the risk of external code mutating the list attached to the exception.

### Complete Java 17+ Program

Save as `ValidationFailureDemo.java`:

```java
import java.util.List;

public class ValidationFailureDemo {
    static final class ValidationFailure extends Exception {
        private final List<String> violations;

        ValidationFailure(String message, List<String> violations) {
            super(message);
            this.violations = List.copyOf(violations);
        }

        List<String> getViolations() {
            return violations;
        }
    }

    static <T> T requirePresent(T value, String field)
            throws ValidationFailure {
        if (value == null) {
            throw new ValidationFailure(
                    "Invalid field: " + field,
                    List.of(field + " is required"));
        }
        return value;
    }

    public static void main(String[] args) {
        try {
            System.out.println("valid="
                    + requirePresent("C-42", "customerId"));
            requirePresent(null, "customerId");
        } catch (ValidationFailure ex) {
            System.out.println("type="
                    + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("violations=" + ex.getViolations());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ValidationFailureDemo.java
java ValidationFailureDemo
```

Output:

```text
valid=C-42
type=ValidationFailure
message=Invalid field: customerId
violations=[customerId is required]
```

Analysis:

1. `ValidationFailure` is a **non-generic custom checked exception**.
2. The `List<String>` field holds structured information; it does not turn the exception into `ValidationFailure<String>`.
3. The `requirePresent` method **is generic** because it declares `<T>` and returns the same type `T` as the parameter. A generic method can throw a **concrete** exception type `ValidationFailure`.
4. `main()` catches this concrete exception type; this is a valid `catch` type.
5. The error has its own message and metadata without violating JLS §8.1.2.

If metadata is sensitive, consider what types of data are allowed into exceptions/logs. A typed field does not mean it is permitted to hold passwords, tokens, or personal information that requires protection.

## 6. Generic Methods Can Declare `throws E`

The `throws` clause is declared on a **method or constructor**, not on the exception class itself. JLS §8.4.6 allows a **type variable** as a type in the `throws` list, provided that type is a subtype of `Throwable`.

Example:

```java
static <E extends Exception> void rethrow(E failure) throws E {
    throw failure;
}
```

This is an **illustrative method** that can be placed in a regular class. It is allowed to use `E` in the `throws E` signature and in the `throw failure;` statement. At the call site, `E` is inferred from the type of the exception object.

### Java 17+ Program Verifying Generic `throws`

Save as `GenericThrowsDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class GenericThrowsDemo {
    static <E extends Exception> void rethrow(E failure) throws E {
        throw failure;
    }

    static <E extends Exception> void check(
            boolean fail, E failure) throws E {
        if (fail) {
            rethrow(failure);
        }
    }

    public static void main(String[] args) {
        try {
            check(true, new IOException("disk failure"));
        } catch (IOException ex) {
            System.out.println("io=" + ex.getMessage());
        }

        try {
            check(true, new ParseException("bad token", 0));
        } catch (ParseException ex) {
            System.out.println("parse=" + ex.getMessage());
        }

        try {
            check(false, new IOException("not thrown"));
            System.out.println("success");
        } catch (IOException ex) {
            System.out.println("unreachable on this input");
        }
    }
}
```

```bash
javac -encoding UTF-8 GenericThrowsDemo.java
java GenericThrowsDemo
```

Output:

```text
io=disk failure
parse=bad token
success
```

Here:

- The `GenericThrowsDemo` class is **non-generic**.
- The two methods have the type variable `E extends Exception`, so they are **generic methods**.
- `throws E` is permitted by the JLS; at the example call sites, the compiler infers `E` as `IOException` or `ParseException`, respectively.
- The `catch` blocks still use **concrete exception classes**.
- `check(false, ...)` does not throw on this run, but the signature still describes the possibility of throwing `E`; the `catch (IOException)` block remains valid.

Key distinction: **a generic method can propagate an exception type via a type parameter**, whereas **a generic exception class** still cannot be declared.

## 7. Why Is `catch (E ex)` Invalid?

JLS §14.20 sets a specific rule: **a type variable may not be used as the type of an exception parameter** in `catch`.

The following example **intentionally fails to compile**:

```java
class InvalidGenericCatch {
    static <E extends Exception> void handle(E sample) throws E {
        try {
            throw sample;
        } catch (E ex) { // Compile error: type variable in catch.
            System.out.println(ex.getMessage());
        }
    }
}
```

It is not because `E extends Exception` is wrong; it is **the position of `E` in `catch`** that is forbidden by the JLS. Using `throws E` in the method signature is valid.

A valid way to handle this when you truly want shared code is to catch **a concrete class type designed for the handling boundary**:

```java
static <E extends Exception> void handle(E sample) {
    try {
        throw sample;
    } catch (Exception ex) {
        System.out.println(ex.getMessage());
    }
}
```

This is a valid illustrative method; `catch (Exception ex)` is a concrete class type, not a type variable. Even so, catching `Exception` broadly can swallow more errors than intended. Only use it when the method truly has a unified handling policy; if the exact type `E` needs to be passed to the caller, **letting the exception propagate via `throws E`** is usually more accurate.

Note that a `catch` branch checks **the runtime type of the exception**. A parameter type that is a type variable does not produce a class token sufficient for the JVM to distinguish different generic arguments.

## 8. Alternative Using a Generic Class That *Holds* an Error, Not *Is* an Error

A common design solution is to **keep the exception as a regular class** and put generics into a class describing a result, state, or handling mechanism.

Structural example:

```java
final class Outcome<T, E extends Exception> {
    private final T value;
    private final E failure;

    Outcome(T value, E failure) {
        this.value = value;
        this.failure = failure;
    }

    T valueOrThrow() throws E {
        if (failure != null) {
            throw failure;
        }
        return value;
    }
}
```

This is **a valid generic class** because `Outcome` does not extend `Throwable`. The two type parameters carry different meanings:

- `T`: the success value;
- `E extends Exception`: the exception type stored upon failure.

### Runnable Java 17+ Program

Save as `GenericOutcomeDemo.java`:

```java
import java.io.IOException;

public class GenericOutcomeDemo {
    static final class Outcome<T, E extends Exception> {
        private final T value;
        private final E failure;

        Outcome(T value, E failure) {
            this.value = value;
            this.failure = failure;
        }

        T valueOrThrow() throws E {
            if (failure != null) {
                throw failure;
            }
            return value;
        }
    }

    public static void main(String[] args) {
        Outcome<String, IOException> good =
                new Outcome<>("READY", null);
        Outcome<String, IOException> bad =
                new Outcome<>(null, new IOException("file unavailable"));

        try {
            System.out.println("good=" + good.valueOrThrow());
            System.out.println("bad=" + bad.valueOrThrow());
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 GenericOutcomeDemo.java
java GenericOutcomeDemo
```

Output:

```text
good=READY
caught=file unavailable
```

With `good`, the `failure` field is `null`, so it returns the string `READY`. With `bad`, `valueOrThrow()` throws **the exact stored `IOException` object**; the `println("bad=" + ...)` statement is not executed. `catch (IOException)` catches the concrete error at the caller level.

**Design note:** the `Outcome` class above illustrates the generics and exception mechanism. A production-grade `Result`/`Outcome` should have clear invariants such as “only one of `value` or `failure` is set”, factory methods, a null policy, and a consistent state model. Do not use the demo design to represent all data cases without adding those checks.

## 9. Generic Methods in a Non-Generic Exception Class

A custom exception can still have a **generic method**, for example to read stored metadata via a runtime class token.

Save as `TypedDetailDemo.java`:

```java
public class TypedDetailDemo {
    static final class DomainFailure extends RuntimeException {
        private final Object detail;

        DomainFailure(String message, Object detail) {
            super(message);
            this.detail = detail;
        }

        <T> T detailAs(Class<T> type) {
            return type.cast(detail);
        }
    }

    public static void main(String[] args) {
        DomainFailure failure =
                new DomainFailure("invalid amount", Integer.valueOf(25));

        Integer amount = failure.detailAs(Integer.class);
        System.out.println("detail=" + amount);
        System.out.println("message=" + failure.getMessage());

        try {
            String wrong = failure.detailAs(String.class);
            System.out.println(wrong);
        } catch (ClassCastException ex) {
            System.out.println("wrong-type=ClassCastException");
        }
    }
}
```

```bash
javac -encoding UTF-8 TypedDetailDemo.java
java TypedDetailDemo
```

Output:

```text
detail=25
message=invalid amount
wrong-type=ClassCastException
```

The `DomainFailure` class is a **non-generic exception class**, with no `<T>` on the class declaration. Only the `detailAs` method has `<T>`; it uses `Class<T>.cast(...)` to check the requested type at runtime, rather than casting blindly or assuming erasure protects the data.

This example demonstrates the validity of a generic method, **not advice to store all exception metadata as `Object`**. In many APIs, properties with concrete types such as `String fieldName`, `int errorCode`, or `List<String> violations` are easier to read, easier to test, and safer.

## 10. Distinguishing Generic `throws`, Checked Exceptions, and `RuntimeException`

To understand these limitations, separate three layers of rules:

1. **Class declaration:** a generic class may not extend `Throwable` directly or indirectly (JLS §8.1.2).
2. **Method declaration:** a type variable with a bound compatible with `Throwable` is allowed to appear in `throws` (JLS §8.4.6).
3. **`catch` parameter:** a type variable may not be used as an exception parameter type (JLS §14.20).

Whether an exception is **checked** or **unchecked** is a separate axis of rules:

| Kind | Examples | Normal Caller Obligation |
| --- | --- | --- |
| Checked exception | `IOException`, custom `extends Exception` (not under `RuntimeException`) | Catch or declare `throws` if it can escape |
| Unchecked exception | `RuntimeException` and its subclasses | Not required to declare `throws` |
| Unchecked error | `Error` and its subclasses | Not required to declare `throws`; usually not a group to catch for recovery |

**Neither checked nor unchecked exceptions are allowed to be declared as generic exception classes.** Writing `extends RuntimeException` is not a workaround to make `MyException<String>` valid.

Conversely, `<E extends Exception> ... throws E` is a concept of **generic methods and type bounds**. You do not need to create `Exception<E>` to achieve it.

## 11. Concrete `catch` and Multi-Catch Still Work as Usual

When there are two error types that a workflow needs to handle together, Java supports multi-catch:

```java
try {
    readOrQuery();
} catch (java.io.IOException | java.sql.SQLException ex) {
    reportFailure(ex);
}
```

This is an **illustrative snippet**, assuming `readOrQuery()` can throw the two corresponding checked exceptions and `reportFailure(Exception)` is already defined.

The types in a multi-catch are **concrete exception classes**, distinguished at runtime. This syntax **does not require a generic exception class**. A single multi-catch selects and executes one handler body for the corresponding types.

What Java does not allow is placing a **type variable** in place of a class name in a `catch` branch:

```java
// INTENTIONALLY INVALID:
catch (E ex) {
    // E extends Exception is still invalid in this position.
}
```

For generic orchestration code that needs to handle any `E` under a single policy, you can choose to catch a concrete superclass at the layer with shared responsibility, or not catch it and let `throws E` propagate the error to the upper layer. Do not write `catch (T)` just to make code look “generic”.

## 12. Alternative Design Approaches and When to Use Them

| Practical Need | Design to Consider | Why |
| --- | --- | --- |
| A business error with fixed attributes | Non-generic `DomainException` with `String`, `int`, `enum`, `List<String>` fields | Keeps the exception concrete, attributes typed |
| Multiple distinct error types that need separate catching | Non-generic `FileFailure`, `ValidationFailure`, `ServiceFailure` classes | `catch` by distinct runtime type |
| Same algorithm forwarding multiple checked exception types | Generic method `<E extends Exception> ... throws E` | Preserves exact type bound without creating a generic exception |
| Result holding either a typed value or a typed error | Generic `Result<T,E>`/`Outcome<T,E>` not extending `Throwable` | Generics live in the result-management layer |
| Translating errors between layers | Non-generic custom exception accepting `(String, Throwable)` | Preserves the cause chain, avoids losing context |
| Reading a detail by requested type | Generic method `<T> T detailAs(Class<T>)`, or concrete fields | Can check runtime type via `Class<T>` |
| Classifying multiple error types for different responses | Concrete `catch` blocks, ordered specific → general | Matches JVM mechanics and Java's contract |

Do not create an overly deep exception hierarchy just to simulate generic parameters. Choose an exception class representing **the error semantics to catch or propagate**, while additional data carried with the error can live in typed fields.

## 13. Common Misconceptions and Fixes

| Misconception | Actual Result | Fix |
| --- | --- | --- |
| “`Exception<T>` or `RuntimeException<T>` are standard JDK types.” | Those classes are not generic. | Use `Exception`, `RuntimeException`, or a non-generic custom exception. |
| “Only direct `extends Throwable` is forbidden.” | Indirect inheritance is also forbidden. | Check the entire superclass chain. |
| “Adding an intermediate exception class makes `Failure<T>` valid.” | No; `Failure<T>` is still a subclass of `Throwable`. | Move `T` to a field, method, or result holder. |
| “Create a generic exception and distinguish `catch (Failure<String>)` from `catch (Failure<Integer>)`.” | No valid generic exception class exists; type erasure also prevents handlers from distinguishing type arguments. | Use different concrete exception classes when runtime branching is genuinely needed. |
| “Because of this restriction, exceptions cannot contain `List<String>`.” | Generic fields in a non-generic exception are valid. | Declare typed fields without adding `<T>` to the class. |
| “Generic methods cannot throw checked exceptions.” | `throws E` is allowed with an appropriate bound. | Use generic `throws` intentionally. |
| “If `throws E` is valid, then `catch (E ex)` is also valid.” | The JLS forbids type variables in exception parameters. | Catch a concrete class or propagate the error upward. |
| “A `Result<T,E>` class holding an error is also forbidden.” | Only forbidden if that generic class is a subclass of `Throwable`. | Keep `Result` as a data class, not extending `Throwable`. |
| “`T extends Throwable` automatically creates a new exception of class `T`.” | A type variable is not a constructor/new runtime class. | Accept an error object or use an explicit factory. |
| “Always using `catch(Exception)` is right when writing generic code.” | Catching too broadly can mask errors outside policy. | Consider `throws E` or concrete `catch` blocks. |
| “Storing metadata in `Object` and casting arbitrarily is type-safe.” | Can cause `ClassCastException`. | Prefer typed fields or checked `Class<T>.cast`. |
| “To make an error carry `T`, you must `extends Exception<T>`.” | JDK `Exception` has no type parameter; custom generic exceptions are forbidden. | Design a non-generic exception holding typed metadata, or a generic result. |

## 14. Process for Choosing a Custom Exception Design

When tempted to write `MyException<T>`, try following these steps:

**Step 1 — Identify what is being made generic.** Is it the error's data type, result type, handling strategy, or the exception class identity? If it is only information related to the incident, it should usually be a **field**, not a class parameter on the exception.

**Step 2 — Define the exception types that `catch` needs to distinguish.** If callers need to handle “invalid format” differently from “missing file”, you can use two concrete non-generic exception classes or one shared class with a stable error code, depending on the contract.

**Step 3 — Preserve the root cause.** A custom exception should have a constructor accepting `(String message, Throwable cause)` when translating errors from lower layers. Do not replace `cause` with just `cause.getMessage()`.

**Step 4 — Move genericity to where it is valid.** Use a generic method to write reusable algorithms or a generic result holder if you need to carry a value `T` and an error `E`.

**Step 5 — Check type parameter placement.** The exception class declaration **has no `<T>`**; if a type variable is in `throws E`, its bound must be appropriate; in `catch (E ex)`, it is invalid.

**Step 6 — Check checked exceptions.** Methods that can throw checked exceptions must be caught with `catch` or declare `throws` with the proper type, even when the calling code is inside a generic class.

**Step 7 — Write tests for both success and failure paths.** Avoid just looking at whether the code “looks generic”; actually run `javac`, then verify the exact exception type, message, cause, and output.

**Step 8 — Limit metadata.** Fields inside an exception should not store sensitive data and print it straight to logs. Only carry information necessary for handling decisions and diagnostics.

## 15. Self-Check Questions

**Q1.** Is `class NetworkError<T> extends RuntimeException` valid?  
**No.** It is a generic class indirectly extending `Throwable`, which is forbidden by JLS §8.1.2.

**Q2.** What about `class NetworkError extends RuntimeException { List<String> hosts; }`?  
**Valid** with respect to the generic exception restriction. The class is non-generic, and `List<String>` is only the type of a field.

**Q3.** Why are `catch (Failure<String>)` and `catch (Failure<Integer>)` not a solution?  
Because generic exception classes like `Failure<T>` are already forbidden; furthermore, the JVM cannot distinguish two parameterizations by runtime handler type due to type erasure.

**Q4.** Can a method declare `<E extends Exception> void relay(E ex) throws E`?  
**Yes.** The JLS allows a type variable in the `throws` clause if the bound is appropriate.

**Q5.** Why cannot `catch (E ex)` be used right inside that same generic method?  
Because JLS §14.20 forbids using a type variable as the type of an exception parameter.

**Q6.** Is a generic `Result<T,E extends Exception>` forbidden?  
**No**, as long as it does not directly or indirectly extend `Throwable`.

**Q7.** Is `class GenericFailure<T> extends ApplicationFailure` valid when `ApplicationFailure extends RuntimeException`?  
**No.** That generic class is still an indirect subclass of `Throwable`.

**Q8.** Can a non-generic exception class declare `<T> T detailAs(Class<T> type)`?  
**Yes.** A generic method does not make the exception class itself generic.

**Q9.** Can `throw ex;` with `E extends Exception` compile inside a generic method?  
**Yes**, if the checked exception contract is satisfied, for example the method declares `throws E`.

**Q10.** The main need is an error carrying `List<String>` information. What should be done?  
Usually create a **non-generic custom exception** with a `List<String>` field and an appropriate constructor. Only use a `Result` holder if the communication model intentionally wants to represent success/failure as a value.

## Authoritative References

- [Java Language Specification 21 — §8.1.2 Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.2): restriction on generic subclasses of `Throwable`.
- [JLS 21 — §8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6): type variables allowed to appear in the `throws` clause.
- [JLS 21 — §14.20 The `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20): type variables may not be used as `catch` parameter types.
- [JLS 21 — §14.18 The `throw` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.18): rules for throwing exception objects.
- [JLS 21 — §4.6 Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6): meaning of erasing generic type information.
- [JLS 21 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2): checked exceptions and `catch`/`throws` obligations.

**Key takeaway:** Java **forbids generic classes from being subclasses of `Throwable`**, but **does not forbid using generic fields, generic methods, generic result holders, or `throws E`** to work with exceptions. Choose a non-generic exception class carrying stable error semantics, keep metadata in typed fields, and only make generic the algorithms or data that truly require generality.
