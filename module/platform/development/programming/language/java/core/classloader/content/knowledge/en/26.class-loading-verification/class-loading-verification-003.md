# Verifying How loadClass Differs from Class.forName Regarding Class Initialization in Java

`ClassLoader.loadClass(...)` and `Class.forName(...)` can both return a `Class<?>` representing a Java type at runtime, but **they do not share the same guarantee regarding class initialization**. This matters when code uses reflection, plugins, SPI, dependency injection, or a custom `ClassLoader`: seeing `Class<?>` **does not yet mean** that static fields have received their final values or that the `static { ... }` block has executed.

**Core takeaways for Java 17+:**

- **`loader.loadClass("p.Target")`:** according to the standard `ClassLoader` implementation, locates/loads the class by binary name and **does not require initializing** the class. This overload is equivalent to calling `loadClass(name, false)`. Custom subclasses may add side effects; do not make inferences about uncontrolled overridden code.
- **`Class.forName("p.Target")`:** uses the class loader of the **caller** and **requires initializing** the class if not yet initialized.
- **`Class.forName("p.Target", true, loader)`:** selects the explicitly passed loader, **requires initializing** the class if needed.
- **`Class.forName("p.Target", false, loader)`:** locates/loads the class via the specified loader but **does not require initialization**.
- **`Class.forName(module, "p.Target")`:** the `Module` overload (Java 9+) only attempts to locate/load, **does not link or initialize per the API contract**, and returns `null` if not found; it is not equivalent to the single-`String` overload.

This lesson belongs to **Java core – classloader / Behavior Verification**. The goal is to **prove through controlled stdout** when `<clinit>` runs, distinguish loading/linking/initialization, and handle previously initialized classes, TCCL, compile-time constants, arrays, and initializer errors. The experiments prioritize **Java 17+**, providing standalone code, `javac`/`java` commands, and explanations of why the output is correct.

## 1. Three Phases: loading, linking, initialization

An easy-to-remember model:

```text
Class name + ClassLoader
         │
         ▼
       LOADING
     read/find bytes,
   create runtime Class<?>
         │
         ▼
       LINKING
 verification / preparation / resolution
         │
         ▼
    INITIALIZATION
  execute static field initializers
   and static initializer blocks
  (<clinit>) when required by JVM
         │
         ▼
  CLASS IS INITIALIZED
```

- **Loading:** creates or looks up a runtime class by name and loader. The parent may return a class defined by the parent, instead of the child defining it itself.
- **Linking:** the JVM verifies bytecode, prepares the static data area, and resolves symbolic references according to the specification's constraints. Some resolution may occur early or late; **the diagram should not be treated as a rigid schedule**.
- **Initialization:** executes the relevant static field initializers and static blocks in the specified order; the JVM guarantees that the initialization protocol takes place successfully only once for **each runtime class/interface**.

**Preparation is not initialization:** a static field may already have been prepared with its default value before a Java initializer assigns the intended value. Therefore, reading `Class<?>` via `loadClass` cannot prove that static state is "ready".

**Object creation is yet another step:** `ClassLoader.loadClass` or `Class.forName` does not automatically invoke an instance constructor; `new Target()` or `Constructor.newInstance()` is what creates the object. When a class is not yet initialized, creating an instance requires initialization before the constructor runs.

## 2. Comparison Table of Overloads on Java 17

| Call | Loader used | Requires initialization? | When not found |
| --- | --- | --- | --- |
| `loader.loadClass(name)` | `loader` object | **No** per the standard implementation | `ClassNotFoundException` |
| `Class.forName(name)` | Defining loader of the **caller class** | **Yes** | `ClassNotFoundException` |
| `Class.forName(name, true, loader)` | Specified loader; `null` means bootstrap | **Yes** | `ClassNotFoundException` |
| `Class.forName(name, false, loader)` | Specified loader | **No** | `ClassNotFoundException` |
| `Class.forName(module, name)` | Specified module and corresponding loader | **No**, and does not link per Javadoc | Returns `null` |
| `Target.class` | Compile-time type reference | **Does not require it by itself** | N/A; type must be valid in the compilation context |
| `new Target()` | Type resolved from bytecode | **Yes if needed** | May encounter loading/linking/initialization errors |

**Important:** `loadClass(name, false)` with `resolve=false` **does not mean the JVM is guaranteed to do no linking at all**. Some linking/verification may occur as part of the runtime. The supported conclusion here is that it **does not require executing the initializer**, not that "bytes were never inspected".

**Do not confuse `resolveClass` with initialization.** `ClassLoader.resolveClass(Class<?>)` is for linking; it is not an API that guarantees running `<clinit>`.

## 3. How to Create a Reliable Experiment

A common flawed experiment is:

```java
System.out.println(Target.value);
Class<?> result = loader.loadClass("demo.Target");
```

This is **the wrong snippet for verification purposes** if `Target.value` is a static field that is not a compile-time constant: the first field read may **have already initialized `Target` before `loadClass` is called**. In that case, not seeing the static block run on the second statement does not prove the intended point.

To observe properly:

1. Use a **target class with no prior active use**, ideally a different class for each test.
2. Print markers **before and after** the API under test.
3. Place a `System.out.println("INIT ...")` marker inside the target class's static initializer.
4. Use a **binary name string** to request loading without accidentally accessing a static member of the target class.
5. Run **each program in a fresh JVM process** when state needs to be reset. Successful initialization cannot be re-run by calling `forName` multiple times on the same runtime class.
6. If comparing two loaders, keep the **defining loader identity** clear and separate the plugin classpath from the host.
7. Do not use `Thread.sleep` to guess whether initialization has occurred; rely on markers and specified Java/JVM behavior.

