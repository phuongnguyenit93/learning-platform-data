# When Is Overriding loadClass Necessary?

## 1. Selection Principle

**You should only override ClassLoader.loadClass when you need to change the class loader selection policy or the delegation order.** If the goal is only to **find class bytes from a new source**, such as a directory, JAR, network, memory, or bytecode generated at runtime, prefer **overriding findClass**. This is recommended directly in Java's ClassLoader Javadoc.

Reason: the default loadClass already has the complete logic **findLoadedClass → parent delegation → findClass → resolveClass if requested**, along with locking. Overriding loadClass completely shifts the responsibility for ensuring caching, synchronization, class identity, and error handling onto you.

Overriding loadClass is a justified choice when:
- A plugin needs **selective child-first**, meaning its own implementation must take precedence over the parent's version with the same name.
- The runtime requires **routing classes by namespace/tenant** instead of relying on the usual parent.
- There is a policy **prohibiting delegation of certain class names to the parent**; the policy must be checked right at the entry point.
- Special delegation across multiple peer loaders requires custom order coordination.

If those situations do not exist, you generally do not need to override. **Do not change the class loading algorithm just because you want to change where class files are read from.**

## 2. Three Methods with Different Roles

~~~java
public Class<?> loadClass(String name)
        throws ClassNotFoundException;

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException;

protected Class<?> findClass(String name)
        throws ClassNotFoundException;
~~~

These are API signatures for reference, not a standalone Java program.

| Component | Role |
| --- | --- |
| **loadClass(String)** | Public entry point, equivalent to loadClass(name, false). |
| **loadClass(String, boolean)** | Protected entry point containing the class lookup algorithm and an option to request linking. |
| **findClass(String)** | Hook to find/define a class when the default algorithm needs the current loader to find it itself. |
| **findLoadedClass(String)** | Checks for a class for which the JVM has already recorded this loader as an initiating loader. |
| **defineClass** | Defines a runtime class from bytecode and assigns the defining loader. |
| **resolveClass(Class)** | Requests class linking; does not initialize static fields. |
| **getClassLoadingLock(String)** | Lock dedicated to a class name during loading, needed when writing your own loadClass. |

Because the two-parameter overload is **protected**, application code normally calls loader.loadClass(name). If a subclass overrides the protected overload, calls to the public loadClass(name) inherited from ClassLoader still go through that execution path.

**The name** is usually a binary name, for example **demo.Widget**, not the file path **demo/Widget.class**. Nested classes usually have a binary name with a **$** sign.

## 3. The Default Parent-First Loading Path

ClassLoader.loadClass(name, resolve) is described by the JDK in the following order:

1. Synchronize on the object returned by **getClassLoadingLock(name)**.
2. Call **findLoadedClass(name)** to reuse an already loaded Class.
3. If not present yet, delegate to **parent.loadClass(name)**; if there is no parent, use the bootstrap loader.
4. If the parent cannot find it, call **findClass(name)** so the current loader defines the class itself.
5. If **resolve=true**, call **resolveClass(c)** on the result.
6. Return **Class<?>**; it does not automatically create an instance or run static initializers.

~~~text
loadClass(name, resolve)
       |
       v
getClassLoadingLock(name)
       |
       v
findLoadedClass(name)
       |
       +-- found ------------------+
       |                           |
       v                           |
parent.loadClass(name)             |
       |                           |
       +-- found ------------------+
       |                           |
       v                           |
findClass(name)                    |
       |                           |
       +---------------------------+
       |
       v
resolve=true? -> resolveClass(c)
       |
       v
return Class<?> c
~~~

**Overriding findClass only replaces one node of the flow above.** You add a way to retrieve the bytes while still inheriting the Class reuse logic, parent-first order, loading lock, and resolution.

That is why the Javadoc recommends that subclasses override **findClass**, rather than overriding **loadClass** by default.

### 3.1 Why Is Parent-First Usually Useful?

- Foundational classes are shared rather than having the child define its own separate version.
- Shared interfaces/DTOs of the host and plugin can have the same Class identity.
- Reduces seemingly puzzling ClassCastException scenarios.
- Less code to manually manage concurrent loading and avoid duplicate definitions.
- Easier to reason about when checking security, module access, package identity, and loader constraints.

