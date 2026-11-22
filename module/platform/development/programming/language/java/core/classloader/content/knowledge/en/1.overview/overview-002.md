# From Source Code and Bytecode to a Live Class in the JVM

A Java class does not go straight from a `.java` file into an object in memory. First, the source code is compiled into the `.class` format; when the program runs, the JVM uses a class loader to locate and define the class, performs the linking steps, and then initializes the class when Java's rules require it. Only then can objects be instantiated and method bytecode executed.

This article focuses on **the transformation chain from source code → class file → JVM-managed class** and the specific role of the class loader. Distinguishing each step helps explain why a class can exist on disk without the JVM having loaded it yet, why two classes with the same name are not necessarily the same type, and why an error can appear at runtime even though compilation succeeded.

## 1. The Big Picture

```text
Source code: src/demo/Target.java
          |
          | javac --release 17
          v
Class file: out/demo/Target.class
  - binary name, constant pool, fields/methods, bytecode, metadata
          |
          | JVM needs a reference to the class
          v
Class loader: locate class data + defineClass (or equivalent JVM mechanism)
          |
          v
Loading → Linking [Verification → Preparation → Resolution*]
          |
          | active use triggers the initialization requirement
          v
Initialization: executes <clinit> once per defined class
          |
          v
Class<?> / class metadata in the JVM
          |
          +--> new / reflection can create instances (objects)
          +--> method invocation: interpreter / JIT executes the code
```

Note on `*`: **resolution** may be performed by the JVM on demand, and is not required to complete every reference before initialization. A linear diagram describes logical relationships; it does not mean every step happens only once at a single fixed point in time.

| Component | Location / Role | Distinction |
| --- | --- | --- |
| `Target.java` | Source code text file | A normal JVM does not execute this content directly as compiled bytecode; the `java Target.java` command (source-file mode) includes a compilation step performed by the launcher. |
| `Target.class` | File or resource containing class-file bytes | May reside in a directory, JAR, module image, or be generated in memory; it does not have to exist as a standalone file. |
| Bytecode | Instructions in the `Code` attribute of a specific method | Input to the JVM's execution engine, not CPU machine code, and does not encompass the entire contents of a class file. |
| Class loader | Component that defines a class from binary data | Participates in determining **type identity** together with the class's binary name. |
| `java.lang.Class<?>` | Reflective object representing the class/type at runtime | Not a copy of the `.class` file, nor an instance of the business class itself. |
| Instance | Object created from a class, typically via `new` | A class can already be loaded without having any instances. |

Note two independent milestones: **`javac` succeeding** only proves that the source code passed compile-time checks; **the JVM successfully loading/linking/initializing** also depends on the actual bytecode, runtime version, libraries, loader, and initialization logic.

## 2. From `.java` to `.class`: What Does the Compiler Do?

`javac` reads source code, performs lexical/syntactic analysis, checks types, resolves names against the **compile-time** classpath/module path, and emits class files. Lambdas, generics, `switch`, `try`, and so on are mapped to appropriate structures in the class file. Standard generics use **type erasure**; parameterized types do not automatically generate a separate class file for each of `List<String>` and `List<Integer>`.

A class file begins with the magic number `0xCAFEBABE` and carries a format version (Java 17 corresponds to **major version 61**, Java 21 to 65). It contains the constant pool, class/superclass/interface names, modifiers, fields, methods, attributes, and the bytecode of methods that have code. The constant pool holds constants and **symbolic references** such as class names, method names, and descriptors; this does not mean every referenced class is loaded immediately when the file is read.

The binary name of `demo.Target` is `demo.Target`; its typical classpath path is `demo/Target.class`. A file path is only one storage form; the same bytes can live inside a JAR or come from a custom loader.

### Lab A — Observing Compilation, Loading, and Initialization

Create two files matching this exact directory tree:

```text
project/
└── src/
    └── demo/
        ├── Target.java
        └── App.java
```

**`src/demo/Target.java`**

```java
package demo;

public class Target {
    static {
        System.out.println("06 - Target initialized");
    }

    public static void hello() {
        System.out.println("07 - Target.hello()");
    }
}
```

