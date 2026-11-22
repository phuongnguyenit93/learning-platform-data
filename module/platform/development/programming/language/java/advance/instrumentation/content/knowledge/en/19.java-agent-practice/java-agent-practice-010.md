# Testing a Strongly Encapsulated Module and Adding Only the Required Relationships

In Java Instrumentation experiments, an agent often needs to observe a class inside a **named module** whose package is neither `exports`ed nor `opens`ed externally. Even if the agent can locate the `Class<?>` by name, invoking a public method via reflection can still be rejected; accessing a private member is rejected even more strictly. In another case, injected bytecode needs to use a helper in **another module**, but the target module does not have a readability relationship to the helper.

The right approach is not to "open the entire module," but to identify **which relationship is actually missing** and **which module actually needs the permission**:

- **Readability**: Does module A read module B? `A.canRead(B)`.
- **Qualified export**: Does package `p` of A allow B to access public types and public members through the corresponding mechanisms? `A.isExported("p", B)`.
- **Qualified open**: Does package `p` of A allow B to perform *deep reflection* on non-public members? `A.isOpen("p", B)`.
- **Class-loader visibility**: Can the class loader actually locate the class/helper? This is a **separate** condition and is not automatically resolved by read/export/open.

In the **Java Advance – instrumentation** module, under **Agent Experiments**, this lesson builds a Java 17+ program with **two named modules and one startup agent**, sequentially confirming that access is denied and then using `Instrumentation.redefineModule(...)` to add the exact three required relationships. Each step is verified against actual execution output and further validated to ensure that **unrelated modules do not receive permissions**.

## 1. Objectives of the Experiment

After completing this lesson, you should be able to:

1. Create a named module with **strong encapsulation**: an internal package exists and contains a public class, but has no `exports` and no `opens`.
2. Distinguish between three scenarios: missing a read edge, missing an export for public access, and missing an open for deep reflection.
3. Use `Module.canRead`, `Module.isExported`, `Module.isOpen`, `Method.invoke`, and `Method.trySetAccessible` to **observe the difference**, rather than guessing from `module-info.java` alone.
4. Modify relationships at **runtime** using `Instrumentation.redefineModule`, with `Set.of(...)` containing only the module receiving the permission.
5. Prove that after granting permissions to the agent, the package is not unconditionally exported/opened and does not automatically grant access to a third module.
6. Recognize the limitations: modifying the runtime graph **does not edit the module descriptor in source**, does not change class loader delegation, does not grant private access when only `exports` is present, and does not automatically guarantee correct bytecode weaving.

## 2. "Strong Encapsulation" in the Java Platform Module System

In Java 9+, `module-info.java` describes the dependencies and package boundaries of a **named module**. For example:

```java
module demo.secure {
}
```

When the module contains package `demo.secret` but does not declare:

```java
exports demo.secret;
opens demo.secret;
```

code in other modules cannot access that package by default. In particular:

- **Having a `public` class is not enough**. If its package is not exported to the caller's module, Java access control can block invoking a public method via reflection.
- **Having an export is not enough for private access**. Deep reflection on a private method/field generally requires the package to be **open** to the module performing reflection.
- `opens` enables deep reflection, which is broader than export in many scenarios. A package opened to module B is also treated as exported to B at **runtime** according to `Module.isExported(package, B)`; however, **export alone does not imply open**.
- `exports p to moduleB;` and `opens p to moduleB;` are relationships **qualified by target module**, not open to every module.
- A non-exported/non-opened package does not mean a class cannot be found. Class loading, module accessibility, and reflective access are separate layers.

> **Strong encapsulation is not an absolute security sandbox against a trusted agent in the same JVM.** An agent with `Instrumentation` and permission to modify the module graph can actively expand permissions at runtime; therefore, only load agents from trusted sources and tightly control the scope of granted permissions.

### 2.1. Permission Matrix

| Observed Condition | `canRead` | `isExported` | `isOpen` | Meaning |
| --- | --- | --- | --- | --- |
| Module A reads B | `A.canRead(B)` | Does not change automatically | Does not change automatically | Adds a read edge for module A; does not yet grant A access to all packages of B |
| Module A exports package `p` to B | Does not add a read edge automatically | `A.isExported("p", B)=true` | May still be `false` | B can access public APIs of `p` when other conditions are met |
| Module A opens `p` to B | Does not add a read edge automatically | Treated as exported at runtime to B | `A.isOpen("p", B)=true` | Code in B can request to suppress access checks during reflection on `p` |
| Unconditional export/open | Does not imply all read edges | `isExported("p")` or `isOpen("p")` | Broader than a single target | Should not be granted broadly if only one agent needs access |

An **unnamed** module (such as an agent on the classpath) reads all modules, but **that does not cause every named module to export/open its packages to it**. This is why the agent can locate `demo.secret.Hidden` yet still be blocked at `Method.invoke`.

## 3. `Instrumentation.redefineModule`: Adding Only the Necessary Permissions

