# Building a Typed Constructor-Based Factory with Clear Error Messages — Java Reflection

## 1. Practice Problem

Suppose a system has multiple implementations of a `Report` interface and wants to instantiate the appropriate one at runtime. Each implementation has a **constructor taking `String title`**. The caller needs to:

- Ask the factory to create an instance with the **exact type `T extends Report`**, rather than receiving `Object` and casting everywhere.
- Check the expected constructor **once when creating the factory**, instead of looking up metadata on every request.
- Clearly report missing classes, contract mismatches, missing constructor signatures, non-public constructors, uninstantiable types, or **errors originating from the constructor body itself**.
- Preserve the `cause` and stack trace when wrapping exceptions, helping operators tell whether a failure comes from configuration/Reflection or business logic.

Desired design:

```java
TypedFactory<PdfReport> factory = TypedFactory.forClass(PdfReport.class);
PdfReport report = factory.create("Monthly");
System.out.println(report.render()); // PDF: Monthly
```

This is an illustrative snippet using classes fully defined in Section 5. `TypedFactory<PdfReport>` lets the compiler know `create(...)` returns `PdfReport`, while Reflection is confined to the factory class.

**Idea:** isolate Reflection risks behind a small boundary, and express the rest of the application using interfaces and generic types. A factory does not need to turn every Java call into `Method.invoke`; after creating the object, use ordinary polymorphism.

## 2. What Does a "Typed Constructor" Mean?

The `java.lang.reflect.Constructor<T>` API retains the type information of the instance to be created:

```java
Class<PdfReport> type = PdfReport.class;
Constructor<PdfReport> ctor = type.getConstructor(String.class);
PdfReport report = ctor.newInstance("Monthly");
```

The snippet above requires `import java.lang.reflect.Constructor;` and the classes from the complete example below; it throws checked reflection exceptions, so the enclosing method must declare `throws` or `catch` them appropriately.

Components:

| Component | Meaning |
|---|---|
| `Class<T>` | Runtime token representing the concrete type `T` |
| `Constructor<T>` | Constructor metadata creating an instance corresponding to `T` |
| `type.getConstructor(String.class)` | Looks up a **public** constructor with **exactly one** parameter declared as `String` |
| `constructor.newInstance(title)` | Checks invocation conditions and runs the constructor body, returning `T` on success |
| `TypedFactory<T extends Report>` | Wraps the constructor and provides a typed creation API, bounding the return type to `Report` |

Inside the generic factory:

```java
public final class TypedFactory<T extends Report> {
    private final Constructor<T> constructor;
    // Other members...
}
```

This is a design declaration snippet; the complete runnable class is in Section 5.

### What Type Safety Guarantees — and Does Not Guarantee

`TypedFactory<PdfReport>.create(...)` returns `PdfReport` at compile time. Using a `Class<T>` obtained from the `PdfReport.class` literal makes lookup steps safer than raw `Class<?>` and unchecked `(T) rawObject` casts.

However, **generics do not turn runtime lookup into compile-time lookup**:

- The class might lack a `public PdfReport(String)` constructor.
- The constructor might have `private` or `protected` visibility.
- The constructor body might throw `IllegalArgumentException`, `IOException`, `Error`, etc.
- In module/class loader environments, access, linkage, or class initialization errors can still occur.

The factory must diagnose these clearly. Do not promise that using `Constructor<T>` makes Reflection immune to runtime failures.

## 3. Selecting the Right Constructor: public, declared, signature, and valid class

Two common APIs:

```java
type.getConstructor(String.class);
type.getDeclaredConstructor(String.class);
```

- `getConstructor(...)` finds a **public constructor** with the specified parameter types.
- `getDeclaredConstructor(...)` finds a constructor declared directly in the class, including non-public ones.
- Constructors are **not inherited** from superclasses: there is no mechanism to look up a public inherited constructor as with methods.
- Both lookup APIs rely on the **exact parameter type list**. They do not auto-box `int` to `Integer`, select overloads automatically, or convert `CharSequence` to `String`.
- `Class.getConstructor(...)` throws `NoSuchMethodException` when there is no public constructor matching the signature, even if a private constructor with the same signature exists.
- Constructors are not regular methods; do not look them up with `getMethod("ClassName", ...)`.

For a `String` parameter:

| Actual constructor | `getConstructor(String.class)` |
|---|---|
| `public PdfReport(String title)` | Found |
| `private PdfReport(String title)` | Throws `NoSuchMethodException` |
| `public PdfReport(CharSequence title)` | Throws `NoSuchMethodException` |
| `public PdfReport()` | Throws `NoSuchMethodException` |
| `public PdfReport(String title, int version)` | Throws `NoSuchMethodException` |
| `public PdfReport(String... values)` | Throws `NoSuchMethodException` when looked up with `String.class`, because the bytecode parameter type is `String[].class` |

**Do not automatically "try every constructor until one works"**: that makes the factory API unpredictable and can execute unintended code. Specify the contract signature clearly; when it does not match, report a configuration error with concrete corrective guidance.

Before instantiating, note that `abstract class` and `interface` types cannot be instantiated this way. The example checks early in the factory to produce a clear message. For enums, records, non-static member classes, anonymous/local classes, or classes from JPMS modules, structure and instantiation have their own constraints; do not force every class into a `(String)` contract.

## 4. Designing the Factory and Error Categories

In this practice exercise, we split errors into two distinct runtime exceptions:

- `FactoryConfigurationException`: invalid factory setup — the class does not exist, does not implement `Report`, is abstract, lacks a public `(String)` constructor, or metadata inspection is denied. This is usually a deployment/config/plugin contract error.
- `FactoryCreationException`: the factory was created, but **instance creation failed** — the target constructor threw an error, or invocation encountered access/argument/instantiation issues.

Both preserve a `Throwable cause`, not just a string message. Message templates should state **error kind, class, signature, and root cause**:

```text
Missing public constructor (String) on WrongConstructor
Constructor of FailingReport failed: IllegalArgumentException: invalid title
```

Avoid writing only `"Cannot create object"` or `"Reflection failed"`: maintainers will not know whether to change configuration, fix the constructor, or fix the input.

### Three Stages with Distinct Responsibilities

```text
input Class<T> or configured class name
             |
             v
[1] verify class + contract T extends Report
             |
             v
[2] resolve and cache public Constructor<T>(String)
             |
             v
[3] create(title) -> Constructor.newInstance(title)
             |
     +-------+-----------------------+
     |                               |
     v                               v
Reflection invocation error    Constructor body throws Throwable
IllegalAccessException,        InvocationTargetException
InstantiationException, ...                |
     |                                  getCause()
     v                                      v
FactoryCreationException       FactoryCreationException
(with original cause)          (with target's cause)
```

Performing **constructor lookup upfront** ensures missing-constructor errors surface immediately in `forClass`, rather than waiting for the first request. This is a useful **fail-fast** pattern when factories are created during bootstrap.

## 5. Complete Java 17+ Example with Clear Error Messages