Parent-first is not a mandatory rule for every custom loader, but it is a good default when the system does not require child-first isolation.

## 4. Needs That Do Not Require Overriding loadClass

| Need | Extension Point to Consider |
| --- | --- |
| Loading from a separate class directory | findClass or URLClassLoader. |
| Reading bytes from a database, network, or memory | findClass + defineClass. |
| Decrypting/decompressing bytes before defining | Preprocess bytes inside findClass. |
| Generating runtime bytecode by class name | Appropriate defineClass/lookup mechanism, possibly from findClass. |
| Reading *.properties or template resources | findResource/getResource; not loadClass. |
| Wanting a class to be initialized | Active use or Class.forName(name, true, loader). |
| Wanting to load a class by binary name | Call the existing public loadClass. |
| Wanting to see which loader defined a class | Class.getClassLoader() on the result. |
| Wanting to add class loading logging | Prefer JVM logging/instrumentation at an appropriate hook, without changing the algorithm when unnecessary. |

For these cases, replacing loadClass can make the system more complex without any practical benefit.

## 5. Java 17+ Example 1: Only Overriding findClass Is Needed

Goal: the loader finds a class itself in the **plugin-out** directory when the parent cannot see that class.

Structure:

~~~text
project/
├── FinderDemo.java
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
        return "hello";
    }
}
~~~

**FinderDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public class FinderDemo {
    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {

            if (!name.startsWith("plugin.")) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class")
                );
                System.out.println("findClass: " + name);
                return defineClass(name, bytes, 0, bytes.length);

            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader =
                new DirectoryLoader(Path.of("plugin-out"));

        Class<?> type = loader.loadClass("plugin.Greeter");

        System.out.println("defined by child = "
                + (type.getClassLoader() == loader));

        System.out.println("before instance");
        Object obj = type.getConstructor().newInstance();
        System.out.println("message = "
                + type.getMethod("message").invoke(obj));
    }
}
~~~

From the **project** directory:

~~~bash
javac -d plugin-out src/plugin/Greeter.java
javac FinderDemo.java
java FinderDemo
~~~

Stdout verified on JDK 21 (Java 17+ compatible example):

~~~text
findClass: plugin.Greeter
defined by child = true
before instance
Greeter initialized
message = hello
~~~

**Explanation:**

1. **DirectoryLoader** does not override loadClass; it inherits parent-first.
2. **ClassLoader.getPlatformClassLoader()** acts as the parent in the example. This parent cannot find plugin.Greeter located in plugin-out.
3. The default algorithm calls **DirectoryLoader.findClass**, reads the bytes, and calls defineClass.
4. **type.getClassLoader() == loader** is true because DirectoryLoader defined the class.
5. The **Greeter initialized** line only appears when reflection creates an instance; loadClass does not automatically initialize the class.

If **plugin-out** is placed on the search path of an appropriate parent, the parent can find the class first and the child's findClass hook will not run. That is parent-first working as designed, not a bug.

**Class source safety:** the example uses a path controlled by code. A production custom loader must control the binary name, path traversal/symlinks, input bytes, package/protection domain, size, and trusted source. Do not use this example as a loader for loading arbitrary data from users.

## 6. Case Where Overriding Is Actually Needed: Selective Child-First

Suppose:
- The host contains **demo.message.Version** with a source() method returning **parent**.
- The plugin contains a class with the **same binary name** whose source() returns **plugin**.
- Architectural requirement: implementations belonging to **demo.message.*** must prioritize the plugin version.
- Other packages, including the Java platform and shared APIs, must still preserve parent-first.

If you only override findClass, the default algorithm will let the parent find Version first. The parent already has a class with the same name, so child.findClass will not be called. **This is precisely when overriding loadClass can be necessary** to change the order within a selected namespace:

~~~text
If name belongs to demo.message.*
    findLoadedClass
         |
         v
    try findClass(child) first
         |
         +-- not found -> fallback parent
         |
         v
    resolve if requested

If name belongs to another namespace
    super.loadClass -> default parent-first
~~~

Because you are changing the class lookup order, you must maintain caching, locking, the resolve flag, and proper exception handling.