The agent receives `Instrumentation` from `premain` or `agentmain`. The Java 9+ API signature is:

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

Meaning of the parameters:

| Parameter | What does it add? | Example Need |
| --- | --- | --- |
| `module` | The module **being modified** | `demo.secure`, which is the source of the read edge/export/open |
| `extraReads` | Set of additional modules that `module` will read | Instrumented code in `demo.secure` needs to read named module `demo.helper` |
| `extraExports` | Packages in `module` additionally exported to target modules | Agent needs to call a public method of `demo.secret.Hidden` |
| `extraOpens` | Packages in `module` additionally opened for deep reflection to target modules | Agent needs to access private method `Hidden.token()` |
| `extraUses` | Additional service interfaces used by the module | Use only when instrumentation genuinely needs a service-loading relationship |
| `extraProvides` | Additional service providers provided by the module | Use only when there is an actual matching service provider |

This lesson does not use Java ServiceLoader services, so it passes empty `Set.of()` and `Map.of()` for the last two parameters. **Do not add service permissions just because the API has those parameters.**

Key rules to know:

- `redefineModule` **only expands** the sets of reads/exports/opens/uses/provides. This API **does not remove** a previously added permission and cannot be used to restore the module graph to its initial state.
- If `module` is an unnamed module, the API is a **no-op**. The target to modify in this lesson is the **named module `demo.secure`**, not the agent's unnamed module.
- Call `inst.isModifiableModule(target)` before operating. If the JVM does not allow modifying the module, report that it is unsupported; do not try to bypass it by writing directly to JDK internal structures.
- Keys in `extraExports`/`extraOpens` must be **packages that actually belong to the module being modified**, for example `"demo.secret"`. Values must be **non-empty** sets of target modules.
- `Map.of("demo.secret", Set.of(agentModule))` grants permission to **one specific module**; this is vastly different from `--add-opens demo.secure/demo.secret=ALL-UNNAMED`, which allows all unnamed modules to access that package.
- The fact that the JVM allows adding edges does not guarantee they are well-designed. Each edge must be justified by an actual use case.

## 4. Experiment Architecture

We build two named modules:

1. **`demo.secure`**: contains `demo.app.Main` and `demo.secret.Hidden`. This module **does not export/open** package `demo.secret`; `Hidden` has `public static greeting()` and `private static token()`.
2. **`demo.helper`**: contains class `helper.api.Bridge` and exports package `helper.api`. This is a named module present in the boot layer, but initially **`demo.secure` does not read it**.

The startup agent **`probe.AccessAgent`** resides in the unnamed module of the system class loader. The agent receives `Instrumentation`, checks the three conditions, and then adds them one by one:

```text
(1) demo.secure --reads--> demo.helper

(2) demo.secure --exports demo.secret --> agent unnamed module

(3) demo.secure --opens demo.secret --> agent unnamed module

                      (no export/open granted to demo.helper)
```

### 4.1. Visualizing the Module Graph

```text
Named module: demo.secure
  +-- demo.app.Main
  +-- demo.secret.Hidden      [no exports/opens in module-info]

Named module: demo.helper
  +-- helper.api.Bridge       [exports helper.api]

Unnamed module: agent
  +-- probe.AccessAgent

Before:
    demo.secure --X--> demo.helper           (no read)
    demo.secure/demo.secret --X--> agent      (no export/open)
    demo.secure/demo.secret --X--> demo.helper

After:
    demo.secure ------READS------> demo.helper
    demo.secure/demo.secret --EXPORTS------> agent unnamed
    demo.secure/demo.secret --OPENS--------> agent unnamed
    demo.secure/demo.secret --X------------> demo.helper
```

**Be careful with edge direction:** `extraReads` has `demo.secure` as its source module; `extraExports` and `extraOpens` also modify `demo.secure`, but the module receiving the permission is the **agent unnamed module**. Because the agent belongs to an unnamed module, it already reads all named modules; there is no need to add an `agent → demo.secure` edge.

In the demo, the `extraReads` part is **verified only via the runtime module graph** using `canRead`. It does not pretend to prove that a method is linked to `Bridge`, because no such `invokestatic` call has been injected into bytecode. The export and open scenarios are verified using **actual reflection calls**.

## 5. Java 17+ File Structure

```text
module-access-lab/
├── agent.mf
├── agent-src/
│   └── probe/
│       └── AccessAgent.java
├── src/
│   ├── demo.secure/
│   │   ├── module-info.java
│   │   └── demo/
│   │       ├── app/
│   │       │   └── Main.java
│   │       └── secret/
│   │           └── Hidden.java
│   └── demo.helper/
│       ├── module-info.java
│       └── helper/
│           └── api/
│               └── Bridge.java
└── out/                            # created by build commands
    ├── agent/
    ├── mods/
    └── access-agent.jar
```

Use the **exact file names and paths**, because `javac --module-source-path` relies on the module directory names (`demo.secure`, `demo.helper`) to place classes in the right modules.

