# Additive Relationships Are Not Access Revocation Operations

## 1. Objective: Understanding the Exact Permissions of Instrumentation.redefineModule

When building a Java agent for an application using the **Java Platform Module System (JPMS)**, you may encounter errors because instrumented code needs to read another module, access an unexported package, perform deep reflection on private members, or use a service via `ServiceLoader`. Since Java 9, `java.lang.instrument.Instrumentation` has provided the `redefineModule(...)` method to help agents **add** module relationships at runtime.

The most important takeaway of this lesson: **`redefineModule` has no permission revocation functionality**. Having the word "redefine" in the method name easily leads learners to think they can pass a new module graph to overwrite the old module graph—for example, granting `opens` for a period of time and then calling it with empty sets/maps to remove it. This understanding is **incorrect**.

According to Java SE 17, the method only **expands** module read relationships, package exports/opens, and service use/provide relationships. It **cannot reduce** existing relationships. In particular, passing an empty set or map only means **no new relationships are added in this call**, and does **not remove old relationships**.

After this lesson, you will be able to:

1. Distinguish the five parameters `extraReads`, `extraExports`, `extraOpens`, `extraUses`, and `extraProvides`.
2. Distinguish **read edge**, **export**, and **open** in JPMS access control.
3. Correctly predict the result of calling `redefineModule` a second time with all empty sets/maps.
4. Understand that `isModifiableModule` and whether a module is named or unnamed are two separate aspects.
5. Run **Java 17+** with a named module, startup agent, compile/run commands, and clear stdout.
6. Analyze the impact of additive relationships on security, least privilege, plugins, tracing, and agent lifecycle.
7. Distinguish "cannot be revoked via this API" from other security controls or isolation mechanisms.

## 2. Module Graph Definition and the Additive-Only Property

JPMS represents relationships between modules using a directed graph and per-module metadata. For a class belonging to one module to access a class in another module, a **reads relationship** is usually required, and the package containing the target class must be **exported** or **opened** appropriately for the type of access.

Imagine:

~~~text
Named module: demo.vault                       Unnamed module: application/agent
+-----------------------------+                +--------------------------+
| vault.api                   |                | demo.Main / helper       |
| vault.internal              |                |                          |
|                             |                |                          |
| Initial module graph:       |                |                          |
|   vault.api not exported    |                |                          |
|   vault.internal not opened |                |                          |
+-----------------------------+                +--------------------------+
            |
            | Instrumentation.redefineModule(...)
            v
+-----------------------------+
| Expanded module graph:      |
|   exports vault.api  -------> app module
|   opens vault.internal -----> app module
|   reads java.sql -----------> java.sql module
|   uses java.sql.Driver
+-----------------------------+
            |
            | redefineModule(vault, empty, empty, empty, empty, empty)
            v
+-----------------------------+
| Previous relationships STAY:|
|   export / open / reads /   |
|   uses still exist          |
+-----------------------------+
~~~

This is a **relationship diagram**, not complete code structure. The actual syntax of `redefineModule` will be explained in section 3 and tested in section 6.

### 2.1. Why Is "redefine" Not "replace all"?

In `redefineClasses`, the caller provides replacement bytes for an existing class. However, **`redefineModule` has a different contract**: it takes sets/maps containing **additional** relationships, not a full snapshot of a new graph to enforce.

The right mental model:

~~~text
reads_after    = reads_before    U extraReads
exports_after  = exports_before  U extraExports
opens_after    = opens_before    U extraOpens
uses_after     = uses_before     U extraUses
provides_after = provides_before U extraProvides
~~~

The `U` symbol here represents a conceptual **union of relationships**, not Java code; specifically, `exports`, `opens`, and `provides` also have their own map/target/provider structures and validation rules. The formula is meant to clarify the **direction of strictly expanding relationship scope**, not to guarantee that every collection type in the API is implemented as a Set union.

The specification explicitly states that you cannot **reduce** the set of read modules, the set of exported/opened packages, or the used/provided services. These properties may have originated from `module-info.java`, from launcher options like `--add-opens`, from another agent, or from a previous `redefineModule` call.

### 2.2. When Should It Be Used?

An agent needs to access a helper in a module that is not yet read, needs reflection to observe private fields, or needs to integrate a service from another module. This is a requirement for **intentional privilege escalation** at runtime. If the problem is **revoking permissions after turning off the agent**, `redefineModule` is not the API to solve it.

## 3. API Signature and Meaning of the Five Parameters

In Java 17, the full signature is:

~~~java
void redefineModule(
        Module module,
        Set<Module> extraReads,
        Map<String, Set<Module>> extraExports,
        Map<String, Set<Module>> extraOpens,
        Set<Class<?>> extraUses,
        Map<Class<?>, List<Class<?>>> extraProvides);
~~~

This is a **reference signature**; to use it in a real Java program, invoke the method on an `Instrumentation` instance and import `java.lang.Module`, `java.util.*`. All collections must be **non-null**; empty collections are valid when no corresponding relationship type needs to be added.

| Parameter | What is added | Relationship direction / constraints |
|---|---|---|
| `module` | Source module to be updated | Usually a **named module** to be instrumented |
| `extraReads` | Modules that `module` is additionally allowed to read | From `module` **to** each module in the Set |
| `extraExports` | Public packages of `module` additionally exported to target modules | Key is a **package name present in `module`**, value is a **non-empty** Set of target modules |
| `extraOpens` | Packages of `module` additionally opened to target modules | Key is a **package name present in `module`**, value is a **non-empty** Set of target modules |
| `extraUses` | Service types that `module` is allowed to use | Set of service `Class<?>` objects; the agent must ensure the service type is accessible at the use site |
| `extraProvides` | Providers that `module` additionally provides | Key is the service type, value is a **non-empty List of provider classes**, provider belongs to the source module and implements the service |

