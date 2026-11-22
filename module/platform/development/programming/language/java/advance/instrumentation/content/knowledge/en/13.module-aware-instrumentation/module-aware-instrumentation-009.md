# Open Only the Exact Package and Exact Module Needed for a Helper or Reflection

When instrumenting a Java application that uses the **Java Platform Module System (JPMS)**, a Java agent may need to allow a helper to call into an unexported package, or read a private field via reflection. The solution should not be to open the entire module or every package of the JDK: **open only the exact package that needs to be accessed to the exact module performing the operation**, and only add `reads` or `exports` edges when the business logic genuinely requires it.

Since Java 9, `java.lang.instrument.Instrumentation` provides `redefineModule` to **add** module read edges, package exports, and package opens at runtime. This API carries strong privileges: opening a package to a module allows **any code in the receiving module** to perform deep reflection into the classes of that package, not just the specific helper you have in mind. Therefore, you must treat **the unit of access grant as module + package**, not a specific method or field.

This lesson focuses on least-privilege design for a Java agent and helper: distinguishing `reads`, `exports`, and `opens`; understanding the two directions of relationships between source and target modules; using `Instrumentation.redefineModule` with exact arguments; checking permissions before and after; avoiding `ALL-UNNAMED` when you can grant access to a single module; and running a Java 17+ demo to see the needed package opened while another package remains encapsulated.

## 1. Model: Who Needs Access to What?

Suppose the application has a named module `com.shop.core` and inside the module there are:

```text
com.shop.core
  ├─ com.shop.api
  │    └─ OrderFacade               (public API)
  ├─ com.shop.internal
  │    └─ PricingState              (private state)
  └─ com.shop.auth
       └─ TokenVault                (sensitive data)
```

An agent has `ProbeHelper` that wants to inspect `PricingState` for error diagnostics. If the helper performs `Field.trySetAccessible()` or `MethodHandles.privateLookupIn(...)`, the issue is usually that package `com.shop.internal` is **not open to the module containing the helper**.

**The principled grant path:**

```text
module com.shop.core
  package com.shop.internal
          |
          | opens ... to
          v
module containing ProbeHelper

module com.shop.core
  package com.shop.auth
          |
          | DOES NOT open to helper
          X
```

There is no need to automatically open `com.shop.auth` just because it is in the same module. Nor is there any need to open all of `java.base`, pass `--add-opens=...=ALL-UNNAMED`, or export `com.shop.internal` to everyone just because one measurement requires reflection.

A few points you must know right away:

- **Open** is a privilege granted by the **module that owns the package**, directed toward the **receiving module**.
- A module can contain multiple packages; configuration should open only a single package if needed.
- The receiving module can be a **named** or **unnamed module**. A typical startup Java agent JAR is loaded by the system class loader into that loader's **unnamed module**.
- Unnamed modules from **different class loaders** are not automatically the same `Module` object.
- **Opening a package does not automatically load the helper**. JPMS permissions and class-loader visibility are two separate concerns.

## 2. Three Relationships to Keep Strictly Separate: reads, exports, opens

This is the most important table before calling `redefineModule`.

| Mechanism | Direction | What it allows | What it does not automatically guarantee |
|---|---|---|---|
| `reads` | Module **A reads B** | A has a readability relationship with B | B does not thereby export or open its packages |
| `exports p to A` | Module **B owning p** exports p to A | A can access **public types and appropriate public/protected APIs** under Java rules when other conditions hold | Does not automatically allow deep reflection into private members |
| `opens p to A` | Module **B owning p** opens p to A | Code in A can perform **deep reflection** on types in p via the appropriate APIs | Does not automatically swap class loaders, grant access to other packages, or bypass remaining checks |
| `exports p` without `to` | B exports p unconditionally | Many other modules can use the public API | Broader scope than a qualified export |
| `opens p` without `to` | B opens p unconditionally | Many other modules can deep-reflect into the package | Broader scope than a qualified open |

A detail of `Module.isExported(p, other)`: a package that is **open** to `other` is also considered **exported to other at runtime** according to the specification. However, this does **not** make `exports` and `opens` the same concept. Deep reflection is a broader capability than accessing a public API.

### 2.1. Examples of Grant Direction

Suppose:

```text
M = module com.shop.core          (contains com.shop.internal.PricingState)
H = module io.acme.agent.helper   (contains ReflectiveProbe)
```

**Helper H wants to read a private field of a class in M:**

- M needs to **open** `com.shop.internal` **to H**.
- If using `MethodHandles.privateLookupIn` from H to M, H must also **read M** and the caller lookup must have appropriate `MODULE`/`PRIVATE` access.
- A `trySetAccessible` call for deep reflection is also subject to the target package's openness to the caller module; do not confuse it with the requirements of `privateLookupIn`.

**Code in M wants to call a helper in H via injected bytecode:**

- M needs to be able to **read H** when required to link the reference.
- If H is a named module, the package containing the public helper API needs to be **exported to M** when accessing those public types/members.
- If the helper resides in a suitable unnamed module, `java.lang.instrument` has a special rule for transformed classes (see section 8); do not assume every named helper receives the same support.
- Even when readability/exports are correct, the target class loader must still be able to **resolve the helper class**; otherwise `NoClassDefFoundError` may occur.

**Mind the direction:** If helper H needs to see private fields in M, calling `redefineModule(H, ...)` to open a package of H is the **wrong direction**. The target of `extraOpens` must be the module **that owns the package to be opened**, namely M.

### 2.2. Distinguishing "Not Exported" from "Not Open"

A named module:

```java
module com.shop.core {
    exports com.shop.api;
}
```

