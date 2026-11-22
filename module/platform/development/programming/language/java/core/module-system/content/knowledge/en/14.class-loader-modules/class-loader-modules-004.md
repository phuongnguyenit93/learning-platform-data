# Class Identity Across Different Loaders

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why two classes with **the same fully qualified name and the same bytecode** can still be two different types in the JVM.
- Distinguish **binary name**, **defining class loader**, and **initiating class loader**.
- Reproduce a failed cast scenario across class loaders using Java 21.
- Recognize impacts on data types, static variables, reflection, SPI, modules, and plugin reloading mechanisms.
- Diagnose class loader errors using evidence from objects and the runtime environment.

## 2. How Does the JVM Determine Class Identity?

In a JVM, the identity of an ordinary class is determined by the pair:

> **Class identity = (binary name, defining class loader)**

**Binary name** is the binary name of the class, such as **com.example.Plugin**. **Defining class loader** is the loader that actually defined that class into the JVM. Note: this is the identity relationship for a class defined at runtime; file names, JAR names, or bytecode contents cannot substitute for the loader's identity.

Suppose two independent loaders **L1** and **L2** both define a class with binary name **com.example.Plugin** from an identical set of bytecode:

| Property | Class defined by L1 | Class defined by L2 |
|---|---|---|
| Binary name | com.example.Plugin | com.example.Plugin |
| Bytecode | May be completely identical | May be completely identical |
| Defining loader | L1 | L2 |
| Class object | C1 | C2 |
| JVM identity | (com.example.Plugin, L1) | (com.example.Plugin, L2) |

Conclusion: **C1 differs from C2**, so an object created from C1 is not automatically an instance of C2. Two classes with the same name can have independent sets of static state and lifecycles.

In Java, **Class#getName()** checks the name; **the == operator on two Class objects** is what checks whether they represent the exact same class at runtime.

### Defining Loader and Initiating Loader

- **Defining loader**: the loader that invoked the class-definition mechanism (typically via ClassLoader#defineClass, or the JVM's equivalent mechanism). Class identity is bound to this loader.
- **Initiating loader**: the loader that was asked to initiate loading the class. It may return a class defined by a parent loader or another loader via delegation.
- **Class#getClassLoader()** returns the defining loader; a class from the bootstrap loader may return **null**.

For example: a child loader requests to load **java.lang.String**, then delegates to the bootstrap loader. The child loader participates in the load request, but it does not become the defining loader of String. Therefore, you cannot infer that "two load requests coming from two loaders" always create two separate classes.

## 3. Loader Delegation Determines Whether Classes Are Duplicated

The common mechanism of **ClassLoader#loadClass** is **parent-first delegation**:

1. Check whether the class has already been loaded/requested previously.
2. Ask the parent loader whether it can load this class.
3. If the parent cannot find it, the current loader searches for and defines it itself (typically in **findClass**).

As a result, multiple child loaders can share a single class defined by the parent loader. When both L1 and L2 successfully delegate to the same class in the parent, the result is **C1 == C2**.

Conversely, if each loader can define its own copy of the class (for example, two isolated plugins, each with its own loading path and the parent loader does not see that class), they will have two different identities. Some plugin systems use a selective **child-first** strategy to prioritize classes inside the plugin. This approach increases isolation, but shared API classes must be controlled.

**Distinguish three commonly confused things:**

- Same class name: only tells you the name; not enough to determine the same type.
- Same path/JAR or same bytecode: only tells you the code source; not enough to determine the same type.
- Same Class object: confirms the same runtime class; type checks rely on this exact identity.

## 4. Hands-On: Same Name and Bytecode, Different Class Identity

The following example runs with **JDK 21** (also applicable from Java 9 onward). We use two **URLClassLoader** instances, both reading the **out** directory, while each loader is allowed to define **demo.Greeter** on its own. We use the **platform class loader** as the parent so that the demo class is not unintentionally loaded and shared by the application loader.

Directory structure before compiling:

~~~text
class-identity-demo/
├── demo/
│   └── Greeter.java
└── IdentityDemo.java
~~~

Create **demo/Greeter.java**:

~~~java
package demo;

public final class Greeter {
    public static int count = 0;

    public String greet() {
        return "Hello from Greeter";
    }
}
~~~

Create **IdentityDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        URL classesDirectory = Path.of("out").toUri().toURL();

        // The platform loader does not load demo.Greeter on the application classpath.
        ClassLoader sharedParent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loader1 =
                     new URLClassLoader(new URL[] {classesDirectory}, sharedParent);
             URLClassLoader loader2 =
                     new URLClassLoader(new URL[] {classesDirectory}, sharedParent)) {

            Class<?> class1 = Class.forName("demo.Greeter", true, loader1);
            Class<?> class2 = Class.forName("demo.Greeter", true, loader2);

            System.out.println("Same name: "
                    + class1.getName().equals(class2.getName()));
            System.out.println("Same Class object: " + (class1 == class2));
            System.out.println("class1 defined by loader1: "
                    + (class1.getClassLoader() == loader1));
            System.out.println("class2 defined by loader2: "
                    + (class2.getClassLoader() == loader2));

            Object fromLoader1 = class1.getDeclaredConstructor().newInstance();
            System.out.println("class1.isInstance: "
                    + class1.isInstance(fromLoader1));
            System.out.println("class2.isInstance: "
                    + class2.isInstance(fromLoader1));

            try {
                class2.cast(fromLoader1);
            } catch (ClassCastException expected) {
                System.out.println("Cast failed: "
                        + expected.getClass().getSimpleName());
            }

            class1.getField("count").setInt(null, 7);
            System.out.println("Static count of class1: "
                    + class1.getField("count").getInt(null));
            System.out.println("Static count of class2: "
                    + class2.getField("count").getInt(null));
        }
    }
}
~~~

