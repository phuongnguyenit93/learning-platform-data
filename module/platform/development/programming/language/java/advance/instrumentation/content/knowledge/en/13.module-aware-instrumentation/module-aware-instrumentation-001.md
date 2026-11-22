# Named module, unnamed module, and helper class readability during Instrumentation

When a Java agent modifies the bytecode of a class belonging to a **named module**, the new bytecode often wants to call **helper classes** provided by the agent: logging, timing, creating spans, counting events, collecting metrics. Since Java 9, there are two barriers to understand separately: **module readability** (is the module allowed to read the module containing the helper?) and **class-loader visibility** (can the class loader find/define the helper class?). If you also touch packages of the named module, you must additionally distinguish **exports** and **opens**.

An ordinary named module **does not read the classpath's unnamed module by default**. Therefore, "the helper JAR is already on the classpath" does not mean bytecode in a named module can link directly to the helper. Java Instrumentation has an important support mechanism: **when a class is actually transformed**, the JVM arranges for that class's module to read **the bootstrap class loader's unnamed module** and **the unnamed module of the class loader that loaded the main agent class**. This mechanism enables injected bytecode to call agent helpers without declaring `requires` in `module-info.java`.

This lesson clarifies the limits of that automatic mechanism, how to proactively add read relationships with `Instrumentation.redefineModule(...)`, when `--add-reads` / `--add-exports` / `--add-opens` are needed, and a Java 17+ example that has been run to verify both failure and success cases.

## 1. How do named modules and unnamed modules differ?

A **named module** has a name and a `module-info.class` descriptor (or an equivalent named module form, such as an automatic module), for example:

```java
module demo.named {
}
```

That is the content of the `module-info.java` file. When running with `--module-path` and `-m demo.named/...`, Java creates a module named `demo.named`. Normal read relationships are declared with `requires` or added dynamically through module system mechanisms.

An **unnamed module** is a nameless module that a class loader assigns to the classes it defines that do not belong to a named module, typically classes on the **classpath**. Different class loaders can have **different unnamed modules**; you should not say "the JVM has exactly one unnamed module" in all situations.

| Property | Ordinary named module | Unnamed module |
| --- | --- | --- |
| Module name | `Module.getName()` returns a non-null name | `getName() == null`; `isNamed() == false` |
| Read edge declaration | Usually from `requires`, or added via VM option/API | Reads all observable modules according to JPMS rules |
| Package exports | Only appropriately exported packages | Exports **every package** belonging to the unnamed module |
| Package opens | Only appropriately opened packages | Opens **every package** belonging to the unnamed module |
| Where classes are found | Module path or source determined by loader/module system | Usually classpath or helper search path of bootstrap/system loader |
| Reading other unnamed modules | Not a default right of an ordinary named module | Capable of reading other unnamed modules according to unnamed module rules |
| Runtime check | `module.isNamed()`, `module.canRead(other)` | Similarly, `isNamed() == false` |

An **automatic module** is a special case: a JAR without `module-info.class` placed on the module path can become a **named** module with broader readability rules, including reading unnamed modules. Do not apply the conclusion "named modules do not read unnamed" to automatic modules without considering that module kind. The hands-on example uses an **explicit named module** with an explicit `module-info.java`.

## 2. Three distinct issues: readability, exports/opens, class loader

Consider a method in module `demo.named` that wants to call:

```java
return demo.helper.Helper.message();
```

The helper is on the classpath and defined by the system class loader in the unnamed module. For the bytecode call to link successfully, you must pay attention to:

1. **Readability:** Does module `demo.named` read the module containing `demo.helper.Helper`? Use `named.canRead(helperModule)` to check.
2. **Package access:** Is package `demo.helper` exported to `demo.named`? For an **unnamed module**, every package is exported, so this lesson's scenario does not require opening an export separately on the helper side.
3. **Loader visibility:** Can the class loader involved in loading/linking class `Target` find class `demo.helper.Helper`? `--add-reads` does not automatically put a JAR onto the classpath, module path, or bootstrap search path.

For **deep reflection** (for example, reading a private field from an agent), a fourth condition appears: the package must be appropriately **opens**. `exports` grants normal Java access to public types; `opens` serves deep reflection. They are not two names for the same operation.

You can inspect modules yourself with:

```java
// Illustrative snippet inside a method; not a standalone program.
Module caller = targetClass.getModule();
Module helper = helperClass.getModule();

System.out.println(caller.isNamed());
System.out.println(helper.isNamed());
System.out.println(caller.canRead(helper));
```

**`ClassLoader.loadClass("demo.helper.Helper")` can find a class even if the calling module does not yet have a read edge to it.** The fact that the loader finds the bytes/class does not prove that direct bytecode linking has access permission. The experiment below will show that `loadClass(...)` succeeds while `Target.hello()` can still throw `IllegalAccessError`.

