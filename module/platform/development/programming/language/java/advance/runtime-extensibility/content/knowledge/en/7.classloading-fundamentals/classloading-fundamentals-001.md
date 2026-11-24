# Distinguishing Class Loading, Linking, and Initialization in the Plugin Activation Flow

## 1. The Three JVM Phases and the Application Activation Step

When a Java application receives an additional plugin, the actions "finding the JAR file," "loading the class," "linking the class," "initializing the class," "creating an object," and "enabling the plugin" are **not synonymous**. If you lump them into a single step, it becomes very difficult to explain why a plugin has been discovered but is not yet running, why a missing-library error only appears when a method is invoked, or why a `static` block runs earlier than expected.

You can view the process at two layers:

- **JVM layer:** loading, linking, and initialization of **classes/interfaces** according to the rules of the Java Virtual Machine.
- **Application layer:** plugin discovery, contract/metadata checks, instance creation, invoking activation methods such as `start()`, and then managing operation and stopping the plugin. These steps are designed by the host or plugin manager.

```text
Host reads plugin configuration/JAR or registration info
                     |
                     v
            Find provider type name
                     |
                     v
       JVM class loading (LOADING)
       find bytecode, create Class
                     |
                     v
       JVM linking (LINKING)
       verify -> prepare -> resolve (*)
                     |
                     v
       JVM initialization (INITIALIZATION)
       run static initialization logic when triggered
                     |
                     v
       Create plugin object (if the model requires it)
                     |
                     v
       Host calls start()/activate() on the plugin
                     |
                     v
       Plugin is allowed to serve requests

(*) The JVM may resolve symbolic references eagerly or defer them
    until use; this diagram is a conceptual sequence, not a
    guarantee that every sub-step occurs in fixed blocks.
```

**Class initialization** is the JVM's job; **plugin activation** is the host's decision. A class may already be initialized in the JVM while the plugin has still not received a `start()` call. Conversely, a plugin manager cannot safely invoke an instance method on a plugin before a suitable object exists.

## 2. Class Loading: Finding and Defining a Type

Class loading is the process by which the JVM, through a class loader, finds the binary representation of a class/interface and creates the corresponding `java.lang.Class` object. For a plugin, the bytecode may come from a JAR on the classpath or from a loading mechanism managed by the host.

For example, the host knows the binary name of a provider:

```text
demo.plugin.GreetingPlugin
```

A typical call is:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("demo.plugin.GreetingPlugin", false, loader);
```

This is an **illustrative snippet**, not a standalone program. The `false` parameter requests **not initializing the class** during this call. According to the Java API, the `Class.forName(name, initialize, loader)` overload attempts to locate, load, and link the class; that is **not synonymous** with executing the `static` block. Some linking resolution work may still occur later.

Distinguish between two objects that are often confused:

- `Class<?>` is the object describing the **type** known to the JVM; holding this object does not mean a plugin instance has been created.
- `GreetingPlugin` is the class type; an **instance** only exists when the host creates an object using `new`, a reflective constructor, or another provider creation mechanism.

`ClassLoader.loadClass("demo.plugin.GreetingPlugin")` is also commonly used to request loading a class; the normal loading operation itself **does not require running static initialization**. However, the host should not rely on the method name "load" to assume all dependencies are compatible: resolution of some references may be deferred.

### The Role of the ClassLoader in Plugins

A Java class is distinguished not only by its binary name but also by **the loader that defined the class**. Two different classloaders can create two distinct types with the same name `demo.spi.Plugin`; a plugin implementing one version of the interface may not be castable to the version held by the host.

To share a contract, plugin systems typically make both the host and the plugin see **the same API/SPI type** through an appropriate classloader hierarchy. A dedicated classloader helps organize dependencies and can support unloading a plugin version once all references have been released; it is **not itself a security boundary** and dynamic loading does not guarantee safe hot-swapping.

## 3. Linking: Verification, Preparation, and Resolution

Linking is the work of turning a loaded class into a usable type according to JVM rules. Three parts to understand:

| Part of linking | What does the JVM do? | What to remember for plugins |
|---|---|---|
| **Verification** | Checks the validity of the class/bytecode representation, type constraints, and verification safety | A plugin with invalid bytecode can cause `VerifyError` before any business method runs |
| **Preparation** | Allocates memory for the class's `static` fields and assigns initial values per JVM rules | This is not the step that runs all programmer-written `static` code |
| **Resolution** | Turns symbolic references in the constant pool into direct references to classes, fields, methods, etc. | Missing dependency classes, wrong signatures, or access violations can surface when references are resolved |

### 3.1. Preparation Is Not Initialization

Consider an illustrative class:

```java
final class State {
    static int counter = 7;
    static String text = build();