In the **class-identity-demo** directory, run:

~~~bash
mkdir out
javac -encoding UTF-8 -d out demo/Greeter.java IdentityDemo.java
java -cp out IdentityDemo
~~~

Expected output:

~~~text
Same name: true
Same Class object: false
class1 defined by loader1: true
class2 defined by loader2: true
class1.isInstance: true
class2.isInstance: false
Cast failed: ClassCastException
Static count of class1: 7
Static count of class2: 0
~~~

### Step-by-Step Explanation

1. **Class.forName** with loader1 and loader2 requests loading the same binary name. Both loaders see the same **out/demo/Greeter.class** file.
2. The chosen parent loader does not load the demo class; therefore, each URLClassLoader defines a class on its own. The result has the same name, yet **class1 != class2**.
3. Object **fromLoader1** belongs to class1. **class2.isInstance(fromLoader1)** returns false, and **class2.cast(fromLoader1)** throws **ClassCastException**.
4. The **static count** field is owned by each defined class individually. Setting the value to 7 on class1 does not change class2's count. This also applies to static initializers and many static caches.

**Key takeaway of the experiment:** changing only the loader while still using the same compiled file is enough to produce two different types. Closing URLClassLoader with **close()** only releases associated resources; it does not guarantee that the JVM immediately unloads the classes from memory.

### Experimenting with Changes to Verify the Role of Delegation

If you give both URLClassLoader instances the application class loader as their parent, and **demo.Greeter** is on the application classpath, the usual parent-first mechanism will return the shared class from the parent. In that case **class1 == class2** can be true, **getClassLoader()** points to the application loader, and static state is shared. The outcome depends on which exact loader actually defines the class, not on how many URLClassLoader objects were created.

## 5. Consequences When Classes Have Different Identities

### 5.1. ClassCastException and Type Checking

When code in plugin A passes a **com.example.Message** object to a place expecting **com.example.Message** defined by plugin B, the names in the error message may look identical, yet the JVM treats them as two different types.

- Direct casting, **Class#cast**, and **Class#isInstance** all rely on runtime type relationships.
- **isAssignableFrom** also checks actual identity and inheritance/interface relationships; it does not compare name strings.
- In modern Java, ClassCastException messages often include loader/module details that help distinguish the two sides. Use those details when diagnosing.

