# Two Forms of `ClassFileTransformer.transform`: With and Without the `Module` Parameter

When writing a Java agent, we typically implement `java.lang.instrument.ClassFileTransformer` to receive class file bytes before the JVM defines or updates a class. Since Java 9, this interface supports **two overloads of `transform`**:

1. The **five-parameter** form available since Java 5, which does not take `Module`.
2. The **six-parameter** form available since Java 9, which additionally takes `java.lang.Module` as the first parameter.

The most subtle point is not just that “the new form has one more parameter”: **the two default methods are wired together in one direction**. On JDK 17, the JVM can enter the six-parameter form; if the transformer does not override that form, the interface's default implementation calls the five-parameter form. Because of this, legacy transformers continue to work. Conversely, overriding **only** the six-parameter form does not make the five-parameter form automatically forward to the new form.

This lesson belongs to the **Transformer Contract** section and covers the signatures, dispatch order, the role of `Module`, return values, and how to prove for yourself which method is called. The examples use Java 17+ and require no external bytecode libraries.

## 1. The Two Exact Signatures

The interface has the following two methods (Javadoc comments omitted for readability):

```java
package java.lang.instrument;

import java.security.ProtectionDomain;

public interface ClassFileTransformer {
    default byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) throws IllegalClassFormatException {
        return null;
    }

    default byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) throws IllegalClassFormatException {
        return transform(
                loader,
                className,
                classBeingRedefined,
                protectionDomain,
                classfileBuffer);
    }
}
```

This is **code illustrating the key part of the Java 17 contract**, not a file learners are allowed to redeclare in the `java.lang.instrument` package. `ClassFileTransformer` is already provided by the JDK; application code only needs to `implements ClassFileTransformer`.

### Five-parameter form (legacy pre-Java 9)

```java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    return null;
}
```

- There is no `Module` information in the parameters.
- Suitable when the logic relies only on class name, class loader, bytes, `ProtectionDomain`, and redefine/retransform state.
- Java 8 agent code usually overrides this form. In Java 8, this was an abstract method of the interface; on Java 9+, the JDK provides a default implementation that returns `null`.
- On JDK 17, a transformer that overrides only the five-parameter form **is still called by the JVM through the forwarding mechanism from the default six-parameter form**.

### Six-parameter form (since Java 9)

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    return null;
}
```

- `Module` is the **first parameter**, while the remaining five parameters keep the same order.
- `module` is of type `java.lang.Module`, representing the module containing the class being transformed.
- It allows filtering classes by JPMS boundaries, distinguishing named/unnamed modules, or identifying the module before deciding to transform.
- This signature requires Java 9+; if you need to compile for Java 8, you cannot reference `java.lang.Module` in Java 8 source code.

Both signatures return `byte[]`, may declare `throws IllegalClassFormatException`, and are implemented with `@Override`. The method name remains **`transform`** in lowercase; placing `Module` at the end or replacing `ClassLoader` with `Module` results in a different signature, not the overload specified to be called by the JVM.

## 2. Dispatch Rules: Understanding the Forwarding Direction

Picture the call path on JDK 17:

```text
JVM prepares to transform a class
             |
             v
transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])
             |
             +-- Does the transformer override the 6-parameter form?
             |       |
             |       +-- Yes --> runs 6-parameter logic
             |       |           (does not automatically call the 5-parameter method)
             |       |
             |       +-- No  --> default 6-parameter method
             |                       |
             |                       v
             |                 calls transform(ClassLoader, String,
             |                                 Class<?>, ProtectionDomain, byte[])
             |                       |
             |                       +-- Overrides 5-parameter? --> runs legacy logic
             |                       |
             |                       +-- No --> default 5-parameter: return null
             v
