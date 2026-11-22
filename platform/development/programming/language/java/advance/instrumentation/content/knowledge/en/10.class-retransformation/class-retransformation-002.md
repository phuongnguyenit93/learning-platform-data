# Finding the target class, checking isModifiableClass, and requesting retransformClasses

> **Problem:** A Java agent running in the JVM wants to add instrumentation to a class that has **already been loaded**. You cannot simply register a `ClassFileTransformer` and wait for the JVM to "reload" that class. You need to **find the exact `Class<?>` object**, verify that **the JVM has the retransformation capability**, check that **the specific class is modifiable**, register a retransformation-capable transformer, and then **explicitly call `Instrumentation.retransformClasses(target)`** and verify the behavior after the request succeeds.

This is a core workflow in the **Retransformation** section of Java Advance – instrumentation. The lesson also explains error-prone details: multiple class loaders defining the same class name, the difference between `isModifiableClass` and `isRetransformClassesSupported`, how the JVM processes the transformer chain, class structural change limits, exception handling, and a compilable/runnable Java 17+ example.

## 1. When do you have to use `retransformClasses`?

For a class not yet defined, an agent can register a transformer before the JVM loads the class:

~~~text
Agent registers transformer
       |
       v
JVM loads TargetService for the first time
       |
       v
ClassFileTransformer.transform(..., classBeingRedefined=null, ...)
       |
       v
Define class with transformed bytes
~~~

For a class that has **already been defined**, `addTransformer` alone does not automatically send that class back into the callback. To have the JVM reprocess an existing class, a separate command is required:

~~~text
JVM already has Class<TargetService>
       |
       v
Agent obtains the exact Class<?> object from the JVM
       |
       v
isRetransformClassesSupported()? --> false: stop or choose another approach
       |
       v
isModifiableClass(target)? ------> false: skip and record a clear reason
       |
       v
Register ClassFileTransformer with canRetransform=true
       |
       v
Instrumentation.retransformClasses(target)
       |
       v
Transformer receives callback for the class being retransformed
       |
       v
JVM verifies/applies new class-file bytes
       |
       v
Subsequent method calls can use the new definition
~~~

`retransformClasses` **does not accept replacement bytes directly** like `redefineClasses`. Instead, the JVM reconstructs the transformation chain from the base bytes of the initial definition or the most recent redefinition, reapplies the results of transformers that do not support retransformation, and calls the transformers that do support it again.

**Three verbs to distinguish:**

| Action | Java API | Direct result |
| --- | --- | --- |
| Discover loaded classes | `getAllLoadedClasses()` | List of `Class<?>` currently kept as loaded by the JVM; does not change bytecode itself |
| Check conditions | `isRetransformClassesSupported()` + `isModifiableClass(clazz)` | Two answers about general capability and per-class modifiability |
| Request the JVM to reprocess a class | `retransformClasses(clazz)` | Re-executes the transformation process per the JVM contract; may change bytecode if a transformer produces valid bytes |

**One rule:** `Class<?>` is the **class identity in the JVM**, including the defining class loader, not just a string name. Two classes with the same name but defined by two different class loaders are **two different targets**.

## 2. Step 1: finding the target class in the JVM

### 2.1. `getAllLoadedClasses()` and filtering by full name

`Instrumentation.getAllLoadedClasses()` returns an array of currently loaded classes, including classes/interfaces, array classes, and hidden classes. It is not restricted to the agent's module or application. For the class name `com.example.billing.InvoiceService`, search by `Class.getName()` using the **dot-separated** name:

~~~java
Class<?> chosen = null;
int matches = 0;

for (Class<?> candidate : inst.getAllLoadedClasses()) {
    if ("com.example.billing.InvoiceService".equals(candidate.getName())) {
        matches++;
        chosen = candidate;
    }
}

if (matches != 1) {
    throw new IllegalStateException("Expected one loaded target, found " + matches);
}
~~~

