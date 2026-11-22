# Class.forName(name, initialize, loader) — Class Loading, Initialization, and Choosing a ClassLoader

## 1. Why Is the Three-Parameter Overload Needed?

Java allows looking up a class by its **string name** at runtime. The method:

```java
public static Class<?> forName(
        String name,
        boolean initialize,
        ClassLoader loader
) throws ClassNotFoundException
```

resides in `java.lang.Class`. It addresses three separate decisions:

1. **`name`:** the binary name of a class/interface or a string describing an array type to look up.
2. **`initialize`:** whether to request the JVM to perform **class/interface initialization** after successfully finding and loading it.
3. **`loader`:** which ClassLoader is used to locate the class; if `null` is passed, it requests using the bootstrap class loader.

The result is a `Class<?>` — **an object describing a runtime type**. `Class.forName` does not create an instance of the target class, does not invoke its instance constructor, and does not guarantee that you have permission to invoke all members of the class via reflection.

Usage example in a plugin application:

```java
// Snippet: pluginLoader is created and configured elsewhere.
Class<?> pluginType =
        Class.forName("com.example.plugin.Handler", false, pluginLoader);

// We now have the Class<?> of the type, but this request has not initialized Handler yet.
```

If `false` is changed to `true`, the method will **request initialization of Handler if Handler has not yet been initialized**. This may execute `static` field assignments and `static` blocks, potentially triggering application code, I/O, or exceptions. This difference is especially important for applications with plugins, service registries, and reflection-based libraries.

## 2. Conceptual Processing Flow

With `Class.forName(name, initialize, loader)`, the JVM must locate the corresponding runtime type and follow the loading/linking/initialization rules:

```text
Class.forName(name, initialize, loader)
       │
       ├─ Determine name format:
       │      ├─ Binary name of class/interface
       │      └─ Descriptor of array type
       │
       ├─ Use specified loader to find/load type
       │      └─ Delegation policy depends on the specific ClassLoader
       │
       ├─ Link/verify per JVM requirements
       │      └─ loading/linking errors may still occur
       │
       └─ If it is a regular class/interface:
              ├─ initialize=false → do not request initialization
              └─ initialize=true  → initialize if not yet completed
                                      └─ static field initializers / blocks
          If name is an array descriptor:
              → JVM creates/obtains array class;
                element class is loaded but not
                initialized solely because of this forName call
       │
       ▼
Return Class<?> or throw exception/error
```

This is a **semantic diagram**, not a mechanical description of the order of every verification/resolution step. The JVM may defer resolving certain symbolic references until needed. The key guarantee is that when a class needs to be initialized, it must undergo verification and preparation as required beforehand.

`Class.forName` **does not arbitrarily choose a suitable loader on its own**. The caller decides the `loader` parameter; that loader and its delegation chain determine which class, if any, can be found.

## 3. The name Parameter: Binary Names and Array Descriptors

### 3.1. Binary Name of Regular Classes

For a top-level class:

```java
Class<?> c = Class.forName(
        "java.util.ArrayList",
        false,
        ClassLoader.getSystemClassLoader()
);
```

`name` is `"java.util.ArrayList"`, **not** the path `"java/util/ArrayList.class"`, the string `"ArrayList.class"`, or a source declaration.

For a nested/member class, the binary name typically uses the `$` character. For example, in the file `Outer.java`:

```java
public class Outer {
    static class Inner {
    }
}
```

The binary name of the member class `Inner` is `Outer$Inner` (with the package prefix if present). When calling:

```java
// Snippet, assuming the Outer class is already on the classpath.
Class<?> inner = Class.forName(
        "Outer$Inner",
        false,
        Outer.class.getClassLoader()
);
```

`"Outer.Inner"` follows the canonical source-name notation, **not a valid binary name** for a member class in this situation. Names of anonymous/local classes also have compiler-generated characteristics; it is better to get `SomeClass.class.getName()` when you already have `Class<?>` instead of guessing the name.

