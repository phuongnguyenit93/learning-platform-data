# The `Module` Argument in `ClassFileTransformer`: Identifying the Exact Module of the Class Being Transformed

## 1. Problem and Goal

Since Java 9, the Java Platform Module System (JPMS) has added the **module** concept to the runtime. For a Java agent, a class is no longer identified solely by its name and class loader: it also **belongs to a specific module**. Two classes in the same package, or even with the same binary name in different loader/layer spaces, can be subject to different module policies and accessibility rules.

`ClassFileTransformer` provides an overload with a `Module` parameter so the agent knows the module of **the class currently being processed**, even at the point when the JVM **has not yet finished defining the class**:

```java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Where:

- **`module`:** the `java.lang.Module` object representing the module **containing the class being transformed**.
- **`loader`:** the defining class loader of the class; may be `null` if the bootstrap loader defines the class.
- **`className`:** the class/interface name in JVM internal name form, e.g., `com/example/Service`.
- **`classBeingRedefined`:** `null` when defining a new class; holds the `Class<?>` object in the redefine/retransform path.
- **`protectionDomain`:** the protection domain associated with defining the class.
- **`classfileBuffer`:** the full class-file bytes for the transformation pass; **the input array must not be modified directly**.

Key takeaway: **module and class loader are two distinct pieces of information**. A single loader can define classes belonging to named modules and its own unnamed module. `module` enables more accurate classification than inferring from package prefixes or TCCL (thread context class loader).

This lesson belongs to the **Instrumentation and Modules** section. We will examine the callback contract, distinguish named/unnamed modules, run a Java agent on Java 17 with both classpath and module path, and then see how to use `module` in production transformer design.

## 2. Which API Provides the `Module` Parameter?

### 2.1. Two `transform` Overloads

`ClassFileTransformer` has two callback forms:

**Historical form, without Module:**

```java
default byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

**Java 9+ form, with Module:**

