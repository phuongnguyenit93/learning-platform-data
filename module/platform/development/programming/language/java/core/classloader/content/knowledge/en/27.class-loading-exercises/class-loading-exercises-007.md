# Reproducing and Fixing the Error Where Classes Have the Same Name but Cannot Be Cast in Java

> **Java Core → ClassLoader → Practice.** Two objects whose classes have the same **binary name**, the same source code, and even the same bytecode taken from a single directory/JAR, can still **fail to be cast** if those classes are defined by **two different ClassLoaders**. This error commonly occurs in plugin systems, application servers, OSGi, hot reload, test class loaders, or applications that package a duplicate copy of the host API. This hands-on exercise uses Java 17+ to (1) reproduce `ClassCastException` with two independent loaders, (2) **fix** it using a shared interface defined by the parent/host loader, and (3) intentionally re-create the error when a plugin defines its own copy of the API using child-first loading. Every program includes files, build commands, verified stdout, and explanations tied to runtime class identity.

## 1. The Problem: The Class Names Are the Same, but Type Identity Differs

In Java, the runtime type of an ordinary class or interface **is not determined solely by its fully qualified name**. According to JVM Specification `5.3`:

```text
Runtime class identity = (binary name, defining ClassLoader)
```

For example, with the same binary name `dup.Token`:

```text
                 ClassLoader L1
                      |
                      v
           defineClass("dup.Token")
                      |
                      v
                Class<?> A

                 ClassLoader L2
                      |
                      v
           defineClass("dup.Token")
                      |
                      v
                Class<?> B

A.getName() == B.getName()     // same String content
A == B                         // false
A.getClassLoader() == L1       // true
B.getClassLoader() == L2       // true
```

This means:

- An instance of `A` **is not automatically** an instance of `B`.
- `B.class` cannot be cast to `A.class` merely because the two classes have the same name.
- `Class.cast` also uses **runtime type identity**, rather than only comparing `getName()`.
- If both are defined by two different loaders, even when their bytecode contents are 100% identical, `ClassCastException` can still occur.
- Two Java packages can also be **two different runtime packages** when they have the same package name but different defining loaders; package-private access and related linkage rules are affected.
- The JVM does not "merge" two classes from different loaders after they have been defined.

This is the correct JVM mechanism for allowing multiple versions of a library to coexist side by side and isolating namespaces, **not a bug in casting**.

## 2. Minimal Reproduction: Same .class File, Two URLClassLoaders

We intentionally use **the same directory containing exactly one `dup/Token.class`** and create **two different `URLClassLoader` instances**, both having the platform loader as their parent. Because `dup.Token` is not in the parent, each loader must define its own runtime class.

Sources:

```text
src/
  dup/dup/Token.java
  host/api/Message.java
  plugin/impl/HelloPlugin.java
  app/
    LoaderIdentityDemo.java
    DuplicateApiDemo.java
build/
  duplicate/                  (created by javac)
  host/                       (created by javac)
  plugin/                     (created by javac)
  app/                        (created by javac)
plugin.jar                    (created by jar)
plugin-with-api.jar           (created by jar)
```

We will use all five source files throughout the experiments so learners can copy them into a single project.

### File 1: src/dup/dup/Token.java

```java
package dup;

public final class Token {
    public String value() {
        return "token";
    }
}
```

This class does not implement any interface from the host. It is a concrete type used to **demonstrate a broken cast**.

### Obtaining the Same Class with Two Loaders

The following code will appear in `LoaderIdentityDemo.main` in section 5:

```java
URL classes = Path.of("build/duplicate")
        .toAbsolutePath().toUri().toURL();

try (URLClassLoader left = new URLClassLoader(
             new URL[]{classes},
             ClassLoader.getPlatformClassLoader());
     URLClassLoader right = new URLClassLoader(
             new URL[]{classes},
             ClassLoader.getPlatformClassLoader())) {

    Class<?> a = Class.forName("dup.Token", true, left);
    Class<?> b = Class.forName("dup.Token", true, right);

    Object rightObject = b.getDeclaredConstructor().newInstance();
    a.cast(rightObject);  // throws ClassCastException
}
```

This is an **excerpt** of the complete program, not a standalone Java file. `Class.forName(name, true, loader)` loads/finds the class via the specified loader and requests initialization; in this example, `Token` has no special static initializer. Having the same directory URL **does not** make the two loaders the same object.

## 3. Why Does the JVM Reject the Cast?

A runtime cast does not merely ask whether class names match; it asks about the actual type relationship:

```text
Object rightObject is an instance of:
   (dup.Token, defining loader = right)

The call a.cast(rightObject) requires it to be an instance of:
   (dup.Token, defining loader = left)

Two Class<?> objects with different identities -> no assignable relationship
                                                -> ClassCastException
```