For generic types, the name `"java.util.List<java.lang.String>"` is also invalid for `forName`; generic arguments do not create a separate runtime class due to type erasure. Use `"java.util.List"`.

### 3.2. Array Type Names Are Descriptors

For an array class, `name` is not written as `"java.lang.String[]"`. It uses the JVM descriptor syntax:

| Java Type | String Passed to `forName` |
|---|---|
| `int[]` | `"[I"` |
| `boolean[]` | `"[Z"` |
| `long[][]` | `"[[J"` |
| `String[]` | `"[Ljava.lang.String;"` |
| `String[][]` | `"[[Ljava.lang.String;"` |
| `mypackage.Widget[]` | `"[Lmypackage.Widget;"` |

One `[` denotes one dimension. `L...;` encloses the binary name of the reference component. Common primitive codes include `Z`, `B`, `C`, `D`, `F`, `I`, `J`, `S` for boolean, byte, char, double, float, int, long, and short.

**Special rule:** if `name` represents an **array class**, the element class may be loaded but is **not initialized**, **regardless of whether `initialize=true` or `false`**. Calling `Class.forName("[Lmypackage.Widget;", true, loader)` is not a shortcut to execute `Widget.<clinit>`.

### 3.3. Primitives and void Cannot Be Looked Up with This Overload

Names such as `"int"`, `"boolean"`, `"void"`, and the letter descriptor `"I"` when passed as a standalone `name` **do not** return `int.class` or `void.class`. The API will attempt to look up a class with that name; typically you will get a `ClassNotFoundException`.

To obtain the `Class` object for a primitive or void, use:

```java
Class<?> integerType = int.class;
Class<?> voidType = void.class;
```

If you need a primitive array, use `Class.forName("[I", false, loader)` or `int[].class`.

## 4. The initialize Parameter: How Do false and true Differ?

| `initialize` | For a regular class/interface | For an array descriptor |
|---|---|---|
| `false` | Requests finding/loading the class, does **not** request running the initializer | Creates/obtains the array class; does not initialize the element class |
| `true` | After finding/loading, requests initialization if not yet completed | The element class is still **not** initialized by this call |

### 4.1. When initialize=false

`Class.forName(name, false, loader)` can return a `Class<?>` so you can inspect metadata such as `getName()`, `getDeclaredMethods()`, or check type identity without proactively initializing the target class. However:

- The class may **have already been initialized earlier** by another call; `false` does not “undo” that state.
- The JVM may still need to **load/link** the class and related types; `false` is not a guarantee of “no other activity” or “no errors can occur”.
- Subsequent reflection operations such as invoking a static method, reading a static field, or creating an instance may require initialization.
- A custom loader may have **its own side effects during loading**; `false` only controls the initialization request of the target class per API semantics and does not disable any code implemented by the loader itself.

### 4.2. When initialize=true

`Class.forName(name, true, loader)` requests the JVM to initialize the target class/interface **if it has not already been initialized**. For a class, initialization includes static field initializer expressions and `static { ... }` blocks in source order; the appropriate superclasses are initialized first according to JVM/JLS rules.

Do not interpret `true` as "re-running the static block on every call": successful initialization is recorded **once per runtime class/interface**. For the same `Class<?>`, calling `forName(..., true, ...)` again does not re-execute `<clinit>`.

If the initializer fails, `Class.forName` may throw `ExceptionInInitializerError` on the first initialization attempt (or propagate an error in the `Error` hierarchy according to JLS rules). The failed runtime class becomes erroneous; subsequent initialization requests may encounter `NoClassDefFoundError` instead of retrying.

## 5. Runnable Example: Observing false → true → true

Create the file `ForNameDemo.java`:

```java
public class ForNameDemo {
    static class Target {
        static int counter = initializeCounter();

        private static int initializeCounter() {
            System.out.println("Target initialized");
            return 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ForNameDemo.class.getClassLoader();

        System.out.println("start");
        Class<?> type = Class.forName(
                "ForNameDemo$Target", false, loader
        );
        System.out.println("loaded: " + type.getSimpleName());

        System.out.println("before init");
        Class<?> again = Class.forName(
                "ForNameDemo$Target", true, loader
        );
        System.out.println("same Class: " + (type == again));

        Class.forName("ForNameDemo$Target", true, loader);
        System.out.println("counter=" + Target.counter);
    }
}
```

