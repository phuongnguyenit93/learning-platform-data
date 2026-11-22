# Instrumentation.redefineModule: extraReads, extraExports, and extraOpens

## 1. The problem: an agent needs to relax access permissions of a named module

Since Java 9, the **Java Platform Module System (JPMS)** adds **readability** and **encapsulation** boundaries alongside traditional `public`/`private` access control. A Java agent can instrument classes in a named module, but newly injected bytecode or the agent's reflection tools sometimes need a module relationship that the original `module-info.java` **does not declare**.

For example:

~~~text
                  demo.target  (named module)
                 /            \
        demo.target.api    demo.target.internal
         public method       private field
                 \            /
                  \          /
                  Agent in unnamed module

Initially:
  demo.target does not read the agent's unnamed module
  demo.target.api is not exported to the agent
  demo.target.internal is not opened to the agent

Agent needs:
  extraReads    : demo.target  ------read------> agent module
  extraExports  : demo.target.api ----export---> agent module
  extraOpens    : demo.target.internal --open--> agent module
~~~

`java.lang.instrument.Instrumentation.redefineModule(...)` allows an agent to **add** these relationships **inside a running JVM**, without modifying `module-info.java` on disk or changing class bytecode. It serves cases where instrumentation needs to read helpers, invoke public APIs, use reflection on internal state, or extend service registrations.

**Key points:**

- **`extraReads`:** *which additional modules are read?* This is an edge from **the module being redefined** to the target module.
- **`extraExports`:** *which packages of the module being redefined are additionally exported, and to which modules?* Typically needed to access **public types/members** across module boundaries.
- **`extraOpens`:** *which packages are additionally opened, and to which modules?* Used for **deep reflection** into non-public members and reflection scenarios permitted by JPMS.

The three permissions have **different** roles. Granting only one permission and hoping all three problems disappear is a common mistake in agents.

Original documentation: [Java 17 — Instrumentation.redefineModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map)).

## 2. Full signature and meaning of each argument

The method belongs to the `java.lang.instrument.Instrumentation` interface, since Java 9:

~~~java
void redefineModule(
        Module module,
        Set<Module> extraReads,
        Map<String, Set<Module>> extraExports,
        Map<String, Set<Module>> extraOpens,
        Set<Class<?>> extraUses,
        Map<Class<?>, List<Class<?>>> extraProvides);
~~~

This is an **illustrative API signature**, not a standalone program. When writing code, you need to import `java.lang.instrument.Instrumentation`, `java.util.Set`, `Map`, and `List`. The `Instrumentation` instance is passed by the JVM into `premain` or `agentmain`; do **not** create it manually with `new Instrumentation()`.

| Argument | Expected value | Effect |
| --- | --- | --- |
| `module` | `Module` whose permissions are to be relaxed | **Source** of the reads/exports/opens changes |
| `extraReads` | `Set<Module>`, may be empty | Modules that `module` is allowed to **additionally read** |
| `extraExports` | `Map<String, Set<Module>>`, may be empty | Package name of `module` → modules to **additionally export** to |
| `extraOpens` | `Map<String, Set<Module>>`, may be empty | Package name of `module` → modules to **additionally open** to |
| `extraUses` | `Set<Class<?>>`, may be empty | Service types for which the module is granted an additional `uses` permission |
| `extraProvides` | `Map<Class<?>, List<Class<?>>>`, may be empty | Additional provider implementations for a service |

This article focuses on the **first three arguments for read/export/open**. The two service arguments are still **required to be non-null**, even when unused: use `Set.of()` and `Map.of()` instead of `null`. The fact that `extraUses`/`extraProvides` are supported does not mean the agent automatically registers a JVM service or bypasses accessibility rules for the service type.

Common call structure:

~~~java
inst.redefineModule(
        targetModule,
        Set.of(helperModule),
        Map.of("com.acme.api", Set.of(agentModule)),
        Map.of("com.acme.internal", Set.of(agentModule)),
        Set.of(),
        Map.of());
~~~

This is a **code snippet inside an agent**, assuming `inst`, `targetModule`, `helperModule`, and `agentModule` already exist. It is only valid when the packages `com.acme.api` and `com.acme.internal` **actually belong to `targetModule`**. `Map.of` and `Set.of` create unmodifiable containers, suitable for a fixed configuration request.

## 3. `extraReads`: adding a readability edge

Suppose module `M` needs to use classes from module `H`. `M.canRead(H)` indicates whether `M` has a read edge to `H` in the runtime graph.

~~~text
                 before                        after
     module M              module H     module M ------> module H
        canRead(H) = false                   canRead(H) = true
~~~

Performing this via an agent:

~~~java
inst.redefineModule(
        moduleM,
        Set.of(moduleH),   // M additionally reads H
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

This snippet is **code inside an agent** that already has the module variables. **The direction is `moduleM → moduleH`**, not the reverse. If you pass `moduleH` as the first argument of the call, you are modifying the wrong module.

### 3.1. Readability does not automatically create export/open

**`M.canRead(H) == true` is not enough for M to call every class/member of H.** The package in H must still be exported/opened depending on the situation. For code in M to invoke a public type of H via JVM linkage, it usually requires **M reads H** **and** **H exports that package to M**. A read edge does not automatically open private fields.

The reverse direction is also worth noting: **exporting a package of H to M does not automatically add `M → H` to the module graph**. When querying `H.isExported("h.api", M)`, this API **does not automatically check** whether M reads H.

This explains why an agent sometimes has to perform **two operations on two different modules**:

~~~text
M needs to call H.API:
    redefineModule(M, extraReads={H}, ...)
    redefineModule(H, extraExports={"h.api" -> {M}}, ...)
~~~

If `H` is an **unnamed module**, H's packages are already treated as exported/open under JPMS rules, but module M **may still need a read edge to H** and must still satisfy **class-loader visibility**. Relaxing the JPMS graph does not automatically allow M's class loader to find a helper defined in an isolated loader.

### 3.2. Do not confuse `extraReads` with `java.base`

A named module reads `java.base` by default in standard cases, and an unnamed module has its own module-reading rules. In a hands-on example, we choose an edge that **is initially absent** to demonstrate the change; if you check `target.canRead(Object.class.getModule())`, it is usually already `true`, so no difference will be observed.

Reference: [Java 17 — Module.canRead](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#canRead(java.lang.Module)).

## 4. `extraExports`: adding permission to use a package's public API

A named module has package `p.api` but **does not** have `exports p.api;` in `module-info.java`. A class inside it may be `public`, yet an external module does not automatically have permission to link against that class.

`extraExports` adds a **qualified export** to the specified set of modules:

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of("p.api", Set.of(consumerModule)),
        Map.of(),
        Set.of(),
        Map.of());
~~~

This is **code inside an agent**. The key `"p.api"` is the **dotted package name**, not the internal name `"p/api"` used in bytecode or `ClassFileTransformer`. The map value is a **non-empty set of modules**; it is not a module name as a String.

After it succeeds:

~~~java
boolean exported = sourceModule.isExported("p.api", consumerModule);
~~~

This check asks whether package `p.api` is exported **at least to `consumerModule`**. It does **not** prove the package is unconditionally exported to all modules. `sourceModule.isExported("p.api")` (without a module parameter) asks about an **unqualified export**; do not substitute one overload for the other when verifying a **targeted** permission relaxation.

### 4.1. Export does not mean private access

Export permission allows the target module to access **public types** and members permitted under Java access rules. It **does not automatically allow deep reflection** into private fields/methods of the package.

For example, a public class in a non-exported package has a public static method. After exporting the package to the agent, invoking the public method via reflection can succeed; however, `privateField.setAccessible(true)` in a package that is only exported and **not opened** can still throw `InaccessibleObjectException`.

### 4.2. The target package must actually exist in the source module

This is a common mistake:

~~~java
Map.of("p/unknown", Set.of(agentModule)) // Wrong: name uses /
~~~

Even fixing it to `"p.unknown"` is wrong if it is **not** a package of `sourceModule`. `redefineModule` may throw `IllegalArgumentException` when a key in `extraExports`/`extraOpens` does not belong to the module being modified. Do not construct keys from unnormalized class names or mix up agent packages with application packages.

Reference: [Java 17 — Module.isExported](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#isExported(java.lang.String,java.lang.Module)).

## 5. `extraOpens`: allowing targeted deep reflection

`opens` has a different goal from `exports`. When package `p.internal` is **opened** to the agent module, code in the agent can perform permitted deep reflection operations, such as `Field.setAccessible(true)` on a private field in that package.

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of(),
        Map.of("p.internal", Set.of(agentModule)),
        Set.of(),
        Map.of());
~~~

The snippet above uses the **dotted name** of the package. Verification:

~~~java
boolean opened = sourceModule.isOpen("p.internal", agentModule);
~~~

`opened == true` does not mean every module is opened to; this is still **qualified opens**. To check for unconditional opens, use the `sourceModule.isOpen("p.internal")` overload.

**Surprising detail:** According to `Module.isExported(String, Module)`, a package **opened to module X is also considered exported to X at runtime**. Therefore, after `extraOpens("p.internal" → X)`, you will commonly see:

~~~text
source.isOpen("p.internal", X)     == true
source.isExported("p.internal", X) == true
~~~

This is the runtime semantics of an open package; it **does not mean an `exports` declaration was added to `module-info.java`**. Nor does it mean every public type in that package can immediately be used by external callers when compiling normal Java code; JPMS compile-time and runtime are two different phases.

### 5.1. Comparison via reflection behavior

| Package state in source module | Calling a public member from target module | `privateField.setAccessible(true)` from target module |
| --- | --- | --- |
| Not exported, not opened | May fail with `IllegalAccessException` | Usually `InaccessibleObjectException` |
| Qualified exported to target only | Public types/members are accessible per visibility rules | **Does not automatically grant** deep reflection |
| Qualified opened to target | Also considered exported at runtime to target | May allow deep reflection, if other conditions are valid |

Reflection methods have their own readability rules (the `AccessibleObject` Javadoc notes that reflection **assumes readability** in certain access checks). Therefore, use `Module.canRead` to inspect the **read graph** and `isExported`/`isOpen` to inspect the **package boundary**, rather than using a single reflection test to infer all three flags.

Deep reflection may still be subject to other conditions, such as special members, `final`, security policy permissions, or how the caller resolves its module. "Open" is not a guarantee that you can **write** to every private/final field, regardless of data type.

Reference: [Java 17 — AccessibleObject.setAccessible/trySetAccessible](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html).

## 6. Decision table: which relationship should be added?

| Actual requirement | Permission to consider first | What else is needed? |
| --- | --- | --- |
| Newly injected bytecode in named module M calls a helper in H | `extraReads`: M → H | H exports the helper package to M (or helper is in an unnamed module), loader must see the helper |
| Agent calls a public method of a hidden target package | `extraExports` from target → agent | Class/method is actually public, right target Module, and valid reflection/loader |
| Agent reads a private field for observation | `extraOpens` from target → agent | Reflection on the right class/member; other policy conditions |
| Agent uses `MethodHandles` private lookup in a package | Usually needs `extraOpens` from target → caller module | `MethodHandles.privateLookupIn` also requires a read edge/appropriate lookup characteristics |
| Target only wants to expose a public API to plugin X, not the whole JVM | Qualified `extraExports` to X | Do not open unconditionally, do not use a broad target |
| Agent only needs to read class-file bytes, no reflection on private data | May need **no** module expansion at all | Filter/parse bytecode according to the transformer contract |
| Building a scanner that only reads metadata from an offline JAR | Usually does not need `redefineModule` | Read files/bytes, no class loading/reflection needed |

**Principle of least privilege:** open the right module, the right package, and the right target module; do not automatically add `extraReads`/`extraExports`/`extraOpens` for all packages or `java.base` just because of a single `IllegalAccessException`.

## 7. Executable Java 17+ example: agent opens three relationships for a named module

The example runs **a new JVM** with a `-javaagent` agent and a named-module application `demo.target`. The target module declares no exports/opens in `module-info.java`. The agent lives in the **unnamed module** on the application classpath, checks before/after states, and invokes reflection to demonstrate the behavior.

**Important point:** this is a **real Java agent**, not a mocked `Instrumentation`. The example **does not** modify class bytecode, does not need a `ClassFileTransformer`, and does not use dynamic attach.

### 7.1. Directory structure

~~~text
module-demo/
  src/
    demo.target/
      module-info.java
      demo/
        target/
          api/
            PublicApi.java
          internal/
            Secret.java
          app/
            Main.java
  agent-src/
    AccessAgent.java
    MANIFEST.MF
  mods/               (created by javac)
  agent-bin/          (created by javac)
  access-agent.jar    (created by jar)
~~~

### 7.2. Target module without exported or opened packages

**File: `src/demo.target/module-info.java`**

~~~java
module demo.target {
    // Intentionally do not export/open any package.
}
~~~

**File: `src/demo.target/demo/target/api/PublicApi.java`**

~~~java
package demo.target.api;

public final class PublicApi {
    private PublicApi() { }

    public static String greet() {
        return "API";
    }
}
~~~

**File: `src/demo.target/demo/target/internal/Secret.java`**

~~~java
package demo.target.internal;

public final class Secret {
    private static final String VALUE = "hidden";

    private Secret() { }
}
~~~

**File: `src/demo.target/demo/target/app/Main.java`**

~~~java
package demo.target.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app=started");
    }
}
~~~

