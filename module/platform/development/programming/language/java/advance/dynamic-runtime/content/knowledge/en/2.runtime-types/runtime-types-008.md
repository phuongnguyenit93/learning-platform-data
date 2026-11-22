# 2.8 Distinguishing class loading, linking, and initialization; controlling initialization via `Class.forName`

When Java encounters a type at runtime, the JVM does not necessarily perform all work related to that type immediately. **Loading, linking, and initialization** are distinct phases; distinguishing them helps control when `static` code runs, design plugin loading mechanisms, and diagnose runtime errors.

## 1. Learning outcomes

After this lesson, you can:

- Explain how finding/defining a class differs from verifying, preparing, and resolving references, and how it differs from running the `static` initializer.
- Predict whether actions such as `Target.class`, reading constants, `new Target()`, `ClassLoader.loadClass(...)`, and each overload of `Class.forName(...)` initialize `Target`.
- Proactively defer or request initialization, while understanding the limits of this choice.
- Analyze parent–child initialization order, default values of `static` fields, and initialization errors.

## 2. Three phases in a type's lifecycle

A practical view of the lifecycle is:

```text
Class name / bytecode
       |
       v
LOADING            Find class representation and create corresponding Class object
       |
       v
LINKING            Verification -> Preparation -> Resolution (*)
       |
       v
INITIALIZATION     Execute the static initialization part of the class/interface
       |
       v
Use the initialized type
```

`(*)` Resolution does not necessarily complete immediately along with verification/preparation: the JVM is allowed to resolve references eagerly or when actually needed. **Before initialization begins, the class must have been loaded, verified, and prepared**; this does not mean all of its symbolic references have been resolved. These steps can trigger loading or linking additional other types.

| Phase | What does the JVM do? | Does it run `static { ... }` of the class in question? |
| --- | --- | --- |
| **Loading** | Find bytecode/binary representation using a class loader, define the runtime type and its `Class<?>` object. | No, not merely because the class is loaded. |
| **Linking: verification** | Check bytecode structure, data types, validity of instructions, and JVM constraints. | No. |
| **Linking: preparation** | Allocate/set up state for `static` fields and assign initial **default values** (`0`, `false`, `null`...); may prepare internal structures. | Does not run author-written `static` assignment expressions. |
| **Linking: resolution** | Turn symbolic references to classes, fields, methods... into runtime entities and check linking/access constraints. | Does not by itself mean running `<clinit>`. |
| **Initialization** | Execute the class initializer: `static` values computed at runtime and `static` blocks in declaration order. | Yes, if the class has initialization code to run. |

### 2.1. Loading: knowing a type exists does not mean the type is initialized

Class loaders (bootstrap, platform, application, or custom loaders) participate in finding and defining classes. The JVM determines **the runtime identity of a class by its binary name combined with its defining class loader**: two loaders can define two classes with the same name that are different runtime types. Therefore, in plugin systems, the right class name is not enough; choosing the right loader is also important.

Loading a class can cause I/O, load additional classes, or execute the class loader's own work. The important point here is that **loading by itself is not a command to run the target class's `static` block**. One should not infer that the loading operation is always completely free of side effects across the entire application.

### 2.2. Linking: checking and preparing, without executing initialization logic

Consider a class with `static int count = 7;`. During preparation, memory for `count` is prepared with the default `0`; the assignment expression `7` belongs to initialization. A `static final` field that is a compile-time constant expression has special handling according to the specification, so do not use reading an inlined constant to infer the execution order of all initializers.

