# `resolveClass` and the Difference from Class Initialization

> **Context:** Java Core → ClassLoader → Class Loading API. This article explains precisely what `ClassLoader.resolveClass(Class<?>)` does, how it relates to `loadClass`/`defineClass`, and why **linking** a class is not the same as **initialization**. The content follows the Java SE contract and the JVM Specification; standalone examples use Java 17+.

## 1. Core Answer

In a custom `ClassLoader`, the snippet:

~~~java
Class<?> type = loadClass("example.Widget");
resolveClass(type);
~~~

means **requesting that `example.Widget` be loaded if not already loaded, and then linking the returned class if needed**. It does **not** mean “invoking the static initializer of `Widget`”. Because `resolveClass` is `protected final`, this snippet is only valid **within the body of a `ClassLoader` subclass** (or a Java context permitted to access protected members); this is an **illustrative snippet**, not a standalone program.

To request **initialization** of a class using an explicit API, you can use:

~~~java
Class.forName("example.Widget", true, suitableLoader);
~~~

where `suitableLoader` is a suitable loader. The three-parameter overload with `initialize=true` requests initialization of the class/interface; `false` does not request initialization. Upon initialization, `ConstantValue` values are applied and the `<clinit>` method (if present) is executed according to JVM/JLS rules.

**Quick Distinction:**

| Concept/API | Meaning | Guaranteed to run `static { ... }` of the target class? |
| --- | --- | --- |
| `ClassLoader.loadClass(String)` | Finds/returns `Class<?>` via the loader and delegation; by default does not request resolution with boolean `true` | **No** |
| `ClassLoader.loadClass(String, boolean)` | Protected method: can request `resolveClass` when `resolve=true` | **No** |
| `ClassLoader.resolveClass(Class<?>)` | **Links** a class that already has a `Class<?>`; the API name is somewhat misleading | **No** |
| `Class.forName(name, false, loader)` | Looks up `Class<?>` via the loader **without requesting initialization** | **No** |
| `Class.forName(name, true, loader)` | Looks up and requests to **initialize** the corresponding class/interface | **Yes if needed**, though `<clinit>` may not exist, may have already run earlier, or may have no side effects |
| `new Widget()` | Creates an instance; must ensure the relevant class has been initialized before use | **Runs when it is an active use requiring initialization** |
| `Widget.someStaticMethod()` | Calls a static method; triggers initialization of the class/interface declaring the method | **Runs when needed** |
| Reading `Widget.someStaticNonconstantField` | Reads a `static` field that is not a constant variable | **Runs when needed** |
| Reading `Widget.COMPILE_TIME_CONSTANT` from compiled code | May use the inlined value, without needing to initialize the declaring class | **Not by this operation alone** |

“Running `<clinit>`” should not be understood as *always producing a log line*. Many classes do not have a `<clinit>`, an already initialized class will not run again, and a static initializer is not required to print to the screen.

## 2. Three Phases of a Runtime Class

JVM Specification `5` defines three sets of tasks: **loading**, **linking**, **initialization**.

~~~text
                  LOADING
         Read/create runtime class and Class<?> token
                       |
                       v
                  LINKING
         +-----------------------------+
         | Verification                | check class file/type safety
         | Preparation                 | create static fields; default values
         | Resolution                  | resolve symbolic references when needed
         +-----------------------------+
                       |
                       v
                INITIALIZATION
        assign ConstantValue per JVMS rules
        run <clinit> if defined
        record initialized / erroneous state
~~~

This is a **logical** diagram; the JVM may resolve symbolic references **lazily or eagerly** within the scope of the specification. Do not infer that every reference has been resolved as soon as `resolveClass` returns.

### 2.1. Loading

Loading locates the binary representation, creates the runtime class/interface or array class, and may request additional classes. For an ordinary class, the runtime identity is **(binary name, defining class loader)**.

For example, two custom loaders may both return the name `org.example.Plugin`, yet be two different runtime types if **each loader defines** that class itself. Conversely, when both loaders delegate to the same parent, the result can be exactly one `Class<?>`.

`ClassLoader.loadClass(name)` typically returns an existing type or finds a new type, and **the success of the call must not be taken as evidence that the initializer has run**.

