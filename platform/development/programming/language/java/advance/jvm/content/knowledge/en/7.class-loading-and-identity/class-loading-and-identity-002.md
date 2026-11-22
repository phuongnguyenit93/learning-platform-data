# Bootstrap, platform, application class loaders and the delegation mechanism

## 1. Learning objectives

A Java program can use thousands of classes, but they are not necessarily found and defined by the same component. The JVM uses **class loaders** to create classes from binary representations, resolve references, and organize namespaces. Since Java 9, the built-in class loader system is commonly explained through three components: **bootstrap**, **platform**, and **application/system**.

After this lesson, you can:

- Distinguish the responsibilities of the three built-in loaders, how to obtain them via the Java API, and the role of the classpath/module path.
- Read accurately the standard **parent-first** delegation algorithm, and the methods **loadClass**, **findLoadedClass**, **findClass**, **defineClass**, and **resolveClass**.
- Understand **defining loader** versus **initiating loader**, and class identity based on binary name **and** defining loader.
- Explain why **String.class.getClassLoader()** is typically **null**, yet **null** does not mean there is no class.
- Distinguish **loading**, **linking** (verification, preparation, resolution), and **initialization**.
- Recognize cases involving custom loaders, context class loaders, Java modules, ServiceLoader, multiple dependency versions, and common errors.
- Practice with Java 17+ to observe loaders, demonstrate that two classes with the same binary name are still different types when they have two defining loaders, and distinguish class loading from class initialization.

Scope: foundational rules of Java SE 17+ and the JVM model; details such as loader implementation class names, paths, and diagnostic output may differ across JDKs.

## 2. What does a class loader do?

A **class loader** is the mechanism that delivers class/interface definitions to the JVM. For an ordinary class, a loader can obtain the class bytes from the classpath, module path, JAR, network, memory, or an application-provided source, and then use the JVM mechanism to define the class.

Distinguish:

- **Finding class bytes:** locating where the data resides, for example the entry **com/example/Order.class** in a JAR.
- **Defining a class (define):** the JVM creates a runtime class from valid class data, associating the class's identity with a **defining loader**.
- **Loading a class (load):** a load request can be satisfied by one loader delegating to another loader; the loader receiving the request is not necessarily the loader that directly defines it.
- **Linking (link):** performing verification, preparation, and reference resolution according to JVM rules.
- **Initializing (initialize):** running class initialization work, such as static field initializers and static initializer blocks, at the time specified by Java.

Therefore, the statement "the loader has found the class" does not automatically mean **the static initializer has run** or that all references of the class have been resolved.

A **Class<?>** is an object representing a type at runtime; **Class.getClassLoader()** provides the loader that defined that ordinary class. For array classes and primitives, the API has specific rules that will be covered below.

## 3. Three built-in loaders in modern Java

A general model for JDK 17 with the default loader system:

~~~text
                    JVM / Java runtime
                          |
                          v
                  Bootstrap loader
                          ^
                          | delegation
                  Platform loader
                          ^
                          | delegation
             Application / System loader
                          ^
                          | delegation
          Application-specific custom class loader
~~~

The arrows represent the **typical delegation path from child loader up to parent**. This is a mental model, not a claim that every Java modules lookup always follows a rigid tree or that every custom loader uses parent-first.

| Loader | General responsibility | API / observable information |
| --- | --- | --- |
| **Bootstrap** | Loads/defines core classes provided by the VM/runtime, such as the core of **java.base** | Built-in loader in the JVM; with **Class.getClassLoader()**, a bootstrap-defined class typically returns **null** |
| **Platform** | Loads many Java SE, JDK platform classes/modules, and runtime components as assigned by the JDK | **ClassLoader.getPlatformClassLoader()** |
| **Application / System** | System loader used for the application on the application classpath, application module path, and appropriate scopes | **ClassLoader.getSystemClassLoader()**; typically the loader of the main class in a standard classpath launch |

Before Java 9, many resources used the term **extension class loader**. Since Java 9, the old extension mechanism changed and **platform class loader** is the appropriate concept for JDK 17+. Do not design Java 17 programs relying on the **jre/lib/ext** directory as a current mechanism.

### 3.1. Bootstrap class loader

Bootstrap is a foundational component provided by the JVM and is not required to exist as a normal Java **ClassLoader** object. When querying:

~~~java
String.class.getClassLoader()
~~~

the result on a standard Java SE JVM is **null**, meaning the **String** class is defined by bootstrap.