`java.lang.Class#cast(Object)` checks whether the object can be cast to the type represented by this `Class<?>`. `Class#isInstance(Object)` and `Class#isAssignableFrom(Class<?>)` are also useful for checking beforehand:

```java
System.out.println(a.isInstance(rightObject)); // false
System.out.println(a.isAssignableFrom(b));      // false
System.out.println(a == b);                     // false
```

These lines are a snippet placed within a scope that has `a`, `b`, and `rightObject` from the example in section 2. They cannot "fix" the type identity relationship; they only reflect the actual state.

A situation can also occur where a shared subclass relationship allows casting to a **common interface/superclass** to succeed, even though casting between **two concrete implementation classes** still fails. This is the key to the fix in a plugin architecture.

### Why Can Invoking Methods via Reflection Still Succeed?

Even when two concrete types cannot be cast directly, reflection can invoke a public method on the right `Class<?>` and corresponding object:

```java
Object value = b.getDeclaredConstructor().newInstance();
Object result = b.getMethod("value").invoke(value);
```

This approach **does not turn** `value` into an instance of class `a`. Reflection still checks access and the method receiver; it merely avoids requiring a static cast to an incompatible concrete type.

Using reflection for every call is a risky workaround (loss of type safety, needing to handle `InvocationTargetException`, JPMS/reflection issues), and not the recommended plugin communication design.

## 4. The Fix: A Shared API Defined by the Host/Parent

A plugin system should clearly separate:

```text
System/host ClassLoader
    └── api.Message         <-- defined ONLY ONCE
          ^
          |
    +-----+------------------------------+
    |                                    |
PluginLoader A                      PluginLoader B
    └── impl.HelloPlugin               └── impl.HelloPlugin
         implements api.Message             implements api.Message
```

The two concrete implementation classes still have different identities:

```text
(impl.HelloPlugin, Loader A)
(impl.HelloPlugin, Loader B)
```

**But both implement the exact same runtime interface:**

```text
(api.Message, HostLoader)
```

The host can cast each implementation object to `api.Message`, and then call `message()` through the shared interface. There is no need to cast an object from plugin A to an implementation class defined by plugin B.

### File 2: src/host/api/Message.java

```java
package api;

public interface Message {
    String message();
}
```

This file **belongs to the host application**, is compiled into `build/host`, and is placed on the host application's classpath. A second copy of it **must not** be packaged into `plugin.jar` in the proper solution.

### File 3: src/plugin/impl/HelloPlugin.java

```java
package impl;

import api.Message;

public final class HelloPlugin implements Message {
    @Override
    public String message() {
        return "hello-from-plugin";
    }
}
```

When compiling the plugin, the compiler must see the host API via `-cp build/host`. However, **a compile-time classpath does not mean a copy of the API should be packaged into the plugin JAR**. `plugin.jar` will contain only `impl/HelloPlugin.class`. When the JVM resolves the plugin's interface, the plugin's parent loader must return the host's own `api.Message`.

### When Should You Use a Shared API?

- The host needs to call plugin methods through a clear contract.
- Multiple plugin loaders coexist side by side, each containing different implementations/dependencies.
- You need to hot reload implementations while the host API remains stable.
- You want to avoid using reflection for every operation.
- You want a public contract that can be tested for Java source and binary compatibility.

**Do not cast plugin implementation objects to each other:**

```java
// DO NOT do this with an implementation from another loader:
// HelloPluginFromA typed = (HelloPluginFromA) objectFromB;

// DO:
// Message typed = (Message) objectFromAOrB;
```

The two lines above are **pseudocode** because the names `HelloPluginFromA` and `objectFromB` are not declared Java classes/variables. In the complete program, the code uses the `Message` interface directly.

## 5. Complete Program: LoaderIdentityDemo.java

**File `src/app/LoaderIdentityDemo.java`** creates both the broken-cast scenario and the fixed scenario.