**There are no parameters named `removeReads`, `removeExports`, `removeOpens`, `removeUses`, or `removeProvides`.** The parameters all start with `extra`. Passing `Map.of()`/`Set.of()` is not a "clear configuration" syntax.

A sample call:

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(helperModule),
        Map.of("app.api", Set.of(consumerModule)),
        Map.of("app.internal", Set.of(agentModule)),
        Set.of(MyService.class),
        Map.of(MyService.class, List.of(MyProvider.class)));
~~~

The snippet above is a **structural template**, not a standalone demo; the module variables and service/provider must be declared, the packages must belong to the right source module, and `MyProvider` must be a valid provider in the source module. Do not arbitrarily populate all parameters if you only need to open one package.

### 3.1. Separating Module and Class Capabilities

`Instrumentation` has:

~~~java
boolean isModifiableModule(Module module);
~~~

This check is for **module redefinition**; it is **not** `isModifiableClass(Class<?>)`, `isRedefineClassesSupported()`, or `isRetransformClassesSupported()`. You do not need to declare `Can-Redefine-Classes: true` just to call `redefineModule`.

If `isModifiableModule(namedModule)` is false and you still attempt to update it, the VM may throw `UnmodifiableModuleException`. If parameters are invalid, `IllegalArgumentException` or `NullPointerException` may occur depending on the case.

### 3.2. Unnamed Module: "Modifiable" but No-Op

The specification has an easily surprising detail:

- `isModifiableModule(unnamedModule)` always returns **true**;
- `redefineModule(unnamedModule, ...)` is a **no-op**.

Do not conclude **"isModifiableModule true means every change takes effect"**. Unnamed modules already have their own broad read/export/open rules in JPMS; the API does not need to and does not perform named-module-style graph updates for them.

In the example, the source to modify is the **named module** `demo.vault`. The module of `Main` on the classpath is an **unnamed module** acting as the target receiving permissions.

## 4. Reads, Exports, and Opens Are Not a Single Permission

### 4.1. Reads: Knowing and Linking to Another Module

`source.canRead(target)` queries whether the source module has a reads relationship with the target module. `extraReads = Set.of(target)` expands the graph so that source additionally reads target. However, **a read edge does not automatically export the target's packages**.

If `moduleA` reads `moduleB`, that does not mean `moduleB` must allow `moduleA` deep reflection into all private fields. Appropriate export/open relationships **granted by the module containing the target package** are still required.

### 4.2. Exports: Accessing Public Types/Members Under JPMS

`extraExports` causes a package in the **source module** to be exported to specific target modules. This enables normal access to **public types and public members**, provided other reads/accessibility conditions are met.

For example, `Map.of("vault.api", Set.of(client))` opens export access for `vault.api` to the exact `client` module. This is a **qualified export**, not opening the package to all modules. It **does not automatically open all private members for deep reflection**.

### 4.3. Opens: Deep Reflection May Be Permitted

`extraOpens` causes a package in the source module to be opened to target modules. When a package is opened, reflection calls such as `Field.setAccessible(true)` can be permitted under JPMS, though they are still subject to other platform controls and reflection semantics.

For example, `Map.of("vault.internal", Set.of(client))` allows the `client` module to request deep reflection into the source's `vault.internal` package. **Opening a package grants a broader access scope than exporting a public API**, so it requires great caution.

### 4.4. Relationship Selection Table

| What the agent wants to do | Relationship usually needed | What must not be inferred |
|---|---|---|
| Code in module A references module B | `A reads B` | Does not automatically allow reading private fields of B |
| Consumer module needs public API of a package in source | `source exports package -> consumer` | Does not automatically open private fields |
| Reflection needs `setAccessible(true)` on a non-public member | `source opens package -> caller module` | Does not bypass all other security control mechanisms |
| Module wants to use a service via `ServiceLoader` | `uses ServiceType` and type accessible at the call site | Does not automatically create a provider |
| Module provides a new service provider | `provides ServiceType with Provider` | Provider must belong to the source module, implement the service, and satisfy provider rules |

**An often overlooked point:** `module-info.java` is a build/deploy-time declaration; `redefineModule` adjusts the **runtime module graph**. A `javac` command in a separate build pipeline **does not automatically know** about relationships an agent might add later when the application runs. If Java source directly references a package that is not exported at compile time, proper module/build design is required; runtime updates do not replace compile-time rules.

## 5. Additive Relationships Cannot Be Revoked by Calling Again with Empty Sets

Suppose the agent has called:

~~~java
inst.redefineModule(
        vault,
        Set.of(sql),
        Map.of("vault.api", Set.of(client)),
        Map.of("vault.internal", Set.of(client)),
        Set.of(java.sql.Driver.class),
        Map.of());
~~~

After the valid call, `vault` has added reads/export/open/uses. Later you want to "undo" it and call:

~~~java
inst.redefineModule(
        vault,
        Set.of(),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

**No relationships are removed.** The second call only says: *"In this update, I am not adding anything."* It does **not** mean: *"Set reads/exports/opens/uses/provides to empty."*

Before–after diagram:

~~~text
Before agent:
  vault.canRead(sql)                  = false
  vault.isExported("vault.api", app)  = false
  vault.isOpen("vault.internal", app) = false
  vault.canUse(java.sql.Driver.class)= false

Agent adds:
  reads sql, exports api -> app, opens internal -> app, uses Driver

Immediately after:
  reads/export/open/uses = true

Agent calls again with all empty collections:
  reads/export/open/uses = true   // Not revoked
~~~

**This is not merely "the API lacks a remove method."** The `redefineModule` specification actively declares that **the set of relationships cannot be reduced**. If the caller supplies a smaller set than the previous call, the API still only **adds** the listed elements, rather than removing absent elements.

**Operational consequence:** it is impossible to guarantee "temporarily open private access for 5 seconds, then close it again using the same API." Once added, the new relationship remains part of the runtime module **until the corresponding runtime/module lifecycle ends**, aside from other isolation/lifecycle mechanisms outside `redefineModule`. To get a reliably clean boundary, you typically need to restart the JVM or move the workload to a newly designed, isolated environment/module identity; do not make an empty call to pretend revocation happened.

## 6. Demo 1 (Java 17+): Expanding reads/exports/opens/uses, Failed "Undo" Attempt

### 6.1. Lab Design

We create:

- **Named module `demo.vault`**, containing two packages `vault.api` and `vault.internal` without **exporting/opening** any package in `module-info.java`.
- **`demo.Main`** on the classpath, belonging to the **unnamed module**; it only uses reflection to obtain the type in `vault.internal`, without directly importing the private package.
- **`demo.ModuleAgent`**, a startup Java agent receiving `Instrumentation`, which then **while the app is running** expands the graph using `redefineModule`.
- Module **`java.sql`**, used as a reads target, and the `java.sql.Driver` service used to demonstrate `uses`.
- At the end of the demo, the agent calls `redefineModule` again with **all empty collections**, then re-measures the module graph.

### 6.2. Directory Tree

~~~text
module-additive-lab/
├── agent.mf
├── src/
│   ├── vault/
│   │   ├── module-info.java
│   │   └── vault/
│   │       ├── api/
│   │       │   └── Visible.java
│   │       └── internal/
│   │           └── Secret.java
│   ├── agent/
│   │   └── demo/
│   │       └── ModuleAgent.java
│   └── app/
│       └── demo/
│           └── Main.java
└── out/                        # generated on compilation
    ├── vault/
    ├── agent/
    ├── app/
    └── module-agent.jar
~~~

The demo code below has been compiled with `javac --release 17` and run on a JDK supporting Java 17+ and module instrumentation.

### 6.3. Defining the Named Module demo.vault

File **`src/vault/module-info.java`**:

~~~java
module demo.vault {
}
~~~

File **`src/vault/vault/api/Visible.java`**:

~~~java
package vault.api;

public final class Visible {
    public static String hello() {
        return "hello";
    }
}
~~~

File **`src/vault/vault/internal/Secret.java`**:

~~~java
package vault.internal;

public final class Secret {
    private final String token = "demo-secret";

    public Secret() {
    }
}
~~~

An empty module descriptor means the packages `vault.api` and `vault.internal` are **not yet exported/opened** to the unnamed client. `Visible` is a public class, but being public **does not automatically bypass the module export barrier**. `Secret` has a private field to test deep reflection.

### 6.4. Agent Adding Four Relationships

File **`src/agent/demo/ModuleAgent.java`**:

~~~java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

public final class ModuleAgent {
    private static Instrumentation inst;

    public static void premain(
            String options, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void expand(
            Module vault, Module client, Module sql) {
        if (!inst.isModifiableModule(vault)) {
            throw new IllegalStateException(
                    "Module not modifiable");
        }

        inst.redefineModule(
                vault,
                Set.of(sql),
                Map.of("vault.api", Set.of(client)),
                Map.of("vault.internal", Set.of(client)),
                Set.of(java.sql.Driver.class),
                Map.of());

        System.out.println("agent:expanded");
    }

    public static void emptyUpdate(Module vault) {
        inst.redefineModule(
                vault,
                Set.of(),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of());

        System.out.println("agent:empty-request");
    }
}
~~~

**Exact breakdown of each parameter in `expand`:**

1. `vault` is the **source named module** to be modified.
2. `Set.of(sql)` makes `vault` **additionally read the `java.sql` module**.
3. `Map.of("vault.api", Set.of(client))` exports the `vault.api` package **strictly to the unnamed client module**.
4. `Map.of("vault.internal", Set.of(client))` opens the `vault.internal` package **strictly to the unnamed client module** so reflection can access private fields.
5. `Set.of(java.sql.Driver.class)` adds the **uses `java.sql.Driver`** relationship for `vault`; we also add reads to `java.sql` so the service type is reachable when needed.
6. `Map.of()` in the last parameter means **no service providers are added** in this call.
7. `emptyUpdate` performs a call with **no additions**. It has no revocation syntax.
8. There is no `ClassFileTransformer`, `retransformClasses`, or `redefineClasses` in this example. This is **changing module relationships**, not changing class bytecode.

A startup agent is loaded before `main` to obtain `Instrumentation`, but `redefineModule` is only invoked **when the application explicitly calls `expand`**, after the modules have been loaded. This allows measuring the "before/after" state within the same JVM.

### 6.5. Main Checking Runtime Permissions and Reflection

File **`src/app/demo/Main.java`**:

~~~java
package demo;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class Main {
    static void state(
            String label, Module source,
            Module target, Module sql) {
        System.out.println(
                label + ": reads-sql=" + source.canRead(sql)
                + " exports-api=" + source.isExported(
                        "vault.api", target)
                + " opens-internal=" + source.isOpen(
                        "vault.internal", target)
                + " uses-driver=" + source.canUse(
                        java.sql.Driver.class));
    }

    public static void main(String[] args)
            throws Exception {
        Class<?> cls = Class.forName("vault.internal.Secret");
        Module source = cls.getModule();
        Module target = Main.class.getModule();
        Module sql = java.sql.Driver.class.getModule();

        state("before", source, target, sql);

        Constructor<?> ctor = cls.getDeclaredConstructor();
        boolean blocked;
        try {
            ctor.setAccessible(true);
            blocked = false;
        } catch (InaccessibleObjectException expected) {
            blocked = true;
        }
        System.out.println(
                "before:reflect-blocked=" + blocked);

        ModuleAgent.expand(source, target, sql);
        state("after", source, target, sql);

        ctor.setAccessible(true);
        Object obj = ctor.newInstance();
        Field token = cls.getDeclaredField("token");
        token.setAccessible(true);
        System.out.println(
                "after:secret=" + token.get(obj));

        ModuleAgent.emptyUpdate(source);
        state("after-empty", source, target, sql);
        System.out.println(
                "after-empty:secret=" + token.get(obj));
    }
}
~~~

**Valuable learning observations:**

- `Class.forName` can find a class in a resolved module; finding the class **does not mean** reflection has permission to access private members.
- `source.canRead(sql)` checks the read edge, `isExported` and `isOpen` check per-package/target module, and `canUse(Driver.class)` checks the service use relation.
- Before opening the package, `ctor.setAccessible(true)` is rejected with `InaccessibleObjectException`, which is intentionally caught so the demo can continue.
- After the agent adds `opens`, `setAccessible(true)` on the constructor and private field succeeds; this is an observable effect, not just boolean metadata.
- At the end of the demo, `emptyUpdate` **does not revoke** the relationships: both introspection and the opened reflection permissions remain in effect.

**Note:** Do not pass package names using slash paths like `vault/internal`. For `extraOpens` and `extraExports`, the keys are **dot-separated package names**: `vault.internal`, `vault.api`.

### 6.6. Agent Manifest

File **`agent.mf`**, ending with a newline:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ModuleAgent

~~~

`Can-Redefine-Classes: true` or `Can-Retransform-Classes: true` is not needed, because the demo does not use those two capabilities. `redefineModule` has been supported since Java 9 and has its own capability check via `isModifiableModule`.

### 6.7. Build and Run Commands on Java 17+

From the `module-additive-lab` root directory, create the output directories. If using Bash:

~~~bash
mkdir -p out/vault out/agent out/app
~~~

If using PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/vault, out/agent, out/app
~~~

Compile with **JDK 17 or a newer JDK** targeting Java 17 API/source:

~~~bash
javac --release 17 -d out/vault src/vault/module-info.java src/vault/vault/api/Visible.java src/vault/vault/internal/Secret.java
javac --release 17 -d out/agent src/agent/demo/ModuleAgent.java
javac --release 17 -cp out/agent -d out/app src/app/demo/Main.java
jar --create --file out/module-agent.jar --manifest agent.mf -C out/agent .
~~~

**Why are there three output directories?**

- `out/vault` contains the **named module** `demo.vault` and `module-info.class`.
- `out/agent` contains `ModuleAgent.class`, packaged into the Java agent JAR.
- `out/app` contains `Main.class` in the unnamed module on the classpath.
- `Main` does not directly import `vault.internal.Secret`, so the source does not fail compilation due to the named module not exporting the package. It uses reflection after the module is resolved.

Run:

~~~bash
java -Xverify:all --module-path out/vault --add-modules demo.vault,java.sql -javaagent:out/module-agent.jar -cp out/app demo.Main
~~~

Options:

- `--module-path out/vault` declares the location of the named module.
- `--add-modules demo.vault,java.sql` ensures **both named modules are resolved** at JVM startup; it does not replace `redefineModule`.
- `-javaagent` loads the agent to obtain `Instrumentation`.
- `-cp out/app` runs `Main` in the unnamed module.
- `-Xverify:all` helps verify classes in the test environment.

**Verified stdout with a JDK supporting these APIs:**

~~~text
before: reads-sql=false exports-api=false opens-internal=false uses-driver=false
before:reflect-blocked=true
agent:expanded
after: reads-sql=true exports-api=true opens-internal=true uses-driver=true
after:secret=demo-secret
agent:empty-request
after-empty: reads-sql=true exports-api=true opens-internal=true uses-driver=true
after-empty:secret=demo-secret
~~~

### 6.8. Interpreting Each Milestone

| Point in time | Runtime relationships | Deep reflection |
|---|---|---|
| Before calling `expand` | `reads-sql`, `exports-api`, `opens-internal`, `uses-driver` are all **false** in the lab | `setAccessible(true)` is rejected |
| After `expand` succeeds | All four become **true** | Private field `token` can be read |
| After `emptyUpdate` | Relationships **remain true**, not revoked | Reading `token` continues to work |

The line `after-empty:secret=demo-secret` is memorable proof: **passing empty sets to `redefineModule` does not "close" the package again**. Note also that previously obtained or configured reflection objects/methods are not a valid way to simulate revocation either: the API has no operation to close module relationships in this runtime.

**Conditions for accurate reproduction:** run in a fresh JVM, do not pre-add `--add-exports` or `--add-opens` for the demo packages, and use the exact empty module descriptor shown above. If another agent has already opened the package beforehand, the "false" baseline may not hold; `redefineModule` still provides no revocation path.

## 7. Demo 2: extraProvides Is Also Additive, Not a Replacement List

In `redefineModule`, the **`extraProvides`** parameter allows a named module to additionally register **provider classes** for a service type. A provider must:

- belong to the source module itself that is being redefined;
- actually implement or extend the service type;
- have a provider form supported by `ServiceLoader`;
- be in a **non-empty List** for each service type key.

Importantly: if a subsequent call omits an old provider, that **does not remove** the already-registered provider.

### 7.1. Service Mini-Lab Layout

~~~text
module-provider-lab/
├── agent.mf
├── src/
│   ├── spi/
│   │   ├── module-info.java
│   │   └── spi/
│   │       ├── api/
│   │       │   └── Greeting.java
│   │       └── impl/
│   │           └── English.java
│   ├── agent/
│   │   └── demo/
│   │       └── ProvideAgent.java
│   └── app/
│       └── demo/
│           └── Main.java
└── out/
    ├── spi/
    ├── agent/
    ├── app/
    └── provide-agent.jar
~~~

Here, the named module `demo.spi` exports the service API `spi.api` so the application can use the interface, but **has not declared `provides` in module-info**. The provider class `spi.impl.English` exists in the module from the start but has not yet been published as a service provider for `ServiceLoader`.

### 7.2. Named Module Service and Provider

File **`src/spi/module-info.java`**:

~~~java
module demo.spi {
    exports spi.api;
}
~~~

File **`src/spi/spi/api/Greeting.java`**:

~~~java
package spi.api;

public interface Greeting {
    String message();
}
~~~

File **`src/spi/spi/impl/English.java`**:

~~~java
package spi.impl;

public final class English implements spi.api.Greeting {
    public English() {
    }

    public String message() {
        return "hello";
    }
}
~~~

There is no need to export the `spi.impl` package: `ServiceLoader` has its own mechanism for handling named-module providers according to specific rules, once the module properly declares/publishes the provider.

### 7.3. Agent Using extraProvides

File **`src/agent/demo/ProvideAgent.java`**:

~~~java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class ProvideAgent {
    private static Instrumentation inst;

    public static void premain(
            String opts, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void add(
            Module module, Class<?> service,
            Class<?> provider) {
        inst.redefineModule(
                module,
                Set.of(),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of(service, List.of(provider)));
    }

    public static void empty(Module module) {
        inst.redefineModule(
                module,
                Set.of(),
                Map.of(),
                Map.of(),
                Set.of(),
                Map.of());
    }
}
~~~

Only the **sixth parameter** `extraProvides` has data in the `add` call. The other empty maps/sets explicitly indicate no `reads`, `exports`, `opens`, or `uses` are added in this call. `empty` is the control empty call: it does not cancel the provider.

### 7.4. Application Using ServiceLoader

File **`src/app/demo/Main.java`**:

~~~java
package demo;

import spi.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args)
            throws Exception {
        Class<?> provider = Class.forName("spi.impl.English");
        Module source = Greeting.class.getModule();

        System.out.println(
                "before-providers="
                + ServiceLoader.load(Greeting.class).stream().count());

        ProvideAgent.add(source, Greeting.class, provider);

        System.out.println(
                "after-providers="
                + ServiceLoader.load(Greeting.class).stream().count());
        System.out.println(
                "provider-message="
                + ServiceLoader.load(Greeting.class)
                        .findFirst().orElseThrow().message());

        ProvideAgent.empty(source);
        System.out.println(
                "after-empty-providers="
                + ServiceLoader.load(Greeting.class).stream().count());
    }
}
~~~

Each measurement creates **a new `ServiceLoader`** to observe the changed state; if the application holds a cached loader/provider list from earlier, that cache might not immediately reflect the addition. `Main` is an unnamed module, which can use the public service type from the `spi.api` package of the named module `demo.spi` once the module is resolved.

### 7.5. Manifest, Build, and Run

File **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProvideAgent

~~~

Create output directories with Bash:

~~~bash
mkdir -p out/spi out/agent out/app
~~~

Or PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/spi, out/agent, out/app
~~~

From the `module-provider-lab` root directory:

~~~bash
javac --release 17 -d out/spi src/spi/module-info.java src/spi/spi/api/Greeting.java src/spi/spi/impl/English.java
javac --release 17 -d out/agent src/agent/demo/ProvideAgent.java
javac --release 17 --module-path out/spi --add-modules demo.spi -cp out/agent -d out/app src/app/demo/Main.java
jar --create --file out/provide-agent.jar --manifest agent.mf -C out/agent .
java -Xverify:all --module-path out/spi --add-modules demo.spi -javaagent:out/provide-agent.jar -cp out/app demo.Main
~~~

**Tested stdout:**

~~~text
before-providers=0
after-providers=1
provider-message=hello
after-empty-providers=1
~~~

Meaning:

1. The `demo.spi` module has the provider class but **has not registered the provides relationship**, so `ServiceLoader` cannot find it in the initial check.
2. The agent calls `redefineModule` with `extraProvides`, publishing the existing provider.
3. A fresh `ServiceLoader` lookup finds the provider, instantiates the object, and calls `message()` successfully.
4. A second `redefineModule` call with `Map.of()` in `extraProvides` **does not remove the provider**: the count remains 1.

Thus, the **additive-only** property applies not only to reads/exports/opens, but also to **service provision**. This demo has a limitation: it does not assert that all previously cached `ServiceLoader` instances automatically reload immediately; the program creates a new loader for each check.

## 8. Why Can't You "Temporarily Revoke" with a Module Agent?

### 8.1. Opening a Package Comes Without a Lease/Timeout

`redefineModule` does not accept a timestamp, TTL, revoke token, or undo API. It does not create "temporary permissions" that expire on their own. An agent can use a configuration condition to **choose not to continue exploiting the permission**, but that is **different** from the added JPMS permission being withdrawn from the module graph.

For example, in Demo 1, after `emptyUpdate`, `source.isOpen("vault.internal", client)` is still true. Even if the agent disables its exporter and stops calling reflection, the package remains open at the module graph level for the designated client module.

### 8.2. removeTransformer and detach Are Not Revocations

- `Instrumentation.removeTransformer(transformer)` unregisters a classfile transformer for future transformations; it **does not invoke module redefinition in reverse**.
- `VirtualMachine.detach()` in the Attach API disconnects control from the helper to the target JVM; it **does not close opened packages**.
- A running JVM does not treat an "agent finished" event as a condition to revoke module edges.
- Once an agent is loaded into a target JVM, the permissions it is allowed to create can affect the lifetime of the JVM, so lifecycle must be accounted for right from the design phase.

### 8.3. Changing the Module Graph Differs from Changing the Module Descriptor

`Module.getDescriptor()` reflects the module's declared information; dynamically added relationships do not necessarily appear as new directives in the original descriptor. Check runtime effectiveness using **`canRead`, `isExported`, `isOpen`, `canUse`** or actual behavior like reflection/`ServiceLoader`, rather than just reading `module-info.class` and concluding the current edges.

### 8.4. What to Do If You Want a New Boundary?

If the security requirement demands **closing permissions after a measurement session**, a different approach is needed:

- **Do not add permissions** if you can measure via public APIs, JFR, logging, or bytecode hooks that do not require deep reflection.
- Place the tool in an **isolated JVM/process** and terminate the process when the measurement session finishes. A fresh JVM starts from an unexpanded module graph, provided the corresponding flags/agent are not reapplied.
- In a module layer/loader architecture designed for teardown, you can create **new module identities** and stop using the old graph, while cleaning up references properly. This is **recreating the environment**, not a revocation operation of `redefineModule` on the old module.
- Revoke permissions at the **system layer or application policy layer** where a real revoke API exists, if that is the requirement; do not confuse it with the ability to reduce JPMS reads/exports/opens.

Never claim that you can call `redefineModule` again with `extraOpens=Map.of()` to "close permissions." That violates the official contract.

## 9. Security and the Principle of Least Privilege

### 9.1. The Wider You Open, the Larger the Attack Surface

Between two choices:

~~~java
Map.of("vault.internal", Set.of(specificConsumerModule))
~~~

and a broad configuration open to many modules, **restricting to a specific target module** reduces the scope of granted permissions. `extraOpens` accepts **`Set<Module>`**; it allows the agent to control exactly which target module receives the permission.

A few principles:

1. Only open **packages that are genuinely needed**. If a public API can be used, avoid `opens` on private packages.
2. Only grant to the **module that actually runs the reflection code**; do not mistakenly grant to another module and still hit errors.
3. Do not add every module to `extraReads`; only add edges that the new bytecode actually needs.
4. Do not export/open JVM or third-party module packages without appropriate approval/operational procedures.
5. Log in a controlled manner: source module name, package, target module, timestamp, reason, request ID, and authorized initiating actor.
6. Understand clearly that **granted permissions do not withdraw themselves**; assess risk over the **lifetime of the JVM**, not just the window when the agent is collecting data.
7. Test module access on the actual JVM/vendor/module layer; do not extrapolate results from a classpath-only demo to all deployments.

### 9.2. Opens Does Not Mean Bypassing All Security Layers

Opening a package under JPMS can make reflection into non-public members valid, but it does not automatically disable all other controls: Java type access rules, module resolution, native/security restrictions, and environment policies can still apply. `redefineModule` should not be treated as "system-wide root."

However, **relaxing encapsulation is a sensitive action**. An agent trusted to operate inside a JVM has significant power; do not allow loading agents from untrusted sources and do not accept arbitrary package/module names from unauthenticated users.

### 9.3. Named vs Unnamed Targets and CLI Flags

The example uses a **specific unnamed module** of `Main` as the target. This differs from broadly opening a package to all unnamed modules via launcher options:

~~~text
--add-opens demo.vault/vault.internal=ALL-UNNAMED
~~~

This line is **only for comparing CLI syntax**; it must not be used in the lab run command because it would invalidate the initial `opens-internal=false` state. `ALL-UNNAMED` has a broader scope than a specific `Module` object designated via `Set.of(client)`.

Many packages reside in modules layered by different class loaders; you must check the exact `Module` object and identity at runtime. Two modules with the same name in different module layers are not by default the same `Module` object.

## 10. Characteristics Related to ServiceLoader and Providers

### 10.1. extraUses Is Not extraProvides

- `extraUses` adds a declaration that **this module uses a service type**; it **does not create a new provider**.
- `extraProvides` adds a mapping of **which provider this module uses to provide a service**; the provider class must be a member of the source module and implement/extend the service type.
- `redefineModule` **does not exhaustively check that the service type is accessible at every instrumentation site**; the responsibility for ensuring accessibility lies with the agent.
- `ServiceLoader` has caching/discovery rules; a loader created before a provider is added may not reflect the new provider unless a new loader is created or reloaded appropriately.

### 10.2. A Provider Is Not Immediately Instantiated

`Map.of(ServiceType.class, List.of(Provider.class))` adds the **provides relationship** for the module; it does not mean that a provider instance is always instantiated immediately at the `redefineModule` call. A new `ServiceLoader` performs discovery/instantiation according to its rules at the time of use.

### 10.3. Do Not Use Empty Sets to Remove Providers

In Demo 2, after `extraProvides` sets the provider count to 1, a subsequent update with `Map.of()` for `extraProvides` still causes a **fresh ServiceLoader** to see 1 provider. If removing a provider from an operational environment is required, a different lifecycle/deployment strategy is needed rather than expecting an empty map call to delete an added relationship.

## 11. Error Handling and Input Validation

| Scenario | Possible outcome / exception | How to handle |
|---|---|---|
| `isModifiableModule(namedModule) == false` | `UnmodifiableModuleException` if modification is attempted | Check capability first, do not try to force the VM |
| Passing `null` for module or any collection parameter | `NullPointerException` | Use `Set.of()` / `Map.of()` when not adding anything |
| Collection contains null key/value/element | `NullPointerException` per Javadoc | Validate and never pass null |
| Package key is not in the source module | `IllegalArgumentException` | Use `source.getPackages()` to verify package names |
| `extraExports`/`extraOpens` maps a package to an empty Set | `IllegalArgumentException` | If not adding an export/open, **omit the key from the map**, do not map the key to `Set.of()` |
| `extraProvides` maps a service to an empty List | `IllegalArgumentException` | Omit the key when there are no new providers |
| Provider class does not belong to the source module | `IllegalArgumentException` | Choose a provider residing in the module being updated |
| Provider class does not implement the service | `IllegalArgumentException` | Check the service/provider hierarchy beforehand |
| `extraUses` service is not accessible at the use site | Possible access/linkage error or `ServiceConfigurationError` when using the service | Add read/exports if needed, test at the call site |
| Calling `redefineModule` with an unnamed module | **No-op**, not an error per contract | Do not rely on this call to change an unnamed module's graph |
| Calling again with all empty collections | Keeps added relationships intact, does not revoke | Do not confuse an empty update with a rollback |
| Reflection is still blocked after opens | Wrong source/target module, package, timing, or other requirement | Check `isOpen`, loader/module identity, member kind, and original exception |

### 11.1. Checking the Package Key Before Calling

~~~java
if (!source.getPackages().contains("vault.internal")) {
    throw new IllegalArgumentException(
            "Package absent from source module");
}
~~~

This **snippet** requires a defined `source` variable of type `Module`. The Java API requires Java-style **dot-separated** package names; the JVM internal name `vault/internal` is not a valid key.

### 11.2. Runtime Relationships May Already Be Open

Before adding, you can check:

~~~java
boolean alreadyOpen =
        source.isOpen("vault.internal", client);
~~~

If it is already true, there is not necessarily a need to call `redefineModule` again. However, **do not expect it to become false after removing a transformer**: transformer changes do not control already-opened module relationships.

### 11.3. isModifiableModule Is Not a Global Permission Check

`isModifiableModule` only answers **whether the module can be modified by redefineModule**. It does not replace an enterprise authorization policy on **who is allowed to request an agent to open which package**, nor is it proof that permissions were later revoked. Production agents need an independent control plane with appropriate operation permissions and an audit trail of granted changes.

## 12. Concurrency, Multiple Agents, and Cumulative State

The Javadoc notes that `redefineModule` is **safe to call concurrently**, allowing multiple agents to add relationships to the same module nearly simultaneously. This does not turn the API into a transaction with "restore snapshot" capability:

~~~text
Agent A: opens package.p -> Module X
Agent B: opens package.p -> Module Y
Agent A: redefineModule(package.p -> empty)
Result: open permissions added to X/Y are not removed by the last call
~~~

**The risk of "lost updates" from overwriting the whole graph** is not the right model for this API because it is **additive**. However, multiple agents can produce a **broader set of permissions than intended**, because each agent only sees its own requests. Operators need to inventory the **total added permissions**, not just the current agent's configuration.

### 12.1. Limited Idempotency

Repeatedly adding the same existing read/export/open relation usually does not turn it into a different new permission. However, do not treat the entire agent pipeline as idempotent just because the JPMS relation already exists: the agent may also register transformers, providers, threads, MBeans, or telemetry exporters. Manage the lifecycle of those resources separately.

### 12.2. Module Descriptor Is Not a Complete Log

An application may have an almost unchanged `module-info.java` configuration, while the runtime graph has been opened by agents or launcher flags. Therefore, when investigating encapsulation/reflective access errors, record **module identity + runtime `isOpen/isExported/canRead/canUse` state**, rather than only printing the module descriptor.

## 13. Application Scenarios in Instrumentation

### 13.1. Agent Injecting Helper Calls into a Named Module

Suppose you instrument a class belonging to the named module `business.core` and inject a call to a helper in the `telemetry.agent` module. If the target class's module does not yet read the helper module, linking the callback/helper may fail even if the classfile bytecode is valid.

The agent may need:

~~~java
inst.redefineModule(
        businessModule,
        Set.of(telemetryModule),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

This is an **illustrative snippet**, assuming the `Module` variables are already available. Before doing this, check whether the JVM has already added the appropriate read edge for the agent helper according to instrumentation rules; do not grant excessive permissions when unnecessary.

**Important:** adding reads does not automatically export the helper API. The helper module side may need to export the package containing the helper to the business module, or use a helper layout appropriate for the class loader/agent mechanism.

### 13.2. Agent Wanting to Read Private Fields of a Framework

If diagnostic logic needs deep reflection into an internal package of `framework.core`, the source of `extraOpens` must be the **module containing the package**; the target is the module of the **code performing the reflection**.

~~~java
inst.redefineModule(
        frameworkModule,
        Set.of(),
        Map.of(),
        Map.of("framework.internal", Set.of(agentModule)),
        Set.of(),
        Map.of());
~~~

This is also a **snippet**. Do not confuse the direction by opening a package in `agentModule` and expecting the framework's package to be opened. If deep reflection is not truly necessary, prefer a lower-privilege API.

### 13.3. An Agent Is Not a Permission-Revocation Tool When Stopping Measurement

After completing diagnostics, the agent can stop background tasks, remove transformers, or stop exporting data. **Opened JPMS permissions remain**. The shutdown plan must explicitly state: "stopping instrumentation activity" is **different** from "revoking granted `opens`." If an audit requires real revocation, a restart/isolation path and verification that no old module identity remains in use are needed.

## 14. Exercises and Answers

### Exercise A — Predicting After an Empty Update

Demo 1 called `expand`, making `vault.isOpen("vault.internal", client)` true. Then `emptyUpdate` was called with `extraOpens=Map.of()`. Predict `isOpen` and test `ctor.setAccessible(true)`.

**Answer:** `isOpen` remains true; reflection continues to be allowed by the opened relationship, assuming no other controls changed.

### Exercise B — Distinguishing exports and opens

Modify Demo 1 to have **only** `extraExports` for package `vault.internal`, without `extraOpens`. Predict that public members can be accessed normally under appropriate conditions, while `setAccessible(true)` for private `token` **is not opened by a qualified export alone**. Explain why this permission differs from `opens`.

### Exercise C — Wrong Direction

An agent wants to read a private field in `framework.core.internal` but calls `redefineModule(agentModule, ..., extraOpens...)`. What is wrong? The **source module** must be the module **owning the package**, while the target is the module performing reflection.

### Exercise D — Provider Not Lost After Empty Update

Run Demo 2, add the provider with `extraProvides`, then call the empty update. Predict `ServiceLoader.load(Greeting.class).stream().count()` when creating a new loader: **1**, not reverting to 0.

### Exercise E — Validation of extraOpens

Try passing `Map.of("vault.internal", Set.of())`. Per the API contract, you may get `IllegalArgumentException` because **the map contains a key with an empty Set**. If you do not want to add permissions for that package, you should **omit the key entry**, not create an empty key.

### Exercise F — Checking the Unnamed Module

In the demo, obtain `Module app = Main.class.getModule()`. `app.isNamed()` is expected to be false. Why can `inst.isModifiableModule(app)` still return true, yet calling `redefineModule(app, ...)` does not expand it like a named module? Because the specification defines **unnamed module updates as a no-op**.

### Exercise G — Operational Policy

A team proposes opening a private package for 10 minutes and then "turning off permissions" with `extraOpens=Map.of()`. Identify at least two design flaws and propose a solution. **Guided answer:** the API does not revoke; a target module with open permission retains it, so you need to reduce initial privileges or use process isolation/restart if a recovery boundary is required.

### Self-Check Questions

1. **Does `redefineModule` allow removing an added read edge?** — No.
2. **Is `extraExports` for exporting public APIs or deep reflection?** — Primarily for exporting packages; deep reflection on non-public members requires appropriate opens.
3. **Do `extraOpens` keys use `vault/internal` or `vault.internal`?** — `vault.internal`.
4. **When mapping a package to an empty Set, is that a remove?** — No; it is also invalid input for export/open.
5. **Does `extraUses` automatically create a provider?** — No.
6. **Is `extraProvides` a complete replacement list?** — No, it is additive only.
7. **Does `redefineModule` on an unnamed module have an expanding effect?** — No, it is a no-op.
8. **What does `isModifiableModule(unnamed)` return?** — Per Javadoc, true.
9. **Does `removeTransformer` close added `opens`?** — No.
10. **How do you verify the actual state after an update?** — `canRead`, `isExported`, `isOpen`, `canUse`, actual access/`ServiceLoader`.

## 15. Safe Deployment Checklist

### Before Granting Permissions

- [ ] Identify the exact named source module, package, and target module object.
- [ ] Verify that the package key belongs to `source.getPackages()`.
- [ ] Confirm whether reads, exports, opens, uses, or provides are needed; do not use broad permissions when narrow ones suffice.
- [ ] Check `inst.isModifiableModule(source)`.
- [ ] Clearly understand that **added permissions cannot be revoked by `redefineModule`**.
- [ ] Have approval and auditing for qualified exports/opens to sensitive packages.
- [ ] Avoid automatically accepting package/target modules from untrusted input.

### During the Update

- [ ] Use non-null collections; `Set.of()`/`Map.of()` for unchanged types.
- [ ] Do not include a package key with an empty Set in `extraExports`/`extraOpens`.
- [ ] For `extraProvides`, ensure the provider actually belongs to the source module, implements the service, and the list is non-empty.
- [ ] Log the added relationships, actor, and timestamp.
- [ ] When multiple agents call concurrently, inventory the **cumulative** result; do not treat later calls as replacements.
- [ ] Check error conditions and handle exceptions in a controlled manner.

### After the Update

- [ ] Read runtime state `canRead`, `isExported`, `isOpen`, `canUse`.
- [ ] Test the exact required behavior: helper linkage, reflection, `ServiceLoader`.
- [ ] Explicitly note that stopping the agent/transformer **is not equivalent** to revoking JPMS relations.
- [ ] If a new privilege boundary is needed, verify the restart/isolation plan.
- [ ] Avoid printing demo secrets into production logs; `demo-secret` is strictly for experimentation.
- [ ] Test on the actual JDK/vendor/class loader/module layers.
- [ ] Do not claim permissions were revoked if you only called `redefineModule` again with empty collections.

## 16. Summary and References

**Principle to remember:** in Java Instrumentation, `redefineModule` is an **additive-only module relationship API**, not an API that replaces the graph with a new configuration. It can add **reads**, **exports**, **opens**, **uses**, and **provides**. It **cannot reduce** existing relationships; empty parameters in a subsequent call do not cancel added permissions.

Demo 1 proves the module graph expands from false to true and stays true after an empty update; Demo 2 proves a new provider appearing via `ServiceLoader` still exists after an empty update. When designing an agent with access to internal packages, adhere to **least privilege**, restrict to specific source/target modules, and define a different lifecycle strategy if the problem genuinely requires permission revocation.

**Official References (Java SE 17):**

- [Instrumentation.redefineModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map)): signature, additive-only property, unnamed no-op, validation, concurrency, `isModifiableModule`.
- [java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `canUse`, and distinguishing named/unnamed.
- [java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent startup mechanisms, access permissions to modules and class loaders.
- [UnmodifiableModuleException](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/UnmodifiableModuleException.html): module that cannot be modified by the Instrumentation API.
- [java.util.ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): service discovery and dynamically added providers.
- [JLS 17 `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`, `uses`, `provides`.
