# Do Not Use a Class Loader to Reload the Class Currently Being Transformed

In Java Instrumentation, when the JVM calls `ClassFileTransformer.transform(...)` to process a class, that class **may be in the middle of being defined**. At this point, the transformer already has the **internal name of the class** (`className`), the **class loader defining it** (`loader`), and the **input bytecode** (`classfileBuffer`). The transformer **does not need to** and **should not** call `loader.loadClass(...)` or `Class.forName(...)` to "reload" the very class being transformed.

This principle belongs to the topic **Class loaders and helpers**: avoid pulling the target class back into the class loading process when that process has not yet completed; separate agent helper code from business classes; process bytecode from the data the JVM passed in instead of looking up a new `Class<?>` via a loader.

After this lesson, you will be able to distinguish: **a loader received as context information** and **a loader invoked to load a class** are two different things; why "reloading" can lead to reentrancy, dependency cycles, or hangs; when `classBeingRedefined` can be used; why a helper visible from the agent is not necessarily visible from an instrumented application class; and how to write a JDK 17+ Java agent that can be safely tested.

## 1. The class loading flow and the position of the transform callback

Consider an application that needs to load `lab.app.TargetService`. A simplified flow:

~~~text
Application requests to use lab.app.TargetService
        |
        v
Class loader locates the bytes defining the class
        |
        v
ClassLoader.defineClass(...) or equivalent mechanism
        |
        v
JVM runs the ClassFileTransformer.transform(...) chain
        |       Parameters already available:
        |       - className = "lab/app/TargetService"
        |       - loader = defining class loader
        |       - classfileBuffer = bytes to process
        |
        v
JVM verifies and defines the class from the final result
        |
        v
Class can be linked and initialized when needed
        |
        v
Application executes the class code
~~~

This is a **conceptual** diagram, not a promise that every JVM executes every step in the exact micro-order in every situation. What **is guaranteed by the API** is that the transformer is called during definition/redefinition/retransformation and **before the final bytes are verified or applied**.

A wrong call inside the callback:

~~~java
Class<?> target = loader.loadClass("lab.app.TargetService"); // DO NOT DO THIS
~~~

may ask that same loader to process again the name it is **currently defining**. The class does not necessarily appear yet as a `Class<?>` recorded by the loader. The outcome depends on the loader/JVM/state: reentrant loading, an uncontrollable chain of class dependencies, linkage errors, or deadlocks may occur. **Do not claim that every call will certainly throw the same exception**; the loading request itself at this point is the design problem.

### Core rule

**Use `className` to decide whether to transform the class; use `classfileBuffer` to read and modify bytecode. Do not reach back into the class loader to obtain the `Class<?>` currently being defined.**

If the transformer does not need to modify anything, return `null`. If modification is needed, create a **new byte array** from the received data; do not overwrite `classfileBuffer` in place.

## 2. loadClass is not a "reload class" API

The name `ClassLoader.loadClass(String)` sometimes leads learners to think that each call re-reads the `.class` file and creates a new definition. That is **not** the API contract.

In the default implementation, `ClassLoader.loadClass(name, resolve)` typically performs:

1. Uses `findLoadedClass(name)` to find a class **already recorded by the loader** under that name.
2. If not found, attempts to **delegate to the parent loader** according to delegation.
3. If the parent cannot find it, attempts `findClass(name)` on the current loader.
4. May link (*resolve*) the class according to the parameter and return a `Class<?>`.

`ClassLoader` subclasses may have different strategies (child-first, plugin isolation, module layer, dynamic bytecode), but there is **no** standard Java mechanism to "revert an old class back to an never-loaded state" using `loadClass` alone.

### Before, during, and after definition are different

| Timing | What does calling `loader.loadClass(targetName)` mean? | Should it be done in a transformer? |
| --- | --- | --- |
| **Before** the class is requested to load | May start loading/defining the class | Do not use as a preparation step from the callback |
| **During** the class definition callback | May re-request the same class whose definition is incomplete, creating dependencies/reentrancy | **No** |
| **After** class definition finishes | Usually returns the existing `Class<?>` or delegates; does not "reload" the definition | Unnecessary for the transform that just finished |
| **During redefine/retransform** of an already loaded class | The class already exists and the callback may be passed `classBeingRedefined` | **No need** to call the loader to look it up again |

Therefore, even if calling `loadClass` for an already loaded class can return normally, that does not prove it is safe or useful **while transforming that very class**. Reading the class bytes already provided as input is both clearer and avoids depending on loader state.

### Class names must use the right format

`className` from `ClassFileTransformer` is in **internal name** form:

~~~text
lab/app/TargetService
java/util/ArrayList
~~~

Whereas `ClassLoader.loadClass(String)` uses **binary name** form:

~~~text
lab.app.TargetService
java.util.ArrayList
~~~

If the transformer only needs to filter targets, do not convert to a binary name and call the loader. Just compare the internal name:

~~~java
if (!"lab/app/TargetService".equals(className)) {
    return null;
}
~~~

