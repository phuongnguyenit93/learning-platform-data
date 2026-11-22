# findLoadedClass and Reusing Classes Recorded by a Loader

## 1. Why Does a ClassLoader Need to Check Loaded Classes?

When the JVM or an application requests to load a class, the class loader needs to know whether that name has already been processed within the scope of the relevant loader. If every request created a new class definition with the same binary name in the same defining loader, the type system would lack consistency and could violate JVM rules.

Java provides the method:

```java
protected final Class<?> findLoadedClass(String name)
```

This method returns the `Class<?>` corresponding to the binary name `name` **if the JVM has recorded the current loader as an initiating loader of the class with that name**. If no matching record exists, the method returns `null`.

Importantly: `findLoadedClass` is a **lookup of existing state**, not a request to read a `.class` file, call the parent loader, execute `findClass`, initialize the class, or create an object.

A practical rule of thumb:

- **`findLoadedClass(name)`:** "Has the JVM recorded this loader as an initiating loader of the class named `name`?"
- **`loadClass(name)`:** "Find/obtain the class named `name`, typically by checking already loaded classes, delegating to the parent, and only then searching with the current loader."
- **`findClass(name)`:** "If the search mechanism in the parent has not provided the class, let the current loader try to find and define the class in its own way."
- **`defineClass(...)`:** "Define a runtime class from appropriate bytes, with the current loader as the defining loader."
- **`resolveClass(c)`:** "Ask the JVM to link the class per the API, if needed"; not synonymous with executing the static initializer.

In a properly designed loader, `findLoadedClass` is an important first step to avoid attempting to redefine a class repeatedly and to allow subsequent lookups to reuse the recorded runtime type.

## 2. What Exactly Does the Method Return?

According to the Java SE 17 API, `findLoadedClass(String)`:

1. Accepts a **binary name** such as `com.example.Plugin` or `java.lang.String`.
2. Checks whether the loader object on which the method is invoked has been recorded by the JVM as an **initiating loader** of the class with that name.
3. Returns a `Class<?>` if a record exists; otherwise returns `null`.

The method is **`protected final`**:

- `protected`: external code cannot call it freely through an arbitrary `ClassLoader`; subclasses can use it within their loading mechanism.
- `final`: subclasses cannot override it and alter the meaning of looking up what the JVM has recorded.
- No checked `ClassNotFoundException`: it only performs a lookup and does not search for files/modules along the loading path itself.
- A `null` value means **this loader has not been recorded by the VM as an initiating loader of that name**; it does not mean that the class is absent from every loader in the JVM.

For example, if the application loader already knows `com.example.Service` but a new custom loader has never participated in loading that name, `custom.findLoadedClass("com.example.Service")` can return `null` even though the class clearly exists in the application. After the custom loader asks its parent to load the class, recording the initiating loader follows VM rules and the request context; do not infer that a direct Java call created a copy of the class or necessarily caches the result in an arbitrary manner.

### The Word "Loaded" Can Be Misleading

`findLoadedClass` is named after its practical usage in the `loadClass` algorithm, but its exact contract refers to the **initiating loader recorded by the JVM**, not merely "a class that this loader itself defined via `defineClass`".

A loader can:

- **Define a class itself**: it is the defining loader and is recorded by the VM in connection with loading the class.
- **Delegate** to a parent loader: the returned class may have been defined by the parent; the initiating loader and the defining loader can be different.
- Not know the class at all: `findLoadedClass` returns `null` within the scope of that loader, even though a parent or another loader may be able to find the class.

The JVMS specification describes this distinction using the concepts of **defining loader** and **initiating loader**.

## 3. Placing findLoadedClass in the Default loadClass Flow

With the default `ClassLoader.loadClass(String, boolean)`, the main logic can be read as follows:

```text
loadClass(binaryName, resolve)
          |
          v
findLoadedClass(binaryName)
          |
          +-- Class<?> found -------> reuse recorded Class<?>
          |
          +-- null
                |
                v
      Parent.loadClass(binaryName)
       (or bootstrap if parent is null)
                |
                +-- Success --------> use Class<?> provided by parent
                |
                +-- Not found
                        |
                        v
                   findClass(binaryName)
                        |
                        +-- Success -> use found/defined Class<?>
                        |
                        +-- Failure -> ClassNotFoundException

If resolve == true: call resolveClass(classFound).
Return Class<?> to the requester.
```

Written in pseudocode:

```text
Class c = findLoadedClass(name);
if (c == null) {
    try {
        c = parent != null
                ? parent.loadClass(name)
                : askBootstrapLoader(name);
    } catch (ClassNotFoundException ignored) {
        // continue with the current loader mechanism
    }
    if (c == null) {
        c = findClass(name);
    }
}
if (resolve) {
    resolveClass(c);
}
return c;
```

**This is pseudocode illustrating the flow, not standalone compilable Java code**: `askBootstrapLoader` is not a public method in the Java API. The actual flow also includes synchronization using `getClassLoadingLock(name)` and VM lookup details.

Key points:

- `findLoadedClass` is called **before** parent delegation or `findClass` in the default algorithm.
- If it returns a `Class<?>`, the loader does not need to try finding or redefining that type during that call.
- If it returns `null`, the mechanism continues through the parent/bootstrap and/or `findClass`.
- `loadClass(name)` is equivalent to `loadClass(name, false)`; the `false` value does not omit the `findLoadedClass` step.

A subclass can override `loadClass` to implement child-first, selective delegation, or a custom mechanism; in that case, it must properly preserve duplicate-loading prevention.

## 4. Class Names, Type Identity, and Lookup Scope Limits

Java runtime class/interface identity is based on **binary name and defining loader**. Therefore:

```text
com.example.Widget + LoaderA  -> runtime Class A
com.example.Widget + LoaderB  -> runtime Class B
```

The two `Class<?>` objects above are different if LoaderA and LoaderB actually define two independent classes, even though the string name `com.example.Widget` is the same.

`findLoadedClass` **does not search JVM-wide** to return any arbitrary class matching the name. It checks for a class for which the **current** loader has been recorded by the VM as an initiating loader. Therefore:

- LoaderA can find A's own version of `Widget`.
- LoaderB may not have recorded `Widget` yet, so it returns `null`.
- Afterwards, LoaderB may delegate and receive a parent's `Widget`, or define B's own `Widget`, depending on the policy and relevant loading constraints.
- Do not infer from `findLoadedClass(name) == null` that the name does not appear on the class path or has not been defined by another loader.

### Binary Name Differs from Descriptor

| Kind | Example | Use with findLoadedClass? |
|---|---|---|
| Class binary name | `java.lang.String` | Yes |
| Nested class binary name | `java.util.Map$Entry` | Yes |
| Bytecode internal name | `java/lang/String` | No |
| Class field descriptor | `Ljava/lang/String;` | No |
| Source-style array | `String[]` | Not a binary name of an ordinary class |
| Primitive name | `int` | Not a class loaded from an ordinary class file |

For arrays, the JVM has its own rules for creating array classes when needed; do not use `findLoadedClass("[I")` as a general-purpose API to create or query array classes by descriptor. For array types, use a class literal (`int[].class`) or `Class.forName` with a documented supported array name, if string-based lookup is required.

## 5. Java 17: Accurately Demonstrating Single Definition and Reuse

The following example intentionally designs **a custom loader that defines a specific class itself**. This helps prove that `findLoadedClass` avoids redefining the class without depending on how a parent delegation path records it.

Create a file named **`FindLoadedDemo.java`** containing both the public class and a package-private class at the end of the file:

```java
import java.io.IOException;
import java.io.InputStream;

public class FindLoadedDemo {
    static final String TARGET = "LocalPayload";

    static class CopyLoader extends ClassLoader {
        private int definitions;

        CopyLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> peek(String binaryName) {
            return findLoadedClass(binaryName);
        }

        int definitions() {
            return definitions;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    type = findClass(name);
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                throw new ClassNotFoundException(name);
            }

            String resource = name.replace('.', '/') + ".class";

            try (InputStream input =
                         getParent().getResourceAsStream(resource)) {
                if (input == null) {
                    throw new ClassNotFoundException(name);
                }

                byte[] bytes = input.readAllBytes();
                Class<?> type =
                        defineClass(name, bytes, 0, bytes.length);
                definitions++;
                return type;
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = FindLoadedDemo.class.getClassLoader();
        CopyLoader custom = new CopyLoader(app);

        System.out.println("Before load: "
                + (custom.peek(TARGET) == null));

        Class<?> first = custom.loadClass(TARGET);
        Class<?> second = custom.loadClass(TARGET);

        System.out.println("Same Class object: " + (first == second));
        System.out.println("Found by peek: "
                + (custom.peek(TARGET) == first));
        System.out.println("Definitions: " + custom.definitions());
        System.out.println("Owned by custom: "
                + (first.getClassLoader() == custom));

        Class<?> appCopy = app.loadClass(TARGET);
        System.out.println("Different from app: "
                + (first != appCopy));
    }
}

class LocalPayload {
}
```