Using JDK 17+:

```bash
javac ForNameDemo.java
java ForNameDemo
```

Stdout:

```text
start
loaded: Target
before init
Target initialized
same Class: true
counter=7
```

**Explanation:**

1. The first call passes `false`: the JVM returns the `Class<?>` of `Target`, but does not request running `initializeCounter()`.
2. `type.getSimpleName()` reads metadata of `Class<?>`, without running Target's static initializer.
3. The second call passes `true`: it requests initializing Target, so `Target initialized` is printed exactly once and `Target.counter=7` is assigned.
4. `type == again` is `true` because both represent the same runtime class.
5. The third call with `true` does not re-run the initializer; reading `Target.counter` prints the value 7.

**It is not the case that** `initialize=false` means "return only the name", or that `initialize=true` means "create an instance". Both return a `Class<?>` object; they differ in whether initialization is requested.

## 6. The loader Parameter: Selecting the Runtime Namespace

### 6.1. Why Pass the Loader Explicitly?

A class is fundamentally identified by the JVM by its **binary name together with its defining ClassLoader**. Two independent loaders can define two classes with the same name that are not the same runtime class; casting or mismatched linking between them can fail even though the name strings are identical.

In `Class.forName(name, initialize, loader)`, the `loader` parameter specifies the loader that **initiates the class lookup process**. That loader may apply parent-first delegation and return a class **defined by a parent**. Therefore:

```java
Class<?> type = Class.forName(name, false, pluginLoader);
ClassLoader definingLoader = type.getClassLoader();
```

This is a snippet, requiring `name` and `pluginLoader` at the call site. `definingLoader` **is not necessarily equal to** `pluginLoader`: the class may be defined by a parent/bootstrap loader. Check `type.getClassLoader()` when diagnosing why the wrong library is being used.

If **`loader=null`** is passed, the API uses the **bootstrap class loader**. This is not a "flexible default" or "use the system loader" option. For example:

```java
Class<?> stringType =
        Class.forName("java.lang.String", false, null);
System.out.println(stringType == String.class);
```

Inside a Java method with `throws ClassNotFoundException` or catching the corresponding exception, stdout is `true`. However, a plugin class located only in a custom loader's directory will typically not be found by the bootstrap loader.

### 6.2. Comparison with the One-Parameter Overload

`Class.forName("mypackage.Handler")` is semantically equivalent to `Class.forName("mypackage.Handler", true, currentLoader)`, where `currentLoader` is the **defining loader of the class containing the call** per the API specification. It does not automatically use `Thread.currentThread().getContextClassLoader()`.

Comparison:

```java
// Snippet: the class and loader must exist in the appropriate context.

Class<?> a = Class.forName("mypackage.Handler");
// Requests initialize=true and uses the calling class's loader.

Class<?> b = Class.forName(
        "mypackage.Handler", false, explicitlyChosenLoader
);
// Does not request initialize; uses the explicitly passed loader.
```

A thread context class loader (TCCL) may be set by a framework to support SPI/plugins. If you want to use it, you must **explicitly pass it**:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "mypackage.Handler", false, context
);
```

This is a **snippet**, not a standalone program. Note that `context` can be `null`; passing `null` to the three-parameter overload means using the bootstrap loader, so plugin applications need to choose/check an explicit fallback before calling.

### 6.3. Access to the Looked-Up Class Is Not Guaranteed

`Class.forName` **does not check beforehand whether the caller has permission to access the target class**. Obtaining a `Class<?>` does not grant permission to invoke constructors or `private`/package-private members. Java access control, module rules, and reflection constraints still apply afterward. Calling `setAccessible(true)` does not automatically bypass module encapsulation in modern JDKs.

## 7. Runnable Example: Finding a Class in a Plugin Directory via URLClassLoader

This example illustrates explicit loader selection and the effect of the `initialize` flag. We compile the plugin class **into a directory not on the host classpath**, then use `URLClassLoader` to read it.

### 7.1. Create Plugin.java

```java
package demo;

