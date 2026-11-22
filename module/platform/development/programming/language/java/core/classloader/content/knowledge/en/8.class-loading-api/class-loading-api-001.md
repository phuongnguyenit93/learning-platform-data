# `ClassLoader.loadClass` and the Meaning of the `resolve` Parameter

## 1. Lesson Objectives

In Java, the `ClassLoader.loadClass` method returns the `Class<?>` object corresponding to a class or interface name. However, it is important to clearly distinguish:

- **Loading**: The JVM finds or creates the runtime type definition.
- **Linking**: The JVM verifies, prepares, and resolves the necessary references of the type definition.
- **Initialization**: The JVM executes static initialization code according to active-use rules.

For `ClassLoader`, there are two important overloads:

~~~java
public Class<?> loadClass(String name) throws ClassNotFoundException;

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException;
~~~

The **single-parameter** overload behaves equivalently to calling **`loadClass(name, false)`**. In the two-parameter overload, **`resolve == true`** requests the **`resolveClass(c)`** step in the default algorithm, meaning it requests linking the found `Class` object; it is **not a class initialization flag**.

This lesson answers practical questions:

1. How does `loadClass` locate classes through the parent delegation mechanism?
2. At which step does the `resolve` flag take effect?
3. Why might `resolve=true` still not execute a static block?
4. When should `Class.forName` with the `initialize` flag be used instead of `loadClass`?
5. How can you write and test a `ClassLoader` subclass without confusing loading, linking, and initialization?

## 2. Signatures and Contracts of the Two Overloads

| API | Access Scope | Key Behavior |
| --- | --- | --- |
| `loadClass(String name)` | `public` | Loads/finds a class by binary name; by default, calls the two-parameter overload with `resolve=false`. |
| `loadClass(String name, boolean resolve)` | `protected` | In the default implementation, performs delegation and, when `resolve=true`, calls `resolveClass(c)` on the result. |
| `resolveClass(Class<?> c)` | `protected final` | Requests the JVM to link the class if not yet linked; the class may have been defined by another loader. |
| `findLoadedClass(String name)` | `protected final` | Checks for a class for which the JVM has already recorded the loader as an initiating loader, helping avoid reloading the same name. |
| `findClass(String name)` | `protected` | Extension point for the loader to find/define the class itself when delegation does not find it. |

**Note on visibility:** normal application code **cannot directly call** `loader.loadClass("a.B", true)` unless it is within the `protected` access scope. A compilable example is calling **`loader.loadClass("a.B")`**, or creating a subclass with a public wrapper for instructional purposes.

`name` is typically a **binary name** such as `java.lang.String` or `demo.Widget`. For a nested member class with the binary name `example.Outer$Inner`, the `$` symbol is part of the binary name. Do not confuse this binary name with the resource path `example/Outer$Inner.class`.

## 3. Default Algorithm of `loadClass(name, resolve)`

The `ClassLoader` documentation describes the default implementation as parent-first. Diagram:

~~~text
loadClass(name, resolve)
          │
          ▼
getClassLoadingLock(name)
          │
          ▼
findLoadedClass(name)
          │
          ├──── class already recorded ───────────────┐
          │                                           │
          └─ null                                     │
               │                                      │
               ▼                                      │
        ask parent loader (or bootstrap)              │
               │                                      │
        ┌──────┴──────┐                               │
        │    found    │───────────────────────────────┤
        │             │                               │
        └─ not found ─┘                               │
               │                                      │
               ▼                                      │
         findClass(name)                              │
               │                                      │
               └────────── Class<?> c ────────────────┘
                                                      │
                                                      ▼
                                         resolve == true?
                                           │        │
                                          Yes      No
                                           │        │
                                           ▼        │
                                      resolveClass(c)
                                           │        │
                                           └────┬───┘
                                                ▼
                                         return Class<?> c
~~~

Pseudocode approximating the JDK semantics, though not the verbatim JDK source code:

~~~java
// Pseudocode: JVM/parent steps are simplified for easier learning.
synchronized (getClassLoadingLock(name)) {
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            c = parentOrBootstrapLoad(name);
        } catch (ClassNotFoundException e) {
            c = findClass(name);
        }
    }
    if (resolve) {
        resolveClass(c);
    }
    return c;
}
~~~

Key points to remember:

1. **Check cache/tracking first:** `findLoadedClass(name)` returns the definition that the JVM has already recorded as initiated by the corresponding loader.
2. **Delegation:** the default implementation gives the parent a chance before searching on its own.
3. **Fallback:** only when the parent/bootstrap loader cannot find the class is `findClass(name)` needed on the current loader.
4. **The resolve flag is handled after obtaining the `Class`:** passing `true` does not turn bytecode lookup into a different search algorithm.
5. **The result is a `Class<?>`, not an instance** of that class. `loadClass` does not invoke a constructor to create an object of the loaded class.

A custom loader may override `loadClass` and use a different policy, such as conditional child-first. Therefore, this is the model for the **default implementation** and subclasses that inherit it, not a promise about every custom ClassLoader in the world.

## 4. What Does `resolve=true` Actually Mean?

The parameter name is easily misunderstood. In `loadClass(name, true)`, `resolve` means "**request linking of the returned class**" in the default algorithm. This step calls `resolveClass(c)`.

At the JVM level, linking consists of major activities:

| Linking Phase | Purpose |
| --- | --- |
| **Verification** | Verifies that the definition/bytecode is valid against JVM rules. |
| **Preparation** | Prepares storage for static fields and sets their initial values according to the specification (does not execute arbitrary Java static initializers). |
| **Resolution** | Replaces symbolic references with their corresponding runtime references when the JVM performs resolution. |

**Do not equate** the name `resolveClass` with a guarantee that "every symbolic reference in the constant pool has already been fully resolved right now". The JVM Specification allows **on-demand (lazy) resolution**; many resolution errors can surface when a specific reference is first used. `resolveClass` is a linking request for the class under the ClassLoader contract, not an API that enumerates or forces resolution of all the class's dependencies.

Some consequences:

- `resolve=false` **does not guarantee** that the class has never been linked. The JVM may already have performed part or all of linking for another reason.
- `resolve=true` **does not run the static initializer** merely because that flag is chosen.
- `resolve=true` **does not force immediate loading of every class** appearing in every method name, field, or constant pool entry of the class.
- If the class has already been linked, calling `resolveClass` neither creates a new class definition nor runs static code again.
- A verification or linking error may be exposed during this process, but **the exact timing of certain resolution errors** still depends on JVM rules and actual usage.

### 4.1 Reading `resolve` as "Connecting the Class" Is Still Not Enough

Saying "`resolve=true` = resolve every reference" is too strong. Saying "`resolve=true` only flips a boolean without affecting anything" misses the linking step that the loader requests.

The right way to understand it: **after finding `Class<?> c`, the default overload may ask the JVM to link `c` via `resolveClass(c)` when the flag is true**. It does not change initialization rules and does not promise that every symbolic reference across the entire application is processed immediately.

## 5. Difference Between `resolve` and `initialize`

This is the most important point for learners of the Java ClassLoader.

- **Resolve / link:** relates to validity and the linking state of the type.
- **Initialize:** executes the static initialization code of a class/interface according to JLS §12.4.

The two operations have different timing and triggers. Given the class:

~~~java
class Target {
    static {
        System.out.println("Target initialized");
    }
}
~~~

After `loader.loadClass("Target")`, the JVM has the `Class`, but has not necessarily run the static block. Even with a `loadClass("Target", true)` call through a subclass, this flag itself is still **not** an initialization trigger.

In contrast, `Class.forName` provides an overload with a different parameter:

~~~java
Class<?> a = Class.forName("java.lang.String");
Class<?> b = Class.forName("java.lang.String", false, loader);
Class<?> c = Class.forName("java.lang.String", true, loader);
~~~