In the directory containing this file, run on JDK 17 or later:

```bash
javac FindLoadedDemo.java
java FindLoadedDemo
```

Stdout output:

```text
Before load: true
Same Class object: true
Found by peek: true
Definitions: 1
Owned by custom: true
Different from app: true
```

**Step-by-step explanation:**

1. `javac` generates `FindLoadedDemo.class`, the corresponding auxiliary class files, and `LocalPayload.class`. The two `LocalPayload` runtime class identities are created only **when the program actively loads them**.
2. `custom.peek("LocalPayload")` calls `findLoadedClass` from within the subclass. Initially, the custom loader has not defined or been recorded by the VM for that name, so it returns `null`.
3. The first `custom.loadClass(TARGET)` call enters the override branch reserved solely for `LocalPayload`; `findLoadedClass` returns `null`, and `findClass` reads the bytes of `LocalPayload.class` and calls `defineClass`. The `definitions` counter increases to one.
4. On the second call, `findLoadedClass` returns the exact `Class<?>` already defined by the custom loader, so `findClass` is not called again.
5. `first == second` proves it is the same runtime class object; `definitions == 1` proves the class was **defined once** by the custom loader.
6. `first.getClassLoader() == custom` indicates that the custom loader is the **defining loader** of this copy of the class.
7. `app.loadClass(TARGET)` provides a separate runtime `LocalPayload` defined by the application loader. The two classes have the same binary name but different defining loaders, so `first != appCopy`.

**Scope of demonstration:** the override performs child-first **only for `LocalPayload`**. Other names go through `super.loadClass` under the default mechanism. Do not apply an uncontrolled child-first pattern to core packages or shared plugin APIs.

No instance of `LocalPayload` is created in the example; loading a class definition and creating an object are two different operations.

## 6. When a Class Is Loaded by the Parent: Reuse and Owner Are Two Different Questions

Consider a child loader that delegates normally:

```java
ClassLoader app = MyMain.class.getClassLoader();
ClassLoader child = new ClassLoader(app) { };
Class<?> type = child.loadClass("java.lang.String");
```

This snippet is **illustrative code** and requires a `MyMain` class. `type` is normally `String.class` itself, whose defining loader is bootstrap. The child loader does **not** create another new `String`.

Here, we should distinguish:

- **Lookup result:** `child.loadClass(...)` may return a `Class<?>` defined by the parent/bootstrap.
- **Defining loader:** `type.getClassLoader()` describes the loader that owns the definition; for standard `String`, this will be `null`.
- **Initiating loader:** the JVM can record loaders that participate in the process of loading/resolving a class; `findLoadedClass` checks the **VM's record**, not simply "whether a Java method was ever called".
- **Reuse:** when receiving the parent's `Class<?>` itself, no additional copy of the class is automatically created.

A point to be careful about with the direct `child.loadClass(...)` example: **do not assert that in every JVM context, after every time Java code directly calls `loadClass` to obtain a class from a parent, `child.findLoadedClass(name)` must necessarily be non-`null`.** The exact contract of `findLoadedClass` requires that the JVM has recorded the loader as an initiating loader; JVM loading/resolution activity and a method call explicitly invoked by Java code should not be equated in your program's reasoning.

### Java 17 Example: Confirming the Same Runtime Class After Delegation

Create a file named **`ParentReuseDemo.java`**:

```java
public class ParentReuseDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader parent = ParentReuseDemo.class.getClassLoader();
        ClassLoader child = new ClassLoader(parent) { };

        Class<?> a = child.loadClass("ParentReuseDemo");
        Class<?> b = child.loadClass("ParentReuseDemo");

        System.out.println("Same Class returned: " + (a == b));
        System.out.println("Same as source class: "
                + (a == ParentReuseDemo.class));
        System.out.println("Owner is parent: "
                + (a.getClassLoader() == parent));
        System.out.println("Child does not define it: "
                + (a.getClassLoader() != child));

        Class<?> core = child.loadClass("java.lang.String");
        System.out.println("String from bootstrap: "
                + (core == String.class
                   && core.getClassLoader() == null));
    }
}
```

Run:

```bash
javac ParentReuseDemo.java
java ParentReuseDemo
```

Stdout on JDK 17 in a typical class path configuration:

```text
Same Class returned: true
Same as source class: true
Owner is parent: true
Child does not define it: true
String from bootstrap: true
```

Both `child.loadClass("ParentReuseDemo")` calls return the same class identity defined by the **parent**. The program does not require a guarantee that is not in the API regarding how many times the parent's method is called internally or the internal recording state of `child`; it only observes what is certain from the results.

## 7. When findLoadedClass Returns null: Properly Understanding the Possibilities

`null` can occur when:

1. That loader has not yet participated in loading or been recorded by the VM for the requested binary name.
2. A class with the same name exists in another loader, but this loader has not yet been recorded as its initiating loader.
3. The loader has been created, but the program has not yet requested to load a class within its scope.
4. The passed name does not match the API contract, for example using a descriptor instead of a binary name; a `null` return should not be used to infer that the name syntax is valid.

**One cannot infer solely from `null` that:**

- The class does not exist in the JVM.
- The parent/bootstrap cannot find the class.
- The class file is not on the class path.
- The class has never been loaded by any class loader.
- `defineClass` must be called immediately, bypassing the loader's delegation policy.

If the loader is executing the default algorithm, a `null` result causes it to proceed with parent delegation first. Only when the parent step fails to find it is `findClass` called.

## 8. What If findLoadedClass Is Omitted or Duplicate Definition Occurs?

Suppose a custom loader overrides `loadClass` and reads the bytes itself every time, calling `defineClass` for **the same binary name**. Within one defining loader, two runtime classes with the same name cannot be defined; this behavior can lead to a `LinkageError` due to an attempted duplicate definition, rather than producing "two new versions" with the same defining loader.

A pseudocode example **that should not be used in an application**:

```text
// Wrong: does not check whether the class has already been defined or recorded
loadClass(name):
    bytes = readClassFile(name)
    return defineClass(name, bytes, ...)
```

When the same name is requested again, the loader may proceed to call `defineClass` and fail. Conversely, Section 5 showed one way to check `findLoadedClass` before defining.

**Relationship to identity:** two classes with the same binary name but different **defining loaders** can coexist. Two definitions with the same name by the **same defining loader** do not form two valid classes. The two situations do not contradict each other.

**Relationship to other errors:** `ClassNotFoundException` means the lookup did not find the class; `LinkageError` can occur when class data/constraints/linking are invalid. Do not call every `LinkageError` "the class was loaded twice"; instead, examine the specific message and stack trace.

## 9. findLoadedClass Does Not Mean Initialization or Object Creation

Each of the following actions is distinct:

| Operation | Meaning |
|---|---|
| `findLoadedClass(name)` | Look up a class already recorded by the JVM for this initiating loader |
| `loadClass(name)` | Request to load/obtain a class, normally without requiring initialization |
| `defineClass(...)` | Define a runtime class from bytes |
| `resolveClass(c)` | Request linking the class per the API |
| `Class.forName(name)` | Look up a class; the single-parameter overload typically requires initialization |
| `new SomeClass()` | Create a new instance, ensuring the class is initialized according to the rules |
| `getDeclaredConstructor().newInstance()` | Use reflection to create an instance if access and constructor are appropriate |

Because `findLoadedClass` only returns a recorded `Class<?>`:

- It does not execute any constructor.
- It does not actively run the static initializer `<clinit>`.
- It does not prove that the class has initialized successfully; loading, linking, and initialization are distinct phases.
- It does not guarantee that the class can be used with every method or dependency at any given time; linking/resolution and access rules can still cause errors.

Example:

```java
Class<?> existing = custom.peek("LocalPayload");
```

If the program has already created/recorded the class with the `custom` loader as in Section 5, the line above only retrieves the class metadata. That is not a `new LocalPayload()` call.

## 10. Thread Safety: Why Must It Be Tied to getClassLoadingLock?

In a multithreaded environment, two threads can simultaneously request the loader to load the same binary name:

```text
Thread A: findLoadedClass("Plugin") -> null
Thread B: findLoadedClass("Plugin") -> null
Thread A: defineClass("Plugin", ...) -> succeeds
Thread B: defineClass("Plugin", ...) -> risk of duplicate definition/LinkageError
```

If you override `loadClass` yourself, you need to synchronize the **check if loaded → load/define → resolve** sequence for the same name. The `ClassLoader.getClassLoadingLock(name)` API provides a lock suited to the class-loading mechanism.