## 7. Java 17+ Example 2: Selectively Overriding loadClass

Directory structure:

~~~text
project/
├── host-src/
│   ├── SelectivePolicyDemo.java
│   └── demo/message/Version.java
└── plugin-src/
    └── demo/message/Version.java
~~~

**host-src/demo/message/Version.java**:

~~~java
package demo.message;

public class Version {
    public String source() {
        return "parent";
    }
}
~~~

**plugin-src/demo/message/Version.java**:

~~~java
package demo.message;

public class Version {
    public String source() {
        return "plugin";
    }
}
~~~

**host-src/SelectivePolicyDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class SelectivePolicyDemo {
    static final class PluginFirstLoader extends URLClassLoader {
        PluginFirstLoader(URL url, ClassLoader parent) {
            super(new URL[]{url}, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            if (!name.startsWith("demo.message.")) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null) {
                    try {
                        found = findClass(name);
                    } catch (ClassNotFoundException missing) {
                        found = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(found);
                }

                return found;
            }
        }
    }

    static String source(Class<?> clazz) throws Exception {
        return (String) clazz.getMethod("source")
                .invoke(clazz.getConstructor().newInstance());
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = ClassLoader.getSystemClassLoader();
        URL pluginUrl = Path.of("plugin-out").toUri().toURL();

        try (URLClassLoader defaultLoader =
                     new URLClassLoader(new URL[]{pluginUrl}, parent);
             PluginFirstLoader selective =
                     new PluginFirstLoader(pluginUrl, parent)) {

            Class<?> parentClass = Class.forName(
                    "demo.message.Version", false, parent);

            Class<?> normal =
                    defaultLoader.loadClass("demo.message.Version");

            Class<?> plugin =
                    selective.loadClass("demo.message.Version");

            System.out.println("default = " + source(normal));
            System.out.println("selective = " + source(plugin));
            System.out.println("default same parent = "
                    + (normal == parentClass));
            System.out.println("selective same parent = "
                    + (plugin == parentClass));
            System.out.println("selective defined by child = "
                    + (plugin.getClassLoader() == selective));
        }
    }
}
~~~

Compile **the two Version.java files into two different output roots**, avoiding mixing class files:

~~~bash
javac -d host-out host-src/demo/message/Version.java host-src/SelectivePolicyDemo.java
javac -d plugin-out plugin-src/demo/message/Version.java
java -cp host-out SelectivePolicyDemo
~~~

Stdout verified by running on JDK 21:

~~~text
default = parent
selective = plugin
default same parent = true
selective same parent = false
selective defined by child = true
~~~

### 7.1 Why Does the Default Version Come from the Parent?

URLClassLoader asks the parent first by default. Host-out is on the application classpath and contains **demo.message.Version**, so defaultLoader receives the Class defined by the application loader; the method returns **parent**.

### 7.2 Why Does the Selective Version Come from the Plugin?

For a name starting with **demo.message.**, PluginFirstLoader calls **findClass** directly before asking the parent. It finds the class in plugin-out and defines the type itself. As a result, the method returns **plugin**.

For other packages, the method calls super.loadClass to maintain the parent-first policy. This prevents child-first from unintentionally spreading to all shared types.

### 7.3 Two Different Classes Despite Having the Same Name

**normal** and **plugin** both have the binary name demo.message.Version, but their defining loaders differ. Because class identity is based on **binary name + defining loader**, the **normal == plugin** comparison will be false.

Do not forcibly cast a plugin instance to the host Version just because the names match. Across a host-plugin boundary, shared interfaces/DTOs generally must come from a common defining loader.

### 7.4 Why Does the Code Use findLoadedClass?

Once a loader has initiated a class by name, subsequent loads must be consistent. **findLoadedClass** avoids attempting to repeatedly define a Class with the same name in the same loader, which could lead to a **LinkageError**.

### 7.5 Why Use getClassLoadingLock?

If two threads concurrently load demo.message.Version at the same time, both could try findClass and defineClass without locking. **synchronized(getClassLoadingLock(name))** helps ensure that the cache check and the definition process happen safely.

In the example, the subclass does not register itself as parallel capable, so the current locking approach is sufficient for illustration. For complex parallel loading systems, registering as parallel-capable before instantiating should be evaluated further.