**`src/demo/App.java`**

```java
package demo;

public class App {
    public static void main(String[] args) throws Exception {
        System.out.println("01 - main started");

        Class<?> byLiteral = Target.class;
        System.out.println("02 - " + byLiteral.getName());

        ClassLoader loader = App.class.getClassLoader();
        Class<?> byLoadClass = loader.loadClass("demo.Target");
        System.out.println("03 - same Class: " + (byLiteral == byLoadClass));

        Class<?> withoutInit = Class.forName("demo.Target", false, loader);
        System.out.println("04 - same Class: " + (byLiteral == withoutInit));

        System.out.println("05 - before active use");
        Target.hello();
        System.out.println("08 - main ended");
    }
}
```

Inside the `project` directory, run with JDK 17 or later:

```sh
javac --release 17 -d out src/demo/Target.java src/demo/App.java
java -cp out demo.App
```

**Expected output:**

```text
01 - main started
02 - demo.Target
03 - same Class: true
04 - same Class: true
05 - before active use
06 - Target initialized
07 - Target.hello()
08 - main ended
```

Explanation of each observation:

1. `Target.class` returns the `Class` object for `demo.Target` but **does not require initializing** `Target`. The VM is permitted to load/link before the program can observe it.
2. `loader.loadClass("demo.Target")` locates/returns the class through the loader and **normally does not initialize** it. Because both references point to the same class defined by the same loader, the `==` comparison is `true`.
3. `Class.forName("demo.Target", false, loader)` asks to locate the class with **`initialize=false`**, so the `static` block still has not run.
4. Calling the static method `Target.hello()` is an **active use** that causes the JVM to initialize `Target` before the method body runs: printing `06` then `07`. Class initialization occurs only once for that class in that loader.
5. `App` already had to be initialized by the JVM in order to run its `main`. The operations on `Target` in this example do not imply that every class referenced in a program is initialized at the same time.

Try changing `Class.forName("demo.Target", false, loader)` to `Class.forName("demo.Target", true, loader)`, then recompile and run in a new JVM process: line `06` will appear **before line `04`**. The second argument triggered initialization. If you call `Class.forName(String)`, by default it requests initialization and uses the caller class's loader per the API contract.

To inspect the bytecode and metadata, run:

```sh
javap -classpath out -c -p demo.App
javap -classpath out -verbose demo.Target
```

In the `javap -c` output for `App`, you can find instructions such as `ldc` (loading the class literal), `invokevirtual`, and `invokestatic`; `-verbose` on `Target` shows `major version: 61` because we compiled with `--release 17`. `javap` **disassembles a class file** for human inspection; it is not a tool that proves a class was loaded by the JVM while the application ran.

> **Key takeaway:** Having a `.class` file does not mean the class has been loaded; being loaded does not mean it has been initialized; and initializing a class does not mean an instance of that class exists.

## 3. Loading: Where Does the JVM Get a Class From?

When the JVM needs the class `demo.Target`, an appropriate loader is used to locate the binary data, validate the class-definition requirements, and create the runtime representation of the class. For a custom Java loader, the typical path is `loadClass` → delegate to parent → `findClass` → read bytes → `defineClass`. This is the common **parent delegation** pattern, not a rule that every loader must load files from disk or follow that exact algorithm.

The built-in loaders in JDK 17+:

- **Bootstrap loader**: loads core platform classes; Java represents this loader as `null` in `Class.getClassLoader()`, though `null` does not mean the class has no loader.
- **Platform loader**: serves many platform classes/modules; obtained via `ClassLoader.getPlatformClassLoader()`.
- **Application/System loader**: typically loads application classes from the classpath and appropriate application modules; obtained via `ClassLoader.getSystemClassLoader()`.
- **Custom loader**: can load plugins, system-generated class bytes, or isolated classpaths as needed.

Sketch of typical delegation:

```text
Application / Custom loader
         |
         | ask parent first (if the loader is parent-first)
         v
     Platform loader
         |
         v
   Bootstrap loader
         |
    if parent cannot find it, the child loader searches itself
```

