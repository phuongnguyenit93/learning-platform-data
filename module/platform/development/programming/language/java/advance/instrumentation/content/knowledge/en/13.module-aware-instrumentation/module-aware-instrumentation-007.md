# Checking `isModifiableModule` and Handling `UnmodifiableModuleException`

> **Context:** Java Advance → Instrumentation → **Instrumentation and Modules**. Since Java 9, a Java agent can inspect and extend certain relationships in the Java Platform Module System (JPMS) using `Instrumentation.isModifiableModule` and `Instrumentation.redefineModule`. This lesson focuses on deciding whether to modify a module, exceptions when rejected, the special case of the unnamed module, valid package configuration, and how to verify access permissions after modification. The Java 17+ sample has been tested on OpenJDK 24.

## 1. The Big Picture

Suppose a Java agent wants to use reflection to observe a private method in package `demo.internal` of the named module `demo.secret`. If the package is not opened to the agent's module, `setAccessible(true)` can throw `InaccessibleObjectException`. The agent can ask the JVM to open **this exact package to the exact recipient module**, but it needs to check whether the target module can be modified:

~~~java
Module targetModule = targetClass.getModule();

if (instrumentation.isModifiableModule(targetModule)) {
    instrumentation.redefineModule(
        targetModule,
        Set.of(),
        Map.of(),
        Map.of("demo.internal", Set.of(agentModule)),
        Set.of(),
        Map.of()
    );
}
~~~

This is an **illustrative snippet**, requiring the variables `instrumentation`, `targetClass`, `agentModule`, and the corresponding imports. The full version with `premain`, manifest, named module, and runnable code is in section 6.

There are three things to distinguish:

1. **Can the module be modified?** `isModifiableModule(module)` checks whether `redefineModule` can be used with that module.
2. **Is the proposed change valid?** Is the package name right, do the sets/maps contain valid data, is the recipient module correct? `isModifiableModule == true` does **not** guarantee that every input will be accepted by the JVM.
3. **Has the change taken effect?** You must verify the actual relationship using `Module.isOpen(package, recipient)`, `Module.isExported(...)`, or `Module.canRead(...)`. `redefineModule` returns `void`, with no success boolean.

**Most common pitfall:** `isModifiableModule` **always returns `true` for an unnamed module**, yet calling `redefineModule` on an unnamed module is a **no-op**. Do not use a `true` return value to conclude that the module has had another package opened.

## 2. The `isModifiableModule(Module)` Contract

Signature:

~~~java
boolean isModifiableModule(Module module);
~~~

According to the Java SE API:

- Returns `true` if the module can be modified with `redefineModule`, otherwise returns `false`.
- For an **unnamed module**, always returns `true` by special API rule; calling `redefineModule` on an unnamed module does nothing.
- Passing `null` throws `NullPointerException`.
- Available since Java 9. This is not a variant of `isModifiableClass(Class<?>)`.

Obtaining a `Module` properly:

~~~java
Module fromType = SomeType.class.getModule();

Module fromBootLayer = ModuleLayer.boot()
        .findModule("java.base")
        .orElseThrow();
~~~

This is a **code snippet**, where `SomeType` must be an available class. If the module is in a **custom module layer** or has not been resolved, `ModuleLayer.boot().findModule("name")` may not find it. Not having the module in the boot layer **does not mean the module is unmodifiable**.

### Distinguishing `Module` and `Class`

| API | Argument Type | Question |
|---|---|---|
| `isModifiableModule(Module)` | `Module` | Can JPMS relationships be extended via `redefineModule`? |
| `isModifiableClass(Class<?>)` | `Class<?>` | Is the class of a kind that can be retransformed/redefined? |
| `isRetransformClassesSupported()` | No arguments | Do the JVM and agent have the retransformation capability? |
| `isRedefineClassesSupported()` | No arguments | Do the JVM and agent have the class redefinition capability? |

Similar names do not make them interchangeable. A modifiable module does **not** prove that every class in that module can have its method bodies modified, nor does it allow adding/removing fields via retransform. Conversely, `UnmodifiableModuleException` is **not** `UnmodifiableClassException`.