This **does not mean the String class has no class loader**; its defining loader is bootstrap according to the JVM mechanism. The **null** value is a convention in the Java API for the bootstrap loader in corresponding cases.

Bootstrap has no parent. Essential classes such as **java.lang.Object** and **java.lang.String** are typically defined by bootstrap. You should not claim that every class starting with **java.** is defined by bootstrap: many kinds of platform classes are assigned to other loaders.

### 3.2. Platform class loader

The platform loader is responsible for many Java/JDK platform classes not belonging to the set defined by bootstrap. Java provides:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
~~~

You can use the platform loader as the parent of a custom class loader when you only want the custom loader to inherit visibility of platform classes without implicitly seeing application classes.

**Important exception to the tree diagram:** since Java 9, the module system affects class visibility. The Java 17 ClassLoader documentation explicitly notes that the platform loader **may have to delegate to other loaders, such as the application loader**, to handle upgraded/overridden modules that corresponding modules have a reads relationship with. Therefore, you should not claim that "the platform loader can never see classes of the application loader under any circumstances."

### 3.3. Application/system class loader

The application loader is also called the **system class loader**:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

In a typical launch:

~~~bash
java -cp out com.example.Main
~~~

the main class in **out** is usually defined by the default system loader. This loader sees application classes according to the classpath/module configuration and can delegate to use platform classes.

In modern JDKs, the implementation class of the system loader is an internal detail. **Do not cast the system loader to URLClassLoader** and do not assume it always has an **addURL** method or a classpath URL structure like JDK 8. If Java is launched with a custom system loader configuration, some environment-dependent comparisons may differ.

**Inheritance path:** according to the API, the platform loader is the **parent or ancestor** of the system loader. In the default setup it is usually the direct parent; custom system class loaders may add intermediate layers.

## 4. Parent is not a Java class inheritance relationship

In:

~~~java
ClassLoader child = new ClassLoader(parent) {};
~~~

**parent** is the loader to **delegate class lookup to**. It does not mean child has an **extends parent.getClass()** relationship or that child automatically copies all classes already defined by parent.

Three relationships must be distinguished:

| Relationship | Question |
| --- | --- |
| **ClassLoader parent** | When this loader is asked for a class, which loader can it ask first? |
| **Class extends/interface implements** | Which type does a Java type inherit from / implement? |
| **Module reads/exports/opens** | Which packages/classes is a module allowed to reference/access? |

The three relationships interact but do not substitute for one another. Parent delegation does not automatically grant reflective access to a package encapsulated by a module; a class loading successfully also does not make all of its members accessible.

## 5. The standard parent-first delegation algorithm

The default implementation of **ClassLoader.loadClass(String, boolean)**, when not overridden, operates in the spirit of:

~~~text
loadClass(binaryName, resolve)
    |
    v
1. findLoadedClass(binaryName)
   Already recorded by this loader as loaded? -> reuse it
    |
    v not found yet
2. Ask parent.loadClass(binaryName)
   If parent == null: try the JVM's bootstrap loader
    |
    +-- succeeded -> use the class provided by parent/bootstrap
    |
    v not found
3. Call this loader's own findClass(binaryName)
    |
    +-- found bytes / defined class -> return Class
    |
    v not found
4. Throw ClassNotFoundException
    |
    v if class was found
5. If resolve=true: resolveClass(theClass)
6. Return Class<?>
~~~

Key points to remember:

- **findLoadedClass** is used to avoid defining the same class twice in the same loader.
- **Parent-first** means asking the parent first before calling the child's **findClass**. It helps ensure core Java classes and shared dependencies are shared consistently.
- **findClass** is the appropriate hook when writing a custom loader while keeping the default delegation mechanism.
- **defineClass(name, bytes, off, len)** actually submits the new definition to the JVM, if the data is valid.
- **resolveClass** is related to the linking step; it **does not mean initializing static fields**.
- **ClassNotFoundException** is the result when a class load request by name cannot find a matching definition; linkage errors can occur at other stages.

The algorithm above is the default implementation of **ClassLoader**, not a mandatory contract that every custom loader must use in the exact same order. A loader can override **loadClass** to use **child-first** or module-specific mechanisms, but it must respect JVM constraints on class identity, types, permissions, and consistency.

### 5.1. Example of parent-first avoiding a duplicate core class

Suppose the application loader is asked for **java.lang.String**:

~~~text
Application loader -> Platform loader -> Bootstrap loader
                                     -> defines java.lang.String
                 <- returns the same Class
        <- returns the same Class
~~~