From another module, code can use the public API in `com.shop.api` if it can read `com.shop.core`. However, that does not allow accessing private members of `com.shop.api.OrderFacade` via `setAccessible(true)`. For `com.shop.internal`, which is neither exported nor open, the access rules are even stricter.

If you only need to call a public API, prefer the **public API** or a qualified export when approved. If you genuinely need private reflection, use a **qualified open** for the minimal package. Do not open a package just to fix a `ClassNotFoundException` caused by the class loader not seeing the JAR.

## 3. The Right API: Instrumentation.redefineModule

Since Java 9, the API signature is:

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

Understand that **the first module is the module being expanded**, not "the agent's module." Meaning of each parameter:

| Parameter | Meaning | When only deep reflection is needed |
|---|---|---|
| `module` | The module to add reads/exports/opens/uses/provides to | **The module owning the class/package to be read** |
| `extraReads` | Additional modules that `module` will read | `Set.of()` if reads do not need to change |
| `extraExports` | Package name → set of modules to additionally export to | `Map.of()` if no separate public export is needed |
| `extraOpens` | Package name → set of modules to additionally open to | **Only the single package and helper module needed** |
| `extraUses` | Additional service types that the module uses | `Set.of()` if ServiceLoader dependencies do not change |
| `extraProvides` | Service type → additional implementation classes provided | `Map.of()` if no providers are added |

Opening a single package `com.shop.internal` of the target module to the exact helper module:

```java
Module target = PricingState.class.getModule();
Module helper = ReflectiveProbe.class.getModule();

if (!target.isModifiableModule()) {
    // Wrong API: Module does not have an isModifiableModule() method.
}
```

**The snippet above is intentionally only an API error comparison example, not code to use in an application.** Checking modifiability is **not** a method on `Module`; use the `Instrumentation` instance:

```java
// Snippet inside the agent; inst, target, and helper are already defined.
if (!inst.isModifiableModule(target)) {
    reportSkipped("MODULE_UNMODIFIABLE");
} else {
    inst.redefineModule(
        target,
        Set.of(),
        Map.of(),
        Map.of("com.shop.internal", Set.of(helper)),
        Set.of(),
        Map.of()
    );
}
```

`reportSkipped` is an undefined illustrative helper function, not standalone runnable source. The complete example is in section 5.

### 3.1. Package Names Must Be Dotted Names

`extraOpens` takes a **full Java dotted package name**:

```text
CORRECT: com.shop.internal
WRONG:   com/shop/internal
WRONG:   com.shop.internal.PricingState
WRONG:   com.shop.* 
```

The unit of access grant is a **package**, not a class name, and there are no wildcards in map keys. If you want to open multiple packages, you must list **each package explicitly**, not use a module name or prefix to request opening all of them.

### 3.2. Map Values Must Be a **Non-Empty** Set of Modules

`Map.of("com.shop.internal", Set.of(helper))` is valid. `Map.of("com.shop.internal", Set.of())` is invalid for `extraOpens` and can cause `IllegalArgumentException`. Passing a package that does not belong to the target module in `extraOpens`/`extraExports` also causes `IllegalArgumentException`.

Before mutating, you can check:

```java
if (!target.getPackages().contains("com.shop.internal")) {
    throw new IllegalArgumentException("Not a package of target module");
}
```

This is an illustrative snippet with `target` already declared. Do not rely on sharing a `com.shop` prefix to assume a package definitely belongs to that named module.

### 3.3. If No Other Privileges Are Needed, Pass Empty Sets/Maps

Do not add `extraReads`, `extraExports`, `extraUses`, or `extraProvides` just because the method has six parameters. A call tailored to the actual need can use:

```java
inst.redefineModule(
    target,
    Set.of(),                                  // no extra reads
    Map.of(),                                  // no extra exports
    Map.of("com.shop.internal", Set.of(helper)), // open only this package
    Set.of(),                                  // no extra uses
    Map.of()                                   // no extra provides
);
```

Because `extraOpens` is already sufficient for `Field.trySetAccessible` in this scenario, there is **no need** to simultaneously export all packages or add reads by intuition.

### 3.4. Additive Only, No Revocation

`redefineModule` **cannot shrink** the set of read modules, exported/opened packages, or service dependencies. This is not an API to "open temporarily and then close."

```text
T0: module M does not open p to H
T1: agent calls redefineModule(M, extraOpens={p -> {H}})
T2: M now opens p to H
T3: agent wants to close it again -> NO revocation operation via redefineModule
```

If a module was already opened broadly beforehand via manifest/CLI/app code, another narrow open call **does not shrink** the prior scope. Returning to the initial permission configuration may require **starting a new JVM** with the right configuration. Therefore, reviewing permissions before calling the API is more important than assuming a rollback exists.

### 3.5. isModifiableModule Differs from isModifiableClass

- `inst.isModifiableModule(module)` checks whether a module can be modified via `redefineModule`.
- `inst.isModifiableClass(clazz)` checks whether a class can be redefined/retransformed.

These are **two independent concerns**. Do not infer from `isModifiableClass(clazz)==true` that `redefineModule(clazz.getModule(),...)` will be valid.

In particular, `isModifiableModule(unnamedModule)` always returns `true` per the Java API contract, **but redefining an unnamed module is a no-op**. Do not take `true` in that case and report "new package opened."

## 4. Checking Permissions Before and After Opening

Methods on `java.lang.Module` help with diagnostics:

```java
Module source = TargetClass.class.getModule();
Module consumer = HelperClass.class.getModule();

boolean reads = consumer.canRead(source);
boolean exported = source.isExported("com.shop.internal", consumer);
boolean opened = source.isOpen("com.shop.internal", consumer);
```

