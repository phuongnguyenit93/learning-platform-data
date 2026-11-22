# Same Class Name but Different Defining Loader in Java

Two Java classes can have the same name—and even be loaded from **the exact same `.class` file with identical bytecode**—yet the JVM still treats them as **two distinct types** if they were **defined by two different class loaders**. This is an important point when using Reflection to identify types: comparing only `Class.getName()` or display names is not enough.

This lesson belongs to the **Type Names and Identity** topic. We will distinguish **class name (binary name)**, **defining class loader**, **initiating class loader**, and **runtime identity of `Class<?>`**; then observe the consequences for casting, method invocation, and plugin design.

## 1. One Class Name Does Not Guarantee Only One Runtime Type

In ordinary Java code, you normally think of `com.example.Plugin` as a single unique type. That assumption appears true because most applications use the **parent class loader delegation** model, causing a single definition to be shared.

However, the JVM allows multiple class loaders to create separate class definitions. For ordinary reference classes, runtime identity can be understood via the pair:

**(binary name, defining class loader)**

For example, two different loaders both define a class with the binary name `com.example.Plugin`:

```text
PluginLoader A                            PluginLoader B
      |                                         |
      | defineClass("com.example.Plugin", ...)  | defineClass("com.example.Plugin", ...)
      v                                         v
Class<?> A                                 Class<?> B

A.getName() == "com.example.Plugin"        B.getName() == "com.example.Plugin"

A.getName().equals(B.getName())  == true
A == B                            == false
A.isAssignableFrom(B)             == false
```

Key observations:

- **Equal names**: `Class.getName()` of both classes can return the exact same string.
- **Different `Class` objects**: `A == B` is `false`; they represent two distinct type definitions.
- **No type compatibility just because names match**: an object of `A` does not automatically become an object of `B`.
- **Bytecode does not determine type identity**: even with identical `.class` contents, if a new loader defines its own copy, the type identity is still different.
- **Same defining loader + same binary name**: within a single loader, defining a class succeeds only once per binary name; attempting a duplicate definition typically causes `LinkageError`.

This rule applies to **reference classes defined by a class loader**. Primitive types are established by the JVM and are not loaded via `defineClass` like ordinary classes.

## 2. Distinguishing Defining Loader and Initiating Loader

The **defining loader** is the class loader that directly **defines** the class, typically via `defineClass(...)` or an equivalent definition mechanism. `Class.getClassLoader()` returns the loader that defined the class (which may be `null` for classes defined by the bootstrap loader).

The **initiating loader** is the loader that the JVM used to **initiate a class-loading request**, thereby recording the initiating relationship. This loader can delegate to its parent, so it is **not necessarily** the loader that actually defines the class.

### Case A: two child loaders delegate to the same parent

```text
ChildLoader 1 ----\
                   \ delegate
                    -> ParentLoader -> define "com.example.Plugin"
                   /                       |
ChildLoader 2 ----/                        v
                                        Same Class<?>
```

Even though there are two child loader objects, both receive back **the exact same `Class<?>`** defined by the parent. You cannot conclude there are two distinct types merely because there are two loaders at the start of the call.

### Case B: each child loader defines the class itself

```text
ChildLoader 1 -> define "com.example.Plugin" -> Class A
ChildLoader 2 -> define "com.example.Plugin" -> Class B
                                               
Class A != Class B
```

The result is two distinct runtime types. Two classes can share the same binary name, the same API, and the same bytes; determining identity still depends on the loader that **actually defines** them.

**Note:** `ClassLoader.loadClass(...)` in its default implementation typically checks already-loaded classes, then delegates up to the parent, and finally falls back to `findClass(...)` if not found. Merely subclassing `ClassLoader` or creating two class loader instances **does not guarantee** two distinct `Class` objects. To actively define a separate copy, you must implement an appropriate loading strategy.

## 3. Java 17+ Example: Same Name, Different Defining Loader, Failed Cast

The runnable example below intentionally creates **two class loaders that each define their own `DemoPlugin`**, while delegating to the parent to share `PluginApi`. This lets us observe both the identity issue and one way for loaders to communicate.

Create three files in the **same directory**.

**File 1 — `PluginApi.java`**

```java
public interface PluginApi {
    String greet();
}
```

**File 2 — `DemoPlugin.java`**