This is an **illustrative code snippet inside an agent that already has `Instrumentation inst`**, not a standalone program. This pattern **does not load** `InvoiceService` itself; it only inspects the list of loaded classes the JVM already has. If `matches == 0`, the class may not have been defined yet, the name may be wrong, or the application may be using a different implementation. If `matches > 1`, **do not pick the first element**: it is very likely that two defining class loaders have loaded a class with the same name.

In the `ClassFileTransformer.transform` callback, `className` is instead a JVM internal name, for example `com/example/billing/InvoiceService`. Do not compare slash-formatted names from the callback against `Class.getName()` without converting the format.

### 2.2. Choosing the right loader and module

When there are multiple matches, you must narrow down by **defining class loader** and, when needed, by known module/reference class:

~~~java
for (Class<?> candidate : inst.getAllLoadedClasses()) {
    if (!"com.example.billing.InvoiceService".equals(candidate.getName())) {
        continue;
    }
    ClassLoader definingLoader = candidate.getClassLoader();
    Module module = candidate.getModule();
    // Record the loader/module identifier or compare against a known target loader.
    // Only select the candidate when it matches the application to be instrumented.
}
~~~

This is also an **illustrative snippet**, without a predefined variable specifying the target loader. A class defined by the bootstrap loader may have `getClassLoader() == null`. A loader's name or `toString()` is only for diagnostics; if you have the target loader object, comparing **object identity** (`==`) is more reliable than comparing display strings.

Systems that commonly have multiple versions of a class with the same name: application servers, plugin frameworks, test runners, OSGi, containers supporting hot reload, or services using isolated class loaders. Selecting by class name while ignoring the loader can transform the **wrong tenant/plugin**, leading to class verification errors or unpredictable behavior.

**Do not hold strong references to every `Class<?>`/`ClassLoader` indefinitely** just as a class lookup cache: such references can retain an entire class loader and the object graph of an old deployment, increasing the risk of memory leaks. Filter within the scope of the work and release references that are no longer needed.

### 2.3. How is `getInitiatedClasses(loader)` different?

`getInitiatedClasses(loader)` returns the classes for which the loader is recorded as an *initiating loader* and can be found by name; it is **not synonymous** with "all classes defined by that loader". With delegation, a loader can initiate a class that is actually defined by a parent loader. In addition, this method does not include hidden classes per the API contract.

When you only know the class name and do not yet know the loader, `getAllLoadedClasses()` is the general discovery tool. When you need to limit the scope by a related loader, `getInitiatedClasses(loader)` can help, but you still must check `clazz.getClassLoader()`, name, and module to confirm the exact identity.

### 2.4. Why not just use `Class.forName`?

~~~java
Class<?> c = Class.forName(
    "com.example.billing.InvoiceService", false, intendedLoader);
~~~

This call **can cause the JVM to load/define a class that has not been loaded yet** (even though the `initialize=false` parameter does not actively run class initialization). Therefore, it is **not a pure query** to find out whether a class is already loaded, and it can alter class loading timing. Use `getAllLoadedClasses()` when the goal is **only to find already-loaded classes**. `Class.forName` is appropriate when you **intentionally** request a class to be loaded and have controlled the loader/consequences.

## 3. Step 2: checking two independent conditions

A class can only be retransformed when **both** hold:

1. The JVM and agent configuration **supports retransformation**: `inst.isRetransformClassesSupported() == true`.
2. The target class object **can have its definition changed**: `inst.isModifiableClass(clazz) == true`.

The two answers do not substitute for each other.

### 3.1. JVM capability: `isRetransformClassesSupported`

For a startup agent using `-javaagent:agent.jar`, the manifest must request:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.agent.MyAgent
Can-Retransform-Classes: true
~~~

This is an **illustrative manifest sample**; the name `com.example.agent.MyAgent` must match the actual packaged class. `Can-Retransform-Classes: true` is a condition to request the capability, but **does not by itself guarantee** that the actual JVM supports it. Without the flag or with `false`, this agent configuration is not permitted to use retransformation.