```java
default byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

The signatures above are **illustrative** and require importing `java.security.ProtectionDomain`. In Java 17, **both methods are default methods** of the interface; do not use `ClassFileTransformer` as a functional interface/lambda.

The backward compatibility rules are very important:

- If an implementation **only overrides the 5-parameter form**, the default implementation of the 6-parameter form will **delegate to the 5-parameter form**. Legacy agents continue to work, but do not directly receive module metadata in their callback.
- If an implementation **overrides the 6-parameter form**, you get `Module` directly in the callback. There is no need to override both just to obtain module information.
- If neither method is overridden, the 5-parameter default returns `null`; the 6-parameter form forwards to it, resulting in no bytecode transformation.
- If both are overridden, clearly define the logic applied in each form; avoid infinite mutual recursion.

A Java 17 agent that needs the module directly **should override the 6-parameter form**, for example:

```java
new ClassFileTransformer() {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        // module is the module of the class being transformed.
        return null; // Do not modify bytecode.
    }
}
```

This is an **illustrative** snippet placed inside `Instrumentation.addTransformer(...)`, not a standalone program.

### 2.2. At Which Phases Does the Callback Occur?

When registered via:

```java
inst.addTransformer(transformer, false);
```

the transformer is invoked during **new class definitions** and **class redefinitions** in accordance with the contract. With `canRetransform=true`, it is also invoked during **retransformation** if the VM/agent supports the capability.

Distinction:

| Case | `module` | `classBeingRedefined` | Notes |
| --- | --- | --- | --- |
| JVM is defining a new class | Target module | `null` | No `Class<?>` for the target class is needed at the callback |
| `redefineClasses` | Module of the already-loaded class | Target `Class<?>` | Bytes from `ClassDefinition` proceed through the transformer chain |
| `retransformClasses` and transformer `canRetransform=true` | Module of the already-loaded class | Target `Class<?>` | Callback is invoked again |
| `retransformClasses` and transformer `canRetransform=false` | No new callback for this transformer | Not applicable | JVM reuses the previous transform result per the specification |

**Do not misunderstand:** `classBeingRedefined == null` indicates the **initial class definition** path; it does not mean the class belongs to no module.

In every invocation path, `module` identifies the entity containing the class. Do not use `className` to guess the module name, especially when the system has multiple module layers or custom loaders.

## 3. What Object Is `Module`?

`java.lang.Module` describes a **runtime module**, which can be either a **named module** or an **unnamed module**. Useful methods:

```java
module.isNamed();
module.getName();
module.getClassLoader();
module.getLayer();
module.getDescriptor();
module.getPackages();
```

Meanings:

- `isNamed()`: `true` if it is a named module, `false` if unnamed.
- `getName()`: the module name if named, **`null` if unnamed**.
- `getClassLoader()`: the module's loader, which may be the bootstrap loader (`null`) depending on the module.
- `getLayer()`: the layer containing the module, or `null` if the module is not in a layer.
- `getDescriptor()`: the `ModuleDescriptor` of a named module, or `null` for an unnamed module.
- `getPackages()`: the package names belonging to the module, **not** a list of all classes/methods.

**Important:** `module.getName() == null` means an **unnamed module** per the `Module` API; that is **different** from `loader == null` (bootstrap class loader). Do not equate the two conditions.

### 3.1. Named Module

A named module has a **name**, for example:

```java
module demo.named {
}
```

If class `demo.named.NamedTarget` is defined in this module, the callback can observe:

```text
module.isNamed() -> true
module.getName() -> "demo.named"
```

A module can be **explicit** (having `module-info.class`) or **automatic** (a JAR on the module path treated as an automatic module under JPMS rules). In both cases, `isNamed()` returns `true`.

For example, `String.class.getModule().getName()` on Java 17 returns `java.base`. This is a **named module**; the `java.lang.String` class is typically defined by the bootstrap loader. Thus, **a named module can certainly coexist with `loader == null`**.

### 3.2. Unnamed Module

A class running on the regular **classpath** is a member of the **unnamed module** corresponding to its defining class loader. Even though the module has no name, it **is still a `Module` object**.

```java
Module m = MyApp.class.getModule();
System.out.println(m.isNamed()); // false for a regular classpath app.
System.out.println(m.getName());  // null
```

This is an illustrative snippet in a `MyApp` application running on the classpath. You must not interpret **`module == null` as equivalent to unnamed**. The `ClassFileTransformer` specification describes the `module` parameter as the module of the class; for a regular class in an unnamed module, there will be an **unnamed Module**.

The JDK has one unnamed module **per class loader**, obtained via `loader.getUnnamedModule()` when `loader` is a non-null Java object. Therefore, two custom loaders can have **two distinct unnamed modules** even though both have `getName() == null`.

If code needs to run defensively against an unexpected `module == null` situation, label it **unknown/unavailable**, and do not automatically treat it as unnamed.

### 3.3. Table Distinguishing Module and Loader

| Class / context | `module.isNamed()` | `module.getName()` | `loader` in callback |
| --- | --- | --- | --- |
| `java.lang.String` in a typical JDK 17 runtime | `true` | `java.base` | `null`, bootstrap |
| Regular application class on the classpath | `false` | `null` | Application loader object |
| Class in an explicit named module on the module path | `true` | Name declared in `module-info.java` | The loader to which the module is assigned, typically application/platform |
| Class in an automatic module | `true` | Automatic module name | The loader to which the module is assigned |
| Class in the unnamed module of a custom loader | `false` | `null` | Custom loader object |

This describes **typical patterns**, not a "one module = one loader" law. A loader can host multiple named modules and its own unnamed module; classloader topology depends on the Java runtime and module layers.

## 4. Why Aren't Class Name / Package / Loader Alone Enough?

Suppose the transformer receives:

```text
className = "com/example/Service"
loader = appLoader
```

That information **does not by itself confirm** which module the class belongs to:

- In a classpath application, the class may belong to the **unnamed module** of `appLoader`.
- In a module path application, a class in the same package may belong to a **named module**.
- If there are multiple `ModuleLayer`s, modules with the same name in different layers are **distinct `Module` objects**.
- Multiple classloaders can define the same binary name while having different class identities.

Even the `parent/child` relationship of loaders does not tell you which module a class is defined in.

**Conclusion:** use **the callback's `module`** when selecting a policy for the class being transformed. When you need to identify a **specific** module in a system with multiple layers, you may need to rely on **the identity of the `Module` object** along with the loader/layer, not just `module.getName()`.

### Do Not Use `Thread.currentThread().getContextClassLoader()` as a Substitute

TCCL is a context that a framework/thread can set for looking up resources or services. TCCL can differ from the loader **defining the class being transformed**. Therefore, this snippet is conceptually wrong:

```java
ClassLoader guess =
        Thread.currentThread().getContextClassLoader();