A **parent loader** is not the same as a **parent Java class** (the `extends` keyword); those are two distinct relationships. A custom loader may use child-first delegation by design, and loaders supporting the Java Platform Module System have more complex lookup mechanisms than the diagram above. You should not assume every class passes through one simple delegation chain.

### How Do Classpath, JARs, and Module Path Affect Loading?

In Lab A, `java -cp out demo.App` puts `out` on the classpath. The application loader can locate `demo/App.class` and `demo/Target.class` by binary name. With a JAR, you can use `java -cp app.jar demo.App` if the JAR contains the appropriate entries. With named modules, `--module-path` and module resolution determine which modules are visible, along with readability/exports constraints; none of this reduces to simply adding a path to `-cp`.

If a file does not exist where the loader looks, if a dependency is missing, or if a module does not read/export the required package, previously compiled source code can still fail when run in another environment.

## 4. Linking: Turning Bytes into a Safely Usable Class

According to the Java Virtual Machine Specification, **linking** consists of three parts:

**Verification:** Checks that the class file has a valid structure and that bytecode type constraints are respected. A corrupted `.class` file, invalid bytecode, or certain inconsistencies can cause a `VerifyError` or a class format error.

**Preparation:** The JVM allocates and sets **default values** for the class's `static` fields in the appropriate management structures. For example, with `static int count = 5`: during preparation, the default initial value is `0`; the assignment of `5` is normally executed during initialization. A `static final` field that is a **constant variable** with a `ConstantValue` attribute may be assigned its constant value directly during preparation, so the `0` rule does not apply to every case.

**Resolution:** The JVM replaces symbolic references in the constant pool with appropriate runtime references as needed, checking the existence and accessibility of the referenced class, field, or method. Resolution can happen **on demand**; errors from missing dependencies or mismatched API signatures may surface late, when the relevant instruction is executed.

Ordering constraint: a class must be **verified and prepared before initialization**; resolution may be performed flexibly. Some dependent classes may be loaded earlier to support verification or resolution without necessarily being initialized yet.

These concepts do not equate to **compile-time linking** in native toolchains. Java class files retain many symbolic references for the JVM to resolve at runtime.

## 5. Initialization: When Does `static` Actually Run?

Initialization executes the special `<clinit>` method synthesized by the compiler/JVM from static field initializers and `static { ... }` blocks in source order, if the class requires such code. Before initializing a subclass, the JVM must initialize the appropriate superclass; for interfaces, the related initialization rules differ from classes.

Operations that commonly trigger class initialization:

- Creating an instance with `new Target()`.
- Calling a static method declared by the class, such as `Target.hello()`.
- Reading/writing a static field declared by the class, except for certain **constant variable** cases inlined by the compiler.
- Calling reflection APIs with the initialization flag set to `true`, or certain reflection operations that perform active use.
- The JVM initializes the class containing `main` before running the `main` method.

Operations that **do not by themselves require initializing** `Target`: taking `Target.class`, reading the class name from `Class`, `ClassLoader.loadClass("demo.Target")`, and `Class.forName("demo.Target", false, loader)`. The JVM may still load/prepare early as an optimization, but it must not expose initialization side effects before the language allows.

Example of a **compile-time constant**:

```java
package demo;

public class Constants {
    public static final int PORT = 8080; // constant variable
    public static final Integer BOXED_PORT = 8080; // not a constant variable
    static {
        System.out.println("Constants initialized");
    }
}
```

Another class reading `Constants.PORT` may receive the inlined value **without triggering `Constants` initialization**. By contrast, reading `Constants.BOXED_PORT` causes active use and initialization. To test this, place the reading code in a separate class and run in a fresh JVM process, because a class is initialized only once within its defining scope. Changing a constant value in a library without recompiling consumers can leave consumers holding the old value.

If `<clinit>` throws an exception, the first access may receive `ExceptionInInitializerError` (depending on the error type); that class can enter a failed initialization state, and subsequent uses typically encounter `NoClassDefFoundError` indicating that the class could not be initialized. Successful loading and linking do not guarantee that initialization logic will succeed.

## 6. What Exactly Is "a Live Class in the JVM"?