Child loaders **can initiate loading** via delegation; the runtime class is defined by bootstrap. By default, the application loader does not create an arbitrary copy of **java.lang.String**.

Custom loaders should not attempt to define classes in **java.*** using **defineClass**; the Java API places security restrictions on this package name, in addition to conditions on modules, packages, and class files.

### 5.2. Sample pattern overriding findClass

The following code only illustrates the structure of **findClass**; it is not a standalone program because the byte-reading part is not provided:

~~~java
class ResourceClassLoader extends ClassLoader {
    ResourceClassLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String binaryName)
            throws ClassNotFoundException {
        byte[] bytes = readClassBytes(binaryName);
        if (bytes == null) {
            throw new ClassNotFoundException(binaryName);
        }
        return defineClass(binaryName, bytes, 0, bytes.length);
    }

    private byte[] readClassBytes(String binaryName) {
        // Mechanism for retrieving class bytes from a custom source would be implemented here.
        return null;
    }
}
~~~

Because this sample returns null, it **cannot actually load a new class yet**; it only shows where to implement the logic. The runnable example in section 9 will perform definition from a complete byte array without needing an external data-loading mechanism.

Note that **binaryName** in the **loadClass/findClass** API typically has the form **com.example.MyType**, not **com/example/MyType**. When looking up an entry in a JAR, the loader itself converts it to a path **com/example/MyType.class** if its source mechanism requires it.

## 6. Defining loader, initiating loader, and class identity

When loader A receives a request to load **com.example.Service** and successfully delegates to loader B, use the exact terms:

- **B is the defining loader** if B actually defines the class from bytes.
- **A is an initiating loader** in the loading process recorded by the JVM, even though A did not directly define it.
- That runtime class has an **identity tied to its binary name and defining loader**.

Conceptually, a runtime class/interface is identified by the pair:

~~~text
(binary name, defining loader)
~~~

Consequently, two **plugin.Task** classes directly defined by two different loaders are **two different runtime types**, even though they have:

- the same binary name **plugin.Task**;
- the same class bytes;
- the same method signatures;
- the same superclass **java.lang.Object**.

For these two types:

~~~text
("plugin.Task", LoaderA) != ("plugin.Task", LoaderB)
~~~

The **Class<?>** objects are not equal; an instance of the class from LoaderA cannot automatically be cast to the type from LoaderB. Problems such as plugin isolation, application server redeployment, and multiple library versions require understanding this property properly.

### 6.1. What happens when child loaders only delegate?

If both **LoaderA** and **LoaderB** are parent-first to the same parent that defined **shared.Api**, the two requests can return **the same Class object** of **shared.Api**. **LoaderA != LoaderB** does not force the resulting classes to be different: you must check **who actually defined the class**.

### 6.2. Runtime package also considers the loader

It is not enough for two classes to have the same package string **com.example**. The JVM determines the runtime package based on **package name and defining loader** (along with relevant module rules). Two classes with the same package name but from different defining loaders **do not automatically have package-private access** to each other.

This explains confusing IllegalAccessError failures when a bytecode-generated class has the same package string as the original class but is defined by a different loader.

### 6.3. Loading constraints when communicating across loaders

Methods/fields whose descriptors reference types defined by different loaders may be subject to **loading constraints** to ensure type safety during linking. You cannot simply create two classes with the same binary name and expect the system to treat them as one type when passing objects across loader boundaries.

Practical solutions include: placing shared APIs in a parent loader, passing data through stable formats, or using an interface where both sides see the **same Class object** of that interface.

## 7. Distinguishing loading, linking, and initialization

Abbreviated lifecycle diagram:

~~~text
Source of class bytes
      |
      v
Loading / define class
      |
      v
Linking
  +--> Verification: class file/bytecode and type constraints
  +--> Preparation: prepares static fields with appropriate default values
  +--> Resolution: resolves symbolic references (may be lazy)
      |
      v
Initialization
  +--> static initializers and static field initializers of the class
      |
      v
Class is ready for uses that require initialization
~~~

Preparation and resolution have ordering rules and can happen incrementally. **Resolution** is not necessarily performed all at once for all references immediately when loadClass is called. Do not equate linking with running an object constructor.

Examples of actions that often have different effects:

| Action | Does it force immediate initialization of the target class? |
| --- | --- |
| **loader.loadClass("demo.Widget")** | Typically **no**; by default equivalent to loadClass(name, false) |
| **Class.forName("demo.Widget", false, loader)** | **Does not request initialization** |
| **Class.forName("demo.Widget")** | Requests load/link and **initialize** per the one-parameter overload contract |
| **Class.forName("demo.Widget", true, loader)** | Requests initialization |
| **new Widget()** | Is an active use, requiring the class to be initialized per rules |
| Accessing a static field/method other than the constant variables exception | Can trigger initialization per JLS/JVMS rules |
| Referencing **Widget.class** | Does not itself initialize Widget merely by obtaining the class literal |