This is an **illustrative snippet**: `TargetClass`/`HelperClass` are real classes in your system. The booleans may vary depending on the module/configuration.

**Exact meaning:**

- `consumer.canRead(source)` asks whether the consumer module reads the module containing the target.
- `source.isExported(packageName, consumer)` asks whether the target package is exported **at least** to the consumer. A package opened to the consumer is also considered exported at runtime per the Javadoc.
- `source.isOpen(packageName, consumer)` asks whether the target package is open **at least** to the consumer. This value is the critical condition for deep reflection.
- `source.isOpen(packageName)` **with no module argument** asks about unconditional openness, not a qualified open.
- `getModule().isNamed()` helps distinguish named/unnamed; `getName()==null` for an unnamed module is normal.

**Do not misuse:**

```java
source.isOpen("com.shop.internal")           // different from asking for 1 consumer
source.isOpen("com.shop.internal", consumer) // the right qualified open question
```

After a qualified open, `isOpen(packageName,consumer)` can be `true` while `isOpen(packageName)` remains `false`. That is **correct least-privilege design**, not a bug.

### Verify Behavior, Not Just Flags

Even when `isOpen==true`:

- Make sure `consumer` is the **exact Module object of the code actually calling reflection**, not a similarly named helper class in a different loader.
- Reflecting on a specific field/method can still fail due to class not found, a different class loader, a special SecurityManager/policy, or an inappropriate API operation.
- `MethodHandles.privateLookupIn` additionally requires readability and caller lookup privileges.
- Module permissions do not automatically make a class in a custom loader visible on the system classpath.

Verify the **exact access operation needed** after opening, for example that `Field.trySetAccessible()` returns `true` for the approved field.

## 5. Complete Java 17+ Experiment: Open Only One Package to One Agent

We will create a **named module** `demo.target` with **two unexported/unopened packages**:

- `demo.target.internal`: contains private field `marker` that the agent wants to read.
- `demo.target.other`: contains private field `hidden` that the agent **must not open**.

The agent is a startup `-javaagent` loaded into the **unnamed module of the system class loader**. In `premain`, the agent locates the target module, checks reflection before opening, calls `Instrumentation.redefineModule` to open only `demo.target.internal` to **the agent's own Module object**, re-checks the field, and confirms the other package remains encapsulated.

### 5.1. Create the Exact Directory Structure

```text
module-open-lab/
  src/
    demo.target/
      module-info.java
      demo/target/Main.java
      demo/target/internal/SecretBox.java
      demo/target/other/OtherSecret.java
  agent-src/
    demo/agent/OpenAgent.java
  agent.mf
```

This consists of **four Java files for the target module and one Java file for the agent**. No bytecode transformer, ASM/Byte Buddy library, or retransform privilege is needed: the goal of the example is **granting JPMS access via Instrumentation**.

### 5.2. `src/demo.target/module-info.java`

```java
module demo.target {
    // Intentionally neither exports nor opens the two packages below.
}
```

There is no `opens demo.target.internal;`, nor `exports demo.target.internal;`. This is a normal encapsulated module. Not exporting the package containing `Main` does not prevent the launcher from starting main via `-m demo.target/demo.target.Main` in the standard scenario.

### 5.3. `src/demo.target/demo/target/Main.java`

```java
package demo.target;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP_STARTED");
    }
}
```

The main program only prints one line. It does not directly call the agent and does not need to modify `module-info.java` to add `requires` to the agent's code.

### 5.4. `src/demo.target/demo/target/internal/SecretBox.java`

```java
package demo.target.internal;

public final class SecretBox {
    private static int marker = 7;
}
```

Private field `marker` is used as **non-sensitive demo data**. In a real product, the fact that an agent can access a private field does not mean it is allowed to log credentials, tokens, or personal data.

### 5.5. `src/demo.target/demo/target/other/OtherSecret.java`

```java
package demo.target.other;

public final class OtherSecret {
    private static int hidden = 9;
}
```

This is the control package. The agent attempts `trySetAccessible` on the private field here after opening package `demo.target.internal`; it must **still fail**. This negative test proves that privileges were not expanded beyond the required scope.

### 5.6. `agent-src/demo/agent/OpenAgent.java`

```java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.lang.reflect.Field;
import java.util.Map;
import java.util.Set;

public final class OpenAgent {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        Module target = ModuleLayer.boot()
                .findModule("demo.target")
                .orElseThrow();

        Module helper = OpenAgent.class.getModule();
        String packageName = "demo.target.internal";

        Class<?> secret = Class.forName(
                target, "demo.target.internal.SecretBox");
        if (secret == null) {
            throw new ClassNotFoundException(
                    "demo.target.internal.SecretBox");
        }

        Field marker = secret.getDeclaredField("marker");

        System.out.println("TARGET_NAMED=" + target.isNamed());
        System.out.println("HELPER_NAMED=" + helper.isNamed());
        System.out.println(
                "BEFORE_OPEN=" + target.isOpen(packageName, helper));
        System.out.println(
                "BEFORE_ACCESS=" + marker.trySetAccessible());

        if (!inst.isModifiableModule(target)) {
            System.out.println("SKIPPED_UNMODIFIABLE_MODULE");
            return;
        }

        inst.redefineModule(
                target,
                Set.of(),
                Map.of(),
                Map.of(packageName, Set.of(helper)),
                Set.of(),
                Map.of()
        );

        System.out.println(
                "AFTER_OPEN=" + target.isOpen(packageName, helper));

        boolean enabled = marker.trySetAccessible();
        System.out.println("AFTER_ACCESS=" + enabled);
        if (enabled) {
            System.out.println("MARKER=" + marker.getInt(null));
        }

        String otherPackage = "demo.target.other";
        Class<?> other = Class.forName(
                target, "demo.target.other.OtherSecret");
        if (other == null) {
            throw new ClassNotFoundException(
                    "demo.target.other.OtherSecret");
        }
        Field hidden = other.getDeclaredField("hidden");

        System.out.println(
                "OTHER_OPEN=" + target.isOpen(otherPackage, helper));
        System.out.println(
                "OTHER_ACCESS=" + hidden.trySetAccessible());
    }
}
```