```java
import api.Message;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL classes = Path.of("build/duplicate")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader left = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader right = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> a = Class.forName("dup.Token", true, left);
            Class<?> b = Class.forName("dup.Token", true, right);
            Object rightObject =
                    b.getDeclaredConstructor().newInstance();

            System.out.println("same binary name: "
                    + a.getName().equals(b.getName()));
            System.out.println("same Class object: "
                    + (a == b));
            System.out.println("distinct defining loaders: "
                    + (a.getClassLoader() == left
                       && b.getClassLoader() == right));
            System.out.println("same runtime module: "
                    + (a.getModule() == b.getModule()));

            try {
                a.cast(rightObject);
                System.out.println("cross-loader cast: succeeded");
            } catch (ClassCastException ex) {
                System.out.println(
                        "cross-loader cast: ClassCastException");
            }
        }

        URL pluginJar = Path.of("plugin.jar")
                .toAbsolutePath().toUri().toURL();
        ClassLoader hostLoader = Message.class.getClassLoader();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[]{pluginJar}, hostLoader);
             URLClassLoader second = new URLClassLoader(
                     new URL[]{pluginJar}, hostLoader)) {

            Class<?> p1 = Class.forName(
                    "impl.HelloPlugin", true, first);
            Class<?> p2 = Class.forName(
                    "impl.HelloPlugin", true, second);

            Message m1 = (Message) p1
                    .getDeclaredConstructor().newInstance();
            Message m2 = (Message) p2
                    .getDeclaredConstructor().newInstance();

            System.out.println("plugin impl classes identical: "
                    + (p1 == p2));
            System.out.println("shared host interface: "
                    + (p1.getInterfaces()[0] == Message.class
                       && p2.getInterfaces()[0] == Message.class));
            System.out.println("both cast to host API: "
                    + (m1 instanceof Message
                       && m2 instanceof Message));
            System.out.println("first plugin result: "
                    + m1.message());
            System.out.println("second plugin result: "
                    + m2.message());
        }
    }
}
```

### Mechanics of the First Part

- `left` and `right` have **the same URL** pointing to `build/duplicate`, yet they are **two different loader objects**.
- Because `dup.Token` is not in the platform loader, `left` and `right` each separately define a class from the same bytes.
- `a.getName().equals(b.getName()) == true`, but `a == b == false`.
- The two classes belong to **two different unnamed modules** associated with the two loaders (in this example), so `a.getModule() == b.getModule()` is `false`.
- `a.cast(rightObject)` attempts to cast an instance of B to A: the JVM rejects it as expected.

### Mechanics of the Second Part

- `Message.class` is defined by the host/system loader because `build/host` is on `-cp`.
- The two plugin loaders use **the loader of `Message.class` itself as their parent**.
- `plugin.jar` contains only the implementation; `impl.HelloPlugin` is defined separately by each child loader.
- When loading the `api.Message` interface, the parent returns a shared `Class<?>`.
- Although `p1 != p2`, both instances can be cast to the same `Message` and call `message()` safely.
- The demo uses `p1.getInterfaces()[0]` because the demo's `HelloPlugin` has exactly one direct interface. In real applications, do not rely on index 0; use `Message.class.isAssignableFrom(p1)` and inspect the interface hierarchy.

## 6. Compilation, JAR Packaging, and Run Commands

From the root directory containing `src`, run:

```bash
javac --release 17 -d build/duplicate src/dup/dup/Token.java
javac --release 17 -d build/host src/host/api/Message.java
javac --release 17 -cp build/host -d build/plugin src/plugin/impl/HelloPlugin.java
jar --create --file plugin.jar -C build/plugin .
javac --release 17 -cp build/host -d build/app src/app/LoaderIdentityDemo.java
```

On **Linux/macOS**, the separator for multiple entries in a Java classpath is `:`:

```bash
java -cp "build/app:build/host" LoaderIdentityDemo
```

On **Windows PowerShell/CMD**, the classpath separator is `;`:

```powershell
java -cp "build/app;build/host" LoaderIdentityDemo
```

Do not add `build/duplicate`, `build/plugin`, or `plugin.jar` to the **host application classpath**. If you place them there, the host/system loader may load `dup.Token` or `impl.HelloPlugin` before the child due to parent-first delegation, causing the experiment to **no longer measure two different defining loaders**.

`Plugin.jar` does not need a copy of `api/Message.class`, because `Message` is already on the host. Separating the compile classpath from the final plugin archive is the key practical point.

### Exact Stdout from Running on OpenJDK 24 with javac --release 17

```text
same binary name: true
same Class object: false
distinct defining loaders: true
same runtime module: false
cross-loader cast: ClassCastException
plugin impl classes identical: false
shared host interface: true
both cast to host API: true
first plugin result: hello-from-plugin
second plugin result: hello-from-plugin
```

These ten lines do not depend on absolute directory names. The result shows that the issue is **loader-scoped type identity**, and the proper fix lies in a **shared parent API**, not in trying to force the cast.

**This is a functional test, not proof that the plugin is sandboxed.** Plugin classes run in the same JVM process; loaders do not automatically grant or revoke filesystem/network permissions.

## 7. Counterexample: Plugin Repackages the API and Uses Child-First

A very common source of errors:

```text
Host:
  build/host/api/Message.class
  (defined by system ClassLoader)

Plugin JAR:
  api/Message.class           <-- duplicate copy of the API packaged by mistake
  impl/HelloPlugin.class

Child-first PluginLoader:
  prioritizes api.* from plugin JAR
  prioritizes impl.* from plugin JAR
```