Putting the literal on the left is also safe when `className == null`. In special class scenarios, especially some runtime-generated definitions, you must not assume every callback has an ordinary class name.

## 3. Why is reloading the target inside the callback risky?

### 3.1. Reentrant class loading

While defining A, the JVM invokes the transformer for A. If the transformer in turn requests loading A through the loader, we have a logical dependency chain:

~~~text
Loader is defining A
       |
       v
transform(A)
       |
       v
loader.loadClass(A)
       |
       +----> May return to the same unfinished process
                    |
                    +----> cyclic dependency / recursion / loading error
~~~

Not every loader and every situation produces the exact same recursion; by default, loaders have mechanisms to check already-loaded classes and synchronize with locks. However, **a class currently being defined** is not necessarily published yet as a completed class ready to be returned to another request. Do not rely on an implementation-dependent behavior to avoid cycles.

### 3.2. Class loading locks and deadlocks

`ClassLoader.loadClass` synchronizes by default using the lock returned by `getClassLoadingLock(name)`. Some custom loaders that are not registered as *parallel capable* lock at the loader level; others may use per-name locks. If a callback requests additional classes while holding a lock, it can create additional lock-wait relationships, especially when multiple loaders depend on each other or two threads are concurrently loading classes with circular dependencies.

An example of the risk, **not every JVM scenario will hang**:

~~~text
Thread-1 holds lock on loader-X while defining A
       |
       +-- transform(A) wants to load B using loader-Y

Thread-2 holds lock on loader-Y while defining B
       |
       +-- transform(B) wants to load A using loader-X

=> Risk of circular wait; JVM/custom loader may throw an error or hang.
~~~

There is no guarantee that adding `synchronized` or `ThreadLocal<Boolean> inTransform` to the agent solves every risk: a per-thread guard does not control wait cycles **across threads** or **across loaders**.

### 3.3. Linkage errors and class identity

A class in the JVM is identified at runtime by its **binary name plus defining class loader**. A different loader can define a class with the **same name** that is **a different runtime class**. If a transformer tries to redefine via `defineClass` in the same loader or uses another loader to find a "copy" of the target, the consequences may include:

- `LinkageError`-type errors when attempting duplicate definition in circumstances the JVM does not allow.
- Class cast or linkage failures because two loaders define types with the same name but different identities.
- Resources/class bytes found from a different source than the bytes the JVM is transforming.
- Unpredictable class loading synchronization in plugin applications, application servers, or OSGi-like environments.

**Note on `ClassCircularityError`:** this exception is used by the JVM when it detects a cycle in the superclass hierarchy during loading; **not every `loadClass` call inside a transformer throws `ClassCircularityError`**. When documenting errors, prefer "may lead to class-loading/linkage problems" rather than promising a fixed exception.

### 3.4. Unintentionally initializing application classes

`Class.forName(binaryName)` is a call that can load **and initialize** a class in the caller's context. Meanwhile, the overload `Class.forName(name, false, loader)` does not request initialization, but **may still have to load/link the class**. Therefore:

~~~java
Class.forName("lab.app.TargetService", true, loader);  // WRONG in transform(A)
Class.forName("lab.app.TargetService", false, loader); // Also should not be used in transform(A)
~~~

Passing `false` **does not solve the problem of defining A**; it only controls the initialization request. Static initializer `<clinit>`, auxiliary class loading, and module linkage are all separate concerns from analyzing the existing bytes.

## 4. Reading ClassFileTransformer parameters properly

The commonly used Java 17+ signature:

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // No need for loader.loadClass(className).
    return null;
}
~~~

This is a **code snippet that must be placed in a class implementing `ClassFileTransformer`**, not a standalone runnable program.

| Parameter | What can it be used for? | What it should not be misunderstood as |
| --- | --- | --- |
| `module` | Identify the module associated with the class to transform; filter by scope when needed | Automatic access to every package/private API |
| `loader` | Know the **defining loader**; distinguish bootstrap (`null`), app, or plugin loader | An invitation to call `loader.loadClass(target)` in the callback |
| `className` | Filter by internal name, e.g., `"lab/app/TargetService"` | A binary name to pass verbatim to `loadClass` |
| `classBeingRedefined` | During redefine/retransform, indicates the existing `Class<?>` itself; on fresh load it is `null` | A Class object required to be non-null in every callback |
| `protectionDomain` | Metadata about the protection domain of the class being defined/redefined | A mechanism for the agent to bypass all JVM/module protections |
| `classfileBuffer` | **The exact input at this transform step** to parse and emit new bytes | An array allowed to be modified directly or always identical to the `.class` file on disk |

The `ClassFileTransformer` contract requires: if no change is needed, return `null`; if a change is needed, create a **new byte array** and return valid class file bytes. The `classfileBuffer` array passed in **must not be modified in place**.

When there are multiple transformers, the input bytes of one transformer may have already been modified by a previous transformer. Reading `getResourceAsStream("...class")` or a file from disk yourself and treating it as the "original" can easily lose valid transformations performed before your step.