For example, if both loaders define **api.Task**, a plugin implementing loader A's **api.Task** will not be treated by the JVM as implementing loader B's **api.Task** even though the interface names are identical.

### 5.2. Static Variables, Singletons, and Class Initialization

Each separately defined class has its own set of static fields and its own class initialization process. A singleton stored in a static field of a class is not automatically a JVM-wide singleton if that class has multiple definitions from multiple loaders. Logger registries, caches, or static counters can split in the same way.

Do not rely on static fields in a plugin to hold state that must be shared across loaders. Place shared state in a service/interface with a clearly defined lifecycle and loader.

### 5.3. Reflection and Linkage Errors

Reflection can retrieve a method name and instantiate an object successfully yet still fail when passing an object whose parameter type has the wrong identity. When loaders must resolve a type appearing in a method signature, the JVM may apply **loading constraints** to force the parties to agree on the referenced class. Violating a constraint can produce **LinkageError**, sometimes accompanied by a **loader constraint violation** message.

**Do not conflate the errors:**

| Symptom | Common meaning | How to verify |
|---|---|---|
| ClassCastException | The object does not belong to the target type at runtime | Print the name and defining loader of both Class objects |
| LinkageError / loader constraint violation | Conflict when linking class definitions across loaders | Check signatures, shared APIs, and delegation paths |
| ClassNotFoundException | The queried loader cannot find the requested binary name | Check classpath/module path and the loader used |
| NoClassDefFoundError | The JVM cannot complete using a required class, e.g., missing dependency or earlier initialization failure | Inspect the root cause in the stack trace |

The errors above may relate to the same misconfigured loader setup, but not every case is "two classes with the same name."

## 6. Designing a Shared API for a Plugin System

Suppose the host application defines an API:

~~~java
package api;

public interface Task {
    String execute();
}
~~~

A plugin should only define **plugin.impl.TaskImpl** itself and reference **api.Task** defined by the shared loader.

~~~java
package plugin.impl;

import api.Task;

public final class TaskImpl implements Task {
    @Override
    public String execute() {
        return "Done";
    }
}
~~~

Desired loader model:

~~~text
Application / shared API loader
    └── defines api.Task
         ├── Plugin loader A
         │    └── defines plugin.a.TaskImpl
         └── Plugin loader B
              └── defines plugin.b.TaskImpl
~~~

Because both plugin loaders delegate **api.Task** to the same upper-level loader, implementations can be used through the shared interface while still isolating each plugin's internal classes.

If plugin A loads a different copy of **api.Task** on its own and plugin B/application uses the other copy, checking **api.Task.class.isAssignableFrom(pluginClass)** may fail or linkage errors may occur. Therefore:

- Place **interfaces, DTOs, exceptions, and types appearing in communication contracts** into a shared API defined by one specific loader.
- Have plugin loaders **delegate the shared API packages**. Only isolate implementation packages that truly need to be independent.
- Pass objects through shared interfaces or neutral data (such as JSON/byte arrays with a clear schema) when implementations are intentionally kept separate.
- When using **ServiceLoader**, specify the loader explicitly, e.g. **ServiceLoader.load(Task.class, pluginLoader)**; the provider must be compatible with the exact **Task.class** used by the caller. The **Thread context class loader (TCCL)** also affects many frameworks when they look up providers or resources.

**Note:** simply putting the same interface name into both JARs is not enough. The API needs **the same Class identity** at runtime.

## 7. Relationship to Packages and the Java Platform Module System (JPMS)

Since Java 9, the module system adds access boundaries and module metadata. However, modules with the same name or packages with identical names do not turn two classes defined by two different loaders into a single class.

Distinguish:

- **Binary name**: the binary name, such as **demo.Greeter**.
- **Runtime class identity**: binary name combined with defining loader.
- **Runtime package**: a package identified by package name and defining loader; therefore, two classes in the same lexical package name but defined by two different loaders do not automatically have package-private access to each other.
- **Module**: the scope containing classes with its own readability/exports/opens rules; **Class#getModule()** indicates the class's module. Classpath classes typically belong to the unnamed module of the corresponding loader.