// Do not infer the module of the class being transformed from guess.
```

Use the callback `module` and callback defining loader as the source of truth; TCCL may serve other business logic, but it does not prove class ownership.

## 5. Why Is `module` Useful Right at Class-Loading Time?

The transformer is called by the JVM **before the class is completely defined**. During a new load, `classBeingRedefined == null`, so there is no corresponding `Class<?>` object on which to call `getModule()`.

A dangerous mistake is to load the class yourself inside `transform` to find its module:

```java
// Do not do this in a load-time transformer:
Class<?> c = Class.forName(
        className.replace('/', '.'),
        false,
        loader);
Module m = c.getModule();
```

This example is only to **illustrate a design flaw**; `className` might be absent or have a special form, and `loader` might be `null`. The call can also:

- Trigger recursive class loading for the very class the JVM is currently defining;
- Cause `ClassCircularityError`, deadlock, or alter loading order;
- Trigger a custom loader and unwanted side effects;
- Find a class from another loader/module that does not match the current callback bytes.

Instead:

```java
// Correct: take the Module already provided by the JVM.
boolean named = module != null && module.isNamed();
String name = module == null ? "<unknown>"
        : (named ? module.getName() : "<unnamed>");
```

This is a check **that requires no new class loading**. The module data is accurate per the callback and does not have to be inferred from JAR paths or package prefixes.

In the redefine/retransform path, `classBeingRedefined` is an existing `Class<?>` object, so `classBeingRedefined.getModule()` is a useful cross-check. However, **do not use that technique for the initial load path**, because that parameter is `null`.

## 6. Java 17 Hands-On: An Agent Observing Named and Unnamed Modules

Demo objectives:

1. Create **one Java agent** that overrides the 6-parameter `transform(Module,...)` overload.
2. Run a **classpath** application: the target belongs to an unnamed module.
3. Run an **explicit named module** application: the target belongs to module `demo.named`.
4. Compare the module in the callback with `Target.class.getModule()` in the application **after the class is loaded**.
5. Do not modify bytecode: the transformer always returns `null`.

The two applications are run in **two separate JVM launches**, but using the **same agent JAR**. This keeps the results easy to verify and unaffected by custom module graphs.

### 6.1. Directory Structure

```text
module-context-demo/
├── agent.mf
└── src/
    ├── agent/
    │   └── ModuleProbeAgent.java
    ├── plain/
    │   └── demo/
    │       └── plain/
    │           ├── PlainTarget.java
    │           └── PlainMain.java
    └── named/
        ├── module-info.java
        └── demo/
            └── named/
                ├── NamedTarget.java
                └── ModuleMain.java
```

All files in the example use Java 17 APIs. The `module-info.java` file **belongs only to the named application**; the classpath app has no module descriptor.

### 6.2. File `src/agent/ModuleProbeAgent.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ModuleProbeAgent {
    private ModuleProbeAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                // Log only the two target classes; avoid logging the entire JVM.
                boolean selected =
                        "demo/plain/PlainTarget".equals(className)
                        || "demo/named/NamedTarget".equals(className);

                if (!selected) {
                    return null;
                }

                boolean named =
                        module != null && module.isNamed();
                String moduleName =
                        module == null ? "<unknown>"
                        : named ? module.getName() : "<unnamed>";

                System.out.println("[transform] "
                        + className
                        + " module=" + moduleName
                        + " named=" + named
                        + " bootstrapLoader=" + (loader == null));

                return null; // Leave classfileBuffer unchanged.
            }
        }, false);
    }
}
```

Key points:

- `@Override` **the exact 6-parameter overload**. If you omit the `Module` parameter, module information will no longer be a direct callback parameter.
- The filter uses `"literal".equals(className)`, so it is safe if the class name is unavailable in special situations.
- `module == null` is recorded as `<unknown>`, not mislabeled as unnamed. In both demo cases, `module` is provided by the JVM.
- `bootstrapLoader` only illustrates the **defining loader**, and must not be used in place of the module name.
- `classBeingRedefined` is unused because the demo only observes new class definitions.
- `false` in `addTransformer(..., false)` means retransformation capability is not needed; load-time callbacks are still received.
- `return null` means **no bytecode modification**, not an error.
- The demo prints one short line in the callback. Production agents typically need a minimal recorder instead of heavy I/O or logging thousands of classes.

### 6.3. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: ModuleProbeAgent

```