### What when classBeingRedefined is non-null?

On a **fresh load**, the JVM is constructing the class, so `classBeingRedefined == null` by the API. During **redefinition** or **retransformation**, this is the `Class<?>` reference currently being modified.

In that case, if you need to know the target's runtime identity, you already have that object:

~~~java
if (classBeingRedefined != null) {
    ClassLoader definingLoader = classBeingRedefined.getClassLoader();
    // Only obtain metadata; do not call definingLoader.loadClass(targetName).
}
~~~

This is an **illustrative snippet**, not advice to invoke reflective methods or application logic inside the callback. And `classBeingRedefined != null` is **not enough** to distinguish redefine from retransform: both events can pass this reference.

## 5. Typical bad code: looking up the target via the loader

**Do not run the snippet below as a Java agent**. It is a negative example to help recognize the anti-pattern:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {
    if (!"lab/app/TargetService".equals(className)) {
        return null;
    }

    try {
        // WRONG: the callback is currently processing TargetService itself.
        Class<?> target = loader.loadClass("lab.app.TargetService");
        System.out.println(target.getDeclaredMethods().length);
    } catch (ClassNotFoundException e) {
        throw new IllegalStateException(e);
    }
    return null;
}
~~~

The problems:

1. The callback for `TargetService` is called when the class may **not have finished being defined**. A nested `loadClass(TargetService)` request can re-enter the loading flow.
2. `getDeclaredMethods()` also triggers the need to read/resolve additional metadata about declared method types; it is not the only way to analyze bytecode.
3. If `loader == null` (bootstrap), the code throws `NullPointerException` before even reaching the load step.
4. With a custom/child-first loader, the risk of cross-dependencies, deadlocks, or loading the wrong type becomes even harder to control.
5. If an agent callback throws an exception, the JVM may still continue the transformer chain according to the contract. "Throw an exception to stop the pipeline and roll everything back" is not a reliable strategy.

**Do not fix it by changing to `Class.forName("lab.app.TargetService", false, loader)`.** It still requests class loading. Also do not fix it by switching to the system class loader: it may not be the loader actually defining the target, leading to **a different class identity or the class not being found**.

## 6. Correct code: filter by name and read the available bytes

Minimal transformer:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {

    if (!"lab/app/TargetService".equals(className)) {
        return null;
    }

    boolean hasClassMagic = classfileBuffer.length >= 4
            && (classfileBuffer[0] & 0xFF) == 0xCA
            && (classfileBuffer[1] & 0xFF) == 0xFE
            && (classfileBuffer[2] & 0xFF) == 0xBA
            && (classfileBuffer[3] & 0xFF) == 0xBE;

    // If only observing or filtering, there is no need to create a new byte array.
    return null;
}
~~~

This is a **code snippet** illustrating the principle, not a complete class. Checking `CAFEBABE` on the first four bytes is a **magic header** check, **not proof that the entire class file is valid**. Actual structural verification should be delegated to a standard class file parser.

For real bytecode transformation:

~~~text
Do:
    classfileBuffer -> parser/class model -> transform -> new bytes -> return

Do not do:
    className -> loader.loadClass(className) -> reflection on target
              -> try to recreate bytes or define target again
~~~

In Java 17, you can use ASM or another bytecode library to parse the received bytes; with JDK 24+, `java.lang.classfile.ClassFile.of().parse(classfileBuffer)` is a standard option. The JDK 24 API is **not available in JDK 17/21 as a stable API**, so if a project needs to support Java 17, choose a compatible library or separate implementations by version.

## 7. Runnable Java 17+ example: agent does not reload the target class

The full example uses **two separate code areas**:

- **Agent** contains `lab.agent.SafeLoadingAgent`, which registers the transformer.
- **Application** contains `lab.app.TargetService` and `lab.app.RunDemo`. Only the application actively requests loading the target.

To prove **the callback already has enough information**, the transformer logs the class name per the filter condition, whether the loader is bootstrap, the state of `classBeingRedefined`, and the magic bytes. It **does not** call `Class.forName`, `ClassLoader.loadClass`, or the class literal `TargetService.class` inside the callback. The agent returns `null`, so this is a **safe inspection/observation demo**, not yet modifying bytecode.

### 7.1. Directory structure

~~~text
safe-loader-demo/
├── agent-src/
│   └── lab/agent/SafeLoadingAgent.java
├── app-src/
│   └── lab/app/TargetService.java
│   └── lab/app/RunDemo.java
└── agent.mf
~~~

The `agent-bin` and `app-bin` directories are created during compilation. Separating the agent JAR from the app classpath makes it clear to verify that **the target class is not directly referenced by the agent as a Java type**.