### 7.6 Why Keep resolveClass When resolve=true?

The protected overload has a **resolve** flag. If true, the custom implementation should call **resolveClass(found)** to uphold the linking contract. **Resolve does not mean initialize**; static initializers still follow separate active use rules.

### 7.7 Why Catch Only ClassNotFoundException to Fall Back?

If the child cannot find the class, falling back to the parent makes sense. However, if the child has invalid bytes and defineClass throws **ClassFormatError**, **VerifyError**, or **LinkageError**, you should not swallow every Throwable and silently use the parent's version. Doing so hides plugin artifact errors and makes the class selection policy unreliable.

In the example, the fallback super.loadClass(name,false) may retry findClass after the parent fails to find it; this is acceptable behavior for illustrative code. Production loaders can optimize this, while still properly preserving caching, locking, and bootstrap/parent semantics.

## 8. Other Cases Where Overriding May Be Reasonable

### 8.1 Multi-Tenant or Namespace-Based Routing

A runtime with multiple isolated class domains may decide that **tenant.alpha.impl** is defined by the Alpha loader, while **tenant.beta.impl** is defined by the Beta loader. If the routing decision cannot be accomplished under default parent-first, a custom loadClass can coordinate the namespaces.

However, when you only want each loader to locate its own byte source and the parent has no competing version, overriding findClass remains simpler.

### 8.2 Proactively Denying a Package Before Delegation

If a policy requires that a plugin **must not see** an internal host package even when the parent has that class, the check must sit **before parent delegation**, so overriding loadClass may be considered.

However, **ClassLoader is not a complete security sandbox**. Rejecting a class name does not replace process isolation, control of exposed APIs, module access, or other security mechanisms. Do not claim that blocking a package is sufficient to safely run untrusted code.

### 8.3 Non-Tree Delegation

Complex module/plugin systems may search for classes across multiple peer loaders instead of a single parent. When overriding loadClass to do this, the risk of **deadlock** is higher because chains can form where loader A waits for B and B waits for A.

You need a clear architecture for lookup order, caching, locking, parallel loading, and cycle bounds. Before writing one from scratch, evaluate proven frameworks/module systems with suitable policies.

## 9. Concurrency: Do Not Break Class Loading Consistency

### 9.1 getClassLoadingLock Is the Foundational Tool

ClassLoader.loadClass synchronizes the entire process on **getClassLoadingLock(name)** by default.

- Non-parallel-capable loaders typically use the ClassLoader object itself as the lock.
- Parallel-capable loaders can use a separate lock per binary name.
- The goal is to prevent two threads from defining a class with the same name simultaneously and to control interaction with delegate loaders.

An override that omits all synchronization easily introduces races. Not every race manifests immediately; it may only appear under heavy server load.

### 9.2 Parallel-Capable Class Loaders

Java provides:

~~~java
protected static boolean registerAsParallelCapable();
protected Object getClassLoadingLock(String className);
~~~

These are API signatures. When a subclass wants to be considered parallel capable, registration must be performed according to the rules when the class loader subclass is initialized and depends on the superclass's parallel-capable capability. Just because the ClassLoader superclass is registered does not mean every subclass is automatically registered.

Non-hierarchical delegation models need to pay special attention to parallel capability to avoid deadlocks. If a simple loader has no high throughput requirements, prefer the default algorithm instead of overcomplicating locking yourself.

### 9.3 Do Not Replace an Already Loaded Class in the Same Loader

Once a loader has initiated a class with a binary name, findLoadedClass can return that exact same Class. You cannot silently replace the entire Class with a newer version of the file bytes merely by changing the policy afterward.

If the architecture must hot-reload implementations, you typically create a **new ClassLoader for each deployment** and manage closing resources, canceling tasks, registries, and references to the old loader. Redefinition via instrumentation is a different matter, not adding another class definition with the same name in the same loader.

## 10. Verify the Contract Before Changing Order
If switching to child-first, identify **which types actually cross the host–plugin boundary** before choosing a prefix. For example, two separate implementations can use different versions of a private library; however, `api.Task` used as a host interface must be provided by the same defining loader. Specifically, verify:

```java
Class<?> pluginType = selective.loadClass("demo.message.Version");
System.out.println(pluginType.getClassLoader() == selective);
```

This is a snippet within the scope of example 7. The result confirms that the implementation is defined by the child; it does **not** prove that every DTO/annotation/exception contract is shared. When adding a child-first namespace, separately verify `sharedApiFromChild == sharedApiFromHost` for the actual APIs and maintain the corresponding package/platform rules.

## 11. Common Design Mistakes

### 11.1 Overriding Public loadClass and Unconditionally Returning findClass

This is an **incorrect** example, do not use it:

~~~java
@Override
public Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return findClass(name);
}
~~~

It bypasses findLoadedClass, parent delegation, the resolve path, and locking. The result may fail to load standard Java classes or attempt to redundantly define an already existing class.

### 11.2 Child-First for All Packages

If plugin-first is applied too broadly, the loader may define shared APIs itself or attempt to handle platform namespaces. The consequences are cast failures, LinkageError, or namespace protection errors.

**Filter namespaces strictly.** The prefix **demo.message.** is different from **demo.messages**; do not use startsWith("demo.message") if you do not want to match a different package that shares the prefix.

### 11.3 Catching Throwable and Falling Back to the Parent

A VerifyError or ClassFormatError indicates invalid bytes/definition, not merely “class not found”. If swallowed and fallen back arbitrarily, the application may silently pick the wrong implementation version.

### 11.4 Defining a Class Multiple Times Yourself

Do not skip **findLoadedClass**. A second defineClass for the same binary name in the same loader can throw LinkageError. Synchronization is also required.

### 11.5 Using loadClass to Alter Initialization

**loadClass does not automatically run static initializers.** The resolve flag is a linking request, not initialization. If you want to proactively initialize using the appropriate API, consider **Class.forName(name, true, loader)**, keeping in mind that it can cause side effects.

### 11.6 Assuming Resource Lookup Automatically Changes with Class Lookup

**getResource/getResources** have their own resource policy. Overriding loadClass for child-first classes does not automatically make resources child-first. If a plugin needs the same priority for templates/configs, you need to design an appropriate resource lookup.

### 11.7 Forgetting the ClassLoader Lifecycle

A new ClassLoader per plugin helps with isolation, but does not automatically make the old loader collectible. Long-lived threads with a context ClassLoader, ThreadLocal values, callback registries, executor queues, or static caches can continue to retain the old loader. Designing unload/cleanup is part of the plugin policy.

## 12. Diagnosing When a Custom Loader Behaves Incorrectly

### findClass Is Never Called

Check whether the parent can find the class name. With parent-first, this is normal behavior. Inspect **returnedClass.getClassLoader()** to see the defining loader.

### ClassCastException Even Though the Message Shows Two Identical Names

Compare **a == b**, **a.getClassLoader()**, and **b.getClassLoader()**. Having the same string name does not mean the runtime types are the same. Check whether a shared API is being defined separately by each loader.

### ClassNotFoundException

Check the binary name, bytecode source, parent chain, and fallback. Nested classes have a **$** character in their binary name. A ClassNotFoundException from findClass signals that the class could not be found; preserve the cause when an I/O error occurs.

### NoClassDefFoundError

Can appear when the JVM needs a type for resolution/initialization and the class cannot be used. Inspect the cause/stack trace and distinguish it from the checked ClassNotFoundException of lookup APIs.

### LinkageError or Loader Constraint Violation

Check for duplicate definitions in the same loader, shared types defined by multiple loaders, method signatures between host/plugin, package restrictions, and module access.

### Deadlock During Concurrent Loading

Take a thread dump and look for locks on loaders A/B and call chains. Evaluate getClassLoadingLock, parallel capability, and delegation cycles. Do not remove synchronized just to avoid blocking; races can cause incorrect class identity.

### Plugin JAR Replaced, Yet the Old Class Still Runs

Check whether the ClassLoader is returning an already loaded Class, as well as the source URL, parent-first behavior, and the deployment's loader. You may need to create a new loader and unload the old one instead of merely replacing the file on disk.

## 13. Java 17+ Observability Tools

In a JVM environment supporting Unified Logging:

~~~bash
java -Xlog:class+load=info -cp host-out SelectivePolicyDemo
java -Xlog:help
~~~

