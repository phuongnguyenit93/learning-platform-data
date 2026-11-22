# Constructors Throwing Exceptions and the `InvocationTargetException` Wrapper in Java Reflection

When creating an object via Java Reflection, `Constructor.newInstance(...)` can fail for **two very different categories of reasons**:

1. **The application's constructor was actually invoked and then threw an exception/error**. Reflection wraps the original error object in `java.lang.reflect.InvocationTargetException`. The caller needs to inspect `getCause()` to see the real issue.
2. **Reflection could not yet invoke a valid constructor**, for example due to wrong argument types, missing access permissions, an abstract target type, or failed class initialization. These cases are normally reported via **their own specific exceptions/errors**, and should not be assumed to be `InvocationTargetException`.

Distinguishing these two categories properly helps programmers fix errors in the right place: checking constructor input data, resolving access/module configuration, or fixing logic inside the constructor.

The goal of this lesson is to understand accurately when `InvocationTargetException` appears, how to unwrap it to handle checked/unchecked exceptions, how to recognize unwrapped errors, and how to write compilable/runnable and diagnosable Java 17+ code.

## 1. Distinguishing Constructor Lookup from Constructor Invocation

A `Class<T>` object provides:

```java
Constructor<T> ctor = type.getConstructor(parameterTypes);
Constructor<T> declared = type.getDeclaredConstructor(parameterTypes);
```

These two statements only retrieve **metadata about a constructor**. They do not yet create an object and do not yet run the constructor body. `getConstructor` searches only for `public` constructors with the exact sequence of parameter types; `getDeclaredConstructor` searches for constructors declared directly on the class, including private constructors.

Instance creation occurs when calling:

```java
T instance = ctor.newInstance(arguments);
```

This is a code pattern illustrating the idea; `T`, `type`, `parameterTypes`, and `arguments` must be defined in an actual program. Two kinds of issues must be kept separate:

- **Lookup failure:** `getConstructor(String.class)` cannot find a matching public signature and throws `NoSuchMethodException`. At that point, the constructor has not run.
- **Invocation failure:** after metadata is found, `newInstance("abc")` attempts to initialize the class (if needed), check permissions/arguments, and execute the constructor. When **the constructor itself** throws an error, Reflection emits an `InvocationTargetException` wrapping the original error.

`Constructor<T>` belongs to package `java.lang.reflect`. The method `newInstance(Object... initargs)` has return type `T`, which does not mean the call is guaranteed to succeed or that every failure produces the same exception type.

## 2. Why Does Java Reflection Need `InvocationTargetException`?

A constructor can declare and throw a checked exception:

```java
public Person(String name) throws java.io.IOException {
    if (name == null) {
        throw new java.io.IOException("name is required");
    }
}
```

If called directly as `new Person(null)`, the caller must handle or declare `IOException` per Java's checked exception rules. Yet when Reflection calls `Constructor.newInstance(...)`, the API signature cannot list in advance every checked exception that **any runtime constructor** might throw.

Therefore, if the constructor executes and throws `IOException`, `IllegalArgumentException`, `AssertionError`, or another `Throwable` from the constructor body, Reflection reports an **`InvocationTargetException`**, holding the original error as its **cause**.

Model:

```text
Constructor.newInstance(arguments)
          |
          +-- prepare/check access, parameters, types, class initialization
          |
          +-- invoke constructor <init>
                    |
                    +-- succeeds -------------------> returns instance
                    |
                    +-- throws IOException ---------> InvocationTargetException
                    |                                    cause = IOException
                    +-- throws IllegalStateException -> InvocationTargetException
                    |                                    cause = IllegalStateException
                    +-- throws AssertionError ------> InvocationTargetException
                                                         cause = AssertionError
```

The diagram depicts **errors originating inside the invoked constructor**. Exceptions or errors occurring in **preceding Reflection steps**, especially class initialization errors, follow separate rules and are not included in the wrapping branch above.

### Two Properties of the Wrapper

