# Class Initialization and Errors Occurring Before or Inside Constructors in Java Reflection

When creating an object via Reflection, many programmers see `Constructor.newInstance(...)` throw an error and conclude that *the constructor is broken*. That conclusion can be wrong: **the JVM must ensure the class has been initialized (class initialization) before actually running the constructor**. Errors can occur in a static field initializer, a static block, superclass initialization, access checks, parameter matching, an instance initializer, a superclass constructor, or the invoked constructor body itself.

This lesson focuses on distinguishing **class initialization (`<clinit>`)** from **object initialization (`<init>`)** and identifying at which stage an error occurs when using `Class`, `Constructor`, and `Constructor.newInstance(...)`. Examples are runnable with Java 17+.

## 1. Two Concepts Often Lumped Together as "Initialization"

### Class Initialization

*Class initialization* is the process where the JVM executes the static field initializers and static initializer blocks belonging to a class, in textual declaration order and according to the rules of the Java Language Specification. The JVM needs to initialize the relevant superclass before initializing a subclass, while also ensuring initialization of a class is coordinated across threads.

Example:

~~~java
class Service {
    static String config = loadConfig();

    static {
        System.out.println("Service static block");
    }

    private static String loadConfig() {
        System.out.println("Service static field");
        return "ready";
    }
}
~~~

This is **illustrative code**, without `main`. On the first initialization of `Service`, calling `loadConfig()` prints first, then the static block prints. Both actions belong to **class initialization**, not the constructor body. In bytecode, that work is organized by the JVM in the special class initialization method `<clinit>`.

**Do not equate three states:**

1. **Loading:** the JVM locates and defines the class structure.
2. **Linking:** verifies, prepares, and optionally resolves references.
3. **Initialization:** executes static initialization logic if it has not yet completed.

Obtaining a `Class<?>` object does not by itself prove that initialization has already happened.

### Object Initialization

When actually creating an instance of an ordinary class, the JVM allocates the object and executes the constructor chain per Java rules:

- The superclass constructor is invoked during instance creation before running the subclass constructor body.
- Each class's instance field initializers and instance initializer blocks execute at the appropriate point after calling the superclass constructor and before the corresponding constructor body.
- The constructor body can assign fields, validate parameters, call services, and throw exceptions.

A constructor appears in bytecode under the special name `<init>`. This **is not** `<clinit>`; a class can be initialized once and then create many instances via many constructor invocations.

## 2. Which Stage Does Reflection Trigger?

| Operation | Does it by itself force initialization of the target class? | Key point to remember |
| --- | --- | --- |
| `SomeClass.class` | No | Obtains the class literal; does not run static initializers merely from this operation |
| `SomeClass.class.getDeclaredConstructor(...)` | No | Only looks up constructor metadata/signature |
| `getDeclaredConstructors()`, `getConstructor(...)` | No | Discovers constructors; does not create an instance |
| `Class.forName("pkg.SomeClass")` | Yes, requests initialization by default | Static initializer errors can blow up **right at `forName`** |
| `Class.forName(name, false, loader)` | Does not request initialization of the target class | Useful when wanting to load/inspect metadata first |
| `constructor.newInstance(args...)` | Yes, if conditions allow reaching instance creation and class is not initialized yet | JVM must initialize the class before executing the constructor |
| `new SomeClass(...)` | Yes | Similar regarding class initialization requirement, though exception paths differ from Reflection |
| Accessing/calling a static member qualifying as active use | Possibly | Has exceptions for constant variables and `JLS 12.4.1` rules |

**Scope note:** "does not initialize the target class" in the table does not mean the API cannot trigger any loading/linking of related types. What is definitely useful in this lesson is that `getDeclaredConstructor` does not run the target class's static block the way `Constructor.newInstance` does by default.

Example of two different calls:

~~~java
Class<?> metadataOnly = Class.forName(
        "com.example.Service", false,
        Thread.currentThread().getContextClassLoader());

Class<?> initialized = Class.forName("com.example.Service");
~~~

This is **illustrative code**; it requires class `com.example.Service` to exist and be visible to the class loader. The first call does not request initializing the target class; the second call requests initialization. If the class has already been initialized earlier, the JVM does not repeat static initializers just because of a new call.

## 3. Order of Class Initialization and Constructors During Object Creation

Consider a subclass inheriting a parent class. When the classes have not yet been initialized and the constructor call succeeds, the observable order is as follows:

~~~text
Look up Constructor via getDeclaredConstructor()
    ↓ does not execute static initializer
Call Constructor.newInstance()
    ↓ check conditions, prepare invocation
Initialize required superclass
    ↓ static fields/static blocks of superclass
Initialize target class
    ↓ static fields/static blocks of target class
Create instance and execute constructor chain
    ↓ superclass constructor; instance initializers
Run target class constructor body
    ↓
newInstance() returns object
~~~

This diagram depicts the success path; an error at any relevant stage can cut short subsequent steps. The exact order of permission checks, argument checks, and certain errors occurring before class initialization also depends on specific API conditions, so do not use the diagram to assert the ordering of all input-validation errors.

### Complete Example 1: Metadata Does Not Initialize, `newInstance` Triggers Initialization

Create the file **`ConstructorInitOrderDemo.java`**:

~~~java
import java.lang.reflect.Constructor;

class ParentStage {
    static {
        System.out.println("ParentStage.<clinit>");
    }

    ParentStage() {
        System.out.println("ParentStage.<init>");
    }
}

class ChildStage extends ParentStage {
    static {
        System.out.println("ChildStage.<clinit>");
    }

    ChildStage() {
        System.out.println("ChildStage.<init>");
    }
}

public class ConstructorInitOrderDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        System.out.println("Metadata lookup start");

        Class<ChildStage> type = ChildStage.class;
        Constructor<ChildStage> ctor = type.getDeclaredConstructor();

        System.out.println("Constructor found");
        ChildStage created = ctor.newInstance();

        System.out.println("Instance created: "
                + (created != null));
    }
}
~~~

Run in the same directory:

~~~bash
javac --release 17 ConstructorInitOrderDemo.java
java ConstructorInitOrderDemo
~~~

**Stdout:**

~~~text
Metadata lookup start
Constructor found
ParentStage.<clinit>
ChildStage.<clinit>
ParentStage.<init>
ChildStage.<init>
Instance created: true
~~~

Explanation:

1. `ChildStage.class` and `getDeclaredConstructor()` allow retrieving metadata without yet running `ChildStage`'s static block.
2. `ctor.newInstance()` requires initializing `ChildStage`. `ParentStage` must be initialized first; the two `<clinit>` lines appear in superclass-then-subclass order.
3. When starting the constructor chain, `ParentStage()` runs before `ChildStage()`, so the two `<init>` lines appear after the static initializers.
4. `newInstance` completes and returns the object, so `Instance created: true` appears last.

In a program that creates many objects, a static block normally runs **only once per successful initialization of the corresponding class** in a runtime/class loader; the constructor runs **each time an instance is created**.

## 4. Errors **Before** the Constructor Body Starts: Static Initialization

If a static field initializer or static block throws an exception during class initialization, the target class's constructor body **has not run yet**. For errors belonging to ordinary non-`Error` exceptions, the JVM represents the initialization failure with `ExceptionInInitializerError`. The causing exception can be read via `getCause()`.

Example:

~~~java
class Broken {
    static final String VALUE = fail();

    private static String fail() {
        throw new IllegalStateException("cannot load configuration");
    }

    Broken() {
        System.out.println("Broken constructor entered");
    }
}
~~~

This snippet is illustrative only. If creating an instance of `Broken` for the first time and `fail()` throws `IllegalStateException`, the JVM never reaches the print statement inside the constructor.

### Complete Example 2: First `ExceptionInInitializerError`, Next `NoClassDefFoundError`

Create the file **`ConstructorStaticFailureDemo.java`**:

~~~java
import java.lang.reflect.Constructor;

class BrokenInitialization {
    static final String VALUE = fail();

    private static String fail() {
        System.out.println("BrokenInitialization.<clinit>");
        throw new IllegalStateException("static boom");
    }

    BrokenInitialization() {
        System.out.println("Constructor entered");
    }
}