```java
public class DemoPlugin implements PluginApi {
    @Override
    public String greet() {
        return "Hello from plugin";
    }
}
```

**File 3 — `LoaderIdentityDemo.java`**

```java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {

    // Only DemoPlugin is defined separately in each loader.
    // Other types, including PluginApi, still delegate to the parent.
    static final class IsolatedPluginLoader extends ClassLoader {
        private static final String TARGET = "DemoPlugin";

        IsolatedPluginLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";

                    try (InputStream stream =
                                 getParent().getResourceAsStream(resource)) {
                        if (stream == null) {
                            throw new ClassNotFoundException(name);
                        }
                        byte[] bytes = stream.readAllBytes();
                        result = defineClass(name, bytes, 0, bytes.length);
                    } catch (IOException e) {
                        throw new ClassNotFoundException(name, e);
                    }
                }

                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = LoaderIdentityDemo.class.getClassLoader();

        IsolatedPluginLoader loaderA = new IsolatedPluginLoader(parent);
        IsolatedPluginLoader loaderB = new IsolatedPluginLoader(parent);

        Class<?> classA = Class.forName("DemoPlugin", true, loaderA);
        Class<?> classB = Class.forName("DemoPlugin", true, loaderB);
        Object first = classA.getDeclaredConstructor().newInstance();

        System.out.println("Same name: "
                + classA.getName().equals(classB.getName()));
        System.out.println("Same Class: " + (classA == classB));
        System.out.println("Correct defining loader: "
                + (classA.getClassLoader() == loaderA
                && classB.getClassLoader() == loaderB));
        System.out.println("A assignable from B: "
                + classA.isAssignableFrom(classB));
        System.out.println("Is DemoPlugin from parent: "
                + DemoPlugin.class.isInstance(first));

        System.out.println("Is shared PluginApi: "
                + (first instanceof PluginApi));
        PluginApi api = (PluginApi) first;
        System.out.println("Called via interface: " + api.greet());

        try {
            DemoPlugin wrong = (DemoPlugin) first;
            System.out.println(wrong.greet());
        } catch (ClassCastException e) {
            System.out.println("Cast to DemoPlugin: ClassCastException");
        }

        // Two normal loaders both delegating to parent.
        ClassLoader childA = new ClassLoader(parent) {};
        ClassLoader childB = new ClassLoader(parent) {};
        System.out.println("Parent delegation, same Class: "
                + (childA.loadClass("DemoPlugin")
                == childB.loadClass("DemoPlugin")));
    }
}
```

Compile and run from the directory containing all three files, using JDK 17 or later:

```bash
javac PluginApi.java DemoPlugin.java LoaderIdentityDemo.java
java LoaderIdentityDemo
```

**Expected stdout** (without printing environment-dependent loader names/addresses):

```text
Same name: true
Same Class: false
Correct defining loader: true
A assignable from B: false
Is DemoPlugin from parent: false
Is shared PluginApi: true
Called via interface: Hello from plugin
Cast to DemoPlugin: ClassCastException
Parent delegation, same Class: true
```

### Why does the example produce this output?

1. `Class.forName("DemoPlugin", true, loaderA)` requests loading `DemoPlugin` via `loaderA`. For that exact name, the `loadClass` method is overridden to call `defineClass(...)`; similarly for `loaderB`. Thus `classA` and `classB` have the same binary name but two different defining loaders.
2. `findLoadedClass(name)` avoids redefining the same class name within **each** loader across multiple calls. The `getClassLoadingLock(name)` lock keeps lookup/definition consistent under concurrency.
3. For `PluginApi`, both loaders call `super.loadClass(...)`, so the parent defines and supplies **one single interface type**. Both copies of `DemoPlugin` implement that exact `PluginApi`. Therefore, an instance of `classA` can be cast safely to `PluginApi` and have `greet()` invoked.
4. `DemoPlugin.class` in the main code refers to the version loaded by the **parent**, which differs from `classA`. Casting an object of `classA` to `DemoPlugin` from the parent throws `ClassCastException`, even though the class names are identical.
5. `childA` and `childB` at the end do not define their own `DemoPlugin` and instead use the default delegation strategy. Both successfully resolve to **the same `Class<?>`** from the parent.

This is a simple training example: the code reads the `DemoPlugin.class` bytes from the parent's resources and intentionally alters the delegation rule for **one** class. A real-world plugin system must additionally handle packages, dependencies, JAR sources, resources, unloading/lifecycle, and security/protection policies.

