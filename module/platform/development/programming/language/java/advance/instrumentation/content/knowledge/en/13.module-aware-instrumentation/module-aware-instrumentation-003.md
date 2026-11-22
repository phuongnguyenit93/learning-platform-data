# Additional Read Relationships Established by the JVM for the Module of a Transformed Class

When a Java agent transforms the bytecode of a class belonging to a **named module**, the new bytecode may call a helper located in the agent JAR or in a JAR added to the bootstrap class loader. Normally, a named module does not automatically read the unnamed module containing helpers on the classpath. To give instrumentation code a chance to link validly, the JVM has a special mechanism: **the module of the transformed class is arranged to read the unnamed module of the bootstrap class loader and the unnamed module of the class loader that loaded the main agent class**.

This is the rule described directly in the [`java.lang.instrument` package specification for Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html), section **Instrumenting code in modules**. This article explains what **module readability** means, when the JVM adds the relationship, how to observe it with a Java 17+ program, and the limits of the mechanism when the helper is located elsewhere or is inaccessible.

## 1. The Problem Before the JVM Adds Read Relationships

The Java Platform Module System (JPMS) distinguishes:

- **Named module**: a module with a name such as `demo.app`, defined by `module-info.java` and the runtime module graph.
- **Unnamed module**: each class loader has an unnamed module to hold classes that do not belong to a named module, such as classes on the classpath. Unnamed modules read all modules; however, a normal named module **does not automatically read an unnamed module**.
- **Read edge** `M → N`: module `M` reads module `N`. The runtime API `M.canRead(N)` reports this relationship.
- **Exports**: the module owning a package allows other modules to access public types in that package; this is a different condition from readability.
- **Class loading**: whether a class loader can actually find/define a class when the JVM resolves a bytecode reference; a read edge does not automatically create a class lookup path.

Suppose a transformer inserts the following call into `demo.Service.execute()` in the named module `demo.app`:

```text
invokestatic agent/ProbeHooks.hit:()V
```

Here `agent.ProbeHooks` resides on the agent's classpath, belonging to the **unnamed module of the system class loader**. Looking only at `module-info.java` of `demo.app`, there is no `requires` pointing to that unnamed module; nor can the `requires` syntax specify an unnamed module like a named module.

The JVM assists the agent by adjusting read relationships when the class is transformed. Therefore, the helper call inserted by the agent **can** be valid at the JPMS level without modifying the application's `module-info.java`.

Conditions still must be checked separately: the helper must be found by the appropriate loader, the package must be accessible, the class name and descriptor must be exact, and the method must have the right access level.

## 2. Which Relationships Exactly Does the JVM Add?

The `java.lang.instrument` specification states that, to support agent helper classes, **the module containing the transformed class** will read two unnamed modules:

1. **The unnamed module of the bootstrap class loader**: typically where the agent proactively places minimal bridges/helpers using `Instrumentation.appendToBootstrapClassLoaderSearch(...)` or a valid `Boot-Class-Path` declaration.
2. **The unnamed module of the class loader that loaded the main agent class**: for a typical startup agent, classes from the agent JAR are loaded by the **system class loader**, so this is usually the unnamed module of the system loader.

The added relationships can be represented as follows:

```text
                       Java agent
                    agent.ReadAgent
                    system class loader
                           |
                           v
             unnamed module of agent loader
                          ^  READS (added)
                          |
named module demo.app ----+
        |
        +----------------------> unnamed module of bootstrap loader
                           READS (added)
```

The `READS` arrow goes **from the module with the instrumented class to the unnamed module containing the helper**. The JVM does not thereby add a reverse relationship `agent → demo.app` and does not automatically open the application's private packages for reflection.

The relationship is added to the **runtime module**: if a class in `demo.app` is transformed and the JVM adds a read edge, that is a relationship of the corresponding `Module`, not a property specific to a single method. Other classes in the same module can observe that read edge after it is established.

### Key Points to Understand Correctly

- This is support **specific to Java Instrumentation** for the unnamed modules mentioned above, not a general rule that all named modules automatically read the classpath.
- The mechanism modifies the **runtime module graph**; it does not add `requires` to source code or `module-info.class`, nor does it alter the initial compilation result.
- `Module.canRead(...)` checks the state at runtime; before the relevant class is transformed, the relationship may not yet appear.
- The agent may run on the system loader depending on JVM configuration; what the specification emphasizes is **the loader that actually loaded the main agent class**, not an arbitrary custom loader created by the application.
- Adding a read edge does not mean every module in the JVM is modified. It is tied to the module of the **transformed class**.