When receiving `Instrumentation` from `premain` or `agentmain`:

~~~java
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransformation is unavailable");
}
~~~

This snippet intentionally **does not** call `addTransformer(t, true)` or `retransformClasses(...)` if the capability is absent. If you still attempt `addTransformer(t, true)` on an unsupported configuration, the API can throw `UnsupportedOperationException`. This error is not solved by merely changing `isModifiableClass` or picking a different class name.

### 3.2. Modifiability of a class: `isModifiableClass`

~~~java
boolean modifiable = inst.isModifiableClass(target);
if (!modifiable) {
    throw new IllegalStateException(
        "Not modifiable: " + target.getName());
}
~~~

`isModifiableClass` **checks whether a specific class can have its definition changed**, used for both redefinition and retransformation. The result **is not determined** by `isRetransformClassesSupported()` or `isRedefineClassesSupported()`. Therefore, a JVM can return `isModifiableClass(target) == true` while retransformation is still forbidden because the general capability is `false`.

According to the Java 17 API, **primitive classes and array classes cannot be modifiable**:

~~~java
inst.isModifiableClass(int.class);        // false
inst.isModifiableClass(String[].class);   // false
~~~

These are **illustrative calls** with clearly specified results, not a complete program. Do not assume all JDK classes are unmodifiable, nor assume every application class is modifiable: check on the **actual JVM and class**. Some special/hidden classes may be unmodifiable.

### 3.3. Quick check table

| `isRetransformClassesSupported()` | `isModifiableClass(target)` | Should you call `retransformClasses(target)`? |
| --- | --- | --- |
| `false` | `false` | **No**: lacks capability and target is unmodifiable |
| `false` | `true` | **No**: target can change definition, but agent/JVM is not permitted to retransform |
| `true` | `false` | **No**: calling will hit `UnmodifiableClassException` |
| `true` | `true` | **Can request**: still needs valid transformer/bytes, the right class, and exception handling |

Even the last row does not mean the transformation is guaranteed to succeed. The JVM still checks class file validity, structural change limits, other transformers, and concurrency conditions.

## 4. Step 3: registering a retransformation-capable transformer

For a class already loaded and wanting the callback to run on `retransformClasses`:

~~~java
ClassFileTransformer transformer = new MyTransformer();
inst.addTransformer(transformer, true); // canRetransform = true
inst.retransformClasses(target);
~~~

This is an API description snippet, **not a standalone file**: `MyTransformer` must be a custom class properly implementing the interface. In Java 17, `ClassFileTransformer` has default `transform` methods, **it is not a functional interface to automatically replace with a lambda**. The full example uses a separate class.

**Distinction:**

- `inst.addTransformer(transformer)` is equivalent to `addTransformer(transformer, false)`. That transformer receives callbacks when a class is defined and redefined, but **is not called again** during retransformation.
- `inst.addTransformer(transformer, true)` creates a *retransformation-capable transformer*. When a loaded class is requested to be retransformed, the JVM invokes this transformer's callback.
- A `canRetransform=false` transformer that previously transformed the class during a prior definition/redefine has its **old result reapplied by the JVM**, without needing a new callback. Having no callback from this group **does not mean its prior effect disappears**.
- If a transformer is newly registered after a class is already loaded, it **does not retroactively receive the past first-definition event**. The `retransformClasses` call generates the appropriate callback pass for the existing class.
- When a transformer returns `null`, it does not request byte changes in that callback pass; a **successful retransform call** does not guarantee new instrumentation is present.

In the six-parameter callback (Java 9+), the fourth parameter helps identify the context:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> classBeingRedefined,
        ProtectionDomain domain, byte[] classfileBuffer) {
    if (classBeingRedefined == null) {
        // Processing the class being defined for the first time.
        return null;
    }
    // Existing class: could be redefine OR retransform.
    return null;
}
~~~

This is only an **illustrative callback body inside a transformer implementation class**, requiring imports for `java.security.ProtectionDomain` and `java.lang.instrument.ClassFileTransformer`. `classBeingRedefined != null` is the condition for an existing class, **it cannot distinguish retransform from redefine on its own** without request context.

