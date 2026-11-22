# Reproducing NoClassDefFoundError and Class Initialization Errors in Java

A Java application can compile successfully and then fail at runtime with `java.lang.NoClassDefFoundError`. Many people look at the error name and simply conclude that "the `.class` file does not exist". This is **true in some scenarios, but not all**. A class **may still be on the classpath and have already been found by the JVM**, yet because **static initialization failed**, subsequent uses of the class still throw `NoClassDefFoundError: Could not initialize class ...`.

This lab exercise uses Java 17+ to independently reproduce two categories of errors:

1. **Missing dependency at runtime:** `app.MissingDemo` was compiled when `lib.Helper` still existed, but at runtime only the application's output is provided. The JVM cannot find the class to link: `NoClassDefFoundError` occurs; the *cause* in the experiment is `ClassNotFoundException`.
2. **Class initialization error (`<clinit>`):** the `demo.Broken` class is found, but its static initializer throws `IllegalStateException`. The first active use encounters `ExceptionInInitializerError`, and the class transitions to the **erroneous** state; the next active use in the **same JVM, for the same class definition** encounters `NoClassDefFoundError`.

Goal: understand the **loading → linking → initialization** order, distinguish between the three errors `ClassNotFoundException`, `ExceptionInInitializerError`, and `NoClassDefFoundError`; know how to write proper compile/run experiments, explain verified stdout, identify the root cause using stack trace/cause/loader, and handle cases properly when an application or plugin has loaded a faulty class.

## 1. Problem Statement: Could Not Find the Class or Did Class Initialization Fail?

Consider these three messages:

```text
java.lang.ClassNotFoundException: lib.Helper

java.lang.NoClassDefFoundError: lib/Helper

java.lang.NoClassDefFoundError: Could not initialize class demo.Broken
```

The messages may look similar, but they refer to different steps:

| Scenario | Typical Throwable Type | What to Check |
| --- | --- | --- |
| The application calls `ClassLoader.loadClass("lib.Helper")` by name, but the loader cannot find it | `ClassNotFoundException` (*checked exception*) | Class name, specific loader, classpath/module path |
| Compiled bytecode requires `lib.Helper`, but the definition cannot be found at runtime | `NoClassDefFoundError` (*LinkageError*) | Compile/runtime dependencies, loader, JAR files, class root |
| The class is found, and its static initializer throws a `RuntimeException` on the first attempt | `ExceptionInInitializerError` (*LinkageError*) | The actual error inside `static { ... }` or static field initialization |
| After the class has entered a failed initialization state, code actively uses the same class again | `NoClassDefFoundError` | Look for the **first failed initialization** in the logs, rather than only looking at the later error |

With `NoClassDefFoundError`, **the message and cause are diagnostic data, not a stable API to parse with hardcoded strings**. The content of the message may vary depending on the JVM or how the situation arises.

## 2. Error Hierarchy in java.lang

```text
java.lang.Throwable
├── Exception
│   └── ReflectiveOperationException
│       └── ClassNotFoundException
└── Error
    └── LinkageError
        ├── NoClassDefFoundError
        ├── ExceptionInInitializerError
        ├── NoSuchMethodError
        ├── NoSuchFieldError
        ├── IllegalAccessError
        └── ...
```

- `ClassNotFoundException` is a **checked exception** that typically arises from calls that look up a class by name, such as `Class.forName(...)` and `ClassLoader.loadClass(...)`.
- `NoClassDefFoundError` and `ExceptionInInitializerError` are **Errors belonging to the LinkageError family**.
- `catch (Exception ex)` **does not catch** these two Errors. In the lab, you can intentionally `catch (LinkageError)` to observe both usage attempts; **linkage errors should not be masked in production business logic**.
- A `NoClassDefFoundError` may have `getCause()==ClassNotFoundException` when a class is missing; however, if the class is already in the erroneous state, the cause **may be the earlier initialization error**. Therefore, you must read the entire cause chain.

## 3. Three Phases of the Class Lifecycle

According to the JLS/JVMS, when using a class, the JVM performs distinct tasks:

```text
LOAD
  |
  | JVM/class loader finds the binary class definition and creates the runtime Class<?>
  v
LINK
  |
  +-- Verify: checks bytecode validity
  +-- Prepare: prepares static fields with default values
  +-- Resolve: links symbolic references to classes/fields/methods
  |            (some resolution may be deferred)
  v
INITIALIZE
  |
  +-- Initialize required superclass/superinterfaces
  +-- Assign static fields according to initializers
  +-- Run static blocks in textual order
  v
READY or ERRONEOUS
```

### Loading

`ClassLoader.loadClass("demo.Broken")` typically loads or finds a class, but **does not require running the static initializer immediately**. The `Broken` class may already be represented by a valid `Class<?>` even though `<clinit>` has not run yet.

### Linking

During the verification/preparation/resolution phases, bytecode may reference classes that have not yet been loaded at the initial point in time. The JVM is permitted to defer some symbolic reference resolution; therefore, a dependency error may only appear **when the corresponding code path is executed**. Do not assume that every missing dependency will crash the application immediately at startup.

### Initialization

When a program first performs an *active use* of a class, the JVM ensures the class is initialized according to Java rules. Static field initializers and `static { ... }` blocks are executed in the appropriate order. If the initializer completes normally, the class is ready. If the initializer fails, the class can be marked **erroneous**; subsequent initialization attempts of the **same runtime class** are not automatically retried like a normal constructor.

**This is the foundation for understanding why "the class file is still on disk", yet after the first failure, `NoClassDefFoundError` appears.**

## 4. Lab A — Missing Library at Runtime, Reproducing NoClassDefFoundError

Goal: create a `lib.Helper` dependency separate from the application. Compile the application with the full dependency and then **intentionally omit the dependency directory from the runtime classpath**.

### 4.1 Project Structure

```text
ncdfe-lab/
├── src/
│   ├── lib/
│   │   └── Helper.java
│   └── app/
│       └── MissingDemo.java
├── lib-classes/               (output of Helper)
└── app-classes/               (output of MissingDemo)
```