**Explanation of key points:**

1. `ModuleLayer.boot().findModule("demo.target")` retrieves the exact module **resolved in the boot layer** of the run using `-m demo.target/...`. Do not use a module name from config without verifying the target is present.
2. `OpenAgent.class.getModule()` retrieves the **exact Module object of the caller** invoking reflection; for a normal agent JAR it is the system unnamed module (hence `HELPER_NAMED=false`).
3. `Class.forName(Module,String)` is used to look up a class in a **specific module**, without requiring the package to be exported to obtain the `Class<?>` object; this method may return `null` if the class does not exist in the module.
4. `getDeclaredField("marker")` can retrieve metadata for a private field but **does not automatically grant permission to access its value**.
5. Before `redefineModule`, `marker.trySetAccessible()` returns `false` when the package is not open to the agent's module.
6. `Map.of(packageName,Set.of(helper))` opens only **one package** to **one Module object**; it does not export/open the remaining packages.
7. After the successful call, both `target.isOpen(packageName,helper)` and `marker.trySetAccessible()` are `true`.
8. `marker.getInt(null)` reads the value of the static field; in the demo it is `7`, **not a guide for reading secrets in production**.
9. `demo.target.other` remains unopened to the helper, so `hidden.trySetAccessible()` still returns `false`.

No step uses `--add-opens` or `ALL-UNNAMED` in the demo runtime. That is the intentional difference between **narrow access via the Instrumentation API** and CLI flags that typically grant access to every unnamed module.

### 5.7. Manifest File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.OpenAgent

```

Keep a trailing blank line at the end of the manifest. `Can-Retransform-Classes: true` or `Can-Redefine-Classes: true` is not needed because the agent does **not** retransform/redefine class bytes. `Instrumentation.redefineModule` is an independent API.

### 5.8. Compile and Run on JDK 17+

From the `module-open-lab` directory, Bash/macOS/Linux:

```shell
mkdir -p mods/demo.target agent-classes

javac -d mods/demo.target \
  src/demo.target/module-info.java \
  src/demo.target/demo/target/Main.java \
  src/demo.target/demo/target/internal/SecretBox.java \
  src/demo.target/demo/target/other/OtherSecret.java

javac -d agent-classes agent-src/demo/agent/OpenAgent.java

jar cfm narrow-agent.jar agent.mf -C agent-classes .

java -javaagent:narrow-agent.jar \
  --module-path mods \
  -m demo.target/demo.target.Main
```

For Windows PowerShell (do not use `\` as a line continuation character):

```powershell
New-Item -ItemType Directory -Force mods/demo.target, agent-classes | Out-Null
javac -d mods/demo.target src/demo.target/module-info.java src/demo.target/demo/target/Main.java src/demo.target/demo/target/internal/SecretBox.java src/demo.target/demo/target/other/OtherSecret.java
javac -d agent-classes agent-src/demo/agent/OpenAgent.java
jar cfm narrow-agent.jar agent.mf -C agent-classes .
java -javaagent:narrow-agent.jar --module-path mods -m demo.target/demo.target.Main
```

**Preconditions:** The example is designed for JDK 17+ with standard JPMS and Instrumentation APIs. A JDK with `javac`, `jar`, and `java` in `PATH` is required; no other Java agent or other `--add-opens` should be altering the permissions of the two packages. If the package is already opened by flags or other code, the `BEFORE_*` output will differ from expected.

### 5.9. Expected Stdout on a Typical HotSpot JDK 17/21

```text
TARGET_NAMED=true
HELPER_NAMED=false
BEFORE_OPEN=false
BEFORE_ACCESS=false
AFTER_OPEN=true
AFTER_ACCESS=true
MARKER=7
OTHER_OPEN=false
OTHER_ACCESS=false
APP_STARTED
```

**How to read the output:**

- `TARGET_NAMED=true`: `demo.target` is resolved as a named module.
- `HELPER_NAMED=false`: agent class is in the unnamed module of the system class loader.
- `BEFORE_OPEN=false` and `BEFORE_ACCESS=false`: before granting access, private reflection into the encapsulated package is blocked.
- `AFTER_OPEN=true` and `AFTER_ACCESS=true`: the API added only the requested qualified open.
- `MARKER=7`: reading the approved field in the demo takes effect.
- `OTHER_OPEN=false` and `OTHER_ACCESS=false`: the unselected package **remains encapsulated**.
- `APP_STARTED`: the main application continues running after `premain`.

If `isModifiableModule(target)` returns false, the demo prints `SKIPPED_UNMODIFIABLE_MODULE` and none of the post-open lines appear; report this as an unsupported environment branch. If `redefineModule` throws an exception, the application main may not run because the startup agent `premain` failed; never assume the open succeeded.

**Scope lesson:** The agent can read private `marker` because the package was opened to the **exact agent module**. However, package `demo.target.other` was not opened; there is no evidence the agent can freely read every private field in the module.

### 5.10. Control Check: Broad Flags Change the Output

If you launch the JVM with:

```shell
java --add-opens=demo.target/demo.target.internal=ALL-UNNAMED \
  -javaagent:narrow-agent.jar \
  --module-path mods \
  -m demo.target/demo.target.Main
