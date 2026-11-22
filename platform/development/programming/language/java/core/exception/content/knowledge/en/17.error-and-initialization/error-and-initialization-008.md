# NoClassDefFoundError on Subsequent Use After a Failed Initialization

> **Java Core – Exception** · Group: **Errors and Initialization** · Java **17+**. This lesson focuses on a phenomenon that is very easy to misdiagnose: the class **was found by the JVM**, but static initialization failed; on the first use you may see `ExceptionInInitializerError` (or a root `Error`), whereas subsequent active uses of the **same class in the same class-loading mechanism** receive `NoClassDefFoundError`.

## 1. Common Phenomenon

A running program produces a stack trace such as:

~~~text
java.lang.ExceptionInInitializerError
    ...
Caused by: java.lang.IllegalStateException: invalid configuration
    ...
~~~

Later, when calling that same class again:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class com.example.Settings
    ...
~~~

A reader might immediately think "the `Settings.class` file has disappeared from the classpath". **That is not the right conclusion in every case.** Another very important cause is: the JVM found the class, but **class initialization previously completed abnormally**; the JVM marks that class as being in an *erroneous state*.

When code continues to perform an operation that requires the class to be initialized, the JVM **does not re-run the static initializer as if nothing had happened**. In the erroneous state, a subsequent use can lead to `NoClassDefFoundError`, indicating that this class **cannot be initialized successfully** in that context.

### Three Concepts That Must Be Separated

1. **Class loading:** finding and creating the runtime representation of the class from the class file/source provided by a class loader.
2. **Linking:** verification, preparation, and resolution according to JVM rules.
3. **Initialization:** executing the class's static variable initializers and `static { ... }` blocks, after satisfying the rules concerning its superclass.

`NoClassDefFoundError` can arise from several kinds of failures in class-related phases. **One specific case** covered in this lesson is when a class **has been loaded/linked enough to enter initialization**, initialization fails, and subsequent active uses fail.

**Key takeaway:** Do not look only at the exception at the end of the chain. Find the **first error that occurred during initialization**.

## 2. Related Exception/Error Hierarchy

~~~text
java.lang.Throwable
├── java.lang.Error
│   └── java.lang.LinkageError
│       ├── java.lang.ExceptionInInitializerError
│       └── java.lang.NoClassDefFoundError
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.lang.IllegalStateException
~~~

Distinctions to make:

| Type | Group | Role in this scenario |
| --- | --- | --- |
| `IllegalStateException` | Unchecked `RuntimeException` | Illustrative root failure, thrown when static initialization is invalid |
| `ExceptionInInitializerError` | Unchecked `Error`, under `LinkageError` | Can be used by the JVM to wrap a **non-Error** exception that caused class initialization to fail |
| `NoClassDefFoundError` | Unchecked `Error`, under `LinkageError` | Can report that the class cannot be made ready for a subsequent use due to an erroneous initialization state; also has other causes such as a missing class definition |
| `ClassNotFoundException` | **Checked** `Exception` | A class-loading API by name, such as `Class.forName`, could not find the requested class definition |

`ExceptionInInitializerError` is **not** a subclass of `RuntimeException`. If you only use `catch (RuntimeException)`, you **cannot catch** this Error. Likewise, `catch (Exception)` does not catch the Error branches above.

**Do not turn this table into advice to catch every Error.** In normal applications, an initialization failure is a serious problem regarding the class's ability to function; the fix is usually to correct the configuration or code, not to swallow the Error and continue.

## 3. Why Do the First Use and Subsequent Uses Throw Two Different Types?

Consider:

~~~java
class BrokenSettings {
    static final String NAME = "app";
    static int VALUE = initialize();

    private static int initialize() {
        throw new IllegalStateException("configuration missing");
    }
}
~~~

This is a valid Java declaration for illustration, though by itself it does not have `main`. When an **active use** requires `BrokenSettings` to be initialized, the JVM executes the initialization code for the static field `VALUE` by calling `initialize()`.

High-level sequence:

1. A first thread performs an operation that requires the class to be initialized.
2. The JVM checks the class's initialization state and dependency constraints.
3. The JVM begins executing the static initializer (and appropriate superclass initialization if needed).
4. `initialize()` throws `IllegalStateException`.
5. Because the root Throwable is **not an `Error`**, the JVM's initialization algorithm attempts to create an `ExceptionInInitializerError` with that cause (per JLS 12.4.2).
6. The class is marked as **erroneous**, and the use that triggered initialization completes abnormally.
7. A subsequent active use of the erroneous class encounters `NoClassDefFoundError` instead of re-running the initializer.
8. Other calls in the same class-loading context continue to fail until the class-loading context changes / the application is restarted with an appropriate fix; simply calling the method again does not return the erroneous state to normal.

**Important:** The rule for using `ExceptionInInitializerError` in step 5 does not apply in the same way if the Throwable thrown by initialization is already a subclass of `Error`. In that case, the `Error` may be propagated directly on the first use, yet the class is still marked erroneous if initialization failed.