JVM receives new byte[] or null
```

Comparison by implementation style:

| Class implementing `ClassFileTransformer` | When a JDK 17 JVM transforms a class | Why? |
|---|---|---|
| Overrides only five-parameter `transform` | **Five-parameter** logic runs | Default six-parameter forwards to five-parameter |
| Overrides only six-parameter `transform` | **Six-parameter** logic runs | JVM enters the overload with `Module` |
| Overrides **both** | **Six-parameter** logic runs | Six-parameter override replaces the forwarding default |
| Overrides neither method | No custom logic; receives `null` | Default six-parameter → default five-parameter → `null` |

**There is no rule that calls both methods in sequence.** If a class overrides both, the five-parameter method only runs when some code **explicitly calls it**, or when it is invoked directly via the five-parameter signature in another context; a Java 9+ JVM does not automatically run the second method after calling the six-parameter override.

**There is no default forwarding from five to six.** A direct Java call to the five-parameter method of a class that only overrides the six-parameter method will use the five-parameter default (`return null`). This is why the two signatures must not be treated as completely interchangeable APIs.

Both methods are `default` in Java 17, so **`ClassFileTransformer` is not a functional interface**; single-method lambda syntax does not apply:

```java
// Invalid on Java 17:
// ClassFileTransformer transformer = (loader, name, type, domain, bytes) -> null;
```

Instead, use a class, an anonymous class, or a library that provides a concrete implementation.

## 3. `Module` Is Information About the Class Being Transformed

When receiving `Module module`, this value describes **the module of the target class being processed by the JVM**. It is not automatically the module of the agent, of `ClassFileTransformer`, or of the ASM/Byte Buddy library.

For example:

- Application classes on the **classpath** usually belong to an **unnamed module** of the class loader that defines them. `module.isNamed()` is `false`; `module.getName()` is `null`.
- A class belonging to `java.base` resides in the **named module** named `java.base`; `module.isNamed()` is `true`, and `module.getName()` returns `"java.base"`.
- An application class packaged in a JPMS module with `module-info.class` can belong to a named module such as `com.example.app`.

A typical check:

```java
String moduleLabel;
if (module == null) {
    moduleLabel = "<unavailable>";
} else if (module.isNamed()) {
    moduleLabel = module.getName();
} else {
    moduleLabel = "<unnamed>";
}
```

This is a **code snippet inside a method body**, not a standalone program. The `null` check supports defensive logging when called manually or in special circumstances; the API documentation describes this as the module of the class being transformed.

### Why not rely solely on `ClassLoader`?

In JPMS, **class loader** and **module** are two distinct concepts:

- `ClassLoader` answers “who defined the class?”; the bootstrap loader is represented as `null` in the callback.
- `Module` answers “which module does this class belong to?”.
- Multiple named modules can be defined by the same loader. Therefore, comparing `loader` is not enough to distinguish all modules.
- There are multiple unnamed modules corresponding to multiple loaders. The `null` name of an unnamed module is not enough to distinguish them all; when identification is needed, keep/compare the `Module` object and the appropriate class loader.

In the new transformer, you can safely filter by both the class's internal name and its module:

```java
if ("com/example/Target".equals(className)
        && module != null
        && module.isNamed()
        && "com.example.app".equals(module.getName())) {
    // Apply logic for the class with the desired name/module.
}
```

This is **an illustrative conditional branch**, not a standalone runnable class. For classes on the classpath, the `module.isNamed()` condition will not be satisfied. Having `Module` in the callback **does not automatically open packages**, does not modify `exports` or `opens`, and does not grant all reflection permissions. Module access issues must be resolved through the corresponding JPMS/JVM mechanisms.

## 4. The Remaining Parameters Are Identical

| Parameter | Meaning | Common pitfalls |
|---|---|---|
| `ClassLoader loader` | Loader defining the class | Can be `null` for the bootstrap loader |
| `String className` | Class name in **JVM internal form**, e.g. `demo/Probe` | Uses `/`, not `demo.Probe`; the API allows `null` in some situations |
| `Class<?> classBeingRedefined` | Existing `Class` if involved in redefine/retransform | Usually `null` during a new class definition |
| `ProtectionDomain protectionDomain` | Security/protection domain of the class | Do not infer the module name solely from the domain |
| `byte[] classfileBuffer` | Input class file byte array for this transform | **Do not mutate the input array in place**; return a new array if transformed |

In the six-parameter form, the table above still applies, simply adding `Module module` before `loader`.

**Example of filtering a newly loaded class:**

```java
if (!"demo/Probe".equals(className)) {
    return null;
}
if (classBeingRedefined == null) {
    System.out.println("New class definition: " + className);
}
return null;
```

This code does not produce new bytecode and does not represent a full method. Placing the literal on the left side of `.equals` avoids an error when `className == null`. During retransform or redefine, `classBeingRedefined` can be non-null; that **does not** by itself indicate whether the transformer was registered with `canRetransform=true`.

### The `return` contract does not change across overloads

```java
return null;             // Keep the bytecode unchanged at the current transform step.
return transformedBytes; // Pass the new class file byte[] into the processing pipeline.
```

The `transformedBytes` array in the example is a variable **that only exists if your code actually creates it**. You cannot modify bytecode just by changing the method name or adding `Module`. When you want to transform, you need code that produces a valid class file (ASM, Byte Buddy, or appropriate bytecode logic), then return a **new array**; the JVM will continue checking and processing other transformers.

If no transformation is performed, **returning `null`** is compliant with the contract, not an error. If a transformer throws an uncaught exception, the specification still allows subsequent transformers to run and the JVM continues attempting to define/update the class; you should not rely on exceptions to “prevent the JVM from loading a class”. `IllegalClassFormatException` helps report malformed class file input during debugging, but by contract is still equivalent to performing no transformation for that step.

## 5. Runnable Java 17+ Example: Three Transformers, One Target Class

We will use an agent JAR that registers **three transformers** in order:

1. `LegacyTransformer` overrides only the **five-parameter** form.
2. `ModuleTransformer` overrides only the **six-parameter** form.
3. `BothTransformer` overrides **both**.

All transformers only observe the `demo.Probe` class, print a log, and `return null`. The output clearly demonstrates the actual call path; no bytecode library or class file rewriting is needed.

Directory layout:

```text
transform-module-demo/
├── src/demo/
│   ├── ObserveAgent.java
│   ├── Probe.java
│   └── App.java
└── agent.mf
```

### 5.1. Target class `src/demo/Probe.java`

```java
package demo;