### 7.2. File agent-src/lab/agent/SafeLoadingAgent.java

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class SafeLoadingAgent {
    public static void premain(String args, Instrumentation instrumentation) {
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if (!"lab/app/TargetService".equals(className)) {
                    return null;
                }

                // No Class.forName, no loader.loadClass, no target class literal!
                boolean magicOK = classfileBuffer.length >= 4
                        && (classfileBuffer[0] & 0xFF) == 0xCA
                        && (classfileBuffer[1] & 0xFF) == 0xFE
                        && (classfileBuffer[2] & 0xFF) == 0xBA
                        && (classfileBuffer[3] & 0xFF) == 0xBE;

                System.out.println("transformTarget=true");
                System.out.println("loaderIsBootstrap=" + (loader == null));
                System.out.println("classBeingRedefinedIsNull="
                        + (classBeingRedefined == null));
                System.out.println("magicOK=" + magicOK);
                return null; // Observe only, do not modify bytes.
            }
        });

        System.out.println("agentRegistered=true");
    }
}
~~~

**Key points:**

1. `premain` is called by the JVM at startup with `-javaagent:safe-agent.jar`. The transformer callback is registered **before** `RunDemo.main()` requests loading `TargetService`.
2. The filter branch `"lab/app/TargetService".equals(className)` runs **first**; unrelated classes pass through via `return null`, reducing overhead and the risk of loading unnecessary helpers.
3. The program does not call any methods on `loader`; it only checks `loader == null` to identify the bootstrap loader.
4. `classfileBuffer` is treated as **read-only**. Byte checks use `& 0xFF` because Java `byte` is signed; there is no need to clone bytes if not modifying them.
5. In the demo, `System.out.println` helps learners observe the callback. In production, logging directly inside a transformer must be rate-limited/sampled and avoid loading complex logging systems.
6. The agent places itself in package `lab.agent`; it does not import or reference `lab.app.TargetService` via a class literal. This reduces coupling between agent helpers and the target.

### 7.3. File app-src/lab/app/TargetService.java

~~~java
package lab.app;

public final class TargetService {
    static {
        System.out.println("targetClinit=true");
    }

    public static String message() {
        return "hello";
    }
}
~~~

The message `targetClinit=true` is printed when the class **initializes**. This event must be distinguished from **loading/defining** the class; the JVM can define a class before initializing it.

### 7.4. File app-src/lab/app/RunDemo.java

~~~java
package lab.app;

public final class RunDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("appBeforeLoad=true");

        ClassLoader appLoader = RunDemo.class.getClassLoader();
        Class<?> target = Class.forName(
                "lab.app.TargetService", false, appLoader);

        System.out.println("loadedWithoutInitializing=true");
        System.out.println("sameLoader="
                + (target.getClassLoader() == appLoader));

        Class.forName("lab.app.TargetService", true, appLoader);
        System.out.println("message="
                + target.getMethod("message").invoke(null));
    }
}
~~~

**Why does this not violate the lesson's principle?** `Class.forName(...)` above is called from **application code `main`**, **outside the `transform` callback**, and is itself the initial load request that the transformer needs to observe. It is not the transformer defining the target and suddenly requesting to reload the target. `Class.forName(name, false, loader)` only requests appropriate loading/linking **without initializing**. The subsequent call with `true` requests normal initialization.

Point to remember: *the application is not forbidden from loading classes*; **the forbidden anti-pattern is "a transformer calling a loader to reload the very class currently being transformed"**.

### 7.5. File agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.SafeLoadingAgent
~~~

The manifest needs a **trailing blank line**. The demo uses a load-time transformer registered via `addTransformer(transformer)`, equivalent to `canRetransform=false`; no retransform/redefine capabilities are needed because neither operation is performed.

### 7.6. Compile with JDK 17+ and run

Bash commands (Linux/macOS or Git Bash). Source directories must be created as in section 7.1:

~~~bash
mkdir -p agent-bin app-bin
javac --release 17 -d agent-bin agent-src/lab/agent/SafeLoadingAgent.java
javac --release 17 -d app-bin app-src/lab/app/TargetService.java app-src/lab/app/RunDemo.java
jar --create --file safe-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:safe-agent.jar -cp app-bin lab.app.RunDemo
~~~

Corresponding Windows PowerShell commands to create the two output directories:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin | Out-Null
javac --release 17 -d agent-bin agent-src/lab/agent/SafeLoadingAgent.java
javac --release 17 -d app-bin app-src/lab/app/TargetService.java app-src/lab/app/RunDemo.java
jar --create --file safe-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:safe-agent.jar -cp app-bin lab.app.RunDemo
~~~

`javac --release 17` compiles against the Java 17 API/class-file target. The JAR contains the entire `lab.agent` package, including the anonymous class generated by the compiler for the transformer (e.g., `SafeLoadingAgent$1.class`). Do not package only `SafeLoadingAgent.class` and forget the transformer implementation class.

**Stdout compiled/run and verified on Zulu OpenJDK 24, with `--release 17`:**

~~~text
agentRegistered=true
appBeforeLoad=true
transformTarget=true
loaderIsBootstrap=false
classBeingRedefinedIsNull=true
magicOK=true
loadedWithoutInitializing=true
sameLoader=true
targetClinit=true
message=hello
~~~

**Reading the output:**