`PublicApi` and `Secret` are both `public class`, but their respective packages are not exported/opened. The JVM can define them in the module; that **does not automatically grant permission** for the agent to access the public method/private field from another module.

The `Main` program is invoked by the launcher via `-m demo.target/demo.target.app.Main`, so it is not necessary to export package `demo.target.app` just to run the entry point in this example. All packages have standard Java dotted names.

### 7.3. Agent checking state before/after `redefineModule`

**File: `agent-src/AccessAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.Set;

public final class AccessAgent {
    public static void premain(
            String args, Instrumentation inst) throws Exception {

        Module target = ModuleLayer.boot()
                .findModule("demo.target").orElseThrow();
        Module agent = AccessAgent.class.getModule();

        String publicPackage = "demo.target.api";
        String privatePackage = "demo.target.internal";

        System.out.println("targetNamed=" + target.isNamed());
        System.out.println("agentUnnamed=" + !agent.isNamed());
        System.out.println("modifiable="
                + inst.isModifiableModule(target));
        System.out.println("readsBefore=" + target.canRead(agent));
        System.out.println("exportsBefore="
                + target.isExported(publicPackage, agent));
        System.out.println("opensBefore="
                + target.isOpen(privatePackage, agent));

        Method method = Class.forName("demo.target.api.PublicApi")
                .getMethod("greet");
        Field field = Class.forName("demo.target.internal.Secret")
                .getDeclaredField("VALUE");

        try {
            method.invoke(null);
            System.out.println("publicBefore=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("publicBefore=IllegalAccessException");
        }

        try {
            field.setAccessible(true);
            System.out.println("privateBefore=unexpected");
        } catch (InaccessibleObjectException expected) {
            System.out.println(
                    "privateBefore=InaccessibleObjectException");
        }

        inst.redefineModule(
                target,
                Set.of(agent),
                Map.of(publicPackage, Set.of(agent)),
                Map.of(privatePackage, Set.of(agent)),
                Set.of(),
                Map.of());

        System.out.println("readsAfter=" + target.canRead(agent));
        System.out.println("exportsAfter="
                + target.isExported(publicPackage, agent));
        System.out.println("opensAfter="
                + target.isOpen(privatePackage, agent));
        System.out.println("openedAlsoExported="
                + target.isExported(privatePackage, agent));
        System.out.println("publicAfter=" + method.invoke(null));

        field.setAccessible(true);
        System.out.println("privateAfter=" + field.get(null));
    }
}
~~~

**File: `agent-src/MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: AccessAgent