### Do not hard-code JVM modifiability

Some HotSpot/OpenJDK runtimes report `true` for specific named modules. This does not mean all JVM implementations, runtime images, and modules must return `true`. The right approach is to **check on the JVM actually running the agent**, not write logic that depends on a value observed from a single build.

## 3. What Permissions Does `redefineModule` Add?

Exact signature:

~~~java
void redefineModule(
    Module module,
    Set<Module> extraReads,
    Map<String, Set<Module>> extraExports,
    Map<String, Set<Module>> extraOpens,
    Set<Class<?>> extraUses,
    Map<Class<?>, List<Class<?>>> extraProvides
);
~~~

The parameters serve different roles:

| Parameter | Meaning | Notes |
|---|---|---|
| `module` | **Source module** to modify | Must be a `Module`, not a class or module name string |
| `extraReads` | Adds modules that the source module can read | A read edge does not by itself make an unexported package public |
| `extraExports` | Exports additional packages to a set of recipient modules | Allows access to public API per JPMS; package name must belong to the source module |
| `extraOpens` | Opens additional packages to a set of recipient modules | For deep reflection; open only the exact package and recipients needed |
| `extraUses` | Declares additional service types used by the source module | Must consider service accessibility at the usage site |
| `extraProvides` | Declares additional service implementations provided by the source module | Provider must belong to the source module, implement the service, with a valid list |

Example of adding qualified opens:

~~~java
inst.redefineModule(
    sourceNamedModule,
    Set.of(), // extraReads
    Map.of(), // extraExports
    Map.of("demo.internal", Set.of(agentModule)), // extraOpens
    Set.of(), // extraUses
    Map.of()  // extraProvides
);
~~~

**Direction of the relationship:** `sourceNamedModule` is the module **containing the package** `demo.internal`. `agentModule` is the module **receiving the open permission**. If you swap the two variables, you may accidentally perform a no-op on the agent's unnamed module or request to open a package that does not belong to the source module.

**Package name:** `demo.internal` is a dotted Java name. Do not use the internal name `demo/internal`, the class name `demo.internal.SecretBox`, or the module name `demo.secret` instead.

### Additive only, no revocation

The Javadoc specifies that `redefineModule` **cannot reduce** the set of modules read, the set of packages exported/opened, or the services used/provided. A subsequent call with empty sets/maps **does not revoke** permissions granted in an earlier call.

~~~java
inst.redefineModule(target, Set.of(), Map.of(),
        Map.of("demo.internal", Set.of(agentModule)),
        Set.of(), Map.of());

// Not a rollback:
inst.redefineModule(target, Set.of(), Map.of(), Map.of(), Set.of(), Map.of());
~~~

This is why you should not grant broad permissions just to "test if it works". Before opening a private package in production, determine the need, the scope of recipient modules, and the impact on the system.

The Javadoc also states that `redefineModule` is **safe for concurrent use**, allowing multiple agents to modify modules at the same time. However, the thread safety of each call **does not** turn an application's check-then-update sequence into a transaction. Additive changes from multiple agents can coexist.

## 4. Special Case: The Unnamed Module

Classes in a Java agent JAR loaded via `-javaagent` belong to the **unnamed module of the system class loader**. Regular Java classes on the classpath also belong to the unnamed module of their defining loader.

~~~java
Module agentModule = AgentEntry.class.getModule();

boolean named = agentModule.isNamed(); // false in a standard agent JAR
boolean modifiable = inst.isModifiableModule(agentModule); // true
inst.redefineModule(agentModule,
        Set.of(), Map.of(), Map.of(), Set.of(), Map.of()); // no-op
~~~

This is an **illustrative snippet**, where `AgentEntry`/`inst` are the class and variable in the agent context.

Both of the following statements are true:

- `inst.isModifiableModule(unnamedModule) == true`.
- `inst.redefineModule(unnamedModule, ...)` is a **no-op**, adding no observable read/open/export edge of effect.