    private static String build() {
        System.out.println("build()");
        return "ready";
    }
}
```

This is an **illustrative class snippet**, not a complete program. In the preparation step, normal `static` fields receive their appropriate default values (`0` or `null`). Assignments like `counter = 7` and the `build()` call belong to **initialization**, and are not simply executed during preparation. Therefore, you should not expect `build()` to be printed merely because the class has been loaded or prepared.

Technical exception to know: a `static final` field with a `ConstantValue` class file attribute is assigned its constant value by the JVM according to preparation rules. This **does not change** the conclusion that `static { ... }` blocks and ordinary static initialization expressions do not run during preparation.

### 3.2. Resolution Can Arrive Late

Bytecode may store symbolic names such as `demo.spi.Plugin`, method names, and parameter types in the constant pool. The JVM has the right to resolve many references during linking or defer them until an instruction actually needs them. Consequently:

- You cannot claim all dependency classes and all methods have been resolved just because `Class.forName(..., false, ...)` returned a `Class`.
- A plugin may load/initialize successfully yet fail when entering **an unexecuted code branch** due to a missing method or dependency class.
- Errors like `NoClassDefFoundError`, `NoSuchMethodError`, `IllegalAccessError`, or other forms of `LinkageError` need to be examined alongside the loader, bytecode version, and libraries actually present.

The possibility of late resolution explains why preflight checks at plugin discovery time are necessary yet not guaranteed to catch every later runtime error.

## 4. Class Initialization: The JVM Runs Static Code

Initialization is the phase in which the JVM executes the class's static initialization logic, typically compiled into the special `<clinit>` method. It includes `static { ... }` blocks and `static` field initialization expressions in valid order. Programmers **do not directly call** `<clinit>` like a normal Java method.

When the JVM initializes a class, it must handle the initialization order of related superclasses according to the specification; this does not mean every loaded dependency class is automatically initialized right away.

**Active use** cases that can trigger class initialization if the class is not yet initialized:

- Creating an object with `new` (initializes the class before running the instance constructor).
- Calling a `static` method declared by the class.
- Reading or writing a `static` field that does not fall under the compile-time constant exception.
- Certain reflective operations or method handle calls per Java/JVM rules; for example, `Class.forName(name, true, loader)` requests initialization.

Conversely, taking a class literal `GreetingPlugin.class`, calling `getName()` on a `Class` object, or using `Class.forName(name, false, loader)` **is not itself a request to initialize that class**. If the class was already initialized by other code beforehand, a `false` call does not "undo" that initialization.

**Constant trap:** directly referencing a primitive/`String` `static final` constant variable whose value is determined at compile time can be inlined into the caller and **does not trigger initialization** of the declaring class. Do not use reading such a constant as a test for whether the `static` block has run.

Successful initialization normally happens **once per defined class** in the JVM, even when multiple threads use it concurrently. The JVM synchronizes the process; other threads may have to wait. A different classloader defining a class with the same name creates a **different type identity**, not a "re-initialization" of the existing `Class` object.

### 4.1. What Happens if `<clinit>` Fails?

A static initialization block may throw an exception, for example because an external dependency is not ready. If initialization code throws a non-`Error` exception, the JVM normally reports `ExceptionInInitializerError` for the failure; subsequent attempts to use the same class in the same loader may encounter `NoClassDefFoundError` because the class is now in an erroneous initialization state. You should not assume you can simply "retry `Class.forName(..., true, ...)`" to make the failed class re-run `static`.

A dangerous example is making network connections, opening files, spawning threads, or self-registering into a registry directly inside `static`. Those side effects can occur **before the host officially enables the plugin**, making error control, rollback, or shutting down the plugin difficult. Business work and resources should be placed in an explicit lifecycle whenever possible.

## 5. Class Initialization, Instance Creation, and Plugin Activation Are Three Separate Actions

Consider a class that has a `static` block, a constructor, and a `start()` method:

| Action | Who coordinates it? | Which code runs? |
|---|---|---|
| JVM **class initialization** | The JVM when encountering a situation requiring initialization | `static` / `<clinit>`, normally once |
| **Instance creation** | Host/factory/ServiceLoader or other code | Constructor and instance initializers, per new object |
| **Plugin activation** | Host or plugin manager per contract | `start()`/`activate()` defined by the system |

An initialized class **does not automatically create an object**; a created object **is not automatically considered an activated plugin** if the contract requires calling `start()`. In a model using a `static` method as an entry point, an instance may not be needed, yet the host must still clearly define the application activation step.

### 5.1. Target Architectural Sequence

1. **Candidate discovery:** read descriptors, service provider files, or configuration to learn which plugins can be loaded.
2. **Pre-checks:** version, contract, signature/trust source, permissions, and configuration conditions. Checks that can be done from metadata should run before executing plugin code.
3. **Type loading/checking:** choose the classloader, obtain `Class` as needed, compare SPI implementation compatibility. This step may cause the JVM to verify/resolve some dependencies.
4. **Initialization/instance creation:** per the JVM mechanism or provider factory; accept that static code and constructors may produce side effects/errors.
5. **Activation:** call `start()` after the host decides to accept the plugin; manage results and active state.
6. **Deactivation:** call `stop()`/`close()` if specified by the contract; release resources and references.

This ordering is an **application policy to limit side effects**; the JVM retains the right to resolve individual references at different times and some steps may already have occurred due to prior operations. The host cannot guarantee all malicious code is safely checked merely by loading `Class` without initializing it.

## 6. Java 17+ Example: Seeing When Each Kind of Code Runs

This example uses reflection to explicitly request loading **without initialization**, then request initialization, create an object, and invoke the activation method. The plugin lives in a separate JAR on the classpath; no external libraries are needed.

### 6.1. File Structure

```text
loading-demo/
├── api/
│   └── src/demo/spi/Plugin.java
├── plugin/
│   └── src/demo/plugin/GreetingPlugin.java
└── host/
    └── src/demo/host/Main.java
