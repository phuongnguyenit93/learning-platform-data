# ClassCastException When Source and Target Class Names Are the Same

The message **`ClassCastException`: “class A cannot be cast to class A”** looks contradictory: the source and target type names are the same, yet the cast still fails. In the JVM, the identity of a **class/interface** is not just its name, but the **pair (binary name, defining class loader)**. Two class loaders can independently define the same name `com.example.Plugin` and form **two distinct JVM types**, even when using a single `.class` file with byte-for-byte identical bytecode.

This lesson focuses on the type identity mechanism, how to reproduce it using Java 17, distinguishing defining and initiating loaders, diagnosing stack traces, and designing boundaries between a host, plugins, or an application server.

## 1. Why Does the Same Name Not Guarantee the Same Class?

~~~text
                  com.example.Plugin
                    /           \
                   v             v
             Loader A         Loader B
                   |             |
              Plugin(A)       Plugin(B)
                   \             /
                 NOT THE SAME TYPE
~~~

Suppose `classA` and `classB` are `Class<?>` objects **actually defined** by two loaders:

~~~java
classA.getName().equals(classB.getName())  // true
classA == classB                           // false
~~~

This is an **illustrative fragment**, not a standalone program. Fundamental rules:

- `Class.getName()` returns the binary name; it is not sufficient to prove that two types share the same identity.
- `Class.getClassLoader()` returns the **defining loader** of the class. For many core classes defined by the bootstrap loader, the API uses `null` to represent the loader.
- `Object.getClass()` returns the runtime class definition of the object; casts rely on that type and inheritance/implementation relationships.
- `instanceof`, `Class.isInstance(...)`, `Class.cast(...)`, and the `checkcast` bytecode **do not merely compare name strings**.
- A single loader cannot define two separate classes with the same binary name within its own namespace; an invalid duplicate definition attempt can cause a `LinkageError`. The error in this lesson typically comes from **two different defining loaders**.
- Two different child loaders can still return **the same `Class<?>`** if both delegate to a parent that already defined the class. You must check the actual defining loader, rather than merely comparing the two initial loader objects.

For array types whose elements are reference classes, the identity of the array type is affected by the element type's identity. Do not treat `Plugin[]` from two different `Plugin` definitions as a compatible array type.

## 2. Why Does the JVM Throw ClassCastException?

An object is created from `Message(A)`, while the target code expects the type `Message(B)`:

~~~text
Loader A                  Loader B
   |                         |
   v                         v
Message(A)              Message(B)
   |                         ^
   v                         |
object ------ cast ----------+
                 |
          ClassCastException
~~~

The JVM checks whether the object is compatible with the target type based on the linked class/interface relationships. Two definitions with the same name from two independent loaders **do not automatically have a type relationship**, even when their bytecode is completely identical.

Real-world example: a plugin implements `com.acme.api.Task` defined by the plugin's loader, but the host expects `Task` defined by the host's loader. An object from the plugin may fail to cast to the host's interface. Reflection only helps locate/invoke methods according to appropriate access permissions; it does not turn two type definitions into the same one.

## 3. Java 17 Program: Same Bytecode, Two Class Loaders, and Cast Failure

Create **two files** in the same directory. The main program uses two `URLClassLoader` instances with the same URL pointing to the directory containing `Payload.class`, but each loader's parent is `null`, so the application class `Payload` is not delegated to the application loader. Core classes such as `java.lang.Object` can still be served by the bootstrap loader.

**File `Payload.java`:**

~~~java
public class Payload {
    public String value() {
        return "same bytecode";
    }
}
~~~

**File `LoaderCollisionDemo.java`:**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderCollisionDemo {
    public static void main(String[] args) throws Exception {
        URL directory = Path.of(".")
                .toAbsolutePath()
                .normalize()
                .toUri()
                .toURL();

        try (URLClassLoader loaderA =
                     new URLClassLoader(new URL[] { directory }, null);
             URLClassLoader loaderB =
                     new URLClassLoader(new URL[] { directory }, null)) {

            Class<?> classA = Class.forName("Payload", true, loaderA);
            Class<?> classB = Class.forName("Payload", true, loaderB);

            Object objectA = classA.getDeclaredConstructor().newInstance();

            System.out.println("Names equal: "
                    + classA.getName().equals(classB.getName()));
            System.out.println("Same Class: " + (classA == classB));
            System.out.println("Loader A defines A: "
                    + (classA.getClassLoader() == loaderA));
            System.out.println("Loader B defines B: "
                    + (classB.getClassLoader() == loaderB));
            System.out.println("A accepts object: "
                    + classA.isInstance(objectA));
            System.out.println("B accepts object: "
                    + classB.isInstance(objectA));

            try {
                classB.cast(objectA);
                System.out.println("Unexpected cast");
            } catch (ClassCastException e) {
                System.out.println("Result: ClassCastException");
            }
        }
    }
}
~~~

