# Distinguishing Compile-Time, Linkage, and Runtime Errors in Java 17

When practicing Java 17, a program can fail during compilation, when the JVM loads and links classes, or while the program is executing. All three are sometimes loosely called "Java errors," yet their **causes, symptoms, and fixes are different**.

This lesson helps you pinpoint which phase a failure occurs in, read error messages accurately, and choose the right next step in a Java 17 environment.

## 1. Three Phases to Distinguish

Consider the basic flow from source code to a running program:

```text
Java source code (.java)
        |
        | javac: syntax parsing, type checking, and language rules
        v
Bytecode (.class)              <-- Compile-time error: valid bytecode cannot be produced
        |
        | java starts the JVM; loads and links required classes
        |   - verification: checks bytecode validity
        |   - preparation: allocates static fields per specification
        |   - resolution: resolves symbolic references to classes/methods/fields
        v
Classes ready for use          <-- Linkage error: bytecode/runtime components are incompatible
        |
        | initializes classes as needed, executes main and methods
        v
Running program                <-- Runtime failure: operations, data, resources, environment...
```

**Important note:** this diagram is a learning model, not a rigid timeline. The JVM can **load classes and resolve references after the program has already started running**. Therefore, a `LinkageError` may surface only when a specific method is called, even though `main` was already running. Classify failures by their **underlying cause**, not solely by when you observe them.

| Criterion | Compile-time error | Linkage error | Runtime failure |
| --- | --- | --- | --- |
| Typical detection phase | `javac` processes source code | JVM loads, verifies, prepares, or resolves class references | Code is already executing and hits an invalid condition or fault |
| Common symptoms | `error: ...`, compilation fails | `java.lang.NoSuchMethodError`, `NoClassDefFoundError`, `UnsupportedClassVersionError` | `ArithmeticException`, `NullPointerException`, `IOException`, `OutOfMemoryError`... |
| Typical causes | Syntax, type, symbol, access, or compile-time constraint error | `.class` files, libraries, or runtime do not match each other | Input data, execution logic, object state, resources, or external services |
| First troubleshooting step | Fix source code or compiler/compile-dependency config | Check runtime version, classpath/module path, JARs, and build consistency | Read the stack trace, root cause, input values, and state at failure time |

In Java, **"linking"** here refers primarily to *JVM linking* under the Java Virtual Machine Specification. Do not confuse it mechanically with linking object files via a C/C++ linker.

## 2. Compile-Time Errors: `javac` Rejects the Source Code

The `javac` compiler checks syntax, types, variable/method/class names, access modifiers, *checked exceptions* rules, and other Java language constraints. When a compile-time error occurs, `javac` exits with a failure status and does not produce a **new valid class file for that code**.

### Example 1: Type Mismatch

Create `CompileErrorDemo.java`:

```java
public class CompileErrorDemo {
    public static void main(String[] args) {
        int quantity = "ten";
        System.out.println(quantity);
    }
}
```

Compile:

```bash
javac CompileErrorDemo.java
```

Typical output:

```text
CompileErrorDemo.java:3: error: incompatible types: String cannot be converted to int
        int quantity = "ten";
                       ^
```

The compiler knows a `String` cannot be directly assigned to an `int` variable. Replace it with `int quantity = 10;` or explicitly parse the string using an appropriate conversion:

```java
int quantity = Integer.parseInt("10");
```

The `parseInt` version **compiles**, yet can still throw `NumberFormatException` at runtime if the string is not a valid integer. This illustrates that **eliminating compile errors does not guarantee zero runtime errors**.

### Example 2: Symbol Not Found

```java
public class MissingSymbolDemo {
    public static void main(String[] args) {
        System.out.println(result);
    }
}
```

`javac` may report:

```text
error: cannot find symbol
    System.out.println(result);
                       ^
  symbol:   variable result
```

The variable `result` has not been declared in an accessible scope. In real projects, `cannot find symbol` can also stem from a misspelled method name, missing import, or **a dependency missing from the compile classpath**.

### Example 3: Unhandled Checked Exception

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class CheckedExceptionDemo {
    public static void main(String[] args) {
        String data = Files.readString(Path.of("settings.txt"));
        System.out.println(data);
    }
}
```

`Files.readString` can throw `IOException`. Because it is a checked exception, the code above must either handle it with `try/catch` or declare `throws IOException`. Otherwise, `javac` reports a compile error such as `unreported exception IOException; must be caught or declared to be thrown`.

A version that compiles:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CheckedExceptionDemo {
    public static void main(String[] args) throws IOException {
        String data = Files.readString(Path.of("settings.txt"));
        System.out.println(data);
    }
}
```