Do not try to "redefine the unnamed module" to grant the agent deep reflection access into another named module. Instead, you must open the package on the **named module that owns the package**, and list the agent's unnamed module as the **recipient** if it is the one needing reflection.

**Other cases to note:**

- `String.class.getModule()` is the named module `java.base`, even though `String.class.getClassLoader() == null`.
- `AgentEntry.class.getModule().getName()` is `null` for an unnamed module; this does not mean the class has no module.
- Each class loader has its own unnamed module. Two classes from two different loaders both having `isNamed() == false` does not guarantee they share the same module object.
- Not every class defined by the system loader is in an unnamed module: a named application module can also be defined by the system loader.

## 5. `UnmodifiableModuleException` and Easily Confused Exceptions

Full name: `java.lang.instrument.UnmodifiableModuleException`. This exception has existed since Java 9 and **extends `RuntimeException`**, so it is an unchecked exception. Per the API, `Instrumentation.redefineModule(...)` can throw it when a module cannot be modified.

| Symptom | Exception / Result | Correct Interpretation |
|---|---|---|
| `inst.isModifiableModule(target) == false` | Boolean `false` | Module is not modifiable according to the check; skip operation, choose fallback |
| `inst.redefineModule(...)` encounters an unmodifiable module | `UnmodifiableModuleException` | Catch and report failure branch; do not pretend it succeeded |
| `extraOpens` points to a package not in the module | `IllegalArgumentException` | **Invalid argument**, not necessarily an unmodifiable module |
| Recipient set of extraOpens/extraExports is empty | `IllegalArgumentException` | Missing recipient module |
| Module/sets/maps parameter or required element is `null` | `NullPointerException` | Input/logic bug that must be fixed |
| Reflection into an unopened package | `InaccessibleObjectException` | Deep reflection not yet permitted, distinct from a redefineModule error |
| `retransformClasses` on a non-modifiable class | `UnmodifiableClassException` | **Class redefinition** error, not module reconfiguration |
| `retransformClasses` causes an unsupported class schema change | `UnsupportedOperationException` | Do not infer that the module is unmodifiable |

### Deliberate handling

Recommended workflow:

1. Verify that the module reference is not `null`, and has the expected name and module layer.
2. Determine named/unnamed via `Module.isNamed()`. If unnamed, do not call redefinition expecting to change module relationships.
3. Verify that the package actually belongs to the source module via `module.getPackages().contains(packageName)`.
4. If `module.isOpen(packageName, recipient)` is already `true`, no need to open it again.
5. If `!inst.isModifiableModule(module)`, take the **unsupported** branch. Do not call `redefineModule` just to ignore the result.
6. If proceeding, call `redefineModule` with **non-null and valid** sets/maps, catching `UnmodifiableModuleException`/`IllegalArgumentException` separately.
7. After a successful call, re-check `isOpen` or the equivalent check for the intended modification type.
8. If opening is not possible, choose a fallback: public API, instrumentation without private reflection, approved launcher configuration, or disabling the optional feature.

**Prechecks do not replace catch blocks.** One API returns a boolean for modifiability and another has a contract that can throw an exception; when building a robust agent, you still must handle the exception path. Avoid catching `RuntimeException` broadly and printing "module is unmodifiable", as argument errors would be masked.

### Defensive helper example

The following snippet assumes it is inside a Java agent with `Instrumentation inst` and the corresponding imports; **it is not a standalone Java file**:

~~~java
static boolean openPackage(Instrumentation inst, Module source,
                           String packageName, Module recipient) {
    if (inst == null || source == null || packageName == null || recipient == null) {
        throw new IllegalArgumentException("Missing required arguments");
    }
    if (!source.isNamed()) {
        return false; // unnamed: redefineModule is a no-op
    }
    if (!source.getPackages().contains(packageName)) {
        return false; // do not call API with an invalid package
    }
    if (source.isOpen(packageName, recipient)) {
        return true; // already has permission
    }
    if (!inst.isModifiableModule(source)) {
        return false; // module does not allow modification
    }

    try {
        inst.redefineModule(source, Set.of(), Map.of(),
                Map.of(packageName, Set.of(recipient)), Set.of(), Map.of());
        return source.isOpen(packageName, recipient);
    } catch (UnmodifiableModuleException e) {
        return false; // deliberate log/fallback in a real agent
    } catch (IllegalArgumentException e) {
        return false; // configuration error, must not be called unmodifiable
    }
}
~~~