Logging can show which class was loaded and its source, though the format depends on the JVM. For class-file bytes:

~~~bash
javap -verbose -classpath host-out demo.message.Version
javap -verbose -classpath plugin-out demo.message.Version
~~~

The two javap commands inspect artifact contents; they do not prove which runtime loader defined the class. Therefore, combine logs with **Class.getClassLoader()** and **Class object identity** in the program.

If using a JAR:

~~~bash
jar --list --file plugin.jar
~~~

An entry existing inside a JAR does not necessarily mean the runtime selects it. Parent delegation can still return the class from elsewhere.

## 14. Checklist Before Deciding to Override

Before writing a custom loadClass, ask yourself:

1. Is parent-first actually wrong for the requirement?
2. If you only need to add a source of class bytes, is findClass already sufficient?
3. Which packages are allowed to be child-first? Is the filter exact and narrow?
4. Which shared interface/DTO/JDK classes must be used from the parent?
5. Have you checked findLoadedClass and synchronized on getClassLoadingLock?
6. Is the resolve flag preserved?
7. Do you only fall back on ClassNotFoundException, or have you accidentally swallowed LinkageError?
8. When the parent also has a class with the same name, has the expected outcome been tested?
9. Is concurrent loading supported and has deadlock risk been evaluated?
10. Are there module/package/security constraints?
11. Do resource lookup and class lookup require compatible policies?
12. Does reload/unload clean up references to the old loader?
13. Are there integration tests covering multiple ClassLoaders and the host API boundary?

If most answers are “no change needed”, keep the default ClassLoader and override only findClass.

## 15. Self-Check

**1.** You want to load a class from the plugin-out directory where the parent cannot see it. What should you override?

**Answer:** findClass (or use a built-in loader); there is no need to override loadClass.

**2.** Both parent and child have p.Version, and the child version needs priority. What override might be needed?

**Answer:** loadClass, to change parent-first into selective child-first.

**3.** Why must findLoadedClass be used before findClass when customizing loadClass?

**Answer:** To reuse the Class already recorded by the JVM for that loader/name, avoid duplicate definitions, and preserve type identity.

**4.** Does resolve=true mean static initializers must run?

**Answer:** No. It requests resolveClass/linking per the contract; initialization is a separate step.

**5.** Are classes with the same binary name and same bytes but different defining loaders the same Class?

**Answer:** No. The defining loader is part of runtime class identity.

**6.** Why should a shared interface api.Task generally be defined by the parent?

**Answer:** Host and plugin need the exact same api.Task Class so casting and method signature linkage remain compatible.

**7.** Should you catch Throwable from child.findClass and fall back to the parent?

**Answer:** No. Format, verification, and linkage errors must be surfaced; only ClassNotFoundException indicates that the child did not find it.

**8.** What can happen if two threads define the same name without locking?

**Answer:** Races, duplicate definitions, LinkageError, or inconsistent state.

**9.** Does overriding loadClass automatically make getResource child-first?

**Answer:** No. Resource lookup has its own APIs and policies.

**10.** Can you replace the implementation of an already loaded class in the same loader with new bytes?

**Answer:** You cannot silently redefine it as a new class with the same name; you typically need a new loader for a new deployment or a separate instrumentation mechanism.

## 16. Key Takeaways

~~~text
Only changing the bytecode source?
        |
        +-- Yes -> prefer findClass
        |
        +-- No, need to change lookup order/policy?
                       |
                       +-- May override loadClass
                                |
                                +-- findLoadedClass
                                +-- getClassLoadingLock
                                +-- clear package filters
                                +-- controlled fallback
                                +-- resolveClass if resolve
                                +-- shared API identity
                                +-- concurrency, errors, and lifecycle
~~~

**findClass** is the default extension point for bytecode sources; **loadClass** is the intervention point for loader selection policy. Override loadClass only when policy requirements genuinely demand it, and always preserve caching, concurrency, resolution, type identity, and the host-plugin boundary.

### References

- Java SE 17 ClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 21 ClassLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- JVMS §5.3 Creation and Loading: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3
- JVMS §5.3.4 Loading Constraints: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4
- JLS §12.2 Loading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