**`Class.forName(name, initialize, loader)`** has an **`initialize`** flag: when `true`, it requests initialization if the class is not yet initialized. The single-argument form `Class.forName(name)` requests initialization by default. That is the fundamental semantic difference from ClassLoader's `resolve` flag.

| Operation | Find/Load `Class` | Linking | Requests Initialization |
| --- | --- | --- | --- |
| `loader.loadClass(name)` | Yes | When the JVM needs it; does not proactively request `resolveClass` in the default overload. | **No** |
| `loadClass(name, false)` in a subclass | Yes | Same as above. | **No** |
| `loadClass(name, true)` in a subclass inheriting the default algorithm | Yes | Calls `resolveClass` on the returned Class. | **No** |
| `Class.forName(name, false, loader)` | Yes | The API requests locate/load/link. | **No** |
| `Class.forName(name, true, loader)` | Yes | Yes | **Yes** |
| `new Target()` | Type is ready for use | JVM performs necessary linking | **Yes**, if not yet initialized |
| Reading `Target.nonConstantStatic` | Type is ready for use | JVM performs necessary linking | **Yes**, if the field is declared by Target and not yet initialized |

**Reading constant variables:** for example, `static final int MAX = 10` with a compile-time constant expression is a special case; reading the constant can be inlined by the compiler and **does not by itself** cause initialization. This is not directly related to the resolve parameter, but helps avoid the assumption "any use of a class name triggers initialization".

## 6. Runnable Example 1: Comparing `resolve=false` and `resolve=true`

Save the file **ResolveFlagDemo.java**:

~~~java
public class ResolveFlagDemo {
    static class Target {
        static {
            System.out.println("Target: static block");
        }

        static int value = compute();

        static int compute() {
            System.out.println("Target: compute");
            return 42;
        }
    }

    static class InspectingLoader extends ClassLoader {
        InspectingLoader(ClassLoader parent) {
            super(parent);
        }

        public Class<?> loadWithResolve(String name, boolean resolve)
                throws ClassNotFoundException {
            System.out.println("request resolve = " + resolve);
            return super.loadClass(name, resolve);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("child findClass called");
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader app = ResolveFlagDemo.class.getClassLoader();
        InspectingLoader child = new InspectingLoader(app);

        String targetName = Target.class.getName();

        Class<?> first = child.loadWithResolve(targetName, false);
        System.out.println("false: same Class = " + (first == Target.class));

        Class<?> second = child.loadWithResolve(targetName, true);
        System.out.println("true: same Class = " + (second == Target.class));

        System.out.println("before active use");
        System.out.println("value = " + Target.value);
    }
}
~~~

Run on JDK 17+:

~~~bash
javac ResolveFlagDemo.java
java ResolveFlagDemo
~~~

Stdout:

~~~text
request resolve = false
false: same Class = true
request resolve = true
true: same Class = true
before active use
Target: static block
Target: compute
value = 42
~~~

### 6.1 Line-by-Line Explanation

1. `Target.class.getName()` obtains the binary name of the nested class without proactively triggering initialization of Target.
2. Both `child.loadWithResolve(...)` calls use **`super.loadClass(name, resolve)`**. The default implementation finds the class through the application parent loader. Child is not the defining loader of Target.
3. The first call with `resolve=false` returns the `Class`; the second call with `resolve=true` requests `resolveClass` on the same Class if needed. Both `==` comparisons with `Target.class` evaluate to true.
4. The line **child findClass called** does not appear because the parent finds Target. This shows that the `resolve` flag does not bypass delegation.
5. After the two loadClass calls, the line **Target: static block** has still not appeared. Initialization only begins when the program first reads the runtime field `Target.value`.
6. Following declaration order, Target prints the static block and then calls `compute()` to assign 42 to value, and only afterward prints the final line.

**Limitation of this example:** stdout proves that neither `resolve=false` nor `resolve=true` **proactively triggers initialization**. It has no direct way to print the timing of verification/resolution of each symbolic reference. Therefore, you should not use the absence of logs to claim with certainty that the JVM has not performed linking when `resolve=false`.

### 6.2 Why Write the `loadWithResolve` Wrapper?

The two-parameter overload is declared **`protected`**. External code cannot arbitrarily write:

~~~java
// Does NOT compile in normal application code:
// new ClassLoader().loadClass("demo.Target", true);
~~~

In the runnable example, the subclass `InspectingLoader` accesses the protected method through `super.loadClass(name, resolve)`, and provides a **public wrapper** solely to demonstrate the flag's meaning. ClassLoader's public `loadClass(name)` method remains the standard API that external code uses.

## 7. Runnable Example 2: `findClass` Is Only Called When the Parent Does Not Find the Class

The `resolve` flag does not change the class-lookup chain, yet to see the entire journey you can try a loader that reads its own `.class` file.

Create the structure:

~~~text
project/
├── DirectoryLoaderDemo.java
└── src/
    └── plugin/
        └── Greeter.java
~~~

**src/plugin/Greeter.java**:

~~~java
package plugin;

public class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public String message() {
        return "Hello";
    }
}
~~~

**DirectoryLoaderDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryLoaderDemo {
    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class"
            ).normalize();

            if (!file.startsWith(root)) {
                throw new ClassNotFoundException(name);
            }

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }

            System.out.println("findClass: " + name);
            return defineClass(name, bytes, 0, bytes.length);
        }

        public Class<?> loadWithResolve(String name, boolean resolve)
                throws ClassNotFoundException {
            return super.loadClass(name, resolve);
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader =
                new DirectoryLoader(Path.of("plugin-classes"));

        Class<?> loaded = loader.loadWithResolve("plugin.Greeter", false);
        System.out.println("defined by child = "
                + (loaded.getClassLoader() == loader));

        Class<?> linked = loader.loadWithResolve("plugin.Greeter", true);
        System.out.println("same Class = " + (loaded == linked));

        System.out.println("before instance");
        Object object = linked.getDeclaredConstructor().newInstance();
        String message = (String) linked.getMethod("message")
                .invoke(object);
        System.out.println("message = " + message);
    }
}
~~~

Run from the **project** directory:

~~~bash
javac -d plugin-classes src/plugin/Greeter.java
javac DirectoryLoaderDemo.java
java -cp . DirectoryLoaderDemo
~~~

Stdout:

~~~text
findClass: plugin.Greeter
defined by child = true
same Class = true
before instance
Greeter initialized
message = Hello
~~~

### 7.1 Why Does the First Call Enter `findClass`?

`DirectoryLoader` has the platform loader as its parent. In this run command, `plugin-classes` **is not on the application classpath**, so the platform parent cannot find `plugin.Greeter`. The custom loader must read the file `plugin-classes/plugin/Greeter.class`, call `defineClass`, and then return the Class.

### 7.2 Why Does the Second Call Not Invoke `findClass`?

The JVM already has the `plugin.Greeter` definition associated with the loader. The `loadWithResolve(..., true)` call returns the same `Class` object; the `findLoadedClass` step finds it, so there is no need to read the file again. After obtaining the result, the true flag causes the default implementation to request `resolveClass`.

### 7.3 When Does the Static Block Run?

**Greeter initialized** only appears when reflection creates an instance via `getDeclaredConstructor().newInstance()`. This is an active use that causes the class to be initialized. Neither `resolve=false` nor `resolve=true` in the two prior calls performs this step on its own.

### 7.4 Notes for Real-World Custom Loaders

This code is an example intended for a known directory. A system that loads classes from untrusted data needs to validate the byte source, valid names, file sizes, symlink paths, access permissions, and security constraints. Avoid directly expanding this demonstration snippet into a mechanism for loading plugins from arbitrary sources without controls.