### 2.2. Linking

Linking consists of:

1. **Verification:** ensures that the class file data is valid and conforms to type safety constraints. An invalid class file can lead to a `VerifyError` or appropriate `LinkageError`s.
2. **Preparation:** creates the static fields and sets them to their **default** values (`0`, `false`, `null`...), **without yet** executing Java initialization expressions.
3. **Resolution:** converts symbolic references in the runtime constant pool into concrete references; this may involve classes, fields, methods, method handles, dynamic constants, call sites, and checking accessibility/loader constraints. The JVM has the authority to choose the timing of resolution within the specified limits.

The API name **`resolveClass`** is misleading because it sounds as if it only performs the *resolution* part. The `ClassLoader` documentation explicitly states: **“Links the specified class.”** This means the purpose of this API is **linking**, not “forcing immediate resolution of all symbolic references”.

### 2.3. Initialization

Initialization performs behavioral work:

- Assigns values from `ConstantValue` to appropriate fields before running `<clinit>`.
- Runs the code of static field initializers/static initializer blocks that the compiler combines into `<clinit>`, if defined.
- Coordinates other threads waiting for initialization of the same runtime class.
- Ensures conditions related to the superclass and superinterfaces that have default methods, depending on the class/interface context per the JLS algorithm.
- Marks the class initialized upon success, or **erroneous** upon failure.

The JVM requires a class to be verified/prepared before being initialized; however, a JVM may still resolve additional references after the class has already been initialized. Therefore, “already initialized” also does **not** prove that every symbolic reference of the class was resolved beforehand.

## 3. Exact Contract of `ClassLoader.resolveClass`

Java SE API signature:

~~~java
protected final void resolveClass(Class<?> c)
~~~

Characteristics:

- **`protected`:** ordinary `main` code cannot arbitrarily call `someLoader.resolveClass(c)` from outside. A custom class loader can call it inside the subclass; Java access rules still apply.
- **`final`:** subclasses **cannot override** the behavior of `resolveClass`. If you want to control how classes are loaded, override the appropriate extension point such as `findClass`, or `loadClass` when a different delegation policy is genuinely needed.
- **`void`:** the method does not return a `Class`; the resulting class token was already passed in.
- **`null` argument:** throws `NullPointerException`, rather than turning into `ClassNotFoundException`.
- **Calling when the class is already linked:** simply returns normally; it does not mean the static initializer will run again.
- **Calling with an unlinked class:** the VM performs linking as specified. Verification/linkage errors can still be detected, though the timing of an error for a specific symbolic reference depends on resolution rules.
- **Not a public API to initialize:** there is no `initialize` parameter and there is no “`resolveClass(true)`”.

Note that there are **two levels of naming**:

- `ClassLoader.resolveClass(Class<?>)` = the API from the loader to **link a class**.
- **JVM resolution (`JVMS 5.4.3`)** = the operation of processing a **symbolic reference** in the constant pool. This is part of linking, but it does not mean that calling `resolveClass` forces all references to be resolved immediately.

### 3.1. Where Is This API Typically Called From?

In the default implementation of `ClassLoader.loadClass(String, boolean)`, the algorithm is described in the form:

~~~java
// Pseudocode: simplified API algorithm; NOT the standard implementation.
synchronized (getClassLoadingLock(name)) {
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            c = (parent != null)
                    ? parent.loadClass(name)
                    : findBootstrapClassOrNull(name);
        } catch (ClassNotFoundException ignored) {
            // Continue searching in the current loader.
        }
        if (c == null) {
            c = findClass(name);
        }
    }
    if (resolve) {
        resolveClass(c);
    }
    return c;
}
~~~

The snippet above only explains the **delegation + link idea**, not code to copy and compile: internal helpers such as `findBootstrapClassOrNull`, access to the `parent` variable, and JDK-specific special handling are not all public APIs for subclasses.

The key point: the `resolve` flag means **“link the class if requested”**, **not “initialize the class”**. It is not a parameter of the public `loadClass(String)` overload. To control the flag from application code, one typically creates **a method on a subclass** that calls the protected overload, as shown in the complete example below.