This helper avoids modifying the module if unnecessary. In production, you should log concisely enough to distinguish the `false`, `IllegalArgumentException`, and `UnmodifiableModuleException` branches, without logging private data or unstable messages as a standard error code.

## 6. Java 17+ Lab: Checking a Module, Opening a Package, and Testing Error Branches

This is a **runnable experiment requiring no external libraries**. It uses:

- Named module `demo.secret` containing `demo.internal.SecretBox`, without exporting/opening the package.
- Startup Java agent `ModuleProbeAgent`. The agent checks named/unnamed modules and calls `redefineModule` to open the package to the agent's unnamed module.
- App `Launcher` that simply prints a marker in `main`.
- A **`Instrumentation` test double** created with `Proxy` that intentionally throws `UnmodifiableModuleException` to test the exception-handling code. **This is not an error raised by the real JVM**.
- A real `redefineModule` call using an invalid package to observe `IllegalArgumentException`.

### 6.1 Project structure

~~~text
module-modifiability-lab/
├── manifest.mf
├── src-agent/
│   └── demo/
│       └── agent/
│           └── ModuleProbeAgent.java
├── src-mod/
│   └── demo.secret/
│       ├── module-info.java
│       └── demo/
│           └── internal/
│               └── SecretBox.java
├── src-app/
│   └── demo/
│       └── app/
│           └── Launcher.java
└── out/                     # created by build commands
    ├── agent/
    ├── mods/
    ├── app/
    └── module-agent.jar
~~~

Requires JDK 17+, `javac`, `jar`, and `java` commands. Run all commands in the project root directory. The `out` directory is created during compilation.

### 6.2 Module needing a package opened

`src-mod/demo.secret/module-info.java`:

~~~java
module demo.secret { }
~~~

This is a **named module**. The descriptor has neither `exports demo.internal` nor `opens demo.internal`. That package is not open to the agent's module when the JVM starts.

`src-mod/demo.secret/demo/internal/SecretBox.java`:

~~~java
package demo.internal;

public final class SecretBox {
    private SecretBox() {}

    private static String secret() {
        return "OPENED";
    }
}
~~~

The class is public, but the private static method `secret()` cannot be deep-accessed from the agent's unnamed module if the package is not open. After the agent opens the exact package via `extraOpens`, `setAccessible(true)` on this private method will succeed on the test runtime.

### 6.3 Application

`src-app/demo/app/Launcher.java`:

~~~java
package demo.app;

public final class Launcher {
    public static void main(String[] args) {
        System.out.println("[APP] main");
    }
}
~~~

The application **does not import** the private class or the agent. It only proves that `premain` runs before `main`. The module `demo.secret` must be resolved via the `--add-modules demo.secret` option on the Java command, because there is no module dependency from the app classpath.

### 6.4 Java agent: `src-agent/demo/agent/ModuleProbeAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableModuleException;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;
import java.util.Set;

public final class ModuleProbeAgent {
    private ModuleProbeAgent() {}