`InvocationTargetException` is a **checked exception**. It has:

- `getCause()`: returns the original `Throwable` that caused the invocation to fail.
- `getTargetException()`: a legacy compatibility method that also grants access to the original exception. In modern code, `getCause()` is generally preferred.

Sample usage:

```java
try {
    Object instance = constructor.newInstance(values);
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable original = e.getCause();
    // Inspect original to find the actual error from the constructor.
}
```

This is an illustrative snippet; `constructor` and `values` come from the caller, and other checked exceptions of `newInstance` need to be handled or declared additionally. Do not merely print `InvocationTargetException` and ignore `cause`, because the primary business error usually lies in the inner layer.

## 3. Complete Java 17+ Example: Distinguishing Multiple Error Types

Save the program as **`ConstructorExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ConstructorExceptionDemo {
    public static class Worker {
        private final String name;

        public Worker(String name) throws IOException {
            if (name == null) {
                throw new IOException("name is required");
            }
            if (name.isBlank()) {
                throw new IllegalArgumentException("blank name");
            }
            if (name.equals("error")) {
                throw new AssertionError("fatal problem");
            }
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public abstract static class AbstractWorker {
        public AbstractWorker() { }
    }

    public static class BrokenInit {
        static {
            if (shouldFail()) {
                throw new IllegalStateException("init failed");
            }
        }

        static boolean shouldFail() {
            return true;
        }

        public BrokenInit() { }
    }

    private static void printCause(String label, InvocationTargetException e) {
        Throwable cause = e.getCause();
        System.out.println(label + ": "
                + cause.getClass().getSimpleName()
                + " -> " + cause.getMessage());
    }

    public static void main(String[] args) throws Exception {
        Constructor<Worker> ctor = Worker.class.getConstructor(String.class);

        System.out.println("throws declared: "
                + ctor.getExceptionTypes()[0].getSimpleName());
        System.out.println("success: " + ctor.newInstance("Lan").getName());

        try {
            ctor.newInstance((Object) null);
        } catch (InvocationTargetException e) {
            printCause("checked", e);
        }

        try {
            ctor.newInstance(" ");
        } catch (InvocationTargetException e) {
            printCause("unchecked", e);
        }

        try {
            ctor.newInstance("error");
        } catch (InvocationTargetException e) {
            printCause("error", e);
        }

        try {
            ctor.newInstance(5);
        } catch (IllegalArgumentException e) {
            System.out.println("argument mismatch: "
                    + e.getClass().getSimpleName());
        }

        try {
            Worker.class.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup failure: "
                    + e.getClass().getSimpleName());
        }

        Constructor<AbstractWorker> abstractCtor =
                AbstractWorker.class.getConstructor();
        try {
            abstractCtor.newInstance();
        } catch (InstantiationException e) {
            System.out.println("abstract: "
                    + e.getClass().getSimpleName());
        }

        Constructor<BrokenInit> brokenCtor =
                BrokenInit.class.getConstructor();
        try {
            brokenCtor.newInstance();
        } catch (ExceptionInInitializerError e) {
            Throwable root = e.getCause();
            System.out.println("class initialization: "
                    + root.getClass().getSimpleName()
                    + " -> " + root.getMessage());
        }
    }
}
```

Run from the directory containing the file with JDK 17 or newer:

```bash
javac ConstructorExceptionDemo.java
java ConstructorExceptionDemo
```

**Stdout verified on JDK 21:**

```text
throws declared: IOException
success: Lan
checked: IOException -> name is required
unchecked: IllegalArgumentException -> blank name
error: AssertionError -> fatal problem
argument mismatch: IllegalArgumentException
lookup failure: NoSuchMethodException
abstract: InstantiationException
class initialization: IllegalStateException -> init failed
```

### Analyzing Each Result