public final class Probe {
    private Probe() {
    }
}
```

The `Probe` class is kept simple to separate callback behavior from instruction rewriting. It is loaded during program execution in a later step.

### 5.2. Application `src/demo/App.java`

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("[app] before loading Probe");
        Class<?> type = Class.forName("demo.Probe");
        System.out.println("[app] loaded=" + type.getName());
    }
}
```

Using `Class.forName("demo.Probe")` after the first log line **requests class loading by name at runtime**. `App` does not directly reference `Probe.class` or `new Probe()` in bytecode, making it easy to see when the class loader is triggered.

Without the agent:

```bash
java -cp out demo.App
```

Stdout:

```text
[app] before loading Probe
[app] loaded=demo.Probe
```

This command only works **after the compilation step in section 5.5**.

### 5.3. Agent and Three Transformers `src/demo/ObserveAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ObserveAgent {
    private ObserveAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new LegacyTransformer());
        inst.addTransformer(new ModuleTransformer());
        inst.addTransformer(new BothTransformer());
        System.out.println("[agent] registered 3 transformers");
    }
}

// Legacy: override only the 5-parameter method.
final class LegacyTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            System.out.println("[legacy-5] demo/Probe");
        }
        return null;
    }
}

// Java 9+: override only the 6-parameter method.
final class ModuleTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            String name = module != null && module.isNamed()
                    ? module.getName()
                    : "<unnamed>";
            System.out.println(
                    "[module-6] demo/Probe module=" + name);
        }
        return null;
    }
}

// Both present: on JDK 17, the JVM selects the 6-parameter overload.
final class BothTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            System.out.println("[both-5] demo/Probe");
        }
        return null;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            System.out.println("[both-6] demo/Probe");
        }
        return null;
    }
}
```

Line-by-line explanation:

- `ObserveAgent.premain` is the agent startup entry point. Its only job in this lesson is to **register** the three transformer instances.
- `inst.addTransformer(...)` defaults to `addTransformer(transformer, false)`; this example only needs new class load events.
- `LegacyTransformer` does not override the `Module` overload, so when the JVM enters that overload, the **default six-parameter method** calls the five-parameter logic and prints `[legacy-5]`.
- `ModuleTransformer` overrides the six-parameter overload and receives the `Module` of `demo.Probe`; because `Probe` runs from `-cp out`, it belongs to an **unnamed module**, so it prints `<unnamed>`.
- `BothTransformer` overrides both; JDK 17 calls the six-parameter overload, so it prints `[both-6]`. The `[both-5]` line **does not appear** merely because the method exists.
- All three return `null`, so `demo.Probe` is loaded as before without producing replacement bytecode.

The four classes (`ObserveAgent`, `LegacyTransformer`, `ModuleTransformer`, `BothTransformer`) are declared in **a single source file**. Java allows multiple non-`public` top-level classes in the same file as one `public` top-level class; `javac` generates separate `.class` files, all of which must be included in the agent JAR.

### 5.4. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.ObserveAgent

```