- `agentRegistered=true`: the transformer was registered before the app requested to load the target.
- `appBeforeLoad=true`: the application begins the class loading operation.
- `transformTarget=true`: the callback was invoked for the right class; not because the agent loaded the target itself.
- `loaderIsBootstrap=false`: in this app class loader example, `loader` is not `null`. **Do not generalize** that every target has a non-null loader.
- `classBeingRedefinedIsNull=true`: this is a **first-time class definition**, not a redefine/retransform.
- `magicOK=true`: the `CAFEBABE` header bytes are present in the input that **the JVM passed to the transformer**.
- `loadedWithoutInitializing=true` then `targetClinit=true`: shows the phase where the class was loaded without running the initializer yet, followed by the application actively requesting initialization.
- `sameLoader=true`: the class was loaded through the application loader as configured in the scenario.
- `message=hello`: no transformer modified bytecode, and the application still works normally.

This demo does not prove that logging inside a callback is always immune to all class-loading side effects. It proves **the target processing path** does not call a loader to load the target itself and runs on a specific test environment.

## 8. What to do if real bytecode transformation is needed?

To transform a method in the target, use the bytes the JVM passes in instead of reflecting on the target while it is being defined.

### 8.1. Use a bytecode parsing library supporting the Java version

With ASM (requires a compatible ASM dependency), a model-creation step can be:

~~~java
org.objectweb.asm.ClassReader reader =
        new org.objectweb.asm.ClassReader(classfileBuffer);
~~~

This is a **code snippet**, not standalone Java to copy-and-run with a plain JDK. `ClassReader` parses a **class byte array**, without needing a `Class<?>` of the target. To modify the class, create the appropriate transformer/visitor and `ClassWriter`, then return the new `byte[]` from `ClassWriter.toByteArray()`.

In JDK 24+, the official Class-File API also provides:

~~~java
java.lang.classfile.ClassModel model =
        java.lang.classfile.ClassFile.of().parse(classfileBuffer);
~~~

This is a **snippet requiring JDK 24+**, not valid on Java 17/21 as a stable API. It also does not need `loader.loadClass(target)` just to parse class bytes.

### 8.2. Be careful when tools need to compute hierarchy or frames

Even though a direct parser does not need to load the target, some utilities that compute hierarchy or common superclasses may **look up/resolve other classes themselves**. For example, an ASM mode that computes frames may need inheritance relationship information, depending on how the writer is configured. If a framework uses class loading to obtain metadata, you still need a strategy:

- Use metadata/class bytes of existing dependencies or controlled resource lookups.
- Avoid requesting to load **the very target currently being transformed**.
- Do not assume the system loader sees the types of a plugin class loader.
- For complex hierarchies, use an appropriate type pool/metadata cache and test across multiple loaders/modules.
- Do not blindly use the target class loader for reflection just because checking superclasses is convenient.

**Separating concepts:** "Do not load the target with the loader" **does not mean** you may never know which loader is defining it. `loader` remains valuable for scoping and safely resolving needed metadata.

### 8.3. Returning null and new arrays

| Callback result | JVM handling |
| --- | --- |
| `return null` | Does not change bytes at this step; subsequent transformers receive the existing bytes |
| `return newClassBytes` | JVM passes the new bytes to the next transformer; at the end of the pipeline, verifies/applies them |
| Modifying `classfileBuffer` directly | **Violates API contract**; must create a new byte array |
| Returning malformed bytes | May be rejected by the JVM after the pipeline |
| Throwing an exception from the transformer | Does not automatically abort the entire pipeline; per contract, subsequent transformers may still be called |

If you only want to collect metrics on how many times classes are loaded, you **do not need** to return a copy of the input. If you want to change content, ensure the output is valid; avoiding `loader.loadClass` solves one risk, not the bytecode verification process.

## 9. Agent helpers: avoiding dependencies on the target being loaded

A common reason a transformer tries to load the target is **a helper having a back-reference to an application class**. For example:

~~~java
public final class AgentHelper {
    public static void record() {
        // Bad design if the helper is called while TargetService is loading:
        // TargetService.someStaticMethod();
    }
}
~~~

This is an **illustrative snippet**, not a standalone runnable class because `TargetService` is not declared here. The issue is the helper calling target code or loading the target to read annotations/metadata while the target **has not finished being defined**.

Better design:

- The helper accepts **neutral data** such as internal name strings, descriptors, timestamps, and raw numbers.
- The transformer processes `classfileBuffer` inside the callback without needing to instantiate target objects.
- Limit helper static initializers from triggering loading of application packages.
- Load/initialize essential agent libraries **before registering the transformer**, if possible, while avoiding preloading the target itself or business classes to be observed.
- Exclude agent/logger/bytecode tooling packages from transformation scope if there is no need to monitor them.
- When a helper needs to be called from **an instrumented method**, ensure the helper can be accessed by **that method's loader** after the class is defined.

### Two distinct helper problems

**Problem A — helper running inside the agent callback:** it needs to be ready while the JVM is defining the class. If the helper itself references the target, it can create a loading dependency cycle.