### 3.2. Default `loadClass(String)` and `loadClass(name, resolve)`

According to the `ClassLoader` contract, the one-parameter overload is implemented via the protected overload with `resolve=false`:

~~~java
public Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return loadClass(name, false);
}
~~~

Therefore, calling `loader.loadClass("pkg.Target")` **does not request** `resolveClass` along the default flow. However, the JVM/loader may have already linked the class earlier or may link eagerly depending on the implementation; one must not infer that the class is definitely in an “unlinked” state solely because of the `false` flag.

The setting `resolve=false` means **not proactively requesting the link step through this API**, rather than a command “forbidding the JVM from linking the class for the rest of the program”. Meanwhile, `resolve=true` also does **not** turn the call into explicit class initialization.

## 4. Standalone Example: `resolveClass` Does Not Run the Static Initializer

File **`LinkVsInit.java`**:

~~~java
public class LinkVsInit {
    static class Target {
        static {
            System.out.println("Target initialized");
        }

        static int answer = 42;
    }

    static final class ProbeLoader extends ClassLoader {
        ProbeLoader() {
            super(LinkVsInit.class.getClassLoader());
        }

        Class<?> loadAndLink(String binaryName)
                throws ClassNotFoundException {
            Class<?> result = loadClass(binaryName, false);
            resolveClass(result);
            return result;
        }
    }

    public static void main(String[] args) throws Exception {
        ProbeLoader loader = new ProbeLoader();

        System.out.println("1. before load/link");
        Class<?> token = loader.loadAndLink("LinkVsInit$Target");
        System.out.println("2. after link: " + token.getName());

        Class.forName("LinkVsInit$Target", false, loader);
        System.out.println("3. after forName(false)");

        Class.forName("LinkVsInit$Target", true, loader);
        System.out.println("4. after forName(true)");

        System.out.println("5. answer=" + Target.answer);
    }
}
~~~

Compile/run using JDK 17 or later:

~~~bash
javac --release 17 LinkVsInit.java
java -cp . LinkVsInit
~~~

**Stdout:**

~~~text
1. before load/link
2. after link: LinkVsInit$Target
3. after forName(false)
Target initialized
4. after forName(true)
5. answer=42
~~~

Explanation:

1. `LinkVsInit.Target` is a static nested class; the binary name used in the API is `LinkVsInit$Target`.
2. `ProbeLoader` has as its parent the loader that loaded the application class `LinkVsInit`. When calling `loadClass`, it **delegates**, so `Target` is typically **defined by the application loader**, not by `ProbeLoader` itself.
3. `resolveClass(token)` requests linking and does not trigger `static{}`: hence the message “Target initialized” **does not yet appear** before line 3.
4. `Class.forName(..., false, loader)` does not request init; line 3 still prints before the message from the static block.
5. `Class.forName(..., true, loader)` requests initialization for the first time; the static block prints “Target initialized”, and the field initializer sets `answer=42`.
6. The subsequent access to `Target.answer` uses the already initialized runtime class, so it does not print the message a second time.

**Verification point:** The success of `resolveClass` **does not make the class initialized**, even when the class is already linked. Having the three lookup calls use the exact same `Class<?>` defined by the parent helps the experiment avoid interference from a different class identity.

If the program is run again in **a new JVM**, the block will run again on the new process's new runtime class. If multiple operations are run within **the same JVM and the same defining loader**, completed initialization will not repeat.

## 5. Identifying Operations That Trigger Initialization

A `Class<?>` object describes the runtime type; it is the action using the type that determines whether initialization is requested. For an uninitialized class:

- `T.class`, `loader.loadClass(name)`, and `Class.forName(name, false, loader)` can obtain `Class<?>` without actively running `<clinit>`.
- `resolveClass(type)` requests **linking** and still does not trigger `<clinit>`. The `LinkVsInit` experiment in Section 4 directly verifies this.
- `Class.forName(name, true, loader)`, `new T()`, calling a static method of `T`, and reading a static field that is not a constant variable are operations that can require initialization.
- Reading a compile-time constant such as `static final int VALUE = 7` can be inlined by the compiler and therefore does not by itself cause initialization. For an array class name, `Class.forName` does not initialize the element class solely from looking up the array.