### 5.1. Strongly Encapsulated Named Module

File `src/demo.secure/module-info.java`:

```java
module demo.secure {
}
```

No `exports demo.secret`, no `opens demo.secret`, no `requires demo.helper`. This intentionally tests strong encapsulation.

File `src/demo.secure/demo/secret/Hidden.java`:

```java
package demo.secret;

public final class Hidden {
    private Hidden() {}

    public static String greeting() {
        return "public-ok";
    }

    private static String token() {
        return "private-ok";
    }
}
```

Both the class and `greeting()` are **public**, yet the package is still not exported to the agent. `token()` is **private**, so even if the package is exported to the agent, deep reflection into this method still requires the appropriate `opens` permission.

File `src/demo.secure/demo/app/Main.java`:

```java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app: running");
    }
}
```

The main program does not import the agent itself. All observation/permission granting happens in `premain`; the `app: running` line indicates that the application still starts up after the agent experiment completes.

### 5.2. Helper Named Module to Test `extraReads`

File `src/demo.helper/module-info.java`:

```java
module demo.helper {
    exports helper.api;
}
```

File `src/demo.helper/helper/api/Bridge.java`:

```java
package helper.api;

public final class Bridge {
    private Bridge() {}

    public static String ping() {
        return "helper-ok";
    }
}
```

The helper module **is present in the boot layer** thanks to the `--add-modules demo.helper` runtime option, but the module's existence **does not automatically add** the `demo.secure → demo.helper` relationship.

We intentionally **do not write** `requires demo.helper;` in `demo.secure/module-info.java`. If it were declared, `secure.canRead(helper)` would already be `true` before the agent acted, eliminating the baseline control.

### 5.3. Java Agent: Measure Before, Grant Layer by Layer, Measure Again

File `agent-src/probe/AccessAgent.java`:

```java
package probe;

import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Set;

public final class AccessAgent {
    public static void premain(String args, Instrumentation inst)
            throws Exception {

        Module secure = ModuleLayer.boot()
                .findModule("demo.secure").orElseThrow();
        Module helper = ModuleLayer.boot()
                .findModule("demo.helper").orElseThrow();
        Module agent = AccessAgent.class.getModule();

        Class<?> hidden = Class.forName(
                "demo.secret.Hidden",
                false,
                ClassLoader.getSystemClassLoader());
        Method publicMethod = hidden.getDeclaredMethod("greeting");
        Method privateMethod = hidden.getDeclaredMethod("token");

        System.out.println("before:read=" + secure.canRead(helper));
        System.out.println("before:export="
                + secure.isExported("demo.secret", agent));
        System.out.println("before:open="
                + secure.isOpen("demo.secret", agent));
        System.out.println("before:public=" + callPublic(publicMethod));
        System.out.println("before:private-access="
                + privateMethod.trySetAccessible());

        if (!inst.isModifiableModule(secure)) {
            throw new IllegalStateException("module not modifiable");
        }

        // Step 1: allow module secure to read module helper only.
        inst.redefineModule(
                secure,
                Set.of(helper),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of());
        System.out.println("after-read:read=" + secure.canRead(helper));

        // Step 2: export package demo.secret to agent only.
        inst.redefineModule(
                secure,
                Set.of(),
                Map.of("demo.secret", Set.of(agent)),
                Map.of(),
                Set.of(),
                Map.of());
        System.out.println("after-export:export="
                + secure.isExported("demo.secret", agent));
        System.out.println("after-export:public="
                + callPublic(publicMethod));
        System.out.println("after-export:private-access="
                + privateMethod.trySetAccessible());

        // Step 3: open package demo.secret to agent only.
        inst.redefineModule(
                secure,
                Set.of(),
                Map.of(),
                Map.of("demo.secret", Set.of(agent)),
                Set.of(),
                Map.of());
        System.out.println("after-open:open="
                + secure.isOpen("demo.secret", agent));
        System.out.println("after-open:private-access="
                + privateMethod.trySetAccessible());
        System.out.println("after-open:private-value="
                + privateMethod.invoke(null));

        // Verify the principle of granting access only to the intended target module.
        System.out.println("isolation:export-to-helper="
                + secure.isExported("demo.secret", helper));
        System.out.println("isolation:open-to-helper="
                + secure.isOpen("demo.secret", helper));
        System.out.println("isolation:export-unqualified="
                + secure.isExported("demo.secret"));
    }

    private static String callPublic(Method m) throws Exception {
        try {
            return (String) m.invoke(null);
        } catch (IllegalAccessException e) {
            return e.getClass().getSimpleName();
        }
    }
}
```

**Important characteristics of the experiment:**

