# Unchecked Exceptions When Overriding Methods in Java

> **Java Core – Exception** · Group **Inheritance and Contracts** · Topic: how an overriding method can declare or throw unchecked exceptions, comparison with checked exception restrictions, and impact on callers. Complete examples use **Java 17+**.

## 1. Key Takeaway

When a method **overrides** a superclass method or implements an interface method, Java restricts the **checked exceptions** declared in the `throws` clause, but **does not impose the same restriction on unchecked exceptions**.

Example:

~~~java
interface Job {
    void execute();
}

class RemoteJob implements Job {
    @Override
    public void execute() throws IllegalStateException {
        throw new IllegalStateException("service unavailable");
    }
}
~~~

These are two valid Java type declarations that can be placed in a single file if there are no other rules regarding public class names. The interface method `Job.execute()` **declares no exceptions**, whereas the overriding version:

- Is allowed to declare `throws IllegalStateException`.
- Is allowed to actually throw `IllegalStateException`.
- Does not force the caller to write `try/catch` or `throws` solely because of this exception type.
- Can still cause the call to **terminate abnormally at runtime** if the exception is not handled.

Reason: `IllegalStateException extends RuntimeException`, which belongs to the **unchecked** group.

**Contrast:** If `throws IllegalStateException` above is changed to `throws IOException`, the compiler will **reject** it, because `IOException` is a new checked exception not permitted by the `Job.execute()` method contract.

What matters for design is that **what Java allows at compile time does not mean a behavioral change is always reasonable**. A subclass can throw a new unchecked exception, yet it must still respect the preconditions and guarantees promised to the caller in the superclass/interface contract.

## 2. Understanding the Relationship Between Checked, Unchecked, and throws

### 2.1. Exception Class Hierarchy

~~~text
java.lang.Throwable
├── java.lang.Error
│   └── Error subclasses                          ← unchecked
└── java.lang.Exception
    ├── java.io.IOException                     ← checked
    │   └── java.io.FileNotFoundException       ← checked
    └── java.lang.RuntimeException              ← unchecked
        ├── java.lang.IllegalArgumentException
        ├── java.lang.IllegalStateException
        ├── java.lang.NullPointerException
        └── java.io.UncheckedIOException
~~~

*Note:* The diagram only illustrates part of the standard Java hierarchy, not an exhaustive list of all subclasses.

**Checked exceptions** are generally subclasses of `Exception` that are not in the `RuntimeException` branch. The compiler requires checked exceptions that can escape from a method to be **caught or declared** according to language rules.

**Unchecked exceptions** include `RuntimeException` and its subclasses, as well as `Error` and its subclasses. Java **does not require** declaring `throws` or catching these exceptions for code to compile.

Therefore:

~~~java
void run() {
    throw new IllegalStateException("bad state");
}
~~~

is a valid method even without a `throws` clause. Conversely:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
void read() {
    throw new java.io.IOException("read failed");
}
~~~

will be rejected by the compiler because `IOException` is neither caught nor declared. The invalid snippet above is not part of the runnable program in this lesson.

### 2.2. throws Is Not a List of Every Possible Error

The `throws` clause serves two roles:

1. Satisfying compile-time rules for **checked exceptions**.
2. Communicating API information to readers and tools when exception types are declared.

However, `throws` **does not list every unchecked exception that might occur**. A method can throw `NullPointerException`, `IllegalArgumentException`, or `IllegalStateException` even when its signature does not mention them.

An unchecked exception can be declared explicitly:

~~~java
void execute() throws IllegalStateException {
    // ...
}
~~~

but doing so **does not turn it into a checked exception** and does not force callers to catch it. In JavaDoc, a `@throws IllegalStateException` tag usually helps clarify **under what conditions** the method may throw the error.

## 3. Overriding Rules for throws: From the Superclass Method's Perspective

According to the [Java Language Specification Java 17 Section 8.4.8.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3), when overriding a method, the set of declared **checked exceptions** cannot be freely expanded compared to the superclass method.

### 3.1. Superclass Method Declares No Checked Exceptions

~~~java
class Parent {
    void save() {
        System.out.println("saved");
    }
}

class Child extends Parent {
    @Override
    void save() throws IllegalStateException {
        throw new IllegalStateException("storage unavailable");
    }
}
~~~

