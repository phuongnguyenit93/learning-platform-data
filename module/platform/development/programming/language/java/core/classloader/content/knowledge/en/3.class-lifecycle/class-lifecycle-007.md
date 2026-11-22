# Eager Resolution, Lazy Resolution, and When Errors Appear in the JVM

> **Topic:** Java Core → ClassLoader → Class Lifecycle. This lesson distinguishes between when the JVM resolves a symbolic reference and when a linkage error is thrown to the program. The experiments use Java 17+ and can be verified on OpenJDK 21.

## 1. Problem: The Program Starts and Only Later Reports a Missing Method

Suppose we compile `App.class` against a version of the `Api` library that has the `message()` method. After compilation, the library is replaced with a version that no longer has that method, while `App.class` remains unchanged.

Why can `main` print several lines before `NoSuchMethodError` appears at the `Api.message()` call? Is the JVM required to wait until the call itself to look up the method?

The answer has two parts:

- The JVM is allowed to perform **eager resolution** of many symbolic references or **lazy resolution** when needed. Internal strategies can vary across JVMs and situations.
- Even if it detects an error early internally, the JVM must still ensure that the error only becomes **observable at a point in the program where an action is taken that might, directly or indirectly, require linkage to the failing entity**. You cannot conclude whether the strategy is eager or lazy solely from the lines of output that appear before the error.

That is the boundary between **when resolution is performed** and **when the error is exposed to the program**.

## 2. Placing Resolution in the Class Lifecycle

A class file records **symbolic references** in the run-time constant pool, such as `Methodref demo/Api.message:()Ljava/lang/String;`. **Resolution** uses the name, descriptor, and loader to find the right runtime class or member. **Linking** consists of verification, preparation, and resolution; verification and preparation must complete before initialization, whereas resolution can come later. Building on that foundation, this lesson focuses on **the resolution schedule and the program point where errors are observed**, without repeating the member lookup algorithm.

## 3. Eager Resolution and Lazy Resolution

### Eager resolution

The JVM may resolve many symbolic references when verifying/linking a class, before the bytecode directly uses them. This can help prepare metadata and detect incompatible dependencies early internally.

### Lazy resolution

The JVM may leave each symbolic reference unresolved until an instruction uses it, such as the first execution of `invokestatic` on a method or `getstatic` on a field. This avoids unnecessary work for unused code.

### What Exactly Does the JVM Guarantee?

JVMS 5.4 and 5.4.3 allow these strategies **as long as they do not change observable semantics**. Eager/lazy is an implementation strategy; Java has no requirement that HotSpot or every JVM must resolve every reference at the same point in time.

| Aspect | Guaranteed? |
| --- | --- |
| Class is loaded before linking | Yes. |
| Verification and preparation complete before initialization | Yes. |
| All symbolic references are resolved before initialization | No. |
| The JVM may eagerly resolve ordinary symbolic references | Yes, within JVMS limits. |
| A linking error is thrown at the point of an action that might directly/indirectly require the relevant linking | Yes. |
| Observing an error at the call site proves the JVM internally uses lazy resolution | No. |

**Important exception:** Certain kinds of references have special rules. A *dynamically-computed constant* must not be resolved arbitrarily before an `ldc`/`ldc_w`/`ldc2_w` instruction needs it or before a bootstrap scenario uses it as a static argument as specified by the JVMS; `invokedynamic` dynamic call sites are also constrained by bootstrap rules. Therefore, you should not claim that “the JVM is allowed to resolve any constant pool entry immediately at load time”.

## 4. Two Points in Time That Must Be Kept Separate

Consider `App.class` referencing `Api.message()`, while the `Api.class` actually running no longer has the corresponding method:

```text
App.class (compiled with Api v1)
      |
      | contains Methodref demo/Api.message:()String
      v
JVM loads App
      |
      +--> JVM may eagerly resolve and detect missing method internally
      |
      +--> main: println("started")
      |
      +--> branch not calling the method: may finish normally
      |
      '--> branch executing invokestatic Api.message()
                      |
                      '--> NoSuchMethodError is observed
                           at the action using the reference
```

On a JVM with a lazy implementation, the method check may happen at the very instruction that uses it. On an eager JVM, the problem may be detected earlier, yet throwing it to the program must still stay within JVMS constraints.

**This is a rule about observable behavior**, not a promise that every error will be thrown only on one exact source line. Linking can happen indirectly; verification, loading of a superclass/interface, or another active operation can cause the program to see an error earlier than predicted from the source code.

### Is the Resolution Result Cached?

According to JVMS 5.4.3, for ordinary reference types:

- If resolution succeeds, subsequent attempts to resolve the **same symbolic reference** continue to succeed with the same entity.
- If the first attempt fails, subsequent attempts for the **same reference** will fail with the same error.
- There are specific details for `invokedynamic`: call site resolution is bound to each instruction using the reference, so the caching rules of ordinary method references should not be generalized to all dynamic call sites.