- The agent uses `ModuleLayer.boot().findModule(...)` to obtain the **exact two runtime `Module` objects**, without creating fake modules or comparing string names to grant permissions. `--add-modules demo.helper` ensures the helper is resolved into the boot layer.
- The agent belongs to an unnamed module, so `agent.isNamed()` will be `false`. We use the **actual** `AccessAgent.class.getModule()` object as the target of export/open; we do not use another self-created module.
- `Class.forName(..., false, loader)` obtains the `Class<?>` object without requiring `Hidden`'s static initializer to run. An unexported package **does not necessarily prevent class loading**. The access tests happen at `Method.invoke` and `trySetAccessible`.
- `getDeclaredMethod` only retrieves the method's metadata; it is not proof that invocation is permitted.
- `callPublic` intentionally catches **specifically `IllegalAccessException`** caused by a public method in an unexported package. If any other unexpected exception occurs, the demo does not swallow it and will fail startup instead of printing "success".
- `trySetAccessible()` returns a boolean: `false` when reflection permission cannot be enabled; unlike `setAccessible(true)`, which can throw `InaccessibleObjectException`.
- The `redefineModule` calls are split step-by-step to prove the individual effects of read, export, and open. In a real agent, the required changes can be combined into a single call once the exact permissions are determined.
- The experiment **does not modify bytecode**, does not register a transformer, and does not require `Can-Retransform-Classes`. The API name `redefineModule` **does not mean** `redefineClasses`. The goal is to observe the runtime JPMS graph via Java Instrumentation.

## 6. Manifest, Compilation, and Running

### 6.1. Startup Agent Manifest

File `agent.mf` (with **one trailing blank line**):

```text
Manifest-Version: 1.0
Premain-Class: probe.AccessAgent

```

`Can-Redefine-Classes: true` is not needed just to use `redefineModule`; that is a separate capability for redefining **classes**. The experiment only requires a JVM that supports the module API and `demo.secure` to be modifiable.

### 6.2. Create Output Directories

In the `module-access-lab` root directory, Linux/macOS:

```bash
mkdir -p out/agent out/mods
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/agent, out/mods | Out-Null
```

### 6.3. Compile Java 17 Code

```bash
javac --release 17 -d out/agent agent-src/probe/AccessAgent.java

jar --create --file out/access-agent.jar --manifest agent.mf -C out/agent .

javac --release 17 -d out/mods --module-source-path src src/demo.secure/module-info.java src/demo.secure/demo/app/Main.java src/demo.secure/demo/secret/Hidden.java src/demo.helper/module-info.java src/demo.helper/helper/api/Bridge.java
```

The commands use the same syntax in bash/PowerShell if `javac`, `java`, and `jar` are on `PATH`. Note:

- **The agent is compiled separately on the classpath** into `out/agent`, not mixed into named module `demo.secure`.
- **The two named modules** are compiled via `--module-source-path src` into `out/mods`.
- **The agent JAR** must be packaged with the appropriate `Premain-Class`; the launcher will look up `probe.AccessAgent`.
- Both parts of the demo are Java 17 source/classfile compatible because `--release 17` is used. The run command can use a newer JVM that supports Java 17 classfiles.

### 6.4. Run Baseline Without Agent

```bash
java --module-path out/mods --add-modules demo.helper --module demo.secure/demo.app.Main
```

Standard output:

```text
app: running
```

There is no runtime module modification because `premain` is not called. This serves as the control case showing that the application/modules run without the agent.

### 6.5. Run With Agent

```bash
java -javaagent:out/access-agent.jar --module-path out/mods --add-modules demo.helper --module demo.secure/demo.app.Main
```

**Verified stdout** when compiled with `javac --release 17` and run on **Azul Zulu OpenJDK 24.0.2**:

```text
before:read=false
before:export=false
before:open=false
before:public=IllegalAccessException
before:private-access=false
after-read:read=true
after-export:export=true
after-export:public=public-ok
after-export:private-access=false
after-open:open=true
after-open:private-access=true
after-open:private-value=private-ok
isolation:export-to-helper=false
isolation:open-to-helper=false
isolation:export-unqualified=false
app: running
```

**This is the observed output of this exact experiment**, not a rule that every JVM/module will produce `before:read=false`. If additional `--add-reads`, `--add-opens`, other agents, or different module descriptors are present, the initial state may already be different.

## 7. Step-by-Step Analysis of the Output

### 7.1. Before Granting Permissions: Module Is Strongly Encapsulated

```text
before:read=false
before:export=false
before:open=false
before:public=IllegalAccessException
before:private-access=false
```

- `demo.secure` **does not read** `demo.helper` because the descriptor has no `requires demo.helper` and the launcher has not added a read edge for this pair.
- `demo.secret` **is not exported/opened** to the agent's unnamed module.
- Even though both `Hidden` and `greeting()` are `public`, the reflective call `Method.invoke(null)` from the agent is blocked: the package is not exported to the caller.
- `token()` is private: `trySetAccessible()` cannot enable suppressing access checks when the package is not open to the caller.

This proves that **a class being found** does not imply **its members can be invoked**.

### 7.2. After `extraReads`: Only the Read Edge Changes

```text
after-read:read=true
```

The agent calls:

```java
inst.redefineModule(
    secure, Set.of(helper), Map.of(), Map.of(), Set.of(), Map.of());
```