**Valid:** `IllegalStateException` is unchecked.

The following example is **intentionally invalid**:

~~~java
class Parent {
    void save() { }
}

class Child extends Parent {
    @Override
    void save() throws java.io.IOException { } // Compile error.
}
~~~

In the second case, `Child.save()` adds a new checked exception that the signature in `Parent.save()` does not permit. The compiler typically reports something like *overridden method does not throw IOException*.

Even when the child method body is empty and does not actually throw `IOException`, the **invalid `throws IOException` declaration** alone is enough to cause a compile-time error.

### 3.2. Superclass Method Declares a Checked Exception

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

class Parent {
    void read() throws IOException { }
}

class Child extends Parent {
    @Override
    void read() throws FileNotFoundException {
        throw new FileNotFoundException("missing.txt");
    }
}
~~~

**Valid:** `FileNotFoundException extends IOException`, so this **narrows** the checked exception type exposed by the override.

Other valid options are keeping `throws IOException` or **declaring no checked exceptions at all**, if the method body handles all relevant checked exceptions.

Conversely:

~~~java
class Parent {
    void read() throws java.io.IOException { }
}

class Child extends Parent {
    @Override
    void read() throws Exception { } // INTENTIONALLY INVALID.
}
~~~

**Invalid:** `Exception` is broader than `IOException`, so it cannot be used to expand the caller's obligation in an override.

### 3.3. Unchecked Exceptions Are Not Restricted by the Same Rule

Suppose the superclass method declares `IOException`:

~~~java
class Parent {
    void fetch() throws java.io.IOException { }
}

class Child extends Parent {
    @Override
    void fetch() throws java.io.FileNotFoundException,
            IllegalStateException {
        throw new IllegalStateException("temporarily unavailable");
    }
}
~~~

This code is **valid**:

- `FileNotFoundException` is a checked subtype of `IOException`, so it is allowed.
- `IllegalStateException` is unchecked, so it is not subject to the superclass method's checked-type restriction.

A `throws` clause may list both checked and unchecked exceptions, but they are checked differently.

**Quick summary:**

| Superclass method signature | Override signature | Valid? | Reason |
| --- | --- | --- | --- |
| No `throws` | No `throws` | Yes | No checked obligation added |
| No `throws` | `throws IllegalStateException` | Yes | Unchecked is permitted |
| No `throws` | `throws IOException` | No | Adds a checked exception |
| `throws IOException` | `throws FileNotFoundException` | Yes | Checked exception is narrowed |
| `throws IOException` | `throws IOException` | Yes | Keeps the permitted checked type |
| `throws IOException` | No `throws` | Yes | Removes the checked declaration |
| `throws IOException` | `throws Exception` | No | Broadens the checked exception |
| `throws IOException` | `throws IllegalStateException` | Yes | No checked left, adds unchecked |

This table covers simple examples without generic exception type parameters; Java has additional technical rules regarding type erasure when overriding generic methods. Do not generalize this into a rule for every complex signature while ignoring the JLS.

## 4. Is It Necessary to Write throws for Unchecked Exceptions in an Override?

**No.** Both of the following approaches are valid:

~~~java
class ServiceA {
    void process() {
        throw new IllegalStateException("not ready");
    }
}

class ServiceB extends ServiceA {
    @Override
    void process() {
        throw new IllegalArgumentException("invalid operation");
    }
}
~~~

And:

~~~java
class ServiceB extends ServiceA {
    @Override
    void process() throws IllegalArgumentException {
        throw new IllegalArgumentException("invalid operation");
    }
}
~~~

These two code blocks **only illustrate separate alternatives**; do not place two duplicate `ServiceB` declarations in the same file. Even if `throws IllegalArgumentException` is written, callers are still not required to catch it because the type is unchecked.

**Why is it sometimes declared anyway?** It can help readers spot error conditions expected by the contract. However, a better presentation is usually JavaDoc describing **the conditions under which it is thrown**, because an exception type name alone does not explain how to use the API:

~~~java
/**
 * @throws IllegalArgumentException if the input is blank
 * @throws IllegalStateException if the service is unavailable
 */
@Override
public String execute(String input) {
    // ...
    return input;
}
~~~

This is an illustrative snippet belonging to a class with a matching superclass method, not a standalone file.