```

### 6.2. Contract — api/src/demo/spi/Plugin.java

```java
package demo.spi;

public interface Plugin {
    void start();
}
```

This interface is the shared contract. Both host and plugin compile against one `Plugin` copy that the running program will share.

### 6.3. Implementation — plugin/src/demo/plugin/GreetingPlugin.java

```java
package demo.plugin;

import demo.spi.Plugin;

public final class GreetingPlugin implements Plugin {
    static {
        System.out.println("    <clinit> GreetingPlugin");
    }

    public GreetingPlugin() {
        System.out.println("    <init> GreetingPlugin");
    }

    @Override
    public void start() {
        System.out.println("    start() GreetingPlugin");
    }
}
```

The `<clinit>` message mimics the name of the static initialization method in the JVM; Java generates the corresponding method at compile time. The `<init>` line is a **string printed inside the constructor**, representing instance creation. Meanwhile, `start()` is a business method invoked by the host, not an automatic JVM initialization hook.

### 6.4. Host — host/src/demo/host/Main.java

```java
package demo.host;

import demo.spi.Plugin;

public final class Main {
    public static void main(String[] args) throws Exception {
        String name = "demo.plugin.GreetingPlugin";
        ClassLoader loader = Thread.currentThread().getContextClassLoader();

        System.out.println("1. Nap lop, chua yeu cau khoi tao");
        Class<?> candidate = Class.forName(name, false, loader);
        System.out.println("2. Class: " + candidate.getName());

        boolean compatible = Plugin.class.isAssignableFrom(candidate);
        System.out.println("3. Dung hop dong: " + compatible);
        if (!compatible) {
            throw new IllegalArgumentException("Not a Plugin: " + name);
        }

        System.out.println("4. Yeu cau JVM khoi tao lop");
        Class.forName(name, true, loader);

        System.out.println("5. Tao doi tuong");
        Plugin plugin = (Plugin) candidate.getDeclaredConstructor().newInstance();

        System.out.println("6. Kich hoat plugin");
        plugin.start();
    }
}
```

Note that the provider class name sits in a host configuration string. Using `Class.forName` here is a pedagogical example to see **the boundaries between phases**; a real-world application may read the name from a descriptor or use `ServiceLoader`/a registry.

### 6.5. Compiling and Running with JDK 17+ on PowerShell

From the `loading-demo` directory, run:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\plugin,out\host | Out-Null

javac -d out\api api\src\demo\spi\Plugin.java
javac -cp out\api -d out\plugin plugin\src\demo\plugin\GreetingPlugin.java
javac -cp out\api -d out\host host\src\demo\host\Main.java

jar --create --file out\greeting-plugin.jar -C out\plugin .
java -cp "out\api;out\host;out\greeting-plugin.jar" demo.host.Main
```