Declaring `throws` **does not guarantee the file exists**. If `settings.txt` is missing or unreadable, the exception can still occur at runtime.

### Quickly Identifying Compile-Time Errors

- The failing step is `javac ...`, or the compile phase of Maven/Gradle/IDE.
- Messages typically show **source filename, line number, column caret, and error description**.
- Fix the source code, source/release settings, or compile classpath.
- When `.class` files remain from an earlier build, **do not mistake leftover files for a successful new compile**. Always check the exit status of the current build command.

## 3. Linkage Errors: The JVM Cannot Use Classes as Bytecode Expects

After `javac` generates bytecode, the JVM must load the classes, verify bytecode format and validity, prepare class structures, and resolve symbolic references to classes, methods, and fields. Failures during these steps belong to the **`java.lang.LinkageError`** family.

A common source of confusion is that **each Java file may have compiled cleanly**, yet the `.class` files or JARs combined in the runtime environment are out of sync.

### Example 4: `NoSuchMethodError` After Replacing a Library Without Recompiling the Caller

First, create two files in the same folder.

`Greeter.java`, initial version:

```java
public class Greeter {
    public static String say() {
        return "Hello";
    }
}
```

`App.java`:

```java
public class App {
    public static void main(String[] args) {
        System.out.println(Greeter.say());
    }
}
```

Compile and run:

```bash
javac Greeter.java App.java
java App
```

Output:

```text
Hello
```

Now suppose someone updates **only `Greeter.java`** to:

```java
public class Greeter {
    public static String greet() {
        return "Hi";
    }
}
```

This time compile only the modified class, **keeping the old `App.class`**:

```bash
javac Greeter.java
java App
```

At runtime, the JVM may report:

```text
Exception in thread "main" java.lang.NoSuchMethodError:
    'java.lang.String Greeter.say()'
    at App.main(App.java:3)
```

What happened?

1. `App.class` was compiled when `Greeter` **still had** the static method `say()`.
2. The new `Greeter.class` removed that method and replaced it with `greet()`.
3. `App.class` still holds a symbolic reference to `Greeter.say(): String`.
4. When the JVM resolves the call, the expected method no longer exists, so it throws `NoSuchMethodError`.

This is a **linkage error at runtime**, even though each `javac` command succeeded individually. If both source files had been recompiled together after the API change, `javac` would have caught the invalid `Greeter.say()` call as a **compile-time error**. The **mismatch between compiled class versions** is what separates the two scenarios.

**How to fix:** align the library version with the application version, update the call to `greet()`, and rebuild both the dependency and application consistently. In projects with multiple JARs, check which class is actually loaded by the class loader and whether an older JAR is inadvertently present.

### Common Linkage Errors

| Error Type | Typical Meaning | First Thing to Check |
| --- | --- | --- |
| `NoSuchMethodError` | Bytecode invokes a method/signature absent from the runtime class | Which JAR version is loaded? Were caller and library built together? |
| `NoSuchFieldError` | Bytecode references a field no longer present in the runtime class | Class versions, field name/type, changed dependencies |
| `NoClassDefFoundError` | The JVM needs a class definition but cannot find/load/complete using it as required; can also follow a class initialization failure | Runtime dependencies, classpath/module path; especially check the message and `Caused by` |
| `IncompatibleClassChangeError` | Binary layout/shape of a class or method changed incompatibly | API changes between two JARs or class files |
| `IllegalAccessError` | Bytecode attempts to access a member no longer accessible at runtime | Changed visibility, class hierarchy, module exports; version mismatch |
| `UnsupportedClassVersionError` | Runtime does not support the loaded class file version | `java -version` and bytecode target used at build time |
| `ClassFormatError` or `VerifyError` | Class file is malformed or violates bytecode verification rules | Which tool generated/transformed the bytecode and whether it matches the runtime |

These error classes extend `LinkageError` directly or indirectly. This table lists useful examples rather than every possible subclass.

### Example 5: Compiled for Java 17, Rejected by an Older Runtime

