# Parent delegation and the purpose of sharing platform types in Java

**Parent delegation** (delegating to the parent class loader) is the default mechanism of `java.lang.ClassLoader`: when a loader receives a request to load a class, it **prioritizes letting the parent loader search for the class first**, and only searches for/defines the class itself if the delegation path cannot load it. This organization allows the application and child loaders to **share the definitions of platform types and API types already provided by the parent loader**, preventing multiple runtime copies of the same class name from breaking type assignment, casting, or communication between plugins and the application.

Two principles to remember:

1. **A class name alone is not enough to identify a Java type at runtime.** The runtime class identity depends on both the *binary name* and the *defining class loader*.
2. **Parent-first is the default policy of `ClassLoader.loadClass`**, not a mandate forcing every custom class loader to behave identically. Some specialized loaders intentionally use a different order to isolate dependencies.

## 1. Why does Java have multiple class loaders?

An application does not necessarily have a single table of class names. Class loaders allow the JVM to locate, define, and organize classes coming from different sources, such as JDK modules, the classpath, plugins, runtime-generated code, or independent deployment scopes.

In a typical Java 17+ setup, the loader chain can be pictured as follows:

```text
Application / System ClassLoader
        |
        | parent
        v
Platform ClassLoader
        |
        | parent
        v
Bootstrap loader (provided by the JVM, not a regular Java ClassLoader)
```

- The **Bootstrap loader** defines many core classes such as `java.lang.Object` and `java.lang.String`; `String.class.getClassLoader()` returns `null`, which by API convention represents the bootstrap loader.
- The **Platform class loader** is responsible for loading classes in the set of platform modules under the modern JDK mechanism.
- The **Application/System class loader** typically loads application code on the classpath and corresponding components.

The diagram is a common model to help understand parent delegation, **not a complete map of every class-loading path**: the Java Platform Module System (JPMS), module readers, custom class loaders, and certain JDK implementations can make module assignment or class routing more complex than the illustrated chain. In particular, `getParent() == null` does not mean “there is no platform code at all to delegate to”; in the `ClassLoader` API, it represents the path to the bootstrap loader.

An application can also create other loaders:

```text
                  Application Loader (contains shared-api)
                  /                  \
                 v                    v
           Plugin A Loader      Plugin B Loader
           (plugin-a.jar)      (plugin-b.jar)
```

The two plugins can have their own implementations while both seeing `shared.api.Plugin` from the application loader. It is this **shared API definition** that allows plugin objects to be checked with `instanceof`, cast to the interface, and passed to the application.

## 2. How does parent delegation work?

The central method is `ClassLoader.loadClass(String name)` or its protected variant `loadClass(String name, boolean resolve)`. For the **default implementation of `ClassLoader`**, the algorithm can be described as:

1. Receive a **binary name** such as `com.example.service.OrderService`, not the path `com/example/service/OrderService.class`.
2. Use `findLoadedClass(name)` to check whether the current loader is already an *initiating loader* of that class; if so, return the known `Class<?>`.
3. If not, **delegate to the parent loader**, or try the bootstrap loader when there is no Java parent.
4. Only when the parent/bootstrap path cannot find the class, call `findClass(name)` on the current loader.
5. If resolution is requested, call `resolveClass(...)`; return the `Class<?>` object.

Illustrated in pseudocode (not a verbatim JDK implementation):

```text
loadClass(binaryName, resolve):
    appropriate lock for the class-loading request

    c = findLoadedClass(binaryName)

    if c == null:
        try:
            c = parent != null
                ? parent.loadClass(binaryName)
                : bootstrapFind(binaryName)
        catch ClassNotFoundException:
            c = null

        if c == null:
            c = findClass(binaryName)

    if resolve:
        resolveClass(c)

    return c
```

When writing a custom loader, you typically override `findClass` to read the bytes and call `defineClass`; inheriting `loadClass` preserves the parent-first order. Overriding `loadClass` to force child-first is a choice with compatibility consequences and should be scoped very specifically.