## 4. Consequences in Reflection and Type Checking

### Comparing `Class<?>` meaningfully

| Check | What is compared? | Does it prove the same runtime type? |
| --- | --- | --- |
| `a.getName().equals(b.getName())` | Class name string | **No** |
| `a == b` or `a.equals(b)` | `Class` identity | **Yes** |
| `a.getClassLoader() == b.getClassLoader()` | Same defining loader | **Not enough**; must also have the same binary name |
| `a.isAssignableFrom(b)` | Whether a value of type `b` is assignable to a variable of type `a` | Checks type compatibility, not just names |
| `a.isInstance(object)` | Whether the instance is compatible with type `a` | Yes, checks object compatibility |
| `a.cast(object)` | Performs a runtime cast to `a` | Throws `ClassCastException` if incompatible |

**`Class<?>` is an object reflecting a concrete type definition**, not a record holding only a name. When you need to prove the same runtime class, prefer comparing the `Class` objects directly.

### Reflection can fail even when display names match

Suppose a `Method` is obtained from `classA`, and you try to invoke it on an instance of `classB`:

```java
// Additional illustration inside main of LoaderIdentityDemo;
// classA and classB have already been created as in the example above.
Object second = classB.getDeclaredConstructor().newInstance();
var methodFromA = classA.getMethod("greet");

try {
    methodFromA.invoke(second);
} catch (IllegalArgumentException e) {
    System.out.println("Wrong receiver runtime type");
}
```

This is an **additional illustrative code snippet**, not a standalone Java file. `methodFromA` describes the method declared on `classA`, whereas `second` is an object of `classB`, not a valid instance of `classA`; the reflective call is rejected with `IllegalArgumentException` for the receiver.

In similar situations, an API that obtains a `Class<?>` from one loader and then uses a constructor/field/method or cast with an object from another loader can fail unexpectedly. You should not look only at `getName()` and assume both sides are compatible.

### What does `ClassCastException` "X cannot be cast to X" mean?

On some Java versions, the runtime error message can show that a class cannot be cast to a class **with the same name**, along with loader/module information to distinguish them. There is no contradiction: the two names match, but the two `Class` objects are different. You should not rely on the **exact wording** of the message because formatting and loader naming vary across JDKs/environments.

## 5. Diagnosing: Identifying Which Class Is Actually Being Used

When encountering cast or Reflection errors in plugins, servlet containers, application servers, hot reload, or test environments, inspect **the name**, **the `Class` object**, and **the defining loader** on both sides.

The following helper snippet can be placed into diagnostic code; it is **not a standalone program**:

```java
static void describe(String label, Object value) {
    Class<?> type = value.getClass();
    ClassLoader loader = type.getClassLoader();

    System.out.println(label + " name=" + type.getName());
    System.out.println(label + " loader=" + loader);
    System.out.println(label + " module=" + type.getModule().getName());
}
```

When comparing two objects:

```java
Class<?> left = leftObject.getClass();
Class<?> right = rightObject.getClass();

System.out.println("Same name: " + left.getName().equals(right.getName()));
System.out.println("Same Class: " + (left == right));
System.out.println("Same defining loader: "
        + (left.getClassLoader() == right.getClassLoader()));
```

**Notes on reading logs:**

- `getClassLoader() == null` is common for classes defined by the **bootstrap loader**; do not interpret `null` as an error.
- `getModule().getName()` can be `null` for an unnamed module; module name **does not replace** the defining loader for determining type identity.
- `ClassLoader.toString()`, loader names, and hash-like identifiers only assist investigation. To assert the same loader programmatically, compare loader objects with `==`.
- Cross-check the classpath, loading order, and actual JARs when suspecting duplicate classes; **the same bytecode source does not make two `Class` objects identical**.
- `Thread.currentThread().getContextClassLoader()` is the **thread's context loader**, used by many frameworks to find resources/classes; it is not necessarily the defining loader of the object under inspection. Prefer `object.getClass().getClassLoader()` when asking "who defined this type?".

When reading stack traces, diagnose both sides of the cast or parameter-receiving method; if an API returns an object from a separate loader, the receiver must check the shared contract rather than casting blindly to its own copy of the class.

## 6. Why Is This Mechanism Useful and Why Is It Error-Prone?

### Benefit: isolated namespaces and lifecycles for plugins