**Problem B — helper called by bytecode injected into the application:** when the application method executes, the JVM resolves the helper reference according to loader/module/visibility relationships. The fact that the agent itself can load the helper **does not guarantee** every target class can resolve that helper.

For example, a `java.base` class defined by the bootstrap loader cannot by default access a helper that only exists in the application class loader. With multiple isolated plugin loaders, classes with the same name may also resolve helpers along different paths.

## 10. Making helpers visible without loading the target yourself

Practical organization approaches:

| Helper placement | When appropriate | Points to note |
| --- | --- | --- |
| Helper is in the agent JAR, visible to system/application loader | Instrumenting simple application classes | Custom loaders may not delegate to the system helper |
| Helper is in a separate JAR and added to bootstrap search | Need targets from bootstrap or multiple loaders to access the helper | Put only minimal classes into bootstrap to avoid split packages/conflicts |
| Add helper to system loader search | Need to extend classes found by the system loader | Does not guarantee every child-first/custom loader uses it |
| Do not inject helper calls into target, only analyze bytecode | Pure metadata probes and self-contained transforms | No need to resolve helpers at runtime |
| Use a bridge mechanism with a clear module/loader contract | Multi-module/plugin applications | Must test module reads/exports/opens, identity, and lifecycle |

Available APIs:

~~~java
instrumentation.appendToBootstrapClassLoaderSearch(jarFile);
instrumentation.appendToSystemClassLoaderSearch(jarFile);
~~~

This is an **illustrative snippet**: `instrumentation` must be provided by the JVM, and `jarFile` is a valid `java.util.jar.JarFile`; a separate JAR must be prepared and errors handled. Do not use these merely to work around the issue of transforming a target; both methods **add locations to search for helpers**, they are not commands to "reload the target".

Oracle Javadoc warns that a JAR added to bootstrap **should contain only the classes/resources intended to be defined by the bootstrap loader**. Putting the entire agent/app JAR there can alter class resolution, causing package conflicts or hard-to-diagnose linkage issues.

Beyond loader visibility, the module system (JPMS) has **readability**, **exports**, and **opens** relationships. In some situations, an agent must arrange module relationships using `Instrumentation.redefineModule(...)`. That is a **helper access** problem, not permission for a transformer to reload the target currently being defined.

### Do not misuse Thread Context ClassLoader

`Thread.currentThread().getContextClassLoader()` (TCCL) can differ from the target's **defining loader**. Using TCCL to "look up" the class being transformed can easily return a class with the same name from a different environment, or fail to find the class at all. If you need to know which loader receives the bytecode, **the `loader` parameter already provides that information directly**. If you only need to filter by name, use `className`.

## 11. When is Class.forName or loader.loadClass valid?

Not all class loading in Java is wrong. This lesson's rule has a **very specific scope**: **while a transformer is processing a class, do not load that same class again yourself**.

Some other valid situations:

- Application code actively uses or loads a class **outside the callback**, as in the `RunDemo.main()` example.
- A plugin framework genuinely intends to load a class after the loader is ready and not inside the define chain of that same class.
- An agent actively finds an **already loaded** class to request `Instrumentation.retransformClasses(existingClass)` or `redefineClasses(...)` outside the callback, after checking capabilities and modifiability.
- An agent needs to prepare **independent helpers** before registering the transformer, without pulling observed targets into the preload process.

Even in these situations, distinguish class loader identity, class initialization, and system changes caused by class loading. The fundamental difference is **not re-entering the unfinished definition process of the target itself**.

### What if the class already exists in a retransform callback?

In redefine/retransform, `classBeingRedefined` already gives the target's `Class<?>`. You can use it to identify the class being modified within reasonable bounds. However, calling `Class.forName(...)` or `loader.loadClass(...)` for the target itself is still **redundant**, does not give you "the latest bytecode version", and can trigger auxiliary loading/linkage logic.

If you want to **read the bytes** currently being transformed, take them only from `classfileBuffer`. If you want to **modify** an already loaded class, do so with `retransformClasses`/`redefineClasses` at an **appropriate orchestration point outside the callback**, rather than nesting those two operations on the target itself while the JVM is still processing its transform.

## 12. Common errors and real-world causes