Compile/run with **JDK 17 or newer**, in the directory containing the files:

~~~bash
javac --release 17 Payload.java LoaderCollisionDemo.java
java LoaderCollisionDemo
~~~

**Exact stdout:**

~~~text
Names equal: true
Same Class: false
Loader A defines A: true
Loader B defines B: true
A accepts object: true
B accepts object: false
Result: ClassCastException
~~~

Analysis:

1. Only **one** `Payload.class` is produced by `javac`, yet two independent loaders define two copies of `Payload` upon request.
2. `Class.forName("Payload", true, loaderX)` requests loading/initializing the class through the passed-in loader. Each `Payload` definition here belongs to its respective defining loader.
3. `getName()` returns `Payload` for both, but `classA == classB` evaluates to `false`; the two `Class<?>` objects do not have the same identity.
4. `objectA` is created by the constructor of `Payload(A)`, so `classA.isInstance(objectA)` is `true`, whereas `classB.isInstance(objectA)` is `false`.
5. `classB.cast(objectA)` throws `ClassCastException`. The example catches the exception to print a fixed string; the original JVM message may include environment-dependent loader/module details.
6. `try-with-resources` calls `URLClassLoader.close()`; this closes the loader's resources and **does not force the JVM to unload the classes immediately**.

The example uses the default package and a `null` parent to make the two independent namespaces easy to observe; this is **not a standard configuration for all plugins**.

### What If You Cast Directly From Application Code?

The following fragment (not part of the standalone program above):

~~~java
Payload p = (Payload) objectA;
~~~

can also fail: `Payload` in the application's source code is linked to the application loader's type, whereas `objectA` belongs to `Payload(A)`. If the application loader has already loaded `Payload`, **three** class definitions with the same name may exist in the process.

## 4. Reading the “A cannot be cast to A” Message

A message on a modern JVM might look like:

~~~text
class com.acme.Plugin cannot be cast to class com.acme.Plugin
(com.acme.Plugin is in unnamed module of loader LoaderA ...;
 com.acme.Plugin is in unnamed module of loader LoaderB ...)
~~~

This is an **illustrative example of the message structure**, not fixed stdout. Loader names, addresses, modules, and formatting may vary across runtimes.

| Component | How to Interpret |
| --- | --- |
| Two identical class names | Same binary name; does not prove the same identity. |
| Two different loaders | Inspect the two actual defining loaders of the source and target. |
| `unnamed module` | Two loaders can each have their own unnamed module and do not automatically share classes. |
| Explicit module name | Helps locate the layer/module, but does not replace checking Class identity. |
| Stack trace at the cast | Shows where the object crosses the boundary and which type the receiver expects. |

Having the same JAR URL, the same package, the same module name, the same bytecode, or the same source file **is not enough to prove it is the same class**. Conversely, multiple child loaders can still receive the same class defined by a parent.

## 5. How Defining Loader and Initiating Loader Differ

- **Defining loader:** the loader that actually defines the class from a ClassFile; it participates in the type's identity. `Class.getClassLoader()` indicates this loader.
- **Initiating loader:** the loader that initiates the load-by-name request; it may delegate to a parent and receive the class defined by the parent.

~~~text
child.loadClass("com.acme.api.Task")
               |
               v
       child asks parent
               |
               v
      parent defines Task
               |
               v
  child returns the exact Class<?> of Task
~~~

In the diagram, child is the initiating loader while parent is the defining loader. If both child loaders delegate to the same parent that defined `Task`, **there is only one Task type**. If the parent does not see `Task` and each child defines it on its own, they have two different identities.

A custom loader may use child-first loading to isolate dependencies, while still keeping shared API contracts via a parent/shared loader mechanism. Merely comparing `loaderA.getParent() == loaderB.getParent()` **is not enough** to conclude that two types are shared.