The JVM defines the runtime identity of a reference class/interface by the pair **(binary name, defining class loader)**. Two different loaders can define two classes with the **same name** from identical bytes, yet the JVM treats them as **two distinct types**. That is why a cast error message can sometimes look strange: `demo.Plugin cannot be cast to demo.Plugin`, because the two sides have the same name but were defined by different loaders.

Two roles must be kept distinct:

- **Initiating loader**: the loader asked to load the class, which may delegate.
- **Defining loader**: the loader that actually defines the class. For example, a child loader is asked for `java.lang.String`, but the parent/bootstrap loader defines it; the defining loader of `String` is bootstrap.

A runtime class has metadata (name, superclass, interfaces, fields, methods, runtime constant pool, etc.) and a corresponding reflective `Class<?>` object. The **Method area** is the logical memory area described by the JVM Specification; **Metaspace** is a HotSpot implementation detail for most class metadata, while the `java.lang.Class` object is a Java object. Do not equate all metadata with the instance heap, nor claim that every JVM uses Metaspace.

**Loading ≠ initialization ≠ instantiation**:

- Loading: the JVM has the runtime definition of the class.
- Initialization: the class's static initialization completes (or fails), per its own rules.
- Instantiation: creating **a** concrete object of the class; many objects may be created, or none at all.

A class can become **eligible for unloading** when its defining loader and related classes/objects are no longer sufficiently referenced to stay alive. Unloading is decided by the GC/runtime and is not guaranteed to happen immediately when `URLClassLoader.close()` is called or a variable is set to `null`. The JDK also has hidden classes and classes generated at runtime; they follow their own rules, so loading from a file on disk is not the only path.

### Lab B — Same Name, Different Defining Loaders

Create two additional files in the same `demo` package under `src/demo/` (keeping the two files from Lab A):

**`src/demo/Plugin.java`**

```java
package demo;

public class Plugin {
    public String message() {
        return "hello plugin";
    }
}
```