Consequently, swapping a JAR on disk while the JVM is running is not a mechanism that automatically fixes a symbolic reference whose resolution has already failed.

## 5. Practical Experiment: Java Compiled with API v1 but Run with API v2

This experiment uses a precompiled caller, keeps the caller unchanged, and replaces the library bytecode at runtime.

Create the files with the following structure:

```text
src-v1/demo/Api.java
src-v2/demo/Api.java
src-app/demo/App.java
```

**File `src-v1/demo/Api.java` — version with the method used at compile time:**

```java
package demo;

public class Api {
    public static String message() {
        return "v1";
    }
}
```

**File `src-v2/demo/Api.java` — replacement version without the `message` method:**

```java
package demo;

public class Api {
    public static String other() {
        return "v2";
    }
}
```

**File `src-app/demo/App.java` — caller that is not recompiled:**

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println("1. App started");

        if (args.length == 0) {
            System.out.println("2. No API call");
            return;
        }

        System.out.println("2. About to invoke Api.message()");
        try {
            call();
        } catch (NoSuchMethodError e) {
            System.out.println("3. Caught NoSuchMethodError");
        }
    }

    static void call() {
        System.out.println(Api.message());
    }
}
```

Compile in order; `App` is compiled with v1, and then at runtime only v2 is placed before `App` on the classpath:

```bash
javac -d build/v1 src-v1/demo/Api.java
javac -cp build/v1 -d build/app src-app/demo/App.java
javac -d build/v2 src-v2/demo/Api.java
java -cp "build/v2:build/app" demo.App
java -cp "build/v2:build/app" demo.App go
```

On Linux/macOS, the classpath separator is `:`. On Windows PowerShell or CMD, the two corresponding run commands are:

```powershell
java -cp "build\v2;build\app" demo.App
java -cp "build\v2;build\app" demo.App go
```

**Output of the command without arguments:**

```text
1. App started
2. No API call
```

**Output of the command with the `go` argument:**

```text
1. App started
2. About to invoke Api.message()
3. Caught NoSuchMethodError
```

The results were verified by compiling and running on OpenJDK 21. The two branches show that the caller bytecode can survive/run partially even when a method reference is missing. Catching `NoSuchMethodError` in this experiment is for observation; **this is not how to fix dependency errors in a real-world application**.

To inspect the references compiled into the caller:

```bash
javap -v -classpath build/app demo.App
```

In the constant pool, look for the `Methodref` for `demo/Api.message` and the descriptor `()Ljava/lang/String;`. The constant pool index is determined by the compiler, so it does not need to match a specific number.

For comparison:

1. Run the same `App.class` with `Api v1`: `java -cp "build/v1:build/app" demo.App go` → prints `v1` after the `About to invoke...` line, with no `NoSuchMethodError`.
2. Remove `Api.class` completely at runtime: when a symbolic reference to `Api` is needed, you may see `NoClassDefFoundError` due to the missing class.
3. If you change `message()` from a static method to an instance method in v2 while the caller still uses `invokestatic`, you may encounter `IncompatibleClassChangeError`.
4. If you recompile the caller with v2, `javac` reports that `message()` does not exist right at **compile time**. The binary incompatibility experiment only makes sense when the caller keeps its old bytecode.

## 6. Separate Example: A Class Loaded/Linked but Not Yet Initialized

Create a standalone file `InitDemo.java`:

```java
public class InitDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
        static int value = 42;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("before lookup");
        Class.forName(
                "InitDemo$Target",
                false,
                InitDemo.class.getClassLoader()
        );
        System.out.println("after lookup; before active use");
        System.out.println("value=" + Target.value);
    }
}
```

Run:

```bash
javac InitDemo.java
java InitDemo
```

Output:

```text
before lookup
after lookup; before active use
Target initialized
value=42
```

`Class.forName(name, false, loader)` requests finding/loading and linking the class without requesting initialization through that call. When the action of reading `Target.value` is executed, the JVM initializes `Target` and prints the message.

**Limitation of this experiment:** It illustrates the boundary between loading/linking and initialization; it **does not prove** whether all symbolic references of `Target` have been resolved or not. A linked/initialized class can still carry unused symbolic references.

Commonly confused APIs:

| API | Meaning | Does Not Guarantee |
| --- | --- | --- |
| `ClassLoader.loadClass(name)` | Requests the loader to load a class by its binary name; the default overload does not request initialization. | That the class's entire constant pool is resolved. |
| `Class.forName(name, false, loader)` | Finds/loads and links the class without requesting initialization. | That it only reads bytes and never verifies/links. |
| `Class.forName(name)` | Finds and initializes the class according to the API rules. | That every reference in the class is eagerly resolved. |
| `ClassLoader.resolveClass(clazz)` | Mechanism used by a loader to link an already-loaded class. | That it is a public API to force resolving every reference in every JVM. |

## 7. Common Misconceptions

**“Seeing an error on the call line means the JVM definitely uses lazy resolution.”** False. The JVM may eagerly resolve and defer *throwing the error to the program* until a valid usage action.

**“If the branch containing the failing call is not executed, the entire process is guaranteed to succeed.”** There is no general guarantee: verification, superclass/interface loading, or an indirect action may uncover other errors and require linking. In the `App` experiment above, the branch not calling the method runs normally; do not treat that as a rule for every error or class.

**“If `Class.forName` succeeds, all method and field dependencies are valid.”** Incorrect. Finding and linking a class is not a guarantee that all unused symbolic references have been resolved successfully.

**“An error appearing after startup must be a resolution error.”** Incorrect: initialization, reflection, verifier, runtime dispatch, service loader, or application logic errors have independent causes.

**“You can delete or modify a running JAR so the JVM will resolve again.”** There is no such guarantee. Already-defined classes and resolution results have semantics tied to the runtime loader. Replacing dependencies requires redeploying, creating a new class loader, or using an appropriate instrumentation mechanism; do not fix it through arbitrary operations on the JAR.

**“If the source compiles, it will link at runtime.”** Incorrect when the caller's bytecode and the dependency version at runtime differ. Binary compatibility errors often only surface after deployment.

## 8. Debugging Workflow for Late-Appearing Errors

1. Record the **exception/error type, message, stack trace, and any `Caused by`**; identify the first instruction/operation that could directly or indirectly require linking.
2. Compare the **compile-time artifacts** and **runtime artifacts**: classpath, module path, JAR versions, duplicate classes, and the defining class loader.
3. Run `javap -v` on the **caller** to inspect `Class`, `Methodref`, `Fieldref`, descriptors, and opcodes; run `javap` on the runtime class to inspect the actual members.
4. If the error is a missing method/field, check the name, descriptor, static/instance flags, and access. Changing the return type or parameters also changes the descriptor, which can cause a linkage error even when the source looks nearly identical.
5. Separate loading, linking, and initialization: where the class is loaded via `loadClass` or `forName`, where `new`/`invokestatic`/`getstatic` executes, and where static initializers throw errors.
6. Reproduce with two branches—one using the reference and one not—as in the example. Observing when the error appears helps identify the triggering action; **it is not a direct measurement of when the JVM resolves internally**.
7. Fix the actual dependency/version/build/deployment or bytecode issue; do not mask linkage errors with `catch (LinkageError)` and continue serving requests.

On HotSpot, you can enable class loading logs to verify where classes come from:

```bash
java -Xlog:class+load=info -cp "build/v2:build/app" demo.App go
```

Class loading logs are **not** a complete log of symbolic reference resolution. When you need to determine the exact eager/lazy strategy of a JVM, rely on the diagnostic tools appropriate for that version while still distinguishing internal behavior from standard semantics.

## 9. Review Questions

1. **Is every symbolic reference required to be resolved before initialization?** No. Verification and preparation must complete before initialization, whereas resolution may continue afterward.
2. **If the JVM finds a missing method via eager resolution, can it throw the error at any arbitrary time?** No. The JVMS requires the point where the program observes the error to be tied to an action that directly or indirectly requires linkage of the relevant reference.
3. **Why does `App` compile against `Api v1` yet throw `NoSuchMethodError` when run with `Api v2`?** The caller contains a symbolic method reference; at runtime, no method with the matching name/descriptor is found.
4. **What does a successful `Class.forName(name, false, loader)` prove?** That the class was found/loaded/linked according to the API semantics without requesting initialization. It does not prove that all other symbolic references will resolve successfully.
5. **Do a missing class file during `Class.forName` and a missing class referenced by bytecode produce the same kind of error?** Not necessarily: the former typically throws `ClassNotFoundException`, whereas a failed symbolic reference linkage can commonly lead to `NoClassDefFoundError`.
6. **Why can you not use the location of `NoSuchMethodError` in a stack trace to conclude that the JVM uses lazy resolution?** Because eager resolution can also detect the error beforehand, yet throwing the error must align with a valid point of use under the JVMS.

## 10. Authoritative References

- [JVMS 5.3 — Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class loading and runtime class identity.
- [JVMS 5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4): eager/lazy choice, linking errors, and error-throwing constraints.
- [JVMS 5.4.3 — Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3): kinds of symbolic references, and behavior when resolution succeeds/fails.
- [JVMS 5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): initialization conditions and sequence.
- [JLS 12.2–12.4 — Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): the Java Language Specification perspective on class loading, linking, and initialization.
- [Java 17 Class.forName API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): the `initialize` argument and class loader.