Verification can detect `VerifyError`. Resolution can detect `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, or other binary compatibility errors. **The timing of reporting resolution errors can differ between JVMs**, because resolution can occur during initial linking or when a specific reference is used.

### 2.3. Initialization: running the class's code, once per class definition

The JVM runs `static` field assignment expressions that are not compile-time constants and `static` blocks in textual order; javac typically combines them into an internal `<clinit>` method if needed. When initializing a class, an uninitialized superclass is initialized first; superinterfaces declaring default methods may also have to be initialized according to JVM rules. Initializing an interface **does not automatically** initialize all of its superinterfaces.

For a class definition that has already initialized successfully, subsequent initialization requests do not re-run the initializer. The JVM synchronizes initialization across threads; another thread needing to initialize the same class must wait rather than running it concurrently a second time. "Once" applies per class definition associated with a class loader, which does not mean all loaders share a single global `static` variable.

## 3. When is a class actually initialized?

For an uninitialized class `Target`, distinguish the following actions:

| Action | Does it require initializing `Target`? | Reason |
| --- | --- | --- |
| `Target.class` | **No**, not merely for obtaining the class literal | Obtaining `Class` is not an active use that triggers the initializer. |
| `ClassLoader.loadClass("pkg.Target")` | **Normally no** | The default mechanism loads the class without requiring the initializer to run; a custom loader may do other work. |
| `Class.forName("pkg.Target", false, loader)` | **No** | Requests finding/loading; `initialize=false` does not start initializing the target. It may still link and resolve dependencies. |
| `Class.forName("pkg.Target")` | **Yes** | Equivalent to the three-parameter overload with `initialize=true` and the calling class's loader. |
| `Class.forName("pkg.Target", true, loader)` | **Yes** | Ensures the class is initialized if it has not been initialized previously. |
| `new Target()` | **Yes** | Creating an instance requires the class to be initialized first. |
| `Target.staticMethod()` | **Yes**, if the method is declared on `Target` | Calling a `static` method is an active use. |
| Reading/writing a non-constant `static` field declared in `Target` | **Yes** | The JVM must initialize the class that actually declares the field. |
| Reading `Target.COMPILE_TIME_CONSTANT` (a primitive/`String` constant qualifying as a constant expression) | **No**, not merely for that operation | The compiler can inline the value; it is not an active use that initializes the class. |
| Creating `new Target[10]` | **No**, not merely for creating the array | Creating an array type does not require initializing the element type. |
| `type.getDeclaredConstructor().newInstance()` | **Yes**, when actually creating an instance | Reflection leads to object creation and class initialization if needed. |

**Note:** `static final` is not synonymous with compile-time constant. For example, `static final int A = 10;` is a constant variable; whereas `static final int B = Integer.parseInt("10");` requires running the expression at initialization time. If a `static` field declared in a parent class is accessed through a child class name, the JVM initializes **the class that actually declares the field**, not necessarily the child class.

## 4. Active control with `Class.forName`

### 4.1. The two most important overloads

```java
Class<?> a = Class.forName("com.example.Plugin");
Class<?> b = Class.forName("com.example.Plugin", false, pluginLoader);
Class<?> c = Class.forName("com.example.Plugin", true, pluginLoader);
```

This is an **API illustration snippet**, assuming `com.example.Plugin` exists and `pluginLoader` has been declared.

- `forName(String)` finds the class using the defining loader of **the class calling the API** and requests initialization (`true`); it does not default to choosing the thread context class loader.
- `forName(String, boolean, ClassLoader)` lets you choose the **loader** and the initialization timing. `false` is suitable for the type discovery or metadata inspection phase; `true` is suitable when intentionally triggering `static` logic.
- `initialize=false` **does not undo** a class that was already initialized beforehand, nor does it prevent another active use in the application from initializing the class later. It is not a "lock" keeping the class in an uninitialized state.
- `loader == null` in the three-parameter overload means using the bootstrap class loader, **not** automatically inferring the application loader.
- The overload `Class.forName(Module module, String name)` (Java 9+) has a different contract: it only attempts to find/load the class in the specified module, **does not link or initialize the class**, and returns `null` if not found. Do not confuse it with the overloads that throw `ClassNotFoundException`.

### 4.2. The class name must be a binary name

For a normal class, use `com.example.Plugin`; for a member class `Outer.Inner`, the binary name is typically `com.example.Outer$Inner`. Class names read from configuration must be checked accurately, including package and loader.

```java
Class<?> nested = Class.forName("java.util.Map$Entry", false,
        ClassLoader.getSystemClassLoader());
Class<?> strings = Class.forName("[Ljava.lang.String;", false,
        ClassLoader.getSystemClassLoader());
Class<?> matrix = Class.forName("[[I", false,
        ClassLoader.getSystemClassLoader());