**`src/demo/LoaderIdentityDemo.java`**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL classesDir = Path.of("out").toAbsolutePath().toUri().toURL();

        try (URLClassLoader left = new URLClassLoader(new URL[] {classesDir}, null);
             URLClassLoader right = new URLClassLoader(new URL[] {classesDir}, null)) {

            Class<?> a = left.loadClass("demo.Plugin");
            Class<?> b = right.loadClass("demo.Plugin");

            System.out.println("same name: " + a.getName().equals(b.getName()));
            System.out.println("same Class: " + (a == b));
            System.out.println("assignable: " + a.isAssignableFrom(b));
        }
    }
}
```

Compile and run **from the `project` directory**:

```sh
javac --release 17 -d out src/demo/Plugin.java src/demo/LoaderIdentityDemo.java
java -cp out demo.LoaderIdentityDemo
```

**Exact stdout:**

```text
same name: true
same Class: false
assignable: false
```

Here, two different `URLClassLoader` instances both have `parent=null` (delegating to bootstrap when appropriate) and independently define `demo.Plugin` from the same `out` directory. Even though the name and bytecode are identical, `a` differs from `b` because their defining loaders differ. `Path.of("out")` intentionally depends on the working directory from which the command is run; running from another directory requires adjusting the path. This demonstrates **type identity**, not a recommendation to use a `null` parent for production plugins: real isolation models must consider shared APIs, module access, resources, and loader lifecycle.

If you switch to two loaders whose parent is the application loader while keeping `Plugin` on the classpath, the parent-first rule can cause both to delegate and receive the **same** `demo.Plugin`. That is why you must determine the **defining loader** before concluding which class was loaded from which file.

## 7. How Does the JVM Execute Bytecode After Loading?

Valid `Class` metadata and bytecode allow the JVM to locate a method when it is invoked. The runtime may use an **interpreter** to interpret bytecode and a **JIT compiler** to compile hot paths into machine code. This happens after or interleaved with class usage; it does not mean the entire class file is JIT-compiled at loading time. Optimizers may inline or transform execution, but must preserve required Java semantics.

A method called by the application can still trigger loading/linking of other classes at runtime because references to them are only now being used. Therefore, the diagram at the start of this article is a **conceptual framework**, not a statement that every class in an application goes through loading, linking, and initialization together right at `main`.

To inspect class-loading events on modern HotSpot, you can run:

```sh
java -Xlog:class+load=info -cp out demo.App
```

This is a HotSpot/JDK Unified Logging flag; the output is verbose and depends on the JDK version, classpath, and environment. Use the log to see the class source and when loading events occur, and **do not** infer initialization timing from a loading log line alone.

## 8. Distinguishing Errors by Stage

| Symptom | Typically Associated With | What to Check |
| --- | --- | --- |
| `javac: cannot find symbol` / `package ... does not exist` | Compilation | Imports, type names, compile classpath/module path. |
| `ClassNotFoundException` | Lookup via `loadClass` / `Class.forName` cannot find the requested name | Binary name, JAR/classpath/module path, initiating loader. |
| `NoClassDefFoundError` | JVM needs to define/use a class but cannot find it, or the class previously failed initialization | Runtime dependencies, nested cause, earlier class initializer. |
| `UnsupportedClassVersionError` | Class file is newer than the JVM supports | Running JDK version vs. `javap -verbose` major version. |
| `ClassFormatError` / `VerifyError` | Class format / bytecode verification | Bytecode-generating tools, build output, class modification steps. |
| `NoSuchMethodError` / `NoSuchFieldError` | Runtime resolution does not match the API compiled against | Actual JAR versions, dependency conflicts, binary compatibility. |
| `ExceptionInInitializerError` | Error during static initialization | Cause stacktrace in `<clinit>`, static initialization order, side effects. |
| `ClassCastException` with the same class name on both sides | Two class definitions with different defining loaders | Loader logs, `getClassLoader()`, plugin versions, and shared APIs. |

These are **diagnostic pointers**, not a 1-to-1 mapping table for every situation. Read both `Caused by` and the error context; errors in the `LinkageError` family can occur when a reference is first used rather than immediately when running the `java` command.

A short diagnostic checklist: (1) check the **binary name** and where `.class` resides, (2) verify the compile/run JDK versions, (3) verify the actual runtime classpath/module path, (4) verify the **initiating/defining loader**, (5) determine whether the failure occurred before or during initialization, and (6) compare dependency versions and the stacktrace. `getClassLoader()` returning `null` for bootstrap is normal.

## 9. Self-Check Questions

1. **If `out/demo/Target.class` exists on disk, is `Target` already in the JVM?** Not necessarily. A class file is a resource; a loading demand or operation must occur for the runtime class to be defined.
2. **Are `Target.class` and `new Target()` the same?** No. The first expression retrieves `Class<?>` and does not by itself require initialization; the second creates an instance and requires initialization of the appropriate class beforehand.
3. **Why did `loadClass` find `Target` without the `static` block printing yet?** Loading and initialization are two distinct stages; `loadClass(String)` normally does not require initialization.
4. **Why might two `demo.Plugin` instances fail to cast to each other?** Runtime type identity includes the defining loader in addition to the binary name.
5. **Must resolution happen for everything before `main` runs?** No. The JVM may resolve references on demand; required checks for each stage must still hold.
6. **Does the JVM only use an interpreter?** No. HotSpot and many implementations combine an interpreter and JIT; optimizations do not change semantics.
7. **Does closing a `URLClassLoader` immediately unload its classes?** No. Closing releases resources opened by the loader; unloading also depends on reachability and GC.

## 10. Takeaways for Moving Forward with ClassLoader

Always answer four separate questions when analyzing a Java class: **(1) Where do the class bytes come from? (2) Which loader defines it? (3) How far has the class been verified/prepared/resolved? (4) Has the class been initialized yet?** Only then ask whether any instances exist, which methods are being executed, and whether JIT compilation is involved.

The standard sequence to remember is **source → compilation → class-file bytes → loading → linking → initialization on active use → execution/instantiation on demand**. In practice, loading and resolution across multiple classes can interleave, and a single binary name can correspond to multiple runtime types through multiple defining loaders. This is the bridge from class-file fundamentals to parent delegation architecture, custom loaders, plugin isolation, and classpath errors in Java applications.
