# Bootstrap class loader and the role of the JVM

## 1. What is the bootstrap class loader?

**Bootstrap class loader** is the mechanism that loads essential foundational classes so that the Java Virtual Machine (JVM) can operate and execute Java programs. Types such as `java.lang.Object`, `java.lang.String`, `java.lang.Class`, and many types belonging to the `java.base` module are defined by the bootstrap class loader on a standard JDK 17.

In short: **the JVM is the execution environment**, whereas **the bootstrap class loader is part of the class loading mechanism at the foundational layer of the JVM**. The bootstrap loader provides core class definitions for both the JVM and higher-level class loaders to use. These two concepts should not be treated as the same thing:

- The **JVM** executes bytecode, verifies and links classes, manages memory/GC, manages threads, and enforces class initialization rules.
- The **bootstrap class loader** is responsible for finding and defining the classes assigned to the bootstrap layer. It is only **one link in the class loading system**, not the entire Java execution engine.
- **Other Java class loaders** (platform, application/system, user-defined class loaders) collaborate to load classes that the bootstrap loader does not define.

This distinction is important when reading `Class.getClassLoader()`, when encountering `ClassNotFoundException`, when designing plugins, or when investigating two classes that **have the same name** yet cannot be cast to each other.

## 2. Why does the JVM need a class loader at the bootstrap layer?

Even a very small Java program needs foundational type definitions. For example:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
```

During execution, the JVM needs the definitions of `java.lang.Object`, `java.lang.Class`, `java.lang.String`, and many related runtime library components. If every class loader had to be a Java object loaded beforehand by another class loader, the startup process would fall into a circular dependency: creating the first class loader would already require the essential classes to be loaded.

The bootstrap class loader solves the need of **initializing the initial type ecosystem**. On common JVM implementations such as HotSpot, this loader is implemented at the JVM/native layer and **does not have a regular `java.lang.ClassLoader` object directly representing it** in the Java API.

That explains why:

```java
System.out.println(String.class.getClassLoader()); // null
```

On a standard JDK 17, this line prints:

```text
null
```

The `null` value is **an API convention representing the bootstrap class loader**; it does not mean "the class was not loaded" or "the JVM does not use a class loader".

> Do not attribute `null` to a class loader object and interpret it as an object named BootstrapClassLoader. In the Java API, null represents the bootstrap layer in places specified by the documentation.

## 3. Bootstrap, platform, and application class loaders on JDK 17

Since Java 9, the module system (JPMS) has changed how the JDK organizes its foundational libraries. On JDK 17, the three built-in class loader layers to distinguish are:

| Layer | Typical role | Observation on Java 17 |
|---|---|---|
| **Bootstrap** | Defines core foundational classes, including most classes in `java.base` | `String.class.getClassLoader() == null` |
| **Platform** | Defines classes belonging to certain other Java SE/JDK platform modules, according to the runtime's module mapping | `ClassLoader.getPlatformClassLoader()` |
| **Application / System** | Loads application classes on the class path and corresponding application modules | `ClassLoader.getSystemClassLoader()` |

This is **a useful model for learning**, but it is not a rule that "the `java.*` package belongs to bootstrap, and other packages belong to application". For example, you must not infer that every class in all `java.*` modules is defined by the bootstrap loader. Which layer defines a specific class depends on the runtime/module configuration and the JDK implementation.

The built-in loaders of JDK 17 typically have the following parent relationships:

```text
Bootstrap class loader
  (no regular ClassLoader object)
                ^
                | parent at API level represented by null
                |
Platform class loader
                ^
                |
Application / System class loader
                ^
                |