It adds the **`demo.secure → demo.helper`** relationship. It **does not** export package `demo.secret`, does not open that package, and does not automatically make helper classes discoverable from a class loader that lacks a loading path.

This is how to verify the read edge at runtime. Because the example has not injected an instruction calling `helper.api.Bridge` from a class in `demo.secure`, the check does not claim that bytecode linking is complete. Testing actual invocation requires a separate test with valid bytecode, an exported helper, proper loader visibility, and a verified test build.

### 7.3. After `extraExports`: Public Method Permitted, Private Still Blocked

```text
after-export:export=true
after-export:public=public-ok
after-export:private-access=false
```

The agent calls:

```java
inst.redefineModule(
    secure, Set.of(),
    Map.of("demo.secret", Set.of(agent)),
    Map.of(), Set.of(), Map.of());
```

`agent` is the specific module to which `AccessAgent.class` belongs. After the call, package `demo.secret` is **qualified-exported** to the agent. `publicMethod.invoke(null)` succeeds and returns `public-ok`. However, `token()` is still private; exporting does not grant **deep reflection**, so `privateMethod.trySetAccessible()` still returns `false`.

This is a useful check to avoid granting overly broad `opens` when an agent only actually needs public APIs.

### 7.4. After `extraOpens`: Private Reflection Permitted

```text
after-open:open=true
after-open:private-access=true
after-open:private-value=private-ok
```

The agent calls:

```java
inst.redefineModule(
    secure, Set.of(), Map.of(),
    Map.of("demo.secret", Set.of(agent)),
    Set.of(), Map.of());
```

`trySetAccessible()` returns `true`, and the agent then successfully invokes `token()`, even though this method is private. This is a stronger permission than export and should only be added when instrumentation/diagnostic functionality **genuinely needs deep reflection**.

**A subtlety:** when a package is **opened** to the agent, `secure.isExported("demo.secret", agent)` is also considered `true` at runtime. Therefore, one cannot infer "isExported true means the source descriptor contains exports"; one must check `isOpen` and distinguish the timing/source of the grant.

### 7.5. Permissions Do Not Leak to Another Named Module

```text
isolation:export-to-helper=false
isolation:open-to-helper=false
isolation:export-unqualified=false
```

These checks confirm that **`demo.helper` did not receive export/open** for package `demo.secret`. Nor was the package exported unconditionally. Only the single agent received permissions according to the chosen `Set.of(agent)`.

**This is the core of "adding only the required relationships":** test both the *positive case* (the granted module has access) and the *negative case* (other modules remain closed). Looking only at `isOpen(..., agent)=true` without checking scope can hide over-broad expansion.

## 8. Testing Changes Based on Actual Requirements

Not every agent needs all three relationships. Match the goal to the minimum required permission:

| Agent Requirement | Relationships to Consider | What Not to Add Just for Convenience |
| --- | --- | --- |
| Only wants to read class/loader name metadata provided by the transformer | May **not need to modify the module graph** | `extraOpens` to every package |
| Bytecode in named module A must call a helper in named module B | `A` reads `B`, helper package exported to A, helper loadable | Opening A's private package to the agent if reflection is not used |
| Agent needs to call a **public** method of a class in an unexported package | Qualified `extraExports` of the package to the agent module | `extraOpens` if public access is already sufficient |
| Agent needs to read a private field/method via reflection | Qualified `extraOpens` to the module performing reflection | Opening the whole module or `ALL-UNNAMED` if only one module needs it |
| Target in a JDK module has a bootstrap helper call injected | Understand automatic read edges, bootstrap helper visibility, and separate access | Broad `--add-opens java.base/*=ALL-UNNAMED` |
| Agent loads helpers from an isolated plugin loader | Appropriate class-loader search/delegation, class identity, and module access | Assuming adding a read edge makes a class appear |

### 8.1. `extraReads` Alone Does Not Grant Access to All Packages

Suppose bytecode in `demo.secure` needs to call `helper.api.Bridge.ping()`. After `secure.canRead(helper)` is `true`, you must still check:
1. Does `demo.helper` contain package `helper.api` and has it **exported** this package to `demo.secure`?
2. Can the defining class loader of the class in `demo.secure` locate `helper.api.Bridge` when the JVM resolves the symbolic reference?
3. Do class `Bridge` and method `ping()` have the right visibility/descriptor?
4. Is the injected bytecode valid with respect to the class file, stack map frames, and the target's classloader/module?

In the demo, `demo.helper` exports `helper.api` unconditionally to eliminate one variable; **the experiment focuses on the read edge**, without equating it to invocation success.

### 8.2. Export and Open Do Not Have the Same Permission Surface

If you only need to call a public diagnostics method, `extraExports` has a narrower scope than `extraOpens`. Open allows deep reflection on other members in the same package as well, **not just a single method**. JPMS does not support `opens` per method name; permissions are granted at the **package-to-module level**.