public final class Plugin {
    static {
        System.out.println("Plugin initialized");
    }

    public static String greet() {
        return "Hello plugin";
    }
}
```

### 7.2. Create PluginHost.java

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginHost {
    public static void main(String[] args) throws Exception {
        URL pluginDir = Path.of("plugin-classes").toUri().toURL();
        ClassLoader parent = PluginHost.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[] { pluginDir }, parent)) {

            System.out.println("before loading");

            Class<?> type = Class.forName(
                    "demo.Plugin", false, pluginLoader
            );
            System.out.println("defined by plugin loader: "
                    + (type.getClassLoader() == pluginLoader));

            System.out.println("before initialization");
            Class<?> initialized = Class.forName(
                    "demo.Plugin", true, pluginLoader
            );
            System.out.println("same runtime class: "
                    + (type == initialized));

            Class.forName("demo.Plugin", true, pluginLoader);
            Object message = type.getMethod("greet").invoke(null);
            System.out.println(message);
        }
    }
}
```

### 7.3. Compile and Run

In the directory containing `Plugin.java` and `PluginHost.java`:

```bash
mkdir plugin-classes
javac -d plugin-classes Plugin.java
javac PluginHost.java
java -cp . PluginHost
```

Resulting files:

```text
working-directory/
├── Plugin.java
├── PluginHost.java
├── PluginHost.class
└── plugin-classes/
    └── demo/
        └── Plugin.class
```

**Do not add the `plugin-classes` directory to the host classpath**. `java -cp . PluginHost` only puts the host class on the classpath. If the plugin class is added to the host classpath, the parent can load it first and the defining loader comparison will produce a different result, because `URLClassLoader` uses parent-first by default.

Stdout when running in a fresh JVM with the structure above:

```text
before loading
defined by plugin loader: true
before initialization
Plugin initialized
same runtime class: true
Hello plugin
```

**Meaning of the output:**

- `forName("demo.Plugin", false, pluginLoader)` allows the loader to find and define Plugin, **without requesting to run** the static block yet.
- `getClassLoader()==pluginLoader` is `true` because the parent does not find Plugin, and URLClassLoader defines the class itself.
- `forName(..., true, pluginLoader)` requests initialization for the first time; the static block prints `Plugin initialized`.
- The subsequent `true` call returns the same runtime class and does not re-execute the static block.
- `getMethod("greet").invoke(null)` invokes the static method and receives the string; Plugin is already initialized so no other initializer execution occurs.
- Closing `URLClassLoader` via try-with-resources releases URL/JAR resources held by the loader; it is **not an immediate unload command** for the defined class. Unloading depends on the JVM's ability to garbage-collect the loader/class once they are no longer reachable.

If you want a second copy of `demo.Plugin` with the same name but a different identity, use a **new** defining loader that does not delegate to a parent that already has Plugin. It is not possible to create another definition in the same loader simply by calling `forName` again.

## 8. Runnable Example: Array Descriptor Name Does Not Initialize the Element Class

Create the file `ForNameArrayDemo.java`:

```java
public class ForNameArrayDemo {
    static class Element {
        static {
            System.out.println("Element initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ForNameArrayDemo.class.getClassLoader();

        System.out.println("before array forName");
        Class<?> arrayType = Class.forName(
                "[LForNameArrayDemo$Element;",
                true,
                loader
        );
        System.out.println("array type: " + arrayType.getTypeName());
        System.out.println("component name: "
                + arrayType.getComponentType().getSimpleName());

        System.out.println("before component initialization");
        Class.forName(
                "ForNameArrayDemo$Element", true, loader
        );
        System.out.println("done");
    }
}
```

Run using JDK 17+:

```bash
javac ForNameArrayDemo.java
java ForNameArrayDemo
```