## 5. Java 17+ experiment: finding a loaded class and retransforming successfully

We will build a startup agent `RetransformAgent`, but **only issue the retransformation command once the class is already in use by the application**. When the agent starts, `TargetService` has not been modified yet. The application creates an instance and then calls into the agent to:

1. Take a snapshot via `getAllLoadedClasses()` and find `TargetService`.
2. Check capability, modifiability, and negative cases for primitive/array types.
3. Register `ReplacementTransformer` with `canRetransform=true`.
4. Call `retransformClasses(target)`, receiving the callback for the existing class.
5. Unregister the transformer, observing **both the old instance and a new instance** using the new definition.

To keep the example completely self-contained without needing a bytecode library, the transformer returns a pre-compiled **variant class file** with the same name and same field/method structure, differing only in the body of `value()`. This is a *demo* technique, not a safe way to arbitrarily transform production classes.

### 5.1. File `TargetService.java` (original)

~~~java
public final class TargetService {
    public String value() { return "ORIGINAL"; }
}
~~~

### 5.2. File `variant/TargetService.java` (replacement)

~~~java
public final class TargetService {
    public String value() { return "INSTRUMENTED"; }
}
~~~

Both sources with the same binary name `TargetService` are compiled **into two different directories**. When the application runs, only the original is on the classpath root; the variant is only read by the agent as **data bytes** at `variant/TargetService.class`. Changing `"ORIGINAL"` to `"INSTRUMENTED"` only affects the method body, without adding methods/fields or changing the superclass.

### 5.3. File `ReplacementTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ReplacementTransformer implements ClassFileTransformer {
    private final Class<?> target;
    private final byte[] replacement;

    public ReplacementTransformer(Class<?> target, byte[] replacement) {
        this.target = target;
        this.replacement = replacement.clone();
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] original) {
        if (classBeingRedefined != target || !"TargetService".equals(className)) {
            return null;
        }
        System.out.println("transform-existing=" + className);
        return replacement.clone();
    }
}
~~~

The transformer intentionally filters by the **exact `Class<?>` object** selected in the class-finding step and the JVM internal name `TargetService`. If two loaders define the same binary name, comparing `classBeingRedefined != target` prevents returning replacement bytes for the wrong class.

`original` is the input to the current transform pass; the example does not modify this array. `replacement.clone()` provides a separate array containing a valid class file. Because the demo only targets a simple class, no other dependencies need to be considered. In a real project, a transformer should selectively transform the input bytes (for example using a bytecode library that supports the running JVM), preserving structure and remaining compatible with multiple transformers.

### 5.4. File `RetransformAgent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RetransformAgent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent=ready");
    }

    public static void retransformTarget() throws Exception {
        Instrumentation inst = instrumentation;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation capability unavailable");
        }
        Class<?> target = null;
        int matches = 0;
        for (Class<?> candidate : inst.getAllLoadedClasses()) {
            if ("TargetService".equals(candidate.getName())) {
                matches++;
                target = candidate;
            }
        }
        System.out.println("matches=" + matches);
        if (matches != 1) {
            throw new IllegalStateException("Ambiguous or missing class");
        }
        System.out.println("modifiable=" + inst.isModifiableClass(target));
        System.out.println("primitive-modifiable=" + inst.isModifiableClass(int.class));
        System.out.println("array-modifiable=" + inst.isModifiableClass(String[].class));
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Selected class is not modifiable");
        }
        byte[] updated = Files.readAllBytes(Path.of("variant/TargetService.class"));
        ReplacementTransformer transformer = new ReplacementTransformer(target, updated);
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
            System.out.println("retransform=done");
        } finally {
            System.out.println("transformer-removed=" + inst.removeTransformer(transformer));
        }
    }
}
~~~

**Why check `matches != 1`?** In the demo there is only one class named `TargetService`. If multiple class loaders contain that same name, automatic selection is unsafe; a real agent needs to identify the target loader/module instead of assuming the first element is right.