public class ConstructorStaticFailureDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<BrokenInitialization> ctor =
                BrokenInitialization.class.getDeclaredConstructor();

        System.out.println("Broken constructor found");

        try {
            ctor.newInstance();
        } catch (ExceptionInInitializerError error) {
            System.out.println("First: "
                    + error.getClass().getSimpleName());
            System.out.println("Cause: "
                    + error.getCause().getClass().getSimpleName());
        }

        try {
            ctor.newInstance();
        } catch (NoClassDefFoundError error) {
            System.out.println("Second: "
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 ConstructorStaticFailureDemo.java
java ConstructorStaticFailureDemo
~~~

**Stdout:**

~~~text
Broken constructor found
BrokenInitialization.<clinit>
First: ExceptionInInitializerError
Cause: IllegalStateException
Second: NoClassDefFoundError
~~~

**Why are there two different errors?**

- The first line confirms that getting `Constructor` **does not trigger** static initialization.
- The first `newInstance` leads the JVM into initializing `BrokenInitialization`; `fail()` throws `IllegalStateException`. The JVM reports `ExceptionInInitializerError` at the class initialization boundary.
- The line `Constructor entered` **never appears**, because the class never completed initialization.
- A class whose initialization failed is marked in an **erroneous** state for that runtime. Subsequent active use of the same class typically encounters `NoClassDefFoundError` because the class cannot be simply re-initialized in the same class loader.

`NoClassDefFoundError` here **does not** mean bytecode or the `.class` file vanished. It can indicate the class fell into a failed-initialization state. To find the cause, trace logs/stack traces back to the initial `ExceptionInInitializerError`, rather than only checking classpath entries.

**Important exception to note:** if a static initializer directly throws an `Error` (for instance, an application-defined `Error` or VM error), the JVM may propagate that exact `Error` instead of wrapping it in `ExceptionInInitializerError`. Therefore, do not write class-initialization error-catching logic relying solely on one wrapper type in all situations.

## 5. Errors **Inside** the Constructor: `InvocationTargetException`

Unlike static initialization before entering the constructor, when code inside the constructor throws an exception, `Constructor.newInstance(...)` surfaces that error via `java.lang.reflect.InvocationTargetException`. The original exception is in:

~~~java
Throwable original = invocationTargetException.getCause();
~~~

This is an **illustrative snippet**. `InvocationTargetException` indicates the reflective call reached executable code, and a throwable emerged from the invoked code; it does not fully describe the deepest location of the error if the constructor calls further methods.

### Complete Example 3: Class Initializes Successfully Yet Constructor Throws an Exception

Create the file **`ConstructorBodyFailureDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

class FailsInConstructor {
    static {
        System.out.println("FailsInConstructor.<clinit>");
    }

    FailsInConstructor() {
        System.out.println("FailsInConstructor.<init>");
        throw new IllegalArgumentException("ctor boom");
    }
}

public class ConstructorBodyFailureDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<FailsInConstructor> ctor =
                FailsInConstructor.class.getDeclaredConstructor();

        try {
            ctor.newInstance();
        } catch (InvocationTargetException error) {
            System.out.println("Wrapper: "
                    + error.getClass().getSimpleName());
            System.out.println("Cause: "
                    + error.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 ConstructorBodyFailureDemo.java
java ConstructorBodyFailureDemo
~~~

**Stdout:**

~~~text
FailsInConstructor.<clinit>
FailsInConstructor.<init>
Wrapper: InvocationTargetException
Cause: IllegalArgumentException
~~~

Analysis: the static initializer ran successfully first. The `<init>` line confirms the constructor began. The constructor body itself threw `IllegalArgumentException`, so Reflection reports `InvocationTargetException` and keeps the original error as `cause`.

**A constructor throwing an exception does not automatically put the class in an erroneous state.** The class in the example initialized statically with success; subsequent constructor calls can be retried, even though the constructor continues throwing exceptions per its logic. This differs from the failed static initialization in the previous section.

### Errors in Instance Field Initializers or Superclass Constructors

"Inside the constructor" from `Constructor.newInstance`'s perspective includes code executed during object creation, **not only** lines directly inside the target class's constructor body:

- A superclass constructor throws an error before the subclass constructor body executes.
- An instance field initializer/instance initializer block of the target class throws an error.
- The constructor calls another method and that method throws an error.
- The constructor triggers for the first time a dependent class whose static initializer fails.

In cases where a throwable arises after the reflective constructor call has begun executing object-initialization code, `InvocationTargetException` may wrap a deeper throwable, including an `ExceptionInInitializerError` from **a dependent class initialized inside the constructor**. Therefore, **inspect the entire cause chain and stack trace**, not just the outermost wrapper to guess the location.

## 6. Table Distinguishing Errors by Timing

| Error | Typical stage | Meaning and how to handle |
| --- | --- | --- |
| `NoSuchMethodException` | Lookup `getDeclaredConstructor(...)` | No constructor with the exact parameter type list; invocation not reached |
| `IllegalAccessException` | Calling `Constructor.newInstance(...)` without permission | Constructor exists, yet caller lacks appropriate access permission |
| `InaccessibleObjectException` | Calling `setAccessible(true)` | Target module does not permit opening deep access under current conditions |
| `IllegalArgumentException` | Validating arguments during `newInstance(...)` | Argument count/types do not match signature or invalid operation |
| `InstantiationException` | Instantiating a non-instantiable type (e.g. abstract class) | Constructor metadata may exist, yet direct instantiation is impossible |
| `ExceptionInInitializerError` | Class initialization before constructor, when an ordinary exception occurs | Inspect the cause of the static initialization error; constructor has not started |
| `NoClassDefFoundError` | Using a class whose initialization failed or cannot be defined | Inspect cause/stack trace, especially logs from the first class initialization failure |
| `InvocationTargetException` | Throwable from code called while running the constructor | Inspect `getCause()` to find the actual error |
| `LinkageError` and certain other `Error`s | Loading/linking/initializing a class or executing | May propagate directly; analyze by error type and root cause |

**Do not confuse `NoSuchMethodException` with `NoClassDefFoundError`:** the first says constructor lookup found no requested signature; the second relates to a class failing to be defined/initialized/executed as required. Also do not merely catch `Exception` and assume all class initialization errors are caught, because `ExceptionInInitializerError` and `NoClassDefFoundError` both belong to the `Error` branch of `Throwable`.

Both `InvocationTargetException` and `ExceptionInInitializerError` can appear in the same cause chain in complex programs. Distinguish an error *initializing the class being instantiated* from an error *initializing a dependent class inside the constructor body*.

## 7. Role of `Class.forName`: Errors Can Happen Earlier Than You Think

If the code sequence is:

~~~java
Class<?> type = Class.forName("com.example.Broken");
Constructor<?> ctor = type.getDeclaredConstructor();
Object value = ctor.newInstance();
~~~

This is **illustrative code** with a hypothetical `com.example.Broken` class. `Class.forName(String)` requests class initialization by default, so the static initializer can fail **right on the first line**, before `getDeclaredConstructor` is called. If the goal is analyzing metadata before active use, use the overload:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "com.example.Broken", false, loader);

Constructor<?> ctor = type.getDeclaredConstructor();
// Only calling ctor.newInstance() requires the target class to initialize.
~~~

This snippet is also **illustrative code**, requiring a real class, valid Reflection permissions, and exception handling. `initialize=false` defers **initialization** rather than turning a broken class into one that can initialize successfully. Loading/linking or class loader checks can still encounter their own errors.

Do not use `Class.forName(name, false, loader)` as a security mechanism for untrusted code; it only changes the timing of class initialization rather than eliminating effects when the class is used later.

## 8. Constructor Reflection Can Also Fail Before Executing Application Code

### Signatures Must Match Strictly

~~~java
Constructor<?> ctor = Example.class
        .getDeclaredConstructor(String.class, int.class);
~~~

This snippet is valid only when `Example` declares a constructor with the exact parameter list `String, int`. Reflection **does not** use autoboxing or widening to find a constructor by "approximate signature":

- `int.class` differs from `Integer.class`.
- `String[].class` differs from `String.class`; varargs `String...` is represented as an array parameter `String[]`.
- Parameterized types like `List<String>` undergo type erasure at runtime and are normally looked up with `List.class`.
- Constructors are not inherited, so you cannot look up a superclass constructor on a subclass's `Class<?>`.

A wrong signature causes `getDeclaredConstructor` to throw `NoSuchMethodException`, even if another constructor could create a valid instance.

### Access Permissions and Module Boundaries

`getDeclaredConstructor` can return metadata for a `private` constructor, yet `newInstance` also checks access. If deep reflection is needed, `trySetAccessible()` can return `false` when the module forbids it; `setAccessible(true)` can throw `InaccessibleObjectException`. If caller and target are in the same module, deep access can normally be opened per JPMS rules, yet should only be done with legitimate reason and failure handling.

A safe pattern:

~~~java
Constructor<?> ctor = type.getDeclaredConstructor(String.class);

if (!ctor.canAccess(null) && !ctor.trySetAccessible()) {
    throw new IllegalStateException("Cannot access constructor");
}

Object instance = ctor.newInstance("demo");
~~~

This is an **illustrative snippet**, with `type` being a valid `Class<?>`. `Constructor#canAccess` takes argument `null`. Instance fields/methods use their corresponding receiver. If execution stops at the permission check, that **is not** an error inside the constructor body.

### Types That Cannot Be Instantiated Directly

An abstract class can have constructors for subclasses to call `super(...)`, and Reflection can find that constructor's metadata, yet `Constructor.newInstance` still cannot directly create an object of the abstract class: it can throw `InstantiationException`. Interfaces have no instance constructors to look up in the ordinary way. Enum constructors also have special restrictions when instantiating via Reflection; do not use `Constructor.newInstance` to create new enum constants.

## 9. How to Read Stack Traces to Locate the Root Error

A useful diagnostic workflow:

1. **Mark stages:** log after obtaining `Class<?>`, after finding `Constructor<?>`, right before and right after `newInstance`. This helps identify whether the error occurred during lookup, initialization, or invocation.
2. **Classify the throwable:** `NoSuchMethodException` at lookup; access/argument errors before entering target code; `ExceptionInInitializerError` related to initialization; `InvocationTargetException` related to throwables during constructor execution.
3. **Walk the causes:** print class name, message, and bounded repeated `getCause()` calls or write the full stack trace to a secure log.
4. **Identify the actually failing class:** it may be a superclass, the target class, or a dependent class actively used inside the constructor.
5. **If `NoClassDefFoundError` appears on a later attempt:** check logs from **the first use**; the second error is often just a consequence of the first init failure.
6. **Fix the root cause:** static configuration, files, classpath/module path, dependencies, access permissions, or constructor logic; avoid blind retries once the class is in an erroneous state.

Example diagnostic classification snippet in an application (assuming `ctor` is already identified and access is permitted):

~~~java
try {
    Object instance = ctor.newInstance();
    System.out.println("Created: " + instance.getClass().getName());
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable actual = e.getCause();
    System.err.println("Constructor path failed: " + actual);
} catch (ExceptionInInitializerError e) {
    System.err.println("Class initialization failed: " + e.getCause());
} catch (NoClassDefFoundError e) {
    System.err.println("Class cannot be initialized/defined: " + e);
}
~~~

This is **diagnostic illustrative code**, which must be placed in a method declaring/handling additional checked exceptions such as `InstantiationException` and `IllegalAccessException`; it is not a standalone program. Real logs must avoid leaking secrets from exception messages or stack traces if sensitive data is involved.

## 10. Can Failed Initialization Be Retried?

If a class's static initialization **fails**, the JVM marks the class in an erroneous state within the runtime that defined it. A second `newInstance` on **that exact class** will typically fail with `NoClassDefFoundError`; there is no standard Reflection API to "reset" class state and rerun the static initializer of the same `Class<?>`.

To recover, one must usually resolve the cause before the JVM initializes the class (e.g. valid configuration), restart the process, or in a specially designed architecture, load a new class definition with another class loader and manage its lifecycle accordingly. Do not use a new loader as a generic band-aid because it can alter type identity and complicate resource management.

Conversely, if a **constructor** throws an exception after the class has initialized successfully, the class is not marked erroneous merely because the constructor failed. Subsequent constructor calls can rerun and may succeed if input/state conditions allow.

### Multithreading Aspects

Class initialization is synchronized by the JVM under its own rules. If one thread initializes a class and fails, other threads needing that class can receive errors because the class failed to initialize. Do not write logic inspecting only `ExceptionInInitializerError` to assume every thread observes the same exception wrapper. Preserving the cause chain and logging the first event makes investigation far more accurate.

## 11. Connection to the Legacy `Class.newInstance()`

`Class.newInstance()` has been deprecated since Java 9 and can let checked exceptions escape from the constructor in a way that undermines exception checking. Prefer `getDeclaredConstructor().newInstance()` to select constructors and read `InvocationTargetException#getCause()` for errors during instance initialization. Both APIs still obey the rule that **the class must initialize successfully before the constructor can run**; therefore static initialization errors must be distinguished from errors inside the constructor.

## 12. Common Reasoning Errors

1. **Thinking `getDeclaredConstructor` runs the static block.** It is a metadata lookup; active use via `newInstance` or `Class.forName(name)` is what can require initialization.
2. **Equating `<clinit>` with `<init>`.** `<clinit>` is class initialization; `<init>` is each instance's constructor.
3. **Seeing `ExceptionInInitializerError` and editing the constructor body.** First check static field initializers/static blocks and superclass initialization.
4. **Seeing `InvocationTargetException` and logging only the wrapper.** Call `getCause()` to see the actual throwable from the constructor path.
5. **Seeing `NoClassDefFoundError` and concluding the class file was deleted.** Class init may have failed earlier; look for the initial log.
6. **Assuming every init failure wraps in `ExceptionInInitializerError`.** Errors in the `Error` branch can propagate directly.
7. **Assuming a constructor throwing an exception makes the class permanently unusable.** That differs from failed class initialization; a failed constructor call does not automatically turn the class erroneous.
8. **Catching only `Exception` to handle all failure types.** `ExceptionInInitializerError` and `NoClassDefFoundError` belong to `Error`; classify clearly and let severe errors surface where appropriate.
9. **Automatically opening an entire module because of a `private` constructor.** JPMS rules and access permissions must be handled specifically; opening a module does not fix a static initialization error.
10. **Repeatedly retrying the same `Constructor` after class init fails.** Calling again does not reset static state; it may only produce a stream of `NoClassDefFoundError`.
11. **Confusing wrong-parameter errors with errors inside the constructor.** `IllegalArgumentException` from `newInstance` argument checking differs from `InvocationTargetException` whose `cause` is an `IllegalArgumentException` thrown by the constructor itself.
12. **Overlooking superclasses/instance initializers.** Errors in superclass object initialization or initializers can happen before the first line of the subclass constructor body, even though the subclass's class initialization succeeded.

## 13. Self-Check Exercise

**Question 1.** Does `SomeType.class.getDeclaredConstructor()` guarantee that `SomeType`'s static block has run?

**Answer:** No. Retrieving constructor metadata does not initialize the target class.

**Question 2.** The target class's static field initializer throws `IllegalStateException` on first active use. What error does `Constructor.newInstance` typically exhibit?

**Answer:** `ExceptionInInitializerError` with `cause` being `IllegalStateException`, occurring before the constructor body begins.

**Question 3.** After init failure, why does calling the same `Constructor.newInstance` again usually throw `NoClassDefFoundError`?

**Answer:** The JVM marks the failed-initialization class in an erroneous state, so it does not rerun the static initializer as an ordinary fresh attempt.

**Question 4.** The static initializer runs successfully, yet the constructor throws `IllegalArgumentException`. What error does Reflection return?

**Answer:** `InvocationTargetException`; calling `getCause()` reveals `IllegalArgumentException`.

**Question 5.** If `Class.forName("pkg.Broken")` is called before constructor lookup, where does init failure occur?

**Answer:** It can blow up right at `Class.forName(String)`, because this overload requests initialization by default.

**Question 6.** A subclass constructor hits an error from a superclass constructor before the subclass body starts. Can `InvocationTargetException` be observed?

**Answer:** Yes. The constructor invocation path includes calling the superclass constructor; `InvocationTargetException#getCause()` traces back to the throwable from object initialization.

**Question 7.** Does `NoSuchMethodException` when calling `getDeclaredConstructor(int.class)` mean a class initialization error?

**Answer:** No. That is a failure of constructor signature lookup, occurring before constructor invocation.

**Question 8.** The class initialized successfully, and the constructor failed due to a specific input. Can another instance still be created?

**Answer:** Yes, if inputs/conditions are fixed and the constructor is invoked again; the class does not become erroneous merely because one constructor call failed.

## 14. Quick Analysis Checklist

When a Reflection error involves a constructor, note:

- **Target class:** `Class#getName()`, class loader, and module when relevant.
- **Metadata:** Was the constructor found? Is the `getParameterTypes()` signature right?
- **Permissions:** `canAccess(null)`, `trySetAccessible()`, possible JPMS restrictions.
- **Failure point:** `Class.forName`, `getDeclaredConstructor`, `newInstance`, or a call inside the constructor?
- **Outermost and root throwable:** `getCause()`, full stack trace; is it `ExceptionInInitializerError`/`NoClassDefFoundError` or `InvocationTargetException`?
- **Timing:** First active use or subsequent use? Has static initialization succeeded?
- **Superclass and dependencies:** Which initializer/constructor did the exception actually originate from?

**Key takeaway:** `getDeclaredConstructor()` looks up metadata; `Constructor.newInstance()` requires the class to be ready, so the JVM may run `<clinit>` **before** entering `<init>`. Static initialization failure typically surfaces as `ExceptionInInitializerError` the first time and `NoClassDefFoundError` afterward; throwables from code on the constructor path are typically wrapped by Reflection into `InvocationTargetException`. Always read the **cause chain** to fix the exact place where the error occurred.