~~~

An actual manifest file must end the main attributes section with a blank line. `Can-Redefine-Classes: true` is not needed: this is **`redefineModule`**, not `redefineClasses`. `Agent-Class` is not needed because the example uses `-javaagent` at startup, not the attach mechanism after the JVM is already running.

For simplicity, the code uses `ModuleLayer.boot().findModule("demo.target")`, which is correct because `demo.target` is a module resolved in the **boot layer** of the example. In a real application with **custom module layers**, do not mistakenly look up a module with the same name in the boot layer. Identify the exact `Module` (typically via `targetClass.getModule()`) and its corresponding class loader.

### 7.4. Compile and run commands

From the `module-demo` directory, with JDK 17 or later:

~~~bash
mkdir -p mods/demo.target agent-bin
javac --release 17 -d mods/demo.target src/demo.target/module-info.java src/demo.target/demo/target/api/PublicApi.java src/demo.target/demo/target/internal/Secret.java src/demo.target/demo/target/app/Main.java
javac --release 17 -d agent-bin agent-src/AccessAgent.java
jar --create --file access-agent.jar --manifest agent-src/MANIFEST.MF -C agent-bin AccessAgent.class
java -javaagent:access-agent.jar --module-path mods -m demo.target/demo.target.app.Main
~~~

On **Windows PowerShell**, replace `mkdir -p mods/demo.target agent-bin` with:

~~~powershell
New-Item -ItemType Directory -Force mods/demo.target, agent-bin | Out-Null
~~~

The `javac`, `jar`, and `java` commands can then be used in PowerShell when run from the right working directory with the JDK in `PATH`. The example does not need `--add-reads`, `--add-exports`, or `--add-opens` flags at startup: the agent itself adds the permissions **after printing the initial state**.

### 7.5. Stdout on OpenJDK/HotSpot supporting `redefineModule`

~~~text
targetNamed=true
agentUnnamed=true
modifiable=true
readsBefore=false
exportsBefore=false
opensBefore=false
publicBefore=IllegalAccessException
privateBefore=InaccessibleObjectException
readsAfter=true
exportsAfter=true
opensAfter=true
openedAlsoExported=true
publicAfter=API
privateAfter=hidden
app=started
~~~

This is **tested output**: the `--release 17` compatible source code was compiled and run on OpenJDK 21 (a Java 17+ JVM) with this exact agent and module. On another JVM, if `isModifiableModule(target)` does not support modifying the module, the operation may fail; the sample output above **is not a guarantee across every JVM**. Use a suitable JDK 17 and the initial module graph as instructed to reproduce.

Notable points:

- `targetNamed=true`: we are modifying a named module, not an unnamed module.
- `agentUnnamed=true`: the demo's agent JAR runs in an unnamed module.
- `readsBefore=false`, `exportsBefore=false`, `opensBefore=false`: none of the three relationships exist yet.
- Before opening the module, invoking the **public method** fails with `IllegalAccessException` and requesting deep reflection on the **private field** fails with `InaccessibleObjectException`.
- After `redefineModule`, all three queries `canRead/isExported/isOpen` become `true`.
- `openedAlsoExported=true` illustrates that an **opened package is considered exported to the same module at runtime**; we did not add `extraExports` for `demo.target.internal`.
- `publicAfter=API` and `privateAfter=hidden` show that the granted permissions changed **actual access behavior**.
- `app=started` appears last: the JVM invokes the agent's `premain` **before** the application's `main` entry point.