**Why read `updated` before `addTransformer`?** Callbacks occur on the class processing path; reading files or depending on heavy frameworks inside `transform` can be slow, cause class-loading cycles, or fail with I/O errors. Here the file is read once beforehand, keeping the bytes immutable via `clone()`.

**Why remove in `finally`?** The example only needs a single controlled retransformation. Removing the registration prevents the transformer from continuing to participate in future processing passes. **Do not confuse remove with undo:** the class whose method was changed still retains the new definition until another definition-changing operation occurs.

### 5.5. File `App.java`

~~~java
public final class App {
    public static void main(String[] args) throws Exception {
        TargetService service = new TargetService();
        System.out.println("before=" + service.value());
        RetransformAgent.retransformTarget();
        System.out.println("after=" + service.value());
        System.out.println("new-instance=" + new TargetService().value());
    }
}
~~~

The line `new TargetService()` appears **before the agent searches for the class**; this ensures the class has already been defined by the JVM in the experiment. We do not need to call `Class.forName` to create it, and we do not need to dynamically attach to another JVM.

### 5.6. Manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: RetransformAgent
Can-Retransform-Classes: true
~~~

This is the manifest of a **startup agent**. Save the file with a trailing newline and `Premain-Class` pointing accurately to the class with `premain(String, Instrumentation)`. To do this exercise with dynamic attach, a corresponding `Agent-Class`/`agentmain` manifest and lifecycle are needed, but the class-finding and retransformation APIs after receiving `Instrumentation` have the same meaning.

### 5.7. Compile and run

In an empty directory, create the files:

~~~text
work/
  ReplacementTransformer.java
  RetransformAgent.java
  TargetService.java
  App.java
  agent.mf
  variant/
    TargetService.java
~~~

Change into the `work` directory and run with **JDK 17+**:

~~~bash
javac --release 17 ReplacementTransformer.java RetransformAgent.java TargetService.java App.java

javac --release 17 -d variant variant/TargetService.java

jar --create --file retransform-agent.jar --manifest agent.mf ReplacementTransformer.class RetransformAgent.class

java -javaagent:retransform-agent.jar App
~~~

The two versions of `TargetService.class` must not overwrite each other. `javac -d variant` puts the replacement into the `variant` directory; `java` uses the default classpath root `.`, so it loads the `ORIGINAL` version first. If the working directory is wrong or `variant/TargetService.class` is missing, the `Files.readAllBytes` call will fail before retransformation.

**Stdout verified on OpenJDK 24, compiled with `--release 17`:**

~~~text
agent=ready
before=ORIGINAL
matches=1
modifiable=true
primitive-modifiable=false
array-modifiable=false
transform-existing=TargetService
retransform=done
transformer-removed=true
after=INSTRUMENTED
new-instance=INSTRUMENTED
~~~

### 5.8. Reading the output and relating it to the API contract

| Stdout line | What it proves |
| --- | --- |
| `agent=ready` | The JVM called `premain` and provided `Instrumentation` |
| `before=ORIGINAL` | `TargetService` was defined before retransformation; the instance is running original code |
| `matches=1` | `getAllLoadedClasses()` found **one** class named `TargetService` |
| `modifiable=true` | The specific class can have its definition changed on the test JVM |
| `primitive-modifiable=false`, `array-modifiable=false` | Primitive and array classes are not modifiable |
| `transform-existing=TargetService` | The `canRetransform=true` transformer received a callback for an already-existing class |
| `retransform=done` | The `retransformClasses(target)` request returned normally |
| `transformer-removed=true` | The transformer registration was removed; this **does not** automatically revert applied bytes |
| `after=INSTRUMENTED` | The same instance now executes the replaced method body |
| `new-instance=INSTRUMENTED` | A new instance of the same class also uses the new definition |

This result **does not mean** every JVM supports retransformation, every class is modifiable, or a transformer can freely add/remove methods. It demonstrates the API order and semantics **on a JVM whose capability was checked** with a structurally compatible demo class.