At this point:

```text
Host API:
    (api.Message, HostLoader)

Plugin API:
    (api.Message, PluginLoader)

Plugin implementation:
    (impl.HelloPlugin, PluginLoader)
    implements (api.Message, PluginLoader)
```

Even though `HelloPlugin` declares `implements api.Message` in its source, it **implements the copy of the API defined by the child loader itself**, not the host's API. Checking it from the host via `Message.class.isAssignableFrom(pluginClass)` yields `false`. Casting it to the host's `api.Message` throws `ClassCastException`.

### Creating the Faulty JAR Containing a Copy of the API

After completing the build steps in section 6, run:

```bash
jar --create --file plugin-with-api.jar \
    -C build/plugin . \
    -C build/host api/Message.class
```

On Windows PowerShell, run the same command on **a single line**:

```powershell
jar --create --file plugin-with-api.jar -C build/plugin . -C build/host api/Message.class
```

`plugin-with-api.jar` contains both `impl/HelloPlugin.class` and `api/Message.class`. This is an **intentionally broken** artifact used to reproduce the bug, and must not be used as the fixed plugin artifact.

### File 5: src/app/DuplicateApiDemo.java

```java
import api.Message;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class DuplicateApiDemo {
    static final class ChildFirst extends URLClassLoader {
        ChildFirst(URL url, ClassLoader parent) {
            super(new URL[]{url}, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> c = findLoadedClass(name);

                if (c == null) {
                    if (name.startsWith("api.")
                            || name.startsWith("impl.")) {
                        try {
                            c = findClass(name);
                        } catch (ClassNotFoundException missing) {
                            c = super.loadClass(name, false);
                        }
                    } else {
                        c = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(c);
                }
                return c;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugin-with-api.jar")
                .toAbsolutePath().toUri().toURL();

        try (ChildFirst loader = new ChildFirst(
                jar, Message.class.getClassLoader())) {

            Class<?> childApi = Class.forName(
                    "api.Message", false, loader);
            Class<?> plugin = Class.forName(
                    "impl.HelloPlugin", true, loader);
            Object instance =
                    plugin.getDeclaredConstructor().newInstance();

            System.out.println("same api binary name: "
                    + childApi.getName()
                              .equals(Message.class.getName()));
            System.out.println("same api Class object: "
                    + (childApi == Message.class));
            System.out.println("plugin implements child api: "
                    + (plugin.getInterfaces()[0] == childApi));
            System.out.println("host API assignable: "
                    + Message.class.isAssignableFrom(plugin));

            try {
                Message typed = (Message) instance;
                System.out.println("host API cast: succeeded");
            } catch (ClassCastException expected) {
                System.out.println(
                        "host API cast: ClassCastException");
            }
        }
    }
}
```

### Why Does the Overridden loadClass Use a Lock?

This child-first example serves only to demonstrate the bug. However, to avoid introducing extra race conditions or double definitions, the code still:

1. Locks with `synchronized(getClassLoadingLock(name))`.
2. Checks `findLoadedClass(name)`.
3. Attempts child-first loading for `api.` and `impl.`, then falls back to the parent via `super.loadClass(name,false)`.
4. Calls `resolveClass` when `resolve == true`.

**This is not a production-reviewed classloader**. In real systems, a child-first policy must account for protected packages (`java.`), class-loading locks, package sealing, certificates, module access, dependency APIs, and security boundaries. In particular, **you should not use child-first loading for the API package shared with the host itself**.

### Compiling and Running the Duplicate API Error Example

```bash
javac --release 17 -cp build/host -d build/app src/app/DuplicateApiDemo.java
```

Linux/macOS:

```bash
java -cp "build/app:build/host" DuplicateApiDemo
```

Windows:

```powershell
java -cp "build/app;build/host" DuplicateApiDemo
```

**Verified stdout on OpenJDK 24, with bytecode built using `--release 17`:**

```text
same api binary name: true
same api Class object: false
plugin implements child api: true
host API assignable: false
host API cast: ClassCastException
```

Both the host and the child have `api.Message` with the same binary name, but their `Class<?>` objects differ; the plugin implements the child copy of the API. This is **the exact kind of error** that occurs when a plugin JAR redundantly packages the host API and a child-first loader shadows the host's API.

## 8. Thoroughly Fixing the Duplicate API

To fix the scenario from section 7 in a real application:

1. **Place the host API on a shared parent classpath/module** and ensure it is loaded by a stable loader.
2. **Do not package a second copy of the API classes into the plugin JAR**. If the plugin only needs the API at compile time, mark the dependency as *provided/compileOnly* as appropriate for Maven/Gradle.
3. **The delegation policy for the API namespace must be parent-first**. If child-first is required for third-party libraries to support multiple versions, separate the rules clearly: `java.` and the host's `api.` are parent-first, while `impl.` and plugin libraries are handled by the child by design.
4. **Recreate the plugin loader** after making changes. A loader that has already defined the wrong class will not replace that definition simply because you delete the `api/Message.class` copy from the JAR on disk.
5. **Verify type identity** with `api.Message.class.isAssignableFrom(implClass)` before casting in the plugin system.
6. **Run integration tests matching the actual loader topology**. Unit tests that run all classes on a single classpath cannot reproduce bugs caused by multiple defining loaders.
7. **Manage the version of the contract API**. The shared API must remain binary-compatible between the host and plugins; if interfaces or method signatures change incompatibly, you can also encounter `NoSuchMethodError`, `AbstractMethodError`, or other linkage errors.

### Maven: Plugin API Dependency as provided

A `pom.xml` fragment for the plugin:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>plugin-api</artifactId>
    <version>1.0.0</version>
    <scope>provided</scope>
</dependency>
```

This is an **illustrative configuration fragment**; the artifact coordinates `com.example:plugin-api:1.0.0` are an example name. `provided` indicates that the dependency is available at compile time but is normally not packaged as a runtime transitively included dependency of the plugin; if using a shaded/assembly plugin, inspect the actual artifact because custom packaging rules may still copy it.

With Maven Shade, check dependencies/exclusions/relocations to ensure another copy of `api.Message` is not packaged into the plugin. **Relocating the shared API** does not create a shared type identity; it renames the API and breaks the contract with the host.

### Gradle: Using compileOnly for the Shared API

A Gradle Groovy DSL fragment:

```groovy
dependencies {
    compileOnly 'com.example:plugin-api:1.0.0'
}
```

This is illustrative syntax. `compileOnly` does not by itself guarantee that an uber-JAR produced by a custom packaging task will not copy the API; you need to inspect the contents of the final plugin JAR.

### Checking the JAR for a Duplicate API Copy

```bash
jar tf plugin.jar
jar tf plugin-with-api.jar
```

In the example:

```text
plugin.jar:
  impl/HelloPlugin.class

plugin-with-api.jar:
  impl/HelloPlugin.class
  api/Message.class
```

These two snippets **excerpt the relevant entries**, rather than showing the full output of `jar tf` (since META-INF/MANIFEST.MF is also present). In production, scan all plugin artifacts and nested/shaded JARs if the runtime loader unpacks or loads them.

## 9. Why Is Parent-First Important When Fixing Cast Errors?

`ClassLoader.loadClass` by default checks already-loaded classes, asks the parent first, and only then calls the child's `findClass`. When the child calls `loadClass("api.Message")` while the parent already provides that API, **the defining loader is the parent**; the child can only act as the initiating loader. Therefore, a duplicate copy of the API inside the plugin JAR might still *not yet* cause an error when the loader is parent-first.

The counterexample in section 7 intentionally applies **child-first to `api.*`**, causing the plugin to define a different `api.Message` and the host cast to fail. The fix is to keep `api.*`/shared contracts parent-first, separating the implementation namespace and private dependencies. If child-first is needed for private libraries, you must preserve `getClassLoadingLock`, `findLoadedClass`, delegation, `resolveClass`, and proper exception classification; do not apply a single policy to all packages.

**Practical verification:** `Message.class.isAssignableFrom(pluginClass)` along with `pluginClass.getClassLoader()` is more reliable than comparing the class name or source JAR. The TCCL and reflective access do not change the runtime identity already defined by the JVM.

## 10. Diagnosing ClassCastException in Practice

The error message may look like:

```text
java.lang.ClassCastException: class dup.Token cannot be cast to class dup.Token
(dup.Token is in unnamed module of loader ...;
 dup.Token is in unnamed module of loader ...)
