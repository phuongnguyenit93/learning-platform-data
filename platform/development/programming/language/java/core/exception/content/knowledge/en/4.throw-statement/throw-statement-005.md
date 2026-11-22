# throw null and NullPointerException in Java

> Java Core – Exception · Group: The throw Statement · Examples run on Java 17 or later.

## 1. Understanding It in One Sentence

`throw null;` **compiles**, but when this statement actually executes, Java **creates and throws a `NullPointerException` object**. The `null` value is not an exception object; there is no such thing as a `catch` block receiving a "null exception."

This is a rule of the **Java Language Specification (JLS), section 14.18**, and it applies to any null reference value that a `throw` expression evaluates to normally, not only the `null` keyword written directly in code.

After this lesson, you will be able to distinguish:

1. `throw null` vs. `throw new NullPointerException(...)`.
2. `throw variable` when the variable holds null vs. when it holds an actual `Throwable` object.
3. `throw factory()` when the factory returns null vs. when the factory itself throws an exception before returning.
4. Static type constraints at compile time vs. the exception type thrown at runtime.
5. How to catch, diagnose, and avoid "throw null" bugs arising in real code.

## 2. Standard Rules for the throw Statement

Java uses the syntax:

```java
throw expression;
```

According to [JLS 17 – The throw Statement, section 14.18](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18), the expression after `throw` must have a type assignable to `Throwable` or be the null literal. At runtime, Java evaluates the expression first, then handles one of three cases:

| Result of `expression` | Behavior of `throw` | Observed exception |
| --- | --- | --- |
| Evaluates normally, yielding a non-null object | Throws **that exact object** | Runtime type of the object |
| Evaluates normally, yielding a `null` reference | **Creates and throws** a `NullPointerException` object | `NullPointerException` |
| The expression itself throws an exception before producing a result | The `throw` statement completes abruptly due to that exception; no final value is thrown | Exception type caused by the expression |

You can visualize it as:

```text
              throw expression;
                       |
              Evaluate expression
                  /          \
           Succeeds           Throws exception E
              |                      |
      What is the result?            v
        /          \            Propagate E
   Non-null        null
      |             |
      v             v
  Throw the     JVM creates NPE
   object       and throws NPE
      \             /
       \           /
         Find catch
       or propagate to caller
```

The JLS clearly defines two easily confused points: `throw` accepts an expression **that does not have to be a `new` expression**, and the value to be thrown **can never become a null-valued Throwable**. If the result is null, a new NPE appears in its place.

### The throw Statement Completes Abruptly

In this construct:

```java
try {
    throw null;
    // Do not write any executable statement here:
    // javac will flag it as an unreachable statement.
} catch (NullPointerException ex) {
    System.out.println("caught NPE");
}
```

Lines after `throw` in the same normal execution branch cannot run. If you place an unconditional executable statement after `throw null;` in the same block, the compiler reports an *unreachable statement*. The comment lines in the example are not executable statements, so this snippet can be used inside a method.

If a matching `catch` clause exists, the program can continue **after the try/catch construct**, rather than returning to the throw site.

## 3. Why Doesn't throw null Cause a Compile Error?

Java has a **null type** for the `null` literal. The JLS specifies that this value is permitted directly in the expression of a `throw` statement. Therefore:

```java
throw null;
```

is valid syntax. This is an illustrative snippet placed inside an appropriate method; a source file containing only this line outside a Java class is not a standalone program.

Closely related examples have different outcomes:

| Source code (in valid context) | Valid at compile time? | What happens at runtime |
| --- | --- | --- |
| `throw null;` | Yes | NPE created by the runtime |
| `throw (RuntimeException) null;` | Yes | NPE created by the runtime; casting null is still null |
| `RuntimeException ex = null; throw ex;` | Yes | NPE created by the runtime |
| `throw new NullPointerException("bad");` | Yes | Throws developer-created NPE with message `bad` |
| `throw new IllegalStateException("failed");` | Yes | Throws `IllegalStateException`, not NPE |
| `throw 42;` | No | `int` is not compatible with `Throwable` |
| `throw "failed";` | No | `String` is not a subtype of `Throwable` |
| `throw new Object();` | No | `Object` is not assignable to `Throwable` |
| `throw (Object) null;` | No | Static type `Object` is incompatible even though the value is null |
| `throw;` | No | Java requires an expression after `throw` |