On HotSpot, `-Xlog:class+load=info` logging can help observe loading, but the output is verbose and JVM-dependent. **A static initializer marker is a simpler proof of initialization timing** in small demos.

## 4. Practice A — `loadClass`, `forName(false)`, and `forName(true)`

Create the project:

```text
initialization-lab/
└── src/demo/LoadVsForNameDemo.java
```

**`src/demo/LoadVsForNameDemo.java`:**

```java
package demo;

public final class LoadVsForNameDemo {
    static final class LoadOnly {
        static {
            System.out.println("INIT LoadOnly");
        }
    }

    static final class FalseTarget {
        static {
            System.out.println("INIT FalseTarget");
        }
    }

    static final class TrueTarget {
        static {
            System.out.println("INIT TrueTarget");
        }
    }

    static final class ActiveTarget {
        static {
            System.out.println("INIT ActiveTarget");
        }

        static void ping() {
            System.out.println("PING ActiveTarget");
        }
    }

    private static String binaryName(String simpleName) {
        return LoadVsForNameDemo.class.getName() + "$" + simpleName;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader app = LoadVsForNameDemo.class.getClassLoader();

        System.out.println("1 before loadClass");
        Class<?> loaded = app.loadClass(binaryName("LoadOnly"));
        System.out.println("2 loaded=" + loaded.getSimpleName());

        System.out.println("3 before forName(false)");
        Class<?> notInitialized = Class.forName(
                binaryName("FalseTarget"), false, app);
        System.out.println("4 loaded=" +
                notInitialized.getSimpleName());

        System.out.println("5 before forName(true)");
        Class<?> initialized = Class.forName(
                binaryName("TrueTarget"), true, app);
        System.out.println("6 loaded=" +
                initialized.getSimpleName());

        System.out.println("7 initialize the earlier LoadOnly");
        Class<?> later = Class.forName(
                binaryName("LoadOnly"), true, app);
        System.out.println("8 same Class=" + (loaded == later));

        System.out.println("9 before active use");
        ActiveTarget.ping();
        System.out.println("10 finished");
    }
}
```

From the `initialization-lab` directory, compile/run on **JDK 17+**:

```sh
javac --release 17 -d out src/demo/LoadVsForNameDemo.java
java -cp out demo.LoadVsForNameDemo
```

**Expected stdout in a fresh JVM:**

```text
1 before loadClass
2 loaded=LoadOnly
3 before forName(false)
4 loaded=FalseTarget
5 before forName(true)
INIT TrueTarget
6 loaded=TrueTarget
7 initialize the earlier LoadOnly
INIT LoadOnly
8 same Class=true
9 before active use
INIT ActiveTarget
PING ActiveTarget
10 finished
```

### Reading the Results Section by Section

- At lines **1–2**, `app.loadClass(...)` returns `Class<?>` for `LoadOnly` **without printing `INIT LoadOnly`**. `getSimpleName()` only retrieves name metadata and does not require static initialization of the target class.
- Lines **3–4** also do not print `INIT FalseTarget`: the `Class.forName(name, false, app)` overload locates/loads the class but **does not require initialization**.
- Lines **5–6** have `INIT TrueTarget` **between the two markers**: the `Class.forName(name, true, app)` overload requires initialization before returning successfully.
- After line **7**, `Class.forName(..., true, app)` receives **the very runtime `LoadOnly` previously returned by `loadClass`**, but this time requires initialization. Thus `INIT LoadOnly` appears, and then `loaded == later` equals `true`.
- At lines **9–10**, calling `ActiveTarget.ping()` is an **active use** of a static method, forcing initialization of `ActiveTarget` before printing `PING`.
- `FalseTarget` **never prints its initializer** throughout the entire program, because no operation forces it to initialize.

**What is actually measured:** the experiment does not prove that `loadClass` "does not read bytecode"; it proves that it **does not trigger static initialization** under this invocation.

## 5. How Does `Class.forName(String)` Differ from the Three-Parameter Overload?

Short form:

```java
Class<?> type = Class.forName("demo.Target");
```

Based on the Javadoc, it uses the **defining loader of the caller class** and **requires initialization**. There is no `initialize=false` parameter in this overload.

Conceptual equivalent when in code belonging to class `Caller`:

```java
Class<?> type = Class.forName(
        "demo.Target", true, Caller.class.getClassLoader());
```

This is an **illustrative snippet** assuming `Caller` exists and the actual caller is `Caller`. When code resides inside a framework/library, the **caller class loader** may differ from the plugin loader that the application wants to use. Therefore, for plugins, it is generally advisable to pass an **explicit loader** to the three-parameter overload.

**TCCL is not automatically used by `Class.forName(String)`.** `Thread.currentThread().getContextClassLoader()` is a separate mechanism, commonly used by SPI libraries such as `ServiceLoader.load(service)`. Changing TCCL does not turn `Class.forName(name)` into "look up using TCCL".

## 6. Practice B — Changing TCCL Does Not Change the Loader of `forName(String)`

This exercise illustrates two independent points: (1) a class that a **child URLClassLoader** can load is not necessarily on the host classpath; (2) `Class.forName(name)` uses the caller's loader and **does not automatically read TCCL**.