`Premain-Class` specifies the class containing `premain`, not a transformer class. The JVM calls `premain`, and then the agent registers the transformers. The actual `META-INF/MANIFEST.MF` of the JAR will contain this header. Keep the trailing blank line at the end of the manifest file as shown.

### 5.5. Compile, Package JAR, and Run

From the `transform-module-demo` directory, with JDK 17+:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/demo/Probe.java src/demo/App.java src/demo/ObserveAgent.java

jar --create --file observe-agent.jar --manifest agent.mf -C out demo/ObserveAgent.class -C out demo/LegacyTransformer.class -C out demo/ModuleTransformer.class -C out demo/BothTransformer.class

java -javaagent:observe-agent.jar -cp out demo.App
```

Each `jar -C out ...` argument packages the corresponding `.class` into the JAR. No class files need to be downloaded from Maven/Gradle. To avoid missing package-private classes alongside the `public class`, inspect the archive contents:

```bash
jar --list --file observe-agent.jar
```

It must contain `META-INF/MANIFEST.MF`, `demo/ObserveAgent.class`, `demo/LegacyTransformer.class`, `demo/ModuleTransformer.class`, and `demo/BothTransformer.class`.

**Expected stdout on OpenJDK/HotSpot Java 17 when newly loaded successfully:**

```text
[agent] registered 3 transformers
[app] before loading Probe
[legacy-5] demo/Probe
[module-6] demo/Probe module=<unnamed>
[both-6] demo/Probe
[app] loaded=demo.Probe
```

Line-by-line walkthrough:

1. The agent is invoked and finishes registration **before application `main` begins**.
2. `App` prints `before loading Probe`, then calls `Class.forName`.
3. `LegacyTransformer` runs the five-parameter method via **default forwarding**.
4. `ModuleTransformer` receives the module of the class on the classpath and prints `<unnamed>` due to the example's display logic.
5. `BothTransformer` prints only `[both-6]`; `[both-5]` does not run automatically.
6. The app continues normally because all three transformers return `null`.

This is a controlled execution model; profilers, other agents, or custom JVMs may add other logs or affect class loading timing. On a standard JDK, the example filters callbacks by `demo/Probe` to suppress logs from other classes.

## 6. When Should You Choose Which Signature?

| Scenario | Recommended choice |
|---|---|
| Maintaining an agent written for Java 8 that only operates on class name/loader | Override **five-parameter**, keeping legacy Java source compatibility |
| New agent targeting Java 17+ that needs to inspect modules | Override **six-parameter** |
| Logic does not depend on modules at all, but agent targets Java 9+ | Either works; a five-parameter override still runs via the six-parameter default |
| Must run on Java 8 **and** handle JPMS on Java 9+ | Design versioned compilation/packaging and consider separate class loading; do not reference `Module` in classes loaded on Java 8 |
| Want to override both to control two different call paths | Possible, but you must **explicitly** share logic if you do not want them to diverge |
| Want to modify already-loaded classes via retransform | The signature does not grant this capability; check and register `canRetransform` appropriately |
| Only need to observe callbacks | Conditionally print/log and `return null` |

**If you override both and want to share logic**, you can have the six-parameter method call a private helper. Illustration:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain domain,
        byte[] bytes) {
    return transformCore(module, loader, className, bytes);
}
```

This is **a snippet inside a class with a `transformCore` helper that you define**, not a standalone program. For logic that uses `Module`, the helper should accept the module parameter explicitly. If you also support external five-parameter calls, decide the behavior when no module is present in that call; avoid having the two overloads call each other in an infinite cycle.

A proper use of the five-parameter form in legacy classes is to keep working code as-is and upgrade the runtime version after testing. **There is no need to add a six-parameter overload just to “force Java 9+ compatibility”**: the default already exists for that compatibility purpose.

## 7. Load-Time, Redefine, and Retransform: Dispatch Does Not Change Capabilities

`ClassFileTransformer` can participate in multiple phases, but which method is overridden **does not control when callbacks occur**.

### Load-time transformation (`load-time transformation`)

The agent registers the transformer before the class is defined. The JVM invokes the callback with the corresponding input bytes. In the example, `classBeingRedefined == null` because it is a new load.

### Redefinition (`redefineClasses`)

If the JVM supports redefine and the class is modifiable, the API can supply new class file bytes for an existing class. Appropriately registered transformers can participate in the process. Signatures with or without `Module` still follow the dispatch mechanism described above.

### Retransformation (`retransformClasses`)

Distinguish between the two registration forms:

```java
inst.addTransformer(transformer);        // canRetransform=false
inst.addTransformer(transformer, true);  // canRetransform=true
```