Custom ClassLoader typically uses app loader as parent
```

The arrows above illustrate **the typical delegation direction**, not a Java inheritance (`extends`) relationship between the class loaders, nor does it mean the JVM forces every custom loader to strictly follow a parent-first policy.

**Version change milestones:**

- **JDK 8 and earlier:** it was commonly said that the bootstrap loader searched for core classes in `rt.jar`/the bootstrap class path, the extension loader handled extensions, and the application loader handled the class path.
- **JDK 9 and later:** the old `rt.jar`/extension mechanism model no longer exists. The JDK provides a runtime image and named modules; the extension loader has been replaced by the **platform class loader**. Therefore, looking for `$JAVA_HOME/jre/lib/rt.jar` on JDK 17 is an outdated expectation.
- **JDK 17:** foundational classes reside in the JDK runtime image and can be browsed in the `jrt:/` form via appropriate tools and APIs. Do not treat `jrt:/` as a regular physical JAR file path.

Commands to help inspect the module structure on JDK 17:

```bash
java --list-modules
java --describe-module java.base
```

They print the module list/details of the current runtime. Module information **supplements** class loader knowledge; it does not replace determining the actual defining loader of each class.

## 4. Specific role of the bootstrap loader in the JVM mechanism

A view of the process:

1. The JVM is started by the `java` launcher program and prepares the runtime.
2. The JVM needs foundational types in order to define, verify, link, and execute other classes. The bootstrap loader is responsible for defining the corresponding set of core types.
3. When an application class is needed, the runtime uses the appropriate loader mechanism. The application class loader typically coordinates with parent loaders; if bootstrap can find and define a requested foundational class, the application shares that definition.
4. Once the class definition is available, the JVM proceeds to handle **linking** (verification, preparation, and resolution according to the rules) and then **initialization** if needed, after which it executes the code.

A pitfall to avoid: **loading does not mean initialization**. Loading/defining `String` is a different activity from running class initialization when a Java operation requires it. The bootstrap class loader does not replace the JVM's verification, initialization, execution, or garbage collection rules.

### Class loaders find and define; what else does the JVM do?

- **Loading:** creating or finding a runtime class/interface from an appropriate binary representation via a class loader.
- **Verification:** checking the class file/bytecode against JVM safety and structural rules.
- **Preparation:** preparing static fields and initial values according to VM rules.
- **Resolution:** converting symbolic references into runtime references; the JVM is permitted to perform parts of this on demand.
- **Initialization:** executing `<clinit>` according to initialization triggering conditions.
- **Execution:** the interpreter/JIT and runtime execute methods/bytecode instructions.
- **Garbage collection and class unloading:** managing the ability to reclaim memory, class metadata, and objects when eligible.

**The bootstrap loader is primarily involved in the stage of defining foundational classes.** The subsequent stages belong to the semantics and execution mechanisms of the JVM, applying to a class regardless of its defining loader.

## 5. Parent delegation: where does bootstrap stand?

The typical class loading model of `ClassLoader.loadClass(String)` in Java can be summarized as follows:

```text
loadClass("com.example.Service")
          |
          v
Already loaded by this loader? -- Yes --> return loaded Class<?>
          |
          No
          v
Ask parent to load (if parent == null: use bootstrap)
          |
          +-- Parent loaded successfully --> use definition returned by parent
          |
          +-- Parent did not find it
                  |
                  v
            Current loader finds/defines it itself (findClass)
                  |
                  v
            Return Class<?> or ClassNotFoundException