Pattern:

```java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> type = findLoadedClass(name);
        if (type == null) {
            // Apply the loader's delegation policy;
            // if the parent does not provide it, then search/define the class.
            type = findClass(name);
        }
        if (resolve) {
            resolveClass(type);
        }
        return type;
    }
}
```

This is an **illustrative skeleton**, not a complete parent-first implementation because it does not delegate to the parent. To use the standard policy, prefer **overriding only `findClass`** and letting the inherited `loadClass` perform the checks, delegation, and synchronization.

### Parallel-Capable Class Loaders

Subclasses can register via `registerAsParallelCapable()` per Java's contract to allow different class names to be loaded concurrently in an appropriate manner. Otherwise, the default implementation may use a broader lock on the loader object. Simply calling `getClassLoadingLock(name)` does not automatically make a loader parallel-capable.

When overriding `loadClass` yourself, lock usage must be consistent with the parallel-capable configuration and any shared mutable state in `findClass`. The illustrative counter in Section 5 is only accessed sequentially in `main`; if placed in a real multithreaded system, separate synchronization/state observation must be designed.

## 11. Why Not Write Your Own Map<String, Class<?>> Cache Instead of findLoadedClass?

Some custom loaders want to store:

```java
Map<String, Class<?>> cache;
```

An application cache can be useful for managing metadata or auxiliary resources, but **it does not replace the JVM contract regarding class identity and initiating loaders**.

Risks of relying solely on a custom-built map:

- The map can become out of sync with the class state recorded by the VM.
- If a class was resolved from a parent, manually removing/losing a key in the map does not make the parent's definition disappear.
- Two threads without proper synchronization can still race to read bytes and call `defineClass`.
- If strong references to `Class<?>` or the custom loader are retained longer than necessary, the cache can prevent class unloading in plugin/hot-reload models.
- The map does not itself check loading constraints or package/module access rules that the VM must enforce.

Therefore, use `findLoadedClass` as the standard lookup in class-loading logic. Only add a cache if it has a **separate purpose**, a clear lifecycle, and does not cause divergence from the VM.

### How Do findLoadedClass and findClass Differ?

Two easily confused names:

- `findLoadedClass`: **checks whether already recorded**; `protected final`, returns `Class<?>` or `null`.
- `findClass`: **hook for finding and defining a new class**, implemented by a subclass; can read bytes/JARs/resources and call `defineClass` or throw `ClassNotFoundException`.

Do not replace `findClass` with a call to `findLoadedClass` and expect a nonexistent class to be created automatically.

## 12. Real-World Case: Plugin Loaders and Hot Reload

A host application loads plugins using custom class loaders. Within the lifecycle of **a single loader object**:

1. Plugin `com.example.ReportPlugin` is requested for the first time.
2. The parent does not provide the plugin class; the custom `findClass` defines it.
3. Subsequent requests for the same name through that loader need to reuse the recorded definition.
4. When hot-reloading a new version, it is usually necessary to **create a new loader** for the new plugin version, because an already defined class is not replaced simply by calling `defineClass` again with the same name on the old loader.

In practice, special redefinition/retransformation mechanisms can be performed via instrumentation, but that is a different API with its own limitations and does not turn `findLoadedClass` into a byte-reloading mechanism.

Conversely, a new class loader also does not guarantee that the old loader will be GC'd/unloaded immediately: threads, callbacks, `ThreadLocal`, caches, instances, or `Class<?>` references can still keep the old loader reachable.

When debugging plugin errors:

- Observe the class loader object and `clazz.getClassLoader()`.
- Compare `Class<?>` objects using `==` when checking whether runtime types share the same identity.
- Check whether the loader actively defines the class or delegates to a parent.
- If conflicts arise, examine `ClassCastException` and `LinkageError` in the context of loaders and descriptors.
- Do not assume that having two classes with the same binary name in two different loaders is automatically an error; often that is the desired isolation mechanism, provided that shared API types are resolved consistently.

## 13. Common Mistakes and How to Avoid Them