Errors on the intentionally invalid lines belong to **compile time**; the NPE from `throw null` belongs to **runtime**. Do not mix these two phases when explaining them.

## 4. Three Sources of NullPointerException Often Lumped Together

Consider three illustrative snippets, each written inside an appropriate Java method.

**Case A — throwing null:**

```java
throw null;
```

The expression `null` completes normally, but the value to be thrown is null; Java creates an NPE.

**Case B — explicitly creating an NPE object:**

```java
throw new NullPointerException("customerId must not be null");
```

The NPE object has already been created with `new` and a meaningful message. `throw` throws that exact object.

**Case C — misusing a null reference:**

```java
String customerName = null;
int length = customerName.length();
```

There is no explicit `throw` statement in the code, yet the JVM throws an NPE when attempting to invoke a method through a null reference.

All of the above can result in **the same NPE type**, yet they differ in root cause and stack trace location. Do not fix every NPE by adding `catch (NullPointerException)`: locate the source that violated the null contract.

### NPE Type and Hierarchy

```text
java.lang.Throwable
    └── java.lang.Exception
        └── java.lang.RuntimeException
            └── java.lang.NullPointerException
```

NPE is an **unchecked exception** because it extends `RuntimeException`. Thus a method can throw NPE without being required to declare `throws NullPointerException`. This does not mean the error can be ignored; NPE usually signals state or an argument that fails to meet the program's assumptions.

## 5. Complete Java 17 Example: Literal, Variable, Factory, and Explicit Error

Save the following code under the exact filename **`ThrowNullDemo.java`**. This is a standalone runnable program requiring no external libraries. Each branch is wrapped by the same test helper to observe handlers and cleanup.

```java
public class ThrowNullDemo {
    private static RuntimeException returnsNull() {
        System.out.println("factory returned null");
        return null;
    }

    private static RuntimeException failsFirst() {
        System.out.println("factory started");
        throw new IllegalStateException("factory failed");
    }

    private static void test(String label, Runnable task) {
        System.out.println("== " + label + " ==");
        try {
            task.run();
            System.out.println("unreachable");
        } catch (NullPointerException ex) {
            System.out.println("caught=NullPointerException");
            if (label.equals("explicit")) {
                System.out.println("message=" + ex.getMessage());
            }
        } catch (IllegalStateException ex) {
            System.out.println(
                    "caught=IllegalStateException: " + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }

    public static void main(String[] args) {
        test("literal", () -> { throw null; });

        test("variable", () -> {
            RuntimeException ex = null;
            throw ex;
        });

        test("returned-null", () -> { throw returnsNull(); });

        test("factory-throws", () -> { throw failsFirst(); });

        test("explicit", () -> {
            throw new NullPointerException("manual message");
        });
    }
}
```

Using JDK 17 or later, in the directory containing the file:

```bash
javac -encoding UTF-8 ThrowNullDemo.java
java ThrowNullDemo
```

**Exact** stdout of the program:

```text
== literal ==
caught=NullPointerException
finally
after
== variable ==
caught=NullPointerException
finally
after
== returned-null ==
factory returned null
caught=NullPointerException
finally
after
== factory-throws ==
factory started
caught=IllegalStateException: factory failed
finally
after
== explicit ==
caught=NullPointerException
message=manual message
finally
after
```

The output was verified when compiling and running on OpenJDK. The code intentionally **does not print `ex.getMessage()` for JVM-created NPEs**, so stdout does not depend on diagnostic details across JVMs. Only the `explicit` branch prints the message passed directly to the constructor in source code.

### Analysis of the Five Branches