Suppose an application is compiled into **Java 17** class files, but the deployment environment runs on a Java 11 JVM.

- Java 17 class files have **major version 61**.
- A Java 11 JVM supports class files up to Java 11 (**major version 55**).
- When loading a version 61 class, the Java 11 JVM cannot accept that format and may throw `UnsupportedClassVersionError`.

To check the environment:

```bash
java -version
javac -version
```

To inspect the class file version:

```bash
javap -verbose App.class
```

Look for `major version: 61` if compiled for Java 17. The fix is to run on a runtime supporting that class file version, or recompile targeting a supported version **if your source syntax and APIs allow it**. There is no valid fix by renaming `.class` files or manually patching version bytes.

### Distinguishing `NoClassDefFoundError` and `ClassNotFoundException`

Both names sound like "missing class," yet their meanings in the Java API differ:

- **`NoClassDefFoundError`:** a `LinkageError`; typically thrown when executing bytecode that needs a class previously referenced cleanly at compile time but unavailable to define at runtime. It can also appear as `Could not initialize class ...` when an earlier initialization attempt for that class failed.
- **`ClassNotFoundException`:** a **checked exception**, typically thrown when code explicitly requests a class by name—such as `Class.forName("com.example.Missing")`—and the class loader cannot find it. It is **not** a subclass of `LinkageError`.

Example:

```java
public class LoadByNameDemo {
    public static void main(String[] args) throws ClassNotFoundException {
        Class.forName("example.DoesNotExist");
    }
}
```

This snippet compiles cleanly and throws `ClassNotFoundException` at runtime if the class name does not exist. Therefore, do not jump to `LinkageError` solely because you see the words "ClassNotFound."

### Class Initialization Is Distinct from Class Linking

In the JVM model, **initialization** (running static initializers, computing static field assignments, etc.) is a separate step from **linking**. If a static initializer throws an exception, you may see `ExceptionInInitializerError`; subsequent attempts to use that class may fail with `NoClassDefFoundError: Could not initialize class ...`.

Example:

```java
public class InitializationDemo {
    static final int VALUE = Integer.parseInt("invalid");

    public static void main(String[] args) {
        System.out.println(VALUE);
    }
}
```

This code **compiles validly**. When the JVM initializes the class, `Integer.parseInt("invalid")` throws `NumberFormatException`, typically wrapped in `ExceptionInInitializerError`. Here, fixing the **initialization data and logic** solves the root cause—not swapping JAR versions whenever you see `Error`.

## 4. Runtime Failures: The Program Runs but Hits an Invalid Condition

A program can pass every compiler check and load/link all needed classes, yet still fail due to **data values**, **program state**, **processing logic**, or **external systems**.

### Example 6: Division by Zero

Create `RuntimeErrorDemo.java`:

```java
public class RuntimeErrorDemo {
    public static void main(String[] args) {
        int divisor = Integer.parseInt(args[0]);
        int result = 100 / divisor;
        System.out.println("Result = " + result);
    }
}
```

Compile:

```bash
javac RuntimeErrorDemo.java
```

Run with valid input:

```bash
java RuntimeErrorDemo 5
```

```text
Result = 20
```

Run with divisor `0`:

```bash
java RuntimeErrorDemo 0
```

Typical message:

```text
Exception in thread "main" java.lang.ArithmeticException: / by zero
    at RuntimeErrorDemo.main(RuntimeErrorDemo.java:4)
```

`javac` cannot predict the runtime argument supplied by the user. `ArithmeticException` here is a **runtime exception**, not a compile-time or linkage error.

This code can also fail with:

- `ArrayIndexOutOfBoundsException` when no `args[0]` argument is supplied.
- `NumberFormatException` when an argument such as `abc` is supplied.
- Logic bugs if you skip bounds validation, even if the program occasionally prints output.

A version with clearer input handling:

```java
public class SafeDivisionDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java SafeDivisionDemo <non-zero-integer>");
            return;
        }

        try {
            int divisor = Integer.parseInt(args[0]);
            if (divisor == 0) {
                System.err.println("Divisor must not be 0.");
                return;
            }
            System.out.println("Result = " + (100 / divisor));
        } catch (NumberFormatException e) {
            System.err.println("Argument must be a valid integer.");
        }
    }
}
```