In this example, `transformer` is a variable holding an object implementing `ClassFileTransformer`, and `inst` is the `Instrumentation` reference in the agent; the two lines only **illustrate the choice**—do not call both for the same instance in a real program.

- With `canRetransform=false`, the transformer is called at load/redefine time; during retransform, the previous transformation result of non-retransform-capable transformers is **reapplied** without necessarily invoking the callback again.
- With `canRetransform=true`, the transformer can be called again by the JVM during retransform.
- `true` only takes effect if the JVM and agent configuration support it. Check `inst.isRetransformClassesSupported()`, `inst.isModifiableClass(clazz)`, and the manifest attribute `Can-Retransform-Classes: true` where appropriate.

The overload with `Module` **does not** have higher retransform privileges than the five-parameter overload. Nor can you infer from `classBeingRedefined != null` whether a particular method was called due to `redefine` or `retransform`; you must rely on the event context.

During retransform/redefine, the output must be a valid class file adhering to the constraints for existing classes. A transformer whose correct method is called but returns invalid bytes can still cause verify/redefine errors.

## 8. `Module` Is Useful but Does Not Guarantee Access to Every Class

In the Java Platform Module System, packages may not be exported or opened to other modules. `module` helps identify the target class's context, but it does not automatically:

- grant the agent read access to all modules;
- open all packages for reflection;
- allow a class loader to see arbitrary dependencies;
- create or modify `module-info.class`;
- allow instrumenting every class in a module without hitting JVM restrictions.

When module relationships need to be changed, `Instrumentation.redefineModule(...)` is a **separate** API with its own contract and preconditions. Before adding such operations, review the specific requirements—do not do it merely because the transformer receives `Module`.

**Two contrasting examples:**

- The agent runs in an unnamed module, and the class to inspect belongs to the named module `java.base`: the callback can see `module.getName()` as `"java.base"` if that class is transformed at an appropriate time.
- The agent runs in an unnamed module, and the target class runs on the classpath: `module.isNamed()` is `false`, even though the agent and target may be defined by different class loaders.

Do not take the agent's module via `ObserveAgent.class.getModule()` and use it in place of the callback's `module` parameter; the two objects represent **two different locations**.

## 9. Common Implementation Mistakes

### 9.1. Defining the wrong signature

```java
// Does not override the standard overload: wrong Module position.
public byte[] transform(ClassLoader loader, Module module, String name,
                        Class<?> clazz, ProtectionDomain domain, byte[] bytes) {
    return null;
}
```

The example above is a **broken method snippet for learning**, not runnable code to put into an application. If you add `@Override`, `javac` reports an error because there is no matching method in the interface; if you omit the annotation, the new method is merely a custom overload that the JVM will not call as the standard callback.

**Tip:** always use `@Override` and verify the exact five or six parameter types; `Module` goes first in the six-parameter form.

### 9.2. Assuming overriding only six parameters makes five-parameter calls run

False. The five-parameter default returns `null`; there is no automatic forwarding from five parameters to six parameters. If you need to support environments that explicitly call the legacy form, choose a clear way to share logic.

### 9.3. Assuming overriding both triggers the callback twice

False on JDK 17 for the same event: a single dispatch path selects the six-parameter override. If you see multiple logs, first check the number of registered transformers, the number of load/redefine/retransform events, and whether your code calls the other method itself.

### 9.4. Comparing class names incorrectly

```java
// Wrong when className is an internal name:
if ("demo.Probe".equals(className)) {
    // Does not match "demo/Probe".
}
```

Use `"demo/Probe"` with slashes (`/`). Also guard carefully against `className == null`.

### 9.5. Calling `module.getName().equals(...)` on an unnamed module

For an unnamed module, `module.getName()` returns `null`. Use:

```java
if (module != null
        && module.isNamed()
        && "com.example.app".equals(module.getName())) {
    // A specific named module.
}
```

This is only a conditional branch inside a callback. Do not assume every class on the classpath has a textual module name.

### 9.6. Mutating the input array or returning non-class-file data

`classfileBuffer` must be treated as immutable. If you want to make changes, create a new array containing a valid class file and `return` it; if not modifying, `return null`. You cannot safely alter a Java method by replacing arbitrary byte sequences while ignoring the constant pool, stack maps, or verifier.

### 9.7. Misunderstanding the role of exceptions