## 3. Default read relationships: which direction is allowed?

Conceptual diagram before agent intervention:

```text
                           Named module
                             demo.named
                                  |
                                  | reads java.base (implicit)
                                  v
                               java.base

System class loader
  └── Unnamed module
        └── demo.helper.Helper

demo.named  -X->  system loader unnamed module
            no read edge by default
```

**Important read directions:**

- **Unnamed module → named modules:** unnamed modules are designed to interact broadly with observable modules.
- **Explicit named module → unnamed module:** no `requires` in `module-info.java` can declare an unnamed module by name. Therefore, that read edge does not exist automatically.
- **Named module → another named module:** normally uses `requires other.module`, and package exports must still be considered.

Saying "the classpath holds all classes so any module can access them" is wrong in JPMS. The classpath determines how classes are found within a loader's scope; **readability** remains an independent module condition.

## 4. Java Instrumentation provides special support for transformed classes

The official documentation for package `java.lang.instrument` describes the support mechanism for agents that place helpers on the search path of the bootstrap loader or the loader that loaded the agent:

> The JVM automatically arranges for the module of a **transformed class** to read the unnamed module of **two loaders**: the bootstrap loader and the loader that loaded the main agent class.

From this follow practical conclusions:

- The agent class is usually loaded by the **system class loader** into that loader's unnamed module.
- Helpers placed on the **system loader**'s search path can be called directly by instrumented bytecode if the named module is given the corresponding read edge by the JVM and the loader finds the helper.
- Helpers that the agent arranges to be loaded by the **bootstrap loader** also have their own unnamed module and can have a read edge created to them.
- This mechanism **does not by default add read edges to every unnamed module of every custom class loader** in the JVM.
- The read relationship is part of the linking condition; the JVM **does not automatically create a helper JAR**. The agent must package/arrange for helper classes to be loadable.
- The support mechanism applies to the module of a class that is **actually transformed**; it does not mean that simply starting the JVM with `-javaagent` causes all named modules to read unnamed modules.

### 4.1. A callback being invoked does not necessarily mean the class was transformed

In `ClassFileTransformer.transform(...)`:

- Returning `null`: the transformer **did not modify bytes** on that pass.
- Returning a new `byte[]`: the transformer supplies bytes for the definition; the JVM treats that class as a **transformed** case.

In the verification experiment in section 7, the callback for `demo/named/Target` **was invoked** but **returned `null`**, so the automatic read edge **did not appear** on the tested JVM. When the same callback returned **`bytes.clone()`** (a valid classfile, with unchanged content), the JVM recorded the class as transformed and the read edge appeared. This is a very clear way to distinguish **"the agent registered/observed"** from **"a transformed class was applied"**.

**You should not use `bytes.clone()` in a production agent just to add a read edge.** If the real goal is to add a read relationship, `redefineModule(...)` is the clearer tool; returning new bytes needlessly has extra overhead and can interact with other transformers. The hands-on exercise uses clone only to verify the specified mechanism.

### 4.2. An agent in an unnamed module does not implicitly gain access to privates of a named module

The direction **Target's named module reads Helper's unnamed module** is for **Target calling Helper**. If the **Agent wants to reflect on private classes/members of Target's module**, you need to check a problem in the **reverse direction**:

- Does the agent module read the target named module?
- Does the Target package have **exports** for the appropriate public access?
- Is the package **opens** to the agent module to use `setAccessible(true)` or deep reflection?
- Is the target class actually made available by the loader?

The JVM automatically adding a read edge for helpers **does not automatically open every package** of the named module to the agent.

## 5. Proactively adding a read edge with `Instrumentation.redefineModule`

When an agent needs to change read relationships without relying on a specific transform pass, it can use:

```java
void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
```

This is a **condensed signature for explanation**, not a complete code snippet. Meaning of each part:

| Parameter | Effect |
| --- | --- |
| `module` | The module **to be updated**, e.g., `Target.class.getModule()`. |
| `extraReads` | Adds modules that `module` can read. |
| `extraExports` | Adds export permissions for packages **of `module`** to specific target modules. |
| `extraOpens` | Adds open permissions for packages **of `module`** for deep reflection. |
| `extraUses` | Adds service types that the module uses. |
| `extraProvides` | Adds service provider mappings of the module. |

With only one requirement—**named Target reads system unnamed Helper**—the concise call is:

```java
// Snippet inside premain/agentmain, with Instrumentation inst.
Module target = ModuleLayer.boot()
        .findModule("demo.named")
        .orElseThrow();
Module helper = ClassLoader.getSystemClassLoader()
        .getUnnamedModule();

if (!inst.isModifiableModule(target)) {
    throw new IllegalStateException("Target module cannot be modified");
}

inst.redefineModule(
    target,
    java.util.Set.of(helper), // extraReads
    java.util.Map.of(),        // extraExports
    java.util.Map.of(),        // extraOpens
    java.util.Set.of(),        // extraUses
    java.util.Map.of()         // extraProvides
);
```

That call **only adds** a read edge from `target` to `helper`. It does not modify the `module-info.class` module descriptor on disk; the read edge is added to the running JVM's module model.

**Important limitations:**

- `redefineModule` only **expands** reads/exports/opens/uses/provides; it **does not revoke** them.
- For an **unnamed module**, `redefineModule` is a **no-op**; `isModifiableModule(unnamed)` still returns `true` per the API. This is not a contradiction: unnamed modules already have broad read/export/open rights by design.
- Before calling it for a named module, check `isModifiableModule(target)`. An unmodifiable module can cause the call to throw `UnmodifiableModuleException`.
- The `extraExports`/`extraOpens` maps must only contain packages **that actually belong to the module being updated**; an invalid package name causes `IllegalArgumentException`. Do not pass an empty target set for a package or null parameters.
- For a target in a **layer other than the boot layer**, you should not rely solely on `ModuleLayer.boot().findModule(...)`; you must obtain the exact `Class<?>` and `getModule()` of the class to instrument, or the appropriate layer.

A read edge **cannot replace loader visibility**: if the helper JAR is outside the search path of the class loader in use, you can still encounter `ClassNotFoundException` or `NoClassDefFoundError`.

## 6. Launcher options: `--add-reads`, `--add-exports`, `--add-opens`

When the configuration is known upfront, you can grant permissions using JVM flags instead of modifying modules at runtime.

| Option | Target | When to use |
| --- | --- | --- |
| `--add-reads demo.named=ALL-UNNAMED` | Named module reads **unnamed modules** | Code in the named module needs to call a helper on the classpath. |
| `--add-exports demo.named/demo.internal=ALL-UNNAMED` | Export package `demo.internal` to unnamed modules | Agent/helper needs to access public types in an unexported package. |
| `--add-opens demo.named/demo.internal=ALL-UNNAMED` | Open package to unnamed modules | Agent needs deep reflection, e.g., accessing private members when other conditions allow. |

The two sides of `--add-exports` and `--add-opens` go **from the module owning the package → the module granted access**. Do not read it backwards: for **Target to read Helper**, use `--add-reads demo.named=ALL-UNNAMED`; you do not need to export `demo.named` to unnamed to achieve that goal.

`--add-reads` can be used at **compile time** to allow source in the named module to reference types on the classpath, and at **run time** to add the runtime read relationship. Compile-time permission **is not automatically persisted as a runtime read edge** in `module-info.class`. The example will intentionally grant `--add-reads` during `javac` but omit it during `java` to reproduce `IllegalAccessError`.

Comparison with the API:

- `--add-reads demo.named=ALL-UNNAMED` opens a read edge to **all unnamed modules** within the option's scope.
- `redefineModule(target, Set.of(helperModule), ...)` adds an edge to **the specific `Module` object passed**, which can be the unnamed module of a particular loader. This approach has a narrower scope.

## 7. Java 17+ hands-on: distinguishing classpath, module read, and transformer

The experiment has **an explicit named module** `demo.named`, a helper in the **system unnamed module**, and a startup agent. Class `Target` has Java code that directly calls `demo.helper.Helper.message()`:

- The code **compiles successfully** because `javac` receives `--add-reads demo.named=ALL-UNNAMED` and knows the classpath contains Helper.
- **Running without a read edge**: Helper is still found via the system class loader, but the JVM rejects direct access linking with `IllegalAccessError`.
- **Agent with a transformer returning `null`**: the callback is invoked, but on the tested JVM there is no automatic read edge.
- **Agent with a transformer returning cloned bytes**: the JVM creates the read edge via the Instrumentation mechanism and the Helper call succeeds.
- **Agent calling `redefineModule`**: the read edge is proactively added before Target loads, and the Helper call also succeeds.
- **`--add-reads` option at runtime**: adds the read edge via the launcher, without needing an agent.

These are **independent JVM runs**, not steps toggled back and forth within the same JVM: module relationships added in one run do not automatically "turn off" afterward.

### 7.1. Directory structure

```text
module-read-demo/
├── src/
│   ├── named/
│   │   ├── module-info.java
│   │   └── demo/named/
│   │       ├── Main.java
│   │       └── Target.java
│   ├── helper/
│   │   └── demo/helper/Helper.java
│   └── agent/
│       └── demo/agent/ModuleAgent.java
└── agent.mf
```

After building, there are `mods/demo.named/` for the named module, `helper-classes/` for the helper classpath, `agent-classes/` and `agent.jar` for the startup agent.