**Error conditions:** if the parent cannot find the class, it signals `ClassNotFoundException` so the child loader has a chance to search for it itself. However, if the class file has a real problem—such as `ClassFormatError`, `VerifyError`, or another linking error—it must not be treated by default as “not found” in order to silently substitute another version. These are fundamentally different kinds of errors.

### Parent-first does not necessarily always call `findClass`

If the parent has already found `java.util.List` or `com.example.SharedApi`, the child class loader usually **does not have to redefine** that name. It receives the same `Class<?>` reference provided by the parent path.

Conversely, when the parent does not contain `com.plugin.Feature` but the child loader has the bytecode for this class, the child calls `findClass`, and then `defineClass` to create a runtime class defined by the child itself.

`resolveClass` belongs to the linking phase and does not mean executing `static` initializer blocks. Calling `loadClass` normally **does not require initializing the class**.

## 3. What does “sharing platform types” mean?

This is the core of parent delegation. Java checks type compatibility based on **runtime type identity**. For a class/interface with the same binary name, different defining loaders generally create **two different types**.

We can represent the identity of a regular class type as a pair:

```text
Runtime type identity =
    (binary name, defining class loader)
```

Example:

```text
("shared.api.Message", ApplicationLoader)  ≠
("shared.api.Message", PluginLoader)
```

Even though the class name and bytecode are identical, these are still two different runtime definitions. If a plugin returns an object implementing its own self-defined version of `shared.api.Message`, the application using the version from the parent may not accept the cast or API signature as expected.

### 3.1. Core JDK types

Types such as `Object`, `String`, `Throwable`, `Class`, `List`, and `Map` provide a common type vocabulary for all parts of the application to communicate. The parent delegation path enables child loaders to use those same definitions from bootstrap/platform according to the runtime architecture.

Examples:

- A plugin creates a `String` and returns it to the application. Both use the same platform class `java.lang.String`.
- A plugin returns a `java.util.List<String>`. The raw type `java.util.List` and `String` are shared at runtime; element correctness and the generic contract must still be respected (generic type parameters are largely erased at runtime).
- A plugin throws `IllegalArgumentException`. The application recognizes the exception type belonging to the platform runtime.

Parent delegation is part of what prevents “two incompatible `java.lang.String` types”, but it **does not automatically guarantee that all plugin APIs are compatible**: application-specific APIs and dependencies must still be defined by a shared loader or made compatible through an appropriate bridging mechanism.

### 3.2. Shared interfaces and models

Suppose we have the API:

```java
package shared.api;

public interface Plugin {
    String execute();
}
```

The application loads `shared.api.Plugin` from the parent loader. Each plugin loader should load **that exact same interface** via delegation, while `plugins.alpha.AlphaPlugin` and `plugins.beta.BetaPlugin` can be defined by their respective child loaders. The application can then receive and invoke the objects using the `shared.api.Plugin` type.

However, if each plugin bundles its own copy of `shared.api.Plugin` and a custom child-first loader defines it independently, having the same package and class name does not make the two interfaces the same type. Operations such as casting and service registration can fail.

The interface snippet above is **an illustrative API excerpt** without a `main` method and needs to be compiled/deployed as a shared dependency of the plugin system.

## 4. Java 17+ example: parent-first shares the Class object, child-first creates a different type

Practice with two Java files in the **same source directory**. The goal is to demonstrate default parent delegation and contrast it with a loader that intentionally goes against the policy.

Create the file **`SharedApi.java`**:

```java
public final class SharedApi {
    public SharedApi() {
    }

    public String message() {
        return "hello";
    }
}
```