1. `getExceptionTypes()` lists the exception types present in the constructor's `throws` declaration. `Worker(String)` declares `IOException`, so the first line prints `IOException`. This metadata **does not mean the constructor always throws an exception**.
2. `ctor.newInstance("Lan")` invokes the constructor successfully; the program receives an instance and prints `success: Lan`.
3. `ctor.newInstance((Object) null)` passes **a single `null` argument** to the `String` parameter. The constructor is invoked, checks `name == null`, and throws `IOException`. Reflection wraps it in `InvocationTargetException`. `getCause()` retrieves `IOException` along with its message.
4. `ctor.newInstance(" ")` invokes the constructor; `isBlank()` returns `true`, so the constructor throws unchecked `IllegalArgumentException`. Because the error originates **inside the constructor**, Reflection still wraps it in `InvocationTargetException`.
5. `ctor.newInstance("error")` causes the constructor itself to throw `AssertionError`. In this example, `InvocationTargetException` also wraps `AssertionError`: the wrapper does not apply only to checked exceptions. You should not automatically catch and ignore every `Error` in production applications.
6. `ctor.newInstance(5)` has an **incompatible argument type** for constructor `Worker(String)`. Reflection throws `IllegalArgumentException` right at the invocation layer; the constructor body does not run. This **is not** `InvocationTargetException`.
7. `Worker.class.getConstructor(int.class)` fails at the **lookup step** because no public constructor `Worker(int)` exists. The result is `NoSuchMethodException`.
8. `AbstractWorker` has a public constructor yet is an **abstract class**; Reflection cannot instantiate it directly, so `Constructor.newInstance()` throws `InstantiationException`.
9. `BrokenInit` has a static initializer block that throws `IllegalStateException`. Class initialization fails **before the constructor body runs**. The JVM emits `ExceptionInInitializerError`; do not confuse this with `InvocationTargetException`.

In the example, nested classes are declared `public static` and the needed constructors are public, avoiding noise from visibility errors. Access permission errors will be explained separately.

## 4. Identification Table: Which Layer Did the Error Come From?

| Failure point | Situation | Observed error | Wrapped by `InvocationTargetException`? |
|---|---|---|---|
| Lookup on `Class` | Matching constructor does not exist | `NoSuchMethodException` | No |
| Preparing invocation | Incompatible argument count/types | `IllegalArgumentException` | No |
| Preparing invocation | Caller lacks permission to invoke constructor | `IllegalAccessException` | No |
| Preparing invocation | Cannot instantiate an abstract class | `InstantiationException` | No |
| Class initialization | Static initializer fails with an exception other than `Error` | `ExceptionInInitializerError` | No |
| Inside constructor body | `throw new IOException(...)` | `InvocationTargetException`, cause = `IOException` | Yes |
| Inside constructor body | `throw new IllegalStateException(...)` | `InvocationTargetException`, cause = `IllegalStateException` | Yes |
| Inside constructor body | `throw new AssertionError(...)` | `InvocationTargetException`, cause = `AssertionError` | Yes |

The table reflects typical cases via **core Reflection**. When class initialization directly throws an `Error`, the JVM may propagate that error according to initialization rules; subsequent repeated initialization failures of the same runtime class typically produce `NoClassDefFoundError`. There is no guarantee that every error before the constructor is `ExceptionInInitializerError`.

**Special note on `IllegalArgumentException`:** the same exception name from different error sources creates two different catch patterns:

```java
// Wrong argument type: Reflection itself throws IllegalArgumentException.
ctor.newInstance(Integer.valueOf(5));

// Valid argument String, yet the constructor itself throws
// IllegalArgumentException: Reflection wraps it in InvocationTargetException.
ctor.newInstance(" ");
```

These two lines are excerpts from the complete program and must not be run back-to-back without exception handling. To conclude where the error originated, rely on the **outer exception type** and **cause**, not merely seeing the name `IllegalArgumentException` appear in a stack trace.

## 5. `getCause()`: Inspecting the Root Error Without Losing Information

When catching `InvocationTargetException`, call:

```java
catch (InvocationTargetException e) {
    Throwable cause = e.getCause();
    cause.printStackTrace();
}
```

This is an illustrative `catch` branch placed inside an appropriate `try` block. `printStackTrace()` helps reveal **the error path inside the constructor**; there is no need to print duplicate stack traces to logs simultaneously. In real applications, you can log the full `e` so the JVM displays the `Caused by` chain.

Use `Throwable` for cause because constructor code can throw a **checked exception, unchecked exception, or `Error`**. Do not blindly cast every cause to `Exception` without checking its type.

`InvocationTargetException.getTargetException()` also returns the original exception, but `getCause()` follows Java's standard exception chaining model, convenient for logging and `Throwable`-processing systems.

### Preserving the Cause Chain When Reporting Errors Upward

If an application wants to convert the error into a contextual exception:

```java
try {
    return ctor.newInstance(value);
} catch (InvocationTargetException e) {
    throw new IllegalStateException(
            "Failed to create " + ctor.getDeclaringClass().getName(),
            e.getCause());
}
```

This is an **illustrative snippet inside a factory method** with `ctor` and `value` already available, along with handling/declaring other Reflection exceptions. The `IllegalStateException(String, Throwable)` constructor preserves the **original cause**; reading the stack trace still traces back to the root error.

Re-wrapping is an **API contract decision**. For expected business errors (e.g. invalid user data), some APIs prefer propagating the exact checked exception type. For a severe `Error`, it generally should not be turned into an ordinary business error and allowed to continue running.

### Do Not Assume `getCause()` Is the Final Error

A constructor may call another service and receive an exception that already wraps a deeper exception, such as an `IllegalStateException` whose cause is an `IOException`. Then:

```text
InvocationTargetException
└── IllegalStateException
    └── IOException
```

Calling `getCause()` once only unwraps **the Reflection wrapper**. To investigate all the way down, inspect the entire cause chain as well as any suppressed exceptions. Do not assume a loop unwrapping to the very end is always the right business handling; an intermediate exception layer may carry important context.

## 6. Checked Exceptions and Unchecked Exceptions in Constructors

The difference between the **`throws` declaration** and **actual runtime errors** is a very important point:

```java
public Worker(String name) throws IOException {
    if (name == null) throw new IOException("name is required");
    if (name.isBlank()) throw new IllegalArgumentException("blank name");
    this.name = name;
}
```

- `IOException` is a checked exception: declared in `throws IOException`, reflected by `Constructor.getExceptionTypes()`.
- `IllegalArgumentException` is an unchecked exception: not required to appear in `throws`, yet the constructor can still throw it.
- Both become `InvocationTargetException` at the **outer layer** when the constructor is invoked via `Constructor.newInstance`.
- `getExceptionTypes()` is only **declared metadata**, not a complete guaranteed list of every error that can actually occur. It does not predict which code paths will execute.

A constructor can also call another constructor via `this(...)` or `super(...)`. If a constructor in that chain throws an exception, instance initialization fails. When the Reflection call originates from `Constructor.newInstance` and the exception arises within the constructor execution flow, the exception is surfaced inside the `InvocationTargetException` wrapper.

Therefore, when diagnosing **why `newInstance` failed**, examine the code that actually runs during construction, including field initializers, instance initializer blocks, and related constructor calls, rather than looking only at `return` or `throws` lines at the outer level.

## 7. Distinguishing Class Initialization Errors from Constructor Errors

Java has two kinds of initialization that are easily confused:

- **Class initialization:** executes static field initializers and `static` blocks (`<clinit>`). It occurs according to JVM rules when a class is actively used, prior to creating an instance of the class.
- **Instance/constructor initialization:** executes object initialization, instance field initializers, and the constructor (`<init>`) in Java-specified order.

In the program's `BrokenInit` example, the static initializer fails. Merely obtaining metadata:

```java
Constructor<BrokenInit> constructor =
        BrokenInit.class.getConstructor();
```

normally **does not actively initialize `BrokenInit`**. However:

```java
constructor.newInstance();
```

requests creating an instance, so the JVM must ensure the class is initialized first. If the static initializer fails due to `IllegalStateException`, the JVM emits `ExceptionInInitializerError`; constructor `BrokenInit()` **never ran**. This is a class initialization error, not an exception from an invoked constructor body.

Subsequent active access to the same class after initialization has failed can trigger `NoClassDefFoundError` because the class is in an erroneous state. Do not repeatedly retry the same runtime class expecting the static block to rerun as if it had never failed.

Another situation: the constructor begins running, yet an instance field initializer or superclass constructor throws an error; Reflection will typically wrap that error in `InvocationTargetException` because the error occurred during instance initialization execution. When diagnosing, inspect the **stack trace of the cause** to locate the true origin.

## 8. How Does `Class.newInstance()` Differ from `Constructor.newInstance()`?

Do not infer identical exception behavior from similar names:

| API | Status | How constructor exceptions are handled |
|---|---|---|
| `Constructor<T>.newInstance(Object... initargs)` | Current Reflection API, allows selecting constructors by signature | Wraps exceptions thrown by the constructor in `InvocationTargetException` |
| `Class<T>.newInstance()` | **Deprecated** since Java 9; should not be used in new code | Can directly propagate exceptions from the constructor, including checked exceptions not explicitly listed in the API's `throws` |

`Class.newInstance()` is a legacy API that uses only an accessible no-arg constructor and has many limitations. Java API documentation recommends using `getDeclaredConstructor().newInstance()` instead for clear constructor selection and exception handling.

That means:

```java
Sample obj = Sample.class.getDeclaredConstructor().newInstance();
```

is the common pattern for new code when a no-arg constructor is needed (assuming a matching constructor exists and the caller is permitted to use it). Yet `getDeclaredConstructor()` finding metadata **does not mean** every private constructor is permitted across modules; access rules still apply.

When upgrading legacy frameworks that use `Class.newInstance()`, review exception handling because the new API's wrapping differs from the old API. Do not merely rename the method while keeping the exact same catch logic mechanically.

## 9. Access Permissions, Private Constructors, and Module Boundaries

`InvocationTargetException` does not mean "the constructor is private":

- `getConstructor(...)` only finds `public` constructors. For a private constructor, lookup may throw `NoSuchMethodException`.
- `getDeclaredConstructor(...)` can find a private constructor, yet when calling `newInstance`, the caller may encounter `IllegalAccessException`.
- `trySetAccessible()` or `setAccessible(true)` can permit suppressing access checks **when class/module relationships allow it**. With Java named modules, deep reflection across packages may require an appropriate `opens`; `setAccessible(true)` may throw `InaccessibleObjectException` if opening is not allowed.
- An `abstract` class cannot be instantiated merely because its constructor is public; `InstantiationException` remains the appropriate error.
- A constructor may receive the right number of arguments yet the **wrong types**. When there is no valid Reflection conversion, `IllegalArgumentException` occurs before the constructor body is called.

Thus, catching `InvocationTargetException` should be dedicated to **errors from executing the constructor**, while lookup/access/type/instantiation errors must be diagnosed separately.

### With Varargs Constructors, Avoid Confusing One `null` Argument with a `null` Varargs Array

`Constructor.newInstance` has signature `Object... initargs`. To pass **one `null` argument** to constructor `Worker(String)`, use:

```java
ctor.newInstance((Object) null);
```

Casting to `(Object)` clarifies that this is **a single argument**, rather than a `null` value that might be interpreted as the entire varargs array. Since `Worker(String)` takes a `String` reference, `null` is a validly typed argument; the constructor will run and itself throw `IOException`.

If `null` is passed to a primitive parameter or argument count/types do not match the constructor signature, Reflection may report `IllegalArgumentException` before running the constructor body. Do not assume that error was wrapped.

## 10. Designing Error Handling in a Factory/Framework

A factory may need clear rules:

1. Select the constructor by **exact** parameter types.
2. Check caller/module access permissions.
3. Validate input data before invoking if there is an input contract.
4. Invoke `newInstance`.
5. If `InvocationTargetException` occurs, inspect `getCause()` to handle the error from the constructor.
6. Handle lookup, access, illegal argument, abstract class, and class initialization errors separately.

Controlled handling pattern for a public constructor taking `String` (this snippet is an **illustrative method** that can be placed in an appropriate class):

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

static <T> T construct(Class<T> type, String name) {
    final Constructor<T> ctor;
    try {
        ctor = type.getConstructor(String.class);
    } catch (NoSuchMethodException e) {
        throw new IllegalArgumentException(
                "No public constructor(String) in " + type.getName(), e);
    }

    try {
        return ctor.newInstance(name);
    } catch (InvocationTargetException e) {
        Throwable cause = e.getCause();

        if (cause instanceof Error error) {
            throw error;
        }
        if (cause instanceof RuntimeException runtime) {
            throw runtime;
        }
        throw new IllegalStateException(
                "Checked exception from constructor of " + type.getName(),
                cause);
    } catch (InstantiationException | IllegalAccessException e) {
        throw new IllegalStateException(
                "Cannot instantiate " + type.getName(), e);
    }
}
```

**Note:** The code block above is a **method template placed inside a class**, not a standalone program; imports belong at the top of the file. The sample defines one concrete contract: rethrowing `Error` and unchecked `RuntimeException`, wrapping checked exceptions in `IllegalStateException`. This is a design choice, **not a mandatory rule** for every framework. `IllegalArgumentException` from wrong Reflection arguments can propagate out; if a custom message is desired, add an appropriate catch branch and context.

For APIs with publicly declared checked exceptions, you may want to preserve the exact checked exception type per the contract rather than wrapping into `IllegalStateException`. In that case, handle the calling method's types/`throws` according to Java language rules, without arbitrary `Throwable` casts.

Avoid:

```java
catch (Exception e) {
    return null;
}
```

This is an **anti-pattern shown only for illustration**. It lumps missing-constructor errors, access errors, and business errors into the same `null` value, destroying diagnostic information. Even if a factory has semantics returning optional/nullable when unable to create an object, it still needs to distinguish which errors fall under expected handling.

## 11. Testing Failing Constructors

When writing tests for Reflection, verify **both the outer layer and the cause**:

```java
// JUnit 5 assertion example;
// placed inside a test method with appropriate JUnit imports and dependency.
InvocationTargetException thrown = assertThrows(
        InvocationTargetException.class,
        () -> ctor.newInstance((Object) null)
);
assertInstanceOf(java.io.IOException.class, thrown.getCause());
assertEquals("name is required", thrown.getCause().getMessage());
```

This is an illustrative test snippet, **not part of the standalone runnable Java program in section 3**. `ctor` is the already looked-up `Constructor<Worker>`, while `assertThrows`, `assertInstanceOf`, and `assertEquals` are JUnit Jupiter APIs. Tests help clearly distinguish "Reflection could not invoke" from "the constructor ran and reported an error".

Practical test cases include: successful constructor; checked exception from constructor body; unchecked exception; Reflection wrong-argument error; nonexistent constructor; blocked access; failed class initialization. For `Error`, avoid accidentally swallowing it and preserve readability of the cause chain.

## 12. Common Misconceptions

1. **"Every exception from `Constructor.newInstance` is inside `InvocationTargetException`."** False. Parameter, access, abstract type, and class initialization errors have their own reporting paths.
2. **"`InvocationTargetException` is the root error of the constructor."** False. It is a Reflection wrapper; use `getCause()` to see the root error.
3. **"If a constructor throws an unchecked exception, Reflection throws that exception directly."** False for `Constructor.newInstance`: errors inside the constructor body are normally wrapped whether checked or unchecked.
4. **"`IOException` in `getExceptionTypes()` means the constructor is guaranteed to fail."** False. Those are merely the types declared in `throws`.
5. **"Wrong arguments are also wrapped as constructor errors."** False. Wrong argument types/count can cause `IllegalArgumentException` from the Reflection layer before the constructor runs.
6. **"`NoSuchMethodException` and `InvocationTargetException` are the same."** False. One error is **metadata not found**, while the other is **the constructor was invoked and threw an error**.
7. **"`getDeclaredConstructor` can always invoke private constructors."** False. Metadata does not automatically bypass Java/JPMS access checks.
8. **"If a static block throws an exception, that error is inside `InvocationTargetException`."** Not by default. Class initialization failure happens before the constructor, typically yielding `ExceptionInInitializerError` or an error per JVM rules.
9. **"`Class.newInstance()` and `Constructor.newInstance()` handle checked exceptions identically."** False. `Class.newInstance()` is a deprecated API with different exception-propagation behavior.
10. **"Catching the error and returning `null` is good enough."** Easily loses the root cause and hides critical errors. Preserve type/cause or provide clear API errors.

## 13. Self-Check Questions

**Question 1.** Constructor `public Service(String x)` throws `IllegalStateException("bad")` in its body. Which outermost exception does a caller invoking via `Constructor.newInstance("x")` see?

**Answer:** `InvocationTargetException`. `getCause()` gives `IllegalStateException` containing message `bad`.

**Question 2.** `Service.class.getConstructor(int.class)` cannot find a matching constructor. Which error occurs?

**Answer:** `NoSuchMethodException` at lookup. No constructor was invoked; there is no `InvocationTargetException`.

**Question 3.** `Constructor<Service>` takes `String`, yet the caller passes `Integer`. Does it necessarily enter the constructor before throwing an error?

**Answer:** No. Reflection detects incompatible arguments and can throw `IllegalArgumentException` before calling the constructor.

**Question 4.** A constructor declares `throws IOException`, receives valid data, and completes. Does Reflection create an `InvocationTargetException` just because `throws` is declared?

**Answer:** No. When the constructor runs successfully, `newInstance` returns the instance. `InvocationTargetException` occurs only when the constructor actually throws an error.

**Question 5.** A static initializer fails before the constructor runs. Is `InvocationTargetException` guaranteed to be the outermost layer?

**Answer:** No. If a static initializer throws an exception not of type `Error`, the JVM typically emits `ExceptionInInitializerError`; class initialization differs from executing the constructor body.

**Question 6.** When catching `InvocationTargetException`, how do you log the real root error while keeping the cause chain?

**Answer:** Read `getCause()`, log the full Throwable/stack trace, and when re-wrapping, pass the cause into the new exception's constructor. Do not merely log `e.getMessage()` and discard the cause.

## Official References

- Java SE API — `java.lang.reflect.Constructor.newInstance(Object...)`: exception contract for `InstantiationException`, `IllegalAccessException`, `IllegalArgumentException`, `InvocationTargetException`, `ExceptionInInitializerError`.
- Java SE API — `java.lang.reflect.InvocationTargetException`: `getCause()`, `getTargetException()`.
- Java SE API — `java.lang.reflect.Constructor.getExceptionTypes()`, `getGenericExceptionTypes()`, `getDeclaringClass()`.
- Java SE API — `java.lang.Class.getConstructor`, `getDeclaredConstructor`, and `Class.newInstance()` (deprecated).
- Java Language Specification — §12.4 *Initialization of Classes and Interfaces*, §12.5 *Creation of New Class Instances*, §11 *Exceptions*.
- Java Virtual Machine Specification — §5.5 *Initialization*, class initialization failure rules.

**Key takeaway:** `Constructor.newInstance` wraps **errors thrown by the executing constructor** in `InvocationTargetException`; read `getCause()` to see the root cause. Constructor lookup, argument checking, access, abstract class, and class initialization errors are **separate cases** that must be diagnosed by their actual exception rather than lumped together as constructor errors.