If many packages must be opened, reconsider the agent design: it may be possible to add a **public bridge API** or instrument at the call site instead of opening numerous private packages. Although `extraExports` cannot be removed with `redefineModule`, a well-designed public bridge can still reduce the permission surface compared to opening entire packages.

### 8.3. Interaction with Instrumentation's Automatic Read Edges

The `java.lang.instrument` specification states that **the module containing the transformed class** is arranged by the JVM to read the unnamed module of the **bootstrap class loader** and the unnamed module of the **class loader that loaded the agent class itself**. This is specific support for transformed bytecode calling helpers in those two unnamed modules.

That **does not automatically create** the `demo.secure → demo.helper` relationship in this lesson, because `demo.helper` is a **named module**. Nor does it **automatically open** `demo.secret` for the agent to perform deep reflection. Therefore, do not use "the JVM already has automatic read edges" as an excuse to skip other necessary read/export/open checks.

## 9. `--add-reads`, `--add-exports`, `--add-opens` vs. `redefineModule`

When startup configuration is under your control, the launcher provides common JPMS options:

```text
--add-reads demo.secure=demo.helper
--add-exports demo.secure/demo.secret=ALL-UNNAMED
--add-opens demo.secure/demo.secret=ALL-UNNAMED
```

The lines above are **individual syntax illustrations**, not a recommendation to pass all three at once. Each line expands permissions for a different purpose:

- `--add-reads`: allows `demo.secure` to additionally read `demo.helper` when the JVM starts.
- `--add-exports`: exports a package to a target; `ALL-UNNAMED` means **all unnamed modules**, which is broader than `Set.of(agentModule)` in the experiment.
- `--add-opens`: opens a package for deep reflection to a target; also broader if `ALL-UNNAMED` is used.

If you run the demo **with those flags**, some `before:...` lines may already be `true` from the start, defeating the control. To test changes made by `redefineModule`, **do not use pre-granting flags** in the run command in Section 6. When testing a launcher-based solution, start a **fresh** JVM and clearly document which permissions came from startup and which were added by the agent.

Comparison table:

| Approach | Timing | Who Controls It? | Key Points to Remember |
| --- | --- | --- | --- |
| `module-info.java` | Compile-time descriptor and resolution | Module/source owner | Explicit, versioned; may not fit third-party applications |
| `--add-reads`/`--add-exports`/`--add-opens` | JVM startup | Launcher/deployment | Takes effect before `premain`; `ALL-UNNAMED` is very broad |
| `Instrumentation.redefineModule` | Runtime after `Instrumentation` is available | Agent with permission to modify | Can grant to a **specific target module object**; expand-only, no rollback |
| `Module.addReads/addExports/addOpens` | Runtime subject to caller restrictions | Code inside the module owning the relationship | Not an arbitrary replacement API for an external agent |

**Distinguish compile-time from runtime:** if you add `import helper.api.Bridge` to `demo.secure` source when the descriptor does not `requires demo.helper`, `javac` can report that the package is not read by this module. An agent modifying the graph **at runtime** does not help a program **compiled earlier** pass compiler checks; you must declare appropriate dependencies or manage compile-time configuration separately.

## 10. Common Mistakes in Agent Experiments

### 10.1. Modifying the Wrong Direction in the Module Graph

If the goal is for code in `demo.secure` to read `demo.helper`, the right call is:

```java
inst.redefineModule(
    secure, Set.of(helper), Map.of(), Map.of(), Set.of(), Map.of());
```

Do not call `redefineModule(helper, Set.of(secure), ...)`: that creates the **helper → secure** direction, which is the opposite of the goal. Similarly, when the agent needs access to `demo.secret`, the export/open must be **a change on the module containing the package**, namely `secure`, with the target module being **agent**.

### 10.2. Using a Package Name That Does Not Belong to the Module

`extraExports` and `extraOpens` only accept package keys **belonging to the module being modified**. Calling:

```java
// WRONG example: helper.api belongs to demo.helper,
// not demo.secure.
inst.redefineModule(
    secure, Set.of(),
    Map.of("helper.api", Set.of(AccessAgent.class.getModule())),
    Map.of(), Set.of(), Map.of());
```

can result in `IllegalArgumentException`. To export package `helper.api` of `demo.helper` (if it were not already exported), you would need to call `redefineModule(helper, ..., extraExports=...)` with a package belonging to `helper` itself. The experiment already exports `helper.api` in its descriptor, so this is unnecessary.

### 10.3. Referencing a Module Not Resolved into the Layer

Having a JAR/module on the module path is not enough to guarantee `ModuleLayer.boot().findModule("demo.helper")` returns a result. In the demo, `--add-modules demo.helper` exists to **ensure the module is resolved**, so the agent can obtain its object and add the read edge.

If `--add-modules demo.helper` is omitted, the environment may not resolve the helper because `demo.secure` does not declare `requires`; `orElseThrow()` then intentionally halts startup. Identify the proper module roots/layer rather than swallowing the error and granting permissions to an object that is not a real module.