1. **`literal`:** Executes `throw null`, receiving a JVM-created NPE. The `catch (NullPointerException ex)` handler catches this object.
2. **`variable`:** The variable has static type `RuntimeException`, but its actual value is null. A valid static type does not turn null into an instance of `RuntimeException`; when thrown, an NPE occurs.
3. **`returned-null`:** `returnsNull()` prints `factory returned null` and then returns null normally. Only **afterward** does the `throw` statement create the NPE. The print side effect on the preceding line has already occurred.
4. **`factory-throws`:** `failsFirst()` prints `factory started` and then throws `IllegalStateException` itself before returning. There is no null result for the `throw` statement to process; the original exception goes straight to the matching catch clause.
5. **`explicit`:** `new NullPointerException("manual message")` creates an object with a specific message; `throw` throws that object.

In every branch, `task.run()` completes abruptly so the `unreachable` line is never printed. `finally` runs, and then `after` runs because the handler has processed the error and completed normally. No branch executes the remainder of the lambda body after the error occurs.

## 6. Reading the Expression After throw Correctly

A common analysis mistake is seeing:

```java
throw createException();
```

and concluding that the program always throws the exact type `createException()` declares as its return type. In reality, you must separate two phases:

- **Evaluation phase:** Call `createException()`. If it throws an exception before returning, that exception propagates immediately.
- **Throwing phase:** Occurs only if the call returns normally. A non-null result is thrown directly; a null result causes an NPE.

Consider an illustrative factory (a method placed inside a Java class; not yet a standalone file):

```java
static RuntimeException createFailure(boolean hasReason) {
    return hasReason
            ? new IllegalArgumentException("bad input")
            : null;
}
```

- `throw createFailure(true);` throws `IllegalArgumentException`.
- `throw createFailure(false);` throws NPE.
- If evaluating the condition or constructing the object itself throws an error, that error is the reason for abrupt completion at that point.

This matters when a factory, converter function, exception builder, or callback inadvertently **returns null as a "no error" signal**. Using that result in a `throw` statement turns "no error" into an unexpected NPE.

## 7. Relationship Between throw null, catch, and finally

An NPE created from `throw null` is still an instance of the `NullPointerException` class. Therefore:

```java
try {
    throw null;
} catch (NullPointerException ex) {
    System.out.println(ex != null);
}
```

Inside a valid method, this snippet prints `true`. The variable `ex` refers to the NPE created by the runtime. Java does not allow a handler parameter to receive a "null exception" in this case.

If you want to handle NPE specifically before other `RuntimeException` types, place the subtype handler before the supertype handler:

```java
try {
    throw null;
} catch (NullPointerException ex) {
    System.out.println("NPE");
} catch (RuntimeException ex) {
    System.out.println("other runtime failure");
}
```

Reversing the two `catch` clauses causes a compile error because the trailing NPE clause is unreachable. `catch (Exception)` can also catch NPE, but catching broadly out of habit easily masks logic bugs.

With `finally`:

```java
try {
    throw null;
} catch (NullPointerException ex) {
    System.out.println("caught");
} finally {
    System.out.println("cleanup");
}
System.out.println("continue");
```

If placed inside a method, stdout is:

```text
caught
cleanup
continue
```

`finally` is a cleanup block when exiting the construct; it does **not** cause the failed evaluation to re-run. If `finally` itself throws another exception, the control outcome can be replaced and the original exception suppressed/lost. Avoid writing `return` or a new `throw` inside `finally` without a clear reason.

## 8. Distinguishing Runtime Exception Type and Compile-Time Static Type

Here is an easily surprising point: `throw null;` has an expression of the **null type**, which the JLS permits directly. However, when throwing **a variable with a checked exception type**, the compiler checks the static type, even if the variable's actual value is null.

Standalone Java 17 example, saved as `TypedNullExample.java`:

```java
import java.io.IOException;

public class TypedNullExample {
    static void fail() throws IOException {
        IOException ex = null;
        throw ex;
    }

    public static void main(String[] args) {
        try {
            fail();
        } catch (IOException ex) {
            System.out.println("caught IOException");
        } catch (NullPointerException ex) {
            System.out.println("caught NPE");
        }
    }
}
```