A host can use a separate loader per plugin to avoid library version conflicts or to replace plugins over their lifecycle. Two plugins can depend on a class with the same binary name while each plugin sees its own definition. This provides **type/dependency isolation**, even though it is **not a security sandbox mechanism**.

A hot-reload feature can create a new loader and load a new version of a class while objects from the old loader still exist. Old and new objects are **not necessarily** compatible just because the class name did not change.

### Risk: "split-brain type"

If the host defines `com.example.api.PluginApi` with one loader, but the plugin also defines **its own copy of that exact interface**, then the statement:

```java
PluginApi api = (PluginApi) pluginObject;
```

can fail. Each `PluginApi` has a different defining loader, so the two interface types do not form a single runtime contract, even if the source code/interface methods are identical.

**Common organization approach:** host and plugin must agree on the types **used as contracts across the boundary** (interfaces, shared DTOs...). Typically the parent/common loader defines the shared API; the child loader loads plugin-specific parts and delegates shared APIs to the parent.

This does not mean "every plugin must be strictly parent-first for everything". A child-first strategy may be needed when a plugin carries its own dependencies. The core rule is to **clearly define which types must share a single runtime identity**.

### Method signature conflicts and loader constraints

The JVM also enforces **loader constraints** to ensure that types appearing in method/field signatures interacting across loaders are resolved consistently in certain cases. When constraints require type identity but two loaders have defined incompatible classes, a `LinkageError` can occur. This differs from a `ClassCastException` at a cast statement, yet both stem from class loader boundaries and type identity.

## 7. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Same class name means same type." | Reference class identity also depends on the defining loader. |
| "Two loader instances always create two different types." | If both delegate to the same defining loader, they receive the same `Class`. |
| "Same JAR/bytecode means casting will work." | The same bytecode can still be defined twice by two different loaders. |
| "`getName()` is enough to check types." | Use names only for display/lookup; use `Class`, `isInstance`, and `isAssignableFrom` for type checks. |
| "`Class.forName(...)` always uses the same loader." | There is an overload accepting an explicit loader; loader choice affects the result. |
| "Changing the TCCL changes the class of an existing instance." | The `Thread Context ClassLoader` does not change the defining loader of an already-defined class. |
| "ClassLoader is a security sandbox." | Namespace/dependency isolation does not automatically create a security boundary. |

## 8. Applying This in System Design

When preparing to write a plugin framework or an API using Reflection, you can follow this process:

1. **Identify the shared contract**: interfaces and data types that must pass from plugin to host and vice versa.
2. **Place the contract in a shared loader**: ensure both host and plugin receive the same `Class<?>` for every contract type.
3. **Place implementations and private dependencies in appropriate loaders**: potentially each plugin's own loader.
4. **Load the plugin through the chosen loader** and check `sharedApiClass.isAssignableFrom(implementationClass)` or `sharedApiClass.isInstance(instance)` before casting.
5. **Do not store class names as proof of compatibility**: use `Class` identity and actual assignability checks.
6. **Log both loaders on failure**: diagnose both the source and receiving sides, especially when `ClassCastException`/`LinkageError` occurs.
7. **Manage loader/instance lifecycles**: avoid retaining references, threads, static caches, or registrations that keep old loaders/plugins alive unintentionally during hot reload.

Most ordinary application code does not need custom class loaders. Understanding class identity rules helps you read Reflection metadata accurately, explain "same-name" cast errors, and make informed decisions when working with plugins/frameworks/containers.

## 9. Takeaways and Self-Check

**Takeaway:** For reference classes, **binary name + defining loader** determines runtime type identity. An initiating loader may merely delegate, so the number of loaders initiating a load does not indicate the number of definitions. Compare `Class<?>` directly, check `isInstance`/`isAssignableFrom`, and share interfaces in the right loader when exchanging objects across plugin boundaries.

Self-check:

1. Two objects have the same `getClass().getName()`, yet casting fails. What else would you check?
2. Two child loaders both call `loadClass("x.Plugin")` and return the exact same `Class<?>`. Who could the defining loader be?
3. In the runnable example, why does casting to `DemoPlugin` fail while casting to `PluginApi` succeeds?
4. Does changing only the thread context class loader change `getClass().getClassLoader()` of an already-created object?
5. If both host and plugin put an API interface into their own separate loaders, what problem can happen?