### 3.1. State Diagram

~~~text
Uninitialized class
      |
      | first active use
      v
Initializing (initialization in progress)
      |
      +-- succeeds --> Initialized --> subsequent active uses proceed normally
      |
      +-- throws Throwable
              |
              +-- not an Error --> JVM wraps in ExceptionInInitializerError
              |
              +-- is an Error ---> may propagate the original Error
              |
              v
       Erroneous class
              |
              | subsequent active use
              v
       NoClassDefFoundError
~~~

This is a **simplified model** focusing on initializer failure; the actual JVM algorithm also handles synchronization locks, recursive initialization, superclasses/superinterfaces, error reporting order, and many other details.

### 3.2. Why Doesn't the JVM Immediately Retry Initializing the Class?

Class initialization sets up shared state and can produce **side effects**: registering services, creating singletons, connecting to resources, writing logs, mutating data structures, or loading native libraries. If an initializer runs partway through and then fails, the JVM has no general mechanism to guarantee rolling back all those side effects.

Remembering that initialization has failed prevents the assumption that "calling it again will make the class recover on its own". According to [JLS §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2), a class is marked erroneous when initialization fails, and subsequent initialization requests are not performed as a normal fresh initialization.

This is why you **should not place failure-prone environmental operations that may need retries inside a static initializer** if the application expects runtime recovery.

## 4. Complete Java 17 Program: Observing the First Use and Subsequent Uses

Save the file as **`FailedInitializationDemo.java`**, keeping the public class name unchanged.

~~~java
public class FailedInitializationDemo {
    static class Broken {
        static final String LABEL = "constant";
        static int VALUE = initialize();

        private static int initialize() {
            System.out.println("broken-initializer");
            throw new IllegalStateException("invalid configuration");
        }

        static void ping() {
            System.out.println("broken-ping");
        }
    }

    static class BrokenByError {
        static int VALUE = initialize();

        private static int initialize() {
            System.out.println("error-initializer");
            throw new AssertionError("broken invariant");
        }
    }

    static class Healthy {
        static int VALUE = initialize();

        private static int initialize() {
            System.out.println("healthy-initializer");
            return 7;
        }
    }