**Limitations of the demo:** `extraReads` is verified via `target.canRead(agent)`, while the two package permissions are further demonstrated via reflection. The example **does not** claim that public reflective invocation by itself proves a new read edge: reflection has its own readability rules. Nor is there any helper-loading operation from the application; the hands-on exercise only demonstrates the module-graph foundation for that step.

## 8. Why must diagnostic checks separate reads, exports, and opens?

The three states are three independent questions, so diagnostic code must also separate them:

~~~java
Module target = someClass.getModule();
Module agent = AccessAgent.class.getModule();

boolean canRead = target.canRead(agent);
boolean publicAccess = target.isExported("demo.target.api", agent);
boolean deepReflection = target.isOpen("demo.target.internal", agent);
~~~

This is **code inside an agent** and `someClass` is a known `Class<?>`; it is not a standalone program. Note the direction:

- `target.canRead(agent)`: **target reads agent**.
- `target.isExported("pkg", agent)`: **target exports pkg to agent**.
- `target.isOpen("pkg", agent)`: **target opens pkg to agent**.

When instrumented code in **target** wants to call a public helper in **agent**, the **target → agent** edge makes sense, though you often need to check whether the helper package is **exported by the agent module to target**. If the agent belongs to an unnamed module, the corresponding JPMS export aspect is usually not an obstacle; however, the target class loader may still **fail to see** the helper.

When the **agent** itself wants to call a public API of **target**, the issue is usually **target exporting the package to agent**. For a private field, **target opening the package to agent** is required. Do not flip the reading module direction just because a diagram has an arrow between two modules.

### 8.1. Why not use `Module.getDescriptor()` to verify changes?

`module-info.class` and `ModuleDescriptor` represent the declared/defined configuration of the module. `redefineModule` expands **runtime** relationships without rewriting the original module descriptor file. When verifying new permissions, call `Module.canRead`, `isExported`, and `isOpen` directly on the right `Module` instead of inferring from the original `module-info.java` contents.

### 8.2. Right module, right layer, right class loader

`Module` is a runtime object, not just a module name `String`. In applications with multiple `ModuleLayer`s, there can be modules with the **same name** in different layers/class loaders. Picking the wrong instance opens permissions on a different object and still fails on the target class.

If you already have `Class<?> targetClass` from `ClassFileTransformer`, an event, or a registry, use `targetClass.getModule()` to find the exact module. If you only have the class name from a transformer at load time, you can leverage the `Module module` parameter of the six-parameter `ClassFileTransformer.transform` overload when appropriate (Java 9+).

## 9. One-way additivity: there is no corresponding revoke operation

According to the Javadoc, `redefineModule` **only expands** read edges, exports, opens, and service uses/provides. It **cannot shrink** the existing set of permissions.

~~~text
Initial state:
    M reads A
    M exports p -> B

Agent calls:
    M additionally reads C
    M opens q -> D

State after:
    M still reads A, and also reads C
    M still exports p -> B, and also opens q -> D
~~~

**There is no way to revoke** granted permissions simply by calling `redefineModule` again with empty sets/maps. A call to `redefineModule(M, Set.of(), Map.of(), Map.of(), Set.of(), Map.of())` does not mean "reset M to defaults".

### 9.1. Broad permissions carry risk

Opening an internal package of a library to the agent module can grant deeper reflection access than intended. For a temporary diagnostic task, this permission remains **in the JVM** after the task finishes. A safe design should:

1. Select the specific module and **specific package**, rather than opening all packages indiscriminately.
2. Select the **specific recipient module**, avoiding opening to all unnamed/arbitrary modules.
3. Add only the permissions actually needed for the helper/probe being instrumented.
4. Restrict which agent code can use the newly granted permissions, and provide lifecycle/cleanup for transformers/loggers/registries.
5. Do not assume that removing a `ClassFileTransformer` or disabling a probe will **revoke** read/export/open edges.
6. Record module expansions in diagnostics so system owners can assess their impact.

These properties do not replace other security policies, module readability/visibility of dependencies, or agent JAR verification.

### 9.2. Concurrency with multiple agents

The Javadoc specifies that `redefineModule` is **safe for concurrent use** and allows multiple agents to modify the same module around the same time. However, that does not mean one agent can "reset" another agent's changes: permissions are **additive**.

Do not infer from this that all surrounding agent logic (caches, logging, class-loader selection, transformers) is automatically thread-safe. Locking/state management must be designed if those parts share mutable data.