| Symptom | Possible cause | Adjustment |
| --- | --- | --- |
| JVM slow or hangs at startup with agent | Callback loads another/target class under class-loading lock; logger/helper loads classes nestedly | Filter classes at the start of callback; remove `loadClass(target)`; restrict helpers |
| `StackOverflowError` during class loading | Reentrant transformation or recursive helper | Break cycles; do not call back into target inside callback |
| `ClassNotFoundException` | Wrong system loader used, binary name/internal name confused, or class not yet defined | Compare `className`, use the right loader when truly needed outside callback |
| `NoClassDefFoundError` | Helper missing from classpath/loader used by instrumented bytecode; initialization failed | Place helper/bootstrap/module properly |
| `LinkageError` during define | Duplicate class definition or loader constraint violation | Do not `defineClass` target yourself; identify runtime identity properly |
| `ClassCastException` between two types with the same name | Class actually defined by two different loaders | Use the expected `Class<?>`/loader, do not create duplicates |
| Target callback not seen | Transformer registered after target already loaded, wrong filter, class belongs to another loader | Register early or retransform in a controlled way |
| `classBeingRedefined == null` | Loading a new definition | Use `className` and bytes; do not try to look up `Class<?>` |
| `loader == null` | Bootstrap-defined class | Do not dereference loader; place helper appropriately |
| `className == null` | Special class scenario defined by JVM/runtime | Write null-safe filters, use other metadata if available |
| Reading .class resource gives different result | Dynamically generated class, multi-release JAR, different resource, or earlier transformer modified bytes | Trust `classfileBuffer` for the current transform pass |
| Agent logs verifier error after returning bytes | Invalid bytecode output, wrong stack maps/frames | Use a bytecode parser/verifier and test on the target JDK |
| Module error after injecting helper call | Loader sees helper but JPMS read/export/open is incompatible | Design module linkage clearly, do not reload target |

**You cannot diagnose every `ClassCircularityError` as caused by the agent**: by JVM definition, it relates to detecting a superclass cycle. When loading/linkage errors occur, inspect the stack trace, active callbacks, and specific loader dependencies; avoid attributing one blanket cause to every error.

## 13. Designing safe filters and avoiding reentrancy

A production transformer typically has the structure:

~~~text
Start transform
    |
    +-- className null? --------------------> return null
    |
    +-- not in target package scope? -------> return null
    |
    +-- is agent/helper package? -----------> return null
    |
    +-- need any metadata? -----------------> read classfileBuffer
    |
    +-- parse/transform bytes with tool
    |
    +-- valid output? ----------------------> return new byte[]
    |
    +-- unchanged? -------------------------> return null
~~~

Design ideas:

1. **Filter very early** using `className`, optionally scoped by `loader`/`module` without forcing the loader to load the target.
2. **Do not call application code** like `TargetService.someMethod()` inside TargetService's transformer.
3. **Avoid initializing complex loggers/serializers** inside the callback, especially during JVM startup.
4. **Separate parsers and helpers from the packages being instrumented**; prepare dependencies before registration if possible.
5. **Use reentrancy guards** for callbacks in systems that need them, but do not treat a guard as a substitute for eliminating class-loading dependencies and cross-thread deadlocks.
6. **Do not hold strong references to class loaders longer than necessary** in agent caches; this can prevent class unloading in plugin applications. If caching by loader, consider weak keys and synchronization.
7. **Do not assume every loader is parent-first**; test child-first, isolated plugin loaders, and bootstrap.
8. **Measure only what needs measuring**; if you only need load counts, do not parse the entire class or load the class via reflection just to record a metric.

### Why is a ThreadLocal guard alone still not enough?

A common pattern:

~~~java
if (Boolean.TRUE.equals(inTransform.get())) {
    return null;
}
inTransform.set(true);
try {
    return doTransform(classfileBuffer);
} finally {
    inTransform.remove();
}
~~~

This is an **illustrative code snippet**, requiring `ThreadLocal<Boolean> inTransform` and `doTransform(byte[])` to be defined. A guard can prevent some recursion **on the same thread**, but **cannot** prevent Thread A from holding loader X and waiting on loader Y while Thread B holds loader Y and waits on loader X. If `doTransform` calls `loader.loadClass(target)`, the design is still wrong even with the guard added.

More important than a guard is **eliminating circular dependencies** directly in the class loading flow.

## 14. Testing loader safety for a Java agent

Do not just check that the application runs after attaching the agent. You should have a focused test matrix:

| Test | How to do it | Expected result |
| --- | --- | --- |
| Target first-time load | Run agent from `premain`, then application loads target | One callback for the right class, no loading error |
| Target not initialized early | App uses `Class.forName(name, false, loader)` then initializes later | Callback runs before `<clinit>` in the sample scenario |
| Many unrelated classes | Load other classes | Filter returns `null` quickly, no indiscriminate logging/transforming |
| Custom child-first loader | Define target with a plugin loader | Does not ask system loader to reload the same name |
| Bootstrap class | Instrument a bootstrap class in an isolated test environment | `loader==null` is handled, no NPE |
| Two classes with same binary name in two loaders | Load in two plugin contexts | Cache/filter distinguishes loader identity |
| Reentrant dependencies | Helper references another class that is also instrumented | No infinite recursion, no deadlock |
| Concurrent multi-threaded loading | Stress class loading across multiple loaders | No hangs, no lock cycles, safe metrics |
| Redefine/retransform | Callback has `classBeingRedefined != null` | No need for `loader.loadClass` to look up target |
| Dynamically generated class | Bytecode from generator/in-memory | Parser uses input bytes, does not rely on classfile resource |
| Missing helper | Inject helper call then test custom loader | Reports linkage/visibility clearly; has packaging solution |
| Verify output | Return bytes from bytecode parser | JVM accepts class, runtime tests pass |

### Assertions to include