Class<?> primitive = int.class;
```

For arrays, the name string follows the JVM descriptor format: `[Ljava.lang.String;` is `String[]`, `[[I` is `int[][]`. `Class.forName` for an array class may load the element type but **does not initialize the element type**, even when `initialize=true`. Do not use `Class.forName("int")` to obtain a primitive type; use `int.class` or `Integer.TYPE`.

## 5. Practice 1: observing when `static` runs

Create the file **`LoadLinkInitDemo.java`** with the following standalone content:

```java
public class LoadLinkInitDemo {
    static class Parent {
        static {
            System.out.println("Parent init");
        }
    }

    static class Target extends Parent {
        static final int CONST = 42;
        static int counter = createCounter();

        static {
            System.out.println("Target static block");
        }

        static int createCounter() {
            System.out.println("Target static field");
            return 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = LoadLinkInitDemo.class.getClassLoader();

        System.out.println("A. Class literal: " + Target.class.getSimpleName());
        System.out.println("B. Compile-time const: " + Target.CONST);

        System.out.println("C. forName(false)");
        Class<?> loaded = Class.forName(
                "LoadLinkInitDemo$Target", false, loader);
        System.out.println(loaded.getName());

        System.out.println("D. forName(true)");
        Class.forName("LoadLinkInitDemo$Target", true, loader);

        System.out.println("E. static value=" + Target.counter);

        System.out.println("F. forName(true) again");
        Class.forName("LoadLinkInitDemo$Target", true, loader);
    }
}
```

Compile and run with Java 17+:

```bash
javac LoadLinkInitDemo.java
java LoadLinkInitDemo
```

Output:

```text
A. Class literal: Target
B. Compile-time const: 42
C. forName(false)
LoadLinkInitDemo$Target
D. forName(true)
Parent init
Target static field
Target static block
E. static value=7
F. forName(true) again
```

**Explanation in order:**

1. `Target.class` obtains the `Class` object and `getSimpleName()` reads the name, without requiring `Target`'s initializer to run.
2. `Target.CONST` is `static final int` with the literal `42`, qualifying as a constant variable, so it is used by the compiler as a compile-time constant and does not trigger initialization.
3. `forName(..., false, ...)` returns the type information (`LoadLinkInitDemo$Target`). There are no `Parent init` or `Target ...` lines.
4. `forName(..., true, ...)` requests initialization for the first time. The JVM initializes `Parent` first, then processes the `counter` field (printing `Target static field`), then the `static` block next.
5. Reading `Target.counter` gives the value `7`; at this point the class is already initialized so no further initialization lines are printed.
6. Calling `forName(..., true, ...)` again does not re-execute the initializer.

Further experiment: move `D. forName(true)` below the statement that reads `Target.counter`. Then **reading the `static` field** becomes the first initializing operation and the initialization log lines appear before printing the value of `counter`.

## 6. Practice 2: how does preparation differ from initialization?

Create the file **`PreparationDemo.java`**:

```java
public class PreparationDemo {
    static class Example {
        static int first = readSecond();
        static int second = 9;

        static int readSecond() {
            System.out.println("second before assignment=" + second);
            return 5;
        }
    }

    public static void main(String[] args) {
        System.out.println("first=" + Example.first
                + ", second=" + Example.second);
    }
}
```

```bash
javac PreparationDemo.java
java PreparationDemo
```

Output:

```text
second before assignment=0
first=5, second=9
```

When class `Example` is prepared, both `first` and `second` have the default value `0`. During initialization, the assignment expression for `first` runs first and calls `readSecond()`; at that moment the statement `second = 9` has not yet executed, so it prints `0`. Afterward `second` receives `9`. The example intentionally reads the field through a method to illustrate the order; in real code, avoid circular dependencies or dependencies on unassigned `static` variables.

## 7. Errors and advanced characteristics to handle properly

### 7.1. Initialization can fail and the class enters an erroneous state

Create the file **`InitializationFailureDemo.java`**:

```java
public class InitializationFailureDemo {
    static class Broken {
        static int value = fail();

        static int fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Exception {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                Class.forName("InitializationFailureDemo$Broken");
            } catch (LinkageError error) {
                System.out.println(attempt + ". "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

```bash
javac InitializationFailureDemo.java
java InitializationFailureDemo
```

Output:

```text
1. ExceptionInInitializerError
2. NoClassDefFoundError
```

The first time, the initialization expression throws `IllegalStateException`, and the JVM wraps the cause in `ExceptionInInitializerError`. After the failure, the class definition `Broken` is in an erroneous state; attempting to initialize that definition again leads to `NoClassDefFoundError` (often with traces of the earlier cause). If the initializer throws an appropriate `Error`, the JVM may propagate that `Error` directly instead of wrapping it. **Do not "retry" initializing the same class by calling `forName(true)` repeatedly.** You need to fix the root cause, create a new environment/loader if the architecture allows, or restart the appropriate process.

### 7.2. Do not lump all errors into "class not found"

| Error / error group | Investigation direction |
| --- | --- |
| `ClassNotFoundException` | The requested loader could not find the binary name; check the name, classpath/module path, deployment, and loader. |
| `NoClassDefFoundError` | Error when the JVM needs a definition/dependency that was previously available or a class whose initialization failed; read `cause` and log **the first error**. |
| `VerifyError`, `ClassFormatError` | Bytecode is corrupted or invalid against JVM constraints. |
| `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` | Library version mismatch, API signature, module/access, or error during resolution. |
| `ExceptionInInitializerError` | `static` initialization code threw an error; check the initializer and root cause. |

`ClassNotFoundException` is a checked exception from class-finding APIs; many linkage/initialization errors are `Error`. Catch error types separately for diagnostics; do not swallow `LinkageError` and continue assuming the system is operating normally.

### 7.3. Concurrency, ordering, and side effects

- The JVM guarantees that a class definition will not have its initializer executed by two threads at the same time; a waiting thread may encounter an error if the first thread's initializer fails.
- An initializer can open connections, create threads, read configuration, or call code in other classes. `forName(true)` can therefore be an operation **with side effects**, even without `new` in the caller's code.
- Class loading, linking, and resolution can occur at times different from what one might infer from logs. Avoid relying on unspecified detailed ordering; rely only on the guarantees regarding initialization and active use.
- In systems with multiple class loaders, types with the same name but different loaders can have different `static` state and cannot be cast to one another.

## 8. Applying in a plugin loading or dynamic configuration system

Suppose configuration contains a plugin's class name. There are two separate needs:

1. **Discover/inspect before activating:** choose the right class loader, use `Class.forName(name, false, loader)` to obtain `Class<?>` and inspect the name, interfaces, annotations, or required constructor. Certain reflection operations may trigger loading or resolving related types; avoid assuming "uninitialized" means all metadata operations are side-effect-free.
2. **Activate at the decided time:** you can call `Class.forName(name, true, loader)` before use, so that the initialization timing and initialization errors are explicit. If right afterward you use reflection to invoke a constructor to create an instance, the instance creation action will also require initialization; calling `true` separately is not mandatory if an explicit activation boundary is not needed.

Decision pattern:

| Goal | Usually reasonable choice |
| --- | --- |
| Only read class description/discover plugin | `forName(name, false, loader)` |
| Require initializer to run immediately at the activate step | `forName(name, true, loader)` |
| Use application/plugin's own loader | Three-parameter overload with a verified loader |
| Want to create an instance immediately | Reflection constructor; remember that it initializes the class |
| Want to undo an initializer that has already run | No `forName` operation does this |

In production, verify the trustworthiness of the class name source and class loader. Loading a class does not automatically make that class "safe"; in particular, `initialize=true` can execute `static` code with the application's permissions. If you need to trace class loading on HotSpot, you can try `java -Xlog:class+load=info ...`; a class load log is **not** proof that the class has run `<clinit>`.

## 9. Common misconceptions and self-check

- **"Loaded = initialized."** False. A `Class<?>` can exist before `static` runs.
- **"Linking always resolves all classes/methods at once."** False. Resolution can be deferred.
- **"`Class.forName(name)` is the same as `ClassLoader.loadClass(name)`."** False regarding the initialization requirement of the standard API.
- **"`forName(false)` definitely avoids all other work."** False. It does not initialize *the target class*, but loading/linking and custom loader code still happen.
- **"Reading any `static final` never initializes the class."** False; only constant variables under compile-time rules have that exception.
- **"`forName(true)` always prints the log again."** False; a successful initializer runs only once per class definition.

Answer for yourself before viewing the hints:

1. Why might `Target.class` not print `static`, whereas `Class.forName("Target")` does?
2. When `Child extends Parent` and `Class.forName("Child", true, loader)` is called for the first time, which class's initializer runs first?
3. If `Target.X` is `static final int X = Integer.parseInt("8");`, does reading `Target.X` require initialization?
4. Why is `Class.forName("[Lpkg.Target;", true, loader)` not a way to proactively run `pkg.Target`'s initializer?
5. Why can a `NoClassDefFoundError` on the second use originate from an earlier `ExceptionInInitializerError`?

**Answer hints:** (1) A class literal is not an active use, while the one-parameter overload requests `initialize=true`. (2) `Parent` then `Child` if neither is initialized yet. (3) Yes, because `parseInt` is not a constant expression. (4) The name describes an array type, which only loads the element type without initializing it. (5) The JVM records that the class failed initialization and does not re-run the initializer for the same class definition.

## 10. Authoritative references

- [Java Language Specification 21, `12.2–12.4: Loading, Linking, Initialization](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html).
- [Java Virtual Machine Specification 21, Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html).
- [Java SE 21 API: `java.lang.Class` and `forName` overloads](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html).

By grasping the boundary **load → link → initialize**, you can accurately predict when `static` logic executes, use `Class.forName` for its intended purpose, and isolate runtime errors without confusing a loaded type with an initialized type.