## 10. Validity conditions, exceptions, and check order

Before calling:

~~~java
if (!inst.isModifiableModule(targetModule)) {
    // Module does not allow redefineModule on this JVM.
    return;
}
inst.redefineModule(
        targetModule, reads, exports, opens,
        Set.of(), Map.of());
~~~

This is a **snippet inside an agent method**, not runnable standalone; `targetModule`, `reads`, `exports`, and `opens` must be defined. `isModifiableModule` checks whether a module can be modified by this API, which is **different** from `isModifiableClass` and the `isRetransformClassesSupported`/`isRedefineClassesSupported` flags. Those flags are for **replacing class bytecode**, not permission to modify the module graph.

| State/error | Meaning | How to handle |
| --- | --- | --- |
| `isModifiableModule(module) == false` | Module cannot be modified with `redefineModule` according to the JVM | Do not call blindly; report unsupported configuration |
| `UnmodifiableModuleException` | JVM rejects modifying the module | Handle and report the specific module error |
| `IllegalArgumentException` | Package in `extraExports`/`extraOpens` does not belong to the module, or a map value is an empty set; service provider violates constraints | Check `module.getPackages()`, package names, and map values |
| `NullPointerException` | An argument is `null` or a set/map contains a `null` key/value | Use `Set.of()`/`Map.of()` when making no changes |
| `InaccessibleObjectException` at `setAccessible` | Package is not opened to the caller module or has another restriction | Verify the exact target Module/package/caller |
| `IllegalAccessException` when calling a public method via reflection | Public access is invalid within module/access boundaries | Check export and whether the type/member is public |
| `NoClassDefFoundError` after weaving a helper | Helper/dependency cannot be resolved from the target's defining loader | Check loader/module graph/helper search path |
| `IllegalCallerException` when using `Module.addOpens` on another module | The `Module.addOpens` API does not let arbitrary callers modify another named module | Use the agent's `Instrumentation.redefineModule` provided by the JVM |

**The set of modules receiving an export/open must not be empty.** For example:

~~~java
Map.of("demo.target.api", Set.<Module>of()) // Wrong: empty value set
Map.of("demo/target/api", Set.of(agent))    // Wrong: internal name, not package name
Map.of("demo.other", Set.of(agent))         // Wrong if demo.other does not belong to target
~~~

These are **Java expressions illustrating invalid inputs**, not examples to run in production. `extraReads` itself may be an **empty set** because it is a set of additional relationships. Similarly, the entire `extraExports` or `extraOpens` map may be empty; only the **value set for a key present in the map** cannot be empty.

### 10.1. Unnamed module is a special case

According to the Javadoc, calling `redefineModule` on an **unnamed module** is a **no-op**. `isModifiableModule(unnamedModule)` always returns `true` because redefining it does nothing. Therefore, do not interpret `isModifiableModule == true` for an unnamed module as proof that the API actually changed permissions.

If the goal is to grant code **in an unnamed module** access to a named module, you usually need to modify the **named module** on the source side (qualified export/open) or change read edges on the corresponding named module, rather than calling `redefineModule` with the unnamed module itself as the first argument and expecting a result.

### 10.2. Service arguments also have constraints

`extraUses` and `extraProvides` are not the focus, but they should not be populated with arbitrary data. For `extraProvides`, each provider list must be **non-empty**, provider types must be members of that module, and they must actually implement the service. The Javadoc also notes that the agent must ensure accessibility of the service type at instrumented sites; the API does not check everything about whether the service type is in an exported package and a validly read module.

The example in this article passes **two non-null empty containers** so that no service use/provide is expanded.

## 11. Case where a Java agent injects a helper call into bytecode

Concrete scenario: a transformer injects a call:

~~~java
probe.bridge.TraceHooks.onEnter();
~~~

This is an **illustrative snippet** called from a business method after instrumentation. Suppose the method is defined in named module `sales.app` and `TraceHooks` resides in the agent's unnamed module.

You may need:

~~~text
                     sales.app (named)
                       |
                  extraReads
                       |
                       v
                agent unnamed module
                    probe.bridge.TraceHooks

Additional requirements:
  - The target defining loader can actually resolve the helper class.
  - The helper is in a package with appropriate visibility.
  - The helper signature does not reference types invisible to the target loader.
  - The target module has the necessary reads relationship when linking bytecode.
~~~

If a different goal is for the agent to use reflection to read a private field `sales.app.internal.OrderState`, the agent must **open `sales.app`'s package to the agent module**. That is a call to `redefineModule(salesAppModule, ..., extraOpens=Map.of("sales.app.internal", Set.of(agentModule)), ...)`. The two behaviors are **different**: one is the target wanting to **call a helper**, while the other is the agent wanting to **read the target**.

### 11.1. JPMS does not replace class loading