This is the manifest for the **agent JAR**, and requires a trailing blank line to end the main section. `Can-Retransform-Classes` or `Can-Redefine-Classes` is not required because it only observes class loading.

### 6.4. File `src/plain/demo/plain/PlainTarget.java`

```java
package demo.plain;

public final class PlainTarget {
    private PlainTarget() {
    }

    public static String text() {
        return "plain";
    }
}
```

This class is packaged into `plain.jar` and placed **on the classpath**, so it belongs to the unnamed module of the application class loader.

### 6.5. File `src/plain/demo/plain/PlainMain.java`

```java
package demo.plain;

public final class PlainMain {
    private PlainMain() {
    }

    public static void main(String[] args) {
        // Call the target after premain so the callback occurs clearly.
        String value = PlainTarget.text();
        Module module = PlainTarget.class.getModule();

        String name = module.isNamed()
                ? module.getName()
                : "<unnamed>";

        System.out.println("[main] module=" + name);
        System.out.println("[main] value=" + value);
    }
}
```

The program only calls `PlainTarget.class.getModule()` **after** the target has been loaded. This is an independent runtime cross-check against the callback; you do not need to do this inside the transformer.

### 6.6. File `src/named/module-info.java`

```java
module demo.named {
}
```

The module is named `demo.named`. The example needs no `requires` or `exports` because it only uses APIs from `java.base` and the application launcher invokes the entry point of the module itself.

### 6.7. File `src/named/demo/named/NamedTarget.java`

```java
package demo.named;

public final class NamedTarget {
    private NamedTarget() {
    }

    public static String text() {
        return "named";
    }
}
```

This class resides in the explicit module `demo.named` rather than an unnamed module.

### 6.8. File `src/named/demo/named/ModuleMain.java`

```java
package demo.named;

public final class ModuleMain {
    private ModuleMain() {
    }

    public static void main(String[] args) {
        String value = NamedTarget.text();
        Module module = NamedTarget.class.getModule();

        String name = module.isNamed()
                ? module.getName()
                : "<unnamed>";

        System.out.println("[main] module=" + name);
        System.out.println("[main] value=" + value);
    }
}
```

`NamedTarget.class.getModule()` reflects the module after the class has been defined. The result must match the module name from `ModuleProbeAgent`'s callback in the same JVM.

### 6.9. Compiling and Packaging (POSIX Shell)

Open a terminal in the `module-context-demo/` directory. JDK 17+ is required:

```bash
mkdir -p out/agent out/plain out/named

javac --release 17 -d out/agent \
  src/agent/ModuleProbeAgent.java

javac --release 17 -d out/plain \
  src/plain/demo/plain/PlainTarget.java \
  src/plain/demo/plain/PlainMain.java

javac --release 17 -d out/named \
  src/named/module-info.java \
  src/named/demo/named/NamedTarget.java \
  src/named/demo/named/ModuleMain.java

jar --create --file module-agent.jar --manifest agent.mf \
  -C out/agent .

jar --create --file plain.jar \
  -C out/plain .

jar --create --file named.jar \
  -C out/named .
```

Explanation:

- `module-agent.jar` contains `ModuleProbeAgent.class` **and `ModuleProbeAgent$1.class`** from the anonymous transformer; use `-C out/agent .` so no class is left out.
- `plain.jar` contains only `demo/plain/...`, with no `module-info.class`.
- `named.jar` contains `module-info.class` along with `demo/named/...`.
- Both programs use the exact **same agent** to demonstrate that `Module` information changes according to the actual module of the class.

### 6.10. Running the Classpath / Unnamed Module Case

```bash
java -javaagent:module-agent.jar \
  -cp plain.jar demo.plain.PlainMain
```

**Expected stdout** on a typical JDK 17+ runtime:

```text
[transform] demo/plain/PlainTarget module=<unnamed> named=false bootstrapLoader=false
[main] module=<unnamed>
[main] value=plain
```

`module.isNamed() == false`, even though `loader != null`. This proves that **an unnamed module is not "no module"**; it has a `Module` object, just without a name.

### 6.11. Running the Module Path / Named Module Case

```bash
java -javaagent:module-agent.jar \
  --module-path named.jar \
  --module demo.named/demo.named.ModuleMain
```

**Expected stdout:**

```text
[transform] demo/named/NamedTarget module=demo.named named=true bootstrapLoader=false
[main] module=demo.named
[main] value=named
```

`module.isNamed() == true` and `module.getName()` equals `demo.named`. Although the loader is not the bootstrap loader in the demo, a module having a name **does not imply** a special dedicated loader.

On a JVM with multiple agents, class-loading logging options, or custom configurations, other logs may appear on stderr/stdout. The lines above are **those actively emitted by the example code**, not a guarantee that no other runtime messages will appear.

### 6.12. Windows PowerShell

Create directories and compile:

```powershell
New-Item -ItemType Directory -Force out/agent, out/plain, out/named | Out-Null

javac --release 17 -d out/agent src/agent/ModuleProbeAgent.java
javac --release 17 -d out/plain src/plain/demo/plain/PlainTarget.java src/plain/demo/plain/PlainMain.java
javac --release 17 -d out/named src/named/module-info.java src/named/demo/named/NamedTarget.java src/named/demo/named/ModuleMain.java

jar --create --file module-agent.jar --manifest agent.mf -C out/agent .
jar --create --file plain.jar -C out/plain .
jar --create --file named.jar -C out/named .
```

The two run commands are the same as POSIX, on single lines:

```powershell
java -javaagent:module-agent.jar -cp plain.jar demo.plain.PlainMain
java -javaagent:module-agent.jar --module-path named.jar --module demo.named/demo.named.ModuleMain
```

Do not use `-cp` for `named.jar` if you want to test a real named module. Putting a JAR with `module-info.class` on the classpath causes its classes to be loaded under the class loader's **unnamed module** rules, not the explicit named module `demo.named`.

### 6.13. Inspecting Artifacts to Avoid Context Mismatches

```bash
jar --list --file module-agent.jar
jar --list --file plain.jar
jar --list --file named.jar

jar --describe-module --file named.jar
```

`named.jar` must contain `module-info.class` and a descriptor declaring `demo.named`. If missing, the test may turn into an automatic module or an unexpected artifact. If `ModuleProbeAgent$1.class` is missing from the agent JAR, the JVM may fail to load the anonymous transformer.

## 7. Selecting Policies Based on `Module`

In production agents, you typically want to instrument only a specific module or group of modules.

**Illustrative filter** example:

```java
private static boolean shouldTransform(
        Module module, String internalName) {

    return module != null
            && module.isNamed()
            && "com.acme.orders".equals(module.getName())
            && "com/acme/orders/OrderService".equals(internalName);
}
```

This code snippet is a helper inside an agent, **not a standalone runnable Java file**. It avoids injecting hooks into non-target modules. Comparing the module name and class name separately — **do not** treat the package prefix as the module name.

### When You Need to Distinguish Multiple Layers

A plugin system can create multiple `ModuleLayer`s and allow modules with **the same name** in different layers. If a policy truly targets a specific **runtime module instance**, comparing names alone is not enough:

```java
private static boolean isExactTarget(
        Module current, Module approved) {
    return current != null && current == approved;
}
```

Here `approved` is a `Module` object reliably identified by the application/agent infrastructure. Do not call `Class.forName` from inside the callback to find a module just to get an object for comparison. You can combine `module.getLayer()`, `module.getClassLoader()`, and the defining loader according to your policy, but **`Module` identity** is the more direct factor if you manage the exact object.

### For Unnamed Modules

If you instrument a classpath application:

```java
if (module != null && !module.isNamed()
        && "demo/plain/PlainTarget".equals(className)) {
    // Class belongs to an unnamed module.
}
```

However, in a JVM with multiple custom loaders, each of them can have its own unnamed module. In that case, narrow further by defining loader, artifact source, or the expected unnamed module object.