### 10.4. Confusing `Class.forName` with Member Access Permission

`Class.forName("demo.secret.Hidden", false, loader)` succeeding **does not prove** that public methods are permitted to be called. Reflection separates locating type metadata from invocation permission; `Method.invoke` is the actual test used in this lesson.

Conversely, `ClassNotFoundException` may be a class loader issue, an unresolved module, or a wrong binary name. Adding export/open alone will not create a class file or fix the class loading path.

### 10.5. Using `setAccessible(true)` and Ignoring Failures

When a package is not open to the module invoking reflection, `setAccessible(true)` can throw `InaccessibleObjectException`. This lesson uses `trySetAccessible()` to obtain a clear `false` control result. In production code, choose the appropriate API and report errors with full context rather than quietly adding broad `--add-opens` to "make the error go away."

### 10.6. Granting Access with `open module` Instead of Qualified Opens

Changing the descriptor to:

```java
open module demo.secure {
}
```

opens packages far more broadly than granting only `demo.secret` to the agent's module. It also deprives the experiment of a negative case. If the goal is just one package and one agent, keep the module closed by default and add only the required relationships.

### 10.7. Confusing `isExported` with the Original Descriptor

`Module.isExported("demo.secret", agent)` checks runtime state; that state can change via `redefineModule` or flags. After a package is `opens`ed to the agent, `isExported(..., agent)` can be `true` because **open is also treated as exported** for runtime access purposes.

If you need to compare against the original descriptor, inspect `Module.getDescriptor()`, though the descriptor does not necessarily reflect dynamic grants expanded at runtime.

### 10.8. Assuming a Module Can Be "Closed Again" After Disabling a Probe

`redefineModule` **does not provide an operation to remove an export/open/read edge**. Disabling a transformer or detaching a probe does not revert the entire module graph. When runtime-granted permissions are a significant operational decision, design the process lifecycle, permission scope, and restart/rollout strategy accordingly.

## 11. Diagnostics Using APIs and Exceptions

| Symptom | Accurate Interpretation | Next Step |
| --- | --- | --- |
| `secure.canRead(helper)=false` | Missing read edge for this module pair | Check `requires`, resolution, `extraReads` |
| `canRead=true` yet code cannot find helper | Read edge does not alter class loader search path | Check loader identity, module resolution, helper path |
| `isExported(p, agent)=false` | Package not exported/opened to agent in runtime graph | Grant `extraExports` only if public access is needed |
| `Method.invoke` throws `IllegalAccessException` | Public method may still be inaccessible because package is not exported or due to other access rules | Check class/method modifiers and exports |
| `trySetAccessible=false` | JVM does not allow enabling deep reflection in current state | Check qualified opens, security conditions |
| `InaccessibleObjectException` | `setAccessible(true)` was rejected | Consider narrow `extraOpens` if genuinely needed |
| `isOpen(p, agent)=true` | Package is open to agent, not opened by default to other modules | Also check `isOpen(p, helper)` and `isOpen(p)` |
| `UnmodifiableModuleException` | JVM does not allow modifying that module via API | Check `isModifiableModule` and platform constraints |
| `IllegalArgumentException` in `redefineModule` | Wrong package key, empty target module set, or invalid input | Compare against `Module.getPackages()` and API contract |
| `NoClassDefFoundError` / `ClassNotFoundException` | Class loading/resolution failure, does not automatically mean missing export | Check defining loader, dependencies, and module graph |
| `IllegalAccessError` in injected bytecode | Invalid runtime linking/access for class/method | Check read edge, exports, method visibility, class identity |

In real logs, record **the module name, package name, defining class loader, target module, and receiving module**. Storing only a single `boolean moduleOpen` is insufficient, because a package may be open to agent A while remaining closed to agent B.

### Minimal Diagnostic Snippet

Below is an **agent code snippet**, assuming `Module secure`, `Module helper`, and `Module agent` are already obtained as in the experiment:

```java
System.out.println("secure name=" + secure.getName());
System.out.println("secure loader=" + secure.getClassLoader());
System.out.println("agent named=" + agent.isNamed());
System.out.println("reads helper=" + secure.canRead(helper));
System.out.println("exports to agent="
        + secure.isExported("demo.secret", agent));
System.out.println("opens to agent="
        + secure.isOpen("demo.secret", agent));
System.out.println("opens to helper="
        + secure.isOpen("demo.secret", helper));
System.out.println("package exists="
        + secure.getPackages().contains("demo.secret"));
```

Use `isModifiableModule(secure)` and `getPackages()` to reduce errors before granting permissions. Avoid using reflection on application private packages inside a transformer running on the class-loading path unless dependencies are prepared, as this can trigger unnecessary recursive loading or deadlocks.

## 12. Controlled Experiment Extensions

### Exercise A: Grant Only Export Without Open