```

then **`BEFORE_OPEN` may already be `true`**, because you granted access to **all unnamed modules** at startup time. Therefore, do not use this flag in the main control run. The flagged run only illustrates that the CLI option grants **broader** access than `Set.of(helper)` inside the agent.

Do not use `--add-opens=...=ALL-UNNAMED` as a "test to see if the helper runs" and leave it behind in production configuration; it can grant the same access to other unnamed modules (in different class loaders).

## 6. MethodHandles.privateLookupIn: Requires reads + opens

Some instrumentation libraries use `MethodHandles.Lookup` instead of the reflection API. When creating a private lookup from another module, `MethodHandles.privateLookupIn(targetClass, callerLookup)` has these conditions:

1. Caller lookup must have the appropriate lookup modes, including `MODULE` and `PRIVATE`.
2. If the caller module is **different** from the target class's module, the caller module must **read** the target module.
3. The target module must **open the target class's package** to the caller lookup's module.

For an agent JAR in an **unnamed module**, unnamed modules read every module under JPMS semantics, so in the demo above usually only the **qualified open** is missing. However, if the helper is packaged as a **separate named module** in a custom layer, you must actually check `helperModule.canRead(targetModule)`; do not take the unnamed example and assume all named modules automatically read one another.

Example check before calling private lookup (snippet contains hypothetical variables/classes, **not standalone**):

```java
Module targetModule = secretClass.getModule();
Module helperModule = TrustedHelper.class.getModule();
String pkg = secretClass.getPackageName();

if (!helperModule.canRead(targetModule)) {
    // Need to resolve the read edge from helper -> target;
    // possible via module-info.java or a redefineModule(helper) call.
}

if (!targetModule.isOpen(pkg, helperModule)) {
    // Need a qualified open from target -> helper.
}

java.lang.invoke.MethodHandles.Lookup lookup =
    java.lang.invoke.MethodHandles.privateLookupIn(
        secretClass, java.lang.invoke.MethodHandles.lookup());
```

Note: `MethodHandles.lookup()` in the snippet must actually be the lookup of the authorized code/module; copying it into a wrapper method in another module can produce a caller lookup with a different identity/privileges than expected. Do not use `lookup.in(...)` or pass a lookup across multiple modules and assume it retains `MODULE` access.

### 6.1. A Missing Read Edge Is Not Fixed by extraOpens in the Reverse Direction

If `H` is a named helper module and `M` contains the class needing private lookup:

```text
Two distinct relationships are needed:

H --reads--> M
M --opens package p to--> H
```

**Two API calls, when needed:**

```java
// 1. Only if H does not yet read M:
inst.redefineModule(
    helperModule,
    Set.of(targetModule),
    Map.of(), Map.of(),
    Set.of(), Map.of()
);

// 2. Only if package p of M is not yet open to H:
inst.redefineModule(
    targetModule,
    Set.of(), Map.of(),
    Map.of("com.shop.internal", Set.of(helperModule)),
    Set.of(), Map.of()
);
```

This is an **illustrative snippet**, not a standalone program; `inst`, `helperModule`, and `targetModule` must be valid runtime objects. If the helper module is unmodifiable or lacks policy approval, do not automatically expand privileges and expect it to be safe.

## 7. When to Use exports Instead of opens?

**Decision question:** Do you genuinely need private reflection?

| Need | Appropriate choice | What not to do |
|---|---|---|
| Helper calls a public method of a public type designed as an API | Appropriate `requires` + `exports` (qualified if only one consumer) | Open the entire package just to call a public API |
| Helper uses `Field.trySetAccessible` on a private field | Qualified `opens` of target package to caller | Only `exports` and hope private access is allowed |
| Helper uses `privateLookupIn` from another module | Caller reads target + target opens package to caller | Skip the read edge or open all packages |
| Application bytecode calls a public static helper in a named module | Source module reads helper module; helper package exports to source | Confuse the direction into source exporting its own package |
| Application bytecode calls a bootstrap/system unnamed helper | Check instrumentation rules, loader visibility, actual module reads | Blindly add all unnecessary `extraReads` |
| Access a private field just to compute a non-essential metric | Redesign via public API/adapter or SKIP with a report | Open sensitive privileges just to get extra data |
| Class is in an unnamed module | Consider normal loader/access rules; `redefineModule(unnamed)` is a no-op | Assume module mutation will create a new boundary |

### 7.1. A Qualified Export Example

Module `com.shop.core` has a public type in package `com.shop.spi`, and helper `io.acme.agent.helper` needs to call the public API:

```java
inst.redefineModule(
    targetModule,
    Set.of(),
    Map.of("com.shop.spi", Set.of(helperModule)),
    Map.of(),
    Set.of(),
    Map.of()
);
```

This **exports** the package, it does not **open** it. The caller must still have the necessary read edge and matching classloader/linkage. `isExported("com.shop.spi",helperModule)` is the check closer to the goal; `trySetAccessible` on a private field is not solved by a qualified export alone.

### 7.2. Package Open Is Broader Than "Only Class X"

Once `p` is opened to `H`, code in `H` can deep-reflect into **many classes and members** in `p`. The API does not allow opening **only a single field** via `extraOpens`.

If `com.shop.internal` contains both `PricingState` that needs to be measured and `TokenVault` that must not be accessed, opening that package still opens the whole package. Better approaches may be:

- Provide a public read-only diagnostic API in a separate package.
- Move types needing deep reflection into a dedicated package designed for instrumentation, if you control the source.
- Pass aggregated/redacted statistics through a bridge provided by the application itself.
- Do not collect information that is not genuinely needed.

**Least privilege in JPMS must go hand in hand with package design**, not just a single line of `Map.of(...)`.

## 8. Module Access Does Not Solve Class-Loader Visibility

In a Java agent, there are two easily confused barriers:

```text
A. Class-loader visibility
   Can the target class resolve ProbeBridge?