### 7.2. `src/named/module-info.java`

```java
module demo.named {
}
```

This module **declares no `requires` or `exports`**. The launcher can still run the main class in the module with `-m demo.named/demo.named.Main`. There is no way to write `requires ALL-UNNAMED` in the descriptor. We intentionally keep the module descriptor minimal to observe the read edge added by the JVM/agent.

### 7.3. `src/helper/demo/helper/Helper.java`

```java
package demo.helper;

public final class Helper {
    private Helper() {}

    public static String message() {
        return "HELLO_FROM_HELPER";
    }
}
```

Helper is compiled into `helper-classes/` and then placed on the **classpath**. It belongs to the **unnamed module of the system class loader** in the experiment, not a named module declared by `module-info.java`.

### 7.4. `src/named/demo/named/Target.java`

```java
package demo.named;

public final class Target {
    private Target() {}

    public static String hello() {
        return demo.helper.Helper.message();
    }
}
```

This is a **direct bytecode reference** to the helper, not reflection. `javac` needs permission to read the unnamed module to compile a named module with this reference; at runtime, the JVM must also have the read edge when linking the method.

### 7.5. `src/named/demo/named/Main.java`

```java
package demo.named;

public final class Main {
    private Main() {}

    public static void main(String[] args) throws Exception {
        Module named = Main.class.getModule();
        Module helper = ClassLoader.getSystemClassLoader()
                .loadClass("demo.helper.Helper").getModule();
        System.out.println("[app] named=" + named.isNamed());
        System.out.println("[app] helperUnnamed=" + !helper.isNamed());
        System.out.println("[app] beforeRead=" + named.canRead(helper));

        try {
            System.out.println("[app] result=" + Target.hello());
        } catch (IllegalAccessError error) {
            System.out.println("[app] callFailed=IllegalAccessError");
        }

        System.out.println("[app] afterRead=" + named.canRead(helper));
    }
}
```

Key learning points:

1. `getSystemClassLoader().loadClass("demo.helper.Helper")` attempts to find the class using the loader and retrieves its `Module` for observation. This can succeed **even when `named.canRead(helper)==false`**.
2. `Target.hello()` is the operation that uses a **direct bytecode call** from the named module to the helper; without a read edge, the VM can throw `IllegalAccessError`.
3. Catching `IllegalAccessError` in this program is **for demonstration only**. You should not wrap an entire production application to swallow `LinkageError`; fix the module configuration instead.
4. `beforeRead` is measured before `Target` needs to load; `afterRead` is measured after attempting to call the method. Thus, we see the read edge appear **in the class transformation path**.

### 7.6. `src/agent/demo/agent/ModuleAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Map;
import java.util.Set;

public final class ModuleAgent {
    private ModuleAgent() {}

    public static void premain(String option, Instrumentation inst) {
        if ("manual".equals(option)) {
            Module target = ModuleLayer.boot().findModule("demo.named").orElseThrow();
            Module helper = ClassLoader.getSystemClassLoader().getUnnamedModule();
            if (!inst.isModifiableModule(target)) {
                throw new IllegalStateException("Target module cannot be modified");
            }
            inst.redefineModule(target, Set.of(helper), Map.of(),
                    Map.of(), Set.of(), Map.of());
            System.out.println("[agent] manual extraReads added");
            return;
        }

        boolean noChange = "noop".equals(option);
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain, byte[] bytes) {
                if ("demo/named/Target".equals(className)) {
                    System.out.println("[agent] observed Target");
                    if (noChange) {
                        return null;
                    }
                    System.out.println("[agent] returning cloned bytes");
                    return bytes.clone();
                }
                return null;
            }
        }, false);
        System.out.println("[agent] transformer installed mode="
                + (noChange ? "noop" : "transform"));
    }
}
```

There are three modes:

- `-javaagent:agent.jar=noop`: registers the transformer but returns `null` when `Target` is loaded. On the tested VM, there is no automatic read edge.
- `-javaagent:agent.jar`: registers the transformer and when encountering `Target` returns **`bytes.clone()`**. The JVM receives new classfile bytes with identical content, but it is treated as a transformation result, creating the read edge supporting the helper.
- `-javaagent:agent.jar=manual`: **does not register a transformer**; proactively calls `redefineModule` so the named module reads the system unnamed module. Illustrates that **adding a read edge does not require instrumenting a class**.

`ClassFileTransformer` in Java 17 **is not a functional interface** because two `transform` overloads have default methods; therefore, the example uses an anonymous class with the six-parameter `@Override`. `return null` and `return bytes.clone()` differ only in the transformation contract, not because the API changed `Target`'s method descriptor.

**Accuracy regarding bootstrap/system:** Instrumentation's special mechanism refers to the unnamed modules of the **bootstrap class loader** and **the class loader that loaded the main agent class**, with no general guarantee for an arbitrary unnamed module of a custom loader. In the example, the agent is loaded by the system loader, so using the system unnamed module itself is appropriate.

### 7.7. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.ModuleAgent

```