Two different loaders can create two different unnamed modules. You must distinguish a **module access error** (access permissions between modules) from a **type identity error** (types with different identities). Both can appear in the same system, but their fixes are different.

## 8. Diagnosing at Runtime

When you see two types with the same name in a stack trace, record the following evidence at both the object creation site and the cast site:

~~~java
static void inspect(Object value) {
    Class<?> type = value.getClass();
    ClassLoader loader = type.getClassLoader();

    System.out.println("Class name: " + type.getName());
    System.out.println("Class object: " + type);
    System.out.println("Defining loader: " + loader);
    System.out.println("Loader identity: "
            + (loader == null ? "bootstrap" : System.identityHashCode(loader)));
    System.out.println("Module: " + type.getModule());
}
~~~

Then compare **sourceClass == targetClass**, **targetClass.isInstance(value)**, and if needed **sourceClass.getClassLoader() == targetClass.getClassLoader()** directly. Do not rely solely on **loader.toString()** or hash codes as absolute proof, as they are only for identification in logs; reference comparison is the actual identity check.

In real applications, continue checking:

1. The parent loader of each loader and the parent-first/child-first mode.
2. Duplicate copies of dependencies/APIs in the application classpath, module path, plugin JARs, or fat JARs.
3. Which loader the framework uses to locate classes/resources, especially TCCL and ServiceLoader.
4. Objects, threads, caches, or callbacks still holding references to old loaders after reloading.
5. Full stack traces of ClassCastException or LinkageError, especially loader/module details.

## 9. Class Identity in Hot Reload and Long-Lived Applications

Containers, application servers, plugin engines, and hot-reload systems often create a new class loader for a new version. This allows loading the new version's classes without reusing the old class identity. Two versions can coexist in the JVM; an old object cannot implicitly be cast to the new class even though it keeps the same package and class name.

For the old version to become eligible for unloading, the application must stop using the objects, Class instances, loader, and related references (including threads, ThreadLocals, listeners, registries, or static caches). **Garbage collection and class unloading do not happen immediately on demand**, so you should not conclude there is a memory leak merely from seeing a class loader briefly remain.

In practice, design a stable API in a shared loader, manage resource/plugin lifecycles explicitly, and transfer data between versions in a format not tied to implementation classes of the old loader.

## 10. Knowledge Self-Check

**Scenario A:** L1 and L2 both ask their parent loader to load **api.Task**, and the parent returns the same Class. Despite having two child loaders, what is the result of **L1.loadClass("api.Task") == L2.loadClass("api.Task")**?

**Answer:** true, when both calls receive the exact same class defined by the parent.

**Scenario B:** Two separate URLClassLoaders read the same **plugin.Widget.class** file, and each loader defines the class itself. The two Class objects have the same **getName()**. Is calling **classB.cast(instanceOfA)** valid?

**Answer:** No. An instance of the class defined by loader A is not automatically an instance of the class defined by loader B; the cast will throw ClassCastException.

**Scenario C:** An application reloads a plugin with a new loader, yet a static singleton in the old loader still holds its value. Is the JVM violating the singleton rule?

**Answer:** No. A static singleton is tied to a specific defined class. The old loader and new loader have separate class identities and separate static state.

## 11. Key Takeaways

- **Class name + defining loader** is the basis for identifying a class in the JVM.
- Same bytecode, same JAR file, or same binary name **does not guarantee** the same Class identity.
- Parent-first delegation can let child loaders share a single class definition; isolated loaders can create separate definitions.
- Loader boundaries directly affect casts, reflection, API/plugin contracts, static state, module/package access, and hot reload.
- When encountering errors, compare the **actual Class objects and defining loaders** on both sides before editing the classpath or changing how classes are loaded.

**Foundational references:** Java Virtual Machine Specification, Chapter 5 (Loading, Linking, and Initializing); Java SE APIs for **java.lang.Class**, **java.lang.ClassLoader**, **java.net.URLClassLoader**, and **java.util.ServiceLoader**.