B. JPMS access/readability
   Does the target's module read the helper module?
   Is the helper package appropriately exported/open?
```

`redefineModule` only handles **B**; it cannot fix a missing class file in a JAR, add a class to all class loaders, or automatically cure a `NoClassDefFoundError` caused by a loader not seeing the helper.

### 8.1. Special Case Where the JVM Supports Java Agents

The `java.lang.instrument` specification states that to support agents that place classes on the search path of the **bootstrap class loader** or the class loader that loads the main agent class, the JVM arranges for the **module of transformed classes** to read the **unnamed module of these two loaders**.

Therefore, when injecting a call to a bootstrap/system unnamed helper, **the necessary read edge may already exist** under Instrumentation rules. You should not always call `redefineModule` for that relationship without checking `targetModule.canRead(helperModule)`.

However, that rule does **not** automatically:

- guarantee the helper class actually resolves from the defining loader;
- export/open the application's private packages to the agent;
- add a read edge to an **arbitrary named helper module** in a custom ModuleLayer;
- allow deep reflection into every package of `java.base`.

When instrumenting classes in a custom loader/module layer, you need to test the actual module, class loader, and helper source rather than applying assumptions from a simple classpath demo.

### 8.2. Getting the Right Module Object

`Class<?>.getModule()` is the reliable source for the module of the **actually defined class**. For example:

```java
Module targetModule = targetClass.getModule();
Module helperModule = helperClass.getModule();
ClassLoader targetLoader = targetClass.getClassLoader();
ClassLoader helperLoader = helperClass.getClassLoader();
```

Do not just use the string `"com.shop.core"` if the application has multiple module layers or different class loaders. A module name is useful information, but it does not prove it is the **exact Module object** containing the actual class. `ModuleLayer.boot().findModule(...)` worked in the demo because the target was loaded by the launcher in the boot layer; that is not how to find an arbitrary module across every application server/plugin loader.

### 8.3. Do Not Use isModifiableModule to Measure "Whether the Agent Sees the Class"

A module may be modifiable while the helper still fails to load. Conversely, the helper may load while the module does not allow further opening. Distinct reasons should be reported:

```text
HELPER_NOT_VISIBLE
MODULE_NOT_READABLE
PACKAGE_NOT_EXPORTED
PACKAGE_NOT_OPEN
MODULE_UNMODIFIABLE
PRIVATE_LOOKUP_DENIED
REFLECTION_DENIED
```

Do not lump everything into "module access failed" and open a bunch of packages. The first diagnostic step is identifying the **exact class, exact module, exact package, exact loader, and the operation being attempted**.

## 9. CLI Flags: Conditionally Equivalent, but Usually Broader

When managing the JVM at startup, JVM options may be more appropriate than mutating modules at runtime:

```shell
# Add qualified opens for a target named module (CLI demo):
java --add-opens=demo.target/demo.target.internal=ALL-UNNAMED \
  --module-path mods \
  -m demo.target/demo.target.Main

# Another example: qualified export of public APIs to a named consumer:
java --add-exports=com.shop.core/com.shop.spi=io.acme.agent.helper ...

# Another example: add readability:
java --add-reads=com.shop.core=io.acme.agent.helper ...
```

Commands containing `...` are **syntax templates**, not standalone runnable shell commands. Module names/paths must be replaced with actual resolved modules. The `--add-opens` option uses the format `<source-module>/<package>=<target-module>(,<target-module>...)`.

### 9.1. ALL-UNNAMED Has a Broad Scope

`ALL-UNNAMED` in the CLI targets **all unnamed modules**, not just the agent's system unnamed module. Therefore, when the agent has `Module helper = OpenAgent.class.getModule()`, the call:

```java
Map.of("demo.target.internal", Set.of(helper))
```

is a **narrower** choice, with a specific module object. If multiple agents/plugins all run in the **same unnamed module**, they will share the privileges granted to that module. Java cannot use a qualified open to target only one class within the receiving module.

### 9.2. One Package Does Not Mean One Class

`--add-opens=java.base/java.lang=ALL-UNNAMED` allows broad deep reflection into the `java.lang` package for every unnamed module. That can be a high-impact change and should not be put into deployment documentation just to silence an unanalyzed `InaccessibleObjectException` warning. Identify the actual field/method, owning package, and caller module first.

### 9.3. Do Not Arbitrarily Copy Compiler Flags to Runtime

`--add-exports` may be used during some build/test phases to compile code accessing unexported APIs, but runtime still requires checking proper module access. `--add-opens` serves deep reflection **at runtime**, not as a way to create a public API contract at compile time. Tests that only pass in the IDE with broad flags can mask real deployment risks.

## 10. Least-Privilege Policy for a Java Agent

A good design should have an **agent-specific permission manifest** (not to be confused with the JAR manifest `Premain-Class`) stating the target and rationale for the grant:

```yaml
features:
  - id: pricing-diagnostic
    enabled: true
    targetModule: com.shop.core
    targetPackage: com.shop.internal
    recipientModule: io.acme.agent.helper
    operation: OPEN_FOR_PRIVATE_REFLECTION
    justification: "Read approved diagnostic counter"
    expectedMembers:
      - "PricingState#sampleCount"
    fallback: SKIP_WITH_REPORT