Keep the trailing blank line in the manifest. Because it only instruments new classes and adds a read edge, the experiment **does not need** `Can-Retransform-Classes` or `Can-Redefine-Classes`. Those two manifest capabilities relate to retransforming/redefining already loaded classes, not a prerequisite for calling `redefineModule`.

### 7.8. Compilation commands on JDK 17+

From the `module-read-demo/` directory, with **Bash**:

```bash
mkdir -p helper-classes mods/demo.named agent-classes

javac --release 17 -d helper-classes \
  src/helper/demo/helper/Helper.java

javac --release 17 \
  --add-reads demo.named=ALL-UNNAMED \
  -cp helper-classes \
  -d mods/demo.named \
  src/named/module-info.java \
  src/named/demo/named/Main.java \
  src/named/demo/named/Target.java

javac --release 17 -d agent-classes \
  src/agent/demo/agent/ModuleAgent.java

jar --create --file agent.jar --manifest agent.mf \
  -C agent-classes .
```

In **PowerShell**, run each command on **one line**; the `\` line continuation above is Bash syntax:

```powershell
New-Item -ItemType Directory -Force -Path helper-classes,mods/demo.named,agent-classes | Out-Null
javac --release 17 -d helper-classes src/helper/demo/helper/Helper.java
javac --release 17 --add-reads demo.named=ALL-UNNAMED -cp helper-classes -d mods/demo.named src/named/module-info.java src/named/demo/named/Main.java src/named/demo/named/Target.java
javac --release 17 -d agent-classes src/agent/demo/agent/ModuleAgent.java
jar --create --file agent.jar --manifest agent.mf -C agent-classes .
```

**Why does the `javac` command have `--add-reads`?** Because `Target.java` directly references the helper on the classpath, but `module-info.java` cannot declare `requires` to an unnamed module. The option lets the Java compiler see the dependency for this compilation pass. **It does not automatically write the permission into the runtime module descriptor.** When running without the agent or the corresponding option, the read edge is still absent.

The commands above have been tested with a JDK supporting `--release 17`: the generated classfiles are Java 17 compatible; no external libraries are needed. If using a shell other than Bash or PowerShell, adjust the directory creation/line continuation syntax accordingly.

## 8. Running each case and reading stdout

Each of the following commands starts **a new JVM**, run from the `module-read-demo/` directory. The module name `demo.named` is taken from `mods/demo.named/module-info.class`, while the helper is at `-cp helper-classes`.

### 8.1. Case A — No agent, no read edge

```bash
java -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Verified stdout:

```text
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=false
[app] callFailed=IllegalAccessError
[app] afterRead=false
```

**Note:** `helperUnnamed=true` shows the helper class was found and belongs to an unnamed module. However, `named.canRead(helper)==false`, so the bytecode of `Target.hello()` is not linked to Helper and the VM throws `IllegalAccessError`. This is proof that **the class loader seeing the class is not enough**.

### 8.2. Case B — Transformer present but returns `null`

```bash
java -javaagent:agent.jar=noop -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout on OpenJDK 24.0.2:

```text
[agent] transformer installed mode=noop
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=false
[agent] observed Target
[app] callFailed=IllegalAccessError
[app] afterRead=false
```

The agent is started; the JVM invokes the callback for Target. However, the callback returns `null`, meaning it provides no transformation of classfile bytes. In the experimental JVM, the read edge supporting the helper **is not created** merely because the callback ran. Therefore, the error still occurs.

Do not draw the rule "just calling addTransformer lets a named module read the classpath." There must be an actual transformation or an explicitly established read edge.

### 8.3. Case C — Transformer returns new bytes

```bash
java -javaagent:agent.jar -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Verified stdout:

```text
[agent] transformer installed mode=transform
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=false
[agent] observed Target
[agent] returning cloned bytes
[app] result=HELLO_FROM_HELPER
[app] afterRead=true
```

Here the agent returns `bytes.clone()`. Although **the byte content is unchanged**, the JVM has a returned transformation result and adds the special read edge. Result:

- `beforeRead=false` because Main runs before Target is actually transformed.
- `afterRead=true` because the module now reads the unnamed module of the loader that loaded the agent.
- `Target.hello()` links successfully with the helper and returns `HELLO_FROM_HELPER`.

**This is not advice to use purposeless cloning in real systems.** The demo intentionally returns new bytes to isolate an API mechanism. If you only need a module read edge, use `redefineModule`; if you need to actually instrument bytecode, return validly modified bytes.