    private static void attempt(String label, Runnable work) {
        System.out.println("== " + label + " ==");
        try {
            work.run();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("type=ExceptionInInitializerError");
            Throwable cause = ex.getCause();
            System.out.println("cause=" + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        } catch (NoClassDefFoundError ex) {
            System.out.println("type=NoClassDefFoundError");
        } catch (AssertionError ex) {
            System.out.println("type=AssertionError: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== non-initializing references ==");
        System.out.println("constant=" + Broken.LABEL);
        System.out.println("class-literal=" + Broken.class.getSimpleName());

        attempt("first broken use",
                () -> System.out.println("value=" + Broken.VALUE));
        attempt("second broken use", () -> Broken.ping());
        attempt("reflective broken use", () -> {
            try {
                Class.forName("FailedInitializationDemo$Broken", true,
                        FailedInitializationDemo.class.getClassLoader());
            } catch (ClassNotFoundException ex) {
                throw new AssertionError(ex);
            }
        });

        attempt("first Error use",
                () -> System.out.println("value=" + BrokenByError.VALUE));
        attempt("second Error use",
                () -> System.out.println("value=" + BrokenByError.VALUE));

        attempt("healthy first use",
                () -> System.out.println("value=" + Healthy.VALUE));
        attempt("healthy second use",
                () -> System.out.println("value=" + Healthy.VALUE));
    }
}
~~~

### 4.1. How to Compile and Run

Use JDK 17 or a newer version:

~~~bash
javac --release 17 -encoding UTF-8 FailedInitializationDemo.java
java FailedInitializationDemo
~~~

**Exact stdout verified by compiling with `javac --release 17` and running the program:**

~~~text
== non-initializing references ==
constant=constant
class-literal=Broken
== first broken use ==
broken-initializer
type=ExceptionInInitializerError
cause=IllegalStateException: invalid configuration
== second broken use ==
type=NoClassDefFoundError
== reflective broken use ==
type=NoClassDefFoundError
== first Error use ==
error-initializer
type=AssertionError: broken invariant
== second Error use ==
type=NoClassDefFoundError
== healthy first use ==
healthy-initializer
value=7
== healthy second use ==
value=7
~~~

The program uses only Java SE and intentionally does not print the default message of `NoClassDefFoundError`, because the JVM-provided message can differ across versions and implementations. The branches are caught **only in this teaching program** so that the remaining cases can still be demonstrated.

### 4.2. Why Didn't the First Two Lines Run Broken's Initializer?

~~~java
System.out.println("constant=" + Broken.LABEL);
System.out.println("class-literal=" + Broken.class.getSimpleName());
~~~

`Broken.LABEL` is a **compile-time constant**: a `static final String` whose initializer is the constant expression `"constant"`. Using this constant value from source can be inlined by the compiler and **does not trigger initialization of class Broken**.

`Broken.class` obtains the `Class<?>` object representing the class; merely obtaining the class literal and calling `getSimpleName()` in this example **does not trigger Broken's static initializer**.

Therefore, stdout does not yet contain `broken-initializer` on the first two lines. It only appears when reading the field `Broken.VALUE` — a static field that is not a constant variable according to the JLS.

### 4.3. First Time: IllegalStateException Becomes ExceptionInInitializerError

The call:

~~~java
System.out.println("value=" + Broken.VALUE);
~~~

requires initializing Broken. The static field `VALUE` calls `initialize()`, prints `broken-initializer`, and then throws `IllegalStateException("invalid configuration")`.

Because the original exception is a RuntimeException (not an Error), the initialization procedure per the JLS creates an `ExceptionInInitializerError`. The handler in the example reads `getCause()` and sees:

~~~text
type=ExceptionInInitializerError
cause=IllegalStateException: invalid configuration
~~~

**Focus on the root cause:** Fix the configuration or logic that caused the initializer to throw `IllegalStateException`. If you only search for the class file because you saw `NoClassDefFoundError` in a later log, it is very easy to go down the wrong path.

### 4.4. Second Time: NoClassDefFoundError Instead of Re-running the Initializer

After the first attempt, Broken is already in the erroneous state. The call:

~~~java
Broken.ping();
~~~

is an active use of the class. Result:

~~~text
== second broken use ==
type=NoClassDefFoundError
~~~

The line `broken-ping` **does not appear**, because the method body is never executed. The JVM must ensure the class is initialized before processing this invocation; the check encounters a class that is already erroneous.

Note: if you inspect the stack trace of NoClassDefFoundError, the remaining information may point to the earlier initialization failure. **Do not rely on the exact cause/message structure of NCDFE across all JVMs**; the first log entry and the cause of the original EIIE remain the most important diagnostic evidence.

### 4.5. Class.forName(..., true, loader) Also Does Not "Retry" the Initializer

The reflective part:

~~~java
Class.forName("FailedInitializationDemo$Broken", true,
        FailedInitializationDemo.class.getClassLoader());
~~~

passes `initialize = true`, requesting initialization when needed. Because Broken is already erroneous, the failure is:

~~~text
== reflective broken use ==
type=NoClassDefFoundError
~~~

Calling `Class.forName` does not reset the state. Calling again via reflection is not an alternative path to recover a broken class.

### 4.6. What If the Initializer Throws a Root Error?

Class `BrokenByError` throws `AssertionError("broken invariant")` from its initializer. It is a subclass of Error. According to the initialization algorithm, in this situation the Error can **be propagated directly** when the class fails the first time:

~~~text
== first Error use ==
error-initializer
type=AssertionError: broken invariant
~~~

Second time:

~~~text
== second Error use ==
type=NoClassDefFoundError
~~~

Therefore, the statement "the first time is **always** ExceptionInInitializerError" is **false**. A more accurate rule: when initialization completes abnormally, a Throwable **that is not an Error** is wrapped by the JVM in ExceptionInInitializerError per the JLS; if it is already an Error, the error can propagate directly.

### 4.7. Successful Initialization Runs Only Once

Class Healthy has the field `VALUE = initialize()`; the method prints `healthy-initializer` and returns 7.

First access:

~~~text
== healthy first use ==
healthy-initializer
value=7
~~~

Subsequent access:

~~~text
== healthy second use ==
value=7
~~~

This is the normal case: the initializer completes successfully, the class is in the initialized state, and it does not need to run again on every active use.

## 5. Which Operations Trigger Class Initialization?

According to [JLS §12.4.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1), initialization is required before certain **active use** operations. For ordinary classes, pay attention to:

- Creating an instance with `new SomeClass()`.
- Invoking a **static method** actually declared by the class.
- Assigning a value to a **static field** declared by the class.
- Reading a **non-constant static field** declared by the class.
- Certain reflection operations that require initialization, including `Class.forName(name)` and `Class.forName(name, true, loader)` when finding a matching class.
- Initializing a subclass may require initializing its superclass and certain superinterfaces according to language rules before running the subclass's initializer.

Conversely, many operations that reference a class **do not by themselves trigger initialization**:

| Expression/Operation | Forces init of the example class? | Reason |
| --- | --- | --- |
| `Broken.class` | Not solely from the class literal | Obtains Class metadata |
| `Broken.LABEL` with a compile-time constant | Not solely from reading the constant | Constant variable can be inlined |
| `Broken.VALUE` | Yes | Reads a static field that is not a compile-time constant |
| `Broken.ping()` | Yes | Invokestatic active use |
| `new Broken()` | Yes | Instance creation requires an initialized class |
| `Class.forName("...Broken", false, loader)` | Does not request initialization due to false flag | Only loads/links per the API; other operations must not be arbitrarily inferred |
| `Class.forName("...Broken", true, loader)` | Yes, requests init when needed | True flag requests initialization |
| `obj instanceof Broken` | Not considered an init trigger solely from the type check | Runtime type check does not necessarily run the static initializer |

This table is based on simple cases and language rules. Operations that can cause **loading/linking** do not necessarily mean **initialization**. Furthermore, in a real program, the class may already have been initialized earlier by another operation.

### 5.1. Constant Variable Is Not the Same as Every static final Field

~~~java
class Constants {
    static final int LIMIT = 10;
    static final String NAME = "demo";
    static final Integer BOXED = 10;
    static final int COMPUTED = Integer.parseInt("10");
}
~~~

This is a valid illustrative Java class. The first two fields are constant variables under JLS conditions: primitive or String `final` initialized with a constant expression.

`BOXED` is not a constant variable because `Integer` is a reference wrapper type; `COMPUTED` uses a method call, not a constant expression. Reading `Constants.BOXED` or `Constants.COMPUTED` can trigger initialization if the class has not yet been initialized.

When troubleshooting "why does accessing field A not run the static block while field B does?", this distinction matters more than the fact that both have the `static final` keywords.

## 6. Real-World Causes of Static Initialization Failure

It is not just `throw new IllegalStateException(...)` in a custom method. Failures can originate from many places:

1. **Static field initializer** runs code that reads invalid configuration.
2. **`static { ... }` block** calls a method and that method throws an unchecked exception.
3. **Static dependency** or superclass that must be initialized first fails.
4. **Loading a driver/native library** via static code fails.
5. **Static singleton** uses a missing environment value and dereferences null.
6. **Static data structure** is constructed with invalid arguments.
7. **Initialization code with side effects** partially executed before throwing an Error/RuntimeException.
8. **Hard-to-recover runtime errors**, such as a resource-related Error, can occur during initialization.

Example:

~~~java
class Config {
    static final int PORT = Integer.parseInt(
            System.getProperty("demo.port"));
}
~~~

This is an illustrative class. If the property is not provided, `System.getProperty("demo.port")` returns null; `Integer.parseInt(null)` throws `NumberFormatException` (a subclass of IllegalArgumentException) during static initialization. When an active use requests initialization for the first time, the JVM may report `ExceptionInInitializerError`; next time, the erroneous class may produce `NoClassDefFoundError`.

The important point is not always NumberFormatException — depending on the original code, it could be an NPE, IllegalArgumentException, or another Error. Read the **root cause** rather than guessing the cause from NCDFE alone.

## 7. In What Order Does Static Initialization Run?

For a class, **static field initializers** and **static initializer blocks** are executed in **textual order** during initialization, with additional JVM rules regarding superclasses/superinterfaces.

Example:

~~~java
class Order {
    static int a = first();

    static {
        System.out.println("static-block");
    }

    static int b = second();

    private static int first() {
        System.out.println("first");
        return 1;
    }

    private static int second() {
        System.out.println("second");
        return 2;
    }
}
~~~

This is a valid illustrative class. If an active use causes `Order` to be initialized successfully, the code in the class prints:

~~~text
first
static-block
second
~~~

If `first()` throws an exception, the subsequent steps **are not executed** in that initialization attempt. There is no general mechanism that automatically undoes side effects that `first()` may have performed before throwing the error.

An important consequence to note: if a static initializer already wrote to a file or registered a listener and then threw an exception, state outside the JVM class may have changed. "Retrying init" by changing the calling logic does not consistently resolve those side effects.

## 8. Do Not Confuse With ClassNotFoundException or a Truly Missing Class File

All three cases can involve a class name, but they **differ in cause and origin path**.

### 8.1. ClassNotFoundException

Example:

~~~java
try {
    Class.forName("example.DoesNotExist");
} catch (ClassNotFoundException ex) {
    System.out.println("Class not found by lookup");
}
~~~

This is an illustrative snippet placed in an appropriate method. `Class.forName(String)` can throw checked `ClassNotFoundException` when the class loader **cannot find the definition with the requested name**.

### 8.2. NoClassDefFoundError Due to a Missing Definition During Linking/Loading

A compiled class may reference another class that was present at build time but **is no longer present on the runtime classpath/module path**. When the JVM needs to resolve this reference, it may throw `NoClassDefFoundError`.

This is a **different** cause branch from "the class was found, but previous initialization failed".

### 8.3. NoClassDefFoundError Due to an Erroneous Class

In this lesson, `Broken.class` existed, the runtime loaded the class, and the initializer even **printed `broken-initializer`** on the first attempt. Therefore, the second NoClassDefFoundError cannot be explained simply as "missing class bytecode".

### 8.4. Quick Comparison Table

| Symptom | Cause group to check |
| --- | --- |
| `ClassNotFoundException` on Class.forName by name | Class loader could not find the requested definition |
| `NoClassDefFoundError` with missing class definition details | Classpath/module/dependency, class name, and linkage error |
| `ExceptionInInitializerError` appeared earlier | Static initialization failed due to a non-Error Throwable |
| `AssertionError`/Error from initializer appeared on first use | Static initialization can also fail **without going through EIIE** |
| `NoClassDefFoundError: Could not initialize class ...` on a later call | Suspect the class was marked erroneous; look for the first failure log |
| Error disappears when run in a new class loader / new process | May match initialization state tied to the class's identity in the old loader; still must fix the root cause |

**Do not rely absolutely on the string `Could not initialize class`.** LinkageError messages are not meant to be a stable parseable format across all JVMs. Inspect the stack trace, the first exception, the runtime classpath, and the entire cause chain.

## 9. Class Loaders and the True Identity of a Class

In the JVM, the concept of "same class" is tied to **binary name and defining class loader**. Two different loaders can define two classes with the same name but with different identities, if the loading/delegation mechanism allows it.

This explains why:

- A class that is already erroneous in **one class loader** cannot be treated as if it can be reset by calling `new` or `Class.forName(..., true, sameLoader)`.
- Another class with the same name loaded/defined in **a different loader** can have its own initialization state, if it is actually defined anew in that loader.
- Creating a new class loader **does not guarantee** a new definition if the loader still delegates to the parent loader that owns the old class.
- In normal applications, the practical way to recover is usually to **fix the root cause** and then **restart the application/process or perform a proper reload mechanism** supported by the platform.

You should not turn "switch class loaders to re-run the initializer" into a default workaround. Plugin reload, app server redeploy, or hot-reload mechanisms can additionally involve class loader leaks, static references, and dependency structures.

## 10. What Happens When Multiple Threads Touch a Class Simultaneously?

Class initialization is coordinated by the JVM with a synchronization mechanism so that two independent threads cannot simultaneously run the full initializer of the **same class identity**.

Scenario:

1. Thread A begins initializing the class.
2. Thread B also needs an active use of the class while A is initializing it.
3. B may have to wait for the initialization performed by A.
4. If A initializes successfully, B can proceed with the initialized class.
5. If A fails to initialize, the class is marked erroneous; B and subsequent active uses may receive `NoClassDefFoundError` according to the state algorithm.

This explains a pattern in multithreaded system logs: **only one thread sees the original initialization Error**, while other threads afterward see NoClassDefFoundError, making the problem look like a sudden missing class.

**Do not write code that depends on which thread will see EIIE or NCDFE** in an initialization race. That is a scheduling detail; when investigating, correlate logs by timestamp and class object.

### Recursive Initialization

If a thread currently initializing a class references that same class in a way Java allows, the JVM has specific rules for **recursive initialization by the same thread**; it does not simply run the initializer infinitely. However, static fields may still be at their default values or not yet assigned, creating subtle "partial initialization" bugs.

This example is outside the main path of the lesson, but reinforces the principle of **avoiding complex static initializers with circular dependencies**.

## 11. How Can a Broken Superclass or Static Dependency Propagate?

When the JVM initializes a class, it must ensure the corresponding superclass is initialized according to the rules. If a superclass has a failing static initializer, initialization of the subclass cannot proceed normally either.

Illustrative example:

~~~java
class Parent {
    static int value = load();

    static int load() {
        throw new IllegalStateException("parent init failed");
    }
}

class Child extends Parent {
    static int other = 10;
}
~~~

These are two valid Java classes without main. When the first active use requires initializing Child, the JVM must initialize Parent first. If Parent throws an error, Child cannot enter the normal initialized state along this path either.

**Check the actual root class in the stack trace:** A NoClassDefFoundError appearing at the call site of Child may originate from Parent or another static dependency. Do not fix Child simply because that is the class name on the final business call line.

### Similar With Static Holder/Singleton

Pattern:

~~~java
class ServiceHolder {
    static final Service INSTANCE = new Service(readConfig());
}
~~~

This is an illustrative snippet requiring an appropriate Service class and readConfig method. If the Service constructor or readConfig fails without being handled properly, initialization of ServiceHolder also fails. Any caller using `ServiceHolder.INSTANCE` later may see NCDFE even if the caller code knows nothing about readConfig.

A singleton holder for **lazy initialization** still uses class initialization; "lazy" only describes the timing of initialization, not automatic retry support when initialization fails.

## 12. Check the Root Error Before Concluding a Missing Dependency

Investigation checklist when encountering NoClassDefFoundError:

1. **Inspect the full exception**, not just the first line: message, stack trace, cause chain.
2. **Search earlier timestamps in the logs** for `ExceptionInInitializerError`, `AssertionError`, or other `Error`s that occurred when the class was first actively used.
3. **Identify the erroneous class**: does it have static blocks/field initializers? Is there a failing superclass or static dependency?
4. **Check the root cause**: IllegalStateException, NumberFormatException, NPE, initializer accessing configuration, driver, native library, or input data.
5. If there is no sign of broken initialization, **check classpath/module path**, packaging, dependency versions, and loader isolation.
6. **Note the class loader** if in a complex plugin/container environment; two classes with the same name in different loaders do not necessarily share the same identity.
7. **Reproduce from a clean process** to capture the **first** failure, because a long-running process may only have NCDFE left in its logs.
8. **Fix the cause in the initializer**, not just by catching NCDFE at the caller.
9. Check for side effects that occurred **before the initialization failure**.
10. **Retest a fresh start**, covering both missing-configuration and valid-configuration cases.

If the log only shows:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class app.Config
~~~

look for an **earlier** stack trace instead of asserting that the jar containing `app.Config` was deleted. Conversely, if the package/class truly was not deployed, re-running the static initializer will not solve the classpath issue.

## 13. Storing and Presenting Errors Without Losing the Root Cause

When debugging, the exception object matters more than a short message. Illustrative example at a diagnostic layer:

~~~java
try {
    useComponent();
} catch (ExceptionInInitializerError ex) {
    logger.error("Component initialization failed", ex);
    throw ex;
}
~~~

This is an illustrative snippet requiring `useComponent()` and an appropriate logger. It preserves the Error after logging rather than fabricating a fake successful result. In an environment without a logging framework, `ex.printStackTrace()` can be used for local diagnosis.

Regarding `ExceptionInInitializerError`:

- `getCause()` usually provides the Throwable that caused the initializer to fail.
- `getException()` is a historical API of this class retained for compatibility; use the general cause chain when possible.
- If a developer manually constructs an EIIE or uses a constructor without a cause, do not assume `getCause()` is always non-null.
- Stack traces may show the first initialization failure, followed by many NoClassDefFoundErrors. **Keep logs in chronological order** to correlate events accurately.

Regarding `NoClassDefFoundError`, do not rely on `getCause()` definitely containing a copy of the first Error: generating detailed messages/causes can be implementation-dependent. The first error in the log is the reliable source for investigation.

## 14. Avoid Putting Connections and Failure-Prone Configuration in Static Initializers

An anti-pattern:

~~~java
class DatabaseGateway {
    static final Connection CONNECTION = connect();

    private static Connection connect() {
        // If connecting fails with an unchecked exception,
        // the class can fall into the erroneous state.
        throw new IllegalStateException("database unavailable");
    }
}
~~~

This is illustrative code requiring `Connection` from java.sql or a corresponding type. The point is to show that **creating resources that can fail due to the environment** during static initialization leaves the class with no natural retry path.

Additionally, a long-lived shared static database connection can violate thread-safety policies, connection lifecycles, and pooling. It is not a good default choice for production.

### 14.1. Solution: Explicit Initialization in an Appropriate Lifecycle

Instead of letting static class initialization carry all environmental failures, move resource creation into a component with a clear lifecycle:

~~~java
import java.io.IOException;

final class ConfigurableService {
    private String config;

    void initialize(String path) throws IOException {
        this.config = readConfig(path);
    }

    private String readConfig(String path) throws IOException {
        if (path == null || path.isBlank()) {
            throw new IOException("configuration path missing");
        }
        return path;
    }

    String currentConfig() {
        if (config == null) {
            throw new IllegalStateException("service not initialized");
        }
        return config;
    }
}
~~~

The class above is a valid Java illustration that can be placed in an appropriate file. It makes configuration failures occur in a **method with a checked IOException contract**, without making the class erroneous just from a single use.

Of course, the service object still needs proper synchronization/lifecycle design, preventing access before initialization, and handling partial initialization states. However, it allows the application to **actively decide** whether to retry, fix configuration, alert operations, or halt startup.

### 14.2. Controlled Lazy Initialization

If you need to defer connecting or loading configuration until first use:

- You can use a method/factory with an explicit result or checked exception.
- Define policies for caching success/failure, retry intervals, and concurrency.
- Avoid permanently caching a failure if the business requirement calls for recovery; conversely, do not infinitely retry operations that may cause side effects.
- If you still use a static holder, remember that **an initializer failure still makes the holder class erroneous**.
- Use your framework's dependency injection/lifecycle hooks if the project has them, but check how the framework reports and caches failures.

**Key point:** move failure-prone environmental errors out of class initialization when a valid recovery path is needed; this avoids the "EIIE the first time, NCDFE thereafter" cycle.

## 15. Can You Catch Error to Recover a Failed Class?

A caller **could** write:

~~~java
try {
    Broken.VALUE = 5;
} catch (ExceptionInInitializerError ex) {
    System.err.println("initialization failed");
}
~~~

This is an illustration requiring a Broken class with an appropriate static field; in the main example, you should not assign to the VALUE field as an attempt to fix the class.

Catching an Error in the caller **does not reset the class state**, does not re-run static initialization, and does not prove that side effects were rolled back. Subsequent active uses can still encounter NCDFE.

**Why shouldn't you catch Error broadly?**

- Errors such as LinkageError, OutOfMemoryError, or initialization errors can leave the application in an unreliable operating state.
- Swallowing an Error hides the root failure and lets the system continue in a broken state.
- Some errors have causes that cannot be recovered at the call site.

You can catch specific Errors in **tests/demos or top-level diagnostic boundaries** to log and terminate/transition state, but do not use `catch (Error) { }` as a default policy to keep running.

## 16. When Can NoClassDefFoundError Occur on the Very First Time?

Avoid over-interpreting one rule from this lesson. `NoClassDefFoundError` is not **only** "a sign of a class broken on a previous attempt". It is also a LinkageError tied to class loading/definition failure, or it can appear when a class needs to be used but is already in the erroneous state because another thread tried to initialize it earlier.

Examples:

- Class A references class B, but B's definition is missing in the runtime environment → NCDFE can appear **on the very first** use of that code path.
- Thread A runs class X's initializer and fails; thread B is the first thread in its own log to call X, but by then X is already erroneous → thread B may see NCDFE without ever seeing EIIE.
- A module/plugin already initialized the class before the request handler started → the first logged request may only see NCDFE.

Therefore, to determine the cause you must examine the **entire process/logs and loaders**, not just the error order within a single thread.

## 17. Common Misconceptions

1. **“NoClassDefFoundError always means a .class file is missing.”** False; the class may have been found, but initialization failed earlier.
2. **“If the code compiled, static initialization is guaranteed to succeed.”** False; initialization can throw exceptions at runtime.
3. **“The first static init failure is always NoClassDefFoundError.”** False; it can be ExceptionInInitializerError or a root Error.
4. **“The first failure is always ExceptionInInitializerError.”** False; a directly thrown Error is not required to be wrapped under the same rule.
5. **“ExceptionInInitializerError is a RuntimeException.”** False; it is an Error under the LinkageError branch.
6. **“NoClassDefFoundError is a checked exception.”** False; it is an unchecked Error.
7. **“Catching Exception will catch EIIE/NCDFE.”** False, because these classes belong to the Error branch.
8. **“Just calling the static method again will retry the initializer.”** False within the same erroneous state.
9. **“Class.forName(..., true, sameLoader) is a retry button for the static initializer.”** False.
10. **“Accessing any static final field definitely initializes the class.”** False for compile-time constant variables.
11. **“Taking Broken.class always runs the static block.”** False; a class literal by itself is not an active use that forces init.
12. **“Class loading and initialization are the same action.”** False; the phases have different rules.
13. **“A static initializer cannot have side effects before failing.”** False; part of the code may already have run.
14. **“The JVM automatically rolls back side effects when an initializer throws an error.”** There is no such general rollback mechanism.
15. **“An erroneous class will automatically work again once external configuration is fixed.”** Not just by fixing configuration; the class needs an appropriate loading/running context to have a fresh init opportunity.
16. **“A new class loader always redefines the class.”** Not if it still delegates to the loader that already defined that class.
17. **“Every thread using the class sees the same first Error type.”** False; other threads can receive NCDFE after init fails.
18. **“If a static initializer throws AssertionError, the next time will also be AssertionError.”** No; an erroneous class causes subsequent active uses to receive NCDFE.
19. **“The message of NoClassDefFoundError is always enough to find the root cause.”** False; you usually need the log of the first initialization.
20. **“Catching NCDFE, returning null, and continuing is safe.”** False; it can mask an uninitialized component state.
21. **“Superclass init failure does not affect the subclass.”** False; subclass initialization has corresponding dependencies.
22. **“A static singleton holder can always be retried if the constructor fails.”** False; the holder can also become erroneous.
23. **“Classpath errors and initialization errors can always be distinguished solely from the class name in the exception.”** False; you must look at the cause, timing, and runtime configuration.
24. **“The message ‘Could not initialize class’ is a stable parsing contract.”** Should not be relied upon; message text can vary across implementations.
25. **“Editing static initialization code in source while the process is running will automatically recover the broken class.”** No; the process/loader still uses the already loaded definition, unless there is a genuine specialized reload mechanism.

## 18. Self-Check Questions and Exercises

**Q1.** A class has a static field initialized by a method that throws `IllegalStateException`. What does the first active use usually receive?

*Answer:* If initialization fails due to a non-Error RuntimeException, the JVM wraps it according to the JLS algorithm into `ExceptionInInitializerError`.

**Q2.** What will the second active use of the already erroneous class receive?

*Answer:* `NoClassDefFoundError` instead of re-initializing normally.

**Q3.** A static initializer directly throws `AssertionError`. Must the first time go through EIIE?

*Answer:* No. An Error can be propagated directly; after the failure, the class becomes erroneous and subsequent uses can receive NCDFE.

**Q4.** Why didn't `Broken.LABEL` run the initializer in the main program?

*Answer:* LABEL is a compile-time constant variable, and that usage does not trigger class initialization.

**Q5.** Does `Broken.class.getSimpleName()` prove that the class has initialized successfully?

*Answer:* No. Class literal/metadata access does not force the static initializer to run the way reading a non-constant static field does.

**Q6.** Does `Class.forName(name, true, sameLoader)` re-initialize an erroneous class?

*Answer:* No; if the JVM has already marked the class erroneous, a subsequent active use receives NCDFE.

**Q7.** Distinguish ClassNotFoundException and NCDFE in the scenario of this lesson.

*Answer:* ClassNotFoundException is a checked exception usually thrown when a class-lookup-by-name API cannot find the definition; NCDFE is a LinkageError that can result from a missing definition at runtime or from a class whose initialization has failed.

**Q8.** Why shouldn't you put a database connection inside a static initializer if retries are needed?

*Answer:* A transient environmental error can make the class erroneous for all subsequent uses, rather than allowing the application to retry in a controlled manner.

**Q9.** When you only see NCDFE on the second request, what is the most important debugging step?

*Answer:* Find the first initialization failure across the entire process/logs, including EIIE or a root Error, and inspect the stack trace/cause.

**Q10.** Is the same binary class name defined by two different loaders always the same runtime class identity?

*Answer:* No. Identity is tied to the defining loader. However, a new class loader does not guarantee a new definition if it continues delegating to the parent loader.

**Q11.** Can thread B see only NCDFE even though it never saw the initial initialization failure?

*Answer:* Yes, if thread A already tried to init the class and failed, and the JVM marked the class erroneous before B could proceed with its active use.

**Q12.** Is catching Exception enough to cover both EIIE and NCDFE?

*Answer:* No. Both are Errors, not subclasses of Exception.

**Q13.** If an initializer mutates a shared registry and then throws an exception, does the JVM automatically roll back the registry?

*Answer:* There is no general rollback. You must design initializers and lifecycles to avoid or control partial side effects.

**Q14.** Can changing `static final int VALUE = 42;` to `static final int VALUE = Integer.parseInt("42");` change the timing of class initialization?

*Answer:* Yes. The first is a constant variable; the second has a method call and is not a compile-time constant expression.

**Q15.** Should you catch NoClassDefFoundError and try to reassign the static field to rescue the class?

*Answer:* No. An erroneous class cannot become initialized simply by assigning a field; you need to fix the root cause and manage lifecycle/class loading properly.

**Q16.** A Child class fails initialization because the Parent static initializer failed. Which class should you inspect first?

*Answer:* Inspect the stack trace and root cause; if Parent is where initialization failed first, address the error in Parent/the dependency first rather than only modifying where Child is used.

## 19. Checklist for Preventing Class Initialization Errors in Production

- **Minimize work in static initializers:** prefer pure constants and stable data structures.
- **Do not put operations requiring retries in static init** if the application requires runtime recovery.
- **Validate input configuration** in an explicit lifecycle rather than creating hidden, unpredictable singletons.
- **Document and monitor startup errors:** log the cause, stack trace, class/module/source, not just a short message.
- **Distinguish dependent class failure** from a missing runtime dependency.
- **Check the same class loader** when investigating erroneous state and reloadability.
- **Test from a clean process** to see the first exception, then test a second active use to confirm the NCDFE path.
- **Avoid non-idempotent side effects** in static initializers, or manage rollback at an appropriate place.
- **Do not catch Error and stay silent;** at a diagnostic boundary, report the incident and stop the component if it is unreliable.
- **Ensure the classpath/module path is correct** if evidence shows NoClassDefFoundError is due to an actually missing definition.
- **Test concurrency** when multiple threads may trigger init almost simultaneously; do not rely on an absolute order of Error notifications.
- **Test call paths that do not trigger init**, such as compile-time constants and metadata, to avoid drawing wrong conclusions when creating a reproduction case.

## 20. Official Java 17 Documentation

- [JLS Java SE 17 §12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): operations that trigger initialization and the compile-time constant exception.
- [JLS Java SE 17 §12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): initialization states, synchronization, Error wrapping, erroneous state, and initialization requests after failure.
- [JVMS Java SE 17 §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): initialization in the JVM.
- [Java SE 17 API — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): the Error class reporting an error in a static initializer and how to retrieve the original exception.
- [Java SE 17 API — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): a LinkageError class with multiple sources, not just initialization failures.
- [Java SE 17 API — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html): group of issues related to loading/linking/class compatibility.
- [Java SE 17 API — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html): checked exception of certain class lookup methods.
- [Java SE 17 API — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): the initialize true/false option when looking up a class.
- [JLS Java SE 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): conditions defining a constant variable.
- [JLS Java SE 17 Chapter 11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked hierarchy and Throwable handling.

**Final reminder:** A class can **exist on the classpath** yet be marked **erroneous** by the JVM after static initialization fails. **The first time** you usually see `ExceptionInInitializerError` when the cause is a RuntimeException, or the root Error when the initializer throws an Error; **subsequent active uses** see `NoClassDefFoundError`. Do not confuse this with a missing class file if there is an earlier initialization failure log. Fix the root error, avoid static initializers that depend on fragile environments, and do not assume calling the class again will recover it in the same class loader.