- In the callback, all branches handling the target **have no** `Class.forName(targetName)`, `loader.loadClass(targetName)`, or manual `defineClass(targetName, ...)`.
- For out-of-scope inputs, the transformer returns `null` without initializing unnecessary dependencies.
- If a new `byte[]` output is returned, the input `classfileBuffer` is not modified in place.
- No unintended class initialization occurs before the point where the application actively uses the class.
- The agent does not break class loader identity across plugin/classloader boundaries.
- No deadlocks or recursion occur under concurrent loading.
- If helper calls are injected into a method, the helper can be resolved **by the method's runtime**, not only from the agent.
- When retransforming/redefining an already loaded target, no second class definition is produced.

**Do not use "first run succeeded" as proof for all class loaders**. Plugin loaders, module layers, bootstrap, and container environments can have different rules. Tests should reflect the deployment environment.

## 15. Self-check exercises

**Question 1.** A transformer receives `className="com/example/Service"` along with `classfileBuffer`. It wants to check whether the method `run()` exists in the class. Does it need `loader.loadClass("com.example.Service")`?

**Question 2.** When the JVM loads a new class, `classBeingRedefined == null`. Does this mean the callback must call `Class.forName(...)` to obtain a `Class<?>`?

**Question 3.** Why is `Class.forName(name, false, loader)` **inside the target's own callback** still an anti-pattern even with `initialize=false`?

**Question 4.** Is `loader == null` in `transform(...)` an error? Which loader is this usually?

**Question 5.** Two plugin loaders define two classes with the same name `com.example.PluginService`. What information is needed to distinguish them?

**Question 6.** Why is calling `ClassLoader.getSystemClassLoader().loadClass(binaryName)` not a safe fix when transforming a target from a custom loader?

**Question 7.** An agent uses a `ClassFileTransformer` that returns `null` for the target. Does that mean the class will no longer be defined by the JVM?

**Question 8.** An agent called `Class.forName(name, false, loader)` in a callback and luckily did not hang on machine A. Should this be considered a portable solution for all JVMs?

**Question 9.** An agent helper called from code injected into a bootstrap class resides in the agent JAR on the system loader. Can the bootstrap class access the helper by default?

**Question 10.** Code in `RunDemo.main` calls `Class.forName("lab.app.TargetService", false, appLoader)`. Why is that different from a transformer making the same call itself?

**Question 11.** A framework wants to compute stack map frames and automatically loads all superclasses using the target's class loader. What needs to be checked before using it in a transformer?

**Question 12.** While retransforming an already loaded class, `classBeingRedefined` is non-null. Is it necessary to call the loader again to get the class identity?

### Answers

1. **No.** Read `classfileBuffer` with a parser such as ASM or the JDK 24 Class-File API; no `Class<?>` is needed to inspect the method list.
2. **No.** `null` is the normal state when loading a new class; use `className` and the existing bytes.
3. `initialize=false` only avoids requesting initialization, **it does not avoid requesting loading/linking** of the very class being defined.
4. **No.** It usually represents the bootstrap loader; do not dereference `loader` if it is `null`.
5. The pair of **binary/internal name and defining loader identity**, optionally along with module when needed.
6. The system loader may not see the custom loader's class, or may see **a different class with the same name**; it also does not fix the reentrancy issue.
7. **No.** `return null` means this transformer **did not modify the bytes**; the JVM continues the transformation/definition chain.
8. **No.** Behavior depends on the JVM, locks/delegation, and state; do not turn luck into a contract.
9. **No.** The bootstrap loader does not by default see classes in the system loader; appropriate helper/module access must be arranged.
10. It is an **initial load request from the application**, outside the callback. The anti-pattern is **requesting to reload the target class itself while the callback is processing that class**.
11. Check whether the framework might re-load the target or other classes currently loading, loader isolation, hierarchy caching, and reentrancy/lock risks.
12. **No.** `classBeingRedefined` already holds the target's `Class<?>`; `classfileBuffer` already holds the bytes to transform.

## 16. Conclusion

**In a transform callback, the target class is not necessarily a `Class<?>` whose definition is complete. Do not ask the class loader to reload that same class.** Use the data directly from the JVM: `className` to filter, `loader`/`module` to understand context, and `classfileBuffer` to parse and emit transformed bytes. If the callback only observes, return `null`.

Keep agent helpers independent of the target, verify helper visibility in the instrumented class's runtime, avoid recursion/deadlocks in class loading, and clearly distinguish **initial loading** from **redefining/retransforming an existing class**.

## 17. Official technical documentation

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): when the callback is invoked, `className`/`loader`/`classBeingRedefined`/`classfileBuffer` parameters, rules for returning bytes/`null` and not modifying the input array.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass` mechanism, parent delegation, `findLoadedClass`, synchronization/class-loading locks, and class loader identity.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch`, and `redefineModule`.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `Class.forName`, class identity, defining loader, and hidden classes.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent manifest, `Premain-Class`, and class loading of agent helpers.
- [JVM Specification 21 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): loading model, class loaders, and interaction with linking/initialization.