```

This is an **illustrative policy schema**, not a configuration automatically read by `Instrumentation`. `expectedMembers` only helps **audit and constrain the agent's logic**; JPMS still opens the entire package to the recipient module. The agent must self-enforce that its code uses only the approved member.

### 10.1. Permission Decision Workflow

1. **Identify the measurement:** is private reflection genuinely needed? Can a public API/adapter be used?
2. **Identify the exact target:** class, defining loader, `targetClass.getModule()`, package.
3. **Identify the exact caller:** `helperClass.getModule()`, do not infer from JAR or package name.
4. **Check current state:** `helper.canRead(target)` when needed; `target.isExported(p,helper)` or `target.isOpen(p,helper)` depending on the operation.
5. **Choose the minimal grant:** only the needed package and the exact Module object; do not add unrelated extras.
6. **Ensure the grant source is approved:** deep reflection privileges expand the capabilities of already trusted code and must not automatically escalate when missing.
7. **Precheck modifiability and package membership:** `inst.isModifiableModule(target)`, `target.getPackages().contains(p)`.
8. **Apply the change if genuinely needed:** one `redefineModule` call with exact arguments; avoid pointless repeated calls.
9. **Verify postconditions:** qualified `isOpen`/`isExported`/`canRead` and the actual reflection/helper operation needed.
10. **Report and manage lifecycle:** module/package/recipient, reason, timestamp, JVM/agent version, outcome. Opened privileges may persist for the lifetime of the JVM.

### 10.2. Cases Where Skipping Is Allowed Instead of Expanding Privileges

- The additional metric can be obtained from a public method, without private state.
- The module/package is sensitive and lacks security review approval.
- The exact caller `Module` cannot be determined in a multi-class-loader system.
- The target module is unmodifiable.
- The sought package does not exist in the target module.
- Code would need to read an entire secret object graph when the goal is only latency.
- Opening the package would give other components of the same unnamed module more privileges than needed.
- Instrumentation is already working sufficiently with coarse-grained metrics.

In these cases, a **SKIPPED** status with a transparent reason is better than expanding `--add-opens` to avoid errors.

### 10.3. Audit Without Logging Private Values

Example record:

```json
{
  "feature": "pricing-diagnostic",
  "operation": "QUALIFIED_OPEN",
  "targetModule": "com.shop.core",
  "package": "com.shop.internal",
  "recipientModule": "io.acme.agent.helper",
  "status": "APPLIED",
  "alreadyOpen": false,
  "postconditionVerified": true,
  "privateValuesLogged": false
}
```

This is an illustrative log. You can add target layer/classloader identity in a real system, but avoid recording sensitive information, customer names, credentials, private field values, or protected deployment paths.

**An operational detail:** `redefineModule` is thread-safe per the Javadoc and may be called close together by multiple agents. However, **that does not mean grants automatically roll back or have policy arbitration**. Multiple agents can accumulate reads/exports/opens; the orchestrator needs to audit the total effective permissions and avoid assuming "my agent did not open it, so the package must still be encapsulated."

## 11. Common Errors and Diagnostics

| Symptom | Possible Cause | Analysis / Solution |
|---|---|---|
| `InaccessibleObjectException` on `setAccessible(true)` | Package is not open to the **actual caller module** | Check `target.isOpen(p,callerModule)`, avoid indiscriminate `ALL-UNNAMED` |
| `trySetAccessible()` returns `false` | Insufficient openness or access conditions | Use a proper qualified open; re-verify with the desired access operation |
| `privateLookupIn` throws `IllegalAccessException` | Missing read edge, target package not open, or caller lookup lacks privileges | Check both `caller.canRead(target)` and `target.isOpen(p,caller)` |
| `IllegalAccessError` when bytecode calls public helper | Missing readability/exports or invalid runtime linkage | Check direction M→H, helper package exports to M if named |
| `NoClassDefFoundError` for helper | Loader cannot resolve helper class | Check bootstrap/system/custom loader path; opening a package does not fix classpath |
| `IllegalArgumentException` in `redefineModule` | Package not in target, or map value is an empty set | Use `getPackages()`, dotted package name, and `Set.of(helper)` |
| `UnmodifiableModuleException` | Module cannot be modified | Precheck `isModifiableModule`, report SKIPPED |
| API called but permissions did not change | You may be redefining an **unnamed module** (no-op) or the wrong Module object | Check `module.isNamed()`, actual target/caller |
| Module remains broadly open despite changing agent config | `redefineModule` is additive only, no revocation | Check flags/other agents, consider JVM restart |
| Another package is also accessible | Prior open grant from CLI/module-info/another agent | Check both **before** and **after** state, do not just report "I did not open it" |
| Test passes in IDE, fails in production | IDE adds `--add-opens`, different module layer/loader | Test with real flags and real classloader |
| Agent uses `ALL-UNNAMED` but named helper is still blocked | Target grant applies to unnamed modules, not a named helper | Qualified open to the helper `Module` itself or appropriate module name |
| `isExported==true` but private reflection fails | Exports does not mean opens | Check `isOpen` and adjust design for the access type |
| Field in class of same name still unreadable | Multiple class definitions due to different loaders | Obtain target via the actual `Class<?>`, not just binary name |
| Helper loads but instrumentation still does not work | Module is open but transformer fails to inject probe, or effect unverified | Separate module permissions from ClassFileTransformer QA |

### 11.1. Do Not Fix Errors with a Privilege-Expansion Loop

Anti-pattern:

```text
InaccessibleObjectException
  -> open all packages of the module
  -> still fails with ClassNotFoundException
  -> open java.base next
  -> fails again with NoClassDefFoundError
