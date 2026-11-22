# Prerequisites and Recommended Learning Sequence — Java Core: ClassLoader

## Learning Objectives

Before studying the `ClassLoader` mechanism, you need to understand how a Java class moves from source code to runtime. `javac` compiles source code into bytecode; the JVM uses loaders to locate and define classes at runtime; afterward, a class can be linked and initialized. Distinguishing these phases helps explain runtime errors in applications, libraries, plugins, and frameworks.

After completing this learning path, you should be able to:

- Distinguish between `.java` source code, `.class` bytecode, JARs, the classpath, the module path, packages, and binary class names.
- Explain with examples the difference between **loading**, **linking**, and **initialization**; recognize that locating a `Class<?>` object does not mean its `static` block has executed.
- Identify the three built-in loaders on Java 9+: **bootstrap**, **platform**, and **application/system**, and describe the default delegation order.
- Understand that a runtime type is uniquely identified by **binary name + defining class loader**, which underlies casting errors in plugin systems.
- Analyze `ClassNotFoundException`, `NoClassDefFoundError`, and initialization errors before deciding to fix the classpath or design a custom loader.

This guide focuses on **prerequisites and learning order**. Custom ClassLoaders, module layers, parallel class loading, and container classloaders are placed after the fundamentals; they are not entry prerequisites.

## 1. Prerequisites

### 1.1. Required Before Starting ClassLoader

| Knowledge Area | Why It Is Needed | Self-Check Level |
|---|---|---|
| Java: `class`, `interface`, `extends`, constructor, `static` | Understand how classes are defined and when static logic runs | Can create a class with `main`, nested classes, and a `static` block |
| Package, `import`, fully qualified class name | Loaders look up classes by **binary name**; `import` is only a source-code convenience | Can distinguish `java.util.List` from `List`; recognize `Outer$Inner` as the binary name of nested class `Outer.Inner` |
| JDK, `javac`, `java` | Avoid confusing class loading with compilation | Can compile and run a program outside an IDE |
| `.class` output, JAR, and classpath | Understand where the JVM can look for bytecode | Know how to pass `-cp` at runtime and identify the classpath root for a packaged class |
| Introductory JVM, `Class<?>`, and instances | Distinguish type metadata from an instance of that type | Can distinguish `Demo.class` from `new Demo()` |
| `Exception`, `Error`, stack trace, and `Caused by` | Read runtime error symptoms | Can identify the root cause in a simple stack trace |

**Entry check:** create a file `Hello.java` containing `public class Hello` with `main`, and run the following two commands from the directory containing the file:

~~~sh
javac Hello.java
java Hello
~~~

You must know that `javac` produces `Hello.class` and `java` launches the JVM to execute the class. When moving `Hello` into `package example;`, you must understand that the runtime name is `example.Hello` and that the directory containing `example/Hello.class` (following the package directory structure) must be on the classpath root, not just any directory containing source files.

### 1.2. Recommended Beforehand or Alongside This Path

- **Basic reflection:** `Class.forName`, `getClass()`, `getName()`, `getClassLoader()`. You do not need to learn all of reflection yet—just understand that `Class<?>` is the object describing a type.
- **Distinguishing compile-time and runtime dependencies:** an application may compile against one JAR but run with a different JAR or a missing JAR.
- **Inheritance and casting:** needed to understand why classes with the same name can still be incompatible when defined by two different loaders.

### 1.3. Not Needed in Depth Right Away

`module-info.java`, `ModuleLayer`, thread context class loader, native JNI, bytecode instrumentation, hot reload, class-loading deadlocks, and `registerAsParallelCapable` are advanced topics. They become valuable once you understand the default loaders and have a concrete need. A ClassLoader does not by itself create a security sandbox for untrusted code.

## 2. Knowledge Dependency Map

~~~text
Java class / package / static / error handling
                 |
                 v
javac / java / .class / JAR / classpath
                 |
                 v
JVM loading -> linking -> initialization
                 |
                 v
bootstrap / platform / application ClassLoader
                 |
                 v
parent delegation / Class.forName / Class<?>
                 |
                 v
class identity + class loading errors
                 |
                 v
custom loader / plugin / container / JPMS
~~~

Each layer explains problems in the next. For example, if you do not yet know where the classpath points, it is very easy to mistake a missing JAR error for a bug in a `loadClass` implementation.

## 3. Recommended Learning Sequence and Stage Gates

### Stage 1 — Source Code, Bytecode, and Class Lookup Scope