This is especially important for interfaces whose methods do not declare unchecked exceptions: implementations can throw errors consistent with the contract without forcing every caller to change signatures.

## 5. Complete Java 17 Program: Override, Polymorphism, and Checked/Unchecked

Save the file as **`OverrideUncheckedDemo.java`**. The example has three parts:

1. Interface `Job` declares no checked exceptions; subclass `RemoteJob` overrides it and declares `throws IllegalStateException`.
2. Interface `FileTask` declares `IOException`; implementations can narrow it to `FileNotFoundException` or omit the checked declaration altogether.
3. Abstract class `Gateway` declares no checked exceptions; its implementation catches `IOException` from a technical operation and **wraps it with its cause** in `UncheckedIOException`.

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.UncheckedIOException;

public class OverrideUncheckedDemo {
    interface Job {
        /** Input must be non-null and non-blank. */
        String execute(String input);
    }

    static class BaseJob implements Job {
        @Override
        public String execute(String input) {
            validate(input);
            return "base:" + input;
        }
    }

    static final class RemoteJob extends BaseJob {
        @Override
        public String execute(String input) throws IllegalStateException {
            validate(input);
            if ("busy".equals(input)) {
                throw new IllegalStateException("service unavailable");
            }
            return "remote:" + input;
        }
    }