### 8.4. Case D — Agent adds the read edge itself, no transform

```bash
java -javaagent:agent.jar=manual -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout:

```text
[agent] manual extraReads added
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=true
[app] result=HELLO_FROM_HELPER
[app] afterRead=true
```

During `premain`, the agent uses `redefineModule(target, Set.of(systemUnnamed), ...)`. Therefore, **right before Main calls Target**, the read edge already exists. There is no "observed Target" line because manual mode **does not register a transformer**. This is the appropriate approach when your goal is managing module relations independently of bytecode transformation.

### 8.5. Case E — Using the JVM option `--add-reads`

```bash
java --add-reads demo.named=ALL-UNNAMED \
  -cp helper-classes --module-path mods \
  -m demo.named/demo.named.Main
```

PowerShell uses a single line:

```powershell
java --add-reads demo.named=ALL-UNNAMED -cp helper-classes --module-path mods -m demo.named/demo.named.Main
```

Stdout:

```text
[app] named=true
[app] helperUnnamed=true
[app] beforeRead=true
[app] result=HELLO_FROM_HELPER
[app] afterRead=true
```

The result is the same as manual in that **the read edge exists before the method call**, but the configuration method differs: the launcher adds it at startup, without needing a Java agent.

> The stdouts A–E above were verified with a program compiled using `javac --release 17` on Zulu/OpenJDK 24.0.2. Actual errors may differ when code, module path, loader, or JVM implementation changes; the core point is the distinction between **having/lacking a read edge** and **being able/unable to call the helper**.

## 9. Readability is not enough when the helper is elsewhere

The auto-read mechanism does not automatically turn a class loader into a place that can find every JAR.

### 9.1. Helper on the system loader search path

If the agent JAR or a dependency containing the helper can be loaded by the **system class loader**, once the named module reads the system unnamed module, the instrumented class can reference public helpers from packages of the unnamed module.

Possible arrangements include:

- Placing the helper JAR on the **application classpath** at startup.
- Packaging the helper in the agent JAR loaded by the system loader, ensuring the agent and helper are packaged properly.
- Using `Instrumentation.appendToSystemClassLoaderSearch(JarFile)` to append the JAR to the system loader's search path when appropriate.

When the system class loader is a custom implementation, the specific constraints of `appendToSystemClassLoaderSearch` still apply. This is **not** an operation that turns a JAR into a named module or adds `requires` to a descriptor.

### 9.2. Helper loaded by the bootstrap class loader

Some agents place minimal helpers on the bootstrap search path:

```java
// Illustrative code in an agent; requires importing java.util.jar.JarFile.
// helperJarPath is a Path to an existing and valid JAR.
inst.appendToBootstrapClassLoaderSearch(
        new java.util.jar.JarFile(helperJarPath.toFile()));
```

Classes defined by the bootstrap loader reside in the **unnamed module of the bootstrap loader**. Instrumentation provides a read edge from the transformed class's module to this unnamed module. However, bootstrap helpers **must only link against classes that the bootstrap loader can define/find**, and must not arbitrarily depend on application/library classes visible only to the system loader.

For agents with many helpers, you need to account for colliding package names, classloader dependencies, split packages, isolation, and `NoClassDefFoundError` when a bootstrap helper mistakenly references an external library.

### 9.3. Helper in a custom class loader

If the helper resides in the unnamed module of a **separate custom loader**, Instrumentation's auto-read rule **does not by default** add a read edge to that module. You may need:

- `redefineModule(targetModule, Set.of(customUnnamedModule), ...)` to add a read edge for **that exact module**;
- designing class-loader delegation/visibility so the instrumented bytecode can actually resolve the helper;
- or moving minimal helpers to the appropriate bootstrap/system search path.

**Adding `extraReads` alone does not guarantee the loader will successfully resolve the called class.** The two conditions are independent. Calling `helperClass.getModule()` and getting an unnamed module does not mean Target's class loader can load that helper.

## 10. When the agent wants to access a named module, exports and opens are needed

So far, the direction being handled is:

```text
Target (named module) ---> Helper (unnamed module)
               required read edge
```

But agents often need to **access classes/packages of Target**:

```text
Agent (system unnamed module) ---> internal class of Target (named module)
                             |
                             +-- public access: requires package to be exported appropriately
                             |
                             +-- deep reflection: requires package to be opened appropriately
```

With normal Java code, **unexported** packages from a named module can cause `IllegalAccessError` even if the calling module sees the class. With reflection wanting to bypass access checks, the module/package must be opened appropriately, otherwise you may encounter `InaccessibleObjectException`.

**Illustrative-only** example, when an agent wants to grant the **system unnamed module** deep reflection into `demo.named` package `demo.named`:

```java
// In the agent, target is the Module of the target class.
// Only valid when "demo.named" is actually a package belonging to target.
Module agentModule =
        ClassLoader.getSystemClassLoader().getUnnamedModule();