**Core concepts:** `.java` is source code; `javac` produces `.class` bytecode; `java` runs the application in the JVM. Output directories, JARs, and `-cp`/`--class-path` determine where the application can locate classes at runtime via the classpath. `import` does not add dependencies.

**Practice:** compile a standalone class; then create a class inside a package. Use `javac -d out` (create the `out` directory first if needed) and run `java -cp out packageName.Main`. Observe the `.class` directory structure matching the package. Try `javap -classpath out -c packageName.Main` to see that the `.class` file contains bytecode metadata that the JVM can process.

**Self-check:** why can `import com.example.Service;` be present yet the runtime still fail to find `Service`? Why does a successful `javac` build not guarantee that `java` can find all dependencies?

**Stage gate:** you can independently identify the binary name, classpath root, and where `.class` files are generated.

### Stage 2 — Distinguishing Loading, Linking, and Initialization

**Core concepts:**

1. **Loading:** the JVM uses a loader to find or create a class definition from class data; a corresponding `Class` object can then be used to represent the type.
2. **Linking:** includes bytecode verification (`verification`), preparation (`preparation`), and resolving symbolic references (`resolution`). The JVM may defer parts of resolution; a sequential diagram does not mean every operation happens immediately at once.
3. **Initialization:** the class's `static` initialization logic is executed according to rules defined by Java/the JVM. Loading and linking a class do not by themselves guarantee that its `static` block has run.

**Practice:** create a class with `static { System.out.println("initialized"); }`, then try obtaining its `Class<?>` object without triggering initialization; use the program in Section 4 to verify. Observe the difference between `X.class` and initializing `X` through active use.

**Self-check:** why does "loaded" not mean "initialized"? Why might a linkage error only appear when a specific code path is actually executed?

**Stage gate:** you can accurately describe all three phases and avoid assuming that all resolution always happens at the same moment.

### Stage 3 — Built-in Loaders and the Parent Delegation Model

**Core concepts:** from Java 9 onward, the runtime has three primary loader responsibility tiers:

- **Bootstrap class loader:** built into the JVM; Java APIs typically represent it as `null`. It loads core classes such as `java.lang.String`.
- **Platform class loader:** supports many platform API classes; obtained via `ClassLoader.getPlatformClassLoader()`.
- **Application/System class loader:** typically loads application classes on the classpath; obtained via `ClassLoader.getSystemClassLoader()`. Embedded environments may configure this differently.

By **default**, `ClassLoader.loadClass(name, resolve)` checks whether the class is already loaded, asks the parent to find it, and only then calls `findClass` if needed. This is the **parent-first** approach. The parent relationship is *class-loading delegation*, which is different from the `extends` inheritance relationship between Java classes. Custom loaders or plugin environments can change this strategy; therefore, parent-first is not an invariant of every ClassLoader.

**Practice:** inspect the results of `String.class.getClassLoader()` and `Main.class.getClassLoader()`. When `String`'s loader returns `null`, the right conclusion is that the API represents the bootstrap loader, not that "the class does not exist." Do not compare a loader's `toString()` output as a fixed standard across JDK versions.

**Self-check:** when the application loader looks up a class, when is the parent consulted in the default implementation? If the parent does not find it, which method is typically responsible for defining the class locally?

**Stage gate:** you can sketch the delegation flow and accurately state the roles of the bootstrap, platform, and application loaders.

### Stage 4 — Observing ClassLoaders and Initialization Timing

**Core concepts:** `Class<?>` describes a runtime type; `getClassLoader()` returns the loader that defined that type; `Class.forName(String, boolean, ClassLoader)` lets you request loading by binary name with an `initialize` flag. Conversely, the `Class.forName(String)` overload requests class initialization according to the API semantics. `ClassLoader.loadClass` does not request initialization by default.

**Practice:** run the complete Java example in Section 4. Then change `false` to `true` in the first call and predict stdout before running it.

**Self-check:** which line shows that a `Class` object exists? Which line shows that the `static` block has executed? Why are these two separate observations?

**Stage gate:** you can accurately predict the example's output and explain each call.

### Stage 5 — Runtime Class Identity and Loader Boundaries

**Core concepts:** a class in the JVM is distinguished by the **pair (binary name, defining loader)**. Two different loaders can define two classes with the same name, yet the JVM treats them as two distinct types. The *initiating* loader that starts a class lookup might simply delegate to its parent; it is not necessarily the *defining loader* of the returned class.

**Thought exercise:** two plugins A and B both contain a class named `com.example.PluginApi`, and each plugin defines the class with its own loader. Why is an object created from A's `PluginApi` not guaranteed to be castable to B's `PluginApi`? How can a shared API defined by a parent loader allow both sides to share a type contract?