File tree:

```text
loader-choice-lab/
├── src/
│   ├── plugin/feature/PluginTarget.java
│   └── host/demo/LoaderChoiceDemo.java
├── plugin-out/
└── host-out/
```

**`src/plugin/feature/PluginTarget.java`:**

```java
package feature;

public final class PluginTarget {
    static {
        System.out.println("INIT PluginTarget");
    }

    public static String message() {
        return "plugin ready";
    }
}
```

**`src/host/demo/LoaderChoiceDemo.java`:**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderChoiceDemo {
    public static void main(String[] args) throws Exception {
        String name = "feature.PluginTarget";
        URL pluginRoot = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[] {pluginRoot},
                    ClassLoader.getPlatformClassLoader())) {

            Class<?> loaded = pluginLoader.loadClass(name);
            System.out.println("loaded by plugin=" +
                    (loaded.getClassLoader() == pluginLoader));

            Thread thread = Thread.currentThread();
            ClassLoader oldContext = thread.getContextClassLoader();

            try {
                thread.setContextClassLoader(pluginLoader);

                try {
                    Class.forName(name);
                    System.out.println("unexpected one-arg success");
                } catch (ClassNotFoundException expected) {
                    System.out.println("one-arg not found=true");
                }

                Class<?> noInit =
                        Class.forName(name, false, pluginLoader);
                System.out.println("false same Class=" +
                        (loaded == noInit));

                System.out.println("before explicit true");
                Class<?> yesInit =
                        Class.forName(name, true, pluginLoader);
                System.out.println("true same Class=" +
                        (loaded == yesInit));
            } finally {
                thread.setContextClassLoader(oldContext);
            }
        }
    }
}
```

Compile from `loader-choice-lab`:

```sh
javac --release 17 -d plugin-out src/plugin/feature/PluginTarget.java
javac --release 17 -d host-out src/host/demo/LoaderChoiceDemo.java
```

Run (intentionally putting **only** `host-out` on the application classpath):

```sh
java -cp host-out demo.LoaderChoiceDemo
```

**Expected stdout in the configuration above:**

```text
loaded by plugin=true
one-arg not found=true
false same Class=true
before explicit true
INIT PluginTarget
true same Class=true
```

Explanation:

1. The parent is the platform loader, which does not know about `feature.PluginTarget` in the `plugin-out` directory. `URLClassLoader` locates the class from its own URL.
2. `pluginLoader.loadClass` returns the runtime `Class<?>` without yet printing `INIT PluginTarget`.
3. Even though the current thread's TCCL was changed to `pluginLoader`, `Class.forName(name)` inside `LoaderChoiceDemo` still uses the **host caller's loader**; the host does not have the plugin on `-cp`, resulting in `ClassNotFoundException`.
4. `Class.forName(name, false, pluginLoader)` receives the exact class the child just loaded and still does not initialize it.
5. `Class.forName(name, true, pluginLoader)` triggers `<clinit>`, printing `INIT PluginTarget` before returning.
6. All three class references `loaded`, `noInit`, and `yesInit` are the **same `Class<?>`** of the plugin loader. The difference is **initialization state**, not class identity.
7. The `finally` block restores the old TCCL; for pooled threads, forgetting to restore it can leak the plugin loader or affect subsequent SPI discovery.

**Do not add `plugin-out` to `-cp`** when running the example: doing so would allow the host's `Class.forName(name)` to find the class, losing the comparison value.

## 7. Operations That Change the State of a `Class`

`loadClass` and `Class.forName(name, false, loader)` **do not by themselves require initialization**. `new`, calling a static method, reading a non-constant static field, assigning a static field, or `Class.forName(name, true, loader)` can be a trigger. `T.class` and reading a compile-time constant do not by themselves force `T` to be initialized. For an inherited static field, the trigger targets **the type that declares the field**; initializing a class also brings in its superclass and certain superinterfaces that have default methods. The lessons on class initialization have explained the underlying rules; this lesson verifies the exact effects of the overloads.

## 8. Practice C — Constant, Class Literal, and Runtime Field

Source file `src/demo/ConstantVsInitDemo.java`:

```java
package demo;

public final class ConstantVsInitDemo {
    static final class Values {
        static {
            System.out.println("INIT Values");
        }

        static final int COMPILE_TIME = 7;
        static final int RUNTIME = Integer.parseInt("8");
    }