```

This is a **sample message**; the OpenJDK version, loader names, and module metadata may cause the format or wording to vary. The "cannot be cast to itself" part is not nonsensical if the **two runtime types** have different defining loaders.

### Proper Type Identity Logging Pattern

```java
static void describe(Object obj) {
    if (obj == null) {
        System.out.println("<null>");
        return;
    }
    Class<?> type = obj.getClass();
    System.out.println("typeName=" + type.getName());
    System.out.println("typeIdentity=" +
            System.identityHashCode(type));
    System.out.println("definingLoader=" + type.getClassLoader());
    System.out.println("loaderIdentity=" +
            System.identityHashCode(type.getClassLoader()));
    System.out.println("module=" + type.getModule());
}
```

This is a **method snippet** that can be placed in any class; using `System.identityHashCode` helps distinguish objects in logs, though hashes can collide — **do not use the hash in place of `==` comparison**.

Details to record separately for the **expected type** and the **actual object**:

- `expected.getName()` and `actual.getClass().getName()`.
- `expected == actual.getClass()`.
- `expected.isInstance(actual)`.
- `expected.isAssignableFrom(actual.getClass())`.
- `expected.getClassLoader()` and `actual.getClass().getClassLoader()`, comparing **identity**.
- `getModule()` and the source location (`ProtectionDomain.CodeSource`) when available.
- When a custom plugin loader is present, log `pluginId`, loader generation, parent, and source JAR/version.

**Watch out for `null`:** The bootstrap loader is represented as `null` in `Class.getClassLoader()`. Two classes having a null loader do not by themselves let you conclude everything about type identity if you have not inspected their names/modules; however, for `String.class`, this is expected bootstrap behavior.

### Do Not Look Only at the JAR Name

Two URLClassLoaders can read **the exact same `plugin.jar`** yet create two implementation classes that are incompatible with each other. Conversely, two classes read from two different JARs can both implement **the same host API** and both be cast to that interface.

`CodeSource.location` helps debug the artifact/version, but **does not replace** comparing defining-loader identity. For generated classes, custom loaders, or JDK runtime classes, `CodeSource` can be `null`.

### JVM Class Loading Logs

With OpenJDK/HotSpot Java 17+:

```bash
java -Xlog:class+load=info -cp "build/app:build/host" LoaderIdentityDemo
```

This is the Linux/macOS command; on Windows, replace `:` with `;`. `-Xlog:class+load=info` prints many additional lines to the output, which can indicate the source JAR/directory/loader; the command **does not produce the exact same stdout as section 6** due to detailed logging.

Logging the source path helps identify the artifact, but to know which **loader instance** the running class belongs to, you need to combine `getClassLoader()`, object identity, and debugger/heap data. `-Xlog` is a HotSpot/Unified Logging option, not a guaranteed API across all JVM vendors.

## 11. Similar-Looking Causes with Different Fixes

| Symptom | Possible Cause | How to Distinguish |
| --- | --- | --- |
| `ClassCastException` despite identical names | Two defining loaders define the same binary name. | Compare `Class<?> ==` and `getClassLoader()`. |
| `ClassCastException` between two different names | Two ordinary unrelated types. | Check actual/expected names and hierarchy first. |
| `NoClassDefFoundError` when loading a plugin | API/dependency class is missing or its definition cannot be found. | Check the cause, loader search/delegation, and JAR. |
| `ClassNotFoundException` during `Class.forName` | Caller picked the wrong loader or the dependency is absent. | Pass the right loader, check the loader hierarchy/classpath. |
| `LinkageError` "loader constraint violation" | The JVM detects that two loaders resolve the same type inconsistently in a signature/override context. | Inspect offending class names, method descriptors, and loader identities. |
| `NoSuchMethodError` | API binary version mismatch; method signature changed. | Compare the API contract/version and `javap` signatures. |
| `AbstractMethodError` | Implementation does not match the interface/abstract method expected at runtime. | Rebuild the plugin against the matching binary contract. |
| `IllegalAccessError` / `InaccessibleObjectException` | Java/JPMS access policies or reflection boundaries. | Check module readability/exports/opens; distinct from type identity errors. |
| Duplicate class definition `LinkageError` | **The same loader** attempts to define a binary name again. | Check `findLoadedClass`/`getClassLoadingLock` and the `loadClass` override. |
| `UnsupportedClassVersionError` | Runtime JVM does not support the class-file major/minor version. | Read the bytecode/JDK version; not a cast issue. |

Do not fix this by catching `ClassCastException` and ignoring it; that only hides the architectural flaw and can leave the plugin partially working.

### Loader Constraint Violation Is Not the Same as a Cast Error

Java linking enforces **loading constraints** for types appearing in inherited method signatures or linkage situations that require consistent type identity across loaders. If one loader has already loaded the name `api.Message` as class A, while a related hierarchy requires the same name to be seen as class B, the JVM can throw `LinkageError` right when checking constraints.

`ClassCastException` is a cast error for an incompatible object; `LinkageError` can appear earlier during loading/linking. Both phenomena share the same root cause of "same-named class across different loaders," but **they are not the same exception subtype**.

## 12. Notes on ServiceLoader, TCCL, and Framework Containers

`ServiceLoader` can be used to locate plugin providers, but you must ensure that the **service interface** comes from a loader visible to both the host and provider with the same identity.

Example of the expected contract:

```java
ServiceLoader<Message> services =
        ServiceLoader.load(Message.class, pluginLoader);