Create the file **`ParentDelegationDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;

public class ParentDelegationDemo {
    static final class SelectiveChildFirstLoader extends ClassLoader {
        private final String nameToIsolate;

        SelectiveChildFirstLoader(ClassLoader parent, String nameToIsolate) {
            super(parent);
            this.nameToIsolate = nameToIsolate;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(nameToIsolate)) {
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
            String resourceName = name.replace('.', '/') + ".class";

            try (InputStream stream =
                    getParent().getResourceAsStream(resourceName)) {
                if (stream == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = stream.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader =
                ParentDelegationDemo.class.getClassLoader();

        ClassLoader defaultChild = new ClassLoader(appLoader) {
        };
        Class<?> delegated = defaultChild.loadClass("SharedApi");

        System.out.println("Parent-first shares class: "
                + (delegated == SharedApi.class));

        ClassLoader isolatedLoader =
                new SelectiveChildFirstLoader(appLoader, "SharedApi");
        Class<?> isolated = isolatedLoader.loadClass("SharedApi");

        System.out.println("Same binary name: "
                + isolated.getName().equals(SharedApi.class.getName()));
        System.out.println("Same runtime class: "
                + (isolated == SharedApi.class));
        System.out.println("Same defining loader: "
                + (isolated.getClassLoader()
                        == SharedApi.class.getClassLoader()));

        Object object = isolated.getDeclaredConstructor().newInstance();
        System.out.println("Can cast to parent's SharedApi: "
                + (object instanceof SharedApi));

        try {
            SharedApi converted = (SharedApi) object;
            System.out.println(converted.message());
        } catch (ClassCastException expected) {
            System.out.println("Cast result: ClassCastException");
        }

        System.out.println("String uses bootstrap loader: "
                + (String.class.getClassLoader() == null));
    }
}
```

Compile and run with JDK 17+ from the directory containing both files:

```bash
javac --release 17 -d out SharedApi.java ParentDelegationDemo.java
java -cp out ParentDelegationDemo
```

Expected output with a standard Java runtime:

```text
Parent-first shares class: true
Same binary name: true
Same runtime class: false
Same defining loader: false
Can cast to parent's SharedApi: false
Cast result: ClassCastException
String uses bootstrap loader: true
```

**Why do we get this result?**

1. `defaultChild` is a child loader that simply inherits `ClassLoader.loadClass`. When it requests `SharedApi`, the application loader can already find the class file in `out` and provides the same runtime class as `SharedApi.class`, so the first comparison returns `true`.
2. `SelectiveChildFirstLoader` is written specifically to **prioritize defining the exact name `SharedApi` on its own**. It reads the `SharedApi.class` bytecode as data, calls `defineClass`, and creates a new `Class<?>` with a **different defining loader**.
3. `isolated.getName()` and `SharedApi.class.getName()` are identical, yet the two `Class` objects are different. The object instantiated via reflection from the isolated version is not an instance of the `SharedApi` type on the application loader side.
4. Therefore, `instanceof` returns `false` and the cast throws `ClassCastException`. This happens **even when the bytecode for both versions of the class is the exact same file**.
5. `java.lang.String` still has the bootstrap loader as its defining loader; the child loader does not redefine `String` itself.

**Example scope caveat:** This loader is only meant to demonstrate the difference in type identity. It intentionally breaks the parent-first order for a single specific name and is not a complete plugin manager. Fetching bytes via `getParent().getResourceAsStream(...)` merely simplifies obtaining sample bytecode; in a real plugin system, you must manage bytecode sources, shared API classes, package sealing, access permissions, dependencies, and loader lifecycles.

### Observing with Class#getClassLoader()

From the example:

```java
ClassLoader definingLoader = isolated.getClassLoader();
ClassLoader parentDefiningLoader = SharedApi.class.getClassLoader();
boolean sameDefinition = isolated == SharedApi.class;
```

This is **an illustrative snippet using variables already declared in `main`**, not a standalone program. It emphasizes that `getClassLoader()` returns the loader that *defined* the class, whereas another loader may act as the *initiating loader* because it successfully delegated the lookup. Do not conclude that “the child defined the class” merely because code called `child.loadClass(...)`.

## 5. What benefits does parent-first provide?