    public static void main(String[] args) throws Exception {
        System.out.println("constant=" + Values.COMPILE_TIME);

        System.out.println("literal=" +
                Values.class.getSimpleName());

        ClassLoader app = ConstantVsInitDemo.class.getClassLoader();
        Class<?> c = Class.forName(
                ConstantVsInitDemo.class.getName() + "$Values",
                false, app);

        System.out.println("forName(false) returned=" +
                c.getSimpleName());

        System.out.println("before runtime field");
        System.out.println("runtime=" + Values.RUNTIME);
        System.out.println("runtime again=" + Values.RUNTIME);
    }
}
```

Compile/run in the project containing `src/demo/ConstantVsInitDemo.java`:

```sh
javac --release 17 -d out src/demo/ConstantVsInitDemo.java
java -cp out demo.ConstantVsInitDemo
```

**Stdout:**

```text
constant=7
literal=Values
forName(false) returned=Values
before runtime field
INIT Values
runtime=8
runtime again=8
```

**Why is there a difference?**

- `COMPILE_TIME` is a **constant variable** because `static final int` is assigned a constant expression `7`. The Java compiler can embed the value into caller code; using this field does not trigger initialization of `Values`.
- `Values.class` provides `Class<?>` **without requiring** the static initializer to run.
- `Class.forName(..., false, app)` obtains `Class<?>` while still leaving the target uninitialized.
- `RUNTIME` **is not a compile-time constant** even though it is `static final`, because `Integer.parseInt("8")` is a method call. The first read of `Values.RUNTIME` requires initialization: printing the marker and then setting `RUNTIME=8`.
- The `runtime again=8` line does not print the marker again because `Values` **has already been initialized successfully**.

**Major pitfall:** `static final` **is not synonymous with** a compile-time constant. Only a subset of types and expressions meet the JLS definition of a *constant variable*. For example, `static final String S = new String("x")` is not a compile-time constant.

## 9. `Class.forName(..., true, ...)` Does Not Create an Object Instance

Consider:

```java
Class<?> type = Class.forName(name, true, loader);
```

The call may cause the target's `static { ... }` to run, but it **is not `new`**. The instance constructor does not run until an object-creation operation occurs.

For reflection:

```java
Class<?> type = Class.forName(name, false, loader);
// Here, the target is not yet required to be initialized.

Object object = type.getDeclaredConstructor().newInstance();
// When the instance is created, the JVM requires the target to be initialized if needed.
```

These are **snippets** that require `name` and `loader` along with exception handling. If the constructor is non-public, you may also run into `IllegalAccessException` or JPMS access rules; do not simply call `setAccessible(true)` and assume every module is open.

Bytecode-level distinction:

- `<clinit>`: class/interface initialization from static initializers and static field assignments.
- `<init>`: instance initialization and constructor chain of each object.

The JVM executes `<clinit>` **at most once successfully per runtime class**; many objects of that class can be created afterward, with a corresponding `<init>` each time.

## 10. Does Calling `forName(true)` Again Run the Initializer a Second Time?

**No**, if the class has already been initialized successfully. A subsequent call may return the same runtime `Class<?>` without repeating the side effects of `<clinit>`.

Example:

```java
Class<?> first = Class.forName(name, true, loader);
Class<?> second = Class.forName(name, true, loader);
System.out.println(first == second);
```

This is a **snippet** assuming `name` and `loader` are the same, the target exists, and there is no custom loading behavior breaking the contract. `true` for comparing the same runtime definition; the target's static initializer **is not run again** because of the second `forName` call.

### Can a Class Be Initialized Multiple Times in a JVM by Name?

If **two different defining loaders** each define the **same binary name**, the JVM treats them as **two separate runtime classes**, so each class has its own initialization state. A plugin reload example:

```text
("plugin.Widget", loader-generation-1)
    → runtime Class A → initializer A

("plugin.Widget", loader-generation-2)
    → runtime Class B → initializer B

A.getName().equals(B.getName()) → true
A == B                           → false
```

However, if a parent-first `loader-generation-2` **receives class A from its parent**, it does not create class B itself. Log the defining loader using `Class.getClassLoader()` when you need to confirm isolation.

## 11. Practice D — Initializer Errors Only Appear When Initialization Is Requested

This program distinguishes **"successfully loading bytes"** from **"successful class initialization"**. We use a class whose static initializer intentionally throws an exception, and actively track two active uses.

File `src/demo/InitFailureDemo.java`:

```java
package demo;

public final class InitFailureDemo {
    static final class Broken {
        static int value = compute();