Even when `sales.app.canRead(agentModule) == true`, the class loader of `sales.app` still needs to **find** the helper bytecode. An isolated custom plugin loader may not see classes in the system/agent loader. In that case, `NoClassDefFoundError` or other linkage errors can still occur even though `Module.canRead` is correct.

Possible solutions include:

- Defining the helper in a **shared loader** accessible to targets.
- For compatible agents, adding a **minimal helper JAR** to the bootstrap search path via `Instrumentation.appendToBootstrapClassLoaderSearch` when the architecture requires it, and verifying actual module/package access.
- Placing separate helpers in each plugin's own loader if isolation is desired, while understanding that static counters/registries will be **one copy per loader**.
- Using a bridge/interface whose contract lives in a shared loader, without passing a plugin's implementation type across boundaries and casting by the same binary name.

`redefineModule` **does not create helper classes**, does not append JARs, does not change class loaders, does not modify `<clinit>` bytecode, and does not make every class in the JVM modifiable.

### 11.2. Agent startup and dynamic attach are not the same

The example uses `premain` with `-javaagent`, so `Instrumentation` is available from JVM startup. If an agent is loaded later via `agentmain`, attach/dynamic agent loading depends on the JVM and separate configuration. Both loading styles can provide `Instrumentation` when supported by the JVM, but do not conflate attach capability with `redefineModule` permissions.

## 12. Comparison with other JPMS configuration methods

There are ways to add permissions **before the JVM runs**, without calling `Instrumentation` in an agent:

| Mechanism | Scope | How it differs from `redefineModule` |
| --- | --- | --- |
| `requires other.module;` | Read edge in `module-info.java` | Source/module descriptor configuration |
| `exports p;` or `exports p to m;` | Exports public package | Declared in module descriptor |
| `opens p;` or `opens p to m;` | Allows deep reflection at runtime | Declared in module descriptor |
| `--add-reads M=H` | Additional read at launch | Set via JVM option before startup |
| `--add-exports M/p=H` | Targeted package export at launch | No agent needed; already active before `main`/`premain` |
| `--add-opens M/p=H` | Targeted package open at launch | No agent needed; already active beforehand |
| `Module.addReads/addExports/addOpens` | Modifies relationships per caller rules | A named module can usually only modify itself from a valid caller |
| `Instrumentation.redefineModule` | Expands runtime graph from an agent | Has `Instrumentation` and can modify other modules per the API contract |

Example of an equivalent configuration for the app module to read the unnamed module, export the public API, and open the private package to the unnamed module:

~~~bash
java --add-reads demo.target=ALL-UNNAMED --add-exports demo.target/demo.target.api=ALL-UNNAMED --add-opens demo.target/demo.target.internal=ALL-UNNAMED --module-path mods -m demo.target/demo.target.app.Main
~~~

**Do not use this command to reproduce the before/after stdout of the hands-on exercise**: because the permissions are already granted **at startup**, the `...Before=false` lines and initial access errors will no longer occur. This is a **syntax comparison command**, not a second step to run with the agent.

In particular, `--add-opens` and `--add-exports` in the command target `ALL-UNNAMED`, which has a broader scope than `Set.of(agentModule)` if the JVM has multiple unnamed modules. For sensitive permissions, use the narrowest possible target.

## 13. Diagnostic workflow when an agent still hits module access errors

1. **Confirm the right JVM/agent:** `premain`/`agentmain` receives the `Instrumentation` for the JVM being monitored.
2. **Confirm the right `Module` object:** obtain it from `Class<?>.getModule()` or the `transform(Module, ...)` callback when possible; do not pick a module solely by name in an arbitrary layer.
3. **Check whether the source module is named:** for an unnamed source, `redefineModule` is a no-op.
4. **Check modifiability:** call `isModifiableModule`, and handle `UnmodifiableModuleException` if needed.
5. **Log the three relationships separately:** `source.canRead(destination)`, `source.isExported(pkg, target)`, `source.isOpen(pkg, target)`; verify the exact direction.
6. **Check the package key:** exact dotted name, belonging to `source.getPackages()`; map value set is non-empty.
7. **Call once intentionally:** pass `Set.of()`/`Map.of()` for dimensions that do not need to be opened.
8. **Verify after the call:** run the same three runtime queries, then test the exact public invocation/private reflection needed.
9. **If it still fails:** check class-loader visibility, the right helper version, package/private/final boundaries, JPMS module layer, cached/instrumented code, and the error stack.
10. **Maintain security:** record granted permissions for later review; do not assume they can be revoked by a subsequent call.

Diagnostic example when `Class<?> targetType` and `Module agentModule` are already known:

~~~java
Module targetModule = targetType.getModule();
String packageName = targetType.getPackageName();

System.out.println("module=" + targetModule.getName());
System.out.println("package=" + packageName);
System.out.println("modifiable="
        + inst.isModifiableModule(targetModule));