**Self-check:** is seeing identical `Class.getName()` values enough to know that two `Class` objects represent the same type? What else must be checked?

**Stage gate:** you can explain loader-related `ClassCastException` errors without confusing them with matching package or source-file names.

### Stage 6 — Diagnosing Real Application Errors

| Symptom | Appropriate Interpretation | First Thing to Check |
|---|---|---|
| `ClassNotFoundException` | An API explicitly looked up a class by name, but the loader could not find it; checked exception | Binary name, classpath/JAR, and the loader passed to the call |
| `NoClassDefFoundError` | The JVM needed a class definition but could not find or use it; can also occur after a prior initialization failure | Read `Caused by`, stack trace, runtime classpath, and earlier errors |
| `ExceptionInInitializerError` | Static initialization logic threw an exception, causing initialization to fail | Read the cause in the `static` initializer and related dependencies |
| `ClassCastException` | Invalid cast; in plugin systems, may be caused by classes with the same name loaded by different loaders | Check actual runtime type, defining loader, and inheritance hierarchy |
| `NoSuchMethodError` / `NoSuchFieldError` | Usually a binary/API version mismatch between compile time and runtime | Check the JAR version actually used by the JVM |

**Diagnostic practice workflow:** (1) read the exact class name and exception/error type; (2) trace `Caused by`; (3) verify the runtime classpath/module path and library versions; (4) ask which loader is looking up/defining the class; (5) design a small test to verify your hypothesis. When appropriate on modern HotSpot JVMs, you can use `-Xlog:class+load=info` to observe class loading, but do not guess root causes solely from log volume.

**Self-check:** how does a missing JAR at runtime typically manifest compared to an exception thrown by a `static` initializer? Why is it important to know the exact error/exception rather than just searching logs for the word "class"?

**Stage gate:** you can distinguish lookup-by-name failures, missing dependent class errors, and initialization errors, and you have a systematic verification method.

### Stage 7 — Advanced Topics After Mastering the Fundamentals

Dive into these only when you have a practical need:

- **Custom ClassLoader:** `findClass`, `defineClass`, reading bytecode, and loader lifecycle. Per API guidance, generally prefer overriding `findClass` to preserve `loadClass` delegation; only override `loadClass` when you intentionally need a different strategy.
- **Plugins and containers:** isolated loaders, shared APIs, dependency isolation, parent-first or alternative lookup strategies; analyze class identity before attempting to fix casting issues.
- **Thread context class loader:** for frameworks and service/provider mechanisms that need lookup based on thread context; distinguish it from `SomeType.class.getClassLoader()`.
- **Java Platform Module System (JPMS):** `module-info.java`, module path, readability, exports/opens, module layers. Do not conflate the module path with the classpath.
- **Resource lookup and real-world environments:** `getResource`/`getResources`, JAR resources, dynamically loaded services, custom launchers; these involve additional scopes and lookup rules.
- **Concurrency, safety pitfalls, and loader design:** parallel-capable loaders, locking/deadlocks, bytecode validation, and security boundaries. A custom loader does not automatically make untrusted code safe.

## 4. Standalone Java 17+ Practice

Create a file named exactly **`ClassLoaderLearning.java`**:

~~~java
public class ClassLoaderLearning {
    static class Probe {
        static {
            System.out.println("Probe initialized");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("String uses bootstrap: "
                + (String.class.getClassLoader() == null));
        System.out.println("Main uses system loader: "
                + (ClassLoaderLearning.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));

        ClassLoader loader = ClassLoaderLearning.class.getClassLoader();
        Class<?> probe = Class.forName(
                "ClassLoaderLearning$Probe", false, loader);
        System.out.println("Located: " + probe.getName());
        System.out.println("Before explicit initialization");

        Class.forName(probe.getName(), true, probe.getClassLoader());
        System.out.println("After explicit initialization");
    }
}
~~~

Compile and run from the directory containing the file:

~~~sh
javac ClassLoaderLearning.java
java ClassLoaderLearning
~~~

With the standard JDK launcher invocation above, stdout is:

~~~text
String uses bootstrap: true
Main uses system loader: true
Located: ClassLoaderLearning$Probe
Before explicit initialization
Probe initialized
After explicit initialization
~~~

**Output explanation:**

1. `String` is defined by the bootstrap loader in a standard JDK environment, so `getClassLoader() == null` is `true`; `null` does not indicate an error.
2. When launched as shown above, `ClassLoaderLearning` uses the system/application loader. Do not assume this exact result applies to every embedded environment or custom loader setup.
3. `Class.forName("ClassLoaderLearning$Probe", false, loader)` returns `Class<?>`, but does not request initialization of `Probe`. Therefore, `Probe initialized` does not appear yet.
4. The subsequent call with `true` requests initialization. The `static` block runs once and is observed between the "Before" and "After" lines.
5. For the same already-initialized class definition, repeating an initialization request does not re-run the `static` initializer.

**Short extension exercise:** change the boolean in the first `Class.forName` call to `true`, run it in a new Java process, and explain why `Probe initialized` appears before the `Located` line. Do not confuse recompiling a file with refreshing already-loaded classes inside a running JVM.

This example intentionally avoids implementing a custom loader: learners should verify the class lifecycle and built-in loaders before moving on to `defineClass`.

## 5. Choosing a Starting Point Based on Current Background

| Current Background | Recommended Start | Readiness Signal to Advance |
|---|---|---|
| Not yet comfortable with `javac`, `java`, `-cp` | Stage 1 | Can run a packaged class and identify the classpath root |
| Writes Java but does not yet understand class lifecycle | Stage 2 | Can distinguish load, link, and initialize |
| Knows basic JVM concepts but not delegation | Stage 3 | Can name the three built-in loaders and default delegation |
| Understands the theory and wants hands-on proof | Stage 4 + example | Accurately predicts stdout and explains each line |
| Debugging plugin or dependency errors | Stages 5–6 | Can identify loader, class identity, error type, and hypothesis |
| Wants to write a custom loader | Stage 7 | Has a concrete use case and understands delegation consequences |

This is a **knowledge dependency order**, not a rigid hour-by-hour schedule. Learners who already have solid prerequisites can start at Stages 2–3, though they should still complete the practice exercise to verify their understanding.

## 6. Common Misconceptions to Avoid

- **"`import` makes the JVM find a class."** `import` only assists when writing source code; the classpath/module path and loaders govern runtime lookup.
- **"Having a `.class` file on disk means the JVM has loaded it."** The file may never have been requested by the process.
- **"Obtaining `Class<?>` means the `static` block has run."** The class may have been loaded/linked without being initialized yet.
- **"`Class.forName` only loads a class."** The one-argument overload requests initialization; the three-argument overload has a control flag.
- **"`null` from `getClassLoader` means an error."** For bootstrap-defined classes, this result is normal.
- **"A parent loader is a superclass."** Parent in a loader hierarchy is for delegation, completely different from `extends`.
- **"Identical class names prove the same type."** You must also account for the defining loader.
- **"All ClassLoaders are always parent-first."** That is only the default behavior; custom loaders and frameworks may use other strategies.
- **"Every error containing the word Class is a missing JAR."** There are also initialization failures, version mismatches, linking errors, and loader boundary issues.
- **"You must write a custom loader from scratch."** Studying and observing the built-in loaders first helps you understand why and when customization is actually needed.

## 7. Review Questions and Completion Criteria

1. How do `javac` and `ClassLoader` handle two different responsibilities? Why can't `import` fix a missing classpath entry?
2. When `Class.forName(name, false, loader)` returns, what can be concluded about class lookup, and what cannot yet be concluded about initialization?
3. How do the bootstrap, platform, and application loaders differ? Why can `String`'s loader be `null`?
4. In the default `loadClass` implementation, in what order are already-loaded checks, parent delegation, and `findClass` performed?
5. Are two classes with the same binary name but different defining loaders considered the same JVM type?
6. What three different diagnostic directions do `ClassNotFoundException`, `NoClassDefFoundError`, and `ExceptionInInitializerError` point to?
7. When code runs in an IDE but fails in the terminal, how would you compare compiler output, classpath, JAR versions, and launcher configuration?
8. In a plugin system, why should you consider having shared APIs defined by a loader visible to both the application and the plugins?

**Completion criteria:** you can answer all eight questions, compile and run the example yourself while explaining the exact order of stdout lines, and formulate a testable hypothesis for a class-loading error. At that point, you are ready to study deeper topics on class identity, parent delegation, resource lookup, and custom loaders without missing fundamentals.

## 8. Official References for Further Study

- [Java SE 21 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): built-in loaders, delegation, `loadClass`, `findClass`, and resources.
- [Java SE 21 — `Class` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `Class.forName` and the `initialize` flag.
- [JVM Specification, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): Loading, Linking, Initializing, and the formal JVM conditions.

Java 21 is selected for reference links for convenience; the example program only uses syntax and APIs available on Java 17 and later.