A callback throwing an exception does not guarantee class loading stops. The `ClassFileTransformer` specification states that subsequent transformers may still run, and the JVM continues attempting to define/update the class. Therefore, log and handle errors explicitly rather than relying on `throw` as an application-blocking mechanism.

### 9.8. Writing a lambda and hitting a compile error

Both methods have default implementations in Java 17, so `ClassFileTransformer` has no single abstract method to serve as a lambda target. Use `new ClassFileTransformer() { @Override ... }` or a concrete class.

### 9.9. Confusing a `Module` issue with a `ClassLoader` issue

If the transformer runs but the module filter does not match, verify whether the class is in a named or unnamed module **and** who its loader is. A class name like `demo/Probe` can appear in multiple loaders, potentially with different module identities.

## 10. A “Symptom → Check” Table

| Observation | Possible explanation | Next check |
|---|---|---|
| Five-parameter override still logs on Java 17 | Six-parameter default delegates to five-parameter | Expected compatibility behavior |
| Six-parameter override logs, five-parameter does not | Six-parameter method was overridden | Expected dispatch behavior |
| Both implemented, but only six-parameter appears | JVM selects the six-parameter overload | No second default callback |
| Transformer registered, but expected class never logs | Class already loaded, wrong filter, or event never occurred | Check registration timing, `className`, loader/module |
| `module.getName()` is `null` | Unnamed module | Use `module.isNamed()` or null check |
| Returns `null`, app unchanged | Transformer is only observing | Must produce valid bytes to modify |
| New bytes returned, but JVM throws an error | Class file malformed or violates update constraints | Check verifier, class structure, retransform/redefine constraints |
| `addTransformer(t, true)` not supported | JVM/agent does not support retransform | Check capabilities and manifest |
| Compiler says method does not override | Wrong signature or wrong Java version | Match against the JDK API used for compilation |
| Logs appear unexpectedly many times | Multiple events/registrations/agents | Trace thread, class loader, module, load/retransform situation |

## 11. Self-Check Questions

**1.** On JDK 17, a transformer class overrides only the five-parameter form. When the JVM enters the callback with `Module`, what happens?

**Answer:** The six-parameter default forwards and invokes that class's five-parameter logic.

**2.** A class overrides only the six-parameter form. If a library directly calls the five-parameter overload, does the six-parameter logic run?

**Answer:** No. The five-parameter default returns `null` if the class does not override it.

**3.** A class overrides both. Does a single class-loading event on JDK 17 run both methods?

**Answer:** No. The JVM invokes the overridden six-parameter overload; the five-parameter method does not run automatically.

**4.** Is `Module module` in the callback the module of the Java agent?

**Answer:** No; it is the module containing the class being transformed.

**5.** For the `demo.Probe` class on the classpath, what does `module.getName()` typically return?

**Answer:** `null`, because it is an unnamed module; you can use `module.isNamed()` to check.

**6.** Why can't `ClassFileTransformer` be used directly with a lambda on Java 17?

**Answer:** Both overloads are default methods, so the interface has no single abstract method to serve as a lambda target.

**7.** How does registering with `addTransformer(t)` differ from `addTransformer(t, true)`?

**Answer:** The default form does not receive callbacks again during retransform, whereas `true` can receive callbacks on retransform if supported by the runtime/agent. Both still use the same overload selection rules.

**8.** If a transformer only `return null`, does `Module` cause the JVM to alter bytecode?

**Answer:** No; `Module` is only additional context, not an instruction to modify the class file.

## 12. Key Takeaways

- **Five-parameter**: legacy contract, does not take `Module`; on JDK 17 the default returns `null` if not overridden.
- **Six-parameter**: Java 9+ contract, with `Module` first; its default **calls the five-parameter form**.
- **Overriding only five** still works on newer JDKs thanks to default delegation; **overriding only six** is called directly when the JVM uses the new overload.
- **Overriding both** does not mean the callback runs twice; on JDK 17 the six-parameter method is selected.
- `Module` describes the **target class**, complementing `ClassLoader`; for classes on the classpath, it is usually an unnamed module.
- The rules for `return null`, returning a new `byte[]`, not mutating `classfileBuffer`, and checking bytecode validity apply **to both signatures**.

## Official References

- Oracle Java 17 — [`ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): both overloads, default delegation, and the bytes contract.
- Oracle Java 17 — [`Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer registration, retransform/redefine, capability support.
- Oracle Java 17 — [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `isNamed()`, `getName()`, module relationships.
- Oracle Java 17 — [Package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): how Java agents are started.