`Thread.currentThread().getContextClassLoader()` (TCCL) is used by some frameworks and `ServiceLoader` to locate providers. Changing the TCCL **does not change the identity** of a Class that has already been defined. It only affects the class lookup path if the API/framework actually uses the context loader.

## 6. Common Places Where This Error Occurs

### 6.1. Plugin Packages Its Own Copy of the Host's API Interface

~~~text
Host class loader:
  com/acme/api/Processor.class      ← original contract

Plugin class loader:
  com/acme/api/Processor.class      ← separate API copy
  com/acme/plugin/ProcessorImpl.class
~~~

`ProcessorImpl` implements `Processor` from the plugin loader. The host casts the object to `Processor` from the host loader and encounters an incompatibility. **Fix:** The host or a parent/shared loader defines exactly **one** `Processor`; the plugin only defines the implementation and uses that same shared interface.

### 6.2. Application Server Hot Redeploy

A container may create a new class loader upon redeployment. Old threads, callbacks, listeners, caches, or singletons hold objects created by the old loader and then pass them into the new code:

~~~text
Old deploy → LoaderOld → com.app.User → old object
New deploy → LoaderNew → com.app.User → new type
                         |
               cast old object to new type
                         |
                 ClassCastException
~~~

You need to clean up the lifecycle of threads/caches/listeners/callbacks on undeploy, and avoid retaining objects belonging to the old class loader across deployment boundaries. Closing the loader does not guarantee that old objects disappear immediately.

### 6.3. Duplicate Libraries via Dependency/Shading

The host and plugin may both package an `api.jar`, or the same model class may be shipped in multiple JARs. Having two JARs on disk **does not necessarily cause an error**; the error happens when two defining loaders actually create two different classes and the code passes an object across the boundary. Shading/relocation may be appropriate for internal dependencies, but **should not create two copies of an API contract** that the host and plugin must share.

### 6.4. Reflection, SPI, and Proxies

`Class.forName(..., loader)`, `ServiceLoader`, proxy factories, and discovery frameworks select a loader based on configuration or the TCCL. A provider may implement an interface defined by a different loader than the consumer; succeeding via reflection does not guarantee a cast to the consumer's interface. Inspect the actual loaders used to load the **contract**, provider, and proxy.

## 7. Diagnosing With the Actual Class<?>

The following fragment assumes `value` is a non-null object and `targetType` is the receiver's target `Class<?>`:

~~~java
Class<?> actualType = value.getClass();

System.out.println("Actual name: " + actualType.getName());
System.out.println("Target name: " + targetType.getName());
System.out.println("Same Class: " + (actualType == targetType));

System.out.println("Actual loader: " + actualType.getClassLoader());
System.out.println("Target loader: " + targetType.getClassLoader());

System.out.println("Actual module: " + actualType.getModule());
System.out.println("Target module: " + targetType.getModule());

System.out.println("Compatible: " + targetType.isInstance(value));
System.out.println("Assignable: "
        + targetType.isAssignableFrom(actualType));
~~~

**Do not draw conclusions solely from `actualType == targetType`**: the object may be a subclass or an implementation of the target interface, so two Class instances can differ while the cast is still valid. `isInstance(value)` reflects compatibility with the target type; `isAssignableFrom(actualType)` is also useful for checking type relationships.

You can format a temporary loader ID in logs:

~~~java
ClassLoader loader = actualType.getClassLoader();
String id = loader == null ? "bootstrap"
        : loader.getClass().getName() + "@"
                + Integer.toHexString(System.identityHashCode(loader));
System.out.println(id);
~~~

This snippet is a fragment that depends on the `actualType` variable. `identityHashCode` is convenient for logging, though collisions are possible; compare loader references with `==` to conclude whether they are the same loader object.

Try inspecting the class origin via `ProtectionDomain` and `CodeSource`:

~~~java
var domain = actualType.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();
System.out.println(source == null
        ? "(unknown)"
        : source.getLocation());
~~~

Not every class has a useful `CodeSource`: bootstrap classes, classes generated in memory, or special loaders might not provide one. **Having the same CodeSource does not guarantee the same identity**.

### Troubleshooting Procedure