```

This is the **typical default** algorithm of `ClassLoader.loadClass`. A custom class loader can override `loadClass` to use a different strategy, and built-in loaders in the module system can handle lookups according to module mappings; one should not claim that every class loader on every JVM always queries bootstrap first for every kind of class in all cases.

### Why is the parent usually prioritized?

Suppose an application or plugin contains a file named `java/lang/String.class`. You cannot infer that just because this file is on the class path, the JVM will use it instead of the `java.lang.String` already defined by the runtime. The delegation mechanism, package/runtime constraints, and class/platform protection rules work together to prevent arbitrary spoofing of core classes.

Practical benefits:

- **Sharing foundational types:** most application classes refer to the same `java.lang.String` definition from bootstrap, avoiding accidentally creating incompatible core types.
- **Consistency:** APIs at different layers can pass/receive the same runtime type from the foundational library.
- **Class loading boundaries:** an application loader does not have the default right to replace or redefine the foundational namespace simply by adding a JAR.
- **Supporting isolation:** a custom class loader can separate types it defines itself, while still typically sharing the JVM foundation with its parent.

**Parent delegation is not a complete security system.** In modern Java, class loaders, JPMS, access checks, and bytecode verification each serve distinct functions; having parent-first should not be treated as meaning the application is safely sandboxed.

## 6. Runtime identity of a class and the impact of the bootstrap loader

In the JVMS, the identity of a runtime class/interface is determined by its **binary name and defining class loader**. For example:

- `java.lang.String` defined by the bootstrap loader is a shared foundational type.
- `com.example.Plugin` defined by loader A can differ from `com.example.Plugin` defined by loader B, even if their bytecode or binary name are identical.
- The fact that both classes use `java.lang.String` as a parameter does not automatically make them compatible with each other.

Distinguish two concepts:

- **Defining loader**: the loader that actually defines the runtime class.
- **Initiating loader**: the loader that initiated the request to load that class; it may receive a definition performed by a parent.

For example, the application loader requests `java.lang.String` via delegation; the bootstrap loader provides the definition. When calling `String.class.getClassLoader()`, we see the **defining loader** at the bootstrap layer (represented as `null`), even though the initiating operation may have come from application code.

If a class defined by a custom loader uses a `String name` field, the field itself still uses the appropriate `String` definition from bootstrap; the custom loader does not need to redefine `java.lang.String`.

### Static state and class identity

Static fields are tied to each runtime class identity. For a class defined separately by loader A and loader B, each definition can have its own static state. Conversely, `String` from bootstrap is the same runtime class that application layers commonly use; instances of this foundational type do not become different types just because they reside in multiple plugins.

## 7. Inspecting the bootstrap loader with Java 17

The following example uses public APIs properly, avoiding printing internal implementation names that may differ across JDKs.

Create the file **`BootstrapLoaderDemo.java`**:

```java
public class BootstrapLoaderDemo {
    static class Sample { }