```

This is a **snippet** that requires `import java.util.ServiceLoader;` along with the `pluginLoader` variable. It also requires valid service registration metadata (`META-INF/services/api.Message`) or proper module `provides`/`uses` declarations. Even if `ServiceLoader` finds the provider class, if the provider implements **an API copy from a different loader**, it can fail because it is not a subtype of the service.

Some containers use the thread context class loader (TCCL) to select a provider/dependency:

```java
Thread t = Thread.currentThread();
ClassLoader old = t.getContextClassLoader();
try {
    t.setContextClassLoader(pluginLoader);
    // Perform provider lookup / plugin call...
} finally {
    t.setContextClassLoader(old);
}
```

The TCCL changes **the lookup context** for APIs that support it; it **does not redefine** the `api.Message` copy already loaded by the host. Changing the TCCL also does not turn an improperly defined `impl.HelloPlugin` into a subtype of the host interface.

Application servers (Tomcat, Jakarta EE), OSGi, Spring Boot DevTools, or plugin frameworks have custom loader hierarchies. You should inspect the specific topology rather than assuming every loader is parent-first or every dependency resides on the system classpath.

## 13. Hot Reload Lifecycle: Avoiding Casts Across an Old Generation

In a hot-reloading plugin system:

```text
Generation 1:
    loader-v1 -> impl.HelloPlugin (runtime type 1)

Generation 2:
    loader-v2 -> impl.HelloPlugin (runtime type 2)

Host:
    api.Message -> defined once, lives across generations