1. Preserve the full stack trace and obtain the exact `Class<?>` of both the source object and the target type.
2. Print `getName()`, `getClassLoader()`, `getModule()`, `isInstance(...)`, and check equality with `==`.
3. Find where the object is created: factory, constructor, reflection, proxy, deserialization, or plugin callback.
4. Check for duplicate API JARs, parent-first/child-first loading strategies, dependency trees, and module layers.
5. If the error only happens after a redeploy, inspect caches, threads, and callbacks that still hold onto the old loader/object.
6. Consolidate the **API contract under a single shared defining loader**, or transfer data across a neutral boundary.

## 8. Solutions and Anti-Patterns

| Scenario | Solution |
| --- | --- |
| Host cannot cast plugin to interface | Define the API interface in the parent/shared loader; the plugin must not redefine it. |
| Two plugins exchange internal models | Share a DTO/interface contract or serialize into a neutral format. |
| Two versions of a library must coexist | Keep implementations in separate loaders and share only the necessary contract. |
| Error after redeploy | Tear down caches/threads/listeners/callbacks holding objects/loaders from the previous deployment. |
| Framework loads provider with the wrong loader | Configure discovery/TCCL/loader consistently with the shared contract. |
| Duplicate dependency classes | Align packaging and verify the defining loader at runtime. |

Do not simply suppress unchecked-cast warnings, re-cast, compare names with `getName()`, overuse reflection, change the TCCL after the object has already been created, or push entire libraries into the bootstrap/system loader. **These approaches do not unify the identity of two class definitions**.

If direct casting across a boundary is required, both sides must reference **the same compatible interface/base class definition**. If complete isolation is required, pass neutral data and reconstruct a valid object on the receiving side instead of forcing an implementation object from domain A into a class of domain B.

## 9. Common Misconceptions

**If two loaders have the same parent, are they guaranteed to load the same type?** False. The parent must actually provide the class; otherwise, each child may define it independently.

**Does the JVM merge classes if their bytecode is identical?** False. The defining loader is a mandatory part of identity.

**Are interfaces immune to this error?** False. A `Task` interface defined by two loaders results in two distinct types; an implementation of one copy does not automatically implement the other.

**Do generics prevent this in all cases?** No. Type erasure can allow a `List` to cross the boundary, and the error only surfaces when retrieving an element and casting it to the receiver's `Payload` model.

**Does closing a URLClassLoader immediately unload its classes?** No. `close()` closes the loader's resources; class metadata and objects can still be retained by stacks, threads, caches, or other references, depending on unloading/GC conditions.

**Is ClassCastException the same as NoClassDefFoundError or LinkageError?** No. `ClassCastException` occurs on an invalid runtime cast; `NoClassDefFoundError` typically relates to the JVM being unable to obtain a required class definition, whereas `LinkageError` is the family of errors thrown during definition/linking. A single loader misconfiguration can manifest as different errors at different phases.

## 10. Self-Check Questions

**Question 1.** Two loaders A and B read the same `Message.class` and both define `pkg.Message` themselves. `classA.getName().equals(classB.getName())` evaluates to `true`. What is `classA == classB`?

**Answer:** `false`, because their defining loaders are different.

**Question 2.** Two child loaders both delegate loading `api.Task` to a parent that already defined `Task`. Are there two types?

**Answer:** No. Both receive the same `Class<?>` defined by the parent.

**Question 3.** Why should you use `targetType.isInstance(value)` instead of only comparing names?

**Answer:** Because it checks whether the object is compatible with the target type according to actual superclass/interface relationships.

**Question 4.** The host has an interface `Task`; the plugin brings its own `Task` with the same name. How do you fix this?

**Answer:** Keep only one definition of the API contract in a shared loader so the plugin's implementation implements the exact `Task` from the host/parent.

**Question 5.** Why does the error appear after a redeploy even though the Java source did not change?

**Answer:** The new loader may define a different type; old objects retained in a cache still belong to the old loader's type and therefore cannot be cast to the new type.

## Key Takeaways

**Having the same class name does not guarantee a cast will succeed.** For a class/interface, the JVM uses **(binary name, defining loader)** as its identity. When encountering “A cannot be cast to A”, inspect the two actual `Class<?>` objects, `getClassLoader()`, `isInstance(...)`, and the path the object took; then share the **API contract from a common loader** or exchange neutral data.

**Authoritative references:**

- *Java Virtual Machine Specification*, Java SE 17 `5.3` — https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Language Specification*, Java SE 17 `12.2` — https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- Java SE 17 API, `ClassLoader` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Class` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