Create `lib-classes` and `app-classes` before compiling. Run the commands from the **`ncdfe-lab` directory**, not from `src`.

### 4.2 Creating the Library

File `src/lib/Helper.java`:

```java
package lib;

public final class Helper {
    public static String message() {
        return "Helper available";
    }
}
```

The `lib.Helper` class is a dependency of the application. The compiler needs to see the `message()` API in order to compile successfully.

### 4.3 Creating the Consumer

File `src/app/MissingDemo.java`:

```java
package app;

import lib.Helper;

public final class MissingDemo {
    public static void main(String[] args) {
        System.out.println("app started");

        try {
            System.out.println(Helper.message());
        } catch (NoClassDefFoundError error) {
            System.out.println("error="
                    + error.getClass().getSimpleName());
            System.out.println("missing=" + error.getMessage());

            Throwable cause = error.getCause();
            System.out.println("cause="
                    + (cause == null
                       ? "<none>"
                       : cause.getClass().getSimpleName()));
        }
    }
}
```

**Why intentionally catch `NoClassDefFoundError`?** Only so the experiment can print the error type, the name of the class that could not be found, and the cause instead of terminating the JVM with a long stack trace. A real application must fix its runtime deployment; it should not treat a missing dependency as a normal business branch.

### 4.4 Compiling with the Proper Dependency

```bash
javac --release 17 -d lib-classes src/lib/Helper.java
javac --release 17 -cp lib-classes -d app-classes src/app/MissingDemo.java
```

- The first command produces `lib-classes/lib/Helper.class`.
- The second command makes `lib.Helper` visible to `javac` via `-cp lib-classes` and produces `app-classes/app/MissingDemo.class`.
- `-d` specifies the output root; package paths are created accordingly.
- **Do not pass both source files to a single `javac` invocation with the same output directory**, because the experiment needs **to keep the dependency output separate from the application output**.

### 4.5 Control Case — Correct Runtime Classpath

**Windows** uses `;` as the path separator:

```bash
java -cp "app-classes;lib-classes" app.MissingDemo
```

**Linux/macOS** uses `:`:

```bash
java -cp "app-classes:lib-classes" app.MissingDemo
```

Verified compile/run stdout:

```text
app started
Helper available
```

Both `app.MissingDemo` and `lib.Helper` are visible to the loader. There is no linkage error.

### 4.6 Failure Case — Omitting Only the Dependency at Runtime

**Do not recompile**. Run:

```bash
java -cp app-classes app.MissingDemo
```

Verified stdout:

```text
app started
error=NoClassDefFoundError
missing=lib/Helper
cause=ClassNotFoundException
```

Exact explanation:

1. The JVM finds `app.MissingDemo` from `app-classes`; therefore, the program prints `app started`.
2. When executing the call `Helper.message()`, the bytecode needs to resolve the `lib.Helper` class.
3. The runtime classpath **does not include `lib-classes`**, so the loader cannot find that class definition.
4. The bytecode usage receives `NoClassDefFoundError`; the cause in the experiment is `ClassNotFoundException`.
5. This is a **missing dependency on the runtime classpath**, not a failing static initializer in `Helper` (because `Helper` was not found).

The name in the message uses forward slashes `lib/Helper` following the VM internal representation, whereas the Java binary name is written `lib.Helper`. Do not take the slashes in the error as evidence that source code must use slashes in imports.

### 4.7 Cross-Checking the Application's Bytecode

```bash
javap -classpath app-classes -c -verbose app.MissingDemo
```

In the constant pool/bytecode of the executed program, the notable part is:

```text
Methodref ... // lib/Helper.message:()Ljava/lang/String;
Class ...     // lib/Helper
...
invokestatic ... // Method lib/Helper.message:()Ljava/lang/String;
```

`javap` proves that **the caller was compiled against `lib.Helper`**, while at runtime the definition required by that symbolic reference is missing. The constant pool indices (`#21`, `#22`, ...) may differ when the source/compiler changes; what matters is **the owner, method name, and descriptor**.

**Lab A Conclusion:** the class existed **at compile time**, but is absent from the sources visible to the loader **at runtime**. Adding the correct dependency to the runtime classpath allows the same client binary to run without modifying code.

## 5. Lab B — Static Initializer Fails and NoClassDefFoundError Appears on the Next Attempt

This lab intentionally **does not delete any class files**. The `demo.Broken` class is always present on the runtime classpath. We make `static { ... }` throw an exception during the first initialization.

### 5.1 Structure

```text
ncdfe-lab/
├── init-src/
│   └── demo/
│       ├── Broken.java
│       └── InitDemo.java
└── init-classes/             (separate output)
```

Also create `init-src/demo` and `init-classes` alongside the directories from Lab A.

### 5.2 The Broken Class with an Intentionally Failing Static Initializer

File `init-src/demo/Broken.java`:

```java
package demo;

public final class Broken {
    public static int number;

    static {
        System.out.println("<clinit> entered");

        if (Boolean.parseBoolean(
                System.getProperty("lab.fail", "true"))) {
            throw new IllegalStateException("boom");
        }

        number = 42;
    }
}
```

Explanation:

- The JVM performs static initialization when the class is first actively used according to the JLS.
- `System.getProperty("lab.fail", "true")` defaults to `"true"` if the JVM property is not passed.
- `Boolean.parseBoolean(...)` is evaluated at runtime, so the compiler accepts a static initializer with a branch that can throw an exception (rather than a block proven at compile time to always fail).
- `IllegalStateException` **is not a subclass of `Error`**, so the JLS requires the JVM to wrap it in an `ExceptionInInitializerError` when initialization fails.
- If the property is `false`, the static initializer sets `number = 42` and the class initializes successfully.
- `number` is a non-final field, so reading it via `Broken.number` genuinely triggers class initialization if not already initialized.

### 5.3 Consumer Attempting Active Use Twice in the Same JVM

File `init-src/demo/InitDemo.java`:

```java
package demo;

public final class InitDemo {
    public static void main(String[] args) {
        System.out.println("loaded without init="
                + Broken.class.getName());

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(
                        "attempt " + attempt + " value=" + Broken.number);
            } catch (LinkageError error) {
                System.out.println(
                        "attempt " + attempt + " error="
                        + error.getClass().getSimpleName());

                Throwable cause = error.getCause();
                System.out.println("cause="
                        + (cause == null
                           ? "<none>"
                           : cause.getClass().getSimpleName()));
            }
        }
    }
}
```

**Key point:** `Broken.class` is used to get the class literal; it **does not by itself require `<clinit>` to run**. However, reading `Broken.number` — a static field that is not a constant variable — is an **active use** and requires the class to be initialized.

The `catch (LinkageError)` statement is solely for the lab to clearly print the first and subsequent attempts; do not use "catch the error and keep running" as a way to recover a class in production.

### 5.4 Compiling

```bash
javac --release 17 -d init-classes init-src/demo/Broken.java init-src/demo/InitDemo.java
```

The result contains:

```text
init-classes/demo/Broken.class
init-classes/demo/InitDemo.class
```

**Both class files are present** in the runtime path. Do not delete or replace `Broken.class` at any step of Lab B.

### 5.5 Default Run — Class Initialization Fails

```bash
java -cp init-classes demo.InitDemo
```

Stdout **verified by running**:

```text
loaded without init=demo.Broken
<clinit> entered
attempt 1 error=ExceptionInInitializerError
cause=IllegalStateException
attempt 2 error=NoClassDefFoundError
cause=ExceptionInInitializerError
```

Step-by-step explanation:

1. `loaded without init=demo.Broken`: the JVM has the `Class<?>` for `Broken`, but has not run the static initializer yet; the class literal expression does not actively use the class in a way that requires initialization.
2. `<clinit> entered`: on the first read of `Broken.number`, the JVM performs static initialization.
3. `attempt 1 error=ExceptionInInitializerError`: the static block throws `IllegalStateException("boom")`; the JVM wraps the initialization failure in `ExceptionInInitializerError`.
4. `cause=IllegalStateException`: the root cause the developer needs to fix lies inside the static initializer, not a classpath issue.
5. `attempt 2 error=NoClassDefFoundError`: the JVM records that `demo.Broken` is already in the **erroneous** state after the failed initialization, so it does not re-run `<clinit>` for the same class.
6. `cause=ExceptionInInitializerError`: the JVM in this experiment still preserves the cause chain related to the previous initialization attempt. **Do not assume every JVM always packages the cause in the exact same format**; look for the first error in the logs.

There is no second `<clinit> entered` line. That is concrete evidence that **the static initializer is not retried automatically**.

### 5.6 Running a New Process with the Corrected Property

Run a **new JVM**:

```bash
java -Dlab.fail=false -cp init-classes demo.InitDemo
```

With PowerShell on Windows, if quoting is needed so the shell does not interpret the hyphen/syntax, you can use:

```powershell
java '-Dlab.fail=false' -cp init-classes demo.InitDemo
```

Verified stdout:

```text
loaded without init=demo.Broken
<clinit> entered
attempt 1 value=42
attempt 2 value=42
```

Now class initialization completes normally. Within the same process, the second access does not run `<clinit>` again because the class is already initialized.

**Important:** This is a **new process**. Fixing the property **after the class has already become erroneous within the same runtime class definition** does not cause `<clinit>` to re-run automatically. To recover a faulty class definition in an application with a custom loader, you typically need to fix the root cause and create a **new definition in a new class loader** following the appropriate plugin lifecycle, or restart the JVM; you cannot "reset the erroneous flag" through any public Java API.

## 6. Comparing Lab A and Lab B with Evidence

| Question | Lab A: Missing Class at Runtime | Lab B: Static Initialization Failure |
| --- | --- | --- |
| Does the required class exist in the runtime output? | **No**: `lib.Helper` was excluded from the runtime classpath | **Yes**: `demo.Broken.class` is in `init-classes` |
| Could the caller compile? | Yes, compiled with `lib-classes` | Yes, both `Broken` and `InitDemo` compiled together |
| Point where the error occurs | Linking class `lib.Helper` when calling `Helper.message()` | First active use of `Broken.number` |
| First observed error | `NoClassDefFoundError` | `ExceptionInInitializerError` |
| Cause in the experiment | `ClassNotFoundException` | `IllegalStateException` |
| Error on retry in the same JVM | Cannot rely on a single common message type; depends on loader/linkage state as well | `NoClassDefFoundError` because the class is already in the erroneous state |
| How to fix | Put the right class/JAR onto the **runtime classpath/loader** | Fix the static initializer/config error and create a valid new initialization process |
| Need to recompile the caller? | No, if the dependency is binary-compatible and deployed properly | No, if the root-cause code and config are correct, though the old erroneous class does not recover on its own |
| How does the classloader matter? | The loader cannot see `lib.Helper` | Identity/erroneous state is tied to a class definition defined by a loader |
| Is it a `ClassNotFoundException` directly from a reflection API? | No: the caller uses a bytecode method reference, so `NoClassDefFoundError` appears | No: the class was found and initialization started |

Because **the same final error `NoClassDefFoundError` has multiple causes**, diagnosis must start from **the preceding sequence of events and the cause chain**.

## 7. Tracing the Cause Chain Instead of Just the Error Name

In production, the full stack trace may show:

**Missing dependency:**

```text
java.lang.NoClassDefFoundError: lib/Helper
    ...
Caused by: java.lang.ClassNotFoundException: lib.Helper
    ...
```

**Static initializer fails on the first attempt:**

```text
java.lang.ExceptionInInitializerError
    ...
Caused by: java.lang.IllegalStateException: boom
    at demo.Broken.<clinit>(Broken.java:...)
    ...
```

**Reusing an already erroneous class:**

```text
java.lang.NoClassDefFoundError: Could not initialize class demo.Broken
    ...
```

These are **abbreviated examples, not fixed stdout**; stack trace line numbers and how causes are presented vary by JVM/build.

How to read them:

1. **The first throwable type in the historical logs**: did `ExceptionInInitializerError` appear before `NoClassDefFoundError`?
2. **Message**: is it a missing binary name `lib/Helper` or the message "Could not initialize class ..."?
3. **Cause**: `ClassNotFoundException`, `IllegalStateException`, `NullPointerException`, or another error?
4. **`<clinit>` frame**: if present, check the static field initializer/static block in the corresponding class.
5. **Loader and CodeSource**: which loader actually defined the class, and from which JAR was it loaded?
6. **Timing**: startup, first request, plugin task, or redeploy?

**Do not truncate the `Caused by` lines when forwarding logs to investigators.** A late `NoClassDefFoundError` is often only a consequence, not the original cause.

## 8. Which Operations Actually Trigger Class Initialization?

JLS `12.4.1` describes the actions that require initializing a class/interface, for example:

| Operation | Requires class initialization when needed? | Notes |
| --- | --- | --- |
| `new Broken()` | Yes | The class is initialized before instance construction completes |
| Reading a static field that is **not a constant variable** (`Broken.number`) | Yes | The demo uses this approach |
| Writing to a static field (`Broken.number = 5`) | Yes | If the operation actually references the class's field |
| Calling a static method (`Broken.run()`) | Yes | Active use |
| `Class.forName("demo.Broken")` | Yes | The single-argument overload requires initialization |
| `Class.forName("demo.Broken", true, loader)` | Yes | Loader is explicitly specified |
| `Class.forName("demo.Broken", false, loader)` | Does not require immediate initialization | May load/link without running the static initializer yet |
| `loader.loadClass("demo.Broken")` | Does not require immediate initialization | The loader will find `Class<?>`, without running `<clinit>` by default |
| `Broken.class` | Does not by itself require initialization | That is why the first line of Lab B prints before the static block |
| Reading a constant variable `static final int LIMIT = 5` | Usually **does not** trigger initialization of the class declaring the constant | The compiler may inline compile-time constants |
| Specific reflective operations triggering initialization | Depends on the API | Read the method's Javadoc; do not assume all reflection behaves identically |

An example for testing laziness:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName("demo.Broken", false, loader);
System.out.println("loaded class=" + type.getName());

// Up to this point, Broken.<clinit> is not yet required to run.
// If called with initialize=true from here, it may throw
// ExceptionInInitializerError when property lab.fail=true.
```

This is **an illustrative snippet inside a method that handles `ClassNotFoundException`**. Do not use it as a standalone file; the labs above already provide complete files and verified stdout.

### Do Not Confuse Load, Resolve, and Initialize

- `loadClass`: locates the class and may delegate to the parent; returning a `Class<?>` does not mean the initializer has run.
- `resolveClass`: used for linking per the ClassLoader API; not synonymous with static initialization.
- `initialize=true` in `Class.forName`: requires class initialization when needed.
- `new`: requires initializing the class before constructing the appropriate instance.

A class can **be loaded** yet fail to **initialize**. That is precisely Lab B.

## 9. What Exactly Does the JVM Do When a Static Initializer Throws an Error?

According to JLS 17 `12.4.2`, for a class `C`:

1. The JVM synchronizes around the **initialization lock** associated with `C`.
2. If `C` is already initialized, return successfully.
3. If `C` is currently being initialized by another thread, the current thread may have to wait.
4. If `C` is already in the **erroneous** state, the JVM **throws `NoClassDefFoundError`** instead of attempting to initialize it again.
5. Otherwise, the JVM prepares to perform any required superclass/superinterfaces initialization.
6. The JVM runs the static fields/static blocks of `C` in their respective textual order.
7. If it completes normally, mark the class **fully initialized**.
8. If the initializer completes abnormally, mark the class **erroneous**, wake up waiting threads, and throw the appropriate error.

### Why Does ExceptionInInitializerError Occur the First Time?

When the initializer throws a `Throwable E`:

- If `E` is **not** an `Error` or a subclass of `Error`, the JVM wraps E in an `ExceptionInInitializerError` when eligible under procedure `12.4.2`.
- If `E` **is already an Error**, the JVM may throw that Error itself on the first failure, **without being required to wrap it in `ExceptionInInitializerError`**.
- Once the class is erroneous, subsequent initialization requests lead to `NoClassDefFoundError`.

Therefore, the statement "the first static initializer error is **always** `ExceptionInInitializerError`" is **false**. The demo uses `IllegalStateException` to provide a clear, easy-to-learn case.

### What If Multiple Threads Actively Use the Class at the Same Time?

Initialization is coordinated and synchronized by the JVM per class; two threads are not allowed to run the same `<clinit>` concurrently and independently. If one thread is initializing the class, another thread may wait. If initialization fails, subsequent threads may encounter the erroneous class and `NoClassDefFoundError`.

**Do not write an application that retries `Broken.number` in a loop hoping the class will re-initialize itself.** Once the state is erroneous, retrying the same runtime class does not fix the underlying cause.

## 10. Constructor Exceptions Differ from Class Initializer Exceptions

Example of a constructor throwing an error:

```java
public final class FailingObject {
    public FailingObject() {
        throw new IllegalStateException("constructor failed");
    }
}
```

This is a compilable Java class, though it **does not contain a `main` method**. If the class initialization of `FailingObject` succeeds normally, having **an object's** constructor throw `IllegalStateException` **does not by itself mark the entire class erroneous**.

Distinguish clearly between:

- Broken `static { throw ... }` / static field initializer → **class initialization** error (can mark the class erroneous).
- Broken instance field initializer or constructor → **instance construction** error; does not automatically make the class erroneous.
- Broken superclass static initializer → the class being initialized may be affected according to the hierarchy initialization procedure.
- Normal method throwing an exception → does not by itself make the class erroneous.

Do not simply look at "the stack trace occurred during `new Broken()`" and conclude it is a constructor error. `new` can trigger class initialization **before** the constructor runs.

## 11. Why Changing a Property Mid-Run Cannot Fix an Erroneous Class

In Lab B, `lab.fail` is read inside `<clinit>`. Suppose within the same JVM we run:

```java
try {
    int ignored = Broken.number;
} catch (LinkageError error) {
    System.setProperty("lab.fail", "false");
}