Do not treat **Class.forName** as a "name-check-only" API while forgetting the **initialize** parameter. Initialization can execute static code with side effects and errors.

## 8. Runnable example 1: observing the three loaders

Create the file **LoaderBasics.java**:

~~~java
public class LoaderBasics {
    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader app = LoaderBasics.class.getClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        System.out.println("mainIsSystem=" + (app == system));
        System.out.println("platformIsDifferent=" + (platform != system));
        System.out.println("stringBootstrap="
                + (String.class.getClassLoader() == null));
        System.out.println("primitiveArrayBootstrap="
                + (int[].class.getClassLoader() == null));
        System.out.println("ownArrayUsesApp="
                + (LoaderBasics[].class.getClassLoader() == app));
        System.out.println("forNameIsString="
                + (Class.forName("java.lang.String", false, app)
                        == String.class));
    }
}
~~~

With JDK 17 and the default system loader, run in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 LoaderBasics.java
java -cp . LoaderBasics
~~~

**Stdout in a typical Java 17 environment using the default system loader:**

~~~text
mainIsSystem=true
platformIsDifferent=true
stringBootstrap=true
primitiveArrayBootstrap=true
ownArrayUsesApp=true
forNameIsString=true
~~~

Interpretation:

1. The main class on the application classpath is defined by the default system loader.
2. The platform loader is a distinct component from the system loader.
3. **String** is a core class defined by bootstrap and its loader is represented as null.
4. **int[]** is created by the JVM for the primitive array, so **getClassLoader()** also returns null.
5. An array class whose component reference type is defined by the app loader has the loader corresponding to the component.
6. **Class.forName** is asked to find String through the app loader; thanks to delegation it receives the exact same Class object **String.class** provided by bootstrap.

If run inside an application server or a custom system loader configuration, the **mainIsSystem** line may differ. This exercise assumes the exact command **java -cp . LoaderBasics** without a custom launcher.

### 8.1. Why do arrays also need special rules?

Array classes are created by the JVM as needed, not by reading a normal **[L...;.class** file. **Class.getClassLoader()** of a reference array equals the loader of the component reference type; a primitive array has a loader represented as null.

Example:

~~~java
// Illustrative code inside a method:
ClassLoader a = String[].class.getClassLoader();   // Typically null
ClassLoader b = LoaderBasics[].class.getClassLoader(); // Loader of LoaderBasics
ClassLoader c = int[][].class.getClassLoader();     // null
~~~

Do not infer from an array's descriptor-like name that a JAR file contains an entry named **[Ljava/lang/String;.class**.

## 9. Runnable example 2: same name, two defining loaders, two different types

This exercise uses **two standalone Java files** and two instances of a custom class loader. It demonstrates class identity without depending on a plugin framework.

Directory structure:

~~~text
workspace/
  ClassIdentityDemo.java
  plugin/
    Task.java
  out/                     (create before compiling)
~~~

File **plugin/Task.java**:

~~~java
package plugin;

public final class Task {
    public int run() {
        return 7;
    }
}
~~~

File **ClassIdentityDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassIdentityDemo {
    static final class ByteArrayLoader extends ClassLoader {
        private final byte[] bytecode;

        ByteArrayLoader(byte[] bytecode) {
            super((ClassLoader) null); // Delegate only to bootstrap
            this.bytecode = bytecode.clone();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("plugin.Task")) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytecode, 0, bytecode.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("out", "plugin", "Task.class"));

        ClassLoader first = new ByteArrayLoader(bytes);
        ClassLoader second = new ByteArrayLoader(bytes);

        Class<?> one = Class.forName("plugin.Task", false, first);
        Class<?> two = Class.forName("plugin.Task", false, second);

        System.out.println("sameName="
                + one.getName().equals(two.getName()));
        System.out.println("sameClass=" + (one == two));
        System.out.println("sameLoader="
                + (one.getClassLoader() == two.getClassLoader()));
        System.out.println("eachOwns="
                + (one.getClassLoader() == first
                        && two.getClassLoader() == second));
        System.out.println("assignable="
                + one.isAssignableFrom(two));
        System.out.println("sharedObject="
                + (one.getSuperclass() == two.getSuperclass()));
    }
}
~~~