inst.redefineModule(
    target,
    java.util.Set.of(),
    java.util.Map.of(),
    java.util.Map.of("demo.named", java.util.Set.of(agentModule)),
    java.util.Set.of(),
    java.util.Map.of()
);
```

This call **adds opens**; it does not change the module's Java source. `extraExports` and `extraOpens` must use packages **belonging to the module being modified**; passing a wrong/non-existent package will be rejected by the API.

If the goal is only for Target to call Helper in system unnamed, you **do not need** to open Target's internal packages; that is a different permission and should be avoided unnecessarily in production.

## 11. Common errors and diagnostics

| Symptom | Possible cause and resolution |
| --- | --- |
| Named module finds `Helper.class` but direct call `Helper.message()` throws `IllegalAccessError` | Missing read edge from named module to unnamed module, or improper package access. Check `Module.canRead` and exports/inspect the helper module. |
| Transformer logs output but `canRead(helper)==false` | Callback may have returned `null`, so it did not produce a transformed class like the demo. Check the bytes actually returned and the timing of the measurement. |
| `canRead=true` is observed yet `NoClassDefFoundError` still occurs | Readability does not help the loader find the JAR/class; check bootstrap/system/custom loader and search paths. |
| Accessing a public type of another named module throws `IllegalAccessError` | May need both a read edge **and exports** from the module owning the package. |
| Reflecting on a private field throws `InaccessibleObjectException` | Check **opens** of the package from the target named module to the agent module; a read edge alone is not enough. |
| Helper is placed in a separate named module | Instrumentation's auto read edge to **unnamed modules** does not substitute for `requires`/`extraReads` to a named helper module. |
| Helper placed in a custom loader does not receive auto edge | The special mechanism only guarantees unnamed modules of bootstrap and the loader loading the main agent; add the edge in a controlled way and resolve loader visibility. |
| `--add-reads` present at compile time but runtime still fails | A read edge at `javac` does not automatically become a runtime relationship. Add the option at `java`, or use Instrumentation. |
| `--add-exports` fixes public access error but private reflection still fails | `exports` does not replace `opens`; choose the right permission. |
| `redefineModule` throws `IllegalArgumentException` | Package name in `extraExports`/`extraOpens` does not belong to the module, or the map contains an empty target set / invalid data. |
| `isModifiableModule(target)==false` | The VM does not allow modifying that module; do not call `redefineModule`, which can throw `UnmodifiableModuleException`. |
| Calling `redefineModule` with an unnamed module shows no change | Per the API this is a no-op; unnamed modules already have broad read/export/open. |
| Two helpers in the same package in bootstrap and system loader cause hard-to-diagnose errors | Avoid colliding names/packages and unclear delegation structures; log the exact class loader and module of the resolved class. |
| Agent works with application classpath but fails when application moves to module path | Named modules have different readability/encapsulation than unnamed modules; need to check bytecode references and module configuration. |

### Step-by-step debugging workflow

1. Log `targetClass.getModule().getName()` and `isNamed()`; determine whether this is an **ordinary named**, **automatic**, or **unnamed module**.
2. Obtain the exact `helperClass.getModule()`, defining loader, and class source; do not use a same-named Helper from another loader.
3. Log `targetModule.canRead(helperModule)` **before/after** transformation or `redefineModule`.
4. Check whether the helper class **can be found/loaded by the relevant class loader**.
5. If the module already reads it but throws `IllegalAccessError`, check package exports, class modifiers, and the method's access check.
6. If reflection fails, check opens for the exact calling module.
7. If only transformer logs appear without an auto edge, confirm whether the transformer returned `null` or a new `byte[]`; do not assume a callback implies transformation.
8. With a separate module layer or custom loader helper, obtain the Module from the exact `Class<?>`, do not rely on a generic module name in the boot layer.
9. Run tests on a real JDK/VM, because interactions with multiple agents/transformers and class loading timing can differ from the development environment.

## 12. Lifecycle and safety notes

- `redefineModule` **only increases permissions**; there is no corresponding "undo" operation in the API. Do not open unnecessary packages/modules.
- The auto read edge mechanism for transformed classes does not replace a plan for helper JAR distribution and class-loader isolation.
- Minimize helper dependencies on internal JDK packages or unexported packages of named modules; if unavoidable, declare reads/exports/opens in the right direction, for the right module, and verify.
- When transforming already-loaded classes with `retransformClasses`/`redefineClasses`, beyond module relations you also need manifest capabilities, class modifiability, and valid schema/bytecode; these are **not** capabilities automatically granted just because `redefineModule` succeeded.
- Do not use `IllegalAccessError` as a normal fallback mechanism on the hot path; fix the module configuration before code needs to call the helper.
- With multiple Java agents, check for colliding helper packages, the main agent's loader, and class transformation order; one agent may create a read edge when a class is transformed before another agent's turn.
- Read/export/open permissions relate to module system security. Privileged agents should keep added permissions narrow in scope and audit adjustments to the runtime module graph.

## 13. Self-check questions

**Question 1.** Helper is already on the classpath and `ClassLoader.loadClass(...)` succeeds. Is a named module calling Helper directly guaranteed not to hit `IllegalAccessError`?

**Answer:** No. Loader visibility and module readability are two different conditions. The named module may not yet have a read edge to Helper's unnamed module.

**Question 2.** Are the unnamed module in the system loader and the unnamed module in a custom loader always the same object?

**Answer:** No. Each class loader can have its own unnamed module; a read edge to system unnamed does not automatically grant permission to every unnamed module of another loader.

**Question 3.** In the experiment, why did `noop` mode print "observed Target" while `afterRead=false`?

**Answer:** The callback returned `null`, providing no transformed bytes. The tested JVM only adds the auto read edge for a **transformed** class, not merely an observed one.

**Question 4.** Why does `return bytes.clone()` make `afterRead=true` even though the method body did not change?

**Answer:** The transformer returned a new classfile byte array (equivalent content), enough for the JVM to consider the class as having gone through transformation, thereby adding the read edge per the Instrumentation mechanism.

**Question 5.** If an agent wants a read edge without modifying the class, what should it do?

**Answer:** Call `Instrumentation.redefineModule(targetModule, Set.of(helperModule), ...)` after checking `isModifiableModule`, or use `--add-reads` at startup. There is no need to clone bytes needlessly.

**Question 6.** Is `--add-reads demo.named=ALL-UNNAMED` identical to `redefineModule(target, Set.of(oneUnnamed), ...)`?

**Answer:** Not completely. The launcher option lets the named module read unnamed modules, whereas the API allows specifying a **specific Module** in `extraReads`.

**Question 7.** To have an agent read a private field of `demo.named.Internal`, is adding a read edge from named to unnamed enough?

**Answer:** No. That is the reverse direction. You need to ensure the package is **opens** to the agent module for deep reflection, along with other class/loader conditions.

**Question 8.** Does `appendToBootstrapClassLoaderSearch` automatically make a named module read every module/JAR?

**Answer:** No. It appends the JAR to the bootstrap class-loader search path. Readability is a module condition; for classes actually transformed by Instrumentation, the JVM supports a read edge to the bootstrap unnamed module. The helper must be successfully defined by the bootstrap loader.

**Question 9.** Can `ModuleLayer.boot().findModule(...)` always be used to find a target in a custom module layer?

**Answer:** No. A custom layer may not belong to the boot layer. Obtain the module from the exact `targetClass.getModule()` or the appropriate layer.

**Question 10.** Once `redefineModule` has been called to export/open a package, can a reverse API be called to revoke the permission within the same JVM?

**Answer:** No. Per the API contract, `redefineModule` only **expands** reads/exports/opens/uses/provides; it does not narrow or revoke granted permissions.

## 14. Summary and official references

**Key takeaways:**

1. **Named and unnamed modules do not have symmetric default readability:** unnamed reads broadly, whereas an ordinary named module does not read the classpath unnamed module by default.
2. **The class loader finding Helper is not enough:** for named module bytecode to call Helper, there must also be a valid read edge and package access.
3. **Instrumentation creates read edges supporting transformed classes** to the unnamed modules of the bootstrap loader and the loader that loaded the main agent class; this **does not apply by default to every custom loader**.
4. **A callback returning `null` differs from a callback returning new bytes:** the hands-on exercise proves the tested JVM does not add an auto edge for an observe-only callback.
5. **`redefineModule` is the proactive and explicit way** to add `extraReads` to a helper module; exports/opens solve package access problems in the other direction.
6. **`--add-reads` at `javac` is not enough for runtime**; add `--add-reads` at `java` or a read edge via instrumentation if needed.
7. **Do not use module reads in place of loader search paths:** the helper JAR must actually be loadable, with the right loader/module and the right API version.

**Official references for cross-checking:**

- [Java SE 17 — `java.lang.instrument` package, section “Instrumenting code in modules”](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 17 — `Instrumentation.redefineModule` and `isModifiableModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map))
- [Java SE 17 — `Module.canRead`, `isExported`, `isOpen`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JLS Java SE 17 §7.7.5 — Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.5)
- [JDK 17 launcher — `--add-reads`, `--add-exports`, `--add-opens`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JDK 17 javac — `--add-reads` when compiling modules](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)