    public static void main(String[] args)
            throws ClassNotFoundException {

        ClassLoader app = BootstrapLoaderDemo.class.getClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        System.out.println("String bootstrap: "
                + (String.class.getClassLoader() == null));
        System.out.println("Object bootstrap: "
                + (Object.class.getClassLoader() == null));
        System.out.println("String[] bootstrap: "
                + (String[].class.getClassLoader() == null));

        System.out.println("Main class via app: "
                + (app == ClassLoader.getSystemClassLoader()));
        System.out.println("Nested class via app: "
                + (Sample.class.getClassLoader() == app));
        System.out.println("Platform parent is bootstrap: "
                + (platform.getParent() == null));
        System.out.println("App parent is platform: "
                + (app.getParent() == platform));

        Class<?> resolved = Class.forName(
                "java.lang.String", false, null);
        System.out.println("Bootstrap resolves String: "
                + (resolved == String.class));

        System.out.println("String module: "
                + String.class.getModule().getName());
    }
}
```

Compile and run in **the default class path configuration of a common JDK 17 HotSpot/OpenJDK**, without using a custom system class loader:

```bash
javac BootstrapLoaderDemo.java
java BootstrapLoaderDemo
```

Stdout:

```text
String bootstrap: true
Object bootstrap: true
String[] bootstrap: true
Main class via app: true
Nested class via app: true
Platform parent is bootstrap: true
App parent is platform: true
Bootstrap resolves String: true
String module: java.base
```

Explanation:

1. `String` and `Object` belong to the runtime core and are defined by the bootstrap loader. `getClassLoader()` returns `null` for those classes.
2. `String[]` is **a different runtime array class from `String`**, but an array class of a reference type has a defining loader corresponding to the defining loader of its component type; therefore `String[].class.getClassLoader() == null`.
3. The `BootstrapLoaderDemo` class and nested class `Sample` are compiled/run by the application from the class path and defined by the default application loader.
4. `platform.getParent() == null` reflects that the platform loader has the bootstrap loader as its parent by API convention; `app.getParent() == platform` holds for the default built-in chain in this example.
5. `Class.forName("java.lang.String", false, null)` passes **`null` for the loader parameter**: the API uses the bootstrap loader for this request. `false` means **do not request initialization**, not "do not load".
6. `String.class.getModule().getName()` prints `java.base`, helping confirm the class belongs to the core module.

Portability note: class loaders are configurable or customizable components. If using `-Djava.system.class.loader`, special agents, or another runtime, some **app parent** comparisons may differ. The comparisons in the example serve as evidence for **the stated configuration**, not a guarantee for every JVM that may exist.

### Why does `String[].class` also report bootstrap?

According to JVM rules, for an array whose component type is a reference type, the defining loader of the array is tied to the defining loader of the component type. For an array of primitives, such as `int[]`, the JVM creates the array class and there is no user-defined component class; `int[].class.getClassLoader()` also commonly returns `null` in Java. Do not infer from `null` that there is an `int[].class` file in the runtime image.

## 8. A null parent does not create a new bootstrap loader

A point easily misunderstood when reading the Java API: the fact that the `ClassLoader` constructor accepts `null` as a parent **does not make that instance the bootstrap loader**.

Create the file **`BootstrapParentDemo.java`**:

```java
public class BootstrapParentDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader isolated = new ClassLoader(null) { };

        System.out.println("Parent is null: "
                + (isolated.getParent() == null));

        Class<?> core = isolated.loadClass("java.lang.String");
        System.out.println("Delegated String: "
                + (core == String.class));

        try {
            isolated.loadClass("BootstrapParentDemo");
            System.out.println("Unexpectedly loaded app class");
        } catch (ClassNotFoundException expected) {
            System.out.println("Application class not visible");
        }
    }
}
```

Run from a standard class path using JDK 17:

```bash
javac BootstrapParentDemo.java
java BootstrapParentDemo
```

Stdout:

```text
Parent is null: true
Delegated String: true
Application class not visible
```

This is a **new class loader object**, an anonymous subclass of `ClassLoader`, whose API parent is `null`. It can rely on bootstrap to load `String`, yet by default it has no custom `findClass` mechanism to locate the `BootstrapParentDemo.class` file on the class path. Consequently, the call to load the application class fails in the described environment.

Key takeaway: **the bootstrap loader is not an instance created via `new ClassLoader(null)`**; that instance merely **delegates to bootstrap** when its parent is `null`.

To load application classes, a custom loader must have an appropriate loading strategy: being assigned a suitable parent, or implementing the finding/defining of the classes it manages itself. Do not arbitrarily use `new ClassLoader(null)` as a "safe isolation method", as visibility and module access errors may arise.

## 9. Does the bootstrap loader automatically initialize every class it loads?

**No.** Three commonly conflated steps must be clearly separated:

1. **Loading**: the runtime class is found/defined by the loader.
2. **Linking**: the JVM verifies, prepares, and resolves references as needed.
3. **Initialization**: the JVM runs `<clinit>` when an appropriate active-use condition occurs.

A class having bootstrap as its defining loader **does not mean** bootstrap directly controls when its static initializer runs; initialization follows the JVM/JLS and depends on how the class is used.

Similarly for application classes:

```java
Class<?> c = Class.forName(
        "com.example.SomeType", false, loader);