**Do not use `module == null` to look for an unnamed module.** If `module` is unavailable in a special situation, treat it as "insufficient metadata", skip or log according to policy, and do not guess.

## 8. Does Module Identity Replace Class Identity?

**No.** A specific class is still identified by **binary name and defining loader**, whereas a module describes runtime membership and access boundaries.

Concepts:

| Datum | Which question does it answer? | What cannot be inferred |
| --- | --- | --- |
| `className` | Which JVM internal name is being transformed? | Does not tell you the module, layer, or unique loader |
| `loader` | Which loader is defining the class? | Does not tell you named/unnamed module from the loader alone |
| `module` | Which runtime module does the class belong to? | Does not tell you whether bytes are verified or if you have permission to modify the class |
| `module.getName()` | Name of a named module | Does not distinguish modules with the same name in different layers |
| `module.getLayer()` | Layer containing the module, if any | Does not pinpoint the exact source file/JAR of each class |
| `protectionDomain` | Domain/protection information at define time | Does not replace module membership |
| `classBeingRedefined` | Existing class object during redefine/retransform | `null` during normal initial load |
| `classfileBuffer` | Bytes currently being processed by the transformer | Does not by itself guarantee the class can resolve/link after rewrite |

**A module name is not a package name.** Module `com.acme.orders` can contain `com.acme.orders.internal` or many other packages. A module name must not be inferred from `className.substring(...)`.

**One loader does not equal one module.** The system/application loader can define classes of named modules in the boot layer as well as classes of the unnamed module on the classpath. Therefore, a simple check like `loader == ClassLoader.getSystemClassLoader()` does not mean the class is in the unnamed module.

## 9. Module Metadata Does Not Automatically Grant Access Permissions

Knowing `module` is not the same as the agent being allowed to arbitrarily use reflection or call private methods of any class in that module.

JPMS has several relationships:

- **Readability:** whether one module reads another (`module.canRead(otherModule)`).
- **Exports:** whether a package is exported to another module for accessing public types under module rules (`module.isExported(packageName, otherModule)`).
- **Opens:** whether a package is open for deep reflection as appropriate (`module.isOpen(packageName, otherModule)`).
- **Class loader visibility:** whether code/helpers can find or link the right class through the corresponding loader/module.

The transformer receives `module` only to **know which module the class belongs to**; the callback does not automatically open packages, add reads, or alter the module descriptor.

### 9.1. Agent Module Read Support and Its Limits

The `java.lang.instrument` documentation states that the JVM arranges for the module of a transformed class to have a **read** relationship to the unnamed module of the bootstrap loader and of the loader that loaded the agent itself. This supports helpers placed by the agent on the appropriate class-search paths.

However, **readability does not replace exports/opens or class visibility**. If injected code tries to call a helper in an inaccessible package/module, or reflection accesses a member that is not opened, the JVM can still throw `IllegalAccessError` or `InaccessibleObjectException`.

For example, calling a helper from an instrumented named module still requires ensuring the helper is placed in the appropriate class loader, has appropriate package/public access, and does not violate module access rules. Do not see `module.isNamed()` and automatically inject calls to a class on the application classpath.

### 9.2. `Instrumentation.redefineModule` to Modify the Module Graph When Truly Needed

Java 9+ APIs include:

```java
inst.isModifiableModule(targetModule);
inst.redefineModule(
        targetModule,
        extraReads,
        extraExports,
        extraOpens,
        extraUses,
        extraProvides);
```

This snippet **illustrates the signatures**; the variables `inst`, `targetModule`, and the sets/maps are not defined. `redefineModule` only **adds** read relationships, exports, opens, or service uses/provides subject to conditions and capabilities; it **does not remove** existing relationships, **does not** move a class from one module to another, and **is not** needed just to log module names.

For an unnamed module, `redefineModule` is a no-op; `isModifiableModule` always returns `true` for an unnamed module according to the Javadoc. Do not call this API out of habit: only modify the module graph if you genuinely have valid access requirements to add.

### 9.3. Comparing Only Module Names Can Create Security Bugs