## 3. Distinguishing Four Layers of Conditions: Read, Load, Export, and Access

A read edge solves exactly one part of the linking problem. For target bytecode to call `agent.ProbeHooks.hit()`, it typically needs:

| Check layer | Question | API or signal |
| --- | --- | --- |
| **Module readability** | Does the target class's module read the module containing the helper? | `targetModule.canRead(helperModule)` |
| **Class-loader visibility** | Can the target's defining loader find `agent.ProbeHooks` when resolving the symbolic reference? | `Class.forName(name, false, targetLoader)`, loader chain analysis |
| **Package accessibility** | Is the helper's package exported to the target module? | `helperModule.isExported("agent", targetModule)` |
| **Member accessibility** | Are the class and method `hit()V` public and is the signature exact? | Bytecode, modifiers, `IllegalAccessError`/`NoSuchMethodError` |

For a helper belonging to an **unnamed module**, the packages of the unnamed module are exported at runtime. Therefore the exports step is normally satisfied; however, the class/method must still be accessible and the loader must still find the class.

For example, a plugin loader completely isolated from the system loader may still fail to resolve `agent.ProbeHooks`. In that case `targetModule.canRead(agentUnnamed)` may be `true`, yet the inserted call still throws `NoClassDefFoundError`.

Conversely, if the helper resides in **another named module**, the two special read edges mentioned above **do not automatically create a read edge to that named module**. It may be necessary to adjust relationships via `Instrumentation.redefineModule(...)` along with appropriate exports.

## 4. Java 17+ Experiment: Observing `Module.canRead` Before and After Transformation

This experiment can be run with JDK 17 or later, **with no external libraries**. We create a named module `demo.app` and a startup agent. The agent registers a transformer that only handles `demo.Target`; the transformer returns a valid copy of the original bytecode. The class code does not change functionality, but the callback returns a non-`null` `byte[]`, which is enough to observe the class transformation path and the read relationship at runtime.

**Scope note:** the experiment demonstrates the read edge arranged by the JVM. It does not insert an actual hook call; to insert an `invokestatic` instruction into a real method, the agent needs a suitable bytecode transformer such as ASM, Byte Buddy, or an equivalent technique.

### 4.1. Project Structure

```text
module-read-demo/
├── agent.mf
├── agent-src/
│   └── agent/
│       └── ReadAgent.java
├── app-src/
│   └── demo.app/
│       ├── module-info.java
│       └── demo/
│           ├── Main.java
│           └── Target.java
└── out/                         # created during compilation
    ├── agent/
    ├── mods/
    └── read-agent.jar
```

### 4.2. Startup Agent and Transformer

File `agent-src/agent/ReadAgent.java`:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ReadAgent {
    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] bytes) {

                // A single target, belonging to the named module demo.app.
                if ("demo/Target".equals(className)
                        && "demo.app".equals(module.getName())) {
                    System.out.println("transform: " + className);
                    // Do not modify logic; return a non-null byte[] to apply
                    // the transformation path to this class.
                    return bytes.clone();
                }
                return null;
            }
        });
    }
}
```

- The Java 9+ callback version has the `Module module` parameter, which is the runtime module of the class being transformed.
- `className` uses the internal name form `demo/Target`, not `demo.Target`.
- Returning `null` for out-of-scope classes means the agent does not transform those classes.
- `bytes.clone()` is used because the input buffer must not be modified directly; in the experiment, the returned byte array is valid and has the same content. When actually instrumenting, return an array containing valid transformed bytecode.
- `addTransformer(...)` by default registers a load-time transformer; the experiment does not call `retransformClasses`, so the manifest **does not need** `Can-Retransform-Classes: true`.

Manifest file `agent.mf` (with a blank line after the last line):

```text
Manifest-Version: 1.0
Premain-Class: agent.ReadAgent

```

### 4.3. Target Named Module

File `app-src/demo.app/module-info.java`:

```java
module demo.app {
}
```

This module does not declare `requires` to any agent library. Classes `Main` and `Target` are in the same module, so `exports demo` is not needed.

File `app-src/demo.app/demo/Target.java`:

```java
package demo;