**Important comparison:** if you add `plugin-classes` to `-cp` or use a parent loader that can also see `plugin.Greeter`, parent-first may return the class defined by the parent. In that case, there is **no** `findClass: plugin.Greeter` line; the expected stdout above holds only for the exact commands given.

## 8. Things `resolve=true` Does NOT Guarantee

This is the section to read before trying to use the resolve flag as an "upfront check for all errors":

| False Conclusion | Reality |
| --- | --- |
| "`resolve=true` runs all `static {}`." | Initialization is a separate step, with its own triggers. |
| "`resolve=false` means the class is not yet linked." | The JVM may have already linked it due to prior use or implementation decisions. |
| "`resolve=true` loads every dependency class." | There is no guarantee that all symbolic references are eagerly resolved immediately. |
| "`resolve=true` always catches every NoSuchMethodError before execution." | Resolution can be lazy; errors may surface when the method/field is used. |
| "`resolve=true` creates a new class object." | The same runtime definition is returned; linking is not a new define pass. |
| "`resolve=true` makes the child loader take precedence over the parent." | The flag only affects the step after the Class has been found. |
| "If `loadClass` returns a Class, the constructor has already run." | Only the runtime metadata of the type exists; the constructor runs when an instance is actually created. |

A class may reference other types or members that are not yet fully resolved at the time `loadClass` returns. The JVM enforces constraints and errors at the point of use as specified; that is why a single loadClass call cannot be used to "certify" every execution branch of the entire dependency graph.

## 9. ClassLoader `resolve` and Resolution in the JVM Are Two Conceptual Layers

The name `resolveClass` provided by the ClassLoader API easily leads to an inaccurate statement:

~~~text
resolveClass(c) == eagerly resolve all constant-pool entries
~~~

This statement is **incorrect**.

The class-file constant pool contains many kinds of symbolic references; many entries are only used when the corresponding bytecode executes. The JVM may choose **lazy** or **eager** resolution in accordance with the rules and error-observability timing defined by the JVMS.

When a specific symbolic reference undergoes resolution, the JVM may locate the method/field/class and check access or type compatibility. Errors such as `NoSuchMethodError`, `NoSuchFieldError`, or `IllegalAccessError` may surface at a runtime point; they do not necessarily appear immediately at the `loadClass(name, true)` call.

Therefore, use the term "**class linking**" to express the meaning of ClassLoader's resolve parameter, while referring to "**symbolic-reference resolution**" when discussing individual references inside the constant pool.

## 10. Relationship with Defining Loader and Initiating Loader

Suppose loader object A receives the request `A.loadClass("demo.Shared")`, but parent B has already defined `demo.Shared`:

~~~text
caller
  │
  └─ A.loadClass(name, resolve)
         │
         ├─ parent B.loadClass(name)
         │          │
         │          └─ Class<?> defined by B
         │
         ├─ if resolve=true, request resolveClass(c)
         │
         └─ return B's Class<?>
~~~

`Class.getClassLoader()` on the result returns **B**, not A. B is the **defining loader**, while A can be an **initiating loader** under the JVM loading model. The `resolve` flag does not transfer definition ownership from B to A.

Multiple different child loaders can delegate to the same parent and receive the **same Class**. Conversely, if two different loaders actually call `defineClass` for the same binary name, those are two distinct runtime types. Class identity normally depends on the pair **(binary name, defining loader)**.

Practical tip: if your logs show `myLoader.loadClass("x.Y")` succeeded, check **`returnedClass.getClassLoader()`** before concluding which loader actually defined `x.Y`.

## 11. Synchronization and Concurrency

The default implementation of `ClassLoader.loadClass(name, boolean)` synchronizes on **`getClassLoadingLock(name)`**:

- For a loader not registered as **parallel capable**, the lock may be the ClassLoader object itself.
- For a parallel-capable loader, the lock can be per binary name, allowing different classes to be loaded in parallel.
- The already-loaded state is checked inside the critical section to avoid attempting duplicate definitions in concurrent loading scenarios.