| Goal | How does parent delegation help? | Limitations |
|---|---|---|
| **Shared platform type identity** | Child uses `String`, `Object`, `Throwable`, etc. defined by the platform runtime | Does not verify all logic that uses those types |
| **Shared API between app and plugin** | Same interface, DTO, or contract from the parent loader | Requires placing the shared API in the actual parent |
| **Avoid duplicate definitions** | Child does not need to load/define a class that the parent has already loaded | Parent may provide a different version than the one the plugin expects |
| **Reduce risk of spoofing core classes** | Normal loaders prioritize JDK classes from parent/bootstrap | This is not a comprehensive sandbox; custom class loaders can change the strategy within the scope permitted |
| **Simplify shared dependencies** | Multiple children share core libraries and class identity | Does not automatically resolve dependency version conflicts or module readability |
| **Maintain a single static state of a shared class** | Children see the same runtime class from the parent and its static fields | Can create coupling or conflicts over shared configuration |

There is a **trade-off with isolation**: once the parent already provides the name `com.lib.JsonParser` version A, the child may not be able to use version B with the same name along its parent-first path. This is why some plugin containers, application servers, or module frameworks design a different namespace/loader policy for implementations and private libraries.

## 6. Parent-first does not mean “all classes are loaded by the parent”

We need to distinguish three scenarios:

### A. Parent has the class

```text
child.loadClass("shared.api.Plugin")
    -> parent.loadClass(...)
    -> succeeds
    -> child receives the exact same Class<?> from parent
```

In a plugin architecture, this is the expected outcome for `shared.api.Plugin`.

### B. Parent does not have the class; child has the class

```text
child.loadClass("plugins.alpha.AlphaPlugin")
    -> parent: ClassNotFoundException
    -> child.findClass(...)
    -> child.defineClass(...)
    -> child defines the plugin implementation
```

This is also standard parent delegation: the child loader searches only after the parent misses.

### C. Parent has the class, but child wants its own copy

```text
child-first for a specific namespace:
    -> child.findClass(...)
    -> child.defineClass(...)
    -> potentially a different runtime type from the same-named class in parent
```

This policy can be suitable for plugin isolation, but **cross-boundary APIs must be excluded** from the isolated loading scope. If the interface over which the app and plugin communicate is defined twice, the two sides may not be able to cast between each other.

**Common design rule:** Keep `java.*` and shared contracts under parent delegation; use a child-specific namespace for private implementation code. A specialized loader may have an even more fine-grained policy, but you should not copy every dependency into the child in an uncontrolled manner.

## 7. Class identity and loader constraints one step deeper

A JVM class is not identified solely by its file name, source URL, or source code. It is defined by its *binary name* together with its *defining loader*. Therefore:

```text
Loader P defines shared.api.Event
Loader A delegates shared.api.Event to P
Loader B delegates shared.api.Event to P

A's Event == B's Event == P's Event
```

Conversely:

```text
Loader A defines shared.api.Event
Loader B defines shared.api.Event

A's Event != B's Event
```

When classes from different loaders interact via method/field descriptors, the JVM enforces **loading constraints** to preserve type consistency in the corresponding contexts. Conflicts can lead to `LinkageError`, whereas an invalid cast at runtime can lead to `ClassCastException`.

Real-world example: `com.example.User cannot be cast to com.example.User` sounds absurd if you only look at the class name, but it can be completely accurate when the two `User` classes have different defining loaders. Some modern JDK stack traces also include the modules/loaders involved, making it easier to identify the root cause.

It is also important to distinguish:

- `ClassNotFoundException` is typically thrown by explicit lookup APIs such as `loadClass` or `Class.forName` when a class cannot be found.
- `NoClassDefFoundError` typically occurs when the JVM needs to link/use a class whose definition can no longer be resolved; it can also happen when the class previously **failed initialization**.
- `ClassCastException` can be caused by two incompatible runtime types, even when they share the same name.
- `LinkageError` can also arise from loader constraints, duplicate definitions, version mismatches, or other linking errors.

Do not conclude that all of these errors are caused by “broken parent delegation”. Inspect the class name, *defining loader*, classpath/module path, and actual versions.

## 8. Why can't the parent see child classes?

The relationship **delegates from child up to parent**; it does not automatically allow the parent to discover classes inside the child.

```text
Parent loader: contains shared.api.Plugin
       ^
       | parent-first delegation
       |
Child loader: contains plugins.alpha.AlphaPlugin
```