Create a single file named **`TypedFactoryDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Modifier;
import java.util.Objects;

public class TypedFactoryDemo {
    public interface Report {
        String render();
    }

    public static final class PdfReport implements Report {
        private final String title;

        public PdfReport(String title) {
            this.title = Objects.requireNonNull(title, "title");
        }

        @Override
        public String render() {
            return "PDF: " + title;
        }
    }

    public static final class WrongConstructor implements Report {
        public WrongConstructor(int pages) {}

        @Override
        public String render() {
            return "unavailable";
        }
    }

    public static final class PrivateReport implements Report {
        private PrivateReport(String title) {}

        @Override
        public String render() {
            return "private";
        }
    }

    public abstract static class AbstractReport implements Report {
        public AbstractReport(String title) {}
    }

    public static final class FailingReport implements Report {
        public FailingReport(String title) {
            throw new IllegalArgumentException("invalid title");
        }

        @Override
        public String render() {
            return "unavailable";
        }
    }

    public static final class FactoryConfigurationException extends RuntimeException {
        public FactoryConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class FactoryCreationException extends RuntimeException {
        public FactoryCreationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class TypedFactory<T extends Report> {
        private final Class<T> type;
        private final Constructor<T> constructor;

        private TypedFactory(Class<T> type, Constructor<T> constructor) {
            this.type = type;
            this.constructor = constructor;
        }

        public static <T extends Report> TypedFactory<T> forClass(Class<T> type) {
            Objects.requireNonNull(type, "type");
            if (type.isInterface() || Modifier.isAbstract(type.getModifiers())) {
                throw new FactoryConfigurationException(
                        "Cannot instantiate abstract type: " + type.getSimpleName(), null);
            }
            try {
                return new TypedFactory<>(type, type.getConstructor(String.class));
            } catch (NoSuchMethodException e) {
                throw new FactoryConfigurationException(
                        "Missing public constructor (String) on " + type.getSimpleName(), e);
            } catch (SecurityException e) {
                throw new FactoryConfigurationException(
                        "Constructor lookup denied for " + type.getSimpleName(), e);
            }
        }

        public T create(String title) {
            try {
                return constructor.newInstance(title);
            } catch (InvocationTargetException e) {
                Throwable cause = e.getCause();
                throw new FactoryCreationException(
                        "Constructor of " + type.getSimpleName() + " failed: "
                                + cause.getClass().getSimpleName() + ": " + cause.getMessage(),
                        cause);
            } catch (InstantiationException | IllegalAccessException | IllegalArgumentException e) {
                throw new FactoryCreationException(
                        "Cannot create " + type.getSimpleName() + " with (String)", e);
            }
        }

        public static TypedFactory<? extends Report> fromName(String className) {
            Objects.requireNonNull(className, "className");
            try {
                Class<? extends Report> type =
                        Class.forName(className).asSubclass(Report.class);
                return forClass(type);
            } catch (ClassNotFoundException e) {
                throw new FactoryConfigurationException(
                        "Cannot load class: " + className, e);
            } catch (ClassCastException e) {
                throw new FactoryConfigurationException(
                        "Configured class " + className + " does not implement Report", e);
            }
        }
    }

    public static void main(String[] args) {
        TypedFactory<PdfReport> pdf = TypedFactory.forClass(PdfReport.class);
        PdfReport created = pdf.create("Monthly");
        System.out.println("success: " + created.render());

        try {
            TypedFactory.forClass(WrongConstructor.class);
        } catch (FactoryConfigurationException e) {
            System.out.println("wrong signature: " + e.getMessage());
        }

        try {
            TypedFactory.forClass(PrivateReport.class);
        } catch (FactoryConfigurationException e) {
            System.out.println("private constructor: " + e.getMessage());
        }

        try {
            TypedFactory.forClass(AbstractReport.class);
        } catch (FactoryConfigurationException e) {
            System.out.println("abstract class: " + e.getMessage());
        }

        try {
            TypedFactory.forClass(FailingReport.class).create("bad");
        } catch (FactoryCreationException e) {
            System.out.println("target failure: " + e.getMessage());
            System.out.println("target cause: " + e.getCause().getClass().getSimpleName());
        }

        try {
            TypedFactory.fromName("java.lang.String");
        } catch (FactoryConfigurationException e) {
            System.out.println("wrong type: " + e.getMessage());
        }

        try {
            TypedFactory.fromName("demo.NotFound");
        } catch (FactoryConfigurationException e) {
            System.out.println("missing type: " + e.getMessage());
        }
    }
}
```

Run in the directory containing the file:

```bash
javac --release 17 TypedFactoryDemo.java
java TypedFactoryDemo
```

**Actual stdout** when compiling and running the program:

```text
success: PDF: Monthly
wrong signature: Missing public constructor (String) on WrongConstructor
private constructor: Missing public constructor (String) on PrivateReport
abstract class: Cannot instantiate abstract type: AbstractReport
target failure: Constructor of FailingReport failed: IllegalArgumentException: invalid title
target cause: IllegalArgumentException
wrong type: Configured class java.lang.String does not implement Report
missing type: Cannot load class: demo.NotFound
```

The code was compiled with `javac --release 17` and ran successfully. It uses public nested classes in a single file for easy copying; in a real application, separate `TypedFactory` and implementations into cleanly managed classes and packages.

## 6. Reading the Output: Classifying Every Case Properly

**Success path:** `TypedFactory.forClass(PdfReport.class)` receives a `Class<PdfReport>`; `getConstructor(String.class)` finds the public constructor with the exact signature. `create("Monthly")` returns an object of type `PdfReport`; the caller invokes `render()` normally without needing `Method.invoke`.

**Wrong signature:** `WrongConstructor` only has an `(int)` constructor. This is not a "runtime parameter cannot be converted" error; the factory detects the **missing `(String)` constructor at lookup time**, catches `NoSuchMethodException`, and translates it into a `FactoryConfigurationException` with clear details.

**Private constructor:** `PrivateReport` has `(String)` but it is private. `getConstructor(String.class)` does not return it; the "missing public constructor" message matches the factory's contract. Do not fall back to finding the private constructor and calling `setAccessible(true)`, as that alters the access contract and can violate JPMS restrictions.