This snippet guards against specific input conditions. It does not mean you should catch every `RuntimeException` everywhere in an application; in real projects, errors should be handled at the layer with enough context to recover, log, or return an appropriate response.

### Other Runtime Failures

| Symptom | Typical Trigger | What to Investigate |
| --- | --- | --- |
| `NullPointerException` | Accessing a method/field through a `null` reference | Which variable is `null`, and why the execution path allowed `null` |
| `IndexOutOfBoundsException` | Index outside the bounds of a list/string/array | Index value and collection/array size |
| `ClassCastException` | Invalid reference cast at runtime | Actual runtime type of the object |
| `NumberFormatException` | String cannot be parsed into a number in the expected format | Input data, validation, and error handling |
| `IOException` | File read/write or I/O operation fails | Path, permissions, file state, data source |
| `OutOfMemoryError` | JVM cannot satisfy a memory allocation request | Memory usage, heap size, retained objects, runtime config |

**Not every runtime failure is a `RuntimeException`.** `IOException` is a checked exception that can actually be thrown at runtime. `OutOfMemoryError` is an `Error`. There are also **logic bugs** where the program produces wrong results without throwing any exception at all.

## 5. Why Can a Successfully Compiled Program Still Fail at Linking or Runtime?

Each of the three checks examines different information:

- **The compiler** inspects source code and the definitions visible **at build time**. It cannot know future input data, network/file state, or the exact set of JARs deployed later.
- **JVM linking** inspects the class definitions actually loaded by class loaders **in the running environment**. If runtime artifacts differ from build artifacts, compiled references may no longer hold.
- **Execution** operates on live data and time-varying state. Failures like division by zero or connection errors depend on runtime circumstances.

For instance, the same call `Greeter.say()` can fail in three distinct ways:

| Scenario | Outcome |
| --- | --- |
| Current `Greeter.java` lacks `say()`, and you compile `App.java` from source | Typically a compile-time error like `cannot find symbol`. |
| Old `App.class` was compiled against `say()`, while runtime loads a new `Greeter.class` without `say()` | `NoSuchMethodError` during linking/call resolution. |
| `Greeter.say()` exists, but its method body performs an operation that throws `ArithmeticException` | Runtime failure inside the method's logic. |

This is why the exact error type and `Caused by` lines matter far more than a vague statement like "the app doesn't run."

## 6. Diagnostic Workflow When Practicing Java 17

### Step 1: Identify Which Command Actually Failed

- If `javac` or the **compile** step of a build fails, start from the compiler message.
- If `java` was invoked and threw `NoSuchMethodError`, `NoClassDefFoundError`, `UnsupportedClassVersionError`, etc., inspect the classes, JARs, and runtime in use.
- If you see a stack trace for `ArithmeticException`, `NullPointerException`, `IOException`, etc., trace the failing call path and data state.

Do not assume every failure appearing after running `java` is a "runtime error" in the sense of **program logic**. Linkage errors also typically surface during launch or execution.

### Step 2: Verify Environment Versions

```bash
java -version
javac -version
```

For Java 17 exercises, confirm both the compiler and runtime point to Java 17. Machines with multiple JDKs or an IDE using a different JDK from the terminal are common sources of confusion.

To inspect a `.class` file:

```bash
javap -verbose App.class
```

Check `major version` (Java 17 is `61`) and the compiled class/method descriptors. The class file version tells you the **bytecode level**, not a guarantee that the program will run on every runtime of that version.

### Step 3: Check Classpath, Module Path, and Dependencies

In standard applications, the runtime must locate the **right versions** of the classes the program depends on.

```bash
java -cp . App
```

Here `-cp .` puts the current directory on the classpath; this is a simple example without external JARs. In real projects, the classpath may be set by the IDE, Maven, Gradle, or a launch script.

Helpful JDK 17 tools:

```bash
jar tf my-library.jar
jdeps my-app.jar
```

`jar tf` lists JAR contents; `jdeps` analyzes static dependencies. They **do not guarantee finding every dependency loaded dynamically via reflection or configuration**.

When you need to see which classes HotSpot JVM 17 actually loads, you can use:

```bash
java -Xlog:class+load=info -cp . App
```

This prints detailed diagnostics; inspect the class names and load sources to spot unexpected JARs. `-Xlog` is a HotSpot JVM diagnostic feature and should not be assumed as a universal contract across all JVM implementations.

### Step 4: Read the Stack Trace from the Useful Lines