If you customize `loadClass` entirely, you must understand the relationship among `getClassLoadingLock`, `findLoadedClass`, parent delegation, and defineClass. An unsafe implementation can cause races between two threads, `LinkageError`, or deadlocks between loaders.

**For use cases where you only want to add a bytecode source, you should usually override `findClass` and keep the default `loadClass` algorithm**, because it already handles delegation, locking, and Class reuse.

## 12. Error Handling: Which Error Belongs to Which Stage?

| Error or Symptom | Likely Cause | How to Interpret in the Context of `loadClass` |
| --- | --- | --- |
| `ClassNotFoundException` | The loader could not find/load the class with the requested name. | Checked exception of the load API; check the name, byte source, parent, and custom findClass. |
| `ClassFormatError` | Invalid binary representation. | Can appear when defining the class, not a "file not found" condition. |
| `UnsupportedClassVersionError` | Class-file version is not supported by the runtime. | Check the compile JDK / runtime JDK and the class-file major version. |
| `VerifyError` | Violation of verifier rules. | Related to linking; do not call it a static initializer error. |
| `NoClassDefFoundError` | Missing a required definition at runtime or the class previously failed initialization. | Can differ from `ClassNotFoundException`; inspect the cause and timing. |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary reference is no longer compatible. | Can surface during resolution/use; `resolve=true` does not guarantee catching every error early. |
| `ExceptionInInitializerError` | Exception thrown during static initialization. | Not an error proactively triggered by the `resolve` flag; investigate the cause in static code. |
| `LinkageError` from duplicate definition | The loader attempted to define a class with the same name again. | Check loading/caching/thread-safety logic and the class source. |

In a custom loader, do not catch every `Throwable` and convert it into `ClassNotFoundException`; doing so hides format, verification, linkage errors, or loader bugs. If **the bytes cannot be found**, throw **`ClassNotFoundException`**, ideally with a cause when an I/O error occurs. If the bytes were found but are invalid, let the appropriate JVM error surface.

## 13. Step-by-Step Troubleshooting

When encountering a `loadClass`-related error, perform these checks in order:

1. **Input name:** is the `name` value a valid binary name? For nested types, check `$`.
2. **Class source:** are the bytes found in the classpath/module path/JAR/directory that the loader expects?
3. **Actual loader:** which object receives the request, what is its parent, and does it override `loadClass`?
4. **Defining loader:** which loader does `clazz.getClassLoader()` return after success? Was the class already defined by a parent?
5. **When the exception occurs:** during load/define, linking, or the active use that triggers initialization?
6. **Is there a difference between `resolve=false` and `resolve=true`?** If so, inspect the actual error and root cause; do not equate it with initialization.
7. **Has another loader defined the same binary name?** Compare the `Class` objects themselves, not just `getName()`.
8. **Has the classpath/JDK changed?** Verify the exact runtime version when reproducing.

You can use:

~~~bash
javap -verbose ResolveFlagDemo
java -Xlog:class+load=info ResolveFlagDemo
java -Xlog:help
~~~

`javap` reads compiled class files/bytecode. Unified Logging helps observe loading on supporting JVMs (such as modern HotSpot). These logs **do not directly prove** that every symbolic reference has undergone resolution or that the static initializer has run; use the dedicated print lines in the examples to identify initialization.

## 14. Common API Usage Mistakes

### 14.1 Calling the Protected Overload as If It Were Public

The following statement does not compile in normal application code:

~~~java
// Invalid example from a non-subclass:
ClassLoader.getSystemClassLoader().loadClass("java.lang.String", true);
~~~

The reason is that `loadClass(String, boolean)` is **protected**. Use the public `loadClass(name)` API, or a wrapper in a subclass as shown in the example when you need to inspect the flag.

### 14.2 Overriding loadClass Yourself Just to Read Files

If the requirement is simply to "find bytecode elsewhere", overriding **`findClass`** is usually sufficient. Overriding **`loadClass`** completely can break the parent delegation order, skip `findLoadedClass`, and lead to duplicate definitions or violate class identity rules.