From the **workspace** directory, with **out** already existing (if not, create the directory):

~~~bash
mkdir out
javac --release 17 -encoding UTF-8 -d out plugin/Task.java ClassIdentityDemo.java
java -cp out ClassIdentityDemo
~~~

If **out** already exists, skip the **mkdir out** command. **Stdout**:

~~~text
sameName=true
sameClass=false
sameLoader=false
eachOwns=true
assignable=false
sharedObject=true
~~~

Why:

- **first** and **second** both receive the same byte array from **Task.class**, but are **two independent ClassLoader instances**.
- Each loader has a null parent, which by convention delegates to bootstrap; bootstrap does not provide **plugin.Task**. After the parent fails to find the class, each loader's **findClass** defines its own copy.
- Both classes carry the same **binary name = plugin.Task**, so **sameName=true**.
- Different **defining loaders** produce different **Class objects**, so **sameClass=false**, **assignable=false**.
- Both classes by default inherit the same **java.lang.Object** defined by bootstrap, so their superclass Class object is one and the same: **sharedObject=true**.

The program does not pass instances between these two classes; if you tried to cast an instance from the first type to the second type, Java would reject it according to runtime type checking.

**Example limitations:** The loader only serves the exact name **plugin.Task**, and Task has no custom plugin dependencies. In a real system, you need to manage multiple classes, resources, package sealing, modules, native libraries, input data security, concurrency, and loader lifecycle. Using the same class name from untrusted sources with **defineClass** requires clear security boundaries.

### 9.1. Why not use parent=system in this example?

If the loader had the system loader as its parent, and system already saw **plugin.Task** on the **out** classpath, the default parent-first algorithm would ask system first, and both child loaders could receive **the same class defined by system**. In that case, the example would no longer demonstrate two different defining loaders. Setting the parent to null is an intentional decision to isolate the **plugin.Task** class in the experiment.

In real applications, you should usually use a parent that shares common APIs (at least the platform loader or a dedicated API loader), rather than assuming a bootstrap parent is appropriate for every plugin.

## 10. Runnable example 3: loading does not automatically run the static initializer

Create the file **InitializationDemo.java**:

~~~java
public class InitializationDemo {
    static class Target {
        static {
            System.out.println("init:Target");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = InitializationDemo.class.getClassLoader();

        Class<?> type =
                Class.forName("InitializationDemo$Target", false, loader);
        System.out.println("loaded=" + (type == Target.class));

        Class.forName("InitializationDemo$Target", true, loader);
        System.out.println("initialized");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 InitializationDemo.java
java InitializationDemo
~~~

**Stdout:**

~~~text
loaded=true
init:Target
initialized
~~~

**Why:** The call **Class.forName(..., false, loader)** provides the **Class object** without requesting initialization of Target. Referencing **Target.class** only obtains the class literal and does not trigger the static initializer. The subsequent **Class.forName(..., true, loader)** call requests initialization and prints **init:Target** once; finally main prints **initialized**.

If Target had already been initialized earlier in the same JVM, the static block would not run again. In this standalone program, it had not been initialized prior to the call with **true**.

## 11. Context class loader: why is there a "context" loader?

The **Thread context class loader (TCCL)** is a loader reference attached to a thread:

~~~java
ClassLoader context = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(context);
~~~

It is **conceptually different** from a class's parent loader or defining loader:

| Kind | Determined by | Purpose |
| --- | --- | --- |
| Class's defining loader | The loader that actually defined the class | Identity of the runtime type |
| Loader's parent | Loader delegation configuration | Where to ask first when looking up a class/resource |
| Thread's context loader | Contextual state set by the thread/framework | Helps infrastructure libraries locate providers/components in the scope of the calling application |

A shared library loaded by bootstrap/platform may need to find extensions packaged in the application. If it only uses the loader that defined the library, it will not necessarily see providers on the application classpath. TCCL provides a way by convention to pass the lookup scope to the library.

For example, **ServiceLoader.load(MyService.class)** (the overload taking a service class) according to the Java API typically uses the thread's context class loader to find providers. Several frameworks, JDBC, logging, SPI, and application servers use TCCL or a similar lookup mechanism.

**Do not confuse:** setting a new context loader with **setContextClassLoader** does not change the defining loader of already-loaded classes, and does not alter the parent chain of the system loader.

### 11.1. Setting TCCL with proper lifecycle management

A useful pattern when temporarily switching context:

~~~java
// Illustrative code inside a method:
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Perform the framework/SPI call that requires pluginLoader.
} finally {
    thread.setContextClassLoader(old);
}
~~~

This is an illustrative snippet, with **pluginLoader** supplied externally. Restore the old loader in **finally** to avoid leaking context to the next task on the same thread, especially in thread pools.

## 12. The Java Platform Module System makes the class loading diagram more nuanced

Since Java 9, the JDK uses the module system. **Module path** and **classpath** have different properties:

- The classpath typically contains classes belonging to the **unnamed module** of the corresponding loader.
- The module path allows the runtime to resolve **named modules** according to module descriptors, exports, reads, and module configurations.
- A module may be defined by the bootstrap, platform, or application loader depending on the JDK/module graph.
- A loader can look up classes based on module/package mappings, and some lookup requests may go to another loader due to module readability/configuration.

A simple example:

~~~bash
java -cp out com.example.Main
~~~

This invokes the main class via the classpath; unlike launching a modular application with:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

The modular line is **illustrative syntax**, requiring a valid module descriptor and artifacts in **mods** in practice. Do not assume simply changing **-cp** to **--module-path** is enough.

**Module encapsulation** is also a separate layer of control: even if a loader finds a class, reflective access to non-open members can still be denied, for example with **InaccessibleObjectException** in applicable situations.

### 12.1. Avoiding outdated JDK 8 assumptions

- **Extension class loader** is no longer the official name of the current tier in JDK 17.
- **rt.jar** and the old JRE/extension directory model are no longer a reliable way to determine the source of Java SE classes.
- The built-in app loader is not required to be a **URLClassLoader**.
- Do not rely on internal implementation names such as **jdk.internal.loader.ClassLoaders$AppClassLoader** to write casts or production APIs.

Rely on **ClassLoader.getPlatformClassLoader()**, **getSystemClassLoader()**, **getParent()**, **getResource(...)**, and public contracts when designing code.

## 13. Custom loaders and child-first: when useful, when risky?

**Parent-first** is useful for sharing platform classes and stable APIs. However, plugin isolation or containers may intentionally use **child-first** for a specific set of packages, so that two modules can run different versions of a library.

One possible per-package policy:

~~~text
Request to load java.*, javax.*, or shared API:
  delegate to parent first

Request to load plugin.internal.*:
  prefer the copy inside the plugin

Other classes:
  delegate/lookup according to loader policy
~~~

This is a conceptual description, **not a standard algorithm applicable to every plugin system**. Risks include:

1. **Class identity conflict:** shared API classes are defined twice so casts, MethodHandles, or reflection no longer match.
2. **LinkageError/loader constraint violation:** descriptors across loaders require the same type but map to different classes.
3. **Broken package-private access:** two classes with the same package name but different loaders are not in the same runtime package.
4. **Deadlock during loading:** loaders acquire locks in incompatible orders when multiple threads load mutually dependent classes.
5. **Resource/service discovery mismatch:** a class is found from one loader, while a resource/provider is found through another loader.
6. **Module/security limits:** a class being present does not mean every package is open or can be defined arbitrarily.
7. **Loader leaks:** threads, ThreadLocals, static caches, timers, MBeans, callbacks, or registries hold strong references to Class/ClassLoader, preventing the plugin from being garbage-collected.

When a custom loader is needed, keep **shared APIs/interfaces** in a stable parent, prefer reusing standard libraries and frameworks that already handle resources/modules/class identity, and only override **loadClass** when the policy genuinely needs to change.

### 13.1. Concurrency and duplicate definition

**ClassLoader.loadClass** by default uses the **getClassLoadingLock(name)** locking mechanism, paired with the **findLoadedClass** step. When writing a custom loader, you must prevent two threads from simultaneously defining the same binary name in the same loader; doing so can cause linkage errors.

A class loader that wants to load different names concurrently can register as **parallel-capable** according to Java API rules. Registration must be performed during class initialization of the loader and coordinate with its superclass; merely adding synchronized in a few places is not enough for every concurrent policy to be correct.

## 14. Classpath, resource lookup, and delegation

Class loaders also locate **resources**. Resource names are usually **/**-separated paths, for example:

~~~text
config/defaults.properties
images/logo.png
META-INF/services/com.example.MyService
~~~

Whereas binary class names typically use dots:

~~~text
com.example.MyService
~~~

This difference leads to a common mistake when calling:

~~~java
// Illustrative inside a method:
ClassLoader loader = Thread.currentThread().getContextClassLoader();
var resource = loader.getResource("config/defaults.properties");
~~~

If you call **getResource("com.example.MyService")** to look up a class file by default, you are using the wrong resource name format. For a class file, the resource path will typically be **com/example/MyService.class**.

**Resource delegation** usually goes through the parent, though there are specific resource lookup rules and Java modules have encapsulation. You should not conclude from **getResource(...) == null** that a Java class definitely cannot be loaded in all cases; the class may be generated from dynamic bytes, the package may not be open, or it may have a different path or loader.

## 15. Diagnosing common class loader errors

| Symptom / Error | Common meaning | What to check |
| --- | --- | --- |
| **ClassNotFoundException** | A request to find a class by name could not find it | Binary name, caller loader, classpath/module path, custom findClass, TCCL |
| **NoClassDefFoundError** | The JVM needed a class during linkage/use but could not obtain the required definition; can also appear after an initialization failure | Root cause, dependencies, class bytes, prior initialization failure |
| **ExceptionInInitializerError** | A static initializer failed and the error was wrapped per rules | Underlying exception in the static initializer |
| **ClassCastException** despite identical class names | Two Class objects have different defining loaders or mismatched interfaces/versions | Print the binary name and **getClassLoader()** of both sides |
| **LinkageError** (various forms) | Violation of linking/definition constraints, e.g. duplicate definition or loader constraints | Which loader defined it, descriptors, class versions, and load logs |
| **IllegalAccessError** | JVM access rules were violated during linking/runtime | Runtime package, defining loader, module access |
| **InaccessibleObjectException** | Reflective access was blocked by module encapsulation | Opens/exports, module graph, avoid reflection into internal APIs |
| **ServiceConfigurationError** | SPI provider could not be found/instantiated/was not assignable | TCCL, META-INF/services, provider module, type identity |
| Plugin cannot be unloaded | Strong references still hold the plugin's loader, classes, or threads | ThreadLocals, executors, caches, callbacks, service registries |

An error showing **ClassNotFoundException: com.example.Foo** is not enough to prove the Foo.class file is missing from the entire machine: the class might be in another loader outside the delegation path, or under a different module name/path configuration.

### 15.1. Step-by-step investigation guide

1. Identify **which class is being requested** and its exact binary name.
2. Identify **where the request originates**: reflection, application main, framework, ServiceLoader, custom loader.
3. Print **Class.getClassLoader()** of the relevant loaded classes and the parent chain via **getParent()**; note that bootstrap typically displays as null.
4. Check **ClassLoader.getSystemClassLoader()**, **getPlatformClassLoader()**, and the current thread's TCCL when SPI/plugins are involved.
5. Check the process's actual classpath/module path, dependency versions, and JAR entries.
6. For custom loaders, inspect the **findLoadedClass → parent → findClass** order, synchronization, and whether the loader defines the same name twice.
7. For cast/linkage errors, compare **Class object identity** and defining loaders, not just type names.
8. For initialization errors, find the underlying exception in the static initializer before changing the classpath.
9. If using JPMS, check reads, exports, opens, and which module owns the package.
10. Fix the right boundary; re-run integration tests using the exact application startup method.

### 15.2. Observation tools

With HotSpot/JDK 17 you can use:

~~~bash
java -Xlog:class+load=info -cp . LoaderBasics
~~~

Depending on configuration, class loading information is written to logs, which may span multiple lines across output streams; **do not** use the full output of this command as the standard stdout of the example because it depends on the runtime.

An option compatible across many Java versions is:

~~~bash
java -verbose:class -cp . LoaderBasics
~~~

For a running process where **jcmd** is supported, you can view the list of diagnostic commands:

~~~bash
jcmd <PID> help
~~~

Then use class loader commands such as **VM.classloaders** or loader statistics if available in the specific JVM. The string **<PID>** is a terminal command placeholder, not literal characters to type verbatim; replace it with the actual process PID. Appropriate permissions are required to attach/diagnose.

When a log records a class as "loaded from location X", do not look solely at the JAR source to conclude class identity; two loaders can still read the same JAR and define two different classes.

## 16. Self-check exercises

**Question 1.** In default JDK 17, what value does **String.class.getClassLoader()** usually return? Does that mean String is not loaded?

**Answer:** It returns **null**, representing the bootstrap loader. String is still a runtime class loaded/defined by the JVM.

**Question 2.** The application loader calls **loadClass("java.lang.String")**, and parent/bootstrap finds the class. Who is the defining loader?

**Answer:** Bootstrap; the application loader may be an initiating loader for the request, but it does not create a new definition for String.

**Question 3.** Two separate custom loaders both define **com.example.Widget** from the same class bytes. Are the two runtime classes equal?

**Answer:** No. Class identity is the pair **(binary name, defining loader)**; if the defining loaders differ, the Class objects differ.

**Question 4.** If two different child loaders both delegate to the same parent that defined **shared.Api**, can the two results be the same Class object?

**Answer:** Yes. Parent-first returns the definition from the parent; the children do not automatically define copies.

**Question 5.** What is the default order in **ClassLoader.loadClass(name, resolve)**?

**Answer:** Check **findLoadedClass**, delegate to parent/bootstrap, and if not found call this loader's own **findClass**; when needed, perform the **resolveClass** step. If not found, throw **ClassNotFoundException**.

**Question 6.** Does **loadClass** force the static initializer to run immediately?

**Answer:** No. Class loading and initialization are two different phases; **Class.forName(name, true, loader)** actively requests initialization.

**Question 7.** Does changing the TCCL cause a class already defined by the system loader to "move" to the plugin loader?

**Answer:** No. TCCL changes the lookup context for APIs/frameworks that use it, not the defining loader of already-created classes.

**Question 8.** Why might ServiceLoader fail to find a provider even though the JAR is on the system?

**Answer:** Depending on the overload and environment, it may be using TCCL or a different module/configuration, the provider may not be within the scope of the loader used, metadata may be missing, or the provider may not be compatible with the shared API type.

**Question 9.** When seeing a **ClassCastException** with two identical type names, what should you check?

**Answer:** Compare the **Class objects** themselves, defining loaders, loader parent paths, and duplicate copies of dependencies/APIs. Having the same binary name is not enough to prove the same runtime type.

**Question 10.** Is it strictly impossible for the platform loader to delegate to the application loader on JDK 17?

**Answer:** No. Java 17 documentation notes cases of module visibility/upgrading that can cause the platform loader to delegate to another loader, including the application loader.

**Question 11.** Does a primitive array class with a name like **[I** have a **[I.class** file for a loader to read?

**Answer:** Not according to the normal Java class file model. The JVM creates array classes on demand; primitive arrays have a loader displayed as **null**. Reference arrays use the defining loader of the component reference type when querying Class.getClassLoader().

**Question 12.** Why should you not cast **ClassLoader.getSystemClassLoader()** to **URLClassLoader** on Java 17?

**Answer:** The built-in system loader is an implementation detail and is not guaranteed by the API to be a URLClassLoader. Use public APIs or appropriate build/deployment mechanisms.

## 17. Checklist for system design

- **Simple classpath app:** rely on the default system loader; no need to create a custom ClassLoader.
- **Running custom plugins:** define the parent, plugin namespace, shared API, and per-package delegation policy.
- **Registering SPI:** understand TCCL, ServiceLoader, provider metadata, and module configuration.
- **Isolating dependency versions:** verify class identity via defining loader, avoid duplicating shared APIs/interfaces into each child loader.
- **Using Reflection:** choose the loader explicitly when needed; consider **Class.forName(name, false, loader)** if you only want to find/inspect a type without initializing it yet.
- **Managing lifecycle:** stop threads/timers, clear registries/caches and TCCL when a plugin stops being used so the loader can be garbage-collected when no longer reachable.
- **Module system:** check both loader visibility and reads/exports/opens relationships.
- **Error diagnosis:** log the class name, defining loader, load location, error cause, and relevant thread context state; avoid relying solely on package names or JARs.
- **Bytecode instrumentation:** ensure class bytes, package, module, class loader identity, and linking constraints align; avoid defining the same name twice in one loader.

### Official documentation

- **Java 17 API — java.lang.ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java 17 API — java.lang.Class**, methods **getClassLoader**, **forName**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java 17 API — java.lang.Thread**, **getContextClassLoader/setContextClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- **Java 17 API — java.util.ServiceLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **JVMS Java SE 17, §5.3 — Creation and Loading**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS Java SE 17, §5.4 — Linking**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS Java SE 17, §5.5 — Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5

**Key takeaway:** On Java 17+, **bootstrap** provides the core foundation, **platform** handles many platform classes, and **application/system** typically loads application classes. ClassLoader by default **delegates parent-first before calling findClass**, though custom loaders and the module mechanism can be more complex than a tree diagram. **Same binary name + different defining loader = different runtime class**. **Loading does not mean initialization**; **TCCL is not the defining loader**. When dealing with class loading, always identify **which loader receives the request, which loader defines it, and which stage of the JVM lifecycle the class is in**.