If an agent relies on `module.getName().startsWith("com.mycompany")` to decide whether to inject a security hook, a module in a plugin layer or untrusted source could have a similar name. In sensitive scenarios, you must check **module identity**, loader, deployment source, or signature/artifact policies where relevant, not just a name that external systems could influence.

## 10. Distinguishing the Callback from `Class.getModule()` and Reflective APIs

Several APIs are easily confused:

### `Class.getModule()`

```java
Module module = SomeClass.class.getModule();
```

Used **after you have a `Class<?>`**. For an already-loaded class, it returns the class's module. In the demo, `PlainTarget.class.getModule()` and `NamedTarget.class.getModule()` match the information printed from the callback.

During **initial transform**, there is no target `Class<?>` in `classBeingRedefined`, so the callback's `module` is the right path and avoids reloading the class.

### `ClassLoader.getUnnamedModule()`

```java
Module unnamed =
        ClassLoader.getSystemClassLoader().getUnnamedModule();
```

This is the unnamed module of the **system loader**, not the module of **every class in the JVM**. If a class is in an explicit named module defined by the system loader, `getUnnamedModule()` still returns an object **different from that class's module**.

### `ModuleLayer.boot()` and `ModuleLayer.findModule(...)`

These are mechanisms for managing/finding modules in a layer. They do not mean "the module of the class being transformed", especially when custom layers exist. They can be useful for resolving a module object managed by trusted infrastructure, but do not need to be called in the callback for routine classification.

### `Module.getName() == null` and `loader == null`

These two conditions answer **two independent questions**:

- `module.getName() == null`: the class is in an **unnamed module**.
- `loader == null`: the class is defined by the **bootstrap loader**.

A class in `java.base` has a non-null module name and a null loader; a classpath class has a null module name and usually a non-null loader.

## 11. Common Mistakes and How to Diagnose Them

| Symptom / statement | Cause | How to handle |
| --- | --- | --- |
| "`module == null` means a classpath class" | Equating null with unnamed | Use `module.isNamed()`; `getName() == null` for unnamed |
| `NullPointerException` on `module.getName()` or `module.isNamed()` | Missing null-check in case module is unavailable | For defensive code, treat `module == null` as unknown, not unnamed |
| Agent only receives the 5-parameter overload | Overrode the legacy method by mistake | Override the 6-parameter overload to receive `Module` directly |
| Switching to a lambda causes a compiler error | `ClassFileTransformer` is not a functional interface on Java 17 | Use a class/anonymous class and `@Override` |
| Filtering with `className.startsWith("java/")` to identify module `java.base` | Package prefix is not module identity | Use `module.getName()` and identity as required |
| TCCL is system, but the class belongs to a named module | TCCL is not the defining loader/module | Use callback parameters; do not infer from TCCL |
| Classpath JAR has `module-info.class`, yet logs still show unnamed | The JAR was put on the **classpath**, so classes are defined in the unnamed module | Run the module using `--module-path` and `--module` |
| Automatic module classified as unnamed | Assuming only explicit modules are named | Check `module.isNamed()`; automatic modules are also named |
| Two plugins have the same module name and their policies get mixed | Using only `module.getName()` as the key | Distinguish by `Module` object/layer/loader/artifact |
| `IllegalAccessError` after instrumenting a named module | Hook calls a helper that is not visible or not accessible | Check loader visibility, module reads/exports, and code linkage |
| `InaccessibleObjectException` during reflection | Package is not open for deep reflection | Check `isOpen`; adjust access in a controlled way if truly needed |
| Log does not appear for a JDK class | Class may have loaded before `premain` registered the transformer | Do not infer the wrong module; check load timing/retransform capability |
| Transformer returns `new byte[0]` for a no-op | Misunderstanding the callback contract | Return `null` when not modifying the class |
| `VerifyError` after transformation | Invalid bytecode/frames/schema | Verify bytes and check module/class loader dependencies |
| `classBeingRedefined == null` while `module` has a name | Initial load of a named-module class | This is a valid state |

When debugging, log at minimum **internal class name + module name + isNamed + loader identity/kind**. However, do not log all class loading in production without a filter because of excessive overhead and reentrancy risk.

## 12. Practical Testing and Operations

### 12.1. Cases to Test