Stdout:

```text
before array forName
array type: ForNameArrayDemo$Element[]
component name: Element
before component initialization
Element initialized
done
```

Even though the first call uses `initialize=true`, the name passed in is an **array descriptor**. Java creates/obtains the array class and loads the element type as needed, but **does not run the Element static initializer** from this operation. The static block runs only when the second call requests initializing **Element itself**.

For a primitive array:

```java
Class<?> primitiveArray = Class.forName(
        "[I", true, ForNameArrayDemo.class.getClassLoader()
);
System.out.println(primitiveArray == int[].class);
```

This is a snippet for a method that already declares `throws ClassNotFoundException`; the `println` line outputs `true` on a standard Java SE JVM. There is no initializer for the primitive `int`.

## 9. Failure Cases During Lookup/Loading/Initialization

| Error or exception | When it typically occurs | Causes to check |
|---|---|---|
| `ClassNotFoundException` | The name cannot be found via the specified loader | Binary name, plugin directory/JAR, parent delegation, module/classpath |
| `LinkageError` | Loading/linking does not satisfy JVM rules | Incompatible bytecode, duplicate definitions, conflicting binary dependencies |
| `UnsupportedClassVersionError` | Bytecode is newer than what the JVM supports | Class file major/minor version, actual Java runtime running |
| `ExceptionInInitializerError` | A static initializer throws a non-`Error` exception during init | Root cause from `<clinit>` or static assignment expressions |
| `NoClassDefFoundError` after failed initialization | The runtime class is in an erroneous state | The first init error, rather than just the classpath |
| `SecurityException` | When applicable security permission checks exist | Security manager/permissions, environment in use |

`ClassNotFoundException` is a **checked exception**; code calling `forName` must declare `throws` or `catch` it. Errors in the `LinkageError` hierarchy are not declared in `throws` but can still occur. Do not catch all errors and treat them as “class does not exist”.

### 9.1. Failed Initialization Example

Create `ForNameFailureDemo.java`:

```java
public class ForNameFailureDemo {
    static class Broken {
        static int state = failure();

        static int failure() {
            throw new IllegalStateException("bad initialization");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ForNameFailureDemo.class.getClassLoader();
        String name = "ForNameFailureDemo$Broken";

        System.out.println("loaded without initialization: "
                + (Class.forName(name, false, loader) != null));

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                Class.forName(name, true, loader);
            } catch (LinkageError error) {
                System.out.println(
                        attempt + ": " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

Run:

```bash
javac ForNameFailureDemo.java
java ForNameFailureDemo
```

Stdout:

```text
loaded without initialization: true
1: ExceptionInInitializerError
2: NoClassDefFoundError
```

Because `initialize=false` does not request running `failure()`, the first call succeeds. The first `true` call triggers the code and throws `IllegalStateException`; the JVM wraps it in `ExceptionInInitializerError`. Once the runtime class is erroneous, the next `true` call does not re-run the initializer and typically throws `NoClassDefFoundError`.

This is why you must inspect the **cause of the first failure**, not just the message from subsequent accesses. If you want to retry while learning, run a new JVM process; reusing the same runtime class in the same process does not automatically recover the state.

## 10. Distinguishing from ClassLoader.loadClass

Both APIs can return `Class<?>`, but the aspects they control differ:

| Criterion | `Class.forName(name, initialize, loader)` | `loader.loadClass(name)` |
|---|---|---|
| Called via | Static method of `Class` | Method of `ClassLoader` |
| Loader selection | Passed explicitly; `null` means bootstrap | Uses the loader object on which the method is called |
| Requests initialization by default? | Depends on the `initialize` parameter | No; the public overload is equivalent to `loadClass(name, false)` |
| Accepts array descriptor? | Yes, syntax such as `[Ljava.lang.String;` | Not a portable way to request an array type from a custom loader |
| Result | `Class<?>` | `Class<?>` |
| Error when class is missing | `ClassNotFoundException` | `ClassNotFoundException` |
| Creates an instance? | No | No |

**Do not equate `initialize=true` with `resolve=true`** in the protected `ClassLoader.loadClass(name, resolve)`. `resolveClass(c)` requests linking, whereas initialization additionally involves executing static initializers. Similarly, `getDeclaredMethods()`, `getAnnotations()`, or other reflection operations have their own loading/linking conditions; reading metadata does not automatically imply invoking `<clinit>`.

### When to Prefer Which API?

- You have a **binary name** and want to ensure the class is initialized: `Class.forName(name, true, chosenLoader)`.
- You have a name and only want to inspect metadata without static side effects yet: `Class.forName(name, false, chosenLoader)`.
- You are implementing a ClassLoader and only need to look up a class according to loader rules: `loader.loadClass(name)`.
- You know the exact class at compile time: usually use `SomeType.class`, avoiding string-based lookup when dynamic lookup is not needed.
- You have an array component `Class<?>` when building plugins: use `java.lang.reflect.Array.newInstance(componentClass, size)` to obtain an array object/array class with the right defining loader.

## 11. Class.forName(Module, String) Is a Different API

Since Java 9, there is an overload:

```java
public static Class<?> forName(Module module, String name)
```

It is **not equivalent** to the three-parameter overload:

- Looks up a class/interface by binary name in the **specified module**.
- Does not initialize the class; according to the API documentation, it does not perform linking in the way the three-parameter overload requires.
- If the class is not found in that module, it can return `null` instead of throwing `ClassNotFoundException`.
- It does not support array descriptors such as `"[Ljava.lang.String;"`.
- Obtaining a `Class<?>` still does not grant access to members restricted by module/package.

Therefore, when working with modules, you should not directly replace `Class.forName(name, false, loader)` with `Class.forName(module, name)` and assume the same contract.

## 12. Practical Issues with Plugins and Frameworks

### 12.1. Right Name, Wrong Loader

A plugin contains `com.acme.Plugin`, yet the host calls:

```java
Class.forName("com.acme.Plugin");
```

If the host's loader cannot find the plugin class, the call fails with `ClassNotFoundException`, even though the plugin file actually exists on the machine. The solution is to determine the **appropriate ClassLoader** for the plugin and pass it to the three-parameter overload.

An inverse issue: both the host and the plugin bundle a shared API class. If the custom loader uses child-first loading for that API, the two runtime classes with the same binary name cannot be cast to each other; having equal `getName()` values does not mean the `Class<?>` objects are equal. You should keep communication APIs between host and plugin defined by an appropriate shared loader.

### 12.2. initialize=true Has Side Effects

With a plugin registry, calling `forName(name, true, loader)` while *scanning the list* can run static blocks even when the plugin has not yet been selected for use. If the initializer spawns threads, connects to a database, writes logs, or configures global state, a simple scan can turn into an expensive or error-prone operation.

One way to separate responsibilities:

1. **Discovery:** look up the class with `initialize=false`, inspect metadata, and check prerequisite conditions.
2. **Validation:** verify that the class matches the API, module/loader, and required constructor/method types.
3. **Activation:** when actually using the plugin, perform an operation that requires initialization and create an appropriate instance.
4. **Failure handling:** distinguish between missing class, incompatible linkage, failed initialization, and application logic errors.

Even though `false` avoids requesting initialization of the **target class**, inspection via reflection can still load related types, and some framework methods have side effects of their own. Do not blindly assume that discovery is an operation that cannot throw errors.

### 12.3. Parent-First or Child-First Is Up to the Loader

`Class.forName` **does not alter the delegation policy**. If a custom loader inherits the default `ClassLoader.loadClass`, it prioritizes `findLoadedClass`, then the parent loader, and only then `findClass`. If the loader overrides `loadClass` with conditional child-first rules, `Class.forName` uses the actual behavior of that loader.

To diagnose, log all of:

```java
// Snippet after obtaining Class<?> type:
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
```

The trio of name/defining loader/module helps identify the runtime class that was found, especially when multiple JARs contain the same binary name.

## 13. Class.forName Diagnostic Checklist

When a `Class.forName` call produces an unexpected result, check in order:

1. Does **the `name` string** use the exact **binary name**? For a nested class, does it use `$`? For an array, does it use a descriptor with `[` and `L...;`? Were `.class`, `/` slashes, or generic arguments accidentally included in the name?
2. What is **the passed-in loader**? Is it `null`, the host loader, TCCL, or a plugin-specific loader? Could a parent find a different class with the same name first?
3. Is **`initialize`** `true` or `false`? Could the static block have already run from an earlier usage? Are you calling with an array descriptor, leaving the element still uninitialized?
4. Has **the runtime type been verified** using `type.getName()`, `type.getClassLoader()`, and, where applicable, `type.getModule()`?
5. **Which category does the error belong to**: `ClassNotFoundException`, `LinkageError`, `ExceptionInInitializerError`, or a reflection/access error? Read the full cause and the first failure, not only subsequent retry calls.
6. Is **the JDK/runtime** the right version for the bytecode and module access? `ClassNotFoundException` is not the only explanation for every loading error.
7. **Test in a fresh JVM** if you are checking initialization order: an already initialized class will not execute its static block again for the same runtime class.
8. **Check the plugin's dependencies**: finding the entry-point class does not guarantee that every class it uses will link and run successfully.
9. **Do not use `Class.forName` to “hot reload”** an already defined class; you need to design an appropriate plugin/loader lifecycle and reload mechanism.

## 14. Self-Check Questions

1. **Does `Class.forName("p.Service", false, loader)` run `Service.<clinit>`?** It does not actively request it; Service may have already been initialized earlier.
2. **Does `Class.forName("p.Service", true, loader)` return a Service object?** No; it returns `Class<?>` and may run the static initializer.
3. **Does calling `forName` twice with `true` run `<clinit>` twice?** No, if the same runtime class has already been successfully initialized.
4. **Does passing `loader=null` use the system class loader?** No; this overload selects the bootstrap loader.
5. **Is `Class.forName("Outer.Inner")` right for looking up a member class `Outer.Inner` in source?** Ordinarily no; the binary name is `Outer$Inner`.
6. **Does `Class.forName("int")` return `int.class`?** No; use `int.class` or a dedicated primitive lookup API when supported.
7. **To look up `String[][]` via the three-parameter overload, what is name?** `"[[Ljava.lang.String;"`.
8. **Does `Class.forName("[Lp.Widget;", true, loader)` force Widget to initialize?** No; the array component class is not initialized by this call.
9. **Does using `Class.forName("p.Service")` implicitly pick up TCCL?** No; it uses the caller's defining loader per the one-parameter overload contract.
10. **If a plugin class is defined by a parent, does `type.getClassLoader()` always equal the loader passed to forName?** No; the parent/boot loader may be the defining loader.
11. **Does finding `Class<?>` mean you are allowed to invoke every private method?** No; Java access rules and module boundaries still apply.
12. **When `Class.forName(Module, String)` does not find a class, does it throw CNFE like the three-parameter overload?** No; it can return `null` and has its own contract.

## 15. Official Documentation

- [Java SE 21 API — `java.lang.Class.forName(String, boolean, ClassLoader)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): per-parameter contract, array descriptors, exceptions, and overload differences.
- [Java SE 26 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): newer API documentation, including `forPrimitiveName(String)` in versions that support it.
- [Java SE 21 API — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): loading, parent-first, `findLoadedClass`, `findClass`, defining loader.
- [JLS — 12.2 Loading; 12.3 Linking; 12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html): rules for initializing static state, superclasses, reflection, and loading/linking.
- [JVMS — 5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): type identity, link/initialize, and erroneous state.

The key takeaway when designing applications with dynamic ClassLoaders is that **the three parameters control three different things**: `name` identifies the queried type, `loader` determines the search path and the runtime identity that can be obtained, and `initialize` decides whether to request executing initialization logic yet. Distinguishing them helps avoid both plugin-not-found errors and premature initializer execution.