public final class Target {
    static {
        System.out.println("Target initialized");
    }
}
```

File `app-src/demo.app/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module named = Main.class.getModule();
        Module agentUnnamed =
                ClassLoader.getSystemClassLoader().getUnnamedModule();

        System.out.println("module=" + named.getName());
        System.out.println("before=" + named.canRead(agentUnnamed));

        // Do not reference Target.class directly in the constant pool:
        // load by name after printing the "before" state.
        Class.forName("demo.Target", true, Main.class.getClassLoader());

        System.out.println("after=" + named.canRead(agentUnnamed));
    }
}
```

This is why the example uses `Class.forName("demo.Target", ...)` instead of referencing `Target.class` directly: it defers loading the target until after the `before` check line, making the observation point clearer.

### 4.4. Compile, Package, and Run

From the `module-read-demo` directory, create the two output directories. On Linux/macOS:

```bash
mkdir -p out/agent out/mods
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/agent, out/mods | Out-Null
```

The remaining commands are the same across operating systems with JDK 17+:

```bash
javac --release 17 -d out/agent agent-src/agent/ReadAgent.java

jar --create --file out/read-agent.jar --manifest agent.mf -C out/agent .

javac --release 17 -d out/mods --module-source-path app-src \
  app-src/demo.app/module-info.java \
  app-src/demo.app/demo/Main.java \
  app-src/demo.app/demo/Target.java
```

The `javac` command above is wrapped using `\\` in POSIX shell syntax; on Windows PowerShell, use **a single line** to avoid mistaking the line-continuation character:

```powershell
javac --release 17 -d out/mods --module-source-path app-src app-src/demo.app/module-info.java app-src/demo.app/demo/Main.java app-src/demo.app/demo/Target.java
```

**Run without the agent:**

```bash
java --module-path out/mods --module demo.app/demo.Main
```

Output:

```text
module=demo.app
before=false
Target initialized
after=false
```

**Run with the startup agent:**

```bash
java -javaagent:out/read-agent.jar --module-path out/mods --module demo.app/demo.Main
```

Output:

```text
module=demo.app
before=false
transform: demo/Target
Target initialized
after=true
```

Both results above were verified with OpenJDK 21 and `--release 17` code. In the case with the agent, `ReadAgent` belongs to the unnamed module of the system loader; initially `demo.app` does not read that unnamed module. When `demo.Target` is processed by the transformer, the JVM adds the read relationship to module `demo.app`; afterwards `canRead` returns `true`.

**What is observed precisely:** `after=true` indicates that the runtime module graph has the read relationship; it **does not prove** that `Target`'s bytecode already calls a helper or that every helper can be loaded. The example intentionally keeps the bytecode unchanged to separate the JPMS mechanism from the method-call insertion operation.

If this example is applied to a JVM that has other agents or `--add-reads` options that already opened the read edge, `before` may be `true` from the start. When diagnosing, inspect the running module graph configuration rather than treating `false → true` as an invariant rule in every environment.

## 5. When Inserting a Real Helper, What Part Does the Automatic Read Edge Solve?

Suppose the transformer modifies `demo.Target.handle()` to insert:

```text
invokestatic agent/ProbeHooks.hit:()V
```

The `agent.ProbeHooks` code belongs to the unnamed module of the class loader that loaded the main agent. When `demo.Target` is transformed, the read-edge addition mechanism lets module `demo.app` read that unnamed module, so it can pass the **readability** condition of JPMS.

However, the JVM still must resolve the symbolic reference `agent/ProbeHooks` in the context of `demo.Target`'s class loader. If that is an isolated class loader that cannot find the helper via its parent or its own classpath, `NoClassDefFoundError` can occur even though the read edge exists. If the helper does not have `public static void hit()`, `IllegalAccessError` or `NoSuchMethodError` may occur depending on the error.

A commonly used design:

```text
named module of target class
          |
          +-- automatic read edge --> unnamed module of agent loader
          |
          +-- automatic read edge --> unnamed module of bootstrap loader
                                                    |
                                               public hook API
                                                    |
                                           lightweight dispatch