**Abstract class:** `AbstractReport` is a valid type under `T extends Report` but cannot be instantiated directly. Checking early with `Modifier.isAbstract` reports a configuration error rather than letting `Constructor.newInstance` fail later.

**Error in the constructor body:** `FailingReport(String)` is valid, yet throws `IllegalArgumentException("invalid title")` when executed. `Constructor.newInstance` **wraps target-code errors in `InvocationTargetException`**. The factory uses `e.getCause()` to retrieve `IllegalArgumentException` and creates a `FactoryCreationException` with the original cause and a message containing the error type and details.

**Class violates contract:** `Class.forName("java.lang.String")` finds the class, but `String` does not implement `Report`. `asSubclass(Report.class)` throws `ClassCastException`; the factory translates it into a configuration error saying "does not implement Report". Do not silence the check with an unchecked `(Class<Report>)` cast.

**Non-existent class:** `Class.forName("demo.NotFound")` throws `ClassNotFoundException`. This is a **class lookup** error, distinct from `NoSuchMethodException` when the class exists but the constructor does not match.

## 7. Why Must the Factory Preserve the Cause?

If you only write:

```java
catch (Exception e) {
    throw new RuntimeException("Create failed");
}
```

then the original error's stack trace is lost from the **cause chain**; it becomes very hard to tell whether the failure was a missing constructor, a security restriction, a null input, or a bug inside the implementation.

Preserving the cause:

```java
catch (InvocationTargetException e) {
    Throwable targetFailure = e.getCause();
    throw new FactoryCreationException(
            "Constructor of " + type.getName() + " failed",
            targetFailure);
}
```

This is an **illustrative code snippet** inside `TypedFactory<T>`, where `type` and `FactoryCreationException` already exist. When the thrown exception is logged, the stack trace shows the path through the factory class down to the constructor failure. Do not log only `getMessage()` when stack trace analysis is needed.

### Distinguishing the Outer Wrapper from the Inner Cause

| Stage | Original/observed exception | What to report |
|---|---|---|
| `getConstructor` cannot find public signature | `NoSuchMethodException` | Misconfiguration: missing public constructor `(String)` |
| `Class.forName` cannot find class | `ClassNotFoundException` | Misconfiguration: class name / class loader / classpath |
| `asSubclass` fails contract | `ClassCastException` | Misconfiguration: implementation is not a subtype of the interface |
| `Constructor.newInstance` lacks access | `IllegalAccessException` | Cannot invoke constructor due to access control/module |
| Constructor body throws exception | `InvocationTargetException` wrapping Throwable | Object creation failure: **actual cause is in `getCause()`** |
| Class/runtime incompatibility error | `LinkageError`, `ExceptionInInitializerError`, etc. | JVM linkage/initialization error, not necessarily from the constructor body |

**Key point:** `InvocationTargetException` is the Reflection invocation wrapper; `FactoryCreationException` in the example is an **application-defined wrapper**. These two classes are not the same. Factory callers only need to understand the contract published by the application; maintainers can inspect the cause to investigate the root issue.

In production, whether to wrap or **rethrow serious `Error`s** (such as `OutOfMemoryError`) requires an explicit policy. The example chooses one easy-to-understand output exception type for learning purposes, but you should not swallow `Error`s or turn severe JVM failures into retryable business errors.

## 8. A Typed Factory When the Class Is Configured as a String

When runtime receives an implementation name from a configuration file, `Class.forName(className)` returns `Class<?>`. To preserve the `Report` contract, use:

```java
Class<? extends Report> reportType =
        Class.forName(configuredName).asSubclass(Report.class);
TypedFactory<? extends Report> factory =
        TypedFactory.forClass(reportType);
Report report = factory.create("Monthly");
```

This is an **illustrative snippet** with an application-supplied `configuredName` and the classes from the complete example. When the class is decided from a runtime string, the compiler cannot know ahead of time whether it is `PdfReport` or `OtherReport`; hence the safe return type is `? extends Report` or `Report`, **not `PdfReport`**.

If a caller needs `PdfReport` specifically, pass `PdfReport.class` directly or explicitly check/cast the subtype before using it.

**Do not load classes from untrusted user-supplied strings without controls.** By default, `Class.forName(String)` can **initialize the class**; static initializers can execute code even before you call the constructor. For a plugin system, use an allowlist/registry, verified implementation names, permitted class loaders, and avoid leaking the full classpath in client-facing error messages.

If you want to separate class loading from initialization, use the overload:

```java
Class<?> rawType = Class.forName(
        configuredName,
        false,
        Thread.currentThread().getContextClassLoader());
```