## 6. Inside `retransformClasses`: bytes and transformer order

When `retransformClasses(target)` is called, the JVM does not take the **currently executing bytes** and arbitrarily append instrumentation in a copy-paste fashion. The contract describes reconstructing the definition:

1. Start from the base class-file bytes of the initial definition, or the base bytes of **the most recent redefinition**.
2. Results of transformers that **do not support retransformation** (`canRetransform=false`) from the previous load/redefine are **reapplied automatically**, without calling their `transform` again.
3. Transformers that **support retransformation** (`canRetransform=true`) are **called again** in the JVM-contracted order, and the output of the previous transformer becomes the input for the next transformer.
4. The JVM verifies and attempts to apply the new class definition. If the class-file bytes are invalid or violate limits, the request fails.

~~~text
Base class-file bytes of the class
   |
   +-- old results of non-retransformable transformers (reapplied, no callback)
   |
   +-- capable transformer 1: transform(...)  (new callback)
   |
   +-- capable transformer 2: transform(...)  (new callback)
   |
   v
JVM verify + install class definition
~~~

In the Java 17 API, multiple groups of Java/native transformers have a defined order; when multiple agents are present, the final result depends on the **entire chain**. Picking the right class and registering a transformer with the right flag does not guarantee another agent will not modify the bytes next.

A subtle detail: the JVM may reorganize the constant pool or some attributes when regenerating the base bytes. Do not hash `classfileBuffer` and assert that it must match byte-for-byte with the original `.class` file on disk. A production transformer should inspect the class structure and ensure valid output, avoiding reasoning based on unstable byte offsets.

**Do not modify `classfileBuffer` in place.** If nothing changes, `return null`; if changing, return a new byte array.

## 7. Limits and consequences of replacing a running class

Retransformation is a powerful tool, not an unlimited license to "load a completely different Java version".

- **Cannot arbitrarily change structure:** The API/JVM TI restricts adding/removing methods or fields, changing method signatures, changing superclass/interface relationships, or forbidden structural attributes. The example only changes the **method body** to stay within supported transformations.
- **Does not recreate objects:** The `service` object in the demo is still the old instance; only new method invocations can run the new definition. The JVM does not create a replacement object and swap references.
- **Does not reset static fields:** Static values remain intact; `<clinit>` does not automatically run again just because of retransformation.
- **Active stack frames:** If a method already has a running frame when the definition changes, that frame may continue executing the old bytecode; new invocations use the new definition. Do not treat retransformation as a logic synchronization point for all threads.
- **No guarantee of restoring the original when removing the transformer:** `removeTransformer` only cancels registration; it does not automatically revert a class whose new definition the JVM has already installed.
- **No guarantee all class loaders/modules allow new helpers:** If the new bytes call into a helper class, valid class loader and module access are required; errors such as `NoClassDefFoundError` or `IllegalAccessError` can appear even when the classfile itself is valid.
- **Does not automatically change future/other classes:** A retransformed class can continue operating with the new bytes, but other classes are not automatically retransformed by package name. To target multiple classes, you must select each `Class<?>` accurately and pass an intentional target array.

In hot environments, retransformation can involve safepoints, deoptimization, or other JVM costs depending on the implementation. Do not apply it en masse to thousands of classes just because the API allows it; choose a small scope, measure latency, and have safety conditions when enabling.

## 8. Error scenarios: distinguishing "not found", "unmodifiable", and "bad bytes"