Run the given demo and remove **step 3** `extraOpens` (in a **separate test run**, not by modifying the Sheet results). You should see `after-export:public=public-ok` and `after-export:private-access=false`. Thus, the public API is sufficient for the public call use case; deep reflection is not needed.

### Exercise B: Grant Only Open

In a fresh JVM run, omit step 2 `extraExports` and perform only step 3 `extraOpens`. Predict:
- `secure.isOpen("demo.secret", agent)=true`;
- `secure.isExported("demo.secret", agent)=true` according to the runtime API, because open is treated as exported to the same target module;
- public invocation may be allowed and private `trySetAccessible` succeeds;
- `isExported("demo.secret")` remains `false` if only qualified open was granted.

You must start a **fresh JVM** because grants from a previous run cannot be revoked within the same process.

### Exercise C: Wrong Direction for `extraReads`

Start a fresh JVM and try granting `helper → secure` instead of `secure → helper`. Compare `secure.canRead(helper)` before and after. Do not expect the wrong direction to turn `secure.canRead(helper)` into `true`. This test proves that module readability is a **directional** relationship.

### Exercise D: A Third Module

Create an additional `demo.observer` and check `secure.isOpen("demo.secret", observerModule)`. If granted only to `agent`, the observer must still be denied. Avoid drawing conclusions from the observer's `Class.forName`; test public/private method access accordingly.

### Exercise E: Actually Instrument a Class in a Named Module

Once you understand the module graph, build a transformer using a verified bytecode library to inject a helper call. Test **with and without** valid read edges/exports, and verify:
- Is the class loaded/verified?
- Which automatic read edges does the module containing the instrumented class have?
- Does the helper have the right defining loader and right method descriptor?
- Which layer do `NoClassDefFoundError`, `IllegalAccessError`, and `VerifyError` originate from?
- Is a read edge to a named helper actually needed, or is the helper in an unnamed module already supported by the JVM?

Exercise E is an extended experiment and **is not code implemented in the standalone demo of this lesson**.

## 13. Minimum-Privilege Checklist When Deploying an Agent

- [ ] Identify the **source module** containing the transformed class or the package to be accessed.
- [ ] Identify the **target module receiving permission** via the actual `Class.getModule()` of the code performing the operation; do not rely solely on package names.
- [ ] Verify that the required modules have been **resolved into the appropriate layer**.
- [ ] Check `isModifiableModule` and the actual package presence in `getPackages()`.
- [ ] For helper calls from bytecode, determine which **read** and **export** are needed; check loader visibility separately.
- [ ] If only calling public members, prefer **qualified export** over qualified open.
- [ ] Use **qualified open** only when private/deep reflection is required.
- [ ] Do not use `ALL-UNNAMED`, `open module`, or open `java.base` broadly if a narrow module grant suffices.
- [ ] Verify before/after with `canRead`/`isExported`/`isOpen`, plus actual invocation tests.
- [ ] Include a **negative control** for a module that was not granted permission.
- [ ] Record JVM/agent version, loader/module identity, and startup flags in test logs.
- [ ] Understand that dynamic grants **have no rollback operation** in `redefineModule`; plan for restarts when the graph needs to be reset.
- [ ] Ensure the agent JAR is trusted and contains only the permissions required for its use case.

## 14. Self-Check Questions

1. Why does `Method.invoke` throw `IllegalAccessException` before permissions are granted even though `Hidden` is public?
2. How does `demo.secure.canRead(demo.helper)` change after `extraReads`? Is that enough to prove a `Bridge.ping()` call from bytecode will succeed?
3. Why can `extraExports` allow public invocation to succeed while `trySetAccessible` on a private method still returns `false`?
4. What additional permission does `extraOpens` to the agent create? Why should export and open not be treated as identical?
5. If a package has been opened to the agent, what can `isExported("demo.secret", agent)` return? Why?
6. Why does granting permission to `agent` **not automatically** export/open the package to `demo.helper`?
7. What happens if the key in `extraExports` is `"helper.api"` while the module being modified is `demo.secure`?
8. Why is `--add-modules demo.helper` needed even though the demo already has the `out/mods/demo.helper` directory?
9. Can `redefineModule` close an opened package again after disabling a probe? If not, what should deployment do?
10. Do `java.lang.instrument`'s automatic read edges to unnamed modules replace `extraReads` to a named helper module?

## 15. Official Documentation

- [Java SE 21 — `Instrumentation.redefineModule` and `isModifiableModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): contract for adding reads, exports, opens, uses, provides, and the inability to revoke permissions.
- [Java SE 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `getPackages`, and details on unnamed/named modules.
- [Java SE 21 — `AccessibleObject.trySetAccessible`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html): scope of deep reflection and differences from `setAccessible(true)`.
- [Java SE 21 — `java.lang.instrument`, section *Instrumenting code in modules*](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): the JVM adds automatic readability to unnamed modules of the bootstrap and agent loaders when a class is instrumented.
- [Java SE 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--module-path`, `--module`, `--add-modules`, `--add-reads`, `--add-exports`, `--add-opens`.