Standard output with the files above:

```text
1. Nap lop, chua yeu cau khoi tao
2. Class: demo.plugin.GreetingPlugin
3. Dung hop dong: true
4. Yeu cau JVM khoi tao lop
    <clinit> GreetingPlugin
5. Tao doi tuong
    <init> GreetingPlugin
6. Kich hoat plugin
    start() GreetingPlugin
```

The host message code prints unaccented Vietnamese for easy exact output comparison on any console. On macOS/Linux, use the equivalent shell paths/commands and replace the `;` classpath separator with `:`.

### 6.6. Why Does This Order Matter?

- After line **1**, the JVM locates and links the class per `Class.forName(name, false, loader)`; there is no `<clinit>` line from the plugin.
- Line **2** only retrieves the `Class` object's name; it does not create an instance.
- Line **3** checks whether the type implements the `Plugin` interface; no plugin business code has been called yet.
- After line **4**, requesting initialization makes the JVM execute the `static` block and print `<clinit>`.
- After line **5**, the constructor is called to create an instance and prints `<init>`. The class is already initialized, so `<clinit>` does not run a second time.
- Only after line **6** does the host call `start()`; at this point the plugin performs the operation defined in the contract.

If you **omit the `Class.forName(name, true, loader)` call** while still keeping instance creation, the JVM will have to initialize `GreetingPlugin` before its constructor runs. Thus the `<clinit>` line will appear at the object creation step. This is why you cannot use "constructor was called" to infer that the class only began initializing at that exact moment.

If you remove `greeting-plugin.jar` from the classpath, the `Class.forName(name, false, loader)` call will fail with `ClassNotFoundException`. This is a **class loading failure**, not a `start()` error.

## 7. ServiceLoader and Provider Initialization

In SPI on the classpath, `ServiceLoader` is the mechanism that helps the host discover providers published via `META-INF/services/<service-binary-name>`. It involves class loading but **is not synonymous with the entire plugin activation lifecycle**.

Conceptual example:

```java
ServiceLoader<Plugin> services = ServiceLoader.load(Plugin.class);

for (Plugin plugin : services) {
    plugin.start();
}
```

This is an **illustrative supplementary snippet**, assuming `Plugin` is imported and a valid provider is registered. `ServiceLoader.load(...)` mainly creates the loader object; locating and instantiating providers normally happens **lazily** when iterating the list. In a typical classpath example, when `ServiceLoader` actually instantiates the provider, the JVM must ensure the class is initialized before the constructor runs. Meanwhile, `plugin.start()` is a separate decision by the host.

Important consequence: if the host iterates over `ServiceLoader` just to "check which plugins exist," iterating may already **instantiate providers and run static code/constructors**. If you want to inspect metadata before running plugin code, design a separate descriptor or inspection step, or use the appropriate provider API and understand its loading/initialization limits. `ServiceLoader` does not itself enforce trust checks, access permissions, ordering priority, or `stop()` management.

For providers in a **named module** under JPMS, the `provides ... with ...` rule also allows a provider factory form per the specification. Provider creation details depend on how it is published; the core lesson remains separating **type discovery/definition** from **code executed during initialization and plugin startup**.

## 8. Classifying Errors by Phase