| Misconception | Correct Understanding |
|---|---|
| "`findLoadedClass` will load the class if it is not yet present." | It only performs a lookup and returns `null` if no matching record exists. |
| "`findLoadedClass` only finds classes that the loader itself defined." | The API is based on the **initiating loader** recorded by the JVM, not simply the defining loader. |
| "`findLoadedClass(name) == null` proves the class does not exist anywhere in the JVM." | It only reflects the VM state related to the **current loader**. |
| "Same binary name means same class." | Runtime identity also depends on the defining loader. |
| "`loadClass` creates a new class definition every time." | A proper loader reuses the recorded class or the definition provided by a parent. |
| "`findClass` and `findLoadedClass` are different names for the same thing." | One finds/defines a new class, while the other looks up a loaded one. |
| "Repeating `defineClass` with the same name in one loader is how to update a class." | This can cause `LinkageError`; hot reload typically requires a new loader or an appropriate instrumentation mechanism. |
| "`findLoadedClass` runs the static initializer." | It does not require initialization or instance creation. |
| "Using `findLoadedClass` alone is enough to prevent races." | The check-then-load/define sequence must be properly synchronized, typically via `getClassLoadingLock`. |
| "If the parent returns the class, the child is definitely the defining loader." | The defining loader is the one that actually defines the class, typically the parent or bootstrap in a delegation scenario. |
| "A `Map<String,Class<?>>` cache can replace VM state on its own." | A separate map does not control JVM initiating-loader records or class identity. |

## 14. Self-Check

**Question 1.** `findLoadedClass("com.example.Task")` returns `null`. Can we conclude that `Task.class` is not on the class path?

**Answer:** No. We only know that the current loader has not been recorded by the JVM as an initiating loader for that binary name; a parent or another loader may be able to see the class.

**Question 2.** Why is `findLoadedClass` `protected final`?

**Answer:** Subclasses can use it within their class-loading logic, but cannot override it to alter the meaning of looking up state recorded by the JVM.

**Question 3.** A class is defined for the first time by a custom loader using `defineClass`. The next time the same loader requests it again, which method should be used to check whether the class already exists?

**Answer:** `findLoadedClass(binaryName)`, under appropriate synchronization in `loadClass`, will help reuse the `Class<?>`.

**Question 4.** Two independent loaders define `com.example.Task` with the same bytes. Are their `Class<?>` objects equal?

**Answer:** No. The same binary name with different defining loaders produces two different runtime identities.

**Question 5.** `child.loadClass("java.lang.String")` returns `String.class`. What does `String.class.getClassLoader() == null` mean?

**Answer:** `String` has bootstrap as its defining loader in a standard JDK configuration. It does not mean the child loader defined `String` itself.

**Question 6.** What is dangerous if two threads both see `findLoadedClass(name) == null` and then both call `defineClass`?

**Answer:** They may attempt to repeatedly define the same binary name in one loader, leading to a linkage error. Proper locking is needed around the entire check-and-define section, or the default `loadClass` implementation should be used.

**Question 7.** Does `findLoadedClass` guarantee that the class has already been initialized?

**Answer:** No. Loading/recording and initialization are different phases; the method only performs a lookup.

**Question 8.** Why do two calls to `custom.loadClass("LocalPayload")` in `FindLoadedDemo` cause `definitions` to increase only once?

**Answer:** After the first `defineClass`, the JVM records the class with that loader. On the second call, `findLoadedClass` returns the existing `Class<?>`, so `findClass` is not entered.

## 15. Key Takeaways and References

- **`findLoadedClass(String)` is a lookup:** returns the class already recorded by the VM for the **initiating loader**, or `null`.
- **The default `loadClass` checks already loaded classes first** before delegating and calling `findClass` if needed.
- **Reusing `Class<?>` is a requirement for a consistent loader**, helping avoid duplicate `defineClass` calls for the same name in a single defining loader.
- **Defining loader differs from initiating loader:** a class obtained from a parent typically has the parent as its owner; one must distinguish between the lookup result and where it was defined.
- **Thread safety and lifecycle:** use `getClassLoadingLock` when overriding `loadClass`; do not treat `findLoadedClass` as a tool for initialization, garbage collection, or hot reload.

Official documentation:

1. [Java SE 17 — ClassLoader.findLoadedClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLoadedClass(java.lang.String)): definition by initiating loader and return value.
2. [Java SE 17 — ClassLoader.loadClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)): default algorithm, `findLoadedClass`, parent delegation, `findClass`, and synchronization.
3. [Java SE 17 — ClassLoader.getClassLoadingLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)): class loading locks and parallel-capable loaders.
4. [JVMS 17 — 5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining loader, initiating loader, and class identity.
5. [JVMS 17 — 5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): type consistency constraints across loaders.