```

`ClassNotFoundException` and `NoClassDefFoundError` are usually related to **class loading/linkage**, and cannot be fixed by unlimited opens. `InaccessibleObjectException` is a signal regarding deep reflection; you must identify the **specific package** and **caller module**. `IllegalAccessError` can arise from exports/readability or package-private JVM identity, not necessarily just missing opens.

## 12. Testing: Prove Both Granted Access and Denied Access

### 12.1. Positive Tests

- `target.isOpen(approvedPackage,helper)==true` after the operation.
- `Field.trySetAccessible()==true` for the approved field in that package.
- `ClassLoader` resolves the right class; if using `MethodHandles.privateLookupIn`, perform an appropriate lookup and verify.
- Application main continues running if an optional feature has been accepted.

### 12.2. Equally Important Negative Tests

- A second package in the same module **still** has `isOpen(otherPackage,helper)==false`.
- `trySetAccessible()` on a private field in the second package remains false.
- Another module does not receive an unintended qualified open (if there is a way to test with a second module).
- When `--add-opens=...=ALL-UNNAMED` is present, the test detects that the privilege was already broad **before** the agent called `redefineModule`.
- If the package does not exist in the module, the agent **reports an error** rather than trying to open a guessed name.
- If `isModifiableModule=false`, the agent does not call mutation.

### 12.3. Performance, Rollback, Deployment

- Do not call `redefineModule` on every method invocation; mutating permissions is a configuration step in the agent lifecycle.
- Do not reflect on private values just to "test" in production. Use metadata and appropriate postcondition checks while keeping data within allowed policy.
- Control scope across multiple module layers/loaders and different agent attach cycles.
- Do not treat shutting down/restarting a helper as a way to automatically re-close a package. Module permissions already opened are not revoked via `redefineModule`.
- Do not put broad startup flags into production because unit tests "needed to run" without approval.
- Test on actual JDK/VM vendors and module configurations, not just on a sample classpath app.

## 13. Self-Check Questions

1. **Helper H wants to deep-reflect into a private field in package p of module M. Which module must be expanded?** M, via `extraOpens p → {H}`.
2. **Is `extraExports p → {H}` needed if only doing `Field.trySetAccessible`?** No; a qualified open is more appropriate, if API and policy allow.
3. **Is an `extraOpens` map key written as `com/foo/internal` or `com.foo.internal`?** Dotted form `com.foo.internal`.
4. **Does `extraOpens` allow opening only a single class?** No, the unit is a package.
5. **Does `isModifiableModule(unnamedModule)==true` mean calling `redefineModule` will open a new package?** No, the API is a no-op on an unnamed module.
6. **Why can `target.isOpen(p)` be false while `target.isOpen(p,helper)` is true?** Because the package is only **qualified-opened** to the helper.
7. **What does `privateLookupIn` across a module boundary require?** A lookup with appropriate privileges, the helper module reading the target module, and the target package opened to the helper.
8. **If a named module M containing a transformed target calls an unnamed bootstrap helper, must you always add a read edge manually?** No. Java Instrumentation has a JVM rule supporting reading unnamed modules of bootstrap/system for transformed classes; you must still check the loader/actual module.
9. **If the helper class is not found, is opening the app's package enough?** No; you must resolve class-loader visibility.
10. **Why is `ALL-UNNAMED` usually broader than `Set.of(OpenAgent.class.getModule())`?** Because it can include unnamed modules of multiple class loaders.
11. **Does opening `com.shop.internal` give the helper exclusive access only to `PricingState#count`?** No. Code in the helper module can deep-reflect into many members in the package.
12. **Can you call `redefineModule` a second time to revoke a previous open?** No. The API only expands.
13. **To have module M call a public helper in named module H, what are the key relationships?** M reads H; the public helper package in H exports to M; class-loader visibility is still required.
14. **Every time an agent encounters `InaccessibleObjectException`, should it open all of `java.base`?** No. Find the exact target package, caller module, and data genuinely needed.
15. **Why test an unopened package?** To prove that granted privileges do not bleed into other unintended packages.
16. **Does `isModifiableClass` check the modifiability of a module?** No, that is a different API from `isModifiableModule`.
17. **Does opening a package fix a `ClassNotFoundException` caused by the loader not seeing the helper?** No.
18. **If code with the same binary name resides in two custom loaders, whose module should you obtain?** Obtain it via the actual `Class<?>` of the target/caller used in instrumentation.
19. **If the JVM keeps a package open after the agent detaches, is that a bug?** Not necessarily; privileges added via `redefineModule` are not automatically revoked.
20. **An optional measurement feature requires opening a package containing secrets, without approval. What should you choose?** Use another API/metric or **SKIPPED with reason**, do not automatically escalate privileges.

## 14. Official References

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineModule`, `isModifiableModule`, parameters and exceptions.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): behavior of adding reads/exports/opens/uses/provides, unnamed module no-op, thread-safety.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `getPackages`, and qualified access.
- [Java SE 21 — `MethodHandles`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `privateLookupIn` and module readability/opens conditions.
- [Java SE 21 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible`, and `InaccessibleObjectException`.
- [Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR in system unnamed module and JVM support for read edges on transformed classes.
- [Java SE 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--add-reads`, `--add-exports`, `--add-opens`, `--module-path`, and `-m`.
- [JLS SE 21 — `7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): definition of module reads/exports/opens, qualified clauses.
- [JPMS State of the Module System](https://openjdk.org/projects/jigsaw/spec/sotms/): background on readability and strong encapsulation.

**Remember:** do not "open a module" as a blanket operation. Find the **module owning the package**, the **module actually calling the helper/reflection**, and the **type of access needed**. Use qualified `opens` when deep reflection is required, `exports` for public APIs, and `reads` for readability; only add missing relationships via `Instrumentation.redefineModule`, verify postconditions, and **do not treat granted privileges as automatically revocable**.