This is an illustrative snippet. `initialize=false` only defers initialization; when instantiating later, the class may still be initialized and throw an error. The thread context class loader may not be appropriate in every application: choose the loader according to your plugin/module architecture, rather than assuming it is always right. In JPMS systems and multi-classloader setups, verify visibility, module boundaries, and actual loading behavior.

## 9. Why Resolve the Constructor Once and Cache It?

The design retains:

```java
private final Class<T> type;
private final Constructor<T> constructor;
```

In each `TypedFactory<T>` instance, `getConstructor(String.class)` runs only in `forClass`; `create` reuses `Constructor<T>`. This approach:

1. **Fails fast** when the implementation configuration violates the constructor contract.
2. Avoids repeating metadata lookup on every object creation.
3. Centralizes logging and exception translation in one place.
4. Improves testability because every failure mode goes through a consistent factory API.

However, **the constructor body still runs on every `create(...)`** and may fail depending on input data. Caching metadata is not caching instances, nor does it imply a singleton factory or thread safety of the created object itself.

An immutable factory holding only `Class<T>` and `Constructor<T>` can be reused across multiple threads; however, if the constructor implementation creates shared mutable state or touches shared resources, thread safety of creation still depends on the implementation and those resources.

### Avoiding Memory Leaks with Plugins and Class Loaders

A `static Map<Class<?>, TypedFactory<?>>` living for the entire application lifetime can hold strong references to `Class`/`Constructor` and plugin class loaders. In systems with unloading/redeployment, consider:

- Scoping the factory to the plugin's lifecycle and releasing the registry when the plugin stops.
- Attaching metadata per class using `ClassValue` when appropriate.
- Being careful with `WeakHashMap<Class<?>, ...>` because values may hold back-references to the class, defeating weak keys.
- Not caching solely by the `getName()` string when multiple class loaders exist, because the same binary name can belong to two distinct runtime classes.

Caching should be guided by profiling; for very infrequent instantiations, a simple factory class and accurate checks matter more than micro-optimization.

## 10. Good Error Messages: Informative Without Leaking Secrets

A good configuration error message can follow this pattern:

```text
Cannot construct report implementation com.example.PdfReport:
expected public constructor (java.lang.String)
```

In real systems, include:

- **Operation:** load / verify constructor / create.
- **Class:** full name (`type.getName()`) to distinguish packages.
- **Expected signature:** e.g. `(java.lang.String)`, not just a generic method name.
- **Error kind:** `NoSuchMethodException`, `IllegalAccessException`, or failure from target.
- **Root cause:** preserved via an exception constructor taking `cause`.
- **Controlled context:** operation ID, plugin/module, or class loader if needed for investigation.

The example uses `getSimpleName()` for short, stable stdout; in production logging where multiple classes can share a simple name, use `getName()`, along with module/loader details when needed.

Never include sensitive values such as passwords, tokens, secret keys, personal data, or secret input strings in error messages or logs just for debugging. You can say "constructor argument validation failed" and keep the root cause in internal logs, rather than echoing verbatim user input over a public API.

### Do Not Swallow Errors into Null

Avoid:

```java
try {
    return constructor.newInstance(title);
} catch (Exception ignored) {
    return null;
}
```

This is an **anti-pattern** in a method returning `T`. If the `null` object is used later, the caller gets a `NullPointerException` at an unrelated location, losing the stack trace of the original cause. Throw a structured error or return a `Result<T, Error>` type clearly defined by the application contract.

## 11. Common Mistakes When Designing a Reflection Factory

**1. Using raw `Constructor` or casting `(T) ctor.newInstance(...)` unconditionally.** Raw types strip compile-time information; use `Class<T>` and `Constructor<T>`, or `asSubclass(BaseType.class)` when the type comes from a runtime name.

**2. Calling `getDeclaredConstructor` and assuming it is invokable.** Declared lookup can find a private constructor, yet `newInstance` still checks access. `setAccessible(true)` does not guarantee bypassing module access and should not be used merely to "circumvent" a public constructor contract.

**3. Confusing lookup errors with target errors.** A missing constructor is `NoSuchMethodException` during resolution; an error thrown by constructor code is inside `InvocationTargetException.getCause()`. Handle them in separate branches.

**4. Catching generic `Exception` and printing `"Factory failed"`.** Strips actionable details; preserve the cause and separate configuration from creation.