        private static int compute() {
            System.out.println("INIT Broken");
            throw new IllegalStateException("invalid configuration");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = InitFailureDemo.class.getName() + "$Broken";
        ClassLoader app = InitFailureDemo.class.getClassLoader();

        Class<?> loaded = app.loadClass(name);
        System.out.println("loaded without init=" +
                (loaded.getClassLoader() == app));

        try {
            Class.forName(name, true, app);
        } catch (ExceptionInInitializerError error) {
            System.out.println("first error=" +
                    error.getClass().getSimpleName());
            System.out.println("root cause=" +
                    error.getCause().getClass().getSimpleName());
        }

        try {
            Class.forName(name, true, app);
        } catch (NoClassDefFoundError error) {
            System.out.println("second error=" +
                    error.getClass().getSimpleName());
        }
    }
}
```

Compile/run with JDK 17+ in a fresh JVM:

```sh
javac --release 17 -d out src/demo/InitFailureDemo.java
java -cp out demo.InitFailureDemo
```

**Stdout:**

```text
loaded without init=true
INIT Broken
first error=ExceptionInInitializerError
root cause=IllegalStateException
second error=NoClassDefFoundError
```

**Explanation:**

1. `loadClass` successfully returns the runtime type of `Broken` without forcing `compute()` to run.
2. `Class.forName(name, true, app)` triggers initialization; `compute()` prints the marker and then throws `IllegalStateException`.
3. Because the exception thrown from the initializer is not an `Error`, the JVM wraps it in `ExceptionInInitializerError`, while also marking the class in the **erroneous** state.
4. Calling `Class.forName(..., true, ...)` again on the **same runtime class** does not re-run the initializer; the JVM reports `NoClassDefFoundError` related to the erroneous state.
5. `NoClassDefFoundError` does not always mean the `.class` file has disappeared. It can be a consequence of **a previous initialization failure**.

**Why not place `throw new IllegalStateException(...)` directly inside an unconditional static block?** In Java source, a static initializer is not allowed to "cannot complete normally" under syntax/control-flow checks. Writing a `compute()` call in a field initializer creates an example that compiles and has a failure at runtime.

**Operations:** do not "fix" this by calling `loadClass` again. Within the same runtime class, initialization does not reset. You need to inspect the **first root cause** and handle the class loader lifecycle if loading a new generation is truly necessary.

## 12. `Class.forName(Module, String)` Is a Completely Different Overload

Java 9+ added:

```java
Class<?> found =
        Class.forName(SomeType.class.getModule(), "pkg.Target");
```

This is an **illustrative snippet**; the module/type must exist. According to the **Java 17 Javadoc**:

- The method accepts a **`Module` object**, not a `ClassLoader`.
- It attempts to locate/load a class belonging to the exact given module.
- It **does not link** the target class and **does not run the class initializer**.
- If there is no class by that binary name in that module, the result is **`null`**, unlike the `ClassNotFoundException` of the three-parameter overload.
- It does not by itself guarantee that the class is accessible to the caller; runtime module access checks must still be considered when using members.
- If the module's loader defines other modules, a name belonging to another module might be loaded, yet the method **returns null** because it does not belong to the specified module.

**Do not write tests that only compare the string `Class.forName` while ignoring the signature**. `Class.forName(String)` and `Class.forName(Module, String)` do not have the same initialization semantics.

## 13. Special Case: Array Class Does Not Initialize the Component Type

The `Class.forName(name, boolean, loader)` Javadoc has an exception: if `name` denotes an **array class**, the JVM loads the component type but **does not initialize the component type solely because of the array lookup**.

Example name of `demo.Item[]` in `Class.getName()` form:

```text
[Ldemo.Item;
```

The syntax with `[L` and `;` is a JVM binary descriptor-like name for object arrays, different from the source name `demo.Item[]`.

### Practice E — Array Lookup and Element Initialization

**`src/demo/ArrayInitDemo.java`:**

```java
package demo;

public final class ArrayInitDemo {
    static final class Element {
        static {
            System.out.println("INIT Element");
        }

        Element() {
            System.out.println("CONSTRUCT Element");
        }
    }

    public static void main(String[] args) throws Exception {
        String elementName = ArrayInitDemo.class.getName() + "$Element";
        String arrayName = "[L" + elementName + ";";
        ClassLoader app = ArrayInitDemo.class.getClassLoader();

        System.out.println("before array forName(true)");
        Class<?> arrayClass = Class.forName(arrayName, true, app);
        System.out.println("array loaded=" + arrayClass.isArray());

        Element[] values = new Element[2];
        System.out.println("array length=" + values.length);

        System.out.println("before new element");
        values[0] = new Element();
        System.out.println("after new element");
    }
}
```

Compile/run:

```sh
javac --release 17 -d out src/demo/ArrayInitDemo.java
java -cp out demo.ArrayInitDemo
```

**Stdout:**

```text
before array forName(true)
array loaded=true
array length=2
before new element
INIT Element
CONSTRUCT Element
after new element
```

**Why?** `Class.forName(arrayName, true, app)` returns the runtime **array class**, without forcing the `Element` component to be initialized. `new Element[2]` creates an array with elements initially `null`, without creating an `Element` object. Only `new Element()` on the later line requires initializing the component class, and then calls the constructor.

Do not wrongly generalize that `forName(..., true, ...)` always runs the initializer of **every type mentioned in the name**. You must check the class/interface/array cases per the Javadoc.

## 14. Runtime Class Identity: Same Name, Same `Class<?>`, Different State

In Practice A:

```text
app.loadClass("demo.LoadVsForNameDemo$LoadOnly")
    └── returns Class<?> C, init not yet requested

Class.forName("demo.LoadVsForNameDemo$LoadOnly", true, app)
    └── returns the same Class<?> C, but requests init before returning
```

The difference **is not different bytecode or a different loader**. The `Class<?>` object has the same identity across both lookups. Only the **initialization side effect** differs.

Verify:

```java
System.out.println(loaded == later);
System.out.println(loaded.getClassLoader() == app);
```

These two snippets assume the variable names from Practice A. To understand why a static field has its default value or its complete value, you need to distinguish between the **prepared but not initialized** and **initialized** states — the `ClassLoader` API does not provide a general public `isInitialized(Class<?>)` method to check the state without doing anything else.

**Do not try to infer initialized status merely from having a `Class<?>` or `classLoader.findLoadedClass`.** `findLoadedClass` returns information regarding a class whose loading was initiated by the loader, not a status API for `<clinit>`.

## 15. Parent Type Initialization When Testing `forName(true)`

Requesting initialization of a class may run the static initializer of an uninitialized superclass and superinterfaces that declare default methods before that class's static code. However, requesting initialization of an interface does not automatically initialize all superinterfaces. When testing `forName(true)`, place the marker in the exact expected type and record the **order** if inheritance is present. This rule is separate from which loader locates/defines the type.

## 16. Why a Fresh Runtime Class Is Needed for Each Test

The JVM synchronizes initialization so that only one thread executes the initializer of the **same runtime class**, while other threads wait for the result. Once successful, repeating `Class.forName(name, true, loader)` does not re-run the marker. When an error occurs, the same class definition becomes erroneous; see the failure experiment in section 11. To measure the first trigger independently, use a new defining loader that actually creates a new class or launch a fresh JVM, as guided in the final lesson of the chapter.

## 17. Do Not Confuse Initialization Errors with Loading and Reflection Errors

- `ClassNotFoundException` when looking up a name does not prove the initializer ran.
- `ExceptionInInitializerError` usually wraps an unchecked exception from the initial initializer run; afterward, the same runtime class may report `NoClassDefFoundError` because it is erroneous.
- Reflection/constructors also have `InvocationTargetException`, `IllegalAccessException`, and other failures. Inspect the cause and the test step location; do not attribute every error from calling `forName` to **class loading**.

## 18. Verification When Using Plugins or `URLClassLoader`

A plugin framework typically performs:

```java
Class<?> impl = pluginLoader.loadClass("plugin.ServiceImpl");
Object service = impl.getDeclaredConstructor().newInstance();
```

This is a **snippet** that requires a plugin loader and exception handling. If the implementation has a static initializer:

- `loadClass` in the standard way **does not yet require** running the initializer.
- `getDeclaredConstructor()` only retrieves constructor metadata and does not invoke the constructor body.
- `Constructor.newInstance()` is reflective instance creation and may **require class initialization**.
- An `ExceptionInInitializerError` may occur during instance creation, even though `loadClass` completed successfully.

If the framework replaces `loadClass` with `Class.forName(name, true, pluginLoader)` during the **discovery** phase, it may execute the plugin's static code earlier than expected. This can cause I/O, network connections, thread creation, or thrown errors before the lifecycle phase managed by the host.

**Design recommendation:** during discovery, clearly distinguish between "knowing which types can be used" and "when initializer code is allowed to run". Use the appropriate loader and API, then activate the service in a startup phase with logging, timeouts, and permissions according to the architecture.

## 19. `ServiceLoader` and TCCL Are a Different Experiment

`ServiceLoader.load(SPI)` typically uses TCCL to locate descriptors and providers; whereas `Class.forName(String)` has loader selection tied to the caller. In a plugin, do not rely on changing TCCL to conclude that `forName(String)` will see all classes of the plugin. The lesson **Verifying Resource Lookup and Service Providers** separates checking SPI identity, resource descriptors, and provider instantiation.

## 20. Reflection: Metadata Inspection Only or Actual Type Usage?

`type.getDeclaredConstructors()` and `type.getDeclaredMethods()` typically only read metadata, whereas `constructor.newInstance()`, `Field.get(null)` on a static field, or `Method.invoke(null, ...)` for a static method can trigger initialization. Therefore, the result "`loadClass` does not print the marker" is only valid if **no subsequent operation** has yet created an instance or invoked a static member. Separate each action with its own marker as in section 4.

## 21. Pre-Initialized Case: Why "Seeing No Marker" Is Not Enough

If class `Target` was already used before the measurement section:

```java
Target.ping();             // this call may have already initialized it
loader.loadClass("Target");
Class.forName("Target");
```

This is **pseudocode** whose binary name needs to be adjusted properly. When calling the two APIs afterward, the static initializer is no longer printed even though `Class.forName` still requests initialization per its contract, because the JVM sees that the class **is already initialized**.

Therefore, you cannot run a program and conclude:

> "`Class.forName` does not initialize because I didn't see `static { }` print anything."

A valid conclusion must consider the **state prior to the call**. The exercises in the README intentionally use separate classes or fresh processes.

### How to Improve the Test

- Create a **new target class with no prior active use** for each check.
- Place markers adjacent to the API statements.
- Do not use a target's non-constant static field to build the class name.
- If you need to test multiple times, run a fresh `java` process for each run instead of expecting the class initializer to be reset.
- If testing reload through a new loader, check `type.getClassLoader()` to ensure the parent did not silently provide the same old type.

## 22. Practice F — `Class.forName(String)` Has the Same Init Result as true When the Caller Sees the Class

To confirm the **one-parameter** overload, use a new target class in the project on the application classpath.

File **`src/demo/OneArgumentForNameDemo.java`**:

```java
package demo;

public final class OneArgumentForNameDemo {
    static final class Target {
        static {
            System.out.println("INIT Target");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = OneArgumentForNameDemo.class.getName()
                + "$Target";

        System.out.println("before one-arg");
        Class<?> type = Class.forName(name);
        System.out.println("after one-arg");
        System.out.println("same defining loader=" +
                (type.getClassLoader()
                        == OneArgumentForNameDemo.class.getClassLoader()));
    }
}
```

Compile/run:

```sh
javac --release 17 -d out src/demo/OneArgumentForNameDemo.java
java -cp out demo.OneArgumentForNameDemo
```

**Stdout:**

```text
before one-arg
INIT Target
after one-arg
same defining loader=true
```

The `Class.forName(name)` call requests initialization before returning, so `INIT Target` appears between the two markers. `type.getClassLoader()` matches the loader of the caller `OneArgumentForNameDemo` because the entire program is on the application classpath under this run command.

**Compared to Practice B:** the one-parameter overload succeeds here because the target is on the **caller's classpath**; in Practice B, the target was only in the plugin loader's dedicated URL, so that overload failed even though TCCL had been switched.

## 23. How to Inspect Bytecode to Rule Out "Optimizer Removed the Initializer"

When using compile-time constants, the compiler may emit `ldc`/`bipush`/`sipush` instead of `getstatic`. Inspecting the bytecode helps explain why using a constant does not initialize the declaring class.

Example from Practice C:

```sh
javap -classpath out -c -p demo.ConstantVsInitDemo
javap -classpath out -c -p 'demo.ConstantVsInitDemo$Values'
```

In POSIX/PowerShell shells, single quotes around the nested binary name help preserve the `$` character. `javap` can show that `<clinit>` of `Values` contains the marker printing and `Integer.parseInt("8")`; the `main` method can use the embedded constant value.

**Caution:** `javap` only reads class files on disk and **does not by itself prove** that the JVM selected that class file through the runtime loader graph. If the classpath has multiple versions of the same binary name, you must combine it with `Class.getClassLoader()`, `ProtectionDomain.getCodeSource()`, and `-Xlog:class+load`.

## 24. Diagnostic Logging Helpful for the Loading/Initialization Distinction

A simple helper once you already have `Class<?>`:

```java
static void describe(Class<?> type) {
    ClassLoader definingLoader = type.getClassLoader();
    Module module = type.getModule();

    System.out.println("class=" + type.getName());
    System.out.println("loader=" +
            (definingLoader == null
                    ? "<bootstrap>" : definingLoader.getClass().getName()));
    System.out.println("module=" +
            (module.isNamed() ? module.getName() : "<unnamed>"));
}
```

This is an **illustrative method**; the metadata lines **do not force `<clinit>` of the target to run**. Do not use `Class.forName(name)` merely to log metadata of a class not yet looked up, because that overload may initialize the target. When you only want to know which class is loaded through a loader, prefer `Class.forName(name, false, loader)` if there is a genuine reason to perform a lookup.

If you need to log the **CodeSource** of a class, use a null-safe path:

```java
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();
var url = source == null ? null : source.getLocation();
System.out.println(url == null ? "<unknown>" : url.toExternalForm());
```

This snippet requires an existing `type`; the URL may contain a filesystem path or internal information, so avoid exposing it in client logs. CodeSource does not by itself prove bytecode integrity or confirm that the target has been initialized.

### JDK Unified Logging

On HotSpot supporting Unified Logging:

```sh
java -Xlog:class+load=info -cp out demo.LoadVsForNameDemo
java -Xlog:help
```

Loading logs can show when a class is found/loaded, but they **are not logs confirming that the static block has run**. Some HotSpot versions also provide the `class+init` tag; check `-Xlog:help` first. Do not hardcode the stdout of these logging commands, as metadata/timestamps/VM versions differ.

## 25. Debugging: What to Check If Output Differs from Expected Stdout?

| Symptom | Common hypothesis | How to check |
| --- | --- | --- |
| `INIT` appears before `loadClass` | Target already had active use before measurement | Separate the target class; run a fresh JVM |
| `INIT` does not appear on `forName(true)` | Class was already initialized earlier; or target has no printing initializer | Inspect the entire code path and loader identity |
| `Class.forName(name)` fails while `child.loadClass(name)` succeeds | Caller loader cannot see the child's private URL | Pass `child` to the three-parameter overload |
| Changing TCCL still leaves `forName(String)` failing | One-parameter overload does not automatically use TCCL | Print caller loader and TCCL; use explicit loader |
| `Class.forName(name,false,loader)` encounters `LinkageError` | Not initializing does **not** rule out loading/linking errors | Read stacktrace, verify dependencies, bytecode |
| `Class.forName(name,true,loader)` throws `ExceptionInInitializerError` | Static initializer threw an exception or dependency init failed | Check root cause/initializer code |
| Next `forName(true)` call throws `NoClassDefFoundError` | Class is already erroneous due to previous init | Fix root cause, reset via appropriate lifecycle |
| Array `forName(true)` does not print component marker | Array lookup does not initialize element type | Actively use the element class separately |
| `static final` does not produce `INIT` | Field is a compile-time constant | Compare with `javap`, use a non-constant static field for testing |
| Plugin class ends up defined by host loader | Parent-first or plugin directory is on host classpath | Print `type.getClassLoader()`, check `-cp` and URLs |
| Constructor message seen after `forName(true)` | Code inside `<clinit>` may itself create an object; not forName creating an instance itself | Inspect the static initializer and stacktrace |
| Test runs differently in IDE | IDE puts plugin output on host classpath or runs reused JVM/test order | Run separate `javac/java` commands and identify the classpath |

An "unexpected" result is usually due to **the environment and order of active use** rather than the JVM randomly altering the API contract.

## 26. Misconceptions to Avoid

- **"`loadClass` and `Class.forName` only differ in syntax."** False: initialization semantics and loader selection may differ.
- **"Having a `Class<?>` means the static block has run."** False; the class may only be loaded/linked.
- **"`loadClass` is guaranteed not to cause linking errors."** False; not requiring init is different from not performing linking.
- **"`Class.forName(name, false, loader)` guarantees no bytecode is loaded."** False; it can still load the class, it only does not require the initializer.
- **"`Class.forName(name)` always uses TCCL."** False; it uses the caller class's loader.
- **"`Class.forName(name, true, loader)` always creates an object."** False; it returns `Class<?>` and does not run the instance constructor.
- **"`static final` always keeps a class from initializing when read."** False; only compile-time constant variables have this exception.
- **"`Target.class` will run the static initializer."** Not under normal class literal behavior.
- **"Calling `forName(true)` twice will run the static block twice."** False for the same successfully initialized runtime class.
- **"A binary name only initializes once across the entire JVM."** False if different defining loaders create different runtime class identities.
- **"`Class.forName(module,name)` is the same as `Class.forName(name)`."** False: the module overload does not link/init and returns `null` if not found.
- **"Array `forName(true)` always initializes the component class."** False according to the Javadoc.
- **"`NoClassDefFoundError` always means a missing `.class` file."** False if previous class initialization failed.
- **"Using `loadClass` is enough to guarantee a plugin runs no code before startup."** Not absolute: custom loaders, linking/dependencies, and application code can create side effects; analyze the full execution path.
- **"A JVM test rerun resets the static initializer between test methods."** Not if the same runtime class in the same process/loader is still used.
- **"Logging the class name proves whether the parent or child defined it."** No; you need `Class.getClassLoader()`.

## 27. Quick Verification Checklist

1. Choose a target class **with no prior active use**; have its static initializer print a unique marker.
2. Print markers before/after each API.
3. Use the correct binary name (`Outer$Inner` for a nested class).
4. Explicitly record the caller loader, explicit loader, parent, and TCCL if applicable.
5. Test `loadClass` → verify no `INIT` before active use.
6. Test `Class.forName(name, false, loader)` on a separate target → verify no `INIT`.
7. Test `Class.forName(name, true, loader)` → `INIT` marker appears before the method returns successfully.
8. Test `Class.forName(name)` with a class belonging to the caller loader → confirm the initializer and caller loader.
9. Test a `static final` compile-time constant versus a runtime-initialized static field.
10. Test array class lookup and array creation, then creating an element instance.
11. Test an initializer throwing an error → `ExceptionInInitializerError` first and `NoClassDefFoundError` afterward, preserving the root cause.
12. Run each experiment in a fresh JVM when a reset is needed.
13. Do not accidentally add plugin output to the application classpath.
14. Check `Class<?>` identity and defining loader when comparing two loader instances.
15. For production, do not use `Class.forName(..., true, ...)` merely for discovery when static initialization is not yet permitted.

## 28. Self-Check Questions with Answers

**1. Does `loader.loadClass("p.T")` require running `<clinit>` by default?** No.

**2. How does `Class.forName("p.T")` differ from `loadClass` regarding initialization?** It requires initializing the target if it is not yet initialized.

**3. How do you load a class via a specified loader without requiring initialization?** `Class.forName("p.T", false, loader)` or `loader.loadClass("p.T")` under standard behavior.

**4. Does `Class.forName("p.T", true, loader)` return an object instance or a `Class<?>`?** `Class<?>`; it does not automatically run the instance constructor.

**5. Does changing TCCL change the loader used by `Class.forName(String)`?** No. That overload uses the caller class loader.

**6. How does `Class.forName(Module,String)` differ?** It does not link/init per Javadoc and returns `null` if the class does not belong to the requested module.

**7. Why does `static final int N=7` not print the initializer when read?** It is a constant variable, which may be inlined by the compiler.

**8. Why can `static final int N=Integer.parseInt("7")` print the initializer?** It is not a constant expression, so reading the field triggers initialization.

**9. Do two calls to `Class.forName(name,true,loader)` run the initializer twice?** No, if the same runtime class has already been initialized successfully.

**10. Can `getDeclaredConstructor().newInstance()` initialize the class?** Yes, because creating an instance is an active use.

**11. Does array `Class.forName("[Lp.T;", true, loader)` force `p.T` to initialize?** No, according to the Javadoc for array classes.

**12. Why can a subsequent active use after a failed class initialization throw `NoClassDefFoundError`?** The runtime class is in the erroneous state, and the initializer is not retried.

**13. Do two class loaders defining the same binary name share the same initialization state?** No; they are two distinct runtime types.

**14. Is `resolveClass` equivalent to `Class.forName(..., true, ...)`?** No. `resolveClass` relates to linking and does not require class initialization.

**15. If a program does not print `INIT` on `Class.forName(name)`, what should you check first?** Whether the target was already initialized earlier, the binary name/loader identity, and whether the experiment uses a fresh class/fresh JVM.

**16. Why can testing class initialization with a static constant be misleading?** Because the compiler may inline the value and not emit an active-use `getstatic` on the declaring class.

## 29. Official References

- [Java SE 17 — ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass(String)` and `loadClass(String, boolean)`, parent delegation, `resolveClass`.
- [Java SE 17 — Class Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName(String)`, `forName(String, boolean, ClassLoader)`, `forName(Module, String)` and initialization semantics.
- [JLS Java SE 17 — 12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, static field, static method, superclass/interface initialization.
- [JLS Java SE 17 — 12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): initialization state, coordination, and erroneous classes.
- [JVMS Java SE 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading/linking/initialization and runtime class identity.
- [Java SE 17 — Constructor Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): reflective instance creation and related initialization.
- [Java SE 17 — URLClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): classpath-style plugin loader and parent delegation.
- [JDK 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting `<clinit>` bytecode and constant folding.

**Conclusion:** standard `loadClass` and `Class.forName(name, false, loader)` help locate/load a class **without requiring initialization**; `Class.forName(name)` and `Class.forName(name, true, loader)` **require initialization**, but only if the runtime class is not yet initialized. Distinguish **selected loader, initialization state, active use, and class identity**, and then verify using static initializer markers in **a fresh JVM** to avoid false conclusions from a class having already been initialized earlier.