| Scenario | Symptom/exception | How to handle |
| --- | --- | --- |
| Class is not actually loaded yet | `matches=0` when filtering `getAllLoadedClasses()` | Wait for the class to be loaded, or intentionally load it under the right loader if the task allows; do not try to retransform a string name |
| Multiple loaders loaded classes with the same name | `matches>1` | Select by defining loader/module, do not pick the first element |
| Manifest missing `Can-Retransform-Classes: true` or JVM does not support it | `isRetransformClassesSupported()==false`; possibly `UnsupportedOperationException` | Fix manifest/evaluate VM; must start the agent properly for the capability to take effect |
| Target is primitive/array or non-modifiable class | `isModifiableClass(target)==false`; possibly `UnmodifiableClassException` if still requested | Skip and record a clear reason; choose another appropriate class |
| Transformer registered with default `false` | No callback seen during retransformation | Use `addTransformer(transformer, true)` if supported; note old effects of non-capable transformers |
| `ClassFileTransformer` only returns `null` | `retransformClasses` may complete but behavior is unchanged | Verify name/loader filter, callback logs, and output bytes |
| New bytes have wrong class name | `NoClassDefFoundError` | Check the binary name of the class file, do not swap definitions for another class |
| Corrupted classfile or incompatible JDK bytecode | `ClassFormatError` or `UnsupportedClassVersionError` | Check bytecode generation tool/target JDK and classfile version |
| Disallowed structural change | `UnsupportedOperationException` or corresponding VM error | Keep structure within retransform limits; only modify method bodies when needed |
| Invalid class/helper linkage | `LinkageError`, `ClassCircularityError`, `IllegalAccessError` | Check class loaders, modules, package visibility, and class loading recursion |
| Passing `null` class array or `null` element | `NullPointerException` | Validate input before calling |
| Transformer removed but instrumentation still runs | `removeTransformer()==true` yet class remains changed | Applied definitions do not auto-revert; to roll back you must design a dedicated mechanism |

**Two exceptions to know well:**

- `UnmodifiableClassException` is a checked exception when requesting to modify a class that is not allowed; checking `isModifiableClass` beforehand avoids many failure cases, though it does not replace error handling.
- `UnsupportedOperationException` relates to capabilities or changes not supported by the JVM. It can occur even when `isModifiableClass(target)==true` if the transformer produces invalid structural changes.

According to the specification, if `retransformClasses` throws an exception, **no class in the target set is successfully retransformed**. However, transformer callbacks may already have been invoked before the JVM verifies and applies the final bytes; therefore **callback logs do not prove completion**. Furthermore, an uncaught exception thrown by a callback may be treated by the JVM as `return null` and continue the chain, so you should design tighter diagnostics and output tests rather than relying on an exception inside the callback to abort the operation.

## 9. How to find and retransform multiple classes safely?

In real applications, "find every class by prefix" can be too broad. One approach is to build a list by an **explicit allowlist** of binary names, defining loaders, or modules, then filter:

~~~java
// Illustrative snippet inside an agent, not a standalone Java file.
if (!inst.isRetransformClassesSupported()) {
    return;
}

List<Class<?>> selected = new ArrayList<>();
for (Class<?> clazz : inst.getAllLoadedClasses()) {
    if (!allowedNames.contains(clazz.getName())) continue;
    if (clazz.isArray() || clazz.isPrimitive()) continue;
    if (!inst.isModifiableClass(clazz)) continue;
    if (!matchesExpectedLoaderAndModule(clazz)) continue;
    selected.add(clazz);
}

if (!selected.isEmpty()) {
    inst.retransformClasses(selected.toArray(new Class<?>[0]));
}
~~~

This Java pseudocode **does not compile standalone** because it lacks `inst`, `allowedNames`, `matchesExpectedLoaderAndModule`, and collection imports. It only shows the filtering order and API calls. With duplicate class names across multiple loaders, `matchesExpectedLoaderAndModule` is a project policy you must define yourself; do not skip this step and treat every match as the same target.

`retransformClasses(Class<?>... classes)` takes varargs, including an **empty** array (which does nothing). It can accept **multiple classes in one request** to satisfy interrelated changes; the JVM has all-or-none behavior when the operation fails per the specification. However, to keep operations controllable:

1. Use small groups by logical feature/module, avoiding unbounded scans of the entire JVM.
2. Record class identity clearly by *name + loader + module*; snapshot match counts and exclusion reasons.
3. Check both capability and `isModifiableClass` for each class, while accepting that race conditions may exist up to the moment of the call.
4. Test bytecode on an actual JVM with the same transformer chain.
5. Execute at a safe stage, with performance monitoring and failure thresholds.
6. Confirm observations from the class after the operation rather than only counting callbacks.

If a class is not yet loaded, you can **register a transformer waiting for its first definition** instead of forcing class loading just to retransform it. Which approach to choose depends on the goal: whether you need immediate effect on a running class, or only want to apply it to classes about to be defined.

## 10. Safe production workflow and rollback capability

A practical playbook:

### Before the request

- **Identify the target:** full name, loader/module, application, and methods to instrument; exclude risky framework/core classes.
- **Check capability:** `Can-Retransform-Classes: true` in the deployed agent JAR, `isRetransformClassesSupported()==true` in the real JVM.
- **Check eligibility:** `getAllLoadedClasses` returns the specific class, without picking the wrong loader; `isModifiableClass` is `true`.
- **Prepare bytes/transformer:** keep valid method/field layout, normalize class version, avoid double transformation, and avoid loading helper classes yourself inside the callback.
- **Design failure policy:** should a single class failure stop the agent? Is a canary/allowlist needed? Where are logs and alerts sent?

### During the request

- Register the transformer with `canRetransform=true` (if callbacks are needed).
- Call `retransformClasses` with the exact selected `Class<?>` objects.
- Handle `UnmodifiableClassException`, `UnsupportedOperationException`, and `Error`s reflecting invalid class bytes according to a safe strategy. Do not arbitrarily swallow `Throwable` to make the system look "successful".
- If only a one-time operation is needed, unregister in `finally` after the call. Removing the transformer **does not** restore bytecode that has already been applied.

### After the request

- Record the **request succeeded** status when the API returns normally; verify the **functional result** with a meaningful test/metric on the target class.
- Measure CPU, latency, allocation/GC, and check whether the callback causes recursion/deadlock.
- Do not assume instances have been reset: active frames and current state have their own semantics.
- If rollback is needed, use a pre-tested approach: a transformer capable of producing old bytes via retransform, `redefineClasses` with compatible bytes, or restarting the JVM without the agent. Do not assume `removeTransformer` alone is a rollback.
- Avoid holding class arrays and transformer/loader references indefinitely, especially in applications with hot deployment.

## 11. Misconceptions to eliminate

- **"`addTransformer(t, true)` will automatically reprocess all loaded classes":** No. It registers the callback; you still need `retransformClasses(target)` for already-existing classes.
- **"Searching by class name alone is enough":** Insufficient when there are multiple defining class loaders/modules. Class identity is the true target.
- **"`isModifiableClass(target)==true` means retransformation is enabled":** False. These are two independent conditions; you must check `isRetransformClassesSupported()`.
- **"Array classes or primitives can be retransformed because `Class<?>` exists":** False. They are not modifiable.
- **"`Class.forName(name, false, loader)` only looks up loaded classes":** False. It can trigger class loading, even though it does not force initialization.
- **"A `canRetransform=false` transformer is called again on retransform":** False. The JVM reuses that transformer's previous result without invoking the callback.
- **"Seeing `classBeingRedefined != null` guarantees it is retransformation":** False. Redefinition also passes a non-null `Class<?>` object.
- **"A successful retransform guarantees the method is instrumented":** False. The transformer may not match or may return `null`, or a subsequent transformer may overwrite the result.
- **"Once the transformer is removed, the class automatically reverts to original code":** False. Removing only drops the registration; it does not change the installed definition.
- **"You can freely add fields/methods during retransform":** No. The JVM enforces structural change limits, so you must verify output bytes and compatible versions.

### Official documentation

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, `isRetransformClassesSupported`, `retransformClasses`, and exceptions.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): `transform` callback, input bytes, transformer groups, and application order.
- [Java SE 17 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest attributes, `premain`/`agentmain`, and how the JVM grants instrumentation permissions.