Example:

```text
Exception in thread "main" java.lang.ArithmeticException: / by zero
    at RuntimeErrorDemo.main(RuntimeErrorDemo.java:4)
```

How to read it:

1. `ArithmeticException` is the **exception type**; `/ by zero` describes the condition.
2. `RuntimeErrorDemo.main(RuntimeErrorDemo.java:4)` points to the location in compiled source code (when line-number info is present).
3. Subsequent `at ...` lines, if present, show the call chain.
4. If `Caused by: ...` appears, follow the cause chain down to the root error. With `NoClassDefFoundError`, this is especially crucial because the root cause may be an earlier class initialization failure.

The message above is illustrative; line numbers, formatting, and stack frames depend on your actual source code and runtime.

### Step 5: Fix at the Right Layer and Retry

| Finding | Appropriate Action |
| --- | --- |
| `javac` reports type mismatch or missing variable/method | Fix source code or compile classpath dependencies, then recompile. |
| `NoSuchMethodError`/`NoSuchFieldError` | Align APIs, JARs, and application; rebuild classes that call the changed API. |
| `NoClassDefFoundError` | Inspect runtime dependencies, class loaders, module path, and root class initialization errors. |
| `UnsupportedClassVersionError` | Use a runtime supporting the bytecode or compile for a supported target level. |
| `NullPointerException`/`ArithmeticException` | Check data, program invariants, input validation, and add tests for the failing case. |
| `IOException` or environment failure | Check permissions, paths, resources, external services, and recovery handling. |

In environments using Java 17's **Java Platform Module System (JPMS)**, module configuration or resolution errors can also occur at compile time or startup, such as a missing module listed in `requires`. These can also prevent an application from running, yet **not every module error message is a `LinkageError`**. Classify based on the actual error and detection phase.

## 7. Comparing Through Three Short Labs

| Lab | How to Reproduce | Expected Result | Resolution |
| --- | --- | --- | --- |
| **Compile-time** | Assign string `"ten"` directly to an `int` variable in `CompileErrorDemo` | `javac` reports `incompatible types` | Fix the type or parse the input intentionally |
| **Linkage** | Build `App` against `Greeter.say()`, then replace only `Greeter.class` with a version lacking `say()` | `java App` throws `NoSuchMethodError` | Align caller/API and rebuild consistently |
| **Runtime** | Build `RuntimeErrorDemo` and run `java RuntimeErrorDemo 0` | `ArithmeticException: / by zero` | Validate divisor and handle invalid input |

These three cases demonstrate that **the same JDK 17 environment** can produce three very different failure categories; picking the right investigation path saves far more time than uninstalling and reinstalling the JDK whenever an error appears.

## 8. Self-Check Questions

**1. Why can `javac` succeed yet `java` still throw `NoSuchMethodError`?**  
Because the class file/JAR loaded at runtime may differ from the API the caller compiled against. The JVM cannot find a method with the matching signature in the actual loaded class.

**2. Is `NumberFormatException` in `Integer.parseInt(args[0])` a compile-time error?**  
No. The syntax and types can be completely valid; the exception only occurs when the input string does not represent a valid integer.

**3. Does `NoClassDefFoundError` always mean a JAR file is missing?**  
No. Besides a missing class definition at runtime, it can relate to a class that failed earlier during initialization. Always read the full message and cause chain.

**4. If an error appears after typing `java App`, can you conclude it is a runtime logic bug?**  
No. The JVM can also detect linkage errors while loading classes or resolving references at runtime.

**5. What error can happen when compiling for Java 17 and running on a Java 11 JVM?**  
`UnsupportedClassVersionError`, because the older JVM does not support Java 17 class files (major version 61).

**6. When tracking down a JAR containing the wrong class version, what should you inspect?**  
Inspect the runtime classpath/module path, deployed dependencies, and where classes are loaded from; on HotSpot you can inspect class-loading logs.

## Official Documentation

- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html) — language rules and what the compiler must check.
- [Java Virtual Machine Specification, Java SE 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — class loading, linking, and initialization phases.
- [Java SE 17 API — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html) — the JVM linkage error hierarchy.
- [Java SE 17 API — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html) — exceptions not required to be declared at compile time.
- [Java 17 javac Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) and [Java 17 java Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — compiler and launcher tools, plus options useful for diagnostics.