Run:

```bash
javac TypedNullExample.java
java TypedNullExample
```

Output:

```text
caught NPE
```

**Explanation:** `ex` has static type `IOException` (checked), so `fail()` declares `throws IOException`. However, the runtime value of `ex` is null, so the throw statement results in an unchecked NPE. No actual `IOException` is created or thrown in this run.

A variable of type `Exception` or `Throwable` requires even closer attention to checked-exception catching/declaration requirements. Do not ignore compiler constraints just because tests show a branch currently returns null. Conversely, writing `throws NullPointerException` is optional at the language level because NPE is an unchecked exception.

## 9. Helpful NullPointerExceptions and Error Messages

Modern JDKs can produce helpful NPE messages based on the bytecode operation that failed. OpenJDK JEP 358 added this mechanism starting in JDK 14; on HotSpot, the `ShowCodeDetailsInExceptionMessages` option is enabled by default starting in JDK 15.

In some situations, the message can indicate an attempt to invoke a method, read a field, or **throw a null reference**. However, you must distinguish:

| Aspect | Stability |
| --- | --- |
| Value after `throw` is null → Java throws NPE | Language rule, defined by the JLS |
| `getMessage()` of a JVM-created NPE | May depend on JVM, bytecode, and configuration |
| `new NullPointerException("manual")` → message `manual` | Message passed to constructor by application code |
| Stack trace, line numbers, variable names representing null | Depends on compilation and runtime information |

According to the Java 17 API documentation, `NullPointerException.getMessage()` may return the constructor-supplied message, an implementation-specific message, or `null`. For an NPE explicitly created by a developer without a message, do not assume the runtime will automatically append an expression-analysis message.

If using a supported HotSpot JVM, you can enable or disable this detail for diagnostics:

```bash
java -XX:+ShowCodeDetailsInExceptionMessages ThrowNullDemo
java -XX:-ShowCodeDetailsInExceptionMessages ThrowNullDemo
```

In the main example, stdout **does not change** because the code only prints the type name of the runtime NPEs, not their messages. This is a VM-specific option; do not assume every JVM supports the exact same flag.

In unit tests, prefer asserting the **exception type** and program state. Only assert exact message text when it is guaranteed by your own API or a library contract.

## 10. Writing Better Code Than throw null

### Creating Meaningful Exceptions

For invalid arguments:

```java
if (age < 0) {
    throw new IllegalArgumentException("age must be non-negative");
}
```

For required non-null arguments:

```java
if (customerId == null) {
    throw new NullPointerException("customerId must not be null");
}
```

The two snippets above are only method-body examples, assuming the corresponding variables are already declared. Choose the exception type according to **the API contract**, rather than using NPE for every business error.

### Using Objects.requireNonNull for Null Checks

Standard Java provides `Objects.requireNonNull`; with the overload taking a `String` message, it returns the input reference if non-null, or throws an NPE with the specified message if the input is null.

Standalone Java 17 file `RequireNonNullDemo.java`:

```java
import java.util.Objects;

public class RequireNonNullDemo {
    static void process(String id) {
        String checked = Objects.requireNonNull(
                id, "id must not be null");
        System.out.println(checked);
    }

    public static void main(String[] args) {
        try {
            process(null);
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Run:

```bash
javac RequireNonNullDemo.java
java RequireNonNullDemo
```

Stdout:

```text
id must not be null
```

This is a check **at the data-entry boundary**. If null is a valid API state (for example, a query with no result), design an explicit way to represent absence such as `Optional<T>` when appropriate, instead of forcing an exception to stand in for a normal condition.

### Do Not Write Exception Factories That Return null

Dangerous design:

```java
static RuntimeException buildFailure(String reason) {
    if (reason == null) {
        return null;
    }
    return new IllegalStateException(reason);
}
```

If the caller writes `throw buildFailure(null);`, the program throws an NPE instead of the intended business exception type.

Clearer design:

```java
static IllegalStateException buildFailure(String reason) {
    String message = reason == null
            ? "operation failed"
            : reason;
    return new IllegalStateException(message);
}
```

These two factory snippets only illustrate a method inside a class and **are not standalone Java files**. They should be adapted to real business rules: when there is no error, do not call `throw`; when there is an error, return or construct a non-null Throwable, preserving `cause` when wrapping an original error.

## 11. Common Misconceptions

1. **"throw null must be a compile error."** False: the null literal is permitted by the JLS; the runtime throws an NPE.
2. **"You can throw a null-valued exception object."** False: null is not an object; Java creates an NPE.
3. **"catch receives null."** False: the handler receives an actual NPE object.
4. **"A variable of type RuntimeException definitely holds a RuntimeException."** False: a reference variable can hold null.
5. **"The factory is declared to return RuntimeException, so throw factory() definitely throws RuntimeException."** False: the factory can return null, or throw a different exception itself before returning.
6. **"throw new NullPointerException and throw null are completely identical."** False: both can produce the NPE type, but they differ in object origin and message creation.
7. **"Every NPE has a helpful message."** False: `getMessage()` can be null or vary by implementation.
8. **"NPE is unchecked, so it can just be ignored."** False: the compiler does not require declaring it, but the error still interrupts execution flow.
9. **"I know the checked exception variable is null, so throws is not needed."** False: checked exception checking depends on the static type of the expression.
10. **"Catching NPE fixes the null bug."** False: you usually need to check contracts, initialize properly, and trace where null originated.
11. **"throw null automatically preserves the cause of the previous error."** False: there is no concrete Throwable to serve as a cause; if you need to preserve one, construct a new exception using a constructor that accepts a cause.
12. **"Running finally continues the rest of the throw statement."** False: cleanup only happens during control transfer; it does not re-execute the initial evaluation.

## 12. Self-Check Questions

**Question 1.** What exception type is produced by `throw null;` at runtime? Why is it valid at compile time?

*Answer:* NPE. Java allows the null literal after `throw`, and if the value to be thrown is null, the runtime creates an NPE.

**Question 2.** Does `RuntimeException ex = null; throw ex;` throw an actual `RuntimeException` object from `ex`?

*Answer:* There is no `RuntimeException` object in the variable. The null value results in an NPE created by the runtime.

**Question 3.** With `throw makeException();`, if `makeException()` throws `IllegalStateException` before returning, what is the result?

*Answer:* `IllegalStateException` propagates immediately. The throw statement has no return value to turn into an NPE.

**Question 4.** Why can `fail() throws IOException` throw an NPE at runtime when executing `IOException x = null; throw x;`?

*Answer:* The checked static type `IOException` determines the declaration requirement, while the runtime null value causes Java to create an NPE.

**Question 5.** Should you write tests comparing the exact message generated by the JVM for `throw null`?

*Answer:* No. The exception type is stable per the JLS, whereas diagnostic messages can depend on the implementation.

**Question 6.** When a factory returns null while the caller writes `throw factory();`, where should the fix be made?

*Answer:* Review the contract: if there is no error, avoid throwing; if there is an error, construct a non-null Throwable with the appropriate type, message, and cause.

## 13. Authoritative References

- [JLS 17, section 14.18 – The throw Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): rules for expression evaluation and creating an NPE when the value after `throw` is null.
- [JLS 17, section 11.2 – Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): how the compiler analyzes and requires declaring checked exceptions.
- [Java 17 API – NullPointerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): NPE hierarchy and messages, including the "throwing null" case.
- [Java 17 API – Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull` overloads.
- [OpenJDK JEP 358 – Helpful NullPointerExceptions](https://openjdk.org/jeps/358): mechanism for adding diagnostic NPE details.

**Takeaway:** You need an **actual Throwable object** to throw a meaningful exception. If the expression after `throw` simply evaluates to null, Java **throws a new NPE**. Set explicit null constraints, read static types accurately, and preserve error causes when designing exceptions.