int value = Broken.number; // May still throw NoClassDefFoundError.
```

This is **an illustrative snippet inside a `demo` class that has imported/can see `Broken`**, not a standalone runnable file. The property has been updated, yet **the static initialization of the same `Class<?>` does not re-run automatically**.

Appropriate ways to handle this:

- **Standard applications:** fix the configuration/dependency/initializer and restart the JVM.
- **Plugins with their own loader:** stop the plugin, clean up all listeners/threads/TCCL/instances, fix the artifact or configuration, create a **new class loader** to obtain a new runtime class definition, and then re-initialize according to the proper lifecycle.
- **Not possible:** call `Class.forName` repeatedly expecting an erroneous `Class<?>` to reset itself.
- **Should not do:** try calling `System.gc()` or `URLClassLoader.close()` and then reuse the class in the **same loader that defined it**. Closing does not repair the class initialization state.

Creating a new loader **does not guarantee** success if the underlying cause remains (for example, DB config, missing secret, broken native library); it only provides an opportunity for a new class definition to be initialized with the proper state.

## 12. Practice Distinguishing ClassNotFoundException from NoClassDefFoundError

A common question: "Why does calling `Class.forName` produce `ClassNotFoundException`, while calling a method produces `NoClassDefFoundError`?"

Consider:

```java
Class.forName("lib.Helper");
```

This is **an illustrative snippet** inside a method that declares/handles `ClassNotFoundException`. Because the API is asked to look up a class by **string name**, if the loader cannot find the class, it typically throws the **checked `ClassNotFoundException`** directly.

Conversely:

```java
System.out.println(lib.Helper.message());
```

This is **an illustrative snippet**, assuming the caller was already compiled against `lib.Helper`. The JVM resolves the symbolic reference in bytecode to perform the call; if the class definition is missing, the VM may throw **`NoClassDefFoundError`**.

Visualization:

```text
API lookup by name:
    Class.forName("lib.Helper")
          |
          +-- loader cannot find it
          |
          +-- ClassNotFoundException (checked)

Bytecode reference:
    invokestatic lib/Helper.message:()Ljava/lang/String;
          |
          +-- JVM needs the class during linking
          +-- definition cannot be found
          |
          +-- NoClassDefFoundError (LinkageError)
              [cause may be ClassNotFoundException]
```

**Both can still originate from an incorrect classpath**, but the throwable type depends on the **call path/API** and the **point at which the JVM is searching/resolving**. Do not treat the two exception/error types as synonyms.

## 13. Classpath Root: Properly Fixing the Lab A Error

In Lab A, the file is located at:

```text
lib-classes/
└── lib/
    └── Helper.class
```

For the binary name `lib.Helper`, **the classpath root must be the `lib-classes` directory**, not `lib-classes/lib`. The JVM resolves the package path `lib/Helper.class` relative to each root.

**Incorrect:**

```bash
java -cp lib-classes/lib app.MissingDemo
```

The command above is also missing the output of `app.MissingDemo`; even if the app root is added, `lib-classes/lib` is still **not the right root** for `lib.Helper`.

**Correct with both directories:**

```bash
# Linux/macOS
java -cp "app-classes:lib-classes" app.MissingDemo
```

```powershell
# Windows PowerShell
java -cp 'app-classes;lib-classes' app.MissingDemo
```

If the dependency is packaged in a JAR, the archive root must contain the `lib/Helper.class` entry, and the JAR must be placed on the appropriate runtime classpath:

```bash
jar --create --file helper.jar -C lib-classes .
```

Then, for example, on Linux/macOS:

```bash
java -cp "app-classes:helper.jar" app.MissingDemo
```

On Windows, replace `:` with `;`.

**Tip:** adding a JAR/path to the **compile classpath** does not automatically add it to the **runtime classpath**. Similarly, the fact that an IDE sees a dependency does not prove that the script/Docker/server/plugin loader will see that dependency at runtime.

## 14. When the Class Is Actually Present, Yet the JVM Still Reports NoClassDefFoundError

Beyond static initialization failure, several other causes need to be checked:

| Scenario | Mechanism | Diagnostic Approach |
| --- | --- | --- |
| The `Helper.class` file is on disk, but placed under the wrong **classpath root** | The loader cannot resolve it via the expected binary name path | Compare the package against the output root |
| The JAR contains the class, but is not on the runtime `-cp` | Compilation and deployment are out of sync | Print the runtime classpath and JAR list |
| Plugin class exists only in a child loader | Parent loader does not search downward into child loaders | Check the defining/initiating loader, and TCCL if the API uses TCCL |
| The JAR is on the module path, but the module has not been resolved | Observable does not mean resolved | Check `--module-path`, `--add-modules`, and the JPMS dependency graph |
| The class depends on **another dependency** that is missing | The first class can load, and the secondary dependency is only missing during linking | Read the **class name in the message/cause** and stack trace |
| The class became erroneous due to a static block failure | Subsequent active use throws NCDFE even though `.class` exists | Look for the earlier `ExceptionInInitializerError` / original initializer error |
| Binary name/package changed, but stale files remain | Caller bytecode requires a different name | `javap`, check binary names and build artifacts |
| Stale JAR/class files shadowed by a parent-loader version | The JVM loads a different API than the artifact being inspected | `Class.getClassLoader()`, CodeSource, `-Xlog:class+load=info` |
| Code was compiled against an incompatible API version | Broken member reference | May be `NoSuchMethodError` / `NoSuchFieldError`, not necessarily NCDFE |
| Corrupted class file or unsupported version | Verification/format/version error | `ClassFormatError` / `UnsupportedClassVersionError` may appear |

Do not fix this by adding random JARs in bulk. You need to identify **the class name to be resolved** and **which loader is performing the lookup**.

## 15. Diagnosing with javap, CodeSource, and Class Loading Logs

### 15.1 Inspecting Bytecode References

Lab A:

```bash
javap -classpath app-classes -c -verbose app.MissingDemo
```

Look for `lib/Helper` and `invokestatic`. This confirms that the caller binary **actually depends on** `lib.Helper`, even if the current source code may have changed.

### 15.2 Verifying Which Loader Can Find the Runtime Class

An illustrative helper:

```java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