| Error or symptom | Usually related to | How to investigate |
|---|---|---|
| `ClassNotFoundException` in `Class.forName` | Cannot find the requested class using the chosen loader | Check binary name, classpath/JAR, active class loader |
| `UnsupportedClassVersionError` | Bytecode is incompatible with the JVM version | Compare JDK versions used for compiling and running |
| `VerifyError` | Invalid bytecode/types under verification | Check bytecode, bytecode generation tools, and dependencies |
| `NoClassDefFoundError` | Cannot find/define a dependency class or a class previously failed initialization | Read the message and cause; distinguish a missing class from a failed initialization state |
| `NoSuchMethodError`, `IllegalAccessError` | Resolution/instruction uses a member incompatible with the runtime library | Check API/SPI versions and method/access modifiers |
| `ExceptionInInitializerError` | Error while executing static initialization code | Inspect `cause` and the `static` block; avoid blind retries |
| `InvocationTargetException` from reflection | Constructor/method invoked via reflection threw an exception | Inspect the underlying cause exception; distinguish from loading/linking errors |
| `ClassCastException` when casting provider | Contract mismatch or two classloaders defined two different copies of a same-named type | Check type identity and loaders on both sides |
| `ServiceConfigurationError` when iterating SPI | Invalid provider declaration or ServiceLoader failed to create provider | Check `META-INF/services`, constructor/factory, dependencies, and cause |

**Do not assign an error type to a single absolute moment.** Because the JVM can resolve references lazily, linking errors can appear on a later call even when `Class.forName` and the constructor succeeded earlier. Recording the stack trace, classloader, and the point where the host invoked the API helps pinpoint the true source of the error.

## 9. Practical Rules for Designing Plugin Activation

**Keep static blocks simple.** Use them only for immutable state and pure initialization if truly necessary. Avoid opening connections, starting background threads, writing files, or issuing business commands from `static` because the host may not have decided to enable the plugin yet.

**Verify the contract before creating an instance.** For example, `Plugin.class.isAssignableFrom(candidate)` can detect loaded-type incompatibility before invoking a constructor. Even so, this check does not replace verifying the plugin source, checking versions/dependencies, or handling runtime errors.

**Distinguish "loaded" from "ready to serve."** Useful plugin manager states might be `DISCOVERED` → `VALIDATED` → `LOADED` → `CREATED` → `ACTIVE` → `STOPPED`, but those are **host-defined business states**, not copies of the three JVMS phases. A provider can be loaded first and activated later.

**Do not treat `close()` as "uninitializing a class."** Calling `stop()`/`close()` only releases resources managed by the plugin according to the contract. The JVM has no standard "uninitialize class" operation; reclaiming classes/loaders depends on all related objects/references becoming eligible for collection. Changing a plugin version within the same process requires careful classloader and resource management, or process isolation.

**Keep control in the host.** The host decides when to accept a plugin, which activation method is called, when to interrupt, log errors, apply timeouts, or roll back. That a class has initialized successfully tells you only one thing about the JVM; it does not prove the plugin honors the business contract or is safe.

## 10. Self-Check Questions

1. **Does having a `Class` object mean `static` has already run?** No. You can request loading/linking without initialization, e.g., `Class.forName(name, false, loader)`.
2. **Does preparation execute the assignment `static int counter = compute()`?** No. The expression calling `compute()` belongs to class initialization; preparation normally creates the field with a default value per JVM rules.
3. **Why can `NoSuchMethodError` appear when invoking the plugin rather than when loading it?** Because some references can be resolved lazily when needed.
4. **How are a `static` block, a constructor, and `start()` similar?** All three can run plugin code, but they occur under **three different mechanisms**: class initialization, instance creation, and business activation.
5. **Does `ServiceLoader` finding a provider mean the host has enabled the plugin?** No; finding/creating the provider and calling `start()` are separate decisions.
6. **Does closing a plugin re-run `<clinit>` when opening it next time?** Not via calling `stop()/start()` on the same already-initialized class. Getting a fresh class with the same name in a different loader is a separate class-loading and lifecycle problem.

**Exercise:** Run the example in section 6, then (a) remove the `Class.forName(name, true, loader)` statement and observe when `<clinit>` runs; (b) call `plugin.start()` twice and compare the number of `<clinit>`, `<init>`, and `start()` lines; (c) remove the plugin JAR from the classpath and note which step fails first. Explain each result in terms of the JVM phases and application lifecycle.

## References

- Java Virtual Machine Specification 17, Chapter 5 – Loading, Linking, and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Java Language Specification 17, Chapter 12 – Execution, Initialization: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- Java SE 17, `Class.forName(String, boolean, ClassLoader)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, `java.util.ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