The child can load the interface from the parent. However, if the parent calls `parent.loadClass("plugins.alpha.AlphaPlugin")`, it does not automatically scan a list of every child loader to find this class.

The way to communicate is for **the child to instantiate the implementation and expose it as the shared interface**, or for the system to actively maintain a registry/loader reference to locate the plugin. You should not expect Java to provide “reverse delegation” automatically.

### Thread context class loader (TCCL)

Some SPIs/frameworks must locate providers housed in a child loader even when the lookup code executes inside a library defined by the parent. In such cases, the **thread context class loader** can serve as a hint:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> provider = loader.loadClass("plugins.alpha.AlphaPlugin");
```

This is an **illustrative snippet** that requires the appropriate loader to already be set on the thread; `getContextClassLoader()` can return `null` and `loadClass` can throw `ClassNotFoundException`. In a real application, both cases must be handled.

The TCCL does not automatically alter how `ClassLoader.loadClass` resolves every class. It is simply a loader reference that code or a framework can explicitly choose to use; for example, `ServiceLoader` has ways of selecting an appropriate loader to locate providers. Especially in a thread pool, you must restore the context loader after the task if you temporarily changed it, to prevent leaking plugin context across requests.

## 9. Distinguishing parent delegation from easily confused concepts

### Classpath and module path

The **classpath** determines the sources where classes can be searched for; **parent delegation** determines which loader is queried and in what order. Having a `.class` file inside the child's JAR does not mean the child will always define the class: if the parent already has a class with the same name, the parent wins by default.

In **JPMS** (Java 9+), module readability, exports/opens, and module-to-loader mapping introduce additional restrictions/relationships. A loader may load a class while code is still prevented from accessing a package due to module/access rules. Do not equate the parent delegation mechanism with module access control.

### Loading, linking, and initialization

- `loadClass("pkg.Type")` takes a binary name and returns `Class<?>` after the appropriate lookup/loading process, optionally including resolution if requested by the call path.
- `Class.forName("pkg.Type", false, loader)` allows obtaining `Class<?>` without requiring initialization.
- `Class.forName("pkg.Type")` typically requires initialization.
- `String.class.getClassLoader() == null` is a way to observe that the bootstrap loader is the defining loader, **not** proof of the invocation order of class-loading APIs.

### Class and resource

`ClassLoader.getResource("pkg/Type.class")` searches for a **resource** using `/` separators, whereas `loadClass("pkg.Type")` loads a **class** by its binary name. Both can be implemented/delegated according to separate policies; finding a resource file does not necessarily mean the class is defined by that querying loader. Do not rely solely on the `.class` path to assert identity.

### “Parent-first = complete security”

Parent-first makes it difficult to arbitrarily replace critical classes found by the parent, and defining packages under `java.*` is further restricted by the Java runtime. Nevertheless, **a class loader is not a general security sandbox**: it does not replace access control for files, networks, processes, native code, or evaluating the trustworthiness of a plugin.

## 10. Common design mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Packaging the shared API inside every plugin and using child-first for that API | Incorrect `instanceof`/casts, loader constraint conflicts | Define the shared API in the parent; have plugins delegate the API namespace |
| Calling `child.loadClass` and assuming the child always defined the class | Misdiagnosing which loader owns the class | Inspect `clazz.getClassLoader()` and compare `Class<?>` objects |
| Overriding the entire `loadClass` method to apply child-first to every name | Collisions with core/third-party/shared types | Apply child-first only to the specific private namespaces that actually need it |
| Changing the binary name to `pkg/Type.class` when calling `loadClass` | `ClassNotFoundException` | Use `pkg.Type`; paths are only for resource lookups |
| Assuming the parent can load implementations located only in the child | Plugin cannot be found | Use the plugin's loader, a registry, or an appropriate context loader |
| Assuming having the same FQCN means casting will succeed | `ClassCastException` or `LinkageError` | Check the defining loaders and where shared contracts are placed |
| Assuming parent-first automatically resolves all version differences | Plugin uses the wrong API/`NoSuchMethodError` | Design the classpath and dependency isolation scopes properly |
| Holding references to child loaders, `Class` objects, threads, or instances indefinitely | The loader cannot easily be garbage-collected when the plugin unloads | Release registries, tasks, threads/TCCL, and resources according to lifecycle |

An important case is the **static singleton**. If the same class is defined separately in two loaders, each runtime class has its own static fields. When the class is shared through the parent, the children all access the static state of **the exact same runtime class**. This can either be intentional (a shared registry) or a risk (coupling and difficulty isolating configuration); you must choose the loader scope deliberately.

## 11. How to diagnose class-loading issues

When encountering a puzzling `ClassCastException` or dependency conflict, proceed in order:

1. **Obtain the binary names of both types** from the exception or relevant code.
2. **Print the defining loaders**: `someObject.getClass().getClassLoader()`, `ExpectedApi.class.getClassLoader()`, even when one side is `null` (bootstrap).
3. **Compare `Class<?>` directly**: `obj.getClass() == ExpectedApi.class` when an exact-class check makes sense; or `ExpectedApi.class.isAssignableFrom(obj.getClass())` when checking a subtype relationship.
4. **Inspect the parent chain** and the override policies for `loadClass`, `findClass`, and `getResource`. Default parent-first differs from custom child-first.
5. **Check the placement of APIs/dependencies**: is the shared contract located in the app/platform parent or duplicated inside plugins?
6. **Verify the actual class origin** by inspecting the code source/resource when possible; note that a URL path is no substitute for defining loader information.
7. **Examine the module/service discovery context** if using JPMS, `ServiceLoader`, or the thread context class loader.
8. **Fix the classpath and loader policy deliberately**. Avoid workarounds such as renaming classes, catching and ignoring `ClassCastException`, or forcing reflection access outside the contract.

A diagnostic helper can be placed in a Java method:

```java
static void describe(Class<?> type) {
    System.out.println("Name: " + type.getName());
    System.out.println("Defining loader: " + type.getClassLoader());
}
```

This is a helper method that can be used inside a class, **not a standalone program**. The output of the loader line depends on the JVM, deployment, and how the loader overrides `toString()`, so there is no fixed stdout for this example.

## 12. Knowledge self-check

1. **Does a child calling `loadClass("java.lang.String")` necessarily define String itself?** No. In the standard case, the platform class is found via delegation and shares the definition from bootstrap.
2. **Does parent-first mean the child never defines classes?** No. If the parent cannot find it, the child can call `findClass`/`defineClass`.
3. **Are two `com.acme.User` classes with identical bytecode but different defining loaders the same type?** No. Their runtime identities differ, so casts can fail.
4. **Why must a shared interface reside in a common loader?** So that the application and plugins use the same runtime type as the contract, allowing values from plugins to be assigned to the interface already known by the application.
5. **When can child-first be useful?** When a plugin needs its own dependency version that the parent should not impose; there must be rules protecting shared APIs.
6. **Can the parent automatically find every class located only in a child loader?** No; it requires a loader reference, registry, service mechanism, or context loader.
7. **Is calling `child.loadClass("pkg.Type")` and observing `clazz.getClassLoader() == parent` a bug?** No, that may be parent delegation working exactly as intended.
8. **Can parent delegation replace module access controls and application security?** No. Those are independent mechanisms with their own goals.

## 13. Official references

- Java SE 17 API, `ClassLoader` and default behavior of `loadClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification, `5.3 “Creation of Classes and Interfaces”` (defining/initiating loaders, class identity): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java Virtual Machine Specification, `5.3.4 “Loading Constraints”`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- Java SE 17 API, `Thread.getContextClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#getContextClassLoader()

**Key takeaway:** Parent delegation by default prioritizes searching for classes in the parent loader; as a result, multiple child loaders can use **the same platform types and shared contracts**. When the same binary name is defined by different loaders, they are different runtime types. Place shared APIs in the parent loader, isolate implementations in child loaders, and use a child-first policy only when a separate dependency scope is truly required.