**5. Using the deprecated `type.newInstance()`.** Use `getDeclaredConstructor().newInstance()` or `getConstructor(...).newInstance(...)`; `Class.newInstance()` has a different exception contract, especially when the constructor throws checked exceptions.

**6. Letting callers pass `Object... args` without defining a signature.** Easily leads to mismatched arity, boxing, varargs, or wrong-cast issues. With a `create(String)` factory, callers know the exact input contract.

**7. Failing to check `interface`/`abstract`, constructor signature, and service contract before serving requests.** Errors surface late and misconfigurations become hard to pinpoint. Validate at bootstrap whenever possible.

**8. Assuming `Class.forName` only "reads metadata".** The single-argument overload can trigger class initialization. Class names from untrusted input must be controlled.

**9. Caching factories globally via strong `Class` keys in plugin-reloading systems.** Can retain old class loaders. Choose clear ownership and cache lifecycles.

**10. Automatically retrying a target constructor after it throws an exception.** The constructor may already have produced side effects before failing (opening files, writing to a DB, sending requests). Retry only when the action is idempotent and governed by an explicit retry policy.

**11. Treating Reflection error messages as a stable contract.** The JDK or compiler can change message text; tests should assert on **exception type, cause, and the message parts controlled by your application**.

## 12. Practice Extensions

### Exercise 1 — No-argument factory

Try writing `TypedFactory<T>` with `getConstructor()` and `create()`, then compare it with the `Supplier<T>` interface. When all implementations are known at compile time, a factory using a method reference (`PdfReport::new` when the constructor signature matches) is usually simpler than Reflection.

### Exercise 2 — Multi-argument factory

Change the contract to `create(String title, int pages)`; look up `type.getConstructor(String.class, int.class)`. Write a test for a class that only has a `(String, Integer)` constructor: Reflection **does not automatically find that overload**.

### Exercise 3 — Asserting on exceptions

Use JUnit or your project's test harness to verify:
- `forClass(WrongConstructor.class)` throws `FactoryConfigurationException` with cause `NoSuchMethodException`.
- `forClass(PrivateReport.class)` reports **missing public constructor**.
- `forClass(AbstractReport.class)` reports an abstract type.
- `forClass(FailingReport.class).create("bad")` throws `FactoryCreationException` with `getCause() instanceof IllegalArgumentException`.
- `fromName("java.lang.String")` reports that the class does not implement `Report`.
- `forClass(PdfReport.class).create("ok")` returns the expected `PdfReport` and rendered output.

### Exercise 4 — Registering plugins by interface

Replace accepting arbitrary class names with a validated `Map<String, Class<? extends Report>>` registry. Clients select an ID such as `"pdf"` instead of a Java binary class name directly; the registry can be populated from `ServiceLoader` when plugin registration is needed.

## 13. Pre-Production Checklist

1. **Clear contract:** the factory creates `T extends Report` and requires an exact public `(String)` constructor.
2. **Typed metadata:** use `Class<T>` and `Constructor<T>`, avoiding arbitrary raw casts.
3. **Fail fast:** validate concrete class, non-abstract status, and constructor signature when creating the factory.
4. **Separate errors:** distinguish configuration/lookup from creation/invocation and exceptions thrown by the target constructor.
5. **Preserve cause:** always keep the cause when wrapping, using messages with class + signature.
6. **No unconditional access bypass:** prefer public constructors and explicit APIs, respecting JPMS.
7. **Safe runtime class names:** validate, allowlist, and manage class loaders; do not accept arbitrary untrusted input.
8. **Lifecycle-aware caching:** avoid repeated lookups, but do not retain plugin class loaders indefinitely.
9. **Test both success and failure paths:** pay attention to primitive/wrapper, abstract, private, and target runtime exceptions.
10. **Keep logs useful yet minimal:** do not leak sensitive input and do not swallow the root cause.

## 14. Summary

- `Class<T>` + `Constructor<T>` form the foundation for building a **typed Reflection factory**.
- `getConstructor(String.class)` explicitly enforces a **public constructor with exactly one `String` parameter**, checked early during factory configuration.
- `Constructor.newInstance` can wrap exceptions from the **target constructor body** in `InvocationTargetException`; preserve `getCause()` when translating to an application exception.
- Good error messages distinguish **class/contract/constructor lookup errors** from **instantiation/target logic errors**, rather than simply saying "Reflection failed".
- After successful creation, invoke methods normally via `Report`/`PdfReport`. Reflection should live inside a small, well-scoped, thoroughly tested factory class.