```

The `false` value means deferring the initialization request. If the program later uses `new SomeType()`, accesses a static field that is not a compile-time constant, calls a static method, or performs another operation that triggers initialization, only then must the JVM initialize it according to the rules.

This distinction helps avoid side effects when only scanning class metadata. For example, a class path analysis tool or plugin system may need to know whether a class exists before allowing its static initializer to execute.

## 10. Bootstrap loader, platform modules, and the runtime image

### Do not use the `rt.jar` model for Java 17

On JDK 8, documentation often illustrated the bootstrap class loader reading the Java core from `rt.jar`. That explanation is **version-dependent**. Since JDK 9, the modular runtime image has changed how libraries are packaged. JDK 17 provides runtime modules, among which `java.base` is the mandatory module containing foundational APIs.

You can inspect the details directly:

```bash
java --describe-module java.base
```

Appropriate tools and providers can display resources in the runtime using URLs of the form `jrt:/java.base/...`. That is a **runtime image URI scheme**, not a claim that all classes are read by Java from a JAR named `jrt.jar`.

### Not every JDK class is loaded by bootstrap

For example, `java.lang.String` in `java.base` belongs to bootstrap. However, the JDK also has other Java SE modules and tool/implementation modules, which may be assigned to the bootstrap, platform, or application loader depending on configuration. Do not build a classification table based solely on package prefixes `java.`, `javax.`, `jdk.`, or by guessing from module names.

When you need a conclusion in a specific program, inspect the **actual runtime class**:

```java
Class<?> type = Class.forName("java.lang.String");
ClassLoader definingLoader = type.getClassLoader();
Module module = type.getModule();
```

This is an **illustrative** snippet that must be placed inside a method that declares/handles `ClassNotFoundException`. `definingLoader == null` means the class is defined by bootstrap. `module.getName()` provides the named module's name if present, but **module name and class loader are two distinct attributes**.

### Do not replace core libraries by placing a JAR at the front of the class path

Adding a JAR containing bytecode with the same name as a core class to the class path is not a valid method to "override `java.lang.String`". The JDK applies loader/module/package mechanisms and corresponding JVM constraints.

There are JVM options intended for **instrumentation, patching, and internal research**, such as module patching or bootstrap class path appending on certain JVMs; they have their own conditions and limitations, and **do not mean you can arbitrarily overwrite every class in `java.base`**. When working with JDK 17, read the exact documentation of the VM and the option you are using instead of copying `-Xbootclasspath/p` instructions from the JDK 8 era verbatim.

## 11. Class loaders are not synonymous with every JVM protection mechanism

The bootstrap loader is often explained alongside "safety" benefits because it helps prevent shared foundational classes from being arbitrarily replaced by an application. However, the boundaries must be understood accurately:

- **Bytecode verification** belongs to the JVM's class file validity checking mechanism, not simply "bootstrap approves the bytecode and lets it run".
- **Access control** (`public`, `protected`, package access, module exports/opens, nestmates...) operates according to Java/JVM semantics; loader identity affects the runtime package and type compatibility.
- **JPMS** governs readability, exports, and opens between modules; "defined by bootstrap" does not mean code in every module is permitted to access every internal API of that class.
- **Security Manager** is not a recommended mechanism for sandboxing untrusted code in modern Java. Do not assume that parent delegation is sufficient to isolate malicious bytecode.

Therefore, use class loaders to understand **visibility, identity, and delegation**, and use other API/module/runtime mechanisms for appropriate access, verification, and isolation requirements.

## 12. Real-world mistakes and how to investigate

### Mistake 1: "`getClassLoader() == null` means the class has not loaded"

Incorrect. For `String.class`, `null` is precisely the sign that the defining loader is represented by the API as bootstrap. The class is already present and `Class<?>` represents that runtime type.

### Mistake 2: "Anything whose name starts with `java.` is bootstrap"

Incorrect. The module set of a modern JDK is broader than `java.base`; you must inspect the actual defining loader and module mapping. Moreover, the JDK forbids many improper ways of defining classes belonging to system namespaces.

### Mistake 3: "The bootstrap loader is `ClassLoader.getSystemClassLoader()`"

Incorrect. `ClassLoader.getSystemClassLoader()` returns the system/application loader, typically used for applications. `ClassLoader.getPlatformClassLoader()` returns the platform loader. The bootstrap loader is not returned as a regular `ClassLoader` object.

### Mistake 4: "A null parent means there is no delegation mechanism"

Incorrect. In `ClassLoader`'s default contract, a `null` parent causes delegation to bootstrap. The `BootstrapParentDemo` example demonstrates this exact point.

### Mistake 5: "The application loader and bootstrap define two copies of `String`"

In a standard JDK 17 program, other loaders delegate/are configured to use the shared `String` definition from bootstrap. Do not infer that each loader keeps its own copy of core classes. The ability to define the same name in two custom loaders primarily relates to application classes/permitted namespaces.

### Mistake 6: "Getting `ClassNotFoundException` means bootstrap is broken"

Not true. `ClassNotFoundException` can come from the requested loader not being able to see the corresponding class/path/module. A parent-null custom loader like in the example only sees bootstrap and what it defines itself; failing to see `BootstrapParentDemo` from the class path is not a sign of a broken JVM.

Other related errors:

- `NoClassDefFoundError` can appear when a class needed at linking/runtime cannot be found or a previous initialization failed; the error name does not prove the bootstrap loader is broken.
- `ClassCastException` between two classes with the same name can involve two different **defining loaders**.
- `LinkageError` can reflect an incompatible mismatch during loading/linking/resolution. Inspect the full stack trace, not just the first line.

### Short diagnostic workflow

1. Record the **exact binary name** of the type, for example `com.example.Plugin`, along with how the program invokes the loader.
2. Inspect `clazz.getClassLoader()`, `clazz.getModule()`, and `clazz.getProtectionDomain()` where valid, avoiding assumptions based on the package name. `getProtectionDomain()` may have varying configurations/access permissions and is not always necessary.
3. Inspect the parent chain and module/class path of the loader **that is actually being invoked**.
4. If there are two `Class<?>` instances, compare `classA == classB` directly; if false, check the defining loader of each class.
5. On HotSpot, use loading logs, but distinguish **lines where a class is loaded** from **lines where a class is initialized**.

Command for logging class loading on HotSpot JDK 17:

```bash
java -Xlog:class+load=info BootstrapLoaderDemo
```

The log can be very long because the JDK and libraries load many classes. Run with and without the application to investigate the class loading path, avoiding false conclusions when looking only at logs without class initialization information.

## 13. Self-check exercises

**Question 1.** `String.class.getClassLoader()` returns `null` on a standard JDK 17. What does that mean?

**Answer:** `String` is defined by the bootstrap class loader; the API uses `null` to represent this defining loader, not to mean there is no class.

**Question 2.** On JDK 17, is looking for `java.lang.String`'s code in `rt.jar` the right approach?

**Answer:** No. Since Java 9, the runtime has been organized into a module image; `java.lang.String` belongs to `java.base`. The `rt.jar` model was characteristic of earlier JDK systems and documentation.

**Question 3.** If an application class has a `java.lang.String title` field, does it need to define `String` itself?

**Answer:** No. The application loader typically uses the `String` definition from bootstrap through the appropriate mechanism; the JVM identifies types by runtime class identity.

**Question 4.** Does `ClassLoader.getPlatformClassLoader().getParent() == null` mean the platform loader has no parent?

**Answer:** At the Java API level, `null` represents bootstrap; the platform loader can use bootstrap as its parent under this mechanism.

**Question 5.** Two custom class loaders separately define `com.example.Widget`. Are the two runtime classes equal?

**Answer:** No, if their defining loaders differ. Having the same binary name is not enough; `Widget.class` from two separate definitions does not share the same runtime identity.

**Question 6.** Why is `new ClassLoader(null) {}` not "re-instantiating the bootstrap class loader"?

**Answer:** It creates **a separate Java loader object** whose parent is represented by `null`. That loader can delegate to bootstrap, but it does not become the JVM's bootstrap mechanism.

**Question 7.** Does loading `java.lang.String` through bootstrap automatically mean "the JVM ran the constructor of a `String` object"?

**Answer:** Not yet. Class loading/initialization concerns the class definition; object construction concerns each specific instance. The JVM can define a class without executing a constructor to create an object of that class.

## 14. Key takeaways and official references

- **Bootstrap** is the layer that defines core classes; in the Java API, `getClassLoader() == null` typically represents the bootstrap defining loader.
- **The JVM** is the broader system, performing linking, initialization, bytecode execution, memory management, and many other activities.
- **JDK 17:** uses a runtime module image and has bootstrap/platform/application layers; do not equate it with the `rt.jar` and extension loader model of JDK 8.
- **Loader identity:** runtime class identity depends on both the binary name and the defining class loader. Delegation helps application classes share the runtime core.
- **Experimental verification:** use `Class.getClassLoader()`, `getModule()`, and ``Class.forName(name, false, null)`` to understand each case strictly via the API.

Official documentation:

1. [Java Virtual Machine Specification 17, §5 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html).
2. [Java SE 17 — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, platform/system loader.
3. [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()`, `forName`, `getModule()`.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261): the module system and built-in loader behavior since Java 9.
5. [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): changes to runtime image organization and the `rt.jar` model.