- **Unnamed classpath:** `module.isNamed() == false`, `module.getName() == null`.
- **Named module:** `module.isNamed() == true`, `getName()` returns the actual name.
- **Automatic module:** JAR on the module path, no explicit descriptor, yet still named.
- **Bootstrap class:** `loader == null` and the module can still be named (e.g., `java.base`).
- **Plugin loader:** distinguish the unnamed modules of two loaders; avoid merging caches by `getName()`.
- **Two layers:** if two named modules with the same name exist in different layers, test module identity when a policy targets one exact layer.
- **Redefine/retransform:** the class's module is preserved and the callback receives the right phase; for a transformer with `canRetransform=false`, retransform may not invoke the callback.
- **Code-injected helpers:** verify class loader visibility, reads, exports, opens, verifier, and performance after adding instrumentation.

### 12.2. Checklist for a Module-Aware Transformer

1. Override **`transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])`** when module metadata is needed directly.
2. Do not treat an unnamed module as `null`; use `isNamed()` and `getName()` with their proper semantics.
3. Use the **callback `module`** during initial load; do not call `Class.forName` to obtain a `Class<?>`.
4. Separate module name from package name and defining loader; do not infer from TCCL.
5. If an exact module must be selected, consider `Module` identity and `ModuleLayer`, not just the name.
6. Do not treat module metadata as access permission; check reads/exports/opens and helper linkage.
7. Use `redefineModule` only when necessary and only add permitted relationships; do not use it to move a class to another module.
8. Keep the transformer short, null-safe, filtered to specific classes, and free of complex I/O and recursive class loading.
9. Return `null` when not modifying bytes; if modifying, produce a valid new byte array without mutating the input.
10. Test both classpath and module path on the target JVM, along with registration timing and other agents.

## 13. Self-Check Questions

**Question 1.** Does `module == null` mean the class is in an unnamed module?

**Answer:** No. An unnamed module is still a `Module` object. Use `!module.isNamed()` or `module.getName() == null` after ensuring `module` is non-null.

**Question 2.** Does `loader == null` mean the class is not in a named module?

**Answer:** No. For example, `java.lang.String` is in `java.base` (named) and is defined by the bootstrap loader.

**Question 3.** Can you obtain the right module by calling `Class.forName` yourself inside initial transform?

**Answer:** You should not. The class may not be finished defining yet; the operation risks recursive class loading, deadlock, or wrong loading. The callback already provides the module directly.

**Question 4.** Why do legacy agents overriding the 5-parameter form still run on Java 17?

**Answer:** The default implementation of the 6-parameter overload forwards to the 5-parameter overload. To receive `Module` directly, override the 6-parameter overload.

**Question 5.** Do two modules with the same name in two different module layers have the same identity?

**Answer:** No. They are two distinct runtime `Module` objects. A policy that compares only names can conflate them.

**Question 6.** Does `module.isNamed() == true` automatically grant reflection access to private members?

**Answer:** No. Readability, exports, opens, and visibility are separate mechanisms; the `Module` parameter does not adjust them on its own.

**Question 7.** If `named.jar` is run on the classpath instead of the module path, is it still in an explicit named module?

**Answer:** No. Classpath classes are defined in the corresponding loader's unnamed module even if the archive contains `module-info.class`. To test an explicit named module, you must use the module launcher.

## 14. Official Documentation

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): 5/6-parameter overloads, `Module` callback, loader, class name, redefine/retransform, and `return null`.
- [Oracle Java SE 17 — `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): named/unnamed modules, `isNamed`, `getName`, `getLayer`, readability, exports, and opens.
- [Oracle Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, `getUnnamedModule`, and delegation.
- [Oracle Java SE 17 — `Class.getModule()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModule()): module of an already-defined class.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `isModifiableModule`, `redefineModule`, retransform/redefine.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, manifest, agent classes, and module read support during instrumentation.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): module path, unnamed/automatic modules, module layers, and launcher options.

**Key Takeaway:** `Module module` in the 6-parameter overload of `ClassFileTransformer.transform` tells you the **runtime module containing the class being transformed**, even when the class does not yet have a `Class<?>` to query. **Named/unnamed module**, **defining class loader**, and **internal class name** are three distinct axes of identification. Use the callback `module` for accurate classification, but do not treat it as an access grant or a substitute for verifying bytecode and managing the module graph.