When diagnosing, inspect the class's **first active use operation**; a class-loading log line or a successful `resolveClass` result is not enough to conclude that the initializer has run.

## 6. Why “Linked” Does Not Mean “Every Reference Is Resolved”

Suppose class `A` has bytecode calling `B.work()`. The runtime constant pool of `A` contains a symbolic reference to the relevant class/method. The JVM can:

- Process some symbolic references right when verifying/linking the class.
- Defer resolution until the relevant instruction is actually executed.
- Load auxiliary classes during verification or linking, while still not initializing them.
- Apply loader constraints and access checks when resolution requires them.

The JVMS allows **eager or lazy resolution**, while still imposing constraints on where an error may be thrown when a reference is used and on certain kinds of dynamic constants/call sites. Therefore, one cannot make the general promise:

> “`resolveClass(A.class)` succeeds ⇒ every method/field/class referenced by `A` already exists, access checks succeeded, and statements using them are guaranteed not to throw `LinkageError`.”

That promise is **false**. `resolveClass` is a class-linking API; it is not a transitive dependency scanner or an absolute validator of every call site. `NoClassDefFoundError`, `NoSuchMethodError`, `IllegalAccessError`, or other linkage errors can still appear later at the point where a reference is used.

### 6.1. Loading, Verifying, Preparing, and Resolving Depend on Each Other but Are Not Necessarily Simultaneous

A specification-compliant JVM guarantees:

- A class is loaded before it is linked.
- A class is completely verified and prepared before it is initialized.
- Resolution may still take place **after the point of initialization** for certain symbolic references, depending on the implementation strategy and JVMS constraints.
- If a resolution error is detected, it must be thrown at a point where a program action may directly or indirectly require that linkage.
- A class may have been loaded by loader A through delegation while the actual **defining loader** is B. Loading constraints ensure type safety in such cross-loader interactions.

Practical consequence: a smoke test that only calls `loadClass(..., true)` or `resolveClass` cannot replace an **integration test that executes** the APIs that need to be used. Finding a class does not guarantee compatibility with the ABI, module access, or runtime usage of the application.

## 7. When Writing Your Own `ClassLoader`: Where Should `resolveClass` Go?

### 7.1. Common Case: Override `findClass`, Keep Default `loadClass`

If you only need to add a bytecode source, prefer overriding `findClass(String)`. The parent-first logic, `findLoadedClass` cache, class-loading locks, and `resolve` flag are handled by the default `ClassLoader.loadClass`.

Example **illustrating a subclass body**:

~~~java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] bytes = obtainClassBytes(name); // custom method you must provide
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

This is **not a standalone runnable Java program** because `obtainClassBytes` is a hypothetical method used to read bytes. The main idea: `findClass` **defines** the class and returns it. If the caller goes through `loadClass(name, true)`, the default implementation will call `resolveClass`. Calling `resolveClass` inside `findClass` is not required for everything to be “compliant”.

### 7.2. When Overriding `loadClass(String, boolean)`

A child-first loader or one with a custom package policy must properly handle caching, locking, and resolution:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> type = findLoadedClass(name);

        if (type == null) {
            if (isOwnedPackage(name)) {
                try {
                    type = findClass(name);
                } catch (ClassNotFoundException ex) {
                    type = super.loadClass(name, false);
                }
            } else {
                type = super.loadClass(name, false);
            }
        }

        if (resolve) {
            resolveClass(type);
        }
        return type;
    }
}
~~~

This is **Java pseudocode** inside a subclass: `isOwnedPackage` and `findClass` are implementation-dependent, so do not copy this verbatim into a project that has not defined those two methods. The key thing to observe is that **`resolveClass(type)` is only executed when the `resolve` flag is `true`**, after obtaining `Class<?>`.

Principles to avoid breaking the loader:

1. Use `findLoadedClass(name)` so you do not attempt to call `defineClass` repeatedly for the same binary name.
2. Synchronize on `getClassLoadingLock(name)` per the `ClassLoader` contract; if you want it to be **parallel capable**, you must register it and ensure the loader properly supports the mechanism.
3. Maintain consistency: for the same name already recorded by this loader as an initiating loader, subsequent corresponding calls must return that exact `Class`.
4. Do not redefine core Java classes or shared interfaces at the host/plugin boundary under an uncontrolled child-first policy.
5. Understand that `resolve=true` only requests **linking**, not running `<clinit>`.
6. Handle `ClassNotFoundException` (class not found) differently from `LinkageError` (binary/verification/constraint errors), and do not blindly swallow linkage errors to “try another loader”.
7. Do not arbitrarily call `Class.forName(..., true, ...)` in plugin-loading code if the intent is only to check for the presence of a class; it can trigger static side effects.

### 7.3. `defineClass` and `resolveClass` Are Two Separate Operations

`defineClass(String, byte[], int, int)` converts class bytes into a runtime `Class<?>` created by the **defining loader**. `resolveClass(clazz)` is an additional call to link that class if needed. Some custom loaders proactively call both:

~~~java
Class<?> defined = defineClass(name, bytes, 0, bytes.length);
resolveClass(defined);
return defined;
~~~

The snippet above is only valid **inside a `ClassLoader` subclass** where `name` and `bytes` are already available. It does not create an object instance and **does not** invoke `<clinit>`. If the class has an initializer that performs I/O, creates threads, or calls a service, those behaviors do not start automatically just because you called `defineClass` and then `resolveClass`. They may start later when calling `new`, a static method, a static nonconstant field, or reflection requesting initialization.

**Do not treat `defineClass` as meaning “the bytecode is ready for every call”.** Preparation state and resolution errors can appear later. Separate deployment/loading policy from plugin activation policy.

## 8. An Example Showing That a Failure Occurs at Initialization, Not Linking

File **`InitFailureAfterLink.java`**:

~~~java
public class InitFailureAfterLink {
    static class Broken {
        static int value = compute();

        private static int compute() {
            System.out.println("running Broken.<clinit>");
            throw new IllegalStateException("missing configuration");
        }
    }

    static class ProbeLoader extends ClassLoader {
        ProbeLoader() {
            super(InitFailureAfterLink.class.getClassLoader());
        }

        Class<?> link(String name) throws ClassNotFoundException {
            Class<?> type = loadClass(name, false);
            resolveClass(type);
            return type;
        }
    }