System.out.println("TCCL=" + loader);
System.out.println("resource=" +
        loader.getResource("lib/Helper.class"));
```

This is **an illustrative snippet inside a method**, assuming the TCCL is non-null. A non-null resource URL **only proves the loader can locate that resource**, which is not enough to conclude the class will verify/link/initialize successfully; module access and class loading policy may differ from the resource lookup path.

If the class loads successfully, check:

```java
Class<?> type = lib.Helper.class;
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());

java.security.ProtectionDomain pd = type.getProtectionDomain();
java.security.CodeSource cs =
        (pd == null ? null : pd.getCodeSource());

System.out.println("source="
        + (cs == null ? "<unknown>" : cs.getLocation()));
```

This is **an illustrative snippet**, assuming the compiled code has `lib.Helper`. CodeSource may be null; with a custom loader, the source may differ from the runtime classpath printed by the host. Do not use this snippet when the class has not loaded and then ignore the original error; in that situation, class loading logs/deployment paths are more useful.

### 15.3 HotSpot Class Load Logs

```bash
java -Xlog:class+load=info -cp "app-classes:lib-classes" app.MissingDemo
```

The line above is for Linux/macOS; on Windows, replace `:` with `;`. HotSpot can print many load events, helping identify which class was loaded and from what source if log information is present. However, `class+load` logs do not by themselves point out **the values inside the static initializer** causing the error. For Lab B, the stack trace pointing to `demo.Broken.<clinit>` and the cause `IllegalStateException` are more important.

### 15.4 Do Not Treat Every Post-Failure Log as the Root Cause

On a server, a single initialization failure at startup can cause **hundreds of subsequent requests** to log `NoClassDefFoundError: Could not initialize class ...`. If you only read the log at the 100th request, you are only seeing the consequence. Look for the **first time** the static initializer ran and the real exception from configuration, resources, network, a null value, or service discovery.

Sometimes a class's static initializer calls another class whose own initialization fails. In that case, the cause chain spans multiple classes; you need to trace back to the original `<clinit>` frame and initial exception.

## 16. Where Do Real-World Static Initialization Errors Come From?

In the experiment we intentionally threw `IllegalStateException("boom")`. In real applications, a static initializer can fail due to:

- `NullPointerException` when reading configuration that has not been set.
- `IllegalArgumentException` from parsing an invalid path/URL/charset/timezone.
- `ExceptionInInitializerError` from a dependency whose static initialization failed earlier.
- `SecurityException` or `IllegalAccessError` when an operation is restricted by runtime/module access.
- `UnsatisfiedLinkError` when loading a native library inside a static block.
- `ServiceConfigurationError` when the initializer uses `ServiceLoader` with broken provider metadata.
- `NoClassDefFoundError` because another dependency is missing right when the initializer calls it.
- `OutOfMemoryError` or insufficient system resources.
- Static initialization ordering across multiple classes leading to an unready state or complex dependency cycles.

Therefore, a class initialization failure **does not necessarily start with `IllegalStateException`**. Lab B simply chose this error to clearly illustrate the wrapping rule.

**Good design:** limit I/O, network, database, native loading, or service discovery calls that can fail inside a static initializer if they depend on changing operational state. Prefer an **explicit initialization method**, factory, or `start()` lifecycle that returns controlled errors and supports application-level retry/rollback.

### Anti-pattern Example

```java
public final class GlobalClient {
    static final Connection CONNECTION = openDatabaseOrThrow();

    private GlobalClient() { }

    static Connection connection() {
        return CONNECTION;
    }

    // openDatabaseOrThrow and Connection are illustrative elements.
}
```

This is **pseudocode**, not a standalone file: `Connection`/`openDatabaseOrThrow` are undeclared. If the database is not ready at class initialization time, the class can fall into a permanently erroneous state in that runtime class. Replacing this with explicit lifecycle/DI/resource management allows error reporting and retries according to application policy.

## 17. Different Outcomes Between a Class Literal, Static Field, and Static Constant

A side experiment worth understanding:

```java
package demo;

public class ConstantExample {
    public static final int LIMIT = 10;
    public static int dynamicValue = init();

    private static int init() {
        System.out.println("initializing ConstantExample");
        return 20;
    }
}
```

This is a **standalone compilable class**, without `main` yet.

When client code compiled with the same API accesses `ConstantExample.LIMIT`, the compiler can **inline** the number `10`. Merely reading that constant variable **does not force class initialization**. However, reading `dynamicValue` triggers initialization and can print `initializing ConstantExample`.

Do not use a `static final int` compile-time constant as a trigger when you want to test `<clinit>`. In Lab B, we use **`public static int number`**, ensuring that the read operation is an active use.

Also do not assume that every `static final` is a compile-time constant: `static final Object X = new Object()` is not a constant variable in the JLS sense.

## 18. Relationship Between Initialization Errors, ClassLoaders, and Hot Reload

According to the JVMS, runtime class identity includes **the binary name and the defining class loader**. Two different custom classloaders can independently define two copies of `demo.Broken` with the same name.

```text
OldPluginLoader
    |
    +-- demo.Broken (class definition A)
           +-- initialization failed
           +-- state: ERRONEOUS

NewPluginLoader
    |
    +-- demo.Broken (class definition B)
           +-- independent class initialization state
           +-- may succeed after config fix