```

An `impl.HelloPlugin` object from loader-v1 **cannot** be cast to the concrete type from loader-v2, even when both share the same source. However, both can be cast to `api.Message` if the API lives in the host loader and is binary-compatible.

To unload an old generation:

1. Prevent new tasks from using old implementation objects.
2. Unregister event handlers, service provider references, and caches holding `Class<?>`/plugin instances.
3. Stop tasks and clean up TCCL/ThreadLocal entries that might retain the old loader.
4. Close the `URLClassLoader` if it is a type that supports `close`.
5. Drop host references to objects/`Class<?>`/loader of the old generation.
6. Observe reachability/GC if needed, without assuming that class unloading happens immediately.

`URLClassLoader.close()` **does not delete already-loaded classes**, does not fix type identity, and does not "coerce" an old instance into a new generation. It closes the loader's resources per the API; to replace an implementation, create a new loader and update references at the application layer.

### Do Not Pass Implementation Objects Across the Boundary as Public API Types

If the host API declares:

```java
public interface Message {
    String message();
}
```

this is a safe contract in the demo because it only uses Java's runtime `String`, which is shared by the host and plugin.

However, if the API returns `impl.HelloPlugin` or a `plugin.private.Data` type defined by the child loader, the host may not be able to resolve or cast that type. Design the public plugin contract using **types from the host/shared API or Java/JDK types** with a unified identity; use an appropriate DTO/boundary protocol when deeper isolation is needed.

Generic type parameters also require attention: `List<PluginImpl>` can still carry instances of a class defined by the plugin loader; **type erasure does not turn implementation types into shared types** and can throw a cast error where elements are read.

## 14. Anti-Patterns and Practical Fixes

| Mistake | Why It Fails | Fix |
| --- | --- | --- |
| "Same binary name means it can be cast." | Missing defining loader identity. | Compare `Class<?>` and loader; use a shared abstraction. |
| "Same JAR bytes means same Class." | Two loader instances still create two namespaces. | Create a single loader when the exact same concrete type is truly needed, or use a shared API. |
| Packaging `plugin-api.jar` into both host and child-first plugin | Two runtime copies of `api.Message`. | Provided/compileOnly API; parent-first API namespace. |
| Using child-first for both `api.*` and `impl.*` | The plugin defines its own API instead of using the host API. | Selective child-first for implementation deps; host API always parent-first. |
| Only deleting the API file from the plugin JAR after the JVM has loaded it | An already-defined class does not replace itself. | Create a new class loader generation/restart and rebuild the artifact. |
| Using reflection as a "fix" for type identity | Only invokes methods via reflection; does not create real subtyping. | Shared interface or explicit data transfer boundary. |
| Casting `ClassLoader.getSystemClassLoader()` to `URLClassLoader` | In Java 9+, the system loader is generally not a URLClassLoader. | Use an appropriate API or a custom loader of the right type. |
| Seeing identical `CodeSource.location` and ignoring the loader | Archive/path does not determine Class identity. | Inspect `getClassLoader()` directly. |
| Changing TCCL and expecting the old cast to succeed | TCCL does not alter an already-defined class. | Fix the owner loader/API hierarchy and reload the generation. |
| Repeating `defineClass` with the same name and loader | The JVM rejects duplicate class definitions. | `findLoadedClass` and proper locking/loader policy. |
| Disabling JPMS/`--add-opens` to fix `ClassCastException` | Opening reflective access does not merge Class identities. | Fix the API definition/loader graph. |
| Checking only with `instanceof` against a host-linked class | May return false without revealing the loader issue. | Log expected/actual `Class<?>` + loaders + modules. |

## 15. Step-by-Step Checklist When a Plugin Fails to Cast

1. **Read the exact error.** Confirm whether it is truly `ClassCastException`, a `LinkageError` loader constraint, or another error.
2. **Record the expected class:** binary name, `Class<?>` object, defining loader, module, version.
3. **Record the actual class:** `object.getClass()`, name, loader, module, and source location if available.
4. **Compare using `==`**, not just `getName()` or `toString()`.
5. **Check the shared API:** whether `HostApi.class == pluginClass.getInterfaces()[...]` matches, or use `HostApi.class.isAssignableFrom(pluginClass)`.
6. **Inspect the JAR:** was a copy of `api.*` copied into the plugin by shading/assembly/the loader?
7. **Check delegation:** is the host API parent-first, and is child-first accidentally shadowing shared packages?
8. **Inspect runtime state:** which dependency/JAR is actually being loaded; verify parent loader vs child loader.
9. **Fix build/deployment:** remove the duplicate API from the plugin artifact, pin the API version, and share the shared loader.
10. **Replace the loader generation:** do not expect an already-defined runtime type to transform itself.
11. **Run integration tests** with at least two child loader instances and two plugin versions if the project supports hot reload.
12. **Manage the lifecycle** so old instances/caches are not carried over to the new generation.

Do not consider matching plugin JAR checksums sufficient; checksums verify bytes, whereas the issue lies in **defining loader identity**.

## 16. Self-Check Exercises and Answers

1. **Two separate loaders both read the same `dup.Token.class` file; why are the `Class<?>` objects different?**  
   Runtime identity consists of the binary name and the defining loader; two independent loader instances define two runtime types.

2. **Does having the same `Class.getName()` for A and B prove that a cast is valid?**  
   No. Compare identity `A == B` or the `isAssignableFrom` relationship.

3. **If the same loader calls `loadClass("dup.Token")` multiple times, does it create multiple classes?**  
   On the standard path, `findLoadedClass` and synchronization prevent redefinition; a single `Class<?>` is returned for the appropriate name/loader.

4. **When two implementations come from two different plugin loaders, can casting both to the same host interface succeed?**  
   Yes, if both implement the exact **same** runtime interface defined by the parent/host.

5. **If a plugin JAR contains a duplicate copy of the API, but parent-first API lookup returns the host API, can the cast succeed?**  
   Yes, it can. The duplicate copy in the JAR remains a design/packaging risk; if child-first is used or the hierarchy changes, it can fail.

6. **Why is `Message.class.isAssignableFrom(pluginClass)` false in `DuplicateApiDemo`?**  
   The plugin implements `api.Message` defined by the child loader; the host's `Message.class` has a different defining loader.

7. **Does changing only the TCCL turn a child API class into the host API?**  
   No. The TCCL only assists lookup in APIs that use it; it does not modify an existing Class identity.

8. **Does an identical `CodeSource.location` mean two runtime classes are the same?**  
   No. The same JAR can be loaded by multiple child loader instances.

9. **Does `URLClassLoader.close()` make an old instance castable to a new version of the class?**  
   No. Closing does not redefine classes and does not change type identity.

10. **An application needs two plugins to use different dependency versions; should their implementations be cast to one another?**  
    No. Use a shared host API, DTOs, or an explicit protocol.

11. **Are `ClassCastException` and a duplicate definition `LinkageError` the same?**  
    No. ClassCastException is an invalid cast; duplicate definition occurs when the same defining loader attempts to define the same name twice; loader constraint errors belong to linking.

12. **In Maven/Gradle, how do you reduce the risk of redundantly packaging the host API?**  
    Use `provided` or `compileOnly` respectively, inspect the final JAR, and keep the API namespace parent-first.

13. **Why is it necessary to test on the production loader topology?**  
    Unit tests using a single app loader can mask class identity mismatches that occur with custom child loaders.

14. **What problem occurs when an API contract takes a parameter belonging to a plugin's private package?**  
    The host may not be able to resolve the same class identity for that type; the public boundary should use shared/host types.

## 17. Official Documentation

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findClass`, `findLoadedClass`, `defineClass`, and defining loader.
- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity is binary name + defining loader; initiating vs defining loader and loading constraints.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `cast`, `isInstance`, `isAssignableFrom`, `getClassLoader`, `getModule`.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): constructors, URL sources, `close`.
- [Java SE 21 — ClassCastException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassCastException.html): meaning of a failed cast.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): SPI service/provider identity and loader.
- [Java SE 21 — Package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html): runtime packages and package metadata.