    private static void validate(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("input required");
        }
    }

    interface FileTask {
        void open() throws IOException;
    }

    static class MissingFileTask implements FileTask {
        @Override
        public void open() throws FileNotFoundException {
            throw new FileNotFoundException("missing.txt");
        }
    }

    static class WorkingFileTask implements FileTask {
        @Override
        public void open() {
            System.out.println("open=ok");
        }
    }

    static abstract class Gateway {
        abstract String load();
    }

    static final class CheckedToUncheckedGateway extends Gateway {
        @Override
        String load() {
            try {
                return fetch();
            } catch (IOException ex) {
                throw new UncheckedIOException("cannot load data", ex);
            }
        }

        private String fetch() throws IOException {
            throw new IOException("upstream offline");
        }
    }

    public static void main(String[] args) {
        System.out.println("== unchecked through interface ==");
        Job job = new RemoteJob();
        System.out.println("result=" + job.execute("ok"));

        try {
            job.execute("busy");
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }

        try {
            job.execute("");
        } catch (IllegalArgumentException ex) {
            System.out.println("input=" + ex.getMessage());
        }

        System.out.println("== checked narrowing ==");
        FileTask missing = new MissingFileTask();
        try {
            missing.open();
        } catch (IOException ex) {
            System.out.println("checked=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }

        FileTask working = new WorkingFileTask();
        try {
            working.open();
        } catch (IOException ex) {
            System.out.println("unexpected=" + ex.getMessage());
        }

        System.out.println("== checked wrapped as unchecked ==");
        Gateway gateway = new CheckedToUncheckedGateway();
        try {
            gateway.load();
        } catch (UncheckedIOException ex) {
            System.out.println("wrapper=" + ex.getClass().getSimpleName());
            System.out.println("cause=" + ex.getCause().getClass().getSimpleName()
                    + ": " + ex.getCause().getMessage());
        }
    }
}
~~~

### Compile and Run

Use JDK 17 or newer:

~~~bash
javac --release 17 -encoding UTF-8 OverrideUncheckedDemo.java
java OverrideUncheckedDemo
~~~

**Exact stdout verified by compiling and running:**

~~~text
== unchecked through interface ==
result=remote:ok
caught=IllegalStateException: service unavailable
input=input required
== checked narrowing ==
checked=FileNotFoundException: missing.txt
open=ok
== checked wrapped as unchecked ==
wrapper=UncheckedIOException
cause=IOException: upstream offline
~~~

The program uses an intentionally created `IOException`, independent of external files or networks, so the error messages and stdout are deterministic. Each expected exception is caught at the exact boundary of its demonstration section.

## 6. Reading the Program Closely: The Unchecked Part of Job

### 6.1. Interface Without throws

~~~java
interface Job {
    String execute(String input);
}
~~~

At compile time, code using a variable of type `Job` sees a signature that **declares no checked exceptions**. Therefore, the caller is not forced to write `try/catch` when simply calling `job.execute("ok")`.

Even so, an implementation can still throw an unchecked exception. That does not change the return type or the call signature seen by the compiler.

### 6.2. Subclass Override and Unchecked Declaration

~~~java
static final class RemoteJob extends BaseJob {
    @Override
    public String execute(String input) throws IllegalStateException {
        validate(input);
        if ("busy".equals(input)) {
            throw new IllegalStateException("service unavailable");
        }
        return "remote:" + input;
    }
}
~~~

The `RemoteJob` class both overrides `BaseJob`'s implementation and satisfies the `Job` interface. The `@Override` annotation instructs the compiler to verify that this is genuinely an override, preventing typos in method names or parameters.

The `throws IllegalStateException` clause **does not violate** the checked exception contract of either the superclass or the interface. Nor does it require callers to declare `throws IllegalStateException`.

However, when `input="busy"`, the call throws `IllegalStateException`, which will propagate to the caller if not caught.

### 6.3. Polymorphism: Variable Type Differs from Runtime Object Type

~~~java
Job job = new RemoteJob();
job.execute("busy");
~~~

The call expression relies on the **static type `Job`** for the compiler to check the signature and checked exceptions. At runtime, Java uses **dynamic dispatch** to select the `RemoteJob.execute` implementation on the actual object.

As a result, the executed method can throw `IllegalStateException`, even though the interface type does not declare `throws`. The runtime does not forbid this merely because the caller views the method through the supertype.

In other words:

- **Static type / signature:** determines compile-time obligations regarding checked exceptions.
- **Runtime implementation:** determines which code executes and which exception is actually thrown.
- **Catch:** if present, selects the matching handler based on the runtime type of the exception.

This is why callback interfaces and frameworks can let unchecked exceptions propagate across multiple layers that do not declare `throws`.

### 6.4. Different Unchecked Exceptions Can Still Represent Two Distinct Errors

In `RemoteJob`, `validate()` can throw `IllegalArgumentException` when the input is null or blank. When the input is `busy`, the implementation throws `IllegalStateException`.

Both are unchecked, but their meanings differ:

- `IllegalArgumentException`: the argument does not satisfy the API's preconditions.
- `IllegalStateException`: the object/service is not in a state that allows completing the operation.

Callers can catch each type separately when there is genuinely an appropriate recovery action. You should not treat every `RuntimeException` as an input error just to "catch them all."

## 7. Reading the Checked Narrowing Part Closely

In the program, the interface defines:

~~~java
interface FileTask {
    void open() throws IOException;
}
~~~

First implementation:

~~~java
class MissingFileTask implements FileTask {
    @Override
    public void open() throws FileNotFoundException {
        throw new FileNotFoundException("missing.txt");
    }
}
~~~

This is **valid checked exception narrowing**. A caller holding an interface-typed reference:

~~~java
FileTask missing = new MissingFileTask();
try {
    missing.open();
} catch (IOException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
~~~

must handle or declare `IOException` according to the **static type `FileTask`**, even though the runtime implementation throws the subtype `FileNotFoundException`.

Second implementation:

~~~java
class WorkingFileTask implements FileTask {
    @Override
    public void open() {
        System.out.println("open=ok");
    }
}
~~~

is allowed to **omit the checked exception declaration entirely** in the override. Yet in the main program:

~~~java
FileTask working = new WorkingFileTask();
try {
    working.open();
} catch (IOException ex) {
    System.out.println("unexpected=" + ex.getMessage());
}
~~~

catching `IOException` is still valid and reasonable given the **interface signature**.

If the variable type is changed directly to `WorkingFileTask`, the compiler knows that this specific implementation declares no checked `IOException`. Writing a `catch (IOException ex)` directly around a call that cannot throw a checked `IOException` can trigger the error *exception is never thrown in body of corresponding try statement*:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
WorkingFileTask working = new WorkingFileTask();
try {
    working.open();
} catch (IOException ex) {
    System.out.println("unreachable for this static call");
}
~~~

The difference here is the **static type of the call expression**, not Java "predicting" the runtime outcome of the implementation.

## 8. When an Override Must Call Code That Throws a Checked Exception Not Allowed by the Superclass

An implementation may have to call an I/O API that declares `throws IOException`, while the superclass/interface method **does not allow adding a checked exception**. There are two main approaches:

1. **Handle and recover locally** if there is a valid way to do so.
2. **Convert to a meaningful unchecked exception, preserving the cause**, if the error needs to propagate to another layer and the method contract does not allow a checked exception to escape.

Example from the main program:

~~~java
static final class CheckedToUncheckedGateway extends Gateway {
    @Override
    String load() {
        try {
            return fetch();
        } catch (IOException ex) {
            throw new UncheckedIOException("cannot load data", ex);
        }
    }

    private String fetch() throws IOException {
        throw new IOException("upstream offline");
    }
}
~~~

`Gateway.load()` declares no checked exceptions. `CheckedToUncheckedGateway.load()` still overrides validly because it **catches** `IOException` inside the method body and then throws `UncheckedIOException`.

`UncheckedIOException` is a standard class introduced in Java 8 that extends `RuntimeException` and is designed to carry an `IOException` as its cause. The line:

~~~java
throw new UncheckedIOException("cannot load data", ex);
~~~

preserves the source information via `getCause()`; it **does not discard the original error** to replace it with a contextless message.

**Not every checked exception should be wrapped in `UncheckedIOException`**. This class is specifically for `IOException`. For other checked types, choose an unchecked exception that makes sense for the API contract, such as `IllegalStateException("context", cause)` or an appropriate custom runtime exception.

**Do not use wrapping to dodge design:** if the caller is required to resolve an expected business error, simply wrapping it as unchecked to silence the compiler can cause callers to forget to handle it. You must clearly determine whether the error type is recoverable before deciding.

## 9. New Unchecked Exceptions Can Be Thrown, But Behavioral Contracts Must Hold

At the language level, a subclass is allowed to declare or throw new unchecked exceptions. At the design level, **a subclass must still be substitutable for its superclass/interface in valid contexts** (*substitutability*).

API example:

~~~java
class Formatter {
    /** Accepts any non-null String, including a 1-character String. */
    String format(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value required");
        }
        return "ok:" + value;
    }
}
~~~

An override should not arbitrarily raise the minimum requirement to "must be at least 3 characters":

~~~java
class StrictFormatter extends Formatter {
    @Override
    String format(String value) {
        if (value.length() < 3) {
            throw new IllegalArgumentException("too short");
        }
        return super.format(value);
    }
}
~~~

The two classes above are **illustrative snippets** without `main`; they compile, but the override has **contract issues**:

- Under `Formatter`'s contract, the value `"A"` is a valid input.
- With `StrictFormatter`, the value `"A"` causes an unchecked `IllegalArgumentException`.
- A caller holding a `Formatter`-typed reference can unexpectedly fail on an input previously guaranteed to be valid.
- The override also lacks consistent null checking: for `null`, `value.length()` causes a `NullPointerException` instead of the same `IllegalArgumentException` as the parent.

**The compiler still accepts it**, because this is not a violation of checked exception rules or override signatures. However, the design can violate the behavior promised by the API.

Solutions:

- Do not **strengthen preconditions** for inputs that the superclass contract has promised to accept.
- Do not **weaken postconditions** or break invariants that callers are entitled to rely on.
- Clearly document **valid** unchecked exceptions according to the API (e.g., null input, service unavailable state).
- For variants that genuinely have a different contract, consider a **separate API/method/type**, rather than forcing an override into unpredictable behavior.

This is the spirit of applying the **Liskov Substitution Principle**, even though the JLS only enforces part of these constraints.

## 10. Interface Exception Contracts Should Describe Expected Behavior

An interface may declare no checked exceptions and still need JavaDoc describing unchecked errors:

~~~java
interface Job {
    /**
     * Executes the task with a valid input string.
     *
     * @param input a non-null, non-blank string
     * @return the processing result
     * @throws IllegalArgumentException if input is invalid
     * @throws IllegalStateException if the service is not ready
     */
    String execute(String input);
}
~~~

This is a valid interface illustrating a contract. An implementation should honor the promised conditions, regardless of whether it declares `throws IllegalStateException` in code.

When writing an override, the following cases need careful consideration:

| Override behavior | Allowed by compiler? | Contract-compatible? |
| --- | --- | --- |
| Throw `IllegalArgumentException` when input is null and contract forbids null | Yes | Usually yes |
| Throw `IllegalStateException` when service is not ready as described by contract | Yes | Usually yes |
| Throw `IllegalArgumentException` for input the contract guaranteed to be valid | Yes | May violate contract |
| Throw unchecked from an unhandled internal bug | May compile | Should not be treated as a guaranteed business outcome |
| Add `throws IOException` to an override of a method with no checked throws | No | No runtime outcome because it does not compile |
| Catch `IOException` and wrap in `UncheckedIOException` with cause | Yes | Depends on contract and recovery policy |

There is no need to list every possible `NullPointerException` caused by bugs in JavaDoc; prioritize error conditions that are **expected and meaningful to the caller**.

## 11. Catch Ordering When Handling Unchecked Exceptions

A call through a supertype variable can still throw different runtime subtypes. If you choose to catch them, Java requires placing **more specific catches before more general ones**:

~~~java
try {
    job.execute(input);
} catch (IllegalArgumentException ex) {
    handleInvalidInput(ex);
} catch (IllegalStateException ex) {
    handleUnavailable(ex);
} catch (RuntimeException ex) {
    reportUnexpected(ex);
}
~~~

This is an illustrative structure with handler methods that need to be defined. `IllegalArgumentException` and `IllegalStateException` are sibling subtypes with no inheritance order required between them; however, both must precede `RuntimeException` if they appear in the same `catch` chain.

Writing them in reverse:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
try {
    job.execute(input);
} catch (RuntimeException ex) {
    reportUnexpected(ex);
} catch (IllegalStateException ex) {
    handleUnavailable(ex);
}
~~~

causes the second `catch` to be shadowed because `RuntimeException` already catches every `IllegalStateException`.

**You should not catch `RuntimeException` at every layer and let execution continue**. Catching broadly can sometimes make sense at a task/web-request boundary to log and translate into a system error, but a clear policy is needed to avoid hiding bugs.

## 12. Checked Exceptions Can Still Come from a Supertype Reference

This is an easily confused distinction between the Java compiler and runtime:

~~~java
interface ReaderTask {
    String read() throws IOException;
}

class ConstantReader implements ReaderTask {
    @Override
    public String read() {
        return "fixed data";
    }
}
~~~

These are illustrative declarations that require importing `IOException`.

- Calling `read()` on a `ReaderTask`-typed variable still has the compile-time contract `throws IOException`.
- Calling the exact same override on a `ConstantReader`-typed variable has no `throws IOException`, so there is no need to declare checked `IOException` merely because the interface declares it.
- If a caller encounters another implementation that validly throws `IOException`, catching/handling the exception will be based on the actual object at runtime.

Thus, **an override is allowed to narrow checked throws** and **unchecked exceptions can arise outside the checked list**. The two rules do not contradict each other.

## 13. When a Class Implements Multiple Interfaces with Different throws Clauses

Suppose two interfaces have methods with the same signature:

~~~java
interface LocalAction {
    void execute() throws java.io.IOException;
}

interface DatabaseAction {
    void execute() throws java.sql.SQLException;
}
~~~

A class implementing both must provide an overriding implementation that is valid for **both contracts**. For example:

~~~java
class UnifiedAction implements LocalAction, DatabaseAction {
    @Override
    public void execute() throws IllegalStateException {
        throw new IllegalStateException("not ready");
    }
}
~~~

This is **valid**: the implementation declares no checked exceptions and only declares the unchecked `IllegalStateException`. Because a common checked exception type would have to be compatible with both inherited methods, you cannot arbitrarily add `throws IOException` or `throws SQLException` to the shared override when only one side declares that type.

This is an extended case showing why **having no checked throws** often makes it easier to implement multiple interfaces with different contracts; however, unchecked exceptions must still respect the behavioral guarantees of **each** interface.

If a class is forced to perform an I/O operation that throws a checked exception, it can still handle it locally or wrap the exception after weighing the design.

## 14. Are Error Exceptions Also Permitted in Overrides?

By language definition, `Error` and its subclasses are also **unchecked exceptions**. The compiler does not require declaring `throws Error` and does not restrict them under override checked-throws rules.

However, **you should not use `Error` to represent business errors** or use it as a way to bypass the compiler. `Error` classes are typically reserved for serious situations such as class linkage errors or JVM-level resource failures; normal applications should not design recovery flows around them.

If you need to represent an unchecked application error condition, typically use a subtype of `RuntimeException` with an appropriate message and cause.

## 15. Distinguishing Easily Confused Concepts When Overriding

### 15.1. Override vs. Overload

~~~java
class Parent {
    void work(String value) { }
}

class Child extends Parent {
    @Override
    void work(String value) throws IllegalStateException { }

    void work(int value) throws java.io.IOException { }
}
~~~

These are illustrative classes that **compile**, in which:

- `work(String)` in `Child` **overrides** `Parent`'s method, so the superclass method's checked-throws restriction applies.
- `work(int)` in `Child` is an **overload with a different signature**, not an override of `Parent.work(String)`. It can declare `IOException` because it is not constrained by `Parent.work(String)`'s `throws`, though callers must handle checked `IOException` if they call this overload.

`@Override` helps catch mistakes. If `@Override` is placed on `work(int)` in this example, the compiler will report an error because that method does not override any corresponding method.

### 15.2. Not Every Method with the Same Name Is an Override

- A `static` method with the same signature in a subclass is **method hiding**, not dynamic overriding.
- A `private` method in a superclass is not inherited as an overridable method.
- A `final` method is not permitted to be overridden.
- Constructors are not overridden.

These cases follow different language rules; do not mechanically apply reasoning about overriding exceptions to every method sharing a name.

### 15.3. The throws Signature Does Not Determine Runtime Catching

A method may declare `throws IllegalStateException` yet actually throw `IllegalArgumentException` or throw nothing at all. Matching a `catch` at runtime is based on **the actual runtime type of the thrown `Throwable` object**, not simply the type name in the `throws` clause.

Therefore, `throws RuntimeException` is not a "barrier" guaranteeing that only `RuntimeException` can arise in all circumstances; `Error`s can also occur, and checked exceptions can only propagate under valid language rules or unusual external mechanisms.

## 16. How to Review an Override That Involves Exceptions

When you see a subclass overriding a method, check in order:

1. **Identify the exact superclass/interface method** being overridden by the signature; is `@Override` present?
2. **Note the checked throws of the superclass method**, distinguishing them from unchecked throws.
3. **Classify each type in the override's `throws`:** checked or unchecked?
4. **If checked**, verify it is valid under the parent contract; do not add a broader or new checked type.
5. **If unchecked**, remember compile time allows it, but read JavaDoc/preconditions/postconditions to determine behavioral compatibility.
6. **Read the body:** does it call any checked-exception APIs? If so, are they caught/declared validly? Is it wrapped into an unchecked exception while preserving the cause?
7. **Check the caller's static type:** calling via the interface versus via the implementation leads to different checked-exception analysis.
8. **Test with runtime polymorphism:** with a parent variable pointing to a child instance, is the exception caught properly and is promised behavior preserved?
9. **Check catch boundaries:** do not catch too broadly and ignore programming bugs; log the exception object rather than just the message.
10. **Check error-translation policy:** do not wrap a recoverable business checked exception into a `RuntimeException` solely to avoid `throws`.

When every step checks out, an override can declare additional unchecked exceptions at the language level while still maintaining an easy-to-use API contract.

## 17. Common Misconceptions

- **"The parent method has no `throws`, so the child method cannot throw any exception."** False: unchecked exceptions can still be thrown.
- **"The child method has `throws RuntimeException`, so the caller must catch it."** False: unchecked exceptions create no compile-time obligation.
- **"Only `RuntimeException` is unchecked."** Incomplete: `Error` and its subclasses are also unchecked.
- **"A child method can expand checked `throws` just like a normal overload."** False: overrides are constrained by the parent method's checked `throws`.
- **"If the base `throws IOException`, the child can `throws Exception`."** False: broadening checked `throws` is invalid.
- **"A child throwing `FileNotFoundException` instead of `IOException` is wrong."** False: `FileNotFoundException` is a subtype of `IOException`.
- **"If an interface declares no exceptions, an implementation cannot throw `IllegalStateException`."** False: it is an unchecked exception.
- **"Assigning to an interface variable and calling an implementation does not affect error handling."** You must distinguish compile-time checking via the static type from runtime dynamic dispatch.
- **"If an implementation drops `throws IOException`, callers via the interface don't need to handle `IOException`."** False: calls through the interface type still follow the interface's checked signature.
- **"Wrapping `IOException` into `UncheckedIOException` loses the original cause."** False if using a constructor that accepts a cause; check `getCause()`.
- **"Wrapping checked exceptions into unchecked ones is always a good decision."** False: it depends on the contract and the caller's ability to recover.
- **"The compiler allows a new unchecked exception, so it is always LSP-compatible."** False: the override may strengthen preconditions or break behavioral guarantees.
- **"Catching `RuntimeException` before `IllegalStateException` is fine."** False: the specific handler is shadowed and will not compile.
- **"`throws IllegalStateException` means the method only throws that type."** False: the `throws` clause does not describe every runtime error.
- **"Changing the input contract in a subclass is just an implementation detail."** False if it causes valid callers of the superclass to stop working properly.
- **"`@Override` affects runtime exceptions."** No: this annotation helps the compiler verify overriding; runtime throw/catch mechanics do not change.

## 18. Self-Check Questions

**Question 1.** Interface `Action { void run(); }`; an overriding implementation declares `throws IllegalArgumentException`. Does it compile?

*Answer:* Yes. `IllegalArgumentException` is unchecked. Callers are not forced to catch it because of that declaration.

**Question 2.** What if the implementation's declaration is changed to `throws IOException`?

*Answer:* It does not compile if the interface/base does not permit checked `IOException` on the overridden method.

**Question 3.** Base method declares `throws IOException`. Child override declares `throws FileNotFoundException`. Is this valid?

*Answer:* Yes. `FileNotFoundException` is a checked subtype of `IOException`, meaning it narrows `throws`.

**Question 4.** Base `throws IOException`, child `throws Exception`. Is this valid?

*Answer:* No. `Exception` is a checked supertype broader than `IOException`.

**Question 5.** Why does `FileTask task = new WorkingFileTask();` still require handling `IOException` when calling `task.open()`?

*Answer:* The compiler checks the call against the static type `FileTask`, which declares `throws IOException`, even though the `WorkingFileTask` implementation does not declare it.

**Question 6.** If an override wants to call `Files.readString(path)` inside a superclass method that declares no checked `throws`, what must it do?

*Answer:* Catch/handle `IOException` inside the override, or translate it into an unchecked exception compatible with the contract while preserving the cause. It must not simply add `throws IOException` against override rules.

**Question 7.** Why is adding an unchecked `IllegalArgumentException` when input `"A"` was allowed by the base class problematic?

*Answer:* The compiler allows it, but the override's behavior can strengthen preconditions, violating substitutability and the caller's contract.

**Question 8.** Do you need to write `throws IllegalStateException` to throw `IllegalStateException`?

*Answer:* No. That declaration is optional and does not make the exception checked.

**Question 9.** A class implements two interfaces with the same `execute()` method: the first `throws IOException`, the second `throws SQLException`, and the implementation declares no checked throws but has `throws IllegalStateException`. Is this valid?

*Answer:* Yes. Unchecked exceptions are not constrained by the checked `throws` of the two interfaces.

**Question 10.** If you catch `RuntimeException` and ignore it to continue business logic, is it always safe?

*Answer:* No. It can hide bugs or a serious state error. Broad catches should only exist at boundaries with a clear handling policy.

## 19. Official References

- [JLS Java SE 17 Section 8.4.8.3 – Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exception restrictions when overriding methods.
- [JLS Java SE 17 Section 9.4.1.3 – Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3): conditions for overriding/implementing interface methods.
- [JLS Java SE 17 Section 8.4.6 – Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): meaning of a method's `throws` clause.
- [JLS Java SE 17 Chapter 11 – Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked classification and exception-checking mechanism.
- [Java SE 17 API – RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): unchecked branch for runtime errors.
- [Java SE 17 API – UncheckedIOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): unchecked wrapper preserving the `IOException` cause.
- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): message, cause, and stack trace.

**Remember:** **An override is permitted to declare or throw unchecked exceptions**, even when the superclass/interface method has no `throws` clause. **Checked exceptions must obey the superclass method's contract** and cannot be arbitrarily added or broadened. However, an override accepted by the compiler is not necessarily well-designed: preserve preconditions/postconditions, document expected errors, preserve the cause when wrapping, and consider how callers invoke the method through the supertype.