    public static void main(String[] args) throws Exception {
        ProbeLoader probe = new ProbeLoader();
        Class<?> type = probe.link("InitFailureAfterLink$Broken");
        System.out.println("linked: " + type.getName());

        try {
            Class.forName("InitFailureAfterLink$Broken", true, probe);
        } catch (ExceptionInInitializerError error) {
            System.out.println("initialization failed: "
                    + error.getCause().getClass().getSimpleName());
        }

        try {
            Class.forName("InitFailureAfterLink$Broken", true, probe);
        } catch (NoClassDefFoundError error) {
            System.out.println("later use: "
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 InitFailureAfterLink.java
java -cp . InitFailureAfterLink
~~~

Stdout:

~~~text
linked: InitFailureAfterLink$Broken
running Broken.<clinit>
initialization failed: IllegalStateException
later use: NoClassDefFoundError
~~~

Analysis:

- `probe.link` returns successfully: the class is loaded/linked but **not yet initialized**, so the `compute()` method has not run.
- `Class.forName(..., true, probe)` requests initialization; the compiler placed the `compute()` call inside `<clinit>`. `IllegalStateException` (which is not an `Error`) is wrapped by the JVM in `ExceptionInInitializerError`.
- The runtime class is then in the **erroneous** state; the next initialization request for **the same class identity** encounters `NoClassDefFoundError`. That does not prove the `.class` file disappeared, and calling `resolveClass` again has no effect to fix it.
- Another copy of the class with the same name **defined by a different loader** is a different runtime class identity, yet creating a new loader does not solve the “missing configuration” cause; the source of the error needs to be fixed.

**Note:** Both `ExceptionInInitializerError` and `NoClassDefFoundError` are subclasses of `Error`, belonging to class initialization failures; with a corrupted class file or invalid module access, an error may occur earlier during loading/linking. Do not lump all class loader failures into a single exception.

## 9. Distinguishing Three Error Groups When Debugging

| Phase or Situation | Common Symptom | What to Check |
| --- | --- | --- |
| Looking up a class by name fails | `ClassNotFoundException` from `loadClass`/`Class.forName` | Loader, binary name, class path/module path, JAR, delegation mechanism |
| Class file version not supported by the VM | `UnsupportedClassVersionError` | `java -version`, `javap -verbose` major version, `javac --release` |
| Invalid bytecode | `ClassFormatError`, `VerifyError` | Bytecode generator/instrumentation, class file version |
| Binary contract differs from compile time | `NoSuchMethodError`, `NoSuchFieldError`, `IncompatibleClassChangeError` | Dependency version, classpath/module graph, which class the loader chose |
| Visibility rules/loading constraints | `IllegalAccessError` or appropriate `LinkageError` | JPMS readability/exports, runtime package, class identity |
| Static initializer computation fails | `ExceptionInInitializerError` or the original `Error` | `<clinit>`, static fields, configuration, first side effects |
| Class already erroneous after a failed initialization | `NoClassDefFoundError` | The **previous** initialization failure in the same runtime class |
| Attempting to use protected `resolveClass` outside a subclass | **Compile-time access error** | Java access permissions, not a JVM loading error |
| Calling `resolveClass(null)` inside a subclass | `NullPointerException` | Null argument, not “class not yet loaded” |

**Important warning:** The table lists *commonly observed* symptoms, not an assertion that the JVM always throws each error type at a fixed step. The JVM allows controlled eager/lazy resolution, so a binary dependency error might only surface when a specific instruction is executed.

### 9.1. Why Calling `resolveClass` Alone Is Not Enough to Test All Dependencies

Plugin code may contain a symbolic reference to `LibraryV2.doWork()` while the runtime only provides `LibraryV1`. If the JVM does not yet need to resolve that method reference during initial linking, `resolveClass` can return normally. When the code actually invokes the method, the JVM may throw `NoSuchMethodError`.

Therefore, tests must **exercise the business code paths that need to be supported**, rather than stopping at `Class<?> c = loader.loadClass(name)` or `resolveClass(c)`. At the same time, you need to test startup, static initialization, module permissions, and interactions between class loaders.

## 10. Does `resolveClass` Proactively Load Superclasses/Dependencies?

The class loading and verification/linking phases may require loading additional classes/interfaces such as superclasses or those needed to verify descriptors/hierarchies. However, one must not infer from this that:

- **Every** class imported in the source file must already have been loaded after `resolveClass`.
- **Every** class appearing in a method body has already been initialized.
- All static fields of auxiliary classes have already received values from their initializers.
- A child loader definitely defined the class itself if it called `resolveClass`.

A class can be loaded/linked while dependencies in unexecuted code paths have not yet been used; references may wait to be resolved according to JVM policy. A Java import is a compile-time syntactic concept, not a dependency list that the class loader must load immediately.

**Often overlooked point:** When a `ClassLoader` subclass calls `resolveClass(c)`, `c` may come from **parent delegation**. Calling link does not turn the subclass into the **defining loader** of `c`. Proper observation:

~~~java
Class<?> c = someLoader.loadClass("java.lang.String");
System.out.println(c.getClassLoader() == null);
~~~

On common Java runtimes where `String` belongs to the bootstrap loader, the program prints `true`. However, this is only a snippet inside a class with a valid `someLoader` variable; one should not print internal implementation names to deduce class identity.

## 11. Linking ≠ Initialization in Real Applications

### 11.1. Plugin Discovery

A host wanting to display a list of plugins may only **load the class token** of a provider to verify metadata, without wanting to create database connections or threads from a static initializer. Typically:

1. Use metadata/JAR descriptors to find candidates.
2. Use `Class.forName(binaryName, false, pluginLoader)` when the token is needed.
3. Check the contract using `SharedApi.class.isAssignableFrom(candidate)` with **SharedApi defined by the shared loader**.
4. Only when a provider has been chosen and is ready to start its lifecycle, invoke reflection/constructor/static entry point per the required API.

**Do not use `resolveClass` as an absolute “safe dry run”:** linking can still load/verify other classes, incur overhead, encounter linkage errors, or trigger behavior implemented in your own custom loader. Furthermore, subsequent reflection operations can cause the class to initialize depending on the specific method and API.

### 11.2. Framework Dependency Injection and Reflection

A framework reading `Class<?>`, annotations, and method/field metadata can occur before an object is created. However, one should not claim that every reflection API avoids triggering initialization: you must read the contract of the API being called. For example, `Class.forName(name,true,loader)` intentionally initializes, whereas `Class.forName(name,false,loader)` does not request initialization.

If framework configuration encounters an `ExceptionInInitializerError`, first identify **which active use operation occurred earlier** rather than automatically blaming the “class scan” step. Similarly, a `NoClassDefFoundError` on a later access may reflect an initialization failure from startup.

### 11.3. Hot Reload and Class-Loader Isolation

Each class is normally initialized at most once **per runtime class identity**. When the host creates a new loader and **defines** the same binary name as a new class, the new class has its own static state and can be initialized separately. If the new loader simply delegates back to the old class, neither `resolveClass` nor `Class.forName(...,true,loaderMoi)` creates a new version of the type.

Therefore, when hot reloading:

- Clearly specify the **defining loader** of shared APIs and plugin classes.
- Do not use `resolveClass` expecting to “reset” static state.
- Clean up threads/callbacks/caches/`ThreadLocal` so the old loader can be GC'd under the runtime's conditions; `URLClassLoader.close()` does not guarantee immediate unloading.
- Manage the plugin lifecycle via explicit APIs, avoiding putting all startup/teardown inside a static initializer.

## 12. Limitations and Implementation Details to State Accurately

- **You cannot call `<clinit>` directly from Java source** like an ordinary method. The compiler generates its body from static initializers; the VM decides the timing of initialization according to the rules.
- **`resolveClass` is not a synonym for `Class.forName(..., true, ...)`**. One API links; the other API requests initialization.
- **`loadClass(name, false)` does not guarantee that the class is completely unlinked**. It merely does not proactively request `resolveClass` through this API path.
- **`resolveClass` does not guarantee eager resolution of the entire runtime constant pool**; the JVMS permits lazy resolution.
- **`resolveClass` is not a public method** and is not used to replace Java module readability/access checks.
- **There is no guarantee on the log ordering of “class loaded”, “class linked”, “class initialized”** as a single sequence across all JVMs; logs are implementation observations, not a replacement for the specification.
- **Linker errors can be encountered before the initializer**. For example, a class file with the wrong major version or a bytecode verification failure. However, do not assume a given symbolic reference error will be detected immediately upon calling `resolveClass`.
- **Do not use the `resolve=true` flag to force a class reload**. For the same already-linked class token, the call is a no-op; actual reloading depends on a new runtime class created by a different defining loader.
- **Initialization is safely coordinated across threads**, but updating mutable static state after init still requires separate synchronization according to the Java Memory Model.
- **Class path/module path can change runtime identity/access**, but they do not change the definition of `resolveClass` in the Java SE API.

## 13. How to Observe on JDK 17+ Without Confusing Logs with the Specification

### 13.1. `javap` Shows Whether `<clinit>` Code Exists

Compile `LinkVsInit.java` first, then:

~~~bash
javap -c -p 'LinkVsInit$Target'
~~~

In PowerShell and Unix shells, single quotes protect the `$` in the binary name. `javap` typically displays the class initializer section under the `static {};` heading. That section contains bytecode that prints “Target initialized” and assigns `answer=42`. Finding that bytecode **does not** indicate it has executed in a specific process.

### 13.2. HotSpot Unified Logging

If using OpenJDK/HotSpot with unified logging support:

~~~bash
java -Xlog:class+load=info LinkVsInit
java -Xlog:class+init=info LinkVsInit
java -Xlog:help
~~~

- `class+load` shows load events; loading a class **is not synonymous with** init.
- `class+init` allows observing certain initialization events on JVMs/systems that support that tag; the output can be very long.
- `-Xlog` is an implementation-specific JVM logging mechanism, not a common API every Java Virtual Machine is required to support. Check `java -Xlog:help` when switching JDKs/vendors.

**Do not parse HotSpot's message format to infer language rules.** Use a program that prints “before/after” markers and cross-check the JVMS/JLS to understand the behavior.

### 13.3. Observing in a Debugger

A debugger may automatically evaluate expressions or invoke methods via reflection, thereby **causing initialization outside the intent of the experiment**. When comparing `resolveClass` with `Class.forName(true)`, run the program from the command line and do not evaluate static fields in the debugger before reading stdout. If the class has already been initialized due to another operation, the experiment will not show the “Target initialized” line at the expected position.

## 14. Checklist for Choosing the Right API

| Goal | Appropriate API/Technique | Why |
| --- | --- | --- |
| Check whether a class can be found by name via a loader | `loader.loadClass(binaryName)` | Looks up the class; does not proactively initialize per the default contract |
| Have a class token and need to request linking in a custom loader | `resolveClass(token)` inside a subclass | Explicit link; does not automatically trigger `<clinit>` |
| Obtain a class token while wanting to defer initialization | `Class.forName(binaryName,false,loader)` | Does not request init |
| Want to ensure a class is initialized before entering the next lifecycle | `Class.forName(binaryName,true,loader)` | Requests init per runtime identity |
| Run normal application code | `new`/static method/field access | The JVM automatically links/initializes when needed; do not add manual `resolveClass` calls |
| Confirm the right version of a class was loaded | `clazz.getClassLoader()`, `clazz.getModule()`, source/dependency | Checks class identity/class source |
| Catch binary compatibility issues | Execute real code paths + integration tests | `resolveClass` does not guarantee all symbolic references are resolved |
| Debug initialization errors | Inspect `ExceptionInInitializerError.getCause()` and the first log | Distinguishes initialization failure from class not found |

### 14.1. “True/False” Questions with Answers

1. “`resolveClass` calls `<clinit>` of the passed-in class.” — **False**.
2. “`resolveClass` is `protected final void` in `ClassLoader`.” — **True**.
3. “`resolveClass` forces resolution of every method/field reference in the constant pool before returning.” — **False**.
4. “`loadClass(name, false)` guarantees the class is definitely still unlinked.” — **False**.
5. “`Class.forName(name, false, loader)` does not request initializing the class.” — **True**.
6. “`Class.forName(name, true, loader)` re-initializes on every call.” — **False**.
7. “A static initializer can throw an error after `resolveClass` previously returned successfully.” — **True**.
8. “A class can finish loading and linking, and only later encounter `NoSuchMethodError` at a call site.” — **True** if method reference resolution is performed lazily per the JVMS.
9. “`resolveClass(c)` changes the defining loader of `c` to the calling loader.” — **False**.
10. “If code is defined by another loader with an identical class name, it can be a separate runtime class and be initialized separately.” — **True**.

## 15. Primary References for Cross-Checking

1. [`ClassLoader.resolveClass` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html#resolveClass(java.lang.Class)) — `protected final`; the documentation specifies its primary function is to **link the specified class**, while noting the method name is somewhat misleading.
2. [`ClassLoader.loadClass(String, boolean)` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)) — sequence of `findLoadedClass` → delegation → `findClass` → `resolveClass` when the flag is true.
3. [`Class.forName` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)) — meaning of the `initialize` parameter.
4. [JVMS 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3) — class identity, defining/initiating class loaders.
5. [JVMS 5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4) — verification, preparation, resolution, and eager/lazy flexibility.
6. [JVMS 5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5) — `ConstantValue`, `<clinit>`, triggers, and the erroneous state.
7. [JLS 12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4) — active use, superclasses, superinterfaces, and thread coordination mechanism.

**Summary:** `resolveClass` is a **linking** facility of `ClassLoader`, not a call that runs the static initializer. The `resolve` flag in `loadClass` is not equivalent to `initialize` in `Class.forName`. To understand class loading errors accurately, always separate **loading → linking (verification/preparation/resolution) → initialization** and remember that the JVM can resolve symbolic references at different times.