```

The agent implements the hook with a **small, low-dependency bootstrap helper** when it needs to serve multiple loaders or JDK classes. The helper JAR can be placed on the bootstrap search path using `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`. It must be prepared before the point of use; adding the JAR after a symbolic reference has already failed to resolve is not guaranteed to recover that reference.

The automatic read edge **does not automatically put the helper onto bootstrap**, does not copy classes between loaders, does not rewrite bytecode to use a different loading path, and does not guarantee compatibility between classes of the same name defined by different loaders.

## 6. Readability Does Not Mean Reflection Permission into a Named Module

The automatic read-edge mechanism goes in the direction **target module → unnamed module containing the helper**. Meanwhile, many agents need to go the other way: the agent wants to read private fields, call private methods, or define helpers in the package of a class belonging to a named module.

Distinguish the following questions:

| Scenario | What must be checked |
| --- | --- |
| Bytecode in target calls a public helper in an unnamed module | Read edge from target to unnamed module; helper loadable; public class/method and exact descriptor |
| Agent reflects on the public API of a package in a named module | Package has appropriate exports; class loader/module identified accurately |
| Agent uses deep reflection into private members of target | Package must be appropriately `opens`; automatic read edge does not replace `opens` |
| Agent calls a helper belonging to **another named module** | Read edge to the helper named module **and** package exported to target |
| Agent defines a new class into a controlled package/module | Requires a permitted class-definition mechanism, exact class loader/module/lookup; not inferred from automatic read edge |

In particular, `--add-opens` serves deep reflection, unlike `--add-reads` for readability. A module can read another module and still not be able to access an unexported package.

## 7. When Is `Instrumentation.redefineModule` Needed?

If instrumentation needs to add relationships to **another named module**, or needs additional exports/opens, the `Instrumentation.redefineModule` API is the appropriate tool in cases where the module permits modification.

Example **illustrative snippet, not a standalone program**: you already have `Instrumentation inst`, `Module targetModule` (the module containing the transformed class), and `Module helperModule` (the named module containing `com.example.probe.ProbeHooks`):

```java
import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

// inst, targetModule, and helperModule already obtained from runtime.
if (!inst.isModifiableModule(targetModule)
        || !inst.isModifiableModule(helperModule)) {
    throw new IllegalStateException("Module cannot be modified");
}

inst.redefineModule(
        targetModule,
        Set.of(helperModule), // extraReads: target reads helper named module
        Map.of(),             // extraExports
        Map.of(),             // extraOpens
        Set.of(),             // extraUses
        Map.of());            // extraProvides

inst.redefineModule(
        helperModule,
        Set.of(),
        Map.of("com.example.probe", Set.of(targetModule)),
        Map.of(),
        Set.of(),
        Map.of());
```

The illustration shows two **distinct** actions: adding the target's read edge and exporting the helper's package to the target. The package `com.example.probe` must actually belong to `helperModule`, and the relevant modules/classes must already exist.

**There is no need to call this code yourself just to add the two read edges to unnamed modules that the JVM already promises to establish in Java Instrumentation.** Use it only when there is a real additional requirement and when system conditions have been verified.

For `redefineModule`, adjustments are additive: the API provides no way to remove existing read edges/exports/opens. Therefore, modifying the module graph in a long-lived JVM requires a clear scope and rationale; do not try many adjustments assuming they can be completely undone like editing a configuration variable.

## 8. How to Diagnose at Runtime

In the agent, after the target class has been transformed and `Class<?> targetClass` is available, you can inspect the relationship with the agent module:

```java
// Snippet used in the agent; targetClass is the actual Class<?>.
Module targetModule = targetClass.getModule();
Module agentModule = ReadAgent.class.getModule();

System.out.println("target module=" + targetModule.getName());
System.out.println("agent module named=" + agentModule.isNamed());
System.out.println("target reads agent=" + targetModule.canRead(agentModule));
System.out.println("target loader=" + targetClass.getClassLoader());
System.out.println("agent loader=" + ReadAgent.class.getClassLoader());
```

The snippet above is a diagnostic block inside `agent.ReadAgent` after `targetClass` has been provided; do not copy it into `Main` of the named module to directly import `agent.ReadAgent`, because `Main` originally has no such compile-time dependency.

If `Class<?> helperClass` is already available, check package exports and loader identity:

```java
// helperClass is the actual Class<?> used for the helper.
Module helperModule = helperClass.getModule();
System.out.println("read=" + targetClass.getModule().canRead(helperModule));
System.out.println("exported=" + helperModule.isExported(
        helperClass.getPackageName(), targetClass.getModule()));