### 14.3 Treating resolve=true as an Eager Initialization Mechanism

To request initialization via the API, consider **`Class.forName(name, true, loader)`**, keeping in mind that static initializers can have side effects and throw errors. Calling `loadClass(name, true)` (in a subclass) does not carry that meaning.

### 14.4 Treating resolve=false as a Guarantee That "The Class Has Not Been Verified"

Java does not allow a caller to use the false flag to force the JVM to avoid all verification/linking work. The returned class may be processed by the VM according to eager/lazy strategies and usage demands.

### 14.5 Assuming Every Runtime Error Originates at loadClass

A library may load successfully yet miss a method used in a later logic branch; symbolic-reference resolution will only report the error at that point. Inspect the stack trace and the exact context that produced the error, rather than relying on when the user happens to observe the failure.

## 15. Self-Check

**Question 1.** What flag in the two-parameter overload is `ClassLoader.loadClass("pkg.Type")` equivalent to?

**Answer:** `resolve=false`, per the ClassLoader implementation.

**Question 2.** Does `resolve=true` guarantee executing Type's `static {}` block?

**Answer:** No. It requests linking via `resolveClass` in the default algorithm; initialization is a separate step.

**Question 3.** Why cannot normal code directly call `loader.loadClass(name, true)`?

**Answer:** This overload is **protected**, accessible only according to Java's `protected` access rules.

**Question 4.** If a class is defined by a parent loader, does the `resolve=true` flag cause the child loader to redefine the class?

**Answer:** No. The child still returns the parent's Class; linking does not transfer the defining loader.

**Question 5.** Can `NoSuchMethodError` occur after `loadClass(name, true)` has succeeded?

**Answer:** Yes. There is no guarantee that all symbolic references undergo immediate eager resolution; the error may surface when a specific reference is used.

**Question 6.** When a custom loader only needs to load bytes from its own directory, which method should usually be overridden?

**Answer:** `findClass(name)` to locate the bytes and call `defineClass`; retain the default `loadClass` if the delegation policy meets the requirements.

**Question 7.** What is the important difference between `Class.forName(name, false, loader)` and `Class.forName(name, true, loader)`?

**Answer:** The **initialize** parameter controls whether class initialization is requested, not ClassLoader's resolve flag.

**Question 8.** Once the class loader has returned a Class, has Type's instance constructor definitely been called?

**Answer:** No. `loadClass` returns class metadata; creating an instance requires using an appropriate object-creation operation.

**Question 9.** Does `resolve=false` guarantee that the verifier has not run yet?

**Answer:** No. The JVM may perform verification/linking according to other valid rules and needs; the false flag is not an absolute deferral mechanism.

## 16. Summary

~~~text
loadClass(name, false)
  └─ find/return Class<?> via delegation, without proactively requesting resolveClass
       └─ does NOT mean it will initialize the class

loadClass(name, true) (protected)
  └─ find/return Class<?> and then request resolveClass(Class<?>)
       └─ link the class per the JVM
       └─ does NOT mean eager resolution of the entire constant pool
       └─ does NOT mean it will initialize the class

Class.forName(name, true, loader)
  └─ find/load/link and request class initialization
       └─ may run static code and cause side effects
~~~

Remember three independent axes: **finding the Class**, **linking the Class**, and **initializing the Class**. The `resolve` parameter of `ClassLoader.loadClass` relates to the **link** step and does not control the execution of `static {}`. To know which loader actually defined a Class, inspect `Class.getClassLoader()`; to know whether a static initializer has run, observe the actual initialization triggers rather than inferring from the resolve parameter.

### Official References

- Java SE 21 **ClassLoader API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 21 **Class.forName API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)
- **JVM Specification §5.4 – Linking**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4
- **JVM Specification §5.5 – Initialization**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5
- **Java Language Specification §12.2–12.4**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html