System.out.println("openedToAgent="
        + targetModule.isOpen(packageName, agentModule));
~~~

This is **code inside an agent** and requires `inst`, `targetType`, and `agentModule` variables. Do not log excessive sensitive data or print thousands of classes into a logger inside a transformer callback: the logger/helper itself can trigger class loading.

## 14. Common misconceptions

1. **"`redefineModule` is the same as `redefineClasses`."** False: one API modifies runtime module relationships, while the other replaces class-file definitions.
2. **"`extraReads` automatically allows reading private fields."** False: readability is different from deep reflection.
3. **"`extraExports` is enough to call `setAccessible(true)` on any private member."** False: an open package and checking other constraints are required.
4. **"`extraOpens` only relates to source compilation."** False: it is for runtime reflection capabilities; an open package is also considered exported to the recipient module when queried at runtime.
5. **"The key of `extraOpens` must be `java/lang`."** False: the key is a dotted package name like `"java.lang"`.
6. **"A map containing a non-existent package is silently ignored."** False: the API may throw `IllegalArgumentException`.
7. **"An empty target module set means export to everyone."** False: an empty value set is invalid; it is not an unqualified export.
8. **"Pass `null` for `extraUses`/`extraProvides` when unused."** False: they must be non-null; use empty containers.
9. **"Once permissions are added, call again with empty collections to remove them."** False: relationships can only be expanded.
10. **"`isModifiableModule` is equivalent to `isModifiableClass`."** False: they check two different kinds of objects and mechanisms.
11. **"`isModifiableModule(unnamed) == true` means it can be modified."** False: redefining an unnamed module is a no-op.
12. **"With the right read edge, the class loader will automatically find the helper."** False: the module graph and class-loader lookup are two separate constraints.
13. **"`isExported(pkg, target)` proves every module can see the package."** False: this may only be a qualified export.
14. **"If the agent can load a module, reflection is guaranteed to succeed."** False: the right caller module, target class/member, and opens/export are required.
15. **"The agent permanently modifies `module-info.java` on disk."** False: changes take effect on the runtime module in the JVM.
16. **"Multiple agents calling concurrently always cause conflicts."** False: the `redefineModule` method is documented by Javadoc as safe for concurrent use; however, callers must still manage other state.
17. **"Opening `java.base` unconditionally is the optimal fix for all reflection errors."** False: overly broad opening weakens encapsulation; grant only the necessary package/target.
18. **"Reflecting into an open package proves the read edge changed."** False: reflection has different access-check characteristics from normal Java linkage; `canRead` must be checked separately.

## 15. Self-check questions

1. In `redefineModule(M, Set.of(H), ...)`, which module **reads** which module?
2. Package `p.internal` has been `extraExports`-ed to the agent but not yet `extraOpens`-ed. Is `setAccessible(true)` on a private field guaranteed to work?
3. Why can `Module.isOpen("p", agent)` and `Module.isOpen("p")` return different results?
4. Why can `isExported("p.internal", agent)` be `true` after granting only `extraOpens`?
5. In the example, what are the two exceptions thrown before opening the public API and before opening the private field?
6. Why is `agent.getClass().getModule()` not the right way to get the module of **class `AccessAgent`** if `agent` is already a `Module` object? Use `AccessAgent.class.getModule()`.
7. When the target application is in a module layer other than the boot layer, how do you select the right `Module` to modify?
8. If a helper is in the agent's unnamed module but the target class loader cannot see the helper, is granting `extraReads` alone enough?
9. Why is passing `Map.of("p", Set.of())` for `extraExports` wrong?
10. Can an agent revoke qualified opens via a second `redefineModule` call with an empty map?
11. What does `isModifiableModule(unnamedModule)` return, and what effect does calling `redefineModule` on an unnamed module have?
12. Why does the demo run without declaring `Can-Redefine-Classes: true`?
13. When additional service providers are needed, why must the agent itself verify the accessibility of the service type at the instrumentation site?

**Conclusion:** `Instrumentation.redefineModule` is a tool for **dynamically expanding the module graph** for an agent. `extraReads` adds a read edge **from the module being modified**, `extraExports` opens public packages **to specific targets**, and `extraOpens` enables **targeted deep reflection**. The three relationship types are not interchangeable; class loaders, module layers, and actual access constraints must also be accounted for. This is an **additive-only** operation in the JVM, so grant the minimum necessary, verify with `Module.canRead`/`isExported`/`isOpen`, and test at the exact call site being instrumented.

### References

- [Java 17 — Instrumentation: redefineModule, isModifiableModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — Module: canRead, isExported, isOpen](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java 17 — AccessibleObject: setAccessible and trySetAccessible](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java 17 — Package java.lang.instrument: agent manifest and lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261)