```

This is a conceptual diagram, not a VM API for directly reading `ERRONEOUS`. A new loader **only creates a new opportunity** if it actually defines the new class itself, rather than delegating to the faulty class in the parent loader.

In a plugin host:

1. **Shared API** resides in the parent loader so the host/plugin agree on interface identity.
2. **Plugin implementation** is defined by its own custom loader.
3. If an implementation class is erroneous, stop/clean up the plugin according to its lifecycle.
4. Avoid host static caches, TCCL, threads, or listeners retaining the old class/loader when undeploying.
5. Create a new loader pointing to the fixed artifact/config and reinitialize the plugin.
6. Verify that the new loader actually defines `demo.Broken`; if the parent has already defined a class with the same name, delegation may still return the old definition.
7. Do not treat `URLClassLoader.close()` as "resetting class initialization"; closing only manages URL search paths/JAR handles.

**Do not try to fix initialization errors by reflecting into private fields or using `Unsafe` to force the class to re-run `<clinit>`.** There is no public Java SE contract guaranteeing such an operation is safe or semantically valid.

## 19. Module Path and the "Class Is on Disk but Cannot Be Loaded" Problem

Since Java 9, code can reside on the classpath (unnamed module) or the module path (named/automatic module). A JAR being present on `--module-path` only makes it **observable**; the module must also be **resolved** in the graph, and class access is also subject to exports/opens/readability.

For example, a classpath application trying to use a class in an unresolved named module may need `--add-modules module.name` or the appropriate dependency relationship. However, **do not treat `--add-modules` as a universal solution for every NoClassDefFoundError**. Identify which loader loaded the class, which module contains the class, whether the module graph is resolved, and whether the root cause is actually discovery or erroneous initialization.

For Labs A and B in this article, **only the classpath is used** and there is no `module-info.java`, making it easy to separate the two root causes without mixing in JPMS resolution.

## 20. Additional Tests Worth Trying

### Exercise 1 — Deleting the App Class Instead of the Lib Class

Keep `lib-classes` but run:

```bash
java -cp lib-classes app.MissingDemo
```

The launcher will **fail to find the main class `app.MissingDemo`**. A launcher message such as "Could not find or load main class ..." differs from the case where main has already started running and the JVM lacks the `lib.Helper` class. Do not assert that every kind of main startup failure must carry the same throwable as Lab A.

### Exercise 2 — Fixing the Runtime Classpath of Lab A

Add `lib-classes` back **without recompiling the client**. The verified result is `app started` then `Helper available`. That is because the root cause is the deployment path, not the source API.

### Exercise 3 — Changing the Lab B Property Value Before Startup

Run:

```bash
java -Dlab.fail=false -cp init-classes demo.InitDemo
```

Predict the output before looking: the static block runs **once**, and both reads of the static field print `42`. This is the control case that has already been run and verified.

### Exercise 4 — Changing the Property After the First Failure in the Same JVM

Modify `InitDemo` so that in the first `catch` it calls `System.setProperty("lab.fail", "false")` and then tries reading `Broken.number` again. According to the JLS, it still does not automatically reinitialize the erroneous class definition. Compare this with starting a new JVM and explain the difference.

### Exercise 5 — Replacing IllegalStateException with an Error

In `Broken`, replace the throw in the static initializer with `throw new AssertionError("boom");` in a runtime branch. Prediction:

- On the first attempt, the initializer terminates with a subclass of `Error`, so `AssertionError` itself may be thrown, not necessarily `ExceptionInInitializerError`.
- The next active use of the erroneous class leads to `NoClassDefFoundError`.

**This is a prediction exercise based on the JLS**, not stdout from the two executed labs. When writing code to observe it, `InitDemo`'s `catch (LinkageError)` does not catch `AssertionError` because `AssertionError` is on a different `Error` branch; if you want to demonstrate it, use a harness with `catch (Throwable)` only in the lab and absolutely never mask similar errors in production.

### Exercise 6 — A Failing Constructor Does Not Make the Class Erroneous

Create a class whose constructor throws `IllegalArgumentException`. Both calls to the constructor can throw an exception from the new constructor invocation; the class's static initialization can still have succeeded. Compare with Lab B to understand how per-class state differs from per-instance state.

### Exercise 7 — Checking the First Failure in Multi-Threaded Logs

Run multiple threads that simultaneously actively use a class whose static block sleeps briefly and then throws an error. Avoid writing tests that depend on scheduling order; what should be observed is **one initialization attempt** synchronized at the class level, and subsequent callers seeing the erroneous state. Read JLS `12.4.2` to understand the lock/wait rules.

## 21. Quick Diagnostic Table for Real-World Deployments

| Symptom | First Question | How to Fix |
| --- | --- | --- |
| `NoClassDefFoundError: pkg/Type`, cause `ClassNotFoundException` | Are the JAR/runtime roots right? Does the loader see that class? | Fix the runtime classpath/module path/delegation |
| `NoClassDefFoundError: Could not initialize class pkg.Type` | What failed during the first initialization? Is there a `<clinit>` frame? | Fix the static initializer/config, and establish a valid new initialization |
| `ExceptionInInitializerError` | Which static field/block threw the original exception? | Read `getCause()` and the stack trace, and fix the cause |
| `ClassNotFoundException` from `Class.forName` | Are the passed name/loader right? | Choose the appropriate loader, and verify the binary name |
| `NoSuchMethodError` | Which API did the caller compile against, and which API is loaded at runtime? | Ensure binary compatibility/version alignment |
| `NoSuchFieldError` | Does the field name + descriptor still exist? | Compare `javap` between caller and runtime |
| `UnsupportedClassVersionError` | Was the bytecode compiled for a higher JDK than runtime? | Choose the appropriate JDK/build target |
| `IllegalAccessError` | Does the member exist, and are access/module exports compatible? | Fix access/module graph, not just adding classpath |
| `UnsatisfiedLinkError` inside `<clinit>` | Native library/ABI/path and loader ownership? | Fix the native dependency, and inspect the first error |
| Error occurs only in a plugin | Which parent/child loader does the plugin use? Which shared API version? | Check loader identity, artifact, and lifecycle |
| Error disappears after restart but recurs when startup config is wrong | Static initializer runs early before config | Order initialization/config properly or switch to an explicit lifecycle |
| Many NCDFE errors for the same class after one EIIE error | The class is already erroneous; later requests suffer the consequence | Find the first exception, fix the root cause, and restart/redeploy |

## 22. Ordered Diagnostic Checklist

1. **Record the full throwable and cause chain.** Do not just copy the `NoClassDefFoundError` line.
2. **Identify the requested class name.** Is it `lib/Helper`, `demo.Broken`, or another dependency in the cause?
3. **Ask whether the main class has already started running.** The launcher failing to find the main class differs from the JVM missing a dependency along a code path.
4. **Check whether the class is in the runtime output/JAR.** `jar --list` and the filesystem path.
5. **Compare the compile and runtime classpaths.** `javac -cp` does not automatically carry over to `java -cp`.
6. **Determine the classpath root from the package.** `lib.Helper` requires the `lib/Helper.class` entry relative to the root.
7. **Identify the specific loader.** App loader, plugin loader, which API's TCCL, or which JPMS layer?
8. **Verify the code source and duplicate JARs** when multiple versions share the same class name.
9. **If `<clinit>` appears, read the first failure.** `NullPointerException`, config, native, SPI, or missing dependency?
10. **If the class is erroneous, do not retry the same class indefinitely.** Fix the root cause and use a new JVM or appropriate class definition.
11. **If it is a plugin, stop and clean up before reloading.** Do not leave TCCL/tasks/caches pointing to the old loader.
12. **Use `javap` to inspect bytecode references**, especially when the source differs from the artifact.
13. **Re-run both control comparisons.** Complete vs. missing dependency; failing initializer vs. succeeding initializer.
14. **Add an integration test using the real runtime artifact**, rather than relying solely on IDE/compile-time tests.
15. **Inspect logs starting from startup**, not just the Nth error after the service has been running for a long time.

## 23. Self-Check Questions with Answers

**1.** Why does Lab A compile cleanly yet still fail at runtime?

**Answer:** `javac` sees `lib.Helper` from `lib-classes` at compile time, but `java -cp app-classes` cannot see the dependency when the symbolic reference needs to be resolved.

**2.** In Lab A, why is `app started` printed before the error is reported?

**Answer:** The JVM was able to load/run the main class; the error only occurs when the code path actually calls `Helper.message()` and requires `lib.Helper`.

**3.** Why does Lab B produce `ExceptionInInitializerError` followed by `NoClassDefFoundError`?

**Answer:** The first access to `Broken.number` triggers the static initializer, which throws `IllegalStateException` (wrapped by the JVM in EIIE). The class transitions to erroneous; on the next attempt, the JLS specifies not to retry and throws NCDFE.

**4.** Why does `Broken.class.getName()` not print `<clinit> entered`?

**Answer:** A class literal does not by itself require class initialization. `Broken.number` is an actual active use.

**5.** Can you call `System.setProperty("lab.fail","false")` after EIIE and then read `Broken.number` successfully within the same definition?

**Answer:** No, according to the JLS for a class that is already erroneous; you must fix the cause and create a new runtime class definition or restart appropriately.

**6.** How do `ClassNotFoundException` and `NoClassDefFoundError` differ in the hierarchy?

**Answer:** CNFE is a checked `Exception`; NCDFE is a `LinkageError`. They appear in different APIs/resolution paths even though both can be caused by a missing class.

**7.** If a static initializer directly throws `AssertionError`, does EIIE always occur on the first attempt?

**Answer:** No. EIIE wrapping applies when the thrown E is not an Error/subclass; `AssertionError` can be thrown directly.

**8.** If only a constructor throws an exception, does the class automatically become erroneous?

**Answer:** Not automatically. A constructor error is an instance construction failure; class initialization may have already completed.

**9.** Does `NoClassDefFoundError: Could not initialize class ...` mean the JVM could not read the class file?

**Answer:** Not necessarily; usually the class was already found/loaded, but initialization failed earlier. You need to look for the first `<clinit>` failure.

**10.** Why might replacing a plugin JAR in the same class loader fail to fix an initialization error?

**Answer:** The runtime class definition has already been defined and marked erroneous; the loader will not automatically redefine a class with the same name. A new deployment/loader is needed along with cleanup and a root-cause fix.

**11.** Why should you avoid putting network connection setup inside a static initializer?

**Answer:** A transient error at startup can turn the class erroneous with no automatic retry like a service lifecycle; managing explicit init/close is easier to control.

**12.** If the current source no longer imports `lib.Helper` but the deployed bytecode still references it, what should you inspect?

**Answer:** `javap -c -verbose` on the **deployed caller.class** and build artifacts; the IDE source is not proof of the bytecode actually running.

## Conclusion

**`NoClassDefFoundError` does not solely mean "missing `.class` on disk".** It can occur when the JVM cannot find a class needed for linking (**Lab A**), or when the JVM requires initializing a class again that previously failed and is in the **erroneous** state (**Lab B**).

Proper handling must be based on **the first failure + cause + the step the JVM is executing**:

- **Missing class at runtime:** fix the runtime dependency/classpath/module/loader visibility.
- **Static initializer failure:** fix the root cause in `<clinit>`/config, and then use a valid initialization with a new JVM/class definition; do not retry the same erroneous class indefinitely.
- **Other API version/access errors:** verify the exact throwable, bytecode, and defining loader before applying a fix.

When practicing, keep **two runnable control cases**: a runtime with/without the dependency, and a JVM with/without the property causing initializer failure. Combining them with JLS `12.4.2` will help you accurately interpret the trickiest `NoClassDefFoundError` issues in servers and plugin systems.

**Official Java SE 17 Documentation:**

- [`NoClassDefFoundError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html) — the class definition can no longer be found when needed by the JVM/loader.
- [`ClassNotFoundException` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html) — checked exception when looking up a class by name.
- [`ExceptionInInitializerError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html) — error occurring inside a static initializer.
- [JLS 17 §12.4.1 — When Initialization Occurs](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1) — active use scenarios.
- [JLS 17 §12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2) — initialized/erroneous states, EIIE wrapping, and subsequent NCDFE.
- [JVMS 17 §5 — Loading, Linking, and Initializing](https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-5.html) — symbolic resolution and class loading.
- [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — `loadClass` and delegation.