System.out.println("helper loader=" + helperClass.getClassLoader());
```

`Module.canRead` does not guarantee that the JVM will resolve the helper using the target loader; you can test class lookup separately:

```java
try {
    Class<?> seen = Class.forName(
            "agent.ProbeHooks", false, targetClass.getClassLoader());
    System.out.println("resolved helper loader=" + seen.getClassLoader());
} catch (ClassNotFoundException e) {
    System.out.println("Target loader cannot find helper: " + e);
}
```

A single `Class.forName` only checks the class name through the chosen loader; it does **not** prove that all call paths, signatures, access, or deep dependencies are correct.

### Result Analysis Table

| Observation | Appropriate conclusion |
| --- | --- |
| `canRead=false` before the first transform | Normal for a regular named module, if no other read edge exists yet |
| `canRead=true` after a class in the module is transformed | Consistent with the read-edge addition mechanism |
| `canRead=true` from the start | The module may already have a read edge from prior config/agent or be an automatic module; does not yet prove your agent actually transformed the target |
| `canRead=true` but `ClassNotFoundException` / `NoClassDefFoundError` | Focus on loader visibility, helper location, dependencies, and initialization errors |
| `canRead=true` but `IllegalAccessError` | Check package exports, class/method access levels, and module identity |
| `InaccessibleObjectException` error during reflective access | Check `opens` for reflection; do not confuse with read edge |
| `canRead=false` after only registering the transformer | Not necessarily an error: no matching class has been transformed yet or the transformer returned `null` |
| Helper resides in another named module | Automatic reads to unnamed modules are insufficient; consider `redefineModule` if needed |

**Effective diagnostic order:** (1) record the exact `Class<?>/Module/ClassLoader` of the target, (2) prove the transformer was invoked and returned bytes for the expected class, (3) check `canRead`, (4) check helper loadability, (5) check exports, members, descriptors, and dependencies.

## 9. Misconceptions to Avoid

1. **“The agent class sees the helper, so the target definitely sees it.”** The transformer runs under the agent's loader; the inserted bytecode is linked in the context of the target class. These are two separate environments that must be checked independently.
2. **“`--add-reads` fixes the classpath automatically.”** No. Readability and classloader delegation/search paths are two different mechanisms.
3. **“Adding a read relationship opens the entire module.”** No. It does not automatically `opens` private packages, does not grant deep reflection rights, and does not replace Java access checks.
4. **“The read relationship to the agent's unnamed module applies to every named module.”** No. The specification ties the rule to the module of the transformed class. Do not generalize to modules that do not participate in instrumentation.
5. **“The agent JAR is a named module because `-javaagent` is used.”** According to the specification, classes from the agent JAR are loaded by the system loader and belong to that loader's unnamed module, except for special arrangements of auxiliary code that the agent itself implements.
6. **“A read edge lets the target access any helper named module.”** No. The two special destinations are the unnamed module of bootstrap and of the loader that loaded the main agent class.
7. **“You must edit `module-info.java` and rebuild the application to instrument.”** The JVM has a specific runtime mechanism for this case; the source descriptor does not need to be changed to observe instrumentation-induced read edges.
8. **“`Module.canRead=true` proves the measurement is working.”** Not yet. You must verify that bytecode was actually inserted, the helper is called, and probe data appears.
9. **“You can remove a read edge when disabling a probe.”** `redefineModule` only expands the module graph and provides no operation to remove added relationships. Separate enabling/disabling instrumentation from the assumption that the module graph will revert to its original state.
10. **“Every class transitions `false → true` like the example.”** Unnamed/automatic modules or configurations with `--add-reads` may already read the unnamed module beforehand; observations must be placed in context.

## 10. Self-Check Questions

1. To which **two unnamed modules** does the JVM add read relationships when a class is transformed by Java Instrumentation?
2. Which condition does the direction `targetModule → agentUnnamed` satisfy when bytecode calls `agent.ProbeHooks.hit()`?
3. Why does adding a read edge not help an isolated class loader find a helper that is only on the system loader's classpath?
4. Why does the test program print `before=false` without the agent, and `after=true` when the agent returns `bytes.clone()` for `demo.Target`?
5. In what cases is `Instrumentation.redefineModule` needed even though the JVM automatically establishes the two special read edges?
6. What is the difference between `canRead`, `isExported`, and `isOpen`? How do errors at each layer manifest?
7. If `canRead` on the target module is already `true` from the start, what do you check before concluding that the transformer has taken effect?
8. Why can `canRead=true` not be used as the sole condition to declare that a probe is working successfully?

## 11. Official Documentation

- [Java 17 — `java.lang.instrument` package, section *Instrumenting code in modules*](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): JVM rules for the module of a transformed class reading the two unnamed modules.
- [Java 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, and differences between named/unnamed modules.
- [Java 21 — `java.lang.instrument.Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `redefineModule`, bootstrap/system class-loader search.
- [Java 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback receiving `Module`, `ClassLoader`, input bytes, and return value.
- [Java 21 — Java Virtual Machine Specification, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): class loading, linking, and symbolic reference resolution.