    public static void premain(String options, Instrumentation inst) throws Exception {
        Module agent = ModuleProbeAgent.class.getModule();
        Module target = ModuleLayer.boot().findModule("demo.secret").orElseThrow();

        System.out.println("[AGENT] unnamed=" + !agent.isNamed());
        System.out.println("[AGENT] unnamedModifiable=" + inst.isModifiableModule(agent));
        inst.redefineModule(agent, Set.of(), Map.of(), Map.of(), Set.of(), Map.of());
        System.out.println("[AGENT] unnamedRedefine=no-op");

        System.out.println("[TARGET] name=" + target.getName());
        System.out.println("[TARGET] modifiable=" + inst.isModifiableModule(target));
        System.out.println("[TARGET] openBefore=" + target.isOpen("demo.internal", agent));

        Class<?> type = Class.forName("demo.internal.SecretBox", false,
                ClassLoader.getSystemClassLoader());
        Method method = type.getDeclaredMethod("secret");
        boolean accessibleBefore;
        try {
            method.setAccessible(true);
            accessibleBefore = true;
        } catch (InaccessibleObjectException expected) {
            accessibleBefore = false;
        }
        System.out.println("[REFLECT] accessibleBefore=" + accessibleBefore);

        // Test double: verifies the exception branch; not a real JVM throwing this error.
        simulateUnmodifiable(target, "demo.internal", agent);

        boolean applied = openPackage(inst, target, "demo.internal", agent);
        System.out.println("[TARGET] openApplied=" + applied);
        System.out.println("[TARGET] openAfter=" + target.isOpen("demo.internal", agent));
        if (applied) {
            method.setAccessible(true);
            System.out.println("[REFLECT] result=" + method.invoke(null));
        }

        // Argument error from the real JVM: package does not exist in the source module.
        try {
            inst.redefineModule(target, Set.of(),
                    Map.of("demo.missing", Set.of(agent)), Map.of(), Set.of(), Map.of());
            System.out.println("[INVALID] unexpectedlyAccepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("[INVALID] rejected=" + expected.getClass().getSimpleName());
        }
    }

    private static void simulateUnmodifiable(
            Module source, String pkg, Module recipient) {
        Instrumentation fake = (Instrumentation) Proxy.newProxyInstance(
                Instrumentation.class.getClassLoader(),
                new Class<?>[]{Instrumentation.class},
                (proxy, method, args) -> {
                    if ("isModifiableModule".equals(method.getName())) return true;
                    if ("redefineModule".equals(method.getName()))
                        throw new UnmodifiableModuleException("deliberate test double");
                    throw new UnsupportedOperationException(method.getName());
                });
        System.out.println("[SIMULATED] openApplied="
                + openPackage(fake, source, pkg, recipient));
    }

    private static boolean openPackage(Instrumentation inst, Module source,
            String pkg, Module recipient) {
        if (!source.isNamed()) {
            System.out.println("[OPEN] unnamedNoOp");
            return false;
        }
        if (!inst.isModifiableModule(source)) {
            System.out.println("[OPEN] moduleNotModifiable");
            return false;
        }
        if (source.isOpen(pkg, recipient)) {
            System.out.println("[OPEN] alreadyOpen");
            return true;
        }
        try {
            inst.redefineModule(source, Set.of(), Map.of(),
                    Map.of(pkg, Set.of(recipient)), Set.of(), Map.of());
            return true;
        } catch (UnmodifiableModuleException e) {
            System.out.println("[OPEN] rejected=UnmodifiableModuleException");
            return false;
        } catch (IllegalArgumentException e) {
            System.out.println("[OPEN] invalidArguments");
            return false;
        }
    }
}
~~~

This is a **complete compilable file**. When using a real agent, you should extend `openPackage` with `source.getPackages()` validation and `null` checks like the helper in section 5; in the lab, the two error cases are demonstrated separately for easier observation.

### 6.5 Understanding the two execution paths: test double and real JVM

**Simulated branch:** `simulateUnmodifiable(...)` creates a `Proxy` implementing `Instrumentation`. When `openPackage` calls `isModifiableModule`, the proxy returns `true`. When it calls `redefineModule`, the proxy throws `UnmodifiableModuleException`. This proves the catch branch returns `false` and does not crash the program. It **does not** prove that the `demo.secret` module is actually unmodifiable.

**Real branch:** right after the test double, the agent passes the **real `inst`** from the JVM into `openPackage`. On the tested HotSpot/OpenJDK, this named module is modifiable; the call with valid `extraOpens` succeeds and the package becomes open to the agent. At that point `Method.setAccessible(true)` is allowed and invocation returns the string `OPENED`.

**Real negative test:** after opening, a `redefineModule` call puts `demo.missing` into `extraExports`; that package does not belong to module `demo.secret`, so the JVM throws `IllegalArgumentException`. This error has a **different cause** from `UnmodifiableModuleException`.

### 6.6 Manifest and build commands

`manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ModuleProbeAgent

~~~

There is a newline and a trailing blank line in the manifest. `-javaagent` uses `Premain-Class`, without needing `Agent-Class`, `Can-Retransform-Classes`, or `Can-Redefine-Classes`, because we are **not** performing class retransformation/redefinition.

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/mods out/app

javac --release 17 -d out/agent src-agent/demo/agent/ModuleProbeAgent.java
javac --release 17 --module-source-path src-mod -d out/mods -m demo.secret
javac --release 17 -d out/app src-app/demo/app/Launcher.java
jar --create --file out/module-agent.jar --manifest manifest.mf -C out/agent .

java -javaagent:out/module-agent.jar --module-path out/mods --add-modules demo.secret -cp out/app demo.app.Launcher
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/mods, out/app | Out-Null

javac --release 17 -d out/agent src-agent/demo/agent/ModuleProbeAgent.java
javac --release 17 --module-source-path src-mod -d out/mods -m demo.secret
javac --release 17 -d out/app src-app/demo/app/Launcher.java
jar --create --file out/module-agent.jar --manifest manifest.mf -C out/agent .

java "-javaagent:out/module-agent.jar" --module-path out/mods --add-modules demo.secret -cp out/app demo.app.Launcher
~~~

The final PowerShell command is written on **a single line** so it does not depend on line-continuation characters. The different `javac` commands correspond to the **agent class** and the **named module**. `--module-source-path src-mod` requires the exact `src-mod/demo.secret` directory containing `module-info.java`. The `--add-modules demo.secret` option makes the JVM resolve the named module into the boot layer so the agent can find it.

You can inspect the JAR:

~~~bash
jar --list --file out/module-agent.jar
~~~

The JAR must contain `META-INF/MANIFEST.MF` and `demo/agent/ModuleProbeAgent.class`. The agent is invoked by the JVM via `-javaagent`, so there is no need to put the agent JAR itself on `-cp`.

### 6.7 Verified stdout on OpenJDK 24

The Java files were compiled with `javac --release 17` and run on OpenJDK 24. Stdout:

~~~text
[AGENT] unnamed=true
[AGENT] unnamedModifiable=true
[AGENT] unnamedRedefine=no-op
[TARGET] name=demo.secret
[TARGET] modifiable=true
[TARGET] openBefore=false
[REFLECT] accessibleBefore=false
[OPEN] rejected=UnmodifiableModuleException
[SIMULATED] openApplied=false
[TARGET] openApplied=true
[TARGET] openAfter=true
[REFLECT] result=OPENED
[INVALID] rejected=IllegalArgumentException
[APP] main
~~~

Accurate interpretation by **source of each line**:

| Marker | Source | Evidence |
|---|---|---|
| `[AGENT] unnamed=true` | Real JVM | The agent is in an unnamed module |
| `unnamedModifiable=true` | Real JVM | `isModifiableModule` contract for unnamed modules |
| `unnamedRedefine=no-op` | Real JVM | `redefineModule` on an unnamed module does not change relationships |
| `[TARGET] modifiable=true` | Real JVM | Module `demo.secret` is modifiable **in the tested runtime** |
| `openBefore=false` | Real JVM | Package is not yet open to the agent |
| `accessibleBefore=false` | Real JVM | Deep reflection is denied |
| `[OPEN] rejected=UnmodifiableModuleException` | **Test double** | Helper's catch block works with a simulated error |
| `[SIMULATED] openApplied=false` | **Test double** | Falls back to `false` instead of crashing the program |
| `[TARGET] openApplied=true` | Real JVM | `redefineModule` opens the valid package |
| `openAfter=true` | Real JVM | The new opens relationship is present |
| `[REFLECT] result=OPENED` | Real JVM | Reflection into the private method succeeds after opening |
| `[INVALID] rejected=IllegalArgumentException` | Real JVM | Invalid package in extraExports configuration |
| `[APP] main` | Real JVM | Application runs after agent startup |

**Do not call `[OPEN] rejected=UnmodifiableModuleException` a real JVM error**: it was produced by the `Proxy`. The actual test in that runtime shows `demo.secret` is modifiable and its package can be opened. Another JVM may have different module modifiability or access behavior; do not hard-code `true` for every named module.

## 7. Variations to Try to Understand the Mechanism

**Experiment 1 — omit the module from the boot layer:** remove `--add-modules demo.secret` while keeping `--module-path out/mods`. When the agent calls `ModuleLayer.boot().findModule("demo.secret").orElseThrow()`, `NoSuchElementException` may occur because the module has not been resolved. This is a **resolution issue**, not an unmodifiable module.

**Experiment 2 — wrong package:** change the real call to `Map.of("demo.missing", Set.of(agent))` in `extraOpens`. It fails with `IllegalArgumentException` because the package does not belong to the source. Even when `isModifiableModule(target) == true`, this request is still invalid.

**Experiment 3 — module reports false:** in the proxy test double, change `isModifiableModule` from returning `true` to `false`. Then `openPackage` prints `moduleNotModifiable` and returns `false` **before** calling `redefineModule`. This tests the `false` branch with controlled simulation, without relying on the JVM providing an unmodifiable module.

**Experiment 4 — package already open:** run the module with a launcher configuration containing `--add-opens demo.secret/demo.internal=ALL-UNNAMED`. When the package is already open to the agent's unnamed module, `isOpen(...)` may initially be `true` and reflection before the agent's call will no longer be denied. Lesson: **do not hard-code the verified stdout of the default environment after changing flags**.

**Experiment 5 — testing null errors:** calling `inst.isModifiableModule(null)` must throw `NullPointerException` per the contract. Only test inside a try-catch block; do not use null as a valid Module. For `redefineModule`, all six parameters and elements within sets/maps must obey the non-null rule.

## 8. Fallback Options When a Module Cannot Be Modified

There is no safe or valid way to "ignore" an `UnmodifiableModuleException` and assume permission was granted. When an agent needs reflection but the runtime does not allow modifying the module:

- **Prefer public APIs** or other hooks to reduce the need for deep reflection.
- **Configure at JVM startup** if you control the launcher and the system owner approves. For example, opening the package at startup can use `--add-opens demo.secret/demo.internal=ALL-UNNAMED`. This is **broader** than a qualified open dedicated to one module in the example; consider the blast radius.
- **Edit the module descriptor** if the project owns the source: `opens demo.internal to specific.named.module;` (if the recipient module is designed appropriately), instead of performing disallowed runtime modification.
- **Disable the feature** requiring this permission, record a clear status such as `MODULE_ACCESS_UNAVAILABLE`, and do not report fake success metrics/tracing.
- **Diagnose per JVM**: vendor, JDK version, module name/layer, package, recipient, and specific exception. Do not infer from a generic "agent failed" message.

Illustrative fallback startup command on a supporting JVM:

~~~bash
java --module-path out/mods --add-modules demo.secret --add-opens demo.secret/demo.internal=ALL-UNNAMED -cp out/app demo.app.Launcher
~~~

This command only illustrates **opens permission declared at the launcher**; without an agent there is no code using reflection. It differs from opening a package to **only one recipient module** via `redefineModule` and should not be treated as a default replacement in production.

## 9. Quick Diagnosis Table

| Symptom | Plausible Cause | Action |
|---|---|---|
| `isModifiableModule(unnamed) == true` but redefine changes nothing | For unnamed, `redefineModule` is a no-op | Identify the exact **named source module** containing the package |
| `isModifiableModule(named) == false` | Module is not modifiable per runtime | Skip operation, use fallback |
| `UnmodifiableModuleException` | JVM cannot modify the module in the call | Catch separately; do not misinterpret as a class error |
| `IllegalArgumentException` | Wrong package, empty recipient, or invalid provider | Validate sets/maps and package name |
| `NullPointerException` | Module/arg/collection contains null | Fix input logic instead of trying to catch and continue |
| `InaccessibleObjectException` | Package not yet open to caller/agent | Check source module, package, recipient, and `isOpen` |
| `ClassNotFoundException` | Wrong classloader or unresolved module | Check module path, layer, loader |
| `NoSuchElementException` from `orElseThrow()` | Module name not in the queried layer | Use the right ModuleLayer, `--add-modules` if needed |
| `isOpen(pkg, recipient) == false` after call | Call did not open the right relationship or failed | Check named/unnamed, extraOpens, and return/exception |
| `isModifiableClass(clazz) == true` | Only answers about a **class** | Do not substitute for `isModifiableModule` |
| `--add-opens` resolves reflection | Launcher pre-granted permission | Evaluate scope; do not open more than required |
| Test double prints `UnmodifiableModuleException` | Proxy threw the error by design | Do not report this as a real error from HotSpot |

## 10. Self-Check Questions

1. **What parameter type does `isModifiableModule` take?** `Module`, not `Class<?>`.
2. **What happens if `null` is passed to `isModifiableModule`?** Throws `NullPointerException`.
3. **Why does an unnamed module always return `true`?** By specification, `redefineModule` on an unnamed module is a no-op.
4. **Does a modifiable named module mean any package can be opened arbitrarily?** No; the package must belong to the module and the arguments must be valid.
5. **Which exception indicates a module cannot be modified?** `UnmodifiableModuleException`.
6. **Is this exception checked or unchecked?** Unchecked, extending `RuntimeException`.
7. **How does it differ from `UnmodifiableClassException`?** One exception is for module configuration; the other is for class retransformation/redefinition.
8. **How do you measure whether a package is actually open to the agent?** `source.isOpen(packageName, agentModule)`.
9. **If the source module is unnamed, does opening it make it a named module?** No.
10. **How do `extraExports` and `extraOpens` differ?** Exports are for public API visibility; opens are for deep reflection.
11. **Can `redefineModule` be used to remove previously granted opens?** No; the API is additive only.
12. **Why does the lab need `Proxy`?** To test the `UnmodifiableModuleException` catch block deterministically; the tested JDK does not raise a real error for that module.
13. **What does a non-existent package error throw?** `IllegalArgumentException`, which must not be called `UnmodifiableModuleException`.
14. **If a module is in a custom layer, does `ModuleLayer.boot()` always find it?** No; you must use the right layer.

## 11. Agent Design Checklist

- [ ] Obtain the right source `Module`, the right module layer, and determine named/unnamed.
- [ ] For unnamed modules, note `isModifiableModule=true` but do not mistake a `redefineModule` no-op for a real change.
- [ ] Check `isModifiableModule` for a named module before modifying it.
- [ ] Catch `UnmodifiableModuleException` separately; distinguish `IllegalArgumentException` and `NullPointerException`.
- [ ] Verify the source package belongs to the module and the recipient module set is non-empty.
- [ ] Grant only the minimum `extraReads`/`extraExports`/`extraOpens`/services needed.
- [ ] Re-verify `isOpen`, `isExported`, or `canRead` after applying.
- [ ] Do not use `isModifiableClass`/retransform capability in place of `isModifiableModule`.
- [ ] Separate reflection, class loading, module resolution, and module reconfiguration errors.
- [ ] Test the error branch with a test double; in reports clearly distinguish simulated and real JVM behavior.
- [ ] If the package cannot be opened, have a clear fallback and do not report fake success.
- [ ] Do not expect a subsequent `redefineModule` to revoke previously added relationships.

## Authoritative References

- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isModifiableModule`, `redefineModule`, unnamed values, parameters, errors, and concurrency.
- [Java SE 21 — `UnmodifiableModuleException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableModuleException.html): unchecked exception when a module cannot be modified.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): Java 17+ signatures and contract.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `isNamed`, `isOpen`, `getPackages`, `isExported`, and `canRead`.
- [Java SE 21 — `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): deep reflection when a module does not open a package.
- [JLS 21 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): package exports/opens, named and unnamed modules.
